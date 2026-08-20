// Full pipeline repro: parse -> render -> map roundtrip for the two highlight cases
const fs = require("fs");
const path = require("path");

global.window = global;

// ---------- minimal DOM shim ----------
class TextNode {
  constructor(text) { this.nodeType = 3; this.textContent = text; this.childNodes = []; this.children = []; this.tagName = "#text"; this.parentElement = null; }
}
class Element {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.childNodes = [];
    this.parentElement = null;
    this.className = "";
    this._attrs = {};
    this.style = {};
    this.contentEditable = "inherit";
    this._textContent = "";
    this._innerHTML = "";
  }
  get classList() {
    const self = this;
    return { contains(c) { return (" " + self.className + " ").indexOf(" " + c + " ") >= 0; } };
  }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  appendChild(node) {
    node.parentElement = this;
    this.childNodes.push(node);
    if (node.nodeType === 1) this.children.push(node);
    return node;
  }
  get textContent() {
    if (this.childNodes.length === 0) return this._textContent;
    return this.childNodes.map(c => c.textContent).join("");
  }
  set textContent(v) {
    this.childNodes = []; this.children = []; this._textContent = v;
    if (v) { const tn = new TextNode(v); tn.parentElement = this; this.childNodes.push(tn); }
  }
  set innerHTML(v) {
    this.childNodes = []; this.children = []; this._innerHTML = v;
    if (v === "<br>") { const br = new Element("br"); br.parentElement = this; this.childNodes.push(br); this.children.push(br); }
  }
  get innerHTML() { return this._innerHTML; }
  get firstChild() { return this.childNodes[0] || null; }
  querySelectorAll(sel) {
    const out = [];
    const isBlockIndex = sel.match(/^\.m0-src-block\[data-m0-block-index="(\d+)"\]$/);
    if (isBlockIndex) {
      const want = isBlockIndex[1];
      const walk = el => {
        if (el !== this && el.classList.contains("m0-src-block") && el.getAttribute("data-m0-block-index") === want) out.push(el);
        el.children.forEach(walk);
      };
      walk(this);
    } else if (sel === "li" || sel === "br") {
      const tag = sel.toUpperCase();
      const walk = el => { if (el !== this && el.tagName === tag) out.push(el); el.children.forEach(walk); };
      walk(this);
    } else {
      const cls = sel.replace(/^\./, "");
      const walk = el => { if (el !== this && el.classList.contains(cls)) out.push(el); el.children.forEach(walk); };
      walk(this);
    }
    return out;
  }
  querySelector(sel) { const r = this.querySelectorAll(sel); return r.length ? r[0] : null; }
}

class Range {
  constructor() { this.startContainer = null; this.startOffset = 0; this.collapsedFlag = false; }
  setStart(node, offset) { this.startContainer = node; this.startOffset = offset; }
  setStartBefore(node) {
    const parent = node.parentElement;
    this.startContainer = parent;
    this.startOffset = parent ? parent.childNodes.indexOf(node) : 0;
  }
  collapse(toStart) { this.collapsedFlag = true; }
  get collapsed() { return this.collapsedFlag; }
}

class TreeWalker {
  constructor(root, whatToShow, filter) {
    this._queue = []; this._root = root; this._filter = filter || null; this._collect(root);
  }
  _collect(node) {
    if (node.nodeType === 3) {
      if (!this._filter) { this._queue.push(node); return; }
      const r = this._filter.acceptNode(node);
      if (r === NodeFilter.FILTER_REJECT) return;
      if (r === NodeFilter.FILTER_ACCEPT) this._queue.push(node);
      return;
    }
    for (const c of node.childNodes) this._collect(c);
  }
  nextNode() { return this._queue.length ? this._queue.shift() : null; }
}
const NodeFilter = { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2, FILTER_SKIP: 3 };

global.document = {
  createElement(tag) { return new Element(tag); },
  createTextNode(t) { return new TextNode(t); },
  createRange() { return new Range(); },
  createTreeWalker(root, whatToShow, filter) { return new TreeWalker(root, whatToShow, filter); },
  querySelector(sel) {
    if (global._renderedBlocks) {
      const m = sel.match(/^\.m0-src-block\[data-m0-block-index="(\d+)"\]$/);
      if (m) return global._renderedBlocks[parseInt(m[1], 10)] || null;
    }
    return null;
  },
};
global.NodeFilter = NodeFilter;

// ---------- load modules ----------
const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js", "renderer.js", "mapper.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}

const parser = window.MemoriaParser;
const renderer = window.MemoriaRenderer;
const mapper = window.MemoriaMapper;

function dumpNode(n, indent) {
  const pad = " ".repeat(indent);
  switch (n.type) {
    case "text": return `${pad}text(${JSON.stringify(n.content)})`;
    case "highlight": return `${pad}highlight[bg=${n.color},fg=${n.fgColor}]{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    case "bold": return `${pad}bold{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    case "italic": return `${pad}italic{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    case "bold_italic": return `${pad}bold_italic{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    default: return `${pad}${n.type}(${JSON.stringify(n.content || n.code || "")})`;
  }
}

function collectAllTextNodes(el, out) {
  for (const c of el.childNodes) {
    if (c.nodeType === 3) out.push(c);
    else collectAllTextNodes(c, out);
  }
  return out;
}

function fmtPath(p) { return p ? "[" + p.join(",") + "]" : "null"; }
function fmtSrc(s) { return s ? "L" + s.line + "C" + s.col : "null"; }
function keyOf(a) { return a ? a.blockIndex + ":" + (a.nodePath || []).join(",") + ":" + a.offset : "null"; }

const cases = [
  ["CASE1 spaces+nested", "[[\\h:blue:purple| *是* ** *的* ** ]]"],
  ["CASE2 no-space bolditalic", "[[\\h:blue:purple|*是* ***的***]]"],
];

for (const [name, line] of cases) {
  console.log("=".repeat(80));
  console.log("### " + name + "  ::  " + line);
  const body = "前置文本\n" + line + "\n结尾";
  const doc = parser.parse(body);
  mapper.setDoc(doc);

  // locate the paragraph block containing the highlight
  let para = null, paraIdx = -1;
  for (let i = 0; i < doc.blocks.length; i++) {
    const b = doc.blocks[i];
    if (b.type === "paragraph" && JSON.stringify(b).indexOf("highlight") >= 0) { para = b; paraIdx = i; break; }
  }
  console.log("paragraph blockIndex=" + paraIdx);
  para.children.forEach(n => console.log(dumpNode(n, 2)));

  const container = renderer.render(doc);
  global._renderedBlocks = {};
  container.querySelectorAll(".m0-src-block").forEach(el => {
    global._renderedBlocks[parseInt(el.getAttribute("data-m0-block-index"), 10)] = el;
  });

  const pEl = global._renderedBlocks[paraIdx];
  const textNodes = [];
  collectAllTextNodes(pEl, textNodes);
  console.log("rendered text: " + JSON.stringify(pEl.textContent));
  console.log("text nodes: " + textNodes.map(t => JSON.stringify(t.textContent)).join(" | "));

  // bidirectional consistency: domToAst -> astToSrc -> srcToAst should give same path/offset
  let failures = 0;
  for (let i = 0; i < textNodes.length; i++) {
    const tn = textNodes[i];
    for (let off = 0; off <= tn.textContent.length; off++) {
      const ast = mapper.domToAst(tn, off);
      if (!ast) { failures++; if (failures < 5) console.log(`  domToAst null node#${i} off=${off}`); continue; }
      const src = mapper.astToSrc(ast.blockIndex, ast.nodePath, ast.offset);
      if (!src) { failures++; if (failures < 5) console.log(`  astToSrc null node#${i} off=${off} ast=${keyOf(ast)}`); continue; }
      const back = mapper.srcToAst(src.line, src.col);
      if (!back || keyOf(back) !== keyOf(ast)) {
        failures++;
        if (failures < 10) console.log(`  ROUNDTRIP node#${i} off=${off} ast=${keyOf(ast)} -> src=${fmtSrc(src)} -> back=${back ? keyOf(back) : "null"}`);
      }
    }
  }
  console.log("roundtrip failures: " + failures);
  console.log("");
}
