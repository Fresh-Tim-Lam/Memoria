# 语义移植自 deepseek-harness packages/core/tools（工具定义与错误语义）、
# packages/context/agent-instructions（指令文件发现，见 prompt.py）、
# packages/session-query/tool-session-query（会话检索工具）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""只读知识库工具：检索 / 读文档 / 读知识点 / 库概览 / 校验 / 检索历史会话。

六个知识库工具全部**复用 Memoria 既有服务层**（不重写检索、不另立索引）；另三个读面工具（`glob`/`grep`/`read_image`）见文件末尾「上游读面」块（2026-09-20，§6.16）：

| 工具 | 复用 |
|---|---|
| `search_kb` | `services/search_kernel.search()`（lexical 通道）+ `kp_index.build_kp_index()` 补行号锚点 |
| `read_document` | `services/kp_resolver.resolve_knowledge_points()` + `storage.sidecar` |
| `read_kp` | `services/kp_index.py` + 正文切片 |
| `kb_overview` | `storage.scanner.collect_md_files()` + sidecar 摘要 |
| `validate_kb` | `services/document.DocumentService.validate_kb()`（内部经 `check_report.summarize_check_counts`） |
| 会话查询家族（`search_sessions` 等 **5** 个） | `services/agent/session/query.py`（**对话记录**而非知识库文档，故不产生 `文件:行号` 锚点）；其余四个见文件末尾「会话查询家族」块（2026-09-20，§6.17） |

两处必须说明的实现取舍：

1. **零写入守卫**（`kb_read_only`）。Memoria 的检索/校验链路会顺带维护**可再生
   缓存**与 manifest 基线：`lexical_tokenizer.configure_jieba_cache` 建
   `.memoria/cache/lexical/jieba/`、`lexical_index.save_lexical_index` 写
   `.memoria/cache/lexical/index.json`、`search_aux.rebuild_search_aux` 写
   `.memoria/cache/search_aux/**`、`manifest.save_manifest` 可能建
   `manifest.yaml`。M1 的工具面**只读**，因此在调用期间把这些写点重定向到进程
   临时目录（或抑制），使知识库正文与元数据逐字节不变。这也保证「知识库零写入」
   不依赖「缓存恰好已存在」这一偶然条件。
2. **不构造 `DocumentService(kb_path=...)`**：其 `__post_init__` 会做
   `ensure_manifest_baseline` / `sync_kb_pending` / kp_targets 重建等写库引导。
   `validate_kb` 工具用「先按无库构造，再直接赋 `kb_path`」的只读实例，绕开引导。

导入本模块不联网、不读知识库；工具体在调用时才导入具体服务。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from memoria.services.agent.tools.registry import (
    INVALID_ARGUMENTS_CODE,
    Tool,
    ToolOutput,
    error_text,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_TOP_K",
    "KB_TOOL_NAMES",
    "build_kb_tools",
    "kb_read_only",
]

DEFAULT_TOP_K = 5
#: 单次 `read_document` 返回的正文字符上限（工具结果的硬边界，上游同样对结果设界）。
MAX_BODY_CHARS = 20_000
#: 锚点片段取 KP 起始行起的行数。
SNIPPET_LINES = 3
SNIPPET_CHARS = 240
MAX_FILES_IN_OVERVIEW = 200
MAX_ISSUES_IN_REPORT = 20

KB_TOOL_NAMES = (
    "search_kb", "read_document", "read_kp", "kb_overview",
    "validate_kb", "search_sessions",
    "glob", "grep", "read_image",
    "session_event_search", "session_trace", "session_event_trace", "session_event_read",
    "resolve_reference",
    "audit_references", "propose_write",
)

#: `search_sessions` 默认 / 最多列出多少个历史会话。
DEFAULT_SESSION_HITS = 5
MAX_SESSION_HITS = 20

_SCRATCH_DIRS: dict[str, str] = {}


def _scratch_dir(kb_path: str) -> str:
    """每个（进程, 知识库）一个临时目录，用于承接被重定向的可再生缓存。"""
    key = os.path.normcase(os.path.abspath(kb_path))
    existing = _SCRATCH_DIRS.get(key)
    if existing is not None:
        return existing
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    path = os.path.join(tempfile.gettempdir(), f"memoria-agent-readonly-{os.getpid()}-{digest}")
    os.makedirs(path, exist_ok=True)
    _SCRATCH_DIRS[key] = path
    return path


@contextlib.contextmanager
def kb_read_only(kb_path: str) -> Iterator[str]:
    """在只读工具调用期间屏蔽知识库写入（重定向缓存、抑制 manifest 落盘）。

    重定向的写点与理由：

    - `lexical_tokenizer.configure_jieba_cache`：jieba 缓存目录建在库内；
    - `lexical_index.lexical_cache_path`：词法索引缓存；
    - `search_aux.search_aux_dir`：隐式检索 aux 缓存；
    - `manifest.save_manifest`：首次打开时可能新建 `manifest.yaml` 基线
      （`audit_manifest_diff` 的基线段无论如何都返回"已建基线"摘要，故抑制
      落盘不改变可观察结果，只是不再往库里写文件）。

    退出时逐项还原，异常路径同样还原。
    """
    from memoria.services import lexical_index, lexical_tokenizer, search_aux
    from memoria.storage import manifest

    scratch = _scratch_dir(kb_path)
    previous_env = os.environ.get("JIEBA_CACHE_DIR")

    def _jieba_cache_dir(_kb: str | None = None) -> None:
        cache_dir = os.path.join(scratch, "lexical", "jieba")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["JIEBA_CACHE_DIR"] = cache_dir

    def _lexical_cache_path(_kb: str) -> str:
        return os.path.join(scratch, "lexical", "index.json")

    def _aux_dir(_kb: str) -> str:
        return os.path.join(scratch, "search_aux")

    def _discard_manifest(_kb: str, _entries: Mapping[str, Any]) -> None:
        return None

    patches: tuple[tuple[Any, str, Any], ...] = (
        (lexical_tokenizer, "configure_jieba_cache", _jieba_cache_dir),
        (lexical_index, "lexical_cache_path", _lexical_cache_path),
        (search_aux, "search_aux_dir", _aux_dir),
        (manifest, "save_manifest", _discard_manifest),
    )
    originals = [(module, attr, getattr(module, attr)) for module, attr, _ in patches]
    for module, attr, replacement in patches:
        setattr(module, attr, replacement)
    try:
        yield scratch
    finally:
        for module, attr, original in originals:
            setattr(module, attr, original)
        if previous_env is None:
            os.environ.pop("JIEBA_CACHE_DIR", None)
        else:
            os.environ["JIEBA_CACHE_DIR"] = previous_env


# —— 正文读取（只读，不走 DocumentService 的写库引导）——


def _safe_rel(kb_path: str, path: str) -> str | None:
    """校验并归一化工作区内相对路径（走允许根列表）；越界或非 .md 返回 None。"""
    rel = (path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or not rel.lower().endswith(".md"):
        return None
    resolved = _resolve_in_read_roots(_read_roots(kb_path), rel)
    if resolved is None:
        return None
    norm = resolved[1]
    # `..` / 绝对路径 / 允许根之外都在 `_resolve_in_read_roots()` 内拒：这里只回「相对根」的路径
    if norm == ".." or norm.startswith("../"):  # 冗余守卫：与旧实现同一口径（防解析器被放宽）
        return None
    return norm


def _read_body_lines(kb_path: str, rel: str) -> tuple[str, list[str]]:
    from memoria.storage.markdown import strip_frontmatter

    full = os.path.join(kb_path, rel)
    with open(full, "r", encoding="utf-8") as handle:
        body, _ = strip_frontmatter(handle.read())
    return body, body.splitlines() or [""]


def _snippet(lines: Sequence[str], line: int | None) -> str:
    if not line or line < 1 or line > len(lines):
        return ""
    chunk = " / ".join(part.strip() for part in lines[line - 1 : line - 1 + SNIPPET_LINES] if part.strip())
    return chunk[:SNIPPET_CHARS]


def _line_hint(kp: Mapping[str, Any]) -> int | None:
    hint = ((kp.get("range") or {}).get("start") or {}).get("line_hint")
    try:
        value = int(hint)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _kp_map_for_file(kb_path: str, rel: str) -> dict[str, dict[str, Any]]:
    """该文件的 `{kp_id: {name, line, snippet}}`（行号优先取 range 解析结果）。"""
    from memoria.services.kp_resolver import resolve_knowledge_points
    from memoria.storage.sidecar import load_sidecar_for_md

    body, lines = _read_body_lines(kb_path, rel)
    sidecar = load_sidecar_for_md(os.path.join(kb_path, rel), kb_path)
    out: dict[str, dict[str, Any]] = {}
    for kp in resolve_knowledge_points(body, sidecar):
        kp_id = str(kp.get("id") or "")
        if not kp_id:
            continue
        resolved = kp.get("range_resolved") or {}
        line = resolved.get("start_line") if resolved.get("ok") else None
        if not line:
            line = _line_hint(kp)
        out[kp_id] = {
            "name": kp.get("name") or kp_id,
            "line": line,
            "snippet": _snippet(lines, line),
        }
    return out


def _error(message: str, code: str = INVALID_ARGUMENTS_CODE) -> ToolOutput:
    return ToolOutput(text=error_text(message, code), error=True, code=code)


# —— 工具实现 ——


def _search_kb(kb_path: str, query: str, top_k: int) -> ToolOutput:
    text = (query or "").strip()
    if not text:
        return _error("search_kb: query 不能为空")
    from memoria.services.search_kernel import search

    with kb_read_only(kb_path):
        payload = search(text, kb_path=kb_path, scope="kb", modes="lexical", limit=top_k)

    if not payload.get("available", True):
        return _error(
            f"search_kb: 检索不可用（{payload.get('reason') or payload.get('message') or '未知原因'}）",
            "SEARCH_UNAVAILABLE",
        )

    hits = list(payload.get("results") or [])
    if not hits:
        return ToolOutput(
            text=(
                f"未在知识库中检索到与 {text!r} 匹配的内容"
                f"（lexical 通道，库内 {payload.get('index_records', 0)} 条 KP 记录）。"
            )
        )

    by_file: dict[str, dict[str, dict[str, Any]]] = {}
    rows: list[str] = []
    anchors: list[dict[str, Any]] = []
    for index, hit in enumerate(hits, start=1):
        rel = str(hit.get("file") or "")
        kp_id = str(hit.get("kp_id") or "")
        info = by_file.setdefault(rel, _kp_map_for_file(kb_path, rel)).get(kp_id, {})
        line = info.get("line")
        name = hit.get("name") or info.get("name") or kp_id
        snippet = info.get("snippet") or ""
        location = f"{rel}:{line}" if line else rel
        rows.append(f"{index}. {location}  {name}（score={hit.get('score')}）")
        if snippet:
            rows.append(f"   {snippet}")
        anchors.append(
            {
                "file": rel,
                "line": line,
                "kp_id": kp_id,
                "name": name,
                "snippet": snippet,
                "score": hit.get("score"),
            }
        )
    head = f"检索 {text!r}：命中 {len(hits)} 条（lexical）。引用来源请写成 `文件:行号`。"
    return ToolOutput(text="\n".join([head, *rows]), anchors=tuple(anchors))


def _read_document(kb_path: str, path: str, *, offset: int = 1, limit: int | None = None) -> ToolOutput:
    rel = _safe_rel(kb_path, path)
    if rel is None:
        return _error("read_document: path 必须是工作区（允许根）内的相对 .md 路径（不得上跳）")
    full = os.path.join(kb_path, rel)
    if not os.path.isfile(full):
        return _error(f"read_document: 文档不存在：{rel}", "NOT_FOUND")

    from memoria.services.kp_resolver import resolve_knowledge_points
    from memoria.storage.sidecar import load_sidecar_for_md

    body, lines = _read_body_lines(kb_path, rel)
    sidecar = load_sidecar_for_md(full, kb_path)
    kps = resolve_knowledge_points(body, sidecar)

    kp_rows: list[str] = []
    anchors: list[dict[str, Any]] = []
    for kp in kps:
        kp_id = str(kp.get("id") or "")
        resolved = kp.get("range_resolved") or {}
        line = resolved.get("start_line") if resolved.get("ok") else None
        if not line:
            line = _line_hint(kp)
        name = kp.get("name") or kp_id
        location = f"{rel}:{line}" if line else rel
        kp_rows.append(f"- {location}  {name}")
        anchors.append({"file": rel, "line": line, "kp_id": kp_id, "name": name, "snippet": _snippet(lines, line)})

    window, footer = _read_window(lines, offset=offset, limit=limit, display=rel, body=body)
    parts = [
        f"文档 {rel}：共 {len(lines)} 行，{len(kps)} 个知识点。",
        "",
        "知识点（`文件:行号`）：",
        *(kp_rows or ["- （该文档没有 sidecar 知识点）"]),
        "",
        "正文：",
        window,
    ]
    if footer:
        parts.append(footer)

    return ToolOutput(text="\n".join(parts), anchors=tuple(anchors))


def _read_kp(kb_path: str, kp_id: str) -> ToolOutput:
    key = (kp_id or "").strip()
    if not key:
        return _error("read_kp: id 不能为空")
    from memoria.services.kp_index import build_kp_index
    from memoria.storage.sidecar import load_sidecar_for_md

    entries = build_kp_index(kb_path)["by_id"].get(key) or []
    if not entries:
        return _error(f"read_kp: 知识库中不存在知识点 {key!r}", "NOT_FOUND")
    entry = entries[0]
    body_lines = _read_body_lines(kb_path, entry.file)[1]
    start = entry.start_line or 1
    end = entry.end_line or start
    excerpt = body_lines[start - 1 : end]
    sidecar = load_sidecar_for_md(os.path.join(kb_path, entry.file), kb_path) or {}
    detail = next(
        (kp for kp in (sidecar.get("knowledge_points") or []) if isinstance(kp, dict) and kp.get("id") == key),
        {},
    )
    meta: list[str] = []
    if detail.get("tags"):
        meta.append(f"tags: {', '.join(str(t) for t in detail['tags'])}")
    if detail.get("aliases"):
        meta.append(f"aliases: {', '.join(str(a) for a in detail['aliases'])}")
    if detail.get("description"):
        meta.append(f"description: {detail['description']}")
    header = f"知识点 {key}（{entry.name}）@ {entry.file}:{start}-{end}"
    parts = [header]
    if meta:
        parts.append(" / ".join(meta))
    parts.extend(["", *excerpt])
    text = "\n".join(parts)
    anchor = {
        "file": entry.file,
        "line": start,
        "kp_id": key,
        "name": entry.name,
        "snippet": _snippet(body_lines, start),
    }
    return ToolOutput(text=text, anchors=(anchor,))


def _kb_overview(kb_path: str) -> ToolOutput:
    from memoria.storage.scanner import collect_md_files
    from memoria.storage.sidecar import load_sidecar_for_md

    files = collect_md_files(kb_path)
    rows: list[str] = []
    total_kps = 0
    for rel in files[:MAX_FILES_IN_OVERVIEW]:
        sidecar = load_sidecar_for_md(os.path.join(kb_path, rel), kb_path) or {}
        kp_count = len([kp for kp in (sidecar.get("knowledge_points") or []) if isinstance(kp, dict)])
        total_kps += kp_count
        description = str(sidecar.get("description") or "").strip()
        rows.append(f"- {rel}（KP {kp_count}）{(' — ' + description) if description else ''}")

    instruction_files = [
        name
        for name in ("kb-spec.zh-CN.md", "preview-formats.md", "prompt.zh-CN.md")
        if os.path.isfile(os.path.join(kb_path, ".memoria", "agent", name))
    ]
    parts = [
        f"知识库：{os.path.abspath(kb_path)}",
        f"Markdown 文档：{len(files)} 篇；知识点合计：{total_kps} 个",
        f"指令文件：{', '.join(instruction_files) if instruction_files else '（无）'}",
        "",
        "文件清单：",
        *rows,
    ]
    if len(files) > MAX_FILES_IN_OVERVIEW:
        parts.append(f"…（还有 {len(files) - MAX_FILES_IN_OVERVIEW} 篇未列出）")
    return ToolOutput(text="\n".join(parts))


def _readonly_document_service(kb_path: str) -> Any:
    """构造不触发写库引导的 `DocumentService`（详见模块 docstring 取舍 2）。"""
    from memoria.services.document import DocumentService

    service = DocumentService(kb_path=None)
    service.kb_path = kb_path
    service._cache.clear()
    return service


def _validate_kb(kb_path: str) -> ToolOutput:
    with kb_read_only(kb_path):
        report = _readonly_document_service(kb_path).validate_kb()

    parts = [
        f"校验结果：{report.get('status')}；检查 {report.get('files_checked', 0)} 篇文档，"
        f"errors={report.get('errors', 0)} warnings={report.get('warnings', 0)}。"
    ]
    details: list[str] = []
    for row in (report.get("files") or [])[:MAX_ISSUES_IN_REPORT]:
        for issue in (row.get("errors") or []):
            details.append(f"- [error] {row.get('path')}: {issue}")
        for issue in (row.get("warnings") or []):
            details.append(f"- [warning] {row.get('path')}: {issue}")
    for key in ("kb_integrity", "manifest_diff"):
        block = report.get(key) or {}
        for level in ("errors", "warnings"):
            for issue in (block.get(level) or [])[:MAX_ISSUES_IN_REPORT]:
                details.append(f"- [{level[:-1]}] {issue.get('message') or issue}")
    for issue in (report.get("path_moves") or [])[:MAX_ISSUES_IN_REPORT]:
        details.append(f"- [error] 路径漂移 {issue.get('from')} → {issue.get('to')}")
    graph = report.get("graph_audit") or {}
    for row in (graph.get("files") or [])[:MAX_ISSUES_IN_REPORT]:
        for issue in (row.get("issues") or []):
            details.append(f"- [图] {row.get('path')}: {issue.get('message') or issue}")

    if details:
        parts.extend(["", *details[: MAX_ISSUES_IN_REPORT * 2]])
    return ToolOutput(text="\n".join(parts))


# —— 工具声明（OpenAI function-calling 兼容 schema）——


def _search_session_history(kb_path: str, query: str, limit: int) -> ToolOutput:
    """检索**历史会话**（过去与本库的对话记录）。

    与知识库文档无关：命中以「会话 `<id>` 第 N 条」标识，**不产生 `文件:行号` 锚点**
    （那是文档引用的形状，混用会让模型把对话当成库内出处）。只读会话 JSONL 目录，
    不碰正文 / sidecar / manifest；作用域限本库（不存在跨库会话）。
    """
    from memoria.services.agent.session.query import SessionQueryError, search_sessions

    text = (query or "").strip()
    if not text:
        return _error("search_sessions: query 不能为空")
    try:
        # 每会话只取最强一条（工具面靠它定位，避免把大段历史灌进上下文）；语料按 modified_at 倒序
        groups = search_sessions(kb_path, text, hit_limit=1)
    except SessionQueryError as exc:
        return _error(f"search_sessions: {exc}")
    if not groups:
        return ToolOutput(
            text=(
                "（历史会话里没有命中。注意这里检索的是**过去与本知识库的对话记录**，"
                "不是知识库文档 —— 找资料请用 `search_kb`。）"
            )
        )
    cap = max(1, min(limit, MAX_SESSION_HITS))
    lines = [f"历史会话命中 {len(groups)} 个（按最近聊过排序，最多列出 {cap} 个）："]
    for group in groups[:cap]:
        lines.append("")
        lines.append(f"## 会话 {group.session_id}")
        if group.title:
            lines.append(f"- 标题：{group.title}")
        lines.append(f"- 轮数：{group.turn_count}")
        hit = group.best
        lines.append(f"- 最强命中：第 {hit.seq} 条（{hit.type}）—— {hit.snippet}")
    lines.append("")
    lines.append("引用这些内容时写成「会话 <id> 第 N 条」，**不要**写成 `文件:行号`（那是知识库文档的形状）。")
    return ToolOutput(text="\n".join(lines))


def build_kb_tools(kb_path: str, *, top_k: int = DEFAULT_TOP_K) -> tuple[Tool, ...]:
    """绑定到某个知识库的只读工具集；全部声明 `read_only=True`。"""
    root = os.path.abspath(kb_path)

    def _bound_search(arguments: Mapping[str, Any]) -> ToolOutput:
        return _search_kb(root, str(arguments.get("query") or ""), int(arguments.get("top_k") or top_k))

    def _bound_search_sessions(arguments: Mapping[str, Any]) -> ToolOutput:
        raw = arguments.get("limit")
        try:
            limit = int(raw) if raw is not None else DEFAULT_SESSION_HITS
        except (TypeError, ValueError):
            limit = DEFAULT_SESSION_HITS
        return _search_session_history(root, str(arguments.get("query") or ""), limit)

    return (
        Tool(
            name="search_kb",
            description=(
                "在知识库内做词法检索，返回命中知识点所在文件与行号锚点及片段。"
                "需要查资料、确认库内是否已有某概念时先用它。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "description": "检索词或问题关键词"},
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": f"返回条数上限（默认 {top_k}）",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_bound_search,
        ),
        Tool(
            name="read_document",
            description=(
                "读取知识库内一篇 Markdown 文档的正文与知识点清单（带 `文件:行号`）。"
                f"正文默认返回前 {DEFAULT_READ_LIMIT} 行；被截断时正文尾会给出一条续读提示，"
                "按提示里的 offset 再调一次即可接着读。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1, "description": "知识库内相对路径，例如 neural-network.md"},
                    "offset": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "正文起始行（1-based，默认 1；行号口径与知识点锚点一致）",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": DEFAULT_READ_LIMIT,
                        "description": f"最多返回多少行正文（默认且最多 {DEFAULT_READ_LIMIT}）",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _read_document_call(root, arguments),
        ),
        Tool(
            name="read_kp",
            description="按知识点 id 读取该知识点的正文片段与元数据（带 `文件:行号`）。",
            parameters={
                "type": "object",
                "properties": {"id": {"type": "string", "minLength": 1, "description": "知识点 id，例如 mlp"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _read_kp(root, str(arguments.get("id") or "")),
        ),
        Tool(
            name="kb_overview",
            description="查看知识库规模与文件清单概览（文档数、知识点数、指令文件、文件列表）。",
            parameters={
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "description": "可选：为何需要概览（仅用于审计，不参与计算）"}
                },
                "additionalProperties": False,
            },
            handler=lambda _arguments: _kb_overview(root),
        ),
        Tool(
            name="validate_kb",
            description="运行知识库校验，返回 errors/warnings 摘要（sidecar、manifest、路径漂移、图链接）。",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda _arguments: _validate_kb(root),
        ),
        Tool(
            name="search_sessions",
            description=(
                "检索**过去与本知识库的对话记录**（历史会话），返回命中的会话与片段。"
                "问「我们之前聊过什么 / 上次说到哪」这类问题时用它；"
                "它检索的不是知识库文档（找资料请用 `search_kb`）。"
                "命中以「会话 <id> 第 N 条」标识，**不要**写成 `文件:行号`。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "description": "检索词（按字面量匹配：空白弹性、大小写不敏感）",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_SESSION_HITS,
                        "description": f"最多列出多少个会话（默认 {DEFAULT_SESSION_HITS}）",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_bound_search_sessions,
        ),
        # —— 上游读面（2026-09-20，§6.16）：`glob` / `grep` / `read_image` ——
        # 三者都只读；允许根（今天=库根）之外一律拒绝，VCS 元数据目录排除、`.memoria/**` 默认可见（见文件末尾块）。
        Tool(
            name="glob",
            description=(
                "按 glob 模式列出**工作区内**（当前 = 知识库根）的文件路径（只读，只列文件、不列目录）。"
                "不含 `/` 的模式匹配任意深度的文件名（`*.md` 等于在全库找 .md）；"
                f"最多返回 {GLOB_MAX_RESULTS} 条（按修改时间新→旧），超出时给出计数与收窄提示。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "minLength": 1, "description": "glob 模式，例如 **/*.md、vocab/*.md"},
                    "path": {"type": "string", "description": "可选：工作区相对目录（搜索根，默认工作区根）"},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _glob_tool(root, arguments),
        ),
        Tool(
            name="grep",
            description=(
                "在**工作区内**（当前 = 知识库根）按正则逐行搜索正文，按文件分组返回 `Line N: <片段>`（只读）。"
                f"最多返回 {GREP_MAX_MATCHES} 处命中、单行预览 {GREP_MAX_LINE_BYTES} 字节，"
                f"扫描超过 {GREP_TIMEOUT_S:.0f} 秒即中止。正则用 Python `re` 语法（非 ripgrep 方言）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python `re` 正则（空白本身是合法模式）"},
                    "path": {"type": "string", "description": "可选：工作区相对文件或目录（默认整个工作区根）"},
                    "include": {
                        "type": "string",
                        "description": "可选：单个正向 glob 过滤文件名，例如 *.md、*.{md,markdown}（不支持 ! 取反与逗号列表）",
                    },
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _grep_tool(root, arguments),
        ),
        Tool(
            name="read_image",
            description=(
                "读取工作区内的 PNG/JPEG/WebP/GIF 图片。**当前缺「多媒体眼睛」插件**："
                "调用只会做参数与格式校验并返回明确错误，不会返回图片内容 —— 需要图上的信息时请改用文字描述。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "minLength": 1, "description": "库内相对路径，例如 .memoria/images/x.png"}
                },
                "required": ["file_path"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _read_image_tool(root, arguments),
        ), *_session_query_tools(root), *_reference_tools(root), *_write_proposal_tools(root),
    )


# ── 上游读面移植：`read_document` 分页 + `glob` / `grep` / `read_image`（2026-09-20；§6.16）──
# 语义移植自 deepseek-harness `packages/fs/tool-fs`（`src/read.ts` 的 `offset`/`limit` 与三重 cap、
# `src/read-render.ts` 的续读 footer 文案、`src/read-image.ts` 的扩展名/签名判定）与
# `packages/fs/tool-fs-search`（`src/glob.ts` 的 `globMaxResults` 与 VCS 目录排除、`src/grep.ts`
# 的 `grepMaxMatches`/`grepMaxLineBytes`/`include` 单 glob 校验），pin `0d1f5000`。
#
# 整块**追加在文件末尾**（上方既有 `<文件>:<行号>` 锚点零漂移；唯一例外是 `read_document`
# 工具声明区因新增 `offset`/`limit` 两个参数 +15 行，其后锚点已重取，见 §6.16「文档」）。
#
# 与上游的三处结构性差异（详见 §6.16 偏差表）：
# 1. 工具面是**工作区根**（今天 = 库根）而不是「知识库内容面」：路径经**允许根列表**校验（今天
#    = `[库根]`，将来可追加外部根：只读/不可信），可见性由程序施加；VCS 内部目录跳过，
#    `.memoria/**` 默认可见，解析到允许根之外的条目一律**明确拒绝**（不是「不存在」）且不读；
# 2. `grep` 用 Python `re` 而非 ripgrep：正则方言不同（无 `\p{…}`、无 `\z` 之外的 PCRE 扩展），
#    结果上限与超时都在 Python 侧自持（`GREP_MAX_MATCHES` / `GREP_TIMEOUT_S`），零新依赖；
# 3. `read_image` 缺的是**多媒体「眼睛」插件**（属未来多媒体能力，不算读面缺口）：端点消息
#    层是纯文本（`llm/types.py` 的 `Message.content`），承载不了图片内容块 ⇒ 校验后明确拒绝。

#: 一次 `read_document` 返回的默认且最大正文行数（上游 `READ_LIMIT`，`tool-fs/src/read.ts:15`）。
DEFAULT_READ_LIMIT = 2000
#: 一次 `glob` 内联展示的路径上限（上游 `globMaxResults`，`tool-fs-search/src/glob.ts:25` + README.md:60）。
GLOB_MAX_RESULTS = 100
#: `glob`/`grep` 遍历跳过的目录名：**只跳 VCS 内部**（上游 `GLOB_VCS_EXCLUDES`，`src/glob.ts:37`）—— 理由=非内容且会污染 glob/grep；`.memoria/**` 默认可见（2026-09-20 改正）。
GLOB_EXCLUDED_DIRS = (".git", ".svn", ".hg", ".bzr", ".jj", ".sl")
#: 一次 `grep` 内联保留的命中数上限（上游 `grepMaxMatches`，`src/grep.ts:29` + README.md:61）。
GREP_MAX_MATCHES = 250
#: 单条命中行预览的字节上限（上游 `grepMaxLineBytes`，`src/grep.ts:35` + README.md:62）。
GREP_MAX_LINE_BYTES = 2000
#: `grep` 的协作式时间预算（秒），对齐上游 `timeoutMs` 默认 30000（README.md:64）。
GREP_TIMEOUT_S = 30.0
#: `grep` 单文件读取上限（**本地新增边界**：上游由 ripgrep 流式处理、无此上限）；超限文件跳过并计数。
GREP_MAX_FILE_BYTES = 4 * 1024 * 1024
#: 二进制探测的前导字节数（对齐 ripgrep 口径：前导含 NUL 即视为二进制并跳过）。
GREP_BINARY_SNIFF_BYTES = 8192
#: 图片签名探测需要的字节数（PNG 8 / JPEG 3 / GIF 6 / RIFF-WEBP 12）。
IMAGE_SNIFF_BYTES = 16
#: `read_image` 认的扩展名 → 媒体类型（逐字照抄上游 `IMAGE_EXTENSIONS`，`read-image.ts:25-31`）。
IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
#: 「本端点不支持图像输入」的稳定错误码（本地新增；上游同类拒绝是普通错误、无专用码）。
UNSUPPORTED_IMAGE_INPUT = "UNSUPPORTED_IMAGE_INPUT"


class _ReadOffsetError(ValueError):
    """`read_document` 的 `offset` 超出正文行数（上游抛 `FS_NOT_FOUND`，`read-render.ts:96-98`）。"""


def _positive_int(raw: Any, default: int) -> int | None:
    """`None`（未给）⇒ `default`；非整数 / 布尔 / < 1 ⇒ `None`（调用方据此出参数错误）。"""
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return None
    return raw


def _read_window(
    lines: Sequence[str],
    *,
    offset: int,
    limit: int | None,
    display: str,
    body: str,
) -> tuple[str, str]:
    """按 `offset`/`limit`/字符预算取正文窗口，返回 `(窗口文本, 续读提示)`。

    语义对齐上游 `buildWindow()` + `formatReadOutput()`（`read-render.ts:111-170`）：

    - `offset` 是 **1-based 正文行号**（frontmatter 已剥离，与知识点锚点同一行空间）；
    - `limit` 省略时取 `DEFAULT_READ_LIMIT`（上游「默认值 = 上限」的口径）；
    - 字符预算仍是既有 `MAX_BODY_CHARS`（本地边界，上游对应 `readMaxBytes`）；
    - 越界（`offset > 总行数`；空文件 + `offset=1` 除外）抛 `_ReadOffsetError`，消息对齐上游
      `offset <offset> is out of range for "<path>" (<total> lines)`；
    - 未截断时**不产出 footer**（保持旧调用逐字兼容），且正文末尾换行照旧保留。
    """
    cap = DEFAULT_READ_LIMIT if limit is None else limit
    total = len(lines)
    if offset > total and not (total == 0 and offset == 1):
        raise _ReadOffsetError(f'offset {offset} 超出范围 —— "{display}" 正文共 {total} 行')
    start = offset - 1
    window: list[str] = []
    used = 0
    while start + len(window) < total and len(window) < cap:
        text = lines[start + len(window)]
        cost = len(text) + (1 if window else 0)
        if used + cost > MAX_BODY_CHARS:
            break
        window.append(text)
        used += cost
    end = start + len(window)  # 末行的 1-based 行号；窗口为空时 = offset - 1
    if end >= total:
        tail = "\n" if window and start == 0 and body.endswith("\n") else ""
        return "\n".join(window) + tail, ""
    if not window:
        footer = f"\n…（第 {offset} 行本身就超过 {MAX_BODY_CHARS} 字符的正文预算，未返回内容。）"
    elif len(window) < cap:
        footer = (
            f"\n…（正文已达 {MAX_BODY_CHARS} 字符预算：显示第 {offset}-{end} 行，共 {total} 行；"
            f"续读请把 offset 设为 {end + 1}。）"
        )
    else:
        footer = f"\n…（已显示第 {offset}-{end} 行，共 {total} 行；续读请把 offset 设为 {end + 1}。）"
    return "\n".join(window), footer


def _read_document_call(kb_path: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`read_document` 的工具包装层：解析 `offset`/`limit`，把越界转成 `NOT_FOUND` 结果。"""
    offset = _positive_int(arguments.get("offset"), 1)
    limit = _positive_int(arguments.get("limit"), DEFAULT_READ_LIMIT)
    if offset is None:
        return _error("read_document: offset 必须是 ≥ 1 的整数")
    if limit is None or limit > DEFAULT_READ_LIMIT:
        return _error(f"read_document: limit 必须是 1..{DEFAULT_READ_LIMIT} 的整数")
    try:
        return _read_document(kb_path, str(arguments.get("path") or ""), offset=offset, limit=limit)
    except _ReadOffsetError as exc:
        return _error(f"read_document: {exc}", "NOT_FOUND")


def _safe_rel_any(kb_path: str, path: str) -> str | None:
    """校验并归一化工作区相对路径（**不限定扩展名**）；空 / 上跳 / 越界返回 None。

    与 `_safe_rel()` 同源，只去掉 `.md` 后缀要求：`glob`/`grep` 要能指向任意文件与目录。
    校验与归一化统一走**允许根列表**（`_read_roots()`）——
    今天单根 ⇒ 语义与改正前逐字一致，将来多根即按序解析。
    """
    rel = (path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return None
    resolved = _resolve_in_read_roots(_read_roots(kb_path), rel)
    if resolved is None:
        return None
    # 越界（`..` / 绝对路径 / 允许根之外）在 `_resolve_in_read_roots()` 内 fail-closed 拒绝
    # ⇒ 这里只回「落在某个允许根内」的相对路径，调用方（glob/grep/read_image）无需改动。
    return resolved[1]


def _safe_rel_dir(kb_path: str, path: str) -> str | None:
    """工作区相对**目录**（`""` = 工作区根）；越界/非法返回 None。"""
    norm = _safe_rel_any(kb_path, path)
    if norm is None:
        return None
    return "" if norm == "." else norm


def _walk_kb_files(kb_path: str, subdir: str = "") -> list[str]:
    """工作区文件清单（相对**允许根**、`/` 分隔）：跳过 VCS 目录与解析到允许根外的条目。

    越界判定在**两侧都先 `realpath`**：Windows 8.3 短名（`LAMTIM~1`）与 junction/符号链接会让
    `realpath` 与 `abspath` 的书写形式不同 —— 只归一化一侧会把整个库误判成「根外」而**静默返回空**。
    """
    out: list[str] = []
    for root in _read_roots(kb_path):  # 今天单根（= 库根）⇒ 输出与改正前逐字一致；将来可多根
        real_root = os.path.realpath(root)
        base = os.path.join(root, subdir) if subdir else root
        for current, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(name for name in dirnames if name not in GLOB_EXCLUDED_DIRS)
            prefix = os.path.relpath(current, root).replace(os.sep, "/")
            prefix = "" if prefix == "." else prefix + "/"
            for name in filenames:
                real = os.path.realpath(os.path.join(current, name))
                if real != real_root and not real.startswith(real_root + os.sep):
                    continue  # 符号链接指向根外 ⇒ 不返回（后续也不会去读）
                out.append(prefix + name)
    return sorted(out)


def _translate_glob(pattern: str) -> str:
    """glob → 正则**主体**：`*` 不跨 `/`、`**` 跨目录（`**/` 可匹配零层）、`{a,b}` 择一、`[...]` 透传。

    与上游 ripgrep 的 glob 方言有出入（见 §6.16 偏差 2）：不支持 `!` 取反、不支持 `**` 之外
    的深度修饰；`{}` 只做单层展开（不嵌套）。
    """
    import re

    out: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**", index):
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    out.append("(?:.*/)?")
                    index += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                index += 1
            continue
        if char == "?":
            out.append("[^/]")
        elif char == "{":
            end = pattern.find("}", index + 1)
            if end < 0:
                out.append(re.escape(char))
            else:
                options = pattern[index + 1 : end].split(",")
                out.append("(?:" + "|".join(_translate_glob(option) for option in options) + ")")
                index = end + 1
                continue
        elif char == "[":
            end = pattern.find("]", index + 1)
            if end < 0:
                out.append(re.escape(char))
            else:
                out.append(pattern[index : end + 1])
                index = end + 1
                continue
        else:
            out.append(re.escape(char))
        index += 1
    return "".join(out)


def _glob_matcher(pattern: str) -> Any:
    """按上游口径构造匹配函数：模式含 `/` 时比「相对搜索根的整条路径」，否则比**文件名**（任意深度）。"""
    import re

    rx = re.compile(_translate_glob(pattern) + r"\Z", re.DOTALL)
    by_name = "/" not in pattern

    def matches(rel: str) -> bool:
        target = rel.rsplit("/", 1)[-1] if by_name else rel
        return rx.match(target) is not None

    return matches


def _mtime(kb_path: str, rel: str) -> float:
    try:
        return os.stat(os.path.join(kb_path, rel)).st_mtime
    except OSError:
        return 0.0


def _glob_tool(kb_path: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`glob`：按 glob 模式列出工作区文件（只读；允许根之外与越界一律拒绝）。"""
    pattern = str(arguments.get("pattern") or "").strip()
    if not pattern:
        return _error("glob: pattern 不能为空")
    raw_path = str(arguments.get("path") or "").strip()
    subdir = ""
    if raw_path:
        resolved = _safe_rel_dir(kb_path, raw_path)
        if resolved is None:
            return _error("glob: path 必须是工作区（允许根）内的相对目录（不得上跳或越界）")
        subdir = resolved
        if not os.path.isdir(os.path.join(kb_path, subdir) if subdir else kb_path):
            return _error(f"glob: 目录不存在：{raw_path}", "NOT_FOUND")
    matches = _glob_matcher(pattern)
    found = [
        rel
        for rel in _walk_kb_files(kb_path, subdir)
        if matches(rel[len(subdir) + 1 :] if subdir else rel)
    ]
    if not found:
        return ToolOutput(text=f"未匹配到文件（pattern={pattern!r}）。glob 只列文件、不列目录。")
    # 上游 `--sort=modified`：按修改时间排序（方向取「新→旧」，证据见 §6.16 未实测第 ① 条）
    found.sort(key=lambda rel: _mtime(kb_path, rel), reverse=True)
    shown = found[:GLOB_MAX_RESULTS]
    rows = list(shown)
    if len(found) > len(shown):
        rows.extend(
            [
                "",
                f"（匹配 {len(found)} 个文件，仅显示最近修改的 {len(shown)} 个；"
                "本库无 spill 存储，请收窄 pattern 或 path 以查看其余。）",
            ]
        )
    return ToolOutput(text="\n".join(rows))


def _check_include(include: str) -> str | None:
    """校验 `include` 是**单个正向 glob**（对齐上游 `validateInclude()`，`grep.ts:67-78`）。"""
    if not include.strip():
        return "include 不能为空"
    if include.startswith("!"):
        return "include 只接受正向 glob；不支持 `!` 取反"
    depth = 0
    for char in include:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            return "include 只能是单个 glob（择一请写成 {a,b}，不要用逗号列表）"
    return None


def _preview_line(text: str, max_bytes: int = GREP_MAX_LINE_BYTES) -> str:
    """按字节截断预览行，不切开 UTF-8 码点（上游 `previewLine()` 口径）。"""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="ignore") + "…"


def _grep_skipped_note(large: int, binary: int) -> str:
    bits: list[str] = []
    if large:
        bits.append(f"{large} 个文件超过 {GREP_MAX_FILE_BYTES // (1024 * 1024)} MiB 未扫描")
    if binary:
        bits.append(f"{binary} 个二进制文件已跳过")
    return f"（{'；'.join(bits)}）" if bits else ""


def _grep_tool(kb_path: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`grep`：正则逐行搜工作区正文，按文件分组返回 `Line N: <片段>`（只读）。"""
    import re
    import time

    pattern = str(arguments.get("pattern") or "")
    if pattern == "":
        return _error("grep: pattern 不能为空（空白本身是合法正则）")
    include = str(arguments.get("include") or "")
    if include:
        problem = _check_include(include)
        if problem is not None:
            return _error(f"grep: include 非法 —— {problem}")
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return _error(f"grep: 正则非法（本工具用 Python `re` 语法，非 ripgrep 方言）—— {exc}")

    raw_path = str(arguments.get("path") or "").strip()
    if raw_path:
        resolved = _safe_rel_any(kb_path, raw_path)
        if resolved is None:
            return _error("grep: path 必须是工作区（允许根）内的相对文件或目录（不得上跳或越界）")
        full = os.path.join(kb_path, resolved)
        if os.path.isdir(full):
            targets = _walk_kb_files(kb_path, "" if resolved == "." else resolved)
        elif os.path.isfile(full):
            targets = [resolved]
        else:
            return _error(f"grep: 目标不存在：{resolved}", "NOT_FOUND")
    else:
        targets = _walk_kb_files(kb_path)
    if include:
        matches_include = _glob_matcher(include)
        targets = [rel for rel in targets if matches_include(rel)]

    deadline = time.monotonic() + GREP_TIMEOUT_S
    hits: list[tuple[str, int, str]] = []
    seen = 0
    skipped_large = 0
    skipped_binary = 0
    for rel in targets:
        if time.monotonic() > deadline:
            return _error(
                f"grep: 超过 {GREP_TIMEOUT_S:.0f} 秒协作预算已中止（已扫到 {seen} 处命中）——"
                "请收窄 pattern / path / include 后重试",
                "SEARCH_ABORTED",
            )
        full = os.path.join(kb_path, rel)
        try:
            if os.path.getsize(full) > GREP_MAX_FILE_BYTES:
                skipped_large += 1
                continue
            with open(full, "rb") as handle:
                head = handle.read(GREP_BINARY_SNIFF_BYTES)
                if b"\x00" in head:
                    skipped_binary += 1
                    continue
                payload = head + handle.read()
        except OSError:
            continue
        for number, line in enumerate(payload.decode("utf-8", errors="replace").splitlines(), start=1):
            if rx.search(line) is None:
                continue
            seen += 1
            if len(hits) < GREP_MAX_MATCHES:
                hits.append((rel, number, _preview_line(line)))

    note = _grep_skipped_note(skipped_large, skipped_binary)
    if not hits:
        return ToolOutput(text=f"未匹配到内容（pattern={pattern!r}）。{note}")
    grouped: dict[str, list[str]] = {}
    for rel, number, text in hits:
        grouped.setdefault(rel, []).append(f"Line {number}: {text}")
    body = "\n\n".join(f"{rel}\n" + "\n".join(rows) for rel, rows in grouped.items())
    header = (
        f"命中 {len(hits)} 处（pattern={pattern!r}）"
        if seen <= len(hits)
        else f"命中 {len(hits)}/{seen} 处（pattern={pattern!r}）"
    )
    parts = [header, "", body]
    if seen > len(hits):
        parts.extend(
            [
                "",
                f"（仅显示前 {len(hits)} 处；本库无 spill 存储，请收窄 pattern / path / include 以查看其余。）",
            ]
        )
    if note:
        parts.append(note)
    return ToolOutput(text="\n".join(parts))


def _sniff_image_media_type(data: bytes) -> str | None:
    """按文件签名判定媒体类型（逐条对齐上游 `sniffImageMediaType()`，`read-image.ts:54-60`）。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _read_image_tool(kb_path: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`read_image`：参数与格式校验照上游，随后因**缺「多媒体眼睛」插件**而明确拒绝。

    不伪造成功：缺的是**多媒体「眼睛」插件**（属未来多媒体能力，非读面缺口）—— 本地消息层
    （`llm/types.py` 的纯文本 `Message.content`）无法承载图片内容块，故校验通过后仍返回
    `UNSUPPORTED_IMAGE_INPUT`，并在文本里说明真实原因与替代做法（图片识别留待该插件）。
    校验顺序先参数/格式、后能力拒绝：这样模型能区分「文件不是图片」与「端点收不了图片」。
    """
    raw = str(arguments.get("file_path") or "")
    if not raw.strip():
        return _error("read_image: file_path 不能为空")
    normalized = _safe_rel_any(kb_path, raw)
    if normalized is None:
        return _error("read_image: file_path 必须是工作区（允许根）内的相对路径（不得上跳或越界）")
    extension = os.path.splitext(normalized)[1].lower()
    declared = IMAGE_EXTENSIONS.get(extension)
    if declared is None and extension:
        return _error(
            f"read_image: 扩展名 {extension} 不是受支持的图片格式 —— read_image 只认 PNG/JPEG/WebP/GIF"
            "（无扩展名的路径按文件签名判定）"
        )
    full = os.path.join(kb_path, normalized)
    if not os.path.isfile(full):
        return _error(f"read_image: 文件不存在：{normalized}", "NOT_FOUND")
    try:
        with open(full, "rb") as handle:
            data = handle.read(IMAGE_SNIFF_BYTES)
    except OSError as exc:
        return _error(f"read_image: 读取失败 —— {exc}")
    sniffed = _sniff_image_media_type(data)
    if sniffed is None:
        return _error(f"read_image: 文件内容不是受支持的图片格式（PNG/JPEG/WebP/GIF）：{normalized}")
    if declared is not None and declared != sniffed:
        # 上游同类拒绝：扩展名声明的类型与文件签名不一致（`read-image.ts` 的 IMAGE_TYPE_MISMATCH）。
        return _error(
            f"read_image: 扩展名 {extension} 声明 {declared}，但文件签名是 {sniffed} ——"
            " 请把文件重命名成与内容一致的格式，或先转换成 PNG/JPEG/WebP/GIF"
        )
    media_type = declared or sniffed
    return _error(
        f"read_image: 本端点暂不支持图像输入 —— {normalized} 已通过格式校验（{media_type}），"
        "但缺『多媒体眼睛』插件（属未来多媒体能力）：当前模型通道（纯文本 `Message.content`）"
        "无法把图片作为内容块发出，故不返回图片本身；请改用文字描述该图（见 dsh-agent-port.md §6.16）。",
        UNSUPPORTED_IMAGE_INPUT,
    )


# ── 允许读根列表（2026-09-20 设计改正：工具面 = **工作区根**，不是「知识库内容面」）──
# 今天只有一个允许根（= 库根）⇒ 与改正前行为逐字等价；结构上支持将来追加外部根（例如 Windows
# 拖入对话栏的外部文件，可带只读/不可信标记）。「只能看到某些文件」是**程序施加的可见性/权限**
# （VCS 内部目录跳过 + realpath 越界拒绝），**不是**把工具本身缩到知识库；允许根之外一律
# **明确拒绝**（fail-closed：参数错误，不是「文件不存在」），将来把根加进本列表即放行。


def _read_roots(kb_path: str) -> tuple[str, ...]:
    """允许读根列表（agent 工作区）：今天 = `(库根,)`；将来可追加外部根（只读/不可信）。"""
    return (os.path.abspath(kb_path),)


def _resolve_in_read_roots(roots: Sequence[str], path: str) -> tuple[str, str] | None:
    """把相对路径解析到某个允许根，返回 `(根, 相对该根的路径)`；空 / 上跳 / 越界返回 None。

    fail-closed：任一根都不容纳 ⇒ None（调用方一律转成参数错误，绝不「当成不存在」）。
    """
    rel = (path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return None
    norm = os.path.normpath(rel).replace(os.sep, "/")
    if norm == ".." or norm.startswith("../"):
        return None
    for root in roots:
        full = os.path.abspath(os.path.join(root, norm))
        if full == root or full.startswith(root + os.sep):
            return root, norm
    return None


# ── 会话查询家族：其余四个工具（2026-09-20；§6.17）──────────────────────────────────
# 语义移植自 deepseek-harness `packages/session-query/tool-session-query`（`src/index.ts` 的五个工具
# 声明与 `isConcurrencySafe`、`src/input.ts` 的参数与 ISO 8601 时间戳口径、`src/operations.ts` 的
# 五个操作、`src/presentation.ts` 的结果文本）与 `packages/session-query/session-query`（`src/tracing.ts`、
# `src/index.ts` 的三个方法、`config.ts:6` 的 `SESSION_QUERY_READ_WINDOW_MAX`），pin `0d1f5000`。
#
# 整块**追加在文件末尾**：`build_kb_tools()` 的返回元组已就地接上 `*_session_query_tools(root)`、
# `KB_TOOL_NAMES` 已等量改写（两处都零行漂移）⇒ 上方既有 `<文件>:<行号>` 锚点全部未动。
#
# 与上游的四处结构性差异（逐条见 dsh-agent-port.md §6.17「语义偏差与取舍」）：
# 1. **无调用方会话身份** ⇒ 四个工具的 `session_id` **全部必填**；上游「省略 = 当前会话」以及事件
#    检索「在当前步骤之前截断」（`operations.ts:128-139`）都没有本地落点；
# 2. **无工作区授权面**（上游按调用方 `cwd` 精确相等授权，`workspace-access.ts`）：本地语料就是
#    本库会话目录，作用域天然限本库 ⇒ 没有 `SESSION_QUERY_TOOL_UNAUTHORIZED` 一类错误；
# 3. **无 spill、无 `searchTimeoutMs`（30s 协作截止）**：与既有 `search_sessions` 一致，命中上限与
#    四重有界化（`session/query.py`）已足够；上游「模型看不到游标/偏移/分页大小/可控上限」照做；
# 4. **错误码取本地既有码族**：参数/作用域非法 ⇒ `INVALID_ARGUMENTS`（fail-closed，绝不「静默空」）、
#    目标不存在 ⇒ `NOT_FOUND`（上游是 `SESSION_QUERY_INVALID_FILTER` / `SESSION_QUERY_*_NOT_FOUND`）。

#: 事件级检索的命中上限（上游 `maxSearchResults` 默认 100，`tool-session-query/src/index.ts:22`）。
SESSION_EVENT_HITS_CAP = 100
#: 带时区限定的 ISO 8601（逐字对齐上游 `input.ts:179-180` 的 `ISO_TIMESTAMP`：秒与小数秒可省，偏移必需）。
#: 存**模式串**而非编译结果：本模块顶层不导入 `re`（工具体内才用正则，见 `_translate_glob()` 等同款做法）。
_ISO_TIMESTAMP_PATTERN = (
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?(Z|([+-])(\d{2}):(\d{2}))$"
)


class _SessionArgError(ValueError):
    """会话查询工具的参数 / 作用域错误（一律转成 `INVALID_ARGUMENTS` 结果，fail-closed）。"""


def _iso_ms(value: Any) -> str:
    """epoch 毫秒 → 上游 `formatTime()` 的 `toISOString()` 形态（UTC，`Z` 结尾）。"""
    import datetime

    try:
        moment = datetime.datetime.fromtimestamp(int(value) / 1000, tz=datetime.timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_ms(value: Any, name: str) -> int | None:
    """带时区限定的 ISO 8601 → **含端点**的 epoch 毫秒；省略 / 空串 ⇒ `None`（不过滤）。

    口径对齐上游 `input.ts::parseIsoTimestamp()`：`Z` 或 `±HH:MM` 必需、秒与小数秒可省、逐项做
    日历校验；**偏差**：上游保留亚毫秒余数并按 `nextUp/nextDown` 夹紧端点，本地按**毫秒**截断。
    """
    import calendar
    import datetime
    import re

    text = str(value or "").strip()
    if not text:
        return None
    match = re.match(_ISO_TIMESTAMP_PATTERN, text)
    if match is None:
        raise _SessionArgError(f"{name} 必须是带时区限定的 ISO 8601 时间戳（`Z` 或 `±HH:MM`）：{text!r}")
    year, month, day, hour, minute = (int(match.group(index)) for index in range(1, 6))
    second = int(match.group(6) or 0)
    offset_hour = int(match.group(10) or 0)
    offset_minute = int(match.group(11) or 0)
    sign = -1 if match.group(9) == "-" else 1
    if (
        not 1 <= month <= 12
        or not 1 <= day <= calendar.monthrange(year, month)[1]
        or hour > 23
        or minute > 59
        or second > 59
        or offset_hour > 23
        or offset_minute > 59
    ):
        raise _SessionArgError(f"{name} 不是合法的 ISO 8601 时间戳：{text!r}")
    zone = datetime.timezone(sign * datetime.timedelta(hours=offset_hour, minutes=offset_minute))
    return int(datetime.datetime(year, month, day, hour, minute, second, tzinfo=zone).timestamp() * 1000)


def _seq_arg(value: Any, name: str) -> int | None:
    """`seq` / `seq_from` / `seq_to`：省略 ⇒ `None`；负数 / 布尔 / 非整数 ⇒ 参数错误（上游 `assertNonNegativeSafeInteger`）。"""
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _SessionArgError(f"{name} 必须是 ≥ 0 的整数（收到 {value!r}）")
    return value


def _event_types_arg(value: Any) -> tuple[str, ...] | None:
    """事件类型白名单：省略 ⇒ `None`；空数组 / 非字符串项 ⇒ 参数错误（上游 `assertNonEmptyArray`）。"""
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise _SessionArgError("event_types 必须是至少含一个取值的字符串数组")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _SessionArgError("event_types 的取值必须是非空字符串")
        out.append(item)
    return tuple(out)


def _session_arg(arguments: Mapping[str, Any], tool: str) -> str:
    """`session_id`（**本地必填**：没有「调用方会话」身份可用）。"""
    value = arguments.get("session_id")
    if not isinstance(value, str) or not value.strip():
        raise _SessionArgError(f"{tool}: session_id 必填（本地没有「当前会话」身份，不能省略）")
    return value.strip()


def _title_of(kb_path: str, session_id: str) -> str:
    """会话标题（与 `agent_sessions_list` / `search_sessions` 同一口径：`summarize_session_file` 的原始行扫描）。"""
    from memoria.services.agent.session.history import summarize_session_file
    from memoria.services.agent.session.store import session_file

    return str(summarize_session_file(session_file(kb_path, session_id)).get("title") or "")


def _seq_text(values: Sequence[int]) -> str:
    return "无" if not values else "、".join(f"第 {value} 条" for value in values)


def _neighbour_line(event: Mapping[str, Any]) -> str:
    """事件精读的相邻事件摘要（上游 `presentation.ts::formatNeighbor()`：标题行 + 语义文本缩进两格）。"""
    from memoria.services.agent.session.query import event_text

    head = f"- 第 {event.get('seq')} 条 | {event.get('type')} | {_iso_ms(event.get('time'))}"
    text = event_text(event)
    if not text:
        return head + " | （无语义文本）"
    return head + "\n  " + text.replace("\n", "\n  ")


def _session_event_search(root: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`session_event_search`：一个会话内的事件级检索（上游 `executeEventSearch`，作用域 = 本库会话）。"""
    from memoria.services.agent.session.query import (
        SessionQueryError,
        SessionQueryNotFound,
        require_session,
        search_session,
    )

    tool = "session_event_search"
    try:
        session_id = _session_arg(arguments, tool)
        query = str(arguments.get("query") or "")
        if not query.strip():
            raise _SessionArgError("query 不能为空")
        seq_from = _seq_arg(arguments.get("seq_from"), "seq_from")
        seq_to = _seq_arg(arguments.get("seq_to"), "seq_to")
        if seq_from is not None and seq_to is not None and seq_from > seq_to:
            raise _SessionArgError("seq_from 不得大于 seq_to")
        time_from = _epoch_ms(arguments.get("time_from"), "time_from")
        time_to = _epoch_ms(arguments.get("time_to"), "time_to")
        if time_from is not None and time_to is not None and time_from > time_to:
            raise _SessionArgError("time_from 不得大于 time_to")
        types = _event_types_arg(arguments.get("event_types"))
        require_session(root, session_id)  # 作用域坏掉 fail loud，不静默空
        hits = search_session(
            root,
            session_id,
            query,
            limit=SESSION_EVENT_HITS_CAP + 1,
            types=types,
            time_from=time_from,
            time_to=time_to,
            seq_from=seq_from,
            seq_to=seq_to,
        )
        title = _title_of(root, session_id)
    except _SessionArgError as exc:
        return _error(f"{tool}: {exc}")
    except SessionQueryNotFound as exc:
        return _error(f"{tool}: {exc}", "NOT_FOUND")
    except SessionQueryError as exc:
        return _error(f"{tool}: {exc}")
    except ValueError as exc:  # 非法会话 id（`session_file()` 的 fail-closed 正则）
        return _error(f"{tool}: {exc}")

    capped = len(hits) > SESSION_EVENT_HITS_CAP
    hits = hits[:SESSION_EVENT_HITS_CAP]
    lines = [f"会话 {session_id} — {title}" if title else f"会话 {session_id}", ""]
    if not hits:
        lines.append(f"未在该会话里命中（query={query!r}）。")
    else:
        lines.append(f"事件命中 {len(hits)} 条：")
        for index, hit in enumerate(hits, start=1):
            lines.append(f"{index}. 第 {hit.seq} 条 | {hit.type} | {_iso_ms(hit.time)}")
            lines.append(f"   片段：{hit.snippet}")
        if capped:
            lines.extend(
                ["", f"（已达结果上限 {SESSION_EVENT_HITS_CAP} 条：请收窄 query 或加过滤条件以看到其余。）"]
            )
    lines.extend(
        [
            "",
            f"引用这些内容时写成「会话 {session_id} 第 N 条」，**不要**写成 `文件:行号`（那是知识库文档的形状）。",
        ]
    )
    return ToolOutput(text="\n".join(lines))


def _session_trace(root: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`session_trace`：一个会话的谱系（上游 `executeSessionTrace` / `presentation.formatSessionTrace`）。"""
    from memoria.services.agent.session.query import (
        SessionQueryError,
        SessionQueryNotFound,
        session_lineage,
    )

    tool = "session_trace"
    try:
        session_id = _session_arg(arguments, tool)
        lineage = session_lineage(root, session_id)
    except _SessionArgError as exc:
        return _error(f"{tool}: {exc}")
    except SessionQueryNotFound as exc:
        return _error(f"{tool}: {exc}", "NOT_FOUND")
    except SessionQueryError as exc:
        return _error(f"{tool}: {exc}")
    except ValueError as exc:
        return _error(f"{tool}: {exc}")

    target = lineage.target
    lines = [
        f"会话 {target.session_id} — {target.title}" if target.title else f"会话 {target.session_id}",
        f"创建时间：{_iso_ms(target.created_at)}",
        "",
        "祖先（由近及远）：",
    ]
    if not lineage.ancestors and lineage.unresolved_parent_id is None:
        lines.append("- 无（目标即根会话）")
    for record in lineage.ancestors:
        lines.append(f"- {record.session_id} — {record.title} | {_iso_ms(record.created_at)}")
    if lineage.unresolved_parent_id is not None:
        lines.append(f"- [{lineage.unresolved_parent_id}] 不在本地会话目录里（父会话未解析）")
    lines.append("")
    lines.append("后代：")
    if not lineage.descendants:
        lines.append("- 无")
    for depth, record in lineage.descendants:
        lines.append(f"{'  ' * depth}- {record.session_id} — {record.title} | {_iso_ms(record.created_at)}")
    if not lineage.ancestors and not lineage.descendants and lineage.complete:
        lines.extend(
            [
                "",
                "（本地会话格式不记录 `parentSession`：没有 fork/派生会话 ⇒ 每个会话都是根、都没有后代。）",
            ]
        )
    return ToolOutput(text="\n".join(lines))


def _session_event_trace(root: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`session_event_trace`：一条事件的替换关系与（缺失的）引用关系（上游 `executeEventTrace`）。"""
    from memoria.services.agent.session.query import (
        SessionQueryError,
        SessionQueryNotFound,
        trace_event,
    )

    tool = "session_event_trace"
    try:
        session_id = _session_arg(arguments, tool)
        seq = _seq_arg(arguments.get("seq"), "seq")
        if seq is None:
            raise _SessionArgError("seq 必填")
        trace = trace_event(root, session_id, seq)
        title = _title_of(root, session_id)
    except _SessionArgError as exc:
        return _error(f"{tool}: {exc}")
    except SessionQueryNotFound as exc:
        return _error(f"{tool}: {exc}", "NOT_FOUND")
    except SessionQueryError as exc:
        return _error(f"{tool}: {exc}")
    except ValueError as exc:
        return _error(f"{tool}: {exc}")

    target = trace.target
    lines = [
        f"会话 {session_id} — {title}" if title else f"会话 {session_id}",
        f"目标：第 {target.get('seq')} 条 | {target.get('type')} | {_iso_ms(target.get('time'))}",
        f"被替换为：{_seq_text([] if trace.replaced_by is None else [trace.replaced_by])}",
        f"替换链：{_seq_text(trace.replacement_chain)}",
        f"被目标替换的事件：{_seq_text(trace.replaced_seqs)}",
    ]
    if trace.source_seqs is None:
        lines.append("直接引用的源事件：本地事件格式不记录 `sourceEventSeqs` ⇒ 无从给出（上游按该字段计算）")
    else:
        lines.append(f"直接引用的源事件：{_seq_text(trace.source_seqs)}")
    if trace.derived_seqs is None:
        lines.append("由目标派生的事件：同上，本地不落盘任何派生/引用关系 ⇒ 无从给出")
    else:
        lines.append(f"由目标派生的事件：{_seq_text(trace.derived_seqs)}")
    lines.extend(
        [
            "",
            "（本地「替换」口径：`compaction` 的 `shadowed` 与 `compaction/prune` 的 `pruned[].seq`"
            " 覆盖的事件，与回放一致。）",
        ]
    )
    return ToolOutput(text="\n".join(lines))


def _session_event_read(root: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """`session_event_read`：一条事件的**完整未删节**记录 + 可选相邻事件摘要（上游 `executeEventRead`）。"""
    import json as _json

    from memoria.services.agent.session.query import (
        SessionQueryError,
        SessionQueryNotFound,
        read_event,
    )

    tool = "session_event_read"
    try:
        session_id = _session_arg(arguments, tool)
        seq = _seq_arg(arguments.get("seq"), "seq")
        if seq is None:
            raise _SessionArgError("seq 必填")
        window = read_event(root, session_id, seq, before=arguments.get("before"), after=arguments.get("after"))
        title = _title_of(root, session_id)
    except _SessionArgError as exc:
        return _error(f"{tool}: {exc}")
    except SessionQueryNotFound as exc:
        return _error(f"{tool}: {exc}", "NOT_FOUND")
    except SessionQueryError as exc:
        return _error(f"{tool}: {exc}")
    except ValueError as exc:
        return _error(f"{tool}: {exc}")

    lines = [
        f"会话 {session_id} — {title}" if title else f"会话 {session_id}",
        f"目标事件（第 {seq} 条，完整未删节）：",
        "```json",
        _json.dumps(dict(window.target), ensure_ascii=False, indent=2),
        "```",
    ]
    before = [event for event in window.events if int(event.get("seq") or 0) < seq]
    after = [event for event in window.events if int(event.get("seq") or 0) > seq]
    if before:
        lines.extend(["", "之前的事件：", *(_neighbour_line(event) for event in before)])
    if after:
        lines.extend(["", "之后的事件：", *(_neighbour_line(event) for event in after)])
    return ToolOutput(text="\n".join(lines))


def _session_query_tools(kb_path: str) -> tuple[Tool, ...]:
    """会话查询家族的四把只读工具（`search_sessions` 之外的其余四个）；`build_kb_tools()` 末尾拼接。"""
    from memoria.services.agent.session.query import MAX_READ_WINDOW

    target_session = {
        "type": "string",
        "minLength": 1,
        "description": "目标会话 id（本地必填：没有「当前会话」身份可用）",
    }
    seq_parameter = {"type": "integer", "minimum": 0, "description": "目标事件序号 seq（从 0 起）"}
    return (
        Tool(
            name="session_event_search",
            description=(
                "在**指定会话**内按字面量检索事件（「上次那个结论是在第几步给的」这类问题用它）。"
                f"最多返回 {SESSION_EVENT_HITS_CAP} 条命中，超限时提示收窄查询；"
                "命中写成「会话 <id> 第 N 条」，**不要**写成 `文件:行号`（那是知识库文档的形状）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "session_id": target_session,
                    "query": {"type": "string", "minLength": 1, "description": "检索词（字面量匹配：空白弹性、大小写不敏感）"},
                    "seq_from": {"type": "integer", "minimum": 0, "description": "事件 seq 下界（含）"},
                    "seq_to": {"type": "integer", "minimum": 0, "description": "事件 seq 上界（含）"},
                    "time_from": {"type": "string", "description": "事件时间下界（含）：带时区限定的 ISO 8601，例如 2026-09-20T09:00:00+08:00"},
                    "time_to": {"type": "string", "description": "事件时间上界（含）：格式同 time_from"},
                    "event_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '事件类型白名单（子句内 OR），例如 ["user/message"]',
                    },
                },
                "required": ["session_id", "query"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _session_event_search(kb_path, arguments),
        ),
        Tool(
            name="session_trace",
            description=(
                "读取一个会话的**谱系**：祖先链（由近及远）与后代树。"
                "想看某个会话从哪来、有没有派生会话时用它。"
            ),
            parameters={
                "type": "object",
                "properties": {"session_id": target_session},
                "required": ["session_id"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _session_trace(kb_path, arguments),
        ),
        Tool(
            name="session_event_trace",
            description=(
                "读取一条事件的**替换关系**：被谁替换、替换链、以及它替换掉了哪些事件。"
                "想知道某个旧结论是否已被压缩/裁剪覆盖时用它。"
            ),
            parameters={
                "type": "object",
                "properties": {"session_id": target_session, "seq": seq_parameter},
                "required": ["session_id", "seq"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _session_event_trace(kb_path, arguments),
        ),
        Tool(
            name="session_event_read",
            description=(
                "读取一条事件的**完整未删节 JSON**，并可选给出前/后若干条相邻事件的摘要。"
                "需要精确原文（而不是检索片段）时用它。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "session_id": target_session,
                    "seq": seq_parameter,
                    "before": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": MAX_READ_WINDOW,
                        "description": f"额外摘要前多少条事件（默认 0，最多 {MAX_READ_WINDOW}）",
                    },
                    "after": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": MAX_READ_WINDOW,
                        "description": f"额外摘要后多少条事件（默认 0，最多 {MAX_READ_WINDOW}）",
                    },
                },
                "required": ["session_id", "seq"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _session_event_read(kb_path, arguments),
        ),
    )


# ── 引用板块（R 线）：只读「引用解析」+「引用审计」（2026-09-20；§6.18）──────────────────────
# 口径来源 = `docs/design/agent-capabilities.md` §6.5「引用完整性：让模型写的路径真的可用（P / V / L
# 三路线）」（该节 `agent-capabilities.md:447-481`；台账行 `docs/todo.md:265` 的 **AG07**，
# 与 `docs/design/dsh-agent-port.md:733` 的前置依赖同一份口径）。三条路线逐条落法：
#
#   **P**（提示词收窄语法）= 已由 `prompt.FILE_REFERENCE_SECTION`（`prompt.py:208-218`）承载
#       （要求引用取自工具回显的 canonical 路径），本块**不重复实现**；
#   **V**（输出后程序校验 + 库内清单分级收敛）= **本块实现** ——
#       V1 归一化：NFKC、剥 CJK 标点/引号包裹、去 `./` 前缀（`_reference_normalize()`）；
#       V2 分级收敛：精确 → 唯一 basename → 唯一后缀（`_reference_converge_file()`）；
#          **任一级命中 >1 即 `ambiguous` 并回候选，绝不猜**；
#       V3 回灌：`not_found` 当**普通结果**返回（「真实情况 + 下一步」），**不自动重试**；
#   **L**（改读时投影）= **已落地**（2026-09-20）⇒ 区间锚点（`x.md#L12-L30`）解析到**当前正文行**
#       并双向校验（起/末都存在、起 ≤ 止）：`ok`（含解析到的行范围 + 首末行摘要）/ `invalid`（倒置）/
#       `not_found`（越界）；仍**不把正文塞进结果**（投影只给行号与首末行，正文由 `read_document` 取）。
#
# §6.5 的「不要做」清单照办：不靠扩正则修跳转、不做模糊编辑距离自动改写（实体解析共识：误并比漏并更糟）、
# 不改写会话 JSONL / 事件日志、不为整库做路径枚举 schema（只在库内清单上分级收敛）。
#
# **本期只覆盖库内五类引用**：`@路径` / `@[label](dsh-session:…[#seq:…])` / `[[…]]` / `文件:行号` / `![](...)`。
# **仍明确不做**（写进工具描述，避免模型误以为能解）：① 块级引用（代码块 / 表格 / 公式 —— 需要新的稳定块
# 标识，属另一设计）；② 选区**文本**引用（`@路径#L12-L30` 只给行区间，正文仍由 `read_document` 取；
# 对话片段引用 `…#seq:<n>` 由 `session/reference.py` 在快照侧投影，不经本块）。
#
# 两把工具都**只读**：路径一律走允许根列表（`_read_roots()` / `_resolve_in_read_roots()`）、会话 id 一律走
# `session_file()`（非法 id 直接报错，fail-closed）、图片注册表只读不重建；工具体全程 `kb_read_only()` 守卫。
# 复用（不重写）：`link_resolver.scan_wikilinks` / `resolve_link_target` / `build_link_overrides`、
# `link_instances.is_line_attached` / `line_at_offset`、`session/reference.decode_session_uri`（与其 mention
# 正则，单一事实源）、`session/store.session_file`、`document.DocumentService` 的图片引用解析
# （`_parse_image_ref_url` / `diagnose_image_refs` / `_doc_image_names_from_body` / `_load_image_registry`）
# 与 `_resolve_scan_link_entry`、`storage.scanner.collect_md_files`。

#: 单条引用 token 的字符上限（超长 ⇒ `INVALID_ARGUMENTS`；防把整篇正文当 token 传进来）。
REFERENCE_MAX_CHARS = 512
#: 歧义候选一次最多列多少条。
REFERENCE_MAX_CANDIDATES = 10
#: `audit_references` 一次最多报多少条问题，同时是 `limit` 的上限（到顶给「已达上限」提示）。
REFERENCE_AUDIT_MAX_ISSUES = 100

#: 五类**库内**引用（本期范围）；`resolve_reference` 的 `kind` 省略即自动识别。
REFERENCE_KINDS = ("file", "session", "kp_link", "anchor", "image")

#: 解析状态词表（封闭集合）。`ambiguous` / `unsupported` 是两种「不猜」的诚实结果。
_REFERENCE_STATUS_LABELS = {
    "ok": "已解析",
    "not_found": "目标不存在",
    "ambiguous": "多目标歧义（未猜）",
    "invalid": "token 非法",
    "rejected": "越界拒绝",
    "unsupported": "本地不支持",
}

_REFERENCE_KIND_LABELS = {
    "file": "file（`@路径` 文件引用）",
    "session": "session（`dsh-session:` 会话引用）",
    "kp_link": "kp_link（`[[…]]` 知识点 / 链接）",
    "anchor": "anchor（`文件:行号` 锚点）",
    "image": "image（`![](...)` 图片引用）",
}

#: `@路径` 提及（语法逐字对齐前端 `agent-panel.js:125` 的 `MENTION_RE`：`@` 必须在行首或空白之后，
#: `@"含空格"`（引号可缺）与裸 token 两种形态；两个分支恰好命中其一）。
_FILE_MENTION_PATTERN = r'(?:^|\s)@(?:"([^"]*)"?|(\S+))'

#: `文件:行号` / 区间锚点（文件字符类对齐前端 `ANCHOR_RE`，`agent-panel.js:117`；另补 `#L12-L30` 形态：
#: 分隔符既可以是 `:` / `：`，也可以是 `#`；2026-09-20 起 `#` 形态两端可各带**可选列号** `C<列>`（1 起）。
#: 字符类里的 CJK 标点全用 `\u` 转义写，避免 `—～` 被 Python 解释成码点区间（JS 里的同类隐患）。
_ANCHOR_REF_PATTERN = (
    r"`?\"?'?"
    r"(?P<file>[^\s`\"'<>()\[\]#:：\uFF1A\uFF0C\u3001\u3002\uFF1B\uFF01\uFF1F\u300C\u300D\u300E\u300F"
    r"\u3010\u3011\uFF08\uFF09\u300A\u300B\u3008\u3009\u3014\u3015\u2026\u00B7\u2014\uFF5E]+?"
    r"\.(?:md|markdown))"
    r"(?P<sep>[:：]|#)\s*#?L?(?P<start>\d+)(?:C(?P<startcol>\d+))?"
    r"(?:\s*[-\u2013\u2014~]\s*#?L?(?P<end>\d+)(?:C(?P<endcol>\d+))?)?"
    r"`?\"?'?"
)

#: 图片引用括号内文本（与 `DocumentService.diagnose_image_refs()` 的扫描形状一致：`!\[…\]\(([^)]*)\)`
#: —— 比 `_IMG_REF_RE` 宽，能把「裸 URL 含空白」这类**不可注册**写法也取出来）。
_IMAGE_REF_PATTERN = r"!\[[^\]]*\]\(([^)]*)\)"

#: 本块全部检查名（`audit_references` 文本末尾一次性列出，均可由 `resolve_reference` 复现）。
_REFERENCE_AUDIT_CHECKS = (
    "file_reference.missing",
    "file_reference.ambiguous",
    "file_reference.outside_root",
    "session_reference.invalid_uri",
    "session_reference.invalid_id",
    "session_reference.session_not_found",
    "kp_link.unresolved_target",
    "kp_link.ambiguous_target",
    "kp_link.body_not_attached",
    "anchor.file_missing",
    "anchor.ambiguous_file",
    "anchor.line_out_of_range",
    "anchor.range_inverted",
    "anchor.outside_root",
    "image.missing",
    "image.unregistered",
    "image.not_registered",
)

#: V1 归一化要剥掉的包裹字符（引号 / 反引号 / 成对括号与 CJK 括注）。
_REFERENCE_WRAPPERS = "`\"'「」『』【】（）()《》〈〉〔〕[]"

#: V1 归一化里「路径到此为止」的终止字符：CJK 标点/成对括号之后的内容不属于路径
#: （`@a.md（说明）` 里的 `（说明）` 是正文标注，不是文件名）。与前端 `ANCHOR_RE` 的排除集同源。
#: **不含空白** —— `@"含 空格.md"` 的引号形态里空白是路径的一部分（上游 `formatFileMention` 同口径）。
_REFERENCE_TERMINATORS = "，。、；！？「」『』【】（）()《》〈〉〔〕…·\u2014\uFF5E"


def _ref_re(pattern: str) -> Any:
    """惰性编译引用正则（本模块顶层不导入 `re`，与 §6.17 同款做法）。"""
    import re

    return re.compile(pattern)


def _reference_normalize(raw: str) -> str:
    """V1 归一化（§6.5 落地顺序 1）：NFKC → 按终止字符截断 → 剥包裹标点 → `\\`→`/` → 去 `./` 前缀。

    只做 §6.5 列出的那一档零风险动作：**不做**编辑距离、不做模糊改写。
    """
    import unicodedata

    text = unicodedata.normalize("NFKC", str(raw or "")).strip()
    for index, char in enumerate(text):
        if char in _REFERENCE_TERMINATORS:
            text = text[:index]
            break
    text = text.strip(_REFERENCE_WRAPPERS).strip()
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _reference_rel_in_roots(kb_path: str, raw: str) -> str | None:
    """归一化后落到某个允许根内 ⇒ 回相对路径；空 / 上跳 / 越界 ⇒ None（fail-closed）。"""
    return _safe_rel_any(kb_path, _reference_normalize(raw))


def _reference_converge_file(
    kb_path: str,
    rel: str,
    *,
    files: Sequence[str] | None = None,
) -> tuple[str, str | None, list[str], str]:
    """V2 分级收敛：精确 → 唯一 basename → 唯一后缀；任一级 >1 即 `ambiguous`（**绝不猜**）。

    返回 `(status, 收敛目标, 候选, 命中级别)`。只比「库内清单」（`_walk_kb_files()`，即允许根 + VCS 排除），
    不做任何模糊匹配 —— 与 §6.5「模糊（尾部元素加权）」的**未采纳**部分一致：误并比漏并更糟。
    """
    inventory = list(files) if files is not None else _walk_kb_files(kb_path)
    if rel in inventory:
        return "ok", rel, [], "exact"
    base = rel.rsplit("/", 1)[-1]
    hits = [name for name in inventory if name.rsplit("/", 1)[-1] == base]
    if len(hits) == 1:
        return "ok", hits[0], [], "unique_basename"
    if len(hits) > 1:
        return "ambiguous", None, hits, "basename"
    suffix = "/" + rel
    hits = [name for name in inventory if name.endswith(suffix)]
    if len(hits) == 1:
        return "ok", hits[0], [], "unique_suffix"
    if len(hits) > 1:
        return "ambiguous", None, hits, "suffix"
    return "not_found", None, [], "none"


def _reference_result(
    kind: str,
    *,
    status: str,
    target: str = "",
    detail: str = "",
    reason: str = "",
    candidates: Sequence[str] = (),
    next_step: str = "",
) -> dict[str, Any]:
    """一次解析的结构化结果（渲染层只负责排版，不再判断语义）。"""
    return {
        "kind": kind,
        "status": status,
        "target": target,
        "detail": detail,
        "reason": reason,
        "candidates": [str(item) for item in candidates],
        "next": next_step,
    }


def _reference_render(token: str, result: Mapping[str, Any]) -> str:
    """把结构化结果排成模型可见文本（类型 / 归一化目标 / 状态 / 指向 / 候选 / 原因 / 下一步）。"""
    lines = [
        f"引用解析：{token}",
        f"- 类型：{_REFERENCE_KIND_LABELS[result['kind']]}",
        f"- 归一化目标：{result['target'] or '（未能归一化）'}",
        f"- 状态：{result['status']}（{_REFERENCE_STATUS_LABELS[result['status']]}）",
    ]
    if result["detail"]:
        lines.append(f"- 指向：{result['detail']}")
    candidates = list(result["candidates"])
    if candidates:
        shown = candidates[:REFERENCE_MAX_CANDIDATES]
        lines.append(f"- 候选（共 {len(candidates)} 个，最多列 {REFERENCE_MAX_CANDIDATES} 个）：")
        lines.extend(f"  {index}. {item}" for index, item in enumerate(shown, start=1))
        if len(candidates) > len(shown):
            lines.append(f"  …（还有 {len(candidates) - len(shown)} 个未列出）")
    if result["reason"]:
        lines.append(f"- 原因：{result['reason']}")
    if result["next"]:
        lines.append(f"- 建议下一步：{result['next']}")
    return "\n".join(lines)


def _reference_kp_candidate(item: Mapping[str, Any]) -> str:
    """知识点候选的一行描述（`{kp_id}（{name}）· {file}:{start_line}`）。"""
    kp_id = str(item.get("kp_id") or "")
    name = str(item.get("name") or kp_id)
    file = str(item.get("file") or "")
    line = item.get("start_line")
    location = f"{file}:{line}" if line else file
    return f"{kp_id}（{name}）· {location}" if kp_id else f"{name} · {location}"


# —— 五类引用的解析体 ——


def _resolve_file_reference(kb_path: str, token: str) -> dict[str, Any]:
    """`@路径`（上游 `context/file-reference` 语义）：尾斜杠 = 目录，其余按文件（V 分级收敛）。"""
    match = _ref_re(_FILE_MENTION_PATTERN).search(token)
    if match is None:
        return _reference_result(
            "file",
            status="invalid",
            reason="不是 `@路径` 形态（`@` 必须在一个 token 的开头：行首或空白之后）",
            next_step='传形如 `@docs/a.md` 或 `@"docs/A B.md"` 的 token',
        )
    raw = match.group(1) if match.group(1) is not None else (match.group(2) or "")
    if raw.startswith("["):
        return _reference_result(
            "file",
            status="invalid",
            target=raw,
            reason="这是 Markdown mention（`@[label](…)`）形态，不是文件引用",
            next_step="显式传 kind=\"session\"，或去掉 kind 让工具按标记自动识别",
        )
    normalized = _reference_normalize(raw)
    if not normalized:
        return _reference_result("file", status="invalid", reason="`@` 之后为空", next_step="补上库内相对路径")
    is_dir = normalized.endswith("/")
    rel = _reference_rel_in_roots(kb_path, normalized)
    if rel is None:
        return _reference_result(
            "file",
            status="rejected",
            target=normalized,
            reason="路径在允许根（知识库根）之外，或含上跳 `..` —— 工具面 fail-closed 拒绝",
            next_step="改用库内相对路径（`kb_overview` 可看全库文件清单）",
        )
    if is_dir:
        if not os.path.isdir(os.path.join(kb_path, rel)):
            return _reference_result(
                "file",
                status="not_found",
                target=normalized.rstrip("/") + "/",
                reason="库内没有该目录",
                next_step='用 `glob(pattern="**/*.md")` 或 `kb_overview` 核对真实目录名',
            )
        count = len(_walk_kb_files(kb_path, rel))
        return _reference_result(
            "file",
            status="ok",
            target=normalized.rstrip("/") + "/",
            detail=f"目录 {rel}/（其下 {count} 个文件）",
            next_step=f'glob(pattern="**/*.md", path="{rel}") 或 search_kb 检索目录内容',
        )

    status, target, candidates, matched = _reference_converge_file(kb_path, rel)
    if status == "ambiguous":
        return _reference_result(
            "file",
            status="ambiguous",
            target=rel,
            reason=f"库内有 {len(candidates)} 个同名 / 同后缀文件（{matched} 级命中 >1）—— 程序不猜",
            candidates=candidates,
            next_step="把候选里的完整相对路径原样复制过来再问一次",
        )
    if status != "ok" or not target:
        return _reference_result(
            "file",
            status="not_found",
            target=rel,
            reason="库内不存在该文件（精确 / 唯一 basename / 唯一后缀三级都未命中）",
            next_step='用 `glob(pattern="**/*.md")` 或 `kb_overview` 核对真实路径',
        )
    info = _kp_map_for_file(kb_path, target)
    _, target_lines = _read_body_lines(kb_path, target)
    converged = "" if matched == "exact" else f"（按唯一 {matched} 收敛：`{rel}` → `{target}`）"
    return _reference_result(
        "file",
        status="ok",
        target=target,
        detail=f"知识库文档 {target}（共 {len(target_lines)} 行，{len(info)} 个知识点）{converged}",
        next_step=f'read_document(path="{target}")',
    )


def _resolve_session_reference(kb_path: str, token: str) -> dict[str, Any]:
    """`dsh-session:` 会话引用：URI 走 `decode_session_uri()`，文件走 `session_file()`（fail-closed）。"""
    from memoria.services.agent.session.reference import _MENTION_RE, decode_session_uri
    from memoria.services.agent.session.store import session_file

    match = _MENTION_RE.search(token)
    if match is None:
        return _reference_result(
            "session",
            status="invalid",
            reason="不是会话引用形态（`@[label](dsh-session:…)` 或裸 `dsh-session:…`）",
            next_step="用前端「历史」页签里的「引用」按钮插入规范 token",
        )
    uri = match.group(2) if match.group(2) is not None else (match.group(3) or "")
    try:
        session_id = decode_session_uri(uri)
    except ValueError as exc:
        return _reference_result(
            "session",
            status="invalid",
            target=uri,
            reason=f"URI 非规范（`decode_session_uri()` 拒绝：{exc}）",
            next_step="重新用「历史」里的引用按钮生成 token（`dsh-session:` + 无填充 base64url(JSON)）",
        )
    try:
        full = session_file(kb_path, session_id)
    except ValueError as exc:
        return _reference_result(
            "session",
            status="rejected",
            target=session_id,
            reason=f"解码成功但会话 id 非法：{exc}",
            next_step="只接受 store 允许的 id 形状（字母数字与 `.` `_` `-`）",
        )
    if not os.path.isfile(full):
        return _reference_result(
            "session",
            status="not_found",
            target=session_id,
            reason="本库会话目录内没有该会话文件（会话按库分，不跨库）",
            next_step='用 `search_sessions` 找本库真实存在的会话 id',
        )
    title = _title_of(kb_path, session_id)
    detail = f"会话 `{session_id}`" + (f"（标题：{title}）" if title else "（无标题，可能尚未生成）")
    return _reference_result(
        "session",
        status="ok",
        target=session_id,
        detail=detail,
        next_step=f'session_event_read(session_id="{session_id}", seq=0) 或 search_sessions',
    )


def _resolve_kp_link_reference(kb_path: str, token: str) -> dict[str, Any]:
    """`[[…]]`：id / 文件名两路（`resolve_link_target()`）；**别名与挂接需文档上下文**，如实说明。"""
    from memoria.services.link_resolver import resolve_link_target, scan_wikilinks

    links = scan_wikilinks(token)
    if not links:
        return _reference_result(
            "kp_link",
            status="invalid",
            reason="不是 `[[…]]` 形态（宽正则 `\\[\\[([^\\]|#\\]]+)(?:#…)?(?:\\|…)?\\]\\]` 未命中）",
            next_step="传 `[[kp_id]]` / `[[kp_id#边型]]` / `[[kp_id|显示文字]]`",
        )
    link = links[0]
    target_id = link["target_id"]
    result = resolve_link_target(kb_path, target_id)
    status = str(result.get("status") or "")
    candidates = [_reference_kp_candidate(item) for item in result.get("candidates") or []]
    alias_note = "；别名（`links[].anchor_text` / 正文同标签）与「正文出现但未挂接」需要文档上下文，请对含该 token 的文档跑 `audit_references`"
    if status == "ok" and candidates:
        item = result["candidates"][0]
        return _reference_result(
            "kp_link",
            status="ok",
            target=target_id,
            detail=f"{_reference_kp_candidate(item)}（命中方式：{result.get('match') or 'kp_id'}）",
            next_step=f'read_kp(id="{item.get("kp_id") or target_id}")' + alias_note,
        )
    if status == "ambiguous":
        return _reference_result(
            "kp_link",
            status="ambiguous",
            target=target_id,
            reason=f"`by_id` 里有 {len(candidates)} 条同 id 记录（跨文件重复定义）—— 程序不猜",
            candidates=candidates,
            next_step="改用 `文件:行号` 锚点指定到具体那一处" + alias_note,
        )
    return _reference_result(
        "kp_link",
        status="not_found",
        target=target_id,
        reason=str(result.get("message") or "知识点 id 与文件 stem 都没命中"),
        next_step='用 `search_kb` 或 `kb_overview` 找真实 id / 文件名' + alias_note,
    )


def _resolve_anchor_reference(kb_path: str, token: str) -> dict[str, Any]:
    """`文件:行号` 锚点。单行与**区间**（`#L12-L30`，可选列号 `#L3C2-L5C7`）都解析到当前正文行并双向校验。"""
    text = token.strip()
    ranged = _at_range_parts(text)
    if ranged is not None:
        # 选区引用的规范 token `@路径#L12C5-L14C20` / `@"带空格 路径"#L12-L30`：剥掉 `@` 与引号后
        # 与 `文档#L…` 走**同一段**区间读时投影（含空格路径只能从这条入口进来）。
        return _anchor_range_result(kb_path, ranged[0], ranged[1], ranged[3], ranged[2], ranged[4])
    regex = _ref_re(_ANCHOR_REF_PATTERN)
    match = regex.fullmatch(text) or regex.search(text)
    if match is None:
        return _reference_result(
            "anchor",
            status="invalid",
            reason="不是 `文件:行号` 形态（文件需以 `.md` / `.markdown` 结尾，行号取十进制）",
            next_step="传形如 `neural-network.md:17`、`notes/a.md:L7` 或 `notes/a.md#L12-L30` 的 token",
        )
    start = int(match.group("start"))
    end_text = match.group("end")
    end = int(end_text) if end_text else None
    raw_file = match.group("file")
    if match.group("sep") == "#" and (match.group("startcol") is not None or match.group("endcol") is not None):
        # 列号只认 `#` 形态（`#L3C2-L5C7`）：`文件:3C2` 不是本块语法，绝不猜 ⇒ 与 `@路径#L…` 共用同一段投影
        return _anchor_range_result(
            kb_path,
            raw_file,
            start,
            end,
            int(match.group("startcol")) if match.group("startcol") is not None else None,
            int(match.group("endcol")) if match.group("endcol") is not None else None,
        )
    rel = _reference_rel_in_roots(kb_path, raw_file)
    display = f"{_reference_normalize(raw_file)}:{start}" + (f"-{end}" if end else "")
    if rel is None:
        return _reference_result(
            "anchor",
            status="rejected",
            target=display,
            reason="锚点路径在允许根之外或含上跳 `..` —— fail-closed 拒绝",
            next_step="改用库内相对路径（工具结果里回显的 canonical 路径）",
        )
    status, target, candidates, matched = _reference_converge_file(kb_path, rel)
    if status == "ambiguous":
        return _reference_result(
            "anchor",
            status="ambiguous",
            target=display,
            reason=f"锚点文件有 {len(candidates)} 个同名 / 同后缀候选（{matched} 级命中 >1）—— 不猜",
            candidates=candidates,
            next_step="用候选里的完整相对路径重写锚点",
        )
    if status != "ok" or not target:
        return _reference_result(
            "anchor",
            status="not_found",
            target=display,
            reason="锚点文件在库内不存在（精确 / 唯一 basename / 唯一后缀三级都未命中）",
            next_step='用 `glob(pattern="**/*.md")` 核对真实路径',
        )
    _, lines = _read_body_lines(kb_path, target)
    total = len(lines)
    if end is not None:
        # L 路线（**读时投影**，2026-09-20 落地；此前一律回 `unsupported`）：区间解析到**当前正文行**
        # 并双向校验 ⇒ `ok`（行范围 + 首末行摘要）/ `invalid`（倒置）/ `not_found`（越界）。
        # 实现落在文件末尾 `_anchor_range_result()`（与 `@路径#L12-L30` 入口共用同一段代码）。
        return _anchor_range_result(kb_path, raw_file, start, end)
    if start < 1 or start > total:
        return _reference_result(
            "anchor",
            status="not_found",
            target=display,
            reason=f"第 {start} 行超出 `{target}` 的正文范围（该文档正文共 {total} 行）",
            next_step=f'read_document(path="{target}") 取回真实行号（或按唯一 basename 收敛后的路径重试）',
        )
    snippet = lines[start - 1].strip()[:SNIPPET_CHARS]
    return _reference_result(
        "anchor",
        status="ok",
        target=display,
        detail=f"{target} 第 {start} 行：{snippet or '（该行为空行）'}",
        next_step=f'read_document(path="{target}", offset={start}, limit=1)',
    )


def _reference_image_registry(kb_path: str) -> tuple[dict[str, Any], bool]:
    """读 `.memoria/images/registry.json`（**只读**：缺失时返回 `({}, False)`，不重建、不落盘）。"""
    service = _readonly_document_service(kb_path)
    path = service._image_registry_path()
    if not path or not os.path.isfile(path):
        return {}, False
    return dict(service._load_image_registry().get("refs") or {}), True


def _resolve_image_reference(kb_path: str, token: str) -> dict[str, Any]:
    """`![](...)`：只覆盖 `.memoria/images/**`；校验存在性 + 注册规则可识别性 + registry 登记状态。"""
    from memoria.services.document import DocumentService
    from memoria.storage.constants import MEMORIA_DIR

    match = _ref_re(_IMAGE_REF_PATTERN).search(token)
    if match is None:
        return _reference_result(
            "image",
            status="invalid",
            reason="不是 `![](...)` 形态",
            next_step="传形如 `![](<.memoria/images/x.png>)` 的完整图片引用",
        )
    raw = match.group(1).strip()
    url, registrable = DocumentService._parse_image_ref_url(raw)
    if url is None:
        return _reference_result(
            "image",
            status="invalid",
            target=raw,
            reason="括号内取不到 URL",
            next_step="传形如 `![](<.memoria/images/x.png>)` 的完整图片引用",
        )
    norm = url[8:] if url.startswith("/files/") else url
    prefix = f"{MEMORIA_DIR}/images/"
    if not norm.startswith(prefix):
        return _reference_result(
            "image",
            status="unsupported",
            target=norm,
            reason="不是库内图片引用（本期只覆盖 `.memoria/images/**`；外链 / 其它目录不解析）",
            next_step="若确为库内图片，请写成 `.memoria/images/<文件名>`（含空格用尖括号包裹）",
        )
    name = norm[len(prefix) :].split("#", 1)[0].split("?", 1)[0]
    if not name or "/" in name or "\\" in name:
        return _reference_result(
            "image",
            status="invalid",
            target=norm,
            reason="图片名非法（必须落在 `.memoria/images/` 直下、不含子目录）",
            next_step="把图片放进 `.memoria/images/` 再引用",
        )
    rel = _reference_rel_in_roots(kb_path, norm)
    if rel is None:
        return _reference_result(
            "image",
            status="rejected",
            target=norm,
            reason="图片路径解析到允许根之外（含上跳或绝对路径）—— fail-closed 拒绝",
            next_step="改用库内 `.memoria/images/<文件名>`",
        )
    display = f".memoria/images/{name}"
    exists = os.path.isfile(os.path.join(kb_path, rel))
    refs, registry_present = _reference_image_registry(kb_path)
    if not registrable:
        return _reference_result(
            "image",
            status="invalid",
            target=display,
            detail=f"文件{'存在' if exists else '不存在'}",
            reason="裸 URL 含空白 ⇒ 图片注册规则（`_parse_image_ref_url()`）识别不到，"
            "会被当成「未引用」，保存时有被自动清理误删的风险",
            next_step=f"改写成尖括号形式：`![](<{norm}>)`",
        )
    if not exists:
        return _reference_result(
            "image",
            status="not_found",
            target=display,
            reason="`.memoria/images/` 下没有该文件",
            next_step="把图片导入该库（或修正文件名与扩展名）",
        )
    if not registry_present:
        detail = "文件存在；`registry.json` 缺失（注册表未生成，登记状态无法判定）"
    elif name in refs:
        detail = "文件存在；registry.json 已登记（引用方：" + "、".join(str(x) for x in (refs.get(name) or [])) + "）"
    else:
        detail = "文件存在；但 registry.json 的 refs 里没有它（注册表可能未重建）"
    return _reference_result(
        "image",
        status="ok",
        target=display,
        detail=detail,
        next_step='read_image(file_path="' + rel + '")（当前缺「多媒体眼睛」插件，只会回明确错误）',
    )


#: kind → 解析体（`resolve_reference` 的唯一分派表）。
_REFERENCE_RESOLVERS: dict[str, Any] = {
    "file": _resolve_file_reference,
    "session": _resolve_session_reference,
    "kp_link": _resolve_kp_link_reference,
    "anchor": _resolve_anchor_reference,
    "image": _resolve_image_reference,
}


def _detect_reference_kind(token: str) -> str | None:
    """按标记自动识别引用类型；识别不出回 None（调用方转成参数错误，绝不瞎猜）。"""
    from memoria.services.agent.session.reference import _MENTION_RE

    text = token.strip()
    if _MENTION_RE.search(text):
        return "session"
    if text.startswith("!["):
        return "image"
    if _at_range_parts(text) is not None:
        return "anchor"  # `@路径#L12-L30`（选区引用 token）：按**锚点**解，不按 `@路径` 文件引用
    if text.startswith("@"):
        return "file"
    if _ref_re(_ANCHOR_REF_PATTERN).fullmatch(text):
        return "anchor"
    if text.startswith("[["):
        return "kp_link"
    return None


def _resolve_reference(kb_path: str, reference: str, kind: str | None = None) -> ToolOutput:
    """`resolve_reference` 工具体：解析**一条**引用并回结构化结果文本（只读）。"""
    token = str(reference or "").strip()
    if not token:
        return _error("resolve_reference: reference 不能为空")
    if len(token) > REFERENCE_MAX_CHARS:
        return _error(
            f"resolve_reference: reference 过长（{len(token)} 字符 > 上限 {REFERENCE_MAX_CHARS}）"
            "—— 一次只解析一条引用 token"
        )
    if kind is not None and str(kind).strip():
        key = str(kind).strip().lower()
        if key not in REFERENCE_KINDS:
            return _error(
                f"resolve_reference: 未知 kind {kind!r}（可选 {'、'.join(REFERENCE_KINDS)}；省略即按标记自动识别）"
            )
    else:
        detected = _detect_reference_kind(token)
        if detected is None:
            return _error(
                f"resolve_reference: 无法识别引用类型：{token!r} —— 需是 `@路径`、`@[label](dsh-session:…)`、"
                "`[[id]]`、`文件:行号`、`![](...)` 之一，或用 kind 显式指定"
            )
        key = detected
    with kb_read_only(kb_path):
        result = _REFERENCE_RESOLVERS[key](kb_path, token)
    return ToolOutput(text=_reference_render(token, result))


# —— 引用审计 ——


def _audit_issue(
    check: str,
    severity: str,
    rel: str,
    line: int | None,
    target: str,
    problem: str,
) -> dict[str, Any]:
    """一条审计问题：类型（检查名）/ 位置（文件:行）/ 目标 / 问题 / 严重级。"""
    return {
        "check": check,
        "severity": severity,
        "file": rel,
        "line": line,
        "target": target,
        "problem": problem,
    }


def _audit_preview(values: Sequence[str]) -> str:
    """候选短清单（审计行内展示，最多 3 个）。"""
    shown = [str(item) for item in values[:3]]
    text = "、".join(f"`{item}`" for item in shown)
    return text + (f" 等 {len(values)} 个" if len(values) > len(shown) else "")


def _audit_document(
    kb_path: str,
    rel: str,
    *,
    service: Any,
    inventory: Sequence[str],
    image_problems: Mapping[str, list[dict[str, Any]]],
    registry_refs: Mapping[str, Any],
    registry_present: bool,
) -> list[dict[str, Any]]:
    """单篇文档的五类引用扫描（只读）；返回问题清单（未截断，由调用方做上限）。"""
    from memoria.services.agent.session.reference import _MENTION_RE, decode_session_uri
    from memoria.services.agent.session.store import session_file
    from memoria.services.document import DocumentService
    from memoria.services.link_instances import is_line_attached, line_at_offset
    from memoria.services.link_resolver import (
        build_link_overrides,
        resolve_link_target,
        scan_wikilinks,
        wikilink_label,
    )
    from memoria.storage.constants import MEMORIA_DIR
    from memoria.storage.sidecar import load_sidecar_for_md

    body, lines = _read_body_lines(kb_path, rel)
    issues: list[dict[str, Any]] = []

    def add(check: str, severity: str, line: int, target: str, problem: str) -> None:
        issues.append(_audit_issue(check, severity, rel, line, target, problem))

    # ① `@路径`（跳过会话 mention 与 `@[label]` 形态：那些由 ② 负责）
    for match in _ref_re(_FILE_MENTION_PATTERN).finditer(body):
        token_text = match.group(1) if match.group(1) is not None else (match.group(2) or "")
        if token_text.startswith("[") or token_text.startswith("dsh-session:"):
            continue
        if _at_range_parts("@" + token_text) is not None or _at_range_parts(
            "@" + token_text.rstrip("。，、；：！？）】」』》”’)]}")
        ) is not None:
            continue  # `@路径#L12-L30`（选区区间引用）由 ④ 锚点扫描负责（含倒置 / 越界）
        raw = _reference_normalize(token_text)
        if not raw:
            continue
        at = body.find("@", match.start(), match.end())
        line = line_at_offset(body, at if at >= 0 else match.start())
        target = f"@{raw}"
        if raw.endswith("/"):
            rel_dir = _reference_rel_in_roots(kb_path, raw)
            if rel_dir is None:
                add("file_reference.outside_root", "error", line, target, "路径在允许根之外或含上跳 `..`，fail-closed 拒绝")
            elif not os.path.isdir(os.path.join(kb_path, rel_dir)):
                add("file_reference.missing", "error", line, target, "库内没有该目录")
            continue
        rel_target = _reference_rel_in_roots(kb_path, raw)
        if rel_target is None:
            add("file_reference.outside_root", "error", line, target, "路径在允许根之外或含上跳 `..`，fail-closed 拒绝")
            continue
        status, _converged, candidates, _matched = _reference_converge_file(kb_path, rel_target, files=inventory)
        if status == "not_found":
            add("file_reference.missing", "error", line, target, "库内不存在该文件（精确 / 唯一 basename / 唯一后缀三级都未命中）")
        elif status == "ambiguous":
            add(
                "file_reference.ambiguous",
                "warning",
                line,
                target,
                f"多义：{_audit_preview(candidates)}（程序不猜，用完整相对路径重写）",
            )

    # ② 会话引用（`@[label](dsh-session:…)` 与裸 `dsh-session:`）
    for match in _MENTION_RE.finditer(body):
        uri = match.group(2) if match.group(2) is not None else (match.group(3) or "")
        line = line_at_offset(body, match.start())
        try:
            session_id = decode_session_uri(uri)
        except ValueError:
            add("session_reference.invalid_uri", "error", line, uri, "URI 非规范（`decode_session_uri()` 拒绝）")
            continue
        try:
            full = session_file(kb_path, session_id)
        except ValueError as exc:
            add("session_reference.invalid_id", "error", line, session_id, f"会话 id 非法：{exc}")
            continue
        if not os.path.isfile(full):
            add(
                "session_reference.session_not_found",
                "warning",
                line,
                session_id,
                "本库会话目录内没有该会话文件（会话按库分，不跨库）",
            )

    # ③ `[[…]]`：目标可解析性 + 是否挂接（别名走 sidecar + 正文同标签的 overrides）
    sidecar = load_sidecar_for_md(os.path.join(kb_path, rel), kb_path)
    overrides = build_link_overrides(sidecar, body)
    for link in scan_wikilinks(body):
        raw = str(link["raw"])
        target_id = str(link["target_id"])
        label = wikilink_label(target_id, link.get("display"))
        line = line_at_offset(body, int(link["start"]))
        targets = [str(item) for item in (overrides.get(label) or overrides.get(target_id) or [])]
        if len(targets) > 1:
            add("kp_link.ambiguous_target", "warning", line, raw, f"别名「{label}」指向多个目标：{_audit_preview(targets)}（不猜）")
        elif len(targets) == 1:
            resolved = resolve_link_target(kb_path, targets[0])
            if resolved.get("status") != "ok":
                add("kp_link.unresolved_target", "warning", line, raw, f"路由目标 `{targets[0]}` 无法解析（知识点与文件都没命中）")
        else:
            resolved = resolve_link_target(kb_path, target_id)
            if resolved.get("status") == "ambiguous":
                candidates = [_reference_kp_candidate(item) for item in resolved.get("candidates") or []]
                add("kp_link.ambiguous_target", "warning", line, raw, f"`by_id` 内多条同 id 记录：{_audit_preview(candidates)}（不猜）")
            elif resolved.get("status") != "ok":
                add("kp_link.unresolved_target", "warning", line, raw, f"知识点 id 与文件 stem 都没命中：`{target_id}`")
        entry = service._resolve_scan_link_entry(sidecar, label) or service._resolve_scan_link_entry(sidecar, target_id)
        if not is_line_attached(entry, line, body, lines):
            add("kp_link.body_not_attached", "warning", line, raw, "正文出现但未挂接（sidecar `instances` / `excluded` 里没有本行）")

    # ④ `文件:行号` 锚点（跳过 URL 里的 `…/x.md:3` 与 `@a.md:3` 的 `@` 形态：前一个字符是 `/` `:`，或文件段以 `@` 开头）
    for match in _ref_re(_ANCHOR_REF_PATTERN).finditer(body):
        if match.start() > 0 and body[match.start() - 1] in "/:":
            continue
        start = int(match.group("start"))
        end_text = match.group("end")
        end = int(end_text) if end_text else None
        raw_file = match.group("file")
        col_only = match.group("sep") == "#" and match.group("startcol") is not None
        if raw_file.startswith("@"):
            if end is None and not col_only:
                continue  # `@a.md:3` / `@a.md#L3`：文件引用类（① 负责），保持既有跳过
            raw_file = raw_file.lstrip("@")  # `@路径#L12-L30`（选区引用 token）：剥 `@` 后按锚点校验
        # 列号只认 `#` 形态（`#L3C2-L5C7`）；`文件:3C2` 不是本块语法 ⇒ 当作无列（绝不猜）
        has_col = match.group("sep") == "#" and (
            match.group("startcol") is not None or match.group("endcol") is not None
        )
        start_col = int(match.group("startcol")) if has_col and match.group("startcol") is not None else None
        end_col = int(match.group("endcol")) if has_col and match.group("endcol") is not None else None
        line = line_at_offset(body, match.start())
        target = f"{raw_file}:{start}" + (f"-{end}" if end else "")
        if start_col is not None or end_col is not None:
            target = f"{raw_file}#L{start}" + (f"C{start_col}" if start_col is not None else "")
            if end is not None:
                target += f"-L{end}" + (f"C{end_col}" if end_col is not None else "")
        rel_target = _reference_rel_in_roots(kb_path, raw_file)
        if rel_target is None:
            add("anchor.outside_root", "error", line, target, "锚点路径在允许根之外或含上跳 `..`，fail-closed 拒绝")
            continue
        status, converged, candidates, _matched = _reference_converge_file(kb_path, rel_target, files=inventory)
        if status == "ambiguous":
            add("anchor.ambiguous_file", "warning", line, target, f"锚点文件多义：{_audit_preview(candidates)}（不猜）")
            continue
        if status != "ok" or not converged:
            add("anchor.file_missing", "warning", line, target, "锚点文件在库内不存在（精确 / 唯一 basename / 唯一后缀三级都未命中）")
            continue
        target_lines = _read_body_lines(kb_path, converged)[1]
        line_count = len(target_lines)
        if end is not None and end < start:
            # 区间**倒置**（2026-09-20 起可校验：读时投影落地后才拿得到两端行空间）
            add(
                "anchor.range_inverted",
                "warning",
                line,
                target,
                f"区间锚点倒置：起点 L{start} 在终点 L{end} 之后（区间须 `#L<起>-L<止>` 且起 ≤ 止）",
            )
            continue
        if end is not None and end == start and start_col is not None and end_col is not None and end_col < start_col:
            # 列区间**倒置**（同一行内起列 > 止列；复现路径 = `resolve_reference` 的 `invalid`）
            add(
                "anchor.range_inverted",
                "warning",
                line,
                target,
                f"列区间倒置：同行起点第 {start_col} 列在终点第 {end_col} 列之后（同行内起列须 ≤ 止列）",
            )
            continue
        if start < 1 or start > line_count or (end is not None and end > line_count):
            beyond = start if (start < 1 or start > line_count) else end
            add(
                "anchor.line_out_of_range",
                "warning",
                line,
                target,
                f"第 {beyond} 行超出 `{converged}` 的正文范围（共 {line_count} 行）",
            )
            continue
        for at_line, at_col in ((start, start_col), (end if end is not None else start, end_col)):
            if at_col is None:
                continue
            length = len(target_lines[at_line - 1]) if 1 <= at_line <= line_count else 0
            if at_col < 1 or at_col > length + 1:
                # 列越界（复用 `anchor.line_out_of_range` 这一检查名：复现路径 = `resolve_reference` 的 `not_found`）
                add(
                    "anchor.line_out_of_range",
                    "warning",
                    line,
                    target,
                    f"第 {at_line} 行第 {at_col} 列超出（该行共 {length} 个字符，合法列 1..{length + 1}）",
                )
                break

    # ⑤ 图片：注册规则识别性 / 文件存在性（复用 `diagnose_image_refs()` 的口径）+ registry 登记状态
    for item in image_problems.get("unregistered") or []:
        add(
            "image.unregistered",
            "error",
            int(item.get("line") or 0),
            str(item.get("src") or ""),
            "裸 URL 含空白 ⇒ 图片注册规则识别不到（保存时可能被当作未引用清理）；改成 `![](<…>)` 尖括号形式",
        )
    for item in image_problems.get("missing") or []:
        add(
            "image.missing",
            "error",
            int(item.get("line") or 0),
            str(item.get("src") or ""),
            f"引用的图片不在 `.memoria/images/`：`{item.get('url')}`",
        )
    prefix = f"{MEMORIA_DIR}/images/"
    if registry_present:
        for match in _ref_re(_IMAGE_REF_PATTERN).finditer(body):
            url, registrable = DocumentService._parse_image_ref_url(match.group(1).strip())
            if not url or not registrable:
                continue  # 不可注册 / 取不到 URL 的写法由 `image.unregistered` 负责，不重复报
            norm = url[8:] if url.startswith("/files/") else url
            if not norm.startswith(prefix):
                continue
            name = norm[len(prefix) :].split("#", 1)[0].split("?", 1)[0]
            if not name or "/" in name or name in registry_refs:
                continue
            if not os.path.isfile(os.path.join(kb_path, norm)):
                continue  # 文件本身就不存在：由 `image.missing` 报，登记状态无意义
            add(
                "image.not_registered",
                "warning",
                line_at_offset(body, match.start()),
                match.group(0),
                f"`.memoria/images/{name}` 不在 `registry.json` 的 refs 里（注册表可能未重建）",
            )
    return issues


def _audit_references(kb_path: str, path: Any = None, limit: int = REFERENCE_AUDIT_MAX_ISSUES) -> ToolOutput:
    """`audit_references` 工具体：按文档扫五类引用，回问题清单（类型/位置/目标/问题/严重级/检查名）。"""
    from memoria.storage.scanner import collect_md_files

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= REFERENCE_AUDIT_MAX_ISSUES:
        return _error(f"audit_references: limit 必须是 1..{REFERENCE_AUDIT_MAX_ISSUES} 的整数")

    rel_filter: str | None = None
    if path is not None and str(path).strip():
        rel_filter = _safe_rel(kb_path, str(path))
        if rel_filter is None:
            return _error("audit_references: path 必须是工作区（允许根）内的相对 .md 路径（不得上跳）")
        if not os.path.isfile(os.path.join(kb_path, rel_filter)):
            return _error(f"audit_references: 文档不存在：{rel_filter}", "NOT_FOUND")

    files = [rel_filter] if rel_filter else collect_md_files(kb_path)
    shown: list[dict[str, Any]] = []
    total = 0
    with kb_read_only(kb_path):
        service = _readonly_document_service(kb_path)
        inventory = _walk_kb_files(kb_path)
        registry_refs, registry_present = _reference_image_registry(kb_path)
        diagnosed = service.diagnose_image_refs() or {}
        per_doc: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for group in ("unregistered", "missing"):
            for item in diagnosed.get(group) or []:
                per_doc.setdefault(str(item.get("doc") or ""), {}).setdefault(group, []).append(item)
        for rel in files:
            found = _audit_document(
                kb_path,
                rel,
                service=service,
                inventory=inventory,
                image_problems=per_doc.get(rel) or {},
                registry_refs=registry_refs,
                registry_present=registry_present,
            )
            for issue in found:
                total += 1
                if len(shown) < limit:
                    shown.append(issue)

    scope = f"指定文档 `{rel_filter}`" if rel_filter else f"全库 {len(files)} 篇 .md"
    if not shown:
        return ToolOutput(text=f"引用审计：扫描 {scope}，未发现引用问题。")
    errors = sum(1 for item in shown if item["severity"] == "error")
    warnings = len(shown) - errors
    lines = [f"引用审计：扫描 {scope}，发现 {total} 个引用问题（已列 {len(shown)} 条：error {errors} / warning {warnings}）。"]
    if total > len(shown):
        lines.append(f"（已达上限 {limit} 条：还有 {total - len(shown)} 条未列出；请用 `path` 参数收窄到单篇文档）")
    for item in shown:
        where = f"{item['file']}:{item['line']}" if item["line"] else str(item["file"])
        lines.append(f"- [{item['severity']}] {item['check']} @ {where} 目标 {item['target']}：{item['problem']}")
    lines.append("")
    lines.append("检查名（可用 resolve_reference 逐个复现）：" + " / ".join(_REFERENCE_AUDIT_CHECKS))
    return ToolOutput(text="\n".join(lines))


def _reference_tools(kb_path: str) -> tuple[Tool, ...]:
    """引用板块（R 线）两把**只读**工具；`build_kb_tools()` 末尾拼接（§6.18）。"""

    def _bound_resolve(arguments: Mapping[str, Any]) -> ToolOutput:
        raw_kind = arguments.get("kind")
        kind = str(raw_kind) if raw_kind is not None else None
        return _resolve_reference(kb_path, str(arguments.get("reference") or ""), kind)

    def _bound_audit(arguments: Mapping[str, Any]) -> ToolOutput:
        limit = _positive_int(arguments.get("limit"), REFERENCE_AUDIT_MAX_ISSUES)
        if limit is None or limit > REFERENCE_AUDIT_MAX_ISSUES:
            return _error(f"audit_references: limit 必须是 1..{REFERENCE_AUDIT_MAX_ISSUES} 的整数")
        return _audit_references(kb_path, arguments.get("path"), limit)

    return (
        Tool(
            name="resolve_reference",
            description=(
                "解析**一条**库内引用，回结构化结果：类型 / 归一化目标 / 是否存在 / 指向什么 / 歧义候选 / 建议下一步。"
                "覆盖五类：`@相对路径`（含 `@\"带空格\"` 与目录尾斜杠）、`@[label](dsh-session:…[#seq:…])`、`[[知识点]]`、"
                "`文件:行号`（含行区间 `文件#L12-L30`）、`![](...)`（`.memoria/images/**`）。"
                "多目标一律判 `ambiguous` 并回候选（**不猜**）；行区间解析到**当前正文行**并校验两端"
                "（倒置 ⇒ `invalid`；越界 ⇒ `not_found`），正文仍要自己去 `read_document` 读；"
                "**不支持**块级引用（代码块 / 表格 / 公式）。写回答前可先核对自己的引用是否可用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "minLength": 1,
                        "description": "一条引用 token 的原文（含 `@` / `[[…]]` / `![]` / `文件:行号` 标记）",
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(REFERENCE_KINDS),
                        "description": "可选：强制按该类引用解析（省略即按标记自动识别）",
                    },
                },
                "required": ["reference"],
                "additionalProperties": False,
            },
            handler=_bound_resolve,
        ),
        Tool(
            name="audit_references",
            description=(
                "审计库内文档的引用完整性，逐条回「检查名 / 位置（文件:行）/ 目标 / 问题 / 严重级」。"
                "默认扫全库 `.md`，可用 `path` 收窄到单篇。检查名与 `resolve_reference` 一一对应（可复现）。"
                f"一次最多报 {REFERENCE_AUDIT_MAX_ISSUES} 条（到顶会提示收窄）。只读，不改任何文件。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "可选：只审计知识库内该篇 .md（默认全库）"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": REFERENCE_AUDIT_MAX_ISSUES,
                        "description": f"最多列出多少条问题（默认且最多 {REFERENCE_AUDIT_MAX_ISSUES}）",
                    },
                },
                "additionalProperties": False,
            },
            handler=_bound_audit,
        ),
    )


# ── 行区间（L 路线：读时投影）＋ 选区引用 token（2026-09-20；§6.20）───────────────────────────
# 用户报障：「内容显示区可以拖拽选取加入对话了，但实际写入对话的仍然只是 `@文件名`，根本没有标出
# 对应内容的源码位置」。本轮按 AG07 已定的 **L 路线（读时投影）** 落地两块：
#   ① 前端写出规范 token `@路径#L12-L30`（含空格 `@"路径"#L12-L30`，单行 `#L12`）；
#   ② 本模块把该 token / `文档#L12-L30` 解析到**当前正文行**并双向校验（起/末存在、起 ≤ 止）。
# **投影口径**：只回「解析到的行范围 + 首末行摘要」——**不把区间正文塞进结果**（正文仍由模型自己
#   `read_document(offset, limit)` 取），与 §6.5「只允许读取时投影形态」一致；`#L` 语法**只有**
#   `#L<起>C<起列>?-L<止>C<止列>?` / `#L<行>C<列>?`（列可只写一端）两种，不发明第三种（P 收窄语法的"保守"要求）。
# 整块追加在文件末尾 ⇒ 上方既有 `file:line` 锚点只受前面几处**等量/近似等量**改写影响（见本轮报告）。

#: 选区引用的规范 token：`@路径#L12C5-L14C20` / `@路径#L12C5` / `@路径#L12-L30` / `@路径#L12`
#: / `@"含 空格"#L12-L30`。两端各为 `L<行>` 或 `L<行>C<列>`（列 1 起，**可只写一端** ⇒ 缺列=行首/行末）；
#: `@` 后允许上游同款的成对引号（`formatMention` 口径）。**不发明第三种分隔符**（P 收窄语法的保守要求）。
_AT_RANGE_PATTERN = (
    r"`?\"?'?@(?:\"(?P<qpath>[^\"]*)\"|(?P<path>[^\s`\"']+?))"
    r"#L(?P<from>\d+)(?:C(?P<fromcol>\d+))?"
    r"(?:\s*[-\u2013\u2014~]\s*L?(?P<to>\d+)(?:C(?P<tocol>\d+))?)?"
    r"`?\"?'?"
)


def _at_range_parts(raw: str) -> tuple[str, int, int | None, int | None, int | None] | None:
    """`@路径#L12C5-L14C20`（列号可缺；单行 `#L12` / `#L12C5`；含空格 `@"…"#L12-L30`）
    ⇒ `(路径原文, 起行, 起列或 None, 止行或 None, 止列或 None)`。

    路径**不在这里归一化或校验**（是否库内由调用方走允许根 + 分级收敛）；不匹配回 `None` ——
    识别不出就交给其它引用类型，**绝不猜**。列的合法性（越界 / 倒置）由 `_anchor_range_result()` 校验。
    """
    match = _ref_re(_AT_RANGE_PATTERN).fullmatch(str(raw or "").strip())
    if match is None:
        return None
    path = match.group("qpath") if match.group("qpath") is not None else (match.group("path") or "")
    to_text = match.group("to")
    from_col = match.group("fromcol")
    to_col = match.group("tocol")
    return (
        path,
        int(match.group("from")),
        int(from_col) if from_col is not None else None,
        int(to_text) if to_text is not None else None,
        int(to_col) if to_col is not None else None,
    )


def _anchor_range_result(
    kb_path: str,
    raw_file: str,
    start: int,
    end: int | None,
    start_col: int | None = None,
    end_col: int | None = None,
) -> dict[str, Any]:
    """`文档#L12C5-L14C20`（含选区 token `@路径#L…`）的**行 / 列区间读时投影**（L 路线，2026-09-20）。

    行号空间 = `_read_body_lines()` 剥掉 frontmatter 的**正文行**（与 `read_document` 同一口径）。
    列号 = **1 起的字符位置**（caret 语义：行首 = 1，行末 caret = 行长 + 1）⇒ 合法列 `1..len+1`；
    缺列 = 「行首 / 行末」语义（不猜具体列）。`end is None` 即单行锚点（无列时结果与既有单行口径逐字一致）。
    返回 `_reference_result(...)`：
      `rejected`（路径越界）/ `ambiguous` / `not_found`（文件级）→ `invalid`（行 / 列倒置）
      → `not_found`（行 / 列越界）→ `ok`（起止 + 首末行摘要）。**不含正文**。
    """
    rel = _reference_rel_in_roots(kb_path, raw_file)
    plain = start_col is None and end_col is None
    display = (
        f"{_reference_normalize(raw_file)}:{start}" + (f"-{end}" if end is not None else "")
        if plain
        else _range_col_display(raw_file, start, start_col, end, end_col)
    )
    if rel is None:
        return _reference_result(
            "anchor",
            status="rejected",
            target=display,
            reason="锚点路径在允许根之外或含上跳 `..` —— fail-closed 拒绝",
            next_step="改用库内相对路径（工具结果里回显的 canonical 路径）",
        )
    status, target, candidates, matched = _reference_converge_file(kb_path, rel)
    if status == "ambiguous":
        return _reference_result(
            "anchor",
            status="ambiguous",
            target=display,
            reason=f"锚点文件有 {len(candidates)} 个同名 / 同后缀候选（{matched} 级命中 >1）—— 不猜",
            candidates=candidates,
            next_step="用候选里的完整相对路径重写锚点",
        )
    if status != "ok" or not target:
        return _reference_result(
            "anchor",
            status="not_found",
            target=display,
            reason="锚点文件在库内不存在（精确 / 唯一 basename / 唯一后缀三级都未命中）",
            next_step='用 `glob(pattern="**/*.md")` 核对真实路径',
        )
    _, lines = _read_body_lines(kb_path, target)
    total = len(lines)
    if end is not None and end < start:
        return _reference_result(
            "anchor",
            status="invalid",
            target=display,
            reason=f"行区间倒置：起点 L{start} 在终点 L{end} 之后（区间须写成 `#L<起>-L<止>` 且起 ≤ 止）",
            next_step=f"改写成 `{target}#L{end}-L{start}`，或退回单行锚点 `{target}:{start}`",
        )
    if end is not None and end == start and start_col is not None and end_col is not None and end_col < start_col:
        return _reference_result(
            "anchor",
            status="invalid",
            target=display,
            reason=f"列区间倒置：同行起点第 {start_col} 列在终点第 {end_col} 列之后（同行内起列须 ≤ 止列）",
            next_step=f"改写成 `{target}#L{start}C{end_col}-L{start}C{start_col}`，或退回单列锚点",
        )
    last_line = start if end is None else end
    if start < 1 or last_line > total:
        beyond = start if (start < 1 or start > total) else last_line
        return _reference_result(
            "anchor",
            status="not_found",
            target=display,
            reason=f"第 {beyond} 行超出 `{target}` 的正文范围（该文档正文共 {total} 行）",
            next_step=f'read_document(path="{target}") 取回真实行号（或按唯一 basename 收敛后的路径重试）',
        )
    for line_no, col in ((start, start_col), (last_line, end_col)):
        if col is None:
            continue
        length = len(lines[line_no - 1])
        if col < 1 or col > length + 1:
            return _reference_result(
                "anchor",
                status="not_found",
                target=display,
                reason=f"第 {line_no} 行第 {col} 列超出（该行共 {length} 个字符，合法列 1..{length + 1}）",
                next_step=f'read_document(path="{target}", offset={line_no}, limit=1) 取回该行后按真实字符数重写列号',
            )
    if end is None:
        snippet = lines[start - 1].strip()[:SNIPPET_CHARS]
        where = f"第 {start} 行" if start_col is None else f"第 {start} 行第 {start_col} 列"
        return _reference_result(
            "anchor",
            status="ok",
            target=display,
            detail=f"{target} {where}：{snippet or '（该行为空行）'}",
            next_step=f'read_document(path="{target}", offset={start}, limit=1)',
        )
    first = lines[start - 1].strip()[:SNIPPET_CHARS]
    last = lines[end - 1].strip()[:SNIPPET_CHARS]
    if plain:
        detail = f"{target} 第 {start}-{end} 行（{end - start + 1} 行）："
    else:
        start_txt = str(start_col) if start_col is not None else "行首"
        end_txt = str(end_col) if end_col is not None else "行末"
        detail = f"{target} 起 {start}:{start_txt} → 止 {end}:{end_txt}（{end - start + 1} 行）："
    return _reference_result(
        "anchor",
        status="ok",
        target=display,
        detail=detail + f"首行 {first or '（空行）'} / 末行 {last or '（空行）'}",
        next_step=f'read_document(path="{target}", offset={start}, limit={end - start + 1})',
    )


def _range_col_display(
    raw_file: str, start: int, start_col: int | None, end: int | None, end_col: int | None
) -> str:
    """列号形态的目标串 = 与 token 同拼写（`a.md#L3C2-L5C7`）；无列时由调用方沿用既有 `:2-4` 口径。"""
    head = _reference_normalize(raw_file)
    out = f"{head}#L{start}" + (f"C{start_col}" if start_col is not None else "")
    if end is not None:
        out += f"-L{end}" + (f"C{end_col}" if end_col is not None else "")
    return out


# ── W 线第一步：**提议**工具（M3a 工具面；2026-09-20）────────────────────────────────────────
# 口径：`agent-capabilities.md` §2.3 第 1 步「propose = 模型调用写工具 ⇒ **只产 plan、不落盘**；
# 提议卡片 = `intent` + `preview_plan()` 算出的影响文件/行」。真正的写闸门在人确认那一步：
# 对话栏确认卡（`js/plan-confirm.js`）→ `agent_plan_apply`（写前备份 → 原语 → 审计 → 可撤销）。
#
# **为什么声明 `read_only=True`**（与设计稿的一处偏差，如实登记）：`registry.Tool.read_only` 的定义是
# 「该工具**不改动知识库**」（`tools/registry.py:106`）。本工具只做三件事：① 结构/语义校验
# ② dry-run（整段由 `kb_read_only()` 包裹 ⇒ 连可再生缓存都不落库）③ 把 plan 排进**进程内信箱**
# 给前端取走 —— 一个字节都不落盘，字面成立。设计稿那句「写工具声明 `read_only=False` ⇒ 必过审批」
# 假定的是"工具 = 落盘那一步"；本架构把落盘推到人手确认之后，**审批面没有被放宽**
# （`DefaultApprovalPolicy` 对任何 `read_only=False` 工具照旧一律拒绝，本轮未改它一行）。
# M3b 的真写原语工具仍须 `read_only=False` 并走审批。
#
# 信封里的 `v` / `txid` / `op_id` 由**程序**填（模型只给 `intent` + `ops`）：`txid` 有严格形态
# （`plan.TXID_RE`）、`op_id` 要求 plan 内唯一 —— 交给模型最易错，且错了也帮不上它。
# **整块追加在文件末尾** ⇒ 上方既有 `file:line` 锚点零漂移。

#: 提议工具的稳定名（提示词门控与前端都认它；**只增不改**）
PROPOSE_TOOL_NAME = "propose_write"

#: 计划没过校验/试算时的错误码：让模型按 `op_id` **重写整批**再提（而不是逐条打补丁）
INVALID_PLAN_CODE = "INVALID_PLAN"

#: 进程内信箱 `{库根绝对路径: [plan, …]}`；RPC `agent_plan_pending` 取走即清空
#  （**不落盘**：进程重启即丢。提议本来就是"等人确认"的瞬时物，不是事实源）
_PROPOSALS: dict[str, list[dict[str, Any]]] = {}


def take_proposals(kb_path: str) -> list[dict[str, Any]]:
    """取走某库**已提议但尚未展示**的 plan（取走即清空；没有就回空表）。"""
    return _PROPOSALS.pop(os.path.abspath(kb_path or ""), [])


class _ValidationService:
    """给 plan 校验用的**最小只读服务**：只提供 `kb_path`，方法**借用 `DocumentService` 的实现**。

    为什么不直接 `DocumentService(kb_path=…)`（本模块 docstring 第 2 条已定此口径）：
    其 `__post_init__` 会走 `set_kb_path()` ⇒ 写库引导 + `remember_last_kb_path()` 改用户的
    `config/ui-settings.json`。在"每次提议"的热路径上既重又有副作用。这里**只借实现、不建实例**
    （`check_kp_id` 的唯一依赖是 `self.kb_path` 与模块级缓存的 `build_kp_index()`）。
    """

    def __init__(self, kb_path: str) -> None:
        self.kb_path = kb_path

    def check_kp_id(self, kp_id: str, rel_path: str | None = None) -> dict:
        from memoria.services.document import DocumentService

        return DocumentService.check_kp_id(self, kp_id, rel_path)

    def __getattr__(self, name: str) -> Any:
        # plan 校验将来新增对 service 的依赖时**立刻可见**，而不是静默降级成"没校验"
        raise AttributeError(
            f"提议工具只提供最小只读服务（当前只有 check_kp_id）；plan 校验新增了对 {name} 的依赖 ⇒ "
            "请在 _ValidationService 里显式借用 DocumentService 的**同一实现**（不要另写一份校验）"
        )


def _propose_write(kb_path: str, arguments: Mapping[str, Any]) -> ToolOutput:
    """校验 + dry-run（**零落盘**）后把 plan 排进信箱；不过校验就回错误（模型据此重写整批）。"""
    import time

    from memoria.services.agent.plan import PLAN_VERSION, preview_plan, validate_plan

    intent = str(arguments.get("intent") or "").strip()
    ops: list[dict[str, Any]] = []
    for index, item in enumerate(arguments.get("ops") or [], start=1):
        if not isinstance(item, Mapping):
            continue
        row = {str(key): value for key, value in item.items()}
        row.setdefault("op_id", f"o{index}")  # 缺省由程序补齐（plan 内唯一性由校验器兜底）
        ops.append(row)
    plan: dict[str, Any] = {
        "v": PLAN_VERSION,
        "txid": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-01",
        "intent": intent,
        "ops": ops,
    }
    service = _ValidationService(kb_path)
    with kb_read_only(kb_path):
        checked = validate_plan(kb_path, plan, service=service)
        if checked.get("status") != "ok":
            detail = "\n".join(
                f"- [{row.get('op_id') or '-'}] {row.get('code')}: {row.get('message')}"
                for row in (checked.get("errors") or [])
            )
            return ToolOutput(
                text=error_text(
                    "计划未通过校验，**什么都没写**。最常见的原因是行号 / 原文取自**旧内容**（文件刚被改过）。"
                    "请按两步重来：① 先 `read_document` 重新读该文件，拿到**当前**行号与逐字原文；"
                    "② 按下面的问题修正后**重提整批** —— 出错的 op 要改对，**别把它删掉**，"
                    "也别把没出错的 op 丢掉：\n" + detail,
                    INVALID_PLAN_CODE,
                ),
                error=True,
                code=INVALID_PLAN_CODE,
            )
        preview = preview_plan(kb_path, plan, service=service)
    if preview.get("status") != "ok" or not preview.get("previewed"):
        return ToolOutput(
            text=error_text("计划试算（dry-run）失败，请稍后重提：计划本身没有落盘", INVALID_PLAN_CODE),
            error=True,
            code=INVALID_PLAN_CODE,
        )
    _PROPOSALS.setdefault(os.path.abspath(kb_path), []).append(plan)
    files = [row for row in (preview.get("files") or []) if isinstance(row, Mapping)]
    total = sum(len(row.get("ops") or []) for row in files)
    lines = [
        f"- {row.get('file')}：{len(row.get('ops') or [])} 项操作，改 {len(row.get('lines_changed') or [])} 行"
        for row in files
    ]
    return ToolOutput(
        text=(
            f"已**提议**（尚未写入）{total} 项操作，影响 {len(files)} 个文件：\n"
            + "\n".join(lines)
            + "\n用户会在对话栏看到一张**确认卡**，逐条勾选并点「应用」之后才会真正写入"
            "（写入前自动备份、之后可撤销）。在用户明确告诉你结果之前，**不要声称已经写入**，"
            "也不要重复提议同一批改动。"
        )
    )


def _write_proposal_tools(kb_path: str) -> tuple[Tool, ...]:
    """W 线第一把工具（**只提议、不落盘**）；`build_kb_tools()` 末尾拼接。"""

    def _bound(arguments: Mapping[str, Any]) -> ToolOutput:
        return _propose_write(kb_path, arguments)

    return (
        Tool(
            name=PROPOSE_TOOL_NAME,
            description=(
                "**提议**一批对知识库的修改，交给用户在对话栏的确认卡上逐条确认。"
                "**本工具不写盘**：只有用户勾选并点「应用」之后才会真正写入（写入前自动备份、之后可撤销）。"
                "用户要求修改/写入知识库时用它，一次提一批（同一意图的多处改动放进同一个 ops 数组）。"
                "`ops[]` 支持的 op 与字段："
                "① `upsert_kp`（建/改知识点）—— `file`、`kp_id`、`name`（可选 `description`/`tags`）、"
                "`range`=`{start:{line[,col]},end:{line[,col]}}`（1 起行号，可省列）；"
                "② `attach_links`（把正文里的纯文本挂成跳转并把锚文本包成 `[[id]]`）—— `file`、"
                "`anchor_text`（必须与正文**逐字**相同的纯文本，且**尚未**被 `[[…]]` 包过）、"
                "`targets`=`[知识点 id 或文件名]`（可省 `edge_type`=`reference`|`extend`）、"
                "可选 `occurrences`=`[{line[,col]}]`（同行出现多处且要给 col 时必须给）；"
                "③ `detach_links`（拆掉跳转、还原纯文本）—— `file`、`anchor_text`、"
                "`occurrences`=`[{line}]`（该行确实挂着这个锚文本）、`mode`=`detach`（默认）；"
                "④ `replace_lines`（**改正文**：替换若干行）—— `file`、"
                "`range`=`{start:{line},end:{line}}`（1 起、**含端点**）、`expect`（这几行**现在**的"
                "逐字原文，多行用 `\\n` 连接；对不上就拒）、`text`（替换成的新正文，可多行）；"
                "⑤ `insert_lines`（**插入正文**）—— `file`、`after`（插在这一行**之后**；`0` = 插到正文"
                "最前）、`expect`（`after` 那行的原文；`after=0` 时省略）、`text`；"
                "⑥ `delete_lines`（**删正文**）—— `file`、`range`、`expect`。"
                "⑦ `create_file`（**新建 .md**）—— `file`（库内相对 `.md` 路径，父目录自动建）、"
                "可选 `body`（初始正文，直接给完整内容）；该文件**必须不存在**。"
                "⑧ `rename_file`（**重命名 .md**）—— `file`、`new_name`（只给文件名、可省 `.md`，"
                "保持所在目录）；会**级联改写全库** `[[文件名]]` 引用（预览会列出被改写的文件）。"
                "⑨ `upsert_block`（**整块重建**代码块 / mermaid / 公式块）—— `file`、"
                "`kind`=`code`|`mermaid`|`math`、`range`（要**恰好**覆盖整个块：开围栏 → 内容 → 闭围栏，"
                "1 起含端点）、`expect`（整块**逐字**原文）、`content`（**不含围栏**的新块内容）、"
                "可选 `lang`（kind=code 时的语言；缺省沿用原语言）。"
                "围栏由程序重建；`content` 里不许再出现围栏行（``` / `$$`）。"
                "**表格本轮不提供**（人 UI 也还不能写表格，§7 5.2）。"
                "⑩ `insert_image_ref`（**插入一行图片引用**）—— `file`、`after`（插在这一行之后）、"
                "`expect`（`after` 那行的原文）、`path`（**库内相对**图片路径，通常是"
                "`.memoria/images/xxx.png`；必须已存在于库内）、可选 `alt`（替代文本）、"
                "可选 `attrs`（显示属性，如 `width=300,align=center`，写在 title 位）。"
                "**图片入库 / 改属性 / 移动删除本轮不提供**（入库的备份集有先有鸡还是先有蛋的问题、"
                "属性语法权威在人 UI、删除属默认关）。"
                "改正文的 op **必须排在挂/拆跳转、建点之后**（那些 op 的行号以编辑前的正文为准），"
                "同一文件的多条改正文区间不得重叠；"
                "`create_file` / `rename_file` 改变路径或全库引用 ⇒ **必须单独成一批**"
                "（同一 plan 里不能再有别的 op）。"
                "**删除文件本轮不提供**（设计里属「默认关」，等权限档定案）。"
                "提议前先 `read_document` 读清目标原文与行号，不要凭印象写；"
                "提议被拒时：**若原因是行号/原文过期**（文件刚被人改过），先 `read_document` 重新读一遍拿到"
                "当前行号，再按返回的 `op_id` 与错误码修正后**重提整批** —— 出错的 op 要改对，"
                "**别把它删掉**，也别把没出错的 op 丢掉；"
                "提议成功后，在用户回来告诉你结果之前**不要声称已写入**。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                        "description": "一句话说明这批改动要做什么（人话；会显示在确认卡上）",
                    },
                    "ops": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 20,
                        "description": "要改的条目（字段随 op，见工具说明）",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                },
                "required": ["intent", "ops"],
                "additionalProperties": False,
            },
            handler=_bound,
        ),
    )
