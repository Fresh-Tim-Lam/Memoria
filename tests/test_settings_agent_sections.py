"""设置弹窗「页签条可滚动 + 滚条隐藏」与「Agent 页两个可折叠子版块」的契约钉子。

人（2026-09-23）三句：「`div` 这一栏页签支持鼠标滚动，滚条越细越好，最好看不到」；
「`button` 把 capability 做到 chat」；「chat 页内分两个子版块，并且可以折叠，页签 chat 改名为 Agent，
子版块名字你来定」。落地口径（子版块名由人授权自定 ⇒ 取「对话」+「能力插件」）：

1. **页签条 = `#settings-tabs` 可横向滚动**：`overflow-x: auto` + `flex-wrap: nowrap`
   （不 nowrap 就会换行、永不溢出 ⇒ 也就谈不上滚动）；滚条**整条隐藏**（`scrollbar-width: none`
   + `::-webkit-scrollbar` 归零）；滚轮绑定在 `graph-settings.js`（写法同 `#tabs` 的那条）。
2. **页签集合**：`renderTabsHtml()` 出 7 个按钮（含 `agent`、**不含** `plugins`）。
3. **Agent 页两个子版块**：`<details>` + `ensureAgentSections()`；「对话」默认展开、装着原
   `#agent-settings`（**移动节点**而不是重建 ⇒ 字段 id 与 `agent-panel.js` 的事件绑定原样保留）；
   「能力插件」默认折叠、装着能力面板。
4. **文案成对**：`settings.section.chat` / `settings.section.caps` 中英都有；`settings.tab.plugins`
   已退役（两份语言包都不再声明）。
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_GRAPH = _APP / "js" / "graph-settings.js"
_CSS = _APP / "css" / "app.css"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}


def _graph() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _rule(css: str, selector: str) -> str:
    """取某条**行首锚定**的规则体（子串匹配会误取覆盖块）。"""
    found = re.search(r"^" + re.escape(selector) + r" \{([^}]*)\}", css, re.M)
    assert found, f"缺规则：{selector}"
    return found.group(1)


def test_tab_strip_scrolls_with_the_wheel_and_hides_the_bar() -> None:
    """页签条可横向滚动、滚条**看不到**、且滚轮真的接管（不是靠拖滑块）。"""
    css = _CSS.read_text(encoding="utf-8")
    body = _rule(css, "#settings-tabs")
    assert "overflow-x: auto" in body, "页签条要能横向滚动"
    assert "scrollbar-width: none" in body, "滚条应整条隐藏（人：「最好看不到」）"
    assert "height: 0" in _rule(css, "#settings-tabs::-webkit-scrollbar"), "WebKit 滚条也要归零"
    assert "flex-wrap: nowrap" in _rule(css, "#settings-tabs .-config-tabs"), "不 nowrap 就永远不溢出"

    graph = _graph()
    assert "bindSettingsTabWheelScroll" in graph and "tabsEl.scrollLeft += delta" in graph, "滚轮没有绑上"
    assert 'document.getElementById("settings-tabs")' in graph


def test_tab_set_is_seven_with_agent_and_without_plugins() -> None:
    """页签 = 7 个（`2D/3D/群/检索/检查/显示/Agent`）；`plugins` 已并入 Agent 页。"""
    tabs = _graph().split("function renderTabsHtml")[1].split("</div>`")[0]
    names = re.findall(r'data-settings-tab="([a-zA-Z0-9]+)"', tabs)
    assert names == ["graph2d", "graph3d", "graphGroups", "search", "check", "view", "agent"], names
    assert "settings.tab.plugins" not in tabs and "plugins" not in names


def test_agent_page_has_two_collapsible_sections() -> None:
    """「Agent」页 = 两个 `<details>` 子版块：「对话」（默认开）+「能力插件」（默认合）。"""
    graph = _graph()
    assert 'document.createElement("details")' in graph, "子版块应是可折叠的 details"
    assert 'box.open = !!open;' in graph
    assert 'settingsSectionEl("settings.section.chat", "agent-section-chat", true)' in graph
    assert 'settingsSectionEl("settings.section.caps", "agent-section-caps", false)' in graph


def test_chat_section_moves_the_existing_form_instead_of_rebuilding_it() -> None:
    """「对话」子版块**移动**原 `#agent-settings`（重建会丢事件绑定与字段 id）。"""
    graph = _graph()
    assert "while (env.firstChild) chatBody.appendChild(env.firstChild);" in graph
    assert 'env.querySelector("#agent-sections")' in graph, "装配要幂等（切页签会反复调用）"
    assert "global.MemoriaPluginSettings.renderSettingsBody()" in graph
    assert "global.MemoriaPluginSettings.bindSettingsForm(capsBody)" in graph


def test_section_titles_exist_in_both_locales_and_plugins_tab_key_is_retired() -> None:
    """子版块标题中英成对；`settings.tab.plugins`（原「能力」页签名）已退役。"""
    zh = _LOCALES["zh-CN"].read_text(encoding="utf-8")
    en = _LOCALES["en"].read_text(encoding="utf-8")
    for text, chat, caps in ((zh, "对话", "能力插件"), (en, "Chat", "Capabilities")):
        assert re.search(r"section:\s*\{", text), "缺 settings.section 子对象"
        assert f'chat: "{chat}"' in text and f'caps: "{caps}"' in text, f"{chat}/{caps} 缺失"
    assert 'plugins: "能力"' not in zh and 'plugins: "Capabilities"' not in en, "退役的页签名不该还在"
    assert 'agent: "Agent"' in zh and 'agent: "Agent"' in en, "页签应叫 Agent"


def test_section_styles_reuse_tokens() -> None:
    """子版块样式落在 `app.css` 末尾追加块、用既有令牌、不硬编码颜色。"""
    css = _CSS.read_text(encoding="utf-8")
    block = css.rsplit("/* ===== 2026-09-23 追加：设置页签条", 1)[1]
    for selector in (".-settings-section", ".-settings-section-head", ".-settings-section-body"):
        assert selector in block, f"样式缺失：{selector}"
    assert "var(--border-sep, var(--border))" in block and "var(--text-bright)" in block
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", block), "不许硬编码颜色"


def test_every_settings_page_section_folds_through_one_shared_path() -> None:
    """人 2026-09-23：「设置其他地方也可也效仿 Agent 页签的子版块设计可展缩」。

    `foldSettingsSections()` 把各页的 `<section class="-settings-section">` 就地折成
    `<details class="-settings-section" open>`（**移动节点** ⇒ 六个 renderer（2D/3D/节点群/检索/检查/显示）
    一行未改、字段 id 与事件绑定原样保留）；调用点**同行追加**在 `setSettingsTab()` 的 if/else 链之后
    ⇒ 六个页签共用一条路径，且不推位下方任何一行（既有 `graph-settings.js:<行号>` 锚点零漂移）。
    """
    graph = _graph()
    assert "function foldSettingsSections(root)" in graph
    assert 'root.querySelectorAll("section.-settings-section")' in graph, "只认 section ⇒ 对已有 details 幂等"
    assert "box.open = true;" in graph, "默认展开：是「可收起」，不是「默认藏起来」"
    assert 'head.className = "-settings-section-head";' in graph, "折叠头复用同一套样式"
    assert 'body.className = "-settings-section-body";' in graph
    assert "while (sec.firstChild) body.appendChild(sec.firstChild);" in graph, "移动节点，不重建 HTML"
    assert "sec.replaceWith(box);" in graph
    assert "} foldSettingsSections(bodyEl);" in graph, "要与最后一个 else-if 的 `}` 同行（否则行号漂移）"


def test_folded_head_matches_the_old_heading_style() -> None:
    """折叠头 = 折叠前 `<h3 class="-settings-heading">` 那一档（同字号/字重），并给出点击热区。"""
    css = _CSS.read_text(encoding="utf-8")
    heading = _rule(css, ".-settings-heading")
    assert "font-size: 0.75rem;" in heading and "font-weight: 600;" in heading
    tail = css.rsplit("/* ===== 2026-09-23 追加：**折叠子版块的标题定为一套规范**", 1)[1]
    head = tail.split(".-settings-section-head {", 1)[1].split("}", 1)[0]
    assert "font-size: 0.75rem;" in head and "font-weight: 600;" in head, "同一档，否则折叠前后观感会变"
    assert "padding: 0.5rem 0;" in head, "上下 8px 兼作点击热区（取代原 `<h3>` 的 margin-bottom）"
