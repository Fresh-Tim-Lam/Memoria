"""link consistency audit tests."""

from __future__ import annotations

from memoria.services.document import DocumentService
from memoria.services.link_instances import audit_link_consistency


def test_navigation_demo_depth_entry_has_body():
    svc = DocumentService()
    svc.set_kb_path("examples")
    doc = svc.load_document("navigation-demo.md")
    audit = doc["link_audit"]
    entry = next(x for x in audit["links"] if x["anchor_text"] == "深度 RL")
    assert entry["status"] == "ok"
    assert entry["preview_attached_count"] >= 1


def test_audit_flags_missing_body():
    body = "plain text only\n"
    links = [{"anchor_text": "缺失链接", "targets": ["rl"], "instances": []}]
    audit = audit_link_consistency(body, links, body.split("\n"))
    assert audit["links"][0]["status"] == "missing_body"
