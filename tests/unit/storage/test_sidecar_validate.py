"""侧车校验测试。"""

from memoria.storage.sidecar_validate import validate_sidecar


def test_validate_rejects_duplicate_ids():
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {"id": "x", "name": "A", "range": {"start": {"snippet": "a"}, "end": {"snippet": "b"}}},
            {"id": "x", "name": "B", "range": {"start": {"snippet": "c"}, "end": {"snippet": "d"}}},
        ],
    }
    v = validate_sidecar(data, "a.md")
    assert v["ok"] is False
    assert any("重复" in e for e in v["errors"])


def test_validate_range_relocate_warning():
    lines = ["# Title", "content"]
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [{
            "id": "t",
            "name": "T",
            "range": {
                "start": {"snippet": "# Title", "line_hint": 1},
                "end": {"snippet": "missing", "line_hint": 99},
            },
        }],
    }
    v = validate_sidecar(data, "a.md", lines)
    assert v["ok"] is True
    assert any("无法重定位" in w for w in v["warnings"])


def test_validate_rejects_invalid_edge_type():
    data = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {"id": "a", "name": "A", "range": {"start": {"snippet": "x"}, "end": {"snippet": "y"}}},
        ],
        "edges": [{"type": "depends_on", "source_id": "a", "targets": []}],
    }
    v = validate_sidecar(data, "a.md")
    assert v["ok"] is False
    assert any("无效 type" in e for e in v["errors"])


def test_validate_links_edge_type():
    base = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {"id": "a", "name": "A", "range": {"start": {"snippet": "x"}, "end": {"snippet": "y"}}},
        ],
    }
    ok = validate_sidecar(
        {
            **base,
            "links": [
                {"anchor_text": "t", "targets": ["b"], "edge_type": "extend"},
            ],
        },
        "a.md",
    )
    assert ok["ok"] is True

    bad = validate_sidecar(
        {
            **base,
            "links": [
                {"anchor_text": "t", "targets": ["b"], "edge_type": "contain"},
            ],
        },
        "a.md",
    )
    assert bad["ok"] is False
    assert any("edge_type" in e for e in bad["errors"])
