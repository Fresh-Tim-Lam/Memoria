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
| `compaction` | `{summary, shadowed:[seq…], …}` | 在 `shadowed` 中最旧的 seq 处出一条 `user` 消息（摘要 + checkpoint 框定），其 `shadowed` 里的 seq **全部跳过** |
| `compaction/prune` | `{pruned:[{seq, head, tail, …}]}` | 被列出的 `tool/result` 在回放时**就地**换成「头 + 标记 + 尾」（**原事件逐字留在日志里**，只是不再进请求） |
| `session/title` | `{title, message_seqs:[seq…], source:{kind}}` | **跳过**（标题是 **log-only** 的：既不进消息序列、也不进模型输入；只由**标题折叠**读取，见 `title.py`） |

## 压缩回放（M2）

`compaction` 事件由 `services/agent/compaction.py` 产出形状、由 `ask.py` 落盘（单写者 + 仅追加）。
回放口径：

- 摘要出自 `compaction.frame_summary()`（**延迟导入**：`compaction` 已按「事件常量」方向依赖本模块，
  反向只能延迟，避免循环导入）；
- 摘要在**原区间最旧一条 seq 的位置**出现（= 时序上仍在原处），而不是追加在末尾；
- **链式压缩**：后一次压缩若覆盖前一次区间（含前一条 `compaction` 记录自身），则只出**最新**那份
  合并摘要 —— `emit_at` 以同一键覆盖，旧摘要不再重复出现；
- 无效记录（`shadowed` 为空 / 摘要为空）**忽略**，不吞掉任何事件（fail-safe：宁可当没压过）。

## 工具结果裁剪回放（M2）

`compaction/prune` 事件由 `services/agent/pruner.py` 产出形状、由 `ask.py` 落盘（同压缩：单写者 +
仅追加）。回放口径：

- 记录里的 `pruned[].seq` 指向 `tool/result` 事件；回放时用**记录里落盘的** `head` / `tail`
  重建正文（`pruner.apply_budget()`）⇒ 与当次请求所见**逐字一致**，且不随默认预算变化而漂移；
- **原事件仍在日志里**（append-only）⇒ 检索 / 导出 / 审计看到的仍是原文，只有**发给模型**的
  请求用裁剪视图；
- **链式/重复**：同一 `seq` 被多条记录覆盖时**后写覆盖**（与压缩同口径）；形状不全的记录**整条
  忽略**（fail-safe：宁可让模型看到原文，也不拿半截预算去切正文）。

## 标题（M2）

`session/title` 事件（形状见 `services/agent/title.py`）是 **log-only** 的：回放**跳过**它（既不出消息、
也不进模型输入），但**会话摘要**要读它 —— `summarize_events()` 用 `title.fold_title()` 折叠；
`summarize_session_file()` 的**原始行扫描**里另找 `"session/title"` 行、只对**最后一个命中行**解码
（与它读 `user/message` 预览同一套"不解码整份文件"的做法）。**两处口径一致**：都以**最后一条非空标题**为准，
没有标题事件时回落到「首条提问前 `TITLE_CHARS` 字」。

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

上游用 compaction（把旧区间摘成摘要）解决长会话；本地 M2 起同构（见上「压缩回放」），
**截断只是兜底**（硬上限）：

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
from memoria.services.agent.pruner import apply_budget, prune_applied
from memoria.services.agent.session.store import read_session
from memoria.services.agent.title import fold_title

__all__ = [
    "COMPACTION",
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_MESSAGES",
    "SESSION_SCAN_MAX_BYTES",
    "build_history",
    "compaction_shadowed",
    "conversation_events",
    "conversation_messages",
    "replay_events",
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
#: 压缩事件（形状由 `services/agent/compaction.py` 定、`ask.py` 落盘；见「压缩回放」）。
COMPACTION = "compaction"

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

#: 原始行扫描时的 `session/title` 事件标记（取值同 `title.SESSION_TITLE`；写字面量避免反向依赖）。
_TITLE_TYPE_MARK = b'"session/title"'


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


def _tool_message(event: Mapping[str, Any], prune: Mapping[int, tuple[int, int]] | None) -> Message:
    """`tool/result` → `tool` 消息；被 `compaction/prune` 覆盖的按记录里的预算重建正文。"""
    data = _data(event)
    name = data.get("name")
    content = str(data.get("content") or "")
    seq = event.get("seq")
    if prune and isinstance(seq, int) and seq in prune:
        head, tail = prune[seq]
        content = apply_budget(content, head, tail)
    return Message(
        role=Role.TOOL,
        content=content,
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


def _summary_message(summary: str) -> Message:
    """把落盘的摘要正文包成替换消息（框定语出自 `compaction.frame_summary()`）。"""
    # 延迟导入：`compaction` 在模块层依赖本模块的事件常量，反向只能延迟（避免循环导入）
    from memoria.services.agent.compaction import frame_summary

    return Message(role=Role.USER, content=frame_summary(summary))


def _compaction_plan(
    events: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, str], set[int]]:
    """把 `compaction` 事件折成（在哪些 seq 上出摘要, 要跳过哪些 seq）。

    见模块 docstring 的「压缩回放」：摘要落在原区间最旧的 seq 处；链式压缩只出最新那份；
    无效记录（空 `shadowed` / 空摘要）忽略。
    """
    emit_at: dict[int, str] = {}
    skip: set[int] = set()
    for event in events:
        if event.get("type") != COMPACTION:
            continue
        data = _data(event)
        raw = data.get("shadowed")
        seqs = (
            [seq for seq in raw if isinstance(seq, int)]
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
            else []
        )
        summary = str(data.get("summary") or "").strip()
        if not seqs or not summary:
            continue  # 无效记录：忽略，不吞掉任何事件（fail-safe）
        skip.update(seqs)
        emit_at[min(seqs)] = summary  # 后写覆盖 ⇒ 链式压缩只出最新那份合并摘要
    return emit_at, skip


def compaction_shadowed(events: Sequence[Mapping[str, Any]]) -> set[int]:
    """`compaction` 记录覆盖的 `seq`（供裁剪器跳过 —— 它们本来就不进请求）。"""
    return _compaction_plan(events)[1]


def _replay(
    events: Sequence[Mapping[str, Any]],
    *,
    emit_at: Mapping[int, str] | None = None,
    skip: set[int] | None = None,
    prune: Mapping[int, tuple[int, int]] | None = None,
) -> list[Message]:
    """按事件顺序重建消息序列（配对失败的整轮丢弃，见模块 docstring）。

    `emit_at` / `skip` 由 `_compaction_plan()` 给出：被压缩覆盖的 seq 一律跳过，并在该区间
    **最旧那条 seq** 处补一条摘要消息（位置不变，见「压缩回放」）。`prune` 由
    `pruner.prune_applied()` 给出：命中的 `tool/result` 按其预算重建正文（见「工具结果裁剪回放」）。
    """
    messages: list[Message] = []
    index = 0
    total = len(events)
    while index < total:
        event = events[index]
        seq = event.get("seq")
        if skip and isinstance(seq, int) and seq in skip:
            summary = (emit_at or {}).get(seq)
            if summary:
                messages.append(_summary_message(summary))
            index += 1
            continue
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
                messages.extend(_tool_message(row, prune) for row in results)
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


def conversation_events(kb_path: str, session_id: str) -> list[dict[str, Any]]:
    """会话的**事件**列表（跳过 header）—— 供压缩选择区间用（`compaction.select_span`）。"""
    return _conversation_events(kb_path, session_id)


def replay_events(
    events: Sequence[Mapping[str, Any]],
    *,
    apply_compaction: bool = True,
    prune: Mapping[int, tuple[int, int]] | None = None,
) -> list[Message]:
    """把**给定事件列表**回放成消息序列（不做容量截断）。

    默认应用已落盘的压缩覆盖（`apply_compaction=True`）：压缩器据此拿到「有效视图」
    （既有摘要 + 更新的轮次），从而**合并**旧 checkpoint 而不是把原文再喂一遍
    （对齐上游「旧 checkpoint 要合并、不要照抄」）。

    `prune`（可选）由调用方传 `pruner.prune_applied(session_events)`：**传入整份会话**的裁剪表，
    这样即便只回放被压缩的一个子区间，区间内的工具结果也已按裁剪视图呈现（上游：摘要器读的是
    裁剪后的表面）。省略时不裁剪 —— 这就是「原始视图」。
    """
    if apply_compaction:
        emit_at, skip = _compaction_plan(events)
    else:
        emit_at, skip = {}, None
    return _replay(events, emit_at=emit_at, skip=skip, prune=prune)


def build_history(
    kb_path: str,
    session_id: str,
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_chars: int = MAX_HISTORY_CHARS,
) -> list[Message]:
    """把会话回放成**可再发**的消息序列（含工具轮；容量截断见模块 docstring）。

    会先应用已落盘的 `compaction` 与 `compaction/prune` 事件（见「压缩回放」「工具结果裁剪回放」），
    再按容量做兜底截断。会话文件不存在时返回空列表（= 全新会话，等价于不带历史）。
    截断策略：从最新往旧保留，最多 `max_messages` 条 / `max_chars` 字符。
    """
    events = _conversation_events(kb_path, session_id)
    emit_at, skip = _compaction_plan(events)
    return _truncate(
        _replay(events, emit_at=emit_at, skip=skip, prune=prune_applied(events)),
        max_messages,
        max_chars,
    )


def _first_user_text(events: Sequence[Mapping[str, Any]]) -> str:
    for event in events:
        if event.get("type") == USER_MESSAGE:
            return _text(event).strip()
    return ""


def summarize_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """会话摘要（`agent_sessions_list` 用）：轮数 / 首条提问预览与标题。

    `title` 优先取**折叠出的标题**（`session/title` 事件：模型标题或确定性兜底）；
    没有标题事件时才回落到「首条提问前 `TITLE_CHARS` 字」（M1 行为）。
    """
    turn_count = sum(1 for event in events if event.get("type") == USER_MESSAGE)
    first = _first_user_text(events)
    folded = fold_title(events)
    return {
        "turn_count": turn_count,
        "preview": first[:PREVIEW_CHARS],
        "title": folded.title if folded is not None else first[:TITLE_CHARS],
    }


def summarize_session(kb_path: str, session_id: str) -> dict[str, Any]:
    """读盘并返回 `summarize_events()` 的摘要（会话不存在 ⇒ 全零摘要）。"""
    return summarize_events(_conversation_events(kb_path, session_id))


def _preview_from_line(line: bytes) -> str:
    """从**单行**事件 JSON 取 `data.text`（仅此一处解码 + 一次 `json.loads`）。"""
    record = _record_from_line(line)
    return _text(record).strip() if record is not None else ""


def _title_from_line(line: bytes) -> str:
    """从**单行** `session/title` JSON 取 `data.title`（同样只解码一次）。"""
    record = _record_from_line(line)
    return str(_data(record).get("title") or "") if record is not None else ""


def _record_from_line(line: bytes) -> Mapping[str, Any] | None:
    try:
        record = json.loads(line.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, Mapping) else None


def summarize_session_file(
    path: str, *, max_bytes: int = SESSION_SCAN_MAX_BYTES, size: int | None = None
) -> dict[str, Any]:
    """**原始行扫描**的会话摘要（供 `agent_sessions_list` 用，避免读放大）。

    与 `summarize_session()` 的差别：**不整体 `json.loads`**——只按行找
    `"user/message"` 子串计 `turn_count`，并从**首个**命中行取预览、从**最后一个**
    `"session/title"` 命中行取标题。扫描全程在**字节串**上进行（不解码整份文件），
    只对命中行解码 + `json.loads` 一次；因此：

    - `turn_count` 语义为「**扫描上限内的** `user/message` 事件行数」（超限时
      只统计上限内的部分，返回值另带 `capped: true`）；
    - **标题**：优先取最后一条非空 `session/title`（模型标题或兜底标题），没有时才回落到
      「首个 `user/message` 行前 `TITLE_CHARS` 字」——与 `summarize_events()` 的
      `fold_title()` **同口径**；
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
    title = ""
    for line in lines:
        if _TITLE_TYPE_MARK in line:
            candidate = _title_from_line(line)
            if candidate:
                title = candidate  # 最后一条**非空**标题胜出（与 fold_title 同口径）
            continue
        if _USER_TYPE_MARK not in line:
            continue
        turn_count += 1
        if not seen_first:
            seen_first = True
            first = _preview_from_line(line)
    return {
        "turn_count": turn_count,
        "preview": first[:PREVIEW_CHARS],
        "title": title or first[:TITLE_CHARS],
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
