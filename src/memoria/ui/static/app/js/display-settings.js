/**
 * 显示设置：预览区字号 + 界面整体缩放 + **字体**（按语言各一档 / 顶栏单独一档）
 * 配置入口：设置 → "显示" 页签；界面缩放另支持 Ctrl+= / Ctrl+- / Ctrl+0。
 * 持久化：localStorage（"-display-settings"）+ 磁盘 ui-settings.json（display 段，可选）。
 */
(function (global) {
  "use strict";

  const STORAGE_KEY = "-display-settings";

  const DEFAULTS = {
    previewFontSize: 14, // 预览区正文字号（px）
    uiScale: 1.0,        // 界面整体缩放倍率
    //: 按语言的**正文字体**（`{"zh-CN": "Microsoft YaHei", "en": "Comic Sans MS"}`；空串/缺键 = 该语言跟随默认）
    fonts: {},
    //: 顶栏 "MEMORIA" 的字体（空 = 跟随正文字体）
    fontBrand: "", backgroundPreload: false, // 顶栏字体 / 后台预加载（2026-09-23 追加，见文件末尾「后台预加载」块）
  };

  //: 字体名候选（下拉的选项；用户只能从这些里选 —— 人 2026-09-23：「你应该给下拉可选样式而不是输入」）
  const FONT_CHOICES = [
    "Segoe UI", "Microsoft YaHei", "Microsoft YaHei UI", "SimSun", "SimHei", "KaiTi",
    "PingFang SC", "Noto Sans SC", "Source Han Sans SC",
    "Consolas", "Georgia", "Cambria", "Times New Roman", "Arial", "Comic Sans MS",
  ];

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

  function esc(s) {
    const app = global.MemoriaApp;
    return app && app.esc ? app.esc(s) : String(s == null ? "" : s);
  }

  /** 界面支持的语言列表（`MemoriaI18n` 缺席时退回 zh-CN）。 */
  function langs() {
    const i18n = global.MemoriaI18n;
    const list = i18n && i18n.SUPPORTED ? i18n.SUPPORTED : ["zh-CN"];
    return Array.isArray(list) && list.length ? list : ["zh-CN"];
  }

  /** 规范化「按语言的字体」：**覆盖全部支持的语言**（缺的填空串）、非字符串一律丢成空串。
   *  为什么要把空档也显式写出来：后端 `save_ui_settings` 是**浅合并**（`{**old, **new}`，
   *  `storage/ui_settings.py:56-63`）⇒ 直接"删键"清不掉磁盘上的旧值，会把旧字体在下次启动带回来。
   */
  function normalizeFonts(raw) {
    const out = {};
    for (const code of langs()) {
      const value = raw && typeof raw === "object" ? raw[code] : "";
      out[code] = typeof value === "string" ? value.trim() : "";
    }
    return out;
  }

  /** 单个字体名 → CSS 片段：含空格/逗号时补引号（否则 `Comic Sans MS` 会被当成三个 family）。 */
  function quoteFont(name) {
    const value = String(name || "").trim();
    if (!value) return "";
    if (/^'.*'$/.test(value) || /^".*"$/.test(value)) return value;
    return /[\s,]/.test(value) ? '"' + value.replace(/"/g, "") + '"' : value;
  }

  /** 正文用字体栈：**当前界面语言优先**，其余语言按支持顺序跟上（浏览器按字形逐字选用）。 */
  function fontStack(fonts) {
    const i18n = global.MemoriaI18n;
    const cur = (i18n && i18n.currentLang ? i18n.currentLang() : "") || langs()[0];
    const order = [cur].concat(langs().filter((code) => code !== cur));
    return order.map((code) => quoteFont((fonts || {})[code])).filter(Boolean).join(", ");
  }

  /** 仅保留本模块管理的键，避免脏键污染 load/save 结果 */
  function pickKnown(data) {
    const out = {};
    if (data && data.previewFontSize !== undefined) out.previewFontSize = data.previewFontSize;
    if (data && data.uiScale !== undefined) out.uiScale = data.uiScale;
    if (data && data.fonts !== undefined) out.fonts = normalizeFonts(data.fonts); if (data && data.backgroundPreload !== undefined) out.backgroundPreload = !!data.backgroundPreload;
    if (data) for (const k of PERF_KEYS) if (data[k] !== undefined) out[k] = k === "perfAdmission" ? !!data[k] : clampPerf(k, data[k]); // 2026-09-24 追加：预览池智能替换的权重（见文件末尾「性能版块」块）
    if (data && data.fontBrand !== undefined) {
      out.fontBrand = typeof data.fontBrand === "string" ? data.fontBrand.trim() : "";
    }
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
    merged.fonts = normalizeFonts(merged.fonts);
    merged.fontBrand = typeof merged.fontBrand === "string" ? merged.fontBrand.trim() : "";
    return pickKnown(merged);
  }

  /** 字号：作用预览区（--preview-font-size）、源码 / 分栏区（--editor-font-size）与**对话面板**（--agent-font-size，2026-09-19：设置里的字号同时管对话正文与输入框） */
  function applyFontSize(px) {
    const preview = document.getElementById("preview");
    if (preview) preview.style.setProperty("--preview-font-size", px + "px");
    const editor = document.getElementById("editor");
    if (editor) editor.style.setProperty("--editor-font-size", px + "px");
    document.getElementById("-agent-dock")?.style.setProperty("--agent-font-size", px + "px"); // 对话面板根（元素缺失时 ?. 静默跳过）
  }

  function applyUiScale(x) {
    const target = round1(x);
    // 真实布局放缩：根字号 = 16px × scale。CSS 尺寸均为 rem（相对根字号），
    // 缩放时 UI/字体/间距等比变化，flex/百分比布局重新排布填满窗口，
    // 不会像 zoom 那样"放大镜越界"。
    document.documentElement.style.fontSize =
      target === DEFAULTS.uiScale ? "" : 16 * target + "px";
    // rem 基准变化会重排侧栏等以 rem 定宽的元素，但其几何变化不会触发
    // window resize；主动派发一次，让监听方（图谱容器、dock 生效宽度等）
    // 按新的布局重算。
    window.dispatchEvent(new Event("resize"));
  }

  /**
   * 字体：把两个 CSS 变量挂到 `<html>` 上（`app.css` 末尾那两条规则读它们 ⇒ 一处设置全站生效）：
   * - `--font-content` = 按语言拼的正文栈 ⇒ 作用 `.markdown-body`（**Markdown 预览**与**对话栏里渲染的正文**
   *   共用同一个类）；
   * - `--font-brand` = 顶栏 "MEMORIA" 专用档（留空 ⇒ 由 CSS 兜底回正文字体）。
   * 空值一律**移除**变量（而不是写空串）⇒ 回落到 `--font-sans`（默认字体）。
   */
  function applyFonts(s) {
    const root = document.documentElement;
    const stack = fontStack(s.fonts);
    if (stack) root.style.setProperty("--font-content", stack);
    else root.style.removeProperty("--font-content");
    const brand = quoteFont(s.fontBrand);
    if (brand) root.style.setProperty("--font-brand", brand);
    else root.style.removeProperty("--font-brand");
  }

  function applyAll() {
    const s = load();
    applyFontSize(s.previewFontSize);
    applyUiScale(s.uiScale);
    applyFonts(s); announcePreload(s.backgroundPreload); announcePerfPolicy(s); // 2026-09-23 追加：把「后台预加载」开关同步给 app.js 的预览预渲染调度器（见文件末尾「后台预加载」块）
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

  /** 当前主题模式（深色/浅色/跟随系统）；模块缺失时按跟随系统处理 */
  function themeMode() {
    const tm = global.MemoriaThemeMode;
    return tm && tm.MODES.indexOf(tm.get()) !== -1 ? tm.get() : "system";
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
    return `<div class="-settings-layout -settings-layout--solo"><div class="-settings-form"><section class="-settings-section">
      <h3 class="-settings-heading">${T("settings.display.themeGroup")}</h3>
      <label class="-settings-field">
        <span>${T("settings.display.themeLabel")}</span>
        <select id="display-theme">
          <option value="system"${themeMode() === "system" ? " selected" : ""}>${T("settings.display.themeSystem")}</option>
          <option value="dark"${themeMode() === "dark" ? " selected" : ""}>${T("settings.display.themeDark")}</option>
          <option value="light"${themeMode() === "light" ? " selected" : ""}>${T("settings.display.themeLight")}</option>
        </select>
      </label>
      <p class="-muted -settings-note">${T("settings.display.themeNote")}</p>
    </section>
    <section class="-settings-section">
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
      ${fontRows(s, T)}
      <p class="-muted -settings-note">${T("settings.display.fontLangNote")}</p>
      <label class="-settings-field">
        <span>${T("settings.display.fontBrandLabel")}</span>
        ${fontSelect('data-display-setting="fontBrand"', s.fontBrand, T("settings.display.fontBrandDefault"))}
      </label>
      <p class="-muted -settings-note">${T("settings.display.fontBrandNote")}</p>
    </section>
    <section class="-settings-section">
      <h3 class="-settings-heading">${T("settings.display.uiScaleGroup")}</h3>
      <p class="-muted -settings-note">${T("settings.display.uiScaleNote")}</p>
      ${rangeField("uiScale", T("settings.display.uiScale"), SCALE_MIN, SCALE_MAX, SCALE_STEP, s.uiScale, T("settings.display.uiScaleHint"))}
      <div class="-settings-actions">
        <button type="button" class="-btn secondary" id="display-ui-scale-reset">${T("settings.display.resetScale")}</button>
      </div>
    </section>${preloadSection(T, s)}</div></div>`;
  }

  function bindSettingsForm(root) {
    if (!root) return;
    root.querySelectorAll("[data-display-setting]").forEach((el) => {
      const key = el.dataset.displaySetting;
      const handler = () => {
        let val = el.type === "checkbox" ? !!el.checked : el.type === "number" ? Number(el.value) : el.value;   // 2026-09-23 追加：勾选框取 checked（`el.value` 恒为 "on"）；2026-09-24 追加：数字框取 Number（性能版块的权重）
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
    // 按语言的字体：每档一个输入框；空值 ⇒ 写空串（`normalizeFonts` 覆盖全部语言 ⇒ 后端浅合并能真正清掉旧值）
    root.querySelectorAll("[data-display-font-lang]").forEach((el) => {
      const code = el.dataset.displayFontLang;
      const handler = () => {
        const fonts = normalizeFonts(load().fonts);
        fonts[code] = String(el.value || "").trim();
        save({ fonts });
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
    const themeSel = root.querySelector("#display-theme");
    if (themeSel && global.MemoriaThemeMode) {
      themeSel.addEventListener("change", () => {
        global.MemoriaThemeMode.set(themeSel.value);
      });
    }
    const langSel = root.querySelector("#display-language");
    if (langSel && global.MemoriaI18n) {
      langSel.addEventListener("change", () => {
        global.MemoriaI18n.setLang(langSel.value);
        // 界面语言变了 ⇒ 正文字体栈的**优先级**要重算（当前语言那档排最前），否则中英档的顺序还停在旧语言
        applyAll();
        if (global.MemoriaGraphSettings && global.MemoriaGraphSettings.rerenderCurrentTab) {
          global.MemoriaGraphSettings.rerenderCurrentTab();
        }
      });
    }
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-23 追加：**按语言的字体**的下拉行（人：「设置中 文字还要添加字体类型，这个字体是 markdown
  //   预览的文字和 agent 对话栏中渲染的文字，还支持修改顶栏 "MEMORIA" 的字体，不同语言可以设置不同字体」）。
  //   一行 = 一种界面语言（`MemoriaI18n.SUPPORTED`，标签直接用 `langDisplay()`），顶栏字标另有一行。
  //   两处都是**下拉**（`<select>`）—— 人 2026-09-23 复审：「你新添加的这些框的 ui 样式违反整体设计……
  //   你应该给下拉可选样式而不是输入」⇒ 走既有的 `.-settings-field select` 规则，外观与「主题/语言」
  //   两个下拉完全一致；首项空值 = 跟随默认，选项来自 `FONT_CHOICES`。
  //   声明写在 `bindSettingsForm` 之后不影响上方的 `renderSettingsBody()`：函数声明会提升。

  /** 一档字体的下拉：首项「默认」（空值），其后是 `FONT_CHOICES`。
   *  **存档值不在候选表里也补进选项并选中** —— 否则旧存档（或手改过的 ui-settings.json）会回显成空白，
   *  看起来像"字体被清掉了"，而 `applyFonts()` 其实仍在用它。 */
  function fontSelect(attrs, value, noneLabel) {
    const cur = String(value || "").trim();
    const names = cur && FONT_CHOICES.indexOf(cur) === -1 ? [cur].concat(FONT_CHOICES) : FONT_CHOICES;
    const options = [`<option value=""${cur ? "" : " selected"}>${esc(noneLabel)}</option>`]
      .concat(names.map((name) => `<option value="${esc(name)}"${name === cur ? " selected" : ""}>${esc(name)}</option>`))
      .join("");
    return `<select ${attrs}>${options}</select>`;
  }

  function fontRows(s, T) {
    const i18n = global.MemoriaI18n;
    return langs()
      .map((code) => {
        const label = i18n && i18n.langDisplay ? i18n.langDisplay(code) : code;
        const value = ((s && s.fonts) || {})[code] || "";
        return `<label class="-settings-field">
        <span>${esc(label)}</span>
        ${fontSelect(`data-display-font-lang="${esc(code)}"`, value, T("settings.display.fontSlotDefault"))}
      </label>`;
      })
      .join("");
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-23 追加：**后台预加载**开关（设置 →「显示」→「性能」子版块）。
  // 人：「出现在页签的文件能不能内存预加载减小切换速度？或者后台提供 后台预加载开关，并且说明更大的
  // 硬件开销和更流畅的体验（推荐大型知识库）」。
  //
  // 分工：本文件只管**字段与持久化**（`DEFAULTS.backgroundPreload` → `pickKnown` → 既有的
  // localStorage `-display-settings` + 磁盘 `ui-settings.json` 的 `display` 段，与字号/字体同一条
  // `save_ui_settings` 通道），生效逻辑全在 app.js 末尾「预览 DOM 缓存 + 后台预渲染」块里；
  // 两边只经 `window.MemoriaApp.setBackgroundPreload(bool)` 这一个门面交互（`applyAll()` 每次设置
  // 变更都会通告一次，函数在开关未变时是空操作）。
  //
  // 声明紧挨在 `global.MemoriaDisplaySettings = {...}` **之前**（与上方 `fontSelect` / `fontRows` 同一手法：
  // 函数声明会提升，`applyAll()` 与 `renderSettingsBody()` 在运行时都能取到），只推动其后的导出行。

  /** 「性能」子版块：后台预加载开关 + **预览池智能替换**的权重 / 公式 / 恢复默认。
   *  用 `<section class="-settings-section">` + `<h3 class="-settings-heading">` 的既有骨架 —— 设置弹窗
   *  打开时 `graph-settings.js::foldSettingsSections()` 会把它与其它页签的版块一起折成可展缩的 `<details>`。
   *  2026-09-24 起下半段（`perfPolicyHtml`）是本文件末尾「性能版块」块声明的：公式里的数字取自
   *  `js/preview-cache-policy.js` 的常量 + **当前生效的权重** ⇒ 面板上看到的就是真正在算的那条式子。 */
  function preloadSection(T, s) {
    return `<section class="-settings-section">
      <h3 class="-settings-heading">${T("settings.display.perfGroup")}</h3>
      <label class="-settings-field -settings-field--inline">
        <input type="checkbox" data-display-setting="backgroundPreload"${s && s.backgroundPreload ? " checked" : ""}>
        <span>${T("settings.display.preloadLabel")}</span>
      </label>
      <p class="-muted -settings-note">${T("settings.display.preloadNote")}${preloadFootprintNote(T)}</p>
      ${perfPolicyHtml(T, s)}
    </section>`;
  }

  /** 说明文案后附一句"当前实际占了多少"（用 app.js 缓存的自身估算口径；未开启或无缓存时不附）。
   *  为什么附实时值：开销是随"缓存了几个页签、各多大"变的常量说明说不准，现场读数最有说服力。 */
  function preloadFootprintNote(T) {
    const app = global.MemoriaApp;
    const stats = app && typeof app.previewCacheStats === "function" ? app.previewCacheStats() : null;
    if (!stats || !stats.enabled || !stats.entries) return "";
    return T("settings.display.preloadFootprint", {
      n: stats.entries,
      mb: (stats.bytes / 1048576).toFixed(1),
    });
  }

  /** 把开关同步给 app.js 的预览预渲染调度器（app.js 缺席时静默跳过：本模块可独立加载）。 */
  function announcePreload(on) {
    const app = global.MemoriaApp;
    if (app && typeof app.setBackgroundPreload === "function") app.setBackgroundPreload(!!on);
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

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-24 追加：「性能」版块的下半段 —— **预览池智能替换**的权重、公式与「恢复默认」。
  //
  // 人：「……一些权重参数应该支持设置内「性能」板块调整，显示计算公式，支持恢复默认」。
  // 分工与上一条「后台预加载」完全同款：**本文件只管字段与持久化**（`PERF_DEFAULTS` → `pickKnown`
  // → 既有的 localStorage + 磁盘 `display` 段同一条 `save_ui_settings` 通道），**算法与生效逻辑**在
  // `js/preview-cache-policy.js`（纯函数）+ `app.js` 末尾「预览池智能替换」块；两边只经
  // `window.MemoriaApp.setPreviewCachePolicy(policy)` 这一个门面交互。
  //
  // **为什么这组声明放在导出行之后**：① `PERF_KEYS` / `clampPerf` 被上面的 `pickKnown`（第 116 行）
  // 引用，而 `pickKnown` 只在 `load()` / `hydrateFromDisk()` 里被调用、都不发生在模块体执行期间
  // ⇒ 跑到那里时本段必然已就绪（用 `var` 而不是 `const`，以防将来有人把它挪到模块体里调用而踩 TDZ）；
  // ② 包装 `bindSettingsForm` 必须发生在**导出之后**（否则包装会被导出对象覆盖）。
  // 函数声明一律提升 ⇒ `preloadSection` 与 `applyAll` 运行时都取得到（与上一条「后台预加载」同一手法）。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 这组键的默认值。**必须与 `js/preview-cache-policy.js::DEFAULTS` 逐字相等**
   *  （有一条跨文件钉子测试逐键核对两边 —— 两处都写其实是"设置侧默认"与"算法侧默认"的边界，改了要一起改）。 */
  var PERF_DEFAULTS = {
    previewCacheMax: 8,
    previewCacheMaxLines: 8000,
    preloadMaxLines: 4000,
    preloadMaxTabs: 8,
    perfTimeWeight: 1.0,
    perfFreqWeight: 0.5,
    perfRecencyWeight: 0.6,
    perfSizeWeight: 0.4,
    perfAgingWeight: 0.05,
    perfHalfLifeH: 12,
    perfAdmission: true,
    // 导航预测器（§3.5）：`markov` = 只用跳转行为训练马尔可夫链（样本不足自动退化为启发式）
    navPredictor: "markov",
    navHalfLifeDays: 14,
  };

  /** 这组键的合法区间（与策略模块的 `RANGES` 同源）。设置侧也夹一次 ⇒ 坏值进不了盘。 */
  var PERF_RANGES = {
    previewCacheMax: [1, 32],
    previewCacheMaxLines: [200, 200000],
    preloadMaxLines: [200, 200000],
    preloadMaxTabs: [1, 64],
    perfTimeWeight: [0, 5],
    perfFreqWeight: [0, 5],
    perfRecencyWeight: [0, 5],
    perfSizeWeight: [0, 5],
    perfAgingWeight: [0, 5],
    perfHalfLifeH: [0.5, 168],
    navHalfLifeDays: [0.5, 365],
  };

  var PERF_KEYS = Object.keys(PERF_DEFAULTS);
  Object.assign(DEFAULTS, PERF_DEFAULTS);   // `DEFAULTS` 是 const 声明的**对象** ⇒ 可变；补键不动上方任何一行

  /** 本段自己的取词（`renderSettingsBody` 里的 `T` 只在那个函数作用域内；导出后拿不到）。 */
  function perfT(key, params) {
    const i18n = global.MemoriaI18n;
    return i18n && typeof i18n.t === "function" ? i18n.t(key, params) : key;
  }

  /** 单键归一：布尔化 / 枚举 / 夹到区间；非法值回落默认（**绝不写怪值**，与算法侧 `sanitize` 同一口径）。 */
  function clampPerf(key, value) {
    if (key === "perfAdmission") return !!value;
    if (key === "navPredictor") {
      // 枚举键：只认 `MemoriaNavModel.MODES`（模块在末尾才加载 ⇒ **调用期**取值，缺席时用同一份字面量兜底）
      const mod = global.MemoriaNavModel;
      const modes = mod && mod.MODES ? mod.MODES : ["off", "markov"];
      const text = String(value == null ? "" : value);
      return modes.indexOf(text) >= 0 ? text : PERF_DEFAULTS.navPredictor;
    }
    const range = PERF_RANGES[key] || [0, 1];
    const n = typeof value === "number" ? value : parseFloat(String(value == null ? "" : value));
    if (!Number.isFinite(n)) return PERF_DEFAULTS[key];
    return Math.min(Math.max(n, range[0]), range[1]);
  }

  /** 数值输入框（既有 `-settings-field` 骨架 + `data-display-setting` ⇒ 走同一条保存链路）。 */
  function perfNumberField(key, T, s) {
    const range = PERF_RANGES[key] || [0, 1];
    const step = key === "previewCacheMax" || key === "preloadMaxTabs" ? 1 : key === "perfHalfLifeH" ? 0.5 : key.endsWith("Lines") ? 500 : 0.05;
    const value = s && s[key] !== undefined ? s[key] : PERF_DEFAULTS[key];
    return `<label class="-settings-field">
      <span>${T("settings.display.perfField." + key)}</span>
      <input type="number" data-display-setting="${key}" min="${range[0]}" max="${range[1]}" step="${step}" value="${value}">
    </label>`;
  }

  /** 公式块：字母是符号，**数字全部取自代码常量 + 当前生效的权重** ⇒ 显示的就是真正在算的那条式子。 */
  function perfFormulaHtml(T, s) {
    const mod = global.MemoriaPreviewPolicy || {};
    const at = (key) => String(s && s[key] !== undefined ? s[key] : PERF_DEFAULTS[key]);
    const line = T("settings.display.perfFormula", {
      wt: at("perfTimeWeight"),
      wf: at("perfFreqWeight"),
      wr: at("perfRecencyWeight"),
      ws: at("perfSizeWeight"),
      wa: at("perfAgingWeight"),
    });
    const terms = T("settings.display.perfFormulaTerms", {
      ref: mod.LOAD_REF_MS || 8000,
      mb: Math.round((mod.BYTES_REF || 4194304) / 1048576),
      cap: mod.AGING_CAP || 20,
      tau: at("perfHalfLifeH"),
    });
    return `<div class="-perf-formula">
      <p class="-muted -settings-note -perf-title">${T("settings.display.perfFormulaTitle")}</p>
      <code class="-perf-formula-line">${line}</code>
      <p class="-muted -settings-note">${terms}</p>
    </div>`;
  }

  /** 「性能」版块的下半段：一组门槛与权重 + 入场闸 + 公式 + **导航预测器** + 现场读数 + 按钮。 */
  function perfPolicyHtml(T, s) {
    const fields = [
      "previewCacheMax",
      "previewCacheMaxLines",
      "preloadMaxLines",
      "preloadMaxTabs",
      "perfTimeWeight",
      "perfFreqWeight",
      "perfRecencyWeight",
      "perfSizeWeight",
      "perfAgingWeight",
      "perfHalfLifeH",
      "navHalfLifeDays",
    ]
      .map((key) => perfNumberField(key, T, s))
      .join("");
    const on = s && s.perfAdmission !== undefined ? !!s.perfAdmission : PERF_DEFAULTS.perfAdmission;
    const navMode = s && s.navPredictor !== undefined ? s.navPredictor : PERF_DEFAULTS.navPredictor;
    const modes = global.MemoriaNavModel && global.MemoriaNavModel.MODES ? global.MemoriaNavModel.MODES : ["off", "markov"];
    const navOptions = modes
      .map((mode) => `<option value="${mode}"${mode === navMode ? " selected" : ""}>${T("settings.display.perfNavMode." + mode)}</option>`)
      .join("");
    return `<p class="-muted -settings-note -perf-title">${T("settings.display.perfPolicyLabel")}</p>
      ${fields}
      <label class="-settings-field -settings-field--inline">
        <input type="checkbox" data-display-setting="perfAdmission"${on ? " checked" : ""}>
        <span>${T("settings.display.perfField.perfAdmission")}</span>
      </label>
      <p class="-muted -settings-note">${T("settings.display.perfAdmissionNote")}</p>
      ${perfFormulaHtml(T, s)}
      <label class="-settings-field">
        <span>${T("settings.display.perfField.navPredictor")}</span>
        <select data-display-setting="navPredictor">${navOptions}</select>
      </label>
      <p class="-muted -settings-note">${T("settings.display.perfNavNote")}</p>
      <p class="-muted -settings-note -perf-title">${T("settings.display.perfLiveTitle")}</p>
      <div class="-perf-live" data-perf-live>${perfLiveHtml(T)}</div>
      <div class="-settings-actions">
        <button type="button" class="-btn secondary" data-perf-refresh>${T("settings.display.perfRefresh")}</button>
        <button type="button" class="-btn secondary" data-perf-reset>${T("settings.display.perfReset")}</button>
        <button type="button" class="-btn secondary" data-nav-reset>${T("settings.display.perfNavReset")}</button>
      </div>`;
  }

  /** 读数里的用户可控文本（路径）做最小转义 —— 别让文件名里的尖括号变成标签。 */
  function perfEsc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /** **现场读数**：最近一次切页签的耗时与是否命中 + 池内逐条分数（含路径）+ 三个生效门槛。
   *  为什么给读数：门槛/权重的效果只能靠现场数字判断 —— 真机反馈"教材第 8 章切得慢"就是靠
   *  "它到底进没进池、分多少"定位的（第 8 章 3983 行 > 当时 1200 行的预渲染上限 ⇒ 从未被预渲染）。 */
  function perfLiveHtml(T) {
    const app = global.MemoriaApp;
    if (!app || typeof app.previewCacheScores !== "function") return T("settings.display.perfLiveNone");
    let data = null;
    try { data = app.previewCacheScores(); } catch (_) { data = null; }
    if (!data) return T("settings.display.perfLiveNone");
    const lim = data.limits && typeof data.limits === "object" ? data.limits : {};
    const lines = [
      T("settings.display.perfLiveLast", {
        js: Math.round(Number(data.lastSwitchMs) || 0), paint: (data.lastSwitchAsync && typeof data.lastSwitchAsync.paint === "number") ? Math.round(data.lastSwitchAsync.paint) : "—",   // 2026-09-24：**脚本耗时 ≠ 体感**（真机读数：脚本 335 ms 而画面 1788 ms，人反馈"和实际感受不一致"）⇒ 两个都摊开
        how: data.lastSwitchHit ? T("settings.display.perfLiveHit") : T("settings.display.perfLiveMiss"),
      }),
      T("settings.display.perfLiveLimits", {
        pool: data.limit || 0,
        cacheLines: lim.cacheLines || 0,
        preloadLines: lim.preloadLines || 0,
        done: lim.preloadDone || 0,
        tabs: lim.preloadTabs || 0,
        evicts: data.evicts || 0,
      }),
    ];
    const rows = Array.isArray(data.rows) ? data.rows : [];
    if (!rows.length) lines.push(T("settings.display.perfLiveEmpty"));
    else {
      rows.forEach((row) => {
        lines.push(
          T("settings.display.perfLiveRow", {
            path: perfEsc(row.path),
            score: (Number(row.score) || 0).toFixed(2),
            hits: row.hits || 0,
            idle: (Number(row.idleH) || 0).toFixed(1),
            load: (Number(row.t) || 0).toFixed(2),
          })
        );
      });
    }
    // 导航模型（§3.5）：节点/边/样本数 + 预渲染命中率（"我们猜的下一个"到底猜中过几次）
    const nav = data.nav && typeof data.nav === "object" ? data.nav : null;
    if (nav) {
      lines.push(
        T("settings.display.perfLiveNav", {
          nodes: nav.nodes || 0,
          edges: nav.edges || 0,
          samples: nav.samples || 0,
          min: nav.minSamples || 0,
          rate: Math.round((Number(nav.hitRate) || 0) * 100),
          hits: nav.hits || 0,
          misses: nav.misses || 0,
        })
      );
    }
    // 全程五阶段（绝对增量 ⇒ 这里两两相减，得到每段自己的耗时）：stash · load · editor · view · tail
    if (data.lastSwitchPhases && typeof data.lastSwitchPhases === "object") {
      const ph = data.lastSwitchPhases;
      let prev = 0;
      const list = [];
      for (const key of PERF_PHASE_ORDER) {
        if (typeof ph[key] !== "number") continue;
        list.push(key + " " + (ph[key] - prev));
        prev = ph[key];
      }
      if (list.length) lines.push(T("settings.display.perfLivePhases", { list: list.join(" · ") }));
    }
    // 命中恢复的**分段耗时**（增量 ms）：直接指出那几百毫秒花在哪一段（attach / wikilinks / mermaid / scroll …）
    if (data.lastSwitchHit && data.lastSwitchParts && typeof data.lastSwitchParts === "object") {
      const parts = data.lastSwitchParts;
      const list = Object.keys(parts).map((key) => key + " " + parts[key]).join(" · ");
      if (list) lines.push(T("settings.display.perfLiveParts", { list: list }));
    }
    // **异步**标记（相对本次切换起点 ms）：`paint` = 双 rAF（画面真的更新了）/ `mathjax` = 排版跑完
    if (data.lastSwitchAsync && typeof data.lastSwitchAsync === "object") {
      const asyncMarks = data.lastSwitchAsync;
      const list = Object.keys(asyncMarks).map((key) => key + " " + asyncMarks[key]).join(" · ");
      if (list) lines.push(T("settings.display.perfLiveAsync", { list: list }));
    }
    // **窗口化调试**（2026-09-24 AG76；人：「仍然无法滚动，要调试日志」）⇒ 两行：
    // 计数行（`wheel` 到了没 / `scrolls` 滚了没 / `fallback` 原生滚动生效没 / `max` 能不能滚 / 跳转锚点命中没）
    // + 轨迹行（最近 8 条：`attach` / `anchorLine` / `move` / `wheel`）。
    const win = data.win && typeof data.win === "object" ? data.win : null;
    if (win) {
      lines.push(T("settings.display.perfLiveWin", {
        attach: win.attach || 0, skip: win.skip || "—",
        wheel: win.wheel || 0, scrolls: win.scrolls || 0, fb: win.fallback || 0,
        from: win.from, to: win.to, slots: win.slots, shown: win.shown,
        top: win.top, max: win.max, line: win.anchorLine || 0, jump: win.jumpIdx,
      }));
      lines.push(T("settings.display.perfLiveWinLog", {
        list: (Array.isArray(win.log) && win.log.length) ? win.log.join(" · ") : "—",
      }));
      // **编辑路径读数**（人 2026-09-24：「按回车会卡顿一下，现在添加日志我们集中精力优化这个」）：
      //   等待（去抖+事件循环被占）/ 全量重渲染（同步 parse+render+stamp）/ 接管 / 补链接 / 排版（异步）
      const ed = win.edit && typeof win.edit === "object" ? win.edit : null;
      if (ed && ed.n) {
        lines.push(T("settings.display.perfLiveEdit", {
          n: ed.n, wait: ed.wait || 0, render: ed.render || 0, attach: ed.attach || 0,
          links: ed.links || 0, math: ed.math || 0,
        }));
      }
      // **渲染分段**（人 2026-09-24：`postRender 26679 / 58698` 只说明"卡在 renderPreview 里"，需要看到里面哪一步）
      //   ⚠️ 优先显示 **`rpWorst`（最慢那一次）**：编辑会把"最近一次"覆盖掉，而要看的是那个几十秒的冷渲染。
      const rp = win.rp && typeof win.rp === "object" ? win.rp : null;
      const rpWorst = win.rpWorst && typeof win.rpWorst === "object" ? win.rpWorst : null;
      const useWorst = !!(rpWorst && rpWorst.parts && (rpWorst.total || 0) > ((rp && rp.parts && (rp.parts.audit || rp.parts.mjStart)) || 0));
      const use = useWorst ? rpWorst : rp;
      if (use && use.parts && Object.keys(use.parts).length) {
        const rlist = [];
        for (const key of PERF_RENDER_ORDER) {
          if (typeof use.parts[key] !== "number") continue;
          rlist.push(T("settings.display.perfRenderPart." + key) + " " + use.parts[key]);
        }
        if (rlist.length) lines.push(T("settings.display.perfLiveRender", { total: use.parts.audit || use.parts.mjStart || 0, list: rlist.join(" · ") }));
      }
      // **位置漂移读数**（人 2026-09-24：「我每次回车画面都往上跑」）——
      //   渲染前 → 渲染后 的 `scrollTop` 差、会话累计、以及 `_move` 里补偿的合计。
      const dr = win.drift && typeof win.drift === "object" ? win.drift : null;
      if (dr && dr.n) {
        const sign = (v) => (v > 0 ? "+" : "") + perfCount(v);
        lines.push(T("settings.display.perfLiveDrift", {
          n: dr.n, before: perfCount(dr.before), after: perfCount(dr.after),
          delta: sign(dr.delta), sum: sign(dr.sum), comp: sign(dr.comp), line: dr.line || 0, off: dr.off || 0,
        }));
      }
    }
    // 池占用（**实测节点数**）⇒ 直接回答"要不要改缓存形态"：活 DOM 区间 vs 序列化 HTML 区间（设计 §3.3 第一组数）
    const pool = data.pool && typeof data.pool === "object" ? data.pool : null;
    if (pool) {
      const mod = global.MemoriaPreviewPolicy;
      const band = mod && typeof mod.estimateBand === "function" ? mod.estimateBand(pool.nodes, pool.chars) : null;
      lines.push(
        T("settings.display.perfLivePool", {
          entries: pool.entries || 0,
          nodes: perfCount(pool.nodes),
          chars: perfCount(pool.chars),
          est: perfMB(pool.bytes),
          live: band ? perfMB(band.live[0]) + " – " + perfMB(band.live[1]) : "—",
          html: band ? perfMB(band.html[0]) + " – " + perfMB(band.html[1]) : "—",
          ast: perfCount(pool.astBlocks),
        })
      );
    }
    // 滞留清理（切换文件后按新候选集比对删除的投机条目数）
    if (typeof data.stalePruned === "number") {
      lines.push(T("settings.display.perfLiveStale", { n: data.stalePruned }));
    }
    return lines.map((line) => `<div class="-perf-live-line">${line}</div>`).join("");
  }

  /** 「全程阶段」的固定顺序（读数要两两相减 ⇒ 顺序必须与 `app.js` 里 `_markPhase` 的调用次序一致）。
   *  2026-09-24 加 `rpEnd`：它打在 `setViewMode` 里（`app.js` 文件里位置更靠后，但**执行时在 `render` 之前**）
   *  ⇒ 不能按"源码出现顺序"推断，测试改成逐字核对本清单。作用是把 `render` 那一段从中间切开：
   *  `editor→postRender` = 冷渲染整条流水线（parse→render→插 DOM→stamp→静态收尾），`postRender→rpEnd` = `attach`（窗口化，含它自己那点几何读），`rpEnd→render` 应≈0；**命中路径没有 `postRender`**（那段整段跳过）⇒ 读数侧跳过缺的键，两两相减仍成立。 */
  var PERF_PHASE_ORDER = ["stash", "load", "editor", "viewIn", "viewPre", "postRender", "rpEnd", "render", "settle", "tail"];
  var PERF_RENDER_ORDER = ["entry", "parse", "dom", "stamp", "mermaid", "mjStart", "audit"];   // `renderPreview()` 内部分段（跨文件顺序钉子核对，同 `PERF_PHASE_ORDER`）

  /** 千分位（读数用；没有 `toLocaleString` 就退回原值）。 */
  function perfCount(value) {
    const n = Math.round(Number(value) || 0);
    return typeof n.toLocaleString === "function" ? n.toLocaleString("en-US") : String(n);
  }

  /** 字节 → "X.X MB" / "X KB"（读数用；估算值不需要更高精度）。 */
  function perfMB(bytes) {
    const n = Math.max(0, Number(bytes) || 0);
    if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
    if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
    return Math.round(n) + " B";
  }

  /** 刷新读数：只换读数容器的 **innerHTML**（按钮在容器外 ⇒ 不会连带丢掉监听器）。 */
  function refreshPerfLive(root) {
    const box = root && root.querySelector("[data-perf-live]");
    if (box) box.innerHTML = perfLiveHtml(perfT);
  }

  /** 「恢复默认」：**只重置这一组键**（不动字号 / 缩放 / 字体 / 后台预加载开关）。 */
  function resetPerfDefaults(root) {
    const next = {};
    for (const key of PERF_KEYS) next[key] = PERF_DEFAULTS[key];
    save(next);   // 走同一条 `save` ⇒ 本地即时 + 磁盘去抖 + `applyAll()` 通告新策略
    if (!root) return;
    // 就地回填控件值（**不重渲染**：重渲染会丢监听器，重绑又会叠出重复 handler）
    for (const key of PERF_KEYS) {
      const el = root.querySelector('[data-display-setting="' + key + '"]');
      if (!el) continue;
      if (el.type === "checkbox") el.checked = !!next[key];
      else el.value = String(next[key]);
    }
    const formula = root.querySelector(".-perf-formula");
    if (formula) formula.outerHTML = perfFormulaHtml(perfT, next);   // 公式里含权重 ⇒ 换掉（块内无控件，不需重绑）
  }

  /** 把这组键（缺失即默认）通告给 app.js；策略模块缺席时直接给原始对象，由 app.js 自行兜底。 */
  function announcePerfPolicy(s) {
    const app = global.MemoriaApp;
    if (!app || typeof app.setPreviewCachePolicy !== "function") return;
    const src = {};
    for (const key of PERF_KEYS) src[key] = s && s[key] !== undefined ? s[key] : PERF_DEFAULTS[key];
    const mod = global.MemoriaPreviewPolicy;
    app.setPreviewCachePolicy(mod ? mod.sanitize(src) : src);
  }

  /** 清空导航模型（**可再生缓存**，清了只损失一点预测质量 ⇒ 不做二次确认，但给回执）。 */
  function resetNavModel() {
    const nav = global.MemoriaNavPredictor;
    if (!nav || typeof nav.clearModel !== "function") return;
    Promise.resolve(nav.clearModel()).then(function () {
      const info = global.MemoriaApp && global.MemoriaApp.showFlashInfo;
      if (info) info(perfT("settings.display.perfNavResetDone"));
    }).catch(function () { /* 缓存清不掉不影响使用 */ });
  }

  /** 绑定「刷新读数」「恢复默认」「清空导航模型」三个按钮（在既有 `bindSettingsForm` **之后**跑 ⇒ 不改中段）。 */
  function bindPerfExtra(root) {
    if (!root) return;
    const refresh = root.querySelector("[data-perf-refresh]");
    if (refresh) refresh.addEventListener("click", function () { refreshPerfLive(root); });
    const reset = root.querySelector("[data-perf-reset]");
    if (reset) reset.addEventListener("click", function () { resetPerfDefaults(root); });
    const navReset = root.querySelector("[data-nav-reset]");
    if (navReset) navReset.addEventListener("click", function () { resetNavModel(); refreshPerfLive(root); });
  }

  var _bindSettingsFormBase = global.MemoriaDisplaySettings.bindSettingsForm;
  global.MemoriaDisplaySettings.bindSettingsForm = function (root) {
    _bindSettingsFormBase(root);
    bindPerfExtra(root);
  };
})(window);
