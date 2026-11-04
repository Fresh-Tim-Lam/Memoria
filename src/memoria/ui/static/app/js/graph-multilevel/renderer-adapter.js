/**
 * Memoria 多层次图谱 B4 —— I-07 `RendererAdapter`（S3 渲染接口；**仅 2D 实现**）。
 *
 * 冻结依据：
 *   - S3-6：`Renderer{getCapabilities(), render(container, vm), update(vm, opts), dispose(), on(event)}`；
 *     2D/3D 同签名；纯 VM 输入；不取数/不裁剪/不算 presence/不重算簇。
 *   - S3-5：只画 `presence=shown` 的边/节点；suppressed/unknown 无视觉（禁幽灵边）。
 *   - S3-11 / S8-4 冻结预算：`max_nodes=200`、`max_edges=400`、动画 ≤180ms；
 *     VM 超硬上限 ⇒ `RENDER_BUDGET_EXCEEDED` fail-visible（Renderer 不静默裁剪）。
 *   - S3-ADDENDUM-1/2：节点/边 `presence?/rule_id?` 只作为 view-status；`data_edge_ids` Renderer 禁读。
 *   - S3-2/S3-3：cluster 半径 `clamp(8+2.2·log2(member_count+1),12,28)`；KP **固定半径 8px**（screen-space）。
 *   - B4 工程口径：**只做 2D**；3D 仅同签名接口 + `capability=false`，不实现、不阻断。
 *
 * 复用：布局种子/会话内保位沿用 KGviz v0 的确定性思路（本模块自含确定性布局；
 * 旧 force 布局与旧视图仍在 legacy 入口保留）；标签 LOD/避让复用 `MemoriaGraphLabels.layoutNodeLabels`。
 */
(function (global) {
  "use strict";

  const Canonical = global.MemoriaGraphCanonical || (typeof require === "function" ? require("./canonical.js") : null);

  const MAX_NODES = 200;
  const MAX_EDGES = 400;
  const ANIMATION_MAX_MS = 180;
  const KP_RADIUS = 8;
  const CLUSTER_MIN_RADIUS = 12;
  const CLUSTER_MAX_RADIUS = 28;
  const TAU = Math.PI * 2;
  const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

  const MAIN_STATES = ["Idle", "Loading", "Degraded"]; // 仅用于说明本模块不持有导航态
  void MAIN_STATES;

  const VM_TOP_FIELDS = Object.freeze([
    "view_model_id", "level_id", "level_label", "dimension_id", "view_family_id", "nodes", "edges",
  ]);
  const NODE_REQUIRED = Object.freeze(["id", "kind", "label", "role"]);
  const NODE_KINDS = Object.freeze(["kp", "cluster"]);
  const NODE_ROLES = Object.freeze(["member"]);
  const PRESENCE_VALUES = Object.freeze(["shown", "suppressed", "unknown"]);
  const EDGE_REQUIRED = Object.freeze(["id", "type"]);
  const VM_FORBIDDEN_TOP = Object.freeze([
    "frame_id", "edition", "edition_sha", "mode", "focus", "selection", "history",
    "capabilities", "clusters", "run_id", "dendrogram", "metrics", "candidates",
  ]);
  const EDGE_COLORS = Object.freeze({
    semantic: "#e06c75",
    structural: "#61afef",
    navigation: "#e5c07b",
    reference: "#8b949e",
    extend: "#c678dd",
    contain: "#61afef",
  });
  const EVENT_TYPES = Object.freeze(["nodeClick", "edgeClick", "backgroundClick", "hover"]);

  class RendererError extends Error {
    constructor(code, message, detail) {
      super(message || code);
      this.name = "RendererError";
      this.code = code;
      this.detail = detail || null;
    }
  }

  function fail(code, message, detail) {
    throw new RendererError(code, message, detail);
  }

  function fnv1a(text) {
    let hash = 0x811c9dc5;
    const s = String(text);
    for (let i = 0; i < s.length; i++) {
      hash ^= s.charCodeAt(i);
      hash = (hash * 0x01000193) >>> 0;
    }
    return hash >>> 0;
  }

  function clusterRadius(memberCount) {
    const n = Math.max(0, Number(memberCount) || 0);
    return Math.min(CLUSTER_MAX_RADIUS, Math.max(CLUSTER_MIN_RADIUS, 8 + 2.2 * Math.log2(n + 1)));
  }

  function nodeRadius(node) {
    if (node.kind === "cluster") return clusterRadius(node.member_count || node.aggregate_count || 1);
    return KP_RADIUS; // KP 固定 8px screen-space（R-S3-7）
  }

  function labelText(node) {
    return String(node.label == null ? node.id : node.label);
  }

  function assertVm(vm) {
    if (!vm || typeof vm !== "object" || Array.isArray(vm)) fail("GRAPH_PRESENCE_INVALID", "VM 必须是对象");
    const leaks = VM_FORBIDDEN_TOP.filter((k) => k in vm);
    if (leaks.length) fail("GRAPH_PRESENCE_INVALID", `VM 含禁入字段（Renderer 不消费导航/簇内部）：${leaks.join(",")}`);
    if (!Array.isArray(vm.nodes) || !Array.isArray(vm.edges)) {
      fail("GRAPH_PRESENCE_INVALID", "VM.nodes/edges 必须是数组");
    }
    for (const node of vm.nodes) {
      for (const f of NODE_REQUIRED) if (!(f in node)) fail("GRAPH_PRESENCE_INVALID", `VM 节点缺必填 ${f}`);
      if (!NODE_KINDS.includes(node.kind)) fail("GRAPH_PRESENCE_INVALID", `VM 节点 kind 非法：${node.kind}`);
      if (!NODE_ROLES.includes(node.role)) fail("GRAPH_PRESENCE_INVALID", `VM 节点 role 非法：${node.role}（v1 只有 member）`);
      if ("presence" in node && !PRESENCE_VALUES.includes(node.presence)) {
        fail("GRAPH_PRESENCE_INVALID", `VM 节点 presence 非法：${node.presence}`);
      }
      if (node.presence && node.presence !== "shown" && !node.rule_id) {
        fail("GRAPH_PRESENCE_INVALID", "VM non-shown 节点缺 rule_id（X-RULE fail-closed）");
      }
      if ("layout_group" in node) {
        if (node.kind === "cluster") fail("GRAPH_PRESENCE_INVALID", "layout_group 不得用于 cluster");
        if (!node.layout_group || node.layout_group.semantic !== false) {
          fail("GRAPH_PRESENCE_INVALID", "layout_group.semantic 必须 false");
        }
      }
    }
    for (const edge of vm.edges) {
      for (const f of EDGE_REQUIRED) if (!(f in edge)) fail("GRAPH_PRESENCE_INVALID", `VM 边缺必填 ${f}`);
      if ("presence" in edge && !PRESENCE_VALUES.includes(edge.presence)) {
        fail("GRAPH_PRESENCE_INVALID", `VM 边 presence 非法：${edge.presence}`);
      }
      if (edge.presence && edge.presence !== "shown" && !edge.rule_id) {
        fail("GRAPH_PRESENCE_INVALID", "VM non-shown 边缺 rule_id（S3-ADDENDUM-2 fail-closed）");
      }
    }
    return vm;
  }

  function shownModel(vm) {
    return {
      nodes: vm.nodes.filter((n) => !n.presence || n.presence === "shown"),
      edges: vm.edges.filter((e) => !e.presence || e.presence === "shown"),
    };
  }

  function assertBudget(vm) {
    if (vm.nodes.length > MAX_NODES || vm.edges.length > MAX_EDGES) {
      fail(
        "RENDER_BUDGET_EXCEEDED",
        `VM 超硬上限：nodes=${vm.nodes.length}/${MAX_NODES}, edges=${vm.edges.length}/${MAX_EDGES}（Renderer 不裁剪）`,
        { nodes: vm.nodes.length, edges: vm.edges.length, max_nodes: MAX_NODES, max_edges: MAX_EDGES }
      );
    }
  }

  // ── 确定性布局（种子来自 VM id；update 保位、不 reheat）────────────────────
  function computeLayout(vm, seed, width, height, prevPositions) {
    const shown = shownModel(vm);
    const ids = shown.nodes.map((n) => n.id).sort();
    const positions = new Map();
    const radiusById = new Map(shown.nodes.map((n) => [n.id, nodeRadius(n)]));
    const maxR = ids.reduce((m, id) => Math.max(m, radiusById.get(id) || KP_RADIUS), KP_RADIUS);
    const cx = width / 2;
    const cy = height / 2;
    const count = Math.max(1, ids.length);
    const spread = Math.max(60, Math.min(width, height) / 2 - maxR - 24);
    const angleOffset = ((seed >>> 0) % 1000) / 1000 * TAU;
    ids.forEach((id, index) => {
      if (prevPositions && prevPositions.has(id)) {
        positions.set(id, { ...prevPositions.get(id) });
        return;
      }
      const t = (index + 1) / count;
      const r = spread * Math.sqrt(t) * 0.92;
      const angle = angleOffset + index * GOLDEN_ANGLE;
      positions.set(id, { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r });
    });
    return { positions, radiusById, shown, width, height };
  }

  function defaultHost(doc) {
    return {
      createCanvas(width, height) {
        const canvas = doc.createElement("canvas");
        canvas.width = Math.max(1, Math.round(width));
        canvas.height = Math.max(1, Math.round(height));
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", "多层次图谱（2D）");
        const ctx = canvas.getContext("2d");
        return { canvas, ctx };
      },
      append(container, canvas) {
        if (container && typeof container.appendChild === "function") container.appendChild(canvas);
      },
      remove(container, canvas) {
        if (container && typeof container.removeChild === "function" && canvas.parentNode === container) {
          try { container.removeChild(canvas); } catch (_) { /* noop */ }
        }
      },
      on(canvas, type, handler) {
        if (canvas && typeof canvas.addEventListener === "function") canvas.addEventListener(type, handler);
      },
      off(canvas, type, handler) {
        if (canvas && typeof canvas.removeEventListener === "function") canvas.removeEventListener(type, handler);
      },
      rect(canvas) {
        if (canvas && typeof canvas.getBoundingClientRect === "function") return canvas.getBoundingClientRect();
        return { left: 0, top: 0, width: canvas.width, height: canvas.height };
      },
      dpr() {
        return Math.min(2, Number(global.devicePixelRatio) || 1);
      },
    };
  }

  class Renderer2D {
    constructor(container, options = {}) {
      this.backend = "2d";
      this.container = container || null;
      this.options = options || {};
      this.doc = options.document || global.document || null;
      this.host = options.host || (this.doc ? defaultHost(this.doc) : null);
      this._listeners = Object.create(null);
      this._canvas = null;
      this._ctx = null;
      this._positions = new Map();
      this._nodeById = new Map();
      this._edgeList = [];
      this._view = { width: 1, height: 1 };
      this._seed = Number.isFinite(options.layoutSeed) ? options.layoutSeed >>> 0 : null;
      this._hoverId = null;
      this._selection = null;
      this._disposed = false;
      this._bound = [];
      this.lastRender = null;
      this.lastError = null;
    }

    getCapabilities() {
      return {
        backend: "2d",
        capable: true,
        capability: true,
        backends: ["2d"],
        maxNodes: MAX_NODES,
        maxEdges: MAX_EDGES,
        max_nodes: MAX_NODES,
        max_edges: MAX_EDGES,
        anime_max_ms: ANIMATION_MAX_MS,
        animationMaxMs: ANIMATION_MAX_MS,
        fps: 60,
        screenSpaceSizes: true,
        labels: "lod-avoidance",
        events: EVENT_TYPES.slice(),
        reducedMotion: true,
        statusLabels: true,
      };
    }

    /** 渲染器不得读 `data_edge_ids`：输入只按白名单读取节点/边字段（源码静态检查）。 */
    _project(vm) {
      assertVm(vm);
      const nodes = vm.nodes.map((n) => ({
        id: String(n.id),
        kind: n.kind,
        label: labelText(n),
        role: n.role,
        member_count: n.member_count,
        aggregate_count: n.aggregate_count,
        representative: n.representative,
        root_exempt: n.root_exempt,
        range_ok: n.range_ok,
        layout_group: n.layout_group,
        presence: n.presence || "shown",
        rule_id: n.rule_id,
      }));
      const edges = vm.edges.map((e) => ({
        id: String(e.id),
        type: e.type,
        state: e.state,
        presence: e.presence || "shown",
        rule_id: e.rule_id,
      }));
      return { nodes, edges };
    }

    render(container, vm) {
      if (this._disposed) fail("GRAPH_INTERNAL", "Renderer 已 dispose");
      if (container) this.container = container;
      if (!this.container) fail("GRAPH_INTERNAL", "缺少容器");
      const model = this._project(vm);
      assertBudget(vm);
      const width = this._measureWidth();
      const height = this._measureHeight();
      this._ensureCanvas(width, height);
      const seed = this._seed == null ? fnv1a(vm.view_model_id || "vm") : this._seed;
      this._seed = seed;
      const layout = computeLayout({ nodes: model.nodes, edges: model.edges }, seed, width, height, null);
      this._applyLayout(layout, model);
      this._bindPointer();
      this._draw();
      return this._summary("render");
    }

    update(vm, opts) {
      opts = opts || {};
      if (this._disposed) fail("GRAPH_INTERNAL", "Renderer 已 dispose");
      const model = this._project(vm);
      assertBudget(vm);
      const keep = opts.relayout === true ? null : this._positions;
      const width = this._measureWidth();
      const height = this._measureHeight();
      this._ensureCanvas(width, height);
      const seed = this._seed == null ? fnv1a(vm.view_model_id || "vm") : this._seed;
      const layout = computeLayout({ nodes: model.nodes, edges: model.edges }, seed, width, height, keep);
      const before = new Map(this._positions);
      this._applyLayout(layout, model);
      let moved = 0;
      for (const [id, p] of this._positions) {
        const old = before.get(id);
        if (!old || old.x !== p.x || old.y !== p.y) moved += 1;
      }
      this._draw();
      const summary = this._summary("update");
      summary.moved = moved;
      summary.reheat = opts.relayout === true;
      return summary;
    }

    dispose() {
      if (this._disposed) return { status: "ok", already: true };
      for (const [target, type, handler] of this._bound) this.host && this.host.off && this.host.off(target, type, handler);
      this._bound = [];
      if (this.host && this.host.remove && this._canvas) this.host.remove(this.container, this._canvas);
      this._canvas = null;
      this._ctx = null;
      this._positions.clear();
      this._nodeById.clear();
      this._edgeList = [];
      this._disposed = true;
      return { status: "ok" };
    }

    on(type, handler) {
      if (typeof handler !== "function") throw new Error("on(type, handler) 需要函数");
      (this._listeners[type] || (this._listeners[type] = [])).push(handler);
      return () => this.off(type, handler);
    }

    off(type, handler) {
      const list = this._listeners[type];
      if (!list) return;
      const idx = list.indexOf(handler);
      if (idx >= 0) list.splice(idx, 1);
    }

    _emit(type, payload) {
      for (const fn of (this._listeners[type] || []).slice()) {
        try { fn(payload); } catch (err) { console.error("[Renderer2D]", type, err); }
      }
      for (const fn of (this._listeners["*"] || []).slice()) {
        try { fn({ type, payload }); } catch (err) { console.error("[Renderer2D]", err); }
      }
    }

    _measureWidth() {
      const c = this.container;
      return Math.max(1, Number(c?.clientWidth) || Number(c?.width) || 800);
    }

    _measureHeight() {
      const c = this.container;
      return Math.max(1, Number(c?.clientHeight) || Number(c?.height) || 600);
    }

    _ensureCanvas(width, height) {
      if (this._canvas) {
        const dpr = this.host && this.host.dpr ? this.host.dpr() : 1;
        const w = Math.max(1, Math.round(width * dpr));
        const h = Math.max(1, Math.round(height * dpr));
        if (this._canvas.width !== w) this._canvas.width = w;
        if (this._canvas.height !== h) this._canvas.height = h;
        return;
      }
      if (!this.host) fail("GRAPH_INTERNAL", "无 host（需要 document 或注入 host）");
      const dpr = this.host.dpr ? this.host.dpr() : 1;
      const made = this.host.createCanvas(width * dpr, height * dpr);
      this._canvas = made.canvas;
      this._ctx = made.ctx;
      if (this._ctx && this._ctx.setTransform) this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (this._canvas) {
        this._canvas.width = Math.max(1, Math.round(width * dpr));
        this._canvas.height = Math.max(1, Math.round(height * dpr));
      }
      if (this.host.append) this.host.append(this.container, this._canvas);
    }

    _applyLayout(layout, model) {
      this._positions = layout.positions;
      this._nodeById = new Map(model.nodes.map((n) => [n.id, n]));
      this._edgeList = model.edges.filter((e) => e.presence === "shown");
      this._radiusById = layout.radiusById;
      this._view = { width: layout.width, height: layout.height };
    }

    _bindPointer() {
      if (!this.host || !this._canvas || !this.host.on) return;
      if (this._bound.length) return;
      const move = (event) => this._onPointerMove(event);
      const click = (event) => this._onPointerClick(event);
      this.host.on(this._canvas, "pointermove", move);
      this.host.on(this._canvas, "click", click);
      this._bound.push([this._canvas, "pointermove", move], [this._canvas, "click", click]);
    }

    _point(event) {
      if (event && Number.isFinite(event.offsetX) && Number.isFinite(event.offsetY)) {
        return { x: event.offsetX, y: event.offsetY };
      }
      const rect = this.host && this.host.rect ? this.host.rect(this._canvas) : { left: 0, top: 0 };
      return { x: (event?.clientX || 0) - (rect.left || 0), y: (event?.clientY || 0) - (rect.top || 0) };
    }

    _pickNode(x, y) {
      let best = null;
      for (const [id, p] of this._positions) {
        const r = (this._radiusById && this._radiusById.get(id)) || KP_RADIUS;
        const d2 = (p.x - x) ** 2 + (p.y - y) ** 2;
        if (d2 <= r * r && (!best || d2 < best.d2)) best = { id, d2 };
      }
      return best ? this._nodeById.get(best.id) : null;
    }

    _pickEdge(x, y) {
      let best = null;
      for (const edge of this._edgeList) {
        const ends = edgeEndpoints(edge.id);
        if (!ends) continue;
        const a = this._positions.get(ends.source);
        const b = this._positions.get(ends.target);
        if (!a || !b) continue;
        const d = pointSegmentDistance(x, y, a, b);
        if (d <= 6 && (!best || d < best.d)) best = { edge, d };
      }
      return best ? best.edge : null;
    }

    _onPointerMove(event) {
      const { x, y } = this._point(event);
      const node = this._pickNode(x, y);
      const id = node ? node.id : null;
      if (id !== this._hoverId) {
        this._hoverId = id;
        this._draw();
        this._emit("hover", id ? { node_id: id, kind: node.kind } : { node_id: null, kind: null });
      }
    }

    _onPointerClick(event) {
      const { x, y } = this._point(event);
      this.handlePointClick(x, y, event?.shiftKey ? { shift: true } : {});
    }

    /** 供 host/tests 直接驱动点击（屏幕坐标）；事件 payload 白名单无导航字段。 */
    handlePointClick(x, y, extra = {}) {
      const node = this._pickNode(x, y);
      if (node) {
        const payload = { node_id: node.id, kind: node.kind, ...extra };
        this._emit("nodeClick", payload);
        return { type: "nodeClick", payload };
      }
      const edge = this._pickEdge(x, y);
      if (edge) {
        const payload = { edge_id: edge.id, ...extra };
        this._emit("edgeClick", payload);
        return { type: "edgeClick", payload };
      }
      this._emit("backgroundClick", { ...extra });
      return { type: "backgroundClick", payload: { ...extra } };
    }

    setSelection(selection) {
      this._selection = selection || null;
      if (this._active !== false) this._draw();
    }

    _draw() {
      const ctx = this._ctx;
      if (!ctx) return;
      const width = this._view.width;
      const height = this._view.height;
      const calls = { clear: 0, edges: 0, nodes: 0, labels: 0, text: 0 };
      if (ctx.setTransform && this.host && this.host.dpr) {
        const dpr = this.host.dpr();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      if (ctx.clearRect) { ctx.clearRect(0, 0, width, height); calls.clear += 1; }
      // 边：只画 shown；suppressed/unknown 无视觉
      for (const edge of this._edgeList) {
        const ends = edgeEndpoints(edge.id);
        if (!ends) continue;
        const a = this._positions.get(ends.source);
        const b = this._positions.get(ends.target);
        if (!a || !b) continue;
        const incident = this._hoverId && (ends.source === this._hoverId || ends.target === this._hoverId);
        if (ctx.beginPath) {
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = EDGE_COLORS[edge.type] || EDGE_COLORS.reference;
          ctx.globalAlpha = incident ? 0.95 : 0.5;
          ctx.lineWidth = incident ? 2.2 : 1.2;
          if (ctx.stroke) ctx.stroke();
          ctx.globalAlpha = 1;
          calls.edges += 1;
        }
      }
      // 节点：S3 token；只画 shown
      for (const node of this._nodeById.values()) {
        if (node.presence !== "shown") continue;
        const p = this._positions.get(node.id);
        if (!p) continue;
        const r = (this._radiusById && this._radiusById.get(node.id)) || nodeRadius(node);
        const hovered = this._hoverId === node.id;
        if (ctx.beginPath) {
          ctx.beginPath();
          if (ctx.arc) ctx.arc(p.x, p.y, r, 0, TAU);
          ctx.fillStyle = node.kind === "cluster" ? "#3d6ea8" : "#88a9c9";
          if (node.range_ok === false) ctx.fillStyle = "#6b6b6b";
          if (ctx.fill) ctx.fill();
          if (hovered && ctx.stroke) {
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.stroke();
          }
          if (node.kind === "cluster" && ctx.stroke) {
            ctx.strokeStyle = node.root_exempt ? "#e5c07b" : "#9cc4e6";
            ctx.lineWidth = node.root_exempt ? 2.2 : 1.2;
            if (ctx.setLineDash && node.root_exempt) ctx.setLineDash([3, 2]);
            ctx.stroke();
            if (ctx.setLineDash) ctx.setLineDash([]);
          }
          calls.nodes += 1;
        }
        if (node.kind === "cluster" && node.member_count != null && ctx.fillText) {
          ctx.fillStyle = "#ffffff";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.font = "10px system-ui, sans-serif";
          if (ctx.fillText) { ctx.fillText(String(node.member_count), p.x, p.y); calls.text += 1; }
        }
      }
      // 标签：复用旧 KGviz label LOD/避让（存在则用；否则全部显示）
      const labelItems = [];
      for (const node of this._nodeById.values()) {
        if (node.presence !== "shown") continue;
        const p = this._positions.get(node.id);
        if (!p) continue;
        labelItems.push({
          id: node.id,
          text: labelText(node),
          x: p.x,
          y: p.y + ((this._radiusById && this._radiusById.get(node.id)) || KP_RADIUS) + 4,
          r: 0,
          degree: node.kind === "cluster" ? Number(node.member_count) || 0 : 0,
        });
      }
      let visible = labelItems;
      const Labels = global.MemoriaGraphLabels;
      if (Labels && typeof Labels.layoutNodeLabels === "function") {
        const layout = Labels.layoutNodeLabels(labelItems, { topN: 10, lod: true });
        this._labelLayout = layout;
        visible = labelItems.filter((it) => layout.visibleIds.has(it.id));
      }
      if (ctx.font && ctx.fillText) {
        ctx.font = "10px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        for (const it of visible) {
          ctx.fillStyle = "#d7e3f0";
          if (ctx.fillText) { ctx.fillText(it.text, it.x, it.y); calls.labels += 1; }
        }
      }
      this.lastRender = {
        nodes: calls.nodes,
        edges: calls.edges,
        labels: calls.labels,
        texts: calls.text,
        bounded: true,
        maxNodes: MAX_NODES,
        maxEdges: MAX_EDGES,
        animationMaxMs: ANIMATION_MAX_MS,
        layoutSeed: this._seed,
        positions: this._positions.size,
        shownNodes: [...this._nodeById.values()].filter((n) => n.presence === "shown").length,
        shownEdges: this._edgeList.length,
      };
      this._drawCalls = calls;
    }

    _summary(op) {
      const base = {
        status: "ok",
        op,
        backend: this.backend,
        nodeCount: this._nodeById.size,
        edgeCount: this._edgeList.length,
        positions: this._positions.size,
        layoutSeed: this._seed,
        drawCalls: this._drawCalls || null,
        caps: this.getCapabilities(),
      };
      return base;
    }
  }

  function edgeEndpoints(edgeId) {
    // B3 视图边 id = `type|src_view|tgt_view`（S4 `_classify_edges`）；其它形态（invalid/unresolved）
    // 永不 shown，因此渲染路径只需处理 3 段 id。
    const parts = String(edgeId).split("|");
    if (parts.length < 3) return null;
    return { source: parts[1], target: parts[2] };
  }

  function pointSegmentDistance(px, py, a, b) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len2 = dx * dx + dy * dy;
    if (!len2) return Math.hypot(px - a.x, py - a.y);
    let t = ((px - a.x) * dx + (py - a.y) * dy) / len2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
  }

  /**
   * 3D：**只留同签名接口 + capability=false**（0.5 不实现 3D；不阻断 2D/旧 3D legacy 入口）。
   * `render/update` 必须 fail-visible（RENDER_UNSUPPORTED_BACKEND），而不是静默成功。
   */
  class Renderer3D {
    constructor(container, options = {}) {
      this.backend = "3d";
      this.container = container || null;
      this.options = options || {};
      this._listeners = Object.create(null);
    }

    getCapabilities() {
      return {
        backend: "3d",
        capable: false,
        capability: false,
        backends: ["3d"],
        maxNodes: MAX_NODES,
        maxEdges: MAX_EDGES,
        max_nodes: MAX_NODES,
        max_edges: MAX_EDGES,
        anime_max_ms: ANIMATION_MAX_MS,
        animationMaxMs: ANIMATION_MAX_MS,
        reason: "3D_NOT_IN_0_5",
        message: "0.5 只实现 2D；3D 仅保留同签名接口（capability=false）。旧 3D 走 legacy 入口。",
      };
    }

    render(container, vm) {
      void container;
      void vm;
      fail("RENDER_UNSUPPORTED_BACKEND", "3D 渲染未在 0.5 实现（capability=false；入口应回退 2D/legacy）");
    }

    update(vm, opts) {
      void vm;
      void opts;
      fail("RENDER_UNSUPPORTED_BACKEND", "3D 渲染未在 0.5 实现（capability=false）");
    }

    dispose() {
      return { status: "ok", already: true };
    }

    on(type, handler) {
      (this._listeners[type] || (this._listeners[type] = [])).push(handler);
      return () => this.off(type, handler);
    }

    off(type, handler) {
      const list = this._listeners[type];
      if (!list) return;
      const idx = list.indexOf(handler);
      if (idx >= 0) list.splice(idx, 1);
    }
  }

  function createRendererAdapter(backend, container, options = {}) {
    if (backend === "2d") return new Renderer2D(container, options);
    if (backend === "3d") return new Renderer3D(container, options);
    fail("GRAPH_INTERNAL", `未知渲染后端：${backend}`);
  }

  function getRendererCapabilities(backend, container, options) {
    return createRendererAdapter(backend, container, options).getCapabilities();
  }

  const api = {
    Renderer2D,
    Renderer3D,
    RendererError,
    createRendererAdapter,
    getRendererCapabilities,
    MAX_NODES,
    MAX_EDGES,
    ANIMATION_MAX_MS,
    KP_RADIUS,
    CLUSTER_MIN_RADIUS,
    CLUSTER_MAX_RADIUS,
    EVENT_TYPES,
    VM_TOP_FIELDS,
    assertVm,
    assertBudget,
    shownModel,
    clusterRadius,
    nodeRadius,
    computeLayout,
    fnv1a,
    EDGE_COLORS,
  };
  global.MemoriaGraphRendererAdapter = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
