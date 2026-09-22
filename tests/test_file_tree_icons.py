"""文件树图标两态（`已配置元数据` / `未配置`）**按颜色**区分 —— CSS 契约钉子。

**2026-09-22 追加**：同一个文件也钉住「缩进**折角**紧贴行首字形」这条几何口径（见文件末尾三例）。

人：「缺少元数据配置的 md 文档和已经配置的 md 文档的图标区分开（以前是另一个文档图标：
配置过的有颜色，没配置的没颜色、浅一点）」。

改前的实况（本文件把新口径钉住，同时也钉住"为什么改"）：两态只有**亮度**一个轴
（`.-tree-icon` 基础 `opacity: .85` → 无侧车 `.55`），**颜色两支都沿行的 `--text-primary`**
⇒ 同一字形同一颜色，扫一眼分不出「这篇还没建 KP」。

三条不变量（任一被改都会红）：
① **状态源**：后端 `list_files()` 每项的 `has_sidecar`（`document.py:511`）⇒ `file-tree.js:181`
   无侧车给行加 `.no-sidecar`（前端**不自己猜**有没有元数据）；
② **颜色轴**：已配置 ⇒ `--theme-color`（着色）；未配置 ⇒ `--text-secondary` 灰 + `opacity: .55`；
③ **互斥且只作用于文件行**：两条选择器一个带 `:not(.no-sidecar)`、一个是 `.no-sidecar`，
   都锚在 `.-tree-item` 下的 `.-tree-icon` ⇒ **不碰目录行**的文件夹图标（`.-tree-dir-head`）。
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_CSS = (_APP / "css" / "app.css").read_text(encoding="utf-8")
_JS = (_APP / "js" / "file-tree.js").read_text(encoding="utf-8")
_BACKEND = (Path(__file__).resolve().parents[1] / "src" / "memoria" / "services" / "document.py").read_text(
    encoding="utf-8"
)

#: 两条规则的完整选择器（后加的那条生效 ⇒ 取**最后一次**声明）
CONFIGURED_SELECTOR = ".-tree-item:not(.no-sidecar) .-tree-icon"
PLAIN_SELECTOR = ".-tree-item.no-sidecar .-tree-icon"


def _rule_body(selector: str) -> str:
    bodies = re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", _CSS)
    assert bodies, f"app.css 里找不到选择器：{selector}"
    return bodies[-1]


def test_state_comes_from_the_backend_has_sidecar_flag() -> None:
    """前端**不猜**：类名由后端 `has_sidecar` 决定（`list_files()` 逐文件读侧车）。"""
    assert '"has_sidecar": sc is not None' in _BACKEND
    assert 'f.has_sidecar ? "" : " no-sidecar"' in _JS


def test_configured_files_get_a_coloured_icon() -> None:
    body = _rule_body(CONFIGURED_SELECTOR)
    assert "var(--theme-color)" in body, "已配置的图标应当着主题色"


def test_unconfigured_files_get_a_grey_and_faint_icon() -> None:
    body = _rule_body(PLAIN_SELECTOR)
    assert "var(--text-secondary)" in body, "未配置的图标应当**不着色**（落次要色）"
    assert re.search(r"opacity:\s*0?\.\d+", body), "未配置的图标应当更浅（保留亮度轴）"


def test_the_two_states_are_mutually_exclusive_and_do_not_touch_folders() -> None:
    assert ":not(.no-sidecar)" in CONFIGURED_SELECTOR
    assert ":not(" not in PLAIN_SELECTOR
    # 两条都锚在**文件行**（`.-tree-item`）⇒ 目录行的文件夹图标（`.-tree-dir-head`）不受影响
    for selector in (CONFIGURED_SELECTOR, PLAIN_SELECTOR):
        assert selector.startswith(".-tree-item") and "tree-dir" not in selector


# ── 折角（缩进连接线）紧贴行首字形（2026-09-22）────────────────────────────────────────
# 人：「你之前设计的那个『折角』符号应该紧贴『文件图标』，而不是空一点位置」。
# 两处空档：① 文件行缩进旧值 `12 + depth×14` 比折角槽右缘多 8px；② 折角字形只有 8px 宽而槽是
# 1 整格 14px ⇒ 槽内右侧还空 6px。合计 14px（真机实测）。
CORNER_SELECTOR = ".-tree-guide-corner"
CORNER_CONNECTOR = ".-tree-guide-corner::after"


def test_file_rows_start_at_the_corner_slot_right_edge() -> None:
    """文件行缩进 = `4 + depth×14`（= 折角槽的右缘 = 下一格的起点），与目录行**同一条公式**。"""
    file_fn = _JS.split("function renderTreeFileItem")[1]
    dir_fn = _JS.split("function renderTreeDirNode")[1]
    assert "const pad = 4 + depth * 14;" in file_fn, "文件行首字形必须落在折角槽右缘"
    assert "const pad = 4 + depth * 14;" in dir_fn, "目录行是同一条公式（缩进阶梯只有一格宽）"
    assert "12 + depth * 14" not in _JS, "旧的多出 8px 空档不许复活"


def test_the_corner_slot_is_exactly_one_indent_step() -> None:
    """折角槽 = 1 整格（14px）⇒ 缩进阶梯与 `.-tree-guide-rail` 的 14px 步长一致。"""
    body = _rule_body(CORNER_SELECTOR)
    assert "flex: 0 0 14px;" in body and "width: 14px;" in body


def test_the_gap_inside_the_corner_slot_is_filled_by_a_one_pixel_connector() -> None:
    """字形只有 8px 宽 ⇒ 槽内右侧 6px 由 1px 横线延长到行首字形。

    坐标取自字形 viewBox `-0.5 0 8.5 10.5` 的横段（`M3 10 … L8 10`）：字形盒 10px 高、垂直居中，
    横段中心距行中线 **+4.5px**；横段右端在 8px 宽盒里 ≈ x=7.5px ⇒ 延长线自 7px 起（重叠约 0.5px、
    不留缝），一直连到槽右缘（`right: 0`）。线宽与透明度跟字形一致（1px / `.75`），**不拉宽字形**
    （`preserveAspectRatio: none` 会把 1px 竖笔画变成 1.7px、与 1px 导轨不符）。
    """
    body = _rule_body(CORNER_CONNECTOR)
    assert "left: 7px;" in body and "right: 0;" in body, "从字形横段右端连到槽右缘（= 行首字形）"
    assert "top: calc(50% + 4.5px);" in body, "与字形横段同高（不出现台阶）"
    assert "border-top: 1px solid currentColor;" in body, "线宽与导轨一致"
    assert "opacity: 0.75;" in body, "与字形同一透明度"
