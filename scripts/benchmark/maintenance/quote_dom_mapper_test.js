#!/usr/bin/env node
/* task-156 单测：mapper._resolveQuoteDomTarget（引用块 DOM 光标 → 直接 child / 列表项）
 *
 * 背景：既有 R0 —— mapper.domToAst/astToDom 无 BLOCKQUOTE 分支，把 children 当内联数组，
 *   任何 child>0 都映射回 child0 ⇒ 预览编辑第 2 段/引用内列表项会覆盖第 1 段并写盘。
 *   本测试守护新增的 DOM 侧定位 helper（纯 DOM 遍历，可用假 DOM 单测）。
 * 覆盖：多段引用 / 段落+列表混合 / 列表内多 item / 嵌套列表 / 非法 DOM。
 * 用法：node scripts/benchmark/maintenance/quote_dom_mapper_test.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const MAPPER = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "mapper.js");
const src = fs.readFileSync(MAPPER, "utf8");

function extractFunction(name) {
  const head = "\n  function " + name + "(";
  const start = src.indexOf(head);
  if (start < 0) throw new Error("function not found: " + name);
  let i = src.indexOf("{", start + head.length - 1);
  if (i < 0) throw new Error("brace not found: " + name);
  let depth = 0, end = -1;
  for (let k = i; k < src.length; k++) {
    const ch = src[k];
    if (ch === "{") depth++;
    else if (ch === "}") { depth--; if (depth === 0) { end = k + 1; break; } }
  }
  if (end < 0) throw new Error("function end not found: " + name);
  return src.slice(start + 1, end);
}

const fnResolveItem = extractFunction("resolveListItem");
const fnQuoteTarget = extractFunction("_resolveQuoteDomTarget");
const helperSrc = [fnResolveItem, fnQuoteTarget].join("\n");

let pass = 0;
const fails = [];
function ok(name, cond, extra) {
  if (cond) { pass++; return; }
  fails.push(name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  console.log("FAIL  " + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
}
const j = JSON.stringify;

function makeSandbox() {
  const sandbox = {};
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(helperSrc, sandbox, { filename: "mapper-quote-helpers.js" });
  return sandbox;
}

// ── 假 DOM ─────────────────────────────────────────────────────────────────
function el(tag) {
  const node = { tagName: tag, parentElement: null, children: [], childNodes: [], classList: { contains: () => false } };
  node.appendChild = (c) => { c.parentElement = node; node.children.push(c); node.childNodes.push(c); return c; };
  node.text = (s) => {
    const t = { nodeType: 3, textContent: s, parentElement: node };
    node.children.push(t); node.childNodes.push(t); return t;
  };
  node.querySelectorAll = (sel) => {
    const want = String(sel || "").toUpperCase();
    const out = [];
    (function walk(n) {
      (n.children || []).forEach((c) => {
        if (c.tagName === want) out.push(c);
        walk(c);
      });
    })(node);
    return out;
  };
  return node;
}

function makeBody() {
  // 引用块 DOM：<p>前言</p><ul><li>q1</li><li><p>q2</p><ul><li>q2a</li></ul></li></ul><p>后记</p>
  const blockEl = el("BLOCKQUOTE");
  const p0 = el("P"); const t0 = p0.text("前言");
  const ul = el("UL");
  const li0 = el("LI"); const t1 = li0.text("q1");
  const li1 = el("LI"); const p2 = el("P"); const t2 = p2.text("q2"); li1.appendChild(p2);
  const uln = el("UL"); const lin = el("LI"); const tn = lin.text("q2a"); uln.appendChild(lin); li1.appendChild(uln);
  ul.appendChild(li0); ul.appendChild(li1);
  const p3 = el("P"); const t3 = p3.text("后记");
  blockEl.appendChild(p0); blockEl.appendChild(ul); blockEl.appendChild(p3);
  return { blockEl, p0, ul, li0, li1, p2, p3, t0, t1, t2, t3, tn, uln, lin };
}
function makeBlock() {
  // 与 DOM 同构的 AST：children = [paragraph, list(2 项，第2项含嵌套子列表), paragraph]
  return {
    type: "blockquote",
    children: [
      { type: "paragraph", children: [] },
      {
        type: "list", ordered: false,
        items: [
          { type: "list_item", children: [] },
          {
            type: "list_item", children: [],
            list: { type: "list", ordered: false, items: [{ type: "list_item", children: [] }] },
          },
        ],
      },
      { type: "paragraph", children: [] },
    ],
  };
}

{
  const S = makeSandbox();
  const dom = makeBody();
  const block = makeBlock();

  const r0 = S._resolveQuoteDomTarget(block, dom.blockEl, dom.t0);
  ok("A1 第 1 段文本 ⇒ childIdx=0, itemIdx=-1", r0 && r0.childIdx === 0 && r0.itemIdx === -1, r0);

  const r3 = S._resolveQuoteDomTarget(block, dom.blockEl, dom.t3);
  ok("A2 第 2 段文本 ⇒ childIdx=2, itemIdx=-1（不再映射回 child0）", r3 && r3.childIdx === 2 && r3.itemIdx === -1, r3);

  const r1 = S._resolveQuoteDomTarget(block, dom.blockEl, dom.t1);
  ok("A3 列表第 1 项 ⇒ childIdx=1, itemIdx=0", r1 && r1.childIdx === 1 && r1.itemIdx === 0 &&
    r1.childEl === dom.ul && r1.item === block.children[1].items[0], r1 && { c: r1.childIdx, i: r1.itemIdx });

  const r2 = S._resolveQuoteDomTarget(block, dom.blockEl, dom.t2);
  ok("A4 列表第 2 项（<li><p>text</p>）⇒ itemIdx=1", r2 && r2.childIdx === 1 && r2.itemIdx === 1 &&
    r2.item === block.children[1].items[1], r2 && { c: r2.childIdx, i: r2.itemIdx });

  const rn = S._resolveQuoteDomTarget(block, dom.blockEl, dom.tn);
  ok("A5 嵌套列表项（挂第 2 项下）⇒ childIdx=1, itemIdx=1（顶层项），listPath=[1,0]",
    rn && rn.childIdx === 1 && rn.itemIdx === 1 && rn.listPath && j(rn.listPath) === "[1,0]",
    rn && { c: rn.childIdx, i: rn.itemIdx, lp: rn.listPath });

  ok("A6 domNode 是 blockEl 自身（未进任何 child）⇒ null", S._resolveQuoteDomTarget(block, dom.blockEl, dom.blockEl) === null);

  // DOM 多出一个不在 AST 里的直接子元素 ⇒ childIdx 越界 ⇒ null
  const extra = el("P");
  dom.blockEl.appendChild(extra);
  ok("A7 DOM 直接子元素数 > AST children ⇒ null（不猜）", S._resolveQuoteDomTarget(block, dom.blockEl, extra) === null);
}

console.log("\n=== SUMMARY === PASS=" + pass + " FAIL=" + fails.length);
if (fails.length) { fails.forEach((f) => console.log("  - " + f)); process.exit(1); }
process.exit(0);
