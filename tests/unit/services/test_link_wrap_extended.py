"""扩展匹配文本包裹（[[深度]] RL → [[深度 RL]]）。"""

from __future__ import annotations

from memoria.services.link_instances import wrap_plain_on_lines
from memoria.services.link_text_search import line_matched_spans, scan_link_text_matches


def test_wrap_replaces_partial_wikilink_span():
    row = "可继续点 [[ddpg]] 按顺序点在[[深度]] RL 中的结合。"
    body = row
    entry = {"anchor_text": "深度", "instances": []}
    matches = scan_link_text_matches(
        body,
        "深度 RL",
        [row],
        link_entry=entry,
        search_options={"fuzzy_whitespace": True, "route_anchor": "深度"},
    )
    assert len(matches) == 1
    spans = line_matched_spans(matches, [1])
    new_body, n = wrap_plain_on_lines(body, "深度 RL", [1], line_spans=spans)
    assert n == 1
    assert "[[深度 RL]]" in new_body
    assert "[[深度]] RL" not in new_body
