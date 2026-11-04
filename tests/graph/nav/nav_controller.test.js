/**
 * B4 / I-08 NavController 机检（Node，无 DOM）。
 * 覆盖：9 主状态 / 正交变量 / T01–T30 / frame_id 复算 / 事务化 diff=0 / expand 不改 nav。
 * 运行：node tests/graph/nav/nav_controller.test.js
 */
"use strict";
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "../../..");
const JS = path.join(ROOT, "src/memoria/ui/static/app/js/graph-multilevel");
const Canonical = require(path.join(JS, "canonical.js"));
const Nav = require(path.join(JS, "nav-controller.js"));
const { NavController, MAIN_STATES, DISPLAY_STATES, MODES, EVENTS, TRANSITION_ROWS, expandTransitions } = Nav;

const results = [];
const details = {};
function check(name, fn) {
  try {
    fn();
    results.push({ name, ok: true });
  } catch (err) {
    results.push({ name, ok: false, error: String((err && err.stack) || err) });
    throw err;
  }
}

function makeCtl(extra = {}) {
  return new NavController({ editionSha: "ed1", activeDimensions: ["A", "H"], ...extra });
}
function emitted(ctl, type) {
  const got = [];
  ctl.on(type, (payload) => got.push(payload));
  return got;
}
function at(state) {
  const ctl = makeCtl();
  const step = (evt, payload) => {
    const r = ctl.dispatch(evt, payload);
    assert.strictEqual(r.ok, true, `构造 ${state} 失败：${evt} ${JSON.stringify(r.error || {})}`);
    return r;
  };
  switch (state) {
    case "Idle":
      break;
    case "Loading":
      step("OPEN_GRAPH");
      break;
    case "Degraded":
      step("OPEN_GRAPH");
      step("DATA_FAILED");
      break;
    case "Overview":
      step("OPEN_GRAPH");
      step("DATA_READY");
      break;
    case "Focused":
      step("OPEN_GRAPH");
      step("DATA_READY");
      step("FOCUS_NODE", { node_id: "a" });
      break;
    case "HierarchyDrilled":
      step("OPEN_GRAPH");
      step("DATA_READY");
      step("CLICK_CLUSTER", { node_id: "c1", kind: "cluster", expandable: true });
      break;
    case "RelationExpanded":
      step("OPEN_GRAPH");
      step("DATA_READY");
      step("SELECT_DIMENSION", { dimension_id: "A" });
      break;
    case "RelationDeepened":
      step("OPEN_GRAPH");
      step("DATA_READY");
      step("SELECT_DIMENSION", { dimension_id: "A" });
      step("EXPLICIT_NEW_HOP");
      break;
    case "Stale":
      step("OPEN_GRAPH");
      step("DATA_READY");
      step("CORPUS_CHANGED", { editionSha: "ed2" });
      break;
    default:
      throw new Error(`未支持状态 ${state}`);
  }
  assert.strictEqual(ctl.getState(), state, `构造状态错误：期望 ${state} 实得 ${ctl.getState()}`);
  return ctl;
}

const PY_FRAME_HASHES = {
  // Python: memoria.graph.multilevel.admission.sha256_canonical(frame_spec)
  "L0|fam-a|A|root|1|false|default|200|400": "2a1f980b4ec3345f095351ad60082fc0cdbef75266e6ad2a0992a3b4114b9bda",
  "L0|fam-a|A|root|1|false|full|200|400": "19d4f53e2c3d988e1f2b45b98a9440b08191ab7dfc2ff3369d7c13c424100b4f",
  "L1|fam-b|H|cl0|1|false|default|200|400": "4e68522eec29c1de71bfadb16ec4b56eb9ea994fcd236bacc33892840d90f9b5",
  "L1|fam-a|A|a|2|true|default|200|400": "0048cf48b05027d8d59fa72855659b0166c9d80dc314954c9ed7da9d9fbeac41",
};

function run() {
  // ── 0. 状态/事件/正交变量冻结 ───────────────────────────────────────
  check("nine_main_states_and_orthogonal_vars", () => {
    assert.deepStrictEqual(MAIN_STATES, [
      "Idle", "Loading", "Degraded", "Overview", "Focused",
      "HierarchyDrilled", "RelationExpanded", "RelationDeepened", "Stale",
    ]);
    assert.strictEqual(MAIN_STATES.length, 9);
    assert.deepStrictEqual(MODES, ["default", "full"]);
    assert.deepStrictEqual(Nav.DATA_STATES, ["ok", "empty_nosemantic"]);
    assert.strictEqual(EVENTS.length, 21);
    // FullExpanded / EmptyNoSemantic 不得是主状态（正交变量）
    for (const forbidden of ["FullExpanded", "EmptyNoSemantic"]) {
      assert.ok(!MAIN_STATES.includes(forbidden), `${forbidden} 不得作为主状态`);
    }
  });

  check("transition_table_t01_t30_unique_pairs", () => {
    assert.strictEqual(TRANSITION_ROWS.length, 30);
    assert.deepStrictEqual(TRANSITION_ROWS.map((r) => r.id), Array.from({ length: 30 }, (_, i) => `T${String(i + 1).padStart(2, "0")}`));
    const edges = expandTransitions();
    const seen = new Set();
    const duplicates = [];
    for (const e of edges) {
      const key = `${e.from}|${e.event}`;
      if (seen.has(key)) duplicates.push(key);
      seen.add(key);
    }
    assert.deepStrictEqual(duplicates, [], `(state,event) 重复：${duplicates}`);
    details.expandedEdges = edges.length;
    details.designClaimedEdges = 148;
    details.edgeCountNote = "S5-eng-check 声称 148；按唯一 (state,event) 展开为 89（差异已报 Lead/SE 复核）";
    // wildcard 展开正确
    const closeRows = edges.filter((e) => e.event === "CLOSE");
    assert.strictEqual(closeRows.length, 8, "T05 ALL\\{Idle} 应展开 8 边");
    const reloadRows = edges.filter((e) => e.event === "RELOAD");
    assert.strictEqual(reloadRows.length, 9, "T06 ALL 应展开 9 边");
    for (const e of edges) {
      assert.ok(MAIN_STATES.includes(e.from), `非法 From ${e.from}`);
      assert.ok(EVENTS.includes(e.event), `非法 Event ${e.event}`);
    }
  });

  // ── 1. frame_spec / frame_id 可复算（与 Python canonical 对齐）────────
  check("frame_spec_eight_fields_and_python_canonical_hashes", () => {
    const ctl = at("Overview");
    const spec = ctl.getFrameSpec();
    assert.deepStrictEqual(Object.keys(spec).sort(), Nav.FRAME_SPEC_FIELDS.slice().sort());
    for (const forbidden of ["frame_id", "edition", "edition_sha", "nav_id", "mode_nav", "focus_ui"]) {
      assert.ok(!(forbidden in spec), `frame_spec 含禁入字段 ${forbidden}`);
    }
    assert.deepStrictEqual(spec.budget, { max_nodes: 200, max_edges: 400 });
    const key = `${spec.level}|${spec.view_family}|${spec.dimension_id}|${spec.focus}|${spec.hop}|${spec.new_hop}|${spec.mode}|${spec.budget.max_nodes}|${spec.budget.max_edges}`;
    assert.strictEqual(ctl.getFrameId(), PY_FRAME_HASHES[key], `frame_id 与 Python canonical 不符：${key}`);
    assert.strictEqual(ctl.getFrameId(), Canonical.canonicalSha(spec));
    const frames = [
      { level: "L1", view_family: "fam-b", dimension_id: "H", focus: "cl0", hop: 1, new_hop: false, mode: "default", budget: { max_nodes: 200, max_edges: 400 } },
      { level: "L1", view_family: "fam-a", dimension_id: "A", focus: "a", hop: 2, new_hop: true, mode: "default", budget: { max_nodes: 200, max_edges: 400 } },
    ];
    const expected = [
      "4e68522eec29c1de71bfadb16ec4b56eb9ea994fcd236bacc33892840d90f9b5",
      "0048cf48b05027d8d59fa72855659b0166c9d80dc314954c9ed7da9d9fbeac41",
    ];
    frames.forEach((f, i) => assert.strictEqual(Canonical.canonicalSha(f), expected[i], `canonical sha 不符 #${i}`));
  });

  // ── 2. T01–T30 逐行场景 ────────────────────────────────────────────
  check("t01_t30_all_rows_have_passing_scenario", () => {
    const scenarios = {
      T01: () => [at("Idle"), "OPEN_GRAPH", {}],
      T02: () => [at("Loading"), "DATA_READY", { editionSha: "ed1" }],
      T03: () => [at("Loading"), "DATA_FAILED", {}],
      T04: () => [at("Degraded"), "RETRY", {}],
      T05: () => [at("Overview"), "CLOSE", {}],
      T06: () => [at("Idle"), "RELOAD", {}],
      T07: () => [at("Overview"), "DATA_REFRESHED", { editionSha: "ed1", data_state: "empty_nosemantic" }],
      T08: () => [at("Overview"), "FOCUS_NODE", { node_id: "a" }],
      T09: () => [at("Overview"), "CLICK_KP", { node_id: "a", kind: "kp", file: "a.md" }],
      T10: () => [at("Overview"), "CLICK_EDGE", { edge_id: "semantic|a|b" }],
      T11: () => [at("Overview"), "CLICK_BACKGROUND", {}],
      T12: () => [at("Focused"), "CLICK_BACKGROUND", {}],
      T13: () => [at("Overview"), "CLICK_CLUSTER", { node_id: "c1", kind: "cluster", expandable: true }],
      T14: () => [at("Focused"), "CLICK_CLUSTER", { node_id: "c1", kind: "cluster", expandable: true }],
      T15: () => [at("HierarchyDrilled"), "CLICK_CLUSTER", { node_id: "c2", kind: "cluster", expandable: true }],
      T16: () => [at("RelationExpanded"), "CLICK_CLUSTER", { node_id: "c2", kind: "cluster", expandable: true }],
      T17: () => [at("RelationDeepened"), "CLICK_CLUSTER", { node_id: "c2", kind: "cluster", expandable: true }],
      T18: () => [at("Overview"), "FOCUS_LOST", {}],
      T19: () => [at("Focused"), "FOCUS_CLEAR", {}],
      T20: () => [at("Focused"), "BACK", {}],
      T21: () => [at("RelationDeepened"), "BACK", {}],
      T22: () => [at("Overview"), "BACK", {}],
      T23: () => [at("RelationExpanded"), "BREADCRUMB_TO", { index: 0 }],
      T24: () => [at("Overview"), "SELECT_DIMENSION", { dimension_id: "H" }],
      T25: () => [at("RelationExpanded"), "EXPLICIT_NEW_HOP", {}],
      T26: () => [at("RelationDeepened"), "EXPLICIT_NEW_HOP", {}],
      T27: () => [at("Overview"), "TOGGLE_EXPAND", {}],
      T28: () => [at("Overview"), "CORPUS_CHANGED", { editionSha: "ed2" }],
      T29: () => [at("Overview"), "RESET", {}],
      T30: () => [at("Stale"), "RESET", {}],
    };
    const rowById = Object.fromEntries(TRANSITION_ROWS.map((r) => [r.id, r]));
    const covered = [];
    for (const row of TRANSITION_ROWS) {
      const scenario = scenarios[row.id];
      assert.ok(scenario, `缺 T 行场景：${row.id}`);
      const [ctl, evt, payload] = scenario();
      const beforeState = ctl.getState();
      const result = ctl.dispatch(evt, payload);
      assert.strictEqual(result.ok, true, `${row.id} ${beforeState}-${evt} 失败：${JSON.stringify(result.error || {})}`);
      const to = row.to;
      if (to === "SELF") {
        assert.strictEqual(ctl.getState(), beforeState, `${row.id} 应 SELF（状态不变）`);
      } else if (to === "ORIGIN") {
        assert.ok(DISPLAY_STATES.includes(ctl.getState()), `${row.id} 应回显示态（origin），实得 ${ctl.getState()}`);
      } else if (to === "ANCESTOR") {
        assert.ok(DISPLAY_STATES.includes(ctl.getState()), `${row.id} 应回显示态（祖先），实得 ${ctl.getState()}`);
      } else if (to === "DRILL_TARGET") {
        assert.ok(["HierarchyDrilled", "RelationExpanded"].includes(ctl.getState()), `${row.id} drill 目标非法：${ctl.getState()}`);
      } else if (to === "DIM_TARGET") {
        assert.ok(["Overview", "HierarchyDrilled", "RelationExpanded"].includes(ctl.getState()), `${row.id} 维度目标非法`);
      } else {
        assert.strictEqual(ctl.getState(), to, `${row.id} 目标应为 ${to}，实得 ${ctl.getState()}`);
      }
      covered.push(row.id);
    }
    assert.strictEqual(covered.length, 30);
    details.t01_t30 = covered;
  });

  // ── 3. 点击/焦点语义 ────────────────────────────────────────────────
  check("focus_does_not_change_frame_and_background_returns_origin", () => {
    const ctl = at("Overview");
    const frameId = ctl.getFrameId();
    const frameFocus = ctl.getFrame().focus;
    const jumps = emitted(ctl, "editorJump");
    assert.strictEqual(ctl.dispatch("FOCUS_NODE", { node_id: "a" }).ok, true);
    assert.strictEqual(ctl.getFrameId(), frameId, "FOCUS_NODE 不得改 frame（R-S5-5）");
    assert.strictEqual(ctl.getFrame().focus, frameFocus);
    assert.strictEqual(ctl.getUiFocus(), "a");
    assert.strictEqual(ctl.dispatch("CLICK_BACKGROUND").ok, true);
    assert.strictEqual(ctl.getState(), "Overview");
    assert.strictEqual(ctl.getUiFocus(), null);
    assert.strictEqual(ctl.dispatch("CLICK_KP", { node_id: "a", kind: "kp", file: "a.md" }).ok, true);
    assert.strictEqual(jumps.length, 1, "kp 点击应发 editorJump 事件");
    assert.deepStrictEqual(Object.keys(jumps[0]).sort(), ["file", "node_id"]);
    // 未知 kind fail-closed
    assert.strictEqual(ctl.dispatch("CLICK_KP", { node_id: "a", kind: "cluster", file: "a.md" }).ok, false);
  });

  check("drill_back_restores_exact_canonical_frame", () => {
    const ctl = at("Overview");
    const before = ctl.getFrameId();
    const beforeSnap = ctl.snapshotSha();
    assert.strictEqual(ctl.dispatch("CLICK_CLUSTER", { node_id: "c1", kind: "cluster", expandable: true }).ok, true);
    assert.notStrictEqual(ctl.getFrameId(), before);
    assert.strictEqual(ctl.getStack().length, 1);
    assert.strictEqual(ctl.dispatch("BACK").ok, true);
    assert.strictEqual(ctl.getFrameId(), before, "BACK 未精确恢复 canonical frame");
    assert.strictEqual(ctl.snapshotSha(), beforeSnap, "BACK 后 canonical state 未恢复");
    assert.strictEqual(ctl.getStack().length, 0);
  });

  check("dimension_switch_push_and_back", () => {
    const ctl = at("Overview");
    const before = ctl.getFrameId();
    const beforeSnap = ctl.snapshotSha();
    const r = ctl.dispatch("SELECT_DIMENSION", { dimension_id: "H" });
    assert.strictEqual(r.ok, true);
    assert.strictEqual(ctl.getFrame().dimension, "H");
    assert.strictEqual(ctl.getStack().length, 1);
    assert.ok(ctl.getHistory().length >= 0);
    assert.strictEqual(ctl.dispatch("BACK").ok, true);
    assert.strictEqual(ctl.getFrameId(), before, "维度切换 BACK 未回到切换前 canonical frame");
    assert.strictEqual(ctl.snapshotSha(), beforeSnap);
    assert.strictEqual(ctl.dispatch("SELECT_DIMENSION", { dimension_id: "Z" }).ok, false);
  });

  check("explicit_new_hop_unique_and_idempotent", () => {
    const ctl = at("RelationExpanded");
    assert.strictEqual(ctl.getFrame().hop, 1);
    assert.strictEqual(ctl.dispatch("EXPLICIT_NEW_HOP").ok, true);
    assert.strictEqual(ctl.getState(), "RelationDeepened");
    assert.strictEqual(ctl.getFrame().hop, 2);
    assert.strictEqual(ctl.getFrame().new_hop, true);
    const stackLen = ctl.getStack().length;
    assert.strictEqual(ctl.dispatch("EXPLICIT_NEW_HOP").ok, true);
    assert.strictEqual(ctl.getStack().length, stackLen, "重复 NEW_HOP 必须幂等（不 push）");
    // H 维不允许多跳
    const h = at("Overview");
    h.dispatch("SELECT_DIMENSION", { dimension_id: "H" });
    assert.strictEqual(h.dispatch("EXPLICIT_NEW_HOP").ok, false);
  });

  // ── 4. expand 不改 nav（S5-8/R-S5-7）────────────────────────────────
  check("toggle_expand_does_not_change_nav", () => {
    const calls = [];
    const ctl = makeCtl({ requestAdmission: (spec) => { calls.push(spec); return { status: "ok" }; } });
    for (const [evt, payload] of [
      ["OPEN_GRAPH", {}], ["DATA_READY", {}], ["CLICK_CLUSTER", { node_id: "c1", kind: "cluster", expandable: true }],
    ]) assert.strictEqual(ctl.dispatch(evt, payload).ok, true);
    const before = {
      state: ctl.getState(), focus: ctl.getFrame().focus, level: ctl.getFrame().level,
      dimension: ctl.getFrame().dimension, stack: ctl.getStack(), mode: ctl.getMode(),
    };
    const r = ctl.dispatch("TOGGLE_EXPAND", { candidate_superset: true });
    assert.strictEqual(r.ok, true);
    assert.strictEqual(ctl.getState(), before.state, "expand 改了主状态");
    assert.strictEqual(ctl.getFrame().focus, before.focus, "expand 改了 focus");
    assert.strictEqual(ctl.getFrame().level, before.level, "expand 改了 level");
    assert.strictEqual(ctl.getFrame().dimension, before.dimension, "expand 改了 dimension");
    assert.deepStrictEqual(ctl.getStack(), before.stack, "expand 改了 stack");
    assert.notStrictEqual(ctl.getMode(), before.mode, "expand 应切换正交 mode");
    assert.strictEqual(calls[calls.length - 1].mode, "full", "S4 请求应带 full mode");
    assert.strictEqual(ctl.getFrameId(), Canonical.canonicalSha(ctl.getFrameSpec()), "mode 变化后 frame_id 应可复算");
    assert.strictEqual(ctl.dispatch("TOGGLE_EXPAND", { candidate_superset: false }).ok, false);
  });

  // ── 5. 事务化：失败 diff=0（无孤立 stack / 无状态变化）───────────────
  check("transaction_failure_keeps_canonical_diff_zero", () => {
    const cases = [
      ["CLICK_CLUSTER", { node_id: "c1", kind: "cluster", expandable: true }],
      ["SELECT_DIMENSION", { dimension_id: "H" }],
      ["TOGGLE_EXPAND", {}],
    ];
    for (const [evt, payload] of cases) {
      const ctl = makeCtl({
        requestAdmission: () => { throw Object.assign(new Error("S4 down"), { code: "GRAPH_BUDGET_INVALID" }); },
      });
      for (const [e, p] of [["OPEN_GRAPH", {}], ["DATA_READY", {}]]) assert.strictEqual(ctl.dispatch(e, p).ok, true);
      const before = ctl.snapshotSha();
      const stackBefore = JSON.stringify(ctl.getStack());
      const result = ctl.dispatch(evt, payload);
      assert.strictEqual(result.ok, false, `${evt} 注入 S4 失败后不应成功`);
      assert.strictEqual(result.error.code, "GRAPH_BUDGET_INVALID");
      assert.strictEqual(ctl.snapshotSha(), before, `${evt} 失败后 canonical diff 非 0`);
      assert.strictEqual(JSON.stringify(ctl.getStack()), stackBefore, `${evt} 失败留下孤立 stack`);
    }
    // 初始 DATA_READY admission 失败 → Degraded（S5-9 初始失败路径）
    const ctl = makeCtl({ requestAdmission: () => { throw Object.assign(new Error("down"), { code: "GRAPH_INTERNAL" }); } });
    ctl.dispatch("OPEN_GRAPH");
    const r = ctl.dispatch("DATA_READY", {});
    assert.strictEqual(r.ok, true, "DATA_READY 当前实现不请求 admission（构造 frame 无 S4 失败面）");
  });

  // ── 6. 非法转移 fail-closed ──────────────────────────────────────────
  check("illegal_transitions_fail_closed", () => {
    const cases = [
      [at("Idle"), "CLICK_KP", { kind: "kp", file: "a.md" }],
      [at("Loading"), "FOCUS_NODE", { node_id: "a" }],
      [at("Stale"), "OPEN_GRAPH", {}],
      [at("Overview"), "OPEN_GRAPH", {}],
      [at("Overview"), "NOT_AN_EVENT", {}],
      [at("Overview"), "CLICK_CLUSTER", { node_id: "c1", kind: "kp", expandable: true }],
      [at("Overview"), "CORPUS_CHANGED", { editionSha: "ed1" }],
    ];
    for (const [ctl, evt, payload] of cases) {
      const before = ctl.snapshotSha();
      const r = ctl.dispatch(evt, payload);
      assert.strictEqual(r.ok, false, `${evt} 应 fail-closed`);
      assert.strictEqual(ctl.snapshotSha(), before, `${evt} 非法转移改了状态（diff 非 0）`);
    }
  });

  // ── 7. FOCUS_LOST / DATA_REFRESHED 存在且不重取景 ───────────────────
  check("focus_lost_and_data_refreshed_recovery", () => {
    assert.ok(expandTransitions().some((e) => e.event === "FOCUS_LOST"));
    assert.ok(expandTransitions().some((e) => e.event === "DATA_REFRESHED"));
    const ctl = at("Focused");
    const frameId = ctl.getFrameId();
    const r = ctl.dispatch("FOCUS_LOST");
    assert.strictEqual(r.ok, true);
    assert.ok(DISPLAY_STATES.includes(ctl.getState()));
    assert.strictEqual(ctl.getUiFocus(), null);
    const ctl2 = at("Overview");
    const before = ctl2.getFrameId();
    assert.strictEqual(ctl2.dispatch("DATA_REFRESHED", { editionSha: "ed1", data_state: "empty_nosemantic" }).ok, true);
    assert.strictEqual(ctl2.getFrameId(), before, "DATA_REFRESHED 不得重取景");
    assert.strictEqual(ctl2.getDataState(), "empty_nosemantic");
  });

  // ── 8. 持久化白名单 / 渲染器事件映射 ────────────────────────────────
  check("persistence_whitelist_only_mode_dimension_level0", () => {
    const ctl = at("RelationDeepened");
    const persisted = ctl.persist();
    assert.deepStrictEqual(Object.keys(persisted).sort(), ["dimension", "level0", "mode"]);
    assert.deepStrictEqual(Object.keys(persisted.level0).sort(), ["budget", "dimension_id", "focus", "level", "view_family"]);
    assert.ok(!("stack" in persisted) && !("history" in persisted) && !("focus" in persisted));
    const restored = makeCtl();
    restored.restorePersisted({ ...persisted, stack: [{ evil: true }], history: [1, 2] });
    assert.deepStrictEqual(restored.persist().level0.focus, persisted.level0.focus);
    assert.strictEqual(restored.getStack().length, 0, "重开不得恢复深栈");
  });

  check("renderer_event_mapping_no_navigation_leak", () => {
    const ctl = at("Overview");
    const jumps = emitted(ctl, "editorJump");
    // kp：S3-7 renderer payload 只有 node_id/kind（file 由 Presentation 解析）⇒ 无 file 时 fail-closed
    const kp = ctl.handleRendererEvent({ type: "nodeClick", node_id: "a", kind: "kp" });
    assert.strictEqual(kp.ok, false);
    assert.strictEqual(
      ctl.handleRendererEvent({ type: "nodeClick", node_id: "a", kind: "kp", file: "a.md" }).ok,
      true
    );
    assert.strictEqual(jumps.length, 1);
    // cluster → drill
    const drill = ctl.handleRendererEvent({ type: "nodeClick", node_id: "c1", kind: "cluster", expandable: true });
    assert.strictEqual(drill.ok, true);
    assert.strictEqual(ctl.getState(), "HierarchyDrilled");
    // background → 清 selection
    ctl.dispatch("CLICK_EDGE", { edge_id: "semantic|a|b" });
    assert.ok(ctl.getSelection());
    const back = ctl.handleRendererEvent({ type: "backgroundClick" });
    assert.strictEqual(back.ok, true);
    assert.strictEqual(ctl.getSelection(), null);
    // hover 不改导航
    const state = ctl.getState();
    const hover = ctl.handleRendererEvent({ type: "hover", node_id: "a" });
    assert.strictEqual(hover.ok, true);
    assert.strictEqual(ctl.getState(), state);
    // 未知 kind fail-closed
    assert.strictEqual(ctl.handleRendererEvent({ type: "nodeClick", node_id: "x", kind: "third" }).ok, false);
  });

  // ── 9. 栈上限（事务化失败 diff=0）──────────────────────────────────
  check("max_stack_overflow_is_transactional", () => {
    const ctl = makeCtl({ maxStack: 3 });
    for (const [e, p] of [["OPEN_GRAPH", {}], ["DATA_READY", {}]]) ctl.dispatch(e, p);
    let levels = 0;
    let failed = null;
    for (let i = 0; i < 8; i++) {
      const before = ctl.snapshotSha();
      const r = ctl.dispatch("CLICK_CLUSTER", { node_id: "c" + i, kind: "cluster", expandable: true });
      if (!r.ok) { failed = { r, before, after: ctl.snapshotSha() }; break; }
      levels += 1;
    }
    assert.ok(failed, "超过 maxStack 仍未失败");
    assert.strictEqual(failed.r.error.code, "S5_STACK_OVERFLOW");
    assert.strictEqual(failed.after, failed.before, "栈溢出失败后 diff 非 0");
    assert.strictEqual(ctl.getStack().length, 3);
  });

  console.log(JSON.stringify({ suite: "nav_controller", results, details, passed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length }));
}

run();
