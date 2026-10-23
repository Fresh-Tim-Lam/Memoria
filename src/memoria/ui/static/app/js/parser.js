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
   * 表格行切分：把一行按「单元格边界」的 `|` 切分，但**跳过公式（`$...$`/`$$...$$`）
   * 与行内代码（` ` `...` ` `）内部的竖线**——避免 `$|x|$`、`\|` 这类被误当分隔符。
   * 返回单元格字符串数组（含前导/尾随空串，由调用方再 trim/shift/pop，语义与旧 split("|") 对齐）。
   */
  function splitTableRow(raw) {
    var cells = [];
    var buf = "";
    var i = 0;
    var n = raw.length;
    while (i < n) {
      var ch = raw[i];
      // 转义竖线 \| ：字面竖线，不是边界
      if (ch === "\\" && raw[i + 1] === "|") { buf += "\\|"; i += 2; continue; }
      // 行内公式 $...$（或 $$...$$）：跳到配对的结束
      if (ch === "$") {
        var dbl = raw[i + 1] === "$";
        var close = dbl ? "$$" : "$";
        buf += (dbl ? "$$" : "$");
        i += (dbl ? 2 : 1);
        var closeIdx = raw.indexOf(close, i);
        if (closeIdx >= 0) { buf += raw.slice(i, closeIdx + close.length); i = closeIdx + close.length; }
        continue;
      }
      // 行内代码 `...`：跳到配对反引号
      if (ch === "`") {
        buf += "`";
        i += 1;
        var bt = raw.indexOf("`", i);
        if (bt >= 0) { buf += raw.slice(i, bt + 1); i = bt + 1; }
        continue;
      }
      // 单元格边界
      if (ch === "|") { cells.push(buf); buf = ""; i += 1; continue; }
      buf += ch;
      i += 1;
    }
    cells.push(buf);
    return cells.map(function (c) { return c.trim(); });
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
   *
   * ★ 2026-10-21 task-40：Document 节点新增 `trailingNewline`（原文是否以 "\n" 结尾）。
   *
   *   为什么需要：`"a\n".split("\n")` → `["a",""]`，那个末尾空串是**行终止符的产物，
   *   不是真实空行**。parser 会把它建模成一个 `blank_line` 块 ⇒ 在树里
   *   「文末换行」与「真的多一个空行」**不可区分**。这正是 S13（回写丢尾 \n）的树级根因：
   *   不是实现忘了写，而是**树里没有这个信息**。
   *
   *   本字段把它显式记下来。**注意：不改变块数口径**（尾部 blank_line 块照旧产生），
   *   以免 `S_render_frozen` 基线（scale-5k = 3111，末块正是该假 blank 块）失真。
   *   消费方若要精确重建原文，按 `trailingNewline` 决定末尾是否补 "\n"。
   *
   * @param {string} body — 全文源码
   * @returns {object} Document（含 `trailingNewline: boolean`）
   */
  function parse(body) {
    var src = (typeof body === "string") ? body : "";
    var lines = src.split("\n");
    var doc = AST.document(parseBlocks(lines));
    // 原文是否以换行结尾（空串 ⇒ 无换行）
    doc.trailingNewline = src.length > 0 && src.charAt(src.length - 1) === "\n";
    return doc;
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
   * 落块 + 记录它的**源码行区间**（1-based 闭区间）。
   * 这是"块 ↔ 源码行"的**单一事实源**：预览映射（`app.js stampBlockLines` 的
   * `data--src-line`）、KP 范围带、预览编辑回写（`spliceBlockSource`）都直接消费它，
   * 不得再各自复写一套块边界判定（历史上重复实现导致 223/274 份文档行号漂移）。
   * @param {Array} blocks
   * @param {object} blk — AST block
   * @param {number} startIdx — 块首行（0-based）
   * @param {number} i — 解析器当前下标：等于 startIdx 表示"尚未跨行"，否则为跨行后的下一行
   */
  function emit(blocks, blk, startIdx, i) {
    blk.srcLine = startIdx + 1;
    blk.srcLineEnd = i > startIdx ? i : startIdx + 1;
    blocks.push(blk);
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
        emit(blocks, AST.blankLine(), lineNum, i);
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
        emit(blocks, AST.frontmatter(fmLines.join("\n")), lineNum, Math.min(i, endLine));
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
        // Math.min：围栏未闭合时上面的 while 会走到 endLine，末尾的 i++ 会越界一行
        emit(blocks, AST.codeBlock(lang, codeLines.join("\n")), lineNum, Math.min(i, endLine));
        continue;
      }

      // ── 数学块 $$（首尾各占一行） ──
      if (rawLine.trim() === "$$") {
        var mathLines = [];
        i++;
        while (i < endLine && lines[i].trim() !== "$$") {
          mathLines.push(lines[i]);
          i++;
        }
        i++; // skip closing $$
        emit(blocks, AST.mathBlock(mathLines.join("\n")), lineNum, Math.min(i, endLine));
        continue;
      }

      // ── 单行数学块 $$...$$（$$ 与内容同行，例如 $$P(z_k)=Q(z_k)$$） ──
      // 只有整行首尾为 $$、且内容不含内嵌 $$ 时才视为块级公式，否则退回行内处理
      var sm = /^\$\$(.*)\$\$\s*$/.exec(rawLine.trim());
      if (sm && sm[1].indexOf("$$") === -1 && sm[1].trim() !== "") {
        emit(blocks, AST.mathBlock(sm[1].trim()), lineNum, i);
        i++;
        continue;
      }

      // ── 标题 ──
      if (tokens.length > 0 && tokens[0].type === "heading_prefix") {
        var levelMatch = tokens[0].value.match(/^#+/);
        var level = levelMatch ? levelMatch[0].length : 1;
        var inlineTokens = tokens.slice(1);
        var children = parseInline(inlineTokens);
        emit(blocks, AST.heading(level, children), lineNum, i);
        i++;
        continue;
      }

      // ── 水平线 ──
      if (rawLine.trim().match(/^([-*_]\s*){3,}$/) || rawLine.trim() === "***") {
        emit(blocks, AST.horizontalRule(), lineNum, i);
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
            emit(blocks, AST.image(tokens[0].value, tokens[imgEndIdx].value, tokens[imgEndIdx].title), lineNum, i);
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
        // E28（2026-10-22）：逐行记下**原始**前缀（`>` / `> ` / `>\t`），
        // SourceGen 据此无损回写；否则 `>`→`> `、`>a`→`> a`，每次往返凭空插入空格。
        var qPrefixes = [];
        while (i < endLine) {
          var qt = lexer.tokenize(lines[i]);
          if (qt.length === 0 || qt[0].type !== "blockquote_prefix") break;
          qPrefixes.push(qt[0].value);
          qBlocks.push(AST.paragraph(parseInline(qt.slice(1))));
          i++;
        }
        if (qBlocks.length) {
          var qBlock = AST.blockquote(qBlocks);
          qBlock.prefixes = qPrefixes; // 与 children 等长；SourceGen 长度不匹配时退回默认 "> "
          emit(blocks, qBlock, lineNum, i);
        }
        continue;
      }

      // ── 列表 ──
      if (tokens.length > 0 && tokens[0].type === "list_prefix") {
        var isOrdered = /^\d+\.$/.test(tokens[0].value);
        // 保留首项源编号：列表被公式/代码块等隔断拆成多个 <ol> 时，
        // 渲染仍从正确数字开始（如 `1. a\n$$...$$\n2. b` 显示 1. / 2. 而非 1. / 1.）
        var listStart = isOrdered ? parseInt(tokens[0].value, 10) : null;
        var items = [];
        // ★ 2026-10-21 task-40：记录每项的**源码行号**（1-based，与 blk.srcLine 同口径）。
        //   为什么需要：松散列表里列表项之间的空行会被跳过（下面 `lt2.length === 0` 分支），
        //   而 `AST.list` 的 items 只存内容 ⇒ **空行在第几项之后无法追溯**。
        //   例：`- a\n- b\n\nafter` 的 list 区间是 L1-3（吞了空行），但 items 只有 2 项。
        //   有了 itemSrcLine，可据「相邻两项行号差 > 1」判定其间的空行数 ⇒ 逐字节重建可行。
        var itemSrcLine = [];
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
          itemSrcLine.push(scan + 1);   // 1-based 源码行号
          scan++;
        }
        // 注意：此处 i 仍等于块首行，跨行末端在 scan；若传 i 会退化成单行区间。
        //
        // ★ 2026-10-23 Bug C：**列表末尾的空行不属于列表**。
        //   扫描循环对空行是 `scan++` 继续找下一项（松散列表语义，这是对的），
        //   但循环 break 时 `scan` 已经越过「末尾那串空行」⇒ 传给 emit 后
        //   `list.srcLineEnd` 把它们算进列表区间 ⇒ AST 里**没有 blank_line 块** ⇒
        //   预览渲染不出列表后的空行（用户报「- 块后的空行在预览里看不到」）。
        //   修法：用最后一个 item 的实际行号收尾，让主循环从末尾空行继续 ⇒ 生成 blank_line。
        //   （`itemSrcLine` 本来就是为「逐字节重建」准备的，见上面的说明。）
        var lastItemLine = itemSrcLine.length
          ? itemSrcLine[itemSrcLine.length - 1]   // 1-based
          : lineNum + 1;                           // 防御：空 items 时至少占当前行
        var listNode = AST.list(isOrdered, items, listStart);
        listNode.itemSrcLine = itemSrcLine;
        emit(blocks, listNode, lineNum, lastItemLine);
        i = lastItemLine;
        continue;
      }

      // ── 表格 ──
      if (rawLine.indexOf("|") >= 0 && i + 1 < endLine && lines[i + 1].trim().match(/^\|?[\s\-:|]+\|?$/)) {
        var tableRows = [];
        var row = splitTableRow(rawLine);
        if (row[0] === "") row.shift();
        if (row[row.length - 1] === "") row.pop();
        tableRows.push(row);

        i++; // skip separator
        i++; // move to first data row

        while (i < endLine && lines[i].indexOf("|") >= 0) {
          var dr = splitTableRow(lines[i]);
          if (dr[0] === "") dr.shift();
          if (dr[dr.length - 1] === "") dr.pop();
          tableRows.push(dr);
          i++;
        }

        var header = tableRows[0] || [];
        var dataRows = tableRows.slice(1);
        emit(blocks, AST.table(header, dataRows), lineNum, i);
        continue;
      }

      // ── 段落（默认） ──
      var children = parseInline(tokens);
      emit(blocks, AST.paragraph(children), lineNum, i);
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