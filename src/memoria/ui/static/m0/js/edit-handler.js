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
      _previewCursorBlock.classList.remove("m0-preview-cursor");
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
    var blocks = document.querySelectorAll('.m0-src-block[data-m0-src-line]');
    var targetBlock = null;
    for (var i = 0; i < blocks.length; i++) {
      var s = parseInt(blocks[i].getAttribute("data-m0-src-line"), 10);
      var e = parseInt(blocks[i].getAttribute("data-m0-src-line-end"), 10) || s;
      if (srcLine >= s && srcLine <= e) {
        targetBlock = blocks[i];
        break;
      }
    }
    if (!targetBlock) return;

    // 不可编辑 block：不显示光标
    var blockIdx = parseInt(targetBlock.getAttribute("data-m0-block-index"), 10);
    if (isNonEditableBlock(blockIdx)) return;

    // 可编辑 block：添加光标指示
    targetBlock.classList.add("m0-preview-cursor");
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
    var lineEl = document.querySelector("#line-" + srcLine + " .m0-line-content");
    if (!lineEl) return;
    var node = lineEl.firstChild;
    if (!node || node.nodeType !== 3) return;
    var safeCol = Math.min(Math.max(0, srcCol), node.textContent.length);
    var afterNode = node.splitText(safeCol);
    var cursor = document.createElement("span");
    cursor.className = "m0-sync-cursor";
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

    // 行号：从 DOM 的 data-m0-src-line 获取（由 stampBlockLines 精确计算）
    // astToSrc 的 line 对 frontmatter/多行 block 计算不准确
    var srcLine = srcPos.line;  // 0-based fallback
    var blockEl = document.querySelector('.m0-src-block[data-m0-block-index="' + astPos.blockIndex + '"]');
    if (blockEl) {
      var dl = parseInt(blockEl.getAttribute("data-m0-src-line"), 10);
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
    var srcLineEl = document.querySelector("#line-" + srcLine + " .m0-line-content");
    var srcLineText = srcLineEl ? (srcLineEl.textContent || "") : "";
    var blockEl = block ? document.querySelector('.m0-src-block[data-m0-block-index="' + blockIndex + '"]') : null;
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
    [T.CODE_BLOCK, T.MATH_BLOCK, T.MERMAID, T.TABLE, T.FRONTMATTER].forEach(function (t) {
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
    while (el && !(el.classList && el.classList.contains("m0-src-block"))) {
      el = el.parentElement;
    }
    if (!el) { flog("GBI", "→ -1 (anchor=" + tag + " off=" + off + " no .m0-src-block)"); return -1; }
    var bi = parseInt(el.getAttribute("data-m0-block-index"), 10);
    flog("GBI", "→ " + bi + " (anchor=" + tag + " off=" + off + ")");
    return bi;
  }

  function placeCursorInBlock(blockIndex, atEnd) {
    var el = document.querySelector('.m0-src-block[data-m0-block-index="' + blockIndex + '"]');
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
    // 没有文本节点（空行 block）→ 在 block 元素上放置光标
    if (!first) {
      flog("PCB", "  no text nodes → placing on blockEl directly");
      var r0 = document.createRange();
      r0.setStart(el, 0);
      r0.collapse(true);
      var s0 = window.getSelection();
      s0.removeAllRanges();
      s0.addRange(r0);
      flog("PCB", "  → OK (empty block)");
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
      if (el.classList && el.classList.contains("m0-src-block")) { blockEl = el; break; }
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
      if (!lastText) { flog("EDGE", "isAtBlockEdge(1) → false (no lastText, empty block)"); return false; }
      var isLast = sel.anchorNode === lastText && sel.anchorOffset >= (lastText.textContent || "").length;
      flog("EDGE", "isAtBlockEdge(1) anchor='" + (sel.anchorNode.textContent || "").substring(0, 15) + "' off=" + sel.anchorOffset + " lastText='" + (lastText.textContent || "").substring(0, 15) + "' len=" + (lastText.textContent || "").length + " → " + isLast);
      return isLast;
    } else {
      // 开头：光标在第一个文本节点的开头
      var firstText = walker.nextNode();
      if (!firstText) { flog("EDGE", "isAtBlockEdge(-1) → false (no firstText)"); return false; }
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
      var walkEl = clickTarget;
      while (walkEl && !(walkEl.classList && walkEl.classList.contains("m0-src-block"))) {
        walkEl = walkEl.parentElement;
      }
      if (walkEl) {
        var clickBi = parseInt(walkEl.getAttribute("data-m0-block-index"), 10);
        if (!isNaN(clickBi) && isNonEditableBlock(clickBi)) {
          flog("MOUSE", "mouseup on non-editable block " + clickBi + " → skip sync (allow dblclick)");
          return;
        }
      }

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

      // ── Case A: 当前 block 不可编辑 → preventDefault + 跳到下一个可编辑 block ──
      if (isNonEditableBlock(curBlkIdx)) {
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
      //    所有方向键都做边界检查：在边界且下一 block 不可编辑 → 跳过
      var atEdge = isAtBlockEdge(dir);
      flog("CASB", "Case B: curBlk " + curBlkIdx + " atEdge(" + dir + ")=" + atEdge);
      if (atEdge) {
        var nextBlk = curBlkIdx + dir;
        flog("CASB", "  nextBlk=" + nextBlk);
        // 下一个 block 不可编辑 → preventDefault + 跳过
        if (nextBlk >= 0 && isNonEditableBlock(nextBlk)) {
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
        var sel = '<select id="blk-lang-sel" class="m0-block-lang-sel" title="语言">';
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
        var html = '<span class="m0-block-edit-hint">类型:</span><select id="blk-mermaid-type" class="m0-block-lang-sel">';
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
        var html = '<span class="m0-block-edit-hint">符号:</span>';
        for (var i = 0; i < syms.length; i++) {
          html += '<button type="button" class="m0-math-sym-btn" data-sym="' + syms[i] + '">' + syms[i] + "</button>";
        }
        return html;
      }
    },
    table: {
      label: "编辑表格",
      tools: function () {
        return '<button type="button" class="m0-fmt-btn" id="blk-add-row" title="添加行">+行</button>' +
               '<button type="button" class="m0-fmt-btn" id="blk-add-col" title="添加列">+列</button>';
      }
    }
  };

  /**
   * 进入行内公式编辑模式
   * @param {HTMLElement} mathEl — .m0-math span 或 mjx-container[data-m0-inline-math] 元素
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
      // 原始 .m0-math span：从 data-formula 或 textContent 获取
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
    var fmtBar = document.querySelector(".m0-format-bar");
    var blkBar = document.getElementById("block-edit-bar");
    if (fmtBar) fmtBar.classList.add("hidden");
    if (blkBar) blkBar.classList.remove("hidden");

    var labelEl = document.getElementById("block-edit-label");
    if (labelEl) labelEl.textContent = "编辑行内公式";

    // 生成符号工具栏
    var toolsEl = document.getElementById("block-edit-tools");
    if (toolsEl) {
      var syms = ["α","β","γ","δ","θ","λ","μ","π","σ","φ","ω","∑","∏","∫","∂","∞","≤","≥","≠","±","×","÷","√","∈","∉","⊂","⊃","∪","∩","∀","∃"];
      var html = '<span class="m0-block-edit-hint">符号:</span>';
      for (var i = 0; i < syms.length; i++) {
        html += '<button type="button" class="m0-math-sym-btn" data-sym="' + syms[i] + '">' + syms[i] + "</button>";
      }
      toolsEl.innerHTML = html;

      // 绑定符号按钮：在光标处插入符号
      toolsEl.querySelectorAll(".m0-math-sym-btn").forEach(function (btn) {
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
    mathEl.classList.add("m0-block-editing");
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
    var srcStart = parseInt(blockEl.getAttribute("data-m0-src-line"), 10) || 0;
    var srcEnd = parseInt(blockEl.getAttribute("data-m0-src-line-end"), 10) || srcStart;

    EH.blockEditMode = { blockIndex: blockIndex, blockEl: blockEl, blockType: blockType, srcStart: srcStart, srcEnd: srcEnd };

    // 切换工具栏
    var fmtBar = document.querySelector(".m0-format-bar");
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
    blockEl.classList.add("m0-block-editing");

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
      var symBtns = document.querySelectorAll(".m0-math-sym-btn");
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
      mathEl.classList.remove("m0-block-editing");

      _restoreToolbar();
      EH.blockEditMode = null;

      if (changed && typeof state !== "undefined" && state) {
        // 找到包含此公式的源码行并替换
        var editor = document.getElementById("editor");
        if (editor) {
          var lineEls = editor.querySelectorAll(".m0-line-content");
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
      // .m0-math span 如果未修改则可以直接显示 $formula$ 文本
      if (ctx.isMjxContainer || changed) {
        if (typeof state !== "undefined" && state) {
          if (typeof window._scheduleRender === "function") window._scheduleRender();
          else if (typeof window.renderPreview === "function") window.renderPreview();
        }
      } else {
        // .m0-math span 未修改：恢复 $formula$ 文本
        mathEl.textContent = "$" + newFormula + "$";
      }
      flog("DBL", "exit inline math: changed=" + changed + " new=" + newFormula + " mjx=" + (ctx.isMjxContainer || false));
      return;
    }

    // ── 块级编辑退出 ──
    var blockEl = ctx.blockEl;

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
    var lineEls = editor.querySelectorAll(".m0-line-content");
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
          return '<div class="m0-line" data-line="' + n + '" id="line-' + n + '">' +
            '<span class="m0-lineno">' + n + '</span>' +
            '<span class="m0-line-content" contenteditable="true" spellcheck="false" tabindex="-1">' +
            (line || "") + '</span></div>';
        }).join("");
      }
    }

    // 恢复 block 不可编辑
    blockEl.contentEditable = "false";
    blockEl.classList.remove("m0-block-editing");

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
    var fmtBar = document.querySelector(".m0-format-bar");
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
      if (EH.blockEditMode) { flog("DBL", "already in blockEditMode → return"); return; }

      // ── 检查是否双击了行内公式 (.m0-math 或 mjx-container[data-m0-inline-math]) ──
      // MathJax typeset 后 .m0-math span 可能被替换为 mjx-container，
      // 因此同时检查两种标记
      var mathEl = e.target;
      while (mathEl && mathEl !== preview) {
        if (mathEl.classList && mathEl.classList.contains("m0-math")) break;
        if (mathEl.tagName === "MJX-CONTAINER" && mathEl.getAttribute("data-m0-inline-math") === "true") break;
        mathEl = mathEl.parentElement;
      }
      if (mathEl && mathEl !== preview) {
        var isMathSpan = mathEl.classList && mathEl.classList.contains("m0-math");
        var isInlineMjx = mathEl.tagName === "MJX-CONTAINER" && mathEl.getAttribute("data-m0-inline-math") === "true";
        if (isMathSpan || isInlineMjx) {
          flog("DBL", "→ inline math edit mode (" + (isInlineMjx ? "mjx-container" : ".m0-math") + ")");
          enterInlineMathEditMode(mathEl);
          e.preventDefault();
          return;
        }
      }

      // ── 检查是否双击了不可编辑 block ──
      var el = e.target;
      while (el && !(el.classList && el.classList.contains("m0-src-block"))) {
        el = el.parentElement;
      }
      if (!el) { flog("DBL", "no .m0-src-block ancestor → return"); return; }

      var bi = parseInt(el.getAttribute("data-m0-block-index"), 10);
      flog("DBL", "found .m0-src-block bi=" + bi + " tag=" + el.tagName + " ce=" + el.contentEditable);
      if (isNaN(bi)) { flog("DBL", "bi NaN → return"); return; }

      var ned = isNonEditableBlock(bi);
      flog("DBL", "isNonEditableBlock(" + bi + ")=" + ned);
      if (!ned) { flog("DBL", "editable block → return"); return; }

      flog("DBL", "→ enterBlockEditMode(" + bi + ")");
      enterBlockEditMode(el, bi);
    });

    // 完成按钮
    var doneBtn = document.getElementById("block-edit-done");
    if (doneBtn) {
      doneBtn.addEventListener("click", function () { exitBlockEditMode(); });
    }

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

})();
