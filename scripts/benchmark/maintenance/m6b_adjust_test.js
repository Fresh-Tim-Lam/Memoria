#!/usr/bin/env node
/* M6b 调整逻辑单测：从真实 app.js 抽取 KP 行号调整辅助函数，配 DOM/state stub 后断言。
   用法：node scripts/benchmark/maintenance/m6b_adjust_test.js */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "app.js");
const src = fs.readFileSync(APP, "utf8");
const start = src.indexOf("    function _kpRr(kp)");
const end = src.indexOf("    // 源码编辑器：Backspace/Delete/Enter 行级操作");
if (start < 0 || end < 0 || end <= start) {
  console.error("无法定位辅助函数区");
  process.exit(1);
}
const body = src.slice(start, end);

let failures = 0;
function check(name, cond, extra) {
  console.log((cond ? "PASS" : "FAIL") + "  " + name + (extra ? "  " + JSON.stringify(extra) : ""));
  if (!cond) failures += 1;
}

function freshDoc() {
  return {
    knowledge_points: [
      {
        id: "k1",
        name: "K1",
        range: { start: { line_hint: 2 }, end: { line_hint: 4 } },
        range_resolved: { ok: true, start_line: 2, end_line: 4 },
      },
      {
        id: "k2",
        name: "K2",
        range: { start: { line_hint: 6 }, end: { line_hint: 7 } },
        range_resolved: { ok: true, start_line: 6, end_line: 7 },
      },
    ],
  };
}

function runScenario(title, mutate) {
  const state = { doc: freshDoc(), hoveredKpId: null };
  const sandbox = {
    state,
    CSS: { escape: (s) => s },
    document: {
      querySelector: () => null,
    },
    highlightKpHover: () => {},
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(body, sandbox, { filename: "m6b-helpers.js" });
  const lines = (id) => {
    const k = state.doc.knowledge_points.find((x) => x.id === id);
    return [k.range_resolved.start_line, k.range_resolved.end_line];
  };
  mutate(sandbox, lines);
  return lines;
}

const r1 = runScenario("区域中段 Enter → k1 吸收(终点+1)、k2 顺延", (s, lines) => {
  const absorb = s.findAbsorbKp(3, 5, 20);
  check("吸收命中 k1", absorb === "k1", { absorb });
  s.adjustKpRangesAfterInsert(3, { before: false, absorbId: absorb });
  check("k1 2..4 → 2..5", JSON.stringify(lines("k1")) === JSON.stringify([2, 5]), lines("k1"));
  check("k2 6..7 → 7..8", JSON.stringify(lines("k2")) === JSON.stringify([7, 8]), lines("k2"));
});
const r2 = runScenario("区域末行行尾 Enter → 不吸收，仅后续顺延", (s, lines) => {
  const absorb = s.findAbsorbKp(4, 20, 20);
  check("吸收为空", absorb === null, { absorb });
  s.adjustKpRangesAfterInsert(4, { before: false, absorbId: absorb });
  check("k1 保持 2..4", JSON.stringify(lines("k1")) === JSON.stringify([2, 4]), lines("k1"));
  check("k2 → 7..8", JSON.stringify(lines("k2")) === JSON.stringify([7, 8]), lines("k2"));
});
const r3 = runScenario("标题前缀前插空行(before) → 起点>=p 的 KP 顺延", (s, lines) => {
  s.adjustKpRangesAfterInsert(6, { before: true });
  check("k1 保持 2..4", JSON.stringify(lines("k1")) === JSON.stringify([2, 4]), lines("k1"));
  check("k2 6..7 → 7..8", JSON.stringify(lines("k2")) === JSON.stringify([7, 8]), lines("k2"));
});
const r3b = runScenario("区域内部行前插空行 → 该 KP 吸收（终点+1）", (s, lines) => {
  const absorb = s.findAbsorbKpBefore(3);
  check("吸收命中 k1", absorb === "k1", { absorb });
  s.adjustKpRangesAfterInsert(3, { before: true, absorbId: absorb });
  check("k1 2..4 → 2..5", JSON.stringify(lines("k1")) === JSON.stringify([2, 5]), lines("k1"));
  check("k2 6..7 → 7..8", JSON.stringify(lines("k2")) === JSON.stringify([7, 8]), lines("k2"));
});
const r4 = runScenario("删除区域末行(R=4) → k1 终点-1、k2 顺延", (s, lines) => {
  s.adjustKpRangesAfterRemove(4);
  check("k1 2..4 → 2..3", JSON.stringify(lines("k1")) === JSON.stringify([2, 3]), lines("k1"));
  check("k2 6..7 → 5..6", JSON.stringify(lines("k2")) === JSON.stringify([5, 6]), lines("k2"));
});
const r5 = runScenario("删除区域首行(R=2) → 并入上一行近似、k2 顺延", (s, lines) => {
  s.adjustKpRangesAfterRemove(2);
  check("k1 2..4 → 1..3", JSON.stringify(lines("k1")) === JSON.stringify([1, 3]), lines("k1"));
  check("k2 6..7 → 5..6", JSON.stringify(lines("k2")) === JSON.stringify([5, 6]), lines("k2"));
});

console.log(failures ? `\nM6b 单测：${failures} 项失败` : "\nM6b 单测：全 PASS（区域内 Enter 并入/顺延/删行收缩/标题前插行）");
process.exit(failures ? 1 : 0);
