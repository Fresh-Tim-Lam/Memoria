# 配套单测（M1 收尾「真取消」）：被测调用面为本地新增
# `services/agent/loop.py::CancelToken`（三个检查点）与
# `services/agent/ask_stream.py::AskJobManager.cancel()`。
# agent 循环语义移植自 deepseek-harness packages/core/agent-loop（MIT / BSD-3-Clause）；
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720

"""取消语义的离线单测：不联网、不写知识库正文。

覆盖（对应任务验收项）：
① **迭代边界取消**：令牌在迭代开始前已置位 ⇒ `stop_reason=aborted`、`iterations=0`、
   不发起任何模型请求、`loop/end.stop_reason="aborted"`；
② **流式过程中取消**：逐事件检查 ⇒ **立即停止消费生成器**（假 provider 的 `finally`
   被触发、后续事件不再产出），**已生成的部分文本保留**为 `answer`；
③ **工具调用后取消**：工具里置位令牌 ⇒ 本轮已产出的文本保留、不再发起下一步请求；
④ `AskJobManager.cancel()`：取消后 `poll` 给 `done`+`aborted`+部分 `answer`、
   **busy 立刻释放**（可马上再 `start`），且 `cancel()` 幂等（未知 job / 已结束 job
   都返回结构化结果而非抛异常）。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from memoria.services.agent import ask_stream
from memoria.services.agent.llm import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    Role,
    TextDelta,
    ToolCall,
)
from memoria.services.agent.loop import AgentLoop, CancelToken, StopReason
from memoria.services.agent.tools import Tool, ToolOutput, ToolRegistry

# —— 测试替身 ——


class PlainProvider:
    """按脚本产出事件；记录每次请求（用于断言"取消后不再发起请求"）。"""

    name = "plain"

    def __init__(self, script: list[list[Any]]) -> None:
        self.script = [list(step) for step in script]
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        step = self.script.pop(0) if self.script else [FinishEvent(reason=FinishReason.STOP)]
        yield from step


class CountingProvider:
    """可观察"消费到第几个事件"与"生成器是否被关闭"的假 provider。"""

    name = "counting"

    def __init__(self, total: int) -> None:
        self.total = total
        self.produced = 0
        self.closed = False

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        try:
            for index in range(self.total):
                self.produced += 1
                yield TextDelta(f"片{index}")
        finally:
            self.closed = True  # 生成器被 close()（取消）或自然耗尽时都会走到这里


def cancel_tool(token: CancelToken) -> Tool:
    """一个「调用即取消」的工具（模拟用户在工具执行期间点了停止）。"""

    def handler(_arguments: dict[str, Any]) -> ToolOutput:
        token.cancel()
        return ToolOutput(text="工具结果：已检索")

    return Tool(
        name="noop",
        description="测试用只读工具",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )


def collect_events() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
    seen: list[tuple[str, dict[str, Any]]] = []
    return seen, (lambda kind, data: seen.append((kind, dict(data))))


# —— ① 迭代边界取消 ——


def test_cancel_before_first_iteration_yields_aborted_without_requests() -> None:
    token = CancelToken()
    token.cancel()
    provider = PlainProvider([[TextDelta("不该被调用")]])
    events, on_event = collect_events()
    loop = AgentLoop(provider=provider, tools=ToolRegistry(), cancel=token, on_event=on_event)

    result = loop.run("问题")

    assert result.stop_reason is StopReason.ABORTED
    assert result.answer == ""
    assert result.iterations == 0
    assert result.error is None
    assert provider.requests == []  # 检查点①生效：一次模型请求都没发
    assert [kind for kind, _ in events] == ["loop/end"]
    assert events[0][1]["stop_reason"] == "aborted"


# —— ② 流式过程中取消（部分文本保留 + 生成器关闭）——


def test_cancel_mid_stream_stops_consuming_and_keeps_partial_text() -> None:
    token = CancelToken()
    provider = CountingProvider(total=50)
    pieces: list[str] = []

    def on_text(piece: str) -> None:
        pieces.append(piece)
        if len(pieces) >= 2:  # 收到第 2 片时取消（用户点了「停止」）
            token.cancel()

    loop = AgentLoop(provider=provider, tools=ToolRegistry(), on_text=on_text, cancel=token)
    result = loop.run("问题")

    assert result.stop_reason is StopReason.ABORTED
    assert result.answer == "片0片1"  # 已生成的部分文本保留
    assert result.error is None
    consumed_at_return = provider.produced
    assert consumed_at_return < provider.total  # 没有继续收完
    assert consumed_at_return <= 3  # 第 3 片在检查点被丢弃（不再消费）
    assert provider.closed is True  # 生成器被关闭（底层 HTTP 响应随之关闭）
    time.sleep(0.05)
    assert provider.produced == consumed_at_return  # 返回后不再产出任何事件


# —— ③ 工具调用后取消 ——


def test_cancel_after_tool_call_keeps_text_and_stops_next_request() -> None:
    token = CancelToken()
    provider = PlainProvider(
        [
            [TextDelta("先查一下："), FinishEvent(reason=FinishReason.TOOL_CALLS, tool_calls=[ToolCall(id="c1", name="noop", arguments="{}")])],
            [TextDelta("最终答案"), FinishEvent(reason=FinishReason.STOP)],
        ]
    )
    registry = ToolRegistry([cancel_tool(token)])
    events, on_event = collect_events()
    loop = AgentLoop(provider=provider, tools=registry, cancel=token, on_event=on_event)

    result = loop.run("问题")

    assert result.stop_reason is StopReason.ABORTED
    assert result.answer == "先查一下："  # 本轮已产出文本保留
    assert result.iterations == 1
    assert result.error is None
    assert len(provider.requests) == 1  # 取消后不再发起下一步请求
    assert len(result.tool_calls) == 1 and result.tool_calls[0].name == "noop"
    assert events[-1][0] == "loop/end" and events[-1][1]["stop_reason"] == "aborted"


# —— ④ 作业面取消（busy 立即释放 / poll 给 aborted / 幂等）——


def _patch_slow_ask(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """把 `ask_stream.ask` 换成"先吐一片、再等取消"的假实现。"""
    state: dict[str, Any] = {"calls": 0}

    def fake_ask(kb_path: str, question: str, **kwargs: Any) -> Any:
        state["calls"] += 1
        on_text = kwargs.get("on_text")
        cancel = kwargs.get("cancel")
        if on_text is not None:
            on_text("部分文本")
        for _ in range(600):  # 最多等 3s；正常会在收到取消后立刻退出
            if cancel is not None and cancel.is_cancelled():
                break
            time.sleep(0.005)
        state["saw_cancel"] = bool(cancel is not None and cancel.is_cancelled())
        return SimpleNamespace(
            answer="部分文本",
            anchors=(),
            tool_calls=(),
            usage={},
            session_id="session-cancel-0001",
            stop_reason="aborted",
            iterations=1,
            error=None,
        )

    monkeypatch.setattr(ask_stream, "ask", fake_ask)
    return state


def _env() -> dict[str, str]:
    return {"MEMORIA_AGENT_BASE_URL": "http://panel.example/v1"}


def test_ask_job_manager_cancel_releases_busy_and_reports_aborted(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _patch_slow_ask(monkeypatch)
    kb = tmp_path / "kb"
    kb.mkdir()
    manager = ask_stream.AskJobManager()
    env = _env()

    started = manager.start(str(kb), "第一问", env=env)
    assert started["status"] == "ok"
    job_id = started["job_id"]

    # 等首个增量到达（作业确实在跑）
    for _ in range(200):
        if manager.poll(job_id, 0)["cursor"]:
            break
        time.sleep(0.01)
    assert manager.poll(job_id, 0)["status"] == ask_stream.RUNNING

    cancelled = manager.cancel(job_id)
    assert cancelled == {
        "status": "ok",
        "job_id": job_id,
        "cancelled": True,
        "job_status": ask_stream.DONE,
    }

    snapshot = manager.poll(job_id, 0)
    assert snapshot["status"] == ask_stream.DONE
    assert snapshot["stop_reason"] == "aborted"
    assert snapshot["answer"] == "部分文本"  # 已生成的部分片段保留
    assert snapshot["cancelled"] is True

    # busy 立刻释放：取消后允许马上发起新提问
    again = manager.start(str(kb), "第二问", env=env)
    assert again["status"] == "ok" and again["job_id"] != job_id

    for _ in range(400):
        if state["calls"] >= 1 and state.get("saw_cancel"):
            break
        time.sleep(0.005)
    assert state["saw_cancel"] is True  # 取消令牌确实到达了工作线程

    # 幂等：已结束的作业再取消 ⇒ ok + cancelled:false
    done = manager.cancel(job_id)
    assert done["status"] == "ok" and done["cancelled"] is False
    # 未知作业 ⇒ 结构化错误（不抛异常）
    unknown = manager.cancel("no-such-job")
    assert unknown["status"] == "error"
    assert unknown["code"] == ask_stream.CODE_UNKNOWN_JOB
    assert unknown["cancelled"] is False
    # 空 id 同样结构化
    assert manager.cancel("")["code"] == ask_stream.CODE_UNKNOWN_JOB


def test_cancel_token_is_idempotent_and_thread_safe() -> None:
    token = CancelToken()
    assert token.is_cancelled() is False
    token.cancel()
    token.cancel()
    assert token.is_cancelled() is True
    token.reset()
    assert token.is_cancelled() is False
    # 跨线程置位后立刻可见（Event 的内存可见性）
    done = threading.Event()

    def worker() -> None:
        token.cancel()
        done.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert done.wait(1.0)
    thread.join(1.0)
    assert token.is_cancelled() is True


# —— ⑤ provider 增量读面（真取消/真流式的前提）——


def test_provider_reads_sse_incrementally_with_read1() -> None:
    """provider 必须用 `read1()` 逐块取响应体。

    `HTTPResponse.read(n)` 在「无 Content-Length / Connection: close」的 SSE 响应上会
    **阻塞到 EOF 或读满 n 字节**（实测 3.6s 的流只在结束时返回一整块），那样增量投递
    与"取消时立即停止消费生成器"都失效。此测试用**只实现 `read1` 的假响应**锁定该行为：
    一旦有人改回 `read()`，`read_calls` 断言失败。
    """
    from memoria.services.agent.llm import AgentConfig
    from memoria.services.agent.llm.providers.openai_compatible import OpenAICompatibleProvider

    frames = [
        b'data: {"choices":[{"index":0,"delta":{"content":"\\u54cd"}}]}\n\n',
        b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    class FakeResponse:
        def __init__(self) -> None:
            self.chunks = list(frames)
            self.read_calls = 0
            self.closed = False

        def read1(self, _size: int) -> bytes:
            return self.chunks.pop(0) if self.chunks else b""

        def read(self, _size: int = -1) -> bytes:
            self.read_calls += 1
            raise AssertionError("响应体必须用 read1() 增量读取，不得用 read()")

        def close(self) -> None:
            self.closed = True

    response = FakeResponse()
    provider = OpenAICompatibleProvider(
        AgentConfig(base_url="http://example.invalid/v1", model="m"),
        opener=lambda *_args, **_kwargs: response,
    )
    request = LlmRequest(model="m", messages=(Message(role=Role.USER, content="问题"),))

    events = list(provider.stream(request))

    assert response.read_calls == 0  # 从未走阻塞式 read()
    assert response.closed is True  # 流结束即关闭响应（取消时同样会走到）
    texts = [event.text for event in events if isinstance(event, TextDelta)]
    assert texts == ["响"]
    assert isinstance(events[-1], FinishEvent) and events[-1].reason is FinishReason.STOP
