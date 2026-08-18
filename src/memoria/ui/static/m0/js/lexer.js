/**
 * MemoriaLexer — 词法分析器
 * Phase 2: 将单行源码字符串解析为 Token 数组
 * 依赖: MemoriaAST (类型常量)
 */

window.MemoriaLexer = (function () {
  "use strict";

  var T = MemoriaAST.TYPES;

  // ── 配对表：open type → close type ──
  var _PAIR_CLOSE = {
    "bold_open": "bold_close",
    "italic_open": "italic_close",
    "bold_italic_open": "bold_italic_close",
    "strikethrough_open": "strikethrough_close",
    "code_open": "code_close",
    "math_inline_open": "math_inline_close",
  };

  /**
   * 检查 tokens 中是否有未匹配的 open token
   */
  function _hasUnmatched(tokens, openType) {
    var closeType = _PAIR_CLOSE[openType];
    if (!closeType) return false;
    var depth = 0;
    for (var k = 0; k < tokens.length; k++) {
      if (tokens[k].type === openType) depth++;
      else if (tokens[k].type === closeType) depth--;
    }
    return depth > 0;
  }

  /**
   * 将单行源码解析为 Token 数组
   * @param {string} sourceLine — 一行源码
   * @param {number} [srcOffset=0] — 该行第一个字符在整个文档中的列偏移
   * @returns {Array<{type:string, value:string, srcStart:number, srcEnd:number}>}
   */
  function tokenize(sourceLine, srcOffset) {
    srcOffset = srcOffset || 0;
    var tokens = [];
    var i = 0;
    var len = sourceLine.length;

    while (i < len) {
      var ch = sourceLine[i];
      var rem = len - i;

      // ── 行首标记 ──
      if (i === 0) {
        // 标题前缀 ### / ## / #
        var hm = sourceLine.match(/^(#{1,6})\s/);
        if (hm) {
          tokens.push(make("heading_prefix", hm[0], i, srcOffset));
          i += hm[0].length;
          continue;
        }
        // 列表前缀 - * +
        var lm = sourceLine.match(/^(\s*)([-*+])\s/);
        if (lm) {
          var indent = lm[1].length;
          if (indent > 0) {
            tokens.push(make("text", lm[1], i, srcOffset));
            i += indent;
          }
          tokens.push(make("list_prefix", lm[2], i, srcOffset));
          i += 2; // marker + space
          continue;
        }
        // 有序列表 1. 2. 等
        var om = sourceLine.match(/^(\s*)(\d+)\.\s/);
        if (om) {
          var oindent = om[1].length;
          if (oindent > 0) {
            tokens.push(make("text", om[1], i, srcOffset));
            i += oindent;
          }
          tokens.push(make("list_prefix", om[2] + ".", i, srcOffset));
          i += om[2].length + 2; // number + ". "
          continue;
        }
        // 引用前缀 >
        var qm = sourceLine.match(/^(\s*)(>\s?)/);
        if (qm) {
          if (qm[1].length > 0) {
            tokens.push(make("text", qm[1], i, srcOffset));
            i += qm[1].length;
          }
          tokens.push(make("blockquote_prefix", qm[2], i, srcOffset));
          i += qm[2].length;
          continue;
        }
      }

      // ── 转义 ──
      if (ch === "\\" && i + 1 < len) {
        tokens.push(make("escape", sourceLine[i + 1], i, srcOffset));
        i += 2;
        continue;
      }

      // ── 图片 ![alt](url) ──
      if (ch === "!" && rem >= 2 && sourceLine[i + 1] === "[") {
        var imgMatch = matchBracketLink(sourceLine, i + 1);
        if (imgMatch) {
          tokens.push(make("image_open", imgMatch.alt, i, srcOffset));
          tokens.push(make("image_close", imgMatch.url, i + imgMatch.fullLen, srcOffset));
          i += imgMatch.fullLen + 1; // +1 for the leading !
          continue;
        }
      }

      // ── 粗斜体 *** ──
      if (ch === "*" && rem >= 3 && sourceLine[i + 1] === "*" && sourceLine[i + 2] === "*") {
        var biType = _hasUnmatched(tokens, "bold_italic_open") ? "bold_italic_close" : "bold_italic_open";
        tokens.push(make(biType, "***", i, srcOffset));
        i += 3;
        continue;
      }

      // ── 粗体 ** ──
      if (ch === "*" && rem >= 2 && sourceLine[i + 1] === "*") {
        var bType = _hasUnmatched(tokens, "bold_open") ? "bold_close" : "bold_open";
        tokens.push(make(bType, "**", i, srcOffset));
        i += 2;
        continue;
      }

      // ── 斜体 * ──
      if (ch === "*") {
        var itType = _hasUnmatched(tokens, "italic_open") ? "italic_close" : "italic_open";
        tokens.push(make(itType, "*", i, srcOffset));
        i += 1;
        continue;
      }

      // ── 粗体 __ (Markdown alt) ──
      if (ch === "_" && rem >= 2 && sourceLine[i + 1] === "_") {
        var bType2 = _hasUnmatched(tokens, "bold_open") ? "bold_close" : "bold_open";
        tokens.push(make(bType2, "__", i, srcOffset));
        i += 2;
        continue;
      }

      // ── 斜体 _ ──
      if (ch === "_") {
        var itType2 = _hasUnmatched(tokens, "italic_open") ? "italic_close" : "italic_open";
        tokens.push(make(itType2, "_", i, srcOffset));
        i += 1;
        continue;
      }

      // ── 删除线 ~~ ──
      if (ch === "~" && rem >= 2 && sourceLine[i + 1] === "~") {
        var sType = _hasUnmatched(tokens, "strikethrough_open") ? "strikethrough_close" : "strikethrough_open";
        tokens.push(make(sType, "~~", i, srcOffset));
        i += 2;
        continue;
      }

      // ── 行内代码 ` ──
      if (ch === "`") {
        var cType = _hasUnmatched(tokens, "code_open") ? "code_close" : "code_open";
        tokens.push(make(cType, "`", i, srcOffset));
        i += 1;
        continue;
      }

      // ── 行内数学 $...$ ──
      if (ch === "$") {
        var mType = _hasUnmatched(tokens, "math_inline_open") ? "math_inline_close" : "math_inline_open";
        tokens.push(make(mType, "$", i, srcOffset));
        i += 1;
        continue;
      }

      // ── [[\...]] 字体样式 ──
      if (ch === "[" && rem >= 3 && sourceLine[i + 1] === "[" && sourceLine[i + 2] === "\\") {
        var fm = matchFontStyle(sourceLine, i);
        if (fm) {
          tokens.push(make(fm.openType, fm.openValue, i, srcOffset));
          // 只跳过开标签，内容和 ]] 交给主循环正常 tokenize
          i += fm.openLen;
          continue;
        }
      }

      // ── ]] 关闭 ──
      if (ch === "]" && rem >= 2 && sourceLine[i + 1] === "]") {
        tokens.push(make("highlight_close", "]]", i, srcOffset));
        i += 2;
        continue;
      }

      // ── Wiki 链接 [[id]] 或 [[id|display]] ──
      if (ch === "[" && rem >= 2 && sourceLine[i + 1] === "[") {
        var wl = matchWikiLink(sourceLine, i);
        if (wl) {
          tokens.push(make("wiki_link_open", wl.target + (wl.display ? "|" + wl.display : ""), i, srcOffset));
          tokens.push(make("wiki_link_close", "]]", i + wl.fullLen - 2, srcOffset));
          i += wl.fullLen;
          continue;
        }
        // 未匹配到有效 wiki link，当作普通文本
        tokens.push(make("text", "[", i, srcOffset));
        i += 1;
        continue;
      }

      // ── 普通链接 [text](url) ──
      if (ch === "[") {
        var lm2 = matchBracketLink(sourceLine, i);
        if (lm2) {
          tokens.push(make("link_open", lm2.alt, i, srcOffset));
          tokens.push(make("link_close", lm2.url, i + lm2.fullLen, srcOffset));
          i += lm2.fullLen;
          continue;
        }
        tokens.push(make("text", "[", i, srcOffset));
        i += 1;
        continue;
      }

      // ── 普通文本 ──
      // 收集到下一个特殊字符
      var j = i;
      while (j < len) {
        var c = sourceLine[j];
        if (c === "\\" || c === "*" || c === "_" || c === "~" || c === "`" ||
            c === "$" || c === "[" || c === "]" || c === "!") {
          break;
        }
        j++;
      }
      // 但如果是 ]] 也停止
      if (j < len && sourceLine[j] === "]" && j + 1 < len && sourceLine[j + 1] === "]") {
        // already handled above, but j would stop at ]
      }
      if (j > i) {
        tokens.push(make("text", sourceLine.slice(i, j), i, srcOffset));
        i = j;
      } else {
        // 单字符，未匹配到任何模式
        tokens.push(make("text", ch, i, srcOffset));
        i += 1;
      }
    }

    return tokens;
  }

  // ── 内部辅助 ──

  function make(type, value, pos, srcOffset) {
    return {
      type: type,
      value: value,
      srcStart: (srcOffset || 0) + pos,
      srcEnd: (srcOffset || 0) + pos + value.length - 1,
    };
  }

  /**
   * 匹配 [[\x:param|...]] 或 [[\x|...]] 字体样式
   * @returns {{openType:string, openValue:string, openLen:number, contentLen:number, closeLen:number}|null}
   */
  function matchFontStyle(line, i) {
    // line[i] = '[', line[i+1] = '[', line[i+2] = '\'
    var rest = line.slice(i + 3); // after [[\
    // [[\h:blue|text]] or [[\h|text]]
    var m = rest.match(/^([a-z]+)(?::([^|\]]+))?\|/);
    if (!m) return null;

    var cmd = m[0]; // e.g. "h:blue|" or "h|"
    var tag = m[1]; // e.g. "h"
    var param = m[2] || ""; // e.g. "blue" or ""

    var openLen = 3 + cmd.length; // [[\ + cmd

    // 找到对应的 ]]
    var closeIdx = line.indexOf("]]", i + openLen);
    if (closeIdx === -1) return null;

    var contentLen = closeIdx - (i + openLen);
    var closeLen = 2;

    var typeMap = {
      "h": "highlight_open",
      "c": "font_color_open",
      "s": "font_size_open",
      "b": "font_bold_open",
      "i": "font_italic_open",
      "u": "font_underline_open",
      "sup": "font_superscript_open",
      "sub": "font_subscript_open",
    };

    var openType = typeMap[tag] || "highlight_open";
    var openValue = tag + (param ? ":" + param : "");

    return {
      openType: openType,
      openValue: openValue,
      openLen: openLen,
      contentLen: contentLen,
      closeLen: closeLen,
    };
  }

  /**
   * 匹配 Wiki 链接 [[id]] 或 [[id|display]]
   * @returns {{target:string, display:string, fullLen:number}|null}
   */
  function matchWikiLink(line, i) {
    // line[i] = '[', line[i+1] = '['
    // 不以 \ 开头（字体样式已在上面处理）
    if (line[i + 2] === "\\") return null;

    var closeIdx = line.indexOf("]]", i + 2);
    if (closeIdx === -1) return null;

    var inner = line.slice(i + 2, closeIdx);
    if (!inner) return null; // [[]] 无效

    var pipeIdx = inner.indexOf("|");
    var target, display;
    if (pipeIdx >= 0) {
      target = inner.slice(0, pipeIdx);
      display = inner.slice(pipeIdx + 1);
    } else {
      target = inner;
      display = "";
    }

    return {
      target: target,
      display: display,
      fullLen: closeIdx + 2 - i,
    };
  }

  /**
   * 匹配 [text](url) 或 ![alt](url)
   * @returns {{alt:string, url:string, fullLen:number}|null}
   */
  function matchBracketLink(line, i) {
    // line[i] = '['
    var closeBracket = line.indexOf("](", i + 1);
    if (closeBracket === -1) return null;

    var alt = line.slice(i + 1, closeBracket);
    var parenClose = line.indexOf(")", closeBracket + 2);
    if (parenClose === -1) return null;

    var url = line.slice(closeBracket + 2, parenClose);
    return {
      alt: alt,
      url: url,
      fullLen: parenClose + 1 - i,
    };
  }

  // ── 公开 API ──
  return {
    tokenize: tokenize,
  };
})();