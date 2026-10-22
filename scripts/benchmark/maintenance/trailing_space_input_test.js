#!/usr/bin/env node
/* E27 / E29 单测：**块末尾（含样式节点内）空格**的源码保留 + 预览可见宽度。
 *
 * 背景（2026-10-22）：
 *   E27「样式文字末尾无法输入空格」/ E29「预览区英文单词后无法输入空格」。
 *   真机 + CDP 复现结论：`EditSync.insertText(" ")` 与 `parser → source-gen`
 *   **都正确写入了空格**（`state.doc.body` 末尾确有 `" "`）；丢的是**渲染宽度** ——
 *   `.-preview` 的 `white-space` 是默认 `normal`，CSS 折叠行尾空格 ⇒ 空格零宽、光标不动，
 *   用户看到「敲空格没反应」。样式节点内（`**…**` / `[[\h|…]]`）同理：空格仍在行尾。
 *   与 E28（lexer 把 `>` 后的语法空格吃进前缀）**不同层**：E28 丢源码字节，本缺陷源码字节正确。
 *
 * 本测试锁三层：
 *   L1 源码层：parse→generate 对「末尾空格」逐字节保留（普通 / bold / italic / highlight）。
 *   L2 编辑层：模拟 `EditSync.insertText(" ")` 在 AST 最后一个 Text 叶上追加（app.js 的真实路径）
 *              ⇒ generate 必须把空格写回源码；连续两个空格同样保留。
 *   L3 呈现层：render-core 只在该块「最后一个文本节点以空格/制表符结尾」时给其宿主元素
 *              加内联 `white-space: pre-wrap`（让尾随空格占宽）；非尾部空格、无空格不得加。
 *
 * 用法：node scripts/benchmark/maintenance/trailing_space_input_test.js
 * 退出码：0 = 全 PASS；1 = 有 FAIL。
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS_DIR = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js");

// ── 浏览器全局脚本（ast → lexer → parser → source-gen → render-core）──
global.window = global;

// ── 最小 DOM 桩：只实现 render-core 用到的节点 API（不引 jsdom）──────────────
function makeDom() {
  let doc = null;

  function textNode(value) {
    const n = {
      nodeType: 3,
      nodeValue: String(value),
      textContent: String(value),
      parentElement: null,
      parentNode: null,
    };
    return n;
  }

  function element(tag) {
    const el = {
      nodeType: 1,
      tagName: String(tag).toUpperCase(),
      style: {},
      className: "",
      childNodes: [],
      attrs: {},
      parentElement: null,
      parentNode: null,
      appendChild(child) {
        if (child && child.__fragment) {
          child.childNodes.slice().forEach((c) => el.appendChild(c));
          child.childNodes.length = 0;
          return child;
        }
        child.parentNode = el;
        child.parentElement = el.nodeType === 1 ? el : null;
        el.childNodes.push(child);
        return child;
      },
      setAttribute(k, v) { el.attrs[k] = String(v); },
      getAttribute(k) { return Object.prototype.hasOwnProperty.call(el.attrs, k) ? el.attrs[k] : null; },
      removeAttribute(k) { delete el.attrs[k]; },
      querySelector() { return null; },
      querySelectorAll() { return []; },
      closest() { return null; },
      contains() { return false; },
    };
    Object.defineProperty(el, "textContent", {
      get() {
        return el.childNodes.map((c) => (c.nodeType === 3 ? c.nodeValue : c.textContent)).join("");
      },
      set(v) {
        el.childNodes.length = 0;
        if (v !== "") el.appendChild(textNode(v));
      },
    });
    Object.defineProperty(el, "innerHTML", {
      get() { return el.__innerHTML || ""; },
      set(v) {
        el.__innerHTML = String(v);
        el.childNodes.length = 0;
      },
    });
    return el;
  }

  function fragment() {
    const f = element("#fragment");
    f.__fragment = true;
    return f;
  }

  function walkText(root) {
    const out = [];
    (function walk(n) {
      if (n.nodeType === 3) { out.push(n); return; }
      (n.childNodes || []).forEach(walk);
    })(root);
    return out;
  }

  doc = {
    createElement: (tag) => element(tag),
    createTextNode: (v) => textNode(v),
    createDocumentFragment: () => fragment(),
    createTreeWalker(root) {
      const nodes = walkText(root);
      let i = 0;
      return { nextNode() { return i < nodes.length ? nodes[i++] : null; } };
    },
  };
  return { document: doc, treeTextNodes: walkText };
}

const dom = makeDom();
global.document = dom.document;
global.NodeFilter = { SHOW_TEXT: 4 };

for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js", path.join("surface", "render-core.js")]) {
  const file = path.join(JS_DIR, f);
  vm.runInThisContext(fs.readFileSync(file, "utf8"), { filename: file });
}

const AST = global.MemoriaAST;
const P = global.MemoriaParser;
const G = global.MemoriaSourceGen;
const RC = global.MemoriaRenderCore;

let pass = 0;
const failures = [];
function ok(cond, label, detail) {
  if (cond) { pass++; return; }
  failures.push(label + (detail !== undefined ? "  [" + JSON.stringify(detail) + "]" : ""));
}
function eq(actual, expected, label) {
  ok(actual === expected, label, { expected, got: actual });
}

// ── L1：源码层往返（块末尾空格逐字节保留）──────────────────────────────────
const ROUNDTRIP = [
  ["word", "普通文本末尾"],
  ["word ", "普通文本已有尾随空格"],
  ["**bold**", "加粗节点末尾"],
  ["**bold **", "加粗节点内尾随空格"],
  ["**bold** ", "加粗标记 ** 之后的尾随空格（语法标记不破坏）"],
  ["*italic*", "斜体节点末尾"],
  ["*italic *", "斜体节点内尾随空格"],
  ["*italic* ", "斜体标记 * 之后的尾随空格"],
  ["[[\\h|highlighted]]", "高亮节点末尾"],
  ["[[\\h|highlighted]] ", "高亮标记 ]] 之后的尾随空格"],
  ["[[\\b|abc]] ", "字体加粗标记 ]] 之后的尾随空格"],
  ["[[\\h|highlighted ]]", "高亮节点内尾随空格"],
  ["[[\\c:red|colored ]]", "颜色节点内尾随空格"],
  ["[[\\b|fontbold ]]", "字体加粗节点内尾随空格"],
  ["plain **bold ** tail ", "混排 + 整段尾随空格"],
];
for (const [src, label] of ROUNDTRIP) {
  const gen = G.generate(P.parse(src));
  eq(gen, src, "L1 parse→generate 保留末尾空格 · " + label);
}
// 二次往返幂等（E28 同口径：不得每轮再补/再吞空格）
for (const [src] of ROUNDTRIP) {
  const once = G.generate(P.parse(src));
  eq(G.generate(P.parse(once)), once, "L1 二次往返稳定 · " + JSON.stringify(src));
}

// ── L2：模拟 EditSync.insertText(" ") 的 AST 写入路径 ─────────────────────────
/** 取 block 的 children 容器（列表取首项；blockquote 取首段，与 parser 形状一致）。 */
function inlineChildrenOf(block) {
  if (!block) return null;
  if (block.type === "list") return block.items && block.items[0] ? block.items[0].children : null;
  if (block.type === "blockquote") {
    const p = block.children && block.children[0];
    return p && p.children ? p.children : null;
  }
  return block.children || null;
}
/** 找到 children 里最后一个 Text 叶（递归），返回节点引用。 */
function lastTextLeaf(nodes) {
  if (!nodes) return null;
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    if (n.type === "text") return n;
    if (n.children) {
      const sub = lastTextLeaf(n.children);
      if (sub) return sub;
    }
  }
  return null;
}
function insertSpaceAtEnd(src) {
  const doc = P.parse(src);
  const block = doc.blocks[0];
  const leaves = inlineChildrenOf(block);
  const leaf = lastTextLeaf(leaves);
  if (!leaf) throw new Error("no text leaf: " + JSON.stringify(src));
  leaf.content = leaf.content + " ";
  return G.generate(doc);
}

const INSERT_CASES = [
  ["word", "word ", "普通文本末尾插入空格"],
  ["**bold**", "**bold **", "加粗文字末尾插入空格（落在 ** 内）"],
  ["*italic*", "*italic *", "斜体文字末尾插入空格（落在 * 内）"],
  ["[[\\h|highlighted]]", "[[\\h|highlighted ]]", "高亮文字末尾插入空格（落在 ]] 内）"],
  ["[[\\c:red|colored]]", "[[\\c:red|colored ]]", "颜色文字末尾插入空格（落在 ]] 内）"],
  ["> a", "> a ", "引用块正文末尾插入空格"],
];
for (const [src, want, label] of INSERT_CASES) {
  eq(insertSpaceAtEnd(src), want, "L2 EditSync.insertText(' ') · " + label);
  eq(G.generate(P.parse(want)), want, "L2 写回源码二次往返稳定 · " + label);
}
// 连续两个空格：逐次追加，源码必须是两个空格（不是被 trim 成一个/吞掉）
(function () {
  const once = insertSpaceAtEnd("word");
  eq(once, "word ", "L2 第一次空格");
  const twice = insertSpaceAtEnd(once);
  eq(twice, "word  ", "L2 第二次空格（连续空格逐个保留）");
  eq(G.generate(P.parse(twice)), "word  ", "L2 两个尾随空格往返稳定");
})();
// E27 验收口径：样式节点内连续两个空格 ⇒ `[[\b|abc  ]]` / `**bold  **`
(function () {
  const hl1 = insertSpaceAtEnd("[[\\b|abc]]");
  const hl2 = insertSpaceAtEnd(hl1);
  eq(hl2, "[[\\b|abc  ]]", "L2 样式节点内连续两个空格（E27 验收）");
  eq(G.generate(P.parse(hl2)), hl2, "L2 样式节点内两个空格保存后重开仍在");

  const b1 = insertSpaceAtEnd("**bold**");
  const b2 = insertSpaceAtEnd(b1);
  eq(b2, "**bold  **", "L2 加粗节点内连续两个空格");
  eq(G.generate(P.parse(b2)), b2, "L2 加粗节点内两个空格保存后重开仍在");
})();
// 中文词后空格同样保留（E29 验收要求「中文词后同测」）
(function () {
  const once = insertSpaceAtEnd("中文");
  eq(once, "中文 ", "L2 中文词后空格");
  eq(insertSpaceAtEnd(once), "中文  ", "L2 中文词后连续两个空格");
})();
// 空格后再打字：空格不得被覆盖/吞掉
(function () {
  let src = insertSpaceAtEnd("word");
  const doc = P.parse(src);
  const leaf = lastTextLeaf(inlineChildrenOf(doc.blocks[0]));
  leaf.content += "x";
  eq(G.generate(doc), "word x", "L2 空格后再打字不丢空格（普通）");

  let src2 = insertSpaceAtEnd("[[\\b|abc]]");
  const doc2 = P.parse(src2);
  const leaf2 = lastTextLeaf(inlineChildrenOf(doc2.blocks[0]));
  leaf2.content += "x";
  eq(G.generate(doc2), "[[\\b|abc x]]", "L2 样式节点内空格后再打字不丢空格");
})();

// ── L3：呈现层（render-core 只给「尾随空白」的宿主加 pre-wrap）───────────────
const core = RC.createRenderCore({});
function render(src) {
  return core.renderBlock(P.parse(src).blocks[0], 0);
}
function lastText(root) {
  const nodes = dom.treeTextNodes(root);
  return nodes.length ? nodes[nodes.length - 1] : null;
}
function hostOf(node) { return node && node.parentElement ? node.parentElement : node; }
function whiteSpaceOf(host) { return host && host.style ? host.style.whiteSpace : undefined; }

(function () {
  const el = render("word ");
  const ls = lastText(el);
  ok(!!ls && whiteSpaceOf(hostOf(ls)) === "pre-wrap",
    "L3 普通段落尾随空格 ⇒ 宿主 white-space: pre-wrap", { ws: ls ? whiteSpaceOf(hostOf(ls)) : null });
})();

(function () {
  const el = render("[[\\h|highlighted ]]");
  const ls = lastText(el);
  ok(!!ls && whiteSpaceOf(hostOf(ls)) === "pre-wrap", "L3 高亮节点内尾随空格 ⇒ 该 span 加 pre-wrap");
  ok(!!el && !el.style.whiteSpace, "L3 高亮块外层 p 不被无谓改写");
})();

(function () {
  const el = render("**bold **");
  const ls = lastText(el);
  ok(!!ls && whiteSpaceOf(hostOf(ls)) === "pre-wrap", "L3 加粗节点内尾随空格 ⇒ strong 加 pre-wrap");
})();

(function () {
  const el = render("[[\\b|abc ]]");
  const ls = lastText(el);
  ok(!!ls && whiteSpaceOf(hostOf(ls)) === "pre-wrap", "L3 `[[\\b|…]]` 节点内尾随空格 ⇒ 该 span 加 pre-wrap");
})();

(function () {
  const el = render("word");
  ok(!el.style.whiteSpace, "L3 无尾随空格 ⇒ 不加 pre-wrap（渲染基线不变）");
})();

(function () {
  const el = render("word  more");
  ok(!el.style.whiteSpace, "L3 中间多空格（非尾部）⇒ 不加 pre-wrap（不改变既有折叠行为）");
})();

// E28 回归：空引用块（无文本节点）不因本修复被改写
(function () {
  const el = render("> ");
  ok(!!el && !el.style.whiteSpace, "L3 空引用块 `> ` 不加 pre-wrap（E28 渲染不受影响）");
})();
// E28 内容空格：`>  `（第二个空格是正文）⇒ 引用内段落需要可见宽度
(function () {
  const el = render(">  ");
  const ls = lastText(el);
  ok(!!ls && whiteSpaceOf(hostOf(ls)) === "pre-wrap", "L3 `>  ` 的内容空格 ⇒ 引用段落加 pre-wrap");
})();

// ── 汇总 ────────────────────────────────────────────────────────────────────
console.log("");
if (failures.length) {
  console.log("FAIL " + failures.length + " / PASS " + pass);
  failures.forEach((f) => console.log("  - " + f));
  process.exit(1);
}
console.log("PASS " + pass + " 项（E27/E29 末尾空格：源码保留 + 预览可见宽度）");
process.exit(0);
