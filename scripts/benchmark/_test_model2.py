"""Test model loading with full error output."""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = open(ROOT / "benchmarks/beir_scifact/_model_test2.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

try:
    log("step1: import torch")
    import torch
    log(f"torch {torch.__version__}, cuda={torch.cuda.is_available()}")

    log("step2: import sentence_transformers")
    from sentence_transformers import SentenceTransformer
    log("imported")

    log("step3: loading model")
    m = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", local_files_only=True)
    log(f"loaded: {type(m).__name__}")

    log("step4: encoding")
    v = m.encode(["hello world"], normalize_embeddings=True)
    log(f"encoded: {len(v[0])} dims, first 5: {v[0][:5]}")

    log("DONE")
except Exception as e:
    log(f"EXCEPTION: {type(e).__name__}: {e}")
    traceback.print_exc(file=LOG)
finally:
    LOG.close()
