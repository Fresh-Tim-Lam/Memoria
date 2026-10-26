"""task-169 回归守卫：输入框显式高度把手 + 上下文圆环移到输入框下方。

人原话：
  「会话输入框只需要调整高，因为宽是自适应」
  「上下文占用的样式不要显示在底栏，应该显示在输入框底下」

真机证据（行为层）：
  artifacts/agent/verify/todo/agent-composer-resize-ctxring/verify.json
  · 原生 resize 已去掉；把手存在且只改高度；高度写盘并在重启后生效
  · 圆环四态在输入框下方逐一验证；底栏不再有环；底栏 token 口径仍在

本测试是**结构回归**（锁不变量，替代会过期字面量的弱断言）：
  ① CSS：`.-agent-input` 不再 `resize: vertical`；把手/圆环行样式存在；
  ② JS：setupComposerResize 接线；pointer capture；高度夹紧 + 写盘键；
  ③ 圆环宿主 = `.-agent-composer` 内、输入框下方；不再 append 到 `#status-bar`；
  ④ i18n 中英均有把手提示键。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "js" / "agent-panel.js"
CSS = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "css" / "app.css"
ZH = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "i18n" / "zh-CN.js"
EN = ROOT / "src" / "memoria" / "ui" / "static" / "app" / "i18n" / "en.js"


def _panel() -> str:
    return PANEL.read_text(encoding="utf-8")


def test_native_textarea_resize_is_removed_and_handle_styles_exist():
    css = CSS.read_text(encoding="utf-8")
    # 原生 resize 小把手必须已去掉（人：「只调高，宽自适应」）
    assert "resize: vertical" not in css[css.index(".-agent-input {"): css.index(".-agent-input:focus")], (
        "task-169 回归：.-agent-input 仍有原生 resize"
    )
    assert "resize: none" in css
    # 显式把手与圆环行样式存在
    assert ".-agent-input-resize {" in css
    assert ".-agent-ctx-ring-row {" in css
    assert "#agent-ctx-ring {" in css
    # 底栏旧环被隐藏，避免双环残留
    assert "#status-bar #status-ctx-ring {" in css


def test_composer_resize_is_wired_and_persisted_via_ui_settings():
    src = _panel()
    # 接线：init 里调用；把手惰性创建；只调高（宽度不写）
    assert "setupComposerResize();" in src
    assert 'handle.id = "agent-input-resize";' in src
    assert "composer.insertBefore(handle, input.nextSibling);" in src
    # 拖拽跟手（指针移出/出窗口仍继续）
    assert "setPointerCapture(e.pointerId)" in src
    # 只写 height，且夹在 min-height ~ 60% 视口
    assert 'input.style.height = h + "px";' in src
    assert "COMPOSER_HEIGHT_MAX_RATIO = 0.6" in src
    # 持久化走 ui_settings 的 agent 段（统一入口；不碰 layout）
    assert "composerHeightPx" in src
    assert 'call("save_ui_settings", { agent: agent })' in src
    # 键盘可访问
    assert '"ArrowUp"' in src and '"ArrowDown"' in src


def test_context_ring_moves_under_input_not_status_bar():
    src = _panel()
    block = src[src.index("function renderContextRing"): src.index("function systemRowText")]
    # 宿主 = composer 内、输入框下方的一行
    assert 'document.querySelector(".-agent-composer")' in block
    assert 'document.getElementById("agent-ctx-ring-row")' in block
    assert 'composer.insertBefore(row, actions)' in block
    # 不再挂到 #status-bar；旧 id 只用于“移除残留”，绝不用于创建
    assert "bar.appendChild(host)" not in block
    assert 'host.id = "status-ctx-ring"' not in block
    assert 'document.getElementById("status-ctx-ring")' in block  # 只作为 legacy 清理
    # 四态语义全在（未知 / chars÷chars / over / 已压缩 N 次）
    assert "compactRingUnknown" in block
    assert "view.percent" in block and "view.chars" in block and "view.max" in block
    assert "view.over" in block
    assert "view.times > 0" in block and "compactTimes" in block


def test_composer_handle_i18n_present_in_both_languages():
    for path in (ZH, EN):
        text = path.read_text(encoding="utf-8")
        assert "resizeHint:" in text, f"{path.name} 缺 agent.input.resizeHint"
        assert "agent.input" in text
