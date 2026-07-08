"""图谱链接自查测试。"""

from __future__ import annotations

from pathlib import Path

from memoria.graph.edge_derivation import build_target_kp_resolver
from memoria.graph.link_audit import (
    ISSUE_MISSING_SIDECAR,
    audit_file_graph_links,
    audit_kb_graph_links,
)
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.sidecar import load_sidecar_for_md

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


def test_audit_detects_missing_sidecar():
    sidecar = {
        "knowledge_points": [
            {
                "id": "sec",
                "name": "Sec",
                "range": {
                    "start": {"snippet": "## Sec"},
                    "end": {"snippet": "see [[tgt-a]] and [[tgt-b]]"},
                },
            }
        ],
        "links": [
            {
                "anchor_text": "tgt-a",
                "targets": ["mdp"],
                "instances": [{"line": 2, "wrapped": True}],
            }
        ],
    }
    body = "## Sec\nsee [[tgt-a]] and [[tgt-b]]\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))
    report = audit_file_graph_links("x.md", body, sidecar, resolve_target_kp=resolve)
    missing = [i for i in report["issues"] if i["code"] == ISSUE_MISSING_SIDECAR]
    assert len(missing) == 1
    assert missing[0]["anchor_text"] == "tgt-b"
    assert missing[0]["kp_id"] == "sec"


def test_audit_tongduan_four_wikilinks_three_unique_edges():
    md = EXAMPLES / "navigation-demo.md"
    sc = load_sidecar_for_md(md, EXAMPLES)
    body, _ = strip_frontmatter(md.read_text(encoding="utf-8"))
    resolve = build_target_kp_resolver(str(EXAMPLES))
    report = audit_file_graph_links(
        "navigation-demo.md", body, sc, resolve_target_kp=resolve
    )
    missing = [
        i
        for i in report["issues"]
        if i["code"] == ISSUE_MISSING_SIDECAR and i.get("kp_id") == "同段多链接"
    ]
    assert missing == []
    kp = next(s for s in report["kp_summaries"] if s["kp_id"] == "同段多链接")
    assert kp["wikilink_count"] == 5
    assert kp["derived_edge_count"] == 4


def test_audit_kb_runs_on_examples():
    data = audit_kb_graph_links(str(EXAMPLES))
    assert data["status"] == "ok"
    assert data["summary"]["files_checked"] >= 1
