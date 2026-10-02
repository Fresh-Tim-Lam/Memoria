/**
 * LegacySurface —— 显示子系统插头「legacy」：把现有实现映射到契约接口。
 *
 * 契约：docs/design/view-surface-contract.md
 *   §3.1 接口（宿主 → 引擎）：mount / setText / setMode / applyEdit / undo / redo /
 *         revealRange / getScrollAnchor / setScrollAnchor / getSrcRangeForSelection /
 *         isBlockFrozen / destroy / flush
 *   §3.2 宿主回调（引擎 → 宿主）：onTextChange / onCursorChange / onLinkActivate /
 *         onRevealRequest / onMeasure / onDegraded
 *   §3.3 时序（flush 清单 F1–F8）
 *   §3.4 冻结规则
 *   §4.3 capabilities
 *
 * 定位：**薄适配器** —— 不重写任何渲染 / 编辑逻辑，全部委托给现有全局入口：
 *   · window.MemoriaApp         —— 门面（state / renderEditor / renderPreview / openFile）
 *   · window.MemoriaEditSync    —— 编辑事务（insertText / backspace / deleteForward /
 *                                  splitParagraph / deleteSelection / undo / redo / flushRepaint）
 *   · window.MemoriaEditHandler —— 编辑态（cursorAST / blockEditMode / _captionEditingEl / _composing）
 *   · window.MemoriaMapper      —— 坐标映射（domToAst / astToSrc）
 *
 * 如实声明（本刀范围；以下均为「查得到的事实」，不是猜测）：
 *   1) app.js 的 `setViewMode` / `collectEditorBody` / `highlightRange` / `highlightPreviewRange` /
 *      `_getViewTopSrcLine` / `_scrollToSrcLine` **都是主 IIFE 内的闭包、未挂到 `window.MemoriaApp` 门面**
 *      ⇒ 适配器改用**等价的真实入口**（视图按钮点击 = 真实用户路径）或**就地读 DOM**。
 *      `getScrollAnchor` / `setScrollAnchor` 的 DOM 读数**镜像** app.js:1690 `_getViewTopSrcLine` /
 *      app.js:1717 `_scrollToSrcLine`（零行漂移纪律下无法从门面取到这两处闭包）。若 app.js 那两处改了，
 *      这里需同步。
 *   2) `MemoriaEditSync` 只导出 insertText / flushRepaint / backspace / deleteForward / splitParagraph /
 *      revertBlock / applyStyle / getSelectionStyles / deleteSelection / beginUndoGroup / endUndoGroup /
 *      undo / redo / resetHistory；**commit / commitRange / commitSelection 未导出**（内部闭包）。
 *   3) `revealRange`：legacy 真正的「跳转落点」是闭包 `highlightRange`（band + flash + 二次校准），
 *      门面取不到 ⇒ 适配器只能做到**滚动到位**（不画 band、不闪、不做二次校准）。这是能力缺口，如实标注。
 *   4) 冻结判定 `isBlockFrozen` 用现有可查的编辑态实现；查不到的（如 caption 不落在任何块上）**保守返回 true**。
 */
window.createLegacySurface = function createLegacySurface(deps) {
  "use strict";
  deps = deps || {};

  var _container = deps.container || null;
  var _host = deps.host || null;
  var _mounted = false;

  function _app() { return window.MemoriaApp; }
  function _st() { return window.state; }
  function _es() { return window.MemoriaEditSync; }
  function _eh() { return window.MemoriaEditHandler; }
  function _M() { return window.MemoriaMapper; }

  function _hostObj() {
    return _host || (window.MemoriaSurface && window.MemoriaSurface.host) || null;
  }
  /** 回调宿主（§3.2）。宿主回调异常不得影响引擎。 */
  function _callHost(name, a, b) {
    var h = _hostObj();
    var fn = h && h[name];
    if (typeof fn === "function") { try { return fn(a, b); } catch (e) { /* 宿主侧异常吞掉 */ } }
  }

  /** F1–F7：读真源 / 换视图 / 销毁前先落定「停手才渲」的那一块（AG103 `flushRepaint`）。 */
  function _settle() {
    var es = _es();
    if (es && typeof es.flushRepaint === "function") { try { es.flushRepaint(); } catch (e) { /* noop */ } }
  }

  function _currentText() {
    var s = _st();
    return (s && s.doc && typeof s.doc.body === "string") ? s.doc.body : null;
  }

  // ── 滚动锚点的 DOM 读数（镜像 app.js:1690 / 1717，见文件头「如实声明 1)」）────────────
  function _topSrcLine(mode) {
    var editorPane = document.getElementById("editor-pane");
    var previewPane = document.getElementById("preview-pane");
    if ((mode === "source" || mode === "split") && editorPane) {
      var ct = editorPane.getBoundingClientRect().top;
      var lines = editorPane.querySelectorAll(".-line");
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].getBoundingClientRect().bottom >= ct) return +(lines[i].dataset.line || 0) || null;
      }
    }
    if ((mode === "preview" || mode === "split") && previewPane) {
      var pt = previewPane.getBoundingClientRect().top;
      var blocks = previewPane.querySelectorAll("[data--src-line]");
      for (var j = 0; j < blocks.length; j++) {
        if (blocks[j].getBoundingClientRect().bottom >= pt) return +(blocks[j].dataset.SrcLine || 0) || null;
      }
    }
    return null;
  }

  function _scrollToSrcLine(mode, lineNum) {
    if (!lineNum) return false;
    var editorPane = document.getElementById("editor-pane");
    var previewPane = document.getElementById("preview-pane");
    if ((mode === "source" || mode === "split") && editorPane) {
      var el = document.getElementById("line-" + lineNum);
      if (el) { editorPane.scrollTop += el.getBoundingClientRect().top - editorPane.getBoundingClientRect().top; return true; }
    }
    if ((mode === "preview" || mode === "split") && previewPane) {
      var blocks = previewPane.querySelectorAll("[data--src-line]");
      var target = null;
      for (var i = 0; i < blocks.length; i++) {
        var s = +(blocks[i].dataset.SrcLine || 0);
        var e = +(blocks[i].dataset.SrcLineEnd || s);
        if (s <= lineNum && e >= lineNum) { target = blocks[i]; break; }
        if (s >= lineNum && !target) target = blocks[i];
      }
      if (target) { previewPane.scrollTop += target.getBoundingClientRect().top - previewPane.getBoundingClientRect().top; return true; }
    }
    return false;
  }

  var api = {
    // ── §4.3 能力声明（按事实）──────────────────────────────────────────────
    // virtualization:false —— K4a 窗口化已整体回退（app.js:1645 / 1474 AG97），预览是整篇真 DOM。
    // incrementalRender:false —— 尽管有**单块**增量重渲（`reRenderBlock`），但契约 §4.3 指的是「块级复用」
    //   （跨整篇渲染复用同一批块节点）；legacy 整篇渲染是**全量重建**、无 reconciler ⇒ 按契约口径为 false。
    // blockEdit:true —— 有块编辑（edit-handler `enterBlockEditMode`：代码/公式/表格/mermaid）。
    // imageCaption:true —— 有图片 caption 编辑（edit-handler `_captionEditingEl`）。
    // findInPage:'native' —— 找页内命中走浏览器原生（legacy 未自建视口化搜索）。
    capabilities: {
      virtualization: false,
      incrementalRender: false,
      blockEdit: true,
      imageCaption: true,
      findInPage: "native",
    },

    /** §3.1 生命周期：宿主提供 container，引擎接管其内容。
     *  legacy 例外：`#editor-split` / `#preview` 的 DOM 生命期归 app.js ⇒ 适配器**只记录、不接管、不重建**。 */
    mount: function (container, host) {
      if (container) _container = container;
      if (host) _host = host;
      _mounted = true;
    },

    /** §3.1 设置整篇文本（cause ∈ open | switch | reload | external）。F6：先落定。 */
    setText: function (text, cause) {
      _settle();
      var s = _st();
      if (!s || !s.doc) return;
      var body = (text == null) ? "" : String(text);
      s.doc.body = body;
      s.doc.lines = body.split("\n");
      s.doc.preview_body = null;   // 正文变了 ⇒ 预览缓存作废
      var A = _app();
      if (A && typeof A.renderEditor === "function") A.renderEditor(s.doc);
      if (A && typeof A.renderPreview === "function") return A.renderPreview(s.doc);
      _callHost("onTextChange", body, cause || "external");
    },

    /** §3.1 视图模式（source | split | preview）。F6：先落定。 */
    setMode: function (mode) {
      _settle();
      var s = _st();
      if (!s || !mode) return;
      if (s.viewMode === mode) return;   // 已是该模式 ⇒ 空操作（setViewMode 同模式也会重渲，避免多余）
      // 委托真实用户入口：视图按钮的 click 处理器即 `setViewMode(btn.dataset.view)`（app.js:12667）
      var btn = document.querySelector('.-view-btn[data-view="' + mode + '"]');
      if (btn) { btn.click(); return; }
      _callHost("onDegraded", "setMode:no-entry");
    },

    /** §3.1 唯一内容变更入口（EditOp）。F1：先落定。legacy 的编辑是**光标驱动**的，op.at 的任意定位能力有限。 */
    applyEdit: function (op) {
      if (!op || !op.kind) return false;
      _settle();
      var es = _es();
      if (!es) return false;
      switch (op.kind) {
        case "insertText":
          if (typeof es.insertText !== "function") return false;
          return es.insertText(op.text || "");
        case "splitBlock":
          return typeof es.splitParagraph === "function" ? es.splitParagraph() : false;
        case "mergeBlock":
          return typeof es.backspace === "function" ? es.backspace() : false;
        case "deleteRange":
        case "replaceRange":
          // legacy 的范围删除入口 `deleteSelection(range)` 需要**浏览器 Range**（不是文本坐标），
          // 且 commitRange 未导出 ⇒ 契约的文本坐标 op 在此无法无损映射；如实返回 false。
          return false;
        default:
          return false;
      }
    },

    /** §3.1 撤销 / 重做。F2：快照语义，先落定。 */
    undo: function () { _settle(); var es = _es(); return es && typeof es.undo === "function" ? es.undo() : false; },
    redo: function () { _settle(); var es = _es(); return es && typeof es.redo === "function" ? es.redo() : false; },

    /** §3.1 跳转落点。F5：先落定。
     *  ⚠️ 能力缺口（见文件头 3)）：真正的 `highlightRange` 是闭包、门面取不到 ⇒ 这里只做**滚动到位**
     *  （不画 band、不闪、不做 AG104 的二次校准）。 */
    revealRange: function (startLine, endLine, opts) {
      _settle();
      var s = _st();
      if (!s || !s.doc || startLine == null) return;
      var mode = s.viewMode || "preview";
      if (opts && opts.scroll === false) return;
      _scrollToSrcLine(mode === "preview" ? "preview" : mode, startLine);
    },

    /** §3.1 取滚动锚点（切模式 / 换文件时取）。F4：先落定。 */
    getScrollAnchor: function () {
      _settle();
      var s = _st();
      var mode = s ? s.viewMode : null;
      return { mode: mode, srcLine: _topSrcLine(mode) };
    },

    /** §3.1 设滚动锚点。F4：先落定。 */
    setScrollAnchor: function (a) {
      _settle();
      if (!a || a.srcLine == null) return;
      var s = _st();
      var mode = a.mode || (s ? s.viewMode : null);
      _scrollToSrcLine(mode, a.srcLine);
    },

    /** §3.1 选区 → 源码坐标。F3：返回坐标必须与真源一致 ⇒ 先落定。
     *  返回 { startLine, startCol, endLine, endCol, collapsed }（行号 **1-based**，与 revealRange/data--src-line 一致）。 */
    getSrcRangeForSelection: function () {
      _settle();
      var s = _st();
      var M = _M();
      var sel = window.getSelection && window.getSelection();
      if (!s || !s.doc || !M || !sel || sel.rangeCount === 0) return null;
      var r = sel.getRangeAt(0);
      var a = M.domToAst(r.startContainer, r.startOffset);
      var b = M.domToAst(r.endContainer, r.endOffset);
      if (!a || !b || a.blockIndex < 0 || b.blockIndex < 0) return null;
      var sa = M.astToSrc(a.blockIndex, a.nodePath || [], a.offset || 0);
      var sb = M.astToSrc(b.blockIndex, b.nodePath || [], b.offset || 0);
      if (!sa || !sb) return null;
      return {
        startLine: sa.line + 1, startCol: sa.col,
        endLine: sb.line + 1, endCol: sb.col,
        collapsed: !!sel.isCollapsed,
      };
    },

    /** §3.4 冻结规则：正在块编辑 ‖ 正在图片 caption 编辑 ‖ IME 组合中且光标在此块 ‖ 非折叠选区跨过此块。
     *  blockId 在 legacy = `data--block-index`（位置下标；legacy 无稳定块 id，见基线 C1「未测」）。 */
    isBlockFrozen: function (blockId) {
      var eh = _eh();
      if (!eh) return false;
      // ① 正在块编辑
      if (eh.blockEditMode && eh.blockEditMode.blockIndex === blockId) return true;
      // ② 正在图片 caption 编辑：legacy 的 caption 编辑态是**全局**的 `_captionEditingEl`（不直接带 blockId）；
      //    能定位到所属块就按块比对，定位不到 ⇒ 保守返回 true（宁可冻结，也不重建正在编辑的节点）。
      if (eh._captionEditingEl) {
        var el = eh._captionEditingEl;
        var blk = el && el.closest ? el.closest(".-src-block") : null;
        var bi = blk ? parseInt(blk.getAttribute("data--block-index"), 10) : NaN;
        if (!isFinite(bi) || bi === blockId) return true;
      }
      // ③ IME 组合中且光标在此块
      if (eh._composing && eh.cursorAST && eh.cursorAST.blockIndex === blockId) return true;
      // ④ 非折叠选区跨过此块
      var sel = window.getSelection && window.getSelection();
      if (sel && !sel.isCollapsed) {
        var M = _M();
        if (!M) return true;   // 有非折叠选区但拿不到映射器 ⇒ 保守
        var a = M.domToAst(sel.anchorNode, sel.anchorOffset);
        var f = M.domToAst(sel.focusNode, sel.focusOffset);
        if (!a || !f) return true;   // 选区在预览块之外、映射不到 ⇒ 保守
        var lo = Math.min(a.blockIndex, f.blockIndex);
        var hi = Math.max(a.blockIndex, f.blockIndex);
        if (lo <= blockId && blockId <= hi) return true;
      }
      return false;
    },

    /** §3.1 销毁。F7：先落定（否则丢字）。
     *  legacy 不摘除 DOM（`#editor-split` / `#preview` 归 app.js），只清本适配器的本地引用。 */
    destroy: function () {
      _settle();
      _mounted = false;
    },

    /** §3.3 / §4.2：落定未落定变更，并返回交接包 { text, cursor, anchor, mode, frozen }。 */
    flush: function () {
      _settle();
      var s = _st();
      return {
        text: _currentText(),
        cursor: api.getSrcRangeForSelection(),
        anchor: api.getScrollAnchor(),
        mode: s ? s.viewMode : null,
        // legacy 无稳定块 id；冻结按需由 isBlockFrozen() 判定（§3.4），不做预计算
        frozen: null,
      };
    },
  };

  return api;
};
