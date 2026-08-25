/**
 * 图谱节点标签：短标签（画布） vs 详情（悬停）；M4 预留 smart 模式
 */
(function (global) {
  "use strict";

  const LABEL_MODES = {
    name_short: { label: "名称（缩短）", available: true },
    id: { label: "知识点 ID", available: true },
    name: { label: "名称（完整）", available: true },
    smart: { label: "智能摘要（M4 检索引擎）", available: false },
  };

  const DEFAULT_LABEL = {
    labelMode: "name_short",
    labelMaxLen: 8,
  };

  function truncate(text, maxLen) {
    const s = String(text ?? "").trim();
    const n = Math.max(2, maxLen | 0 || 8);
    if (s.length <= n) return s;
    return s.slice(0, Math.max(1, n - 1)) + "…";
  }

  function resolveNodeDisplayLabel(node, labelSettings) {
    const settings = { ...DEFAULT_LABEL, ...labelSettings };
    let mode = settings.labelMode || "name_short";
    if (mode === "smart" || !LABEL_MODES[mode]?.available) {
      mode = "name_short";
    }
    const name = node.name || node.label || node.id || "";
    const id = node.id || "";
    let raw = name;
    if (mode === "id") raw = id;
    else if (mode === "name") raw = name;
    else raw = name || id;
    if (mode === "name") return raw;
    return truncate(raw, settings.labelMaxLen);
  }

  function resolveNodeHoverHtml(node) {
    if (!node) return "";
    const name = node.name || node.label || node.id || "—";
    const id = node.id || "—";
    const file = node.file || "—";
    const desc = (node.description || "").trim();
    let html = `<span class="m0-graph-hint-title">${escapeHtml(name)}</span>`;
    html += `<span class="m0-graph-hint-meta">ID · ${escapeHtml(id)}</span>`;
    html += `<span class="m0-graph-hint-meta">${escapeHtml(file)}</span>`;
    if (desc) {
      html += `<span class="m0-graph-hint-desc">${escapeHtml(desc)}</span>`;
    }
    return html;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  global.MemoriaGraphLabels = {
    LABEL_MODES,
    DEFAULT_LABEL,
    truncate,
    resolveNodeDisplayLabel,
    resolveNodeHoverHtml,
  };
})(typeof window !== "undefined" ? window : globalThis);
