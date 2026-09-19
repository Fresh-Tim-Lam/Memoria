"""模型服务商**账户余额**查询（可选能力：只读、fail-open、绝不出网偷跑）。

设计口径：

1. **只在「出网」开启时可用**（与 `config.is_enabled()` 同源）。关闭时直接返回
   `status="disabled"`，**不发起任何请求** —— 与知识库工具面的"默认离线"红线一致。
2. **供应商差异靠 `base_url` 主机名判定**，不做探测、不猜路径：目前支持 DeepSeek
   （`/user/balance`）与 Moonshot（`/v1/users/me/balance`）；其余端点（含 OpenAI，其官方
   没有余额端点）返回 `status="unsupported"`。
3. **任何异常都不抛给界面**：一律收敛成 `status="error"|"unsupported"|"disabled"`，并把
   显示串置为 `—`。
4. **显示串由本模块产出**（返回里的 `text`），前端只负责贴 —— 这样不必为"余额"新增 i18n
   键（数字与货币符号本身就是通用形态）。
5. 只用标准库（`urllib`）、不新增依赖；不缓存（缓存与刷新节流交给调用方，避免两处各自记忆）。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from memoria.services.agent.llm.config import AgentConfig, is_enabled, load_config

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_BALANCE_TIMEOUT_S",
    "UNKNOWN_TEXT",
    "balance_url",
    "fetch_balance",
    "format_amount",
    "parse_payload",
    "provider_of",
]

#: 未知/不可用时的显示串（前端直接贴，不再包一层文案）。
UNKNOWN_TEXT = "—"
#: 余额请求超时：比模型调用短得多（这是"顺手看一眼"的能力，不该拖住界面）。
DEFAULT_BALANCE_TIMEOUT_S = 6.0

#: 主机名子串 → 余额端点路径。
BALANCE_PATHS: dict[str, str] = {
    "deepseek": "/user/balance",
    "moonshot": "/v1/users/me/balance",
}
#: 币种 → 符号（取不到就退回 `CODE ` 前缀）。
CURRENCY_SYMBOLS: dict[str, str] = {
    "CNY": "¥",
    "RMB": "¥",
    "USD": "$",
    "EUR": "€",
    "JPY": "¥",
    "HKD": "HK$",
}


def provider_of(base_url: str, *, known: dict[str, str] | None = None) -> str:
    """从 `base_url` 的主机名判定服务商标识；认不出返回空串。"""
    table = BALANCE_PATHS if known is None else known
    host = (urllib.parse.urlsplit(str(base_url or "")).hostname or "").lower()
    for name in table:
        if name in host:
            return name
    return ""


def balance_url(base_url: str, *, known: dict[str, str] | None = None) -> str | None:
    """拼出余额端点 URL；服务商不受支持或 `base_url` 不完整时返回 `None`。"""
    table = BALANCE_PATHS if known is None else known
    name = provider_of(base_url, known=table)
    if not name:
        return None
    parts = urllib.parse.urlsplit(str(base_url or ""))
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}{table[name]}"


def format_amount(amount: Any, currency: Any) -> str:
    """`110.0 + "CNY"` → `"¥110.00"`；数字解析失败则原样拼接（不猜）。"""
    code = str(currency or "").strip().upper()
    prefix = CURRENCY_SYMBOLS.get(code) or (f"{code} " if code else "")
    try:
        return f"{prefix}{float(amount):,.2f}"
    except (TypeError, ValueError):
        text = str(amount if amount is not None else "").strip()
        return f"{prefix}{text}" if text else UNKNOWN_TEXT


def parse_payload(payload: Any, provider: str) -> tuple[str, str, float | None]:
    """解析两家服务的余额响应 → `(显示串, 币种, 可用余额)`；形状不认识时回落 `—`。"""
    if not isinstance(payload, dict):
        return UNKNOWN_TEXT, "", None
    if provider == "deepseek":
        infos = payload.get("balance_infos")
        info = infos[0] if isinstance(infos, list) and infos and isinstance(infos[0], dict) else {}
        if not info:
            return UNKNOWN_TEXT, "", None
        currency = str(info.get("currency") or "CNY")
        raw = info.get("total_balance")
        try:
            total = float(raw)
        except (TypeError, ValueError):
            total = None
        return format_amount(raw, currency), currency, total
    if provider == "moonshot":
        data = payload.get("data")
        data = data if isinstance(data, dict) else {}
        raw = data.get("available_balance")
        if raw is None:
            return UNKNOWN_TEXT, "", None
        try:
            total = float(raw)
        except (TypeError, ValueError):
            total = None
        return format_amount(raw, "CNY"), "CNY", total
    return UNKNOWN_TEXT, "", None


def fetch_balance(
    config: AgentConfig | None = None,
    *,
    timeout_s: float = DEFAULT_BALANCE_TIMEOUT_S,
    opener: Callable[[urllib.request.Request, float], Any] | None = None,
) -> dict:
    """查询余额并返回面板可直接消费的字典。

    返回形状（`status` 是唯一判据，`text` 永远可贴）：

    | status | 含义 | `text` |
    |---|---|---|
    | `ok` | 查到了 | `¥110.00` |
    | `disabled` | 出网关闭 | `—` |
    | `no_key` | 未配置密钥 | `—` |
    | `unsupported` | 该端点没有余额接口（含 OpenAI） | `—` |
    | `error` | 网络/解析失败（**不抛异常**） | `—` |

    `opener` 仅用于测试注入（默认 `urllib.request.urlopen`）。
    """
    if not is_enabled():
        return {"status": "disabled", "text": UNKNOWN_TEXT}
    cfg = config if config is not None else load_config()
    url = balance_url(cfg.base_url)
    if url is None:
        return {"status": "unsupported", "text": UNKNOWN_TEXT, "base_url": cfg.base_url}
    if not cfg.api_key:
        return {"status": "no_key", "text": UNKNOWN_TEXT}

    request = urllib.request.Request(  # noqa: S310 —— 只访问由 base_url 派生的 https 端点
        url,
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Accept": "application/json",
            "User-Agent": "Memoria/agent-balance",
        },
        method="GET",
    )
    do_open = opener if opener is not None else urllib.request.urlopen
    try:
        # ⚠️ 必须用关键字传 timeout：`urlopen` 的第 2 个**位置**参数是 `data`（请求体），
        # 传成位置参数会把数字当 body ⇒ `TypeError: message_body should be a bytes-like object`。
        with do_open(request, timeout=timeout_s) as response:  # type: ignore[union-attr]
            payload = json.loads(response.read().decode("utf-8", "replace") or "null")
    except urllib.error.HTTPError as e:  # 401/403 = 密钥或权限问题，值得区分
        return {"status": "error", "text": UNKNOWN_TEXT, "code": f"http_{e.code}", "message": str(e)}
    except (urllib.error.URLError, OSError, ValueError, TypeError, json.JSONDecodeError) as e:
        logger.debug("[agent-balance] 查询失败：%r", e)
        return {"status": "error", "text": UNKNOWN_TEXT, "code": "network_error", "message": str(e)}

    text, currency, total = parse_payload(payload, provider_of(cfg.base_url))
    out: dict[str, Any] = {"status": "ok", "text": text, "currency": currency}
    if total is not None:
        out["total"] = total
    return out
