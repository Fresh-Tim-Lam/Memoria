/**
 * task-380 P0 机检（Node，无 DOM）：demo 语料 fixture 上的默认 hub / focus / 分组 / 布局。
 * 运行：node tests/graph/ui/renderer_demo_p0.test.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const ROOT = path.resolve(__dirname, "../../..");
const Adapter = require(path.join(ROOT, "src/memoria/ui/static/app/js/graph-multilevel/renderer-adapter.js"));
const FIXTURE = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/demo-p0-vm.json"), "utf8"));
const results = [];
function check(name, fn) {
  try { fn(); results.push({ name, ok: true }); }
  catch (err) { results.push({ name, ok: false, error: String((err && err.stack) || err) }); throw err; }
}
function makeCtx() {
  return {
    fillStyles: [], strokeStyles: [], fonts: [], strokeAlphas: [], calls: 0,
    _alpha: 1, font: "10px sans-serif",
    get globalAlpha() { return this._alpha; }, set globalAlpha(v) { this._alpha = v; },
    clearRect() {}, fillRect() { this.fillStyles.push(this.fillStyle); }, beginPath() {}, closePath() {},
    moveTo() {}, lineTo() {}, arc() {}, rect() {}, stroke() { this.strokeStyles.push(this.strokeStyle); this.strokeAlphas.push(this.globalAlpha); },
    fill() { this.fillStyles.push(this.fillStyle); }, fillText() { this.fonts.push(this.font); this.fillStyles.push(this.fillStyle); },
    strokeText() { this.fonts.push(this.font); this.strokeStyles.push(this.strokeStyle); },
    save() {}, restore() {}, setLineDash() {}, measureText(t) { return { width: String(t).length * 6 }; },
    createRadialGradient() { return { addColorStop() {} }; },
  };
}
function makeHost() {
  return {
    createCanvas(w, h) {
      return {
        canvas: { width: w | 0, height: h | 0, getBoundingClientRect: () => ({ left: 0, top: 0, width: w, height: h }), style: {}, setAttribute() {} },
        ctx: makeCtx(),
      };
    },
    append() {}, remove() {}, on() {}, off() {}, rect: () => ({ left: 0, top: 0, width: 325, height: 520 }), dpr: () => 1,
  };
}
function hubId(presentation, vm) {
  const degrees = presentation.degrees || {};
  const shown = vm.nodes.filter((n) => (n.presence || "shown") === "shown" && n.kind === "kp").map((n) => String(n.id));
  return shown.sort((a, b) => (Number(degrees[b]) || 0) - (Number(degrees[a]) || 0) || a.localeCompare(b))[0];
}
function spread(positions) {
  const xs = [...positions.values()].map((p) => p.x);
  const ys = [...positions.values()].map((p) => p.y);
  return {
    xSpread: Math.max(...xs) - Math.min(...xs),
    ySpread: Math.max(...ys) - Math.min(...ys),
    distinctX: new Set(xs.map((x) => Math.round(x))).size,
    distinctY: new Set(ys.map((y) => Math.round(y))).size,
  };
}
async function checkAsync(name, fn) {
  try { await fn(); results.push({ name, ok: true }); }
  catch (err) { results.push({ name, ok: false, error: String((err && err.stack) || err) }); throw err; }
}

function run() {
  const vm = FIXTURE.vm;
  const presentation = FIXTURE.presentation;
  const shown = vm.nodes.filter((n) => (n.presence || "shown") === "shown" && n.kind === "kp").map((n) => String(n.id));
  const hub = hubId(presentation, vm);

  check("demo_fixture_has_focus_and_groups", () => {
    assert.ok(shown.length >= 2, `demo 默认 shown=${shown.length}，应 >=2`);
    assert.ok(shown.includes(hub), `hub ${hub} 不在 shown`);
    assert.ok(presentation.groups && presentation.groups.length >= 1, "demo 缺 presentation.groups");
    const groupMembers = new Set(presentation.groups.flatMap((g) => g.member_ids));
    for (const id of shown) assert.ok(groupMembers.has(id), `shown ${id} 未被任何 group 覆盖`);
    for (const g of presentation.groups) {
      assert.strictEqual(g.presentation_only, true, "group 未标 presentation_only");
      assert.ok(!("kind" in g) && !("presence" in g), "group 不得伪造 VM 字段");
    }
  });

  check("focus_centered_layout_not_vertical_collapse", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D({ clientWidth: 325, clientHeight: 520 }, { host, presentation });
    r.setFocusNode(hub);
    r.render({ clientWidth: 325, clientHeight: 520 }, vm);
    const p = r._positions.get(hub);
    assert.ok(p, "hub 无位置");
    assert.ok(Math.abs(p.x - 162.5) < 1 && Math.abs(p.y - 260) < 1, `focus 未居中：${JSON.stringify(p)}`);
    const s = spread(r._positions);
    assert.ok(s.xSpread > 80 && s.ySpread > 80, `布局塌缩：xSpread=${s.xSpread} ySpread=${s.ySpread}`);
    assert.ok(s.distinctX >= 3 && s.distinctY >= 3, `布局成一条线：distinctX=${s.distinctX} distinctY=${s.distinctY}`);
  });

  check("presentation_groups_collapse_expand_without_vm_change", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D({ clientWidth: 325, clientHeight: 520 }, { host, presentation });
    r.setFocusNode(hub);
    r.render({ clientWidth: 325, clientHeight: 520 }, vm);
    assert.strictEqual(r.lastRender.groups, presentation.groups.length);
    const group = r.getGroups()[0];
    r.toggleGroup(group.group_id);
    assert.strictEqual(r.isGroupCollapsed(group.group_id), true);
    assert.ok(r.lastRender.hiddenMembers >= group.member_ids.length, "折叠后成员未隐藏");
    // group 命中盒存在（点击可展开）
    const hit = (r._groupHit || []).find((h) => h.group.group_id === group.group_id);
    assert.ok(hit, "折叠组缺少可点击命中盒");
    r.toggleGroup(group.group_id);
    assert.strictEqual(r.isGroupCollapsed(group.group_id), false);
    assert.strictEqual(r.lastRender.hiddenMembers, 0);
  });

  check("focus_switch_recenters_and_relayouts", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D({ clientWidth: 325, clientHeight: 520 }, { host, presentation });
    r.setFocusNode(hub);
    r.render({ clientWidth: 325, clientHeight: 520 }, vm);
    const other = shown.find((id) => id !== hub);
    r.setFocusNode(other);
    const upd = r.update(vm, {});
    const p = r._positions.get(other);
    assert.ok(p, "新 focus 无位置");
    assert.ok(Math.abs(p.x - 162.5) < 1 && Math.abs(p.y - 260) < 1, `点击/切换 focus 未重新居中：${JSON.stringify(p)}`);
    assert.ok(upd.moved > 0, "focus 切换后位置未重排");
  });

  return { vm, presentation, shown, hub };
}

async function runAsync(ctx) {
  const { vm, presentation, hub } = ctx;
  await checkAsync("deferred_first_render_waits_for_layout_not_800_fallback", async () => {
    const host = makeHost();
    // 首帧容器尚未布局（0×0），稍后变成真实 325×583
    const dims = { width: 0, height: 0 };
    const container = {
      clientWidth: 0, clientHeight: 0,
      getBoundingClientRect: () => ({ left: 0, top: 0, width: dims.width, height: dims.height }),
    };
    const r = new Adapter.Renderer2D(container, { host, presentation });
    r.setFocusNode(hub);
    const first = r.render(container, vm);
    assert.strictEqual(first.status, "deferred", "零尺寸时首帧未推迟");
    assert.ok(!r._canvas, "零尺寸时不应先创建 canvas");
    dims.width = 325; dims.height = 583;
    container.clientWidth = 325; container.clientHeight = 583;
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.ok(r._canvas, "布局稳定后仍未渲染");
    assert.strictEqual(r._canvas.width, 325, `backing 宽不是实测 325：${r._canvas.width}`);
    assert.strictEqual(r._canvas.height, 583, `backing 高不是实测 583：${r._canvas.height}`);
    assert.strictEqual(r._canvas.style.width, "325px", "CSS 宽未用实测 px");
    assert.strictEqual(r._canvas.style.height, "583px", "CSS 高未用实测 px");
    const cssAspect = 325 / 583;
    const backingAspect = r._canvas.width / r._canvas.height;
    assert.ok(Math.abs(cssAspect - backingAspect) < 1e-6, "CSS/backing 比例不一致（会被非等比拉伸）");
    const focusPos = r._positions.get(hub);
    assert.ok(Math.abs(focusPos.x - 162.5) < 1 && Math.abs(focusPos.y - 291.5) < 1, `首帧 focus 未居中：${JSON.stringify(focusPos)}`);
    const s = spread(r._positions);
    assert.ok(s.xSpread > 100 && s.ySpread > 100, `首帧布局被压扁：${JSON.stringify(s)}`);
    const ratio = s.xSpread / Math.max(1, s.ySpread);
    assert.ok(ratio > 0.65 && ratio < 1.55, `首帧布局横向/纵向比例异常：${ratio}`);
    r.dispose();
  });

  await checkAsync("resize_recomputes_layout_and_canvas_px", async () => {
    const host = makeHost();
    const dims = { width: 325, height: 583 };
    const container = {
      clientWidth: 325, clientHeight: 583,
      getBoundingClientRect: () => ({ left: 0, top: 0, width: dims.width, height: dims.height }),
    };
    const r = new Adapter.Renderer2D(container, { host, presentation });
    r.setFocusNode(hub);
    r.render(container, vm);
    assert.strictEqual(r._canvas.style.width, "325px");
    dims.width = 240; dims.height = 500;
    container.clientWidth = 240; container.clientHeight = 500;
    // Node 无 ResizeObserver；直接调用内部重测入口，等价于观察器回调
    r._onContainerResize();
    await new Promise((resolve) => setTimeout(resolve, 140));
    assert.strictEqual(r._canvas.style.width, "240px", "尺寸变化后 CSS 宽未更新");
    assert.strictEqual(r._canvas.style.height, "500px", "尺寸变化后 CSS 高未更新");
    const focusPos = r._positions.get(hub);
    assert.ok(Math.abs(focusPos.x - 120) < 1 && Math.abs(focusPos.y - 250) < 1, `resize 后未重新居中：${JSON.stringify(focusPos)}`);
    r.dispose();
  });
}

(async () => {
  const ctx = run();
  await runAsync(ctx);
  console.log(JSON.stringify({ suite: "renderer_demo_p0", hub: ctx.hub, shown: ctx.shown.length, results, passed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length }));
})();
