/* Memoria 图谱布局 Web Worker */
"use strict";

importScripts("/m0/js/graph-layout-sim-core.js");

const Sim = self.MemoriaGraphLayoutSim;
let dim = "2d";
let state = { nodes: [], simLinks: [], alpha: 1, dragId: null };
let opts = { ...Sim.DEFAULTS };
let running = false;
let timer = null;

function tickOnce(alphaOverride) {
  if (dim === "3d") Sim.tick3D(state, opts, alphaOverride);
  else Sim.tick2D(state, opts, alphaOverride);
}

function loop() {
  if (!running) return;
  for (let i = 0; i < opts.maxTicksPerFrame; i++) {
    tickOnce();
  }
  self.postMessage({
    type: "tick",
    alpha: state.alpha,
    nodes: state.nodes.map((n) => ({
      id: n.id,
      x: n.x,
      y: n.y,
      z: n.z,
      vx: n.vx,
      vy: n.vy,
      vz: n.vz,
    })),
  });
  timer = setTimeout(loop, 16);
}

self.onmessage = (e) => {
  const msg = e.data || {};
  switch (msg.type) {
    case "load":
      dim = msg.dim === "3d" ? "3d" : "2d";
      opts = { ...Sim.DEFAULTS, ...(msg.opts || {}) };
      state.nodes = (msg.nodes || []).map((n) => ({ ...n }));
      state.simLinks = (msg.simLinks || []).map((l) => ({ ...l }));
      state.alpha = 1;
      state.dragId = null;
      Sim.warmup(state, opts, dim);
      state.alpha = opts.alphaTarget ?? 0.12;
      self.postMessage({ type: "ready", alpha: state.alpha, nodes: state.nodes });
      break;
    case "start":
      if (running) return;
      running = true;
      loop();
      break;
    case "stop":
      running = false;
      if (timer) clearTimeout(timer);
      timer = null;
      break;
    case "setDrag":
      state.dragId = msg.id || null;
      if (msg.reheat > 0) state.alpha = Math.max(state.alpha, msg.reheat);
      break;
    case "moveDrag":
      if (!state.dragId) break;
      const dn = state.nodes.find((n) => n.id === state.dragId);
      if (!dn) break;
      dn.x = msg.x;
      dn.y = msg.y;
      if (dim === "3d") dn.z = msg.z ?? dn.z;
      dn.vx = 0;
      dn.vy = 0;
      dn.vz = 0;
      break;
    case "reheat":
      state.alpha = Math.max(state.alpha, msg.amount ?? 0.25);
      break;
    case "setOpts":
      Object.assign(opts, msg.opts || {});
      break;
    default:
      break;
  }
};
