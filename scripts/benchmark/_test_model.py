"""Quick test: load embedding model and encode one sentence."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = open(ROOT / "benchmarks/beir_scifact/_model_test.log", "w", encoding="utf-8")

def log(msg):
    OUT.write(msg + "\n")
    OUT.flush()

log("importing sentence_transformers")
from sentence_transformers import SentenceTransformer
log("imported ok")

log("loading model with local_files_only=True")
m = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", local_files_only=True)
log(f"loaded: {type(m).__name__}")

log("encoding test sentence")
v = m.encode(["hello world"], normalize_embeddings=True)
log(f"encoded: {len(v[0])} dims, first 5: {v[0][:5]}")

log("DONE")
OUT.close()
