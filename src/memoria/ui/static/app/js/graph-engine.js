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

    getOutgoingLinks(nodeId) {
      return this.links.filter((l) => l.source === nodeId);
    }

    edgeColor(type) {
      return EDGE_COLORS[type] || EDGE_COLORS.reference;
    }
  }

  global.MemoriaGraphEngine = MemoriaGraphEngine;
  global.MemoriaGraphEdgeColors = EDGE_COLORS;
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
