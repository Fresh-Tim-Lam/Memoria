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

键 `enabled`（是否允许出网）与 `status_refresh_ms`（状态 bar 刷新间隔，毫秒整数）都是
**UI 旋钮**、不是调用参数，故**不参与** `load_config()` 的逐字段回退：由 `is_enabled()` /
`status_refresh_ms()` / `save_config()` 读写同一份 JSON（缺省与细节见文件末尾那段）。

密钥只从环境或本地文件读取，**绝不进入日志、异常消息或 `repr`**（掩码见
`mask_secret`）。导入本模块不联网、不读文件：只有显式调用 `load_config()`
才会解析本地 JSON。端点凭据格式判定移植自上游 `api-key.ts`
（trim 后必须为可打印 ASCII，空格除外）。

写侧（`save_config`）只服务于 UI 配置面板：浅合并 + 原子写，密钥**只在传入非空
新值时才覆盖**（避免掩码占位把已存密钥清空）。
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
    "ENABLED_KEY",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "ENV_CONFIG_DIR",
    "ENV_CONFIG_FILE",
    "ENV_MODEL",
    "ENV_TIMEOUT_S",
    "config_file_path",
    "is_enabled",
    "load_config",
    "mask_secret",
    "normalize_api_key",
    "read_raw_config",
    "save_config",
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
#: 「允许出网」开关的 JSON 键（缺省视为开）。
ENABLED_KEY = "enabled"

_JSON_KEYS = ("base_url", "api_key", "model", "timeout_s", "status_refresh_ms", ENABLED_KEY)
#: UI 可写键白名单（`save_config` 只接受这些键）。
_WRITABLE_KEYS = frozenset(_JSON_KEYS)
#: 文本类键（trim 后原样存）。
_TEXT_KEYS = frozenset({"base_url", "model"})
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


# ── 写侧（UI 配置面板用）────────────────────────────────────────────────────


def read_raw_config(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """本地 JSON 的**原始键值**（不做逐字段回退，也不丢弃未知键）。

    与 `_read_file_config` 的差别：这里服务于"读—改—写"往返，故①**完整保留**
    未知键（用户手写的其它字段不得被面板覆盖掉）；②文件缺失/损坏时返回空 dict
    而不抛错（面板仍需可用，读取侧的严格校验由 `load_config()` 负责）。
    """
    path = config_file_path(env)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("[agent-llm] 本地配置无法解析，按空配置处理：%s", path)
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _coerce_enabled(value: Any) -> bool:
    """宽松解析「出网」开关：布尔原样；字符串按 0/false/no/off 判否；其余按真假值。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off")
    return bool(value)


def is_enabled(env: Mapping[str, str] | None = None) -> bool:
    """是否允许出网（`enabled` 键）；缺省 / 非布尔值时视为 **True**。

    用户口径：默认可用、可一键关（见 `docs/design/dsh-agent-port.md`）。
    """
    return _coerce_enabled(read_raw_config(env).get(ENABLED_KEY))


def save_config(
    patch: Mapping[str, Any],
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """浅合并写入本地 JSON（tmp + `os.replace` 原子写），返回合并后的完整对象。

    约定（与桌面端配置面板一致）：

    - 只接受白名单键 `base_url` / `api_key` / `model` / `timeout_s` / `enabled`
      以及 `status_refresh_ms`，其它键报 `ConfigError`（绝不写文件）；
    - `api_key` **仅在传入非空新值时覆盖**——面板回显的是掩码，空值表示"不修改"；
    - `timeout_s` 空值同样表示"不修改"，非空则沿用 `load_config()` 的同一套校验
      （正数），非法值不落盘；`status_refresh_ms` 同口径（正整数毫秒）；
    - 文件里已有的未知键原样保留。
    """
    if not isinstance(patch, Mapping):
        raise ConfigError("配置 patch 必须是键值对象")
    unknown = sorted(str(key) for key in patch if str(key) not in _WRITABLE_KEYS)
    if unknown:
        raise ConfigError(f"不支持的配置键：{', '.join(unknown)}")

    path = config_file_path(env)
    current = read_raw_config(env)
    for key, value in patch.items():
        name = str(key)
        if name == "api_key":
            secret = "" if value is None else str(value).strip()
            if secret:
                current[name] = secret
            continue
        if name == ENABLED_KEY:
            current[name] = _coerce_enabled(value)
            continue
        if name == "timeout_s":
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            current[name] = _coerce_timeout(value, origin=str(path))
            continue
        if name in _TEXT_KEYS:
            current[name] = "" if value is None else str(value).strip()
            continue
        # 追加键（2026-09-19）：放在分支链末位 ⇒ 既有键的处理行号零漂移
        if name == "status_refresh_ms" and value not in (None, ""):
            current[name] = _coerce_status_refresh_ms(value, origin=str(path))

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return current


# ── 状态 bar 刷新间隔（2026-09-19；桌面端 UI 计时器旋钮）────────────────────────
# **与 `enabled` 同类**：它是 UI 旋钮、不是模型调用参数，故不进 `AgentConfig`、也不参与
# `load_config()` 的逐字段回退；由 `status_refresh_ms()` / `save_config()` 读写同一份 JSON。
# 取值 = **毫秒整数**（前端只给 7 档：5000 / 15000 / 30000 / 60000 / 300000 / 600000 / 3600000，
# 由 `agent-panel.js::STATUS_REFRESH_CHOICES` 收敛）。本段整体追加在文件末尾 ⇒ 上方所有
# `<文件>:<行号>` 锚点零漂移。
_STATUS_REFRESH_KEY = "status_refresh_ms"
#: 状态 bar 的默认刷新间隔（毫秒）；60 000 = 既有余额槽 60s TTL 的节拍，也是七档里的 `1min`。
DEFAULT_STATUS_REFRESH_MS = 60000


def status_refresh_ms(env: Mapping[str, str] | None = None) -> int:
    """状态 bar 的刷新间隔（毫秒）；缺省 / 非法值一律回退 `DEFAULT_STATUS_REFRESH_MS`。

    宽松口径与 `is_enabled()` 一致（手改坏值不该让配置视图 RPC 失败）；**严格校验在
    写侧**（`save_config` 走 `_coerce_status_refresh_ms`）。
    """
    raw = read_raw_config(env).get(_STATUS_REFRESH_KEY)
    try:
        ms = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_STATUS_REFRESH_MS
    return ms if ms > 0 else DEFAULT_STATUS_REFRESH_MS


def _coerce_status_refresh_ms(value: Any, origin: str) -> int:
    """写侧校验：**正整数毫秒**（档位由前端收敛为 7 档，这里只做正数校验）。"""
    try:
        ms = int(float(value))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{origin} 的刷新间隔必须是毫秒数，收到 {value!r}") from exc
    if ms <= 0:
        raise ConfigError(f"{origin} 的刷新间隔必须为正数，收到 {ms!r}")
    return ms
