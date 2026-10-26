"""task-170：分栏编辑时「预览重渲的 scroll 事件」不得反向同步源码区。

真机根因（pre-fix RED 证据见 artifacts/agent/verify/todo/split-mermaid-edit-scroll-before.json）：
源码编辑 → 预览整篇重渲：`renderPreview` 先清空 preview（浏览器把 preview scrollTop 夹到 0），
`_restorePreviewScrollAnchor` 再写回旧位置。这两次**程序化**滚动都会触发 scroll 事件，
`_onSplitPaneScroll("preview")` 误当用户滚动 ⇒ `_scrollToSrcLine("source", 预览顶行)`
把源码区拽到「当前块顶部」，每敲一个字重复一次。

本测试钉住修复的三条不变量（只做静态源码断言，真机行为由探针验证）：
1. 重渲窗口有显式计数 `_previewRenderInFlight`，且 `_onSplitPaneScroll` 在回声判消之前直接返回；
2. 计数在 `_renderPreviewKeepScroll` 进入时 +1、两帧后配对 -1（不用 boolean，防重入提前解除）；
3. 锚点恢复 / 漂移补偿这些程序化滚动都标记为 split 回声，避免被误判为用户滚动。
"""

from __future__ import annotations

from pathlib import Path

APP_JS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "memoria"
    / "ui"
    / "static"
    / "app"
    / "js"
    / "app.js"
)


def _src() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_split_scroll_sync_is_suppressed_during_preview_rerender() -> None:
    src = _src()
    assert "var _previewRenderInFlight = 0;" in src, "缺少重渲窗口计数"
    assert "_previewRenderInFlight++;" in src, "进入 _renderPreviewKeepScroll 必须 +1"
    assert "_previewRenderInFlight = Math.max(0, _previewRenderInFlight - 1);" in src, "两帧后必须配对递减"

    start = src.index("function _onSplitPaneScroll(")
    body = src[start : start + 900]
    assert "if (_previewRenderInFlight > 0) return;" in body, "重渲窗口内必须直接返回，不得反向同步"
    assert body.index("_previewRenderInFlight > 0") < body.index("_consumeSplitEcho("), (
        "守卫必须在回声判消之前；否则清空/恢复的 scroll 事件会先被当成一次回声消费掉，"
        "恢复位置的下一次事件仍会去拽源码区"
    )


def test_programmatic_preview_scroll_is_marked_as_echo() -> None:
    src = _src()
    # 锚点恢复：按元素/行号恢复与裸像素兜底两条路径都要标记
    assert 'try { _markSplitEcho("preview", pane); }' in src, "锚点恢复后必须标记 split 回声"
    # 漂移收敛（80/260/700/1500ms 的补偏移）也要标记
    assert 'try { _markSplitEcho("preview", pp); }' in src, "漂移补偿后必须标记 split 回声"
