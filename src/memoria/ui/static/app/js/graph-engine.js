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

  class MemoriaGraphEngine {
    constructor() {
      this.nodes = [];
      this.links = [];
      this.rawEdges = [];
      this._listeners = Object.create(null);
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

    getOutgoingLinks(nodeId) {
      return this.links.filter((l) => l.source === nodeId);
    }

    edgeColor(type) {
      return EDGE_COLORS[type] || EDGE_COLORS.reference;
    }
  }

  global.MemoriaGraphEngine = MemoriaGraphEngine;
  global.MemoriaGraphEdgeColors = EDGE_COLORS;
})(typeof window !== "undefined" ? window : globalThis);
