from memoria.range.locator import locate_snippet, resolve_range


def test_locate_snippet_with_hint():
    lines = ["alpha", "beta target", "gamma target", "delta"]
    idx, cands = locate_snippet(lines, "target", line_hint=3)
    assert idx == 2
    assert 1 in cands and 2 in cands


def test_resolve_range_forward_end():
    lines = [
        "# Title",
        "para one",
        "## Section",
        "para two",
        "## Next",
    ]
    start = {"snippet": "# Title", "line_hint": 1}
    end = {"snippet": "para one", "line_hint": 2}
    result = resolve_range(lines, start, end)
    assert result["ok"] is True
    assert result["start_line"] == 1
    assert result["end_line"] == 2


def test_resolve_range_end_not_found():
    lines = ["# Title", "content only"]
    start = {"snippet": "# Title", "line_hint": 1}
    end = {"snippet": "missing text", "line_hint": 99}
    result = resolve_range(lines, start, end)
    assert result["ok"] is False
    assert result["error"] == "end_snippet_not_found"
