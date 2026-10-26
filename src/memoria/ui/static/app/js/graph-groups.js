/**
 * 图谱节点群：并查集闭包（出边目标均在群内）+ 页签命名（M4 智能命名预留）
 */
(function (global) {
  "use strict";

  const ALL_GROUP_ID = "all";

  class UnionFind {
    constructor(ids) {
      this.parent = new Map();
      this.rank = new Map();
      for (const id of ids) {
        this.parent.set(id, id);
        this.rank.set(id, 0);
      }
    }

    find(x) {
      let p = this.parent.get(x);
      if (p === undefined) return x;
      if (p !== x) {
        p = this.find(p);
        this.parent.set(x, p);
      }
      return p;
    }

    union(a, b) {
      if (a === b) return;
      let ra = this.find(a);
      let rb = this.find(b);
      if (ra === rb) return;
      const rka = this.rank.get(ra) || 0;
      const rkb = this.rank.get(rb) || 0;
      if (rka < rkb) [ra, rb] = [rb, ra];
      else if (rka === rkb) this.rank.set(ra, rka + 1);
      this.parent.set(rb, ra);
    }
  }

  function truncateLabel(text, maxLen) {
    const s = String(text || "").trim();
    const max = Math.max(4, maxLen || 12);
    if (s.length <= max) return s;
    return s.slice(0, Math.max(1, max - 1)) + "…";
  }

  function nodeLabel(node, mode) {
    if (!node) return "";
    if (mode === "hub_id") return node.id || node.kp_id || "";
    return node.name || node.label || node.id || "";
  }

  function degreeMap(links) {
    const deg = new Map();
    const bump = (id) => deg.set(id, (deg.get(id) || 0) + 1);
    for (const l of links || []) {
      if (l.source) bump(l.source);
      if (l.target) bump(l.target);
    }
    return deg;
  }

  function pickHubNode(nodeIds, nodesById, links, labelMode) {
    const deg = degreeMap(links);
    let bestId = nodeIds[0];
    let bestScore = -1;
    for (const id of nodeIds) {
      const score = deg.get(id) || 0;
      if (score > bestScore) {
        bestScore = score;
        bestId = id;
      }
    }
    return nodesById.get(bestId) || { id: bestId, name: bestId };
  }

  /**
   * 并查集：每条边 union(source, target) → 出边闭包分量。
   * 无连边的单节点自成一群。
   */
  function computeGraphGroups(nodes, links, opts = {}) {
    const labelMode = opts.groupLabelMode || "hub_name";
    const labelMaxLen = opts.groupLabelMaxLen ?? 12;
    const nodesById = new Map((nodes || []).map((n) => [n.id, n]));
    const ids = [...nodesById.keys()];
    const uf = new UnionFind(ids);

    for (const l of links || []) {
      if (!l.source || !l.target) continue;
      if (!nodesById.has(l.source) || !nodesById.has(l.target)) continue;
      uf.union(l.source, l.target);
    }

    const buckets = new Map();
    for (const id of ids) {
      const root = uf.find(id);
      if (!buckets.has(root)) buckets.set(root, []);
      buckets.get(root).push(id);
    }

    const groups = [...buckets.entries()]
      .map(([rootId, nodeIds]) => {
        nodeIds.sort();
        const hub = pickHubNode(nodeIds, nodesById, links, labelMode);
        const label = truncateLabel(nodeLabel(hub, labelMode), labelMaxLen);
        return {
          id: rootId,
          rootId,
          nodeIds,
          size: nodeIds.length,
          hubId: hub.id,
          hubName: hub.name || hub.label || hub.id,
          label,
          edgeCount: (links || []).filter(
            (l) => nodeIds.includes(l.source) && nodeIds.includes(l.target)
          ).length,
        };
      })
      .sort((a, b) => b.size - a.size || a.label.localeCompare(b.label, "zh"));

    const nodeToGroup = new Map();
    for (const g of groups) {
      for (const id of g.nodeIds) nodeToGroup.set(id, g.id);
    }

    return {
      allGroupId: ALL_GROUP_ID,
      groups,
      nodeToGroup,
      totalGroups: groups.length,
    };
  }

  /** M4 SearchKernel 预留：智能群命名 */
  function suggestGroupLabel(group, nodes, links, opts = {}) {
    void nodes;
    void links;
    void opts;
    const mode = opts.groupLabelMode || "hub_name";
    const hub = { id: group.hubId, name: group.hubName };
    return {
      status: "ok",
      suggested: null,
      reason: "search_kernel_not_available",
      default: truncateLabel(nodeLabel(hub, mode), opts.groupLabelMaxLen ?? 12),
      hub_id: group.hubId,
    };
  }

  function filterGraphByGroup(nodes, links, groupsMeta, groupId) {
    if (!groupId || groupId === ALL_GROUP_ID) {
      return { nodes: nodes || [], links: links || [], groupId: ALL_GROUP_ID };
    }
    const g = (groupsMeta?.groups || []).find((x) => x.id === groupId);
    if (!g) {
      return { nodes: [], links: [], groupId };
    }
    const set = new Set(g.nodeIds);
    const fn = (nodes || []).filter((n) => set.has(n.id));
    const fl = (links || []).filter((l) => set.has(l.source) && set.has(l.target));
    return { nodes: fn, links: fl, groupId };
  }

  function buildLayoutLoadOpts(engine, viewOpts, groupId) {
    return {
      spreadFactor: viewOpts?.spreadFactor,
      groupId: groupId ?? ALL_GROUP_ID,
      groups: engine?.groups,
      groupSpacing: viewOpts?.groupSpacing ?? 260,
      distMode: viewOpts?.distMode ?? "grid",
      graphStyle: viewOpts?.graphStyle ?? "force",
    };
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // KGViz D-KGV-09（§6）：毛球态判定 —— 单条件 + 实测校准（2026-10-27 task-187）
  //   旧组合（labels>60 OR edges/nodes<4 OR avgdeg<8）在真实语料上【开局永远命中】；
  //   v0 改为单条件：最大连通分量占比 maxGroupShare ≥ 阈值。
  //   阈值来源（同一测量条件下实测，见报告 §2）：
  //     · hairball 真实语料：134/404 ⇒ 89.55%；HEAD archive 61/154 ⇒ 81.97%
  //     · 良好/稀疏语料：synthetic 6×5 群 ⇒ 16.67%；真实稀疏 KB 329/36 ⇒ 2.74%
  //   ⇒ 取 0.80 = min(实测 hairball 81.97%) − 1.97pp 容差（仍远高于良好语料上界）。
  //   注意：本判定是【粗粒度提示】，不是"图不可用"的硬门禁（设计 D-KGV-09 原意）。
  const HAIRBALL_MAX_GROUP_SHARE_THRESHOLD = 0.8;
  const HAIRBALL_CALIBRATION = Object.freeze({
    measuredAt: "2026-10-27",
    hairball: [
      { corpus: "docs/example/AAA_Vocab (worktree, post_build)", nodes: 134, edges: 404, maxGroupShare: 0.8955 },
      { corpus: "docs/example/AAA_Vocab (HEAD archive)", nodes: 61, edges: 154, maxGroupShare: 0.8197 },
    ],
    good: [
      { corpus: "synthetic 6 groups × 5 nodes", nodes: 30, edges: 24, maxGroupShare: 0.1667 },
      { corpus: "artifacts/baseline-kb/数字通信原理 (sparse)", nodes: 329, edges: 36, maxGroupShare: 0.0274 },
    ],
    derivation: "threshold = min(hairball measured 0.8197) - 0.0197 margin = 0.80",
  });

  /**
   * 毛球态判定（单条件：最大连通分量占比）。
   * 复用 computeGraphGroups 的 Union-Find（零新增字段）；若未传 groupsMeta 则现场算。
   * @returns {{isHairball:boolean, rule:string, threshold:number, metrics:object}}
   */
  function computeHairball(nodes, links, groupsMeta, opts = {}) {
    const nodeList = nodes || [];
    const linkList = links || [];
    const n = nodeList.length;
    const threshold = Number.isFinite(opts.threshold)
      ? Number(opts.threshold)
      : HAIRBALL_MAX_GROUP_SHARE_THRESHOLD;
    let sizes = [];
    const groups = groupsMeta?.groups;
    if (Array.isArray(groups)) {
      sizes = groups.map((g) => Number(g.size) || (Array.isArray(g.nodeIds) ? g.nodeIds.length : 0));
    } else {
      const present = new Set(nodeList.map((x) => x.id));
      const uf = new UnionFind([...present]);
      for (const l of linkList) {
        if (!l || !l.source || !l.target) continue;
        if (!present.has(l.source) || !present.has(l.target)) continue;
        uf.union(l.source, l.target);
      }
      const buckets = new Map();
      for (const id of present) {
        const root = uf.find(id);
        buckets.set(root, (buckets.get(root) || 0) + 1);
      }
      sizes = [...buckets.values()];
    }
    const componentCount = sizes.length;
    const maxGroupSize = sizes.length ? Math.max(...sizes) : 0;
    const maxGroupShare = n ? maxGroupSize / n : 0;
    const deg = degreeMap(linkList);
    const degreeValues = nodeList.map((x) => deg.get(x.id) || 0);
    const degreeSum = degreeValues.reduce((a, b) => a + b, 0);
    const metrics = {
      nodeCount: n,
      edgeCount: linkList.length,
      componentCount,
      maxGroupSize,
      maxGroupShare: Number(maxGroupShare.toFixed(4)),
      labels: n,
      edgesPerNode: n ? Number((linkList.length / n).toFixed(3)) : 0,
      avgDegree: n ? Number((degreeSum / n).toFixed(2)) : 0,
      zeroDegreeCount: degreeValues.filter((d) => d === 0).length,
    };
    const isHairball = n > 0 && maxGroupShare >= threshold;
    return {
      isHairball,
      rule: "max_group_share >= threshold",
      threshold,
      metrics,
      calibration: HAIRBALL_CALIBRATION,
    };
  }

  global.MemoriaGraphGroups = {
    ALL_GROUP_ID,
    computeGraphGroups,
    suggestGroupLabel,
    filterGraphByGroup,
    truncateLabel,
    buildLayoutLoadOpts,
  };
  global.MemoriaGraphHairball = {
    THRESHOLD: HAIRBALL_MAX_GROUP_SHARE_THRESHOLD,
    CALIBRATION: HAIRBALL_CALIBRATION,
    computeHairball,
  };
})(typeof window !== "undefined" ? window : globalThis);
