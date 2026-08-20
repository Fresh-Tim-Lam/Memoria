// Compare applyStyle outcomes for MULTIPLE selection scenarios on both cases
const fs = require("fs");
const path = require("path");
global.window = global;

// ---------- minimal DOM shim ----------
class TextNode {
  constructor(text) { this.nodeType = 3; this.textContent = text; this.childNodes = []; this.children = []; this.tagName = "#text"; this.parentElement = null; }
}
class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = String(tag).toUpperCase();
    this.children = []; this.childNodes = []; this.parentElement = null;
    this.className = ""; this._attrs = {}; this.style = {}; this.contentEditable = "inherit";
    this._textContent = ""; this._innerHTML = "";
  }
  get classList() { const s = this; return { contains(c) { return (" " + s.className + " ").indexOf(" " + c + " ") >= 0; } }; }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  appendChild(n) { n.parentElement = this; this.childNodes.push(n); if (n.nodeType === 1) this.children.push(n); return n; }
  get textContent() { if (this.childNodes.length === 0) return this._textContent; return this.childNodes.map(c => c.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.children = []; this._textContent = v; if (v) { const tn = new TextNode(v); tn.parentElement = this; this.childNodes.push(tn); } }
  set innerHTML(v) { this.childNodes = []; this.children = []; this._innerHTML = v; if (v === "<br>") { const br = new Element("br"); br.parentElement = this; this.childNodes.push(br); this.children.push(br); } }
  get innerHTML() { return this._innerHTML; }
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
class Range {
  constructor() { this.startContainer = null; this.startOffset = 0; this.collapsedFlag = false; }
  setStart(n, o) { this.startContainer = n; this.startOffset = o; }
  setStartBefore(n) { const p = n.parentElement; this.startContainer = p; this.startOffset = p ? p.childNodes.indexOf(n) : 0; }
  collapse() { this.collapsedFlag = true; }
  get collapsed() { return this.collapsedFlag; }
}
class TreeWalker {
  constructor(root, whatToShow, filter) { this._q = []; this._f = filter || null; this._c(root); }
  _c(n) {
    if (n.nodeType === 3) {
      if (!this._f) { this._q.push(n); return; }
      const r = this._f.acceptNode(n);
      if (r === NodeFilter.FILTER_REJECT) return;
      if (r === NodeFilter.FILTER_ACCEPT) this._q.push(n);
      return;
    }
    n.childNodes.forEach(c => this._c(c));
  }
  nextNode() { return this._q.length ? this._q.shift() : null; }
}
const NodeFilter = { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2, FILTER_SKIP: 3 };
global.document = {
  createElement: t => new Element(t),
  createTextNode: t => new TextNode(t),
  createRange: () => new Range(),
  createTreeWalker: (r, w, f) => new TreeWalker(r, w, f),
  querySelector(sel) {
    if (global._blocks) { const m = sel.match(/^\.m0-src-block\[data-m0-block-index="(\d+)"\]$/); if (m) return global._blocks[+m[1]] || null; }
    return null;
  },
};
global.NodeFilter = NodeFilter;

const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js", "renderer.js", "mapper.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const A = window.MemoriaAST;
const parser = window.MemoriaParser;
const renderer = window.MemoriaRenderer;
const mapper = window.MemoriaMapper;
const G = window.MemoriaSourceGen;

// ---- machinery replication (from app.js) ----
function cloneInlineNode(node, children) {
  const copy = {};
  Object.keys(node).forEach(k => { if (k !== "children") copy[k] = node[k]; });
  copy.children = children;
  return copy;
}
function splitInlineAt(children, nodePath, offset) {
  if (!children || !nodePath || !nodePath.length) return null;
  const idx = nodePath[0];
  const node = children[idx];
  if (!node) return null;
  const before = children.slice(0, idx);
  const after = children.slice(idx + 1);
  if (nodePath.length === 1) {
    if (node.type !== "text") return null;
    const lText = node.content.slice(0, offset);
    const rText = node.content.slice(offset);
    const left = before.slice();
    const right = after.slice();
    if (lText) left.push(A.text(lText));
    if (rText) right.unshift(A.text(rText));
    return { left, right };
  }
  if (!node.children || !Array.isArray(node.children)) return null;
  const sub = splitInlineAt(node.children, nodePath.slice(1), offset);
  if (!sub) return null;
  const left2 = before.slice();
  const right2 = after.slice();
  if (sub.left.length) left2.push(cloneInlineNode(node, sub.left));
  if (sub.right.length) right2.unshift(cloneInlineNode(node, sub.right));
  return { left: left2, right: right2 };
}
const MERGEABLE_STYLES = { bold: 1, italic: 1, bold_italic: 1, strikethrough: 1, highlight: 1, font_color: 1, font_size: 1, font_bold: 1, font_italic: 1, font_underline: 1, font_superscript: 1, font_subscript: 1 };
function sameNodeAttrs(a, b) {
  const ka = Object.keys(a).filter(k => k !== "children");
  const kb = Object.keys(b).filter(k => k !== "children");
  if (ka.length !== kb.length) return false;
  for (const k of ka) if (a[k] !== b[k]) return false;
  return true;
}
function mergeAdjacentInline(nodes) {
  if (!nodes || !nodes.length) return nodes;
  const out = [];
  for (const n of nodes) {
    const last = out[out.length - 1];
    if (last && last.type === "text" && n.type === "text") {
      out[out.length - 1] = A.text(last.content + n.content);
      continue;
    }
    if (last && MERGEABLE_STYLES[last.type] && last.type === n.type && sameNodeAttrs(last, n) && last.children && n.children) {
      last.children = mergeAdjacentInline(last.children.concat(n.children));
      continue;
    }
    out.push(n);
  }
  return out;
}
function _wrapEmphasis(children, bold, italic) {
  if (bold && italic) return [A.boldItalic(children)];
  if (bold) return [A.bold(children)];
  if (italic) return [A.italic(children)];
  return children;
}
function _emphasis(nodes, mode, inBold, inItalic) {
  inBold = !!inBold; inItalic = !!inItalic;
  const out = [];
  for (const n of nodes) {
    const t = n.type;
    if (t === "bold" || t === "italic" || t === "bold_italic") {
      const curBold = (t === "bold" || t === "bold_italic");
      const curItalic = (t === "italic" || t === "bold_italic");
      out.push(..._emphasis(n.children || [], mode, inBold || curBold, inItalic || curItalic));
    } else if (n.children && n.children.length) {
      out.push(cloneInlineNode(n, _emphasis(n.children, mode, inBold, inItalic)));
    } else {
      let fb = inBold, fi = inItalic;
      if (mode === "bold") fb = true;
      else if (mode === "nobold") fb = false;
      else if (mode === "italic") fi = true;
      else if (mode === "noitalic") fi = false;
      out.push(..._wrapEmphasis([n], fb, fi));
    }
  }
  return mergeAdjacentInline(out);
}
function _stripHighlight(nodes) {
  const out = [];
  for (const n of nodes) {
    if (n.type === "highlight") {
      let stripped = _stripHighlight(n.children);
      if (n.fgColor) stripped = [A.fontColor(n.fgColor, stripped)];
      out.push(...stripped);
    } else if (n.children && n.children.length) out.push(cloneInlineNode(n, _stripHighlight(n.children)));
    else out.push(n);
  }
  return mergeAdjacentInline(out);
}
function _stripColorStyles(nodes) {
  let bg = null, fg = null, bgOk = true, fgOk = true, bgSeen = false, fgSeen = false;
  const stripped = (function walk(list, curBg, curFg) {
    const out = [];
    for (const n of list) {
      if (n.type === "highlight") out.push(...walk(n.children || [], n.color == null ? curBg : n.color, n.fgColor == null ? curFg : n.fgColor));
      else if (n.type === "font_color") out.push(...walk(n.children || [], curBg, n.color == null ? curFg : n.color));
      else if (n.children && n.children.length) out.push(cloneInlineNode(n, walk(n.children, curBg, curFg)));
      else {
        if (curBg == null) bgOk = false;
        else if (!bgSeen) { bgSeen = true; bg = curBg; }
        else if (curBg !== bg) bgOk = false;
        if (curFg == null) fgOk = false;
        else if (!fgSeen) { fgSeen = true; fg = curFg; }
        else if (curFg !== fg) fgOk = false;
        out.push(n);
      }
    }
    return out;
  })(nodes, null, null);
  return { bg: (bgOk && bgSeen) ? bg : null, fg: (fgOk && fgSeen) ? fg : null, children: mergeAdjacentInline(stripped) };
}
function _applyFontColor(nodes, color) {
  const st = _stripColorStyles(nodes);
  if (st.bg != null) return [A.highlight(st.bg, color || "red", st.children)];
  return [A.fontColor(color || "red", _stripFontColor(nodes))];
}
function _stripFontColor(nodes) {
  const out = [];
  for (const n of nodes) {
    if (n.type === "font_color") out.push(..._stripFontColor(n.children));
    else if (n.children && n.children.length) out.push(cloneInlineNode(n, _stripFontColor(n.children)));
    else out.push(n);
  }
  return mergeAdjacentInline(out);
}
function _applyHighlight(nodes, color) {
  const st = _stripColorStyles(nodes);
  if (st.fg != null) return [A.highlight(color || null, st.fg, st.children)];
  return [A.highlight(color || null, null, _stripHighlight(nodes))];
}

function extractSelection(block, startAst, endAst) {
  const splitEnd = splitInlineAt(block.children, endAst.nodePath, endAst.offset);
  if (!splitEnd) return null;
  const splitStart = splitInlineAt(splitEnd.left, startAst.nodePath, startAst.offset);
  if (!splitStart || !splitStart.right.length) return null;
  return { before: splitStart.left, middle: splitStart.right, after: splitEnd.right };
}

function runApply(line, selectText, fmt, color) {
  const body = "前置\n" + line + "\n后置";
  const doc = parser.parse(body);
  let para = null, paraIdx = -1;
  for (let i = 0; i < doc.blocks.length; i++) {
    if (doc.blocks[i].type === "paragraph" && JSON.stringify(doc.blocks[i]).indexOf("highlight") >= 0) { para = doc.blocks[i]; paraIdx = i; break; }
  }
  mapper.setDoc(doc);
  const container = renderer.render(doc);
  global._blocks = {};
  container.querySelectorAll(".m0-src-block").forEach(el => { global._blocks[+el.getAttribute("data-m0-block-index")] = el; });
  const pEl = global._blocks[paraIdx];
  const tns = [];
  (function collect(el) { for (const c of el.childNodes) { if (c.nodeType === 3) tns.push(c); else collect(c); } })(pEl);

  // locate selection range covering the target substring in rendered text
  const rendered = pEl.textContent;
  const selIdx = rendered.indexOf(selectText);
  if (selIdx < 0) return "  !! selectText not found in rendered: " + JSON.stringify(rendered);

  // find text nodes spanning [selIdx, selIdx+selectText.length)
  let acc = 0, startNode = null, startOff = 0, endNode = null, endOff = 0;
  for (const tn of tns) {
    const len = tn.textContent.length;
    if (startNode === null && acc <= selIdx && selIdx <= acc + len) {
      startNode = tn; startOff = selIdx - acc;
    }
    if (acc <= selIdx + selectText.length && selIdx + selectText.length <= acc + len) {
      endNode = tn; endOff = selIdx + selectText.length - acc;
      break;
    }
    acc += len;
  }
  if (!startNode || !endNode) return "  !! selection mapping failed";

  const startAst = mapper.domToAst(startNode, startOff);
  const endAst = mapper.domToAst(endNode, endOff);
  if (!startAst || !endAst) return "  !! domToAst null";
  const ex = extractSelection(para, startAst, endAst);
  if (!ex) return "  !! extract failed";

  const transformed = fmt === "fontcolor" ? _applyFontColor(ex.middle, color)
    : fmt === "highlight" ? _applyHighlight(ex.middle, color)
    : _emphasis(ex.middle, fmt, false, false);
  const merged = mergeAdjacentInline(ex.before.concat(transformed).concat(ex.after));
  return G.generateInlineList(merged);
}

const cases = [
  ["CASE1 spaces+nested", "[[\\h:blue:purple| *是* ** *的* ** ]]"],
  ["CASE2 no-space bolditalic", "[[\\h:blue:purple|*是* ***的***]]"],
];
for (const [name, line] of cases) {
  console.log("=".repeat(70));
  console.log("### " + name);
  console.log("  SRC: " + line);
  for (const sel of ["的", "是", " 的 ", " *是* "]) {
    const out = runApply(line, sel, "fontcolor", "red");
    console.log("  select " + JSON.stringify(sel) + " fontcolor=red:");
    console.log("    " + out);
  }
  console.log("");
}
