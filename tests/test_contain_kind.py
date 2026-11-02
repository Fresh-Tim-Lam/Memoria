"""`contain_kind`（ontology v0.2）的契约钉子：结构包含 ≠ 语义整体-部分。

来源：人（2026-11-02）「文本上的 contain 不一定真实具有 contain 的语义，所以有必要做一些区分，
别让程序自动一视同仁处理为 contain 边。」批准重开 v0.2：`dec-20261102-3b8e6eb6`。

本文件钉住：
1. 派生层 `derive_contain_edges()` 静态写 `contain_kind="structural"`（不写 sidecar、不猜 semantic）；
2. canonical schema 的跨字段规则：`semantic` 必须带 `assertion_source`；`derived_by=system_range`
   只能是 `structural`；未知取值非法；
3. collect 输出里 33 条 contain 全部 structural（有 frozen 语料时）。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = _ROOT / "docs" / "design" / "kg-edge-provenance.schema.json"
FROZEN = (
    _ROOT
    / "artifacts"
    / "agent"
    / "verify"
    / "debate"
    / "kg-retrieval"
    / "round2"
    / "frozen"
    / "数字通信原理"
)


def _base_edge() -> dict:
    return {
        "type": "contain",
        "source_id": "kp-a",
        "targets": ["kp-b"],
        "relevance": 0.9,
        "derived": True,
        "origin": "range",
        "derived_by": "system_range",
        "generator_version": "contain-v1",
    }


def test_derivation_writes_structural_contain_kind() -> None:
    from memoria.graph.edge_derivation import KpRange, derive_contain_edges

    edges = derive_contain_edges([
        KpRange("a", 1, 100),
        KpRange("b", 10, 20),
        KpRange("c", 30, 40),
    ])
    assert len(edges) == 2
    for edge in edges:
        assert edge["type"] == "contain"
        assert edge["derived_by"] == "system_range"
        assert edge["contain_kind"] == "structural"
        assert "assertion_source" not in edge


@pytest.fixture(scope="module")
def validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def test_schema_accepts_structural(validator) -> None:
    edge = _base_edge()
    edge["contain_kind"] = "structural"
    assert list(validator.iter_errors(edge)) == []


def test_schema_accepts_semantic_with_author_source(validator) -> None:
    edge = _base_edge()
    edge["derived_by"] = "author"
    edge["contain_kind"] = "semantic"
    edge["provenance_state"] = "asserted"
    edge["assertion_source"] = {
        "file": "教材/03_第3章_模拟信号的数字编码.md",
        "line_start": 10,
        "line_end": 12,
        "quote_sha256": "a" * 64,
    }
    assert list(validator.iter_errors(edge)) == []


def test_schema_rejects_semantic_without_source(validator) -> None:
    edge = _base_edge()
    edge["contain_kind"] = "semantic"
    errors = list(validator.iter_errors(edge))
    assert errors, "semantic 无 assertion_source 必须判红"
    assert any("assertion_source" in err.message for err in errors)


def test_schema_rejects_unknown_kind(validator) -> None:
    edge = _base_edge()
    edge["contain_kind"] = "maybe"
    errors = list(validator.iter_errors(edge))
    assert errors


def test_schema_rejects_system_range_semantic(validator) -> None:
    edge = _base_edge()  # derived_by=system_range
    edge["contain_kind"] = "semantic"
    edge["assertion_source"] = {"file": "x.md", "line_start": 1, "line_end": 1, "quote_sha256": "b" * 64}
    errors = list(validator.iter_errors(edge))
    assert errors, "system_range 派生边不得标 semantic"


def test_collect_frozen_contains_are_all_structural() -> None:
    if not FROZEN.is_dir():
        pytest.skip("frozen 语料不在本机（gitignored artifacts）")
    from memoria.graph.collector import collect_graph_data

    data = collect_graph_data(str(FROZEN))
    edges = data.get("edges") or []
    assert len(edges) == 62
    contain = [edge for edge in edges if edge.get("type") == "contain"]
    assert len(contain) == 33
    assert all(edge.get("contain_kind") == "structural" for edge in contain)
    assert all(edge.get("derived_by") == "system_range" for edge in contain)
    # 非 contain 边不得被塞 contain_kind（避免把字段滥用到 link/作者边）
    assert not any(edge.get("contain_kind") for edge in edges if edge.get("type") != "contain")
