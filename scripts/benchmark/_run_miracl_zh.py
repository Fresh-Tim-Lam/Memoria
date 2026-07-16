"""Run MIRACL zh benchmark: Lexical / Lexical+Embed / Lexical+Embed+Rerank.

Single script that runs all 3 modes sequentially using multiprocessing.Pool
for model isolation. 966 docs (qrel-coverage subset), 393 queries.

Uses per-query timeout in rerank mode to avoid hangs on slow CPU inference.
"""
import sys
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import json
import time
import multiprocessing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.eval import load_queries, load_qrels
from benchmark.metrics import recall_at_k, precision_at_k, noise_at_k, ndcg_at_k, mrr

KB = str(ROOT / "benchmarks" / "miracl_zh" / "kb_gold")
Q = load_queries(ROOT / "benchmarks" / "miracl_zh" / "eval" / "queries.json")
QR = load_qrels(ROOT / "benchmarks" / "miracl_zh" / "eval" / "qrels.json")

OUT_DIR = ROOT / "benchmarks" / "miracl_zh"


def init_worker():
    """Initialize worker: rebuild lexical index."""
    global _search, _kb
    from memoria.services.search_kernel import search
    from memoria.services.lexical_index import rebuild_lexical_index
    _kb = KB
    _search = search
    rebuild_lexical_index(_kb)


def init_worker_embed():
    """Initialize worker with embedding model loaded."""
    global _search, _kb
    import memoria.services.embedding_provider as ep
    from memoria.services.search_kernel import search
    from memoria.services.lexical_index import rebuild_lexical_index
    from memoria.storage import ui_settings
    ui_settings.save_ui_settings({"search": {
        "embedding_enabled": True,
        "allow_model_download": True,
        "body_locate_enabled": False,
        "rerank_enabled": False,
    }})
    _kb = KB
    _search = search
    rebuild_lexical_index(_kb)
    ep.ensure_embedding_index(_kb)
    ep._load_model(ep.embedding_model_name())


def init_worker_rerank():
    """Initialize worker with embedding + reranker models loaded."""
    global _search, _kb
    import memoria.services.embedding_provider as ep
    import memoria.services.rerank_provider as rp
    from memoria.services.search_kernel import search
    from memoria.services.lexical_index import rebuild_lexical_index
    from memoria.storage import ui_settings
    from memoria.services.model_router import embed_rerank_model
    ui_settings.save_ui_settings({"search": {
        "embedding_enabled": True,
        "allow_model_download": True,
        "body_locate_enabled": False,
        "rerank_enabled": True,
        "rerank_tier": "light",
    }})
    _kb = KB
    _search = search
    rebuild_lexical_index(_kb)
    ep.ensure_embedding_index(_kb)
    ep._load_model(ep.embedding_model_name())
    reranker_name = embed_rerank_model(kb_path=_kb)
    if reranker_name:
        rp._load_reranker(reranker_name)


def run_one(args):
    idx, qid, text, modes = args
    try:
        relevant = QR.get(qid, set())
        if not relevant:
            return None
        payload = _search(text, kb_path=_kb, modes=modes, limit=10)
        ranked = [r["kp_id"] for r in payload.get("results") or []]
        fusion = payload.get("fusion", "unknown")
        row = {"query_id": qid, "query": text, "ranked": ranked, "relevant": sorted(relevant), "modes": modes, "fusion": fusion}
        for k in (1, 5, 10):
            row[f"recall@{k}"] = recall_at_k(ranked, relevant, k)
            row[f"precision@{k}"] = precision_at_k(ranked, relevant, k)
            row[f"noise@{k}"] = noise_at_k(ranked, relevant, k)
            row[f"ndcg@{k}"] = ndcg_at_k(ranked, relevant, k)
        row["mrr"] = mrr(ranked, relevant)
        return row
    except Exception as e:
        return {"query_id": qid, "error": f"{type(e).__name__}: {e}"}


def _load_done_qids(out_file: Path) -> set:
    """Read existing results to skip already-completed queries (for resume)."""
    done = set()
    if not out_file.is_file():
        return done
    with open(out_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if "error" not in row:
                    done.add(row["query_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _run_batch_with_timeout(tasks, init_func, query_timeout):
    """Run tasks with per-query timeout using apply_async."""
    out_rows = []
    timed_out = []
    if not tasks:
        return out_rows, timed_out
    pool = multiprocessing.Pool(processes=1, initializer=init_func)
    try:
        for task in tasks:
            async_res = pool.apply_async(run_one, (task,))
            try:
                row = async_res.get(timeout=query_timeout)
                out_rows.append(row)
            except multiprocessing.TimeoutError:
                qid = task[1]
                timed_out.append(qid)
                print(f"  TIMEOUT qid={qid} (>{query_timeout}s)")
                pool.terminate()
                pool.join()
                pool = multiprocessing.Pool(processes=1, initializer=init_func)
    finally:
        pool.terminate()
        pool.join()
    return out_rows, timed_out


def run_mode(mode_name, modes, init_func, use_timeout=False, query_timeout=180):
    """Run a single evaluation mode."""
    out_file = OUT_DIR / f"results_{mode_name}.jsonl"
    # Do NOT clear file; support resume
    if not out_file.is_file():
        out_file.write_text("", encoding="utf-8")

    done_qids = _load_done_qids(out_file)
    pending = [(i, item["query_id"], item["text"], modes)
               for i, item in enumerate(Q) if item["query_id"] not in done_qids]
    total = len(Q)
    print(f"\n=== {mode_name} (modes={modes}, {total} queries, {len(pending)} pending) ===")
    t0 = time.time()
    ok = len(done_qids)
    failed = 0
    skipped = 0
    timed_out_count = 0

    if use_timeout:
        # Rerank mode: per-query timeout
        BATCH = 20
        pos = 0
        while pos < len(pending):
            chunk = pending[pos: pos + BATCH]
            rows, timed_out = _run_batch_with_timeout(chunk, init_func, query_timeout)
            for row in rows:
                if row is None:
                    skipped += 1
                elif "error" in row:
                    failed += 1
                    print(f"  [FAIL] qid={row['query_id']}: {row['error']}")
                else:
                    ok += 1
                    with open(out_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
            for qid in timed_out:
                failed += 1
                timed_out_count += 1
            pos += len(chunk)
            elapsed = time.time() - t0
            print(f"  progress: ok={ok}/{total} failed={failed} skipped={skipped} "
                  f"timed_out={timed_out_count} elapsed={elapsed:.0f}s")
    else:
        # Simple mode: imap_unordered
        with multiprocessing.Pool(processes=1, initializer=init_func) as pool:
            results = pool.imap_unordered(run_one, pending)
            for i, row in enumerate(results):
                if row is None:
                    skipped += 1
                    continue
                if "error" in row:
                    failed += 1
                    print(f"  [FAIL] qid={row['query_id']}: {row['error']}")
                else:
                    ok += 1
                    with open(out_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                if (i + 1) % 50 == 0:
                    elapsed = time.time() - t0
                    print(f"  progress: {i+1}/{len(pending)} ok={ok} failed={failed} skipped={skipped} elapsed={elapsed:.0f}s")

    elapsed = time.time() - t0
    print(f"=== {mode_name} DONE: ok={ok} failed={failed} skipped={skipped} "
          f"timed_out={timed_out_count} elapsed={elapsed:.0f}s ===")

    aggregate_results(mode_name, out_file)
    return ok


def aggregate_results(mode_name, src_file):
    """Aggregate per-query results and print summary."""
    from benchmark.metrics import aggregate_metric

    k_values = (1, 5, 10)
    recalls = {k: [] for k in k_values}
    precisions = {k: [] for k in k_values}
    noises = {k: [] for k in k_values}
    ndcgs = {k: [] for k in k_values}
    mrrs = []
    rows = []

    seen_qids = set()
    with open(src_file, encoding="utf-8") as f:
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
    summary = {"mode": mode_name, "query_count": count, "mrr": aggregate_metric(mrrs)}
    for k in k_values:
        summary[f"recall@{k}"] = aggregate_metric(recalls[k])
        summary[f"precision@{k}"] = aggregate_metric(precisions[k])
        summary[f"noise@{k}"] = aggregate_metric(noises[k])
        summary[f"ndcg@{k}"] = aggregate_metric(ndcgs[k])

    out_path = OUT_DIR / f"results_{mode_name}_summary.json"
    out_path.write_text(
        json.dumps({"summary": summary, "queries": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n--- {mode_name} Summary ({count} queries) ---")
    for k, v in summary.items():
        if k in ("mode", "query_count"):
            continue
        val = round(v["mean"], 4) if isinstance(v, dict) else round(v, 4)
        print(f"  {k}={val}")


def main():
    print(f"KB: {KB}")
    print(f"Queries: {len(Q)}, Qrels: {len(QR)}")

    # Mode 1: Lexical-only
    run_mode("lexical", "lexical", init_worker)

    # Mode 2: Lexical+Embed (RRF)
    run_mode("embed", "both", init_worker_embed)

    # Mode 3: Lexical+Embed+Rerank (with per-query timeout)
    run_mode("rerank", "both", init_worker_rerank, use_timeout=True, query_timeout=180)

    print("\n=== ALL DONE ===")


if __name__ == "__main__":
    main()
