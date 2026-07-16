"""Build a qrel-coverage KB subset: all qrel kp_ids + 500 distractors."""
import sys
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark.beir_scifact import write_document, load_corpus
from memoria.storage.manifest import rebuild_manifest

root = ROOT / "benchmarks/beir_scifact"
corpus_root = root / "raw" / "scifact"
kb_dir = root / "kb_gold_subset"

qr = json.loads((root / "eval" / "qrels.json").read_text(encoding="utf-8"))
qrel_ids = set()
for v in qr.values():
    qrel_ids.update(v)
print(f"qrel kp_ids: {len(qrel_ids)}", flush=True)

docs = load_corpus(corpus_root)
all_ids = sorted(docs.keys())
distractor_ids = [i for i in all_ids if i not in qrel_ids][:500]
selected = sorted(qrel_ids | set(distractor_ids))
print(f"selected: {len(selected)} (qrel={len(qrel_ids)} distractor={len(distractor_ids)})", flush=True)

if kb_dir.exists():
    shutil.rmtree(kb_dir)
kb_dir.mkdir(parents=True)

for doc_id in selected:
    write_document(kb_dir, doc_id, docs[doc_id], "gold")

rebuild_manifest(str(kb_dir))
print(f"built kb_gold_subset: {len(selected)} docs", flush=True)
