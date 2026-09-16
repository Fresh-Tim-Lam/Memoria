/**
 * theme-mode.js — 主题模式（深色 / 浅色 / 跟随系统）
 *
 * 依据：docs/conventions/frontend-modules.md（R1 新代码不进 app.js，模块自行初始化）
 * 落点：<html data-theme="dark|light">，样式见 theme/light.css
 * 持久化：磁盘 ui-settings.json → layout.theme（与 layout.sidebarWidth 同段，浅合并不互相覆盖）
 *        localStorage 仅作首帧快路径（桌面壳 WebView2 私有模式下不跨进程保留，磁盘为准）
 * 状态：生效中，2026-09-16
 */
(function (global) {
  "use strict";

  var KEY = "-theme-mode";
  var MODES = ["system", "dark", "light"];
  var mode = "system";

  function prefersLight() {
    try {
      return !!(global.matchMedia && global.matchMedia("(prefers-color-scheme: light)").matches);
    } catch (e) {
      return false;
    }
  }

  /** 实际生效的主题：system 按系统外观解析为 dark / light */
  function resolved(m) {
    var mm = m || mode;
    if (mm === "light") return "light";
    if (mm === "dark") return "dark";
    return prefersLight() ? "light" : "dark";
  }

  function apply() {
    var root = document.documentElement;
    if (root) root.setAttribute("data-theme", resolved());
  }

  function api() {
    return global.MemoriaBridge && global.MemoriaBridge.api();
  }

  function persist() {
    try {
      localStorage.setItem(KEY, mode);
    } catch (e) {
      /* ignore */
    }
    var a = api();
    if (a && a.save_ui_settings) {
      a.save_ui_settings({ layout: { theme: mode } }).catch(function () {});
    }
  }

  function set(m) {
    if (MODES.indexOf(m) === -1) return;
    mode = m;
    apply();
    persist();
  }

  function watchSystem() {
    if (!global.matchMedia) return;
    try {
      var mql = global.matchMedia("(prefers-color-scheme: light)");
      var onChange = function () {
        if (mode === "system") apply();
      };
      if (mql.addEventListener) mql.addEventListener("change", onChange);
      else if (mql.addListener) mql.addListener(onChange);   // 旧内核兜底
    } catch (e) {
      /* ignore */
    }
  }

  /** 启动时以磁盘设置为准（只覆盖一次；之后用户手选即为准） */
  async function hydrateFromDisk() {
    var a = api();
    if (!a || !a.get_ui_settings) return;
    try {
      var res = await a.get_ui_settings();
      var t = res && res.status === "ok" && res.settings && res.settings.layout
        ? res.settings.layout.theme
        : null;
      if (MODES.indexOf(t) !== -1 && t !== mode) {
        mode = t;
        apply();
      }
    } catch (e) {
      /* 非桌面环境忽略 */
    }
  }

  function boot() {
    try {
      var saved = localStorage.getItem(KEY);
      if (MODES.indexOf(saved) !== -1) mode = saved;
    } catch (e) {
      /* ignore */
    }
    apply();
    watchSystem();
    if (global.MemoriaBridge && global.MemoriaBridge.onReady) {
      global.MemoriaBridge.onReady(function () { hydrateFromDisk(); });
    } else {
      hydrateFromDisk();
    }
  }

  global.MemoriaThemeMode = {
    MODES: MODES,
    get: function () { return mode; },
    resolved: function () { return resolved(); },
    set: set,
    init: boot,
  };

  // 立即应用（脚本在 body 末尾，此时 <html> 已存在），早于应用内容渲染
  boot();
})(window);
