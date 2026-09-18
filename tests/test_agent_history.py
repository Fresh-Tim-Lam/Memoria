# 配套单测（M1c 多轮续聊 + 会话历史）：被测调用面为本地新增
# `services/agent/session/history.py` 与 `ask(replay=...)`；
# 会话 JSONL 格式移植自 deepseek-harness packages/session/*（MIT / BSD-3-Clause）。
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720

"""会话历史重建 / 续聊回放 的离线单测：不联网、不写知识库正文。

覆盖（对应任务验收项）：
① 历史重建的**序列合法性**（assistant.tool_calls 与随后的 tool 消息一一配对）；
② 容量上限截断（从最新往旧保留，且不留孤儿 tool 消息）；
③ 续聊：两次 `ask()` 用同一 `session_id`，第二次请求体内含第一轮消息；
④ 全新会话不带历史；⑤ `replay=False` 时不回放；⑥ 会话文件里 `user/message` 2 条且 `seq` 连续。
另覆盖 `agent_sessions_list` / `agent_session_load` 所依赖的
`summarize_session()` 与 `conversation_messages()`。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.ask import ask
from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    Role,
    TextDelta,
    ToolCall,
    Usage,
    UsageEvent,
)
from memoria.services.agent.session.history import (
    MAX_HISTORY_CHARS,
    MAX_HISTORY_MESSAGES,
    build_history,
    conversation_messages,
    summarize_session,
)
from memoria.services.agent.session.store import SessionStore, new_session_id, read_session

NEURAL_MD = """# 神经网络

## 感知机

最古老的线性分类器。

## 多层感知机

MLP 由多层全连接组成。
"""

NEURAL_SIDECAR = """schema_version: 1
file: neural-network.md
knowledge_points:
- id: perceptron
  name: 感知机
  tags:
  - 神经网络
  range:
    start:
      snippet: '## 感知机'
      line_hint: 3
    end:
      snippet: 最古老的线性分类器。
      line_hint: 5
- id: mlp
  name: 多层感知机
  tags:
  - 神经网络
  range:
    start:
      snippet: '## 多层感知机'
      line_hint: 7
    end:
      snippet: MLP 由多层全连接组成。
      line_hint: 9
"""


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库：一篇文档 + 一个 sidecar（搜索工具据此产出锚点）。"""
    root = tmp_path / "kb"
    (root / ".memoria" / "sidecars").mkdir(parents=True)
    (root / ".memoria" / "agent").mkdir(parents=True)
    (root / "neural-network.md").write_text(NEURAL_MD, encoding="utf-8")
    (root / ".memoria" / "sidecars" / "neural-network.memoria.yaml").write_text(
        NEURAL_SIDECAR, encoding="utf-8"
    )
    return root


# —— 测试替身 ——


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


def tool_step(*calls: ToolCall) -> list[Any]:
    return [FinishEvent(reason=FinishReason.TOOL_CALLS, tool_calls=calls)]


def role_of(message: Message) -> str:
    role = message.role
    return role.value if isinstance(role, Role) else str(role)


def assert_legal_sequence(messages: Sequence[Message]) -> None:
    """断言 OpenAI 兼容协议的结构约束：assistant.tool_calls 后必须紧跟配对的 tool 消息。"""
    pending: list[str] = []
    for message in messages:
        role = role_of(message)
        if role == "tool":
            assert pending, f"出现孤儿 tool 消息：{message!r}"
            assert message.tool_call_id == pending.pop(0), f"tool_call_id 与调用顺序不符：{message!r}"
            continue
        assert not pending, f"assistant.tool_calls 未被 tool 消息跟上：{pending}"
        if role == "assistant":
            assert all(call.id for call in message.tool_calls), f"tool_calls 含空 id：{message!r}"
            pending = [call.id for call in message.tool_calls]
    assert not pending, f"序列以未配对的 tool_calls 结束：{pending}"


def session_events(kb: Path, session_id: str) -> list[dict[str, Any]]:
    return [row for row in read_session(str(kb), session_id) if isinstance(row.get("seq"), int)]


# —— ① 序列合法性（配对保留 / 异常轮成对丢弃）——


def test_build_history_replays_tool_round_and_stays_legal(kb: Path) -> None:
    session_id = "session-history-0001"
    store = SessionStore(str(kb), session_id)
    arguments = json.dumps({"query": "多层感知机"}, ensure_ascii=False)
    store.append("user/message", {"text": "多层感知机在哪？"})
    store.append(
        "assistant/message",
        {
            "iteration": 1,
            "content": "我查一下。",
            "tool_calls": [{"id": "c1", "name": "search_kb", "arguments": arguments}],
        },
    )
    store.append("tool/call", {"id": "c1", "name": "search_kb", "arguments": arguments})
    store.append(
        "tool/result",
        {"id": "c1", "name": "search_kb", "is_error": False, "code": "ok", "content": "neural-network.md:7", "anchors": []},
    )
    store.append("assistant/message", {"iteration": 2, "content": "见 `neural-network.md:7`。", "tool_calls": []})
    store.append("loop/end", {"stop_reason": "final-answer"})

    history = build_history(str(kb), session_id)

    assert [role_of(message) for message in history] == ["user", "assistant", "tool", "assistant"]
    assert history[1].tool_calls == (ToolCall(id="c1", name="search_kb", arguments=arguments),)
    assert history[2].tool_call_id == "c1" and history[2].name == "search_kb"
    assert history[3].content == "见 `neural-network.md:7`。"
    assert_legal_sequence(history)  # 全保真：tool 轮原样回放


def test_build_history_drops_unpaired_tool_round(kb: Path) -> None:
    """`tool_calls` 没有配对结果（进程崩在工具执行中途）⇒ 整轮丢弃，不留孤立 tool_calls。"""
    session_id = "session-history-0002"
    store = SessionStore(str(kb), session_id)
    store.append("user/message", {"text": "第一问"})
    store.append(
        "assistant/message",
        {
            "iteration": 1,
            "content": "我查一下。",
            "tool_calls": [
                {"id": "c1", "name": "search_kb", "arguments": "{}"},
                {"id": "c2", "name": "read_kp", "arguments": "{}"},
            ],
        },
    )
    store.append("tool/result", {"id": "c1", "name": "search_kb", "content": "只有一半结果", "anchors": []})
    store.append("assistant/message", {"iteration": 2, "content": "收尾答案", "tool_calls": []})

    history = build_history(str(kb), session_id)

    assert [role_of(message) for message in history] == ["user", "assistant"]
    assert history[1].content == "收尾答案" and history[1].tool_calls == ()
    assert_legal_sequence(history)


def test_build_history_skips_orphan_tool_result(kb: Path) -> None:
    session_id = "session-history-0003"
    store = SessionStore(str(kb), session_id)
    store.append("tool/result", {"id": "c9", "name": "search_kb", "content": "孤儿结果", "anchors": []})
    store.append("user/message", {"text": "在吗"})

    history = build_history(str(kb), session_id)

    assert [role_of(message) for message in history] == ["user"]
    assert_legal_sequence(history)


# —— ② 容量上限与截断策略 ——


def test_build_history_truncates_from_newest(kb: Path) -> None:
    session_id = "session-history-0004"
    store = SessionStore(str(kb), session_id)
    for index in range(6):
        store.append("user/message", {"text": f"问{index}"})
        store.append("assistant/message", {"content": f"答{index}", "tool_calls": []})

    history = build_history(str(kb), session_id, max_messages=4)

    assert len(history) == 4
    assert [message.content for message in history] == ["问4", "答4", "问5", "答5"]  # 从最新往旧保留
    assert_legal_sequence(history)


def test_build_history_truncates_by_chars(kb: Path) -> None:
    session_id = "session-history-0005"
    store = SessionStore(str(kb), session_id)
    store.append("user/message", {"text": "旧" * 50})
    store.append("assistant/message", {"content": "旧答" * 50, "tool_calls": []})
    store.append("user/message", {"text": "新问"})
    store.append("assistant/message", {"content": "新答", "tool_calls": []})

    history = build_history(str(kb), session_id, max_chars=20)

    assert [message.content for message in history] == ["新问", "新答"]  # 至少保留最新 1 条且不超预算
    assert_legal_sequence(history)


def test_build_history_never_leads_with_tool_message(kb: Path) -> None:
    """截断到只剩 tool 消息时，前导 tool 消息被丢弃（不产生孤儿 tool）。"""
    session_id = "session-history-0006"
    store = SessionStore(str(kb), session_id)
    store.append("user/message", {"text": "问"})
    store.append(
        "assistant/message",
        {"content": "", "tool_calls": [{"id": "c1", "name": "search_kb", "arguments": "{}"}]},
    )
    store.append("tool/result", {"id": "c1", "name": "search_kb", "content": "结果", "anchors": []})

    assert build_history(str(kb), session_id, max_messages=1) == []  # 只剩 tool ⇒ 丢弃
    assert_legal_sequence(build_history(str(kb), session_id, max_messages=2))

    assert MAX_HISTORY_MESSAGES == 40 and MAX_HISTORY_CHARS == 32_000


# —— ③④⑤⑥ 续聊回放（经 `ask()`，假 provider 捕获请求）——


def test_resume_sends_previous_round_in_request(kb: Path) -> None:
    session_id = "session-resume-0001"
    first = FakeProvider([text_step("答案一")])
    second = FakeProvider([text_step("答案二")])

    result1 = ask(str(kb), "第一问", provider=first, model="fake-model", session_id=session_id)
    result2 = ask(str(kb), "第二问", provider=second, model="fake-model", session_id=session_id)

    assert result1.session_id == session_id == result2.session_id
    assert result2.session_path == result1.session_path

    sent = list(second.requests[0].messages)
    assert [role_of(message) for message in sent] == ["user", "assistant", "user"]
    assert [message.content for message in sent] == ["第一问", "答案一", "第二问"]
    assert_legal_sequence(sent)

    events = session_events(kb, session_id)
    assert [row["type"] for row in events if row["type"] == "user/message"] == ["user/message"] * 2
    assert [row["data"]["text"] for row in events if row["type"] == "user/message"] == ["第一问", "第二问"]
    assert [row["seq"] for row in events] == list(range(len(events)))  # seq 连续无缺口


def test_fresh_session_sends_no_history(kb: Path) -> None:
    provider = FakeProvider([text_step("答案")])

    result = ask(str(kb), "只有这一问", provider=provider, model="fake-model", session_id="session-fresh-0001")

    sent = list(provider.requests[0].messages)
    assert len(sent) == 1 and sent[0].content == "只有这一问" and role_of(sent[0]) == "user"
    assert result.session_id == "session-fresh-0001"


def test_unknown_session_id_is_a_fresh_session(kb: Path) -> None:
    provider = FakeProvider([text_step("答案")])

    ask(str(kb), "问题", provider=provider, model="fake-model", session_id=new_session_id())

    sent = list(provider.requests[0].messages)
    assert [message.content for message in sent] == ["问题"]  # 文件不存在 ⇒ 无历史


def test_replay_disabled_sends_only_current_question(kb: Path) -> None:
    session_id = "session-replay-off-0001"
    ask(str(kb), "第一问", provider=FakeProvider([text_step("答案一")]), model="fake-model", session_id=session_id)
    third = FakeProvider([text_step("答案三")])

    ask(
        str(kb),
        "第三问",
        provider=third,
        model="fake-model",
        session_id=session_id,
        replay=False,
    )

    sent = list(third.requests[0].messages)
    assert [message.content for message in sent] == ["第三问"]


# —— 会话列表/载入所依赖的只读视图 ——


def test_summarize_and_conversation_view_with_anchors(kb: Path) -> None:
    session_id = "session-view-0001"
    provider = FakeProvider(
        [
            tool_step(ToolCall(id="c1", name="search_kb", arguments=json.dumps({"query": "多层感知机"}))),
            text_step("多层感知机见 `neural-network.md:7`。"),
        ]
    )
    ask(str(kb), "多层感知机讲的是什么？", provider=provider, model="fake-model", session_id=session_id)

    summary = summarize_session(str(kb), session_id)
    assert summary["turn_count"] == 1
    assert summary["preview"] == "多层感知机讲的是什么？"
    assert summary["title"] == "多层感知机讲的是什么？"

    view = conversation_messages(str(kb), session_id)
    # 一轮只出一条 assistant 气泡 = 该轮最后一条非空 assistant/message（工具轮前言不入气泡）
    assert [item["role"] for item in view] == ["user", "assistant"]
    assert view[1]["text"] == "多层感知机见 `neural-network.md:7`。"
    anchors = view[1]["anchors"]
    assert any(anchor["file"] == "neural-network.md" and anchor["line"] == 7 for anchor in anchors)
    # 锚点按轮归属：user 气泡不带锚点
    assert "anchors" not in view[0]

    assert summarize_session(str(kb), "session-does-not-exist") == {
        "turn_count": 0,
        "preview": "",
        "title": "",
    }
    assert conversation_messages(str(kb), "session-does-not-exist") == []
