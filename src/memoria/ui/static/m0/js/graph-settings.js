/**
 * 图谱设置：localStorage + 磁盘持久化、设置弹窗、侧栏分割
 */
(function (global) {
  "use strict";

  const STORAGE_KEY = "m0-graph-settings";
  const PREVIEW_H_KEY = "m0-settings-preview-h";

  const DEFAULTS = {
    labelMode: "name_short",
    labelMaxLen: 8,
    linkDistance: 108,
    linkStrength: 0.28,
    repulsion: 5200,
    centerStrength: 0.006,
    velocityDecay: 0.8,
    warmupTicks: 160,
    arrowSize: 7,
    nodeRadius: 6,
    spreadFactor: 0.42,
    groupLabelMode: "hub_name",
    groupLabelMaxLen: 12,
    groupSpacing: 260,
    alphaMin: 0.012,
    alphaDecay: 0.045,
    alphaTarget: 0.12,
    dragReheat: 0.28,
    dragReleaseReheat: 0.2,
  };

  const SPLIT_DEFAULTS = {
    files: 0.55,
    graph2d: 0.82,
    graph3d: 0.72,
  };

  const LEGACY_SPLIT_KEY = "m0-graph-sidebar-nav-kp-split";

  const SAMPLE_GRAPH = {
    nodes: [
      {
        id: "rl-overview",
        name: "RL 概览",
        label: "RL 概览",
        file: "knowledge/rl-overview.md",
        description: "子目录示例 — 学习路径概览",
        range_ok: true,
      },
      {
        id: "mdp",
        name: "马尔可夫决策过程",
        label: "马尔可夫决策过程",
        file: "mdp.md",
        description: "强化学习的数学基础框架",
        range_ok: true,
      },
      {
        id: "贝尔曼方程",
        name: "贝尔曼方程",
        label: "贝尔曼方程",
        file: "mdp.md",
        range_ok: true,
      },
      {
        id: "q-learning",
        name: "Q-Learning",
        label: "Q-Learning",
        file: "q-learning.md",
        range_ok: true,
      },
      {
        id: "policy-gradient",
        name: "策略梯度",
        label: "策略梯度",
        file: "policy-gradient.md",
        range_ok: true,
      },
    ],
    edges: [
      {
        type: "reference",
        source_id: "rl-overview",
        targets: ["mdp", "贝尔曼方程"],
        relevance: 0.85,
      },
      { type: "extend", source_id: "mdp", targets: ["q-learning"], relevance: 0.6 },
      {
        type: "reference",
        source_id: "q-learning",
        targets: ["policy-gradient"],
        relevance: 0.7,
      },
    ],
  };

  let settingsTab = "graph2d";
  let previewEngine = null;
  let previewLayout = null;
  let previewView = null;
  let onChangeHandler = null;
  let diskPrefs = null;
  let diskSaveTimer = null;
  const sidebarSplitState = { tab: "files", ratio: SPLIT_DEFAULTS.files };

  function api() {
    return global.MemoriaBridge && global.MemoriaBridge.api();
  }

  function readLocalGraph() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function writeLocalGraph(graph) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(graph));
    } catch (_) {
      /* ignore */
    }
  }

  function load() {
    const merged = { ...DEFAULTS, ...readLocalGraph(), ...(diskPrefs?.graph || {}) };
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
    const payload = {
      graph: load(),
      sidebarSplit: { ...(diskPrefs?.sidebarSplit || {}), ...readSidebarSplitCache() },
      settingsPreviewH: readPreviewHeight(),
    };
    if (global.MemoriaCheckSettings) {
      payload.check = global.MemoriaCheckSettings.load();
    }
    if (global.MemoriaSearchSettings) {
      const search = global.MemoriaSearchSettings.load();
      payload.search = {
        embedding_enabled: !!search.embeddingEnabled,
        search_modes: search.searchModes || "lexical",
        body_locate_enabled: !!search.bodyLocateEnabled,
      };
    }
    a.save_ui_settings(payload).catch(() => {});
  }

  function readSidebarSplitCache() {
    const out = {};
    for (const tab of Object.keys(SPLIT_DEFAULTS)) {
      const v = parseFloat(localStorage.getItem(splitStorageKey(tab)));
      if (Number.isFinite(v)) out[tab] = v;
    }
    return out;
  }

  function readPreviewHeight() {
    const v = parseInt(localStorage.getItem(PREVIEW_H_KEY), 10);
    return Number.isFinite(v) ? v : null;
  }

  async function hydrateFromDisk() {
    const a = api();
    if (!a?.get_ui_settings) return load();
    try {
      const res = await a.get_ui_settings();
      if (res?.status !== "ok" || !res.settings) return load();
      diskPrefs = res.settings;
      if (diskPrefs.graph && typeof diskPrefs.graph === "object") {
        writeLocalGraph({ ...readLocalGraph(), ...diskPrefs.graph });
      }
      const splits = diskPrefs.sidebarSplit;
      if (splits && typeof splits === "object") {
        for (const [tab, ratio] of Object.entries(splits)) {
          if (SPLIT_DEFAULTS[tab] != null && Number.isFinite(Number(ratio))) {
            localStorage.setItem(splitStorageKey(tab), String(ratio));
          }
        }
      }
      if (Number.isFinite(diskPrefs.settingsPreviewH)) {
        localStorage.setItem(PREVIEW_H_KEY, String(diskPrefs.settingsPreviewH));
      }
      notifyChange();
      return load();
    } catch (_) {
      return load();
    }
  }

  function save(partial) {
    const next = { ...load(), ...partial };
    writeLocalGraph(next);
    diskPrefs = diskPrefs || {};
    diskPrefs.graph = { ...(diskPrefs.graph || {}), ...next };
    scheduleDiskSave();
    notifyChange();
    return next;
  }

  function reset() {
    localStorage.removeItem(STORAGE_KEY);
    if (diskPrefs) diskPrefs.graph = { ...DEFAULTS };
    for (const tab of Object.keys(SPLIT_DEFAULTS)) {
      localStorage.removeItem(splitStorageKey(tab));
    }
    if (diskPrefs) diskPrefs.sidebarSplit = { ...SPLIT_DEFAULTS };
    if (global.MemoriaCheckSettings) global.MemoriaCheckSettings.reset();
    scheduleDiskSave();
    notifyChange();
    return { ...DEFAULTS };
  }

  function getLabelSettings() {
    const s = load();
    return { labelMode: s.labelMode, labelMaxLen: s.labelMaxLen };
  }

  function getViewOptions() {
    const s = load();
    return {
      labelMode: s.labelMode,
      labelMaxLen: s.labelMaxLen,
      linkDistance: s.linkDistance,
      linkStrength: s.linkStrength,
      repulsion: s.repulsion,
      centerStrength: s.centerStrength,
      velocityDecay: s.velocityDecay,
      warmupTicks: s.warmupTicks,
      arrowSize: s.arrowSize,
      nodeRadius: s.nodeRadius,
      spreadFactor: s.spreadFactor,
      groupLabelMode: s.groupLabelMode,
      groupLabelMaxLen: s.groupLabelMaxLen,
      groupSpacing: s.groupSpacing,
      alphaMin: s.alphaMin,
      alphaDecay: s.alphaDecay,
      alphaTarget: s.alphaTarget,
      dragReheat: s.dragReheat,
      dragReleaseReheat: s.dragReleaseReheat,
    };
  }

  function onChange(fn) {
    onChangeHandler = fn;
  }

  function notifyChange() {
    syncFormFromSettings();
    refreshPreview();
    if (onChangeHandler) onChangeHandler(getViewOptions());
  }

  function syncFormFromSettings() {
    const s = load();
    const root = document.getElementById("settings-body");
    if (!root) return;
    root.querySelectorAll("[data-graph-setting]").forEach((el) => {
      const key = el.dataset.graphSetting;
      if (key == null || s[key] === undefined) return;
      if (el.type === "range") {
        el.value = String(s[key]);
        const out = root.querySelector(`[data-graph-setting-value="${key}"]`);
        if (out) out.textContent = String(s[key]);
      } else if (el.tagName === "SELECT") {
        el.value = String(s[key]);
      }
    });
  }

  function teardownPreview() {
    stopPreview();
    if (previewView) previewView.destroy();
    previewEngine = null;
    previewLayout = null;
    previewView = null;
  }

  const SPLIT_MIN_TOP = 100;
  const SPLIT_MIN_BOTTOM = 72;
  const SPLIT_RESIZER_H = 6;

  function splitStorageKey(tab) {
    return `m0-sidebar-split-${tab}`;
  }

  function loadGraphSplit(tab) {
    const key = tab || sidebarSplitState.tab;
    const fromDisk = diskPrefs?.sidebarSplit?.[key];
    if (Number.isFinite(fromDisk) && fromDisk >= 0.35 && fromDisk <= 0.92) {
      return fromDisk;
    }
    let v = parseFloat(localStorage.getItem(splitStorageKey(key)));
    if (!Number.isFinite(v) && key === "graph2d") {
      v = parseFloat(localStorage.getItem(LEGACY_SPLIT_KEY));
    }
    const def = SPLIT_DEFAULTS[key] ?? 0.6;
    if (Number.isFinite(v) && v >= 0.35 && v <= 0.92) return v;
    return def;
  }

  function saveGraphSplit(tab, ratio) {
    const key = tab || sidebarSplitState.tab;
    localStorage.setItem(splitStorageKey(key), String(ratio));
    diskPrefs = diskPrefs || {};
    diskPrefs.sidebarSplit = { ...(diskPrefs.sidebarSplit || {}), [key]: ratio };
    scheduleDiskSave();
  }

  function resetGraph2dInternalLayout() {
    const roots = ["graph-2d-root", "graph-3d-root"];
    const hints = ["graph-2d-hint", "graph-3d-hint"];
    for (const id of roots) {
      const root = document.getElementById(id);
      if (root) {
        root.style.flex = "";
        root.style.height = "";
      }
    }
    for (const id of hints) {
      const hint = document.getElementById(id);
      if (hint) {
        hint.style.flex = "";
        hint.style.height = "";
      }
    }
  }

  /** 上=文件树/图谱/3D，下=知识点列表 */
  function applySidebarNavKpSplit(split, onResize) {
    const container = document.getElementById("sidebar-body-split");
    const top = document.getElementById("sidebar-nav-panel");
    const bottom = document.getElementById("sidebar-kp-block");
    if (!container || !top || !bottom) return;
    const ch = container.clientHeight;
    if (ch <= 0) return;
    resetGraph2dInternalLayout();
    const maxTop = ch - SPLIT_MIN_BOTTOM - SPLIT_RESIZER_H;
    const topH = Math.round(
      Math.max(SPLIT_MIN_TOP, Math.min(maxTop, ch * split))
    );
    const bottomH = Math.max(SPLIT_MIN_BOTTOM, ch - topH - SPLIT_RESIZER_H);
    top.style.flex = "none";
    top.style.height = `${topH}px`;
    bottom.style.flex = "none";
    bottom.style.height = `${bottomH}px`;
    if (onResize) onResize();
  }

  function clearSidebarNavKpSplit() {
    const top = document.getElementById("sidebar-nav-panel");
    const bottom = document.getElementById("sidebar-kp-block");
    if (top) {
      top.style.flex = "";
      top.style.height = "";
    }
    if (bottom) {
      bottom.style.flex = "";
      bottom.style.height = "";
    }
    resetGraph2dInternalLayout();
  }

  function applyStoredPanelHeight(targetId, storageKey, min, max) {
    const el = document.getElementById(targetId);
    if (!el) return;
    let v = parseInt(localStorage.getItem(storageKey), 10);
    if (!Number.isFinite(v) && Number.isFinite(diskPrefs?.settingsPreviewH)) {
      v = diskPrefs.settingsPreviewH;
    }
    if (Number.isFinite(v)) {
      v = Math.max(min, Math.min(max, v));
      el.style.height = `${v}px`;
      el.style.flex = "none";
    } else {
      el.style.height = "";
      el.style.flex = "";
    }
  }

  function bindVerticalResize(handle, target, opts = {}) {
    if (!handle || !target || handle.dataset.resizeBound === "1") return;
    handle.dataset.resizeBound = "1";
    const { storageKey, min = 120, max = 600, onResize } = opts;
    let active = false;
    let sy = 0;
    let sh = 0;

    handle.addEventListener("pointerdown", (e) => {
      active = true;
      sy = e.clientY;
      sh = target.offsetHeight;
      target.style.flex = "none";
      handle.classList.add("dragging");
      handle.setPointerCapture(e.pointerId);
      e.preventDefault();
    });

    const finish = (e) => {
      if (!active) return;
      active = false;
      handle.classList.remove("dragging");
      try {
        handle.releasePointerCapture(e.pointerId);
      } catch (_) {
        /* ignore */
      }
      if (storageKey) {
        const h = target.offsetHeight;
        localStorage.setItem(storageKey, String(h));
        diskPrefs = diskPrefs || {};
        diskPrefs.settingsPreviewH = h;
        scheduleDiskSave();
      }
      if (onResize) onResize();
    };

    handle.addEventListener("pointermove", (e) => {
      if (!active) return;
      const nh = Math.max(min, Math.min(max, sh + (e.clientY - sy)));
      target.style.height = `${nh}px`;
      if (onResize) onResize();
    });
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  }

  function bindPreviewResize() {
    applyStoredPanelHeight("graph-settings-preview-wrap", PREVIEW_H_KEY, 140, 520);
    bindVerticalResize(
      document.getElementById("graph-settings-preview-resizer"),
      document.getElementById("graph-settings-preview-wrap"),
      {
        storageKey: PREVIEW_H_KEY,
        min: 140,
        max: 520,
        onResize: () => previewView?.reflow?.(),
      }
    );
  }

  function refreshPreview() {
    if (!previewEngine || !previewView) return;
    previewLayout?.applyOptions(getViewOptions(), { relayout: true });
    previewView.applyOptions(getViewOptions(), { relayout: false });
  }

  function stopPreview() {
    previewView?.stop();
    previewLayout?.stop();
  }

  function renderLabelSection(s) {
    const modes = MemoriaGraphLabels.LABEL_MODES;
    const modeOptions = Object.entries(modes)
      .map(
        ([id, meta]) =>
          `<option value="${id}"${!meta.available ? " disabled" : ""}${s.labelMode === id ? " selected" : ""}>${meta.label}</option>`
      )
      .join("");
    return `<section class="m0-settings-section">
            <h3 class="m0-settings-heading">节点标签</h3>
            <p class="m0-muted m0-settings-note">画布上为<strong>短标签</strong>；悬停侧栏/预览区显示 ID、文件与说明。智能摘要留待 M4 检索引擎。</p>
            <label class="m0-settings-field">
              <span>显示策略</span>
              <select data-graph-setting="labelMode">${modeOptions}</select>
            </label>
            <label class="m0-settings-field">
              <span>缩短字数 <output data-graph-setting-value="labelMaxLen">${s.labelMaxLen}</output></span>
              <input type="range" data-graph-setting="labelMaxLen" min="4" max="20" step="1" value="${s.labelMaxLen}">
            </label>
          </section>`;
  }

  function renderLayoutSection(s, title, includeArrow) {
    const arrow = includeArrow
      ? rangeField("arrowSize", "箭头大小", 4, 12, 1, s.arrowSize)
      : "";
    return `<section class="m0-settings-section">
            <h3 class="m0-settings-heading">${title}</h3>
            <p class="m0-muted m0-settings-note">力导向参数；2D/3D 各自独立布局，参数名共用。</p>
            ${rangeField("linkDistance", "边长", 60, 200, 4, s.linkDistance)}
            ${rangeField("repulsion", "斥力", 2000, 9000, 200, s.repulsion)}
            ${rangeField("linkStrength", "边拉力", 0.08, 0.6, 0.02, s.linkStrength, true)}
            ${rangeField("centerStrength", "向心力", 0, 0.05, 0.002, s.centerStrength, true)}
            ${rangeField("spreadFactor", "初始散布", 0.2, 0.55, 0.02, s.spreadFactor, true)}
            ${rangeField("nodeRadius", "节点半径", 4, 12, 1, s.nodeRadius)}
            ${arrow}
            <p class="m0-muted m0-settings-note">模拟 Alpha：余温、衰减与拖拽加热。</p>
            ${rangeField("alphaMin", "最低 alpha", 0.002, 0.05, 0.001, s.alphaMin, true, 3)}
            ${rangeField("alphaDecay", "衰减率", 0.01, 0.12, 0.005, s.alphaDecay, true, 3)}
            ${rangeField("alphaTarget", "初始余温", 0.05, 0.5, 0.01, s.alphaTarget, true)}
            ${rangeField("dragReheat", "拖拽加热", 0.1, 0.6, 0.02, s.dragReheat, true)}
            ${rangeField("dragReleaseReheat", "松手加热", 0.05, 0.5, 0.02, s.dragReleaseReheat, true)}
          </section>`;
  }

  function renderGroupTabSection(s) {
    return `<section class="m0-settings-section">
            <h3 class="m0-settings-heading">节点群页签</h3>
            <p class="m0-muted m0-settings-note">并查集闭包分量；侧栏第二行页签对 2D/3D 通用。M4 可接入智能命名与排序。</p>
            <label class="m0-settings-field">
              <span>页签命名</span>
              <select data-graph-setting="groupLabelMode">
                <option value="hub_name"${s.groupLabelMode === "hub_name" ? " selected" : ""}>Hub 名称</option>
                <option value="hub_id"${s.groupLabelMode === "hub_id" ? " selected" : ""}>Hub ID</option>
                <option value="smart" disabled>智能命名（M4 占位）</option>
              </select>
            </label>
            ${rangeField("groupLabelMaxLen", "页签最大字数", 6, 20, 1, s.groupLabelMaxLen)}
            ${rangeField("groupSpacing", "「全部」群间距", 160, 420, 20, s.groupSpacing)}
            <label class="m0-settings-field">
              <span>群页签排序</span>
              <select disabled title="M4 占位">
                <option>按规模（默认）</option>
              </select>
            </label>
            <label class="m0-settings-field m0-settings-field--placeholder">
              <span>隐藏单节点群页签</span>
              <input type="checkbox" disabled title="后续版本">
            </label>
          </section>`;
  }

  function renderPreviewColumn(hintText) {
    return `<div class="m0-settings-preview-col">
          <h3 class="m0-settings-heading">示例预览</h3>
          <div class="m0-settings-preview-stack">
            <div id="graph-settings-preview-wrap" class="m0-graph-settings-preview-wrap">
              <div id="graph-settings-preview" class="m0-graph-settings-preview"></div>
              <div id="graph-settings-preview-hint" class="m0-graph-hint m0-graph-hint--overlay m0-graph-settings-preview-hint">
                <span class="m0-muted">${hintText}</span>
              </div>
            </div>
            <div id="graph-settings-preview-resizer" class="m0-graph-panel-resizer" title="拖拽调整预览高度"></div>
          </div>
        </div>`;
  }

  function renderSettingsShell(formSectionsHtml, hintText) {
    return `<div class="m0-settings-layout">
        <div class="m0-settings-form">${formSectionsHtml}</div>
        ${renderPreviewColumn(hintText)}
      </div>`;
  }

  function renderSettingsBody2d() {
    const s = load();
    return renderSettingsShell(
      renderLabelSection(s) + renderLayoutSection(s, "2D 布局", true),
      "悬停节点查看完整信息"
    );
  }

  function renderSettingsBody3d() {
    const s = load();
    return renderSettingsShell(
      renderLabelSection(s) + renderLayoutSection(s, "3D 布局", false),
      "左键旋转 · 滚轮缩放 · 悬停节点查看详情"
    );
  }

  function renderSettingsBodyGroups() {
    const s = load();
    return `<div class="m0-settings-layout m0-settings-layout--solo">
        <div class="m0-settings-form">${renderGroupTabSection(s)}</div>
      </div>`;
  }

  function renderSettingsBody() {
    return renderSettingsBody2d();
  }

  function rangeField(key, label, min, max, step, value, isFloat, decimals) {
    const dec = decimals != null ? decimals : isFloat ? 2 : 0;
    const v = isFloat ? Number(value).toFixed(dec) : value;
    const decAttr = isFloat && decimals != null ? ` data-graph-setting-decimals="${decimals}"` : "";
    return `<label class="m0-settings-field">
      <span>${label} <output data-graph-setting-value="${key}">${v}</output></span>
      <input type="range" data-graph-setting="${key}" min="${min}" max="${max}" step="${step}" value="${value}"${decAttr}>
    </label>`;
  }

  function bindPreviewHoverHint(engine) {
    engine.on("hover", ({ node }) => {
      const hint = document.getElementById("graph-settings-preview-hint");
      if (!hint) return;
      if (!node) {
        hint.innerHTML =
          settingsTab === "graph3d"
            ? '<span class="m0-muted">左键旋转 · 滚轮缩放 · 悬停节点查看详情</span>'
            : '<span class="m0-muted">悬停节点查看完整信息</span>';
        return;
      }
      hint.innerHTML = MemoriaGraphLabels.resolveNodeHoverHtml(node);
    });
  }

  function bootPreview() {
    const root = document.getElementById("graph-settings-preview");
    if (!root) return;
    let attempts = 0;
    const tryBoot = () => {
      if (root.clientWidth > 0 && root.clientHeight > 0) {
        previewView?.reflow?.();
        previewView?.onPanelShown?.();
        previewView?.start?.();
        return;
      }
      attempts += 1;
      if (attempts < 30) {
        requestAnimationFrame(tryBoot);
      }
    };
    requestAnimationFrame(tryBoot);
  }

  function ensurePreview2d() {
    if (
      !window.MemoriaGraphEngine ||
      !window.MemoriaGraphLayout2D ||
      !window.MemoriaGraphView2D
    ) {
      return;
    }
    const root = document.getElementById("graph-settings-preview");
    if (!root) return;
    if (!previewEngine) {
      previewEngine = new MemoriaGraphEngine();
      previewEngine.loadPayload(SAMPLE_GRAPH);
      previewLayout = new MemoriaGraphLayout2D(getViewOptions());
      previewLayout.start();
      previewView = new MemoriaGraphView2D(
        root,
        previewEngine,
        previewLayout,
        getViewOptions()
      );
      bindPreviewHoverHint(previewEngine);
    } else {
      refreshPreview();
    }
    bootPreview();
  }

  function ensurePreview3d() {
    if (
      !window.MemoriaGraphEngine ||
      !window.MemoriaGraphLayout3D ||
      !window.MemoriaGraphView3D ||
      !window.THREE
    ) {
      return;
    }
    const root = document.getElementById("graph-settings-preview");
    if (!root) return;
    if (!previewEngine) {
      previewEngine = new MemoriaGraphEngine();
      previewEngine.loadPayload(SAMPLE_GRAPH);
      previewLayout = new MemoriaGraphLayout3D(getViewOptions());
      previewLayout.start();
      previewView = new MemoriaGraphView3D(
        root,
        previewEngine,
        previewLayout,
        getViewOptions()
      );
      bindPreviewHoverHint(previewEngine);
    } else {
      refreshPreview();
    }
    bootPreview();
  }

  function renderTabsHtml(active) {
    return `<div class="m0-config-tabs" role="tablist">
      <button type="button" class="m0-config-tab${active === "graph2d" ? " active" : ""}" data-settings-tab="graph2d" role="tab">2D 图谱</button>
      <button type="button" class="m0-config-tab${active === "graph3d" ? " active" : ""}" data-settings-tab="graph3d" role="tab">3D 图谱</button>
      <button type="button" class="m0-config-tab${active === "graphGroups" ? " active" : ""}" data-settings-tab="graphGroups" role="tab">节点群页签</button>
      <button type="button" class="m0-config-tab${active === "search" ? " active" : ""}" data-settings-tab="search" role="tab">检索</button>
      <button type="button" class="m0-config-tab${active === "check" ? " active" : ""}" data-settings-tab="check" role="tab">检查</button>
    </div>`;
  }

  function setSettingsTab(tab) {
    settingsTab = tab;
    const tabsEl = document.getElementById("settings-tabs");
    const bodyEl = document.getElementById("settings-body");
    if (!tabsEl || !bodyEl) return;
    tabsEl.innerHTML = renderTabsHtml(tab);
    tabsEl.querySelectorAll("[data-settings-tab]").forEach((btn) => {
      btn.addEventListener("click", () => setSettingsTab(btn.dataset.settingsTab));
    });
    if (tab === "graph2d") {
      teardownPreview();
      bodyEl.innerHTML = renderSettingsBody2d();
      bindSettingsForm(bodyEl);
      bindPreviewResize();
      ensurePreview2d();
    } else if (tab === "graph3d") {
      teardownPreview();
      bodyEl.innerHTML = renderSettingsBody3d();
      bindSettingsForm(bodyEl);
      bindPreviewResize();
      ensurePreview3d();
    } else if (tab === "graphGroups") {
      teardownPreview();
      stopPreview();
      bodyEl.innerHTML = renderSettingsBodyGroups();
      bindSettingsForm(bodyEl);
    } else if (tab === "check" && global.MemoriaCheckSettings) {
      teardownPreview();
      stopPreview();
      bodyEl.innerHTML = global.MemoriaCheckSettings.renderSettingsBody();
      global.MemoriaCheckSettings.bindSettingsForm(bodyEl);
    } else if (tab === "search" && global.MemoriaSearchSettings) {
      teardownPreview();
      stopPreview();
      bodyEl.innerHTML = global.MemoriaSearchSettings.renderSettingsBody();
      global.MemoriaSearchSettings.bindSettingsForm(bodyEl);
    }
  }

  function bindSettingsForm(root) {
    root.querySelectorAll("[data-graph-setting]").forEach((el) => {
      const key = el.dataset.graphSetting;
      const handler = () => {
        let val = el.value;
        if (el.type === "range") {
          val =
            el.step && String(el.step).includes(".")
              ? parseFloat(val)
              : parseInt(val, 10);
          const out = root.querySelector(`[data-graph-setting-value="${key}"]`);
          if (out) {
            const dec = el.dataset.graphSettingDecimals;
            out.textContent =
              el.step && String(el.step).includes(".")
                ? Number(val).toFixed(dec ? parseInt(dec, 10) : 2)
                : String(val);
          }
        }
        save({ [key]: val });
      };
      el.addEventListener("input", handler);
      el.addEventListener("change", handler);
    });
  }

  function openModal() {
    const modal = document.getElementById("settings-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    setSettingsTab(settingsTab);
    refreshSettingsPathHint();
  }

  async function refreshSettingsPathHint() {
    const el = document.getElementById("settings-config-path");
    if (!el) return;
    const a = global.MemoriaBridge?.api?.();
    if (!a?.get_ui_settings) {
      el.hidden = true;
      return;
    }
    try {
      const res = await a.get_ui_settings();
      if (res?.status !== "ok") {
        el.hidden = true;
        return;
      }
      const label = res.settings_rel || "config/ui-settings.json";
      el.textContent = `设置保存在程序目录：${label}`;
      el.title = res.settings_file || label;
      el.hidden = false;
    } catch (_) {
      el.hidden = true;
    }
  }

  function closeModal() {
    global.MemoriaSearchSettings?.flushPendingDiskSave?.();
    document.getElementById("settings-modal")?.classList.add("hidden");
    persistToDisk();
    teardownPreview();
  }

  function bindSidebarNavKpSplit(onResize) {
    const container = document.getElementById("sidebar-body-split");
    const handle = document.getElementById("sidebar-nav-kp-resizer");
    if (!container || !handle || handle.dataset.splitBound === "1") return;
    handle.dataset.splitBound = "1";

    let active = false;
    const sync = () => {
      applySidebarNavKpSplit(sidebarSplitState.ratio, onResize);
    };

    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(() => sync());
      ro.observe(container);
    }

    handle.addEventListener("pointerdown", (e) => {
      active = true;
      handle.classList.add("dragging");
      handle.setPointerCapture(e.pointerId);
      e.preventDefault();
    });

    const finish = (e) => {
      if (!active) return;
      active = false;
      handle.classList.remove("dragging");
      try {
        handle.releasePointerCapture(e.pointerId);
      } catch (_) {
        /* ignore */
      }
      saveGraphSplit(sidebarSplitState.tab, sidebarSplitState.ratio);
    };

    handle.addEventListener("pointermove", (e) => {
      if (!active) return;
      const rect = container.getBoundingClientRect();
      const ch = rect.height;
      if (ch <= 0) return;
      const maxTop = ch - SPLIT_MIN_BOTTOM - SPLIT_RESIZER_H;
      const topH = Math.max(
        SPLIT_MIN_TOP,
        Math.min(maxTop, e.clientY - rect.top)
      );
      sidebarSplitState.ratio = topH / ch;
      applySidebarNavKpSplit(sidebarSplitState.ratio, onResize);
    });
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  }

  function refreshSidebarNavKpSplit(tab, onResize) {
    sidebarSplitState.tab = tab || "files";
    sidebarSplitState.ratio = loadGraphSplit(sidebarSplitState.tab);
    applySidebarNavKpSplit(sidebarSplitState.ratio, onResize);
  }

  function bindModal() {
    document.getElementById("btn-settings")?.addEventListener("click", openModal);
    document.getElementById("settings-close")?.addEventListener("click", closeModal);
    document.getElementById("settings-dismiss")?.addEventListener("click", closeModal);
    document.getElementById("settings-reset")?.addEventListener("click", () => {
      reset();
      setSettingsTab(settingsTab);
    });
    document
      .getElementById("settings-modal")
      ?.querySelector(".m0-modal-backdrop")
      ?.addEventListener("click", closeModal);
  }

  global.MemoriaGraphSettings = {
    DEFAULTS,
    SPLIT_DEFAULTS,
    load,
    save,
    reset,
    getLabelSettings,
    getViewOptions,
    onChange,
    hydrateFromDisk,
    openModal,
    closeModal,
    bindModal,
    bindVerticalResize,
    bindSidebarNavKpSplit,
    refreshSidebarNavKpSplit,
    clearSidebarNavKpSplit,
    /** @deprecated 使用 refreshSidebarNavKpSplit */
    bindSidebarGraphResize: bindSidebarNavKpSplit,
    /** @deprecated 使用 refreshSidebarNavKpSplit */
    refreshSidebarGraphSplit: (onResize) => refreshSidebarNavKpSplit("graph2d", onResize),
    /** @deprecated */
    deactivateSidebarGraphSplit: clearSidebarNavKpSplit,
    SAMPLE_GRAPH,
  };
})(typeof window !== "undefined" ? window : globalThis);
