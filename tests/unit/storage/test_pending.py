"""pending.yaml 同步与持久化。"""

from __future__ import annotations

import shutil
from pathlib import Path

from memoria.services.document import DocumentService
from memoria.storage.pending import (
    dismiss_pending_item,
    load_pending,
    proposals_for_file,
    sync_kb_pending,
)


def _copy_fixture(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "m3_pending_kb"
    kb = tmp_path / "kb"
    shutil.copytree(src, kb)
    return kb


def test_sync_creates_pending_with_h4_proposals(tmp_path):
    kb = _copy_fixture(tmp_path)
    summary = sync_kb_pending(str(kb))
    assert summary["pending_count"] >= 3
    assert load_pending(str(kb)) is not None
    heading, mention, definition = proposals_for_file(str(kb), "module1.md")
    kp_heading = [p for p in heading if p["name"].startswith("知识点")]
    assert len(kp_heading) == 3


def test_pending_survives_reopen(tmp_path):
    kb = _copy_fixture(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    doc = svc.load_document("module1.md")
    assert len(doc["heading_proposals"]) >= 3

    svc2 = DocumentService(kb_path=str(kb))
    doc2 = svc2.load_document("module1.md")
    assert len(doc2["heading_proposals"]) == len(doc["heading_proposals"])


def test_confirm_removes_from_pending(tmp_path):
    kb = _copy_fixture(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    doc = svc.load_document("module1.md")
    before = len(doc["heading_proposals"])
    assert before >= 1
    prop = doc["heading_proposals"][0]
    start = prop["range"]["start"]["line_hint"]
    end = prop["range"]["end"]["line_hint"]
    svc.confirm_kp_range(
        "module1.md",
        prop["name"],
        prop["name"],
        start,
        end,
    )
    doc2 = svc.load_document("module1.md")
    assert len(doc2["heading_proposals"]) == before - 1


def test_dismiss_prevents_resync(tmp_path):
    kb = _copy_fixture(tmp_path)
    sync_kb_pending(str(kb))
    heading, _, _ = proposals_for_file(str(kb), "module1.md")
    pid = heading[0]["pending_id"]
    assert pid
    dismiss_pending_item(str(kb), pid)
    sync_kb_pending(str(kb))
    heading2, _, _ = proposals_for_file(str(kb), "module1.md")
    assert all(p["pending_id"] != pid for p in heading2)
