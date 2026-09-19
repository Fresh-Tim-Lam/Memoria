# 配套单测：被测调用面语义移植自 deepseek-harness packages/session-query/session-query
# 的 extraction.ts + filters.ts（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""会话检索（M2）离线单测：不联网、不写知识库正文。

覆盖：
① 语义文本抽取的规则表（哪些事件贡献文本、结构性/未知事件为空、`compaction` 取摘要）；
② 字面量匹配（转义防注入 / 空白弹性 / 大小写不敏感 / Unicode / 空查询报错）；
③ 命中摘要窗口（截断补省略号、空白折叠、无匹配时按开头截断）；
④ 会话内检索（文本命中、类型白名单 OR、seq/time 区间、单页上限、坏 id / 缺失文件）；
⑤ 跨会话检索（按会话分组、`best` = 最小 seq、`hit_count`、`title`/`turn_count`、
   组间按 `modified_at` 倒序、`sessions_limit` 上限）；
⑥ 有界化参数 fail loud（负数 / 非整数）；字节预筛不影响正确性（ASCII 大小写差异仍命中）。
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.session.history import (
    ASSISTANT_MESSAGE,
    COMPACTION,
    TOOL_CALL,
    TOOL_RESULT,
    USER_MESSAGE,
)
from memoria.services.agent.session.query import (
    DEFAULT_HIT_LIMIT,
    MAX_HIT_LIMIT,
    SNIPPET_ELLIPSIS,
    SessionQueryError,
    compile_text_pattern,
    event_text,
    search_session,
    search_sessions,
    snippet,
)
from memoria.services.agent.session.store import SessionStore
from memoria.services.agent.tools import (
    INVALID_ARGUMENTS_CODE,
    KB_TOOL_NAMES,
    ToolRegistry,
    build_kb_tools,
)

# —— 辅助 ——


def _event(kind: str, data: dict[str, Any], *, seq: int = 0, time: int = 1_700_000_000_000) -> dict[str, Any]:
    return {"v": 1, "seq": seq, "time": time, "type": kind, "data": data}


def _session(root: Path, session_id: str, events: Sequence[tuple[str, dict[str, Any]]]) -> SessionStore:
    store = SessionStore(str(root), session_id)
    for kind, data in events:
        store.append(kind, data)
    store.flush()
    return store


# —— ① 语义文本抽取 ——


def test_event_text_covers_semantic_events_only() -> None:
    assert event_text(_event(USER_MESSAGE, {"text": "  你好 世界  "})) == "你好 世界"
    assert event_text(_event(ASSISTANT_MESSAGE, {"content": "答案"})) == "答案"
    assert event_text(_event(TOOL_RESULT, {"content": "检索结果"})) == "检索结果"
    # assistant 的 tool_calls 也贡献文本（name + arguments，上游 blockText 的 tool-call 分支）
    assistant = _event(
        ASSISTANT_MESSAGE,
        {"content": "让我查一下", "tool_calls": [{"id": "c1", "name": "search_kb", "arguments": '{"query":"梯度"}'}]},
    )
    text = event_text(assistant)
    assert "让我查一下" in text and "search_kb" in text and "梯度" in text


def test_event_text_is_empty_for_structural_and_unknown_events() -> None:
    for kind in (TOOL_CALL, "step/start", "step/error", "loop/end"):
        assert event_text(_event(kind, {"text": "不该被检索", "content": "也不该"})) == ""
    # 未知事件不因载荷里恰好有字符串就变成可检索（上游口径）
    assert event_text(_event("some/unknown", {"text": "字符串"})) == ""


def test_event_text_reads_compaction_summary() -> None:
    """本地扩展：被压缩的旧对话只剩摘要，必须仍可检索。"""
    assert event_text(_event(COMPACTION, {"summary": "## 待办\n- 修 P06", "shadowed": [0, 1]})) == "## 待办\n- 修 P06"


def test_event_text_joins_and_drops_empty_parts() -> None:
    assert event_text(_event(ASSISTANT_MESSAGE, {"content": "   ", "tool_calls": []})) == ""
    joined = event_text(_event(ASSISTANT_MESSAGE, {"content": "a", "tool_calls": [{"name": "", "arguments": "b"}]}))
    assert joined == "a\nb"


# —— ② 字面量匹配 ——


def test_compile_text_pattern_is_literal_and_whitespace_flexible() -> None:
    pattern = compile_text_pattern("a.b")
    assert pattern.search("xa.bx") is not None
    assert pattern.search("axb") is None, "正则元字符必须被转义（点号不是通配）"

    flexible = compile_text_pattern("梯度   下降")
    assert flexible.search("梯度\n\n下降") is not None, "词间空白弹性（含换行）"
    assert flexible.search("梯度下降") is None, "词间至少要有一个空白"


def test_compile_text_pattern_is_case_insensitive_and_unicode() -> None:
    pattern = compile_text_pattern("MLP")
    assert pattern.search("mlp 由多层组成") is not None
    assert compile_text_pattern("感知机").search("多层感知机") is not None


def test_compile_text_pattern_rejects_blank_query() -> None:
    for bad in ("", "   ", "\n\t"):
        with pytest.raises(SessionQueryError):
            compile_text_pattern(bad)


def test_compile_text_pattern_resists_regex_injection() -> None:
    """查询永远是数据：`.*` 之类不得变成通配。"""
    pattern = compile_text_pattern(".*")
    assert pattern.search("这里没有那两个字符") is None
    assert pattern.search("字面量 .* 出现") is not None


# —— ③ 命中摘要 ——


def test_snippet_windows_around_match_and_marks_truncation() -> None:
    body = "前" * 200 + "关键词" + "后" * 200
    pattern = compile_text_pattern("关键词")
    out = snippet(body, pattern, width=10)
    assert "关键词" in out
    assert out.startswith(SNIPPET_ELLIPSIS) and out.endswith(SNIPPET_ELLIPSIS)
    assert len(out) < len(body)


def test_snippet_without_truncation_has_no_ellipsis() -> None:
    pattern = compile_text_pattern("关键词")
    assert snippet("关键词", pattern) == "关键词"


def test_snippet_folds_whitespace() -> None:
    pattern = compile_text_pattern("a b")
    assert "\n" not in snippet("a\n   b", pattern)


# —— ④ 会话内检索 ——


def _kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / ".memoria" / "agent").mkdir(parents=True, exist_ok=True)
    return root


def test_search_session_finds_text_hits_in_seq_order(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(
        root,
        "s1",
        [
            (USER_MESSAGE, {"text": "梯度下降是什么"}),
            (ASSISTANT_MESSAGE, {"content": "梯度下降是一种优化方法"}),
            (USER_MESSAGE, {"text": "那学习率呢"}),
        ],
    )
    hits = search_session(str(root), "s1", "梯度")
    assert [hit.seq for hit in hits] == [0, 1]
    assert all("梯度" in hit.snippet for hit in hits)
    assert {hit.type for hit in hits} == {USER_MESSAGE, ASSISTANT_MESSAGE}


def test_search_session_type_filter_is_or_within_clause(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(
        root,
        "s2",
        [
            (USER_MESSAGE, {"text": "梯度"}),
            (ASSISTANT_MESSAGE, {"content": "梯度"}),
            (TOOL_RESULT, {"content": "梯度"}),
        ],
    )
    only_tool = search_session(str(root), "s2", "梯度", types=[TOOL_RESULT])
    assert [hit.seq for hit in only_tool] == [2]
    both = search_session(str(root), "s2", "梯度", types=[USER_MESSAGE, TOOL_RESULT])
    assert [hit.seq for hit in both] == [0, 2]


def test_search_session_range_filters(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    store = SessionStore(str(root), "s3")
    store.append(USER_MESSAGE, {"text": "梯度"})
    store.append(USER_MESSAGE, {"text": "梯度"})
    store.append(USER_MESSAGE, {"text": "梯度"})
    store.flush()
    assert [hit.seq for hit in search_session(str(root), "s3", "梯度", seq_from=1)] == [1, 2]
    assert [hit.seq for hit in search_session(str(root), "s3", "梯度", seq_to=1)] == [0, 1]
    assert [hit.seq for hit in search_session(str(root), "s3", "梯度", seq_from=1, seq_to=1)] == [1]
    # time 区间：全部事件同一毫秒，给一个必然落空的区间
    assert search_session(str(root), "s3", "梯度", time_from=1, time_to=2) == []


def test_search_session_respects_limit(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    store = SessionStore(str(root), "s4")
    for _ in range(5):
        store.append(USER_MESSAGE, {"text": "梯度"})
    store.flush()
    assert len(search_session(str(root), "s4", "梯度", limit=2)) == 2
    assert len(search_session(str(root), "s4", "梯度", limit=MAX_HIT_LIMIT + 100)) == 5
    assert search_session(str(root), "s4", "梯度", limit=0) == []


def test_search_session_missing_session_is_empty(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    assert search_session(str(root), "nope", "梯度") == []


def test_search_session_rejects_bad_limits_and_ids(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    with pytest.raises(SessionQueryError):
        search_session(str(root), "s5", "梯度", limit=-1)
    with pytest.raises(SessionQueryError):
        search_session(str(root), "s5", "梯度", limit="20")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        search_session(str(root), "../escape", "梯度")


# —— ⑤ 跨会话检索 ——


def test_search_sessions_groups_and_orders_by_recency(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "old", [(USER_MESSAGE, {"text": "梯度 旧"})])
    _session(root, "new", [(USER_MESSAGE, {"text": "梯度 新"}), (ASSISTANT_MESSAGE, {"content": "梯度 新答"})])
    # 显式设置 mtime，避免同秒写入导致顺序不稳定
    sessions = root / ".memoria" / "agent" / "sessions"
    os.utime(sessions / "old.jsonl", (1_600_000_000, 1_600_000_000))
    os.utime(sessions / "new.jsonl", (1_700_000_000, 1_700_000_000))

    groups = search_sessions(str(root), "梯度")
    assert [group.session_id for group in groups] == ["new", "old"]
    newest = groups[0]
    assert newest.title == "梯度 新"
    assert newest.turn_count == 1
    assert newest.hit_count == 2
    assert newest.best.seq == 0, "best = 该会话内 seq 最小的一条"
    assert newest.best.session_id == "new"
    assert groups[1].hit_count == 1


def test_search_sessions_honours_sessions_limit(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    for index in range(3):
        _session(root, f"q{index}", [(USER_MESSAGE, {"text": "梯度"})])
    assert len(search_sessions(str(root), "梯度", sessions_limit=2)) == 2
    assert len(search_sessions(str(root), "梯度", sessions_limit=99)) == 3


def test_search_sessions_returns_empty_when_no_hit(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "s9", [(USER_MESSAGE, {"text": "完全无关的内容"})])
    assert search_sessions(str(root), "梯度") == []
    # 没开库 / 没有会话目录
    assert search_sessions(str(tmp_path / "empty-kb"), "梯度") == []


def test_search_sessions_hit_limit_per_session(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    store = SessionStore(str(root), "many")
    for _ in range(4):
        store.append(USER_MESSAGE, {"text": "梯度"})
    store.flush()
    groups = search_sessions(str(root), "梯度", hit_limit=2)
    assert groups[0].hit_count == 2, "每会话命中数受 hit_limit 约束"


# —— ⑥ 字节预筛 ——


def test_ascii_case_difference_survives_byte_prefilter(tmp_path: Path) -> None:
    """预筛是 ASCII 小写化的字节比对，故查询大小写与正文不同也要命中。"""
    root = _kb(tmp_path)
    _session(root, "case", [(USER_MESSAGE, {"text": "Hello World"})])
    assert [hit.seq for hit in search_session(str(root), "case", "HELLO")] == [0]
    assert [hit.seq for hit in search_session(str(root), "case", "hello world")] == [0]


def test_default_hit_limit_is_bounded() -> None:
    assert 0 < DEFAULT_HIT_LIMIT <= MAX_HIT_LIMIT


# —— ⑦ 工具面（对应上游 tool-session-query）——


def test_kb_tool_names_match_built_tools(tmp_path: Path) -> None:
    """`KB_TOOL_NAMES` 必须与实际注册的工具集逐字一致（防止两边漂移）。"""
    root = _kb(tmp_path)
    assert tuple(tool.name for tool in build_kb_tools(str(root))) == KB_TOOL_NAMES
    assert "search_sessions" in KB_TOOL_NAMES


def test_search_sessions_tool_is_read_only_and_labels_sessions(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "tool-s", [(USER_MESSAGE, {"text": "我们上次讨论过梯度下降"})])
    tool = ToolRegistry(build_kb_tools(str(root))).get("search_sessions")
    assert tool is not None and tool.read_only

    out = tool.handler({"query": "梯度下降"})
    assert not out.error
    assert "会话 tool-s" in out.text
    assert "梯度下降" in out.text
    # 会话命中不是文档出处：不得出现 `文件:行号` 形状的锚点
    assert out.anchors == ()
    assert ":1" not in out.text


def test_search_sessions_tool_rejects_empty_query(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    tool = ToolRegistry(build_kb_tools(str(root))).get("search_sessions")
    out = tool.handler({"query": "   "})
    assert out.error and out.code == INVALID_ARGUMENTS_CODE


def test_search_sessions_tool_hints_when_nothing_matches(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "tool-none", [(USER_MESSAGE, {"text": "完全无关"})])
    tool = ToolRegistry(build_kb_tools(str(root))).get("search_sessions")
    out = tool.handler({"query": "梯度"})
    assert not out.error
    assert "不是知识库文档" in out.text and "search_kb" in out.text


def test_search_sessions_tool_respects_limit(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    for index in range(4):
        _session(root, f"lim{index}", [(USER_MESSAGE, {"text": "梯度"})])
    sessions = root / ".memoria" / "agent" / "sessions"
    for index in range(4):
        os.utime(sessions / f"lim{index}.jsonl", (1_600_000_000 + index, 1_600_000_000 + index))
    tool = ToolRegistry(build_kb_tools(str(root))).get("search_sessions")
    out = tool.handler({"query": "梯度", "limit": 2})
    assert out.text.count("## 会话 ") == 2
    # 非法 limit 退回默认值，而不是炸掉工具
    assert tool.handler({"query": "梯度", "limit": "abc"}).error is False
