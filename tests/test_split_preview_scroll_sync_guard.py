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


def test_switch_to_split_restore_is_locked_and_marked_as_echo() -> None:
    """E36：切到分栏时两侧的程序化滚动不得被 split 同步监听反向顶回。"""
    src = _src()
    start = src.index("async function setViewMode(")
    end = src.index("function _getViewTopSrcLine(", start)
    body = src[start:end]
    assert "splitSyncLock = true;" in body, "切分栏恢复前必须加 split 同步锁"
    assert '_markSplitEcho("source", $("#editor-pane"));' in body, "源码侧恢复后必须标回声"
    assert '_markSplitEcho("preview", $("#preview-pane"));' in body, "预览侧恢复后必须标回声"
    assert "setTimeout(() => { splitSyncLock = false; }, 0);" in body, "恢复后必须解锁"


def test_e36_switch_uses_precise_line_plus_offset_anchor() -> None:
    """E36：切分栏不能只恢复「块起始行」，必须保留顶部行/块内偏移。

    真机 CDP（本测试只做静态 pin）：preview 滚到 32 行代码块中间 400px 处切分栏，
    旧实现跳回块首 399.9px；source→split 两侧相差 15 行。行为证据见
    artifacts/agent/verify/todo/e36-split-view-drift/README.md。
    """
    src = _src()
    assert "function _captureViewAnchor(" in src, "必须新增精确锚点采集"
    assert "offset: r.top - containerTop" in src, "源码锚点必须带行内像素偏移"
    assert 'blockIndex: block.getAttribute("data--block-index")' in src, "预览锚点必须记块下标"
    assert "function _scrollToViewAnchor(" in src, "必须新增精确锚点恢复"
    assert "targetTop = anchor.offset || 0;" in src, "来源侧必须按像素偏移精确回位"
    assert "targetTop = -frac * r.height;" in src, "另一侧必须按同一源码行比例对齐（不是块首）"

    start = src.index("async function setViewMode(")
    end = src.index("function _getViewTopSrcLine(", start)
    body = src[start:end]
    assert '_captureViewAnchor(prevMode === "split" ? mode : prevMode)' in body, (
        "切视图前必须采集精确锚点；从分栏回单视图时取即将保留的一侧"
    )
    assert '_scrollToViewAnchor(_viewAnchorBeforeRerender, "split")' in body, (
        "切分栏必须走精确锚点恢复"
    )
    assert '_scrollToSrcLine("source", anchorLine)' not in body, "不得再按块起始行恢复源码侧"
    assert '_scrollToSrcLine("preview", anchorLine)' not in body, "不得再按块起始行恢复预览侧"


def test_e36_reanchor_after_layout_settles_and_boundary_fix() -> None:
    """E36：宽度重排/惰性物化/MathJax 晚几拍改高度时要补锚点；顶行判定不得回退一行。"""
    src = _src()
    start = src.index("async function setViewMode(")
    end = src.index("function _getViewTopSrcLine(", start)
    body = src[start:end]
    assert '_scheduleViewAnchorReanchor(_viewAnchorBeforeRerender, "split")' in body, (
        "切分栏后必须在稳定点补锚点"
    )
    assert '_scheduleViewAnchorReanchor(_viewAnchorBeforeRerender, "preview")' in body, (
        "切回单预览后同样要补锚点（整篇重渲 + 惰性物化）"
    )
    assert 'if (mode !== "split") _viewAnchorSeq++;' in src, "离开分栏必须作废旧锚点定时器"
    assert "if (state.viewMode !== targetMode) return;" in src, "补锚点不得跨模式生效"
    assert "r.bottom > containerTop + 0.5" in src, "顶行判定必须排除恰好贴视口顶的上一行"


def test_e36_split_echo_has_per_pane_slots() -> None:
    """E36：切分栏时两侧同一拍各归位一次，回声槽必须按 mode 分开，否则后一次覆盖前一次。"""
    src = _src()
    assert "let splitEcho = { source: null, preview: null };" in src
    assert "splitEcho[mode] = { top: pane.scrollTop" in src
    assert "const echo = splitEcho[mode];" in src
