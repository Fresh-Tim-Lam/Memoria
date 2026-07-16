"""Test rebuild_lexical_index on full 5183 doc KB (aux skipped)."""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

print("import", flush=True)
from memoria.services import lexical_index as li
from memoria.services import search_aux as sa
from memoria.services import lexical_tokenizer as lt

# Skip aux (O(N^2) perf bug)
sa.rebuild_search_aux = lambda kb_path: {"kp_count": 0}
li.rebuild_search_aux = sa.rebuild_search_aux
# Use fallback tokenizer (English SciFact doesn't need jieba; avoids C ext crash)
lt._ensure_jieba = lambda: False
lt._JIEBA_READY = False

KB = str(ROOT / "benchmarks/beir_scifact/kb_gold")
print(f"KB={KB}", flush=True)

print("rebuild_lexical_index start", flush=True)
try:
    index = li.rebuild_lexical_index(KB)
    print(f"records={index['record_count']} tokens={index['token_count']}", flush=True)
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
print("DONE", flush=True)
