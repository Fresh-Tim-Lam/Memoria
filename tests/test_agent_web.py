# 配套单测：被测调用面语义移植自 deepseek-harness `packages/web`（`web-search-deepseek` 的
# Anthropic 兼容面线格式与结果归一、`web-fetch-http` 的 URL 策略 / 内容分类、`web/tool-web` 的
# `{sources[], truncated}` 形状）（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""联网（N 线）的离线单测：**全程不触网**（`opener` / `resolver` / `socket.getaddrinfo` 全注入）。

覆盖：

① **归一**：罐装 Anthropic 响应 → `{sources:[{url,title,snippet}], truncated}`（引文取自 `text` 块的
   `citations[]`、按 URL 去重、超上限截断）；**没有 `web_search_tool_result` 块 = `WEB_PROVIDER_ERROR`**
   （坏形状：缺块 / `content` 不是数组 / 非 JSON 对象）；
② **基址推导**：DeepSeek 主机自动推导、显式 `search_base_url` 优先、**异主机缺显式值时 fail-closed**；
   线格式：`POST {base}/messages`、体带原生 server tool、头 `x-api-key` + `authorization`（密钥只在这两处）；
③ **抓取安全**（草案 §3.3）：仅 http(s)、拒内嵌凭据、DNS 解析失败即拒、
   私网 / 回环 / 链路本地 / 组播 / 保留 / 未指定**逐地址**拒、只跟**同源**重定向且**逐跳重校验**、
   跳数上限、字节上限（**绝不无界 `read()`**）、HTML 去脚本 / 样式 / 标签；
④ **pending 落点**：抓取结果进 `storage/pending.py::save_pending` 的 `kind=web` 条目（同 URL 幂等），
   回给模型的只有「路径 + 摘要 + 长度」，**正文不进上下文**；
⑤ **出网闸**：`agent.json: enabled=false` ⇒ 两把工具都拒（`WEB_DISABLED`）、**一次网络动作都不做**；
⑥ **审计**：每次出网追加一条 `net/request` 会话事件（`{tool,host,url,status,bytes}`），
   且**密钥与正文都不落进会话日志**。
"""

from __future__ import annotations

import email.message
import io
import json
import socket
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent import web as web_mod
from memoria.services.agent.llm import config as config_mod
from memoria.services.agent.llm.config import AgentConfig
from memoria.services.agent.llm.types import ToolCall
from memoria.services.agent.tools import KB_TOOL_NAMES, ToolRegistry, build_kb_tools
from memoria.services.agent.tools.kb import WEB_DISABLED_CODE
from memoria.storage.pending import load_pending, pending_path

SECRET = "sk-test-only-not-a-real-key-1234567890"
SESSION_ID = "sess-web"
#: 一个「看起来像公网」的地址：所有注入的 resolver 都返回它（真正的地址类别由分类器单测覆盖）。
PUBLIC_IP = "93.184.216.34"

CANNED_SEARCH = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "content": [
        {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "x"}},
        {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_1",
            "content": [
                {"type": "web_search_result", "url": "https://a.example/1", "title": "A 篇", "page_age": "2026-01-01"},
                {"type": "web_search_result", "url": "https://b.example/2", "title": "B 篇"},
                # 同一 URL 出现两次（`max_uses > 1` 时会这样）⇒ 只留一条
                {"type": "web_search_result", "url": "https://a.example/1", "title": "A 篇（重复）"},
            ],
        },
        {
            "type": "text",
            "text": "见上面两条来源。",
            "citations": [
                {"type": "web_search_result_location", "url": "https://a.example/1", "cited_text": "A 的引文。"},
                {"type": "web_search_result_location", "url": "https://b.example/2", "cited_text": "B 的引文。"},
            ],
        },
    ],
}


class _Response:
    """响应替身：`read(n)` 语义照 `http.client`（可多次读、读完返回空串）。"""

    def __init__(self, body: bytes = b"", *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self._offset = 0
        self.status = status
        self.headers = dict(headers or {})
        self.closed = False

    def read(self, size: int | None = None) -> bytes:
        if size is None or size < 0:
            chunk = self._body[self._offset :]
        else:
            chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class _Opener:
    """opener 替身：**`timeout` 是关键字参数**（照仓库纪律"绝不位置传超时"）。"""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.requests: list[Any] = []
        self.timeouts: list[Any] = []

    def __call__(self, request: Any, *, timeout: Any = None) -> Any:
        self.requests.append(request)
        self.timeouts.append(timeout)
        response = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def _config(**overrides: Any) -> AgentConfig:
    """一份「指向 DeepSeek 官方端点」的配置（不触网：opener 全注入）。"""
    values: dict[str, Any] = {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": SECRET,
        "model": "deepseek-chat",
    }
    values.update(overrides)
    return AgentConfig(**values)


def _client(opener: Any, *, config: AgentConfig | None = None, on_outbound: Any = None) -> Any:
    return web_mod.WebClient(
        config or _config(),
        opener=opener,
        resolver=lambda host, port=None: [PUBLIC_IP],
        on_outbound=on_outbound,
    )


def _json_response(payload: Any, *, status: int = 200) -> _Response:
    return _Response(json.dumps(payload).encode("utf-8"), status=status, headers={"Content-Type": "application/json"})


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小库根（联网工具只按库根寻址）。"""
    root = tmp_path / "kb"
    (root / ".memoria").mkdir(parents=True)
    return root


@pytest.fixture()
def enabled_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """写出「出网开着 + 指向 DeepSeek」的本地配置，并清掉可能存在的环境变量（保证可复现）。"""
    for name in ("MEMORIA_AGENT_BASE_URL", "MEMORIA_AGENT_API_KEY", "MEMORIA_AGENT_MODEL", "MEMORIA_AGENT_TIMEOUT_S"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "agent.json"
    path.write_text(
        json.dumps({"base_url": "https://api.deepseek.com/v1", "api_key": SECRET, "model": "deepseek-chat", "enabled": True}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMORIA_AGENT_CONFIG", str(path))
    return path


# —— ① 检索响应归一 ——


def test_search_normalizes_sources_with_citation_snippets() -> None:
    opener = _Opener(_json_response(CANNED_SEARCH))
    result = _client(opener).search("多层感知机")

    assert result == {
        "sources": [
            {"url": "https://a.example/1", "title": "A 篇", "snippet": "A 的引文。"},
            {"url": "https://b.example/2", "title": "B 篇", "snippet": "B 的引文。"},
        ],
        "truncated": False,
    }
    assert opener.timeouts == [config_mod.DEFAULT_SEARCH_TIMEOUT_S]  # 超时按关键字传入


def test_search_truncates_to_max_results() -> None:
    result = web_mod.parse_search_response(CANNED_SEARCH, max_results=1)

    assert result["truncated"] is True
    assert [source["url"] for source in result["sources"]] == ["https://a.example/1"]


@pytest.mark.parametrize(
    "payload",
    [
        {"content": [{"type": "text", "text": "没有联网结果的散文"}]},
        {"content": "不是数组"},
        {},
    ],
    ids=["no-result-block", "content-not-list", "empty"],
)
def test_search_without_result_block_is_provider_error(payload: Any) -> None:
    """**没有 `web_search_tool_result` 块 = 失败**（上游同口径：不拿模型散文冒充搜索结果）。"""
    with pytest.raises(web_mod.WebError) as caught:
        web_mod.parse_search_response(payload)
    assert caught.value.code == web_mod.CODE_PROVIDER


def test_search_malformed_json_body_is_provider_error() -> None:
    opener = _Opener(_Response(b"<html>not json</html>", headers={"Content-Type": "text/html"}))
    with pytest.raises(web_mod.WebError) as caught:
        _client(opener).search("x")
    assert caught.value.code == web_mod.CODE_PROVIDER


def test_search_body_and_headers_shape() -> None:
    """线格式逐字段对齐上游 `provider.ts:204-237`（密钥只出现在两个头里）。"""
    body = web_mod.build_search_body("联想记忆", "deepseek-chat", 4)
    assert body == {
        "model": "deepseek-chat",
        "max_tokens": web_mod.SEARCH_MAX_TOKENS,
        "messages": [{"role": "user", "content": "联想记忆"}],
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
    }

    headers = web_mod.build_search_headers(SECRET)
    assert headers["x-api-key"] == SECRET
    assert headers["authorization"] == f"Bearer {SECRET}"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["content-type"] == "application/json"
    assert sorted(key for key, value in headers.items() if SECRET in value) == ["authorization", "x-api-key"]


def test_search_requires_api_key() -> None:
    from memoria.services.agent.llm.errors import AuthError

    opener = _Opener(_json_response(CANNED_SEARCH))
    with pytest.raises(AuthError):
        _client(opener, config=_config(api_key="")).search("x")


def test_search_never_logs_the_api_key(caplog: pytest.LogCaptureFixture) -> None:
    """仓库铁律：密钥**绝不进日志**（连 DEBUG 级也不行）。"""
    import logging

    opener = _Opener(_json_response(CANNED_SEARCH))
    with caplog.at_level(logging.DEBUG):
        _client(opener).search("多层感知机")
    assert caplog.text and "POST" in caplog.text, "DEBUG 级应留下一次调用痕迹（便于复盘）"
    assert SECRET not in caplog.text


# —— ② 基址推导 ——


def test_anthropic_base_url_derived_for_deepseek() -> None:
    assert web_mod.anthropic_base_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/anthropic/v1"
    assert web_mod.anthropic_base_url("https://api.deepseek.com") == web_mod.DEEPSEEK_ANTHROPIC_BASE


def test_anthropic_base_url_explicit_override_wins() -> None:
    assert (
        web_mod.anthropic_base_url("https://gateway.example/v1", "https://gateway.example/anthropic/v1/")
        == "https://gateway.example/anthropic/v1"
    )


def test_anthropic_base_url_foreign_host_without_override_fails_closed() -> None:
    with pytest.raises(web_mod.WebError) as caught:
        web_mod.anthropic_base_url("https://gateway.example/v1")
    assert caught.value.code == web_mod.CODE_CONFIG
    assert "search_base_url" in str(caught.value), "报错要点名该填哪个键（可照做）"


# —— ③ 抓取安全面 ——


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://a.example/x", web_mod.CODE_INVALID_URL),
        ("file:///C:/x.txt", web_mod.CODE_INVALID_URL),
        ("https://", web_mod.CODE_INVALID_URL),
        ("https://user:pass@a.example/x", web_mod.CODE_BLOCKED_URL),
        ("https://" + "a" * 9000 + ".example/x", web_mod.CODE_INVALID_URL),
    ],
    ids=["ftp", "file", "no-host", "credentials", "too-long"],
)
def test_check_fetch_url_rejects(url: str, code: str) -> None:
    with pytest.raises(web_mod.WebError) as caught:
        web_mod.check_fetch_url(url)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("address", "reason"),
    [
        ("127.0.0.1", "回环"),
        ("10.1.2.3", "私网"),
        ("192.168.1.1", "私网"),
        ("172.16.0.9", "私网"),
        ("169.254.169.254", "链路本地"),  # 云元数据地址
        ("224.0.0.1", "组播"),
        ("240.0.0.1", "保留"),
        ("0.0.0.0", "未指定"),
        ("::1", "回环"),
        ("fd00::1", "私网"),
        ("fe80::1", "链路本地"),
        ("not-an-ip", "不是合法 IP（not-an-ip）"),
    ],
)
def test_blocked_address_reason(address: str, reason: str) -> None:
    assert web_mod.blocked_address_reason(address) == reason
    assert web_mod.blocked_address_reason(PUBLIC_IP) is None


def test_fetch_rejects_private_address_after_resolution() -> None:
    """SSRF 防护的落点：主机名解析到私网地址即拒（**不看主机名字面**）。"""
    opener = _Opener(_Response(b"ok"))
    client = web_mod.WebClient(_config(), opener=opener, resolver=lambda host, port=None: ["10.0.0.5"])
    with pytest.raises(web_mod.WebError) as caught:
        client.fetch("http://internal.example/secret")
    assert caught.value.code == web_mod.CODE_BLOCKED_URL
    assert opener.requests == [], "拒绝必须发生在**发请求之前**"


def test_fetch_rejects_private_address_in_any_resolved_answer() -> None:
    """**逐地址**校验：只要解析结果里有**一个**私网/回环地址就拒（多 A 记录同罪）。"""
    opener = _Opener(_Response(b"ok"))
    client = web_mod.WebClient(
        _config(), opener=opener, resolver=lambda host, port=None: [PUBLIC_IP, "10.0.0.7"]
    )
    with pytest.raises(web_mod.WebError) as caught:
        client.fetch("http://mixed.example/x")
    assert caught.value.code == web_mod.CODE_BLOCKED_URL
    assert opener.requests == []


def test_fetch_resolution_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(web_mod.WebError) as caught:
        web_mod.resolve_addresses("no-such-host.example")
    assert caught.value.code == web_mod.CODE_BLOCKED_URL


def test_fetch_extracts_html_text_and_keeps_timeout_keyword() -> None:
    page = "<html><head><style>p{color:red}</style></head><body><h1>标题</h1><script>var x=1;</script><p>正文&amp;更多</p></body></html>"
    opener = _Opener(_Response(page.encode("utf-8"), headers={"Content-Type": "text/html; charset=utf-8"}))
    fetched = _client(opener).fetch("https://a.example/page")

    assert fetched["url"] == "https://a.example/page"
    assert fetched["status_code"] == 200
    assert fetched["content_type"] == "text/html; charset=utf-8"
    assert fetched["truncated"] is False
    assert "标题" in fetched["body"] and "正文&更多" in fetched["body"]
    assert "color:red" not in fetched["body"] and "var x=1" not in fetched["body"]  # 脚本 / 样式整块丢弃
    assert opener.timeouts == [config_mod.DEFAULT_FETCH_TIMEOUT_S]


def test_fetch_caps_bytes_without_unbounded_read() -> None:
    payload = b"<p>" + b"x" * 5000 + b"</p>"
    opener = _Opener(_Response(payload, headers={"Content-Type": "text/html"}))
    fetched = _client(opener).fetch("https://a.example/big", max_bytes=1024)

    assert fetched["truncated"] is True
    assert len(fetched["body"]) <= 1024


def test_fetch_rejects_unsupported_content_type_and_binary() -> None:
    opener = _Opener(_Response(b"\x89PNG\r\n\x1a\n", headers={"Content-Type": "image/png"}))
    with pytest.raises(web_mod.WebError) as caught:
        _client(opener).fetch("https://a.example/i.png")
    assert caught.value.code == web_mod.CODE_UNSUPPORTED

    opener = _Opener(_Response(b"a\x00b", headers={"Content-Type": "text/plain"}))
    with pytest.raises(web_mod.WebError) as caught:
        _client(opener).fetch("https://a.example/bin")
    assert caught.value.code == web_mod.CODE_UNSUPPORTED


def test_fetch_follows_same_origin_redirect_and_rechecks_each_hop() -> None:
    seen: list[str] = []

    def resolver(host: str, port: int | None = None) -> list[str]:
        seen.append(host)
        return [PUBLIC_IP]

    opener = _Opener(
        _Response(b"", status=302, headers={"Location": "/moved"}),
        _Response(b"<p>ok</p>", headers={"Content-Type": "text/html"}),
    )
    client = web_mod.WebClient(_config(), opener=opener, resolver=resolver)
    fetched = client.fetch("https://a.example/start")

    assert fetched["url"] == "https://a.example/moved"
    assert seen == ["a.example", "a.example"], "每一跳都要重跑地址校验"
    assert len(opener.requests) == 2


def test_fetch_rejects_cross_origin_redirect() -> None:
    opener = _Opener(_Response(b"", status=302, headers={"Location": "https://evil.example/x"}))
    with pytest.raises(web_mod.WebError) as caught:
        _client(opener).fetch("https://a.example/start")
    assert caught.value.code == web_mod.CODE_BLOCKED_URL
    assert len(opener.requests) == 1, "跨源跳转不发出第二跳"


def test_fetch_caps_redirect_hops() -> None:
    opener = _Opener(_Response(b"", status=302, headers={"Location": "/loop"}))  # 一直同源跳
    with pytest.raises(web_mod.WebError) as caught:
        _client(opener).fetch("https://a.example/loop")
    assert caught.value.code == web_mod.CODE_BLOCKED_URL
    assert len(opener.requests) == web_mod.MAX_REDIRECTS + 1


def test_fetch_http_error_carries_status_and_message() -> None:
    """HTTP 4xx/5xx ⇒ 归 `WEB_PROVIDER_ERROR` 并带上状态码与端点错误信封里的 message。"""
    headers = email.message.Message()
    headers["Content-Type"] = "application/json"
    error = urllib.error.HTTPError(
        "https://a.example/x", 429, "Too Many Requests", headers, io.BytesIO('{"error": {"message": "限流"} }'.encode("utf-8"))
    )
    opener = _Opener(error)
    with pytest.raises(web_mod.WebError) as caught:
        _client(opener).fetch("https://a.example/x")
    assert caught.value.code == web_mod.CODE_PROVIDER and caught.value.status == 429
    assert "限流" in str(caught.value)


def test_same_origin_semantics() -> None:
    assert web_mod.same_origin("https://a.example/x", "https://a.example:443/y")
    assert web_mod.same_origin("http://a.example/x", "http://a.example:80/y")
    assert not web_mod.same_origin("https://a.example/x", "http://a.example/y")
    assert not web_mod.same_origin("https://a.example/x", "https://a.example:8443/y")
    assert not web_mod.same_origin("https://a.example/x", "https://sub.a.example/y")


# —— ④ pending 落点 ——


def test_save_fetched_page_lands_in_pending_and_returns_pointer(kb: Path) -> None:
    fetched = {
        "url": "https://a.example/page",
        "status_code": 200,
        "body": "第一段正文。\n\n第二段正文。",
        "truncated": False,
        "content_type": "text/html",
    }
    saved = web_mod.save_fetched_page(str(kb), fetched["url"], fetched)

    assert saved["path"] == pending_path(str(kb))
    assert saved["chars"] == len(fetched["body"])
    assert saved["summary"] == "第一段正文。 第二段正文。"

    store = load_pending(str(kb)) or {}
    items = [item for item in store["items"] if item.get("kind") == "web"]
    assert len(items) == 1
    item = items[0]
    assert item["pending_id"] == saved["pending_id"] and item["status"] == "pending"
    assert item["url"] == fetched["url"] and item["chars"] == len(fetched["body"])
    assert "第一段正文。" in item["summary"]

    # 同 URL 再抓一次 ⇒ 覆盖同一条（幂等，不堆重复条目）
    web_mod.save_fetched_page(str(kb), fetched["url"], fetched)
    store = load_pending(str(kb)) or {}
    assert len([item for item in store["items"] if item.get("kind") == "web"]) == 1


# —— ⑤ / ⑥ 工具层：出网闸 + 审计 ——


def _registry(kb: Path) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb), session_id=SESSION_ID))


def _invoke(kb: Path, name: str, **arguments: Any) -> Any:
    return _registry(kb).invoke(ToolCall(id="c1", name=name, arguments=json.dumps(arguments)))


def _session_text(kb: Path) -> str:
    path = kb / ".memoria" / "agent" / "sessions" / f"{SESSION_ID}.jsonl"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


@pytest.mark.parametrize("name", ["web_search", "fetch_url"])
def test_tools_are_registered_read_only(tmp_path: Path, name: str) -> None:
    root = tmp_path / "kb2"
    (root / ".memoria").mkdir(parents=True)
    registry = _registry(root)

    assert KB_TOOL_NAMES[-6:-4] == ("web_search", "fetch_url"), "其后另有脚本工作区四把（2026-09-24，§3.4）"
    tool = registry.get(name)
    assert tool is not None and tool.read_only, "只读 ⇒ 按既有策略免审批"
    assert tool.parameters["additionalProperties"] is False


@pytest.mark.parametrize(
    ("name", "arguments"),
    [("web_search", {"query": "x"}), ("fetch_url", {"url": "https://a.example/x"})],
)
def test_tools_are_gated_off_when_outbound_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, arguments: dict[str, Any]
) -> None:
    """默认关 = `enabled: false`：两把工具都拒、给可照做的提示，且**一次网络动作都不做**。"""
    for env_name in ("MEMORIA_AGENT_BASE_URL", "MEMORIA_AGENT_API_KEY", "MEMORIA_AGENT_MODEL"):
        monkeypatch.delenv(env_name, raising=False)
    path = tmp_path / "agent.json"
    path.write_text(json.dumps({"api_key": SECRET, "enabled": False}), encoding="utf-8")
    monkeypatch.setenv("MEMORIA_AGENT_CONFIG", str(path))

    def _explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("出网关闭时不得有任何网络动作")

    monkeypatch.setattr(web_mod, "WebClient", _explode)
    root = tmp_path / "kb3"
    (root / ".memoria").mkdir(parents=True)
    result = _invoke(root, name, **arguments)

    assert result.is_error and result.output.code == WEB_DISABLED_CODE
    assert "出网" in result.content and "enabled" in result.content
    assert _session_text(root) == "", "被闸住的调用不写任何会话事件"


def test_web_search_tool_returns_sources_and_records_net_event(
    kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opener = _Opener(_json_response(CANNED_SEARCH))
    _patch_client(monkeypatch, opener, config=_config())

    result = _invoke(kb, "web_search", query="多层感知机")

    assert not result.is_error
    assert "https://a.example/1" in result.content and "A 篇" in result.content and "A 的引文。" in result.content
    assert "见上面两条来源。" not in result.content, "正文散文不进结果（只给标题 + URL + 摘要）"
    assert SECRET not in result.content

    events = [json.loads(line) for line in _session_text(kb).splitlines() if line.strip()]
    net = [event for event in events if event.get("type") == "net/request"]
    assert len(net) == 1, "每次出网一条审计事件"
    data = net[0]["data"]
    assert data["tool"] == "web_search" and data["status"] == 200 and data["bytes"] > 0
    assert data["host"] == "api.deepseek.com" and data["url"].endswith("/anthropic/v1/messages")
    assert SECRET not in _session_text(kb), "密钥绝不落进会话日志"


def test_fetch_url_tool_returns_pointer_not_body(
    kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "抓到的正文第一句。" + "正文" * 500
    opener = _Opener(_Response(("<p>%s</p>" % body).encode("utf-8"), headers={"Content-Type": "text/html"}))
    _patch_client(monkeypatch, opener, config=_config())

    result = _invoke(kb, "fetch_url", url="https://a.example/page")

    assert not result.is_error
    assert "落库路径：" in result.content and pending_path(str(kb)) in result.content
    assert "摘要：" in result.content and "长度：" in result.content
    assert body not in result.content, "长文不进上下文（只回路径 + 摘要 + 长度）"

    store = load_pending(str(kb)) or {}
    item = [row for row in store["items"] if row.get("kind") == "web"][0]
    assert item["url"] == "https://a.example/page" and item["chars"] == len(body)

    net = [json.loads(line) for line in _session_text(kb).splitlines() if '"net/request"' in line]
    assert len(net) == 1 and net[0]["data"]["tool"] == "fetch_url"


def test_tools_report_provider_failure_as_tool_error(
    kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _Opener(_json_response({"content": "not a list"})), config=_config())

    result = _invoke(kb, "web_search", query="x")

    assert result.is_error and result.output.code == web_mod.CODE_PROVIDER
    assert result.content.startswith("Error: web_search:")


def test_web_search_rejects_blank_query_without_any_outbound(
    kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _Opener(_json_response(CANNED_SEARCH)), config=_config())

    result = _invoke(kb, "web_search", query="   ")

    assert result.is_error and result.output.code == "INVALID_ARGUMENTS"
    assert _session_text(kb) == ""


# —— ③′ 真机复验（2026-09-23）当场抓到的两个坑：压缩体 + 误杀正常网页 ——

def test_fetch_decodes_gzip_encoded_body() -> None:
    """真实站点会返回 `Content-Encoding: gzip`：未解压的字节里含 NUL，会误撞二进制判据。"""
    import gzip

    payload = ("<p>解压之后才看得见的中文正文。</p>" * 40).encode("utf-8")
    opener = _Opener(
        _Response(gzip.compress(payload), headers={"Content-Type": "text/html", "Content-Encoding": "gzip"})
    )

    fetched = _client(opener).fetch("https://a.example/gz")

    assert fetched["status_code"] == 200
    assert "解压之后才看得见的中文正文。" in fetched["body"]


def test_fetch_accepts_real_html_with_sparse_nul_bytes() -> None:
    """**真机复验（2026-09-23）的核心回归**：`api-docs.deepseek.com` 那页是正常 HTML
    （`<!doctype html>` 开头、77809 字节、`text/html`、无压缩），却夹了 **4 个 NUL**、
    首个在第 39864 字节的中文正文中间 ⇒ 旧判据"任何位置出现 NUL 就拒"把整页判死，
    功能上等于**抓不到任何真实站点**。
    """
    text = "<!doctype html><html><body>" + "中文正文" * 3000 + "</body></html>"
    raw = text.encode("utf-8")
    at = 40000  # 落在 `_BINARY_PREFIX_BYTES` 窗口之外
    raw = raw[:at] + b"\x00" + raw[at:] + b"\x00\x00\x00"  # 共 4 个，密度远低于阈值

    fetched = _client(_Opener(_Response(raw, headers={"Content-Type": "text/html"}))).fetch("https://a.example/zh")

    assert fetched["status_code"] == 200
    assert "中文正文" in fetched["body"]
    assert "doctype" not in fetched["body"], "标签照旧剥掉（放过杂字节不等于放过整页的正文提取）"


def test_looks_binary_judgement_boundaries() -> None:
    """新判据的两条边界：**前缀有 NUL** 或 **整体密度超阈值**才拒；少数杂字节放过。"""
    assert web_mod._looks_binary(b"") is False
    assert web_mod._looks_binary(b"a\x00b") is True, "前缀窗口内有 NUL ⇒ 拒（旧用例的语义仍在）"
    assert web_mod._looks_binary(b"x" * 5000 + b"\x00" * 3) is False, "窗口外三个杂字节 ⇒ 放过"
    assert web_mod._looks_binary(b"x" * 5000 + b"\x00" * 100) is True, "通篇二进制（密度 ≈20‰）⇒ 拒"


def _patch_client(monkeypatch: pytest.MonkeyPatch, opener: Any, *, config: AgentConfig) -> None:
    """把工具层内部构造的 `WebClient` 换成**注入 opener / resolver** 的实例（单测不触网）。

    只替换构造参数、不动 `on_outbound`（审计回调仍由工具层传入 ⇒ 审计路径被真实测到），
    因此联网工具的"出网 → 审计 → 落库"三条链路在本文件里是**端到端**跑通的。
    """
    real = web_mod.WebClient

    def factory(_config: Any, **kwargs: Any) -> Any:
        return real(config, opener=opener, resolver=lambda host, port=None: [PUBLIC_IP], **kwargs)

    monkeypatch.setattr(web_mod, "WebClient", factory)
    # 2026-09-24：`_web_client()` 会把**机器级 + 库级**域名名单合并后显式传给 WebClient
    # ⇒ 这里让那条路径里的 `load_config()` 也返回**同一份注入配置**，两处才不会各说各话
    # （合并语义本身另有专门用例：`test_merge_domain_rules_only_tightens` 等）。
    from memoria.services.agent.llm import config as config_mod

    monkeypatch.setattr(config_mod, "load_config", lambda env=None: config)


# —— ⑨ 域名名单（2026-09-24；草案 §3.3「域名单」的落点）——


def test_parse_domains_normalises_and_ignores_junk() -> None:
    """用户那一行里的各种写法都归一成裸域；**写错的项一律忽略**（不猜、不报错）。"""
    parsed = web_mod.parse_domains(
        "Example.COM, *.Sub.Example.com, https://x.example.org/docs, a.io:8443, 、b.cn; \n"
        "localhost, 中文.com, a.*.b.com, -bad.com, x_y.com, ,"
    )
    assert parsed == ("example.com", "sub.example.com", "x.example.org", "a.io", "b.cn")
    assert web_mod.parse_domains("") == () and web_mod.parse_domains(None) == ()


def test_domain_allowed_semantics() -> None:
    """`deny` 优先；`allow` 非空 ⇒ 只放行列内**及其子域**；两表皆空 ⇒ 不限（仍受地址类别约束）。"""
    assert web_mod.domain_allowed("example.com") == (True, "open")
    allow = web_mod.parse_domains("example.com")
    deny = web_mod.parse_domains("ads.example.com")
    assert web_mod.domain_allowed("a.example.com", allow, deny) == (True, "allow")
    assert web_mod.domain_allowed("ads.example.com", allow, deny) == (False, "deny")
    assert web_mod.domain_allowed("other.org", allow, deny) == (False, "not-allow")
    assert web_mod.domain_allowed("evil-example.com", allow, deny) == (False, "not-allow"), "后缀不许'看着像就放行'"
    assert web_mod.domain_allowed("", allow, deny) == (False, "empty")
    assert web_mod.domain_allowed("EXAMPLE.com.", allow, deny) == (True, "allow"), "大小写与尾点要归一"


def test_fetch_denied_domain_is_rejected_before_any_dns_or_request() -> None:
    """被名单拒的域**连 DNS 都不解析**（名单先于地址校验）⇒ 一个请求、一次解析都没有。"""
    seen: list[Any] = []
    response = _Response(b"<p>ok</p>", headers={"Content-Type": "text/html"})

    def opener(request: Any, *, timeout: Any = None) -> Any:
        seen.append("request")
        return response

    def resolver(host: str, port: int | None = None) -> list[str]:
        seen.append("dns")
        return [PUBLIC_IP]

    client = web_mod.WebClient(_config(fetch_deny_domains="example.com"), opener=opener, resolver=resolver)
    with pytest.raises(web_mod.WebError) as caught:
        client.fetch("https://a.example.com/x")
    assert caught.value.code == web_mod.CODE_BLOCKED_DOMAIN
    assert seen == [], "名单先于 DNS：被拒的域不该触发解析，更不该发请求"


def test_fetch_allowlist_blocks_everything_else() -> None:
    """`allow` 非空 ⇒ 只放行列内域；域外的抓取被拒且**真的没出网**。"""
    opener = _Opener(_Response(b"<p>ok</p>", headers={"Content-Type": "text/html"}))
    client = _client(opener, config=_config(fetch_allow_domains="docs.python.org, github.com"))

    fetched = client.fetch("https://docs.python.org/3/")
    assert fetched["status_code"] == 200
    with pytest.raises(web_mod.WebError) as caught:
        client.fetch("https://example.com/")
    assert caught.value.code == web_mod.CODE_BLOCKED_DOMAIN
    assert len(opener.requests) == 1, "只有放行的那一次真的出网"


def test_net_domains_rpc_returns_rules_and_ignored_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """设置页读的那条 RPC：回**归一化结果**与"忽略了几处"，人一眼能看出配没配上。"""
    from memoria.presentation.api.ui import UIAPI

    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("MEMORIA_AGENT_CONFIG", raising=False)
    root = tmp_path / "kb2"
    (root / ".memoria").mkdir(parents=True)
    api = UIAPI(kb_path=str(root))

    saved = api.agent_save_config({"fetch_allow_domains": "example.com, *.sub.example.org, 中文.com"})
    assert saved["status"] == "ok", saved
    data = api.agent_net_domains()
    assert data["status"] == "ok"
    assert data["allow_rules"] == ["example.com", "sub.example.org"]
    assert data["ignored"]["allow"] == 1, "写不出来的那条要如实计数（不是静默吞掉）"
    assert data["deny_rules"] == [] and data["code"] == web_mod.CODE_BLOCKED_DOMAIN


def test_fetch_tool_surfaces_domain_block_code(kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """工具面：抓被名单禁的域 ⇒ 工具结果带 `WEB_BLOCKED_DOMAIN`（前端据此给可照做的提示）。"""
    _patch_client(
        monkeypatch,
        _Opener(_Response(b"<p>ok</p>", headers={"Content-Type": "text/html"})),
        config=_config(fetch_deny_domains="example.com"),
    )
    result = _invoke(kb, "fetch_url", url="https://a.example.com/page")
    assert result.is_error and result.output.code == web_mod.CODE_BLOCKED_DOMAIN


# —— ⑩ 库级名单合并 + 工具级能力闸（2026-09-24；N 线插件化第二片）——


def test_merge_domain_rules_only_tightens() -> None:
    """合并语义（安全铁律）：`deny` 并集、`allow` 交集 ⇒ **库级只能收紧，不能放宽**。"""
    merged_allow, merged_deny = web_mod.merge_domain_rules("a.com, b.com", "x.com", ["b.com"], ["y.com"])
    assert merged_allow == ("b.com",), "两边都有 allow ⇒ 取交集（库级放不出机器级的圈）"
    assert merged_deny == ("x.com", "y.com"), "deny 取并集"

    assert web_mod.merge_domain_rules("", "x.com", ["only.org"], []) == (("only.org",), ("x.com",)), "机器级不限时库级可当白名单"
    assert web_mod.merge_domain_rules("a.com, b.com", "", [], []) == (("a.com", "b.com"), ()), "库级没配 ⇒ 就是机器级那份"
    assert web_mod.merge_domain_rules("a.com", "", ["c.com"], []) == ((), ()), "交集为空 ⇒ 该库谁都抓不了（宁可全拒，也不放宽）"


def test_kb_level_domain_rules_are_applied_by_the_fetch_tool(
    kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """库级参数（能力插件 `web-fetch.config`）经 `_web_client()` 合并后**真的生效**。"""
    from memoria.services.agent import plugins as plugins_mod

    monkeypatch.setattr(
        plugins_mod,
        "kb_enablement",
        lambda _kb: {"web-fetch": {"on": True, "config": {"deny": ["example.com"]}}},
    )
    opener = _Opener(_Response(b"<p>ok</p>", headers={"Content-Type": "text/html"}))
    _patch_client(monkeypatch, opener, config=_config())  # 机器级没有任何名单

    blocked = _invoke(kb, "fetch_url", url="https://a.example.com/page")
    assert blocked.is_error and blocked.output.code == web_mod.CODE_BLOCKED_DOMAIN
    assert opener.requests == [], "被库级名单拒 ⇒ 一个请求都不发"
    assert not _invoke(kb, "fetch_url", url="https://docs.python.org/3/").is_error


def test_tool_level_capability_gate_blocks_net_tools(
    kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**工具级能力闸**：本库把 `net.fetch` 关掉 ⇒ `fetch_url` 被拒且**零网络动作**。

    这是 N 线插件化的可测证据（`plan.validate_plan()` 够不到不走 plan 的工具，闸落在 `_outbound_guard`）。
    """
    import types

    from memoria.services.agent import plugins as plugins_mod

    monkeypatch.setattr(
        plugins_mod,
        "active_plugins",
        lambda _kb: types.SimpleNamespace(enforced=True, tool_ids=frozenset({"net.search"})),
    )

    def _explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("能力闸拦住时不得有任何网络动作")

    monkeypatch.setattr(web_mod, "WebClient", _explode)
    result = _invoke(kb, "fetch_url", url="https://docs.python.org/3/")
    assert result.is_error and result.output.code == "capability_disabled"
    assert "能力插件" in result.content and _session_text(kb) == "", "被闸住的调用不写会话事件"


def test_tool_level_capability_gate_gates_off_when_no_declaration(
    kb: Path, enabled_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """口径 2：**一份声明都没有 ⇒ 不闸**（行为同接线前）—— 残缺拷贝里不该突然联网工具全废。"""
    import types

    from memoria.services.agent import plugins as plugins_mod

    monkeypatch.setattr(
        plugins_mod,
        "active_plugins",
        lambda _kb: types.SimpleNamespace(enforced=False, tool_ids=frozenset()),
    )
    opener = _Opener(_Response(b"<p>ok</p>", headers={"Content-Type": "text/html"}))
    _patch_client(monkeypatch, opener, config=_config())
    assert not _invoke(kb, "fetch_url", url="https://docs.python.org/3/").is_error
