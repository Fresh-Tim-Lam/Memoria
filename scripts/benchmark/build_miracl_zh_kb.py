"""Build MIRACL zh Memoria KB from corpus_subset.jsonl.

Each corpus doc has format: {"_id": "doc_id", "title": "...", "text": "..."}
kp_id = doc_id (kept as-is in qrels).
File name = sequential index to avoid special chars in doc_id (contains #).
Maintains id_map.json: {doc_id: filename} for qrels lookup.
"""
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from memoria.storage.constants import SIDECAR_SCHEMA_VERSION
from memoria.storage.manifest import rebuild_manifest

RAW = ROOT / "benchmarks" / "miracl_zh" / "raw"
OUT = ROOT / "benchmarks" / "miracl_zh"
KB = OUT / "kb_gold"


def build_kb():
    """Build KB from corpus_subset.jsonl; one md per doc, plus sidecars."""
    if KB.exists():
        shutil.rmtree(KB)
    KB.mkdir(parents=True)

    corpus_dir = KB / "corpus"
    corpus_dir.mkdir(parents=True)
    sidecar_dir = KB / ".memoria" / "sidecars" / "corpus"
    sidecar_dir.mkdir(parents=True)

    corpus_jsonl = RAW / "corpus_subset.jsonl"
    if not corpus_jsonl.is_file():
        print(f"ERROR: {corpus_jsonl} not found; run _download_miracl_zh.py first")
        return 0

    id_map: dict[str, str] = {}  # doc_id -> filename (no extension)
    count = 0
    with open(corpus_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = str(row.get("docid") or row.get("_id") or "")
            title = str(row.get("title") or "").strip() or doc_id
            text = str(row.get("text") or "").strip()

            # Use sequential index as filename (doc_id contains #, not filesystem-safe)
            filename = f"doc_{count:05d}"
            id_map[doc_id] = filename
            kp_id = doc_id  # kp_id keeps original doc_id for qrels compatibility

            # Compose md content
            md_content = f"# {title}\n\n{text}\n"
            rel_md = f"corpus/{filename}.md"
            md_path = KB / rel_md
            md_path.write_text(md_content, encoding="utf-8")

            # Compose sidecar
            tags = [w for w in title.split() if w][:5]  # crude tags from title
            if not tags:
                tags = ["miracl_zh"]
            sidecar = {
                "schema_version": SIDECAR_SCHEMA_VERSION,
                "file": rel_md.replace("\\", "/"),
                "knowledge_points": [{
                    "id": kp_id,
                    "name": title[:120],
                    "tags": tags,
                    "description": text[:240].replace("\n", " "),
                    "range": {
                        "start": {"line_hint": 1, "snippet": title},
                        "end": {"line_hint": max(1, md_content.count("\n")), "snippet": text[-120:].strip()},
                    },
                }],
                "links": [],
            }
            sc_path = sidecar_dir / f"{filename}.memoria.yaml"
            with open(sc_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(sidecar, f, allow_unicode=True, sort_keys=False)
            count += 1

    # Save id_map for evaluation script (doc_id -> filename)
    memoria_dir = KB / ".memoria"
    memoria_dir.mkdir(parents=True, exist_ok=True)
    (memoria_dir / "id_map.json").write_text(
        json.dumps(id_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rebuild_manifest(str(KB))
    print(f"Built KB: {count} docs -> {KB}")
    print(f"id_map: {len(id_map)} entries")
    return count


def main():
    print("=== Building MIRACL zh KB ===")
    n = build_kb()
    if n == 0:
        sys.exit(1)
    print("=== DONE ===")


if __name__ == "__main__":
    main()
