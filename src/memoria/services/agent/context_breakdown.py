"""会话上下文的**结构化拆分**（DSH `contextBreakdown` 的 Memoria 版）。

DSH 的 ContextMeter 把上下文拆成 system / tools / messages 三段 token；
Memoria 的请求历史本身是**字符预算**（`MAX_HISTORY_CHARS = 32_000`），因此这里
不伪造 provider 的精确 token，而是返回：

- 三段各自的**字符数**（唯一真实口径）；
- 由字符数按 `chars / 4` 估算的 token（明确标记 `estimated`，供 UI 显示量级）；
- 已有的字符预算事实（`max_chars` / `threshold_chars` / `compacted_times`）。

唯一事实源：
- system 文本 = `prompt.build_system_prompt(...)`（与 `ask.py` 同一调用）；
- tools 文本 = `ToolRegistry.schemas()` 的 JSON（与 wire 请求同源）；
- messages 文本 = `history.build_history(...)`（与请求历史同源）。

本模块只读；任何读盘/构建失败由调用方降级，不改变会话状态。
"""

from __future__ import annotations

import json
import math
from typing import Any

from memoria.services.agent.session.history import MAX_HISTORY_CHARS, build_history
from memoria.services.agent.session.history import session_context_usage

__all__ = ["build_context_breakdown", "estimate_tokens"]

#: 粗略 token 估算：4 字符 ≈ 1 token（与 DSH 的启发式 breakdown 同量级，不是 provider 计费值）。
CHARS_PER_TOKEN = 4


def estimate_tokens(chars: int) -> int:
    """字符数 → 估算 token（向上取整；0 保持 0）。"""
    return int(math.ceil(max(0, int(chars)) / CHARS_PER_TOKEN))


def _message_chars(messages) -> int:
    total = 0
    for message in messages:
        total += len(message.content or "")
        for call in message.tool_calls or ():
            total += len(call.arguments or "")
            total += len(call.name or "")
        if message.name:
            total += len(message.name)
        total += len(message.tool_call_id or "")
        for image in message.images or ():
            # 图片本身不计字符；其占位/描述在 content 中，如果未来加 base64 再按字节算。
            total += 0
    return total


def _tools_chars(schemas) -> int:
    if not schemas:
        return 0
    return len(json.dumps(schemas, ensure_ascii=False, separators=(",", ":"), default=str))


def build_context_breakdown(
    kb_path: str,
    session_id: str,
    model: str | None = None,
    *,
    max_chars: int = MAX_HISTORY_CHARS,
) -> dict[str, Any]:
    """构建 system / tools / messages 三段字符拆分（只读）。

    `model` 为空时沿用配置默认模型；工具注册失败时退化为空工具集（只影响 tools 段，
    不阻断 system/messages 的读数）。
    """
    from memoria.services.agent.prompt import build_system_prompt
    from memoria.services.agent.tools.kb import build_kb_tools
    from memoria.services.agent.tools.registry import ToolRegistry

    schemas: list[dict[str, Any]] = []
    try:
        registry = ToolRegistry(build_kb_tools(kb_path))
        schemas = list(registry.schemas())
        system = build_system_prompt(kb_path, tools=schemas, model=model or "")
    except Exception:  # noqa: BLE001 — 只读派生，构建失败时保留其余两段
        system = ""
        schemas = []

    try:
        messages = build_history(kb_path, session_id, max_chars=max_chars)
    except Exception:  # noqa: BLE001
        messages = []

    system_chars = len(system or "")
    tools_chars = _tools_chars(schemas)
    message_chars = _message_chars(messages)
    total_chars = system_chars + tools_chars + message_chars

    budget = None
    try:
        budget = session_context_usage(kb_path, session_id)
    except Exception:  # noqa: BLE001
        budget = None

    return {
        "status": "ok",
        "session_id": session_id,
        "model": model or "",
        "segments": {
            "system": {"chars": system_chars, "tokens": estimate_tokens(system_chars)},
            "tools": {"chars": tools_chars, "tokens": estimate_tokens(tools_chars)},
            "messages": {"chars": message_chars, "tokens": estimate_tokens(message_chars)},
        },
        "total": {"chars": total_chars, "tokens": estimate_tokens(total_chars)},
        "budget": budget,
        "estimate": {
            "method": "chars/4",
            "chars_per_token": CHARS_PER_TOKEN,
            "tokens_are_estimated": True,
        },
    }
