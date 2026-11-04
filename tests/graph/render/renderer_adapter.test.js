/**
 * B4 / I-07 RendererAdapter 机检（Node，无 DOM；host 注入）。
 * 运行：node tests/graph/render/renderer_adapter.test.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "../../..");
const JS = path.join(ROOT, "src/memoria/ui/static/app/js/graph-multilevel");
const Canonical = require(path.join(JS, "canonical.js"));
const Adapter = require(path.join(JS, "renderer-adapter.js"));
const VM = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/vm-b4.json"), "utf8"));
const results = [];
function check(name, fn) {
  try {
    fn();
    results.push({ name, ok: true });
  } catch (err) {
    results.push({ name, ok: false, error: String(err && err.stack || err) });
    throw err;
  }
}
function makeCtx() {
  const ctx = {
    calls: 0,
    strokeAlphas: [],
    clearRect() { this.calls += 1; },
    beginPath() { this.calls += 1; },
    moveTo() { this.calls += 1; },
    lineTo() { this.calls += 1; },
    stroke() { this.calls += 1; this.strokeAlphas.push(this.globalAlpha); },
    fill() { this.calls += 1; },
    arc() { this.calls += 1; },
    fillText() { this.calls += 1; },
    setTransform() {},
    setLineDash() {},
    measureText(text) { return { width: String(text).length * 6 }; },
  };
  return ctx;
}
function makeHost() {
  return {
    canvas: null,
    ctx: null,
    createCanvas(width, height) {
      const canvas = {
        width: Math.round(width),
        height: Math.round(height),
        getBoundingClientRect: () => ({ left: 0, top: 0, width: 640, height: 480 }),
        style: {},
        setAttribute() {},
      };
      this.canvas = canvas;
      this.ctx = makeCtx();
      return { canvas, ctx: this.ctx };
    },
    append() {},
    remove() {},
    listeners: [],
    on(target, type, handler) { this.listeners.push([target, type, handler]); },
    off() {},
    rect: () => ({ left: 0, top: 0, width: 640, height: 480 }),
    dpr: () => 1,
  };
}
function container() { return { clientWidth: 640, clientHeight: 480 }; }
function run() {
  // ── 1. 五方法 + 2D/3D 同签名 ───────────────────────────────────────────
  check("2d_3d_same_signature_five_methods", () => {
    const host = makeHost();
    const r2 = new Adapter.Renderer2D(container(), { host });
    const r3 = new Adapter.Renderer3D(container());
    for (const key of ["getCapabilities", "render", "update", "dispose", "on"]) {
      assert.strictEqual(typeof r2[key], "function", `2D 缺 ${key}`);
      assert.strictEqual(typeof r3[key], "function", `3D 缺 ${key}`);
      assert.strictEqual(r2[key].length, r3[key].length, `${key} 2D/3D 参数个数不一致`);
    }
  });

  check("2d_capabilities_frozen_budget", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host });
    const caps = r.getCapabilities();
    assert.strictEqual(caps.maxNodes, 200);
    assert.strictEqual(caps.maxEdges, 400);
    assert.strictEqual(caps.animationMaxMs, 180);
    assert.deepStrictEqual(caps.backends, ["2d"]);
    assert.strictEqual(caps.capable, true);
    assert.strictEqual(caps.fps, 60);
    assert.strictEqual(caps.screenSpaceSizes, true);
  });

  check("3d_capability_false_and_fail_visible", () => {
    const r3 = new Adapter.Renderer3D(container());
    const caps = r3.getCapabilities();
    assert.strictEqual(caps.capability, false);
    assert.strictEqual(caps.capable, false);
    assert.strictEqual(caps.backend, "3d");
    assert.strictEqual(caps.reason, "3D_NOT_IN_0_5");
    for (const fn of ["render", "update"]) {
      assert.throws(() => r3[fn](container(), VM), (err) => err.code === "RENDER_UNSUPPORTED_BACKEND");
    }
    assert.deepStrictEqual(r3.dispose(), { status: "ok", already: true });
    // 3D capability=false 不阻断 2D：2D 仍可正常创建
    const host = makeHost();
    const r2 = new Adapter.Renderer2D(container(), { host });
    assert.strictEqual(r2.render(container(), VM).status, "ok");
  });

  // ── 2. 2D smoke：只画 presence=shown / 预算统计 / 标签 LOD 复用 ────────
  check("2d_smoke_only_shown_and_stats", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host });
    const summary = r.render(container(), VM);
    assert.strictEqual(summary.status, "ok");
    assert.strictEqual(summary.backend, "2d");
    // 6 nodes: 3 shown + 1 cluster root shown (cl_root) + cl1 shown = 4 shown, c/d 不画
    assert.strictEqual(r.lastRender.shownNodes, 4);
    assert.strictEqual(r.lastRender.shownEdges, 3);
    assert.strictEqual(r.lastRender.nodes, 4);
    assert.strictEqual(r.lastRender.edges, 3);
    assert.strictEqual(r.lastRender.bounded, true);
    // suppressed/unknown 节点没有任何绘制位置
    assert.ok(!r._positions.has("c"));
    assert.ok(!r._positions.has("d"));
    assert.ok(r._positions.has("cl_root"));
  });

  check("label_lod_reuses_legacy_module", () => {
    const calls = [];
    global.MemoriaGraphLabels = {
      layoutNodeLabels(items, opts) {
        calls.push({ count: items.length, opts });
        return { visibleIds: new Set(items.slice(0, 2).map((i) => i.id)), hiddenIds: [] };
      },
    };
    try {
      const host = makeHost();
      const r = new Adapter.Renderer2D(container(), { host });
      r.render(container(), VM);
      assert.strictEqual(calls.length, 1, "Renderer 未复用 MemoriaGraphLabels.layoutNodeLabels");
      assert.strictEqual(r.lastRender.labels, 2, "LOD 返回的 visibleIds 应控制标签数");
    } finally {
      delete global.MemoriaGraphLabels;
    }
  });

  // ── 3. 确定性布局 + 会话内保位（旧 KGviz 对齐项）─────────────────────
  check("deterministic_layout_and_session_stability", () => {
    const hostA = makeHost();
    const hostB = makeHost();
    const a = new Adapter.Renderer2D(container(), { host: hostA });
    const b = new Adapter.Renderer2D(container(), { host: hostB });
    a.render(container(), VM);
    b.render(container(), VM);
    const pa = [...a._positions.entries()].sort(([x], [y]) => x.localeCompare(y));
    const pb = [...b._positions.entries()].sort(([x], [y]) => x.localeCompare(y));
    assert.deepStrictEqual(pa, pb, "同 VM 两次 render 布局不一致");
    const before = JSON.stringify([...a._positions.entries()].sort());
    const upd = a.update(VM, {});
    assert.strictEqual(upd.moved, 0, "update 同 VM 不应移动节点（会话内保位）");
    assert.strictEqual(JSON.stringify([...a._positions.entries()].sort()), before);
  });

  // ── 4. 事件回传（nodeClick/edgeClick/backgroundClick；payload 无导航）──
  check("events_payloads_have_no_navigation_fields", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host });
    r.render(container(), VM);
    const events = [];
    r.on("nodeClick", (e) => events.push(["nodeClick", e]));
    r.on("edgeClick", (e) => events.push(["edgeClick", e]));
    r.on("backgroundClick", (e) => events.push(["backgroundClick", e]));
    r.on("hover", (e) => events.push(["hover", e]));
    const pos = r._positions.get("cl1");
    r.handlePointClick(pos.x, pos.y);
    const a = r._positions.get("a");
    r.handlePointClick(a.x, a.y);
    r.handlePointClick(2, 2);
    const nodeClick = events.find(([t]) => t === "nodeClick");
    assert.ok(nodeClick, "应有 nodeClick");
    assert.deepStrictEqual(Object.keys(nodeClick[1]).sort(), ["kind", "node_id"]);
    const back = events.find(([t]) => t === "backgroundClick");
    assert.ok(back);
    assert.deepStrictEqual(Object.keys(back[1]), []);
    // 边点击：取 a-b 中点
    const b = r._positions.get("b");
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const edge = r.handlePointClick(mid.x, mid.y);
    if (edge.type === "edgeClick") {
      assert.ok("edge_id" in edge.payload);
      assert.ok(!("frame" in edge.payload) && !("mode" in edge.payload));
    }
    for (const [, payload] of events) {
      for (const forbidden of ["frame", "frame_id", "mode", "focus", "level", "dimension", "history", "navigate"]) {
        assert.ok(!(forbidden in payload), `事件 payload 泄漏导航字段 ${forbidden}`);
      }
    }
  });

  // ── 5. 预算 fail-visible（Renderer 不裁剪）────────────────────────────
  check("budget_overflow_is_fail_visible_not_silent_crop", () => {
    const big = {
      ...VM,
      nodes: Array.from({ length: 201 }, (_, i) => ({
        id: "n" + i, kind: "kp", label: "n" + i, role: "member", presence: "shown",
      })),
      edges: [],
    };
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host });
    assert.throws(() => r.render(container(), big), (err) =>
      err.code === "RENDER_BUDGET_EXCEEDED" && err.detail.max_nodes === 200);
    const bigEdges = {
      ...VM,
      nodes: [
        { id: "a", kind: "kp", label: "a", role: "member", presence: "shown" },
        { id: "b", kind: "kp", label: "b", role: "member", presence: "shown" },
      ],
      edges: Array.from({ length: 401 }, (_, i) => ({ id: `semantic|a|b|${i}`, type: "semantic", presence: "shown" })),
    };
    assert.throws(() => r.render(container(), bigEdges), (err) => err.code === "RENDER_BUDGET_EXCEEDED");
  });

  // ── 6. 无效 VM fail-closed ─────────────────────────────────────────
  check("invalid_vm_fail_closed", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host });
    const cases = [
      [{ ...VM, nodes: [{ id: "x", kind: "third", label: "x", role: "member" }] }, "kind"],
      [{ ...VM, nodes: [{ id: "x", kind: "kp", label: "x", role: "bridge" }] }, "role"],
      [{ ...VM, nodes: [{ id: "x", kind: "kp", label: "x", role: "member", presence: "suppressed" }] }, "rule_id"],
      [{ ...VM, nodes: [{ id: "x", kind: "kp", role: "member" }] }, "label"],
      [{ ...VM, mode: "full" }, "禁入字段"],
      [{ ...VM, nodes: [{ id: "x", kind: "cluster", label: "x", role: "member", layout_group: { semantic: false } }] }, "layout_group"],
    ];
    for (const [vm, needle] of cases) {
      assert.throws(() => r.render(container(), vm), (err) =>
        err.code === "GRAPH_PRESENCE_INVALID" && String(err.message).includes(needle),
        `未对无效 VM fail-closed：${needle}`);
    }
  });

  // ── 7. Renderer 不读 data_edge_ids（静态 + 行为）────────────────────
  check("renderer_never_reads_data_edge_ids", () => {
    const src = fs.readFileSync(path.join(JS, "renderer-adapter.js"), "utf8");
    const code = src
      .split("\n")
      .filter((line) => !/^\s*(\*|\/\/)/.test(line))
      .join("\n");
    assert.ok(!code.includes(".get(\"data_edge_ids\")"), "渲染器读取了 data_edge_ids");
    assert.ok(!code.includes("[\"data_edge_ids\"]"), "渲染器读取了 data_edge_ids");
    // 行为：VM 带 data_edge_ids 时渲染结果与不带时一致
    const withIds = JSON.parse(JSON.stringify(VM));
    withIds.edges[0].data_edge_ids = ["semantic|a|b"];
    const hostA = makeHost();
    const hostB = makeHost();
    const a = new Adapter.Renderer2D(container(), { host: hostA });
    const b = new Adapter.Renderer2D(container(), { host: hostB });
    a.render(container(), VM);
    b.render(container(), withIds);
    assert.strictEqual(a.lastRender.nodes, b.lastRender.nodes);
    assert.strictEqual(a.lastRender.edges, b.lastRender.edges);
  });

  // ── 8. dispose 停止事件、3D 不阻断 ─────────────────────────────────
  check("dispose_and_no_blocking_on_3d_unavailable", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host });
    r.render(container(), VM);
    const got = [];
    r.on("backgroundClick", (e) => got.push(e));
    r.dispose();
    r.dispose(); // 幂等
    assert.throws(() => r.render(container(), VM), /dispose/);
    // createRendererAdapter 工厂：3D 返回 capability=false 的实例而非抛错（不阻断）
    const r3 = Adapter.createRendererAdapter("3d", container(), {});
    assert.strictEqual(r3.getCapabilities().capability, false);
  });

  // ── 4b. 边高亮（旧 KGviz 对齐项）────────────────────────────────────
  check("edge_highlight_on_hover", () => {
    const host = makeHost();
    const r = new Adapter.Renderer2D(container(), { host });
    r.render(container(), VM);
    r._hoverId = "a";
    r._draw();
    const alphas = host.ctx.strokeAlphas || [];
    assert.ok(alphas.some((a) => a >= 0.9), `悬停节点关联边应高亮（stroke alphas=${JSON.stringify(alphas.slice(0, 8))}）`);
    assert.ok(alphas.some((a) => a <= 0.6), "非关联边应保持低亮");
  });

  // ── 9. 挂载 + 事件回传 + 3D 显式回退 2D（不阻断）─────────────────────
  check("mount_wires_events_and_falls_back_to_2d", () => {
    const Mount = require(path.join(JS, "mount.js"));
    const host = makeHost();
    const seen = [];
    const fakeNav = { handleRendererEvent: (evt) => seen.push(evt) };
    const mounted = Mount.mountGraphView({
      container: container(),
      vm: VM,
      nav: fakeNav,
      backend: "2d",
      host,
      resolveFile: (nodeId) => (nodeId === "a" ? "a.md" : null),
    });
    assert.strictEqual(mounted.fellBack, false);
    assert.strictEqual(mounted.rendererCapabilities.capable, true);
    assert.strictEqual(seen.length, 0, "render 不应产生事件");
    const pos = mounted.renderer._positions.get("a");
    mounted.renderer.handlePointClick(pos.x, pos.y);
    assert.strictEqual(seen.length, 1);
    assert.strictEqual(seen[0].type, "nodeClick");
    assert.strictEqual(seen[0].node_id, "a");
    assert.strictEqual(seen[0].file, "a.md", "Presentation resolveFile 应补 file（S5 CLICK_KP guard）");
    // 3D 不可用 ⇒ 显式回退 2D，不抛错、不阻断
    const host3 = makeHost();
    const fallback = Mount.mountGraphView({
      container: container(), vm: VM, nav: fakeNav, backend: "3d", host: host3,
    });
    assert.strictEqual(fallback.fellBack, true);
    assert.strictEqual(fallback.fallbackReason, "3D_NOT_IN_0_5");
    assert.strictEqual(fallback.renderer.getCapabilities().backend, "2d");
    assert.strictEqual(fallback.render(VM).status, "ok");
    const posFallback = fallback.renderer._positions.get("a");
    fallback.renderer.handlePointClick(posFallback.x, posFallback.y);
    assert.ok(seen.length >= 2, "回退后的 2D 渲染器仍应回传事件");
    fallback.destroy();
  });

  console.log(JSON.stringify({ suite: "renderer_adapter", results, passed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length }));
}

run();
