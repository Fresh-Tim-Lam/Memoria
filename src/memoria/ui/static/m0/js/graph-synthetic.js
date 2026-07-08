/**
 * Synthetic graph for layout stress tests (M2).
 */
(function (global) {
  "use strict";

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

  function node(i, fileIdx) {
    const id = `kp-${i}`;
    return {
      id,
      name: `知识点 ${i}`,
      label: `知识点 ${i}`,
      description: `synthetic node ${i}`,
      file: `synthetic/file-${fileIdx % 8}.md`,
      kp_id: id,
      range_ok: true,
      start_line: 1,
      end_line: 3,
    };
  }

  function edge(sourceId, targets, type = "reference") {
    return {
      type,
      source_id: sourceId,
      targets,
      relevance: 0.65,
    };
  }

  function syntheticGraph(nNodes, pattern = "small_world", opts = {}) {
    const n = Math.max(1, nNodes | 0);
    const avgDegree = opts.avgDegree ?? 4;
    const nGroups = opts.nGroups ?? 5;
    const seed = opts.seed ?? 0;
    let rng = seed;
    const rand = () => {
      rng = (rng * 1103515245 + 12345) & 0x7fffffff;
      return rng / 0x7fffffff;
    };

    const nodes = [];
    for (let i = 0; i < n; i++) nodes.push(node(i, i % Math.max(1, nGroups)));
    const ids = nodes.map((x) => x.id);
    const edges = [];

    if (pattern === "chain") {
      for (let i = 0; i < n - 1; i++) edges.push(edge(ids[i], [ids[i + 1]]));
    } else if (pattern === "star") {
      for (let i = 1; i < n; i++) edges.push(edge(ids[0], [ids[i]]));
    } else if (pattern === "partitioned") {
      const groups = Math.max(2, Math.min(nGroups, n));
      const size = Math.max(1, Math.floor(n / groups));
      for (let g = 0; g < groups; g++) {
        const start = g * size;
        const end = Math.min(n, start + size);
        const local = ids.slice(start, end);
        for (let i = 0; i < local.length - 1; i++) {
          edges.push(edge(local[i], [local[i + 1]]));
        }
        if (local.length > 2) edges.push(edge(local[0], [local[local.length - 1]], "extend"));
      }
    } else {
      const targetCount = Math.max(n - 1, Math.floor((n * avgDegree) / 2));
      const seen = new Set();
      let attempts = 0;
      while (seen.size < targetCount && attempts < targetCount * 20) {
        attempts++;
        const s = Math.floor(rand() * n);
        const t = Math.floor(rand() * n);
        if (s === t) continue;
        const key = `${ids[s]}->${ids[t]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        edges.push(edge(ids[s], [ids[t]]));
      }
    }

    const links = expandLinks(edges);
    return { nodes, edges, links };
  }

  global.MemoriaGraphSynthetic = {
    BENCHMARK_SCALES: [50, 100, 250, 500, 1000],
    BENCHMARK_PATTERNS: ["small_world", "partitioned", "star"],
    syntheticGraph,
    expandLinks,
  };
})(typeof window !== "undefined" ? window : globalThis);
