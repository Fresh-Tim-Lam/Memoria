"""EmbeddingProvider 设置与 stub 行为。"""

from memoria.services.embedding_provider import (
    is_embedding_enabled,
    search_semantic,
)
from memoria.storage.ui_settings import save_ui_settings


def test_semantic_disabled_by_default():
    save_ui_settings({"search": {"embedding_enabled": False}})
    assert is_embedding_enabled() is False
    res = search_semantic("q", kb_path="/tmp/x", limit=5)
    assert res["available"] is False
    assert res["reason"] == "embedding_not_enabled"
    save_ui_settings({"search": {"embedding_enabled": False}})


def test_semantic_not_installed_when_enabled(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / ".memoria" / "cache" / "lexical").mkdir(parents=True)
    save_ui_settings({"search": {"embedding_enabled": True}})
    try:
        monkeypatch.setattr(
            "memoria.services.embedding_provider.ensure_embedding_index",
            lambda _kb: {"records": []},
        )
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("no st")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        res = search_semantic("q", kb_path=str(kb), limit=5)
        assert res["reason"] == "embedding_not_installed"
    finally:
        save_ui_settings({"search": {"embedding_enabled": False}})
