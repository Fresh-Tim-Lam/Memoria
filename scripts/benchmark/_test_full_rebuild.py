"""Test rebuild_lexical_index on full 5183-doc KB."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

OUT = open(ROOT / "benchmarks/beir_scifact/_full_rebuild_log.txt", "w", encoding="utf-8")
def log(msg):
    OUT.write(msg + "\n")
    OUT.flush()

log("imports start")
from memoria.services import search_aux as sa
from memoria.services import lexical_index as li
log("imports done")

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold")
log(f"KB={KB}")

# Test: rebuild_lexical_index (includes rebuild_search_aux + tokenize all docs)
log("=== rebuild_lexical_index start ===")
t0 = time.time()
try:
    li.rebuild_lexical_index(KB)
    t1 = time.time()
    log(f"rebuild_lexical_index DONE: {t1-t0:.2f}s")
except Exception as e:
    t1 = time.time()
    log(f"rebuild_lexical_index FAILED after {t1-t0:.2f}s: {type(e).__name__}: {e}")

log("ALL TESTS DONE")
OUT.close()
