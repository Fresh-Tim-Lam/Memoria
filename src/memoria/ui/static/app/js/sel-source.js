/**
 * sel-source.js — 源码区选区（键盘 Shift+方向键 ／ 鼠标跨行拖拽）
 *
 * 用途：每个 `.-line-content` 是独立 contenteditable，**原生选区跨不过行边界**
 *      （实测：Shift+← 选到行首即卡住；跨行拖拽时浏览器只给到行粒度）。
 *      本模块自建 anchor/focus 记账并统一渲染选区。
 * 依据：docs/conventions/frontend-modules.md（R1 不进 app.js / R2 显式注入 / R5 复用 core）
 * 装配：window.MemoriaSelSource.init({ editor, closestLineEl, offsetWithinLine })
 * 状态：生效中，2026-09-15
 *
 * 行为规范（与预览区一致）：
 *   Shift+←/→        逐字符；到行首/行尾跨到邻行末尾/开头
 *   Ctrl+Shift+←/→   按词（英文单词 / 连续汉字段）
 *   Shift+↑/↓        换行并**保留列**
 *   鼠标跨行拖拽      两端都保留**真实字符位置**（不整行化、上拖不回到上一行行首）
 */
(function () {
  "use strict";

  var S = window.MemoriaSelSource = window.MemoriaSelSource || {};
  var C = window.MemoriaSelectionCore;
  var ARROWS = { ArrowUp: 1, ArrowDown: 1, ArrowLeft: 1, ArrowRight: 1 };

  var deps = null;
  var anchor = null;   // { line, offset } —— 键盘/拖拽共用的起点（拖拽时=按下点）
  var focus = null;    // { line, offset } —— 移动端
  var drag = null;     // { point, crossed }

  // ── DOM 定位 ──────────────────────────────────────────────────
  function lineEl(line) { return document.getElementById("line-" + line); }
  function contentOf(line) {
    var el = lineEl(line);
    return el ? el.querySelector(".-line-content") : null;
  }
  function textOf(line) {
    var c = contentOf(line);
    return c ? (c.textContent || "") : null;
  }
  function lineOfNode(node) {
    if (!node || !deps || !deps.closestLineEl) return 0;
    var el = deps.closestLineEl(node);
    return el ? +(el.dataset.line || 0) : 0;
  }

  /** 当前原生光标 → { line, offset } */
  function caretPos() {
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount) return null;
    var node = sel.focusNode || sel.anchorNode;
    var off = sel.focusNode ? sel.focusOffset : sel.anchorOffset;
    var line = lineOfNode(node);
    if (!line) return null;
    var c = contentOf(line);
    if (!c) return null;
    return { line: line, offset: C.textOffsetOf(c, node, off) };
  }

  /** 渲染 anchor→focus（方向无关，内部按行/偏移归一） */
  function render() {
    if (!anchor || !focus) return;
    var a = anchor, b = focus;
    if (a.line > b.line || (a.line === b.line && a.offset > b.offset)) { var t = a; a = b; b = t; }
    var ca = contentOf(a.line), cb = contentOf(b.line);
    if (!ca || !cb) return;
    C.renderRange(ca, a.offset, cb, b.offset);
  }

  // ── 键盘：Shift+方向键 ────────────────────────────────────────
  function shiftExtend(key, dir, word) {
    // 原生选区已折叠 ⇒ 光标被外部移动过（点击/普通方向键/撤销/编辑）→ 按当前光标重新起锚
    var sel = window.getSelection();
    var collapsed = !sel || !sel.rangeCount || sel.isCollapsed;
    if (!anchor || collapsed) {
      var cur = caretPos();
      if (!cur) return;
      anchor = { line: cur.line, offset: cur.offset };
      focus = { line: cur.line, offset: cur.offset };
    }
    if (key === "ArrowRight") {
      var tr = textOf(focus.line) || "";
      if (focus.offset < tr.length) {
        focus.offset = word ? Math.min(C.wordRight(tr, focus.offset), tr.length) : focus.offset + 1;
      } else if (textOf(focus.line + 1) !== null) {
        focus.line += 1;
        focus.offset = 0;
      } else { return; }
    } else if (key === "ArrowLeft") {
      var tl = textOf(focus.line) || "";
      if (focus.offset > 0) {
        focus.offset = word ? C.wordLeft(tl, focus.offset) : focus.offset - 1;
      } else if (textOf(focus.line - 1) !== null) {
        focus.line -= 1;
        focus.offset = (textOf(focus.line) || "").length;
      } else { return; }
    } else {
      var nl = focus.line + dir;
      if (textOf(nl) === null) return;
      focus.line = nl;
      focus.offset = Math.min(focus.offset, (textOf(nl) || "").length);   // 保留列
    }
    render();
  }

  function onKeydown(e) {
    if (!e.shiftKey || !ARROWS[e.key]) return;
    e.preventDefault();
    // capture 阶段截断：不让 app.js 的行级处理器再走一遍（两套光标逻辑会互相打架）
    e.stopPropagation();
    shiftExtend(
      e.key,
      (e.key === "ArrowRight" || e.key === "ArrowDown") ? 1 : -1,
      !!(e.ctrlKey || e.metaKey)
    );
  }

  // ── 鼠标：跨行拖拽 ────────────────────────────────────────────
  /**
   * 鼠标点 → { line, offset }
   * 优先用 caretRangeFromPoint 取**精确字符位置**；落在行外（行号槽/行间空白）时，
   * 按相对参考行的方向贴到该行开头（向下进入）或行尾（向上进入）。
   */
  function pointToPos(x, y, refLine) {
    var p = C.pointPos(x, y);
    if (p) {
      var line = lineOfNode(p.node);
      var c = line ? contentOf(line) : null;
      if (line && c) return { line: line, offset: deps.offsetWithinLine(p.node, p.offset, c) };
    }
    var hit = document.elementFromPoint ? document.elementFromPoint(x, y) : null;
    var row = hit && hit.closest ? hit.closest(".-line") : null;
    if (!row) return null;
    var n = +(row.dataset.line || 0);
    if (!n) return null;
    return { line: n, offset: (n >= (refLine || n)) ? 0 : (textOf(n) || "").length };
  }

  function markLines(lo, hi) {
    clearLines();
    for (var n = Math.min(lo, hi); n <= Math.max(lo, hi); n++) {
      var el = lineEl(n);
      if (el) el.classList.add("is-drag-select");
    }
  }

  function clearLines() {
    document.querySelectorAll("#editor .-line.is-drag-select").forEach(function (el) {
      el.classList.remove("is-drag-select");
    });
  }

  function onMousedown(e) {
    if (e.button !== 0 || !e.target.closest) return;
    if (!e.target.closest(".-line-content")) return;
    var line = lineOfNode(e.target);
    if (!line) return;
    // ★ 锚点保留**真实字符位置**：旧实现只记行号，导致跨行拖拽时本行被整行选中、
    //   上拖时边界回退到上一行行首
    var pt = pointToPos(e.clientX, e.clientY, line);
    drag = { point: { line: line, offset: pt && pt.line === line ? pt.offset : 0 }, crossed: false };
  }

  function onMousemove(e) {
    if (!drag || e.buttons !== 1) return;
    var cur = pointToPos(e.clientX, e.clientY, drag.point.line);
    if (!cur) return;
    if (!drag.crossed && cur.line === drag.point.line) return;   // 单行内仍交给浏览器原生
    drag.crossed = true;
    anchor = { line: drag.point.line, offset: drag.point.offset };
    focus = { line: cur.line, offset: cur.offset };
    render();
    markLines(drag.point.line, cur.line);
  }

  function onMouseup() {
    if (!drag) return;
    if (drag.crossed) render();
    drag = null;
    clearLines();
  }

  function onDblclick(e) {
    if (!e.target.closest) return;
    if (!e.target.closest(".-line-content")) return;
    var line = lineOfNode(e.target);
    if (!line) return;
    e.preventDefault();
    anchor = { line: line, offset: 0 };
    focus = { line: line, offset: (textOf(line) || "").length };
    render();
  }

  // ── 装配 ──────────────────────────────────────────────────────
  S.init = function (d) {
    deps = d || {};
    if (!deps.editor || !C) return false;
    deps.editor.addEventListener("keydown", onKeydown, true);
    deps.editor.addEventListener("mousedown", onMousedown);
    deps.editor.addEventListener("mousemove", onMousemove);
    deps.editor.addEventListener("mouseup", onMouseup);
    window.addEventListener("mouseup", onMouseup);
    deps.editor.addEventListener("dblclick", onDblclick);
    return true;
  };
})();
