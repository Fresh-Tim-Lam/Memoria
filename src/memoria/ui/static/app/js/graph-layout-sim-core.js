/**
 * 力导向 tick 核心（主线程 / Worker 共用）
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    linkDistance: 108,
    linkStrength: 0.28,
    repulsion: 5200,
    centerStrength: 0.006,
    velocityDecay: 0.8,
    alphaMin: 0.012,
    alphaDecay: 0.045,
    alphaTarget: 0.12,
    dragReheat: 0.28,
    dragReleaseReheat: 0.2,
    maxTicksPerFrame: 6,
    warmupTicks: 160,
    groupMode: "single",
  };

  /** 全部群视图下默认跳过跨群排斥；拖拽节点与任意节点之间始终参与排斥 */
  function skipPairRepulsion(a, b, dragId, groupMode) {
    if (!a.groupId || !b.groupId || a.groupId === b.groupId) return false;
    if (dragId && (a.id === dragId || b.id === dragId)) return false;
    return groupMode === "all";
  }

  function tick2D(state, opts, alphaOverride) {
    const nodes = state.nodes;
    const links = state.simLinks;
    const n = nodes.length;
    const alpha = alphaOverride != null ? alphaOverride : state.alpha;
    const repBase = opts.repulsion * (1 + Math.sqrt(n) * 0.15);
    const rep = repBase * alpha;
    const center = opts.centerStrength * alpha;
    const dragId = state.dragId;
    const groupMode = opts.groupMode || "single";

    for (let i = 0; i < n; i++) {
      const anchorX = nodes[i].groupOx != null ? nodes[i].groupOx : 0;
      const anchorY = nodes[i].groupOy != null ? nodes[i].groupOy : 0;
      nodes[i].vx += (anchorX - nodes[i].x) * center;
      nodes[i].vy += (anchorY - nodes[i].y) * center;
    }

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        if (skipPairRepulsion(nodes[i], nodes[j], dragId, groupMode)) continue;
        let dx = nodes[j].x - nodes[i].x;
        let dy = nodes[j].y - nodes[i].y;
        let dist2 = dx * dx + dy * dy;
        if (dist2 < 1) {
          dx = (Math.random() - 0.5) * 0.01;
          dy = (Math.random() - 0.5) * 0.01;
          dist2 = dx * dx + dy * dy;
        }
        const dist = Math.sqrt(dist2);
        const f = rep / dist2;
        const fx = (dx / dist) * f;
        const fy = (dy / dist) * f;
        nodes[i].vx -= fx;
        nodes[i].vy -= fy;
        nodes[j].vx += fx;
        nodes[j].vy += fy;
      }
    }

    for (const link of links) {
      const s = nodes[link.sourceIndex];
      const t = nodes[link.targetIndex];
      let dx = t.x - s.x;
      let dy = t.y - s.y;
      let dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const str = opts.linkStrength * alpha * (link.strengthScale || 1);
      const force = ((dist - opts.linkDistance) / dist) * str;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      s.vx += fx;
      s.vy += fy;
      t.vx -= fx;
      t.vy -= fy;
    }

    for (const node of nodes) {
      if (node.id === dragId) continue;
      node.vx *= opts.velocityDecay;
      node.vy *= opts.velocityDecay;
      node.x += node.vx;
      node.y += node.vy;
    }

    if (alphaOverride == null) {
      const decay = opts.alphaDecay ?? 0.045;
      state.alpha += (opts.alphaMin - state.alpha) * decay;
    }
  }

  function tick3D(state, opts, alphaOverride) {
    const nodes = state.nodes;
    const links = state.simLinks;
    const n = nodes.length;
    const alpha = alphaOverride != null ? alphaOverride : state.alpha;
    const repBase = opts.repulsion * (1 + Math.sqrt(n) * 0.15);
    const rep = repBase * alpha;
    const center = opts.centerStrength * alpha;
    const dragId = state.dragId;
    const groupMode = opts.groupMode || "single";

    for (let i = 0; i < n; i++) {
      const anchorX = nodes[i].groupOx != null ? nodes[i].groupOx : 0;
      const anchorY = nodes[i].groupOy != null ? nodes[i].groupOy : 0;
      const anchorZ = nodes[i].groupOz != null ? nodes[i].groupOz : 0;
      nodes[i].vx += (anchorX - nodes[i].x) * center;
      nodes[i].vy += (anchorY - nodes[i].y) * center;
      nodes[i].vz += (anchorZ - nodes[i].z) * center;
    }

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        if (skipPairRepulsion(nodes[i], nodes[j], dragId, groupMode)) continue;
        let dx = nodes[j].x - nodes[i].x;
        let dy = nodes[j].y - nodes[i].y;
        let dz = nodes[j].z - nodes[i].z;
        let dist2 = dx * dx + dy * dy + dz * dz;
        if (dist2 < 1) {
          dx = (Math.random() - 0.5) * 0.01;
          dy = (Math.random() - 0.5) * 0.01;
          dz = (Math.random() - 0.5) * 0.01;
          dist2 = dx * dx + dy * dy + dz * dz;
        }
        const dist = Math.sqrt(dist2);
        const f = rep / dist2;
        const fx = (dx / dist) * f;
        const fy = (dy / dist) * f;
        const fz = (dz / dist) * f;
        nodes[i].vx -= fx;
        nodes[i].vy -= fy;
        nodes[i].vz -= fz;
        nodes[j].vx += fx;
        nodes[j].vy += fy;
        nodes[j].vz += fz;
      }
    }

    for (const link of links) {
      const s = nodes[link.sourceIndex];
      const t = nodes[link.targetIndex];
      let dx = t.x - s.x;
      let dy = t.y - s.y;
      let dz = t.z - s.z;
      let dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.01;
      const str = opts.linkStrength * alpha * (link.strengthScale || 1);
      const force = ((dist - opts.linkDistance) / dist) * str;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      const fz = (dz / dist) * force;
      s.vx += fx;
      s.vy += fy;
      s.vz += fz;
      t.vx -= fx;
      t.vy -= fy;
      t.vz -= fz;
    }

    for (const node of nodes) {
      if (node.id === dragId) continue;
      node.vx *= opts.velocityDecay;
      node.vy *= opts.velocityDecay;
      node.vz *= opts.velocityDecay;
      node.x += node.vx;
      node.y += node.vy;
      node.z += node.vz;
    }

    if (alphaOverride == null) {
      const decay = opts.alphaDecay ?? 0.045;
      state.alpha += (opts.alphaMin - state.alpha) * decay;
    }
  }

  function warmup(state, opts, dim) {
    const tick = dim === "3d" ? tick3D : tick2D;
    const ticks = opts.warmupTicks;
    state.alpha = 1;
    for (let i = 0; i < ticks; i++) {
      tick(state, opts, 1 - i / ticks);
    }
  }

  function packNodes(nodes, dim) {
    return nodes.map((n) => ({
      id: n.id,
      x: n.x,
      y: n.y,
      z: dim === "3d" ? n.z || 0 : 0,
      vx: n.vx || 0,
      vy: n.vy || 0,
      vz: dim === "3d" ? n.vz || 0 : 0,
      groupId: n.groupId || null,
      groupOx: n.groupOx != null ? n.groupOx : null,
      groupOy: n.groupOy != null ? n.groupOy : null,
      groupOz: dim === "3d" && n.groupOz != null ? n.groupOz : null,
    }));
  }

  function applyPackedPositions(nodes, packed, dim) {
    const byId = new Map((packed || []).map((p) => [p.id, p]));
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const p = byId.get(node.id) ?? packed[i];
      if (!p) continue;
      node.x = p.x;
      node.y = p.y;
      node.vx = p.vx;
      node.vy = p.vy;
      if (dim === "3d") {
        node.z = p.z;
        node.vz = p.vz;
      }
    }
  }

  function layoutOptsForWorker(layout) {
    return {
      ...layout.opts,
      groupMode: layout._groupMode || "single",
    };
  }

  global.MemoriaGraphLayoutSim = {
    DEFAULTS,
    tick2D,
    tick3D,
    warmup,
    packNodes,
    applyPackedPositions,
    layoutOptsForWorker,
    skipPairRepulsion,
  };
})(typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : globalThis);
