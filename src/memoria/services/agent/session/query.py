# 语义移植自 deepseek-harness packages/session-query/session-query 的 extraction.ts + filters.ts
# （MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""会话检索（M2）：在 `<kb>/.memoria/agent/sessions/*.jsonl` 上做**字面量**全文检索。

对照上游 `dsh-session-query` 的两处语义：

**1. 语义文本抽取（`extraction.ts` 的 `extractSessionEventText`）** —— 只有"第一方语义事件"
贡献可检索文本，结构性与未知事件一律为空：

| 事件 | 抽取 |
|---|---|
| `user/message` | `text` |
| `assistant/message` | `content` + 各 `tool_calls` 的 `name` / `arguments` |
| `tool/result` | `content` |
| `tool/call`、`step/*`、`loop/end` | **空**（结构性，不含语义文本） |
| 其它/未知 | **空**（上游口径：未知事件不因载荷里恰好有字符串就变成可检索） |

**本地新增一行**：`compaction`（我们自己的事件）取其 `summary` —— 那是模型写的语义正文，
不检索它等于把被压缩掉的那段对话从检索面里抹掉。上游没有该事件，故属本地扩展。

**2. 字面量匹配（`filters.ts` 的 `compileSessionTextFilter`）** —— 查询被当作**数据**而非
可执行语法：按空白切成词、**逐词正则转义**（杜绝正则注入）、词间以 `\\s+` 连接（**空白弹性**）、
整条大小写不敏感且 Unicode 感知。空查询（纯空白）直接报错。

过滤子沿用上游结构：**子句之间 AND、子句内取值 OR**（`SessionResultFilter` /
`SessionEventResultFilter`）；本地实现了其中的 `type` / `time` / `seq` / `text` 四类事件子句
（上游另有 `surface`，本地无"表面"概念、压缩覆盖由 `history` 在回放层处理）。

## 本地适配与偏差

- 上游语料是 `ctx.sessions`（live 优先）+ SQLite FTS 索引；本地没有 live 会话注册表，语料就是
  **磁盘上的会话文件**（按 `modified_at` 倒序），也没有索引 —— 用**字节级预筛**代替：先在不解码
  的字节串上做 ASCII 小写化后的**逐词存在性**检查，全词命中才解析该文件。故大小写不敏感在预筛
  阶段只对 ASCII 成立（非 ASCII 的大小写折叠只在解析后生效）—— 这只影响"要不要解析该文件"的
  性能判断，**不影响命中结果的正确性**：预筛判否只会跳过文件，而可解析的命中必然先在字节层命中过。
- **排序口径**：上游按「该会话最强匹配事件」做**相关性**排序；本地没有相关度评分器，改为**按会话
  的 `modified_at` 倒序**（最近聊过的先出），组内按 `seq` 升序。已登记为偏差。
- **不移植**：不透明游标 `SessionSearchCursor`（那是给 SQLite 分页用的，本地用显式 `limit`）、
  `lineage` / `trace`（会话谱系与事件溯源：本地没有 fork/派生会话）、`tracing.ts` /
  `observation.ts`（宿主可观测性）、`session-query-sqlite`（本地不引索引）、
  `session-log-export`（导出 UI，本轮不做）。
- `snippet` 的**窗口算法未逐字对齐**：上游只说"匹配点附近的纯文本摘录"，此处实现为
  「首个匹配点前后各 `SNIPPET_WIDTH` 字符 + 被裁剪侧补省略号」，已登记为偏差。
- **有界**（对齐上游「Apply bounds to the complete result」）：单份文件 `SESSION_QUERY_MAX_BYTES`
  上限、跨会话扫描份数上限、单页命中数上限、摘要窗口上限；超出上限的**事实**（`capped`）在
  `search_session` 的返回里不体现 —— 需要该事实的调用方用 `history.summarize_session_file()`
  的 `capped` 字段（会话列表已在用）。
- **在原始事件上检索**（不套用 `compaction/prune` 的裁剪视图）：被裁掉的工具输出中间段**仍可被
  搜到** —— 本地取舍是「宁可搜得全」，不让裁剪把历史从检索面抹掉（上游检索走的是裁剪后的表面）。

## 只读

本模块只读会话文件（按字节读 + 逐行 `json.loads`），不写盘、不联网、不打印。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from memoria.services.agent.session.history import (
    ASSISTANT_MESSAGE,
    COMPACTION,
    SESSION_SCAN_MAX_BYTES,
    TOOL_RESULT,
    USER_MESSAGE,
    summarize_session_file,
)
from memoria.services.agent.session.store import list_sessions, session_file

__all__ = [
    "DEFAULT_HIT_LIMIT",
    "DEFAULT_SESSION_LIMIT",
    "MAX_HIT_LIMIT",
    "MAX_SESSION_LIMIT",
    "SESSION_QUERY_MAX_BYTES",
    "SNIPPET_WIDTH",
    "SessionEventHit",
    "SessionGroupHit",
    "SessionQueryError",
    "compile_text_pattern",
    "event_text",
    "search_session",
    "search_sessions",
    "snippet",
]

#: 单份会话文件的扫描字节上限（与 `history.SESSION_SCAN_MAX_BYTES` 同值同意图：不漏大文件，
#: 也不因某个超大会话把检索拖垮）。
SESSION_QUERY_MAX_BYTES = SESSION_SCAN_MAX_BYTES
#: 跨会话检索默认扫描多少份会话（按 `modified_at` 倒序取最新的）。
DEFAULT_SESSION_LIMIT = 50
MAX_SESSION_LIMIT = 500
#: 单页命中的默认与上限条数。
DEFAULT_HIT_LIMIT = 20
MAX_HIT_LIMIT = 200
#: 命中摘要窗口：首个匹配点前后各取多少字符。
SNIPPET_WIDTH = 80
#: 摘要被裁剪时补的省略号。
SNIPPET_ELLIPSIS = "…"

#: 不贡献语义文本的结构性事件（上游 `extraction.ts` 里显式返回 `''` 的那批）。
_STRUCTURAL = frozenset({"tool/call", "step/start", "step/error", "loop/end"})


class SessionQueryError(ValueError):
    """检索参数非法（对齐上游 `SESSION_QUERY_INVALID_FILTER`）。"""


def _data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("data")
    return value if isinstance(value, Mapping) else {}


def _joined(parts: Iterable[Any]) -> str:
    """按上游 `joinText` 口径拼接：逐段 `strip()`、丢空段、以换行连接。"""
    return "\n".join(text for text in (str(part or "").strip() for part in parts) if text)


def event_text(event: Mapping[str, Any]) -> str:
    """抽取一条会话事件的**语义文本**；非语义事件返回空串（规则表见模块 docstring）。"""
    kind = str(event.get("type") or "")
    if kind in _STRUCTURAL:
        return ""
    data = _data(event)
    if kind == USER_MESSAGE:
        return _joined([data.get("text")])
    if kind == ASSISTANT_MESSAGE:
        parts: list[Any] = [data.get("content")]
        calls = data.get("tool_calls")
        if isinstance(calls, Sequence) and not isinstance(calls, (str, bytes)):
            for call in calls:
                if isinstance(call, Mapping):
                    parts.extend([call.get("name"), call.get("arguments")])
        return _joined(parts)
    if kind == TOOL_RESULT:
        return _joined([data.get("content")])
    if kind == COMPACTION:
        # 本地扩展：被压缩的旧对话只剩这份摘要，不检索它会从检索面消失
        return _joined([data.get("summary")])
    return ""


def compile_text_pattern(text: str) -> re.Pattern[str]:
    """把查询编译成**字面量**模式：空白弹性 + 大小写不敏感 + Unicode 感知。

    语义移植自上游 `filters.ts::compileSessionTextFilter`：逐词转义后以 `\\s+` 连接，故查询
    永远只是数据、不是可执行的正则语法（杜绝注入）。空查询（或纯空白）报错。
    """
    trimmed = (text or "").strip()
    if not trimmed:
        raise SessionQueryError("检索词必须含非空白字符")
    pattern = r"\s+".join(re.escape(part) for part in re.split(r"\s+", trimmed))
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


def snippet(text: str, pattern: re.Pattern[str], *, width: int = SNIPPET_WIDTH) -> str:
    """首个匹配点前后的纯文本摘录（被裁剪的一侧补省略号）。

    上游只说"匹配点附近的纯文本摘录"，**窗口算法未逐字移植**（已登记为偏差）。空白先折叠成
    单空格（避免把换行/缩进原样塞进摘要）。找不到匹配时按开头截断。
    """
    body = " ".join(str(text or "").split())
    if not body or width <= 0:
        return body
    match = pattern.search(body)
    start = 0 if match is None else max(0, match.start() - width)
    end = len(body) if match is None else min(len(body), match.end() + width)
    head = SNIPPET_ELLIPSIS if start > 0 else ""
    tail = SNIPPET_ELLIPSIS if end < len(body) else ""
    return f"{head}{body[start:end]}{tail}"


@dataclass(frozen=True, slots=True)
class SessionEventHit:
    """一条事件级命中（对应上游 `SessionEventSearchHit`）。"""

    session_id: str
    seq: int
    time: int
    type: str
    snippet: str


@dataclass(frozen=True, slots=True)
class SessionGroupHit:
    """一个会话的跨会话命中（对应上游 `SessionSearchHit`：按会话分组）。"""

    session_id: str
    modified_at: int
    title: str
    turn_count: int
    hit_count: int
    best: SessionEventHit


@dataclass
class _Filters:
    """一次检索的事件过滤子（子句间 AND；`types` 子句内 OR）。"""

    types: tuple[str, ...] | None = None
    time_from: int | None = None
    time_to: int | None = None
    seq_from: int | None = None
    seq_to: int | None = None

    def accepts(self, event: Mapping[str, Any], pattern: re.Pattern[str]) -> bool:
        if self.types is not None and str(event.get("type") or "") not in self.types:
            return False
        moment = event.get("time")
        if isinstance(moment, int):
            if self.time_from is not None and moment < self.time_from:
                return False
            if self.time_to is not None and moment > self.time_to:
                return False
        seq = event.get("seq")
        if isinstance(seq, int):
            if self.seq_from is not None and seq < self.seq_from:
                return False
            if self.seq_to is not None and seq > self.seq_to:
                return False
        return bool(pattern.search(event_text(event)))


def _limit(value: Any, default: int, upper: int, *, name: str) -> int:
    """有界化一个调用方给的条数上限：`None` ⇒ 默认；负数/非整数 ⇒ 报错（fail loud）。"""
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SessionQueryError(f"{name} 必须是非负整数（收到 {value!r}）")
    return min(value, upper)


def _prefilter_ok(blob: bytes, tokens: Sequence[bytes]) -> bool:
    """字节级预筛：查询的**每个词**都必须以 ASCII 小写形态出现在文件字节里。

    `bytes.lower()` 只影响 ASCII A–Z，对 UTF-8 其余字节是恒等变换；故判否是安全的（可解析的
    命中必然先在字节层命中过），判可则是近似（交给解析后的大小写折叠决定）。
    """
    lowered = blob.lower()
    return all(token in lowered for token in tokens)


def _scan(
    path: str,
    session_id: str,
    pattern: re.Pattern[str],
    tokens: Sequence[bytes],
    filters: _Filters,
    cap: int,
) -> list[SessionEventHit]:
    """扫一份会话文件（**有界**）：先字节预筛，再逐行解析取语义文本。

    文件不存在 ⇒ 空结果（与 `history.build_history()` 的"会话不存在 = 空历史"同口径：
    面板可能拿着一个已被删除的会话 id）。
    """
    if not os.path.isfile(path):
        return []
    with open(path, "rb") as handle:
        blob = handle.read(SESSION_QUERY_MAX_BYTES)
    if tokens and not _prefilter_ok(blob, tokens):
        return []
    lines = blob.split(b"\n")
    if len(blob) >= SESSION_QUERY_MAX_BYTES and lines:
        lines.pop()  # 触到上限时末段多半是被截断的半行
    hits: list[SessionEventHit] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue  # 撕裂尾部/坏行：跳过，不因一行坏掉整份会话
        if not isinstance(event, Mapping):
            continue
        seq = event.get("seq")
        if not isinstance(seq, int):
            continue  # header 没有 seq
        if not filters.accepts(event, pattern):
            continue
        if len(hits) >= cap:
            break  # 上限判断必须在 append **之前**：cap=0 时不得吐出一条
        hits.append(
            SessionEventHit(
                session_id=session_id,
                seq=seq,
                time=int(event.get("time") or 0),
                type=str(event.get("type") or ""),
                snippet=snippet(event_text(event), pattern),
            )
        )
        if len(hits) >= cap:
            break
    return hits


def _tokens(query: str) -> list[bytes]:
    return [part.lower().encode("utf-8") for part in re.split(r"\s+", query.strip()) if part]


def search_session(
    kb_path: str,
    session_id: str,
    query: str,
    *,
    limit: int | None = DEFAULT_HIT_LIMIT,
    types: Sequence[str] | None = None,
    time_from: int | None = None,
    time_to: int | None = None,
    seq_from: int | None = None,
    seq_to: int | None = None,
) -> list[SessionEventHit]:
    """**会话内**检索（对应上游 `SessionEventSearchRequest`）；命中按 `seq` 升序。

    `types` 是事件类型白名单（子句内 OR）；`limit` 为单页上限（有界，见模块 docstring）。
    """
    pattern = compile_text_pattern(query)
    cap = _limit(limit, DEFAULT_HIT_LIMIT, MAX_HIT_LIMIT, name="limit")
    filters = _Filters(
        types=tuple(types) if types else None,
        time_from=time_from,
        time_to=time_to,
        seq_from=seq_from,
        seq_to=seq_to,
    )
    return _scan(session_file(kb_path, session_id), session_id, pattern, _tokens(query), filters, cap)


def search_sessions(
    kb_path: str,
    query: str,
    *,
    sessions_limit: int | None = DEFAULT_SESSION_LIMIT,
    hit_limit: int | None = DEFAULT_HIT_LIMIT,
    types: Sequence[str] | None = None,
    time_from: int | None = None,
    time_to: int | None = None,
) -> list[SessionGroupHit]:
    """**跨会话**检索（对应上游 `SessionSearchRequest`）；按会话分组。

    - 语料 = 最新的 `sessions_limit` 份会话（`list_sessions()` 已按 `modified_at` 倒序，故组间
      也是"最近聊过的先出"；上游按相关性排序，本地无评分器，已登记为偏差）；
    - 每个会话内最多取 `hit_limit` 条命中，`best` = 其中 `seq` 最小的一条；
    - `title` / `turn_count` 由 `history.summarize_session_file()` 的**原始行扫描**给出
      （不整体 `json.loads`，与 `agent_sessions_list` 同一口径）。
    """
    pattern = compile_text_pattern(query)
    scan_cap = _limit(sessions_limit, DEFAULT_SESSION_LIMIT, MAX_SESSION_LIMIT, name="sessions_limit")
    per_session = _limit(hit_limit, DEFAULT_HIT_LIMIT, MAX_HIT_LIMIT, name="hit_limit")
    filters = _Filters(types=tuple(types) if types else None, time_from=time_from, time_to=time_to)
    tokens = _tokens(query)
    out: list[SessionGroupHit] = []
    for row in list_sessions(kb_path)[:scan_cap]:
        path = str(row.get("path") or "")
        if not path:
            continue
        session_id = str(row.get("session_id") or "")
        size = int(row.get("size_bytes") or 0)
        hits = _scan(path, session_id, pattern, tokens, filters, per_session)
        if not hits:
            continue
        summary = summarize_session_file(path, size=size)
        out.append(
            SessionGroupHit(
                session_id=session_id,
                modified_at=int(row.get("modified_at") or 0),
                title=str(summary.get("title") or ""),
                turn_count=int(summary.get("turn_count") or 0),
                hit_count=len(hits),
                best=hits[0],
            )
        )
    return out
