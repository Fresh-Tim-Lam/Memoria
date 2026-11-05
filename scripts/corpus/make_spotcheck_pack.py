#!/usr/bin/env python
"""生成人类抽检包（protocol v2）：只含“分歧项 + 随机 5 KP / 5 对”的上下文片段。

目标：人类**不读 126k 字符全文**，只看本包：
- 两位 agent 标注（agent-a/agent-b）的分歧项（span 边界 / concept_type / 存在性 / 类型 / 方向）；
- 随机抽样：5 个无分歧 KP + 5 个无分歧候选对（固定 seed，可复核）；
- 每项只给 `chapter.txt` 的 **±N 字符上下文窗口** 与待裁决问题，**绝不塞全文**。

输入（两位 agent 标签，尚未生成时工具不运行；本脚本不生成任何标签）：
  artifacts/corpus/pilot/agent-labels/agent-a/kps.agent-a.jsonl
  artifacts/corpus/pilot/agent-labels/agent-a/pool-judgments.agent-a.jsonl
  （agent-b 同理）
输出：
  artifacts/corpus/pilot/spotcheck/SPOTCHECK-PACK.md   ← 人类填写（裁决表）
  artifacts/corpus/pilot/spotcheck/spotcheck-pack.json ← 机器可读（含上下文总字节/项数估计）

退出码：0 = 已生成；2 = 输入缺失/解析失败（不伪造包）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iaa_runner  # noqa: E402

S0_TYPES = {"contain", "reference", "extend"}
MAX_DIFF_ITEMS_DEFAULT = 24
MAX_ITEMS_DEFAULT = 40


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _span_of(kp: dict) -> tuple[int, int] | None:
    spans = kp.get("spans")
    if isinstance(spans, list) and spans and isinstance(spans[0], dict):
        s, e = spans[0].get("start"), spans[0].get("end")
        if isinstance(s, int) and isinstance(e, int) and 0 <= s < e:
            return s, e
    return None


def excerpt(chapter: str, start: int, end: int, context: int, label: str) -> dict:
    lo = max(0, start - context)
    hi = min(len(chapter), end + context)
    return {
        "side": label,
        "span": {"start": start, "end": end},
        "window": {"start": lo, "end": hi},
        "text": chapter[lo:hi],
        "truncated_left": lo > 0,
        "truncated_right": hi < len(chapter),
        "chars": hi - lo,
    }


def _kp_side(kp: dict, chapter: str, context: int, label: str) -> dict:
    span = _span_of(kp) or (0, 0)
    return {
        "id": kp.get("id"),
        "concept_type": kp.get("concept_type"),
        "type_uncertain": bool(kp.get("type_uncertain")),
        "excerpt": excerpt(chapter, span[0], span[1], context, label),
    }


def _kpis(kps_a: list[dict], kps_b: list[dict], chapter: str, context: int,
          seed: int, sample_kps: int) -> dict:
    matching = iaa_runner.match_kp_spans(kps_a, kps_b)
    a_by = {k["id"]: k for k in kps_a}
    b_by = {k["id"]: k for k in kps_b}
    diff_items: list[dict] = []
    for m in matching["pairs"]:
        a, b = a_by[m["gold_id"]], b_by[m["second_id"]]
        sa, sb = _span_of(a), _span_of(b)
        kinds = []
        if sa != sb:
            kinds.append("span_boundary")
        if a.get("concept_type") != b.get("concept_type"):
            kinds.append("concept_type")
        if not kinds:
            continue
        item = {
            "item_id": f"kp-diff-{len(diff_items) + 1:02d}",
            "item_type": "disagreement",
            "kind": "kp",
            "kinds": kinds,
            "matched_iou": m["iou"],
            "a": _kp_side(a, chapter, context, "A"),
            "b": _kp_side(b, chapter, context, "B"),
            "question": "两段 span/类型不一致：按手册 v1.1 §1.2/§1.6，是否接受其中一方？",
            "decision": "",
            "level": "",
            "reviewer": "",
            "date": "",
        }
        diff_items.append(item)
    for kid in matching["unmatched_gold"]:
        a = a_by[kid]
        diff_items.append({
            "item_id": f"kp-diff-{len(diff_items) + 1:02d}", "item_type": "disagreement",
            "kind": "kp", "kinds": ["unmatched_a"], "matched_iou": 0.0,
            "a": _kp_side(a, chapter, context, "A"), "b": None,
            "question": "A 有、B 无对应 span：保留 A / 删除 / 并入其它 KP？",
            "decision": "", "level": "", "reviewer": "", "date": "",
        })
    for kid in matching["unmatched_second"]:
        b = b_by[kid]
        diff_items.append({
            "item_id": f"kp-diff-{len(diff_items) + 1:02d}", "item_type": "disagreement",
            "kind": "kp", "kinds": ["unmatched_b"], "matched_iou": 0.0,
            "a": None, "b": _kp_side(b, chapter, context, "B"),
            "question": "B 有、A 无对应 span：保留 B / 删除 / 并入其它 KP？",
            "decision": "", "level": "", "reviewer": "", "date": "",
        })
    # 随机抽样：无分歧的 matched pairs
    clean = [m for m in matching["pairs"]
             if _span_of(a_by[m["gold_id"]]) == _span_of(b_by[m["second_id"]])
             and a_by[m["gold_id"]].get("concept_type") == b_by[m["second_id"]].get("concept_type")]
    rng = random.Random(seed)
    sample = rng.sample(clean, k=min(sample_kps, len(clean))) if clean else []
    sample_items = []
    for m in sample:
        a, b = a_by[m["gold_id"]], b_by[m["second_id"]]
        sample_items.append({
            "item_id": f"kp-sample-{len(sample_items) + 1:02d}",
            "item_type": "spotcheck",
            "kind": "kp",
            "kinds": [],
            "matched_iou": m["iou"],
            "a": _kp_side(a, chapter, context, "A"),
            "b": _kp_side(b, chapter, context, "B"),
            "question": "随机抽检：该 span/类型是否可接受？（是 / 否 + 理由）",
            "decision": "", "level": "", "reviewer": "", "date": "",
        })
    return {"diffs": diff_items, "samples": sample_items,
            "stats": {"matched": matching["matched_count"],
                      "unmatched_a": len(matching["unmatched_gold"]),
                      "unmatched_b": len(matching["unmatched_second"]),
                      "clean_matched": len(clean)}}


def _edge_value(row: dict | None) -> dict:
    if not row:
        return {"label": None, "type": None, "direction": None,
                "confidence": None, "rationale": None}
    return {k: row.get(k) for k in ("label", "type", "direction", "confidence", "rationale")}


def _edge_side(row: dict | None, kps_by_id: dict, chapter: str, context: int,
               label: str) -> dict | None:
    if row is None:
        return None
    span = None
    a_span = row.get("assertion_span")
    if isinstance(a_span, dict) and isinstance(a_span.get("start"), int) \
            and isinstance(a_span.get("end"), int):
        span = (a_span["start"], a_span["end"])
    if span is None:
        s = _span_of(kps_by_id.get(row.get("source"), {})) if row.get("source") else None
        t = _span_of(kps_by_id.get(row.get("target"), {})) if row.get("target") else None
        if s and t:
            span = (min(s[0], t[0]), max(s[1], t[1]))
    if span is None:
        return {"pair_id": row.get("pair_id"), **_edge_value(row), "excerpt": None,
                "note": "无 assertion_span，无法给上下文（需补证据）"}
    return {"pair_id": row.get("pair_id"), **_edge_value(row),
            "excerpt": excerpt(chapter, span[0], span[1], context, label)}


def _edges(pool_a: list[dict], pool_b: list[dict], pool: list[dict], kps_a: list[dict],
           kps_b: list[dict], chapter: str, context: int, seed: int,
           sample_pairs: int) -> dict:
    a_by = {r["pair_id"]: r for r in pool_a if r.get("pair_id")}
    b_by = {r["pair_id"]: r for r in pool_b if r.get("pair_id")}
    kps_a_by = {k["id"]: k for k in kps_a}
    kps_b_by = {k["id"]: k for k in kps_b}
    diff_items: list[dict] = []
    clean_pairs: list[str] = []
    for item in pool:
        pair_id = item["pair_id"]
        a, b = a_by.get(pair_id), b_by.get(pair_id)
        if a is None or b is None:
            kinds = ["missing_a"] if a is None else ["missing_b"]
        else:
            a_edge, b_edge = a.get("label") == "edge", b.get("label") == "edge"
            kinds = []
            if a_edge != b_edge:
                kinds.append("existence")
            elif a_edge:
                if a.get("type") != b.get("type"):
                    kinds.append("edge_type")
                if a.get("direction") != b.get("direction"):
                    kinds.append("edge_direction")
        if kinds:
            diff_items.append({
                "item_id": f"edge-diff-{len(diff_items) + 1:02d}",
                "item_type": "disagreement", "kind": "edge", "kinds": kinds,
                "pair_id": pair_id, "source": item["source"], "target": item["target"],
                "a": _edge_side(a, kps_a_by, chapter, context, "A"),
                "b": _edge_side(b, kps_b_by, chapter, context, "B"),
                "question": "该候选对：边/类型/方向按手册 v1.1 §2 应如何裁决？",
                "decision": "", "level": "", "reviewer": "", "date": "",
            })
        else:
            clean_pairs.append(pair_id)
    rng = random.Random(seed + 1)
    sample_pairs_sel = rng.sample(clean_pairs, k=min(sample_pairs, len(clean_pairs))) if clean_pairs else []
    sample_items = []
    for pair_id in sample_pairs_sel:
        item = next(p for p in pool if p["pair_id"] == pair_id)
        a, b = a_by.get(pair_id), b_by.get(pair_id)
        sample_items.append({
            "item_id": f"edge-sample-{len(sample_items) + 1:02d}",
            "item_type": "spotcheck", "kind": "edge", "kinds": [],
            "pair_id": pair_id, "source": item["source"], "target": item["target"],
            "a": _edge_side(a, kps_a_by, chapter, context, "A"),
            "b": _edge_side(b, kps_b_by, chapter, context, "B"),
            "question": "随机抽检：该 pair 判定是否可接受？（是 / 否 + 理由）",
            "decision": "", "level": "", "reviewer": "", "date": "",
        })
    return {"diffs": diff_items, "samples": sample_items,
            "stats": {"pool": len(pool), "a_rows": len(pool_a), "b_rows": len(pool_b),
                      "clean_pairs": len(clean_pairs)}}


def _render_markdown(pack: dict) -> str:
    lines = [
        "# SPOTCHECK-PACK — 人类抽检/裁决包（protocol v2）",
        "",
        "> 本包只含**分歧项 + 随机抽样**的 chapter 上下文片段（每项 ±%d 字符），"
        "**不含 chapter 全文**；不需要阅读 126k 全文。" % pack["context_window_chars"],
        "> 填写方式：每项在 `decision` 写 `采 A` / `采 B` / `重判：<结论>` / `无法裁决`；"
        "可补 `level`(A/B/C)、`reviewer`、`date`。保存到 `adjudication-log.jsonl`。",
        "",
        "## 概览",
        "",
        f"- 分歧项：{pack['counts']['diffs']}（KP {pack['counts']['kp_diffs']} / 边 {pack['counts']['edge_diffs']}；"
        f"可用 {pack['counts']['diffs_available']}，已截断 {pack['counts']['diffs_truncated']}）",
        f"- 随机抽检：{pack['counts']['samples']}（KP {pack['counts']['kp_samples']} / 对 {pack['counts']['edge_samples']}）",
        f"- 上下文总量：{pack['context_chars_total']} 字符（chapter 共 {pack['chapter_chars']} 字符，"
        f"占比 {pack['context_chars_total'] / max(1, pack['chapter_chars']):.2%}）",
        f"- 预计人类时间：约 {pack['est_human_minutes']} 分钟（≤120）",
        "",
        "## 逐项（人类填写）",
        "",
    ]
    for idx, item in enumerate(pack["items"], 1):
        lines.append(f"### {idx}. {item['item_id']} · {item['item_type']} · {item['kind']} "
                     f"· kinds={','.join(item.get('kinds') or ['-'])}")
        lines.append("")
        if item["kind"] == "kp":
            for side in ("a", "b"):
                side_data = item.get(side)
                if side_data:
                    lines.append(f"- {side.upper()}：id={side_data['id']} type={side_data['concept_type']} "
                                 f"span={side_data['excerpt']['span']}")
        else:
            lines.append(f"- pair_id={item['pair_id']} {item['source']} -> {item['target']}")
            for side in ("a", "b"):
                side_data = item.get(side)
                if side_data:
                    lines.append(f"- {side.upper()}：label={side_data.get('label')} type={side_data.get('type')} "
                                 f"direction={side_data.get('direction')}")
        if item.get("question"):
            lines.append(f"- 问题：{item['question']}")
        for side in ("a", "b"):
            side_data = item.get(side)
            if not side_data or not side_data.get("excerpt"):
                continue
            ex = side_data["excerpt"]
            lines.append(f"- {side.upper()} 上下文 [窗口 {ex['window']['start']},{ex['window']['end']})"
                         f"（span={ex['span']}，{'左侧截断' if ex['truncated_left'] else ''}"
                         f"{'右侧截断' if ex['truncated_right'] else ''}）：")
            lines.append("")
            lines.append("```text")
            lines.append(ex["text"])
            lines.append("```")
        lines.append("")
        lines.append("| decision | level | reviewer | date |")
        lines.append("|---|---|---|---|")
        lines.append(f"| {item.get('decision', '')} | {item.get('level', '')} | "
                     f"{item.get('reviewer', '')} | {item.get('date', '')} |")
        lines.append("")
    lines.append("## 结论（人类填写）")
    lines.append("")
    lines.append("| 接受 A | 接受 B | 重判 | 无法裁决 | 耗时（分钟） | 签名 |")
    lines.append("|---|---|---|---|---|---|")
    lines.append("|  |  |  |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def build(agent_a_dir: Path, agent_b_dir: Path, chapter_path: Path, pool_path: Path,
          seed: int = 373, sample_kps: int = 5, sample_pairs: int = 5,
          context: int = 260, max_diff_items: int = MAX_DIFF_ITEMS_DEFAULT,
          max_items: int = MAX_ITEMS_DEFAULT) -> dict:
    kps_a = read_jsonl(agent_a_dir / "kps.agent-a.jsonl")
    kps_b = read_jsonl(agent_b_dir / "kps.agent-b.jsonl")
    pool_a = read_jsonl(agent_a_dir / "pool-judgments.agent-a.jsonl")
    pool_b = read_jsonl(agent_b_dir / "pool-judgments.agent-b.jsonl")
    pool = read_jsonl(pool_path)
    chapter = chapter_path.read_text(encoding="utf-8")
    kps = _kpis(kps_a, kps_b, chapter, context, seed, sample_kps)
    edges = _edges(pool_a, pool_b, pool, kps_a, kps_b, chapter, context, seed, sample_pairs)
    diff_available = len(kps["diffs"]) + len(edges["diffs"])
    diff_items = (kps["diffs"] + edges["diffs"])[:max_diff_items]
    items = (diff_items + kps["samples"] + edges["samples"])[:max_items]
    truncated = diff_available - len(diff_items)
    context_chars = sum(
        ((side or {}).get("excerpt") or {}).get("chars", 0)
        for item in items for side in (item.get("a"), item.get("b")))
    est = min(180, 15 + 2 * len(items) + context_chars // 8000)
    pack = {
        "schema": "corpus-pilot-spotcheck-pack/v1",
        "protocol": "v2",
        "seed": seed,
        "context_window_chars": context,
        "chapter_chars": len(chapter),
        "inputs": {
            "agent_a_dir": str(agent_a_dir), "agent_b_dir": str(agent_b_dir),
            "chapter": str(chapter_path), "pool": str(pool_path),
            "shas": {
                "chapter": sha256_file(chapter_path), "pool": sha256_file(pool_path),
                "kps_a": sha256_file(agent_a_dir / "kps.agent-a.jsonl"),
                "kps_b": sha256_file(agent_b_dir / "kps.agent-b.jsonl"),
                "pool_a": sha256_file(agent_a_dir / "pool-judgments.agent-a.jsonl"),
                "pool_b": sha256_file(agent_b_dir / "pool-judgments.agent-b.jsonl"),
            },
        },
        "counts": {
            "diffs": len(diff_items), "diffs_available": diff_available,
            "diffs_truncated": truncated,
            "kp_diffs": sum(1 for i in diff_items if i["kind"] == "kp"),
            "edge_diffs": sum(1 for i in diff_items if i["kind"] == "edge"),
            "samples": len(kps["samples"]) + len(edges["samples"]),
            "kp_samples": len(kps["samples"]), "edge_samples": len(edges["samples"]),
        },
        "kp_stats": kps["stats"], "edge_stats": edges["stats"],
        "context_chars_total": context_chars,
        "est_human_minutes": est,
        "items": items,
        "note": ("人类只看本包，不读 chapter 全文；每项上下文为 ±%d 字符窗口。" % context),
    }
    return pack


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build human spotcheck pack (protocol v2)")
    ap.add_argument("--agent-a-dir", default="artifacts/corpus/pilot/agent-labels/agent-a")
    ap.add_argument("--agent-b-dir", default="artifacts/corpus/pilot/agent-labels/agent-b")
    ap.add_argument("--chapter", default="artifacts/corpus/pilot/source/chapter.txt")
    ap.add_argument("--pool", default="artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    ap.add_argument("--seed", type=int, default=373)
    ap.add_argument("--sample-kps", type=int, default=5)
    ap.add_argument("--sample-pairs", type=int, default=5)
    ap.add_argument("--context-chars", type=int, default=260)
    ap.add_argument("--max-diff-items", type=int, default=MAX_DIFF_ITEMS_DEFAULT)
    ap.add_argument("--max-items", type=int, default=MAX_ITEMS_DEFAULT)
    ap.add_argument("--out", default="artifacts/corpus/pilot/spotcheck/SPOTCHECK-PACK.md")
    ap.add_argument("--json-out", default="artifacts/corpus/pilot/spotcheck/spotcheck-pack.json")
    args = ap.parse_args(argv)
    a_dir, b_dir = Path(args.agent_a_dir), Path(args.agent_b_dir)
    needed = [a_dir / "kps.agent-a.jsonl", a_dir / "pool-judgments.agent-a.jsonl",
              b_dir / "kps.agent-b.jsonl", b_dir / "pool-judgments.agent-b.jsonl",
              Path(args.chapter), Path(args.pool)]
    missing = [str(p) for p in needed if not p.exists()]
    if missing:
        print(json.dumps({"ok": False, "status": "missing_input", "missing": missing,
                          "note": "agent 标签尚未生成；本脚本不生成标签，仅处理已有文件"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    try:
        pack = build(a_dir, b_dir, Path(args.chapter), Path(args.pool), seed=args.seed,
                     sample_kps=args.sample_kps, sample_pairs=args.sample_pairs,
                     context=args.context_chars, max_diff_items=args.max_diff_items,
                     max_items=args.max_items)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "status": "invalid", "error": type(exc).__name__,
                          "message": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_markdown(pack), encoding="utf-8", newline="\n")
    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "out": str(out), "json_out": str(json_out),
                      "counts": pack["counts"], "context_chars_total": pack["context_chars_total"],
                      "chapter_chars": pack["chapter_chars"],
                      "est_human_minutes": pack["est_human_minutes"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
