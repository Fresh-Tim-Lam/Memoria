"""contain 语义区分的机检钉子（task-287 方案 A）。

人（2026-11-02）：「文本上的 contain 不一定真实具有 contain 的语义，所以我觉得有必要做一些
区分，别让程序自动一视同仁处理为 contain 边。」

`derive_contain_edges()` 只按知识点**区间几何包含**生成 `type="contain"`（`derived_by=system_range`），
不代表作者断言了"整体-部分"语义。产品侧不能改冻结的 3 类类型空间，所以方案 A 的做法是：
面向人的文案一律写"结构包含候选、语义未验证"，并用 `contain_semantics_guard.py` 钉住。

本文件把该守卫接进 pytest（CI 会跑），并验证守卫自己的红路径（不是永绿脚本）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "agent" / "contain_semantics_guard.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_GUARD), *args],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def test_contain_semantics_guard_is_green() -> None:
    """当前源码必须满足方案 A 的口径（i18n/badge/agent 提示词 + 14 个消费点仍在）。"""
    done = _run()
    assert done.returncode == 0, f"contain 语义机检报红：\n{done.stdout}\n{done.stderr}"
    assert "RESULT: PASS" in done.stdout


def test_contain_semantics_guard_has_red_paths() -> None:
    """证红：守卫必须能发现"文案被改回语义化 contain"这类回归（否则等于没钉）。"""
    done = _run("--selftest")
    assert done.returncode == 0, f"守卫的红路径自测失败：\n{done.stdout}\n{done.stderr}"
    assert "SELFTEST PASS" in done.stdout


def test_guard_json_reports_consumer_points() -> None:
    """机器可读输出里必须包含 14 个消费读取点（删点必须显式面对）。"""
    done = _run("--json")
    assert done.returncode == 0, done.stderr
    import json

    payload = json.loads(done.stdout)
    assert payload["schema"] == "contain-semantics-guard/v1"
    assert len(payload["consumers"]) == 14
    assert all(item["present"] for item in payload["consumers"])
