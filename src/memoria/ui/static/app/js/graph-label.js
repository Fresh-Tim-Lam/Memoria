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

  // ── KGViz D-KGV-06：标签 LOD/避让（可读性前置；不是性能优化）────────────────
  // 目标：134 个标签不再无条件全画；按【度数高 > 度数低】优先级做碰撞检测，
  //       被隐藏标签在 hover/缩放变稀疏后重新出现。
  // 纯函数（不依赖 DOM），2D 渲染层传入屏幕坐标与 measureText；机检直接复用。
  const LABEL_LOD_DEFAULTS = {
    fontSize: 10,
    labelHeight: 12,
    padX: 2,
    padY: 1,
    gap: 1,            // 两包围盒最小间距（px）
    topN: 10,          // 度数最高的 N 个节点标签【必然可见】
    maxLabels: 0,      // 0 = 不做硬上限（由碰撞自然限流）
  };

  /** 无 canvas 时的宽度估计（CJK 按 1em，ASCII 按 0.62em） */
  function estimateLabelWidth(text, fontSize) {
    const fs = fontSize || LABEL_LOD_DEFAULTS.fontSize;
    let w = 0;
    for (const ch of String(text || "")) {
      w += /[\u1100-\u11ff\u2e80-\u9fff\uff00-\uffef]/.test(ch) ? fs : fs * 0.62;
    }
    return Math.max(fs * 1.5, w);
  }

  function boxesOverlap(a, b, gap = 1) {
    return !(
      a.x + a.w + gap <= b.x ||
      b.x + b.w + gap <= a.x ||
      a.y + a.h + gap <= b.y ||
      b.y + b.h + gap <= a.y
    );
  }

  /** 标签候选位置（中心点偏移）：优先节点下方，其次上/右/左/斜向；用于给 topN 腾位置 */
  function labelCandidateCenters(item, w, h, fontH) {
    const r = Math.max(0, item.r || 0);
    const dx = r + 5 + w / 2;
    const dy = r + 4 + h / 2;
    const lane = h + 3;
    return [
      [0, dy],
      [0, -dy],
      [dx, 0],
      [-dx, 0],
      [0, dy + lane],
      [0, -dy - lane],
      [dx, -lane],
      [-dx, -lane],
      [dx, lane],
      [-dx, lane],
      [0, dy + lane * 2],
      [0, -dy - lane * 2],
    ].map(([ox, oy]) => ({ cx: item.x + ox, cy: item.y + oy, ox, oy }));
  }

  /**
   * 计算可见标签与包围盒（屏幕坐标）。
   * @param items [{id,text,x,y,r,degree}]
   * @param options {fontSize,labelHeight,padX,padY,gap,topN,maxLabels,hoverIds,lod,measureText}
   * @returns {{visibleIds:Set, boxes:Map, hiddenIds:string[], topIds:string[],
   *            overlapCount:number, visibleCount:number, allCount:number, lod:boolean}}
   */
  function layoutNodeLabels(items, options = {}) {
    const o = { ...LABEL_LOD_DEFAULTS, ...(options || {}) };
    const byId = new Map();
    for (const it of items || []) byId.set(it.id, it);
    const measure = typeof o.measureText === "function"
      ? o.measureText
      : (t) => estimateLabelWidth(t, o.fontSize);
    const lod = o.lod !== false;
    const hoverIds = new Set((o.hoverIds || []).filter((id) => byId.has(id)));
    const sorted = (items || []).slice().sort((a, b) => {
      const da = Number(a.degree) || 0;
      const db = Number(b.degree) || 0;
      if (db !== da) return db - da;
      return String(a.id).localeCompare(String(b.id));
    });
    const topIds = sorted.slice(0, Math.max(0, o.topN | 0)).map((it) => it.id);
    const topSet = new Set(topIds);
    const visibleIds = new Set();
    const boxes = new Map();
    const hiddenIds = [];
    const placed = [];
    let overlapCount = 0;

    const tryPlace = (item, forced) => {
      if (!item) return false;
      const text = String(item.text ?? "");
      const rawW = Math.max(1, Number(measure(text, o.fontSize)) || 1);
      const w = rawW + o.padX * 2;
      const h = o.labelHeight + o.padY * 2;
      const cands = labelCandidateCenters(item, w, h, o.labelHeight);
      for (const c of cands) {
        const box = { x: c.cx - w / 2, y: c.cy - h / 2, w, h, cx: c.cx, cy: c.cy, text };
        if (!placed.some((b) => boxesOverlap(box, b, o.gap))) {
          placed.push(box);
          boxes.set(item.id, box);
          visibleIds.add(item.id);
          return true;
        }
      }
      if (forced) {
        // topN / hover 必须可见：即使找不到空位也强制放（可能重叠 —— 由机检报告，不静默）
        const box = { x: cands[0].cx - w / 2, y: cands[0].cy - h / 2, w, h, cx: cands[0].cx, cy: cands[0].cy, text };
        placed.push(box);
        boxes.set(item.id, box);
        visibleIds.add(item.id);
        if (placed.some((b) => b !== box && boxesOverlap(box, b, o.gap))) overlapCount += 1;
        return true;
      }
      return false;
    };

    // 1) hover 最高优先（被隐藏的标签必须能出现）
    for (const id of hoverIds) tryPlace(byId.get(id), true);
    // 2) 度数最高 topN 必然可见
    for (const id of topIds) {
      if (visibleIds.has(id)) continue;
      tryPlace(byId.get(id), true);
    }
    // 3) 其余按优先级做碰撞避让；关闭 LOD 时全部强制显示（可回退 / 必红 fixture）
    let extraCount = 0;
    for (const item of sorted) {
      if (visibleIds.has(item.id)) continue;
      const placedOk = tryPlace(item, lod === false);
      if (!placedOk) {
        hiddenIds.push(item.id);
        continue;
      }
      extraCount += 1;
      if (lod && o.maxLabels > 0 && visibleIds.size >= o.maxLabels) break;
    }
    // 关闭 LOD 时把所有剩余未尝试的也补上（全部显示，用于回退/红态）
    if (!lod) {
      for (const item of sorted) {
        if (visibleIds.has(item.id)) continue;
        tryPlace(item, true);
      }
    }
    // 统计可见标签两两重叠数（机检口径）
    for (let i = 0; i < placed.length; i++) {
      for (let j = i + 1; j < placed.length; j++) {
        if (boxesOverlap(placed[i], placed[j], o.gap)) overlapCount += 1;
      }
    }
    return {
      visibleIds,
      boxes,
      hiddenIds,
      topIds,
      hoverIds: [...hoverIds],
      overlapCount,
      visibleCount: visibleIds.size,
      allCount: (items || []).length,
      lod,
    };
  }

  global.MemoriaGraphLabels = {
    LABEL_MODES,
    DEFAULT_LABEL,
    LABEL_LOD_DEFAULTS,
    truncate,
    resolveNodeDisplayLabel,
    resolveNodeHoverHtml,
    estimateLabelWidth,
    boxesOverlap,
    layoutNodeLabels,
  };
})(typeof window !== "undefined" ? window : globalThis);
