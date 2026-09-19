"""`services/agent/llm/balance.py` 的离线单测：不联网、不读真实密钥。

覆盖：
① 服务商判定与余额 URL 拼接（DeepSeek / Moonshot / 认不出的端点）；
② 两家响应形状的解析（含形状不认识时回落 `—`）；
③ 金额格式化（含非数字、未知币种）；
④ 四条短路路径（**出网关** / 无密钥 / 不支持 / 网络异常）—— 一律不抛异常、`text` 恒可贴；
⑤ 出网关闭时**不得**发起任何请求（注入的 opener 必须一次都没被调用）。
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from memoria.services.agent.llm.balance import (
    UNKNOWN_TEXT,
    balance_url,
    fetch_balance,
    format_amount,
    parse_payload,
    provider_of,
)
from memoria.services.agent.llm.config import AgentConfig


class FakeResponse:
    """最小可用的 `urlopen` 返回对象（上下文管理器 + `read()`）。"""

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _cfg(base_url: str = "https://api.deepseek.com", key: str = "sk-test") -> AgentConfig:
    return AgentConfig(base_url=base_url, api_key=key)


# —— ① 服务商判定与 URL ——


def test_provider_of_known_hosts() -> None:
    assert provider_of("https://api.deepseek.com") == "deepseek"
    assert provider_of("https://api.deepseek.com/v1") == "deepseek"
    assert provider_of("https://api.moonshot.cn/v1") == "moonshot"
    assert provider_of("https://api.openai.com/v1") == ""
    assert provider_of("") == ""


def test_balance_url_uses_origin_and_provider_path() -> None:
    assert balance_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/user/balance"
    assert balance_url("https://api.moonshot.cn/v1") == "https://api.moonshot.cn/v1/users/me/balance"
    # 认不出的端点 ⇒ None（调用方据此返回 unsupported）
    assert balance_url("https://api.openai.com/v1") is None
    # base_url 不完整 ⇒ 也是 None，而不是拼出半个 URL
    assert balance_url("no-scheme.example.com/v1") is None


# —— ② 响应解析 ——


def test_parse_deepseek_payload() -> None:
    text, currency, total = parse_payload(
        {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": "110.00"}]},
        "deepseek",
    )
    assert text == "¥110.00"
    assert currency == "CNY"
    assert total == pytest.approx(110.0)


def test_parse_moonshot_payload() -> None:
    text, currency, total = parse_payload({"code": 0, "data": {"available_balance": 12.5}}, "moonshot")
    assert text == "¥12.50"
    assert currency == "CNY"
    assert total == pytest.approx(12.5)


def test_parse_unknown_shapes_fall_back() -> None:
    # 空 balance_infos / 缺 data / 非字典 / 认不出的 provider ⇒ 一律 `—`，绝不抛
    assert parse_payload({"balance_infos": []}, "deepseek")[0] == UNKNOWN_TEXT
    assert parse_payload({"code": 0}, "moonshot")[0] == UNKNOWN_TEXT
    assert parse_payload("not-a-dict", "deepseek")[0] == UNKNOWN_TEXT
    assert parse_payload({"balance_infos": [{"total_balance": "1"}]}, "other")[0] == UNKNOWN_TEXT


# —— ③ 金额格式化 ——


def test_format_amount() -> None:
    assert format_amount("110.0", "CNY") == "¥110.00"
    assert format_amount(1234.5, "USD") == "$1,234.50"
    assert format_amount(1, "XXX") == "XXX 1.00"
    assert format_amount("unknown", "CNY") == "¥unknown"
    assert format_amount(None, "") == UNKNOWN_TEXT


# —— ④ 短路路径（都不该抛，text 都可贴） ——


def test_no_key_returns_no_key_without_request() -> None:
    called: list[object] = []

    def opener(request: object, timeout: float) -> object:
        called.append(request)
        raise AssertionError("无密钥时不应发起请求")

    out = fetch_balance(_cfg(key=""), opener=opener)
    assert out["status"] == "no_key"
    assert out["text"] == UNKNOWN_TEXT
    assert called == []


def test_unsupported_provider() -> None:
    out = fetch_balance(_cfg(base_url="https://api.openai.com/v1"))
    assert out["status"] == "unsupported"
    assert out["text"] == UNKNOWN_TEXT


def test_network_error_is_swallowed() -> None:
    def opener(request: object, timeout: float) -> object:
        raise urllib.error.URLError("boom")

    out = fetch_balance(_cfg(), opener=opener)
    assert out["status"] == "error"
    assert out["code"] == "network_error"
    assert out["text"] == UNKNOWN_TEXT


def test_http_error_is_classified() -> None:
    def opener(request: object, timeout: float) -> object:
        raise urllib.error.HTTPError("u", 401, "unauthorized", {}, None)  # type: ignore[arg-type]

    out = fetch_balance(_cfg(), opener=opener)
    assert out["status"] == "error"
    assert out["code"] == "http_401"


def test_ok_path_parses_payload() -> None:
    out = fetch_balance(
        _cfg(),
        opener=lambda request, timeout: FakeResponse(
            {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": "7.50"}]}
        ),
    )
    assert out["status"] == "ok"
    assert out["text"] == "¥7.50"
    assert out["total"] == pytest.approx(7.5)


# —— ⑤ 出网关：一次请求都不许发 ——


def test_disabled_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    import memoria.services.agent.llm.balance as balance

    monkeypatch.setattr(balance, "is_enabled", lambda: False)
    called: list[object] = []

    def opener(request: object, timeout: float) -> object:
        called.append(request)
        raise AssertionError("出网关闭时不应发起请求")

    out = balance.fetch_balance(_cfg(), opener=opener)
    assert out["status"] == "disabled"
    assert out["text"] == UNKNOWN_TEXT
    assert called == []
