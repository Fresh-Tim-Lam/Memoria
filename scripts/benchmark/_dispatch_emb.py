"""Dispatch all 300 queries as separate subprocesses to isolate segfaults.

Each query runs in its own Python process, preventing torch/C-extension
memory corruption from affecting subsequent queries.
"""
import json
import subprocess
import sys
import time
import faulthandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

_DISPATCH_FAULT = open(ROOT / "benchmarks/beir_scifact/_fault_dispatch.log", "w", encoding="utf-8")
faulthandler.enable(file=_DISPATCH_FAULT)

from benchmark.eval import load_queries, load_qrels

q = load_queries(ROOT / "benchmarks/beir_scifact/eval/queries.json")
qr = load_qrels(ROOT / "benchmarks/beir_scifact/eval/qrels.json")

OUT = ROOT / "benchmarks/beir_scifact/results_embedding.jsonl"
# Start fresh
OUT.write_text("", encoding="utf-8")

# Progress log
LOG = open(ROOT / "benchmarks/beir_scifact/_dispatch_emb.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

total = len(q)
ok = 0
failed = 0
skipped = 0
t0 = time.time()

for i, item in enumerate(q):
    qid = item["query_id"]
    text = item["text"]
    if qid not in qr or not qr[qid]:
        skipped += 1
        continue

    elapsed = time.time() - t0
    log(f"[{i}/{total}] qid={qid} (ok={ok} failed={failed} elapsed={elapsed:.0f}s)")
    # Redirect subprocess output to files to avoid pipe buffer deadlocks
    stdout_path = ROOT / f"benchmarks/beir_scifact/_q_{qid}.stdout"
    stderr_path = ROOT / f"benchmarks/beir_scifact/_q_{qid}.stderr"
    try:
        with open(stdout_path, "w", encoding="utf-8") as stdout_fh, \
             open(stderr_path, "w", encoding="utf-8") as stderr_fh:
            result = subprocess.run(
                [sys.executable, "-u", str(ROOT / "scripts/benchmark/_run_one.py"),
                 "--qid", str(qid),
                 "--query", text,
                 "--out", str(OUT)],
                cwd=str(ROOT),
                stdout=stdout_fh,
                stderr=stderr_fh,
                timeout=180,
            )
        if result.returncode == 0:
            ok += 1
        else:
            failed += 1
            try:
                stderr_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-500:]
            except Exception:
                stderr_tail = ""
            log(f"  FAIL rc={result.returncode} stderr: {stderr_tail}")
    except subprocess.TimeoutExpired:
        failed += 1
        log(f"  TIMEOUT (>180s)")
    except Exception as e:
        failed += 1
        log(f"  ERROR: {type(e).__name__}: {e}")

    if (i + 1) % 20 == 0:
        log(f"--- progress: {i+1}/{total} ok={ok} failed={failed} skipped={skipped} elapsed={time.time()-t0:.0f}s ---")

log(f"=== DONE: ok={ok} failed={failed} skipped={skipped} total={total} elapsed={time.time()-t0:.0f}s ===")
LOG.close()
print(f"DONE: ok={ok} failed={failed} skipped={skipped}")

