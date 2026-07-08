"""边类型与图谱收集器测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memoria.graph.collector import collect_graph_data
from memoria.graph.edge_types import (
    EDGE_EXTEND,
    EDGE_REFERENCE,
    edge_props_for_link_target,
    normalize_edge_type,
    normalize_link_edge_type,
    normalize_link_relevance,
    normalize_target_edges,
    normalize_wikilink_edge_hint,
    relevance_for_link,
)
from memoria.services.document import DocumentService
from memoria.storage.sidecar import sidecar_path_for
from memoria.storage.sidecar_validate import validate_sidecar

EXAMPLES = Path(__file__).resolve().parents[3] / "examples"


def test_normalize_edge_type_aliases():
    assert normalize_edge_type("reference") == EDGE_REFERENCE
    assert normalize_edge_type("prerequisite") == EDGE_REFERENCE
    assert normalize_wikilink_edge_hint("extend") == "extend"
    assert normalize_edge_type("invalid") is None


def test_normalize_link_edge_type():
    assert normalize_link_edge_type("extend") == EDGE_EXTEND
    assert normalize_link_edge_type("reference") == EDGE_REFERENCE
    assert normalize_link_edge_type("prerequisite") == EDGE_REFERENCE
    assert normalize_link_edge_type(None) == EDGE_REFERENCE
    assert normalize_link_edge_type("contain") == EDGE_REFERENCE


def test_normalize_link_relevance():
    assert normalize_link_relevance(None, edge_type="reference") == 0.7
    assert normalize_link_relevance(None, edge_type="extend") == 0.6
    assert normalize_link_relevance(0.85) == 0.85
    assert normalize_link_relevance(1.5) == 1.0
    assert normalize_link_relevance(-0.1) == 0.0
    assert normalize_link_relevance("bad", edge_type="extend") == 0.6


def test_relevance_for_link():
    assert relevance_for_link({"edge_type": "extend", "relevance": 0.42}) == 0.42
    assert relevance_for_link({"edge_type": "reference"}) == 0.7


def test_normalize_target_edges():
    link = {"edge_type": "reference", "relevance": 0.8}
    out = normalize_target_edges(None, target_ids=["a", "b"], link=link)
    assert out["a"]["relevance"] == 0.8
    assert out["b"]["edge_type"] == EDGE_REFERENCE


def test_edge_props_for_link_target():
    link = {
        "edge_type": "reference",
        "relevance": 0.5,
        "target_edges": {
            "b": {"edge_type": "extend", "relevance": 0.42},
        },
    }
    assert edge_props_for_link_target(link, "b") == (EDGE_EXTEND, 0.42)
    assert edge_props_for_link_target(link, "x") == (EDGE_REFERENCE, 0.5)


def test_validate_sidecar_edges_structure():
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {
                "id": "a",
                "name": "A",
                "range": {"start": {"snippet": "x"}, "end": {"snippet": "y"}},
            }
        ],
        "edges": [
            {
                "type": "prerequisite",
                "source_id": "a",
                "targets": ["b"],
                "relevance": 0.9,
            }
        ],
    }
    v = validate_sidecar(data, "a.md", known_kp_ids={"a", "b"})
    assert v["ok"] is True
    assert any("归一化" in w for w in v["warnings"])


def test_validate_sidecar_edges_unknown_target():
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {
                "id": "a",
                "name": "A",
                "range": {"start": {"snippet": "x"}, "end": {"snippet": "y"}},
            }
        ],
        "edges": [{"type": "reference", "source_id": "a", "targets": ["missing"]}],
    }
    v = validate_sidecar(data, "a.md", known_kp_ids={"a"})
    assert v["ok"] is False
    assert any("target 不存在" in e for e in v["errors"])


@pytest.fixture
def svc() -> DocumentService:
    s = DocumentService()
    s.set_kb_path(str(EXAMPLES))
    return s


def test_collect_graph_data_derives_from_links_not_sidecar_edges():
    data = collect_graph_data(str(EXAMPLES))
    assert data["status"] == "ok"
    nav_edges = [
        e
        for e in data["edges"]
        if e.get("file") == "navigation-demo.md"
        and e.get("origin") == "link"
        and e["targets"] == ["mdp"]
    ]
    assert any(e["type"] == EDGE_REFERENCE and e["source_id"] == "多跳链路" for e in nav_edges)
    assert all(e.get("derived") for e in nav_edges)


def test_get_graph_data_via_service(svc: DocumentService):
    data = svc.get_graph_data()
    assert data["status"] == "ok"
    assert len(data["nodes"]) >= 10
    assert isinstance(data["edges"], list)


def test_knowledge_sidecar_mirror_path():
    md = EXAMPLES / "knowledge" / "rl-overview.md"
    sc = sidecar_path_for(md, EXAMPLES)
    assert sc.replace("\\", "/").endswith(
        ".memoria/sidecars/knowledge/rl-overview.memoria.yaml"
    )
