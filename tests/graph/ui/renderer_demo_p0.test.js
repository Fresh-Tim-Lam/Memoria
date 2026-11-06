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
function hasThreeFramePlateau(log) {
  for (let i = 2; i < log.length; i++) {
    const a = log[i - 2].maxDisp;
    const b = log[i - 1].maxDisp;
    const c = log[i].maxDisp;
    if (Math.abs(a - b) < 1e-9 && Math.abs(b - c) < 1e-9) return true;
  }
  return false;
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
    const p = r.getPositions().get(hub);
    assert.ok(p, "hub 无位置");
    assert.ok(Math.abs(p.x - 162.5) < 1 && Math.abs(p.y - 260) < 1, `focus 未居中：${JSON.stringify(p)}`);
    const s = spread(r.getPositions());
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
    const p = r.getPositions().get(other);
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
    const focusPos = r.getPositions().get(hub);
    assert.ok(Math.abs(focusPos.x - 162.5) < 1 && Math.abs(focusPos.y - 291.5) < 1, `首帧 focus 未居中：${JSON.stringify(focusPos)}`);
    const s = spread(r.getPositions());
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
    const focusPos = r.getPositions().get(hub);
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
    const ctr = r1.getPositions().get(hub);
    const radii = [...r1.getPositions().entries()]
      .filter(([id]) => id !== hub)
      .map(([, p]) => Math.hypot(p.x - ctr.x, p.y - ctr.y));
    const spreadR = Math.max(...radii) - Math.min(...radii);
    assert.ok(spreadR > 10, `力导向仍近似等半径环：radii=${radii.map((x) => x.toFixed(1))}`);
    assert.ok(new Set(radii.map((x) => Math.round(x))).size >= 3, "邻居半径缺乏自由度");

    const host2 = makeHost();
    const r2 = new Adapter.Renderer2D(container, { host: host2, presentation });
    r2.setFocusNode(hub);
    r2.render(container, vm);
    for (const id of [...r1.getPositions().keys()].sort()) {
      const a = r1.getPositions().get(id);
      const b = r2.getPositions().get(id);
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
    const start = { ...r.getPositions().get(hub) };
    const beforeCamera = { ...r._camera };
    const otherId = shown.find((id) => id !== hub);
    const otherBefore = { ...r.getPositions().get(otherId) };
    const base = { clientX: start.x, clientY: start.y, button: 0, pointerId: 1, preventDefault() {} };
    r._onPointerDown(base);
    r._onPointerMove({ ...base, clientX: start.x + 40, clientY: start.y + 22 });
    const moved = r.getPositions().get(hub);
    assert.ok(Math.abs(moved.x - (start.x + 40)) < 0.01 && Math.abs(moved.y - (start.y + 22)) < 0.01, "节点拖拽未更新位置");
    assert.ok(r._pinned.has(hub), "拖拽后未 pin");
    assert.deepStrictEqual(r._camera, beforeCamera, "节点拖拽不应改变 camera");
    r._onPointerUp(base);
    assert.strictEqual(r._drag, null);
    // task-385：松手解除拖拽 pin；邻居继续收敛
    assert.ok(!r._pinned.has(hub), "松手未解除拖拽 pin");
    // 拖拽松手后力导向重加热：其它节点继续收敛
    const otherAfter = r.getPositions().get(otherId);
    assert.ok(Math.hypot(otherAfter.x - otherBefore.x, otherAfter.y - otherBefore.y) > 0.01, "松手后邻居未继续力导向收敛");
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
    const posBefore = new Map([...r.getPositions()].map(([id, p]) => [id, { ...p }]));
    const base = { clientX: 6, clientY: 6, button: 0, pointerId: 2, preventDefault() {} };
    r._onPointerDown(base);
    r._onPointerMove({ ...base, clientX: 46, clientY: 26 });
    assert.strictEqual(r._camera.x, 40);
    assert.strictEqual(r._camera.y, 20);
    assert.strictEqual(r._userAdjusted, true);
    for (const [id, p] of r.getPositions()) {
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
    assert.ok(initialLog.every((f) => f.maxDisp <= 4), `存在单帧 >4px：${JSON.stringify(initialLog.filter((f) => f.maxDisp > 4).slice(0, 3))}`);
    assert.strictEqual(hasThreeFramePlateau(initialLog), false, "存在连续 3 帧相同 maxDisp 平台");

    // focus 过渡：以当前坐标为初值，不整图瞬移
    const before = new Map([...r.getPositions()].map(([id, p]) => [id, { ...p }]));
    const other = shown.find((id) => id !== hub);
    r.setFocusNode(other);
    r.update(vm, {});
    let maxImmediate = 0;
    for (const [id, p] of r.getPositions()) {
      const old = before.get(id);
      if (old) maxImmediate = Math.max(maxImmediate, Math.hypot(p.x - old.x, p.y - old.y));
    }
    assert.ok(maxImmediate < 1, `focus 切换初值发生瞬移：${maxImmediate}`);
    assert.strictEqual(r._simulating, true, "focus 过渡未启动动画");
    raf.drain();
    const focusLog = r.getForceFrameLog();
    assert.ok(focusLog.length > 5);
    assert.ok(focusLog.every((f) => f.maxDisp <= 4), "focus 过渡单帧 >4px");
    assert.strictEqual(hasThreeFramePlateau(focusLog), false, "focus 过渡存在连续 3 帧相同 maxDisp 平台");
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
    for (const id of [...a.r.getPositions().keys()].sort()) {
      const pa = a.r.getPositions().get(id);
      const pb = b.r.getPositions().get(id);
      assert.ok(Math.abs(pa.x - pb.x) < 1e-9 && Math.abs(pa.y - pb.y) < 1e-9, `2× 动画结果不一致：${id}`);
    }
    a.r.dispose(); b.r.dispose();
  });

  check("pointermove_follows_without_4px_dead_zone", () => {
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const raf = makeRafQueue();
    const r = new Adapter.Renderer2D(container, {
      host: makeHost(), presentation, animateForce: true,
      requestAnimationFrame: raf.raf, cancelAnimationFrame: raf.cancel,
    });
    r.setFocusNode(hub);
    r.render(container, vm);
    raf.drain();
    const id = shown.find((x) => x !== hub);
    const start = { ...r.getPositions().get(id) };
    const base = { clientX: start.x, clientY: start.y, button: 0, pointerId: 7, preventDefault() {} };
    r._onPointerDown(base);
    assert.ok(r._pinned.has(id), "pointerdown 未立即 pin");
    const errors = [];
    let forceState = null;
    for (let i = 1; i <= 10; i++) {
      r._onPointerMove({ ...base, clientX: start.x + i * 3, clientY: start.y + i * 2 });
      const p = r.getPositions().get(id);
      const err = Math.hypot(p.x - (start.x + i * 3), p.y - (start.y + i * 2));
      errors.push(err);
      if (i === 1) {
        assert.ok(err <= 2, `首次 3px move 未跟手（死区）：${err}`);
        forceState = r._forceState;
        assert.ok(forceState, "首次 node move 未启动 force state");
      } else {
        assert.ok(err <= 2, `第 ${i} 次 move 跟手误差 >2px：${err}`);
        assert.strictEqual(r._forceState, forceState, "反复 move 重建了 force state");
      }
    }
    assert.ok(errors.every((e) => e <= 2), `跟手误差：${errors}`);
    assert.strictEqual(r._simulating, true, "pointerdown 未启动拖拽常驻模拟");
    assert.strictEqual(r._forceFrames, 0, "未 drain 时 forceFrames 被 move 重置/推进");
    r._onPointerUp({ ...base, clientX: start.x + 30, clientY: start.y + 20 });
    assert.strictEqual(r._drag, null);
    assert.ok(!r._pinned.has(id), "松手未解除拖拽 pin");
    r.dispose();
  });

  check("drag_hold_keeps_neighbors_moving_no_rebuild", () => {
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const raf = makeRafQueue();
    const r = new Adapter.Renderer2D(container, {
      host: makeHost(), presentation, animateForce: true,
      requestAnimationFrame: raf.raf, cancelAnimationFrame: raf.cancel,
    });
    r.setFocusNode(hub);
    r.render(container, vm);
    raf.drain();
    const id = shown.find((x) => x !== hub);
    const neighborId = shown.find((x) => x !== hub && x !== id);
    const start = { ...r.getPositions().get(id) };
    const base = { clientX: start.x, clientY: start.y, button: 0, pointerId: 11, preventDefault() {} };
    r._onPointerDown(base);
    assert.strictEqual(r._simulating, true, "pointerdown 未启动拖拽模拟");
    assert.strictEqual(r._forceHold, true, "拖拽期间未保持模拟");
    const stateRef = r._forceState;
    const neighborBefore = { ...r.getPositions().get(neighborId) };
    // 不动指针，等 ≥10 帧：邻居应持续受力
    for (let i = 0; i < 12; i++) raf.drain(1);
    const neighborAfter = r.getPositions().get(neighborId);
    assert.ok(Math.hypot(neighborAfter.x - neighborBefore.x, neighborAfter.y - neighborBefore.y) > 0.01,
      "拖拽保持期间邻居没有受力移动");
    const holdLog = r.getForceFrameLog();
    assert.ok(holdLog.every((f) => f.maxDisp <= 4), "拖拽期间单帧位移 >4px");
    assert.strictEqual(r._forceState, stateRef, "拖拽期间 move 重建了 force state");
    // 继续移动 pointer：state 不重建
    for (let i = 1; i <= 5; i++) r._onPointerMove({ ...base, clientX: start.x + i * 2, clientY: start.y + i });
    assert.strictEqual(r._forceState, stateRef, "拖拽 move 重建了 force state");
    assert.strictEqual(r._forceHold, true);
    r._onPointerUp({ ...base, clientX: start.x + 10, clientY: start.y + 5 });
    assert.strictEqual(r._forceHold, false);
    assert.ok(!r._pinned.has(id), "松手未解除拖拽 pin");
    raf.drain();
    assert.strictEqual(r._simulating, false, "松手后模拟未收敛停止");
    r.dispose();
  });

  check("idle_motion_initial_focus_and_release_each_at_least_30_frames", () => {
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const raf = makeRafQueue();
    const r = new Adapter.Renderer2D(container, {
      host: makeHost(), presentation, animateForce: true,
      requestAnimationFrame: raf.raf, cancelAnimationFrame: raf.cancel,
    });
    r.setFocusNode(hub);
    r.render(container, vm);
    const neighborId = shown.find((x) => x !== hub);
    const initialBefore = { ...r.getPositions().get(neighborId) };
    for (let i = 0; i < 120 && r._forceFrames < 30; i++) raf.drain(1);
    assert.strictEqual(r._simulating, true, "初始动画 30 帧内已停");
    assert.ok(r._forceFrames >= 30, "初始动画不足 30 帧");
    const initialAfter = r.getPositions().get(neighborId);
    assert.ok(Math.hypot(initialAfter.x - initialBefore.x, initialAfter.y - initialBefore.y) > 0.01, "初始动画邻居未移动");
    assert.ok(r.getForceFrameLog().every((f) => f.maxDisp <= 4), "初始动画单帧 >4px");
    raf.drain();

    const other = shown.find((x) => x !== hub && x !== neighborId);
    r.setFocusNode(other);
    r.update(vm, {});
    const focusBefore = { ...r.getPositions().get(neighborId) };
    for (let i = 0; i < 120 && r._forceFrames < 30; i++) raf.drain(1);
    assert.strictEqual(r._simulating, true, "focus 动画 30 帧内已停");
    assert.ok(r._forceFrames >= 30, "focus 动画不足 30 帧");
    const focusAfter = r.getPositions().get(neighborId);
    assert.ok(Math.hypot(focusAfter.x - focusBefore.x, focusAfter.y - focusBefore.y) > 0.01, "focus 动画邻居未移动");
    assert.ok(r.getForceFrameLog().every((f) => f.maxDisp <= 4), "focus 动画单帧 >4px");
    raf.drain();

    const dragId = shown.find((x) => x !== other);
    const start = { ...r.getPositions().get(dragId) };
    const base = { clientX: start.x, clientY: start.y, button: 0, pointerId: 21, preventDefault() {} };
    r._onPointerDown(base);
    r._onPointerMove({ ...base, clientX: start.x + 8, clientY: start.y + 5 });
    r._onPointerUp({ ...base, clientX: start.x + 8, clientY: start.y + 5 });
    const releaseBefore = { ...r.getPositions().get(neighborId) };
    assert.strictEqual(r._simulating, true, "松手后未启动连续动画");
    for (let i = 0; i < 120 && r._forceFrames < 30; i++) raf.drain(1);
    assert.strictEqual(r._simulating, true, "松手后动画 30 帧内已停");
    assert.ok(r._forceFrames >= 30, "松手后动画不足 30 帧");
    const releaseAfter = r.getPositions().get(neighborId);
    assert.ok(Math.hypot(releaseAfter.x - releaseBefore.x, releaseAfter.y - releaseBefore.y) > 0.01, "松手后邻居未继续移动");
    assert.ok(r.getForceFrameLog().every((f) => f.maxDisp <= 4), "松手后动画单帧 >4px");
    r.dispose();
  });

  check("semantics_edge_dash_selection_group_and_dblclick", () => {
    assert.deepStrictEqual(Adapter.EDGE_DASH.contain, []);
    assert.deepStrictEqual(Adapter.EDGE_DASH.structural, []);
    assert.deepStrictEqual(Adapter.EDGE_DASH.reference, [5, 4]);
    assert.deepStrictEqual(Adapter.EDGE_DASH.semantic, [2, 3]);
    assert.deepStrictEqual(Adapter.EDGE_DASH.extend, [5, 4]);

    const host = makeHost();
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const r = new Adapter.Renderer2D(container, { host, presentation, animateForce: false });
    r.setFocusNode(hub);
    r.render(container, vm);
    const selected = shown.find((id) => id !== hub);
    const p = r.getPositions().get(selected);
    const res = r.handlePointClick(p.x, p.y);
    assert.strictEqual(res.type, "nodeClick");
    assert.strictEqual(r._selectedId, selected, "单击 KP 未选中");
    assert.strictEqual(r._focusNodeId, hub, "单击 KP 不应改变 focus");
    assert.strictEqual(r._selection.kind, "node");
    assert.ok(r._selectedNeighbors.size >= 1, "未计算一跳邻居");
    assert.ok(r._ctx.strokeStyles.includes("#f0f6fc"), "选中节点描边未绘制");
    let dbl = null;
    r.on("nodeDblClick", (payload) => { dbl = payload; });
    r._onPointerDblClick({ clientX: p.x, clientY: p.y });
    assert.ok(dbl && dbl.node_id === selected, "双击未发 nodeDblClick");
    const bg = r.handlePointClick(2, 2);
    assert.strictEqual(bg.type, "backgroundClick");
    assert.strictEqual(r._selectedId, null, "空白点击未清除选中");
    const rectHit = (r._groupHit || []).find((h) => h.kind === "rect");
    assert.ok(rectHit, "缺少展开组包络");
    const gid = rectHit.group.group_id;
    let clickedGroup = null;
    r.on("groupClick", (payload) => { clickedGroup = payload.group_id; });
    r.handlePointClick(rectHit.x0 + 2, (rectHit.y0 + rectHit.y1) / 2);
    assert.strictEqual(clickedGroup, gid, "组点击未发 groupClick");
    assert.ok(!r._collapsedGroups.has(gid), "组点击不应原位 toggle");
    r.dispose();
  });

  check("view_snapshot_restores_positions_camera_selection", () => {
    const host = makeHost();
    const container = { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
    const r = new Adapter.Renderer2D(container, { host, presentation, animateForce: false });
    r.setFocusNode(hub);
    r.render(container, vm);
    const nodeId = shown.find((id) => id !== hub);
    r.selectNode(nodeId);
    r._camera = { x: 30, y: -20, scale: 1.4 };
    const snap = r.captureViewState();
    r._camera = { x: 0, y: 0, scale: 1 };
    r.clearSelection();
    r.getPositions().set(nodeId, { x: 1, y: 2 });
    r.restoreViewState(snap);
    assert.deepStrictEqual(r._camera, { x: 30, y: -20, scale: 1.4 });
    assert.strictEqual(r._selectedId, nodeId);
    assert.deepStrictEqual(r.getPositions().get(nodeId), snap.positions.find(([id]) => id === nodeId)[1]);
    r.dispose();
  });
}

(async () => {
  const ctx = run();
  await runAsync(ctx);
  console.log(JSON.stringify({ suite: "renderer_demo_p0", hub: ctx.hub, shown: ctx.shown.length, results, passed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length }));
})();
