"""Aggregate per-query results from all batch JSONL files into final metrics.

Reads all _batch_*.jsonl files and computes aggregate IR metrics.
"""
import sys
import json
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.metrics import aggregate_metric

batch_files = sorted(glob.glob(str(ROOT / "benchmarks/beir_scifact/_batch_*.jsonl")))
if not batch_files:
    print("No batch files found!")
    sys.exit(1)

print(f"Found {len(batch_files)} batch files:")
for f in batch_files:
    print(f"  {Path(f).name}")

k_values = (1, 5, 10)
recalls = {k: [] for k in k_values}
precisions = {k: [] for k in k_values}
noises = {k: [] for k in k_values}
ndcgs = {k: [] for k in k_values}
mrrs = []
all_rows = []
seen_qids = set()

for batch_file in batch_files:
    with open(batch_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = row["query_id"]
            if qid in seen_qids:
                continue  # deduplicate
            seen_qids.add(qid)
            for k in k_values:
                recalls[k].append(row[f"recall@{k}"])
                precisions[k].append(row[f"precision@{k}"])
                noises[k].append(row[f"noise@{k}"])
                ndcgs[k].append(row[f"ndcg@{k}"])
            mrrs.append(row["mrr"])
            all_rows.append(row)

count = len(mrrs)
summary = {
    "kb_path": str(ROOT / "benchmarks/beir_scifact/kb_gold_subset"),
    "modes": "lexical",
    "query_count": count,
    "mrr": aggregate_metric(mrrs),
}
for k in k_values:
    summary[f"recall@{k}"] = aggregate_metric(recalls[k])
    summary[f"precision@{k}"] = aggregate_metric(precisions[k])
    summary[f"noise@{k}"] = aggregate_metric(noises[k])
    summary[f"ndcg@{k}"] = aggregate_metric(ndcgs[k])

out_path = ROOT / "benchmarks/beir_scifact/results_gold_subset_lexical_fixed.json"
out_path.write_text(json.dumps({"summary": summary, "queries": all_rows}, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"\nAggregated {count} queries from {len(batch_files)} batches")
for k, v in summary.items():
    if k in ("kb_path", "modes", "query_count"):
        continue
    val = round(v["mean"], 4) if isinstance(v, dict) else round(v, 4)
    print(f"  {k}={val}")
