/**
 * 统一桌面 API 桥接：pywebview（开发）与 PyQt6 QWebChannel（发布）
 */
(function (global) {
  "use strict";

  const READY = "memoriaready";

  function parseRpcResult(raw) {
    if (raw === null || raw === undefined) return raw;
    if (typeof raw === "object") return raw;
    if (typeof raw === "string") {
      try {
        return JSON.parse(raw);
      } catch (_) {
        return raw;
      }
    }
    return raw;
  }

  function installApi(api) {
    if (!api) return;
    global.memoria = global.memoria || {};
    global.memoria.api = api;
    global.dispatchEvent(new Event(READY));
  }

  function wrapQtMethod(bridge, prop) {
    return function (...args) {
      const invoked = bridge.invoke(String(prop), JSON.stringify(args));
      if (invoked && typeof invoked.then === "function") {
        return invoked.then(parseRpcResult);
      }
      return parseRpcResult(invoked);
    };
  }

  function makeQtApi(bridge) {
    return new Proxy(
      {},
      {
        get(_target, prop) {
          if (prop === "then" || typeof prop === "symbol") return undefined;
          return wrapQtMethod(bridge, prop);
        },
      }
    );
  }

  function installQtApi(bridge) {
    global.__memoriaQtBridge = bridge;
    installApi(makeQtApi(bridge));
  }

  function api() {
    return global.memoria && global.memoria.api;
  }

  function onReady(fn) {
    if (typeof fn !== "function") return;
    if (api()) {
      fn();
      return;
    }
    global.addEventListener(READY, fn, { once: true });
  }

  function bootQtChannel() {
    if (global.__memoriaQtBridgeReady) return true;
    if (global.__memoriaQtBooting) return false;
    if (typeof QWebChannel === "undefined" || !global.qt?.webChannelTransport) {
      return false;
    }
    global.__memoriaQtBooting = true;
    new QWebChannel(global.qt.webChannelTransport, function (channel) {
      if (channel.objects?.bridge) {
        installQtApi(channel.objects.bridge);
        global.__memoriaQtBridgeReady = true;
      }
    });
    return false;
  }

  function ensureQtBridge() {
    if (bootQtChannel()) return;
    let tries = 0;
    const timer = setInterval(function () {
      tries += 1;
      if (global.__memoriaQtBridgeReady || bootQtChannel() || tries > 400) {
        clearInterval(timer);
      }
    }, 25);
  }

  global.addEventListener("pywebviewready", () => {
    if (global.pywebview && global.pywebview.api) {
      installApi(global.pywebview.api);
    }
  });

  if (global.pywebview && global.pywebview.api) {
    installApi(global.pywebview.api);
  }

  if (
    global.qt?.webChannelTransport ||
    (global.navigator?.userAgent || "").includes("QtWebEngine")
  ) {
    ensureQtBridge();
  }

  global.MemoriaBridge = {
    api,
    onReady,
    installApi,
    installQtApi,
    makeQtApi,
  };
})(typeof window !== "undefined" ? window : globalThis);
