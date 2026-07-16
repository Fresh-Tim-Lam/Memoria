"""Run embedding eval using multiprocessing.Pool to isolate segfaults.

Each query runs in a worker process. If a worker crashes (segfault),
Pool automatically creates a new one. Model is loaded per-worker (cached
in worker's global state).
"""
import sys
import os
# Force CPU + offline to avoid CUDA segfault
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
import json
import time
import traceback
import multiprocessing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# Import before pool creation to cache indices
from benchmark.eval import load_queries, load_qrels
from benchmark.metrics import recall_at_k, precision_at_k, noise_at_k, ndcg_at_k, mrr

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold_subset")
Q = load_queries(ROOT / "benchmarks/beir_scifact/eval/queries.json")
QR = load_qrels(ROOT / "benchmarks/beir_scifact/eval/qrels.json")

OUT = ROOT / "benchmarks/beir_scifact/results_embedding.jsonl"
OUT.write_text("", encoding="utf-8")

LOG = open(ROOT / "benchmarks/beir_scifact/_pool_emb.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()


def init_worker():
    """Initialize worker: load model once, reuse for all queries."""
    global _model, _search, _kb
    import memoria.services.embedding_provider as ep
    from memoria.services.search_kernel import search
    from memoria.storage import ui_settings
    ui_settings.save_ui_settings({"search": {
        "embedding_enabled": True,
        "allow_model_download": True,
        "body_locate_enabled": False,
    }})
    _kb = KB
    _search = search
    # Pre-load model
    ep.ensure_embedding_index(_kb)
    _model = ep._load_model(ep.embedding_model_name())


def run_one(args):
    """Run a single query. If this crashes, Pool replaces the worker."""
    idx, qid, text = args
    try:
        relevant = QR.get(qid, set())
        if not relevant:
            return None
        payload = _search(text, kb_path=_kb, modes="both", limit=20)
        ranked = [r["kp_id"] for r in payload.get("results") or []]
        row = {"query_id": qid, "ranked": ranked, "relevant": sorted(relevant), "modes": "both"}
        for k in (1, 5, 10):
            row[f"recall@{k}"] = recall_at_k(ranked, relevant, k)
            row[f"precision@{k}"] = precision_at_k(ranked, relevant, k)
            row[f"noise@{k}"] = noise_at_k(ranked, relevant, k)
            row[f"ndcg@{k}"] = ndcg_at_k(ranked, relevant, k)
        row["mrr"] = mrr(ranked, relevant)
        return row
    except Exception as e:
        return {"query_id": qid, "error": f"{type(e).__name__}: {e}"}


def main():
    tasks = [(i, item["query_id"], item["text"]) for i, item in enumerate(Q)]
    total = len(tasks)

    log(f"Starting Pool with 1 worker, {total} queries")
    t0 = time.time()
    ok = 0
    failed = 0
    skipped = 0

    # Use 1 worker to avoid concurrent model loading (memory)
    with multiprocessing.Pool(processes=1, initializer=init_worker) as pool:
        results = pool.imap_unordered(run_one, tasks)
        for i, row in enumerate(results):
            if row is None:
                skipped += 1
                continue
            if "error" in row:
                failed += 1
                log(f"  [{i}] qid={row['query_id']} FAIL: {row['error']}")
            else:
                ok += 1
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

            if (i + 1) % 10 == 0:
                elapsed = time.time() - t0
                log(f"  progress: {i+1}/{total} ok={ok} failed={failed} skipped={skipped} elapsed={elapsed:.0f}s")

    elapsed = time.time() - t0
    log(f"=== DONE: ok={ok} failed={failed} skipped={skipped} total={total} elapsed={elapsed:.0f}s ===")
    LOG.close()
    print(f"DONE: ok={ok} failed={failed} skipped={skipped}")


if __name__ == "__main__":
    main()
