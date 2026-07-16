#!/usr/bin/env python3
"""Download BEIR SciFact and build Memoria KB profiles for retrieval benchmark."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.beir_scifact import (  # noqa: E402
    PROFILE_CHOICES,
    build_kb_from_scifact,
    download_scifact,
    export_eval_files,
    load_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "benchmarks" / "beir_scifact",
        help="benchmark root directory",
    )
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=PROFILE_CHOICES,
        default=["gold", "minimal", "skeleton"],
    )
    parser.add_argument(
        "--doc-limit",
        type=int,
        default=None,
        help="limit corpus size (for quick local runs)",
    )
    parser.add_argument(
        "--query-limit",
        type=int,
        default=None,
        help="limit exported eval queries",
    )
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=None,
        help="use existing extracted SciFact directory (skip download)",
    )
    args = parser.parse_args()

    out = args.out
    if args.corpus_root is not None:
        corpus_root = args.corpus_root
        if not (corpus_root / "corpus.jsonl").is_file():
            print("Invalid --corpus-root: missing corpus.jsonl", file=sys.stderr)
            return 1
    else:
        raw_dir = out / "raw"
        corpus_root = raw_dir / "scifact"
        if not args.skip_download or not (corpus_root / "corpus.jsonl").is_file():
            print("Downloading SciFact …")
            corpus_root = download_scifact(raw_dir)
        else:
            print("Using cached SciFact at", corpus_root)

    docs = load_corpus(corpus_root)
    doc_ids = sorted(docs.keys())
    if args.doc_limit:
        doc_ids = doc_ids[: args.doc_limit]
    doc_id_set = set(doc_ids)

    for profile in args.profiles:
        kb_dir = out / f"kb_{profile}"
        n = build_kb_from_scifact(corpus_root, kb_dir, profile, doc_limit=args.doc_limit)
        print(f"Built kb_{profile}: {n} KPs -> {kb_dir}")

    eval_dir = out / "eval"
    nq, nqrel = export_eval_files(
        corpus_root,
        eval_dir,
        query_limit=args.query_limit,
        doc_ids_in_kb=doc_id_set,
    )
    print(f"Exported eval: {nq} queries, {nqrel} with qrels -> {eval_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
