/**
 * MemoriaParser — 语法分析器
 * Phase 3: Token[] → AST (Document)
 * 依赖: MemoriaAST, MemoriaLexer
 */

window.MemoriaParser = (function () {
  "use strict";

  var AST = MemoriaAST;
  var lexer = MemoriaLexer;

  // ── 配对表：open type → close type ──
  var PAIR_CLOSE = {
    "bold_open": "bold_close",
    "italic_open": "italic_close",
    "bold_italic_open": "bold_italic_close",
    "strikethrough_open": "strikethrough_close",
    "code_open": "code_close",
    "highlight_open": "highlight_close",
    "font_color_open": "highlight_close",
    "font_size_open": "highlight_close",
    "font_bold_open": "highlight_close",
    "font_italic_open": "highlight_close",
    "font_underline_open": "highlight_close",
    "font_superscript_open": "highlight_close",
    "font_subscript_open": "highlight_close",
    "wiki_link_open": "wiki_link_close",
    "link_open": "link_close",
    "image_open": "image_close",
    "math_inline_open": "math_inline_close",
  };

  /**
   * 解析行内 tokens → Inline AST 节点数组
   * @param {Array} tokens
   * @returns {Array} Inline[]
   */
  function parseInline(tokens) {
    var result = [];
    var i = 0;

    while (i < tokens.length) {
      var tok = tokens[i];

      // 转义
      if (tok.type === "escape") {
        result.push(AST.escape(tok.value));
        i++;
        continue;
      }

      // 文本
      if (tok.type === "text") {
        result.push(AST.text(tok.value));
        i++;
        continue;
      }

      // 行内代码 `
      if (tok.type === "code_open") {
        var codeEnd = findClose(tokens, i, "code_close");
        if (codeEnd !== -1) {
          var codeContent = tokens.slice(i + 1, codeEnd).map(function (t) { return t.value; }).join("");
          result.push(AST.code(codeContent));
          i = codeEnd + 1;
        } else {
          result.push(AST.text(tok.value));
          i++;
        }
        continue;
      }

      // 行内数学 $
      if (tok.type === "math_inline_open") {
        var mathEnd = findClose(tokens, i, "math_inline_close");
        if (mathEnd !== -1) {
          var formula = tokens.slice(i + 1, mathEnd).map(function (t) {
            // 词法器把公式内反斜杠（\frac、\nu 等）切为 escape 令牌，需还原为 "\\"+char，
            // 否则公式源码回写（SourceGen）会丢反斜杠，公式损坏
            return t.type === "escape" ? "\\" + t.value : t.value;
          }).join("");
          result.push(AST.mathInline(formula));
          i = mathEnd + 1;
        } else {
          result.push(AST.text(tok.value));
          i++;
        }
        continue;
      }

      // 图片
      if (tok.type === "image_open") {
        var imgEnd = findClose(tokens, i, "image_close");
        if (imgEnd !== -1) {
          result.push(AST.image(tok.value, tokens[imgEnd].value, tokens[imgEnd].title));
          i = imgEnd + 1;
        } else {
          result.push(AST.text("![" + tok.value));
          i++;
        }
        continue;
      }

      // 链接
      if (tok.type === "link_open") {
        var linkEnd = findClose(tokens, i, "link_close");
        if (linkEnd !== -1) {
          result.push(AST.link(tok.value, tokens[linkEnd].value));
          i = linkEnd + 1;
        } else {
          result.push(AST.text("[" + tok.value));
          i++;
        }
        continue;
      }

      // 粗斜体 ***
      if (tok.type === "bold_italic_open") {
        var biEnd = findClose(tokens, i, "bold_italic_close");
        if (biEnd !== -1) {
          var biChildren = parseInline(tokens.slice(i + 1, biEnd));
          result.push(AST.boldItalic(biChildren));
          i = biEnd + 1;
        } else {
          result.push(AST.text(tok.value));
          i++;
        }
        continue;
      }

      // 粗体 **
      if (tok.type === "bold_open") {
        var bEnd = findClose(tokens, i, "bold_close");
        if (bEnd !== -1) {
          var bChildren = parseInline(tokens.slice(i + 1, bEnd));
          result.push(AST.bold(bChildren));
          i = bEnd + 1;
        } else {
          result.push(AST.text(tok.value));
          i++;
        }
        continue;
      }

      // 斜体 *
      if (tok.type === "italic_open") {
        var itEnd = findClose(tokens, i, "italic_close");
        if (itEnd !== -1) {
          var itChildren = parseInline(tokens.slice(i + 1, itEnd));
          result.push(AST.italic(itChildren));
          i = itEnd + 1;
        } else {
          result.push(AST.text(tok.value));
          i++;
        }
        continue;
      }

      // 删除线 ~~
      if (tok.type === "strikethrough_open") {
        var sEnd = findClose(tokens, i, "strikethrough_close");
        if (sEnd !== -1) {
          var sChildren = parseInline(tokens.slice(i + 1, sEnd));
          result.push(AST.strikethrough(sChildren));
          i = sEnd + 1;
        } else {
          result.push(AST.text(tok.value));
          i++;
        }
        continue;
      }

      // 荧光笔 / 字体样式 [[\...]]
      if (tok.type === "highlight_open" || tok.type === "font_color_open" ||
          tok.type === "font_size_open" || tok.type === "font_bold_open" ||
          tok.type === "font_italic_open" || tok.type === "font_underline_open" ||
          tok.type === "font_superscript_open" || tok.type === "font_subscript_open") {

        var hlEnd = findClose(tokens, i, "highlight_close");
        if (hlEnd !== -1) {
          var hlChildren = parseInline(tokens.slice(i + 1, hlEnd));
          var parts = tok.value.split(":"); // "h:yellow:red" or "h:blue" or "h"
          var tag = parts[0];
          var param = parts[1] || "";      // e.g. "yellow" or "blue"
          var fgParam = parts[2] || "";    // e.g. "red" (for [[\h:yellow:red|...]])

          switch (tok.type) {
            case "highlight_open":
              result.push(AST.highlight(param || null, fgParam || null, hlChildren));
              break;
            case "font_color_open":
              result.push(AST.fontColor(param, hlChildren));
              break;
            case "font_size_open":
              result.push(AST.fontSize(param, hlChildren));
              break;
            case "font_bold_open":
              result.push(AST.fontBold(hlChildren));
              break;
            case "font_italic_open":
              result.push(AST.fontItalic(hlChildren));
              break;
            case "font_underline_open":
              result.push(AST.fontUnderline(hlChildren));
              break;
            case "font_superscript_open":
              result.push(AST.fontSuperscript(hlChildren));
              break;
            case "font_subscript_open":
              result.push(AST.fontSubscript(hlChildren));
              break;
          }
          i = hlEnd + 1;
        } else {
          result.push(AST.text(tok.value));
          i++;
        }
        continue;
      }

      // Wiki 链接 [[id]] 或 [[id|display]]
      if (tok.type === "wiki_link_open") {
        var wlEnd = findClose(tokens, i, "wiki_link_close");
        if (wlEnd !== -1) {
          var inner = tok.value;
          var pipeIdx = inner.indexOf("|");
          if (pipeIdx >= 0) {
            result.push(AST.wikiLink(inner.slice(0, pipeIdx), inner.slice(pipeIdx + 1)));
          } else {
            result.push(AST.wikiLink(inner, ""));
          }
          i = wlEnd + 1;
        } else {
          result.push(AST.text("[[" + tok.value));
          i++;
        }
        continue;
      }

      // 未匹配的关闭 token → 文本
      result.push(AST.text(tok.value));
      i++;
    }

    return result;
  }

  /**
   * 在 tokens 中从 start 开始查找匹配的关闭 token
   * @returns {number} index 或 -1
   */
  function findClose(tokens, start, expectedCloseType) {
    var depth = 0;
    for (var j = start; j < tokens.length; j++) {
      var t = tokens[j].type;
      // 所有映射到同一 close 类型的 open 都计入深度，支持跨类型嵌套
      // （如 highlight_open / font_color_open / font_size_open ... 都配对 highlight_close）
      if (PAIR_CLOSE[t] === expectedCloseType) {
        depth++;
      } else if (t === expectedCloseType) {
        depth--;
        if (depth === 0) return j;
      }
    }
    return -1;
  }

  // ── Block 解析 ──

  /**
   * 解析全文 → Document AST
   * @param {string} body — 全文源码
   * @returns {object} Document
   */
  function parse(body) {
    var lines = body.split("\n");
    return AST.document(parseBlocks(lines));
  }

  /**
   * 解析行范围 → Block[]
   * @param {string} body — 全文
   * @param {number} startLine — 起始行号 (0-based)
   * @param {number} endLine — 结束行号 (exclusive)
   * @returns {Array} Block[]
   */
  function parseRange(body, startLine, endLine) {
    var lines = body.split("\n");
    return parseBlocks(lines, startLine, endLine);
  }

  /**
   * 核心 block 解析
   * @param {string[]} lines — 所有行
   * @param {number} [startLine=0]
   * @param {number} [endLine=lines.length]
   * @returns {Array} Block[]
   */
  function parseBlocks(lines, startLine, endLine) {
    startLine = startLine || 0;
    endLine = endLine || lines.length;
    var blocks = [];

    var i = startLine;
    while (i < endLine) {
      var rawLine = lines[i];
      var lineNum = i; // 0-based line number in source

      // ── 空行 ──
      if (rawLine.trim() === "") {
        blocks.push(AST.blankLine());
        i++;
        continue;
      }

      var tokens = lexer.tokenize(rawLine);

      // ── Frontmatter (仅全文开头) ──
      if (i === 0 && rawLine.trim() === "---") {
        var fmLines = [];
        i++;
        while (i < endLine && lines[i].trim() !== "---") {
          fmLines.push(lines[i]);
          i++;
        }
        i++; // skip closing ---
        blocks.push(AST.frontmatter(fmLines.join("\n")));
        continue;
      }

      // ── 围栏代码块 ──
      if (rawLine.trim().match(/^(`{3,}|~{3,})/)) {
        var fenceMatch = rawLine.trim().match(/^(`{3,}|~{3,})(\w*)/);
        var lang = fenceMatch[2] || "";
        var codeLines = [];
        i++;
        while (i < endLine && !lines[i].trim().match(/^(`{3,}|~{3,})/)) {
          codeLines.push(lines[i]);
          i++;
        }
        i++; // skip closing fence
        blocks.push(AST.codeBlock(lang, codeLines.join("\n")));
        continue;
      }

      // ── 数学块 $$ ──
      if (rawLine.trim() === "$$") {
        var mathLines = [];
        i++;
        while (i < endLine && lines[i].trim() !== "$$") {
          mathLines.push(lines[i]);
          i++;
        }
        i++; // skip closing $$
        blocks.push(AST.mathBlock(mathLines.join("\n")));
        continue;
      }

      // ── 标题 ──
      if (tokens.length > 0 && tokens[0].type === "heading_prefix") {
        var levelMatch = tokens[0].value.match(/^#+/);
        var level = levelMatch ? levelMatch[0].length : 1;
        var inlineTokens = tokens.slice(1);
        var children = parseInline(inlineTokens);
        blocks.push(AST.heading(level, children));
        i++;
        continue;
      }

      // ── 水平线 ──
      if (rawLine.trim().match(/^([-*_]\s*){3,}$/) || rawLine.trim() === "***") {
        blocks.push(AST.horizontalRule());
        i++;
        continue;
      }

      // ── 图片（单独一行，允许行尾空白） ──
      if (tokens[0] && tokens[0].type === "image_open") {
        var imgEndIdx = findClose(tokens, 0, "image_close");
        if (imgEndIdx !== -1) {
          // image_close 之后只允许空白（用户复制/粘贴常带行尾空格）
          var imgTailBlank = true;
          for (var _ti = imgEndIdx + 1; _ti < tokens.length; _ti++) {
            if (tokens[_ti].type !== "text" || tokens[_ti].value.trim() !== "") {
              imgTailBlank = false;
              break;
            }
          }
          if (imgTailBlank) {
            blocks.push(AST.image(tokens[0].value, tokens[imgEndIdx].value, tokens[imgEndIdx].title));
            i++;
            continue;
          }
        }
      }

      // ── 引用 ──
      if (tokens.length > 0 && tokens[0].type === "blockquote_prefix") {
        // 连续引用行：每行解析为一个独立段落，保留完整内联结构（高亮/加粗/颜色等）。
        // 若按文本拼接，[[\h:...]] / ** 等标记会被当作纯文本丢失。
        var qBlocks = [];
        while (i < endLine) {
          var qt = lexer.tokenize(lines[i]);
          if (qt.length === 0 || qt[0].type !== "blockquote_prefix") break;
          qBlocks.push(AST.paragraph(parseInline(qt.slice(1))));
          i++;
        }
        if (qBlocks.length) blocks.push(AST.blockquote(qBlocks));
        continue;
      }

      // ── 列表 ──
      if (tokens.length > 0 && tokens[0].type === "list_prefix") {
        var isOrdered = /^\d+\.$/.test(tokens[0].value);
        var items = [];
        var scan = i;
        while (scan < endLine) {
          var lt2 = lexer.tokenize(lines[scan]);
          // 松散列表：列表项之间的空行不中断列表（CommonMark 语义，从 PDF 复制常见）
          if (lt2.length === 0) {
            scan++;
            continue;
          }
          if (lt2[0].type !== "list_prefix") break;
          // 有序/无序类型变化视为新列表（如 `1. a\n\n- b`），不合并
          if (/^\d+\.$/.test(lt2[0].value) !== isOrdered) break;
          var itemChildren2 = parseInline(lt2.slice(1));
          items.push(AST.listItem(itemChildren2));
          scan++;
        }
        blocks.push(AST.list(isOrdered, items));
        i = scan;
        continue;
      }

      // ── 表格 ──
      if (rawLine.indexOf("|") >= 0 && i + 1 < endLine && lines[i + 1].trim().match(/^\|?[\s\-:|]+\|?$/)) {
        var tableRows = [];
        var row = rawLine.split("|").map(function (c) { return c.trim(); });
        if (row[0] === "") row.shift();
        if (row[row.length - 1] === "") row.pop();
        tableRows.push(row);

        i++; // skip separator
        i++; // move to first data row

        while (i < endLine && lines[i].indexOf("|") >= 0) {
          var dr = lines[i].split("|").map(function (c) { return c.trim(); });
          if (dr[0] === "") dr.shift();
          if (dr[dr.length - 1] === "") dr.pop();
          tableRows.push(dr);
          i++;
        }

        var header = tableRows[0] || [];
        var dataRows = tableRows.slice(1);
        blocks.push(AST.table(header, dataRows));
        continue;
      }

      // ── 段落（默认） ──
      var children = parseInline(tokens);
      blocks.push(AST.paragraph(children));
      i++;
    }

    return blocks;
  }

  // ── 公开 API ──
  return {
    parseInline: parseInline,
    parseBlocks: parseBlocks,
    parse: parse,
    parseRange: parseRange,
  };
})();