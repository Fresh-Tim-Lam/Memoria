"""examples 知识库 M0 收尾验收。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memoria.services.document import DocumentService
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import sidecar_path_for

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


@pytest.fixture
def svc() -> DocumentService:
    s = DocumentService()
    s.set_kb_path(str(EXAMPLES))
    return s


def test_all_examples_have_sidecar(svc: DocumentService):
    rels = list(collect_md_files(str(EXAMPLES)))
    missing = []
    for rel in rels:
        full = Path(sidecar_path_for(EXAMPLES / rel, EXAMPLES))
        if not full.is_file():
            missing.append(rel)
    assert not missing, "缺少侧车: " + ", ".join(missing)


def test_all_sidecars_validate_without_errors(svc: DocumentService):
    report = svc.validate_kb()
    assert report["status"] == "ok"
    assert report["errors"] == 0, report["files"]


def test_load_mdp_has_resolved_kps(svc: DocumentService):
    doc = svc.load_document("mdp.md")
    assert doc["status"] == "ok"
    assert len(doc["knowledge_points"]) >= 2
    assert all(kp.get("range_resolved", {}).get("ok") for kp in doc["knowledge_points"])


def test_transformer_pending_excludes_confirmed_kps(svc: DocumentService):
    doc = svc.load_document("transformer.md")
    assert len(doc["knowledge_points"]) >= 1
    assert isinstance(doc["heading_proposals"], list)
    assert isinstance(doc["mention_proposals"], list)
    confirmed_names = {(kp.get("name") or "").strip() for kp in doc["knowledge_points"]}
    confirmed_ids = {(kp.get("id") or "").strip() for kp in doc["knowledge_points"]}
    for p in doc["heading_proposals"]:
        name = (p.get("name") or "").strip()
        assert name not in confirmed_names and name not in confirmed_ids
