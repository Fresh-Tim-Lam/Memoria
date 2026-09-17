# 语义移植自 deepseek-harness packages/llm/llm（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""agent LLM 调用的 provider 中立词汇：消息、请求、流式事件与用量。

上游 `dsh-llm` 用「逻辑约定 provider 中立、适配器拥有协议」的方式定义消息、
内容块与流式分片；本模块是那套词汇的 Python 语义等价物（内容块收敛为文本 +
工具调用，见 `artifacts/dsh-port-llm/notes.md` 的偏差表）：

- `Message` / `ToolSchema` / `LlmRequest`：一次请求的不可变描述；
- `TextDelta` / `ReasoningDelta` / `ToolCallDelta` / `UsageEvent` / `FinishEvent`：
  适配器产出的原始流式事件，协议顺序为「`usage` 先于 `finish`，终止 `finish`
  之后不再有任何事件」；
- `Usage`：一次调用的 token 计量（`estimated=True` 表示端点未返回 usage，
  由启发式估算得出）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from memoria.services.agent.llm.errors import AgentLlmError

__all__ = [
    "FinishEvent",
    "FinishReason",
    "LlmRequest",
    "Message",
    "ReasoningDelta",
    "Role",
    "StreamEvent",
    "TextDelta",
    "ToolCall",
    "ToolCallDelta",
    "ToolSchema",
    "Usage",
    "UsageEvent",
]


class Role(str, Enum):
    """消息角色；与 OpenAI 兼容 `messages[].role` 取值一致。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(str, Enum):
    """模型响应为何结束（上游 `FinishReasonMap` 的 kind 词汇）。"""

    STOP = "stop"
    TOOL_CALLS = "tool-calls"
    MAX_TOKENS = "max-tokens"
    CONTENT_FILTER = "content-filter"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """模型请求的一次工具调用；`arguments` 保持模型产出的原始 JSON 字符串。"""

    id: str
    name: str
    arguments: str = ""


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """发给模型的工具声明（JSON Schema 描述）。"""

    name: str
    description: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Message:
    """一条对话消息；`content` 为纯文本（M1 收敛面，见 notes 偏差表）。"""

    role: Role | str
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """一次模型请求的完整描述（适配器负责映射到 provider 协议）。"""

    model: str
    messages: tuple[Message, ...] = ()
    system: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tools: tuple[ToolSchema, ...] = ()
    tool_choice: str | Mapping[str, Any] | None = None
    stream: bool = True
    timeout_s: float | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    """一次调用的 token 计量。

    `estimated=True` 表示端点没有返回 usage，字段值来自启发式估算（见
    `memoria.services.agent.llm.usage`）。`total_tokens` 为 None 时 `total`
    按 prompt + completion 求和。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int | None = None
    estimated: bool = False
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None

    @property
    def total(self) -> int:
        """完整调用总量；端点给出总量时以其为准。"""
        if self.total_tokens is not None:
            return self.total_tokens
        return self.prompt_tokens + self.completion_tokens

    def plus(self, other: Usage) -> Usage:
        """累加两次调用；任一侧为估算值则结果为估算值。"""
        total = self.total_tokens
        other_total = other.total_tokens
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=None if total is None or other_total is None else total + other_total,
            estimated=self.estimated or other.estimated,
            cache_read_tokens=_sum_optional(self.cache_read_tokens, other.cache_read_tokens),
            cache_write_tokens=_sum_optional(self.cache_write_tokens, other.cache_write_tokens),
        )


def _sum_optional(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


@dataclass(frozen=True, slots=True)
class TextDelta:
    """回答文本增量。"""

    text: str
    index: int = 0


@dataclass(frozen=True, slots=True)
class ReasoningDelta:
    """推理（思维链）文本增量；端点不提供时不会出现。"""

    text: str
    index: int = 0


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    """工具调用参数增量；同一 `index` 的多次增量按到达顺序拼接。"""

    index: int
    id: str = ""
    name: str = ""
    arguments_delta: str = ""


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """用量事件；协议上先于终止 `FinishEvent`。"""

    usage: Usage


@dataclass(frozen=True, slots=True)
class FinishEvent:
    """流的终止事件；`reason` 为 `ERROR`/`ABORTED` 时 `failure` 描述失败。

    上游约定「流始终以终止 finish 结束」，因此流内失败（连接中断、端点带内
    报错）以本事件投递；请求尚未建立或 HTTP 状态失败则直接抛
    `AgentLlmError` 子类（见 `errors.py`）。
    """

    reason: FinishReason
    usage: Usage | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    failure: AgentLlmError | None = None


StreamEvent = TextDelta | ReasoningDelta | ToolCallDelta | UsageEvent | FinishEvent
