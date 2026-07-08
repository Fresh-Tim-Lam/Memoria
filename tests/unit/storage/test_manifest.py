"""manifest 磁盘 diff。"""

from __future__ import annotations

from memoria.services.document import DocumentService
from memoria.storage.manifest import (
    audit_manifest_diff,
    filter_manifest_diff_for_path_moves,
    load_manifest,
    rebuild_manifest,
    touch_manifest_entry,
)


def _write_kb(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "a.md").write_text("# A\n\nbody\n", encoding="utf-8")
    return kb


def test_ensure_baseline_on_first_audit(tmp_path):
    kb = _write_kb(tmp_path)
    report = audit_manifest_diff(str(kb))
    assert report["baseline_created"] is True
    assert report["summary"]["warning_count"] == 0
    assert load_manifest(str(kb)) is not None


def test_detect_external_md_change(tmp_path):
    kb = _write_kb(tmp_path)
    audit_manifest_diff(str(kb))
    (kb / "a.md").write_text("# A\n\nchanged\n", encoding="utf-8")
    report = audit_manifest_diff(str(kb))
    assert report["summary"]["md_changed_count"] == 1
    codes = [w["code"] for w in report["warnings"]]
    assert "manifest_md_changed" in codes


def test_touch_manifest_after_write(tmp_path):
    kb = _write_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    audit_manifest_diff(str(kb))
    (kb / "a.md").write_text("# A\n\nvia memoria\n", encoding="utf-8")
    touch_manifest_entry(str(kb), "a.md")
    report = audit_manifest_diff(str(kb))
    assert report["summary"]["warning_count"] == 0


def test_rebuild_manifest(tmp_path):
    kb = _write_kb(tmp_path)
    audit_manifest_diff(str(kb))
    (kb / "b.md").write_text("# B\n", encoding="utf-8")
    report = audit_manifest_diff(str(kb))
    assert report["summary"]["added_count"] == 1
    rebuild_manifest(str(kb))
    report2 = audit_manifest_diff(str(kb))
    assert report2["summary"]["warning_count"] == 0


def test_validate_kb_includes_manifest(tmp_path):
    kb = _write_kb(tmp_path)
    svc = DocumentService(kb_path=str(kb))
    report = svc.validate_kb()
    assert "manifest_diff" in report
    assert load_manifest(str(kb)) is not None
    assert report["manifest_diff"]["summary"]["warning_count"] == 0


def test_filter_manifest_hides_move_add_remove(tmp_path):
    kb = _write_kb(tmp_path)
    audit_manifest_diff(str(kb))
    sub = kb / "subdir"
    sub.mkdir()
    (kb / "a.md").replace(sub / "a.md")
    raw = audit_manifest_diff(str(kb))
    assert raw["summary"]["added_count"] == 1
    assert raw["summary"]["removed_count"] == 1
    moves = [{"from": "a.md", "to": "subdir/a.md", "kind": "md_sha256"}]
    filtered = filter_manifest_diff_for_path_moves(raw, moves)
    assert filtered["summary"]["warning_count"] == 0


def test_sync_manifest_blocked_when_path_moves(tmp_path):
    kb = _write_kb(tmp_path)
    audit_manifest_diff(str(kb))
    sub = kb / "subdir"
    sub.mkdir()
    (kb / "a.md").replace(sub / "a.md")
    svc = DocumentService(kb_path=str(kb))
    res = svc.sync_manifest()
    assert res["status"] == "error"
    assert res.get("blocked") is True
    assert len(res.get("path_moves") or []) == 1
