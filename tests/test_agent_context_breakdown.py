"""会话上下文三段拆分（system / tools / messages）的只读回归。

口径：字符是真实预算；token 是 `chars/4` **估算**（响应显式标记
`estimate.tokens_are_estimated`），绝不冒充当 provider 计费值。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memoria.services.agent.context_breakdown import (
    CHARS_PER_TOKEN,
    build_context_breakdown,
    estimate_tokens,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_KB = ROOT / "docs" / "example" / "AAA_Vocab"


def test_estimate_tokens_is_ceiling_and_zero_safe() -> None:
    assert estimate_tokens(0) == 0
    assert estimate_tokens(1) == 1
    assert estimate_tokens(4) == 1
    assert estimate_tokens(5) == 2
    assert CHARS_PER_TOKEN == 4


def test_breakdown_returns_three_segments_and_budget() -> None:
    result = build_context_breakdown(str(EXAMPLE_KB), "no-such-session", "deepseek-chat")
    assert result["status"] == "ok"
    segments = result["segments"]
    assert set(segments) == {"system", "tools", "messages"}
    for segment in segments.values():
        assert segment["chars"] >= 0
        assert segment["tokens"] == estimate_tokens(segment["chars"])
    total = sum(segment["chars"] for segment in segments.values())
    assert result["total"]["chars"] == total
    assert result["total"]["tokens"] == estimate_tokens(total)
    assert result["estimate"]["method"] == "chars/4"
    assert result["estimate"]["tokens_are_estimated"] is True
    assert result["budget"] is not None
    assert result["budget"]["max_chars"] > 0


def test_ui_api_exposes_read_only_breakdown_rpc() -> None:
    from memoria.presentation.api.ui import UIAPI

    assert hasattr(UIAPI, "agent_context_breakdown")
