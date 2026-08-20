// Print rendered DOM tree for the two cases
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
    this._textContent = ""; this._innerHTML = "";
  }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  appendChild(n) { n.parentElement = this; this.childNodes.push(n); if (n.nodeType === 1) this.children.push(n); return n; }
  get textContent() { if (this.childNodes.length === 0) return this._textContent; return this.childNodes.map(c => c.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.children = []; this._textContent = v; if (v) { const tn = new TextNode(v); tn.parentElement = this; this.childNodes.push(tn); } }
  get firstChild() { return this.childNodes[0] || null; }
}
global.document = { createElement: t => new Element(t), createTextNode: t => new TextNode(t) };

const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "renderer.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const parser = window.MemoriaParser;
const renderer = window.MemoriaRenderer;

function html(el, depth) {
  if (!depth) depth = 0;
  const pad = "  ".repeat(depth);
  if (el.nodeType === 3) return `${pad}#text ${JSON.stringify(el.textContent)}`;
  const attrs = Object.entries(el._attrs).map(([k, v]) => ` ${k}="${v}"`).join("");
  const styleKeys = Object.keys(el.style || {});
  const styleStr = styleKeys.length ? ` style="${styleKeys.map(k => `${k}:${el.style[k]}`).join(";")}"` : "";
  const cls = el.className ? ` class="${el.className}"` : "";
  const lines = [`${pad}<${el.tagName}${cls}${styleStr}${attrs}>`];
  el.childNodes.forEach(c => lines.push(html(c, depth + 1)));
  lines.push(`${pad}</${el.tagName}>`);
  return lines.join("\n");
}

const cases = [
  "[[\\h:blue:purple| *是* ** *的* ** ]]",
  "[[\\h:blue:purple|*是* ***的***]]",
];
for (const line of cases) {
  console.log("=".repeat(60));
  console.log("SRC: " + line);
  const doc = parser.parse(line);
  const container = renderer.render(doc);
  console.log(html(container.childNodes[0].childNodes[0], 0));
  console.log("");
}
