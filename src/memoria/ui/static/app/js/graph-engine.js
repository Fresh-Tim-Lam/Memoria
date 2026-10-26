/**
 * Memoria GraphEngine — 数据层 + 事件（与 Shell / 渲染解耦）
 */
(function (global) {
  "use strict";

  const EDGE_COLORS = {
    contain: "#3fb950",
    reference: "#58a6ff",
    extend: "#d29922",
  };

  // ── KGViz D-KGV-13（人裁决②）：节点尺寸【连续变化】，无档位 ────────────────
  // 人裁决：视觉尺寸 = 基准 × [75%, 165%]（线性尺寸）；基准 = 用户 nodeRadius 设置（默认 6.0）。
  // radius(d) = R_MIN + (R_MAX - R_MIN) · t(d)，t = 连续分位（percentile-rank，**非分桶**）。
  // 设计：docs/design/kg-visualization-v0.md §1.2-1.3（冻结）。以下均为纯函数，供机检复用。
  const SIZE_RATIO_MIN = 0.75;
  const SIZE_RATIO_MAX = 1.65;
  const DEFAULT_BASE_RADIUS = 6.0;

  function normalizeBaseRadius(baseRadius) {
    const n = Number(baseRadius);
    return Number.isFinite(n) && n > 0 ? n : DEFAULT_BASE_RADIUS;
  }

  /** 由用户 nodeRadius 设置派生连续半径区间（U-KGV-2：v0 按【随基准缩放】实现） */
  function sizingRangeForBase(baseRadius) {
    const b = normalizeBaseRadius(baseRadius);
    return { min: b * SIZE_RATIO_MIN, max: b * SIZE_RATIO_MAX };
  }

  /**
   * 无向度：每条 link 的 source / target 各计一次。
   * 与 2D `_galaxyStats()`、tooltip「连接数」、T-census 的 degree 口径一致。
   */
  function computeUndirectedDegrees(nodes, links) {
    const deg = new Map();
    for (const n of nodes || []) deg.set(n.id, 0);
    const bump = (id) => {
      if (!id) return;
      deg.set(id, (deg.get(id) || 0) + 1);
    };
    for (const l of links || []) {
      if (!l) continue;
      bump(l.source);
      bump(l.target);
    }
    return deg;
  }

  /** 当前语料里出现过的 distinct degree（升序）；用于连续分位 t(d) */
  function distinctSortedDegrees(degreeMap, nodeIds) {
    const set = new Set();
    for (const id of nodeIds || []) {
      const d = degreeMap.get(id);
      if (typeof d === "number") set.add(d);
    }
    return [...set].sort((a, b) => a - b);
  }

  /**
   * t(d) = (#distinct degree 值 < d) / (K-1)，K = distinct degree 数。
   * · 单调不减； · min degree ⇒ t=0，max degree ⇒ t=1（最厚节点可达 R_MAX）；
   * · 同 degree ⇒ 同 t（正确行为，不是分桶）； · 不取整、不量化 ⇒ 无档位。
   */
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

  /** 连续尺寸映射：degree → 半径 px（未取整，保留浮点连续性） */
  function radiusForDegree(degree, distinctSorted, baseRadius) {
    const range = sizingRangeForBase(baseRadius);
    const t = normalizedRankT(degree, distinctSorted);
    return range.min + (range.max - range.min) * t;
  }

  function expandLinks(edges) {
    const links = [];
    for (const e of edges || []) {
      const source = e.source_id;
      if (!source) continue;
      for (const target of e.targets || []) {
        if (!target || target === source) continue;
        links.push({
          source,
          target,
          type: e.type || "reference",
          relevance: e.relevance ?? 0.5,
        });
      }
    }
    return links;
  }

  // ── KGViz D-KGV-07：布局确定性种子（2D/3D 共用；非力导向参数，只替换随机源）───────
  // 同一语料 + 同一种子 ⇒ 初始化坐标字节级一致；换种子 ⇒ 坐标不同（证明随机性仍在）。
  // 默认固定种子；`setLayoutSeed` 仅供测试/未来设置项暴露（v0 不做 UI）。
  const DEFAULT_LAYOUT_SEED = 0x9e3779b9;

  /** mulberry32：32-bit 确定性 PRNG，返回 [0,1) 浮点。 */
  function createSeededRandom(seed) {
    let a = seed >>> 0;
    return function seededRandom() {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /** FNV-1a 32-bit 字符串哈希（用于从语料身份派生种子；v0 默认不用，保留给设置项/测试）。 */
  function hashStringToSeed(str) {
    let h = 0x811c9dc5;
    const s = String(str || "");
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
  }

  class MemoriaGraphEngine {
    constructor() {
      this.nodes = [];
      this.links = [];
      this.rawEdges = [];
      this._listeners = Object.create(null);
      this._degreeMap = new Map();
      this._degreeDistinct = [];
      this._layoutSeed = DEFAULT_LAYOUT_SEED;
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
          console.error("[GraphEngine]", event, err);
        }
      }
    }

    loadPayload(payload, groupOpts) {
      const nodes = (payload?.nodes || []).map((n) => ({
        id: n.id,
        name: n.name || n.label || n.id,
        label: n.label || n.name || n.id,
        description: (n.description || "").trim(),
        file: n.file,
        kp_id: n.kp_id || n.id,
        range_ok: !!n.range_ok,
        start_line: n.start_line,
        end_line: n.end_line,
      }));
      this.rawEdges = payload?.edges || [];
      this.links = expandLinks(this.rawEdges);
      this.nodes = nodes;
      // D-KGV-13：一次 O(N+E) 建度表 + distinct 度表；2D 连续大小 / tooltip 原值共用同一口径
      this._degreeMap = computeUndirectedDegrees(this.nodes, this.links);
      this._degreeDistinct = distinctSortedDegrees(
        this._degreeMap,
        this.nodes.map((n) => n.id)
      );
      const gopts = groupOpts || {};
      if (global.MemoriaGraphGroups) {
        this.groups = global.MemoriaGraphGroups.computeGraphGroups(
          this.nodes,
          this.links,
          gopts
        );
      } else {
        this.groups = { groups: [], nodeToGroup: new Map(), allGroupId: "all", totalGroups: 0 };
      }
      this._emit("load", {
        nodes: this.nodes,
        links: this.links,
        groups: this.groups,
      });
      // KGViz D-KGV-09（§6）：毛球态判定 —— 复用前端 Union-Find 分组，零新增字段。
      // 结果挂在 engine 上并发出 `hairball` 事件，供未来 UI 提示消费（当前暂无 UI 消费方）。
      if (global.MemoriaGraphHairball) {
        this.hairball = global.MemoriaGraphHairball.computeHairball(
          this.nodes,
          this.links,
          this.groups
        );
        this._emit("hairball", this.hairball);
      } else {
        this.hairball = null;
      }
      return this;
    }

    getNode(id) {
      return this.nodes.find((n) => n.id === id) || null;
    }

    /** 节点「连接数」绝对原值（无向度；tooltip 必须显示它，D-KGV-03 附加约束） */
    degreeOf(id) {
      return this._degreeMap.get(id) || 0;
    }

    /** 当前语料 distinct degree（升序），供连续分位映射使用 */
    degreeDistinct() {
      return this._degreeDistinct;
    }

    /** 连续尺寸：degree → 半径 px（D-KGV-13；不含 hover/focus 加成） */
    radiusForNode(id, baseRadius) {
      return radiusForDegree(this.degreeOf(id), this._degreeDistinct, baseRadius);
    }

    sizingRange(baseRadius) {
      return sizingRangeForBase(baseRadius);
    }

    /** 当前布局种子（D-KGV-07）；默认固定，测试/设置可用 setLayoutSeed 覆盖 */
    layoutSeed() {
      return this._layoutSeed >>> 0;
    }

    setLayoutSeed(seed) {
      const n = Number(seed);
      this._layoutSeed = Number.isFinite(n) ? n >>> 0 : DEFAULT_LAYOUT_SEED;
      return this._layoutSeed;
    }

    /** 毛球态判定结果（D-KGV-09；loadPayload 后可用；无 groups 扩展时 null） */
    hairballReport() {
      return this.hairball || null;
    }

    getOutgoingLinks(nodeId) {
      return this.links.filter((l) => l.source === nodeId);
    }

    edgeColor(type) {
      return EDGE_COLORS[type] || EDGE_COLORS.reference;
    }
  }

  // ── KGViz D-KGV-15（§8 T-double）：视觉通道编码声明 + 可机检「双编码冲突」 ──────
  // 判定口径（冻结）：同变量 + 同方向 = 冗余强化 ⇒ PASS；不同变量或方向相反 ⇒ 冲突。
  // 声明必须与生产渲染公式一致（tests/test_kgviz_hairball_tdouble.py 有静态断言 +
  // 真机相关性测量双重校验；改公式必须同步改这里，否则 T-double 会报/漏报）。
  const VISUAL_CHANNELS = Object.freeze([
    {
      id: "2d.nodeRadius",
      surface: "2d",
      channel: "size",
      variable: "degree",
      direction: 1,
      source: "graph-view-2d.js#_radiusForNode / engine.radiusForNode（连续分位，degree 越大半径越大）",
    },
    {
      id: "2d.galaxyColor",
      surface: "2d",
      channel: "color",
      variable: "degree",
      direction: 1,
      source: "graph-view-2d.js#galaxyNodeColor2D(ratio)：ratio 越大越亮",
    },
    {
      id: "2d.galaxyHalo",
      surface: "2d",
      channel: "brightness",
      variable: "degree",
      direction: 1,
      source: "graph-view-2d.js#halo = 0.14 + ratio * 0.3（galaxy 分支）",
    },
    {
      id: "3d.nodeRadius",
      surface: "3d",
      channel: "size",
      variable: null,
      direction: 0,
      source: "graph-view-3d.js#_rebuildGraph 节点 scale 恒 1（D-KGV-04：3D 等大）",
    },
    {
      id: "3d.galaxyColor",
      surface: "3d",
      channel: "color",
      variable: "degree",
      direction: 1,
      source: "graph-view-3d.js#galaxyColor3D(ratio)",
    },
    {
      id: "3d.galaxyEmissive",
      surface: "3d",
      channel: "brightness",
      variable: "degree",
      direction: 1,
      source: "graph-view-3d.js#emissiveIntensity = 0.25 + ratio * 0.45",
    },
    {
      id: "3d.galaxyHalo",
      surface: "3d",
      channel: "brightness",
      variable: "degree",
      direction: 1,
      source: "graph-view-3d.js#halo.material.opacity = boost opacity（半径不随 degree 变，D-KGV-16）",
    },
  ]);

  /**
   * 按 D-KGV-15 检查双编码：同 surface 内每个变量只能有一个方向。
   * @param {Array} channels 通道声明（默认 VISUAL_CHANNELS）
   * @returns {{pass:boolean, conflicts:Array, bySurface:object, encodedVariables:string[]}}
   */
  function checkVisualEncoding(channels) {
    const list = (channels || VISUAL_CHANNELS).filter((c) => c && typeof c === "object");
    const bySurface = Object.create(null);
    const conflicts = [];
    for (const ch of list) {
      if (ch.variable == null) continue; // 该通道不编码变量（如 3D 等大半径）⇒ 不参与冲突
      const surface = String(ch.surface || "unknown");
      const bucket = bySurface[surface] || (bySurface[surface] = Object.create(null));
      const prev = bucket[ch.variable];
      if (prev) {
        const dirA = Math.sign(Number(prev.direction) || 0);
        const dirB = Math.sign(Number(ch.direction) || 0);
        if (dirA !== dirB && dirA !== 0 && dirB !== 0) {
          conflicts.push({
            surface,
            variable: ch.variable,
            channels: [prev.id, ch.id],
            reason: "opposite_direction",
          });
        }
      } else {
        bucket[ch.variable] = ch;
      }
    }
    // 不同变量：同一 surface 里存在 ≥2 个非 null 变量 ⇒ 检查它们是否同时"同向/冲突"
    for (const surface of Object.keys(bySurface)) {
      const vars = Object.keys(bySurface[surface]);
      if (vars.length > 1) {
        for (let i = 0; i < vars.length; i++) {
          for (let j = i + 1; j < vars.length; j++) {
            conflicts.push({
              surface,
              variable: vars[i],
              otherVariable: vars[j],
              channels: [bySurface[surface][vars[i]].id, bySurface[surface][vars[j]].id],
              reason: "different_variables",
            });
          }
        }
      }
    }
    const encodedVariables = [
      ...new Set(list.filter((c) => c.variable != null).map((c) => String(c.variable))),
    ];
    return {
      pass: conflicts.length === 0,
      conflicts,
      bySurface,
      encodedVariables,
      channels: list.map((c) => ({ id: c.id, surface: c.surface, variable: c.variable, direction: c.direction })),
    };
  }

  global.MemoriaGraphEngine = MemoriaGraphEngine;
  global.MemoriaGraphEdgeColors = EDGE_COLORS;
  // T-double 机检出口（声明 + 检查）
  global.MemoriaGraphVisualChannels = {
    CHANNELS: VISUAL_CHANNELS,
    check: checkVisualEncoding,
  };
  // 纯函数出口（机检 T-size-2/3/4 直接用；生产由 engine 实例方法调用）
  global.MemoriaGraphSizing = {
    SIZE_RATIO_MIN,
    SIZE_RATIO_MAX,
    DEFAULT_BASE_RADIUS,
    normalizeBaseRadius,
    sizingRangeForBase,
    computeUndirectedDegrees,
    distinctSortedDegrees,
    normalizedRankT,
    radiusForDegree,
  };
  // D-KGV-07：布局确定性种子纯函数（layout-2d/3d 各自注入；机检直接用）
  global.MemoriaGraphSeed = {
    DEFAULT_LAYOUT_SEED,
    createSeededRandom,
    hashStringToSeed,
  };
})(typeof window !== "undefined" ? window : globalThis);
