"""C10：弹窗层级单源化。

真实复现（dev CDP，2026-11-13）：
  `#settings-modal` 的 computed z-index = 1000；
  `MemoriaApp.showTreeContextMenu()` 的 `.-context-menu` = 10050；
  菜单出现在弹窗之上，弹窗中心被菜单覆盖 ⇒ 弹窗不可点。

本测试钉住修复后的层级顺序与单源 token，防止再次把 raw z-index 写回。
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "memoria"
    / "ui"
    / "static"
    / "app"
    / "css"
    / "app.css"
)


def _text() -> str:
    return CSS.read_text(encoding="utf-8")


def _root_token(name: str) -> int:
    m = re.search(rf"--{re.escape(name)}:\s*(\d+)\s*;", _text())
    assert m, f"app.css 缺少层级 token --{name}"
    return int(m.group(1))


def test_c10_layer_token_order() -> None:
    """模态必须高于后台浮层；灯箱仍在最上。"""
    assert _root_token("z-search-panel") < _root_token("z-context-menu")
    assert _root_token("z-context-menu") < _root_token("z-flash")
    assert _root_token("z-flash") < _root_token("z-color-picker")
    assert _root_token("z-color-picker") < _root_token("z-modal")
    assert _root_token("z-modal") < _root_token("z-lightbox")
    assert _root_token("z-search-panel") == 9000, "既有搜索面板数值应保持不变（只改引用方式）"


def test_c10_overlays_use_tokens_not_raw_z_index() -> None:
    src = _text()
    expected = {
        ".-toolbar-search-panel": "--z-search-panel",
        "#-flash-host": "--z-flash",
        ".-context-menu": "--z-context-menu",
        ".-color-picker-mask": "--z-color-picker",
        ".-modal": "--z-modal",
        ".-lightbox-overlay": "--z-lightbox",
    }
    for selector, token in expected.items():
        start = src.index(selector + " {")
        body = src[start : src.index("}", start)]
        assert f"z-index: var({token});" in body, f"{selector} 必须使用 {token}"
        assert not re.search(r"z-index:\s*\d+;", body), f"{selector} 不得写回 raw z-index"


def test_c10_modal_above_known_background_overlays() -> None:
    modal = _root_token("z-modal")
    for name in ("z-search-panel", "z-context-menu", "z-flash", "z-color-picker"):
        assert modal > _root_token(name), f"模态必须高于 --{name}"
