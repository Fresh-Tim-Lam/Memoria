#!/usr/bin/env python
"""Protocol v2 的 IAA/一致性报告生成器（agent bulk + 人类裁决/抽检）。

两种模式（必须显式声明，防止把 agent 数值冒充人类 IAA）：
- `--mode agent_bulk_human_adjudication`：两个独立 agent 标注 + 人类只裁决分歧/抽检；
  报告拆分 `agent_vs_agent`（agent 间一致性，advisory）与
  `human_adjudication_agreement`（人类接受/改判比例，**不是 human IAA**）；
  要求 adjudication-log 非空（否则 exit 2）。
- `--mode pure_agent`：不找人类；报告强制 `human_unvalidated=true`、`not_c8_conclusion=true`，
  **绝不出现 `human_iaa=true`**（0.5 不解禁）。

本脚本只读已有 agent 标签/人类裁决日志，**不生成任何标签**、不伪造 IAA。

退出码：0 = 报告已生成；1 = 标注来源/模式违规（如把 human 标签当 agent）；2 = 输入缺失/为空。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iaa_runner  # noqa: E402

MODES = ("agent_bulk_human_adjudication", "pure_agent")
HUMAN_MARKERS = ("human", "annotator-", "corpus-pilot-builder")
ROLE_AGENT = {"a": "agent-a", "b": "agent-b"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assert_agent(rows: list[dict], expected: str, label: str) -> list[str]:
    errors: list[str] = []
    for i, row in enumerate(rows, 1):
        annotator = str(row.get("annotator", ""))
        method = str(row.get("annotation_method", ""))
        blob = f"{annotator} {method} {row.get('annotator_type', '')}".lower()
        if annotator != expected:
            errors.append(f"{label} 第 {i} 行 annotator={annotator!r}，应为 {expected!r}")
        if any(marker in blob for marker in HUMAN_MARKERS):
            errors.append(f"{label} 第 {i} 行含 human/machine 标记（{annotator!r}/{method!r}），拒绝")
        if "status" in row and row.get("status") != "agent_annotator_draft":
            errors.append(f"{label} 第 {i} 行 status={row.get('status')!r} 应为 agent_annotator_draft")
    return errors


def _choice(decision: object) -> str:
    s = str(decision or "").strip().lower()
    if s in ("a", "采a", "采 a", "accept a", "接受a", "接受 a"):
        return "A"
    if s in ("b", "采b", "采 b", "accept b", "接受b", "接受 b"):
        return "B"
    if s:
        if s.startswith("重判") or "other" in s or "无法" in s or "折中" in s:
            return "other"
        return "unknown"
    return ""


def adjudication_agreement(rows: list[dict], pack_item_ids: set[str] | None) -> dict:
    judged = [r for r in rows if _choice(r.get("decision"))]
    unjudged = [r for r in rows if not _choice(r.get("decision"))]
    accepted_a = accepted_b = overturned = unknown = 0
    for row in judged:
        c = _choice(row.get("decision"))
        if c == "A":
            accepted_a += 1
        elif c == "B":
            accepted_b += 1
        elif c == "other":
            overturned += 1
        else:
            unknown += 1
    accepted = accepted_a + accepted_b
    total = len(judged)
    by_type: dict[str, dict] = {}
    for row in judged:
        t = str(row.get("item_type") or "unknown")
        bucket = by_type.setdefault(t, {"n": 0, "accepted": 0, "other": 0})
        bucket["n"] += 1
        c = _choice(row.get("decision"))
        if c in ("A", "B"):
            bucket["accepted"] += 1
        else:
            bucket["other"] += 1
    for bucket in by_type.values():
        bucket["agreement"] = round(bucket["accepted"] / bucket["n"], 6) if bucket["n"] else None
    expected = sorted(pack_item_ids) if pack_item_ids else []
    judged_ids = {r.get("item_id") for r in judged}
    missing = [i for i in expected if i not in judged_ids]
    return {
        "n_judged": total,
        "n_expected": len(expected) if expected else None,
        "n_missing": len(missing) if expected else None,
        "missing_item_ids": missing[:20],
        "unjudged_rows": len(unjudged),
        "accepted_a": accepted_a,
        "accepted_b": accepted_b,
        "overturned": overturned,
        "unknown": unknown,
        "human_adjudication_agreement": round(accepted / total, 6) if total else None,
        "by_item_type": by_type,
        "note": ("人类接受某一 agent 判断的比例；这是**人类裁决一致率**，不是人类双标 IAA，"
                 "不得写成 human_iaa。"),
    }


def build(mode: str, agent_a_dir: Path, agent_b_dir: Path, pool_path: Path,
          sections_path: Path, adjudications_path: Path | None,
          spotcheck_json: Path | None) -> dict:
    kps_a = read_jsonl(agent_a_dir / "kps.agent-a.jsonl")
    kps_b = read_jsonl(agent_b_dir / "kps.agent-b.jsonl")
    pool_a = read_jsonl(agent_a_dir / "pool-judgments.agent-a.jsonl")
    pool_b = read_jsonl(agent_b_dir / "pool-judgments.agent-b.jsonl")
    pool = read_jsonl(pool_path)
    sections = json.loads(sections_path.read_text(encoding="utf-8"))["sections"]
    empty = [name for name, rows in (("agent-a/kps", kps_a), ("agent-b/kps", kps_b),
                                     ("agent-a/pool", pool_a), ("agent-b/pool", pool_b)) if not rows]
    if empty:
        raise ValueError(f"agent 标签为空: {empty}（不生成报告）")
    errors = (assert_agent(kps_a, ROLE_AGENT["a"], "agent-a/kps")
              + assert_agent(pool_a, ROLE_AGENT["a"], "agent-a/pool")
              + assert_agent(kps_b, ROLE_AGENT["b"], "agent-b/kps")
              + assert_agent(pool_b, ROLE_AGENT["b"], "agent-b/pool"))
    if errors:
        raise PermissionError("; ".join(errors[:20]))
    base = iaa_runner.build_report(kps_a, kps_b, pool_a, pool_b, pool, None, sections)
    agent_vs_agent = {
        "kp_span_unitizing_alpha": base["kp_span_unitizing_alpha"],
        "kp_span_matching": base["kp_span_matching"],
        "kp_type_cohen_kappa": base["kp_type_cohen_kappa"],
        "kp_type_raw_agreement": base["kp_type_raw_agreement"],
        "edge_tuple_f1": base["edge_tuple_f1"],
        "edge_pool_agreement_kappa": base["edge_pool_agreement_kappa"],
        "edge_pool_agreement_kappa_undirected": base["edge_pool_agreement_kappa_undirected"],
        "edge_pool_direction_reversals": base["edge_pool_direction_reversals"],
        "edge_pool_missing_judgments": base["edge_pool_missing_judgments"],
        "pass": base["pass"],
        "sample_sizes": base["sample_sizes"],
        "note": "agent 间一致性；advisory，不是人类 IAA，不能单独作为 C8 证据。",
    }
    adjudication = None
    complete: bool | None = None
    if mode == "agent_bulk_human_adjudication":
        if adjudications_path is None or not adjudications_path.exists():
            raise FileNotFoundError("agent_bulk_human_adjudication 模式需要人类 adjudication-log")
        rows = [r for r in read_jsonl(adjudications_path) if not r.get("_template")]
        if not rows:
            raise ValueError("adjudication-log 为空（人类尚未裁决）")
        pack_ids = None
        if spotcheck_json is not None and spotcheck_json.exists():
            pack = json.loads(spotcheck_json.read_text(encoding="utf-8"))
            pack_ids = {i["item_id"] for i in pack.get("items", [])}
        adjudication = adjudication_agreement(rows, pack_ids)
        complete = (adjudication["n_missing"] == 0) if adjudication["n_expected"] else None
    report = {
        "schema": "corpus-pilot-iaa-report/v2",
        "mode": mode,
        "annotator_type": "agent",
        "human_iaa": False,
        "human_adjudication": mode == "agent_bulk_human_adjudication",
        "human_unvalidated": (mode == "pure_agent") or (complete is False),
        "not_c8_conclusion": True,
        "human_adjudication_complete": complete,
        "agent_vs_agent": agent_vs_agent,
        "human_adjudication_agreement": adjudication,
        "provenance": {
            "inputs": {
                "kps_a": {"path": str(agent_a_dir / "kps.agent-a.jsonl"),
                          "sha256": sha256_file(agent_a_dir / "kps.agent-a.jsonl")},
                "kps_b": {"path": str(agent_b_dir / "kps.agent-b.jsonl"),
                          "sha256": sha256_file(agent_b_dir / "kps.agent-b.jsonl")},
                "pool_a": {"path": str(agent_a_dir / "pool-judgments.agent-a.jsonl"),
                           "sha256": sha256_file(agent_a_dir / "pool-judgments.agent-a.jsonl")},
                "pool_b": {"path": str(agent_b_dir / "pool-judgments.agent-b.jsonl"),
                           "sha256": sha256_file(agent_b_dir / "pool-judgments.agent-b.jsonl")},
                "pool": {"path": str(pool_path), "sha256": sha256_file(pool_path)},
            },
            "adjudications": ({"path": str(adjudications_path),
                               "sha256": sha256_file(adjudications_path)}
                              if adjudication is not None and adjudications_path else None),
            "note": ("agent bulk 标注；人类只做裁决/抽检。human_iaa 恒为 false；"
                     "pure_agent 时 human_unvalidated=true。不得把本报告标成人类双标 IAA。"),
        },
        "warning": ("NOT a two-human C8 IAA. agent_vs_agent is advisory; "
                    "human_adjudication_agreement is human acceptance rate, not IAA."),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Protocol v2 IAA/adjudication report")
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--agent-a-dir", default="artifacts/corpus/pilot/agent-labels/agent-a")
    ap.add_argument("--agent-b-dir", default="artifacts/corpus/pilot/agent-labels/agent-b")
    ap.add_argument("--pool", default="artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    ap.add_argument("--sections", default="artifacts/corpus/pilot/source/sections.json")
    ap.add_argument("--adjudications", default="artifacts/corpus/pilot/spotcheck/adjudication-log.jsonl")
    ap.add_argument("--spotcheck-json", default="artifacts/corpus/pilot/spotcheck/spotcheck-pack.json")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    a_dir, b_dir = Path(args.agent_a_dir), Path(args.agent_b_dir)
    needed = [a_dir / "kps.agent-a.jsonl", a_dir / "pool-judgments.agent-a.jsonl",
              b_dir / "kps.agent-b.jsonl", b_dir / "pool-judgments.agent-b.jsonl",
              Path(args.pool), Path(args.sections)]
    missing = [str(p) for p in needed if not p.exists()]
    if missing:
        print(json.dumps({"ok": False, "status": "missing_input", "mode": args.mode,
                          "missing": missing,
                          "note": "agent 标签尚未生成；不生成报告（exit 2）"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    adjudications = Path(args.adjudications) if args.adjudications else None
    spotcheck_json = Path(args.spotcheck_json) if args.spotcheck_json else None
    if args.mode == "agent_bulk_human_adjudication" and (
            adjudications is None or not adjudications.exists()):
        print(json.dumps({"ok": False, "status": "missing_human_adjudication",
                          "mode": args.mode,
                          "missing": [str(adjudications) if adjudications else "adjudications"],
                          "note": "bulk 模式需要人类 adjudication-log（exit 2）"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    try:
        report = build(args.mode, a_dir, b_dir, Path(args.pool), Path(args.sections),
                       adjudications, spotcheck_json)
    except PermissionError as exc:
        print(json.dumps({"ok": False, "status": "invalid_annotator_source",
                          "mode": args.mode, "errors": str(exc).split("; ")[:20],
                          "note": "拒绝人类/机器标签混入 agent 报告（exit 1）"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "insufficient_data", "mode": args.mode,
                          "message": str(exc), "note": "缺数据/为空（exit 2）"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    out = Path(args.out or f"artifacts/agent/verify/corpus/pilot/iaa-report-v2-{args.mode}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "out": str(out), "mode": args.mode,
                      "human_iaa": report["human_iaa"],
                      "human_unvalidated": report["human_unvalidated"],
                      "not_c8_conclusion": report["not_c8_conclusion"],
                      "human_adjudication_agreement": (
                          report["human_adjudication_agreement"] or {}).get(
                              "human_adjudication_agreement")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
