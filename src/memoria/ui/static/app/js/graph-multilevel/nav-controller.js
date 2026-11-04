/**
 * Memoria 多层次图谱 B4 —— I-08 `NavController`（S5 导航状态机，仅 Presentation）。
 *
 * 冻结依据：
 *   - S5-nav-v1.md：9 主状态 + 正交 `mode`/`data_state`；T01–T30 唯一真源；
 *     `frame_id = sha256(canonical(S4_FRAME_SPEC))`（S6-6，8 字段，budget 展开）；
 *     导航事务化（成功才 commit，失败 canonical diff=0）；expand 不改 focus/level/dimension/stack。
 *   - S6-7：`GraphNavFrame` 字段；`NAV_STACK_ENTRY{frame_id,canonical_frame_ref,ts}`；
 *     持久化白名单 `mode/dimension/level0 frame`；不消费 S4 未冻结字段。
 *
 * 本模块是纯 JS（无 DOM），Node 测试与浏览器共用；`requestAdmission(frameSpec)` 由外部注入，
 * 真实实现里接 S4（Python/RPC）——本层只构造 frame_spec、不算 presence、不读 DataSource。
 */
(function (global) {
  "use strict";

  const Canonical = global.MemoriaGraphCanonical || (typeof require === "function" ? require("./canonical.js") : null);
  if (!Canonical) throw new Error("MemoriaGraphCanonical 未加载");

  const MAIN_STATES = Object.freeze([
    "Idle", "Loading", "Degraded", "Overview", "Focused",
    "HierarchyDrilled", "RelationExpanded", "RelationDeepened", "Stale",
  ]);
  const DISPLAY_STATES = Object.freeze([
    "Overview", "Focused", "HierarchyDrilled", "RelationExpanded", "RelationDeepened",
  ]);
  const MODES = Object.freeze(["default", "full"]);
  const DATA_STATES = Object.freeze(["ok", "empty_nosemantic"]);
  const EVENTS = Object.freeze([
    "OPEN_GRAPH", "DATA_READY", "DATA_FAILED", "RETRY", "CLOSE", "RELOAD",
    "DATA_REFRESHED", "FOCUS_NODE", "CLICK_KP", "CLICK_EDGE", "CLICK_BACKGROUND",
    "CLICK_CLUSTER", "FOCUS_LOST", "FOCUS_CLEAR", "BACK", "BREADCRUMB_TO",
    "SELECT_DIMENSION", "EXPLICIT_NEW_HOP", "TOGGLE_EXPAND", "CORPUS_CHANGED", "RESET",
  ]);
  const MAX_STACK = 50;
  const DEFAULT_BUDGET = Object.freeze({ max_nodes: 200, max_edges: 400 });
  const FRAME_SPEC_FIELDS = Object.freeze([
    "level", "view_family", "dimension_id", "focus", "hop", "new_hop", "mode", "budget",
  ]);
  const FRAME_SPEC_FORBIDDEN = Object.freeze([
    "frame_id", "edition", "edition_sha", "nav_id", "origin", "history",
  ]);

  // ── T01–T30（S5-nav-v1 附录 A；`from` 用集合占位符展开）──────────────────
  const T_ALL = "ALL";
  const T_ALL_MINUS_IDLE = "ALL\\{Idle}";
  const T_DISPLAY = "*";
  const TRANSITION_ROWS = Object.freeze([
    { id: "T01", from: ["Idle"], event: "OPEN_GRAPH", guard: "backend_ready", action: "read_settings_no_deep_stack", to: "Loading" },
    { id: "T02", from: ["Loading"], event: "DATA_READY", guard: "edition_match", action: "build_default_frame_set_data_state", to: "Overview" },
    { id: "T03", from: ["Loading"], event: "DATA_FAILED", guard: "retryable", action: "show_degraded", to: "Degraded" },
    { id: "T04", from: ["Degraded"], event: "RETRY", guard: "retryable", action: "retry_load", to: "Loading" },
    { id: "T05", from: [T_ALL_MINUS_IDLE], event: "CLOSE", guard: "", action: "save_settings_clear_memory_history", to: "Idle" },
    { id: "T06", from: [T_ALL], event: "RELOAD", guard: "", action: "rebuild_frame_clear_history", to: "Loading" },
    { id: "T07", from: [T_DISPLAY], event: "DATA_REFRESHED", guard: "edition_match", action: "recompute_data_state_no_reframe", to: "SELF" },
    { id: "T08", from: ["Overview", "HierarchyDrilled", "RelationExpanded", "RelationDeepened"], event: "FOCUS_NODE", guard: "node_focusable", action: "record_origin_ui_focus_keep_frame_focus", to: "Focused" },
    { id: "T09", from: [T_DISPLAY], event: "CLICK_KP", guard: "kind=kp&file", action: "jump_editor_frame_stack_unchanged", to: "SELF" },
    { id: "T10", from: [T_DISPLAY], event: "CLICK_EDGE", guard: "edge_id", action: "selection_edge_frame_stack_unchanged", to: "SELF" },
    { id: "T11", from: ["Overview", "HierarchyDrilled", "RelationExpanded", "RelationDeepened"], event: "CLICK_BACKGROUND", guard: "", action: "selection_null", to: "SELF" },
    { id: "T12", from: ["Focused"], event: "CLICK_BACKGROUND", guard: "", action: "selection_null_return_origin", to: "ORIGIN" },
    { id: "T13", from: ["Overview"], event: "CLICK_CLUSTER", guard: "kind=cluster&expandable", action: "tx_drill_push_hop_reset_clear_selection", to: "HierarchyDrilled" },
    { id: "T14", from: ["Focused"], event: "CLICK_CLUSTER", guard: "kind=cluster&expandable", action: "tx_drill_clear_ui_focus_push", to: "DRILL_TARGET" },
    { id: "T15", from: ["HierarchyDrilled"], event: "CLICK_CLUSTER", guard: "kind=cluster&expandable", action: "tx_drill_push", to: "HierarchyDrilled" },
    { id: "T16", from: ["RelationExpanded"], event: "CLICK_CLUSTER", guard: "kind=cluster&expandable", action: "tx_drill_push", to: "RelationExpanded" },
    { id: "T17", from: ["RelationDeepened"], event: "CLICK_CLUSTER", guard: "kind=cluster&expandable", action: "tx_drill_push", to: "RelationExpanded" },
    { id: "T18", from: [T_DISPLAY], event: "FOCUS_LOST", guard: "focus_missing", action: "tx_restore_nearest_ancestor_or_root", to: "ANCESTOR" },
    { id: "T19", from: ["Focused"], event: "FOCUS_CLEAR", guard: "", action: "return_origin_clear_selection", to: "ORIGIN" },
    { id: "T20", from: ["Focused"], event: "BACK", guard: "stack_nonempty", action: "tx_back_clear_ui_focus", to: "ORIGIN" },
    { id: "T21", from: ["HierarchyDrilled", "RelationExpanded", "RelationDeepened"], event: "BACK", guard: "stack_nonempty", action: "tx_pop_restore_frame", to: "ANCESTOR" },
    { id: "T22", from: ["Overview"], event: "BACK", guard: "stack_empty", action: "noop_announce_root", to: "Overview" },
    { id: "T23", from: [T_DISPLAY], event: "BREADCRUMB_TO", guard: "target_in_stack", action: "truncate_to_target_tx_restore", to: "ANCESTOR" },
    { id: "T24", from: [T_DISPLAY], event: "SELECT_DIMENSION", guard: "dimension_active", action: "tx_push_hop_reset_mode_keep_history", to: "DIM_TARGET" },
    { id: "T25", from: ["RelationExpanded"], event: "EXPLICIT_NEW_HOP", guard: "A&focus&hop=1", action: "tx_push_hop2_new_hop_true", to: "RelationDeepened" },
    { id: "T26", from: ["RelationDeepened"], event: "EXPLICIT_NEW_HOP", guard: "hop=2", action: "idempotent_noop", to: "RelationDeepened" },
    { id: "T27", from: [T_DISPLAY], event: "TOGGLE_EXPAND", guard: "S4_candidate_superset", action: "tx_toggle_mode_keep_frame_stack", to: "SELF" },
    { id: "T28", from: [T_DISPLAY], event: "CORPUS_CHANGED", guard: "edition_mismatch", action: "mark_stale_no_auto_reframe", to: "Stale" },
    { id: "T29", from: [T_DISPLAY], event: "RESET", guard: "", action: "clear_history_rebuild_default", to: "Loading" },
    { id: "T30", from: ["Stale"], event: "RESET", guard: "", action: "clear_history_reload", to: "Loading" },
  ]);

  function expandFrom(fromSpec) {
    if (Array.isArray(fromSpec)) {
      const out = [];
      for (const item of fromSpec) out.push(...expandFrom(item));
      return out;
    }
    if (fromSpec === T_ALL) return MAIN_STATES.slice();
    if (fromSpec === T_ALL_MINUS_IDLE) return MAIN_STATES.filter((s) => s !== "Idle");
    if (fromSpec === T_DISPLAY) return DISPLAY_STATES.slice();
    if (MAIN_STATES.includes(fromSpec)) return [fromSpec];
    throw new Error(`未知 From 占位符：${fromSpec}`);
  }

  /** 展开成 (state,event) 唯一边集；返回含每行 id 的列表。 */
  function expandTransitions() {
    const edges = [];
    for (const row of TRANSITION_ROWS) {
      for (const from of expandFrom(row.from)) edges.push({ ...row, from });
    }
    return edges;
  }

  // ── 错误码（S5/S6 canonical；只列本模块使用）────────────────────────────
  const ERR = Object.freeze({
    ILLEGAL: "S5_ILLEGAL_TRANSITION",
    GUARD: "S5_GUARD_FAILED",
    STACK_EMPTY: "S5_STACK_EMPTY",
    STACK_OVERFLOW: "S5_STACK_OVERFLOW",
    FRAME_ID: "GRAPH_FRAME_ID_INVALID",
    BUDGET: "GRAPH_BUDGET_INVALID",
    INTERNAL: "GRAPH_INTERNAL",
  });

  function clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  function deriveStateForFrame(frame) {
    if (!frame) return "Overview";
    if (frame.level && frame.level !== "L0") {
      if (frame.dimension === "H") return "HierarchyDrilled";
    }
    if (frame.dimension === "A" || frame.dimension === "a") {
      if (frame.hop >= 2 && frame.new_hop) return "RelationDeepened";
      if (frame.hop >= 1 && (frame.origin || frame.relation_expanded)) return "RelationExpanded";
    }
    return "Overview";
  }

  class NavController {
    constructor(options = {}) {
      this.options = options || {};
      this.root = {
        focus: options.rootFocus || options.root?.focus || "root",
        level: options.rootLevel || options.root?.level || "L0",
        view_family: options.rootViewFamily || options.root?.view_family || "fam-a",
        dimension_id: options.rootDimension || options.root?.dimension_id || "A",
      };
      this.activeDimensions = Array.isArray(options.activeDimensions)
        ? options.activeDimensions.slice()
        : ["A", "H"];
      this.budget = { ...DEFAULT_BUDGET, ...(options.budget || {}) };
      this.editionSha = options.editionSha || null;
      this.requestAdmission = typeof options.requestAdmission === "function"
        ? options.requestAdmission
        : () => ({ status: "ok" });
      this.now = typeof options.now === "function" ? options.now : () => Date.now();
      this.maxStack = Number(options.maxStack) > 0 ? Number(options.maxStack) : MAX_STACK;
      this._listeners = Object.create(null);

      this.state = "Idle";
      this.mode = "default";
      this.dataState = "ok";
      this.frame = null;
      this.stack = [];
      this.history = [];
      this.selection = null;
      this.uiFocus = null;
      this.originState = null;
      this.lastError = null;
    }

    // ── 只读面 ───────────────────────────────────────────────────────────
    getState() { return this.state; }
    getMode() { return this.mode; }
    getDataState() { return this.dataState; }
    getFrame() { return clone(this.frame); }
    getStack() { return clone(this.stack); }
    getHistory() { return clone(this.history); }
    getSelection() { return clone(this.selection); }
    getUiFocus() { return this.uiFocus; }
    getOriginState() { return this.originState; }
    getLastError() { return this.lastError; }
    getCapabilities() {
      return {
        states: MAIN_STATES.slice(),
        events: EVENTS.slice(),
        orthogonal: { mode: MODES.slice(), data_state: DATA_STATES.slice() },
        maxStack: this.maxStack,
        budget: { ...this.budget },
      };
    }

    getFrameSpec() {
      if (!this.frame) return null;
      return {
        level: this.frame.level,
        view_family: this.frame.view_family,
        dimension_id: this.frame.dimension,
        focus: this.frame.focus,
        hop: this.frame.hop,
        new_hop: this.frame.new_hop,
        mode: this.frame.mode,
        budget: { ...this.frame.budget },
      };
    }

    getFrameId() {
      const spec = this.getFrameSpec();
      if (!spec) return null;
      return Canonical.canonicalSha(spec);
    }

    /** 规范快照（事务 diff 口径；可机检）。 */
    snapshot() {
      return {
        state: this.state,
        mode: this.mode,
        dataState: this.dataState,
        frame: clone(this.frame),
        frameId: this.getFrameId(),
        stack: clone(this.stack),
        history: clone(this.history),
        selection: clone(this.selection),
        uiFocus: this.uiFocus,
        originState: this.originState,
      };
    }

    snapshotSha() {
      return Canonical.canonicalSha(this.snapshot());
    }

    persist() {
      // S5-12：只持久化 mode/dimension/level0 frame（不存深栈、不存 focus 历史）
      return {
        mode: this.mode,
        dimension: this.frame ? this.frame.dimension : this.root.dimension_id,
        level0: {
          focus: this.root.focus,
          level: this.root.level,
          view_family: this.root.view_family,
          dimension_id: this.root.dimension_id,
          budget: { ...this.budget },
        },
      };
    }

    restorePersisted(settings = {}) {
      if (MODES.includes(settings.mode)) this.mode = settings.mode;
      if (typeof settings.dimension === "string" && this.activeDimensions.includes(settings.dimension)) {
        this.root.dimension_id = settings.dimension;
      }
      if (settings.level0 && typeof settings.level0 === "object") {
        const l0 = settings.level0;
        if (typeof l0.focus === "string") this.root.focus = l0.focus;
        if (typeof l0.level === "string") this.root.level = l0.level;
        if (typeof l0.view_family === "string") this.root.view_family = l0.view_family;
        if (l0.budget && typeof l0.budget === "object") this.budget = { ...this.budget, ...l0.budget };
      }
      return this.persist();
    }

    // ── 事件订阅（nav 事件；不向 VM/渲染器泄漏）────────────────────────────
    on(type, handler) {
      if (typeof handler !== "function") throw new Error("on(type, handler) 需要函数");
      (this._listeners[type] || (this._listeners[type] = [])).push(handler);
      return () => this.off(type, handler);
    }

    off(type, handler) {
      const list = this._listeners[type];
      if (!list) return;
      const idx = list.indexOf(handler);
      if (idx >= 0) list.splice(idx, 1);
    }

    _emit(type, payload) {
      for (const fn of (this._listeners[type] || []).slice()) {
        try { fn(payload); } catch (err) { console.error("[NavController]", type, err); }
      }
      for (const fn of (this._listeners["*"] || []).slice()) {
        try { fn({ type, payload }); } catch (err) { console.error("[NavController]", err); }
      }
    }

    // ── 渲染器事件 → 导航事件（S3-7 → S5-3；payload 白名单无导航字段）────────
    handleRendererEvent(event = {}) {
      const type = event.type || event.event;
      if (type === "nodeClick") {
        const kind = event.kind;
        if (kind === "kp") return this.dispatch("CLICK_KP", { node_id: event.node_id, file: event.file, kind });
        if (kind === "cluster") {
          return this.dispatch("CLICK_CLUSTER", {
            node_id: event.node_id, kind, expandable: event.expandable !== false,
            level: event.level, view_family: event.view_family,
          });
        }
        return this._fail("CLICK_KP", { code: ERR.GUARD, message: "未知节点 kind（S5-3 fail-closed）" });
      }
      if (type === "edgeClick") return this.dispatch("CLICK_EDGE", { edge_id: event.edge_id });
      if (type === "backgroundClick") return this.dispatch("CLICK_BACKGROUND", {});
      if (type === "focus") return this.dispatch("FOCUS_NODE", { node_id: event.node_id });
      // hover 不改导航（S5-3/S5-10）
      if (type === "hover") return { ok: true, state: this.state, ignored: "hover", frameId: this.getFrameId() };
      return this._fail(type || "UNKNOWN", { code: ERR.ILLEGAL, message: `未知识别事件 ${type}` });
    }

    // ── 主入口：dispatch(state,event) 查表 → handler ─────────────────────
    dispatch(eventName, payload = {}) {
      if (!EVENTS.includes(eventName)) {
        return this._fail(eventName, { code: ERR.ILLEGAL, message: `未知事件 ${eventName}` });
      }
      const row = expandTransitions().find((r) => r.from === this.state && r.event === eventName);
      if (!row) {
        return this._fail(eventName, {
          code: ERR.ILLEGAL,
          message: `非法转移 (${this.state}, ${eventName})（S5 fail-closed）`,
        });
      }
      const handler = this[`_on_${eventName}`];
      if (typeof handler !== "function") {
        return this._fail(eventName, { code: ERR.INTERNAL, message: `缺少 handler：${eventName}` });
      }
      const result = handler.call(this, payload, row);
      if (result && result.ok === false) {
        this.lastError = result.error || { code: result.code || ERR.GUARD, message: result.message || "" };
        this._emit("error", { event: eventName, ...this.lastError });
        return { ...result, state: this.state, frameId: this.getFrameId(), error: this.lastError };
      }
      this.lastError = null;
      const out = {
        ok: true,
        event: eventName,
        previousState: result && result.previousState,
        state: this.state,
        mode: this.mode,
        dataState: this.dataState,
        frameId: this.getFrameId(),
        frameSpec: this.getFrameSpec(),
        ...(result && result.extra ? result.extra : {}),
      };
      this._emit("transition", out);
      return out;
    }

    _fail(eventName, error) {
      return {
        ok: false,
        event: eventName,
        state: this.state,
        frameId: this.getFrameId(),
        error: { code: error.code || ERR.GUARD, message: error.message || "" },
      };
    }

    // ── 事务化：clone → build next → 请求 S4 → 成功才 commit；失败 diff=0 ───
    _transact(buildNext, { previousState, initialFailureToDegraded = false } = {}) {
      const before = this.snapshot();
      let next;
      try {
        next = buildNext();
        if (!next || !next.frame) throw Object.assign(new Error("事务未构造 frame"), { code: ERR.INTERNAL });
        const spec = this._specOf(next.frame);
        this._assertSpec(spec);
        const admitted = this.requestAdmission(clone(spec));
        if (admitted && admitted.ok === false) {
          throw Object.assign(new Error(admitted.message || "S4 admission failed"), {
            code: admitted.code || "GRAPH_BUDGET_INVALID",
          });
        }
      } catch (err) {
        this._restore(before);
        if (initialFailureToDegraded && this.state === "Loading") this.state = "Degraded";
        return {
          ok: false,
          error: { code: err.code || ERR.INTERNAL, message: String(err.message || err) },
          diffSha: this.snapshotSha() === Canonical.canonicalSha(before) ? "0" : "nonzero",
        };
      }
      this._commit(next);
      if (previousState !== undefined) {
        return { ok: true, previousState };
      }
      return { ok: true };
    }

    _commit(next) {
      if (next.state !== undefined) this.state = next.state;
      if (next.frame !== undefined) this.frame = next.frame;
      if (next.stack !== undefined) this.stack = next.stack;
      if (next.history !== undefined) this.history = next.history;
      if (next.selection !== undefined) this.selection = next.selection;
      if (next.uiFocus !== undefined) this.uiFocus = next.uiFocus;
      if (next.originState !== undefined) this.originState = next.originState;
      if (next.dataState !== undefined) this.dataState = next.dataState;
      if (next.mode !== undefined) this.mode = next.mode;
      if (this.frame) {
        this.frame.mode = this.mode;
        this.frame.frame_id = this.getFrameId();
        this.frame.edition = this.editionSha;
        this.frame.history = this.history.map((h) => h.frame_id);
      }
    }

    _restore(snapshot) {
      this.state = snapshot.state;
      this.mode = snapshot.mode;
      this.dataState = snapshot.dataState;
      this.frame = clone(snapshot.frame);
      this.stack = clone(snapshot.stack);
      this.history = clone(snapshot.history);
      this.selection = clone(snapshot.selection);
      this.uiFocus = snapshot.uiFocus;
      this.originState = snapshot.originState;
    }

    _specOf(frame) {
      return {
        level: frame.level,
        view_family: frame.view_family,
        dimension_id: frame.dimension,
        focus: frame.focus,
        hop: frame.hop,
        new_hop: !!frame.new_hop,
        mode: frame.mode || this.mode,
        budget: { ...(frame.budget || this.budget) },
      };
    }

    _assertSpec(spec) {
      if (!spec || typeof spec !== "object") throw Object.assign(new Error("frame_spec 缺失"), { code: ERR.FRAME_ID });
      const keys = Object.keys(spec);
      const missing = FRAME_SPEC_FIELDS.filter((k) => !(k in spec));
      const extra = keys.filter((k) => !FRAME_SPEC_FIELDS.includes(k));
      if (missing.length || extra.length) {
        throw Object.assign(new Error(`frame_spec 字段非法 missing=${missing} extra=${extra}`), { code: ERR.FRAME_ID });
      }
      for (const forbidden of FRAME_SPEC_FORBIDDEN) {
        if (forbidden in spec) throw Object.assign(new Error(`frame_spec 含禁入字段 ${forbidden}`), { code: ERR.FRAME_ID });
      }
      if (!spec.focus) throw Object.assign(new Error("frame_spec.focus 为空"), { code: ERR.FRAME_ID });
    }

    _newFrame(partial = {}) {
      const base = this.frame || {
        focus: this.root.focus,
        level: this.root.level,
        view_family: this.root.view_family,
        dimension: this.root.dimension_id,
        hop: 1,
        new_hop: false,
        mode: this.mode,
        budget: { ...this.budget },
        origin: null,
        edition: this.editionSha,
        history: [],
      };
      const frame = {
        focus: base.focus,
        level: base.level,
        view_family: base.view_family,
        dimension: base.dimension,
        hop: base.hop,
        new_hop: base.new_hop,
        mode: this.mode,
        budget: { ...(base.budget || this.budget) },
        origin: base.origin || null,
        edition: this.editionSha,
        history: [],
        ...clone(partial),
      };
      frame.mode = partial.mode || this.mode;
      frame.frame_id = Canonical.canonicalSha(this._specOf(frame));
      return frame;
    }

    _pushCurrent(stack, frame = this.frame) {
      if (!frame) return stack.slice();
      const key = `${frame.focus}|${frame.level}|${frame.dimension}|${frame.mode}`;
      const exists = stack.some((e) => {
        const ref = e.canonical_frame_ref;
        return `${ref.focus}|${ref.level}|${ref.dimension_id}|${ref.mode}` === key;
      });
      if (exists) return stack.slice();
      const entry = {
        frame_id: Canonical.canonicalSha(this._specOf(frame)),
        // S6-7 NAV_STACK_ENTRY.canonical_frame_ref = S4_FRAME_SPEC（8 字段）
        canonical_frame_ref: clone(this._specOf(frame)),
        ts: this.now(),
      };
      const next = stack.concat([entry]);
      if (next.length > this.maxStack) throw Object.assign(new Error("导航栈溢出"), { code: ERR.STACK_OVERFLOW });
      return next;
    }

    _recordHistory(nextFrame) {
      const entry = { frame_id: nextFrame.frame_id, canonical_frame_ref: clone(this._specOf(nextFrame)) };
      return this.history.concat([entry]);
    }

    _applySpecToFrame(spec) {
      return this._newFrame({
        focus: spec.focus,
        level: spec.level,
        view_family: spec.view_family,
        dimension: spec.dimension_id,
        hop: spec.hop,
        new_hop: !!spec.new_hop,
        mode: spec.mode,
        budget: { ...spec.budget },
      });
    }

    // ── T01–T30 handlers ────────────────────────────────────────────────
    _on_OPEN_GRAPH(payload) {
      if (this.state !== "Idle") return { ok: false, code: ERR.ILLEGAL, message: "OPEN_GRAPH 只允许 Idle" };
      // T01 guard: backend_ready
      if (payload && payload.backendReady === false) {
        return { ok: false, code: ERR.GUARD, message: "backend 未就绪" };
      }
      const previous = this.state;
      this.state = "Loading";
      this._emit("nav", { event: "OPEN_GRAPH", state: this.state });
      return { ok: true, previousState: previous };
    }

    _on_DATA_READY(payload = {}) {
      const edition = payload.editionSha ?? payload.edition ?? this.editionSha;
      if (edition && this.editionSha && edition !== this.editionSha) {
        return { ok: false, code: ERR.GUARD, message: "edition 不匹配（T02 edition_match）" };
      }
      if (edition) this.editionSha = edition;
      const dataState = DATA_STATES.includes(payload.data_state) ? payload.data_state : "ok";
      const mode = MODES.includes(payload.mode) ? payload.mode : this.mode;
      const previous = this.state;
      this.mode = mode;
      this.frame = this._newFrame({ mode, hop: 1, new_hop: false });
      this.stack = [];
      this.history = [];
      this.selection = null;
      this.uiFocus = null;
      this.originState = null;
      this.dataState = dataState;
      this.state = "Overview";
      this.frame.frame_id = this.getFrameId();
      this.frame.history = [];
      this._emit("nav", { event: "DATA_READY", state: this.state, frameId: this.frame.frame_id });
      return { ok: true, previousState: previous };
    }

    _on_DATA_FAILED(payload = {}) {
      if (payload.retryable === false) return { ok: false, code: ERR.GUARD, message: "不可重试的数据失败" };
      const previous = this.state;
      this.state = "Degraded";
      this._emit("nav", { event: "DATA_FAILED", state: this.state });
      return { ok: true, previousState: previous };
    }

    _on_RETRY(payload = {}) {
      if (payload.retryable === false) return { ok: false, code: ERR.GUARD, message: "不可重试" };
      const previous = this.state;
      this.state = "Loading";
      this._emit("nav", { event: "RETRY", state: this.state });
      return { ok: true, previousState: previous };
    }

    _on_CLOSE() {
      const previous = this.state;
      if (this.state === "Idle") return { ok: true, state: "Idle", previousState: previous };
      this.state = "Idle";
      this.frame = null;
      this.stack = [];
      this.history = [];
      this.selection = null;
      this.uiFocus = null;
      this.originState = null;
      this.dataState = "ok";
      this._emit("nav", { event: "CLOSE", state: this.state });
      return { ok: true, previousState: previous };
    }

    _on_RELOAD() {
      const previous = this.state;
      this._rebuildLevel0();
      this.state = "Loading";
      this._emit("nav", { event: "RELOAD", state: this.state });
      return { ok: true, previousState: previous };
    }

    _rebuildLevel0() {
      this.frame = this._newFrame({
        focus: this.root.focus,
        level: this.root.level,
        view_family: this.root.view_family,
        dimension: this.root.dimension_id,
        hop: 1,
        new_hop: false,
        mode: this.mode,
        budget: { ...this.budget },
      });
      this.stack = [];
      this.history = [];
      this.selection = null;
      this.uiFocus = null;
      this.originState = null;
      this.frame.frame_id = this.getFrameId();
    }

    _on_DATA_REFRESHED(payload = {}) {
      const edition = payload.editionSha ?? payload.edition;
      if (edition && this.editionSha && edition !== this.editionSha) {
        return { ok: false, code: ERR.GUARD, message: "edition 不匹配（DATA_REFRESHED guard）" };
      }
      const dataState = DATA_STATES.includes(payload.data_state) ? payload.data_state : this.dataState;
      this.dataState = dataState;
      this._emit("nav", { event: "DATA_REFRESHED", state: this.state, dataState });
      return { ok: true, previousState: this.state };
    }

    _on_FOCUS_NODE(payload = {}) {
      if (!payload.node_id) return { ok: false, code: ERR.GUARD, message: "FOCUS_NODE 缺 node_id" };
      if (payload.focusable === false) return { ok: false, code: ERR.GUARD, message: "节点不可聚焦" };
      return this._transact(() => ({
        state: "Focused",
        frame: this._newFrame({ mode: this.mode, hop: this.frame ? this.frame.hop : 1, new_hop: this.frame ? this.frame.new_hop : false }),
        originState: this.state,
        uiFocus: String(payload.node_id),
      }), { previousState: this.state });
    }

    _on_CLICK_KP(payload = {}) {
      // S5-3：kp → 跳编辑器；frame/stack 不变；点击事件由渲染器发出
      if (payload.kind !== "kp" || !payload.file) {
        return { ok: false, code: ERR.GUARD, message: "CLICK_KP 需要 kind=kp 且 file" };
      }
      this._emit("editorJump", { node_id: String(payload.node_id || ""), file: payload.file });
      return { ok: true, previousState: this.state };
    }

    _on_CLICK_EDGE(payload = {}) {
      if (!payload.edge_id) return { ok: false, code: ERR.GUARD, message: "CLICK_EDGE 缺 edge_id" };
      this.selection = { kind: "edge", edge_id: String(payload.edge_id) };
      this._emit("selection", this.selection);
      return { ok: true, previousState: this.state };
    }

    _on_CLICK_BACKGROUND() {
      if (this.state === "Focused") {
        const target = this.originState || deriveStateForFrame(this.frame);
        this.selection = null;
        this.uiFocus = null;
        this.originState = null;
        const previous = this.state;
        // 回 origin：frame 不变（Focused 不改 frame.focus）；状态恢复即可
        this.state = DISPLAY_STATES.includes(target) ? target : "Overview";
        this._emit("nav", { event: "CLICK_BACKGROUND", state: this.state });
        return { ok: true, previousState: previous };
      }
      this.selection = null;
      this._emit("nav", { event: "CLICK_BACKGROUND", state: this.state });
      return { ok: true, previousState: this.state };
    }

    _on_CLICK_CLUSTER(payload = {}) {
      if (payload.kind !== "cluster" || !payload.node_id) {
        return { ok: false, code: ERR.GUARD, message: "CLICK_CLUSTER 需要 kind=cluster 与 node_id" };
      }
      if (payload.expandable === false) return { ok: false, code: ERR.GUARD, message: "簇不可展开" };
      const targetState = this._drillTargetState(payload);
      return this._transact(() => {
        const stack = this._pushCurrent(this.stack);
        const level = payload.level || this._incrementLevel(this.frame ? this.frame.level : this.root.level);
        const viewFamily = payload.view_family || (this.frame ? this.frame.view_family : this.root.view_family);
        const frame = this._newFrame({
          focus: String(payload.node_id),
          level,
          view_family: viewFamily,
          dimension: this.frame ? this.frame.dimension : this.root.dimension_id,
          hop: 1,
          new_hop: false,
          mode: this.mode,
          origin: null,
        });
        return { state: targetState, frame, stack, selection: null, uiFocus: null, originState: null };
      }, { previousState: this.state });
    }

    _incrementLevel(level) {
      const m = /^L(\d+)$/.exec(String(level || "L0"));
      return m ? `L${Number(m[1]) + 1}` : `${level}-child`;
    }

    _drillTargetState(payload) {
      if (payload.target_state && ["HierarchyDrilled", "RelationExpanded"].includes(payload.target_state)) {
        return payload.target_state;
      }
      if (this.state === "RelationDeepened" || this.state === "RelationExpanded") return "RelationExpanded";
      return "HierarchyDrilled";
    }

    _on_FOCUS_LOST(payload = {}) {
      // 事务化：恢复最近祖先（栈顶）或 root；失败 diff=0
      const targetState = this._ancestorState();
      return this._transact(() => {
        let frame;
        let stack = this.stack.slice();
        if (stack.length) {
          const top = stack[stack.length - 1];
          frame = this._applySpecToFrame(top.canonical_frame_ref);
          stack = stack.slice(0, -1);
        } else {
          frame = this._newFrame({
            focus: this.root.focus, level: this.root.level, view_family: this.root.view_family,
            dimension: this.root.dimension_id, hop: 1, new_hop: false, mode: this.mode,
          });
        }
        return { state: targetState, frame, stack, selection: null, uiFocus: null, originState: null };
      }, { previousState: this.state });
    }

    _ancestorState() {
      if (this.stack.length) {
        const top = this.stack[this.stack.length - 1];
        const ref = top.canonical_frame_ref;
        const frame = { ...ref, dimension: ref.dimension_id, hop: ref.hop, new_hop: ref.new_hop };
        return deriveStateForFrame(frame);
      }
      return "Overview";
    }

    _on_FOCUS_CLEAR() {
      if (this.state !== "Focused") return { ok: false, code: ERR.ILLEGAL, message: "FOCUS_CLEAR 只允许 Focused" };
      const target = this.originState || deriveStateForFrame(this.frame);
      const previous = this.state;
      this.state = DISPLAY_STATES.includes(target) ? target : "Overview";
      this.selection = null;
      this.uiFocus = null;
      this.originState = null;
      this._emit("nav", { event: "FOCUS_CLEAR", state: this.state });
      return { ok: true, previousState: previous };
    }

    _on_BACK(payload = {}) {
      if (this.state === "Overview") {
        // T22：栈空 no-op
        if (this.stack.length === 0) {
          this._emit("nav", { event: "BACK", state: this.state, announce: "root" });
          return { ok: true, previousState: this.state };
        }
      }
      if (this.state === "Focused") {
        const target = this.originState || deriveStateForFrame(this.frame);
        const previous = this.state;
        this.state = DISPLAY_STATES.includes(target) ? target : "Overview";
        this.uiFocus = null;
        this.selection = null;
        this.originState = null;
        this._emit("nav", { event: "BACK", state: this.state });
        return { ok: true, previousState: previous };
      }
      if (!this.stack.length) {
        return { ok: false, code: ERR.STACK_EMPTY, message: "导航栈为空（BACK guard）" };
      }
      const targetState = this._ancestorState();
      return this._transact(() => {
        const stack = this.stack.slice(0, -1);
        const top = this.stack[this.stack.length - 1];
        const frame = this._applySpecToFrame(top.canonical_frame_ref);
        return { state: targetState, frame, stack, selection: null, uiFocus: null, originState: null };
      }, { previousState: this.state });
    }

    _on_BREADCRUMB_TO(payload = {}) {
      const targetId = payload.frame_id || payload.target_frame_id;
      const index = Number.isInteger(payload.index) ? payload.index : this.stack.findIndex((e) => e.frame_id === targetId);
      if (index < 0 || index >= this.stack.length) {
        return { ok: false, code: ERR.GUARD, message: "BREADCRUMB_TO 目标不在栈内" };
      }
      const targetState = (() => {
        const ref = this.stack[index].canonical_frame_ref;
        return deriveStateForFrame({ ...ref, dimension: ref.dimension_id, hop: ref.hop, new_hop: ref.new_hop });
      })();
      return this._transact(() => {
        const stack = this.stack.slice(0, index);
        const frame = this._applySpecToFrame(this.stack[index].canonical_frame_ref);
        return { state: targetState, frame, stack, selection: null, uiFocus: null, originState: null };
      }, { previousState: this.state });
    }

    _on_SELECT_DIMENSION(payload = {}) {
      const dim = payload.dimension_id;
      if (!this.activeDimensions.includes(dim)) {
        return { ok: false, code: ERR.GUARD, message: `维度未激活：${dim}` };
      }
      const targetState = dim === "H" ? "HierarchyDrilled" : "RelationExpanded";
      return this._transact(() => {
        const stack = this._pushCurrent(this.stack);
        const frame = this._newFrame({
          focus: payload.focus || (this.frame ? this.frame.focus : this.root.focus),
          level: this.frame ? this.frame.level : this.root.level,
          view_family: payload.view_family || (this.frame ? this.frame.view_family : this.root.view_family),
          dimension: dim,
          hop: 1,
          new_hop: false,
          mode: this.mode,
        });
        return { state: targetState, frame, stack, selection: null, uiFocus: null, originState: null };
      }, { previousState: this.state });
    }

    _on_EXPLICIT_NEW_HOP() {
      const frame = this.frame;
      if (!frame) return { ok: false, code: ERR.GUARD, message: "无 focus frame" };
      if (this.state === "RelationDeepened" && frame.hop === 2) {
        // T26：幂等 no-op
        this._emit("nav", { event: "EXPLICIT_NEW_HOP", state: this.state, idempotent: true });
        return { ok: true, previousState: this.state };
      }
      if (this.state !== "RelationExpanded" || frame.dimension !== "A" || frame.hop !== 1 || !frame.focus) {
        return { ok: false, code: ERR.GUARD, message: "EXPLICIT_NEW_HOP 仅 A 维/focus/hop=1" };
      }
      return this._transact(() => {
        const stack = this._pushCurrent(this.stack);
        const next = this._newFrame({ ...this._specFromFrame(frame), hop: 2, new_hop: true, mode: this.mode });
        next.dimension = frame.dimension;
        return { state: "RelationDeepened", frame: next, stack, selection: null };
      }, { previousState: this.state });
    }

    _specFromFrame(frame) {
      return {
        focus: frame.focus,
        level: frame.level,
        view_family: frame.view_family,
        dimension: frame.dimension,
        hop: frame.hop,
        new_hop: frame.new_hop,
        budget: { ...(frame.budget || this.budget) },
      };
    }

    _on_TOGGLE_EXPAND(payload = {}) {
      if (payload.candidateSuperset === false || payload.candidate_superset === false) {
        return { ok: false, code: ERR.GUARD, message: "candidate_superset 不成立（T27 guard）" };
      }
      const nextMode = this.mode === "default" ? "full" : "default";
      return this._transact(() => {
        const frame = this._newFrame({ mode: nextMode, hop: this.frame ? this.frame.hop : 1, new_hop: this.frame ? this.frame.new_hop : false });
        return {
          state: this.state, mode: nextMode, frame,
          stack: this.stack, selection: this.selection,
        };
      }, { previousState: this.state });
    }

    _on_CORPUS_CHANGED(payload = {}) {
      const edition = payload.editionSha ?? payload.edition;
      if (!edition || edition === this.editionSha) {
        return { ok: false, code: ERR.GUARD, message: "CORPUS_CHANGED 需要 edition 不匹配" };
      }
      const previous = this.state;
      this.editionSha = edition;
      this.state = "Stale";
      this._emit("nav", { event: "CORPUS_CHANGED", state: this.state });
      return { ok: true, previousState: previous };
    }

    _on_RESET() {
      const previous = this.state;
      this._rebuildLevel0();
      this.state = "Loading";
      this._emit("nav", { event: "RESET", state: this.state });
      return { ok: true, previousState: previous };
    }
  }

  const api = {
    NavController,
    MAIN_STATES,
    DISPLAY_STATES,
    MODES,
    DATA_STATES,
    EVENTS,
    MAX_STACK,
    DEFAULT_BUDGET,
    FRAME_SPEC_FIELDS,
    FRAME_SPEC_FORBIDDEN,
    TRANSITION_ROWS,
    ERR,
    expandTransitions,
    expandFrom,
    deriveStateForFrame,
    canonical: Canonical,
  };
  global.MemoriaGraphNavController = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
