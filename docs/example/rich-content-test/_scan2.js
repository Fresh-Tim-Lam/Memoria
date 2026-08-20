// Scan every line of test-content.md: tokenize + parse + render, flag any line
// whose RENDERED visible text still contains literal * _ ~ [ ] markers (recognition failure)
const fs = require("fs");
const path = require("path");
global.window = global;

class TextNode {
  constructor(text) { this.nodeType = 3; this.textContent = text; this.childNodes = []; this.children = []; this.tagName = "#text"; this.parentElement = null; }
}
class Element {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.children = []; this.childNodes = []; this.parentElement = null;
    this.className = ""; this._attrs = {}; this.style = {}; this.contentEditable = "inherit";
    this._textContent = "";
  }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  appendChild(n) { n.parentElement = this; this.childNodes.push(n); if (n.nodeType === 1) this.children.push(n); return n; }
  get textContent() { if (this.childNodes.length === 0) return this._textContent; return this.childNodes.map(c => c.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.children = []; this._textContent = v; }
  get firstChild() { return this.childNodes[0] || null; }
}
global.document = { createElement: t => new Element(t), createTextNode: t => new TextNode(t) };

const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "renderer.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const lexer = window.MemoriaLexer;
const parser = window.MemoriaParser;
const renderer = window.MemoriaRenderer;

const body = fs.readFileSync("test-content.md", "utf8");
const lines = body.split("\n");

// per-line: strip leading block prefixes, then check the inline part
function inlinePart(line) {
  return line
    .replace(/^(#{1,6})\s+/, "")
    .replace(/^(\s*)([-*+]\s|\d+\.\s|>\s?)/, "$1");
}

let bad = 0;
lines.forEach((line, idx) => {
  if (!line.includes("[[")) return;
  const toks = lexer.tokenize(line);
  const nodes = parser.parseInline(toks);
  // render inline part via a fake paragraph
  const doc = parser.parse(line);
  let blocks = doc.blocks;
  let visible = "";
  for (const b of blocks) {
    if (b.type === "paragraph") {
      const el = renderer.renderInlineList ? null : null;
      // easiest: render whole doc and take textContent of the first paragraph block
    }
  }
  const container = renderer.render(doc);
  let text = container.textContent || "";
  const mark = /[*_~]/.test(text) ? "  <-- LITERAL MARKUP REMAINS" : "";
  if (mark) {
    bad++;
    console.log(`L${idx + 1}: ${JSON.stringify(line)}`);
    console.log(`   toks: ${toks.map(t => t.type + (t.value !== "**" && t.value !== "*" && t.value !== "***" ? `(${JSON.stringify(t.value)})` : "")).join(" ")}`);
    console.log(`   rendered: ${JSON.stringify(text)}${mark}`);
  }
});
console.log("----");
console.log("lines with literal markup remaining:", bad);
