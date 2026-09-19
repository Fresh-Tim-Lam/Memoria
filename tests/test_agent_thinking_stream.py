# 配套单测（AG08「模型思考流进面板」）：思考流**只流式、不落盘**。
# 被测调用面：services/agent/loop.py 的 `on_reasoning` 透传、
# services/agent/ask_stream.py 的 `AskJob.note_reasoning` / `snapshot` 双游标 /
# `AskJobManager.poll(reasoning_cursor)`。
# agent 循环语义移植自 deepseek-harness packages/core/agent-loop（MIT / BSD-3-Clause）；
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720

"""思考流的离线单测：不联网、不写知识库正文。

覆盖（对应任务验收项）：
① **循环层**：假 provider 交错产出 `ReasoningDelta` / `TextDelta` ⇒ `on_reasoning` /
   `on_text` 各自收到正确片段且**顺序与到达一致**；思考**不混入** `answer`；
② **只有思考、没有正文**的轮次仍正常终止（`answer == ""`、`stop_reason=final-answer`）；
③ **作业层游标**：`note_reasoning` 追加、`snapshot` 的 `reasoning_delta` /
   `reasoning_cursor` 与文本游标**完全独立**、按游标增量投递**不重放**、空片段不入缓冲；
④ **管理器端到端**：工作线程把 `on_reasoning` 接进 `note_reasoning`，`poll` 增量拼回
   完整思考且正文 `delta` 语义不变；思考-only 轮次报 `done` + 空 `answer`。
"""

from __future__ import annotations

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
    ReasoningDelta,
    TextDelta,
)
from memoria.services.agent.loop import AgentLoop, StopReason
from memoria.services.agent.tools import ToolRegistry

# —— 测试替身 ——


class ScriptProvider:
    """按一份固定脚本产出事件，并记录请求（本测试只跑单步，无需分步脚本）。"""

    name = "script"

    def __init__(self, step: list[Any]) -> None:
        self.step = list(step)
        self.requests: list[LlmRequest] = []

    def stream(self, request: LlmRequest) -> Iterator[Any]:
        self.requests.append(request)
        yield from self.step


# —— ① 循环层：思考与正文分流且保序 ——


def test_loop_delivers_reasoning_and_text_separately_in_order() -> None:
    provider = ScriptProvider(
        [
            ReasoningDelta("先想一想"),
            TextDelta("答案"),
            ReasoningDelta("再补一句"),
            FinishEvent(reason=FinishReason.STOP),
        ]
    )
    seen: list[tuple[str, str]] = []
    loop = AgentLoop(
        provider=provider,
        tools=ToolRegistry(),
        on_text=lambda piece: seen.append(("text", piece)),
        on_reasoning=lambda piece: seen.append(("reasoning", piece)),
    )

    result = loop.run("问题")

    assert seen == [
        ("reasoning", "先想一想"),
        ("text", "答案"),
        ("reasoning", "再补一句"),
    ]
    assert result.answer == "答案"  # 思考不混入答案
    assert "先想一想" not in result.answer and "再补一句" not in result.answer
    assert result.stop_reason is StopReason.FINAL_ANSWER
    assert len(provider.requests) == 1


def test_loop_without_on_reasoning_still_records_for_usage() -> None:
    """未接线 `on_reasoning` 时不得抛错，思考仍进 `reasoning_parts` 供估算用量。"""
    provider = ScriptProvider([ReasoningDelta("思考"), FinishEvent(reason=FinishReason.STOP)])
    loop = AgentLoop(provider=provider, tools=ToolRegistry())

    result = loop.run("问题")

    assert result.answer == ""
    assert result.stop_reason is StopReason.FINAL_ANSWER
    assert result.error is None


# —— ② 只有思考、没有正文 ——


def test_loop_reasoning_only_turn_terminates_with_empty_answer() -> None:
    provider = ScriptProvider(
        [ReasoningDelta("只想不答"), FinishEvent(reason=FinishReason.STOP)]
    )
    pieces: list[str] = []
    loop = AgentLoop(provider=provider, tools=ToolRegistry(), on_reasoning=pieces.append)

    result = loop.run("问题")

    assert pieces == ["只想不答"]
    assert result.answer == ""
    assert result.stop_reason is StopReason.FINAL_ANSWER
    assert result.error is None


# —— ③ 作业层游标：独立、增量、不重放 ——


def test_ask_job_reasoning_cursor_is_independent_and_never_replays() -> None:
    job = ask_stream.AskJob(job_id="job-1", kb_path="", question="q")
    job.note_reasoning("甲")
    job.note_reasoning("乙")
    job.note_delta("x")

    first = job.snapshot(0, 0)
    assert first["delta"] == "x" and first["cursor"] == 1
    assert first["reasoning_delta"] == "甲乙" and first["reasoning_cursor"] == 2

    # 两个游标互不影响：文本游标推进不改变思考投递；思考游标推进不改变文本投递
    second = job.snapshot(1, 1)
    assert second["delta"] == "" and second["cursor"] == 1
    assert second["reasoning_delta"] == "乙" and second["reasoning_cursor"] == 2

    # 思考游标已到末尾 ⇒ 不重放
    third = job.snapshot(1, 2)
    assert third["reasoning_delta"] == "" and third["reasoning_cursor"] == 2
    # 文本侧语义保持原样：越界游标回落到 0 重放
    assert job.snapshot(99, 0)["delta"] == "x"


def test_ask_job_note_reasoning_ignores_empty_pieces() -> None:
    job = ask_stream.AskJob(job_id="job-2", kb_path="", question="q")
    job.note_reasoning("")
    job.note_reasoning("思")

    snap = job.snapshot(0, 0)
    assert snap["reasoning_delta"] == "思" and snap["reasoning_cursor"] == 1


# —— ④ 管理器端到端：worker 接线 + poll 增量 + 思考-only ——


def _patch_reasoning_ask(
    monkeypatch: pytest.MonkeyPatch, *, answer: str, reasoning: tuple[str, ...]
) -> None:
    """把 `ask_stream.ask` 换成"先吐思考、再吐正文"的假实现。"""

    def fake_ask(kb_path: str, question: str, **kwargs: Any) -> Any:
        on_text = kwargs.get("on_text")
        on_reasoning = kwargs.get("on_reasoning")
        for piece in reasoning:
            if on_reasoning is not None:
                on_reasoning(piece)
        if answer and on_text is not None:
            on_text(answer)
        return SimpleNamespace(
            answer=answer,
            anchors=(),
            tool_calls=(),
            usage={},
            session_id="session-think-0001",
            stop_reason="final-answer",
            iterations=1,
            error=None,
        )

    monkeypatch.setattr(ask_stream, "ask", fake_ask)


def _env() -> dict[str, str]:
    return {"MEMORIA_AGENT_BASE_URL": "http://panel.example/v1"}


def _drain(manager: ask_stream.AskJobManager, job_id: str) -> tuple[str, str, dict[str, Any]]:
    """按两个游标轮询到作业结束，返回（累积思考, 累积正文, 末次快照）。"""
    reason, text, rc, tc = "", "", 0, 0
    snap: dict[str, Any] = {}
    for _ in range(400):
        snap = manager.poll(job_id, tc, rc)
        reason += str(snap.get("reasoning_delta") or "")
        text += str(snap.get("delta") or "")
        rc = int(snap.get("reasoning_cursor") or 0)
        tc = int(snap.get("cursor") or 0)
        if snap.get("status") != ask_stream.RUNNING:
            break
        time.sleep(0.005)
    return reason, text, snap


def test_manager_poll_streams_reasoning_incrementally(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_reasoning_ask(monkeypatch, answer="最终答案", reasoning=("思考一", "思考二"))
    kb = tmp_path / "kb"
    kb.mkdir()
    manager = ask_stream.AskJobManager()

    started = manager.start(str(kb), "问题", env=_env())
    assert started["status"] == "ok"

    reason, text, snap = _drain(manager, started["job_id"])

    assert snap["status"] == ask_stream.DONE
    assert reason == "思考一思考二"  # 按游标增量拼回完整思考，不重放、不遗漏
    assert text == "最终答案"  # 正文侧语义不变
    assert snap["reasoning_cursor"] == len("思考一思考二")
    assert snap["cursor"] == len("最终答案")


def test_manager_reasoning_only_turn_reports_done_with_empty_answer(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_reasoning_ask(monkeypatch, answer="", reasoning=("只想不答",))
    kb = tmp_path / "kb"
    kb.mkdir()
    manager = ask_stream.AskJobManager()

    started = manager.start(str(kb), "问题", env=_env())
    reason, text, snap = _drain(manager, started["job_id"])

    assert snap["status"] == ask_stream.DONE
    assert reason == "只想不答"
    assert text == "" and snap["answer"] == ""
    assert snap["reasoning_cursor"] == len("只想不答")
    assert snap["stop_reason"] == "final-answer"


def test_manager_poll_tolerates_bad_reasoning_cursor(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非数字思考游标按 0 处理（与文本游标同一兜底，不抛异常）。"""
    _patch_reasoning_ask(monkeypatch, answer="答", reasoning=("思",))
    kb = tmp_path / "kb"
    kb.mkdir()
    manager = ask_stream.AskJobManager()

    started = manager.start(str(kb), "问题", env=_env())
    for _ in range(400):
        snap = manager.poll(started["job_id"], 0, "bad")  # type: ignore[arg-type]
        if snap.get("status") != ask_stream.RUNNING:
            break
        time.sleep(0.005)

    assert snap["status"] == ask_stream.DONE
    assert snap["reasoning_delta"] == "思"  # 游标 0 ⇒ 整段重放一次，无异常
