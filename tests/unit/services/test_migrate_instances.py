"""migrate_link_instances reconcile tests."""

from __future__ import annotations

from memoria.services.link_instances import migrate_link_instances


def test_reconcile_stale_instance_lines():
    body = "line1\n[[按顺序点]] here\n"
    lines = body.split("\n")
    link = {
        "anchor_text": "按顺序点",
        "targets": ["x"],
        "instances": [{"line": 99, "wrapped": True}],
    }
    out = migrate_link_instances(body, link, lines)
    assert out["instances"] == [{"line": 2, "wrapped": True}]
