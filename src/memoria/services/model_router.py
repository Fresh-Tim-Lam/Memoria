"""SearchKernel v1.5c：多模型路由骨架（lazy load + 设置/manifest）。"""

from __future__ import annotations

import json
import os
from typing import Any

from memoria.storage.ui_settings import load_ui_settings

DEFAULT_MODEL_SET: dict[str, str | None] = {
    "lexical": "rule+jieba+pypinyin",
    "embed_recall": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "embed_rerank": "BAAI/bge-reranker-v2-m3",
    "embed_rerank_light": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "mt_bridge": "opus-mt-zh-en",
    "llm_tag": None,
    "llm_summary": None,
    "ltr_feedback": "linear-v1",
}

ROLE_FLAGS: dict[str, str] = {
    "embed_recall": "embedding_enabled",
    "embed_rerank": "rerank_enabled",
    "mt_bridge": "mt_bridge_enabled",
}

# 单元测试等误写入的占位名；非 HuggingFace 真实模型
_BLOCKED_EMBED_MODELS = frozenset({
    "custom-model",
    "test-model",
    "fake-model",
})

# 用户/UI 历史配置可能保存了无 org 前缀的短名；映射到 HF cache 的完整 id
# 避免在 local_files_only=True 时按短名查 cache 失败
_MODEL_ALIAS_MAP: dict[str, str] = {
    "paraphrase-multilingual-MiniLM-L12-v2": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
    "all-mpnet-base-v2": "sentence-transformers/all-mpnet-base-v2",
    "multi-qa-MiniLM-L6-cos-v1": "sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
    "bge-base-en-v1.5": "BAAI/bge-base-en-v1.5",
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
    "bge-large-en-v1.5": "BAAI/bge-large-en-v1.5",
}


def normalize_embed_recall_model(name: str | None) -> str:
    """校验用户配置的召回模型名；非法则回退默认，短名补全 org 前缀。"""
    raw = str(name or "").strip()
    if not raw or raw.lower() in _BLOCKED_EMBED_MODELS:
        return str(DEFAULT_MODEL_SET["embed_recall"])
    return _MODEL_ALIAS_MAP.get(raw, raw)


def models_manifest_path(kb_path: str | None) -> str | None:
    if not kb_path:
        return None
    return os.path.join(kb_path, ".memoria", "cache", "models", "manifest.json")


def _load_kb_manifest(kb_path: str | None) -> dict[str, Any]:
    path = models_manifest_path(kb_path)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_model_set(*, kb_path: str | None = None) -> dict[str, Any]:
    """合并默认 model_set、UI 设置与 KB manifest。"""
    search = load_ui_settings().get("search")
    search = search if isinstance(search, dict) else {}
    manifest = _load_kb_manifest(kb_path)

    model_set = dict(DEFAULT_MODEL_SET)
    embed_override = str(search.get("embedding_model") or "").strip()
    if embed_override:
        model_set["embed_recall"] = normalize_embed_recall_model(embed_override)
    for key in DEFAULT_MODEL_SET:
        if search.get(key):
            model_set[key] = str(search[key]).strip()
        ms = manifest.get("model_set")
        if isinstance(ms, dict) and ms.get(key):
            model_set[key] = str(ms[key]).strip()

    bridge_lang = str(
        manifest.get("bridge_lang")
        or search.get("bridge_lang")
        or "en"
    ).strip().lower()
    if bridge_lang not in ("en", "zh", "off"):
        bridge_lang = "en"

    rerank_tier = str(search.get("rerank_tier") or "default").strip().lower()
    if rerank_tier == "light":
        model_set["embed_rerank"] = model_set.get("embed_rerank_light")

    return {
        "model_set": model_set,
        "bridge_lang": bridge_lang,
        "flags": {
            "embedding_enabled": bool(search.get("embedding_enabled")),
            "rerank_enabled": bool(search.get("rerank_enabled")),
            "mt_bridge_enabled": bool(search.get("mt_bridge_enabled")),
            "body_locate_enabled": bool(search.get("body_locate_enabled")),
        },
    }


def is_role_enabled(role: str, *, kb_path: str | None = None) -> bool:
    cfg = load_model_set(kb_path=kb_path)
    flags = cfg.get("flags") or {}
    if role == "lexical":
        return True
    flag_key = ROLE_FLAGS.get(role)
    if flag_key:
        return bool(flags.get(flag_key))
    return False


def model_id(role: str, *, kb_path: str | None = None) -> str | None:
    cfg = load_model_set(kb_path=kb_path)
    ms = cfg.get("model_set") or {}
    val = ms.get(role)
    return str(val).strip() if val else None


def bridge_lang(*, kb_path: str | None = None) -> str:
    return str(load_model_set(kb_path=kb_path).get("bridge_lang") or "en")


def embed_recall_model(*, kb_path: str | None = None) -> str:
    return normalize_embed_recall_model(model_id("embed_recall", kb_path=kb_path))


def embed_rerank_model(*, kb_path: str | None = None) -> str | None:
    if not is_role_enabled("embed_rerank", kb_path=kb_path):
        return None
    return model_id("embed_rerank", kb_path=kb_path)


def query_plan_stub(*, kb_path: str | None = None) -> dict[str, Any]:
    """检索 QueryPlan 占位（MT / alias 扩展在 1.5d 实现）。"""
    cfg = load_model_set(kb_path=kb_path)
    return {
        "expanded": [],
        "bridge_lang": cfg.get("bridge_lang") if is_role_enabled("mt_bridge", kb_path=kb_path) else None,
        "roles": {
            role: {
                "enabled": is_role_enabled(role, kb_path=kb_path),
                "model": model_id(role, kb_path=kb_path),
            }
            for role in ("lexical", "embed_recall", "embed_rerank", "mt_bridge")
        },
    }
