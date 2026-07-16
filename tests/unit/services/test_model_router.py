"""SearchKernel v1.5c：ModelRouter 骨架。"""

from memoria.services.model_router import (
    DEFAULT_MODEL_SET,
    embed_recall_model,
    is_role_enabled,
    load_model_set,
    normalize_embed_recall_model,
    query_plan_stub,
)
from memoria.storage import ui_settings


def _patch_settings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_settings, "_settings_dir", lambda: tmp_path)


def test_load_model_set_defaults(tmp_path, monkeypatch):
    _patch_settings_dir(tmp_path, monkeypatch)
    ui_settings.save_ui_settings({"search": {"embedding_enabled": False, "embedding_model": ""}})
    cfg = load_model_set()
    assert cfg["model_set"]["embed_recall"] == DEFAULT_MODEL_SET["embed_recall"]
    assert cfg["bridge_lang"] == "en"
    assert cfg["flags"]["embedding_enabled"] is False


def test_is_role_enabled_embedding(tmp_path, monkeypatch):
    _patch_settings_dir(tmp_path, monkeypatch)
    ui_settings.save_ui_settings({"search": {"embedding_enabled": True, "rerank_enabled": False}})
    assert is_role_enabled("lexical") is True
    assert is_role_enabled("embed_recall") is True
    assert is_role_enabled("embed_rerank") is False


def test_normalize_embed_recall_model_rejects_test_placeholder():
    assert normalize_embed_recall_model("custom-model") == DEFAULT_MODEL_SET["embed_recall"]
    assert normalize_embed_recall_model("paraphrase-multilingual-MiniLM-L12-v2") == (
        "paraphrase-multilingual-MiniLM-L12-v2"
    )


def test_embed_recall_model_from_settings(tmp_path, monkeypatch):
    _patch_settings_dir(tmp_path, monkeypatch)
    ui_settings.save_ui_settings(
        {"search": {"embedding_model": "paraphrase-multilingual-MiniLM-L12-v2"}}
    )
    assert embed_recall_model() == "paraphrase-multilingual-MiniLM-L12-v2"


def test_query_plan_stub(tmp_path, monkeypatch):
    _patch_settings_dir(tmp_path, monkeypatch)
    ui_settings.save_ui_settings({"search": {"embedding_enabled": True, "mt_bridge_enabled": False}})
    plan = query_plan_stub()
    assert plan["bridge_lang"] is None
    assert plan["roles"]["lexical"]["enabled"] is True
    assert plan["roles"]["embed_recall"]["enabled"] is True
