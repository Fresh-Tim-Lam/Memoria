"""Single-query embedding evaluator (run as subprocess to isolate segfaults).

Usage:
    python scripts/benchmark/_run_one.py --qid 1 --query "..." --kb kb_gold_subset
"""
import sys
import os
# Force CPU + offline to avoid CUDA segfault
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import json
import argparse
import traceback
import faulthandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

parser = argparse.ArgumentParser()
parser.add_argument("--qid", required=True)
parser.add_argument("--query", required=True)
parser.add_argument("--kb", default="kb_gold_subset")
parser.add_argument("--out", required=True, help="Output JSONL file (append mode)")
args = parser.parse_args()

_FAULT = open(ROOT / f"benchmarks/beir_scifact/_fault_q{args.qid}.log", "w", encoding="utf-8")
faulthandler.enable(file=_FAULT)

try:
    from memoria.storage import ui_settings
    ui_settings.save_ui_settings({"search": {
        "embedding_enabled": True,
        "allow_model_download": True,
        "body_locate_enabled": False,
    }})

    from memoria.services import lexical_index as li
    from memoria.services import embedding_provider as ep
    from memoria.services.search_kernel import search
    from benchmark.metrics import recall_at_k, precision_at_k, noise_at_k, ndcg_at_k, mrr
    from benchmark.eval import load_qrels

    KB = str(ROOT / "benchmarks/beir_scifact" / args.kb)
    # Ensure indices (cached, no rebuild)
    li.ensure_lexical_index(KB)
    ep.ensure_embedding_index(KB)

    qr = load_qrels(ROOT / "benchmarks/beir_scifact/eval/qrels.json")
    relevant = qr.get(args.qid, set())

    payload = search(args.query, kb_path=KB, modes="both", limit=20)
    ranked = [r["kp_id"] for r in payload.get("results") or []]

    row = {"query_id": args.qid, "ranked": ranked, "relevant": sorted(relevant), "modes": "both"}
    for k in (1, 5, 10):
        row[f"recall@{k}"] = recall_at_k(ranked, relevant, k)
        row[f"precision@{k}"] = precision_at_k(ranked, relevant, k)
        row[f"noise@{k}"] = noise_at_k(ranked, relevant, k)
        row[f"ndcg@{k}"] = ndcg_at_k(ranked, relevant, k)
    row["mrr"] = mrr(ranked, relevant)

    with open(args.out, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"OK qid={args.qid} results={len(ranked)}", file=sys.stderr)
except Exception as e:
    print(f"FAIL qid={args.qid} {type(e).__name__}: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
finally:
    _FAULT.close()
