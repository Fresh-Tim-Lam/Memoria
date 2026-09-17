# 语义移植自 deepseek-harness packages/core/tools（工具定义与错误语义）
# 与 packages/context/agent-instructions（指令文件发现，见 prompt.py）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""只读知识库工具：检索 / 读文档 / 读知识点 / 库概览 / 校验。

五个工具全部**复用 Memoria 既有服务层**（不重写检索、不另立索引）：

| 工具 | 复用 |
|---|---|
| `search_kb` | `services/search_kernel.search()`（lexical 通道）+ `kp_index.build_kp_index()` 补行号锚点 |
| `read_document` | `services/kp_resolver.resolve_knowledge_points()` + `storage.sidecar` |
| `read_kp` | `services/kp_index.py` + 正文切片 |
| `kb_overview` | `storage.scanner.collect_md_files()` + sidecar 摘要 |
| `validate_kb` | `services/document.DocumentService.validate_kb()`（内部经 `check_report.summarize_check_counts`） |

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

KB_TOOL_NAMES = ("search_kb", "read_document", "read_kp", "kb_overview", "validate_kb")

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


def _read_document(kb_path: str, path: str) -> ToolOutput:
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

    truncated = len(body) > MAX_BODY_CHARS
    shown = body[:MAX_BODY_CHARS]
    parts = [
        f"文档 {rel}：共 {len(lines)} 行，{len(kps)} 个知识点。",
        "",
        "知识点（`文件:行号`）：",
        *(kp_rows or ["- （该文档没有 sidecar 知识点）"]),
        "",
        "正文：",
        shown,
    ]
    if truncated:
        parts.append(f"\n…（正文已截断，仅显示前 {MAX_BODY_CHARS} 字符）")
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


def build_kb_tools(kb_path: str, *, top_k: int = DEFAULT_TOP_K) -> tuple[Tool, ...]:
    """绑定到某个知识库的只读工具集；全部声明 `read_only=True`。"""
    root = os.path.abspath(kb_path)

    def _bound_search(arguments: Mapping[str, Any]) -> ToolOutput:
        return _search_kb(root, str(arguments.get("query") or ""), int(arguments.get("top_k") or top_k))

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
            description="读取知识库内一篇 Markdown 文档的正文与知识点清单（带 `文件:行号`）。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1, "description": "知识库内相对路径，例如 neural-network.md"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=lambda arguments: _read_document(root, str(arguments.get("path") or "")),
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
    )
