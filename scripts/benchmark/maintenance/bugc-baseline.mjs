/**
 * bugc-baseline.mjs —— Bug C 基线/回归探针（零依赖，纯 node）
 *
 * 为什么要有它：用户报「- 块后的空行在预览区域没有渲染成空行」。
 * 实测根因是两处叠加：
 *   ① `parser.js` 列表扫描把**末尾空行**并入 `list.srcLineEnd` ⇒ AST 里没有 blank_line 块；
 *   ② `source-gen.js` 的 `case T.LIST` 只按 items 逐项 join，**忽略 `itemSrcLine`**
 *      ⇒ 松散列表里**项之间**的空行在做任何一次编辑后被永久抹掉。
 *
 * 本探针对每个用例断言两件事：
 *   A. AST 块序列（是否把末尾空行还给了 blank_line）
 *   B. 逐块 `generateBlock` 重拼后是否**逐字节**等于原源码
 *
 * 用法：
 *   node scripts/benchmark/maintenance/bugc-baseline.mjs            # 打印 + 自检（失败 exit 1）
 *   node scripts/benchmark/maintenance/bugc-baseline.mjs --json     # 机读输出
 *
 * 口径：`--expect-fixed` 表示断言"修复后应有的行为"；
 *       不带该开关时只打印实测值（用于记录基线，不判失败）。
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "../../..");
const JS_DIR = path.join(REPO, "src/memoria/ui/static/app/js");

const withExpect = process.argv.includes("--expect-fixed");
const asJson = process.argv.includes("--json");

function loadModules() {
  const sandbox = { console };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  // 依赖顺序：ast → lexer（依赖 ast）→ parser → source-gen
  for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js"]) {
    const code = fs.readFileSync(path.join(JS_DIR, f), "utf8");
    vm.runInContext(code, sandbox, { filename: f });
  }
  return sandbox;
}

/**
 * 用例表。`expectBlocks` / `expectRegenEqual` 是**修复后**的期望（仅 --expect-fixed 时断言）。
 */
const CASES = [
  {
    id: "list-trailing-blank",
    src: "- 第一项\n- 第二项\n\n后面一段文字",
    note: "列表末尾一个空行（用户报的原始场景）",
    expectBlocks: ["list(1..2)", "blank_line(3..3)", "paragraph(4..4)"],
    expectRegenEqual: true,
  },
  {
    id: "list-no-blank",
    src: "- a\n- b",
    note: "无空行（回归：不得凭空补空行）",
    expectBlocks: ["list(1..2)"],
    expectRegenEqual: true,
  },
  {
    id: "list-loose-between",
    src: "- a\n\n- b\n- c",
    note: "松散列表：项间空行属于列表内部，回写必须保留",
    expectBlocks: ["list(1..4)"],
    expectRegenEqual: true,
  },
  {
    id: "list-trailing-two-blanks",
    src: "- a\n\n\nafter",
    note: "列表后两个空行（项间无，末尾两个）",
    expectBlocks: ["list(1..1)", "blank_line(2..2)", "blank_line(3..3)", "paragraph(4..4)"],
    expectRegenEqual: true,
  },
  {
    id: "ordered-loose-between",
    src: "1. x\n\n2. y\ntail",
    // 注意：L2 空行是**项之间**（属于 list，松散列表语义），末尾 L4 `tail` 紧跟 ⇒ **没有**末尾空行。
    // 所以期望里不应出现 blank_line —— 项间空行由 source-gen 按 itemSrcLine 重建（见回写等价断言）。
    note: "有序松散列表：项间空行属于列表内部，末尾无空行",
    expectBlocks: ["list(1..3)", "paragraph(4..4)"],
    expectRegenEqual: true,
  },
  {
    id: "list-blank-mid-then-item",
    src: "- a\n\n- b\n\nafter",
    note: "项间空行 + 末尾空行同时存在",
    expectBlocks: ["list(1..3)", "blank_line(4..4)", "paragraph(5..5)"],
    expectRegenEqual: true,
  },
];

function run() {
  const S = loadModules();
  const P = S.MemoriaParser;
  const G = S.MemoriaSourceGen;
  const results = [];

  for (const c of CASES) {
    const doc = P.parse(c.src);
    const blocks = doc.blocks.map(
      (b) => b.type + "(" + b.srcLine + ".." + b.srcLineEnd + ")"
    );
    const rebuilt = doc.blocks.map((b) => G.generateBlock(b)).join("\n");
    const regenEqual = rebuilt === c.src;

    const r = {
      id: c.id,
      note: c.note,
      src: c.src,
      blocks,
      regenEqual,
      rebuilt,
      itemSrcLine: (doc.blocks.find((b) => b.type === "list") || {}).itemSrcLine || null,
      expectBlocks: c.expectBlocks,
      expectRegenEqual: c.expectRegenEqual,
    };
    if (withExpect) {
      r.blocksOk = JSON.stringify(blocks) === JSON.stringify(c.expectBlocks);
      r.pass = r.blocksOk && regenEqual === c.expectRegenEqual;
    }
    results.push(r);
  }

  if (asJson) {
    console.log(JSON.stringify({ withExpect, cases: results }, null, 2));
  } else {
    console.log("=== Bug C 基线/回归（列表空行） ===");
    for (const r of results) {
      console.log("\n  [" + r.id + "] " + r.note);
      console.log("    源码    : " + JSON.stringify(r.src));
      console.log("    blocks  : " + r.blocks.join(" "));
      console.log("    itemSrcLine: " + JSON.stringify(r.itemSrcLine));
      console.log("    回写等价: " + (r.regenEqual ? "✅" : "❌ 得到 " + JSON.stringify(r.rebuilt)));
      if (withExpect) console.log("    期望    : " + r.expectBlocks.join(" ") + "  ⇒ " + (r.pass ? "PASS" : "FAIL"));
    }
  }

  if (withExpect) {
    const failed = results.filter((r) => !r.pass);
    console.log(
      "\n" + (failed.length ? "FAIL " + failed.length + "/" + results.length : "PASS " + results.length + "/" + results.length)
    );
    process.exit(failed.length ? 1 : 0);
  }
}

run();
