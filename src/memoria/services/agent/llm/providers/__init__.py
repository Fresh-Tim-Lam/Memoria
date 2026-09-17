# 语义移植自 deepseek-harness packages/llm/llm-pi-ai（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""内置 provider 适配器与注册。

上游 `dsh-llm-pi-ai` 的 `providers` 字典即整个配置面：每个键都是请求可选择的
路由名。本包目前只移植 **OpenAI 兼容**那一部分（`openai-compatible`，含
`openai_compatible` 别名），注册发生在导入本包时（无网络、无文件 IO）。
"""

from __future__ import annotations

from memoria.services.agent.llm.config import AgentConfig
from memoria.services.agent.llm.providers.openai_compatible import (
    PROVIDER_NAMES,
    OpenAICompatibleProvider,
    SseDecoder,
    chat_completions_url,
)

__all__ = [
    "OpenAICompatibleProvider",
    "PROVIDER_NAMES",
    "SseDecoder",
    "chat_completions_url",
    "register_builtin_providers",
]


def _factory(config: AgentConfig) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(config)


def register_builtin_providers() -> None:
    """注册内置 provider 路由（幂等）。"""
    from memoria.services.agent.llm.provider import register_provider

    for name in PROVIDER_NAMES:
        register_provider(name, _factory, replace=True)


register_builtin_providers()
