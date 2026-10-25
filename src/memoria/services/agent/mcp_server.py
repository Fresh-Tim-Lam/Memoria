"""Memoria MCP 薄绑定（stdio / 无状态 / 零新依赖）—— 0.5.0-S3（task-122）。

## 覆盖子集（**诚实声明：本实现是 MCP 2026-07-28 的子集，不是"符合规范"**）

实现（见 `docs/design/agent-mcp-binding.md` §2 的逐项表）：

| RPC | 状态 | 依据 |
|---|---|---|
| `server/discover` | ✅ | **spec MUST**；`DiscoverResult` required：`cacheScope/capabilities/resultType/supportedVersions/ttlMs` |
| `tools/list` | ✅ | `ListToolsResult` required：`cacheScope/resultType/tools/ttlMs` |
| `tools/call` | ✅ | `CallToolResult` required：`content/resultType`；请求参数 required：`_meta/name` |
| `notifications/cancelled` | ⚠️ 只接收不处理 | stdio 绑定用它中断请求；本实现忽略（请求都很短） |
| `resources/*` / `prompts/*` / `sampling/*` / `roots/*` / `elicitation/*` | ❌ **未实现** | 不在最小集；`initialize` 时代握手同理 |
| `tasks/*` / `input_required`（MRTR） | ❌ **未实现** | 本 server 返回 `resultType:"complete"` |
| 进度通知 / 订阅 / `server/discover` 之外的列举 | ❌ **未实现** | 同上 |

**协议时代**：只支持 `2026-07-28`（无状态：无 `initialize` 握手、无协议级 session）。
版本不匹配（或缺 `_meta` 版本）⇒ `-32022 UnsupportedProtocolVersion` + 可操作提示，**不做静默降级**。

## 写安全（在进程边界复跑 W1–W4）

- **W1 入口唯一**：只暴露 `propose_write`（plan 形态）；**没有任何直写工具**；写必须带**服务端签发的 `read_handle`**
  且走 `propose_write → validate_plan → preview_plan → apply_plan(origin="agent", gate_token=…)` 唯一写者链。
- **W2 读后写**：`outline`/`section` 读成功 ⇒ 签发 `read_handle`（绑 `(kb, rel, sha256)`，`secrets` 随机、
  一次性不设但 TTL/LRU 有界）**并**记进程内观察；`snippet` **既不签发 handle 也不记观察**（片段≠看过）。
  `propose_write` 的每个 op 目标文件必须带有效 handle：缺失 ⇒ `FS_NOT_OBSERVED`；sha 变 ⇒ `FS_STALE_VERSION`；
  handle 无效/过期/被淘汰 ⇒ `WRITE_GATE_BYPASS`。
- **W3 写前备份**：`apply_plan` 内部第一步 `snapshot_pre_images`（失败 ⇒ 零写入）。
- **W4 审批在分发前**：`approvals.WRITE_CAPABILITY.require_approval("confirm")` 在**调用工具前**执行；
  外部调用若声称 `approval=auto` 且能力有写权限 ⇒ `APPROVAL_REQUIRED`（拒绝）。

## 无状态语义（协议无状态 ≠ server 无内部状态）

- 协议层：每次请求自带 `_meta`（`protocolVersion`/`clientCapabilities`），**不依赖任何握手或会话 id**；
- server 内部：`read_handle` 表与 `observation` 表都是**进程内**的；**重启 ⇒ 两表皆空 ⇒ 客户端必须重读**
  （与 `observation` 的"不跨会话存活"完全一致）。这是 spec 允许的（SEP-2567：跨调用状态用服务端签发 handle）。
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "PROTOCOL_VERSION",
    "SERVER_NAME",
    "HandleStore",
    "McpServer",
    "main",
]

#: 只支持这一个协议时代（无状态）。见模块头"覆盖子集"。
PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_VERSIONS: tuple[str, ...] = (PROTOCOL_VERSION,)
SERVER_NAME = "memoria-agent"
SERVER_VERSION = "0.5.0-s3"

#: MCP 结果里的缓存提示（`ListToolsResult` / `DiscoverResult` **required**）。
CACHE_SCOPE = "private"
TOOLS_TTL_MS = 300_000  # 工具面稳定 5 分钟
DISCOVER_TTL_MS = 300_000

#: JSON-RPC / MCP 稳定错误码（-32020..-32099 由 spec 保留；本轮 `-32004 → -32022`）。
E_PARSE = -32700
E_INVALID_REQUEST = -32600
E_METHOD_NOT_FOUND = -32601
E_INVALID_PARAMS = -32602
E_UNSUPPORTED_PROTOCOL_VERSION = -32022

#: 请求 `_meta` 的键（spec：全部元数据走消息体）。
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPS = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

#: 进程内固定的观察 owner（stdio transport 由客户端 spawn，进程生命周期 ≈ 客户端会话）。
MCP_SESSION = "mcp-stdio"

#: `read_handle` 的 TTL 与容量上限（R-S3：无界表会泄漏；淘汰后再用必须**响亮失败**）。
HANDLE_TTL_S = 1800
HANDLE_MAX = 1024


@dataclass(frozen=True, slots=True)
class _Handle:
    kb_path: str
    rel_path: str
    sha256: str
    expires_at: float


class HandleStore:
    """`read_handle` 表：`secrets` 随机 token → (kb, rel, sha)，**TTL + LRU 有界**。

    - token 用 `secrets.token_urlsafe(32)`（**不可猜测**；同一文件读两次得到不同 handle）；
    - 超过 `max_entries` ⇒ 淘汰**最久未用**的一条；淘汰/过期后再用 ⇒ `WRITE_GATE_BYPASS`（不静默）。
    """

    def __init__(self, *, ttl_s: float = HANDLE_TTL_S, max_entries: int = HANDLE_MAX) -> None:
        self._ttl = float(ttl_s)
        self._max = int(max_entries)
        self._items: OrderedDict[str, _Handle] = OrderedDict()

    def mint(self, kb_path: str, rel_path: str, sha256: str) -> str:
        self._evict()
        token = f"rh-{secrets.token_urlsafe(32)}"
        self._items[token] = _Handle(
            kb_path=os.path.abspath(kb_path),
            rel_path=str(rel_path),
            sha256=str(sha256),
            expires_at=time.time() + self._ttl,
        )
        while len(self._items) > self._max:
            self._items.popitem(last=False)  # LRU 淘汰最旧
        return token

    def lookup(self, token: str) -> _Handle | None:
        self._evict()
        item = self._items.get(str(token or ""))
        if item is None:
            return None
        self._items.move_to_end(str(token))  # 命中即刷新 LRU
        return item

    def _evict(self) -> None:
        now = time.time()
        for token in [k for k, v in self._items.items() if v.expires_at <= now]:
            self._items.pop(token, None)

    def __len__(self) -> int:
        self._evict()
        return len(self._items)


# ── 工具面（4 把；schema 目标 ≤1,450 tok）────────────────────────────────────
def _tool_specs() -> list[dict]:
    file_arg = {"type": "string", "description": "库内相对路径（.md）"}
    return [
        {
            "name": "outline",
            "description": "看一篇 md 的标题树（标题+行号区间+行数），不读正文。返回 read_handle 供后续写入。",
            "inputSchema": {
                "type": "object",
                "properties": {"file": file_arg},
                "required": ["file"],
                "additionalProperties": False,
            },
        },
        {
            "name": "section",
            "description": "按标题或行号取一节正文（含标题行）。同名多候选必须给 path/near_line，否则报歧义。返回 read_handle。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file": file_arg,
                    "heading": {"type": "string"},
                    "line": {"type": "integer", "minimum": 1},
                    "near_line": {"type": "integer", "minimum": 1},
                    "path": {"type": "array", "items": {"type": "string"}},
                    "part": {"type": "integer", "minimum": 1},
                },
                "required": ["file"],
                "additionalProperties": False,
            },
        },
        {
            "name": "snippet",
            "description": "按关键词找命中行，回命中行 ±N 行窗口（最多 5 窗）。片段不算读过该文件（不返回 read_handle）。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file": file_arg,
                    "query": {"type": "string"},
                    "line": {"type": "integer", "minimum": 1},
                    "ctx_lines": {"type": "integer", "minimum": 0, "maximum": 20},
                },
                "required": ["file"],
                "additionalProperties": False,
            },
        },
        {
            "name": "propose_write",
            "description": (
                "按计划写库（唯一写入口；无直写工具）。ops 见 plan 动词表；每个目标文件必须带读时拿到的 "
                "read_handle。返回 txid/files/lines_changed/undo_available/preview。"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "description": "人话一句，用于审计"},
                    "ops": {"type": "array", "items": {"type": "object"}},
                    "handles": {
                        "type": "object",
                        "description": "rel_path → read_handle（每个被写文件一个）",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["intent", "ops", "handles"],
                "additionalProperties": False,
            },
        },
    ]


def _safe_rel(kb_path: str, path: str) -> str | None:
    """库内相对路径校验（不上跳 / 不绝对 / 必须 .md）。"""
    raw = str(path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or os.path.isabs(raw):
        return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    rel = "/".join(parts)
    if not rel.lower().endswith((".md", ".markdown")):
        return None
    full = os.path.abspath(os.path.join(kb_path, rel))
    if os.path.commonpath([full, os.path.abspath(kb_path)]) != os.path.abspath(kb_path):
        return None
    return rel


def _read_body(kb_path: str, rel: str) -> tuple[str, list[str]]:
    from memoria.storage.markdown import strip_frontmatter

    with open(os.path.join(kb_path, rel), encoding="utf-8") as fh:
        raw = fh.read()
    body, _ = strip_frontmatter(raw)
    return body, body.splitlines()


def _sha(path: str) -> str:
    import hashlib

    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class McpServer:
    """一个绑到某知识库的 MCP server（stdio）。`handle_message()` 可直接单测，不必起进程。"""

    def __init__(self, kb_path: str, *, handle_store: HandleStore | None = None) -> None:
        self.kb_path = os.path.abspath(kb_path)
        self.handles = handle_store or HandleStore()
        # 注意：**没有** txid 计数器 —— txid 由 `tools/kb.py::_next_txid` 扫盘生成（唯一实现，
        # 见 `_next_txid()` 的 docstring：这里曾经有过第二份内存实现，导致重启后撞批次 flaky）。

    # ── JSON-RPC 入口 ──
    def handle_message(self, message: Any) -> dict | None:
        if not isinstance(message, Mapping):
            return self._error(None, E_INVALID_REQUEST, "消息必须是 JSON-RPC 对象")
        method = str(message.get("method") or "")
        req_id = message.get("id")
        is_notification = req_id is None
        if not method:
            return None if is_notification else self._error(req_id, E_INVALID_REQUEST, "缺 method")
        params = message.get("params") if isinstance(message.get("params"), Mapping) else {}

        # 版本校验（spec：每个请求在 _meta 里带版本；缺失/不匹配 ⇒ -32022，不做静默降级）
        meta = params.get("_meta") if isinstance(params.get("_meta"), Mapping) else {}
        version_error = self._check_version(meta)
        if version_error is not None and method != "server/discover":
            return None if is_notification else self._error(req_id, E_UNSUPPORTED_PROTOCOL_VERSION, version_error)

        if method == "server/discover":
            return None if is_notification else self._ok(req_id, self._discover_result())
        if method == "tools/list":
            return None if is_notification else self._ok(req_id, self._list_tools_result())
        if method == "tools/call":
            return None if is_notification else self._tools_call(req_id, params)
        if method in ("notifications/cancelled", "notifications/initialized"):
            return None  # 只接收不处理（本 server 请求都很短）
        if is_notification:
            return None
        return self._error(req_id, E_METHOD_NOT_FOUND, f"未实现的方法：{method}（本 server 只实现 discover/tools.list/tools.call）")

    # ── 结果构造 ──
    def _check_version(self, meta: Mapping) -> str | None:
        claimed = str(meta.get(META_VERSION) or "").strip()
        if not claimed:
            return (
                f"缺 `_meta.{META_VERSION}` —— 本 server 只支持无状态时代 {PROTOCOL_VERSION}；"
                "请在每次请求里带上该字段（不要走 initialize 握手）"
            )
        if claimed not in SUPPORTED_VERSIONS:
            return (
                f"不支持的协议版本：{claimed!r}（本 server 支持：{', '.join(SUPPORTED_VERSIONS)}）。"
                "本 server 不提供 2025-11-25 的 initialize 回退（避免静默降级）"
            )
        return None

    def _meta(self) -> dict:
        return {META_SERVER_INFO: {"name": SERVER_NAME, "version": SERVER_VERSION}}

    def _ok(self, req_id: Any, result: Mapping) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": dict(result)}

    def _error(self, req_id: Any, code: int, message: str, data: Any = None) -> dict:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": err}

    def _discover_result(self) -> dict:
        return {
            "cacheScope": CACHE_SCOPE,
            "capabilities": {"tools": {}},
            "resultType": "complete",
            "supportedVersions": list(SUPPORTED_VERSIONS),
            "ttlMs": DISCOVER_TTL_MS,
            "instructions": (
                "Memoria 知识库的只读粒度工具 + plan 形态写入。读: outline/section/snippet；"
                "写: propose_write（必须带读时拿到的 read_handle）。"
            ),
            "_meta": self._meta(),
        }

    def _list_tools_result(self) -> dict:
        return {
            "cacheScope": CACHE_SCOPE,
            "resultType": "complete",
            "tools": _tool_specs(),
            "ttlMs": TOOLS_TTL_MS,
            "_meta": self._meta(),
        }

    def _tools_call(self, req_id: Any, params: Mapping) -> dict:
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") if isinstance(params.get("arguments"), Mapping) else {}
        handlers = {
            "outline": self._tool_outline,
            "section": self._tool_section,
            "snippet": self._tool_snippet,
            "propose_write": self._tool_propose_write,
        }
        handler = handlers.get(name)
        if handler is None:
            return self._error(req_id, E_INVALID_PARAMS, f"未知工具：{name!r}（可用：{', '.join(handlers)}）")
        try:
            text, structured, is_error = handler(arguments)
        except _ToolFailure as exc:
            return self._ok(
                req_id,
                {
                    "content": [{"type": "text", "text": f"{exc.code}: {exc.message}"}],
                    "resultType": "complete",
                    "isError": True,
                    "_meta": self._meta(),
                },
            )
        result: dict[str, Any] = {
            "content": [{"type": "text", "text": text}],
            "resultType": "complete",
            "_meta": self._meta(),
        }
        if structured is not None:
            result["structuredContent"] = structured
        if is_error:
            result["isError"] = True
        return self._ok(req_id, result)

    # ── 工具实现 ──
    def _observe(self, rel: str, sha: str) -> None:
        """读成功即记一次进程内观察（供 `observation.issue_clearance` 用）。"""
        from memoria.services.agent import observation

        observation.record_read(self.kb_path, MCP_SESSION, rel, present=True, version=sha)

    def _tool_outline(self, args: Mapping) -> tuple[str, dict | None, bool]:
        from memoria.services.agent import section_index as si

        rel = _safe_rel(self.kb_path, str(args.get("file") or ""))
        if rel is None or not os.path.isfile(os.path.join(self.kb_path, rel)):
            raise _ToolFailure("NOT_FOUND", f"文档不存在或路径非法：{args.get('file')!r}")
        body, _lines = _read_body(self.kb_path, rel)
        payload = si.build_outline(body)
        sha = _sha(os.path.join(self.kb_path, rel))
        self._observe(rel, sha)
        token = self.handles.mint(self.kb_path, rel, sha)
        rows = [
            f"{'  ' * (n['level'] - 1)}{n['title']}  (L{n['line_no']}-{n['end_line_no']}，{n['lines']} 行)"
            # R-S1B-5 / task-132：同名标题带 `preview` —— MCP 文本同样是模型的唯一可见通道，
            # 这里过去只拼标题+行号 ⇒ 同名节在跨进程路径上仍只能猜（与 tools/kb.py 同源修复）。
            + (f"  ∥ {n['preview']}" if n.get("preview") else "")
            for n in payload.get("headings") or []
        ]
        text = "\n".join([f"文档 {rel}：{payload.get('count', 0)} 个标题", *rows, f"read_handle: {token}"])
        return text, {"kind": "outline", "file": rel, "read_handle": token, "count": payload.get("count", 0)}, False

    def _tool_section(self, args: Mapping) -> tuple[str, dict | None, bool]:
        from memoria.services.agent import section_index as si

        rel = _safe_rel(self.kb_path, str(args.get("file") or ""))
        if rel is None or not os.path.isfile(os.path.join(self.kb_path, rel)):
            raise _ToolFailure("NOT_FOUND", f"文档不存在或路径非法：{args.get('file')!r}")
        body, _lines = _read_body(self.kb_path, rel)
        selector: dict[str, Any] = {}
        if args.get("heading"):
            selector["heading"] = str(args["heading"])
        for key in ("line", "near_line", "part"):
            if args.get(key) is not None:
                selector[key] = int(args[key])
        if args.get("path"):
            selector["path"] = args["path"]
        payload = si.get_section(body, **selector) if not selector.get("part") else si.get_section_part(
            body, part=int(selector.pop("part")), **selector
        )
        if not payload.get("ok"):
            code = str(payload.get("code") or "SECTION_NOT_FOUND")
            msg = str(payload.get("message") or "无法定位该节")
            cands = payload.get("candidates") or []
            if cands:
                # R-S1B-5 / task-132：候选必须带 `preview`（正文首行）—— **这是 MCP 路径的
                # 第二个消费者**，过去只拼 `L行号`（连父级都丢了）⇒ 模型拿不到消歧信息。
                lines_ = ["；候选（按 preview 辨认目标）："]
                for c in cands:
                    preview = str(c.get("preview") or "").strip()
                    parent = "/".join(c.get("parent_path") or []) or "根"
                    lines_.append(
                        f"  - L{c['line_no']} h{c.get('level')} [{parent}] {preview or '（空节）'}"
                    )
                if payload.get("candidates_truncated"):
                    lines_.append(
                        f"  …共 {payload.get('candidate_count', len(cands))} 个候选，"
                        f"其余 {payload.get('omitted_count', 0)} 个未列出"
                    )
                how = str(payload.get("how_to_disambiguate") or "").strip()
                if how:
                    lines_.append(how)
                msg += "\n" + "\n".join(lines_)
            raise _ToolFailure(code, msg)
        sec = payload.get("section") or {}
        sha = _sha(os.path.join(self.kb_path, rel))
        self._observe(rel, sha)
        token = self.handles.mint(self.kb_path, rel, sha)
        head = f"{rel} 「{sec.get('title')}」(L{sec.get('line_no')}-{sec.get('end_line_no')})"
        text = "\n".join([head, "", str(payload.get("text") or ""), f"read_handle: {token}"])
        return text, {"kind": "section", "file": rel, "read_handle": token, "section": sec}, False

    def _tool_snippet(self, args: Mapping) -> tuple[str, dict | None, bool]:
        from memoria.services.agent import section_index as si

        rel = _safe_rel(self.kb_path, str(args.get("file") or ""))
        if rel is None or not os.path.isfile(os.path.join(self.kb_path, rel)):
            raise _ToolFailure("NOT_FOUND", f"文档不存在或路径非法：{args.get('file')!r}")
        body, _lines = _read_body(self.kb_path, rel)
        payload = si.get_snippet(
            body,
            query=str(args["query"]) if args.get("query") else None,
            line=int(args["line"]) if args.get("line") is not None else None,
            ctx_lines=int(args["ctx_lines"]) if args.get("ctx_lines") is not None else si.SNIPPET_DEFAULT_CTX_LINES,
        )
        if not payload.get("ok"):
            raise _ToolFailure(str(payload.get("code") or "UNSUPPORTED"), str(payload.get("message") or "参数不足"))
        # **不签发 handle、不记观察**（片段 ≠ 看过这个文件；见 R-S2-1 裁定）。
        wins = payload.get("windows") or []
        if not wins:
            return f"{rel}：0 命中", {"kind": "snippet", "file": rel, "read_handle": None, "matches": 0}, False
        parts = [f"{rel}：{payload.get('match_count')} 处命中（展示 {payload.get('shown')} 个窗口）"]
        for w in wins:
            parts.append(f"--- L{w['start_line_no']}-{w['end_line_no']} ---")
            parts.append(str(w.get("text") or ""))
        parts.append("（片段不构成'读过该文件'：要写请先用 outline/section 读）")
        return "\n".join(parts), {"kind": "snippet", "file": rel, "read_handle": None, "matches": payload.get("match_count")}, False

    def _next_txid(self) -> str:
        """**必须复用 `tools/kb.py::_next_txid`，不许在这里再写一份**（2026-10-25 教训）。

        我第一版在这里写了"内存自增 `-01`"的第二份实现 ⇒ 与 `kb.py` 的**扫盘**实现分叉：
        重启后 `_tx_seq` 归零 ⇒ 同一秒内生成已被占用的 txid ⇒ `backup_failed（批次已存在）`
        ⇒ `mcp_binding.py` 变成 flaky（6 次跑 3 红 3 绿）。
        `kb.py` 那份的 docstring 早在 2026-09-22 就写明了为什么必须扫盘；这里只做**唯一一份**。
        """
        from memoria.services.agent.tools.kb import _next_txid as _kb_next_txid

        return _kb_next_txid(self.kb_path, MCP_SESSION, time.gmtime())

    def _tool_propose_write(self, args: Mapping) -> tuple[str, dict | None, bool]:
        from memoria.services.agent import observation
        from memoria.services.agent.apply import apply_plan
        from memoria.services.agent.plan import preview_plan, validate_plan

        intent = str(args.get("intent") or "").strip()
        ops = [row for row in (args.get("ops") or []) if isinstance(row, Mapping)]
        handles = args.get("handles") if isinstance(args.get("handles"), Mapping) else {}
        if not ops:
            raise _ToolFailure("INVALID_PLAN", "ops 必须是非空数组")

        # W2：每个被写文件必须带**有效 read_handle**（缺 ⇒ FS_NOT_OBSERVED；sha 变 ⇒ FS_STALE_VERSION）
        for row in ops:
            rel = _safe_rel(self.kb_path, str(row.get("file") or ""))
            if rel is None:
                raise _ToolFailure("INVALID_PLAN", f"op 目标路径非法：{row.get('file')!r}")
            token = str(handles.get(rel) or "").strip()
            if not token:
                raise _ToolFailure(
                    observation.CODE_NOT_OBSERVED,
                    f"没读过 {rel} —— 请先用 outline/section 读它、拿到 read_handle，再带上 handles={{'{rel}': handle}}",
                )
            item = self.handles.lookup(token)
            if item is None:
                raise _ToolFailure(
                    observation.CODE_GATE_BYPASS,
                    f"{rel} 的 read_handle 无效/已过期/已被淘汰 —— 请重新 outline/section 读一遍",
                )
            if item.rel_path != rel or item.kb_path != self.kb_path:
                raise _ToolFailure(observation.CODE_GATE_BYPASS, f"read_handle 与目标文件不匹配：{rel}")
            now_sha = _sha(os.path.join(self.kb_path, rel))
            if now_sha != item.sha256:
                raise _ToolFailure(
                    observation.CODE_STALE_VERSION,
                    f"{rel} 在你读过之后又被改过了 —— 请重新读一遍再提",
                )

        # W4：核心写能力必须 confirm 及以上（外部不得 auto）
        from memoria.services.agent import approvals

        try:
            approvals.WRITE_CAPABILITY.require_approval(str(args.get("approval") or "confirm"))
        except approvals.ContractViolation as exc:
            raise _ToolFailure(exc.code, exc.message) from exc

        plan = {"v": 1, "txid": self._next_txid(), "intent": intent, "ops": ops}
        checked = validate_plan(self.kb_path, plan)
        if checked.get("status") != "ok":
            first = (checked.get("errors") or [{}])[0]
            raise _ToolFailure("INVALID_PLAN", f"{first.get('code')}: {first.get('message')}")
        preview = preview_plan(self.kb_path, plan)

        # W1：过 W2 闸 ⇒ 签发一次性令牌 ⇒ 唯一写者链（origin=agent）
        token = observation.issue_clearance(self.kb_path, MCP_SESSION, ops)
        if token is None:
            code, message = observation.gate_ops(self.kb_path, MCP_SESSION, ops) or (
                observation.CODE_NOT_OBSERVED,
                "读后写闸未放行",
            )
            raise _ToolFailure(code, message)
        result = apply_plan(
            self.kb_path,
            plan,
            session_id=MCP_SESSION,
            txid=plan["txid"],
            base_versions=preview.get("base_versions"),
            auto=True,
            origin="agent",
            gate_token=token,
        )
        if result.get("status") != "ok":
            raise _ToolFailure(str(result.get("code") or "WRITE_FAILED"), str(result.get("message") or "写入失败"))

        files = [row for row in (preview.get("files") or []) if isinstance(row, Mapping)]
        lines_changed = sum(len(row.get("lines_changed") or []) for row in files)
        # ⑦ 回执必须含 preview（跨进程客户端要靠它给人看）
        diff_rows = [
            {"file": row.get("file"), "lines_changed": row.get("lines_changed") or [],
             "diff": (row.get("ops") or [{}])[0].get("diff") or []}
            for row in files
        ][:5]
        structured = {
            "kind": "write",
            "txid": plan["txid"],
            "files": [str(row.get("file") or "") for row in files],
            "lines_changed": lines_changed,
            "undo_available": True,
            "preview": diff_rows,
        }
        text = "\n".join(
            [
                f"已写入 {plan['txid']}：{len(structured['files'])} 个文件，{lines_changed} 行",
                f"files: {', '.join(structured['files'])}",
                f"undo: 可撤销（txid={plan['txid']}）",
                "preview:",
                json.dumps(diff_rows, ensure_ascii=False)[:1500],
            ]
        )
        return text, structured, False


class _ToolFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def serve(kb_path: str, *, stdin=None, stdout=None) -> int:
    """stdio 主循环：newline-delimited JSON-RPC 2.0；日志一律走 stderr。"""
    fin = stdin or sys.stdin
    fout = stdout or sys.stdout
    server = McpServer(kb_path)
    print(f"[mcp] {SERVER_NAME} {SERVER_VERSION} 已启动，kb={kb_path}，版本={PROTOCOL_VERSION}", file=sys.stderr)
    for line in fin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": E_PARSE, "message": f"解析失败：{exc}"}}
        else:
            reply = server.handle_message(message)
        if reply is None:
            continue
        fout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        fout.flush()
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Memoria MCP 薄绑定（stdio，MCP 2026-07-28 子集）")
    ap.add_argument("--kb", required=True, help="知识库根目录")
    args = ap.parse_args(list(argv) if argv is not None else None)
    if not os.path.isdir(args.kb):
        print(f"[mcp] 知识库不存在：{args.kb}", file=sys.stderr)
        return 2
    return serve(args.kb)


if __name__ == "__main__":
    raise SystemExit(main())
