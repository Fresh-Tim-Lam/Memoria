# 一次回合「过程内容」的形状单一来源（实时通道与回放共用）。
# 语义对应上游 deepseek-harness 的「Turn Process Folding」：一次回合（turn）的过程内容
# = 推理（reasoning）行 + 工具调用（tool call）行 + 最终答复之前的更早助手正文。
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720

"""回合过程内容的**唯一形状来源**：实时通道（`ask_stream`）与回放（`session/history.py`）共用。

为什么单独成模块：过程行既要「边跑边出」（作业面按事件流实时投递），又要在载入旧会话时
「按同一形状回放」，两处若各写一份，形状必漂移。这里只做**纯函数**（不读盘、不联网、无
状态），故可离线单测。

三类内容（前端一律按 `kind` 分派）：

- `tool` 行：一次工具调用 / 结果 —— `tool/call` 与 `tool/result` **各出一行、同一 `id`**，
  前端按 `id` 合并状态（`running` → `ok` / `error`）；
- `step` 行：一次模型输出（`assistant/message`）—— `text` 是「更早的助手正文」，**不截断**
  （回合结束后折叠成摘要行，展开仍要看全文）；
- 推理（`reasoning`）**随 `step` 出现**（`step.reasoning`），不单列一行。

摘要口径与既有 `ask._tool_message()` **同源**：空白折叠成一个空格 + 截断。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["arg_summary", "process_items", "row_detail", "step_row", "tool_row"]

#: 事件类型（与 `loop.py` 写入、`history.py` 回放的取值一致）。
ASSISTANT_MESSAGE = "assistant/message"
TOOL_CALL = "tool/call"
TOOL_RESULT = "tool/result"

#: 工具行摘要（`arg_summary`）与工具结果详情（`row_detail`）的截断长度。
SUMMARY_LIMIT = 120
DETAIL_LIMIT = 240

#: 工具名 → 「最有信息量」的参数键（首个命中的键胜出；缺省回落到第一个非空标量值）。
_ARG_KEYS: dict[str, tuple[str, ...]] = {
    "read_document": ("path", "file"),
    "read_image": ("path", "file"),
    "create_file": ("path", "file"),
    "rename_file": ("path", "file"),
    "edit_file": ("path", "file"),
    "delete_file": ("path", "file"),
    "grep": ("pattern",),
    "glob": ("pattern",),
    "search_kb": ("query",),
    "kb_overview": ("purpose",),
    "resolve_reference": ("reference",),
    "propose_write": ("intent",),
    "session_event_read": ("session_id",),
    "session_event_search": ("query",),
}


def row_detail(text: Any, limit: int = DETAIL_LIMIT) -> str:
    """工具结果 / 正文的**单行摘要**：空白折叠成一个空格、截断 `limit` 字。

    与既有 `ask._tool_message()` **同口径**（面板展示失败原因用的就是它），故过程行详情与
    轮询载荷里的 `tool_calls[].message` 逐字一致。`None` / 空 ⇒ 空串。
    """
    return " ".join(str(text or "").split())[:limit]


def _as_mapping(arguments: Any) -> Mapping[str, Any]:
    """把工具参数（JSON 字符串或 dict）收敛成映射；坏 JSON / 非对象一律给空映射（不抛）。"""
    if isinstance(arguments, Mapping):
        return arguments
    if isinstance(arguments, str):
        try:
            value = json.loads(arguments)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, Mapping) else {}
    return {}


def _scalar_text(value: Any) -> str:
    """非空标量的文本形式；非标量 / 空字符串 ⇒ 空串（用于参数摘要回落）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    return ""


def arg_summary(name: str, arguments: Any) -> str:
    """挑工具参数里**最有信息量的一项**做一行摘要（截断 120）。

    按工具名挑键（见 `_ARG_KEYS`）：找不到就回落到第一个非空标量值，再回落到空串。两个特例：
    `grep` 在 `pattern` 后可拼 `include`；`session_event_read` 拼成 `session_id#seq`。值**原样**
    取自参数（不编造）；参数是坏 JSON 时返回空串（不抛）。
    """
    data = _as_mapping(arguments)
    text = ""
    if data:
        tool = str(name or "")
        if tool == "session_event_read" and ("session_id" in data or "seq" in data):
            sid = _scalar_text(data.get("session_id"))
            seq = _scalar_text(data.get("seq"))
            text = f"{sid}#{seq}" if seq else sid
        elif tool == "grep":
            pattern = _scalar_text(data.get("pattern"))
            include = _scalar_text(data.get("include"))
            text = f"{pattern} {include}".strip() if include else pattern
        if not text:
            for key in _ARG_KEYS.get(tool, ()):
                text = _scalar_text(data.get(key))
                if text:
                    break
        if not text:
            for value in data.values():
                text = _scalar_text(value)
                if text:
                    break
    return text[:SUMMARY_LIMIT]


def tool_row(rec: Mapping[str, Any], *, state: str, iteration: int = 0) -> dict:
    """工具**行**（一行 = 一次调用）；`tool/call` 与 `tool/result` 两行 `id` 相同、前端据此合并。

    `rec` 是 `tool/call` 或 `tool/result` 的 `data`：`tool/call` 传 `state="running"`
    （`detail=""`、`code=None`）；`tool/result` 传 `state="ok"|"error"`（按 `is_error` 定），
    `code` 取 `data["code"]`、`detail` 取 `row_detail(data["content"])`。
    """
    data: Mapping[str, Any] = rec if isinstance(rec, Mapping) else {}
    name = str(data.get("name") or "")
    row: dict[str, Any] = {
        "kind": "tool",
        "id": str(data.get("id") or ""),
        "name": name,
        "summary": arg_summary(name, data.get("arguments")),
        "state": state,
        "code": None,
        "detail": "",
        "iteration": int(iteration or 0),
    }
    if state != "running":
        row["code"] = data.get("code")
        row["detail"] = row_detail(data.get("content"))
    return row


def step_row(iteration: int, content: Any, tool_calls: Any, reasoning: Any = None) -> dict:
    """一步（一次模型输出）→ 行。

    `text` **不截断**（它是"更早的助手正文"，折叠后仍可能被展开看全文）；`tool_calls` 只报
    **条数**（明细在工具行里）；`reasoning` 原文，**空则省略该键**（省体积、旧读者也无感）。
    """
    calls = (
        tool_calls
        if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes))
        else ()
    )
    row: dict[str, Any] = {
        "kind": "step",
        "iteration": int(iteration or 0),
        "text": content if isinstance(content, str) else str(content or ""),
        "tool_calls": len(calls),
    }
    if reasoning is not None and str(reasoning).strip():
        row["reasoning"] = reasoning if isinstance(reasoning, str) else str(reasoning)
    return row


def _event_data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("data")
    return value if isinstance(value, Mapping) else {}


def _is_final_answer(data: Mapping[str, Any]) -> bool:
    """该 `assistant/message` 是否构成「最终答复」：正文非空白 **且** 无工具调用。"""
    content = data.get("content")
    if not (isinstance(content, str) and content.strip()):
        return False
    calls = data.get("tool_calls")
    if isinstance(calls, Sequence) and not isinstance(calls, (str, bytes)):
        return len(calls) == 0
    return not calls


def process_items(events: Sequence[Mapping[str, Any]]) -> list[dict]:
    """**回放用**：把一轮的事件序列折成过程行列表（按事件顺序）。

    每个 `assistant/message` → `step_row`；每个 `tool/call` → `tool_row(running)`；
    每个 `tool/result` → `tool_row(ok/error)`。**若该轮最后一条 `assistant/message` 构成最终
    答复**（正文非空白且无工具调用），则**跳过它** —— 它就是"最终答案"，由调用方单独作为气泡
    正文渲染；否则（末条带工具调用 / 正文为空，如 `max-tokens`、被取消的轮次）整轮过程**全部
    保留可见**。工具行没有自己的 `iteration`，沿用最近一次 `assistant/message` 的。
    """
    final_index: int | None = None
    for index, event in enumerate(events):
        if isinstance(event, Mapping) and event.get("type") == ASSISTANT_MESSAGE:
            final_index = index
    skip_final = final_index is not None and _is_final_answer(_event_data(events[final_index]))

    rows: list[dict] = []
    last_iteration = 0
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            continue
        kind = event.get("type")
        data = _event_data(event)
        if kind == ASSISTANT_MESSAGE:
            last_iteration = int(data.get("iteration") or last_iteration or 0)
            if index == final_index and skip_final:
                continue
            rows.append(step_row(last_iteration, data.get("content"), data.get("tool_calls"), data.get("reasoning")))
        elif kind == TOOL_CALL:
            rows.append(tool_row(data, state="running", iteration=last_iteration))
        elif kind == TOOL_RESULT:
            rows.append(tool_row(data, state="error" if data.get("is_error") else "ok", iteration=last_iteration))
    return rows
