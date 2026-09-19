# 配套单测：被测调用面语义移植自 deepseek-harness packages/session/session-title、
# session-title-llm、session-title-first-prompt-llm（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""会话标题（M2）离线单测：不联网、不写知识库正文。

覆盖：
① 规范化（控制序列 / 隐形字符 / 空白折叠 / 按 UTF-8 字节截断且不切开码点 / 非法上限）；
② 合格消息与折叠（只有人类非空提问合格、`through_seq` 上界、最新一条胜出）；
③ 确定性兜底（首条消息前 N 词、只落一次、已有标题则跳过）；
④ 模型标题调用（请求形状、规范化、fail-closed 六路、输入上限、路由/model 记录）；
⑤ `first-prompt` 节律（只在恰好一条合格消息时生成）；
⑥ 端到端（首轮落 fallback+provider 两条、次轮不再生成、被取消的轮次跳过、失败 fail-open、
   标题**永不进模型输入**、会话列表按折叠标题显示）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.ask import ask
from memoria.services.agent.llm import (
    AgentLlmError,
    FinishEvent,
    FinishReason,
    LlmRequest,
    ProviderError,
    TextDelta,
    Usage,
    UsageEvent,
)
from memoria.services.agent.loop import CancelToken
from memoria.services.agent.session.history import (
    ASSISTANT_MESSAGE,
    USER_MESSAGE,
    build_history,
    summarize_events,
    summarize_session_file,
)
from memoria.services.agent.session.store import SessionStore, read_session, session_file
from memoria.services.agent.title import (
    SESSION_TITLE,
    TITLE_MAX_BYTES,
    TitleError,
    auto_title,
    clean_title_text,
    collect_title_messages,
    ensure_fallback,
    fallback_title,
    fold_title,
    generate_title,
    normalize_title,
    title_message,
    title_system_prompt,
    truncate_title_utf8,
)

# —— 测试替身 ——


class FakeProvider:
    """按脚本产出流式事件的假 provider；**脚本耗尽后一个事件也不发**（便于测「无终止事件」）。"""

    name = "fake"

    def __init__(self, script: Sequence[Sequence[Any]]) -> None:
        self.script: list[list[Any]] = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        if not self.script:
            return
        yield from self.script.pop(0)


class BoomProvider:
    """迭代即抛 `AgentLlmError` 的假 provider（模拟确定性连接失败）。"""

    name = "boom"

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        raise AgentLlmError("连接模型端点失败", code="UNREACHABLE")
        yield  # pragma: no cover


def text_step(text: str) -> list[Any]:
    return [
        TextDelta(text),
        UsageEvent(Usage(prompt_tokens=10, completion_tokens=5)),
        FinishEvent(reason=FinishReason.STOP),
    ]


def _kb(root: Path) -> Path:
    (root / ".memoria" / "agent").mkdir(parents=True, exist_ok=True)
    (root / "doc.md").write_text("# 文档\n\n正文。\n", encoding="utf-8")
    return root


def _session(root: Path, session_id: str, events: Sequence[tuple[str, dict[str, Any]]]) -> SessionStore:
    store = SessionStore(str(root), session_id)
    for kind, data in events:
        store.append(kind, data)
    store.flush()
    return store


def _events(root: Path, session_id: str) -> list[dict[str, Any]]:
    return [row for row in read_session(str(root), session_id) if isinstance(row.get("seq"), int)]


def _titles(root: Path, session_id: str) -> list[dict[str, Any]]:
    return [row for row in _events(root, session_id) if row["type"] == SESSION_TITLE]


# —— ① 规范化 ——


def test_normalize_strips_terminal_control_sequences() -> None:
    assert clean_title_text("a\x1b[31m红\x1b[0m色") == "a红色", "CSI（SGR）序列要被去掉"
    assert clean_title_text("标题\x1b]0;window title\x07尾巴") == "标题尾巴", "OSC 序列要被去掉"
    assert clean_title_text("x\x1bMb") == "xb", "其余两字节 ESC 序列也要去掉"
    assert clean_title_text("\x1b]8;;https://example.com") == "", "未终结的 OSC 尾巴同样要去掉"


def test_normalize_strips_control_and_directional_characters() -> None:
    assert clean_title_text("a\x00\x08b\x7f c\x9f") == "ab c", "非空白 C0/C1 控制字符要被去掉"
    assert clean_title_text("a\u200bb\u202ec\ufeffd") == "abcd", "方向/隐形控制字符要被去掉"
    assert clean_title_text("a\n\t b") == "a b", "空白（含换行/制表）要折叠成单空格"


def test_normalize_truncates_by_utf8_bytes_without_splitting_code_point() -> None:
    text = "标题标题标题"  # 每个字 3 字节
    assert truncate_title_utf8(text, 9) == "标题标"
    assert truncate_title_utf8(text, 8) == "标题", "8 字节只放得下 2 个字（6 字节），第 3 个会被切开"
    assert truncate_title_utf8("abc", 3) == "abc"
    assert normalize_title("  " + text + "  ", max_bytes=6) == "标题"


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "9"])
def test_normalize_rejects_bad_byte_limit(bad: Any) -> None:
    with pytest.raises(TitleError):
        truncate_title_utf8("标题", bad)


def test_fallback_takes_leading_words_within_caps() -> None:
    text = "一二三四五六七八九十"
    assert fallback_title("one two three", max_words=2) == "one two"
    assert fallback_title("\n  one   two \t three  ") == "one two three", "空白先折叠再分词"
    assert fallback_title(text, max_words=3, max_bytes=12) == "一二三四", "字节上限优先于词数上限"


# —— ② 合格消息与折叠 ——


def test_title_message_requires_human_nonempty_text() -> None:
    assert title_message({"seq": 1, "type": ASSISTANT_MESSAGE, "data": {"content": "答案"}}) is None
    assert title_message({"seq": 2, "type": USER_MESSAGE, "data": {"text": "   "}}) is None
    assert title_message({"seq": 3, "type": USER_MESSAGE, "data": {"text": "\x1b[0m\x00"}}) is None
    assert title_message({"seq": 4, "type": USER_MESSAGE, "data": {}}) is None
    got = title_message({"seq": 5, "type": USER_MESSAGE, "data": {"text": " 有效提问 "}})
    assert got is not None and got.seq == 5 and got.text == " 有效提问 "


def test_collect_title_messages_respects_through_seq() -> None:
    events = [
        {"seq": 0, "type": USER_MESSAGE, "data": {"text": "第一问"}},
        {"seq": 1, "type": ASSISTANT_MESSAGE, "data": {"content": "答案"}},
        {"seq": 2, "type": USER_MESSAGE, "data": {"text": "   "}},
        {"seq": 3, "type": USER_MESSAGE, "data": {"text": "第二问"}},
    ]
    assert [m.seq for m in collect_title_messages(events)] == [0, 3]
    assert [m.seq for m in collect_title_messages(events, through_seq=0)] == [0]
    assert [m.seq for m in collect_title_messages(events, through_seq=2)] == [0]


def test_fold_title_takes_the_latest_and_ignores_empty() -> None:
    def title_event(seq: int, text: str, kind: str = "fallback") -> dict[str, Any]:
        return {
            "seq": seq,
            "time": 1000 + seq,
            "type": SESSION_TITLE,
            "data": {"title": text, "message_seqs": [0], "source": {"kind": kind}},
        }

    assert fold_title([{"seq": 0, "type": USER_MESSAGE, "data": {"text": "问"}}]) is None
    snapshot = fold_title([title_event(1, "兜底标题"), title_event(2, "模型标题", "provider")])
    assert snapshot is not None
    assert (snapshot.title, snapshot.source, snapshot.event_seq, snapshot.updated_at) == (
        "模型标题",
        "provider",
        2,
        1002,
    )
    assert snapshot.message_seqs == (0,)
    # 后一条是空标题 ⇒ 视作没有那条，仍用前一条（fail-safe）
    later = fold_title([title_event(1, "兜底标题"), title_event(2, "")])
    assert later is not None and later.title == "兜底标题"


# —— ③ 确定性兜底 ——


def test_ensure_fallback_appends_once_from_first_message(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    session = _session(root, "fb", [(USER_MESSAGE, {"text": "一二三四五六七八九十问"})])
    events = _events(root, "fb")

    assert ensure_fallback(session, events) is True
    rows = _titles(root, "fb")
    assert len(rows) == 1
    assert rows[0]["data"]["title"] == "一二三四五六七八九十问"
    assert rows[0]["data"]["message_seqs"] == [0]
    assert rows[0]["data"]["source"] == {"kind": "fallback"}
    # 幂等：再来一次不会再落（已有标题）
    assert ensure_fallback(session, _events(root, "fb")) is False
    assert len(_titles(root, "fb")) == 1


def test_ensure_fallback_skips_when_title_exists_or_no_message(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    session = _session(root, "fb2", [(ASSISTANT_MESSAGE, {"content": "只有答案"})])
    assert ensure_fallback(session, _events(root, "fb2")) is False
    assert _titles(root, "fb2") == []

    session2 = _session(
        root,
        "fb3",
        [(USER_MESSAGE, {"text": "问"}), (SESSION_TITLE, {"title": "既有标题", "source": {"kind": "provider"}})],
    )
    assert ensure_fallback(session2, _events(root, "fb3")) is False
    assert [row["data"]["title"] for row in _titles(root, "fb3")] == ["既有标题"]


# —— ④ 模型标题调用 ——


def test_generate_title_request_shape() -> None:
    provider = FakeProvider([text_step("  多层感知机  ")])
    messages = collect_title_messages(
        [{"seq": 7, "type": USER_MESSAGE, "data": {"text": "多层感知机讲的是什么？"}}]
    )
    call = generate_title(provider, messages, model="probe-model")

    assert call.title == "多层感知机" and call.model == "probe-model"
    assert call.usage is not None and call.usage.total == 15
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.system == title_system_prompt()
    assert request.max_tokens == 96
    assert len(request.messages) == 1 and request.messages[0].content is not None
    # 选材消息被**框成 JSON**（提问正文无法破坏结构分隔）
    body = request.messages[0].content
    assert body.startswith("根据这个 JSON 数组里的人类消息生成会话标题：\n")
    assert json.loads(body.split("\n", 1)[1]) == [{"seq": 7, "text": "多层感知机讲的是什么？"}]


@pytest.mark.parametrize(
    "step",
    [
        [FinishEvent(reason=FinishReason.ERROR, failure=ProviderError("端点炸了"))],
        [FinishEvent(reason=FinishReason.ABORTED, failure=ProviderError("被中止"))],
        [TextDelta("半截"), FinishEvent(reason=FinishReason.MAX_TOKENS)],
        [TextDelta("要调工具"), FinishEvent(reason=FinishReason.TOOL_CALLS)],
        [TextDelta("被过滤"), FinishEvent(reason=FinishReason.CONTENT_FILTER)],
        [TextDelta("  \x1b[0m "), FinishEvent(reason=FinishReason.STOP)],
        [],  # 一个事件都不发 ⇒ 无终止事件
    ],
)
def test_generate_title_is_fail_closed(step: list[Any]) -> None:
    provider = FakeProvider([step])
    with pytest.raises(TitleError):
        generate_title(provider, collect_title_messages([{"seq": 0, "type": USER_MESSAGE, "data": {"text": "问"}}]))


def test_generate_title_rejects_bad_input_and_wraps_provider_errors() -> None:
    provider = FakeProvider([text_step("标题")])
    with pytest.raises(TitleError):
        generate_title(provider, ())
    with pytest.raises(TitleError):
        generate_title(provider, collect_title_messages([{"seq": 0, "type": USER_MESSAGE, "data": {"text": "问"}}]), max_input_bytes=8)
    assert provider.requests == [], "输入不合法时一次请求都不该发"
    with pytest.raises(TitleError):
        generate_title(BoomProvider(), collect_title_messages([{"seq": 0, "type": USER_MESSAGE, "data": {"text": "问"}}]))


def test_generate_title_respects_cancel() -> None:
    token = CancelToken()
    token.cancel()
    provider = FakeProvider([text_step("标题")])
    with pytest.raises(TitleError):
        generate_title(
            provider,
            collect_title_messages([{"seq": 0, "type": USER_MESSAGE, "data": {"text": "问"}}]),
            cancel=token,
        )


# —— ⑤ first-prompt 节律 ——


def test_auto_title_only_on_the_first_message(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    one = _session(root, "auto1", [(USER_MESSAGE, {"text": "第一问"})])
    provider = FakeProvider([text_step("模型标题")])
    call = auto_title(one, _events(root, "auto1"), provider=provider, model="m")
    assert call is not None and call.title == "模型标题"
    row = _titles(root, "auto1")[-1]
    assert row["data"]["source"] == {"kind": "provider", "provider": "fake", "model": "m"}
    assert row["data"]["message_seqs"] == [0]

    two = _session(
        root,
        "auto2",
        [(USER_MESSAGE, {"text": "第一问"}), (ASSISTANT_MESSAGE, {"content": "答"}), (USER_MESSAGE, {"text": "第二问"})],
    )
    quiet = FakeProvider([text_step("不该出现")])
    assert auto_title(two, _events(root, "auto2"), provider=quiet, model="m") is None
    assert quiet.requests == []
    assert _titles(root, "auto2") == []


# —— ⑥ 端到端 ——


def test_ask_lands_fallback_then_provider_title_on_first_turn(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    provider = FakeProvider([text_step("答案"), text_step("首轮标题")])

    result = ask(str(root), "第一问", provider=provider, model="probe-model", session_id="e2e1")

    assert result.answer == "答案"
    rows = _titles(root, "e2e1")
    assert [row["data"]["source"]["kind"] for row in rows] == ["fallback", "provider"]
    assert rows[0]["data"]["title"] == "第一问"
    assert rows[1]["data"]["title"] == "首轮标题"
    # 标题调用的用量也记下来（形状同 `loop/end.usage`；**本地扩展**，上游不记）
    assert rows[1]["data"]["usage"]["total_tokens"] == 15
    assert set(rows[1]["data"]["usage"]) == {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated",
        "cache_read_tokens",
        "cache_write_tokens",
        "cache_miss_tokens",
    }
    assert "usage" not in rows[0]["data"], "兜底标题零成本，不记用量"
    # 标题**永不进模型输入**：主回合请求里没有标题字样，且回放也不多出消息
    main = "\n".join(message.content or "" for message in provider.requests[0].messages)
    assert "首轮标题" not in main
    assert [message.content for message in build_history(str(root), "e2e1")] == ["第一问", "答案"]
    summary = summarize_events(_events(root, "e2e1"))
    assert summary["title"] == "首轮标题"
    scanned = summarize_session_file(session_file(str(root), "e2e1"))
    assert scanned["title"] == "首轮标题", "原始行扫描与折叠口径必须一致"


def test_ask_does_not_regenerate_title_on_second_turn(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    first = FakeProvider([text_step("答案一"), text_step("首轮标题")])
    second = FakeProvider([text_step("答案二")])

    ask(str(root), "第一问", provider=first, model="probe-model", session_id="e2e2")
    ask(str(root), "第二问", provider=second, model="probe-model", session_id="e2e2")

    assert len(second.requests) == 1, "次轮不该再发标题调用"
    assert [row["data"]["title"] for row in _titles(root, "e2e2")] == ["第一问", "首轮标题"]


def test_ask_skips_title_when_turn_aborted(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    token = CancelToken()
    token.cancel()  # 进循环前就被取消 ⇒ 该轮 ABORTED、一次模型调用都不发
    provider = FakeProvider([text_step("不该出现")])

    result = ask(str(root), "问一句", provider=provider, model="probe-model", session_id="e2e3", cancel=token)

    assert result.stop_reason == "aborted"
    assert provider.requests == []
    assert [row["data"]["source"]["kind"] for row in _titles(root, "e2e3")] == ["fallback"], "只留兜底标题"


def test_ask_survives_title_failure(tmp_path: Path) -> None:
    root = _kb(tmp_path / "kb")
    provider = FakeProvider(
        [text_step("答案"), [FinishEvent(reason=FinishReason.ERROR, failure=ProviderError("标题端点炸了"))]]
    )

    result = ask(str(root), "第一问", provider=provider, model="probe-model", session_id="e2e4")

    assert result.answer == "答案", "标题失败不影响问答"
    assert [row["data"]["source"]["kind"] for row in _titles(root, "e2e4")] == ["fallback"]


def test_ask_titles_old_session_on_next_turn(tmp_path: Path) -> None:
    """老会话（建标题能力之前落的）再聊一句时补一条兜底标题；但不做模型标题（非首轮）。"""
    root = _kb(tmp_path / "kb")
    _session(
        root,
        "old",
        [(USER_MESSAGE, {"text": "旧的第一问"}), (ASSISTANT_MESSAGE, {"content": "旧的答案"})],
    )
    provider = FakeProvider([text_step("新答案")])

    ask(str(root), "再问一句", provider=provider, model="probe-model", session_id="old")

    assert len(provider.requests) == 1
    rows = _titles(root, "old")
    assert [row["data"]["source"]["kind"] for row in rows] == ["fallback"]
    assert rows[0]["data"]["title"] == "旧的第一问"


def test_title_bytes_and_words_limits_are_wired() -> None:
    """上限取自上游 README 示例（8 词 / 96 字节兜底；任何来源 120 字节）。"""
    long_text = "词" * 200
    assert len(normalize_title(long_text).encode("utf-8")) <= TITLE_MAX_BYTES
    assert len(fallback_title(long_text).encode("utf-8")) <= 96
