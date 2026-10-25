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
      // ★ task-155（一期）：引用块内支持**块级列表**（GFM `> - item`）。
      //   做法：把连续引用行的前缀剥掉得到「内层源码行」，用 parseBlocks 子解析
      //   （复用既有列表解析：有序/无序、嵌套缩进、松散列表空行）。
      //   · list 子块：保留（一个 list 可跨多行），并把它的行号从"切片相对"换算成**绝对**；
      //   · 其它子块（段落/空行/标题…）：**逐行还原成段落**，保持 task-155 之前的引用语义
      //     （每行一段），避免 `> # x` / `> ---` 等在本期被悄悄改成块级语义。
      //   子块上的 `srcLine/srcLineEnd`（1-based 绝对闭区间）是 SourceGen 前缀回写与 mapper
      //   列号映射的**单一事实源**（一期核心：多行 child 不再"1 child = 1 行"）。
      if (tokens.length > 0 && tokens[0].type === "blockquote_prefix") {
        var qStripped = [];
        var qPrefixes = [];
        while (i < endLine) {
          var qt = lexer.tokenize(lines[i]);
          if (qt.length === 0 || qt[0].type !== "blockquote_prefix") break;
          qPrefixes.push(qt[0].value);
          qStripped.push(lines[i].slice(qt[0].value.length));
          i++;
        }
        if (qStripped.length) {
          var qChildren = [];
          var qSub = parseBlocks(qStripped, 0, qStripped.length);
          for (var qbi = 0; qbi < qSub.length; qbi++) {
            var qb = qSub[qbi];
            if (qb.type === "list") {
              // list 跨多行：srcLine/srcLineEnd 由"切片内相对(1-based)"换成"绝对(1-based)"
              qb.srcLine = lineNum + qb.srcLine;
              qb.srcLineEnd = lineNum + qb.srcLineEnd;
              qChildren.push(qb);
              continue;
            }
            // 其它块：逐行还原为段落（与旧行为逐字节一致）
            var qbFrom = qb.srcLine - 1;
            var qbTo = qb.srcLineEnd - 1;
            for (var qln = qbFrom; qln <= qbTo; qln++) {
              var qRaw = qStripped[qln] == null ? "" : qStripped[qln];
              var qP = AST.paragraph(parseInline(lexer.tokenize(qRaw)));
              qP.srcLine = lineNum + qln + 1;
              qP.srcLineEnd = qP.srcLine;
              qChildren.push(qP);
            }
          }
          var qBlock = AST.blockquote(qChildren);
          qBlock.prefixes = qPrefixes; // 与"引用行"等长（1:1），SourceGen 逐字节回写
          emit(blocks, qBlock, lineNum, i);
        }
        continue;
      }

      // ── 列表 ──
      // ★ 2026-10-23（0.4.7 任务 4：多级列表）：重写为**栈式建树**。
      //   旧实现只认「行首就是 list_prefix 的行」，缩进行（首个 token 是缩进 text）
      //   直接被降级成段落 ⇒ 多级列表完全不支持，且编辑后会损坏（已由 e374463f 堵住损坏）。
      //   新实现按**对齐宽度**判定层级（用户：「空格数量不要紧，关键是对齐」）：
      //     Tab = 4、空格 = 1；同一父级下兄弟项宽度一致即视为同层；
      //     不要求固定步长（2 空格 / 4 空格 / Tab 都可）；Tab 与空格等价。
      //   `item.list` 挂子列表（**不放进 children** —— children 是行内节点）。
      if (tokens.length > 0 && tokens[0].type === "list_prefix") {
        var isOrdered = /^\d+\.$/.test(tokens[0].value);
        // 保留首项源编号：列表被公式/代码块等隔断拆成多个 <ol> 时，
        // 渲染仍从正确数字开始（如 `1. a\n$$...$$\n2. b` 显示 1. / 2. 而非 1. / 1.）
        var listStart = isOrdered ? parseInt(tokens[0].value, 10) : null;
        var itemSrcLine = [];          // 每项源码行号（1-based）——顶层项口径，兼容既有消费方

        /**
         * 缩进宽度：Tab 记 4、其余按字符数。
         * （不做 CommonMark 的「Tab 进位到 4 的倍数」，因为用户只要求"对齐"。）
         */
        function indentWidth(str) {
          var w = 0;
          for (var ci = 0; ci < str.length; ci++) w += str[ci] === "\t" ? 4 : 1;
          return w;
        }

        /**
         * 把一行拆成 { indentRaw, marker, ordered, contentTokens }。
         * 非列表行返回 null。
         * 兼容 lexer 现在会产出「marker 后的分隔空格 text token」（e374463f）。
         */
        function parseListLine(raw) {
          var toks = lexer.tokenize(raw);
          if (!toks.length) return null;
          var k = 0;
          var ind = "";
          // 前导缩进（lexer 把它产成一个 text token，紧跟在首位）
          if (toks[k].type === "text" && /^[ \t]+$/.test(toks[k].value)) {
            ind = toks[k].value;
            k++;
          }
          if (k >= toks.length || toks[k].type !== "list_prefix") return null;
          var marker = toks[k].value;
          var ord = /^\d+\.$/.test(marker);
          k++;
          // 跳过 marker 后的分隔空格（e374463f 新增的 text token）
          if (k < toks.length && toks[k].type === "text" && toks[k].value === " ") k++;
          return { indentRaw: ind, marker: marker, ordered: ord, content: toks.slice(k) };
        }

        // ── 先收集：连续列表行 + 松散列表的空行 ──
        var collected = [];   // { srcLine(1-based), indentRaw, marker, ordered, content }
        var scan = i;
        var pendingBlank = 0; // 已跳过、尚未归属的空行数（用于项间空行重建）
        while (scan < endLine) {
          var rawLine = lines[scan];
          if (rawLine.trim() === "") {
            pendingBlank++;
            scan++;
            continue;
          }
          var pl = parseListLine(rawLine);
          if (!pl) break;
          // 顶层 marker 类型变化视为新列表（既有语义：`1. a\n\n- b` 不合并）
          // 注意：**子列表**的类型可以不同（`- a` 下挂 `1. x` 是合法的）
          collected.push({
            srcLine: scan + 1,
            indentRaw: pl.indentRaw,
            marker: pl.marker,
            ordered: pl.ordered,
            content: pl.content,
            blanksBefore: pendingBlank,
          });
          pendingBlank = 0;
          scan++;
        }

        // ── 栈式建树 ──
        if (collected.length) {
          var topOrdered = collected[0].ordered;
          // 只取与首项同类型的顶层项；遇到顶层类型变化就在那里截断（其余留给下一轮 parseBlocks）
          var take = 0;
          for (; take < collected.length; take++) {
            var it0 = collected[take];
            var w0 = indentWidth(it0.indentRaw);
            // 顶层 = 缩进宽度等于首项宽度；类型必须一致
            if (w0 === indentWidth(collected[0].indentRaw) && it0.ordered !== topOrdered) break;
          }
          var used = collected.slice(0, take);

          var wStack = [];        // 缩进宽度栈（每层一个宽度）
          var itemsByLevel = [[]]; // itemsByLevel[level] = 该层的项数组（用于挂载）
          var lastItemByLevel = {}; // lastItemByLevel[level] = 该层最近的 item（父项）

          for (var ci2 = 0; ci2 < used.length; ci2++) {
            var cIt = used[ci2];
            var w = indentWidth(cIt.indentRaw);

            // 栈维护：找 level
            if (!wStack.length) {
              wStack.push(w);
            } else if (w > wStack[wStack.length - 1]) {
              wStack.push(w);
            } else if (w < wStack[wStack.length - 1]) {
              while (wStack.length && w < wStack[wStack.length - 1]) wStack.pop();
              if (!wStack.length || w < wStack[wStack.length - 1]) wStack.push(w);
            }
            var level = wStack.length - 1;

            var item = AST.listItem(parseInline(cIt.content), {
              srcLine: cIt.srcLine,
              indent: cIt.indentRaw,
              // task-157：有序项的真实手写序号（source-gen 逐字节回写用）
              number: cIt.ordered ? parseInt(cIt.marker, 10) : null,
            });

            if (level === 0) {
              itemsByLevel[0].push(item);
              itemSrcLine.push(cIt.srcLine);
            } else {
              // 挂到「最近一个 level-1 的父项的 .list」上
              var parent = lastItemByLevel[level - 1];
              if (!parent) {
                // 防御：level>0 却没有父项（理论上不会发生）⇒ 降级为顶层
                itemsByLevel[0].push(item);
                itemSrcLine.push(cIt.srcLine);
                item = itemsByLevel[0][itemsByLevel[0].length - 1];
              } else {
                if (!parent.list) {
                  parent.list = AST.list(cIt.ordered, [], cIt.ordered ? parseInt(cIt.marker, 10) : null);
                }
                parent.list.items.push(item);
              }
            }
            // 记录该层最近的 item（供下一层挂载）+ 清掉更深层的记录
            lastItemByLevel[level] = item;
            for (var deeper = level + 1; deeper < 20; deeper++) delete lastItemByLevel[deeper];
          }

          var listNode = AST.list(topOrdered, itemsByLevel[0], listStart);
          listNode.itemSrcLine = itemSrcLine;

          // 列表区间收尾（Bug C）：用最后一个**任何层级**项的行号
          var lastLine = used[used.length - 1].srcLine;
          emit(blocks, listNode, lineNum, lastLine);
          i = lastLine;
          continue;
        }
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