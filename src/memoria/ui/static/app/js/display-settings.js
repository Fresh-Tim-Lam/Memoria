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
  const FONT_MAX = 20;
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

  function load() {
    const merged = Object.assign({}, DEFAULTS, readLocal());
    if (diskPrefs && diskPrefs.display) Object.assign(merged, diskPrefs.display);
    const fs = clamp(merged.previewFontSize, FONT_MIN, FONT_MAX);
    if (fs !== null) merged.previewFontSize = Math.round(fs);
    const sc = clamp(merged.uiScale, SCALE_MIN, SCALE_MAX);
    if (sc !== null) merged.uiScale = round1(sc);
    return merged;
  }

  /** 预览容器：优先 #preview（主编辑区），其次 .-preview（设置页内嵌预览等） */
  function previewRoot() {
    return document.getElementById("preview") || document.querySelector(".-preview");
  }

  function applyPreviewFontSize(px) {
    const root = previewRoot();
    if (!root) return;
    root.style.setProperty("--preview-font-size", px + "px");
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
    applyPreviewFontSize(s.previewFontSize);
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
        diskPrefs = { display: res.settings.display };
        writeLocal(Object.assign({}, DEFAULTS, readLocal(), diskPrefs));
      }
    } catch (_) {
      /* ignore */
    }
    applyAll();
    return load();
  }

  function save(partial) {
    const next = Object.assign({}, load(), partial);
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
    return `<section class="-settings-section">
      <h3 class="-settings-heading">预览区文字</h3>
      <p class="-muted -settings-note">仅作用于预览区正文，内部元素（标题/代码块/引用）随比例缩放。</p>
      ${rangeField("previewFontSize", "字号", FONT_MIN, FONT_MAX, 1, s.previewFontSize, `默认 ${DEFAULTS.previewFontSize}px，范围 ${FONT_MIN}–${FONT_MAX}px。`)}
    </section>
    <section class="-settings-section">
      <h3 class="-settings-heading">界面整体缩放</h3>
      <p class="-muted -settings-note">对整个应用界面按比例缩放（等价于浏览器 Ctrl+±）。</p>
      ${rangeField("uiScale", "缩放比例", SCALE_MIN, SCALE_MAX, SCALE_STEP, s.uiScale, "快捷键：Ctrl+= 放大 / Ctrl+- 缩小 / Ctrl+0 复位 100%。")}
      <div class="-settings-actions">
        <button type="button" class="-btn secondary" id="display-ui-scale-reset">复位为 100%</button>
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
