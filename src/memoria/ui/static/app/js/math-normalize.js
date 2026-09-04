/**
 * 将未写定界符的伪公式转为 TeX（不破坏已有 $ / $$ 块）。
 */
window.MemoriaMathNormalize = (function () {
  "use strict";

  const UNICODE = {
    "α": "\\alpha", "β": "\\beta", "γ": "\\gamma", "δ": "\\delta",
    "ε": "\\varepsilon", "ζ": "\\zeta", "η": "\\eta", "θ": "\\theta",
    "λ": "\\lambda", "μ": "\\mu", "π": "\\pi", "ρ": "\\rho",
    "σ": "\\sigma", "τ": "\\tau", "φ": "\\phi", "ω": "\\omega",
    "Σ": "\\sum", "Π": "\\prod", "∈": "\\in", "⊆": "\\subseteq",
    "∞": "\\infty", "·": "\\cdot", "×": "\\times", "√": "\\sqrt",
    "→": "\\to", "←": "\\leftarrow", "⇒": "\\Rightarrow",
    "≤": "\\le", "≥": "\\ge", "≠": "\\ne", "±": "\\pm",
  };

  const MATH_RE =
    /[=^\\_∈Σπγαβτελρσφω√·←→]|\\sum|\\prod|\\max|\\min|\\exp|\\log|\\sqrt|\bsoftmax\b|\bexp\s*\(|\bscore\s*\(|\bQ\s*\(|\bV\s*\^|\bE_|\bmax_\{|\bmin_\{|\|S\||R\^n|Q\s*\*|V\s*\*|π\s*\(|α_|Σ_/;

  function hasInlineOrBlockDelimiters(s) {
    return /\$\$[\s\S]*?\$\$/.test(s) || /\$[^$\n]+\$/.test(s) || /\\\[[\s\S]+?\\\]/.test(s);
  }

  function chineseRatio(s) {
    const m = s.match(/[\u4e00-\u9fff]/g);
    return m ? m.length / s.length : 0;
  }

  /** 文档已含 $ 时：仅处理无定界符的 legacy 行，且绝不拆 $$ 块 */
  function isLegacyFormulaLine(line) {
    const t = line.trim();
    if (!t || t === "$$") return false;
    if (/^#{1,6}\s/.test(t)) return false;
    if (/^[-*+]\s/.test(t)) return false;
    if (/^\d+\.\s/.test(t)) return false;
    if (t.startsWith(">") || t.startsWith("|")) return false;
    if (t.startsWith("```") || t.startsWith("---")) return false;
    if (/\*\*[^*]+\*\*/.test(t)) return false;
    if (/\[\[[^\]]+\]\]/.test(t)) return false;
    // 图片行（![alt](path)）不是公式：alt 常含下划线（如文件名 photomode_21072025_160332），
    // 否则会被 MATH_RE 的 `_` 误判为旧式公式而包成 $$ 数学块，图片永不渲染。
    // url 支持尖括号 <...>（路径可含空格/中文）与裸路径两种形式，属性串可缺省。
    if (/^!\[[^\]]*\]\(\s*<[^>]*>(?:\s+"[^"]*")?\s*\)/.test(t)) return false;
    if (/^!\[[^\]]*\]\([^)\s]+(?:\s+"[^"]*")?\s*\)/.test(t)) return false;
    if (hasInlineOrBlockDelimiters(t)) return false;
    if (!MATH_RE.test(t)) return false;
    if (chineseRatio(t) > 0.15) return false;
    return true;
  }

  function toLatex(raw) {
    let s = raw.trim();
    for (const [ch, tex] of Object.entries(UNICODE)) {
      s = s.split(ch).join(tex);
    }
    s = s.replace(/\bsoftmax\s*\(/g, "\\mathrm{softmax}(");
    s = s.replace(/\bexp\s*\(/g, "\\exp(");
    s = s.replace(/\blog\s*\(/g, "\\log(");
    s = s.replace(/\bmax_\{/g, "\\max_{");
    s = s.replace(/\bmin_\{/g, "\\min_{");
    s = s.replace(/\bmax_/g, "\\max_");
    s = s.replace(/\bmin_/g, "\\min_");
    s = s.replace(/\bE_\\pi/g, "\\mathbb{E}_{\\pi}");
    s = s.replace(/\bE_/g, "\\mathbb{E}_");
    s = s.replace(/\^T\b/g, "^{\\top}");
    s = s.replace(/\^\\top\b/g, "^{\\top}");
    s = s.replace(/←/g, "\\leftarrow ");
    s = s.replace(/√d_k/g, "\\sqrt{d_k}");
    s = s.replace(/Σ_/g, "\\sum_");
    return s;
  }

  function wrapDisplay(line) {
    return `$$\n${toLatex(line)}\n$$`;
  }

  function normalize(body) {
    if (!body) return body;
    const docHasExplicitMath = /\$/.test(body);
    const lines = body.split("\n");
    let inDisplayBlock = false;

    return lines
      .map((line) => {
        const trimmed = line.trim();

        if (trimmed === "$$") {
          inDisplayBlock = !inDisplayBlock;
          return line;
        }
        if (inDisplayBlock) return line;

        if (hasInlineOrBlockDelimiters(line)) return line;

        if (!docHasExplicitMath && isLegacyFormulaLine(line)) {
          return wrapDisplay(line);
        }
        return line;
      })
      .join("\n");
  }

  return { normalize, toLatex, isLegacyFormulaLine };
})();
