#!/usr/bin/env node
/* P4 门禁：`data--src-line` / `data--src-line-end` 的**写入门禁**。
 *
 * 背景（裁决出处）：
 *   docs/design/block-identity-design.md §7 R3 —— `data--src-line(-end)` 保留，但**定性为派生投影**：
 *     ① 唯一真源 = BlockIndex；
 *     ② **只允许经 `block-index.js` 的 `upsert()` 写**，禁止任何其它写入点；
 *     ③ 加门禁校验（就是本脚本）。
 *   docs/design/block-identity-build-plan.md P4 —— 「文件白名单 + 函数体归属双判定」。
 *
 * 判定规则（三条同时成立才算 PASS）：
 *   1. 命中点在允许清单文件里（初始仅 `block-index.js`）；
 *   2. 且该命中点位于 `BlockIndex` 的 `upsert()` 函数体内；
 *   3. 且该命中点不是"从别处读出来再抄过去"的转发写（v2 规则，见下）。
 *   其余一律 FAIL（宁可红，不可静默绿）。
 *
 * 为什么需要第 3 条：`div.setAttribute(k, pre.getAttribute(k))`（k 来自含 `data--src-line` 的
 * 常量数组）在语义上**也是**一次写入——它复制了另一个节点上的行号，等于"第二处事实来源"。
 * 只按文件白名单判会把这种写法静默放过。若某处确属合法，须写进 ALLOWED_FORWARD 并写明理由。
 *
 * 用法：
 *   node scripts/benchmark/maintenance/check_line_attr_gate.js            # 人类可读，exit 0/1
 *   node scripts/benchmark/maintenance/check_line_attr_gate.js --json     # 机器可读
 *   node scripts/benchmark/maintenance/check_line_attr_gate.js --root <dir>   # 指定扫描根（自测用）
 *   node scripts/benchmark/maintenance/check_line_attr_gate.js --list     # 仅列出允许清单
 * 退出码：0 = 干净；1 = 有违规（或扫描根不存在等用法错误）。
 */
"use strict";

const fs = require("fs");
const path = require("path");

/* ── 配置 ───────────────────────────────────────────────────────────────── */

/** 被守护的属性名（写成字符串常量，本文件自身因此不会被误判——见 IGNORE_FILES）。 */
const GUARDED = ["data--src-line", "data--src-line-end"];

/** 允许清单：唯一合法的写入者。 */
const ALLOWED_FILE = "block-index.js";
const ALLOWED_FN = "upsert";

/** 显式登记的"转发写"豁免（初始为空）。增补必须写理由，并在此处留痕。 */
const ALLOWED_FORWARD = [
  // { file: "markdown-preview.js", line: 227, reason: "……" },
];

/** 不参与扫描的文件（门禁自身需要写属性名字面量）。 */
const IGNORE_FILES = new Set(["check_line_attr_gate.js", "check_line_attr_gate_test.js"]);

const DEFAULT_ROOT = path.join(
  __dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js"
);

/* ── 源文本 → 行号 ───────────────────────────────────────────────────────── */

function lineIndex(src) {
  const starts = [0];
  for (let i = 0; i < src.length; i++) if (src.charCodeAt(i) === 10) starts.push(i + 1);
  return (offset) => {
    let lo = 0;
    let hi = starts.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (starts[mid] <= offset) lo = mid;
      else hi = mid - 1;
    }
    return lo + 1; // 1-based
  };
}

/* ── 函数体定位：找到含某偏移的最内层 function 及其名字 ───────────────────── */

/** 从 `offset` 向后找与 `openPos` 处 `{` 配平的 `}`（跳过字符串/注释/模板串）。 */
function matchBrace(src, openPos) {
  let depth = 0;
  for (let i = openPos; i < src.length; i++) {
    const c = src[i];
    if (c === '"' || c === "'" || c === "`") {
      const q = c;
      i++;
      while (i < src.length && src[i] !== q) {
        if (src[i] === "\\") i++;
        i++;
      }
      continue;
    }
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i++;
      i++;
      continue;
    }
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * 找出所有 `function NAME(...) { ... }` 与 `NAME(...) { ... }`（方法简写）以及箭头 `NAME = (...) => {`。
 * 返回 [{name, start, end}]（start/end 为花括号内区间）。
 *
 * ⚠️ 必须排除关键字控制块（if/for/while/switch/catch…）：否则 `if (el) { … }` 会被
 *    识别成一个叫 "if" 的"函数体"，把 upsert() 内的合法写入判成 wrong-function。
 */
const KEYWORDS = new Set([
  "if", "for", "while", "switch", "catch", "do", "else", "try", "finally", "with",
  "return", "function", "typeof", "new", "delete", "void", "in", "of", "instanceof",
]);

function functionBodies(src) {
  const out = [];
  const patterns = [
    /(?:^|[^.\w$])(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/g,
    /(?:^|[^.\w$])(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/g,
    /(?:^|[^.\w$])(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\s*)?\([^)]*\)\s*=>\s*\{/g,
    /(?:^|[^.\w$])([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?function\s*\([^)]*\)\s*\{/g,
  ];
  for (const re of patterns) {
    let m;
    while ((m = re.exec(src))) {
      const name = m[1];
      if (KEYWORDS.has(name)) continue; // 控制块不是函数
      const openPos = src.indexOf("{", m.index + m[0].length - 1);
      if (openPos < 0) continue;
      const closePos = matchBrace(src, openPos);
      if (closePos < 0) continue;
      out.push({ name, start: openPos, end: closePos });
    }
  }
  return out;
}

/** 含该偏移的最内层函数名（找不到 ⇒ null）。 */
function enclosingFunction(bodies, offset) {
  let best = null;
  for (const b of bodies) {
    if (offset > b.start && offset < b.end) {
      if (!best || b.end - b.start < best.end - best.start) best = b;
    }
  }
  return best ? best.name : null;
}

/* ── 写入点识别（4 类形式） ─────────────────────────────────────────────── */

/**
 * 在注释里提到属性名不算写入 ⇒ 先把注释区间抹成空格（保留长度，行号不变）。
 * 字符串字面量**不抹**：模板串里拼 HTML 属性是真实写入形式。
 */
function blankComments(src) {
  const chars = src.split("");
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === '"' || c === "'" || c === "`") {
      const q = c;
      i++;
      while (i < src.length && src[i] !== q) {
        if (src[i] === "\\") i++;
        i++;
      }
      i++;
      continue;
    }
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") {
        chars[i] = " ";
        i++;
      }
      continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      chars[i] = " ";
      chars[i + 1] = " ";
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) {
        if (src[i] !== "\n") chars[i] = " ";
        i++;
      }
      if (i < src.length) {
        chars[i] = " ";
        chars[i + 1] = " ";
        i += 2;
      }
      continue;
    }
    i++;
  }
  return chars.join("");
}

/** 属性名在源码中的转义变体（`data--src-line` 也可能写成字符串常量）。 */
const NAME_RE = /data--src-line(?![-\w])|data--src-line-end/g;

/**
 * 扫描一份源码，返回所有写入点：
 *   [{ line, col, kind, detail }]
 * kind ∈ setAttribute | template | dataset | forward | constArray
 */
function findWrites(src) {
  const clean = blankComments(src);
  const at = lineIndex(src);
  const writes = [];
  const seen = new Set();

  const push = (offset, kind, detail) => {
    const line = at(offset);
    const key = line + "|" + kind + "|" + detail;
    if (seen.has(key)) return;
    seen.add(key);
    writes.push({ line, col: offset - (src.lastIndexOf("\n", offset - 1) + 1) + 1, offset, kind, detail });
  };

  // (1) setAttribute("data--src-line"…) / setAttribute(k, v) 其中 k 可能来自常量数组
  const setAttrRe = /\.(?:setAttribute|setAttributeNS)\s*\(/g;
  let m;
  while ((m = setAttrRe.exec(clean))) {
    // 取括号内参数文本（粗略：到匹配的 ) ）
    const open = clean.indexOf("(", m.index);
    let depth = 0;
    let end = -1;
    for (let i = open; i < clean.length; i++) {
      if (clean[i] === "(") depth++;
      else if (clean[i] === ")") {
        depth--;
        if (depth === 0) {
          end = i;
          break;
        }
      }
    }
    const args = end > 0 ? clean.slice(open + 1, end) : "";
    if (NAME_RE.test(args)) {
      NAME_RE.lastIndex = 0;
      push(m.index, "setAttribute", "setAttribute(…data--src-line…)");
    } else {
      NAME_RE.lastIndex = 0;
      // 转发写（两种形态，都等于"把另一个节点上的行号抄过来"）：
      //   a) setAttribute(k, pre.getAttribute(k))      —— 参数里直接出现 getAttribute / dataset
      //   b) setAttribute(k, v) 且 k、v 来自属性名常量数组 —— 值在别处 getAttribute 取得
      const looksForwardArgs = /getAttribute\s*\(|\.dataset\b/.test(args);
      const looksForwardLoop = /forEach\s*\(\s*\(?\s*k\b/.test(clean.slice(Math.max(0, m.index - 220), m.index));
      if (looksForwardArgs || looksForwardLoop) {
        push(m.index, "forward", "setAttribute(k, v) 转发形态（需登记豁免）");
      }
    }
  }
  NAME_RE.lastIndex = 0;

  // (2) 模板串/字符串里直接拼属性：data--src-line="…
  //     ⚠️ 必须排除"读"的两种常见形态，否则会误判：
  //       a) 选择器：querySelector('.-src-block[data--src-line="N"]')
  //       b) 正则测试：if (!/data--src-line=/.test(rest))
  const tplRe = /data--src-line(?:-end)?\s*=/g;
  while ((m = tplRe.exec(clean))) {
    const before = clean.slice(Math.max(0, m.index - 60), m.index);
    // a) 位于选择器字符串内（同一行内前面有 querySelector/querySelectorAll/matches/closest）
    const lineStart = clean.lastIndexOf("\n", m.index) + 1;
    const linePrefix = clean.slice(lineStart, m.index);
    const inSelector = /\b(?:querySelector|querySelectorAll|matches|closest|getElementById)\s*\([^)]*$/.test(linePrefix);
    // b) 位于正则字面量 `/…/` 内（前后各有一个未转义斜杠夹住）
    const inRegex = /\/[^/\n]*$/.test(before) && /^\s*(?:-end)?\s*[^/]*\//.test(clean.slice(m.index, m.index + 80));
    if (inSelector || inRegex) continue;
    push(m.index, "template", 'HTML 模板里拼 data--src-line="…"');
  }

  // (3) dataset 形式**写入**：必须出现在赋值左侧
  //     `el.dataset.SrcLine = 5` / `el.dataset["SrcLine"] = 5` / `dataset.--srcLine`
  //     ⚠️ 只认"左值"。`+(el.dataset.SrcLine || 0)` 这类是**读**，绝不能判红。
  const dsRe =
    /\.dataset\s*(?:\.\s*(?:SrcLine|SrcLineEnd|--srcLine|--srcLineEnd)\b|\[\s*["'`](?:SrcLine|SrcLineEnd|--src-line(?:-end)?)["'`]\s*\])\s*=(?![=>])/g;
  while ((m = dsRe.exec(clean))) push(m.index, "dataset", "dataset 左值赋值（写入）");

  // (4) 常量数组：["data--block-index", "data--src-line", …] —— 本身不写，但常是转发写的引信；
  //     单独记账，便于人工判断（不计入"裸写"违规，由 forward 规则兜）。
  const arrRe = /\[\s*["'`]data--block-index["'`]\s*,[^\[\]]*["'`]data--src-line/gi;
  while ((m = arrRe.exec(clean))) push(m.index, "constArray", "属性名常量数组（转发写引信）");

  return writes;
}

/* ── 主扫描 ─────────────────────────────────────────────────────────────── */

function walkJs(root) {
  const out = [];
  if (!fs.existsSync(root)) return out;
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) stack.push(p);
      else if (ent.isFile() && ent.name.endsWith(".js")) out.push(p);
    }
  }
  out.sort();
  return out;
}

function scan(root) {
  const files = walkJs(root);
  const violations = [];
  const allowed = [];
  const scanned = [];

  for (const file of files) {
    const base = path.basename(file);
    scanned.push(file);
    if (IGNORE_FILES.has(base)) continue;

    const src = fs.readFileSync(file, "utf8");
    const writes = findWrites(src);
    if (!writes.length) continue;

    const bodies = functionBodies(src);

    for (const w of writes) {
      const rel = path.relative(path.join(__dirname, "..", "..", ".."), file).replace(/\\/g, "/");

      // constArray 只是引信，不单独判红
      if (w.kind === "constArray") {
        allowed.push({ file: rel, line: w.line, kind: w.kind, note: "引信：不构成写入" });
        continue;
      }

      // forward 形态：显式豁免则放行
      if (w.kind === "forward") {
        const hit = ALLOWED_FORWARD.find((a) => base === a.file && Math.abs(a.line - w.line) <= 2);
        if (hit) {
          allowed.push({ file: rel, line: w.line, kind: w.kind, note: "已登记豁免：" + hit.reason });
          continue;
        }
        violations.push({ ...w, file: rel, rule: "forward-write" });
        continue;
      }

      const isAllowedFile = base === ALLOWED_FILE;
      // 归属判定用**源码偏移**（不是行/列重建的近似值——行号经换行归一化会漂）
      const fnName = isAllowedFile ? enclosingFunction(bodies, w.offset) : null;
      const inUpsert = fnName === ALLOWED_FN;

      if (isAllowedFile && inUpsert) {
        allowed.push({ file: rel, line: w.line, kind: w.kind, note: `在 ${ALLOWED_FILE}:${ALLOWED_FN}() 内` });
      } else if (isAllowedFile) {
        violations.push({ ...w, file: rel, rule: "wrong-function", actualFn: fnName || "(未识别函数体)" });
      } else {
        violations.push({ ...w, file: rel, rule: "non-whitelisted-file" });
      }
    }
  }

  return { violations, allowed, scanned };
}

/* ── 修复建议 ───────────────────────────────────────────────────────────── */

function fixHint(v) {
  switch (v.rule) {
    case "non-whitelisted-file":
      return `移到 BlockIndex：在 ${ALLOWED_FILE} 的 upsert() 里写，本文件改为读 [data--src-line] 或走 blocksInRange()`;
    case "wrong-function":
      return `${ALLOWED_FILE} 内也只允许 upsert() 写（当前在 ${v.actualFn}）—— 把写属性收敛到 upsert()`;
    case "forward-write":
      return "这是把另一个节点上的行号抄过来（等于第二处事实来源）：改由 upsert(handle) 重写；确属合法请登记 ALLOWED_FORWARD 并写理由";
    default:
      return "改走 BlockIndex.upsert()";
  }
}

/* ── CLI ────────────────────────────────────────────────────────────────── */

function main(argv) {
  const asJson = argv.includes("--json");
  const listOnly = argv.includes("--list");
  const ri = argv.indexOf("--root");
  const root = ri >= 0 && argv[ri + 1] ? path.resolve(argv[ri + 1]) : DEFAULT_ROOT;

  if (listOnly) {
    console.log(JSON.stringify({ allowedFiles: [ALLOWED_FILE], allowedFunction: ALLOWED_FN, allowedForward: ALLOWED_FORWARD, ignored: [...IGNORE_FILES] }, null, 2));
    return 0;
  }

  if (!fs.existsSync(root)) {
    const msg = "扫描根不存在: " + root;
    if (asJson) console.log(JSON.stringify({ ok: false, error: msg }, null, 2));
    else console.error("GATE ERROR  " + msg);
    return 1;
  }

  const { violations, allowed, scanned } = scan(root);
  const ok = violations.length === 0;

  if (asJson) {
    console.log(
      JSON.stringify(
        {
          ok,
          root: path.relative(path.join(__dirname, "..", "..", ".."), root).replace(/\\/g, "/") || ".",
          guarded: GUARDED,
          allowedFiles: [ALLOWED_FILE],
          allowedFunction: ALLOWED_FN,
          scannedFiles: scanned.length,
          violationCount: violations.length,
          violations: violations.map((v) => ({
            file: v.file,
            line: v.line,
            col: v.col,
            kind: v.kind,
            rule: v.rule,
            actualFn: v.actualFn || null,
            fix: fixHint(v),
          })),
          allowedCount: allowed.length,
        },
        null,
        2
      )
    );
    return ok ? 0 : 1;
  }

  console.log("── data--src-line 写入门禁 ──");
  console.log("扫描根 : " + root);
  console.log("扫描文件: " + scanned.length + " 个 .js");
  console.log("允许清单: " + ALLOWED_FILE + " 的 " + ALLOWED_FN + "() 内（其它一律 FAIL）");
  console.log("");

  if (ok) {
    console.log("RESULT  PASS  0 处违规写点");
    console.log("（" + allowed.length + " 处命中均在允许范围内）");
  } else {
    console.log("RESULT  FAIL  " + violations.length + " 处违规写点");
    console.log("");
    for (const v of violations) {
      console.log(`  ${v.file}:${v.line}:${v.col}  [${v.rule}]`);
      console.log(`     形式: ${v.detail}`);
      console.log(`     修法: ${fixHint(v)}`);
    }
  }
  return ok ? 0 : 1;
}

if (require.main === module) {
  process.exit(main(process.argv.slice(2)));
}

module.exports = { findWrites, scan, functionBodies, enclosingFunction, GUARDED, ALLOWED_FILE, ALLOWED_FN, DEFAULT_ROOT, main };
