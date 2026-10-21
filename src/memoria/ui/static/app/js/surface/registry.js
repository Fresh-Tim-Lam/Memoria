/**
 * MemoriaSurface —— 显示子系统插口（Surface registry / 双插头协议）
 *
 * 契约：docs/design/view-surface-contract.md
 *   §4.1 注册与切换（register / current / switchTo）
 *   §4.2 交接（flush → destroy → mount+setText+setMode+setScrollAnchor → 恢复光标；任一步失败回滚）
 *   §4.3 能力声明（capabilities，由插头自己声明）
 *   §4.4 失败与回退（失败 ⇒ 回滚到老插头 + onDegraded('switch-failed')）
 *
 * 本文件只立「插口」：注册表 + 切换协议 + 宿主回调装配位。
 * **不迁移**任何既有调用路径（app.js 现有调用照旧；改走插口是 NewSurface 能跑之后的事）。
 *
 * 对外：window.MemoriaSurface = { registry, host, register, current, list, switchTo }
 *       window.SurfaceRegistry = registry（契约 §4.1 的命名）
 */
(function () {
  "use strict";

  // ── 注册表：name -> factory ────────────────────────────────────────────────
  var _factories = Object.create(null);
  var _order = [];              // 注册顺序（list() 用）

  var _current = null;         // 当前插头名
  var _instance = null;        // 当前插头实例
  var _chain = Promise.resolve();  // 切换串行链 ⇒ 可重入安全（同一时刻只跑一次切换）
  var _warnedUnknown = {};         // 未注册插头名 → 已 warn（每个名字只 warn 一次）

  // ── 宿主回调集（契约 §3.2）：装配位，宿主可覆盖任一 ──────────────────────────
  var host = {
    onTextChange: function () {},
    onCursorChange: function () {},
    onLinkActivate: function () {},
    onRevealRequest: function () {},
    onMeasure: function () {},
    onDegraded: function (reason) {
      try { console.warn("[MemoriaSurface] degraded:", reason); } catch (e) { /* noop */ }
    },
  };

  function _has(name) { return Object.prototype.hasOwnProperty.call(_factories, name); }

  function register(name, factory) {
    if (typeof name !== "string" || !name) throw new Error("MemoriaSurface.register(name, factory): name 必须是非空字符串");
    if (typeof factory !== "function") throw new Error("MemoriaSurface.register(name, factory): factory 必须是函数");
    if (!_has(name)) _order.push(name);
    _factories[name] = factory;
    return registry;
  }

  function current() { return _current; }
  function list() { return _order.slice(); }

  function _resolveContainer(ctx) {
    if (ctx && ctx.container) return ctx.container;
    return document.getElementById("editor-split") || document.getElementById("preview") || null;
  }

  /**
   * §4.2 step1：老插头 flush() → 交接包 { text, cursor, anchor, mode, frozen }。
   * flush() 直接返回该包；缺项时按 ctx / 老插头查询兜底。
   */
  function _captureHandoff(old, ctx) {
    var bundle = null;
    if (old && typeof old.flush === "function") {
      try { bundle = old.flush(); } catch (e) { bundle = null; }
    }
    var b = (bundle && typeof bundle === "object") ? bundle : {};
    var st = window.state;
    var text = (b.text != null) ? b.text
      : (ctx && typeof ctx.getText === "function") ? ctx.getText()
        : (st && st.doc ? st.doc.body : null);
    var anchor = (b.anchor != null) ? b.anchor
      : (old && typeof old.getScrollAnchor === "function") ? old.getScrollAnchor()
        : null;
    var mode = (b.mode != null) ? b.mode
      : (ctx && ctx.mode != null) ? ctx.mode
        : (st ? st.viewMode : null);
    return {
      text: text,
      cursor: (b.cursor != null) ? b.cursor : null,
      anchor: anchor,
      mode: mode,
      frozen: (b.frozen != null) ? b.frozen : null,
    };
  }

  function _doSwitch(name, ctx) {
    // 同一插头切到自身 ⇒ 安全空操作（本刀只有 legacy 一个插头，这条必经）
    if (name === _current && _instance) return Promise.resolve(_current);

    if (!_has(name)) {
      // §4.4：未注册 = 失败。P6c 起 legacy 已删除 ⇒ switchTo('legacy') 落到这里：
      //   ① onDegraded('unknown-surface') 显式上报；② 保持当前插头不变；③ console.warn（每名一次）；
      //   ④ 把 rejection 抛给调用方 —— 任何一条都不允许"静默成功"。
      if (!_warnedUnknown[name]) {
        _warnedUnknown[name] = true;
        try {
          console.warn("[MemoriaSurface] switchTo('" + name + "'): 未注册的插头（P6c 起 legacy 已删除），保持当前插头 '" + (_current || "null") + "'");
        } catch (e) { /* noop */ }
      }
      host.onDegraded("unknown-surface");
      return Promise.reject(new Error("MemoriaSurface.switchTo: 未注册的插头 '" + name + "'"));
    }

    var oldName = _current;
    var old = _instance;
    var handoff = null;
    var next = null;
    var container = _resolveContainer(ctx);

    try {
      // ① 老插头 flush() → 交接包
      if (old) handoff = _captureHandoff(old, ctx);

      // ② 老插头 destroy()
      if (old && typeof old.destroy === "function") old.destroy();

      // ③ 新插头 mount()（+ 有交接包时 setText / setMode / setScrollAnchor）
      next = _factories[name]({ container: container, host: host, ctx: ctx });
      if (!next || typeof next.mount !== "function") throw new Error("插头工厂未返回合法插头: " + name);
      next.mount(container, host);

      // 首次挂载（old == null）：采用宿主现存状态，**不**重放 setText/setMode/setScrollAnchor
      // —— 否则会在加载期把应用刷回顶部 / 触发重渲（本刀硬验收：适配后行为与适配前逐项一致）
      if (handoff) {
        if (handoff.text != null && typeof next.setText === "function") next.setText(handoff.text, "switch");
        if (handoff.mode != null && typeof next.setMode === "function") next.setMode(handoff.mode);
        if (handoff.anchor != null && typeof next.setScrollAnchor === "function") next.setScrollAnchor(handoff.anchor);
        // ④ 恢复光标。契约 §3.1 未定义 setCursor，最近的入口是 revealRange（不滚动、不闪）
        if (handoff.cursor && typeof next.revealRange === "function") {
          var c = handoff.cursor;
          next.revealRange(c.startLine, c.endLine, { scroll: false, flash: false });
        }
      }

      _current = name;
      _instance = next;
      return Promise.resolve(name);
    } catch (e) {
      // ⑤ 任一步失败 ⇒ 回滚到老插头 + onDegraded('switch-failed')
      try {
        if (old && typeof old.mount === "function") {
          old.mount(container, host);
          if (handoff) {
            if (handoff.text != null && typeof old.setText === "function") old.setText(handoff.text, "switch");
            if (handoff.mode != null && typeof old.setMode === "function") old.setMode(handoff.mode);
            if (handoff.anchor != null && typeof old.setScrollAnchor === "function") old.setScrollAnchor(handoff.anchor);
          }
          _current = oldName;
          _instance = old;
        } else {
          _current = null;
          _instance = null;
        }
      } catch (e2) { /* 回滚尽力而为，不再抛 */ }
      host.onDegraded("switch-failed");
      return Promise.reject(e);
    }
  }

  function switchTo(name, ctx) {
    // 串行化：切换排队依次执行 ⇒ 幂等、可重入安全（同一插头自切由 _doSwitch 首行短路）
    var run = function () { return _doSwitch(name, ctx); };
    _chain = _chain.then(run, run);
    return _chain;
  }

  /**
   * 逐出注册（**仅探针用**，2026-10-20 阶段 2 P1）。
   * 用途：C11/C12 探针临时注册合成插头（`__broken` / `__lossy`）后必须清理，
   * 否则会残留在注册表里污染后续用例。
   *
   * 安全约束：
   *   · 只允许逐出 **以 `__` 开头的名字**（生产插头 legacy/new 不可逐出）；
   *   · 若被逐出的是**当前插头** ⇒ 拒绝（避免 _current 指向已删工厂的死状态）。
   * @returns {boolean} 是否真的逐出
   */
  function evict(name) {
    if (typeof name !== "string" || name.indexOf("__") !== 0) {
      throw new Error("SurfaceRegistry.evict: 只允许逐出探针插头（名字须以 __ 开头）: '" + name + "'");
    }
    if (name === _current) {
      throw new Error("SurfaceRegistry.evict: 不能逐出当前插头 '" + name + "'，请先 switchTo 别的插头");
    }
    if (!_has(name)) return false;
    delete _factories[name];
    var i = _order.indexOf(name);
    if (i >= 0) _order.splice(i, 1);
    return true;
  }

  var registry = {
    register: register,
    current: current,
    list: list,
    switchTo: switchTo,
    __evict: evict,   // 仅探针用（C11/C12 合成插头清理）
  };

  var MemoriaSurface = {
    registry: registry,
    host: host,
    // 顶层别名（契约 §4.1 的短写法；控制台便捷：MemoriaSurface.current() / switchTo()）
    register: register,
    current: current,
    list: list,
    switchTo: switchTo,
  };

  window.MemoriaSurface = MemoriaSurface;
  window.SurfaceRegistry = registry;   // 契约 §4.1 命名
})();
