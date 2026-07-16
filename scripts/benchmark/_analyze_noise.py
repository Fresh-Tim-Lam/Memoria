"""Analyze per-query results from the fixed benchmark results JSON."""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
p = ROOT / "benchmarks/beir_scifact/results_gold_subset_lexical_fixed.json"
data = json.loads(p.read_text(encoding="utf-8"))
queries = data.get("queries", [])
print(f"Total queries: {len(queries)}")

# Analyze Noise@1 distribution
noise1_dist = Counter()
for q in queries:
    n1 = q.get("noise@1", 1.0)
    if n1 == 0:
        noise1_dist["hit"] += 1
    else:
        noise1_dist["miss"] += 1
print(f"\nNoise@1 distribution: {dict(noise1_dist)}")
hit_count = noise1_dist["hit"]
print(f"  Hit rate (top-1 correct): {hit_count}/{len(queries)} = {hit_count/len(queries):.2%}")

# Analyze Recall@10 distribution
recall10_dist = Counter()
for q in queries:
    r10 = q.get("recall@10", 0.0)
    if r10 == 0:
        recall10_dist["total_miss"] += 1
    elif r10 == 1.0:
        recall10_dist["full_recall"] += 1
    else:
        recall10_dist["partial"] += 1
print(f"\nRecall@10 distribution: {dict(recall10_dist)}")

# Analyze MRR distribution
mrr_buckets = Counter()
for q in queries:
    mrr_val = q.get("mrr", 0.0)
    if mrr_val == 0:
        mrr_buckets["0.0 (not found)"] += 1
    elif mrr_val == 1.0:
        mrr_buckets["1.0 (top-1)"] += 1
    elif mrr_val >= 0.5:
        mrr_buckets["0.5-0.99 (top-2)"] += 1
    elif mrr_val >= 0.33:
        mrr_buckets["0.33-0.5 (top-3)"] += 1
    else:
        mrr_buckets["<0.33 (rank>3)"] += 1
print(f"\nMRR distribution:")
for bucket, count in sorted(mrr_buckets.items()):
    print(f"  {bucket}: {count} ({count/len(queries):.1%})")

# Show 5 worst queries (recall@10 = 0.0)
worst = [q for q in queries if q.get("recall@10", 0.0) == 0.0]
print(f"\nTotal misses (recall@10=0): {len(worst)}")
for q in worst[:5]:
    ranked_top3 = q["ranked"][:3] if q.get("ranked") else []
    print(f"  qid={q['query_id']}: top3={ranked_top3} relevant={q['relevant']}")

# Show 5 best queries
best = [q for q in queries if q.get("recall@1", 0.0) == 1.0]
print(f"\nPerfect top-1 hits: {len(best)}")
for q in best[:3]:
    print(f"  qid={q['query_id']}: top1={q['ranked'][0]} relevant={q['relevant']}")

# Analyze query text length vs performance
print("\n--- Query length vs performance ---")
short_queries = [q for q in queries if len(q.get("ranked", [])) > 0]
if short_queries:
    # Check if queries with longer text perform better
    import json as json_mod
    queries_file = ROOT / "benchmarks/beir_scifact/eval/queries.json"
    all_queries = json_mod.loads(queries_file.read_text(encoding="utf-8"))
    query_text_map = {q["query_id"]: q["text"] for q in all_queries}

    short_text = []
    long_text = []
    for q in queries:
        qid = q["query_id"]
        text = query_text_map.get(qid, "")
        r10 = q.get("recall@10", 0.0)
        if len(text) < 60:
            short_text.append(r10)
        else:
            long_text.append(r10)

    if short_text:
        print(f"Short queries (<60 chars): {len(short_text)} queries, avg recall@10={sum(short_text)/len(short_text):.3f}")
    if long_text:
        print(f"Long queries (>=60 chars): {len(long_text)} queries, avg recall@10={sum(long_text)/len(long_text):.3f}")
