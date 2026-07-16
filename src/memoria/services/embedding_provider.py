"""Embedding 检索层（M4 · 可选 sentence-transformers）。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from datetime import datetime, timezone
from typing import Any

# 必须在任何 HF/transformers 相关 import 之前设置，否则 huggingface_hub
# 会在 import 时缓存 online 状态，后续 setdefault 无效
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from memoria.services.text_normalize import normalize_math_for_semantic
from memoria.services.lexical_index import ensure_lexical_index
from memoria.services.model_router import embed_recall_model
from memoria.storage.ui_settings import load_ui_settings

SCHEMA_VERSION = 3
_SUPPORTED_SCHEMA_VERSIONS = {1, 2, 3}
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_model_cache: dict[str, Any] = {}
_model_load_lock = threading.Lock()
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
    from memoria.services.model_router import embed_recall_model, normalize_embed_recall_model

    name = str(_search_settings().get("embedding_model") or "").strip()
    return normalize_embed_recall_model(name) if name else embed_recall_model()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _record_desc_text(rec: dict) -> str:
    """元数据通道：有 description 时以描述为主；否则 name/tags/别名。"""
    name = str(rec.get("name") or "").strip()
    desc = str(rec.get("kp_description") or "").strip()
    aliases = " ".join(str(a) for a in (rec.get("aliases_explicit") or []) if str(a).strip())
    if desc:
        parts = [desc, aliases] if aliases else [desc]
    else:
        parts = [
            str(rec.get("kp_id") or ""),
            name,
            " ".join(str(t) for t in (rec.get("tags") or [])),
            aliases,
            str(rec.get("file_description") or ""),
        ]
    return normalize_math_for_semantic(" ".join(p for p in parts if p))


def _record_text(rec: dict) -> str:
    auto_tags = " ".join(str(t) for t in (rec.get("auto_tags") or []))
    aliases = " ".join(str(a) for a in (rec.get("aliases") or []))
    phrases = " ".join(str(p) for p in (rec.get("key_phrases") or []))
    parts = [
        str(rec.get("kp_id") or ""),
        str(rec.get("name") or ""),
        " ".join(str(t) for t in (rec.get("tags") or [])),
        str(rec.get("kp_description") or ""),
        auto_tags,
        aliases,
        phrases,
        str(rec.get("summary_1l") or ""),
        str(rec.get("body_excerpt") or "")[:800],
    ]
    return normalize_math_for_semantic(" ".join(p for p in parts if p))


def _text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class _TransformersEmbedder:
    """Wraps transformers AutoTokenizer + AutoModel with mean pooling.

    Replaces sentence_transformers.SentenceTransformer to avoid
    ONNX/Keras compatibility issues.
    """

    def __init__(self, model_name: str):
        import sys as _sys
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from transformers import AutoTokenizer, AutoModel

        _diag = os.environ.get("MEMORIA_EMB_DIAG")
        if _diag:
            print(f"[emb-diag] loading tokenizer: {model_name}", file=_sys.stderr, flush=True)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        if _diag:
            print(f"[emb-diag] tokenizer OK, loading model: {model_name}", file=_sys.stderr, flush=True)
        self.model = AutoModel.from_pretrained(model_name, local_files_only=True)
        self.model.eval()
        self._name = model_name
        if _diag:
            print(f"[emb-diag] model OK: {type(self.model).__name__}", file=_sys.stderr, flush=True)

    def encode(self, sentences, *, normalize_embeddings: bool = True, show_progress_bar: bool = False):
        import torch

        if isinstance(sentences, str):
            sentences = [sentences]
        results = []
        with torch.no_grad():
            for text in sentences:
                inputs = self.tokenizer(
                    text, return_tensors="pt", padding=True, truncation=True, max_length=512
                )
                outputs = self.model(**inputs)
                token_embeddings = outputs.last_hidden_state
                attention_mask = inputs["attention_mask"]
                input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
                embedding = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
                    input_mask_expanded.sum(1), min=1e-9
                )
                if normalize_embeddings:
                    embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
                results.append(embedding[0].cpu().tolist())
        return results


def _load_model(model_name: str):
    name = (model_name or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if name in _model_cache:
        return _model_cache[name]
    with _model_load_lock:
        if name in _model_cache:
            return _model_cache[name]
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        try:
            model = _TransformersEmbedder(name)
        except (OSError, ValueError, ImportError):
            if name != DEFAULT_MODEL:
                return _load_model(DEFAULT_MODEL)
            raise
        _model_cache[name] = model
        return model


def _make_out_record(
    lex_rec: dict,
    vec: list[float],
    desc_vec: list[float],
    text_fp: str,
) -> dict:
    return {
        "kp_id": lex_rec.get("kp_id"),
        "file": lex_rec.get("file"),
        "name": lex_rec.get("name"),
        "text_fp": text_fp,
        "vector": vec,
        "desc_vector": desc_vec,
    }


def _combined_fingerprint(full_text: str, desc_text: str) -> str:
    return _text_fingerprint(full_text + "\x1e" + desc_text)


def _semantic_similarity(
    q_list: list[float],
    rec: dict,
) -> tuple[float, str]:
    """返回 (相似度 0–1, source: semantic | semantic-desc)。"""
    vec = rec.get("vector") or []
    desc_vec = rec.get("desc_vector") or []
    sim_full = _cosine(q_list, vec)
    sim_desc = _cosine(q_list, desc_vec) if desc_vec else 0.0
    if sim_desc > sim_full + 1e-6:
        return sim_desc, "semantic-desc"
    return sim_full, "semantic"


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
        pending: list[tuple[dict, str, str, str]] = []

        for lex_rec in lexical_records:
            kid = str(lex_rec.get("kp_id") or "")
            if not kid:
                continue
            text = _record_text(lex_rec)
            desc_text = _record_desc_text(lex_rec)
            text_fp = _combined_fingerprint(text, desc_text)
            old = cached_by_id.get(kid)
            old_vec = old.get("vector") if isinstance(old, dict) else None
            old_desc = old.get("desc_vector") if isinstance(old, dict) else None
            if (
                not force
                and isinstance(old_vec, list)
                and old_vec
                and isinstance(old_desc, list)
                and old_desc
                and str(old.get("text_fp") or "") == text_fp
            ):
                out_records.append(
                    _make_out_record(
                        lex_rec,
                        [float(x) for x in old_vec],
                        [float(x) for x in old_desc],
                        text_fp,
                    )
                )
                continue
            if not force and isinstance(old_vec, list) and old_vec and not old.get("text_fp"):
                pending.append((lex_rec, text, desc_text, text_fp))
                continue
            pending.append((lex_rec, text, desc_text, text_fp))

        if pending:
            st_model = _load_model(model_name)
            batch: list[str] = []
            for _lex_rec, text, desc_text, _fp in pending:
                batch.append(text)
                batch.append(desc_text)
            vectors = st_model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for i, (lex_rec, _text, _desc_text, text_fp) in enumerate(pending):
                out_records.append(
                    _make_out_record(
                        lex_rec,
                        [float(x) for x in vectors[i * 2]],
                        [float(x) for x in vectors[i * 2 + 1]],
                        text_fp,
                    )
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
    import sys as _sys
    _diag = os.environ.get("MEMORIA_EMB_DIAG")
    def _dlog(msg):
        if _diag:
            print(f"[emb-search] {msg}", file=_sys.stderr, flush=True)

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
    _dlog("importing torch/transformers")
    try:
        import torch  # noqa: F401
        from transformers import AutoTokenizer, AutoModel  # noqa: F401
    except ImportError:
        return {
            "status": "ok",
            "available": False,
            "reason": "embedding_not_installed",
            "results": [],
        }

    _dlog("ensure_embedding_index")
    index = ensure_embedding_index(kb_path)
    _dlog(f"index records={len(index.get('records') or []) if index else 0}")
    if not index or not index.get("records"):
        return {
            "status": "ok",
            "available": False,
            "reason": "embedding_index_empty",
            "results": [],
        }

    _dlog("loading model")
    model = _load_model(str(index.get("model") or embedding_model_name()))
    _dlog("model loaded, encoding query")
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
        sim, src = _semantic_similarity(q_list, rec)
        if sim <= 0.05:
            continue
        scored.append((sim, src, rec))

    scored.sort(key=lambda x: (-x[0], str(x[2].get("kp_id") or "")))
    results = []
    for sim, src, rec in scored[: max(1, int(limit))]:
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
            "sources": [src],
        })
    return {
        "status": "ok",
        "available": True,
        "results": results,
        "modes": "semantic",
    }
