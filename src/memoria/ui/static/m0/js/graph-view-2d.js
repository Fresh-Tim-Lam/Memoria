/**
 * GraphEngine 2D Canvas 视图：MemoriaGraphLayout2D + 平移缩放 + 有向边
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    labelMode: "name_short",
    labelMaxLen: 8,
    nodeRadius: 6,
    arrowSize: 7,
  };

  function displayLabelForNode(n, opts) {
    if (window.MemoriaGraphLabels) {
      return MemoriaGraphLabels.resolveNodeDisplayLabel(n, {
        labelMode: opts.labelMode,
        labelMaxLen: opts.labelMaxLen,
      });
    }
    const s = String(n.name || n.label || n.id || "").trim();
    const max = opts.labelMaxLen || 8;
    if (s.length <= max) return s;
    return s.slice(0, Math.max(1, max - 1)) + "…";
  }

  function drawDirectedEdge(ctx, sx, sy, tx, ty, nodeRadius, color, lineWidth, alpha, arrowSize) {
    const dx = tx - sx;
    const dy = ty - sy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 1) return;
    const ux = dx / dist;
    const uy = dy / dist;
    const pad = nodeRadius + 3;
    const head = arrowSize;
    const x1 = sx + ux * pad;
    const y1 = sy + uy * pad;
    const tipX = tx - ux * pad;
    const tipY = ty - uy * pad;
    const x2 = tipX - ux * head;
    const y2 = tipY - uy * head;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";

    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();

    const angle = Math.atan2(dy, dx);
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(
      tipX - head * Math.cos(angle - Math.PI / 7),
      tipY - head * Math.sin(angle - Math.PI / 7)
    );
    ctx.lineTo(
      tipX - head * 0.72 * Math.cos(angle),
      tipY - head * 0.72 * Math.sin(angle)
    );
    ctx.lineTo(
      tipX - head * Math.cos(angle + Math.PI / 7),
      tipY - head * Math.sin(angle + Math.PI / 7)
    );
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawNodeLabel(ctx, n, r, opts, isHover, isTarget) {
    const text = displayLabelForNode(n, opts);
    const fontSize = 10;
    const ly = n.y + r + 4;
    ctx.font = `${fontSize}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.lineWidth = 3;
    ctx.strokeStyle = "rgba(13, 17, 23, 0.92)";
    ctx.strokeText(text, n.x, ly);
    if (isHover) ctx.fillStyle = "#f0f6fc";
    else if (isTarget) ctx.fillStyle = "#79c0ff";
    else if (n.range_ok === false) ctx.fillStyle = "#6e7681";
    else ctx.fillStyle = "#adbac7";
    ctx.fillText(text, n.x, ly);
  }

  class GraphView2D {
    constructor(container, engine, layout, options = {}) {
      this.container = container;
      this.engine = engine;
      this.layout = layout;
      this.opts = { ...DEFAULTS, ...options };
      this.canvas = document.createElement("canvas");
      this.canvas.className = "m0-graph-canvas";
      this.ctx = this.canvas.getContext("2d");
      container.innerHTML = "";
      container.appendChild(this.canvas);

      this.active = false;
      this.transform = { x: 0, y: 0, k: 1 };
      this.hoverId = null;
      this.remoteHoverId = null;
      this.externalFocus = null;
      this.dragging = false;
      this.dragNode = null;
      this._dragPendingNode = null;
      this.lastPointer = { x: 0, y: 0 };
      this._resizeObs = null;
      this._pendingRelayout = false;
      this._userView = false;

      this._onEngineLoad = () => this.resetSimulation();
      this._onLayoutTick = () => {
        if (this.active) this.draw();
      };
      this._onLayoutReset = () => {
        if (!this._userView) this.fitToView();
        if (this.active) this.draw();
      };

      engine.on("load", this._onEngineLoad);
      layout.on("tick", this._onLayoutTick);
      layout.on("reset", this._onLayoutReset);

      this._bindPointer();
      this._observeResize();
      this.resetSimulation();
    }

    destroy() {
      this.active = false;
      this.engine.off("load", this._onEngineLoad);
      this.layout.off("tick", this._onLayoutTick);
      this.layout.off("reset", this._onLayoutReset);
      if (this._resizeObs) this._resizeObs.disconnect();
      this.canvas.replaceWith(document.createElement("div"));
    }

    get simNodes() {
      return this.layout.nodes;
    }

    get simLinks() {
      return this.layout.simLinks;
    }

    _isPanelVisible() {
      return this.container.clientWidth > 10 && this.container.clientHeight > 10;
    }

    _observeResize() {
      this._lastFit = { w: 0, h: 0 };
      const ro = new ResizeObserver(() => {
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        if (w === this._lastFit.w && h === this._lastFit.h) return;
        if (h <= 0 || w <= 0) return;
        this._lastFit = { w, h };
        this._fitCanvas();
        if (this._pendingRelayout && this._isPanelVisible()) {
          this.resetSimulation();
        } else if (this.simNodes.length) {
          this.draw();
        }
      });
      ro.observe(this.container);
      this._resizeObs = ro;
      this._fitCanvas();
    }

    _fitCanvas() {
      const w = Math.max(1, Math.floor(this.container.clientWidth));
      const h = Math.max(1, Math.floor(this.container.clientHeight));
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = Math.floor(w * dpr);
      this.canvas.height = Math.floor(h * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.viewW = w;
      this.viewH = h;
    }

    fitToView(padding = 36) {
      const w = this.viewW || 200;
      const h = this.viewH || 200;
      if (!this.simNodes.length) {
        this.transform = { x: w / 2, y: h / 2, k: 1 };
        return;
      }
      const b = this.layout.bounds2D();
      const bw = Math.max(b.maxX - b.minX, 40);
      const bh = Math.max(b.maxY - b.minY, 40);
      const k = Math.min((w - padding * 2) / bw, (h - padding * 2) / bh, 2.5);
      this.transform = {
        x: w / 2 - b.cx * k,
        y: h / 2 - b.cy * k,
        k: Math.max(this.opts.zoomMin2d ?? 0.05, k),
      };
    }

    onPanelShown() {
      this._fitCanvas();
      if (this._pendingRelayout || !this.simNodes.length) {
        this.resetSimulation();
        return;
      }
      this.draw();
    }

    _markUserView() {
      this._userView = true;
    }

    resetSimulation() {
      this._fitCanvas();
      if (!this._isPanelVisible()) {
        this._pendingRelayout = true;
        return;
      }
      this._pendingRelayout = false;
      this._userView = false;
      const groupId =
        global.MemoriaGraphShell?.getGraphGroupId?.() ??
        global.MemoriaGraphGroups?.ALL_GROUP_ID ??
        "all";
      const loadOpts = global.MemoriaGraphGroups?.buildLayoutLoadOpts
        ? global.MemoriaGraphGroups.buildLayoutLoadOpts(this.engine, this.opts, groupId)
        : { spreadFactor: this.opts.spreadFactor };
      this.layout.loadFromEngine(this.engine, loadOpts);
      this.layout.applyOptions(this._layoutOptsFromView(), { relayout: false });
      this.fitToView();
      this.draw();
    }

    _layoutOptsFromView() {
      return {
        linkDistance: this.opts.linkDistance,
        linkStrength: this.opts.linkStrength,
        repulsion: this.opts.repulsion,
        centerStrength: this.opts.centerStrength,
        velocityDecay: this.opts.velocityDecay,
        warmupTicks: this.opts.warmupTicks,
        spreadFactor: this.opts.spreadFactor,
        alphaMin: this.opts.alphaMin,
        alphaDecay: this.opts.alphaDecay,
        alphaTarget: this.opts.alphaTarget,
        dragReheat: this.opts.dragReheat,
        dragReleaseReheat: this.opts.dragReleaseReheat,
      };
    }

    applyOptions(partial, opts = {}) {
      Object.assign(this.opts, partial || {});
      const zMin = this.opts.zoomMin2d ?? 0.05;
      const zMax = this.opts.zoomMax2d ?? 8;
      this.transform.k = Math.max(zMin, Math.min(zMax, this.transform.k));
      this.layout.applyOptions(this._layoutOptsFromView(), opts);
      if (!opts.relayout) this.draw();
    }

    reflow() {
      this._lastFit = { w: 0, h: 0 };
      this._fitCanvas();
      this.draw();
    }

    start() {
      this.active = true;
      this.layout._ensureSimulationRunning?.();
      this.draw();
    }

    stop() {
      this.active = false;
      this._cancelDrag();
    }

    _cancelDrag() {
      if (this.dragNode || this._dragPendingNode) {
        this.layout.setDragNode(null);
      }
      this.dragging = false;
      this.dragNode = null;
      this._dragPendingNode = null;
    }

    _dragMoved(e) {
      const start = this._dragStart || this.lastPointer;
      return (
        Math.abs(e.clientX - start.x) > 4 || Math.abs(e.clientY - start.y) > 4
      );
    }

    _activateNodeDrag(nodeId) {
      if (!nodeId || this.dragNode) return;
      this.dragNode = this.layout.getNode(nodeId) || { id: nodeId };
      this.layout.setDragNode(nodeId);
    }

    setExternalFocus({ sourceIds = [], targetIds = [] } = {}) {
      const inLayout = new Set(this.simNodes.map((n) => n.id));
      const s = new Set((sourceIds || []).filter((id) => inLayout.has(id)));
      const t = new Set((targetIds || []).filter((id) => inLayout.has(id)));
      this.externalFocus = s.size || t.size ? { sourceIds: s, targetIds: t } : null;
      if (this.active) this.draw();
    }

    clearExternalFocus() {
      if (!this.externalFocus) return;
      this.externalFocus = null;
      if (this.active) this.draw();
    }

    _focusHoverId() {
      const remote = this.remoteHoverId;
      if (remote && !this.simNodes.some((n) => n.id === remote)) {
        return this.hoverId;
      }
      return remote || this.hoverId;
    }

    setRemoteHover(nodeId) {
      const id = nodeId || null;
      if (this.remoteHoverId === id) return;
      this.remoteHoverId = id;
      if (this.active) this.draw();
    }

    clearRemoteHover() {
      if (!this.remoteHoverId) return;
      this.remoteHoverId = null;
      if (this.active) this.draw();
    }

    _screenToWorld(sx, sy) {
      const { x, y, k } = this.transform;
      return { x: (sx - x) / k, y: (sy - y) / k };
    }

    _pickNode(sx, sy) {
      const { x, y } = this._screenToWorld(sx, sy);
      const r = this.opts.nodeRadius + 6;
      let best = null;
      let bestD = r * r;
      for (const n of this.simNodes) {
        const dx = n.x - x;
        const dy = n.y - y;
        const d2 = dx * dx + dy * dy;
        if (d2 <= bestD) {
          bestD = d2;
          best = n;
        }
      }
      return best;
    }

    _bindPointer() {
      this.canvas.addEventListener(
        "wheel",
        (e) => {
          e.preventDefault();
          const rect = this.canvas.getBoundingClientRect();
          const sx = e.clientX - rect.left;
          const sy = e.clientY - rect.top;
          const sens = this.opts.zoomSensitivity2d ?? 1.0;
          const base = e.deltaY > 0 ? 0.9 : 1.1;
          const factor = sens !== 1 ? Math.pow(base, sens) : base;
          const k0 = this.transform.k;
          const zMin = this.opts.zoomMin2d ?? 0.05;
          const zMax = this.opts.zoomMax2d ?? 8;
          const k1 = Math.max(zMin, Math.min(zMax, k0 * factor));
          this.transform.x = sx - ((sx - this.transform.x) / k0) * k1;
          this.transform.y = sy - ((sy - this.transform.y) / k0) * k1;
          this.transform.k = k1;
          this._markUserView();
          if (this.active) this.draw();
        },
        { passive: false }
      );

      this.canvas.addEventListener("pointerdown", (e) => {
        const rect = this.canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const node = this._pickNode(sx, sy);
        this._dragStart = { x: e.clientX, y: e.clientY };
        this.lastPointer = { x: e.clientX, y: e.clientY };
        this.dragging = true;
        this.dragNode = null;
        this._dragPendingNode = node || null;
        this.canvas.setPointerCapture(e.pointerId);
      });

      this.canvas.addEventListener("pointermove", (e) => {
        const rect = this.canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        if (this.dragging) {
          if (this._dragPendingNode && !this.dragNode && this._dragMoved(e)) {
            this._activateNodeDrag(this._dragPendingNode.id);
          }
          const dx = e.clientX - this.lastPointer.x;
          const dy = e.clientY - this.lastPointer.y;
          this.lastPointer = { x: e.clientX, y: e.clientY };
          if (this.dragNode) {
            const w = this._screenToWorld(sx, sy);
            this.layout.moveDragNode2D(w.x, w.y);
          } else {
            this.transform.x += dx;
            this.transform.y += dy;
            this._markUserView();
          }
          if (this.active) this.draw();
          return;
        }
        const hit = this._pickNode(sx, sy);
        if (!this.remoteHoverId) {
          const next = hit ? hit.id : null;
          if (next !== this.hoverId) {
            this.hoverId = next;
            this.engine._emit("hover", { node: hit ? this.engine.getNode(hit.id) : null });
          }
        }
        this.canvas.style.cursor = hit || this.remoteHoverId ? "pointer" : "grab";
      });

      this.canvas.addEventListener("pointerup", (e) => {
        const rect = this.canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const pending = this._dragPendingNode;
        const moved = this._dragMoved(e);
        const wasNode = this.dragNode || pending;
        this._cancelDrag();
        try {
          this.canvas.releasePointerCapture(e.pointerId);
        } catch (_) {
          /* ignore */
        }
        if (pending && !moved) {
          this.engine._emit("nodeClick", { node: this.engine.getNode(pending.id) });
        }
        if (!this.remoteHoverId) {
          const hit = this._pickNode(sx, sy);
          const next = hit ? hit.id : null;
          if (next !== this.hoverId) {
            this.hoverId = next;
            this.engine._emit("hover", { node: hit ? this.engine.getNode(hit.id) : null });
          }
        }
        if (this.active) this.draw();
      });

      this.canvas.addEventListener("pointerleave", () => {
        if (this.remoteHoverId) return;
        if (this.hoverId) {
          this.hoverId = null;
          this.engine._emit("hover", { node: null });
        }
      });
    }

    draw() {
      if (!this.active) return;
      const ctx = this.ctx;
      const w = this.viewW || 1;
      const h = this.viewH || 1;
      const opts = this.opts;
      ctx.save();
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = getComputedStyle(this.container).backgroundColor || "#161b22";
      ctx.fillRect(0, 0, w, h);

      ctx.translate(this.transform.x, this.transform.y);
      ctx.scale(this.transform.k, this.transform.k);

      const hover = this._focusHoverId();
      const ext = this.externalFocus;
      const extActive = !!(ext && (ext.sourceIds.size || ext.targetIds.size));
      const outLinks = hover
        ? new Set(this.engine.getOutgoingLinks(hover).map((l) => l.target))
        : null;

      for (const link of this.simLinks) {
        const s = this.simNodes[link.sourceIndex];
        const t = this.simNodes[link.targetIndex];
        if (!s || !t) continue;
        let active = false;
        if (hover) {
          active = link.source === hover || link.target === hover;
        } else if (extActive) {
          active = ext.sourceIds.has(link.source) && ext.targetIds.has(link.target);
        }
        const padR = opts.nodeRadius + (active ? 2 : 0);
        let alpha = 0.45;
        if (active) alpha = 0.95;
        else if (extActive || hover) alpha = 0.14;
        drawDirectedEdge(
          ctx,
          s.x,
          s.y,
          t.x,
          t.y,
          padR,
          this.engine.edgeColor(link.type),
          active ? 2.2 : 1.2,
          alpha,
          opts.arrowSize
        );
      }

      for (const n of this.simNodes) {
        const isHover = n.id === hover;
        const isExtSource = extActive && ext.sourceIds.has(n.id);
        const isExtTarget = extActive && ext.targetIds.has(n.id);
        const isTarget = (outLinks && outLinks.has(n.id)) || isExtTarget;
        const isFocus = isHover || isExtSource || isExtTarget;
        const r = opts.nodeRadius + (isHover || isExtSource ? 3 : isExtTarget ? 2 : 0);
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        if (isHover || isExtSource) ctx.fillStyle = "#f0f6fc";
        else if (isTarget) ctx.fillStyle = "#79c0ff";
        else if (extActive || hover) ctx.fillStyle = "#484f58";
        else if (n.range_ok === false) ctx.fillStyle = "#8b949e";
        else ctx.fillStyle = "#c9d1d9";
        ctx.fill();
        if (isFocus) {
          ctx.strokeStyle = isExtSource || isExtTarget ? "#a371f7" : "#58a6ff";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        drawNodeLabel(ctx, n, r, opts, isHover || isExtSource, isTarget);
      }

      ctx.restore();
    }
  }

  global.MemoriaGraphView2D = GraphView2D;
})(typeof window !== "undefined" ? window : globalThis);
