"""BEIR SciFact: download, parse, convert to Memoria KB profiles."""

from __future__ import annotations

import json
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Literal

import yaml

from ._bootstrap import ROOT  # noqa: F401 — ensures src on path
from memoria.storage.constants import SIDECAR_SCHEMA_VERSION
from memoria.storage.manifest import rebuild_manifest

ProfileName = Literal["gold", "minimal", "skeleton"]

SCIFACT_URL = (
    "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip"
)

PROFILE_CHOICES: tuple[ProfileName, ...] = ("gold", "minimal", "skeleton")


def _slug_token(text: str, *, max_len: int = 32) -> str:
    s = re.sub(r"[^\w]+", "-", text.lower()).strip("-")
    return (s[:max_len] or "tag")


def download_scifact(raw_dir: str | Path, *, timeout: int = 120) -> Path:
    """Download and unzip SciFact into *raw_dir*; return corpus root."""
    import ssl
    import urllib.error

    raw = Path(raw_dir)
    raw.mkdir(parents=True, exist_ok=True)
    zip_path = raw / "scifact.zip"
    root = raw / "scifact"
    if (root / "corpus.jsonl").is_file():
        return root
    if not zip_path.is_file():
        ctx = ssl.create_default_context()
        try:
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
        req = urllib.request.Request(SCIFACT_URL, headers={"User-Agent": "memoria-benchmark/1.0"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                zip_path.write_bytes(resp.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "SciFact download failed (network/SSL). Manual steps:\n"
                f"  1. Download {SCIFACT_URL}\n"
                f"  2. Save as {zip_path}\n"
                "  3. Re-run with --skip-download\n"
                "Or pass --corpus-root pointing at extracted scifact/ folder."
            ) from exc
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(raw)
    if not (root / "corpus.jsonl").is_file():
        for candidate in raw.rglob("corpus.jsonl"):
            return candidate.parent
        raise FileNotFoundError("corpus.jsonl not found after unzip")
    return root


def load_corpus(corpus_root: Path) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    with open(corpus_root / "corpus.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            docs[str(row["_id"])] = {
                "title": (row.get("title") or "").strip(),
                "text": (row.get("text") or "").strip(),
                "metadata": row.get("metadata") or {},
            }
    return docs


def load_queries(corpus_root: Path) -> dict[str, str]:
    queries: dict[str, str] = {}
    with open(corpus_root / "queries.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            queries[str(row["_id"])] = (row.get("text") or "").strip()
    return queries


def load_qrels(corpus_root: Path, *, split: str = "test") -> dict[str, dict[str, int]]:
    """query_id -> {doc_id: relevance_score}."""
    path = corpus_root / "qrels" / f"{split}.tsv"
    qrels: dict[str, dict[str, int]] = {}
    with open(path, encoding="utf-8") as f:
        header = f.readline()
        if not header.lower().startswith("query-id"):
            f.seek(0)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 3:
                continue
            qid, doc_id, score = parts[0], parts[1], int(parts[2])
            qrels.setdefault(qid, {})[doc_id] = score
    return qrels


def _lead_sentence(text: str, max_len: int = 240) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def _end_snippet(text: str, max_len: int = 120) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    tail = text[-max_len:]
    if " " in tail:
        tail = tail.split(" ", 1)[1]
    return tail


def _kp_metadata(doc_id: str, doc: dict[str, Any], profile: ProfileName) -> tuple[dict[str, Any], str]:
    title = doc["title"] or doc_id
    text = doc["text"]
    meta: dict[str, Any] = {"id": doc_id}

    if profile == "skeleton":
        meta["name"] = doc_id
    else:
        meta["name"] = title

    if profile == "gold":
        tags = ["scifact", "science"]
        meta_md = doc.get("metadata") or {}
        if isinstance(meta_md, dict):
            for key in ("primary_category", "category", "field"):
                val = meta_md.get(key)
                if val:
                    tags.append(_slug_token(str(val)))
        meta["tags"] = sorted(set(tags))[:8]
        if text:
            meta["description"] = _lead_sentence(text)

    heading = f"# {title}"
    body = f"{heading}\n\n{text}\n"
    meta["range"] = {
        "start": {"line_hint": 1, "snippet": heading},
        "end": {"line_hint": max(1, body.count("\n")), "snippet": _end_snippet(text)},
    }
    return meta, body


def write_document(kb_root: Path, doc_id: str, doc: dict[str, Any], profile: ProfileName) -> None:
    rel_md = f"corpus/{doc_id}.md"
    md_path = kb_root / rel_md
    md_path.parent.mkdir(parents=True, exist_ok=True)

    kp_meta, body = _kp_metadata(doc_id, doc, profile)
    md_path.write_text(body, encoding="utf-8")

    sidecar_dir = kb_root / ".memoria" / "sidecars" / "corpus"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "file": rel_md.replace("\\", "/"),
        "knowledge_points": [kp_meta],
        "links": [],
    }
    sc_path = sidecar_dir / f"{doc_id}.memoria.yaml"
    with open(sc_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(sidecar, f, allow_unicode=True, sort_keys=False)


def build_kb_from_scifact(
    corpus_root: Path,
    kb_root: Path,
    profile: ProfileName,
    *,
    doc_limit: int | None = None,
) -> int:
    kb_root = Path(kb_root)
    if kb_root.exists():
        shutil.rmtree(kb_root)
    kb_root.mkdir(parents=True)

    docs = load_corpus(corpus_root)
    ids = sorted(docs.keys())
    if doc_limit is not None:
        ids = ids[:doc_limit]

    for doc_id in ids:
        write_document(kb_root, doc_id, docs[doc_id], profile)

    rebuild_manifest(str(kb_root))
    return len(ids)


def export_eval_files(
    corpus_root: Path,
    eval_dir: Path,
    *,
    split: str = "test",
    query_limit: int | None = None,
    doc_ids_in_kb: set[str] | None = None,
) -> tuple[int, int]:
    eval_dir = Path(eval_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)

    queries = load_queries(corpus_root)
    qrels_raw = load_qrels(corpus_root, split=split)

    qrels_filtered: dict[str, list[str]] = {}
    query_list: list[dict[str, str]] = []

    for qid, text in sorted(queries.items(), key=lambda x: x[0]):
        rel = qrels_raw.get(qid, {})
        if doc_ids_in_kb is not None:
            rel = {d: s for d, s in rel.items() if d in doc_ids_in_kb}
        if not rel:
            continue
        qrels_filtered[qid] = sorted(d for d, s in rel.items() if s > 0)
        query_list.append({"query_id": qid, "text": text})
        if query_limit is not None and len(query_list) >= query_limit:
            break

    (eval_dir / "queries.json").write_text(
        json.dumps(query_list, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (eval_dir / "qrels.json").write_text(
        json.dumps(qrels_filtered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(query_list), len(qrels_filtered)
