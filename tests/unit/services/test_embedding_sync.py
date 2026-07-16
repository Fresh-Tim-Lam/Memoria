"""Embedding 增量索引与预热。"""

import json
from pathlib import Path

import pytest
import yaml

from memoria.services.embedding_provider import (
    SCHEMA_VERSION,
    embedding_cache_path,
    sync_embedding_index,
)
from memoria.storage.ui_settings import save_ui_settings


@pytest.fixture
def kb_with_lexical(tmp_path, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    md = kb / "note.md"
    md.write_text("# Title\n\nBody about cats.\n", encoding="utf-8")
    sidecar_dir = kb / ".memoria" / "sidecars"
    sidecar_dir.mkdir(parents=True)
    sidecar = {
        "schema_version": 1,
        "file": "note.md",
        "knowledge_points": [
            {
                "id": "kp-cat",
                "name": "Cat",
                "tags": ["animal"],
                "description": "feline",
                "range": {
                    "start": {"line_hint": 3},
                    "end": {"line_hint": 3},
                },
            }
        ],
    }
    (sidecar_dir / "note.memoria.yaml").write_text(
        yaml.dump(sidecar, allow_unicode=True),
        encoding="utf-8",
    )
    encode_calls: list[list[str]] = []

    class FakeModel:
        def encode(self, texts, **kwargs):
            encode_calls.append(list(texts))
            return [[0.1, 0.9, 0.0] for _ in texts]

    monkeypatch.setattr(
        "memoria.services.embedding_provider._load_model",
        lambda _name: FakeModel(),
    )
    save_ui_settings({"search": {"embedding_enabled": True}})
    return kb, encode_calls


def test_sync_embedding_incremental_reuses_vectors(kb_with_lexical):
    kb, encode_calls = kb_with_lexical
    first = sync_embedding_index(str(kb), force=True)
    assert first is not None
    assert first["schema_version"] == SCHEMA_VERSION
    assert len(first["records"]) == 1
    assert encode_calls and len(encode_calls[0]) == 2
    assert "desc_vector" in first["records"][0]

    encode_calls.clear()
    second = sync_embedding_index(str(kb), force=False)
    assert second is not None
    assert encode_calls == []
    assert second["records"][0]["vector"] == first["records"][0]["vector"]


def test_sync_embedding_only_encodes_changed_kp(kb_with_lexical):
    kb, encode_calls = kb_with_lexical
    sync_embedding_index(str(kb), force=True)
    encode_calls.clear()

    sidecar_path = kb / ".memoria" / "sidecars" / "note.memoria.yaml"
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8"))
    sidecar["knowledge_points"].append(
        {
            "id": "kp-dog",
            "name": "Dog",
            "tags": ["animal"],
            "description": "canine",
            "range": {
                "start": {"line_hint": 3},
                "end": {"line_hint": 3},
            },
        }
    )
    sidecar_path.write_text(yaml.dump(sidecar, allow_unicode=True), encoding="utf-8")

    from memoria.services.lexical_index import rebuild_lexical_index

    rebuild_lexical_index(str(kb))

    index = sync_embedding_index(str(kb), force=False)
    assert index is not None
    assert len(index["records"]) == 2
    assert len(encode_calls) == 1
    assert len(encode_calls[0]) == 2


def test_embedding_index_persisted_on_disk(kb_with_lexical):
    kb, _ = kb_with_lexical
    sync_embedding_index(str(kb), force=True)
    path = Path(embedding_cache_path(str(kb)))
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["record_count"] == 1
    assert "text_fp" in data["records"][0]

    save_ui_settings({"search": {"embedding_enabled": False}})
