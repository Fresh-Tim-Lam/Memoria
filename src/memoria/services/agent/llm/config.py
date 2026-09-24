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

_JSON_KEYS = ("base_url", "api_key", "model", "timeout_s", "status_refresh_ms", "transcript_mode", ENABLED_KEY, "permission", "search_base_url", "search_max_results", "fetch_max_bytes", "search_timeout_s", "fetch_timeout_s", "fetch_allow_domains", "fetch_deny_domains", "script_interpreter", "script_use_bundled", "script_timeout_s")
#: UI 可写键白名单（`save_config` 只接受这些键）。
_WRITABLE_KEYS = frozenset(_JSON_KEYS)
#: 文本类键（trim 后原样存）。
_TEXT_KEYS = frozenset({"base_url", "model", "search_base_url", "fetch_allow_domains", "fetch_deny_domains", "script_interpreter"})
#: HTTP 头可原样承载、且各端点密钥实际使用的字符集（上游 `LEGAL_API_KEY`）。
_LEGAL_API_KEY = re.compile(r"^[\x21-\x7E]+$")

# ── 联网（N 线，2026-09-23；§6.28）：出网基址与限额 ──────────────────────────────
# **与 `enabled` 不同**：这几组键是**调用参数**（联网工具要用）⇒ 进 `AgentConfig`，也进
# `save_config()` 的键白名单；`enabled` 仍是"UI 旋钮、不进调用参数"（见其段注）。默认值来源：
# 结果条数 **5**（与 `tools/kb.py` 的 `DEFAULT_TOP_K` 同值：一次检索回给模型的条目数与检索
# 命中数同一量级）、抓取字节 **2 MiB**（对齐 `SESSION_SCAN_MAX_BYTES` 的量级）、两侧超时
# **30s**（对齐上游 `searchTimeoutMs` 默认 30000）。基址推导见 `services/agent/web.py::
# anthropic_base_url`（缺省 = 从 `base_url` 推导；非 DeepSeek 端点须显式给 `search_base_url`）。
DEFAULT_SEARCH_MAX_RESULTS = 5
DEFAULT_FETCH_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_SEARCH_TIMEOUT_S = 30.0
DEFAULT_FETCH_TIMEOUT_S = 30.0
#: 正整数类联网键（写侧校验用）。
_WEB_POSITIVE_KEYS = frozenset({"search_max_results", "fetch_max_bytes"})
#: 秒数类联网键（写侧校验用；与 `timeout_s` 同一套 `_coerce_timeout`）。
_WEB_TIMEOUT_KEYS = frozenset({"search_timeout_s", "fetch_timeout_s"})

# ── 脚本工作区（人 2026-09-24 拍板；`services/agent/scratch.py`）──────────────────
# 三个键都是**脚本工作区**设置（设计见 `docs/design/agent-capabilities.md §3.4`）：
#   · `script_interpreter` 解释器显式路径（空 = 依次回落"发布包内置 → 系统"）；
#   · `script_use_bundled` 是否允许用发布包内置的那一份（关掉即只用系统解释器）；
#   · `script_timeout_s` 单次执行超时（`scratch.MIN/MAX_TIMEOUT_S` 会再夹一次）。
# 与 `enabled` 不同 ⇒ 它们是**调用参数**，进 `AgentConfig`、也进写白名单。
DEFAULT_SCRIPT_TIMEOUT_S = 60.0
#: 秒数类脚本键（写侧校验用）。
_SCRIPT_TIMEOUT_KEYS = frozenset({"script_timeout_s"})
#: 布尔类脚本键（写侧只做真值化）。
_SCRIPT_BOOL_KEYS = frozenset({"script_use_bundled"})


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
    #: 联网（N 线，2026-09-23；§6.28）：Anthropic 兼容面基址（空 = 按 `base_url` 推导）、
    #: 单次检索的条目上限、单次抓取的字节上限、检索与抓取各自的超时（秒）。
    search_base_url: str = ""
    search_max_results: int = DEFAULT_SEARCH_MAX_RESULTS
    fetch_max_bytes: int = DEFAULT_FETCH_MAX_BYTES
    search_timeout_s: float = DEFAULT_SEARCH_TIMEOUT_S
    fetch_timeout_s: float = DEFAULT_FETCH_TIMEOUT_S
    #: 抓取**域名名单**（2026-09-24；§3.3 的"域名单"落点）：逗号/空白分隔的域列表。
    #: `fetch_deny_domains` 命中即拒（优先）；`fetch_allow_domains` 非空 ⇒ 只允许列内（含子域）。
    #: 两者都为空 = 不限域名（仍受"拒私网/回环…"与出网总闸约束）。解析口径见 `web.py::parse_domains()`。
    fetch_allow_domains: str = ""
    fetch_deny_domains: str = ""
    #: 脚本工作区（人 2026-09-24 拍板）：解释器显式路径（空 = 发布包内置 → 系统）、
    #: 是否允许用内置解释器、单次执行超时（秒）。
    script_interpreter: str = ""
    script_use_bundled: bool = True
    script_timeout_s: float = DEFAULT_SCRIPT_TIMEOUT_S

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
        # `utf-8-sig` 而不是 `utf-8`（2026-09-24 真机踩到）：`config/agent.json` 是**人也会手改**的文件，
        # Windows 记事本 / PowerShell `Set-Content -Encoding utf8` 会写 **UTF-8 BOM** ⇒ 用 `utf-8` 读会把
        # `\ufeff` 留在串首、`json.loads` 报 `Unexpected UTF-8 BOM` ⇒ 整个配置读不出来（面板一片空、
        # 出网闸与名单全部回落默认，看着像"设置没生效"）。`utf-8-sig` 对**无 BOM** 的文件行为完全一致。
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
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
        **_web_config_values(file_values, source_file),
        **_script_config_values(file_values, source_file),
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
        raw = json.loads(path.read_text(encoding="utf-8-sig"))  # 容忍手改文件带 BOM（见 `_read_file_config()` 注释）
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
      以及 `status_refresh_ms` / `transcript_mode` / `permission`，其它键报 `ConfigError`（绝不写文件）；
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
        # 追加键（2026-09-22）：过程内容呈现模式，仅 normal / compact
        if name == "transcript_mode" and value not in (None, ""):
            current[name] = _coerce_transcript_mode(value, origin=str(path))
        # 追加键（2026-09-22）：审批档位（按 agent 配，`{agent_id: 档位名}`）
        if name == PERMISSION_KEY and value is not None:
            current[name] = _coerce_permission(value, origin=str(path))
        # 追加键（2026-09-23）：联网（N 线，§6.28）—— 正整数（条数 / 字节）与秒数（两侧超时）；
        # `search_base_url` 走上面的 `_TEXT_KEYS`（trim 后原样存，空串 = 回落自动推导）。
        if name in _WEB_POSITIVE_KEYS and value not in (None, ""):
            current[name] = _coerce_positive_int(value, origin=str(path), what=name)
        if name in _WEB_TIMEOUT_KEYS and value not in (None, ""):
            current[name] = _coerce_timeout(value, origin=f"{path} 的 {name}")
        # 追加键（2026-09-24）：脚本工作区（`script_interpreter` 走上面的 `_TEXT_KEYS`；
        # `script_use_bundled` 只做真值化；`script_timeout_s` 与其它秒数键同一套校验）。
        if name in _SCRIPT_BOOL_KEYS and value is not None:
            current[name] = bool(value)
        if name in _SCRIPT_TIMEOUT_KEYS and value not in (None, ""):
            current[name] = _coerce_timeout(value, origin=f"{path} 的 {name}")

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


# ── 过程内容呈现模式（2026-09-22；桌面端 UI 旋钮）────────────────────────────────
# **与 `enabled` / `status_refresh_ms` 同类**：它是 UI 旋钮、不是模型调用参数，故不进
# `AgentConfig`、也不参与 `load_config()` 的逐字段回退；由 `transcript_mode()` / `save_config()`
# 读写同一份 JSON。取值只允许 `normal`（过程内容常显）/ `compact`（回合结束后折叠为摘要行）。
# 本段整体追加在文件末尾 ⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
#: 过程内容呈现模式的 JSON 键。
_TRANSCRIPT_MODE_KEY = "transcript_mode"
#: 缺省 / 非法值一律回落此值（对齐上游 Turn Process Folding 的默认折叠）。
DEFAULT_TRANSCRIPT_MODE = "compact"
#: 允许的取值（写侧**严格**拒绝其它值，不落盘）。
_TRANSCRIPT_MODES = ("normal", "compact")


def transcript_mode(env: Mapping[str, str] | None = None) -> str:
    """过程内容呈现模式；缺省 / 非法值一律回退 `DEFAULT_TRANSCRIPT_MODE`。

    宽松口径与 `is_enabled()` / `status_refresh_ms()` 一致（手改坏值不该让配置视图 RPC 失败）；
    **严格校验在写侧**（`save_config` 走 `_coerce_transcript_mode`）。
    """
    raw = read_raw_config(env).get(_TRANSCRIPT_MODE_KEY)
    value = str(raw).strip().lower() if raw is not None else ""
    return value if value in _TRANSCRIPT_MODES else DEFAULT_TRANSCRIPT_MODE


def _coerce_transcript_mode(value: Any, origin: str) -> str:
    """写侧校验：只接受 `normal` / `compact`（大小写与首尾空白归一），其它值报 `ConfigError`。"""
    text = str(value).strip().lower()
    if text not in _TRANSCRIPT_MODES:
        raise ConfigError(f"{origin} 的 {_TRANSCRIPT_MODE_KEY} 只允许 normal / compact，收到 {value!r}")
    return text


# ── 2026-09-22 追加：审批档位段（`config/agent.json: permission`）────────────────────────
# 本块是**末尾追加** ⇒ 上方既有行号锚点零漂移。段值形状 `{agent_id: 档位名}`（人 2026-09-22
# 口径：「档位配置跟随 agent，后续会有多种 agent 的设计」）——当前只有主 agent（`main`）。
# **档位名的封闭词表不在本层**：那是 agent 语义（`services/agent/permission_presets.py`），
# 写侧只做形状校验，免得配置层反向依赖 agent 包（`permission_presets` 已正向依赖本模块）。

#: 审批档位段的键名；与 `_JSON_KEYS` 里的同名字面量是同一个键（该行在 `PERMISSION_KEY`
#: 定义之前求值，故那边只能写字面量）。
PERMISSION_KEY = "permission"


def permission_presets_map(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """读审批档位段（`{agent_id: 档位名}`）；缺省 / 形状不对一律回空表（宽松口径）。

    **严格校验在写侧**（`_coerce_permission`）；档位名是否合法由 `permission_presets` 模块的
    `default_preset()` 判定（未知名回落默认档）。
    """
    raw = read_raw_config(env).get(PERMISSION_KEY)
    if not isinstance(raw, Mapping):
        return {}
    return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(k).strip()}


def _coerce_permission(value: Any, origin: str) -> dict[str, str]:
    """写侧校验：`{agent_id: 档位名}`（键值都归一为字符串）；非映射报 `ConfigError`。

    空值键/空值档位一律丢弃（等价于"不配这一项"）；档位名的合法词表由调用方（UI RPC 层）
    先行校验，本层不认识 agent 语义。
    """
    if not isinstance(value, Mapping):
        raise ConfigError(f"{origin} 的 {PERMISSION_KEY} 必须是 {{agent: 档位名}} 的键值对象")
    out: dict[str, str] = {}
    for agent, name in value.items():
        key = str(agent or "").strip()
        text = str(name or "").strip()
        if key and text:
            out[key] = text
    return out


# ── 联网（N 线，2026-09-23；§6.28）：读侧取值 + 正整数校验 ─────────────────────────
# 整段**追加在文件末尾** ⇒ 上方所有 `<文件>:<行号>` 锚点零漂移（`load_config()` 里只**展开一行**
# `**_web_config_values(...)`，`save_config()` 的键分支追加在既有分支链**末位**）。
# 口径：①空串 / 缺省 = **默认值**（与 `timeout_s` 的 "空值不修改" 写侧语义配套）；②键**在文件里但
# 非法** ⇒ 报 `ConfigError`（与 `timeout_s` 同口径：坏值不静默吞掉）；③`search_base_url` 是文本，
# 不做更多校验 —— 它是不是能用的 Anthropic 面由 `services/agent/web.py::anthropic_base_url` 判定。


def _coerce_positive_int(value: Any, origin: str, what: str) -> int:
    """严格正整数（读写共用，口径同 `_coerce_status_refresh_ms`：先 `float` 再 `int`）。"""
    try:
        number = int(float(value))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{origin} 的 {what} 必须是整数，收到 {value!r}") from exc
    if number <= 0:
        raise ConfigError(f"{origin} 的 {what} 必须为正整数，收到 {number!r}")
    return number


def _web_config_values(file_values: Mapping[str, Any], source: str) -> dict[str, Any]:
    """从本地 JSON 取联网七键（缺省 ⇒ 默认值；非法 ⇒ `ConfigError`）；供 `load_config()` 展开。"""

    def present(key: str) -> Any:
        raw = file_values.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        return raw

    base_url = present("search_base_url")
    count = present("search_max_results")
    size = present("fetch_max_bytes")
    timeout = present("search_timeout_s")
    fetch_timeout = present("fetch_timeout_s")
    allow = file_values.get("fetch_allow_domains")
    deny = file_values.get("fetch_deny_domains")
    return {
        "search_base_url": "" if base_url is None else str(base_url).strip(),
        "search_max_results": DEFAULT_SEARCH_MAX_RESULTS
        if count is None
        else _coerce_positive_int(count, source, "search_max_results"),
        "fetch_max_bytes": DEFAULT_FETCH_MAX_BYTES
        if size is None
        else _coerce_positive_int(size, source, "fetch_max_bytes"),
        "search_timeout_s": DEFAULT_SEARCH_TIMEOUT_S
        if timeout is None
        else _coerce_timeout(timeout, origin=f"{source} 的 search_timeout_s"),
        "fetch_timeout_s": DEFAULT_FETCH_TIMEOUT_S
        if fetch_timeout is None
        else _coerce_timeout(fetch_timeout, origin=f"{source} 的 fetch_timeout_s"),
        # 域名名单两键：**空串是合法值**（= 不限），故只做 trim、不做"缺省回落"式的丢弃
        "fetch_allow_domains": "" if allow is None else str(allow).strip(),
        "fetch_deny_domains": "" if deny is None else str(deny).strip(),
    }


def _script_config_values(file_values: Mapping[str, Any], source: str) -> dict[str, Any]:
    """从本地 JSON 取脚本工作区三键（缺省 ⇒ 默认值；非法 ⇒ `ConfigError`）；供 `load_config()` 展开。

    口径：`script_interpreter` 空串是**合法值**（= 依次回落"发布包内置 → 系统"）；`script_use_bundled`
    只做真值化（JSON 里写 `false` 即关掉内置解释器）；`script_timeout_s` 与其它秒数键同一套校验。
    """
    raw_path = file_values.get("script_interpreter")
    raw_bundled = file_values.get("script_use_bundled")
    raw_timeout = file_values.get("script_timeout_s")
    return {
        "script_interpreter": "" if raw_path is None else str(raw_path).strip(),
        "script_use_bundled": True if raw_bundled is None else bool(raw_bundled),
        "script_timeout_s": DEFAULT_SCRIPT_TIMEOUT_S
        if raw_timeout is None or (isinstance(raw_timeout, str) and not raw_timeout.strip())
        else _coerce_timeout(raw_timeout, origin=f"{source} 的 script_timeout_s"),
    }

