#!/usr/bin/env node
/* G3 门禁：调度内核 VM 单测（replace/merge/优先级/epoch 陈旧丢弃/flush 收敛/旁路）。
   载入真实 scheduler.js，按场景断言 counters 与 queue 收敛（queued=0）。
   用法：node scripts/benchmark/maintenance/scheduler_vm_test.js
*/
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "scheduler.js");
const code = fs.readFileSync(SRC, "utf8");

function fresh(bypass) {
  const sandbox = {
    console: { log: () => {} },
    setTimeout, clearTimeout, Date, Number, Math,
    __BENCH_DISABLE_SCHEDULER: !!bypass,
  };
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(code, ctx, { filename: "scheduler.js" });
  return ctx.MemoriaScheduler;
}

let failures = 0;
function check(name, cond, extra) {
  console.log((cond ? "PASS" : "FAIL") + "  " + name + (extra ? "  " + JSON.stringify(extra) : ""));
  if (!cond) failures += 1;
}

(async () => {
  // A) replace 顶替 + 优先级排序 + flush 收敛 queued=0
  {
    const S = fresh(false);
    const order = [];
    S.schedule({ kind: "kp_panel", key: "f1", priority: 2, run: () => { order.push("panel"); } });
    S.schedule({ kind: "kp_panel", key: "f1", priority: 2, replace: true, run: () => { order.push("panel2"); } });
    S.schedule({ kind: "doc_save", key: "f1", priority: 0, run: () => { order.push("doc"); } });
    check("A1 顶替合并计数=1", S.counters().merged === 1, S.counters());
    await S.flush();
    const st = S.status();
    check("A2 queued=0 收敛", st.queued === 0 && !st.running, st);
    check("A3 执行序：P0 doc 先于 P2 panel", order[0] === "doc" && order.includes("panel2") && !order.includes("panel"), order);
    check("A4 executed=2", S.counters().executed === 2, S.counters());
  }

  // B) epoch 陈旧丢弃（dropStale + bumpEpoch）
  {
    const S = fresh(false);
    const gen = S.epoch();
    S.schedule({ kind: "index_rebuild", key: "kb", priority: 3, dropStale: true, gen, run: async () => { throw new Error("不应执行"); } });
    S.bumpEpoch();
    await S.flush();
    check("B1 陈旧丢弃=1 且 executed=0", S.counters().dropped === 1 && S.counters().executed === 0, S.counters());
    check("B2 queued=0", S.status().queued === 0, S.status());
  }

  // C) 旁路（__BENCH_DISABLE_SCHEDULER=1）：同步立即执行，不排队
  {
    const S = fresh(true);
    let ran = false;
    S.schedule({ kind: "kp_panel", key: "f", priority: 2, run: () => { ran = true; } });
    await S.flush();
    const c = S.counters();
    check("C1 isBypass 生效且同步执行", S.isBypass() && ran, c);
    check("C2 bypass scheduled=executed=1", c.scheduled === 1 && c.executed === 1, c);
    check("C3 queued=0", S.status().queued === 0, S.status());
  }

  console.log(failures ? `\nG3 VM 单测：${failures} 项失败` : "\nG3 VM 单测：全 PASS（replace/merge/prio/epoch-drop/flush 收敛/旁路）");
  process.exit(failures ? 1 : 0);
})();
