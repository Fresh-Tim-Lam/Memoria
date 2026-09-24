# 语义移植自 deepseek-harness packages/web（`web-search-deepseek` 的 Anthropic 兼容面调用、
# `web-fetch-http` 的 URL 策略与内容分类、`web/tool-web` 的归一结果形状）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""联网（N 线）：检索 provider + 抓取安全层（实现记录见 `docs/design/dsh-agent-port.md` §6.28）。

本模块只有两个能力，**均无后台/自动触发路径**（默认关 + 逐次显式，草案 §3.1）：工具面在
`tools/kb.py` 的 `_web_tools()`，审批面一行未动（两把工具声明 `read_only=True` ⇒ 免审批）。

| 能力 | 上游对照 | 本地口径 |
|---|---|---|
| `WebClient.search()` | `web-search-deepseek/src/provider.ts:197-270`：**原生 server tool** `web_search_20250305`，一次检索 = 一次完整模型调用（额外 token 费） | 同一线格式：`POST {anthropic_base}/v1/messages`，头 `x-api-key` + `authorization: Bearer` + `anthropic-version`，体带 `tools:[{type,name,max_uses}]`；结果归一成 `{sources[], truncated}` |
| `WebClient.fetch()` | `web-fetch-http/src/provider.ts`（无 key 公网抓取；上游把 **SSRF 防护标 deferred**） | **安全面本地补齐**（草案 §3.3 明确要求）：仅 http(s)、拒 URL 内凭据、DNS 解析后**逐地址**拒私网/回环/链路本地/组播/保留/未指定、只允许**同源**重定向且**逐跳重校验**、字节 + 字符双上限、显式超时 |

为什么走 **Anthropic 面**而不是 Responses 面：DeepSeek 自家 Responses 面把内置工具标为 `Ignored`，
只有 `api.deepseek.com/anthropic` 代理了原生 Web Search（见 `docs/todo.md` AG54 的调研结论）。

设计约定（与 `providers/openai_compatible.py::stream()` 同一套纪律）：

- 纯标准库（`urllib` / `json` / `socket` / `ipaddress` / `http.client`），**零新依赖**；
- 超时**只以关键字**传入（`opener(request, timeout=…)`），异常按类型归一
  （`urllib.error.HTTPError` / `TimeoutError` / `http.client.InvalidURL` / `OSError`）；
- `opener` / `resolver` 可注入 ⇒ 单测**永不触网**；
- 密钥只出现在请求头的 `x-api-key` / `authorization` 两处，**绝不进日志、异常消息或 `repr`**；
- 抓取结果**只进 `pending`**（草案态）：`save_fetched_page()` 走既有
  `storage/pending.py::save_pending`，给模型只回「路径 + 摘要 + 长度」（长文不进上下文）。
"""

from __future__ import annotations

import hashlib
import html
import http.client
import ipaddress
import json
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from memoria import __version__
from memoria.services.agent.llm.config import (
    DEFAULT_FETCH_MAX_BYTES,
    DEFAULT_FETCH_TIMEOUT_S,
    DEFAULT_SEARCH_MAX_RESULTS,
    DEFAULT_SEARCH_TIMEOUT_S,
    AgentConfig,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CODE_BLOCKED_DOMAIN",
    "CODE_BLOCKED_URL",
    "CODE_CONFIG",
    "CODE_INVALID_URL",
    "CODE_PROVIDER",
    "CODE_UNSUPPORTED",
    "DEEPSEEK_ANTHROPIC_BASE",
    "DEEPSEEK_HOST",
    "FETCH_MAX_TEXT_CHARS",
    "MAX_REDIRECTS",
    "MAX_URL_CHARS",
    "WEB_SEARCH_TOOL_TYPE",
    "WebClient",
    "WebError",
    "anthropic_base_url",
    "assert_public_host",
    "blocked_address_reason",
    "build_search_body",
    "build_search_headers",
    "check_fetch_url",
    "citation_snippets",
    "classify_content_type",
    "domain_allowed",
    "extract_text",
    "merge_domain_rules",
    "parse_domains",
    "parse_search_response",
    "resolve_addresses",
    "same_origin",
    "save_fetched_page",
    "summarize_text",
]

#: DeepSeek 官方 Anthropic 兼容面（`/v1` 含在内，`/messages` 由调用方拼出）。
DEEPSEEK_ANTHROPIC_BASE = "https://api.deepseek.com/anthropic/v1"
#: 只对这一个主机做「OpenAI 面 → Anthropic 面」的自动推导；其它主机必须显式配 `search_base_url`。
DEEPSEEK_HOST = "api.deepseek.com"
#: 原生 server tool 的类型名（上游 `provider.ts:212` 逐字同名；改它等于换协议）。
WEB_SEARCH_TOOL_TYPE = "web_search_20250305"
#: `anthropic-version` 头取值（上游默认值，逐字同名）。
ANTHROPIC_VERSION = "2023-06-01"
#: 检索调用的 `max_tokens`：本层只要 `web_search_tool_result` 块、不需要长正文 ⇒ 取小上限。
SEARCH_MAX_TOKENS = 256
#: 检索响应的原始读取上限（字节）：结果块是结构化短文本，超出即视为异常响应。
SEARCH_MAX_BYTES = 4 * 1024 * 1024
#: 单条摘要（citation 引文）的字符上限。
SNIPPET_MAX_CHARS = 400
#: 回给模型的摘要长度；`pending` 条目 `name` 另取更短的一段。
FETCH_SUMMARY_MAX_CHARS = 240
PENDING_NAME_MAX_CHARS = 80
#: 抓取正文的**字符**上限（与 `tools/kb.py` 的 `MAX_BODY_CHARS` 同值：单次进上下文的内容都按此设界）。
FETCH_MAX_TEXT_CHARS = 20_000
#: URL 长度上限（官方外链口径 ≤ 8192 字符）。
MAX_URL_CHARS = 8192
#: 同源重定向的最大跳数（逐跳都要重跑地址校验；超限即拒）。
MAX_REDIRECTS = 3
#: 读响应体的块大小（**绝不 `read()` 无界**）。
_READ_CHUNK_BYTES = 64 * 1024
#: HTTP 错误体的读取上限（只用于取错误消息）。
_ERROR_BODY_BYTES = 64 * 1024
#: 重定向状态码。
_REDIRECT_CODES = (301, 302, 303, 307, 308)
#: 出网身份（版本号取自 `memoria/__version__.py` 单一来源）。
USER_AGENT = f"memoria-agent/{__version__}"

#: 稳定失败码（与上游 `WebError` 的 `WEB_*` 词汇同族）。
CODE_PROVIDER = "WEB_PROVIDER_ERROR"
CODE_INVALID_URL = "WEB_INVALID_URL"
CODE_BLOCKED_URL = "WEB_BLOCKED_URL"
CODE_CONFIG = "WEB_CONFIG"
CODE_UNSUPPORTED = "WEB_UNSUPPORTED_CONTENT"
#: 域名名单拒绝（2026-09-24；§3.3 的"域名单"落点）——与 `WEB_BLOCKED_URL` 分开：前者是**用户的名单**，
#: 后者是"地址类别 / URL 形状"（回环、私网、内嵌凭据、协议）。前端据此给不同的可照做提示。
CODE_BLOCKED_DOMAIN = "WEB_BLOCKED_DOMAIN"


class WebError(Exception):
    """联网层的稳定失败：`code` 取 `WEB_*` 词汇，消息**绝不含密钥**。"""

    def __init__(self, message: str, code: str = CODE_PROVIDER, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


# ── 纯函数：基址推导 / URL 校验 / 地址类别 ────────────────────────────────────────


def anthropic_base_url(base_url: str, search_base_url: str = "") -> str:
    """推导 Anthropic 兼容面基址（`/messages` 由调用方拼接）。

    规则（草案 AG54 的基址推导条目）：

    1. 显式 `search_base_url` **优先**（任意主机都行：自建网关 / 代理 / 其它厂商的 Anthropic 面）；
    2. 否则**只认** `api.deepseek.com`：应用配置里的 `base_url` 是**OpenAI 兼容面**
       （`https://api.deepseek.com/v1`）⇒ 返回 `https://api.deepseek.com/anthropic/v1`；
    3. 其它主机**不猜**（fail-closed）：抛 `WebError(WEB_CONFIG)`，并在消息里点明该填哪个键。
    """
    explicit = str(search_base_url or "").strip().rstrip("/")
    if explicit:
        return explicit
    host = (urllib.parse.urlsplit(str(base_url or "").strip()).hostname or "").lower()
    if host == DEEPSEEK_HOST:
        return DEEPSEEK_ANTHROPIC_BASE
    raise WebError(
        f"当前模型端点的主机是 {host or '（未配置）'} —— 推导不出 Anthropic 兼容面基址"
        f"（只有 {DEEPSEEK_HOST} 能自动推导）。请在设置 → Agent 里显式填 `search_base_url`"
        "（例如自建网关的 https://<主机>/anthropic/v1），或把模型端点换回 DeepSeek 官方端点。",
        CODE_CONFIG,
    )


def check_fetch_url(url: str) -> str:
    """抓取前的**纯**URL 校验（不解析 DNS）：仅 http(s)、无内嵌凭据、长度有界；返回原样 URL。"""
    text = str(url or "").strip()
    if not text:
        raise WebError("抓取的 URL 不能为空。", CODE_INVALID_URL)
    if len(text) > MAX_URL_CHARS:
        raise WebError(f"URL 超过 {MAX_URL_CHARS} 字符上限（收到 {len(text)} 字符）。", CODE_INVALID_URL)
    parts = urllib.parse.urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise WebError(
            f"不支持的协议 {scheme or '（空）'}：只允许抓取 http / https 的网页。", CODE_INVALID_URL
        )
    if parts.username or parts.password:
        raise WebError("URL 里带了内嵌凭据（`user:pass@`）⇒ 拒绝抓取。", CODE_BLOCKED_URL)
    if not parts.hostname:
        raise WebError(f"URL 缺少主机名：{text}", CODE_INVALID_URL)
    return text


def blocked_address_reason(address: str) -> str | None:
    """该 IP 是否属于**不许出网**的类别；属则返回中文原因，否则 `None`（纯函数，单测直取）。"""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return f"不是合法 IP（{address}）"
    for label, hit in (
        # 顺序有讲究：`ipaddress` 的 `is_private` 对回环 / 链路本地 / 保留 / 未指定**也为真**，
        # 故更具体的类别必须写在前面，否则报出来的原因会是笼统的"私网"。
        ("回环", ip.is_loopback),
        ("链路本地", ip.is_link_local),
        ("组播", ip.is_multicast),
        ("未指定", ip.is_unspecified),
        ("保留", ip.is_reserved),
        ("私网", ip.is_private),
    ):
        if hit:
            return label
    return None


def resolve_addresses(host: str, port: int | None = None) -> list[str]:
    """解析主机名 → 全部 IP（v4/v6）；**解析失败即拒**（fail-closed，草案 §3.3）。"""
    try:
        infos = socket.getaddrinfo(host, port or 0, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise WebError(
            f"无法解析主机 {host}（{type(exc).__name__}）⇒ 抓取按拒绝处理。", CODE_BLOCKED_URL
        ) from exc
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4] if len(info) > 4 else ()
        ip = str(sockaddr[0]) if sockaddr else ""
        if ip and ip not in addresses:
            addresses.append(ip)
    if not addresses:
        raise WebError(f"主机 {host} 没有解析到任何地址 ⇒ 抓取按拒绝处理。", CODE_BLOCKED_URL)
    return addresses


def assert_public_host(url: str, *, resolver: Callable[..., Sequence[str]] = resolve_addresses) -> list[str]:
    """解析 URL 主机并**逐地址**校验；任一地址落在禁出网类别 ⇒ `WebError(WEB_BLOCKED_URL)`。

    这是 SSRF 防护的落点：`http://127.0.0.1/`、`http://10.0.0.5/`、`http://[::1]/`、
    `http://169.254.169.254/`（云元数据）一律拒；**每一次重定向后都要重跑**（见 `WebClient.fetch`）。
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    addresses = resolver(host, parts.port)
    for ip in addresses:
        reason = blocked_address_reason(ip)
        if reason:
            raise WebError(
                f"拒绝出网：{host} 解析到{reason}地址 {ip}（只允许抓公网地址，见草案 §3.3）。",
                CODE_BLOCKED_URL,
            )
    return list(addresses)


def _effective_port(parts: urllib.parse.SplitResult) -> int:
    if parts.port:
        return int(parts.port)
    return 443 if parts.scheme.lower() == "https" else 80


def same_origin(left: str, right: str) -> bool:
    """同源判定（协议 + 主机 + 有效端口）；重定向只允许同源（草案 §3.3）。"""
    a, b = urllib.parse.urlsplit(left), urllib.parse.urlsplit(right)
    return (
        a.scheme.lower(),
        (a.hostname or "").lower(),
        _effective_port(a),
    ) == (
        b.scheme.lower(),
        (b.hostname or "").lower(),
        _effective_port(b),
    )


# ── 纯函数：请求构造与响应归一 ──────────────────────────────────────────────────


def build_search_body(query: str, model: str, max_results: int) -> dict[str, Any]:
    """原生检索的请求体（上游 `provider.ts:205-213` 同形；`messages[].content` 用字符串形态）。"""
    return {
        "model": str(model or ""),
        "max_tokens": SEARCH_MAX_TOKENS,
        "messages": [{"role": "user", "content": str(query or "")}],
        "tools": [{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": int(max_results)}],
    }


def build_search_headers(api_key: str) -> dict[str, str]:
    """检索请求头：密钥只在 `x-api-key` / `authorization` 两处出现（**绝不进日志**）。

    两个头都发，理由同上游（`provider.ts:226-227`）：官方 DeepSeek 认 `x-api-key`，
    而 Anthropic 兼容的网关多认 `authorization: Bearer`。
    """
    return {
        "x-api-key": api_key,
        "authorization": f"Bearer {api_key}",
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": USER_AGENT,
    }


def citation_snippets(blocks: Iterable[Any]) -> dict[str, str]:
    """`text` 块的 `citations[]` → `{url: cited_text}`（摘要的唯一来源，上游 `provider.ts:121-132`）。

    Anthropic 的 `web_search_result` 条目通常**不带**行内摘要：正文片段在**另一个** `text` 块的
    citation 里，按 URL 关联（同一 URL 首次出现者胜）。
    """
    snippets: dict[str, str] = {}
    for block in blocks:
        if not isinstance(block, Mapping) or block.get("type") != "text":
            continue
        citations = block.get("citations")
        if not isinstance(citations, Sequence) or isinstance(citations, (str, bytes)):
            continue
        for cite in citations:
            if not isinstance(cite, Mapping):
                continue
            url = str(cite.get("url") or "").strip()
            text = str(cite.get("cited_text") or "").strip()
            if url and text and url not in snippets:
                snippets[url] = text[:SNIPPET_MAX_CHARS]
    return snippets


def parse_search_response(payload: Any, *, max_results: int | None = None) -> dict[str, Any]:
    """Anthropic 面响应 → `{sources:[{url,title,snippet}], truncated}`。

    **没有 `web_search_tool_result` 块 = 失败**（上游同口径：不拿模型散文去凑结果）；
    条目按 URL 去重，摘要取自 citation（`citation_snippets`）。`truncated` 只在**本地**按
    `max_results` 截断时为 `True`（端点侧的 `max_uses` 由请求参数收敛）。
    """
    blocks = payload.get("content") if isinstance(payload, Mapping) else None
    if not isinstance(blocks, Sequence) or isinstance(blocks, (str, bytes)):
        blocks = []
    result_blocks = [
        block
        for block in blocks
        if isinstance(block, Mapping) and block.get("type") == "web_search_tool_result"
    ]
    if not result_blocks:
        raise WebError(
            "模型端点没有返回 `web_search_tool_result` 块 ⇒ 这次检索没有拿到任何来源"
            "（可能该端点未开原生联网，或该模型不支持这个 server tool）。",
            CODE_PROVIDER,
        )
    snippets = citation_snippets(blocks)
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in result_blocks:
        items = block.get("content")
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            continue
        for item in items:
            if not isinstance(item, Mapping) or item.get("type") != "web_search_result":
                continue
            url = str(item.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                {
                    "url": url,
                    "title": str(item.get("title") or "").strip(),
                    "snippet": str(snippets.get(url) or "").strip(),
                }
            )
    truncated = False
    limit = _positive_int(max_results, 0)
    if limit and len(sources) > limit:
        sources = sources[:limit]
        truncated = True
    return {"sources": sources, "truncated": truncated}


def classify_content_type(content_type: str) -> str | None:
    """`Content-Type` → `html` / `text` / `None`（不支持，如二进制）；缺头按 `text` 处理。"""
    mime = str(content_type or "").split(";")[0].strip().lower()
    if not mime:
        return "text"
    if mime in ("text/html", "application/xhtml+xml"):
        return "html"
    if mime.startswith("text/"):
        return "text"
    if mime in ("application/json", "application/xml") or mime.endswith(("+json", "+xml")):
        return "text"
    return None


# 去脚本/样式等**整块**内容；`<(标签)[^>]*>.*?</\1>` 不含嵌套量词 ⇒ 线性、无回溯爆炸
# （且输入恒 ≤ 抓取字节上限）。倒序无关：先整块删、再删注释、再把块级标签换成换行、最后删标签。
_HTML_DROP_RE = re.compile(r"(?is)<(script|style|noscript|template|svg)\b[^>]*>.*?</\1\s*>")
_HTML_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_HTML_BLOCK_RE = re.compile(
    r"(?i)</?(?:p|div|br|li|ul|ol|dl|dt|dd|tr|td|th|table|h[1-6]|section|article|aside|header|footer"
    r"|main|nav|blockquote|pre|hr|figure|figcaption|form)\b[^>]*>"
)
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_SPACES_RE = re.compile(r"[^\S\n]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _decode_text(raw: bytes) -> str:
    """字节 → 文本：UTF-8（含 BOM）→ GB18030（Windows 中文常见）→ 有损兜底（与 `tools/kb.py` 同口径）。"""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text(raw: bytes, kind: str = "text") -> str:
    """响应字节 → 可读文本（HTML 去脚本/样式/标签并反转义；行内空白折叠）；末尾按字符上限截断。"""
    body = _decode_text(raw)
    if kind == "html":
        body = _HTML_DROP_RE.sub(" ", body)
        body = _HTML_COMMENT_RE.sub(" ", body)
        body = _HTML_BLOCK_RE.sub("\n", body)
        body = _HTML_TAG_RE.sub("", body)
        body = html.unescape(body)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = _SPACES_RE.sub(" ", body)
    body = _BLANK_LINES_RE.sub("\n\n", body)
    return body.strip()[:FETCH_MAX_TEXT_CHARS]


def summarize_text(text: str, limit: int = FETCH_SUMMARY_MAX_CHARS) -> str:
    """正文 → 单行摘要（空白折叠 + 截断）；这是**唯一**回给模型的内容形态。"""
    return " ".join(str(text or "").split())[:limit]


def save_fetched_page(kb_path: str, url: str, fetched: Mapping[str, Any]) -> dict[str, Any]:
    """把抓取结果落进库内**待确认清单**，只回指针（草案 §3.1/§3.2 的 `pending` 落点）。

    复用既有 `storage/pending.py::save_pending`（形状不变：`{schema_version, updated_at, items}`），
    只**追加**一种 kind = `web` 的条目（web 专属键 `url` / `chars` / `content_type` / `fetched_at` /
    `summary`）—— 正文本身只存这份库里，**不回模型**；同一 URL 重复抓取时覆盖同一条（幂等）。
    """
    from memoria.storage.pending import (
        PENDING_SCHEMA_VERSION,
        load_pending,
        pending_path,
        save_pending,
    )

    body = str(fetched.get("body") or "")
    summary = summarize_text(body)
    pending_id = hashlib.sha256(f"net|{url}".encode("utf-8")).hexdigest()[:16]
    item: dict[str, Any] = {
        "pending_id": pending_id,
        "file": url,
        "kind": "web",
        "name": summary[:PENDING_NAME_MAX_CHARS] or url,
        "status": "pending",
        "url": url,
        "chars": len(body),
        "content_type": str(fetched.get("content_type") or ""),
        "truncated": bool(fetched.get("truncated")),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }
    store = load_pending(kb_path) or {}
    if not isinstance(store, Mapping):
        store = {}
    items = [
        row
        for row in (store.get("items") or [])
        if isinstance(row, Mapping) and row.get("pending_id") != pending_id
    ]
    data = {
        "schema_version": PENDING_SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items + [item],
    }
    save_pending(kb_path, data)
    return {
        "pending_id": pending_id,
        "path": pending_path(kb_path),
        "summary": summary,
        "chars": len(body),
        "truncated": bool(fetched.get("truncated")),
    }


# ── 客户端（provider + 安全层；`opener` / `resolver` 可注入 ⇒ 单测不触网）──────────────


def _positive_int(value: Any, fallback: int) -> int:
    """宽松取正整数；`None` / 非数 / ≤0 一律回落 `fallback`。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return int(fallback)
    return number if number > 0 else int(fallback)


def _positive_float(value: Any, fallback: float) -> float:
    """宽松取正数秒；`None` / 非数 / ≤0 一律回落 `fallback`。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return number if number > 0 else float(fallback)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """禁止 `urllib` 自动跟随重定向：跳数与我们自己的地址校验必须**逐跳**执行。"""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _http_error_message(exc: urllib.error.HTTPError, url: str, *, label: str) -> str:
    """HTTP 错误 → 可读消息（尽力取 Anthropic 错误信封的 `message`；**不回显任何凭据**）。"""
    detail = ""
    try:
        raw = exc.read(_ERROR_BODY_BYTES)
        body = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — 错误体拿不到就只能报状态码（网关 5xx/429 常见）
        body = None
    if isinstance(body, Mapping):
        error = body.get("error")
        if isinstance(error, Mapping):
            detail = str(error.get("message") or "")
        elif isinstance(error, str):
            detail = error
        detail = detail or str(body.get("message") or "")
    suffix = f"：{detail}" if detail else ""
    return f"{label} {url} 失败：HTTP {exc.code}{suffix}"


def _read_capped(response: Any, cap: int) -> tuple[bytes, bool]:
    """按块读响应体，**绝不 `read()` 无界**；读满 `cap` 字节即停并返回 `truncated=True`。"""
    chunks: list[bytes] = []
    size = 0
    while size <= cap:
        chunk = response.read(min(_READ_CHUNK_BYTES, cap - size + 1))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    raw = b"".join(chunks)
    truncated = len(raw) > cap
    return raw[:cap], truncated


class WebClient:
    """一次调用一个实例：检索（provider）+ 抓取（安全层）。

    `on_outbound` 是**审计观测回调**（每次出网调一次，载荷 `{tool,host,url,status,bytes}`）：
    它拿不到密钥与正文（见 `_note_outbound`），且失败**不得**打断联网本身（与 `loop._emit` 同口径）。
    """

    def __init__(
        self,
        config: AgentConfig,
        *,
        opener: Any = None,
        resolver: Callable[..., Sequence[str]] | None = None,
        on_outbound: Callable[[Mapping[str, Any]], None] | None = None,
        allow_domains: Sequence[str] | None = None,
        deny_domains: Sequence[str] | None = None,
    ) -> None:
        self._config = config
        # 默认 opener **不跟随重定向**（同一个 `timeout=` 关键字纪律，见模块头）。
        self._opener = opener or urllib.request.build_opener(_NoRedirect()).open
        self._resolver = resolver or resolve_addresses
        self._on_outbound = on_outbound
        #: 域名名单（2026-09-24）：只在构造期解析一次；两表都空 = 不限。
        #: `allow_domains`/`deny_domains` 传**已合并**的两表（机器级 + 库级，见 `merge_domain_rules()`）；
        #: 省略 ⇒ 直接用机器级那两键（老调用点与单测的语义不变）。
        self._allow = tuple(allow_domains) if allow_domains is not None else parse_domains(getattr(config, "fetch_allow_domains", ""))
        self._deny = tuple(deny_domains) if deny_domains is not None else parse_domains(getattr(config, "fetch_deny_domains", ""))

    def _assert_domain(self, url: str) -> None:
        """域名名单闸（每跳调用）：`deny` 命中或不在非空 `allow` 内 ⇒ `WEB_BLOCKED_DOMAIN`。"""
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        allowed, reason = domain_allowed(host, self._allow, self._deny)
        if allowed:
            return
        detail = "在禁止名单里" if reason == "deny" else "不在允许名单里"
        raise WebError(
            f"抓取 {url}：主机 {host} {detail}（域名名单由用户在设置 → Agent 里配置；"
            "`fetch_deny_domains` 优先，`fetch_allow_domains` 非空时只放行列内域及其子域）。",
            CODE_BLOCKED_DOMAIN,
        )

    # —— 审计（只带可公开的事实）——

    def _note_outbound(self, tool: str, url: str, status: int, size: int) -> None:
        if self._on_outbound is None:
            return
        host = urllib.parse.urlsplit(url).hostname or ""
        try:
            self._on_outbound(
                {"tool": tool, "host": host, "url": url, "status": int(status), "bytes": int(size)}
            )
        except Exception as exc:  # noqa: BLE001 — 观测回调失败不得打断联网
            logger.warning("[agent-web] 出网审计回调失败：%r", exc)

    # —— 检索（DeepSeek 原生 server tool，走 Anthropic 兼容面）——

    def search(
        self, query: str, *, max_results: int | None = None, timeout_s: float | None = None
    ) -> dict[str, Any]:
        """一次联网检索；返回 `{sources:[{url,title,snippet}], truncated}`（**不回正文**）。"""
        text = str(query or "").strip()
        if not text:
            raise WebError("检索词不能为空。", CODE_INVALID_URL)
        limit = _positive_int(max_results, self._config.search_max_results or DEFAULT_SEARCH_MAX_RESULTS)
        timeout = _positive_float(
            timeout_s, self._config.search_timeout_s or DEFAULT_SEARCH_TIMEOUT_S
        )
        base = anthropic_base_url(self._config.base_url, self._config.search_base_url)
        url = f"{base}/messages"
        # 凭据走对话同一条通路（缺失/非法 ⇒ AuthError，消息只点名配置来源）
        payload = json.dumps(
            build_search_body(text, self._config.model, limit), ensure_ascii=False
        ).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload, headers=build_search_headers(self._config.require_api_key()), method="POST"
        )
        logger.debug("[agent-web] POST %s model=%s max_results=%s", url, self._config.model, limit)
        try:
            response = self._opener(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            message = _http_error_message(exc, url, label="检索")
            self._note_outbound("web_search", url, int(getattr(exc, "code", 0) or 0), 0)
            raise WebError(message, CODE_PROVIDER, status=getattr(exc, "code", None)) from exc
        except TimeoutError as exc:
            self._note_outbound("web_search", url, 0, 0)
            raise WebError(f"检索 {url} 超时（{timeout}s）。", CODE_PROVIDER) from exc
        except http.client.InvalidURL as exc:
            # 非数字端口等：`InvalidURL` 不是 `OSError`，须显式捕获（与 provider 同因）
            raise WebError(f"检索端点 {url} 不是可用的 URL：{exc}", CODE_CONFIG) from exc
        except OSError as exc:
            self._note_outbound("web_search", url, 0, 0)
            raise WebError(f"连接检索端点 {url} 失败（{type(exc).__name__}）。", CODE_PROVIDER) from exc
        with closing(response):
            raw = response.read(SEARCH_MAX_BYTES)
            status = int(getattr(response, "status", 200) or 200)
        self._note_outbound("web_search", url, status, len(raw))
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise WebError(f"检索端点返回的不是 JSON：{exc.msg}", CODE_PROVIDER) from exc
        return parse_search_response(parsed, max_results=limit)

    # —— 抓取（纯标准库；安全面全在本地）——

    def fetch(
        self, url: str, *, max_bytes: int | None = None, timeout_s: float | None = None
    ) -> dict[str, Any]:
        """抓一页正文（HTML/文本），返回 `{url,status_code,body,truncated,content_type}`。

        安全面（草案 §3.3）：纯 URL 校验 → **域名名单**（每跳，2026-09-24）→ **每跳**解析主机并拒私网
        地址 → 只跟**同源**重定向（≤ `MAX_REDIRECTS` 跳，逐跳重校验）→ 按字节上限读体 → 按内容类型
        分类 → 按字符上限截断。
        """
        cap = _positive_int(max_bytes, self._config.fetch_max_bytes or DEFAULT_FETCH_MAX_BYTES)
        timeout = _positive_float(timeout_s, self._config.fetch_timeout_s or DEFAULT_FETCH_TIMEOUT_S)
        current = check_fetch_url(url)
        for _hop in range(MAX_REDIRECTS + 1):
            # 名单先于 DNS：被名单拒的域**连解析都不做**（少一次外泄面，也少一次等待）
            self._assert_domain(current)
            assert_public_host(current, resolver=self._resolver)
            request = urllib.request.Request(
                current,
                headers={
                    "accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                    "user-agent": USER_AGENT,
                },
                method="GET",
            )
            logger.debug("[agent-web] GET %s max_bytes=%s", current, cap)
            try:
                response = self._opener(request, timeout=timeout)
            except urllib.error.HTTPError as exc:
                status = int(getattr(exc, "code", 0) or 0)
                headers = getattr(exc, "headers", None)
                location = (
                    str(headers.get("Location") or "")
                    if status in _REDIRECT_CODES and headers is not None
                    else ""
                )
                message = "" if location else _http_error_message(exc, current, label="抓取")
                exc.close()
                if location:
                    current = self._redirect_target(current, location)
                    continue
                self._note_outbound("fetch_url", current, status, 0)
                raise WebError(message, CODE_PROVIDER, status=status or None) from exc
            except TimeoutError as exc:
                self._note_outbound("fetch_url", current, 0, 0)
                raise WebError(f"抓取 {current} 超时（{timeout}s）。", CODE_PROVIDER) from exc
            except http.client.InvalidURL as exc:
                raise WebError(f"抓取地址 {current} 不是可用的 URL：{exc}", CODE_INVALID_URL) from exc
            except OSError as exc:
                self._note_outbound("fetch_url", current, 0, 0)
                raise WebError(f"连接 {current} 失败（{type(exc).__name__}）。", CODE_PROVIDER) from exc
            with closing(response):
                status = int(getattr(response, "status", 200) or 200)
                headers = getattr(response, "headers", None)
                content_type = str(headers.get("Content-Type") or "") if headers is not None else ""
                if status in _REDIRECT_CODES:
                    location = str(headers.get("Location") or "") if headers is not None else ""
                    if not location:
                        raise WebError(
                            f"抓取 {current}：HTTP {status} 重定向但响应里没有 Location 头。",
                            CODE_PROVIDER,
                            status=status,
                        )
                    current = self._redirect_target(current, location)
                    continue
                raw, byte_truncated = _read_capped(response, cap)
            raw = _decode_body(raw, str(getattr(response, "headers", {}).get("Content-Encoding", "") or "")); self._note_outbound("fetch_url", current, status, len(raw))  # 2026-09-23 真机验证抓到的坑：真实站点会返回压缩体（未解压的字节含 NUL），必须先按 Content-Encoding 解压
            kind = classify_content_type(content_type)
            if kind is None:
                raise WebError(
                    f"抓取 {current}：内容类型 {content_type or '（缺）'} 不是可读文本"
                    "（只支持 HTML / 纯文本 / JSON / XML）。",
                    CODE_UNSUPPORTED,
                    status=status,
                )
            if _looks_binary(raw):  # 2026-09-23 真机验证抓到的坑：真实 HTML 里也可能夹几个 NUL（实测该页 77809 字节里有 4 个、首个在第 39864 字节）⇒ 判据改成"看前缀 + 看密度"，不再一票否决
                raise WebError(
                    f"抓取 {current}：响应看着是**二进制**（含 NUL 字节）⇒ 不按文本处理。",
                    CODE_UNSUPPORTED,
                    status=status,
                )
            body = extract_text(raw, kind)
            return {
                "url": current,
                "status_code": status,
                "body": body,
                "truncated": bool(byte_truncated or len(body) >= FETCH_MAX_TEXT_CHARS),
                "content_type": content_type,
            }
        raise WebError(
            f"抓取 {url}：重定向超过 {MAX_REDIRECTS} 跳 ⇒ 停止跟随（只跟同源重定向，见草案 §3.3）。",
            CODE_BLOCKED_URL,
        )

    def _redirect_target(self, current: str, location: str) -> str:
        """重定向目标：只允许**同源**（跨源即拒）；目标串本身也要过一遍纯 URL 校验。"""
        target = urllib.parse.urljoin(current, location)
        target = check_fetch_url(target)
        if not same_origin(current, target):
            raise WebError(
                f"拒绝跨源重定向：{current} → {target}（只跟同源重定向，见草案 §3.3）。",
                CODE_BLOCKED_URL,
            )
        return target


def _decode_body(raw: bytes, content_encoding: str) -> bytes:
    """按 `Content-Encoding` 解压响应体（**2026-09-23 真机验证当场抓到的坑**）。

    实测抓 `https://api-docs.deepseek.com/...` 拿到的是**压缩体**，未解压的字节里含 `\\x00`，
    正好撞上下游"看着像二进制 ⇒ 拒绝"的判据 ⇒ 功能上等于"抓不到任何真实站点"。
    这里先用**标准库**解开（`gzip` / `deflate` 两种写法都认）。

    `br`（Brotli）标准库解不了 ⇒ **原样返回**，让下游照旧按二进制如实拒绝（不硬猜、不引新依赖）。
    解压失败同样原样返回（宁可下游拒绝，也不要抛在解压里）。
    """
    import gzip
    import zlib

    enc = (content_encoding or "").strip().lower()
    if not enc or enc == "identity":
        return raw
    try:
        if "gzip" in enc:
            return gzip.decompress(raw)
        if enc in ("deflate", "zlib"):
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)  # 裸 deflate（无 zlib 头）
    except (OSError, EOFError, zlib.error):
        return raw
    return raw


#: `_looks_binary` 的前缀窗口：真正的二进制（PNG/JPEG/ZIP/PDF/可执行）几乎都在**头几个字节**就有 NUL。
_BINARY_PREFIX_BYTES = 4096
#: 整体 NUL 密度阈值（千分比）：超过它才判"这体基本是二进制"。
_BINARY_NUL_PERMILLE = 10


def _looks_binary(raw: bytes) -> bool:
    """响应体是否**应当按二进制拒绝**（2026-09-23 真机验证后重写的判据）。

    原判据是"任何位置出现 `\\x00` 就拒绝"，实测**误杀真实网页**：`api-docs.deepseek.com` 那页是
    正常 HTML（`<!doctype html>` 开头、77809 字节、`text/html`、无压缩），却夹了 **4 个 NUL**
    （首个在第 39864 字节的中文正文中间）⇒ 功能上等于"抓不到任何真实站点"。

    新判据两条，任一命中才拒（**宁可放过夹了几个杂字节的文本，也不要把整页判死**）：
    1. **前缀有 NUL**（前 `_BINARY_PREFIX_BYTES` 字节内）—— 真二进制几乎必中；
    2. **整体 NUL 密度**超过 `_BINARY_NUL_PERMILLE` 千分比 —— 拦"通篇是二进制"的响应。
    放过的杂字节由下游 `decode(..., errors="replace")` 与正文提取兜底。
    """
    head = raw[:_BINARY_PREFIX_BYTES]
    if b"\x00" in head:
        return True
    if not raw:
        return False
    return raw.count(b"\x00") * 1000 > len(raw) * _BINARY_NUL_PERMILLE


# ── 域名名单（2026-09-24；草案 §3.3 里"域名单"的落点，工具面在 `tools/kb.py`）──────────────
# 为什么需要：`assert_public_host()` 管的是**地址类别**（回环 / 私网 / 链路本地…），管不了
# "这个库只许抓哪几个站"。名单是**用户的策略**，与地址类别正交 ⇒ 单独一层、单独一个失败码
# （`WEB_BLOCKED_DOMAIN`，与 `WEB_BLOCKED_URL` 分开，前端据此给不同的可照做提示）。
# 匹配口径（写死在下面两句里，单测直取）：**域本身或它的子域**命中即算（`example.com` 命中
# `a.b.example.com`），`deny` 优先于 `allow`，`allow` 为空 = 不限。
# 整段追加在文件末尾 ⇒ 上方既有 `<文件>:<行号>` 锚点零漂移。

#: 合法域名/主机名的形状（label 由字母数字与连字符组成、至少两段 —— `localhost`、中文域、
#: 通配符中段一律**不算合法**：写错的名字宁可被忽略，也不要变成"看起来配了其实没配"）。
_DOMAIN_RULE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")


def parse_domains(value: Any) -> tuple[str, ...]:
    """把**用户填的一行**域名清单解析成归一化元组（去重、保序；写错的项**忽略**）。

    容忍的写法（都归一成裸域）：`example.com`、`.example.com`、`*.example.com`、
    `https://example.com/docs`、`example.com:8443`；分隔符 = 逗号（中英）/ 分号 / 空白。
    归一后只保留**小写、无端口、无路径、无通配**的域；非法（含通配中段、中文、纯 IP 段数不足等）
    一律丢弃 —— 解析器宁可少一条，也不要把错名字当规则用。
    """
    text = str(value or "")
    out: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;，；、\s]+", text):
        item = raw.strip().lower()
        if not item:
            continue
        if "://" in item:
            item = (urllib.parse.urlsplit(item).hostname or "").lower()
        item = item.split("/")[0].split(":")[0].lstrip("*").strip(".")
        if not item or item in seen:
            continue
        if not _DOMAIN_RULE_RE.match(item):
            continue
        seen.add(item)
        out.append(item)
    return tuple(out)


def _domain_matches(host: str, rule: str) -> bool:
    """`host` 是否就是 `rule`，或是它的子域（`rule` 已由 `parse_domains()` 归一）。"""
    return host == rule or host.endswith("." + rule)


def domain_allowed(
    host: str, allow: Sequence[str] = (), deny: Sequence[str] = ()
) -> tuple[bool, str]:
    """域名是否放行 ⇒ `(allowed, reason)`；`reason ∈ deny | not-allow | open | empty`。

    判据（与 `WebClient._assert_domain` 共用；纯函数，单测直取）：
    ① 空主机 ⇒ 拒；② `deny` 命中 ⇒ 拒（**优先**）；③ `allow` 非空 ⇒ 只放行列内（含子域）；
    ④ `allow` 为空 ⇒ **不限**（仍受地址类别与出网总闸约束）。
    """
    name = str(host or "").strip().lower().strip(".")
    if not name:
        return False, "empty"
    if any(_domain_matches(name, rule) for rule in deny):
        return False, "deny"
    if allow:
        return (True, "allow") if any(_domain_matches(name, rule) for rule in allow) else (False, "not-allow")
    return True, "open"


def merge_domain_rules(
    machine_allow: Any = "",
    machine_deny: Any = "",
    kb_allow: Sequence[str] = (),
    kb_deny: Sequence[str] = (),
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """把**机器级**（`config/agent.json` 两键）与**库级**（能力插件 `web-fetch.config`）合成一套规则。

    **库级只能收紧，不能放宽**（安全铁律；见 `agent-capabilities.md` §3.3 与文件尾「域名名单」块）：

    | 输入 | `deny` | `allow` |
    |---|---|---|
    | 库级为空 | 机器级 | 机器级（含"空 = 不限"） |
    | 库级非空 | **并集**（机器级 ∪ 库级） | 机器级空 ⇒ 库级白名单；两边都非空 ⇒ **交集** |

    ⇒ "某个库把机器级禁止的域放开"在结构上不可能；库级想再收紧（尤其"只许抓这几个站"）随时可以。
    """
    allowed_machine = parse_domains(machine_allow)
    denied_machine = parse_domains(machine_deny)
    allowed_kb = tuple(str(rule).strip().lower() for rule in kb_allow if str(rule).strip())
    denied_kb = tuple(str(rule).strip().lower() for rule in kb_deny if str(rule).strip())
    denied = _union(denied_machine, denied_kb)
    if not allowed_kb:
        allowed = allowed_machine
    elif not allowed_machine:
        allowed = allowed_kb
    else:
        allowed = tuple(rule for rule in allowed_machine if rule in set(allowed_kb))
    return allowed, denied


def _union(*groups: Sequence[str]) -> tuple[str, ...]:
    """去重合并（保序：先机器级、后库级）。"""
    out: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in out:
                out.append(item)
    return tuple(out)
