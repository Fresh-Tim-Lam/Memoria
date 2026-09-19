"""模型**计价表**与成本估算（人民币 / 每 100 万 tokens）。

口径（**唯一事实源，调价时只改这里**）：

1. 价目来源：DeepSeek 官方「模型 & 价格」页 —— `PRICE_TABLE_URL`（本次核对日期
   见 `PRICE_TABLE_UPDATED`）。官方原话：「产品价格可能发生变动，DeepSeek 保留修改
   价格的权利」⇒ 本表是**有日期的快照**，不是"永远正确"，界面必须把日期一起显示。
2. **高峰 / 空闲双档**：高峰 = **北京时间** 周一至周五 `09:00–12:00` 与 `14:00–18:00`，
   其余时间（含周末全天）为空闲；**空闲价 = 高峰价的一半**。因此累计成本**必须逐轮
   按其时间戳定档再相加**，不能先加 token 再乘一个价。
3. 计费项三项：**输入·缓存命中** / **输入·缓存未命中** / **输出**，各自单价。
   币种 CNY（与 `balance.py` 查到的余额同币种，可直接比对）。
4. **只认表内模型**：表里没有（含别名归一后仍没有）一律返回 `None`/`priced=False`，
   **绝不猜、也不按 0 计**；缓存明细未知的轮次同样不算（避免把"未知"当"全未命中"）。
5. 别名：官方脚注说明旧模型名仍可调用但已下线、**按 Flash 价计费** ⇒ 见 `MODEL_ALIASES`。
6. 只用标准库；**不联网、不读配置、不写盘**（纯函数，可离线完整验证）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

__all__ = [
    "CN_OFFSET_HOURS",
    "CURRENCY",
    "MODEL_ALIASES",
    "PEAK_WINDOWS",
    "PRICES",
    "PRICE_TABLE_UPDATED",
    "PRICE_TABLE_URL",
    "estimate",
    "is_peak",
    "normalize_model",
    "turn_cost",
]

#: 币种（与余额查询同币种）。
CURRENCY = "CNY"
#: 本表核对日期（官方调价后**追加**新表并更新此日期，界面会把日期显示出来）。
PRICE_TABLE_UPDATED = "2026-09-19"
#: 价目来源。
PRICE_TABLE_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
#: 北京时间相对 UTC 的固定偏移（无夏令时，故用定值偏移，避免依赖 tzdata）。
CN_OFFSET_HOURS = 8

#: 高峰时段（北京时间，左闭右开）：周一至周五 09:00–12:00 与 14:00–18:00。
PEAK_WINDOWS: tuple[tuple[int, int, int, int], ...] = ((9, 0, 12, 0), (14, 0, 18, 0))

#: 每 1M tokens 单价（元）：`{模型: {"hit"|"miss"|"output": (空闲价, 高峰价)}}`。
PRICES: dict[str, dict[str, tuple[float, float]]] = {
    "deepseek-flash": {"hit": (0.02, 0.04), "miss": (1.0, 2.0), "output": (4.0, 8.0)},
    "deepseek-v4-pro": {"hit": (0.15, 0.30), "miss": (4.5, 9.0), "output": (13.5, 27.0)},
}

#: 旧模型名 → 现价目表的键（官方脚注：旧名仍可调用，但由新版模型提供服务、按 Flash 价计费）。
MODEL_ALIASES: dict[str, str] = {
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-v4-flash-vision-exp": "deepseek-flash",
}

_CN_TZ = timezone(timedelta(hours=CN_OFFSET_HOURS))
_ITEMS = ("hit", "miss", "output")


def _as_ms(value: Any) -> int | None:
    """宽松取整数毫秒；`bool` 不算数字（`True` 会被当成 1）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value:  # 排除 NaN
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
    return None


def normalize_model(name: Any) -> str:
    """模型名 → 价目表键；表里没有（含别名归一后仍没有）返回空串。"""
    key = str(name or "").strip().lower()
    if not key:
        return ""
    key = MODEL_ALIASES.get(key, key)
    return key if key in PRICES else ""


def is_peak(moment_ms: Any) -> bool:
    """epoch 毫秒 → 是否落在高峰时段（北京时间 周一至周五 `PEAK_WINDOWS` 内）。

    时间戳无法解析时返回 `False`（空闲档）——**调用方应先判"有没有时间戳"**：
    `turn_cost()` 对无时间戳的轮次直接判为不可计价，而不是按空闲价糊过去。
    """
    ms = _as_ms(moment_ms)
    if ms is None:
        return False
    local = datetime.fromtimestamp(ms / 1000.0, tz=_CN_TZ)
    if local.weekday() >= 5:  # 5=周六, 6=周日
        return False
    minutes = local.hour * 60 + local.minute
    for start_h, start_m, end_h, end_m in PEAK_WINDOWS:
        if start_h * 60 + start_m <= minutes < end_h * 60 + end_m:
            return True
    return False


def _turn_tokens(row: Mapping[str, Any]) -> tuple[int, int, int] | None:
    """一轮的（命中, 未命中, 输出）token 数；缓存明细不可知（且推不出）时返回 `None`。"""
    prompt = _as_ms(row.get("prompt")) or 0
    hit = _as_ms(row.get("cache_hit"))
    miss = _as_ms(row.get("cache_miss"))
    if miss is None and hit is not None and prompt >= hit:
        miss = prompt - hit  # 端点只给命中量时的补法（与 usage_report 同口径）
    if hit is None or miss is None:
        return None
    return hit, miss, (_as_ms(row.get("completion")) or 0)


def turn_cost(row: Mapping[str, Any], model: Any) -> dict[str, Any] | None:
    """单轮成本明细；不可计价（模型不在表内 / 无时间戳 / 缓存明细未知）返回 `None`。"""
    key = normalize_model(model)
    prices = PRICES.get(key)
    if prices is None or not isinstance(row, Mapping):
        return None
    peak = is_peak(row.get("time"))
    if _as_ms(row.get("time")) is None:
        return None
    tokens = _turn_tokens(row)
    if tokens is None:
        return None
    idx = 1 if peak else 0
    hit, miss, output = tokens
    unit = {item: prices[item][idx] for item in _ITEMS}
    return {
        "peak": peak,
        "hit_tokens": hit,
        "hit_cost": hit * unit["hit"] / 1_000_000,
        "miss_tokens": miss,
        "miss_cost": miss * unit["miss"] / 1_000_000,
        "output_tokens": output,
        "output_cost": output * unit["output"] / 1_000_000,
    }


def estimate(rows: Iterable[Any], model: Any) -> dict[str, Any]:
    """逐轮计价后求和（**逐轮**是为了让高峰/空闲各按其时间档计费）。

    返回 `{currency, model, price_table, price_table_url, priced, turns, priced_turns,
    peak_turns, hit_tokens, hit_cost, miss_tokens, miss_cost, output_tokens, output_cost,
    total_cost}`；金额保留 6 位小数避开浮点噪声。`priced=False` 表示**没有一个可计价
    轮次**（模型不在表内，或全部轮次缺时间戳/缓存明细）—— 界面据此显示 `—` 而不是 `¥0`。
    """
    key = normalize_model(model)
    agg: dict[str, Any] = {
        "currency": CURRENCY,
        "model": key,
        "price_table": PRICE_TABLE_UPDATED,
        "price_table_url": PRICE_TABLE_URL,
        "priced": False,
        "turns": 0,
        "priced_turns": 0,
        "peak_turns": 0,
        "hit_tokens": 0,
        "hit_cost": 0.0,
        "miss_tokens": 0,
        "miss_cost": 0.0,
        "output_tokens": 0,
        "output_cost": 0.0,
        "total_cost": 0.0,
    }
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        agg["turns"] += 1
        one = turn_cost(row, key)
        if one is None:
            continue
        agg["priced_turns"] += 1
        if one["peak"]:
            agg["peak_turns"] += 1
        for item in _ITEMS:
            agg[item + "_tokens"] += one[item + "_tokens"]
            agg[item + "_cost"] += one[item + "_cost"]
    agg["total_cost"] = agg["hit_cost"] + agg["miss_cost"] + agg["output_cost"]
    agg["unpriced_turns"] = agg["turns"] - agg["priced_turns"]
    agg["priced"] = bool(key) and agg["priced_turns"] > 0
    for name in ("hit_cost", "miss_cost", "output_cost", "total_cost"):
        agg[name] = round(agg[name], 6)
    return agg
