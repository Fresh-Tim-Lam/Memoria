"""Download MIRACL Chinese dev split: queries, qrels, and qrel-coverage corpus subset.

MIRACL zh has 393 dev queries over 4.9M corpus passages (10 shards).
We only download corpus docs referenced by qrels (qrel-coverage subset),
keeping the KB small enough for CPU benchmark.

Uses hf-mirror.com endpoint (set via HF_ENDPOINT env var) for China access.
"""
import json
import os
import sys
from pathlib import Path

# Use mirror endpoint (must be set before any HF import)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "benchmarks" / "miracl_zh" / "raw"
OUT.mkdir(parents=True, exist_ok=True)


def download_queries_qrels():
    """Download dev queries and qrels from HuggingFace miracl/miracl repo."""
    from huggingface_hub import hf_hub_download
    import shutil

    repo = "miracl/miracl"
    base = "miracl-v1.0-zh"

    files = [
        (f"{base}/topics/topics.miracl-v1.0-zh-dev.tsv", "queries.tsv"),
        (f"{base}/qrels/qrels.miracl-v1.0-zh-dev.tsv", "qrels.tsv"),
    ]

    for remote, local in files:
        local_path = OUT / local
        if local_path.exists():
            print(f"  [skip] {local} already exists")
            continue
        print(f"  downloading {remote} ...")
        p = hf_hub_download(repo_id=repo, filename=remote, repo_type="dataset")
        shutil.copy2(p, local_path)
        print(f"  saved -> {local_path}")


def parse_queries(path: Path) -> dict[str, str]:
    """Parse TSV: qid\\tquery"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                out[parts[0]] = parts[1]
    return out


def parse_qrels(path: Path) -> dict[str, set[str]]:
    """Parse TREC qrels: qid 0 doc_id relevance"""
    out: dict[str, set[str]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 4:
                continue
            qid, _, doc_id, score = parts[0], parts[1], parts[2], int(parts[3])
            if score > 0:
                out.setdefault(qid, set()).add(doc_id)
    return out


def build_corpus_subset(needed_ids: set[str]):
    """Stream MIRACL zh corpus shards and extract only docs in needed_ids."""
    import gzip
    from huggingface_hub import hf_hub_download

    corpus_path = OUT / "corpus_subset.jsonl"
    if corpus_path.exists():
        found = 0
        with open(corpus_path, encoding="utf-8") as f:
            for line in f:
                found += 1
        if found >= len(needed_ids):
            print(f"  [skip] corpus_subset.jsonl already has {found} docs")
            return

    repo = "miracl/miracl-corpus"
    shards = [f"miracl-corpus-v1.0-zh/docs-{i}.jsonl.gz" for i in range(10)]
    print(f"  streaming {len(shards)} shards for {len(needed_ids)} needed docs ...")

    found = 0
    remaining = set(needed_ids)
    with open(corpus_path, "w", encoding="utf-8") as fout:
        for shard_idx, shard_file in enumerate(shards):
            if not remaining:
                break
            print(f"  shard {shard_idx}/10: downloading {shard_file} ...")
            try:
                shard_path = hf_hub_download(
                    repo_id=repo, filename=shard_file, repo_type="dataset"
                )
            except Exception as e:
                print(f"    FAIL shard {shard_idx}: {e}")
                continue
            with gzip.open(shard_path, "rt", encoding="utf-8") as fin:
                for line in fin:
                    if not remaining:
                        break
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # MIRACL corpus uses "docid" field (not "_id")
                    doc_id = str(row.get("docid") or row.get("_id") or "")
                    if doc_id in remaining:
                        fout.write(line)
                        remaining.discard(doc_id)
                        found += 1
                        if found % 50 == 0:
                            print(f"    found {found}/{len(needed_ids)}")

    print(f"  extracted {found} docs -> {corpus_path}")
    if remaining:
        print(f"  WARNING: {len(remaining)} docs not found in corpus")


def main():
    print("=== MIRACL zh download (hf-mirror) ===")
    print(f"  HF_ENDPOINT = {os.environ.get('HF_ENDPOINT', '(default)')}")
    download_queries_qrels()

    queries = parse_queries(OUT / "queries.tsv")
    qrels = parse_qrels(OUT / "qrels.tsv")

    print(f"  queries: {len(queries)}")
    print(f"  qrels: {len(qrels)} queries with relevant docs")

    needed_ids: set[str] = set()
    for docs in qrels.values():
        needed_ids.update(docs)
    print(f"  unique relevant docs: {len(needed_ids)}")

    build_corpus_subset(needed_ids)

    # Export eval files
    eval_dir = ROOT / "benchmarks" / "miracl_zh" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    query_list = [
        {"query_id": qid, "text": queries[qid]}
        for qid in sorted(qrels.keys())
        if qid in queries
    ]
    qrels_out = {qid: sorted(docs) for qid, docs in qrels.items()}

    (eval_dir / "queries.json").write_text(
        json.dumps(query_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (eval_dir / "qrels.json").write_text(
        json.dumps(qrels_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  eval: {len(query_list)} queries -> {eval_dir}")
    print("=== DONE ===")


if __name__ == "__main__":
    main()
