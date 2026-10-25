#!/usr/bin/env node
/* task-147（R0 数据损坏）：`collectEditorBody()` 的尾换行保真 —— **白盒单测**（不依赖浏览器）
 *
 * 手法沿用 `scripts/benchmark/maintenance/edit_cut_undo_test.js`：
 *   从 `app.js` **按花括号配平抽取真实源码**（不是复制逻辑副本）+ `node:vm` + 最小 DOM 桩。
 *
 * 被测的真实函数（全部来自磁盘上的 app.js）：
 *   `_docEndsWithNL()` / `_restoreDocTailNL()` / `collectEditorBody()`
 *
 * 判据（硬性纪律，见 task-147 与 doc-body-staleness-analysis.md §10）：
 *   ① **逐字节比对**（Buffer.equals），不是长度、不是行数、不是计数；
 *   ② "编辑生效"用**内容不等式/包含**证明，不用长度；
 *   ③ 失败时打印首个差异字节下标 + 前后文，避免"只看到一个数字不等"。
 *
 * 矩阵：尾形态 ×4（无 / `\n` / `\n\n` / `\n\n\n`）× 编辑 ×3（插入 / 删除 / 拆行）= 12 组合。
 * 改前预期（红矩阵）：
 *   · 尾 `\n\n`、`\n\n\n` 的 6 组合 **FAIL**（各少 1 个尾换行）
 *   · 尾 无 / `\n` 的 6 组合 **PASS**（证明只有"≥2 换行"边界坏，不是全坏）
 *   · 其中"插入"在 ≥2 换行时会**长度相等但字节不同** ⇒ 专列 `netLenEqualButBytesDiffer`，
 *     这就是"净长度巧合"的现场证据：任何长度判据都会放过它，逐字节判据能抓住。
 *
 * 用法：node scripts/benchmark/maintenance/tail_newline_roundtrip_test.js
 * 退出码：0 = 全 PASS；1 = 有 FAIL（改前跑应得 1）。
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP_JS = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "app.js");
const SRC = fs.readFileSync(APP_JS, "utf8");

// ── 0. 统计记录 ───────────────────────────────────────────────────────────────
let passes = 0;
const failures = [];
const rows = []; // 矩阵行（给报告用）

function ok(name, cond, extra) {
  if (cond) { passes++; return true; }
  failures.push(name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  console.log("FAIL  " + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  return false;
}
function pass(name) { passes++; console.log("PASS  " + name); }

// ── 1. 抽取真实源码（花括号配平；比 "\n  }\n" 稳）────────────────────────────
function extractFunction(name) {
  const head = "\n  function " + name + "(";
  const start = SRC.indexOf(head);
  if (start < 0) throw new Error("未在 app.js 找到函数: " + name);
  const braceStart = SRC.indexOf("{", start);
  if (braceStart < 0) throw new Error("函数无函数体: " + name);
  let depth = 0;
  for (let i = braceStart; i < SRC.length; i++) {
    const c = SRC[i];
    if (c === "{") depth++;
    else if (c === "}") { depth--; if (depth === 0) return SRC.slice(start + 1, i + 1); }
  }
  throw new Error("函数花括号不平衡: " + name);
}

const fDocEndsWithNL = extractFunction("_docEndsWithNL");
const fRestoreTail = extractFunction("_restoreDocTailNL");
const fCollect = extractFunction("collectEditorBody");

pass("抽取 _docEndsWithNL 真实源码");
pass("抽取 _restoreDocTailNL 真实源码");
pass("抽取 collectEditorBody 真实源码");
ok("被测函数确实是 app.js 里使用 DOM 的那一版（含 .-line-content 选择器）",
  fCollect.indexOf('.-line-content') >= 0);
ok("被测函数确实调用了尾换行回补（防止抽错版本）",
  fCollect.indexOf("_restoreDocTailNL") >= 0);

// ── 2. 最小 DOM 桩：把 canonical body 的 splitlines 结果渲染成"编辑器行" ──────
/** Python `str.splitlines()` 的 LF 等价（无其它行终止符）：末尾 `\n` 不产生最后一项。
 *  canonical body 由后端 `load_document` 给出（CRLF 已归一为 LF）。 */
function splitlines(s) {
  const parts = s.split("\n");
  if (s.length && s.endsWith("\n")) parts.pop();
  return parts.length ? parts : [""]; // 后端: `body.splitlines() or [""]`
}
/** 与 splitlines 的逆运算：lines + 真源"是否有尾换行" ⇒ canonical body */
function bodyFromLines(lines, tailNL) {
  return lines.join("\n") + (tailNL ? "\n" : "");
}

let domLines = []; // 当前"编辑器 DOM"的逻辑行；用户编辑作用于此
function fakeLineEl(text) {
  return {
    textContent: text,
    querySelector: function () { return null; },              // 无 .-sync-cursor
    cloneNode: function () { return { textContent: text, querySelectorAll: function () { return []; } }; },
  };
}
const fakeEditor = {
  querySelectorAll: function (sel) {
    return sel === ".-line-content" ? domLines.map(fakeLineEl) : [];
  },
};

const sandbox = {};
sandbox.globalThis = sandbox;
sandbox.console = console;
sandbox.state = { doc: null };
sandbox.syncLog = function () { }; // 真实 app.js 里是日志函数
sandbox.$ = function (sel) { return sel === "#editor" ? fakeEditor : null; };
vm.createContext(sandbox);
vm.runInContext(
  fDocEndsWithNL + "\n" + fRestoreTail + "\n" + fCollect +
  "\nthis.__collectEditorBody = collectEditorBody;" +
  "\nthis.__docEndsWithNL = _docEndsWithNL;",
  sandbox,
  { filename: APP_JS + "#task147-extracted" }
);
const collectEditorBody = sandbox.__collectEditorBody;
ok("vm 内成功实例化 collectEditorBody", typeof collectEditorBody === "function");

// ── 3. 逐字节比对工具 ─────────────────────────────────────────────────────────
function byteDiff(got, exp) {
  const a = Buffer.from(got, "utf8");
  const b = Buffer.from(exp, "utf8");
  if (a.equals(b)) return null;
  const n = Math.min(a.length, b.length);
  let i = 0;
  while (i < n && a[i] === b[i]) i++;
  return {
    firstDiffByte: i,
    gotBytes: a.length,
    expBytes: b.length,
    gotTail: JSON.stringify(got.slice(Math.max(0, got.length - 8))),
    expTail: JSON.stringify(exp.slice(Math.max(0, exp.length - 8))),
    gotHex: a.slice(Math.max(0, i - 3), i + 3).toString("hex"),
    expHex: b.slice(Math.max(0, i - 3), i + 3).toString("hex"),
  };
}
function tailRepr(s) {
  return JSON.stringify(s.length > 8 ? s.slice(-8) : s);
}

// ── 4. 编辑操作：只作用在"逻辑行"上（模拟用户在编辑器 DOM 里打字）──────────────
const OPS = {
  /** 插入：在第 1 行末尾追加哨兵 `Z`（内容级证据，不用长度） */
  insert: function (lines) {
    lines[0] = lines[0] + "Z";
    return { marker: "Z", desc: "line1 + 'Z'" };
  },
  /** 删除：删掉第 1 行最后一个字符 */
  delete: function (lines) {
    if ((lines[0] || "").length < 2) throw new Error("用例前提：第一行至少 2 字符");
    lines[0] = lines[0].slice(0, -1);
    return { marker: null, desc: "line1 - last char" };
  },
  /** 拆行：把第 1 行拆成两行（新增一个 `\n`） */
  split: function (lines) {
    const l = lines[0] || "";
    if (l.length < 6) throw new Error("用例前提：第一行至少 6 字符");
    lines.splice(0, 1, l.slice(0, 5), l.slice(5));
    return { marker: null, desc: "line1 split at col 5" };
  },
};

// ── 5. 矩阵：尾形态 × 编辑 ───────────────────────────────────────────────────
const TAILS = [
  { key: "none", label: "尾=无", tail: "" },
  { key: "single", label: "尾=\\n（1 个换行）", tail: "\n" },
  { key: "blank", label: "尾=\\n\\n（空行结尾）", tail: "\n\n" },
  { key: "blank2", label: "尾=\\n\\n\\n（两个空行）", tail: "\n\n\n" },
];
const BASE_LINES = ["# tail 用例标题", "第二行正文 abcdef", "第三行正文 123456"];

console.log("\n=== 矩阵：尾形态 × 编辑（逐字节比对；长度只作诊断输出，绝不参与判据）===\n");
console.log(
  "CASE".padEnd(40) + "RESULT  " + "gotBytes/expBytes".padEnd(22) + "netLenEqualButBytesDiffer"
);
console.log("-".repeat(118));

for (const t of TAILS) {
  for (const opKey of Object.keys(OPS)) {
    const label = t.label + "  ×  " + opKey;
    // canonical：后端 load_document 的 body（LF 归一）——**尾形态必须原样来自 t.tail**。
    // ⚠️ 曾经的夹具错误：这里用 `bodyFromLines(lines, tailNL)` 只会补 **1 个** `\n`，
    //    于是 `\n\n` / `\n\n\n` 两个用例被悄悄退化成 `\n` ⇒ 12 组合全绿（测试自己变成假绿）。
    //    修法：canonical 直接 = 基础行 + 该形态的**字面尾部**；`tailNL` 只用于"是否有尾换行"。
    const canonical = BASE_LINES.join("\n") + t.tail;
    const tailNL = canonical.endsWith("\n");

    // 期望：同一个编辑作用在 canonical 的逻辑行上（编辑不触碰尾部形态）
    const expLines = splitlines(canonical).slice();
    const opMeta = OPS[opKey](expLines);
    const expected = bodyFromLines(expLines, tailNL);

    // 模拟：编辑器 DOM 里就是 canonical 的 splitlines 结果，然后用户编辑
    domLines = splitlines(canonical).slice();
    OPS[opKey](domLines);
    sandbox.state.doc = { body: canonical }; // 真源（flag 从这里首次判定并被缓存）

    // 编辑生效（内容级证据，不用长度）
    const editTookEffect = expected !== canonical &&
      (opMeta.marker === null ? true : expected.indexOf(opMeta.marker) >= 0);

    const got = collectEditorBody();
    const diff = byteDiff(got, expected);
    // "净长度巧合"判定：拿 **编辑前 canonical 的长度** 与 got 比（正是 task-141 探针的错判据）。
    //   插入 +1 与"丢 1 个尾换行" −1 抵消 ⇒ 长度看起来"没变"，但字节不同。
    const netLenEqualButBytesDiffer =
      (Buffer.byteLength(got, "utf8") === Buffer.byteLength(canonical, "utf8")) && !!diff;

    rows.push({
      tail: t.key,
      op: opKey,
      canonicalBytes: Buffer.byteLength(canonical, "utf8"),
      gotBytes: Buffer.byteLength(got, "utf8"),
      expBytes: Buffer.byteLength(expected, "utf8"),
      netLenEqualButBytesDiffer,
      pass: !diff && editTookEffect,
      diff,
    });

    const result = (!diff && editTookEffect) ? "PASS  " : "FAIL  ";
    console.log(
      label.padEnd(40) + result + " " +
      String(Buffer.byteLength(got, "utf8") + "/" + Buffer.byteLength(expected, "utf8")).padEnd(22) +
      String(netLenEqualButBytesDiffer)
    );
    if (diff) {
      console.log("        ↳ 首个差异字节#" + diff.firstDiffByte +
        "  got(" + diff.gotBytes + ")=" + diff.gotTail + "  exp(" + diff.expBytes + ")=" + diff.expTail +
        "  hex got[" + diff.gotHex + "] exp[" + diff.expHex + "]");
    }
    if (!editTookEffect) console.log("        ↳ 编辑没有改变 canonical（用例前提失败，不得视为通过）");

    ok(label + " ⇒ 逐字节相等", !diff, diff || undefined);
    ok(label + " ⇒ 编辑确实生效（内容级）", editTookEffect);
  }
}

// ── 6. 汇总 ─────────────────────────────────────────────────────────────────
const tailBad = rows.filter((r) => !r.pass);
console.log("\n=== 汇总 ===");
console.log("总组合:", rows.length, " PASS:", rows.length - tailBad.length, " FAIL:", tailBad.length);
for (const r of rows) {
  if (!r.pass) console.log("  FAIL " + r.tail + " × " + r.op +
    "  gotBytes=" + r.gotBytes + " expBytes=" + r.expBytes +
    (r.netLenEqualButBytesDiffer ? "  【长度相等但字节不同 = 净长度巧合】" : ""));
}
const netLenCases = rows.filter((r) => r.netLenEqualButBytesDiffer).map((r) => r.tail + "×" + r.op);
console.log("净长度巧合用例（长度判据会放过、字节判据抓住）:", netLenCases.length ? netLenCases.join(", ") : "（无）");
console.log("\nPASS =", passes, "  FAIL =", failures.length);
if (failures.length) {
  console.log("\n失败明细：");
  failures.forEach(function (f) { console.log("  - " + f); });
  process.exit(1);
}
process.exit(0);
