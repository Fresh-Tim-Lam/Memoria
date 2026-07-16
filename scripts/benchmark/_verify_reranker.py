"""Verify bge-reranker-v2-m3 loads and infers in offline mode."""
import os
import sys
import faulthandler

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

# Redirect all output to file to avoid PowerShell stderr issues
LOG_FILE = open("_verify_reranker.log", "w", encoding="utf-8")
def log(msg):
    LOG_FILE.write(msg + "\n")
    LOG_FILE.flush()

faulthandler.enable(file=LOG_FILE)

MODEL = "BAAI/bge-reranker-v2-m3"

log("importing transformers...")
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

torch.set_num_threads(2)

log("loading tokenizer...")
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
log(f"tokenizer OK: {type(tok).__name__}")

log("loading model...")
try:
    model = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
    model.eval()
    log(f"model OK: {type(model).__name__}")
except Exception as e:
    log(f"model FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(file=LOG_FILE)
    LOG_FILE.close()
    sys.exit(1)

log("running test pairs (batch_size=2)...")
texts_a = ["hello world", "machine learning"]
texts_b = ["hi there", "deep learning"]
try:
    inputs = tok(
        texts_a,
        texts_b,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512,
    )
    log(f"  input_ids shape: {inputs['input_ids'].shape}")
    with torch.no_grad():
        out = model(**inputs)
        logits = out.logits.squeeze(-1).float().cpu().tolist()
        if isinstance(logits, float):
            logits = [logits]
    log(f"  logits: {logits}")
    log("=== ALL OK ===")
except Exception as e:
    log(f"  INFERENCE FAIL: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc(file=LOG_FILE)

LOG_FILE.close()
