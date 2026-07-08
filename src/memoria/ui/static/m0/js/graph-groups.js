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
})(typeof window !== "undefined" ? window : globalThis);
