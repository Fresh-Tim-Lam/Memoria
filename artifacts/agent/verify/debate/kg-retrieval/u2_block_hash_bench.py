"""U-2 实测：块级 hash 的计算耗时（task-191 addendum ②）

## 要回答的问题（Lead 定的判据）

> 真库（12 sidecar / 357 KP / 58 md / 5.27MB）全量计算块 hash 的耗时，
> 以及【增量场景】：改 1 个文件时只重算该文件。
> 判据：单文件 < 50ms ⇒ 可放进保存流程；> 500ms ⇒ 必须异步。

## 块的定义（与提案 §4.5 一致）

按 Markdown **结构块**切分：heading 行 / 段落（连续非空行）/ 代码块 / 表格。
一个块 = 连续的若干行，边界在 heading 行之前。

## 口径（与提案 §3.3 一致，必须写死）

    block_hash = sha256(LF归一化(行去尾空白).join("\n") + "\n")

用法：python .../u2_block_hash_bench.py
"""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

KB = Path("D:/AAA_Courses/数字通信原理")
REPO = Path(__file__).resolve().parents[5]

#: 判据阈值（Lead 给定）
SYNC_THRESHOLD_MS = 50.0
ASYNC_THRESHOLD_MS = 500.0


def _norm_lines(text: str) -> list[str]:
    """LF 归一化 + 去行尾空白（不剥 BOM）。"""
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def split_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """按 Markdown 结构切块，返回 [(start_idx, end_idx_exclusive), ...]。

    规则（刻意保持简单可预测）：
      · 以 ATX heading（`#` 开头）为**新块起点**
      · 连续非空行为一段
      · 空行分隔段落
      · fenced code block 整体算一个块（``` 配对）
    """
    blocks: list[tuple[int, int]] = []
    i = 0
    n = len(lines)
    cur_start = 0
    in_fence = False
    fence_marker = ""

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
                i += 1
                continue
            if marker == fence_marker:
                in_fence = False
                i += 1
                continue
            i += 1
            continue

        if in_fence:
            i += 1
            continue

        # heading ⇒ 关闭当前块，开新块
        if stripped.startswith("#"):
            if i > cur_start:
                blocks.append((cur_start, i))
            cur_start = i
            i += 1
            continue

        # 空行 ⇒ 关闭当前块（段落边界）
        if not stripped:
            if i > cur_start:
                blocks.append((cur_start, i))
            i += 1
            cur_start = i
            continue

        i += 1

    if cur_start < n:
        blocks.append((cur_start, n))
    return blocks


def block_hash(lines: list[str], start: int, end: int) -> str:
    payload = "\n".join(lines[start:end]).rstrip("\n") + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> tuple[int, float]:
    """返回 (块数, 耗时毫秒)。"""
    t0 = time.perf_counter()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = _norm_lines(text)
    blocks = split_blocks(lines)
    for s, e in blocks:
        block_hash(lines, s, e)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return len(blocks), elapsed_ms


def main() -> int:
    if not KB.is_dir():
        print(f"[SKIP] 真库不可访问：{KB}")
        return 0

    md_files = sorted(KB.rglob("*.md"))
    total_bytes = sum(p.stat().st_size for p in md_files)
    print("=== U-2：块级 hash 计算耗时实测 ===")
    print(f"库：{KB}")
    print(f"md 文件：{len(md_files)}   总字节：{total_bytes:,} ({total_bytes/1024/1024:.2f} MB)")
    print()

    # ── 全量 ─────────────────────────────────────────────────────────
    per_file: list[tuple[str, int, float, int]] = []
    t_all0 = time.perf_counter()
    for p in md_files:
        nblocks, ms = hash_file(p)
        per_file.append((p.name, nblocks, ms, p.stat().st_size))
    full_ms = (time.perf_counter() - t_all0) * 1000
    total_blocks = sum(n for _, n, _, _ in per_file)

    print(f"全量：{full_ms:.1f} ms   块总数：{total_blocks}")
    print()

    # ── 单文件 ───────────────────────────────────────────────────────
    times = [ms for _, _, ms, _ in per_file]
    print("单文件耗时分布：")
    print(f"  min    {min(times):.2f} ms")
    print(f"  median {statistics.median(times):.2f} ms")
    print(f"  mean   {statistics.mean(times):.2f} ms")
    print(f"  max    {max(times):.2f} ms  ({max(per_file, key=lambda x: x[2])[0]})")
    print(f"  p90    {sorted(times)[int(len(times)*0.9)]:.2f} ms")
    print()

    print("最大的 3 个文件：")
    for name, nblocks, ms, size in sorted(per_file, key=lambda x: -x[3])[:3]:
        print(f"  {name:<45} {size/1024:>8.1f} KB  {nblocks:>5} 块  {ms:>7.2f} ms")
    print()

    # ── 增量场景：改 1 个文件 ────────────────────────────────────────
    largest = max(per_file, key=lambda x: x[2])
    print("增量场景（改 1 个文件 ⇒ 只重算该文件）：")
    print(f"  最坏（最大文件 {largest[0]}）：{largest[2]:.2f} ms")
    print(f"  典型（中位文件）：{statistics.median(times):.2f} ms")
    print()

    # ── 判据 ─────────────────────────────────────────────────────────
    worst_single = max(times)
    if worst_single < SYNC_THRESHOLD_MS:
        verdict = f"✅ 单文件最坏 {worst_single:.1f}ms < {SYNC_THRESHOLD_MS}ms ⇒ 可放进保存同步路径"
    elif worst_single > ASYNC_THRESHOLD_MS:
        verdict = f"🔴 单文件最坏 {worst_single:.1f}ms > {ASYNC_THRESHOLD_MS}ms ⇒ 必须异步"
    else:
        verdict = (f"⚠️ 单文件最坏 {worst_single:.1f}ms 介于 {SYNC_THRESHOLD_MS}–{ASYNC_THRESHOLD_MS}ms "
                   f"⇒ 建议：保存路径只算变更块，全量走异步")
    print(f"判据结论：{verdict}")

    out = REPO / "artifacts/agent/verify/debate/kg-retrieval/u2-block-hash-bench.json"
    out.write_text(
        json.dumps(
            {
                "kb": str(KB),
                "md_files": len(md_files),
                "total_bytes": total_bytes,
                "total_blocks": total_blocks,
                "full_ms": round(full_ms, 2),
                "per_file_min_ms": round(min(times), 2),
                "per_file_median_ms": round(statistics.median(times), 2),
                "per_file_max_ms": round(worst_single, 2),
                "verdict": verdict,
                "files": [
                    {"name": n, "blocks": b, "ms": round(ms, 2), "bytes": sz}
                    for n, b, ms, sz in per_file
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
