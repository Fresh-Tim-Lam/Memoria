/**
 * Memoria i18n 引擎：界面语言包加载/查询/切换。
 *
 * 契约见 docs/conventions/i18n.md：
 * - 包位置 app/i18n/zh-CN.js / en.js，挂到 window.MEMORIA_LOCALES。
 * - 查找顺序：当前语言 → zh-CN → 键名本身（缺键回退中文，不抛错）。
 * - 切换：settings → 显示 → 界面语言；即时生效（刷新 [data-i18n]/[data-i18n-attr] 节点
 *   并派发 memoria:langchange 供动态区域重渲染），持久化到本地与磁盘 ui-settings.json。
 */
(function (g) {
  "use strict";

  var LS_KEY = "-i18n";
  var DEFAULT_LANG = "zh-CN";
  var SUPPORTED = ["zh-CN", "en"];
  var _refreshFns = [];
  var _diskSeed = null;

  function api() {
    return g.MemoriaBridge && g.MemoriaBridge.api && g.MemoriaBridge.api();
  }

  function locales() {
    return g.MEMORIA_LOCALES || {};
  }

  function readLocalLang() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return "";
      var d = JSON.parse(raw);
      return d && typeof d === "object" && typeof d.lang === "string" ? d.lang : "";
    } catch (_e) {
      return "";
    }
  }

  function writeLocalLang(lang) {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({ lang: lang }));
    } catch (_e) {
      /* ignore */
    }
  }

  function supported(lang) {
    return SUPPORTED.indexOf(lang) !== -1;
  }

  function currentLang() {
    var l = readLocalLang();
    return supported(l) ? l : DEFAULT_LANG;
  }

  function lookup(lang, key) {
    var node = locales()[lang];
    if (!node) return null;
    var parts = String(key).split(".");
    for (var i = 0; i < parts.length; i++) {
      if (!node || typeof node !== "object") return null;
      node = node[parts[i]];
    }
    return typeof node === "string" ? node : null;
  }

  function fill(template, params) {
    if (!params || typeof template !== "string") return template;
    return template.replace(/\{(\w+)\}/g, function (m, name) {
      return params[name] !== undefined && params[name] !== null ? String(params[name]) : m;
    });
  }

  /** t(key[, params])：当前语言 → zh-CN → 键名。 */
  function t(key, params) {
    var v = lookup(currentLang(), key);
    if (v === null) v = lookup(DEFAULT_LANG, key);
    return fill(v === null ? key : v, params);
  }

  /** 仅查指定语言包，无回退；返回 string 或 null（后端 code 消息本地化用） */
  function rawLookup(lang, key) {
    return lookup(lang, key);
  }

  /** 语言自述名（用于选择框显示；语言名以母语展示，两个包中取值一致） */
  function langDisplay(code) {
    const v = t("langs." + code);
    return v !== "langs." + code ? v : code;
  }

  /** 静态节点刷新：文本 data-i18n；属性 data-i18n-attr="title:key;placeholder:key2" */
  function applyStatic(root) {
    var scope = root || document;
    if (!scope) return;
    // CSS content 文案（伪元素无法挂 data-i18n）：整页刷新时同步 CSS 变量
    if (scope === document && document.documentElement) {
      document.documentElement.style.setProperty("--memoria-i18n-range", t("assist.rangeTag"));
    }
    if (scope.querySelectorAll) {
      scope.querySelectorAll("[data-i18n]").forEach(function (el) {
        var key = el.getAttribute("data-i18n");
        if (key) el.textContent = t(key);
      });
      scope.querySelectorAll("[data-i18n-attr]").forEach(function (el) {
        var spec = String(el.getAttribute("data-i18n-attr") || "");
        spec.split(";").forEach(function (pair) {
          var idx = pair.indexOf(":");
          if (idx <= 0) return;
          var attr = pair.slice(0, idx).trim();
          var key = pair.slice(idx + 1).trim();
          if (attr && key) el.setAttribute(attr, t(key));
        });
      });
    }
  }

  function setLang(code) {
    if (!supported(code)) return currentLang();
    writeLocalLang(code);
    scheduleDiskSave();
    applyStatic();
    try {
      g.dispatchEvent(new Event("memoria:langchange"));
    } catch (_e) {
      /* ignore */
    }
    _refreshFns.forEach(function (fn) {
      try {
        fn();
      } catch (_e) {
        /* ignore */
      }
    });
    return code;
  }

  function addRefresh(fn) {
    if (typeof fn === "function") _refreshFns.push(fn);
  }

  var _diskTimer = null;
  function scheduleDiskSave() {
    if (_diskTimer) clearTimeout(_diskTimer);
    _diskTimer = setTimeout(function () {
      _diskTimer = null;
      var a = api();
      if (a && a.save_ui_settings) {
        a.save_ui_settings({ i18n: { lang: currentLang() } }).catch(function () {});
      }
    }, 280);
  }

  /** 启动时从磁盘种子补充（本地已有偏好则本地优先，与显示设置一致）。 */
  async function hydrate() {
    var a = api();
    if (a && a.get_ui_settings) {
      try {
        var res = await a.get_ui_settings();
        if (res && res.status === "ok" && res.settings && res.settings.i18n) {
          var seed = res.settings.i18n.lang;
          if (supported(seed) && !readLocalLang()) writeLocalLang(seed);
        }
      } catch (_e) {
        /* ignore */
      }
    }
    applyStatic();
    return currentLang();
  }

  g.MemoriaI18n = {
    DEFAULT_LANG: DEFAULT_LANG,
    SUPPORTED: SUPPORTED,
    currentLang: currentLang,
    setLang: setLang,
    t: t,
    rawLookup: rawLookup,
    langDisplay: langDisplay,
    applyStatic: applyStatic,
    addRefresh: addRefresh,
    hydrate: hydrate,
  };
})(typeof window !== "undefined" ? window : globalThis);
