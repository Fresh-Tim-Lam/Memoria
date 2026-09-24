"""设置里的**字体类型**（按语言分档 + 顶栏一档）的契约钉子。

人（2026-09-23）：「设置中 文字还要添加字体类型，这个字体是 markdown 预览的文字和 agent 对话栏中渲染的
文字，还支持修改顶栏 "MEMORIA" 的字体，不同语言可以设置不同字体」。落地口径：

1. **落点只有两处 CSS 变量**（挂在 `<html>` 上，全站生效）：
   `--font-content` → `.markdown-body`（**预览与对话栏正文共用这一个类**）；
   `--font-brand` → `.toolbar-left .logo`（顶栏字标），留空由 `var()` 兜底链回正文/`--font-sans`。
2. **按语言各一档**：`fonts: {"zh-CN": …, "en": …}`，正文栈按"**当前界面语言优先**、其余按支持顺序跟上"
   拼成（浏览器按字形逐字选用）⇒ 中英各用各的字体，切语言只换优先级。
3. **空值要能真正清掉**：`normalizeFonts()` **覆盖全部支持语言**（缺的填空串）—— 因为后端
   `save_ui_settings` 是浅合并（删键清不掉磁盘旧值，下次启动会把旧字体带回来）。
4. **字体名引号**：含空格/逗号时补 `"`（否则 `Comic Sans MS` 会被当成三个 family）。
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_JS = _APP / "js" / "display-settings.js"
_CSS = _APP / "css" / "app.css"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}

_KEYS = ("fontLangNote", "fontSlotDefault", "fontBrandLabel", "fontBrandDefault", "fontBrandNote")


def _js() -> str:
    return _JS.read_text(encoding="utf-8")


def _rule(css: str, selector: str) -> str:
    found = re.search(r"^" + re.escape(selector) + r" \{([^}]*)\}", css, re.M)
    assert found, f"缺规则：{selector}"
    return found.group(1)


def test_defaults_carry_both_font_keys() -> None:
    """`fonts`（按语言）与 `fontBrand`（顶栏）都进了 DEFAULTS ⇒ 不设任何值时行为与改动前完全一致。"""
    src = _js()
    assert "fonts: {}," in src, "缺按语言的字体默认值"
    assert 'fontBrand: "",' in src, "缺顶栏字体默认值"


def test_language_slots_cover_every_supported_language() -> None:
    """`normalizeFonts()` **覆盖全部支持语言**（空档显式写空串）—— 否则浅合并清不掉磁盘旧值。"""
    src = _js()
    assert "function normalizeFonts(raw)" in src
    assert "for (const code of langs())" in src, "必须遍历全部支持语言（不能只保留有值的键）"
    assert "out[code] = typeof value === \"string\" ? value.trim() : \"\";" in src


def test_content_stack_puts_the_current_language_first() -> None:
    """正文栈 = **当前界面语言优先** + 其余语言跟上（切语言只换优先级，中英各用自己的字体）。"""
    src = _js()
    assert "function fontStack(fonts)" in src
    assert "const order = [cur].concat(langs().filter((code) => code !== cur));" in src
    assert ".map((code) => quoteFont((fonts || {})[code])).filter(Boolean).join(\", \")" in src


def test_font_names_are_quoted_when_needed() -> None:
    """含空格/逗号的字体名要补引号（否则 `Comic Sans MS` 被解析成三个 family）。"""
    src = _js()
    assert "function quoteFont(name)" in src
    assert 'return /[\\s,]/.test(value) ? \'"\' + value.replace(/"/g, "") + \'"\' : value;' in src
    assert "/^'.*'$/." in src and '/^".*"$/.test(value)' in src, "已带引号的不要二次包装"


def test_apply_fonts_sets_and_clears_the_two_variables() -> None:
    """空值必须**移除**变量（回落 `--font-sans`），不是写空串；两个变量都挂在 `<html>` 上。"""
    src = _js()
    assert "function applyFonts(s)" in src
    assert 'root.style.setProperty("--font-content", stack);' in src
    assert 'root.style.removeProperty("--font-content");' in src
    assert 'root.style.setProperty("--font-brand", brand);' in src
    assert 'root.style.removeProperty("--font-brand");' in src
    assert "applyFonts(s);" in src.split("function applyAll()")[1], "applyAll 要带上字体"


def test_css_rules_cover_preview_transcript_and_brand() -> None:
    """两条 CSS 规则：`.markdown-body`（预览 + 对话正文共用）与顶栏字标，兜底链完整。"""
    css = _CSS.read_text(encoding="utf-8")
    assert "font-family: var(--font-content, var(--font-sans));" in _rule(css, ".markdown-body")
    brand = _rule(css, ".toolbar-left .logo")
    assert "font-family: var(--font-brand, var(--font-content, var(--font-sans)));" in brand


def test_dropdown_popup_is_capped_and_scrolls_only_for_font_slots() -> None:
    """下拉浮层**限高 + 可滚**（人 2026-09-23：「下拉不用全展开，可以加滚条」）。

    做法 = `appearance: base-select` + `::picker(select)`（Chromium 135+ 的可定制 select），
    这样仍是原生控件（键盘 / IME / 无障碍语义由浏览器给），只是浮层可样式化。
    作用域必须**只命中字体那两个** —— 主题 / 语言等既有原生下拉不许被牵连。
    """
    css = _CSS.read_text(encoding="utf-8")
    marker = "@supports (appearance: base-select)"
    assert marker in css, "缺可定制 select 的开关（不支持时整块失效 = 退回原生浮层）"
    block = css.split(marker, 1)[1]
    assert 'select[data-display-font-lang],\n    select[data-display-setting="fontBrand"] {\n        appearance: base-select;' in block
    assert 'select[data-display-font-lang]::picker(select),' in block
    assert 'select[data-display-setting="fontBrand"]::picker(select)' in block
    assert "max-height: 8.75rem;" in block, "浮层要限高（与 .-edge-target-datalist 同档）"
    assert "overflow-y: auto;" in block, "超出部分要能滚（即人说的「滚条」）"
    assert "overscroll-behavior: contain;" in block, "滚到底不要带动外层表单"
    assert "#display-theme" not in block and "#display-language" not in block, "别牵连其它原生下拉"
    # `base-select` 会让 select 继承父级字体（原生控件默认是 UA 的 Arial）⇒ 不统一就会让同一页的
    # 「字体」下拉与「主题 / 语言」下拉字体不一致（正是人抱怨的同一类问题）。
    settings_select = css.rsplit(".-settings-field select {", 1)[1].split("}", 1)[0]
    assert "font-family: var(--font-sans);" in settings_select, "设置区下拉要统一字体"
    assert "min-height: 1.75rem;" in settings_select, "base-select 是 flex 盒、闭合态矮 2px，要钉下界对齐"


def test_picker_scrollbar_mirrors_the_global_thin_scrollbar() -> None:
    """浮层滚条必须与全站细滚条**同一套令牌与几何**（人 2026-09-23：「请你保持和其他统一的细滚条」）。

    全局那条 `html *::-webkit-scrollbar` 够不到 picker（top layer 里的伪元素，实测仍是平台默认 15px）
    ⇒ 只能显式镜像：10px 命中区 + 4px 两侧透明内缩 = 可见 2px 滑块 + 三档不透明度。
    两条实测约束也要钉住：**必须带 `::picker(select)`**；**不许**写 `scrollbar-width/color`
    （标准属性一非 `auto`，Chromium 就整块忽略 `::-webkit-scrollbar`）。
    """
    css = _CSS.read_text(encoding="utf-8")
    block = css.split("@supports (appearance: base-select)", 1)[1]
    assert "select[data-display-font-lang]::picker(select)::-webkit-scrollbar," in block
    bar = block.split("::-webkit-scrollbar {", 1)[1].split("}", 1)[0]
    assert "width: var(--scrollbar-hit);" in bar, "命中区要复用全局令牌（10px）"
    thumb = block.split("::-webkit-scrollbar-thumb {", 1)[1].split("}", 1)[0]
    assert "background-color: var(--scrollbar-thumb-idle);" in thumb
    assert "border-width: 0 var(--scrollbar-inset) 1px;" in thumb, "4px 两侧内缩 ⇒ 可见 2px"
    assert "background-clip: content-box;" in thumb
    assert "border-radius: 999px;" in thumb
    assert "var(--scrollbar-thumb-hover)" in block and "var(--scrollbar-thumb-drag)" in block, "三档都要有"
    # 注释里出现这两个名字是**说明为什么不能用**；判据只看有没有真写成声明。
    assert not re.search(r"scrollbar-(width|color)\s*:", block), "标准属性会顶掉 ::-webkit-scrollbar（466 vs 443）"


def test_settings_form_binds_language_slots_and_brand() -> None:
    """UI：每语言一个**下拉**（`data-display-font-lang`）+ 顶栏一行（复用既有 `data-display-setting` 通道）。

    人 2026-09-23 复审：「你新添加的这些框的 ui 样式违反整体设计……你应该给下拉可选样式而不是输入」
    ⇒ 控件必须是 `.settings-field` 里的原生 `<select>`（走既有 `.-settings-field select` 规则、外观与
    「主题 / 语言」两个下拉一致），且**不许**再出现自造的 `input[type=text]` + `datalist`。
    """
    src = _js()
    assert 'data-display-font-lang="' in src and "root.querySelectorAll(\"[data-display-font-lang]\")" in src
    assert "save({ fonts });" in src
    assert 'data-display-setting="fontBrand"' in src, "顶栏字体走既有绑定通道"
    assert "i18n.langDisplay" in src, "语言档标签用 langDisplay（与界面语言一致）"


def test_font_widgets_are_dropdowns_not_free_text() -> None:
    """字体档必须是**下拉**：首项空值（= 跟随默认），其后是候选表；存档值不在表里也要补进来。"""
    src = _js()
    assert "function fontSelect(attrs, value, noneLabel)" in src
    assert "return `<select ${attrs}>${options}</select>`;" in src
    assert 'class="-settings-field"' in src, "要挂在既有字段容器里，样式才与其它下拉一致"
    assert "datalist" not in src, "改用下拉后不该再有 datalist"
    assert '"text"' not in src, "不该再有自造的文本输入框"
    assert '<option value=""${cur ? "" : " selected"}>' in src, "首项必须是空值（选它 = 跟随默认）"
    assert (
        "const names = cur && FONT_CHOICES.indexOf(cur) === -1 ? [cur].concat(FONT_CHOICES) : FONT_CHOICES;"
        in src
    ), "存档值不在候选表里时要补成选项，否则回显成空白"


def test_font_labels_exist_in_both_locales() -> None:
    """五个字体文案键中英成对（缺一个设置页就会漏出裸 key）。"""
    for locale, path in _LOCALES.items():
        text = path.read_text(encoding="utf-8")
        missing = [key for key in _KEYS if f"{key}:" not in text]
        assert not missing, f"{locale} 缺 settings.display 字体键：{missing}"
        assert "Object.assign(g.MEMORIA_LOCALES[\"" + locale + "\"].settings.display, {" in text
