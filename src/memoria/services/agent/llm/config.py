# 语义移植自 deepseek-harness packages/llm/llm（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""agent LLM 的配置来源与凭据掩码。

配置优先级（逐字段回退）：环境变量 → 本地 `config/agent.json` → 默认值。

| 字段 | 环境变量 | JSON 键 |
|---|---|---|
| 端点 | `MEMORIA_AGENT_BASE_URL` | `base_url` |
| 密钥 | `MEMORIA_AGENT_API_KEY` | `api_key` |
| 模型 | `MEMORIA_AGENT_MODEL` | `model` |
| 超时（秒） | `MEMORIA_AGENT_TIMEOUT_S` | `timeout_s` |

密钥只从环境或本地文件读取，**绝不进入日志、异常消息或 `repr`**（掩码见
`mask_secret`）。导入本模块不联网、不读文件：只有显式调用 `load_config()`
才会解析本地 JSON。端点凭据格式判定移植自上游 `api-key.ts`
（trim 后必须为可打印 ASCII，空格除外）。
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memoria.services.agent.llm.errors import (
    INVALID_CREDENTIAL_CODE,
    MISSING_CREDENTIAL_CODE,
    AuthError,
    ConfigError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AgentConfig",
    "CONFIG_FILENAME",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_S",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "ENV_CONFIG_DIR",
    "ENV_CONFIG_FILE",
    "ENV_MODEL",
    "ENV_TIMEOUT_S",
    "config_file_path",
    "load_config",
    "mask_secret",
    "normalize_api_key",
]

ENV_BASE_URL = "MEMORIA_AGENT_BASE_URL"
ENV_API_KEY = "MEMORIA_AGENT_API_KEY"
ENV_MODEL = "MEMORIA_AGENT_MODEL"
ENV_TIMEOUT_S = "MEMORIA_AGENT_TIMEOUT_S"
#: 显式指定本地 JSON 配置路径（测试/多环境用）。
ENV_CONFIG_FILE = "MEMORIA_AGENT_CONFIG"
#: 与 `memoria.storage.ui_settings` 共用的配置目录覆盖。
ENV_CONFIG_DIR = "MEMORIA_CONFIG_DIR"

CONFIG_FILENAME = "agent.json"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT_S = 60.0

_JSON_KEYS = ("base_url", "api_key", "model", "timeout_s")
#: HTTP 头可原样承载、且各端点密钥实际使用的字符集（上游 `LEGAL_API_KEY`）。
_LEGAL_API_KEY = re.compile(r"^[\x21-\x7E]+$")


def mask_secret(secret: str | None) -> str:
    """掩码凭据：只保留极少前缀与长度，绝不返回完整取值。"""
    value = (secret or "").strip()
    if not value:
        return ""
    if len(value) < 8:
        return "***"
    return f"{value[:3]}***（len={len(value)}）"


def normalize_api_key(raw: str) -> str:
    """校验并返回可用的密钥；不可用时抛 `AuthError`（不回显取值）。

    与上游 `assertUsableApiKey` 一致：先静默 trim（.env/导出常带空白），
    空值报 `MISSING_CREDENTIAL`，含 HTTP 头无法承载的字符报
    `INVALID_CREDENTIAL`；诊断只点名配置来源。
    """
    value = (raw or "").strip()
    if not value:
        raise AuthError(
            f"密钥为空；请设置环境变量 {ENV_API_KEY}（或 {CONFIG_FILENAME} 的 api_key）为原始密钥",
            code=MISSING_CREDENTIAL_CODE,
        )
    if not _LEGAL_API_KEY.match(value):
        raise AuthError(
            f"密钥包含 HTTP 头无法承载的字符；请把 {ENV_API_KEY}"
            f"（或 {CONFIG_FILENAME} 的 api_key）设为原始密钥本身",
            code=INVALID_CREDENTIAL_CODE,
        )
    return value


@dataclass(frozen=True, slots=True, repr=False)
class AgentConfig:
    """一次 agent 会话的端点配置；`repr` 掩码密钥（凭据绝不外显）。"""

    base_url: str = ""
    api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S
    #: 诊断用：各字段最终来源（`env` / `file:<path>` / `default`），不含敏感值。
    source: str = "default"

    def __repr__(self) -> str:
        return (
            "AgentConfig("
            f"base_url={self.base_url!r}, api_key={mask_secret(self.api_key)!r}, "
            f"model={self.model!r}, timeout_s={self.timeout_s!r}, source={self.source!r})"
        )

    __str__ = __repr__

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())

    def require_api_key(self) -> str:
        """返回可用密钥；缺失/非法时抛 `AuthError`。"""
        return normalize_api_key(self.api_key)

    def require_base_url(self) -> str:
        """返回去掉尾斜杠的端点；缺失时抛 `ConfigError`。"""
        value = (self.base_url or "").strip()
        if not value:
            raise ConfigError(
                f"未配置模型端点；请设置环境变量 {ENV_BASE_URL}（或 {CONFIG_FILENAME} 的 base_url）"
            )
        return value.rstrip("/")


def config_file_path(env: Mapping[str, str] | None = None) -> Path:
    """本地 JSON 配置路径（`MEMORIA_AGENT_CONFIG` > `MEMORIA_CONFIG_DIR` > 仓库根 `config/`）。"""
    environ: Mapping[str, str] = os.environ if env is None else env
    override = environ.get(ENV_CONFIG_FILE)
    if override:
        return Path(override)
    config_dir = environ.get(ENV_CONFIG_DIR)
    if config_dir:
        return Path(config_dir) / CONFIG_FILENAME
    # src/memoria/services/agent/llm/config.py → 上溯到仓库根
    return Path(__file__).resolve().parents[5] / "config" / CONFIG_FILENAME


def _read_file_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"本地配置 {path} 无法解析为 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"本地配置 {path} 顶层必须是 JSON 对象")
    unknown = sorted(set(raw) - set(_JSON_KEYS))
    if unknown:
        logger.warning("[agent-llm] %s 含未知键，已忽略：%s", path, ", ".join(unknown))
    return {k: raw[k] for k in _JSON_KEYS if k in raw}


def _coerce_timeout(value: Any, origin: str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{origin} 的超时值必须是秒数，收到 {value!r}") from exc
    if timeout <= 0:
        raise ConfigError(f"{origin} 的超时值必须为正数，收到 {timeout!r}")
    return timeout


def load_config(env: Mapping[str, str] | None = None) -> AgentConfig:
    """读取配置：环境变量 → 本地 JSON → 默认值；不联网、不写文件。

    `env` 省略时读 `os.environ`（测试可注入映射以完全离线复现）。
    """
    environ: Mapping[str, str] = os.environ if env is None else env
    path = config_file_path(environ)
    file_values = _read_file_config(path)
    source_file = f"file:{path}"

    def pick(env_key: str, json_key: str) -> tuple[Any, str | None]:
        raw = environ.get(env_key)
        if raw is not None and str(raw).strip() != "":
            return raw, "env"
        if json_key in file_values and file_values[json_key] not in (None, ""):
            return file_values[json_key], source_file
        return None, None

    base_url, src_base = pick(ENV_BASE_URL, "base_url")
    api_key, src_key = pick(ENV_API_KEY, "api_key")
    model, src_model = pick(ENV_MODEL, "model")
    timeout, src_timeout = pick(ENV_TIMEOUT_S, "timeout_s")

    origins = [s for s in (src_base, src_key, src_model, src_timeout) if s]
    if not origins:
        source = "default"
    elif all(s == "env" for s in origins) or all(s == source_file for s in origins):
        source = origins[0]
    else:
        source = "mixed"

    return AgentConfig(
        base_url=str(base_url or "").strip(),
        api_key=str(api_key or "").strip(),
        model=str(model or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        timeout_s=_coerce_timeout(timeout, origin=src_timeout or "default")
        if timeout is not None
        else DEFAULT_TIMEOUT_S,
        source=source,
    )
