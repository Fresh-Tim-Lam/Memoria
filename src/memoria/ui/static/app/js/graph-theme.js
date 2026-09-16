/**
 * graph-theme.js — 图谱（2D/3D 画布）主题配色
 *
 * 依据：docs/conventions/frontend-modules.md（R1 新代码不进 app.js）
 * 为什么需要它：2D/3D 图谱是 <canvas>/WebGL 绘制的，**吃不到 CSS 变量**，
 *   必须把 :root 上的 --graph-* 显式读出来再交给绘图代码。
 * 颜色来源：theme/memoria.css（深色）与 theme/light.css（浅色）里的 --graph-* 变量；
 *   两个视图都从这里取值，避免各写一套而漂移。
 * 缓存：按 <html data-theme> 缓存，避免"每帧 getComputedStyle"；
 *   主题一变（data-theme 改变或收到 memoria:themechange）自动失效。
 * 状态：生效中，2026-09-16
 */
(function (global) {
  "use strict";

  // 兜底值 = 改造前的硬编码色，取不到变量时行为与旧版一致
  var FALLBACK = {
    bg: "#0a0d13",
    containerBg: "#161b22",
    node: "#c9d1d9",
    nodeHover: "#f0f6fc",
    nodeTarget: "#79c0ff",
    nodeDim: "#3d4350",
    nodeInvalid: "#3a4152",
    nodeMuted: "#8b949e",
    label: "#adbac7",
    labelInvalid: "#6e7681",
    labelBg: "rgba(13, 17, 23, 0.85)",
    halo: "rgba(13, 17, 23, 0.92)",
    focus: "#58a6ff",
    focusExt: "#a371f7",
    galaxyDim: "rgb(139,148,158)",
    galaxyBright: "rgb(240,246,252)",
  };

  var VAR_MAP = {
    bg: "--graph-bg",
    node: "--graph-node",
    nodeHover: "--graph-node-hover",
    nodeTarget: "--graph-node-target",
    nodeDim: "--graph-node-dim",
    nodeInvalid: "--graph-node-invalid",
    nodeMuted: "--graph-node-muted",
    label: "--graph-label",
    labelInvalid: "--graph-label-invalid",
    labelBg: "--graph-label-bg",
    halo: "--graph-halo",
    focus: "--graph-focus",
    focusExt: "--graph-focus-ext",
    galaxyDim: "--graph-galaxy-dim",
    galaxyBright: "--graph-galaxy-bright",
  };

  var cache = null;          // { theme, colors }
  var subscribers = [];

  function themeKey() {
    return document.documentElement.getAttribute("data-theme") || "dark";
  }

  function custom(name, dflt) {
    try {
      var got = getComputedStyle(document.documentElement).getPropertyValue(name);
      got = (got || "").trim();
      return got || dflt;
    } catch (e) {
      return dflt;
    }
  }

  /** CSS 颜色字符串（canvas 2D 用） */
  function colors() {
    var key = themeKey();
    if (cache && cache.theme === key) return cache.colors;
    var out = {};
    Object.keys(VAR_MAP).forEach(function (k) {
      out[k] = custom(VAR_MAP[k], FALLBACK[k]);
    });
    cache = { theme: key, colors: out };
    return out;
  }

  function cssToInt(s) {
    var m = /^#([0-9a-fA-F]{6})$/.exec(String(s).trim());
    if (m) return parseInt(m[1], 16);
    m = /^#([0-9a-fA-F]{3})$/.exec(String(s).trim());
    if (m) {
      var h = m[1];
      return parseInt(h[0] + h[0] + h[1] + h[1] + h[2] + h[2], 16);
    }
    m = /^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/.exec(String(s).trim());
    if (m) return (+m[1] << 16) | (+m[2] << 8) | +m[3];
    return 0xffffff;
  }

  /** 0xRRGGBB 整数（three.js 用），键与 colors() 相同 */
  function hex() {
    var c = colors();
    var out = {};
    Object.keys(c).forEach(function (k) {
      out[k] = cssToInt(c[k]);
    });
    return out;
  }

  function invalidate() {
    cache = null;
  }

  function notify() {
    invalidate();
    subscribers.forEach(function (cb) {
      try {
        cb();
      } catch (e) {
        /* 单个订阅者出错不影响其它视图 */
      }
    });
  }

  function onThemeChange(cb) {
    if (typeof cb === "function") subscribers.push(cb);
  }

  // 主题切换（theme-mode.js 派发）与系统外观变化都刷新调色板并通知视图重绘
  if (typeof global.addEventListener === "function") {
    global.addEventListener("memoria:themechange", notify);
  }
  try {
    if (global.matchMedia) {
      var mql = global.matchMedia("(prefers-color-scheme: light)");
      var onChange = function () { notify(); };
      if (mql.addEventListener) mql.addEventListener("change", onChange);
      else if (mql.addListener) mql.addListener(onChange);
    }
  } catch (e) {
    /* ignore */
  }

  global.MemoriaGraphTheme = {
    colors: colors,
    hex: hex,
    toInt: cssToInt,        // CSS 颜色串 → 0xRRGGBB（three.js / 自算需要）
    invalidate: invalidate,
    onThemeChange: onThemeChange,
  };
})(window);
