# 语义移植自 deepseek-harness packages/llm/token-meter（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""用量计量：单次与累计计数，以及端点未返回 usage 时的估算。

上游 `token-meter` 用固定密度启发式（`estimate.ts`：每 4 字符 1 token，另加
块/角色结构开销）在没有精确 tokenization 时给出保守价格，并区分「provider
usage」与「estimated」两类基准（`TokenMeasurementBaseline`）。本模块保留这两点：

- `estimate_*`：文本/消息/请求的启发式价格；
- `estimate_usage`：端点未返回 usage 时构造 `Usage(estimated=True)`；
- `UsageMeter`：跨调用累计（单次 + 累计计数、估算调用计数）。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from memoria.services.agent.llm.types import LlmRequest, Message, Usage

__all__ = [
    "BLOCK_OVERHEAD",
    "CHARS_PER_TOKEN",
    "ROLE_OVERHEAD",
    "UsageMeter",
    "estimate_completion_tokens",
    "estimate_message_tokens",
    "estimate_request_tokens",
    "estimate_text_tokens",
    "estimate_tools_tokens",
    "estimate_usage",
]

#: 固定文本密度（上游 `CHARS_PER_TOKEN`）。
CHARS_PER_TOKEN = 4
#: 每个内容块的结构开销（JSON 框架与类型标记）。
BLOCK_OVERHEAD = 4
#: 每条消息的角色字段框架开销。
ROLE_OVERHEAD = 4


def estimate_text_tokens(text: str) -> int:
    """按固定密度估算一段文本的 token 数。"""
    return math.ceil(len(text or "") / CHARS_PER_TOKEN)


def estimate_tools_tokens(tools: object) -> int:
    """估算工具 schema 部分的 token 数；空声明为 0。"""
    if not tools:
        return 0
    payload = json.dumps(tools, ensure_ascii=False, default=str)
    return estimate_text_tokens(payload) + BLOCK_OVERHEAD


def estimate_message_tokens(message: Message) -> int:
    """估算一条模型可见消息的 token 数（内容密度 + 角色/块框架开销）。"""
    tokens = ROLE_OVERHEAD + estimate_text_tokens(message.content)
    if message.tool_call_id:
        tokens += estimate_text_tokens(message.tool_call_id)
    for call in message.tool_calls:
        tokens += BLOCK_OVERHEAD + estimate_text_tokens(call.name) + estimate_text_tokens(call.arguments)
    return tokens


def estimate_request_tokens(request: LlmRequest) -> int:
    """估算一次请求的输入 token 数（system + 消息 + 工具声明）。"""
    tokens = estimate_text_tokens(request.system or "")
    for message in request.messages:
        tokens += estimate_message_tokens(message)
    tool_payload = [
        {"name": tool.name, "description": tool.description, "parameters": dict(tool.parameters)}
        for tool in request.tools
    ]
    return tokens + estimate_tools_tokens(tool_payload)


def estimate_completion_tokens(text: str) -> int:
    """估算模型输出的 token 数。"""
    return estimate_text_tokens(text)


def estimate_usage(request: LlmRequest, completion_text: str = "", *, reasoning_text: str = "") -> Usage:
    """端点未返回 usage 时的估算值；结果标记 `estimated=True`。"""
    prompt_tokens = estimate_request_tokens(request)
    completion_tokens = estimate_completion_tokens(completion_text) + estimate_completion_tokens(reasoning_text)
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated=True,
    )


@dataclass(slots=True)
class UsageMeter:
    """跨调用累计用量：总量字段与调用/估算计数。

    `estimated_calls` 统计有多少次调用的 usage 来自估算而非端点上报，便于上层
    在界面上标注「用量为估算值」。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0
    estimated_calls: int = 0
    last: Usage | None = field(default=None)

    def add(self, usage: Usage) -> Usage:
        """累计一次调用的用量；返回该次用量。"""
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total
        self.cache_read_tokens += usage.cache_read_tokens or 0
        self.cache_write_tokens += usage.cache_write_tokens or 0
        self.calls += 1
        if usage.estimated:
            self.estimated_calls += 1
        self.last = usage
        return usage

    @property
    def any_estimated(self) -> bool:
        """是否至少有一次调用的用量为估算值。"""
        return self.estimated_calls > 0

    def to_dict(self) -> dict[str, int | bool | None]:
        """可序列化快照。"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "calls": self.calls,
            "estimated_calls": self.estimated_calls,
            "any_estimated": self.any_estimated,
            "last_estimated": None if self.last is None else self.last.estimated,
        }

    def reset(self) -> None:
        """清零累计计数。"""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.calls = 0
        self.estimated_calls = 0
        self.last = None
