"""文件树图标两态（`已配置元数据` / `未配置`）**按颜色**区分 —— CSS 契约钉子。

**2026-09-22 追加**：同一个文件也钉住文件树的**缩进与连接线**口径（折角退役 ⇒ 每层一条竖导轨
「|」、文件行标记位是一个点、目录行是三角，且两种行**逐列对齐**；见文件末尾三例）。

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


# ── 缩进连接线（2026-09-22 第三版：**折角退役**，仿 Trae）──────────────────────────────
# 人：「你不用折角了，仿照 trae 文件树的显示，展开文件夹后，子文件夹和文件前面都有「|」，
#      文件前面是一个点，而文件夹就是一个三角，保证文件夹和子文件对齐」。
RAIL_SELECTOR = ".-tree-guide-rail"
DOT_SELECTOR = ".-tree-dot"
TWISTY_SELECTOR = ".-tree-twisty"


def test_file_and_dir_rows_share_one_indent_formula_so_columns_line_up() -> None:
    """**两种行同一个缩进公式** ⇒ 图标、文字逐列对齐（人：「保证文件夹和子文件对齐」）。

    缩进 = `4 + depth×14`：导轨每层占一格，行首「标记位」占**最后一格**（目录 = 展开三角 /
    文件 = 点），图标与文字都在标记位之后 ⇒ 只要两行的 `gap` 相同，三列就必然对齐。
    旧值 `12 + depth×14`（文件行）已被本轮统一掉。
    """
    file_fn = _JS.split("function renderTreeFileItem")[1]
    dir_fn = _JS.split("function renderTreeDirNode")[1]
    assert "const pad = 4 + depth * 14;" in file_fn, "文件行 = 统一公式"
    assert "const pad = 4 + depth * 14;" in dir_fn, "目录行 = 同一条公式"
    assert "12 + depth * 14" not in _JS, "旧的 +8px 偏置不许复活"
    # 两行的 gap 必须同值（否则「标记位→图标」那段差出来，图标就不齐）。
    # 取**行首**那条：`.-tree-item` 在文件里还有第二条（末尾块 `{ position: relative; }`），
    # `_rule_body()` 的"最后一条匹配"会取到它。
    item_gap = re.search(r"^\.-tree-item \{([^}]*)\}", _CSS, re.M).group(1)
    head_gap = re.search(r"^\.-tree-dir-head \{([^}]*)\}", _CSS, re.M).group(1)
    assert "gap: 0.25rem;" in item_gap and "gap: 0.25rem;" in head_gap, "文件行/目录行 gap 必须一致"


def test_the_elbow_is_retired_and_only_vertical_rails_remain() -> None:
    """**不再画折角**：`treeGuides()` 只发 `depth` 段竖导轨「|」，且源码里不再引用 `treeCorner`。"""
    guides = _JS.split("function treeGuides(")[1].split("\n  }")[0]
    assert "i < depth" in guides, "每层一条导轨（depth 段），不是 depth-1 段"
    assert "treeCorner" not in guides, "折角字形不再被使用"
    assert "-tree-guide-corner" not in _JS, "折角类名不该再出现（退役）"
    # CSS 侧：折角的两条规则（本体 + `::after`）都不许再以**选择器**形式存在
    for pattern in (r"^\.-tree-guide-corner\s*\{", r"^\.-tree-guide-corner::after\s*\{",
                    r"^\.-tree-item \.-tree-guide-corner::after\s*\{"):
        assert not re.search(pattern, _CSS, re.M), f"折角规则应已移除：{pattern}"
    assert _rule_body(RAIL_SELECTOR), "竖导轨（「|」）保留"


def test_file_rows_carry_a_dot_marker_in_the_same_slot_as_the_twisty() -> None:
    """文件行的标记位 = **一个点**（目录行那儿是三角），且两者**同宽** ⇒ 落在同一格。

    点**贴右**（`justify-content: flex-end`）⇒ 紧邻文件图标，读作"文件前面一个点"。
    """
    file_fn = _JS.split("function renderTreeFileItem")[1]
    assert '<span class="-tree-dot" aria-hidden="true"></span>' in file_fn, "文件行必须带点标记"
    assert "-tree-dot" not in _JS.split("function renderTreeDirNode")[0], "点只属于文件行"
    dot = _rule_body(DOT_SELECTOR)
    twisty = _rule_body(TWISTY_SELECTOR)
    assert "0.875rem" in dot and "0.875rem" in twisty, "点与三角必须同宽（同一格）"
    assert "justify-content: flex-end;" in dot, "点贴右 ⇒ 紧邻文件图标"
    assert "color: var(--border);" in dot, "与导轨同色系"
    mark = _rule_body(DOT_SELECTOR + "::after")
    assert "border-radius: 50%;" in mark and "width: 3px;" in mark and "height: 3px;" in mark, "是个圆点"


def test_the_rail_is_centred_under_the_parent_twisty() -> None:
    """竖线画在导轨槽的**中心**（`left: 7px`），不是槽左缘 —— 这样它正好穿过母文件夹三角的中心。

    人：「竖线应该保持和母文件夹的三角符号对齐」。三角字形在它自己那 14px 格里是**居中**的
    （`.-tree-twisty` 的 `text-align: center` ⇒ 字形中心 = 格中心），所以线的 x 必须是「槽左缘 + 7px」；
    原来用 `border-left` 画在槽左缘 ⇒ 比三角中心偏左 7px。
    """
    rail = _rule_body(RAIL_SELECTOR)  # 末尾覆盖块那条（基规则在 5564，末尾块改画法）
    assert "position: relative;" in rail and "border-left: 0;" in rail, "槽左缘的线要撤掉"
    mark = _rule_body(RAIL_SELECTOR + "::before")
    assert "left: 7px;" in mark, "线画在槽中心（14px 槽的一半）"
    assert "border-left: 1px solid currentColor;" in mark, "仍是 1px、同色"
    # 取**行首**那条基规则（`_rule_body()` 的最后一条匹配是末尾覆盖块，不含 flex/width）
    base = re.search(r"^" + re.escape(RAIL_SELECTOR) + r" \{([^}]*)\}", _CSS, re.M).group(1)
    assert "flex: 0 0 14px;" in base and "width: 14px;" in base, "槽宽仍是 14px（去 border 不改盒宽）"
    assert "text-align: center;" in _rule_body(TWISTY_SELECTOR), "三角居中 ⇒ 其中心就是槽中心"
