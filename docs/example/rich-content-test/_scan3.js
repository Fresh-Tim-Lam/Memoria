// Comprehensive: for each test line, parse -> render -> for every visible text
// char, run domToAst -> astToSrc and verify round trip. Also simulate clicking.
const fs = require("fs");
const path = require("path");
global.window = global;

class TextNode {
  constructor(text) { this.nodeType = 3; this.textContent = text; this.childNodes = []; this.children = []; this.tagName = "#text"; this.parentElement = null; this.nodeName = "#text"; }
}
class Element {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.nodeName = this.tagName;
    this.children = []; this.childNodes = []; this.parentElement = null;
    this.className = ""; this._attrs = {}; this.style = {}; this.contentEditable = "inherit";
    this._textContent = "";
  }
  get classList() { const s = this; return { contains(c) { return (" " + s.className + " ").indexOf(" " + c + " ") >= 0; } }; }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  appendChild(n) { n.parentElement = this; this.childNodes.push(n); if (n.nodeType === 1) this.children.push(n); return n; }
  get textContent() { if (this.childNodes.length === 0) return this._textContent; return this.childNodes.map(c => c.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.children = []; this._textContent = v; if (v) { const tn = new TextNode(v); tn.parentElement = this; this.childNodes.push(tn); } }
  get firstChild() { return this.childNodes[0] || null; }
  querySelectorAll(sel) {
    const out = [];
    const bim = sel.match(/^\.m0-src-block\[data-m0-block-index="(\d+)"\]$/);
    if (bim) {
      const want = bim[1];
      (function walk(el) { if (el !== this && el.classList.contains("m0-src-block") && el.getAttribute("data-m0-block-index") === want) out.push(el); el.children.forEach(walk); })(this);
    } else if (sel === "li" || sel === "br") {
      const tag = sel.toUpperCase();
      (function walk(el) { if (el !== this && el.tagName === tag) out.push(el); el.children.forEach(walk); })(this);
    } else {
      const cls = sel.replace(/^\./, "");
      (function walk(el) { if (el !== this && el.classList.contains(cls)) out.push(el); el.children.forEach(walk); })(this);
    }
    return out;
  }
  querySelector(sel) { const r = this.querySelectorAll(sel); return r.length ? r[0] : null; }
}
const NodeFilter = { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2, FILTER_SKIP: 3 };
global.NodeFilter = NodeFilter;
global.document = {
  createElement: t => new Element(t),
  createTextNode: t => new TextNode(t),
  createTreeWalker: (root, whatToShow) => {
    const q = [];
    (function walk(n) { if (n.nodeType === 3) q.push(n); n.childNodes.forEach(walk); })(root);
    return { nextNode: () => q.length ? q.shift() : null };
  },
};

const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js", "renderer.js", "mapper.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const parser = window.MemoriaParser;
const renderer = window.MemoriaRenderer;
const mapper = window.MemoriaMapper;
const G = window.MemoriaSourceGen;

function collectTextNodes(el, out) {
  for (const c of el.childNodes) {
    if (c.nodeType === 3) out.push(c);
    else collectTextNodes(c, out);
  }
  return out;
}

const cases = [
  "[[\\h:blue:purple| *是* ** *的* ** ]]",   // user's "failing" spaced form
  "[[\\h:blue:purple|*是* ***的***]]",        // user's "working" form
  "[[\\h:blue:purple|*是****的***]]",         // current test file line 61 (log L15)
];

for (const line of cases) {
  console.log("=".repeat(80));
  console.log("SRC: " + line);
  const body = "前置\n" + line + "\n后置";
  const doc = parser.parse(body);
  const paraIdx = doc.blocks.findIndex(b => b.type === "paragraph" && JSON.stringify(b).indexOf("highlight") >= 0);
  mapper.setDoc(doc);
  const container = renderer.render(doc);
  global._blocks = {};
  container.querySelectorAll(".m0-src-block").forEach(el => { global._blocks[+el.getAttribute("data-m0-block-index")] = el; });
  const pEl = global._blocks[paraIdx];
  const tns = [];
  collectTextNodes(pEl, tns);
  console.log("rendered: " + JSON.stringify(pEl.textContent));
  let roundtripOk = true;
  for (const tn of tns) {
    for (let off = 0; off <= tn.textContent.length; off++) {
      const ast = mapper.domToAst(tn, off);
      if (!ast) { console.log(`  domToAst FAIL tn=${JSON.stringify(tn.textContent)} off=${off}`); roundtripOk = false; continue; }
      const src = mapper.astToSrc(ast.blockIndex, ast.nodePath, ast.offset);
      if (!src) { console.log(`  astToSrc FAIL tn=${JSON.stringify(tn.textContent)} off=${off} ast=${JSON.stringify(ast)}`); roundtripOk = false; continue; }
      const back = mapper.srcToAst(ast.blockIndex, src.line, src.col);
      if (!back || back.blockIndex === -1) {
        // srcToAst quirks known; verify via source text char at mapped position
        const lineText = (body.split("\n")[src.line] || "");
        if (off < tn.textContent.length) {
          const expectedChar = tn.textContent[off];
          const mappedSrcChar = lineText[src.col];
          if (mappedSrcChar !== expectedChar) {
            console.log(`  MISMATCH tn=${JSON.stringify(tn.textContent)} off=${off} char=${JSON.stringify(expectedChar)} -> src L${src.line + 1} C${src.col} char=${JSON.stringify(mappedSrcChar)}`);
            roundtripOk = false;
          }
        }
      }
    }
  }
  console.log("  click roundtrip: " + (roundtripOk ? "OK" : "FAILED"));
}
