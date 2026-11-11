"""task-2026-11-11：应用级加载蒙层 + 窗口恢复加载样式的结构回归。

人反馈：
  · 程序窗口加载机制没有模块化；
  · 打开应用 / 新窗口 / 最小化到点开，凡是加载行为都要有加载样式；
  · 只要还有东西在加载，蒙版不能撤。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "js"
CSS = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "css" / "app.css"
INDEX = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "index.html"
APP = JS / "app.js"


def test_loading_overlay_module_exists_with_ref_count_api() -> None:
    src = (JS / "loading-overlay.js").read_text(encoding="utf-8")
    for name in ("begin", "end", "track", "isBusy", "count"):
        assert name in src, f"loading-overlay 缺 API: {name}"
    assert "tasks.size > 0" in src
    assert "tasks.size ==" in src or "tasks.size > 0" in src
    assert "root.hidden = !busy" in src
    # 不允许按时间自动撤：模块中没有“时间到了就隐藏”的计时器
    assert "CAP_MS" not in src
    assert "setTimeout" not in src
    # 2026-11-11：加载蒙层视觉 = 程序化星场「星穹帷幕 / Astral Veil」，不是静态关键帧
    assert "Astral Veil" in src and "星穹帷幕" in src
    assert "requestAnimationFrame(skyLoop)" in src
    assert "seedStars" in src
    assert "skyStars" in src
    assert "canvas" in src
    # 人反馈：不要悬浮加载卡片；中心是 Memoria 图标 + 艺术字 + 心跳
    assert "-memoria-loading__card" not in src
    assert "-memoria-loading__stage" in src
    assert "Memoria.png" in src
    assert "-memoria-loading__word" in src
    assert "setKnowledgeProfile" in src
    assert "seedNebulae" in src


def test_loading_overlay_is_loaded_before_app_and_styled_by_theme() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert html.index("loading-overlay.js") < html.index("app.js")
    css = CSS.read_text(encoding="utf-8")
    assert ".-memoria-loading" in css
    assert ".-memoria-loading[hidden]" in css
    assert ".-memoria-loading__sky" in css
    assert ".-memoria-loading__stage" in css
    assert ".-memoria-loading__logo" in css
    assert ".-memoria-loading__word" in css
    assert "memoria-boot-pulse" in css
    assert "var(--theme-color" in css
    assert "var(--bg-secondary)" in css
    # 2026-11-11：底色必须与编辑器/预览区一致（同为 --bg-primary），不能再叠径向渐变
    assert "html[data-theme=\"light\"] .-memoria-loading" in css
    assert "background: var(--bg-primary);" in css


def test_boot_and_restore_paths_hold_the_mask_until_init_finishes() -> None:
    src = APP.read_text(encoding="utf-8")
    assert "window.__memoriaBootLoadingToken" in src
    assert "function finishBootLoading" in src
    assert "finishBootLoading();" in src
    assert "loadingText(\"app.loadingStage.startup\"" in src
    assert "loadingText(\"app.loadingStage.restoring\"" in src
    assert "document.addEventListener(\"visibilitychange\"" in src
    # 启动/恢复都必须走同一个引用计数层，不允许再各自 setTimeout 隐藏
    assert "MemoriaLoading.begin(" in src
    assert "MemoriaLoading.end(" in src
    # 2026-11-11：必须等 agent 面板可发送才释放 boot token
    assert "memoria:agent-ready" in src
    assert "window.__memoriaAgentReady" in src


def test_agent_panel_reports_ready_after_config_and_history() -> None:
    src = (JS / "agent-panel.js").read_text(encoding="utf-8")
    assert "window.__memoriaAgentReady = false" in src
    assert "memoria:agent-ready" in src
    assert "Promise.allSettled([configReady, historyReady])" in src
    assert "refreshConfig()" in src
    assert "restoreLastSession()" in src


def test_loading_labels_exist_in_both_locales() -> None:
    for name in ("zh-CN.js", "en.js"):
        text = (ROOT / "src" / "memoria" / "ui" / "static" / "app" / "i18n" / name).read_text(encoding="utf-8")
        assert "startup:" in text and "restoring:" in text
        assert "app.loading" not in text  # 键名在 app.loading 下，不写成扁平字符串


def test_agent_panel_recovers_stale_busy_job_after_reconnect() -> None:
    src = (JS / "agent-panel.js").read_text(encoding="utf-8")
    assert "res.code === \"busy\"" in src
    assert "agent_ask_cancel" in src
    assert "本面板不知道的旧作业" in src


def test_long_session_window_and_load_earlier() -> None:
    src = (JS / "agent-panel.js").read_text(encoding="utf-8")
    assert "INITIAL_RENDER_MESSAGES" in src
    assert "LOAD_EARLIER_MESSAGES" in src
    assert "renderStart" in src
    assert "className = \"-agent-load-earlier\"" in src
    assert "renderMessages({ keepScroll: true })" in src
    assert "renderedMessages()" in src
    assert "renderedTurnOffset()" in src
    css = CSS.read_text(encoding="utf-8")
    assert ".-agent-load-earlier {" in css


def test_turn_rail_is_positioned_as_a_minimap_not_equal_spacing() -> None:
    src = (JS / "agent-panel.js").read_text(encoding="utf-8")
    assert "function layoutTurnMarks" in src
    assert "Math.pow(index / (count - 1), 1.75)" in src
    assert "RAIL_WINDOW_TURNS" in src
    assert "moveRailWindow" in src
    assert "\"wheel\"" in src
    assert "mark.style.top" in src
    # 不设原生 title；悬停用主题化预览浮层
    assert "mark.title =" not in src
    css = CSS.read_text(encoding="utf-8")
    assert ".-agent-turn-mark {\n    position: absolute;" in css
    assert ".-agent-turn-preview {" in css
    assert "border-radius: 12px;" in css
    # 2026-11-11：滚条与定位条必须分侧——滚条在右，定位条在左
    assert ".-agent-stream > .-agent-messages {\n    padding-left: 48px;" in css
    assert ".-agent-turn-rail {\n    left: 4px;" in css
    assert ".-agent-turn-preview {\n    left: 34px;" in css
