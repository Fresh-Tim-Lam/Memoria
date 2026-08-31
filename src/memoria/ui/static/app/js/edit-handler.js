/**
 * Memoria Edit Handler
 * 预览区编辑交互：光标点击映射、方向键、输入、删除、回车
 *
 * 依赖：app.js (log, state, ts, _logBuf, _scheduleFlush)
 *      MemoriaMapper (M = window.MemoriaMapper)
 */
;(function () {
  "use strict";

  var EH = window.MemoriaEditHandler = {};

  // ════════════════════════════════════════════════════════════════
  //  文件日志系统 — 输出到 d:\AAA_Jupyter\Memoria\logs\block-skip-debug.log
  // ════════════════════════════════════════════════════════════════
  var _flogBuf = [];
  var _flogTimer = null;
  var _flogSeq = 0;

  function _fts() {
    var d = new Date();
    return "[" + String(d.getHours()).padStart(2, "0") + ":" +
      String(d.getMinutes()).padStart(2, "0") + ":" +
      String(d.getSeconds()).padStart(2, "0") + "." +
      String(d.getMilliseconds()).padStart(3, "0") + "]";
  }

  function flog(tag, msg) {
    _flogSeq++;
    var line = _fts() + " #" + _flogSeq + " [" + tag + "] " + msg;
    _flogBuf.push(line);
    if (_flogTimer) clearTimeout(_flogTimer);
    _flogTimer = setTimeout(_flogFlush, 200);
  }

  function _flogFlush() {
    if (_flogTimer) { clearTimeout(_flogTimer); _flogTimer = null; }
    if (!_flogBuf.length) return;
    var content = _flogBuf.join("\n") + "\n";
    _flogBuf = [];
    try {
      var api = window.memoria && window.memoria.api;
      if (api && api.write_debug_log) {
        api.write_debug_log("block-skip-debug.log", content);
      }
    } catch (e) { /* ignore */ }
  }

  window.addEventListener("beforeunload", function () { _flogFlush(); });
  window.flog = flog;

  // ── 编辑模式（默认开启）──
  EH.editMode = true;

  /**
   * 编辑光标是否真实位于预览区（闪烁光标）
   * 由事件驱动显式维护（focusin / 预览区 mouseup / 模式切换 / 文件切换），
   * 不依赖实时读取 selection —— 切换文件/重渲染后 selection 可能残留旧位置，
   * 实时快照不可控，显式状态机才可靠。
   */
  EH._caretInPreview = false;

  /** 切换编辑模式，更新按钮 UI */
  EH.toggleEditMode = function () {
    EH.editMode = !EH.editMode;
    var btn = document.getElementById("btn-edit-mode");
    if (btn) btn.classList.toggle("active", EH.editMode);
    var sw = document.getElementById("edit-mode-toggle");
    if (sw) {
      sw.setAttribute("aria-checked", EH.editMode ? "true" : "false");
      sw.title = EH.editMode ? "编辑模式：点击定位光标（再次点击关闭）" : "浏览模式：点击链接（再次点击开启编辑）";
    }
    // 控制预览区 contentEditable：OFF 时链接可点击跳转
    var preview = document.getElementById("preview");
    if (preview) {
      preview.contentEditable = EH.editMode ? "true" : "false";
    }
    // 编辑模式关闭 → 预览区无"闪烁光标"概念，图片插入按钮必须立即禁用
    // （selection 仍可能停留在预览区，selectionchange 不会因此触发，需在此主动禁用）
    if (!EH.editMode) {
      EH._caretInPreview = false;
      var imgBtn = document.getElementById("btn-insert-image");
      if (imgBtn) imgBtn.disabled = true;
    } else {
      // 开启编辑模式：焦点若已落在预览区则视为有编辑光标，否则无
      EH._caretInPreview = !!(document.activeElement &&
        document.activeElement.closest && document.activeElement.closest("#preview"));
    }
  };

  // ── 预览区光标位置缓存（源码坐标）──
  EH.currentCursor = null;  // { srcLine, srcCol, blockIndex }
  EH.cursorAST = null;      // { blockIndex, nodePath, offset } — 预览区编辑锚点
  EH._composing = false;      // 是否处于 IME 组合输入中
  EH._composeStartAST = null; // 组合输入起始 AST 锚点（组合期间 DOM 会被污染，仅以此为准）

  // ── 源码区假光标 ──
  var _fakeCursorEl = null;

  // ── 预览区光标指示（源码→预览方向）──
  var _previewCursorBlock = null;

  function hidePreviewCursor() {
    if (_previewCursorBlock) {
      _previewCursorBlock.classList.remove("-preview-cursor");
      _previewCursorBlock = null;
    }
  }

  /**
   * 在预览区显示光标指示（源码→预览方向）
   * 不可编辑 block（代码块/数学块/表格/Mermaid/frontmatter）不显示光标
   * @param {number} srcLine — 1-based 源码行号
   */
  function showPreviewCursor(srcLine) {
    hidePreviewCursor();

    // 查找源码行对应的预览 block
    var blocks = document.querySelectorAll('.-src-block[data--src-line]');
    var targetBlock = null;
    for (var i = 0; i < blocks.length; i++) {
      var s = parseInt(blocks[i].getAttribute("data--src-line"), 10);
      var e = parseInt(blocks[i].getAttribute("data--src-line-end"), 10) || s;
      if (srcLine >= s && srcLine <= e) {
        targetBlock = blocks[i];
        break;
      }
    }
    if (!targetBlock) return;

    // 不可编辑 block：不显示光标
    var blockIdx = parseInt(targetBlock.getAttribute("data--block-index"), 10);
    if (isNonEditableBlock(blockIdx)) return;

    // 可编辑 block：添加光标指示
    targetBlock.classList.add("-preview-cursor");
    _previewCursorBlock = targetBlock;
  }

  /**
   * 获取源码编辑器中当前光标所在行号
   * @returns {number} 1-based 行号，-1 表示无效
   */
  function getSourceCursorLine() {
    var sel = window.getSelection();
    if (!sel || !sel.anchorNode) return -1;
    var el = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
    while (el && !(el.id && el.id.indexOf("line-") === 0)) {
      el = el.parentElement;
    }
    if (!el || !el.id) return -1;
    return parseInt(el.id.replace("line-", ""), 10) || -1;
  }

  /**
   * 绑定源码编辑器光标变化 → 预览区光标指示
   */
  function bindSourceCursorSync() {
    var editor = document.getElementById("editor");
    if (!editor) return;

    function onSourceCursorChange() {
      if (typeof state === "undefined" || !state) return;
      if (state.viewMode !== "split") return;
      var line = getSourceCursorLine();
      if (line > 0) showPreviewCursor(line);
    }

    editor.addEventListener("keyup", onSourceCursorChange);
    editor.addEventListener("mouseup", onSourceCursorChange);
    editor.addEventListener("focus", onSourceCursorChange);
  }

  function showFakeCursor(srcLine, srcCol) {
    hideFakeCursor();
    var lineEl = document.querySelector("#line-" + srcLine + " .-line-content");
    if (!lineEl) return;
    var node = lineEl.firstChild;
    if (!node || node.nodeType !== 3) return;
    var safeCol = Math.min(Math.max(0, srcCol), node.textContent.length);
    var afterNode = node.splitText(safeCol);
    var cursor = document.createElement("span");
    cursor.className = "-sync-cursor";
    cursor.textContent = "|";
    lineEl.insertBefore(cursor, afterNode);
    _fakeCursorEl = cursor;
  }

  function hideFakeCursor() {
    if (!_fakeCursorEl) return;
    var prev = _fakeCursorEl.previousSibling;
    var next = _fakeCursorEl.nextSibling;
    var parent = _fakeCursorEl.parentNode;
    if (parent) {
      if (prev && prev.nodeType === 3 && next && next.nodeType === 3) {
        prev.textContent += next.textContent;
        parent.removeChild(next);
      }
      parent.removeChild(_fakeCursorEl);
      parent.normalize();
    }
    _fakeCursorEl = null;
  }

  // ── 核心：通过 Mapper 内核获取精确定位 ──

  /**
   * 使用 MemoriaMapper 从浏览器 Selection 精确计算源码坐标
   * 处理所有 inline 语法：**bold**, *italic*, [[\h|highlight]], \c:color, $math$, 等
   * @returns {{ srcLine:number, srcCol:number, blockIndex:number } | null}
   */
  function getPreviewCursor() {
    var sel = window.getSelection();
    if (!sel || !sel.anchorNode) return null;
    var M = window.MemoriaMapper;
    if (!M) return null;

    // domToAst: DOM 光标位置 → AST 坐标 { blockIndex, nodePath, offset }
    var astPos = M.domToAst(sel.anchorNode, sel.anchorOffset);
    if (!astPos || astPos.blockIndex < 0) {
      log("EH", "domToAst: not in any valid block");
      return null;
    }

    // astToSrc: 计算列偏移（正确处理 inline 语法前缀）
    var srcPos = M.astToSrc(astPos.blockIndex, astPos.nodePath, astPos.offset);
    if (!srcPos) {
      log("EH", "astToSrc: failed for block " + astPos.blockIndex);
      return null;
    }

    // 行号：从 DOM 的 data--src-line 获取（由 stampBlockLines 精确计算）
    // astToSrc 的 line 对 frontmatter/多行 block 计算不准确
    var srcLine = srcPos.line;  // 0-based fallback
    var blockEl = document.querySelector('.-src-block[data--block-index="' + astPos.blockIndex + '"]');
    if (blockEl) {
      var dl = parseInt(blockEl.getAttribute("data--src-line"), 10);
      if (!isNaN(dl)) srcLine = dl - 1;  // 转为 0-based
    }

    // LIST block: 每个 item 在不同源码行，需要加上 item 索引
    if (astPos.listItemIndex !== undefined) {
      srcLine += astPos.listItemIndex;
    }

    return {
      srcLine: srcLine + 1,  // 转为 1-based 用于编辑器
      srcCol: srcPos.col,    // 来自 astToSrc，已处理 inline 前缀
      blockIndex: astPos.blockIndex,
      listItemIndex: astPos.listItemIndex,  // LIST block 专用
      nodePath: astPos.nodePath,  // AST 坐标：相对 block 的 inline 节点路径
      offset: astPos.offset,      // AST 坐标：在最终 Text 节点内的偏移
    };
  }

  /**
   * 隐式同步源码光标（存到 state + 显示假光标供校验）
   */
  function syncSourceCursor(srcLine, srcCol, blockIndex) {
    EH.currentCursor = { srcLine: srcLine, srcCol: srcCol, blockIndex: blockIndex };
    if (typeof state !== "undefined" && state) {
      state.cursorLine = srcLine;
      state.cursorCol = srcCol;
    }
    if (typeof state !== "undefined" && state && state.viewMode === "split") {
      showFakeCursor(srcLine, srcCol);
    }
  }

  /**
   * 从浏览器 Selection 读取光标并同步到源码（click / arrow 共用）
   * @param {string} tag — 日志标签（如 "click"、"arrow:ArrowLeft"）
   */
  function syncFromSelection(tag) {
    var cur = getPreviewCursor();
    if (!cur) { log("EH", tag + ": not on a valid block"); return; }
    logCursorContext(cur.srcLine, cur.srcCol, cur.blockIndex, cur.listItemIndex);
    syncSourceCursor(cur.srcLine, cur.srcCol, cur.blockIndex);
    // 保存 AST 坐标，供预览区编辑（beforeinput）定位到具体 Text 节点
    EH.cursorAST = {
      blockIndex: cur.blockIndex,
      nodePath: cur.nodePath,
      offset: cur.offset,
    };
    if (typeof setSourceCursor === "function") {
      setSourceCursor(cur.srcLine, cur.srcCol);
    }
    log("EH", tag + ": L" + cur.srcLine + " C" + cur.srcCol + " (block " + cur.blockIndex + ")");
  }

  /**
   * 光标上下文日志（用于验证映射正确性）
   */
  /**
   * 计算 textNode 在 blockEl 内的 textContent 偏移量
   */
  function getTextOffsetInBlock(blockEl, textNode, offsetInNode) {
    if (!blockEl || !textNode) return 0;
    var walker = document.createTreeWalker(blockEl, NodeFilter.SHOW_TEXT, null, false);
    var total = 0;
    var node;
    while ((node = walker.nextNode())) {
      if (node === textNode) return total + offsetInNode;
      total += (node.textContent || "").length;
    }
    return total;
  }

  function logCursorContext(srcLine, srcCol, blockIndex, listItemIndex) {
    var M = window.MemoriaMapper;
    var doc = M ? M.getDoc() : null;
    var block = doc && doc.blocks ? doc.blocks[blockIndex] : null;
    var srcLineEl = document.querySelector("#line-" + srcLine + " .-line-content");
    var srcLineText = srcLineEl ? (srcLineEl.textContent || "") : "";
    var blockEl = block ? document.querySelector('.-src-block[data--block-index="' + blockIndex + '"]') : null;
    var pvText = blockEl ? (blockEl.textContent || "") : "";

    // LIST block: 使用特定 <li> 的文本和偏移
    var sel = window.getSelection();
    var pvCol = 0;
    if (listItemIndex !== undefined && blockEl) {
      var lis = blockEl.querySelectorAll("li");
      var liEl = listItemIndex < lis.length ? lis[listItemIndex] : null;
      if (liEl) {
        pvText = liEl.textContent || "";
        if (sel && sel.anchorNode && liEl.contains(sel.anchorNode)) {
          pvCol = getTextOffsetInBlock(liEl, sel.anchorNode, sel.anchorOffset);
        }
      }
    } else if (sel && sel.anchorNode && blockEl && blockEl.contains(sel.anchorNode)) {
      pvCol = getTextOffsetInBlock(blockEl, sel.anchorNode, sel.anchorOffset);
    }

    var ctx = 8;
    var srcBefore = srcLineText.substring(Math.max(0, srcCol - ctx), srcCol);
    var srcAt = srcLineText.charAt(srcCol) || "\u00b7";
    var srcAfter = srcLineText.substring(srcCol + 1, srcCol + 1 + ctx);
    var srcCtx = "[" + srcBefore + "|" + srcAt + "|" + srcAfter + "]";

    var pvBefore = pvText.substring(Math.max(0, pvCol - ctx), pvCol);
    var pvAt = pvText.charAt(pvCol) || "\u00b7";
    var pvAfter = pvText.substring(pvCol + 1, pvCol + 1 + ctx);
    var pvCtx = "[" + pvBefore + "|" + pvAt + "|" + pvAfter + "]";

    log("CTX", "SRC L" + srcLine + " C" + srcCol + " " + srcCtx);
    log("CTX", "PV  blk" + blockIndex + " C" + pvCol + " " + pvCtx);
  }

  // ── F2: 鼠标点击 → 光标同步 ──

  // 不可编辑的 block 类型（方向键需跳过）
  var NON_EDITABLE = null;
  function _nonEditableSet() {
    if (NON_EDITABLE) return NON_EDITABLE;
    var T = MemoriaAST.TYPES;
    NON_EDITABLE = {};
    [T.CODE_BLOCK, T.MATH_BLOCK, T.MERMAID, T.TABLE, T.FRONTMATTER, T.IMAGE].forEach(function (t) {
      NON_EDITABLE[t] = true;
    });
    return NON_EDITABLE;
  }

  function isNonEditableBlock(blockIndex) {
    var M = window.MemoriaMapper;
    var doc = M ? M.getDoc() : null;
    if (!doc || !doc.blocks || blockIndex < 0 || blockIndex >= doc.blocks.length) {
      flog("NED", "isNonEditableBlock(" + blockIndex + ") → false (no doc/blocks)");
      return false;
    }
    var t = doc.blocks[blockIndex].type;
    var r = _nonEditableSet().hasOwnProperty(t);
    flog("NED", "isNonEditableBlock(" + blockIndex + ") type=" + t + " → " + r);
    return r;
  }

  /** 是否为图片块（光标可停靠在 img 前/后，但内容不可编辑） */
  function isImageBlock(blockIndex) {
    var M = window.MemoriaMapper;
    var doc = M ? M.getDoc() : null;
    if (!doc || !doc.blocks || blockIndex < 0 || blockIndex >= doc.blocks.length) return false;
    return doc.blocks[blockIndex].type === "image";
  }

  /** 光标是否停在图片块的 img 前（0）/后（1）；非图片停靠位置返回 -1 */
  function imageStopOffset(sel) {
    if (!sel || !sel.anchorNode || !sel.anchorNode.classList) return -1;
    if (!sel.anchorNode.classList.contains("-src-block")) return -1;
    if (sel.anchorOffset !== 0 && sel.anchorOffset !== 1) return -1;
    var bi = parseInt(sel.anchorNode.getAttribute("data--block-index"), 10);
    if (isNaN(bi) || !isImageBlock(bi)) return -1;
    return sel.anchorOffset;
  }

  /** 在图片块的 img 前（side=0）/后（side=1）放置光标 */
  function placeCursorInImageBlock(blockIndex, side) {
    var el = document.querySelector('.-src-block[data--block-index="' + blockIndex + '"]');
    if (!el) return false;
    var off = side > 0 ? (el.childNodes.length || 0) : 0;
    var r = document.createRange();
    r.setStart(el, Math.min(off, el.childNodes.length));
    r.collapse(true);
    var s = window.getSelection();
    s.removeAllRanges();
    s.addRange(r);
    flog("PCB", "placeCursorInImageBlock(" + blockIndex + ", side=" + side + ") off=" + off + " → OK");
    return true;
  }

  function findEditableBlockIndex(fromIndex, direction) {
    var M = window.MemoriaMapper;
    var doc = M ? M.getDoc() : null;
    if (!doc || !doc.blocks) { flog("FEI", "findEditableBlockIndex: no doc"); return -1; }
    var idx = fromIndex + direction;
    var skipped = [];
    while (idx >= 0 && idx < doc.blocks.length) {
      if (!isNonEditableBlock(idx)) {
        flog("FEI", "findEditableBlockIndex(" + fromIndex + "," + direction + ") → " + idx + " skipped=[" + skipped.join(",") + "]");
        return idx;
      }
      skipped.push(idx + "(" + doc.blocks[idx].type + ")");
      idx += direction;
    }
    flog("FEI", "findEditableBlockIndex(" + fromIndex + "," + direction + ") → -1 skipped=[" + skipped.join(",") + "]");
    return -1;
  }

  function getBlockIndexFromSelection() {
    var sel = window.getSelection();
    if (!sel || !sel.anchorNode) { flog("GBI", "→ -1 (no selection)"); return -1; }
    var el = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
    var tag = sel.anchorNode.nodeName || "?";
    var off = sel.anchorOffset;
    while (el && !(el.classList && el.classList.contains("-src-block"))) {
      el = el.parentElement;
    }
    if (!el) { flog("GBI", "→ -1 (anchor=" + tag + " off=" + off + " no .-src-block)"); return -1; }
    var bi = parseInt(el.getAttribute("data--block-index"), 10);
    flog("GBI", "→ " + bi + " (anchor=" + tag + " off=" + off + ")");
    return bi;
  }

  function placeCursorInBlock(blockIndex, atEnd) {
    var el = document.querySelector('.-src-block[data--block-index="' + blockIndex + '"]');
    if (!el) { flog("PCB", "placeCursorInBlock(" + blockIndex + "," + atEnd + ") → FAIL no blockEl"); return false; }
    flog("PCB", "placeCursorInBlock(" + blockIndex + "," + atEnd + ") tag=" + el.tagName + " ce=" + el.contentEditable);
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        var p = node.parentElement;
        while (p && p !== el) {
          if (p.contentEditable === "false") return NodeFilter.FILTER_REJECT;
          p = p.parentElement;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    }, false);
    var first = null, last = null;
    var node;
    while ((node = walker.nextNode())) {
      if (!first) first = node;
      last = node;
    }
    // 没有文本节点（空行 block）→ 在 block 元素上放置光标（atEnd 时放元素末尾，
    // 如图片块 img 之后）
    if (!first) {
      flog("PCB", "  no text nodes → placing on blockEl directly");
      var r0 = document.createRange();
      var offEmpty = atEnd ? (el.childNodes.length || 0) : 0;
      r0.setStart(el, Math.min(offEmpty, el.childNodes.length));
      r0.collapse(true);
      var s0 = window.getSelection();
      s0.removeAllRanges();
      s0.addRange(r0);
      flog("PCB", "  → OK (empty block, off=" + offEmpty + ")");
      return true;
    }
    var target = atEnd ? last : first;
    var offset = atEnd ? (target.textContent || "").length : 0;
    flog("PCB", "  target='" + (target.textContent || "").substring(0, 20) + "' offset=" + offset);
    var range = document.createRange();
    range.setStart(target, offset);
    range.collapse(true);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    flog("PCB", "  → OK");
    return true;
  }

  /**
   * 检查光标是否在当前 block 的边界（使用编译内核查询 DOM 位置）
   * @param {number} direction - 1=末尾（Right/Down），-1=开头（Left/Up）
   * @returns {boolean}
   */
  function isAtBlockEdge(direction) {
    var sel = window.getSelection();
    if (!sel || !sel.anchorNode) { flog("EDGE", "isAtBlockEdge(" + direction + ") → false (no sel)"); return false; }

    // 找到当前 block 元素
    var el = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
    var blockEl = null;
    while (el) {
      if (el.classList && el.classList.contains("-src-block")) { blockEl = el; break; }
      el = el.parentElement;
    }
    if (!blockEl) { flog("EDGE", "isAtBlockEdge(" + direction + ") → false (no blockEl)"); return false; }

    // TreeWalker 查找 block 内的文本节点（跳过 contentEditable=false 子元素）
    var walker = document.createTreeWalker(blockEl, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        var p = node.parentElement;
        while (p && p !== blockEl) {
          if (p.contentEditable === "false") return NodeFilter.FILTER_REJECT;
          p = p.parentElement;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    }, false);

    if (direction > 0) {
      // 末尾：光标在最后一个文本节点的末尾
      var lastText = null;
      var n;
      while ((n = walker.nextNode())) lastText = n;
      // 空块（如空行）无文本节点 → 视为边界（支持从空行进入相邻图片块的停靠）
      if (!lastText) { flog("EDGE", "isAtBlockEdge(1) → true (empty block, treated as edge)"); return true; }
      var isLast = sel.anchorNode === lastText && sel.anchorOffset >= (lastText.textContent || "").length;
      flog("EDGE", "isAtBlockEdge(1) anchor='" + (sel.anchorNode.textContent || "").substring(0, 15) + "' off=" + sel.anchorOffset + " lastText='" + (lastText.textContent || "").substring(0, 15) + "' len=" + (lastText.textContent || "").length + " → " + isLast);
      return isLast;
    } else {
      // 开头：光标在第一个文本节点的开头
      var firstText = walker.nextNode();
      if (!firstText) { flog("EDGE", "isAtBlockEdge(-1) → true (empty block, treated as edge)"); return true; }
      var isFirst = sel.anchorNode === firstText && sel.anchorOffset === 0;
      flog("EDGE", "isAtBlockEdge(-1) anchor='" + (sel.anchorNode.textContent || "").substring(0, 15) + "' off=" + sel.anchorOffset + " firstText='" + (firstText.textContent || "").substring(0, 15) + "' → " + isFirst);
      return isFirst;
    }
  }

  /**
   * 绑定 beforeinput：拦截预览区的文本输入，统一走 AST 编辑管线
   * 每种编辑操作逐步实现，当前支持 insertText（Backspace/Delete/Enter 后续补充）
   */
  function bindBeforeInput() {
    var preview = document.getElementById("preview");
    if (!preview) return;

    preview.addEventListener("beforeinput", function (e) {
      if (!EH.editMode) return;
      if (typeof state === "undefined" || !state) return;
      if (state.viewMode === "source") return;
      // 块编辑模式（代码块/数学块/表格等）不拦截，交还原生编辑
      if (EH.blockEditMode) return;
      // IME 组合输入期间不拦截，交还原生编辑；提交统一在 compositionend 处理
      if (EH._composing) return;

      var EditSync = window.MemoriaEditSync;
      if (!EditSync) return;

      var inputType = e.inputType;
      var fn = null;
      var arg = null;

      if (inputType === "insertText") {
        if (!e.data) return;
        fn = "insertText";
        arg = e.data;
      } else if (inputType === "deleteContentBackward" || inputType === "deleteContentForward") {
        var selNow = window.getSelection();
        if (selNow && !selNow.isCollapsed) {
          // 非折叠选区：删除整个选中范围（作为单个撤销单元）
          fn = "deleteSelection";
          arg = selNow.getRangeAt(0).cloneRange();
        } else {
          fn = inputType === "deleteContentBackward" ? "backspace" : "deleteForward";
        }
      } else if (inputType === "insertParagraph") {
        fn = "splitParagraph";
      } else {
        return; // 其余 inputType（IME/粘贴等）暂不拦截
      }

      if (typeof EditSync[fn] !== "function") return;

      // 用最新浏览器选区刷新 AST 锚点（保证光标位置准确）
      syncFromSelection("beforeinput");

      // 阻止浏览器直接修改 DOM，改由 AST 编辑管线统一处理
      e.preventDefault();
      if (arg !== null) EditSync[fn](arg);
      else EditSync[fn]();
    });

    // Ctrl+Z / Ctrl+Y（及 Ctrl+Shift+Z）撤销与重做
    preview.addEventListener("keydown", function (e) {
      if (!EH.editMode) return;
      if (typeof state === "undefined" || !state) return;
      if (state.viewMode === "source") return;
      if (!(e.ctrlKey || e.metaKey)) return;

      var key = (e.key || "").toLowerCase();
      var EditSync = window.MemoriaEditSync;
      if (!EditSync) return;

      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        EditSync.undo();
      } else if (key === "y" || (key === "z" && e.shiftKey)) {
        e.preventDefault();
        EditSync.redo();
      }
    });
  }

  /**
   * 绑定 IME 组合输入（composition）事件
   * 组合过程中（拼音如 wo'shi'shui）只做视觉反馈，不写入源码；
   * 组合结束（compositionend）时，把最终提交的中文字符通过 AST 管线写入。
   */
  function bindComposition() {
    var preview = document.getElementById("preview");
    if (!preview) return;

    preview.addEventListener("compositionstart", function (e) {
      if (!EH.editMode) return;
      if (typeof state === "undefined" || !state) return;
      if (state.viewMode === "source") return;
      // 图片名称编辑中：input 的 IME 由浏览器原生处理，不进 AST 编辑管线
      // （否则 input 内的组合事件冒泡到 preview，compositionend 会把中文误插到文档 → 重渲染退出编辑）
      if (EH._captionEditingEl) return;

      // 组合开始前 DOM 尚未被污染，此时同步锚点是准确的
      syncFromSelection("compositionstart");
      EH._composing = true;
      EH._composeStartAST = EH.cursorAST ? {
        blockIndex: EH.cursorAST.blockIndex,
        nodePath: (EH.cursorAST.nodePath || []).slice(),
        offset: EH.cursorAST.offset,
      } : null;
    });

    preview.addEventListener("compositionend", function (e) {
      if (!EH._composing) return;
      EH._composing = false;

      var committed = (e.data != null) ? e.data : "";
      var EditSync = window.MemoriaEditSync;
      if (!EditSync) { EH._composeStartAST = null; return; }

      // 组合期间原生输入已污染 DOM，恢复起始锚点（不能依赖当前选区）
      EH.cursorAST = EH._composeStartAST;

      if (committed) {
        EditSync.insertText(committed, true);
      } else if (typeof EditSync.revertBlock === "function") {
        // 空提交（用户取消选词）：仅回滚被污染的前端 DOM
        EditSync.revertBlock();
      }
      EH._composeStartAST = null;
    });
  }

  EH.bindPreviewClick = function () {
    var preview = document.getElementById("preview");
    var editor = document.getElementById("editor");
    if (!preview) return;

    // 源码区获得焦点时清除假光标
    if (editor) {
      editor.addEventListener("mousedown", function () { hideFakeCursor(); });
      editor.addEventListener("focus", function () { hideFakeCursor(); });
    }

    // 源码→预览方向：光标变化时同步预览区指示
    bindSourceCursorSync();

    // mouseup: 使用 Mapper 获取精确坐标
    preview.addEventListener("mouseup", function (e) {
      if (!EH.editMode) return;  // 浏览模式：不拦截点击，链接/右键正常
      if (typeof state === "undefined" || !state) return;
      if (state.viewMode === "source") return;

      // 如果点击在不可编辑 block 上，不同步光标（避免转移焦点，让 dblclick 能触发）
      var clickTarget = e.target;
      // 行内公式（contenteditable=false 原子块）：点击/拖拽用于整体选中公式，不同步光标
      if (clickTarget.closest && clickTarget.closest(".-math")) {
        flog("MOUSE", "mouseup on inline math → skip sync (keep formula selection)");
        return;
      }
      var walkEl = clickTarget;
      while (walkEl && !(walkEl.classList && walkEl.classList.contains("-src-block"))) {
        walkEl = walkEl.parentElement;
      }
      if (walkEl) {
        var clickBi = parseInt(walkEl.getAttribute("data--block-index"), 10);
        if (!isNaN(clickBi) && isNonEditableBlock(clickBi)) {
          // 正在编辑名称（caption）时，点击名称文字交给原生光标定位（可点文字中间），
          // 不做图片前/后停靠，否则每次点击 selection 都被 placeCursorInImageBlock 覆盖
          if (isImageBlock(clickBi) && EH.blockEditMode && EH.blockEditMode.blockType === "image" &&
              clickTarget.closest && clickTarget.closest("[data--image-caption]")) {
            flog("MOUSE", "mouseup on caption while editing → skip dock (native caret)");
            return;
          }
          // 图片块：点击 img 外的空白 → 光标停靠图片前/后（点击 img 本体 → Lightbox）
          if (isImageBlock(clickBi) && !(clickTarget.tagName === "IMG")) {
            var sideImg = 0;
            var imgEl = walkEl.querySelector("img.-preview-image");
            if (imgEl) {
              var ir = imgEl.getBoundingClientRect();
              sideImg = e.clientX >= ir.left + ir.width / 2 ? 1 : 0;
            }
            flog("MOUSE", "mouseup on image block blank → dock cursor side=" + sideImg);
            placeCursorInImageBlock(clickBi, sideImg);
            EH._caretInPreview = true;  // 编辑光标真实停靠预览区图片旁
            setTimeout(function () { syncFromSelection("click:image"); }, 0);
            return;
          }
          flog("MOUSE", "mouseup on non-editable block " + clickBi + " → skip sync (allow dblclick)");
          return;
        }
      }

      EH._caretInPreview = true;  // 点击预览区 → 编辑光标真实位于预览区
      setTimeout(function () { syncFromSelection("click"); }, 0);
    });

    // keydown: 方向键 → 浏览器先移动光标，setTimeout 后同步
    var ARROW_KEYS = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1 };
    preview.addEventListener("keydown", function (e) {
      if (!EH.editMode) return;
      if (typeof state === "undefined" || !state) return;
      if (state.viewMode === "source") return;
      // IME 组合期间方向键用于候选词导航，交还 IME，不做 AST 光标同步
      if (EH._composing) return;
      // 图片名称编辑中：方向键交给 contenteditable 原生光标移动（capKeyHandler 内做边界钳制）
      if (EH._captionEditingEl) return;
      if (!ARROW_KEYS[e.key]) return;
      var key = e.key;
      var dir = (key === "ArrowRight" || key === "ArrowDown") ? 1 : -1;

      flog("═══", "═══════════════════════════════════════════");
      flog("KEY", "keydown: " + key + " dir=" + dir + " editMode=" + EH.editMode);
      flog("KEY", "currentCursor=" + JSON.stringify(EH.currentCursor));

      // ── AST-first: 在浏览器移动光标之前，先查询当前位置 ──
      var curBlkIdx = getBlockIndexFromSelection();

      // 光标不在任何 block 内 → 使用上一个已知位置回退
      if (curBlkIdx < 0) {
        flog("KEY", "curBlkIdx<0, falling back to currentCursor");
        curBlkIdx = (EH.currentCursor && EH.currentCursor.blockIndex >= 0)
          ? EH.currentCursor.blockIndex : -1;
      }

      // 无法确定当前位置 → 让浏览器处理
      if (curBlkIdx < 0) {
        flog("KEY", "curBlkIdx still <0 → browser handle");
        setTimeout(function () { syncFromSelection("arrow:" + key); }, 0);
        return;
      }

      // ── Case A: 当前 block 不可编辑 ──
      //    图片块：光标可停靠 img 前/后，按方向键在两侧间移动或离开；
      //    其他块：跳过到下一个可编辑 block
      if (isNonEditableBlock(curBlkIdx)) {
        var imgStop = isImageBlock(curBlkIdx) ? imageStopOffset(window.getSelection()) : -1;
        if (imgStop >= 0) {
          flog("CASA", "Case A: image block, imgStop=" + imgStop + " dir=" + dir + " → dock nav");
          e.preventDefault();
          var inside = (imgStop === 0 && dir > 0) || (imgStop === 1 && dir < 0);
          if (inside) {
            // 在图片两侧间移动
            placeCursorInImageBlock(curBlkIdx, imgStop === 0 ? 1 : 0);
          } else {
            // 离开图片块到相邻可编辑块
            var outIdx = findEditableBlockIndex(curBlkIdx, dir);
            if (outIdx >= 0) placeCursorInBlock(outIdx, dir < 0);
          }
          syncFromSelection("arrow:" + key);
          return;
        }
        flog("CASA", "Case A: curBlk " + curBlkIdx + " non-editable → skip");
        e.preventDefault();
        var skipIdx = findEditableBlockIndex(curBlkIdx, dir);
        if (skipIdx >= 0) {
          placeCursorInBlock(skipIdx, dir < 0);
        }
        syncFromSelection("arrow:" + key);
        return;
      }

      // ── Case B: 当前 block 可编辑，检查是否在 block 边界 ──
      //    所有方向键都做边界检查：在边界且下一 block 不可编辑 → 图片块停靠 img 两侧，其他跳过
      var atEdge = isAtBlockEdge(dir);
      flog("CASB", "Case B: curBlk " + curBlkIdx + " atEdge(" + dir + ")=" + atEdge);
      if (atEdge) {
        var nextBlk = curBlkIdx + dir;
        flog("CASB", "  nextBlk=" + nextBlk);
        // 下一个 block 不可编辑 → 图片块停靠 / 其他跳过
        if (nextBlk >= 0 && isNonEditableBlock(nextBlk)) {
          if (isImageBlock(nextBlk)) {
            // 从相邻可编辑块边界进入图片块：向右 → img 前，向左 → img 后
            flog("CASB", "  nextBlk is image → dock at img side");
            e.preventDefault();
            placeCursorInImageBlock(nextBlk, dir > 0 ? 0 : 1);
            syncFromSelection("arrow:" + key);
            return;
          }
          flog("CASB", "  nextBlk non-editable → preventDefault + skip");
          e.preventDefault();
          var skipIdx2 = findEditableBlockIndex(nextBlk, dir);
          if (skipIdx2 >= 0) {
            placeCursorInBlock(skipIdx2, dir < 0);
          }
          syncFromSelection("arrow:" + key);
          return;
        }
        flog("CASB", "  nextBlk editable or out of range → no skip");
      }

      // ── Case C: 正常移动 → 让浏览器处理，事后同步 ──
      flog("CASC", "Case C: normal move, browser handles, then check");
      setTimeout(function () {
        var newBlk = getBlockIndexFromSelection();
        flog("CASC", "  after browser move: newBlk=" + newBlk);
        // 移动后落入不可编辑 block → 跳过
        if (newBlk >= 0 && isNonEditableBlock(newBlk)) {
          flog("CASC", "  newBlk non-editable → skip");
          var sIdx = findEditableBlockIndex(newBlk, dir);
          if (sIdx >= 0) placeCursorInBlock(sIdx, dir < 0);
        }
        // 光标不在任何 block 内 → 回退到上一个已知位置 + 跳过
        else if (newBlk < 0) {
          flog("CASC", "  newBlk<0 → fallback to lastBlk");
          var lastBlk = (EH.currentCursor && EH.currentCursor.blockIndex >= 0)
            ? EH.currentCursor.blockIndex : -1;
          flog("CASC", "  lastBlk=" + lastBlk);
          if (lastBlk >= 0) {
            var nb = lastBlk + dir;
            flog("CASC", "  nb=" + nb);
            if (nb >= 0 && isNonEditableBlock(nb)) {
              flog("CASC", "  nb non-editable → skip");
              var sIdx2 = findEditableBlockIndex(nb, dir);
              if (sIdx2 >= 0) placeCursorInBlock(sIdx2, dir < 0);
            } else if (nb >= 0 && !isNonEditableBlock(nb)) {
              flog("CASC", "  nb editable → placeCursor");
              placeCursorInBlock(nb, dir < 0);
            } else {
              flog("CASC", "  nb out of range → placeCursor lastBlk");
              placeCursorInBlock(lastBlk, dir > 0);
            }
          }
        }
        syncFromSelection("arrow:" + key);
      }, 0);
    });

    // 绑定块编辑双击事件
    bindBlockEditEvents();

    // 绑定 beforeinput 编辑拦截（AST 编辑管线）
    bindBeforeInput();

    // 绑定 IME 组合输入事件
    bindComposition();
  };

  // ── F3-F6: ArrowLeft/Right/Up/Down — 已在 bindPreviewClick 中实现 ──

  // ── F10: 双击进入块编辑模式 ──

  EH.blockEditMode = null;  // { blockIndex, blockEl, blockType, srcStart, srcEnd }

  /** 块类型对应的标签和工具 */
  var _BLOCK_TOOLS = {
    code_block: {
      label: "编辑代码块",
      tools: function (block) {
        var langs = ["", "javascript", "python", "bash", "json", "html", "css", "sql", "mermaid"];
        var sel = '<select id="blk-lang-sel" class="-block-lang-sel" title="语言">';
        for (var i = 0; i < langs.length; i++) {
          var v = langs[i];
          var sel2 = (block.lang === v) ? " selected" : "";
          sel += '<option value="' + v + '"' + sel2 + ">" + (v || "无") + "</option>";
        }
        sel += "</select>";
        return sel;
      }
    },
    mermaid: {
      label: "编辑思维导图",
      tools: function () {
        var types = [
          { v: "graph TD", l: "流程图" },
          { v: "sequenceDiagram", l: "序列图" },
          { v: "classDiagram", l: "类图" },
          { v: "stateDiagram-v2", l: "状态图" },
          { v: "erDiagram", l: "ER图" },
          { v: "gantt", l: "甘特图" },
        ];
        var html = '<span class="-block-edit-hint">类型:</span><select id="blk-mermaid-type" class="-block-lang-sel">';
        for (var i = 0; i < types.length; i++) {
          html += '<option value="' + types[i].v + '">' + types[i].l + "</option>";
        }
        html += "</select>";
        return html;
      }
    },
    math_block: {
      label: "编辑数学公式",
      tools: function () {
        var syms = ["α","β","γ","δ","θ","λ","μ","π","σ","φ","ω","∑","∏","∫","∂","∞","≤","≥","≠","±","×","÷","√","∈","∉","⊂","⊃","∪","∩","∀","∃"];
        var html = '<span class="-block-edit-hint">符号:</span>';
        for (var i = 0; i < syms.length; i++) {
          html += '<button type="button" class="-math-sym-btn" data-sym="' + syms[i] + '">' + syms[i] + "</button>";
        }
        return html;
      }
    },
    table: {
      label: "编辑表格",
      tools: function () {
        return '<button type="button" class="-fmt-btn" id="blk-add-row" title="添加行">+行</button>' +
               '<button type="button" class="-fmt-btn" id="blk-add-col" title="添加列">+列</button>';
      }
    },
    image: {
      label: "编辑图片",
      tools: function () {
        return '<span class="-block-edit-hint">对齐:</span>' +
          '<button type="button" class="-fmt-btn -img-align-btn" data-align="left" title="左对齐">左</button>' +
          '<button type="button" class="-fmt-btn -img-align-btn" data-align="center" title="居中">中</button>' +
          '<button type="button" class="-fmt-btn -img-align-btn" data-align="right" title="右对齐">右</button>' +
          '<span class="-block-edit-hint">大小:</span>' +
          '<input type="range" id="img-size-slider" class="-img-size-slider" min="50" max="800" step="10" title="图片显示宽度">' +
          '<span class="-img-size-val" id="img-size-val">300</span>' +
          '<span class="-block-edit-hint">名称:</span>' +
          '<input type="range" id="img-name-size-slider" class="-img-name-size-slider" min="10" max="32" step="1" title="名称字号">' +
          '<span class="-img-name-val" id="img-name-val">14</span>' +
          '<button type="button" id="img-name-toggle" class="-fmt-btn" title="显示/隐藏图片名称">名称:开</button>' +
          '<button type="button" class="-fmt-btn" id="img-mgr-btn" title="打开图片管理">图片管理</button>';
      }
    }
  };

  /**
   * 进入行内公式编辑模式
   * @param {HTMLElement} mathEl — .-math span 或 mjx-container[data--inline-math] 元素
   */
  function enterInlineMathEditMode(mathEl) {
    if (EH.blockEditMode) exitBlockEditMode();

    // 判断元素类型并获取公式
    var isMjxContainer = mathEl.tagName === "MJX-CONTAINER";
    var formula = "";
    if (isMjxContainer) {
      // MathJax 渲染后的 mjx-container：从 data-formula 属性获取
      formula = mathEl.getAttribute("data-formula") || "";
    } else {
      // 原始 .-math span：从 data-formula 或 textContent 获取
      formula = mathEl.getAttribute("data-formula") || "";
      if (!formula) {
        var rawText = mathEl.textContent || "";
        formula = rawText.replace(/^\$/, "").replace(/\$$/, "");
      }
    }

    EH.blockEditMode = {
      isInline: true,
      mathEl: mathEl,
      isMjxContainer: isMjxContainer,
      originalFormula: formula,
      blockType: "math_inline",
    };

    // 切换工具栏
    var fmtBar = document.querySelector(".-format-bar");
    var blkBar = document.getElementById("block-edit-bar");
    if (fmtBar) fmtBar.classList.add("hidden");
    if (blkBar) blkBar.classList.remove("hidden");

    var labelEl = document.getElementById("block-edit-label");
    if (labelEl) labelEl.textContent = "编辑行内公式";

    // 生成符号工具栏
    var toolsEl = document.getElementById("block-edit-tools");
    if (toolsEl) {
      var syms = ["α","β","γ","δ","θ","λ","μ","π","σ","φ","ω","∑","∏","∫","∂","∞","≤","≥","≠","±","×","÷","√","∈","∉","⊂","⊃","∪","∩","∀","∃"];
      var html = '<span class="-block-edit-hint">符号:</span>';
      for (var i = 0; i < syms.length; i++) {
        html += '<button type="button" class="-math-sym-btn" data-sym="' + syms[i] + '">' + syms[i] + "</button>";
      }
      toolsEl.innerHTML = html;

      // 绑定符号按钮：在光标处插入符号
      toolsEl.querySelectorAll(".-math-sym-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var sym = btn.getAttribute("data-sym");
          var sel = window.getSelection();
          if (sel && sel.rangeCount && mathEl.contains(sel.anchorNode)) {
            var range = sel.getRangeAt(0);
            range.deleteContents();
            range.insertNode(document.createTextNode(sym));
            range.collapse(false);
            sel.removeAllRanges();
            sel.addRange(range);
          }
        });
      });
    }

    // 清除 MathJax 渲染内容，显示原始公式文本（不含 $）
    mathEl.contentEditable = "true";
    mathEl.classList.add("-block-editing");
    mathEl.textContent = formula;

    // 聚焦并全选
    mathEl.focus();
    var range = document.createRange();
    range.selectNodeContents(mathEl);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    flog("DBL", "inline math edit mode: formula=" + formula + " mjx=" + isMjxContainer);
  }

  /**
   * 进入块编辑模式
   */
  function enterBlockEditMode(blockEl, blockIndex) {
    var M = window.MemoriaMapper;
    var doc = M ? M.getDoc() : null;
    if (!doc || !doc.blocks || blockIndex < 0 || blockIndex >= doc.blocks.length) return;

    var block = doc.blocks[blockIndex];
    var blockType = block.type;
    // Mermaid 是 CODE_BLOCK with lang="mermaid"
    if (blockType === "code_block" && block.lang === "mermaid") blockType = "mermaid";

    var toolsDef = _BLOCK_TOOLS[blockType];
    if (!toolsDef) return;

    // 获取源码行范围
    var srcStart = parseInt(blockEl.getAttribute("data--src-line"), 10) || 0;
    var srcEnd = parseInt(blockEl.getAttribute("data--src-line-end"), 10) || srcStart;

    // 图片块：保留 <img> 显示，工具栏提供对齐/大小/管理操作（单击图片触发）
    if (blockType === "image") {
      var editorImg = document.getElementById("editor");
      var srcLineText = "";
      if (editorImg && srcStart > 0) {
        var lineElsImg = editorImg.querySelectorAll(".-line-content");
        var srcLineElImg = lineElsImg[srcStart - 1];
        if (srcLineElImg) srcLineText = srcLineElImg.textContent || "";
      }
      var imgElImg = blockEl.querySelector("img");
      var capElImg = blockEl.querySelector("[data--image-caption]");
      EH.blockEditMode = {
        blockIndex: blockIndex, blockEl: blockEl, blockType: "image",
        srcStart: srcStart, srcEnd: srcStart, originalContent: srcLineText,
        imgEl: imgElImg,
        imgAttrs: parseImageAttrsFromLine(srcLineText),
        // 名称（alt）编辑锚点
        captionEl: capElImg,
        originalCaption: capElImg ? (capElImg.textContent || "") : "",
        // 进入编辑时的渲染内联样式（renderer 按源码 width/height 生成）；
        // 退出时恢复它而不是删除，否则会抹掉写回后渲染的 width，
        // 图片退回 max-width:35% 钳制的"固定大小"，需刷新才恢复
        imgOrigStyle: {
          width: imgElImg ? imgElImg.style.width : "",
          maxWidth: imgElImg ? imgElImg.style.maxWidth : "",
        },
      };

      // 切换工具栏
      var fmtBarImg = document.querySelector(".-format-bar");
      var blkBarImg = document.getElementById("block-edit-bar");
      if (fmtBarImg) fmtBarImg.classList.add("hidden");
      if (blkBarImg) blkBarImg.classList.remove("hidden");
      var labelElImg = document.getElementById("block-edit-label");
      if (labelElImg) labelElImg.textContent = "编辑图片";
      // "编辑图片"标签置于工具栏（#editor-header）最左侧：隐藏文件名 #file-meta
      var metaElImg = document.getElementById("file-meta");
      if (metaElImg) metaElImg.style.display = "none";
      var toolsElImg = document.getElementById("block-edit-tools");
      if (toolsElImg) {
        toolsElImg.innerHTML = toolsDef.tools(block);
        _initImageTools();
      }
      blockEl.classList.add("-block-editing");
      log("EH", "enterBlockEditMode: image block " + blockIndex + " line " + srcStart + " attrs=" + JSON.stringify(EH.blockEditMode.imgAttrs));
      return;
    }

    // 其余块类型：原始可编辑内容即块内纯文本（代码/公式不含围栏）
    var originalContent = blockEl.textContent || "";

    EH.blockEditMode = { blockIndex: blockIndex, blockEl: blockEl, blockType: blockType, srcStart: srcStart, srcEnd: srcEnd, originalContent: originalContent };

    // 切换工具栏
    var fmtBar = document.querySelector(".-format-bar");
    var blkBar = document.getElementById("block-edit-bar");
    if (fmtBar) fmtBar.classList.add("hidden");
    if (blkBar) blkBar.classList.remove("hidden");

    var labelEl = document.getElementById("block-edit-label");
    if (labelEl) labelEl.textContent = toolsDef.label;

    var toolsEl = document.getElementById("block-edit-tools");
    if (toolsEl) {
      toolsEl.innerHTML = toolsDef.tools(block);
      // 绑定工具事件
      _bindBlockEditTools(blockType, blockEl);
    }

    // 使 block 可编辑
    blockEl.contentEditable = "true";
    blockEl.classList.add("-block-editing");

    // 聚焦
    blockEl.focus();

    // 选中所有内容
    var range = document.createRange();
    range.selectNodeContents(blockEl);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    log("EH", "enterBlockEditMode: block " + blockIndex + " type=" + blockType + " lines " + srcStart + "-" + srcEnd);
  }

  /**
   * 解析图片源码行中的属性：![alt](url "width=300,align=center")
   * @returns {object} {width?, height?, align?}
   */
  function parseImageAttrsFromLine(line) {
    var m = line && line.match(/^!\[[^\]]*\]\([^)\s]+(?:\s+"([^"]*)")?\)\s*$/);
    if (!m || !m[1]) return {};
    var attrs = {};
    m[1].split(",").forEach(function (kv) {
      var eq = kv.indexOf("=");
      if (eq > 0) {
        var k = kv.slice(0, eq).trim();
        var v = kv.slice(eq + 1).trim();
        if (k === "width" || k === "height" || k === "align" || k === "name-size" || k === "name") attrs[k] = v;
      }
    });
    return attrs;
  }

  /** 图片编辑工具栏：绑定对齐按钮 / 大小滑条 / 图片管理入口（单击触发） */
  function _initImageTools() {
    var ctx = EH.blockEditMode;
    if (!ctx || ctx.blockType !== "image") return;

    // 对齐按钮：点击 → 派发属性更新（app.js 写回源码并重进编辑）
    var alignBtns = document.querySelectorAll("#block-edit-tools .-img-align-btn");
    for (var i = 0; i < alignBtns.length; i++) {
      (function (btn) {
        var a = btn.getAttribute("data-align");
        if (ctx.imgAttrs.align === a) btn.classList.add("active");
        btn.addEventListener("click", function () {
          var align = btn.getAttribute("data-align");
          var btns = document.querySelectorAll("#block-edit-tools .-img-align-btn");
          for (var j = 0; j < btns.length; j++) btns[j].classList.remove("active");
          btn.classList.add("active");
          dispatchImageAttr({ align: align });
        });
      })(alignBtns[i]);
    }

    // 大小滑条：拖动实时预览（临时改 img 内联样式），松手提交源码
    var slider = document.getElementById("img-size-slider");
    var valEl = document.getElementById("img-size-val");
    if (slider) {
      var curW = parseInt(ctx.imgAttrs.width, 10);
      if (isNaN(curW)) {
        curW = ctx.imgEl ? Math.round(ctx.imgEl.getBoundingClientRect().width) : 300;
      }
      slider.value = String(curW);
      if (valEl) valEl.textContent = String(curW);
      slider.addEventListener("input", function () {
        if (valEl) valEl.textContent = this.value;
        if (ctx.imgEl) {
          ctx.imgEl.style.maxWidth = "100%";
          ctx.imgEl.style.width = this.value + "px";
        }
      });
      slider.addEventListener("change", function () {
        dispatchImageAttr({ width: this.value });
      });
    }

    // 图片管理入口
    var mgrBtn = document.getElementById("img-mgr-btn");
    if (mgrBtn) {
      mgrBtn.addEventListener("click", function () {
        document.dispatchEvent(new CustomEvent("memoria:open-image-manager"));
      });
    }

    // 名称字号滑条：拖动实时改 caption 字号，松手提交 name-size
    var nameSlider = document.getElementById("img-name-size-slider");
    var nameValEl = document.getElementById("img-name-val");
    if (nameSlider) {
      var curNs = parseInt(ctx.imgAttrs["name-size"], 10);
      if (isNaN(curNs)) {
        curNs = (ctx.captionEl && parseFloat(getComputedStyle(ctx.captionEl).fontSize)) || 14;
        curNs = Math.round(curNs);
      }
      nameSlider.value = String(curNs);
      if (nameValEl) nameValEl.textContent = String(curNs);
      nameSlider.addEventListener("input", function () {
        if (nameValEl) nameValEl.textContent = this.value;
        if (ctx.captionEl) ctx.captionEl.style.fontSize = this.value + "px";
      });
      nameSlider.addEventListener("change", function () {
        dispatchImageAttr({ "name-size": this.value });
      });
    }

    // 名称显示/隐藏开关（name=hide 隐藏；默认/name=show 显示）
    // active（蓝色高亮）表示"开"= 名称显示中
    var nameToggle = document.getElementById("img-name-toggle");
    if (nameToggle) {
      var nameHidden = ctx.imgAttrs.name === "hide";
      nameToggle.textContent = nameHidden ? "名称:关" : "名称:开";
      nameToggle.classList.toggle("active", !nameHidden);
      nameToggle.addEventListener("click", function () {
        dispatchImageAttr({ name: ctx.imgAttrs.name === "hide" ? "show" : "hide" });
      });
    }
  }

  /** 开始编辑图片名称（alt）文字：单击后替换为原生 <input>（单行输入框） */
  function startCaptionEdit(capEl) {
    if (EH._captionEditingEl === capEl) return;
    if (EH._captionEditingEl) finishCaptionEdit();
    EH._captionEditingEl = capEl;
    capEl.classList.add("-caption-editing");
    // 记录原文本（放弃编辑时恢复）
    capEl.setAttribute("data--caption-orig", capEl.textContent || "");
    var input = document.createElement("input");
    input.type = "text";
    input.className = "-caption-input";
    input.value = capEl.textContent || "";
    // 字号跟随名称字号（renderer name-size 或默认）
    var fs = window.getComputedStyle(capEl).fontSize;
    if (fs) input.style.fontSize = fs;
    capEl.textContent = "";
    capEl.appendChild(input);
    input.focus();
    input.select();
    // input 原生处理 IME / 光标（不会越出输入框）；Enter 提交；失焦提交
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        finishCaptionEdit(capEl, input.value);
      }
    });
    input.addEventListener("blur", function () {
      finishCaptionEdit(capEl, input.value);
    }, { once: true });
    flog("CAP", "start caption edit (input)");
  }

  /** 结束名称编辑：写回 alt 到源码行（memoria:image-caption → app.js 更新） */
  function finishCaptionEdit(capEl, inputValue) {
    if (EH._captionEditingEl !== capEl) return;
    EH._captionEditingEl = null;
    if (!capEl) return;
    capEl.classList.remove("-caption-editing");
    var newCap = (inputValue != null ? inputValue : capEl.textContent || "").trim().replace(/\s*\n\s*/g, " ");
    // 移除 input，恢复纯文本显示（app.js 会重渲染，这里先本地更新）
    if (capEl.querySelector("input.-caption-input")) {
      capEl.textContent = newCap;
    }
    var ctx = EH.blockEditMode;
    if (ctx && ctx.blockType === "image" && ctx.srcStart && newCap !== ctx.originalCaption) {
      document.dispatchEvent(new CustomEvent("memoria:image-caption", {
        detail: { srcLine: ctx.srcStart, caption: newCap },
      }));
      flog("CAP", "submit caption=" + newCap + " srcLine=" + ctx.srcStart);
    } else {
      flog("CAP", "caption unchanged or no ctx");
    }
  }

  /** 派发图片属性更新事件（app.js 更新源码行 → 重写渲染 → 重进编辑） */
  function dispatchImageAttr(attrs) {
    var ctx = EH.blockEditMode;
    if (!ctx || ctx.blockType !== "image") return;
    document.dispatchEvent(new CustomEvent("memoria:image-attr", {
      detail: { srcLine: ctx.srcStart, attrs: attrs },
    }));
  }

  /**
   * 绑定块编辑工具事件
   */
  function _bindBlockEditTools(blockType, blockEl) {
    if (blockType === "code_block" || blockType === "mermaid") {
      var langSel = document.getElementById("blk-lang-sel") || document.getElementById("blk-mermaid-type");
      if (langSel) {
        langSel.addEventListener("change", function () {
          // 仅记录，退出时统一更新
          EH.blockEditMode.pendingLang = this.value;
        });
      }
    } else if (blockType === "math_block") {
      var symBtns = document.querySelectorAll(".-math-sym-btn");
      for (var i = 0; i < symBtns.length; i++) {
        symBtns[i].addEventListener("click", function () {
          var sym = this.getAttribute("data-sym");
          var sel = window.getSelection();
          if (sel.rangeCount > 0) {
            var range = sel.getRangeAt(0);
            range.deleteContents();
            range.insertNode(document.createTextNode(sym));
            range.collapse(false);
          }
        });
      }
    }
  }

  /**
   * 退出块编辑模式：捕获内容 → 更新源码 → 重新渲染
   */
  function exitBlockEditMode() {
    if (!EH.blockEditMode) return;
    var ctx = EH.blockEditMode;

    // ── 行内公式编辑退出 ──
    if (ctx.isInline) {
      var mathEl = ctx.mathEl;
      var newFormula = (mathEl.textContent || "").replace(/^\$/, "").replace(/\$$/, "");
      var changed = (newFormula !== ctx.originalFormula);

      // 恢复不可编辑
      mathEl.contentEditable = "false";
      mathEl.classList.remove("-block-editing");

      _restoreToolbar();
      EH.blockEditMode = null;

      if (changed && typeof state !== "undefined" && state) {
        // 找到包含此公式的源码行并替换
        var editor = document.getElementById("editor");
        if (editor) {
          var lineEls = editor.querySelectorAll(".-line-content");
          var oldStr = "$" + ctx.originalFormula + "$";
          var newStr = "$" + newFormula + "$";
          for (var li = 0; li < lineEls.length; li++) {
            var txt = lineEls[li].textContent || "";
            if (txt.indexOf(oldStr) !== -1) {
              lineEls[li].textContent = txt.replace(oldStr, newStr);
              break;
            }
          }
          // 更新 state.doc.body
          var body = [];
          lineEls.forEach(function (le) { body.push(le.textContent || ""); });
          state.doc.body = body.join("\n");
        }
      }

      // mjx-container 需要重新渲染以恢复 MathJax 显示（无论是否修改）
      // .-math span 如果未修改则可以直接显示 $formula$ 文本
      if (ctx.isMjxContainer || changed) {
        if (typeof state !== "undefined" && state) {
          if (typeof window._scheduleRender === "function") window._scheduleRender();
          else if (typeof window.renderPreview === "function") window.renderPreview();
        }
      } else {
        // .-math span 未修改：恢复 $formula$ 文本
        mathEl.textContent = "$" + newFormula + "$";
      }
      flog("DBL", "exit inline math: changed=" + changed + " new=" + newFormula + " mjx=" + (ctx.isMjxContainer || false));
      return;
    }

    // ── 块级编辑退出 ──
    var blockEl = ctx.blockEl;

    // 图片编辑：无文本修改；恢复进入编辑前的渲染内联样式
    // （不能直接删除 width/max-width：写回后重渲染的 img 内联样式是 renderer
    //   按源码属性生成的，删除会导致图片退回 max-width:35% 钳制的固定大小）
    if (ctx.blockType === "image") {
      // 若正在编辑名称文字则先收尾（不提交：视为放弃本次名称编辑）
      if (EH._captionEditingEl) {
        var capElX = EH._captionEditingEl;
        capElX.classList.remove("-caption-editing");
        if (capElX.querySelector("input.-caption-input")) {
          capElX.textContent = capElX.getAttribute("data--caption-orig") || "";
        }
        EH._captionEditingEl = null;
      }
      if (ctx.imgEl) {
        ctx.imgEl.style.width = (ctx.imgOrigStyle && ctx.imgOrigStyle.width) || "";
        ctx.imgEl.style.maxWidth = (ctx.imgOrigStyle && ctx.imgOrigStyle.maxWidth) || "";
      }
      if (blockEl) blockEl.classList.remove("-block-editing");
      // 恢复文件名显示（进入图片编辑时隐藏了 #file-meta 使标签位于工具栏最左）
      var metaElImg2 = document.getElementById("file-meta");
      if (metaElImg2) metaElImg2.style.display = "";
      _restoreToolbar();
      EH.blockEditMode = null;
      flog("DBL", "exit image edit mode (no content write)");
      return;
    }

    // 获取编辑后的纯文本内容
    var newContent = "";
    if (ctx.blockType === "table") {
      // 表格编辑暂不处理内容更新
    } else {
      // 获取纯文本
      newContent = blockEl.textContent || "";
    }

    // 获取源码行
    var editor = document.getElementById("editor");
    if (!editor) { _restoreToolbar(); EH.blockEditMode = null; return; }

    var srcStart = ctx.srcStart;  // 1-based
    var srcEnd = ctx.srcEnd;

    // 更新源码行
    var newLines = newContent.split("\n");

    // 对 CODE_BLOCK / MERMAID: 需要加围栏
    var M = window.MemoriaMapper;
    var doc = M ? M.getDoc() : null;
    var block = doc && doc.blocks ? doc.blocks[ctx.blockIndex] : null;

    if (ctx.blockType === "code_block" || ctx.blockType === "mermaid") {
      var lang = (EH.blockEditMode.pendingLang !== undefined) ? EH.blockEditMode.pendingLang : (block ? block.lang : "");
      // 围栏代码块: ```lang \n code \n ```
      var fence = "```";
      var firstLine = fence + (lang || "");
      var lastLine = fence;
      newLines = [firstLine].concat(newLines).concat([lastLine]);
    } else if (ctx.blockType === "math_block") {
      // 数学块: $$ \n formula \n $$
      newLines = ["$$"].concat(newLines).concat(["$$"]);
    }

    // 替换源码行 (1-based → 0-based)
    var lineEls = editor.querySelectorAll(".-line-content");
    var oldLineCount = srcEnd - srcStart + 1;

    // 简单策略：如果行数相同，逐行替换；如果不同，重建编辑器
    if (newLines.length === oldLineCount) {
      for (var i = 0; i < newLines.length; i++) {
        var idx = srcStart - 1 + i;  // 0-based
        var el = lineEls[idx];
        if (el) el.textContent = newLines[i];
      }
    } else {
      // 行数变化：需要重建编辑器内容
      // 收集所有行文本
      var allLines = [];
      for (var j = 0; j < lineEls.length; j++) {
        allLines.push(lineEls[j].textContent || "");
      }
      // 替换对应行
      var before = allLines.slice(0, srcStart - 1);
      var after = allLines.slice(srcEnd);
      var combined = before.concat(newLines).concat(after);
      // 重建
      if (typeof window._renderEditor === "function") {
        window._renderEditor(combined.join("\n"));
      } else {
        // 手动重建
        editor.innerHTML = combined.map(function (line, k) {
          var n = k + 1;
          return '<div class="-line" data-line="' + n + '" id="line-' + n + '">' +
            '<span class="-lineno">' + n + '</span>' +
            '<span class="-line-content" contenteditable="true" spellcheck="false" tabindex="-1">' +
            (line || "") + '</span></div>';
        }).join("");
      }
    }

    // 内容有变化 → 标记脏（写盘），与源码输入一致
    if (ctx.blockType !== "table" && newContent !== ctx.originalContent && typeof window._markDirty === "function") {
      window._markDirty();
    }

    // 恢复 block 不可编辑
    blockEl.contentEditable = "false";
    blockEl.classList.remove("-block-editing");

    // 恢复工具栏
    _restoreToolbar();

    log("EH", "exitBlockEditMode: block " + ctx.blockIndex + " type=" + ctx.blockType);

    EH.blockEditMode = null;

    // 触发重新渲染
    if (typeof state !== "undefined" && state && typeof window._scheduleRender === "function") {
      window._scheduleRender();
    } else if (typeof window.renderPreview === "function") {
      window.renderPreview();
    }
  }

  function _restoreToolbar() {
    var fmtBar = document.querySelector(".-format-bar");
    var blkBar = document.getElementById("block-edit-bar");
    if (fmtBar) fmtBar.classList.remove("hidden");
    if (blkBar) blkBar.classList.add("hidden");
  }

  /** 绑定双击和退出事件 */
  function bindBlockEditEvents() {
    var preview = document.getElementById("preview");
    if (!preview) return;

    // 双击不可编辑 block 或行内公式 → 进入编辑模式
    preview.addEventListener("dblclick", function (e) {
      flog("DBL", "─── dblclick fired ───");
      flog("DBL", "target=" + (e.target.tagName || e.target.nodeName) + " class=" + (e.target.className || ""));

      if (!EH.editMode) { flog("DBL", "editMode off → return"); return; }
      if (typeof state === "undefined" || !state) { flog("DBL", "no state → return"); return; }
      if (state.viewMode === "source") { flog("DBL", "viewMode=source → return"); return; }
      // 图片编辑模式（双击放大场景）：放行到下方图片块分支执行退出；其余编辑模式直接跳过
      if (EH.blockEditMode && EH.blockEditMode.blockType !== "image") { flog("DBL", "already in blockEditMode → return"); return; }

      // ── 检查是否双击了行内公式 (.-math 或 mjx-container[data--inline-math]) ──
      // MathJax typeset 后 .-math span 可能被替换为 mjx-container，
      // 因此同时检查两种标记
      var mathEl = e.target;
      while (mathEl && mathEl !== preview) {
        if (mathEl.classList && mathEl.classList.contains("-math")) break;
        if (mathEl.tagName === "MJX-CONTAINER" && mathEl.getAttribute("data--inline-math") === "true") break;
        mathEl = mathEl.parentElement;
      }
      if (mathEl && mathEl !== preview) {
        var isMathSpan = mathEl.classList && mathEl.classList.contains("-math");
        var isInlineMjx = mathEl.tagName === "MJX-CONTAINER" && mathEl.getAttribute("data--inline-math") === "true";
        if (isMathSpan || isInlineMjx) {
          flog("DBL", "→ inline math edit mode (" + (isInlineMjx ? "mjx-container" : ".-math") + ")");
          enterInlineMathEditMode(mathEl);
          e.preventDefault();
          return;
        }
      }

      // ── 检查是否双击了不可编辑 block ──
      var el = e.target;
      while (el && !(el.classList && el.classList.contains("-src-block"))) {
        el = el.parentElement;
      }
      if (!el) { flog("DBL", "no .-src-block ancestor → return"); return; }

      var bi = parseInt(el.getAttribute("data--block-index"), 10);
      flog("DBL", "found .-src-block bi=" + bi + " tag=" + el.tagName + " ce=" + el.contentEditable);
      if (isNaN(bi)) { flog("DBL", "bi NaN → return"); return; }

      var ned = isNonEditableBlock(bi);
      flog("DBL", "isNonEditableBlock(" + bi + ")=" + ned);
      if (!ned) { flog("DBL", "editable block → return"); return; }

      // 图片块：双击 = Lightbox 放大（单击已进入编辑工具栏）；若已在图片编辑模式则退出
      if (isImageBlock(bi)) {
        if (EH.blockEditMode && EH.blockEditMode.blockType === "image") exitBlockEditMode();
        flog("DBL", "image block dblclick → Lightbox (skip edit mode)");
        return;
      }

      flog("DBL", "→ enterBlockEditMode(" + bi + ")");
      enterBlockEditMode(el, bi);
    });

    // 单击图片块 → 进入图片编辑工具栏（左键单击触发）
    preview.addEventListener("click", function (e) {
      if (!EH.editMode) return;
      if (typeof state === "undefined" || !state || state.viewMode === "source") return;
      var el = e.target;
      // 单击名称文字 → 直接编辑名称（同时进入/保持图片编辑模式，阶段 G）
      var capT = el && el.closest ? el.closest("[data--image-caption]") : null;
      if (capT && preview.contains(capT)) {
        if (!(EH.blockEditMode && EH.blockEditMode.blockType === "image")) {
          var capBlock = capT.closest(".-image-block");
          if (capBlock && preview.contains(capBlock)) {
            var capBi = parseInt(capBlock.getAttribute("data--block-index"), 10);
            if (!isNaN(capBi) && isImageBlock(capBi)) {
              enterBlockEditMode(capBlock, capBi);
            }
          }
        }
        if (EH.blockEditMode && EH.blockEditMode.blockType === "image") {
          startCaptionEdit(capT);
          e.preventDefault();
          return;
        }
      }
      if (EH.blockEditMode) return;
      var imgBlock = el && el.closest ? el.closest(".-image-block") : null;
      if (!imgBlock || !preview.contains(imgBlock)) return;
      var biImg = parseInt(imgBlock.getAttribute("data--block-index"), 10);
      if (isNaN(biImg)) return;
      if (!isImageBlock(biImg)) return;
      flog("CLK", "single click image block bi=" + biImg + " → enterBlockEditMode");
      enterBlockEditMode(imgBlock, biImg);
      e.preventDefault();
    });

    // Escape 退出
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && EH.blockEditMode) {
        e.preventDefault();
        exitBlockEditMode();
      }
    });

    // 点击块外部退出
    document.addEventListener("mousedown", function (e) {
      if (!EH.blockEditMode) return;
      var bar = document.getElementById("block-edit-bar");
      // 行内公式：检查 mathEl
      var editEl = EH.blockEditMode.blockEl || EH.blockEditMode.mathEl;
      if (bar && bar.contains(e.target)) return;
      if (editEl && editEl.contains(e.target)) return;
      // 点击在其他地方 → 退出
      exitBlockEditMode();
    });
  }

  /**
   * 属性提交后重新进入图片编辑模式（DOM 已重建，按源码行重新定位）
   * @param {number} srcLine — 1-based 源码行号
   */
  EH.reenterImageEdit = function (srcLine) {
    var el = document.querySelector('.-src-block[data--src-line="' + srcLine + '"]');
    if (!el) return;
    var bi = parseInt(el.getAttribute("data--block-index"), 10);
    if (isNaN(bi)) return;
    var M = window.MemoriaMapper;
    var doc = M ? M.getDoc() : null;
    if (!doc || !doc.blocks || bi < 0 || bi >= doc.blocks.length) return;
    if (doc.blocks[bi].type !== "image") return;
    enterBlockEditMode(el, bi);
  };

  /**
   * 名称（alt）提交后放置光标：定位到图片块相邻的可编辑文本（优先左侧块末尾，
   * 否则右侧块开头），避免提交后光标残留在图片块停靠点 / 文档开头等不合理位置
   * @param {number} srcLine — 1-based 源码行号
   */
  EH.placeCaretAfterNameEdit = function (srcLine) {
    var el = document.querySelector('.-src-block[data--src-line="' + srcLine + '"]');
    if (!el) return;
    var bi = parseInt(el.getAttribute("data--block-index"), 10);
    if (isNaN(bi)) return;
    var outIdx = findEditableBlockIndex(bi, -1);
    if (outIdx >= 0) {
      placeCursorInBlock(outIdx, true);
    } else {
      outIdx = findEditableBlockIndex(bi, 1);
      if (outIdx >= 0) placeCursorInBlock(outIdx, false);
    }
    setTimeout(function () { syncFromSelection("caption-submit"); }, 0);
  };

})();
