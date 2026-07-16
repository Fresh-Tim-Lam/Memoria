"""Aggregate partial rerank results for MIRACL zh (60/393 queries)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.metrics import aggregate_metric

SRC = ROOT / "benchmarks" / "miracl_zh" / "results_rerank.jsonl"
OUT = ROOT / "benchmarks" / "miracl_zh" / "results_rerank_summary.json"

k_values = (1, 5, 10)
recalls = {k: [] for k in k_values}
precisions = {k: [] for k in k_values}
noises = {k: [] for k in k_values}
ndcgs = {k: [] for k in k_values}
mrrs = []
rows = []

seen_qids = set()
with open(SRC, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in row:
            continue
        qid = row["query_id"]
        if qid in seen_qids:
            continue
        seen_qids.add(qid)
        for k in k_values:
            recalls[k].append(row[f"recall@{k}"])
            precisions[k].append(row[f"precision@{k}"])
            noises[k].append(row[f"noise@{k}"])
            ndcgs[k].append(row[f"ndcg@{k}"])
        mrrs.append(row["mrr"])
        rows.append(row)

count = len(mrrs)
summary = {"mode": "rerank", "query_count": count, "mrr": aggregate_metric(mrrs)}
for k in k_values:
    summary[f"recall@{k}"] = aggregate_metric(recalls[k])
    summary[f"precision@{k}"] = aggregate_metric(precisions[k])
    summary[f"noise@{k}"] = aggregate_metric(noises[k])
    summary[f"ndcg@{k}"] = aggregate_metric(ndcgs[k])

OUT.write_text(
    json.dumps({"summary": summary, "queries": rows}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"--- rerank Summary ({count} queries, PARTIAL) ---")
for k, v in summary.items():
    if k in ("mode", "query_count"):
        continue
    val = round(v["mean"], 4) if isinstance(v, dict) else round(v, 4)
    print(f"  {k}={val}")
