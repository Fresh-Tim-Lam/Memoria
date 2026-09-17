# 语义移植自 deepseek-harness packages/llm/llm（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""provider 中立接口与按名注册表。

对应上游 `dsh-llm/src/index.ts` 的适配器注册表语义：服务本身不含任何 provider
协议代码，只定义「一次流 = 一次 provider 尝试」的调用面与注册表；协议由适配器
拥有（`providers/` 下的模块）。

- `LlmProvider`：provider 中立接口（`typing.Protocol`，结构化）；
- `register_provider` / `create_provider`：按配置名取适配器实例；
- 未知路由名抛 `NO_ADAPTER`，重复注册同名路由抛 `DUPLICATE_ADAPTER`（对齐上游）。

导入本模块不联网、不读配置文件；内置 provider 采用惰性注册（首次取实例时导入
`providers/`），因此单独导入本模块也不会产生额外副作用。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Protocol, runtime_checkable

from memoria.services.agent.llm.config import AgentConfig, load_config
from memoria.services.agent.llm.errors import (
    DUPLICATE_ADAPTER_CODE,
    NO_ADAPTER_CODE,
    ConfigError,
)
from memoria.services.agent.llm.types import LlmRequest, StreamEvent

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_PROVIDER_NAME",
    "LlmProvider",
    "ProviderFactory",
    "create_provider",
    "provider_names",
    "register_provider",
    "unregister_provider",
]

#: 未显式指定 provider 时的默认路由名。
DEFAULT_PROVIDER_NAME = "openai-compatible"

ProviderFactory = Callable[[AgentConfig], "LlmProvider"]

_factories: dict[str, ProviderFactory] = {}
_builtins_loaded = False


@runtime_checkable
class LlmProvider(Protocol):
    """provider 中立调用面：一次 `stream()` 就是一次 provider 尝试。"""

    #: 注册用的路由名。
    name: str

    def stream(self, request: LlmRequest) -> Iterator[StreamEvent]:
        """发起一次调用，按到达顺序产出流式事件。

        约定（对齐上游 `StreamChunk` 协议）：`UsageEvent` 先于终止
        `FinishEvent`；终止事件之后不再产出任何事件；请求失败在**尚未产出任何
        事件**时抛 `AgentLlmError` 子类，已开始产出后的失败以带 `failure` 的
        终止 `FinishEvent` 投递。
        """
        ...


def register_provider(name: str, factory: ProviderFactory, *, replace: bool = False) -> None:
    """注册一个 provider 路由名；重复注册默认拒绝。"""
    key = (name or "").strip()
    if not key:
        raise ConfigError("provider 名不能为空")
    if key in _factories and not replace:
        raise ConfigError(
            f"provider 路由 {key!r} 已注册；如需覆盖请显式 replace=True",
            code=DUPLICATE_ADAPTER_CODE,
        )
    _factories[key] = factory


def unregister_provider(name: str) -> None:
    """移除一个 provider 路由；不存在时静默返回。"""
    _factories.pop((name or "").strip(), None)


def provider_names() -> tuple[str, ...]:
    """已注册的路由名（注册顺序）。"""
    _ensure_builtins()
    return tuple(_factories)


def create_provider(name: str | None = None, *, config: AgentConfig | None = None) -> LlmProvider:
    """按配置名取 provider 实例；`config` 省略时读环境/本地配置。"""
    _ensure_builtins()
    key = (name or DEFAULT_PROVIDER_NAME).strip() or DEFAULT_PROVIDER_NAME
    factory = _factories.get(key)
    if factory is None:
        known = ", ".join(sorted(_factories)) or "（无）"
        raise ConfigError(f"未注册的 provider 路由 {key!r}；已知路由：{known}", code=NO_ADAPTER_CODE)
    settings = config if config is not None else load_config()
    return factory(settings)


def _ensure_builtins() -> None:
    """惰性导入内置 provider 并完成注册（避免导入期副作用与循环依赖）。"""
    global _builtins_loaded
    if _builtins_loaded:
        return
    from memoria.services.agent.llm import providers

    providers.register_builtin_providers()
    _builtins_loaded = True
