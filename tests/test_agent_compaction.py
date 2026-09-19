# 配套单测：被测调用面语义移植自 deepseek-harness packages/compaction/*
# （MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""长会话压缩（M2）离线单测：不联网、不写知识库正文。

覆盖：
① 区域选择（工具配对切割点 / 尾部逐字保留 / 最小覆盖量 / 必须含用户消息 / 尽量多压）；
② 回放（被覆盖区间在原位换成摘要、链式压缩只出最新那份、无效记录不吞事件、工具配对完好、
   `replay_events(apply_compaction=False)` 可取原始视图）；
③ 摘要器 fail-closed（error / aborted / max-tokens / 空正文 / 返回工具调用 / 取消），
   以及「指令作为最后一条 user 消息 + 对话前缀原样保留」的 KV 对齐形状；
④ 端到端（超预算自动压缩并落 `compaction` 事件、本轮请求不再含被覆盖的旧料；压缩失败
   **不打断**提问）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.ask import ask
from memoria.services.agent.compaction import (
    COMPACTION_INSTRUCTION,
    CompactionError,
    MIN_SPAN_CHARS,
    SUMMARY_CLOSE_TAG,
    SUMMARY_OPEN_TAG,
    balanced_cuts,
    compact_threshold_chars,
    event_chars,
    frame_summary,
    retain_chars,
    select_span,
    summarize_span,
)
from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    ProviderError,
    Role,
    TextDelta,
    ToolCall,
    ToolSchema,
    Usage,
    UsageEvent,
)
from memoria.services.agent.loop import CancelToken
from memoria.services.agent.session.history import (
    ASSISTANT_MESSAGE,
    COMPACTION,
    TOOL_RESULT,
    USER_MESSAGE,
    build_history,
    replay_events,
)
from memoria.services.agent.session.store import SessionStore, read_session

# —— 测试替身（与 tests/test_agent_loop.py 同形）——


class FakeProvider:
    """按脚本产出流式事件的假 provider；记录收到的请求以便断言。"""

    name = "fake"

    def __init__(self, script: Sequence[Sequence[Any]]) -> None:
        self.script: list[list[Any]] = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else [TextDelta("（脚本耗尽）"), FinishEvent(reason=FinishReason.STOP)]
        yield from step


def text_step(text: str) -> list[Any]:
    return [
        TextDelta(text),
        UsageEvent(Usage(prompt_tokens=10, completion_tokens=5)),
        FinishEvent(reason=FinishReason.STOP),
    ]


SUMMARY_TEXT = "## 待办\n- (none)\n"


# —— 辅助 ——


def _session(root: Path, session_id: str, events: Sequence[tuple[str, dict[str, Any]]]) -> SessionStore:
    store = SessionStore(str(root), session_id)
    for kind, data in events:
        store.append(kind, data)
    store.flush()
    return store


def _turn(index: int, size: int) -> list[tuple[str, dict[str, Any]]]:
    """一轮问答：正文带 `FILLER<index>` 标记，便于断言"旧料是否还在请求里"。"""
    body = f"FILLER{index}-" + "x" * size
    return [(USER_MESSAGE, {"text": body}), (ASSISTANT_MESSAGE, {"content": body})]


def _tool_wrapped_turn(index: int, size: int) -> list[tuple[str, dict[str, Any]]]:
    """一轮**带工具调用**的问答：user → assistant(1 个 tool_call) → tool/result → assistant。"""
    body = f"FILLER{index}-" + "x" * size
    call_id = f"call-{index}"
    return [
        (USER_MESSAGE, {"text": body}),
        (
            ASSISTANT_MESSAGE,
            {"content": "", "tool_calls": [{"id": call_id, "name": "search_kb", "arguments": "{}"}]},
        ),
        (TOOL_RESULT, {"id": call_id, "name": "search_kb", "content": body, "anchors": []}),
        (ASSISTANT_MESSAGE, {"content": body}),
    ]


def _assert_tool_pairing(messages: Sequence[Message]) -> None:
    """回放结果必须满足 OpenAI 兼容协议的结构约束（无孤立 tool_calls / 无孤儿 tool 消息）。"""
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.role == Role.TOOL.value:
            raise AssertionError(f"孤儿 tool 消息（第 {index} 条）：{message.content[:40]}")
        calls = message.tool_calls or ()
        if calls:
            followed = messages[index + 1 : index + 1 + len(calls)]
            assert len(followed) == len(calls), "tool_calls 数量与紧随的 tool 消息不符"
            for call, result in zip(calls, followed):
                assert result.role == Role.TOOL.value
                assert result.tool_call_id == call.id
            index += 1 + len(calls)
            continue
        index += 1


# —— ① 区域选择 ——


def test_balanced_cuts_mark_tool_group_interior() -> None:
    """`cuts[i]` = 「在 events[i] 之前切割」是否平衡：工具调用与其结果之间必须为 False。"""
    events = [
        {"seq": 0, "type": USER_MESSAGE, "data": {"text": "q"}},
        {
            "seq": 1,
            "type": ASSISTANT_MESSAGE,
            "data": {"content": "", "tool_calls": [{"id": "c1", "name": "search_kb", "arguments": "{}"}]},
        },
        {"seq": 2, "type": TOOL_RESULT, "data": {"id": "c1", "name": "search_kb", "content": "r"}},
        {"seq": 3, "type": ASSISTANT_MESSAGE, "data": {"content": "答"}},
    ]
    assert balanced_cuts(events) == [True, True, False, True, True]


def test_retain_below_threshold_invariant() -> None:
    """上游不变量 `retain < threshold`（`config.ts:144-154`）在默认比例下成立。"""
    assert retain_chars() < compact_threshold_chars()


def test_select_span_returns_none_below_minimum() -> None:
    assert select_span([], max_chars=100_000) is None
    short = [{"seq": 0, "type": USER_MESSAGE, "data": {"text": "短"}}]
    assert select_span(short, max_chars=100_000) is None


def test_select_span_requires_a_user_message() -> None:
    """区间内必须有用户消息，否则不值得一次模型调用（本地下限）。"""
    events = [
        {"seq": index, "type": TOOL_RESULT, "data": {"id": f"c{index}", "content": "x" * 3000}}
        for index in range(4)
    ]
    assert select_span(events, max_chars=6_000) is None


def test_select_span_protects_tail_and_takes_the_latest_legal_cut() -> None:
    events: list[dict[str, Any]] = []
    seq = 0
    for index in range(3):
        for kind, data in _turn(index, 6_000):
            events.append({"seq": seq, "type": kind, "data": data})
            seq += 1
    span = select_span(events, max_chars=10_000)
    assert span is not None
    start, end = span
    assert start == 0
    keep = retain_chars(10_000)
    assert sum(event_chars(event) for event in events[end:]) >= keep
    # 「尽量多压」：再多覆盖一条就会让逐字保留不足
    assert sum(event_chars(event) for event in events[end + 1 :]) < keep
    assert prefix_chars(events, end) >= MIN_SPAN_CHARS


def prefix_chars(events: Sequence[dict[str, Any]], end: int) -> int:
    return sum(event_chars(event) for event in events[:end])


def test_select_span_never_ends_inside_a_tool_group() -> None:
    """带工具轮的旧料：切割点只能落在工具组之外。"""
    events: list[dict[str, Any]] = []
    seq = 0
    for index in range(3):
        for kind, data in _tool_wrapped_turn(index, 6_000):
            events.append({"seq": seq, "type": kind, "data": data})
            seq += 1
    span = select_span(events, max_chars=10_000)
    assert span is not None
    _, end = span
    assert balanced_cuts(events)[end], "切割点必须工具配对平衡"


# —— ② 回放 ——


def test_build_history_replaces_shadowed_range_with_summary(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    _session(
        root,
        "s1",
        [
            (USER_MESSAGE, {"text": "旧问题"}),
            (ASSISTANT_MESSAGE, {"content": "旧答案"}),
            (USER_MESSAGE, {"text": "新问题"}),
            (ASSISTANT_MESSAGE, {"content": "新答案"}),
            (COMPACTION, {"summary": "旧料摘要", "shadowed": [0, 1]}),
        ],
    )
    messages = build_history(str(root), "s1")
    texts = [message.content for message in messages]
    assert len(messages) == 3
    assert "旧料摘要" in messages[0].content
    assert messages[0].role == Role.USER.value
    assert SUMMARY_OPEN_TAG in messages[0].content and SUMMARY_CLOSE_TAG in messages[0].content
    assert all("旧问题" not in text and "旧答案" not in text for text in texts)
    assert messages[1].content == "新问题"
    assert messages[2].content == "新答案"


def test_chained_compaction_emits_only_the_latest_summary(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    _session(
        root,
        "s2",
        [
            (USER_MESSAGE, {"text": "第一轮"}),
            (ASSISTANT_MESSAGE, {"content": "答一"}),
            (COMPACTION, {"summary": "第一份摘要", "shadowed": [0, 1]}),
            (USER_MESSAGE, {"text": "第二轮"}),
            (ASSISTANT_MESSAGE, {"content": "答二"}),
            # 链式：第二次把「第一轮 + 第一份摘要记录 + 第二轮」全压掉
            (COMPACTION, {"summary": "第二份摘要", "shadowed": [0, 1, 2, 3, 4]}),
        ],
    )
    messages = build_history(str(root), "s2")
    summaries = [message for message in messages if "摘要" in message.content]
    assert len(summaries) == 1, "链式压缩只应出最新那份合并摘要"
    assert "第二份摘要" in messages[0].content


def test_invalid_compaction_record_is_ignored(tmp_path: Path) -> None:
    """空 `shadowed` / 空摘要 ⇒ 忽略该记录，不吞掉任何事件（fail-safe）。"""
    root = tmp_path / "kb"
    _session(
        root,
        "s3",
        [
            (USER_MESSAGE, {"text": "问一"}),
            (ASSISTANT_MESSAGE, {"content": "答一"}),
            (COMPACTION, {"summary": "有摘要但没覆盖任何东西", "shadowed": []}),
            (COMPACTION, {"summary": "", "shadowed": [0]}),
        ],
    )
    messages = build_history(str(root), "s3")
    assert [message.content for message in messages] == ["问一", "答一"]


def test_compaction_preserves_tool_pairing(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    events: list[tuple[str, dict[str, Any]]] = []
    events += _tool_wrapped_turn(0, 4_000)  # seq 0-3
    events += _tool_wrapped_turn(1, 4_000)  # seq 4-7
    events.append((COMPACTION, {"summary": "前两轮摘要", "shadowed": [0, 1, 2, 3]}))
    _session(root, "s4", events)
    messages = build_history(str(root), "s4")
    _assert_tool_pairing(messages)
    assert "前两轮摘要" in messages[0].content
    assert any("FILLER1" in message.content for message in messages)
    assert all("FILLER0" not in message.content for message in messages)


def test_replay_events_can_ignore_compaction(tmp_path: Path) -> None:
    """`apply_compaction=False` 取**原始**视图（压缩器据此核对、诊断用）。"""
    root = tmp_path / "kb"
    store = _session(
        root,
        "s5",
        [
            (USER_MESSAGE, {"text": "旧问题"}),
            (ASSISTANT_MESSAGE, {"content": "旧答案"}),
            (COMPACTION, {"summary": "摘要", "shadowed": [0, 1]}),
        ],
    )
    events = store.events()
    assert [message.content for message in replay_events(events, apply_compaction=False)] == ["旧问题", "旧答案"]
    assert [message.content for message in replay_events(events)] != ["旧问题", "旧答案"]


def test_frame_summary_wraps_with_preamble_and_tags() -> None:
    framed = frame_summary("  正文  ")
    assert framed.startswith("以下")
    assert f"{SUMMARY_OPEN_TAG}\n正文\n{SUMMARY_CLOSE_TAG}" in framed


# —— ③ 摘要器 ——


def test_summarize_span_keeps_conversation_prefix_and_appends_instruction() -> None:
    """形状对齐上游：同一份 system + tools + 对话前缀，指令**只在最后**（KV 前缀复用）。"""
    provider = FakeProvider([text_step(SUMMARY_TEXT)])
    prefix = [Message(role=Role.USER, content="旧料"), Message(role=Role.ASSISTANT, content="旧答")]
    call = summarize_span(
        provider,
        prefix,
        system="SYS",
        tools=(ToolSchema(name="read_document"),),
        model="probe-model",
    )
    assert call.text == SUMMARY_TEXT.strip()
    assert call.model == "probe-model"
    request = provider.requests[0]
    assert request.system == "SYS"
    assert [tool.name for tool in request.tools] == ["read_document"]
    assert [message.content for message in request.messages[:-1]] == ["旧料", "旧答"]
    assert request.messages[-1].role == Role.USER.value
    assert request.messages[-1].content == COMPACTION_INSTRUCTION


@pytest.mark.parametrize(
    "step",
    [
        pytest.param([FinishEvent(reason=FinishReason.ERROR, failure=ProviderError("端点炸了"))], id="error"),
        pytest.param([TextDelta("半截"), FinishEvent(reason=FinishReason.ABORTED)], id="aborted"),
        pytest.param([TextDelta("半截"), FinishEvent(reason=FinishReason.MAX_TOKENS)], id="max-tokens"),
        pytest.param([FinishEvent(reason=FinishReason.STOP)], id="empty"),
        pytest.param([FinishEvent(reason=FinishReason.STOP, tool_calls=(ToolCall("c1", "read_document", "{}"),))], id="tool-call"),
    ],
)
def test_summarize_span_fail_closed(step: list[Any]) -> None:
    provider = FakeProvider([step])
    with pytest.raises(CompactionError):
        summarize_span(provider, [Message(role=Role.USER, content="旧料")], model="m")


def test_summarize_span_respects_cancel() -> None:
    token = CancelToken()
    token.cancel()
    provider = FakeProvider([text_step(SUMMARY_TEXT)])
    with pytest.raises(CompactionError):
        summarize_span(provider, [Message(role=Role.USER, content="旧料")], cancel=token)


# —— ④ 端到端 ——


def _long_kb(root: Path) -> Path:
    (root / ".memoria" / "agent").mkdir(parents=True, exist_ok=True)
    (root / "doc.md").write_text("# 文档\n\n正文。\n", encoding="utf-8")
    return root


def test_ask_compacts_long_session_and_drops_shadowed_content(tmp_path: Path) -> None:
    root = _long_kb(tmp_path / "kb")
    events: list[tuple[str, dict[str, Any]]] = []
    for index in range(7):
        events += _turn(index, 4_000)  # 7 轮 × 2 条 × ~4008 字符 ≈ 56k 字符
    _session(root, "long", events)

    provider = FakeProvider([text_step(SUMMARY_TEXT), text_step("压缩后的答案")])
    result = ask(
        str(root),
        "接着说说",
        provider=provider,
        model="probe-model",
        session_id="long",
        config=None,
    )
    assert result.answer == "压缩后的答案"
    # 第一次调用是摘要（末尾是指令），第二次是主回合
    assert len(provider.requests) == 2
    assert provider.requests[0].messages[-1].content == COMPACTION_INSTRUCTION

    records = read_session(str(root), "long")
    compactions = [row for row in records if row.get("type") == COMPACTION]
    assert len(compactions) == 1
    data = compactions[0]["data"]
    assert data["summary"] == SUMMARY_TEXT.strip()
    assert data["shadowed"], "shadowed 必须记录被覆盖的 seq"
    assert data["shadowed_chars"] > 0
    assert data["model"] == "probe-model"

    # 主回合的请求：含 checkpoint、不含被覆盖的旧料
    main = provider.requests[1]
    joined = "\n".join(message.content for message in main.messages)
    assert SUMMARY_OPEN_TAG in joined
    assert "FILLER0" not in joined, "被压缩的旧料不应再逐字重发"
    assert "FILLER6" in joined, "最新的尾部必须逐字保留"
    _assert_tool_pairing(main.messages)


def test_ask_survives_compaction_failure(tmp_path: Path) -> None:
    """压缩失败 fail-open：不落 `compaction` 事件，但提问照常走完。"""
    root = _long_kb(tmp_path / "kb")
    events: list[tuple[str, dict[str, Any]]] = []
    for index in range(7):
        events += _turn(index, 4_000)
    _session(root, "long2", events)

    provider = FakeProvider(
        [[FinishEvent(reason=FinishReason.ERROR, failure=ProviderError("摘要端点炸了"))], text_step("照样答题")]
    )
    result = ask(str(root), "接着说说", provider=provider, model="probe-model", session_id="long2")
    assert result.answer == "照样答题"
    records = read_session(str(root), "long2")
    assert not [row for row in records if row.get("type") == COMPACTION]


def test_ask_does_not_compact_short_session(tmp_path: Path) -> None:
    """历史在预算内 ⇒ 一次多余的模型调用都不发。"""
    root = _long_kb(tmp_path / "kb")
    _session(root, "short", _turn(0, 100))
    provider = FakeProvider([text_step("答案")])
    result = ask(str(root), "再问一句", provider=provider, model="probe-model", session_id="short")
    assert result.answer == "答案"
    assert len(provider.requests) == 1
    assert not [row for row in read_session(str(root), "short") if row.get("type") == COMPACTION]


def test_session_jsonl_stays_append_only_after_compaction(tmp_path: Path) -> None:
    """压缩不重写历史：原有事件逐行原样保留，只多出一条 `compaction`。"""
    root = _long_kb(tmp_path / "kb")
    events: list[tuple[str, dict[str, Any]]] = []
    for index in range(7):
        events += _turn(index, 4_000)
    _session(root, "long3", events)
    before = read_session(str(root), "long3")
    provider = FakeProvider([text_step(SUMMARY_TEXT), text_step("答案")])
    ask(str(root), "接着说说", provider=provider, model="probe-model", session_id="long3")
    after = read_session(str(root), "long3")
    assert after[: len(before)] == before, "既有记录必须逐条不变（仅追加）"
    assert after[len(before)]["type"] == COMPACTION
    # seq 连续（store 的连续 seq 不变量；header 无 seq，故先过滤）
    seqs = [row["seq"] for row in after if isinstance(row.get("seq"), int)]
    assert seqs == list(range(len(seqs)))
    # 文件仍是「一行一个 JSON 对象」
    path = root / ".memoria" / "agent" / "sessions" / "long3.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        assert isinstance(json.loads(line), dict)
