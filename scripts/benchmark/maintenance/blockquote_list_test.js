#!/usr/bin/env node
/* task-155 一期单测：引用块内列表（`> - item`）
 *
 * 判据（Lead 一期验收）：
 *   A. AST：`> - a\n> - b` ⇒ blockquote.children = [list]，2 项（改前应为 2 个 paragraph ⇒ 红）
 *   B. 逐字节：parse→generate 往返 == 原文，且二次往返幂等（**基线已绿，必须保持绿**）
 *      样本含 Eigen_Face.md:155-158 真实形态、`>`（空引用行）、`>abc`/`>>` 无空格前缀、松散列表、有序、行内格式/数学
 *   C. mapper 列号：
 *       · `>abc`（无空格） 内容起点 col=1（旧实现恒给 2 ⇒ 红）
 *       · `>> abc`（嵌套） 内容起点 col=3（旧实现恒给 2 ⇒ 红）
 *       · `> - a`（新能力） 列表项内容起点 col=4（`> ` + `- `）
 *       · `> 10. x`（有序 ≥10 项） 内容起点 col=6（`> ` + `10. `）
 *       · 反向（AST→源码）同样校验上述列
 * 用法：node scripts/benchmark/maintenance/blockquote_list_test.js
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

// ── A. AST：引用块内列表 ───────────────────────────────────────────────────
function firstQuote(src) {
  const doc = P.parse(src);
  return (doc.blocks || []).find((b) => b.type === "blockquote");
}
{
  const q = firstQuote("> - a\n> - b");
  ok("A1 `> - a\\n> - b` 解析出 blockquote", !!q);
  const kids = (q && q.children) || [];
  ok("A2 children 里出现 list（改前是 2 个 paragraph）", kids.length === 1 && kids[0].type === "list",
    { types: kids.map((k) => k.type) });
  ok("A3 list 有 2 个 item", kids[0] && kids[0].type === "list" && (kids[0].items || []).length === 2,
    { items: kids[0] && kids[0].items && kids[0].items.length });
  const q2 = firstQuote("> 前言\n> - a\n> - b\n> 后记");
  const k2 = (q2 && q2.children) || [];
  ok("A4 前后段落 + 中间列表：types = paragraph,list,paragraph",
    k2.length === 3 && k2[0].type === "paragraph" && k2[1].type === "list" && k2[2].type === "paragraph",
    { types: k2.map((k) => k.type) });
  const q3 = firstQuote("> 1. a\n> 2. b");
  ok("A5 有序列表识别", (q3 && q3.children && q3.children[0] && q3.children[0].type === "list" &&
    q3.children[0].ordered === true), { kids: q3 && q3.children && q3.children.map((k) => k.type) });
  const q4 = firstQuote("> - a\n>   - nested");
  const c4 = (q4 && q4.children && q4.children[0]) || null;
  ok("A6 嵌套列表（缩进）挂到 item.list", !!(c4 && c4.type === "list" && c4.items && c4.items[0] &&
    c4.items[0].list && c4.items[0].list.items && c4.items[0].list.items.length === 1), c4 && c4.type);
}

// ── B. 逐字节往返（基线，必须全绿）────────────────────────────────────────
const SAMPLES = [
  "> - a\n> - b",
  "> - 从一堆人脸中提炼出 $ k $ 个“基础脸型”（特征人脸）\n> - 每张人脸表示为这些基础脸型的加权组合（$ k $ 个系数）\n> - 识别时比较两张脸的系数向量是否接近\n> - 原始需要 $ d^2 $ 个数，现在只需要 $ k $ 个数（$ k \\ll d^2 $）",
  "> **特征人脸法 = PCA + SVD技巧 + 投影降维 + 最近邻识别**\n>\n> - 从一堆人脸中提炼出 $ k $ 个“基础脸型”（特征人脸）\n> - 每张人脸表示为这些基础脸型的加权组合（$ k $ 个系数）",
  "> plain quote",
  ">",
  "> ",
  ">abc",
  ">> abc",
  "> > abc",
  "> - a\n>\n> - b",
  "> - a\n>   - nested\n>   - nested2\n> - b",
  "> 1. a\n> 2. b",
  "> 1. ten\n> 2. eleven",
  "> # 引用里的标题（本期仍是段落文本）",
  "> - $x$ **bold** `code`",
];
// INFO（非本轮引入）：有序列表 start>1 的往返重编号是既有行为（source-gen 按 idx 重新编号），
//   与 task-155 无关，仅记录，不作为一期判据。
console.log("INFO 既有行为（非本轮）：`10. ten\\n11. eleven` 往返 = " +
  JSON.stringify(G.generate(P.parse("10. ten\n11. eleven"))));

for (const src of SAMPLES) {
  const gen = G.generate(P.parse(src));
  ok("B 往返字节相等: " + j(src.slice(0, 46)), gen === src, { gen: gen });
  ok("B 二次幂等: " + j(src.slice(0, 46)), G.generate(P.parse(gen)) === gen);
}

// ── C. mapper 列号（引用前缀宽度 + 引用内列表）─────────────────────────────
function mapBack(src, nodePath, offset) {
  const doc = P.parse(src);
  M.setDoc(doc);
  return M.astToSrc(0, nodePath, offset || 0);
}
function mapFwd(src, line, col) {
  const doc = P.parse(src);
  M.setDoc(doc);
  return M.srcToAst(line, col);
}
{
  const b1 = mapBack(">abc", [0, 0], 0);
  ok("C1 `>abc` 反向：内容起点 col=1（旧实现错给 2）", b1 && b1.line === 0 && b1.col === 1, b1);

  const b2 = mapBack(">> abc", [0, 0], 0);
  ok("C2 `>> abc` 反向：内容起点 col=3（旧实现错给 2）", b2 && b2.line === 0 && b2.col === 3, b2);

  // `> - a`：nodePath = [childIdx=0, itemIdx=0, inlineIdx=0]
  const b3 = mapBack("> - a", [0, 0, 0], 0);
  ok("C3 `> - a` 反向：列表项内容 col=4（`> `2 + `- `2）", b3 && b3.line === 0 && b3.col === 4, b3);

  const b4 = mapBack("> 10. x", [0, 0, 0], 0);
  ok("C4 `> 10. x` 反向：内容 col=6（`> `2 + `10. `4）", b4 && b4.line === 0 && b4.col === 6, b4);

  // 正向：源码列 → AST 坐标
  const f1 = mapFwd(">abc", 0, 1);
  ok("C5 `>abc` 正向：col1 ⇒ nodePath [0,0] offset0", f1 && j(f1.nodePath) === "[0,0]" && f1.offset === 0, f1);

  const f2 = mapFwd(">> abc", 0, 3);
  ok("C6 `>> abc` 正向：col3 ⇒ nodePath [0,0] offset0", f2 && j(f2.nodePath) === "[0,0]" && f2.offset === 0, f2);

  const f3 = mapFwd("> - a", 0, 4);
  ok("C7 `> - a` 正向：col4 ⇒ nodePath [0,0,0] offset0", f3 && j(f3.nodePath) === "[0,0,0]" && f3.offset === 0, f3);

  const f4 = mapFwd("> 10. x", 0, 6);
  ok("C8 `> 10. x` 正向：col6 ⇒ nodePath [0,0,0] offset0", f4 && j(f4.nodePath) === "[0,0,0]" && f4.offset === 0, f4);

  const f5 = mapFwd("> - a\n> - b", 1, 4);
  ok("C9 `> - a\\n> - b` 第二行 col4 ⇒ nodePath [0,1,0] offset0", f5 && j(f5.nodePath) === "[0,1,0]" && f5.offset === 0, f5);
}

// ── D. 旧 AST 防御（F3 契约不能被本期破坏）──────────────────────────────────
{
  const A = global.MemoriaAST;
  const bq = A.blockquote([A.paragraph([A.text("a")]), A.paragraph([A.text("b")])]);
  bq.prefixes = [">"];
  ok("D1 旧 AST（无跨度+prefixes 不等长）⇒ 全部回退默认 \"> \"", G.generateBlock(bq) === "> a\n> b", G.generateBlock(bq));
  const bq2 = A.blockquote([A.paragraph([A.text("a")]), A.paragraph([A.text("b")])]);
  bq2.prefixes = [">", ">> "];
  ok("D2 旧 AST（无跨度+prefixes 等长）⇒ 有序逐个回写", G.generateBlock(bq2) === ">a\n>> b", G.generateBlock(bq2));
}

console.log("\n=== SUMMARY === PASS=" + pass + " FAIL=" + fails.length);
if (fails.length) {
  console.log("失败明细：");
  fails.forEach((f) => console.log("  - " + f));
  process.exit(1);
}
process.exit(0);
