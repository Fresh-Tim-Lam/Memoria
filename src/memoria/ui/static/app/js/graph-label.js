/**
 * 图谱节点标签：短标签（画布） vs 详情（悬停）；M4 预留 smart 模式
 */
(function (global) {
  "use strict";

  const LABEL_MODES = {
    name_short: { labelKey: "graph.labelModes.name_short", available: true },
    id: { labelKey: "graph.labelModes.id", available: true },
    name: { labelKey: "graph.labelModes.name", available: true },
    smart: { labelKey: "graph.labelModes.smart", available: false },
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

  /**
   * 悬停详情 HTML。
   * KGViz D-KGV-03 附加约束：连续分位大小是「相对量」，会让人把排名读成重要 ⇒
   * 【必须】同时显示 degree 绝对原值（由调用方传入已本地化的 `degreeText`，本模块不依赖 i18n）。
   */
  function resolveNodeHoverHtml(node, opts) {
    if (!node) return "";
    const name = node.name || node.label || node.id || "—";
    const id = node.id || "—";
    const file = node.file || "—";
    const desc = (node.description || "").trim();
    const degreeText = opts && typeof opts.degreeText === "string" ? opts.degreeText.trim() : "";
    let html = `<span class="-graph-hint-title">${escapeHtml(name)}</span>`;
    if (degreeText) {
      html += `<span class="-graph-hint-degree">${escapeHtml(degreeText)}</span>`;
    }
    html += `<span class="-graph-hint-meta">ID · ${escapeHtml(id)}</span>`;
    html += `<span class="-graph-hint-meta">${escapeHtml(file)}</span>`;
    if (desc) {
      html += `<span class="-graph-hint-desc">${escapeHtml(desc)}</span>`;
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
