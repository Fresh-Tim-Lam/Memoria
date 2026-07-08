"""知识库构建测试。"""

from __future__ import annotations

import json
from pathlib import Path

from memoria.graph.edge_derivation import (
    build_target_kp_resolver,
    derive_file_graph_edges,
    kp_ranges_from_resolved,
    sources_for_link_instance,
)
from memoria.graph.kb_build import build_knowledge_base, sync_file_sidecar_links
from memoria.services.kp_resolver import resolve_knowledge_points
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.sidecar import load_sidecar_for_md

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


def test_sync_creates_link_for_wikilink_in_kp_range():
    sidecar = {
        "knowledge_points": [
            {
                "id": "sec",
                "name": "Sec",
                "range": {
                    "start": {"snippet": "## Sec"},
                    "end": {"snippet": "see [[mdp]] here"},
                },
            }
        ],
        "links": [],
    }
    body = "## Sec\n\nsee [[mdp]] here\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))
    sync = sync_file_sidecar_links("x.md", body, sidecar, resolve_target_kp=resolve)
    assert sync["links_created"] == 1
    assert sync["instances_added"] == 1
    assert sidecar["links"][0]["anchor_text"] == "mdp"
    assert sidecar["links"][0]["targets"] == ["mdp"]
    assert sidecar["links"][0]["instances"] == [{"line": 3, "wrapped": True}]


def test_sync_preserves_existing_targets():
    sidecar = {
        "knowledge_points": [
            {
                "id": "sec",
                "name": "Sec",
                "range": {
                    "start": {"snippet": "## Sec"},
                    "end": {"snippet": "[[深度 RL]] end"},
                },
            }
        ],
        "links": [
            {
                "anchor_text": "深度 RL",
                "targets": ["ddpg"],
                "instances": [],
            }
        ],
    }
    body = "## Sec\n\n[[深度 RL]] end\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))
    sync = sync_file_sidecar_links("x.md", body, sidecar, resolve_target_kp=resolve)
    assert sync["links_created"] == 0
    assert sidecar["links"][0]["targets"] == ["ddpg"]


def test_sync_parent_only_gap_between_children():
    """父 KP 与子 KP 之间的空隙区（不相交区域）仍应同步 wikilink。"""
    sidecar = {
        "knowledge_points": [
            {
                "id": "parent",
                "name": "Parent",
                "range": {
                    "start": {"snippet": "# Parent"},
                    "end": {"snippet": "tail line"},
                },
            },
            {
                "id": "child-a",
                "name": "A",
                "range": {
                    "start": {"snippet": "## A"},
                    "end": {"snippet": "end a"},
                },
            },
            {
                "id": "child-b",
                "name": "B",
                "range": {
                    "start": {"snippet": "## B"},
                    "end": {"snippet": "tail line"},
                },
            },
        ],
        "links": [],
    }
    body = (
        "# Parent\n\n"
        "intro [[mdp]] here.\n\n"
        "## A\n\n"
        "end a\n\n"
        "gap between children.\n\n"
        "## B\n\n"
        "tail line\n"
    )
    resolve = build_target_kp_resolver(str(EXAMPLES))
    sync = sync_file_sidecar_links("x.md", body, sidecar, resolve_target_kp=resolve)
    assert sync["skipped_outside_kp"] == 0
    assert sync["instances_added"] >= 1
    assert sidecar["links"][0]["source_id"] == "parent"
    kps = resolve_knowledge_points(body, sidecar)
    _, edges = derive_file_graph_edges(
        "x.md", body, sidecar, resolve_target_kp=resolve
    )
    parent_edges = [e for e in edges if e["source_id"] == "parent"]
    assert parent_edges
    assert parent_edges[0]["targets"] == ["mdp"]


def test_sync_applies_extend_hint_in_parent_intro():
    sidecar = {
        "knowledge_points": [
            {
                "id": "attention",
                "name": "注意力",
                "range": {
                    "start": {"snippet": "# 注意力"},
                    "end": {"snippet": "tail"},
                },
            },
            {
                "id": "qkv",
                "name": "QKV",
                "range": {
                    "start": {"snippet": "## QKV"},
                    "end": {"snippet": "qkv end"},
                },
            },
        ],
        "links": [],
    }
    body = "# 注意力\n\nsee [[transformer#extend]] intro.\n\n## QKV\n\nqkv end\n\ntail\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))
    sync = sync_file_sidecar_links("x.md", body, sidecar, resolve_target_kp=resolve)
    assert sync["links_created"] == 1
    assert sidecar["links"][0]["edge_type"] == "extend"
    assert sidecar["links"][0]["source_id"] == "attention"


def test_sync_applies_prerequisite_hint_as_reference():
    sidecar = {
        "knowledge_points": [
            {
                "id": "rl",
                "name": "RL",
                "range": {
                    "start": {"snippet": "# RL"},
                    "end": {"snippet": "tail"},
                },
            }
        ],
        "links": [],
    }
    body = "# RL\n\nsee [[mdp#prerequisite]] intro.\n\ntail\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))
    sync = sync_file_sidecar_links("x.md", body, sidecar, resolve_target_kp=resolve)
    assert sync["links_created"] == 1
    assert sidecar["links"][0]["edge_type"] == "reference"


def test_sync_configured_link_in_parent_gap_without_wikilink():
    sidecar = {
        "knowledge_points": [
            {
                "id": "parent",
                "name": "Parent",
                "range": {
                    "start": {"snippet": "# Parent"},
                    "end": {"snippet": "tail"},
                },
            },
            {
                "id": "child",
                "name": "Child",
                "range": {
                    "start": {"snippet": "## Child"},
                    "end": {"snippet": "child end"},
                },
            },
        ],
        "links": [
            {
                "anchor_text": "mdp",
                "targets": ["mdp"],
                "source_id": "parent",
                "instances": [],
            }
        ],
    }
    body = "# Parent\n\nplain mdp mention in intro.\n\n## Child\n\nchild end\n\ntail\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))
    sync = sync_file_sidecar_links("x.md", body, sidecar, resolve_target_kp=resolve)
    assert sync["instances_added"] >= 1
    assert any(i["line"] == 3 for i in sidecar["links"][0]["instances"])


def test_build_knowledge_base_writes_artifacts(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    md = kb / "a.md"
    md.write_text(
        "---\n"
        "description: test\n"
        "---\n"
        "# Title\n\n"
        "## Section\n\n"
        "Link [[mdp]].\n",
        encoding="utf-8",
    )
    sidecar_dir = kb / ".memoria" / "sidecars"
    sidecar_dir.mkdir(parents=True)
    sidecar_path = sidecar_dir / "a.memoria.yaml"
    sidecar_path.write_text(
        "schema_version: 1\n"
        "file: a.md\n"
        "knowledge_points:\n"
        "  - id: section\n"
        "    name: Section\n"
        "    range:\n"
        "      start:\n"
        "        snippet: '## Section'\n"
        "      end:\n"
        "        snippet: 'Link [[mdp]].'\n"
        "links: []\n",
        encoding="utf-8",
    )
    # copy mdp sidecar into tmp kb is hard; use examples build on EXAMPLES instead
    result = build_knowledge_base(str(EXAMPLES))
    assert result["status"] in ("ok", "partial")
    build_dir = EXAMPLES / ".memoria" / "build"
    assert (build_dir / "graph.json").is_file()
    assert (build_dir / "report.json").is_file()
    report = json.loads((build_dir / "report.json").read_text(encoding="utf-8"))
    assert report["graph"]["nodes"] >= 1


def test_build_navigation_demo_syncs_tongduan():
    result = build_knowledge_base(str(EXAMPLES))
    md = EXAMPLES / "navigation-demo.md"
    sc = load_sidecar_for_md(md, EXAMPLES)
    body, _ = strip_frontmatter(md.read_text(encoding="utf-8"))
    anchors = {ln["anchor_text"] for ln in sc.get("links") or []}
    assert "q-learning" in anchors
    assert "policy-gradient" in anchors
    assert result["graph"]["edges"] >= 1
