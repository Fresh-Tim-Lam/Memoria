# 语义移植自 deepseek-harness packages/llm/llm-pi-ai（OpenAI 兼容部分，MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""OpenAI 兼容 `/chat/completions` 适配器（纯标准库 `urllib` + 手写 SSE）。

对应上游 `dsh-llm-pi-ai` 的 `openai-completions` 路由（其 `src/stream.ts`
把带内事件翻译成统一流式协议）。本实现：

- `POST {base_url}/chat/completions`，`stream: true`；
- 手写 SSE 解析：`data: {...}` 载荷、`[DONE]` 终止标记、跨 chunk 断行、
  空行与 `:` 注释行忽略、多行 `data` 按 SSE 规范以换行拼接；
- `delta.content` → `TextDelta`，`delta.reasoning_content` / `delta.reasoning`
  → `ReasoningDelta`，`delta.tool_calls[]` 按 `index` 聚合（参数保持原始 JSON
  字符串，逐片拼接）；
- `finish_reason` 映射为统一结束原因；`usage` 缺失时按字符估算并标记
  `estimated=True`（不强求端点的 `stream_options.include_usage`，因为不少网关
  会拒绝未知字段）；
- 失败语义：HTTP 状态/连接失败在**尚未产出事件**时抛 `AgentLlmError` 子类；
  已开始产出后的断流、带内 `error` 对象、无终止标记的截断，以携带 `failure`
  的终止 `FinishEvent` 投递（对齐上游「流始终以终止 finish 结束」）。

密钥只用于 `Authorization` 头，且绝不写入日志、异常消息或 `repr`。
"""

from __future__ import annotations

import codecs
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import closing
from typing import Any

from memoria.services.agent.llm.config import AgentConfig
from memoria.services.agent.llm.errors import (
    EMPTY_RESPONSE_CODE,
    INVALID_REQUEST_CODE,
    PROTOCOL_CODE,
    TIMEOUT_CODE,
    TRANSPORT_CODE,
    AgentLlmError,
    ConfigError,
    ProviderError,
    classify_detail,
    error_for,
)
from memoria.services.agent.llm.types import (
    FinishEvent,
    FinishReason,
    LlmRequest,
    Message,
    ReasoningDelta,
    Role,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    Usage,
    UsageEvent,
)
from memoria.services.agent.llm.usage import estimate_usage

logger = logging.getLogger(__name__)

__all__ = ["OpenAICompatibleProvider", "PROVIDER_NAMES", "SseDecoder", "chat_completions_url"]

#: 注册到 provider 注册表的路由名（含别名）。
PROVIDER_NAMES = ("openai-compatible", "openai_compatible")

#: 单次 `read()` 的最大字节数。
_READ_SIZE = 65536
#: 默认请求头中声明的客户端标识。
_USER_AGENT = "memoria-agent-llm/1"

#: 线上 `finish_reason` → 统一结束原因。
_FINISH_REASONS = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "function_call": FinishReason.TOOL_CALLS,
    "length": FinishReason.MAX_TOKENS,
    "content_filter": FinishReason.CONTENT_FILTER,
}

#: 部分端点把推理文本放在这些 delta 字段里。
_REASONING_FIELDS = ("reasoning_content", "reasoning")


def chat_completions_url(base_url: str) -> str:
    """由端点基址拼出 `chat/completions` URL。"""
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ConfigError("模型端点为空；请设置 MEMORIA_AGENT_BASE_URL")
    return f"{value}/chat/completions"


class SseDecoder:
    """增量 SSE 解码器：喂入任意切分的字节，产出完整 `data` 载荷。

    只使用 `data:` 字段（`event:` / `id:` / `retry:` 当前不使用），忽略 `:`
    注释行与空行，多行 `data` 按 SSE 规范以 `\\n` 拼接后整块产出。
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._data: list[str] = []
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def feed(self, chunk: bytes) -> list[str]:
        """喂入一段字节，返回本次新完成的载荷列表。"""
        if chunk:
            self._buffer += self._decoder.decode(chunk)
        payloads: list[str] = []
        while True:
            index = self._buffer.find("\n")
            if index < 0:
                break
            line = self._buffer[:index].rstrip("\r")
            self._buffer = self._buffer[index + 1 :]
            payload = self._consume_line(line)
            if payload is not None:
                payloads.append(payload)
        return payloads

    def close(self) -> list[str]:
        """收尾：处理末尾无换行的残留行与尚未派发的 data 块。"""
        self._buffer += self._decoder.decode(b"", final=True)
        payloads: list[str] = []
        if self._buffer.strip():
            payload = self._consume_line(self._buffer.rstrip("\r"))
            if payload is not None:
                payloads.append(payload)
        self._buffer = ""
        if self._data:
            payloads.append("\n".join(self._data))
            self._data.clear()
        return payloads

    def _consume_line(self, line: str) -> str | None:
        if line == "":
            # 空行 = 事件边界：有 data 才派发。
            if not self._data:
                return None
            payload = "\n".join(self._data)
            self._data.clear()
            return payload
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            self._data.append(value)
        return None


class _ToolCallAccumulator:
    """按 `index` 聚合 `tool_calls` 增量（id/name 取首个非空值，参数逐片拼接）。"""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, str]] = {}

    def add(self, index: int, call_id: str, name: str, arguments_delta: str) -> None:
        entry = self._calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if call_id:
            entry["id"] = call_id
        if name:
            entry["name"] = name
        if arguments_delta:
            entry["arguments"] += arguments_delta

    def assembled(self) -> tuple[ToolCall, ...]:
        return tuple(
            ToolCall(id=entry["id"], name=entry["name"], arguments=entry["arguments"])
            for _index, entry in sorted(self._calls.items())
        )

    def __bool__(self) -> bool:
        return bool(self._calls)


class OpenAICompatibleProvider:
    """OpenAI 兼容端点适配器；一次 `stream()` 即一次 provider 尝试。"""

    name = "openai-compatible"

    def __init__(
        self,
        config: AgentConfig,
        *,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._config = config
        #: 便于测试注入（默认 `urllib.request.urlopen`）。
        self._opener = opener or urllib.request.urlopen

    # —— 请求构造 ——

    def build_body(self, request: LlmRequest) -> dict[str, Any]:
        """把中立请求映射为 OpenAI 兼容请求体（仅序列化已设置的字段）。"""
        messages: list[dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(_message_to_wire(message) for message in request.messages)
        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": bool(request.stream),
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": dict(tool.parameters),
                    },
                }
                for tool in request.tools
            ]
        if request.tool_choice is not None:
            body["tool_choice"] = request.tool_choice
        return body

    def build_headers(self) -> dict[str, str]:
        """请求头；凭据只出现在 `Authorization`（非法取值抛 `AuthError`）。"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": _USER_AGENT,
        }
        if self._config.has_api_key:
            headers["Authorization"] = f"Bearer {self._config.require_api_key()}"
        else:
            logger.debug("[agent-llm] 未配置密钥，按无认证请求发送：%s", chat_completions_url(self._config.base_url))
        return headers

    # —— 调用 ——

    def stream(self, request: LlmRequest) -> Iterator[StreamEvent]:
        """发起一次调用并按到达顺序产出事件。"""
        url = chat_completions_url(self._config.base_url)
        timeout = request.timeout_s or self._config.timeout_s
        payload = json.dumps(self.build_body(request), ensure_ascii=False).encode("utf-8")
        http_request = urllib.request.Request(
            url,
            data=payload,
            headers=self.build_headers(),
            method="POST",
        )
        logger.debug("[agent-llm] POST %s model=%s", url, request.model)
        try:
            response = self._opener(http_request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from exc
        except TimeoutError as exc:
            raise error_for(TIMEOUT_CODE, f"请求 {url} 超时（{timeout}s）") from exc
        except OSError as exc:
            raise error_for(TRANSPORT_CODE, f"连接 {url} 失败：{exc}") from exc
        with closing(response):
            yield from self._iter_events(response, request)

    def _iter_events(self, response: Any, request: LlmRequest) -> Iterator[StreamEvent]:
        """解析 SSE 响应体，聚合增量并产出终止事件。"""
        decoder = SseDecoder()
        tool_calls = _ToolCallAccumulator()
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage: Usage | None = None
        reason: FinishReason | None = None
        failure: AgentLlmError | None = None
        saw_done = False

        def payloads() -> Iterator[str]:
            while True:
                try:
                    chunk = response.read(_READ_SIZE)
                except TimeoutError as exc:
                    raise error_for(TIMEOUT_CODE, f"读取 {request.model} 响应超时") from exc
                except OSError as exc:
                    raise error_for(TRANSPORT_CODE, f"读取响应中断：{exc}") from exc
                if not chunk:
                    break
                yield from decoder.feed(chunk)
            yield from decoder.close()

        for payload in payloads():
            if payload.strip() == "[DONE]":
                saw_done = True
                break
            data = _parse_payload(payload)
            if "error" in data:
                failure = _error_from_body(data["error"])
                break
            chunk_usage = _usage_from_wire(data.get("usage"))
            if chunk_usage is not None:
                usage = chunk_usage
            choices = data.get("choices")
            if choices is None:
                raise ProviderError(
                    f"端点返回了无法识别的流载荷（无 choices）：{payload[:200]}",
                    code=PROTOCOL_CODE,
                )
            if not isinstance(choices, list):
                raise ProviderError(
                    f"端点返回的 choices 不是数组：{payload[:200]}",
                    code=PROTOCOL_CODE,
                )
            if not choices:
                # 例如收尾的 usage-only 分片（`{"choices": [], "usage": {...}}`）。
                continue
            choice = choices[0] if isinstance(choices[0], dict) else {}
            delta = choice.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str) and content:
                    text_parts.append(content)
                    yield TextDelta(text=content)
                for field_name in _REASONING_FIELDS:
                    reasoning = delta.get(field_name)
                    if isinstance(reasoning, str) and reasoning:
                        reasoning_parts.append(reasoning)
                        yield ReasoningDelta(text=reasoning)
                for raw_call in delta.get("tool_calls") or ():
                    if not isinstance(raw_call, dict):
                        continue
                    function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
                    index = raw_call.get("index")
                    event = ToolCallDelta(
                        index=int(index) if isinstance(index, int) else 0,
                        id=str(raw_call.get("id") or ""),
                        name=str(function.get("name") or ""),
                        arguments_delta=str(function.get("arguments") or ""),
                    )
                    tool_calls.add(event.index, event.id, event.name, event.arguments_delta)
                    yield event
            wire_reason = choice.get("finish_reason")
            if isinstance(wire_reason, str) and wire_reason:
                reason = _map_finish_reason(wire_reason, request.model)

        completion_text = "".join(text_parts)
        reasoning_text = "".join(reasoning_parts)
        assembled = tool_calls.assembled()
        if reason is None and failure is None:
            if not saw_done:
                # 没有终止标记就断流：传输截断（上游归为 TRANSPORT）。
                failure = error_for(TRANSPORT_CODE, f"响应在终止标记前结束（model={request.model}）")
            elif assembled:
                reason = FinishReason.TOOL_CALLS
            else:
                reason = FinishReason.STOP
        if reason is FinishReason.STOP and not completion_text and not reasoning_text and not assembled:
            # 上游：正常结束却零内容的退化响应不视作成功的空消息，可安全重试。
            failure = ProviderError(
                f"模型 {request.model!r} 正常结束但没有产出任何内容",
                code=EMPTY_RESPONSE_CODE,
            )
        if usage is None:
            usage = estimate_usage(request, completion_text, reasoning_text=reasoning_text)
        yield UsageEvent(usage=usage)
        if failure is not None:
            yield FinishEvent(reason=FinishReason.ERROR, usage=usage, tool_calls=assembled, failure=failure)
            return
        yield FinishEvent(reason=reason or FinishReason.STOP, usage=usage, tool_calls=assembled)


def _message_to_wire(message: Message) -> dict[str, Any]:
    """中立消息 → OpenAI 兼容 `messages[]` 条目。"""
    role = message.role.value if isinstance(message.role, Role) else str(message.role)
    entry: dict[str, Any] = {"role": role, "content": message.content}
    if message.name:
        entry["name"] = message.name
    if message.tool_call_id:
        entry["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        entry["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    return entry


def _parse_payload(payload: str) -> dict[str, Any]:
    if not payload.strip():
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"SSE 载荷不是合法 JSON：{payload[:200]}",
            code=PROTOCOL_CODE,
        ) from exc
    if not isinstance(data, dict):
        raise ProviderError(f"SSE 载荷不是 JSON 对象：{payload[:200]}", code=PROTOCOL_CODE)
    return data


def _usage_from_wire(raw: Any) -> Usage | None:
    """端点 `usage` 对象 → `Usage`；缺字段返回 None。"""
    if not isinstance(raw, dict):
        return None
    prompt = raw.get("prompt_tokens")
    completion = raw.get("completion_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        return None
    total = raw.get("total_tokens")
    details = raw.get("prompt_tokens_details") if isinstance(raw.get("prompt_tokens_details"), dict) else {}
    cache_read = details.get("cached_tokens")
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total if isinstance(total, int) else None,
        estimated=False,
        cache_read_tokens=cache_read if isinstance(cache_read, int) else None,
    )


def _map_finish_reason(wire_reason: str, model: str) -> FinishReason:
    mapped = _FINISH_REASONS.get(wire_reason)
    if mapped is None:
        logger.debug("[agent-llm] 端点 %s 返回未知 finish_reason=%r，按 stop 处理", model, wire_reason)
        return FinishReason.STOP
    return mapped


def _error_from_body(raw: Any) -> AgentLlmError:
    """带内 `{"error": {...}}` → 异常对象（消息脱敏，只带端点文本）。"""
    if isinstance(raw, dict):
        detail = str(raw.get("message") or raw.get("type") or raw.get("code") or raw)
        code = raw.get("code")
        text = f"{code} {detail}" if isinstance(code, str) and code else detail
        return error_for(classify_detail(text), f"端点返回错误：{detail}")
    return error_for(classify_detail(str(raw)), f"端点返回错误：{raw}")


def _http_error(exc: urllib.error.HTTPError) -> AgentLlmError:
    """HTTP 状态失败 → 异常对象；`Retry-After` 转为重试等待秒数。"""
    detail = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")[:2000]
    except Exception:  # noqa: BLE001 — 读不到响应体不影响状态分类
        body = ""
    if body:
        detail = _detail_from_body(body)
    code = classify_detail(detail, exc.code)
    retry_after = _parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
    summary = f"HTTP {exc.code}"
    if detail:
        summary = f"{summary}：{detail}"
    if code == INVALID_REQUEST_CODE:
        summary = f"{summary}（该请求不可重试）"
    return error_for(code, summary, status=exc.code, retry_after_s=retry_after)


def _detail_from_body(body: str) -> str:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body[:500]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or error)[:500]
        if error is not None:
            return str(error)[:500]
    return body[:500]


def _parse_retry_after(raw: str | None) -> float | None:
    """解析 `Retry-After`；支持秒数与 HTTP 日期之外的纯数字形式。"""
    if not raw:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        logger.debug("[agent-llm] 无法解析 Retry-After=%r，改用本地退避", raw)
        return None
    return value if value > 0 else None
