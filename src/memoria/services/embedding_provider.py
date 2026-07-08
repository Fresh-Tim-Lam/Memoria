"""Embedding 检索层（M4 · 可选 sentence-transformers）。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from datetime import datetime, timezone
from typing import Any

from memoria.services.text_normalize import normalize_math_for_semantic
from memoria.services.lexical_index import ensure_lexical_index
from memoria.storage.ui_settings import load_ui_settings

SCHEMA_VERSION = 2
_SUPPORTED_SCHEMA_VERSIONS = {1, 2}
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_model_cache: dict[str, Any] = {}
_warmup_lock = threading.Lock()
_warmup_started: set[str] = set()


def embedding_cache_path(kb_path: str) -> str:
    return os.path.join(kb_path, ".memoria", "cache", "embeddings", "index.json")


def _search_settings() -> dict:
    raw = load_ui_settings().get("search")
    return raw if isinstance(raw, dict) else {}


def is_embedding_enabled() -> bool:
    return bool(_search_settings().get("embedding_enabled"))


def embedding_model_name() -> str:
    name = str(_search_settings().get("embedding_model") or "").strip()
    return name or DEFAULT_MODEL


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _record_text(rec: dict) -> str:
    parts = [
        str(rec.get("kp_id") or ""),
        str(rec.get("name") or ""),
        " ".join(str(t) for t in (rec.get("tags") or [])),
        str(rec.get("kp_description") or ""),
        str(rec.get("body_excerpt") or "")[:800],
    ]
    return normalize_math_for_semantic(" ".join(p for p in parts if p))


def _text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_model(model_name: str):
    if model_name in _model_cache:
        return _model_cache[model_name]
    from sentence_transformers import SentenceTransformer

    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except (OSError, ValueError, ImportError):
        model = SentenceTransformer(model_name)
    _model_cache[model_name] = model
    return model


def _make_out_record(lex_rec: dict, vec: list[float], text_fp: str) -> dict:
    return {
        "kp_id": lex_rec.get("kp_id"),
        "file": lex_rec.get("file"),
        "name": lex_rec.get("name"),
        "text_fp": text_fp,
        "vector": vec,
    }


def _index_meta(
    model: str,
    *,
    lexical_built_at: str | None,
    records: list[dict],
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "model": model,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "lexical_built_at": lexical_built_at or "",
        "record_count": len(records),
        "records": records,
    }


def sync_embedding_index(kb_path: str, *, force: bool = False) -> dict | None:
    """增量同步向量索引：仅对新增/变更 KP 编码，其余复用磁盘缓存。"""
    if not is_embedding_enabled():
        return None
    try:
        model_name = embedding_model_name()
        lexical = ensure_lexical_index(kb_path)
        lexical_records = lexical.get("records") or []
        lexical_built_at = str(lexical.get("built_at") or "")
        cached = None if force else load_embedding_index(kb_path)
        cached_by_id: dict[str, dict] = {}
        if cached:
            for rec in cached.get("records") or []:
                kid = str(rec.get("kp_id") or "")
                if kid:
                    cached_by_id[kid] = rec

        if (
            cached
            and not force
            and str(cached.get("lexical_built_at") or "") == lexical_built_at
            and int(cached.get("record_count") or 0) == len(lexical_records)
            and int(cached.get("schema_version") or 0) == SCHEMA_VERSION
        ):
            return cached

        out_records: list[dict] = []
        pending: list[tuple[dict, str, str]] = []

        for lex_rec in lexical_records:
            kid = str(lex_rec.get("kp_id") or "")
            if not kid:
                continue
            text = _record_text(lex_rec)
            text_fp = _text_fingerprint(text)
            old = cached_by_id.get(kid)
            old_vec = old.get("vector") if isinstance(old, dict) else None
            if (
                not force
                and isinstance(old_vec, list)
                and old_vec
                and str(old.get("text_fp") or "") == text_fp
            ):
                out_records.append(_make_out_record(lex_rec, [float(x) for x in old_vec], text_fp))
                continue
            if not force and isinstance(old_vec, list) and old_vec and not old.get("text_fp"):
                # v1 索引迁移：KP 仍在且尚无指纹时先复用向量并写入指纹
                out_records.append(_make_out_record(lex_rec, [float(x) for x in old_vec], text_fp))
                continue
            pending.append((lex_rec, text, text_fp))

        if pending:
            st_model = _load_model(model_name)
            vectors = st_model.encode(
                [text for _, text, _ in pending],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for (lex_rec, _text, text_fp), vec in zip(pending, vectors):
                out_records.append(
                    _make_out_record(lex_rec, [float(x) for x in vec], text_fp)
                )

        out_records.sort(key=lambda r: str(r.get("kp_id") or ""))
        index = _index_meta(
            model_name,
            lexical_built_at=lexical_built_at,
            records=out_records,
        )
        save_embedding_index(kb_path, index)
        return index
    except Exception:
        return load_embedding_index(kb_path)


def build_embedding_index(kb_path: str, *, model_name: str | None = None) -> dict:
    """全量重建（测试/强制刷新）。"""
    _ = model_name
    index = sync_embedding_index(kb_path, force=True)
    if index is None:
        return _index_meta(model_name or embedding_model_name(), lexical_built_at="", records=[])
    return index


def save_embedding_index(kb_path: str, index: dict) -> str:
    path = embedding_cache_path(kb_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    return path


def load_embedding_index(kb_path: str) -> dict | None:
    path = embedding_cache_path(kb_path)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if int(data.get("schema_version") or 0) not in _SUPPORTED_SCHEMA_VERSIONS:
            return None
        if str(data.get("model") or "") != embedding_model_name():
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def rebuild_embedding_index(kb_path: str) -> dict | None:
    return sync_embedding_index(kb_path, force=True)


def ensure_embedding_index(kb_path: str) -> dict | None:
    if not is_embedding_enabled():
        return None
    cached = load_embedding_index(kb_path)
    if cached is not None:
        lexical = ensure_lexical_index(kb_path)
        if (
            str(cached.get("lexical_built_at") or "") == str(lexical.get("built_at") or "")
            and int(cached.get("record_count") or 0) == len(lexical.get("records") or [])
            and int(cached.get("schema_version") or 0) == SCHEMA_VERSION
        ):
            return cached
    return sync_embedding_index(kb_path, force=False)


def warmup_embedding(kb_path: str) -> None:
    """后台预热：加载磁盘索引 + 本地模型，避免首次搜索阻塞 UI。"""
    if not is_embedding_enabled() or not kb_path:
        return
    with _warmup_lock:
        if kb_path in _warmup_started:
            return
        _warmup_started.add(kb_path)

    def _run() -> None:
        try:
            ensure_embedding_index(kb_path)
            _load_model(embedding_model_name())
        except Exception:
            with _warmup_lock:
                _warmup_started.discard(kb_path)

    threading.Thread(target=_run, daemon=True, name="memoria-embedding-warmup").start()


def reset_warmup_state(kb_path: str | None = None) -> None:
    with _warmup_lock:
        if kb_path:
            _warmup_started.discard(kb_path)
        else:
            _warmup_started.clear()


def search_semantic(
    query: str,
    *,
    kb_path: str,
    scope: str = "kb",
    rel_path: str | None = None,
    limit: int = 20,
) -> dict:
    q = (query or "").strip()
    if not q:
        return {
            "status": "ok",
            "available": True,
            "results": [],
            "modes": "semantic",
        }
    if not is_embedding_enabled():
        return {
            "status": "ok",
            "available": False,
            "reason": "embedding_not_enabled",
            "results": [],
        }
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return {
            "status": "ok",
            "available": False,
            "reason": "embedding_not_installed",
            "results": [],
        }

    index = ensure_embedding_index(kb_path)
    if not index or not index.get("records"):
        return {
            "status": "ok",
            "available": False,
            "reason": "embedding_index_empty",
            "results": [],
        }

    model = _load_model(str(index.get("model") or embedding_model_name()))
    q_text = normalize_math_for_semantic(q)
    q_vec = model.encode([q_text], normalize_embeddings=True, show_progress_bar=False)[0]
    q_list = [float(x) for x in q_vec]

    scope_norm = (scope or "kb").lower()
    file_norm = str(rel_path or "").replace("\\", "/")
    scored: list[tuple[float, dict]] = []
    for rec in index.get("records") or []:
        f = str(rec.get("file") or "").replace("\\", "/")
        if scope_norm == "file" and file_norm and f != file_norm:
            continue
        vec = rec.get("vector") or []
        sim = _cosine(q_list, vec)
        if sim <= 0.05:
            continue
        scored.append((sim, rec))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("kp_id") or "")))
    results = []
    for sim, rec in scored[: max(1, int(limit))]:
        pct = round(sim * 100, 1)
        name = rec.get("name") or rec.get("kp_id")
        results.append({
            "kp_id": rec.get("kp_id"),
            "id": rec.get("kp_id"),
            "label": name,
            "name": name,
            "file": rec.get("file"),
            "score": pct,
            "semantic_score": pct,
            "confidence": pct,
            "sources": ["semantic"],
        })
    return {
        "status": "ok",
        "available": True,
        "results": results,
        "modes": "semantic",
    }
