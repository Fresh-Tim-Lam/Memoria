#!/usr/bin/env python3
"""G05 · 锚定「图谱渲染」基线（改造前）

跑 `render_l1.mjs` 采集 L1 无头分账数据，盖上 commit / 语料指纹 / 时间戳，落盘
`results/render-<label>_<sha>.{json,md}`，供后续优化做 A/B 对照（见 docs/design/graph-benchmark.md）。

用法：
    python scripts/benchmark/graph/anchor_render_baseline.py                 # label=baseline
    python scripts/benchmark/graph/anchor_render_baseline.py --label after-d1
    python scripts/benchmark/graph/anchor_render_baseline.py --scales 100,500 --frames 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
MJS = HERE / "render_l1.mjs"


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=False
    )
    return proc.stdout.strip()


def corpus_digest(payload: dict) -> str:
    """语料指纹（计数口径）：确定性 seed 下各档的 (scale, pattern, 节点数, 边数)。"""
    parts = [
        f"seed={payload['seed']}",
        f"view={payload['view']['w']}x{payload['view']['h']}@{payload['view']['dpr']}",
    ]
    for r in payload["results"]:
        parts.append(f"{r['pattern']}:{r['scale']}:{r['nodeCount']}:{r['linkCount']}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def render_md(meta: dict, payload: dict) -> str:
    L = [
        "# 图谱渲染基线（L1 无头 · 2D）",
        "",
        f"- 基线 commit：`{meta['sha']}`（工作区：{meta['tree_state']}）",
        f"- 记录时间：{meta['recorded_at']}",
        f"- 语料：`syntheticGraph`（seed={payload['seed']}）"
        f" × scales={meta['scales']} × patterns={meta['patterns']}"
        f"（指纹 `{meta['corpus_digest']}`）",
        f"- 视口：{payload['view']['w']}×{payload['view']['h']} @dpr{payload['view']['dpr']}；"
        f"每帧 {payload['results'][0]['ticksPerFrame']} tick；采样 {payload['frames']} 帧（报 p50/p95）",
        "- 方法：走真机同链路（`engine.loadPayload()` → `view.resetSimulation()` → "
        "`layout.loadFromEngine()` 含 160 tick warmup），随后逐帧分账计时："
        "`tickMs` = 1 次 `layout.runFrameTicks()`（**内含帧预算决策，与真机 `start()` 同入口**）；"
        "`drawMs` = 1 次 `view.draw()`（绘制调用次数由 recording stub canvas ctx 统计）",
        "",
        "## 分账结果（ms）",
        "",
        f"- 帧预算：`frameBudgetMs={payload['results'][0]['frameBudgetMs']}`"
        f"（显式覆盖 {payload['frameBudgetOverride']}；0 = 关闭预算 = 旧行为）"
        f"，上限 `maxTicksPerFrame={payload['results'][0]['ticksPerFrame']}`",
        f"- 装载（含 160 tick warmup，**无预算**）："
        + "；".join(f"{r['pattern'][:4]}{r['scale']}={r['loadMs']:.0f}ms" for r in payload["results"]),
        "",
        "| pattern | 节点 | 边 | 群 | 实际 tick/帧 | **布局 tick p50** | 布局 p95 | 绘制 p50 | "
        "绘制 p95 | **单帧合计 p50** | 单帧合计 p95 | hover 绘制 p50 | 绘制调用/帧 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in payload["results"]:
        L.append(
            f"| {r['pattern']} | {r['nodeCount']} | {r['linkCount']} | {r['groupCount']} | "
            f"{r['ticksRun']['mean']} | "
            f"**{r['tickMs']['p50']}** | {r['tickMs']['p95']} | "
            f"**{r['drawMs']['p50']}** | {r['drawMs']['p95']} | "
            f"**{r['frameMs']['p50']}** | {r['frameMs']['p95']} | "
            f"{r['hoverDrawMs']['p50']} | {r['callsPerDrawTotal']} |"
        )

    L += [
        "",
        "> 判读：`单帧合计` 与 16.7ms（60fps 预算）比。超过预算 ⇒ 拖拽必掉帧，"
        "且**先看是布局列还是绘制列**——这两列的优化手段完全不同。",
        "",
        "## 若不做「静止停帧」的每秒代价",
        "",
        "> 现状：图谱页签可见期间 rAF 循环常驻、alpha 冷却后仍按 ~60fps 重绘"
        "（见 `docs/design/graph-benchmark.md` §现状诊断）。下表是这一档每秒白付的量。",
        "",
        "| pattern | 节点 | 布局 tick/秒 (ms) | 绘制/秒 (ms) | 绘制调用/秒 |",
        "|---|---|---|---|---|",
    ]
    for r in payload["results"]:
        idle = r["idlePerSecIfNeverStop"]
        L.append(
            f"| {r['pattern']} | {r['nodeCount']} | {idle['tickMs']} | {idle['drawMs']} | "
            f"{idle['calls']} |"
        )

    L += [
        "",
        "## 布局质量代理指标（供近似排斥 A/B 对照观感）",
        "",
        "| pattern | 节点 | 边长 p50 | 边长 p95 | 边长 max | 参与统计边数 | 跳过 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in payload["results"]:
        q = r["quality"]
        L.append(
            f"| {r['pattern']} | {r['nodeCount']} | {q['edgeLenP50']} | {q['edgeLenP95']} | "
            f"{q['edgeLenMax']} | {q['edgeCount']} | {q['edgeSkipped']} |"
        )

    L += [
        "",
        "## 口径与边界（结论必须带这些前提）",
        "",
        "1. 无头环境**没有真 canvas**：绘制只测「调用次数 + JS 侧耗时」，"
        "**不含光栅化与 GPU** —— 真机的 `drawMs` 会高于此表。",
        "2. ≥60 节点时真机布局跑在 Web Worker；本层量的是同一份 sim-core 代码在**主线程**的口径，"
        "绝对值有偏差、量级可比。",
        "3. 真帧率 / 长任务 / 3D 必须走 **L2 浏览器层**，本层不能替代。",
        "4. 仅覆盖 2D（Canvas 2D）；3D 需 WebGL。",
        "",
        f"- 原始数据：`results/render-{meta['label']}_{meta['sha']}.json`",
        f"- 采集命令：`{meta['cmd']}`",
    ]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="锚定图谱渲染 L1 基线")
    ap.add_argument("--label", default="baseline", help="产物名标签（默认 baseline）")
    ap.add_argument("--scales", default=None)
    ap.add_argument("--patterns", default=None)
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not MJS.is_file():
        raise SystemExit(f"缺少采集脚本：{MJS}")

    cmd = ["node", str(MJS), "--frames", str(args.frames), "--seed", str(args.seed)]
    if args.scales:
        cmd += ["--scales", args.scales]
    if args.patterns:
        cmd += ["--patterns", args.patterns]

    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout)
        return proc.returncode
    payload = json.loads(proc.stdout)

    sha = git("rev-parse", "--short", "HEAD") or "unknown"
    dirty = bool(git("status", "--porcelain"))
    meta = {
        "label": args.label,
        "sha": sha,
        "tree_state": "dirty（含未提交改动）" if dirty else "clean",
        "recorded_at": datetime.now(UTC).isoformat(),
        "corpus_digest": corpus_digest(payload),
        "scales": sorted({r["scale"] for r in payload["results"]}),
        "patterns": sorted({r["pattern"] for r in payload["results"]}),
        "cmd": " ".join(cmd),
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = f"render-{args.label}_{sha}"
    (RESULTS / f"{stem}.json").write_text(
        json.dumps({"meta": meta, **payload}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (RESULTS / f"{stem}.md").write_text(render_md(meta, payload), encoding="utf-8")
    print(f"[anchor] written {RESULTS / (stem + '.md')}")
    print(f"[anchor] written {RESULTS / (stem + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
