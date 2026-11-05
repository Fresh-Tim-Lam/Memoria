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
    save() {}, restore() {}, translate() {}, scale() {}, setLineDash() {}, measureText(t) { return { width: String(t).length * 6 }; },
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
function makeRafQueue() {
  const queue = [];
  let nextId = 0;
  return {
    raf: (cb) => { queue.push(cb); nextId += 1; return nextId; },
    cancel: () => {},
    drain(n = 10000) {
      let count = 0;
      while (queue.length && count < n) {
        const cb = queue.shift();
        cb(performance.now());
        count += 1;
      }
      return count;
    },
    pending: () => queue.length,
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
  const { vm, presentation, hub, shown } = ctx;
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

  check("labels_use_presentation_names_and_truncate", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D({ clientWidth: 325, clientHeight: 520 }, { host, presentation });
    r.setFocusNode(hub);
    r.render({ clientWidth: 325, clientHeight: 520 }, vm);
    assert.strictEqual(r._nodeById.get("kp-022").label, "macroeconomics", "标签未优先使用 presentation.names");
    const longNode = [...r._nodeById.values()].find((n) => presentation.names[n.id] && presentation.names[n.id].length > 18);
    assert.ok(longNode, "fixture 缺超长名称样例");
    assert.ok(longNode.label.length <= 18, `超长标签未截断：${longNode.label}`);
    assert.ok(longNode.label.endsWith("…"), "截断未加省略号");
    assert.strictEqual(r._nodeById.get(hub).label.includes("kp-022"), false, "标签仍显示 id");
    r.dispose();
  });

  check("force_layout_is_not_radial_ring_and_deterministic", () => {
    const host = makeHost();
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const r1 = new Adapter.Renderer2D(container, { host, presentation });
    r1.setFocusNode(hub);
    r1.render(container, vm);
    const ctr = r1._positions.get(hub);
    const radii = [...r1._positions.entries()]
      .filter(([id]) => id !== hub)
      .map(([, p]) => Math.hypot(p.x - ctr.x, p.y - ctr.y));
    const spreadR = Math.max(...radii) - Math.min(...radii);
    assert.ok(spreadR > 10, `力导向仍近似等半径环：radii=${radii.map((x) => x.toFixed(1))}`);
    assert.ok(new Set(radii.map((x) => Math.round(x))).size >= 3, "邻居半径缺乏自由度");

    const host2 = makeHost();
    const r2 = new Adapter.Renderer2D(container, { host: host2, presentation });
    r2.setFocusNode(hub);
    r2.render(container, vm);
    for (const id of [...r1._positions.keys()].sort()) {
      const a = r1._positions.get(id);
      const b = r2._positions.get(id);
      assert.ok(Math.abs(a.x - b.x) < 1e-9 && Math.abs(a.y - b.y) < 1e-9, `2× 力导向结果不一致：${id}`);
    }
    assert.strictEqual(r1.lastRender.layoutMode, "force");
    r1.dispose(); r2.dispose();
  });

  check("node_drag_pins_position_without_relayout", () => {
    const host = makeHost();
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const r = new Adapter.Renderer2D(container, { host, presentation });
    r.setFocusNode(hub);
    r.render(container, vm);
    const start = { ...r._positions.get(hub) };
    const beforeCamera = { ...r._camera };
    const otherId = shown.find((id) => id !== hub);
    const otherBefore = { ...r._positions.get(otherId) };
    const base = { clientX: start.x, clientY: start.y, button: 0, pointerId: 1, preventDefault() {} };
    r._onPointerDown(base);
    r._onPointerMove({ ...base, clientX: start.x + 40, clientY: start.y + 22 });
    const moved = r._positions.get(hub);
    assert.ok(Math.abs(moved.x - (start.x + 40)) < 0.01 && Math.abs(moved.y - (start.y + 22)) < 0.01, "节点拖拽未更新位置");
    assert.ok(r._pinned.has(hub), "拖拽后未 pin");
    assert.deepStrictEqual(r._camera, beforeCamera, "节点拖拽不应改变 camera");
    r._onPointerUp(base);
    assert.strictEqual(r._drag, null);
    // 拖拽松手后力导向重加热：其它节点继续收敛，dragged 节点保持 pin
    const otherAfter = r._positions.get(otherId);
    assert.ok(Math.hypot(otherAfter.x - otherBefore.x, otherAfter.y - otherBefore.y) > 0.01, "松手后邻居未继续力导向收敛");
    const draggedAfter = r._positions.get(hub);
    assert.ok(Math.hypot(draggedAfter.x - moved.x, draggedAfter.y - moved.y) < 1e-6, "拖拽节点 pin 未保持");
    // 拖拽后的 click 被抑制，不触发 focus
    let clicks = 0;
    r.on("nodeClick", () => { clicks += 1; });
    r._onPointerClick({ ...base, clientX: moved.x, clientY: moved.y });
    assert.strictEqual(clicks, 0, "拖拽后 click 未抑制");
    r.dispose();
  });

  check("blank_pan_moves_camera_only", () => {
    const host = makeHost();
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const r = new Adapter.Renderer2D(container, { host, presentation });
    r.setFocusNode(hub);
    r.render(container, vm);
    const posBefore = new Map([...r._positions].map(([id, p]) => [id, { ...p }]));
    const base = { clientX: 6, clientY: 6, button: 0, pointerId: 2, preventDefault() {} };
    r._onPointerDown(base);
    r._onPointerMove({ ...base, clientX: 46, clientY: 26 });
    assert.strictEqual(r._camera.x, 40);
    assert.strictEqual(r._camera.y, 20);
    assert.strictEqual(r._userAdjusted, true);
    for (const [id, p] of r._positions) {
      assert.ok(Math.abs(p.x - posBefore.get(id).x) < 1e-9 && Math.abs(p.y - posBefore.get(id).y) < 1e-9, "pan 不应移动节点坐标");
    }
    r._onPointerUp(base);
    r.dispose();
  });

  check("wheel_zoom_about_pointer_and_fit_reset", () => {
    const host = makeHost();
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const r = new Adapter.Renderer2D(container, { host, presentation });
    r.setFocusNode(hub);
    r.render(container, vm);
    const beforeWorld = r._screenToWorld(100, 120);
    r._onWheel({ clientX: 100, clientY: 120, deltaY: -240, preventDefault() {} });
    assert.ok(r._camera.scale > 1, "滚轮未放大");
    assert.strictEqual(r._userAdjusted, true);
    const afterWorld = r._screenToWorld(100, 120);
    assert.ok(Math.abs(afterWorld.x - beforeWorld.x) < 0.01 && Math.abs(afterWorld.y - beforeWorld.y) < 0.01, "缩放未以指针为中心");
    const fitted = r.fitView();
    assert.ok(fitted.scale > 0);
    assert.strictEqual(r._userAdjusted, false);
    const reset = r.resetView();
    assert.strictEqual(reset.scale, 1);
    assert.strictEqual(reset.x, 0);
    r.dispose();
  });

  check("rAF_force_animation_no_teleport_and_focus_transition", () => {
    const host = makeHost();
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const raf = makeRafQueue();
    const r = new Adapter.Renderer2D(container, {
      host, presentation, animateForce: true,
      requestAnimationFrame: raf.raf, cancelAnimationFrame: raf.cancel,
    });
    r.setFocusNode(hub);
    r.render(container, vm);
    assert.strictEqual(r._simulating, true, "动画模式未启动 rAF 模拟");
    raf.drain();
    assert.strictEqual(r._simulating, false, "模拟未收敛停止");
    const initialLog = r.getForceFrameLog();
    assert.ok(initialLog.length > 10, "帧日志太少");
    assert.ok(initialLog.every((f) => f.maxDisp <= 12), `存在单帧 >12px：${JSON.stringify(initialLog.filter((f) => f.maxDisp > 12).slice(0, 3))}`);

    // focus 过渡：以当前坐标为初值，不整图瞬移
    const before = new Map([...r._positions].map(([id, p]) => [id, { ...p }]));
    const other = shown.find((id) => id !== hub);
    r.setFocusNode(other);
    r.update(vm, {});
    let maxImmediate = 0;
    for (const [id, p] of r._positions) {
      const old = before.get(id);
      if (old) maxImmediate = Math.max(maxImmediate, Math.hypot(p.x - old.x, p.y - old.y));
    }
    assert.ok(maxImmediate < 1, `focus 切换初值发生瞬移：${maxImmediate}`);
    assert.strictEqual(r._simulating, true, "focus 过渡未启动动画");
    raf.drain();
    const focusLog = r.getForceFrameLog();
    assert.ok(focusLog.length > 5);
    assert.ok(focusLog.every((f) => f.maxDisp <= 12), "focus 过渡单帧 >12px");
    r.dispose();
  });

  check("animation_is_deterministic_two_runs", () => {
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    function makeAnimated() {
      const raf = makeRafQueue();
      const r = new Adapter.Renderer2D(container, {
        host: makeHost(), presentation, animateForce: true,
        requestAnimationFrame: raf.raf, cancelAnimationFrame: raf.cancel,
      });
      r.setFocusNode(hub);
      r.render(container, vm);
      return { r, raf };
    }
    const a = makeAnimated();
    const b = makeAnimated();
    for (let i = 0; i < 120; i++) { a.raf.drain(1); b.raf.drain(1); }
    for (const id of [...a.r._positions.keys()].sort()) {
      const pa = a.r._positions.get(id);
      const pb = b.r._positions.get(id);
      assert.ok(Math.abs(pa.x - pb.x) < 1e-9 && Math.abs(pa.y - pb.y) < 1e-9, `2× 动画结果不一致：${id}`);
    }
    a.r.dispose(); b.r.dispose();
  });
}

(async () => {
  const ctx = run();
  await runAsync(ctx);
  console.log(JSON.stringify({ suite: "renderer_demo_p0", hub: ctx.hub, shown: ctx.shown.length, results, passed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length }));
})();
