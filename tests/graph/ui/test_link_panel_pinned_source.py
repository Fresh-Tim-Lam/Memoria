# -*- coding: utf-8 -*-
"""链接小窗 pinned 持久化回归（task-391 rev14，源码断言）。

Lead 真机复现：`prefs.pinned=true` 被持久化并在新面板恢复 ⇒ 用户“没开 pin”却点画布不关闭，
UI 只有 13px 图标颜色差异，认知不一致。

新语义（本次修复）：
  1) 新打开的小窗默认 `pinned=false`，**不从 prefs 恢复 pinned**；
  2) 保存时**不再持久化 pinned**；
  3) 用户在本次面板内点 pin 的 toggle 仍保留；
  4) 未 pin 时点图谱/画布必须关闭（outside 逻辑保持）。

本文件是快速源码断言（不依赖浏览器）；真机行为见 `test_link_panel_pin.py`。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APP_JS = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "js" / "app.js"


def _read() -> str:
    assert APP_JS.is_file(), f"缺少 app.js：{APP_JS}"
    return APP_JS.read_text(encoding="utf-8", errors="replace")


def _fn_body(src: str, header: str) -> str:
    """从 `header` 起到下一个顶层 `  }` 结束（app.js 同缩进风格）。"""
    i = src.index(header)
    j = src.index("\n  }\n", i)
    return src[i:j]


def test_new_link_panel_never_restores_pinned_from_prefs() -> None:
    src = _read()
    read_fn = _fn_body(src, "async function _linkPanelPrefsRead()")
    assert "raw.pinned" not in read_fn, "prefs 读取仍恢复 pinned（回归）"
    assert "pinned: false" in read_fn, "prefs 读取必须强制 pinned=false"
    assert "prefs.pinned" not in src, "面板创建/其它处仍在消费 prefs.pinned（回归）"
    create_fn = _fn_body(src, "async function showLinkPanel(")
    assert re.search(r"pinned:\s*false", create_fn), "新面板构造必须显式 pinned=false"


def test_link_panel_persist_does_not_store_pinned() -> None:
    src = _read()
    persist_fn = _fn_body(src, "function _linkPanelPersist(patch)")
    assert "pinned: !!pop.pinned" not in persist_fn, "持久化 base 仍带 pinned（回归）"
    assert "next.pinned = false" in persist_fn, "持久化必须显式清掉 pinned（浅合并会保留历史 true）"
    assert "pinned: !!pop.pinned" not in src, "其它持久化路径仍写 pinned（回归）"


def test_unpinned_panel_closes_on_outside_and_pin_toggle_kept() -> None:
    src = _read()
    outside_fn = _fn_body(src, "function _linkPanelOutside(e)")
    assert "pop.pinned" in outside_fn and "closeLinkPanel" in outside_fn, "outside 关闭逻辑缺失"
    toggle_fn = _fn_body(src, "function _linkPanelTogglePin(pop)")
    assert "pop.pinned = !pop.pinned" in toggle_fn, "面板内 pin toggle 被误删"
    assert "_linkPanelUpdatePin(pop)" in toggle_fn, "pin 图标状态未更新"
