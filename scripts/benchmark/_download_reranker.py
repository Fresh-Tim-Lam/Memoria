"""Download single file: model.safetensors for bge-reranker-v2-m3."""
import os
import sys

for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
    os.environ.pop(k, None)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from huggingface_hub import hf_hub_download

MODEL = "BAAI/bge-reranker-v2-m3"
FILE = "model.safetensors"

print(f"Downloading {MODEL}/{FILE} ...", flush=True)
try:
    path = hf_hub_download(repo_id=MODEL, filename=FILE)
    sz = os.path.getsize(path)
    print(f"OK: {path} ({sz:,} bytes)", flush=True)
except Exception as e:
    print(f"FAIL: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=== DONE ===", flush=True)
