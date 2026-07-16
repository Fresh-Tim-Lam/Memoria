"""Test model loading with transformers (bypass sentence_transformers ONNX issue)."""
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = open(ROOT / "benchmarks/beir_scifact/_model_test3.log", "w", encoding="utf-8")
def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()

try:
    log("step1: import torch")
    import torch
    log(f"torch {torch.__version__}, cuda={torch.cuda.is_available()}")

    log("step2: import transformers")
    from transformers import AutoTokenizer, AutoModel
    log("imported")

    model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    log(f"step3: loading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    log("tokenizer loaded")

    log("step4: loading model")
    model = AutoModel.from_pretrained(model_name, local_files_only=True)
    log(f"model loaded: {type(model).__name__}")

    log("step5: encoding test")
    inputs = tokenizer("hello world", return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
    # Mean pooling
    token_embeddings = outputs.last_hidden_state
    attention_mask = inputs["attention_mask"]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    embedding = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
    log(f"encoded: {embedding.shape[1]} dims, first 5: {embedding[0][:5].tolist()}")

    log("DONE")
except Exception as e:
    log(f"EXCEPTION: {type(e).__name__}: {e}")
    traceback.print_exc(file=LOG)
finally:
    LOG.close()
