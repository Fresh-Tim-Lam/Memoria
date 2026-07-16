"""Embedding v1.5d：元数据双路语义召回。"""

from memoria.services.embedding_provider import (
    _record_desc_text,
    _record_text,
    _semantic_similarity,
    search_semantic,
)
from memoria.storage.ui_settings import save_ui_settings


def test_record_desc_text_omits_body_and_aux():
    rec = {
        "kp_id": "kp1",
        "name": "Name",
        "kp_description": "误闯天家",
        "body_excerpt": "x" * 900,
        "tags": ["t"],
        "auto_tags": ["bert"],
        "key_phrases": ["attention"],
        "summary_1l": "long summary from body",
        "aliases": ["implicit-alias"],
        "aliases_explicit": ["用户别名"],
    }
    full = _record_text(rec)
    desc = _record_desc_text(rec)
    assert "误闯天家" in desc
    assert "用户别名" in desc
    assert "Name" not in desc
    assert "bert" not in desc
    assert "attention" not in desc
    assert len(full) > len(desc)
    assert rec["body_excerpt"][:50] in full
    assert rec["body_excerpt"][:50] not in desc


def test_semantic_similarity_prefers_desc_channel():
    q = [1.0, 0.0]
    rec = {
        "vector": [0.2, 0.98],
        "desc_vector": [0.95, 0.31],
    }
    sim, src = _semantic_similarity(q, rec)
    assert src == "semantic-desc"
    assert sim > 0.9


def test_search_semantic_uses_desc_channel(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_ui_settings({"search": {"embedding_enabled": True}})

    index = {
        "schema_version": 3,
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
        "records": [
            {
                "kp_id": "transformer",
                "name": "Transformer",
                "file": "t.md",
                "vector": [0.1, 0.2, 0.9],
                "desc_vector": [0.85, 0.52, 0.1],
            }
        ],
    }

    class FakeModel:
        def encode(self, texts, **kwargs):
            return [[1.0, 0.6, 0.0] for _ in texts]

    monkeypatch.setattr(
        "memoria.services.embedding_provider.ensure_embedding_index",
        lambda _kb: index,
    )
    monkeypatch.setattr(
        "memoria.services.embedding_provider._load_model",
        lambda _name: FakeModel(),
    )

    res = search_semantic("错误地闯入天的家里", kb_path=str(kb), limit=5)
    assert res["available"] is True
    hit = res["results"][0]
    assert hit["kp_id"] == "transformer"
    assert hit["sources"] == ["semantic-desc"]
    assert hit["semantic_score"] >= 80.0

    save_ui_settings({"search": {"embedding_enabled": False}})
