/**
 * 无边框窗口：最小化 / 最大化 / 关闭、边缘缩放、最大化时拖拽顶栏还原
 */
(function (global) {
  "use strict";

  const EDGES = ["n", "s", "e", "w", "nw", "ne", "sw", "se"];
  const DRAG_THRESHOLD = 4;
  const TITLEBAR_Y_OFFSET = 17;

  let maximized = false;
  let frameless = false;
  let shellKind = "pywebview";
  let minSize = { w: 900, h: 600 };
  let resizeLayer = null;

  function api() {
    return global.MemoriaBridge && global.MemoriaBridge.api();
  }

  function setMaximizeIcon(btn, isMax) {
    if (!btn) return;
    btn.classList.toggle("is-restore", !!isMax);
    btn.title = isMax ? "还原" : "最大化";
    btn.setAttribute("aria-label", btn.title);
  }

  function onMaximizeStateChange(isMax, btnMax) {
    maximized = !!isMax;
    setMaximizeIcon(btnMax, maximized);
    setResizeLayerVisible(frameless && !maximized);
  }

  function setResizeLayerVisible(visible) {
    if (!resizeLayer) return;
    resizeLayer.classList.toggle("hidden", !visible);
  }

  function ensureResizeLayer() {
    if (resizeLayer) return resizeLayer;
    resizeLayer = document.createElement("div");
    resizeLayer.id = "window-resize-layer";
    resizeLayer.className = "m0-win-resize-layer hidden";
    resizeLayer.setAttribute("aria-hidden", "true");
    EDGES.forEach((edge) => {
      const el = document.createElement("div");
      el.className = `m0-win-resize-handle m0-win-resize-${edge}`;
      el.dataset.edge = edge;
      resizeLayer.appendChild(el);
    });
    document.body.appendChild(resizeLayer);
    return resizeLayer;
  }

  function bindResizeLayer(a) {
    const layer = ensureResizeLayer();
    // PyQt6 + Win32 用原生 WM_NCHITTEST 边缘缩放；JS RPC 每帧 resize 太慢
    if (shellKind === "pyqt6" && /Win/i.test(navigator.platform)) {
      layer.dataset.bound = "1";
      setResizeLayerVisible(false);
      return;
    }
    if (layer.dataset.bound === "1") {
      setResizeLayerVisible(frameless && !maximized);
      return;
    }
    layer.dataset.bound = "1";

    let dragging = null;

    const onMove = (e) => {
      if (!dragging) return;
      e.preventDefault();
      const dx = e.screenX - dragging.sx;
      const dy = e.screenY - dragging.sy;
      let w = dragging.w;
      let h = dragging.h;
      const edge = dragging.edge;
      if (edge.includes("e")) w += dx;
      if (edge.includes("w")) w -= dx;
      if (edge.includes("s")) h += dy;
      if (edge.includes("n")) h -= dy;
      w = Math.max(minSize.w, Math.round(w));
      h = Math.max(minSize.h, Math.round(h));
      a.window_resize_to?.(w, h, edge);
    };

    const onUp = () => {
      dragging = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.classList.remove("m0-win-resizing");
    };

    layer.querySelectorAll(".m0-win-resize-handle").forEach((handle) => {
      handle.addEventListener("mousedown", (e) => {
        if (maximized || e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        dragging = {
          edge: handle.dataset.edge,
          sx: e.screenX,
          sy: e.screenY,
          w: global.innerWidth,
          h: global.innerHeight,
        };
        document.body.classList.add("m0-win-resizing");
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });

    setResizeLayerVisible(frameless && !maximized);
  }

  const NO_DRAG_SELECTORS =
    "#btn-kb-close, .m0-kb-exit, .toolbar-search-wrap, .toolbar-actions, .m0-window-controls";

  function isNoDragTarget(target) {
    return target instanceof Element && !!target.closest(NO_DRAG_SELECTORS);
  }

  function syncToolbarDragExclusion() {
    if (shellKind !== "pyqt6") return;
    const bridge = global.__memoriaQtBridge;
    if (!bridge?.setToolbarDragExclusion) return;
    const right = document.querySelector(".toolbar-right");
    if (!right) return;
    const left = Math.round(right.getBoundingClientRect().left);
    if (Number.isFinite(left) && left > 0) {
      bridge.setToolbarDragExclusion(left);
    }
  }

  function bindToolbarDragExclusionSync() {
    if (shellKind !== "pyqt6") return;
    let timer = null;
    const schedule = () => {
      if (timer) return;
      timer = global.requestAnimationFrame(() => {
        timer = null;
        syncToolbarDragExclusion();
      });
    };
    global.addEventListener("resize", schedule);
    if (typeof ResizeObserver !== "undefined") {
      const toolbar = document.getElementById("toolbar");
      const kbWrap = document.getElementById("kb-indicator-wrap");
      const ro = new ResizeObserver(schedule);
      if (toolbar) ro.observe(toolbar);
      if (kbWrap) ro.observe(kbWrap);
    }
    schedule();
  }

  function bindTitlebarDrag(a) {
    document.querySelectorAll(".pywebview-drag-region").forEach((el) => {
      el.addEventListener(
        "mousedown",
        (e) => {
          if (isNoDragTarget(e.target)) return;
          if (e.button !== 0 || maximized) return;
          if (shellKind === "pyqt6") {
            e.preventDefault();
            e.stopPropagation();
            const bridge = global.__memoriaQtBridge;
            if (bridge?.startMove) {
              bridge.startMove();
            } else {
              a?.window_start_move?.();
            }
            return;
          }
          /* pywebview：依赖 CSS -webkit-app-region */
        },
        true
      );
    });
  }

  function bindMaximizedTitlebarDrag(a, btnMax) {
    let session = null;

    const onMove = async (e) => {
      if (!session) return;
      const dx = e.screenX - session.sx;
      const dy = e.screenY - session.sy;

      if (!session.restored) {
        if (Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
        try {
          const res = await a.window_restore_from_drag?.(
            e.screenX,
            e.screenY,
            session.ratioX
          );
          if (res?.status === "ok") {
            session.restored = true;
            session.w = res.width || session.w;
            onMaximizeStateChange(false, btnMax);
          }
        } catch (_) {
          /* ignore */
        }
        return;
      }

      const w = session.w || minSize.w;
      a.window_move_to?.(
        Math.round(e.screenX - session.ratioX * w),
        Math.round(e.screenY - TITLEBAR_Y_OFFSET)
      );
    };

    const onUp = () => {
      session = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };

    document.querySelectorAll(".pywebview-drag-region").forEach((el) => {
      el.addEventListener(
        "mousedown",
        (e) => {
          if (isNoDragTarget(e.target)) return;
          if (!maximized || e.button !== 0) return;
          e.preventDefault();
          e.stopImmediatePropagation();
          session = {
            sx: e.screenX,
            sy: e.screenY,
            ratioX: e.clientX / Math.max(global.innerWidth, 1),
            restored: false,
            w: null,
          };
          document.addEventListener("mousemove", onMove);
          document.addEventListener("mouseup", onUp);
        },
        true
      );
    });
  }

  async function initWindowChrome() {
    const wrap = document.getElementById("window-controls");
    if (!wrap) return;

    const a = api();
    if (!a?.get_window_chrome) {
      wrap.classList.add("hidden");
      return;
    }

    try {
      const res = await a.get_window_chrome();
      frameless = res?.status === "ok" && !!res.frameless;
      shellKind = res?.shell || "pywebview";
      maximized = !!res?.maximized;
      if (Number.isFinite(res?.min_width)) minSize.w = res.min_width;
      if (Number.isFinite(res?.min_height)) minSize.h = res.min_height;
    } catch (_) {
      frameless = false;
    }

    if (!frameless) {
      wrap.classList.add("hidden");
      return;
    }

    wrap.classList.remove("hidden");

    const btnMin = document.getElementById("btn-win-minimize");
    const btnMax = document.getElementById("btn-win-maximize");
    const btnClose = document.getElementById("btn-win-close");

    bindResizeLayer(a);
    bindTitlebarDrag(a);
    bindMaximizedTitlebarDrag(a, btnMax);
    bindToolbarDragExclusionSync();

    btnMin?.addEventListener("click", () => {
      a.window_minimize?.();
    });

    btnMax?.addEventListener("click", async () => {
      const res = await a.window_toggle_maximize?.();
      if (res?.status === "ok") {
        onMaximizeStateChange(!!res.maximized, btnMax);
      }
    });

    btnClose?.addEventListener("click", () => {
      a.window_close?.();
    });

    onMaximizeStateChange(maximized, btnMax);
  }

  global.MemoriaWindowChrome = {
    initWindowChrome,
    syncToolbarDragExclusion,
  };
})(typeof window !== "undefined" ? window : globalThis);
