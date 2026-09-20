# 配套单测：被测调用面语义移植自 deepseek-harness packages/session-query/session-query 的
# tracing.ts + index.ts（traceSession / traceEvent / readEvent）与
# packages/session-query/tool-session-query 的 index.ts + presentation.ts（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""会话查询家族其余四工具（事件检索 / 会话谱系 / 事件溯源 / 事件精读）的离线单测。

覆盖：
① 有界化常量与上游一致（`before`/`after` ≤ 50、命中上限 100）且与 `pruner.PRUNE` 同值；
② `read_event`（窗口夹紧、默认仅目标、越界/非法窗口/缺失目标与缺失会话）；
③ `trace_event`（compaction / compaction/prune 的替换关系、替换链、后写覆盖；引用关系恒 `None`）；
④ `session_lineage`（根会话、父链、后代树、未解析父会话、成环、缺失目标）；
⑤ 四个工具的模型可见文本（命中/片段/上限提示/完整 JSON/相邻摘要/谱系/替换关系）；
⑥ 工具注册与 `read_only`、schema 必填与上限、参数错误 fail-closed（`INVALID_ARGUMENTS`）、
   目标缺失 `NOT_FOUND`、坏作用域（目录穿越）不静默返回空。
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.llm.types import ToolCall
from memoria.services.agent.pruner import PRUNE
from memoria.services.agent.session.history import (
    ASSISTANT_MESSAGE,
    COMPACTION,
    TOOL_CALL,
    TOOL_RESULT,
    USER_MESSAGE,
)
from memoria.services.agent.session.query import (
    DEFAULT_SEARCH_RESULT_LIMIT,
    MAX_READ_WINDOW,
    REPLACEMENT_TYPES,
    SessionQueryError,
    SessionQueryNotFound,
    read_event,
    require_session,
    session_lineage,
    trace_event,
)
from memoria.services.agent.session.store import SessionStore
from memoria.services.agent.tools import (
    INVALID_ARGUMENTS_CODE,
    KB_TOOL_NAMES,
    Tool,
    ToolRegistry,
    build_kb_tools,
)

SESSION_TOOLS = ("session_event_search", "session_trace", "session_event_trace", "session_event_read")
NOT_FOUND_CODE = "NOT_FOUND"

# —— 辅助 ——


def _kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / ".memoria" / "agent").mkdir(parents=True, exist_ok=True)
    return root


def _session(
    root: Path,
    session_id: str,
    events: Sequence[tuple[str, dict[str, Any]]],
    *,
    parent: str | None = None,
) -> SessionStore:
    extra = {"parentSession": parent} if parent else {}
    store = SessionStore(str(root), session_id, header_extra=extra)
    for kind, data in events:
        store.append(kind, data)
    store.flush()
    return store


def _tool(root: Path, name: str) -> Tool:
    tool = ToolRegistry(build_kb_tools(str(root))).get(name)
    assert tool is not None, name
    return tool


def _turns(*texts: str) -> list[tuple[str, dict[str, Any]]]:
    return [(USER_MESSAGE, {"text": text}) for text in texts]


def _mixed_session(root: Path, session_id: str = "trace-s1") -> SessionStore:
    """若干轮 + 一条工具调用：既有语义文本事件，也有一条结构性（无语义文本）事件。"""
    return _session(
        root,
        session_id,
        [
            (USER_MESSAGE, {"text": "梯度下降是什么"}),
            (
                ASSISTANT_MESSAGE,
                {"content": "梯度下降是一种优化方法", "tool_calls": [{"id": "c1", "name": "search_kb", "arguments": "{}"}]},
            ),
            (TOOL_CALL, {"id": "c1", "name": "search_kb", "arguments": "{}"}),
            (TOOL_RESULT, {"id": "c1", "name": "search_kb", "content": "命中：梯度下降"}),
            (USER_MESSAGE, {"text": "那学习率呢"}),
            ("loop/end", {"stop_reason": "final-answer"}),
        ],
    )


# —— ① 常量与上游一致 ——


def test_limits_match_upstream_and_pruner() -> None:
    assert MAX_READ_WINDOW == 50, "上游 SESSION_QUERY_READ_WINDOW_MAX（session-query/src/config.ts:6）"
    assert DEFAULT_SEARCH_RESULT_LIMIT == 100, "上游 maxSearchResults 默认值（tool-session-query/src/index.ts:22）"
    assert PRUNE in REPLACEMENT_TYPES, "本地替换关系必须涵盖 compaction/prune（字面量不得漂移）"
    assert COMPACTION in REPLACEMENT_TYPES


def test_tool_cap_equals_upstream_default() -> None:
    from memoria.services.agent.tools.kb import SESSION_EVENT_HITS_CAP

    assert SESSION_EVENT_HITS_CAP == DEFAULT_SEARCH_RESULT_LIMIT


# —— ② `read_event` ——


def test_read_event_window_is_clamped(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "w1", _turns(*[f"第 {index} 轮" for index in range(6)]))

    window = read_event(str(root), "w1", 3, before=1, after=2)
    assert [event["seq"] for event in window.events] == [2, 3, 4, 5]
    assert window.target["seq"] == 3
    assert (window.start_seq, window.end_seq) == (2, 5)

    clipped = read_event(str(root), "w1", 1, before=5, after=1)
    assert [event["seq"] for event in clipped.events] == [0, 1, 2], "左端夹紧到 0"

    assert [event["seq"] for event in read_event(str(root), "w1", 2).events] == [2], "省略 before/after ⇒ 只给目标"


def test_read_event_rejects_bad_window_and_missing_target(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "w2", _turns("一"))

    for bad in (-1, MAX_READ_WINDOW + 1, "2", True, 1.5):
        with pytest.raises(SessionQueryError):
            read_event(str(root), "w2", 0, before=bad)
    with pytest.raises(SessionQueryNotFound):
        read_event(str(root), "w2", 99)
    with pytest.raises(SessionQueryNotFound):
        read_event(str(root), "nope", 0)
    with pytest.raises(ValueError):
        require_session(str(root), "../escape")
    assert require_session(str(root), "w2").endswith("w2.jsonl")


# —— ③ `trace_event` ——


def test_trace_event_reports_compaction_replacements(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(
        root,
        "t1",
        [
            (USER_MESSAGE, {"text": "旧提问"}),
            (ASSISTANT_MESSAGE, {"content": "旧回答"}),
            (COMPACTION, {"summary": "摘要", "shadowed": [0, 1]}),
        ],
    )

    covered = trace_event(str(root), "t1", 0)
    assert covered.replaced_by == 2
    assert covered.replacement_chain == (2,)
    assert covered.replaced_seqs == ()
    assert covered.source_seqs is None and covered.derived_seqs is None, "本地无从计算（不伪造 0 条）"

    replacer = trace_event(str(root), "t1", 2)
    assert replacer.replaced_by is None
    assert replacer.replacement_chain == ()
    assert replacer.replaced_seqs == (0, 1)


def test_trace_event_follows_chain_and_last_writer_wins(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(
        root,
        "t2",
        [
            (USER_MESSAGE, {"text": "旧"}),
            (COMPACTION, {"summary": "一层", "shadowed": [0]}),
            (COMPACTION, {"summary": "二层", "shadowed": [0, 1]}),
        ],
    )
    assert trace_event(str(root), "t2", 0).replacement_chain == (2,), "后写覆盖：0 直接由 2 覆盖"


def test_trace_event_reads_prune_records(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(
        root,
        "t3",
        [
            (TOOL_RESULT, {"id": "c1", "name": "search_kb", "content": "很长" * 100}),
            (PRUNE, {"pruned": [{"seq": 0, "id": "c1", "chars_before": 900, "chars_after": 40, "head": 20, "tail": 20}]}),
        ],
    )
    pruned = trace_event(str(root), "t3", 0)
    assert pruned.replaced_by == 1
    assert trace_event(str(root), "t3", 1).replaced_seqs == (0,)


# —— ④ `session_lineage` ——


def test_session_lineage_root_is_self(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "root-1", _turns("唯一一轮"))

    lineage = session_lineage(str(root), "root-1")
    assert lineage.target.session_id == "root-1"
    assert lineage.ancestors == () and lineage.descendants == ()
    assert lineage.complete is True and lineage.unresolved_parent_id is None
    assert lineage.target.title == "唯一一轮"


def test_session_lineage_walks_parent_chain_and_descendants(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "p", _turns("根会话"))
    _session(root, "c", _turns("子会话"), parent="p")
    _session(root, "g", _turns("孙会话"), parent="c")

    leaf = session_lineage(str(root), "g")
    assert [record.session_id for record in leaf.ancestors] == ["c", "p"], "由近及远"
    assert leaf.target.parent_session_id == "c"
    assert leaf.descendants == ()

    top = session_lineage(str(root), "p")
    assert top.ancestors == ()
    assert [(depth, record.session_id) for depth, record in top.descendants] == [(1, "c"), (2, "g")]


def test_session_lineage_reports_unresolved_parent(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "orphan", _turns("父会话不在本地"), parent="ghost")

    lineage = session_lineage(str(root), "orphan")
    assert lineage.complete is False
    assert lineage.unresolved_parent_id == "ghost"
    assert lineage.ancestors == ()


def test_session_lineage_rejects_cycle_and_missing_target(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "a", _turns("a"), parent="b")
    _session(root, "b", _turns("b"), parent="a")

    with pytest.raises(SessionQueryError):
        session_lineage(str(root), "a")
    with pytest.raises(SessionQueryNotFound):
        session_lineage(str(root), "nope")


# —— ⑤ 工具：`session_event_search` ——


def test_session_event_search_lists_hits_with_seq_and_snippet(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _mixed_session(root)
    out = _tool(root, "session_event_search").handler({"session_id": "trace-s1", "query": "梯度下降"})

    assert not out.error
    assert "事件命中 3 条" in out.text, "tool/call 是结构性事件，不贡献语义文本"
    assert "第 0 条 | user/message" in out.text
    assert "第 3 条 | tool/result" in out.text
    assert "片段：梯度下降是什么" in out.text
    assert out.anchors == (), "会话命中不是文档出处：不产生 `文件:行号` 锚点"
    assert "会话 trace-s1 第 N 条" in out.text


def test_session_event_search_filters(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    store = SessionStore(str(root), "f1")
    for text in ("梯度", "无关", "梯度"):
        store.append(USER_MESSAGE, {"text": text})
    store.flush()

    tool = _tool(root, "session_event_search")
    assert "事件命中 2 条" in tool.handler({"session_id": "f1", "query": "梯度"}).text
    only_first = tool.handler({"session_id": "f1", "query": "梯度", "seq_from": 0, "seq_to": 0})
    assert "事件命中 1 条" in only_first.text and "第 0 条" in only_first.text
    by_type = tool.handler({"session_id": "f1", "query": "梯度", "event_types": [ASSISTANT_MESSAGE]})
    assert "未在该会话里命中" in by_type.text, "类型白名单生效"

    now = int(time.time() * 1000)
    in_range = tool.handler(
        {
            "session_id": "f1",
            "query": "梯度",
            "time_from": _iso(now - 60_000),
            "time_to": _iso(now + 60_000),
        }
    )
    assert "事件命中 2 条" in in_range.text
    out_of_range = tool.handler({"session_id": "f1", "query": "梯度", "time_to": _iso(now - 60_000)})
    assert "未在该会话里命中" in out_of_range.text


def _iso(epoch_ms: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(epoch_ms / 1000, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_session_event_search_caps_at_upstream_limit(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    store = SessionStore(str(root), "cap")
    for _ in range(DEFAULT_SEARCH_RESULT_LIMIT + 5):
        store.append(USER_MESSAGE, {"text": "梯度"})
    store.flush()

    out = _tool(root, "session_event_search").handler({"session_id": "cap", "query": "梯度"})
    assert f"事件命中 {DEFAULT_SEARCH_RESULT_LIMIT} 条" in out.text
    assert "已达结果上限 100 条" in out.text and "收窄" in out.text
    assert out.text.count("| user/message |") == DEFAULT_SEARCH_RESULT_LIMIT


def test_session_event_search_fails_closed(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _mixed_session(root)
    tool = _tool(root, "session_event_search")

    missing_target = tool.handler({"session_id": "nope", "query": "梯度"})
    assert missing_target.error and missing_target.code == NOT_FOUND_CODE, "坏目标不静默返回空"
    escape = tool.handler({"session_id": "../escape", "query": "梯度"})
    assert escape.error and escape.code == INVALID_ARGUMENTS_CODE

    bad_args: list[dict[str, Any]] = [
        {"session_id": "trace-s1", "query": "   "},
        {"query": "梯度"},
        {"session_id": "trace-s1"},
        {"session_id": "trace-s1", "query": "梯度", "seq_from": -1},
        {"session_id": "trace-s1", "query": "梯度", "seq_from": 3, "seq_to": 1},
        {"session_id": "trace-s1", "query": "梯度", "time_from": "2026-09-20T09:00:00"},
        {"session_id": "trace-s1", "query": "梯度", "time_from": "2026-09-20T09:00:00Z", "time_to": "2026-09-19T09:00:00Z"},
        {"session_id": "trace-s1", "query": "梯度", "event_types": []},
        {"session_id": "trace-s1", "query": "梯度", "event_types": [""]},
        {"session_id": "trace-s1", "query": "梯度", "seq_to": "2"},
    ]
    for arguments in bad_args:
        out = tool.handler(arguments)
        assert out.error and out.code == INVALID_ARGUMENTS_CODE, arguments


def test_session_event_search_empty_hit_is_not_error(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "none-1", _turns("完全无关"))
    out = _tool(root, "session_event_search").handler({"session_id": "none-1", "query": "梯度"})
    assert not out.error
    assert "未在该会话里命中" in out.text


# —— ⑤ 工具：`session_event_read` ——


def test_session_event_read_returns_full_event_and_neighbour_summaries(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _mixed_session(root)
    out = _tool(root, "session_event_read").handler({"session_id": "trace-s1", "seq": 2, "before": 1, "after": 2})

    assert not out.error
    assert "目标事件（第 2 条，完整未删节）：" in out.text
    payload = json.loads(out.text.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert payload["seq"] == 2 and payload["type"] == TOOL_CALL and payload["data"]["name"] == "search_kb"
    assert "之前的事件：" in out.text and "- 第 1 条 | assistant/message" in out.text
    assert "之后的事件：" in out.text and "- 第 3 条 | tool/result" in out.text
    assert "命中：梯度下降" in out.text, "相邻事件按语义文本摘要（缩进两格）"
    # 目标自身不重复列在相邻摘要里
    assert "- 第 2 条 |" not in out.text


def test_session_event_read_marks_events_without_semantic_text(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _mixed_session(root)
    out = _tool(root, "session_event_read").handler({"session_id": "trace-s1", "seq": 4, "before": 2})
    assert "（无语义文本）" in out.text, "tool/call 是结构性事件：`event_text()` 为空"
    assert "- 第 5 条 |" not in out.text, "after 省略 ⇒ 不给后续事件"


def test_session_event_read_fails_closed(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _mixed_session(root)
    tool = _tool(root, "session_event_read")

    missing_target = tool.handler({"session_id": "trace-s1", "seq": 99})
    assert missing_target.error and missing_target.code == NOT_FOUND_CODE
    for arguments in (
        {"session_id": "nope", "seq": 0},
        {"session_id": "trace-s1"},
        {"session_id": "trace-s1", "seq": -1},
        {"session_id": "trace-s1", "seq": 0, "before": MAX_READ_WINDOW + 1},
        {"session_id": "trace-s1", "seq": 0, "after": "2"},
        {"session_id": "trace-s1", "seq": 0, "before": True},
    ):
        out = tool.handler(arguments)
        assert out.error, arguments
        assert out.code == (NOT_FOUND_CODE if arguments.get("session_id") == "nope" else INVALID_ARGUMENTS_CODE)


# —— ⑤ 工具：`session_trace` / `session_event_trace` ——


def test_session_trace_tool_reports_root_and_parent_chain(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(root, "p", _turns("根会话"))
    _session(root, "c", _turns("子会话"), parent="p")
    _session(root, "solo", _turns("无亲无故"))
    tool = _tool(root, "session_trace")

    solo = tool.handler({"session_id": "solo"})
    assert not solo.error
    assert "- 无（目标即根会话）" in solo.text
    assert "不记录 `parentSession`" in solo.text, "本地无 fork/派生会话：如实说明而不是伪造谱系"

    top = tool.handler({"session_id": "p"})
    assert "- 无（目标即根会话）" in top.text
    assert "  - c — 子会话" in top.text, "后代按深度缩进"
    assert "不记录 `parentSession`" not in top.text

    child = tool.handler({"session_id": "c"})
    assert "- p — 根会话" in child.text and "- 无（目标即根会话）" not in child.text

    assert tool.handler({"session_id": "nope"}).code == NOT_FOUND_CODE
    assert tool.handler({}).code == INVALID_ARGUMENTS_CODE

    unresolved = _session(root, "orphan", _turns("父不在本地"), parent="ghost")
    orphan = tool.handler({"session_id": "orphan"})
    assert unresolved is not None and "[ghost] 不在本地会话目录里" in orphan.text


def test_session_event_trace_tool_reports_replacements_and_missing_citations(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    _session(
        root,
        "e1",
        [
            (USER_MESSAGE, {"text": "旧提问"}),
            (ASSISTANT_MESSAGE, {"content": "旧回答"}),
            (COMPACTION, {"summary": "摘要", "shadowed": [0, 1]}),
        ],
    )
    tool = _tool(root, "session_event_trace")

    replaced = tool.handler({"session_id": "e1", "seq": 0})
    assert not replaced.error
    assert "被替换为：第 2 条" in replaced.text
    assert "替换链：第 2 条" in replaced.text
    assert "被目标替换的事件：无" in replaced.text
    assert "无从给出" in replaced.text

    replacer = tool.handler({"session_id": "e1", "seq": 2})
    assert "被目标替换的事件：第 0 条、第 1 条" in replacer.text
    assert "被替换为：无" in replacer.text

    assert tool.handler({"session_id": "e1", "seq": 42}).code == NOT_FOUND_CODE
    assert tool.handler({"session_id": "e1", "seq": -1}).code == INVALID_ARGUMENTS_CODE
    assert tool.handler({"session_id": "e1"}).code == INVALID_ARGUMENTS_CODE


# —— ⑥ 注册面 ——


def test_new_session_query_tools_registered_and_read_only(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    registry = ToolRegistry(build_kb_tools(str(root)))

    assert tuple(tool.name for tool in build_kb_tools(str(root))) == KB_TOOL_NAMES
    assert registry.names()[-4:] == SESSION_TOOLS, "新增工具追加在工具面末尾（零锚点漂移）"
    for name in SESSION_TOOLS:
        tool = registry.get(name)
        assert tool is not None and tool.read_only and tool.parameters["additionalProperties"] is False

    schemas: dict[str, Any] = {schema.name: schema.parameters for schema in registry.schemas()}
    assert set(schemas["session_event_search"]["properties"]) == {
        "session_id", "query", "seq_from", "seq_to", "time_from", "time_to", "event_types",
    }
    assert schemas["session_event_search"]["required"] == ["session_id", "query"]
    assert set(schemas["session_trace"]["properties"]) == {"session_id"}
    assert set(schemas["session_event_trace"]["properties"]) == {"session_id", "seq"}
    assert set(schemas["session_event_read"]["properties"]) == {"session_id", "seq", "before", "after"}
    assert schemas["session_event_read"]["properties"]["before"]["maximum"] == MAX_READ_WINDOW
    assert schemas["session_event_read"]["required"] == ["session_id", "seq"], "session_id 本地必填"


def test_session_query_tools_reject_unknown_and_missing_arguments(tmp_path: Path) -> None:
    root = _kb(tmp_path)
    registry = ToolRegistry(build_kb_tools(str(root)))

    unknown = registry.invoke(
        ToolCall(id="c1", name="session_event_read", arguments=json.dumps({"session_id": "x", "seq": 0, "limit": 3}))
    )
    assert unknown.is_error and unknown.output.code == INVALID_ARGUMENTS_CODE

    missing = registry.invoke(ToolCall(id="c2", name="session_event_read", arguments=json.dumps({"seq": 0})))
    assert missing.is_error and missing.output.code == INVALID_ARGUMENTS_CODE, "schema 层就要求 session_id"

    for call_id, name, arguments in (
        ("c3", "session_trace", {}),
        ("c4", "session_event_trace", {"session_id": "x"}),
        ("c5", "session_event_search", {"session_id": "x", "query": "a", "seq_from": -1}),
    ):
        result = registry.invoke(ToolCall(id=call_id, name=name, arguments=json.dumps(arguments)))
        assert result.is_error and result.output.code == INVALID_ARGUMENTS_CODE, name
