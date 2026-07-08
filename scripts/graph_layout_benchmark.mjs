#!/usr/bin/env node
/**
 * M2 graph layout stress benchmark (Node.js).
 * Loads MemoriaGraphLayout2D/3D + MemoriaGraphGroups from static JS.
 *
 * Usage:
 *   node scripts/graph_layout_benchmark.mjs
 *   node scripts/graph_layout_benchmark.mjs --scales 50,100,250
 */

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const JS_DIR = path.join(ROOT, "src", "memoria", "ui", "static", "m0", "js");

function parseArgs(argv) {
  const out = { scales: null, patterns: null, simFrames: 60, ticksPerFrame: 6 };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--scales" && argv[i + 1]) {
      out.scales = argv[++i].split(",").map((x) => parseInt(x, 10)).filter(Number.isFinite);
    } else if (argv[i] === "--patterns" && argv[i + 1]) {
      out.patterns = argv[++i].split(",").map((x) => x.trim()).filter(Boolean);
    } else if (argv[i] === "--frames" && argv[i + 1]) {
      out.simFrames = parseInt(argv[++i], 10) || 60;
    }
  }
  return out;
}

function makeSandbox() {
  const sandbox = {
    console,
    performance,
    Math,
    Object,
    Array,
    Map,
    Set,
    JSON,
    requestAnimationFrame(fn) {
      return setTimeout(fn, 0);
    },
    cancelAnimationFrame(id) {
      clearTimeout(id);
    },
  };
  sandbox.global = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox;
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

function benchLayout(LayoutClass, Groups, graph, opts = {}) {
  const layout = new LayoutClass({});
  const t0 = performance.now();
  layout.loadFromEngine(graph.nodes, graph.links, opts);
  const warmupMs = performance.now() - t0;

  const t1 = performance.now();
  for (let f = 0; f < opts.simFrames; f++) {
    for (let i = 0; i < opts.ticksPerFrame; i++) {
      layout.tick();
    }
  }
  const simMs = performance.now() - t1;
  layout.stop?.();

  let groupsMs = 0;
  if (Groups) {
    const tg = performance.now();
    Groups.computeGraphGroups(graph.nodes, graph.links, {
      groupLabelMode: "hub_name",
      groupLabelMaxLen: 12,
    });
    groupsMs = performance.now() - tg;
  }

  return {
    warmupMs: Math.round(warmupMs * 100) / 100,
    simMs: Math.round(simMs * 100) / 100,
    groupsMs: Math.round(groupsMs * 100) / 100,
    nodeCount: graph.nodes.length,
    linkCount: graph.links.length,
  };
}

function main() {
  const args = parseArgs(process.argv);
  const sandbox = makeSandbox();
  loadScripts(sandbox, [
    "graph-synthetic.js",
    "graph-groups.js",
    "graph-layout-2d.js",
    "graph-layout-3d.js",
  ]);

  const {
    MemoriaGraphSynthetic: Synth,
    MemoriaGraphGroups: Groups,
    MemoriaGraphLayout2D: Layout2D,
    MemoriaGraphLayout3D: Layout3D,
  } = sandbox;

  const scales = args.scales || Synth.BENCHMARK_SCALES;
  const patterns = args.patterns || Synth.BENCHMARK_PATTERNS;
  const results = [];

  for (const pattern of patterns) {
    for (const n of scales) {
      const graph = Synth.syntheticGraph(n, pattern, { seed: 42, nGroups: Math.max(3, Math.floor(n / 40)) });
      const groupOpts = {
        groupId: Groups.ALL_GROUP_ID,
        groups: Groups.computeGraphGroups(graph.nodes, graph.links, {}),
        groupSpacing: 260,
        spreadFactor: 0.42,
        simFrames: args.simFrames,
        ticksPerFrame: args.ticksPerFrame,
      };

      results.push({
        pattern,
        scale: n,
        layout2d: benchLayout(Layout2D, Groups, graph, groupOpts),
        layout3d: benchLayout(Layout3D, Groups, graph, groupOpts),
      });
    }
  }

  const payload = {
    status: "ok",
    engine: "memoria-graph-layout",
    simFrames: args.simFrames,
    ticksPerFrame: args.ticksPerFrame,
    results,
  };
  console.log(JSON.stringify(payload, null, 2));
}

main();
