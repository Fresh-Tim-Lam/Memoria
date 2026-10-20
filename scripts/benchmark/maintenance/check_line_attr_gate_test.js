#!/usr/bin/env node
/* P4 门禁自测：证明 `check_line_attr_gate.js` **会红也会绿**。
 *
 * 为什么需要这份自测：一个"永远 PASS"的门禁（正则写错、白名单过宽、把读当写）
 * 在干净仓上同样 exit 0 —— 只测"不误报"**不能**证明门禁有效。
 * 因此本文件同时覆盖三类断言：
 *   【红】真正的写入必须被抓住（setAttribute / 模板拼属性 / dataset 左值 / 转发写）
 *   【绿】真正的读取**不得**被误报（选择器 / dataset 读 / getAttribute 读 / 正则测试 / 注释）
 *   【归属】`block-index.js` 的白名单是"文件 + upsert() 函数体"双判定，不是只认文件名
 *
 * 做法：把构造的源码写成临时目录里的文件，用 `--root` 让门禁扫那个目录，
 * **拿真门禁脚本的真实退出码**判定（不 mock、不复制判定逻辑）。
 *
 * 用法：node scripts/benchmark/maintenance/check_line_attr_gate_test.js
 */
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const GATE = path.join(__dirname, "check_line_attr_gate.js");

let failures = 0;
function check(name, cond, extra) {
  console.log((cond ? "PASS" : "FAIL") + "  " + name + (extra ? "  " + JSON.stringify(extra) : ""));
  if (!cond) failures += 1;
}

/* ── 建临时扫描根 ───────────────────────────────────────────────────────── */

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lineattr-gate-"));

function mkdirp(p) {
  fs.mkdirSync(p, { recursive: true });
  return p;
}

/** 在临时根下写一组文件，返回 {dir, run()}。 */
function fixture(name, files) {
  const dir = mkdirp(path.join(tmpRoot, name));
  for (const [rel, content] of Object.entries(files)) {
    const p = path.join(dir, rel);
    mkdirp(path.dirname(p));
    fs.writeFileSync(p, content, "utf8");
  }
  return {
    dir,
    run() {
      try {
        const out = execFileSync(process.execPath, [GATE, "--root", dir, "--json"], {
          encoding: "utf8",
          stdio: ["ignore", "pipe", "pipe"],
        });
        return { code: 0, json: JSON.parse(out) };
      } catch (e) {
        // 非零退出时 stdout 里仍有 JSON
        const out = (e.stdout || "").toString();
        let json = null;
        try {
          json = JSON.parse(out);
        } catch (_) {
          json = null;
        }
        return { code: e.status == null ? -1 : e.status, json };
      }
    },
  };
}

/* ── 【红】真正的写入必须被抓住 ─────────────────────────────────────────── */

console.log("── 【红】必须 FAIL 的反例 ──");

const R1 = fixture("red-setattribute", {
  "app.js": 'function stamp(el, n) {\n  el.setAttribute("data--src-line", n);\n}\n',
});
let r = R1.run();
check("R1 裸 setAttribute ⇒ exit 1", r.code === 1, { exit: r.code });
check("R1 报出 1 处违规", r.json && r.json.violationCount === 1, r.json && r.json.violationCount);
check("R1 定位到 app.js:2", r.json && r.json.violations[0].file.endsWith("app.js") && r.json.violations[0].line === 2,
  r.json && r.json.violations[0]);

const R2 = fixture("red-src-line-end", {
  "app.js": 'function stamp(el, a, b) {\n  el.setAttribute("data--src-line-end", b);\n}\n',
});
r = R2.run();
check("R2 data--src-line-end 也算（不是只守不带后缀的那个）⇒ exit 1", r.code === 1, { exit: r.code });

const R3 = fixture("red-template", {
  "render.js": 'function block(b) {\n  return `<p data--src-line="${b.s}">x</p>`;\n}\n',
});
r = R3.run();
check("R3 模板串拼属性（绕过 setAttribute 的写法）⇒ exit 1", r.code === 1, { exit: r.code });
check("R3 归类为 template", r.json && r.json.violations[0] && r.json.violations[0].kind === "template",
  r.json && r.json.violations[0] && r.json.violations[0].kind);

const R4 = fixture("red-dataset-write", {
  "app.js": 'function stamp(el, n) {\n  el.dataset.SrcLine = n;\n}\n',
});
r = R4.run();
check("R4 dataset 左值赋值 ⇒ exit 1", r.code === 1, { exit: r.code });

const R5 = fixture("red-forward", {
  "markdown-preview.js":
    'function swap(pre, div) {\n' +
    '  ["data--block-index", "data--src-line", "data--src-line-end"].forEach((k) => {\n' +
    "    const v = pre.getAttribute(k);\n" +
    "    if (v) div.setAttribute(k, v);\n" +
    "  });\n" +
    "}\n",
});
r = R5.run();
check("R5 转发写 setAttribute(k, getAttribute(k)) ⇒ exit 1", r.code === 1, { exit: r.code });
check("R5 归类为 forward-write（不是静默放过）",
  r.json && r.json.violations.some((v) => v.rule === "forward-write"),
  r.json && r.json.violations.map((v) => v.rule));

// 【归属】白名单文件里、但不在 upsert() 内 ⇒ 仍然红
const R6 = fixture("red-wrong-function", {
  "block-index.js":
    "function other(el, n) {\n" +
    '  el.setAttribute("data--src-line", n);\n' +
    "}\n" +
    "function upsert(h) {\n" +
    "  return h;\n" +
    "}\n",
});
r = R6.run();
check("R6 block-index.js 内但在 other() 里写 ⇒ exit 1（文件白名单不等于放行）", r.code === 1, { exit: r.code });
check("R6 归类为 wrong-function",
  r.json && r.json.violations.some((v) => v.rule === "wrong-function"),
  r.json && r.json.violations.map((v) => v.rule));

/* ── 【绿】真正的读取不得误报 ───────────────────────────────────────────── */

console.log("");
console.log("── 【绿】必须 PASS 的正例（读 ≠ 写）──");

const G1 = fixture("green-empty", { "app.js": "function noop() { return 1; }\n" });
r = G1.run();
check("G1 完全无关的代码 ⇒ exit 0", r.code === 0, { exit: r.code });

const G2 = fixture("green-reads", {
  "app.js":
    "function reads(block, els) {\n" +
    "  const a = +(block.dataset.SrcLine || 0);\n" +          // dataset 读
    "  const b = +(block.dataset.SrcLineEnd || a);\n" +       // dataset 读
    "  const c = Number(block.getAttribute('data--src-line')) || 0;\n" + // getAttribute 读
    "  const sel = document.querySelector('.-src-block[data--src-line=\"5\"]');\n" + // 选择器
    "  const hit = els.filter((el) => el.closest('[data--src-line]'));\n" + // closest
    "  return [a, b, c, sel, hit];\n" +
    "}\n",
});
r = G2.run();
check("G2 dataset 读 / getAttribute 读 / 选择器 / closest ⇒ exit 0（不误报）", r.code === 0,
  { exit: r.code, violations: r.json && r.json.violations });

const G3 = fixture("green-regex-test", {
  "render.js":
    "function attach(html, lineAttrs, rest) {\n" +
    "  if (!/data--src-line=/.test(rest)) {\n" +
    "    rest += ' ' + lineAttrs;\n" +
    "  }\n" +
    "  return html;\n" +
    "}\n",
});
r = G3.run();
check("G3 正则字面量 `if (!/data--src-line=/.test(rest))` ⇒ exit 0", r.code === 0, { exit: r.code });

const G4 = fixture("green-comments", {
  "app.js":
    "// 这里讨论 data--src-line 与 data--src-line-end 的语义（注释不是代码）\n" +
    "/* 也不要因为 /* 注释 */ 里的 data--src-line 判红 */\n" +
    "function noop() {}\n",
});
r = G4.run();
check("G4 注释里提到属性名 ⇒ exit 0（注释抹除生效）", r.code === 0, { exit: r.code });

// 【归属】白名单文件 + upsert() 函数体内 ⇒ 这才是唯一合法写点
const G5 = fixture("green-allowed", {
  "block-index.js":
    "function upsert(handle) {\n" +
    "  const el = handle.el;\n" +
    "  if (el) {\n" +
    '    el.setAttribute("data--src-line", handle.srcStart + 1);\n' +
    '    el.setAttribute("data--src-line-end", handle.srcEnd);\n' +
    "  }\n" +
    "}\n",
});
r = G5.run();
check("G5 唯一合法写点（block-index.js 的 upsert 内）⇒ exit 0", r.code === 0,
  { exit: r.code, violations: r.json && r.json.violations });
check("G5 该 2 处被记为 allowed（而非漏扫）", r.json && r.json.allowedCount === 2,
  r.json && r.json.allowedCount);

/* ── 【混合】一个目录里同时有合法与违规 ⇒ 只报违规 ─────────────────────── */

console.log("");
console.log("── 【混合】同时存在合法与违规 ⇒ 仅报违规 ──");

const M1 = fixture("mixed", {
  "block-index.js":
    "function upsert(h) {\n" + '  h.el.setAttribute("data--src-line", h.srcStart + 1);\n' + "}\n",
  "app.js": "function stamp(el, n) {\n" + '  el.setAttribute("data--src-line", n);\n' + "}\n",
});
r = M1.run();
check("M1 exit 1", r.code === 1, { exit: r.code });
check("M1 只报 app.js 那 1 处（白名单内的不报）",
  r.json && r.json.violationCount === 1 && r.json.violations[0].file.endsWith("app.js"),
  r.json && r.json.violations);

/* ── 【自证】门禁在真实仓库上当前应为红（基线 > 0） ────────────────────── */

console.log("");
console.log("── 【基线】真实仓库当前状态 ──");

let realRun = null;
try {
  realRun = execFileSync(process.execPath, [GATE, "--json"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
} catch (e) {
  realRun = (e.stdout || "").toString();
}
let realJson = null;
try {
  realJson = JSON.parse(realRun);
} catch (_) {
  realJson = null;
}
check("真实仓库扫描有结果（json 可解析）", !!realJson);
if (realJson) {
  console.log("     基线违规处数 = " + realJson.violationCount + "（P2/P3 完成后须归零，届时本断言改判为 exit 0）");
  check("真实仓库当前确有违规（改造前，证明门禁不是空转）", realJson.violationCount > 0,
    { violationCount: realJson.violationCount });
}

/* ── 收尾 ───────────────────────────────────────────────────────────────── */

try {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
} catch (_) {
  /* 临时目录清不掉不影响判定 */
}

console.log("");
console.log(failures ? "RESULT  FAIL  " + failures + " 条断言失败" : "RESULT  PASS  全部断言通过");
process.exit(failures ? 1 : 0);
