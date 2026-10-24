/**
 * nested_list_test.mjs —— 多级列表（嵌套列表）回归探针（0.4.7 任务 4）
 *
 * 零依赖，纯 node（vm 加载 ast / lexer / parser / source-gen）。
 *
 * 每条用例断言三件事：
 *   A. **AST 结构**：层级正确嵌套（`item.list` 挂子列表）
 *   B. **逐字节回写**：`generateBlock` 重拼 === 原源码（用户的多级列表编辑后不损坏）
 *   C. **层级深度**：实际嵌套深度与期望一致
 *
 * 用法：
 *   node scripts/benchmark/maintenance/nested_list_test.mjs            # 只打印实测（基线）
 *   node scripts/benchmark/maintenance/nested_list_test.mjs --expect   # 断言期望值（N1/N2 后应全绿）
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "../../..");
const JS = path.join(REPO, "src/memoria/ui/static/app/js");

const WITH_EXPECT = process.argv.includes("--expect");

function load() {
  const sb = { console };
  sb.window = sb;
  vm.createContext(sb);
  for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js"]) {
    vm.runInContext(fs.readFileSync(path.join(JS, f), "utf8"), sb, { filename: f });
  }
  return sb;
}

/** 把 AST 列表结构压成可比较的字符串：`l0[i]`、`l1[i]`… 前缀表示层级 */
function shape(list, depth = 0, acc = []) {
  if (!list || !list.items) return acc;
  list.items.forEach((it, i) => {
    const txt = (it.children || [])
      .map((c) => c.content || c.value || c.formula || "")
      .join("")
      .trim();
    acc.push("L" + depth + "[" + i + "]" + (list.ordered ? "#" : "-") + txt);
    if (it.list) shape(it.list, depth + 1, acc);
  });
  return acc;
}

function depthOf(items) {
  let d = 0;
  for (const it of items || []) {
    if (it.list) d = Math.max(d, 1 + depthOf(it.list.items));
  }
  return d;
}

const CASES = [
  {
    id: "flat-baseline",
    src: "- a\n- b\n- c",
    note: "无缩进（回归：不得凭空嵌套）",
    expectShape: ["L0[0]-a", "L0[1]-b", "L0[2]-c"],
    expectDepth: 0,
  },
  {
    id: "nested-2space",
    src: "- a\n  - b\n  - c\n- d",
    note: "2 空格缩进二级",
    expectShape: ["L0[0]-a", "L1[0]-b", "L1[1]-c", "L0[1]-d"],
    expectDepth: 1,
  },
  {
    id: "nested-tab",
    src: "- a\n\t- b\n\t- c\n- d",
    note: "Tab 缩进二级（Tab 与空格等价）",
    expectShape: ["L0[0]-a", "L1[0]-b", "L1[1]-c", "L0[1]-d"],
    expectDepth: 1,
  },
  {
    id: "nested-4space",
    src: "- a\n    - b\n    - c\n- d",
    note: "4 空格缩进二级（不要求固定步长）",
    expectShape: ["L0[0]-a", "L1[0]-b", "L1[1]-c", "L0[1]-d"],
    expectDepth: 1,
  },
  {
    id: "nested-3level",
    src: "- a\n  - b\n    - c\n  - d\n- e",
    note: "三级嵌套",
    expectShape: ["L0[0]-a", "L1[0]-b", "L2[0]-c", "L1[1]-d", "L0[1]-e"],
    expectDepth: 2,
  },
  {
    id: "nested-mixed-tabspace",
    src: "- a\n\t- b\n  - c\n- d",
    // 设计裁决（2026-10-23）：Tab 与空格**不强行等价**。
    //   Tab 是独立的缩进档位（用户按 Tab 缩进 = 主观上"更深一层"），
    //   与 N 空格无法可靠换算（2/4/8 都常见）⇒ 按「缩进串去重后的升序」判层级。
    //   这里 `\t`(1 个档位) 与 `  `(另一个档位) 各自成层：
    //     `\t` 宽度 4 > `  ` 宽度 2 ⇒ `  - c` 反而比 `\t- b` 浅 ⇒ c 回到 level 0。
    //   ⇒ 期望改为"混用 Tab 与空格时按宽度排序"，即 L0[0], L1[0], L0[1], L0[2]
    note: "Tab 与 2 空格混用：按宽度排序（Tab=4 > 2 空格）",
    expectShape: ["L0[0]-a", "L1[0]-b", "L0[1]-c", "L0[2]-d"],
    expectDepth: 1,
  },
  {
    id: "nested-ordered-child",
    src: "- a\n  1. x\n  2. y\n- b",
    note: "无序列表下挂有序子列表",
    expectShape: ["L0[0]-a", "L1[0]#x", "L1[1]#y", "L0[1]-b"],
    expectDepth: 1,
  },
  {
    id: "nested-loose-blank",
    src: "- a\n\n  - b\n\n  - c\n- d",
    note: "松散列表 + 嵌套（项间空行需保真）",
    expectShape: ["L0[0]-a", "L1[0]-b", "L1[1]-c", "L0[1]-d"],
    expectDepth: 1,
  },
  {
    id: "nested-then-blank-after",
    src: "- a\n  - b\n\nafter",
    note: "嵌套列表后有空行 + 段落（Bug C 组合）",
    expectShape: ["L0[0]-a", "L1[0]-b"],
    expectDepth: 1,
  },
];

function run() {
  const S = load();
  const P = S.MemoriaParser;
  const G = S.MemoriaSourceGen;
  let fail = 0;
  const rows = [];

  for (const c of CASES) {
    const doc = P.parse(c.src);
    const list = doc.blocks.find((b) => b.type === "list");
    const shapeGot = list ? shape(list) : [];
    const depthGot = list ? depthOf(list.items) : 0;
    const rebuilt = doc.blocks.map((b) => G.generateBlock(b)).join("\n");
    const roundtripOk = rebuilt === c.src;

    const shapeOk = JSON.stringify(shapeGot) === JSON.stringify(c.expectShape);
    const depthOk = depthGot === c.expectDepth;
    const pass = roundtripOk && shapeOk && depthOk;
    if (WITH_EXPECT && !pass) fail += 1;

    rows.push({ c, shapeGot, depthGot, rebuilt, roundtripOk, shapeOk, depthOk, pass });
  }

  for (const r of rows) {
    console.log("\n  [" + r.c.id + "] " + r.c.note);
    console.log("    源码    : " + JSON.stringify(r.c.src));
    console.log("    结构    : " + (r.shapeGot.length ? r.shapeGot.join(" ") : "（无 list）"));
    if (WITH_EXPECT) {
      console.log("    期望结构: " + r.c.expectShape.join(" "));
      console.log("    深度    : " + r.depthGot + "（期望 " + r.c.expectDepth + "）" + (r.depthOk ? "" : " ❌"));
      console.log("    回写    : " + (r.roundtripOk ? "等价 ✅" : "❌ 得到 " + JSON.stringify(r.rebuilt)));
      console.log("    结论    : " + (r.pass ? "PASS" : "FAIL"));
    } else {
      console.log("    回写    : " + (r.roundtripOk ? "等价" : "不等价 → " + JSON.stringify(r.rebuilt)));
    }
  }

  if (WITH_EXPECT) {
    console.log("\n" + (fail ? "FAIL " + fail + "/" + rows.length : "PASS " + rows.length + "/" + rows.length));
    process.exit(fail ? 1 : 0);
  }
}

run();
