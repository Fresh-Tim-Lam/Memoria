"""task-198 契约：图片编辑滚动 / 小窗 mermaid / 关闭小窗不再滚动（静态钉住）。"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
APP_JS = APP / "js" / "app.js"
IMAGE_JS = APP / "js" / "image-tools.js"
EDIT_JS = APP / "js" / "edit-handler.js"
ZH = APP / "i18n" / "zh-CN.js"
EN = APP / "i18n" / "en.js"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_b1_image_edit_uses_keep_scroll_entry() -> None:
    """B1：图片属性/名称写回 = 整篇重渲 ⇒ 必须走 keep-scroll 入口，不能直调 renderPreview。

    RED 证据（task-198 真机）：旧路径 previewTop 8301→0；改成 keep-scroll 后可视锚点行不变。
    """
    src = _read(IMAGE_JS)
    fn = src.split("async function applyImageEditLines(lines)")[1].split("/** 预览区图片右键菜单")[0]
    assert "renderPreviewKeepScroll" in fn, "图片编辑写回必须复用 keep-scroll 重渲入口"
    assert "if (typeof A2.renderPreviewKeepScroll" in fn, "只有能力缺失时才允许 fallback 到 renderPreview"
    assert "editorPane.scrollTop = srcScrollTop" in fn, "分栏源码区也要恢复（编辑器重建会归零）"
    assert "renderPreviewKeepScroll: _renderPreviewKeepScroll" in _read(APP_JS)


def test_b1_block_edit_focus_prevents_scroll() -> None:
    """重进图片编辑模式的 focus 不能把块滚进视口（会叠加在锚点恢复上）。"""
    src = _read(EDIT_JS)
    assert "blockEl.focus({ preventScroll: true })" in src


def test_b2_link_panel_reuses_main_mermaid_post_processor() -> None:
    """B2：小窗预览必须复用主预览的 renderMermaidBlocks，而不是自己 mermaid.init。"""
    src = _read(APP_JS)
    fn = src.split("async function _linkPanelRenderPreview(")[1].split("\n  }")[0]
    assert "MP.renderMermaidBlocks(docEl)" in fn
    assert "await MP.renderMermaidBlocks" in fn
    assert "mermaid.init" not in fn, "重复初始化 mermaid 有已知风险"
    # 调用点必须 await（否则 mermaid 异步替换在小窗关闭/切换后仍继续）
    assert "await _linkPanelRenderPreview(" in src


def test_b3_close_path_has_no_scrolling_and_focus_is_prevent_scroll() -> None:
    """B3：关闭只关闭；滚动只由定位按钮触发（不是 close 里的 if）。"""
    src = _read(APP_JS)
    close_fn = src.split("function closeLinkPanel(opts = {})")[1].split("\n  }")[0]
    assert "scrollIntoView" not in close_fn
    assert "scrollTop" not in close_fn
    assert "scrollTo" not in close_fn
    assert "_focusNoScroll(pop.anchorEl)" in close_fn
    assert "_focusNoScroll(pop.opener)" in close_fn
    assert "focus({ preventScroll: true })" in src
    # 旧写法（裸 focus）不能出现在关闭路径
    assert "pop.anchorEl.focus()" not in close_fn


def test_b3_locate_button_exists_and_is_the_only_scroll_owner() -> None:
    src = _read(APP_JS)
    assert 'data-panel-locate' in src
    assert "_linkPanelLocateAnchor(pop)" in src
    locate_fn = src.split("function _linkPanelLocateAnchor(pop)")[1].split("\n  }")[0]
    assert "scrollIntoView" in locate_fn, "定位按钮必须真的滚动到入口"
    assert "closeLinkPanel" in locate_fn
    # 按钮的 i18n 键中英齐全
    for loc in (_read(ZH), _read(EN)):
        assert "locate:" in loc
        assert "locateTitle:" in loc


def test_b3_no_plain_focus_that_can_scroll_in_panel_lifecycle() -> None:
    """扫描 panel 生命周期附近：不允许裸 `.focus()` 重新引入隐式滚动。"""
    src = _read(APP_JS)
    for m in re.finditer(r"(anchorEl|opener)\.focus\(\)", src):
        raise AssertionError(f"panel 生命周期仍有裸 focus()：{m.group(0)}")
