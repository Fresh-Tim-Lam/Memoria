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
        return "> " + (block.children || []).map(function (b) {
          return generateBlock(b);
        }).join("\n> ");

      case T.LIST:
        return (block.items || []).map(function (item, idx) {
          var prefix = block.ordered ? (idx + 1) + ". " : "- ";
          return prefix + generateInlineList(item.children);
        }).join("\n");

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