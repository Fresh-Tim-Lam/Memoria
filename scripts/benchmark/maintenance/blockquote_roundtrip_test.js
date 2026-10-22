#!/usr/bin/env node
/* E28 单测：引用块 `>` 前缀的「语法空格 vs 内容空格」与 parse↔generate 往返幂等。
   用法：node scripts/benchmark/maintenance/blockquote_roundtrip_test.js
   背景（E28）：lexer 旧前缀正则 `^(\s*)(>\s?)` 把 `>` 后的第一个空格当语法空格吃掉，
   SourceGen 回写恒写 "> " ⇒ `>a` 被规范化、`>` / `>> ` 等写法回写漂移。
   断言分三层：
     L1 结构：`>a` / `>` / `>> ` 仍解析为 blockquote（容忍无空格写法）
     L2 字节：generate(parse(src)) === src（回写保留原有空白，含内容侧空格）
     L3 幂等：generate(parse(generate(parse(src)))) === 第一次输出（二次往返稳定）
   另含回归：列表/标题/代码块/数学块前缀不受影响；无 prefixes 的旧 AST 仍按 "> " 回写。 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const JS_DIR = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js");

// ── 在 Node 里加载浏览器全局脚本（ast → lexer → parser → source-gen）──
global.window = global;
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js"]) {
  const file = path.join(JS_DIR, f);
  vm.runInThisContext(fs.readFileSync(file, "utf8"), { filename: file });
}

const AST = global.MemoriaAST;
const L = global.MemoriaLexer;
const P = global.MemoriaParser;
const G = global.MemoriaSourceGen;

let failures = 0;
let passes = 0;
const failLines = [];
function check(name, cond, extra) {
  if (cond) { passes++; console.log("PASS  " + name); }
  else {
    failures++;
    const tail = extra !== undefined ? "  " + JSON.stringify(extra) : "";
    failLines.push("FAIL  " + name + tail);
    console.log("FAIL  " + name + tail);
  }
}
function j(v) { return JSON.stringify(v); }

// ── 往返工具 ──
function gen(src) { return G.generate(P.parse(src)); }
function roundtripPairs(src) {
  const g1 = gen(src);
  const g2 = gen(g1);
  return { g1, g2 };
}
function blockTypes(src) { return P.parse(src).blocks.map(b => b.type); }

// =========================================================================
// A. 结构：引用块识别（容忍 `>a` 无空格写法；`>` 空引用；多级 `>> `）
// =========================================================================
const STRUCT_CASES = [
  { name: "A1  `> `  空引用（单语法空格）", src: "> ", types: ["blockquote"] },
  { name: "A2  `>a`  无空格写法", src: ">a", types: ["blockquote"] },
  { name: "A3  `>`   裸标记", src: ">", types: ["blockquote"] },
  { name: "A4  `>> ` 两级嵌套", src: ">> ", types: ["blockquote"] },
  { name: "A5  `> a  b` 内容含双空格", src: "> a  b", types: ["blockquote"] },
  { name: "A6  `> > deep` 空格分隔嵌套", src: "> > deep", types: ["blockquote"] },
];
for (const c of STRUCT_CASES) {
  check(c.name + " 解析为引用块", j(blockTypes(c.src)) === j(c.types), blockTypes(c.src));
}

// A7 连续引用行合并为 1 个 blockquote（多行）
(function () {
  const src = "> a\n>b\n> c";
  const doc = P.parse(src);
  const bqs = doc.blocks.filter(b => b.type === "blockquote");
  check("A7  连续 3 行引用合并为 1 个 blockquote", bqs.length === 1 && bqs[0].children.length === 3,
    { bqCount: bqs.length, children: bqs[0] && bqs[0].children.length });
})();

// A8 `>` 行不吞掉后续普通段落（引用块边界正确）
(function () {
  const types = blockTypes("> q\nafter");
  check("A8  引用块后普通段落不被并入", j(types) === j(["blockquote", "paragraph"]), types);
})();

// =========================================================================
// B. 语法空格 vs 内容空格：前缀只消费**一个**空格，其余全部属于用户内容
// =========================================================================
function bqContent(src) {
  const doc = P.parse(src);
  const bq = doc.blocks.find(b => b.type === "blockquote");
  if (!bq || !bq.children[0]) return null;
  return bq.children[0].children.map(n => n.content).join("");
}
const CONTENT_CASES = [
  { name: "B1  `> a`   内容为 \"a\"", src: "> a", want: "a" },
  { name: "B2  `>  a`  内容保留 1 个前导空格", src: ">  a", want: " a" },
  { name: "B3  `>   a` 内容保留 2 个前导空格", src: ">   a", want: "  a" },
  { name: "B4  `> a  b` 中间双空格是内容", src: "> a  b", want: "a  b" },
  { name: "B5  `>a`    无语法空格，内容 \"a\"", src: ">a", want: "a" },
  { name: "B6  `> `    空内容", src: "> ", want: "" },
  { name: "B7  `>  `   内容为单个空格（第二个空格是内容）", src: ">  ", want: " " },
  // B8/B9：`>>` / `> >` 的**整段标记**（含内层 `>`）都算前缀，正文只取 `x`；
  //     外层仍是 1 层 blockquote（不递归渲染嵌套），前缀原文由 SourceGen 逐字节回写。
  { name: "B8  `>> x`  两级前缀后内容 \"x\"", src: ">> x", want: "x" },
  { name: "B9  `> > x` 空格分隔嵌套后内容 \"x\"", src: "> > x", want: "x" },
  { name: "B10 `>\\ta`  制表符作为语法空白", src: ">\ta", want: "a" },
];
for (const c of CONTENT_CASES) {
  check(c.name, bqContent(c.src) === c.want, { got: bqContent(c.src), want: c.want });
}

// B11：嵌套标记必须出现在解析结果里（不被吃掉），且 blockquote 外层只有 1 层
(function () {
  const doc = P.parse(">> x");
  const bqs = doc.blocks.filter(b => b.type === "blockquote");
  check("B11 `>> x` 只产生 1 层 blockquote 且内层标记保留",
    bqs.length === 1 && bqs[0].children.length === 1, { bqs: bqs.length });
})();

// =========================================================================
// C. 字节级往返：generate(parse(src)) === src（E28 核心）
// =========================================================================
const ROUNDTRIP_CASES = [
  "> ",
  ">",
  ">a",
  "> a",
  ">  a",
  ">> ",
  ">> x",
  "> > x",
  "> a  b",
  ">  ",
  ">\ta",
  "> a\n>b\n> c",
  "> a\n>\n> b",
  "> **bold** 与 *italic*",
  "para\n> quote\npara2",
  "> 多字节内容：中文 与 emoji 🚀",
];
for (const src of ROUNDTRIP_CASES) {
  const { g1 } = roundtripPairs(src);
  check("C  往返字节保留 " + j(src), g1 === src, { got: g1 });
}

// =========================================================================
// D. 幂等：二次往返稳定（parse→generate→parse→generate）
// =========================================================================
for (const src of ROUNDTRIP_CASES) {
  const { g1, g2 } = roundtripPairs(src);
  check("D  二次往返稳定 " + j(src), g2 === g1, { g1, g2 });
}

// D17 幂等还要求 AST 形状稳定（块数/块类型/引用前缀序列）
for (const src of ROUNDTRIP_CASES) {
  const d1 = P.parse(src);
  const d2 = P.parse(gen(src));
  const shape = d => d.blocks.map(b => b.type + ":" + (b.prefixes ? b.prefixes.join("|") : "-"));
  check("D  两次解析 AST 同形 " + j(src), j(shape(d1)) === j(shape(d2)), { a: shape(d1), b: shape(d2) });
}

// =========================================================================
// E. 回归：其它块前缀不受影响（避免 `>` 修复波及列表/标题/代码块/数学块）
// =========================================================================
const REGRESSION = [
  { name: "E1  标题 `# h`", src: "# h" },
  { name: "E2  无序列表 `- a`", src: "- a" },
  { name: "E3  有序列表 `1. a`", src: "1. a" },
  { name: "E4  代码块", src: "```js\nvar a = 1;\n```" },
  { name: "E5  数学块", src: "$$\nx^2\n$$" },
  { name: "E6  水平线", src: "---" },
  { name: "E7  表格", src: "| a | b |\n| --- | --- |\n| 1 | 2 |" },
  { name: "E8  段落含 > 非行首", src: "a > b" },
];
for (const c of REGRESSION) {
  const { g1, g2 } = roundtripPairs(c.src);
  check(c.name + " 往返稳定", g1 === g2, { g1, g2 });
}

// E9 列表项内含 `>` 不被当成引用前缀（前缀只在行首）
(function () {
  const types = blockTypes("- a > b");
  check("E9  列表项内 > 保持列表", j(types) === j(["list"]), types);
})();

// E10 代码块内的 `> ` 原样保留（不被引用化）
(function () {
  const src = "```\n> code\n```";
  const doc = P.parse(src);
  const cb = doc.blocks.find(b => b.type === "code_block");
  check("E10 代码块内 > 原样", !!cb && cb.code === "> code", cb && cb.code);
})();

// =========================================================================
// F. 向后兼容：外部（app.js）构造的 blockquote 无 prefixes 时仍按 "> " 回写
// =========================================================================
(function () {
  const bq = AST.blockquote([AST.paragraph([AST.text("hello")])]);
  check("F1  无 prefixes 的 AST 回写为 \"> hello\"", G.generateBlock(bq) === "> hello", G.generateBlock(bq));
})();

(function () {
  const bq = AST.blockquote([]);
  check("F2  空 blockquote 回写非空标记", G.generateBlock(bq) === "> ", G.generateBlock(bq));
})();

// F3 前缀数组与子块数量不一致时退回默认（防御外部构造）
(function () {
  const bq = AST.blockquote([AST.paragraph([AST.text("a")]), AST.paragraph([AST.text("b")])]);
  bq.prefixes = [">"];
  check("F3  prefixes 长度不匹配 ⇒ 回退默认前缀",
    G.generateBlock(bq) === "> a\n> b", G.generateBlock(bq));
})();

// =========================================================================
// 汇总
// =========================================================================
console.log("");
console.log("──────────────────────────────────────────────");
console.log("PASS " + passes + " / FAIL " + failures + " （共 " + (passes + failures) + " 项）");
if (failures) {
  console.log("失败清单：");
  for (const l of failLines) console.log("  " + l);
  process.exit(1);
}
console.log("E28 引用块往返幂等：全 PASS");
