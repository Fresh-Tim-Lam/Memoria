/**
 * MemoriaSourceGen — 源码生成器
 * Phase 4: AST → 源码文本（Parser 的逆操作）
 * 依赖: MemoriaAST
 */

window.MemoriaSourceGen = (function () {
  "use strict";

  var AST = MemoriaAST;
  var T = AST.TYPES;

  /**
   * 生成整个文档的源码
   * @param {object} doc — Document 节点
   * @returns {string}
   */
  function generate(doc) {
    if (!doc || !doc.blocks) return "";
    return doc.blocks.map(function (block) {
      return generateBlock(block);
    }).join("\n");
  }

  /**
   * 生成指定范围的 block 源码
   * @param {object} doc
   * @param {number} startBlock — 起始 block index (inclusive)
   * @param {number} endBlock — 结束 block index (exclusive)
   * @returns {string}
   */
  function generateRange(doc, startBlock, endBlock) {
    if (!doc || !doc.blocks) return "";
    var blocks = doc.blocks.slice(startBlock, endBlock);
    return blocks.map(function (block) {
      return generateBlock(block);
    }).join("\n");
  }

  /**
   * 生成单个 block 的源码
   * @param {object} block
   * @returns {string}
   */
  function generateBlock(block) {
    if (!block) return "";

    switch (block.type) {
      case T.BLANK_LINE:
        return "";

      case T.HEADING:
        return "#".repeat(block.level) + " " + generateInlineList(block.children);

      case T.PARAGRAPH:
        return generateInlineList(block.children);

      case T.CODE_BLOCK:
        return "```" + (block.lang || "") + "\n" + block.code + "\n```";

      case T.MATH_BLOCK:
        return "$$\n" + block.formula + "\n$$";

      case T.IMAGE:
        return "![" + block.alt + "](" + block.url + (block.title ? " \"" + block.title + "\"" : "") + ")";

      case T.HORIZONTAL_RULE:
        return "---";

      case T.BLOCKQUOTE:
        // E28（2026-10-22）：旧实现恒写 `"> " + 正文`，把 `>` / `>a` 统一成 `> ` / `> a`
        //   ⇒ 每次往返**凭空插入一个空格**，而「`>` 后的空格是标记语法还是用户内容」
        //   在回写后无从分辨。parser 现在把每行原始前缀记进 `block.prefixes`
        //   （与 children 等长），这里按原样回写 ⇒ `>`、`> `、`>a`、`> a`、`>> ` 均逐字节还原。
        var qKids = block.children || [];
        if (!qKids.length) return "> ";   // 空引用块：仍回写 `> `（历史行为，且可表达「`>` + 一个空格 + 空正文」）
        var qPrefixes = block.prefixes;
        var qUsePrefixes = Array.isArray(qPrefixes) && qPrefixes.length === qKids.length;
        return qKids.map(function (b, qIdx) {
          return (qUsePrefixes ? _quotePrefixOf(qPrefixes[qIdx]) : "> ") + generateBlock(b);
        }).join("\n");

      case T.LIST:
        // ★ 2026-10-23 Bug C：松散列表的**项间空行**必须逐字节重建。
        //   parser 把「项之间」的空行吸收进同一个 list 块（CommonMark 松散列表语义，这是对的），
        //   并用 `itemSrcLine`（每项的 1-based 源码行）记下了每项实际所在行。
        //   旧实现只按 items 逐项 join("\n") ⇒ 那些空行在做任何一次编辑后被**永久抹掉**。
        //   重建规则：相邻两项的行号差 > 1 ⇒ 其间插入 (差 - 1) 个空行。
        //   ⚠️ 只有 `itemSrcLine` 与 `items` **等长**时才可信（编辑后若不维护会失真，
        //      调用方必须同步更新或清空它）。
        //
        // ★ 2026-10-23（0.4.7 任务 4：多级列表）：**递归生成子列表**。
        //   每项优先用 `item.indent`（原文缩进，Tab 保持 Tab）与 `item.list`（子列表）。
        //   子项没有 `indent`（编辑新建的项）⇒ 按「父缩进 + 2 空格」推算，保持最小可用。
        var srcLines = block.itemSrcLine;
        var hasItemLines = Array.isArray(srcLines) && srcLines.length === (block.items || []).length;

        /**
         * 递归：把 list 生成源码行。
         *
         * **空行重建的唯一依据是「上一行源码行号」**（`prevEmittedLine`）——
         * 而不是「同级相邻两项的行号差」。原因：多级列表里源码顺序是
         * `父项 → 全部子项 → 下一个父项`，用「同级差」会把子项占用的行算成空行。
         * 逐行推进 `cursorLine` 后，任何层级的项只用 `item.srcLine - cursorLine - 1` 补空行。
         */
        function genListLines(node, fallbackIndent, state) {
          var lines = [];
          var items = (node && node.items) || [];
          for (var idx = 0; idx < items.length; idx++) {
            var item = items[idx];
            var myLine = item.srcLine;
            if (myLine && state.cursorLine && myLine - state.cursorLine > 1) {
              for (var g2 = 0; g2 < myLine - state.cursorLine - 1; g2++) lines.push("");
            }
            var indent2 = item.indent != null ? item.indent : fallbackIndent;
            var prefix2 = node.ordered ? (idx + 1) + ". " : "- ";
            lines.push(indent2 + prefix2 + generateInlineList(item.children));
            if (myLine) state.cursorLine = myLine;
            if (item.list && item.list.items && item.list.items.length) {
              var sub = genListLines(item.list, indent2 + "  ", state);
              for (var si = 0; si < sub.length; si++) lines.push(sub[si]);
            }
          }
          return lines;
        }

        {
          var state = { cursorLine: 0 };
          var out = genListLines(block, "", state);
          // 兼容旧路径：若解析结果没有任何 item.indent / item.srcLine
          // （例如编辑后由 A.list() 新建的列表节点），退回原「无缩进 + 同级 itemSrcLine 差」行为。
          var anyIndent = out.some(function (l) { return /^[ \t]/.test(l); });
          var anySrcLine = (block.items || []).some(function (it) { return it && it.srcLine; });
          if (!anyIndent && !anySrcLine) {
            var out2 = [];
            (block.items || []).forEach(function (item, idx) {
              if (hasItemLines && idx > 0) {
                var gap = (srcLines[idx] || 0) - (srcLines[idx - 1] || 0) - 1;
                for (var g = 0; g < gap; g++) out2.push("");
              }
              var prefix = block.ordered ? (idx + 1) + ". " : "- ";
              out2.push(prefix + generateInlineList(item.children));
              if (item.list && item.list.items && item.list.items.length) {
                var sub2 = genListLines(item.list, "  ", { cursorLine: 0 });
                for (var si2 = 0; si2 < sub2.length; si2++) out2.push(sub2[si2]);
              }
            });
            out = out2;
          }
          return out.join("\n");
        }

      case T.TABLE:
        var header = "| " + (block.header || []).join(" | ") + " |";
        var sep = "|" + (block.header || []).map(function () { return " --- |"; }).join("");
        var rows = (block.rows || []).map(function (row) {
          return "| " + (row || []).join(" | ") + " |";
        });
        return [header, sep].concat(rows).join("\n");

      case T.FRONTMATTER:
        return "---\n" + block.yaml + "\n---";

      case T.MERMAID:
        return "```mermaid\n" + block.code + "\n```";

      default:
        return "";
    }
  }

  /**
   * 校验引用行前缀：只接受 lexer 产出的引用标记串（`>` + 至多一个空格/制表符，可重复，
   * 例如 `>`、`> `、`>\t`、`>> `、`> > `）。
   * 其它值（外部构造/旧 AST 残留）一律退回历史默认 `"> "`，保证不会写出非法前缀。
   * @param {string} prefix
   * @returns {string}
   */
  function _quotePrefixOf(prefix) {
    return (typeof prefix === "string" && /^(?:>[ \t]?)+$/.test(prefix)) ? prefix : "> ";
  }

  /**
   * 生成 inline 节点数组的源码
   * @param {Array} children
   * @returns {string}
   */
  function generateInlineList(children) {
    if (!children) return "";
    return children.map(function (node) {
      return generateInline(node);
    }).join("");
  }

  /**
   * 生成单个 inline 节点的源码
   * @param {object} node
   * @returns {string}
   */
  function generateInline(node) {
    if (!node) return "";

    switch (node.type) {
      case T.TEXT:
        return node.content;

      case T.BOLD:
        return "**" + generateInlineList(node.children) + "**";

      case T.ITALIC:
        return "*" + generateInlineList(node.children) + "*";

      case T.BOLD_ITALIC:
        return "***" + generateInlineList(node.children) + "***";

      case T.STRIKETHROUGH:
        return "~~" + generateInlineList(node.children) + "~~";

      case T.CODE:
        return "`" + node.code + "`";

      case T.HIGHLIGHT:
        var hlParam = node.color || "";
        if (node.fgColor) hlParam = hlParam + ":" + node.fgColor;
        if (hlParam) {
          return "[[\\h:" + hlParam + "|" + generateInlineList(node.children) + "]]";
        }
        return "[[\\h|" + generateInlineList(node.children) + "]]";

      case T.FONT_COLOR:
        return "[[\\c:" + node.color + "|" + generateInlineList(node.children) + "]]";

      case T.FONT_SIZE:
        return "[[\\s:" + node.size + "|" + generateInlineList(node.children) + "]]";

      case T.FONT_BOLD:
        return "[[\\b|" + generateInlineList(node.children) + "]]";

      case T.FONT_ITALIC:
        return "[[\\i|" + generateInlineList(node.children) + "]]";

      case T.FONT_UNDERLINE:
        return "[[\\u|" + generateInlineList(node.children) + "]]";

      case T.FONT_SUPERSCRIPT:
        return "[[\\sup|" + generateInlineList(node.children) + "]]";

      case T.FONT_SUBSCRIPT:
        return "[[\\sub|" + generateInlineList(node.children) + "]]";

      case T.WIKI_LINK:
        if (node.display) {
          return "[[" + node.target + "|" + node.display + "]]";
        }
        return "[[" + node.target + "]]";

      case T.LINK:
        return "[" + node.text + "](" + node.url + ")";

      case T.MATH_INLINE:
        return "$" + node.formula + "$";

      case T.ESCAPE:
        return "\\" + node.char;

      default:
        return "";
    }
  }

  // ── 公开 API ──
  return {
    generate: generate,
    generateBlock: generateBlock,
    generateInline: generateInline,
    generateInlineList: generateInlineList,
    generateRange: generateRange,
  };
})();