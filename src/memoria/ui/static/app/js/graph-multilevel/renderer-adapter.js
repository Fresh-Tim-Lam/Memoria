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
  // task-391：唯一节点/位置事实源（RenderScene）与节点多态模型（RenderNode）。
  // 浏览器由 index.html 在 renderer-adapter.js 之前加载 render-scene.js。
  const SceneModule = global.MemoriaGraphRenderScene
    || (typeof require === "function" ? require("./render-scene.js") : null);
  const RenderNode = SceneModule ? SceneModule.RenderNode : null;
  const RenderScene = SceneModule ? SceneModule.RenderScene : null;

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
  // task-381：拖拽/平移/缩放
  const DRAG_THRESHOLD_PX = 4;
  const ZOOM_MIN = 0.35;
  const ZOOM_MAX = 2.5;
  const LABEL_MAX_CHARS = 18;

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
  // task-387：关联/引用/语义关系虚线；结构/层级实线（图例同步）
  const EDGE_DASH = Object.freeze({
    contain: [],
    structural: [],
    navigation: [],
    reference: [5, 4],
    semantic: [2, 3],
    extend: [5, 4],
    association: [5, 4],
  });
  const EVENT_TYPES = Object.freeze(["nodeClick", "edgeClick", "backgroundClick", "hover", "nodeDblClick", "groupClick", "backgroundGhostClick"]);

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
    // 单组且仅 1 个成员 ⇒ 它就是这唯一节点，不应再画“组节点 + 成员”两个东西。
    // 显式 container（demo L0_1）例外：容器即使只有 1 个成员也要显示。
    const singleMemberOnly = raw.length === 1 && (raw[0].member_ids || []).length === 1 && !raw[0].container;
    return raw
      .map((g) => ({
        group_id: String(g.group_id || ""),
        parent_id: String(g.parent_id || g.parent_group_id || ""),
        file: String(g.file || ""),
        section: String(g.section || ""),
        // task-391 rev26：demo 容器标签（L0_x）由 presentation 提供；有 label 时不追加成员数。
        label: String(g.label || ""),
        member_ids: Array.isArray(g.member_ids) ? g.member_ids.map(String) : [],
        count: Number(g.count) || (Array.isArray(g.member_ids) ? g.member_ids.length : 0),
        presentation_only: true,
        container: g.container === true,
        empty_container: g.empty_container === true,
        // task-391 rev26：presentation 固定初值（空容器排布）；渲染后仍可被力/拖拽移动。
        x: Number.isFinite(Number(g.x)) ? Number(g.x) : null,
        y: Number.isFinite(Number(g.y)) ? Number(g.y) : null,
      }))
      .filter((g) => g.group_id && (g.container || g.member_ids.length >= (singleMemberOnly ? 2 : 1)))
      .sort((a, b) => (a.file || a.group_id).localeCompare(b.file || b.group_id));
  }

  // ── task-391 rev35：上一站背景化的 log 深度衰减（人的视觉裁决）────────────
  // depth = 进入子站前的站深（根站=1，子站=2…）；lg = log2(depth+1)；
  // scale = max(0.55, 1 - 0.18*lg)；alpha = max(0.28, 0.62 - 0.14*lg)。
  // 立即上一站（depth=1）≈ 0.82 大小 / 0.48 alpha；更深层更小更淡。
  function backgroundDepthScale(depth) {
    const d = Math.max(1, Number(depth) || 1);
    const lg = Math.log2(d + 1);
    return Math.max(0.55, 1 - 0.18 * lg);
  }

  function backgroundDepthAlpha(depth) {
    const d = Math.max(1, Number(depth) || 1);
    const lg = Math.log2(d + 1);
    return Math.max(0.28, 0.62 - 0.14 * lg);
  }

  function groupLabel(group) {
    // task-391 rev26：explicit label（demo 容器）原样显示，不追加 (n)；
    // 其余按旧语义 “章节/文件名 (成员数)”。
    if (group && group.label) return String(group.label);
    const raw = String(group.section || group.file || group.group_id || "");
    const chapter = raw.match(/第\s*\d+\s*章/);
    const base = chapter ? chapter[0] : raw;
    return `${base} (${group.member_ids.length})`;
  }

  function truncateTextWidth(ctx, text, maxWidth) {
    if (!ctx.measureText || ctx.measureText(text).width <= maxWidth) return text;
    let out = text;
    while (out.length > 1 && ctx.measureText(`${out}…`).width > maxWidth) out = out.slice(0, -1);
    return `${out}…`;
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

  function drawHexagon(ctx, x, y, r) {
    if (!ctx || !ctx.beginPath || !ctx.moveTo || !ctx.lineTo) return;
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = -Math.PI / 2 + (i * TAU) / 6;
      const px = x + Math.cos(a) * r;
      const py = y + Math.sin(a) * r;
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.closePath && ctx.closePath();
  }

  function drawGroupBadge(ctx, x, y, count, color) {
    if (!ctx || !ctx.arc || !ctx.fillText) return;
    ctx.beginPath();
    ctx.arc(x, y, 8, 0, TAU);
    ctx.fillStyle = "rgba(13,17,23,0.95)";
    if (ctx.fill) ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    if (ctx.stroke) ctx.stroke();
    ctx.fillStyle = "#f0f6fc";
    ctx.font = "9px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(count), x, y + 0.5);
  }

  /** 旧 drawDirectedEdge：线 + 箭头（端点按两端半径让位）。 */
  function drawDirectedEdge(ctx, sx, sy, tx, ty, nodeRadius, color, lineWidth, alpha, arrowSize, dash) {
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
    if (ctx.setLineDash) ctx.setLineDash(Array.isArray(dash) ? dash : []);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    if (ctx.stroke) ctx.stroke();
    if (ctx.setLineDash) ctx.setLineDash([]);
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

  function truncateLabel(text, maxChars) {
    const s = String(text == null ? "" : text).trim();
    const max = Math.max(1, Number(maxChars) || LABEL_MAX_CHARS);
    if (s.length <= max) return s;
    return s.slice(0, Math.max(1, max - 1)) + "…";
  }

  function labelText(node, names) {
    // task-381：Presentation.names 优先（只读），fallback node.label/id；超长截断。
    const name = names && typeof names === "object" ? names[String(node.id)] : null;
    const raw = (typeof name === "string" && name.trim())
      ? name
      : (node.label != null && String(node.label) !== String(node.id) ? node.label : node.id);
    return truncateLabel(raw, LABEL_MAX_CHARS);
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

  // task-381：确定性力导向（repulsion + link + center + collision；固定 seed/tick）
  const FORCE = Object.freeze({
    repulsion: 5200,
    linkDistance: 96,
    linkStrength: 0.22,
    centerStrength: 0.008,
    collisionPad: 10,
    velocityDecay: 0.82,
    alphaMin: 0.012,
    alphaDecay: 0.955,
    ticks: 140,
    dragTicks: 70,
    minFrames: 45,
    quietFrames: 10,
    doneAlpha: 0.2,
    maxVelocity: 30,
    forceScale: 0.14,
    maxStep: 8, // 仅用于诊断历史，正常帧不再使用固定位移 clamp
    maxFrames: 420,
  });

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

  // task-391：力循环只有一份实现 —— `RenderScene.stepForce()`（见 render-scene.js）。
  // 旧的 buildForceState/stepForceState/runForceLayout 与 extraBodies 外挂环已删除：
  // KP / 折叠簇 / 背景幽灵现在同属一个 nodes Map、同一个 stepForce 循环。

  function forceLinksFor(shownEdges) {
    const links = [];
    for (const edge of shownEdges) {
      const ends = edgeEndpoints(edge.id);
      if (!ends) continue;
      // task-381：不同边给不同目标距/强度（仍由 edge id 确定性派生），
      // 避免 hub-star 语料收敛成完美圆环，保留旧 KGviz 的“自由作用力”非对称观感。
      const h = fnv1a(String(edge.id));
      links.push({
        source: ends.source,
        target: ends.target,
        distance: FORCE.linkDistance + ((h % 72) - 36),
        strength: FORCE.linkStrength * (0.75 + ((h >>> 8) % 50) / 100),
      });
    }
    links.sort((a, b) => `${a.source}|${a.target}`.localeCompare(`${b.source}|${b.target}`));
    return links;
  }

  function makeSeededRandom(seed) {
    let a = seed >>> 0;
    return function seededRandom() {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function computeForceLayout(vm, seed, width, height, degreeInfo, focusId, opts = {}) {
    const shown = shownModel(vm);
    const ids = shown.nodes.map((n) => n.id).sort();
    const radiusById = new Map(shown.nodes.map((n) => [n.id, nodeRadius(n, degreeInfo)]));
    const positions = new Map();
    const focus = focusId && ids.includes(String(focusId)) ? String(focusId) : null;
    const maxR = ids.reduce((m, id) => Math.max(m, radiusById.get(id) || KP_BASE_RADIUS), KP_BASE_RADIUS);
    const cx = width / 2;
    const cy = height / 2;
    const maxRing = Math.max(60, Math.min(width - 2 * maxR - 40, height - 2 * maxR - 56) / 2);
    // 固定 seed + id 排序 → 确定性环形/抖动初值（不要全叠中心靠斥力爆开）
    const rand = makeSeededRandom((fnv1a(`${seed}|${ids.join("|")}`) ^ 0x9e3779b9) >>> 0);
    const prev = opts.prevPositions || null;
    const smoothFocus = opts.smoothFocus === true;
    for (const id of ids) {
      if (prev && prev.has(id)) positions.set(id, { ...prev.get(id) });
    }
    const newIds = ids.filter((id) => id !== focus && !(prev && prev.has(id)));
    const ringCount = Math.max(1, Math.ceil(newIds.length / 12));
    newIds.forEach((id, i) => {
      const ring = Math.floor(i / 12);
      const j = i % 12;
      const inRing = Math.min(12, newIds.length - ring * 12);
      const angle = (j / Math.max(1, inRing)) * TAU + (rand() - 0.5) * 0.18 + ring * 0.21;
      const radius = maxRing * (0.38 + 0.58 * ((ring + 1) / ringCount)) * (0.92 + rand() * 0.16);
      positions.set(id, { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius });
    });
    if (focus && !(smoothFocus && prev && prev.has(focus))) positions.set(focus, { x: cx, y: cy });
    const pinned = new Set(opts.pinned || []);
    const links = forceLinksFor(shown.edges).concat(opts.extraLinks || []);
    // task-391：warmup 也走 RenderScene.stepForce（由 Renderer 在 sync 后调用 relax），
    // 这里只返回确定性初值，不再保留第二套力实现。
    return { positions, radiusById, shown, width, height, links, focus, pinned };
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
        // task-391 rev20：禁止原生图片拖拽/文本选择抢走图谱拖拽手势（CSS 同步兜底）。
        canvas.draggable = false;
        canvas.setAttribute("draggable", "false");
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
      on(canvas, type, handler, options) {
        if (canvas && typeof canvas.addEventListener === "function") canvas.addEventListener(type, handler, options);
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
      if (!RenderScene || !RenderNode) {
        fail("GRAPH_INTERNAL", "缺少 render-scene.js（browser 需在 renderer-adapter.js 之前加载）");
      }
      this.backend = "2d";
      this.container = container || null;
      this.options = options || {};
      this.doc = options.document || global.document || null;
      this.host = options.host || (this.doc ? defaultHost(this.doc) : null);
      this._listeners = Object.create(null);
      this._canvas = null;
      this._ctx = null;
      // task-391：唯一节点与位置事实源（RenderScene.nodes；不再有第二张位置表）。
      this._scene = new RenderScene({ force: FORCE });
      this._installScenePainters();
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
      this._groupGeom = new Map();
      this._groupHit = [];
      this._groupLabelBoxes = [];
      this._bgGhost = null;
      // task-391 rev29：上一站全视图背景化快照 + 全展开开关 + 容器标签集（去重 VM cluster）
      this._bgSnapshot = [];
      // task-391 rev38：上一站 visible edges（数据边+presentation links），背景化绘制/入同一力场
      this._bgSnapshotEdges = [];
      this._expandAll = false;
      this._containerLabels = new Set(
        this._groups.filter((g) => g.container && g.label).map((g) => String(g.label))
      );
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
      this._cancelRaf = typeof options.cancelAnimationFrame === "function"
        ? options.cancelAnimationFrame
        : (typeof global.cancelAnimationFrame === "function"
          ? global.cancelAnimationFrame.bind(global)
          : (id) => clearTimeout(id));
      // 真实浏览器走 rAF 连续动画；Node 测试默认同步 warmup（可用 animateForce:true 注入 rAF 测试）
      this._animateForce = options.animateForce === true
        || (options.animateForce !== false && typeof global.requestAnimationFrame === "function");
      this._forceState = null;
      this._forceAnimationRaf = null;
      this._forceFrames = 0;
      this._forceFrameLog = [];
      this._simulating = false;
      this._lastForceTicks = 0;
      this._drawScheduled = false;
      this._forceHold = false;
      this._hoverId = null;
      this._selection = null;
      this._selectedId = null;
      this._selectedGroupId = null;
      this._selectedNeighbors = new Set();
      this._disposed = false;
      this._bound = [];
      // task-381：camera + 本视图 pin/拖拽状态
      this._camera = { x: 0, y: 0, scale: 1 };
      this._userAdjusted = false;
      this._drag = null;
      this._suppressClick = false;
      this.lastRender = null;
      this.lastError = null;
    }

    /** task-391：节点绘制策略（按 drawKind 分派；唯一绘制入口在 RenderScene.draw）。 */
    _installScenePainters() {
      this._scene.setPainters({
        kp: (ctx, node, view) => this._paintKp(ctx, node, view),
        cluster: (ctx, node, view) => this._paintVmCluster(ctx, node, view),
        group: (ctx, node, view) => this._paintGroupCluster(ctx, node, view),
        ghost: (ctx, node, view) => this._paintGhost(ctx, node, view),
        // task-391 rev29：上一站全视图背景化（dim、不可选中/可拖、标签可辨）
        bgGhost: (ctx, node, view) => this._paintBackgroundSnapshotNode(ctx, node, view),
      });
    }

    /** task-391 rev29：进入子站时的“上一站全视图”快照（presentation-only 背景层）。 */
    setBackgroundSnapshot(nodes, edges) {
      this._bgSnapshot = Array.isArray(nodes) ? nodes : [];
      // task-391 rev38：background edges（上一站拓扑），不进 _edgeList/数据边统计
      this._bgSnapshotEdges = Array.isArray(edges) ? edges : [];
      this._syncScene();
      if (this._ctx) this._draw();
      return this._bgSnapshot.length;
    }

    clearBackgroundSnapshot() {
      this._bgSnapshot = [];
      this._bgSnapshotEdges = [];
      this._syncScene();
      if (this._ctx) this._draw();
    }

    /** task-391 rev38：背景边映射到场景节点 + 作为同一个 stepForce 的 links（节点同池受力）。 */
    _backgroundForceLinks() {
      const out = [];
      for (const edge of this._bgSnapshotEdges || []) {
        const a = edge.source === "ghost:A" ? "ghost:A" : `bg:${String(edge.source)}`;
        const b = edge.target === "ghost:A" ? "ghost:A" : `bg:${String(edge.target)}`;
        if (!this._scene.has(a) || !this._scene.has(b) || a === b) continue;
        out.push({ source: a, target: b, strength: 0.1, distance: 88 });
      }
      return out;
    }

    /** task-391 rev38：背景化边——保留原线型/方向语义，但更淡更细（alpha<1，颜色仍按 edge.type）。 */
    _drawBackgroundEdges(ctx) {
      const edges = this._bgSnapshotEdges || [];
      if (!edges.length) return 0;
      let drawn = 0;
      for (const edge of edges) {
        const a = edge.source === "ghost:A" ? this._scene.get("ghost:A") : this._scene.get(`bg:${String(edge.source)}`);
        const b = edge.target === "ghost:A" ? this._scene.get("ghost:A") : this._scene.get(`bg:${String(edge.target)}`);
        if (!a || !b) continue;
        const depth = Math.max(1, Number(edge.depth) || 1);
        const lg = Math.log2(depth + 1);
        const alpha = Math.max(0.18, 0.5 - 0.1 * lg);
        const type = String(edge.type || "reference");
        // 用 drawDirectedEdge 的 alpha 参数直接绘制（保留箭头/线型语义），不再改外层 globalAlpha
        drawDirectedEdge(
          ctx, a.x, a.y, b.x, b.y, 0,
          EDGE_COLORS[type] || EDGE_COLORS.reference,
          Math.max(0.7, VISUAL.edgeWidth * 0.75), alpha, VISUAL.arrowSize * 0.8,
          EDGE_DASH[type] || []
        );
        drawn += 1;
      }
      return drawn;
    }

    /** 只读：当前前景层可见节点（供“上一站快照”使用；不是第二份位置存储）。 */
    getVisibleNodes() {
      const out = [];
      for (const node of this._scene.nodes.values()) {
        if (node.layer !== "foreground") continue;
        out.push({
          id: String(node.id), x: node.x, y: node.y,
          radius: node.radius, kind: node.kind, shape: node.shape,
          label: node.label, drawKind: node.drawKind,
        });
      }
      return out;
    }

    /** 当前 pin 的节点 id（由 RenderNode.fixed 派生，不是第二份状态）。 */
    get _pinned() {
      const out = new Set();
      for (const node of this._scene.nodes.values()) if (node.fixed) out.add(node.id);
      return out;
    }

    /** 只读位置快照（测试/宿主调试）；唯一事实源仍是 RenderScene。 */
    getPositions() {
      const out = new Map();
      for (const node of this._scene.nodes.values()) out.set(node.id, { x: node.x, y: node.y });
      return out;
    }

    /** 只读节点访问（半径/velocity/fixed 等；唯一事实源仍是 RenderScene）。 */
    getNode(id) {
      return this._scene.get(id);
    }

    /**
     * 批量设置节点位置（首屏网格/快照恢复的公开入口）。
     * 未建节点先登记为待建位置，由下一次 sync 消费；不产生第二份位置存储。
     */
    applyPositions(positions) {
      this._scene.applyPositions(positions);
      if (this._ctx) this._draw();
      return this.getPositions();
    }

    /** app.js H 首屏 chapter 网格布局的渲染器侧入口（位置只写 RenderNode）。 */
    applyOverviewLayout(positions, opts = {}) {
      this._stopForceAnimation();
      this._forceHold = false;
      this.applyPositions(positions);
      if (opts.resetCamera !== false) {
        this._camera = { x: 0, y: 0, scale: 1 };
        this._userAdjusted = false;
      }
      if (this._ctx) this._draw();
      return this.getPositions();
    }

    /**
     * task-391：把 VM/presentation/background 投影进唯一 RenderScene。
     * 位置/半径/名字映射在这里一次算清，之后所有消费者（命中/力/绘制/快照）只读 scene。
     */
    _syncScene(layout) {
      const radiusOf = (node) => {
        if (node && node.group) return clusterRadius((node.group.member_ids || []).length);
        if (node && node.kind === "cluster") return nodeRadius(node, this._degreeInfo);
        const id = node && node.id != null ? String(node.id) : "";
        if (layout && layout.radiusById && layout.radiusById.has(id)) return layout.radiusById.get(id);
        return nodeRadius(node || { kind: "kp" }, this._degreeInfo);
      };
      // task-391 rev29 B：VM 里的 cluster 节点若与 presentation 容器同名（L0_x），
      // 只保留容器表达，避免“全展开”出现两个 L0_1 副本。
      const vm = this._lastVm || { nodes: [] };
      const dedupVm = {
        ...vm,
        nodes: (vm.nodes || []).filter((n) => {
          if (!n || n.kind !== "cluster") return true;
          const label = String(n.label || n.name || n.section || n.id || "");
          return !this._containerLabels || !this._containerLabels.has(label);
        }),
      };
      return this._scene.sync({
        vm: dedupVm,
        groups: this._groups,
        collapsedGroups: this._collapsedGroups,
        hiddenIds: this._hiddenMemberIds(),
        layout: layout || null,
        background: this._bgGhost,
        // task-391 rev29 C：上一站全视图背景化快照（presentation-only background layer）
        // task-391 rev35：按 depth 做 log 衰减——绘制半径同步乘 scale（每帧从原始 radius 重算，不叠加）
        backgroundNodes: (this._bgSnapshot || []).map((n) => ({
          ...n,
          radius: Math.max(3, (Number(n.radius) || 8) * backgroundDepthScale(n.depth)),
        })),
        groupLabelOf: (group) => groupLabel(group),
        labelOf: (node) => labelText(node, this._presentation && this._presentation.names),
        radiusOf,
        hasCollapsedAncestor: (groupId) => this._groupHasCollapsedAncestor(groupId),
      });
    }

    /** task-391 rev29 B：“全展开”时容器组展开（成员可见，容器只保留一个 envelope 表达）。 */
    setExpandAll(flag) {
      const next = flag === true;
      if (next === this._expandAll) return this._expandAll;
      this._expandAll = next;
      for (const g of this._groups || []) {
        if (!g.container) continue;
        const canExpand = (g.member_ids || []).length > 0;
        if (next && canExpand) this._collapsedGroups.delete(g.group_id);
        else this._collapsedGroups.add(g.group_id);
      }
      this._syncGroups();
      this._syncScene();
      if (this._ctx) this._draw();
      return this._expandAll;
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
      this._containerLabels = new Set(
        this._groups.filter((g) => g.container && g.label).map((g) => String(g.label))
      );
      if (this._nodeById && this._nodeById.size) {
        // 半径/标签变化只更新节点属性，位置本身保持（会话内保位）
        this._syncScene();
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

    _groupCenter(group) {
      return this._scene.groupCenter(group && group.member_ids);
    }

    // task-391：`_composeRenderNodes` / `_forceBodies` / `_pickRenderNode` 已删除。
    // 节点集合由 `_syncScene()` 一次投影进 RenderScene；命中统一走 `this._scene.pick()`。

    _syncGroups() {
      const shown = new Set(
        [...this._nodeById.values()].filter((n) => n.presence === "shown").map((n) => n.id)
      );
      this._groups = normalizeGroups(this._presentation).map((g) => ({
        ...g,
        member_ids: g.member_ids.filter((id) => shown.has(id)),
        // task-391 rev26：空容器（L0_2..L0_4）没有成员也必须保留（否则 demo 簇节点消失）
      })).filter((g) => g.member_ids.length > 0 || g.container);
      // 显式 demo 容器（如 L0_1）默认折叠：当前层只显示容器节点，成员进入子图后才显示。
      // task-391 rev29 B：全展开（setExpandAll(true)）时改为展开，同一时刻只保留一个 L0_x 表达。
      for (const g of this._groups) {
        if (!g.container) continue;
        const canExpand = (g.member_ids || []).length > 0;
        if (!this._expandAll || !canExpand) this._collapsedGroups.add(g.group_id);
        else this._collapsedGroups.delete(g.group_id);
      }
      for (const id of [...this._collapsedGroups]) {
        if (!this._groups.some((g) => g.group_id === id)) this._collapsedGroups.delete(id);
      }
      // task-391 rev47：父容器折叠时，子簇（如 L0_1_C1）不在父站散落；进入其父组子站后再显示。
      this._groups = this._groups.filter((g) => !this._groupHasCollapsedAncestor(g.group_id));
      return this._groups;
    }

    /** 当前被折叠组隐藏的成员（边/标签/节点都跳过）；支持 parent/child 多级组。 */
    _hiddenMemberIds() {
      const hidden = new Set();
      const byId = new Map(this._groups.map((g) => [g.group_id, g]));
      const addDescendants = (groupId) => {
        const g = byId.get(groupId);
        if (!g) return;
        for (const id of g.member_ids) hidden.add(id);
        for (const child of this._groups) {
          if (child.parent_id === groupId) addDescendants(child.group_id);
        }
      };
      for (const g of this._groups) {
        if (this._collapsedGroups.has(g.group_id)) addDescendants(g.group_id);
      }
      return hidden;
    }

    _groupHasCollapsedAncestor(groupId) {
      let cur = (this._groups || []).find((g) => g.group_id === groupId);
      const seen = new Set();
      while (cur && cur.parent_id && !seen.has(cur.group_id)) {
        seen.add(cur.group_id);
        if (this._collapsedGroups.has(cur.parent_id)) return true;
        cur = (this._groups || []).find((g) => g.group_id === cur.parent_id);
      }
      return false;
    }

    _groupAllMemberIds(groupId) {
      const out = new Set();
      const add = (id) => {
        const g = (this._groups || []).find((x) => x.group_id === id);
        if (!g) return;
        for (const m of g.member_ids) out.add(m);
        for (const child of this._groups) if (child.parent_id === id) add(child.group_id);
      };
      add(groupId);
      return out;
    }

    // ── task-381：camera / pan / zoom / fit ───────────────────────────────
    _screenToWorld(x, y) {
      const c = this._camera;
      const s = c.scale || 1;
      return { x: (x - c.x) / s, y: (y - c.y) / s };
    }

    _worldToScreen(x, y) {
      const c = this._camera;
      const s = c.scale || 1;
      return { x: x * s + c.x, y: y * s + c.y };
    }

    getViewState() {
      return {
        x: this._camera.x,
        y: this._camera.y,
        scale: this._camera.scale,
        userAdjusted: this._userAdjusted,
        pinned: [...this._pinned],
      };
    }

    /** 显式 reset（不清 pinned；双击空白/外部按钮可调用）。 */
    resetView() {
      this._camera = { x: 0, y: 0, scale: 1 };
      this._userAdjusted = false;
      if (this._ctx) this._draw();
      return this.getViewState();
    }

    /** 显式 fit：按 shown 节点 bbox 适配容器；手动操作后不再自动调用。 */
    fitView(padding) {
      if (!this._scene.size() || !this._view.width || !this._view.height) return this.getViewState();
      const pad = Number.isFinite(padding) ? padding : 28;
      const hidden = this._hiddenMemberIds();
      const xs = [];
      const ys = [];
      for (const node of this._scene.nodes.values()) {
        if (hidden.has(node.id)) continue;
        xs.push(node.x);
        ys.push(node.y);
      }
      if (!xs.length) return this.getViewState();
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const bw = Math.max(1, maxX - minX);
      const bh = Math.max(1, maxY - minY);
      const scale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.min(
        (this._view.width - 2 * pad) / bw,
        (this._view.height - 2 * pad) / bh,
        1.0
      )));
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      this._camera = {
        x: this._view.width / 2 - cx * scale,
        y: this._view.height / 2 - cy * scale,
        scale,
      };
      this._userAdjusted = false;
      if (this._ctx) this._draw();
      return this.getViewState();
    }

    /** task-381：滚轮以指针为中心缩放；手动后 userAdjusted=true，后续不自动 fit。 */
    _onWheel(event) {
      if (!event) return;
      if (typeof event.preventDefault === "function") event.preventDefault();
      const { x, y } = this._point(event);
      const world = this._screenToWorld(x, y);
      const delta = Number(event.deltaY) || 0;
      const factor = Math.exp(-delta * 0.0015);
      const scale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, this._camera.scale * factor));
      if (scale === this._camera.scale) return;
      this._camera.scale = scale;
      this._camera.x = x - world.x * scale;
      this._camera.y = y - world.y * scale;
      this._userAdjusted = true;
      if (this._ctx) this._draw();
    }

    /** 渲染器不得读 `data_edge_ids`：输入只按白名单读取节点/边字段（源码静态检查）。 */
    _project(vm) {
      assertVm(vm);
      const nodes = vm.nodes.map((n) => ({
        id: String(n.id),
        kind: n.kind,
        label: labelText(n, this._presentation && this._presentation.names),
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

    // ── task-382：rAF 连续力导向动画 ─────────────────────────────────────
    _stopForceAnimation() {
      this._simulating = false;
      if (this._forceAnimationRaf != null) {
        try { this._cancelRaf(this._forceAnimationRaf); } catch (_) { /* noop */ }
        this._forceAnimationRaf = null;
      }
      this._forceState = null;
    }

    /**
     * 从当前坐标启动/重加热连续动画；每帧只走一个 tick。
     * - focus 初始（pinFocusCenter=true）锚定中心；
     * - focus 切换/拖拽时 pinFocusCenter=false，保留当前位置平滑过渡。
     */
    _startForceAnimation(opts = {}) {
      if (!this._animateForce || !this._scene.size()) return false;
      this._stopForceAnimation();
      const links = forceLinksFor(this._edgeList).concat(this._backgroundForceLinks());
      // task-391：动画每一帧只调用 RenderScene.stepForce（唯一力循环）。
      const state = this._scene.buildForceState({
        links,
        focusId: opts.focusId || null,
        width: this._view.width,
        height: this._view.height,
        pinned: opts.pinned || this._pinned,
        pinFocusCenter: opts.pinFocusCenter === true,
        alpha: Number.isFinite(opts.alpha) ? opts.alpha : 1,
      });
      this._forceState = state;
      this._forceFrames = 0;
      this._forceFrameLog = [];
      this._simulating = true;
      let quiet = 0;
      const tick = () => {
        if (!this._simulating || this._disposed || this._forceState !== state) return;
        // task-385：拖拽期间模拟常驻；alpha 低时重加热，不因 quiet/alpha 停止
        if (this._forceHold && state.alpha < 0.12) state.alpha = 0.35;
        const maxDisp = this._scene.stepForce(state);
        this._forceFrames += 1;
        this._forceFrameLog.push({
          frame: this._forceFrames,
          alpha: Math.round(state.alpha * 10000) / 10000,
          maxDisp: Math.round(maxDisp * 10000) / 10000,
        });
        if (this._forceFrameLog.length > 600) this._forceFrameLog.shift();
        quiet = maxDisp < 0.05 ? quiet + 1 : 0;
        if (this._ctx) this._draw();
        // task-386：非拖拽也必须有可见连续动画；停止必须同时满足
        // 最小帧数 + quiet 连续 + alpha 低（拖拽期 _forceHold 完全跳过）。
        const done = !this._forceHold && (
          this._forceFrames >= FORCE.maxFrames
          || (this._forceFrames >= FORCE.minFrames
            && quiet >= FORCE.quietFrames
            && state.alpha <= FORCE.doneAlpha)
        );
        if (done) {
          this._simulating = false;
          this._forceAnimationRaf = null;
          this._lastForceTicks = this._forceFrames;
          return;
        }
        this._forceAnimationRaf = this._raf(tick);
      };
      this._forceAnimationRaf = this._raf(tick);
      return true;
    }

    getForceFrameLog() {
      return this._forceFrameLog.slice();
    }

    /** task-384：pointermove 更新坐标后请求一次 rAF 重绘（与动画帧合并）。 */
    _requestDraw() {
      if (this._drawScheduled) return;
      this._drawScheduled = true;
      this._raf(() => {
        this._drawScheduled = false;
        if (!this._disposed && this._ctx) this._draw();
      });
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
      const layout = computeForceLayout(
        { nodes: model.nodes, edges: model.edges }, seed, width, height,
        this._degreeInfo, this._focusNodeId,
        { pinned: this._pinned, prevPositions: null, animate: this._animateForce, extraLinks: this._backgroundForceLinks() }
      );
      this._layoutFocusId = this._focusNodeId;
      this._applyLayout(layout, model);
      this._syncGroups();
      // 唯一位置写入点：frame layout → RenderScene 节点（新节点取布局坐标，老节点保位）
      this._syncScene(layout);
      // task-391：无 rAF 环境（测试/降级）用 RenderScene.relax 做确定性 warmup
      if (!this._animateForce) {
        this._scene.relax(layout.links, FORCE.ticks, {
          width, height, focusId: this._focusNodeId, pinFocusCenter: true, pinned: layout.pinned,
        });
      }
      this._bindPointer();
      this._draw();
      if (this._animateForce) {
        this._startForceAnimation({ focusId: this._focusNodeId, pinFocusCenter: true, alpha: 1 });
      }
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
      this._stopForceAnimation();
      // focus 变化必须重排（否则旧位置让邻居塌成一列）；普通 update 保位
      const focusChanged = this._layoutFocusId !== this._focusNodeId;
      const before = this.getPositions();
      const keep = (opts.relayout === true || focusChanged) ? null : before;
      const width = this._measureWidth();
      const height = this._measureHeight();
      this._ensureCanvas(width, height);
      const seed = this._seed == null ? fnv1a(vm.view_model_id || "vm") : this._seed;
      const relayout = opts.relayout === true || focusChanged;
      const layout = relayout
        ? computeForceLayout(
          { nodes: model.nodes, edges: model.edges }, seed, width, height,
          this._degreeInfo, this._focusNodeId,
          {
            pinned: this._pinned,
            prevPositions: before,
            extraLinks: this._backgroundForceLinks(),
            smoothFocus: this._animateForce,
            animate: this._animateForce,
          }
        )
        : computeLayout({ nodes: model.nodes, edges: model.edges }, seed, width, height, keep, this._degreeInfo, this._focusNodeId);
      this._layoutFocusId = this._focusNodeId;
      this._applyLayout(layout, model);
      this._syncGroups();
      this._syncScene(layout);
      if (relayout && !this._animateForce) {
        this._scene.relax(layout.links, FORCE.ticks, {
          width, height, focusId: this._focusNodeId, pinFocusCenter: true, pinned: layout.pinned, smoothFocus: true,
        });
      }
      let moved = 0;
      const after = this.getPositions();
      for (const [id, p] of after) {
        const old = before.get(id);
        if (!old || old.x !== p.x || old.y !== p.y) moved += 1;
      }
      this._draw();
      if (relayout && this._animateForce) {
        // task-382：focus 过渡以当前坐标为初值，rAF 逐帧收敛（不整图从零重排）
        this._startForceAnimation({ focusId: this._focusNodeId, pinFocusCenter: false, alpha: 0.35 });
      }
      const summary = this._summary("update");
      summary.moved = moved;
      summary.reheat = opts.relayout === true;
      return summary;
    }

    dispose() {
      if (this._disposed) return { status: "ok", already: true };
      this._stopForceAnimation();
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
      this._scene.clear();
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

    _deferredSummary(op) {      return {
        status: "deferred",
        op,
        backend: this.backend,
        reason: "CONTAINER_NOT_LAID_OUT",
        nodeCount: this._nodeById ? this._nodeById.size : 0,
        edgeCount: this._edgeList ? this._edgeList.length : 0,
        positions: this._scene.size(),
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
      this._nodeById = new Map(model.nodes.map((n) => [n.id, n]));
      this._edgeList = model.edges.filter((e) => e.presence === "shown");
      this._view = { width: layout.width, height: layout.height };
      return layout;
    }

    _bindPointer() {
      if (!this.host || !this._canvas || !this.host.on) return;
      if (this._bound.length) return;
      const down = (event) => this._onPointerDown(event);
      const move = (event) => this._onPointerMove(event);
      const up = (event) => this._onPointerUp(event);
      const cancel = (event) => this._onPointerUp(event);
      const wheel = (event) => this._onWheel(event);
      const click = (event) => {
        this._clickSeenAt = Date.now();
        this._onPointerClick(event);
      };
      const dbl = (event) => this._onPointerDblClick(event);
      this.host.on(this._canvas, "pointerdown", down);
      this.host.on(this._canvas, "pointermove", move);
      this.host.on(this._canvas, "pointerup", up);
      this.host.on(this._canvas, "pointercancel", cancel);
      this.host.on(this._canvas, "wheel", wheel, { passive: false });
      this.host.on(this._canvas, "click", click);
      this.host.on(this._canvas, "dblclick", dbl);
      this._bound.push(
        [this._canvas, "pointerdown", down],
        [this._canvas, "pointermove", move],
        [this._canvas, "pointerup", up],
        [this._canvas, "pointercancel", cancel],
        [this._canvas, "wheel", wheel],
        [this._canvas, "click", click],
        [this._canvas, "dblclick", dbl]
      );
      // 旧环境无 PointerEvent 时提供 mouse 兜底（真实 Chromium 只走 pointer）
      if (!global.PointerEvent && this.host.on) {
        const mdown = (event) => this._onPointerDown(event);
        const mmove = (event) => this._onPointerMove(event);
        const mup = (event) => this._onPointerUp(event);
        this.host.on(this._canvas, "mousedown", mdown);
        this.host.on(this._canvas, "mousemove", mmove);
        this.host.on(this._canvas, "mouseup", mup);
        this._bound.push(
          [this._canvas, "mousedown", mdown],
          [this._canvas, "mousemove", mmove],
          [this._canvas, "mouseup", mup]
        );
      }
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

    // task-391：`_pickNode` 已删除；所有命中（KP/折叠簇/幽灵/双击）统一走
    // `this._scene.pick()`，节点身份与命中策略由 RenderNode 自己承担。

    _pickEdge(x, y) {
      let best = null;
      for (const edge of this._edgeList) {
        const ends = edgeEndpoints(edge.id);
        if (!ends) continue;
        const a = this._scene.get(ends.source);
        const b = this._scene.get(ends.target);
        if (!a || !b) continue;
        const d = pointSegmentDistance(x, y, a, b);
        if (d <= 6 && (!best || d < best.d)) best = { edge, d };
      }
      return best ? best.edge : null;
    }

    _onPointerDown(event) {
      if (!this._ctx) return;
      if (event && event.button != null && event.button !== 0) return;
      const screen = this._point(event);
      const world = this._screenToWorld(screen.x, screen.y);
      const rn = this._scene.pick(world.x, world.y);
      if (!rn && !this._hasLayout()) return;
      if (event && typeof event.preventDefault === "function") event.preventDefault();
      if (rn && this._canvas && typeof this._canvas.setPointerCapture === "function" && event && event.pointerId != null) {
        try { this._canvas.setPointerCapture(event.pointerId); } catch (_) { /* noop */ }
      }
      this._drag = {
        mode: rn ? "node" : "pan",
        nodeId: rn ? rn.id : null,
        nodeKind: rn ? rn.kind : null,
        startX: screen.x,
        startY: screen.y,
        lastX: screen.x,
        lastY: screen.y,
        startWorld: rn ? { x: rn.x, y: rn.y } : null,
        startCamera: { ...this._camera },
        moved: false,
        forceStarted: false,
        pointerId: event && event.pointerId != null ? event.pointerId : null,
      };
      if (rn) {
        // task-384/391：pointerdown 命中任何节点立即 pin（统一拖拽入口）
        this._hoverId = rn.id;
        this._scene.beginDrag(rn);
        // task-385：拖拽期间模拟常驻（参考 3D：pointerdown setDragNode + 持续模拟）
        this._forceHold = true;
        if (this._animateForce && !this._simulating) {
          this._startForceAnimation({ pinFocusCenter: false, alpha: 0.85 });
        }
      }
    }

    _onPointerMove(event) {
      const screen = this._point(event);
      const drag = this._drag;
      if (drag) {
        const dx = screen.x - drag.startX;
        const dy = screen.y - drag.startY;
        const distance = Math.hypot(dx, dy);
        if (drag.mode === "node" && drag.nodeId && drag.startWorld) {
          // task-384：无论移动多少都立即更新 pinned 节点（4px 只决定是否 click）
          // task-391：KP / 折叠簇 / 幽灵同一条拖拽路径，同一个位置 store。
          const scale = this._camera.scale || 1;
          const next = {
            x: drag.startWorld.x + dx / scale,
            y: drag.startWorld.y + dy / scale,
          };
          this._scene.dragTo(drag.nodeId, next.x, next.y);
          drag.moved = drag.moved || distance >= DRAG_THRESHOLD_PX;
          drag.lastX = screen.x;
          drag.lastY = screen.y;
          if (this._animateForce && !this._simulating) {
            // 异常停止时由下一次 move 重启一次；正常运行只更新 pin，不重建 state
            drag.forceStarted = true;
            this._startForceAnimation({ pinFocusCenter: false, alpha: 0.85 });
          }
          this._requestDraw();
          return;
        }
        if (drag.mode === "pan") {
          if (!drag.moved && distance < DRAG_THRESHOLD_PX) return;
          drag.moved = true;
          this._camera.x = drag.startCamera.x + dx;
          this._camera.y = drag.startCamera.y + dy;
          this._userAdjusted = true;
          drag.lastX = screen.x;
          drag.lastY = screen.y;
          this._requestDraw();
          return;
        }
        return;
      }
      const world = this._screenToWorld(screen.x, screen.y);
      const rn = this._scene.pick(world.x, world.y);
      const id = rn ? rn.id : null;
      if (id !== this._hoverId) {
        this._hoverId = id;
        this._requestDraw();
        this._emit("hover", id ? { node_id: id, kind: rn.kind } : { node_id: null, kind: null });
      }
    }

    _onPointerUp(event) {
      const drag = this._drag;
      if (!drag) return;
      this._drag = null;
      this._forceHold = false;
      if (drag.mode === "node" && drag.nodeId) {
        // task-385：松手解除拖拽 pin，让节点回到力导向（统一释放入口）
        this._scene.endDrag(drag.nodeId);
      }
      if (drag.moved) {
        // 拖拽超过阈值：抑制随后的 click（不触发 focus/选中）
        this._suppressClick = true;
        setTimeout(() => { this._suppressClick = false; }, 300);
        if (drag.mode === "node") {
          if (this._animateForce) {
            // task-386：松手 alpha≥0.45 重加热，保证至少 30–60 帧继续可见收敛
            this._startForceAnimation({ pinFocusCenter: false, alpha: 0.5 });
          } else {
            this._settleForceAfterDrag();
          }
        }
      }
      if (this._canvas && typeof this._canvas.releasePointerCapture === "function" && drag.pointerId != null) {
        try { this._canvas.releasePointerCapture(drag.pointerId); } catch (_) { /* noop */ }
      }
      this._requestDraw();
      if (event && typeof event.preventDefault === "function" && drag.moved) event.preventDefault();
    }

    /** task-381：拖拽 pin 后重加热力导向，让邻居继续收敛（不是拖完就死）。 */
    _settleForceAfterDrag() {
      if (!this._scene.size()) return;
      this._scene.relax(forceLinksFor(this._edgeList).concat(this._backgroundForceLinks()), FORCE.dragTicks, {
        width: this._view.width,
        height: this._view.height,
        focusId: null,
        pinFocusCenter: false,
        pinned: this._pinned,
        alpha: 1,
      });
      this._lastForceTicks = FORCE.dragTicks;
      if (this._ctx) this._draw();
    }

    _onPointerClick(event) {
      if (this._suppressClick) {
        this._suppressClick = false;
        return;
      }
      const { x, y } = this._point(event);
      this.handlePointClick(x, y, event?.shiftKey ? { shift: true } : {});
    }

    _onPointerDblClick(event) {
      const { x, y } = this._point(event);
      const world = this._screenToWorld(x, y);
      const node = this._scene.pick(world.x, world.y);
      if (!node) {
        // 双击空白 = fit（显式操作；符合 userAdjusted 门控）
        this.fitView();
        return;
      }
      const payload = { node_id: node.id, kind: node.kind };
      this._emit("nodeDblClick", payload);
    }

    /** 供 host/tests 直接驱动点击（屏幕坐标）；事件 payload 白名单无导航字段。 */
    _pickGroup(x, y) {
      const inside = [];
      for (const hit of this._groupHit || []) {
        if (hit.kind === "circle") {
          if ((x - hit.x) ** 2 + (y - hit.y) ** 2 <= hit.r * hit.r) inside.push(hit);
        } else if (hit.kind === "rect") {
          if (x >= hit.x0 && x <= hit.x1 && y >= hit.y0 && y <= hit.y1) inside.push(hit);
        }
      }
      if (!inside.length) return null;
      // 嵌套 group 时选最内层（面积最小/半径最小），否则父包络会吞掉子组点击
      inside.sort((a, b) => {
        const area = (h) => h.kind === "circle" ? Math.PI * h.r * h.r : (h.x1 - h.x0) * (h.y1 - h.y0);
        return area(a) - area(b);
      });
      return inside[0];
    }

    handlePointClick(x, y, extra = {}) {
      // 公开入口接收屏幕坐标；内部命中一律世界坐标（camera 变换）
      const world = this._screenToWorld(x, y);
      x = world.x;
      y = world.y;
      // 统一命中：唯一 RenderScene.pick()，按节点 hitPolicy 分派返回/下钻/选中
      const rn = this._scene.pick(x, y);
      if (rn) {
        if (rn.hitPolicy === "return") {
          const payload = { kind: "background-ghost", label: rn.label, ...extra };
          this._emit("backgroundGhostClick", payload);
          return { type: "backgroundGhostClick", payload };
        }
        if (rn.hitPolicy === "drill" && rn.group) {
          this.selectGroup(rn.group.group_id);
          const payload = { group_id: rn.group.group_id, kind: "presentation-group", ...extra };
          this._emit("groupClick", payload);
          return { type: "groupClick", payload };
        }
        this.selectNode(rn.id);
        const payload = { node_id: rn.id, kind: rn.kind, ...extra };
        this._emit("nodeClick", payload);
        return { type: "nodeClick", payload };
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
        this._emit("groupClick", payload);
        return { type: "groupClick", payload };
      }
      // task-387：空白点击清除选中，不改 focus
      this.clearSelection();
      this._emit("backgroundClick", { ...extra });
      return { type: "backgroundClick", payload: { ...extra } };
    }

    setSelection(selection) {
      this._selection = selection || null;
      if (this._active !== false) this._draw();
    }

    /** task-387：单击 KP = 选中节点 + 一跳邻居 + 相关边（不改 focus / 不跳转）。 */
    selectNode(nodeId) {
      const id = nodeId ? String(nodeId) : null;
      this._selectedGroupId = null;
      this._selectedId = id;
      this._selection = id ? { kind: "node", node_id: id } : null;
      this._selectedNeighbors = new Set();
      if (id) {
        for (const edge of this._edgeList) {
          const ends = edgeEndpoints(edge.id);
          if (!ends) continue;
          if (ends.source === id) this._selectedNeighbors.add(ends.target);
          else if (ends.target === id) this._selectedNeighbors.add(ends.source);
        }
        this._highlightId = id;
      } else {
        this._highlightId = null;
      }
      if (this._ctx) this._draw();
      return { selected: id, neighbors: [...this._selectedNeighbors] };
    }

    clearSelection() {
      this._selectedId = null;
      this._selectedGroupId = null;
      this._selectedNeighbors = new Set();
      this._selection = null;
      this._highlightId = null;
      if (this._ctx) this._draw();
      return { selected: null };
    }

    /** task-387：点击组 → 选中组并高亮成员（展开/折叠由 toggleGroup 完成）。 */
    selectGroup(groupId) {
      const id = groupId ? String(groupId) : null;
      const group = (this._groups || []).find((g) => g.group_id === id);
      this._selectedId = null;
      this._selectedGroupId = group ? id : null;
      this._selectedNeighbors = group ? this._groupAllMemberIds(id) : new Set();
      this._selection = group ? { kind: "group", group_id: id } : null;
      this._highlightId = null;
      if (this._ctx) this._draw();
      return group ? { group_id: id, members: group.member_ids.slice() } : null;
    }

    /** task-389：视图快照（下钻/返回恢复位置、相机、选中、focus；不重新布局）。 */
    captureViewState() {
      return {
        positions: this._scene.snapshotPositions(),
        camera: { ...this._camera },
        userAdjusted: this._userAdjusted,
        selectedId: this._selectedId,
        selectedGroupId: this._selectedGroupId,
        selectedNeighbors: [...this._selectedNeighbors],
        selection: this._selection ? JSON.parse(JSON.stringify(this._selection)) : null,
        highlightId: this._highlightId,
        focusNodeId: this._focusNodeId,
        layoutFocusId: this._layoutFocusId,
        collapsedGroups: [...this._collapsedGroups],
      };
    }

    restoreViewState(snapshot) {
      if (!snapshot) return false;
      this._stopForceAnimation();
      this._forceHold = false;
      this._scene.restorePositions(snapshot.positions || []);
      this._camera = { ...(snapshot.camera || { x: 0, y: 0, scale: 1 }) };
      this._userAdjusted = !!snapshot.userAdjusted;
      this._selectedId = snapshot.selectedId || null;
      this._selectedGroupId = snapshot.selectedGroupId || null;
      this._selectedNeighbors = new Set(snapshot.selectedNeighbors || []);
      this._selection = snapshot.selection || null;
      this._highlightId = snapshot.highlightId || null;
      this._focusNodeId = snapshot.focusNodeId || null;
      this._layoutFocusId = snapshot.layoutFocusId || null;
      this._collapsedGroups = new Set(snapshot.collapsedGroups || []);
      if (this._ctx) this._draw();
      return true;
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

    /** 同一画布的背景视图幽灵节点：上一站 A 留在画布上，连到当前视图入口。 */
    setBackgroundGhost(info) {
      this._bgGhost = info || null;
      // 位置由 RenderScene.sync 统一重建（唯一位置 store，无 aux 外挂）
      this._syncScene();
      if (this._ctx) {
        if (this._bgGhost && this._scene.size()) {
          this._startForceAnimation({ pinFocusCenter: false, alpha: 0.45 });
        }
        this._draw();
      }
      return this._bgGhost;
    }

    clearBackgroundGhost() {
      this._bgGhost = null;
      this._syncScene();
      if (this._ctx) {
        if (this._scene.size()) this._startForceAnimation({ pinFocusCenter: false, alpha: 0.3 });
        this._draw();
      }
      return true;
    }

    // ── 绘制策略（task-391：单绘制入口 RenderScene.draw → RenderNode.draw → painter）──
    /**
     * task-391 rev29 C：上一站全视图背景化节点（layer=background, hitPolicy=none）。
     * 只做 dim 绘制（形状/标签保留可辨），不参与命中/拖拽/力；不是第二份位置存储。
     */
    _paintBackgroundSnapshotNode(ctx, node) {
      // task-391 rev35（人的视觉裁决）：背景化节点仍为白色发光、不绘制任何标签，
      // 但按 log 深度衰减：半径/发光 blur 同步乘 scale，亮度用 alpha 降低。
      const depth = node.data && node.data.depth != null ? Number(node.data.depth) : 1;
      const scale = backgroundDepthScale(depth);
      const alpha = backgroundDepthAlpha(depth);
      const cluster = node.shape === "hexagon" || node.kind === "cluster";
      const prevAlpha = ctx.globalAlpha;
      if (ctx.globalAlpha !== undefined) ctx.globalAlpha = alpha;
      if (cluster) {
        ctx.save?.();
        if (ctx.shadowColor !== undefined) ctx.shadowColor = "rgba(240,246,252,0.95)";
        if (ctx.shadowBlur !== undefined) ctx.shadowBlur = 14 * scale;
        drawHexagon(ctx, node.x, node.y, node.radius);
        ctx.fillStyle = "#f0f6fc";
        if (ctx.fill) ctx.fill();
        ctx.strokeStyle = "#f0f6fc";
        ctx.lineWidth = 1.6 * scale;
        if (ctx.stroke) ctx.stroke();
        if (ctx.shadowBlur !== undefined) ctx.shadowBlur = 0;
        if (ctx.shadowColor !== undefined) ctx.shadowColor = "transparent";
        ctx.restore?.();
        drawHexagon(ctx, node.x, node.y, node.radius + 3 * scale);
        ctx.strokeStyle = "rgba(240,246,252,0.28)";
        ctx.lineWidth = 1;
        if (ctx.stroke) ctx.stroke();
      } else {
        drawStar(ctx, node.x, node.y, Math.max(3, node.radius), "#f0f6fc", 0.28 * scale, VISUAL.glow * scale);
      }
      if (ctx.globalAlpha !== undefined) ctx.globalAlpha = prevAlpha === undefined ? 1 : prevAlpha;
    }

    /** 背景幽灵（layer=background）。
     *  task-391 回归修复：旧 `_drawBackgroundGhost()` 的 ghost→target 跨层虚线在重构时丢失，
     *  这里按原样式补回（rgba(88,166,255,0.55)、1.4px、dash [5,4]）。该线**不是数据边**：
     *  不新增 edge、不进 VM/`_edgeList`/edge 统计，只是幽灵到子图入口的视觉连接。 */
    _paintGhost(ctx, node, view) {
      const calls = view.calls || { nodes: 0, labels: 0, text: 0 };
      const targetId = node.data && node.data.targetId != null ? String(node.data.targetId) : "";
      const target = targetId ? this._scene.get(targetId) : null;
      if (target && ctx.beginPath && ctx.moveTo && ctx.lineTo && ctx.stroke) {
        ctx.save?.();
        ctx.beginPath();
        ctx.moveTo(node.x, node.y);
        ctx.lineTo(target.x, target.y);
        ctx.strokeStyle = "rgba(88,166,255,0.55)";
        ctx.lineWidth = 1.4;
        if (ctx.setLineDash) ctx.setLineDash([5, 4]);
        ctx.stroke();
        if (ctx.setLineDash) ctx.setLineDash([]);
        ctx.restore?.();
      }
      ctx.save?.();
      if (ctx.globalAlpha !== undefined) ctx.globalAlpha = 0.75;
      drawHexagon(ctx, node.x, node.y, node.radius);
      ctx.fillStyle = "rgba(240,246,252,0.16)";
      if (ctx.fill) ctx.fill();
      ctx.strokeStyle = "rgba(240,246,252,0.85)";
      ctx.lineWidth = 1.6;
      if (ctx.setLineDash) ctx.setLineDash([4, 2]);
      if (ctx.stroke) ctx.stroke();
      if (ctx.setLineDash) ctx.setLineDash([]);
      ctx.restore?.();
      if (ctx.fillText) {
        ctx.font = VISUAL.labelFont;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "#f0f6fc";
        ctx.fillText(String(node.label || ""), node.x, node.y + node.radius + 4);
        calls.labels += 1;
      }
      calls.nodes += 1;
    }

    /** 折叠组节点（presentation group → hexagon + 成员数徽标）。 */
    _paintGroupCluster(ctx, node, view) {
      const calls = view.calls || { nodes: 0, labels: 0, text: 0 };
      const group = node.group;
      if (!group) return;
      const selectedGroup = this._selectedGroupId === group.group_id;
      const radius = node.radius;
      // 默认：实心白色发光六边形；点击进入后：样式 B（蓝色双环虚线六边形）
      if (selectedGroup) {
        drawHexagon(ctx, node.x, node.y, radius);
        ctx.fillStyle = "rgba(88,166,255,0.16)";
        if (ctx.fill) ctx.fill();
        ctx.strokeStyle = "#58a6ff";
        ctx.lineWidth = 2.2;
        if (ctx.setLineDash) ctx.setLineDash([4, 2]);
        if (ctx.stroke) ctx.stroke();
        if (ctx.setLineDash) ctx.setLineDash([]);
        drawHexagon(ctx, node.x, node.y, radius + 3);
        ctx.strokeStyle = "rgba(88,166,255,0.35)";
        ctx.lineWidth = 1;
        if (ctx.stroke) ctx.stroke();
      } else {
        ctx.save?.();
        if (ctx.shadowColor !== undefined) ctx.shadowColor = "rgba(240,246,252,0.95)";
        if (ctx.shadowBlur !== undefined) ctx.shadowBlur = 14;
        drawHexagon(ctx, node.x, node.y, radius);
        ctx.fillStyle = "#f0f6fc";
        if (ctx.fill) ctx.fill();
        ctx.strokeStyle = "#f0f6fc";
        ctx.lineWidth = 1.6;
        if (ctx.stroke) ctx.stroke();
        if (ctx.shadowBlur !== undefined) ctx.shadowBlur = 0;
        if (ctx.shadowColor !== undefined) ctx.shadowColor = "transparent";
        ctx.restore?.();
        drawHexagon(ctx, node.x, node.y, radius + 3);
        ctx.strokeStyle = "rgba(240,246,252,0.28)";
        ctx.lineWidth = 1;
        if (ctx.stroke) ctx.stroke();
      }
      // task-391 rev26：空容器（L0_2..L0_4）没有成员，不画 “0” 成员数徽标（名字已统一 L0_x）。
      if (!group.empty_container) {
        drawGroupBadge(ctx, node.x + radius * 0.7, node.y - radius * 0.7, group.member_ids.length, selectedGroup ? "#58a6ff" : "#0d1117");
      }
      if (view.groupHit) view.groupHit.push({ kind: "circle", x: node.x, y: node.y, r: radius + 4, group, selected: selectedGroup });
      if (ctx.fillText) {
        ctx.font = VISUAL.labelFont;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        const ctext = truncateTextWidth(ctx, String(node.label || ""), Math.max(40, radius * 2 + 8));
        ctx.fillStyle = selectedGroup ? "#f0f6fc" : (VISUAL.nodeMuted || "#8b949e");
        ctx.fillText(ctext, node.x, node.y + radius + 4);
        calls.labels += 1;
        const cw = ctx.measureText ? ctx.measureText(ctext).width : ctext.length * 6;
        if (view.groupLabelBoxes) view.groupLabelBoxes.push({ x: node.x - cw / 2 - 2, y: node.y + radius + 3, w: cw + 4, h: 14 });
      }
      calls.nodes += 1;
    }

    _paintKp(ctx, node, view) {
      this._paintGalaxyNode(ctx, node, view);
    }

    _paintVmCluster(ctx, node, view) {
      this._paintGalaxyNode(ctx, node, view);
    }

    /** KP / VM cluster：沿用旧 galaxy 星点与选中环（同一绘制实现，按 data.kind 区分外观）。 */
    _paintGalaxyNode(ctx, node, view) {
      const calls = view.calls || { nodes: 0, labels: 0, text: 0 };
      const data = node.data;
      if (!data) return;
      const degreeMax = this._degreeInfo && this._degreeInfo.distinct.length
        ? this._degreeInfo.distinct[this._degreeInfo.distinct.length - 1]
        : 0;
      const hovered = this._hoverId === data.id;
      const highlighted = this._highlightId === data.id;
      const selected = this._selectedId === data.id;
      const selectionActive = !!(this._selectedId || this._selectedGroupId);
      const inSelection = selectionActive && (selected || this._selectedNeighbors.has(data.id));
      const focusId = this._hoverId || this._highlightId || null;
      const dim = selectionActive ? !inSelection : (!!focusId && !hovered && !highlighted);
      const r = visualRadius(data, this._degreeInfo, hovered, highlighted);
      const degree = data.kind === "kp" ? this._degreeInfo?.map.get(data.id) : null;
      const ratio = degreeMax && Number.isFinite(degree) ? Math.max(0, Math.min(1, degree / degreeMax)) : null;
      let fill;
      if (selected) fill = VISUAL.nodeHover;
      else if (hovered) fill = VISUAL.nodeHover;
      else if (highlighted) fill = VISUAL.nodeTarget;
      else if (dim) fill = VISUAL.nodeDim;
      else if (data.range_ok === false) fill = VISUAL.nodeInvalid;
      else if (data.kind === "kp" && ratio != null) fill = galaxyColor(ratio);
      else fill = VISUAL.node;
      let halo = 0;
      if (selected) halo = 0.6;
      else if (hovered) halo = 0.6;
      else if (highlighted) halo = 0.4;
      else if (dim) halo = 0.1;
      else if (ratio != null) halo = 0.14 + ratio * 0.3;
      else halo = 0.12;
      if (data.kind === "kp") {
        drawStar(ctx, node.x, node.y, r, fill, halo, VISUAL.glow);
      } else if (ctx.beginPath) {
        ctx.beginPath();
        if (ctx.arc) ctx.arc(node.x, node.y, r, 0, TAU);
        ctx.fillStyle = fill;
        if (ctx.fill) ctx.fill();
        if (ctx.stroke && !dim) {
          ctx.strokeStyle = data.root_exempt ? "#e5c07b" : withAlpha(VISUAL.node, 0.35);
          ctx.lineWidth = data.root_exempt ? 2.2 : 1.2;
          if (ctx.setLineDash && data.root_exempt) ctx.setLineDash([3, 2]);
          ctx.stroke();
          if (ctx.setLineDash) ctx.setLineDash([]);
        }
      }
      if ((selected || inSelection || hovered || highlighted) && ctx.beginPath && ctx.arc && ctx.stroke) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + (selected ? 2.2 : 1.5), 0, TAU);
        ctx.strokeStyle = selected ? "#f0f6fc" : (inSelection ? "rgba(88,166,255,0.62)" : VISUAL.focus);
        ctx.lineWidth = selected ? 2 : (inSelection ? 1.2 : 2);
        ctx.stroke();
      }
      if (data.id === this._focusNodeId && ctx.beginPath && ctx.arc && ctx.stroke) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + (selected ? 5 : 3), 0, TAU);
        ctx.strokeStyle = selected ? "rgba(88,166,255,0.9)" : "rgba(88,166,255,0.55)";
        ctx.lineWidth = selected ? 1.4 : 1;
        if (ctx.setLineDash) ctx.setLineDash([2, 3]);
        ctx.stroke();
        if (ctx.setLineDash) ctx.setLineDash([]);
      }
      if (data.kind === "cluster" && data.member_count != null && ctx.fillText) {
        ctx.fillStyle = VISUAL.node;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = VISUAL.labelFont;
        ctx.fillText(String(data.member_count), node.x, node.y);
        calls.text += 1;
      }
      calls.nodes += 1;
    }

    /**
     * task-391 rev26：**presentation-only** demo 连线（容器链 / 容器→KP）。
     * 从 `presentation.links` 解析已建场景节点（`group:<gid>` 或裸 KP id）后画结构色虚线；
     * 不新增边、不进 VM/`_edgeList`/edge 统计，纯展示连接。返回本次绘制条数（诊断用）。
     */
    _drawPresentationLinks(ctx) {
      const links = this._presentation && Array.isArray(this._presentation.links)
        ? this._presentation.links : [];
      if (!links.length || !ctx.beginPath) return 0;
      let drawn = 0;
      ctx.save?.();
      ctx.strokeStyle = "rgba(139,148,158,0.55)";
      ctx.lineWidth = 1.2;
      if (ctx.setLineDash) ctx.setLineDash([4, 4]);
      for (const link of links) {
        if (!link) continue;
        const source = this._scene.get(String(link.source || link.source_id || ""));
        const target = this._scene.get(String(link.target || link.target_id || ""));
        if (!source || !target) continue;
        ctx.beginPath();
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);
        ctx.stroke();
        drawn += 1;
      }
      if (ctx.setLineDash) ctx.setLineDash([]);
      ctx.restore?.();
      return drawn;
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
      // task-381：camera（pan/zoom）只影响世界层；背景/命中坐标单独换算
      const cam = this._camera;
      const applyCamera = typeof ctx.translate === "function" && typeof ctx.scale === "function"
        && (cam.x !== 0 || cam.y !== 0 || cam.scale !== 1);
      if (applyCamera) {
        ctx.save();
        ctx.translate(cam.x, cam.y);
        ctx.scale(cam.scale, cam.scale);
      }

      // task-391：绘制前统一 reconcile 节点集合（折叠/展开/幽灵/VM 变化都只走这一处）
      this._syncScene();
      // task-391 rev26：presentation-only demo 连线（容器链 / 容器→KP），先于节点绘制（在底层）。
      this._presentationLinkDraws = this._drawPresentationLinks(ctx);
      const drawView = {
        calls,
        painters: this._scene.painters,
        hoverId: this._hoverId,
        highlightId: this._highlightId,
        selectedId: this._selectedId,
        selectedGroupId: this._selectedGroupId,
        selectedNeighbors: this._selectedNeighbors,
        focusNodeId: this._focusNodeId,
        groupHit: this._groupHit,
        groupLabelBoxes: this._groupLabelBoxes,
        degreeInfo: this._degreeInfo,
      };
      // task-391 rev38：背景化边（上一站拓扑）先于背景节点，保留原线型/方向语义
      this._backgroundEdgeDraws = this._drawBackgroundEdges(ctx);
      // 背景层（幽灵）先画
      this._scene.draw(ctx, drawView, "background");

      const focusId = this._hoverId || this._highlightId || null;
      const radiusOf = (id) => {
        const node = this._scene.get(id);
        return node ? node.radius : KP_BASE_RADIUS;
      };
      // Presentation-only 文件/section 分组：先画展开组包络；折叠组成员后续跳过
      const hidden = this._hiddenMemberIds();
      this._groupHit = [];
      this._groupLabelBoxes = [];
      drawView.groupHit = this._groupHit;
      drawView.groupLabelBoxes = this._groupLabelBoxes;
      const groupGeom = new Map();
      const selectedGroupId = this._selectedGroupId;
      for (const group of this._groups) {
        if (this._groupHasCollapsedAncestor(group.group_id)) continue;
        const members = group.member_ids
          .map((id) => ({ id, node: this._scene.get(id) }))
          .filter((m) => m.node)
          .map((m) => ({ id: m.id, p: { x: m.node.x, y: m.node.y } }));
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
        if (this._collapsedGroups.has(group.group_id)) continue;
        const g = groupGeom.get(group.group_id);
        const pad = 14;
        const x0 = g.minX - pad, y0 = g.minY - pad, x1 = g.maxX + pad, y1 = g.maxY + pad;
        const selectedGroup = selectedGroupId === group.group_id;
        // 组—成员从属细线（不只靠标签）
        if (ctx.beginPath && ctx.moveTo && ctx.lineTo && ctx.stroke) {
          for (const m of members) {
            ctx.beginPath();
            ctx.moveTo(g.cx, g.cy);
            ctx.lineTo(m.p.x, m.p.y);
            ctx.strokeStyle = selectedGroup ? "rgba(210,153,34,0.34)" : "rgba(88,166,255,0.14)";
            ctx.lineWidth = 1;
            if (ctx.setLineDash) ctx.setLineDash([2, 5]);
            ctx.stroke();
            if (ctx.setLineDash) ctx.setLineDash([]);
          }
        }
        if (ctx.beginPath) {
          if (ctx.roundRect) {
            ctx.beginPath();
            ctx.roundRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0), 10);
          } else if (ctx.rect) {
            ctx.beginPath();
            ctx.rect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
          }
          ctx.fillStyle = selectedGroup ? "rgba(210,153,34,0.10)" : "rgba(88,166,255,0.05)";
          if (ctx.fill) ctx.fill();
          ctx.strokeStyle = selectedGroup ? "rgba(210,153,34,0.95)" : "rgba(88,166,255,0.38)";
          ctx.lineWidth = selectedGroup ? 2 : 1;
          if (ctx.setLineDash) ctx.setLineDash([5, 4]);
          if (ctx.stroke) ctx.stroke();
          if (ctx.setLineDash) ctx.setLineDash([]);
          // 组标识：六边形图标 + 成员数徽标，区别于 KP 圆形
          drawHexagon(ctx, x0 + 8, y0 - 8, 5.5);
          ctx.fillStyle = selectedGroup ? "rgba(210,153,34,0.20)" : "rgba(88,166,255,0.18)";
          if (ctx.fill) ctx.fill();
          ctx.strokeStyle = selectedGroup ? "#d29922" : "#58a6ff";
          ctx.lineWidth = 1.2;
          if (ctx.stroke) ctx.stroke();
          drawGroupBadge(ctx, x0 + 20, y0 - 8, group.member_ids.length, selectedGroup ? "#d29922" : "#58a6ff");
        }
        this._groupHit.push({ kind: "rect", x0, y0, x1, y1, group, selected: selectedGroup });
        if (ctx.fillText) {
          ctx.font = VISUAL.labelFont;
          ctx.textAlign = "left";
          ctx.textBaseline = "bottom";
          const gtext = truncateTextWidth(ctx, groupLabel(group), Math.max(36, (x1 - x0) - 36));
          const gw = ctx.measureText ? ctx.measureText(gtext).width : gtext.length * 6;
          const box = { x: x0 + 28, y: y0 - 18, w: gw + 4, h: 16 };
          const overlapsPrev = this._groupLabelBoxes.some((b) =>
            !(box.x + box.w <= b.x || b.x + b.w <= box.x || box.y + box.h <= b.y || b.y + b.h <= box.y));
          if (!overlapsPrev) {
            ctx.lineWidth = VISUAL.labelHaloWidth;
            ctx.strokeStyle = VISUAL.halo;
            if (ctx.strokeText) ctx.strokeText(gtext, x0 + 30, y0 - 3);
            ctx.fillStyle = selectedGroup ? "#d29922" : VISUAL.nodeMuted || "#8b949e";
            ctx.fillText(gtext, x0 + 30, y0 - 3);
            calls.labels += 1;
            this._groupLabelBoxes.push(box);
          }
        }
      }

      // 边：只画 shown；折叠组成员隐藏；关系类型用线型/颜色区分
      const selectedId = this._selectedId;
      const selectionActive = !!(selectedId || selectedGroupId);
      for (const edge of this._edgeList) {
        const ends = edgeEndpoints(edge.id);
        if (!ends) continue;
        if (hidden.has(ends.source) || hidden.has(ends.target)) continue;
        const a = this._scene.get(ends.source);
        const b = this._scene.get(ends.target);
        if (!a || !b) continue;
        const selectionIncident = !!selectedId
          && (ends.source === selectedId || ends.target === selectedId);
        const groupIncident = !!selectedGroupId
          && this._selectedNeighbors.has(ends.source) && this._selectedNeighbors.has(ends.target);
        const incident = !!focusId && (ends.source === focusId || ends.target === focusId);
        const dim = selectionActive ? !(selectionIncident || groupIncident) : !!focusId && !incident;
        const alpha = dim ? VISUAL.edgeAlphaDim : (focusId || selectionActive ? VISUAL.edgeAlphaActive : VISUAL.edgeAlpha);
        const lineWidth = (incident || selectionIncident || groupIncident) ? VISUAL.edgeWidthActive : VISUAL.edgeWidth;
        const padR = Math.max(radiusOf(ends.source), radiusOf(ends.target)) + (incident || selectionIncident ? 2 : 0);
        drawDirectedEdge(
          ctx, a.x, a.y, b.x, b.y, padR,
          EDGE_COLORS[edge.type] || EDGE_COLORS.reference,
          lineWidth, alpha, VISUAL.arrowSize,
          EDGE_DASH[edge.type] || []
        );
        calls.edges += 1;
      }

      // 前景节点：唯一绘制入口（KP / 折叠簇 / VM cluster 都走 RenderScene.draw → RenderNode.draw）
      this._scene.draw(ctx, drawView, "foreground");

      // 标签：旧 KGviz LOD/避让 + 10px/halo（A3-1）
      const labelItems = [];
      for (const node of this._nodeById.values()) {
        if (node.presence !== "shown") continue;
        if (hidden.has(node.id)) continue;
        const sceneNode = this._scene.get(node.id);
        if (!sceneNode) continue;
        const p = { x: sceneNode.x, y: sceneNode.y };
        const baseR = sceneNode.radius;
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
      let labelLayout = null;
      if (Labels && typeof Labels.layoutNodeLabels === "function") {
        const layout = Labels.layoutNodeLabels(labelItems, {
          topN: 5,
          maxLabels: 14,
          lod: true,
          measureText: ctx.measureText ? (text) => ctx.measureText(text).width : undefined,
        });
        labelLayout = layout;
        // task-390：组标题占用屏幕空间，KP 标签不得覆盖组标签
        const groupBoxes = this._groupLabelBoxes || [];
        const overlapsGroup = (box) => groupBoxes.some((gb) => Labels.boxesOverlap
          ? Labels.boxesOverlap(box, gb, 1)
          : !(box.x + box.w <= gb.x || gb.x + gb.w <= box.x || box.y + box.h <= gb.y || gb.y + gb.h <= box.y));
        visible = labelItems.filter((it) => {
          if (!layout.visibleIds.has(it.id)) return false;
          const box = layout.boxes?.get?.(it.id);
          if (box && overlapsGroup(box)) return false;
          return true;
        });
        this._labelLayout = layout;
      }
      const textCtx = ctx;
      if (ctx.font && ctx.fillText) {
        ctx.font = VISUAL.labelFont;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        for (const it of visible) {
          const node = this._nodeById.get(it.id);
          const hovered = it.id === this._hoverId;
          const highlighted = it.id === this._highlightId;
          const box = labelLayout?.boxes?.get(it.id);
          const tx = box ? box.cx : it.x;
          const ty = box ? box.y + 1 : it.y;
          ctx.lineWidth = VISUAL.labelHaloWidth;
          ctx.strokeStyle = VISUAL.halo;
          if (ctx.strokeText) ctx.strokeText(it.text, tx, ty);
          if (hovered) ctx.fillStyle = VISUAL.nodeHover;
          else if (highlighted) ctx.fillStyle = VISUAL.nodeTarget;
          else if (node && node.range_ok === false) ctx.fillStyle = VISUAL.labelInvalid;
          else ctx.fillStyle = VISUAL.label;
          ctx.fillText(it.text, tx, ty);
          calls.labels += 1;
        }
      }
      if (applyCamera && ctx.restore) ctx.restore();
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
        positions: this._scene.size(),
        shownNodes: [...this._nodeById.values()].filter((n) => n.presence === "shown").length,
        shownEdges: this._edgeList.length,
        groups: this._groups.length,
        collapsedGroups: [...this._collapsedGroups],
        focusNode: this._focusNodeId,
        hiddenMembers: hidden.size,
        groupLabelCount: (this._groupLabelBoxes || []).length,
        labelLayout: this._labelLayout ? {
          visibleCount: this._labelLayout.visibleCount,
          allCount: this._labelLayout.allCount,
          hiddenCount: this._labelLayout.hiddenIds.length,
          overlapCount: this._labelLayout.overlapCount,
          overlapRate: this._labelLayout.allCount
            ? Math.round((this._labelLayout.overlapCount / Math.max(1, this._labelLayout.visibleCount)) * 1000) / 1000
            : 0,
          topIds: this._labelLayout.topIds,
          groupLabelCount: (this._groupLabelBoxes || []).length,
        } : null,
        camera: { ...this._camera },
        userAdjusted: this._userAdjusted,
        pinned: [...this._pinned],
        simulating: !!this._simulating,
        forceFrames: this._forceFrames || 0,
        forceMaxDisp: this._forceFrameLog.length ? this._forceFrameLog[this._forceFrameLog.length - 1].maxDisp : 0,
        layoutMode: "force",
        forceTicks: this._lastForceTicks || FORCE.ticks,
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
        positions: this._scene.size(),
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
    RenderNode,
    RenderScene,
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
    EDGE_DASH,
  };
  global.MemoriaGraphRendererAdapter = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
