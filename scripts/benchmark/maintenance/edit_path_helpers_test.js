#!/usr/bin/env node
/* task-156 Step0 单测：app.js 的编辑路径/行区间 helper（后续所有改动的口径来源）
 *
 * 白盒：从真实 app.js 抽取 helper 区（marker 之间），在 vm 中注入 _doc/_blockLineMap 后断言。
 * 覆盖 Lead 要求的 4 组：
 *   · list child（跨多行）的行区间
 *   · paragraph child（1 行）的行区间
 *   · 嵌套 list（引用内 list 内 list）
 *   · 旧 AST（无 srcLine/srcLineEnd）的兜底
 * 用法：node scripts/benchmark/maintenance/edit_path_helpers_test.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "app.js");
const src = fs.readFileSync(APP, "utf8");
const START_MARK = "    // ── task-156 二期 Step0：编辑路径 / 行区间 helper";
const END_MARK = "    // ── end: edit path helpers ──";
const start = src.indexOf(START_MARK);
const end = src.indexOf(END_MARK);
if (start < 0 || end < 0 || end <= start) {
  console.error("无法定位 task-156 helper 区（marker 缺失）");
  process.exit(1);
}
const helperSrc = src.slice(start, end);

let pass = 0;
const fails = [];
function ok(name, cond, extra) {
  if (cond) { pass++; return; }
  fails.push(name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  console.log("FAIL  " + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
}
const j = JSON.stringify;

function makeSandbox(doc, lineMap) {
  const sandbox = { _doc: doc, _blockLineMap: lineMap };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(helperSrc, sandbox, { filename: "app-helpers.js" });
  return sandbox;
}

// ── 夹具：一个引用块（段落 / 跨两行 list / 段落）+ 顶层 list ─────────────────
function fixture() {
  const childPara0 = { type: "paragraph", srcLine: 10, srcLineEnd: 10, children: [] };
  const childList = {
    type: "list", ordered: false, srcLine: 11, srcLineEnd: 12,
    items: [
      { type: "list_item", srcLine: 1, children: [{ type: "text", content: "a" }] },   // 切片相对
      { type: "list_item", srcLine: 2, children: [{ type: "text", content: "b" }] },
      { type: "list_item", srcLine: 4, children: [{ type: "text", content: "d" }] },   // 松散：跳过 1 行
      { type: "list_item", children: [{ type: "text", content: "legacy" }] },          // 无 srcLine 兜底
      {
        type: "list_item", srcLine: 6, children: [{ type: "text", content: "x" }],
        list: { type: "list", ordered: true, start: 3, items: [{ type: "list_item", srcLine: 7, children: [] }] },
      },
    ],
  };
  const childPara2 = { type: "paragraph", srcLine: 13, srcLineEnd: 13, children: [] };
  const quoteBlock = {
    type: "blockquote", srcLine: 10, srcLineEnd: 13, prefixes: ["> ", "> ", "> ", "> "],
    children: [childPara0, childList, childPara2],
  };
  const plain = { type: "paragraph", srcLine: 14, srcLineEnd: 14, children: [] };
  const topList = {
    type: "list", ordered: true, start: 10, srcLine: 15, srcLineEnd: 17,
    items: [
      { type: "list_item", srcLine: 15, children: [] },
      { type: "list_item", srcLine: 16, children: [] },
      { type: "list_item", srcLine: 17, children: [] },
    ],
  };
  const doc = { blocks: [quoteBlock, plain, topList] };
  // block0 起始于源码第 10 行（1-based）⇒ 0-based startLine = 9
  const lineMap = {
    0: { startLine: 9, endLine: 12 },
    1: { startLine: 13, endLine: 13 },
    2: { startLine: 14, endLine: 16 },
  };
  return { doc, lineMap, quoteBlock, childList, topList };
}

// ── A. _parseEditPath ──────────────────────────────────────────────────────
{
  const { doc, lineMap, quoteBlock, childList, topList } = fixture();
  const S = makeSandbox(doc, lineMap);
  const paraPath = S._parseEditPath(quoteBlock, [0, 0, 2]);
  ok("A1 引用+段落：childIdx/itemIdx/inlinePath",
    paraPath && paraPath.kind === "quote" && paraPath.childIdx === 0 && paraPath.itemIdx === null &&
    j(paraPath.inlinePath) === "[0,2]", paraPath);

  const listPath = S._parseEditPath(quoteBlock, [1, 2, 0]);
  ok("A2 引用+列表项：childIdx=1 itemIdx=2 inlinePath=[0]（path.slice(2)）",
    listPath && listPath.kind === "quote" && listPath.childIdx === 1 && listPath.itemIdx === 2 &&
    listPath.item === childList.items[2] && j(listPath.inlinePath) === "[0]", listPath && j(listPath.inlinePath));

  const listChildOnly = S._parseEditPath(quoteBlock, [1]);
  ok("A3 引用+list child 但只有 childIdx：itemIdx=null、inlineRoot=[]（不得误当段落）",
    listChildOnly && listChildOnly.itemIdx === null && j(listChildOnly.inlineRoot) === "[]", listChildOnly);

  const top = S._parseEditPath(topList, [1, 0]);
  ok("A4 顶层列表：itemIdx=1、inlinePath=[0]", top && top.kind === "list" && top.itemIdx === 1 &&
    j(top.inlinePath) === "[0]", top && j(top.inlinePath));

  const plainB = S._parseEditPath(doc.blocks[1], [0]);
  ok("A5 普通段落块：kind=block、inlinePath 原样", plainB && plainB.kind === "block" && j(plainB.inlinePath) === "[0]", plainB);

  ok("A6 空 nodePath 的引用块 ⇒ null（不猜 child0）", S._parseEditPath(quoteBlock, []) === null);
  ok("A7 越界 childIdx ⇒ null", S._parseEditPath(quoteBlock, [99, 0]) === null);
  ok("A8 block=null ⇒ null", S._parseEditPath(null, [0]) === null);
}

// ── B. _childLineRange ─────────────────────────────────────────────────────
{
  const { doc, lineMap } = fixture();
  const S = makeSandbox(doc, lineMap);
  const p0 = S._childLineRange(0, 0);
  ok("B1 paragraph child（1 行）：{9,9}", p0 && p0.startLine === 9 && p0.endLine === 9, p0);
  const p1 = S._childLineRange(0, 1);
  ok("B2 list child（跨 2 行）：{10,11}", p1 && p1.startLine === 10 && p1.endLine === 11, p1);
  const p2 = S._childLineRange(0, 2);
  ok("B3 尾段：{12,12}", p2 && p2.startLine === 12 && p2.endLine === 12, p2);
  ok("B4 无 lineMap 的块 ⇒ null", S._childLineRange(99, 0) === null);
  ok("B5 childIdx 越界 ⇒ null", S._childLineRange(0, 99) === null);

  // 旧 AST（child 无 srcLine/srcLineEnd）⇒ 1 child = 1 行兜底
  const legacyDoc = { blocks: [{ type: "blockquote", srcLine: 1, children: [
    { type: "paragraph", children: [] }, { type: "paragraph", children: [] },
  ] }] };
  const S2 = makeSandbox(legacyDoc, { 0: { startLine: 5, endLine: 6 } });
  const l0 = S2._childLineRange(0, 0);
  const l1 = S2._childLineRange(0, 1);
  ok("B6 旧 AST 兜底：child0→{5,5}", l0 && l0.startLine === 5 && l0.endLine === 5, l0);
  ok("B7 旧 AST 兜底：child1→{6,6}", l1 && l1.startLine === 6 && l1.endLine === 6, l1);
}

// ── C. _quoteItemLineRange（含松散列表空行、嵌套 list、旧项兜底）──────────────
{
  const { doc, lineMap } = fixture();
  const S = makeSandbox(doc, lineMap);
  const it0 = S._quoteItemLineRange(0, 1, 0);
  ok("C1 item0（切片相对 1）⇒ 块首行9 + 0 = 9", it0 && it0.startLine === 9 && it0.endLine === 9, it0);
  const it1 = S._quoteItemLineRange(0, 1, 1);
  ok("C2 item1（相对 2）⇒ 9 + 1 = 10", it1 && it1.startLine === 10, it1);
  const it2 = S._quoteItemLineRange(0, 1, 2);
  ok("C3 松散列表 item2（相对 4）⇒ 9 + 3 = 12", it2 && it2.startLine === 12, it2);
  const it3 = S._quoteItemLineRange(0, 1, 3);
  ok("C4 无 srcLine 的项兜底：child 首行10 + itemIdx3 = 13", it3 && it3.startLine === 13, it3);
  const nested = S._quoteItemLineRange(0, 1, 4);
  ok("C5 嵌套 list 的父项（相对 6）⇒ 9 + 5 = 14", nested && nested.startLine === 14, nested);
  ok("C6 越界 item ⇒ null", S._quoteItemLineRange(0, 1, 99) === null);
}

// ── D. _segPos（跨段/跨项判定）─────────────────────────────────────────────
{
  const { doc, lineMap } = fixture();
  const S = makeSandbox(doc, lineMap);
  ok("D1 引用段落 child0 ⇒ 0", S._segPos(doc.blocks[0], { nodePath: [0, 0] }) === 0);
  ok("D2 引用 list child1 item0 ⇒ 100001", S._segPos(doc.blocks[0], { nodePath: [1, 0] }) === 100001);
  ok("D3 引用 list child1 item2 ⇒ 100003", S._segPos(doc.blocks[0], { nodePath: [1, 2, 0] }) === 100003);
  ok("D4 同 list 内跨 item：item3 序位 > item1（不返回 false 的依据）",
    S._segPos(doc.blocks[0], { nodePath: [1, 3] }) > S._segPos(doc.blocks[0], { nodePath: [1, 1] }));
  ok("D5 顶层列表 item2 ⇒ 2", S._segPos(doc.blocks[2], { nodePath: [2, 0] }) === 2);
  ok("D6 空路径 ⇒ -1", S._segPos(doc.blocks[0], { nodePath: [] }) === -1);
}

console.log("\n=== SUMMARY === PASS=" + pass + " FAIL=" + fails.length);
if (fails.length) { fails.forEach((f) => console.log("  - " + f)); process.exit(1); }
process.exit(0);
