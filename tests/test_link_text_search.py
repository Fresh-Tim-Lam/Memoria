"""`link_text_search.scan_link_text_matches` 的**纯文本 span 回归**（产品缺陷修复，2026-09-20）。

**缺陷**：纯文本分支把 **body 绝对偏移**当成**行内**偏移去查 `view_to_orig`，于是返回的
`col` / `matched_text` / `replace_start` **整体右移**，而且 `matched_text` 根本不等于锚文本
——最小复现：行 `前缀文字注意力机制后缀文字。` ⇒ 返回 `col=9, matched_text='后缀文字。'`
（正确应为 `col=4, '注意力机制'`）。下游 `apply_link_instances()` 拿这条 span 去包裹，会把
**正文改坏**（实测曾产出 `注意力机制是核心[[。注意力机]]制也出现在别处。`）——这是**人机 UI
共用**的同一条链路（源码区「选中一行 → 挂链接」同样受影响）。

**修法**：先换算成行内下标再查映射表 —— `row_pos = pos - (body.rfind("\\n", 0, pos) + 1)`
（`link_text_search.py` 纯文本分支；等量替换、行号零漂移）。

本文件是那个修复的**最小复现钉**：三例锚定"返回的 span 必须真的是锚文本"，另加一条通用
不变量（`row[replace_start:replace_end] == matched_text`），今后任何偏移漂移都会当场失败。
"""

from __future__ import annotations

import pytest

from memoria.services.link_text_search import line_matched_spans, scan_link_text_matches

ANCHOR = "注意力机制"

#: (整篇正文, 期望的行内列号列表)——行号都是 3
CASES = [
    ("# T\n\n前缀文字注意力机制后缀文字。\n", [4]),
    ("# T\n\n这里提到注意力机制一次。\n", [4]),
    ("# T\n\n注意力机制是核心。注意力机制也出现在别处。\n", [0, 9]),
    ("# T\n\n注意力机制\n", [0]),  # 独占一行
]


@pytest.mark.parametrize(("body", "expected_cols"), CASES)
def test_plain_spans_are_exact(body: str, expected_cols: list[int]) -> None:
    """返回的 span 必须是**锚文本本身**（列号按行内计），与它在第几行无关。"""
    lines = body.split("\n")
    matches = scan_link_text_matches(body, ANCHOR, lines)
    assert [m["line"] for m in matches] == [3] * len(expected_cols)
    assert [m["col"] for m in matches] == expected_cols
    assert [m["matched_text"] for m in matches] == [ANCHOR] * len(expected_cols)


@pytest.mark.parametrize(("body", "_cols"), CASES)
def test_span_maps_back_onto_the_row(body: str, _cols: list[int]) -> None:
    """通用不变量（本次缺陷会直接违反它）：`row[replace_start:replace_end] == matched_text`。"""
    lines = body.split("\n")
    row = lines[2]
    for m in scan_link_text_matches(body, ANCHOR, lines):
        assert row[m["replace_start"] : m["replace_end"]] == m["matched_text"] == ANCHOR


def test_line_matched_spans_points_at_the_anchor() -> None:
    """下游取用的 `line_matched_spans()` 也必须指到锚文本（它决定 `apply_link_instances` 包哪儿）。"""
    body = "# T\n\n前缀文字注意力机制后缀文字。\n"
    row = body.split("\n")[2]
    spans = line_matched_spans(scan_link_text_matches(body, ANCHOR, body.split("\n")), [3])
    pos, matched, end = spans[3]
    assert row[pos:end] == matched == ANCHOR
