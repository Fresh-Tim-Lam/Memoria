"""Run P3 Embed-Rerank eval using multiprocessing.Pool.

Same as _pool_emb.py but with rerank_enabled=True.
Uses bge-reranker-v2-m3 cross-encoder to re-rank RRF-fused Top-20.
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

from benchmark.eval import load_queries, load_qrels
from benchmark.metrics import recall_at_k, precision_at_k, noise_at_k, ndcg_at_k, mrr

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold_subset")
Q = load_queries(ROOT / "benchmarks/beir_scifact/eval/queries.json")
QR = load_qrels(ROOT / "benchmarks/beir_scifact/eval/qrels.json")

OUT = ROOT / "benchmarks/beir_scifact/results_rerank.jsonl"
# NOTE: do NOT clear OUT on startup; we resume from existing results

LOG = open(ROOT / "benchmarks/beir_scifact/_pool_rerank.log", "a", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()


def init_worker():
    """Initialize worker: load embed + reranker models once, reuse for all queries."""
    global _search, _kb
    import memoria.services.embedding_provider as ep
    import memoria.services.rerank_provider as rp
    from memoria.services.search_kernel import search
    from memoria.storage import ui_settings
    ui_settings.save_ui_settings({"search": {
        "embedding_enabled": True,
        "allow_model_download": True,
        "body_locate_enabled": False,
        "rerank_enabled": True,
        "rerank_tier": "light",
    }})
    _kb = KB
    _search = search
    # Pre-load embed model
    ep.ensure_embedding_index(_kb)
    ep._load_model(ep.embedding_model_name())
    # Pre-load reranker model
    from memoria.services.model_router import embed_rerank_model
    reranker_name = embed_rerank_model(kb_path=_kb)
    log(f"  reranker model: {reranker_name}")
    if reranker_name:
        rp._load_reranker(reranker_name)
        log(f"  reranker loaded OK")


def run_one(args):
    """Run a single query. If this crashes, Pool replaces the worker."""
    idx, qid, text = args
    try:
        relevant = QR.get(qid, set())
        if not relevant:
            return None
        payload = _search(text, kb_path=_kb, modes="both", limit=20)
        ranked = [r["kp_id"] for r in payload.get("results") or []]
        fusion = payload.get("fusion", "unknown")
        row = {"query_id": qid, "ranked": ranked, "relevant": sorted(relevant), "modes": "both", "fusion": fusion}
        for k in (1, 5, 10):
            row[f"recall@{k}"] = recall_at_k(ranked, relevant, k)
            row[f"precision@{k}"] = precision_at_k(ranked, relevant, k)
            row[f"noise@{k}"] = noise_at_k(ranked, relevant, k)
            row[f"ndcg@{k}"] = ndcg_at_k(ranked, relevant, k)
        row["mrr"] = mrr(ranked, relevant)
        return row
    except Exception as e:
        return {"query_id": qid, "error": f"{type(e).__name__}: {e}"}


def _load_done_qids() -> set[str]:
    """Read existing results to skip already-completed queries."""
    done = set()
    if not OUT.is_file():
        return done
    with open(OUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                done.add(row["query_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _run_batch(tasks, *, query_timeout=180):
    """Run tasks with per-query timeout using apply_async.

    Returns (results_list, timed_out_qids).
    On timeout, terminates the pool and returns partial results.
    """
    out_rows = []
    timed_out = []
    if not tasks:
        return out_rows, timed_out

    pool = multiprocessing.Pool(processes=1, initializer=init_worker)
    try:
        for task in tasks:
            async_res = pool.apply_async(run_one, (task,))
            try:
                row = async_res.get(timeout=query_timeout)
                out_rows.append(row)
            except multiprocessing.TimeoutError:
                qid = task[1]
                timed_out.append(qid)
                log(f"  TIMEOUT qid={qid} (>{query_timeout}s)")
                # Terminate stuck worker, restart for remaining tasks
                pool.terminate()
                pool.join()
                pool = multiprocessing.Pool(processes=1, initializer=init_worker)
    finally:
        pool.terminate()
        pool.join()
    return out_rows, timed_out


def main():
    done_qids = _load_done_qids()
    log(f"Loaded {len(done_qids)} already-completed queries")

    # Filter out completed queries
    pending = [(i, item["query_id"], item["text"]) for i, item in enumerate(Q)
               if item["query_id"] not in done_qids]
    total = len(Q)
    log(f"Starting rerank eval: {len(pending)}/{total} pending (rerank enabled)")

    t0 = time.time()
    ok = len(done_qids)
    failed = 0
    skipped = 0
    timed_out_count = 0

    # Process in chunks; restart pool after each timeout to get fresh worker
    BATCH = 20
    pos = 0
    while pos < len(pending):
        chunk = pending[pos : pos + BATCH]
        rows, timed_out = _run_batch(chunk, query_timeout=180)
        for row in rows:
            if row is None:
                skipped += 1
            elif "error" in row:
                failed += 1
                log(f"  qid={row['query_id']} FAIL: {row['error']}")
            else:
                ok += 1
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        for qid in timed_out:
            failed += 1
            log(f"  qid={qid} TIMEOUT (skipped)")
            timed_out_count += 1
        pos += len(chunk)
        elapsed = time.time() - t0
        log(f"  progress: ok={ok}/{total} failed={failed} skipped={skipped} "
            f"timed_out={timed_out_count} elapsed={elapsed:.0f}s")

    elapsed = time.time() - t0
    log(f"=== DONE: ok={ok} failed={failed} skipped={skipped} "
        f"timed_out={timed_out_count} total={total} elapsed={elapsed:.0f}s ===")
    LOG.close()
    print(f"DONE: ok={ok} failed={failed} skipped={skipped} timed_out={timed_out_count}")


if __name__ == "__main__":
    main()
