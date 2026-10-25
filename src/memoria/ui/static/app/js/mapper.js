/**
 * MemoriaMapper — 位置映射器
 * Phase 5: AST ↔ Source ↔ DOM 坐标双向转换
 * 依赖: MemoriaAST, MemoriaParser, MemoriaSourceGen
 */

window.MemoriaMapper = (function () {
  "use strict";

  var AST = MemoriaAST;
  var T = AST.TYPES;
  var parser = MemoriaParser;
  var sourceGen = MemoriaSourceGen;

  /**
   * 获取 inline 节点的源码前缀长度
   * @param {object} node — inline AST node
   * @returns {number}
   */
  function inlinePrefixLen(node) {
    switch (node.type) {
      case T.BOLD: return 2;           // **
      case T.ITALIC: return 1;         // *
      case T.BOLD_ITALIC: return 3;    // ***
      case T.STRIKETHROUGH: return 2;  // ~~
      case T.CODE: return 1;           // `
      case T.HIGHLIGHT:
        var hlLen = 5;  // [[\h|
        if (node.color) hlLen = 6 + node.color.length;  // [[\h:color|
        if (node.fgColor) hlLen += 1 + node.fgColor.length;  // :fgColor
        return hlLen;
      case T.FONT_COLOR: return 6 + node.color.length;   // [[\c:color|
      case T.FONT_SIZE: return 6 + (node.size || "").length; // [[\s:size|
      case T.FONT_BOLD: return 5;       // [[\b|
      case T.FONT_ITALIC: return 5;     // [[\i|
      case T.FONT_UNDERLINE: return 5;  // [[\u|
      case T.FONT_SUPERSCRIPT: return 7; // [[\sup|
      case T.FONT_SUBSCRIPT: return 7;   // [[\sub|
      case T.WIKI_LINK:
        if (node.display) return 2 + node.target.length + 1; // [[target|
        return 2;      // [[
      case T.LINK: return 1;           // [
      case T.MATH_INLINE: return 1;    // $
      case T.ESCAPE: return 1;         // \
      case T.TEXT: return 0;
      default: return 0;
    }
  }

  /**
   * 获取 inline 节点的源码后缀长度
   * @param {object} node
   * @returns {number}
   */
  function inlineSuffixLen(node) {
    switch (node.type) {
      case T.BOLD: return 2;           // **
      case T.ITALIC: return 1;         // *
      case T.BOLD_ITALIC: return 3;    // ***
      case T.STRIKETHROUGH: return 2;  // ~~
      case T.CODE: return 1;           // `
      case T.HIGHLIGHT: return 2;      // ]]
      case T.FONT_COLOR: return 2;     // ]]
      case T.FONT_SIZE: return 2;      // ]]
      case T.FONT_BOLD: return 2;      // ]]
      case T.FONT_ITALIC: return 2;    // ]]
      case T.FONT_UNDERLINE: return 2; // ]]
      case T.FONT_SUPERSCRIPT: return 2; // ]]
      case T.FONT_SUBSCRIPT: return 2;  // ]]
      case T.WIKI_LINK: return 2;      // ]]
      case T.LINK: return 0;           // already in link_close
      case T.MATH_INLINE: return 1;    // $
      case T.ESCAPE: return 0;
      case T.TEXT: return 0;
      default: return 0;
    }
  }

  /**
   * 获取 inline 节点的渲染文本长度
   * @param {object} node
   * @returns {number}
   */
  function renderedLen(node) {
    if (!node) return 0;
    if (node.type === T.TEXT) return node.content.length;
    if (node.type === T.CODE) return node.code.length;
    if (node.type === T.ESCAPE) return 1;
    if (node.type === T.MATH_INLINE) return node.formula.length;
    if (node.type === T.WIKI_LINK) return (node.display || node.target).length;
    if (node.type === T.LINK) return node.text.length;
    if (node.children) {
      var total = 0;
      for (var i = 0; i < node.children.length; i++) {
        total += renderedLen(node.children[i]);
      }
      return total;
    }
    return 0;
  }

  /**
   * 源码列 → 渲染偏移（在给定 inline 节点内）
   * @param {object} node — inline AST 节点
   * @param {number} srcCol — 源码列偏移（相对于该节点开头）
   * @returns {{renderedOffset:number, targetNode:object}|null}
   */
  function srcColToRendered(node, srcCol) {
    if (!node) return null;

    // Text 节点：直接映射
    if (node.type === T.TEXT) {
      if (srcCol >= 0 && srcCol <= node.content.length) {
        return { renderedOffset: srcCol, targetNode: node };
      }
      return null;
    }

    // 叶子节点（无 children）
    if (node.type === T.CODE) {
      if (srcCol >= 0 && srcCol <= node.code.length) {
        return { renderedOffset: srcCol, targetNode: node };
      }
      return null;
    }
    if (node.type === T.ESCAPE) {
      return { renderedOffset: 0, targetNode: node };
    }
    if (node.type === T.MATH_INLINE) {
      if (srcCol >= 0 && srcCol <= node.formula.length) {
        return { renderedOffset: srcCol, targetNode: node };
      }
      return null;
    }
    if (node.type === T.WIKI_LINK) {
      var display = node.display || node.target;
      if (srcCol >= 0 && srcCol <= display.length) {
        return { renderedOffset: srcCol, targetNode: node };
      }
      return null;
    }
    if (node.type === T.LINK) {
      if (srcCol >= 0 && srcCol <= node.text.length) {
        return { renderedOffset: srcCol, targetNode: node };
      }
      return null;
    }

    // 有 children 的节点：递归
    var prefix = inlinePrefixLen(node);
    var pos = prefix;
    var renderedPos = 0;

    for (var i = 0; i < (node.children || []).length; i++) {
      var child = node.children[i];
      var childSrcLen = inlineSourceLen(child);

      if (srcCol >= pos && srcCol <= pos + childSrcLen) {
        var result = srcColToRendered(child, srcCol - pos);
        if (result) {
          result.renderedOffset += renderedPos;
          return result;
        }
        return null;
      }
      pos += childSrcLen;
      renderedPos += renderedLen(child);
    }

    // 在后缀或超出范围
    var suffix = inlineSuffixLen(node);
    if (srcCol >= pos && srcCol <= pos + suffix) {
      return { renderedOffset: renderedPos, targetNode: node };
    }

    return null;
  }

  /**
   * 渲染偏移 → 源码列（在给定 inline 节点内）
   * @param {object} node
   * @param {number} renderedOffset
   * @param {boolean} [preferEnd=true] — 边界位置时，true=偏好当前子节点(<=)，false=偏好下一个子节点(<)
   * @returns {{srcCol:number, leafOffset:number, targetNode:object}|null}
   */
  function renderedToSrcCol(node, renderedOffset, preferEnd) {
    if (preferEnd === undefined) preferEnd = true;
    if (!node) return null;

    if (node.type === T.TEXT) {
      if (renderedOffset >= 0 && renderedOffset <= node.content.length) {
        return { srcCol: renderedOffset, leafOffset: renderedOffset, targetNode: node };
      }
      return null;
    }

    if (node.type === T.CODE) {
      if (renderedOffset >= 0 && renderedOffset <= node.code.length) {
        return { srcCol: renderedOffset, leafOffset: renderedOffset, targetNode: node };
      }
      return null;
    }
    if (node.type === T.ESCAPE) {
      return { srcCol: 0, leafOffset: 0, targetNode: node };
    }
    if (node.type === T.MATH_INLINE) {
      if (renderedOffset >= 0 && renderedOffset <= node.formula.length) {
        return { srcCol: renderedOffset, leafOffset: renderedOffset, targetNode: node };
      }
      return null;
    }
    if (node.type === T.WIKI_LINK) {
      var display = node.display || node.target;
      if (renderedOffset >= 0 && renderedOffset <= display.length) {
        return { srcCol: renderedOffset, leafOffset: renderedOffset, targetNode: node };
      }
      return null;
    }
    if (node.type === T.LINK) {
      if (renderedOffset >= 0 && renderedOffset <= node.text.length) {
        return { srcCol: renderedOffset, leafOffset: renderedOffset, targetNode: node };
      }
      return null;
    }

    // 有 children 的节点
    var prefix = inlinePrefixLen(node);
    var srcPos = prefix;
    var renderedPos = 0;

    for (var i = 0; i < (node.children || []).length; i++) {
      var child = node.children[i];
      var childRenderedLen = renderedLen(child);

      var inRange = preferEnd
        ? (renderedOffset >= renderedPos && renderedOffset <= renderedPos + childRenderedLen)
        : (renderedOffset >= renderedPos && renderedOffset < renderedPos + childRenderedLen);

      if (inRange) {
        var result = renderedToSrcCol(child, renderedOffset - renderedPos, preferEnd);
        if (result) {
          result.srcCol += srcPos;
          return result;
        }
        return null;
      }
      srcPos += inlineSourceLen(child);
      renderedPos += childRenderedLen;
    }

    // 超出范围
    return { srcCol: srcPos, leafOffset: 0, targetNode: node };
  }

  /**
   * 计算 inline 节点的源码总长度
   * @param {object} node
   * @returns {number}
   */
  function inlineSourceLen(node) {
    if (!node) return 0;
    if (node.type === T.TEXT) return node.content.length;
    if (node.type === T.CODE) return node.code.length;
    if (node.type === T.ESCAPE) return 1;
    if (node.type === T.MATH_INLINE) return node.formula.length;
    if (node.type === T.WIKI_LINK) {
      // Full source: [[target|display]] or [[target]]
      return 4 + node.target.length + (node.display ? 1 + node.display.length : 0);
    }
    if (node.type === T.LINK) {
      // Full source: [text](url)
      return 4 + node.text.length + node.url.length;
    }
    return inlinePrefixLen(node) + inlineSuffixLen(node) +
      (node.children || []).reduce(function (s, c) { return s + inlineSourceLen(c); }, 0);
  }

  /**
   * 获取 block 的源码前缀长度（标题 #、引用 >、列表 - 等）
   * @param {object} block
   * @param {number} [itemIdx=0] — LIST_ITEM 专用：该项在所属 LIST 中的下标；
   *   有序列表的序号宽度随项变化（`9. ` 3 列 / `10. ` 4 列 / `100. ` 5 列），
   *   必须按真实序号位数计算，不能硬编码 2 列。
   * @returns {number}
   */
  function blockPrefixLen(block, itemIdx) {
    if (!block) return 0;
    switch (block.type) {
      case T.HEADING: return block.level + 1; // "## " = 3
      case T.BLOCKQUOTE: return 2;            // "> "
      case T.LIST_ITEM: return listItemPrefixLen(block, itemIdx); // "- " 或 "N. "
      default: return 0;
    }
  }

  /**
   * 列表项源码前缀长度：`"- "` = 2；有序列表按**真实序号位数**计算 `"N. "`。
   *
   * 口径必须与 lexer 一致（`lexer.js` 有序列表分支按 `om[2].length + 2` 推进列号），
   * 即「原始源码」列号。序号按 AST 的渲染语义取号：`block.items[i]` 的序号 =
   * `(block.start || 1) + i` —— 这正是 renderer 用 `<ol start=N>` 呈现的序号
   * （parser 的 `emit()` 把 `srcLine/srcLineEnd` 落在真实行区间、`items` 与行一一对应，
   * 因此第 i 个 item 落在 `srcLine + i` 行，其行首序号就是基准 + i）。
   *
   * 已知偏差（不在本修复范围，属规划期问题）：若源文档各列表项序号不连续/不从
   * 基准递增（如 `5. a` 后接 `12. b`），parser 只保留首项编号、丢弃后续原始数字，
   * 映射器无法恢复中间项的真实位数 —— 这需要在 AST/parser 层保留每个 item 的
   * 原始标记文本，超出本轮只改 mapper/source-gen 的修复边界。
   *
   * @param {object} item — LIST_ITEM 节点
   * @param {number} [itemIdx=0]
   * @returns {number}
   */
  function listItemPrefixLen(item, itemIdx) {
    var idx = (typeof itemIdx === "number" && isFinite(itemIdx) && itemIdx >= 0) ? Math.floor(itemIdx) : 0;
    // 行内带 `ordered` 标记的 item（非 parser 标准产物，防御性支持）
    if (item && item.ordered === false) return 2;
    // 位于 LIST 上（parser 标准结构：item 自身不带 ordered/start）
    if (item && typeof item.ordered === "boolean") {
      return item.ordered ? String((item.start || 1) + idx).length + 2 : 2;
    }
    return 2;
  }

  /**
   * 由 LIST block + item 下标求该项的源码前缀长度（`"- "` 或 `"N. "`）
   * @param {object} listBlock — LIST 节点
   * @param {number} itemIdx
   * @returns {number}
   */
  function listPrefixLen(listBlock, itemIdx) {
    if (!listBlock) return 2;
    var idx = (typeof itemIdx === "number" && isFinite(itemIdx) && itemIdx > 0) ? Math.floor(itemIdx) : 0;
    var item = (listBlock.items && listBlock.items[idx]) || null;
    if (item) {
      // item 自带 ordered 标记时以其为准（防御性）；否则用列表头
      if (typeof item.ordered !== "boolean" && typeof listBlock.ordered === "boolean") {
        return listBlock.ordered ? String((listBlock.start || 1) + idx).length + 2 : 2;
      }
      return listItemPrefixLen(item, idx);
    }
    if (typeof listBlock.ordered === "boolean") {
      return listBlock.ordered ? String((listBlock.start || 1) + idx).length + 2 : 2;
    }
    return 2;
  }

  // ── task-155（一期）：引用块的行跨度/前缀宽度/引用内列表映射 ──────────────
  /** 引用块内某源码行（0-based 绝对）的**真实前缀宽度**。
   *  E28 允许 `>` / `> ` / `>> ` / `>\t` 等前缀；旧实现恒用 2（`"> "`）⇒
   *  `>abc`（实际内容起点 1）与 `>> abc`（实际 3）都偏 1 列。修复依据 = `block.prefixes`。 */
  function _quotePfxLenAt(block, lineIdx0) {
    var p = block && block.prefixes;
    var base = (block && block.srcLine > 0) ? block.srcLine - 1 : 0;
    var i = lineIdx0 - base;
    if (Array.isArray(p) && i >= 0 && i < p.length && typeof p[i] === "string" && p[i].length) {
      return p[i].length;
    }
    return 2; // 旧 AST（无 prefixes）：退回历史口径
  }

  /** 引用内列表：由源码行反推 item 下标（item.srcLine 是"引用切片内相对 1-based"） */
  function _quoteListItemIndex(block, list, lineIdx0) {
    var qBase = (block && block.srcLine > 0) ? block.srcLine - 1 : 0;
    var items = (list && list.items) || [];
    var best = -1;
    for (var i2 = 0; i2 < items.length; i2++) {
      var it = items[i2];
      if (it && it.srcLine > 0) {
        var abs = qBase + it.srcLine - 1;
        if (abs === lineIdx0) return i2;
        if (abs <= lineIdx0) best = i2;
      }
    }
    if (best >= 0) return best;
    var rel = lineIdx0 - (list.srcLine > 0 ? list.srcLine - 1 : qBase);
    if (rel < 0) rel = 0;
    if (rel >= items.length) rel = items.length - 1;
    return rel;
  }

  /** 在 inline 节点树里定位（与 findInlineAtSrcCol 同口径，但路径前缀已给定） */
  function _quoteInlineAt(node, srcCol, path) {
    if (!node) return null;
    if (node.type === T.TEXT) {
      if (srcCol >= 0 && srcCol <= node.content.length) {
        return { blockIndex: -1, nodePath: path, offset: srcCol };
      }
      return null;
    }
    var kids = node.children || [];
    if (!kids.length) return { blockIndex: -1, nodePath: path, offset: srcCol };
    var pos = inlinePrefixLen(node);
    for (var i3 = 0; i3 < kids.length; i3++) {
      var sl = inlineSourceLen(kids[i3]);
      if (srcCol >= pos && srcCol < pos + sl) {
        return _quoteInlineAt(kids[i3], srcCol - pos, path.concat(i3));
      }
      pos += sl;
    }
    return { blockIndex: -1, nodePath: path, offset: srcCol };
  }

  /** 引用内列表：AST 坐标 → 源码行列（path[0]=itemIdx，其后为 item 内 inline 路径） */
  function _quoteListAstToSrc(block, list, path, offset, lineBase0) {
    var items = list.items || [];
    var itemIdx = (path && path.length) ? path[0] : 0;
    if (itemIdx >= items.length) itemIdx = Math.max(0, items.length - 1);
    var item = items[itemIdx] || null;
    var itemLine = (item && item.srcLine > 0) ? lineBase0 + item.srcLine - 1 : lineBase0 + itemIdx;
    var qPfx = _quotePfxLenAt(block, itemLine);
    var col = qPfx + listPrefixLen(list, itemIdx);
    if (!item) return { line: itemLine, col: col + offset };
    var inlinePath = (path || []).slice(1);
    var qInline = item.children || [];
    if (!inlinePath.length) return { line: itemLine, col: col + offset };
    var node = qInline[inlinePath[0]];
    if (!node) return { line: itemLine, col: col };
    for (var p2 = 0; p2 < inlinePath[0]; p2++) col += inlineSourceLen(qInline[p2]);
    col += inlinePrefixLen(node);
    for (var d2 = 1; d2 < inlinePath.length; d2++) {
      var idx2 = inlinePath[d2];
      if (!node.children || idx2 >= node.children.length) break;
      for (var k2 = 0; k2 < idx2; k2++) col += inlineSourceLen(node.children[k2]);
      node = node.children[idx2];
      col += inlinePrefixLen(node);
    }
    return { line: itemLine, col: col + offset };
  }

  /** 引用内列表：源码行列 → AST 坐标（nodePath 含 blockquote child 下标） */
  function _quoteListSrcToAst(block, list, childIdx, lineIdx0, col, qPfx, blockIndex) {
    var items = list.items || [];
    var itemIdx = _quoteListItemIndex(block, list, lineIdx0);
    var colInItem = col - qPfx - listPrefixLen(list, itemIdx);
    if (colInItem < 0) colInItem = 0;
    var item = items[itemIdx];
    var qInline = (item && item.children) || [];
    if (!qInline.length) return { blockIndex: blockIndex, nodePath: [childIdx, itemIdx], offset: 0 };
    var pos = 0;
    for (var j3 = 0; j3 < qInline.length; j3++) {
      var sl3 = inlineSourceLen(qInline[j3]);
      if (colInItem >= pos && colInItem < pos + sl3) {
        var inner3 = _quoteInlineAt(qInline[j3], colInItem - pos, [childIdx, itemIdx, j3]);
        if (inner3) { inner3.blockIndex = blockIndex; return inner3; }
        return { blockIndex: blockIndex, nodePath: [childIdx, itemIdx, j3], offset: 0 };
      }
      pos += sl3;
    }
    return { blockIndex: blockIndex, nodePath: [childIdx, itemIdx, qInline.length - 1], offset: 0 };
  }

  /**
   * 源码行/列 → AST 坐标
   * @param {number} line — 0-based 源码行号
   * @param {number} col — 0-based 源码列号
   * @returns {{blockIndex:number, nodePath:number[], offset:number}|null}
   */
  function srcToAst(line, col) {
    // 需要 doc 引用，由外部设置
    var doc = _currentDoc;
    if (!doc || !doc.blocks) return null;

    // 找到包含该行的 block：**优先**用块自带源码行区间（parser 落的 `srcLine`/`srcLineEnd` = 单一事实源）；
    // 缺字段才退回按 `blockLineCount` 逐块累加（历史口径，仅兜底）。`lineCount` 语义 = 该块 0 基首行。
    var blockIndex = -1;
    var lineCount = 0;
    for (var i = 0; i < doc.blocks.length; i++) {
      var b = doc.blocks[i];
      var bLines = b && b.srcLineEnd >= b.srcLine ? b.srcLineEnd - b.srcLine + 1 : blockLineCount(b);
      var bStart = b && b.srcLine > 0 ? b.srcLine - 1 : lineCount;
      if (line >= bStart && line < bStart + bLines) {
        blockIndex = i; lineCount = bStart; break;
      }
      lineCount = bStart + bLines;
    }

    if (blockIndex === -1) return null;

    var block = doc.blocks[blockIndex];
    var inlineNodes = block.children || [];

    // 如果 block 没有 inline children（如 blank_line, image），返回 block 级位置
    if (!inlineNodes || inlineNodes.length === 0) {
      return { blockIndex: blockIndex, nodePath: [], offset: 0 };
    }

    // 在 inline 节点中查找
    var prefix = blockPrefixLen(block);
    // 注：LIST/BLOCKQUOTE 是**块级**节点（内容在 items/children 里，不在 children 上），
    // 它们的源码带多行 `- `/`N. `/`> ` 前缀，**不适用**下面这套「单行 inline + 块级前缀」
    // 口径 —— 真实行列在各自的专用分支里算（LIST 用 `listPrefixLen(block, itemIdx)`，
    // 逐项按真实序号位数，与 lexer 的 `om[2].length + 2` 对齐）。这里生成单行源码仅为
    // 兜底「光标在内容之后」的列号，不参与 LIST/BLOCKQUOTE 分支。
    // （生成器会对有序列表按解析序号连续编号，但该产物只影响无 nodePath 的兜底路径。）
    var srcLine = sourceGen.generateBlock(block);
    // 对于多行 block，使用该行的起始位置
    var blockLineStart = 0;
    // 简化：假设 block 是单行的（heading, paragraph）
    // 对于多行 block（code_block, math_block），返回 block 级位置
    if (block.type === T.CODE_BLOCK || block.type === T.MATH_BLOCK) {
      return { blockIndex: blockIndex, nodePath: [], offset: col };
    }

    // BLOCKQUOTE block（task-155 一期）：children 可能是**跨多行**的块级 list；
    //   行归属用每个 child 的 `srcLine/srcLineEnd`（parser 落的绝对行区间），
    //   前缀宽度用 `block.prefixes` 真实长度（修 `>` / `>> ` 的既有 off-by-one）。
    if (block.type === T.BLOCKQUOTE) {
      var qKids2 = block.children || [];
      if (!qKids2.length) return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      var qBase2 = block.srcLine > 0 ? block.srcLine - 1 : lineCount;
      var qSel = -1;
      for (var qc = 0; qc < qKids2.length; qc++) {
        var qk = qKids2[qc];
        var qs = qk && qk.srcLine > 0 ? qk.srcLine - 1 : qBase2 + qc;
        var qe = (qk && qk.srcLine > 0 && qk.srcLineEnd >= qk.srcLine) ? qk.srcLineEnd - 1 : qs;
        if (line >= qs && line <= qe) { qSel = qc; break; }
      }
      if (qSel < 0) return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      var qCh = qKids2[qSel];
      var qPfx = _quotePfxLenAt(block, line);
      if (qCh.type === T.LIST) {
        return _quoteListSrcToAst(block, qCh, qSel, line, col, qPfx, blockIndex);
      }
      var qInline2 = (qCh && qCh.children) || [];
      if (!qInline2.length) return { blockIndex: blockIndex, nodePath: [qSel], offset: 0 };
      var qSrcCol2 = col - qPfx; // 去掉该行**真实**前缀
      if (qSrcCol2 < 0) qSrcCol2 = 0;
      var qpos2 = 0;
      for (var qj3 = 0; qj3 < qInline2.length; qj3++) {
        var qnode2 = qInline2[qj3];
        var qlen2 = inlineSourceLen(qnode2);
        if (qSrcCol2 >= qpos2 && qSrcCol2 < qpos2 + qlen2) {
          var qinner2 = findInlineAtSrcCol(qnode2, qSrcCol2 - qpos2, [qSel].concat(qj3));
          if (qinner2) {
            qinner2.blockIndex = blockIndex;
            return qinner2;
          }
          return { blockIndex: blockIndex, nodePath: [qSel].concat(qj3), offset: 0 };
        }
        qpos2 += qlen2;
      }
      return { blockIndex: blockIndex, nodePath: [qSel, qInline2.length - 1], offset: 0 };
    }

    var srcCol = col;

    // 在 inline 节点中查找
    var pos = prefix;
    var nodePath = [];
    for (var j = 0; j < inlineNodes.length; j++) {
      var node = inlineNodes[j];
      var slen = inlineSourceLen(node);
      if (srcCol >= pos && srcCol < pos + slen) {
        // 在该节点内，递归查找
        var inner = findInlineAtSrcCol(node, srcCol - pos, nodePath.concat(j));
        if (inner) return inner;
        return { blockIndex: blockIndex, nodePath: nodePath.concat(j), offset: 0 };
      }
      pos += slen;
    }

    // 超出范围
    // （防跌进：LIST/BLOCKQUOTE 的源码行只含行首前缀 + inline 内容，不满足上面"单行"
    //  假设；它们在上方已由专用分支处理。走到这里 ⇒ 这两个分支被跳过（如 block 缺
    //  `children`），返回块级位置而非越界下标，避免 nodePath[0] 指向不存在的项。）
    if (block.type === T.LIST || block.type === T.BLOCKQUOTE) {
      return { blockIndex: blockIndex, nodePath: [], offset: col };
    }
    return { blockIndex: blockIndex, nodePath: [inlineNodes.length - 1], offset: 0 };
  }

  /**
   * 在 inline 节点树中查找源码列位置
   */
  function findInlineAtSrcCol(node, srcCol, path) {
    if (node.type === T.TEXT) {
      if (srcCol >= 0 && srcCol <= node.content.length) {
        return { blockIndex: -1, nodePath: path, offset: srcCol };
      }
      return null;
    }

    if (!node.children || node.children.length === 0) {
      return { blockIndex: -1, nodePath: path, offset: srcCol };
    }

    var prefix = inlinePrefixLen(node);
    var pos = prefix;
    for (var i = 0; i < node.children.length; i++) {
      var child = node.children[i];
      var slen = inlineSourceLen(child);
      if (srcCol >= pos && srcCol < pos + slen) {
        return findInlineAtSrcCol(child, srcCol - pos, path.concat(i));
      }
      pos += slen;
    }
    return { blockIndex: -1, nodePath: path, offset: srcCol };
  }

  /**
   * AST 坐标 → 源码行/列
   * @param {number} blockIndex
   * @param {number[]} nodePath
   * @param {number} offset
   * @returns {{line:number, col:number}|null}
   */
  function astToSrc(blockIndex, nodePath, offset) {
    var doc = _currentDoc;
    if (!doc || !doc.blocks) return null;
    if (blockIndex >= doc.blocks.length) return null;

    var block = doc.blocks[blockIndex];

    // 计算 line：**优先**用块自带源码行区间（parser 的 `srcLine` = 单一事实源）；缺字段才退回累加兜底
    var line = block.srcLine > 0 ? block.srcLine - 1 : 0; // 1 基 ⇒ −1 得 0 基行号
    for (var i = 0; !(block.srcLine > 0) && i < blockIndex; i++) {
      line += blockLineCount(doc.blocks[i]); // 兜底：块缺 `srcLine` 时逐块累加（历史口径）
    }

    // LIST block: 使用 items，每个 item 占一行，前缀 "- "（无序，2 字符）
    // 或 "N. "（有序，宽度随真实序号位数变化：`10. ` = 4、`100. ` = 5）
    if (block.type === T.LIST) {
      if (!block.items || block.items.length === 0) {
        return { line: line, col: 0 };
      }
      if (!nodePath || nodePath.length === 0) {
        return { line: line, col: 0 };
      }
      var itemIdx = nodePath[0];
      if (itemIdx >= block.items.length) return { line: line, col: 0 };
      // 每个 item 在自己的源码行上
      line += itemIdx;
      // 前缀列宽按该项真实序号位数计算：无序 "- " = 2；有序按 `"N. "` 宽度
      // （`10. ` = 4 列，`100. ` = 5 列）。口径与 lexer 的 `om[2].length + 2` 一致，
      // 硬编码 2 会让 ≥10 项的有序列表光标/列号少算位数（R3）。
      var liCol = listPrefixLen(block, itemIdx);
      if (nodePath.length === 1) {
        return { line: line, col: liCol + offset };
      }
      // 遍历 item 的 children
      var liItem = block.items[itemIdx];
      var liInlineNodes = liItem.children || [];
      var liNode = liInlineNodes[nodePath[1]];
      if (!liNode) return { line: line, col: liCol };
      // 加上前面兄弟节点的源码长度
      for (var lp = 0; lp < nodePath[1]; lp++) {
        liCol += inlineSourceLen(liInlineNodes[lp]);
      }
      liCol += inlinePrefixLen(liNode);
      for (var lj = 2; lj < nodePath.length; lj++) {
        var lidx = nodePath[lj];
        if (!liNode.children || lidx >= liNode.children.length) break;
        for (var lk = 0; lk < lidx; lk++) {
          liCol += inlineSourceLen(liNode.children[lk]);
        }
        liNode = liNode.children[lidx];
        liCol += inlinePrefixLen(liNode);
      }
      liCol += offset;
      return { line: line, col: liCol };
    }

    // BLOCKQUOTE block（task-155 一期）：行跨度 + 真实前缀宽度；children 可为跨行 list
    if (block.type === T.BLOCKQUOTE) {
      var qKids3 = block.children || [];
      var qBaseLine = block.srcLine > 0 ? block.srcLine - 1 : line;
      if (!qKids3.length) return { line: qBaseLine, col: _quotePfxLenAt(block, qBaseLine) };
      if (!nodePath || nodePath.length === 0) {
        return { line: qBaseLine, col: _quotePfxLenAt(block, qBaseLine) };
      }
      var qIdx = nodePath[0];
      if (qIdx >= qKids3.length) return { line: qBaseLine, col: _quotePfxLenAt(block, qBaseLine) };
      var qCh3 = qKids3[qIdx];
      var qChildLine = (qCh3 && qCh3.srcLine > 0) ? qCh3.srcLine - 1 : qBaseLine + qIdx;
      if (qCh3 && qCh3.type === T.LIST) {
        return _quoteListAstToSrc(block, qCh3, nodePath.slice(1), offset, qChildLine);
      }
      var qPfx3 = _quotePfxLenAt(block, qChildLine);
      var qInline3 = (qCh3 && qCh3.children) || [];
      var qPath3 = nodePath.slice(1);
      if (!qPath3.length) return { line: qChildLine, col: qPfx3 + offset };
      var qNode3 = qInline3[qPath3[0]];
      if (!qNode3) return { line: qChildLine, col: qPfx3 };
      var qCol3 = qPfx3;
      for (var qp3 = 0; qp3 < qPath3[0]; qp3++) qCol3 += inlineSourceLen(qInline3[qp3]);
      qCol3 += inlinePrefixLen(qNode3);
      for (var qd3 = 1; qd3 < qPath3.length; qd3++) {
        var qidx3 = qPath3[qd3];
        if (!qNode3.children || qidx3 >= qNode3.children.length) break;
        for (var qk3 = 0; qk3 < qidx3; qk3++) qCol3 += inlineSourceLen(qNode3.children[qk3]);
        qNode3 = qNode3.children[qidx3];
        qCol3 += inlinePrefixLen(qNode3);
      }
      return { line: qChildLine, col: qCol3 + offset };
    }

    // 计算 col (非 LIST block)
    var prefix = blockPrefixLen(block);
    var col = prefix;

    if (!nodePath || nodePath.length === 0) {
      // 无 inline children 的 block（如 IMAGE、HORIZONTAL_RULE）
      // offset > 0 表示光标在内容之后（如图片右侧），映射到源码行尾
      if (offset > 0) {
        var srcText = sourceGen.generateBlock(block);
        if (srcText.indexOf("\n") === -1) {
          return { line: line, col: srcText.length };
        }
      }
      return { line: line, col: col };
    }

    // 遍历 nodePath
    var inlineNodes = block.children || [];
    if (!inlineNodes || inlineNodes.length === 0) {
      return { line: line, col: col };
    }

    var node = inlineNodes[nodePath[0]];
    if (!node) return { line: line, col: 0 };

    // 加上前面兄弟节点的源码长度
    for (var p = 0; p < nodePath[0]; p++) {
      col += inlineSourceLen(inlineNodes[p]);
    }

    col += inlinePrefixLen(node);

    for (var j = 1; j < nodePath.length; j++) {
      var idx = nodePath[j];
      if (!node.children || idx >= node.children.length) break;
      for (var k = 0; k < idx; k++) {
        col += inlineSourceLen(node.children[k]);
      }
      node = node.children[idx];
      col += inlinePrefixLen(node);
    }

    col += offset;

    return { line: line, col: col };
  }

  /**
   * DOM 光标位置 → AST 坐标
   * 需要 Renderer 创建的 DOM 结构
   * @param {Node} domNode — 光标所在的 DOM 节点
   * @param {number} domOffset — 光标偏移
   * @returns {{blockIndex:number, nodePath:number[], offset:number}|null}
   */
  function domToAst(domNode, domOffset) {
    var doc = _currentDoc;
    if (!doc) return null;

    // 向上查找 -src-block
    var blockEl = domNode;
    while (blockEl && !(blockEl.classList && blockEl.classList.contains("-src-block"))) {
      blockEl = blockEl.parentElement;
    }
    if (!blockEl) return null;

    var blockIndex = parseInt(blockEl.getAttribute("data--block-index"), 10);
    if (isNaN(blockIndex) || blockIndex >= doc.blocks.length) return null;

    var block = doc.blocks[blockIndex];
    var mapSeg = [];

    function _seg(label, len) { mapSeg.push(label + ":" + len); }

    // LIST block: 需要找到光标在哪个 <li> 中
    if (block.type === T.LIST) {
      if (!block.items || block.items.length === 0) {
        return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      }
      // 向上查找 <li> 元素
      var liEl = domNode;
      while (liEl && liEl.tagName !== "LI") {
        liEl = liEl.parentElement;
        if (!liEl || liEl === blockEl) break;
      }
      if (!liEl || liEl.tagName !== "LI") {
        return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      }
      // ★ 2026-10-23（task-80）：按 DOM 真实父子关系定位 item —— **递归下潜 `item.list`**。
      //
      // 旧实现有两个 BUG：
      //   ① `blockEl.querySelectorAll("li")` 拿的是**扁平文档序**（含嵌套子项），
      //      却和 `block.items.length`（只有顶层）比长度 ⇒ 第 2~N 个 li 全部越界，
      //      返回 `nodePath: []` 且**没有 listItemIndex**（"第二项/戊/外层二" 都中招）。
      //   ② 即使不越界，扁平序 `k` 被当成 `block.items[k]` 的下标 ⇒ 嵌套 li 取到
      //      **错误 item 的 children**，nodePath 完全错位（"子项 B"→[1,0]）。
      //
      // 新实现**不再索引比对**，而是沿着「liEl 的父列表是不是当前 list 的 DOM 根」
      // 逐层下潜，结构由 DOM 决定、AST 侧递归 `item.list` 同步 ⇒ 两者天然对齐。
      // 见 `resolveListItem()`。
      var resolved = resolveListItem(block, blockEl, liEl);
      if (!resolved) {
        return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      }
      var itemIndex = resolved.listItemIndex;
      var listPath = resolved.listPath;
      // ★ `resolved.item` 才是**真正的目标项**（可能是嵌套子项）；
      //   `topIndex` 是它在顶层 `block.items` 中的下标 —— `nodePath[0]` 仍用 topIndex，
      //   因为既有 6 处代码把 `nodePath[0]` 当「顶层 item 下标」解释。
      //   ⚠️ 下面对 `item` 的重新赋值必须保持这个区分：
      //   `item` = 目标项本身（取 children）；`topIndex` = 顶层下标（写 nodePath）。
      var topIndex = resolved.topIndex;
      // 在 <li> 内计算渲染偏移
      var liTextNodes = [];
      collectTextNodes(liEl, liTextNodes);
      var liRenderedOffset = 0;
      if (domNode.nodeType === 3) {
        var liFound = false;
        var liPendingMath = null;
        for (var li2 = 0; li2 < liTextNodes.length; li2++) {
          var liTn = liTextNodes[li2];
          var liM = nearestMathAncestor(liTn);
          if (liM) {
            if (liM !== liPendingMath) {
              var liMLen = mathAtomLen(liM);
              _seg("math", liMLen);
              liRenderedOffset += liMLen;
              liPendingMath = liM;
            }
            continue;
          }
          liPendingMath = null;
          if (liTn === domNode) {
            liRenderedOffset += domOffset;
            liFound = true;
            _seg("hit", domOffset);
            break;
          }
          _seg(textNodeLabel(liTn), liTn.textContent.length);
          liRenderedOffset += liTn.textContent.length;
        }
        if (!liFound) liRenderedOffset = 0;
      } else {
        // 元素节点边界（光标停在 <li> 内元素上）：累加该元素之前的文本 + 内部前 offset 个子节点文本
        var liPendingMath2 = null;
        for (var li3 = 0; li3 < liTextNodes.length; li3++) {
          var lj = liTextNodes[li3];
          if (domNode.contains(lj)) break;
          var liM2 = nearestMathAncestor(lj);
          if (liM2) {
            if (liM2 !== liPendingMath2) {
              var liMLen2 = mathAtomLen(liM2);
              _seg("math", liMLen2);
              liRenderedOffset += liMLen2;
              liPendingMath2 = liM2;
            }
            continue;
          }
          liPendingMath2 = null;
          _seg(textNodeLabel(lj), lj.textContent.length);
          liRenderedOffset += lj.textContent.length;
        }
        var liChildCount = domNode.childNodes ? domNode.childNodes.length : 0;
        // 原子元素：不累加内部 CHTML 文本，domOffset>0 视为原子之后，按真实渲染长度占位
        if (_isAtomElement(domNode)) {
          if (domOffset > 0) liRenderedOffset += atomLenForDom(domNode);
        } else {
          for (var li4 = 0; li4 < domOffset && li4 < liChildCount; li4++) {
            var liChild = domNode.childNodes[li4];
            liRenderedOffset += (liChild.nodeType === 1 && _isAtomElement(liChild)) ? atomLenForDom(liChild) : nodeTextLen(liChild);
          }
        }
      }
      // 在 item.children 中映射
      // ★ task-80：用 `resolved.item`（递归解析出的**真实目标项**），不能用
      //   `block.items[itemIndex]` —— 那是旧的扁平序口径，嵌套时会取错项。
      var item = resolved.item;
      // ★ task-80：`nodePath` 语义**保持不变** —— `[顶层 item 下标, ...inline 路径]`。
      //   嵌套 li 的 `nodePath[0]` 取它所属**顶层项**的下标（topIndex），
      //   因此既有 6 处按 `nodePath[0]=顶层 item 下标` 解释的代码零影响。
      //   真正带层级的路径放在**新字段** `listPath`（如 [0,1]），只供升降级使用。
      if (!item.children || item.children.length === 0) {
        return {
          blockIndex: blockIndex,
          nodePath: [topIndex],
          offset: 0,
          listItemIndex: itemIndex,
          listPath: listPath,
        };
      }
      var liPreferEnd = (domOffset > 0);
      var liResult = renderedToSrcCol({ children: item.children }, liRenderedOffset, liPreferEnd);
      if (window.log) window.log("MAP", "domToAst block=" + blockIndex + " item=" + itemIndex + " listPath=[" + (listPath || []).join(",") + "] dom=" + describeDomNode(domNode, domOffset) + " seg=[" + mapSeg.join(",") + "] renderedOffset=" + liRenderedOffset + " -> " + (liResult ? JSON.stringify(liResult.targetNode && liResult.targetNode.type) : "null"));
      var liPath = findNodePathInList(item.children, liResult.targetNode);
      return {
        blockIndex: blockIndex,
        nodePath: [topIndex].concat(liPath || [0]),
        offset: liResult.leafOffset,
        listItemIndex: itemIndex,
        listPath: listPath,
      };
    }

    // 简单 block（无 inline children）
    if (!block.children || block.children.length === 0) {
      return { blockIndex: blockIndex, nodePath: [], offset: domOffset };
    }

    // 在 block element 内查找文本节点位置
    // 收集所有文本节点
    var textNodes = [];
    collectTextNodes(blockEl, textNodes);

    // 计算光标对应的「渲染文本偏移」。domNode 可能是文本节点（直接命中），
    // 也可能是元素节点（选区边界停在元素上，如 span.-hl 的 offset=0 /
    // offset=子节点数）。元素节点必须按「元素之前的文本长度 + 元素内部前
    // offset 个子节点的文本长度」计算，否则会累加成整块总长，导致跨样式
    // 边界选区的样式应用错位甚至失败（颜色完全没变）。
    var renderedOffset = 0;
    if (domNode.nodeType === 3) {
      var found = false;
      var pendingMath = null; // 当前跳过的公式原子块（内部 MathJax 文本只占一次位）
      for (var i = 0; i < textNodes.length; i++) {
        var tn = textNodes[i];
        var mEl = nearestMathAncestor(tn);
        if (mEl) {
          if (mEl !== pendingMath) {
            var mLen = mathAtomLen(mEl);
            _seg("math", mLen);
            renderedOffset += mLen;
            pendingMath = mEl;
          }
          continue; // 公式内部 MathJax 文本节点：跳过
        }
        pendingMath = null;
        if (tn === domNode) {
          renderedOffset += domOffset;
          _seg("hit", domOffset);
          found = true;
          break;
        }
        _seg(textNodeLabel(tn), tn.textContent.length);
        renderedOffset += tn.textContent.length;
      }
      if (!found) renderedOffset = 0;
    } else {
      // 无 inline children 的简单块（IMAGE / HORIZONTAL_RULE / 空行）：
      // 光标停在 blockEl 元素边界 —— offset 0 = 块首（图片前），offset ≥ 1 = 块尾（图片后）
      if ((!block.children || block.children.length === 0) && domNode === blockEl) {
        return { blockIndex: blockIndex, nodePath: [], offset: domOffset > 0 ? 1 : 0 };
      }
      var pendingMath2 = null;
      for (var j = 0; j < textNodes.length; j++) {
        var tj = textNodes[j];
        if (domNode.contains(tj)) break;
        var mEl2 = nearestMathAncestor(tj);
        if (mEl2) {
          if (mEl2 !== pendingMath2) {
            var mLen2 = mathAtomLen(mEl2);
            _seg("math", mLen2);
            renderedOffset += mLen2;
            pendingMath2 = mEl2;
          }
          continue;
        }
        pendingMath2 = null;
        _seg(textNodeLabel(tj), tj.textContent.length);
        renderedOffset += tj.textContent.length;
      }
      // 原子元素（contentEditable=false）：其内部文本（MathJax CHTML）不可作为
      // 渲染偏移依据；domOffset>0 视为位于原子之后，原子按真实渲染长度占位
      // （math 取 data-formula 长度，与 AST renderedLen 一致）
      if (_isAtomElement(domNode)) {
        if (domOffset > 0) renderedOffset += atomLenForDom(domNode);
      } else {
        var childCount = domNode.childNodes ? domNode.childNodes.length : 0;
        for (var c = 0; c < domOffset && c < childCount; c++) {
          var child = domNode.childNodes[c];
          renderedOffset += (child.nodeType === 1 && _isAtomElement(child)) ? atomLenForDom(child) : nodeTextLen(child);
        }
      }
    }

    // 渲染偏移 → AST 坐标
    var preferEnd = (domOffset > 0);
    var result = renderedToSrcCol({ children: block.children }, renderedOffset, preferEnd);
    if (window.log) window.log("MAP", "domToAst block=" + blockIndex + " dom=" + describeDomNode(domNode, domOffset) + " seg=[" + mapSeg.join(",") + "] renderedOffset=" + renderedOffset + " -> " + (result ? JSON.stringify(result.targetNode && result.targetNode.type) : "null"));
    if (!result) return { blockIndex: blockIndex, nodePath: [0], offset: 0 };

    // 从整个 block 的 inline 树中找到 nodePath
    var nodePath = findNodePathInList(block.children, result.targetNode);
    return {
      blockIndex: blockIndex,
      nodePath: nodePath || [0],
      offset: result.leafOffset,
    };
  }

  /**
   * ★ 2026-10-23（task-80）：把 DOM `<li>` 解析为 AST 中的列表项。
   *
   * 为什么要单独一个函数：`domToAst` 旧实现用「扁平 li 序号」当 `block.items` 下标，
   * 在**嵌套列表**下必然错位（见 `domToAst` 里的注释）。这里改为**按 DOM 真实父子
   * 关系递归下潜**：DOM 侧「liEl 的父 `<ul>` 是不是当前 list 的 DOM 根」和 AST 侧
   * 「item.list 递归」是完全同构的，因此不需要任何序号对齐。
   *
   * 返回值同时保留**两套坐标**，各自服务不同的消费方：
   *   · `listItemIndex` — **扁平 li 索引**（`blockEl.querySelectorAll("li")` 文档序）。
   *     `edit-handler.getPreviewCursor()` 的 `srcLine += listItemIndex` 与
   *     `logCursorContext` 的 `lis[listItemIndex]` 都依赖这个语义，**不能改**。
   *   · `listPath` — **树路径**（如 `[0,1]` = 顶层第 0 项的第二个子项）。
   *     新增字段，供 `indentListLevel`（Tab/Shift+Tab 升降级）定位当前项。
   *   · `topIndex` — 该 item 在**顶层** `block.items` 中的下标。`nodePath[0]` 用它，
   *     从而 `nodePath` 的既有语义（6 处代码依赖）完全不变。
   *
   * @param {object} block — LIST block（含 `items`）
   * @param {Element} blockEl — 该块的根 `<ul>/<ol>`（`data--block-index` 指向它）
   * @param {Element} liEl — 光标所在的 `<li>`
   * @returns {{item:object, listPath:number[], listItemIndex:number, topIndex:number}|null}
   */
  function resolveListItem(block, blockEl, liEl) {
    if (!block || !block.items || !liEl) return null;

    // 扁平索引：与 getPreviewCursor 的 `srcLine += listItemIndex` 口径一致
    var flatIdx = -1;
    var allLis = blockEl.querySelectorAll("li");
    for (var fi = 0; fi < allLis.length; fi++) {
      if (allLis[fi] === liEl) { flatIdx = fi; break; }
    }
    if (flatIdx < 0) return null;

    /**
     * 递归下潜。`listRoot` 是当前 list 的 DOM 根（顶层是 blockEl，之后是 item 内嵌的 ul/ol）。
     * `items` 是与之对应的 AST 数组；`path` 是到当前层的前缀。
     */
    function descend(listRoot, items, path) {
      // 本层所有直接 <li>（只取直系子元素，不递归 querySelectorAll）
      var siblings = [];
      for (var s = 0; s < listRoot.children.length; s++) {
        if (listRoot.children[s].tagName === "LI") siblings.push(listRoot.children[s]);
      }
      // liEl 是否在本层
      var idxInLevel = -1;
      for (var t = 0; t < siblings.length; t++) {
        if (siblings[t] === liEl) { idxInLevel = t; break; }
      }
      if (idxInLevel >= 0) {
        var hitItem = items[idxInLevel];
        if (!hitItem) return null;              // AST/DOM 不一致 ⇒ 交给调用方 bail
        return {
          item: hitItem,
          listPath: path.concat([idxInLevel]),
          listItemIndex: flatIdx,
          topIndex: path.length ? path[0] : idxInLevel,
        };
      }
      // 不在本层 ⇒ 下潜到每个 <li> 的子列表
      for (var u = 0; u < siblings.length; u++) {
        var sibLi = siblings[u];
        var childListEl = null;
        for (var c = 0; c < sibLi.children.length; c++) {
          var ce = sibLi.children[c];
          if (ce.tagName === "UL" || ce.tagName === "OL") { childListEl = ce; break; }
        }
        if (!childListEl) continue;
        var sibItem = items[u];
        var childItems = (sibItem && sibItem.list && sibItem.list.items) ? sibItem.list.items : null;
        if (!childItems || !childItems.length) continue;
        var r = descend(childListEl, childItems, path.concat([u]));
        if (r) return r;
      }
      return null;
    }

    return descend(blockEl, block.items, []);
  }

  /**
   * AST 坐标 → DOM Range
   * @param {number} blockIndex
   * @param {number[]} nodePath
   * @param {number} offset
   * @returns {Range|null}
   */
  function astToDom(blockIndex, nodePath, offset) {
    var doc = _currentDoc;
    if (!doc) return null;

    var blockEl = document.querySelector('.-src-block[data--block-index="' + blockIndex + '"]');
    if (!blockEl) return null;

    var block = doc.blocks[blockIndex];
    if (!block) return null;

    // LIST block：定位到具体 <li>
    if (block.type === T.LIST) {
      if (!block.items || block.items.length === 0) {
        return _rangeInContainer(blockEl, 0);
      }
      var itemIdx = (nodePath && nodePath.length) ? nodePath[0] : 0;
      var lis = blockEl.querySelectorAll("li");
      if (itemIdx >= lis.length) return _rangeInContainer(blockEl, 0);
      var liEl = lis[itemIdx];
      var item = block.items[itemIdx];
      var relPath = (nodePath || []).slice(1);
      var renderedOffset = _renderedOffsetInInline(item.children || [], relPath, offset);
      var atomSide = _atomSideOfPath(item.children || [], relPath, offset);
      var range = _rangeAtRenderedOffset(liEl, renderedOffset, atomSide);
      if (window.log) window.log("MAP", "astToDom block=" + blockIndex + " item=" + itemIdx + " path=[" + (relPath || []).join(",") + "] off=" + offset + " atomSide=" + atomSide + " rendered=" + renderedOffset + " -> " + _describeRange(range));
      return range;
    }

    // 简单 block（无 inline children，如 BLANK_LINE / IMAGE）
    if (!block.children || block.children.length === 0) {
      var br = blockEl.querySelector("br");
      if (br) {
        var r = document.createRange();
        r.setStartBefore(br);
        r.collapse(true);
        return r;
      }
      // IMAGE 块：offset 0 = 图片左侧（img 前），offset > 0 = 图片右侧（img 后），
      // 使光标可停靠在图片两侧（导航 / 换行）
      var imgSide = offset > 0 ? 1 : 0;
      return _rangeInContainer(blockEl, Math.min(imgSide, blockEl.childNodes.length));
    }

    // 计算渲染偏移（渲染文本偏移 = 前面兄弟的渲染长度之和 + 叶内偏移）
    var renderedOffset = _renderedOffsetInInline(block.children, nodePath, offset);
    var atomSide = _atomSideOfPath(block.children, nodePath, offset);
    var range = _rangeAtRenderedOffset(blockEl, renderedOffset, atomSide);
    if (window.log) window.log("MAP", "astToDom block=" + blockIndex + " path=[" + (nodePath || []).join(",") + "] off=" + offset + " atomSide=" + atomSide + " rendered=" + renderedOffset + " -> " + _describeRange(range));
    return range;
  }

  /** 简洁描述 Range 起点（用于 MAP 日志） */
  function _describeRange(range) {
    if (!range) return "null";
    return describeDomNode(range.startContainer, range.startOffset);
  }

  /**
   * 计算 inline 节点路径 + 叶偏移对应的「渲染文本偏移」
   * @param {Array} inlineNodes — 顶层 inline 节点数组
   * @param {number[]} nodePath — 相对 inlineNodes 的路径
   * @param {number} offset — 叶节点内的偏移
   * @returns {number}
   */
  function _renderedOffsetInInline(inlineNodes, nodePath, offset) {
    if (!inlineNodes || inlineNodes.length === 0) return 0;
    if (!nodePath || nodePath.length === 0) return 0;

    var renderedOffset = 0;
    var topIdx = nodePath[0];

    for (var p = 0; p < topIdx && p < inlineNodes.length; p++) {
      renderedOffset += renderedLen(inlineNodes[p]);
    }

    var node = inlineNodes[topIdx];
    if (!node) return renderedOffset + (offset || 0);

    for (var j = 1; j < nodePath.length; j++) {
      var idx = nodePath[j];
      if (!node.children || idx >= node.children.length) break;
      for (var k = 0; k < idx; k++) {
        renderedOffset += renderedLen(node.children[k]);
      }
      node = node.children[idx];
    }

    return renderedOffset + (offset || 0);
  }

  /**
   * 将容器内的渲染文本偏移映射为光标 Range。
   * 遍历「渲染单元」（可编辑文本节点 + contentEditable=false 原子元素）。
   * 原子元素按真实渲染长度占位（math 取 data-formula 长度，其余取 textContent 长度），
   * 光标无法放入原子内部：坐标落在原子起点 → 光标放原子之前；落在原子内部/末尾 → 放原子之后。
   * @param {HTMLElement} container
   * @param {number} renderedOffset
   * @param {string} [atomSide] — AST 坐标指向原子内部时的优先方向："before"|"after"|null。
   *   offset=0（原子开头）传 "before"，offset>0（原子内部/末尾）传 "after"；
   *   传 null 时坐标在原子区间内一律视为原子之后。
   */
  function _rangeAtRenderedOffset(container, renderedOffset, atomSide) {
    var units = [];
    _collectRenderUnits(container, units);

    var pos = 0;
    for (var i = 0; i < units.length; i++) {
      var u = units[i];
      var end = pos + u.len;
      if (u.kind === "text") {
        if (renderedOffset >= pos && renderedOffset <= end) {
          var range = document.createRange();
          range.setStart(u.node, renderedOffset - pos);
          range.collapse(true);
          if (window.log) window.log("MAP", "rangeAt offset=" + renderedOffset + " -> text#" + (u.node.data || "").slice(0, 12).replace(/\n/g, "\\n") + "@" + (renderedOffset - pos));
          return range;
        }
      } else {
        // 原子单元：只有起点边界可放原子前（atomSide=before），内部/末尾一律原子后
        if (renderedOffset >= pos && renderedOffset <= end) {
          var before = (atomSide === "before" && renderedOffset === pos);
          var r = document.createRange();
          if (before) r.setStartBefore(u.node);
          else r.setStartAfter(u.node);
          r.collapse(true);
          if (window.log) window.log("MAP", "rangeAt offset=" + renderedOffset + " atomSide=" + atomSide + " -> " + (before ? "before" : "after") + " " + describeDomNode(u.node, 0));
          return r;
        }
      }
      pos = end;
    }

    // Fallback：定位到最后一个单元之后
    if (units.length > 0) {
      var last = units[units.length - 1];
      var fr = document.createRange();
      if (last.kind === "text") {
        fr.setStart(last.node, last.len);
      } else {
        fr.setStartAfter(last.node);
      }
      fr.collapse(true);
      if (window.log) window.log("MAP", "rangeAt offset=" + renderedOffset + " -> FALLBACK units=" + units.length);
      return fr;
    }

    if (window.log) window.log("MAP", "rangeAt offset=" + renderedOffset + " -> EMPTY " + describeDomNode(container, 0));
    return _rangeInContainer(container, 0);
  }

  /**
   * 收集容器内的「渲染单元」：可编辑文本节点 + 原子元素。
   * 原子元素作为整体单元，不深入其内部（MathJax CHTML 内部文本不可逐字计数）。
   */
  function _collectRenderUnits(el, result) {
    if (!el || !result) return;
    var nodes = el.childNodes;
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.nodeType === 3) {
        result.push({ kind: "text", node: n, len: n.data.length });
      } else if (n.nodeType === 1) {
        if (_isAtomElement(n)) {
          result.push({ kind: "atom", node: n, len: atomLenForDom(n) });
        } else {
          _collectRenderUnits(n, result);
        }
      }
    }
  }

  /**
   * 判断 DOM 元素是否为「原子块」（内容不可逐字编辑/定位）：
   * contentEditable=false 元素；或 MathJax 可能把 .-math 重建成的 mjx-container
   * （带 data--inline-math 标记）；或渲染器生成的 .-math span。
   */
  function _isAtomElement(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.contentEditable === "false") return true;
    if (el.classList && el.classList.contains("-math")) return true;
    if (el.hasAttribute && el.hasAttribute("data--inline-math")) return true;
    return false;
  }

  /**
   * 原子元素在「渲染偏移」中占用的长度。
   * 行内公式取 data-formula 长度（MathJax 二次渲染后 textContent 会丢失 $^_ 等标记，
   * 与 AST 的 renderedLen(MATH_INLINE)=formula.length 不一致）；其余（wikilink/link）
   * 渲染器按显示文本设置 textContent，长度与 renderedLen 一致。
   */
  function atomLenForDom(el) {
    if (!el) return 0;
    var f = el.getAttribute && el.getAttribute("data-formula");
    if (f != null) return f.length;
    return el.textContent.length;
  }

  /**
   * 判断 AST 坐标是否指向「原子节点」内部（math_inline/wiki_link/link）。
   * 返回 "before"（offset=0，原子开头）/ "after"（offset>0，原子内部或末尾）/ null（普通可编辑位置）。
   * 原子块内无法放置光标：恢复选区时起点须映射到原子之前、终点到原子之后。
   */
  function _atomSideOfPath(inlineNodes, nodePath, offset) {
    if (!inlineNodes || !inlineNodes.length || !nodePath || !nodePath.length) return null;
    var node = inlineNodes[nodePath[0]];
    if (!node) return null;
    var atom = false;
    for (var j = 1; j < nodePath.length; j++) {
      if (node.type === T.MATH_INLINE || node.type === T.WIKI_LINK || node.type === T.LINK) {
        atom = true;
        break;
      }
      if (!node.children || !node.children.length) break;
      node = node.children[nodePath[j]];
      if (!node) break;
    }
    if (!atom && (node.type === T.MATH_INLINE || node.type === T.WIKI_LINK || node.type === T.LINK)) atom = true;
    if (!atom) return null;
    return offset > 0 ? "after" : "before";
  }

  function _rangeInContainer(container, offset) {
    var r = document.createRange();
    if (container.firstChild) {
      r.setStart(container, Math.min(offset, container.childNodes.length));
    } else {
      r.setStart(container, 0);
    }
    r.collapse(true);
    return r;
  }

  /**
   * 计算节点（文本/元素）的渲染文本长度。
   * 文本节点 = data.length；元素节点 = 内部所有文本长度。
   */
  function nodeTextLen(node) {
    if (!node) return 0;
    if (node.nodeType === 3) return node.data.length;
    if (node.nodeType === 1) return node.textContent.length;
    return 0;
  }

  /**
   * 文本节点的最近 -math 祖先（公式原子块），无则返回 null。
   * MathJax 会把 .-math 内部的 $...$ 二次渲染成 CHTML mjx 结构，
   * 内部产生多个文本节点；这些节点不能逐个计入渲染偏移，必须跳过。
   */
  function nearestMathAncestor(tn) {
    if (!tn) return null;
    var p = tn.parentElement;
    while (p && p.nodeType === 1) {
      if (p.classList && p.classList.contains("-math")) return p;
      // MathJax typeset 后 .-math span 可能被替换为带 data--inline-math 的 mjx-container
      if (p.hasAttribute && p.hasAttribute("data--inline-math")) return p;
      p = p.parentElement;
    }
    return null;
  }

  /**
   * 公式原子块在「渲染偏移」中占用的长度 = AST 公式长度（与
   * renderedLen(MATH_INLINE)=formula.length 保持一致）。
   */
  function mathAtomLen(mathEl) {
    if (!mathEl) return 0;
    var f = mathEl.getAttribute("data-formula") || "";
    return f.length;
  }

  /** 文本节点的简要描述（用于 MAP 日志）：类名 + 文本前若干字符 */
  function textNodeLabel(tn) {
    if (!tn) return "?";
    var p = tn.parentElement;
    var cls = "";
    while (p && p.nodeType === 1 && !cls) {
      if (p.classList && p.classList.length) cls = p.className;
      p = p.parentElement;
    }
    var t = (tn.textContent || "").slice(0, 16).replace(/\n/g, "\\n");
    return (cls ? cls.split(" ")[0] + "#" : "") + t;
  }

  /** DOM 节点的简要描述（用于 MAP 日志） */
  function describeDomNode(domNode, domOffset) {
    if (!domNode) return "null";
    if (domNode.nodeType === 3) {
      return "text#" + (domNode.textContent || "").slice(0, 16).replace(/\n/g, "\\n") + "@" + domOffset;
    }
    return (domNode.tagName || "?").toLowerCase() + "." + (domNode.className ? String(domNode.className).split(" ")[0] : "") + "@" + domOffset;
  }

  /**
   * 收集 DOM 元素内的所有文本节点
   */
  function collectTextNodes(el, result) {
    if (!el) return;
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while ((node = walker.nextNode())) {
      result.push(node);
    }
  }

  /**
   * 在 inline 节点列表中查找目标节点的路径
   */
  function findNodePathInList(list, target) {
    if (!list || !target) return null;
    for (var i = 0; i < list.length; i++) {
      if (list[i] === target) return [i];
      if (list[i].children) {
        var sub = findNodePathInList(list[i].children, target);
        if (sub) return [i].concat(sub);
      }
    }
    return null;
  }

  /**
   * 计算 block 占用的源码行数
   */
  function blockLineCount(block) {
    if (!block) return 0;
    switch (block.type) {
      case T.CODE_BLOCK:
        return ((block.code || "").split("\n").length) + 2; // fence + code + fence
      case T.MATH_BLOCK:
        return ((block.formula || "").split("\n").length) + 2;
      case T.FRONTMATTER:
        return ((block.yaml || "").split("\n").length) + 2;
      case T.MERMAID:
        return ((block.code || "").split("\n").length) + 2;
      case T.TABLE:
        return (block.rows || []).length + 2; // header + separator + data rows
      case T.LIST:
        return (block.items || []).length; // 每个 item 占一行
      case T.BLOCKQUOTE:
        return (block.children || []).length; // 每个引用行一个段落
      default:
        return 1;
    }
  }

  // ── 内部状态 ──
  var _currentDoc = null;

  /**
   * 设置当前文档（渲染器和映射器共享）
   * @param {object} doc
   */
  function setDoc(doc) {
    _currentDoc = doc;
  }

  /**
   * 获取当前文档
   */
  function getDoc() {
    return _currentDoc;
  }

  // ── 公开 API ──
  return {
    // 核心映射
    domToAst: domToAst,
    astToDom: astToDom,
    srcToAst: srcToAst,
    astToSrc: astToSrc,

    // 底层工具
    srcColToRendered: srcColToRendered,
    renderedToSrcCol: renderedToSrcCol,
    inlinePrefixLen: inlinePrefixLen,
    inlineSuffixLen: inlineSuffixLen,
    inlineSourceLen: inlineSourceLen,
    blockPrefixLen: blockPrefixLen,
    renderedLen: renderedLen,

    // 文档管理
    setDoc: setDoc,
    getDoc: getDoc,
  };
})();