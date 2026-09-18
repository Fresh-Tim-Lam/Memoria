# 语义移植自 deepseek-harness packages/llm/llm（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""agent LLM 调用的异常层级与「是否可重试」判定。

对应上游 `dsh-llm/src/error.ts`（稳定机器可路由 `code` + 失败分类）与
`dsh-llm-retry` 的默认可重试集合：消费方按 `code` 路由，绝不解析消息文本。

- `AgentLlmError`：基类，携带稳定 `code`，可选 HTTP `status` 与 `retry_after_s`；
- `ConfigError` / `AuthError` / `RateLimited` / `LlmTimeoutError` / `ProviderError`；
- `is_retryable()`：429 / 5xx / 网络超时 / 连接重置可重试；**确定性连接失败**
  （连接被拒 / DNS 解析失败 / TLS 证书校验失败 / 无效 URL，见 `is_unreachable()`）
  归为 `UNREACHABLE` 且**不重试**；其余 4xx 不重试。

异常消息中**绝不出现密钥**：凭据问题只点名配置来源（环境变量名或配置文件），
不回显取值。
"""

from __future__ import annotations

import errno as _errno
import http.client
import re
import socket
import ssl
from typing import Any

__all__ = [
    "AgentLlmError",
    "AuthError",
    "ConfigError",
    "LlmTimeoutError",
    "ProviderError",
    "RateLimited",
    "RETRYABLE_CODES",
    "UNREACHABLE_CODE",
    "classify_detail",
    "code_for_status",
    "error_for",
    "is_context_window_exceeded",
    "is_quota_exceeded",
    "is_retryable",
    "is_unreachable",
    "unreachable_kind",
]

# —— 与上游共享的稳定 code 词汇（`HarnessError.code` / 失败 code 常量）——
CONFIG_CODE = "CONFIG"
AUTH_CODE = "AUTH"
MISSING_CREDENTIAL_CODE = "MISSING_CREDENTIAL"
INVALID_CREDENTIAL_CODE = "INVALID_CREDENTIAL"
RATE_LIMIT_CODE = "RATE_LIMIT"
QUOTA_EXCEEDED_CODE = "QUOTA"
CONTEXT_WINDOW_EXCEEDED_CODE = "CONTEXT_WINDOW_EXCEEDED"
EMPTY_RESPONSE_CODE = "EMPTY_RESPONSE"
SERVER_CODE = "SERVER"
TRANSPORT_CODE = "TRANSPORT"
TIMEOUT_CODE = "TIMEOUT"
#: 新增（非上游词汇）：**确定性**连接失败——连接被拒 / DNS 解析失败 / TLS 证书
#: 校验失败 / 无效 URL。重试必然会以同样方式失败，故**刻意不进** `RETRYABLE_CODES`。
UNREACHABLE_CODE = "UNREACHABLE"
INVALID_REQUEST_CODE = "INVALID_REQUEST"
PROTOCOL_CODE = "PROTOCOL"
NO_ADAPTER_CODE = "NO_ADAPTER"
DUPLICATE_ADAPTER_CODE = "DUPLICATE_ADAPTER"

#: 上游 `retry-policy.ts` 的默认可重试集合（normal 模式）。
#: 本轮**未增未删**：`UNREACHABLE` 是新增的独立 code，不在其中。
RETRYABLE_CODES: frozenset[str] = frozenset(
    {EMPTY_RESPONSE_CODE, RATE_LIMIT_CODE, SERVER_CODE, TIMEOUT_CODE, TRANSPORT_CODE}
)

# 非重试的永久性 code：每次尝试都会以同样方式失败。
_TERMINAL_CODES: frozenset[str] = frozenset(
    {
        CONFIG_CODE,
        AUTH_CODE,
        MISSING_CREDENTIAL_CODE,
        INVALID_CREDENTIAL_CODE,
        QUOTA_EXCEEDED_CODE,
        CONTEXT_WINDOW_EXCEEDED_CODE,
        INVALID_REQUEST_CODE,
        PROTOCOL_CODE,
        NO_ADAPTER_CODE,
        DUPLICATE_ADAPTER_CODE,
        UNREACHABLE_CODE,
    }
)

#: `URLError` 里以**字符串**形式给出的"无效 URL"提示（`reason` 非异常对象）。
_UNREACHABLE_TEXT_MARKERS = ("unknown url type", "no host given", "no host supplied")

#: 端点报错文本里的**确定性**连接失败措辞（命中即归 `UNREACHABLE`，不重试）。
#: 刻意只收确定性措辞：`connection reset/aborted/broken pipe` 属瞬时故障，仍归 `TRANSPORT`。
_UNREACHABLE_DETAIL = re.compile(
    r"connection\s+refused|actively\s+refused|getaddrinfo|name\s+or\s+service\s+not\s+known"
    r"|nodename\s+nor\s+servname|certificate\s+verify\s+failed|self[- ]signed\s+certificate"
    r"|no\s+host\s+given|unknown\s+url\s+type",
    re.IGNORECASE,
)

#: Windows 的"目标计算机积极拒绝"（`ConnectionRefusedError` 已覆盖，此处兜底裸 OSError）。
_WINERROR_CONNECTION_REFUSED = 10061


class AgentLlmError(Exception):
    """agent LLM 调用失败基类：稳定 code + 可选 HTTP 事实。"""

    #: 子类默认 code；实例可用 `code=` 覆盖为更精确的稳定值。
    code: str = "AGENT_LLM"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        if not isinstance(message, str) or not message:
            raise ValueError("AgentLlmError message 必须是非空字符串")
        resolved = code or type(self).code
        if not isinstance(resolved, str) or not resolved:
            raise ValueError("AgentLlmError code 必须是非空字符串")
        if status is not None and (not isinstance(status, int) or not 100 <= status <= 599):
            raise ValueError("AgentLlmError status 必须是 100–599 的整数")
        if retry_after_s is not None and (not isinstance(retry_after_s, (int, float)) or retry_after_s <= 0):
            raise ValueError("AgentLlmError retry_after_s 必须是正数")
        super().__init__(message)
        self.code = resolved
        self.status = status
        self.retry_after_s = float(retry_after_s) if retry_after_s is not None else None

    def __repr__(self) -> str:
        facts = [f"code={self.code!r}"]
        if self.status is not None:
            facts.append(f"status={self.status}")
        if self.retry_after_s is not None:
            facts.append(f"retry_after_s={self.retry_after_s!r}")
        return f"{type(self).__name__}({self.args[0]!r}, {', '.join(facts)})"

    def to_failure(self) -> dict[str, Any]:
        """可序列化失败事实（对齐上游 `LlmFailure`）。"""
        failure: dict[str, Any] = {"message": str(self), "code": self.code}
        if self.status is not None:
            failure["status"] = self.status
        if self.retry_after_s is not None:
            failure["providerRetryAfterMs"] = int(self.retry_after_s * 1000)
        return failure


class ConfigError(AgentLlmError):
    """配置缺失或非法（端点、模型名、超时值等）。"""

    code = CONFIG_CODE


class AuthError(AgentLlmError):
    """凭据缺失或不可用；`code` 可为 `MISSING_CREDENTIAL` / `INVALID_CREDENTIAL` / `AUTH`。"""

    code = AUTH_CODE


class RateLimited(AgentLlmError):
    """被端点限流（HTTP 429）；可携带 `Retry-After` 秒数。"""

    code = RATE_LIMIT_CODE


class LlmTimeoutError(AgentLlmError):
    """请求或流读取超时（自定义名，避免与内建 `TimeoutError` 混淆）。"""

    code = TIMEOUT_CODE


class ProviderError(AgentLlmError):
    """端点侧失败：4xx/5xx、协议错、连接中断、空响应等。

    `code` 取 `SERVER` / `INVALID_REQUEST` / `TRANSPORT` / `PROTOCOL` /
    `EMPTY_RESPONSE` / `QUOTA` 等稳定值。
    """

    code = "PROVIDER"


def _root_cause(error: BaseException) -> BaseException:
    """剥开 `urllib.error.URLError` 等包装层，取最底层的失败原因。

    `URLError` 自身是 `OSError` 子类，其 `reason` 才是真实的 `socket`/`ssl` 异常；
    分类必须先下钻，否则"连接被拒"会被当成笼统的连接错误。
    """
    seen: set[int] = set()
    current = error
    while id(current) not in seen:
        seen.add(id(current))
        reason = getattr(current, "reason", None)
        if isinstance(reason, BaseException):
            current = reason
        else:
            break
    return current


def is_unreachable(error: BaseException) -> bool:
    """是否为**确定性**连接失败：重试必然以同样方式失败，故不应重试。

    覆盖：连接被拒（`ConnectionRefusedError` / WinError 10061）、DNS 解析失败
    （`socket.gaierror`）、TLS 证书校验失败（`ssl.SSLCertVerificationError`）、
    无效 URL（`http.client.InvalidURL` 或 `URLError("unknown url type…")`）。

    与**瞬时故障**（超时 / 连接重置 / broken pipe / 5xx / 429）相对；后者仍可重试。
    """
    if getattr(error, "code", None) == UNREACHABLE_CODE:
        return True  # 已按本 code 分类过的失败（幂等）
    cause = _root_cause(error)
    if isinstance(cause, (ConnectionRefusedError, socket.gaierror, ssl.SSLCertVerificationError)):
        return True
    if isinstance(cause, ssl.SSLError) and "CERTIFICATE_VERIFY_FAILED" in str(cause).upper():
        return True
    if isinstance(cause, http.client.InvalidURL):
        return True
    if getattr(cause, "winerror", None) == _WINERROR_CONNECTION_REFUSED:
        return True
    if getattr(cause, "errno", None) == _errno.ECONNREFUSED:
        return True
    text = str(cause).lower()
    return any(marker in text for marker in _UNREACHABLE_TEXT_MARKERS)


def unreachable_kind(error: BaseException) -> str:
    """确定性连接失败的中文归类（供异常消息拼装；不含凭据）。"""
    cause = _root_cause(error)
    if isinstance(cause, ConnectionRefusedError) or getattr(cause, "winerror", None) == _WINERROR_CONNECTION_REFUSED:
        return "目标端口拒绝连接"
    if getattr(cause, "errno", None) == _errno.ECONNREFUSED:
        return "目标端口拒绝连接"
    if isinstance(cause, socket.gaierror):
        return "域名解析失败"
    if isinstance(cause, ssl.SSLCertVerificationError) or isinstance(cause, ssl.SSLError):
        return "TLS 证书校验失败"
    if isinstance(cause, http.client.InvalidURL):
        return "端点 URL 无效"
    return "端点 URL 无效或不可达"


def is_retryable(error: BaseException) -> bool:
    """判断一次失败是否值得重试（429 / 5xx / 超时 / 连接中断）。

    未知失败一律判为不可重试（fail closed），与上游「不在合格集合内的失败
    原样委派」一致；确定性连接失败（`is_unreachable()`）明确判为不可重试。
    """
    if isinstance(error, (ConfigError, AuthError)):
        return False
    if isinstance(error, RateLimited):
        return True
    if isinstance(error, LlmTimeoutError):
        return True
    if isinstance(error, ProviderError):
        if error.code in _TERMINAL_CODES:
            return False
        if error.code in RETRYABLE_CODES:
            return True
        return error.status is not None and error.status >= 500
    if isinstance(error, AgentLlmError):
        return error.code in RETRYABLE_CODES
    # 网络层异常（socket 超时、连接重置、DNS 失败等）都是 OSError 子类；
    # 本模块只用于模型调用边界，故整体视为可重试——**确定性连接失败除外**。
    if isinstance(error, OSError):
        return not is_unreachable(error)
    return False


def code_for_status(status: int) -> str:
    """HTTP 状态 → 稳定失败 code。"""
    if status == 429:
        return RATE_LIMIT_CODE
    if status in (401, 403):
        return AUTH_CODE
    if status >= 500:
        return SERVER_CODE
    if status in (408, 504):
        return TIMEOUT_CODE
    return INVALID_REQUEST_CODE


# 上游 `error.ts` 的上下文溢出识别（结构化 + 自然语言措辞）。
_STRUCTURED_CONTEXT_OVERFLOW = re.compile(
    r"(?:^|[^a-z0-9])context[\s_-](?:length|window)[\s_-]"
    r"(?:exceed(?:ed|s)?|overflow(?:ed)?|limit[\s_-]exceeded)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_TOO_LARGE_FOR_CONTEXT = re.compile(
    r"\b(?:request|prompt|input|messages?)\s+(?:is\s+|are\s+)?"
    r"too\s+(?:large|long)\s+for\s+(?:(?:this|the)\s+)?"
    r"(?:model(?:'s)?\s+)?context(?:\s+window)?\b",
    re.IGNORECASE,
)
_MAX_CONTEXT_LENGTH = re.compile(
    r"\b(?:maximum|max)(?:\s+(?:allowed|supported))?\s+context\s+(?:length|window)\b",
    re.IGNORECASE,
)
_QUOTA_PATTERNS = (
    re.compile(r"\binsufficient[\s_-]+(?:quota|balance|credits?)\b", re.IGNORECASE),
    re.compile(r"\b(?:quota|usage[\s_-]+limit)[\s_-]+(?:exceeded|exhausted|reached)\b", re.IGNORECASE),
    re.compile(r"\bexceed(?:ed|s)?[\s_-]+(?:(?:your|the)[\s_-]+)?(?:current[\s_-]+)?quota\b", re.IGNORECASE),
    re.compile(r"\b(?:balance|credits?)[\s_-]+(?:exhausted|depleted)\b", re.IGNORECASE),
    re.compile(r"\bout[\s_-]+of[\s_-]+(?:credits?|budget)\b", re.IGNORECASE),
)


def is_context_window_exceeded(detail: str) -> bool:
    """端点文本是否表明请求超出模型上下文窗口（不可重试）。"""
    return bool(
        _STRUCTURED_CONTEXT_OVERFLOW.search(detail)
        or _MAX_CONTEXT_LENGTH.search(detail)
        or _TOO_LARGE_FOR_CONTEXT.search(detail)
    )


def is_quota_exceeded(detail: str) -> bool:
    """端点文本是否表明账户配额/余额耗尽（不可重试，区别于瞬时限流）。"""
    return any(pattern.search(detail) for pattern in _QUOTA_PATTERNS)


def classify_detail(detail: str, status: int | None = None) -> str:
    """把端点报错文本 + 可选状态码归类为稳定 code（上游 `classifyPiAiError` 语义）。

    依据：先看配额/上下文这类永久性失败，再看状态码，最后看措辞关键词。
    """
    if is_quota_exceeded(detail):
        return QUOTA_EXCEEDED_CODE
    if is_context_window_exceeded(detail):
        return CONTEXT_WINDOW_EXCEEDED_CODE
    if status is not None:
        return code_for_status(status)
    if re.search(r"\b(?:401|403)\b", detail):
        return AUTH_CODE
    if re.search(r"\b429\b|rate.?limit", detail, re.IGNORECASE):
        return RATE_LIMIT_CODE
    if re.search(r"\b(?:400|413|422)\b|invalid.?request|payload too large", detail, re.IGNORECASE):
        return INVALID_REQUEST_CODE
    if re.search(r"\b5\d\d\b", detail):
        return SERVER_CODE
    if re.search(r"\btime(?:d)?\s*out\b|timeout", detail, re.IGNORECASE):
        return TIMEOUT_CODE
    if _UNREACHABLE_DETAIL.search(detail):
        # 端点带内报错里的确定性连接失败（无 HTTP 状态可依据时）——不重试。
        return UNREACHABLE_CODE
    if re.search(r"\b(?:network|connection|socket|fetch|terminated)\b|ECONN[A-Z]+", detail, re.IGNORECASE):
        return TRANSPORT_CODE
    return PROTOCOL_CODE


def error_for(code: str, message: str, *, status: int | None = None, retry_after_s: float | None = None) -> AgentLlmError:
    """按稳定 code 构造对应异常类型（供适配器统一映射）。"""
    if code == AUTH_CODE:
        return AuthError(message, status=status)
    if code == MISSING_CREDENTIAL_CODE or code == INVALID_CREDENTIAL_CODE:
        return AuthError(message, code=code, status=status)
    if code == RATE_LIMIT_CODE:
        return RateLimited(message, status=status, retry_after_s=retry_after_s)
    if code == TIMEOUT_CODE:
        return LlmTimeoutError(message, status=status)
    return ProviderError(message, code=code, status=status, retry_after_s=retry_after_s)
