#!/usr/bin/env node
/**
 * G05 · 图谱渲染性能采集（L1 无头层）
 *
 * 用途：把「每帧花在布局 vs 花在绘制」分开量出来，为优化项的优先级提供数据依据。
 * 对应设计文档：docs/design/graph-benchmark.md（指标口径与 A/B 门禁以该文档为准）。
 *
 * 用法：
 *   node scripts/benchmark/graph/render_l1.mjs
 *   node scripts/benchmark/graph/render_l1.mjs --scales 100,500 --patterns small_world --frames 30
 *   node scripts/benchmark/graph/render_l1.mjs --out scripts/benchmark/graph/results/raw.json
 *
 * 口径边界（不许含糊，报告里必须一并给出）：
 *   1. 无头环境没有真 canvas —— 绘制只测「调用次数 + JS 侧耗时」，**测不到光栅化与 GPU**。
 *   2. 真机在 ≥60 节点时布局跑在 Web Worker 里；本脚本量的是同一份 sim-core 代码在主线程的口径，
 *      绝对值会有偏差，量级可比。
 *   3. 真帧率（frame_ms / 长任务）必须走 L2 浏览器层，本层不能替代。
 *   4. 只覆盖 2D（Canvas 2D）。3D 需要 WebGL，只能走 L2。
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, "..", "..", "..");
const JS_DIR = path.join(ROOT, "src", "memoria", "ui", "static", "app", "js");

const VIEW_W = 1200;
const VIEW_H = 800;
const DPR = 2;

/**
 * 视图参数：必须与 `src/memoria/ui/static/app/js/graph-settings.js` 的 `DEFAULTS` 保持一致。
 *
 * 为什么必须补全：`GraphView2D._layoutOptsFromView()` 会把视图 opts **无条件**写进布局 opts
 * （`graph-view-2d.js:315-329`），视图缺键就会把 `undefined` 覆盖到布局默认值上，
 * 导致 `rep = undefined * alpha = NaN` → 整个仿真发散成 NaN（静默、无报错）。
 * 生产链路由 `app.js` 传完整 `getViewOptions()`，所以未暴露；改那边 DEFAULTS 时请同步这里。
 */
const VIEW_OPTS = {
  labelMode: "name_short",
  labelMaxLen: 8,
  linkDistance: 108,
  linkStrength: 0.28,
  repulsion: 5200,
  centerStrength: 0.006,
  velocityDecay: 0.8,
  warmupTicks: 160,
  arrowSize: 7,
  nodeRadius: 6,
  spreadFactor: 0.42,
  groupLabelMode: "hub_name",
  groupLabelMaxLen: 12,
  groupSpacing: 260,
  distMode: "grid",
  alphaMin: 0.012,
  alphaDecay: 0.045,
  alphaTarget: 0.12,
  dragReheat: 0.28,
  dragReleaseReheat: 0.2,
  graphStyle: "force",
  galaxyGlow2d: 0.6,
};

/** 仿真必需参数；缺一个就会静默变 NaN（见 VIEW_OPTS 注释） */
const REQUIRED_SIM_KEYS = [
  "linkDistance",
  "linkStrength",
  "repulsion",
  "centerStrength",
  "velocityDecay",
  "alphaMin",
  "alphaDecay",
  "alphaTarget",
];

/** 被计数的 canvas 2D 方法（绘制调用次数的口径） */
const CTX_METHODS = [
  "save",
  "restore",
  "beginPath",
  "closePath",
  "moveTo",
  "lineTo",
  "arc",
  "rect",
  "stroke",
  "fill",
  "clearRect",
  "fillRect",
  "translate",
  "scale",
  "setTransform",
  "clip",
  "setLineDash",
  "fillText",
  "strokeText",
  "drawImage",
];

function parseArgs(argv) {
  const out = {
    scales: null,
    patterns: null,
    frames: 30,
    seed: 42,
    out: null,
    structureOnly: false,
    frameBudget: null,
    profile: false,
    noBh: false,
    bhTheta: null,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--structure-only") {
      out.structureOnly = true;
    } else if (a === "--no-bh") {
      // 关掉 Barnes-Hut，走精确 O(N²) —— 与默认（近似）做同 build A/B
      out.noBh = true;
    } else if (a === "--profile") {
      // 打开 sim-core 的分项剖面（center / repulsion / links / integrate + pair 数与 dist2<1 守卫命中数）
      out.profile = true;
    } else if (a === "--bh-theta" && argv[i + 1]) {
      // Barnes-Hut 近似程度（默认 0.9）：越大越快、力误差越大
      out.bhTheta = parseFloat(argv[++i]);
    } else if (a === "--frame-budget" && argv[i + 1]) {
      // 0 = 关闭预算（复现改造前的"每帧固定 maxTicksPerFrame 个 tick"）
      out.frameBudget = parseFloat(argv[++i]);
    } else if (a === "--scales" && argv[i + 1]) {
      out.scales = argv[++i]
        .split(",")
        .map((x) => parseInt(x, 10))
        .filter(Number.isFinite);
    } else if (a === "--patterns" && argv[i + 1]) {
      out.patterns = argv[++i]
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
    } else if (a === "--frames" && argv[i + 1]) {
      out.frames = parseInt(argv[++i], 10) || 30;
    } else if (a === "--seed" && argv[i + 1]) {
      out.seed = parseInt(argv[++i], 10) || 42;
    } else if (a === "--out" && argv[i + 1]) {
      out.out = argv[++i];
    }
  }
  return out;
}

function resetCounter(counter) {
  for (const k of Object.keys(counter)) delete counter[k];
}

function makeRecordingCtx(counter) {
  const ctx = {};
  for (const m of CTX_METHODS) {
    ctx[m] = () => {
      counter[m] = (counter[m] || 0) + 1;
    };
  }
  ctx.measureText = (t) => {
    counter.measureText = (counter.measureText || 0) + 1;
    // 无头环境给一个稳定的近似宽度即可（真实字宽由 L2 浏览器量）
    return { width: String(t ?? "").length * 6 };
  };
  ctx.createRadialGradient = () => {
    counter.createRadialGradient = (counter.createRadialGradient || 0) + 1;
    return { addColorStop() {} };
  };
  ctx.createLinearGradient = () => {
    counter.createLinearGradient = (counter.createLinearGradient || 0) + 1;
    return { addColorStop() {} };
  };
  ctx.getImageData = () => ({ data: new Uint8ClampedArray(4), width: 1, height: 1 });
  return ctx;
}

function makeSandbox(counter) {
  const ctx = makeRecordingCtx(counter);
  const makeCanvas = () => ({
    tagName: "CANVAS",
    className: "",
    width: 0,
    height: 0,
    style: {},
    getContext: (kind) => (kind === "2d" ? ctx : null),
    addEventListener() {},
    removeEventListener() {},
    replaceWith() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: VIEW_W, height: VIEW_H }),
  });
  const container = {
    innerHTML: "",
    style: {},
    clientWidth: VIEW_W,
    clientHeight: VIEW_H,
    appendChild() {},
    addEventListener() {},
    removeEventListener() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: VIEW_W, height: VIEW_H }),
  };
  class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  const sandbox = {
    console,
    performance,
    Math,
    Object,
    Array,
    Map,
    Set,
    JSON,
    Number,
    String,
    Boolean,
    Date,
    Error,
    isFinite,
    parseFloat,
    parseInt,
    Uint8ClampedArray,
    Float64Array,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    devicePixelRatio: DPR,
    ResizeObserver,
    getComputedStyle: () => ({
      backgroundColor: "#161b22",
      getPropertyValue: () => "",
    }),
    requestAnimationFrame(fn) {
      return setTimeout(fn, 0);
    },
    cancelAnimationFrame(id) {
      clearTimeout(id);
    },
    document: {
      createElement: (tag) =>
        tag === "canvas"
          ? makeCanvas()
          : { tagName: String(tag).toUpperCase(), style: {}, appendChild() {}, addEventListener() {} },
      getElementById: () => null,
      addEventListener() {},
      removeEventListener() {},
      body: { style: {}, appendChild() {} },
    },
  };
  sandbox.global = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.__container = container;
  vm.createContext(sandbox);
  return sandbox;
}

function loadScripts(sandbox, names) {
  for (const name of names) {
    const file = path.join(JS_DIR, name);
    if (!fs.existsSync(file)) throw new Error(`missing ${file}`);
    vm.runInContext(fs.readFileSync(file, "utf8"), sandbox);
  }
}

function pct(sorted, p) {
  if (!sorted.length) return 0;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[i];
}

function stat(values) {
  const s = [...values].sort((a, b) => a - b);
  const r = (x) => Math.round(x * 1000) / 1000;
  return { p50: r(pct(s, 50)), p95: r(pct(s, 95)), max: r(s[s.length - 1] || 0) };
}

/** 布局质量代理指标：边长的分布（用于 D2 近似排斥的 A/B 观感对照） */
function edgeLengthStats(nodes, simLinks) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const lens = [];
  let skipped = 0;
  for (const l of simLinks) {
    // 索引优先（layout 自己的口径），退回按 id 查（兜底，避免索引口径变化导致静默 NaN）
    const a = nodes[l.sourceIndex] || byId.get(l.source);
    const b = nodes[l.targetIndex] || byId.get(l.target);
    if (!a || !b) {
      skipped++;
      continue;
    }
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    if (!Number.isFinite(dx) || !Number.isFinite(dy)) {
      skipped++;
      continue;
    }
    lens.push(Math.sqrt(dx * dx + dy * dy));
  }
  const sorted = [...lens].sort((x, y) => x - y);
  const r = (x) => Math.round(x * 10) / 10;
  return {
    edgeLenP50: r(pct(sorted, 50)),
    edgeLenP95: r(pct(sorted, 95)),
    edgeLenMax: r(sorted[sorted.length - 1] || 0),
    edgeCount: sorted.length,
    edgeSkipped: skipped,
  };
}

function benchOne(sandbox, { scale, pattern, frames, seed, frameBudget, profile, noBh, bhTheta }) {
  const {
    MemoriaGraphSynthetic: Synth,
    MemoriaGraphEngine: Engine,
    MemoriaGraphLayout2D: Layout2D,
    MemoriaGraphView2D: View2D,
  } = sandbox;

  const graph = Synth.syntheticGraph(scale, pattern, {
    seed,
    nGroups: Math.max(3, Math.floor(scale / 40)),
  });
  const engine = new Engine();
  const layout = new Layout2D(VIEW_OPTS);
  const view = new View2D(sandbox.__container, engine, layout, VIEW_OPTS);
  view.active = true;

  // 走真机同一条链路：loadPayload → "load" → view.resetSimulation() → layout.loadFromEngine(含 160 tick warmup)
  const t0 = performance.now();
  engine.loadPayload(
    { nodes: graph.nodes, edges: graph.edges },
    { groupLabelMode: "hub_name", groupLabelMaxLen: 12 }
  );
  const loadMs = Math.round((performance.now() - t0) * 1000) / 1000;

  // 守卫：缺键会被静默覆盖成 undefined 并让仿真发散成 NaN；宁可显式失败，也不要产出垃圾数据
  for (const k of REQUIRED_SIM_KEYS) {
    if (!Number.isFinite(layout.opts[k])) {
      throw new Error(
        `layout.opts.${k} = ${layout.opts[k]}（非有限）—— VIEW_OPTS 与 graph-settings.js DEFAULTS 不同步？`
      );
    }
  }
  const badNodes = layout.nodes.filter(
    (n) => !Number.isFinite(n.x) || !Number.isFinite(n.y)
  );
  if (badNodes.length) {
    throw new Error(
      `仿真发散：${badNodes.length}/${layout.nodes.length} 个节点坐标非有限（scale=${scale} pattern=${pattern}）`
    );
  }

  // A/B 对照用：显式覆盖帧预算（0 = 关闭预算，复现"每帧固定 maxTicksPerFrame 个 tick"的旧行为）
  if (frameBudget != null) {
    layout.applyOptions({ frameBudgetMs: frameBudget }, { relayout: false });
  }
  if (profile) {
    layout.applyOptions({ profile: true }, { relayout: false });
    layout._profile = null; // 只统计帧循环内的 tick（warmup 已跑完，不混进来）
  }
  if (noBh) {
    layout.applyOptions({ bh: false }, { relayout: false }); // 精确 O(N²)，供 A/B
  }
  if (bhTheta > 0) {
    layout.applyOptions({ bhTheta }, { relayout: false });
  }

  view.fitToView();
  view.draw(); // 预热一次（字体测量、渐变等）

  const counter = sandbox.__counter;
  if (process.env.GRAPH_L1_DEBUG) {
    console.error("[debug] node0 =", JSON.stringify(layout.nodes[0]));
    console.error("[debug] simLink0 =", JSON.stringify(layout.simLinks[0]));
    console.error("[debug] transform =", JSON.stringify(view.transform));
  }
  const ticks = layout.opts.maxTicksPerFrame || 6;
  const tickMs = [];
  const drawMs = [];
  const frameMs = [];
  const hoverDrawMs = [];
  const ticksRun = [];
  let callsPerDraw = {};

  for (let f = 0; f < frames; f++) {
    const tTick = performance.now();
    // 与真机同入口：runFrameTicks() 内含帧预算决策（start() 也调它）
    ticksRun.push(layout.runFrameTicks());
    tickMs.push(performance.now() - tTick);

    resetCounter(counter);
    const tDraw = performance.now();
    view.draw();
    const drawCost = performance.now() - tDraw;
    drawMs.push(drawCost);
    frameMs.push(performance.now() - tTick);
    if (f === frames - 1) callsPerDraw = { ...counter };
  }

  // hover 场景：悬停任意一个节点（会走 getOutgoingLinks + 高亮分支）
  const hoverId = graph.nodes[Math.max(0, Math.floor(graph.nodes.length / 2))]?.id || null;
  view.hoverId = hoverId;
  for (let f = 0; f < Math.min(frames, 15); f++) {
    const t = performance.now();
    view.draw();
    hoverDrawMs.push(performance.now() - t);
  }
  view.hoverId = null;

  const totalCalls = Object.values(callsPerDraw).reduce((a, b) => a + b, 0);

  return {
    scale,
    pattern,
    nodeCount: layout.nodes.length,
    linkCount: layout.simLinks.length,
    groupCount: engine.groups?.groups?.length ?? 0,
    ticksPerFrame: ticks,
    frameBudgetMs: layout.opts.frameBudgetMs ?? null,
    bh: layout.opts.bh !== false,
    bhTheta: layout.opts.bhTheta ?? null,
    // 实际执行的 warmup tick 数（装载阶段；受 sim-core.WARMUP_PAIR_TICK_CAP 工作量上限约束）
    warmupTicksRun: sandbox.MemoriaGraphLayoutSim?.effectiveWarmupTicks
      ? sandbox.MemoriaGraphLayoutSim.effectiveWarmupTicks(
          layout.nodes.length,
          layout.opts.warmupTicks
        )
      : null,
    ticksRun: {
      mean: Math.round((ticksRun.reduce((a, b) => a + b, 0) / ticksRun.length) * 100) / 100,
      min: Math.min(...ticksRun),
      max: Math.max(...ticksRun),
    },
    loadMs,
    tickMs: stat(tickMs),
    drawMs: stat(drawMs),
    frameMs: stat(frameMs),
    hoverDrawMs: stat(hoverDrawMs),
    callsPerDraw,
    callsPerDrawTotal: totalCalls,
    // 若不做「静止停帧」：页签可见期间这一档每秒仍要付这些量
    idlePerSecIfNeverStop: {
      frames: 60,
      tickMs: Math.round(stat(tickMs).p50 * 60),
      drawMs: Math.round(stat(drawMs).p50 * 60),
      calls: totalCalls * 60,
    },
    quality: edgeLengthStats(layout.nodes, layout.simLinks),
    profile: profileFrom(layout._profile),
  };
}

/** 把 sim-core 的累加剖面整理成可读口径（分项占比 / 每 tick / 每对） */
function profileFrom(p) {
  if (!p) return null;
  const total = p.centerMs + p.repulsionMs + p.linksMs + p.integrateMs;
  const pairs = Math.max(0, (p.pairSlots ?? 0) - (p.skipped ?? 0)); // 实际参与计算的对数
  const slots = Math.max(1, p.pairSlots ?? 0);
  const r2 = (x) => Math.round(x * 100) / 100;
  return {
    ticks: p.ticks,
    pairs,
    pairSlots: p.pairSlots ?? 0,
    skippedPairs: p.skipped ?? 0,
    // 关键假设指标：`dist2 < distanceMin`（近重合节点）被夹住/被跳过的频率
    distGuardHits: p.distGuardHits,
    guardHitRate: pairs ? Math.round((p.distGuardHits / pairs) * 1e6) / 1e6 : 0,
    // Barnes-Hut 路径：近似力应用次数（应 ∝ N log N）与树格数
    bhInteractions: p.bhInteractions ?? 0,
    bhCells: p.bhCells ?? 0,
    nsPerBhInteraction: p.bhInteractions
      ? Math.round((p.repulsionMs * 1e6) / p.bhInteractions)
      : 0,
    centerMs: r2(p.centerMs),
    repulsionMs: r2(p.repulsionMs),
    linksMs: r2(p.linksMs),
    integrateMs: r2(p.integrateMs),
    repulsionShare: total ? Math.round((p.repulsionMs / total) * 1000) / 1000 : 0,
    // 两个口径要分开看：pair 循环对**每一对 i<j**都要跑一次 skip 检查（含被跳过的），
    // 故跨群多的图（partitioned）用"每计算对"做分母会虚高 —— 以 nsPerSlot 为准。
    nsPerComputedPair: pairs ? Math.round((p.repulsionMs * 1e6) / pairs) : 0,
    nsPerSlot: p.pairSlots ? Math.round((p.repulsionMs * 1e6) / slots) : 0,
  };
}

function main() {
  const args = parseArgs(process.argv);
  const counter = {};
  const sandbox = makeSandbox(counter);
  sandbox.__counter = counter;
  loadScripts(sandbox, [
    "graph-synthetic.js",
    "graph-label.js",
    "graph-groups.js",
    "graph-bh-tree.js",
    "graph-layout-sim-core.js",
    "graph-layout-2d.js",
    "graph-engine.js",
    "graph-view-2d.js",
  ]);

  const { MemoriaGraphSynthetic: Synth, MemoriaGraphGroups: Groups } = sandbox;
  const scales = args.scales || Synth.BENCHMARK_SCALES;
  const patterns = args.patterns || Synth.BENCHMARK_PATTERNS;

  // --structure-only：不算布局/渲染，只出图结构（秒级）。
  // 用途：成本由「最大连通分量」决定（跨群排斥被跳过），没有这一列就看不懂 tick 耗时为什么忽高忽低。
  if (args.structureOnly) {
    const rows = [];
    for (const pattern of patterns) {
      for (const scale of scales) {
        const graph = Synth.syntheticGraph(scale, pattern, {
          seed: args.seed,
          nGroups: Math.max(3, Math.floor(scale / 40)),
        });
        const g = Groups.computeGraphGroups(graph.nodes, graph.links, {});
        const largest = g.groups[0]?.size ?? 0;
        rows.push({
          pattern,
          scale,
          nodeCount: graph.nodes.length,
          linkCount: graph.links.length,
          groupCount: g.groups.length,
          largestGroup: largest,
          largestGroupShare:
            graph.nodes.length > 0
              ? Math.round((largest / graph.nodes.length) * 1000) / 1000
              : 0,
          isolatedNodes: g.groups.filter((x) => x.size === 1).length,
        });
      }
    }
    console.log(
      JSON.stringify(
        { status: "ok", mode: "structure-only", seed: args.seed, results: rows },
        null,
        2
      )
    );
    return;
  }

  const results = [];
  for (const pattern of patterns) {
    for (const scale of scales) {
      results.push(
        benchOne(sandbox, {
          scale,
          pattern,
          frames: args.frames,
          seed: args.seed,
          frameBudget: args.frameBudget,
          profile: args.profile,
          noBh: args.noBh,
          bhTheta: args.bhTheta,
        })
      );
    }
  }

  const payload = {
    status: "ok",
    engine: "memoria-graph-render-l1",
    layer: "L1-headless",
    dimension: "2d",
    view: { w: VIEW_W, h: VIEW_H, dpr: DPR },
    frames: args.frames,
    seed: args.seed,
    frameBudgetOverride: args.frameBudget,
    caveats: [
      "无头环境无真 canvas：绘制只测调用次数与 JS 侧耗时，不含光栅化/GPU",
      "真机 ≥60 节点时布局在 Web Worker 内，本层为主线程同代码口径",
      "真帧率与长任务需走 L2 浏览器层",
      "仅覆盖 2D；3D 需 WebGL，只能走 L2",
    ],
    results,
  };

  const text = JSON.stringify(payload, null, 2);
  if (args.out) {
    const dest = path.isAbsolute(args.out) ? args.out : path.join(ROOT, args.out);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, text + "\n", "utf8");
    console.error(`[render_l1] written ${path.relative(ROOT, dest)}`);
  }
  console.log(text);
}

main();
