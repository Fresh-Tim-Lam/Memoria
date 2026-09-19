# 配套单测：被测调用面语义移植自 deepseek-harness packages/llm/*（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""agent LLM 层离线单测：全部使用本地 `http.server` stub 或注入 opener，不联网。"""

from __future__ import annotations

import http.client
import io
import json
import socket
import ssl
import threading
import urllib.error
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from memoria.services.agent.llm import (
    AgentConfig,
    AgentLlmError,
    AuthError,
    ConfigError,
    FinishEvent,
    FinishReason,
    LlmRequest,
    LlmTimeoutError,
    Message,
    OpenAICompatibleProvider,
    ProviderError,
    RateLimited,
    RetryPolicy,
    Role,
    TextDelta,
    ToolCallDelta,
    Usage,
    UsageEvent,
    UsageMeter,
    delay_for,
    estimate_usage,
    is_retryable,
    iter_with_retry,
    local_delay,
    mask_secret,
    normalize_api_key,
    run_with_retry,
)
from memoria.services.agent.llm.errors import (
    EMPTY_RESPONSE_CODE,
    INVALID_REQUEST_CODE,
    RETRYABLE_CODES,
    TRANSPORT_CODE,
    UNREACHABLE_CODE,
    is_unreachable,
)
from memoria.services.agent.llm.providers.openai_compatible import SseDecoder
from memoria.services.agent.llm.retry import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TOTAL_TIMEOUT_S,
)

SECRET = "sk-memoria-test-SECRET-0123456789abcdef"
MODEL = "test-model"


# —— 本地 stub 端点 ——


class _StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler 约定
        server = self.server
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        server.requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})
        spec = server.responses[min(len(server.requests) - 1, len(server.responses) - 1)]
        self.send_response(spec["status"])
        for key, value in (spec.get("headers") or {}).items():
            self.send_header(key, value)
        chunks = spec.get("chunks")
        if chunks is None:
            payload: bytes = spec.get("body", b"")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        for chunk in chunks:
            self.wfile.write(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            self.wfile.flush()


@contextmanager
def stub_server(responses: list[dict[str, Any]]) -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.responses = responses  # type: ignore[attr-defined]
    server.requests = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def base_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}/v1"


def sse(*payloads: str) -> bytes:
    return "".join(f"data: {payload}\n\n" for payload in payloads).encode("utf-8")


def delta_chunk(content: str | None = None, *, reasoning: str | None = None) -> str:
    delta: dict[str, Any] = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    return json.dumps({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}, ensure_ascii=False)


def finish_chunk(reason: str) -> str:
    return json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": reason}]})


def usage_chunk(prompt: int, completion: int) -> str:
    return json.dumps(
        {
            "choices": [],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion},
        }
    )


def tool_delta_chunk(index: int, call_id: str = "", name: str = "", arguments: str = "") -> str:
    function: dict[str, Any] = {}
    if name:
        function["name"] = name
    if arguments:
        function["arguments"] = arguments
    call: dict[str, Any] = {"index": index, "function": function}
    if call_id:
        call["id"] = call_id
    return json.dumps({"choices": [{"index": 0, "delta": {"tool_calls": [call]}, "finish_reason": None}]})


def make_request(**overrides: Any) -> LlmRequest:
    options: dict[str, Any] = {
        "model": MODEL,
        "messages": (Message(role=Role.USER, content="你好"),),
        "timeout_s": 5.0,
    }
    options.update(overrides)
    return LlmRequest(**options)


def collect(provider: OpenAICompatibleProvider, request: LlmRequest) -> list[Any]:
    return list(provider.stream(request))


def text_of(events: list[Any]) -> str:
    return "".join(event.text for event in events if isinstance(event, TextDelta))


def finish_of(events: list[Any]) -> FinishEvent:
    finals = [event for event in events if isinstance(event, FinishEvent)]
    assert len(finals) == 1, f"流必须以唯一终止事件结束，实际 {finals!r}"
    return finals[0]


# —— ① SSE 解析 ——


def test_sse_decoder_handles_split_lines_comments_and_done() -> None:
    decoder = SseDecoder()
    raw = (
        b": keep-alive comment\n"
        b"\n"
        b'data: {"a": 1}\r\n'
        b"\r\n"  # CRLF 行尾
        b'data: {"t": "\xe4\xb8\xad\xe6\x96\x87"}\n'
        b"\n"
        b"data: [DONE]\n"
        b"\n"
    )
    payloads: list[str] = []
    for index in range(len(raw)):  # 逐字节喂入：断行与多字节字符都被切开
        payloads.extend(decoder.feed(raw[index : index + 1]))
    payloads.extend(decoder.close())

    assert payloads == ['{"a": 1}', '{"t": "中文"}', "[DONE]"]


def test_sse_decoder_joins_multiline_data() -> None:
    decoder = SseDecoder()
    payloads = decoder.feed(b"data: line1\ndata: line2\n\n")
    assert payloads == ["line1\nline2"]


def test_stream_parses_sse_text_usage_and_finish_reason() -> None:
    raw = sse(
        delta_chunk("你"),
        delta_chunk("好"),
        finish_chunk("length"),
        usage_chunk(11, 7),
        "[DONE]",
    )
    chunks = [raw[:17], raw[17:61], raw[61:]]  # 在任意字节处切开，覆盖跨 chunk 断行
    with stub_server([{"status": 200, "chunks": chunks}]) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        events = collect(provider, make_request())

        assert text_of(events) == "你好"
        usage = next(event.usage for event in events if isinstance(event, UsageEvent))
        assert (usage.prompt_tokens, usage.completion_tokens, usage.total) == (11, 7, 18)
        assert usage.estimated is False
        final = finish_of(events)
        assert final.reason is FinishReason.MAX_TOKENS
        assert final.usage is usage

    sent = json.loads(server.requests[0]["body"])  # type: ignore[attr-defined]
    assert server.requests[0]["path"] == "/v1/chat/completions"  # type: ignore[attr-defined]
    assert sent["model"] == MODEL
    assert sent["stream"] is True
    assert sent["messages"] == [{"role": "user", "content": "你好"}]


# —— ② tool_calls 增量按 index 聚合 ——


def test_tool_call_deltas_are_aggregated_by_index() -> None:
    chunks = [
        sse(
            tool_delta_chunk(0, "call_a", "search", "{"),
            tool_delta_chunk(1, "call_b", "read_doc", '{"path":'),
            tool_delta_chunk(0, arguments='"query": "贝叶斯"}'),
            tool_delta_chunk(1, arguments=' "a.md"}'),
            finish_chunk("tool_calls"),
            "[DONE]",
        )
    ]
    with stub_server([{"status": 200, "chunks": chunks}]) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        events = collect(provider, make_request())

    deltas = [event for event in events if isinstance(event, ToolCallDelta)]
    assert [delta.index for delta in deltas] == [0, 1, 0, 1]
    assert deltas[0].name == "search" and deltas[0].id == "call_a"
    final = finish_of(events)
    assert final.reason is FinishReason.TOOL_CALLS
    assert [(call.id, call.name, call.arguments) for call in final.tool_calls] == [
        ("call_a", "search", '{"query": "贝叶斯"}'),
        ("call_b", "read_doc", '{"path": "a.md"}'),
    ]


# —— ③ 429 后重试成功 ——


def test_rate_limited_is_retried_then_succeeds() -> None:
    responses = [
        {
            "status": 429,
            "headers": {"Retry-After": "0.05", "Content-Type": "application/json"},
            "body": json.dumps({"error": {"message": "rate limit exceeded"}}).encode(),
        },
        {"status": 200, "chunks": [sse(delta_chunk("恢复"), finish_chunk("stop"), "[DONE]")]},
    ]
    with stub_server(responses) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        delays: list[float] = []
        events = list(
            iter_with_retry(
                lambda: provider.stream(make_request()),
                policy=RetryPolicy(initial_delay_s=0.01, max_delay_s=1.0, jitter_ratio=0.0),
                on_retry=lambda _attempt, delay, _exc: delays.append(delay),
            )
        )
        assert len(server.requests) == 2  # type: ignore[attr-defined]

    assert text_of(events) == "恢复"
    assert finish_of(events).reason is FinishReason.STOP
    assert delays == [0.05]  # 端点 Retry-After 覆盖本地退避


def test_rate_limited_without_retry_raises() -> None:
    responses = [
        {
            "status": 429,
            "headers": {"Retry-After": "0.05"},
            "body": json.dumps({"error": {"message": "rate limit exceeded"}}).encode(),
        }
    ]
    with stub_server(responses) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        with pytest.raises(RateLimited) as excinfo:
            collect(provider, make_request())

    assert excinfo.value.code == "RATE_LIMIT"
    assert excinfo.value.status == 429
    assert excinfo.value.retry_after_s == 0.05
    assert SECRET not in str(excinfo.value)


def test_max_retries_exhausted_reraises_server_error() -> None:
    server_error = {
        "status": 500,
        "body": json.dumps({"error": {"message": "internal server error"}}).encode(),
    }
    with stub_server([server_error]) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        with pytest.raises(ProviderError) as excinfo:
            list(
                iter_with_retry(
                    lambda: provider.stream(make_request()),
                    policy=RetryPolicy(max_retries=2, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0),
                )
            )
        assert len(server.requests) == 3  # 首次 + 2 次重试

    assert excinfo.value.code == "SERVER"


# —— ④ 400 不重试 ——


def test_invalid_request_is_not_retried() -> None:
    responses = [
        {
            "status": 400,
            "body": json.dumps({"error": {"message": "invalid request: unknown field 'foo'"}}).encode(),
        }
    ]
    with stub_server(responses) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        with pytest.raises(ProviderError) as excinfo:
            list(
                iter_with_retry(
                    lambda: provider.stream(make_request()),
                    policy=RetryPolicy(initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0),
                )
            )
        assert len(server.requests) == 1  # type: ignore[attr-defined]

    assert excinfo.value.code == INVALID_REQUEST_CODE
    assert excinfo.value.status == 400


def test_truncated_stream_reports_transport_failure() -> None:
    """没有终止标记就断流：以带 TRANSPORT 失败的终止事件投递（对齐上游语义）。"""
    responses = [
        {"status": 200, "chunks": [sse(delta_chunk("半"), delta_chunk("句"))]},  # 在 finish/[DONE] 前断流
        {"status": 500, "body": b"{}"},
    ]
    with stub_server(responses) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        policy = RetryPolicy(max_retries=3, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0)
        events = list(iter_with_retry(lambda: provider.stream(make_request()), policy=policy))
        assert len(server.requests) == 1  # 带内失败不触发重试  # type: ignore[attr-defined]

    assert text_of(events) == "半句"
    final = finish_of(events)
    assert final.reason is FinishReason.ERROR
    assert final.failure is not None and final.failure.code == TRANSPORT_CODE


def test_failure_after_first_delta_is_not_retried() -> None:
    """已投递分片后抛出的失败不重放（避免重复输出）。"""
    responses = [
        {"status": 200, "chunks": [sse(delta_chunk("半")), b"data: {not json\n\n"]},
        {"status": 500, "body": b"{}"},
    ]
    with stub_server(responses) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        policy = RetryPolicy(max_retries=3, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0)
        stream = iter_with_retry(lambda: provider.stream(make_request()), policy=policy)
        first = next(stream)
        assert isinstance(first, TextDelta) and first.text == "半"
        with pytest.raises(ProviderError):
            next(stream)
        assert len(server.requests) == 1  # type: ignore[attr-defined]


# —— ⑤ usage 正常与缺失 ——


def test_usage_estimated_when_endpoint_omits_usage() -> None:
    chunks = [sse(delta_chunk("估计"), delta_chunk("用量"), finish_chunk("stop"), "[DONE]")]
    with stub_server([{"status": 200, "chunks": chunks}]) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        events = collect(provider, make_request())

    usage = next(event.usage for event in events if isinstance(event, UsageEvent))
    assert usage.estimated is True
    assert usage.prompt_tokens > 0 and usage.completion_tokens > 0
    assert usage.total == usage.prompt_tokens + usage.completion_tokens
    assert finish_of(events).usage is usage


def test_empty_completion_is_reported_as_retryable_failure() -> None:
    chunks = [sse(finish_chunk("stop"), "[DONE]")]
    with stub_server([{"status": 200, "chunks": chunks}]) as server:
        provider = OpenAICompatibleProvider(AgentConfig(base_url=base_url(server), model=MODEL))
        events = collect(provider, make_request())

    final = finish_of(events)
    assert final.reason is FinishReason.ERROR
    assert final.failure is not None and final.failure.code == EMPTY_RESPONSE_CODE


def test_estimate_usage_and_meter_accumulate() -> None:
    request = make_request()
    estimated = estimate_usage(request, "回答文本")
    assert estimated.estimated is True and estimated.total > 0

    meter = UsageMeter()
    meter.add(Usage(prompt_tokens=10, completion_tokens=5, cache_read_tokens=3))
    meter.add(estimated)
    assert meter.to_dict()["total_tokens"] == 15 + estimated.total
    assert meter.calls == 2 and meter.estimated_calls == 1 and meter.any_estimated is True
    meter.reset()
    assert meter.to_dict()["calls"] == 0 and meter.to_dict()["total_tokens"] == 0


# —— ⑥ 密钥掩码 ——


def test_secret_is_masked_in_repr_and_errors() -> None:
    config = AgentConfig(base_url="http://127.0.0.1:1/v1", api_key=SECRET, model=MODEL)
    assert SECRET not in repr(config)
    assert SECRET not in str(config)
    assert mask_secret(SECRET) == "sk-***（len=39）"
    assert mask_secret("short") == "***"
    assert mask_secret("") == ""

    with pytest.raises(AuthError) as excinfo:
        normalize_api_key("sk-含非法字符")
    assert excinfo.value.code == "INVALID_CREDENTIAL"
    assert "含非法字符" not in str(excinfo.value)

    with pytest.raises(AuthError) as missing:
        normalize_api_key("   ")
    assert missing.value.code == "MISSING_CREDENTIAL"

    provider = OpenAICompatibleProvider(AgentConfig(base_url="http://127.0.0.1:1/v1", api_key="sk-含非法字符"))
    with pytest.raises(AuthError) as from_provider:
        provider.build_headers()
    assert "含非法字符" not in repr(from_provider.value)


def test_headers_carry_bearer_token_only_when_configured() -> None:
    provider = OpenAICompatibleProvider(AgentConfig(base_url="http://127.0.0.1:1/v1", api_key=SECRET))
    assert provider.build_headers()["Authorization"] == f"Bearer {SECRET}"
    anon = OpenAICompatibleProvider(AgentConfig(base_url="http://127.0.0.1:1/v1"))
    assert "Authorization" not in anon.build_headers()


# —— 退避 / 配置 / 注入 seam ——


def test_local_delay_matches_upstream_backoff() -> None:
    policy = RetryPolicy(initial_delay_s=1.0, max_delay_s=4.0, jitter_ratio=0.5)
    assert local_delay(1, policy, rand=lambda: 0.5) == 1.0
    assert local_delay(2, policy, rand=lambda: 0.5) == 2.0
    assert local_delay(9, policy, rand=lambda: 0.5) == 4.0  # 指数上限
    assert local_delay(1, policy, rand=lambda: 1.0) == 1.5  # +50% 抖动
    assert local_delay(1, policy, rand=lambda: 0.0) == 0.5  # -50% 抖动
    assert local_delay(3, RetryPolicy(initial_delay_s=1.0, max_delay_s=2.0, jitter_ratio=1.0), rand=lambda: 1.0) == 2.0


def test_delay_for_prefers_retry_after_within_bounds() -> None:
    policy = RetryPolicy(initial_delay_s=0.5, max_delay_s=10.0, jitter_ratio=0.0)
    assert delay_for(RateLimited("限流", retry_after_s=3.0), 1, policy) == 3.0
    assert delay_for(RateLimited("限流", retry_after_s=30.0), 1, policy) is None  # 超出上限即放弃
    assert delay_for(RateLimited("限流"), 1, policy) == 0.5
    assert delay_for(ProviderError("服务端错误", code="SERVER"), 3, policy) == 2.0


def test_config_from_env_and_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from memoria.services.agent.llm import config as config_module

    config_file = tmp_path / "agent.json"
    config_file.write_text(
        json.dumps({"base_url": "http://file.example/v1", "model": "file-model", "timeout_s": 12}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMORIA_AGENT_CONFIG", str(config_file))
    monkeypatch.setenv("MEMORIA_AGENT_API_KEY", SECRET)

    loaded = config_module.load_config()
    assert loaded.base_url == "http://file.example/v1"
    assert loaded.model == "file-model"
    assert loaded.timeout_s == 12.0
    assert loaded.api_key == SECRET and SECRET not in repr(loaded)
    assert loaded.source == "mixed"

    monkeypatch.setenv("MEMORIA_AGENT_BASE_URL", "http://env.example/v1")
    assert config_module.load_config().base_url == "http://env.example/v1"

    monkeypatch.setenv("MEMORIA_AGENT_TIMEOUT_S", "abc")
    with pytest.raises(ConfigError):
        config_module.load_config()


def test_status_refresh_ms_default_and_roundtrip(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """状态 bar 刷新间隔（`status_refresh_ms`）：默认 1min、白名单往返、非法值不落盘、读侧宽松。"""
    from memoria.services.agent.llm import config as config_module

    config_file = tmp_path / "agent.json"
    monkeypatch.setenv("MEMORIA_AGENT_CONFIG", str(config_file))

    # 未配置 ⇒ 默认 60 000 ms（=1min，既有余额 60s TTL 的节拍）
    assert config_module.DEFAULT_STATUS_REFRESH_MS == 60000
    assert config_module.status_refresh_ms() == 60000
    # 它不是调用参数：`AgentConfig` / `load_config()` 都不带这个字段（与 `enabled` 同类）
    assert not hasattr(config_module.load_config(), "status_refresh_ms")

    # 写盘（白名单键）→ 原样读回（毫秒整数）
    saved = config_module.save_config({"status_refresh_ms": 300000})
    assert saved["status_refresh_ms"] == 300000
    assert config_module.status_refresh_ms() == 300000

    # 空值 = 不修改；非法值（0 / 非数）不落盘
    assert config_module.save_config({"status_refresh_ms": ""})["status_refresh_ms"] == 300000
    with pytest.raises(ConfigError):
        config_module.save_config({"status_refresh_ms": 0})
    with pytest.raises(ConfigError):
        config_module.save_config({"status_refresh_ms": "abc"})
    assert config_module.status_refresh_ms() == 300000

    # 未在白名单里的键仍被拒绝（新增键不得放宽白名单）
    with pytest.raises(ConfigError):
        config_module.save_config({"status_refresh_msec": 1})

    # 手改坏值（绕过 UI 校验）⇒ 读侧宽松回退默认，不抛错
    config_file.write_text(json.dumps({"status_refresh_ms": "oops"}), encoding="utf-8")
    assert config_module.status_refresh_ms() == 60000


def test_missing_base_url_raises_config_error() -> None:
    provider = OpenAICompatibleProvider(AgentConfig())
    with pytest.raises(ConfigError):
        collect(provider, make_request())


def test_injected_opener_is_used_without_network() -> None:
    payload = sse(delta_chunk("注入"), finish_chunk("stop"), "[DONE]")
    calls: list[tuple[str, float | None]] = []

    def opener(request: Any, timeout: float | None = None) -> io.BytesIO:
        calls.append((request.full_url, timeout))
        return io.BytesIO(payload)

    provider = OpenAICompatibleProvider(
        AgentConfig(base_url="http://injected.example/v1", model=MODEL, timeout_s=7.0),
        opener=opener,
    )
    events = collect(provider, make_request(timeout_s=None))

    assert calls == [("http://injected.example/v1/chat/completions", 7.0)]
    assert text_of(events) == "注入"
    assert finish_of(events).reason is FinishReason.STOP


def test_agent_llm_error_failure_facts() -> None:
    error = AgentLlmError("boom", code="SERVER", status=503, retry_after_s=1.5)
    assert error.to_failure() == {
        "message": "boom",
        "code": "SERVER",
        "status": 503,
        "providerRetryAfterMs": 1500,
    }
    assert "code='SERVER'" in repr(error)


# —— ⑦ 确定性连接失败 vs 瞬时故障（不重试 / 仍重试）——


def deterministic_errors() -> list[BaseException]:
    """构造的确定性连接失败（不需要真网络）。"""
    refused = ConnectionRefusedError(10061, "由于目标计算机积极拒绝，无法连接。")
    return [
        refused,
        urllib.error.URLError(refused),  # urlopen 会把底层原因包进 URLError（本身是 OSError）
        socket.gaierror(-2, "Name or service not known"),
        ssl.SSLCertVerificationError(1, "certificate verify failed"),
        http.client.InvalidURL("nonnumeric port: 'abc'"),
        urllib.error.URLError("unknown url type: 'htp'"),
        ProviderError("无法连接模型端点", code=UNREACHABLE_CODE),
    ]


def transient_errors() -> list[BaseException]:
    """构造的瞬时故障（超时 / 重置 / 5xx / 429 / 传输截断）。"""
    return [
        TimeoutError("timed out"),
        ConnectionResetError(10054, "远程主机强迫关闭了一个现有的连接。"),
        BrokenPipeError(32, "Broken pipe"),
        ProviderError("服务端错误", code="SERVER", status=500),
        ProviderError("传输中断", code=TRANSPORT_CODE),
        AgentLlmError("传输中断", code=TRANSPORT_CODE, status=None),
        RateLimited("限流"),
        LlmTimeoutError("读取超时"),
    ]


def test_deterministic_connection_failures_are_not_retryable() -> None:
    assert UNREACHABLE_CODE not in RETRYABLE_CODES  # 新增 code 刻意不进可重试集合
    policy = RetryPolicy()
    for error in deterministic_errors():
        assert is_unreachable(error) is True, repr(error)
        assert is_retryable(error) is False, repr(error)
        assert policy.allows(error) is False, repr(error)


def test_transient_failures_stay_retryable() -> None:
    policy = RetryPolicy()
    for error in transient_errors():
        assert is_unreachable(error) is False, repr(error)
        assert is_retryable(error) is True, repr(error)
        assert policy.allows(error) is True, repr(error)


def test_connection_refused_endpoint_fails_immediately_with_unreachable() -> None:
    """注入 opener 抛"连接被拒"：一次尝试即失败，code=UNREACHABLE，消息含 URL 与原因。"""
    calls: list[str] = []

    def opener(request: Any, timeout: float | None = None) -> Any:
        calls.append(request.full_url)
        raise urllib.error.URLError(ConnectionRefusedError(10061, "由于目标计算机积极拒绝，无法连接。"))

    provider = OpenAICompatibleProvider(
        AgentConfig(base_url="http://127.0.0.1:9/v1", model=MODEL, timeout_s=5.0),
        opener=opener,
    )
    policy = RetryPolicy(max_retries=5, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0)
    with pytest.raises(AgentLlmError) as excinfo:
        list(iter_with_retry(lambda: provider.stream(make_request()), policy=policy))

    assert len(calls) == 1  # 不做任何重试
    assert excinfo.value.code == UNREACHABLE_CODE
    assert "http://127.0.0.1:9/v1/chat/completions" in str(excinfo.value)  # 人话：含目标 URL
    assert "确定性" in str(excinfo.value)
    assert SECRET not in str(excinfo.value)


def test_invalid_url_is_classified_unreachable_without_retry() -> None:
    def opener(request: Any, timeout: float | None = None) -> Any:
        raise http.client.InvalidURL("nonnumeric port: 'abc'")

    provider = OpenAICompatibleProvider(
        AgentConfig(base_url="http://bad.example:abc/v1", model=MODEL),
        opener=opener,
    )
    with pytest.raises(AgentLlmError) as excinfo:
        list(iter_with_retry(lambda: provider.stream(make_request()), policy=RetryPolicy(max_retries=3)))
    assert excinfo.value.code == UNREACHABLE_CODE
    assert "URL" in str(excinfo.value)


def test_transport_failure_still_retried_then_succeeds() -> None:
    """瞬时故障（连接重置）仍走重试：第二次尝试成功。"""
    attempts: list[int] = []

    def opener(request: Any, timeout: float | None = None) -> Any:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionResetError(10054, "远程主机强迫关闭了一个现有的连接。")
        return io.BytesIO(sse(delta_chunk("恢复"), finish_chunk("stop"), "[DONE]"))

    provider = OpenAICompatibleProvider(AgentConfig(base_url="http://reset.example/v1", model=MODEL), opener=opener)
    retries: list[int] = []
    events = list(
        iter_with_retry(
            lambda: provider.stream(make_request()),
            policy=RetryPolicy(max_retries=2, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0),
            on_retry=lambda attempt, _delay, _exc: retries.append(attempt),
        )
    )
    assert len(attempts) == 2
    assert retries == [1]
    assert text_of(events) == "恢复"


# —— ⑧ 有界等待：total_timeout_s 用假时钟判定 ——


def test_run_with_retry_gives_up_when_backoff_would_exceed_total_timeout() -> None:
    clock = [0.0]
    calls: list[int] = []
    retries: list[int] = []

    def call() -> None:
        calls.append(1)
        raise RateLimited("限流")

    policy = RetryPolicy(
        max_retries=5,
        initial_delay_s=1.0,
        max_delay_s=10.0,
        jitter_ratio=0.0,
        total_timeout_s=2.5,
    )
    with pytest.raises(RateLimited):
        run_with_retry(
            call,
            policy=policy,
            sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
            monotonic=lambda: clock[0],
            rand=lambda: 0.5,
            on_retry=lambda attempt, _delay, _exc: retries.append(attempt),
        )

    # 第 1 次重试退避 1.0s（可行）→ 第 2 次退避 2.0s 会越过 deadline 2.5s ⇒ 放弃
    assert calls == [1, 1]
    assert retries == [1]
    assert clock[0] == 1.0  # 只 sleep 了 1.0s，绝不越过总时限


def test_iter_with_retry_reports_each_retry_attempt() -> None:
    state = {"n": 0}

    def factory() -> Iterator[Any]:
        state["n"] += 1
        if state["n"] < 3:
            raise ProviderError("服务端错误", code="SERVER", status=500)
        return iter([TextDelta("ok"), FinishEvent(reason=FinishReason.STOP)])

    seen: list[tuple[int, float]] = []
    events = list(
        iter_with_retry(
            factory,
            policy=RetryPolicy(max_retries=5, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0),
            on_retry=lambda attempt, delay, _exc: seen.append((attempt, delay)),
        )
    )
    assert [attempt for attempt, _delay in seen] == [1, 2]
    assert text_of(events) == "ok"


# —— ⑨ 面板路径策略（交互路径，等待有界；库层默认不变）——


def test_panel_retry_policy_is_tighter_than_library_default() -> None:
    from memoria.services.agent.ask_stream import (
        PANEL_MAX_RETRIES,
        PANEL_RETRY_POLICY,
        PANEL_TOTAL_TIMEOUT_S,
    )

    assert (PANEL_MAX_RETRIES, PANEL_TOTAL_TIMEOUT_S) == (2, 20.0)
    assert PANEL_RETRY_POLICY.max_retries == 2
    assert PANEL_RETRY_POLICY.total_timeout_s == 20.0
    assert PANEL_RETRY_POLICY.retryable_codes == RETRYABLE_CODES
    assert PANEL_RETRY_POLICY.initial_delay_s == 0.5  # 其余沿用库层默认
    assert PANEL_RETRY_POLICY.max_delay_s == 10.0
    # 库层上游默认值不变
    assert DEFAULT_MAX_RETRIES == 5
    assert DEFAULT_TOTAL_TIMEOUT_S == 120.0
    assert RetryPolicy().max_retries == 5
    assert RetryPolicy().total_timeout_s == 120.0


def test_ask_job_manager_uses_panel_retry_policy(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """面板作业实际把 PANEL_RETRY_POLICY 传给了 ask()（不改 RPC 签名）。"""
    import time
    from types import SimpleNamespace

    from memoria.services.agent import ask_stream

    captured: dict[str, Any] = {}

    def fake_ask(kb_path: str, question: str, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            answer="好",
            anchors=(),
            tool_calls=(),
            usage={},
            session_id="session-x",
            stop_reason="final-answer",
            iterations=1,
            error=None,
        )

    monkeypatch.setattr(ask_stream, "ask", fake_ask)
    kb = tmp_path / "kb"
    kb.mkdir()
    manager = ask_stream.AskJobManager()
    env = {"MEMORIA_AGENT_BASE_URL": "http://panel.example/v1", "MEMORIA_AGENT_MODEL": MODEL}
    started = manager.start(str(kb), "问题", env=env)
    assert started["status"] == "ok"

    job_id = started["job_id"]
    for _ in range(200):  # 等工作线程跑完（池是单线程，几乎立即）
        snapshot = manager.poll(job_id, 0)
        if snapshot["status"] != ask_stream.RUNNING:
            break
        time.sleep(0.01)
    assert snapshot["status"] == ask_stream.DONE
    assert captured["retry_policy"] is ask_stream.PANEL_RETRY_POLICY
    assert captured["session_id"] is None
