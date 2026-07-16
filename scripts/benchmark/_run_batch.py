"""Batch runner for lexical benchmark evaluation.

Processes a range of queries and writes results to a batch-specific JSONL file.
Can be called multiple times for different ranges. If a batch crashes,
only that batch's data is lost.

Usage:
    python scripts/benchmark/_run_batch.py --start 0 --count 30
    python scripts/benchmark/_run_batch.py --start 30 --count 30
    ...
"""
import sys
import json
import argparse
import traceback
import faulthandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# Parse args before heavy imports
parser = argparse.ArgumentParser()
parser.add_argument("--start", type=int, default=0, help="Start index in queries list")
parser.add_argument("--count", type=int, default=30, help="Number of queries to process")
parser.add_argument("--batch-id", type=str, default=None, help="Batch ID for output file")
args = parser.parse_args()

BATCH_ID = args.batch_id or f"batch_{args.start:04d}"

# Enable faulthandler to dump traceback on segfault
_FAULT_LOG = open(ROOT / f"benchmarks/beir_scifact/_fault_{BATCH_ID}.log", "w", encoding="utf-8")
faulthandler.enable(file=_FAULT_LOG)

LOG = open(ROOT / f"benchmarks/beir_scifact/_batch_{BATCH_ID}.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

log(f"batch={BATCH_ID} start={args.start} count={args.count}")

from benchmark.eval import load_qrels, load_queries
from benchmark.metrics import recall_at_k, precision_at_k, noise_at_k, ndcg_at_k, mrr
from memoria.services.search_kernel import search
from memoria.services import lexical_index as li
from memoria.services import search_aux as sa
import memoria.services.suggest_metadata as sm

# Disable jieba/pypinyin for English-only SciFact to avoid C extension memory issues.
import memoria.services.lexical_tokenizer as lt
lt._ensure_jieba = lambda: False
lt.pinyin_tokens = lambda text: []
lt.pinyin_compact = lambda text: ""

# Patch all modules that did `from lexical_tokenizer import tokenize/pinyin_compact`
# These modules have their own local reference that won't see the module-level patch
li.pinyin_compact = lambda text: ""
li.tokenize = lt.tokenize
sa.tokenize = lt.tokenize
sm.tokenize = lt.tokenize

log("imports done (jieba/pypinyin disabled)")

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold_subset")

# Only rebuild index for the first batch
if args.start == 0:
    log("rebuild_index (first batch)")
    li.rebuild_lexical_index(KB)
    log("rebuild done")
else:
    log("ensuring index exists")
    li.ensure_lexical_index(KB)
    log("index ready")

q = load_queries(ROOT / "benchmarks/beir_scifact/eval/queries.json")
qr = load_qrels(ROOT / "benchmarks/beir_scifact/eval/qrels.json")
log(f"total queries={len(q)} qrels={len(qr)}")

# Select batch
end = min(args.start + args.count, len(q))
batch = q[args.start:end]
log(f"batch range: [{args.start}, {end}), batch size={len(batch)}")

k_values = (1, 5, 10)
jsonl_path = ROOT / f"benchmarks/beir_scifact/_batch_{BATCH_ID}.jsonl"
jsonl_fh = open(jsonl_path, "w", encoding="utf-8")

evaluated = 0
skipped = 0
crashed = 0

for idx, item in enumerate(batch):
    global_idx = args.start + idx
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
        log(f"  [{global_idx}] qid={qid} EXCEPTION: {type(e).__name__}: {e}")
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

jsonl_fh.close()
log(f"batch done: evaluated={evaluated}, skipped={skipped}, crashed={crashed}")
LOG.close()

print(f"BATCH={BATCH_ID} evaluated={evaluated} skipped={skipped} crashed={crashed}")
