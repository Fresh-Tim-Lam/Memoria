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

  const _t = (k) => (global.MemoriaI18n ? global.MemoriaI18n.t(k) : k);

  function api() {
    return global.MemoriaBridge && global.MemoriaBridge.api();
  }

  function setMaximizeIcon(btn, isMax) {
    if (!btn) return;
    btn.classList.toggle("is-restore", !!isMax);
    btn.title = isMax ? _t("win.restore") : _t("win.maximize");
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
    resizeLayer.className = "-win-resize-layer hidden";
    resizeLayer.setAttribute("aria-hidden", "true");
    EDGES.forEach((edge) => {
      const el = document.createElement("div");
      el.className = `-win-resize-handle -win-resize-${edge}`;
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
      document.body.classList.remove("-win-resizing");
    };

    layer.querySelectorAll(".-win-resize-handle").forEach((handle) => {
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
        document.body.classList.add("-win-resizing");
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });

    setResizeLayerVisible(frameless && !maximized);
  }

  const NO_DRAG_SELECTORS =
    "#btn-kb-close, .-kb-exit, .toolbar-search-wrap, .toolbar-actions, .-window-controls";

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
    if (shellKind === "pyqt6") {
      // PyQt6：沿用系统级拖动（Qt 原生 HTCAPTION）
      document.querySelectorAll(".pywebview-drag-region").forEach((el) => {
        el.addEventListener(
          "mousedown",
          (e) => {
            if (isNoDragTarget(e.target)) return;
            if (e.button !== 0 || maximized) return;
            e.preventDefault();
            e.stopPropagation();
            const bridge = global.__memoriaQtBridge;
            if (bridge?.startMove) {
              bridge.startMove();
            } else {
              a?.window_start_move?.();
            }
          },
          true
        );
      });
      return;
    }

    /* pywebview：WebView2 子窗口拦截 WM_NCHITTEST，命中测试到不了表单
       WndProc → 不采用 NCHITTEST。顶栏拖动由 bindNativeCaptionDrag 绑定
       mousedown → RPC window_begin_drag → 后端 PostMessage → WndProc
       （UI 线程）发起原生标题栏拖动，见 window_win32.py。 */
  }

  function bindNativeCaptionDrag(a) {
    // pywebview（WebView2）子窗口拦截 WM_NCHITTEST，命中测试无法到达表单
    // WndProc → 弃用 NCHITTEST 方案。改为：顶栏 mousedown → RPC
    // window_begin_drag → 后端 PostMessage → WndProc（UI 线程）执行
    // ReleaseCapture + SendMessage(WM_NCLBUTTONDOWN, HTCAPTION)，进入
    // 系统原生标题栏拖动循环（鼠标捕获 / Aero Snap 全部原生处理）。
    // 最大化时的"下拉还原"由 bindMaximizedTitlebarDrag（JS 路径）接管。
    document.querySelectorAll(".pywebview-drag-region").forEach((el) => {
      el.addEventListener(
        "mousedown",
        (e) => {
          if (isNoDragTarget(e.target)) return;
          if (e.button !== 0 || maximized) return;
          e.preventDefault();
          e.stopPropagation();
          a?.window_begin_drag?.();
        },
        true
      );
    });
  }

  function bindFocusStateSync(a, btnMax) {
    // 原生拖动（下拉还原最大化 / Aero Snap 最大化）后，JS 侧状态可能过期：
    // 窗口重新获得焦点时拉取真实最大化状态，刷新图标
    global.addEventListener("focus", () => {
      a?.get_window_chrome?.().then((res) => {
        if (res?.status === "ok" && !!res.maximized !== maximized) {
          onMaximizeStateChange(!!res.maximized, btnMax);
        }
      });
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
      // 版本号与后端 __version__ 单一来源统一显示（避免 UI 硬编码漂移）
      if (typeof res?.version === "string" && res.version) {
        const v = `v${res.version}`;
        document.title = `Memoria ${v}`;
        const h1 = document.querySelector("#welcome h1");
        if (h1) h1.innerHTML = `Memoria <span class="-app-version">${v}</span>`;
        const badge = document.getElementById("app-badge");
        if (badge) badge.textContent = v;
      }
    } catch (_) {
      frameless = false;
    }

    if (!frameless) {
      wrap.classList.add("hidden");
      // 原生窗口：系统标题栏负责窗口控制，禁用前端拖拽区域
      document.querySelectorAll(".pywebview-drag-region").forEach((el) => {
        el.style.setProperty("-webkit-app-region", "no-drag");
      });
      return;
    }

    wrap.classList.remove("hidden");

    const btnMin = document.getElementById("btn-win-minimize");
    const btnMax = document.getElementById("btn-win-maximize");
    const btnClose = document.getElementById("btn-win-close");

    bindResizeLayer(a);
    if (shellKind === "pywebview") {
      // WebView2 不（可靠地）支持 -webkit-app-region: drag：显式禁用。
      // 窗口拖动统一走 WM_NCHITTEST→HTCAPTION 原生路径（见 window_win32.py）
      document.querySelectorAll(".pywebview-drag-region").forEach((el) => {
        el.style.setProperty("-webkit-app-region", "no-drag");
      });
    }
    bindTitlebarDrag(a);
    if (shellKind === "pywebview") {
      // 原生拖动：mousedown → RPC window_begin_drag → WndProc 发起原生
      // 标题栏拖动（ReleaseCapture + WM_NCLBUTTONDOWN HTCAPTION）；
      // 最大化时的"下拉还原"走 JS 路径（bindMaximizedTitlebarDrag）
      bindNativeCaptionDrag(a);
      bindMaximizedTitlebarDrag(a, btnMax);
      bindFocusStateSync(a, btnMax);
    } else {
      bindMaximizedTitlebarDrag(a, btnMax);
    }
    bindToolbarDragExclusionSync();

    if (shellKind === "pywebview") {
      // 双击标题栏切换最大化/还原（原生窗口行为，标题栏被隐藏后需手动补上）
      document.querySelectorAll(".pywebview-drag-region").forEach((el) => {
        el.addEventListener("dblclick", (e) => {
          if (isNoDragTarget(e.target)) return;
          e.preventDefault();
          e.stopPropagation();
          a.window_toggle_maximize?.().then((res) => {
            if (res?.status === "ok") {
              onMaximizeStateChange(!!res.maximized, btnMax);
            }
          });
        });
      });
    }

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
