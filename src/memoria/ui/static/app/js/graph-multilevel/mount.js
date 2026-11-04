/**
 * B4 / I-07 挂载与事件回传（2D 优先；3D 不可用 ⇒ 显式回退 2D，不阻断）。
 *
 * 设计边界（S3-6/S3-7/S3-11）：
 *   - Renderer 只接收 VM；本模块只做「容器挂载 + 渲染器事件 → NavController」的接线；
 *   - 不取数、不做 presence/裁剪（S4 唯一裁剪者）；
 *   - 3D capability=false 时**显式回退 2D**并给出 fallbackReason（S3-11 降级可见，不静默）；
 *   - legacy 入口（旧 KGviz 2D/3D）不在此模块替换；调用方需显式选择使用本挂载器。
 */
(function (global) {
  "use strict";

  const Adapter = global.MemoriaGraphRendererAdapter
    || (typeof require === "function" ? require("./renderer-adapter.js") : null);
  if (!Adapter) throw new Error("MemoriaGraphRendererAdapter 未加载");

  const RENDERER_EVENTS = ["nodeClick", "edgeClick", "backgroundClick", "hover"];

  /**
   * @param {object} options
   *   container, vm, nav（NavController 实例，可选）, backend="2d"|"3d",
   *   host（测试注入）, resolveFile(node_id)（Presentation 负责把 VM 节点 id 映射到文件）,
   *   legacyRenderer（旧 renderer 实例，可选；3D 回退目标）
   * @returns {{renderer, fellBack, fallbackReason, render, destroy, rendererCapabilities}}
   */
  function mountGraphView(options = {}) {
    const container = options.container;
    if (!container) throw new Error("mountGraphView 需要 container");
    const backend = options.backend || "2d";
    let fellBack = false;
    let fallbackReason = null;
    let renderer = Adapter.createRendererAdapter(backend, container, options);
    if (!renderer.getCapabilities().capable) {
      fallbackReason = renderer.getCapabilities().reason || "RENDERER_UNAVAILABLE";
      fellBack = true;
      // S3-11：WebGL/3D 不可用 ⇒ 显式回退 2D（可见提示由调用方用 fallbackReason 渲染）
      renderer = Adapter.createRendererAdapter("2d", container, options);
    }
    const nav = options.nav || null;
    const unsubscribers = [];
    for (const type of RENDERER_EVENTS) {
      unsubscribers.push(
        renderer.on(type, (payload) => {
          if (!nav || typeof nav.handleRendererEvent !== "function") return;
          const enriched = { type, ...payload };
          if (type === "nodeClick" && enriched.kind === "kp" && typeof options.resolveFile === "function") {
            const file = options.resolveFile(enriched.node_id);
            if (file) enriched.file = file;
          }
          nav.handleRendererEvent(enriched);
        })
      );
    }
    const api = {
      renderer,
      fellBack,
      fallbackReason,
      rendererCapabilities: renderer.getCapabilities(),
      render(vm) {
        return renderer.render(container, vm);
      },
      update(vm, opts) {
        return renderer.update(vm, opts);
      },
      destroy() {
        for (const off of unsubscribers) {
          try { off(); } catch (_) { /* noop */ }
        }
        unsubscribers.length = 0;
        return renderer.dispose();
      },
    };
    if (options.vm) api.render(options.vm);
    return api;
  }

  const api = { mountGraphView, RENDERER_EVENTS };
  global.MemoriaGraphMount = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
