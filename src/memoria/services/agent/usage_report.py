"""会话用量聚合：把 `<kb>/.memoria/agent/sessions/*.jsonl` 的 `loop/end` 事件
汇总成逐轮行与总量（**纯标准库、纯函数、只读**）。

口径（字段与 `loop.py::usage_payload()` 写进 `loop/end.usage` 的载荷一一对应）：

- **一轮**（turn）= 一条 `loop/end` 事件（一次 `ask()` 里全部模型步数之和）；
- **不含压缩开销**：M2 的 compaction 摘要调用把用量记在自己的 `compaction.usage`（与 `loop/end`
  同形状，由 `ask.py` 落盘）里，本报告只扫 `loop/end` ⇒ 压缩消耗**不计入**任何一轮
  （见 `docs/design/dsh-agent-port.md §6.8` 的「已知缺口」）；
- `prompt` / `completion` / `total`：该轮输入 / 输出 / 合计 token；
- `cache_hit` / `cache_miss`：端点上报的**命中 / 未命中**缓存 token。端点未给该
  形态字段时为 `None`（= **未知**，绝不写成 0）；OpenAI 形态只给命中量时，
  未命中量按 `prompt - cache_hit` 补出（可推才补）；
- `hit_rate`：`cache_hit / prompt`（该轮输入里命中缓存的比例）；`cache_hit` 未知
  或 `prompt <= 0` 时为 `None`；
- `estimated`：端点完全没给 usage、由启发式估算（`estimated=True`）时标注。

**已知限制**（引用数字时必须一起给出）：

1. 会话只记 `loop/end.usage`，**未记模型名**，故逐轮行不含 `model`；
2. 本次改动前落盘的**老会话**没有 cache 字段 ⇒ 其 `cache_hit` 恒为 `None`，
   计入汇总的 `cache_unknown_turns`，且**不参与**命中率分母 —— 命中率因此是
   `None`（"未知"）而**不是** 0；
3. 汇总的 `cache_hit` / `cache_miss` 只在"至少一轮上报过该值"时给数（否则
   `None`）；`cache_miss` 为若干**已知**未命中量之和，未知轮次不计入而非按 0 计。

读取走**原始行扫描 + 字节上限**（参照 `session/history.py::summarize_session_file`）：
全程在字节串上找 `"loop/end"` 子串，只对命中行解码 + `json.loads`；单份文件最多
读 `SCAN_MAX_BYTES`（超限时该会话 `capped=True`，只统计上限内的轮次、丢弃末段半行），
故大文件不会把内存打爆。

本模块不写盘、不联网、不打印。
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

from memoria.services.agent.session.history import SESSION_SCAN_MAX_BYTES
from memoria.services.agent.session.store import list_sessions, session_file

__all__ = [
    "SCAN_MAX_BYTES",
    "aggregate_usage",
    "hit_rate",
    "iter_session_turns",
    "turn_from_event",
    "usage_stats",
]

#: 单份会话文件的扫描字节上限（与 `history.SESSION_SCAN_MAX_BYTES` 同一口径）。
SCAN_MAX_BYTES = SESSION_SCAN_MAX_BYTES

_LOOP_END = "loop/end"
#: 行级近似标记（`store._encode` 写出的 JSON 形态）；扫描全程在字节串上进行。
_LOOP_END_MARK = b'"loop/end"'


def _int_or_none(value: Any) -> int | None:
    """整数字段的宽松读取：非整数（含 bool / 缺失 / 字符串）一律 `None`。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def hit_rate(cache_hit: int | None, prompt: int | None) -> float | None:
    """命中率 = 命中 token / 输入 token；任一缺失或输入非正 ⇒ `None`（未知，不是 0）。"""
    if cache_hit is None or prompt is None or prompt <= 0:
        return None
    return round(cache_hit / prompt, 4)


def turn_from_event(record: Mapping[str, Any], session_id: str) -> dict[str, Any] | None:
    """一条会话记录 → 逐轮用量行；非 `loop/end` 或缺 `usage` 时返回 `None`。"""
    if record.get("type") != _LOOP_END:
        return None
    data = record.get("data") if isinstance(record.get("data"), Mapping) else {}
    usage = data.get("usage") if isinstance(data.get("usage"), Mapping) else None
    if usage is None:
        return None
    prompt = _int_or_none(usage.get("prompt_tokens")) or 0
    completion = _int_or_none(usage.get("completion_tokens")) or 0
    total = _int_or_none(usage.get("total_tokens"))
    cache_hit = _int_or_none(usage.get("cache_read_tokens"))
    cache_miss = _int_or_none(usage.get("cache_miss_tokens"))
    if cache_miss is None and cache_hit is not None and prompt >= cache_hit:
        cache_miss = prompt - cache_hit  # OpenAI 形态：只给命中量，未命中量可推
    return {
        "session_id": session_id,
        "seq": _int_or_none(record.get("seq")),
        # 事件时间（epoch 毫秒，见 session/store.py 的信封）。**成本估算要靠它定峰谷价**
        # （`services/agent/llm/pricing.py`：高峰/空闲双档），故逐轮带出（2026-09-19 追加）。
        "time": _int_or_none(record.get("time")),
        "prompt": prompt,
        "completion": completion,
        "total": total if total is not None else prompt + completion,
        "cache_hit": cache_hit,
        "cache_miss": cache_miss,
        "hit_rate": hit_rate(cache_hit, prompt),
        "estimated": bool(usage.get("estimated")),
    }


def _session_id_of(path: str) -> str:
    name = os.path.basename(str(path))
    return name[: -len(".jsonl")] if name.endswith(".jsonl") else name


def _scan(path: str, session_id: str, max_bytes: int) -> tuple[list[dict[str, Any]], bool]:
    """**原始行扫描**一个会话文件；返回（用量行, 是否被字节上限截断）。"""
    limit = max_bytes if isinstance(max_bytes, int) and max_bytes > 0 else 0
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], False
    capped = bool(limit) and size > limit
    with open(path, "rb") as handle:
        data = handle.read(limit) if capped else handle.read()
    lines = data.split(b"\n")
    if capped and lines:
        lines.pop()  # 末段多半是被截断的半行，不计
    rows: list[dict[str, Any]] = []
    for line in lines:
        if _LOOP_END_MARK not in line:
            continue
        try:
            record = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if not isinstance(record, Mapping):
            continue
        row = turn_from_event(record, session_id)
        if row is not None:
            rows.append(row)
    return rows, capped


def iter_session_turns(
    path: str,
    *,
    session_id: str | None = None,
    max_bytes: int = SCAN_MAX_BYTES,
) -> Iterator[dict[str, Any]]:
    """逐个产出某会话文件的用量行（大文件按字节上限截断，见模块 docstring）。"""
    rows, _capped = _scan(path, session_id or _session_id_of(path), max_bytes)
    yield from rows


def _accumulate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """把用量行累加成汇总块（命中率只在有 cache 数据的轮次上算）。"""
    prompt = completion = total = 0
    cache_hit = cache_miss = 0
    hit_denom = 0  # 命中率分母：只含 cache 已知的轮次
    hit_known = miss_known = estimated_turns = 0
    for row in rows:
        prompt += int(row.get("prompt") or 0)
        completion += int(row.get("completion") or 0)
        total += int(row.get("total") or 0)
        if row.get("estimated"):
            estimated_turns += 1
        if row.get("cache_hit") is not None:
            hit_known += 1
            cache_hit += int(row["cache_hit"])
            hit_denom += int(row.get("prompt") or 0)
        if row.get("cache_miss") is not None:
            miss_known += 1
            cache_miss += int(row["cache_miss"])
    return {
        "turns": len(rows),
        "prompt": prompt,
        "completion": completion,
        "total": total,
        "cache_hit": cache_hit if hit_known else None,
        "cache_miss": cache_miss if miss_known else None,
        "hit_rate": round(cache_hit / hit_denom, 4) if hit_known and hit_denom > 0 else None,
        "estimated_turns": estimated_turns,
        "cache_unknown_turns": len(rows) - hit_known,
    }


def aggregate_usage(paths: Iterable[str], *, max_bytes: int = SCAN_MAX_BYTES) -> dict[str, Any]:
    """聚合若干会话文件的用量（**纯函数、只读**）。

    返回 `{sessions: [按会话汇总...], turns: [逐轮行...], summary: {汇总}}`：
    无 `loop/end` 轮次（或不可读）的会话**不计入** `sessions` 列表；
    `summary["sessions"]` 是纳入统计的会话**个数**。
    """
    session_rows: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    for path in paths:
        if not path:
            continue
        session_id = _session_id_of(path)
        rows, capped = _scan(str(path), session_id, max_bytes)
        if not rows:
            continue
        turns.extend(rows)
        session_rows.append(
            {
                "session_id": session_id,
                "path": str(path),
                "capped": capped,
                **_accumulate(rows),
            }
        )
    summary = {"sessions": len(session_rows), **_accumulate(turns)}
    return {"sessions": session_rows, "turns": turns, "summary": summary}


def usage_stats(
    kb_path: str,
    session_id: str | None = None,
    *,
    max_bytes: int = SCAN_MAX_BYTES,
) -> dict[str, Any]:
    """一个知识库（或其单个会话）的用量汇总（**只读**）。

    `session_id` 省略 ⇒ 统计库内全部会话；非空 ⇒ 只统计该会话（id 非法由
    `store.session_file()` 抛 `ValueError`）。返回结构与 `aggregate_usage()` 一致，
    并附 `kb_path` 便于调用方回显。
    """
    sid = (session_id or "").strip()
    if sid:
        paths = [session_file(kb_path, sid)]
    else:
        paths = [str(row.get("path") or "") for row in list_sessions(kb_path)]
    report = aggregate_usage(paths, max_bytes=max_bytes)
    return {"kb_path": os.path.abspath(kb_path), **report}
