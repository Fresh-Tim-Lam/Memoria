"""kb_integrity 单元测试。"""

from __future__ import annotations

from pathlib import Path

from memoria.storage.kb_integrity import audit_kb_integrity, collect_sidecar_md_rels

FIXTURE_KB = Path(__file__).resolve().parents[2] / "fixtures" / "m3_integrity_kb"


def test_collect_sidecar_md_rels():
    rels = collect_sidecar_md_rels(str(FIXTURE_KB))
    assert "ok-clean.md" in rels
    assert "orphan-only.md" in rels
    assert "orphan-md.md" not in rels


def test_audit_summary_counts():
    report = audit_kb_integrity(str(FIXTURE_KB))
    s = report["summary"]
    assert s["md_count"] >= 8
    assert s["sidecar_count"] >= 7
    assert s["error_count"] >= 1
    assert s["warning_count"] >= 2
