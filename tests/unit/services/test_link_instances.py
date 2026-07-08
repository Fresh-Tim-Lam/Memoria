"""link_instances 单元测试。"""

from __future__ import annotations

from memoria.services.link_instances import (
    build_preview_body,
    scan_link_text_matches,
    wrap_plain_on_lines,
)
from memoria.services.link_md import remove_wikilink_on_line


def test_scan_finds_wrapped_and_plain():
    body = "按顺序点击（说明）\n可继续 [[按顺序点]] 在深度 RL。"
    lines = body.split("\n")
    matches = scan_link_text_matches(body, "按顺序点", lines)
    lines_found = {m["line"] for m in matches}
    assert 2 in lines_found
    assert 1 not in lines_found or any(m["line"] == 1 and m.get("is_substring") for m in matches)


def test_scan_substring_marked():
    body = "按顺序点击（每跳一次）"
    matches = scan_link_text_matches(body, "按顺序点", body.split("\n"))
    assert len(matches) == 1
    assert matches[0]["is_substring"] is True


def test_remove_wikilink_on_line():
    body = "第一行\n第二 [[按顺序点]] 行\n第三"
    new, ok = remove_wikilink_on_line(body, "按顺序点", 2)
    assert ok
    assert new == "第一行\n第二 按顺序点 行\n第三"


def test_wrap_plain_on_lines():
    body = "A 按顺序点 B\nC 按顺序点 D"
    new, n = wrap_plain_on_lines(body, "按顺序点", [2])
    assert n == 1
    assert "[[按顺序点]]" in new.split("\n")[1]
    assert "[[按顺序点]]" not in new.split("\n")[0]


def test_preview_body_filters_non_instance():
    body = "L1 [[按顺序点]]\nL2 [[按顺序点]]"
    links = [
        {
            "anchor_text": "按顺序点",
            "targets": ["x"],
            "instances": [{"line": 2, "wrapped": True}],
        }
    ]
    preview = build_preview_body(body, links, body.split("\n"))
    assert preview.startswith("L1 按顺序点")
    assert "[[按顺序点]]" in preview.split("\n")[1]
