#!/usr/bin/env python3
"""Run Memoria SearchKernel retrieval benchmark and print JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.eval import evaluate_retrieval, load_qrels, load_queries  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", type=Path, required=True, help="Memoria KB root")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--modes", default="lexical", choices=["lexical", "semantic", "both"])
    parser.add_argument("--k", nargs="+", type=int, default=[1, 5, 10])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--no-rebuild", action="store_true")
    parser.add_argument("--out", type=Path, default=None, help="write full JSON report")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    qrels = load_qrels(args.qrels)
    report = evaluate_retrieval(
        kb_path=str(args.kb),
        queries=queries,
        qrels=qrels,
        k_values=tuple(sorted(set(args.k))),
        modes=args.modes,
        limit=args.limit,
        rebuild_index=not args.no_rebuild,
    )

    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    if args.out:
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
