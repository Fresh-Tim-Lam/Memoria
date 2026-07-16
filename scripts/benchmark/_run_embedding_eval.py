"""Run benchmark with Embedding (P1 Embed-Recall) enabled.

This tests the full SearchKernel v1.5 multi-model capability:
  P0: Lexical (jieba+pypinyin) + P1: Embed-Recall (bi-encoder) + RRF fusion

Usage:
    python scripts/benchmark/_run_embedding_eval.py --batch-id e0 --start 0 --count 30
"""
import sys
import os
# Force CPU to avoid CUDA segfault on repeated model.encode() calls
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import json
import argparse
import traceback
import faulthandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

parser = argparse.ArgumentParser()
parser.add_argument("--start", type=int, default=0)
parser.add_argument("--count", type=int, default=30)
parser.add_argument("--batch-id", type=str, default=None)
parser.add_argument("--kb", type=str, default="kb_gold_subset",
                    choices=["kb_gold_subset", "kb_gold"])
args = parser.parse_args()

BATCH_ID = args.batch_id or f"emb_{args.start:04d}"

_FAULT_LOG = open(ROOT / f"benchmarks/beir_scifact/_fault_{BATCH_ID}.log", "w", encoding="utf-8")
faulthandler.enable(file=_FAULT_LOG)

LOG = open(ROOT / f"benchmarks/beir_scifact/_batch_{BATCH_ID}.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

log("imports start")
from benchmark.eval import load_qrels, load_queries
from benchmark.metrics import recall_at_k, precision_at_k, noise_at_k, ndcg_at_k, mrr
from memoria.services.search_kernel import search
from memoria.services import lexical_index as li
from memoria.services import search_aux as sa
from memoria.services import embedding_provider as ep
from memoria.storage import ui_settings
log("imports done")

# Enable Embedding (P1 Embed-Recall) in UI settings
# Disable body_locate (C extension crashes on benchmark KB)
log("enabling embedding in UI settings")
ui_settings.save_ui_settings({
    "search": {
        "embedding_enabled": True,
        "allow_model_download": True,
        "body_locate_enabled": False,
    }
})
log(f"embedding_enabled={ep.is_embedding_enabled()}")
log(f"embedding_model={ep.embedding_model_name()}")

KB = str(ROOT / "benchmarks/beir_scifact" / args.kb)
log(f"KB={KB}")

# Rebuild lexical index (needed for embedding to get records)
log("rebuild_lexical_index start")
li.rebuild_lexical_index(KB)
log("rebuild_lexical_index done")

# Build embedding index (use ensure to reuse cache if valid)
log("ensure_embedding_index start")
try:
    emb_index = ep.ensure_embedding_index(KB)
    if not emb_index or not emb_index.get("records"):
        log("cache miss, building embedding index...")
        emb_index = ep.build_embedding_index(KB)
    log(f"embedding_index done: records={len(emb_index.get('records') or [])}")
except Exception as e:
    log(f"build_embedding_index FAILED: {type(e).__name__}: {e}")
    traceback.print_exc(file=LOG)
    LOG.flush()

# Load queries and qrels
q = load_queries(ROOT / "benchmarks/beir_scifact/eval/queries.json")
qr = load_qrels(ROOT / "benchmarks/beir_scifact/eval/qrels.json")
log(f"queries={len(q)} qrels={len(qr)}")

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
        # Timeout dump: if search hangs >15s, print stack trace
        faulthandler.dump_traceback_later(15, file=_FAULT_LOG)
        log(f"  [{global_idx}] qid={qid} searching...")
        payload = search(text, kb_path=KB, modes="both", limit=20)
        faulthandler.cancel_dump_traceback_later()
        ranked = [r["kp_id"] for r in payload.get("results") or []]
        log(f"  [{global_idx}] qid={qid} results={len(ranked)}")
    except Exception as e:
        faulthandler.cancel_dump_traceback_later()
        log(f"  [{global_idx}] qid={qid} EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc(file=LOG)
        LOG.flush()
        crashed += 1
        continue

    row = {"query_id": qid, "ranked": ranked, "relevant": sorted(relevant), "modes": "both"}
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
        log(f"  progress: evaluated={evaluated}, skipped={skipped}, crashed={crashed}, i={global_idx}")

jsonl_fh.close()
log(f"batch done: evaluated={evaluated}, skipped={skipped}, crashed={crashed}")
LOG.close()
_FAULT_LOG.close()

print(f"BATCH={BATCH_ID} evaluated={evaluated} skipped={skipped} crashed={crashed}")
