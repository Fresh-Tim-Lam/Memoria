/**
 * Memoria 图谱布局层 — 原生 3D 力导向（x/y/z 对等）
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
    spreadFactor: 0.42,
    groupSpacing: 260,
  };

  function nodeIndex(nodes) {
    const map = new Map();
    nodes.forEach((n, i) => map.set(n.id, i));
    return map;
  }

  function spreadRadiusForCount(n, spreadFactor) {
    const sf = spreadFactor || DEFAULTS.spreadFactor;
    return Math.max(72, Math.cbrt(Math.max(1, n)) * 140 * sf);
  }

  /** Fibonacci 球面均匀初始分布 */
  function initialPositions3D(nodes, radius) {
    const n = nodes.length;
    if (!n) return [];
    const golden = Math.PI * (3 - Math.sqrt(5));
    return nodes.map((node, i) => {
      const t = n > 1 ? i / (n - 1) : 0.5;
      const y = 1 - t * 2;
      const ring = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i;
      const jitter = 1 + (Math.random() - 0.5) * 0.08;
      const r = radius * jitter;
      return {
        ...node,
        x: Math.cos(theta) * ring * r,
        y: y * r,
        z: Math.sin(theta) * ring * r,
        vx: 0,
        vy: 0,
        vz: 0,
        pinned: false,
      };
    });
  }

  function initialPositionsForGroups(allNodes, groupsMeta, spreadFactor, groupSpacing) {
    const nodeById = new Map(allNodes.map((n) => [n.id, n]));
    const groupList = groupsMeta?.groups || [];
    if (!groupList.length) {
      return initialPositions3D(allNodes, spreadRadiusForCount(allNodes.length, spreadFactor));
    }
    const cols = Math.max(1, Math.ceil(Math.sqrt(groupList.length)));
    const rows = Math.ceil(groupList.length / cols);
    const spacing = groupSpacing || DEFAULTS.groupSpacing;
    const out = [];

    groupList.forEach((g, gi) => {
      const subset = g.nodeIds.map((id) => nodeById.get(id)).filter(Boolean);
      if (!subset.length) return;
      const radius = spreadRadiusForCount(subset.length, spreadFactor);
      const local = initialPositions3D(subset, radius);
      const col = gi % cols;
      const row = Math.floor(gi / cols);
      const ox = (col - (cols - 1) / 2) * spacing;
      const oy = (row - (rows - 1) / 2) * spacing;
      const oz = 0;
      for (const n of local) {
        n.x += ox;
        n.y += oy;
        n.z += oz;
        n.groupId = g.id;
        n.groupOx = ox;
        n.groupOy = oy;
        n.groupOz = oz;
        out.push(n);
      }
    });

    return out;
  }

  class MemoriaGraphLayout3D {
    constructor(options = {}) {
      this.opts = { ...DEFAULTS, ...options };
      this.nodes = [];
      this.simLinks = [];
      this.alpha = 1;
      this.running = false;
      this.raf = null;
      this._listeners = Object.create(null);
      this._dragId = null;
    }

    on(event, fn) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(fn);
      return () => this.off(event, fn);
    }

    off(event, fn) {
      const list = this._listeners[event];
      if (!list) return;
      const i = list.indexOf(fn);
      if (i >= 0) list.splice(i, 1);
    }

    _emit(event, payload) {
      for (const fn of this._listeners[event] || []) {
        try {
          fn(payload);
        } catch (err) {
          console.error("[GraphLayout3D]", event, err);
        }
      }
    }

    applyOptions(partial, opts = {}) {
      Object.assign(this.opts, partial || {});
      if (opts.relayout && this._engineNodes?.length) {
        this.loadFromEngine(this._engineNodes, this._engineLinks, this._lastLoadOpts || {});
      }
    }

    getNode(id) {
      return this.nodes.find((n) => n.id === id) || null;
    }

    loadFromEngine(engineOrNodes, linksOrOpts, maybeOpts) {
      let nodes;
      let links;
      let opts = {};
      if (engineOrNodes && engineOrNodes.nodes) {
        nodes = engineOrNodes.nodes;
        links = engineOrNodes.links;
        opts = linksOrOpts || {};
      } else {
        nodes = engineOrNodes || [];
        links = linksOrOpts || [];
        opts = maybeOpts || {};
      }
      this._engineNodes = nodes;
      this._engineLinks = links;
      this._lastLoadOpts = { ...opts };
      this._groupMode =
        opts.groupId === global.MemoriaGraphGroups?.ALL_GROUP_ID || !opts.groupId
          ? "all"
          : "single";

      let layoutNodes = nodes;
      let layoutLinks = links;
      if (
        opts.groupId &&
        opts.groupId !== global.MemoriaGraphGroups?.ALL_GROUP_ID &&
        global.MemoriaGraphGroups
      ) {
        const filtered = global.MemoriaGraphGroups.filterGraphByGroup(
          nodes,
          links,
          opts.groups,
          opts.groupId
        );
        layoutNodes = filtered.nodes;
        layoutLinks = filtered.links;
        this._groupMode = "single";
      }

      const sf = opts.spreadFactor ?? this.opts.spreadFactor;
      if (this._groupMode === "all" && opts.groups?.groups?.length) {
        this.nodes = initialPositionsForGroups(
          layoutNodes,
          opts.groups,
          sf,
          opts.groupSpacing ?? this.opts.groupSpacing
        );
      } else {
        const radius = spreadRadiusForCount(layoutNodes.length, sf);
        this.nodes = initialPositions3D(layoutNodes, radius);
      }

      const idx = nodeIndex(this.nodes);
      this.simLinks = (layoutLinks || [])
        .map((l) => {
          const si = idx.get(l.source);
          const ti = idx.get(l.target);
          if (si == null || ti == null) return null;
          const rel = Number(l.relevance);
          const strengthScale = Number.isFinite(rel) ? 0.55 + rel * 0.9 : 1;
          return {
            ...l,
            sourceIndex: si,
            targetIndex: ti,
            strengthScale,
          };
        })
        .filter(Boolean);
      this.alpha = 1;
      if (this._shouldUseWorker?.() && this._syncWorkerLoad?.()) {
        /* worker warmup + reset on ready */
      } else {
        this._warmup();
        this.alpha = this._simOpts().alphaTarget;
        this._emit("reset", { nodes: this.nodes, links: this.simLinks });
      }
      return this;
    }

    _simOpts() {
      return { ...this.opts, groupMode: this._groupMode || "single" };
    }

    _warmup() {
      const Sim = global.MemoriaGraphLayoutSim;
      if (Sim) {
        Sim.warmup(
          { nodes: this.nodes, simLinks: this.simLinks, alpha: this.alpha, dragId: this._dragId },
          this._simOpts(),
          "3d"
        );
        return;
      }
      const ticks = this.opts.warmupTicks;
      this.alpha = 1;
      for (let i = 0; i < ticks; i++) {
        this.tick(1 - i / ticks);
      }
    }

    reheat(amount = 0.25) {
      this.alpha = Math.max(this.alpha, amount);
    }

    setDragNode(id) {
      const prev = this._dragId;
      this._dragId = id || null;
      if (id) this.reheat(this.opts.dragReheat ?? 0.28);
      else if (prev) this.reheat(this.opts.dragReleaseReheat ?? 0.2);
    }

    /** 3D 拖拽：改 x/y/z */
    moveDragNode3D(x, y, z) {
      const n = this.getNode(this._dragId);
      if (!n) return;
      n.x = x;
      n.y = y;
      n.z = z;
      n.vx = 0;
      n.vy = 0;
      n.vz = 0;
    }

    tick(alphaOverride) {
      if (this._workerActive) return;
      const Sim = global.MemoriaGraphLayoutSim;
      if (Sim) {
        const st = {
          nodes: this.nodes,
          simLinks: this.simLinks,
          alpha: this.alpha,
          dragId: this._dragId,
        };
        Sim.tick3D(st, this._simOpts(), alphaOverride);
        this.alpha = st.alpha;
        return;
      }
      const { nodes, simLinks: links } = this;
      const n = nodes.length;
      const alpha = alphaOverride != null ? alphaOverride : this.alpha;
      const repBase = this.opts.repulsion * (1 + Math.sqrt(n) * 0.15);
      const rep = repBase * alpha;
      const center = this.opts.centerStrength * alpha;

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
          if (
            nodes[i].groupId &&
            nodes[j].groupId &&
            nodes[i].groupId !== nodes[j].groupId
          ) {
            continue;
          }
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
        const str =
          this.opts.linkStrength * alpha * (link.strengthScale || 1);
        const force = ((dist - this.opts.linkDistance) / dist) * str;
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

      const dragId = this._dragId;
      for (const node of nodes) {
        if (node.id === dragId) continue;
        node.vx *= this.opts.velocityDecay;
        node.vy *= this.opts.velocityDecay;
        node.vz *= this.opts.velocityDecay;
        node.x += node.vx;
        node.y += node.vy;
        node.z += node.vz;
      }

      if (alphaOverride == null) {
        const decay = this.opts.alphaDecay ?? 0.045;
        this.alpha += (this.opts.alphaMin - this.alpha) * decay;
      }
    }

    start() {
      if (this.running) return;
      this.running = true;
      const frame = () => {
        if (!this.running) return;
        for (let i = 0; i < this.opts.maxTicksPerFrame; i++) {
          this.tick();
        }
        this._emit("tick", { nodes: this.nodes, alpha: this.alpha });
        this.raf = requestAnimationFrame(frame);
      };
      this.raf = requestAnimationFrame(frame);
    }

    stop() {
      this.running = false;
      if (this.raf) cancelAnimationFrame(this.raf);
      this.raf = null;
    }

    bounds3D() {
      let minX = Infinity;
      let minY = Infinity;
      let minZ = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      let maxZ = -Infinity;
      for (const n of this.nodes) {
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        minZ = Math.min(minZ, n.z);
        maxX = Math.max(maxX, n.x);
        maxY = Math.max(maxY, n.y);
        maxZ = Math.max(maxZ, n.z);
      }
      return {
        minX,
        minY,
        minZ,
        maxX,
        maxY,
        maxZ,
        cx: (minX + maxX) / 2,
        cy: (minY + maxY) / 2,
        cz: (minZ + maxZ) / 2,
      };
    }
  }

  global.MemoriaGraphLayout3D = MemoriaGraphLayout3D;
})(typeof window !== "undefined" ? window : globalThis);
