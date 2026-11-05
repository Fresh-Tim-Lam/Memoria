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
 *   - S3-2/S3-3（视觉值由 S3-ADDENDUM-3 修订）：cluster 半径 `clamp(8+2.2·log2(member_count+1),12,28)`；
 *     KP 半径 = 旧 KGviz 连续分位映射 `radiusForDegree(degree, distinctSorted, 6)`（≈4.5–9.9px，
 *     degree 来自 Presentation 元数据、**不进 VM**）；节点/标签/边/背景/光晕取旧 KGviz 视觉值。
 *     S3-ADDENDUM-3 只改元素外观，不改 kind/presence/白名单/data_edge_ids 禁读。
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
  // S3-ADDENDUM-3 A3-1：视觉基线 = 0.4.10 旧 KGviz 2D
  const KP_BASE_RADIUS = 6;
  const SIZE_RATIO_MIN = 0.75;
  const SIZE_RATIO_MAX = 1.65;
  const HOVER_EXTRA_RADIUS = 3;
  const TARGET_EXTRA_RADIUS = 2;
  const CLUSTER_MIN_RADIUS = 12;
  const CLUSTER_MAX_RADIUS = 28;
  const TAU = Math.PI * 2;
  const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

  const VISUAL = Object.freeze({
    bg: "#0a0d13",
    containerBg: "#161b22",
    node: "#c9d1d9",
    nodeHover: "#f0f6fc",
    nodeTarget: "#79c0ff",
    nodeDim: "#3d4350",
    nodeInvalid: "#3a4152",
    nodeMuted: "#8b949e",
    label: "#adbac7",
    labelInvalid: "#6e7681",
    halo: "rgba(13,17,23,0.92)",
    focus: "#58a6ff",
    galaxyDim: "rgb(139,148,158)",
    galaxyBright: "rgb(240,246,252)",
    labelFont: "10px system-ui, sans-serif",
    labelHaloWidth: 3,
    edgeAlpha: 0.45,
    edgeAlphaActive: 0.95,
    edgeAlphaDim: 0.14,
    edgeWidth: 1.2,
    edgeWidthActive: 2.2,
    arrowSize: 7,
    glow: 0.6,
  });

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
    contain: "#3fb950",
    reference: "#58a6ff",
    extend: "#d29922",
    semantic: "#e06c75", // A3-1 additive：旧 KGviz 无此类型，唯一新增色
    structural: "#58a6ff",
    navigation: "#58a6ff",
  });
  const EVENT_TYPES = Object.freeze(["nodeClick", "edgeClick", "backgroundClick", "hover", "nodeDblClick", "groupClick"]);

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

  // ── 连续 degree 分位映射（逐字复刻旧 graph-engine.js，不改旧文件）────────────
  function sizingRangeForBase(baseRadius) {
    const b = Number.isFinite(baseRadius) && baseRadius > 0 ? baseRadius : KP_BASE_RADIUS;
    return { min: b * SIZE_RATIO_MIN, max: b * SIZE_RATIO_MAX };
  }

  /** t(d) = (#distinct degree < d) / (K-1)；单调、连续、非分桶。 */
  function normalizedRankT(degree, distinctSorted) {
    const arr = distinctSorted || [];
    const k = arr.length;
    if (k <= 1) return 0;
    const d = Number(degree) || 0;
    let lo = 0;
    let hi = k - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid] < d) lo = mid + 1;
      else hi = mid;
    }
    return lo / (k - 1);
  }

  function radiusForDegree(degree, distinctSorted, baseRadius) {
    const range = sizingRangeForBase(baseRadius);
    const t = normalizedRankT(degree, distinctSorted);
    return range.min + (range.max - range.min) * t;
  }

  function normalizedDegrees(degrees) {
    const map = new Map();
    for (const [id, value] of Object.entries(degrees || {})) {
      const num = Number(value);
      if (Number.isFinite(num)) map.set(String(id), Math.max(0, num));
    }
    const distinct = [...new Set([...map.values()])].sort((a, b) => a - b);
    return { map, distinct };
  }

  function degreeRatio(degreeInfo, degree) {
    if (!degreeInfo || !degreeInfo.map.size) return null;
    const max = degreeInfo.distinct.length ? degreeInfo.distinct[degreeInfo.distinct.length - 1] : 0;
    if (!max) return 0;
    return Math.max(0, Math.min(1, (Number(degree) || 0) / max));
  }

  // ── Presentation-only 文件/section 分组（task-380；不是 S2 cluster）────────
  function normalizeGroups(presentation) {
    const raw = Array.isArray(presentation && presentation.groups) ? presentation.groups : [];
    return raw
      .map((g) => ({
        group_id: String(g.group_id || ""),
        file: String(g.file || ""),
        section: String(g.section || ""),
        member_ids: Array.isArray(g.member_ids) ? g.member_ids.map(String) : [],
        count: Number(g.count) || (Array.isArray(g.member_ids) ? g.member_ids.length : 0),
        presentation_only: true,
      }))
      .filter((g) => g.group_id && g.member_ids.length)
      .sort((a, b) => (a.file || a.group_id).localeCompare(b.file || b.group_id));
  }

  function groupLabel(group) {
    return `${group.section || group.file || group.group_id} (${group.member_ids.length})`;
  }

  function galaxyColor(ratio) {
    const k = Math.max(0, Math.min(1, Number(ratio) || 0));
    const dim = [139, 148, 158];
    const bright = [240, 246, 252];
    const r = Math.round(dim[0] + (bright[0] - dim[0]) * k);
    const g = Math.round(dim[1] + (bright[1] - dim[1]) * k);
    const b = Math.round(dim[2] + (bright[2] - dim[2]) * k);
    return `rgb(${r},${g},${b})`;
  }

  function withAlpha(color, alpha) {
    const a = Math.max(0, Math.min(1, Number(alpha) || 0));
    if (typeof color === "string" && color.charAt(0) === "#" && color.length === 7) {
      const n = parseInt(color.slice(1), 16);
      return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
    }
    const m = /rgba?\(([\d.]+),([\d.]+),([\d.]+)/.exec(String(color || ""));
    if (m) return `rgba(${m[1]},${m[2]},${m[3]},${a})`;
    return color;
  }

  /** 旧 galaxy 星点：径向渐变光晕 + 实心核心。 */
  function drawStar(ctx, x, y, r, color, halo, glow) {
    if (!ctx || !ctx.createRadialGradient || !ctx.arc) return;
    const gr = r * (1.6 + Math.max(0, Number(glow) || 0) * 2.4);
    const grad = ctx.createRadialGradient(x, y, r * 0.1, x, y, gr);
    grad.addColorStop(0, withAlpha(color, halo));
    grad.addColorStop(0.55, withAlpha(color, halo * 0.45));
    grad.addColorStop(1, withAlpha(color, 0));
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(x, y, gr, 0, TAU);
    if (ctx.fill) ctx.fill();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, TAU);
    if (ctx.fill) ctx.fill();
  }

  /** 旧 drawDirectedEdge：线 + 箭头（端点按两端半径让位）。 */
  function drawDirectedEdge(ctx, sx, sy, tx, ty, nodeRadius, color, lineWidth, alpha, arrowSize) {
    if (!ctx || !ctx.beginPath) return;
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
    ctx.save && ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = lineWidth;
    if ("lineCap" in ctx) ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    if (ctx.stroke) ctx.stroke();
    const angle = Math.atan2(dy, dx);
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - head * Math.cos(angle - Math.PI / 7), tipY - head * Math.sin(angle - Math.PI / 7));
    ctx.lineTo(tipX - head * 0.72 * Math.cos(angle), tipY - head * 0.72 * Math.sin(angle));
    ctx.lineTo(tipX - head * Math.cos(angle + Math.PI / 7), tipY - head * Math.sin(angle + Math.PI / 7));
    ctx.closePath && ctx.closePath();
    if (ctx.fill) ctx.fill();
    ctx.restore && ctx.restore();
    ctx.globalAlpha = 1;
  }

  function nodeRadius(node, degreeInfo) {
    if (node.kind === "cluster") return clusterRadius(node.member_count || node.aggregate_count || 1);
    if (!degreeInfo || !degreeInfo.map.size) return KP_BASE_RADIUS;
    const degree = degreeInfo.map.get(node.id);
    return radiusForDegree(Number.isFinite(degree) ? degree : 0, degreeInfo.distinct, KP_BASE_RADIUS);
  }

  /** 视觉半径 = 数据映射 + 交互态加成（A3-1：hover +3 / target +2）。 */
  function visualRadius(node, degreeInfo, hovered, highlighted) {
    const base = nodeRadius(node, degreeInfo);
    return base + (hovered ? HOVER_EXTRA_RADIUS : highlighted ? TARGET_EXTRA_RADIUS : 0);
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
    // S3-11/S4 边界：S4 对 **shown** 选点做预算裁剪；VM 仍携带 suppressed/unknown
    // 候选（审计用，S4-10），其数量不受 render 预算约束。Renderer 的硬上限因此只校验
    // 它真正要画的 shown 子集（不做任何裁剪，超限 fail-visible）。
    const shownNodes = vm.nodes.filter((n) => !n.presence || n.presence === "shown").length;
    const shownEdges = vm.edges.filter((e) => !e.presence || e.presence === "shown").length;
    if (shownNodes > MAX_NODES || shownEdges > MAX_EDGES) {
      fail(
        "RENDER_BUDGET_EXCEEDED",
        `VM 的 shown 超硬上限：nodes=${shownNodes}/${MAX_NODES}, edges=${shownEdges}/${MAX_EDGES}（Renderer 不裁剪）`,
        { nodes: shownNodes, edges: shownEdges, max_nodes: MAX_NODES, max_edges: MAX_EDGES }
      );
    }
  }

  // ── 确定性布局（种子来自 VM id；focus 居中 + 邻居多臂环形；update 保位）────
  function computeLayout(vm, seed, width, height, prevPositions, degreeInfo, focusId) {
    const shown = shownModel(vm);
    const ids = shown.nodes.map((n) => n.id).sort();
    const positions = new Map();
    const radiusById = new Map(shown.nodes.map((n) => [n.id, nodeRadius(n, degreeInfo)]));
    const maxR = ids.reduce((m, id) => Math.max(m, radiusById.get(id) || KP_BASE_RADIUS), KP_BASE_RADIUS);
    const cx = width / 2;
    const cy = height / 2;
    const focus = focusId && ids.includes(String(focusId)) ? String(focusId) : null;
    const angleOffset = ((seed >>> 0) % 1000) / 1000 * TAU;
    if (prevPositions) {
      for (const id of ids) {
        if (prevPositions.has(id)) positions.set(id, { ...prevPositions.get(id) });
      }
    }
    if (focus) positions.set(focus, { x: cx, y: cy });
    const playW = Math.max(120, width - 2 * maxR - 40);
    const playH = Math.max(120, height - 2 * maxR - 56);
    const maxRing = Math.max(40, Math.min(playW, playH) / 2);
    const others = ids
      .filter((id) => id !== focus && !positions.has(id))
      .sort((a, b) => {
        const da = degreeInfo?.map.get(a) ?? -1;
        const db = degreeInfo?.map.get(b) ?? -1;
        return db - da || a.localeCompare(b);
      });
    const count = others.length;
    if (count) {
      // 单环最多 12 个；更多时两环（内圈 8、外圈其余）；偶数角度避免“一根竖线”
      const twoRings = count > 12;
      const innerCount = twoRings ? Math.min(8, Math.ceil(count / 2)) : count;
      const ring0 = twoRings ? maxRing * 0.55 : maxRing * 0.92;
      others.forEach((id, i) => {
        const onInner = i < innerCount;
        const n = onInner ? innerCount : Math.max(1, count - innerCount);
        const j = onInner ? i : i - innerCount;
        const angle = angleOffset + (j * TAU) / n + (onInner ? 0 : Math.PI / Math.max(3, n));
        positions.set(id, { x: cx + Math.cos(angle) * (onInner ? ring0 : maxRing), y: cy + Math.sin(angle) * (onInner ? ring0 : maxRing) });
      });
    }
    if (!focus) {
      // 无显式 focus：旧的确定性 radial（兼容未 setFocus 的调用）
      ids.forEach((id, index) => {
        if (positions.has(id)) return;
        const t = (index + 1) / Math.max(1, ids.length);
        const r = Math.max(60, Math.min(playW, playH) / 2) * Math.sqrt(t) * 0.92;
        const angle = angleOffset + index * GOLDEN_ANGLE;
        positions.set(id, { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r });
      });
    }
    return { positions, radiusById, shown, width, height };
  }

  function defaultHost(doc) {
    return {
      createCanvas(width, height) {
        const canvas = doc.createElement("canvas");
        canvas.width = Math.max(1, Math.round(width));
        canvas.height = Math.max(1, Math.round(height));
        canvas.style.display = "block";
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
      this._presentation = options.presentation || null;
      this._degreeInfo = normalizedDegrees(this._presentation && this._presentation.degrees);
      this._focusNodeId = null;
      this._layoutFocusId = null;
      this._groups = normalizeGroups(this._presentation);
      this._collapsedGroups = new Set();
      this._groupHit = [];
      this._lastVm = null;
      this._pendingVm = null;
      this._deferredScheduled = false;
      this._resizeObserver = null;
      this._resizeTimer = null;
      this._raf = typeof options.requestAnimationFrame === "function"
        ? options.requestAnimationFrame
        : (typeof global.requestAnimationFrame === "function"
          ? global.requestAnimationFrame.bind(global)
          : (cb) => setTimeout(cb, 16));
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

    /**
     * Presentation 元数据（degree 原值等）——**不进 VM**（S3-12 / A3-1）。
     * 只用于视觉映射（连续半径/渐变/光晕），不参与 presence/裁剪。
     */
    setPresentation(presentation) {
      this._presentation = presentation || null;
      this._degreeInfo = normalizedDegrees(this._presentation && this._presentation.degrees);
      this._groups = normalizeGroups(this._presentation);
      if (this._nodeById && this._nodeById.size) {
        const shown = { nodes: [...this._nodeById.values()], edges: this._edgeList };
        const degreeInfo = this._degreeInfo;
        const radiusById = new Map(shown.nodes.map((n) => [n.id, nodeRadius(n, degreeInfo)]));
        this._radiusById = radiusById;
        // 半径变化也更新布局间距的最小留白（位置本身保持以维持会话内保位）
        if (this._ctx) this._draw();
      }
      return this._degreeInfo;
    }

    getPresentation() {
      return this._presentation;
    }

    /** task-380：focus 居中布局（由 Presentation 传入；不进 VM）。 */
    setFocusNode(nodeId) {
      const next = nodeId ? String(nodeId) : null;
      if (this._focusNodeId !== next) this._focusNodeId = next;
      return this._focusNodeId;
    }

    getFocusNode() {
      return this._focusNodeId;
    }

    /** Presentation-only 分组（文件/section；不是 S2 cluster，不进 VM）。 */
    getGroups() {
      return this._groups.map((g) => ({ ...g, member_ids: g.member_ids.slice() }));
    }

    toggleGroup(groupId) {
      const id = String(groupId || "");
      if (!this._groups.some((g) => g.group_id === id)) return false;
      if (this._collapsedGroups.has(id)) this._collapsedGroups.delete(id);
      else this._collapsedGroups.add(id);
      if (this._ctx) this._draw();
      return true;
    }

    isGroupCollapsed(groupId) {
      return this._collapsedGroups.has(String(groupId || ""));
    }

    _syncGroups() {
      const shown = new Set(
        [...this._nodeById.values()].filter((n) => n.presence === "shown").map((n) => n.id)
      );
      this._groups = normalizeGroups(this._presentation).map((g) => ({
        ...g,
        member_ids: g.member_ids.filter((id) => shown.has(id)),
      })).filter((g) => g.member_ids.length);
      for (const id of [...this._collapsedGroups]) {
        if (!this._groups.some((g) => g.group_id === id)) this._collapsedGroups.delete(id);
      }
      return this._groups;
    }

    /** 当前被折叠组隐藏的成员（边/标签/节点都跳过）。 */
    _hiddenMemberIds() {
      const hidden = new Set();
      for (const g of this._groups) {
        if (!this._collapsedGroups.has(g.group_id)) continue;
        for (const id of g.member_ids) hidden.add(id);
      }
      return hidden;
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
      this._lastVm = vm;
      this._ensureResizeObserver();
      const model = this._project(vm);
      assertBudget(vm);
      if (!this._hasLayout()) {
        // 首帧等 rAF/真实布局；绝不用 800 回退尺寸画第一帧
        this._scheduleDeferredRender(vm, { update: false });
        return this._deferredSummary("render");
      }
      const width = this._measureWidth();
      const height = this._measureHeight();
      this._ensureCanvas(width, height);
      const seed = this._seed == null ? fnv1a(vm.view_model_id || "vm") : this._seed;
      this._seed = seed;
      const layout = computeLayout({ nodes: model.nodes, edges: model.edges }, seed, width, height, null, this._degreeInfo, this._focusNodeId);
      this._layoutFocusId = this._focusNodeId;
      this._applyLayout(layout, model);
      this._syncGroups();
      this._bindPointer();
      this._draw();
      return this._summary("render");
    }

    update(vm, opts) {
      opts = opts || {};
      if (this._disposed) fail("GRAPH_INTERNAL", "Renderer 已 dispose");
      this._lastVm = vm;
      this._ensureResizeObserver();
      const model = this._project(vm);
      assertBudget(vm);
      if (!this._hasLayout()) {
        this._scheduleDeferredRender(vm, { ...opts, update: true });
        return this._deferredSummary("update");
      }
      // focus 变化必须重排（否则旧位置让邻居塌成一列）；普通 update 保位
      const focusChanged = this._layoutFocusId !== this._focusNodeId;
      const keep = (opts.relayout === true || focusChanged) ? null : this._positions;
      const width = this._measureWidth();
      const height = this._measureHeight();
      this._ensureCanvas(width, height);
      const seed = this._seed == null ? fnv1a(vm.view_model_id || "vm") : this._seed;
      const layout = computeLayout({ nodes: model.nodes, edges: model.edges }, seed, width, height, keep, this._degreeInfo, this._focusNodeId);
      const before = new Map(this._positions);
      this._applyLayout(layout, model);
      this._layoutFocusId = this._focusNodeId;
      this._syncGroups();
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
      if (this._resizeObserver) {
        try { this._resizeObserver.disconnect(); } catch (_) { /* noop */ }
        this._resizeObserver = null;
      }
      if (this._resizeTimer) {
        clearTimeout(this._resizeTimer);
        this._resizeTimer = null;
      }
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
      const rect = c && typeof c.getBoundingClientRect === "function" ? c.getBoundingClientRect() : null;
      return Math.max(0, Number(rect?.width) || Number(c?.clientWidth) || Number(c?.width) || 0);
    }

    _measureHeight() {
      const c = this.container;
      const rect = c && typeof c.getBoundingClientRect === "function" ? c.getBoundingClientRect() : null;
      return Math.max(0, Number(rect?.height) || Number(c?.clientHeight) || Number(c?.height) || 0);
    }

    _hasLayout() {
      return this._measureWidth() >= 2 && this._measureHeight() >= 2;
    }

    /**
     * task-380 P0：首帧必须等容器布局稳定，禁止用 800×600 回退尺寸先画
     * （否则 backing/CSS aspect 不一致 ⇒ 横轴压扁）。
     * 用 rAF 轮询到有尺寸；有 ResizeObserver 时再挂尺寸变化重排。
     */
    _scheduleDeferredRender(vm, opts) {
      if (this._deferredScheduled) return;
      this._deferredScheduled = true;
      this._pendingVm = vm;
      this._pendingOpts = opts || {};
      let tries = 0;
      const tick = () => {
        this._deferredScheduled = false;
        if (this._disposed) return;
        if (this._hasLayout()) {
          const nextVm = this._pendingVm;
          const nextOpts = this._pendingOpts || {};
          this._pendingVm = null;
          this._pendingOpts = null;
          if (nextVm) {
            if (nextOpts.update) this.update(nextVm, nextOpts);
            else this.render(this.container, nextVm);
          }
          return;
        }
        tries += 1;
        if (tries <= 60) this._raf(tick);
      };
      this._raf(tick);
    }

    _ensureResizeObserver() {
      if (this._resizeObserver || !global.ResizeObserver || !this.container) return;
      try {
        this._resizeObserver = new global.ResizeObserver(() => this._onContainerResize());
        this._resizeObserver.observe(this.container);
      } catch (_) {
        this._resizeObserver = null;
      }
    }

    _onContainerResize() {
      if (this._resizeTimer) clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => {
        this._resizeTimer = null;
        if (this._disposed || !this._lastVm) return;
        const w = this._measureWidth();
        const h = this._measureHeight();
        if (w < 2 || h < 2) return;
        if (Math.abs(w - this._view.width) < 1 && Math.abs(h - this._view.height) < 1) return;
        // 尺寸变化必须重新布局，不能只改 canvas.width/height
        this.update(this._lastVm, { relayout: true });
      }, 80);
    }

    _deferredSummary(op) {
      return {
        status: "deferred",
        op,
        backend: this.backend,
        reason: "CONTAINER_NOT_LAID_OUT",
        nodeCount: this._nodeById ? this._nodeById.size : 0,
        edgeCount: this._edgeList ? this._edgeList.length : 0,
        positions: this._positions ? this._positions.size : 0,
        layoutSeed: this._seed,
        drawCalls: null,
        caps: this.getCapabilities(),
      };
    }

    _ensureCanvas(width, height) {
      const dpr = this.host && this.host.dpr ? this.host.dpr() : 1;
      if (this._canvas) {
        const w = Math.max(1, Math.round(width * dpr));
        const h = Math.max(1, Math.round(height * dpr));
        if (this._canvas.width !== w) this._canvas.width = w;
        if (this._canvas.height !== h) this._canvas.height = h;
        // CSS 用实测 px（不再 100% 非等比拉伸）
        if (this._canvas.style) {
          this._canvas.style.width = `${Math.max(1, Math.round(width))}px`;
          this._canvas.style.height = `${Math.max(1, Math.round(height))}px`;
        }
        this._bindPointer();
        return;
      }
      if (!this.host) fail("GRAPH_INTERNAL", "无 host（需要 document 或注入 host）");
      const made = this.host.createCanvas(width * dpr, height * dpr);
      this._canvas = made.canvas;
      this._ctx = made.ctx;
      if (this._ctx && this._ctx.setTransform) this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (this._canvas) {
        this._canvas.width = Math.max(1, Math.round(width * dpr));
        this._canvas.height = Math.max(1, Math.round(height * dpr));
        if (this._canvas.style) {
          this._canvas.style.width = `${Math.max(1, Math.round(width))}px`;
          this._canvas.style.height = `${Math.max(1, Math.round(height))}px`;
        }
      }
      if (this.host.append) this.host.append(this.container, this._canvas);
      this._bindPointer();
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
      const click = (event) => {
        // 真实浏览器 click 优先；CDP/无 click 环境由 mouseup 兜底（见下方 up）
        this._clickSeenAt = Date.now();
        this._onPointerClick(event);
      };
      const up = (event) => {
        const { x, y } = this._point(event);
        const mark = `${x},${y}`;
        if (this._pendingUp === mark) return;
        this._pendingUp = mark;
        // click 通常在 mouseup 同步随后到达；若未到达则兜底触发一次
        setTimeout(() => {
          this._pendingUp = null;
          if (this._clickSeenAt && Date.now() - this._clickSeenAt < 300) return;
          this._onPointerClick(event);
        }, 0);
      };
      this.host.on(this._canvas, "pointermove", move);
      this.host.on(this._canvas, "mousemove", move);
      this.host.on(this._canvas, "click", click);
      this.host.on(this._canvas, "mouseup", up);
      const dbl = (event) => this._onPointerDblClick(event);
      this.host.on(this._canvas, "dblclick", dbl);
      this._bound.push(
        [this._canvas, "pointermove", move],
        [this._canvas, "mousemove", move],
        [this._canvas, "click", click],
        [this._canvas, "mouseup", up],
        [this._canvas, "dblclick", dbl]
      );
    }

    _point(event) {
      // 真实 PointerEvent/MouseEvent 都带 clientX/clientY；统一用画布 rect 换算，
      // 避免合成事件 offsetX=0 或容器内滚动/边框导致的坐标偏差。
      if (event && Number.isFinite(event.clientX) && Number.isFinite(event.clientY)) {
        const rect = this.host && this.host.rect ? this.host.rect(this._canvas) : { left: 0, top: 0 };
        return { x: event.clientX - (rect.left || 0), y: event.clientY - (rect.top || 0) };
      }
      if (event && Number.isFinite(event.offsetX) && Number.isFinite(event.offsetY)) {
        return { x: event.offsetX, y: event.offsetY };
      }
      return { x: 0, y: 0 };
    }

    _pickNode(x, y) {
      let best = null;
      const hidden = this._hiddenMemberIds ? this._hiddenMemberIds() : new Set();
      for (const [id, p] of this._positions) {
        if (hidden.has(id)) continue;
        const r = (this._radiusById && this._radiusById.get(id)) || KP_BASE_RADIUS;
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

    _onPointerDblClick(event) {
      const { x, y } = this._point(event);
      const node = this._pickNode(x, y);
      if (!node) return;
      const payload = { node_id: node.id, kind: node.kind };
      this._emit("nodeDblClick", payload);
    }

    /** 供 host/tests 直接驱动点击（屏幕坐标）；事件 payload 白名单无导航字段。 */
    _pickGroup(x, y) {
      for (const hit of this._groupHit || []) {
        if (hit.kind === "circle") {
          if ((x - hit.x) ** 2 + (y - hit.y) ** 2 <= hit.r * hit.r) return hit;
        } else if (hit.kind === "rect") {
          if (x >= hit.x0 && x <= hit.x1 && y >= hit.y0 && y <= hit.y1) return hit;
        }
      }
      return null;
    }

    handlePointClick(x, y, extra = {}) {
      const node = this._pickNode(x, y);
      if (node) {
        const payload = { node_id: node.id, kind: node.kind, ...extra };
        this._emit("nodeClick", payload);
        return { type: "nodeClick", payload };
      }
      // 折叠组节点优先于边（组中心可能与 focus 点/边重叠）
      const circleHit = (this._groupHit || []).find((hit) => hit.kind === "circle"
        && (x - hit.x) ** 2 + (y - hit.y) ** 2 <= hit.r * hit.r);
      if (circleHit) {
        const payload = { group_id: circleHit.group.group_id, kind: "presentation-group", ...extra };
        this.toggleGroup(circleHit.group.group_id);
        this._emit("groupClick", payload);
        return { type: "groupClick", payload };
      }
      const edge = this._pickEdge(x, y);
      if (edge) {
        const payload = { edge_id: edge.id, ...extra };
        this._emit("edgeClick", payload);
        return { type: "edgeClick", payload };
      }
      const groupHit = this._pickGroup(x, y);
      if (groupHit) {
        const payload = { group_id: groupHit.group.group_id, kind: "presentation-group", ...extra };
        this.toggleGroup(groupHit.group.group_id);
        this._emit("groupClick", payload);
        return { type: "groupClick", payload };
      }
      this._emit("backgroundClick", { ...extra });
      return { type: "backgroundClick", payload: { ...extra } };
    }

    setSelection(selection) {
      this._selection = selection || null;
      if (this._active !== false) this._draw();
    }

    /** 搜索定位/正文链接 hover 的高亮（Presentation 瞬态；不进 VM）。 */
    setHighlight(nodeId) {
      this._highlightId = nodeId || null;
      if (this._ctx) this._draw();
      return this._highlightId;
    }

    getHighlight() {
      return this._highlightId || null;
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
      // 旧 KGviz 画布背景 #0a0d13（A3-1）
      if (ctx.fillRect) {
        ctx.fillStyle = VISUAL.bg;
        ctx.fillRect(0, 0, width, height);
      }

      const focusId = this._hoverId || this._highlightId || null;
      const radiusOf = (id) => (this._radiusById && this._radiusById.get(id)) || KP_BASE_RADIUS;
      // Presentation-only 文件/section 分组：先画展开组包络；折叠组成员后续跳过
      const hidden = this._hiddenMemberIds();
      this._groupHit = [];
      const groupGeom = new Map();
      for (const group of this._groups) {
        const members = group.member_ids
          .map((id) => ({ id, p: this._positions.get(id) }))
          .filter((m) => m.p);
        if (!members.length) continue;
        const xs = members.map((m) => m.p.x);
        const ys = members.map((m) => m.p.y);
        groupGeom.set(group.group_id, {
          minX: Math.min(...xs), maxX: Math.max(...xs),
          minY: Math.min(...ys), maxY: Math.max(...ys),
          cx: xs.reduce((a, b) => a + b, 0) / xs.length,
          cy: ys.reduce((a, b) => a + b, 0) / ys.length,
        });
        if (this._collapsedGroups.has(group.group_id)) continue;
        const g = groupGeom.get(group.group_id);
        const pad = 14;
        const x0 = g.minX - pad, y0 = g.minY - pad, x1 = g.maxX + pad, y1 = g.maxY + pad;
        if (ctx.beginPath && ctx.rect) {
          ctx.beginPath();
          ctx.rect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
          ctx.fillStyle = "rgba(88,166,255,0.05)";
          if (ctx.fill) ctx.fill();
          ctx.strokeStyle = "rgba(88,166,255,0.28)";
          ctx.lineWidth = 1;
          if (ctx.setLineDash) ctx.setLineDash([4, 3]);
          if (ctx.stroke) ctx.stroke();
          if (ctx.setLineDash) ctx.setLineDash([]);
        }
        this._groupHit.push({ kind: "rect", x0, y0, x1, y1, group });
        if (ctx.fillText) {
          ctx.font = VISUAL.labelFont;
          ctx.textAlign = "left";
          ctx.textBaseline = "bottom";
          ctx.lineWidth = VISUAL.labelHaloWidth;
          ctx.strokeStyle = VISUAL.halo;
          if (ctx.strokeText) ctx.strokeText(groupLabel(group), x0 + 2, y0 - 2);
          ctx.fillStyle = VISUAL.nodeMuted || "#8b949e";
          ctx.fillText(groupLabel(group), x0 + 2, y0 - 2);
          calls.labels += 1;
        }
      }

      // 边：只画 shown；折叠组成员隐藏；旧线宽/透明度 + 箭头
      for (const edge of this._edgeList) {
        const ends = edgeEndpoints(edge.id);
        if (!ends) continue;
        if (hidden.has(ends.source) || hidden.has(ends.target)) continue;
        const a = this._positions.get(ends.source);
        const b = this._positions.get(ends.target);
        if (!a || !b) continue;
        const incident = !!focusId && (ends.source === focusId || ends.target === focusId);
        const alpha = focusId ? (incident ? VISUAL.edgeAlphaActive : VISUAL.edgeAlphaDim) : VISUAL.edgeAlpha;
        const lineWidth = incident ? VISUAL.edgeWidthActive : VISUAL.edgeWidth;
        const padR = Math.max(radiusOf(ends.source), radiusOf(ends.target)) + (incident ? 2 : 0);
        drawDirectedEdge(
          ctx, a.x, a.y, b.x, b.y, padR,
          EDGE_COLORS[edge.type] || EDGE_COLORS.reference,
          lineWidth, alpha, VISUAL.arrowSize
        );
        calls.edges += 1;
      }

      // 节点：旧 galaxy 星点（degree ratio → 颜色/光晕/半径加成）；只画 shown
      const degreeMax = this._degreeInfo && this._degreeInfo.distinct.length
        ? this._degreeInfo.distinct[this._degreeInfo.distinct.length - 1]
        : 0;
      for (const node of this._nodeById.values()) {
        if (node.presence !== "shown") continue;
        if (hidden.has(node.id)) continue;
        const p = this._positions.get(node.id);
        if (!p) continue;
        const baseR = radiusOf(node.id);
        const hovered = this._hoverId === node.id;
        const highlighted = this._highlightId === node.id;
        const dim = !!focusId && !hovered && !highlighted;
        const r = visualRadius(node, this._degreeInfo, hovered, highlighted);
        const degree = node.kind === "kp" ? this._degreeInfo?.map.get(node.id) : null;
        const ratio = degreeMax && Number.isFinite(degree) ? Math.max(0, Math.min(1, degree / degreeMax)) : null;
        let fill;
        if (hovered) fill = VISUAL.nodeHover;
        else if (highlighted) fill = VISUAL.nodeTarget;
        else if (dim) fill = VISUAL.nodeDim;
        else if (node.range_ok === false) fill = VISUAL.nodeInvalid;
        else if (node.kind === "kp" && ratio != null) fill = galaxyColor(ratio);
        else fill = VISUAL.node;
        let halo = 0;
        if (hovered) halo = 0.6;
        else if (highlighted) halo = 0.4;
        else if (dim) halo = 0.1;
        else if (ratio != null) halo = 0.14 + ratio * 0.3;
        else halo = 0.12;
        if (node.kind === "kp") {
          drawStar(ctx, p.x, p.y, r, fill, halo, VISUAL.glow);
        } else if (ctx.beginPath) {
          ctx.beginPath();
          if (ctx.arc) ctx.arc(p.x, p.y, r, 0, TAU);
          ctx.fillStyle = fill;
          if (ctx.fill) ctx.fill();
          if (ctx.stroke && !dim) {
            ctx.strokeStyle = node.root_exempt ? "#e5c07b" : withAlpha(VISUAL.node, 0.35);
            ctx.lineWidth = node.root_exempt ? 2.2 : 1.2;
            if (ctx.setLineDash && node.root_exempt) ctx.setLineDash([3, 2]);
            ctx.stroke();
            if (ctx.setLineDash) ctx.setLineDash([]);
          }
        }
        if ((hovered || highlighted) && ctx.beginPath && ctx.arc && ctx.stroke) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, r, 0, TAU);
          ctx.strokeStyle = VISUAL.focus;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        if (node.kind === "cluster" && node.member_count != null && ctx.fillText) {
          ctx.fillStyle = VISUAL.node;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.font = VISUAL.labelFont;
          ctx.fillText(String(node.member_count), p.x, p.y);
          calls.text += 1;
        }
        calls.nodes += 1;
      }

      // 折叠组：画组节点（成员数），点击展开
      for (const group of this._groups) {
        if (!this._collapsedGroups.has(group.group_id)) continue;
        const g = groupGeom.get(group.group_id);
        if (!g) continue;
        const n = group.member_ids.length;
        const radius = Math.min(26, Math.max(12, 10 + 2 * Math.log2(n + 1)));
        if (ctx.beginPath && ctx.arc) {
          ctx.beginPath();
          ctx.arc(g.cx, g.cy, radius, 0, TAU);
          ctx.fillStyle = "rgba(88,166,255,0.16)";
          if (ctx.fill) ctx.fill();
          ctx.strokeStyle = "rgba(88,166,255,0.55)";
          ctx.lineWidth = 1.4;
          if (ctx.setLineDash) ctx.setLineDash([3, 2]);
          if (ctx.stroke) ctx.stroke();
          if (ctx.setLineDash) ctx.setLineDash([]);
        }
        this._groupHit.push({ kind: "circle", x: g.cx, y: g.cy, r: radius + 4, group });
        calls.nodes += 1;
        if (ctx.fillText) {
          ctx.font = VISUAL.labelFont;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = VISUAL.node || "#c9d1d9";
          ctx.fillText(String(n), g.cx, g.cy);
          ctx.textBaseline = "top";
          ctx.fillStyle = VISUAL.nodeMuted || "#8b949e";
          ctx.fillText(groupLabel(group), g.cx, g.cy + radius + 4);
          calls.labels += 1;
        }
      }

      // 标签：旧 KGviz LOD/避让 + 10px/halo（A3-1）
      const labelItems = [];
      for (const node of this._nodeById.values()) {
        if (node.presence !== "shown") continue;
        if (hidden.has(node.id)) continue;
        const p = this._positions.get(node.id);
        if (!p) continue;
        const baseR = radiusOf(node.id);
        const extra = node.id === this._hoverId ? HOVER_EXTRA_RADIUS : node.id === this._highlightId ? TARGET_EXTRA_RADIUS : 0;
        labelItems.push({
          id: node.id,
          text: labelText(node),
          x: p.x,
          y: p.y + baseR + extra + 4,
          r: 0,
          degree: node.kind === "cluster"
            ? Number(node.member_count) || 0
            : Number(this._degreeInfo?.map.get(node.id)) || 0,
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
        ctx.font = VISUAL.labelFont;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        for (const it of visible) {
          const node = this._nodeById.get(it.id);
          const hovered = it.id === this._hoverId;
          const highlighted = it.id === this._highlightId;
          ctx.lineWidth = VISUAL.labelHaloWidth;
          ctx.strokeStyle = VISUAL.halo;
          if (ctx.strokeText) ctx.strokeText(it.text, it.x, it.y);
          if (hovered) ctx.fillStyle = VISUAL.nodeHover;
          else if (highlighted) ctx.fillStyle = VISUAL.nodeTarget;
          else if (node && node.range_ok === false) ctx.fillStyle = VISUAL.labelInvalid;
          else ctx.fillStyle = VISUAL.label;
          ctx.fillText(it.text, it.x, it.y);
          calls.labels += 1;
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
        groups: this._groups.length,
        collapsedGroups: [...this._collapsedGroups],
        focusNode: this._focusNodeId,
        hiddenMembers: hidden.size,
        visual: {
          bg: VISUAL.bg,
          labelFont: VISUAL.labelFont,
          label: VISUAL.label,
          halo: VISUAL.halo,
          edgeColors: { ...EDGE_COLORS },
          baseRadius: KP_BASE_RADIUS,
          radiusMin: sizingRangeForBase(KP_BASE_RADIUS).min,
          radiusMax: sizingRangeForBase(KP_BASE_RADIUS).max,
          degrees: this._degreeInfo ? this._degreeInfo.map.size : 0,
        },
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
    KP_BASE_RADIUS,
    HOVER_EXTRA_RADIUS,
    TARGET_EXTRA_RADIUS,
    CLUSTER_MIN_RADIUS,
    CLUSTER_MAX_RADIUS,
    VISUAL,
    EVENT_TYPES,
    VM_TOP_FIELDS,
    assertVm,
    assertBudget,
    shownModel,
    clusterRadius,
    nodeRadius,
    visualRadius,
    radiusForDegree,
    normalizedRankT,
    sizingRangeForBase,
    galaxyColor,
    normalizedDegrees,
    computeLayout,
    fnv1a,
    EDGE_COLORS,
  };
  global.MemoriaGraphRendererAdapter = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
