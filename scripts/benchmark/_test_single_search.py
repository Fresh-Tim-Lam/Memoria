"""Minimal test: single search call."""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

print("import", flush=True)
from memoria.services.search_kernel import search
from memoria.services import lexical_index as li
from memoria.services import search_aux as sa

sa.rebuild_search_aux = lambda kb_path: {"kp_count": 0}
li.rebuild_search_aux = sa.rebuild_search_aux

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold_small")
print("rebuild_index", flush=True)
li.rebuild_lexical_index(KB)
print("rebuild done", flush=True)

print("single search", flush=True)
try:
    r = search("GATA-3 is important for hematopoietic stem cell function", kb_path=KB, modes="lexical", limit=20)
    print(f"  results={len(r.get('results') or [])}", flush=True)
    print(f"  top3={[x.get('kp_id') for x in (r.get('results') or [])[:3]]}", flush=True)
except Exception as e:
    print(f"  EXCEPTION: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
print("DONE", flush=True)
