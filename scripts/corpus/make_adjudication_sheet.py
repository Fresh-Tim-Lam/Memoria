#!/usr/bin/env python
"""从两位**人类**标注者的文件生成裁决差异表（供裁决人填结论）。

只读人类标注文件（annotator-a / annotator-b），输出 span 边界 / 类型 / 方向 / 存在性差异；
**不读取、不引用 pilot 的机器草案 A 标签**，不生成任何标签，只生成待裁决表格。

输出 Markdown（默认 `artifacts/corpus/pilot/human-kit/coordinator/ADJUDICATION-SHEET.generated.md`）：
- §1 元数据与输入 sha（可复核）
- §2 KP 差异表（boundary/type/unmatched）
- §3 语义边差异表（existence/type/direction/extra）
- §4 裁决统计（供 IAA 报告引用）

退出码：0 = 已生成（有差异也正常）；2 = 输入缺失/无法解析。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iaa_runner  # noqa: E402

KP_DIFF_HEADER = ("| # | kind | 对象 | A（annotator-a） | B（annotator-b） | 差异说明 | "
                  "裁决选项 | 决定 | level | reviewer | date |")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _kp_quote(kp: dict, chapter: str) -> str:
    span = kp["spans"][0]
    quote = chapter[span["start"]:span["end"]].replace("|", "\\|").replace("\n", " ")
    return f"`[{span['start']},{span['end']})` {quote[:70]}"


def kp_diffs(kps_a: list[dict], kps_b: list[dict], chapter: str) -> tuple[list[str], dict]:
    matching = iaa_runner.match_kp_spans(kps_a, kps_b)
    a_by = {k["id"]: k for k in kps_a}
    b_by = {k["id"]: k for k in kps_b}
    rows: list[str] = []
    kinds = {"boundary": 0, "type": 0, "unmatched_a": 0, "unmatched_b": 0}
    for m in matching["pairs"]:
        a, b = a_by[m["gold_id"]], b_by[m["second_id"]]
        a_span, b_span = a["spans"][0], b["spans"][0]
        diffs = []
        if (a_span["start"], a_span["end"]) != (b_span["start"], b_span["end"]):
            diffs.append("span_boundary")
            kinds["boundary"] += 1
        if a.get("concept_type") != b.get("concept_type"):
            diffs.append("concept_type")
            kinds["type"] += 1
        if not diffs:
            continue
        rows.append(
            f"| {len(rows) + 1} | {'+'.join(diffs)} | {m['gold_id']} ↔ {m['second_id']} "
            f"(IoU={m['iou']}) | {_kp_quote(a, chapter)} / type={a.get('concept_type')} | "
            f"{_kp_quote(b, chapter)} / type={b.get('concept_type')} | "
            f"边界/类型不一致（见 kind） | 采 A / 采 B / 折中 / 重切 |  | A/B/C |  |  |")
    for kid in matching["unmatched_gold"]:
        kinds["unmatched_a"] += 1
        rows.append(
            f"| {len(rows) + 1} | unmatched_a | {kid} | {_kp_quote(a_by[kid], chapter)} | — | "
            f"A 有、B 无对应 span | 保留 A / 删除 / 并入匹配项 |  | A/B/C |  |  |")
    for kid in matching["unmatched_second"]:
        kinds["unmatched_b"] += 1
        rows.append(
            f"| {len(rows) + 1} | unmatched_b | {kid} | — | {_kp_quote(b_by[kid], chapter)} | "
            f"B 有、A 无对应 span | 保留 B / 删除 / 并入匹配项 |  | A/B/C |  |  |")
    stats = {
        "a_kp": len(kps_a), "b_kp": len(kps_b),
        "matched": matching["matched_count"],
        "unmatched_a": len(matching["unmatched_gold"]),
        "unmatched_b": len(matching["unmatched_second"]),
        "diffs": kinds,
        "adjudication_rows": len(rows),
    }
    return rows, stats


def edge_diffs(pool_a: list[dict], pool_b: list[dict], pool: list[dict]) -> tuple[list[str], dict]:
    a_by = {r["pair_id"]: r for r in pool_a if r.get("pair_id")}
    b_by = {r["pair_id"]: r for r in pool_b if r.get("pair_id")}
    pool_by = {p["pair_id"]: p for p in pool}
    rows: list[str] = []
    kinds = {"existence": 0, "type": 0, "direction": 0, "missing": 0, "extra": 0}
    for pair_id in sorted(set(pool_by) | set(a_by) | set(b_by)):
        a, b = a_by.get(pair_id), b_by.get(pair_id)
        if pair_id.startswith("extra-") or (a is None and b is None):
            continue
        if a is None or b is None:
            kinds["missing"] += 1
            side = "A" if a is None else "B"
            rows.append(
                f"| {len(rows) + 1} | missing_{side.lower()} | {pair_id} | "
                f"{a.get('label') if a else '—'} | {b.get('label') if b else '—'} | "
                f"{side} 缺该池对判定 | 补标 / 以另一方为准 |  | A/B/C |  |  |")
            continue
        a_edge = a.get("label") == "edge"
        b_edge = b.get("label") == "edge"
        if a_edge != b_edge:
            kinds["existence"] += 1
            rows.append(
                f"| {len(rows) + 1} | existence | {pair_id} | edge | no_edge | "
                f"一方判有边、一方判无边 | 采 A / 采 B / 重看断言 span 后裁 |  | A/B/C |  |  |"
                if a_edge else
                f"| {len(rows) + 1} | existence | {pair_id} | no_edge | edge | "
                f"一方判有边、一方判无边 | 采 A / 采 B / 重看断言 span 后裁 |  | A/B/C |  |  |")
            continue
        if not a_edge:
            continue
        if a.get("type") != b.get("type"):
            kinds["type"] += 1
            rows.append(
                f"| {len(rows) + 1} | edge_type | {pair_id} | {a.get('type')} | {b.get('type')} | "
                f"类型不一致（S0 三类型判据见手册 v1.1 §2） | 采 A / 采 B / 重判类型 |  | A/B/C |  |  |")
        if a.get("direction") != b.get("direction"):
            kinds["direction"] += 1
            rows.append(
                f"| {len(rows) + 1} | edge_direction | {pair_id} | {a.get('direction')} | "
                f"{b.get('direction')} | 方向不一致（反向对记 target->source；both 需双向断言） | "
                f"采 A / 采 B / 重判方向 |  | A/B/C |  |  |")
    for file_rows, side in ((pool_a, "A"), (pool_b, "B")):
        for row in file_rows:
            if str(row.get("pair_id", "")).startswith("extra-"):
                kinds["extra"] += 1
                rows.append(
                    f"| {len(rows) + 1} | extra_{side.lower()} | {row.get('pair_id')} | "
                    f"{row.get('source')}->{row.get('target')} | — | {side} 的池外追加边 | "
                    f"并入 / 拒绝 |  | A/B/C |  |  |")
    stats = {"pool_pairs": len(pool_by), "a_rows": len(pool_a), "b_rows": len(pool_b),
             "diffs": kinds, "adjudication_rows": len(rows)}
    return rows, stats


def build(kps_a_path: Path, kps_b_path: Path, pool_a_path: Path, pool_b_path: Path,
          pool_path: Path, chapter_path: Path) -> dict:
    kps_a, kps_b = read_jsonl(kps_a_path), read_jsonl(kps_b_path)
    pool_a, pool_b = read_jsonl(pool_a_path), read_jsonl(pool_b_path)
    pool = read_jsonl(pool_path)
    chapter = chapter_path.read_text(encoding="utf-8")
    kp_rows, kp_stats = kp_diffs(kps_a, kps_b, chapter)
    edge_rows, edge_stats = edge_diffs(pool_a, pool_b, pool)
    lines = [
        "# ADJUDICATION-SHEET（由机器生成；待裁决人填写“决定/level/reviewer/date”）",
        "",
        "> 本表只读**两位人类标注者**的文件；不读取、不引用 pilot 机器草案标签；不生成任何标签。",
        "> 规则：手册 v1.1 §2（S0 三类型/方向）与 §4（A/B/C 裁决）；改判后需更新 IAA 报告。",
        "",
        "## 1. 输入（sha256 可复核）",
        "",
        "| 文件 | sha256 |",
        "|---|---|",
        f"| `{kps_a_path}` | `{sha256_file(kps_a_path)}` |",
        f"| `{kps_b_path}` | `{sha256_file(kps_b_path)}` |",
        f"| `{pool_a_path}` | `{sha256_file(pool_a_path)}` |",
        f"| `{pool_b_path}` | `{sha256_file(pool_b_path)}` |",
        f"| `{pool_path}`（候选池） | `{sha256_file(pool_path)}` |",
        "",
        "## 2. KP 差异（span 边界 / concept_type / 存在性）",
        "",
        KP_DIFF_HEADER,
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *(kp_rows or ["| — | — | 无差异 | — | — | — | — | — | — | — | — |"]),
        "",
        f"- 统计：{json.dumps(kp_stats, ensure_ascii=False)}",
        "",
        "## 3. 语义边差异（存在性 / 类型 / 方向 / 池外追加）",
        "",
        KP_DIFF_HEADER,
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *(edge_rows or ["| — | — | 无差异 | — | — | — | — | — | — | — | — |"]),
        "",
        f"- 统计：{json.dumps(edge_stats, ensure_ascii=False)}",
        "",
        "## 4. 裁决结论汇总（人工填写）",
        "",
        "| 裁决总条数 | 采 A | 采 B | 折中/重判 | C 级 | 裁决一致率 |",
        "|---|---|---|---|---|---|",
        "|  |  |  |  |  |  |",
        "",
        "> 裁决一致率 = 双方独立判断经复核确认（不变）的比例；目标 ≥0.80（C8）。",
        "",
    ]
    return {"markdown": "\n".join(lines),
            "kp_stats": kp_stats, "edge_stats": edge_stats,
            "inputs_sha256": {
                "kps_a": sha256_file(kps_a_path), "kps_b": sha256_file(kps_b_path),
                "pool_a": sha256_file(pool_a_path), "pool_b": sha256_file(pool_b_path),
                "pool": sha256_file(pool_path)}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate human adjudication diff sheet")
    ap.add_argument("--kps-a", default="artifacts/corpus/pilot/human-kit/annotator-a/kps.annotator-a.jsonl")
    ap.add_argument("--kps-b", default="artifacts/corpus/pilot/human-kit/annotator-b/kps.annotator-b.jsonl")
    ap.add_argument("--pool-a",
                    default="artifacts/corpus/pilot/human-kit/annotator-a/pool-judgments.annotator-a.jsonl")
    ap.add_argument("--pool-b",
                    default="artifacts/corpus/pilot/human-kit/annotator-b/pool-judgments.annotator-b.jsonl")
    ap.add_argument("--pool", default="artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    ap.add_argument("--chapter", default="artifacts/corpus/pilot/source/chapter.txt")
    ap.add_argument("--out",
                    default="artifacts/corpus/pilot/human-kit/coordinator/ADJUDICATION-SHEET.generated.md")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args(argv)
    paths = [Path(args.kps_a), Path(args.kps_b), Path(args.pool_a), Path(args.pool_b),
             Path(args.pool), Path(args.chapter)]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(json.dumps({"ok": False, "status": "missing_input", "missing": missing},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    try:
        result = build(*paths)
    except Exception as exc:  # noqa: BLE001 —— 解析失败必须红
        print(json.dumps({"ok": False, "status": "invalid", "error": type(exc).__name__,
                          "message": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result["markdown"], encoding="utf-8", newline="\n")
    summary = {"ok": True, "out": str(out), "kp_stats": result["kp_stats"],
               "edge_stats": result["edge_stats"]}
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({**summary, "inputs_sha256": result["inputs_sha256"]},
                       ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
