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
   * @returns {number}
   */
  function blockPrefixLen(block) {
    if (!block) return 0;
    switch (block.type) {
      case T.HEADING: return block.level + 1; // "## " = 3
      case T.BLOCKQUOTE: return 2;            // "> "
      case T.LIST_ITEM: return 2;             // "- " or "1. "
      default: return 0;
    }
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

    // 找到包含该行的 block
    var blockIndex = -1;
    var lineCount = 0;
    for (var i = 0; i < doc.blocks.length; i++) {
      var b = doc.blocks[i];
      var bLines = blockLineCount(b);
      if (line >= lineCount && line < lineCount + bLines) {
        blockIndex = i;
        break;
      }
      lineCount += bLines;
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
    var srcLine = sourceGen.generateBlock(block);
    // 对于多行 block，使用该行的起始位置
    var blockLineStart = 0;
    // 简化：假设 block 是单行的（heading, paragraph）
    // 对于多行 block（code_block, math_block），返回 block 级位置
    if (block.type === T.CODE_BLOCK || block.type === T.MATH_BLOCK) {
      return { blockIndex: blockIndex, nodePath: [], offset: col };
    }

    // BLOCKQUOTE block: block.children 是块级段落（每行一个），nodePath[0] 为段落索引
    if (block.type === T.BLOCKQUOTE) {
      var qLineIdx = line - lineCount; // 该行在 block 内的偏移（block 起始行 = lineCount）
      if (qLineIdx < 0 || qLineIdx >= (block.children || []).length) {
        return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      }
      var qBlock = block.children[qLineIdx];
      var qInline = (qBlock && qBlock.children) || [];
      if (!qInline.length) {
        return { blockIndex: blockIndex, nodePath: [qLineIdx], offset: 0 };
      }
      var qSrcCol = col - blockPrefixLen(block); // 去掉 "> " 前缀
      if (qSrcCol < 0) qSrcCol = 0;
      var qpos = 0;
      for (var qj = 0; qj < qInline.length; qj++) {
        var qnode = qInline[qj];
        var qlen = inlineSourceLen(qnode);
        if (qSrcCol >= qpos && qSrcCol < qpos + qlen) {
          var qinner = findInlineAtSrcCol(qnode, qSrcCol - qpos, [qLineIdx].concat(qj));
          if (qinner) {
            qinner.blockIndex = blockIndex;
            return qinner;
          }
          return { blockIndex: blockIndex, nodePath: [qLineIdx].concat(qj), offset: 0 };
        }
        qpos += qlen;
      }
      return { blockIndex: blockIndex, nodePath: [qLineIdx, qInline.length - 1], offset: 0 };
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

    // 计算 line
    var line = 0;
    for (var i = 0; i < blockIndex; i++) {
      line += blockLineCount(doc.blocks[i]);
    }

    // LIST block: 使用 items，每个 item 占一行，前缀 "- " (2字符)
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
      var liCol = 2; // "- " 前缀
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

    // BLOCKQUOTE block: nodePath[0] 为段落索引，每个段落占一行（前缀 "> "）
    if (block.type === T.BLOCKQUOTE) {
      if (!nodePath || nodePath.length === 0) {
        return { line: line, col: 2 };
      }
      var qIdx = nodePath[0];
      if (qIdx >= (block.children || []).length) return { line: line, col: 2 };
      line += qIdx;
      var qBlock = block.children[qIdx];
      var qInline = (qBlock && qBlock.children) || [];
      if (nodePath.length === 1) {
        return { line: line, col: 2 + offset };
      }
      var qNode = qInline[nodePath[1]];
      if (!qNode) return { line: line, col: 2 };
      var qCol = 2;
      for (var qp = 0; qp < nodePath[1]; qp++) qCol += inlineSourceLen(qInline[qp]);
      qCol += inlinePrefixLen(qNode);
      for (var qj2 = 2; qj2 < nodePath.length; qj2++) {
        var qidx = nodePath[qj2];
        if (!qNode.children || qidx >= qNode.children.length) break;
        for (var qk = 0; qk < qidx; qk++) qCol += inlineSourceLen(qNode.children[qk]);
        qNode = qNode.children[qidx];
        qCol += inlinePrefixLen(qNode);
      }
      qCol += offset;
      return { line: line, col: qCol };
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

    // 向上查找 m0-src-block
    var blockEl = domNode;
    while (blockEl && !(blockEl.classList && blockEl.classList.contains("m0-src-block"))) {
      blockEl = blockEl.parentElement;
    }
    if (!blockEl) return null;

    var blockIndex = parseInt(blockEl.getAttribute("data-m0-block-index"), 10);
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
      // 确定 item 索引
      var itemIndex = -1;
      var lis = blockEl.querySelectorAll("li");
      for (var k = 0; k < lis.length; k++) {
        if (lis[k] === liEl) { itemIndex = k; break; }
      }
      if (itemIndex < 0 || itemIndex >= block.items.length) {
        return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      }
      // 在 <li> 内计算渲染偏移
      var liTextNodes = [];
      collectTextNodes(liEl, liTextNodes);
      var liRenderedOffset = 0;
      if (domNode.nodeType === 3) {
        var liFound = false;
        for (var li2 = 0; li2 < liTextNodes.length; li2++) {
          if (liTextNodes[li2] === domNode) {
            liRenderedOffset += domOffset;
            liFound = true;
            _seg("hit", domOffset);
            break;
          }
          var liLen = renderLenOfTextNode(liTextNodes[li2]);
          _seg(textNodeLabel(liTextNodes[li2]), liLen);
          liRenderedOffset += liLen;
        }
        if (!liFound) liRenderedOffset = 0;
      } else {
        // 元素节点边界（光标停在 <li> 内元素上）：累加该元素之前的文本 + 内部前 offset 个子节点文本
        for (var li3 = 0; li3 < liTextNodes.length; li3++) {
          var lj = liTextNodes[li3];
          if (domNode.contains(lj)) break;
          var liLen2 = renderLenOfTextNode(lj);
          _seg(textNodeLabel(lj), liLen2);
          liRenderedOffset += liLen2;
        }
        var liChildCount = domNode.childNodes ? domNode.childNodes.length : 0;
        for (var li4 = 0; li4 < domOffset && li4 < liChildCount; li4++) {
          liRenderedOffset += nodeTextLen(domNode.childNodes[li4]);
        }
      }
      // 在 item.children 中映射
      var item = block.items[itemIndex];
      if (!item.children || item.children.length === 0) {
        return { blockIndex: blockIndex, nodePath: [itemIndex], offset: 0, listItemIndex: itemIndex };
      }
      var liPreferEnd = (domOffset > 0);
      var liResult = renderedToSrcCol({ children: item.children }, liRenderedOffset, liPreferEnd);
      if (window.log) window.log("MAP", "domToAst block=" + blockIndex + " item=" + itemIndex + " dom=" + describeDomNode(domNode, domOffset) + " seg=[" + mapSeg.join(",") + "] renderedOffset=" + liRenderedOffset + " -> " + (liResult ? JSON.stringify(liResult.targetNode && liResult.targetNode.type) : "null"));
      var liPath = findNodePathInList(item.children, liResult.targetNode);
      return {
        blockIndex: blockIndex,
        nodePath: [itemIndex].concat(liPath || [0]),
        offset: liResult.leafOffset,
        listItemIndex: itemIndex,
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
    // 也可能是元素节点（选区边界停在元素上，如 span.m0-hl 的 offset=0 /
    // offset=子节点数）。元素节点必须按「元素之前的文本长度 + 元素内部前
    // offset 个子节点的文本长度」计算，否则会累加成整块总长，导致跨样式
    // 边界选区的样式应用错位甚至失败（颜色完全没变）。
    var renderedOffset = 0;
    if (domNode.nodeType === 3) {
      var found = false;
      for (var i = 0; i < textNodes.length; i++) {
        var tn = textNodes[i];
        if (tn === domNode) {
          renderedOffset += domOffset;
          _seg("hit", domOffset);
          found = true;
          break;
        }
        var tnLen = renderLenOfTextNode(tn);
        _seg(textNodeLabel(tn), tnLen);
        renderedOffset += tnLen;
      }
      if (!found) renderedOffset = 0;
    } else {
      for (var j = 0; j < textNodes.length; j++) {
        var tj = textNodes[j];
        if (domNode.contains(tj)) break;
        var tjLen = renderLenOfTextNode(tj);
        _seg(textNodeLabel(tj), tjLen);
        renderedOffset += tjLen;
      }
      // 行内公式（contentEditable=false 原子块）：其内部文本（MathJax CHTML）不可作为
      // 渲染偏移依据；domOffset>0 视为位于公式之后，+1 哨兵落入其区间末端，
      // 由 renderedToSrcCol/splitInlineAt 将整个公式归入选区一侧
      if (domNode.classList && domNode.classList.contains("m0-math")) {
        if (domOffset > 0) renderedOffset += 1;
      } else {
        var childCount = domNode.childNodes ? domNode.childNodes.length : 0;
        for (var c = 0; c < domOffset && c < childCount; c++) {
          renderedOffset += nodeTextLen(domNode.childNodes[c]);
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
   * AST 坐标 → DOM Range
   * @param {number} blockIndex
   * @param {number[]} nodePath
   * @param {number} offset
   * @returns {Range|null}
   */
  function astToDom(blockIndex, nodePath, offset) {
    var doc = _currentDoc;
    if (!doc) return null;

    var blockEl = document.querySelector('.m0-src-block[data-m0-block-index="' + blockIndex + '"]');
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
      var renderedOffset = _renderedOffsetInInline(item.children || [], (nodePath || []).slice(1), offset);
      return _rangeAtRenderedOffset(liEl, renderedOffset);
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
      return _rangeInContainer(blockEl, 0);
    }

    // 计算渲染偏移（渲染文本偏移 = 前面兄弟的渲染长度之和 + 叶内偏移）
    var renderedOffset = _renderedOffsetInInline(block.children, nodePath, offset);
    return _rangeAtRenderedOffset(blockEl, renderedOffset);
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
   * 将容器内的渲染文本偏移映射为光标 Range
   * 跳过 contentEditable=false 的子元素（MathJax / 代码等）
   * @param {HTMLElement} container
   * @param {number} renderedOffset
   */
  function _rangeAtRenderedOffset(container, renderedOffset) {
    var textNodes = [];
    _collectEditableTextNodes(container, textNodes);

    var pos = 0;
    for (var i = 0; i < textNodes.length; i++) {
      var len = textNodes[i].textContent.length;
      if (renderedOffset >= pos && renderedOffset <= pos + len) {
        var range = document.createRange();
        range.setStart(textNodes[i], renderedOffset - pos);
        range.collapse(true);
        return range;
      }
      pos += len;
    }

    // Fallback：最后一个文本节点末尾
    if (textNodes.length > 0) {
      var last = textNodes[textNodes.length - 1];
      var fr = document.createRange();
      fr.setStart(last, last.textContent.length);
      fr.collapse(true);
      return fr;
    }

    return _rangeInContainer(container, 0);
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
   * 收集容器内「可编辑」的文本节点，跳过 contentEditable=false 子树
   */
  function _collectEditableTextNodes(el, result) {
    if (!el) return;
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentElement;
        while (p && p !== el) {
          if (p.contentEditable === "false") return NodeFilter.FILTER_REJECT;
          p = p.parentElement;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    }, false);
    var node;
    while ((node = walker.nextNode())) result.push(node);
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
   * 文本节点在「渲染偏移」中的长度。
   * 关键修复：m0-math（contentEditable=false 原子块）的 DOM 文本是
   * "$"+formula+"$"（比 AST 公式长度多两个 $）。若按 textContent.length
   * 累加，公式之后的所有文本节点渲染偏移都会被多算 formula.length+2，
   * 使公式后选区的映射错位（样式笔刷范围错乱）。这里按 AST 视角取
   * data-formula.length，与 renderedLen(MATH_INLINE) 保持一致。
   */
  function renderLenOfTextNode(tn) {
    if (!tn) return 0;
    var p = tn.parentElement;
    while (p && p.nodeType === 1) {
      if (p.classList && p.classList.contains("m0-math")) {
        var f = p.getAttribute("data-formula") || "";
        return f.length;
      }
      p = p.parentElement;
    }
    return tn.textContent.length;
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