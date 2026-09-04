/**
 * 知识库静默检查：间隔配置 + 设置页
 */
(function (global) {
  "use strict";

  const STORAGE_KEY = "-check-settings";
  const INTERVAL_OPTIONS = [0, 30, 60, 120, 300, 600];

  const DEFAULTS = {
    silentCheckEnabled: true,
    silentCheckIntervalSec: 120,
  };

  let diskPrefs = null;
  let diskSaveTimer = null;
  let silentTimer = null;
  let silentRunner = null;
  let onChangeHandler = null;

  function api() {
    return global.MemoriaBridge && global.MemoriaBridge.api();
  }

  function readLocal() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function writeLocal(data) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (_) {
      /* ignore */
    }
  }

  function normalizeInterval(sec) {
    const n = parseInt(sec, 10);
    if (!Number.isFinite(n)) return DEFAULTS.silentCheckIntervalSec;
    return INTERVAL_OPTIONS.indexOf(n) !== -1 ? n : DEFAULTS.silentCheckIntervalSec;
  }

  function load() {
    const merged = { ...DEFAULTS, ...readLocal(), ...(diskPrefs || {}) };
    merged.silentCheckIntervalSec = normalizeInterval(merged.silentCheckIntervalSec);
    merged.silentCheckEnabled = merged.silentCheckIntervalSec > 0
      ? !!merged.silentCheckEnabled
      : false;
    return merged;
  }

  function scheduleDiskSave() {
    if (diskSaveTimer) clearTimeout(diskSaveTimer);
    diskSaveTimer = setTimeout(() => {
      diskSaveTimer = null;
      persistToDisk();
    }, 280);
  }

  function persistToDisk() {
    const a = api();
    if (!a?.save_ui_settings) return;
    a.save_ui_settings({ check: load() }).catch(() => {});
  }

  async function hydrateFromDisk() {
    const a = api();
    if (!a?.get_ui_settings) return load();
    try {
      const res = await a.get_ui_settings();
      if (res?.status === "ok" && res.settings?.check) {
        diskPrefs = { ...res.settings.check };
        writeLocal({ ...DEFAULTS, ...readLocal(), ...diskPrefs });
      }
    } catch (_) {
      /* ignore */
    }
    return load();
  }

  function save(partial) {
    const next = { ...load(), ...partial };
    if (next.silentCheckIntervalSec === 0) {
      next.silentCheckEnabled = false;
    } else if (partial.silentCheckIntervalSec != null && partial.silentCheckIntervalSec > 0) {
      next.silentCheckEnabled = true;
    }
    next.silentCheckIntervalSec = normalizeInterval(next.silentCheckIntervalSec);
    writeLocal(next);
    diskPrefs = { ...(diskPrefs || {}), ...next };
    scheduleDiskSave();
    notifyChange();
    return next;
  }

  function reset() {
    localStorage.removeItem(STORAGE_KEY);
    diskPrefs = { ...DEFAULTS };
    scheduleDiskSave();
    notifyChange();
    return { ...DEFAULTS };
  }

  function getIntervalMs() {
    const s = load();
    if (!s.silentCheckEnabled || s.silentCheckIntervalSec <= 0) return 0;
    return s.silentCheckIntervalSec * 1000;
  }

  function notifyChange() {
    syncFormFromSettings();
    restartSilentCheck();
    if (onChangeHandler) onChangeHandler(load());
  }

  function onChange(fn) {
    onChangeHandler = fn;
  }

  function stopSilentCheck() {
    if (silentTimer) {
      clearInterval(silentTimer);
      silentTimer = null;
    }
  }

  function startSilentCheck(runFn) {
    silentRunner = typeof runFn === "function" ? runFn : silentRunner;
    stopSilentCheck();
    const ms = getIntervalMs();
    if (!ms || !silentRunner) return;
    silentTimer = setInterval(() => {
      silentRunner();
    }, ms);
  }

  function restartSilentCheck() {
    if (silentRunner) startSilentCheck(silentRunner);
  }

  function T(key, params) {
    return global.MemoriaI18n && global.MemoriaI18n.t
      ? global.MemoriaI18n.t(key, params)
      : key;
  }

  function intervalLabel(sec) {
    if (sec <= 0) return T("check.settings.off");
    if (sec % 60 === 0) return T("check.settings.minutes", { n: sec / 60 });
    return T("check.settings.seconds", { n: sec });
  }

  function renderSettingsBody() {
    const s = load();
    const intervalOptions = INTERVAL_OPTIONS.map(
      (sec) =>
        `<option value="${sec}"${s.silentCheckIntervalSec === sec ? " selected" : ""}>${intervalLabel(sec)}</option>`
    ).join("");
    return `<div class="-settings-layout -settings-layout--solo">
      <div class="-settings-form">
        <section class="-settings-section">
          <h3 class="-settings-heading">${T("check.settings.heading")}</h3>
          <p class="-muted -settings-note">${T("check.settings.noteMain")}</p>
          <label class="-settings-field">
            <span>${T("check.settings.interval")}</span>
            <select data-check-setting="silentCheckIntervalSec">${intervalOptions}</select>
          </label>
          <label class="-settings-field -settings-field--inline">
            <input type="checkbox" data-check-setting="silentCheckEnabled"${s.silentCheckEnabled && s.silentCheckIntervalSec > 0 ? " checked" : ""}${s.silentCheckIntervalSec === 0 ? " disabled" : ""}>
            <span>${T("check.settings.enabled")}</span>
          </label>
          <p class="-muted -settings-note">${T("check.settings.noteOff")}</p>
        </section>
      </div>
    </div>`;
  }

  function syncFormFromSettings() {
    const root = document.getElementById("settings-body");
    if (!root) return;
    const s = load();
    root.querySelectorAll("[data-check-setting]").forEach((el) => {
      const key = el.dataset.checkSetting;
      if (!key || s[key] === undefined) return;
      if (el.type === "checkbox") {
        el.checked = !!s[key];
        if (key === "silentCheckEnabled") {
          el.disabled = s.silentCheckIntervalSec === 0;
        }
      } else if (el.tagName === "SELECT") {
        el.value = String(s[key]);
      }
    });
  }

  function bindSettingsForm(root) {
    root.querySelectorAll("[data-check-setting]").forEach((el) => {
      const key = el.dataset.checkSetting;
      const handler = () => {
        if (el.type === "checkbox") {
          save({ [key]: el.checked });
          return;
        }
        const val = parseInt(el.value, 10);
        if (key === "silentCheckIntervalSec") {
          save({
            silentCheckIntervalSec: val,
            silentCheckEnabled: val > 0,
          });
        } else {
          save({ [key]: val });
        }
      };
      el.addEventListener("change", handler);
    });
  }

  global.MemoriaCheckSettings = {
    DEFAULTS,
    INTERVAL_OPTIONS,
    load,
    save,
    reset,
    hydrateFromDisk,
    getIntervalMs,
    onChange,
    startSilentCheck,
    stopSilentCheck,
    restartSilentCheck,
    renderSettingsBody,
    bindSettingsForm,
    syncFormFromSettings,
  };
})(typeof window !== "undefined" ? window : globalThis);
