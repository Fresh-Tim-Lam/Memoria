#!/usr/bin/env node
/* G3 门禁：调度内核 VM 单测（replace/merge/优先级/epoch 陈旧丢弃/flush 收敛/旁路）。
   载入真实 scheduler.js，按场景断言 counters 与 queue 收敛（queued=0）。
   M5.1 新增：帧预算切片、优先级借用/防饿死、长任务协作/自动切片、frames_used 计数。
   用法：node scripts/benchmark/maintenance/scheduler_vm_test.js
*/
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "scheduler.js");
const code = fs.readFileSync(SRC, "utf8");

/**
 * 构造隔离 sandbox。
 * - 默认用可控假时钟（performance.now），作业内 clock.t += ms 即可精确控制“耗时”；
 * - requestAnimationFrame 用 setTimeout 驱动，保持跨帧顺序，await flush() 即可跑完；
 * - 与现有单测一致，不提供 requestIdleCallback。
 */
function fresh(opts) {
  opts = opts || {};
  const clock = { t: 1000 };
  const sandbox = {
    console: { log: () => {} },
    setTimeout,
    clearTimeout,
    Date,
    Number,
    Math,
    Promise,
    performance: { now: () => clock.t },
    requestAnimationFrame: (cb) => setTimeout(() => cb(clock.t), 0),
    cancelAnimationFrame: (h) => clearTimeout(h),
    __BENCH_DISABLE_SCHEDULER: !!opts.bypass,
  };
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(code, ctx, { filename: "scheduler.js" });
  const S = ctx.MemoriaScheduler;
  if (opts.config) S.configure(opts.config);
  return { S, clock };
}

let failures = 0;
function check(name, cond, extra) {
  console.log((cond ? "PASS" : "FAIL") + "  " + name + (extra ? "  " + JSON.stringify(extra) : ""));
  if (!cond) failures += 1;
}

(async () => {
  // A) replace 顶替 + 优先级排序 + flush 收敛 queued=0
  {
    const { S } = fresh();
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
    const { S } = fresh();
    const gen = S.epoch();
    S.schedule({ kind: "index_rebuild", key: "kb", priority: 3, dropStale: true, gen, run: async () => { throw new Error("不应执行"); } });
    S.bumpEpoch();
    await S.flush();
    check("B1 陈旧丢弃=1 且 executed=0", S.counters().dropped === 1 && S.counters().executed === 0, S.counters());
    check("B2 queued=0", S.status().queued === 0, S.status());
  }

  // C) 旁路（__BENCH_DISABLE_SCHEDULER=1）：同步立即执行，不排队
  {
    const { S } = fresh({ bypass: true });
    let ran = false;
    S.schedule({ kind: "kp_panel", key: "f", priority: 2, run: () => { ran = true; } });
    await S.flush();
    const c = S.counters();
    check("C1 isBypass 生效且同步执行", S.isBypass() && ran, c);
    check("C2 bypass scheduled=executed=1", c.scheduled === 1 && c.executed === 1, c);
    check("C3 queued=0", S.status().queued === 0, S.status());
  }

  // D) 帧预算切片：10ms/帧，5 个 5ms 作业 ⇒ 2/2/1 三帧，不把多作业塞满一帧
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 10, criticalReserveMs: 4 } });
    const order = [];
    for (let i = 0; i < 5; i++) {
      S.schedule({
        kind: "budget_job", key: "b" + i, priority: 2, estimateMs: 5,
        run: () => { clock.t += 5; order.push(i); },
      });
    }
    await S.flush();
    const c = S.counters();
    check("D1 预算切片：frames_used=3（2+2+1）", c.frames_used === 3, c);
    check("D2 executed=5 且全部完成", c.executed === 5 && order.length === 5, { c, order });
    check("D3 单帧不超过预算（max_frame_ms<=10）", c.max_frame_ms <= 10, c);
    check("D4 未超预算时 budget_exceeded=0", c.budget_exceeded === 0, c);
    check("D5 普通作业无切片", c.slice_count === 0, c);
  }

  // D2) 大作业预估：预算 10ms、每个预估 6ms ⇒ 每帧只启动 1 个
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 10, criticalReserveMs: 4 } });
    for (let i = 0; i < 4; i++) {
      S.schedule({
        kind: "big_job", key: "x" + i, priority: 2, estimateMs: 6,
        run: () => { clock.t += 6; },
      });
    }
    await S.flush();
    const c = S.counters();
    check("D2a 预估 6ms/预算 10ms：每帧 1 个（frames=4）", c.frames_used === 4, c);
    check("D2b executed=4 且 max_frame_ms<=6", c.executed === 4 && c.max_frame_ms <= 6, c);
  }

  // E) 单个不可切片长作业：必须计数 budget_exceeded，且如实记录单帧上界
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 10, criticalReserveMs: 4 } });
    S.schedule({
      kind: "opaque_long", key: "o", priority: 2,
      run: () => { clock.t += 30; },
    });
    await S.flush();
    const c = S.counters();
    check("E1 30ms 长作业 budget_exceeded=1", c.budget_exceeded === 1, c);
    check("E2 frames_used=1 且 max_frame_ms=30（内核不可抢占）", c.frames_used === 1 && c.max_frame_ms === 30, c);
  }

  // F) 优先级借用：P0 8ms 可用满 10ms 预算（超过 P2 保留后的 6ms），同帧再跑 1ms P2
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 10, criticalReserveMs: 4 } });
    const order = [];
    S.schedule({ kind: "p2_small", key: "p2", priority: 2, estimateMs: 1, run: () => { clock.t += 1; order.push("p2"); } });
    S.schedule({ kind: "p0_big", key: "p0", priority: 0, estimateMs: 8, run: () => { clock.t += 8; order.push("p0"); } });
    await S.flush();
    const c = S.counters();
    check("F1 P0 借用 P2 预算：首帧跑完 8ms P0 与 1ms P2", order[0] === "p0" && order.includes("p2") && c.frames_used === 1, { order, c });
    check("F2 借用后整帧 9ms 未超 10ms", c.max_frame_ms === 9 && c.budget_exceeded === 0, c);
  }

  // G) P2 不得饿死 P0/P1：P2 分片途中入队 P0，下一帧先跑 P0 再续 P2
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 10, criticalReserveMs: 4 } });
    const order = [];
    S.schedule({
      kind: "p2_long", key: "p2", priority: 2, maxSliceMs: 3,
      run: async (ctx) => {
        for (let i = 0; i < 4; i++) {
          clock.t += 3;
          order.push("p2-" + i);
          if (i === 0) {
            S.schedule({ kind: "p0_late", key: "p0", priority: 0, run: () => { order.push("p0"); } });
          }
          if (ctx.shouldYield()) await ctx.yield();
        }
      },
    });
    await S.flush();
    const c = S.counters();
    check("G1 分片途中入队的 P0 先于下一次 P2 切片执行", order[0] === "p2-0" && order[1] === "p0", order);
    check("G2 P2 最终完成 4 片且 executed=2", order.filter((x) => x.startsWith("p2-")).length === 4 && c.executed === 2, { order, c });
    check("G3 发生 4 次切片让出（末尾一次为空切片）", c.slice_count === 4 && c.frames_used === 5, c);
  }

  // H) 长任务协作切片：maxSliceMs=4，20×1ms ⇒ 6 帧、5 次让出（末次为空尾切片）
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 12, criticalReserveMs: 4 } });
    let done = false;
    S.schedule({
      kind: "coop_slice", key: "c", priority: 2, maxSliceMs: 4,
      run: async (ctx) => {
        for (let i = 0; i < 20; i++) {
          clock.t += 1;
          if (ctx.shouldYield()) await ctx.yield();
        }
        done = true;
      },
    });
    await S.flush();
    const c = S.counters();
    check("H1 协作长任务完成", done && c.executed === 1, c);
    check("H2 切成 6 帧、5 次切片让出（末尾一次为空切片）", c.frames_used === 6 && c.slice_count === 5, c);
    check("H3 每帧 work<=4ms 且未超预算", c.max_frame_ms <= 4 && c.budget_exceeded === 0, c);
  }

  // I) async generator 自动切片：maxSliceMs=4，10×2ms ⇒ 6 帧、5 次切片（末帧发现 done）
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 12, criticalReserveMs: 4 } });
    let produced = 0;
    S.schedule({
      kind: "gen_slice", key: "g", priority: 2, maxSliceMs: 4,
      run: async function* () {
        for (let i = 0; i < 10; i++) {
          clock.t += 2;
          produced += 1;
          yield i;
        }
      },
    });
    await S.flush();
    const c = S.counters();
    check("I1 generator 全量产出", produced === 10 && c.executed === 1, { produced, c });
    check("I2 自动切片：6 帧、5 次让出（末帧发现 done，空尾切片）", c.frames_used === 6 && c.slice_count === 5, c);
    check("I3 单帧<=4ms", c.max_frame_ms <= 4, c);
  }

  // J) steps 自动切片：maxSliceMs=4，6 步×3ms ⇒ 每帧 2 步，共 3 帧、2 次让出
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 12, criticalReserveMs: 4 } });
    const steps = [];
    for (let i = 0; i < 6; i++) steps.push(() => { clock.t += 3; });
    S.schedule({ kind: "steps_slice", key: "s", priority: 2, maxSliceMs: 4, steps });
    await S.flush();
    const c = S.counters();
    check("J1 steps 全部执行", c.executed === 1, c);
    check("J2 steps 自动切片：3 帧、2 次让出", c.frames_used === 3 && c.slice_count === 2, c);    check("J3 单帧<=6ms 且未超预算", c.max_frame_ms <= 6 && c.budget_exceeded === 0, c);
  }

  // K) configure 参数与默认值
  {
    const { S } = fresh();
    const d = S.configure();
    check("K1 默认预算 12ms / 保留 4ms", d.frameBudgetMs === 12 && d.criticalReserveMs === 4, d);
    const c = S.configure({ frameBudgetMs: 16, criticalReserveMs: 99 });
    check("K2 configure 生效且保留额被夹到预算内", c.frameBudgetMs === 16 && c.criticalReserveMs === 16, c);
  }

  // L) 零耗时 generator 单元也不能饿死渲染：maxUnitsPerFrame 强制每帧让出
  {
    const { S } = fresh({ config: { frameBudgetMs: 12, maxUnitsPerFrame: 100 } });
    let produced = 0;
    S.schedule({
      kind: "zero_gen", key: "z", priority: 2,
      run: async function* () {
        for (let i = 0; i < 5000; i++) {
          produced += 1;
          yield i;
        }
      },
    });
    await S.flush();
    const c = S.counters();
    check("L1 零耗时 5000 单元全部完成且未活锁", produced === 5000 && c.executed === 1, { produced, c });
    check("L2 每帧 100 单元：51 帧 / 50 次让出", c.frames_used === 51 && c.slice_count === 50, c);
    check("L3 零 CPU 耗时下 max_frame_ms=0", c.max_frame_ms === 0, c);
  }

  // M) 已开始的切片作业不被中途 epoch 丢弃（避免半完成副作用）
  {
    const { S, clock } = fresh();
    const gen = S.epoch();
    let done = false;
    S.schedule({
      kind: "midflight_stale", key: "m", priority: 2, maxSliceMs: 2, dropStale: true, gen,
      run: async (ctx) => {
        clock.t += 1;
        S.bumpEpoch();          // 已开始后才越过 epoch
        await ctx.yield();
        clock.t += 1;
        done = true;
      },
    });
    await S.flush();
    const c = S.counters();
    check("M1 已启动作业继续完成，dropped=0", done && c.executed === 1 && c.dropped === 0, c);
    check("M2 跨帧恢复一次 slice_count=1", c.slice_count === 1 && c.frames_used === 2, c);
  }

  // N) 异步等待不消耗帧预算：await 期间假时钟推进 50ms，但不应算作 CPU/超预算
  {
    const { S, clock } = fresh({ config: { frameBudgetMs: 10, criticalReserveMs: 4 } });
    let done = false;
    S.schedule({
      kind: "async_wait", key: "n", priority: 2,
      run: async () => {
        await new Promise((resolve) => setTimeout(() => { clock.t += 50; resolve(); }, 0));
        done = true;
      },
    });
    await S.flush();
    const c = S.counters();
    check("N1 异步等待完成且不记超预算", done && c.budget_exceeded === 0, c);
    check("N2 max_frame_ms=0（只计同步前缀）", c.max_frame_ms === 0, c);
  }

  // P) generator/steps 内部也可以 await ctx.yield()（不能重复 next 运行中的 generator）
  {
    const { S, clock } = fresh();
    let genDone = false;
    let stepDone = false;
    S.schedule({
      kind: "gen_manual", key: "pg", priority: 2,
      run: async function* (ctx) {
        clock.t += 1;
        await ctx.yield();
        clock.t += 1;
        genDone = true;
        yield 1;
      },
    });
    S.schedule({
      kind: "steps_manual", key: "ps", priority: 2,
      steps: [
        async (ctx) => { clock.t += 1; await ctx.yield(); clock.t += 1; },
        () => { clock.t += 1; stepDone = true; },
      ],
    });
    await S.flush();
    const c = S.counters();
    check("P1 generator 内 ctx.yield 后正常完成", genDone, { genDone, c });
    check("P2 step 内 ctx.yield 后正常完成", stepDone, { stepDone, c });
    check("P3 两作业均无失败且无超预算", c.executed === 2 && c.budget_exceeded === 0, c);
  }

  console.log(failures ? `\nG3 VM 单测：${failures} 项失败` : "\nG3 VM 单测：全 PASS（replace/merge/prio/epoch-drop/flush 收敛/旁路 + 帧预算/借用/防饿死/协作切片/自动切片/帧计数）");
  process.exit(failures ? 1 : 0);
})();
