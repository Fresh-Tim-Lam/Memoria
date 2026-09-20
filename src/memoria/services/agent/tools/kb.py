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
| `search_sessions` | `services/agent/session/query.py`（本轮 M2 新增；**对话记录**而非知识库文档，故不产生 `文件:行号` 锚点） |

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
    "search_kb", "read_document",
    "read_kp",
    "kb_overview",
    "validate_kb",
    "search_sessions",
    "glob", "grep", "read_image",
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
    """校验并归一化知识库内相对路径；越界或非 .md 返回 None。"""
    rel = (path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or not rel.lower().endswith(".md"):
        return None
    norm = os.path.normpath(rel).replace(os.sep, "/")
    if norm == ".." or norm.startswith("../"):
        return None
    full = os.path.abspath(os.path.join(kb_path, norm))
    root = os.path.abspath(kb_path)
    if full != root and not full.startswith(root + os.sep):
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
        return _error("read_document: path 必须是知识库内的相对 .md 路径（不得上跳）")
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
        # 三者都只读；库外路径、`.memoria/**` 与 VCS 元数据目录一律排除（见文件末尾块）。
        Tool(
            name="glob",
            description=(
                "按 glob 模式列出**知识库内**的文件路径（只读，只列文件、不列目录）。"
                "不含 `/` 的模式匹配任意深度的文件名（`*.md` 等于在全库找 .md）；"
                f"最多返回 {GLOB_MAX_RESULTS} 条（按修改时间新→旧），超出时给出计数与收窄提示。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "minLength": 1, "description": "glob 模式，例如 **/*.md、vocab/*.md"},
                    "path": {"type": "string", "description": "可选：库内相对目录（搜索根，默认库根）"},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _glob_tool(root, arguments),
        ),
        Tool(
            name="grep",
            description=(
                "在**知识库内**按正则逐行搜索正文，按文件分组返回 `Line N: <片段>`（只读）。"
                f"最多返回 {GREP_MAX_MATCHES} 处命中、单行预览 {GREP_MAX_LINE_BYTES} 字节，"
                f"扫描超过 {GREP_TIMEOUT_S:.0f} 秒即中止。正则用 Python `re` 语法（非 ripgrep 方言）。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python `re` 正则（空白本身是合法模式）"},
                    "path": {"type": "string", "description": "可选：库内相对文件或目录（默认全库）"},
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
                "读取知识库内的 PNG/JPEG/WebP/GIF 图片。**当前端点不支持图像输入**："
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
        ),
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
# 1. 工具面是**知识库**不是工作区：所有路径经 `_safe_rel_any()` 限定库内，`.memoria/**` 与
#    VCS 元数据目录一并跳过，解析到库外的符号链接条目不返回也不读；
# 2. `grep` 用 Python `re` 而非 ripgrep：正则方言不同（无 `\p{…}`、无 `\z` 之外的 PCRE 扩展），
#    结果上限与超时都在 Python 侧自持（`GREP_MAX_MATCHES` / `GREP_TIMEOUT_S`），零新依赖；
# 3. 本地消息层**不能**承载图片内容块（`llm/types.py` 的 `Message.content` 是纯文本、
#    `llm/providers/openai_compatible.py::_message_to_wire()` 只写 `{"role","content": <str>}`），
#    故 `read_image` 只做参数/格式校验后**明确拒绝**，不伪造成功（见 `_read_image_tool()`）。

#: 一次 `read_document` 返回的默认且最大正文行数（上游 `READ_LIMIT`，`tool-fs/src/read.ts:15`）。
DEFAULT_READ_LIMIT = 2000
#: 一次 `glob` 内联展示的路径上限（上游 `globMaxResults`，`tool-fs-search/src/glob.ts:25` + README.md:60）。
GLOB_MAX_RESULTS = 100
#: `glob`/`grep` 遍历跳过的目录名：上游 `GLOB_VCS_EXCLUDES`（`src/glob.ts:37`）+ 本地知识库元数据目录。
GLOB_EXCLUDED_DIRS = (".git", ".svn", ".hg", ".bzr", ".jj", ".sl", ".memoria")
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
    """校验并归一化库内相对路径（**不限定扩展名**）；空 / 上跳 / 越界返回 None。

    与 `_safe_rel()` 同源，只去掉 `.md` 后缀要求：`glob`/`grep` 要能指向任意文件与目录。
    """
    rel = (path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        return None
    norm = os.path.normpath(rel).replace(os.sep, "/")
    if norm == ".." or norm.startswith("../"):
        return None
    full = os.path.abspath(os.path.join(kb_path, norm))
    root = os.path.abspath(kb_path)
    if full != root and not full.startswith(root + os.sep):
        return None
    return norm


def _safe_rel_dir(kb_path: str, path: str) -> str | None:
    """库内相对**目录**（`""` = 库根）；越界/非法返回 None。"""
    norm = _safe_rel_any(kb_path, path)
    if norm is None:
        return None
    return "" if norm == "." else norm


def _walk_kb_files(kb_path: str, subdir: str = "") -> list[str]:
    """库内文件清单（相对库根、`/` 分隔）：跳过 `GLOB_EXCLUDED_DIRS` 与解析到库外的条目。

    越界判定在**两侧都先 `realpath`**：Windows 8.3 短名（`LAMTIM~1`）与 junction/符号链接会让
    `realpath` 与 `abspath` 的书写形式不同 —— 只归一化一侧会把整个库误判成「库外」而**静默返回空**。
    """
    root = os.path.abspath(kb_path)
    real_root = os.path.realpath(root)
    base = os.path.join(root, subdir) if subdir else root
    out: list[str] = []
    for current, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(name for name in dirnames if name not in GLOB_EXCLUDED_DIRS)
        prefix = os.path.relpath(current, root).replace(os.sep, "/")
        prefix = "" if prefix == "." else prefix + "/"
        for name in filenames:
            real = os.path.realpath(os.path.join(current, name))
            if real != real_root and not real.startswith(real_root + os.sep):
                continue  # 符号链接指向库外 ⇒ 不返回（后续也不会去读）
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
    """`glob`：按 glob 模式列出库内文件（只读；库外与越界一律拒绝）。"""
    pattern = str(arguments.get("pattern") or "").strip()
    if not pattern:
        return _error("glob: pattern 不能为空")
    raw_path = str(arguments.get("path") or "").strip()
    subdir = ""
    if raw_path:
        resolved = _safe_rel_dir(kb_path, raw_path)
        if resolved is None:
            return _error("glob: path 必须是知识库内的相对目录（不得上跳或越界）")
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
        return ToolOutput(text=f"未匹配到文件（pattern={pattern!r}）。glob 只列库内文件，不列目录。")
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
    """`grep`：正则逐行搜库内正文，按文件分组返回 `Line N: <片段>`（只读）。"""
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
            return _error("grep: path 必须是知识库内的相对文件或目录（不得上跳或越界）")
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
    """`read_image`：参数与格式校验照上游，随后因**本端点不支持图像输入**而明确拒绝。

    不伪造成功：本地消息层（`llm/types.py` 的纯文本 `Message.content`）无法把图片作为内容块
    发出，故校验通过后仍返回 `UNSUPPORTED_IMAGE_INPUT`，并在文本里说明真实原因与替代做法。
    校验顺序先参数/格式、后能力拒绝：这样模型能区分「文件不是图片」与「端点收不了图片」。
    """
    raw = str(arguments.get("file_path") or "")
    if not raw.strip():
        return _error("read_image: file_path 不能为空")
    normalized = _safe_rel_any(kb_path, raw)
    if normalized is None:
        return _error("read_image: file_path 必须是知识库内的相对路径（不得上跳或越界）")
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
        "但当前模型通道（`llm/types.py` 的纯文本 `Message.content`）无法把图片作为内容块发出，"
        "故不返回图片本身；请改用文字描述该图，或等「消息层图片支持」落地（见 dsh-agent-port.md §6.16 待办）。",
        UNSUPPORTED_IMAGE_INPUT,
    )
