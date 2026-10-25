# S5（task-124）：调用级 trace 成本 + 派生索引 + 容量淘汰 + MCP `_meta` OTel 透传。
# 设计依据：`artifacts/agent/verify/debate/position/agent-arch-position.md` §2-Q5 与 task-124 关闭条件。
# 口径：**不新建并行事实源** —— 会话 JSONL（`trace/call` 事件）仍是唯一事实源；
#       `<kb>/.memoria/agent/trace/index/**` 只是可删除、可从会话重建的 cache。

"""调用级 trace（S5）：每次工具调用的成本字段、有界派生索引、聚合查询与 OTel 上下文透传。

## 为什么要有这一层（不是再造 trace）

`<kb>/.memoria/agent/sessions/<sid>.jsonl` + `audit.py` + 4 把 session 查询工具**已经存在**。
本轮只补三件（task-124）：

1. **调用级成本字段**：`tool/call`/`tool/result` 是"过程播报"，没有成本口径（谁贵、哪里被截断、
   审批拒了多少、写了哪几批）。新增一种**只追加**的会话事件 `trace/call`（回放/压缩/语义抽取
   对未知 type 一律跳过 ⇒ 不改请求体、不动 KV 前缀），载荷见 `build_entry()`。
2. **跨进程 `_meta`**：MCP 的 OTel 约定（`traceparent`/`tracestate`/`baggage`）透传到 trace 条目，
   使进程内/跨进程两侧可凭同一 `trace_id` 串起来（`otel_trace_id()`）。
3. **容量与淘汰**：派生索引按 session 分片，每会话 ≤`MAX_ENTRIES_PER_SESSION` 条，
   FIFO 淘汰**非写路径且无错误**的条目；写路径与错误条目**永不淘汰**；每条 ≤`MAX_ENTRY_BYTES`。

## 隐私硬边界（不是口头承诺，`result_preview_chars` 有测试断言）

trace 条目**不含**工具结果正文：只有
`result_chars`（长度）+ `result_digest`（sha256 前缀）+ `result_preview`（**首 256 字符**）。
参数同理，只留 `args_digest`。为什么仍可能有敏感信息：会话 JSONL 的 `tool/result` 本来就存全文
（回放需要），trace 的边界是**不复制第二份全文**、并把可检索面压到 256 字符。

## 索引是 cache，不是事实源

- 写入时机：**只在查询/聚合/显式重建时**生成（`ensure_index()` / `rebuild_index()`）；
  工具调用热路径**不写索引** ⇒ 不会在会话目录之外产生"写副作用"，也不影响既有快照类测试。
- 删除整个 `trace/` 目录后，`rebuild_index()` 可从会话 JSONL 逐字节重建同一份有界投影
  （淘汰是确定性的：从最旧的可淘汰条目开始丢）。
- 重建耗时 > `REBUILD_BUDGET_S`（5s/会话）时**降级为按需生成**并在返回值里标 `degraded=True`
  （position §2-Q5 的 falsifier 应对），不假装"很快"。

## 分片形态（与任务文本的一处自洽取舍）

任务文本写的是 `trace/index.jsonl` 单文件，但同时要求"**按 session 分片**"与"每会话 5000 条 FIFO"。
单文件无法同时满足"按会话独立上限"与"会话删除后可丢弃"（且会退化成第二个全局日志）。
因此落地为 **`trace/index/<session_id>.jsonl` 每会话一片**（首行是 index header，随后是条目）；
删任意一片都只影响该会话的缓存。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from memoria.services.agent.section_index import estimate_tokens
from memoria.services.agent.session.store import read_session, session_file, sessions_dir

__all__ = [
    "EVENT_TRACE_CALL",
    "TRACE_SCHEMA",
    "INDEX_SCHEMA",
    "MAX_ENTRIES_PER_SESSION",
    "MAX_ENTRY_BYTES",
    "RESULT_PREVIEW_CHARS",
    "REBUILD_BUDGET_S",
    "OTEL_KEYS",
    "OtelContext",
    "aggregate_cost",
    "build_entry",
    "current_otel",
    "ensure_index",
    "index_dir",
    "index_path",
    "otel_scope",
    "otel_trace_id",
    "parse_otel_meta",
    "read_index_entries",
    "rebuild_index",
    "record_mcp_call",
]

#: 会话事件类型（只增不改；未知 type 对回放/压缩/抽取一律无副作用）。
EVENT_TRACE_CALL = "trace/call"
TRACE_SCHEMA = "agent-trace-call/v1"
INDEX_SCHEMA = "agent-trace-index/v1"

#: 每会话索引条目上限（FIFO 淘汰**可淘汰**条目；写路径/错误条目受保护）。
MAX_ENTRIES_PER_SESSION = 5000
#: 索引单条序列化上限（超了先缩 `result_preview`，绝不丢条目语义字段）。
MAX_ENTRY_BYTES = 2048
#: 正文预览硬边界（隐私）：只留前 N 个字符 + 全文 digest + 长度。
RESULT_PREVIEW_CHARS = 256
#: 单会话重建耗时预算（task-124 关闭条件 5；超了标 degraded，不假装达标）。
REBUILD_BUDGET_S = 5.0

#: OTel `_meta` 的三个标准键（MCP 约定：随每个请求的 `_meta` 透传）。
OTEL_KEYS = ("traceparent", "tracestate", "baggage")

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _digest(text: str) -> str:
    """正文/参数的 sha256 前缀（16 hex = 64 bit；隐私面只给摘要，不给原文）。"""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


# ── OTel 上下文（跨进程 `_meta` 透传）────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class OtelContext:
    """从 MCP `_meta` 抽出的 OTel 上下文（只保留 W3C 三个标准键）。"""

    traceparent: str | None = None
    tracestate: str | None = None
    baggage: str | None = None

    def as_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in OTEL_KEYS:
            value = getattr(self, key)
            if value:
                out[key] = value
        return out


#: 当前执行上下文里的 OTel 上下文（MCP server 在分发工具前置入 ⇒ 其内部嵌套的
#: 进程内记录/审计自动继承同一 `traceparent`，这是"跨边界串起两侧"的机制）。
_CURRENT_OTEL: ContextVar[OtelContext | None] = ContextVar("memoria_otel_context", default=None)


def current_otel() -> OtelContext | None:
    return _CURRENT_OTEL.get()


@contextmanager
def otel_scope(ctx: OtelContext | None):
    """把 OTel 上下文置入当前作用域（退出时精确恢复；嵌套安全）。"""
    token = _CURRENT_OTEL.set(ctx)
    try:
        yield ctx
    finally:
        _CURRENT_OTEL.reset(token)


def parse_otel_meta(meta: Mapping[str, Any] | None) -> OtelContext | None:
    """从 MCP 请求 `_meta` 抽取 OTel 三键；一个都没有 ⇒ `None`（不造空上下文）。"""
    if not isinstance(meta, Mapping):
        return None
    values = {
        key: str(meta[key]).strip() for key in OTEL_KEYS if isinstance(meta.get(key), str) and str(meta[key]).strip()
    }
    if not values:
        return None
    return OtelContext(**{key: values.get(key) for key in OTEL_KEYS})


def otel_trace_id(ctx: OtelContext | None) -> str | None:
    """`traceparent` 里的 32-hex `trace_id`（格式不合法返回 `None`，不猜）。"""
    if ctx is None or not ctx.traceparent:
        return None
    match = _TRACEPARENT_RE.match(ctx.traceparent.strip().lower())
    return match.group(1) if match else None


# ── 条目构造 ────────────────────────────────────────────────────────────────
def _write_block(meta: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """工具自报的写回执（`ToolOutput.meta["plan_txid"]` / `meta["write"]`）→ 规范化。"""
    if not isinstance(meta, Mapping):
        return None
    raw = meta.get("write")
    if not isinstance(raw, Mapping):
        return None
    files = [str(item) for item in (raw.get("files") or []) if str(item)]
    return {
        "files": files,
        "lines_added": int(raw.get("lines_added") or 0),
        "lines_removed": int(raw.get("lines_removed") or 0),
        "backup_txid": (str(raw["backup_txid"]) if raw.get("backup_txid") else None),
        "undo_available": bool(raw.get("undo_available")),
    }


def build_entry(
    *,
    tool_id: str,
    turn: int | None,
    arguments: Any,
    content: str,
    error_code: str | None = None,
    truncated: bool | None = None,
    duration_ms: int | None = None,
    approval: Mapping[str, Any] | None = None,
    meta: Mapping[str, Any] | None = None,
    transport: str = "inprocess",
    otel: OtelContext | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """构造一条 `trace/call` 载荷（**唯一构造点**；隐私边界在此）。

    `truncated`：`None` = 该工具没有声明（`truncated_known=False`），聚合时只对"已知"的算
    截断率 —— 不把"没声明"伪装成"没截断"。
    """
    text = str(content or "")
    write = _write_block(meta)
    entry: dict[str, Any] = {
        "v": TRACE_SCHEMA,
        "ts": int(now_ms if now_ms is not None else _now_ms()),
        "tool_id": str(tool_id or ""),
        "turn": turn,
        "args_digest": _digest(json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)),
        "result_chars": len(text),
        "result_digest": _digest(text),
        "result_preview": text[:RESULT_PREVIEW_CHARS],
        "est_tokens": estimate_tokens(text),
        "truncated": bool(truncated) if truncated is not None else False,
        "truncated_known": truncated is not None,
        "approval": {
            "asked": bool((approval or {}).get("asked")),
            "decided": (str(approval["decided"]) if (approval or {}).get("decided") else None),
        },
        "error_code": str(error_code) if error_code else None,
        "write": write,
        "transport": str(transport or "inprocess"),
    }
    if duration_ms is not None:
        entry["duration_ms"] = int(duration_ms)
    if isinstance(meta, Mapping) and meta.get("plan_txid"):
        entry["plan_txid"] = str(meta["plan_txid"])
    if otel is not None:
        payload = otel.as_dict()
        if payload:
            entry["otel"] = payload
            tid = otel_trace_id(otel)
            if tid:
                entry["trace_id"] = tid
    return entry


def _fit_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """把一条条目压进 `MAX_ENTRY_BYTES`（硬上限；只缩可缩字段，不丢成本/写路径语义）。

    收缩阶梯（**确定性**）：`result_preview` 折半 → 去 `tracestate` → 去 `baggage` → 去整个
    `otel`（保留 `trace_id`）→ `write.files` 只留前 10 个并标注 `files_total`/`files_truncated`。
    写路径/错误条目的"受保护"是**不淘汰**，不是"可以超尺寸"；因此被保护条目同样受此硬上限约束。
    """

    def _size(row: Mapping[str, Any]) -> int:
        return len(json.dumps(row, ensure_ascii=False).encode("utf-8"))

    row = dict(entry)
    steps = 0
    while _size(row) > MAX_ENTRY_BYTES:
        steps += 1
        preview = str(row.get("result_preview") or "")
        if preview:
            row["result_preview"] = preview[: max(0, len(preview) // 2)]
            continue
        otel = row.get("otel")
        if isinstance(otel, Mapping) and otel.get("tracestate"):
            row["otel"] = {key: value for key, value in otel.items() if key != "tracestate"}
            continue
        if isinstance(otel, Mapping) and otel.get("baggage"):
            row["otel"] = {key: value for key, value in otel.items() if key != "baggage"}
            continue
        if isinstance(otel, Mapping):
            row.pop("otel", None)
            continue
        write = row.get("write")
        files = list((write or {}).get("files") or []) if isinstance(write, Mapping) else []
        if isinstance(write, Mapping) and len(files) > 10:
            row["write"] = {
                **write,
                "files": files[:10],
                "files_total": len(files),
                "files_truncated": True,
            }
            continue
        break
    if steps:
        row["entry_fitted"] = True
    return row


# ── 容量：FIFO 淘汰（写路径 / 错误条目受保护）───────────────────────────────
def _protected(entry: Mapping[str, Any]) -> bool:
    """写路径或错误条目：**永不淘汰**（写回执是审计线索；错误是排障证据）。"""
    return bool(entry.get("write")) or bool(entry.get("error_code"))


def apply_capacity(entries: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int, bool]:
    """按容量规则裁剪条目（**确定性**：从最旧的可淘汰条目开始丢）。

    返回 `(kept, dropped, over_capacity)`。`over_capacity=True` 表示受保护条目本身已超上限
    （此时一条也不丢，但如实标注，不假装 ≤ 上限）。
    """
    rows = [_fit_entry(entry) for entry in entries]
    excess = max(0, len(rows) - MAX_ENTRIES_PER_SESSION)
    if excess == 0:
        return rows, 0, False
    droppable = [index for index, row in enumerate(rows) if not _protected(row)]
    drop = set(droppable[:excess])
    kept = [row for index, row in enumerate(rows) if index not in drop]
    return kept, len(drop), len(kept) > MAX_ENTRIES_PER_SESSION


# ── 会话侧：trace/call 事件的读取 ─────────────────────────────────────────────
def trace_events(kb_path: str, session_id: str) -> list[dict[str, Any]]:
    """一个会话里的全部 `trace/call` 事件（**按 seq 升序**；会话 JSONL 是事实源）。"""
    rows: list[tuple[int, dict[str, Any]]] = []
    for record in read_session(kb_path, session_id):
        if record.get("type") != EVENT_TRACE_CALL:
            continue
        seq = record.get("seq")
        order = int(seq) if isinstance(seq, int) else len(rows)
        data = record.get("data")
        if isinstance(data, Mapping):
            rows.append((order, dict(data)))
    rows.sort(key=lambda item: item[0])
    return [row for _, row in rows]


# ── 派生索引（cache）────────────────────────────────────────────────────────
def index_dir(kb_path: str) -> str:
    return os.path.join(os.path.abspath(kb_path), ".memoria", "agent", "trace", "index")


def index_path(kb_path: str, session_id: str) -> str:
    key = (session_id or "").strip()
    if not _SAFE_ID_RE.match(key):
        raise ValueError(f"非法会话 id：{session_id!r}")
    return os.path.join(index_dir(kb_path), f"{key}.jsonl")


def _session_source(kb_path: str, session_id: str) -> dict[str, Any]:
    path = session_file(kb_path, session_id)
    if not os.path.isfile(path):
        return {"size": 0, "mtime_ms": 0, "exists": False}
    stat = os.stat(path)
    return {"size": int(stat.st_size), "mtime_ms": int(stat.st_mtime * 1000), "exists": True}


def _write_shard(kb_path: str, session_id: str, header: Mapping[str, Any], entries: Iterable[Mapping[str, Any]]) -> str:
    path = index_path(kb_path, session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n"
        for record in [header, *entries]
    )
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return path


def _read_shard(kb_path: str, session_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    path = index_path(kb_path, session_id)
    if not os.path.isfile(path):
        return None, []
    header: dict[str, Any] | None = None
    entries: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if header is None:
                header = record if isinstance(record, dict) else None
                continue
            if isinstance(record, dict):
                entries.append(record)
    return header, entries


def rebuild_index(kb_path: str, session_id: str) -> dict[str, Any]:
    """从会话 JSONL 重建一个会话的索引分片（cache 语义；可反复调用，结果确定）。

    返回 `{status, session_id, entries, dropped, over_capacity, elapsed_ms, degraded, path}`。
    """
    started = time.perf_counter()
    source = _session_source(kb_path, session_id)
    events = trace_events(kb_path, session_id)
    kept, dropped, over = apply_capacity(events)
    header = {
        "v": INDEX_SCHEMA,
        "kind": "index-header",
        "session_id": session_id,
        "source": source,
        "entries": len(kept),
        "dropped": dropped,
        "over_capacity": over,
        "rebuilt_at": _now_ms(),
        "max_entries": MAX_ENTRIES_PER_SESSION,
        "max_entry_bytes": MAX_ENTRY_BYTES,
    }
    path = _write_shard(kb_path, session_id, header, kept)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "status": "ok",
        "session_id": session_id,
        "entries": len(kept),
        "dropped": dropped,
        "over_capacity": over,
        "elapsed_ms": elapsed_ms,
        "degraded": elapsed_ms > int(REBUILD_BUDGET_S * 1000),
        "path": path,
    }


def ensure_index(kb_path: str, session_id: str) -> dict[str, Any]:
    """确保分片存在且与源文件（size/mtime）一致；不一致则重建。cache 失效不影响正确性。"""
    header, _entries = _read_shard(kb_path, session_id)
    source = _session_source(kb_path, session_id)
    if header is not None and header.get("source") == source and header.get("max_entries") == MAX_ENTRIES_PER_SESSION:
        return {
            "status": "ok",
            "session_id": session_id,
            "entries": int(header.get("entries") or 0),
            "dropped": int(header.get("dropped") or 0),
            "over_capacity": bool(header.get("over_capacity")),
            "rebuilt": False,
            "elapsed_ms": 0,
            "degraded": False,
        }
    rebuilt = rebuild_index(kb_path, session_id)
    rebuilt["rebuilt"] = True
    return rebuilt


def read_index_entries(kb_path: str, session_id: str) -> list[dict[str, Any]]:
    """读一个会话的 index 条目（自动 ensure；只读 cache，失败不抛）。"""
    ensure_index(kb_path, session_id)
    _header, entries = _read_shard(kb_path, session_id)
    return entries


def _known_sessions(kb_path: str) -> list[str]:
    directory = sessions_dir(kb_path)
    if not os.path.isdir(directory):
        return []
    out: list[str] = []
    for name in os.listdir(directory):
        if name.endswith(".jsonl") and _SAFE_ID_RE.match(name[: -len(".jsonl")]):
            out.append(name[: -len(".jsonl")])
    out.sort()
    return out


# ── 聚合（只读；不新增原始数据）───────────────────────────────────────────────
def _time_bound(value: Any) -> int | None:
    """`scope` 的时间下/上界：epoch 毫秒（int）或 ISO 8601 字符串（本地不解析时区歧义）。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    from datetime import datetime

    text = str(value).strip()
    if not text:
        return None
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)


def _match_scope(entry: Mapping[str, Any], scope: Mapping[str, Any]) -> bool:
    if scope.get("tool") and str(entry.get("tool_id") or "") != str(scope["tool"]):
        return False
    if scope.get("transport") and str(entry.get("transport") or "") != str(scope["transport"]):
        return False
    if scope.get("trace_id") and str(entry.get("trace_id") or "") != str(scope["trace_id"]):
        return False
    ts = int(entry.get("ts") or 0)
    lower = _time_bound(scope.get("time_from"))
    upper = _time_bound(scope.get("time_to"))
    if lower is not None and ts < lower:
        return False
    if upper is not None and ts > upper:
        return False
    return True


def aggregate_cost(kb_path: str, scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """按会话/工具/时间窗聚合 trace 成本（**数字可从 index 条目逐项复算，误差 0**）。

    `scope`：`{session_id?, tool?, transport?, trace_id?, time_from?, time_to?}`。
    未给 `session_id` 时遍历库内全部会话（每会话一片，自动 ensure/rebuild）。
    """
    query = dict(scope or {})
    requested = str(query.get("session_id") or "").strip()
    session_ids = [requested] if requested else _known_sessions(kb_path)
    entries: list[dict[str, Any]] = []
    rebuilds: list[dict[str, Any]] = []
    for session_id in session_ids:
        info = ensure_index(kb_path, session_id)
        rebuilds.append(
            {
                "session_id": session_id,
                "rebuilt": bool(info.get("rebuilt")),
                "elapsed_ms": int(info.get("elapsed_ms") or 0),
                "degraded": bool(info.get("degraded")),
                "dropped": int(info.get("dropped") or 0),
                "over_capacity": bool(info.get("over_capacity")),
            }
        )
        for entry in read_index_entries(kb_path, session_id):
            if _match_scope(entry, query):
                entries.append({**entry, "session_id": session_id})

    by_tool: dict[str, dict[str, Any]] = {}
    sums: dict[str, Any] = {
        "calls": len(entries),
        "sessions": len({entry.get("session_id") for entry in entries}),
        "result_chars": 0,
        "est_tokens": 0,
        "truncated_count": 0,
        "truncated_known": 0,
        "error_count": 0,
        "approval_asked": 0,
        "approval_denied": 0,
        "write_calls": 0,
        "write_files": 0,
        "plan_txids": [],
        "transports": {},
        "trace_ids": [],
    }
    for entry in entries:
        tool = str(entry.get("tool_id") or "")
        bucket = by_tool.setdefault(tool, {"calls": 0, "est_tokens": 0, "errors": 0})
        bucket["calls"] += 1
        tokens = int(entry.get("est_tokens") or 0)
        bucket["est_tokens"] += tokens
        sums["result_chars"] += int(entry.get("result_chars") or 0)
        sums["est_tokens"] += tokens
        if entry.get("truncated_known"):
            sums["truncated_known"] += 1
            if entry.get("truncated"):
                sums["truncated_count"] += 1
        if entry.get("error_code"):
            sums["error_count"] += 1
            bucket["errors"] += 1
        approval = entry.get("approval") if isinstance(entry.get("approval"), Mapping) else {}
        if approval.get("asked"):
            sums["approval_asked"] += 1
            if str(approval.get("decided") or "") != "allowed-once":
                sums["approval_denied"] += 1
        write = entry.get("write") if isinstance(entry.get("write"), Mapping) else None
        if write is not None:
            sums["write_calls"] += 1
            sums["write_files"] += len(write.get("files") or [])
        if entry.get("plan_txid"):
            sums["plan_txids"].append(str(entry["plan_txid"]))
        transport = str(entry.get("transport") or "inprocess")
        sums["transports"][transport] = int(sums["transports"].get(transport) or 0) + 1
        if entry.get("trace_id"):
            sums["trace_ids"].append(str(entry["trace_id"]))

    calls = sums["calls"]
    known = sums["truncated_known"]

    def _rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 6) if denominator else None

    return {
        "status": "ok",
        "scope": {
            key: query[key]
            for key in ("session_id", "tool", "transport", "trace_id", "time_from", "time_to")
            if query.get(key) is not None
        },
        "calls": calls,
        "sessions": sums["sessions"],
        "result_chars": sums["result_chars"],
        "est_tokens": sums["est_tokens"],
        "truncated": {
            "count": sums["truncated_count"],
            "known": known,
            "unknown": calls - known,
            "rate": _rate(sums["truncated_count"], known),
        },
        "errors": {"count": sums["error_count"], "rate": _rate(sums["error_count"], calls)},
        "approval": {
            "asked": sums["approval_asked"],
            "denied": sums["approval_denied"],
            "denial_rate": _rate(sums["approval_denied"], sums["approval_asked"]),
        },
        "write": {"calls": sums["write_calls"], "files": sums["write_files"], "txids": sums["plan_txids"]},
        "transports": sums["transports"],
        "trace_ids": sorted(set(sums["trace_ids"])),
        "by_tool": {key: by_tool[key] for key in sorted(by_tool)},
        "index": {
            "shards": rebuilds,
            "rebuilt": sum(1 for row in rebuilds if row["rebuilt"]),
            "degraded": any(row["degraded"] for row in rebuilds),
            "dropped_total": sum(row["dropped"] for row in rebuilds),
        },
        "tokens_estimated": True,
    }


# ── MCP 侧记录（跨进程入口的唯一调用点）───────────────────────────────────────
def record_mcp_call(
    kb_path: str,
    session_id: str,
    *,
    tool_id: str,
    arguments: Any,
    content: str,
    meta: Mapping[str, Any] | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
    otel: OtelContext | None = None,
    extra_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """把一次 MCP 工具调用落成会话 `trace/call` 事件（**不写索引**：索引只在查询时重建）。

    `extra_meta` 是工具结构化回执（如 `propose_write` 的 `txid/files`），用于成本条目的 `write` 块。
    """
    entry = build_entry(
        tool_id=tool_id,
        turn=None,
        arguments=arguments,
        content=content,
        error_code=error_code,
        truncated=None,
        duration_ms=duration_ms,
        approval={"asked": False, "decided": None},
        meta=extra_meta,
        transport="mcp",
        otel=otel,
    )
    entry["session_id"] = session_id
    try:
        from memoria.services.agent.session.store import SessionStore

        store = SessionStore(os.path.abspath(kb_path), session_id)
        store.append(EVENT_TRACE_CALL, entry)
        store.flush()
    except (OSError, ValueError) as exc:  # 观测失败不得影响工具调用（同 audit 的 fail-open 口径）
        return {"status": "error", "message": str(exc), "entry": entry}
    return {"status": "ok", "entry": entry}
