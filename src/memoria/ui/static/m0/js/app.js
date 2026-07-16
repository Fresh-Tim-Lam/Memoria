(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const api = () => window.MemoriaBridge && window.MemoriaBridge.api();

  /** 按住主键拖拽（如图谱平移）时不触发悬停高亮 */
  function shouldSuppressHoverHighlight(e) {
    return !!(e && e.buttons);
  }

  let state = {
    kbPath: "",
    files: [],
    currentPath: null,
    doc: null,
    activeKpId: null,
    assist: null,
    viewMode: localStorage.getItem("m0-view") || "source",
    previewToken: 0,
    assistPreviewTimer: null,
    assistScrollFocus: "start",
    assistLastView: null,
    kpHighlightFadeTimer: null,
    kpHighlightClearTimer: null,
    linkTargetSet: null,
    linkPicker: null,
    openTabs: [],
    configTab: "kp",
    configModalOpts: {},
    kpPanel: null,
    sidebarTab: localStorage.getItem("m0-sidebar-tab") || "files",
    treeExpanded: null,
    graphEngine: null,
    graphLayout2d: null,
    graphLayout3d: null,
    graphView2d: null,
    graphView3d: null,
    graphLinkFocusEl: null,
    kpGraphHoverId: null,
    _editorLinkHoverLine: 0,
    graphData: null,
    graphAudit: null,
    graphGroupId: localStorage.getItem("m0-graph-group") || "all",
    kbValidateReport: null,
    toolbarSearchScope: localStorage.getItem("m0-search-scope") || "kb",
    toolbarSearchResults: [],
    kbPending: null,
    lastFileStats: "",
  };

  function setStatus(msg, stats) {
    $("#status-info").textContent = msg;
    if (stats !== undefined) {
      state.lastFileStats = stats == null ? "" : String(stats);
      renderStatusStats();
    }
  }

  function formatKbCheckStatsHtml(vr) {
    if (!vr) return "";
    const err = vr.errors || 0;
    const warn = vr.warnings || 0;
    if (err === 0 && warn === 0) return "";
    const parts = ["检查"];
    if (err > 0) {
      parts.push(`<span class="m0-stat-error">${err} 错误</span>`);
    }
    if (warn > 0) {
      parts.push(`<span class="m0-stat-warn">${warn} 警告</span>`);
    }
    return parts.join(" · ");
  }

  function normalizeCheckSeverity(severity) {
    return severity === "error" ? "error" : "warning";
  }

  function updateCheckButtonBadge(vr) {
    const badge = $("#btn-check-badge");
    if (!badge) return;
    const err = vr?.errors || 0;
    const warn = vr?.warnings || 0;
    const total = err + warn;
    badge.classList.remove("m0-toolbar-badge--error", "m0-toolbar-badge--warn", "hidden");
    if (total <= 0) {
      badge.textContent = "";
      badge.classList.add("hidden");
      badge.setAttribute("aria-hidden", "true");
      badge.removeAttribute("title");
      return;
    }
    badge.textContent = String(total > 99 ? "99+" : total);
    badge.removeAttribute("aria-hidden");
    if (err > 0) {
      badge.classList.add("m0-toolbar-badge--error");
      badge.title = warn > 0 ? `${err} 错误 · ${warn} 警告` : `${err} 错误`;
    } else {
      badge.classList.add("m0-toolbar-badge--warn");
      badge.title = `${warn} 警告`;
    }
  }

  function renderStatusStats() {
    const el = $("#status-stats");
    if (!el) return;
    el.classList.remove("m0-status-clickable");
    delete el.dataset.graphAuditGoto;

    const chunks = [];
    const vr = state.kbValidateReport;
    if (vr && (vr.errors > 0 || vr.warnings > 0)) {
      chunks.push(formatKbCheckStatsHtml(vr));
      el.dataset.kbCheck = "1";
    } else {
      delete el.dataset.kbCheck;
      if (vr?.status === "ok" && state.kbPath && !state.lastFileStats) {
        chunks.push('<span class="m0-stat-ok">检查通过</span>');
      }
    }

    const gw = vr?.graph_audit?.summary?.warn_count;
    if (gw && !state.lastFileStats) {
      chunks.push(`<span class="m0-stat-warn">图谱 ${gw} 处待配置</span>`);
    }

    if (state.lastFileStats) {
      chunks.push(esc(state.lastFileStats));
    }

    const fileWarns = currentFileGraphAuditWarns();
    const kbWarns = collectKbGraphAuditWarns(state.graphAudit);
    if (fileWarns.length) {
      const first = fileWarns[0];
      chunks.push(
        `<span class="m0-stat-warn">图谱建边 ${fileWarns.length} 处 · ${esc(basename(first.file))} · 点击定位</span>`
      );
      el.classList.add("m0-status-clickable");
      el.dataset.graphAuditGoto = "1";
    } else if (kbWarns.length) {
      const first = kbWarns[0];
      const fileCount = new Set(kbWarns.map((w) => normRelPath(w.file))).size;
      chunks.push(
        `<span class="m0-stat-warn">图谱建边 ${kbWarns.length} 处 · ${esc(basename(first.file))}${fileCount > 1 ? ` 等 ${fileCount} 文件` : ""} · 点击打开</span>`
      );
      el.classList.add("m0-status-clickable");
      el.dataset.graphAuditGoto = "1";
    }

    el.innerHTML = chunks.filter(Boolean).join(" · ");
  }

  function applyCheckIndicators(vr) {
    if (!vr) return;
    updateCheckButtonBadge(vr);
    renderStatusStats();
  }

  function startKbSilentCheck() {
    if (!window.MemoriaCheckSettings) return;
    MemoriaCheckSettings.startSilentCheck(() => {
      if (state.kbPath) runKbValidate({ silent: true });
    });
  }

  function stopKbSilentCheck() {
    window.MemoriaCheckSettings?.stopSilentCheck?.();
  }

  function showFlashError(msg, detail, opts = {}) {
    const host = $("#m0-flash-host");
    if (!host || !msg) return;
    const duration = opts.duration ?? 3800;
    const el = document.createElement("div");
    el.className = "m0-flash-error";
    el.innerHTML =
      `<div class="m0-flash-error-title">${esc(String(msg))}</div>` +
      (detail ? `<div class="m0-flash-error-detail">${esc(String(detail))}</div>` : "");
    host.appendChild(el);
    const fadeMs = 280;
    const fadeTimer = window.setTimeout(() => el.classList.add("m0-flash-leaving"), duration);
    const removeTimer = window.setTimeout(() => el.remove(), duration + fadeMs);
    el._m0FlashTimers = [fadeTimer, removeTimer];
  }

  function setStatusError(msg, detail, opts = {}) {
    setStatus(msg, detail);
    showFlashError(msg, detail, opts);
  }

  function showKbIndicator(path) {
    const wrap = $("#kb-indicator-wrap");
    const el = $("#kb-indicator");
    if (!wrap || !el) return;
    el.textContent = path || "";
    el.title = path || "";
    wrap.classList.toggle("hidden", !path);
    window.MemoriaWindowChrome?.syncToolbarDragExclusion?.();
  }

  function showWelcome(show) {
    $("#welcome").classList.toggle("hidden", !show);
    $("#editor-wrap").classList.toggle("hidden", show);
  }

  async function call(fn, ...args) {
    const a = api();
    if (!a || !a[fn]) throw new Error("API 不可用: " + fn);
    return await a[fn](...args);
  }

  async function loadLinkTargets() {
    try {
      const res = await call("get_link_targets");
      if (res.status === "ok" && Array.isArray(res.resolved_targets)) {
        state.linkTargetSet = new Set(res.resolved_targets);
        state.linkTargetList = res.resolved_targets;
        return;
      }
    } catch (_) {
      /* optional */
    }
    state.linkTargetSet = null;
    state.linkTargetList = [];
  }

  function updateNavButtons() {
    const back = $("#btn-nav-back");
    const fwd = $("#btn-nav-forward");
    if (!back || !fwd || !window.MemoriaNavStack) return;
    back.disabled = !MemoriaNavStack.canBack();
    fwd.disabled = !MemoriaNavStack.canForward();
  }

  async function resolveStartupKbPath() {
    let kbPath = "";
    try {
      kbPath = (await call("get_kb_path")) || "";
    } catch (_) {
      kbPath = "";
    }
    if (kbPath) return kbPath;
    try {
      const remembered = (await call("get_remembered_kb_path")) || "";
      if (!remembered) return "";
      const opened = await call("set_kb_path", remembered);
      if (opened?.status === "ok") {
        return opened.path || remembered;
      }
    } catch (_) {
      /* ignore */
    }
    return "";
  }

  async function initKb() {
    try {
      state.kbPath = await resolveStartupKbPath();
      if (window.MemoriaCheckSettings?.hydrateFromDisk) {
        await MemoriaCheckSettings.hydrateFromDisk();
      }
      if (window.MemoriaGraphSettings?.hydrateFromDisk) {
        await MemoriaGraphSettings.hydrateFromDisk();
        applyGraphViewSettings(MemoriaGraphSettings.getViewOptions());
        MemoriaGraphSettings.refreshSidebarNavKpSplit(
          state.sidebarTab,
          () => {
            state.graphView2d?.reflow?.();
            state.graphView3d?.reflow?.();
          }
        );
      }
      if (window.MemoriaSearchSettings?.hydrateFromDisk) {
        await MemoriaSearchSettings.hydrateFromDisk();
      }
      if (state.kbPath) {
        showKbIndicator(state.kbPath);
        if (window.MemoriaNavStack) MemoriaNavStack.clear();
        state.openTabs = [];
        updateNavButtons();
        await refreshFiles();
        await loadLinkTargets();
        await loadGraphData();
        setStatus("已加载知识库", state.kbPath);
        await runKbValidate({ silent: false });
        startKbSilentCheck();
        const preferred =
          state.files.find((f) => f.path === "navigation-demo.md") ||
          state.files.find((f) => f.path === "mdp.md") ||
          state.files[0];
        if (preferred) await openFile(preferred.path, { skipNav: true });
      } else {
        showWelcome(true);
        showKbIndicator("");
        setStatus("Memoria");
      }
    } catch (e) {
      setStatus("等待后端…");
    }
  }

  async function refreshKbPendingSummary() {
    if (!state.kbPath) {
      state.kbPending = null;
      return;
    }
    try {
      const res = await call("get_kb_pending");
      if (res.status === "ok") state.kbPending = res;
    } catch (_) {
      state.kbPending = null;
    }
  }

  function resetOpenDocumentUi() {
    cancelKpHighlightTimers();
    clearHighlights();
    clearPreviewHighlights();
    clearGraphKpHover();
    clearGraphLinkHighlight();

    state.currentPath = null;
    state.doc = null;
    state.activeKpId = null;
    state.openTabs = [];
    state.configTab = "kp";
    state.configModalOpts = {};
    state.assist = null;
    state.kpPanel = null;

    closeConfigModal();
    closeKpModal({ skipReturn: true });

    renderTabs();
    renderKpList(null);
    const editor = $("#editor");
    if (editor) editor.innerHTML = "";
    const preview = $("#preview");
    if (preview) preview.innerHTML = "";
    const fileTitle = $("#file-title");
    if (fileTitle) fileTitle.textContent = "";
    const fileMeta = $("#file-meta");
    if (fileMeta) fileMeta.textContent = "";
    showWelcome(true);
  }

  async function openKb() {
    const path = await call("select_directory");
    if (!path) return;
    resetOpenDocumentUi();
    state.kbPath = path;
    showKbIndicator(path);
    if (window.MemoriaNavStack) MemoriaNavStack.clear();
    state.openTabs = [];
    updateNavButtons();
    await refreshFiles();
    await loadLinkTargets();
    await loadGraphData();
    await refreshKbPendingSummary();
    setStatus("已打开知识库", path);
    await runKbValidate({ silent: false });
    startKbSilentCheck();
  }

  async function closeKb() {
    try {
      await call("close_kb");
    } catch (_) {
      /* optional */
    }
    state.kbPath = "";
    state.files = [];
    state.currentPath = null;
    state.doc = null;
    state.activeKpId = null;
    state.openTabs = [];
    state.graphData = null;
    state.graphAudit = null;
    state.kbValidateReport = null;
    state.kbPending = null;
    state.lastFileStats = "";
    updateCheckButtonBadge(null);
    state.linkTargetSet = null;
    state.linkTargetList = [];
    clearGraphKpHover();
    clearGraphLinkHighlight();
    if (window.MemoriaNavStack) MemoriaNavStack.clear();
    updateNavButtons();
    showKbIndicator("");
    if (state.graphEngine) {
      state.graphEngine.loadPayload({ nodes: [], edges: [] });
    }
    state.graphView2d?.stop?.();
    state.graphView3d?.stop?.();
    syncGraphGroupBarVisibility();
    updateSidebarTabCounts();
    renderFileTree();
    renderTabs();
    const editor = $("#editor");
    if (editor) editor.innerHTML = "";
    const preview = $("#preview");
    if (preview) preview.innerHTML = "";
    const kpList = $("#kp-list");
    if (kpList) kpList.innerHTML = '<div class="empty">未打开知识库</div>';
    const kpCount = $("#kp-count");
    if (kpCount) kpCount.textContent = "";
    showWelcome(true);
    stopKbSilentCheck();
    setStatus("未打开知识库", "点「打开知识库」选择目录");
    closeCheckModal();
  }

  async function refreshFiles() {
    const res = await call("list_files");
    if (res.status !== "ok") {
      setStatus(res.message || "列表失败");
      return;
    }
    state.files = res.files || [];
    updateSidebarTabCounts();
    renderFileTree();
  }

  function ensureTreeExpandedSet() {
    if (!state.treeExpanded) {
      state.treeExpanded = new Set();
    }
    return state.treeExpanded;
  }

  function ensureTreeExpandedForPath(relPath) {
    if (!relPath) return;
    const expanded = ensureTreeExpandedSet();
    const parts = relPath.replace(/\\/g, "/").split("/");
    let acc = "";
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? `${acc}/${parts[i]}` : parts[i];
      expanded.add(acc);
    }
  }

  function compareTreeNames(a, b) {
    return String(a).localeCompare(String(b), "zh-CN", {
      sensitivity: "base",
      numeric: true,
    });
  }

  function buildFileTreeRoot(files) {
    const root = { dirs: {}, files: [] };
    for (const f of files) {
      const norm = f.path.replace(/\\/g, "/");
      const parts = norm.split("/");
      let node = root;
      let dirPath = "";
      for (let i = 0; i < parts.length - 1; i++) {
        const seg = parts[i];
        dirPath = dirPath ? `${dirPath}/${seg}` : seg;
        if (!node.dirs[seg]) {
          node.dirs[seg] = { name: seg, path: dirPath, dirs: {}, files: [] };
        }
        node = node.dirs[seg];
      }
      node.files.push({ ...f, path: norm });
    }
    return root;
  }

  function renderTreeDirNode(node, depth) {
    const expanded = ensureTreeExpandedSet().has(node.path);
    const pad = 4 + depth * 14;
    let html = `<div class="m0-tree-dir" data-dir="${esc(node.path)}">
      <div class="m0-tree-dir-head" data-dir-toggle="${esc(node.path)}" style="padding-left:${pad}px">
        <span class="m0-tree-twisty">${expanded ? "▼" : "▶"}</span>
        <span class="m0-tree-icon">📁</span>
        <span class="m0-tree-label">${esc(node.name)}</span>
      </div>
      <div class="m0-tree-dir-children${expanded ? "" : " collapsed"}">`;
    html += renderTreeLevel(node, depth + 1);
    html += "</div></div>";
    return html;
  }

  function renderTreeFileItem(f, depth) {
    const active = f.path === state.currentPath ? " active" : "";
    const side = f.has_sidecar ? "" : " no-sidecar";
    const icon = f.has_sidecar ? "📄" : "📝";
    const pad = 12 + depth * 14;
    const label = basename(f.path);
    return `<div class="m0-tree-item${active}${side}" data-path="${esc(f.path)}" title="${esc(f.path)}" style="padding-left:${pad}px">
      <span class="m0-tree-icon">${icon}</span>
      <span class="m0-tree-label">${esc(label)}</span>
    </div>`;
  }

  function renderTreeLevel(node, depth) {
    let html = "";
    const dirs = Object.values(node.dirs || {}).sort((a, b) =>
      compareTreeNames(a.name, b.name)
    );
    for (const dir of dirs) {
      html += renderTreeDirNode(dir, depth);
    }
    const files = (node.files || [])
      .slice()
      .sort((a, b) => compareTreeNames(basename(a.path), basename(b.path)));
    for (const f of files) {
      html += renderTreeFileItem(f, depth);
    }
    return html;
  }

  function bindFileTreeInteraction(el) {
    el.querySelectorAll("[data-dir-toggle]").forEach((head) => {
      head.addEventListener("click", (e) => {
        e.stopPropagation();
        const dirPath = head.dataset.dirToggle;
        const expanded = ensureTreeExpandedSet();
        if (expanded.has(dirPath)) expanded.delete(dirPath);
        else expanded.add(dirPath);
        renderFileTree();
      });
    });
    el.querySelectorAll(".m0-tree-item").forEach((node) => {
      node.addEventListener("click", () => navigateToFile(node.dataset.path));
    });
  }

  function updateSidebarTabCounts() {
    const countEl = $("#sidebar-tab-count-files");
    if (countEl) countEl.textContent = String(state.files?.length || 0);
    const graphEl = $("#sidebar-tab-count-graph2d");
    const graph3dEl = $("#sidebar-tab-count-graph3d");
    const n = state.graphData?.nodes?.length || 0;
    if (graphEl) graphEl.textContent = String(n);
    if (graph3dEl) graph3dEl.textContent = String(n);
  }

  function getGraphGroupComputeOpts(viewOpts) {
    const v = viewOpts || window.MemoriaGraphSettings?.getViewOptions?.() || {};
    return {
      groupLabelMode: v.groupLabelMode || "hub_name",
      groupLabelMaxLen: v.groupLabelMaxLen ?? 12,
    };
  }

  function syncGraphGroupBarVisibility() {
    const bar = $("#sidebar-graph-group-bar");
    if (!bar) return;
    const onGraph =
      state.sidebarTab === "graph2d" || state.sidebarTab === "graph3d";
    const hasNodes = (state.graphEngine?.nodes?.length || 0) > 0;
    const show = onGraph && hasNodes;
    bar.classList.toggle("hidden", !show);
    bar.setAttribute("aria-hidden", show ? "false" : "true");
  }

  function ensureValidGraphGroupSelection() {
    const allId = window.MemoriaGraphGroups?.ALL_GROUP_ID || "all";
    if (state.graphGroupId === allId) return;
    const groups = state.graphEngine?.groups?.groups || [];
    if (!groups.some((g) => g.id === state.graphGroupId)) {
      state.graphGroupId = allId;
      localStorage.setItem("m0-graph-group", allId);
    }
  }

  function bindGraphGroupTabWheel() {
    const el = $("#sidebar-graph-group-tabs");
    if (!el || el.dataset.wheelBound) return;
    el.dataset.wheelBound = "1";
    el.addEventListener(
      "wheel",
      (e) => {
        if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
        e.preventDefault();
        el.scrollLeft += e.deltaY;
      },
      { passive: false }
    );
  }

  function renderGraphGroupTabs() {
    const root = $("#sidebar-graph-group-tabs");
    if (!root || !window.MemoriaGraphGroups) return;
    bindGraphGroupTabWheel();
    const allId = window.MemoriaGraphGroups.ALL_GROUP_ID;
    const groups = state.graphEngine?.groups?.groups || [];
    ensureValidGraphGroupSelection();
    const activeId = state.graphGroupId || allId;

    const tabs = [
      {
        id: allId,
        label: "全部",
        title: "全部节点群（横向瀑布流）",
        count: groups.length || null,
      },
      ...groups.map((g) => ({
        id: g.id,
        label: g.label || g.hubName || g.hubId || g.id,
        title: `${g.hubName || g.hubId} · ${g.size} 节点 · ${g.edgeCount} 边`,
        count: g.size > 1 ? g.size : null,
      })),
    ];

    root.innerHTML = tabs
      .map(
        (t) => `<div class="tab${t.id === activeId ? " active" : ""}" data-graph-group="${escapeAttr(t.id)}" title="${escapeAttr(t.title)}">
          <span class="tab-label">${escapeHtml(t.label)}</span>${t.count != null ? ` <span class="m0-tab-count">${t.count}</span>` : ""}
        </div>`
      )
      .join("");

    root.querySelectorAll("[data-graph-group]").forEach((tab) => {
      tab.addEventListener("click", () => {
        selectGraphGroup(tab.dataset.graphGroup);
      });
    });
    syncGraphGroupBarVisibility();
  }

  function selectGraphGroup(groupId) {
    const allId = window.MemoriaGraphGroups?.ALL_GROUP_ID || "all";
    state.graphGroupId = groupId || allId;
    localStorage.setItem("m0-graph-group", state.graphGroupId);
    clearGraphKpHover();
    renderGraphGroupTabs();
    applyGraphGroupLayout({ relayout: true });
  }

  function applyGraphGroupLayout(opts = {}) {
    if (opts.relayout) {
      state.graphView2d?.resetSimulation?.();
      state.graphView3d?.resetSimulation?.();
    }
  }

  function escapeAttr(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function initGraphPanel() {
    if (
      !window.MemoriaGraphEngine ||
      !window.MemoriaGraphLayout2D ||
      !window.MemoriaGraphLayout3D ||
      !window.MemoriaGraphView2D
    ) {
      return;
    }
    const root2d = $("#graph-2d-root");
    if (!root2d || state.graphView2d) return;
    const viewOpts =
      window.MemoriaGraphSettings?.getViewOptions?.() || {};
    state.graphEngine = new MemoriaGraphEngine();
    state.graphLayout2d = new MemoriaGraphLayout2D(viewOpts);
    state.graphLayout3d = new MemoriaGraphLayout3D(viewOpts);
    state.graphView2d = new MemoriaGraphView2D(
      root2d,
      state.graphEngine,
      state.graphLayout2d,
      viewOpts
    );
    const root3d = $("#graph-3d-root");
    if (root3d && window.MemoriaGraphView3D) {
      state.graphView3d = new MemoriaGraphView3D(
        root3d,
        state.graphEngine,
        state.graphLayout3d,
        viewOpts
      );
    }
    const onGraphNodeClick = ({ node }) => {
      if (!node?.file) return;
      jumpToTarget(
        {
          file: node.file,
          kp_id: node.kp_id || node.id,
          name: node.name || node.label || node.id,
        },
        { source: "graph" }
      );
    };
    const onGraphHover = ({ node }) => {
      if (node) updateGraphNodeHint(node);
      else if (!state.graphLinkFocusEl && !state.kpGraphHoverId) updateGraphAuditHint();
    };
    state.graphEngine.on("nodeClick", onGraphNodeClick);
    state.graphEngine.on("hover", onGraphHover);
  }

  function applyGraphViewSettings(viewOpts) {
    if (state.graphEngine?.nodes?.length && window.MemoriaGraphGroups) {
      state.graphEngine.groups = window.MemoriaGraphGroups.computeGraphGroups(
        state.graphEngine.nodes,
        state.graphEngine.links,
        getGraphGroupComputeOpts(viewOpts)
      );
      refreshGraphGroupLabels();
      renderGraphGroupTabs();
    }
    state.graphLayout2d?.applyOptions(viewOpts, { relayout: false });
    state.graphLayout3d?.applyOptions(viewOpts, { relayout: false });
    state.graphView2d?.applyOptions(viewOpts, { relayout: false });
    state.graphView3d?.applyOptions(viewOpts, { relayout: false });
    applyGraphGroupLayout({ relayout: true });
  }

  async function refreshGraphGroupLabels() {
    const groups = state.graphEngine?.groups?.groups;
    if (!groups?.length || !state.kbPath) return;
    try {
      const payload = groups.map((g) => ({
        id: g.id,
        nodeIds: g.nodeIds,
        hubId: g.hubId,
        hubName: g.hubName,
      }));
      const res = await call("suggest_group_labels", payload);
      const labels = res.labels || {};
      const maxLen =
        window.MemoriaGraphSettings?.getViewOptions?.()?.groupLabelMaxLen ?? 12;
      for (const g of groups) {
        const suggested = labels[g.id];
        if (suggested) {
          g.label = window.MemoriaGraphGroups.truncateLabel(suggested, maxLen);
        }
      }
    } catch (_) {
      /* ignore */
    }
  }

  async function buildKb() {
    if (!state.kbPath) {
      setStatus("请先打开知识库");
      return;
    }
    const btn = $("#btn-build");
    if (btn) btn.disabled = true;
    setStatus("构建中…", "同步链接配置并生成图谱");
    try {
      const res = await call("build_kb");
      if (res.status === "error") {
        setStatus(res.message || "构建失败");
        return;
      }
      await refreshFiles();
      await loadLinkTargets();
      await loadGraphData();
      if (state.currentPath) {
        await openFile(state.currentPath, { skipNav: true });
      }
      const msg = res.message || "构建完成";
      const stats = res.warn_count
        ? `${msg} · ${res.warn_count} 处待人工配置`
        : msg;
      setStatus("构建完成", stats);
      if (res.warn_count > 0 && res.audit) {
        const kinds = Object.entries(res.audit.by_kind || {})
          .filter(([, n]) => n > 0)
          .map(([k, n]) => `${k}: ${n}`)
          .join(" · ");
        if (kinds) setStatus("构建完成", `${stats}（${kinds}）`);
      }
    } catch (e) {
      setStatus("构建失败", String(e.message || e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function applyKbValidateStatus(vr, opts = {}) {
    if (!vr) return;
    applyCheckIndicators(vr);
    if (opts.silent) return;
    if (vr.errors > 0 || vr.warnings > 0) {
      /* 底栏统计已由 renderStatusStats 着色；保留当前文件路径于 status-info */
      if (!state.currentPath) {
        setStatus(state.kbPath || "知识库");
      }
    } else if (vr.status === "ok" && !state.currentPath) {
      setStatus(state.kbPath || "知识库");
    }
  }

  async function runKbValidate(opts = {}) {
    if (!state.kbPath) return null;
    try {
      const vr = await call("validate_kb");
      state.kbValidateReport = vr;
      state.graphAudit = vr.graph_audit || state.graphAudit;
      applyKbValidateStatus(vr, { silent: !!opts.silent });
      if ($("#check-modal") && !$("#check-modal").classList.contains("hidden")) {
        renderCheckModalBody(vr);
      }
      return vr;
    } catch (e) {
      if (!opts.silent) setStatus("检查失败", String(e.message || e));
      return null;
    }
  }

  function checkItemHtml(severity, message, path, openPath, meta) {
    const sev = normalizeCheckSeverity(severity);
    const badge =
      sev === "error"
        ? '<span class="m0-check-badge m0-check-badge--error">错误</span>'
        : '<span class="m0-check-badge m0-check-badge--warning">警告</span>';
    const dataAttrs = [
      meta?.kpId ? `data-check-kp="${esc(meta.kpId)}"` : "",
      meta?.line ? `data-check-line="${meta.line}"` : "",
      meta?.kind ? `data-check-kind="${esc(meta.kind)}"` : "",
    ].filter(Boolean).join(" ");
    const openBtn = openPath
      ? `<button type="button" class="m0-btn secondary m0-check-open-btn" data-check-open="${esc(openPath)}" ${dataAttrs}>打开</button>`
      : "";
    const pathHtml = path
      ? `<div class="m0-check-item-path">${esc(path)}</div>`
      : "";
    return `<div class="m0-check-item m0-check-item--${sev}">
      ${badge}
      <div class="m0-check-item-main">
        <div>${esc(message)}</div>
        ${pathHtml}
      </div>
      ${openBtn}
    </div>`;
  }

  function _issueMessage(e) {
    return typeof e === "string" ? e : (e?.message || String(e));
  }
  function _issueMeta(e) {
    if (typeof e === "string") return {};
    return {
      kpId: e?.kp_id || null,
      line: e?.line || null,
      kind: e?.kind || null,
    };
  }

  function renderCheckModalBody(vr) {
    const body = $("#check-body");
    if (!body) return;
    if (!vr) {
      body.innerHTML = '<p class="m0-muted">暂无检查结果</p>';
      return;
    }
    const errN = vr.errors || 0;
    const warnN = vr.warnings || 0;
    const summaryCls =
      errN > 0 ? "m0-check-summary m0-check-summary--error" : "m0-check-summary";
    let html = `<div class="${summaryCls}">
      已检查 ${vr.files_checked || 0} 个 Markdown 文件 ·
      ${errN > 0 ? `<strong class="m0-stat-error">${errN}</strong>` : `<strong>${errN}</strong>`} 错误 ·
      ${warnN > 0 ? `<strong class="m0-stat-warn">${warnN}</strong>` : `<strong>${warnN}</strong>`} 警告
    </div>`;

    const kbIssues = [
      ...(vr.kb_integrity?.errors || []),
      ...(vr.kb_integrity?.warnings || []),
    ];
    const manifestIssues = [
      ...(vr.manifest_diff?.errors || []),
      ...(vr.manifest_diff?.warnings || []),
    ];
    const pathMoves = vr.path_moves || [];
    if (kbIssues.length) {
      html += '<section class="m0-check-section"><h4 class="m0-check-section-title">全库</h4>';
      for (const issue of kbIssues) {
        const path = issue.paths?.[0] || "";
        html += checkItemHtml(
          issue.severity,
          issue.message,
          issue.paths?.length > 1 ? issue.paths.join(" · ") : path,
          path || null
        );
      }
      html += "</section>";
    }

    if (pathMoves.length) {
      html += `<section class="m0-check-section"><h4 class="m0-check-section-title">路径变更
        <button type="button" class="m0-btn secondary m0-btn--sm" id="check-repair-paths">修复路径</button>
      </h4>`;
      html += `<p class="m0-muted">检测到文件移动/重命名。请先修复路径（会同步更新元数据、待确认项与文件清单）；在此完成前请勿「更新文件清单」。</p>`;
      for (const m of pathMoves) {
        const hint =
          m.kind === "md_sha256"
            ? "内容 hash 匹配"
            : m.kind === "sidecar_drift"
              ? "配置路径漂移"
              : m.kind || "";
        html += checkItemHtml(
          m.severity,
          `${m.from} → ${m.to}`,
          hint,
          m.to || null
        );
      }
      html += "</section>";
    }

    if (manifestIssues.length || (vr.manifest_diff && pathMoves.length === 0)) {
      const md = vr.manifest_diff || {};
      const syncBtn =
        manifestIssues.length > 0 && pathMoves.length === 0
          ? `<button type="button" class="m0-btn secondary m0-btn--sm" id="check-sync-manifest">更新文件清单</button>`
          : "";
      html += `<section class="m0-check-section"><h4 class="m0-check-section-title">文件清单 ${syncBtn}</h4>`;
      if (md.baseline_created) {
        html += `<p class="m0-muted">首次打开：已建立文件清单（${md.file_count || 0} 个文档）</p>`;
      } else if (!manifestIssues.length) {
        html += `<p class="m0-muted">文件清单与磁盘一致（${md.file_count || 0} 个文档）</p>`;
      }
      for (const issue of manifestIssues) {
        const path = issue.paths?.[0] || "";
        html += checkItemHtml(
          issue.severity,
          issue.message,
          issue.paths?.length > 1 ? issue.paths.join(" · ") : path,
          path || null
        );
      }
      html += "</section>";
    }

    for (const fr of vr.files || []) {
      html += `<section class="m0-check-section"><h4 class="m0-check-section-title">${esc(fr.path)}</h4>`;
      for (const e of fr.errors || []) {
        const meta = _issueMeta(e);
        html += checkItemHtml("error", _issueMessage(e), fr.path, fr.path, meta);
      }
      for (const w of fr.warnings || []) {
        const meta = _issueMeta(w);
        html += checkItemHtml("warning", _issueMessage(w), fr.path, fr.path, meta);
      }
      html += "</section>";
    }

    const gaFiles = (vr.graph_audit?.files || []).filter(
      (f) => (f.issues || []).length
    );
    if (gaFiles.length) {
      html += '<section class="m0-check-section"><h4 class="m0-check-section-title">图谱建边</h4>';
      for (const gf of gaFiles) {
        for (const issue of gf.issues || []) {
          html += checkItemHtml(
            issue.severity,
            issue.message || issue.code,
            gf.file,
            gf.file
          );
        }
      }
      html += "</section>";
    }

    if (
      !kbIssues.length &&
      !manifestIssues.length &&
      !pathMoves.length &&
      !(vr.files || []).length &&
      !gaFiles.length
    ) {
      html += '<p class="m0-muted">未发现配置或图谱问题。</p>';
    }
    body.innerHTML = html;
    body.querySelector("#check-sync-manifest")?.addEventListener("click", async () => {
      setStatus("更新文件清单…");
      const res = await call("sync_manifest");
      if (res.status === "ok") {
        setStatus("文件清单已更新", `${res.file_count || 0} 个文档`);
        await runKbValidate({ silent: false });
      } else {
        setStatusError(res.message || "同步失败");
        if (res.blocked && (res.path_moves || []).length) {
          await runKbValidate({ silent: false });
        }
      }
    });

    body.querySelector("#check-repair-paths")?.addEventListener("click", async () => {
      if (
        !window.confirm(
          "修复检测到的路径变更？\n将更新元数据路径、待确认项与文件清单。"
        )
      ) {
        return;
      }
      setStatus("修复路径…");
      const res = await call("repair_path_cascade", true);
      if (res.status === "ok" || res.status === "partial") {
        setStatus(
          "路径已修复",
          `${res.applied_count ?? 0}/${res.move_count ?? 0} 处`
        );
        remapOpenTabsAfterPathRepair(res.applied || []);
        const cur = normRelPath(state.currentPath || "");
        const moved = (res.applied || []).find(
          (m) => normRelPath(m.from) === cur
        );
        const reopenPath = moved ? normRelPath(moved.to) : state.currentPath;
        if (reopenPath) {
          await openFile(reopenPath, {
            skipNav: true,
            kpId: state.activeKpId || null,
          });
        }
        await refreshFiles();
        await loadGraphData();
        await runKbValidate({ silent: false });
      } else {
        setStatusError(res.message || "修复失败");
      }
    });

    body.querySelectorAll("[data-check-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = btn.getAttribute("data-check-open");
        if (!p) return;
        const kpId = btn.getAttribute("data-check-kp") || null;
        const lineStr = btn.getAttribute("data-check-line");
        const kind = btn.getAttribute("data-check-kind") || null;
        const line = lineStr ? parseInt(lineStr, 10) : null;
        closeCheckModal();
        openFile(p, {
          kpId,
          errorHighlight: {
            kind,
            kpId,
            line: line && Number.isFinite(line) ? line : null,
          },
        });
      });
    });
  }

  function openCheckModal() {
    if (!state.kbPath) {
      setStatus("请先打开知识库");
      return;
    }
    const modal = $("#check-modal");
    if (!modal) return;
    modal.classList.remove("hidden");
    renderCheckModalBody(state.kbValidateReport);
    runKbValidate({ silent: true });
  }

  function closeCheckModal() {
    $("#check-modal")?.classList.add("hidden");
  }

  // ── R11: 平面文件导入 ──────────────────────────────────────────

  let _importFileContents = null;
  let _importScanResult = null;

  async function startImport() {
    if (!state.kbPath) {
      setStatus("请先打开知识库");
      return;
    }
    const btn = $("#btn-import");
    if (btn) btn.disabled = true;
    try {
      const files = await call("select_import_files");
      if (!files || !files.length) {
        return;
      }
      _importFileContents = files;
      setStatus("导入预扫描中…");
      const scan = await call("pre_scan_import", files);
      if (scan.status === "error") {
        setStatusError(scan.message || "预扫描失败");
        return;
      }
      _importScanResult = scan;
      if (!scan.has_conflicts) {
        await executeImportDirect(files, {});
        return;
      }
      renderImportConflictDialog(scan);
      $("#import-conflict-modal").classList.remove("hidden");
    } catch (e) {
      setStatusError("导入失败", e.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function executeImportDirect(files, conflictResolution) {
    const btn = $("#btn-import");
    if (btn) btn.disabled = true;
    try {
      setStatus("导入中…");
      const result = await call("execute_import", files, conflictResolution);
      if (result.status === "error") {
        setStatusError(result.message || "导入失败");
        return;
      }
      await afterImportRefresh(result);
      renderImportResultDialog(result);
      $("#import-result-modal").classList.remove("hidden");
    } catch (e) {
      setStatusError("导入失败", e.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function afterImportRefresh(result) {
    await refreshFiles();
    await loadLinkTargets();
    await loadGraphData();
    await refreshKbPendingSummary();
    if (state.currentPath) {
      await openFile(state.currentPath, { skipNav: true });
    }
    const kp = (result.kp_imported || 0) + (result.kp_overwritten || 0) + (result.kp_renamed || 0);
    setStatus("导入完成", `${result.files_written || 0} 文件 · ${kp} KP`);
  }

  function renderImportConflictDialog(scanResult) {
    const body = $("#import-conflict-body");
    if (!body) return;
    const conflicts = scanResult.conflicts || [];
    let html = "";
    html += `<div class="m0-import-scan-summary">`;
    html += `<p>共 <strong>${esc(String(scanResult.total_files || 0))}</strong> 个文件，`;
    html += `<strong>${esc(String(scanResult.total_sections || 0))}</strong> 个段落，`;
    html += `<strong>${esc(String(scanResult.total_kp_declarations || 0))}</strong> 个 KP 声明。</p>`;
    html += `<p class="m0-stat-error">检测到 <strong>${esc(String(conflicts.length))}</strong> 处 KP id 冲突：</p>`;
    html += `</div>`;
    html += `<div class="m0-import-conflict-report">`;
    html += `<textarea id="import-conflict-report-text" class="m0-import-report-textarea" readonly rows="4">${esc(scanResult.conflict_report || "")}</textarea>`;
    html += `</div>`;
    html += `<div class="m0-import-conflict-list">`;
    conflicts.forEach((c, i) => {
      const kpId = esc(c.kp_id || "");
      const source = esc(c.import_source || "");
      const line = c.import_line || 0;
      const existFile = esc(c.existing_file || "");
      const existName = esc(c.existing_name || "");
      html += `<div class="m0-import-conflict-item" data-conflict-idx="${i}">`;
      html += `<div class="m0-import-conflict-header">`;
      html += `<span class="m0-import-conflict-kp-id">${kpId}</span>`;
      html += `<span class="m0-muted">来源: ${source}:${line} → 已存在: ${existFile} (${existName})</span>`;
      html += `</div>`;
      html += `<div class="m0-import-conflict-resolution">`;
      html += `<label><input type="radio" name="import-res-${i}" value="skip" checked> 跳过</label>`;
      html += `<label><input type="radio" name="import-res-${i}" value="overwrite"> 覆盖</label>`;
      html += `<label><input type="radio" name="import-res-${i}" value="rename"> 重命名</label>`;
      html += `<input type="text" class="m0-import-rename-input hidden" data-conflict-idx="${i}" placeholder="新 KP id">`;
      html += `</div>`;
      html += `</div>`;
    });
    html += `</div>`;
    body.innerHTML = html;

    body.querySelectorAll('input[type="radio"]').forEach((radio) => {
      radio.addEventListener("change", (e) => {
        const idx = e.target.name.replace("import-res-", "");
        const renameInput = body.querySelector(`.m0-import-rename-input[data-conflict-idx="${idx}"]`);
        if (renameInput) {
          renameInput.classList.toggle("hidden", e.target.value !== "rename");
          if (e.target.value === "rename") renameInput.focus();
        }
      });
    });
  }

  function collectImportConflictResolution() {
    const body = $("#import-conflict-body");
    if (!body) return {};
    const conflicts = (_importScanResult && _importScanResult.conflicts) || [];
    const resolution = {};
    conflicts.forEach((c, i) => {
      const radios = body.querySelectorAll(`input[name="import-res-${i}"]`);
      let choice = "skip";
      radios.forEach((r) => { if (r.checked) choice = r.value; });
      if (choice === "rename") {
        const renameInput = body.querySelector(`.m0-import-rename-input[data-conflict-idx="${i}"]`);
        const newId = (renameInput && renameInput.value.trim()) || c.kp_id;
        resolution[c.kp_id] = "rename:" + newId;
      } else {
        resolution[c.kp_id] = choice;
      }
    });
    return resolution;
  }

  function renderImportResultDialog(result) {
    const body = $("#import-result-body");
    if (!body) return;
    const kp = (result.kp_imported || 0) + (result.kp_overwritten || 0) + (result.kp_renamed || 0);
    let html = "";
    html += `<div class="m0-import-result-summary">`;
    html += `<p class="m0-stat-ok">导入成功</p>`;
    html += `<p>写入 <strong>${esc(String(result.files_written || 0))}</strong> 个文件，`;
    html += `导入 <strong>${esc(String(result.kp_imported || 0))}</strong> 个 KP，`;
    html += `覆盖 <strong>${esc(String(result.kp_overwritten || 0))}</strong> 个，`;
    html += `重命名 <strong>${esc(String(result.kp_renamed || 0))}</strong> 个，`;
    html += `跳过 <strong>${esc(String(result.kp_skipped || 0))}</strong> 个。</p>`;
    const errors = result.errors || [];
    if (errors.length) {
      html += `<p class="m0-stat-error">${esc(String(errors.length))} 个错误：</p><ul>`;
      errors.forEach((e) => { html += `<li>${esc(String(e))}</li>`; });
      html += `</ul>`;
    }
    html += `</div>`;
    body.innerHTML = html;
  }

  function closeImportConflictModal() {
    $("#import-conflict-modal").classList.add("hidden");
    _importFileContents = null;
    _importScanResult = null;
  }

  function closeImportResultModal() {
    $("#import-result-modal").classList.add("hidden");
  }

  async function loadGraphData() {
    if (!state.kbPath) return;
    try {
      const res = await call("get_graph_data");
      if (res.status !== "ok") {
        setStatus(res.message || "图谱加载失败");
        return;
      }
      state.graphData = res;
      state.graphAudit = res.graph_audit || null;
      updateSidebarTabCounts();
      if (!state.graphEngine) initGraphPanel();
      if (state.graphEngine) {
        const viewOpts =
          window.MemoriaGraphSettings?.getViewOptions?.() || {};
        state.graphEngine.loadPayload(res, getGraphGroupComputeOpts(viewOpts));
        await refreshGraphGroupLabels();
        renderGraphGroupTabs();
        applyGraphGroupLayout({ relayout: true });
      }
      updateGraphAuditHint();
    } catch (e) {
      setStatus("图谱加载失败", String(e.message || e));
    }
  }

  function graphAuditWarnIssues(report) {
    return (report?.issues || []).filter((i) => i.severity === "warn");
  }

  function collectKbGraphAuditWarns(audit) {
    const out = [];
    for (const fr of audit?.files || []) {
      for (const i of graphAuditWarnIssues(fr)) {
        out.push({ ...i, file: i.file || fr.file });
      }
    }
    return out;
  }

  function currentFileGraphAuditWarns() {
    const fileAudit = state.doc?.graph_link_audit;
    if (!fileAudit || !state.currentPath) return [];
    if (normRelPath(fileAudit.file) !== normRelPath(state.currentPath)) return [];
    return graphAuditWarnIssues(fileAudit).map((i) => ({
      ...i,
      file: fileAudit.file,
    }));
  }

  function firstGraphAuditWarn() {
    const fileWarns = currentFileGraphAuditWarns();
    if (fileWarns.length) return fileWarns[0];
    const kbWarns = collectKbGraphAuditWarns(state.graphAudit);
    return kbWarns[0] || null;
  }

  async function gotoGraphAuditIssue(issue) {
    if (!issue?.file) return;
    const rel = normRelPath(issue.file);
    await openFile(rel, { skipNav: true });
    if (issue.line) {
      highlightRange(issue.line, issue.line);
      document
        .getElementById(`line-${issue.line}`)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    setStatus(`图谱建边 · ${basename(rel)}`, issue.message || "");
    updateGraphAuditHint();
  }

  function graphAuditHintLabel(issue) {
    const fileLabel = basename(issue.file || "");
    const loc = issue.line ? `L${issue.line}` : "";
    if (fileLabel && loc) return `${fileLabel} · ${loc}`;
    return fileLabel || loc || "待配置";
  }

  function activeGraphHint() {
    if (state.sidebarTab === "graph3d") return $("#graph-3d-hint");
    if (state.sidebarTab === "graph2d") return $("#graph-2d-hint");
    return null;
  }

  function updateGraphAuditHint() {
    const hint = activeGraphHint();
    if (!hint || state.graphLinkFocusEl) return;
    if (state.sidebarTab !== "graph2d" && state.sidebarTab !== "graph3d") return;
    const fileWarns = currentFileGraphAuditWarns();
    if (fileWarns.length) {
      const first = fileWarns[0];
      hint.innerHTML = `<span class="m0-graph-audit-warn">⚠ ${esc(graphAuditHintLabel(first))}：${esc(first.message)}</span>
        <button type="button" class="m0-btn secondary m0-btn--sm m0-graph-audit-goto">打开文件</button>`;
      return;
    }
    const kbWarns = collectKbGraphAuditWarns(state.graphAudit);
    if (kbWarns.length) {
      const first = kbWarns[0];
      const fileCount = new Set(kbWarns.map((w) => normRelPath(w.file))).size;
      hint.innerHTML = `<span class="m0-graph-audit-warn">⚠ 全库 ${kbWarns.length} 处 · ${esc(basename(first.file))}${fileCount > 1 ? ` 等 ${fileCount} 文件` : ""}：${esc(first.message)}</span>
        <button type="button" class="m0-btn secondary m0-btn--sm m0-graph-audit-goto">打开 ${esc(basename(first.file))}</button>`;
      return;
    }
    hint.innerHTML =
      state.sidebarTab === "graph3d"
        ? '<span class="m0-muted">左键旋转 · 滚轮缩放 · 点击跳转 · 悬停正文链接可高亮</span>'
        : '<span class="m0-muted">滚轮缩放 · 拖空白平移 · 点击跳转 · 悬停正文链接可高亮</span>';
  }

  function syncGraphAuditStatusBar(_baseStats) {
    renderStatusStats();
  }

  function setGraphPanelActive(tab) {
    const on2d = tab === "graph2d";
    const on3d = tab === "graph3d";
    const onGraph = on2d || on3d;
    if (on2d) {
      state.graphLayout2d?.start();
      state.graphLayout3d?.stop();
    } else if (on3d) {
      state.graphLayout3d?.start();
      state.graphLayout2d?.stop();
    } else {
      state.graphLayout2d?.stop();
      state.graphLayout3d?.stop();
    }

    if (state.graphView2d) {
      if (on2d) {
        state.graphView2d.onPanelShown();
        state.graphView2d.start();
      } else {
        state.graphView2d.stop();
      }
    }
    if (state.graphView3d) {
      if (on3d) {
        state.graphView3d.onPanelShown();
        state.graphView3d.start();
      } else {
        state.graphView3d.stop();
      }
    }
    if (onGraph && state.kpGraphHoverId && isNodeInCurrentGraphLayout(state.kpGraphHoverId)) {
      state.graphView2d?.setRemoteHover?.(state.kpGraphHoverId);
      state.graphView3d?.setRemoteHover?.(state.kpGraphHoverId);
      const node = state.graphEngine?.getNode(state.kpGraphHoverId);
      if (node) updateGraphNodeHint(node);
    }
  }

  function setSidebarTab(tab) {
    state.sidebarTab = tab;
    localStorage.setItem("m0-sidebar-tab", tab);
    document.querySelectorAll("[data-sidebar-tab]").forEach((btn) => {
      const on = btn.dataset.sidebarTab === tab;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("[data-sidebar-view]").forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.sidebarView !== tab);
    });
    clearGraphKpHover();
    setGraphPanelActive(tab);
    syncGraphGroupBarVisibility();
    if (tab === "graph2d" || tab === "graph3d") updateGraphAuditHint();
    const onSidebarResize = () => {
      state.graphView2d?.reflow?.();
      state.graphView3d?.reflow?.();
    };
    if (window.MemoriaGraphSettings?.refreshSidebarNavKpSplit) {
      MemoriaGraphSettings.refreshSidebarNavKpSplit(tab, onSidebarResize);
    }
  }

  function renderFileTree() {
    const el = $("#file-tree");
    if (!el) return;
    if (!state.files.length) {
      el.innerHTML = '<div class="empty">无 Markdown 文件</div>';
      return;
    }
    if (state.currentPath) ensureTreeExpandedForPath(state.currentPath);
    const root = buildFileTreeRoot(state.files);
    el.innerHTML = renderTreeLevel(root, 0);
    bindFileTreeInteraction(el);
  }

  function tabLabelFor(candidate) {
    return candidate.name || candidate.kp_id || basename(candidate.file || candidate.path || "");
  }

  function ensureOpenTab(candidate, opts = {}) {
    const path = candidate.file || candidate.path;
    if (!path) return null;
    const kpId = candidate.kp_id || null;
    let tab = state.openTabs.find((t) => t.path === path);
    if (!tab) {
      tab = {
        path,
        kpId,
        label: tabLabelFor({ ...candidate, file: path }),
        pending: !!opts.pending,
        sourceScroll: 0,
        previewScroll: 0,
        kpListScroll: 0,
      };
      state.openTabs.push(tab);
    } else {
      if (kpId) tab.kpId = kpId;
      if (opts.pending !== undefined) tab.pending = opts.pending;
      if (candidate.name) tab.label = candidate.name;
    }
    if (opts.activate) tab.pending = false;
    return tab;
  }

  function _saveCurrentTabScroll() {
    if (!state.currentPath) return;
    const tab = state.openTabs.find((t) => t.path === state.currentPath);
    if (!tab) return;
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    const kpList = $("#kp-list");
    tab.sourceScroll = editorPane ? editorPane.scrollTop : 0;
    tab.previewScroll = previewPane ? previewPane.scrollTop : 0;
    tab.kpListScroll = kpList ? kpList.scrollTop : 0;
  }

  function _restoreTabScroll() {
    if (!state.currentPath) return;
    const tab = state.openTabs.find((t) => t.path === state.currentPath);
    if (!tab) return;
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    const kpList = $("#kp-list");
    if (editorPane && tab.sourceScroll != null) editorPane.scrollTop = tab.sourceScroll;
    if (previewPane && tab.previewScroll != null) previewPane.scrollTop = tab.previewScroll;
    if (kpList && tab.kpListScroll != null) kpList.scrollTop = tab.kpListScroll;
  }

  function closeTabAt(index) {
    const tab = state.openTabs[index];
    if (!tab) return;
    const wasActive = tab.path === state.currentPath;
    state.openTabs.splice(index, 1);
    if (!state.openTabs.length) {
      cancelKpHighlightTimers();
      clearHighlights();
      clearPreviewHighlights();
      clearGraphKpHover();
      clearGraphLinkHighlight();
      state.currentPath = null;
      state.doc = null;
      state.activeKpId = null;
      renderTabs();
      renderFileTree();
      renderKpList(null);
      syncToolbarSearchScopeUI();
      const editor = $("#editor");
      if (editor) editor.innerHTML = "";
      const preview = $("#preview");
      if (preview) preview.innerHTML = "";
      const fileTitle = $("#file-title");
      if (fileTitle) fileTitle.textContent = "";
      const fileMeta = $("#file-meta");
      if (fileMeta) fileMeta.textContent = "";
      showWelcome(true);
      return;
    }
    if (wasActive) {
      const next = state.openTabs[Math.min(index, state.openTabs.length - 1)];
      activateTab(next.path, next.kpId, { skipNav: true });
    } else {
      renderTabs();
    }
  }

  async function activateTab(path, kpId, opts = {}) {
    if (path === state.currentPath && (kpId || null) === (state.activeKpId || null)) {
      const tab = state.openTabs.find((t) => t.path === path);
      if (tab) tab.pending = false;
      renderTabs();
      return;
    }
    // Save scroll position of the current tab before switching
    _saveCurrentTabScroll();
    ensureOpenTab({ file: path, kp_id: kpId }, { activate: true, pending: false });
    // Switching tabs should not trigger kp/line jump — restore last scroll
    await openFile(path, { fromNav: true, skipTabUpsert: true, restoreScroll: true });
  }

  function renderTabs() {
    const tabsEl = $("#tabs");
    if (!tabsEl) return;
    if (!state.openTabs.length) {
      tabsEl.innerHTML = "";
      return;
    }
    tabsEl.innerHTML = state.openTabs
      .map((t, i) => {
        const active = t.path === state.currentPath;
        let cls = "tab";
        if (active) cls += " active";
        else if (t.pending) cls += " tab-pending";
        return `<div class="${cls}" data-tab-index="${i}" title="${esc(t.path)}">
          <span class="tab-label">${esc(t.label || basename(t.path))}</span>
          <span class="close-btn" data-tab-close="${i}" title="关闭">×</span>
        </div>`;
      })
      .join("");

    tabsEl.querySelectorAll("[data-tab-index]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest("[data-tab-close]")) return;
        const t = state.openTabs[+el.dataset.tabIndex];
        if (t) activateTab(t.path, t.kpId);
      });
    });
    tabsEl.querySelectorAll("[data-tab-close]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeTabAt(+btn.dataset.tabClose);
      });
    });
  }

  async function navigateToFile(relPath) {
    if (window.MemoriaNavStack) {
      MemoriaNavStack.openFileFromTree(relPath);
      updateNavButtons();
    }
    await openFile(relPath, { fromNav: true });
  }

  async function openFile(relPath, opts = {}) {
    // 切换文件前保存当前 tab 的滚动位置（含知识点栏）
    if (state.currentPath && state.currentPath !== relPath) {
      _saveCurrentTabScroll();
    }
    cancelKpHighlightTimers();
    clearHighlights();
    clearPreviewHighlights();
    clearGraphLinkHighlight();
    clearGraphKpHover();
    setStatus("加载中…", relPath);
    const res = await call("load_document", relPath);
    if (res.status !== "ok") {
      setStatus(res.message || "加载失败");
      return;
    }
    state.currentPath = relPath;
    state.doc = res;
    state.activeKpId = opts.kpId || null;
    if (!opts.skipTabUpsert) {
      ensureOpenTab(
        { file: relPath, kp_id: state.activeKpId, name: basename(relPath) },
        { activate: true, pending: false }
      );
    } else {
      const tab = state.openTabs.find((t) => t.path === relPath);
      if (tab) {
        tab.pending = false;
        if (state.activeKpId) tab.kpId = state.activeKpId;
      }
    }
    showWelcome(false);
    ensureTreeExpandedForPath(relPath);
    renderFileTree();
    renderTabs();
    renderEditor(res);
    renderKpList(res);
    // 恢复左侧知识点栏滚动位置（除非有 KP 跳转目标会滚动到特定 KP）
    const hasKpJump = opts.kpId || opts.errorHighlight?.kpId;
    if (!hasKpJump) {
      const tab = state.openTabs.find((t) => t.path === relPath);
      const kpList = $("#kp-list");
      if (tab && kpList && tab.kpListScroll != null) {
        kpList.scrollTop = tab.kpListScroll;
      }
    }
    setViewMode(state.viewMode, { skipSave: true });
    await renderPreview(res);
    if (opts.restoreScroll) {
      // Tab switch: restore last scroll position instead of jumping to kp/line
      _restoreTabScroll();
    } else if (opts.errorHighlight) {
      // 检查面板"打开"跳转：使用红色高亮定位
      const eh = opts.errorHighlight;
      if (eh.kind === "link") {
        // 链接问题：红色高亮链接出现的行（多匹配取第一处）
        if (eh.line && Number.isFinite(eh.line) && eh.line > 0) {
          highlightRangeWithError(eh.line, eh.line);
        }
      } else if (eh.kpId) {
        // 知识点问题：红色高亮 KP 范围 + 左侧列表定位高亮
        const kp = (res.knowledge_points || []).find((k) => k.id === eh.kpId);
        const rr = kp?.range_resolved;
        if (rr?.ok) {
          highlightRangeWithError(rr.start_line, rr.end_line);
        } else if (eh.line && Number.isFinite(eh.line) && eh.line > 0) {
          highlightRangeWithError(eh.line, eh.line);
        }
        highlightKpListItemWithError(eh.kpId);
      } else if (eh.line && Number.isFinite(eh.line) && eh.line > 0) {
        highlightRangeWithError(eh.line, eh.line);
      }
    } else if (opts.kpId) {
      const kp = (res.knowledge_points || []).find((k) => k.id === opts.kpId);
      const rr = kp?.range_resolved;
      if (rr?.ok) {
        highlightRange(rr.start_line, rr.end_line);
      }
      // 左侧知识点栏定位到对应 KP（搜索跳转/直接跳转）
      scrollKpListItemIntoView(opts.kpId);
    } else if (opts.lineHint) {
      const line = parseInt(String(opts.lineHint), 10);
      if (Number.isFinite(line) && line > 0) {
        highlightRange(line, line);
      }
    }
    let stats = `${res.knowledge_points.length} KP · ${res.lines.length} 行`;
    const sv = res.sidecar_validation;
    if (sv && (!sv.ok || sv.warnings?.length)) {
      const parts = [];
      if (sv.errors?.length) parts.push(`${sv.errors.length} 错误`);
      if (sv.warnings?.length) parts.push(`${sv.warnings.length} 警告`);
      stats += ` · 配置 ${parts.join(" ")}`;
    }
    setStatus(relPath, stats);
    syncGraphAuditStatusBar(stats);
    updateGraphAuditHint();
    syncToolbarSearchScopeUI();
  }

  // 分栏模式滚动同步：源码滚动→预览跟随，预览滚动→源码跟随
  let splitSyncLock = false;
  function setupSplitScrollSync() {
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    if (editorPane) {
      editorPane.addEventListener("scroll", () => {
        if (state.viewMode !== "split" || splitSyncLock) return;
        splitSyncLock = true;
        const line = _getViewTopSrcLine("source");
        if (line != null) _scrollToSrcLine("preview", line);
        requestAnimationFrame(() => { splitSyncLock = false; });
      });
    }
    if (previewPane) {
      previewPane.addEventListener("scroll", () => {
        if (state.viewMode !== "split" || splitSyncLock) return;
        splitSyncLock = true;
        const line = _getViewTopSrcLine("preview");
        if (line != null) _scrollToSrcLine("source", line);
        requestAnimationFrame(() => { splitSyncLock = false; });
      });
    }
  }

  function renderEditor(doc) {
    $("#file-title").textContent = doc.path;
    const desc = (doc.sidecar && doc.sidecar.description) || "";
    $("#file-meta").textContent = desc;

    const editor = $("#editor");
    editor.innerHTML = doc.lines
      .map((line, i) => {
        const n = i + 1;
        return `<div class="m0-line" data-line="${n}" id="line-${n}">
          <span class="m0-lineno">${n}</span>
          <span class="m0-line-content" contenteditable="true" spellcheck="false" tabindex="-1">${esc(line)}</span>
        </div>`;
      })
      .join("");
  }

  async function setViewMode(mode, opts) {
    const prevMode = state.viewMode;
    state.viewMode = mode;
    if (!opts?.skipSave) {
      localStorage.setItem("m0-view", mode);
    }
    // Save scroll position of the outgoing view
    if (prevMode !== mode) {
      _saveCurrentViewScroll(prevMode);
    }
    // 记录源码行号锚点：用于跨视图（源码↔预览）的文本位置映射
    let anchorLine = null;
    if (prevMode !== mode) {
      anchorLine = _getViewTopSrcLine(prevMode);
    }
    const split = $("#editor-split");
    split.classList.remove("view-source", "view-preview", "view-split");
    split.classList.add(`view-${mode}`);
    document.querySelectorAll(".m0-view-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === mode);
    });
    if (mode !== "source" && state.doc) {
      await renderPreview(state.doc);
    }
    // Restore scroll position of the incoming view after render
    if (prevMode !== mode) {
      if (mode === "split") {
        // 分栏模式：两边都同步到锚点位置
        if (anchorLine != null) {
          _scrollToSrcLine("source", anchorLine);
          _scrollToSrcLine("preview", anchorLine);
        } else {
          _restoreCurrentViewScroll("source");
          _restoreCurrentViewScroll("preview");
        }
      } else if (anchorLine != null && _scrollToSrcLine(mode, anchorLine)) {
        // 锚点恢复成功，跳过 scrollTop 数值恢复
      } else {
        _restoreCurrentViewScroll(mode);
      }
    }
  }

  // 获取当前视图顶部对应的源码行号
  function _getViewTopSrcLine(mode) {
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    if ((mode === "source" || mode === "split") && editorPane) {
      const containerTop = editorPane.getBoundingClientRect().top;
      const lines = editorPane.querySelectorAll(".m0-line");
      for (const line of lines) {
        const r = line.getBoundingClientRect();
        if (r.bottom >= containerTop) {
          return +(line.dataset.line || 0) || null;
        }
      }
    }
    if ((mode === "preview" || mode === "split") && previewPane) {
      const containerTop = previewPane.getBoundingClientRect().top;
      const blocks = previewPane.querySelectorAll("[data-m0-src-line]");
      for (const block of blocks) {
        const r = block.getBoundingClientRect();
        if (r.bottom >= containerTop) {
          return +(block.dataset.m0SrcLine || 0) || null;
        }
      }
    }
    return null;
  }

  // 滚动到指定源码行号对应的视图位置；成功返回 true
  function _scrollToSrcLine(mode, lineNum) {
    if (!lineNum) return false;
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    if ((mode === "source" || mode === "split") && editorPane) {
      const el = document.getElementById("line-" + lineNum);
      if (el) {
        const containerTop = editorPane.getBoundingClientRect().top;
        editorPane.scrollTop += el.getBoundingClientRect().top - containerTop;
        return true;
      }
    }
    if ((mode === "preview" || mode === "split") && previewPane) {
      const blocks = [...previewPane.querySelectorAll("[data-m0-src-line]")];
      let target = null;
      for (const block of blocks) {
        const s = +(block.dataset.m0SrcLine || 0);
        const e = +(block.dataset.m0SrcLineEnd || s);
        if (s <= lineNum && e >= lineNum) {
          target = block;
          break;
        }
        if (s >= lineNum && !target) {
          target = block;
        }
      }
      if (target) {
        const containerTop = previewPane.getBoundingClientRect().top;
        previewPane.scrollTop += target.getBoundingClientRect().top - containerTop;
        return true;
      }
    }
    return false;
  }

  function _saveCurrentViewScroll(mode) {
    if (!state.currentPath) return;
    const tab = state.openTabs.find((t) => t.path === state.currentPath);
    if (!tab) return;
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    if (mode === "source" || mode === "split") {
      tab.sourceScroll = editorPane ? editorPane.scrollTop : 0;
    }
    if (mode === "preview" || mode === "split") {
      tab.previewScroll = previewPane ? previewPane.scrollTop : 0;
    }
  }

  function _restoreCurrentViewScroll(mode) {
    if (!state.currentPath) return;
    const tab = state.openTabs.find((t) => t.path === state.currentPath);
    if (!tab) return;
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    if (mode === "source" || mode === "split") {
      if (editorPane && tab.sourceScroll != null) editorPane.scrollTop = tab.sourceScroll;
    }
    if (mode === "preview" || mode === "split") {
      if (previewPane && tab.previewScroll != null) previewPane.scrollTop = tab.previewScroll;
    }
  }

  async function renderPreview(doc) {
    if (!doc || state.viewMode === "source") return;
    clearGraphLinkHighlight();
    const preview = $("#preview");
    const statusEl = $("#preview-status");
    hidePreviewStatus();
    if (!window.MemoriaMarkdownPreview) {
      preview.innerHTML = '<p class="m0-preview-loading">预览模块未加载</p>';
      return;
    }
    const token = ++state.previewToken;
    preview.innerHTML = '<p class="m0-preview-loading">渲染中…</p>';
    try {
      const report = await MemoriaMarkdownPreview.renderToElement(
        preview,
        doc.preview_body || doc.body || "",
        {
          knownTargets: state.linkTargetSet,
          linkOverrides: doc.link_overrides || null,
          sidecarLinks: doc.preview_body ? null : doc.sidecar?.links || null,
        }
      );
      if (token !== state.previewToken) return;
      showPreviewReport(report);
      showLinkAuditPreviewHint(doc);
      bindPreviewLinks();
    } catch (e) {
      if (token !== state.previewToken) return;
      preview.innerHTML = `<p class="m0-preview-loading">预览失败: ${esc(String(e))}</p>`;
      showPreviewReport({ ok: false, messages: [String(e)] });
    }
  }

  function hidePreviewStatus() {
    const el = $("#preview-status");
    el.classList.add("hidden");
    el.classList.remove("warn", "error");
    el.innerHTML = "";
  }

  function showLinkAuditPreviewHint(doc) {
    const audit = doc?.link_audit;
    if (!audit || audit.ok || state.viewMode === "source") return;
    const n = audit.summary?.issue_count || 0;
    if (!n) return;
    const el = $("#preview-status");
    el.classList.remove("hidden", "error");
    el.classList.add("warn");
    el.innerHTML = `<span>⚠ 链接一致性：${n} 个配置入口未在正文中挂接为可点击 [[…]] · 请打开「配置 → 链接」点击「挂接…」</span>`;
  }

  function showPreviewReport(report) {
    const el = $("#preview-status");
    if (!report || state.viewMode === "source") {
      hidePreviewStatus();
      return;
    }
    if (report.ok) {
      hidePreviewStatus();
      setStatus(
        state.currentPath || "就绪",
        `预览 OK · 公式 ${report.mathRendered}/${report.mathExpected}`
      );
      return;
    }
    el.classList.remove("hidden");
    el.classList.add("warn");
    const parts = report.messages?.length
      ? report.messages
      : ["预览未完全成功"];
    el.innerHTML =
      `<span>⚠ 预览自检：${esc(parts.join("；"))}</span>` +
      (report.mathErrors?.length
        ? `<details><summary>TeX 错误</summary><pre>${esc(report.mathErrors.join("\n"))}</pre></details>`
        : "");
    setStatus(
      state.currentPath || "预览",
      `公式 ${report.mathRendered}/${report.mathExpected} · 有问题`
    );
  }

  function isGraphSidebarTab() {
    return state.sidebarTab === "graph2d" || state.sidebarTab === "graph3d";
  }

  function activeGraphLayout() {
    return state.sidebarTab === "graph3d" ? state.graphLayout3d : state.graphLayout2d;
  }

  function isNodeInCurrentGraphLayout(nodeId) {
    if (!nodeId) return false;
    const layout = activeGraphLayout();
    if (!layout?.nodes?.length) return false;
    return layout.nodes.some((n) => n.id === nodeId);
  }

  function graphIdsInCurrentLayout(ids) {
    return (ids || []).filter((id) => isNodeInCurrentGraphLayout(id));
  }

  function renderKpList(doc) {
    const el = $("#kp-list");
    const kpCount = $("#kp-count");
    if (!doc) {
      if (el) el.innerHTML = '<div class="empty">请选择文件</div>';
      if (kpCount) kpCount.textContent = "";
      return;
    }
    const rawKps = doc.knowledge_points || [];
    const proposals = doc.heading_proposals || [];
    const kps = [...rawKps].sort((a, b) => {
      const la = a?.range_resolved?.start_line ?? a?.range?.start?.line_hint ?? 0;
      const lb = b?.range_resolved?.start_line ?? b?.range?.start?.line_hint ?? 0;
      return la - lb;
    });
    if (kpCount) kpCount.textContent = kps.length ? `${kps.length}` : "";

    if (!kps.length && !proposals.length) {
      el.innerHTML = '<div class="empty">无知识点 · 右键条目或点「配置」</div>';
      return;
    }
    if (!kps.length) {
      el.innerHTML =
        `<div class="empty">无正式 KP · ${proposals.length} 个标题提议<br><span class="m0-muted">点「配置」→ 待确认</span></div>`;
      return;
    }

    el.innerHTML = kps
      .map((kp) => {
        const rr = kp.range_resolved || {};
        let cls = "m0-kp-item";
        if (kp.id === state.activeKpId) cls += " active";
        let meta = kp.id;
        if (rr.ok) {
          meta = `L${rr.start_line}–${rr.end_line}`;
        } else if (rr.error) {
          cls += rr.error.includes("not_found") ? " error" : " warn";
          meta = errorLabel(rr.error);
        }
        const tags = (kp.tags || [])
          .map((t) => `<span class="m0-tag">${esc(t)}</span>`)
          .join("");
        return `<div class="${cls}" data-kp="${esc(kp.id)}">
          <div class="m0-kp-name">${esc(kp.name || kp.id)}</div>
          <div class="m0-kp-meta"><span>${esc(meta)}</span>${tags}</div>
        </div>`;
      })
      .join("");

    el.querySelectorAll(".m0-kp-item").forEach((node) => {
      node.addEventListener("click", () => onKpClick(node.dataset.kp));
      node.addEventListener("mouseenter", (e) => {
        if (shouldSuppressHoverHighlight(e)) return;
        highlightKpHover(node.dataset.kp);
        highlightGraphFromKp(node.dataset.kp);
      });
      node.addEventListener("mouseleave", (e) => {
        if (shouldSuppressHoverHighlight(e)) return;
        clearKpHoverHighlight();
        clearGraphKpHover();
      });
      node.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (window.MemoriaKpContextMenu) {
          MemoriaKpContextMenu.show(node.dataset.kp, e.clientX, e.clientY);
        }
      });
    });
  }

  function kpRangeMeta(kp) {
    const rr = kp.range_resolved || {};
    if (rr.ok) return { text: `L${rr.start_line}–${rr.end_line}`, ok: true };
    if (rr.error) return { text: errorLabel(rr.error), ok: false };
    return { text: "未配置", ok: false };
  }

  function isKpCoveredByConfirmed(proposal, confirmedKps) {
    const name = (proposal.name || "").trim();
    const cid = (proposal.concept_id || "").trim();
    return confirmedKps.some((kp) => {
      const kid = (kp.id || "").trim();
      const kn = (kp.name || "").trim();
      return (name && (kid === name || kn === name)) || (cid && kid === cid);
    });
  }

  function m4SuggestBlockHtml(kind) {
    const kpItems =
      kind === "kp"
        ? `<div class="m0-suggest-item m0-suggest-placeholder">
            <span class="m0-suggest-score">87%</span>
            <span class="m0-suggest-label">policy-gradient</span>
            <span class="m0-muted">本文件 · 可合并</span>
            <button type="button" class="m0-btn secondary m0-btn--sm" disabled>合并</button>
          </div>
          <div class="m0-suggest-item m0-suggest-placeholder">
            <span class="m0-suggest-score">72%</span>
            <span class="m0-suggest-label">q-learning</span>
            <span class="m0-muted">q-learning.md · 跨文件</span>
            <button type="button" class="m0-btn secondary m0-btn--sm" disabled>创建引用</button>
          </div>`
        : `<div class="m0-suggest-item m0-suggest-placeholder">
            <span class="m0-suggest-score">91%</span>
            <span class="m0-suggest-label">[[q-learning|Q-learning]]</span>
            <span class="m0-muted">正文 L42 未绑定</span>
            <button type="button" class="m0-btn secondary m0-btn--sm" disabled>创建路由</button>
          </div>`;
    const title =
      kind === "kp"
        ? "模糊匹配 · 创建 / 合并知识点（M4）"
        : "模糊匹配 · 推荐链接路由（M4）";
    const hint =
      kind === "kp"
        ? "M4 接入 SearchKernel 后：按 name、tags、description Lexical 精排；近重复合并在此展示。"
        : "M4 接入后：扫描正文 [[…]] 与配置差异；未绑定链接与多目标一并列出。";
    return `<details class="m0-suggest-block">
      <summary>${esc(title)}</summary>
      <p class="m0-config-hint">${esc(hint)}</p>
      <div class="m0-suggest-list">${kpItems}</div>
    </details>`;
  }

  function configTabCounts(doc) {
    const confirmedKps = doc.knowledge_points || [];
    const headingP = doc.heading_proposals || [];
    const mentionP = doc.mention_proposals || [];
    const definitionP = doc.definition_proposals || [];
    const pendingHeading = headingP.filter((p) => !isKpCoveredByConfirmed(p, confirmedKps));
    const pendingMention = mentionP.filter((p) => !isKpCoveredByConfirmed(p, confirmedKps));
    const pendingDefinition = definitionP.filter((p) => !isKpCoveredByConfirmed(p, confirmedKps));
    const fileLinks = (doc.sidecar?.links || []).filter((l) => l && typeof l === "object");
    return {
      kp: confirmedKps.length,
      links: fileLinks.length,
      pending: pendingHeading.length + pendingMention.length + pendingDefinition.length,
      pendingHeading,
      pendingMention,
      pendingDefinition,
      confirmedKps,
      fileLinks,
      headingP,
      mentionP,
      definitionP,
    };
  }

  function renderConfigTabBar(counts, activeTab) {
    const tabs = [
      { id: "kp", label: "知识点", count: counts.kp },
      { id: "links", label: "链接", count: counts.links },
      { id: "pending", label: "待确认", count: counts.pending },
    ];
    return `<div class="m0-config-tabs" role="tablist">
      ${tabs
        .map(
          (t) =>
            `<button type="button" class="m0-config-tab${activeTab === t.id ? " active" : ""}" data-config-tab="${t.id}" role="tab" aria-selected="${activeTab === t.id}">${esc(t.label)} <span class="m0-tab-count">${t.count}</span></button>`
        )
        .join("")}
    </div>`;
  }

  function renderConfigKpTab(counts) {
    const { confirmedKps } = counts;
    let html = `<div class="m0-config-toolbar m0-btn-bar m0-btn-bar--start">
      <button type="button" class="m0-btn primary m0-btn--sm" data-config-new-kp>新建知识点</button>
      <span class="m0-muted">空白新建，或在「待确认」Tab 配置标题提议</span>
    </div>`;
    if (!confirmedKps.length) {
      html += `<p class="m0-muted">暂无正式知识点 · 在「待确认」Tab 配置并确认提议</p>`;
    } else {
      html += confirmedKps
        .map((kp) => {
          const meta = kpRangeMeta(kp);
          const metaCls = meta.ok ? "m0-muted" : "m0-config-range-warn";
          const tags = (kp.tags || [])
            .map((t) => `<span class="m0-tag">${esc(t)}</span>`)
            .join("");
          return `<div class="m0-config-item">
            <div class="m0-config-item-main">
              <span class="m0-config-kp-name">${esc(kp.name || kp.id)}</span>
              <span class="${metaCls}">${esc(meta.text)}</span>
              ${tags}
            </div>
            <div class="m0-config-item-actions">
              <button type="button" class="m0-btn primary m0-btn--sm" data-kp-config="${esc(kp.id)}">配置</button>
              <button type="button" class="m0-btn danger m0-btn--sm" data-kp-delete="${esc(kp.id)}" title="从配置中删除该知识点">删除</button>
            </div>
          </div>`;
        })
        .join("");
    }
    return html;
  }

  function linkAuditFor(anchor, audit) {
    return (audit?.links || []).find((x) => x.anchor_text === anchor) || null;
  }

  function linkAuditBadgeHtml(entry) {
    if (!entry) return "";
    if (entry.status === "ok" && entry.targets_resolved !== false) return "";
    const parts = [];
    if (entry.status === "missing_body") {
      parts.push('<span class="m0-link-audit-bad" title="配置已有，正文无 [[]] 入口">缺正文入口</span>');
    } else if (entry.status === "stale_instance") {
      parts.push('<span class="m0-link-audit-bad" title="instances 行号与正文不一致">实例失效</span>');
    } else if (entry.status === "partial") {
      parts.push('<span class="m0-link-audit-warn" title="部分实例未挂接">部分挂接</span>');
    }
    if (entry.targets_resolved === false) {
      parts.push('<span class="m0-link-audit-warn" title="跳转目标无法解析">目标未解析</span>');
    }
    return parts.join(" ");
  }

  function renderLinkAuditBanner(audit) {
    if (!audit || audit.ok) return "";
    const n = audit.summary?.issue_count || 0;
    if (!n) return "";
    const first = (audit.links || []).find(
      (x) => x.status !== "ok" || x.targets_resolved === false
    );
    const fixBtn = first
      ? `<button type="button" class="m0-btn secondary m0-btn--sm" data-link-audit-fix="${esc(first.anchor_text)}">打开首个问题</button>`
      : "";
    return `<div class="m0-link-audit-banner" role="alert">
      <strong>链接一致性</strong>
      <span>${n} 个跳转入口存在一致性问题 · 在列表中点「匹配」勾选位置后，再点面板内「确认并包裹所选」（仅保存路由不会改写正文）</span>
      ${fixBtn}
    </div>`;
  }

  function defaultLinkSearchOptions() {
    return { fuzzy_whitespace: true, fuzzy_suggest: true, case_insensitive: false };
  }

  function renderLinkSearchOptionsHtml(prefix, options) {
    const o = { ...defaultLinkSearchOptions(), ...(options || {}) };
    return `<div class="m0-link-search-options" data-search-options-root="${prefix}">
      <label class="m0-link-search-opt" title="如「深度RL」可匹配正文「深度 RL」">
        <input type="checkbox" data-search-opt="fuzzy_whitespace" ${o.fuzzy_whitespace ? "checked" : ""} />
        忽略空格
      </label>
      <label class="m0-link-search-opt" title="输入时可推荐已有链接文本、标题或正文匹配">
        <input type="checkbox" data-search-opt="fuzzy_suggest" ${o.fuzzy_suggest ? "checked" : ""} />
        模糊推荐
      </label>
      <label class="m0-link-search-opt m0-link-search-opt-future" title="预留 · 后续接搜索引擎">
        <input type="checkbox" data-search-opt="case_insensitive" disabled ${o.case_insensitive ? "checked" : ""} />
        忽略大小写
      </label>
    </div>`;
  }

  function readLinkSearchOptionsFromRoot(rootEl) {
    const opts = defaultLinkSearchOptions();
    if (!rootEl) return opts;
    rootEl.querySelectorAll("[data-search-opt]").forEach((el) => {
      const key = el.getAttribute("data-search-opt");
      if (key && Object.prototype.hasOwnProperty.call(opts, key)) {
        opts[key] = !!el.checked;
      }
    });
    return opts;
  }

  function readEditorLinkSearchOptions() {
    const p = state.linkPicker;
    const root = document.getElementById("link-edit-search-options");
    const opts = readLinkSearchOptionsFromRoot(root);
    if (p) p.searchOptions = opts;
    return opts;
  }

  function readConfigLinkSearchOptions() {
    const root = document.querySelector(
      "#config-link-match-panel [data-search-options-root]"
    );
    const opts = readLinkSearchOptionsFromRoot(root);
    if (state.configLinkMatch) state.configLinkMatch.searchOptions = opts;
    return opts;
  }

  async function openLinkMatchFromConfig(anchorText) {
    const anchor = (anchorText || "").trim();
    if (!anchor || !state.currentPath) return;
    const link = (state.doc?.sidecar?.links || []).find(
      (l) => l.anchor_text === anchor
    );
    const audit = linkAuditFor(anchor, state.doc?.link_audit);
    await openLinkMatchInConfig({
      anchorText: anchor,
      targetIds: link?.targets || [],
      poolIds: link?.pool || link?.targets || [],
      edgeType: link?.edge_type || "reference",
      configHighlight: anchor,
      preselectLines:
        audit?.suggested_lines?.length
          ? audit.suggested_lines
          : audit?.instance_lines?.length
            ? audit.instance_lines
            : undefined,
    });
  }

  function renderLinkMatchPanelHtml(m, variant) {
    if (!m) {
      return variant === "editor"
        ? '<p class="m0-muted m0-link-match-empty">填写匹配文本后扫描正文</p>'
        : "";
    }
    if (m.loading) {
      return '<p class="m0-muted m0-link-match-empty">扫描中…</p>';
    }

    const anchor = m.anchorText;
    const attached = m.matches.filter((x) => x.attached && !x.excluded).length;
    const excluded = m.matches.filter((x) => x.excluded).length;
    const hint =
      `共 ${m.matches.length} 处 · 已挂接 ${attached} 处 · 排除 ${excluded} 处 · 已选 ${m.selected.size} 处`;
    const prefix = variant === "config" ? "config-link-match" : "link-editor-match";
    const panelId =
      variant === "config" ? "config-link-match-panel" : "link-editor-match-panel";
    const panelCls =
      variant === "config" ? "m0-config-link-match m0-link-match-panel" : "m0-link-editor-match m0-link-match-panel";

    const rows = m.matches
      .map((row) => {
        const checked = m.selected.has(row.line);
        const disabled = row.is_substring || row.excluded || row.blocked;
        const cls =
          "m0-link-match-row" +
          (checked ? " is-selected" : "") +
          (row.is_substring ? " is-substring" : "") +
          (row.excluded ? " is-excluded" : "") +
          (row.blocked ? " is-blocked" : "");
        const title = row.blocked
          ? (row.block_reason || "与其它跳转占用区域重叠") + " · 点击定位到该行"
          : row.is_substring
          ? "子串匹配，不可挂接 · 点击定位到该行"
          : row.excluded
            ? "已排除 · 点击定位到该行"
            : "点击整行切换勾选并定位到该行";
        const checkCell = disabled
          ? `<span class="m0-link-match-check-placeholder" aria-hidden="true">—</span>`
          : `<input type="checkbox" data-match-check="${row.line}" ${checked ? "checked" : ""} aria-label="L${row.line}" />`;
        return `<div class="${cls}" data-match-line="${row.line}" data-match-locate="${disabled ? "1" : "0"}" title="${esc(title)}">
          ${checkCell}
          <div class="m0-link-match-main">
            <div class="m0-link-match-head">
              <span class="m0-link-match-line">L${row.line}</span>
              ${row.section ? `<span class="m0-link-match-section">${esc(row.section)}</span>` : ""}
              <span class="m0-link-match-badge">${esc(matchRowBadge(row))}</span>
            </div>
            <div class="m0-link-match-snippet">${highlightSnippet(row.snippet, row.matched_text)}</div>
          </div>
        </div>`;
      })
      .join("");

    const closeBtn =
      variant === "config"
        ? `<button type="button" class="m0-icon-btn" id="config-link-match-close" title="收起">×</button>`
        : "";

    let footer = "";
    if (variant === "config") {
      footer = `<div class="m0-config-link-match-footer m0-btn-bar">
        <button type="button" class="m0-btn secondary" id="config-link-match-cancel">取消</button>
        <button type="button" class="m0-btn primary" id="config-link-match-confirm" ${m.selected.size ? "" : "disabled"}>确认并包裹所选</button>
      </div>`;
    }

    const searchOpts = m.searchOptions || defaultLinkSearchOptions();
    const searchOptsHtml =
      variant === "config" ? renderLinkSearchOptionsHtml(prefix, searchOpts) : "";

    const selectableRows = m.matches.filter(
      (row) => !row.is_substring && !row.excluded && !row.blocked
    );
    const allSelected =
      selectableRows.length > 0 &&
      selectableRows.every((row) => m.selected.has(row.line));
    const allBtnLabel = allSelected ? "取消全选" : "全选";

    return `<div id="${panelId}" class="${panelCls}">
      <div class="m0-link-match-panel-header">
        <span class="m0-link-match-panel-title">匹配「${esc(m.anchorText)}」</span>
        <span class="m0-muted m0-link-match-panel-hint">${esc(hint)}</span>
        ${closeBtn}
      </div>
      ${searchOptsHtml}
      <div class="m0-link-match-toolbar m0-btn-bar m0-btn-bar--start">
        <button type="button" class="m0-btn secondary m0-btn--sm" id="${prefix}-all">${esc(allBtnLabel)}</button>
        <button type="button" class="m0-btn secondary m0-btn--sm" id="${prefix}-plain">仅选未包裹</button>
      </div>
      <div class="m0-link-match-list">${rows || '<p class="m0-muted">未找到匹配</p>'}</div>
      ${footer}
    </div>`;
  }

  function renderConfigLinkMatchPanelHtml() {
    return renderLinkMatchPanelHtml(state.configLinkMatch, "config");
  }

  function renderLinkEditorMatchPanelHtml() {
    return renderLinkMatchPanelHtml(state.linkPicker?.match, "editor");
  }

  function configLinkMatchSlotEl(anchor) {
    const a = (anchor || "").trim();
    if (!a) return null;
    return document.querySelector(
      `.m0-config-link-match-slot[data-link-match-slot="${CSS.escape(a)}"]`
    );
  }

  function _readLinkMatchListScroll(rootEl) {
    const list = rootEl?.querySelector(".m0-link-match-list");
    return list ? list.scrollTop : 0;
  }

  function _restoreLinkMatchListScroll(rootEl, scrollTop) {
    if (scrollTop == null) return;
    const list = rootEl?.querySelector(".m0-link-match-list");
    if (list) list.scrollTop = scrollTop;
  }

  function refreshConfigLinkMatchPanel() {
    const prevSlot = configLinkMatchSlotEl(state.configLinkMatch?.anchorText);
    const prevScroll = _readLinkMatchListScroll(prevSlot);
    document.querySelectorAll(".m0-config-link-match-slot").forEach((el) => {
      el.innerHTML = "";
    });
    if (!state.configLinkMatch) return;
    const slot = configLinkMatchSlotEl(state.configLinkMatch.anchorText);
    if (!slot) return;
    slot.innerHTML = renderConfigLinkMatchPanelHtml();
    _restoreLinkMatchListScroll(slot, prevScroll);
    if (state.configLinkMatch) {
      document.getElementById("config-link-match-panel")?.scrollIntoView({
        block: "nearest",
        behavior: "smooth",
      });
    }
  }

  function refreshLinkEditorMatchPanel() {
    const slot = document.getElementById("link-editor-match-slot");
    if (!slot) return;
    const prevScroll = _readLinkMatchListScroll(slot);
    slot.innerHTML = renderLinkEditorMatchPanelHtml();
    _restoreLinkMatchListScroll(slot, prevScroll);
    syncLinkEditorSaveButtons();
  }

  let linkEditorMatchRescanTimer = null;
  let anchorSuggestTimer = null;
  let anchorSuggestHideTimer = null;

  function hideAnchorSuggest() {
    $("#link-anchor-suggest")?.classList.add("hidden");
  }

  function scheduleAnchorSuggest() {
    clearTimeout(anchorSuggestTimer);
    anchorSuggestTimer = setTimeout(() => refreshAnchorSuggest(), 220);
  }

  async function refreshAnchorSuggest() {
    const p = state.linkPicker;
    const box = $("#link-anchor-suggest");
    if (!p || !box || !state.currentPath) return;
    readLinkEditorFields();
    const q = (p.anchorText || "").trim();
    const opts = readEditorLinkSearchOptions();
    if (!opts.fuzzy_suggest || q.length < 2) {
      hideAnchorSuggest();
      return;
    }
    try {
      const res = await call("suggest_link_anchor_texts", state.currentPath, q, opts);
      const items = (res.suggestions || []).filter((s) => s.text && s.text !== q);
      if (!items.length) {
        hideAnchorSuggest();
        return;
      }
      box.innerHTML = items
        .map(
          (s) =>
            `<button type="button" class="m0-suggest-pick" data-anchor-pick="${esc(s.text)}" title="${esc(s.source || "")}">
              <span class="m0-suggest-label">${esc(s.text)}</span>
              <span class="m0-muted">${esc(s.source || "")}</span>
            </button>`
        )
        .join("");
      box.classList.remove("hidden");
    } catch (_) {
      hideAnchorSuggest();
    }
  }

  function applyAnchorSuggestion(text) {
    const anchor = (text || "").trim();
    if (!anchor) return;
    const input = $("#link-edit-anchor");
    if (input) input.value = anchor;
    const p = state.linkPicker;
    if (p) {
      p.anchorText = anchor;
      p.displayText = anchor;
    }
    hideAnchorSuggest();
    loadLinkEditorMatch();
    syncLinkEditorSaveButtons();
  }

  function scheduleLinkEditorMatchRescan() {
    clearTimeout(linkEditorMatchRescanTimer);
    linkEditorMatchRescanTimer = setTimeout(() => loadLinkEditorMatch(), 350);
  }

  async function loadLinkEditorMatch() {
    const p = state.linkPicker;
    if (!p || (p.mode !== "edit" && p.mode !== "create") || !state.currentPath) return;
    const anchorEl = $("#link-edit-anchor");
    if (anchorEl && !$("#link-modal").classList.contains("hidden")) {
      readLinkEditorFields();
    }
    const anchor = (p.anchorText || "").trim();
    if (!anchor) {
      p.match = null;
      refreshLinkEditorMatchPanel();
      return;
    }

    const searchOptions = {
      ...readEditorLinkSearchOptions(),
      route_anchor: (() => {
        const old = (p.oldAnchorText || "").trim();
        const cur = (p.anchorText || "").trim();
        if (old && old !== cur) return old;
        return old || cur;
      })(),
    };
    p.match = {
      anchorText: anchor,
      matches: [],
      selected: new Set(),
      loading: true,
      searchOptions,
    };
    refreshLinkEditorMatchPanel();

    let scan;
    try {
      scan = await call(
        "scan_link_text_matches",
        state.currentPath,
        anchor,
        searchOptions
      );
    } catch (e) {
      p.match = null;
      refreshLinkEditorMatchPanel();
      setStatus("扫描失败", String(e.message || e));
      return;
    }
    if (scan.status !== "ok") {
      p.match = null;
      refreshLinkEditorMatchPanel();
      return;
    }

    const matches = scan.matches || [];
    const auditEntry = linkAuditFor(anchor, state.doc?.link_audit);
    const preselect = matchPreselectLines(
      matches,
      p.createSelectionLines?.length
        ? p.createSelectionLines
        : auditEntry?.suggested_lines?.length
          ? auditEntry.suggested_lines
          : auditEntry?.instance_lines?.length
            ? auditEntry.instance_lines
            : null
    );

    p.match = {
      anchorText: anchor,
      matches,
      selected: new Set(preselect),
      loading: false,
      searchOptions,
    };
    refreshLinkEditorMatchPanel();
  }

  function closeConfigLinkMatch() {
    state.configLinkMatch = null;
    refreshConfigLinkMatchPanel();
    document
      .querySelectorAll(".m0-config-link-item.is-match-active")
      .forEach((el) => el.classList.remove("is-match-active"));
  }

  function renderConfigLinksTab(counts, highlightAnchor, linkAudit) {
    const { fileLinks } = counts;
    let html = renderLinkAuditBanner(linkAudit);
    html += `<div class="m0-config-toolbar m0-btn-bar m0-btn-bar--start">
      <button type="button" class="m0-btn primary m0-btn--sm" id="config-new-link">新建链接</button>
      <span class="m0-muted">正文选区右键也可创建 · 源码/预览均可拖选 · 匹配文本须与 [[…]] 一致</span>
    </div>`;
    if (!fileLinks.length) {
      html += `<p class="m0-muted">尚未配置链接 · [[文本]] 按知识点 id 或文件名解析</p>`;
    } else {
      html += fileLinks
        .map((link) => {
          const anchor = link.anchor_text || "";
          const targets = (link.targets || []).join(", ");
          const pool =
            (link.pool || []).length > (link.targets || []).length
              ? ` · 备选 ${link.pool.length}`
              : "";
          const auditEntry = linkAuditFor(anchor, linkAudit);
          const badge = linkAuditBadgeHtml(auditEntry);
          const needsAttach =
            auditEntry &&
            (auditEntry.status !== "ok" || auditEntry.preview_attached_count === 0);
          const matchActive =
            state.configLinkMatch?.anchorText === anchor ? " is-match-active" : "";
          const hl =
            (highlightAnchor && anchor === highlightAnchor ? " is-highlight" : "") +
            matchActive +
            (needsAttach ? " has-audit-issue" : "");
          const instHint =
            auditEntry && auditEntry.preview_attached_count > 0
              ? ` · 已挂接 ${auditEntry.preview_attached_count} 处`
              : auditEntry && auditEntry.body_wrapped_count > 0
                ? ` · 正文 ${auditEntry.body_wrapped_count} 处 [[]]`
                : "";
          const matchPanelHtml =
            state.configLinkMatch?.anchorText === anchor
              ? renderConfigLinkMatchPanelHtml()
              : "";
          return `<div class="m0-config-link-block">
          <div class="m0-config-item m0-config-link-item${hl}" data-link-anchor="${esc(anchor)}" role="button" tabindex="0" title="点击在下方匹配正文位置">
            <div class="m0-config-item-main">
              <code class="m0-config-anchor">${esc(anchor)}</code>
              ${badge}
              <span class="m0-muted">→ ${esc(targets || "（未绑定）")}${pool}${instHint}</span>
              ${auditEntry?.issues?.length ? `<span class="m0-link-audit-detail" title="${esc(auditEntry.issues.join("；"))}">${esc(auditEntry.issues[0])}</span>` : ""}
            </div>
            <div class="m0-config-item-actions">
              <button type="button" class="m0-btn secondary m0-btn--sm" data-link-match="${esc(anchor)}" title="在下方选择正文挂接位置">匹配</button>
              <button type="button" class="m0-btn primary m0-btn--sm" data-link-edit="${esc(anchor)}">编辑</button>
              <button type="button" class="m0-btn danger m0-btn--sm" data-link-delete="${esc(anchor)}" title="删除跳转入口及正文 [[]]">删除</button>
            </div>
          </div>
          <div class="m0-config-link-match-slot" data-link-match-slot="${esc(anchor)}">${matchPanelHtml}</div>
          </div>`;
        })
        .join("");
    }
    return html;
  }

  function renderConfigPendingSuggestBlocks() {
    return m4SuggestBlockHtml("kp") + m4SuggestBlockHtml("link");
  }

  function renderConfigPendingTab(counts) {
    const { pendingHeading, pendingMention, pendingDefinition, headingP, mentionP, definitionP } =
      counts;
    const kbTotal = state.kbPending?.total;
    let html = `<div class="m0-config-toolbar m0-btn-bar m0-btn-bar--start">
      <button type="button" class="m0-btn secondary m0-btn--sm" data-config-sync-pending>刷新待确认</button>
      ${kbTotal != null ? `<span class="m0-muted">全库 ${kbTotal} 项</span>` : ""}
    </div>`;
    if (!counts.pending) {
      html += `<p class="m0-muted">无待确认提议 · 扫描标题、段落 mention 或定义句（「X 是…」）后出现在此</p>`;
      html += renderConfigPendingSuggestBlocks();
      return html;
    }
    if (pendingHeading.length) {
      html += `<div class="m0-config-kp-group"><div class="m0-config-kp-group-title">标题提议 (${pendingHeading.length})</div>`;
      html += pendingHeading
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = headingP.indexOf(p);
          return `<div class="m0-config-item">
            <div class="m0-config-item-main">
              <span class="m0-config-tag">标题</span>
              <span class="m0-config-kp-name">${esc(p.name)}</span>
              <span class="m0-muted">${lines}</span>
            </div>
            <div class="m0-config-item-actions">
              <button type="button" class="m0-btn primary m0-btn--sm" data-heading-proposal="${idx}">配置并确认</button>
              ${p.pending_id ? `<button type="button" class="m0-btn secondary m0-btn--sm" data-dismiss-pending="${esc(p.pending_id)}">忽略</button>` : ""}
            </div>
          </div>`;
        })
        .join("");
      html += `</div>`;
    }
    if (pendingMention.length) {
      html += `<div class="m0-config-kp-group"><div class="m0-config-kp-group-title">段落提议 (${pendingMention.length})</div>`;
      html += pendingMention
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = mentionP.indexOf(p);
          return `<div class="m0-config-item">
            <div class="m0-config-item-main">
              <span class="m0-config-tag">段落</span>
              <span class="m0-config-kp-name">${esc(p.name)}</span>
              <span class="m0-muted">${lines}</span>
            </div>
            <div class="m0-config-item-actions">
              <button type="button" class="m0-btn primary m0-btn--sm" data-mention-proposal="${idx}">配置并确认</button>
              ${p.pending_id ? `<button type="button" class="m0-btn secondary m0-btn--sm" data-dismiss-pending="${esc(p.pending_id)}">忽略</button>` : ""}
            </div>
          </div>`;
        })
        .join("");
      html += `</div>`;
    }
    if (pendingDefinition.length) {
      html += `<div class="m0-config-kp-group"><div class="m0-config-kp-group-title">定义句提议 (${pendingDefinition.length})</div>`;
      html += pendingDefinition
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = definitionP.indexOf(p);
          return `<div class="m0-config-item">
            <div class="m0-config-item-main">
              <span class="m0-config-tag">定义</span>
              <span class="m0-config-kp-name">${esc(p.name)}</span>
              <span class="m0-muted">${lines}</span>
            </div>
            <div class="m0-config-item-actions">
              <button type="button" class="m0-btn primary m0-btn--sm" data-definition-proposal="${idx}">配置并确认</button>
            </div>
          </div>`;
        })
        .join("");
      html += `</div>`;
    }
    html += renderConfigPendingSuggestBlocks();
    return html;
  }

  function bindConfigModalEvents(doc, counts, opts) {
    const { headingP, mentionP, definitionP } = counts;
    const body = $("#config-body");

    body.querySelectorAll("[data-config-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.configTab = btn.dataset.configTab;
        renderConfigModal();
      });
    });

    body.querySelector("#config-new-link")?.addEventListener("click", () => {
      state.configTab = "links";
      closeConfigModal();
      openLinkEditor({
        mode: "create",
        anchorText: "",
        displayText: "",
        returnTo: "config",
      });
    });

    body.querySelector("[data-config-new-kp]")?.addEventListener("click", () => {
      closeConfigModal();
      openKpModalForCreate({ returnTo: "config" });
    });

    body.querySelector("[data-link-audit-fix]")?.addEventListener("click", (e) => {
      openLinkMatchFromConfig(e.currentTarget.getAttribute("data-link-audit-fix") || "");
    });

    body.querySelectorAll("[data-link-edit]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const anchor = btn.getAttribute("data-link-edit") || "";
        closeConfigModal();
        openLinkEditor({
          mode: "edit",
          anchorText: anchor,
          displayText: anchor,
          returnTo: "config",
          configHighlight: anchor,
        });
      });
    });
    body.querySelectorAll("[data-link-match]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        openLinkMatchFromConfig(btn.getAttribute("data-link-match") || "");
      });
    });
    body.querySelectorAll("[data-link-delete]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        deleteLinkFromConfig(btn.getAttribute("data-link-delete") || "");
      });
    });
    body.querySelectorAll("[data-link-anchor]").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        const anchor = row.dataset.linkAnchor;
        openLinkMatchFromConfig(anchor);
      });
    });

    body.querySelectorAll("[data-kp-config]").forEach((btn) => {
      btn.addEventListener("click", () => {
        closeConfigModal();
        openKpModal(btn.dataset.kpConfig, { returnTo: "config", tab: "range" });
      });
    });
    body.querySelectorAll("[data-kp-delete]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteKp(btn.getAttribute("data-kp-delete") || "", { refreshConfig: true });
      });
    });
    body.querySelectorAll("[data-heading-proposal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = headingP[+btn.dataset.headingProposal];
        openKpModalFromProposal(p, { returnTo: "config" });
      });
    });
    body.querySelectorAll("[data-mention-proposal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = mentionP[+btn.dataset.mentionProposal];
        openKpModalFromProposal(p, { returnTo: "config" });
      });
    });
    body.querySelectorAll("[data-definition-proposal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = definitionP[+btn.dataset.definitionProposal];
        openKpModalFromProposal(p, { returnTo: "config" });
      });
    });

    body.querySelector("[data-config-sync-pending]")?.addEventListener("click", () => {
      syncPendingFromConfig();
    });
    body.querySelectorAll("[data-dismiss-pending]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        dismissPendingItem(btn.getAttribute("data-dismiss-pending") || "", {
          refreshConfig: true,
        });
      });
    });

    const highlightAnchor = opts.highlightLinkTarget || null;
    if (highlightAnchor && state.configTab === "links") {
      requestAnimationFrame(() => {
        body.querySelector(".m0-config-link-item.is-highlight")?.scrollIntoView({
          block: "nearest",
          behavior: "smooth",
        });
      });
    }
  }

  function renderConfigModal() {
    if (!state.doc) return;
    const doc = state.doc;
    const opts = state.configModalOpts || {};
    const counts = configTabCounts(doc);
    const validation = doc.sidecar_validation || { ok: true, errors: [], warnings: [] };
    const hasSidecar = !!doc.sidecar;
    const tab = state.configTab || "kp";

    $("#config-title").textContent = `文件配置 — ${basename(doc.path)}`;

    let html = `<p class="m0-config-summary">元数据 ${hasSidecar ? "已配置" : "未创建"} · 知识点 ${counts.kp} · 链接 ${counts.links} · 待确认 ${counts.pending}</p>`;
    if (validation.errors?.length) {
      html += `<p class="m0-config-error">错误：${esc(validation.errors.join("；"))}</p>`;
    }
    if (validation.warnings?.length) {
      html += `<p class="m0-config-warn">警告：${esc(validation.warnings.join("；"))}</p>`;
    }
    if (tab === "links" && doc.link_audit && !doc.link_audit.ok) {
      const n = doc.link_audit.summary?.issue_count || 0;
      if (n) {
        html += `<p class="m0-config-warn">链接一致性：${n} 个入口未在正文中挂接为可点击 [[…]]</p>`;
      }
    }

    html += renderConfigTabBar(counts, tab);
    html += `<div class="m0-config-tab-panel" role="tabpanel">`;
    if (tab === "kp") html += renderConfigKpTab(counts);
    else if (tab === "links")
      html += renderConfigLinksTab(
        counts,
        opts.highlightLinkTarget || null,
        doc.link_audit || null
      );
    else html += renderConfigPendingTab(counts);
    html += `</div>`;

    $("#config-body").innerHTML = html;
    bindConfigModalEvents(doc, counts, opts);
  }

  function openConfigModal(opts = {}) {
    if (!state.doc) return;
    const { tab, ...rest } = opts;
    state.configModalOpts = rest;
    if (tab !== undefined) state.configTab = tab;
    else if (!state.configTab) state.configTab = "kp";
    refreshKbPendingSummary().finally(() => {
      renderConfigModal();
      $("#config-modal").classList.remove("hidden");
    });
  }

  async function dismissPendingItem(pendingId, opts = {}) {
    if (!pendingId) return;
    try {
      const res = await call("dismiss_pending", pendingId);
      if (res.status !== "ok") {
        setStatusError(res.message || "忽略失败");
        return;
      }
      if (state.currentPath) {
        const doc = await call("load_document", state.currentPath);
        if (doc.status === "ok") {
          state.doc = doc;
          renderKpList(doc);
        }
      }
      await refreshKbPendingSummary();
      if (opts.refreshConfig) renderConfigModal();
      setStatus("已忽略待确认项");
    } catch (e) {
      setStatusError("忽略失败", e.message);
    }
  }

  async function syncPendingFromConfig() {
    try {
      setStatus("刷新待确认…");
      const res = await call("sync_pending");
      if (res.status !== "ok") {
        setStatusError(res.message || "刷新失败");
        return;
      }
      if (state.currentPath) {
        const doc = await call("load_document", state.currentPath);
        if (doc.status === "ok") {
          state.doc = doc;
          renderKpList(doc);
        }
      }
      await refreshKbPendingSummary();
      renderConfigModal();
      setStatus("待确认已刷新", `${res.pending_count ?? 0} 项`);
    } catch (e) {
      setStatusError("刷新失败", e.message);
    }
  }

  function closeConfigModal() {
    closeConfigLinkMatch();
    $("#config-modal").classList.add("hidden");
  }

  function renderKpModalTabs(activeTab) {
    const tabs = [
      { id: "range", label: "范围" },
      { id: "identity", label: "标识" },
      { id: "tags", label: "标签" },
      { id: "edges", label: "边" },
    ];
    return `<div class="m0-config-tabs m0-kp-tabs" role="tablist">
      ${tabs
        .map(
          (t) =>
            `<button type="button" class="m0-config-tab${activeTab === t.id ? " active" : ""}" data-kp-tab="${t.id}" role="tab">${esc(t.label)}</button>`
        )
        .join("")}
    </div>`;
  }

  function getAssistHostEl() {
    if (state.assist?.host === "kp") return $("#kp-body");
    return $("#assist-body");
  }

  function getAssistPreviewWrapEl() {
    return getAssistHostEl()?.querySelector("[data-range-preview]") || null;
  }

  function rangeRadioGroup(which) {
    const host = state.assist?.host || "modal";
    return `range-${which}-${host}`;
  }

  function lineHasRangeSnippet(lineNo) {
    const lines = state.doc?.lines;
    if (!lines?.length || !Number.isFinite(lineNo)) return false;
    const n = Math.max(1, Math.min(lines.length, Math.floor(lineNo)));
    return !!(lines[n - 1] || "").trim();
  }

  function pickAssistEndLine(kp, startLine) {
    const rr = kp.range_resolved || {};
    const rng = kp.range || {};
    const total = state.doc?.lines?.length || 0;
    let endLine = rr.end_line || rng.end?.line_hint || startLine;
    if (total > 0) {
      endLine = Math.max(1, Math.min(total, endLine));
      if (!lineHasRangeSnippet(endLine)) {
        let fallback = Math.max(1, Math.min(total, startLine));
        for (let n = Math.max(1, startLine); n <= total; n++) {
          if (lineHasRangeSnippet(n)) fallback = n;
        }
        endLine = fallback;
      }
    }
    return endLine;
  }

  function ensureKpRangeAssist(kp) {
    const rr = kp.range_resolved || {};
    const startLine = rr.start_line || kp.range?.start?.line_hint || 1;
    const endLine = pickAssistEndLine(kp, startLine);
    state.assist = {
      host: "kp",
      mode: "kp",
      kpId: kp.id,
      name: kp.name || kp.id,
      startLine,
      endLine,
      error: rr.error,
      startCandidates: rr.start_candidates || [],
      endCandidates: rr.end_candidates || [],
      returnTo: state.kpPanel?.returnTo || null,
    };
    if (!state.assistPreviewMode) state.assistPreviewMode = "source";
  }

  function buildRangeEditorHtml(a) {
    let html = "";
    if (a.error) {
      html += `<p class="m0-config-range-warn">${esc(errorLabel(a.error))}</p>`;
    }
    const total = state.doc?.lines?.length || 0;
    html += `<div class="m0-assist-line-inputs">
      <label>起点行 <input type="number" class="m0-line-input" data-range-start min="1" max="${total || ""}" value="${a.startLine}"></label>
      <label>终点行 <input type="number" class="m0-line-input" data-range-end min="1" max="${total || ""}" value="${a.endLine}"></label>
      <span class="m0-muted">滚轮可微调行号${total ? ` · 正文共 ${total} 行` : ""}</span>
    </div>`;
    if (a.startCandidates.length > 1) {
      html += `<p class="m0-range-candidates-label"><strong>起点候选</strong></p>`;
      html += `<div class="m0-range-candidates">${renderCandidates("start", a.startCandidates)}</div>`;
    }
    if (a.endCandidates.length > 1) {
      html += `<p class="m0-range-candidates-label"><strong>终点候选</strong></p>`;
      html += `<div class="m0-range-candidates">${renderCandidates("end", a.endCandidates)}</div>`;
    }
    html += `<div data-range-preview class="m0-assist-preview-wrap"></div>`;
    html += `<p class="m0-muted">调整行号即更新高亮；预览区可切换源码 / Markdown。</p>`;
    return html;
  }

  function bindRangeCandidateRadios(hostEl) {
    hostEl.querySelectorAll('input[type="radio"][name^="range-"]').forEach((inp) => {
      inp.addEventListener("change", () => {
        const which = inp.name.replace(/^range-(\w+)-.*$/, "$1");
        const line = +inp.value;
        const startEl = hostEl.querySelector("[data-range-start]");
        const endEl = hostEl.querySelector("[data-range-end]");
        if (which === "start" && startEl) startEl.value = line;
        else if (endEl) endEl.value = line;
        setAssistScrollFocus(which);
        renderAssistPreview();
      });
    });
  }

  function bindRangeEditor(hostEl) {
    if (!hostEl) return;
    ["start", "end"].forEach((which) => {
      const el = hostEl.querySelector(
        which === "start" ? "[data-range-start]" : "[data-range-end]"
      );
      if (!el) return;
      el.addEventListener("focus", () => {
        const prev = state.assistScrollFocus;
        setAssistScrollFocus(which);
        const wrap = getAssistPreviewWrapEl();
        if (wrap && prev !== which) applyAssistPreviewLayout(wrap, which);
      });
      el.addEventListener(
        "wheel",
        (e) => {
          e.preventDefault();
          setAssistScrollFocus(which);
          const total = state.doc?.lines?.length || 1;
          const delta = e.deltaY < 0 ? 1 : -1;
          const next = Math.max(1, Math.min(total, (+el.value || 1) + delta));
          el.value = String(next);
          renderAssistPreview();
        },
        { passive: false }
      );
      el.addEventListener("input", () => scheduleAssistPreview(which));
      el.addEventListener("change", () => {
        setAssistScrollFocus(which);
        renderAssistPreview();
      });
    });
    bindRangeCandidateRadios(hostEl);
  }

  function syncKpModalLayout(tab) {
    const body = $("#kp-body");
    body?.classList.toggle("m0-modal-body-kp-range", tab === "range");
    body?.classList.toggle("m0-modal-body-kp-edges", tab === "edges");
  }

  function syncKpModalFooter(_tab, isCreate = false) {
    const saveBtn = $("#kp-save");
    const deleteBtn = $("#kp-delete");
    if (!saveBtn) return;
    if (deleteBtn) deleteBtn.classList.toggle("hidden", isCreate);
    if (_tab === "edges") {
      saveBtn.classList.add("hidden");
    } else {
      saveBtn.classList.remove("hidden");
      saveBtn.disabled = false;
      saveBtn.textContent = "确定";
      saveBtn.title = "确定";
    }
  }

  function clearKpRangeAssist() {
    if (state.assist?.host !== "kp") return;
    clearTimeout(state.assistPreviewTimer);
    state.assistLastView = null;
    state.assist = null;
  }

  function syncKpPanelFromForm() {
    const panel = state.kpPanel;
    if (!panel) return;
    const tab = panel.tab || "range";

    if (panel.mode === "create") {
      const idEl = $("#kp-field-id");
      const nameEl = $("#kp-field-name");
      if (idEl) panel.kpId = idEl.value.trim();
      if (nameEl) panel.name = nameEl.value.trim();
      panel.draft = panel.draft || {};
      const descEl = $("#kp-desc-input");
      if (descEl) panel.draft.description = descEl.value;
    } else {
      panel.draft = panel.draft || {};
      if (tab === "identity") {
        const idEl = $("#kp-field-id");
        const nameEl = $("#kp-field-name");
        if (idEl) panel.draft.id = idEl.value.trim();
        if (nameEl) panel.draft.name = nameEl.value.trim();
      } else if (tab === "tags") {
        syncKpTagStateFromDom(panel);
        const descEl = $("#kp-desc-input");
        if (descEl) panel.draft.description = descEl.value;
      }
    }

    const host = getAssistHostEl();
    let startLine = panel.startLine;
    let endLine = panel.endLine;
    if (host) {
      const startEl = host.querySelector("[data-range-start]");
      const endEl = host.querySelector("[data-range-end]");
      if (startEl) startLine = Math.max(1, parseInt(startEl.value, 10) || startLine || 1);
      if (endEl) endLine = Math.max(1, parseInt(endEl.value, 10) || endLine || startLine || 1);
    } else if (state.assist?.host === "kp") {
      startLine = state.assist.startLine ?? startLine;
      endLine = state.assist.endLine ?? endLine;
    }
    if (startLine != null) panel.startLine = startLine;
    if (endLine != null) panel.endLine = endLine;
    if (state.assist?.host === "kp") {
      if (panel.mode === "create") {
        state.assist.kpId = panel.kpId || state.assist.kpId;
        state.assist.name = panel.name || state.assist.name;
      }
      state.assist.startLine = panel.startLine;
      state.assist.endLine = panel.endLine;
    }
  }

  function renderKpModalBody() {
    const panel = state.kpPanel;
    if (!panel || !state.doc) return;

    const isCreate = panel.mode === "create";
    let kp;
    if (isCreate) {
      kp = {
        id: panel.kpId || "",
        name: panel.name || "",
        tags: [],
        range: {
          start: { line_hint: panel.startLine },
          end: { line_hint: panel.endLine },
        },
        range_resolved: {
          ok: true,
          start_line: panel.startLine,
          end_line: panel.endLine,
        },
      };
    } else {
      kp = (state.doc.knowledge_points || []).find((k) => k.id === panel.kpId);
      if (!kp) return;
    }

    const tab = panel.tab || "range";
    $("#kp-title").textContent = isCreate
      ? `新建知识点${panel.name ? " — " + panel.name : ""}`
      : `知识点 — ${kp.name || kp.id}`;
    syncKpModalLayout(tab);
    syncKpModalFooter(tab, isCreate);

    let content = "";
    if (tab === "range") {
      if (isCreate) {
        state.assist = {
          host: "kp",
          mode: "create",
          kpId: panel.kpId || "",
          name: panel.name || "",
          startLine: panel.startLine || 1,
          endLine: panel.endLine || panel.startLine || 1,
          error: null,
          startCandidates: [],
          endCandidates: [],
          returnTo: panel.returnTo || null,
        };
      } else {
        ensureKpRangeAssist(kp);
        if (panel.startLine != null) state.assist.startLine = panel.startLine;
        if (panel.endLine != null) state.assist.endLine = panel.endLine;
      }
      state.assistScrollFocus = "start";
      state.assistLastView = null;
      content = `<div class="m0-kp-tab-panel m0-kp-range-panel">${buildRangeEditorHtml(state.assist)}</div>`;
    } else if (tab === "identity") {
      clearKpRangeAssist();
      const idVal = isCreate ? kp.id : (panel.draft?.id ?? kp.id);
      const nameVal = isCreate ? (kp.name || kp.id) : (panel.draft?.name ?? kp.name ?? kp.id);
      content = `<div class="m0-kp-tab-panel"><div class="m0-kp-form">
        <label class="m0-link-field">id <input type="text" id="kp-field-id" value="${esc(idVal)}" autocomplete="off" spellcheck="false"></label>
        <label class="m0-link-field">名称 <input type="text" id="kp-field-name" value="${esc(nameVal)}" autocomplete="off"></label>
        <p class="m0-config-hint">${isCreate ? "新建知识点请先在此填写 id 与名称，再到「范围」调整行号。" : "修改 id 将全库同步链接配置与正文 [[…]]（显示文字保持不变）。"}</p>
        ${isCreate ? "" : `<div id="kp-merge-suggest" class="m0-kp-merge-suggest hidden"></div>`}
      </div></div>`;
    } else if (tab === "edges") {
      clearKpRangeAssist();
      content = renderKpEdgesTabHtml(kp);
    } else {
      clearKpRangeAssist();
      ensureKpTagState(panel, kp);
      const desc = isCreate
        ? panel.draft?.description ?? kp.description ?? ""
        : panel.draft?.description != null
          ? panel.draft.description
          : kp.description || "";
      content = `<div class="m0-kp-tab-panel"><div class="m0-kp-form">
        ${renderKpTagsEditorHtml(panel, kp, isCreate)}
        ${renderKpAliasEditorHtml(panel, kp)}
        <label class="m0-link-field">描述
          <textarea id="kp-desc-input" rows="3" placeholder="可选；用于检索与图谱提示">${esc(desc)}</textarea>
        </label>
        ${renderKpDescCandEditorHtml(panel, kp)}
        <div class="m0-kp-tags-zone-toolbar">
          <button type="button" id="kp-sync-aux" class="m0-btn secondary m0-btn--sm">同步检索 aux</button>
          <button type="button" id="kp-suggest-desc" class="m0-btn secondary m0-btn--sm">建议描述</button>
        </div>
        <p class="m0-config-hint">${isCreate ? "描述可选；确认创建时会一并保存。tag/别名/描述候选可提前配置。" : "已选 tag/别名保存后参与检索；候选区点击应用；「同步检索 aux」合并隐式索引提议。"}</p>
      </div></div>`;
    }

    $("#kp-body").innerHTML = renderKpModalTabs(tab) + content;
    bindKpModalEvents(kp);

    if (tab === "range") {
      bindRangeEditor($("#kp-body"));
      renderAssistPreview({ forceScroll: true });
    } else if (tab === "identity" && state.kpPanel?.mode === "edit") {
      loadKpMergeSuggestions(kp.id);
    } else if (tab === "tags") {
      const bindKpId = isCreate ? (panel.kpId || "") : kp.id;
      bindKpTagsEditor(bindKpId, kp);
      bindKpAliasEditor(bindKpId, kp);
      bindKpDescCandEditor(bindKpId);
      bindKpDescSuggest(bindKpId);
      bindKpSyncAux(bindKpId);
    } else if (tab === "edges") {
      bindKpEdgesEvents(kp);
    }
  }

  /* ── KP Edges Tab ── */

  function kpNameForId(kpId) {
    const kp = (state.doc?.knowledge_points || []).find((k) => k.id === kpId);
    return kp ? (kp.name || kp.id) : kpId;
  }

  function deriveKpEdgesForCurrentFile(kp) {
    const kps = state.doc?.knowledge_points || [];
    const sidecar = state.doc?.sidecar || {};
    const links = sidecar.links || [];
    const sidecarEdges = sidecar.edges || [];
    const kpId = kp.id;

    const edges = [];
    const seen = new Set();

    function addEdge(e) {
      const key = [e.type, e.source_id, e.target_id, e.no_build ? 1 : 0].join("|");
      if (seen.has(key)) return;
      seen.add(key);
      edges.push(e);
    }

    // 1. Contain edges: derive from KP range nesting
    const ranges = kps
      .filter((k) => {
        const rr = k.range_resolved || {};
        return rr.ok && rr.start_line != null && rr.end_line != null;
      })
      .map((k) => ({
        kp_id: k.id,
        start: k.range_resolved.start_line,
        end: k.range_resolved.end_line,
      }));

    const noBuildSet = new Set();
    for (const e of sidecarEdges) {
      if (!e || typeof e !== "object") continue;
      if (!e.no_build) continue;
      if ((e.type || "").trim().toLowerCase() !== "contain") continue;
      const sid = (e.source_id || "").trim();
      for (const tgt of e.targets || []) {
        noBuildSet.add(sid + "|" + String(tgt).trim());
      }
    }

    for (const inner of ranges) {
      for (const outer of ranges) {
        if (outer.kp_id === inner.kp_id) continue;
        if (outer.start > inner.start || inner.end > outer.end) continue;
        if (!(outer.start < inner.start || inner.end < outer.end)) continue;
        // Only include if outer or inner is current KP
        if (outer.kp_id !== kpId && inner.kp_id !== kpId) continue;
        const nb = noBuildSet.has(outer.kp_id + "|" + inner.kp_id);
        addEdge({
          type: "contain",
          source_id: outer.kp_id,
          target_id: inner.kp_id,
          relevance: 0.9,
          derived: true,
          origin: "range",
          no_build: nb,
        });
      }
    }

    // 2. Link-derived edges (reference/extend from links[])
    for (const link of links) {
      if (!link || typeof link !== "object") continue;
      const targets = (link.targets || []).filter((t) => t && String(t).trim());
      if (!targets.length) continue;
      const instances = link.instances || [];
      const instLines = instances
        .filter((inst) => inst && typeof inst === "object" && inst.line != null)
        .map((inst) => parseInt(inst.line, 10))
        .filter((n) => n > 0);
      if (!instLines.length) continue;

      const edgeType = normalizeLinkEdgeType(link.edge_type);
      const anchorText = link.anchor_text || "";

      for (const line of instLines) {
        const sourceKps = ranges
          .filter((r) => r.start <= line && line <= r.end)
          .filter((r) => {
            const inner = ranges.find((rr) => rr.kp_id !== r.kp_id && rr.start >= r.start && rr.end <= r.end && rr.start <= line && line <= rr.end && (rr.start > r.start || rr.end < r.end));
            return !inner;
          })
          .map((r) => r.kp_id);

        const effectiveSources = sourceKps.length ? sourceKps : (link.source_id ? [link.source_id] : []);
        for (const sourceId of effectiveSources) {
          if (sourceId !== kpId) continue;
          for (const rawTid of targets) {
            const tid = String(rawTid).trim();
            const tgtProps = loadTargetEdgesFromSidecar(link, edgeType);
            const tgtEdge = tgtProps[tid] || defaultTargetEdgeProps(edgeType);
            addEdge({
              type: tgtEdge.edge_type,
              source_id: sourceId,
              target_id: tid,
              relevance: tgtEdge.relevance,
              derived: true,
              origin: "link",
              anchor_text: anchorText,
              line,
            });
          }
        }
      }
    }

    // 3. Pure sidecar edges (from edges[] without no_build)
    for (const e of sidecarEdges) {
      if (!e || typeof e !== "object") continue;
      if (e.no_build) continue;
      const sid = (e.source_id || "").trim();
      if (!sid) continue;
      if (sid !== kpId) continue;
      const et = normalizeLinkEdgeType(e.type);
      for (const rawTid of e.targets || []) {
        const tid = String(rawTid || "").trim();
        if (!tid) continue;
        addEdge({
          type: et,
          source_id: sid,
          target_id: tid,
          relevance: e.relevance != null ? Math.max(0, Math.min(1, Number(e.relevance))) : defaultRelevanceForEdgeType(et),
          derived: false,
          origin: "sidecar_edge",
        });
      }
    }

    // 4. no_build entries from edges[] (for display)
    for (const e of sidecarEdges) {
      if (!e || typeof e !== "object") continue;
      if (!e.no_build) continue;
      const sid = (e.source_id || "").trim();
      const et = (e.type || "").trim().toLowerCase();
      if (et !== "contain") continue;
      if (!sid) continue;
      if (sid !== kpId) continue;
      for (const rawTid of e.targets || []) {
        const tid = String(rawTid || "").trim();
        if (!tid) continue;
        addEdge({
          type: "contain",
          source_id: sid,
          target_id: tid,
          relevance: 0.9,
          derived: true,
          origin: "range",
          no_build: true,
        });
      }
    }

    return edges;
  }

  function edgeTypeBadgeHtml(type) {
    const colors = { contain: "#5cb85c", reference: "#5bc0de", extend: "#f0ad4e" };
    const labels = { contain: "包含", reference: "引用", extend: "扩展" };
    const color = colors[type] || "#999";
    const label = labels[type] || type;
    return `<span class="m0-edge-type-badge" style="background:${color};color:#fff">${esc(label)}</span>`;
  }

  function edgeOriginLabel(edge) {
    if (edge.origin === "link") return "链接";
    if (edge.origin === "range") return "嵌套";
    if (edge.origin === "sidecar_edge") return "手动";
    return edge.origin || "";
  }

  function renderKpEdgesTabHtml(kp) {
    const kpId = kp.id;
    const edges = deriveKpEdgesForCurrentFile(kp);
    const outgoing = edges.filter((e) => e.source_id === kpId);
    const incoming = edges.filter((e) => e.target_id === kpId && e.source_id !== kpId);

    let html = `<div class="m0-kp-tab-panel m0-kp-edges-panel">`;

    // Outgoing edges section
    html += `<div class="m0-edge-section">`;
    html += `<h4 class="m0-edge-section-title">出边 <span class="m0-tab-count">${outgoing.length}</span></h4>`;
    if (outgoing.length) {
      html += `<div class="m0-edge-list">`;
      for (const e of outgoing) {
        html += `<div class="m0-edge-item" data-edge-type="${esc(e.type)}" data-edge-source="${esc(e.source_id)}" data-edge-target="${esc(e.target_id)}" data-edge-origin="${esc(e.origin || "")}" ${e.anchor_text ? `data-edge-anchor="${esc(e.anchor_text)}"` : ""}>`;
        html += `<div class="m0-edge-main">`;
        html += edgeTypeBadgeHtml(e.type);
        html += `<span class="m0-edge-arrow">${esc(kpNameForId(e.source_id))} → ${esc(kpNameForId(e.target_id))}</span>`;
        html += `<span class="m0-edge-relevance">${e.relevance != null ? Number(e.relevance).toFixed(2) : "—"}</span>`;
        html += `<span class="m0-edge-origin">${esc(edgeOriginLabel(e))}</span>`;
        if (e.no_build) html += `<span class="m0-edge-no-build">已抑制</span>`;
        html += `</div>`;
        html += `<div class="m0-edge-actions">`;
        if (e.type === "contain" && e.no_build) {
          html += `<button type="button" class="m0-btn secondary m0-btn--sm m0-edge-btn-restore" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}">恢复</button>`;
        } else if (e.type === "contain" && !e.no_build) {
          html += `<button type="button" class="m0-btn secondary m0-btn--sm m0-edge-btn-suppress" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}">抑制</button>`;
        }
        if (e.origin === "sidecar_edge") {
          html += `<button type="button" class="m0-btn danger m0-btn--sm m0-edge-btn-delete" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}" data-type="${esc(e.type)}">删除</button>`;
        }
        if (e.origin === "link" && e.anchor_text) {
          html += `<button type="button" class="m0-btn secondary m0-btn--sm m0-edge-btn-config-link" data-anchor="${esc(e.anchor_text)}">配置链接</button>`;
        }
        html += `</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    } else {
      html += `<p class="m0-muted">无出边</p>`;
    }
    html += `</div>`;

    // Incoming edges section
    html += `<div class="m0-edge-section">`;
    html += `<h4 class="m0-edge-section-title">入边 <span class="m0-tab-count">${incoming.length}</span></h4>`;
    if (incoming.length) {
      html += `<div class="m0-edge-list">`;
      for (const e of incoming) {
        html += `<div class="m0-edge-item" data-edge-type="${esc(e.type)}" data-edge-source="${esc(e.source_id)}" data-edge-target="${esc(e.target_id)}" data-edge-origin="${esc(e.origin || "")}">`;
        html += `<div class="m0-edge-main">`;
        html += edgeTypeBadgeHtml(e.type);
        html += `<span class="m0-edge-arrow">${esc(kpNameForId(e.source_id))} → ${esc(kpNameForId(e.target_id))}</span>`;
        html += `<span class="m0-edge-relevance">${e.relevance != null ? Number(e.relevance).toFixed(2) : "—"}</span>`;
        html += `<span class="m0-edge-origin">${esc(edgeOriginLabel(e))}</span>`;
        if (e.no_build) html += `<span class="m0-edge-no-build">已抑制</span>`;
        html += `</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    } else {
      html += `<p class="m0-muted">入边需全库扫描，当前仅显示本文件内入边</p>`;
    }
    html += `</div>`;

    // Create new edge form
    html += `<div class="m0-edge-section m0-edge-create-form">`;
    html += `<h4 class="m0-edge-section-title">新建边</h4>`;
    html += `<div class="m0-edge-create-fields">`;
    html += `<label class="m0-link-field">目标 KP <input type="text" id="kp-edge-target" placeholder="输入 KP id" autocomplete="off" spellcheck="false"></label>`;
    html += `<label class="m0-link-field">边类型 <select id="kp-edge-type"><option value="reference">引用 (reference)</option><option value="extend">扩展 (extend)</option></select></label>`;
    html += `<label class="m0-link-field">关联度 <input type="range" id="kp-edge-relevance" min="0" max="1" step="0.05" value="0.7"><span id="kp-edge-relevance-val">0.70</span></label>`;
    html += `<button type="button" id="kp-edge-create-btn" class="m0-btn primary m0-btn--sm">新建</button>`;
    html += `</div>`;
    html += `</div>`;

    html += `</div>`;
    return html;
  }

  async function reloadDocAndRefreshEdges(kpId) {
    const res = await call("load_document", state.currentPath);
    if (res.status === "ok") {
      state.doc = res;
    }
    renderKpModalBody();
  }

  function bindKpEdgesEvents(kp) {
    const body = $("#kp-body");
    if (!body) return;

    // Suppress contain edge
    body.querySelectorAll(".m0-edge-btn-suppress").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const parentId = btn.dataset.source;
        const childId = btn.dataset.target;
        if (!state.currentPath || !parentId || !childId) return;
        setStatus("抑制 contain 边…");
        const res = await call("set_contain_no_build", state.currentPath, parentId, childId, true);
        if (res.status !== "ok") {
          setStatus(res.message || "操作失败");
          return;
        }
        setStatus("已抑制 contain 边");
        await reloadDocAndRefreshEdges(kp.id);
      });
    });

    // Restore contain edge (remove no_build)
    body.querySelectorAll(".m0-edge-btn-restore").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const parentId = btn.dataset.source;
        const childId = btn.dataset.target;
        if (!state.currentPath || !parentId || !childId) return;
        setStatus("恢复 contain 边…");
        const res = await call("set_contain_no_build", state.currentPath, parentId, childId, false);
        if (res.status !== "ok") {
          setStatus(res.message || "操作失败");
          return;
        }
        setStatus("已恢复 contain 边");
        await reloadDocAndRefreshEdges(kp.id);
      });
    });

    // Delete pure sidecar edge
    body.querySelectorAll(".m0-edge-btn-delete").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const sourceId = btn.dataset.source;
        const targetId = btn.dataset.target;
        const edgeType = btn.dataset.type;
        if (!state.currentPath || !sourceId || !targetId || !edgeType) return;
        if (!window.confirm(`删除边 ${sourceId} → ${targetId} (${edgeType})？`)) return;
        setStatus("删除边…");
        const res = await call("delete_edge", state.currentPath, sourceId, targetId, edgeType);
        if (res.status !== "ok") {
          setStatus(res.message || "操作失败");
          return;
        }
        setStatus("已删除边");
        await reloadDocAndRefreshEdges(kp.id);
      });
    });

    // Configure link (opens link editor for that anchor)
    body.querySelectorAll(".m0-edge-btn-config-link").forEach((btn) => {
      btn.addEventListener("click", () => {
        const anchor = btn.dataset.anchor;
        if (!anchor) return;
        const link = (state.doc?.sidecar?.links || []).find((l) => l.anchor_text === anchor);
        if (!link) return;
        openLinkEditor({
          anchorText: anchor,
          displayText: anchor,
          mode: "edit",
          returnTo: "kp",
        });
      });
    });

    // Create new edge form
    const createBtn = $("#kp-edge-create-btn");
    const relSlider = $("#kp-edge-relevance");
    const relVal = $("#kp-edge-relevance-val");
    if (relSlider && relVal) {
      relSlider.addEventListener("input", () => {
        relVal.textContent = Number(relSlider.value).toFixed(2);
      });
    }

    // Target KP autocomplete
    const targetInput = $("#kp-edge-target");
    if (targetInput) {
      targetInput.addEventListener("input", () => {
        const val = targetInput.value.trim().toLowerCase();
        const existing = body.querySelector(".m0-edge-target-datalist");
        if (existing) existing.remove();
        if (!val) return;
        const kpIds = (state.doc?.knowledge_points || [])
          .map((k) => k.id)
          .filter((id) => id.toLowerCase().includes(val) && id !== kp.id);
        const linkTargets = state.linkTargetList || [];
        const allIds = [...new Set([...kpIds, ...linkTargets.filter((t) => t.toLowerCase().includes(val))])];
        if (!allIds.length) return;
        const datalist = document.createElement("div");
        datalist.className = "m0-edge-target-datalist";
        allIds.slice(0, 10).forEach((id) => {
          const opt = document.createElement("div");
          opt.className = "m0-edge-target-option";
          opt.textContent = id;
          opt.addEventListener("click", () => {
            targetInput.value = id;
            datalist.remove();
          });
          datalist.appendChild(opt);
        });
        targetInput.parentNode.appendChild(datalist);
      });
      targetInput.addEventListener("blur", () => {
        setTimeout(() => {
          const dl = body.querySelector(".m0-edge-target-datalist");
          if (dl) dl.remove();
        }, 200);
      });
    }

    if (createBtn) {
      createBtn.addEventListener("click", async () => {
        const targetId = ($("#kp-edge-target")?.value || "").trim();
        const edgeType = ($("#kp-edge-type")?.value || "reference").trim();
        const relevance = parseFloat($("#kp-edge-relevance")?.value || "0.7");
        if (!targetId) {
          setStatusError("请输入目标 KP id");
          return;
        }
        if (!state.currentPath) return;
        setStatus("新建边…");
        const res = await call("create_edge", state.currentPath, kp.id, targetId, edgeType, relevance);
        if (res.status !== "ok") {
          setStatus(res.message || "新建边失败");
          return;
        }
        setStatus("已新建边");
        await reloadDocAndRefreshEdges(kp.id);
      });
    }
  }

  function loadKpTagCandidatesFromKp(kp) {
    const raw = kp?.tag_candidates || kp?.tagCandidates || [];
    if (!Array.isArray(raw)) return [];
    return raw
      .map((c) => {
        if (typeof c === "string") return { tag: c.trim(), source: "user", score: null };
        if (!c || typeof c !== "object") return null;
        const tag = String(c.tag || "").trim();
        if (!tag) return null;
        return {
          tag,
          source: c.source === "system" ? "system" : c.source === "feedback" ? "feedback" : "user",
          score: c.score != null ? Number(c.score) : null,
        };
      })
      .filter(Boolean);
  }

  function serializeKpTagCandidates(candidates) {
    return (candidates || []).map((c) => {
      const item = { tag: c.tag, source: c.source === "system" ? "system" : c.source === "feedback" ? "feedback" : "user" };
      if (c.score != null && Number.isFinite(Number(c.score))) {
        item.score = Math.round(Number(c.score) * 10) / 10;
      }
      return item;
    });
  }

  function ensureKpTagState(panel, kp) {
    panel.draft = panel.draft || {};
    if (panel.draft.tagState) return panel.draft.tagState;
    let selected = [];
    if (Array.isArray(panel.draft.tags)) {
      selected = [...panel.draft.tags];
    } else if (typeof panel.draft.tags === "string") {
      selected = parseTagsInput(panel.draft.tags);
    } else {
      selected = [...(kp?.tags || [])];
    }
    const selectedSet = new Set(selected.map((t) => t.toLowerCase()));
    const candidates = loadKpTagCandidatesFromKp(kp).filter(
      (c) => !selectedSet.has(c.tag.toLowerCase())
    );
    panel.draft.tagState = { selected, candidates };
    return panel.draft.tagState;
  }

  function syncKpTagStateFromDom(panel) {
    if (!panel?.draft?.tagState) return;
    panel.draft.tags = [...panel.draft.tagState.selected];
    panel.draft.tagCandidates = serializeKpTagCandidates(panel.draft.tagState.candidates);
    if (panel.draft.aliasState) {
      panel.draft.aliases = [...panel.draft.aliasState.selected];
      panel.draft.aliasCandidates = serializeKpAliasCandidates(panel.draft.aliasState.candidates);
    }
    if (panel.draft.descCandState) {
      panel.draft.descriptionCandidates = serializeKpDescCandidates(
        panel.draft.descCandState.candidates
      );
    }
  }

  function loadKpAliasCandidatesFromKp(kp) {
    const raw = kp?.alias_candidates || kp?.aliasCandidates || [];
    if (!Array.isArray(raw)) return [];
    return raw
      .map((c) => {
        if (typeof c === "string") return { alias: c.trim(), source: "user" };
        if (!c || typeof c !== "object") return null;
        const alias = String(c.alias || "").trim();
        if (!alias) return null;
        const src = c.source === "system" ? "system" : c.source === "feedback" ? "feedback" : "user";
        return { alias, source: src };
      })
      .filter(Boolean);
  }

  function serializeKpAliasCandidates(candidates) {
    return (candidates || []).map((c) => ({
      alias: c.alias,
      source: c.source === "system" ? "system" : c.source === "feedback" ? "feedback" : "user",
    }));
  }

  function ensureKpAliasState(panel, kp) {
    panel.draft = panel.draft || {};
    if (panel.draft.aliasState) return panel.draft.aliasState;
    let selected = Array.isArray(panel.draft.aliases)
      ? [...panel.draft.aliases]
      : [...(kp?.aliases || [])];
    const selectedSet = new Set(selected.map((a) => a.toLowerCase()));
    const nameLower = String(kp?.name || "").trim().toLowerCase();
    if (nameLower) selectedSet.add(nameLower);
    const candidates = loadKpAliasCandidatesFromKp(kp).filter(
      (c) => !selectedSet.has(c.alias.toLowerCase())
    );
    panel.draft.aliasState = { selected, candidates };
    return panel.draft.aliasState;
  }

  function loadKpDescCandidatesFromKp(kp) {
    const raw = kp?.description_candidates || kp?.descriptionCandidates || [];
    if (!Array.isArray(raw)) return [];
    return raw
      .map((c) => {
        if (typeof c === "string") return { text: c.trim(), source: "user" };
        if (!c || typeof c !== "object") return null;
        const text = String(c.text || "").trim();
        if (!text) return null;
        const src = c.source === "system" ? "system" : c.source === "feedback" ? "feedback" : "user";
        return { text, source: src };
      })
      .filter(Boolean);
  }

  function serializeKpDescCandidates(candidates) {
    return (candidates || []).map((c) => ({
      text: c.text,
      source: c.source === "system" ? "system" : c.source === "feedback" ? "feedback" : "user",
    }));
  }

  function ensureKpDescCandState(panel, kp) {
    panel.draft = panel.draft || {};
    if (panel.draft.descCandState) return panel.draft.descCandState;
    const current = String(
      panel.draft.description != null ? panel.draft.description : kp?.description || ""
    ).trim();
    const candidates = loadKpDescCandidatesFromKp(kp).filter((c) => c.text !== current);
    panel.draft.descCandState = { candidates };
    return panel.draft.descCandState;
  }

  function renderKpAliasChip(alias, kind, opts = {}) {
    const dismiss = `<button type="button" class="m0-kp-tag-chip-btn" data-alias-dismiss="${esc(alias)}" title="移除">×</button>`;
    const kindCls =
      kind === "selected"
        ? "m0-kp-tag-pick--selected"
        : kind === "cand-user"
          ? "m0-kp-tag-pick--cand-user"
          : "m0-kp-tag-pick--cand-system";
    const title = kind === "selected" ? "点击移到候选" : "点击应用到已选";
    return `<span class="m0-kp-tag-pick ${kindCls}" data-alias="${esc(alias)}" data-alias-kind="${kind === "selected" ? "selected" : "candidate"}" title="${title}">
      <span class="m0-kp-tag-chip-label">${esc(alias)}</span>
      <span class="m0-kp-tag-chip-actions">${dismiss}</span>
    </span>`;
  }

  function renderKpDescCandChip(text, source) {
    const kindCls = source === "user" ? "m0-kp-tag-pick--cand-user" : "m0-kp-tag-pick--cand-system";
    const short = text.length > 72 ? text.slice(0, 70) + "…" : text;
    return `<span class="m0-kp-tag-pick ${kindCls} m0-kp-desc-cand" data-desc-cand="${esc(text)}" title="点击填入描述">
      <span class="m0-kp-tag-chip-label">${esc(short)}</span>
      <button type="button" class="m0-kp-tag-chip-btn" data-desc-dismiss="${esc(text)}" title="移除">×</button>
    </span>`;
  }

  function renderKpAliasEditorHtml(panel, kp) {
    const as = ensureKpAliasState(panel, kp);
    const selHtml = as.selected.length
      ? as.selected.map((a) => renderKpAliasChip(a, "selected")).join("")
      : `<span class="m0-muted m0-kp-tags-empty">暂无已选别名</span>`;
    const candHtml = as.candidates.length
      ? as.candidates
          .map((c) =>
            renderKpAliasChip(c.alias, c.source === "user" ? "cand-user" : "cand-system")
          )
          .join("")
      : `<span class="m0-muted m0-kp-tags-empty">同步 aux 或下方新建</span>`;
    return `<div class="m0-kp-tags-editor m0-kp-alias-editor" id="kp-alias-editor">
      <div class="m0-kp-tags-zone m0-kp-tags-zone--selected">
        <div class="m0-kp-tags-zone-head">已选别名 <span class="m0-muted">参与检索</span></div>
        <div id="kp-alias-selected" class="m0-kp-tags-chips">${selHtml}</div>
      </div>
      <div class="m0-kp-tags-zone m0-kp-tags-zone--candidate">
        <div class="m0-kp-tags-zone-head">别名候选</div>
        <div class="m0-kp-tags-zone-toolbar">
          <div class="m0-kp-tag-create-row">
            <input type="text" id="kp-alias-new-input" placeholder="新建别名" autocomplete="off" spellcheck="false" />
            <button type="button" id="kp-alias-add-btn" class="m0-btn secondary m0-btn--sm">加入候选</button>
          </div>
        </div>
        <div id="kp-alias-candidates" class="m0-kp-tags-chips">${candHtml}</div>
      </div>
    </div>`;
  }

  function renderKpDescCandEditorHtml(panel, kp) {
    const ds = ensureKpDescCandState(panel, kp);
    const candHtml = ds.candidates.length
      ? ds.candidates
          .map((c) => renderKpDescCandChip(c.text, c.source))
          .join("")
      : `<span class="m0-muted m0-kp-tags-empty">同步 aux 后显示描述候选</span>`;
    return `<div class="m0-kp-desc-cand-editor" id="kp-desc-cand-editor">
      <div class="m0-kp-tags-zone-head">描述候选 <span class="m0-muted">点击填入上方描述框</span></div>
      <div id="kp-desc-candidates" class="m0-kp-tags-chips">${candHtml}</div>
    </div>`;
  }

  function refreshKpAliasEditorDom(panel, kp) {
    const sel = $("#kp-alias-selected");
    const cand = $("#kp-alias-candidates");
    if (!panel?.draft?.aliasState || !sel) return;
    const as = panel.draft.aliasState;
    sel.innerHTML = as.selected.length
      ? as.selected.map((a) => renderKpAliasChip(a, "selected")).join("")
      : `<span class="m0-muted m0-kp-tags-empty">暂无已选别名</span>`;
    if (cand) {
      cand.innerHTML = as.candidates.length
        ? as.candidates
            .map((c) =>
              renderKpAliasChip(c.alias, c.source === "user" ? "cand-user" : "cand-system")
            )
            .join("")
        : `<span class="m0-muted m0-kp-tags-empty">同步 aux 或下方新建</span>`;
    }
  }

  function refreshKpDescCandEditorDom(panel, kp) {
    const root = $("#kp-desc-candidates");
    if (!panel?.draft?.descCandState || !root) return;
    const ds = panel.draft.descCandState;
    root.innerHTML = ds.candidates.length
      ? ds.candidates.map((c) => renderKpDescCandChip(c.text, c.source)).join("")
      : `<span class="m0-muted m0-kp-tags-empty">同步 aux 后显示描述候选</span>`;
  }

  function renderKpTagChip(tag, kind, opts = {}) {
    const score =
      opts.score != null
        ? `<span class="m0-kp-tag-pick-score">${esc(String(Math.round(opts.score)))}</span>`
        : "";
    const dismiss = `<button type="button" class="m0-kp-tag-chip-btn" data-tag-dismiss="${esc(tag)}" title="移除">×</button>`;
    const kindCls =
      kind === "selected"
        ? "m0-kp-tag-pick--selected"
        : kind === "cand-user"
          ? "m0-kp-tag-pick--cand-user"
          : "m0-kp-tag-pick--cand-system";
    const title =
      kind === "selected" ? "点击移到候选" : "点击应用到已选";
    return `<span class="m0-kp-tag-pick ${kindCls}" data-tag="${esc(tag)}" data-tag-kind="${kind === "selected" ? "selected" : "candidate"}" title="${title}">
      <span class="m0-kp-tag-chip-label">${esc(tag)}</span>${score}
      <span class="m0-kp-tag-chip-actions">${dismiss}</span>
    </span>`;
  }

  function renderKpTagsEditorHtml(panel, kp, isCreate) {
    const ts = ensureKpTagState(panel, kp);
    const selectedHtml = ts.selected.length
      ? ts.selected.map((t) => renderKpTagChip(t, "selected")).join("")
      : `<span class="m0-muted m0-kp-tags-empty">暂无已选 tag</span>`;
    const candHtml = ts.candidates.length
      ? ts.candidates
          .map((c) =>
            renderKpTagChip(c.tag, c.source === "user" ? "cand-user" : "cand-system", {
              score: c.score,
            })
          )
          .join("")
      : `<span class="m0-muted m0-kp-tags-empty">点击「系统建议」或下方新建</span>`;
    return `<div class="m0-kp-tags-editor" id="kp-tags-editor">
      <div class="m0-kp-tags-zone m0-kp-tags-zone--selected">
        <div class="m0-kp-tags-zone-head">已选 <span class="m0-muted">点击 chip 移到候选</span></div>
        <div id="kp-tags-selected" class="m0-kp-tags-chips">${selectedHtml}</div>
      </div>
      <div class="m0-kp-tags-zone m0-kp-tags-zone--candidate">
        <div class="m0-kp-tags-zone-head">候选 <span class="m0-muted">点击 chip 应用到已选 · × 移除</span></div>
        <div class="m0-kp-tags-zone-toolbar">
          <button type="button" id="kp-suggest-tags" class="m0-btn secondary m0-btn--sm">系统建议</button>
          <div class="m0-kp-tag-create-row">
            <input type="text" id="kp-tag-new-input" placeholder="新建 tag" autocomplete="off" spellcheck="false" />
            <button type="button" id="kp-tag-add-btn" class="m0-btn secondary m0-btn--sm">加入候选</button>
          </div>
        </div>
        <div id="kp-tags-candidates" class="m0-kp-tags-chips">${candHtml}</div>
      </div>
    </div>`;
  }

  function refreshKpTagsEditorDom(panel, kp) {
    const root = $("#kp-tags-editor");
    if (!root || !panel?.draft?.tagState) return;
    const ts = panel.draft.tagState;
    const sel = $("#kp-tags-selected");
    const cand = $("#kp-tags-candidates");
    if (sel) {
      sel.innerHTML = ts.selected.length
        ? ts.selected.map((t) => renderKpTagChip(t, "selected")).join("")
        : `<span class="m0-muted m0-kp-tags-empty">暂无已选 tag</span>`;
    }
    if (cand) {
      cand.innerHTML = ts.candidates.length
        ? ts.candidates
            .map((c) =>
              renderKpTagChip(c.tag, c.source === "user" ? "cand-user" : "cand-system", {
                score: c.score,
              })
            )
            .join("")
        : `<span class="m0-muted m0-kp-tags-empty">点击「系统建议」或下方新建</span>`;
    }
  }

  function promoteKpTag(panel, tag) {
    const ts = panel.draft?.tagState;
    if (!ts || !tag) return;
    if (!ts.selected.includes(tag)) ts.selected.push(tag);
    ts.candidates = ts.candidates.filter((c) => c.tag !== tag);
    syncKpTagStateFromDom(panel);
  }

  function demoteKpTag(panel, tag) {
    const ts = panel.draft?.tagState;
    if (!ts || !tag) return;
    ts.selected = ts.selected.filter((t) => t !== tag);
    if (!ts.candidates.some((c) => c.tag === tag)) {
      ts.candidates.push({ tag, source: "user" });
    }
    syncKpTagStateFromDom(panel);
  }

  function toggleKpTagZone(panel, tag, kind) {
    if (kind === "selected") demoteKpTag(panel, tag);
    else promoteKpTag(panel, tag);
  }

  function dismissKpTag(panel, tag) {
    const ts = panel.draft?.tagState;
    if (!ts || !tag) return;
    ts.selected = ts.selected.filter((t) => t !== tag);
    ts.candidates = ts.candidates.filter((c) => c.tag !== tag);
    syncKpTagStateFromDom(panel);
  }

  function addKpTagCandidate(panel, tag, source = "user", score = null) {
    const ts = panel.draft?.tagState;
    if (!ts) return false;
    const t = (tag || "").trim();
    if (!t || ts.selected.includes(t)) return false;
    const idx = ts.candidates.findIndex((c) => c.tag === t);
    if (idx >= 0) {
      if (source === "system" && ts.candidates[idx].source !== "user") {
        ts.candidates[idx].score = score;
      }
      return false;
    }
    ts.candidates.push({ tag: t, source, score });
    return true;
  }

  function bindKpTagsEditor(kpId, kp) {
    const panel = state.kpPanel;
    if (!panel) return;
    ensureKpTagState(panel, kp);
    const root = $("#kp-tags-editor");
    if (!root) return;

    if (!root.dataset.tagsBound) {
      root.dataset.tagsBound = "1";
      root.addEventListener("click", (e) => {
        const dismiss = e.target.closest("[data-tag-dismiss]");
        if (dismiss) {
          e.stopPropagation();
          dismissKpTag(state.kpPanel, dismiss.getAttribute("data-tag-dismiss"));
          refreshKpTagsEditorDom(
            state.kpPanel,
            state.doc?.knowledge_points?.find((k) => k.id === kpId) || { id: kpId }
          );
          return;
        }
        const chip = e.target.closest(".m0-kp-tag-pick");
        if (!chip) return;
        const tag = chip.getAttribute("data-tag");
        const kind = chip.getAttribute("data-tag-kind");
        if (!tag || !state.kpPanel) return;
        toggleKpTagZone(state.kpPanel, tag, kind);
        refreshKpTagsEditorDom(
          state.kpPanel,
          state.doc?.knowledge_points?.find((k) => k.id === kpId) || { id: kpId }
        );
      });
    }

    $("#kp-tag-add-btn")?.addEventListener("click", () => {
      const input = $("#kp-tag-new-input");
      const raw = (input?.value || "").trim();
      if (!raw) return;
      for (const t of parseTagsInput(raw)) addKpTagCandidate(panel, t, "user");
      if (input) input.value = "";
      refreshKpTagsEditorDom(panel, kp);
    });
    $("#kp-tag-new-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        $("#kp-tag-add-btn")?.click();
      }
    });
    $("#kp-suggest-tags")?.addEventListener("click", () => loadKpTagSuggestions(kpId));
    if (panel.mode !== "create" && !panel.draft.tagState.candidates.length) loadKpTagSuggestions(kpId);
  }

  function promoteKpAlias(panel, alias) {
    const as = panel.draft?.aliasState;
    if (!as || !alias) return;
    if (!as.selected.includes(alias)) as.selected.push(alias);
    as.candidates = as.candidates.filter((c) => c.alias !== alias);
    syncKpTagStateFromDom(panel);
  }

  function demoteKpAlias(panel, alias) {
    const as = panel.draft?.aliasState;
    if (!as || !alias) return;
    as.selected = as.selected.filter((a) => a !== alias);
    if (!as.candidates.some((c) => c.alias === alias)) {
      as.candidates.push({ alias, source: "user" });
    }
    syncKpTagStateFromDom(panel);
  }

  function dismissKpAlias(panel, alias) {
    const as = panel.draft?.aliasState;
    if (!as || !alias) return;
    as.selected = as.selected.filter((a) => a !== alias);
    as.candidates = as.candidates.filter((c) => c.alias !== alias);
    syncKpTagStateFromDom(panel);
  }

  function bindKpAliasEditor(kpId, kp) {
    const panel = state.kpPanel;
    if (!panel) return;
    ensureKpAliasState(panel, kp);
    const root = $("#kp-alias-editor");
    if (!root) return;
    if (!root.dataset.aliasBound) {
      root.dataset.aliasBound = "1";
      root.addEventListener("click", (e) => {
        const dismiss = e.target.closest("[data-alias-dismiss]");
        if (dismiss) {
          e.stopPropagation();
          dismissKpAlias(state.kpPanel, dismiss.getAttribute("data-alias-dismiss"));
          refreshKpAliasEditorDom(
            state.kpPanel,
            state.doc?.knowledge_points?.find((k) => k.id === kpId) || { id: kpId }
          );
          return;
        }
        const chip = e.target.closest("[data-alias]");
        if (!chip) return;
        const alias = chip.getAttribute("data-alias");
        const kind = chip.getAttribute("data-alias-kind");
        if (!alias || !state.kpPanel) return;
        if (kind === "selected") demoteKpAlias(state.kpPanel, alias);
        else promoteKpAlias(state.kpPanel, alias);
        refreshKpAliasEditorDom(
          state.kpPanel,
          state.doc?.knowledge_points?.find((k) => k.id === kpId) || { id: kpId }
        );
      });
    }
    $("#kp-alias-add-btn")?.addEventListener("click", () => {
      const input = $("#kp-alias-new-input");
      const raw = (input?.value || "").trim();
      if (!raw || !panel.draft.aliasState) return;
      const as = panel.draft.aliasState;
      if (!as.selected.includes(raw) && !as.candidates.some((c) => c.alias === raw)) {
        as.candidates.push({ alias: raw, source: "user" });
      }
      if (input) input.value = "";
      refreshKpAliasEditorDom(panel, kp);
    });
  }

  function bindKpDescCandEditor(kpId) {
    const panel = state.kpPanel;
    const kp = state.doc?.knowledge_points?.find((k) => k.id === kpId) || { id: kpId };
    if (!panel) return;
    ensureKpDescCandState(panel, kp);
    const root = $("#kp-desc-cand-editor");
    if (!root || root.dataset.descBound) return;
    root.dataset.descBound = "1";
    root.addEventListener("click", (e) => {
      const dismiss = e.target.closest("[data-desc-dismiss]");
      if (dismiss) {
        e.stopPropagation();
        const text = dismiss.getAttribute("data-desc-dismiss");
        const ds = panel.draft?.descCandState;
        if (ds && text) {
          ds.candidates = ds.candidates.filter((c) => c.text !== text);
          syncKpTagStateFromDom(panel);
          refreshKpDescCandEditorDom(panel, kp);
        }
        return;
      }
      const chip = e.target.closest("[data-desc-cand]");
      if (!chip) return;
      const text = chip.getAttribute("data-desc-cand");
      const ta = $("#kp-desc-input");
      if (text && ta) {
        ta.value = text;
        panel.draft.description = text;
      }
    });
  }

  function bindKpSyncAux(kpId) {
    $("#kp-sync-aux")?.addEventListener("click", () => loadKpImplicitProposals(kpId));
  }

  async function loadKpImplicitProposals(kpId) {
    const panel = state.kpPanel;
    if (!panel || !kpId || !state.currentPath) return;
    const isCreate = panel.mode === "create";
    const tempKp = isCreate
      ? { start_line: panel.startLine, end_line: panel.endLine, name: panel.name || kpId }
      : null;
    const kp = state.doc?.knowledge_points?.find((k) => k.id === kpId) || { id: kpId };
    ensureKpTagState(panel, kp);
    ensureKpAliasState(panel, kp);
    ensureKpDescCandState(panel, kp);
    try {
      const res = await call("sync_implicit_proposals", state.currentPath, kpId, tempKp);
      if (res.status !== "ok") {
        setStatus(res.message || "同步失败");
        return;
      }
      let added = 0;
      for (const row of res.tag_candidates || []) {
        if (addKpTagCandidate(panel, row.tag, row.source || "system", row.score)) added += 1;
      }
      for (const row of res.alias_candidates || []) {
        const as = panel.draft.aliasState;
        const a = String(row.alias || "").trim();
        if (!a || !as) continue;
        const low = a.toLowerCase();
        if (as.selected.some((x) => x.toLowerCase() === low)) continue;
        if (!as.candidates.some((c) => c.alias.toLowerCase() === low)) {
          as.candidates.push({ alias: a, source: row.source || "system" });
          added += 1;
        }
      }
      for (const row of res.description_candidates || []) {
        const ds = panel.draft.descCandState;
        const t = String(row.text || "").trim();
        if (!t || !ds) continue;
        if (!ds.candidates.some((c) => c.text === t)) {
          ds.candidates.push({ text: t, source: row.source || "system" });
          added += 1;
        }
      }
      syncKpTagStateFromDom(panel);
      refreshKpTagsEditorDom(panel, kp);
      refreshKpAliasEditorDom(panel, kp);
      refreshKpDescCandEditorDom(panel, kp);
      setStatus(added ? `已从 aux 合并 ${added} 条候选` : "aux 已同步，无新候选");
    } catch (e) {
      setStatusError(String(e.message || e));
    }
  }

  function bindKpDescSuggest(kpId) {
    $("#kp-suggest-desc")?.addEventListener("click", async () => {
      const ta = $("#kp-desc-input");
      if (!ta || !kpId || !state.currentPath) return;
      const panel = state.kpPanel;
      const isCreate = panel?.mode === "create";
      const tempKp = isCreate
        ? { start_line: panel.startLine, end_line: panel.endLine, name: panel.name || kpId }
        : null;
      try {
        const res = await call("suggest_description", state.currentPath, kpId, tempKp);
        if (res.suggested) ta.value = res.suggested;
      } catch (_) {
        /* ignore */
      }
    });
  }

  async function loadKpTagSuggestions(kpId) {
    const panel = state.kpPanel;
    if (!panel || !kpId || !state.currentPath) return;
    const isCreate = panel.mode === "create";
    const tempKp = isCreate
      ? { start_line: panel.startLine, end_line: panel.endLine, name: panel.name || kpId }
      : null;
    ensureKpTagState(panel, state.doc?.knowledge_points?.find((k) => k.id === kpId) || { tags: [] });
    try {
      const res = await call("suggest_tags", state.currentPath, kpId, 12, tempKp);
      const items = res.suggestions || [];
      let added = 0;
      for (const s of items) {
        if (addKpTagCandidate(panel, s.tag, "system", s.score)) added += 1;
      }
      refreshKpTagsEditorDom(
        panel,
        state.doc?.knowledge_points?.find((k) => k.id === kpId) || { id: kpId }
      );
      if (!items.length) setStatus("暂无 tag 建议");
      else if (added) setStatus(`已加入 ${added} 个系统候选`);
    } catch (_) {
      /* optional */
    }
  }

  async function loadKpMergeSuggestions(kpId) {
    const box = $("#kp-merge-suggest");
    if (!box || !kpId) return;
    box.classList.add("hidden");
    box.innerHTML = "";
    try {
      const res = await call("suggest_kp_merge", kpId, state.currentPath || "");
      const items = (res.suggestions || []).filter((s) => s.kp_id && s.kp_id !== kpId);
      if (!items.length) return;
      box.innerHTML =
        `<p class="m0-config-hint">名称相近的知识点（仅供参考，合并需手动处理）：</p>` +
        items
          .map(
            (s) =>
              `<button type="button" class="m0-suggest-item m0-kp-merge-hit" data-merge-file="${esc(s.file || "")}" data-merge-kp="${esc(s.kp_id || "")}">
                <span class="m0-suggest-score">${esc(String(Math.round(s.score || 0)))}</span>
                <span class="m0-suggest-label">${esc(s.name || s.kp_id)}</span>
                <span class="m0-muted">${esc(basename(s.file || ""))}</span>
              </button>`
          )
          .join("");
      box.classList.remove("hidden");
      box.querySelectorAll(".m0-kp-merge-hit").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const file = btn.getAttribute("data-merge-file");
          const kid = btn.getAttribute("data-merge-kp");
          if (!file) return;
          closeKpModal();
          await openFile(file, { kpId: kid });
        });
      });
    } catch (_) {
      /* optional */
    }
  }

  function bindKpModalEvents(kp) {
    const body = $("#kp-body");
    body.querySelectorAll("[data-kp-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        syncKpPanelFromForm();
        state.kpPanel.tab = btn.dataset.kpTab;
        renderKpModalBody();
      });
    });
  }

  function openKpModal(kpId, opts = {}) {
    if (!state.doc) return;
    const kp = (state.doc.knowledge_points || []).find((k) => k.id === kpId);
    if (!kp) return;
    const rr = kp.range_resolved || {};
    const startLine = rr.start_line || kp.range?.start?.line_hint || 1;
    const endLine = pickAssistEndLine(kp, startLine);
    state.kpPanel = {
      mode: "edit",
      kpId,
      tab: opts.tab || "range",
      returnTo: opts.returnTo || null,
      startLine,
      endLine,
      draft: {},
    };
    renderKpModalBody();
    setupKpModalResize();
    $("#kp-modal").classList.remove("hidden");
  }

  function openKpModalForCreate(opts = {}) {
    if (!state.doc) return;
    const total = state.doc?.lines?.length || 1;
    const startLine = Math.max(1, opts.startLine || 1);
    const endLine = Math.min(Math.max(startLine, opts.endLine || startLine), total);
    state.kpPanel = {
      mode: "create",
      kpId: opts.kpId || "",
      name: opts.name || "",
      startLine,
      endLine,
      proposal: opts.proposal || null,
      tab: opts.tab || "range",
      returnTo: opts.returnTo || null,
    };
    renderKpModalBody();
    setupKpModalResize();
    $("#kp-modal").classList.remove("hidden");
  }

  function openKpModalFromProposal(proposal, opts = {}) {
    if (!proposal) return;
    const r = proposal.range || {};
    closeConfigModal();
    openKpModalForCreate({
      kpId: proposal.concept_id || slugify(proposal.name),
      name: proposal.name || "",
      startLine: r.start?.line_hint || 1,
      endLine: r.end?.line_hint || 1,
      proposal,
      returnTo: opts.returnTo || "config",
      tab: "range",
    });
  }

  function closeKpModal(opts = {}) {
    const panel = state.kpPanel;
    const returnTo = opts.skipReturn ? null : panel?.returnTo;
    const fromProposal = !!panel?.proposal;
    clearKpRangeAssist();
    state.kpPanel = null;
    $("#kp-body")?.classList.remove("m0-modal-body-kp-range");
    $("#kp-body")?.classList.remove("m0-modal-body-kp-edges");
    $("#kp-modal").classList.add("hidden");
    if (returnTo === "config") {
      openConfigModal({
        highlightLinkTarget: state.configModalOpts.highlightLinkTarget,
        tab: fromProposal ? "pending" : state.configTab || "kp",
      });
    }
  }

  async function jumpToTarget(candidate, opts = {}) {
    if (!candidate?.file) return;
    if (!opts.skipNav && window.MemoriaNavStack) {
      MemoriaNavStack.push({
        file: candidate.file,
        kpId: candidate.kp_id || null,
        source: opts.source || "link",
      });
      updateNavButtons();
    }
    await openFile(candidate.file, {
      fromNav: true,
      kpId: candidate.kp_id || null,
      skipTabUpsert: opts.skipTabUpsert,
    });
    const label = candidate.name || candidate.kp_id || candidate.file;
    setStatus(`已跳转 · ${label}`, candidate.file);
  }

  function closeLinkModal(opts = {}) {
    const returnTo = opts.skipReturn ? null : state.linkPicker?.returnTo;
    const configHighlight = state.linkPicker?.configHighlight;
    state.linkPicker = null;
    $("#link-modal").classList.add("hidden");
    if (returnTo === "config") {
      openConfigModal({
        highlightLinkTarget: configHighlight || null,
        tab: state.configTab || "links",
      });
    } else if (returnTo === "kp" && state.kpPanel) {
      renderKpModalBody();
    }
  }

  function linkModalMode() {
    return state.linkPicker?.mode || "jump";
  }

  function syncLinkModalFooter() {
    const mode = linkModalMode();
    const isEdit = mode === "edit" || mode === "create";
    const fromConfig = state.linkPicker?.returnTo === "config";
    $("#link-confirm").classList.toggle("hidden", isEdit);
    $("#link-save").classList.toggle("hidden", !isEdit);
    $("#link-save-jump").classList.toggle("hidden", !isEdit);
    $("#link-config-view").classList.toggle("hidden", !isEdit || fromConfig);
    if (mode === "jump") {
      $("#link-confirm").textContent = "确认跳转";
    }
  }

  function pickIndexRank(selectedOrder, index) {
    return selectedOrder.indexOf(index);
  }

  function candidateTargetId(c) {
    return c.requested_id || c.kp_id || c.file?.replace(/\.md$/i, "") || "";
  }

  function normalizeLinkEdgeType(raw) {
    const s = String(raw || "").trim().toLowerCase();
    return s === "extend" ? "extend" : "reference";
  }

  function defaultRelevanceForEdgeType(edgeType) {
    return normalizeLinkEdgeType(edgeType) === "extend" ? 0.6 : 0.7;
  }

  function normalizeLinkRelevance(raw, edgeType) {
    const d = defaultRelevanceForEdgeType(edgeType);
    if (raw === null || raw === undefined || raw === "") return d;
    const v = Number(raw);
    if (!Number.isFinite(v)) return d;
    return Math.max(0, Math.min(1, v));
  }

  function formatLinkRelevance(val) {
    return (Math.round(Number(val) * 100) / 100).toFixed(2);
  }

  function defaultTargetEdgeProps(edgeType) {
    const et = normalizeLinkEdgeType(edgeType);
    return { edge_type: et, relevance: defaultRelevanceForEdgeType(et) };
  }

  function loadTargetEdgesFromSidecar(sc, fallbackEdgeType) {
    const out = {};
    const defaultEt = normalizeLinkEdgeType(sc?.edge_type || fallbackEdgeType);
    const legacyRel =
      sc?.relevance != null
        ? normalizeLinkRelevance(sc.relevance, defaultEt)
        : defaultRelevanceForEdgeType(defaultEt);
    const te = sc?.target_edges;
    if (te && typeof te === "object") {
      for (const [tid, props] of Object.entries(te)) {
        if (!tid) continue;
        const et = normalizeLinkEdgeType(props?.edge_type || defaultEt);
        out[tid] = {
          edge_type: et,
          relevance: normalizeLinkRelevance(props?.relevance, et),
        };
      }
    }
    for (const tid of sc?.targets || []) {
      const key = String(tid || "").trim();
      if (!key || out[key]) continue;
      out[key] = { edge_type: defaultEt, relevance: legacyRel };
    }
    return out;
  }

  function ensureTargetEdge(p, tid) {
    if (!p.targetEdges) p.targetEdges = {};
    const key = String(tid || "").trim();
    if (!key) return defaultTargetEdgeProps(p.defaultEdgeType);
    if (!p.targetEdges[key]) {
      p.targetEdges[key] = defaultTargetEdgeProps(p.defaultEdgeType);
    }
    return p.targetEdges[key];
  }

  function syncTargetEdgeRelevanceInputs(pickIndex, from) {
    const range = document.querySelector(`[data-target-edge-rel-range="${pickIndex}"]`);
    const num = document.querySelector(`[data-target-edge-rel-num="${pickIndex}"]`);
    if (!range || !num) return;
    if (from === "range") {
      num.value = formatLinkRelevance(range.value);
    } else {
      range.value = formatLinkRelevance(num.value);
    }
    syncLinkEditorSaveButtons();
  }

  function readTargetEdgeFromDom(pickIndex, p) {
    const tid = candidateTargetId(p.candidates[pickIndex]);
    if (!tid) return;
    const props = ensureTargetEdge(p, tid);
    const typeEl = document.querySelector(`[data-target-edge-type="${pickIndex}"]`);
    const numEl = document.querySelector(`[data-target-edge-rel-num="${pickIndex}"]`);
    if (typeEl) props.edge_type = normalizeLinkEdgeType(typeEl.value);
    if (numEl) props.relevance = normalizeLinkRelevance(numEl.value, props.edge_type);
  }

  async function suggestLinkRelevanceForTarget(pickIndex) {
    readLinkEditorFields();
    const p = state.linkPicker;
    if (!p || !state.currentPath) return;
    const tid = candidateTargetId(p.candidates[pickIndex]);
    if (!tid) return;
    const props = ensureTargetEdge(p, tid);
    try {
      const res = await call(
        "suggest_link_relevance",
        state.currentPath,
        p.anchorText || "",
        tid,
        null,
        props.edge_type || "reference",
        state.activeKpId || ""
      );
      if (res.status !== "ok") {
        setStatus(res.message || "推荐失败");
        return;
      }
      if (res.suggested != null) {
        props.relevance = normalizeLinkRelevance(res.suggested, props.edge_type);
        renderLinkTargetList({ preserveFields: false });
        setStatus(`已应用 ${tid} 推荐`, formatLinkRelevance(props.relevance));
      } else {
        setStatus(
          "智能推荐尚未接入",
          `${tid} 默认 ${formatLinkRelevance(res.default ?? defaultRelevanceForEdgeType(props.edge_type))}`
        );
      }
    } catch (e) {
      setStatus("推荐失败", String(e.message || e));
    }
  }

  function collectTargetEdgesForSave(p) {
    readLinkEditorFields();
    const out = {};
    for (const i of p.selectedOrder) {
      const tid = candidateTargetId(p.candidates[i]);
      if (!tid) continue;
      const props = ensureTargetEdge(p, tid);
      out[tid] = {
        edge_type: normalizeLinkEdgeType(props.edge_type),
        relevance: normalizeLinkRelevance(props.relevance, props.edge_type),
      };
    }
    return out;
  }

  function renderTargetEdgeControls(pickIndex, props) {
    const et = normalizeLinkEdgeType(props.edge_type);
    const rel = normalizeLinkRelevance(props.relevance, et);
    return `<div class="m0-link-target-edge">
      <span class="m0-link-target-edge-label">类型</span>
      <select data-target-edge-type="${pickIndex}">
        <option value="reference"${et === "reference" ? " selected" : ""}>引用</option>
        <option value="extend"${et === "extend" ? " selected" : ""}>扩展</option>
      </select>
      <span class="m0-link-target-edge-label">强度</span>
      <input type="range" data-target-edge-rel-range="${pickIndex}" min="0" max="1" step="0.05" value="${rel}" title="边强度 relevance" />
      <input type="number" data-target-edge-rel-num="${pickIndex}" class="m0-link-relevance-num" min="0" max="1" step="0.05" value="${formatLinkRelevance(rel)}" title="边强度 relevance" />
      <button type="button" class="m0-btn secondary m0-btn--sm" data-target-edge-suggest="${pickIndex}">推荐</button>
    </div>`;
  }

  function renderLinkTargetEdgesPanel(p) {
    if (!p.selectedOrder.length) {
      return `<div class="m0-link-edge-editor-panel" id="link-edge-editor-panel">
        <div class="m0-link-section-title">图谱边</div>
        <p class="m0-muted m0-link-edge-empty">请先勾选跳转目标，再在此配置语义边属性</p>
      </div>`;
    }
    const items = p.selectedOrder
      .map((pickIndex) => {
        const c = p.candidates[pickIndex];
        const tid = candidateTargetId(c);
        if (!tid) return "";
        const props = ensureTargetEdge(p, tid);
        const name = c?.name || tid;
        return `<div class="m0-link-edge-editor-item">
          <div class="m0-link-edge-editor-head">
            <span class="m0-link-edge-editor-name">${esc(name)}</span>
            <span class="m0-link-edge-editor-id m0-muted">${esc(tid)} · ${esc(c?.file || tid)}</span>
          </div>
          ${renderTargetEdgeControls(pickIndex, props)}
        </div>`;
      })
      .join("");
    return `<div class="m0-link-edge-editor-panel" id="link-edge-editor-panel">
      <div class="m0-link-section-title">图谱边</div>
      <p class="m0-config-hint m0-link-edge-panel-hint">为下方每个已选目标单独设置语义关系。</p>
      ${items}
    </div>`;
  }

  function readLinkEditorFields() {
    const p = state.linkPicker;
    if (!p) return null;
    const anchorEl = $("#link-edit-anchor");
    if (anchorEl) {
      p.anchorText = anchorEl.value.trim();
      p.displayText = p.anchorText;
    }
    if (p.selectedOrder?.length) {
      for (const i of p.selectedOrder) readTargetEdgeFromDom(i, p);
    }
    return p;
  }

  function linkEditorCanSave(p) {
    if (!p || !p.selectedOrder.length) return false;
    readLinkEditorFields();
    return !!(p.anchorText || "").trim();
  }

  function linkEditorSaveHint(p) {
    if (!p.selectedOrder.length) return "请添加至少一个跳转目标";
    readLinkEditorFields();
    if (!(p.anchorText || "").trim()) {
      return "请填写匹配文本，并在下方添加跳转目标";
    }
    return linkEditorStatusText(p);
  }

  function syncLinkEditorSaveButtons() {
    const p = state.linkPicker;
    if (!p || (p.mode !== "edit" && p.mode !== "create")) return;
    const ok = linkEditorCanSave(p);
    const saveBtn = $("#link-save");
    const saveJumpBtn = $("#link-save-jump");
    const hint = $("#link-hint");
    if (saveBtn) saveBtn.disabled = !ok;
    if (saveJumpBtn) saveJumpBtn.disabled = !ok;
    if (hint) hint.textContent = linkEditorSaveHint(p);
  }

  function bindLinkEditorMetaInputs() {
    const anchorEl = $("#link-edit-anchor");
    if (anchorEl && !anchorEl.dataset.saveSyncBound) {
      anchorEl.dataset.saveSyncBound = "1";
      anchorEl.addEventListener("input", () => {
        syncLinkEditorSaveButtons();
        scheduleLinkEditorMatchRescan();
        scheduleAnchorSuggest();
      });
      anchorEl.addEventListener("focus", () => scheduleAnchorSuggest());
      anchorEl.addEventListener("blur", () => {
        anchorSuggestHideTimer = setTimeout(hideAnchorSuggest, 150);
      });
    }
  }

  function bindLinkTargetEdgeInputs() {
    const p = state.linkPicker;
    if (!p) return;
    const root = $("#link-edge-editor-panel");
    if (!root) return;
    root.querySelectorAll("[data-target-edge-type]").forEach((el) => {
      const pickIndex = +el.dataset.targetEdgeType;
      el.addEventListener("change", () => {
        readTargetEdgeFromDom(pickIndex, p);
        const tid = candidateTargetId(p.candidates[pickIndex]);
        const props = ensureTargetEdge(p, tid);
        const num = document.querySelector(`[data-target-edge-rel-num="${pickIndex}"]`);
        const range = document.querySelector(`[data-target-edge-rel-range="${pickIndex}"]`);
        if (num && num.dataset.userSet !== "1") {
          props.relevance = defaultRelevanceForEdgeType(el.value);
          if (range) range.value = props.relevance;
          num.value = formatLinkRelevance(props.relevance);
        }
        syncLinkEditorSaveButtons();
      });
    });
    root.querySelectorAll("[data-target-edge-rel-range]").forEach((el) => {
      const pickIndex = +el.dataset.targetEdgeRelRange;
      el.addEventListener("input", () => {
        const num = document.querySelector(`[data-target-edge-rel-num="${pickIndex}"]`);
        if (num) num.dataset.userSet = "1";
        readTargetEdgeFromDom(pickIndex, p);
        syncTargetEdgeRelevanceInputs(pickIndex, "range");
      });
    });
    root.querySelectorAll("[data-target-edge-rel-num]").forEach((el) => {
      const pickIndex = +el.dataset.targetEdgeRelNum;
      el.addEventListener("input", () => {
        el.dataset.userSet = "1";
        readTargetEdgeFromDom(pickIndex, p);
        syncTargetEdgeRelevanceInputs(pickIndex, "num");
      });
    });
    root.querySelectorAll("[data-target-edge-suggest]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        suggestLinkRelevanceForTarget(+btn.dataset.targetEdgeSuggest);
      });
    });
  }

  function linkEditorStatusText(p) {
    if (!p.selectedOrder.length) return "请添加至少一个跳转目标";
    const n = p.selectedOrder.length;
    if (p.mode === "create") return `新建链接 · ${n} 个目标`;
    return n > 1 ? `已选 ${n} 个跳转目标` : "已选 1 个跳转目标";
  }

  function renderLinkEditMeta(p) {
    const text = p.anchorText || p.displayText || "";
    const searchOpts = p.searchOptions || defaultLinkSearchOptions();
    let html = `<div class="m0-link-edit-meta">`;
    html += `<label class="m0-link-field"><span>匹配文本</span>
      <div class="m0-link-anchor-field">
        <input type="text" id="link-edit-anchor" value="${esc(text)}" placeholder="正文与预览中可见的文字，即跳转键" autocomplete="off" spellcheck="false" />
        <div class="m0-link-target-suggest hidden" id="link-anchor-suggest"></div>
      </div>
    </label>`;
    html += `<div id="link-edit-search-options">${renderLinkSearchOptionsHtml("link-edit", searchOpts)}</div>`;
    html += `</div>`;
    return html;
  }

  function renderLinkTargetList(opts = {}) {
    const p = state.linkPicker;
    if (!p) return;
    if (opts.preserveFields && (p.mode === "edit" || p.mode === "create")) {
      readLinkEditorFields();
    }
    const { candidates, selectedOrder } = p;
    const isEdit = p.mode === "edit" || p.mode === "create";

    let html = "";
    if (isEdit) {
      html += renderLinkEditMeta(p);
      html += `<div id="link-editor-match-slot">${renderLinkEditorMatchPanelHtml()}</div>`;
      html += `<p class="m0-config-hint m0-link-meta-hint">对应正文 <code>[[匹配文本]]</code>。输入框为搜索词；保存时按所选匹配项采用正文 canonical 文本。</p>`;
      html += `<div class="m0-link-section-title">点击后打开</div>`;
      html += `<p class="m0-config-hint m0-link-targets-hint">勾选目标参与跳转。</p>`;
    }

    if (isEdit) {
      html += `<div class="m0-link-pick-legend">
        <span><i class="m0-link-legend-dot sel"></i>已选（参与跳转）</span>
        <span><i class="m0-link-legend-dot"></i>未选（保留备选）</span>
      </div>`;
    } else {
      html += `<div class="m0-link-pick-legend">
        <span><i class="m0-link-legend-dot primary"></i>队首跳转</span>
        <span><i class="m0-link-legend-dot sel"></i>已选入队</span>
        <span><i class="m0-link-legend-dot"></i>未选</span>
      </div>`;
    }

    if (!candidates.length && isEdit) {
      html += `<p class="m0-muted m0-link-empty">暂无目标 · 在下方添加 KP id 或文件 stem</p>`;
    }

    html += candidates
      .map((c, i) => {
        const rank = pickIndexRank(selectedOrder, i);
        const isSelected = rank >= 0;
        const isPrimary = !isEdit && rank === 0;
        let dotCls = "m0-pick-dot";
        if (isPrimary) dotCls += " is-primary";
        else if (isSelected) dotCls += " is-selected";
        const rowCls =
          "m0-link-pick-item" +
          (isPrimary ? " is-active" : isEdit && isSelected ? " is-selected-row" : "");
        const tid = candidateTargetId(c);
        return `<div class="${rowCls}" data-pick-row="${i}">
          <button type="button" class="${dotCls}" data-pick-dot="${i}" aria-label="选择">
            <span class="m0-pick-dot-inner"></span>
          </button>
          <div class="m0-link-pick-label">
            <div class="m0-link-pick-name">${esc(c.name || tid || c.file)}</div>
            <div class="m0-link-pick-file">${esc(c.file || tid)}</div>
          </div>
          ${isEdit ? `<button type="button" class="m0-link-remove-target" data-remove-target="${i}" title="移除">×</button>` : ""}
        </div>`;
      })
      .join("");

    if (isEdit) {
      html += `<div class="m0-link-add-row">
        <div class="m0-link-add-field">
          <input type="text" id="link-add-target" placeholder="id 或 tag:rl policy …" autocomplete="off" spellcheck="false" />
          <div class="m0-link-target-suggest hidden" id="link-add-target-suggest"></div>
        </div>
        <button type="button" id="link-add-target-btn">添加</button>
      </div>`;
      html += renderLinkTargetEdgesPanel(p);
      html += `<details class="m0-suggest-block m0-link-tag-suggest">
        <summary>智能匹配（M4 · tag / Lexical）</summary>
        <p class="m0-config-hint">输入 tag: 前缀按标签检索知识点；无匹配时可创建未绑定链接或新建知识点。</p>
        <div class="m0-suggest-list m0-suggest-placeholder-list">
          <div class="m0-suggest-item m0-suggest-placeholder">
            <span class="m0-suggest-score">94%</span>
            <span class="m0-suggest-label">q-learning</span>
            <span class="m0-muted">tag:rl · q-learning.md</span>
            <button type="button" class="m0-btn secondary m0-btn--sm" disabled>选用</button>
          </div>
        </div>
      </details>`;
    }

    $("#link-body").innerHTML = html;

    const hint = $("#link-hint");
    const confirmBtn = $("#link-confirm");
    const saveBtn = $("#link-save");
    const saveJumpBtn = $("#link-save-jump");

    if (p.mode === "jump") {
      if (selectedOrder.length) {
        const primary = candidates[selectedOrder[0]];
        const rest = selectedOrder.length - 1;
        hint.textContent =
          `队首：${primary?.name || candidateTargetId(primary) || primary?.file}` +
          (rest > 0 ? ` · 另有 ${rest} 个将加入标签栏` : "");
        confirmBtn.disabled = false;
      } else {
        hint.textContent = "点击圆圈多选；再次点击队首可取消";
        confirmBtn.disabled = true;
      }
    } else {
      syncLinkEditorSaveButtons();
    }

    bindLinkEditorMetaInputs();
    bindLinkTargetEdgeInputs();

    const onPick = (index) => {
      const rank = pickIndexRank(p.selectedOrder, index);
      if (isEdit) {
        if (rank < 0) p.selectedOrder.push(index);
        else p.selectedOrder.splice(rank, 1);
      } else if (rank < 0) {
        p.selectedOrder.push(index);
      } else if (rank === 0) {
        p.selectedOrder.shift();
      } else {
        p.selectedOrder.splice(rank, 1);
        p.selectedOrder.unshift(index);
      }
      renderLinkTargetList({ preserveFields: true });
    };

    $("#link-body").querySelectorAll("[data-pick-row]").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest("[data-pick-dot], [data-remove-target]")) return;
        onPick(+row.dataset.pickRow);
      });
    });
    $("#link-body").querySelectorAll("[data-pick-dot]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        onPick(+btn.dataset.pickDot);
      });
    });
    $("#link-body").querySelectorAll("[data-remove-target]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = +btn.dataset.removeTarget;
        p.candidates.splice(idx, 1);
        p.selectedOrder = p.selectedOrder
          .filter((i) => i !== idx)
          .map((i) => (i > idx ? i - 1 : i));
        renderLinkTargetList({ preserveFields: true });
      });
    });

    bindLinkAddTargetAutocomplete();

    $("#link-add-target-btn")?.addEventListener("click", () => addLinkEditorTarget());
    $("#link-add-target")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        hideLinkTargetSuggest();
        addLinkEditorTarget();
      } else if (e.key === "Escape") {
        hideLinkTargetSuggest();
      }
    });
  }

  const LINK_TARGET_SUGGEST_MAX = 8;
  let linkTargetSuggestHideTimer = null;

  function filterLinkTargetOptions(query) {
    const all = state.linkTargetList || [];
    const q = (query || "").trim().toLowerCase();
    if (!q) return all.slice(0, LINK_TARGET_SUGGEST_MAX);
    return all
      .filter((id) => String(id).toLowerCase().includes(q))
      .slice(0, LINK_TARGET_SUGGEST_MAX);
  }

  let linkTargetSuggestTimer = null;

  async function refreshLinkTargetSuggest() {
    const input = $("#link-add-target");
    if (!input) return;
    const q = (input.value || "").trim();
    if (!q) {
      showLinkTargetSuggest(filterLinkTargetOptions(""));
      return;
    }
    clearTimeout(linkTargetSuggestTimer);
    linkTargetSuggestTimer = setTimeout(async () => {
      if (!state.kbPath) {
        showLinkTargetSuggest(filterLinkTargetOptions(q));
        return;
      }
      try {
        const res = await call("search", q, "kb", LINK_TARGET_SUGGEST_MAX);
        const hits = (res.results || []).map((r) => ({
          id: r.kp_id || r.id,
          label: r.name || r.label || r.kp_id || r.id,
          file: r.file || "",
          score: r.score,
        }));
        if (hits.length) {
          showLinkTargetSuggest(hits);
          return;
        }
      } catch (_) {
        /* fallback */
      }
      showLinkTargetSuggest(
        filterLinkTargetOptions(q).map((id) => ({ id, label: id, file: "", score: 0 }))
      );
    }, 180);
  }

  function hideLinkTargetSuggest() {
    clearTimeout(linkTargetSuggestHideTimer);
    $("#link-add-target-suggest")?.classList.add("hidden");
  }

  function showLinkTargetSuggest(items) {
    const box = $("#link-add-target-suggest");
    if (!box) return;
    if (!items.length) {
      hideLinkTargetSuggest();
      return;
    }
    box.innerHTML = items
      .map((it) => {
        const id = typeof it === "string" ? it : it.id;
        const label = typeof it === "string" ? it : it.label || id;
        const file = typeof it === "string" ? "" : it.file || "";
        const score = typeof it === "string" ? 0 : it.score || 0;
        const meta = file ? basename(file) : "";
        return `<button type="button" class="m0-link-target-opt" data-target-id="${esc(id)}" title="${esc(label)}">
          ${score ? `<span class="m0-suggest-score">${esc(String(Math.round(score)))}</span>` : ""}
          <span class="m0-suggest-label">${esc(label)}</span>
          ${meta ? `<span class="m0-muted">${esc(meta)}</span>` : ""}
        </button>`;
      })
      .join("");
    box.classList.remove("hidden");
    box.querySelectorAll(".m0-link-target-opt").forEach((btn) => {
      btn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const input = $("#link-add-target");
        if (input) input.value = btn.dataset.targetId;
        hideLinkTargetSuggest();
        input?.focus();
      });
    });
  }

  function refreshLinkTargetSuggestSync() {
    refreshLinkTargetSuggest();
  }

  function bindLinkAddTargetAutocomplete() {
    const input = $("#link-add-target");
    if (!input) return;
    input.addEventListener("focus", () => refreshLinkTargetSuggestSync());
    input.addEventListener("input", () => refreshLinkTargetSuggestSync());
    input.addEventListener("blur", () => {
      linkTargetSuggestHideTimer = setTimeout(hideLinkTargetSuggest, 120);
    });
  }

  async function addLinkEditorTarget() {
    const p = state.linkPicker;
    const input = $("#link-add-target");
    if (!p || !input) return;
    readLinkEditorFields();
    const tid = input.value.trim();
    if (!tid) return;
    if (p.candidates.some((c) => candidateTargetId(c) === tid)) {
      setStatus("目标已存在", tid);
      return;
    }
    try {
      const res = await call("resolve_link", tid);
      let candidate;
      if (res.status === "ok" && res.candidates?.[0]) {
        candidate = { ...res.candidates[0], requested_id: tid };
      } else if (res.status === "ambiguous" && res.candidates?.[0]) {
        candidate = { ...res.candidates[0], requested_id: tid };
      } else {
        candidate = {
          file: "",
          kp_id: null,
          name: tid,
          requested_id: tid,
          unresolved: true,
        };
      }
      p.candidates.push(candidate);
      p.selectedOrder.push(p.candidates.length - 1);
      input.value = "";
      hideLinkTargetSuggest();
      renderLinkTargetList({ preserveFields: true });
    } catch (e) {
      setStatus("添加失败", String(e.message || e));
    }
  }

  function openLinkModal() {
    syncLinkModalFooter();
    renderLinkTargetList();
    $("#link-modal").classList.remove("hidden");
  }

  function findSidecarLink(anchorText, displayText) {
    const links = state.doc?.sidecar?.links || [];
    const label = (displayText || "").trim() || anchorText;
    const keys = new Set([anchorText, label].filter(Boolean));
    return links.find((l) => keys.has(l.anchor_text)) || null;
  }

  async function buildCandidatesForAnchor(anchorText, displayText, overrides) {
    const label = (displayText || "").trim() || anchorText;
    const ovr = overrides || state.doc?.link_overrides || {};
    const sc = findSidecarLink(anchorText, displayText);
    const activeIds = ovr[anchorText] || ovr[label] || sc?.targets || null;
    const poolIds = sc?.pool || activeIds;
    let ids = activeIds;

    if (poolIds?.length) {
      ids = poolIds;
    } else if (!ids) {
      for (const key of Object.keys(ovr)) {
        if (key === anchorText || key === label) {
          ids = ovr[key];
          break;
        }
      }
    }

    if (ids?.length) {
      const res = await call("resolve_links", ids);
      const candidates = [];
      const selectedOrder = [];
      const activeSet = new Set(activeIds || ids);
      for (const tid of ids) {
        const found = (res.candidates || []).find(
          (c) => (c.requested_id || c.kp_id || "") === tid
        );
        if (found) {
          const idx = candidates.length;
          candidates.push({ ...found, requested_id: tid });
          if (activeSet.has(tid)) selectedOrder.push(idx);
        } else {
          const idx = candidates.length;
          candidates.push({
            file: "",
            kp_id: null,
            name: tid,
            requested_id: tid,
            unresolved: true,
          });
          if (activeSet.has(tid)) selectedOrder.push(idx);
        }
      }
      if (candidates.length) {
        const order =
          sc?.pool && activeIds
            ? selectedOrder
            : candidates.map((_, i) => i);
        return { candidates, selectedOrder: order };
      }
    }
    try {
      const res = await call("resolve_link", anchorText);
      if (res.status === "ok" && res.candidates?.length) {
        return { candidates: res.candidates, selectedOrder: [0] };
      }
      if (res.status === "ambiguous" && res.candidates?.length) {
        return {
          candidates: res.candidates,
          selectedOrder: res.candidates.map((_, i) => i),
        };
      }
    } catch (_) {
      /* ignore */
    }
    return { candidates: [], selectedOrder: [] };
  }

  async function openLinkEditor(opts = {}) {
    if (!state.currentPath) return;
    const anchorText = (opts.anchorText || "").trim();
    const displayText = (opts.displayText || anchorText).trim();
    const edgeHint = opts.edgeHint || "";
    const overrides = state.doc?.link_overrides || {};
    const built = await buildCandidatesForAnchor(anchorText, displayText, overrides);
    const sc = findSidecarLink(anchorText, displayText);
    const storedAnchor = (sc?.anchor_text || anchorText).trim();
    const edgeType = normalizeLinkEdgeType(sc?.edge_type || opts.edgeType || edgeHint);
    const targetEdges = loadTargetEdgesFromSidecar(sc, edgeType);

    state.linkPicker = {
      mode: opts.mode || "edit",
      title: displayText || storedAnchor || anchorText,
      anchorText: storedAnchor || anchorText,
      oldAnchorText: storedAnchor || anchorText,
      displayText: storedAnchor || displayText || anchorText,
      oldDisplay: opts.oldDisplay ?? (displayText !== anchorText ? displayText : null),
      defaultEdgeType: edgeType,
      targetEdges,
      candidates: built.candidates,
      selectedOrder: built.selectedOrder,
      createSelection: opts.createSelection || null,
      createSelectionLines: opts.createSelectionLines || null,
      returnTo: opts.returnTo || null,
      configHighlight: opts.configHighlight || null,
      searchOptions: defaultLinkSearchOptions(),
    };

    if (opts.mode === "create") {
      $("#link-title").textContent = displayText
        ? `创建链接 — ${displayText.slice(0, 32)}`
        : "创建链接";
    } else {
      $("#link-title").textContent = `编辑链接 — ${displayText.slice(0, 32)}`;
    }

    try {
      const res = await call("get_link_targets");
      state.linkTargetList = res.resolved_targets || [];
    } catch (_) {
      state.linkTargetList = [];
    }

    openLinkModal();
    await loadLinkEditorMatch();
  }

  async function openLinkEditorFromElement(linkEl) {
    const payload = linkContextPayload(linkEl);
    await openLinkEditor({
      mode: "edit",
      anchorText: payload.targetId,
      displayText: payload.displayText,
      oldDisplay: payload.displayText !== payload.targetId ? payload.displayText : null,
    });
  }

  async function openLinkEditorFromSelection(text, opts = {}) {
    const t = (text || "").trim();
    if (!t) return;
    const overrides = state.doc?.link_overrides || {};
    await openLinkEditor({
      mode: "create",
      anchorText: t,
      displayText: t,
      createSelection: t,
      createSelectionLines: opts.preselectLines || null,
    });
    if (overrides[t]?.length) {
      setStatus("发现已有路由", overrides[t].join(", "));
    }
  }

  function showLinkPicker(title, candidates) {
    state.linkPicker = {
      mode: "jump",
      title,
      candidates,
      selectedOrder: candidates.length === 1 ? [0] : [],
    };
    $("#link-title").textContent = `多目标链接 — ${title}`;
    openLinkModal();
  }

  async function confirmLinkPicker() {
    const p = state.linkPicker;
    if (!p || p.mode !== "jump" || !p.selectedOrder.length) return;
    const items = p.selectedOrder.map((i) => p.candidates[i]).filter(Boolean);
    if (!items.length) return;
    const primary = items[0];
    closeLinkModal();
    for (let i = 0; i < items.length; i++) {
      ensureOpenTab(items[i], { pending: i > 0 });
    }
    renderTabs();
    await jumpToTarget(primary, { source: "link", skipTabUpsert: true });
  }

  async function saveLinkEditor(jumpAfter) {
    readLinkEditorFields();
    const p = state.linkPicker;
    if (!p || (p.mode !== "edit" && p.mode !== "create")) return;
    if (!p.selectedOrder.length) {
      setStatus("保存失败", "至少选择一个目标");
      return;
    }
    const searchQuery = (p.anchorText || "").trim();
    const selectedLines = p.match?.selected?.size ? [...p.match.selected] : [];
    const saveAnchor = resolveSaveAnchorFromSelection(p.match, selectedLines, searchQuery);
    if (!saveAnchor) {
      setStatus("保存失败", "请填写匹配文本");
      return;
    }

    const targetIds = p.selectedOrder
      .map((i) => candidateTargetId(p.candidates[i]))
      .filter(Boolean);
    const poolIds = p.candidates
      .map((c) => candidateTargetId(c))
      .filter(Boolean);
    const oldAnchor = (p.oldAnchorText || saveAnchor).trim();
    const anchorRenamed = p.mode === "edit" && oldAnchor !== saveAnchor;
    const returnTo = p.returnTo;
    const configHighlight = p.configHighlight || saveAnchor;
    const targetEdges = collectTargetEdgesForSave(p);
    const defaultEdgeType =
      Object.values(targetEdges)[0]?.edge_type || p.defaultEdgeType || "reference";

    setStatus("保存中…");

    try {
      let res;
      if (p.mode === "create" && p.createSelection) {
        res = await call(
          "wrap_text_as_link",
          state.currentPath,
          p.createSelection,
          saveAnchor,
          targetIds,
          "",
          defaultEdgeType,
          state.activeKpId || "",
          targetEdges
        );
      } else {
        res = await call(
          "save_link_route",
          state.currentPath,
          saveAnchor,
          targetIds,
          "",
          defaultEdgeType,
          state.activeKpId || "",
          oldAnchor,
          "",
          0,
          false,
          poolIds,
          targetEdges
        );
      }

      if (res.status !== "ok") {
        setStatus(res.message || "保存失败");
        return;
      }

      let doc = res.document;
      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await loadLinkTargets();
      }

      const auditEntry = doc?.link_audit?.links?.find((x) => x.anchor_text === saveAnchor);
      const needsMatch =
        p.mode === "create" ||
        anchorRenamed ||
        (auditEntry && auditEntry.status !== "ok");
      const shouldApplyInstances =
        selectedLines.length > 0 &&
        (needsMatch || selectedLinesNeedWrap(p.match, selectedLines));

      if (shouldApplyInstances) {
        const searchOptions = {
          ...readEditorLinkSearchOptions(),
        };
        const routeOld = (p.oldAnchorText || "").trim();
        if (routeOld && routeOld !== saveAnchor) searchOptions.route_anchor = routeOld;
        else if (searchQuery && searchQuery !== saveAnchor) searchOptions.route_anchor = routeOld || searchQuery;

        const applyRes = await call(
          "apply_link_instances",
          state.currentPath,
          saveAnchor,
          targetIds,
          selectedLines,
          "",
          defaultEdgeType,
          state.activeKpId || "",
          anchorRenamed ? oldAnchor : "",
          0,
          poolIds,
          searchOptions,
          targetEdges
        );
        if (applyRes.status !== "ok") {
          setStatus(applyRes.message || "挂接失败");
          return;
        }
        doc = applyRes.document;
      } else if (needsMatch && !selectedLines.length) {
        setStatus("保存失败", "请在弹窗中勾选正文匹配位置");
        return;
      }

      closeLinkModal({ skipReturn: true });

      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await renderPreview(doc);
        await loadLinkTargets();
      }

      setStatus("链接已保存", res.warning || `${saveAnchor} → ${targetIds.join(", ")}`);
      if (returnTo === "config") {
        openConfigModal({ tab: "links", highlightLinkTarget: configHighlight });
      }
      if (jumpAfter && targetIds.length) {
        const jumpRes = await call("resolve_links", targetIds);
        const primary = jumpRes.candidates?.[0];
        if (primary) await jumpToTarget(primary, { source: "link" });
      }
    } catch (e) {
      setStatus("保存失败", String(e.message || e));
    }
  }

  function highlightSnippet(snippet, highlight) {
    const s = snippet || "";
    const a = (highlight || "").trim();
    if (!a) return esc(s);
    if (s.includes(a)) {
      const i = s.indexOf(a);
      return esc(s.slice(0, i)) + `<mark>${esc(a)}</mark>` + esc(s.slice(i + a.length));
    }
    const wrapped = `[[${a}]]`;
    if (s.includes(wrapped)) {
      const i = s.indexOf(wrapped);
      return (
        esc(s.slice(0, i)) +
        `<mark>${esc(wrapped)}</mark>` +
        esc(s.slice(i + wrapped.length))
      );
    }
    return esc(s);
  }

  function matchRowBadge(m) {
    if (m.blocked) return "冲突";
    if (m.excluded) return "已排除";
    if (m.is_substring) return "子串";
    if (m.fuzzy) return "模糊";
    if (m.wrapped) return "已包裹";
    if (m.attached) return "已挂接";
    return "plain";
  }

  function resolveCanonicalAnchorFromMatch(match, selectedLines) {
    if (!match?.matches?.length || !selectedLines?.length) return null;
    const sel = selectedLines.map((ln) => Number(ln));
    if (sel.length === 1) {
      const row = match.matches.find((r) => r.line === sel[0]);
      const t = (row?.matched_text || "").trim();
      return t || null;
    }
    const wanted = new Set(sel);
    const texts = [
      ...new Set(
        match.matches
          .filter((r) => wanted.has(r.line))
          .map((r) => (r.matched_text || "").trim())
          .filter(Boolean)
      ),
    ];
    return texts.length === 1 ? texts[0] : null;
  }

  function resolveSaveAnchorFromSelection(match, selectedLines, fallback) {
    const canonical = resolveCanonicalAnchorFromMatch(match, selectedLines);
    if (canonical) return canonical;
    return (fallback || "").trim();
  }

  function defaultMatchSelection(matches) {
    return matches
      .filter((m) => !m.is_substring && !m.excluded && !m.blocked)
      .map((m) => m.line);
  }

  function matchPreselectLines(matches, preselectLines) {
    const selectable = matches.filter((m) => !m.is_substring && !m.excluded && !m.blocked);
    if (!selectable.length) return [];
    if (preselectLines?.length) {
      const ok = new Set(selectable.map((m) => m.line));
      return preselectLines.filter((ln) => ok.has(ln));
    }
    return defaultMatchSelection(matches);
  }

  function selectedLinesNeedWrap(match, selectedLines) {
    if (!match?.matches?.length || !selectedLines.length) return false;
    const sel = new Set(selectedLines);
    return match.matches.some(
      (m) => sel.has(m.line) && !m.wrapped && !m.is_substring && !m.excluded && !m.blocked
    );
  }

  function applyLinkMatchToolbarAction(m, action) {
    if (!m) return;
    if (action === "all") {
      const selectable = m.matches.filter(
        (row) => !row.is_substring && !row.excluded && !row.blocked
      );
      const allSelected = selectable.length > 0 && selectable.every((row) => m.selected.has(row.line));
      if (allSelected) {
        m.selected.clear();
      } else {
        selectable.forEach((row) => m.selected.add(row.line));
      }
    } else if (action === "plain") {
      m.selected.clear();
      m.matches.forEach((row) => {
        if (!row.wrapped && !row.is_substring && !row.excluded && !row.blocked)
          m.selected.add(row.line);
      });
    }
  }

  async function openLinkMatchInConfig(opts) {
    if (!state.currentPath) return;
    const anchor = (opts.anchorText || "").trim();
    if (!anchor) return;

    const searchOptions = {
      ...(opts.searchOptions || defaultLinkSearchOptions()),
      route_anchor: anchor,
    };
    setStatus("扫描匹配…");
    let scan;
    try {
      scan = await call(
        "scan_link_text_matches",
        state.currentPath,
        anchor,
        searchOptions
      );
    } catch (e) {
      setStatus("扫描失败", String(e.message || e));
      return;
    }
    if (scan.status !== "ok") {
      setStatus(scan.message || "扫描失败");
      return;
    }

    const matches = scan.matches || [];
    const selected = new Set(
      matchPreselectLines(matches, opts.preselectLines)
    );

    state.configLinkMatch = {
      anchorText: anchor,
      oldAnchorText: opts.oldAnchorText || null,
      targetIds: opts.targetIds || [],
      poolIds: opts.poolIds || [],
      edgeType: normalizeLinkEdgeType(opts.edgeType || opts.edgeHint || ""),
      matches,
      selected,
      jumpAfter: !!opts.jumpAfter,
      returnTo: opts.returnTo || null,
      configHighlight: opts.configHighlight || anchor,
      searchOptions,
    };

    const highlight = opts.configHighlight || anchor;
    const configOpen = !$("#config-modal").classList.contains("hidden");
    state.configTab = "links";
    if (configOpen) {
      renderConfigModal();
    } else {
      openConfigModal({ tab: "links", highlightLinkTarget: highlight });
    }
    requestAnimationFrame(() => refreshConfigLinkMatchPanel());
    setStatus(`匹配「${anchor}」`);
  }

  async function confirmConfigLinkMatch() {
    const m = state.configLinkMatch;
    if (!m || !state.currentPath) {
      setStatus("应用失败", "无匹配任务");
      return;
    }
    if (!m.selected.size) {
      const hasSubstring = m.matches.some((r) => r.is_substring && r.line);
      setStatus(
        "应用失败",
        hasSubstring
          ? "子串匹配不可挂接，请勾选带复选框的行"
          : "请先勾选要包裹的正文位置"
      );
      return;
    }
    const searchQuery = (m.anchorText || "").trim();
    const saveAnchor = resolveSaveAnchorFromSelection(m, [...m.selected], searchQuery);
    if (!saveAnchor) {
      setStatus("应用失败", "匹配文本不能为空");
      return;
    }
    setStatus("应用匹配…");
    try {
      const searchOptions = {
        ...readConfigLinkSearchOptions(),
      };
      const routeOld = (m.oldAnchorText || "").trim();
      if (routeOld && routeOld !== saveAnchor) searchOptions.route_anchor = routeOld;
      else if (searchQuery && searchQuery !== saveAnchor) searchOptions.route_anchor = routeOld || searchQuery;

      const res = await call(
        "apply_link_instances",
        state.currentPath,
        saveAnchor,
        m.targetIds,
        [...m.selected],
        "",
        m.edgeType || "reference",
        state.activeKpId || "",
        m.oldAnchorText || "",
        0,
        m.poolIds,
        searchOptions
      );
      if (res.status !== "ok") {
        setStatus(res.message || "应用失败");
        return;
      }
      const configHighlight = m.configHighlight || saveAnchor;
      const jumpAfter = m.jumpAfter;
      const targetIds = m.targetIds;
      closeConfigLinkMatch();
      const doc = res.document;
      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await renderPreview(doc);
        await loadLinkTargets();
      }
      setStatus("链接已挂接", `${saveAnchor} · ${m.selected.size} 处`);
      if (!$("#config-modal").classList.contains("hidden")) {
        renderConfigModal();
      } else {
        openConfigModal({ tab: "links", highlightLinkTarget: configHighlight });
      }
      if (jumpAfter && targetIds.length) {
        const jumpRes = await call("resolve_links", targetIds);
        const primary = jumpRes.candidates?.[0];
        if (primary) await jumpToTarget(primary, { source: "link" });
      }
    } catch (e) {
      setStatus("应用失败", String(e.message || e));
    }
  }

  async function detachLinkFromEntry(payload, linkEl) {
    if (!state.currentPath) return;
    let line = Number(linkEl?.dataset?.linkLine || payload.line || 0);
    if (!line && linkEl) {
      const block = linkEl.closest("[data-m0-src-line]");
      if (block) line = Number(block.dataset.m0SrcLine) || 0;
    }
    const label = payload.displayText || payload.targetId;
    const ok = window.confirm(
      `从跳转入口移除此处？\n\nL${line || "?"} · ${label}\n\n仅解除本处链接标记，保留跳转配置。`
    );
    if (!ok) return;
    if (!line) {
      setStatus("无法定位行号", "请在预览中右键链接");
      return;
    }
    setStatus("移除中…");
    try {
      const res = await call(
        "detach_link_instance",
        state.currentPath,
        payload.targetId,
        line
      );
      if (res.status !== "ok") {
        setStatus(res.message || "移除失败");
        return;
      }
      const doc = res.document;
      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await renderPreview(doc);
      }
      setStatus("已从跳转入口移除此处");
    } catch (e) {
      setStatus("移除失败", String(e.message || e));
    }
  }

  async function deleteLinkFromConfig(anchorText) {
    if (!state.currentPath) return;
    const anchor = (anchorText || "").trim();
    if (!anchor) return;
    const ok = window.confirm(
      `删除跳转入口「${anchor}」？\n\n将移除链接配置，并解除正文中所有 [[${anchor}]] 包裹（保留可见文字）。`
    );
    if (!ok) return;
    setStatus("删除中…");
    try {
      const res = await call("delete_link_route", state.currentPath, anchor);
      if (res.status !== "ok") {
        setStatus(res.message || "删除失败");
        return;
      }
      const doc = res.document;
      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await renderPreview(doc);
        await loadLinkTargets();
      }
      if (!$("#config-modal")?.classList.contains("hidden")) {
        state.configTab = "links";
        renderConfigModal();
      }
      setStatus("已删除跳转入口", anchor);
    } catch (e) {
      setStatus("删除失败", String(e.message || e));
    }
  }

  async function removeLinkFromDocument(payload) {
    if (!state.currentPath) return;
    const ok = window.confirm(
      `移除链接标记并保留显示文字？\n\n${payload.displayText || payload.targetId}`
    );
    if (!ok) return;
    setStatus("移除中…");
    try {
      const res = await call(
        "remove_link",
        state.currentPath,
        payload.targetId,
        payload.displayText !== payload.targetId ? payload.displayText : "",
        payload.linkType || ""
      );
      if (res.status !== "ok") {
        setStatus(res.message || "移除失败");
        return;
      }
      const doc = res.document;
      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await renderPreview(doc);
      }
      setStatus("已移除 [[]] 标记");
    } catch (e) {
      setStatus("移除失败", String(e.message || e));
    }
  }

  async function onMemoriaLinkClick(el) {
    const target = el.dataset.linkTarget;
    const type = el.dataset.linkType || "";
    if (!target) return;
    if (el.classList.contains("m0-link-broken")) {
      await openLinkEditorFromElement(el);
      return;
    }
    try {
      const multiRaw = el.dataset.linkTargets;
      if (multiRaw) {
        let ids;
        try {
          ids = JSON.parse(multiRaw);
        } catch (_) {
          ids = [];
        }
        const res = await call("resolve_links", ids);
        if (res.status === "not_found" || res.status === "error") {
          setStatus(res.message || "多目标链接无法解析", "未绑定");
          return;
        }
        const candidates = res.candidates || [];
        if (candidates.length === 1) {
          await jumpToTarget(candidates[0], { source: "link" });
          return;
        }
        showLinkPicker(
          el.textContent?.trim() || target,
          candidates
        );
        return;
      }
      const routeIds = state.doc?.link_overrides?.[target];
      if (routeIds?.length === 1) {
        const res = await call("resolve_link", routeIds[0]);
        if (res.status === "ok" && res.candidates?.[0]) {
          await jumpToTarget(res.candidates[0], { source: "link" });
          return;
        }
      }
      const res = await call("resolve_link", target);
      if (res.status === "not_found" || res.status === "error") {
        setStatus(res.message || `未找到 [[${target}]]`, "未绑定");
        return;
      }
      if (res.status === "ambiguous") {
        showLinkPicker(target, res.candidates || []);
        return;
      }
      const candidate = (res.candidates || [])[0];
      if (!candidate) {
        setStatus(`未找到 [[${target}]]`, "未绑定");
        return;
      }
      await jumpToTarget(candidate, { source: "link" });
    } catch (e) {
      setStatus(`链接失败: ${target}`, String(e.message || e));
    }
    if (type) {
      /* edge_hint 预留 M2/M3 边类型展示 */
    }
  }

  async function navBack() {
    if (!window.MemoriaNavStack || !MemoriaNavStack.canBack()) return;
    const frame = MemoriaNavStack.navBack();
    updateNavButtons();
    if (frame) await openFile(frame.file, { fromNav: true, kpId: frame.kpId });
  }

  async function navForward() {
    if (!window.MemoriaNavStack || !MemoriaNavStack.canForward()) return;
    const frame = MemoriaNavStack.navForward();
    updateNavButtons();
    if (frame) await openFile(frame.file, { fromNav: true, kpId: frame.kpId });
  }

  function linkContextPayload(linkEl) {
    const targetId = linkEl.dataset.linkTarget || "";
    const linkType = linkEl.dataset.linkType || "";
    const displayText = linkEl.textContent?.trim() || targetId;
    const isBroken = linkEl.classList.contains("m0-link-broken");
    const multiRaw = linkEl.dataset.linkTargets;
    let isMulti = linkEl.classList.contains("m0-link-multi");
    let multiTargets = null;
    if (multiRaw) {
      try {
        multiTargets = JSON.parse(multiRaw);
        isMulti = Array.isArray(multiTargets) && multiTargets.length > 1;
      } catch (_) {
        multiTargets = null;
      }
    }
    return { targetId, linkType, displayText, isBroken, isMulti, multiTargets };
  }

  function bindLinkContextMenu(linkEl) {
    if (!window.MemoriaLinkContextMenu) return;
    linkEl.addEventListener("contextmenu", (e) => {
      const payload = linkContextPayload(linkEl);
      MemoriaLinkContextMenu.showForLink(e, linkEl, {
        ...payload,
        filePath: state.currentPath,
        linkLine: Number(linkEl.dataset.linkLine) || 0,
        onEditLink: () => openLinkEditorFromElement(linkEl),
        onDetachLink: (p) => detachLinkFromEntry(p, linkEl),
        onRemoveLink: (p) => removeLinkFromDocument(p),
        onStatus: (msg) => setStatus(msg),
      });
    });
  }

  function bindPreviewLinks() {
    const preview = $("#preview");
    if (!preview) return;
    preview.querySelectorAll(".memoria-link").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        onMemoriaLinkClick(el);
      });
      el.addEventListener("mouseenter", (e) => {
        if (shouldSuppressHoverHighlight(e)) return;
        highlightGraphFromLink(el);
      });
      el.addEventListener("mouseleave", (e) => {
        if (shouldSuppressHoverHighlight(e)) return;
        if (state.graphLinkFocusEl === el) clearGraphLinkHighlight();
      });
      bindLinkContextMenu(el);
    });
  }

  function kpRangesFromDoc(kps) {
    return (kps || [])
      .filter((kp) => kp.range_resolved?.ok)
      .map((kp) => ({
        kp_id: kp.id,
        start: kp.range_resolved.start_line,
        end: kp.range_resolved.end_line,
      }));
  }

  function strictlyContainsKpRange(outer, inner) {
    if (outer.kp_id === inner.kp_id) return false;
    if (outer.start > inner.start || inner.end > outer.end) return false;
    return outer.start < inner.start || inner.end < outer.end;
  }

  function minimalKpsForLine(line, ranges) {
    const hits = ranges.filter((r) => line >= r.start && line <= r.end);
    if (!hits.length) return [];
    return hits
      .filter(
        (r) =>
          !hits.some(
            (other) =>
              r.kp_id !== other.kp_id && strictlyContainsKpRange(r, other)
          )
      )
      .map((r) => r.kp_id);
  }

  function rawLinkTargetIds(anchorText, linkEl) {
    const multi = linkEl?.dataset?.linkTargets;
    if (multi) {
      try {
        const parsed = JSON.parse(multi);
        if (Array.isArray(parsed) && parsed.length) return parsed;
      } catch (_) {
        /* fall through */
      }
    }
    const key = (anchorText || linkEl?.dataset?.linkTarget || "").trim();
    if (!key) return [];
    const overrides = state.doc?.link_overrides || {};
    if (overrides[key]?.length) return [...overrides[key]];
    const sidecar = state.doc?.sidecar?.links || [];
    const entry = sidecar.find((l) => l.anchor_text === key);
    if (entry?.targets?.length) return [...entry.targets];
    return [key];
  }

  function resolveGraphNodeIds(rawIds) {
    const nodes = state.graphEngine?.nodes || [];
    if (!nodes.length) return [];
    const known = new Set(nodes.map((n) => n.id));
    const out = [];
    const seen = new Set();
    for (const raw of rawIds || []) {
      const tid = String(raw || "").trim();
      if (!tid || tid === "?" || seen.has(tid)) continue;
      if (known.has(tid)) {
        seen.add(tid);
        out.push(tid);
      }
    }
    return out;
  }

  function updateGraphNodeHint(node) {
    const hint = activeGraphHint();
    if (!hint || !node) return;
    if (window.MemoriaGraphLabels) {
      hint.innerHTML = MemoriaGraphLabels.resolveNodeHoverHtml(node);
    } else {
      hint.textContent = `${node.name || node.label || node.id} · ${node.file || ""}`;
    }
  }

  function highlightGraphFromKp(kpId) {
    const ids = resolveGraphNodeIds([kpId]);
    const nodeId = ids[0] || null;
    if (!nodeId || !isNodeInCurrentGraphLayout(nodeId)) {
      clearGraphKpHover();
      return;
    }
    state.kpGraphHoverId = nodeId;
    state.graphView2d?.setRemoteHover?.(nodeId);
    state.graphView3d?.setRemoteHover?.(nodeId);
    const node = state.graphEngine?.getNode(nodeId);
    if (node && isGraphSidebarTab()) {
      updateGraphNodeHint(node);
    }
  }

  function clearGraphKpHover() {
    state.kpGraphHoverId = null;
    state.graphView2d?.clearRemoteHover?.();
    state.graphView3d?.clearRemoteHover?.();
    if (!state.graphLinkFocusEl && (state.sidebarTab === "graph2d" || state.sidebarTab === "graph3d")) {
      updateGraphAuditHint();
    }
  }

  function updateGraphLinkFocusHint(sourceIds, targetIds, rawTargets) {
    const hint = activeGraphHint();
    if (!hint) return;
    if (!sourceIds.length && !targetIds.length && !rawTargets?.length) {
      updateGraphAuditHint();
      return;
    }
    const src = sourceIds.length ? sourceIds.join("、") : "—";
    const tgt = targetIds.length
      ? targetIds.join("、")
      : (rawTargets || []).join("、");
    const note =
      targetIds.length || !rawTargets?.length
        ? ""
        : ' <span class="m0-muted">（目标未入图谱）</span>';
    hint.innerHTML = `<span class="m0-muted">链接</span> ${esc(src)} → ${esc(tgt)}${note}`;
  }

  function highlightGraphFromLinkAnchor(anchorText, line, linkEl) {
    const ranges = kpRangesFromDoc(state.doc?.knowledge_points);
    const allSourceIds = line ? minimalKpsForLine(line, ranges) : [];
    const rawTargets = rawLinkTargetIds(anchorText, linkEl);
    const allTargetIds = resolveGraphNodeIds(rawTargets);
    const sourceIds = graphIdsInCurrentLayout(allSourceIds);
    const targetIds = graphIdsInCurrentLayout(allTargetIds);
    if (sourceIds.length || targetIds.length) {
      state.graphView2d?.setExternalFocus?.({ sourceIds, targetIds });
      state.graphView3d?.setExternalFocus?.({ sourceIds, targetIds });
    } else {
      state.graphView2d?.clearExternalFocus?.();
      state.graphView3d?.clearExternalFocus?.();
    }
    updateGraphLinkFocusHint(allSourceIds, allTargetIds, rawTargets);
  }

  function highlightGraphFromLink(linkEl) {
    if (!linkEl) return;
    if (state.graphLinkFocusEl && state.graphLinkFocusEl !== linkEl) {
      state.graphLinkFocusEl.classList.remove("is-graph-link-focus");
    }
    state.graphLinkFocusEl = linkEl;
    linkEl.classList.add("is-graph-link-focus");
    const line = +(linkEl.dataset.linkLine || 0);
    const anchor = linkEl.dataset.linkTarget || linkEl.textContent?.trim() || "";
    highlightGraphFromLinkAnchor(anchor, line, linkEl);
  }

  function clearGraphLinkHighlight() {
    state.graphView2d?.clearExternalFocus?.();
    state.graphView3d?.clearExternalFocus?.();
    if (state.graphLinkFocusEl) {
      state.graphLinkFocusEl.classList.remove("is-graph-link-focus");
      state.graphLinkFocusEl = null;
    }
    if (state.sidebarTab === "graph2d" || state.sidebarTab === "graph3d") {
      if (state.kpGraphHoverId) {
        const node = state.graphEngine?.getNode(state.kpGraphHoverId);
        if (node) updateGraphNodeHint(node);
      } else {
        updateGraphLinkFocusHint([], [], []);
      }
    }
  }

  function singleWikilinkAnchorOnLine(lineText) {
    const re = /\[\[([^\]|#\]]+)(?:#([^\]|#]+))?(?:\|([^\]]+))?\]\]/g;
    const matches = [...String(lineText || "").matchAll(re)];
    if (matches.length !== 1) return null;
    return matches[0][1].trim();
  }

  function bindEditorLinkHover() {
    const editor = $("#editor");
    if (!editor || editor.dataset.linkHoverBound) return;
    editor.dataset.linkHoverBound = "1";
    editor.addEventListener("mouseover", (e) => {
      if (shouldSuppressHoverHighlight(e)) return;
      if (state.viewMode === "preview") return;
      const row = e.target.closest(".m0-line");
      if (!row || !editor.contains(row)) return;
      const line = +(row.dataset.line || 0);
      const anchor = singleWikilinkAnchorOnLine(state.doc?.lines?.[line - 1] || "");
      if (!anchor) {
        if (state._editorLinkHoverLine) {
          state._editorLinkHoverLine = 0;
          clearGraphLinkHighlight();
        }
        return;
      }
      if (state._editorLinkHoverLine === line) return;
      state._editorLinkHoverLine = line;
      highlightGraphFromLinkAnchor(anchor, line);
    });
    editor.addEventListener("mouseleave", (e) => {
      if (shouldSuppressHoverHighlight(e)) return;
      if (e.relatedTarget && editor.contains(e.relatedTarget)) return;
      state._editorLinkHoverLine = 0;
      clearGraphLinkHighlight();
    });
  }

  function lineForNodeInContainer(node, container) {
    let el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    while (el && el !== container) {
      const row = el.closest?.("[data-line]");
      if (row && container.contains(row)) return +(row.dataset.line || 0);
      const block = el.closest?.("[data-m0-src-line]");
      if (block && container.contains(block)) return +(block.dataset.m0SrcLine || 0);
      el = el.parentElement;
    }
    return 0;
  }

  function previewLinesInRange(preview, lo, hi) {
    const lines = new Set();
    preview.querySelectorAll("[data-m0-src-line]").forEach((el) => {
      const s = +(el.dataset.m0SrcLine || 0);
      const e = +(el.dataset.m0SrcLineEnd || s);
      for (let n = Math.max(lo, s); n <= Math.min(hi, e); n++) lines.add(n);
    });
    return [...lines].sort((a, b) => a - b);
  }

  function walkPreviewTextNodes(root, skipSelector) {
    const nodes = [];
    if (!root) return nodes;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (skipSelector && node.parentElement?.closest(skipSelector)) {
          return NodeFilter.FILTER_REJECT;
        }
        if (!node.textContent?.replace(/\s/g, "")) return NodeFilter.FILTER_SKIP;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    return nodes;
  }

  function applyPreviewTextSelection(preview, anchorLine, focusLine) {
    const lo = Math.min(anchorLine, focusLine);
    const hi = Math.max(anchorLine, focusLine);
    const blocks = [...preview.querySelectorAll(".m0-src-block")]
      .filter((el) => {
        const s = +(el.dataset.m0SrcLine || 0);
        const e = +(el.dataset.m0SrcLineEnd || s);
        return e >= lo && s <= hi;
      })
      .sort((a, b) => +(a.dataset.m0SrcLine || 0) - +(b.dataset.m0SrcLine || 0));
    if (!blocks.length) return false;
    const skip = ".memoria-link, mjx-container";
    const textNodes = [];
    blocks.forEach((b) => textNodes.push(...walkPreviewTextNodes(b, skip)));
    if (!textNodes.length) return false;
    const range = document.createRange();
    const first = textNodes[0];
    const last = textNodes[textNodes.length - 1];
    range.setStart(first, 0);
    range.setEnd(last, last.textContent.length);
    const sel = window.getSelection();
    if (!sel) return false;
    sel.removeAllRanges();
    sel.addRange(range);
    return true;
  }

  function markPreviewDragSelect(preview, anchorLine, focusLine) {
    const lo = Math.min(anchorLine, focusLine);
    const hi = Math.max(anchorLine, focusLine);
    preview.querySelectorAll(".m0-src-block.is-drag-select").forEach((el) => {
      el.classList.remove("is-drag-select");
    });
    preview.querySelectorAll(".m0-src-block").forEach((el) => {
      const s = +(el.dataset.m0SrcLine || 0);
      const e = +(el.dataset.m0SrcLineEnd || s);
      if (e >= lo && s <= hi) el.classList.add("is-drag-select");
    });
  }

  function clearPreviewDragSelect(preview) {
    preview.querySelectorAll(".m0-src-block.is-drag-select").forEach((el) => {
      el.classList.remove("is-drag-select");
    });
  }

  function getSelectionInContainer(container) {
    const sel = window.getSelection();
    if (!sel?.rangeCount || !container) return null;
    const text = sel.toString().trim();
    if (!text) return null;
    const anchor = sel.anchorNode;
    const focus = sel.focusNode;
    if (!anchor || !focus || !container.contains(anchor) || !container.contains(focus)) {
      return null;
    }
    const a = lineForNodeInContainer(anchor, container);
    const f = lineForNodeInContainer(focus, container);
    let lines = [];
    if (container.id === "preview" && a && f) {
      lines = previewLinesInRange(container, Math.min(a, f), Math.max(a, f));
    } else if (a && f) {
      const lo = Math.min(a, f);
      const hi = Math.max(a, f);
      for (let i = lo; i <= hi; i++) lines.push(i);
    } else if (a) {
      lines.push(a);
    }
    return { text, lines };
  }

  function applyEditorTextSelection(anchorLine, focusLine) {
    const lo = Math.min(anchorLine, focusLine);
    const hi = Math.max(anchorLine, focusLine);
    const startEl = document.querySelector(`#line-${lo} .m0-line-content`);
    const endEl = document.querySelector(`#line-${hi} .m0-line-content`);
    if (!startEl || !endEl) return false;
    const startNode = startEl.firstChild || startEl;
    const endNode = endEl.firstChild || endEl;
    const endLen = endNode.textContent?.length ?? 0;
    const range = document.createRange();
    range.setStart(startNode, 0);
    range.setEnd(endNode, endLen);
    const sel = window.getSelection();
    if (!sel) return false;
    sel.removeAllRanges();
    sel.addRange(range);
    return true;
  }

  function markEditorDragSelectLines(anchorLine, focusLine) {
    const lo = Math.min(anchorLine, focusLine);
    const hi = Math.max(anchorLine, focusLine);
    document.querySelectorAll("#editor .m0-line.is-drag-select").forEach((el) => {
      el.classList.remove("is-drag-select");
    });
    for (let n = lo; n <= hi; n++) {
      document.getElementById("line-" + n)?.classList.add("is-drag-select");
    }
  }

  function clearEditorDragSelectLines() {
    document.querySelectorAll("#editor .m0-line.is-drag-select").forEach((el) => {
      el.classList.remove("is-drag-select");
    });
  }

  function bindEditorSelectInteraction() {
    const editor = $("#editor");
    if (!editor || editor.dataset.selectBound) return;
    editor.dataset.selectBound = "1";

    let dragSelect = null;

    editor.addEventListener("beforeinput", (e) => {
      if (e.target.closest(".m0-line-content")) e.preventDefault();
    });
    editor.addEventListener("paste", (e) => {
      if (e.target.closest(".m0-line-content")) e.preventDefault();
    });
    editor.addEventListener("drop", (e) => {
      if (e.target.closest(".m0-line-content")) e.preventDefault();
    });

    editor.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      const content = e.target.closest(".m0-line-content");
      if (!content) return;
      const line = +(content.closest("[data-line]")?.dataset.line || 0);
      if (!line) return;
      dragSelect = { anchorLine: line, focusLine: line };
    });

    editor.addEventListener("mousemove", (e) => {
      if (!dragSelect || e.buttons !== 1) return;
      const row = e.target.closest(".m0-line");
      if (!row || !editor.contains(row)) return;
      const focusLine = +(row.dataset.line || 0);
      if (!focusLine || focusLine === dragSelect.focusLine) return;
      dragSelect.focusLine = focusLine;
      applyEditorTextSelection(dragSelect.anchorLine, dragSelect.focusLine);
      markEditorDragSelectLines(dragSelect.anchorLine, dragSelect.focusLine);
    });

    const endDragSelect = () => {
      if (!dragSelect) return;
      if (dragSelect.anchorLine !== dragSelect.focusLine) {
        applyEditorTextSelection(dragSelect.anchorLine, dragSelect.focusLine);
      }
      dragSelect = null;
      clearEditorDragSelectLines();
    };
    editor.addEventListener("mouseup", endDragSelect);
    window.addEventListener("mouseup", endDragSelect);

    editor.addEventListener("dblclick", (e) => {
      const content = e.target.closest(".m0-line-content");
      if (!content) return;
      const line = +(content.closest("[data-line]")?.dataset.line || 0);
      if (!line) return;
      e.preventDefault();
      applyEditorTextSelection(line, line);
    });
  }

  function bindPreviewSelectInteraction() {
    const preview = $("#preview");
    if (!preview || preview.dataset.selectBound) return;
    preview.dataset.selectBound = "1";

    let dragSelect = null;

    preview.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest(".memoria-link")) return;
      if (e.target.closest("mjx-container")) return;
      const block = e.target.closest(".m0-src-block");
      if (!block || !preview.contains(block)) return;
      const line = +(block.dataset.m0SrcLine || 0);
      if (!line) return;
      dragSelect = { anchorLine: line, focusLine: line };
    });

    preview.addEventListener("mousemove", (e) => {
      if (!dragSelect || e.buttons !== 1) return;
      if (e.target.closest(".memoria-link")) return;
      const block = e.target.closest(".m0-src-block");
      if (!block || !preview.contains(block)) return;
      const focusLine = +(block.dataset.m0SrcLine || 0);
      if (!focusLine || focusLine === dragSelect.focusLine) return;
      dragSelect.focusLine = focusLine;
      applyPreviewTextSelection(preview, dragSelect.anchorLine, dragSelect.focusLine);
      markPreviewDragSelect(preview, dragSelect.anchorLine, dragSelect.focusLine);
    });

    const endDragSelect = () => {
      if (!dragSelect) return;
      if (dragSelect.anchorLine !== dragSelect.focusLine) {
        applyPreviewTextSelection(preview, dragSelect.anchorLine, dragSelect.focusLine);
      }
      dragSelect = null;
      clearPreviewDragSelect(preview);
    };
    preview.addEventListener("mouseup", endDragSelect);
    window.addEventListener("mouseup", endDragSelect);

    preview.addEventListener("dblclick", (e) => {
      if (e.target.closest(".memoria-link")) return;
      if (e.target.closest("mjx-container")) return;
      const block = e.target.closest(".m0-src-block");
      if (!block) return;
      const lo = +(block.dataset.m0SrcLine || 0);
      const hi = +(block.dataset.m0SrcLineEnd || lo);
      if (!lo) return;
      e.preventDefault();
      applyPreviewTextSelection(preview, lo, hi);
    });
  }

  function bindEditorSelectionMenu() {
    const editor = $("#editor");
    if (!editor || !window.MemoriaLinkContextMenu) return;
    editor.addEventListener("contextmenu", (e) => {
      if (!state.currentPath) return;
      const info = getSelectionInContainer(editor);
      if (!info) return;
      MemoriaLinkContextMenu.showForSelection(e, info.text, {
        filePath: state.currentPath,
        lines: info.lines,
        onStatus: setStatus,
        onCreateLink: ({ text: t }) =>
          openLinkEditorFromSelection(t, { preselectLines: info.lines }),
        onCreateKp: ({ text: t, lines }) => openAssistFromSelection({ text: t, lines }),
      });
    });
  }

  function bindPreviewSelectionMenu() {
    const preview = $("#preview");
    if (!preview || !window.MemoriaLinkContextMenu) return;
    preview.addEventListener("contextmenu", (e) => {
      if (e.target.closest(".memoria-link")) return;
      if (!state.currentPath) return;
      const info = getSelectionInContainer(preview);
      if (!info) return;
      const lines = state.doc?.lines || [];
      const md = info.lines?.length
        ? info.lines
            .map((n) => lines[n - 1] || "")
            .join("\n")
            .trim()
        : "";
      MemoriaLinkContextMenu.showForSelection(e, info.text, {
        filePath: state.currentPath,
        lines: info.lines,
        onStatus: setStatus,
        markdown: md || undefined,
        onCreateLink: ({ text: t }) =>
          openLinkEditorFromSelection(t, { preselectLines: info.lines }),
        onCreateKp: ({ text: t, lines }) => openAssistFromSelection({ text: t, lines }),
      });
    });
  }

  function renderProposals() {
    /* 已移至配置窗口 */
  }

  function errorLabel(err) {
    const map = {
      start_snippet_not_found: "起点未找到",
      end_snippet_not_found: "终点未找到",
      end_before_start: "终点在起点前",
      missing_snippet: "缺少 snippet",
    };
    return map[err] || err;
  }

  function onKpClick(kpId, opts = {}) {
    const kp = (state.doc.knowledge_points || []).find((k) => k.id === kpId);
    if (!kp) return;
    if (!opts.skipNav && state.currentPath && window.MemoriaNavStack) {
      MemoriaNavStack.push({
        file: state.currentPath,
        kpId,
        source: "kp",
      });
      updateNavButtons();
    }
    state.activeKpId = kpId;
    renderKpList(state.doc);

    const rr = kp.range_resolved || {};
    if (rr.ok) {
      highlightRange(rr.start_line, rr.end_line);
      return;
    }
    if (opts.skipRangeModal) return;
    openKpModal(kpId, { tab: "range" });
  }

  function cancelKpHighlightTimers() {
    if (state.kpHighlightFadeTimer != null) {
      clearTimeout(state.kpHighlightFadeTimer);
      state.kpHighlightFadeTimer = null;
    }
    if (state.kpHighlightClearTimer != null) {
      clearTimeout(state.kpHighlightClearTimer);
      state.kpHighlightClearTimer = null;
    }
  }

  function previewElOverlapsRange(el, startLine, endLine) {
    const elStart = +(el.dataset.m0SrcLine || 0);
    const elEnd = +(el.dataset.m0SrcLineEnd || elStart);
    if (!elStart) return false;
    return elStart <= endLine && elEnd >= startLine;
  }

  function clearHighlights() {
    document.querySelectorAll(".m0-line").forEach((el) => {
      el.classList.remove("kp-highlight-flash", "kp-error-flash", "fade-out", "in-range", "kp-hover");
    });
  }

  function clearKpListItemErrorHighlight() {
    document.querySelectorAll(".m0-kp-item.error-highlight").forEach((el) => {
      el.classList.remove("error-highlight");
    });
  }

  function dismissKpRangeHighlight() {
    cancelKpHighlightTimers();
    clearHighlights();
    clearPreviewHighlights();
    clearKpListItemErrorHighlight();
  }

  function clearKpHoverHighlight() {
    document.querySelectorAll(".m0-line.kp-hover").forEach((el) => {
      el.classList.remove("in-range", "kp-hover");
    });
    if (state.kpHighlightClearTimer == null && state.kpHighlightFadeTimer == null) {
      clearPreviewHighlights();
    }
  }

  function highlightKpHover(kpId) {
    const kp = (state.doc?.knowledge_points || []).find((k) => k.id === kpId);
    const rr = kp?.range_resolved;
    if (!rr?.ok) return;
    document.querySelectorAll(".m0-line.kp-hover").forEach((el) => {
      el.classList.remove("in-range", "kp-hover");
    });
    for (let n = rr.start_line; n <= rr.end_line; n++) {
      const line = document.getElementById("line-" + n);
      if (line) line.classList.add("in-range", "kp-hover");
    }
    if (state.viewMode !== "source" && state.kpHighlightClearTimer == null) {
      highlightPreviewRange(rr.start_line, rr.end_line, { scroll: false });
    }
  }

  function remapOpenTabsAfterPathRepair(applied) {
    if (!applied?.length) return;
    const map = new Map(
      applied.map((m) => [normRelPath(m.from), normRelPath(m.to)])
    );
    state.openTabs = state.openTabs.map((t) => {
      const next = map.get(normRelPath(t.path));
      return next ? { ...t, path: next } : t;
    });
    if (state.currentPath) {
      const next = map.get(normRelPath(state.currentPath));
      if (next) state.currentPath = next;
    }
  }

  function scrollEditorToLine(lineNum) {
    const line = document.getElementById("line-" + lineNum);
    if (line) line.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function highlightRange(startLine, endLine) {
    dismissKpRangeHighlight();

    const scrollSource = state.viewMode !== "preview";
    let firstSource = null;
    for (let n = startLine; n <= endLine; n++) {
      const line = document.getElementById("line-" + n);
      if (line) {
        line.classList.remove("fade-out");
        line.classList.add("in-range", "kp-highlight-flash");
        if (n === startLine) firstSource = line;
      }
    }
    if (scrollSource && firstSource) {
      firstSource.scrollIntoView({ block: "start", behavior: "smooth" });
    }

    if (state.viewMode !== "source") {
      highlightPreviewRange(startLine, endLine, { scroll: true, flash: true });
    }

    state.kpHighlightFadeTimer = window.setTimeout(() => {
      document.querySelectorAll(".m0-line.kp-highlight-flash").forEach((el) => {
        el.classList.add("fade-out");
      });
      document.getElementById("m0-preview-range-band")?.classList.add("fade-out");
      state.kpHighlightFadeTimer = null;
    }, 800);

    state.kpHighlightClearTimer = window.setTimeout(() => {
      dismissKpRangeHighlight();
      state.kpHighlightClearTimer = null;
    }, 2500);
  }

  // 检查面板"打开"跳转的红色错误高亮：不自动淡出，由用户后续操作清除
  function highlightRangeWithError(startLine, endLine) {
    dismissKpRangeHighlight();

    const scrollSource = state.viewMode !== "preview";
    let firstSource = null;
    for (let n = startLine; n <= endLine; n++) {
      const line = document.getElementById("line-" + n);
      if (line) {
        line.classList.add("in-range", "kp-error-flash");
        if (n === startLine) firstSource = line;
      }
    }
    if (scrollSource && firstSource) {
      firstSource.scrollIntoView({ block: "start", behavior: "smooth" });
    }

    if (state.viewMode !== "source") {
      highlightPreviewRange(startLine, endLine, { scroll: true, flash: true, error: true });
    }
  }

  // 左侧知识点列表定位高亮：滚动到对应 KP 并添加 error 样式
  function highlightKpListItemWithError(kpId) {
    if (!kpId) return;
    const items = document.querySelectorAll(".m0-kp-item");
    for (const item of items) {
      if (item.dataset.kp === kpId) {
        item.classList.add("error-highlight");
        item.scrollIntoView({ block: "center", behavior: "smooth" });
        return;
      }
    }
  }

  // 滚动左侧知识点列表到指定 KP 项（不改变样式，仅定位）
  function scrollKpListItemIntoView(kpId) {
    if (!kpId) return;
    const kpList = $("#kp-list");
    if (!kpList) return;
    const items = kpList.querySelectorAll(".m0-kp-item");
    for (const item of items) {
      if (item.dataset.kp === kpId) {
        const containerTop = kpList.getBoundingClientRect().top;
        const itemTop = item.getBoundingClientRect().top;
        kpList.scrollTop += itemTop - containerTop;
        return;
      }
    }
  }

  function clearPreviewHighlights() {
    document.getElementById("m0-preview-range-band")?.remove();
  }

  function previewOffsetWithin(el, container) {
    const er = el.getBoundingClientRect();
    const cr = container.getBoundingClientRect();
    return {
      top: er.top - cr.top,
      bottom: er.bottom - cr.top,
    };
  }

  function layoutPreviewRangeBand(preview, startLine, endLine) {
    const matches = [...preview.querySelectorAll("[data-m0-src-line]")].filter((el) =>
      previewElOverlapsRange(el, startLine, endLine)
    );
    if (!matches.length) return null;

    let top = Infinity;
    let bottom = -Infinity;
    let first = null;
    let firstLine = Infinity;

    for (const el of matches) {
      const pos = previewOffsetWithin(el, preview);
      top = Math.min(top, pos.top);
      bottom = Math.max(bottom, pos.bottom);
      const ln = +(el.dataset.m0SrcLine || 0);
      if (ln >= startLine && ln < firstLine) {
        firstLine = ln;
        first = el;
      }
    }
    // Fallback: if no block starts at/after startLine (e.g. target line is
    // inside a block whose startLine < target), pick the first match in DOM
    // order (the outermost containing block).
    if (!first && matches.length) {
      first = matches[0];
    }

    if (!Number.isFinite(top) || bottom <= top) return first;

    let band = document.getElementById("m0-preview-range-band");
    if (!band) {
      band = document.createElement("div");
      band.id = "m0-preview-range-band";
      band.className = "m0-preview-range-band";
      band.setAttribute("aria-hidden", "true");
      preview.appendChild(band);
    }

    band.style.top = `${Math.max(0, top)}px`;
    band.style.height = `${bottom - top}px`;
    return first;
  }

  function highlightPreviewRange(startLine, endLine, opts) {
    if (!state.doc) return;
    const preview = $("#preview");
    if (!preview) return;
    if (opts?.flash !== false) {
      clearPreviewHighlights();
    }
    const first = layoutPreviewRangeBand(preview, startLine, endLine);
    const band = document.getElementById("m0-preview-range-band");
    if (band) {
      band.classList.toggle("error", !!opts?.error);
    }
    if (opts?.scroll && first) {
      first.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }

  function openAssistForNewKp(opts = {}) {
    openKpModalForCreate(opts);
  }

  function openAssistFromSelection({ text, lines }) {
    if (!lines?.length) return;
    const lo = Math.min(...lines);
    const hi = Math.max(...lines);
    const name = (text || "").split(/\n/)[0].trim().slice(0, 80) || "新知识点";
    openKpModalForCreate({
      kpId: slugify(name),
      name,
      startLine: lo,
      endLine: hi,
    });
  }

  function readAssistCreateFields() {
    const host = getAssistHostEl();
    if (!host) return { kpId: "", name: "" };
    return {
      kpId: host.querySelector("[data-kp-create-id]")?.value?.trim() || "",
      name: host.querySelector("[data-kp-create-name]")?.value?.trim() || "",
    };
  }

  const ASSIST_CONTEXT_LINES = 3;
  const ASSIST_PREVIEW_TAIL_LINES = 120;

  function getAssistViewWindow(start, end, total) {
    const ctx = ASSIST_CONTEXT_LINES;
    const viewStart = Math.max(1, start - ctx);
    const viewEnd = Math.min(
      total,
      Math.max(end + ctx, viewStart + ASSIST_PREVIEW_TAIL_LINES - 1)
    );
    return { viewStart, viewEnd };
  }

  function getAssistRangeInputs() {
    const host = getAssistHostEl();
    const total = state.doc?.lines?.length || 0;
    const panel = state.kpPanel;
    let start = Math.max(1, +(host?.querySelector("[data-range-start]")?.value || panel?.startLine || 1));
    let end = Math.max(1, +(host?.querySelector("[data-range-end]")?.value || panel?.endLine || 1));
    if (total > 0) {
      start = Math.min(start, total);
      end = Math.min(end, total);
    }
    return { start, end, total, valid: total > 0 && start <= end };
  }

  function assistPreviewToolbarHtml() {
    const mode = state.assistPreviewMode || "source";
    return `<div class="m0-assist-preview-head">
      <span class="m0-muted">范围预览</span>
      <div class="m0-view-toggle" role="tablist" aria-label="预览模式">
        <button type="button" class="m0-view-btn${mode === "source" ? " active" : ""}" data-assist-view="source">源码</button>
        <button type="button" class="m0-view-btn${mode === "markdown" ? " active" : ""}" data-assist-view="markdown">Markdown</button>
      </div>
    </div>`;
  }

  function bindAssistPreviewToolbar(wrap) {
    wrap.querySelectorAll("[data-assist-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.assistPreviewMode = btn.dataset.assistView;
        state.assistLastView = null;
        renderAssistPreview({ forceScroll: true });
      });
    });
  }

  function setAssistScrollFocus(focus) {
    state.assistScrollFocus = focus === "end" ? "end" : "start";
  }

  function assistScrollContainer(wrap) {
    return wrap.querySelector("#assist-preview-scroll") || wrap.querySelector("#assist-md-scroll");
  }

  function getAssistLayoutAnchors(wrap) {
    if (wrap.querySelector("#assist-md-scroll")) {
      return {
        startEl: wrap.querySelector("#assist-md-range"),
        endEl: wrap.querySelector("#assist-md-range-end"),
      };
    }
    return {
      startEl: wrap.querySelector(".assist-range-start"),
      endEl: wrap.querySelector(".assist-range-end"),
    };
  }

  function assistLineOffsetInContainer(lineEl, container) {
    if (!lineEl || !container) return 0;
    const lr = lineEl.getBoundingClientRect();
    const cr = container.getBoundingClientRect();
    return lr.top - cr.top + container.scrollTop;
  }

  function applyAssistPreviewLayout(wrap, focus) {
    const container = assistScrollContainer(wrap);
    if (!container) return;
    const { startEl, endEl } = getAssistLayoutAnchors(wrap);
    if (!startEl) return;

    const h = container.clientHeight;
    if (h <= 0) return;

    const oneThird = h / 3;
    const twoThird = (h * 2) / 3;
    const startTop = assistLineOffsetInContainer(startEl, container);
    const maxScroll = Math.max(0, container.scrollHeight - h);
    let scrollTop;

    if (focus === "end" && endEl) {
      // 终点行底边 = 高亮/非高亮分界，对齐预览区 2/3 处
      const endBoundary =
        assistLineOffsetInContainer(endEl, container) + endEl.offsetHeight;
      scrollTop = endBoundary - twoThird;
    } else {
      // 起点行顶边 = 非高亮/高亮分界，对齐预览区 1/3 处
      scrollTop = startTop - oneThird;
    }

    container.scrollTop = Math.max(0, Math.min(scrollTop, maxScroll));
  }

  function queueAssistPreviewScroll(wrap) {
    if (!wrap) return;
    requestAnimationFrame(() =>
      applyAssistPreviewLayout(wrap, state.assistScrollFocus)
    );
  }

  function assistLineClass(n, start, end) {
    let cls = "m0-line";
    if (n >= start && n <= end) cls += " assist-in-range";
    if (n === start) cls += " assist-range-start";
    if (n === end && end !== start) cls += " assist-range-end";
    if (n === start && end === start) cls += " assist-range-end";
    return cls;
  }

  function createAssistLineEl(n, start, end) {
    const line = state.doc.lines[n - 1] ?? "";
    const el = document.createElement("div");
    el.className = assistLineClass(n, start, end);
    el.dataset.line = String(n);
    el.innerHTML = `<span class="m0-lineno">${n}</span><span class="m0-line-content">${esc(line)}</span>`;
    return el;
  }

  function updateAssistSourceHighlights(wrap, start, end) {
    wrap.querySelectorAll("#assist-preview-scroll .m0-line").forEach((el) => {
      const n = +el.dataset.line;
      el.className = assistLineClass(n, start, end);
    });
  }

  function updateAssistEllipsis(wrap, viewStart, viewEnd, total) {
    const top = wrap.querySelector(".m0-assist-preview-ellipsis-top");
    const bottom = wrap.querySelector(".m0-assist-preview-ellipsis-bottom");
    if (viewStart > 1) {
      const text = `… 上文第 1–${viewStart - 1} 行`;
      if (top) top.textContent = text;
      else {
        const el = document.createElement("div");
        el.className = "m0-assist-preview-ellipsis m0-assist-preview-ellipsis-top m0-muted";
        el.textContent = text;
        wrap.insertBefore(el, wrap.querySelector("#assist-preview-scroll"));
      }
    } else if (top) {
      top.remove();
    }
    if (viewEnd < total) {
      const text = `… 下文第 ${viewEnd + 1}–${total} 行`;
      if (bottom) bottom.textContent = text;
      else {
        const el = document.createElement("div");
        el.className = "m0-assist-preview-ellipsis m0-assist-preview-ellipsis-bottom m0-muted";
        el.textContent = text;
        wrap.appendChild(el);
      }
    } else if (bottom) {
      bottom.remove();
    }
  }

  function patchAssistSourcePreview(wrap, start, end, total, viewStart, viewEnd, last) {
    const scroll = wrap.querySelector("#assist-preview-scroll");
    if (!scroll || last.mode !== "source") return false;

    if (last.viewStart === viewStart && last.viewEnd === viewEnd) {
      updateAssistSourceHighlights(wrap, start, end);
      return true;
    }

    if (last.viewStart === viewStart && viewEnd > last.viewEnd) {
      for (let n = last.viewEnd + 1; n <= viewEnd; n++) {
        scroll.appendChild(createAssistLineEl(n, start, end));
      }
      updateAssistEllipsis(wrap, viewStart, viewEnd, total);
      updateAssistSourceHighlights(wrap, start, end);
      return true;
    }

    if (last.viewStart === viewStart && viewEnd < last.viewEnd) {
      scroll.querySelectorAll(".m0-line").forEach((el) => {
        if (+el.dataset.line > viewEnd) el.remove();
      });
      updateAssistEllipsis(wrap, viewStart, viewEnd, total);
      updateAssistSourceHighlights(wrap, start, end);
      return true;
    }

    if (last.viewEnd === viewEnd && viewStart < last.viewStart) {
      const frag = document.createDocumentFragment();
      for (let n = viewStart; n < last.viewStart; n++) {
        frag.appendChild(createAssistLineEl(n, start, end));
      }
      scroll.insertBefore(frag, scroll.firstChild);
      updateAssistEllipsis(wrap, viewStart, viewEnd, total);
      updateAssistSourceHighlights(wrap, start, end);
      return true;
    }

    if (last.viewEnd === viewEnd && viewStart > last.viewStart) {
      scroll.querySelectorAll(".m0-line").forEach((el) => {
        if (+el.dataset.line < viewStart) el.remove();
      });
      updateAssistEllipsis(wrap, viewStart, viewEnd, total);
      updateAssistSourceHighlights(wrap, start, end);
      return true;
    }

    return false;
  }

  function scheduleAssistPreview(focus) {
    setAssistScrollFocus(focus);
    clearTimeout(state.assistPreviewTimer);
    const delay = state.assistPreviewMode === "markdown" ? 280 : 120;
    state.assistPreviewTimer = setTimeout(() => renderAssistPreview(), delay);
  }

  function renderAssistSourcePreview(wrap, start, end, total, viewStart, viewEnd, opts = {}) {
    let html = assistPreviewToolbarHtml();

    if (viewStart > 1) {
      html += `<div class="m0-assist-preview-ellipsis m0-assist-preview-ellipsis-top m0-muted">… 上文第 1–${viewStart - 1} 行</div>`;
    }

    html += '<div class="m0-assist-preview" id="assist-preview-scroll">';
    for (let n = viewStart; n <= viewEnd; n++) {
      const line = state.doc.lines[n - 1] ?? "";
      html += `<div class="${assistLineClass(n, start, end)}" data-line="${n}">
        <span class="m0-lineno">${n}</span>
        <span class="m0-line-content">${esc(line)}</span>
      </div>`;
    }
    html += "</div>";

    if (viewEnd < total) {
      html += `<div class="m0-assist-preview-ellipsis m0-assist-preview-ellipsis-bottom m0-muted">… 下文第 ${viewEnd + 1}–${total} 行</div>`;
    }

    wrap.innerHTML = html;
    bindAssistPreviewToolbar(wrap);
  }

  async function renderAssistMarkdownPreview(wrap, start, end, total, viewStart, viewEnd, opts = {}) {
    let html = assistPreviewToolbarHtml();

    if (viewStart > 1) {
      html += `<div class="m0-assist-preview-ellipsis m0-assist-preview-ellipsis-top m0-muted">… 上文第 1–${viewStart - 1} 行</div>`;
    }

    html += '<div class="m0-assist-md m0-preview markdown-body" id="assist-md-scroll">';
    const lines = state.doc.lines;

    if (viewStart < start) {
      const chunk = lines.slice(viewStart - 1, start - 1).join("\n");
      html += `<div class="m0-assist-md-part">${MemoriaMarkdownPreview.renderHtml(chunk)}</div>`;
    }

    const rangeChunk = lines.slice(start - 1, end).join("\n");
    html += `<div class="m0-assist-md-part assist-md-range" id="assist-md-range">`;
    html += MemoriaMarkdownPreview.renderHtml(rangeChunk);
    html += '<div id="assist-md-range-end" class="assist-md-anchor" aria-hidden="true"></div>';
    html += "</div>";

    if (end < viewEnd) {
      const chunk = lines.slice(end, viewEnd).join("\n");
      html += `<div class="m0-assist-md-part">${MemoriaMarkdownPreview.renderHtml(chunk)}</div>`;
    }

    html += "</div>";

    if (viewEnd < total) {
      html += `<div class="m0-assist-preview-ellipsis m0-assist-preview-ellipsis-bottom m0-muted">… 下文第 ${viewEnd + 1}–${total} 行</div>`;
    }

    wrap.innerHTML = html;
    bindAssistPreviewToolbar(wrap);

    const mdRoot = wrap.querySelector(".m0-assist-md");
    if (mdRoot && window.MemoriaMarkdownPreview?.initMathJax) {
      try {
        await MemoriaMarkdownPreview.initMathJax();
        if (window.MathJax?.typesetClear) {
          window.MathJax.typesetClear([mdRoot]);
        }
        if (window.MathJax?.typesetPromise) {
          await window.MathJax.typesetPromise([mdRoot]);
        }
      } catch (e) {
        console.warn("assist markdown typeset:", e);
      }
    }
  }

  async function renderAssistPreview(opts) {
    if (!state.doc) return;
    const wrap = getAssistPreviewWrapEl();
    if (!wrap) return;

    const { start, end, total, valid } = getAssistRangeInputs();
    if (!valid) {
      state.assistLastView = null;
      wrap.innerHTML =
        assistPreviewToolbarHtml() +
        '<p class="m0-assist-preview-error">行号无效：终点不能早于起点</p>';
      bindAssistPreviewToolbar(wrap);
      return;
    }

    const { viewStart, viewEnd } = getAssistViewWindow(start, end, total);
    const mode = state.assistPreviewMode || "source";
    const last = state.assistLastView;

    if (
      last &&
      !opts?.forceScroll &&
      patchAssistSourcePreview(wrap, start, end, total, viewStart, viewEnd, last)
    ) {
      state.assistLastView = { mode, viewStart, viewEnd, start, end };
      queueAssistPreviewScroll(wrap);
      return;
    }

    if (mode === "markdown" && window.MemoriaMarkdownPreview) {
      await renderAssistMarkdownPreview(
        wrap,
        start,
        end,
        total,
        viewStart,
        viewEnd,
        opts
      );
    } else {
      renderAssistSourcePreview(
        wrap,
        start,
        end,
        total,
        viewStart,
        viewEnd,
        opts
      );
    }
    state.assistLastView = { mode, viewStart, viewEnd, start, end };
    queueAssistPreviewScroll(wrap);
  }

  function restoreKpModalSize() {
    const box = $("#kp-modal-box");
    if (!box) return;
    try {
      const raw = localStorage.getItem("m0-kp-modal-size");
      if (!raw) return;
      const { w, h } = JSON.parse(raw);
      if (w >= 420) box.style.width = `${w}px`;
      if (h >= 360) box.style.height = `${h}px`;
    } catch (_) {
      /* ignore */
    }
  }

  function setupKpModalResize() {
    const box = $("#kp-modal-box");
    if (!box || box.dataset.resizeBound) return;
    box.dataset.resizeBound = "1";
    restoreKpModalSize();

    let saveTimer = null;
    const onResize = () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        localStorage.setItem(
          "m0-kp-modal-size",
          JSON.stringify({ w: box.offsetWidth, h: box.offsetHeight })
        );
      }, 200);
      const wrap = getAssistPreviewWrapEl();
      if (wrap && !$("#kp-modal").classList.contains("hidden")) {
        applyAssistPreviewLayout(wrap, state.assistScrollFocus);
      }
    };

    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(onResize);
      ro.observe(box);
    }
  }

  function renderCandidates(which, indices) {
    const lines = state.doc.lines;
    const group = rangeRadioGroup(which);
    return indices
      .map((i) => {
        const n = i + 1;
        const text = (lines[i] || "").trim().slice(0, 72);
        return `<div class="candidate-row">
          <input type="radio" name="${group}" value="${n}" id="c-${group}-${n}">
          <label for="c-${group}-${n}" class="candidate-line"><span class="m0-muted">L${n}</span> ${esc(text)}</label>
        </div>`;
      })
      .join("");
  }

  function parseTagsInput(raw) {
    return [
      ...new Set(
        String(raw || "")
          .split(/[,，、;；]/)
          .map((t) => t.trim())
          .filter(Boolean)
      ),
    ];
  }

  async function reloadDocAfterKpChange(res, kpId, message) {
    if (res.status !== "ok") {
      setStatusError(res.message || "保存失败");
      return false;
    }
    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    renderFileTree();
    await setViewMode(state.viewMode, { skipSave: true });
    await renderPreview(res);
    onKpClick(kpId, { skipRangeModal: true });
    setStatus(message);
    return true;
  }

  async function saveKpIdentity() {
    const panel = state.kpPanel;
    if (!panel || !state.currentPath) return false;
    const oldId = panel.kpId;
    const newId = $("#kp-field-id")?.value?.trim() || oldId;
    const name = $("#kp-field-name")?.value?.trim();
    if (!name) {
      setStatusError("保存失败", "名称不能为空");
      return false;
    }
    if (newId !== oldId) {
      if (
        !window.confirm(
          `将知识点 id「${oldId}」重命名为「${newId}」？\n全库链接配置与正文 [[…]] 将同步更新，显示文字不变。`
        )
      ) {
        return false;
      }
      setStatus("迁移 id…");
      const renameRes = await call("rename_kp_id", oldId, newId);
      if (renameRes.status !== "ok") {
        setStatusError(renameRes.message || "id 迁移失败");
        return false;
      }
      panel.kpId = newId;
      if (state.activeKpId === oldId) state.activeKpId = newId;
      await refreshFiles();
      await loadLinkTargets();
      await loadGraphData();
      applyGraphGroupLayout({ relayout: true });
      if (state.currentPath) {
        const docRes = await call("load_document", state.currentPath);
        if (docRes.status === "ok") state.doc = docRes;
      }
      const stats = renameRes.sidecar_files?.length
        ? `${renameRes.sidecar_files.length} 个文件配置 · ${renameRes.md_replacements || 0} 处正文`
        : "";
      setStatus(`id 已迁移 ${oldId} → ${newId}`, stats);
    }
    setStatus("保存配置…");
    const res = await call("update_kp", state.currentPath, panel.kpId, name);
    return reloadDocAfterKpChange(res, panel.kpId, `已更新 ${panel.kpId}`);
  }

  async function saveKpTags() {
    const panel = state.kpPanel;
    if (!panel || !state.currentPath) return false;
    syncKpPanelFromForm();
    const tags = Array.isArray(panel.draft?.tags)
      ? panel.draft.tags
      : panel.draft?.tagState?.selected || [];
    const description = ($("#kp-desc-input")?.value || "").trim();
    const tagCandidates = serializeKpTagCandidates(panel.draft?.tagState?.candidates || []);
    const aliases = panel.draft?.aliasState?.selected || panel.draft?.aliases || [];
    const aliasCandidates = serializeKpAliasCandidates(
      panel.draft?.aliasState?.candidates || []
    );
    const descriptionCandidates = serializeKpDescCandidates(
      panel.draft?.descCandState?.candidates || []
    );
    setStatus("保存配置…");
    const res = await call(
      "update_kp",
      state.currentPath,
      panel.kpId,
      null,
      tags,
      description,
      tagCandidates,
      aliasCandidates,
      aliases,
      descriptionCandidates
    );
    return reloadDocAfterKpChange(res, panel.kpId, `已更新标签 · ${panel.kpId}`);
  }

  async function saveKpModal() {
    const panel = state.kpPanel;
    syncKpPanelFromForm();
    if (panel?.mode === "create") {
      const ok = await saveKpRange();
      if (ok) closeKpModal();
      return;
    }
    const tab = panel?.tab || "range";
    let ok = false;
    if (tab === "range") ok = await saveKpRange();
    else if (tab === "identity") ok = await saveKpIdentity();
    else if (tab === "edges") { closeKpModal(); return; }
    else ok = await saveKpTags();
    if (ok) closeKpModal();
  }

  async function deleteKp(kpId, opts = {}) {
    if (!kpId || !state.currentPath) return;
    const kp = (state.doc?.knowledge_points || []).find((k) => k.id === kpId);
    const label = kp?.name || kpId;
    if (
      !window.confirm(
        `删除知识点「${label}」？\n配置中的条目将移除；正文不会被改写。`
      )
    ) {
      return;
    }
    setStatus("删除中…");
    const res = await call("delete_kp", state.currentPath, kpId);
    if (res.status !== "ok") {
      setStatus(res.message || "删除失败");
      return;
    }
    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    renderFileTree();
    setViewMode(state.viewMode, { skipSave: true });
    renderPreview(res);
    setStatus("已删除知识点", kpId);
    if (opts.closeModal && state.kpPanel?.kpId === kpId) {
      closeKpModal();
    }
    if (opts.refreshConfig && !$("#config-modal").classList.contains("hidden")) {
      renderConfigModal();
    }
  }

  async function deleteKpFromModal() {
    const panel = state.kpPanel;
    if (!panel) return;
    await deleteKp(panel.kpId, { closeModal: true });
  }

  async function saveKpCreateMetadata(kpId) {
    const panel = state.kpPanel;
    if (!panel || !state.currentPath || !kpId) return;
    syncKpPanelFromForm();
    const description = (panel.draft?.description ?? $("#kp-desc-input")?.value ?? "").trim();
    if (!description) return;
    const res = await call("update_kp", state.currentPath, kpId, null, null, description);
    if (res.status === "ok") {
      state.doc = res;
      renderEditor(res);
      renderKpList(res);
      renderFileTree();
      setViewMode(state.viewMode, { skipSave: true });
      renderPreview(res);
    }
  }

  async function saveKpRange() {
    if (!state.currentPath) return false;
    const panel = state.kpPanel;
    let a = state.assist;
    if (!a && panel?.mode === "create") {
      syncKpPanelFromForm();
      a = {
        host: "kp",
        mode: "create",
        kpId: panel.kpId || "",
        name: panel.name || "",
        startLine: panel.startLine || 1,
        endLine: panel.endLine || panel.startLine || 1,
        error: null,
        startCandidates: [],
        endCandidates: [],
        returnTo: panel.returnTo || null,
      };
      state.assist = a;
    }
    if (!a) return false;
    const { start, end, total, valid } = getAssistRangeInputs();
    if (!valid) {
      setStatusError("行号无效", "终点不能早于起点");
      return false;
    }
    if (end > total) {
      setStatusError(
        "行号无效",
        `终点第 ${end} 行超出正文（共 ${total} 行）；请使用编辑器行号，不是含 frontmatter 的文件行号`
      );
      return false;
    }
    if (!lineHasRangeSnippet(start)) {
      setStatusError("无法保存", `起点第 ${start} 行为空，请选择有内容的行`);
      return false;
    }
    if (!lineHasRangeSnippet(end)) {
      setStatusError("无法保存", `终点第 ${end} 行为空，请选择有内容的行`);
      return false;
    }
    const host = a.host;
    const returnTo = a.returnTo;
    let kpId = a.kpId;
    let kpName = a.name;

    if (a.mode === "create") {
      syncKpPanelFromForm();
      kpId = (state.kpPanel?.kpId || "").trim();
      kpName = (state.kpPanel?.name || "").trim();
      a.kpId = kpId;
      a.name = kpName;
      if (!kpId) {
        setStatusError("保存失败", "id 不能为空");
        return false;
      }
      if (!kpName) {
        setStatusError("保存失败", "名称不能为空");
        return false;
      }
      try {
        const check = await call("check_kp_id", kpId, state.currentPath);
        if (check.status !== "ok" || !check.available) {
          setStatusError(check.message || "目标 id 已存在", check.files?.join(", "));
          return false;
        }
      } catch (e) {
        setStatusError("校验失败", String(e.message || e));
        return false;
      }
    }

    setStatus("保存配置…");
    const res = await call(
      "confirm_kp_range",
      state.currentPath,
      kpId,
      kpName,
      start,
      end
    );
    if (res.status !== "ok") {
      setStatusError(res.message || "写入失败");
      if (host === "kp" && state.kpPanel?.kpId) {
        ensureKpRangeAssist(
          (state.doc.knowledge_points || []).find((k) => k.id === state.kpPanel.kpId) || {
            id: kpId,
            name: kpName,
            range_resolved: {},
          }
        );
      }
      return false;
    }

    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    renderFileTree();
    await setViewMode(state.viewMode, { skipSave: true });
    await renderPreview(res);
    // 与 openFile 的 kpId 跳转路径一致：直接 highlightRange + scrollKpListItemIntoView
    state.activeKpId = kpId;
    renderKpList(state.doc);
    highlightRange(start, end);
    scrollKpListItemIntoView(kpId);
    const created = a.mode === "create";
    setStatus(created ? "已创建知识点" : "已更新 range", `${kpId} L${start}–${end}`);
    if (created) {
      try {
        await saveKpCreateMetadata(kpId);
      } catch (_) {
        /* optional */
      }
    }
    try {
      await loadGraphData();
      applyGraphGroupLayout({ relayout: true });
    } catch (_) {
      /* optional */
    }

    if (host === "kp") {
      return true;
    }
    if (returnTo === "config") {
      openConfigModal({ tab: "kp" });
    }
    return true;
  }

  function setupSidebarResize() {
    const sidebar = $("#m0-sidebar");
    const resizer = $("#sidebar-resizer");
    let dragging = false;
    resizer.addEventListener("mousedown", (e) => {
      dragging = true;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const w = Math.max(180, Math.min(480, e.clientX));
      sidebar.style.width = w + "px";
    });
    window.addEventListener("mouseup", () => {
      dragging = false;
    });
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function basename(p) {
    const parts = p.replace(/\\/g, "/").split("/");
    return parts[parts.length - 1];
  }

  function normRelPath(p) {
    return String(p || "").replace(/\\/g, "/");
  }

  function slugify(name) {
    return name
      .toLowerCase()
      .replace(/[^\w\u4e00-\u9fff]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 40) || "kp";
  }

  function focusToolbarSearch() {
    const input = $("#toolbar-search");
    if (!input) return;
    input.focus();
    input.select();
  }

  function hideToolbarSearchPanel() {
    $("#toolbar-search-panel")?.classList.add("hidden");
  }

  function showToolbarSearchPanel(html) {
    const panel = $("#toolbar-search-panel");
    if (!panel) return;
    panel.innerHTML = html;
    panel.classList.remove("hidden");
  }

  function syncToolbarSearchScopeUI() {
    const scope = state.toolbarSearchScope === "file" ? "file" : "kb";
    $("#toolbar-search-scope-kb")?.classList.toggle("active", scope === "kb");
    $("#toolbar-search-scope-file")?.classList.toggle("active", scope === "file");
    const fileBtn = $("#toolbar-search-scope-file");
    if (fileBtn) {
      fileBtn.disabled = !state.currentPath;
      fileBtn.title = state.currentPath
        ? `仅搜索 ${basename(state.currentPath)}`
        : "请先打开文件";
    }
    const scopeSwitch = $("#toolbar-search-scope");
    if (scopeSwitch) {
      scopeSwitch.setAttribute("aria-checked", scope === "file" ? "true" : "false");
      scopeSwitch.title =
        scope === "file"
          ? fileBtn?.title || "仅当前文件（点击切换全库）"
          : "搜索全库（点击切换文件）";
    }
  }

  function toggleToolbarSearchScope() {
    const cur = state.toolbarSearchScope === "file" ? "file" : "kb";
    setToolbarSearchScope(cur === "file" ? "kb" : "file");
  }

  function setToolbarSearchScope(scope) {
    if (scope === "file" && !state.currentPath) {
      setStatusError("请先打开文件");
      return;
    }
    state.toolbarSearchScope = scope === "file" ? "file" : "kb";
    localStorage.setItem("m0-search-scope", state.toolbarSearchScope);
    syncToolbarSearchScopeUI();
    const q = $("#toolbar-search")?.value?.trim();
    if (q) runToolbarSearch();
  }

  let toolbarSearchTimer = null;

  function formatSearchHitScore(hit, modes) {
    const mode = (modes || "lexical").toLowerCase();
    const sem =
      hit.semantic_score != null
        ? hit.semantic_score
        : hit.confidence != null
          ? hit.confidence
          : null;
    const lex = hit.lexical_score != null ? hit.lexical_score : null;

    if (mode === "semantic" && sem != null) {
      return `语义 ${Math.round(sem)}%`;
    }
    if (mode === "both" || mode === "full") {
      const parts = [];
      if (lex != null && lex > 0) parts.push(`字 ${Math.round(lex)}`);
      if (sem != null && sem > 0) parts.push(`语义 ${Math.round(sem)}%`);
      if (hit.tier) {
        const tierLabel = { high: "高", medium: "中", low: "低" }[hit.tier] || hit.tier;
        parts.push(tierLabel);
      }
      if (parts.length) return parts.join(" · ");
    }
    if (hit.tier && mode === "lexical") {
      const tierLabel = { high: "高", medium: "中", low: "低" }[hit.tier] || hit.tier;
      return `字 ${Math.round(lex != null ? lex : hit.score || 0)} · ${tierLabel}`;
    }
    if (lex != null) return `字 ${Math.round(lex)}`;
    return String(Math.round(hit.score || 0));
  }

  async function runToolbarSearch(opts = {}) {
    if (!state.kbPath) {
      setStatusError("请先打开知识库");
      return;
    }
    const q = $("#toolbar-search")?.value?.trim() || "";
    if (!q) {
      hideToolbarSearchPanel();
      return;
    }
    const shiftFile = !!opts.fileOnly && !!state.currentPath;
    const scope =
      shiftFile || state.toolbarSearchScope === "file" ? "file" : "kb";
    if (scope === "file" && !state.currentPath) {
      setStatusError("请先打开文件");
      return;
    }
    const relPath = scope === "file" ? state.currentPath : "";
    const scopeHint = scope === "file" ? ` · ${basename(state.currentPath)}` : "";
    setStatus("搜索…", q + scopeHint);
    try {
      const modesRequested = window.MemoriaSearchSettings?.getSearchModes?.() || "lexical";
      const res = await call("search", q, scope, 20, modesRequested, relPath);
      if (res.status === "error") {
        hideToolbarSearchPanel();
        setStatusError("搜索失败", res.message || "");
        return;
      }
      const items = res.results || [];
      const bodyHits = res.body_locate || [];
      state.toolbarSearchResults = items;
      state.toolbarSearchBodyHits = bodyHits;
      const modes = res.modes || modesRequested;
      if (!items.length && !bodyHits.length) {
        let hint = `无匹配 · ${esc(q)}`;
        if (
          modes !== "lexical" &&
          res.semantic?.available === false &&
          res.semantic?.reason
        ) {
          const reasonMap = {
            embedding_not_enabled: "语义搜索未开启（设置 → 检索）",
            embedding_not_installed: "未安装 sentence-transformers",
            embedding_index_empty: "语义索引为空",
          };
          hint += ` · ${reasonMap[res.semantic.reason] || res.semantic.reason}`;
        }
        if (!window.MemoriaSearchSettings?.isBodyLocateEnabled?.()) {
          hint += " · 可在设置→检索开启「搜索正文定位」";
        }
        showToolbarSearchPanel(`<div class="m0-search-placeholder">${hint}</div>`);
      } else {
        let html = "";
        if (items.length) {
          html += items
            .map(
              (it, i) =>
                `<button type="button" class="m0-suggest-item m0-toolbar-search-hit" data-search-kind="kp" data-search-idx="${i}">
                  <span class="m0-suggest-score" title="${esc((it.sources || []).join(", "))}">${esc(formatSearchHitScore(it, modes))}</span>
                  <span class="m0-suggest-label">${esc(it.label || it.name || it.id || "")}</span>
                  <span class="m0-muted m0-toolbar-search-file">${esc(basename(it.file || ""))}</span>
                </button>`
            )
            .join("");
        }
        if (bodyHits.length) {
          if (items.length) {
            html += `<div class="m0-search-section-label">正文定位</div>`;
          }
          html += bodyHits
            .map(
              (it, i) =>
                `<button type="button" class="m0-suggest-item m0-toolbar-search-hit m0-toolbar-search-body" data-search-kind="body" data-body-idx="${i}">
                  <span class="m0-suggest-score m0-suggest-score--muted" title="正文行匹配">L${esc(String(it.line || ""))}</span>
                  <span class="m0-suggest-label">${esc(it.label || it.snippet || "")}</span>
                  <span class="m0-muted m0-toolbar-search-file">${esc(basename(it.file || ""))}</span>
                </button>`
            )
            .join("");
        }
        showToolbarSearchPanel(html);
        $("#toolbar-search-panel")
          ?.querySelectorAll(".m0-toolbar-search-hit")
          .forEach((btn) => {
            btn.addEventListener("click", async () => {
              const kind = btn.getAttribute("data-search-kind") || "kp";
              if (kind === "body") {
                const idx = parseInt(btn.getAttribute("data-body-idx") || "-1", 10);
                const hit = state.toolbarSearchBodyHits[idx];
                if (!hit?.file) return;
                hideToolbarSearchPanel();
                await openFile(hit.file, { lineHint: hit.line });
                return;
              }
              const idx = parseInt(btn.getAttribute("data-search-idx") || "-1", 10);
              const hit = state.toolbarSearchResults[idx];
              if (!hit?.file) return;
              hideToolbarSearchPanel();
              await openFile(hit.file, { kpId: hit.kp_id || null });
            });
          });
      }
      const total = items.length + bodyHits.length;
      setStatus("搜索完成", `${total} 条 · ${q}${scopeHint}`);
    } catch (e) {
      hideToolbarSearchPanel();
      setStatusError("搜索失败", String(e.message || e));
    }
  }

  function bindPointerDragHoverGuard() {
    if (document.body.dataset.m0HoverDragGuard) return;
    document.body.dataset.m0HoverDragGuard = "1";
    document.addEventListener(
      "pointerdown",
      (e) => {
        if (e.button !== 0) return;
        if (e.target.closest(".m0-kp-item")) return;
        if (e.target.closest(".m0-link-match-row")) return;
        clearKpHoverHighlight();
        clearGraphKpHover();
        dismissKpRangeHighlight();
      },
      true
    );
  }

  function bindEvents() {
    bindPointerDragHoverGuard();
    $("#btn-open").addEventListener("click", openKb);
    $("#btn-import").addEventListener("click", () => startImport());
    $("#btn-kb-close").addEventListener("click", () => closeKb());
    $("#btn-welcome-open").addEventListener("click", openKb);
    $("#btn-nav-back").addEventListener("click", navBack);
    $("#btn-nav-forward").addEventListener("click", navForward);
    $("#btn-refresh").addEventListener("click", async () => {
      await refreshFiles();
      await loadLinkTargets();
      await loadGraphData();
      if (state.currentPath) await openFile(state.currentPath, { skipNav: true });
    });
    $("#btn-build").addEventListener("click", () => buildKb());
    $("#btn-check").addEventListener("click", () => openCheckModal());
    $("#toolbar-search")?.addEventListener("input", () => {
      clearTimeout(toolbarSearchTimer);
      toolbarSearchTimer = setTimeout(() => {
        const q = $("#toolbar-search")?.value?.trim();
        if (q) runToolbarSearch();
        else hideToolbarSearchPanel();
      }, 220);
    });
    $("#toolbar-search-scope")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleToolbarSearchScope();
    });
    $("#toolbar-search-scope")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleToolbarSearchScope();
      }
    });
    syncToolbarSearchScopeUI();
    $("#toolbar-search")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runToolbarSearch({ fileOnly: e.shiftKey });
      } else if (e.key === "Escape") {
        hideToolbarSearchPanel();
        e.target.blur();
      }
    });
    $("#toolbar-search")?.addEventListener("focus", () => {
      const q = $("#toolbar-search")?.value?.trim();
      if (q) runToolbarSearch();
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".toolbar-search-wrap")) hideToolbarSearchPanel();
    });
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        focusToolbarSearch();
      }
    });
    $("#check-close").addEventListener("click", closeCheckModal);
    $("#check-dismiss").addEventListener("click", closeCheckModal);
    $("#check-rerun").addEventListener("click", () => runKbValidate({ silent: false }));
    $("#check-modal .m0-modal-backdrop")?.addEventListener("click", closeCheckModal);
    $("#status-stats")?.addEventListener("click", async () => {
      if ($("#status-stats").dataset.kbCheck) {
        openCheckModal();
        return;
      }
      if (!$("#status-stats").dataset.graphAuditGoto) return;
      const issue = firstGraphAuditWarn();
      if (issue) await gotoGraphAuditIssue(issue);
    });
    $("#graph-2d-hint")?.addEventListener("click", async (e) => {
      if (!e.target.closest(".m0-graph-audit-goto")) return;
      const issue = firstGraphAuditWarn();
      if (issue) await gotoGraphAuditIssue(issue);
    });
    $("#graph-3d-hint")?.addEventListener("click", async (e) => {
      if (!e.target.closest(".m0-graph-audit-goto")) return;
      const issue = firstGraphAuditWarn();
      if (issue) await gotoGraphAuditIssue(issue);
    });
    $("#btn-config").addEventListener("click", () => openConfigModal({ tab: "kp" }));
    $("#btn-kp-new").addEventListener("click", () => {
      if (!state.currentPath || !state.doc) {
        setStatusError("请先打开文件");
        return;
      }
      openKpModalForCreate();
    });
    window.MemoriaKpActions = {
      locate: (kpId) => onKpClick(kpId),
      configure: (kpId) => {
        const kp = (state.doc?.knowledge_points || []).find((k) => k.id === kpId);
        if (!kp) return;
        state.activeKpId = kpId;
        renderKpList(state.doc);
        openKpModal(kpId);
      },
    };
    $("#kp-close").addEventListener("click", closeKpModal);
    $("#kp-cancel").addEventListener("click", closeKpModal);
    $("#kp-modal .m0-modal-backdrop").addEventListener("click", closeKpModal);
    $("#kp-delete").addEventListener("click", () => deleteKpFromModal());
    $("#kp-save").addEventListener("click", () => saveKpModal());
    $("#config-close").addEventListener("click", closeConfigModal);
    $("#config-close-btn").addEventListener("click", closeConfigModal);
    $("#config-modal .m0-modal-backdrop").addEventListener("click", closeConfigModal);
    $("#link-close").addEventListener("click", closeLinkModal);
    $("#link-cancel").addEventListener("click", closeLinkModal);
    $("#link-confirm").addEventListener("click", confirmLinkPicker);
    $("#import-conflict-close").addEventListener("click", closeImportConflictModal);
    $("#import-conflict-cancel").addEventListener("click", closeImportConflictModal);
    $("#import-conflict-modal .m0-modal-backdrop")?.addEventListener("click", closeImportConflictModal);
    $("#import-conflict-copy-report").addEventListener("click", () => {
      const ta = $("#import-conflict-report-text");
      if (ta) {
        ta.select();
        navigator.clipboard.writeText(ta.value).then(() => setStatus("冲突报告已复制")).catch(() => { document.execCommand("copy"); setStatus("冲突报告已复制"); });
      }
    });
    $("#import-conflict-confirm").addEventListener("click", async () => {
      const resolution = collectImportConflictResolution();
      const files = _importFileContents;
      closeImportConflictModal();
      if (files) await executeImportDirect(files, resolution);
    });
    $("#import-result-close").addEventListener("click", closeImportResultModal);
    $("#import-result-dismiss").addEventListener("click", closeImportResultModal);
    $("#import-result-modal .m0-modal-backdrop")?.addEventListener("click", closeImportResultModal);
    $("#link-save").addEventListener("click", () => saveLinkEditor(false));
    $("#link-save-jump").addEventListener("click", () => saveLinkEditor(true));
    $("#link-config-view").addEventListener("click", () => {
      const anchor =
        state.linkPicker?.configHighlight || state.linkPicker?.anchorText || null;
      const fromConfig = state.linkPicker?.returnTo === "config";
      closeLinkModal();
      if (!fromConfig) openConfigModal({ highlightLinkTarget: anchor, tab: "links" });
    });
    $("#config-body")?.addEventListener("click", (e) => {
      const m = state.configLinkMatch;
      if (e.target.id === "config-link-match-close" || e.target.id === "config-link-match-cancel") {
        closeConfigLinkMatch();
        return;
      }
      if (e.target.id === "config-link-match-confirm") {
        confirmConfigLinkMatch();
        return;
      }
      if (!m) return;
      if (
        e.target.id === "config-link-match-all" ||
        e.target.id === "config-link-match-plain"
      ) {
        applyLinkMatchToolbarAction(
          m,
          e.target.id.replace("config-link-match-", "")
        );
        refreshConfigLinkMatchPanel();
        return;
      }
      const rowEl = e.target.closest(".m0-link-match-row");
      if (rowEl && e.target.closest("#config-link-match-panel")) {
        const ln = +rowEl.dataset.matchLine;
        const match = m.matches.find((r) => r.line === ln);
        const locateOnly = rowEl.dataset.matchLocate === "1";
        const onCheckbox = !locateOnly && e.target.closest('input[type="checkbox"]');
        if (!onCheckbox && match && !locateOnly) {
          if (m.selected.has(ln)) m.selected.delete(ln);
          else m.selected.add(ln);
          refreshConfigLinkMatchPanel();
        }
        if (state.viewMode === "preview") {
          setViewMode("split", { skipSave: true });
        }
        highlightRange(ln, ln);
        scrollEditorToLine(ln);
        if (locateOnly) {
          setStatus(`已定位 L${ln}`, match?.is_substring ? "子串匹配，不可挂接" : "点击复选框可挂接");
        }
      }
    });
    $("#config-body")?.addEventListener("change", (e) => {
      if (e.target.closest("[data-search-opt]")) {
        readConfigLinkSearchOptions();
        if (state.configLinkMatch) {
          openLinkMatchInConfig({
            anchorText: state.configLinkMatch.anchorText,
            oldAnchorText: state.configLinkMatch.oldAnchorText,
            targetIds: state.configLinkMatch.targetIds,
            poolIds: state.configLinkMatch.poolIds,
            edgeType: state.configLinkMatch.edgeType,
            jumpAfter: state.configLinkMatch.jumpAfter,
            returnTo: state.configLinkMatch.returnTo,
            configHighlight: state.configLinkMatch.configHighlight,
            preselectLines: [...state.configLinkMatch.selected],
            searchOptions: state.configLinkMatch.searchOptions,
          });
        }
        return;
      }
      const m = state.configLinkMatch;
      const cb = e.target.closest("[data-match-check]");
      if (!m || !cb || !e.target.closest("#config-link-match-panel")) return;
      const ln = +cb.dataset.matchCheck;
      if (cb.checked) m.selected.add(ln);
      else m.selected.delete(ln);
      refreshConfigLinkMatchPanel();
    });
    $("#link-body")?.addEventListener("click", (e) => {
      const pick = e.target.closest("[data-anchor-pick]");
      if (pick) {
        e.preventDefault();
        applyAnchorSuggestion(pick.getAttribute("data-anchor-pick") || "");
        return;
      }
      const m = state.linkPicker?.match;
      if (!m || m.loading) return;
      if (
        e.target.id === "link-editor-match-all" ||
        e.target.id === "link-editor-match-plain"
      ) {
        applyLinkMatchToolbarAction(
          m,
          e.target.id.replace("link-editor-match-", "")
        );
        refreshLinkEditorMatchPanel();
        return;
      }
      const rowEl = e.target.closest(".m0-link-match-row");
      if (rowEl && e.target.closest("#link-editor-match-panel")) {
        const ln = +rowEl.dataset.matchLine;
        const match = m.matches.find((r) => r.line === ln);
        const locateOnly = rowEl.dataset.matchLocate === "1";
        const onCheckbox = !locateOnly && e.target.closest('input[type="checkbox"]');
        if (!onCheckbox && match && !locateOnly) {
          if (m.selected.has(ln)) m.selected.delete(ln);
          else m.selected.add(ln);
          refreshLinkEditorMatchPanel();
        }
        if (state.viewMode === "preview") {
          setViewMode("split", { skipSave: true });
        }
        highlightRange(ln, ln);
        scrollEditorToLine(ln);
        if (locateOnly) {
          setStatus(`已定位 L${ln}`, match?.is_substring ? "子串匹配，不可挂接" : "");
        }
      }
    });
    $("#link-body")?.addEventListener("change", (e) => {
      if (e.target.closest("[data-search-opt]")) {
        readEditorLinkSearchOptions();
        loadLinkEditorMatch();
        return;
      }
      const m = state.linkPicker?.match;
      const cb = e.target.closest("[data-match-check]");
      if (!m || !cb || !e.target.closest("#link-editor-match-panel")) return;
      const ln = +cb.dataset.matchCheck;
      if (cb.checked) m.selected.add(ln);
      else m.selected.delete(ln);
      refreshLinkEditorMatchPanel();
    });
    $("#link-modal .m0-modal-backdrop").addEventListener("click", closeLinkModal);
    document.addEventListener("keydown", (e) => {
      if (e.altKey && e.key === "ArrowLeft") {
        e.preventDefault();
        navBack();
      } else if (e.altKey && e.key === "ArrowRight") {
        e.preventDefault();
        navForward();
      }
    });
    document.querySelectorAll(".m0-view-btn").forEach((btn) => {
      btn.addEventListener("click", () => setViewMode(btn.dataset.view));
    });
    // 分栏模式双向滚动同步
    setupSplitScrollSync();
    setupSidebarResize();
    setupKpModalResize();
    document.querySelectorAll("[data-sidebar-tab]").forEach((btn) => {
      btn.addEventListener("click", () => setSidebarTab(btn.dataset.sidebarTab));
    });
    initGraphPanel();
    if (window.MemoriaGraphSettings) {
      MemoriaGraphSettings.onChange(applyGraphViewSettings);
      MemoriaGraphSettings.bindModal();
      MemoriaGraphSettings.bindSidebarNavKpSplit(() => {
        state.graphView2d?.reflow?.();
        state.graphView3d?.reflow?.();
      });
    }
    if (window.MemoriaCheckSettings) {
      MemoriaCheckSettings.onChange(() => {
        if (state.kbPath) startKbSilentCheck();
      });
    }
    setSidebarTab(state.sidebarTab);
    bindEditorSelectInteraction();
    bindEditorSelectionMenu();
    bindEditorLinkHover();
    bindPreviewSelectInteraction();
    bindPreviewSelectionMenu();
    bindModalDrag();
  }

  /** 模态框标题栏拖拽：mousedown 在 header（排除交互元素）→ 移动整个 .m0-modal-box */
  function bindModalDrag() {
    const NO_DRAG =
      ".m0-icon-btn, button, input, textarea, select, a, [contenteditable], [data-no-drag]";
    let dragging = null;

    function readCurrentTranslate(box) {
      const t = (box.style.transform || "").match(/translate\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)px\s*\)/);
      if (!t) return { dx: 0, dy: 0 };
      return { dx: parseFloat(t[1]) || 0, dy: parseFloat(t[2]) || 0 };
    }

    document.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      const header = e.target.closest(".m0-modal-header");
      if (!header) return;
      if (e.target.closest(NO_DRAG)) return;
      const box = header.closest(".m0-modal-box");
      if (!box) return;
      const modal = box.closest(".m0-modal");
      if (!modal || modal.classList.contains("hidden")) return;
      e.preventDefault();
      const cur = readCurrentTranslate(box);
      dragging = {
        box,
        sx: e.clientX,
        sy: e.clientY,
        dx: cur.dx,
        dy: cur.dy,
      };
      box.style.cursor = "grabbing";
      document.body.style.userSelect = "none";
    });

    document.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      dragging.dx += e.clientX - dragging.sx;
      dragging.dy += e.clientY - dragging.sy;
      dragging.sx = e.clientX;
      dragging.sy = e.clientY;
      dragging.box.style.transform = `translate(${dragging.dx}px, ${dragging.dy}px)`;
    });

    const endDrag = () => {
      if (!dragging) return;
      dragging.box.style.cursor = "";
      document.body.style.userSelect = "";
      dragging = null;
    };
    document.addEventListener("mouseup", endDrag);
    document.addEventListener("mouseleave", endDrag);

    /** 模态框关闭时自动重置拖拽位移，下次打开回到居中位置 */
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.attributeName !== "class") continue;
        const modal = m.target;
        if (modal.classList.contains("hidden")) {
          const box = modal.querySelector(".m0-modal-box");
          if (box) box.style.transform = "";
        }
      }
    });
    document.querySelectorAll(".m0-modal").forEach((modal) => {
      observer.observe(modal, { attributes: true, attributeFilter: ["class"] });
    });
  }

  window.MemoriaBridge?.onReady?.(() => {
    bindEvents();
    initKb();
    window.MemoriaWindowChrome?.initWindowChrome?.();
  });

  window.MemoriaGraphShell = {
    getGraphGroupId() {
      return state.graphGroupId || window.MemoriaGraphGroups?.ALL_GROUP_ID || "all";
    },
  };
})();
