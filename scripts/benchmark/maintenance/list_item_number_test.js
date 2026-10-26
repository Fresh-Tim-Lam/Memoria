#!/usr/bin/env node
/* task-156 Step3 单测：_listItemWithNumber（重建列表项时继承原手写序号）
 *
 * 覆盖 Lead 要求的边界：
 *   · 有序项带 number vs 无序/旧 AST（无 number）
 *   · 松散列表（合并成一个 list，多项 number 不连续：10,11,3,4）
 *   · 嵌套 list
 *   · 旧 AST（无 number）
 * 并做一次"重建后逐字节往返"集成断言（source-gen 逐项回写）。
 * 用法：node scripts/benchmark/maintenance/list_item_number_test.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..", "..");
const JS = path.join(ROOT, "src", "memoria", "ui", "static", "app", "js");
const APP = path.join(JS, "app.js");
const appSrc = fs.readFileSync(APP, "utf8");

global.window = global;
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js"]) {
  vm.runInThisContext(fs.readFileSync(path.join(JS, f), "utf8"), { filename: f });
}
const P = global.MemoriaParser;
const G = global.MemoriaSourceGen;
const A = global.MemoriaAST;

function extractFunction(name) {
  const head = "\n    function " + name + "(";
  const start = appSrc.indexOf(head);
  if (start < 0) throw new Error("function not found: " + name);
  let i = appSrc.indexOf("{", start + head.length - 1);
  let depth = 0, end = -1;
  for (let k = i; k < appSrc.length; k++) {
    if (appSrc[k] === "{") depth++;
    else if (appSrc[k] === "}") { depth--; if (depth === 0) { end = k + 1; break; } }
  }
  if (end < 0) throw new Error("function end not found: " + name);
  return appSrc.slice(start + 1, end);
}

const helperSrc = extractFunction("_listItemWithNumber");
const sandbox = { A: A };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(helperSrc, sandbox, { filename: "list-item-number.js" });
const mk = sandbox._listItemWithNumber;

let pass = 0;
const fails = [];
function ok(name, cond, extra) {
  if (cond) { pass++; return; }
  fails.push(name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  console.log("FAIL  " + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
}

// ── A. 有序项：继承 number；override 生效 ──
{
  const src = A.listItem([A.text("ten")], { number: 10 });
  const left = mk(src, [A.text("te")]);
  ok("A1 有序项继承 number=10", left.number === 10, left.number);
  const right = mk(src, [], 11);
  ok("A2 override=11 ⇒ number=11（拆出的右半）", right.number === 11, right.number);
  ok("A3 无序/无 number ⇒ 不写 number 字段", mk(A.listItem([A.text("a")]), [A.text("b")]).number === undefined);
  ok("A4 旧 AST（srcItem=null）无 override ⇒ 无 number", mk(null, [A.text("x")]).number === undefined);
  ok("A5 旧 AST + override ⇒ 设 number", mk(null, [], 3).number === 3);
  const withIndent = A.listItem([A.text("i")], { number: 5, indent: "  " });
  ok("A6 继承 indent", mk(withIndent, []).indent === "  ", mk(withIndent, []).indent);
}

// ── B. 松散列表（一个 list：number 10,11,3,4 不连续）：重建后乱序号也保真 ──
{
  const src = "10. ten\n11. eleven\n\n3. three\n4. four\n";
  const list = P.parse(src).blocks[0];
  ok("B1 松散列表被解析为同一个 list（4 项）", list.type === "list" && list.items.length === 4, list.items && list.items.length);
  list.items = list.items.map((it) => mk(it, it.children));
  ok("B2 逐项重建后逐字节往返", G.generateBlock(list) === src.trimEnd(), { gen: G.generateBlock(list) });
}

// ── C. 嵌套 list：各层分别继承各自 number ──
{
  const src = "5. five\n   6. six\n7. seven\n";
  const list = P.parse(src).blocks[0];
  const nested = list.items[0].list;
  ok("C1 解析出嵌套子列表", !!(nested && nested.items && nested.items.length === 1));
  list.items[0].children = list.items[0].children;
  if (nested) nested.items[0] = mk(nested.items[0], nested.items[0].children);
  list.items[1] = mk(list.items[1], list.items[1].children);
  ok("C2 嵌套 + 顶层重建后逐字节往返", G.generateBlock(list) === src.trimEnd(), { gen: G.generateBlock(list) });
}

// ── D. 混合：有序项 + 无序子项（无序不写 number）──
{
  const ordered = P.parse("10. ten\n11. eleven\n").blocks[0];
  const rebuilt = A.list(ordered.ordered, ordered.items.map((it) => mk(it, it.children)));
  ok("D1 有序列表逐项重建后往返保真", G.generateBlock(rebuilt) === "10. ten\n11. eleven", { gen: G.generateBlock(rebuilt) });
  const unordered = P.parse("- a\n- b\n").blocks[0];
  const rebuiltU = A.list(false, unordered.items.map((it) => mk(it, it.children)));
  ok("D2 无序列表重建后往返保真", G.generateBlock(rebuiltU) === "- a\n- b", { gen: G.generateBlock(rebuiltU) });
}

console.log("\n=== SUMMARY === PASS=" + pass + " FAIL=" + fails.length);
if (fails.length) { fails.forEach((f) => console.log("  - " + f)); process.exit(1); }
process.exit(0);
