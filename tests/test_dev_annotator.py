"""dev-annotator 回归：outline 必须挂在 shadow root 内。

历史 bug（2026-11-13）：`.outline` 的样式只定义在 shadow `<style>` 里，却把
outline append 到 `document.body` ⇒ 样式不生效，hover 时变成普通块级元素，
每次点选都让页面高度 +30px、内容下移，严重时整窗黑屏。
"""

from __future__ import annotations

from pathlib import Path

ANNOTATOR = Path(__file__).resolve().parents[1] / "tools" / "dev-annotator" / "annotator.js"


def test_outline_lives_in_shadow_root_not_body() -> None:
    src = ANNOTATOR.read_text(encoding="utf-8")
    assert "root.appendChild(outline)" in src
    assert "document.body || document.documentElement).appendChild(outline)" not in src


def test_ensure_mounted_restores_outline_into_shadow_root() -> None:
    src = ANNOTATOR.read_text(encoding="utf-8")
    assert "if (!outline.isConnected) root.appendChild(outline);" in src
