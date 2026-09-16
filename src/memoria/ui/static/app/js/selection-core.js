/**
 * selection-core.js — 选区共享内核（**唯一实现**）
 *
 * 用途：给「预览区」「源码区」两套选区逻辑提供同一份纯函数，
 *      避免同一件事写两遍、避免用 `EH.xxx` 之类私有导出在文件间互相借。
 * 依据：docs/conventions/frontend-modules.md（R2 依赖注入 / R5 共享工具唯一实现）
 * 状态：生效中，2026-09-15
 *
 * 对外接口（window.MemoriaSelectionCore）：
 *   wordLeft(text, from) → 左侧词/汉字段边界偏移
 *   wordRight(text, from) → 右侧词/汉字段边界偏移
 *   textPosAt(el, offset) → { node, offset }  （el 内无文本节点时落到元素本身）
 *   textOffsetOf(el, node, offsetInNode) → 该位置在 el 内的文本偏移
 *   renderRange(ca, offA, cb, offB) → 按 (元素, 偏移) 设置浏览器选区
 *   pointPos(x, y) → { node, offset } 鼠标点对应的文档位置（可能为 null）
 */
(function () {
  "use strict";

  var C = window.MemoriaSelectionCore = window.MemoriaSelectionCore || {};

  // ── 词边界 ────────────────────────────────────────────────────
  // 英文/数字/下划线 = 一个词；连续汉字/假名 = 一个"大块"（中文里一次跳一大段）；
  // 其余（空白、标点、`<` `/` `|` 等）视为分隔符，跳过。
  function isCJK(ch) { return /[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]/.test(ch); }
  function isWordChar(ch) { return /[A-Za-z0-9_]/.test(ch); }
  function isSep(ch) { return !isCJK(ch) && !isWordChar(ch); }

  C.wordLeft = function (text, from) {
    var i = from;
    while (i > 0 && isSep(text[i - 1])) i--;
    if (i === 0) return 0;
    if (isCJK(text[i - 1])) { while (i > 0 && isCJK(text[i - 1])) i--; }
    else { while (i > 0 && isWordChar(text[i - 1])) i--; }
    return i;
  };

  C.wordRight = function (text, from) {
    var n = text.length, i = from;
    while (i < n && isSep(text[i])) i++;
    if (i >= n) return n;
    if (isCJK(text[i])) { while (i < n && isCJK(text[i])) i++; }
    else { while (i < n && isWordChar(text[i])) i++; }
    return i;
  };

  // ── 文本偏移 ↔ DOM 位置 ───────────────────────────────────────
  /** 元素内文本偏移 → DOM 位置（无文本节点时落到元素本身，偏移 0） */
  C.textPosAt = function (el, offset) {
    if (!el) return null;
    var total = (el.textContent || "").length;
    var off = Math.max(0, Math.min(offset, total));
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    var acc = 0, last = null, n;
    while ((n = w.nextNode())) {
      var len = (n.textContent || "").length;
      if (off <= acc + len) return { node: n, offset: Math.max(0, off - acc) };
      acc += len;
      last = n;
    }
    return last ? { node: last, offset: (last.textContent || "").length } : { node: el, offset: 0 };
  };

  /** 文本节点位置 → 元素内文本偏移（元素内可能多段文本，如假光标 span 把文本切成两段） */
  C.textOffsetOf = function (el, node, offsetInNode) {
    if (!el || !node) return 0;
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    var acc = 0, n;
    while ((n = w.nextNode())) {
      if (n === node) return acc + offsetInNode;
      acc += (n.textContent || "").length;
    }
    return Math.min(offsetInNode, (el.textContent || "").length);
  };

  /** 按 (元素, 偏移) 设置浏览器选区；返回是否成功 */
  C.renderRange = function (ca, offA, cb, offB) {
    var pa = C.textPosAt(ca, offA);
    var pb = C.textPosAt(cb, offB);
    if (!pa || !pb) return false;
    var r = document.createRange();
    try {
      r.setStart(pa.node, pa.offset);
      r.setEnd(pb.node, pb.offset);
    } catch (err) { return false; }
    var sel = window.getSelection();
    if (!sel) return false;
    sel.removeAllRanges();
    sel.addRange(r);
    return true;
  };

  /** 鼠标点 → 文档位置（Chromium: caretRangeFromPoint；Firefox: caretPositionFromPoint） */
  C.pointPos = function (x, y) {
    if (document.caretRangeFromPoint) {
      var r = document.caretRangeFromPoint(x, y);
      return r ? { node: r.startContainer, offset: r.startOffset } : null;
    }
    if (document.caretPositionFromPoint) {
      var p = document.caretPositionFromPoint(x, y);
      return p ? { node: p.offsetNode, offset: p.offset } : null;
    }
    return null;
  };
})();
