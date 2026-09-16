/**
 * code-highlight.js — 代码块语法高亮（零依赖，轻量 tokenize）
 *
 * 依据：docs/conventions/frontend-modules.md（R1 新代码不进 app.js / R2 由渲染器调用）
 * 接口：
 *   MemoriaCodeHighlight.render(code, lang) → 已 HTML 转义的字符串（可直接 innerHTML）
 *   MemoriaCodeHighlight.supports(lang)     → boolean
 * 支持语言：python / c / cpp / javascript / typescript / bash / json（其余按通用规则兜底）
 * 配色：全部走 CSS 变量 `--tk-*`（见 app.css 的 `.-tk-*`），便于将来浅色主题覆盖
 * 状态：生效中，2026-09-16
 */
(function () {
  "use strict";

  var H = window.MemoriaCodeHighlight = window.MemoriaCodeHighlight || {};

  var KEYWORDS = {
    python: "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield".split(" "),
    cpp: "alignas auto bool break case catch char class const constexpr continue decltype default delete do double else enum explicit export extern false float for friend goto if inline int long mutable namespace new noexcept nullptr operator override private protected public register return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while".split(" "),
    js: "as async await break case catch class const continue debugger default delete do else export extends false finally for from function get if import in instanceof let new null of return set static super switch this throw true try typeof undefined var void while yield".split(" "),
    bash: "case do done elif else esac fi for function if in local readonly return then until while export declare".split(" "),
    plain: []
  };

  var BUILTINS = {
    python: "str int float bool list dict set tuple bytes print len range enumerate zip map filter sorted sum min max abs open type isinstance super self".split(" "),
    cpp: "std string vector map unordered_map set pair cout cin cerr endl printf sprintf malloc free memcpy size_t uint8_t uint32_t int32_t".split(" "),
    js: "console Math JSON Object Array String Number Boolean Promise Map Set Date RegExp Error document window require process module exports".split(" "),
    bash: "echo cd ls cp mv rm mkdir cat grep sed awk source exit printf".split(" "),
    plain: []
  };

  function set(arr) {
    var s = {};
    for (var i = 0; i < arr.length; i++) s[arr[i]] = true;
    return s;
  }

  /** 语言名归一化（保留大小写不敏感与常见别名） */
  function normLang(lang) {
    var l = String(lang || "").toLowerCase();
    if (/^(py|py3|python|python3)$/.test(l)) return "python";
    if (/^(c|cpp|cxx|cc|h|hpp|hh|cs|csharp|objc)$/.test(l)) return "cpp";
    if (/^(js|javascript|jsx|ts|typescript|tsx|json|json5)$/.test(l)) return "js";
    if (/^(sh|bash|zsh|shell|console|powershell|ps1)$/.test(l)) return "bash";
    return "plain";
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /** token 化并输出 HTML；只加标签，不改动原始文本（textContent 保持不变） */
  function scan(code, lang) {
    var cfg = {
      line: lang === "python" || lang === "bash" ? "#" : (lang === "plain" ? null : "//"),
      block: lang === "cpp" || lang === "js" ? ["/*", "*/"] : null,
      preproc: lang === "cpp",
      triple: lang === "python" ? ['"""', "'''"] : null,
      tmpl: (lang === "js" || lang === "bash") ? "`" : null
    };
    var kws = set(KEYWORDS[lang] || []);
    var builtins = set(BUILTINS[lang] || []);
    var out = "", buf = "", i = 0, n = code.length;

    function flush() {
      if (buf) { out += esc(buf); buf = ""; }
    }
    function tok(cls, text) {
      flush();
      out += '<span class="-tk-' + cls + '">' + esc(text) + "</span>";
    }
    function toEol(from) {
      var e = code.indexOf("\n", from);
      return e < 0 ? n : e;
    }

    while (i < n) {
      var ch = code[i];

      // 预处理指令（C/C++：整行）
      if (cfg.preproc && ch === "#") {
        var pe = toEol(i);
        tok("pre", code.slice(i, pe));
        i = pe;
        continue;
      }
      // 行注释
      if (cfg.line && code.substr(i, cfg.line.length) === cfg.line) {
        var le = toEol(i);
        tok("com", code.slice(i, le));
        i = le;
        continue;
      }
      // 块注释
      if (cfg.block && code.substr(i, 2) === cfg.block[0]) {
        var be = code.indexOf(cfg.block[1], i + 2);
        be = be < 0 ? n : be + cfg.block[1].length;
        tok("com", code.slice(i, be));
        i = be;
        continue;
      }
      // 三引号字符串（Python）
      if (cfg.triple) {
        var tq = null;
        for (var t = 0; t < cfg.triple.length; t++) {
          if (code.substr(i, 3) === cfg.triple[t]) { tq = cfg.triple[t]; break; }
        }
        if (tq) {
          var te = code.indexOf(tq, i + 3);
          te = te < 0 ? n : te + 3;
          tok("str", code.slice(i, te));
          i = te;
          continue;
        }
      }
      // 字符串 / 模板串
      if (ch === '"' || ch === "'" || (cfg.tmpl && ch === cfg.tmpl)) {
        var q = ch, j = i + 1;
        while (j < n) {
          if (code[j] === "\\") { j += 2; continue; }
          if (code[j] === q) { j++; break; }
          if (q !== "`" && code[j] === "\n") break;   // 普通字符串不跨行
          j++;
        }
        tok("str", code.slice(i, Math.min(j, n)));
        i = Math.min(j, n);
        continue;
      }
      // 数字
      if (/[0-9]/.test(ch) || (ch === "." && /[0-9]/.test(code[i + 1] || ""))) {
        var m = /^(0[xXbBoO][0-9a-fA-F_]+|\d[\d_]*(\.\d[\d_]*)?([eE][+-]?\d+)?[fFlLuU]*)/.exec(code.slice(i));
        if (m) { tok("num", m[0]); i += m[0].length; continue; }
      }
      // 标识符 → 关键字 / 内建 / 函数 / 属性
      if (/[A-Za-z_$]/.test(ch)) {
        var idm = /^[A-Za-z_$][\w$]*/.exec(code.slice(i));
        var id = idm[0];
        var k = i + id.length;
        var nxt = code.slice(k).match(/^\s*(.)/);
        var nextCh = nxt ? nxt[1] : "";
        if (kws[id]) tok("kw", id);
        else if (builtins[id] || /^[A-Z][A-Za-z0-9_]*$/.test(id)) tok("typ", id);
        else if (nextCh === "(") tok("fn", id);
        else if (nextCh === ":" && (lang === "js" || lang === "python" || lang === "plain")) tok("prop", id);
        else buf += id;
        i = k;
        continue;
      }
      // 其它原样输出（连续合并，避免碎片化 DOM）
      buf += ch;
      i++;
    }
    flush();
    return out;
  }

  H.supports = function (lang) { return normLang(lang) !== "plain"; };

  H.render = function (code, lang) {
    var text = (code == null) ? "" : String(code);
    var l = normLang(lang);
    if (l === "plain") return esc(text);
    try {
      return scan(text, l);
    } catch (e) {
      return esc(text);   // 高亮失败必须降级为纯文本，绝不吞掉内容
    }
  };
})();
