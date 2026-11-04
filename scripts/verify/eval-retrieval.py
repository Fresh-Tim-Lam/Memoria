#!/usr/bin/env python
"""S9 GATE-RET 可执行评估（S9-10 / S9a；B6 task-353）。

用法::

    python scripts/verify/eval-retrieval.py --kb docs/example/AAA_Vocab \
        --golden docs/design/multilevel-graph/golden/S9-golden-set.json \
        --out artifacts/agent/verify/graph/retrieval/run.json

    # 用当前 KB 的 edition 重建 golden（仅 fixture KB；canonical 真实库 golden 由 B6.2 校准生成）
    python scripts/verify/eval-retrieval.py --write-golden --kb tests/graph/fixtures/kb-mini

退出码：0 = GATE-RET 全 PASS（含 2× 确定性）；1 = 门禁失败/执行失败；2 = 用法错误。
阈值是 **provisional**（S9-10/R8）：未校准前 soft，但脚本仍按阈值 exit 0/1 以形成回归基线。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memoria.graph.retrieval.eval import (  # noqa: E402
    GATE_RET,
    evaluate,
    evaluate_isolated,
    golden_path,
    load_golden,
    write_golden,
)
from memoria.graph.retrieval.index import canonical_bytes, sha256_canonical  # noqa: E402

DEFAULT_KB = REPO / "docs" / "example" / "AAA_Vocab"
DEFAULT_OUT = REPO / "artifacts" / "agent" / "verify" / "graph" / "retrieval"


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S9 GATE-RET retrieval evaluation")
    ap.add_argument("--kb", default=str(DEFAULT_KB), help="KB 根目录（含 .memoria/）")
    ap.add_argument("--golden", default="", help="golden JSON（默认冻结唯一路径）")
    ap.add_argument("--out", default="", help="metrics 输出路径（默认 artifacts/.../<run>.json）")
    ap.add_argument("--in-place", action="store_true",
                    help="不复制 KB（会在 KB/.memoria/cache 写派生索引）")
    ap.add_argument("--write-golden", action="store_true",
                    help="用当前 KB edition 重建 golden（唯一路径）")
    args = ap.parse_args(argv)

    kb = Path(args.kb)
    if not kb.is_dir():
        _emit({"ok": False, "error": "usage", "message": f"KB 不存在：{kb}"})
        return 2
    try:
        if args.write_golden:
            if kb.name != "kb-mini":
                _emit({"ok": False, "error": "usage",
                       "message": "--write-golden 仅用于 fixture KB（kb-mini）；真实库 golden 由 B6.2 校准生成，防止覆盖 canonical"})
                return 2
            res = write_golden(kb)
            _emit({"ok": True, "write_golden": res})
            return 0
        golden = load_golden(args.golden or None)
        out = Path(args.out) if args.out else (
            DEFAULT_OUT / f"gate-ret-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json")
        report = evaluate(kb, golden) if args.in_place else evaluate_isolated(kb, golden)
        payload = {
            "ok": report.ok,
            "gate": "GATE-RET",
            "provisional": True,
            "thresholds": dict(GATE_RET),
            "metrics": report.metrics,
            "gates": report.gates,
            "type_breakdown": report.detail["type_breakdown"],
            "type_gates": report.detail["type_gates"],
            "applicable_types": report.detail["applicable_types"],
            "not_applicable_types": report.detail["not_applicable_types"],
            "has_semantic_edges": report.detail["has_semantic_edges"],
            "all_queries_metrics": report.detail["all_queries_metrics"],
            "metrics_sha": report.detail["metrics_sha"],
            "golden_sha256": report.detail["golden_sha256"],
            "golden_edition": report.detail["golden_edition"],
            "determinism": report.detail["determinism"],
            "per_query": report.detail["per_query"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        payload["output"] = str(out)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        payload["output_sha256"] = sha256_canonical(payload)
        _emit(payload)
        return 0 if report.ok else 1
    except Exception as exc:  # noqa: BLE001 —— 门禁必须可见失败
        _emit({"ok": False, "gate": "GATE-RET", "error": type(exc).__name__,
               "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
