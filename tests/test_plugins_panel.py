"""能力插件面板（设置 →「能力」页签）的契约钉子。

面板 = `js/plugins-settings.js`，它**只**调后端网关 `agent_plugins` / `agent_plugin_set`
（`services/agent/plugins.py` 末尾「契约接线」）。本文件钉四件事：

1. **模块形状**：`window.MemoriaPluginSettings` 暴露 `renderSettingsBody` / `bindSettingsForm`
   —— 与 `MemoriaDisplaySettings` 同款，`graph-settings.js` 的页签分发就按这个形状调；
2. **只走网关**：面板里只允许出现那两个 RPC 名，不出现任何"自己读文件 / 拼库路径"的痕迹
   （这正是"网关已就位、UI 只消费"的边界）；
3. **两处接线**：`graph-settings.js` 的 `renderTabsHtml()` 有该页签、`setSettingsTab()` 有对应分支；
   `index.html` 以**末尾追加**方式加载脚本（保既有 `index.html:<行>` 锚点不推位）；
4. **文案成对**：面板用到的 i18n 键在**中英两份**语言包里都存在（缺一个界面就会漏出裸 key）。
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_PANEL = _APP / "js" / "plugins-settings.js"
_GRAPH = _APP / "js" / "graph-settings.js"
_INDEX = _APP / "index.html"
_CSS = _APP / "css" / "app.css"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}

#: 面板**自己**声明并用到的 i18n 键（叶子名；前缀统一 `settings.plugins.`）。
#: 2026-09-23 起面板不再占独立页签（并入「Agent」页的「能力插件」子版块）⇒ 页签名 `settings.tab.plugins` 已退役。
_PANEL_KEYS = (
    "hint", "loading", "empty", "failed", "noKb",
    "toolsLabel", "readLabel", "writeLabel", "approvalLabel",
    "enforced", "enforcedOn", "enforcedOff", "registry",
    "warnTitle", "errTitle", "saving", "savedOn", "savedOff",
    # 2026-09-24：库级参数（`config` 值位的第一例 = `web-fetch` 的域名名单）的就地编辑
    "configLabel", "configHint", "saved",
)
_SOURCE_KEYS = ("builtin", "user", "kb")
#: 参数名 → 标签（键名是**拼出来**的：`settings.plugins.param.<name>`，故正则抓不到，单列一份）。
_PARAM_KEYS = ("allow", "deny")


def _panel() -> str:
    return _PANEL.read_text(encoding="utf-8")


def test_panel_exposes_the_settings_module_shape() -> None:
    """`window.MemoriaPluginSettings = { renderSettingsBody, bindSettingsForm }` —— 页签分发认这个形状。"""
    src = _panel()
    assert "global.MemoriaPluginSettings = { renderSettingsBody, bindSettingsForm };" in src
    assert "function renderSettingsBody()" in src and "async function bindSettingsForm(root)" in src
    # 依赖只有应用门面（call / T / esc）；缺席时降级，不抛
    assert 'const A = () => global.MemoriaApp || {}' in src


def test_panel_only_talks_to_the_gateway() -> None:
    """面板只调那两个网关 RPC；**不**自己读文件、拼库路径、或直接碰 `.memoria/agent/**`。

    判据只看**代码行**（注释里出现 `<库>/.memoria/agent/capabilities.json` 是给人看的说明，不算越界）。
    """
    src = _panel()
    code = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith(("*", "//", "/*"))
    )
    called = set(re.findall(r'call\("([a-zA-Z_]+)"', code))
    assert called == {"agent_plugins", "agent_plugin_set"}, f"面板多调了别的 RPC：{sorted(called)}"
    for banned in (".memoria", "capabilities.json", "fetch(", "XMLHttpRequest", "readFile", "list_files"):
        assert banned not in code, f"面板不该出现 {banned!r}（切库/读文件都属后端网关的事）"


def test_panel_is_mounted_inside_the_agent_tab() -> None:
    """**不再单独占页签**：面板挂在「Agent」页签的「能力插件」子版块里（`ensureAgentSections()`）。

    人（2026-09-23）：「把 capability 做到 chat，chat 页内分两个子版块，并且可以折叠」 ⇒
    旧的两处接线（页签按钮 + `tab === "plugins"` 分发）随之退役，改由「Agent」页装配时挂载。
    """
    graph = _GRAPH.read_text(encoding="utf-8")
    # 只看**代码行**：退役说明的注释里会**提到**旧分支名（那是给人看的，不算复活）
    code = "\n".join(line for line in graph.splitlines() if not line.strip().startswith(("*", "//", "/*")))
    assert 'data-settings-tab="plugins"' not in code, "「能力」页签已并入 Agent 页，不该再有这个按钮"
    assert 'tab === "plugins"' not in code, "旧的 plugins 分发分支应已退役"
    assert "function ensureAgentSections()" in code, "缺 Agent 页的子版块装配函数"
    assert "ensureAgentSections()" in code.split("if (isAgent)")[1], "Agent 分支没有调装配"
    assert "global.MemoriaPluginSettings.renderSettingsBody()" in code
    assert "global.MemoriaPluginSettings.bindSettingsForm(capsBody)" in code, "面板宿主应是子版块的 body"


def test_index_loads_the_panel_after_the_app_and_panel_modules() -> None:
    """脚本在 `app.js` / `agent-panel.js` **之后**加载（末尾追加的机制 ⇒ 既有 `index.html:<行>` 锚点零漂移）。

    判据是**实质要件**（依赖次序），不是"必须是最后一个 script 标签"：2026-09-23 起末尾还有别的
    追加模块（`agent-question.js`）⇒ 以"最后一个"为判据会变成一碰就红的假钉子。
    """
    html = _INDEX.read_text(encoding="utf-8")
    assert '<script src="/app/js/plugins-settings.js"></script>' in html
    scripts = re.findall(r"<script src=\"([^\"]+)\"></script>", html.split("</body>")[0])
    mine = scripts.index("/app/js/plugins-settings.js")
    for earlier in ("/app/js/app.js", "/app/js/agent-panel.js"):
        assert scripts.index(earlier) < mine, f"{earlier} 必须在面板脚本之前"


def test_panel_styles_exist() -> None:
    """面板的类名在 `app.css` 里有落点（末尾追加块），且用的是既有令牌而不是硬编码颜色。"""
    css = _CSS.read_text(encoding="utf-8")
    block = css.rsplit("/* ===== 2026-09-22 追加：设置 →「能力」页签", 1)[1]
    for selector in (".-plugins-panel", ".-plugins-row", ".-plugins-switch", ".-plugins-src", ".-plugins-err"):
        assert selector in block, f"样式缺失：{selector}"
    assert "var(--bg-tertiary)" in block and "var(--accent-soft)" in block, "应复用既有主题令牌"


def test_panel_i18n_keys_exist_in_both_locales() -> None:
    """面板用到的每个键在**中英两份**语言包里都在（叶子名判定；中英缺一即裸 key）。"""
    src = _panel()
    used = set(re.findall(r'T\("(settings\.plugins\.[a-zA-Z]+)"\)', src))
    assert used == {"settings.plugins." + key for key in _PANEL_KEYS}, f"面板用到的键变了：{sorted(used)}"
    assert '"settings.plugins.source." + String(src || "")' in src, "来源标签按来源拼键"
    assert '"settings.plugins.param." + String(name)' in src, "参数标签按参数名拼键（见 `configHtml()`）"
    for locale, path in _LOCALES.items():
        text = path.read_text(encoding="utf-8")
        missing = [key for key in (*_PANEL_KEYS, *_SOURCE_KEYS, *_PARAM_KEYS) if f"{key}:" not in text]
        assert not missing, f"{locale} 缺键：{missing}"
        assert re.search(r"plugins:\s*\{", text), f"{locale} 缺 `settings.plugins` 子对象"
