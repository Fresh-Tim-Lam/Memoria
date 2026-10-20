/**
 * NewSurface —— 显示子系统插头「new」的**占位实现**（阶段 2 P1，2026-10-20）
 *
 * 契约：docs/design/view-surface-contract.md §3/§4
 *
 * ── 这个文件是什么 ──────────────────────────────────────────────────────
 *   它是 `new` 插头的**唯一注册点**，但此刻**故意不实现**：
 *   契约 §3.1 的每个方法都**明确抛 NotImplemented**，**绝不**返回空 DOM / 静默 no-op
 *   去伪装"能用"。理由：伪装可用的插头会让 C11（新旧等价）/ C12（无损切换）**假绿**——
 *   那比"未实现"危险得多。
 *
 * ── 它的真实用途（现在就有的价值）──────────────────────────────────────
 *   1. 让 `SurfaceRegistry.list()` 能同时看到 `['legacy', 'new']`（双插头注册面成型）；
 *   2. 让 `switchTo('new')` 走**真实的失败路径** ⇒ 验证 registry §4.4 的
 *      「失败回滚到老插头 + onDegraded('switch-failed')」**真的生效**（C12 的证据之一）；
 *   3. 阶段 2 后续片（RenderCore / EditSurface）直接在此文件填充，注册面不用再动。
 *
 * ── 探针合成插头（不在这里）─────────────────────────────────────────────
 *   C11/C12 的"自证会红"用的 `__broken` / `__lossy` 是**探针专用**合成插头，
 *   由 cdp.mjs 在探针模式注入，**不进生产路径**（见 run_probe.py C11/C12 实现）。
 */
window.createNewSurface = function createNewSurface(deps) {
  "use strict";
  var _name = "new";

  /** 统一的"未实现"错误：带插头名 + 方法名 + 契约指针，便于日志定位。 */
  function _notImplemented(method) {
    var err = new Error("[NewSurface] 未实现：" + method + "()");
    err.code = "NOT_IMPLEMENTED";
    err.surface = _name;
    err.method = method;
    err.reason = "阶段 2 P1 只立注册面；NewSurface 的渲染/编辑实现留给后续片（RenderCore / EditSurface）。";
    err.contract = "docs/design/view-surface-contract.md §3.1";
    return err;
  }

  // 契约 §3.1 全部方法：一律抛，不返回假值。
  var api = {
    /** 插头标识（诊断用）。 */
    name: _name,

    /** 契约 §4.3：能力声明 —— 未实现 ⇒ 全 false（诚实声明，不虚报）。 */
    capabilities: {
      supportsEdit: false,
      supportsViewport: false,
      supportsStableBlockId: false,
      findInPage: "unsupported",
      implemented: false,
    },

    mount: function () { throw _notImplemented("mount"); },
    setText: function () { throw _notImplemented("setText"); },
    setMode: function () { throw _notImplemented("setMode"); },
    applyEdit: function () { throw _notImplemented("applyEdit"); },
    undo: function () { throw _notImplemented("undo"); },
    redo: function () { throw _notImplemented("redo"); },
    revealRange: function () { throw _notImplemented("revealRange"); },
    getScrollAnchor: function () { throw _notImplemented("getScrollAnchor"); },
    setScrollAnchor: function () { throw _notImplemented("setScrollAnchor"); },
    getSrcRangeForSelection: function () { throw _notImplemented("getSrcRangeForSelection"); },
    isBlockFrozen: function () { throw _notImplemented("isBlockFrozen"); },
    destroy: function () { throw _notImplemented("destroy"); },
    flush: function () { throw _notImplemented("flush"); },
  };

  return api;
};

/**
 * 自注册（不依赖 app.js 的装配块 —— P1 写域不含 app.js）。
 * 加载顺序：index.html 里 registry.js → legacy-surface.js → new-surface.js → app.js，
 * 故此处 MemoriaSurface 已就绪；app.js 末尾的装配块随后会注册 legacy 并 switchTo('legacy')，
 * 两者互不干扰 ⇒ list() 最终为 ['legacy', 'new']。
 * 若 MemoriaSurface 缺失（单测/非常规加载）⇒ 不抛，留待宿主显式注册。
 */
(function selfRegister() {
  "use strict";
  try {
    var S = (typeof window !== "undefined") ? window.MemoriaSurface : null;
    if (S && typeof S.register === "function") {
      S.register("new", function (deps) { return window.createNewSurface(deps); });
    }
  } catch (e) { /* 注册失败不得影响页面加载（插头缺省时 legacy 照常工作） */ }
})();
