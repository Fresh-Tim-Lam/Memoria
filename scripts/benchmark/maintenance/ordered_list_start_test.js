#!/usr/bin/env node
/* task-157 单测：有序列表 `start > 1` 的逐字节往返保真（含"编辑后整块回写"）
 *
 * 背景（真机 R0）：预览模式编辑列表项一个字 ⇒ `commit()` → `spliceBlockSource(generateBlock(block))`
 *   → 保存写盘。旧 source-gen 用 `idx + 1` 编号 ⇒ 任何非 1 起编号的列表被静默改成 1./2.。
 * 判据：逐字节 `generate(parse(src)) === src`（不是长度）、二次幂等、编辑后仍保真、mapper 列宽。
 * 用法：node scripts/benchmark/maintenance/ordered_list_start_test.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS_DIR = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js");
global.window = global;
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js", "mapper.js"]) {
  const file = path.join(JS_DIR, f);
  vm.runInThisContext(fs.readFileSync(file, "utf8"), { filename: file });
}
const P = global.MemoriaParser;
const G = global.MemoriaSourceGen;
const M = global.MemoriaMapper;

let pass = 0;
const fails = [];
function ok(name, cond, extra) {
  if (cond) { pass++; return; }
  fails.push(name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  console.log("FAIL  " + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
}
function j(v) { return JSON.stringify(v); }

// ── A. ③ AST 是否存 start（修复前提）────────────────────────────────────────
{
  const d1 = P.parse("10. ten\n11. eleven\n");
  ok("A1 `10.` 列表 AST.start=10", d1.blocks[0].type === "list" && d1.blocks[0].start === 10, d1.blocks[0].start);
  const d2 = P.parse("1. one\n2. two\n");
  ok("A2 `1.` 列表 start 为 null/1（不写 start 属性）", !d2.blocks[0].start || d2.blocks[0].start === 1, d2.blocks[0].start);
  const d3 = P.parse("> 10. ten\n> 11. eleven\n");
  const ql = (d3.blocks[0].children || []).find((c) => c.type === "list");
  ok("A3 引用块内有序列表 start=10", ql && ql.start === 10, ql && ql.start);
}

// ── B. 逐字节往返 + 幂等 ────────────────────────────────────────────────────
const SAMPLES = [
  "3. three\n4. four\n",
  "10. ten\n11. eleven\n",
  "9. nine\n10. ten\n",
  "99. big\n100. bigger\n",
  "1. one\n2. two\n",
  "- a\n- b\n",
  "> 10. ten\n> 11. eleven\n",
  "> 3. three\n> 4. four\n",
  "> 1. one\n> 2. two\n",
  "5. five\n   - sub a\n   - sub b\n6. six\n",
  "2. a\n   1. b\n3. c\n",
  "- a\n10. ten\n",
  "7. seven\n\n8. eight\n",
  "10. ten\n11. eleven\n\n3. three\n4. four\n",
  "2. a\n   3. b\n4. c\n",
];
for (const src of SAMPLES) {
  const gen = G.generate(P.parse(src));
  ok("B 往返字节相等: " + j(src.slice(0, 40)), gen === src, { gen: gen });
  ok("B 二次幂等: " + j(src.slice(0, 40)), G.generate(P.parse(gen)) === gen);
}

// INFO：修复后"手工继续编号/嵌套继续编号"均已逐字节保真（逐项 number 回写）。
console.log("INFO 逐项编号保真：`2. a / 3. b(嵌套) / 4. c` 往返 = " +
  JSON.stringify(G.generate(P.parse("2. a\n   3. b\n4. c\n"))));

// ── C. 编辑后整块回写仍保真（模拟预览编辑：改一个 item 的文本后 generate）──────
{
  const doc = P.parse("10. ten\n11. eleven\n");
  const list = doc.blocks[0];
  list.items[0].children.push(global.MemoriaAST.text("X")); // 等价于在 "ten" 后输入 X
  ok("C1 编辑 item 后编号保持 10./11.", G.generateBlock(list) === "10. tenX\n11. eleven", G.generateBlock(list));

  const doc2 = P.parse("> 前言\n> 10. qten\n> 11. qeleven\n");
  const bq = doc2.blocks[0];
  const qList = (bq.children || []).find((c) => c.type === "list");
  qList.items[0].children.push(global.MemoriaAST.text("W"));
  ok("C2 引用块内列表编辑后编号保持 > 10./> 11.",
    G.generateBlock(bq) === "> 前言\n> 10. qtenW\n> 11. qeleven", G.generateBlock(bq));

  const doc3 = P.parse("5. five\n   - sub a\n6. six\n");
  doc3.blocks[0].items[1].children.push(global.MemoriaAST.text("Z"));
  ok("C3 混合嵌套列表编辑后编号保持", G.generateBlock(doc3.blocks[0]) === "5. five\n   - sub a\n6. sixZ", G.generateBlock(doc3.blocks[0]));
}

// ── D. mapper 列宽（listPrefixLen 用真实 start/位数）─────────────────────────
function colOf(src, path, offset) {
  const doc = P.parse(src);
  M.setDoc(doc);
  const r = M.astToSrc(0, path, offset);
  return r && r.col;
}
{
  ok("D1 `10. x` 内容列=4（\"10. \"4 字符）", colOf("10. x", [0, 0, 0], 0) === 4, colOf("10. x", [0, 0, 0], 0));
  ok("D2 `100. x` 内容列=5", colOf("100. x", [0, 0, 0], 0) === 5, colOf("100. x", [0, 0, 0], 0));
  ok("D3 `> 10. x` 内容列=6（\"> \"2 + \"10. \"4）", colOf("> 10. x", [0, 0, 0], 0) === 6, colOf("> 10. x", [0, 0, 0], 0));
  // 松散合并列表：逐项手写序号宽度（`10,11,3,4` 的第三项 `3.` 是 2 列，不是 `12.` 的 3 列）
  const merged = "10. ten\n11. eleven\n\n3. three\n4. four\n";
  ok("D4 松散合并列表第3项（3.）内容列=3（\"3. \"）", colOf(merged, [2, 0, 0], 0) === 3, colOf(merged, [2, 0, 0], 0));
  ok("D5 松散合并列表第4项（4.）内容列=3（\"4. \"）", colOf(merged, [3, 0, 0], 0) === 3, colOf(merged, [3, 0, 0], 0));
  const long = "5. five\n6. six\n7. seven\n8. eight\n9. nine\n10. ten\n";
  ok("D6 递增到两位数：第6项（10.）内容列=4", colOf(long, [5, 0, 0], 0) === 4, colOf(long, [5, 0, 0], 0));
}

// ── E. 既有行为：`A.list()` 新建（无 start）仍从 1 编号（不可回退的"新列表"语义）───
{
  const A = global.MemoriaAST;
  const newList = A.list(true, [A.listItem([A.text("a")]), A.listItem([A.text("b")])]);
  ok("E1 新建无 start 的有序列表 ⇒ 1./2.（保持既有新列表语义）", G.generateBlock(newList) === "1. a\n2. b", G.generateBlock(newList));
}

console.log("\n=== SUMMARY === PASS=" + pass + " FAIL=" + fails.length);
if (fails.length) { fails.forEach((f) => console.log("  - " + f)); process.exit(1); }
process.exit(0);
