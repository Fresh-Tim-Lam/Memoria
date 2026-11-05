/**
 * task-367 / S3-ADDENDUM-3 视觉回归机检（Node，无 DOM）：
 *  - 旧 KGviz 视觉常量（背景/节点色/hover/target/dim/invalid/标签/边色）
 *  - KP 连续 degree 分位半径（≈4.5–9.9px，单调、非分桶）
 *  - hover +3 / target +2
 *  - galaxy 渐变 + 标签 10px/halo + 边色/箭头
 * 运行：node tests/graph/ui/renderer_visual.test.js
 */
"use strict";
const path = require("path");
const assert = require("assert");
const ROOT = path.resolve(__dirname, "../../..");
const Adapter = require(path.join(ROOT, "src/memoria/ui/static/app/js/graph-multilevel/renderer-adapter.js"));

const results = [];
function check(name, fn) {
  try {
    fn();
    results.push({ name, ok: true });
  } catch (err) {
    results.push({ name, ok: false, error: String((err && err.stack) || err) });
    throw err;
  }
}

function makeCtx() {
  const ctx = {
    fillStyles: [], strokeStyles: [], fonts: [], strokeAlphas: [], calls: 0,
    _alpha: 1,
    font: "10px sans-serif",
    get globalAlpha() { return this._alpha; },
    set globalAlpha(v) { this._alpha = v; },
    clearRect() { this.calls += 1; },
    fillRect() { this.calls += 1; this.fillStyles.push(this.fillStyle); },
    beginPath() { this.calls += 1; },
    closePath() {},
    moveTo() {},
    lineTo() {},
    arc() {},
    stroke() { this.calls += 1; this.strokeStyles.push(this.strokeStyle); this.strokeAlphas.push(this.globalAlpha); },
    fill() { this.calls += 1; this.fillStyles.push(this.fillStyle); },
    fillText() { this.calls += 1; this.fonts.push(this.font); this.fillStyles.push(this.fillStyle); },
    strokeText() { this.calls += 1; this.fonts.push(this.font); this.strokeStyles.push(this.strokeStyle); },
    setLineDash() {},
    measureText(t) { return { width: String(t).length * 6 }; },
    createRadialGradient() {
      return { addColorStop() {} };
    },
  };
  return ctx;
}
function makeHost() {
  return {
    createCanvas(w, h) {
      return {
        canvas: {
          width: Math.round(w), height: Math.round(h),
          getBoundingClientRect: () => ({ left: 0, top: 0, width: 640, height: 480 }),
          style: {}, setAttribute() {},
        },
        ctx: makeCtx(),
      };
    },
    append() {}, remove() {}, on() {}, off() {},
    rect: () => ({ left: 0, top: 0, width: 640, height: 480 }),
    dpr: () => 1,
  };
}

const VM = {
  view_model_id: "vm_visual_parity",
  level_id: "LL", level_label: "知识点", dimension_id: "A", view_family_id: "default",
  nodes: [
    { id: "a", kind: "kp", label: "A", role: "member", presence: "shown" },
    { id: "b", kind: "kp", label: "B", role: "member", presence: "shown" },
    { id: "c", kind: "kp", label: "C", role: "member", presence: "shown" },
    { id: "d", kind: "kp", label: "D", role: "member", presence: "shown", range_ok: false },
  ],
  edges: [
    { id: "contain|a|b", type: "contain", presence: "shown" },
    { id: "reference|b|c", type: "reference", presence: "shown" },
    { id: "extend|c|d", type: "extend", presence: "shown" },
    { id: "semantic|a|d", type: "semantic", presence: "shown" },
  ],
};
const PRESENTATION = { degrees: { a: 10, b: 0, c: 4, d: 2 }, files: { a: "a.md" } };

function run() {
  check("old_kgviz_visual_constants", () => {
    assert.deepStrictEqual(
      { bg: Adapter.VISUAL.bg, node: Adapter.VISUAL.node, hover: Adapter.VISUAL.nodeHover,
        target: Adapter.VISUAL.nodeTarget, dim: Adapter.VISUAL.nodeDim,
        invalid: Adapter.VISUAL.nodeInvalid, label: Adapter.VISUAL.label,
        labelInvalid: Adapter.VISUAL.labelInvalid, halo: Adapter.VISUAL.halo },
      { bg: "#0a0d13", node: "#c9d1d9", hover: "#f0f6fc", target: "#79c0ff",
        dim: "#3d4350", invalid: "#3a4152", label: "#adbac7",
        labelInvalid: "#6e7681", halo: "rgba(13,17,23,0.92)" }
    );
    assert.strictEqual(Adapter.VISUAL.labelFont, "10px system-ui, sans-serif");
    assert.strictEqual(Adapter.VISUAL.labelHaloWidth, 3);
    assert.deepStrictEqual(Adapter.EDGE_COLORS.contain, "#3fb950");
    assert.deepStrictEqual(Adapter.EDGE_COLORS.reference, "#58a6ff");
    assert.deepStrictEqual(Adapter.EDGE_COLORS.extend, "#d29922");
    assert.deepStrictEqual(Adapter.EDGE_COLORS.semantic, "#e06c75");
  });

  check("continuous_degree_radius_range_and_monotonic", () => {
    const distinct = [0, 1, 2, 4, 7, 10];
    const range = Adapter.sizingRangeForBase(6);
    assert.strictEqual(range.min, 4.5);
    assert.ok(Math.abs(range.max - 9.9) < 1e-9);
    let prev = -1;
    for (const degree of distinct) {
      const r = Adapter.radiusForDegree(degree, distinct, 6);
      assert.ok(r >= prev, `degree=${degree} 半径未单调：${r} < ${prev}`);
      assert.ok(r >= 4.5 - 1e-9 && r <= 9.9 + 1e-9, `degree=${degree} 半径越界 ${r}`);
      prev = r;
    }
    // 非分桶：中间 degree 的 t 是连续 rank，不是就近档位
    assert.ok(Math.abs(Adapter.radiusForDegree(4, distinct, 6) - (4.5 + 5.4 * (3 / 5))) < 1e-9);
    // 无统计时用 base（6）
    assert.strictEqual(Adapter.nodeRadius({ id: "x", kind: "kp" }, { map: new Map(), distinct: [] }), 6);
  });

  check("hover_target_radius_bonus", () => {
    const info = Adapter.normalizedDegrees(PRESENTATION.degrees);
    const node = { id: "a", kind: "kp" };
    const base = Adapter.nodeRadius(node, info);
    assert.ok(Math.abs(Adapter.visualRadius(node, info, true, false) - (base + 3)) < 1e-9, "hover 未 +3");
    assert.ok(Math.abs(Adapter.visualRadius(node, info, false, true) - (base + 2)) < 1e-9, "target 未 +2");
  });

  check("galaxy_gradient_endpoints", () => {
    assert.strictEqual(Adapter.galaxyColor(0), "rgb(139,148,158)");
    assert.strictEqual(Adapter.galaxyColor(1), "rgb(240,246,252)");
    assert.strictEqual(Adapter.galaxyColor(0.5), "rgb(190,197,205)");
  });

  check("renderer_applies_degree_colors_labels_and_edges", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D({ clientWidth: 640, clientHeight: 480 }, { host, presentation: PRESENTATION });
    const summary = r.render({ clientWidth: 640, clientHeight: 480 }, VM);
    assert.strictEqual(summary.status, "ok");
    const ctx = host.createCanvas; // noop
    void ctx;
    // 半径按 degree 连续
    const radii = ["a", "b", "c", "d"].map((id) => r._radiusById.get(id));
    assert.ok(radii[0] > radii[2] && radii[2] > radii[3] && radii[3] > radii[1], `半径未按 degree 单调：${radii}`);
    // 画布背景
    const c = r._ctx;
    assert.ok(c.fillStyles.includes("#0a0d13"), "未绘制旧画布背景 #0a0d13");
    // galaxy 渐变被使用
    assert.ok(c.fillStyles.some((s) => typeof s === "string" && s.startsWith("rgb(")), "未使用 galaxy 渐变节点色");
    // 标签 10px + halo
    assert.ok(c.fonts.includes("10px system-ui, sans-serif"), "标签字体不是 10px system-ui");
    assert.ok(c.strokeStyles.includes("rgba(13,17,23,0.92)"), "标签 halo 缺失");
    assert.ok(c.fillStyles.includes("#adbac7"), "标签颜色不是 #adbac7");
    // 边色（4 类型）
    for (const color of ["#3fb950", "#58a6ff", "#d29922", "#e06c75"]) {
      assert.ok(c.strokeStyles.includes(color), `缺边色 ${color}`);
    }
    assert.strictEqual(r.lastRender.visual.edgeColors.contain, "#3fb950");
  });

  check("hover_and_target_fill_colors", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D({ clientWidth: 640, clientHeight: 480 }, { host, presentation: PRESENTATION });
    r.render({ clientWidth: 640, clientHeight: 480 }, VM);
    r._hoverId = "a";
    r._highlightId = "b";
    r._draw();
    const styles = r._ctx.fillStyles;
    assert.ok(styles.includes("#f0f6fc"), "hover 节点色 #f0f6fc 缺失");
    assert.ok(styles.includes("#79c0ff"), "target 节点色 #79c0ff 缺失");
    assert.ok(styles.includes("#3d4350"), "dim 节点色 #3d4350 缺失");
    assert.ok(styles.includes("#3a4152"), "invalid 节点色 #3a4152 缺失");
  });

  console.log(JSON.stringify({ suite: "renderer_visual", results, passed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length }));
}

run();


