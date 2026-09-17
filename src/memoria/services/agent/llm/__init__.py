# 语义移植自 deepseek-harness packages/llm/*（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""Provider 中立的 LLM 调用层（dsh 移植 M1 第一块）。

分层与上游 `dsh-llm` 家族一一对应：

| 本包模块 | 上游 | 职责 |
|---|---|---|
| `types.py` | `llm/src/types.ts`、`message.ts` | 消息/请求/流式事件/用量词汇 |
| `errors.py` | `llm/src/error.ts` | 稳定 code 的异常层级与可重试判定 |
| `provider.py` | `llm/src/index.ts` | provider 中立接口与按名注册表 |
| `providers/openai_compatible.py` | `llm-pi-ai`（OpenAI 兼容部分） | `/chat/completions` + 手写 SSE |
| `retry.py` | `llm-retry`、`llm/src/retry-policy.ts` | 指数退避 + 抖动重试 |
| `usage.py` | `token-meter` | 用量计量与缺省估算 |
| `config.py` | `llm/src/api-key.ts`、`call-config.ts` | 环境/本地配置与凭据掩码 |

导入本包不联网、不读配置文件、不打印任何输出（日志走 `logging`）。
"""

from __future__ import annotations

from memoria.services.agent.llm.config import (
    AgentConfig,
    config_file_path,
    is_enabled,
    load_config,
    mask_secret,
    normalize_api_key,
    read_raw_config,
    save_config,
)
from memoria.services.agent.llm.errors import (
    AgentLlmError,
    AuthError,
    ConfigError,
    LlmTimeoutError,
    ProviderError,
    RateLimited,
    is_retryable,
)
from memoria.services.agent.llm.provider import (
    DEFAULT_PROVIDER_NAME,
    LlmProvider,
    create_provider,
    provider_names,
    register_provider,
    unregister_provider,
)
from memoria.services.agent.llm.providers import OpenAICompatibleProvider
from memoria.services.agent.llm.retry import (
    RetryPolicy,
    delay_for,
    iter_with_retry,
    local_delay,
    run_with_retry,
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
    ToolSchema,
    Usage,
    UsageEvent,
)
from memoria.services.agent.llm.usage import UsageMeter, estimate_usage

__all__ = [
    "AgentConfig",
    "AgentLlmError",
    "AuthError",
    "ConfigError",
    "DEFAULT_PROVIDER_NAME",
    "FinishEvent",
    "FinishReason",
    "LlmProvider",
    "LlmRequest",
    "LlmTimeoutError",
    "Message",
    "OpenAICompatibleProvider",
    "ProviderError",
    "RateLimited",
    "ReasoningDelta",
    "RetryPolicy",
    "Role",
    "StreamEvent",
    "TextDelta",
    "ToolCall",
    "ToolCallDelta",
    "ToolSchema",
    "Usage",
    "UsageEvent",
    "UsageMeter",
    "config_file_path",
    "create_provider",
    "delay_for",
    "estimate_usage",
    "is_enabled",
    "is_retryable",
    "iter_with_retry",
    "load_config",
    "local_delay",
    "mask_secret",
    "normalize_api_key",
    "provider_names",
    "read_raw_config",
    "register_provider",
    "run_with_retry",
    "save_config",
    "unregister_provider",
]
