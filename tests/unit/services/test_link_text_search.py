"""link_text_search 单元测试。"""

from __future__ import annotations

from memoria.services.link_text_search import (
    LinkTextSearchOptions,
    build_search_view,
    resolve_canonical_anchor,
    scan_link_text_matches,
    score_anchor_suggestion,
    suggest_link_anchor_texts,
)

NAV_LINE = (
    "连续动作空间方法常同时涉及 [[q-learning]] 与 [[policy-gradient]] 两类思想；"
    "可继续点 [[ddpg]] 按顺序点在[[深度]] RL 中的结合。"
)


def test_fuzzy_whitespace_matches_spaced_text():
    body = "导航到深度 RL 章节\n其他深度RL内容"
    lines = body.split("\n")
    opts = {"fuzzy_whitespace": True}
    matches = scan_link_text_matches(body, "深度RL", lines, search_options=opts)
    m1 = next(m for m in matches if m["line"] == 1)
    assert m1["matched_text"] == "深度 RL"
    assert m1.get("fuzzy") is True
    assert not m1.get("is_substring")
    m2 = next(m for m in matches if m["line"] == 2)
    assert m2.get("is_substring") is True


def test_latin_acronym_before_cjk_suffix_is_plain():
    body = "## 第四层：引入SVD技巧（核心）\n> **特征人脸法 = PCA + SVD技巧 + 投影**"
    lines = body.split("\n")
    matches = scan_link_text_matches(body, "SVD", lines)
    for ln in (1, 2):
        m = next(x for x in matches if x["line"] == ln)
        assert m["matched_text"] == "SVD"
        assert not m.get("is_substring")


def test_latin_acronym_inside_larger_latin_token_stays_substring():
    body = "ASVD技巧"
    lines = body.split("\n")
    matches = scan_link_text_matches(body, "SVD", lines)
    assert matches
    assert all(m.get("is_substring") for m in matches)


def test_cjk_anchor_before_cjk_suffix_is_plain_not_substring():
    body = "而不管智能体实际遵循什么策略。\n"
    lines = body.split("\n")
    matches = scan_link_text_matches(
        body, "智能体", lines, search_options={"fuzzy_whitespace": True}
    )
    m = next(x for x in matches if x["line"] == 1)
    assert m["matched_text"] == "智能体"
    assert not m.get("is_substring")


def test_cjk_phrase_before_next_word_is_plain():
    body = "连续动作空间方法常同时涉及两类思想。\n"
    lines = body.split("\n")
    matches = scan_link_text_matches(
        body, "动作空间", lines, search_options={"fuzzy_whitespace": True}
    )
    m = next(x for x in matches if x["line"] == 1)
    assert m["matched_text"] == "动作空间"
    assert not m.get("is_substring")


def test_exact_without_fuzzy_whitespace():
    body = "深度 RL 章节"
    lines = body.split("\n")
    exact = scan_link_text_matches(body, "深度RL", lines, search_options={"fuzzy_whitespace": False})
    assert not any(m["line"] == 1 and not m.get("is_substring") for m in exact)


def test_suggest_recommends_sidecar_anchor():
    body = "## 深度 RL\n正文"
    links = [{"anchor_text": "深度 RL", "targets": ["x"]}]
    suggestions = suggest_link_anchor_texts(
        body,
        "深durl",
        links,
        search_options={"fuzzy_suggest": True},
    )
    texts = [s["text"] for s in suggestions]
    assert "深度 RL" in texts


def test_score_compact_prefix():
    opts = LinkTextSearchOptions(fuzzy_whitespace=True, fuzzy_suggest=True)
    assert score_anchor_suggestion("深度RL", "深度 RL", options=opts) >= 0.9


def test_search_ignores_other_wikilinks():
    lines = [NAV_LINE]
    matches = scan_link_text_matches(NAV_LINE, "policy", lines)
    assert not matches


def test_search_unwraps_current_strips_foreign():
    lines = [NAV_LINE]
    depth_entry = {"anchor_text": "深度", "instances": [{"line": 1, "wrapped": True}]}
    depth = scan_link_text_matches(
        NAV_LINE, "深度", lines, link_entry=depth_entry
    )
    assert len(depth) == 1
    assert depth[0]["matched_text"] == "深度"
    assert depth[0]["wrapped"] is True

    ddpg = scan_link_text_matches(NAV_LINE, "ddpg", lines)
    assert len(ddpg) == 1
    assert ddpg[0]["matched_text"] == "ddpg"
    assert ddpg[0]["wrapped"] is True

    seq = scan_link_text_matches(NAV_LINE, "按顺序点", lines)
    assert len(seq) == 1
    assert seq[0]["matched_text"] == "按顺序点"
    assert not seq[0].get("wrapped")


def test_depth_rl_matches_across_current_wikilink():
    lines = [NAV_LINE]
    entry = {"anchor_text": "深度", "instances": [{"line": 1, "wrapped": True}]}
    opts = {"fuzzy_whitespace": True, "route_anchor": "深度"}
    for anchor in ("深度 RL", "深度RL"):
        matches = scan_link_text_matches(
            NAV_LINE, anchor, lines, link_entry=entry, search_options=opts
        )
        assert len(matches) == 1, anchor
        m = matches[0]
        assert m["matched_text"] == "深度 RL", anchor
        assert not m.get("wrapped")


def test_match_conflict_with_other_link_wikilink():
    body = "见 [[深度 RL]]。\n第二处 [[深度]] RL。"
    lines = body.split("\n")
    depth_entry = {"anchor_text": "深度", "instances": []}
    sidecar = [
        {"anchor_text": "深度", "targets": ["ddpg"]},
        {"anchor_text": "深度 RL", "targets": ["ddpg"]},
    ]
    opts = {"fuzzy_whitespace": True, "route_anchor": "深度"}
    matches = scan_link_text_matches(
        body,
        "深度 RL",
        lines,
        link_entry=depth_entry,
        search_options=opts,
        sidecar_links=sidecar,
    )
    assert len(matches) >= 2
    blocked = [m for m in matches if m.get("blocked")]
    selectable = [m for m in matches if not m.get("blocked") and not m.get("is_substring")]
    assert blocked, "应标记与其它跳转重叠的项"
    assert selectable, "应保留可挂接的 [[深度]] RL 扩展匹配"
    assert blocked[0]["line"] == 1
    assert selectable[0]["line"] == 2


def test_route_anchor_prefers_shorter_entry_when_extending():
    """侧车同时有 深度 与 深度 RL 时，route_anchor=深度 应匹配 [[深度]] RL。"""
    lines = [NAV_LINE]
    sidecar = [
        {"anchor_text": "深度", "targets": ["ddpg"]},
        {"anchor_text": "深度 RL", "targets": ["ddpg"]},
    ]
    opts = {"fuzzy_whitespace": True, "route_anchor": "深度"}
    matches = scan_link_text_matches(
        NAV_LINE,
        "深度 RL",
        lines,
        link_entry={"anchor_text": "深度 RL"},
        search_options=opts,
        sidecar_links=sidecar,
    )
    ok = [m for m in matches if not m.get("blocked")]
    assert ok
    assert ok[0]["matched_text"] == "深度 RL"


def test_resolve_canonical_anchor_prefers_body_text():
    matches = [
        {"line": 1, "matched_text": "深度 RL", "fuzzy": True},
        {"line": 2, "matched_text": "深度RLhahaha", "is_substring": True},
    ]
    assert resolve_canonical_anchor("深度RL", matches, [1]) == "深度 RL"


def test_no_duplicate_wrapped_and_plain_on_same_line():
    anchor = "Deep RL 四座：DDPG / Q-Learning / Policy Gradient / RL 概览"
    row = f"[[{anchor}]]"
    entry = {"anchor_text": anchor, "instances": [{"line": 1, "wrapped": True}]}
    matches = scan_link_text_matches(row, anchor, [row], link_entry=entry)
    assert len(matches) == 1
    assert matches[0]["wrapped"] is True


def test_build_search_view_strips_foreign_unwraps_route():
    row = "A [[other]] B [[target|显示]] C"
    view, _ = build_search_view(
        row,
        "显示",
        options=LinkTextSearchOptions(),
        link_entry={"anchor_text": "target"},
    )
    assert view == "A  B 显示 C"

    depth_view, _ = build_search_view(
        NAV_LINE,
        "深度 RL",
        options=LinkTextSearchOptions(fuzzy_whitespace=True),
        link_entry={"anchor_text": "深度"},
    )
    assert "[[深度]]" not in depth_view
    assert "深度 RL" in depth_view
    assert "ddpg" not in depth_view
    assert "q-learning" not in depth_view

    ddpg_view, _ = build_search_view(
        NAV_LINE,
        "ddpg",
        options=LinkTextSearchOptions(fuzzy_whitespace=True),
        link_entry=None,
    )
    assert "ddpg" in ddpg_view
    assert "[[深度]]" not in ddpg_view
    assert "强化学习概览" not in ddpg_view
