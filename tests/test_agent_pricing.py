"""`services/agent/llm/pricing.py` 的离线单测：不联网、不读配置。

覆盖：
① 模型名归一（现名 / 官方脚注里的旧别名 / 未收录）；
② 高峰时段判定（北京时间周一至周五 09:00–12:00、14:00–18:00；**周末全天空闲**；
   边界左闭右开：12:00 与 18:00 不算高峰）；
③ 单轮计价（峰谷价差一倍、`cache_miss` 可由 `prompt - cache_hit` 补出）；
④ 不可计价的四类情形（模型未收录 / 缺时间戳 / 缺 cache 明细 / 非映射行）；
⑤ 累计 `estimate`：**逐轮**定档后求和（两轮跨峰谷 ≠ 一轮均价）、`priced=False` 的两条判据、
   金额 6 位小数取整；
⑥ 与 `usage_report.turn_from_event` 的接线：逐轮行必须带出 `time`（峰谷定价的输入）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from memoria.services.agent.llm.pricing import (
    PRICE_TABLE_UPDATED,
    estimate,
    is_peak,
    normalize_model,
    turn_cost,
)
from memoria.services.agent.usage_report import turn_from_event

CN = timezone(timedelta(hours=8))


def ms_of(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    """北京时间 → epoch 毫秒（测试内自造时间戳，不依赖当前时钟）。"""
    return int(datetime(year, month, day, hour, minute, tzinfo=CN).timestamp() * 1000)


# 2026-09-21 是周一，2026-09-19 是周六（用于峰谷与周末的反例）。
MON_PEAK = ms_of(2026, 9, 21, 10, 0)
MON_OFFPEAK = ms_of(2026, 9, 21, 20, 0)
SAT_NOON = ms_of(2026, 9, 19, 10, 0)


def row(**over: object) -> dict:
    """一条用量行（默认 1000 输入 / 200 输出 / 命中 400 / 未命中 600，落在高峰）。"""
    base = {
        "time": MON_PEAK,
        "prompt": 1000,
        "completion": 200,
        "cache_hit": 400,
        "cache_miss": 600,
    }
    base.update(over)
    return base


# ── ① 模型名归一 ──────────────────────────────────────────────────────────


def test_normalize_model_accepts_current_and_alias() -> None:
    assert normalize_model("deepseek-flash") == "deepseek-flash"
    assert normalize_model("DeepSeek-V4-Flash") == "deepseek-flash"  # 官方脚注：旧名按 Flash 计费
    assert normalize_model("  deepseek-v4-pro ") == "deepseek-v4-pro"


def test_normalize_model_rejects_unknown() -> None:
    assert normalize_model("gpt-6-astra") == ""
    assert normalize_model("") == ""
    assert normalize_model(None) == ""


# ── ② 高峰时段 ────────────────────────────────────────────────────────────


def test_peak_boundaries_are_left_closed_right_open() -> None:
    assert is_peak(ms_of(2026, 9, 21, 9, 0)) is True
    assert is_peak(ms_of(2026, 9, 21, 11, 59)) is True
    assert is_peak(ms_of(2026, 9, 21, 12, 0)) is False  # 午休
    assert is_peak(ms_of(2026, 9, 21, 13, 59)) is False
    assert is_peak(ms_of(2026, 9, 21, 14, 0)) is True
    assert is_peak(ms_of(2026, 9, 21, 17, 59)) is True
    assert is_peak(ms_of(2026, 9, 21, 18, 0)) is False
    assert is_peak(ms_of(2026, 9, 21, 8, 59)) is False


def test_weekend_is_always_off_peak() -> None:
    assert is_peak(SAT_NOON) is False          # 周六上午 10:00
    assert is_peak(ms_of(2026, 9, 20, 15, 0)) is False  # 周日下午


def test_peak_uses_beijing_time_not_local() -> None:
    # 同一条毫秒值：北京时间 10:00（高峰）= UTC 02:00（若误按 UTC 判会落到空闲）
    assert is_peak(MON_PEAK) is True
    assert is_peak(MON_OFFPEAK) is False


# ── ③ 单轮计价 ────────────────────────────────────────────────────────────


def test_turn_cost_peak_is_double_off_peak() -> None:
    peak = turn_cost(row(time=MON_PEAK), "deepseek-flash")
    off = turn_cost(row(time=MON_OFFPEAK), "deepseek-flash")
    assert peak is not None and off is not None
    assert peak["peak"] is True and off["peak"] is False
    assert peak["hit_cost"] == off["hit_cost"] * 2
    assert peak["miss_cost"] == off["miss_cost"] * 2
    assert peak["output_cost"] == off["output_cost"] * 2


def test_turn_cost_matches_hand_computed_flash_peak() -> None:
    """Flash 高峰价：命中 0.04 / 未命中 2 / 输出 8 元每 1M tokens。"""
    one = turn_cost(row(), "deepseek-flash")
    assert one is not None
    assert one["hit_cost"] == 400 * 0.04 / 1_000_000
    assert one["miss_cost"] == 600 * 2.0 / 1_000_000
    assert one["output_cost"] == 200 * 8.0 / 1_000_000


def test_turn_cost_derives_miss_from_prompt_minus_hit() -> None:
    one = turn_cost(row(cache_miss=None, cache_hit=250), "deepseek-flash")
    assert one is not None
    assert one["miss_tokens"] == 750


# ── ④ 不可计价 ────────────────────────────────────────────────────────────


def test_turn_cost_none_when_model_unknown() -> None:
    assert turn_cost(row(), "gpt-6-astra") is None
    assert turn_cost(row(), "") is None


def test_turn_cost_none_without_timestamp() -> None:
    assert turn_cost(row(time=None), "deepseek-flash") is None
    assert turn_cost(row(time="not-a-time"), "deepseek-flash") is None


def test_turn_cost_none_when_cache_detail_unknown() -> None:
    assert turn_cost(row(cache_hit=None, cache_miss=None), "deepseek-flash") is None
    # 只有命中量、且 prompt < hit（推不出未命中）⇒ 也不计价，绝不按 0 糊过去
    assert turn_cost(row(cache_hit=9999, cache_miss=None), "deepseek-flash") is None


# ── ⑤ 累计 ────────────────────────────────────────────────────────────────


def test_estimate_prices_each_turn_by_its_own_clock() -> None:
    """一轮高峰 + 一轮空闲 ≠ 两轮都按同一价 —— 逐轮定档是本模块的核心口径。"""
    rows = [row(time=MON_PEAK), row(time=MON_OFFPEAK)]
    agg = estimate(rows, "deepseek-flash")
    half = turn_cost(row(time=MON_OFFPEAK), "deepseek-flash")
    assert half is not None
    assert agg["turns"] == 2 and agg["priced_turns"] == 2 and agg["peak_turns"] == 1
    assert agg["hit_tokens"] == 800 and agg["miss_tokens"] == 1200 and agg["output_tokens"] == 400
    # 高峰那轮恰为空闲那轮的两倍 ⇒ 合计 = 3 × 空闲单轮
    assert agg["total_cost"] == round(half["hit_cost"] * 3 + half["miss_cost"] * 3 + half["output_cost"] * 3, 6)
    assert agg["priced"] is True
    assert agg["price_table"] == PRICE_TABLE_UPDATED


def test_estimate_counts_unpriced_turns_and_keeps_zero_semantics() -> None:
    # 非映射项**不算一轮**（不是用量行）；缺时间戳的那轮算轮次但不可计价
    rows = [row(), row(time=None), "not-a-mapping"]
    agg = estimate(rows, "deepseek-flash")
    assert agg["turns"] == 2 and agg["priced_turns"] == 1
    assert agg["unpriced_turns"] == 1


def test_estimate_not_priced_when_model_unknown_or_no_priced_turn() -> None:
    assert estimate([row()], "gpt-6-astra")["priced"] is False
    assert estimate([row(time=None)], "deepseek-flash")["priced"] is False
    empty = estimate([], "deepseek-flash")
    assert empty["priced"] is False and empty["total_cost"] == 0.0


def test_estimate_rounds_money_to_six_decimals() -> None:
    agg = estimate([row()], "deepseek-v4-pro")
    for name in ("hit_cost", "miss_cost", "output_cost", "total_cost"):
        assert round(agg[name], 6) == agg[name]


# ── ⑥ 与 usage_report 的接线 ──────────────────────────────────────────────


def test_turn_from_event_carries_time_for_peak_pricing() -> None:
    record = {
        "seq": 3,
        "time": MON_PEAK,
        "type": "loop/end",
        "data": {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    }
    assert turn_from_event(record, "s1")["time"] == MON_PEAK
    # 缺 `time` 的旧记录：行仍在，只是 `time=None` ⇒ 该轮不可计价（由 estimate 计为 unpriced）
    old = {"seq": 4, "type": "loop/end", "data": {"usage": {"prompt_tokens": 10}}}
    assert turn_from_event(old, "s1")["time"] is None
