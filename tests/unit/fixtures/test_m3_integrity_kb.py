"""M3 完整性测试知识库（tests/fixtures/m3_integrity_kb）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memoria.graph.link_audit import ISSUE_MISSING_SIDECAR
from memoria.services.document import DocumentService
from memoria.storage.kb_integrity import (
    CODE_DUPLICATE_KP_ID,
    CODE_ORPHAN_MD,
    CODE_ORPHAN_SIDECAR,
    audit_kb_integrity,
)

FIXTURE_KB = Path(__file__).resolve().parents[2] / "fixtures" / "m3_integrity_kb"


@pytest.fixture
def svc() -> DocumentService:
    s = DocumentService()
    s.set_kb_path(str(FIXTURE_KB))
    return s


def test_fixture_kb_exists():
    assert FIXTURE_KB.is_dir()
    assert (FIXTURE_KB / "ok-clean.md").is_file()


def test_kb_integrity_detects_duplicate_ids():
    report = audit_kb_integrity(str(FIXTURE_KB))
    codes = [e["code"] for e in report["errors"]]
    assert CODE_DUPLICATE_KP_ID in codes
    dup = next(e for e in report["errors"] if e["code"] == CODE_DUPLICATE_KP_ID)
    assert "shared-dup-id" in dup["message"]
    assert set(dup["paths"]) == {"dup-a.md", "dup-b.md"}


def test_kb_integrity_detects_orphans():
    report = audit_kb_integrity(str(FIXTURE_KB))
    warn_codes = {w["code"] for w in report["warnings"]}
    assert CODE_ORPHAN_MD in warn_codes
    assert CODE_ORPHAN_SIDECAR in warn_codes
    orphan_md = next(w for w in report["warnings"] if w["code"] == CODE_ORPHAN_MD)
    assert orphan_md["paths"] == ["orphan-md.md"]
    orphan_sc = next(w for w in report["warnings"] if w["code"] == CODE_ORPHAN_SIDECAR)
    assert orphan_sc["paths"] == ["orphan-only.md"]


def test_validate_kb_status_error(svc: DocumentService):
    report = svc.validate_kb()
    assert report["status"] == "error"
    assert report["errors"] >= 2
    assert report["warnings"] >= 4
    assert report["kb_integrity"]["summary"]["error_count"] >= 1


def test_validate_kb_bad_target_file(svc: DocumentService):
    report = svc.validate_kb()
    bad = next(f for f in report["files"] if f["path"] == "bad-target.md")
    assert any("target 不存在" in e for e in bad["errors"])


def test_validate_kb_range_broken_warning(svc: DocumentService):
    report = svc.validate_kb()
    rb = next(f for f in report["files"] if f["path"] == "range-broken.md")
    assert any("无法重定位" in w for w in rb["warnings"])


def test_validate_kb_file_mismatch_warning(svc: DocumentService):
    report = svc.validate_kb()
    fm = next(f for f in report["files"] if f["path"] == "file-mismatch.md")
    assert any("file 路径" in w for w in fm["warnings"])


def test_validate_kb_ok_clean_no_issues(svc: DocumentService):
    report = svc.validate_kb()
    clean = next((f for f in report["files"] if f["path"] == "ok-clean.md"), None)
    assert clean is None


def test_graph_audit_wikilink_gap(svc: DocumentService):
    report = svc.validate_kb()
    ga = report["graph_audit"]
    file_report = next(f for f in ga["files"] if f["file"] == "wikilink-gap.md")
    codes = {i["code"] for i in file_report["issues"]}
    assert ISSUE_MISSING_SIDECAR in codes
    ga_warn = ga["summary"]["warn_count"]
    assert ga_warn > 0
    assert report["warnings"] >= ga_warn


def test_load_ok_clean_document(svc: DocumentService):
    doc = svc.load_document("ok-clean.md")
    assert doc["status"] == "ok"
    assert len(doc["knowledge_points"]) == 1
    assert doc["knowledge_points"][0]["id"] == "ok-kp"
