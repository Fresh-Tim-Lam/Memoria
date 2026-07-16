"""Run gold_subset lexical benchmark with incremental result writing.

Each query's result is appended to a JSONL file. If the process crashes
(C-extension segfault), the JSONL file preserves all completed queries.
A separate aggregation step reads the JSONL and computes final metrics.
"""
import sys
import json
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

LOG = open(ROOT / "benchmarks/beir_scifact/_eval_progress.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

log("imports start")
from benchmark.eval import load_qrels, load_queries
from benchmark.metrics import recall_at_k, precision_at_k, noise_at_k, ndcg_at_k, mrr, aggregate_metric
from memoria.services.search_kernel import search
from memoria.services import lexical_index as li
from memoria.services import search_aux as sa

sa.rebuild_search_aux = lambda kb_path: {"kp_count": 0}
li.rebuild_search_aux = sa.rebuild_search_aux

# Disable C extensions (jieba/pypinyin) to avoid random DLL crashes.
# SciFact is English-only, so fallback regex tokenizer is sufficient.
import memoria.services.lexical_tokenizer as lt
lt._ensure_jieba = lambda: False
lt.pinyin_tokens = lambda text: []
log("jieba/pypinyin disabled (C extension crash workaround)")

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold_subset")
log(f"KB={KB}")

log("rebuild_index")
li.rebuild_lexical_index(KB)
log("rebuild done")

q = load_queries(ROOT / "benchmarks/beir_scifact/eval/queries.json")
qr = load_qrels(ROOT / "benchmarks/beir_scifact/eval/qrels.json")
log(f"queries={len(q)} qrels={len(qr)}")

k_values = (1, 5, 10)

# JSONL file for incremental per-query results
jsonl_path = ROOT / "benchmarks/beir_scifact/_per_query_results.jsonl"
jsonl_path.write_text("", encoding="utf-8")  # clear
jsonl_fh = open(jsonl_path, "a", encoding="utf-8")

log(f"starting loop over {len(q)} queries")

# Test single search before loop
log("test search before loop")
try:
    test_r = search("test query", kb_path=KB, modes="lexical", limit=20)
    log(f"test search ok, results={len(test_r.get('results') or [])}")
except Exception as e:
    log(f"test search EXCEPTION: {type(e).__name__}: {e}")
    traceback.print_exc(file=LOG)
    LOG.flush()

evaluated = 0
skipped = 0
crashed = 0
for i, item in enumerate(q):
    qid = item["query_id"]
    text = item["text"]
    relevant = qr.get(qid, set())
    if not relevant:
        skipped += 1
        continue
    try:
        payload = search(text, kb_path=KB, modes="lexical", limit=20)
        ranked = [r["kp_id"] for r in payload.get("results") or []]
    except Exception as e:
        log(f"  [{i}] qid={qid} EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc(file=LOG)
        LOG.flush()
        crashed += 1
        continue

    row = {"query_id": qid, "ranked": ranked, "relevant": sorted(relevant)}
    for k in k_values:
        row[f"recall@{k}"] = recall_at_k(ranked, relevant, k)
        row[f"precision@{k}"] = precision_at_k(ranked, relevant, k)
        row[f"noise@{k}"] = noise_at_k(ranked, relevant, k)
        row[f"ndcg@{k}"] = ndcg_at_k(ranked, relevant, k)
    row["mrr"] = mrr(ranked, relevant)

    jsonl_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    jsonl_fh.flush()
    evaluated += 1

    if (evaluated % 10) == 0:
        log(f"  progress: evaluated={evaluated}, skipped={skipped}, crashed={crashed}, i={i}, last top1={ranked[0] if ranked else None}")

jsonl_fh.close()
log(f"loop completed: evaluated={evaluated}, skipped={skipped}, crashed={crashed}, total={len(q)}")
log("aggregating")

# Aggregate from JSONL
recalls = {k: [] for k in k_values}
precisions = {k: [] for k in k_values}
noises = {k: [] for k in k_values}
ndcgs = {k: [] for k in k_values}
mrrs = []

with open(jsonl_path, encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        row = json.loads(line)
        for k in k_values:
            recalls[k].append(row[f"recall@{k}"])
            precisions[k].append(row[f"precision@{k}"])
            noises[k].append(row[f"noise@{k}"])
            ndcgs[k].append(row[f"ndcg@{k}"])
        mrrs.append(row["mrr"])

summary = {"kb_path": KB, "modes": "lexical", "query_count": len(mrrs), "mrr": aggregate_metric(mrrs)}
for k in k_values:
    summary[f"recall@{k}"] = aggregate_metric(recalls[k])
    summary[f"precision@{k}"] = aggregate_metric(precisions[k])
    summary[f"noise@{k}"] = aggregate_metric(noises[k])
    summary[f"ndcg@{k}"] = aggregate_metric(ndcgs[k])

out = ROOT / "benchmarks/beir_scifact/results_gold_subset_lexical.json"
out.write_text(json.dumps({"summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"query_count={summary['query_count']}")
for k, v in summary.items():
    if k in ("kb_path", "modes", "query_count"):
        continue
    val = round(v["mean"], 4) if isinstance(v, dict) else round(v, 4)
    log(f"{k}={val}")
log("DONE")
LOG.close()
