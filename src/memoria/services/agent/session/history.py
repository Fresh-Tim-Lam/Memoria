# 会话历史重建：把 `session/store.py` 的 JSONL 事件回放成 LLM 消息序列。
# 事件类型与载荷由 `services/agent/{loop,ask}.py` 产生（会话格式移植自
# deepseek-harness packages/session/*，MIT / BSD-3-Clause；
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720）。

"""会话历史重建（M1c 多轮续聊）：把已落盘的会话事件回放成**可再发的消息序列**。

与 `store.py` 的分工：`store.py` 只负责「一行一个 JSON 事件」的持久化（读/追加），
本模块负责**语义回放**——把事件还原成 provider 中立的消息（`llm/types.py`），
供 `ask()` 续聊时作为 `messages=` 传回 `AgentLoop.run()`。

## 事件 → 消息（回放口径）

| 事件 | 载荷 | 回放为 |
|---|---|---|
| `user/message` | `{text}` | `Message(role=user, content=text)` |
| `assistant/message` | `{content, tool_calls:[{id,name,arguments}]}` | `Message(role=assistant, content, tool_calls)` |
| `tool/result` | `{id,name,content,anchors}` | `Message(role=tool, content, tool_call_id=id, name=name)` |
| `tool/call` | `{id,name,arguments}` | **跳过**（信息已在 assistant 的 `tool_calls` 里） |
| `step/start`、`step/error`、`loop/end` | — | **跳过**（非对话内容） |

## 保真度（**全保真回放**，仅异常轮降级）

`ToolCall`（`llm/types.py:65-72`）可用 `{id,name,arguments}` **完整重建**，而
`OpenAICompatibleProvider._message_to_wire`（`providers/openai_compatible.py:374-391`）
正是按 `tool_call_id` / `tool_calls` 序列化的，因此带工具的轮次**原样回放**：
assistant 带 `tool_calls` + 紧随其后的 `tool` 消息（`tool_call_id` 与 `id` 对齐），
满足 OpenAI 兼容协议的结构约束（否则端点 400）。

**唯一的降级分支**：某条 `assistant/message` 的 `tool_calls` 与紧随其后的
`tool/result` **无法一一配对**（`id` 为空、数量不等、顺序不符——正常写作时只在
进程崩在工具执行中途等撕裂场景出现）。此时**整轮丢弃**（assistant 与其 tool 消息
一起丢），保证输出里绝不出现"孤立 tool_calls"或"孤儿 tool 消息"。

## 容量上限与截断策略

- `MAX_HISTORY_MESSAGES = 40` 条、`MAX_HISTORY_CHARS = 32000` 字符（两个常量均导出）；
- **从最新往旧保留**（越近的上下文越重要）；至少保留最新 1 条（单条超预算也保留，
  否则续聊会凭空丢掉当前上下文）；
- 截断按**整条消息**进行；截断后若序列首部是被截掉 assistant 的 `tool` 消息，
  则一并丢弃（保持序列合法）。

## 只读

本模块只读会话文件（`read_session`），不写盘、不联网、不打印。
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

from memoria.services.agent.llm import Message, Role, ToolCall
from memoria.services.agent.session.store import read_session

__all__ = [
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_MESSAGES",
    "SESSION_SCAN_MAX_BYTES",
    "build_history",
    "conversation_messages",
    "summarize_events",
    "summarize_session",
    "summarize_session_file",
]

#: 回放时保留的最大消息条数（从最新往旧保留）。
MAX_HISTORY_MESSAGES = 40
#: 回放时保留的最大正文字符数（从最新往旧保留）。
MAX_HISTORY_CHARS = 32_000

#: 会话事件类型（与 `loop.py` / `ask.py` 写入的取值一致）。
USER_MESSAGE = "user/message"
ASSISTANT_MESSAGE = "assistant/message"
TOOL_CALL = "tool/call"
TOOL_RESULT = "tool/result"

#: 会话列表里 `preview` / `title` 的最大字符数。
PREVIEW_CHARS = 80
TITLE_CHARS = 40

#: `summarize_session_file()` 单份会话文件的**最大扫描字节数**（超出即 `capped`）。
#: 目的：会话列表只统计/预览，绝不因某份超大会话（如长工具输出）把列表变慢；
#: 取 2 MiB（远大于正常对话：一次问答通常几十 KiB）。
SESSION_SCAN_MAX_BYTES = 2 * 1024 * 1024

#: 原始行扫描时的 `user/message` 事件标记（`store._encode` 写出的 JSON 形态）。
#: 用 **bytes** 形态：扫描全程不解码整份文件（纯 ASCII 子串在字节串上同样精确），
#: 只对命中的**那一行**解码 + 解析预览——这是"去读放大"的关键。
_USER_TYPE_MARK = b'"user/message"'


def _conversation_events(kb_path: str, session_id: str) -> list[dict[str, Any]]:
    """回放会话事件（跳过 header；header 没有 `seq`）。"""
    return [row for row in read_session(kb_path, session_id) if isinstance(row.get("seq"), int)]


def _data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("data")
    return value if isinstance(value, Mapping) else {}


def _text(event: Mapping[str, Any]) -> str:
    return str(_data(event).get("text") or "")


def _tool_call(raw: Any) -> ToolCall | None:
    if not isinstance(raw, Mapping):
        return None
    return ToolCall(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        arguments=str(raw.get("arguments") or ""),
    )


def _tool_message(event: Mapping[str, Any]) -> Message:
    data = _data(event)
    name = data.get("name")
    return Message(
        role=Role.TOOL,
        content=str(data.get("content") or ""),
        tool_call_id=str(data.get("id") or ""),
        name=str(name) if name else None,
    )


def _paired(calls: Sequence[ToolCall], results: Sequence[Mapping[str, Any]]) -> bool:
    """`tool_calls` 与紧随其后的 `tool/result` 是否一一配对（`id` 必须非空且顺序一致）。"""
    if len(calls) != len(results):
        return False
    return all(
        call.id and str(_data(result).get("id") or "") == call.id
        for call, result in zip(calls, results)
    )


def _replay(events: Sequence[Mapping[str, Any]]) -> list[Message]:
    """按事件顺序重建消息序列（配对失败的整轮丢弃，见模块 docstring）。"""
    messages: list[Message] = []
    index = 0
    total = len(events)
    while index < total:
        event = events[index]
        kind = event.get("type")
        if kind == USER_MESSAGE:
            messages.append(Message(role=Role.USER, content=_text(event)))
            index += 1
            continue
        if kind == ASSISTANT_MESSAGE:
            data = _data(event)
            calls = tuple(
                call
                for call in (_tool_call(item) for item in (data.get("tool_calls") or ()))
                if call is not None
            )
            content = str(data.get("content") or "")
            if not calls:
                messages.append(Message(role=Role.ASSISTANT, content=content))
                index += 1
                continue
            cursor = index + 1
            results: list[Mapping[str, Any]] = []
            while cursor < total:
                kind = events[cursor].get("type")
                if kind == TOOL_CALL:
                    # `tool/call` 只是同一调用的冗余播报（信息已在 assistant.tool_calls），
                    # 但生产写入顺序是 assistant/message → tool/call → tool/result，
                    # 故扫描配对时必须跳过它、不能就此收尾
                    cursor += 1
                    continue
                if kind == TOOL_RESULT:
                    results.append(events[cursor])
                    cursor += 1
                    continue
                break
            if _paired(calls, results):
                messages.append(Message(role=Role.ASSISTANT, content=content, tool_calls=calls))
                messages.extend(_tool_message(row) for row in results)
            # 否则整轮丢弃：不留下孤立 tool_calls（端点会 400）
            index = cursor
            continue
        index += 1
    return messages


def _role_of(message: Message) -> str:
    role = message.role
    return role.value if isinstance(role, Role) else str(role)


def _truncate(messages: Sequence[Message], max_messages: int, max_chars: int) -> list[Message]:
    """从最新往旧保留整条消息，再去掉因此变成孤儿的前导 `tool` 消息。"""
    kept: list[Message] = []
    chars = 0
    for message in reversed(messages):
        size = len(message.content or "")
        if kept and (len(kept) >= max_messages or chars + size > max_chars):
            break
        kept.append(message)
        chars += size
    kept.reverse()
    start = 0
    while start < len(kept) and _role_of(kept[start]) == Role.TOOL.value:
        start += 1
    return kept[start:]


def build_history(
    kb_path: str,
    session_id: str,
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_chars: int = MAX_HISTORY_CHARS,
) -> list[Message]:
    """把会话回放成**可再发**的消息序列（含工具轮；容量截断见模块 docstring）。

    会话文件不存在时返回空列表（= 全新会话，等价于不带历史）。
    截断策略：从最新往旧保留，最多 `max_messages` 条 / `max_chars` 字符。
    """
    return _truncate(_replay(_conversation_events(kb_path, session_id)), max_messages, max_chars)


def _first_user_text(events: Sequence[Mapping[str, Any]]) -> str:
    for event in events:
        if event.get("type") == USER_MESSAGE:
            return _text(event).strip()
    return ""


def summarize_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """会话摘要（`agent_sessions_list` 用）：轮数 / 首条提问预览与短标题。"""
    turn_count = sum(1 for event in events if event.get("type") == USER_MESSAGE)
    first = _first_user_text(events)
    return {
        "turn_count": turn_count,
        "preview": first[:PREVIEW_CHARS],
        "title": first[:TITLE_CHARS],
    }


def summarize_session(kb_path: str, session_id: str) -> dict[str, Any]:
    """读盘并返回 `summarize_events()` 的摘要（会话不存在 ⇒ 全零摘要）。"""
    return summarize_events(_conversation_events(kb_path, session_id))


def _preview_from_line(line: bytes) -> str:
    """从**单行**事件 JSON 取 `data.text`（仅此一处解码 + 一次 `json.loads`）。"""
    try:
        record = json.loads(line.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(record, Mapping):
        return ""
    return _text(record).strip()


def summarize_session_file(
    path: str, *, max_bytes: int = SESSION_SCAN_MAX_BYTES, size: int | None = None
) -> dict[str, Any]:
    """**原始行扫描**的会话摘要（供 `agent_sessions_list` 用，避免读放大）。

    与 `summarize_session()` 的差别：**不整体 `json.loads`**——只按行找
    `"user/message"` 子串计 `turn_count`，并从**首个**命中行取预览/标题。扫描全程
    在**字节串**上进行（不解码整份文件），只对该命中行解码 + `json.loads` 一次；因此：

    - `turn_count` 语义为「**扫描上限内的** `user/message` 事件行数」（超限时
      只统计上限内的部分，返回值另带 `capped: true`）；
    - 单文件读取上限 `max_bytes`（默认 `SESSION_SCAN_MAX_BYTES` = 2 MiB），
      `capped` 表示「该文件超过上限，统计被截断」；为免把半行算作一行，
      `capped` 时丢弃最后一段（可能是被截断的不完整行）。未超限时按"整读"取内容
      （`read(-1)`），**不**按上限长度去 ask（那会给每个小文件白分配 2 MiB 缓冲）；
    - `size` 可传入调用方**已知**的文件字节数（`list_sessions()` 已 stat 过）
      以免重复 stat；省略时自行 `os.path.getsize`；
    - 子串判定是**行级近似**：若某条非 user 事件的正文里恰好引用字面量
      `"user/message"`，会被计入（正常对话不会出现；`summarize_session()` 的
      精确口径仍保留给需要严格计数的调用方）。
    """
    limit = max_bytes if isinstance(max_bytes, int) and max_bytes > 0 else 0
    if size is None:
        try:
            size = os.path.getsize(path)
        except OSError:
            return {"turn_count": 0, "preview": "", "title": "", "capped": False}
    capped = bool(limit) and size > limit
    with open(path, "rb") as handle:
        data = handle.read(limit) if capped else handle.read()
    lines = data.split(b"\n")
    if capped and lines:
        lines.pop()  # 末段多半是被截断的半行，不计
    turn_count = 0
    first = ""
    seen_first = False
    for line in lines:
        if _USER_TYPE_MARK not in line:
            continue
        turn_count += 1
        if not seen_first:
            seen_first = True
            first = _preview_from_line(line)
    return {
        "turn_count": turn_count,
        "preview": first[:PREVIEW_CHARS],
        "title": first[:TITLE_CHARS],
        "capped": capped,
    }


def conversation_messages(kb_path: str, session_id: str) -> list[dict[str, Any]]:
    """会话的**渲染视图**（`agent_session_load` 用）：`[{role, text, anchors?}]`。

    与 `build_history()` 的差别（供 UI 恢复气泡，故不按 LLM 协议形状）：

    - 只出 `user` / `assistant` 两种角色，**不含** `tool` 消息；
    - 每轮（一条 `user/message` 到下一轮之前）只出**一条** assistant 气泡 =
      该轮**最后一条非空** `assistant/message`（= 界面上的最终答案，与实时渲染一致）；
    - **锚点归属**：该轮全部 `tool/result` 的 `anchors` 汇总去重后，挂在该轮
      那条 assistant 气泡上（跨轮不混淆；轮内取并集）。
    """
    events = _conversation_events(kb_path, session_id)
    out: list[dict[str, Any]] = []
    turn: dict[str, Any] | None = None
    for event in events:
        kind = event.get("type")
        if kind == USER_MESSAGE:
            _flush_turn(out, turn)
            turn = {"text": _text(event), "answer": "", "anchors": []}
            continue
        if turn is None:
            continue
        if kind == ASSISTANT_MESSAGE:
            content = str(_data(event).get("content") or "")
            if content:
                turn["answer"] = content
            continue
        if kind == TOOL_RESULT:
            for anchor in _data(event).get("anchors") or ():
                if isinstance(anchor, Mapping):
                    turn["anchors"].append(dict(anchor))
    _flush_turn(out, turn)
    return out


def _flush_turn(out: list[dict[str, Any]], turn: dict[str, Any] | None) -> None:
    if turn is None:
        return
    out.append({"role": Role.USER.value, "text": turn["text"]})
    if turn["answer"]:
        record: dict[str, Any] = {"role": Role.ASSISTANT.value, "text": turn["answer"]}
        anchors = _dedupe(turn["anchors"])
        if anchors:
            record["anchors"] = anchors
        out.append(record)


def _dedupe(anchors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """按 (file, line, kp_id) 去重（与 `ask._dedupe_anchors` 同口径）。"""
    seen: set[tuple[str, Any, str]] = set()
    out: list[dict[str, Any]] = []
    for anchor in anchors:
        key = (str(anchor.get("file") or ""), anchor.get("line"), str(anchor.get("kp_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(anchor))
    return out
