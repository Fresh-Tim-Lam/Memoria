/**
 * task-391 机检：RenderScene / RenderNode（Node，无 DOM）。
 *
 * 覆盖人的验收：
 *   1. 唯一节点与位置事实源（一个 Map；sync 保位；不再有 _positions/_auxPositions 双源）；
 *   2. 所有节点同一命中入口 pick()（KP / 折叠簇 / 背景幽灵）；
 *   3. 同一拖拽入口 beginDrag/dragTo/endDrag（三种 kind 走同一条路）；
 *   4. 同一力循环 stepForce（拖 KP 簇动、拖簇 KP 动，双向真实响应）；
 *   5. 单绘制入口 draw()（按 drawKind 分派策略）；
 *   6. Renderer2D 真实接线：折叠组/幽灵命中、拖拽、单 canvas。
 *
 * 运行：node tests/graph/render/render_scene.test.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "../../..");
const JS = path.join(ROOT, "src/memoria/ui/static/app/js/graph-multilevel");
const Adapter = require(path.join(JS, "renderer-adapter.js"));
const SceneModule = require(path.join(JS, "render-scene.js"));
const DEMO = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/graph/ui/fixtures/demo-p0-vm.json"), "utf8"));

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
    calls: 0,
    fillStyles: [],
    strokeStyles: [],
    fonts: [],
    strokeAlphas: [],
    _alpha: 1,
    font: "10px sans-serif",
    globalAlpha: 1,
    clearRect() { this.calls += 1; },
    fillRect() { this.calls += 1; this.fillStyles.push(this.fillStyle); },
    beginPath() { this.calls += 1; },
    closePath() {},
    moveTo() {},
    lineTo() {},
    arc() {},
    rect() {},
    roundRect() {},
    save() {},
    restore() {},
    translate() {},
    scale() {},
    setLineDash() {},
    stroke() { this.calls += 1; this.strokeStyles.push(this.strokeStyle); },
    fill() { this.calls += 1; this.fillStyles.push(this.fillStyle); },
    fillText() { this.calls += 1; this.fonts.push(this.font); },
    strokeText() { this.calls += 1; },
    measureText(t) { return { width: String(t).length * 6 }; },
    createRadialGradient() { return { addColorStop() {} }; },
  };
  return ctx;
}

function makeHost() {
  const host = {
    createCount: 0,
    createCanvas(w, h) {
      this.createCount += 1;
      const canvas = {
        width: w | 0,
        height: h | 0,
        getBoundingClientRect: () => ({ left: 0, top: 0, width: w, height: h }),
        style: {},
        setAttribute() {},
      };
      return { canvas, ctx: makeCtx() };
    },
    append() {},
    remove() {},
    on() {},
    off() {},
    rect: () => ({ left: 0, top: 0, width: 325, height: 520 }),
    dpr: () => 1,
  };
  return host;
}

function container() {
  return { clientWidth: 325, clientHeight: 520, getBoundingClientRect: () => ({ left: 0, top: 0, width: 325, height: 520 }) };
}

function vmOf(nodes) {
  return { view_model_id: "vm_scene", nodes, edges: [] };
}

function kp(id, extra) {
  return { id, kind: "kp", label: id, role: "member", presence: "shown", ...(extra || {}) };
}

const LAYOUT = {
  positions: new Map([['a', { x: 100, y: 100 }], ['b', { x: 240, y: 100 }]]),
  radiusById: new Map(),
};

function makeScene(extra) {
  const scene = new Adapter.RenderScene();
  scene.setPainters({
    kp: extra && extra.paintKp,
    cluster: extra && extra.paintCluster,
    group: extra && extra.paintCluster,
    ghost: extra && extra.paintGhost,
  });
  return scene;
}

function run() {
  // ── 1. RenderNode 几何 / pin / 命中 ─────────────────────────────────
  check("render_node_geometry_pin_hit", () => {
    const node = new Adapter.RenderNode({ id: "a", kind: "kp", x: 10, y: 20, radius: 8, label: "A" });
    assert.strictEqual(node.id, "a");
    assert.strictEqual(node.shape, "circle");
    assert.deepStrictEqual(node.position, { x: 10, y: 20 });
    node.moveTo(30, 40);
    assert.deepStrictEqual(node.position, { x: 30, y: 40 });
    assert.strictEqual(node.hitTest(30, 40), true);
    assert.strictEqual(node.hitTest(30 + 8 + 6, 40), true, "边界含 6px slack 应命中");
    assert.strictEqual(node.hitTest(30 + 8 + 7, 40), false, "超出 slack 不应命中");
    node.pin();
    assert.strictEqual(node.fixed, true);
    assert.deepStrictEqual(node.anchor, { x: 30, y: 40 });
    node.moveTo(1, 2); // 拖拽期间允许移动，但仍是 fixed
    assert.deepStrictEqual(node.anchor, { x: 30, y: 40 }, "pin 锚点不应随拖拽变化");
    node.release();
    assert.strictEqual(node.fixed, false);
    assert.strictEqual(node.anchor, null);
    // 六边形 shape 由 spec 决定（簇/幽灵）
    assert.strictEqual(new Adapter.RenderNode({ id: "g", kind: "ghost" }).shape, "hexagon");
  });

  // ── 2. 同一受力/积分入口：fixed 不动，自由节点按力移动 ──────────────
  check("render_node_force_integrate", () => {
    const free = new Adapter.RenderNode({ id: "a", kind: "kp", x: 100, y: 100, radius: 6 });
    free.applyForce(12, 0);
    const step = free.integrate({ force: undefined, alpha: 1, pad: 10, width: 400, height: 400 });
    assert.ok(step > 0, "受力后应有位移");
    assert.ok(free.x > 100, "正向力应向右移动");
    const fixed = new Adapter.RenderNode({ id: "b", kind: "kp", x: 50, y: 50, radius: 6 });
    fixed.pin();
    fixed.applyForce(999, 999);
    const s2 = fixed.integrate({ alpha: 1, pad: 10, width: 400, height: 400 });
    assert.strictEqual(s2, 0);
    assert.deepStrictEqual(fixed.position, { x: 50, y: 50 }, "fixed 节点不应被积分移动");
  });

  // ── 3. sync：唯一节点 Map、KP/簇/幽灵同池、重同步保位 ───────────────
  check("scene_sync_single_node_store_and_keeps_positions", () => {
    const scene = makeScene();
    const vm = vmOf([kp("a"), kp("b")]);
    const groups = [{ group_id: "g1", member_ids: ["a"], file: "ch1.md", presentation_only: true }];
    const stats = scene.sync({ layout: LAYOUT,
      vm,
      groups,
      collapsedGroups: new Set(["g1"]),
      hiddenIds: new Set([]),
      background: { targetId: "b", x: 40, y: 60, radius: 20, label: "上一站" },
    });
    assert.ok(stats.created >= 4, `应建立 kp a/b + 折叠簇 + 幽灵：${JSON.stringify(stats)}`);
    assert.ok(scene.has("a") && scene.has("b"));
    assert.ok(scene.has("group:g1"), "折叠组应投影成 cluster 节点");
    assert.ok(scene.has("ghost:A"), "背景幽灵应进入同一 nodes Map");
    assert.strictEqual(scene.get("group:g1").kind, "cluster");
    assert.strictEqual(scene.get("group:g1").hitPolicy, "drill");
    assert.strictEqual(scene.get("ghost:A").layer, "background");
    assert.strictEqual(scene.get("a").hitPolicy, "select");
    // 会话内保位：重同步不重置已有节点位置
    scene.get("a").moveTo(123, 45);
    scene.sync({ layout: LAYOUT, vm, groups, collapsedGroups: new Set(["g1"]), background: null });
    assert.deepStrictEqual(scene.get("a").position, { x: 123, y: 45 }, "sync 不应重置已有位置");
    assert.ok(!scene.has("ghost:A"), "清除 background 后幽灵节点应被移除");
  });

  // ── 4. 同一命中入口 pick()：三种 kind 均可命中 ───────────────────────
  check("scene_pick_all_node_kinds", () => {
    const scene = makeScene();
    scene.sync({ layout: LAYOUT,
      vm: vmOf([kp("a"), kp("b")]),
      groups: [{ group_id: "g1", member_ids: ["a"] }],
      collapsedGroups: new Set(["g1"]),
      background: { targetId: "b", x: 300, y: 400, radius: 20, label: "A" },
    });
    scene.get("a").moveTo(100, 100);
    scene.get("b").moveTo(200, 200);
    scene.get("group:g1").moveTo(150, 150);
    scene.get("ghost:A").moveTo(300, 400);
    assert.strictEqual(scene.pick(100, 100).id, "a", "KP 命中");
    assert.strictEqual(scene.pick(200, 200).id, "b", "KP 命中");
    assert.strictEqual(scene.pick(150, 150).id, "group:g1", "折叠簇命中");
    assert.strictEqual(scene.pick(300, 400).id, "ghost:A", "幽灵命中");
    assert.strictEqual(scene.pick(5, 5), null, "空白不应命中");
  });

  // ── 5. 同一拖拽入口：beginDrag/dragTo/endDrag 对三种 kind 一致 ───────
  check("scene_unified_drag_entry_for_all_kinds", () => {
    const scene = makeScene();
    scene.sync({ layout: LAYOUT,
      vm: vmOf([kp("a"), kp("b")]),
      groups: [{ group_id: "g1", member_ids: ["a"] }],
      collapsedGroups: new Set(["g1"]),
      background: { targetId: "b", x: 300, y: 400, radius: 20, label: "A" },
    });
    for (const id of ["a", "group:g1", "ghost:A"]) {
      const node = scene.beginDrag(id);
      assert.ok(node, `${id} beginDrag 应返回节点`);
      assert.strictEqual(node.fixed, true, `${id} 拖拽应 pin`);
      scene.dragTo(id, 77, 88);
      assert.deepStrictEqual(scene.get(id).position, { x: 77, y: 88 }, `${id} 拖拽应走同一位置 store`);
      scene.endDrag(id);
      assert.strictEqual(scene.get(id).fixed, false, `${id} 松手应 release`);
    }
  });

  // ── 6. 同一力循环：拖 KP 簇动、拖簇 KP 动（真实双向）─────────────────
  check("force_is_bilateral_kp_and_cluster", () => {
    const scene = makeScene();
    scene.sync({ layout: LAYOUT,
      vm: vmOf([kp("a"), kp("b")]),
      groups: [{ group_id: "g1", member_ids: ["a"] }],
      collapsedGroups: new Set(["g1"]),
    });
    scene.get("a").moveTo(100, 100);
    scene.get("b").moveTo(240, 100);
    scene.get("group:g1").moveTo(170, 100);
    const state = scene.buildForceState({ width: 325, height: 520 });

    // ① 拖 KP（pin a）⇒ 簇 b 与 group 应受力移动
    scene.beginDrag("a");
    const bBefore = { ...scene.get("b").position };
    const clusterBefore = { ...scene.get("group:g1").position };
    for (let i = 0; i < 8; i += 1) scene.stepForce(state);
    assert.deepStrictEqual(scene.get("a").position, { x: 100, y: 100 }, "pin 的 KP 不应移动");
    const bMoved = Math.hypot(scene.get("b").x - bBefore.x, scene.get("b").y - bBefore.y);
    const clusterMoved = Math.hypot(scene.get("group:g1").x - clusterBefore.x, scene.get("group:g1").y - clusterBefore.y);
    assert.ok(bMoved > 0.01, "拖 KP 时其他 KP 应受力移动");
    assert.ok(clusterMoved > 0.01, "拖 KP 时折叠簇应受力移动（同一力循环）");
    scene.endDrag("a");

    // ② 拖簇（pin group）⇒ KP 应受力移动
    scene.beginDrag("group:g1");
    const kpBefore = { ...scene.get("b").position };
    for (let i = 0; i < 8; i += 1) scene.stepForce(state);
    const kpMoved = Math.hypot(scene.get("b").x - kpBefore.x, scene.get("b").y - kpBefore.y);
    assert.ok(kpMoved > 0.01, "拖折叠簇时 KP 应受力移动（同一力循环）");
    scene.endDrag("group:g1");

    // ③ 幽灵也在同一循环里受力
    scene.sync({ layout: LAYOUT,
      vm: vmOf([kp("a"), kp("b")]),
      groups: [{ group_id: "g1", member_ids: ["a"] }],
      collapsedGroups: new Set(["g1"]),
      background: { targetId: "b", x: 40, y: 460, radius: 20, label: "A" },
    });
    scene.get("ghost:A").moveTo(40, 460);
    const ghostBefore = { ...scene.get("ghost:A").position };
    for (let i = 0; i < 8; i += 1) scene.stepForce(state);
    const ghostMoved = Math.hypot(scene.get("ghost:A").x - ghostBefore.x, scene.get("ghost:A").y - ghostBefore.y);
    assert.ok(ghostMoved > 0.01, "背景幽灵应参与同一力循环");
  });

  // ── 7. 单绘制入口：三种 kind 全部经 scene.draw → RenderNode.draw ─────
  check("single_draw_entry_covers_all_kinds", () => {
    const painted = [];
    const painters = {
      kp: (ctx, node) => { painted.push(node.id); },
      cluster: (ctx, node) => { painted.push(node.id); },
      group: (ctx, node) => { painted.push(node.id); },
      ghost: (ctx, node) => { painted.push(node.id); },
    };
    const scene = new Adapter.RenderScene({ painters });
    scene.sync({ layout: LAYOUT,
      vm: vmOf([kp("a"), kp("b")]),
      groups: [{ group_id: "g1", member_ids: ["a"] }],
      collapsedGroups: new Set(["g1"]),
      background: { targetId: "b", x: 300, y: 400, radius: 20, label: "A" },
    });
    const view = { painters, calls: { nodes: 0 } };
    const count = scene.draw(makeCtx(), view);
    assert.strictEqual(count, scene.size(), "每个节点都应经同一 draw 入口绘制");
    for (const id of ["a", "b", "group:g1", "ghost:A"]) assert.ok(painted.includes(id), `${id} 未经 scene.draw 绘制`);
    // layer 过滤：背景层只画幽灵
    painted.length = 0;
    scene.draw(makeCtx(), view, "background");
    assert.deepStrictEqual(painted, ["ghost:A"]);
    // 未注册策略不画（但节点仍在场，失败可诊断）
    const bare = new Adapter.RenderScene();
    bare.sync({ vm: vmOf([kp("x")]) });
    assert.strictEqual(bare.draw(makeCtx(), { painters: {}, calls: {} }), 0);
  });

  // ── 8. 源码静态：双位置源 / 外挂力 / 旧命中分支已删除 ────────────────
  check("source_has_no_legacy_position_or_branch_duplicates", () => {
    const src = fs.readFileSync(path.join(JS, "renderer-adapter.js"), "utf8")
      .split("\n")
      .filter((line) => !/^\s*(\*|\/\/)/.test(line))
      .join("\n");
    assert.ok(!src.includes("this._positions"), "renderer-adapter 仍持有 _positions 第二位置源");
    assert.ok(!src.includes("this._auxPositions"), "renderer-adapter 仍持有 _auxPositions 第二位置源");
    assert.ok(!src.includes("extraBodies"), "renderer-adapter 仍有 extraBodies 外挂力环");
    assert.ok(!/\._pickNode\s*\(/.test(src), "旧 _pickNode 命中分支未删除");
    assert.ok(!/\._pickRenderNode\s*\(/.test(src), "旧 _pickRenderNode 命中分支未删除");
    assert.ok(!/\._composeRenderNodes\s*\(/.test(src), "旧 _composeRenderNodes 临时模型未删除");
    const sceneSrc = fs.readFileSync(path.join(JS, "render-scene.js"), "utf8");
    assert.ok(sceneSrc.includes("class RenderNode"), "缺少 RenderNode 类");
    assert.ok(sceneSrc.includes("class RenderScene"), "缺少 RenderScene 类");
    assert.ok(sceneSrc.includes("stepForce("), "缺少唯一力循环 stepForce");
    assert.ok(sceneSrc.includes("beginDrag("), "缺少统一拖拽入口 beginDrag");
    assert.ok(sceneSrc.includes("pick("), "缺少统一命中入口 pick");
    assert.ok(sceneSrc.includes("draw("), "缺少统一绘制入口 draw");
  });

  // ── 9. Renderer2D 真实接线：折叠簇 / 幽灵命中（同一 scene.pick）──────
  check("renderer_wires_cluster_and_ghost_through_scene", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host, presentation: DEMO.presentation, animateForce: false });
    r.render(container(), DEMO.vm);
    assert.strictEqual(host.createCount, 1, "必须只有一张画布");
    const group = r.getGroups()[0];
    r.toggleGroup(group.group_id);
    const cluster = r.getNode(`group:${group.group_id}`);
    assert.ok(cluster, "折叠组未进入 RenderScene");
    let clicked = null;
    r.on("groupClick", (p) => { clicked = p; });
    const res = r.handlePointClick(cluster.x, cluster.y);
    assert.strictEqual(res.type, "groupClick", `折叠簇命中走同一 scene.pick（实际 ${res.type}）`);
    assert.strictEqual(clicked.group_id, group.group_id);
    // 幽灵
    const hub = [...r.getPositions().keys()].find((id) => r.getNode(id).kind === "kp");
    const hubNode = r.getNode(hub);
    let ghostClicked = null;
    r.on("backgroundGhostClick", (p) => { ghostClicked = p; });
    r.setBackgroundGhost({ targetId: hub, x: hubNode.x - 120, y: hubNode.y - 100, radius: 20, label: "上一站 A" });
    const ghost = r.getNode("ghost:A");
    assert.ok(ghost, "背景幽灵未进入 RenderScene");
    assert.ok(ghost.layer === "background");
    const gres = r.handlePointClick(ghost.x, ghost.y);
    assert.strictEqual(gres.type, "backgroundGhostClick", "幽灵命中走同一 scene.pick");
    assert.strictEqual(ghostClicked.kind, "background-ghost");
    r.dispose();
  });

  // ── 10. Renderer2D 真实拖拽：拖 KP 簇动 / 拖簇 KP 动 ────────────────
  check("renderer_drag_kp_moves_cluster_and_drag_cluster_moves_kp", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host, presentation: DEMO.presentation, animateForce: false });
    r.render(container(), DEMO.vm);
    const group = r.getGroups()[0];
    r.toggleGroup(group.group_id);
    const clusterId = `group:${group.group_id}`;
    const cluster = r.getNode(clusterId);
    assert.ok(cluster, "折叠簇节点缺失");
    const kpId = DEMO.vm.nodes
      .filter((n) => n.presence === "shown" && n.kind === "kp")
      .map((n) => n.id)
      .find((id) => !group.member_ids.includes(id));
    assert.ok(kpId, "缺少可拖动 KP");
    const kp = r.getNode(kpId);

    // ① 拖 KP ⇒ 簇位置响应
    const clusterBefore = { ...cluster.position };
    r._onPointerDown({ clientX: kp.x, clientY: kp.y, button: 0, pointerId: 31, preventDefault() {} });
    r._onPointerMove({ clientX: kp.x + 40, clientY: kp.y + 22, button: 0, pointerId: 31, preventDefault() {} });
    r._onPointerUp({ clientX: kp.x + 40, clientY: kp.y + 22, button: 0, pointerId: 31, preventDefault() {} });
    const clusterAfter = r.getNode(clusterId).position;
    const movedByKp = Math.hypot(clusterAfter.x - clusterBefore.x, clusterAfter.y - clusterBefore.y);
    assert.ok(movedByKp > 0.01, `拖 KP 后折叠簇未响应（位移 ${movedByKp}）`);

    // ② 拖簇 ⇒ KP 位置响应
    const kpBefore = { ...r.getNode(kpId).position };
    const c2 = r.getNode(clusterId).position;
    r._onPointerDown({ clientX: c2.x, clientY: c2.y, button: 0, pointerId: 32, preventDefault() {} });
    r._onPointerMove({ clientX: c2.x + 36, clientY: c2.y - 24, button: 0, pointerId: 32, preventDefault() {} });
    r._onPointerUp({ clientX: c2.x + 36, clientY: c2.y - 24, button: 0, pointerId: 32, preventDefault() {} });
    const kpAfter = r.getNode(kpId).position;
    const movedByCluster = Math.hypot(kpAfter.x - kpBefore.x, kpAfter.y - kpBefore.y);
    assert.ok(movedByCluster > 0.01, `拖簇后 KP 未响应（位移 ${movedByCluster}）`);
    assert.strictEqual(host.createCount, 1, "全程必须只有一张画布");
    r.dispose();
  });

  // ── 11. task-391 收口：app.js 走 applyOverviewLayout；旧位置表别名彻底删除 ──
  check("app_js_uses_apply_overview_layout_and_no_positions_alias", () => {
    const adapterSrc = fs.readFileSync(path.join(JS, "renderer-adapter.js"), "utf8");
    const sceneSrc = fs.readFileSync(path.join(JS, "render-scene.js"), "utf8");
    const appSrc = fs.readFileSync(path.join(ROOT, "src/memoria/ui/static/app/js/app.js"), "utf8");
    for (const [name, src] of [
      ["renderer-adapter.js", adapterSrc],
      ["render-scene.js", sceneSrc],
      ["app.js", appSrc],
    ]) {
      assert.ok(!src.includes("_positions"), `${name} 仍出现旧位置表标识符（应归零）`);
    }
    assert.ok(appSrc.includes("renderer.applyOverviewLayout(positions)"), "app.js H 首屏未改调 applyOverviewLayout");
    assert.ok(adapterSrc.includes("applyOverviewLayout(positions, opts = {})"), "renderer 缺 applyOverviewLayout 入口");
  });

  check("renderer_apply_overview_layout_writes_grid_positions", () => {
    const host = makeHost();
    const box = container();
    const r = new Adapter.Renderer2D(box, { host, presentation: DEMO.presentation, animateForce: false });
    r.render(box, DEMO.vm);
    // H 首屏语义：先折叠顶层组（app.js multilevelCollapseTopGroups），再网格布局
    const groups = r.getGroups().filter((g) => !g.parent_id);
    assert.ok(groups.length >= 2, "fixture 顶层组不足");
    for (const g of groups) if (!r.isGroupCollapsed(g.group_id)) r.toggleGroup(g.group_id);
    const width = r._measureWidth();
    const height = r._measureHeight();
    const cols = width >= 240 ? 2 : 1;
    const rows = Math.ceil(groups.length / cols);
    const cw = width / cols;
    const ch = Math.min(100, (height - 100) / rows);
    const positions = new Map();
    const expected = new Map();
    groups.forEach((g, gi) => {
      const cx = cw * (gi % cols + 0.5);
      const cy = 90 + ch * (Math.floor(gi / cols) + 0.5);
      const members = g.member_ids || [];
      const rr = Math.max(14, Math.min(34, 8 + members.length * 0.7));
      members.forEach((id, i) => {
        const angle = (Math.PI * 2 * i) / Math.max(1, members.length) - Math.PI / 2;
        const p = { x: cx + Math.cos(angle) * rr, y: cy + Math.sin(angle) * rr };
        positions.set(String(id), p);
        expected.set(String(id), p);
      });
      positions.set(`group:${g.group_id}`, { x: cx, y: cy });
      expected.set(`group:${g.group_id}`, { x: cx, y: cy });
    });
    const existing = r.getPositions();
    for (const id of existing.keys()) {
      if (!positions.has(String(id))) positions.set(String(id), { x: width / 2, y: height - 50 });
    }
    r.applyOverviewLayout(positions);
    const got = r.getPositions();
    const hidden = r._hiddenMemberIds();
    let maxErr = 0;
    for (const [id, p] of expected) {
      const q = got.get(id);
      if (!q) {
        // 折叠组成员暂无节点：位置作为「待建位置」留给展开时消费（与原 app.js 语义一致）
        assert.ok(hidden.has(id), `applyOverviewLayout 后缺节点 ${id}`);
        continue;
      }
      maxErr = Math.max(maxErr, Math.hypot(q.x - p.x, q.y - p.y));
    }
    assert.ok(maxErr < 1e-9, `网格位置写入误差 ${maxErr}（应精确写入 RenderNode）`);
    assert.deepStrictEqual(r._camera, { x: 0, y: 0, scale: 1 }, "applyOverviewLayout 应重置相机");
    assert.strictEqual(r._userAdjusted, false);
    assert.strictEqual(host.createCount, 1, "applyOverviewLayout 不得新建第二张画布");
    assert.strictEqual(r._positions, undefined, "兼容别名必须已删除");
    r.dispose();
  });

  console.log(JSON.stringify({
    suite: "render_scene",
    results,
    passed: results.filter((r) => r.ok).length,
    failed: results.filter((r) => !r.ok).length,
  }));
}

run();
