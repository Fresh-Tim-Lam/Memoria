/**
 * 显示设置：预览区字号 + 界面整体缩放
 * 配置入口：设置 → "显示" 页签；界面缩放另支持 Ctrl+= / Ctrl+- / Ctrl+0。
 * 持久化：localStorage（"-display-settings"）+ 磁盘 ui-settings.json（display 段，可选）。
 */
(function (global) {
  "use strict";

  const STORAGE_KEY = "-display-settings";

  const DEFAULTS = {
    previewFontSize: 14, // 预览区正文字号（px）
    uiScale: 1.0,        // 界面整体缩放倍率
  };

  const FONT_MIN = 12;
  const FONT_MAX = 28;
  const SCALE_MIN = 0.8;
  const SCALE_MAX = 1.5;
  const SCALE_STEP = 0.1;

  let diskPrefs = null;
  let diskSaveTimer = null;

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

  function clamp(v, min, max) {
    const n = Number(v);
    if (!Number.isFinite(n)) return null;
    return Math.min(max, Math.max(min, n));
  }

  function round1(x) {
    return Math.round(x * 10) / 10;
  }

  /** 仅保留本模块管理的两个键，避免 display 等脏键污染 load/save 结果 */
  function pickKnown(data) {
    const out = {};
    if (data && data.previewFontSize !== undefined) out.previewFontSize = data.previewFontSize;
    if (data && data.uiScale !== undefined) out.uiScale = data.uiScale;
    return out;
  }

  function load() {
    // 优先级：本地修改 > 磁盘种子 > 默认值。磁盘值仅作为启动时的初始种子
    // （hydrateFromDisk 已写入 localStorage）；若无条件覆盖本地，用户拖滑块
    // 写入 localStorage 后会被 diskPrefs 立即回滚，界面无任何反应。
    const disk = diskPrefs && diskPrefs.display ? diskPrefs.display : {};
    const merged = Object.assign({}, DEFAULTS, disk, readLocal());
    const fs = clamp(merged.previewFontSize, FONT_MIN, FONT_MAX);
    if (fs !== null) merged.previewFontSize = Math.round(fs);
    const sc = clamp(merged.uiScale, SCALE_MIN, SCALE_MAX);
    if (sc !== null) merged.uiScale = round1(sc);
    return pickKnown(merged);
  }

  /** 字号：同时作用于预览区（--preview-font-size）与源码/分栏区（--editor-font-size） */
  function applyFontSize(px) {
    const preview = document.getElementById("preview");
    if (preview) preview.style.setProperty("--preview-font-size", px + "px");
    const editor = document.getElementById("editor");
    if (editor) editor.style.setProperty("--editor-font-size", px + "px");
  }

  function applyUiScale(x) {
    const target = round1(x);
    // 真实布局放缩：根字号 = 16px × scale。CSS 尺寸均为 rem（相对根字号），
    // 缩放时 UI/字体/间距等比变化，flex/百分比布局重新排布填满窗口，
    // 不会像 zoom 那样"放大镜越界"。
    document.documentElement.style.fontSize =
      target === DEFAULTS.uiScale ? "" : 16 * target + "px";
  }

  function applyAll() {
    const s = load();
    applyFontSize(s.previewFontSize);
    applyUiScale(s.uiScale);
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
    if (!a || !a.save_ui_settings) return;
    a.save_ui_settings({ display: load() }).catch(() => {});
  }

  async function hydrateFromDisk() {
    const a = api();
    if (!a || !a.get_ui_settings) {
      applyAll();
      return load();
    }
    try {
      const res = await a.get_ui_settings();
      if (res && res.status === "ok" && res.settings && res.settings.display) {
        diskPrefs = { display: pickKnown(res.settings.display) };
        // 清洗合并结果，避免残留的 display 键继续嵌套污染
        writeLocal(pickKnown(Object.assign({}, DEFAULTS, readLocal(), diskPrefs.display)));
      }
    } catch (_) {
      /* ignore */
    }
    applyAll();
    return load();
  }

  function save(partial) {
    const next = Object.assign({}, load(), pickKnown(partial));
    writeLocal(next);
    scheduleDiskSave();
    applyAll();
  }

  /** Ctrl+= / Ctrl+- 步进调整界面缩放（返回生效后的值） */
  function adjustUiScale(delta) {
    const s = load();
    const next = round1(clamp(round1(s.uiScale + delta), SCALE_MIN, SCALE_MAX));
    if (next !== s.uiScale) save({ uiScale: next });
    return load().uiScale;
  }

  function resetUiScale() {
    save({ uiScale: DEFAULTS.uiScale });
  }

  function rangeField(key, label, min, max, step, value, note) {
    return `<label class="-settings-field">
      <span>${label}</span>
      <input type="range" data-display-setting="${key}" min="${min}" max="${max}" step="${step}" value="${value}" />
      <output data-display-setting-value="${key}">${value}</output>
    </label>${note ? `<p class="-muted -settings-note">${note}</p>` : ""}`;
  }

  function renderSettingsBody() {
    const s = load();
    const T = (k, p) => (global.MemoriaI18n ? global.MemoriaI18n.t(k, p) : k);
    const i18n = global.MemoriaI18n;
    const curLang = i18n ? i18n.currentLang() : "zh-CN";
    const langOptions = (i18n ? i18n.SUPPORTED : ["zh-CN"])
      .map(
        (code) =>
          `<option value="${code}"${code === curLang ? " selected" : ""}>${i18n ? i18n.langDisplay(code) : code}</option>`
      )
      .join("");
    return `<section class="-settings-section">
      <h3 class="-settings-heading">${T("settings.display.langGroup")}</h3>
      <label class="-settings-field">
        <span>${T("settings.display.langLabel")}</span>
        <select id="display-language">${langOptions}</select>
      </label>
      <p class="-muted -settings-note">${T("settings.display.langNote")}</p>
    </section>
    <section class="-settings-section">
      <h3 class="-settings-heading">${T("settings.display.text")}</h3>
      <p class="-muted -settings-note">${T("settings.display.fontNote")}</p>
      ${rangeField("previewFontSize", T("settings.display.fontSize"), FONT_MIN, FONT_MAX, 1, s.previewFontSize, T("settings.display.fontDefault", { def: DEFAULTS.previewFontSize, min: FONT_MIN, max: FONT_MAX }))}
    </section>
    <section class="-settings-section">
      <h3 class="-settings-heading">${T("settings.display.uiScaleGroup")}</h3>
      <p class="-muted -settings-note">${T("settings.display.uiScaleNote")}</p>
      ${rangeField("uiScale", T("settings.display.uiScale"), SCALE_MIN, SCALE_MAX, SCALE_STEP, s.uiScale, T("settings.display.uiScaleHint"))}
      <div class="-settings-actions">
        <button type="button" class="-btn secondary" id="display-ui-scale-reset">${T("settings.display.resetScale")}</button>
      </div>
    </section>`;
  }

  function bindSettingsForm(root) {
    if (!root) return;
    root.querySelectorAll("[data-display-setting]").forEach((el) => {
      const key = el.dataset.displaySetting;
      const handler = () => {
        let val = el.value;
        if (el.type === "range") {
          val =
            el.step && String(el.step).indexOf(".") !== -1
              ? parseFloat(val)
              : parseInt(val, 10);
          const out = root.querySelector(`[data-display-setting-value="${key}"]`);
          if (out) out.textContent = String(val);
        }
        save({ [key]: val });
      };
      el.addEventListener("input", handler);
      el.addEventListener("change", handler);
    });
    const resetBtn = root.querySelector("#display-ui-scale-reset");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        resetUiScale();
        const out = root.querySelector('[data-display-setting-value="uiScale"]');
        if (out) out.textContent = String(DEFAULTS.uiScale);
        const range = root.querySelector('[data-display-setting="uiScale"]');
        if (range) range.value = String(DEFAULTS.uiScale);
      });
    }
    const langSel = root.querySelector("#display-language");
    if (langSel && global.MemoriaI18n) {
      langSel.addEventListener("change", () => {
        global.MemoriaI18n.setLang(langSel.value);
        if (global.MemoriaGraphSettings && global.MemoriaGraphSettings.rerenderCurrentTab) {
          global.MemoriaGraphSettings.rerenderCurrentTab();
        }
      });
    }
  }

  global.MemoriaDisplaySettings = {
    DEFAULTS,
    load,
    save,
    applyAll,
    hydrateFromDisk,
    adjustUiScale,
    resetUiScale,
    renderSettingsBody,
    bindSettingsForm,
  };
})(window);
