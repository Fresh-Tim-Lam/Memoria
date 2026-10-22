#!/usr/bin/env node
/* E28 补充单测：**键入序列**与**块行区间**（与 blockquote_roundtrip_test.js 互补）。
 *
 * blockquote_roundtrip_test.js 锁定「静态源码 parse↔generate 的字节/幂等」；
 * 本文件锁定预览区编辑真正走的路径：
 *   1) 用户在一个空段落里敲 `>`、再敲空格、再敲文字时，source 逐步怎么变；
 *   2) 引用块内再敲空格（内容空格）不被吞；
 *   3) `>` / `>a` / `>> ` 的前缀原样保留，不再「每键凭空插一个空格」；
 *   4) 引用块的 srcLine/srcLineEnd 覆盖段内 `>` 空行（spliceBlockSource 依赖它）。
 *
 * 用法：node scripts/benchmark/maintenance/blockquote_typing_sequence_test.js
 * 退出码：0 = 全 PASS；1 = 有 FAIL。
 */
"use strict";

const path = require("path");

globalThis.window = globalThis;
const BASE = path.resolve(__dirname, "../../../src/memoria/ui/static/app/js");
require(path.join(BASE, "ast.js"));
require(path.join(BASE, "lexer.js"));
require(path.join(BASE, "parser.js"));
require(path.join(BASE, "source-gen.js"));

const P = window.MemoriaParser;
const G = window.MemoriaSourceGen;
const AST = window.MemoriaAST;

let pass = 0;
const failures = [];

function ok(cond, label, detail) {
  if (cond) {
    pass++;
  } else {
    failures.push(label + (detail ? "  [" + detail + "]" : ""));
  }
}

function eq(actual, expected, label) {
  ok(
    actual === expected,
    label,
    "expected " + JSON.stringify(expected) + " got " + JSON.stringify(actual)
  );
}

function gen(src) {
  return G.generate(P.parse(src));
}

function blocks(src) {
  return P.parse(src).blocks;
}

/**
 * 取第 idx 个引用块的第 paraIdx 段的 inline 文本（模拟编辑管线读 AST 的那一层）。
 */
function quoteText(src, idx, paraIdx) {
  const bq = blocks(src).filter(function (b) {
    return b.type === "blockquote";
  })[idx || 0];
  if (!bq) return null;
  const para = (bq.children || [])[paraIdx || 0];
  if (!para) return null;
  return (para.children || [])
    .map(function (n) {
      return n.content || "";
    })
    .join("");
}

// ── 1. 键入序列：`>` → 空格 → 文字 ─────────────────────────────────────
(function () {
  // 空段落里敲 `>`：app 侧是 paragraph(text ">")，源码 `>`（不是空引用块以外的东西）
  eq(gen(">"), ">", "键入 `>` · 源码 `>`（旧实现会写成 `> `，凭空加空格）");

  // 再敲空格：源码 `> `；这一格是引用标记的分隔空格（语法空格）
  eq(gen("> "), "> ", "键入空格 · 源码 `> `，往返逐字节不变");
  eq(blocks("> ")[0].type, "blockquote", "`> ` 解析为引用块（空内容）");
  eq(quoteText("> "), "", "`> ` 正文为空（该空格是语法空格）");

  // 引用块内**再**敲空格：这是内容空格，必须保住
  eq(gen(">  "), ">  ", "引用块内再敲空格 · 源码 `>  `（第二个空格是内容）");
  eq(quoteText(">  "), " ", "`>  ` 正文为 1 个空格（内容空格未被吞）");

  // 继续敲字：`>  a` / `> a` 都要稳定，不得每次往返再插空格
  eq(gen(">  a"), ">  a", "键入文字 · `>  a` 往返不变");
  eq(gen("> a"), "> a", "键入文字 · `> a` 往返不变");
  eq(quoteText("> a"), "a", "`> a` 正文 `a`");
  eq(quoteText(">  a"), " a", "`>  a` 正文 ` a`（内容空格保留）");
})();

// ── 2. AST 侧追加空格（app.insertText 走过的路径）────────────────────────
(function () {
  // 取 `> a` 的引用段，在正文末尾追加一个空格后回写（等价于预览区再敲一个空格）
  const doc = P.parse("> a");
  const bq = doc.blocks[0];
  const para = bq.children[0];
  para.children.push(AST.text(" "));
  const out = G.generate(doc);
  eq(out, "> a ", "引用正文末尾追加空格 → `> a `");
  eq(gen(out), out, "`> a ` 二次往返稳定");

  // `>a`（无空格写法）追加空格：不得把前缀补成 `> `，也不得丢正文空格
  const doc2 = P.parse(">a");
  doc2.blocks[0].children[0].children.push(AST.text(" "));
  const out2 = G.generate(doc2);
  eq(out2, ">a ", "`>a` 追加空格 → `>a `（前缀 `>` 原样保留）");
  eq(gen(out2), out2, "`>a ` 二次往返稳定");
  eq(blocks(out2)[0].type, "blockquote", "`>a ` 仍是引用块");

  // `>> `（两级前缀）追加空格：前缀整段保留
  const doc3 = P.parse(">> x");
  const bq3 = doc3.blocks[0];
  bq3.children[0].children.push(AST.text(" "));
  const out3 = G.generate(doc3);
  eq(out3, ">> x ", "`>> x` 追加空格 → `>> x `");
  eq(gen(out3), out3, "`>> x ` 二次往返稳定");
  eq(quoteText(out3), "x ", "`>> x ` 正文 `x `（两级前缀不入正文）");
})();

// ── 3. 段内 `>` 空行：行区间必须覆盖它 ──────────────────────────────────
(function () {
  const src = "> a\n>\n> b";
  const bs = blocks(src);
  eq(bs.length, 1, "`> a\\n>\\n> b` 只有 1 个块（引用段内 `>` 空行不断段）");
  eq(bs[0].type, "blockquote", "该块是 blockquote");
  eq(bs[0].srcLine, 1, "引用块 srcLine = 1");
  eq(bs[0].srcLineEnd, 3, "引用块 srcLineEnd = 3（含 `>` 空行，供 spliceBlockSource 用）");
  eq(bs[0].children.length, 3, "引用段内 3 个段落");
  eq(G.generateBlock(bs[0]), src, "引用块整块回写逐字节一致");

  // 多行混排：引用块行区间不吞后面的段落
  const bs2 = blocks("> a\n>\n> b\nafter");
  eq(bs2.length, 2, "`> a\\n>\\n> b\\nafter` → 2 个块");
  eq(bs2[0].srcLineEnd, 3, "引用块结束行 = 3");
  eq(bs2[1].type, "paragraph", "after 是独立段落");
  eq(bs2[1].srcLine, 4, "after 起始行 = 4");
})();

// ── 4. 其它前缀不回归（键入路径同样走 lexer）──────────────────────────────
[
  ["# h", "heading"],
  ["- a", "list"],
  ["1. a", "list"],
  ["```js\nvar a=1;\n```", "code_block"],
  ["$$x$$", "math_block"],
  ["a > b", "paragraph"],
].forEach(function (c) {
  const t = blocks(c[0])[0].type;
  eq(t, c[1], "前缀不回归 " + JSON.stringify(c[0]) + " → " + c[1]);
});

// ── 5. 整篇往返（键入 + 混排）───────────────────────────────────────────
(function () {
  const doc = [
    "# 标题",
    "",
    ">",
    "> ",
    ">a",
    ">>",
    "> > x",
    "",
    "normal",
  ].join("\n");
  const once = gen(doc);
  eq(gen(once), once, "混排整篇二次往返稳定");
  // 引用块必须覆盖前 5 行（`>` / `> ` / `>a` / `>>` / `> > x` 连续）
  const bs = blocks(doc);
  const bq = bs.filter(function (b) {
    return b.type === "blockquote";
  })[0];
  eq(bq && bq.type, "blockquote", "混排 · 存在引用块");
  eq(bq && bq.srcLine, 3, "混排 · 引用块起始行 3");
  eq(bq && bq.srcLineEnd, 7, "混排 · 引用块结束行 7（`>` / `> ` / `>a` / `>>` / `> > x` 连续）");
  eq(bq && bq.children.length, 5, "混排 · 引用块 5 段");
})();

// ── 汇总 ────────────────────────────────────────────────────────────────
console.log("");
if (failures.length) {
  console.log("❌ FAIL " + failures.length + " / PASS " + pass);
  failures.forEach(function (f) {
    console.log("  - " + f);
  });
  process.exit(1);
}
console.log("✅ PASS " + pass + " 项（E28 键入序列 + 行区间）");
process.exit(0);
