# 语义移植自 deepseek-harness packages/core/agent-loop（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""Agent 循环：模型 → 工具调用 → 结果回填 → 再问模型。

对照上游 `dsh-agent-loop` 的单步语义（`src/agent.ts`）：

| 上游 | 本地 |
|---|---|
| 一步 = 一次流式模型请求 + 其工具分发 | 一次 `for` 迭代 |
| `finish.kind === 'max-tokens'` ⇒ 终止 | `StopReason.MAX_TOKENS` |
| `toolCalls.length === 0` ⇒ `{ kind: 'completed' }` | `StopReason.FINAL_ANSWER` |
| 工具结果一律回填进会话日志，下一步据此重建请求 | 结果以 `role=tool` 消息追加，下一步整份历史重发 |
| 没有内置轮次预算（上游已知限制：靠 `agent/turn-stopping` 取消） | `max_iterations`（默认 8）硬上限 ⇒ `StopReason.MAX_ITERATIONS` |
| 流内失败以带 `failure` 的终止事件投递 | 同样：终止事件带 `failure` ⇒ `StopReason.ERROR`，已投递文本保留 |

未移植：并行工具调度与独占屏障（`maxParallelToolCalls`/`tool-calls.ts`）、
会话（`session`/`inbox`）、runtime context 快照、请求 header 冻结。
M1 串行执行工具、同步阻塞；**取消为协作式**（M1 收尾新增 `CancelToken`，
见其 docstring）：只在三个检查点观察（每轮迭代前、流式逐事件、每次工具调用后），
故"取消"不打断正在阻塞的 socket 读，但会**立即停止消费生成器**（`stream.close()`
令 provider 的 `with closing(response)` 关闭底层 HTTP 响应，不再收完剩余分片）。

provider 与工具集都在构造时注入，因此本模块**不联网、不读配置**，可用脚本化
假 provider 完整离线验证。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from memoria.services.agent.approvals import DEFAULT_POLICY, ApprovalPolicy
from memoria.services.agent.llm import (
    AgentLlmError,
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    ReasoningDelta,
    RetryPolicy,
    Role,
    TextDelta,
    ToolSchema,
    Usage,
    UsageEvent,
    UsageMeter,
    estimate_usage,
    iter_with_retry,
)
from memoria.services.agent.tools.registry import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "AgentLoop",
    "CancelToken",
    "LoopResult",
    "StopReason",
    "usage_payload",
]

#: 单次提问允许的最大模型步数（上游无内置预算，此处是 M1 的安全上界）。
DEFAULT_MAX_ITERATIONS = 8


class CancelToken:
    """轻量取消令牌（跨线程安全、幂等）。

    M1 的 agent 循环是**同步阻塞**的，取消只能**协作式**完成：RPC 线程调
    `cancel()`，工作线程在检查点观察到后主动收敛（`StopReason.ABORTED`）。

    选 `threading.Event` 而非"裸可调用对象"，理由：
    ① `Event` 自带内存可见性与线程安全，跨线程写后读无需额外锁、无竞态；
    ② `is_cancelled()` 名字明确——可调用对象容易被误传成 `bool` 或返回非布尔值；
    ③ `cancel()` 幂等，同一令牌可被作业面（`AskJob`）与循环共用；
    ④ 与 `AskJob.lock` 无耦合，不引入锁顺序问题，也不会在持锁时回调用户代码。
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """请求取消（幂等；可从任意线程调用）。"""
        self._event.set()

    def is_cancelled(self) -> bool:
        """是否已请求取消。"""
        return self._event.is_set()

    def reset(self) -> None:
        """清除取消标志（令牌复用/测试用）。"""
        self._event.clear()


class StopReason(str, Enum):
    """循环为何结束。"""

    FINAL_ANSWER = "final-answer"
    MAX_ITERATIONS = "max-iterations"
    MAX_TOKENS = "max-tokens"
    CONTENT_FILTER = "content-filter"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class LoopResult:
    """一次循环的完整结果。"""

    answer: str
    stop_reason: StopReason
    iterations: int
    messages: tuple[Message, ...]
    tool_calls: tuple[ToolResult, ...]
    anchors: tuple[Mapping[str, Any], ...]
    usage: Usage
    error: str | None = None

    def usage_dict(self) -> dict[str, int | bool | None]:
        """用量的可序列化快照（对齐 `UsageMeter.to_dict()` 的字段命名）。"""
        return usage_payload(self.usage)


def usage_payload(usage: Usage) -> dict[str, int | bool | None]:
    """`Usage` → 可序列化载荷；`loop/end` 事件、`AskResult.usage` 与压缩/标题事件共用同一形状。"""
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total,
        "estimated": usage.estimated,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "cache_miss_tokens": usage.cache_miss_tokens,
    }


def _retry_note(message: str, retries: int) -> str:
    """最终错误串：附上"（已重试 N 次）"；`retries == 0` 时原样返回。"""
    if retries <= 0:
        return message
    return f"{message}（已重试 {retries} 次）"


class AgentLoop:
    """同步 agent 循环；provider、工具集、审批策略全部注入。"""

    def __init__(
        self,
        *,
        provider: Any,
        tools: ToolRegistry,
        model: str = "",
        system: str | None = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_s: float | None = None,
        approval: ApprovalPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        meter: UsageMeter | None = None,
        on_text: Callable[[str], None] | None = None,
        on_event: Callable[[str, Mapping[str, Any]], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations 必须为正整数")
        self.provider = provider
        self.tools = tools
        self.model = model
        self.system = system
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.approval = approval if approval is not None else DEFAULT_POLICY
        self.retry_policy = retry_policy
        self.meter = meter if meter is not None else UsageMeter()
        self.on_text = on_text
        self.on_event = on_event
        self.cancel = cancel

    # —— 内部 ——

    def _emit(self, event_type: str, data: Mapping[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event_type, data)
        except Exception as exc:  # noqa: BLE001 — 观测回调失败不得打断循环
            logger.warning("[agent-loop] 事件回调失败（%s）：%r", event_type, exc)

    def _schemas(self) -> tuple[ToolSchema, ...]:
        return self.tools.schemas()

    def _request(self, history: Sequence[Message]) -> LlmRequest:
        return LlmRequest(
            model=self.model,
            messages=tuple(history),
            system=self.system,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=self._schemas(),
            stream=True,
            timeout_s=self.timeout_s,
        )

    def _cancelled(self) -> bool:
        """是否已请求取消（无令牌者恒为 False）。"""
        return self.cancel is not None and self.cancel.is_cancelled()

    def _stream_once(
        self, request: LlmRequest, retry_counter: list[int]
    ) -> tuple[str, Usage | None, FinishEvent | None]:
        """跑完一次模型流；返回（文本, 用量, 终止事件）。

        `retry_counter`（单元素列表，调用方持有）记录本步**已发生的重试次数**：
        `iter_with_retry` 重试发生在流内部，抛错时无法从返回值带回，故用计数器
        让调用方在 `step/error` 与最终错误串里如实呈现"已重试 N 次"。

        取消检查点②：**逐个事件**观察取消令牌；一旦取消即 `break` 并在 `finally`
        中 `stream.close()`——这把 `GeneratorExit` 抛进 `iter_with_retry`，进而令
        provider 的 `with closing(response)` 关闭底层 HTTP 响应，剩余分片不再收。
        """
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage: Usage | None = None
        finish: FinishEvent | None = None

        def on_retry(attempt: int, delay: float, exc: BaseException) -> None:
            retry_counter[0] = attempt
            logger.warning("[agent-loop] 第 %d 次重试（等待 %.2fs 后）：%r", attempt, delay, exc)

        stream = iter_with_retry(
            lambda: self.provider.stream(request),
            policy=self.retry_policy,
            on_retry=on_retry,
        )
        try:
            for event in stream:
                if self._cancelled():
                    break
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                    if self.on_text is not None:
                        self.on_text(event.text)
                elif isinstance(event, ReasoningDelta):
                    reasoning_parts.append(event.text)
                elif isinstance(event, UsageEvent):
                    usage = event.usage if usage is None else usage.plus(event.usage)
                    self.meter.add(event.usage)
                elif isinstance(event, FinishEvent):
                    finish = event
        finally:
            # 正常跑完/抛错时 close() 是空操作；取消 break 时它立即关闭底层响应。
            stream.close()
        text = "".join(text_parts)
        if usage is None and finish is not None and finish.usage is not None:
            usage = finish.usage
            self.meter.add(finish.usage)
        if usage is None:
            usage = estimate_usage(request, text, reasoning_text="".join(reasoning_parts))
            self.meter.add(usage)
        return text, usage, finish

    # —— 主流程 ——

    def run(
        self,
        question: str | None = None,
        *,
        messages: Sequence[Message] | None = None,
    ) -> LoopResult:
        """跑一轮问答：从（可选）新提问开始，直到给出最终答案或触发终止条件。"""
        history: list[Message] = list(messages or ())
        if question is not None:
            history.append(Message(role=Role.USER, content=question))

        tool_results: list[ToolResult] = []
        anchors: list[Mapping[str, Any]] = []
        usage = Usage()
        answer = ""
        error: str | None = None
        stop_reason = StopReason.MAX_ITERATIONS
        iterations = 0

        for iteration in range(1, self.max_iterations + 1):
            # 取消检查点①：每轮迭代开始前
            if self._cancelled():
                stop_reason = StopReason.ABORTED
                break
            iterations = iteration
            request = self._request(history)
            self._emit("step/start", {"iteration": iteration, "message_count": len(history)})
            retry_counter = [0]
            try:
                text, step_usage, finish = self._stream_once(request, retry_counter)
            except AgentLlmError as exc:
                self._emit(
                    "step/error",
                    {"iteration": iteration, "error": repr(exc), "retries": retry_counter[0]},
                )
                stop_reason, error = StopReason.ERROR, _retry_note(str(exc), retry_counter[0])
                break
            if step_usage is not None:
                usage = usage.plus(step_usage)
            if text:
                answer = text

            # 取消检查点②的收口：流式消费中被取消（`_stream_once` 已停止消费并关闭
            # 生成器），此时 `finish` 多半为 None —— 必须**先于**"无终止事件"判定，
            # 否则取消会被误报成 ERROR。保留已生成的部分文本作为 answer。
            if self._cancelled():
                stop_reason = StopReason.ABORTED
                break

            if finish is None:
                stop_reason, error = StopReason.ERROR, "模型流未给出终止事件"
                break
            if finish.failure is not None:
                stop_reason = StopReason.ERROR
                error = _retry_note(str(finish.failure), retry_counter[0])
                break
            if finish.reason is FinishReason.ABORTED:
                stop_reason = StopReason.ABORTED
                break
            if finish.reason is FinishReason.CONTENT_FILTER:
                stop_reason = StopReason.CONTENT_FILTER
                break

            history.append(Message(role=Role.ASSISTANT, content=text, tool_calls=finish.tool_calls))
            self._emit(
                "assistant/message",
                {
                    "iteration": iteration,
                    "content": text,
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in finish.tool_calls
                    ],
                },
            )

            if finish.reason is FinishReason.MAX_TOKENS:
                # 对齐上游：max-tokens 是终止条件，先于工具分发判定
                stop_reason = StopReason.MAX_TOKENS
                break
            if not finish.tool_calls:
                stop_reason = StopReason.FINAL_ANSWER
                break

            aborted = False
            for call in finish.tool_calls:
                result = self.tools.invoke(call, approval=self.approval)
                tool_results.append(result)
                anchors.extend(result.output.anchors)
                history.append(
                    Message(role=Role.TOOL, content=result.content, tool_call_id=call.id, name=result.name)
                )
                self._emit("tool/call", {"id": call.id, "name": call.name, "arguments": call.arguments})
                self._emit(
                    "tool/result",
                    {
                        "id": call.id,
                        "name": result.name,
                        "is_error": result.is_error,
                        "code": result.output.code,
                        "content": result.content,
                        "anchors": [dict(anchor) for anchor in result.output.anchors],
                    },
                )
                # 取消检查点③：每次工具调用之后（工具本身很短、不设内部中断点）
                if self._cancelled():
                    aborted = True
                    break
            if aborted:
                stop_reason = StopReason.ABORTED
                break
        else:
            stop_reason = StopReason.MAX_ITERATIONS

        self._emit(
            "loop/end",
            {
                "stop_reason": stop_reason.value,
                "iterations": iterations,
                "usage": usage_payload(usage),
                "error": error,
            },
        )
        return LoopResult(
            answer=answer,
            stop_reason=stop_reason,
            iterations=iterations,
            messages=tuple(history),
            tool_calls=tuple(tool_results),
            anchors=tuple(anchors),
            usage=usage,
            error=error,
        )
