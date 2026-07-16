"""Download cross-encoder/ms-marco-MiniLM-L-6-v2 (light reranker)."""
import os
import sys

for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
    os.environ.pop(k, None)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

LOG = open("_download_light.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

log(f"Downloading {MODEL} ...")
try:
    from huggingface_hub import snapshot_download
    path = snapshot_download(repo_id=MODEL)
    log(f"OK: {path}")
    for root, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            log(f"  {f} ({os.path.getsize(fp):,} bytes)")
except Exception as e:
    log(f"FAIL: {e}")
    import traceback
    traceback.print_exc(file=LOG)
    LOG.close()
    sys.exit(1)

log("=== DONE ===")
LOG.close()
