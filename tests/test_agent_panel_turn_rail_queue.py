"""Agent 面板：侧边轮次导航（DSH TurnNavigator）+ 待发送队列（DSH QueueDock）的回归钉子。

移植范围（2026-11-10）：
- 右侧固定刻度栏：每个用户轮次一个 mark；点击滚到该轮；悬停/聚焦出 prompt+回答预览；
  当前视口轮次高亮。由 `ensureAgentChrome()` 动态建 DOM ⇒ `index.html` 行号锚点零漂移。
- composer 上方待发送队列：生成中再发送 = 入队；可编辑/删除/打断当前回答并发送；
  当前回答结束后自动 drain 下一条。

本文件只钉**接线**（源码级）与 i18n 键；真机行为由 CDP 探针覆盖。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "memoria" / "ui" / "static" / "app"
PANEL = APP / "js" / "agent-panel.js"
CSS = APP / "css" / "app.css"


def _panel() -> str:
    return PANEL.read_text(encoding="utf-8")


def test_turn_rail_is_wired_to_messages_and_user_turns() -> None:
    src = _panel()
    assert "function ensureAgentChrome(" in src
    assert "function renderTurnRail(" in src
    assert "function scrollToTurn(" in src
    assert 'data-agent-turn="' in src or "setAttribute(\"data-agent-turn\"" in src
    assert "renderTurnRail();" in src
    # 当前轮高亮必须在滚动事件上更新，不能只画一次
    assert 'box.addEventListener("scroll", updateTurnRailActive' in src
    assert "function updateTurnRailActive(" in src
    # 至少两轮才显示（单轮没有导航价值）
    assert "turns.length < 2" in src


def test_queue_queues_while_busy_and_drains_after_finish() -> None:
    src = _panel()
    assert "const pendingQueue = [];" in src
    assert "function enqueueText(" in src
    assert "function drainQueue(" in src
    assert "function renderQueue(" in src
    assert "function steerQueueItem(" in src
    # busy 时 ask() 进队列而不是丢弃
    assert "if (busy) {" in src and "enqueueText(text)" in src
    # 生成中不得禁用发送键（否则无法入队）
    assert "send.disabled = !cfg.enabled;" in src
    # 结束后自动发送下一条
    assert "drainQueue();" in src
    # 队列项保留 tool 协议之外的纯文本；编辑/删除/打断按钮存在
    assert "agent-queue-actions" in src


def test_turn_rail_and_queue_styles_and_i18n_exist() -> None:
    css = CSS.read_text(encoding="utf-8")
    for selector in (
        ".-agent-stream",
        ".-agent-turn-rail",
        ".-agent-turn-mark",
        ".-agent-turn-preview",
        ".-agent-queue",
        ".-agent-queue-row",
        ".-agent-session-footer",
        "#agent-send.-agent-send-btn",
        "#agent-stop.-agent-stop-btn",
    ):
        assert selector in css, f"缺少样式 {selector}"
    zh = (APP / "i18n" / "zh-CN.js").read_text(encoding="utf-8")
    en = (APP / "i18n" / "en.js").read_text(encoding="utf-8")
    for key in ("turnRail", "queue"):
        assert f"    {key}:" in zh, f"zh-CN 缺少 agent.{key}"
        assert f"    {key}:" in en, f"en 缺少 agent.{key}"
    assert "label: \"对话轮次导航\"" in zh
    assert "count: \"{n} 条待发送\"" in zh


def test_dsh_composer_bubble_and_session_footer_are_wired() -> None:
    src = _panel()
    assert "function ensureDshComposer(" in src
    assert "function ensureAgentSessionFooter(" in src
    assert 'id = "agent-session-footer"' in src
    assert 'footer.appendChild(statusbar)' in src
    assert 'footer.appendChild(statusAgent)' in src
    assert "M8.3125 0.980183" in src
    assert 'rect x="4" y="3"' in src and 'rect x="9" y="3"' in src
    status_usage = src.split("function renderStatusUsage(", 1)[1].split("\n  }", 1)[0]
    assert "spanCache" not in status_usage
    assert "agent-session-footer" in src
    assert "renderContextRing" in src
