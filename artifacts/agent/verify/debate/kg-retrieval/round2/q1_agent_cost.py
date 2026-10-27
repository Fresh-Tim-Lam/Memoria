"""Q1 / C 角度：重切边界对检索路径与 token 成本的影响（数字通信原理固定快照）。

只读；输出 JSON。规则（design kg-agent-index-v0 §6.3）：
  · 以 markdown 标题（section）为语义边界；
  · section 估算 token > 3000 时按下级编号/块边界拆（这里按 ceil(span_tokens/3000) 估计）；
  · 不切公式/表格块（本脚本不细分，仅作数量级估算，标注为估算）。

产物：
  · 每章 chars/tokens/section 数/估算 slice 数
  · 选项①（只重算 end）下 read_kp 返回 token 的变化（用 D1 的 hint/heading 口径）
  · 全库重切后索引条目体积（不写 description / 写 description 两种）
  · 若用 LLM 写 description 的一次性 token 成本（0.4237 tok/字 + 价格）
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

REPO = r"D:\AAA_Jupyter\Memoria"
KB = r"D:\AAA_Courses\数字通信原理"
SNAPSHOT = os.path.join(REPO, "artifacts/agent/verify/debate/kg-retrieval/data/corpus-snapshot.json")
TOKEN_PER_CHAR = 0.4237
SLICE_TARGET_TOKENS = 3000
DESC_TOKENS = 34.0  # ≤80 汉字 × 0.4237
ENTRY_COMPACT_TOKENS = 6.0  # num+title（~14 字）→ ≈14.1×0.4237≈6 tok
ENTRY_WITH_DESC_TOKENS = ENTRY_COMPACT_TOKENS + DESC_TOKENS + 8.0  # +snippet/anchor 近似
PEAK = {"hit": 0.04, "miss": 2.0, "output": 8.0}
IDLE = {"hit": 0.02, "miss": 1.0, "output": 4.0}


def read_text(path: str) -> str:
    import io

    return io.open(path, encoding="utf-8", errors="replace").read()


def section_spans(text: str) -> list[tuple[int, int]]:
    """按 markdown 标题切 section：返回 (start_line, end_line) 0-based 半开区间。"""
    lines = text.splitlines()
    heads: list[int] = []
    in_fence = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        if line.startswith("#"):
            heads.append(i)
    if not heads:
        return [(0, len(lines))]
    spans: list[tuple[int, int]] = []
    for idx, start in enumerate(heads):
        end = heads[idx + 1] if idx + 1 < len(heads) else len(lines)
        spans.append((start, end))
    return spans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    snap = json.load(open(SNAPSHOT, encoding="utf-8"))
    snap_kb = snap["kbs"]["数字通信原理"]
    snap_bytes = {row["path"]: row["bytes"] for row in snap_kb.get("md") or []}
    md_paths = []
    for root, _dirs, files in os.walk(KB):
        if ".memoria" in root:
            continue
        for f in files:
            if f.endswith(".md"):
                md_paths.append(os.path.join(root, f))
    md_paths.sort()

    drift = []
    chapter_rows = []
    total_chars = 0
    total_tokens = 0
    total_slices = 0
    total_sections = 0
    for path in md_paths:
        rel = os.path.relpath(path, KB).replace("\\", "/")
        if not rel.startswith("教材/"):
            continue
        text = read_text(path)
        chars = len(text)
        tokens = chars * TOKEN_PER_CHAR
        spans = section_spans(text)
        sections = len(spans)
        slices = 0
        for start, end in spans:
            span_tokens = sum(len(lines_i) + 1 for lines_i in text.splitlines()[start:end]) * TOKEN_PER_CHAR
            slices += max(1, int(span_tokens // SLICE_TARGET_TOKENS) + (1 if span_tokens % SLICE_TARGET_TOKENS else 0))
        actual_bytes = os.path.getsize(path)
        snap_b = snap_bytes.get(rel)
        if snap_b is not None and snap_b != actual_bytes:
            drift.append({"file": rel, "snapshot_bytes": snap_b, "actual_bytes": actual_bytes})
        total_chars += chars
        total_tokens += tokens
        total_slices += slices
        total_sections += sections
        chapter_rows.append(
            {
                "file": rel,
                "chars": chars,
                "tokens": round(tokens, 0),
                "sections": sections,
                "slices_est": slices,
            }
        )

    # 选项①：只重算 end → 用 D1 的 hint（现状）vs heading（下一同级标题）口径对比 read_kp 返回 token
    obj = json.load(open(os.path.join(REPO, "artifacts/agent/verify/debate/kg-retrieval/data/phase3-objections.json"), encoding="utf-8"))
    d1 = obj["D1_span_calib"]["by_method_by_role"]["教材"]
    cur = d1["hint"]
    new = d1["heading"]

    def tk(chars: float) -> float:
        return round(chars * TOKEN_PER_CHAR, 0)

    opt1_readkp = {
        "role": "教材",
        "n": cur["n"],
        "hint_p50_chars": cur["p50"],
        "hint_p90_chars": cur["p90"],
        "heading_p50_chars": new["p50"],
        "heading_p90_chars": new["p90"],
        "hint_p50_tokens": tk(cur["p50"]),
        "hint_p90_tokens": tk(cur["p90"]),
        "heading_p50_tokens": tk(new["p50"]),
        "heading_p90_tokens": tk(new["p90"]),
        "p50_delta_pct": round((new["p50"] / cur["p50"] - 1) * 100, 1),
        "p90_delta_pct": round((new["p90"] / cur["p90"] - 1) * 100, 1),
        "gt4000tok_after_pct": new["gt3000"],  # >3000 字 ≈ >1271 tok；这里仅作下界参考
    }

    # 索引体积（不写 description / 写 description）
    idx_no_desc = total_slices * ENTRY_COMPACT_TOKENS
    idx_with_desc = total_slices * ENTRY_WITH_DESC_TOKENS
    kp_names_only = 2074.0  # coverage.json index_cost.names_only_tokens_est（358 KP）

    # LLM 生成 description 的一次性成本（若在重切时生成；两种方式）
    def llm_cost(desc_tokens_total: float, read_tokens_total: float, call_overhead_tokens: float) -> dict:
        out = {}
        for name, price in (("peak", PEAK), ("idle", IDLE)):
            cost = (
                read_tokens_total * price["miss"]
                + desc_tokens_total * price["output"]
                + call_overhead_tokens * price["miss"]
            ) / 1_000_000
            out[name] = round(cost, 4)
        return out

    per_slice_desc = total_slices * DESC_TOKENS
    per_call_overhead = total_slices * 150.0  # 系统/模板/格式约束的保守估计
    per_chapter_overhead = 14 * 150.0
    llm_desc = {
        "per_slice_calls": llm_cost(per_slice_desc, total_tokens, per_call_overhead),
        "per_chapter_batch": llm_cost(per_slice_desc, total_tokens, per_chapter_overhead),
        "note": "input=重切后正文 token 合计（608k 级）；output=每片 description ≤80 字×0.4237；overhead 为经验估计",
    }

    report = {
        "kb": KB,
        "snapshot_taken_at": snap.get("taken_at"),
        "token_per_char": TOKEN_PER_CHAR,
        "chapters": chapter_rows,
        "totals": {
            "chapters": len(chapter_rows),
            "chars": total_chars,
            "tokens": int(total_tokens),
            "sections": total_sections,
            "slices_est": total_slices,
            "slices_per_chapter_p50": statistics.median([r["slices_est"] for r in chapter_rows]),
        },
        "drift_vs_snapshot": {"n": len(drift), "files": drift[:5]},
        "option1_read_kp_delta": opt1_readkp,
        "index_artifact_tokens": {
            "current_kp_names_only": kp_names_only,
            "slices_no_desc": round(idx_no_desc),
            "slices_with_desc": round(idx_with_desc),
            "per_slice_entry_compact": ENTRY_COMPACT_TOKENS,
            "per_slice_entry_with_desc": ENTRY_WITH_DESC_TOKENS,
        },
        "llm_description_cost_yuan": llm_desc,
        "assumptions": {
            "slice_rule": "section 边界；section > 3000 tok 时 ceil(span/3000) 拆分（数量级估算，未按块边界精确切）",
            "desc": "每片 description ≤80 汉字 ≈ 34 tok output",
            "price": "deepseek-flash 高峰 hit0.04/miss2.0/out8.0；空闲 0.02/1.0/4.0（元/M）",
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
