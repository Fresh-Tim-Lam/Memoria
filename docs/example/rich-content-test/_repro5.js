// Broad emphasis regression: ensure no literal * leaks for common patterns
const fs = require("fs");
const path = require("path");
global.window = global;

class TextNode { constructor(text) { this.nodeType = 3; this.textContent = text; this.childNodes = []; this.children = []; this.tagName = "#text"; this.parentElement = null; } }
class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = String(tag).toUpperCase();
    this.children = []; this.childNodes = []; this.parentElement = null;
    this.className = ""; this._attrs = {}; this.style = {}; this._textContent = "";
  }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  appendChild(n) { n.parentElement = this; this.childNodes.push(n); if (n.nodeType === 1) this.children.push(n); return n; }
  get textContent() { if (this.childNodes.length === 0) return this._textContent; return this.childNodes.map(c => c.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.children = []; this._textContent = v; }
}
global.document = { createElement: t => new Element(t), createTextNode: t => new TextNode(t) };

const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "renderer.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const parser = window.MemoriaParser;
const renderer = window.MemoriaRenderer;

const cases = [
  // basic
  "*em*", "**bold**", "***bi***", "~~del~~", "`code`",
  // nesting with spaces (the user's pattern)
  "*a* **b**", "*a* ***b***", "*a* ** *b* **", "** *a* **",
  // compact star runs (previously broken)
  "*a****b***", "*a***b***", "**a*b**", "*a**b**c*",
  // common inline mixes
  "**bold *em* bold**", "*em **bold** em*", "***bold-italic***", "a **b** c *d* e",
  "**加粗**和*斜体*混合", "*是* **的**", "*是****的***",
  // inside highlight
  "[[\\h:blue:purple|*是****的***]]", "[[\\h:blue|**啊实**]]",
  // underscores unaffected
  "__bold__", "_em_", "__bold _em_ bold__",
  // lists
  "* item", "- item", "1. item",
  // literal asterisks should stay literal when unpaired
  "a * b", "3 * 4 = 12", "a**b", "**a",
];

let bad = 0;
for (const src of cases) {
  const doc = parser.parse(src);
  const container = renderer.render(doc);
  const text = (container.textContent || "");
  // collect AST text leaf contents for comparison
  function leafText(nodes, out) {
    for (const n of (nodes || [])) {
      if (n.type === "text") out.push(n.content);
      else if (n.children && n.children.length) leafText(n.children, out);
    }
  }
  const leaves = [];
  for (const b of doc.blocks) {
    if (b.type === "paragraph") leafText(b.children, leaves);
  }
  const leafJoin = leaves.join("");
  const hasStars = /[*]/.test(text);
  const flag = hasStars ? "  <-- literal * in visible text!" : "";
  if (flag) { bad++; console.log(`${JSON.stringify(src)}\n   rendered: ${JSON.stringify(text)}${flag}`); }
}
console.log("----");
console.log("cases with literal * leaks:", bad, "/", cases.length);
