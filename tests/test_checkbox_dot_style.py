"""勾选框 / 单选框「圆点」化的契约钉子。

人：「把所有的方框打勾选择 ui 改成圆点 ui，原本空，点了就变蓝色」⇒ 一处覆盖全部原生
`input[type="checkbox"]` 与 `input[type="radio"]`（`app.css` 末尾追加块），行为口径 = **未选中空心圆、
选中实心蓝点**；后补口径 = 人：「保持单选的多选的圆 ui 一致，单选多选都可以用 `input`，你只需要在这
说明单选多选 `span`」⇒ **两者长相一致**，单选/多选的区别只由卡片里的 `.-agent-question-mode` 徽标说明。
本文件钉六件事：

1. **块存在且在末尾**（`app.css` 末尾追加 ⇒ 既有 `app.css:<行号>` 锚点零漂移）；
2. **checkbox 与 radio 同一条规则**（不许把 radio 漏在外面 ⇒ 单选多选长相才会一致）；
3. **未选中 = 空心**（`appearance: none` + `border-radius: 50%` + 透明底 + `--border` 描边）；
4. **选中 = 变蓝**（`background` 与 `border-color` 都取 `--theme-color`，而不是各页面自己写 accent）；
5. **靠特异性取胜**（选择器带 `#app`、块里**不许**出现 `!important` —— 否则日后无法再覆盖）；
6. **补回 `appearance: none` 丢掉的两种原生表现**（禁用态降透明、键盘聚焦描边），
   并**结构性验证** `#app` 确实包住了各弹窗（否则设置面板里的控件会漏出原生外观）。
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_CSS = _APP / "css" / "app.css"
_THEME = _APP.parent / "theme" / "memoria.css"  # 主题变量层（先于 app.css 加载）
_INDEX = _APP / "index.html"

#: 末尾块的注释锚（改块时这个前缀要跟着改，否则本文件会立刻红）
_ANCHOR = "/* ===== 2026-09-23 追加：勾选框 / 单选框统一改「圆点」"
_MARK = "2026-09-23 追加：勾选框 / 单选框统一改「圆点」"  # 切块用（保留开头的 `/*`，好让 `_code()` 剥注释）
#: 两种控件**共用**的那段选择器（改动它等于改口径 ⇒ 本文件会立刻红）
_TYPES = ':is([type="checkbox"], [type="radio"])'
_BASE = f':is(#app, .-modal) input{_TYPES}'
_CHECKED = f"{_BASE}:checked"

#: 既有的"更具体的旧写法"（均 0,2,1）—— `:is(#app, .-modal)`（1,1,1）才能一处盖住；它们仍在 = 注释里的理由仍成立
_LEGACY = (
    (_CSS, '.-agent-net input[type="checkbox"]'),
    (_THEME, '.toggle-setting input[type="checkbox"]'),
    (_CSS, '.-settings-field--inline input[type="checkbox"]'),
    (_CSS, '.-link-match-row input[type="checkbox"]:disabled'),
)


def _block() -> str:
    """末尾追加块（从注释锚到文件末，**含注释**）—— 只认这一块，避免误匹配别处的同名声明。"""
    css = _CSS.read_text(encoding="utf-8")
    assert _ANCHOR in css, "勾选框圆点化的末尾块不见了"
    return "/*" + css.split(_MARK, 1)[1]


def _rule(block: str, selector: str) -> str:
    """取某条**行首锚定**的规则体（`.-tree-*` 那轮踩过坑：子串匹配会误取覆盖块）。"""
    found = re.search(r"^" + re.escape(selector) + r" \{([^}]*)\}", block, re.M)
    assert found, f"缺规则：{selector}"
    return found.group(1)


def _code(text: str) -> str:
    """剥掉 `/* … */` 注释 —— 注释里会**提到** `!important` 当反例，不该算进判据。"""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _element(html: str, open_tag: str) -> str:
    """从 `open_tag` 起按 `<div>` / `</div>` **配平**取整段元素（比按缩进猜闭标签稳）。"""
    start = html.index(open_tag)
    depth = 0
    for found in re.finditer(r"<(/?)div\b[^>]*>", html[start:]):
        depth += -1 if found.group(1) else 1
        if depth == 0:
            return html[start : start + found.end()]
    raise AssertionError(f"{open_tag} 没有闭合")


def test_the_block_is_appended_at_the_very_end() -> None:
    """末尾追加块**不许被后面的规则覆盖**（追加块之后不得再出现同名选择器）。

    原本判据是"本块之后没有别的注释块"；2026-09-23 起了第二块末尾追加（待答卡样式）⇒ 判据改成
    **实质要件**：本块之后再没有勾选框/单选框选择器（谁在后面改它谁就得先来改这里）。
    """
    css = _CSS.read_text(encoding="utf-8")
    assert css.rstrip().endswith("}"), "文件应以规则收尾"
    tail = css.split(_MARK, 1)[1]
    # 本块的 5 条规则之后（= 本块末尾那个空行之后的尾部）不许再出现同名选择器
    body = tail.split("\n\n", 1)[1] if "\n\n" in tail else ""
    for needle in ('[type="checkbox"]', '[type="radio"]'):
        assert needle not in body, f"本块之后又出现了 {needle} 规则（会覆盖圆点外观）"


def test_checkbox_and_radio_share_one_rule() -> None:
    """**单选与多选同一套圆点**：两种控件必须出现在**同一个** `:is(...)` 里（人：「保持单选的多选的圆 ui 一致」）。

    分两条规则写迟早会漂（改一处忘一处）⇒ 这里钉"共用选择器"，并且**不许**单独再给 radio 写规则。
    """
    block = _code(_block())
    assert _TYPES in _block(), "两种控件没有共用一个 :is(...) 选择器"
    for line in block.splitlines():
        head = line.split("{", 1)[0]
        assert not ("radio" in head and "checkbox" not in head), f"出现只作用于单选的规则（会与多选不一致）：{head.strip()}"
    for name in ("", ":checked", ":hover:not(:disabled)", ":focus-visible", ":disabled"):
        assert f"{_BASE}{name} {{" in block, f"缺共用规则：{_BASE}{name}"


def test_unchecked_is_an_empty_circle() -> None:
    """未选中 = **空心圆**：抹掉原生方框/单选点外观，圆形 + 透明底 + 描边。"""
    body = _rule(_block(), _BASE)
    assert "appearance: none" in body and "-webkit-appearance: none" in body, "没有抹掉原生控件外观"
    assert "border-radius: 50%" in body, "不是圆"
    assert "background: transparent" in body, "未选中不该有填充（人：「原本空」）"
    assert "border: 1px solid var(--border)" in body, "未选中应有描边，否则空心圆看不见"


def test_dot_size_is_the_agreed_0_8x() -> None:
    """圆点尺寸 = **此前 0.875rem 的 0.8**（≈11.2px ⇒ `0.7rem`）。

    人（2026-09-23）：「所有原点都做太大了，变为原来 0.8」⇒ 这是**取值判断**，改它只改这一个数；
    本条约住"别再随手放大"，也钉住宽高都取该变量（别只改一边）。
    """
    body = _rule(_block(), _BASE)
    assert "--checkbox-size: 0.7rem" in body, "圆点尺寸被改动了（应为此前 0.875rem 的 0.8）"
    assert "width: var(--checkbox-size)" in body and "height: var(--checkbox-size)" in body, "宽高必须都取该变量"


def test_checked_turns_blue() -> None:
    """选中 = **变蓝**：实心底与描边都取主题蓝 `--theme-color`（不新引颜色常量）。"""
    body = _rule(_block(), _CHECKED)
    assert "background: var(--theme-color)" in body, "选中没变蓝"
    assert "border-color: var(--theme-color)" in body, "选中的描边没跟着变蓝"


def test_specificity_wins_without_important() -> None:
    """`:is(#app, .-modal)`（1,1,1）压住既有的 (0,2,1) 写法；块里**不许** `!important`（留着日后可覆盖）。"""
    block = _block()
    assert "!important" not in _code(block), "不许用 !important 打架"
    for path, legacy in _LEGACY:
        assert legacy in path.read_text(encoding="utf-8"), f"注释里的理由失效了：{legacy} 已不在 {path.name} 中"


def test_disabled_and_keyboard_states_are_restored() -> None:
    """`appearance: none` 会连带丢掉原生禁用/聚焦表现 ⇒ 这两条必须自己补回来。"""
    block = _block()
    assert "opacity" in _rule(block, f'{_BASE}:disabled')
    focus = _rule(block, f'{_BASE}:focus-visible')
    assert "outline: 1px solid var(--theme-color)" in focus, "键盘聚焦看不出焦点"


def test_scope_also_covers_the_modals_which_live_outside_app() -> None:
    """作用域必须**同时**含 `.-modal`：`#app` 在 `index.html:250` 就闭合，各弹窗是它的**兄弟**
    （252 行注释明写「浮层统一放 body 层（`#app` 外）」）—— 只写 `#app` 会漏掉设置面板里所有勾选框。

    这条是本轮**真被测试抓到**的缺陷（第一版只写 `#app`）：断言是**双向**的 —— 弹窗若哪天搬进
    `#app`，这里会红并提示把 `.-modal` 分支删掉。
    """
    block = _code(_block())
    assert _BASE in block, "作用域没带上弹窗"
    html = _INDEX.read_text(encoding="utf-8")
    app = _element(html, '<div id="app">')
    for modal in ("settings-body", "link-body", "import-conflict-body", "kb-agent-body"):
        assert f'id="{modal}"' in html, f"{modal} 不见了"
        assert f'id="{modal}"' not in app, f"{modal} 已搬进 #app ⇒ 作用域的 `.-modal` 分支应删掉"
