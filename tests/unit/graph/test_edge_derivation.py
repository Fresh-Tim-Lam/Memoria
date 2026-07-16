"""边推导：range 包含、链接归属、collector 集成。"""

from __future__ import annotations

from pathlib import Path

from memoria.graph.collector import collect_graph_data
from memoria.graph.edge_derivation import (
    KpRange,
    build_target_kp_resolver,
    derive_file_graph_edges,
    derive_link_edges,
    kp_ranges_from_resolved,
    line_in_any_kp,
    minimal_kps_for_line,
    sources_for_link_instance,
    strictly_contains,
)
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.sidecar import load_sidecar_for_md

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


def _derive(rel: str, body: str, sidecar: dict | None) -> tuple[list[dict], list[dict], list[dict]]:
    resolve = build_target_kp_resolver(str(EXAMPLES))
    return derive_file_graph_edges(rel, body, sidecar, resolve_target_kp=resolve)


def test_strictly_contains():
    outer = KpRange("a", 1, 100)
    inner = KpRange("b", 10, 50)
    cross_a = KpRange("c", 40, 80)
    cross_b = KpRange("d", 60, 90)
    assert strictly_contains(outer, inner)
    assert not strictly_contains(inner, outer)
    assert not strictly_contains(cross_a, cross_b)


def test_minimal_kps_nested():
    ranges = [
        KpRange("parent", 3, 68),
        KpRange("child", 9, 27),
        KpRange("other", 29, 68),
    ]
    assert minimal_kps_for_line(20, ranges) == ["child"]
    assert minimal_kps_for_line(5, ranges) == ["parent"]
    assert minimal_kps_for_line(35, ranges) == ["other"]


def test_minimal_kps_partial_overlap():
    ranges = [
        KpRange("a", 10, 30),
        KpRange("b", 25, 40),
    ]
    assert set(minimal_kps_for_line(27, ranges)) == {"a", "b"}


def test_parent_only_gap_uses_parent_kp():
    ranges = [
        KpRange("parent", 1, 20),
        KpRange("child-a", 5, 8),
        KpRange("child-b", 12, 15),
    ]
    assert line_in_any_kp(10, ranges)
    assert minimal_kps_for_line(10, ranges) == ["parent"]


def test_sources_for_link_instance_respects_source_id_in_parent_gap():
    ranges = [
        KpRange("child", 9, 66),
    ]
    link = {
        "anchor_text": "transformer",
        "targets": ["transformer"],
        "source_id": "attention",
        "instances": [{"line": 7, "wrapped": True}],
    }
    assert sources_for_link_instance(7, ranges, link) == []


def test_derive_parent_intro_link_edge():
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
        "links": [
            {
                "anchor_text": "transformer",
                "targets": ["transformer"],
                "edge_type": "extend",
                "source_id": "attention",
                "instances": [{"line": 3, "wrapped": True}],
            }
        ],
    }
    body = "# 注意力\n\n[[transformer#extend]] here.\n\n## QKV\n\nqkv end\n\ntail\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))
    _, edges, _se = derive_file_graph_edges("x.md", body, sidecar, resolve_target_kp=resolve)
    assert len(edges) == 1
    assert edges[0]["source_id"] == "attention"
    assert edges[0]["type"] == "extend"


def test_derive_contain_mdp():
    md = EXAMPLES / "mdp.md"
    sc = load_sidecar_for_md(md, EXAMPLES)
    body, _ = strip_frontmatter(md.read_text(encoding="utf-8"))
    contain, _, _ = _derive("mdp.md", body, sc)
    pairs = {(e["source_id"], e["targets"][0]) for e in contain}
    assert ("mdp", "核心要素") in pairs
    assert ("mdp", "贝尔曼方程") in pairs


def test_wikilink_extend_in_body_not_used_for_graph():
    """derive 不读正文 #extend；未配置 sidecar edge_type 时默认 reference。"""
    sidecar = {
        "knowledge_points": [
            {
                "id": "src",
                "name": "Src",
                "range": {
                    "start": {"snippet": "start"},
                    "end": {"snippet": "end"},
                },
            }
        ],
        "links": [
            {
                "anchor_text": "tgt",
                "targets": ["mdp"],
                "instances": [{"line": 2, "wrapped": True}],
            }
        ],
    }
    body = "start\n[[tgt#extend]] here\nend\n"
    _, link_edges, _ = _derive("x.md", body, sidecar)
    assert len(link_edges) == 1
    assert link_edges[0]["type"] == "reference"


def test_link_edge_type_from_sidecar():
    sidecar = {
        "knowledge_points": [
            {
                "id": "src",
                "name": "Src",
                "range": {
                    "start": {"snippet": "start"},
                    "end": {"snippet": "end"},
                },
            }
        ],
        "links": [
            {
                "anchor_text": "link",
                "targets": ["tgt"],
                "edge_type": "extend",
                "instances": [{"line": 2, "wrapped": True}],
            }
        ],
    }
    body = "start\nlink here\nend\n"
    resolve = build_target_kp_resolver(str(EXAMPLES))

    def resolve_with_tgt(raw: str) -> str | None:
        if raw == "tgt":
            return "tgt"
        return resolve(raw)

    from memoria.graph.edge_derivation import derive_link_edges
    from memoria.services.kp_resolver import resolve_knowledge_points

    kps = resolve_knowledge_points(body, sidecar)
    edges = derive_link_edges(
        "x.md", body, sidecar, kps, resolve_target_kp=resolve_with_tgt
    )
    assert len(edges) == 1
    assert edges[0]["type"] == "extend"
    assert edges[0]["source_id"] == "src"
    assert edges[0]["targets"] == ["tgt"]


def test_derive_link_edges_uses_custom_relevance():
    sidecar = {
        "knowledge_points": [
            {
                "id": "src",
                "name": "Src",
                "range": {
                    "start": {"snippet": "start"},
                    "end": {"snippet": "end"},
                },
            }
        ],
        "links": [
            {
                "anchor_text": "link",
                "targets": ["tgt"],
                "edge_type": "reference",
                "target_edges": {
                    "tgt": {"edge_type": "reference", "relevance": 0.42},
                },
                "instances": [{"line": 2, "wrapped": True}],
            }
        ],
    }
    body = "start\nlink here\nend\n"

    def resolve_with_tgt(raw: str) -> str | None:
        return "tgt" if raw == "tgt" else None

    from memoria.services.kp_resolver import resolve_knowledge_points

    kps = resolve_knowledge_points(body, sidecar)
    edges = derive_link_edges(
        "x.md", body, sidecar, kps, resolve_target_kp=resolve_with_tgt
    )
    assert len(edges) == 1
    assert edges[0]["relevance"] == 0.42


def test_derive_link_edges_per_target_relevance():
    sidecar = {
        "knowledge_points": [
            {
                "id": "src",
                "name": "Src",
                "range": {
                    "start": {"snippet": "start"},
                    "end": {"snippet": "end"},
                },
            }
        ],
        "links": [
            {
                "anchor_text": "link",
                "targets": ["a", "b"],
                "target_edges": {
                    "a": {"edge_type": "reference", "relevance": 0.9},
                    "b": {"edge_type": "extend", "relevance": 0.4},
                },
                "instances": [{"line": 2, "wrapped": True}],
            }
        ],
    }
    body = "start\nlink here\nend\n"

    def resolve(raw: str) -> str | None:
        return raw if raw in ("a", "b") else None

    from memoria.services.kp_resolver import resolve_knowledge_points

    kps = resolve_knowledge_points(body, sidecar)
    edges = derive_link_edges(
        "x.md", body, sidecar, kps, resolve_target_kp=resolve
    )
    by_target = {e["targets"][0]: e for e in edges}
    assert by_target["a"]["relevance"] == 0.9
    assert by_target["a"]["type"] == "reference"
    assert by_target["b"]["relevance"] == 0.4
    assert by_target["b"]["type"] == "extend"


def test_navigation_demo_link_to_mdp_kp():
    md = EXAMPLES / "navigation-demo.md"
    sc = load_sidecar_for_md(md, EXAMPLES)
    body, _ = strip_frontmatter(md.read_text(encoding="utf-8"))
    _, link_edges, _ = _derive("navigation-demo.md", body, sc)
    mdp_links = [
        e
        for e in link_edges
        if e.get("origin") == "link" and e["targets"][0] == "mdp"
    ]
    assert mdp_links
    assert any(e["source_id"] == "多跳链路" for e in mdp_links)


def test_link_outside_kp_range_is_ignored():
    """行号超出文档 KP 覆盖末尾时不建边。"""
    sidecar = {
        "knowledge_points": [
            {
                "id": "a",
                "name": "A",
                "range": {
                    "start": {"snippet": "start"},
                    "end": {"snippet": "end"},
                },
            }
        ],
        "links": [
            {
                "anchor_text": "orphan",
                "targets": ["b"],
                "source_id": "a",
                "instances": [{"line": 99, "wrapped": True}],
            }
        ],
    }
    body = "start\nmiddle\nend\n"
    _, link_edges, _ = _derive("x.md", body, sidecar)
    assert link_edges == []


def test_preamble_wikilink_without_kp_range_skipped():
    sidecar = {
        "knowledge_points": [
            {
                "id": "section-a",
                "name": "A",
                "range": {
                    "start": {"snippet": "## A"},
                    "end": {"snippet": "end a"},
                },
            }
        ],
    }
    body = "# Title\n\nSee [[mdp#extend]] here.\n\n## A\n\nend a\n"
    _, link_edges, _ = _derive("intro.md", body, sidecar)
    assert link_edges == []


def test_file_stem_wikilink_without_kp_id_skipped():
    md = EXAMPLES / "bert.md"
    sc = load_sidecar_for_md(md, EXAMPLES)
    body, _ = strip_frontmatter(md.read_text(encoding="utf-8"))
    _, link_edges, _ = _derive("bert.md", body, sc)
    bad = [e for e in link_edges if e["targets"][0] == "自注意力机制"]
    assert bad == []


def test_file_stem_target_when_kp_id_matches_stem():
    resolve = build_target_kp_resolver(str(EXAMPLES))
    assert resolve("mdp") == "mdp"
    assert resolve("transformer") == "transformer"
    assert resolve("q-learning") == "q-learning"
    assert resolve("attention") == "attention"
    # 仅有文件 stem、无同名 KP 时仍不解析
    assert resolve("hahahah") is None


def test_collect_graph_data_resolved_targets():
    data = collect_graph_data(str(EXAMPLES))
    node_ids = {n["id"] for n in data["nodes"]}
    dangling = [
        e
        for e in data["edges"]
        if e.get("source_id") not in node_ids
        or any(t not in node_ids for t in e.get("targets") or [])
    ]
    assert not dangling


def test_collect_graph_data_has_derived_edges():
    data = collect_graph_data(str(EXAMPLES))
    assert data["status"] == "ok"
    derived = [e for e in data["edges"] if e.get("derived")]
    assert len(derived) >= 5
    assert any(e["type"] == "contain" for e in derived)
    assert any(e["type"] == "reference" for e in derived)
