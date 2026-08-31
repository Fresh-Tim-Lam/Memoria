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
    viewMode: localStorage.getItem("-view") || "source",
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
    sidebarTab: localStorage.getItem("-sidebar-tab") || "files",
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
    graphGroupId: localStorage.getItem("-graph-group") || "all",
    kbValidateReport: null,
    toolbarSearchScope: localStorage.getItem("-search-scope") || "kb",
    toolbarSearchResults: [],
    kbPending: null,
    lastFileStats: "",
  };

  window.state = state;  // 导出给 edit-handler.js 等外部模块使用

  // 块编辑退出后刷新预览/写盘的钩子（edit-handler.js 依赖，原为未定义引用）
  function _scheduleRenderHook() {
    scheduleRenderSync();
  }
  function _markDirtyHook() {
    markDirty();
  }
  window._scheduleRender = _scheduleRenderHook;
  window._markDirty = _markDirtyHook;

  // ── Document sync (in-memory + disk) ──
  const RENDER_DEBOUNCE_MS = 80;   // 停止编辑 80ms 后同步预览（纯内存，接近零延迟）
  const SAVE_DEBOUNCE_MS  = 1500;  // 停止编辑 1.5s 后写盘
  let _renderTimer = null;  // 内存实时同步计时器
  let _saveTimer  = null;  // 磁盘保存计时器
  let _dirty = false;      // 是否有未写盘的编辑
  const _SYNC_LOG = true;  // 调试开关，设为 false 关闭日志

  function syncLog(...args) { if (_SYNC_LOG) console.log("[SYNC]", ...args); }

  /** 收集源码编辑器的当前内容（逐行拼接） */
  function collectEditorBody() {
    const editor = $("#editor");
    if (!editor) { syncLog("collectEditorBody: editor DOM 不存在"); return null; }
    const lines = [...editor.querySelectorAll(".-line-content")];
    if (!lines.length) { syncLog("collectEditorBody: 无 .-line-content 行"); return null; }
    const body = lines.map((el) => el.textContent ?? "").join("\n");
    syncLog("collectEditorBody: 收集到", lines.length, "行, 总长度", body.length);
    return body;
  }

  /** 源码→预览：实时重新渲染预览（内存，不写盘） */
  async function syncSourceToPreview() {
    syncLog("syncSourceToPreview: 开始");
    const body = collectEditorBody();
    if (body === null || !state.currentPath) {
      syncLog("syncSourceToPreview: 跳过 (body=", body, "path=", state.currentPath, ")");
      return;
    }
    state.doc.body = body;
    state.doc.lines = body.split("\n");
    state.doc.preview_body = null;
    syncLog("syncSourceToPreview: 调用 renderPreview, body 前50字:", body.substring(0, 50));
    await renderPreview(state.doc);
    syncLog("syncSourceToPreview: 完成");
  }

  /** 内存实时同步：源码编辑时更新预览 */
  function scheduleRenderSync() {
    clearTimeout(_renderTimer);
    syncLog("scheduleRenderSync: 将在", RENDER_DEBOUNCE_MS, "ms 后执行 syncSourceToPreview");
    _renderTimer = setTimeout(() => syncSourceToPreview(), RENDER_DEBOUNCE_MS);
  }

  /** 将当前内存内容写回磁盘（始终从源码编辑器收集，保证 markdown 格式完整） */
  async function syncToDisk() {
    syncLog("syncToDisk: dirty=", _dirty, "path=", state.currentPath);
    if (!state.currentPath || !_dirty) {
      syncLog("syncToDisk: 跳过 (无路径或无修改)");
      return;
    }
    const body = collectEditorBody();
    if (body === null) { syncLog("syncToDisk: body 为 null，跳过"); return; }
    _dirty = false;
    syncLog("syncToDisk: 写入文件", state.currentPath, ", body长度", body.length, ", 前80字:", body.substring(0, 80));
    try {
      const res = await call("save_document", state.currentPath, body);
      if (res.status !== "ok") {
        console.warn("[SYNC] 保存失败:", res.message);
      } else {
        syncLog("syncToDisk: 保存成功");
        if (res.cleanedImages && res.cleanedImages.length) {
          showFlashInfo(`已清理 ${res.cleanedImages.length} 张未使用图片：${res.cleanedImages.join("、")}`);
        }
      }
    } catch (e) {
      console.warn("[SYNC] 保存异常:", e);
    }
  }

  /** 标记文档为脏（有未保存编辑），启动写盘防抖计时器 */
  function markDirty() {
    syncLog("markDirty: _dirty", _dirty, "→ true, 将在", SAVE_DEBOUNCE_MS, "ms 后写盘");
    _dirty = true;
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => syncToDisk(), SAVE_DEBOUNCE_MS);
  }

  /** 立即写盘（如果脏），返回 Promise。用于文件切换前。 */
  async function flushSync() {
    syncLog("flushSync: dirty=", _dirty);
    clearTimeout(_saveTimer);
    clearTimeout(_renderTimer);
    await syncToDisk();
  }

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
      parts.push(`<span class="-stat-error">${err} 错误</span>`);
    }
    if (warn > 0) {
      parts.push(`<span class="-stat-warn">${warn} 警告</span>`);
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
    badge.classList.remove("-toolbar-badge--error", "-toolbar-badge--warn", "hidden");
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
      badge.classList.add("-toolbar-badge--error");
      badge.title = warn > 0 ? `${err} 错误 · ${warn} 警告` : `${err} 错误`;
    } else {
      badge.classList.add("-toolbar-badge--warn");
      badge.title = `${warn} 警告`;
    }
  }

  function renderStatusStats() {
    const el = $("#status-stats");
    if (!el) return;
    el.classList.remove("-status-clickable");
    delete el.dataset.graphAuditGoto;

    const chunks = [];
    const vr = state.kbValidateReport;
    if (vr && (vr.errors > 0 || vr.warnings > 0)) {
      chunks.push(formatKbCheckStatsHtml(vr));
      el.dataset.kbCheck = "1";
    } else {
      delete el.dataset.kbCheck;
      if (vr?.status === "ok" && state.kbPath && !state.lastFileStats) {
        chunks.push('<span class="-stat-ok">检查通过</span>');
      }
    }

    const gw = vr?.graph_audit?.summary?.warn_count;
    if (gw && !state.lastFileStats) {
      chunks.push(`<span class="-stat-warn">图谱 ${gw} 处待配置</span>`);
    }

    if (state.lastFileStats) {
      chunks.push(esc(state.lastFileStats));
    }

    const fileWarns = currentFileGraphAuditWarns();
    const kbWarns = collectKbGraphAuditWarns(state.graphAudit);
    if (fileWarns.length) {
      const first = fileWarns[0];
      chunks.push(
        `<span class="-stat-warn">图谱建边 ${fileWarns.length} 处 · ${esc(basename(first.file))} · 点击定位</span>`
      );
      el.classList.add("-status-clickable");
      el.dataset.graphAuditGoto = "1";
    } else if (kbWarns.length) {
      const first = kbWarns[0];
      const fileCount = new Set(kbWarns.map((w) => normRelPath(w.file))).size;
      chunks.push(
        `<span class="-stat-warn">图谱建边 ${kbWarns.length} 处 · ${esc(basename(first.file))}${fileCount > 1 ? ` 等 ${fileCount} 文件` : ""} · 点击打开</span>`
      );
      el.classList.add("-status-clickable");
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
    const host = $("#-flash-host");
    if (!host || !msg) return;
    const duration = opts.duration ?? 3800;
    const el = document.createElement("div");
    el.className = "-flash-error";
    el.innerHTML =
      `<div class="-flash-error-title">${esc(String(msg))}</div>` +
      (detail ? `<div class="-flash-error-detail">${esc(String(detail))}</div>` : "");
    host.appendChild(el);
    const fadeMs = 280;
    const fadeTimer = window.setTimeout(() => el.classList.add("-flash-leaving"), duration);
    const removeTimer = window.setTimeout(() => el.remove(), duration + fadeMs);
    el._FlashTimers = [fadeTimer, removeTimer];
  }

  function showFlashInfo(msg, opts = {}) {
    const host = $("#-flash-host");
    if (!host || !msg) return;
    const duration = opts.duration ?? 3800;
    const el = document.createElement("div");
    el.className = "-flash-info";
    el.textContent = String(msg);
    host.appendChild(el);
    const fadeMs = 280;
    const fadeTimer = window.setTimeout(() => el.classList.add("-flash-leaving"), duration);
    const removeTimer = window.setTimeout(() => el.remove(), duration + fadeMs);
    el._FlashTimers = [fadeTimer, removeTimer];
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
      console.log("[initKb] kbPath=" + state.kbPath);
      if (state.kbPath) {
        // 确保服务端 _kb_root 同步（防止前端通过 remembered path 获取但服务端未设置）
        await call("ensure_kb_root", state.kbPath);
      }
      if (window.MemoriaMarkdownPreview?.setKbRootForImages) {
        MemoriaMarkdownPreview.setKbRootForImages(state.kbPath);
      }
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
    const fileMeta = $("#file-meta");
    if (fileMeta) fileMeta.textContent = "";
    showWelcome(true);
  }

  async function openKb() {
    const path = await call("select_directory");
    if (!path) return;
    resetOpenDocumentUi();
    state.kbPath = path;
    if (window.MemoriaMarkdownPreview?.setKbRootForImages) {
      MemoriaMarkdownPreview.setKbRootForImages(path);
    }
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
    state.dirs = res.dirs || [];
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

  function buildFileTreeRoot(files, extraDirs) {
    const root = { dirs: {}, files: [] };
    const ensureDir = (segments) => {
      let node = root;
      let dirPath = "";
      for (const seg of segments) {
        if (!seg) continue;
        dirPath = dirPath ? `${dirPath}/${seg}` : seg;
        if (!node.dirs[seg]) {
          node.dirs[seg] = { name: seg, path: dirPath, dirs: {}, files: [] };
        }
        node = node.dirs[seg];
      }
      return node;
    };
    // 先建立目录骨架（含空目录，保证新建的空文件夹可见）
    for (const d of extraDirs || []) {
      ensureDir(String(d).replace(/\\/g, "/").split("/"));
    }
    for (const f of files) {
      const norm = f.path.replace(/\\/g, "/");
      const parts = norm.split("/");
      const dir = parts.length > 1 ? ensureDir(parts.slice(0, -1)) : root;
      dir.files.push({ ...f, path: norm });
    }
    return root;
  }

  function renderTreeDirNode(node, depth) {
    const expanded = ensureTreeExpandedSet().has(node.path);
    const pad = 4 + depth * 14;
    let html = `<div class="-tree-dir" data-dir="${esc(node.path)}">
      <div class="-tree-dir-head" data-dir-toggle="${esc(node.path)}" style="padding-left:${pad}px">
        <span class="-tree-twisty">${expanded ? "▼" : "▶"}</span>
        <span class="-tree-icon">📁</span>
        <span class="-tree-label">${esc(node.name)}</span>
      </div>
      <div class="-tree-dir-children${expanded ? "" : " collapsed"}">`;
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
    return `<div class="-tree-item${active}${side}" data-path="${esc(f.path)}" title="${esc(f.path)}" style="padding-left:${pad}px">
      <span class="-tree-icon">${icon}</span>
      <span class="-tree-label">${esc(label)}</span>
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
    el.querySelectorAll(".-tree-item").forEach((node) => {
      node.addEventListener("click", () => navigateToFile(node.dataset.path));
    });
    // 右键菜单（事件委托，属性赋值避免 render 重建重复绑定）：
    // 文件 → 重命名/删除；文件夹 → 新建文件/文件夹；空白区 → 根目录下新建
    el.oncontextmenu = (e) => {
      const t = e.target;
      if (!t || !t.closest) return;
      const item = t.closest(".-tree-item");
      if (item) {
        e.preventDefault();
        e.stopPropagation();
        showTreeContextMenu(e.clientX, e.clientY, [
          { label: "重命名", action: () => renameTreeFile(item.dataset.path) },
          { label: "删除", danger: true, action: () => deleteTreeFile(item.dataset.path) },
        ]);
        return;
      }
      const dirHead = t.closest(".-tree-dir-head");
      if (dirHead) {
        e.preventDefault();
        e.stopPropagation();
        const base = dirHead.dataset.dirToggle || "";
        showTreeContextMenu(e.clientX, e.clientY, [
          { label: "新建文件", action: () => createTreeFile(base) },
          { label: "新建文件夹", action: () => createTreeDir(base) },
        ]);
        return;
      }
      if (t.closest("#file-tree")) {
        e.preventDefault();
        e.stopPropagation();
        showTreeContextMenu(e.clientX, e.clientY, [
          { label: "新建文件", action: () => createTreeFile("") },
          { label: "新建文件夹", action: () => createTreeDir("") },
          { label: "图片管理…", action: () => openImageManager() },
        ]);
      }
    };
  }

  // ── 文件树右键菜单 ──────────────────────────────────────────

  const FT_MENU_ID = "-ft-context-menu";
  let _ftMenuBound = false;

  function hideTreeContextMenu() {
    document.getElementById(FT_MENU_ID)?.remove();
  }

  function showTreeContextMenu(x, y, items) {
    hideTreeContextMenu();
    const menu = document.createElement("div");
    menu.id = FT_MENU_ID;
    menu.className = "-context-menu";
    menu.setAttribute("role", "menu");
    for (const it of items) {
      if (it.divider) {
        const div = document.createElement("div");
        div.className = "-ctx-divider";
        menu.appendChild(div);
        continue;
      }
      const row = document.createElement("button");
      row.type = "button";
      row.className = "-ctx-item" + (it.danger ? " danger" : "");
      row.setAttribute("role", "menuitem");
      row.textContent = it.label;
      row.addEventListener("click", (e) => {
        e.stopPropagation();
        hideTreeContextMenu();
        if (it.action) it.action();
      });
      menu.appendChild(row);
    }
    document.body.appendChild(menu);
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    const rect = menu.getBoundingClientRect();
    let nx = x;
    let ny = y;
    if (nx + rect.width > window.innerWidth) nx = window.innerWidth - rect.width - 4;
    if (ny + rect.height > window.innerHeight) ny = window.innerHeight - rect.height - 4;
    menu.style.left = `${Math.max(4, nx)}px`;
    menu.style.top = `${Math.max(4, ny)}px`;

    if (!_ftMenuBound) {
      _ftMenuBound = true;
      document.addEventListener("click", hideTreeContextMenu);
      document.addEventListener("contextmenu", (e) => {
        if (!e.target || !e.target.closest || !e.target.closest("#" + FT_MENU_ID)) {
          hideTreeContextMenu();
        }
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") hideTreeContextMenu();
      });
    }
  }

  /** 轻量应用内输入弹窗（复用 .-modal 样式，避免 pywebview 原生 prompt 系统对话框） */
  function promptTreeInput(title, placeholder, initial, okLabel, cb) {
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML = `
      <div class="-modal-backdrop"></div>
      <div class="-modal-box" style="width:min(360px,92vw)">
        <div class="-modal-header" style="cursor:default"><span>${esc(title)}</span></div>
        <div class="-modal-body">
          <input data-role="ft-input" type="text" style="width:100%;box-sizing:border-box;padding:6px 8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);border-radius:4px;font-size:12px;outline:none"
            placeholder="${esc(placeholder || "")}" value="${esc(initial || "")}" />
        </div>
        <div class="-modal-footer -btn-bar">
          <span class="-modal-footer-spacer"></span>
          <button type="button" class="-btn" data-act="cancel">取消</button>
          <button type="button" class="-btn primary" data-act="ok">${esc(okLabel || "确定")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const input = overlay.querySelector("[data-role=ft-input]");
    const close = (val) => {
      overlay.remove();
      cb(val);
    };
    overlay.querySelector(".-modal-backdrop").addEventListener("click", () => close(null));
    overlay.querySelector('[data-act="cancel"]').addEventListener("click", () => close(null));
    overlay.querySelector('[data-act="ok"]').addEventListener("click", () => {
      close(input.value.trim() || null);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        close(input.value.trim() || null);
      } else if (e.key === "Escape") {
        close(null);
      }
    });
    setTimeout(() => input.focus(), 30);
  }

  /** 轻量应用内确认弹窗 */
  function confirmTreeAction(title, message, okLabel, cb) {
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML = `
      <div class="-modal-backdrop"></div>
      <div class="-modal-box" style="width:min(400px,92vw)">
        <div class="-modal-header" style="cursor:default"><span>${esc(title)}</span></div>
        <div class="-modal-body">${esc(message)}</div>
        <div class="-modal-footer -btn-bar">
          <span class="-modal-footer-spacer"></span>
          <button type="button" class="-btn" data-act="cancel">取消</button>
          <button type="button" class="-btn danger" data-act="ok">${esc(okLabel || "确定")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const close = (val) => {
      overlay.remove();
      if (val) cb();
    };
    overlay.querySelector(".-modal-backdrop").addEventListener("click", () => close(false));
    overlay.querySelector('[data-act="cancel"]').addEventListener("click", () => close(false));
    overlay.querySelector('[data-act="ok"]').addEventListener("click", () => close(true));
  }

  async function renameTreeFile(relPath) {
    const oldName = basename(relPath);
    promptTreeInput("重命名文件", "输入新文件名（自动补 .md）", oldName, "重命名", async (val) => {
      if (!val || val === oldName) return;
      const res = await call("file_rename", relPath, val);
      if (res.status !== "ok") {
        setStatus(res.message || "重命名失败");
        return;
      }
      setStatus("已重命名", res.path);
      if (res.synced) {
        const n = res.md_replacements || 0;
        const m = (res.md_files || []).length;
        const s = (res.sidecar_files || []).length;
        setStatus(`已重命名并同步 ${n} 处链接引用（${m} 个文件正文、${s} 个侧车）`, res.path);
      }
      const tab = state.openTabs.find((t) => t.path === relPath);
      if (tab) {
        tab.path = res.path;
        tab.label = basename(res.path);
      }
      renderTabs();
      await refreshFiles();
      if (state.currentPath === relPath) {
        await openFile(res.path, { fromNav: true });
      }
    });
  }

  async function deleteTreeFile(relPath) {
    confirmTreeAction("删除文件", `确定删除「${basename(relPath)}」？此操作不可恢复。`, "删除", async () => {
      const res = await call("file_delete", relPath);
      if (res.status !== "ok") {
        setStatus(res.message || "删除失败");
        return;
      }
      setStatus("已删除", basename(relPath));
      const tabIdx = state.openTabs.findIndex((t) => t.path === relPath);
      if (tabIdx >= 0) {
        closeTabAt(tabIdx);
      }
      await refreshFiles();
    });
  }

  async function createTreeFile(baseDir) {
    promptTreeInput("新建文件", "输入文件名（自动补 .md）", "", "创建", async (val) => {
      if (!val) return;
      const rel = baseDir ? `${baseDir}/${val}` : val;
      const res = await call("file_create", rel);
      if (res.status !== "ok") {
        setStatus(res.message || "创建失败");
        return;
      }
      setStatus("已创建", res.path);
      if (baseDir) ensureTreeExpandedSet().add(baseDir);
      await refreshFiles();
      await openFile(res.path, { fromNav: true });
    });
  }

  async function createTreeDir(baseDir) {
    promptTreeInput("新建文件夹", "输入文件夹名", "", "创建", async (val) => {
      if (!val) return;
      const rel = baseDir ? `${baseDir}/${val}` : val;
      const res = await call("dir_create", rel);
      if (res.status !== "ok") {
        setStatus(res.message || "创建失败");
        return;
      }
      setStatus("已创建文件夹", res.path);
      if (baseDir) ensureTreeExpandedSet().add(baseDir);
      await refreshFiles();
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
      localStorage.setItem("-graph-group", allId);
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
          <span class="tab-label">${escapeHtml(t.label)}</span>${t.count != null ? ` <span class="-tab-count">${t.count}</span>` : ""}
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
    localStorage.setItem("-graph-group", state.graphGroupId);
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

  /** 需要整体重布局（resetSimulation）的力导向参数 */
  const _RELAYOUT_KEYS = new Set([
    "linkDistance",
    "linkStrength",
    "repulsion",
    "centerStrength",
    "velocityDecay",
    "warmupTicks",
    "spreadFactor",
    "groupSpacing",
    "alphaMin",
    "alphaDecay",
    "alphaTarget",
    "dragReheat",
    "dragReleaseReheat",
  ]);
  /** 维度专属参数；不在表内的共享参数变更视为两个维度都需要重布局 */
  const _DIM_ONLY_KEYS = {
    zoomMin2d: "2d",
    zoomMax2d: "2d",
    zoomSensitivity2d: "2d",
    zoomMinDistance3d: "3d",
    zoomMaxDistance3d: "3d",
    zoomSensitivity3d: "3d",
  };

  function _anyRelayoutKeyChanged(prev, next) {
    for (const k of _RELAYOUT_KEYS) {
      if (prev[k] !== next[k]) return true;
    }
    return false;
  }

  /** 判断哪些维度需要重布局：优先按设置面板当前编辑的维度，其次按参数差异 */
  function _dimsNeedingRelayout(sourceTab, prev, next) {
    const dims = { "2d": false, "3d": false };
    if (!_anyRelayoutKeyChanged(prev, next)) return dims;
    if (sourceTab === "graph2d") {
      dims["2d"] = true;
      return dims;
    }
    if (sourceTab === "graph3d") {
      dims["3d"] = true;
      return dims;
    }
    for (const k of _RELAYOUT_KEYS) {
      if (prev[k] === next[k]) continue;
      const d = _DIM_ONLY_KEYS[k];
      if (d === "2d") dims["2d"] = true;
      else if (d === "3d") dims["3d"] = true;
      else {
        dims["2d"] = true;
        dims["3d"] = true;
      }
    }
    return dims;
  }

  function applyGraphViewSettings(viewOpts, sourceTab) {
    const prev = state._prevViewOpts || {};
    state._prevViewOpts = { ...viewOpts };
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
    const dims = _dimsNeedingRelayout(sourceTab, prev, viewOpts);
    if (dims["2d"]) state.graphView2d?.resetSimulation?.();
    if (dims["3d"]) state.graphView3d?.resetSimulation?.();
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
        ? '<span class="-check-badge -check-badge--error">错误</span>'
        : '<span class="-check-badge -check-badge--warning">警告</span>';
    const dataAttrs = [
      meta?.kpId ? `data-check-kp="${esc(meta.kpId)}"` : "",
      meta?.line ? `data-check-line="${meta.line}"` : "",
      meta?.kind ? `data-check-kind="${esc(meta.kind)}"` : "",
    ].filter(Boolean).join(" ");
    const openBtn = openPath
      ? `<button type="button" class="-btn secondary -check-open-btn" data-check-open="${esc(openPath)}" ${dataAttrs}>打开</button>`
      : "";
    const pathHtml = path
      ? `<div class="-check-item-path">${esc(path)}</div>`
      : "";
    return `<div class="-check-item -check-item--${sev}">
      ${badge}
      <div class="-check-item-main">
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
      body.innerHTML = '<p class="-muted">暂无检查结果</p>';
      return;
    }
    const errN = vr.errors || 0;
    const warnN = vr.warnings || 0;
    const summaryCls =
      errN > 0 ? "-check-summary -check-summary--error" : "-check-summary";
    let html = `<div class="${summaryCls}">
      已检查 ${vr.files_checked || 0} 个 Markdown 文件 ·
      ${errN > 0 ? `<strong class="-stat-error">${errN}</strong>` : `<strong>${errN}</strong>`} 错误 ·
      ${warnN > 0 ? `<strong class="-stat-warn">${warnN}</strong>` : `<strong>${warnN}</strong>`} 警告
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
      html += '<section class="-check-section"><h4 class="-check-section-title">全库</h4>';
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
      html += `<section class="-check-section"><h4 class="-check-section-title">路径变更
        <button type="button" class="-btn secondary -btn--sm" id="check-repair-paths">修复路径</button>
      </h4>`;
      html += `<p class="-muted">检测到文件移动/重命名。请先修复路径（会同步更新元数据、待确认项与文件清单）；在此完成前请勿「更新文件清单」。</p>`;
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
          ? `<button type="button" class="-btn secondary -btn--sm" id="check-sync-manifest">更新文件清单</button>`
          : "";
      html += `<section class="-check-section"><h4 class="-check-section-title">文件清单 ${syncBtn}</h4>`;
      if (md.baseline_created) {
        html += `<p class="-muted">首次打开：已建立文件清单（${md.file_count || 0} 个文档）</p>`;
      } else if (!manifestIssues.length) {
        html += `<p class="-muted">文件清单与磁盘一致（${md.file_count || 0} 个文档）</p>`;
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
      html += `<section class="-check-section"><h4 class="-check-section-title">${esc(fr.path)}</h4>`;
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
      html += '<section class="-check-section"><h4 class="-check-section-title">图谱建边</h4>';
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
      html += '<p class="-muted">未发现配置或图谱问题。</p>';
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

  // ── 图片插入与管理（复制入库 .memoria/images/，阶段 D） ──────────

  async function startInsertImage(insertAtLine) {
    if (!state.kbPath) {
      setStatus("请先打开知识库");
      return;
    }
    if (!state.currentPath) {
      setStatus("请先打开一个文档再插入图片");
      return;
    }
    const local = await call("select_image_file");
    if (!local) return;
    const res = await call("import_image", local);
    if (!res || res.status !== "ok") {
      setStatusError("图片入库失败", (res && res.message) || "未知错误");
      return;
    }
    const alt = String(res.name || "").replace(/\.[^.]+$/, "");
    // URL 用尖括号包裹：文件名可能含中文/空格（如 Windows 截图），裸 URL 会被
    // marked 在空格处截断导致不渲染为图片
    if (!insertSourceLine("![" + alt + "](<" + res.relPath + ">)", insertAtLine)) {
      setStatusError("插入失败", "无法写入源码编辑器");
      return;
    }
    setStatus("图片已入库", res.relPath);
  }

  /** 预览光标所在块的源码起始行（鼠标在预览区域编辑时定位插入点用） */
  function previewCursorSourceLine() {
    const preview = $("#preview");
    const sel = window.getSelection();
    if (!preview || !sel || !sel.rangeCount || !sel.anchorNode) return 0;
    const node =
      sel.anchorNode.nodeType === Node.TEXT_NODE
        ? sel.anchorNode.parentElement
        : sel.anchorNode;
    const block = node && node.closest ? node.closest(".-src-block") : null;
    if (!block || !preview.contains(block)) return 0;
    return +(block.getAttribute("data--src-line") || 0);
  }

  /** 在源码编辑器插入一个独占行（图片须独占一行才渲染），并入撤销栈 */
  function insertSourceLine(text, lineNum) {
    const editor = $("#editor");
    if (!editor) return false;
    const sel = window.getSelection();
    let anchorLine = null;
    if (sel && sel.rangeCount && sel.anchorNode) {
      anchorLine = closestLineEl(sel.anchorNode);
      if (!editor.contains(anchorLine)) anchorLine = null;
    }
    let baseLine = anchorLine;
    // 指定行号优先（预览右键菜单已捕获的光标行）
    if (!baseLine && lineNum > 0) baseLine = document.getElementById("line-" + lineNum);
    // 预览光标兜底：鼠标在预览区域时，selection 锚点在预览 DOM 上
    if (!baseLine) {
      const pLine = previewCursorSourceLine();
      if (pLine > 0) baseLine = document.getElementById("line-" + pLine);
    }
    if (!baseLine) {
      const all = editor.querySelectorAll(".-line");
      baseLine = all[all.length - 1] || null;
    }
    _srcPushBefore();
    _srcCoalesceAt = 0;
    const lastNum = baseLine ? +(baseLine.dataset.line || 0) : 0;
    const newLineEl = document.createElement("div");
    newLineEl.className = "-line";
    newLineEl.dataset.line = String(lastNum + 1);
    newLineEl.id = "line-" + (lastNum + 1);
    const lineno = document.createElement("span");
    lineno.className = "-lineno";
    lineno.textContent = String(lastNum + 1);
    const content = document.createElement("span");
    content.className = "-line-content";
    content.contentEditable = "true";
    content.spellcheck = false;
    content.tabIndex = -1;
    content.textContent = text;
    newLineEl.appendChild(lineno);
    newLineEl.appendChild(content);
    if (baseLine) baseLine.after(newLineEl);
    else editor.appendChild(newLineEl);
    renumberSourceLines();
    _srcAfterEdit();
    const r = document.createRange();
    const node = content.firstChild;
    r.setStart(node, node ? (node.nodeType === Node.TEXT_NODE ? node.textContent.length : 0) : 0);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    scheduleRenderSync();
    markDirty();
    return true;
  }

  /** 编辑光标是否真实位于预览区域（闪烁光标 = 可插入图片） */
  function previewHasCaret() {
    const EH = window.MemoriaEditHandler;
    if (!EH || !EH.editMode) return false;
    // 显式状态机（focusin / 预览区 mouseup / 模式与文件切换维护），
    // 不依赖实时 selection 快照 —— 切换文件后 selection 可能残留旧预览位置，实时读取不可控
    return !!EH._caretInPreview;
  }

  /** 图片插入按钮可用性：仅当文本光标位于预览区域时可点（否则灰色 disabled，不可点） */
  function refreshImageInsertAvailability() {
    const btn = $("#btn-insert-image");
    if (btn) btn.disabled = !previewHasCaret();
  }

  /** 将新的行数组写回文档并重渲染（替换/删除图片用），整体入撤销栈 */
  async function applyImageEditLines(lines) {
    const body = lines.join("\n");
    _srcPushBefore();
    _srcCoalesceAt = 0;
    state.doc.body = body;
    state.doc.lines = lines;
    state.doc.preview_body = null;
    renderEditor(state.doc);
    await renderPreview(state.doc);
    _srcAfterEdit();
    markDirty();
  }

  /** 预览区图片右键菜单：替换（换图保留 alt/title）/ 删除（仅删引用，磁盘文件保留） */
  function showImageContextMenu(x, y, lineNum) {
    showTreeContextMenu(x, y, [
      { label: "替换图片", action: () => replaceImageAtLine(lineNum) },
      { label: "删除图片（仅删引用）", danger: true, action: () => deleteImageAtLine(lineNum) },
    ]);
  }

  async function replaceImageAtLine(lineNum) {
    const local = await call("select_image_file");
    if (!local) return;
    const res = await call("import_image", local);
    if (!res || res.status !== "ok") {
      setStatusError("图片入库失败", (res && res.message) || "未知错误");
      return;
    }
    const lines = (state.doc.body || "").split("\n");
    const raw = lines[lineNum - 1] || "";
    const m = raw.match(/^!\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^)\s]+))((?:\s+"[^"]*")?)\)/);
    if (!m) {
      setStatusError("替换失败", "该行不是标准图片语法");
      return;
    }
    lines[lineNum - 1] = "![" + m[1] + "](<" + res.relPath + ">" + (m[4] || "") + ")";
    await applyImageEditLines(lines);
    setStatus("图片已替换", res.relPath);
  }

  function deleteImageAtLine(lineNum) {
    const lines = (state.doc.body || "").split("\n");
    if (lineNum - 1 >= lines.length) return;
    lines.splice(lineNum - 1, 1);
    applyImageEditLines(lines);
    setStatus("已删除图片引用（磁盘文件保留）");
  }

  // ── 图片管理视图（阶段 F：.memoria/images/ 资产可见化管理） ────────

  let _imgMgrOverlay = null;

  function fmtImageSize(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(2) + " MB";
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + " KB";
    return bytes + " B";
  }

  async function openImageManager() {
    closeImgMgr();
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.id = "-image-manager";
    overlay.innerHTML = `
      <div class="-modal-backdrop"></div>
      <div class="-modal-box -image-mgr-box">
        <div class="-modal-header">
          <span>图片管理</span>
          <span class="-image-mgr-close" data-act="close" title="关闭">✕</span>
        </div>
        <div class="-image-mgr-toolbar">
          <span class="-image-mgr-stat" id="imgr-stat">加载中…</span>
          <button type="button" class="-btn" data-act="refresh">刷新</button>
          <button type="button" class="-btn" data-act="diagnose">检查异常引用</button>
          <button type="button" class="-btn danger" data-act="cleanup">清理未使用图片</button>
        </div>
        <div class="-image-mgr-grid" id="imgr-grid"></div>
      </div>`;
    document.body.appendChild(overlay);
    _imgMgrOverlay = overlay;
    overlay.querySelector(".-modal-backdrop").addEventListener("click", closeImgMgr);
    overlay.querySelector('[data-act="close"]').addEventListener("click", closeImgMgr);
    overlay.querySelector('[data-act="refresh"]').addEventListener("click", renderImageList);
    overlay.querySelector('[data-act="diagnose"]').addEventListener("click", diagnoseImageRefs);
    overlay.querySelector('[data-act="cleanup"]').addEventListener("click", cleanupUnusedImages);
    overlay.querySelector("#imgr-grid").addEventListener("click", onImageCardAction);
    renderImageList();
  }

  function closeImgMgr() {
    if (_imgMgrOverlay) {
      _imgMgrOverlay.remove();
      _imgMgrOverlay = null;
    }
  }

  /** 检查"被文档引用但未成功注册"的图片引用（诊断入口） */
  async function diagnoseImageRefs() {
    const res = await call("diagnose_image_refs");
    if (!res || res.status !== "ok") {
      setStatusError("检查失败", (res && res.message) || "未知错误");
      return;
    }
    const unreg = res.unregistered || [];
    const missing = res.missing || [];
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.id = "-img-diagnose";
    let html = `
      <div class="-modal-backdrop"></div>
      <div class="-modal-box -img-diag-box">
        <div class="-modal-header">
          <span>检查异常图片引用</span>
          <span class="-image-mgr-close" data-act="close" title="关闭">✕</span>
        </div>`;
    if (!unreg.length && !missing.length) {
      html += `<div class="-img-diag-body"><div class="-img-diag-ok">未发现异常引用</div></div></div>`;
    } else {
      if (unreg.length) {
        html += `<div class="-img-diag-body">
          <div class="-img-diag-title">已引用但未注册（${unreg.length}）—— 文件名含空格/中文且未用尖括号包裹，保存时会被误判为未使用而删除</div>
          <ul class="-img-diag-list">` +
          unreg.map((u) => `<li><code>${esc(u.src)}</code><span>（${esc(u.doc)} 第 ${u.line} 行）${u.exists ? "" : " ⚠ 文件已缺失，需重新放入 images"}</span></li>`).join("") +
          `</ul>
          <button type="button" class="-btn" data-act="fix">一键修复为尖括号格式</button>
        </div>`;
      }
      if (missing.length) {
        html += `<div class="-img-diag-body">
          <div class="-img-diag-title">引用格式正常但文件缺失（${missing.length}）</div>
          <ul class="-img-diag-list">` +
          missing.map((u) => `<li><code>${esc(u.url)}</code><span>（${esc(u.doc)} 第 ${u.line} 行）文件不存在</span></li>`).join("") +
          `</ul></div>`;
      }
      html += `</div>`;
    }
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
    overlay.querySelector(".-modal-backdrop").addEventListener("click", () => overlay.remove());
    overlay.querySelector('[data-act="close"]').addEventListener("click", () => overlay.remove());
    const fixBtn = overlay.querySelector('[data-act="fix"]');
    if (fixBtn) {
      fixBtn.addEventListener("click", async () => {
        const r = await call("fix_unregistered_image_refs");
        if (r && r.status === "ok") {
          setStatus("修复完成", `已改写 ${r.fixed} 处引用`);
          overlay.remove();
          renderImageList();
        } else {
          setStatusError("修复失败", (r && r.message) || "未知错误");
        }
      });
    }
  }

  async function renderImageList() {
    const grid = $("#imgr-grid");
    const stat = $("#imgr-stat");
    if (!grid || !stat) return;
    grid.innerHTML = '<div class="-image-mgr-empty">加载中…</div>';
    const res = await call("list_images");
    const imgs = (res && res.images) || [];
    const used = imgs.filter((x) => x.referenced).length;
    stat.textContent = `共 ${imgs.length} 张图片 · 已引用 ${used} · 未使用 ${imgs.length - used}`;
    if (!imgs.length) {
      grid.innerHTML = '<div class="-image-mgr-empty">知识库暂无图片资产</div>';
      return;
    }
    let html = "";
    for (const im of imgs) {
      const refs = im.referencedBy || [];
      const tag = im.referenced
        ? `<span class="-img-tag -img-tag-used">已引用 ${refs.length}</span>`
        : `<span class="-img-tag -img-tag-unused">未使用</span>`;
      const refTxt = im.referenced ? "被 " + refs.join("、") + " 引用" : "未被任何文档引用";
      html += `<div class="-image-card" data-rel="${esc(im.relPath)}" data-name="${esc(im.name)}" data-referenced="${im.referenced ? 1 : 0}">
        <img class="-image-card-thumb" src="/files/${esc(im.relPath)}" alt="${esc(im.name)}" loading="lazy">
        <div class="-image-card-info">
          <div class="-image-card-name" title="${esc(im.name)}">${esc(im.name)}${tag}</div>
          <div class="-image-card-meta">${fmtImageSize(im.size || 0)}</div>
          <div class="-image-card-refs" title="${esc(refTxt)}">${esc(refTxt)}</div>
        </div>
        <div class="-image-card-actions">
          <button type="button" class="-btn" data-act="insert">插入</button>
          <button type="button" class="-btn danger" data-act="delete">删除</button>
        </div>
      </div>`;
    }
    grid.innerHTML = html;
  }

  function onImageCardAction(e) {
    const btn = e.target.closest("button[data-act]");
    const card = e.target.closest(".-image-card");
    if (!btn || !card) return;
    const rel = card.dataset.rel;
    const name = card.dataset.name;
    const referenced = card.dataset.referenced === "1";
    if (btn.dataset.act === "insert") insertImageFromManager(rel, name);
    else if (btn.dataset.act === "delete") deleteImageFromManager(rel, name, referenced);
  }

  function insertImageFromManager(rel, name) {
    if (!state.currentPath) {
      setStatus("请先打开一个文档再插入图片");
      return;
    }
    const alt = String(name || "").replace(/\.[^.]+$/, "");
    if (insertSourceLine("![" + alt + "](<" + rel + '> "width=300")')) {
      setStatus("已插入图片", rel);
    } else {
      setStatusError("插入失败", "无法写入源码编辑器");
    }
  }

  function deleteImageFromManager(rel, name, referenced) {
    if (referenced) {
      const n = (state.doc.lines || []).filter(
        (l) => l.includes(rel) || l.includes("/files/" + rel)
      ).length;
      if (!n) {
        confirmTreeAction(
          "无法删除",
          "该图片被其他文档引用，当前文档未引用它。\n需先在引用它的文档中移除引用，或使用“清理未使用图片”。",
          "知道了",
          () => {}
        );
        return;
      }
      confirmTreeAction(
        "删除引用",
        `该图片在当前文档有 ${n} 处引用。\n将从当前文档移除这些引用（磁盘文件保留）。`,
        "仅删引用",
        () => {
          const lines = (state.doc.body || "")
            .split("\n")
            .filter((l) => !(l.includes(rel) || l.includes("/files/" + rel)));
          applyImageEditLines(lines);
          setStatus("已删除图片引用（磁盘文件保留）");
          renderImageList();
        }
      );
    } else {
      confirmTreeAction(
        "删除图片文件",
        `“${name}”未被任何文档引用。\n确定从 .memoria/images/ 删除该文件吗？此操作不可恢复。`,
        "连文件删",
        async () => {
          const res = await call("cleanup_unused_images", [rel]);
          if (res && res.status === "ok" && (res.deleted || []).length) {
            setStatus("已删除图片文件", name);
            renderImageList();
          } else {
            setStatusError("删除失败", (res && res.message) || "文件不存在");
          }
        }
      );
    }
  }

  async function cleanupUnusedImages() {
    const res = await call("unused_images");
    const un = (res && res.images) || [];
    if (!un.length) {
      setStatus("没有未使用的图片");
      renderImageList();
      return;
    }
    const names = un
      .slice(0, 5)
      .map((x) => x.name)
      .join("、");
    const more = un.length > 5 ? ` 等 ${un.length} 张` : "";
    confirmTreeAction(
      "清理未使用图片",
      `发现 ${un.length} 张未被任何文档引用的图片：${names}${more}\n\n确定删除这些文件吗？此操作不可恢复。`,
      "清理",
      async () => {
        const r = await call("cleanup_unused_images");
        if (r && r.status === "ok") {
          setStatus(`已清理 ${(r.deleted || []).length} 张未使用图片`);
          renderImageList();
        } else {
          setStatusError("清理失败", (r && r.message) || "未知错误");
        }
      }
    );
  }

  /** 更新图片源码行属性（阶段 F 工具栏：对齐/大小滑条；阶段 G：名称字号/显隐），返回新行或 null */
  function updateImageAttrsLine(line, attrs) {
    const m = line.match(/^(!\[[^\]]*\]\([^)\s]+)((?:\s+"[^"]*")?)(\)\s*)$/);
    if (!m) return null;
    const title = m[2].replace(/^\s+"|"$/g, "");
    const list = title ? title.split(",") : [];
    const pending = {};
    ["width", "align", "name-size", "name"].forEach((k) => {
      if (attrs[k] !== undefined) pending[k] = String(attrs[k]);
    });
    const merged = [];
    list.forEach((item) => {
      const eq = item.indexOf("=");
      const k = eq > 0 ? item.slice(0, eq).trim() : item.trim();
      if (pending[k] !== undefined) {
        merged.push(k + "=" + pending[k]);
        pending[k] = undefined;
      } else {
        merged.push(item);
      }
    });
    Object.keys(pending).forEach((k) => {
      if (pending[k] !== undefined) merged.push(k + "=" + pending[k]);
    });
    const newTitle = merged.length ? ' "' + merged.join(",") + '"' : "";
    return m[1] + newTitle + m[3];
  }

  /** 更新图片源码行的名称（alt），返回新行或 null（阶段 G：编辑模式下单击名称文字） */
  function updateImageCaptionLine(line, caption) {
    const m = line.match(/^(!\[)([^\]]*)(\]\([^)\s]+)((?:\s+"[^"]*")?)(\)\s*)$/);
    if (!m) return null;
    return m[1] + caption + m[3] + m[4] + m[5];
  }

  // 图片工具栏属性提交（阶段 F）：对齐/大小 → 更新源码行 → 重写渲染 → 重进编辑
  // 注意：必须 await applyImageEditLines（含 renderPreview）完成后重进编辑，
  // 否则 setTimeout(0) 捕获的是即将被重建的旧 preview DOM，imgEl 变 detached，
  // 后续滑条/对齐操作全部作用在不可见节点上（症状：拖动/确定后图片大小不变）。
  document.addEventListener("memoria:image-attr", async (e) => {
    const detail = (e && e.detail) || {};
    const srcLine = detail.srcLine;
    const attrs = detail.attrs;
    if (!srcLine || !attrs) return;
    const lines = (state.doc.body || "").split("\n");
    const line = lines[srcLine - 1];
    if (!line) return;
    const updated = updateImageAttrsLine(line, attrs);
    if (updated === null) return;
    lines[srcLine - 1] = updated;
    await applyImageEditLines(lines);
    const EH = window.MemoriaEditHandler;
    if (EH && EH.reenterImageEdit) EH.reenterImageEdit(srcLine);
  });

  // 图片名称（alt）编辑提交（阶段 G）：编辑模式下单击名称文字 → 失焦/回车 → 写回源码
  document.addEventListener("memoria:image-caption", async (e) => {
    const detail = (e && e.detail) || {};
    const srcLine = detail.srcLine;
    const caption = detail.caption;
    if (!srcLine || caption === undefined) return;
    const lines = (state.doc.body || "").split("\n");
    const line = lines[srcLine - 1];
    if (!line) return;
    const updated = updateImageCaptionLine(line, caption);
    if (updated === null) return;
    lines[srcLine - 1] = updated;
    await applyImageEditLines(lines);
    const EH = window.MemoriaEditHandler;
    // 名称提交后：光标定位到图片相邻文本（避免残留图片块停靠点/文档开头），
    // 不再重进编辑模式（名称是一次性文字操作；属性/滑条路径仍走 reenterImageEdit）
    if (EH && EH.placeCaretAfterNameEdit) EH.placeCaretAfterNameEdit(srcLine);
  });

  // 图片编辑工具栏 → 打开图片管理
  document.addEventListener("memoria:open-image-manager", () => openImageManager());

  function renderImportConflictDialog(scanResult) {
    const body = $("#import-conflict-body");
    if (!body) return;
    const conflicts = scanResult.conflicts || [];
    let html = "";
    html += `<div class="-import-scan-summary">`;
    html += `<p>共 <strong>${esc(String(scanResult.total_files || 0))}</strong> 个文件，`;
    html += `<strong>${esc(String(scanResult.total_sections || 0))}</strong> 个段落，`;
    html += `<strong>${esc(String(scanResult.total_kp_declarations || 0))}</strong> 个 KP 声明。</p>`;
    html += `<p class="-stat-error">检测到 <strong>${esc(String(conflicts.length))}</strong> 处 KP id 冲突：</p>`;
    html += `</div>`;
    html += `<div class="-import-conflict-report">`;
    html += `<textarea id="import-conflict-report-text" class="-import-report-textarea" readonly rows="4">${esc(scanResult.conflict_report || "")}</textarea>`;
    html += `</div>`;
    html += `<div class="-import-conflict-list">`;
    conflicts.forEach((c, i) => {
      const kpId = esc(c.kp_id || "");
      const source = esc(c.import_source || "");
      const line = c.import_line || 0;
      const existFile = esc(c.existing_file || "");
      const existName = esc(c.existing_name || "");
      html += `<div class="-import-conflict-item" data-conflict-idx="${i}">`;
      html += `<div class="-import-conflict-header">`;
      html += `<span class="-import-conflict-kp-id">${kpId}</span>`;
      html += `<span class="-muted">来源: ${source}:${line} → 已存在: ${existFile} (${existName})</span>`;
      html += `</div>`;
      html += `<div class="-import-conflict-resolution">`;
      html += `<label><input type="radio" name="import-res-${i}" value="skip" checked> 跳过</label>`;
      html += `<label><input type="radio" name="import-res-${i}" value="overwrite"> 覆盖</label>`;
      html += `<label><input type="radio" name="import-res-${i}" value="rename"> 重命名</label>`;
      html += `<input type="text" class="-import-rename-input hidden" data-conflict-idx="${i}" placeholder="新 KP id">`;
      html += `</div>`;
      html += `</div>`;
    });
    html += `</div>`;
    body.innerHTML = html;

    body.querySelectorAll('input[type="radio"]').forEach((radio) => {
      radio.addEventListener("change", (e) => {
        const idx = e.target.name.replace("import-res-", "");
        const renameInput = body.querySelector(`.-import-rename-input[data-conflict-idx="${idx}"]`);
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
        const renameInput = body.querySelector(`.-import-rename-input[data-conflict-idx="${i}"]`);
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
    html += `<div class="-import-result-summary">`;
    html += `<p class="-stat-ok">导入成功</p>`;
    html += `<p>写入 <strong>${esc(String(result.files_written || 0))}</strong> 个文件，`;
    html += `导入 <strong>${esc(String(result.kp_imported || 0))}</strong> 个 KP，`;
    html += `覆盖 <strong>${esc(String(result.kp_overwritten || 0))}</strong> 个，`;
    html += `重命名 <strong>${esc(String(result.kp_renamed || 0))}</strong> 个，`;
    html += `跳过 <strong>${esc(String(result.kp_skipped || 0))}</strong> 个。</p>`;
    const errors = result.errors || [];
    if (errors.length) {
      html += `<p class="-stat-error">${esc(String(errors.length))} 个错误：</p><ul>`;
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
      hint.innerHTML = `<span class="-graph-audit-warn">⚠ ${esc(graphAuditHintLabel(first))}：${esc(first.message)}</span>
        <button type="button" class="-btn secondary -btn--sm -graph-audit-goto">打开文件</button>`;
      return;
    }
    const kbWarns = collectKbGraphAuditWarns(state.graphAudit);
    if (kbWarns.length) {
      const first = kbWarns[0];
      const fileCount = new Set(kbWarns.map((w) => normRelPath(w.file))).size;
      hint.innerHTML = `<span class="-graph-audit-warn">⚠ 全库 ${kbWarns.length} 处 · ${esc(basename(first.file))}${fileCount > 1 ? ` 等 ${fileCount} 文件` : ""}：${esc(first.message)}</span>
        <button type="button" class="-btn secondary -btn--sm -graph-audit-goto">打开 ${esc(basename(first.file))}</button>`;
      return;
    }
    hint.innerHTML =
      state.sidebarTab === "graph3d"
        ? '<span class="-muted">左键旋转 · 滚轮缩放 · 点击跳转 · 悬停正文链接可高亮</span>'
        : '<span class="-muted">滚轮缩放 · 拖空白平移 · 点击跳转 · 悬停正文链接可高亮</span>';
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
    localStorage.setItem("-sidebar-tab", tab);
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
    if (!state.files.length && !(state.dirs || []).length) {
      el.innerHTML = '<div class="empty">无 Markdown 文件</div>';
      return;
    }
    if (state.currentPath) ensureTreeExpandedForPath(state.currentPath);
    const root = buildFileTreeRoot(state.files, state.dirs);
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
    // 切换文件前：同步当前文件到磁盘
    if (state.currentPath && state.currentPath !== relPath) {
      await flushSync();
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
    _dirty = false;
    // 切换文件：清空预览区撤销/重做历史，避免跨文件回退
    if (window.MemoriaEditSync && typeof window.MemoriaEditSync.resetHistory === "function") {
      window.MemoriaEditSync.resetHistory();
    }
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
    srcResetUndo();
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
    // 切换文件：预览区是全新 DOM，旧文件的编辑光标不继承（selection 可能残留，显式清空）
    if (window.MemoriaEditHandler) window.MemoriaEditHandler._caretInPreview = false;
    refreshImageInsertAvailability();
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
    const desc = (doc.sidecar && doc.sidecar.description) || "";
    $("#file-meta").textContent = desc;

    const editor = $("#editor");
    editor.innerHTML = doc.lines
      .map((line, i) => {
        const n = i + 1;
        const content = esc(line) || "<br>";
        return `<div class="-line" data-line="${n}" id="line-${n}">
          <span class="-lineno">${n}</span>
          <span class="-line-content" contenteditable="true" spellcheck="false" tabindex="-1">${content}</span>
        </div>`;
      })
      .join("");
  }

  async function setViewMode(mode, opts) {
    const prevMode = state.viewMode;
    let alreadyRendered = false;
    state.viewMode = mode;
    if (!opts?.skipSave) {
      localStorage.setItem("-view", mode);
    }
    // 页签切换前：将源码编辑器内容同步到内存，刷新两个视图
    if (prevMode !== mode) {
      clearTimeout(_renderTimer);
      syncLog("setViewMode:", prevMode, "→", mode, "| dirty=", _dirty);
      // 始终从源码编辑器收集（它是 markdown 源，不会丢失格式）
      const body = collectEditorBody();
      if (body !== null) {
        state.doc.body = body;
        state.doc.lines = body.split("\n");
        state.doc.preview_body = null;
        syncLog("setViewMode: 更新 state.doc.body, 前80字:", body.substring(0, 80));
      }
      // 从内存重新渲染两个视图
      syncLog("setViewMode: 重新渲染编辑器和预览");
      renderEditor(state.doc);
      await renderPreview(state.doc);
      alreadyRendered = true;
      // 触发写盘
      if (_dirty) { clearTimeout(_saveTimer); syncToDisk(); }
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
    document.querySelectorAll(".-view-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === mode);
    });
    // 视图切换后预览区可见性变化，刷新图片插入按钮的可用状态
    refreshImageInsertAvailability();
    if (mode !== "source" && state.doc && !alreadyRendered) {
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
      const lines = editorPane.querySelectorAll(".-line");
      for (const line of lines) {
        const r = line.getBoundingClientRect();
        if (r.bottom >= containerTop) {
          return +(line.dataset.line || 0) || null;
        }
      }
    }
    if ((mode === "preview" || mode === "split") && previewPane) {
      const containerTop = previewPane.getBoundingClientRect().top;
      const blocks = previewPane.querySelectorAll("[data--src-line]");
      for (const block of blocks) {
        const r = block.getBoundingClientRect();
        if (r.bottom >= containerTop) {
          return +(block.dataset.SrcLine || 0) || null;
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
      const blocks = [...previewPane.querySelectorAll("[data--src-line]")];
      let target = null;
      for (const block of blocks) {
        const s = +(block.dataset.SrcLine || 0);
        const e = +(block.dataset.SrcLineEnd || s);
        if (s <= lineNum && e >= lineNum) { target = block; break; }
        if (s >= lineNum && !target) { target = block; }
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

  let _renderingPreview = false;
  let _renderPending = false;  // 全量渲染被重入保护跳过时置位，当前渲染完成后自动补一次
  var _blockLineMap = null;  // blockIndex → { startLine, endLine } (0-based)

  /**
   * 给 AST 渲染的 DOM 元素标记 data--src-line
   * 直接匹配 sourceLines 和 AST blocks 的消费顺序
   */
  function stampBlockLines(preview, doc) {
    if (!doc || !doc.blocks) return;
    _blockLineMap = [];

    var srcLines = state.doc.body ? state.doc.body.split("\n") : [];
    var srcIdx = 0;
    var blockIdx = 0;

    while (srcIdx < srcLines.length && blockIdx < doc.blocks.length) {
      var block = doc.blocks[blockIdx];
      var rawLine = srcLines[srcIdx];
      var lineCount = 1; // default: 1 source line per block

      // 空行 → BLANK_LINE (1 line)
      if (rawLine.trim() === "") {
        // lineCount stays 1
      }
      // Frontmatter
      else if (srcIdx === 0 && rawLine.trim() === "---") {
        lineCount = 1;
        while (srcIdx + lineCount < srcLines.length && srcLines[srcIdx + lineCount].trim() !== "---")
          lineCount++;
        lineCount++; // include closing ---
      }
      // Fenced code / mermaid
      else if (rawLine.trim().match(/^(`{3,}|~{3,})/)) {
        var fence = rawLine.trim().match(/^(`{3,}|~{3,})/)[1];
        lineCount = 1;
        while (srcIdx + lineCount < srcLines.length && !srcLines[srcIdx + lineCount].trim().startsWith(fence))
          lineCount++;
        lineCount++; // close fence
      }
      // Math block $$
      else if (rawLine.trim() === "$$") {
        lineCount = 1;
        while (srcIdx + lineCount < srcLines.length && srcLines[srcIdx + lineCount].trim() !== "$$")
          lineCount++;
        lineCount++; // closing $$
      }
      // Table (header, separator, data rows)
      else if (rawLine.indexOf("|") >= 0 &&
               srcIdx + 1 < srcLines.length &&
               srcLines[srcIdx + 1].trim().match(/^\|?[\s\-:|]+\|?$/)) {
        lineCount = 2; // header + separator
        while (srcIdx + lineCount < srcLines.length && srcLines[srcIdx + lineCount].indexOf("|") >= 0)
          lineCount++;
      }
      // List items（含空项 "- " 等：用原始行匹配，避免 trim 丢失尾随空格导致漏算）
      // 与 parser 松散列表语义对齐：列表项之间的空行属于同一列表块，跳过后继续收集同类型项
      else if (rawLine.match(/^\s*(\d+\.\s|[-*+]\s)/)) {
        var isOrd = /^\s*\d+\.\s/.test(rawLine);
        lineCount = 1;
        var li = srcIdx + 1;
        while (li < srcLines.length) {
          var lst = srcLines[li];
          if (lst.trim() === "") {
            li++; // 列表块内部的空行：计入该块，继续找后续列表项
            continue;
          }
          var lstM = lst.match(/^\s*(\d+\.\s|[-*+]\s)/);
          if (!lstM) break;
          if (/^\s*\d+\.\s/.test(lst) !== isOrd) break; // 有序/无序类型变化 → 新列表块
          li++;
        }
        lineCount = li - srcIdx;
      }
      // Blockquote (consecutive > lines)
      else if (rawLine.trim().startsWith(">")) {
        lineCount = 1;
        while (srcIdx + lineCount < srcLines.length && srcLines[srcIdx + lineCount].trim().startsWith(">"))
          lineCount++;
      }
      // else: heading / paragraph / image / hr → 1 line

      _blockLineMap[blockIdx] = { startLine: srcIdx, endLine: srcIdx + lineCount - 1 };
      var el = preview.querySelector('.-src-block[data--block-index="' + blockIdx + '"]');
      if (el) {
        el.setAttribute("data--src-line", srcIdx + 1);
        el.setAttribute("data--src-line-end", srcIdx + lineCount);
      }
      blockIdx++;
      srcIdx += lineCount;
    }

    log("STAMP", "mapped " + blockIdx + " blocks from " + srcLines.length + " source lines");
  }

  async function renderPreview(doc, options) {
    if (!doc || state.viewMode === "source") return;
    if (_renderingPreview) {
      // 上次全量渲染未完成（含 await MathJax/Mermaid 挂起窗口）：
      // 直接跳过会让"源码已更新但预览不刷新"（如预览区连续 Enter 拆行）。
      // 置 pending，当前渲染完成后自动补一次渲染最新文档。
      _renderPending = true;
      log("render", "skip: already rendering → queue pending re-render");
      return;
    }
    _renderingPreview = true;
    const incremental = options?.incremental;
    const afterSync = options?.afterSync;
    if (window.MemoriaMarkdownPreview?.setCurrentFileDir && state.currentPath) {
      const parts = state.currentPath.replace(/\\/g, "/").split("/");
      const dir = parts.length > 1 ? parts.slice(0, -1).join("/") + "/" : "";
      log("render", "currentFileDir=" + (dir || "(root)") + "  currentPath=" + state.currentPath);
      MemoriaMarkdownPreview.setCurrentFileDir(dir);
    }
    clearGraphLinkHighlight();
    const preview = $("#preview");
    hidePreviewStatus();
    if (!P || !R || !M) {
      preview.innerHTML = '<p class="-preview-loading">预览模块未加载</p>';
      _renderingPreview = false;
      return;
    }
    const token = ++state.previewToken;
    if (!incremental) {
      preview.innerHTML = '<p class="-preview-loading">渲染中…</p>';
    }
    preview.contentEditable = (window.MemoriaEditHandler && MemoriaEditHandler.editMode) ? "true" : "false";
    try {
      const t0 = performance.now();
      let body = doc.preview_body || doc.body || "";

      // 1. 数学标准化 + 本地图片路径重写（在源码层）
      body = MemoriaMarkdownPreview ? MemoriaMarkdownPreview.normalizeBody(body) : body;
      body = rewriteMdImagePaths(body);

      // 2. AST 解析
      _doc = P.parse(body);
      M.setDoc(_doc);

      // 3. AST → DOM 渲染
      const content = R.render(_doc);
      preview.innerHTML = "";
      preview.appendChild(content);

      // 3b. 构建 block→源行映射，给每个 DOM 元素标记 data--src-line
      stampBlockLines(preview, _doc);

      // 4. 存储 blockLineMap 供 Mapper 使用
      window.__blockLineMap = _blockLineMap;

      // 4. 禁止特殊元素编辑
      preview.querySelectorAll(
        'mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error, .-lightbox-overlay'
      ).forEach(el => { el.contentEditable = "false"; });

      log("F1", "rendered " + _doc.blocks.length + " blocks in " + (performance.now() - t0).toFixed(1) + "ms");

      // 5. 标记图片 alt text（用于 lightbox）
      postProcessWikilinks();
      bindPreviewLinks();

      // 6. Post-process: MathJax, Mermaid, Lightbox
      if (window.MemoriaMarkdownPreview) {
        const MP = MemoriaMarkdownPreview;
        if (MP.renderMermaidBlocks) { try { await MP.renderMermaidBlocks(preview); } catch (e) { log("render", "Mermaid: " + e.message); } }
        if (MP.attachImageLightbox) { try { MP.attachImageLightbox(preview); } catch (e) { log("render", "Lightbox: " + e.message); } }
      }
      if (window.MathJax?.typesetPromise) {
        try { await MathJax.typesetPromise([preview]); } catch (e) { log("render", "MathJax: " + e.message); }
      }

      // 7. Mermaid/MathJax 可能创建了新元素，重新设置 contentEditable=false
      //    直接在 .-src-block 容器上设置，确保即使内部内容被替换也保持不可编辑
      var _nonEditableTypes = { code_block: 1, math_block: 1, mermaid: 1, table: 1, frontmatter: 1 };
      preview.querySelectorAll('.-src-block').forEach(function (blkEl) {
        var bi = parseInt(blkEl.getAttribute("data--block-index"), 10);
        if (!isNaN(bi) && _doc.blocks[bi] && _nonEditableTypes[_doc.blocks[bi].type]) {
          blkEl.contentEditable = "false";
          // 容器内所有子元素也设为不可编辑
          blkEl.querySelectorAll('pre, code, table, svg, mjx-container, .-mermaid-container, .-mermaid-error').forEach(function (el) {
            el.contentEditable = "false";
          });
        }
      });

      // 8. 标记行内公式 mjx-container — MathJax 会替换 .-math span，
      //    导致 dblclick 无法通过 .-math class 找到行内公式。
      //    遍历 AST，将 MATH_INLINE 公式按顺序匹配到可编辑 block 内的 mjx-container
      _tagInlineMathContainers(preview, _doc);

      if (token !== state.previewToken) { _renderingPreview = false; return; }
      showPreviewReport({ ok: true });
      showLinkAuditPreviewHint(doc);
    } catch (e) {
      if (token !== state.previewToken) { _renderingPreview = false; return; }
      preview.innerHTML = `<p class="-preview-loading">预览失败: ${esc(String(e))}</p>`;
      showPreviewReport({ ok: false, messages: [String(e)] });
    }
    _renderingPreview = false;
    // 渲染期间若有请求被重入保护跳过：补渲染一次最新文档，避免预览停留在旧内容
    if (_renderPending) {
      _renderPending = false;
      log("render", "re-run queued render");
      renderPreview(state.doc);
    }
  }

  /**
   * 标记行内公式的 mjx-container 元素
   * MathJax typeset 后 .-math span 可能被替换，导致 dblclick 无法定位。
   * 此函数遍历 AST 中所有 MATH_INLINE 节点，按 block → 顺序匹配 DOM 中的 mjx-container，
   * 打上 data--inline-math="true" 和 data-formula 属性。
   */
  function _tagInlineMathContainers(preview, doc) {
    if (!doc || !doc.blocks) return;
    var _nonEdTypes = { code_block: 1, math_block: 1, mermaid: 1, table: 1, frontmatter: 1 };

    function collectFormulas(block) {
      var formulas = [];
      function walk(node) {
        if (!node) return;
        if (node.type === "math_inline") { formulas.push(node.formula); return; }
        if (node.children) {
          for (var i = 0; i < node.children.length; i++) walk(node.children[i]);
        }
        if (node.items) {
          for (var i = 0; i < node.items.length; i++) {
            if (node.items[i] && node.items[i].children) {
              for (var j = 0; j < node.items[i].children.length; j++) walk(node.items[i].children[j]);
            }
          }
        }
      }
      walk(block);
      return formulas;
    }

    for (var bi = 0; bi < doc.blocks.length; bi++) {
      var block = doc.blocks[bi];
      if (_nonEdTypes[block.type]) continue; // 非可编辑 block 中的 MathJax 是 block math
      var formulas = collectFormulas(block);
      if (formulas.length === 0) continue;
      var blockEl = preview.querySelector('.-src-block[data--block-index="' + bi + '"]');
      if (!blockEl) continue;
      var mjxEls = blockEl.querySelectorAll('mjx-container');
      for (var mi = 0; mi < mjxEls.length && mi < formulas.length; mi++) {
        mjxEls[mi].setAttribute("data--inline-math", "true");
        mjxEls[mi].setAttribute("data-formula", formulas[mi]);
        mjxEls[mi].contentEditable = "false";
      }
    }
  }

  /**
   * 在 markdown 源码中重写本地图片路径 ./images/x.png → /files/images/x.png
   * 在 AST 解析前执行，确保 IMAGE block.url 是正确的服务端路径
   */
  function rewriteMdImagePaths(md) {
    // 处理相对路径图片：裸 URL `![x](.memoria/images/x.png)`（无空格，可选 "title"）
    // 与尖括号包裹 `![x](<.memoria/images/屏幕截图 2026.png> "title")`（含空格/中文，
    // 插入图片功能写出的格式）。统一交给 _rewriteImagePath 重写为 /files/ 编码路径。
    return md.replace(
      /!\[([^\]]*)\]\((?:<([^>]*)>|(\.[^\s)]+))(\s+"[^"]*")?\s*\)/g,
      function (full, alt, angleUrl, bareUrl, title) {
        if (typeof _rewriteImagePath === "function") {
          const src = angleUrl !== undefined ? angleUrl : bareUrl;
          const rewritten = _rewriteImagePath(src);
          if (rewritten === src) return full; // 远程/绝对路径等未重写情况，保持原文
          return "![" + alt + "](" + rewritten + (title || "") + ")";
        }
        return full;
      }
    );
  }

  function _rewriteImagePath(src) {
    var MP = window.MemoriaMarkdownPreview;
    if (!MP || !MP.rewriteLocalImagePaths) return src;
    // 用标记过的 HTML 来触发重写函数
    var tmpHtml = '<img src="' + esc(src) + '">';
    var rewritten = MP.rewriteLocalImagePaths(tmpHtml);
    var m = rewritten.match(/src="([^"]+)"/);
    return m ? m[1] : src;
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
        `<div class="empty">无正式 KP · ${proposals.length} 个标题提议<br><span class="-muted">点「配置」→ 待确认</span></div>`;
      return;
    }

    el.innerHTML = kps
      .map((kp) => {
        const rr = kp.range_resolved || {};
        let cls = "-kp-item";
        if (kp.id === state.activeKpId) cls += " active";
        let meta = kp.id;
        if (rr.ok) {
          meta = `L${rr.start_line}–${rr.end_line}`;
        } else if (rr.error) {
          cls += rr.error.includes("not_found") ? " error" : " warn";
          meta = errorLabel(rr.error);
        }
        const tags = (kp.tags || [])
          .map((t) => `<span class="-tag">${esc(t)}</span>`)
          .join("");
        return `<div class="${cls}" data-kp="${esc(kp.id)}">
          <div class="-kp-name">${esc(kp.name || kp.id)}</div>
          <div class="-kp-meta"><span>${esc(meta)}</span>${tags}</div>
        </div>`;
      })
      .join("");

    el.querySelectorAll(".-kp-item").forEach((node) => {
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
        ? `<div class="-suggest-item -suggest-placeholder">
            <span class="-suggest-score">87%</span>
            <span class="-suggest-label">policy-gradient</span>
            <span class="-muted">本文件 · 可合并</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>合并</button>
          </div>
          <div class="-suggest-item -suggest-placeholder">
            <span class="-suggest-score">72%</span>
            <span class="-suggest-label">q-learning</span>
            <span class="-muted">q-learning.md · 跨文件</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>创建引用</button>
          </div>`
        : `<div class="-suggest-item -suggest-placeholder">
            <span class="-suggest-score">91%</span>
            <span class="-suggest-label">[[q-learning|Q-learning]]</span>
            <span class="-muted">正文 L42 未绑定</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>创建路由</button>
          </div>`;
    const title =
      kind === "kp"
        ? "模糊匹配 · 创建 / 合并知识点（M4）"
        : "模糊匹配 · 推荐链接路由（M4）";
    const hint =
      kind === "kp"
        ? "M4 接入 SearchKernel 后：按 name、tags、description Lexical 精排；近重复合并在此展示。"
        : "M4 接入后：扫描正文 [[…]] 与配置差异；未绑定链接与多目标一并列出。";
    return `<details class="-suggest-block">
      <summary>${esc(title)}</summary>
      <p class="-config-hint">${esc(hint)}</p>
      <div class="-suggest-list">${kpItems}</div>
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
    return `<div class="-config-tabs" role="tablist">
      ${tabs
        .map(
          (t) =>
            `<button type="button" class="-config-tab${activeTab === t.id ? " active" : ""}" data-config-tab="${t.id}" role="tab" aria-selected="${activeTab === t.id}">${esc(t.label)} <span class="-tab-count">${t.count}</span></button>`
        )
        .join("")}
    </div>`;
  }

  function renderConfigKpTab(counts) {
    const { confirmedKps } = counts;
    let html = `<div class="-config-toolbar -btn-bar -btn-bar--start">
      <button type="button" class="-btn primary -btn--sm" data-config-new-kp>新建知识点</button>
      <span class="-muted">空白新建，或在「待确认」Tab 配置标题提议</span>
    </div>`;
    if (!confirmedKps.length) {
      html += `<p class="-muted">暂无正式知识点 · 在「待确认」Tab 配置并确认提议</p>`;
    } else {
      html += confirmedKps
        .map((kp) => {
          const meta = kpRangeMeta(kp);
          const metaCls = meta.ok ? "-muted" : "-config-range-warn";
          const tags = (kp.tags || [])
            .map((t) => `<span class="-tag">${esc(t)}</span>`)
            .join("");
          return `<div class="-config-item">
            <div class="-config-item-main">
              <span class="-config-kp-name">${esc(kp.name || kp.id)}</span>
              <span class="${metaCls}">${esc(meta.text)}</span>
              ${tags}
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn primary -btn--sm" data-kp-config="${esc(kp.id)}">配置</button>
              <button type="button" class="-btn danger -btn--sm" data-kp-delete="${esc(kp.id)}" title="从配置中删除该知识点">删除</button>
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
      parts.push('<span class="-link-audit-bad" title="配置已有，正文无 [[]] 入口">缺正文入口</span>');
    } else if (entry.status === "stale_instance") {
      parts.push('<span class="-link-audit-bad" title="instances 行号与正文不一致">实例失效</span>');
    } else if (entry.status === "partial") {
      parts.push('<span class="-link-audit-warn" title="部分实例未挂接">部分挂接</span>');
    }
    if (entry.targets_resolved === false) {
      parts.push('<span class="-link-audit-warn" title="跳转目标无法解析">目标未解析</span>');
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
      ? `<button type="button" class="-btn secondary -btn--sm" data-link-audit-fix="${esc(first.anchor_text)}">打开首个问题</button>`
      : "";
    return `<div class="-link-audit-banner" role="alert">
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
    return `<div class="-link-search-options" data-search-options-root="${prefix}">
      <label class="-link-search-opt" title="如「深度RL」可匹配正文「深度 RL」">
        <input type="checkbox" data-search-opt="fuzzy_whitespace" ${o.fuzzy_whitespace ? "checked" : ""} />
        忽略空格
      </label>
      <label class="-link-search-opt" title="输入时可推荐已有链接文本、标题或正文匹配">
        <input type="checkbox" data-search-opt="fuzzy_suggest" ${o.fuzzy_suggest ? "checked" : ""} />
        模糊推荐
      </label>
      <label class="-link-search-opt -link-search-opt-future" title="预留 · 后续接搜索引擎">
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
        ? '<p class="-muted -link-match-empty">填写匹配文本后扫描正文</p>'
        : "";
    }
    if (m.loading) {
      return '<p class="-muted -link-match-empty">扫描中…</p>';
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
      variant === "config" ? "-config-link-match -link-match-panel" : "-link-editor-match -link-match-panel";

    const rows = m.matches
      .map((row) => {
        const checked = m.selected.has(row.line);
        const disabled = row.is_substring || row.excluded || row.blocked;
        const cls =
          "-link-match-row" +
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
          ? `<span class="-link-match-check-placeholder" aria-hidden="true">—</span>`
          : `<input type="checkbox" data-match-check="${row.line}" ${checked ? "checked" : ""} aria-label="L${row.line}" />`;
        return `<div class="${cls}" data-match-line="${row.line}" data-match-locate="${disabled ? "1" : "0"}" title="${esc(title)}">
          ${checkCell}
          <div class="-link-match-main">
            <div class="-link-match-head">
              <span class="-link-match-line">L${row.line}</span>
              ${row.section ? `<span class="-link-match-section">${esc(row.section)}</span>` : ""}
              <span class="-link-match-badge">${esc(matchRowBadge(row))}</span>
            </div>
            <div class="-link-match-snippet">${highlightSnippet(row.snippet, row.matched_text)}</div>
          </div>
        </div>`;
      })
      .join("");

    const closeBtn =
      variant === "config"
        ? `<button type="button" class="-icon-btn" id="config-link-match-close" title="收起">×</button>`
        : "";

    let footer = "";
    if (variant === "config") {
      footer = `<div class="-config-link-match-footer -btn-bar">
        <button type="button" class="-btn secondary" id="config-link-match-cancel">取消</button>
        <button type="button" class="-btn primary" id="config-link-match-confirm" ${m.selected.size ? "" : "disabled"}>确认并包裹所选</button>
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
      <div class="-link-match-panel-header">
        <span class="-link-match-panel-title">匹配「${esc(m.anchorText)}」</span>
        <span class="-muted -link-match-panel-hint">${esc(hint)}</span>
        ${closeBtn}
      </div>
      ${searchOptsHtml}
      <div class="-link-match-toolbar -btn-bar -btn-bar--start">
        <button type="button" class="-btn secondary -btn--sm" id="${prefix}-all">${esc(allBtnLabel)}</button>
        <button type="button" class="-btn secondary -btn--sm" id="${prefix}-plain">仅选未包裹</button>
      </div>
      <div class="-link-match-list">${rows || '<p class="-muted">未找到匹配</p>'}</div>
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
      `.-config-link-match-slot[data-link-match-slot="${CSS.escape(a)}"]`
    );
  }

  function _readLinkMatchListScroll(rootEl) {
    const list = rootEl?.querySelector(".-link-match-list");
    return list ? list.scrollTop : 0;
  }

  function _restoreLinkMatchListScroll(rootEl, scrollTop) {
    if (scrollTop == null) return;
    const list = rootEl?.querySelector(".-link-match-list");
    if (list) list.scrollTop = scrollTop;
  }

  function refreshConfigLinkMatchPanel() {
    const prevSlot = configLinkMatchSlotEl(state.configLinkMatch?.anchorText);
    const prevScroll = _readLinkMatchListScroll(prevSlot);
    document.querySelectorAll(".-config-link-match-slot").forEach((el) => {
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
            `<button type="button" class="-suggest-pick" data-anchor-pick="${esc(s.text)}" title="${esc(s.source || "")}">
              <span class="-suggest-label">${esc(s.text)}</span>
              <span class="-muted">${esc(s.source || "")}</span>
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
      .querySelectorAll(".-config-link-item.is-match-active")
      .forEach((el) => el.classList.remove("is-match-active"));
  }

  function renderConfigLinksTab(counts, highlightAnchor, linkAudit) {
    const { fileLinks } = counts;
    let html = renderLinkAuditBanner(linkAudit);
    html += `<div class="-config-toolbar -btn-bar -btn-bar--start">
      <button type="button" class="-btn primary -btn--sm" id="config-new-link">新建链接</button>
      <span class="-muted">正文选区右键也可创建 · 源码/预览均可拖选 · 匹配文本须与 [[…]] 一致</span>
    </div>`;
    if (!fileLinks.length) {
      html += `<p class="-muted">尚未配置链接 · [[文本]] 按知识点 id 或文件名解析</p>`;
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
          return `<div class="-config-link-block">
          <div class="-config-item -config-link-item${hl}" data-link-anchor="${esc(anchor)}" role="button" tabindex="0" title="点击在下方匹配正文位置">
            <div class="-config-item-main">
              <code class="-config-anchor">${esc(anchor)}</code>
              ${badge}
              <span class="-muted">→ ${esc(targets || "（未绑定）")}${pool}${instHint}</span>
              ${auditEntry?.issues?.length ? `<span class="-link-audit-detail" title="${esc(auditEntry.issues.join("；"))}">${esc(auditEntry.issues[0])}</span>` : ""}
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn secondary -btn--sm" data-link-match="${esc(anchor)}" title="在下方选择正文挂接位置">匹配</button>
              <button type="button" class="-btn primary -btn--sm" data-link-edit="${esc(anchor)}">编辑</button>
              <button type="button" class="-btn danger -btn--sm" data-link-delete="${esc(anchor)}" title="删除跳转入口及正文 [[]]">删除</button>
            </div>
          </div>
          <div class="-config-link-match-slot" data-link-match-slot="${esc(anchor)}">${matchPanelHtml}</div>
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
    let html = `<div class="-config-toolbar -btn-bar -btn-bar--start">
      <button type="button" class="-btn secondary -btn--sm" data-config-sync-pending>刷新待确认</button>
      ${kbTotal != null ? `<span class="-muted">全库 ${kbTotal} 项</span>` : ""}
    </div>`;
    if (!counts.pending) {
      html += `<p class="-muted">无待确认提议 · 扫描标题、段落 mention 或定义句（「X 是…」）后出现在此</p>`;
      html += renderConfigPendingSuggestBlocks();
      return html;
    }
    if (pendingHeading.length) {
      html += `<div class="-config-kp-group"><div class="-config-kp-group-title">标题提议 (${pendingHeading.length})</div>`;
      html += pendingHeading
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = headingP.indexOf(p);
          return `<div class="-config-item">
            <div class="-config-item-main">
              <span class="-config-tag">标题</span>
              <span class="-config-kp-name">${esc(p.name)}</span>
              <span class="-muted">${lines}</span>
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn primary -btn--sm" data-heading-proposal="${idx}">配置并确认</button>
              ${p.pending_id ? `<button type="button" class="-btn secondary -btn--sm" data-dismiss-pending="${esc(p.pending_id)}">忽略</button>` : ""}
            </div>
          </div>`;
        })
        .join("");
      html += `</div>`;
    }
    if (pendingMention.length) {
      html += `<div class="-config-kp-group"><div class="-config-kp-group-title">段落提议 (${pendingMention.length})</div>`;
      html += pendingMention
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = mentionP.indexOf(p);
          return `<div class="-config-item">
            <div class="-config-item-main">
              <span class="-config-tag">段落</span>
              <span class="-config-kp-name">${esc(p.name)}</span>
              <span class="-muted">${lines}</span>
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn primary -btn--sm" data-mention-proposal="${idx}">配置并确认</button>
              ${p.pending_id ? `<button type="button" class="-btn secondary -btn--sm" data-dismiss-pending="${esc(p.pending_id)}">忽略</button>` : ""}
            </div>
          </div>`;
        })
        .join("");
      html += `</div>`;
    }
    if (pendingDefinition.length) {
      html += `<div class="-config-kp-group"><div class="-config-kp-group-title">定义句提议 (${pendingDefinition.length})</div>`;
      html += pendingDefinition
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = definitionP.indexOf(p);
          return `<div class="-config-item">
            <div class="-config-item-main">
              <span class="-config-tag">定义</span>
              <span class="-config-kp-name">${esc(p.name)}</span>
              <span class="-muted">${lines}</span>
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn primary -btn--sm" data-definition-proposal="${idx}">配置并确认</button>
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
        body.querySelector(".-config-link-item.is-highlight")?.scrollIntoView({
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

    let html = `<p class="-config-summary">元数据 ${hasSidecar ? "已配置" : "未创建"} · 知识点 ${counts.kp} · 链接 ${counts.links} · 待确认 ${counts.pending}</p>`;
    if (validation.errors?.length) {
      html += `<p class="-config-error">错误：${esc(validation.errors.join("；"))}</p>`;
    }
    if (validation.warnings?.length) {
      html += `<p class="-config-warn">警告：${esc(validation.warnings.join("；"))}</p>`;
    }
    if (tab === "links" && doc.link_audit && !doc.link_audit.ok) {
      const n = doc.link_audit.summary?.issue_count || 0;
      if (n) {
        html += `<p class="-config-warn">链接一致性：${n} 个入口未在正文中挂接为可点击 [[…]]</p>`;
      }
    }

    html += renderConfigTabBar(counts, tab);
    html += `<div class="-config-tab-panel" role="tabpanel">`;
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
    return `<div class="-config-tabs -kp-tabs" role="tablist">
      ${tabs
        .map(
          (t) =>
            `<button type="button" class="-config-tab${activeTab === t.id ? " active" : ""}" data-kp-tab="${t.id}" role="tab">${esc(t.label)}</button>`
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
      html += `<p class="-config-range-warn">${esc(errorLabel(a.error))}</p>`;
    }
    const total = state.doc?.lines?.length || 0;
    html += `<div class="-assist-line-inputs">
      <label>起点行 <input type="number" class="-line-input" data-range-start min="1" max="${total || ""}" value="${a.startLine}"></label>
      <label>终点行 <input type="number" class="-line-input" data-range-end min="1" max="${total || ""}" value="${a.endLine}"></label>
      <span class="-muted">滚轮可微调行号${total ? ` · 正文共 ${total} 行` : ""}</span>
    </div>`;
    if (a.startCandidates.length > 1) {
      html += `<p class="-range-candidates-label"><strong>起点候选</strong></p>`;
      html += `<div class="-range-candidates">${renderCandidates("start", a.startCandidates)}</div>`;
    }
    if (a.endCandidates.length > 1) {
      html += `<p class="-range-candidates-label"><strong>终点候选</strong></p>`;
      html += `<div class="-range-candidates">${renderCandidates("end", a.endCandidates)}</div>`;
    }
    html += `<div data-range-preview class="-assist-preview-wrap"></div>`;
    html += `<p class="-muted">调整行号即更新高亮；预览区可切换源码 / Markdown。</p>`;
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
    body?.classList.toggle("-modal-body-kp-range", tab === "range");
    body?.classList.toggle("-modal-body-kp-edges", tab === "edges");
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
      content = `<div class="-kp-tab-panel -kp-range-panel">${buildRangeEditorHtml(state.assist)}</div>`;
    } else if (tab === "identity") {
      clearKpRangeAssist();
      const idVal = isCreate ? kp.id : (panel.draft?.id ?? kp.id);
      const nameVal = isCreate ? (kp.name || kp.id) : (panel.draft?.name ?? kp.name ?? kp.id);
      content = `<div class="-kp-tab-panel"><div class="-kp-form">
        <label class="-link-field">id <input type="text" id="kp-field-id" value="${esc(idVal)}" autocomplete="off" spellcheck="false"></label>
        <label class="-link-field">名称 <input type="text" id="kp-field-name" value="${esc(nameVal)}" autocomplete="off"></label>
        <p class="-config-hint">${isCreate ? "新建知识点请先在此填写 id 与名称，再到「范围」调整行号。" : "修改 id 将全库同步链接配置与正文 [[…]]（显示文字保持不变）。"}</p>
        ${isCreate ? "" : `<div id="kp-merge-suggest" class="-kp-merge-suggest hidden"></div>`}
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
      content = `<div class="-kp-tab-panel"><div class="-kp-form">
        ${renderKpTagsEditorHtml(panel, kp, isCreate)}
        ${renderKpAliasEditorHtml(panel, kp)}
        <label class="-link-field">描述
          <textarea id="kp-desc-input" rows="3" placeholder="可选；用于检索与图谱提示">${esc(desc)}</textarea>
        </label>
        ${renderKpDescCandEditorHtml(panel, kp)}
        <div class="-kp-tags-zone-toolbar">
          <button type="button" id="kp-sync-aux" class="-btn secondary -btn--sm">同步检索 aux</button>
          <button type="button" id="kp-suggest-desc" class="-btn secondary -btn--sm">建议描述</button>
        </div>
        <p class="-config-hint">${isCreate ? "描述可选；确认创建时会一并保存。tag/别名/描述候选可提前配置。" : "已选 tag/别名保存后参与检索；候选区点击应用；「同步检索 aux」合并隐式索引提议。"}</p>
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
    return `<span class="-edge-type-badge" style="background:${color};color:#fff">${esc(label)}</span>`;
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

    let html = `<div class="-kp-tab-panel -kp-edges-panel">`;

    // Outgoing edges section
    html += `<div class="-edge-section">`;
    html += `<h4 class="-edge-section-title">出边 <span class="-tab-count">${outgoing.length}</span></h4>`;
    if (outgoing.length) {
      html += `<div class="-edge-list">`;
      for (const e of outgoing) {
        html += `<div class="-edge-item" data-edge-type="${esc(e.type)}" data-edge-source="${esc(e.source_id)}" data-edge-target="${esc(e.target_id)}" data-edge-origin="${esc(e.origin || "")}" ${e.anchor_text ? `data-edge-anchor="${esc(e.anchor_text)}"` : ""}>`;
        html += `<div class="-edge-main">`;
        html += edgeTypeBadgeHtml(e.type);
        html += `<span class="-edge-arrow">${esc(kpNameForId(e.source_id))} → ${esc(kpNameForId(e.target_id))}</span>`;
        html += `<span class="-edge-relevance">${e.relevance != null ? Number(e.relevance).toFixed(2) : "—"}</span>`;
        html += `<span class="-edge-origin">${esc(edgeOriginLabel(e))}</span>`;
        if (e.no_build) html += `<span class="-edge-no-build">已抑制</span>`;
        html += `</div>`;
        html += `<div class="-edge-actions">`;
        if (e.type === "contain" && e.no_build) {
          html += `<button type="button" class="-btn secondary -btn--sm -edge-btn-restore" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}">恢复</button>`;
        } else if (e.type === "contain" && !e.no_build) {
          html += `<button type="button" class="-btn secondary -btn--sm -edge-btn-suppress" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}">抑制</button>`;
        }
        if (e.origin === "sidecar_edge") {
          html += `<button type="button" class="-btn danger -btn--sm -edge-btn-delete" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}" data-type="${esc(e.type)}">删除</button>`;
        }
        if (e.origin === "link" && e.anchor_text) {
          html += `<button type="button" class="-btn secondary -btn--sm -edge-btn-config-link" data-anchor="${esc(e.anchor_text)}">配置链接</button>`;
        }
        html += `</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    } else {
      html += `<p class="-muted">无出边</p>`;
    }
    html += `</div>`;

    // Incoming edges section
    html += `<div class="-edge-section">`;
    html += `<h4 class="-edge-section-title">入边 <span class="-tab-count">${incoming.length}</span></h4>`;
    if (incoming.length) {
      html += `<div class="-edge-list">`;
      for (const e of incoming) {
        html += `<div class="-edge-item" data-edge-type="${esc(e.type)}" data-edge-source="${esc(e.source_id)}" data-edge-target="${esc(e.target_id)}" data-edge-origin="${esc(e.origin || "")}">`;
        html += `<div class="-edge-main">`;
        html += edgeTypeBadgeHtml(e.type);
        html += `<span class="-edge-arrow">${esc(kpNameForId(e.source_id))} → ${esc(kpNameForId(e.target_id))}</span>`;
        html += `<span class="-edge-relevance">${e.relevance != null ? Number(e.relevance).toFixed(2) : "—"}</span>`;
        html += `<span class="-edge-origin">${esc(edgeOriginLabel(e))}</span>`;
        if (e.no_build) html += `<span class="-edge-no-build">已抑制</span>`;
        html += `</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    } else {
      html += `<p class="-muted">入边需全库扫描，当前仅显示本文件内入边</p>`;
    }
    html += `</div>`;

    // Create new edge form
    html += `<div class="-edge-section -edge-create-form">`;
    html += `<h4 class="-edge-section-title">新建边</h4>`;
    html += `<div class="-edge-create-fields">`;
    html += `<label class="-link-field">目标 KP <input type="text" id="kp-edge-target" placeholder="输入 KP id" autocomplete="off" spellcheck="false"></label>`;
    html += `<label class="-link-field">边类型 <select id="kp-edge-type"><option value="reference">引用 (reference)</option><option value="extend">扩展 (extend)</option></select></label>`;
    html += `<label class="-link-field">关联度 <input type="range" id="kp-edge-relevance" min="0" max="1" step="0.05" value="0.7"><span id="kp-edge-relevance-val">0.70</span></label>`;
    html += `<button type="button" id="kp-edge-create-btn" class="-btn primary -btn--sm">新建</button>`;
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
    body.querySelectorAll(".-edge-btn-suppress").forEach((btn) => {
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
    body.querySelectorAll(".-edge-btn-restore").forEach((btn) => {
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
    body.querySelectorAll(".-edge-btn-delete").forEach((btn) => {
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
    body.querySelectorAll(".-edge-btn-config-link").forEach((btn) => {
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
        const existing = body.querySelector(".-edge-target-datalist");
        if (existing) existing.remove();
        if (!val) return;
        const kpIds = (state.doc?.knowledge_points || [])
          .map((k) => k.id)
          .filter((id) => id.toLowerCase().includes(val) && id !== kp.id);
        const linkTargets = state.linkTargetList || [];
        const allIds = [...new Set([...kpIds, ...linkTargets.filter((t) => t.toLowerCase().includes(val))])];
        if (!allIds.length) return;
        const datalist = document.createElement("div");
        datalist.className = "-edge-target-datalist";
        allIds.slice(0, 10).forEach((id) => {
          const opt = document.createElement("div");
          opt.className = "-edge-target-option";
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
          const dl = body.querySelector(".-edge-target-datalist");
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
    const dismiss = `<button type="button" class="-kp-tag-chip-btn" data-alias-dismiss="${esc(alias)}" title="移除">×</button>`;
    const kindCls =
      kind === "selected"
        ? "-kp-tag-pick--selected"
        : kind === "cand-user"
          ? "-kp-tag-pick--cand-user"
          : "-kp-tag-pick--cand-system";
    const title = kind === "selected" ? "点击移到候选" : "点击应用到已选";
    return `<span class="-kp-tag-pick ${kindCls}" data-alias="${esc(alias)}" data-alias-kind="${kind === "selected" ? "selected" : "candidate"}" title="${title}">
      <span class="-kp-tag-chip-label">${esc(alias)}</span>
      <span class="-kp-tag-chip-actions">${dismiss}</span>
    </span>`;
  }

  function renderKpDescCandChip(text, source) {
    const kindCls = source === "user" ? "-kp-tag-pick--cand-user" : "-kp-tag-pick--cand-system";
    const short = text.length > 72 ? text.slice(0, 70) + "…" : text;
    return `<span class="-kp-tag-pick ${kindCls} -kp-desc-cand" data-desc-cand="${esc(text)}" title="点击填入描述">
      <span class="-kp-tag-chip-label">${esc(short)}</span>
      <button type="button" class="-kp-tag-chip-btn" data-desc-dismiss="${esc(text)}" title="移除">×</button>
    </span>`;
  }

  function renderKpAliasEditorHtml(panel, kp) {
    const as = ensureKpAliasState(panel, kp);
    const selHtml = as.selected.length
      ? as.selected.map((a) => renderKpAliasChip(a, "selected")).join("")
      : `<span class="-muted -kp-tags-empty">暂无已选别名</span>`;
    const candHtml = as.candidates.length
      ? as.candidates
          .map((c) =>
            renderKpAliasChip(c.alias, c.source === "user" ? "cand-user" : "cand-system")
          )
          .join("")
      : `<span class="-muted -kp-tags-empty">同步 aux 或下方新建</span>`;
    return `<div class="-kp-tags-editor -kp-alias-editor" id="kp-alias-editor">
      <div class="-kp-tags-zone -kp-tags-zone--selected">
        <div class="-kp-tags-zone-head">已选别名 <span class="-muted">参与检索</span></div>
        <div id="kp-alias-selected" class="-kp-tags-chips">${selHtml}</div>
      </div>
      <div class="-kp-tags-zone -kp-tags-zone--candidate">
        <div class="-kp-tags-zone-head">别名候选</div>
        <div class="-kp-tags-zone-toolbar">
          <div class="-kp-tag-create-row">
            <input type="text" id="kp-alias-new-input" placeholder="新建别名" autocomplete="off" spellcheck="false" />
            <button type="button" id="kp-alias-add-btn" class="-btn secondary -btn--sm">加入候选</button>
          </div>
        </div>
        <div id="kp-alias-candidates" class="-kp-tags-chips">${candHtml}</div>
      </div>
    </div>`;
  }

  function renderKpDescCandEditorHtml(panel, kp) {
    const ds = ensureKpDescCandState(panel, kp);
    const candHtml = ds.candidates.length
      ? ds.candidates
          .map((c) => renderKpDescCandChip(c.text, c.source))
          .join("")
      : `<span class="-muted -kp-tags-empty">同步 aux 后显示描述候选</span>`;
    return `<div class="-kp-desc-cand-editor" id="kp-desc-cand-editor">
      <div class="-kp-tags-zone-head">描述候选 <span class="-muted">点击填入上方描述框</span></div>
      <div id="kp-desc-candidates" class="-kp-tags-chips">${candHtml}</div>
    </div>`;
  }

  function refreshKpAliasEditorDom(panel, kp) {
    const sel = $("#kp-alias-selected");
    const cand = $("#kp-alias-candidates");
    if (!panel?.draft?.aliasState || !sel) return;
    const as = panel.draft.aliasState;
    sel.innerHTML = as.selected.length
      ? as.selected.map((a) => renderKpAliasChip(a, "selected")).join("")
      : `<span class="-muted -kp-tags-empty">暂无已选别名</span>`;
    if (cand) {
      cand.innerHTML = as.candidates.length
        ? as.candidates
            .map((c) =>
              renderKpAliasChip(c.alias, c.source === "user" ? "cand-user" : "cand-system")
            )
            .join("")
        : `<span class="-muted -kp-tags-empty">同步 aux 或下方新建</span>`;
    }
  }

  function refreshKpDescCandEditorDom(panel, kp) {
    const root = $("#kp-desc-candidates");
    if (!panel?.draft?.descCandState || !root) return;
    const ds = panel.draft.descCandState;
    root.innerHTML = ds.candidates.length
      ? ds.candidates.map((c) => renderKpDescCandChip(c.text, c.source)).join("")
      : `<span class="-muted -kp-tags-empty">同步 aux 后显示描述候选</span>`;
  }

  function renderKpTagChip(tag, kind, opts = {}) {
    const score =
      opts.score != null
        ? `<span class="-kp-tag-pick-score">${esc(String(Math.round(opts.score)))}</span>`
        : "";
    const dismiss = `<button type="button" class="-kp-tag-chip-btn" data-tag-dismiss="${esc(tag)}" title="移除">×</button>`;
    const kindCls =
      kind === "selected"
        ? "-kp-tag-pick--selected"
        : kind === "cand-user"
          ? "-kp-tag-pick--cand-user"
          : "-kp-tag-pick--cand-system";
    const title =
      kind === "selected" ? "点击移到候选" : "点击应用到已选";
    return `<span class="-kp-tag-pick ${kindCls}" data-tag="${esc(tag)}" data-tag-kind="${kind === "selected" ? "selected" : "candidate"}" title="${title}">
      <span class="-kp-tag-chip-label">${esc(tag)}</span>${score}
      <span class="-kp-tag-chip-actions">${dismiss}</span>
    </span>`;
  }

  function renderKpTagsEditorHtml(panel, kp, isCreate) {
    const ts = ensureKpTagState(panel, kp);
    const selectedHtml = ts.selected.length
      ? ts.selected.map((t) => renderKpTagChip(t, "selected")).join("")
      : `<span class="-muted -kp-tags-empty">暂无已选 tag</span>`;
    const candHtml = ts.candidates.length
      ? ts.candidates
          .map((c) =>
            renderKpTagChip(c.tag, c.source === "user" ? "cand-user" : "cand-system", {
              score: c.score,
            })
          )
          .join("")
      : `<span class="-muted -kp-tags-empty">点击「系统建议」或下方新建</span>`;
    return `<div class="-kp-tags-editor" id="kp-tags-editor">
      <div class="-kp-tags-zone -kp-tags-zone--selected">
        <div class="-kp-tags-zone-head">已选 <span class="-muted">点击 chip 移到候选</span></div>
        <div id="kp-tags-selected" class="-kp-tags-chips">${selectedHtml}</div>
      </div>
      <div class="-kp-tags-zone -kp-tags-zone--candidate">
        <div class="-kp-tags-zone-head">候选 <span class="-muted">点击 chip 应用到已选 · × 移除</span></div>
        <div class="-kp-tags-zone-toolbar">
          <button type="button" id="kp-suggest-tags" class="-btn secondary -btn--sm">系统建议</button>
          <div class="-kp-tag-create-row">
            <input type="text" id="kp-tag-new-input" placeholder="新建 tag" autocomplete="off" spellcheck="false" />
            <button type="button" id="kp-tag-add-btn" class="-btn secondary -btn--sm">加入候选</button>
          </div>
        </div>
        <div id="kp-tags-candidates" class="-kp-tags-chips">${candHtml}</div>
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
        : `<span class="-muted -kp-tags-empty">暂无已选 tag</span>`;
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
        : `<span class="-muted -kp-tags-empty">点击「系统建议」或下方新建</span>`;
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
        const chip = e.target.closest(".-kp-tag-pick");
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
        `<p class="-config-hint">名称相近的知识点（仅供参考，合并需手动处理）：</p>` +
        items
          .map(
            (s) =>
              `<button type="button" class="-suggest-item -kp-merge-hit" data-merge-file="${esc(s.file || "")}" data-merge-kp="${esc(s.kp_id || "")}">
                <span class="-suggest-score">${esc(String(Math.round(s.score || 0)))}</span>
                <span class="-suggest-label">${esc(s.name || s.kp_id)}</span>
                <span class="-muted">${esc(basename(s.file || ""))}</span>
              </button>`
          )
          .join("");
      box.classList.remove("hidden");
      box.querySelectorAll(".-kp-merge-hit").forEach((btn) => {
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
    $("#kp-body")?.classList.remove("-modal-body-kp-range");
    $("#kp-body")?.classList.remove("-modal-body-kp-edges");
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
    return `<div class="-link-target-edge">
      <span class="-link-target-edge-label">类型</span>
      <select data-target-edge-type="${pickIndex}">
        <option value="reference"${et === "reference" ? " selected" : ""}>引用</option>
        <option value="extend"${et === "extend" ? " selected" : ""}>扩展</option>
      </select>
      <span class="-link-target-edge-label">强度</span>
      <input type="range" data-target-edge-rel-range="${pickIndex}" min="0" max="1" step="0.05" value="${rel}" title="边强度 relevance" />
      <input type="number" data-target-edge-rel-num="${pickIndex}" class="-link-relevance-num" min="0" max="1" step="0.05" value="${formatLinkRelevance(rel)}" title="边强度 relevance" />
      <button type="button" class="-btn secondary -btn--sm" data-target-edge-suggest="${pickIndex}">推荐</button>
    </div>`;
  }

  function renderLinkTargetEdgesPanel(p) {
    if (!p.selectedOrder.length) {
      return `<div class="-link-edge-editor-panel" id="link-edge-editor-panel">
        <div class="-link-section-title">图谱边</div>
        <p class="-muted -link-edge-empty">请先勾选跳转目标，再在此配置语义边属性</p>
      </div>`;
    }
    const items = p.selectedOrder
      .map((pickIndex) => {
        const c = p.candidates[pickIndex];
        const tid = candidateTargetId(c);
        if (!tid) return "";
        const props = ensureTargetEdge(p, tid);
        const name = c?.name || tid;
        return `<div class="-link-edge-editor-item">
          <div class="-link-edge-editor-head">
            <span class="-link-edge-editor-name">${esc(name)}</span>
            <span class="-link-edge-editor-id -muted">${esc(tid)} · ${esc(c?.file || tid)}</span>
          </div>
          ${renderTargetEdgeControls(pickIndex, props)}
        </div>`;
      })
      .join("");
    return `<div class="-link-edge-editor-panel" id="link-edge-editor-panel">
      <div class="-link-section-title">图谱边</div>
      <p class="-config-hint -link-edge-panel-hint">为下方每个已选目标单独设置语义关系。</p>
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
    let html = `<div class="-link-edit-meta">`;
    html += `<label class="-link-field"><span>匹配文本</span>
      <div class="-link-anchor-field">
        <input type="text" id="link-edit-anchor" value="${esc(text)}" placeholder="正文与预览中可见的文字，即跳转键" autocomplete="off" spellcheck="false" />
        <div class="-link-target-suggest hidden" id="link-anchor-suggest"></div>
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
      html += `<p class="-config-hint -link-meta-hint">对应正文 <code>[[匹配文本]]</code>。输入框为搜索词；保存时按所选匹配项采用正文 canonical 文本。</p>`;
      html += `<div class="-link-section-title">点击后打开</div>`;
      html += `<p class="-config-hint -link-targets-hint">勾选目标参与跳转。</p>`;
    }

    if (isEdit) {
      html += `<div class="-link-pick-legend">
        <span><i class="-link-legend-dot sel"></i>已选（参与跳转）</span>
        <span><i class="-link-legend-dot"></i>未选（保留备选）</span>
      </div>`;
    } else {
      html += `<div class="-link-pick-legend">
        <span><i class="-link-legend-dot primary"></i>队首跳转</span>
        <span><i class="-link-legend-dot sel"></i>已选入队</span>
        <span><i class="-link-legend-dot"></i>未选</span>
      </div>`;
    }

    if (!candidates.length && isEdit) {
      html += `<p class="-muted -link-empty">暂无目标 · 在下方添加 KP id 或文件 stem</p>`;
    }

    html += candidates
      .map((c, i) => {
        const rank = pickIndexRank(selectedOrder, i);
        const isSelected = rank >= 0;
        const isPrimary = !isEdit && rank === 0;
        let dotCls = "-pick-dot";
        if (isPrimary) dotCls += " is-primary";
        else if (isSelected) dotCls += " is-selected";
        const rowCls =
          "-link-pick-item" +
          (isPrimary ? " is-active" : isEdit && isSelected ? " is-selected-row" : "");
        const tid = candidateTargetId(c);
        return `<div class="${rowCls}" data-pick-row="${i}">
          <button type="button" class="${dotCls}" data-pick-dot="${i}" aria-label="选择">
            <span class="-pick-dot-inner"></span>
          </button>
          <div class="-link-pick-label">
            <div class="-link-pick-name">${esc(c.name || tid || c.file)}</div>
            <div class="-link-pick-file">${esc(c.file || tid)}</div>
          </div>
          ${isEdit ? `<button type="button" class="-link-remove-target" data-remove-target="${i}" title="移除">×</button>` : ""}
        </div>`;
      })
      .join("");

    if (isEdit) {
      html += `<div class="-link-add-row">
        <div class="-link-add-field">
          <input type="text" id="link-add-target" placeholder="id 或 tag:rl policy …" autocomplete="off" spellcheck="false" />
          <div class="-link-target-suggest hidden" id="link-add-target-suggest"></div>
        </div>
        <button type="button" id="link-add-target-btn">添加</button>
      </div>`;
      html += renderLinkTargetEdgesPanel(p);
      html += `<details class="-suggest-block -link-tag-suggest">
        <summary>智能匹配（M4 · tag / Lexical）</summary>
        <p class="-config-hint">输入 tag: 前缀按标签检索知识点；无匹配时可创建未绑定链接或新建知识点。</p>
        <div class="-suggest-list -suggest-placeholder-list">
          <div class="-suggest-item -suggest-placeholder">
            <span class="-suggest-score">94%</span>
            <span class="-suggest-label">q-learning</span>
            <span class="-muted">tag:rl · q-learning.md</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>选用</button>
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
        return `<button type="button" class="-link-target-opt" data-target-id="${esc(id)}" title="${esc(label)}">
          ${score ? `<span class="-suggest-score">${esc(String(Math.round(score)))}</span>` : ""}
          <span class="-suggest-label">${esc(label)}</span>
          ${meta ? `<span class="-muted">${esc(meta)}</span>` : ""}
        </button>`;
      })
      .join("");
    box.classList.remove("hidden");
    box.querySelectorAll(".-link-target-opt").forEach((btn) => {
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
      const block = linkEl.closest("[data--src-line]");
      if (block) line = Number(block.dataset.SrcLine) || 0;
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
    if (_brush) return; // 画笔模式下不跳转，避免涂抹时误触链接
    const target = el.dataset.linkTarget;
    const type = el.dataset.linkType || "";
    if (!target) return;
    if (el.classList.contains("-link-broken")) {
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
    const isBroken = linkEl.classList.contains("-link-broken");
    const multiRaw = linkEl.dataset.linkTargets;
    let isMulti = linkEl.classList.contains("-link-multi");
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

  function postProcessWikilinks() {
    const preview = $("#preview");
    if (!preview) return;
    const lookup = state.linkTargetSet;
    const hasLookup = lookup instanceof Set;
    preview.querySelectorAll(".-wikilink").forEach((el) => {
      const target = el.getAttribute("data--target") || "";
      el.classList.add("memoria-link");
      el.setAttribute("role", "link");
      el.setAttribute("data-link-target", target);
      el.setAttribute("data-link-type", "");
      const blockEl = el.closest("[data--src-line]");
      const line = blockEl ? Number(blockEl.getAttribute("data--src-line")) || 0 : 0;
      el.setAttribute("data-link-line", String(line));
      if (hasLookup) {
        if (lookup.has(target)) {
          el.classList.add("-link-resolved");
          el.setAttribute("tabindex", "0");
          el.setAttribute("title", "跳转到 " + target);
        } else {
          el.classList.add("-link-broken", "memoria-broken-link");
          el.setAttribute("tabindex", "-1");
          el.setAttribute("title", "未绑定目标: " + target);
        }
      } else {
        el.classList.add("-link-pending");
        el.setAttribute("tabindex", "0");
      }
    });
  }

  function bindPreviewLinks() {
    const preview = $("#preview");
    if (!preview) return;
    // 仅绑定未绑定过的元素，避免增量渲染时对旧链接重复绑定事件
    preview.querySelectorAll(".memoria-link:not([data--bound])").forEach((el) => {
      el.setAttribute("data--bound", "1");
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
        : ' <span class="-muted">（目标未入图谱）</span>';
    hint.innerHTML = `<span class="-muted">链接</span> ${esc(src)} → ${esc(tgt)}${note}`;
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
      const row = e.target.closest(".-line");
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
      const block = el.closest?.("[data--src-line]");
      if (block && container.contains(block)) return +(block.dataset.SrcLine || 0);
      el = el.parentElement;
    }
    return 0;
  }

  function previewLinesInRange(preview, lo, hi) {
    const lines = new Set();
    preview.querySelectorAll("[data--src-line]").forEach((el) => {
      const s = +(el.dataset.SrcLine || 0);
      const e = +(el.dataset.SrcLineEnd || s);
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

  /** 聚焦源码编辑器的指定行（单击预览区域时调用） */
  function focusSourceLine(lineNum) {
    const lineEl = document.getElementById("line-" + lineNum);
    if (!lineEl) return;
    const content = lineEl.querySelector(".-line-content");
    if (!content) return;
    // 滚动到该行
    const editorPane = $("#editor-pane");
    if (editorPane) {
      const containerTop = editorPane.getBoundingClientRect().top;
      editorPane.scrollTop += lineEl.getBoundingClientRect().top - containerTop - editorPane.clientHeight / 3;
    }
    // 聚焦并放置光标
    content.focus();
    // 将光标放到行尾
    const range = document.createRange();
    const sel = window.getSelection();
    if (content.childNodes.length > 0) {
      range.selectNodeContents(content);
      range.collapse(false); // 折叠到末尾
    } else {
      range.setStart(content, 0);
      range.collapse(true);
    }
    sel.removeAllRanges();
    sel.addRange(range);
    syncLog("focusSourceLine: 聚焦行", lineNum);
  }

  /** 选中源码编辑器的行范围（拖选/双击预览区域时调用） */
  function selectSourceLines(lo, hi) {
    const startEl = document.getElementById("line-" + lo);
    const endEl = document.getElementById("line-" + hi);
    if (!startEl || !endEl) return;
    const startContent = startEl.querySelector(".-line-content");
    const endContent = endEl.querySelector(".-line-content");
    if (!startContent || !endContent) return;
    // 滚动到起始行
    const editorPane = $("#editor-pane");
    if (editorPane) {
      const containerTop = editorPane.getBoundingClientRect().top;
      editorPane.scrollTop += startEl.getBoundingClientRect().top - containerTop - editorPane.clientHeight / 3;
    }
    const range = document.createRange();
    range.setStart(startContent, 0);
    if (endContent.childNodes.length > 0) {
      range.setEnd(endContent, endContent.childNodes.length);
    } else {
      range.setEnd(endContent, 0);
    }
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    startContent.focus();
    syncLog("selectSourceLines: 选中行", lo, "→", hi);
  }

  function applyPreviewTextSelection(preview, anchorLine, focusLine) {
    const lo = Math.min(anchorLine, focusLine);
    const hi = Math.max(anchorLine, focusLine);
    const blocks = [...preview.querySelectorAll(".-src-block")]
      .filter((el) => {
        const s = +(el.dataset.SrcLine || 0);
        const e = +(el.dataset.SrcLineEnd || s);
        return e >= lo && s <= hi;
      })
      .sort((a, b) => +(a.dataset.SrcLine || 0) - +(b.dataset.SrcLine || 0));
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
    preview.querySelectorAll(".-src-block.is-drag-select").forEach((el) => {
      el.classList.remove("is-drag-select");
    });
    preview.querySelectorAll(".-src-block").forEach((el) => {
      const s = +(el.dataset.SrcLine || 0);
      const e = +(el.dataset.SrcLineEnd || s);
      if (e >= lo && s <= hi) el.classList.add("is-drag-select");
    });
  }

  function clearPreviewDragSelect(preview) {
    preview.querySelectorAll(".-src-block.is-drag-select").forEach((el) => {
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
    const startEl = document.querySelector(`#line-${lo} .-line-content`);
    const endEl = document.querySelector(`#line-${hi} .-line-content`);
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
    document.querySelectorAll("#editor .-line.is-drag-select").forEach((el) => {
      el.classList.remove("is-drag-select");
    });
    for (let n = lo; n <= hi; n++) {
      document.getElementById("line-" + n)?.classList.add("is-drag-select");
    }
  }

  function clearEditorDragSelectLines() {
    document.querySelectorAll("#editor .-line.is-drag-select").forEach((el) => {
      el.classList.remove("is-drag-select");
    });
  }

  /** 聚焦到指定行内容并设置光标位置 */
  function focusLineContent(contentEl, col) {
    contentEl.focus();
    var textNode = contentEl.firstChild;
    if (!textNode || textNode.nodeType !== 3) {
      // 没有 text node（空行有 <br>）→ 在元素开头放置
      var range = document.createRange();
      range.setStart(contentEl, 0);
      range.collapse(true);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      return;
    }
    var safeCol = Math.min(Math.max(0, col), textNode.textContent.length);
    var range = document.createRange();
    range.setStart(textNode, safeCol);
    range.collapse(true);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  /** 从节点向上查找最近的 .-line 行元素 */
  function closestLineEl(node) {
    let el = node;
    while (el && el !== document.body) {
      if (el.classList && el.classList.contains("-line")) return el;
      el = el.parentNode;
    }
    return null;
  }

  /** 计算 node+offset 相对所在行内容元素 textContent 的字符偏移 */
  function offsetWithinLine(node, offset, contentEl) {
    if (!node) return 0;
    let total = 0;
    let cur = node;
    while (cur && cur !== contentEl) {
      let s = cur.previousSibling;
      while (s) {
        total += s.nodeType === Node.TEXT_NODE ? s.textContent.length : (s.textContent || "").length;
        s = s.previousSibling;
      }
      cur = cur.parentNode;
    }
    return total + (offset || 0);
  }

  /** 跨行/跨 block 删除选区：保留首行前段 + 末行后段，删除中间所有行并重编号 */
  function deleteCrossLineSelection(anchorLineEl, focusLineEl) {
    const sel = window.getSelection();
    const aNum = +(anchorLineEl.dataset.line || 0);
    const fNum = +(focusLineEl.dataset.line || 0);
    const loEl = aNum <= fNum ? anchorLineEl : focusLineEl;
    const hiEl = aNum <= fNum ? focusLineEl : anchorLineEl;
    const anchorFirst = aNum <= fNum;
    const loContent = loEl.querySelector(".-line-content");
    const hiContent = hiEl.querySelector(".-line-content");
    if (!loContent || !hiContent) return;

    const loText = loContent.textContent;
    const hiText = hiContent.textContent;
    const loOff = Math.min(
      offsetWithinLine(anchorFirst ? sel.anchorNode : sel.focusNode,
        anchorFirst ? sel.anchorOffset : sel.focusOffset, loContent),
      loText.length);
    const hiOff = Math.min(
      offsetWithinLine(anchorFirst ? sel.focusNode : sel.anchorNode,
        anchorFirst ? sel.focusOffset : sel.anchorOffset, hiContent),
      hiText.length);
    const head = loText.slice(0, loOff);
    const tail = hiText.slice(hiOff);

    loContent.textContent = head + tail;
    if (!loContent.textContent) loContent.innerHTML = "<br>";

    // 删除中间行与末行
    let el = loEl.nextElementSibling;
    while (el && el !== hiEl) {
      const next = el.nextElementSibling;
      el.remove();
      el = next;
    }
    hiEl.remove();

    renumberSourceLines();
    _srcAfterEdit();

    // 光标放到合并处
    const caretCol = head.length;
    const textNode = loContent.firstChild;
    if (textNode && textNode.nodeType === Node.TEXT_NODE) {
      const range = document.createRange();
      range.setStart(textNode, Math.min(caretCol, textNode.textContent.length));
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    } else {
      focusLineContent(loContent, caretCol);
    }

    scheduleRenderSync();
    markDirty();
  }

  /** 源码区编辑报告：记录到同步日志（源码编辑暂不并入预览区撤销栈） */
  function editReport(kind, line, offset, op, text) {
    syncLog("srcEdit:", op, "line=" + line, "offset=" + offset, "text=" + JSON.stringify((text || "").slice(0, 40)));
  }

  // ── 源码编辑器撤销/重做（快照式，覆盖输入/Enter/合并删除/粘贴）──
  let _srcUndoStack = [];
  let _srcRedoStack = [];
  let _srcLastBody = null;   // 最近一次编辑完成后的正文，用作「操作前」状态
  let _srcCoalesceAt = 0;    // 连续输入合并：时间戳 + 行号
  let _srcCoalesceLine = -1;
  let _srcPasting = false;   // 粘贴处理中：input 事件不再入栈
  let _srcComposing = false; // IME 组合中：input 事件不再入栈

  /** 读取源码编辑器当前光标（行/列） */
  function _srcCaret() {
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount || !sel.anchorNode) return { line: 1, col: 0 };
    const lineEl = closestLineEl(sel.anchorNode);
    if (!lineEl) return { line: 1, col: 0 };
    const content = lineEl.querySelector(".-line-content");
    const len = content ? (content.textContent || "").length : 0;
    let col = sel.anchorOffset;
    if (col > len) col = len;
    return { line: +(lineEl.dataset.line || 1), col };
  }

  /** 编辑前入栈（对比上次快照，正文未变则跳过；结构编辑后重置输入合并） */
  function _srcPushBefore() {
    if (_srcLastBody === null) _srcLastBody = collectEditorBody() || "";
    const last = _srcUndoStack[_srcUndoStack.length - 1];
    if (!last || last.body !== _srcLastBody) {
      _srcUndoStack.push({ body: _srcLastBody, caret: _srcCaret() });
      if (_srcUndoStack.length > 300) _srcUndoStack.shift();
    }
    _srcRedoStack.length = 0;
  }

  /** 编辑完成后刷新基线正文 */
  function _srcAfterEdit() {
    _srcLastBody = collectEditorBody() || "";
  }

  /** 应用快照：重写编辑器 DOM + 预览 + 恢复光标 */
  async function _srcApplySnapshot(snap) {
    if (!state.currentPath) return;
    state.doc.body = snap.body;
    state.doc.lines = snap.body.split("\n");
    state.doc.preview_body = null;
    renderEditor(state.doc);
    await renderPreview(state.doc);
    _srcAfterEdit();
    _srcCoalesceAt = 0;
    const lineEl = document.getElementById("line-" + snap.caret.line);
    if (lineEl) {
      const content = lineEl.querySelector(".-line-content");
      if (content) {
        focusLineContent(content, Math.min(snap.caret.col, (content.textContent || "").length));
      }
    }
    markDirty();
  }

  function _srcUndo() {
    if (!_srcUndoStack.length) return false;
    _srcRedoStack.push({ body: _srcLastBody, caret: _srcCaret() });
    const snap = _srcUndoStack.pop();
    _srcApplySnapshot(snap);
    return true;
  }

  function _srcRedo() {
    if (!_srcRedoStack.length) return false;
    _srcUndoStack.push({ body: _srcLastBody, caret: _srcCaret() });
    const snap = _srcRedoStack.pop();
    _srcApplySnapshot(snap);
    return true;
  }

  /** 打开新文件 / 重渲染编辑器时清空源码撤销历史并重建基线 */
  function srcResetUndo() {
    _srcUndoStack = [];
    _srcRedoStack = [];
    _srcCoalesceAt = 0;
    _srcCoalesceLine = -1;
    _srcLastBody = collectEditorBody() || "";
  }

  /** 按 DOM 顺序重排全部行号（data-line / id / 行号 span），保证连续且无重复 id */
  function renumberSourceLines() {
    const els = document.querySelectorAll("#editor .-line");
    els.forEach((el, i) => {
      const n = i + 1;
      el.dataset.line = String(n);
      el.id = "line-" + n;
      const lineno = el.querySelector(".-lineno");
      if (lineno) lineno.textContent = String(n);
    });
  }

  function bindEditorSelectInteraction() {
    const editor = $("#editor");
    if (!editor || editor.dataset.selectBound) return;
    editor.dataset.selectBound = "1";

    let dragSelect = null;

    // 源码编辑时：实时同步预览 + 标记脏
    editor.addEventListener("input", (e) => {
      const content = e.target.closest(".-line-content");
      if (!content) return;
      // 有文字时清除占位 <br>，无文字时补回
      if (content.textContent && content.querySelector("br")) {
        content.innerHTML = content.textContent;
      } else if (!content.textContent && !content.querySelector("br")) {
        content.innerHTML = "<br>";
      }
      // 撤销快照：连续输入（同行、短间隔）合并为一个撤销单元
      if (!_srcPasting && !_srcComposing) {
        const lineNow = +(content.closest("[data-line]")?.dataset.line || 0);
        const now = Date.now();
        if (!(_srcCoalesceAt && now - _srcCoalesceAt < 1200 && _srcCoalesceLine === lineNow)) {
          _srcPushBefore();
        }
        _srcCoalesceAt = now;
        _srcCoalesceLine = lineNow;
      }
      _srcAfterEdit();
      syncLog("editor input: 源码编辑触发, 目标行:", content.closest("[data-line]")?.dataset.line);
      scheduleRenderSync();
      markDirty();
    });

    // 源码编辑器：Backspace/Delete/Enter 行级操作
    editor.addEventListener("keydown", (e) => {
      const content = e.target.closest(".-line-content");
      if (!content) return;
      const lineEl = content.closest("[data-line]");
      if (!lineEl) return;
      const line = +(lineEl.dataset.line || 0);
      if (!line) return;

      // Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z：源码编辑器快照式撤销/重做
      if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "z" || e.key.toLowerCase() === "y")) {
        e.preventDefault();
        if (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey)) {
          _srcRedo();
        } else {
          _srcUndo();
        }
        return;
      }

      const sel = window.getSelection();
      if (!sel?.rangeCount) return;

      // 非折叠选区：单行内交由浏览器原生删除；跨行/跨 block 选区由本处理器合并删除
      if (!sel.isCollapsed) {
        if (e.key === "Backspace" || e.key === "Delete") {
          const anchorLineEl = closestLineEl(sel.anchorNode);
          const focusLineEl = closestLineEl(sel.focusNode);
          if (anchorLineEl && focusLineEl && anchorLineEl !== focusLineEl) {
            e.preventDefault();
            _srcPushBefore();
            _srcCoalesceAt = 0;
            deleteCrossLineSelection(anchorLineEl, focusLineEl);
            return;
          }
        }
        return;
      }

      const text = content.textContent;
      const offset = sel.anchorOffset;

      // 光标移动键：跨行处理
      if (["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.key)) {
        // 跨行方向键：每个 .-line-content 是独立 contenteditable，浏览器无法跨行
        if (e.key === "ArrowDown") {
          e.preventDefault();
          const nextLineEl = document.getElementById("line-" + (line + 1));
          if (nextLineEl) {
            const nextContent = nextLineEl.querySelector(".-line-content");
            if (nextContent) {
              const col = Math.min(offset, (nextContent.textContent || "").length);
              focusLineContent(nextContent, col);
            }
          }
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          const prevLineEl = document.getElementById("line-" + (line - 1));
          if (prevLineEl) {
            const prevContent = prevLineEl.querySelector(".-line-content");
            if (prevContent) {
              const col = Math.min(offset, (prevContent.textContent || "").length);
              focusLineContent(prevContent, col);
            }
          }
        } else if (e.key === "ArrowLeft" && offset === 0) {
          e.preventDefault();
          const prevLineEl = document.getElementById("line-" + (line - 1));
          if (prevLineEl) {
            const prevContent = prevLineEl.querySelector(".-line-content");
            if (prevContent) {
              focusLineContent(prevContent, (prevContent.textContent || "").length);
            }
          }
        } else if (e.key === "ArrowRight" && offset >= text.length) {
          e.preventDefault();
          const nextLineEl = document.getElementById("line-" + (line + 1));
          if (nextLineEl) {
            const nextContent = nextLineEl.querySelector(".-line-content");
            if (nextContent) {
              focusLineContent(nextContent, 0);
            }
          }
        }
      }

      if (e.key === "Backspace" && offset === 0) {
        // 行首退格：合并到上一行（或删除空行）
        const prevLineEl = document.getElementById("line-" + (line - 1));
        if (!prevLineEl) return;
        e.preventDefault();
        _srcPushBefore();
        _srcCoalesceAt = 0;
        editReport("srcEdit", line, offset, "deleteBack-lineStart", text);
        const prevContent = prevLineEl.querySelector(".-line-content");
        if (!prevContent) return;
        const prevText = prevContent.textContent;
        prevContent.textContent = prevText + text;
        // 合并后若无内容补回 <br>，确保光标能定位
        if (!prevContent.textContent) prevContent.innerHTML = "<br>";
        lineEl.remove();
        renumberSourceLines(line);
        _srcAfterEdit();
        // 光标移到合并位置
        const targetNode = prevContent.firstChild;
        if (targetNode) {
          const range = document.createRange();
          range.setStart(targetNode, Math.min(prevText.length, targetNode.textContent?.length || 0));
          range.collapse(true);
          sel.removeAllRanges();
          sel.addRange(range);
        }
        scheduleRenderSync();
        markDirty();
      } else if (e.key === "Delete" && offset >= text.length) {
        // 行末 Delete：合并下一行
        const nextLineEl = document.getElementById("line-" + (line + 1));
        if (!nextLineEl) return;
        e.preventDefault();
        _srcPushBefore();
        _srcCoalesceAt = 0;
        editReport("srcEdit", line, offset, "deleteForward-lineEnd", text);
        const nextContent = nextLineEl.querySelector(".-line-content");
        if (!nextContent) return;
        content.textContent = text + nextContent.textContent;
        // 保持空行有 <br>
        if (!content.textContent) content.innerHTML = "<br>";
        nextLineEl.remove();
        renumberSourceLines(line + 1);
        _srcAfterEdit();
        scheduleRenderSync();
        markDirty();
      } else if (e.key === "Enter") {
        e.preventDefault();
        _srcPushBefore();
        _srcCoalesceAt = 0;
        editReport("srcEdit", line, offset, "Enter", text);

        // 光标在标题前缀末尾（如 "### |标题"）：不拆标题，改为在行前插入空行
        const headingMatch = text.match(/^(#{1,6}\s)/);
        if (headingMatch && offset === headingMatch[1].length) {
          // 在当前行前插入空行
          const newLineEl = document.createElement("div");
          newLineEl.className = "-line";
          newLineEl.dataset.line = String(line);
          newLineEl.id = "line-" + line;
          const newLineno = document.createElement("span");
          newLineno.className = "-lineno";
          const newLineContent = document.createElement("span");
          newLineContent.className = "-line-content";
          newLineContent.contentEditable = "true";
          newLineContent.spellcheck = false;
          newLineContent.tabIndex = -1;
          newLineContent.innerHTML = "<br>";
          newLineEl.appendChild(newLineno);
          newLineEl.appendChild(newLineContent);
          lineEl.before(newLineEl);
          renumberSourceLines(line);
          _srcAfterEdit();
          // 光标留在新空行中
          const br = newLineContent.querySelector("br");
          if (br) {
            const range = document.createRange();
            range.setStartBefore(br);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
          }
          scheduleRenderSync();
          markDirty();
          return;
        }

        // Enter：分割行
        const before = text.slice(0, offset);
        const after = text.slice(offset);
        content.textContent = before;
        if (!before) content.innerHTML = "<br>";
        const newNum = line + 1;
        const newLineEl = document.createElement("div");
        newLineEl.className = "-line";
        newLineEl.dataset.line = String(newNum);
        newLineEl.id = "line-" + newNum;
        const newLineno = document.createElement("span");
        newLineno.className = "-lineno";
        newLineno.textContent = String(newNum);
        const newLineContent = document.createElement("span");
        newLineContent.className = "-line-content";
        newLineContent.contentEditable = "true";
        newLineContent.spellcheck = false;
        newLineContent.tabIndex = -1;
        newLineContent.textContent = after;
        if (!after) newLineContent.innerHTML = "<br>";
        newLineEl.appendChild(newLineno);
        newLineEl.appendChild(newLineContent);
        lineEl.after(newLineEl);
        renumberSourceLines(newNum + 1);
        _srcAfterEdit();
        // 光标移到新行开头
        const range = document.createRange();
        const firstText = newLineContent.firstChild;
        if (firstText) {
          range.setStart(firstText, firstText.nodeType === Node.TEXT_NODE ? 0 : 0);
          range.collapse(true);
          sel.removeAllRanges();
          sel.addRange(range);
        }
        scheduleRenderSync();
        markDirty();
      }
    });

    editor.addEventListener("drop", (e) => {
      if (e.target.closest(".-line-content")) e.preventDefault();
    });

    // 粘贴多行文本：逐行拆分插入。contenteditable 原生粘贴会把换行压成 <br>/<div>，
    // 而 input 处理器会用 textContent 压平 → 换行丢失；这里手动拆分并插入新行。
    // 右键「粘贴」菜单也复用本函数（原生 paste 事件无法程序化构造 clipboardData）。
    editor.addEventListener("paste", (e) => {
      const t = e.target;
      const contentEl = t && t.closest ? t.closest(".-line-content") : null;
      if (!contentEl || !editor.contains(contentEl)) return;
      const clip = e.clipboardData || window.clipboardData;
      if (!clip) return;
      const raw = clip.getData("text/plain");
      if (raw === null || raw === undefined) return;
      e.preventDefault();
      applyEditorPaste(raw, contentEl);
    });

    /**
     * 多行文本粘贴核心：读剪贴板文本 → 逐行拆分插入源码编辑器。
     * 由原生 paste 事件与右键「粘贴」菜单共用。
     * @param {string} raw 剪贴板纯文本
     * @param {HTMLElement} contentEl 目标 .-line-content
     */
    function applyEditorPaste(raw, contentEl) {
      // 粘贴整体作为一个撤销单元：先入栈（正文未变），期间 input 事件不再入栈
      _srcPushBefore();
      _srcCoalesceAt = 0;
      _srcPasting = true;
      const parts = raw.replace(/\r\n?/g, "\n").split("\n");
      let curLineEl = contentEl.closest("[data-line]");
      let cur = contentEl;
      const sel = window.getSelection();
      // 跨行选区：先合并删除，再在合并点上粘贴
      if (sel && !sel.isCollapsed && sel.anchorNode && sel.focusNode) {
        const a = closestLineEl(sel.anchorNode);
        const b = closestLineEl(sel.focusNode);
        if (a && b && a !== b) {
          deleteCrossLineSelection(a, b);
          curLineEl = a;
          cur = a.querySelector(".-line-content");
        }
      }
      // 首段替换当前（折叠）光标/选区
      const range = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
      if (range) {
        range.deleteContents();
        sel.removeAllRanges();
        sel.addRange(range);
      }
      if (parts[0]) {
        const ok = document.execCommand("insertText", false, parts[0]);
        if (!ok) {
          // 兜底（编辑器未聚焦等）：手动替换当前选区，避免首段静默丢失
          const r2 = sel && sel.rangeCount ? sel.getRangeAt(0) : null;
          if (r2) {
            const tn = document.createTextNode(parts[0]);
            r2.deleteContents();
            r2.insertNode(tn);
            r2.setStartAfter(tn);
            r2.collapse(true);
            sel.removeAllRanges();
            sel.addRange(r2);
          }
        }
      }
      // 其余段各占一个新行
      let lastLineNum = +(curLineEl?.dataset.line || 0);
      for (let i = 1; i < parts.length; i++) {
        lastLineNum += 1;
        const newLineEl = document.createElement("div");
        newLineEl.className = "-line";
        newLineEl.dataset.line = String(lastLineNum);
        newLineEl.id = "line-" + lastLineNum;
        const newLineno = document.createElement("span");
        newLineno.className = "-lineno";
        newLineno.textContent = String(lastLineNum);
        const newLineContent = document.createElement("span");
        newLineContent.className = "-line-content";
        newLineContent.contentEditable = "true";
        newLineContent.spellcheck = false;
        newLineContent.tabIndex = -1;
        newLineContent.textContent = parts[i];
        if (!parts[i]) newLineContent.innerHTML = "<br>";
        newLineEl.appendChild(newLineno);
        newLineEl.appendChild(newLineContent);
        if (curLineEl) curLineEl.after(newLineEl);
        curLineEl = newLineEl;
        cur = newLineContent;
      }
      if (parts.length > 1) renumberSourceLines(lastLineNum + 1);
      _srcPasting = false;
      _srcAfterEdit();
      // 光标移到末尾
      if (cur) {
        const r = document.createRange();
        const node = cur.firstChild;
        if (node) {
          r.setStart(node, node.nodeType === Node.TEXT_NODE ? node.textContent.length : 0);
          r.collapse(true);
          sel.removeAllRanges();
          sel.addRange(r);
        }
      }
      scheduleRenderSync();
      markDirty();
    }

    /** 右键「粘贴」：读剪贴板后复用 applyEditorPaste（合成 ClipboardEvent 的 clipboardData 只读，不可伪造） */
    async function pasteAtSourceEditor() {
      let text = "";
      try {
        text = (await navigator.clipboard.readText()) || "";
      } catch (_) {
        text = "";
      }
      if (!text) {
        setStatus("剪贴板为空或无法读取");
        return;
      }
      const sel = window.getSelection();
      let content = null;
      if (sel && sel.anchorNode) {
        const an = sel.anchorNode;
        content = an.nodeType === Node.TEXT_NODE
          ? (an.parentElement ? an.parentElement.closest(".-line-content") : null)
          : (an.closest ? an.closest(".-line-content") : null);
      }
      if (!content || !editor.contains(content)) {
        setStatus("请先将光标置于源码编辑区");
        return;
      }
      applyEditorPaste(text, content);
    }

    // 源码编辑器右键：无选中文本 → 提供「粘贴」菜单
    // （全局捕获阶段已屏蔽原生右键菜单；有选区时交还 bindEditorSelectionMenu 弹链接/知识点菜单）
    editor.addEventListener("contextmenu", (e) => {
      if (!state.currentPath) return;
      if (!(e.target && e.target.closest && e.target.closest(".-line-content"))) return;
      const info = getSelectionInContainer(editor);
      if (info) return;
      e.preventDefault();
      MemoriaLinkContextMenu.showForCursor(e, {
        onPaste: pasteAtSourceEditor,
      });
    });

    // IME 组合输入期间：input 事件不单独入栈，组合整体由 compositionend 后的状态兜底
    editor.addEventListener("compositionstart", () => { _srcComposing = true; });
    editor.addEventListener("compositionend", () => { _srcComposing = false; });

    editor.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      const content = e.target.closest(".-line-content");
      if (!content) return;
      const line = +(content.closest("[data-line]")?.dataset.line || 0);
      if (!line) return;
      dragSelect = { anchorLine: line, focusLine: line };
    });

    editor.addEventListener("mousemove", (e) => {
      if (!dragSelect || e.buttons !== 1) return;
      const row = e.target.closest(".-line");
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
      const content = e.target.closest(".-line-content");
      if (!content) return;
      const line = +(content.closest("[data-line]")?.dataset.line || 0);
      if (!line) return;
      e.preventDefault();
      applyEditorTextSelection(line, line);
    });
  }

  // ═══════════════════════════════════════════════════════════
  //  PREVIEW EDITING — AST-based, built feature by feature
  // ═══════════════════════════════════════════════════════════

  // ── Logging ──
  const MAP_LOG = true;
  let _logBuf = [];
  let _logTimer = null;
  const LOG_FILE = "mapping-debug.log";

  function ts() { const d = new Date(); return "[" + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + ":" + String(d.getSeconds()).padStart(2, "0") + "." + String(d.getMilliseconds()).padStart(3, "0") + "]"; }
  function log(tag, msg) { if (!MAP_LOG) return; const l = ts() + " [" + tag + "] " + msg; console.log(l); _logBuf.push(l); _scheduleFlush(); }
  function _scheduleFlush() { if (_logTimer) clearTimeout(_logTimer); _logTimer = setTimeout(_flushNow, 300); }
  function _flushNow() { if (_logTimer) { clearTimeout(_logTimer); _logTimer = null; } if (!_logBuf.length) return; const c = _logBuf.join("\n") + "\n"; _logBuf = []; call("write_map_log", LOG_FILE, c).catch(function () { }); }
  window.addEventListener("beforeunload", function () { _flushNow(); });
  window.log = log;  // 导出给 edit-handler.js 等外部模块使用

  // ── AST pipeline shortcuts ──
  const L = window.MemoriaLexer;
  const P = window.MemoriaParser;
  const G = window.MemoriaSourceGen;
  const M = window.MemoriaMapper;
  const R = window.MemoriaRenderer;
  const A = window.MemoriaAST;

  // ── Current AST document ──
  let _doc = null;

  /**
   * F1: AST-based preview rendering.
   * Parses source body → AST → renders to DOM.
   * No contenteditable, no cursor, just display.
   */
  function renderPreviewAST(body) {
    if (!P || !R || !M) { log("F1", "modules missing"); return null; }
    const t0 = performance.now();
    _doc = P.parse(body || "");
    M.setDoc(_doc);
    const preview = $("#preview");
    if (!preview) return null;
    const content = R.render(_doc);
    preview.innerHTML = "";
    preview.appendChild(content);
    log("F1", "rendered " + _doc.blocks.length + " blocks in " + (performance.now() - t0).toFixed(1) + "ms");
    return _doc;
  }

  // ════════════════════════════════════════════════════════════════
  //  预览 → 源码 编辑同步（AST 锚点编辑管线）
  //  beforeinput 拦截 → 修改 AST → 反向生成源码 → 增量渲染 → 恢复光标
  // ════════════════════════════════════════════════════════════════
  window.MemoriaEditSync = (function () {
    "use strict";

    // ── 独立撤销/重做日志：单独写 undo-debug.log，避免与 mapping 日志混杂 ──
    var _hlogBuf = [];
    var _hlogTimer = null;
    function hlog(msg) {
      var line = ts() + " [UNDO] " + msg;
      console.log(line);
      _hlogBuf.push(line);
      if (_hlogTimer) clearTimeout(_hlogTimer);
      _hlogTimer = setTimeout(_hlogFlush, 300);
    }
    function _hlogFlush() {
      if (_hlogTimer) { clearTimeout(_hlogTimer); _hlogTimer = null; }
      if (!_hlogBuf.length) return;
      var c = _hlogBuf.join("\n") + "\n";
      _hlogBuf = [];
      call("write_map_log", "undo-debug.log", c).catch(function () { });
    }
    window.addEventListener("beforeunload", function () { _hlogFlush(); });

    var NON_EDITABLE = { code_block: 1, math_block: 1, mermaid: 1, table: 1, frontmatter: 1 };

    /** 用新 block 源码替换该 block 对应的原始源码行，更新 state.doc.body/lines */
    function spliceBlockSource(blockIndex, newBlockSrc) {
      var rawLines = (state.doc.body || "").split("\n");
      var range = (_blockLineMap && _blockLineMap[blockIndex]) || null;
      var start = range ? range.startLine : 0;
      var end = range ? range.endLine : (rawLines.length - 1);
      var newLines = newBlockSrc.split("\n");
      var merged = rawLines.slice(0, start).concat(newLines, rawLines.slice(end + 1));
      state.doc.body = merged.join("\n");
      state.doc.lines = merged;
    }

    /** 增量重渲染预览中的单个 block，并重建 block→源行映射 */
    function reRenderBlock(blockIndex) {
      var preview = $("#preview");
      if (!preview) return;
      var container = preview.querySelector(".-preview-content") || preview;
      R.renderRange(_doc, blockIndex, blockIndex + 1, container);
      stampBlockLines(preview, _doc);
      // 增量渲染替换了 block DOM：.-math span 是新节点，需重新触发 MathJax 排版，
      // 否则行内公式会以裸文本显示（样式应用/笔刷后“公式预览失败”，全量刷新才恢复）
      if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
        try { window.MathJax.typesetPromise([container]); } catch (e) { }
      }
      // 增量渲染出的新 block 里可能有 wikilink，需重新做后处理并绑定跳转事件
      postProcessWikilinks();
      bindPreviewLinks();
    }

    /** 恢复预览区光标到 AST 坐标 */
    function restoreCursor(blockIndex, nodePath, offset) {
      hlog("restoreCursor bi=" + blockIndex + " path=[" + (nodePath || []).join(",") + "] off=" + offset);
      var range = M.astToDom(blockIndex, nodePath, offset);
      if (!range) { hlog("restoreCursor -> FAIL (no range)"); return; }
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      // 同步 EH.cursorAST，避免后续 undo/redo 的 currentSnapshot 读到过期光标
      var EH = window.MemoriaEditHandler;
      if (EH) {
        EH.cursorAST = {
          blockIndex: blockIndex,
          nodePath: (nodePath || []).slice(),
          offset: offset,
        };
      }
    }

    /** 恢复预览区「非折叠选区」（用于样式应用后保持文字仍被选中） */
    function restoreSelection(blockIndex, startNodePath, startOffset, endNodePath, endOffset) {
      var startCursor = { blockIndex: blockIndex, nodePath: startNodePath, offset: startOffset };
      var endCursor = { blockIndex: blockIndex, nodePath: endNodePath, offset: endOffset };
      log("STYLE", "restoreSelection AST start=" + _fmtCursor(startCursor) + " end=" + _fmtCursor(endCursor));
      var startRange = M.astToDom(blockIndex, startNodePath, startOffset);
      var endRange = M.astToDom(blockIndex, endNodePath, endOffset);
      log("STYLE", "restoreSelection DOM start=" + _describeDomPos(startRange) + " end=" + _describeDomPos(endRange));
      if (!startRange || !endRange) {
        // 兜底：无法建立选区时退化为折叠光标
        log("STYLE", "restoreSelection FALLBACK start=" + _fmtCursor(startCursor) +
          " end=" + _fmtCursor(endCursor) +
          " startRange=" + (startRange ? "ok" : "null") + " endRange=" + (endRange ? "ok" : "null"));
        return restoreCursor(blockIndex, endNodePath, endOffset);
      }
      var range = document.createRange();
      range.setStart(startRange.startContainer, startRange.startOffset);
      range.setEnd(endRange.startContainer, endRange.startOffset);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      log("STYLE", "restoreSelection ok [" + startRange.startContainer.nodeName + ":" + startRange.startOffset + "] -> [" + endRange.startContainer.nodeName + ":" + endRange.startOffset + "]");
      // 同步 EH.cursorAST 到选区末尾，作为后续编辑锚点
      var EH = window.MemoriaEditHandler;
      if (EH) {
        EH.cursorAST = {
          blockIndex: blockIndex,
          nodePath: (endNodePath || []).slice(),
          offset: endOffset,
        };
      }
      return true;
    }

    /**
     * 恢复预览区「跨 block 非折叠选区」（用于跨段落样式应用后保持文字仍被选中）。
     * startBlockIndex/endBlockIndex 可不同；若任一端无法建立，退化为折叠光标到选区末尾。
     */
    function restoreSelectionMulti(startBlockIndex, startNodePath, startOffset, endBlockIndex, endNodePath, endOffset) {
      var startRange = M.astToDom(startBlockIndex, startNodePath, startOffset);
      var endRange = M.astToDom(endBlockIndex, endNodePath, endOffset);
      if (!startRange || !endRange) {
        log("STYLE", "restoreSelectionMulti FALLBACK start=" + _fmtCursor({ blockIndex: startBlockIndex, nodePath: startNodePath, offset: startOffset }) +
          " end=" + _fmtCursor({ blockIndex: endBlockIndex, nodePath: endNodePath, offset: endOffset }) +
          " startRange=" + (startRange ? "ok" : "null") + " endRange=" + (endRange ? "ok" : "null"));
        return restoreCursor(endBlockIndex, endNodePath, endOffset);
      }
      var range = document.createRange();
      range.setStart(startRange.startContainer, startRange.startOffset);
      range.setEnd(endRange.startContainer, endRange.startOffset);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      log("STYLE", "restoreSelectionMulti ok [" + startRange.startContainer.nodeName + ":" + startRange.startOffset + "] -> [" + endRange.startContainer.nodeName + ":" + endRange.startOffset + "]");
      // 同步 EH.cursorAST 到选区末尾，作为后续编辑锚点
      var EH = window.MemoriaEditHandler;
      if (EH) {
        EH.cursorAST = {
          blockIndex: endBlockIndex,
          nodePath: (endNodePath || []).slice(),
          offset: endOffset,
        };
      }
      return true;
    }

    /**
     * 解析光标 AST 坐标 → 目标节点及其父级 children 数组与下标
     * @returns {{node:object|null, parentChildren:Array|null, index:number, innerPath:number[]}|null}
     */
    function resolveNode(block, cursor) {
      var root, path;
      if (block.type === "list") {
        var itemIdx = (cursor.nodePath && cursor.nodePath.length) ? cursor.nodePath[0] : 0;
        var item = block.items && block.items[itemIdx];
        if (!item) return null;
        root = item.children || [];
        path = (cursor.nodePath || []).slice(1);
      } else {
        root = block.children || [];
        path = cursor.nodePath || [];
      }

      if (!path.length) {
        return { node: null, parentChildren: root, index: -1, innerPath: [] };
      }

      var parentChildren = root;
      var node = null;
      var index = -1;
      for (var j = 0; j < path.length; j++) {
        node = parentChildren[path[j]];
        if (!node) return null;
        index = path[j];
        if (j < path.length - 1) parentChildren = node.children || [];
      }

      return { node: node, parentChildren: parentChildren, index: index, innerPath: path };
    }

    /** 根据 innerPath 重设 cursor.nodePath（LIST 保留首位的 itemIdx） */
    function setInnerPath(cursor, innerPath) {
      var prefix = (_doc.blocks[cursor.blockIndex].type === "list" && cursor.nodePath && cursor.nodePath.length)
        ? [cursor.nodePath[0]] : [];
      cursor.nodePath = prefix.concat(innerPath);
    }

    /** 浅拷贝 inline 容器节点，替换其 children（保留 color/size 等属性） */
    function cloneInlineNode(node, children) {
      var copy = {};
      Object.keys(node).forEach(function (k) {
        if (k === "children") return;
        copy[k] = node[k];
      });
      copy.children = children;
      return copy;
    }

    /** 通用 inline 树拆分：在 nodePath/offset 处一分为二（支持任意嵌套深度） */
    function splitInlineAt(children, nodePath, offset) {
      if (!children || !nodePath || !nodePath.length) return null;
      var idx = nodePath[0];
      var node = children[idx];
      if (!node) return null;

      var before = children.slice(0, idx);
      var after = children.slice(idx + 1);

      // 叶节点（TEXT）直接切分
      if (nodePath.length === 1) {
        if (node.type === "text") {
          var lText = node.content.slice(0, offset);
          var rText = node.content.slice(offset);
          var left = before.slice();
          var right = after.slice();
          if (lText) left.push(A.text(lText));
          if (rText) right.unshift(A.text(rText));
          return { left: left, right: right };
        }
        // 原子叶子（行内公式/链接等 contentEditable=false，不可从中间拆分）：
        // 光标/选区边界在叶子开头（offset<=0）→ 整体归右侧；在叶子内部/末尾 → 整体归左侧
        var atomic = (node.type === "math_inline" || node.type === "wiki_link" || node.type === "link");
        if (!atomic) return null;
        var left2 = before.slice();
        var right2 = after.slice();
        if (offset > 0) left2.push(node);
        else right2.unshift(node);
        return { left: left2, right: right2 };
      }

      // 嵌套容器节点：递归拆分内部，再把容器节点复制到左右两侧
      if (!node.children || !Array.isArray(node.children)) return null;
      var sub = splitInlineAt(node.children, nodePath.slice(1), offset);
      if (!sub) return null;

      var left2 = before.slice();
      var right2 = after.slice();
      if (sub.left.length) left2.push(cloneInlineNode(node, sub.left));
      if (sub.right.length) right2.unshift(cloneInlineNode(node, sub.right));
      return { left: left2, right: right2 };
    }

    /** 找到 inline 数组中第一个 TEXT 叶节点的路径（用于把光标放到块开头） */
    function firstTextPath(nodes) {
      if (!nodes) return null;
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.type === "text") return { path: [i], offset: 0 };
        if (n.children && n.children.length) {
          var sub = firstTextPath(n.children);
          if (sub) return { path: [i].concat(sub.path), offset: 0 };
        }
      }
      return null;
    }

    /** 找到 inline 数组中最后一个 TEXT 叶节点的路径（用于把光标放到块末尾） */
    function lastTextPath(nodes) {
      if (!nodes) return null;
      for (var i = nodes.length - 1; i >= 0; i--) {
        var n = nodes[i];
        if (n.type === "text") return { path: [i], offset: n.content.length };
        if (n.children && n.children.length) {
          var sub = lastTextPath(n.children);
          if (sub) return { path: [i].concat(sub.path), offset: sub.offset };
        }
      }
      return null;
    }

    /** 计算某个 block 的「末尾」光标坐标（绝对坐标，列表会定位到最后一个 item） */
    function blockEndCursor(blockIndex, block) {
      if (!block) return { blockIndex: blockIndex, nodePath: [], offset: 0 };
      if (block.type === "list") {
        var li = (block.items && block.items.length) ? block.items.length - 1 : -1;
        if (li < 0) return { blockIndex: blockIndex, nodePath: [], offset: 0 };
        var it = block.items[li];
        var lp = lastTextPath(it.children || []);
        if (lp) return { blockIndex: blockIndex, nodePath: [li].concat(lp.path), offset: lp.offset };
        return { blockIndex: blockIndex, nodePath: [li], offset: 0 };
      }
      var lp2 = lastTextPath(block.children || []);
      if (lp2) return { blockIndex: blockIndex, nodePath: lp2.path, offset: lp2.offset };
      return { blockIndex: blockIndex, nodePath: [], offset: 0 };
    }

    /** 判断光标是否在 block 内容的绝对开头（首个 TEXT 叶节点 offset=0） */
    function isAtBlockStart(block, cursor) {
      if (cursor.offset !== 0) return false;
      var children, path;
      if (block.type === "list") {
        var itemIdx = (cursor.nodePath && cursor.nodePath.length) ? cursor.nodePath[0] : 0;
        var item = block.items && block.items[itemIdx];
        children = item ? (item.children || []) : [];
        path = (cursor.nodePath || []).slice(1);
      } else {
        children = block.children || [];
        path = cursor.nodePath || [];
      }
      var fp = firstTextPath(children);
      if (!fp) return path.length === 0;
      if (path.length !== fp.path.length) return false;
      for (var i = 0; i < path.length; i++) {
        if (path[i] !== fp.path[i]) return false;
      }
      return true;
    }

    /** 可安全合并的相邻样式容器节点（渲染效果可叠加，无跳转/链接语义） */
    var MERGEABLE_STYLES = {
      bold: 1, italic: 1, bold_italic: 1, strikethrough: 1,
      highlight: 1, font_color: 1, font_size: 1, font_bold: 1, font_italic: 1,
      font_underline: 1, font_superscript: 1, font_subscript: 1
    };

    /** 判断两个 inline 容器节点除 children 外属性完全相同 */
    function sameNodeAttrs(a, b) {
      var ka = Object.keys(a).filter(function (k) { return k !== "children"; });
      var kb = Object.keys(b).filter(function (k) { return k !== "children"; });
      if (ka.length !== kb.length) return false;
      for (var i = 0; i < ka.length; i++) {
        if (a[ka[i]] !== b[ka[i]]) return false;
      }
      return true;
    }

    /**
     * 合并相邻的相同样式节点（如 [[\c:red|a]][[\c:red|b]] → [[\c:red|ab]]）
     * 以及相邻 text 节点
     */
    function mergeAdjacentInline(nodes) {
      if (!nodes || !nodes.length) return nodes;
      var out = [];
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var last = out[out.length - 1];
        if (last && last.type === "text" && n.type === "text") {
          // 创建新 text 节点，避免原地修改 last.content 污染共享的原 AST 引用
          out[out.length - 1] = A.text(last.content + n.content);
          continue;
        }
        if (last && MERGEABLE_STYLES[last.type] && last.type === n.type &&
            sameNodeAttrs(last, n) && last.children && n.children) {
          last.children = mergeAdjacentInline(last.children.concat(n.children));
          continue;
        }
        out.push(n);
      }
      return out;
    }

    /** 把「插入间隙」(gapPath/gapIndex) 转换为光标坐标（相对 root 的 nodePath + offset） */
    function gapToCursor(root, gapPath, gapIndex) {
      var parent = root;
      for (var i = 0; i < gapPath.length; i++) {
        parent = (parent[gapPath[i]] && parent[gapPath[i]].children) || [];
      }
      if (gapIndex < parent.length) {
        var node = parent[gapIndex];
        if (node.type === "text") {
          return { nodePath: gapPath.concat([gapIndex]), offset: 0 };
        }
        var fp = firstTextPath(node.children || []);
        if (fp) return { nodePath: gapPath.concat([gapIndex]).concat(fp.path), offset: 0 };
        return { nodePath: gapPath.concat([gapIndex]), offset: 0 };
      }
      if (gapIndex - 1 >= 0) {
        var prev = parent[gapIndex - 1];
        if (prev.type === "text") {
          return { nodePath: gapPath.concat([gapIndex - 1]), offset: prev.content.length };
        }
        var lp = lastTextPath(prev.children || []);
        if (lp) return { nodePath: gapPath.concat([gapIndex - 1]).concat(lp.path), offset: lp.offset };
        return { nodePath: gapPath.concat([gapIndex - 1]), offset: 0 };
      }
      return { nodePath: gapPath, offset: 0 };
    }

    /**
     * 删除已为空的 text 节点，并向上删除因此变空的样式容器（如残留的 [[\h:pink|]]）。
     * 完成后归一化相邻节点并就地修正 cursor（nodePath + offset）。
     */
    function pruneEmptyInline(block, cursor) {
      var isList = block.type === "list";
      var itemIdx = isList ? ((cursor.nodePath && cursor.nodePath.length) ? cursor.nodePath[0] : 0) : 0;
      var item = isList ? (block.items && block.items[itemIdx]) : null;
      var root = isList ? (item ? (item.children || []) : []) : (block.children || []);
      var path = isList ? (cursor.nodePath || []).slice(1) : (cursor.nodePath || []);

      if (!path.length) return;

      // 收集从 root 到空 text 叶子的父链
      var chain = [];
      var arr = root;
      for (var i = 0; i < path.length; i++) {
        var idx = path[i];
        var node = arr[idx];
        if (!node) return;
        chain.push({ parent: arr, index: idx, node: node });
        arr = node.children || [];
      }

      var leaf = chain[chain.length - 1];
      if (leaf.node.type !== "text" || leaf.node.content !== "") return;
      leaf.parent.splice(leaf.index, 1);

      // 光标 gap：叶子被删处
      var gapPath = path.slice(0, path.length - 1);
      var gapIndex = leaf.index;

      // 向上删除变空的样式容器
      for (var k = chain.length - 2; k >= 0; k--) {
        var entry = chain[k];
        var container = entry.node;
        if (MERGEABLE_STYLES[container.type] && container.children && container.children.length === 0) {
          entry.parent.splice(entry.index, 1);
          gapPath = path.slice(0, k);
          gapIndex = entry.index;
        } else {
          break;
        }
      }

      // 归一化相邻节点
      var merged = mergeAdjacentInline(root);

      // 段落清空 → 空行
      if (!isList && merged.length === 0 && block.type === "paragraph") {
        block.type = "blank_line";
        block.children = [];
        cursor.nodePath = [];
        cursor.offset = 0;
        return;
      }

      if (isList) {
        block.items[itemIdx].children = merged;
      } else {
        block.children = merged;
      }

      var rel = gapToCursor(merged, gapPath, gapIndex);
      if (!rel) return;
      cursor.nodePath = isList ? [itemIdx].concat(rel.nodePath) : rel.nodePath;
      cursor.offset = rel.offset;
    }

    /** AST 已修改后的统一提交：生成源码 → 更新源码编辑器 → 增量重渲染 → 恢复光标 → 标记脏 */
    function commit(block, cursor) {
      hlog("commit cursor=" + _fmtCursor(cursor));
      spliceBlockSource(cursor.blockIndex, G.generateBlock(block));
      renderEditor(state.doc);
      reRenderBlock(cursor.blockIndex);
      restoreCursor(cursor.blockIndex, cursor.nodePath, cursor.offset);
      markDirty();
      return true;
    }

    /** 同 commit，但提交后恢复为非折叠选区（selStart/selEnd 为 AST 坐标） */
    function commitSelection(block, blockIndex, selStart, selEnd) {
      hlog("commitSelection bi=" + blockIndex + " start=" + _fmtCursor({ blockIndex: blockIndex, nodePath: selStart.nodePath, offset: selStart.offset }) +
        " end=" + _fmtCursor({ blockIndex: blockIndex, nodePath: selEnd.nodePath, offset: selEnd.offset }));
      spliceBlockSource(blockIndex, G.generateBlock(block));
      renderEditor(state.doc);
      reRenderBlock(blockIndex);
      restoreSelection(blockIndex, selStart.nodePath, selStart.offset, selEnd.nodePath, selEnd.offset);
      markDirty();
      return true;
    }

    /** 获取并校验当前编辑锚点（EH.cursorAST） */
    function getEditContext() {
      var EH = window.MemoriaEditHandler;
      var cursor = EH && EH.cursorAST;
      if (!cursor) return null;
      if (!_doc || !_doc.blocks) return null;
      if (cursor.blockIndex < 0 || cursor.blockIndex >= _doc.blocks.length) return null;
      var block = _doc.blocks[cursor.blockIndex];
      if (!block || NON_EDITABLE[block.type]) return null;
      return { block: block, cursor: cursor };
    }

    // ── 撤销/重做（快照式，合并连续输入）──
    var undoStack = [];
    var redoStack = [];
    var lastGroup = null; // { kind, blockIndex, nodePath, offset }
    var _pendingGroupSnapshot = null; // 原子操作分组（粘贴/选中删除）的起点快照

    function cloneCursor(cursor) {
      return {
        blockIndex: cursor.blockIndex,
        nodePath: (cursor.nodePath || []).slice(),
        offset: cursor.offset,
      };
    }

    /** 格式化光标坐标，便于日志观察（附源码行:列 + 光标前后文本，用 | 标记） */
    function _fmtCursor(cursor) {
      if (!cursor) return "null";
      var s = "bi=" + cursor.blockIndex + " path=[" + (cursor.nodePath || []).join(",") + "] off=" + cursor.offset;
      try {
        if (M && typeof M.astToSrc === "function") {
          var pos = M.astToSrc(cursor.blockIndex, cursor.nodePath || [], cursor.offset);
          if (pos) {
            var lineText = (state.doc && state.doc.lines && state.doc.lines[pos.line]) || "";
            var ctx = 8;
            var before = lineText.substring(Math.max(0, pos.col - ctx), pos.col);
            var at = lineText.charAt(pos.col) || "\u00b7";
            var after = lineText.substring(pos.col + 1, pos.col + 1 + ctx);
            s += " | L" + (pos.line + 1) + ":" + pos.col + " [" + before + "|" + at + "|" + after + "]";
          }
        }
      } catch (e) { /* 忽略上下文提取失败 */ }
      return s;
    }

    /** 格式化 DOM Range 起点（节点类型 + 前若干字符 + 偏移），用于恢复选区的对比日志 */
    function _describeDomPos(range) {
      if (!range) return "null";
      var c = range.startContainer;
      var o = range.startOffset;
      if (c && c.nodeType === 3) {
        return "text#" + (c.data || "").slice(0, 12).replace(/\n/g, "\\n") + "@" + o;
      }
      if (c && c.nodeType === 1) {
        return (c.tagName || "?").toLowerCase() + "." + (c.className ? String(c.className).split(" ")[0] : "") + "@" + o;
      }
      return (c ? c.nodeName : "?") + "@" + o;
    }

    /**
     * 格式化「光标前后 N 行」的源码快照（用于段前/段后 Enter 的前后对比）
     * @param {string[]} rawLines — 源码行数组
     * @param {number} lineIndex — 参考行（0-based，通常是光标所在行）
     * @param {number} radius — 前后行数（默认 4）
     * @returns {string} 多行文本，参考行用 >>> 标记
     */
    function _fmtContextLines(rawLines, lineIndex, radius) {
      radius = radius || 4;
      if (!rawLines || !rawLines.length) return "\n  (empty body)";
      var out = [];
      var start = Math.max(0, lineIndex - radius);
      var end = Math.min(rawLines.length - 1, lineIndex + radius);
      for (var i = start; i <= end; i++) {
        var mark = (i === lineIndex) ? ">>>" : "   ";
        out.push(mark + " L" + (i + 1) + ": " + JSON.stringify(rawLines[i]));
      }
      return "\n" + out.join("\n");
    }

    /** 格式化撤销/重做栈大小 */
    function _stackDump() {
      return "undo=" + undoStack.length + " redo=" + redoStack.length;
    }

    /** 连续同类输入判定：本次编辑起点 == 上次编辑终点，且同 block */
    function shouldCoalesce(kind, cursor) {
      if (!lastGroup || lastGroup.kind !== kind) return false;
      if (lastGroup.blockIndex !== cursor.blockIndex) return false;
      var lp = lastGroup.nodePath;
      var cp = cursor.nodePath || [];
      if (lp.length !== cp.length) return false;
      for (var i = 0; i < lp.length; i++) if (lp[i] !== cp[i]) return false;
      return lastGroup.offset === cursor.offset;
    }

    function recordUndo(cursor) {
      undoStack.push({ body: state.doc.body, cursorAST: cloneCursor(cursor) });
      redoStack.length = 0;
      hlog("recordUndo push pre=" + _fmtCursor(cursor) + " bodyLen=" + (state.doc.body || "").length + " | " + _stackDump());
    }

    /** 编辑前记录撤销快照；连续同类输入则合并（不新增快照） */
    function beginUndo(kind, preCursor, forceGroup) {
      // 原子操作分组期间，子操作不各自记录快照（由 beginUndoGroup 统一记录）
      if (_pendingGroupSnapshot) return;
      var coalesce = !forceGroup && shouldCoalesce(kind, preCursor);
      hlog("beginUndo kind=" + kind + " force=" + !!forceGroup + " pre=" + _fmtCursor(preCursor) + " coalesce=" + coalesce + " | " + _stackDump());
      if (coalesce) return;
      recordUndo(preCursor);
    }

    /** 开始一个原子操作分组（粘贴 / 选中删除等）：记录一次起点快照，后续子操作不再各自入栈 */
    function beginUndoGroup() {
      if (_pendingGroupSnapshot) return;
      _pendingGroupSnapshot = currentSnapshot();
      hlog("beginUndoGroup snapshot cursor=" + _fmtCursor(_pendingGroupSnapshot.cursorAST) + " | " + _stackDump());
    }

    /** 结束原子操作分组：将起点快照压入 undoStack，形成单个撤销单元 */
    function endUndoGroup() {
      if (!_pendingGroupSnapshot) return;
      undoStack.push(_pendingGroupSnapshot);
      redoStack.length = 0;
      _pendingGroupSnapshot = null;
      lastGroup = null;
      hlog("endUndoGroup pushed cursor=" + _fmtCursor(undoStack[undoStack.length - 1].cursorAST) + " | " + _stackDump());
    }

    function recordGroup(kind, cursor) {
      lastGroup = { kind: kind, blockIndex: cursor.blockIndex, nodePath: (cursor.nodePath || []).slice(), offset: cursor.offset };
      hlog("recordGroup kind=" + kind + " post=" + _fmtCursor(cursor));
    }

    function currentSnapshot() {
      var EH = window.MemoriaEditHandler;
      var c = (EH && EH.cursorAST) || { blockIndex: 0, nodePath: [], offset: 0 };
      hlog("currentSnapshot cursor=" + _fmtCursor(c) + " | " + _stackDump());
      return { body: state.doc.body, cursorAST: cloneCursor(c) };
    }

    function applySnapshot(snap) {
      hlog("applySnapshot cursor=" + _fmtCursor(snap.cursorAST) + " bodyLen=" + (snap.body ? snap.body.length : 0) + " | " + _stackDump());
      state.doc.body = snap.body;
      state.doc.lines = snap.body.split("\n");
      state.doc.preview_body = null;  // 撤销/重做后 preview_body 缓存过期，必须清空否则渲染旧内容
      renderEditor(state.doc);
      renderPreview(state.doc).then(function () {
        hlog("applySnapshot done -> restoreCursor " + _fmtCursor(snap.cursorAST));
        restoreCursor(snap.cursorAST.blockIndex, snap.cursorAST.nodePath, snap.cursorAST.offset);
      });
      markDirty();
    }

    function undo() {
      if (!undoStack.length) { hlog("undo NO-OP " + _stackDump()); return false; }
      redoStack.push(currentSnapshot());
      var snap = undoStack.pop();
      hlog("undo -> apply cursor=" + _fmtCursor(snap.cursorAST) + " | " + _stackDump());
      applySnapshot(snap);
      lastGroup = null;
      return true;
    }

    function redo() {
      if (!redoStack.length) { hlog("redo NO-OP " + _stackDump()); return false; }
      undoStack.push(currentSnapshot());
      var snap = redoStack.pop();
      hlog("redo -> apply cursor=" + _fmtCursor(snap.cursorAST) + " | " + _stackDump());
      applySnapshot(snap);
      lastGroup = null;
      return true;
    }

    function resetHistory() {
      hlog("resetHistory " + _stackDump());
      undoStack.length = 0;
      redoStack.length = 0;
      lastGroup = null;
    }

    // ── 结构标记自动转换（# / ## / - / * / + / 1. 等）──

    /** 检测段落源码行是否构成块级标记，返回 {type, level?, ordered?} 或 null */
    function detectStructuralMarker(line) {
      if (!line) return null;
      var hm = line.match(/^(#{1,6})\s/);
      if (hm) return { type: "heading", level: hm[1].length };
      var lm = line.match(/^([-*+])\s/);
      if (lm) return { type: "list", ordered: false };
      var om = line.match(/^(\d+)\.\s/);
      if (om) return { type: "list", ordered: true };
      return null;
    }

    /** 计算新 block 的「内容起始」光标坐标（紧跟 marker 之后） */
    function blockContentStart(block) {
      if (block.type === "heading") {
        var fp = firstTextPath(block.children || []);
        return { nodePath: fp ? fp.path : [], offset: 0 };
      }
      if (block.type === "list") {
        var item = block.items && block.items[0];
        var ifp = item ? firstTextPath(item.children || []) : null;
        return { nodePath: ifp ? [0].concat(ifp.path) : [0], offset: 0 };
      }
      var pfp = firstTextPath(block.children || []);
      return { nodePath: pfp ? pfp.path : [], offset: 0 };
    }

    /**
     * 若段落已构成块级标记（标题/列表），则原地转换为对应 block 并修正光标。
     * @returns {boolean} 是否发生了转换
     */
    function convertStructuralBlock(block, cursor) {
      if (block.type !== "paragraph") return false;
      var line = G.generateBlock(block);
      var marker = detectStructuralMarker(line);
      if (!marker) return false;

      var newBlock = P.parseBlocks([line])[0];
      if (!newBlock || newBlock.type === "paragraph") return false;

      // 原地替换 block 属性（block 即 _doc.blocks[cursor.blockIndex]）
      var k;
      for (k in block) { if (Object.prototype.hasOwnProperty.call(block, k)) delete block[k]; }
      for (k in newBlock) { if (Object.prototype.hasOwnProperty.call(newBlock, k)) block[k] = newBlock[k]; }

      var nc = blockContentStart(block);
      cursor.nodePath = nc.nodePath;
      cursor.offset = nc.offset;
      return true;
    }

    /**
     * 在预览区插入文本（insertText）
     * @param {string} text — 插入的字符
     * @returns {boolean} 是否成功
     */
    function insertText(text, forceGroup) {
      if (!text) return false;

      var ctx = getEditContext();
      if (!ctx) return false;
      var block = ctx.block;
      var cursor = ctx.cursor;

      // 空行输入：先把 BLANK_LINE 转成 PARAGRAPH，再插入文字
      // （否则 SourceGen.generateBlock(BLANK_LINE) 返回空串，导致文字丢失）
      if (block.type === "blank_line") {
        block.type = "paragraph";
        block.children = [];
      }

      // 记录编辑前光标（用于撤销快照与合并判断）
      var preCursor = cloneCursor(cursor);

      var node = null;
      if (cursor.nodePath && cursor.nodePath.length) {
        node = A.getNodeAt(block, cursor.nodePath);
      }

      if (node && node.type === "text") {
        A.editText(node, cursor.offset, text);
        cursor.offset += text.length;
      } else if (!node || !A.isInline(node)) {
        // 空 block / 空 list item：新建 Text 节点
        node = A.text(text);
        if (block.type === "list") {
          var itemIdx = (cursor.nodePath && cursor.nodePath.length) ? cursor.nodePath[0] : 0;
          var item = block.items && block.items[itemIdx];
          if (!item) return false;
          item.children = [node];
          cursor.nodePath = [itemIdx, 0];
        } else {
          block.children = [node];
          cursor.nodePath = [0];
        }
        cursor.offset = text.length;
      } else {
        // 叶子但非 Text（CODE/MATH_INLINE/WIKI_LINK/LINK/ESCAPE）：暂不支持纯文本插入
        return false;
      }

      // 结构标记自动转换（段落输入 "# " / "- " / "1. " 等 → 标题/列表）
      convertStructuralBlock(block, cursor);

      beginUndo("insert", preCursor, forceGroup);
      var ok = commit(block, cursor);
      if (ok) recordGroup("insert", cursor);
      return ok;
    }

    /**
     * 全量替换源码行范围 [startLine, endLine] 为新行，重渲染并恢复光标
     * 用于跨 block 操作（合并/删除空行等 block 结构变化场景）
     */
    function commitRange(startLine, endLine, newLines, newCursor, preCursor, kind) {
      beginUndo(kind, preCursor, true);
      var rawLines = (state.doc.body || "").split("\n");
      var merged = rawLines.slice(0, startLine).concat(newLines, rawLines.slice(endLine + 1));
      state.doc.body = merged.join("\n");
      state.doc.lines = merged;
      state.doc.preview_body = null;  // 本地编辑使 preview_body 缓存过期，必须清空否则渲染旧内容
      renderEditor(state.doc);
      renderPreview(state.doc).then(function () {
        restoreCursor(newCursor.blockIndex, newCursor.nodePath, newCursor.offset);
      });
      markDirty();
      recordGroup(kind, newCursor);
      return true;
    }

    /**
     * 列表项「退列表」：去掉列表标记，把当前项变成段落（有内容）或纯空行（空项）。
     * 当前项之前的项仍为一个列表，之后的项仍为一个列表（若有）。
     */
    function outdentListItem(block, cursor, preCursor, itemIdx, isEmpty) {
      var blockIndex = cursor.blockIndex;
      var beforeItems = block.items.slice(0, itemIdx);
      var afterItems = block.items.slice(itemIdx + 1);
      var curItem = block.items[itemIdx];

      var newSrcLines = [];
      if (beforeItems.length) {
        newSrcLines = newSrcLines.concat(G.generateBlock(A.list(block.ordered, beforeItems)).split("\n"));
      }
      if (isEmpty) {
        newSrcLines.push("");
      } else {
        newSrcLines.push(G.generateBlock(A.paragraph(curItem.children || [])));
      }
      if (afterItems.length) {
        newSrcLines = newSrcLines.concat(G.generateBlock(A.list(block.ordered, afterItems)).split("\n"));
      }

      var range = _blockLineMap[blockIndex];
      if (!range) return false;

      // 前面有项时，当前退出的块（段落/空行）落在其后的一个 block；否则占据原 block 位置
      var targetBlockIndex = blockIndex + (beforeItems.length ? 1 : 0);
      var newCursor = isEmpty
        ? { blockIndex: targetBlockIndex, nodePath: [], offset: 0 }
        : (function () {
            var fp = firstTextPath(curItem.children || []);
            return { blockIndex: targetBlockIndex, nodePath: fp ? fp.path : [], offset: 0 };
          })();

      return commitRange(range.startLine, range.endLine, newSrcLines, newCursor, preCursor, "backspace");
    }

    /**
     * 光标在 block 内容开头时退格：合并上一行 / 删除空行 / 合并上一列表项
     */
    function backspaceAtBlockStart(block, cursor, preCursor) {
      var blockIndex = cursor.blockIndex;

      // ── 当前是空行：删除该空行，光标移到上一 block 末尾 ──
      if (block.type === "blank_line") {
        var curRange = _blockLineMap[blockIndex];
        if (!curRange) return false;
        var prevBlock = blockIndex > 0 ? _doc.blocks[blockIndex - 1] : null;
        var newCursor = blockEndCursor(Math.max(0, blockIndex - 1), prevBlock);
        return commitRange(curRange.startLine, curRange.endLine, [], newCursor, preCursor, "backspace");
      }

      // ── 列表项首：退列表（第一项→段落/空行；空项→空行；非空项合并上一项） ──
      if (block.type === "list") {
        var itemIdx = (cursor.nodePath && cursor.nodePath.length) ? cursor.nodePath[0] : 0;
        var curItem = block.items && block.items[itemIdx];
        if (!curItem) return false;
        var itemEmpty = !(curItem.children && curItem.children.length);

        // 第一项：退列表 → 段落（空项→空行）
        if (itemIdx === 0) {
          return outdentListItem(block, cursor, preCursor, itemIdx, itemEmpty);
        }

        // 空列表项：先退成纯空行（不直接删除），下一次 backspace 再删空行
        if (itemEmpty) {
          return outdentListItem(block, cursor, preCursor, itemIdx, true);
        }

        // 非空项：合并到上一项
        var prevItem = block.items[itemIdx - 1];
        var prevLast = lastTextPath(prevItem.children || []);
        prevItem.children = mergeAdjacentInline((prevItem.children || []).concat(curItem.children || []));
        block.items.splice(itemIdx, 1);
        var newSrcLines = G.generateBlock(block).split("\n");
        var range = _blockLineMap[blockIndex];
        if (!range) return false;
        var newCursor2 = prevLast
          ? { blockIndex: blockIndex, nodePath: [itemIdx - 1].concat(prevLast.path), offset: prevLast.offset }
          : { blockIndex: blockIndex, nodePath: [itemIdx - 1], offset: 0 };
        return commitRange(range.startLine, range.endLine, newSrcLines, newCursor2, preCursor, "backspace");
      }

      // ── 空标题：退标题 → 纯空行（与空列表项 "- " 一致：先退成空行，再 backspace 才删空行） ──
      if (block.type === "heading" && !(block.children && block.children.length)) {
        var hrRange = _blockLineMap[blockIndex];
        if (!hrRange) return false;
        return commitRange(hrRange.startLine, hrRange.endLine, [""],
          { blockIndex: blockIndex, nodePath: [], offset: 0 }, preCursor, "backspace");
      }

      // ── 段落/标题首 ──
      var prevBlock = blockIndex > 0 ? _doc.blocks[blockIndex - 1] : null;
      if (!prevBlock) return false;

      // 上一 block 是空行：删除空行，当前 block 上移，光标留在当前 block 开头
      if (prevBlock.type === "blank_line") {
        var prevRange = _blockLineMap[blockIndex - 1];
        if (!prevRange) return false;
        var fp = firstTextPath(block.children || []);
        var newCursor3 = fp
          ? { blockIndex: blockIndex - 1, nodePath: fp.path, offset: 0 }
          : { blockIndex: blockIndex - 1, nodePath: [], offset: 0 };
        return commitRange(prevRange.startLine, prevRange.endLine, [], newCursor3, preCursor, "backspace");
      }

      // 上一 block 是段落/标题：把当前内容合并到上一 block 末尾
      if (prevBlock.type === "paragraph" || prevBlock.type === "heading") {
        var prevChildren = (prevBlock.children || []).slice();
        var prevLast2 = lastTextPath(prevChildren);
        prevBlock.children = mergeAdjacentInline((prevBlock.children || []).concat(block.children || []));
        var mergedSrc = G.generateBlock(prevBlock);
        var prevRange2 = _blockLineMap[blockIndex - 1];
        var curRange2 = _blockLineMap[blockIndex];
        if (!prevRange2 || !curRange2) return false;
        var newCursor4 = prevLast2
          ? { blockIndex: blockIndex - 1, nodePath: prevLast2.path, offset: prevLast2.offset }
          : { blockIndex: blockIndex - 1, nodePath: [], offset: 0 };
        return commitRange(prevRange2.startLine, curRange2.endLine, [mergedSrc], newCursor4, preCursor, "backspace");
      }

      return false;
    }

    /**
     * 退格删除（deleteContentBackward）
     * 支持：Text 节点内退格、与前一相邻 Text 节点合并、行首合并上一行/删空行
     */
    function backspace() {
      var ctx = getEditContext();
      if (!ctx) return false;
      var block = ctx.block;
      var cursor = ctx.cursor;

      var preCursor = cloneCursor(cursor);

      // 空行退格：无 text 节点，直接走行首合并/删除逻辑
      if (block.type === "blank_line") {
        return backspaceAtBlockStart(block, cursor, preCursor);
      }

      var resolved = resolveNode(block, cursor);

      // 空内容（如空列表项 "- "，无 text 节点）：按行首合并/删除处理
      if (!resolved || !resolved.node) {
        if (isAtBlockStart(block, cursor)) {
          return backspaceAtBlockStart(block, cursor, preCursor);
        }
        return false;
      }

      if (resolved.node.type !== "text") return false;

      // 情况 1：Text 节点内退格
      if (cursor.offset > 0) {
        A.backspaceText(resolved.node, cursor.offset);
        cursor.offset -= 1;
        // 内容被删空时，清理空 text 与空样式容器（避免残留 [[\h:pink|]]）
        if (resolved.node.content === "") {
          pruneEmptyInline(block, cursor);
        }
        beginUndo("backspace", preCursor, false);
        var ok = commit(block, cursor);
        if (ok) recordGroup("backspace", cursor);
        return ok;
      }

      // 情况 2：光标在 Text 节点开头，尝试与前一相邻 Text 节点合并
      var prev = resolved.index > 0 ? resolved.parentChildren[resolved.index - 1] : null;
      if (prev && prev.type === "text") {
        var deleted = prev.content.slice(0, -1);
        prev.content = deleted + resolved.node.content;
        resolved.parentChildren.splice(resolved.index, 1);
        var innerPath = resolved.innerPath.slice();
        innerPath[innerPath.length - 1] -= 1;
        setInnerPath(cursor, innerPath);
        cursor.offset = deleted.length;
        beginUndo("backspace", preCursor, false);
        var ok2 = commit(block, cursor);
        if (ok2) recordGroup("backspace", cursor);
        return ok2;
      }

      // 情况 3：光标在 block 内容开头 → 合并到上一行 / 删除空行
      if (isAtBlockStart(block, cursor)) {
        return backspaceAtBlockStart(block, cursor, preCursor);
      }

      // 样式标记边界等复杂情况暂不处理
      return false;
    }

    /**
     * 前向删除（deleteContentForward）
     * 支持：Text 节点内删除、与后一相邻 Text 节点合并
     */
    function deleteForward() {
      var ctx = getEditContext();
      if (!ctx) return false;
      var block = ctx.block;
      var cursor = ctx.cursor;

      var resolved = resolveNode(block, cursor);
      if (!resolved || !resolved.node || resolved.node.type !== "text") return false;

      var preCursor = cloneCursor(cursor);

      // 情况 1：Text 节点内删除（删除 offset 处字符）
      if (cursor.offset < resolved.node.content.length) {
        A.editText(resolved.node, cursor.offset, "");
        beginUndo("delete", preCursor, false);
        var ok = commit(block, cursor);
        if (ok) recordGroup("delete", cursor);
        return ok;
      }

      // 情况 2：光标在 Text 节点末尾，尝试与后一相邻 Text 节点合并
      var next = (resolved.index >= 0 && resolved.index + 1 < resolved.parentChildren.length)
        ? resolved.parentChildren[resolved.index + 1] : null;
      if (next && next.type === "text") {
        resolved.node.content += next.content.slice(1);
        resolved.parentChildren.splice(resolved.index + 1, 1);
        beginUndo("delete", preCursor, false);
        var ok2 = commit(block, cursor);
        if (ok2) recordGroup("delete", cursor);
        return ok2;
      }

      return false;
    }

    /**
     * Enter 拆分段落（insertParagraph）
     * 支持：段落、标题（后段变普通段落）、列表项（同列表内拆两项）
     * 拆分后全量重渲染并恢复光标到新块开头
     */
    function splitParagraph() {
      // 图片块换行（光标停在 img 前/后）：不经过 getEditContext（图片块在
      // NON_EDITABLE 中会被拦截），直接走专用路径——图片前→上方插空行，图片后→下方插空行
      var EH2 = window.MemoriaEditHandler;
      var imgCursor = (EH2 && EH2.cursorAST) || null;
      if (imgCursor && imgCursor.blockIndex >= 0 && _doc && _doc.blocks &&
          _doc.blocks[imgCursor.blockIndex] && _doc.blocks[imgCursor.blockIndex].type === "image" &&
          (!imgCursor.nodePath || imgCursor.nodePath.length === 0)) {
        var imgBlockIndex = imgCursor.blockIndex;
        var imgBlock = _doc.blocks[imgBlockIndex];
        var imgRange = (_blockLineMap && _blockLineMap[imgBlockIndex]) || null;
        if (imgRange) {
          var imgPreCursor = cloneCursor(imgCursor);
          var imgNewLines;
          var imgNewCursor;
          // 用原始源码行（AST 中 image.url 已被绝对化为 /files/...，直接
          // generateBlock 会把相对路径改写为绝对路径，污染源码）
          var imgRawLine = (state.doc.lines && state.doc.lines[imgRange.startLine] != null)
            ? state.doc.lines[imgRange.startLine]
            : G.generateBlock(imgBlock);
          if (imgCursor.offset > 0) {
            // 图片右侧：下方插入空行，光标落空行
            imgNewLines = [imgRawLine, ""];
            imgNewCursor = { blockIndex: imgBlockIndex + 1, nodePath: [], offset: 0 };
          } else {
            // 图片左侧：上方插入空行，光标落空行（原图片块下移）
            imgNewLines = ["", imgRawLine];
            imgNewCursor = { blockIndex: imgBlockIndex, nodePath: [], offset: 0 };
          }
          hlog("splitParagraph image block pre=" + _fmtCursor(imgPreCursor) +
            " new=" + _fmtCursor(imgNewCursor));
          beginUndo("enter", imgPreCursor, true);
          var imgRaw = (state.doc.body || "").split("\n");
          var imgMerged = imgRaw.slice(0, imgRange.startLine)
            .concat(imgNewLines, imgRaw.slice(imgRange.endLine + 1));
          state.doc.body = imgMerged.join("\n");
          state.doc.lines = imgMerged;
          state.doc.preview_body = null;  // 本地编辑使 preview_body 缓存过期，必须清空否则渲染旧内容
          renderEditor(state.doc);
          renderPreview(state.doc).then(function () {
            restoreCursor(imgNewCursor.blockIndex, imgNewCursor.nodePath, imgNewCursor.offset);
          });
          markDirty();
          recordGroup("enter", imgNewCursor);
          return true;
        }
        return false;
      }

      var ctx = getEditContext();
      if (!ctx) return false;
      var block = ctx.block;
      var cursor = ctx.cursor;
      var blockIndex = cursor.blockIndex;

      var range = (_blockLineMap && _blockLineMap[blockIndex]) || null;
      if (!range) return false;

      var preCursor = cloneCursor(cursor);
      var newCursor = null;
      var newSrcLines = null; // 替换 [range.startLine, range.endLine] 的新源码行数组

      if (block.type === "paragraph" || block.type === "heading") {
        var sp = splitInlineAt(block.children || [], cursor.nodePath, cursor.offset);
        if (!sp) return false;

        // 段首：光标在整段开头 → 在上方插入空行，光标落在空行（原块下移并保持类型）
        if (sp.left.length === 0 && sp.right.length > 0) {
          var keepBlock = block.type === "heading"
            ? A.heading(block.level, sp.right)
            : A.paragraph(sp.right);
          newSrcLines = ["", G.generateBlock(keepBlock)];
          newCursor = { blockIndex: blockIndex, nodePath: [], offset: 0 };
        }
        // 段末：光标在整段末尾 → 在下方插入空行，光标落在空行
        else if (sp.right.length === 0) {
          var leftBlock = block.type === "heading"
            ? A.heading(block.level, sp.left)
            : A.paragraph(sp.left);
          newSrcLines = [G.generateBlock(leftBlock), ""];
          newCursor = { blockIndex: blockIndex + 1, nodePath: [], offset: 0 };
        }
        // 段中：正常一分为二，前半保留类型，后半变普通段落
        else {
          var leftBlockM = block.type === "heading"
            ? A.heading(block.level, sp.left)
            : A.paragraph(sp.left);
          var rightBlockM = A.paragraph(sp.right);
          newSrcLines = [G.generateBlock(leftBlockM), G.generateBlock(rightBlockM)];
          var fp = firstTextPath(sp.right);
          newCursor = { blockIndex: blockIndex + 1, nodePath: fp ? fp.path : [], offset: 0 };
        }
      } else if (block.type === "list") {
        var itemIdx = (cursor.nodePath && cursor.nodePath.length) ? cursor.nodePath[0] : 0;
        var item = block.items && block.items[itemIdx];
        if (!item) return false;
        var itemChildren = item.children || [];
        var sp2 = splitInlineAt(itemChildren, (cursor.nodePath || []).slice(1), cursor.offset);
        // 空列表项（无 inline 内容）：左右都空，Enter 在其后插入新空项
        if (!sp2) {
          if (itemChildren.length === 0) {
            sp2 = { left: [], right: [] };
          } else {
            return false;
          }
        }
        var newItems = block.items.slice(0, itemIdx + 1);
        newItems[itemIdx] = A.listItem(sp2.left);
        newItems = newItems.concat([A.listItem(sp2.right)], block.items.slice(itemIdx + 1));
        newSrcLines = G.generateBlock(A.list(block.ordered, newItems)).split("\n");
        var fp2 = firstTextPath(sp2.right);
        newCursor = { blockIndex: blockIndex, nodePath: fp2 ? [itemIdx + 1].concat(fp2.path) : [itemIdx + 1], offset: 0 };
      } else if (block.type === "blank_line") {
        // 纯空行按 Enter → 在当前空行下方再插入一个空行，光标落在新空行
        newSrcLines = ["", ""];
        newCursor = { blockIndex: blockIndex + 1, nodePath: [], offset: 0 };
      } else {
        return false;
      }

      hlog("splitParagraph block=" + block.type + " pre=" + _fmtCursor(preCursor) +
        " new=" + _fmtCursor(newCursor) +
        " srcLines=[" + newSrcLines.map(function (l) { return JSON.stringify(l); }).join(", ") + "]");

      // 记录撤销快照（Enter 独立一步）
      beginUndo("enter", preCursor, true);

      // 光标准确源码行：list 等多行块中，光标可能落在块内中间 item 行（range.startLine 只是块首行）
      var cursorLine = range.startLine;
      if (M && typeof M.astToSrc === "function") {
        var cursorSrcPos = M.astToSrc(preCursor.blockIndex, preCursor.nodePath || [], preCursor.offset);
        if (cursorSrcPos && cursorSrcPos.line != null) cursorLine = cursorSrcPos.line;
      }

      // 替换源码行：原 block 行范围 → 拆分后的新源码行
      var rawLines = (state.doc.body || "").split("\n");
      hlog("splitParagraph BEFORE  cursor-line=" + (cursorLine + 1) +
        _fmtContextLines(rawLines, cursorLine, 4));

      var merged = rawLines.slice(0, range.startLine)
        .concat(newSrcLines, rawLines.slice(range.endLine + 1));
      state.doc.body = merged.join("\n");
      state.doc.lines = merged;
      state.doc.preview_body = null;  // 本地编辑使 preview_body 缓存过期，必须清空否则渲染旧内容
      hlog("splitParagraph AFTER   cursor-line=" + (cursorLine + 1) +
        _fmtContextLines(merged, cursorLine, 4));

      renderEditor(state.doc);

      // 全量重渲染（block 结构已变化），完成后恢复光标到新块开头
      renderPreview(state.doc).then(function () {
        var rb = (_doc && _doc.blocks && _doc.blocks[newCursor.blockIndex]) || null;
        hlog("splitParagraph re-rendered blocks=" + (_doc && _doc.blocks ? _doc.blocks.length : 0) +
          " block[" + newCursor.blockIndex + "].type=" + (rb ? rb.type : "?") +
          " items=" + (rb && rb.items ? rb.items.length : "-"));
        hlog("splitParagraph re-rendered, restore new cursor=" + _fmtCursor(newCursor));
        restoreCursor(newCursor.blockIndex, newCursor.nodePath, newCursor.offset);
      });

      markDirty();
      recordGroup("enter", newCursor);
      return true;
    }

    /**
     * 回滚被 IME 组合输入污染的前端 DOM（AST/源码未变）
     * 用于组合结束但空提交（用户取消选词）的场景
     */
    function revertBlock() {
      var ctx = getEditContext();
      if (!ctx) return false;
      reRenderBlock(ctx.cursor.blockIndex);
      restoreCursor(ctx.cursor.blockIndex, ctx.cursor.nodePath, ctx.cursor.offset);
      return true;
    }

    // ════════════════════════════════════════════════════════════════
    //  预览区选中文字样式编辑：加粗/斜体（切换）、高亮/字体颜色（重着色并合并）
    // ════════════════════════════════════════════════════════════════

    function _isSupportedFormat(formatType) {
      return formatType === "bold" || formatType === "italic" ||
             formatType === "highlight" || formatType === "fontcolor" ||
             formatType === "unhighlight" || formatType === "unfontcolor";
    }

    function _isBoldNode(n) { return n && (n.type === "bold" || n.type === "bold_italic"); }
    function _isItalicNode(n) { return n && (n.type === "italic" || n.type === "bold_italic"); }

    /** 判断一组 inline 中所有可见叶子是否都处于 isStyleNode 指定的容器内 */
    function _everyLeafHasStyle(nodes, isStyleNode, inStyle) {
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (isStyleNode(n)) {
          if (n.children && n.children.length && !_everyLeafHasStyle(n.children, isStyleNode, true)) return false;
          continue;
        }
        if (n.type === "text" || !n.children || !n.children.length) {
          if (!inStyle) return false;
          continue;
        }
        if (!_everyLeafHasStyle(n.children, isStyleNode, inStyle)) return false;
      }
      return true;
    }

    /**
     * 检测选区的背景色（highlight）与前景色（font_color / highlight.fgColor）状态。
     * active 仅当“所有可见叶子都具备该样式且颜色一致”时为 true；color 为统一颜色（默认高亮为 null）。
     */
    function _detectColorState(nodes) {
      var hlSeen = false, hlColor = null, hlMixed = false, hlComplete = true;
      var fcSeen = false, fcColor = null, fcMixed = false, fcComplete = true;

      (function walk(list, curHl, curHlColor, curFg) {
        for (var i = 0; i < list.length; i++) {
          var n = list[i];
          if (n.type === "highlight") {
            walk(n.children || [], true, n.color || null,
                 (n.fgColor != null) ? n.fgColor : curFg);
          } else if (n.type === "font_color") {
            walk(n.children || [], curHl, curHlColor, n.color || null);
          } else if (n.children && n.children.length) {
            walk(n.children, curHl, curHlColor, curFg);
          } else {
            if (curHl) {
              if (!hlSeen) { hlSeen = true; hlColor = curHlColor; }
              else if (curHlColor !== hlColor) hlMixed = true;
            } else {
              hlComplete = false;
            }
            if (curFg != null) {
              if (!fcSeen) { fcSeen = true; fcColor = curFg; }
              else if (curFg !== fcColor) fcMixed = true;
            } else {
              fcComplete = false;
            }
          }
        }
      })(nodes, false, null, null);

      return {
        highlightActive: hlComplete && hlSeen && !hlMixed,
        highlightColor: hlMixed ? null : hlColor,
        fontColorActive: fcComplete && fcSeen && !fcMixed,
        fontColor: fcMixed ? null : fcColor,
      };
    }

    /** 依据目标粗/斜体状态包裹 children（不产生嵌套强调） */
    function _wrapEmphasis(children, bold, italic) {
      if (bold && italic) return [A.boldItalic(children)];
      if (bold) return [A.bold(children)];
      if (italic) return [A.italic(children)];
      return children;
    }

    /**
     * 统一处理强调（粗体/斜体）的增删。
     * 关键：bold/italic/bold_italic 容器在此处被“扁平化”为叶子级别的粗/斜状态，
     * 绝不产生“强调套强调”的嵌套（否则粗体/斜体/粗斜体的星号序列化会歧义并污染源码，
     * 例如 bold{bold_italic{text}} 会被序列化成多个连续星号之类）。
     * 其它容器（highlight/font_color 等）保持不变，仅递归其 children。
     */
    function _emphasis(nodes, mode, inBold, inItalic) {
      inBold = !!inBold;
      inItalic = !!inItalic;
      var out = [];
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var t = n.type;
        if (t === "bold" || t === "italic" || t === "bold_italic") {
          var curBold = (t === "bold" || t === "bold_italic");
          var curItalic = (t === "italic" || t === "bold_italic");
          out = out.concat(_emphasis(n.children || [], mode, inBold || curBold, inItalic || curItalic));
        } else if (n.children && n.children.length) {
          out.push(cloneInlineNode(n, _emphasis(n.children, mode, inBold, inItalic)));
        } else {
          var fb = inBold, fi = inItalic;
          if (mode === "bold") fb = true;
          else if (mode === "nobold") fb = false;
          else if (mode === "italic") fi = true;
          else if (mode === "noitalic") fi = false;
          out = out.concat(_wrapEmphasis([n], fb, fi));
        }
      }
      return mergeAdjacentInline(out);
    }

    /** 递归给所有叶子套上粗体 */
    function _applyBold(nodes) { return _emphasis(nodes, "bold", false, false); }

    /** 递归去除粗体（bold_italic 退化为 italic） */
    function _removeBold(nodes) { return _emphasis(nodes, "nobold", false, false); }

    /** 递归给所有叶子套上斜体 */
    function _applyItalic(nodes) { return _emphasis(nodes, "italic", false, false); }

    /** 递归去除斜体（bold_italic 退化为 bold） */
    function _removeItalic(nodes) { return _emphasis(nodes, "noitalic", false, false); }

    /** 去除范围内所有 highlight 包裹（保留内部内容与其它样式；fgColor 转回 font_color 保留前景色） */
    function _stripHighlight(nodes) {
      var out = [];
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.type === "highlight") {
          var stripped = _stripHighlight(n.children);
          if (n.fgColor) stripped = [A.fontColor(n.fgColor, stripped)];
          out = out.concat(stripped);
        } else if (n.children && n.children.length) {
          out.push(cloneInlineNode(n, _stripHighlight(n.children)));
        } else {
          out.push(n);
        }
      }
      return mergeAdjacentInline(out);
    }

    /**
     * 剥离 highlight / font_color 容器，同时提取全选区统一的背景色/前景色。
     * bg/fg 仅在“所有可见叶子都具备且颜色一致”时为非 null；children 为剥离后的 inline 树。
     */
    function _stripColorStyles(nodes) {
      var bg = null, fg = null, bgOk = true, fgOk = true, bgSeen = false, fgSeen = false;

      var stripped = (function walk(list, curBg, curFg) {
        var out = [];
        for (var i = 0; i < list.length; i++) {
          var n = list[i];
          if (n.type === "highlight") {
            out = out.concat(walk(n.children || [],
              (n.color == null) ? curBg : n.color,
              (n.fgColor == null) ? curFg : n.fgColor));
          } else if (n.type === "font_color") {
            out = out.concat(walk(n.children || [], curBg,
              (n.color == null) ? curFg : n.color));
          } else if (n.children && n.children.length) {
            out.push(cloneInlineNode(n, walk(n.children, curBg, curFg)));
          } else {
            if (curBg == null) bgOk = false;
            else if (!bgSeen) { bgSeen = true; bg = curBg; }
            else if (curBg !== bg) bgOk = false;
            if (curFg == null) fgOk = false;
            else if (!fgSeen) { fgSeen = true; fg = curFg; }
            else if (curFg !== fg) fgOk = false;
            out.push(n);
          }
        }
        return out;
      })(nodes, null, null);

      return {
        bg: (bgOk && bgSeen) ? bg : null,
        fg: (fgOk && fgSeen) ? fg : null,
        children: mergeAdjacentInline(stripped),
      };
    }

    /** 高亮重着色：优先合并为简洁 [[\h:bg:fg]]；无统一前景色时退回嵌套包裹 */
    function _applyHighlight(nodes, color) {
      var st = _stripColorStyles(nodes);
      if (st.fg != null) return [A.highlight(color || null, st.fg, st.children)];
      return [A.highlight(color || null, null, _stripHighlight(nodes))];
    }

    /** 去除范围内所有 font_color 包裹 */
    function _stripFontColor(nodes) {
      var out = [];
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.type === "font_color") out = out.concat(_stripFontColor(n.children));
        else if (n.children && n.children.length) out.push(cloneInlineNode(n, _stripFontColor(n.children)));
        else out.push(n);
      }
      return mergeAdjacentInline(out);
    }

    /** 字体颜色重着色：若存在统一高亮则合并为 [[\h:bg:fg]]；否则退回嵌套包裹 */
    function _applyFontColor(nodes, color) {
      var st = _stripColorStyles(nodes);
      if (st.bg != null) return [A.highlight(st.bg, color || "red", st.children)];
      return [A.fontColor(color || "red", _stripFontColor(nodes))];
    }

    /** 一组 inline 的可见文本总长度 */
    function renderedLenOfNodes(nodes) {
      var total = 0;
      for (var i = 0; i < nodes.length; i++) total += M.renderedLen(nodes[i]);
      return total;
    }

    /** 可见文本偏移 → inline 树中的 {nodePath,offset}（相对 nodes）。
     * preferEnd=true 时，恰好落在某节点结束边界的偏移归属下一节点开头（用于选区
     * 起点：保证样式应用后选区起点精确落在 middle 首个可见字符前，不残留前一
     * 节点，避免公式/高亮等边界处选区漂移）；否则归属当前节点末尾。 */
    function renderedOffsetToPath(nodes, renderedOffset, preferEnd) {
      var total = 0;
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var len = M.renderedLen(n);
        if (renderedOffset <= total + len) {
          var atEnd = renderedOffset === total + len;
          // 边界归属：preferEnd 且存在下一节点时跳过当前节点，落下一节点开头
          if (atEnd && preferEnd && i + 1 < nodes.length) {
            total += len;
            continue;
          }
          var inner = renderedOffset - total;
          if (n.type === "text") return { nodePath: [i], offset: inner };
          if (n.children && n.children.length) {
            var sub = renderedOffsetToPath(n.children, inner, preferEnd);
            if (sub) return { nodePath: [i].concat(sub.nodePath), offset: sub.offset };
            // 偏移恰好越过子节点树末尾：归属容器内最后一个叶子末尾
            var lp = lastTextPath(n.children);
            if (lp) return { nodePath: [i].concat(lp.path), offset: lp.offset };
            return { nodePath: [i], offset: inner };
          }
          return { nodePath: [i], offset: inner };
        }
        total += len;
      }
      return null;
    }

    /** 序列化 inline 节点数组，便于样式调试日志 */
    function _fmtNodes(nodes, depth) {
      if (!nodes) return "null";
      if (!depth) depth = 0;
      if (depth > 6) return "...";
      var parts = [];
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (!n) { parts.push("?"); continue; }
        var t = n.type;
        var extra = "";
        if (t === "text") extra = JSON.stringify(n.content);
        else if (t === "highlight") extra = "color=" + (n.color || "null") + ",fg=" + (n.fgColor || "null");
        else if (t === "font_color") extra = "color=" + (n.color || "null");
        else if (t === "wiki_link") extra = "target=" + (n.target || n.id || "?");
        if (n.children && n.children.length) {
          parts.push(t + (extra ? "[" + extra + "]" : "") + "{" + _fmtNodes(n.children, depth + 1) + "}");
        } else {
          parts.push(t + (extra ? "[" + extra + "]" : ""));
        }
      }
      return parts.join(",");
    }

    function _extractSelectionMiddle(range) {
      log("STYLE", "_extract range=" + (range ? (range.collapsed ? "collapsed" : "sel") : "null"));
      var start = M.domToAst(range.startContainer, range.startOffset);
      var end = M.domToAst(range.endContainer, range.endOffset);
      log("STYLE", "_extract start=" + _fmtCursor(start) + "  end=" + _fmtCursor(end));
      if (!start || !end || start.blockIndex !== end.blockIndex) {
        log("STYLE", "_extract FAIL: invalid/cross-block start=" + (start ? start.blockIndex : "null") + " end=" + (end ? end.blockIndex : "null"));
        return null;
      }
      var block = _doc.blocks[start.blockIndex];
      if (!block) return null;

      var isList = block.type === "list";
      var isQuote = block.type === "blockquote";
      var root, startPath, endPath, itemIdx, quoteIdx;
      if (isList) {
        if (!start.nodePath || !end.nodePath || !start.nodePath.length || !end.nodePath.length) return null;
        itemIdx = start.nodePath[0];
        if (itemIdx !== end.nodePath[0]) return null;
        var item = block.items && block.items[itemIdx];
        if (!item) return null;
        root = item.children || [];
        startPath = start.nodePath.slice(1);
        endPath = end.nodePath.slice(1);
      } else if (isQuote) {
        // 引用块：block.children 是块级段落，需下钻到光标所在段落的 inline 树，
        // 否则会把段落节点当作内联节点处理，导致 AST 非法嵌套、文本丢失
        if (!start.nodePath || !end.nodePath || !start.nodePath.length || !end.nodePath.length) return null;
        quoteIdx = start.nodePath[0];
        if (quoteIdx !== end.nodePath[0]) { log("STYLE", "_extract FAIL: 跨引用段"); return null; }
        var innerBlock = block.children && block.children[quoteIdx];
        if (!innerBlock || !innerBlock.children || !innerBlock.children.length) {
          log("STYLE", "_extract FAIL: 引用段为空/无效");
          return null;
        }
        if (NON_EDITABLE[innerBlock.type]) { log("STYLE", "_extract FAIL: 引用段不可编辑"); return null; }
        root = innerBlock.children;
        startPath = start.nodePath.slice(1);
        endPath = end.nodePath.slice(1);
      } else {
        itemIdx = 0;
        quoteIdx = 0;
        root = block.children || [];
        startPath = start.nodePath || [];
        endPath = end.nodePath || [];
      }

      var splitEnd = splitInlineAt(root, endPath, end.offset);
      if (!splitEnd) { log("STYLE", "_extract FAIL splitEnd"); return null; }
      var splitStart = splitInlineAt(splitEnd.left, startPath, start.offset);
      if (!splitStart || !splitStart.right.length) { log("STYLE", "_extract FAIL splitStart(right empty)"); return null; }

      log("STYLE", "_extract before=[" + _fmtNodes(splitStart.left) + "]");
      log("STYLE", "_extract middle=[" + _fmtNodes(splitStart.right) + "]");
      log("STYLE", "_extract after=[" + _fmtNodes(splitEnd.right) + "]");

      return {
        start: start,
        blockIndex: start.blockIndex,
        block: block,
        isList: isList,
        isQuote: isQuote,
        itemIdx: itemIdx,
        quoteIdx: quoteIdx,
        before: splitStart.left,
        middle: splitStart.right,
        after: splitEnd.right,
      };
    }

    /**
     * 样式变换：根据 formatType 对 middle 应用/移除样式，返回新节点数组。
     * 粗体/斜体默认按「全选区所有叶子都有才移除，否则统一应用」切换；
     * 跨 block 时由 _commitMultiStyle 预先按整个选区判定 forceMode（"apply"/"remove"），
     * 保证「原本加粗的保持不变，其余统一加粗；再点一次才全部取消」。
     */
    function _transformMiddle(formatType, color, middle, forceMode) {
      if (formatType === "bold") {
        if (forceMode) return forceMode === "apply" ? _applyBold(middle) : _removeBold(middle);
        return _everyLeafHasStyle(middle, _isBoldNode, false) ? _removeBold(middle) : _applyBold(middle);
      }
      if (formatType === "italic") {
        if (forceMode) return forceMode === "apply" ? _applyItalic(middle) : _removeItalic(middle);
        return _everyLeafHasStyle(middle, _isItalicNode, false) ? _removeItalic(middle) : _applyItalic(middle);
      }
      if (formatType === "highlight") return _applyHighlight(middle, color);
      if (formatType === "fontcolor") return _applyFontColor(middle, color);
      if (formatType === "unhighlight") return _stripHighlight(middle);
      return _stripFontColor(middle);
    }

    /** 对单个选区上下文应用样式并写回 AST；返回选区起止绝对坐标（不 commit、不恢复选区） */
    function _applyStyleToBlock(ctx, formatType, color, forceMode) {
      // 必须先于 mergeAdjacentInline 计算 before/middle 的渲染长度！
      // mergeAdjacentInline 会原地把相邻样式节点合并进第一个节点（共享对象引用），
      // 合并后再读 ctx.before/ctx.middle 会得到被污染的整块长度，
      // 导致 selStart/selEnd 错位 → restoreSelection 恢复的选区偏移错误 →
      // 笔刷链（_applyBrushToRange 逐样式重取选区）后续样式应用到错误范围（"刷覆盖不了"）。
      var selStartRendered = renderedLenOfNodes(ctx.before);
      var selEndRendered = selStartRendered + renderedLenOfNodes(ctx.middle);
      var transformed = _transformMiddle(formatType, color, ctx.middle, forceMode);
      var merged = mergeAdjacentInline(ctx.before.concat(transformed).concat(ctx.after));
      if (ctx.isList) ctx.block.items[ctx.itemIdx].children = merged;
      else if (ctx.isQuote) ctx.block.children[ctx.quoteIdx].children = merged;
      else ctx.block.children = merged;

      // selStart 用 preferEnd=true：边界偏移归属下一节点开头，确保选区起点精确含住
      // middle 首个可见字符（如公式前的 italic 边界，避免选区起点残留上一节点导致
      // 后续样式链把额外文本卷入）；selEnd 保持归属当前节点末尾（含住 middle 尾部）。
      var selStart = renderedOffsetToPath(merged, selStartRendered, true);
      var selEnd = renderedOffsetToPath(merged, selEndRendered, false);
      if (!selEnd) {
        // lastTextPath 返回 {path, offset}，需归一化后再使用（不能直接读 .nodePath）
        var lp = lastTextPath(merged);
        selEnd = lp ? { nodePath: lp.path, offset: lp.offset } : null;
      }
      if (!selStart) selStart = selEnd;

      var prefix = ctx.isList ? [ctx.itemIdx] : (ctx.isQuote ? [ctx.quoteIdx] : []);
      return {
        selStart: { nodePath: prefix.concat(selStart.nodePath), offset: selStart.offset },
        selEnd: { nodePath: prefix.concat(selEnd.nodePath), offset: selEnd.offset },
      };
    }

    /** 单 block 样式应用：变换 + commit + 恢复选区 */
    function _commitSingleStyle(ctx, formatType, color, forceApply) {
      if (NON_EDITABLE[ctx.block.type]) return { ok: false, message: "该内容不可编辑" };
      var preCursor = cloneCursor(ctx.start);
      log("STYLE", "single before=[" + _fmtNodes(ctx.before) + "] middle=[" + _fmtNodes(ctx.middle) + "] after=[" + _fmtNodes(ctx.after) + "]");
      var sel = _applyStyleToBlock(ctx, formatType, color, forceApply ? "apply" : undefined);
      log("STYLE", "single selStart=" + _fmtCursor(sel.selStart) + " selEnd=" + _fmtCursor(sel.selEnd));
      beginUndo("format", preCursor, true);
      var ok = commitSelection(ctx.block, ctx.blockIndex, sel.selStart, sel.selEnd);
      log("STYLE", "single commit ok=" + ok);
      if (ok) recordGroup("format", { blockIndex: ctx.blockIndex, nodePath: sel.selEnd.nodePath, offset: sel.selEnd.offset });
      return { ok: ok, message: ok ? "" : "样式应用失败" };
    }

    /** 跨 block 样式应用：逐块变换，作为一个撤销单元提交，最后恢复跨块选区 */
    function _commitMultiStyle(formatType, color, range, forceApply) {
      var start = M.domToAst(range.startContainer, range.startOffset);
      var end = M.domToAst(range.endContainer, range.endOffset);
      log("STYLE", "multi domToAst start=" + (start ? JSON.stringify(start) : "null") + " end=" + (end ? JSON.stringify(end) : "null"));
      if (!start || !end || start.blockIndex >= end.blockIndex) {
        return { ok: false, message: "选区边界包含不可拆分元素或跨段落" };
      }

      var infos = [];
      for (var bi = start.blockIndex; bi <= end.blockIndex; bi++) {
        var block = _doc.blocks[bi];
        if (!block) return { ok: false, message: "选区包含无效块" };
        if (NON_EDITABLE[block.type]) return { ok: false, message: "选区包含不可编辑内容（表格/代码/公式等）" };
        if (block.type === "list") return { ok: false, message: "暂不支持跨列表选区的样式应用" };
        if (block.type === "blockquote") return { ok: false, message: "暂不支持跨引用块边界的样式应用" };

        var before = [], middle = [], after = [];
        if (bi === start.blockIndex) {
          var startChildren = block.children || [];
          if (!startChildren.length) {
            // 起点块是空行（nodePath=[] off=0）：无内容可拆，middle 为空
            before = []; middle = []; after = [];
          } else {
            var sp = splitInlineAt(startChildren, start.nodePath || [], start.offset);
            if (!sp) return { ok: false, message: "选区边界不可拆分" };
            before = sp.left; middle = sp.right; after = [];
          }
        } else if (bi === end.blockIndex) {
          var endChildren = block.children || [];
          if (!endChildren.length) {
            // 终点块是空行（nodePath=[] off=0）：选区延伸到行尾，无内容可拆
            before = []; middle = []; after = [];
          } else {
            var ep = splitInlineAt(endChildren, end.nodePath || [], end.offset);
            if (!ep) return { ok: false, message: "选区边界不可拆分" };
            before = []; middle = ep.left; after = ep.right;
          }
        } else {
          middle = (block.children || []).slice();
        }
        infos.push({ blockIndex: bi, block: block, isList: false, itemIdx: 0, before: before, middle: middle, after: after });
      }

      log("STYLE", "multi blocks=" + infos.length + " start=" + start.blockIndex + " end=" + end.blockIndex);

      // 全局判定粗体/斜体：以整个选区的叶子状态决定 apply / remove，
      // 避免「A 段全加粗、B 段混合」时 A 段被误移除
      var allMiddle = [];
      for (var m = 0; m < infos.length; m++) {
        if (infos[m].middle.length) allMiddle = allMiddle.concat(infos[m].middle);
      }
      var forceMode = null;
      if (forceApply) {
        forceMode = "apply";
      } else if (formatType === "bold") {
        forceMode = _everyLeafHasStyle(allMiddle, _isBoldNode, false) ? "remove" : "apply";
      } else if (formatType === "italic") {
        forceMode = _everyLeafHasStyle(allMiddle, _isItalicNode, false) ? "remove" : "apply";
      }

      beginUndoGroup();
      var firstSel = null, firstSelBlock = -1, lastSel = null, lastSelBlock = -1, touched = 0;
      for (var i = 0; i < infos.length; i++) {
        var ctx = infos[i];
        if (!ctx.middle.length) continue;
        var sel = _applyStyleToBlock(ctx, formatType, color, forceMode);
        spliceBlockSource(ctx.blockIndex, G.generateBlock(ctx.block));
        reRenderBlock(ctx.blockIndex);
        if (firstSel === null) { firstSel = sel.selStart; firstSelBlock = ctx.blockIndex; }
        lastSel = sel.selEnd; lastSelBlock = ctx.blockIndex;
        touched++;
      }
      renderEditor(state.doc);
      markDirty();
      endUndoGroup();

      if (touched && firstSel && lastSel) {
        restoreSelectionMulti(firstSelBlock, firstSel.nodePath, firstSel.offset, lastSelBlock, lastSel.nodePath, lastSel.offset);
      }
      log("STYLE", "multi touched=" + touched + " ok=" + (touched > 0));
      return { ok: touched > 0, message: touched > 0 ? "" : "样式应用失败" };
    }

    /**
     * 对预览区选中的文字应用样式（加粗/斜体默认切换，高亮/字体颜色重着色并合并）。
     * 支持同一 block 及跨 block（列表跨 block 暂不支持）。
     * @param {string} formatType
     * @param {string|null} color
     * @param {Range} range
     * @param {boolean} [forceApply] — 强制「应用」而非切换（画笔涂抹使用，已有同样式文字保持不取消）
     */
    function applyStyle(formatType, color, range, forceApply) {
      if (!_isSupportedFormat(formatType)) return { ok: false, message: "不支持的样式类型" };
      log("STYLE", "applyStyle fmt=" + formatType + " color=" + (color || "null") + (forceApply ? " force=apply" : ""));

      var single = _extractSelectionMiddle(range);
      if (single) return _commitSingleStyle(single, formatType, color, forceApply);
      return _commitMultiStyle(formatType, color, range, forceApply);
    }

    /**
     * 删除预览区选中的文字（作为单个撤销单元）。
     * 单 block（列表则同一 item）走 deleteSelectionSingle；
     * 跨 block 走 deleteSelectionMulti（合并删除）。
     * @param {Range} range — 浏览器选区 Range
     * @returns {boolean}
     */
    function deleteSelection(range) {
      var ctx = _extractSelectionMiddle(range);
      if (ctx) return deleteSelectionSingle(ctx);
      return deleteSelectionMulti(range);
    }

    function deleteSelectionSingle(ctx) {
      if (NON_EDITABLE[ctx.block.type]) return false;

      var preCursor = cloneCursor(ctx.start);
      var merged = mergeAdjacentInline(ctx.before.concat(ctx.after));
      if (ctx.isList) ctx.block.items[ctx.itemIdx].children = merged;
      else if (ctx.isQuote) ctx.block.children[ctx.quoteIdx].children = merged;
      else ctx.block.children = merged;

      // 光标恢复到删除位置（选区起点 = before 末尾）
      var selRendered = renderedLenOfNodes(ctx.before);
      var cursorRel = renderedOffsetToPath(merged, selRendered);
      if (!cursorRel) {
        var lp = lastTextPath(merged);
        cursorRel = lp ? { nodePath: lp.path, offset: lp.offset } : { nodePath: [], offset: 0 };
      }
      var prefix = ctx.isList ? [ctx.itemIdx] : (ctx.isQuote ? [ctx.quoteIdx] : []);
      var cursor = {
        blockIndex: ctx.blockIndex,
        nodePath: prefix.concat(cursorRel.nodePath || []),
        offset: cursorRel.offset,
      };

      beginUndo("deleteSelection", preCursor, true);
      var ok = commit(ctx.block, cursor);
      if (ok) recordGroup("deleteSelection", cursor);
      return ok;
    }

    /**
     * 跨 block 删除选区：保留首块选区前的内容 + 末块选区后的内容，
     * 合并为一个 block（沿用首块类型），中间的 block（含空行）整段删除。
     * 整段作为单个撤销单元。
     */
    function deleteSelectionMulti(range) {
      var start = M.domToAst(range.startContainer, range.startOffset);
      var end = M.domToAst(range.endContainer, range.endOffset);
      if (!start || !end || start.blockIndex >= end.blockIndex) return false;

      // 校验范围内所有 block 均可编辑（跨列表暂不支持）
      for (var bi = start.blockIndex; bi <= end.blockIndex; bi++) {
        var blk = _doc.blocks[bi];
        if (!blk) return false;
        if (NON_EDITABLE[blk.type]) return false;
        if (blk.type === "list") return false;
        if (blk.type === "blockquote") return false;
      }

      var startBlock = _doc.blocks[start.blockIndex];
      var endBlock = _doc.blocks[end.blockIndex];
      var preCursor = cloneCursor(start);

      // 拆分首块左半、末块右半
      var sp = splitInlineAt(startBlock.children || [], start.nodePath || [], start.offset);
      var ep = splitInlineAt(endBlock.children || [], end.nodePath || [], end.offset);
      if (!sp || !ep) return false;

      var before = sp.left;
      var after = ep.right;
      var joined = mergeAdjacentInline(before.concat(after));

      // 结果 block 沿用首块类型（heading 保留级别）；全部删空则退化为空行
      var newBlock = startBlock.type === "heading"
        ? A.heading(startBlock.level, joined)
        : A.paragraph(joined);
      var newLines = joined.length ? [G.generateBlock(newBlock)] : [""];

      // 计算要替换的源码行范围（0-based）
      var startSrc = M.astToSrc(start.blockIndex, start.nodePath || [], start.offset);
      var endSrc = M.astToSrc(end.blockIndex, end.nodePath || [], end.offset);
      if (!startSrc || !endSrc) return false;
      var startLine = startSrc.line;
      var endLine = endSrc.line;

      // 新光标：合并处（before 末尾）
      var beforeLen = renderedLenOfNodes(before);
      var cursorRel = joined.length ? renderedOffsetToPath(joined, beforeLen) : null;
      var newCursor = cursorRel
        ? { blockIndex: start.blockIndex, nodePath: cursorRel.nodePath, offset: cursorRel.offset }
        : { blockIndex: start.blockIndex, nodePath: [], offset: 0 };

      log("STYLE", "deleteMulti blocks=" + (end.blockIndex - start.blockIndex + 1) +
        " srcLines=[" + startLine + "," + endLine + "] newSrc=" + JSON.stringify(newLines[0]));
      return commitRange(startLine, endLine, newLines, newCursor, preCursor, "deleteSelection");
    }

    /** 供工具栏读取当前选区的样式状态（active 指示） */
    function getSelectionStyles(range) {
      var ctx = _extractSelectionMiddle(range);
      if (!ctx) return null;
      var cs = _detectColorState(ctx.middle);
      return {
        bold: _everyLeafHasStyle(ctx.middle, _isBoldNode, false),
        italic: _everyLeafHasStyle(ctx.middle, _isItalicNode, false),
        highlightActive: cs.highlightActive,
        highlightColor: cs.highlightColor,
        fontColorActive: cs.fontColorActive,
        fontColor: cs.fontColor,
      };
    }

    return {
      insertText: insertText,
      backspace: backspace,
      deleteForward: deleteForward,
      splitParagraph: splitParagraph,
      revertBlock: revertBlock,
      applyStyle: applyStyle,
      getSelectionStyles: getSelectionStyles,
      deleteSelection: deleteSelection,
      beginUndoGroup: beginUndoGroup,
      endUndoGroup: endUndoGroup,
      undo: undo,
      redo: redo,
      resetHistory: resetHistory,
    };
  })();

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
      // 图片右键：替换图片 / 删除图片（仅删引用）
      const imgEl = e.target.closest("img.-preview-image");
      if (imgEl) {
        e.preventDefault();
        const blockEl = imgEl.closest(".-image-block");
        const lineNum = blockEl ? +(blockEl.getAttribute("data--src-line") || 0) : 0;
        if (lineNum > 0) {
          e.stopPropagation();
          showImageContextMenu(e.clientX, e.clientY, lineNum);
        }
        return;
      }
      if (e.target.closest(".memoria-link, .-wikilink, a[href]")) return;
      if (!state.currentPath) return;
      const info = getSelectionInContainer(preview);
      if (!info) {
        // 无选中文本（光标折叠）→ 提供「粘贴」「插入图片」
        if (!syncPreviewCursorForPaste()) return;
        const insLine = previewCursorSourceLine();
        MemoriaLinkContextMenu.showForCursor(e, {
          onPaste: pasteAtCursor,
          onInsertImage: () => startInsertImage(insLine || undefined),
        });
        return;
      }
      // 捕获选区，供点击菜单项后（contenteditable 失焦）的样式编辑使用
      capturePreviewSelection();
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
        onApplyStyle: (formatType, color) => applyFormat(formatType, color),
      });
    });
  }

  /** 折叠光标右键：用当前浏览器选区同步 EH.cursorAST，供「粘贴」定位 */
  function syncPreviewCursorForPaste() {
    const M = window.MemoriaMapper;
    const EH = window.MemoriaEditHandler;
    const preview = $("#preview");
    const sel = window.getSelection();
    if (!M || !EH || !preview || !sel || !sel.rangeCount) return false;
    const range = sel.getRangeAt(0);
    if (!range.collapsed || !preview.contains(range.startContainer)) return false;
    const ast = M.domToAst(range.startContainer, range.startOffset);
    if (!ast) return false;
    EH.cursorAST = {
      blockIndex: ast.blockIndex,
      nodePath: (ast.nodePath || []).slice(),
      offset: ast.offset,
    };
    return true;
  }

  /** 读取剪贴板并在光标位置粘贴（多行文本逐行拆分插入） */
  async function pasteAtCursor() {
    let text = "";
    try {
      text = (await navigator.clipboard.readText()) || "";
    } catch (_) {
      text = "";
    }
    if (!text) {
      setStatus("剪贴板为空或无法读取");
      return;
    }

    const EditSync = window.MemoriaEditSync;
    if (!EditSync || typeof EditSync.insertText !== "function") {
      setStatus("编辑器未就绪");
      return;
    }

    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    // 作为单个撤销单元：分组包裹，子操作（insertText/splitParagraph）不各自入栈
    if (typeof EditSync.beginUndoGroup === "function") EditSync.beginUndoGroup();
    if (!EditSync.insertText(lines[0])) {
      if (typeof EditSync.endUndoGroup === "function") EditSync.endUndoGroup();
      setStatus("粘贴失败（当前位置不可编辑）");
      return;
    }
    for (let i = 1; i < lines.length; i++) {
      EditSync.splitParagraph();
      if (lines[i]) EditSync.insertText(lines[i]);
    }
    if (typeof EditSync.endUndoGroup === "function") EditSync.endUndoGroup();
    setStatus("已粘贴");
  }

  /* ── Format toolbar ── */
  let _pendingPreviewRange = null;

  /** 在 mousedown 阶段捕获预览区非折叠选区（点击工具栏按钮会导致 contenteditable 失焦） */
  function capturePreviewSelection() {
    const sel = window.getSelection();
    const preview = $("#preview");
    if (!sel || !sel.rangeCount || !preview) { _pendingPreviewRange = null; return; }
    const range = sel.getRangeAt(0);
    if (range.collapsed || !preview.contains(range.startContainer) || !preview.contains(range.endContainer)) {
      _pendingPreviewRange = null;
      return;
    }
    _pendingPreviewRange = range.cloneRange();
  }

  /** 序列化 DOM Range，便于样式调试日志 */
  function _describeRange(r) {
    if (!r) return "null";
    function nd(n) {
      if (!n) return "null";
      if (n.nodeType === 3) return "#text=" + JSON.stringify(n.data.slice(0, 30));
      if (n.nodeType === 1) return "<" + n.nodeName.toLowerCase() + ">";
      return "nodeType=" + n.nodeType;
    }
    return "collapsed=" + r.collapsed + " [" + nd(r.startContainer) + ":" + r.startOffset + "] -> [" + nd(r.endContainer) + ":" + r.endOffset + "]";
  }

  /** 取得当前应作用于预览区的选区（优先实时选区，其次 mousedown 阶段捕获的选区） */
  function getPreviewSelectionRange() {
    const preview = $("#preview");
    if (!preview) return null;
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
      const r = sel.getRangeAt(0);
      if (!r.collapsed && preview.contains(r.startContainer) && preview.contains(r.endContainer)) {
        log("STYLE", "getPreviewSelectionRange -> live " + _describeRange(r));
        return r;
      }
    }
    if (_pendingPreviewRange) {
      const r = _pendingPreviewRange;
      if (!r.collapsed && preview.contains(r.startContainer) && preview.contains(r.endContainer)) {
        log("STYLE", "getPreviewSelectionRange -> pending " + _describeRange(r));
        return r;
      }
    }
    log("STYLE", "getPreviewSelectionRange -> null (no non-collapsed selection in preview)");
    return null;
  }

  /** 切换格式按钮/色块的 active 状态 */
  function _setSwatchActive(selector, attr, activeValue) {
    document.querySelectorAll(selector).forEach((sw) => {
      const v = sw.getAttribute(attr);
      sw.classList.toggle("active", activeValue !== undefined && v === activeValue);
    });
  }

  function _resetFormatToolbarState() {
    const b = document.querySelector('.-fmt-btn[data-fmt="bold"]');
    const i = document.querySelector('.-fmt-btn[data-fmt="italic"]');
    if (b) b.classList.remove("active");
    if (i) i.classList.remove("active");
    _setSwatchActive(".-hl-swatch", "data-hl-color", undefined);
    _setSwatchActive(".-fc-swatch", "data-fc-color", undefined);
  }

  /** 根据预览区实时选区刷新工具栏 active 指示 */
  function updateFormatToolbarState() {
    // 画笔激活：工具栏显示画笔已选样式（B/I 高亮 + 对应色块加框标识）。
    // 高亮 / 文字颜色两个色板、B/I 各自独立显示选中状态，右键可单独取消。
    if (_brush) {
      const b = document.querySelector('.-fmt-btn[data-fmt="bold"]');
      const i = document.querySelector('.-fmt-btn[data-fmt="italic"]');
      if (b) b.classList.toggle("active", !!_brush.bold);
      if (i) i.classList.toggle("active", !!_brush.italic);
      _setSwatchActive(".-hl-swatch", "data-hl-color", _brush.highlight);
      _setSwatchActive(".-fc-swatch", "data-fc-color", _brush.fontcolor);
      _syncBrushArmed();
      return;
    }
    const EditSync = window.MemoriaEditSync;
    if (!EditSync || typeof EditSync.getSelectionStyles !== "function") { _resetFormatToolbarState(); return; }
    const preview = $("#preview");
    const sel = window.getSelection();
    if (!preview || !sel || !sel.rangeCount) { _resetFormatToolbarState(); return; }
    const r = sel.getRangeAt(0);
    if (r.collapsed || !preview.contains(r.startContainer) || !preview.contains(r.endContainer)) {
      _resetFormatToolbarState();
      return;
    }
    const styles = EditSync.getSelectionStyles(r);
    if (!styles) { _resetFormatToolbarState(); return; }

    const b = document.querySelector('.-fmt-btn[data-fmt="bold"]');
    const i = document.querySelector('.-fmt-btn[data-fmt="italic"]');
    if (b) b.classList.toggle("active", !!styles.bold);
    if (i) i.classList.toggle("active", !!styles.italic);
    _setSwatchActive(".-hl-swatch", "data-hl-color", styles.highlightActive ? (styles.highlightColor || "yellow") : undefined);
    _setSwatchActive(".-fc-swatch", "data-fc-color", styles.fontColorActive ? styles.fontColor : undefined);
  }

  // 选区变化时刷新格式工具栏 active 状态（rAF 合并节流）
  let _fmtStateRaf = null;
  document.addEventListener("selectionchange", () => {
    if (_fmtStateRaf) return;
    _fmtStateRaf = requestAnimationFrame(() => {
      _fmtStateRaf = null;
      try { updateFormatToolbarState(); } catch (err) { log("MAP", "sel toolbar ERR " + err); }
      try { _updateAtomicSelectionHighlight(); } catch (err) { log("MAP", "sel highlight ERR " + err); }
    });
  });

  // contentEditable=false 原子块（行内公式 .-math 等）浏览器不渲染原生
  // 选区高亮；检测选区是否覆盖这些原子块，动态加 .-sel-covered 高亮，
  // 让用户涂抹时能看到公式也被选中。
  function _updateAtomicSelectionHighlight() {
    const preview = $("#preview");
    if (!preview) return;
    const atoms = preview.querySelectorAll(".-math");
    if (!atoms.length) return;
    const sel = window.getSelection();
    let r = null;
    let domDesc = "none";
    if (sel && sel.rangeCount && !sel.isCollapsed) {
      const rr = sel.getRangeAt(0);
      if (preview.contains(rr.startContainer) && preview.contains(rr.endContainer)) {
        r = rr;
        domDesc = describeRange(rr);
      }
    }
    let covered = 0;
    for (let i = 0; i < atoms.length; i++) {
      const el = atoms[i];
      let isCovered = false;
      if (r) {
        try {
          const er = document.createRange();
          er.selectNode(el);
          // 相交：选区的 END 在原子块 START 之后 且 选区的 START 在原子块 END 之前
          const c1 = r.compareBoundaryPoints(Range.END_TO_START, er);
          const c2 = r.compareBoundaryPoints(Range.START_TO_END, er);
          isCovered = c1 > 0 && c2 < 0;
          // 兜底：选区边界直接落在公式元素上（点击公式整体选中时，
          // Range 为 [el,0]→[el,1]，边界节点就是公式本身，按节点关系判定）
          if (!isCovered && (r.startContainer === el || r.endContainer === el)) {
            isCovered = true;
          }
          if (isCovered) {
            log("MAP", "selHit cmp=(" + c1 + "," + c2 + ") el=#" + (el.textContent || "").slice(0, 12) + " startIsEl=" + (r.startContainer === el) + " endIsEl=" + (r.endContainer === el));
          }
        } catch (err) { log("MAP", "selHit ERR " + err); }
      }
      el.classList.toggle("-sel-covered", isCovered);
      if (isCovered) covered++;
    }
    log("MAP", "selHighlight sel=" + domDesc + " mathTotal=" + atoms.length + " covered=" + covered);
  }

  /** 选区 Range 简要描述（用于 MAP 日志） */
  function describeRange(r) {
    if (!r) return "null";
    const s = (r.startContainer.nodeType === 3 ? "text#" + (r.startContainer.textContent || "").slice(0, 12) : (r.startContainer.tagName || "?") + "." + (r.startContainer.className || "")) + "@" + r.startOffset;
    const e = (r.endContainer.nodeType === 3 ? "text#" + (r.endContainer.textContent || "").slice(0, 12) : (r.endContainer.tagName || "?") + "." + (r.endContainer.className || "")) + "@" + r.endOffset;
    return "[" + s + " -> " + e + "]";
  }

  function bindFormatToolbar() {
    // 捕获阶段记录预览区选区，避免点击按钮后选区丢失
    const fmtBar = document.querySelector(".-format-bar");
    if (fmtBar && !fmtBar.dataset.selectionGuardBound) {
      fmtBar.dataset.selectionGuardBound = "1";
      fmtBar.addEventListener("mousedown", capturePreviewSelection, true);
    }
    // B and I buttons（已有选区→应用/切换；无选区→进入画笔模式）
    document.querySelectorAll(".-fmt-btn[data-fmt]").forEach((btn) => {
      if (btn.dataset.fmt === "highlight" || btn.dataset.fmt === "fontcolor") return; // handled by dropdown
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const fmt = btn.dataset.fmt;
        if (hasExistingSelection()) {
          applyFormat(fmt);
        } else {
          armBrush(fmt, null);
        }
      });
    });
    // Dropdown toggle
    document.querySelectorAll(".-fmt-dropdown > .-fmt-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const dd = btn.closest(".-fmt-dropdown");
        const wasOpen = dd.classList.contains("open");
        closeAllDropdowns();
        if (!wasOpen) {
          dd.classList.add("open");
          positionDropdown(dd);
        }
      });
    });
    // Highlight color swatches（已有选区→直接应用；无选区→进入画笔模式）
    document.querySelectorAll(".-hl-swatch").forEach((sw) => {
      sw.addEventListener("click", (e) => {
        e.stopPropagation();
        const color = sw.dataset.hlColor;
        if (hasExistingSelection()) {
          applyFormat("highlight", color);
          closeAllDropdowns();
        } else {
          armBrush("highlight", color);
        }
      });
    });
    // Font color swatches（已有选区→直接应用；无选区→进入画笔模式）
    document.querySelectorAll(".-fc-swatch").forEach((sw) => {
      sw.addEventListener("click", (e) => {
        e.stopPropagation();
        const color = sw.dataset.fcColor;
        if (hasExistingSelection()) {
          applyFormat("fontcolor", color);
          closeAllDropdowns();
        } else {
          armBrush("fontcolor", color);
        }
      });
    });
    // 移除样式（无色）
    document.querySelectorAll("[data-hl-none]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        applyFormat("unhighlight");
        closeAllDropdowns();
      });
    });
    document.querySelectorAll("[data-fc-none]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        applyFormat("unfontcolor");
        closeAllDropdowns();
      });
    });
    // 添加颜色（选定后追加到色板，不直接应用）
    document.querySelectorAll("[data-hl-custom]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        addCustomColor("highlight");
      });
    });
    document.querySelectorAll("[data-fc-custom]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        addCustomColor("fontcolor");
      });
    });
    // 渲染已保存的自定义颜色
    renderCustomSwatches("highlight");
    renderCustomSwatches("fontcolor");
    // Close dropdowns on outside click
    document.addEventListener("click", () => closeAllDropdowns());
    // 窗口尺寸变化时重新定位已打开的下拉菜单
    if (!fmtBar || !fmtBar.dataset.resizeBound) {
      window.addEventListener("resize", () => {
        document.querySelectorAll(".-fmt-dropdown.open").forEach((dd) => positionDropdown(dd));
      });
      if (fmtBar) fmtBar.dataset.resizeBound = "1";
    }
  }

  // ---- 应用内颜色选择器（弹层固定在程序窗口内，含确定/取消）----
  let _cp = null;       // 面板 DOM 引用
  let _cpCb = null;     // 完成回调（hex 或 null=取消）
  let _cpH = 0, _cpS = 1, _cpL = 0.5;  // 当前 HSL 状态
  let _cpDrag = false;

  function _hslToHex(h, s, l) {
    s = Math.max(0, Math.min(1, s));
    l = Math.max(0, Math.min(1, l));
    h = ((h % 360) + 360) % 360;
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs((h / 60) % 2 - 1));
    const m = l - c / 2;
    let r = 0, g = 0, b = 0;
    if (h < 60) { r = c; g = x; }
    else if (h < 120) { r = x; g = c; }
    else if (h < 180) { g = c; b = x; }
    else if (h < 240) { g = x; b = c; }
    else if (h < 300) { r = x; b = c; }
    else { r = c; b = x; }
    const to2 = (v) => Math.round((v + m) * 255).toString(16).padStart(2, "0");
    return "#" + to2(r) + to2(g) + to2(b);
  }

  function _hexToHsl(hex) {
    const n = parseInt(hex.slice(1), 16);
    const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0;
    const l = (max + min) / 2;
    const d = max - min;
    if (d !== 0) {
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
      else if (max === g) h = ((b - r) / d + 2) * 60;
      else h = ((r - g) / d + 4) * 60;
    }
    return { h, s, l };
  }

  const _CP_PRESETS = ["#ff0000", "#ff8800", "#ffcc00", "#00cc00", "#00aacc", "#3366ff", "#9900ff", "#ff3399", "#8b4513", "#444444", "#888888", "#ffffff"];

  function ensureColorPicker() {
    if (_cp) return _cp;
    const mask = document.createElement("div");
    mask.className = "-color-picker-mask";
    mask.style.display = "none";
    mask.innerHTML =
      '<div class="-color-picker">' +
      '  <div class="-cp-title">添加自定义颜色</div>' +
      '  <div class="-cp-preview"></div>' +
      '  <div class="-cp-sv"><div class="-cp-cursor"></div></div>' +
      '  <input type="range" class="-cp-hue" min="0" max="360" step="1" value="0">' +
      '  <div class="-cp-presets"></div>' +
      '  <div class="-cp-row">' +
      '    <input type="text" class="-cp-hex" value="#ff0000" spellcheck="false" maxlength="7">' +
      '    <button type="button" class="-cp-cancel">取消</button>' +
      '    <button type="button" class="-cp-ok">确定</button>' +
      "  </div>" +
      "</div>";
    document.body.appendChild(mask);
    const box = mask.firstElementChild;
    const cp = {
      mask, box,
      title: box.querySelector(".-cp-title"),
      preview: box.querySelector(".-cp-preview"),
      sv: box.querySelector(".-cp-sv"),
      cursor: box.querySelector(".-cp-cursor"),
      hue: box.querySelector(".-cp-hue"),
      presets: box.querySelector(".-cp-presets"),
      hex: box.querySelector(".-cp-hex"),
      ok: box.querySelector(".-cp-ok"),
      cancel: box.querySelector(".-cp-cancel")
    };
    // 常用色快捷条
    _CP_PRESETS.forEach((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.style.background = c;
      b.title = c;
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        const h = normalizeHex(c);
        if (!h) return;
        const { h: hh, s: ss, l: ll } = _hexToHsl(h);
        _cpH = hh; _cpS = ss; _cpL = ll;
        _cpUpdate(true);
      });
      cp.presets.appendChild(b);
    });

    function _cpUpdate(updateHex) {
      const hex = _hslToHex(_cpH, _cpS, _cpL);
      cp.sv.style.background =
        "linear-gradient(to top, #000, rgba(0,0,0,0)), linear-gradient(to right, #fff, hsl(" + _cpH + ",100%,50%))";
      cp.cursor.style.left = (_cpS * 100) + "%";
      cp.cursor.style.top = ((1 - _cpL) * 100) + "%";
      if (String(Math.round(_cpH)) !== cp.hue.value) cp.hue.value = String(Math.round(_cpH));
      cp.hue.style.setProperty("---cp-hue-thumb", "hsl(" + Math.round(_cpH) + ", 100%, 50%)");
      cp.preview.style.background = hex;
      if (updateHex && document.activeElement !== cp.hex) cp.hex.value = hex;
    }

    function _cpSetFromPointer(ev) {
      const rect = cp.sv.getBoundingClientRect();
      let x = (ev.clientX - rect.left) / rect.width;
      let y = (ev.clientY - rect.top) / rect.height;
      x = Math.max(0, Math.min(1, x));
      y = Math.max(0, Math.min(1, y));
      _cpS = x;
      _cpL = 1 - y;
      _cpUpdate(true);
    }

    function _cpClose(result) {
      if (_cpDrag) { _cpDrag = false; document.removeEventListener("mousemove", _cpOnMove); document.removeEventListener("mouseup", _cpOnUp); }
      cp.mask.style.display = "none";
      const cb = _cpCb;
      _cpCb = null;
      if (cb) cb(result);
    }

    function _cpOnMove(ev) { if (_cpDrag) _cpSetFromPointer(ev); }
    function _cpOnUp() {
      if (!_cpDrag) return;
      _cpDrag = false;
      document.removeEventListener("mousemove", _cpOnMove);
      document.removeEventListener("mouseup", _cpOnUp);
    }

    cp.sv.addEventListener("mousedown", (e) => {
      e.preventDefault();
      _cpSetFromPointer(e);
      _cpDrag = true;
      document.addEventListener("mousemove", _cpOnMove);
      document.addEventListener("mouseup", _cpOnUp);
    });
    cp.hue.addEventListener("input", () => {
      _cpH = parseFloat(cp.hue.value) || 0;
      _cpUpdate(true);
    });
    cp.hex.addEventListener("input", () => {
      const h = normalizeHex(cp.hex.value);
      if (h) {
        const { h: hh, s: ss, l: ll } = _hexToHsl(h);
        _cpH = hh; _cpS = ss; _cpL = ll;
        _cpUpdate(false);
      }
    });
    cp.hex.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); cp.ok.click(); }
    });
    cp.ok.addEventListener("click", (e) => {
      e.stopPropagation();
      _cpClose(normalizeHex(cp.hex.value));
    });
    cp.cancel.addEventListener("click", (e) => {
      e.stopPropagation();
      _cpClose(null);
    });
    mask.addEventListener("mousedown", (e) => {
      if (e.target === mask) _cpClose(null);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && _cp && _cp.mask.style.display !== "none") {
        e.preventDefault();
        _cpClose(null);
      }
    });
    cp._update = _cpUpdate;
    _cp = cp;
    return cp;
  }

  /** 打开应用内取色面板；确定→onDone(hex)，取消/关闭→onDone(null)。可反复打开 */
  function openColorPicker(title, onDone) {
    const cp = ensureColorPicker();
    closeAllDropdowns();
    _cpCb = onDone;
    cp.title.textContent = title;
    // 初始色：已保存的自定义色最后一个，否则红色
    const first = getCustomColors("fontcolor").concat(getCustomColors("highlight"))[0] || "#ff0000";
    const { h, s, l } = _hexToHsl(first);
    _cpH = h; _cpS = s; _cpL = l;
    cp.mask.style.display = "flex";
    cp.hex.value = first;
    cp._update(true);
    // 不自动聚焦 hex：保持 activeElement 不在 hex 上，SV/色相/常用色操作时 hex 才能实时刷新当前色
  }

  // ---- 自定义颜色管理（添加 / 右键删除 / localStorage 持久化）----
  const HL_CUSTOM_KEY = "-hl-custom-colors";
  const FC_CUSTOM_KEY = "-fc-custom-colors";

  function _customColorKey(kind) {
    return kind === "highlight" ? HL_CUSTOM_KEY : FC_CUSTOM_KEY;
  }

  /** 归一化颜色为 #rrggbb 小写；非法输入返回 null */
  function normalizeHex(c) {
    c = String(c || "").trim().toLowerCase();
    if (/^#[0-9a-f]{6}$/.test(c)) return c;
    if (/^#[0-9a-f]{3}$/.test(c)) {
      return "#" + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
    }
    return null;
  }

  function getCustomColors(kind) {
    try {
      const raw = JSON.parse(localStorage.getItem(_customColorKey(kind)) || "[]");
      if (!Array.isArray(raw)) return [];
      const out = [];
      raw.forEach((c) => {
        const hex = normalizeHex(c);
        if (hex && out.indexOf(hex) === -1) out.push(hex);
      });
      return out;
    } catch (e) {
      return [];
    }
  }

  /** 写入本地缓存 + 程序配置（ui-settings.json 的 customColors 键，磁盘为权威源） */
  function saveCustomColors(kind, colors) {
    try {
      localStorage.setItem(_customColorKey(kind), JSON.stringify(colors));
    } catch (e) { /* ignore */ }
    const next = {};
    ["highlight", "fontcolor"].forEach((k) => {
      next[k] = k === kind ? colors : getCustomColors(k);
    });
    call("save_ui_settings", { customColors: next }).catch(() => {});
  }

  /** 启动时从程序配置同步自定义颜色（磁盘优先，覆盖本地缓存）；并重建色板 */
  async function hydrateCustomColorsFromDisk() {
    try {
      const res = await call("get_ui_settings");
      const cc = res && res.status === "ok" && res.settings && res.settings.customColors;
      if (!cc || typeof cc !== "object") return;
      ["highlight", "fontcolor"].forEach((k) => {
        const list = cc[k];
        if (!Array.isArray(list)) return;
        const clean = [];
        list.forEach((c) => {
          const hex = normalizeHex(c);
          if (hex && clean.indexOf(hex) === -1) clean.push(hex);
        });
        try { localStorage.setItem(_customColorKey(k), JSON.stringify(clean)); } catch (e) { /* ignore */ }
      });
      renderCustomSwatches("highlight");
      renderCustomSwatches("fontcolor");
    } catch (_) { /* 非桌面环境忽略 */ }
  }

  /** 根据背景亮度决定色块文字颜色（黑/白） */
  function swatchTextColor(hex) {
    const n = parseInt(hex.slice(1), 16);
    const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#000" : "#fff";
  }

  // ---- 自定义色块右键菜单（含删除）----
  let _swatchCtxMenu = null;

  function hideSwatchCtxMenu() {
    if (_swatchCtxMenu) {
      _swatchCtxMenu.remove();
      _swatchCtxMenu = null;
    }
  }

  /** 在鼠标位置显示色块右键菜单；点击「删除该颜色」执行删除 */
  function showSwatchCtxMenu(e, hex, kind) {
    hideSwatchCtxMenu();
    const menu = document.createElement("div");
    menu.className = "-context-menu";
    menu.setAttribute("role", "menu");

    const head = document.createElement("button");
    head.type = "button";
    head.className = "-ctx-item disabled";
    head.setAttribute("role", "menuitem");
    head.innerHTML = '<span class="-ctx-head">自定义颜色 ' + hex + "</span>";
    menu.appendChild(head);

    const div = document.createElement("div");
    div.className = "-ctx-divider";
    menu.appendChild(div);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "-ctx-item danger";
    del.setAttribute("role", "menuitem");
    del.textContent = "删除该颜色";
    del.addEventListener("click", (ev) => {
      ev.stopPropagation();
      hideSwatchCtxMenu();
      saveCustomColors(kind, getCustomColors(kind).filter((c) => c !== hex));
      renderCustomSwatches(kind);
      setStatus("已删除自定义颜色 " + hex);
    });
    menu.appendChild(del);

    document.body.appendChild(menu);
    // 定位并防止越界
    menu.style.left = e.clientX + "px";
    menu.style.top = e.clientY + "px";
    const rect = menu.getBoundingClientRect();
    let nx = e.clientX, ny = e.clientY;
    if (nx + rect.width > window.innerWidth) nx = window.innerWidth - rect.width - 4;
    if (ny + rect.height > window.innerHeight) ny = window.innerHeight - rect.height - 4;
    menu.style.left = Math.max(4, nx) + "px";
    menu.style.top = Math.max(4, ny) + "px";
    _swatchCtxMenu = menu;
  }

  // 任意左键点击 / Esc 关闭色块右键菜单（捕获阶段，避免被子元素 stopPropagation 拦截）
  document.addEventListener("click", hideSwatchCtxMenu, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideSwatchCtxMenu();
  });

  /** 重建色板中的自定义颜色块（幂等：先清后建），并绑定 点击=应用 / 右键=菜单 */
  function renderCustomSwatches(kind) {
    const menu = document.querySelector(kind === "highlight" ? ".-hl-colors" : ".-fc-colors");
    if (!menu) return;
    menu.querySelectorAll(".-custom-swatch").forEach((el) => el.remove());
    const noneBtn = menu.querySelector(kind === "highlight" ? "[data-hl-none]" : "[data-fc-none]");
    const dataAttr = kind === "highlight" ? "data-hl-color" : "data-fc-color";
    const fmt = kind === "highlight" ? "highlight" : "fontcolor";
    const colors = getCustomColors(kind);
    colors.forEach((hex) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = (kind === "highlight" ? "-hl-swatch" : "-fc-swatch") + " -custom-swatch";
      btn.setAttribute(dataAttr, hex);
      btn.title = "自定义颜色 " + hex + "（右键菜单可删除）";
      btn.style.backgroundColor = hex;
      btn.style.color = swatchTextColor(hex);
      btn.textContent = "●";
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (hasExistingSelection()) {
          applyFormat(fmt, hex);
          closeAllDropdowns();
        } else {
          armBrush(fmt, hex);
        }
      });
      btn.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        e.stopPropagation();
        showSwatchCtxMenu(e, hex, kind);
      });
      menu.insertBefore(btn, noneBtn);
    });
  }

  /** 打开应用内取色面板；确定后将颜色追加到色板（不直接应用），并进入画笔模式 */
  function addCustomColor(kind) {
    openColorPicker("添加自定义颜色", (hex) => {
      if (!hex) return; // 取消
      const colors = getCustomColors(kind);
      if (colors.indexOf(hex) !== -1) {
        setStatus("颜色 " + hex + " 已在色板中");
        armBrush(kind === "highlight" ? "highlight" : "fontcolor", hex);
        return;
      }
      colors.push(hex);
      saveCustomColors(kind, colors);
      renderCustomSwatches(kind);
      setStatus("已添加自定义颜色 " + hex);
      // 添加成功即进入画笔模式，拖动即可涂抹新颜色
      armBrush(kind === "highlight" ? "highlight" : "fontcolor", hex);
    });
  }

  function closeAllDropdowns() {
    document.querySelectorAll(".-fmt-dropdown.open").forEach((d) => d.classList.remove("open"));
  }

  // ═══════════════════════════════════════════════════════════════
  //  画笔模式：点击颜色后鼠标变画笔，在预览/源码区拖动选择文字即应用目标样式
  // ═══════════════════════════════════════════════════════════════
  let _brush = null; // 多槽位画笔：{ bold: bool, italic: bool, highlight: color|null, fontcolor: color|null }

  /** 画笔样式的中文名 */
  function _brushLabel(fmt) {
    return fmt === "highlight" ? "高亮" :
      fmt === "fontcolor" ? "字体颜色" :
      fmt === "bold" ? "加粗" : "斜体";
  }

  /** 鼠标目标对应的样式类型（B/I/H▾/色▾/对应色块，含自定义色块），否则 null */
  function _targetStyleFmt(t) {
    if (!t || !t.closest) return null;
    if (t.closest('.-fmt-btn[data-fmt="bold"]')) return "bold";
    if (t.closest('.-fmt-btn[data-fmt="italic"]')) return "italic";
    if (t.closest('.-fmt-btn[data-fmt="highlight"], .-hl-swatch')) return "highlight";
    if (t.closest('.-fmt-btn[data-fmt="fontcolor"], .-fc-swatch')) return "fontcolor";
    return null;
  }

  /** 该样式是否已被画笔选中 */
  function _isStyleSelected(fmt) {
    if (!_brush) return false;
    if (fmt === "bold") return !!_brush.bold;
    if (fmt === "italic") return !!_brush.italic;
    if (fmt === "highlight") return !!_brush.highlight;
    if (fmt === "fontcolor") return !!_brush.fontcolor;
    return false;
  }

  /** 画笔中所有已选样式（固定应用顺序：加粗 → 斜体 → 高亮 → 字体颜色） */
  function _brushStyleList() {
    if (!_brush) return [];
    const out = [];
    if (_brush.bold) out.push({ fmt: "bold", color: null });
    if (_brush.italic) out.push({ fmt: "italic", color: null });
    if (_brush.highlight) out.push({ fmt: "highlight", color: _brush.highlight });
    if (_brush.fontcolor) out.push({ fmt: "fontcolor", color: _brush.fontcolor });
    return out;
  }

  /** 已选样式的中文列表（用于状态栏提示） */
  function _brushListLabel() {
    return _brushStyleList().map((s) => _brushLabel(s.fmt)).join("+");
  }

  /** 同步 brush-armed 标识（给每个已选样式对应的格式按钮加高亮） */
  function _syncBrushArmed() {
    document.querySelectorAll(".-fmt-btn.brush-armed").forEach((b) => b.classList.remove("brush-armed"));
    if (!_brush) return;
    ["bold", "italic", "highlight", "fontcolor"].forEach((fmt) => {
      if (_isStyleSelected(fmt)) {
        const el = document.querySelector('.-fmt-btn[data-fmt="' + fmt + '"]');
        if (el) el.classList.add("brush-armed");
      }
    });
  }

  /** 进入画笔模式：选中（或切换）某个样式的槽位，其余已选样式保留 */
  function armBrush(fmt, color) {
    if (!_brush) _brush = { bold: false, italic: false, highlight: null, fontcolor: null };
    if (fmt === "bold") _brush.bold = true;
    else if (fmt === "italic") _brush.italic = true;
    else if (fmt === "highlight") _brush.highlight = color;
    else if (fmt === "fontcolor") _brush.fontcolor = color;
    closeAllDropdowns();
    document.body.classList.add("-brush-active");
    updateFormatToolbarState();
    setStatus("画笔已就绪：可继续点选其他样式，左键拖动涂抹一并应用；右键点击已选样式单独取消");
  }

  /** 全部退出画笔模式（Esc / 右键取消最后一个样式时） */
  function cancelBrush() {
    if (!_brush) return;
    _brush = null;
    document.body.classList.remove("-brush-active");
    document.querySelectorAll(".-fmt-btn.brush-armed").forEach((b) => b.classList.remove("brush-armed"));
    updateFormatToolbarState();
  }

  /** 右键取消「点到的样式」：只清该槽位，其余已选样式保留；全部清空则退出画笔 */
  function unselectBrushStyle(fmt) {
    if (!_brush) return;
    if (fmt === "bold") _brush.bold = false;
    else if (fmt === "italic") _brush.italic = false;
    else if (fmt === "highlight") _brush.highlight = null;
    else if (fmt === "fontcolor") _brush.fontcolor = null;
    if (!_brush.bold && !_brush.italic && !_brush.highlight && !_brush.fontcolor) {
      cancelBrush();
      setStatus("已取消画笔");
      return;
    }
    updateFormatToolbarState();
    setStatus("已取消" + _brushLabel(fmt) + "，其余样式保留");
  }

  /** 是否已存在可应用样式的非折叠选区（预览区实时/捕获选区，或源码编辑器） */
  function hasExistingSelection() {
    if (getPreviewSelectionRange()) return true;
    const sel = window.getSelection();
    const editor = $("#editor");
    if (sel && sel.rangeCount && !sel.getRangeAt(0).collapsed) {
      const r = sel.getRangeAt(0);
      if (editor && editor.contains(r.startContainer) && editor.contains(r.endContainer)) return true;
    }
    return false;
  }

  /** 依次应用画笔中所有已选样式（forceApply：笔刷为「应用」语义，已有同样式不 toggle 取消）；
   *  每次应用后重取实时选区（edit-sync 会恢复选区到新位置） */
  function _applyBrushToRange(ES, firstRange) {
    const styles = _brushStyleList();
    if (!styles.length) return { ok: false, message: "未选择任何样式，请先点击样式按钮或色块" };
    let curRange = firstRange;
    let applied = 0;
    for (let k = 0; k < styles.length; k++) {
      const st = styles[k];
      const res = ES.applyStyle(st.fmt, st.color, curRange, true);
      log("BRUSH", "apply fmt=" + st.fmt + " color=" + st.color + " res=" + JSON.stringify(res));
      if (!res || !res.ok) {
        if (res && res.message) return { ok: applied > 0, message: res.message, applied };
        break;
      }
      applied++;
      const sel = window.getSelection();
      if (!sel || !sel.rangeCount || sel.getRangeAt(0).collapsed) break;
      curRange = sel.getRangeAt(0);
    }
    return { ok: applied > 0, message: applied > 0 ? "" : "样式应用失败", applied };
  }

  /** 画笔 mouseup：预览区内拖动结束 → 应用目标样式（保持画笔可连续涂抹）；右键取消由 contextmenu 捕获阶段处理 */
  function _brushOnMouseUp(e) {
    if (!_brush) return;
    if (e.button !== 0) return;
    if (!e.target || !e.target.closest) return;
    // 色块 / 下拉开关 / 添加颜色 / 取色面板 / 右键菜单：交给各自的 click 处理（重新武装或保持）
    if (e.target.closest(".-hl-swatch, .-fc-swatch, .-hl-custom, .-fc-custom, .-fmt-dropdown > .-fmt-btn, .-color-picker-mask, .-context-menu")) return;
    // 工具栏按钮 / 文档区域之外点击：保持画笔（不取消），可继续回来涂抹；
    // 画笔类型切换由各按钮自身的 click（armBrush 覆盖）负责
    if (e.target.closest(".-fmt-btn, .-view-btn, #block-edit-bar, .-kp-toolbar")) return;
    // 笔刷仅作用于预览区：源码编辑器内涂抹不应用样式（笔刷保持武装，可回到预览继续涂）
    if (!e.target.closest("#preview")) return;

    const sel = window.getSelection();
    if (!sel || !sel.rangeCount || sel.getRangeAt(0).collapsed) {
      setStatus("画笔就绪：左键拖动涂抹应用" + _brushListLabel() + "，右键点击已选样式取消");
      return;
    }
    const r = sel.getRangeAt(0);
    const preview = $("#preview");
    const ES = window.MemoriaEditSync;
    if (preview && preview.contains(r.startContainer) && preview.contains(r.endContainer)) {
      if (ES && typeof ES.applyStyle === "function") {
        const res = _applyBrushToRange(ES, r);
        if (res.ok) {
          setStatus("已应用" + _brushListLabel() + "，继续拖动涂抹或按 Esc 退出");
        } else if (res.message) {
          setStatus(res.message);
        }
      }
    }
  }

  document.addEventListener("mouseup", _brushOnMouseUp);
  // 画笔模式下右键：只取消「右键点到的样式」（已选中的样式槽位），其余已选样式保留；
  // 其他区域右键只屏蔽原生菜单、不取消画笔；自定义色块保留其删除菜单。
  document.addEventListener("contextmenu", (e) => {
    if (!_brush) return;
    const t = e.target;
    if (!t || !t.closest) return;
    // 自定义色块：保留定制删除菜单（画笔不取消，自身 handler 会 preventDefault）
    if (t.closest(".-custom-swatch")) return;
    // 文件树 / 应用内弹窗 / 文件树右键菜单：放行给对应 handler，画笔不拦截
    if (t.closest("#file-tree") || t.closest(".-modal") || t.closest("#" + FT_MENU_ID)) return;
    // 屏蔽原生/其他右键菜单（预览区、工具栏等）
    e.preventDefault();
    e.stopPropagation();
    // 右键点到的样式若已被画笔选中 → 只取消该样式
    const fmt = _targetStyleFmt(t);
    if (fmt && _isStyleSelected(fmt)) {
      unselectBrushStyle(fmt);
    }
  }, true);
  // 格式工具栏 / 取色面板等工具 UI 上右键：屏蔽网页原生右键菜单。
  // 自定义色块（.-custom-swatch）保留其定制删除菜单（自身 handler 会 preventDefault），此处跳过。
  // 源码编辑器 / 预览区：仅 preventDefault 屏蔽原生菜单，不中断传播，
  // 以便选中文本右键的自定义菜单（创建链接/KP 等）照常弹出。
  document.addEventListener("contextmenu", (e) => {
    const t = e.target;
    if (!t || !t.closest) return;
    if (t.closest(".-custom-swatch")) return;
    if (t.closest(".-format-bar, .-color-picker-mask, .-context-menu")) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    if (t.closest("#editor, #preview")) {
      e.preventDefault();
    }
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && _brush) cancelBrush();
  });

  /**
   * 动态定位下拉菜单，保证完整显示在窗口可视区域内。
   * 使用视口坐标 + position:fixed，脱离 #viewer 的 overflow 裁剪，避免被左侧文件树遮挡。
   * 水平：优先向右展开（左对齐按钮），越界则向左展开（右对齐按钮）；
   * 垂直：优先向下展开，越界则向上展开。
   */
  function positionDropdown(dd) {
    const menu = dd.querySelector(".-fmt-dropdown-menu");
    const btn = dd.querySelector(".-fmt-btn");
    if (!menu || !btn) return;

    const menuRect = menu.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const mw = menuRect.width;
    const mh = menuRect.height;

    // 水平：优先右对齐按钮左缘展开；放不下则左对齐按钮右缘展开
    let left = btnRect.left;
    if (left + mw > vw) left = Math.max(4, btnRect.right - mw);
    // 垂直：优先在按钮下方展开；放不下则在按钮上方展开
    let top = btnRect.bottom;
    if (top + mh > vh) top = Math.max(4, btnRect.top - mh);

    menu.style.position = "fixed";
    menu.style.left = left + "px";
    menu.style.right = "auto";
    menu.style.top = top + "px";
    menu.style.bottom = "auto";
  }

  function getEditorSelectionInfo() {
    /** Returns { line, startCol, endCol, text } or null */
    const editor = $("#editor");
    const sel = window.getSelection();
    if (!sel?.rangeCount || !editor) return null;
    const range = sel.getRangeAt(0);
    if (!editor.contains(range.startContainer) || !editor.contains(range.endContainer)) return null;

    const anchorLine = lineForNodeInContainer(range.startContainer, editor);
    const focusLine = lineForNodeInContainer(range.endContainer, editor);
    if (!anchorLine || !focusLine) return null;
    // Only support single-line selection for now
    if (anchorLine !== focusLine) {
      setStatus("格式化仅支持单行内选择");
      return null;
    }
    const lineEl = document.querySelector(`#line-${anchorLine} .-line-content`);
    if (!lineEl) return null;

    // Calculate character offsets within the line text
    const lineText = lineEl.textContent || "";
    const preRange = document.createRange();
    preRange.setStart(lineEl.firstChild || lineEl, 0);
    preRange.setEnd(range.startContainer, range.startOffset);
    const startCol = preRange.toString().length;
    let endCol;
    if (range.collapsed) {
      endCol = startCol;
    } else {
      const preRange2 = document.createRange();
      preRange2.setStart(lineEl.firstChild || lineEl, 0);
      preRange2.setEnd(range.endContainer, range.endOffset);
      endCol = preRange2.toString().length;
    }
    return { line: anchorLine, startCol, endCol, text: lineText.substring(startCol, endCol) };
  }

  async function applyFormat(formatType, color) {
    if (!state.currentPath) return;
    log("STYLE", "applyFormat fmt=" + formatType + " color=" + (color || "null") + " path=" + state.currentPath);

    // 预览区选区优先：走 AST 包裹管线（顶栏按钮点击时选区可能已失焦，用捕获的选区兜底）
    const previewRange = getPreviewSelectionRange();
    if (previewRange && window.MemoriaEditSync && typeof window.MemoriaEditSync.applyStyle === "function") {
      const res = window.MemoriaEditSync.applyStyle(formatType, color, previewRange);
      log("STYLE", "applyFormat res=" + JSON.stringify(res));
      _pendingPreviewRange = null;
      if (res && res.ok) {
        setStatus("已应用样式");
      } else if (res && res.message) {
        setStatus(res.message);
      } else {
        setStatus("样式应用失败");
      }
      return;
    }

    // 移除样式（无色）仅支持预览区 AST 管线；源码区暂不支持
    if (formatType === "unhighlight" || formatType === "unfontcolor") {
      setStatus("请先在预览区选中文字，再使用「无色」");
      return;
    }

    const info = getEditorSelectionInfo();
    if (!info) {
      setStatus("请先在源码中选中文字");
      return;
    }
    if (info.startCol === info.endCol) {
      // No selection — insert empty wrapper at cursor
      const res = await call("format_text", state.currentPath, info.line, info.startCol, info.endCol, formatType, color || null);
      if (res.status !== "ok") {
        setStatus(res.message || "格式化失败");
        return;
      }
      state.doc = res;
      renderEditor(res);
      renderKpList(res);
      await setViewMode(state.viewMode, { skipSave: true });
      // Position cursor inside the wrapper (between prefix and suffix)
      _focusEditorCol(info.line, info.startCol + _formatPrefixLen(formatType, color));
    } else {
      const res = await call("format_text", state.currentPath, info.line, info.startCol, info.endCol, formatType, color || null);
      if (res.status !== "ok") {
        setStatus(res.message || "格式化失败");
        return;
      }
      state.doc = res;
      renderEditor(res);
      renderKpList(res);
      await setViewMode(state.viewMode, { skipSave: true });
    }
  }

  function _formatPrefixLen(formatType, color) {
    if (formatType === "bold") return 2; // **
    if (formatType === "italic") return 1; // *
    if (formatType === "highlight") {
      const c = color || "yellow";
      return c === "yellow" ? 5 : 5 + 1 + c.length; // [[\h| or [[\h:green|
    }
    if (formatType === "fontcolor") {
      const c = color || "red";
      return 5 + 1 + c.length; // [[\c:red|
    }
    return 0;
  }

  function _focusEditorCol(lineNumber, col) {
    const lineEl = document.querySelector(`#line-${lineNumber} .-line-content`);
    if (!lineEl || !lineEl.firstChild) return;
    const textNode = lineEl.firstChild;
    const range = document.createRange();
    range.setStart(textNode, Math.min(col, textNode.length));
    range.collapse(true);
    const sel = window.getSelection();
    if (!sel) return;
    sel.removeAllRanges();
    sel.addRange(range);
    lineEl.focus();
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
    const elStart = +(el.dataset.SrcLine || 0);
    const elEnd = +(el.dataset.SrcLineEnd || elStart);
    if (!elStart) return false;
    return elStart <= endLine && elEnd >= startLine;
  }

  function clearHighlights() {
    document.querySelectorAll(".-line").forEach((el) => {
      el.classList.remove("kp-highlight-flash", "kp-error-flash", "fade-out", "in-range", "kp-hover");
    });
  }

  function clearKpListItemErrorHighlight() {
    document.querySelectorAll(".-kp-item.error-highlight").forEach((el) => {
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
    document.querySelectorAll(".-line.kp-hover").forEach((el) => {
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
    document.querySelectorAll(".-line.kp-hover").forEach((el) => {
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
      document.querySelectorAll(".-line.kp-highlight-flash").forEach((el) => {
        el.classList.add("fade-out");
      });
      document.getElementById("-preview-range-band")?.classList.add("fade-out");
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
    const items = document.querySelectorAll(".-kp-item");
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
    const items = kpList.querySelectorAll(".-kp-item");
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
    document.getElementById("-preview-range-band")?.remove();
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
    const matches = [...preview.querySelectorAll("[data--src-line]")].filter((el) =>
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
      const ln = +(el.dataset.SrcLine || 0);
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

    let band = document.getElementById("-preview-range-band");
    if (!band) {
      band = document.createElement("div");
      band.id = "-preview-range-band";
      band.className = "-preview-range-band";
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
    const band = document.getElementById("-preview-range-band");
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
    return `<div class="-assist-preview-head">
      <span class="-muted">范围预览</span>
      <div class="-view-toggle" role="tablist" aria-label="预览模式">
        <button type="button" class="-view-btn${mode === "source" ? " active" : ""}" data-assist-view="source">源码</button>
        <button type="button" class="-view-btn${mode === "markdown" ? " active" : ""}" data-assist-view="markdown">Markdown</button>
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
    let cls = "-line";
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
    el.innerHTML = `<span class="-lineno">${n}</span><span class="-line-content">${esc(line)}</span>`;
    return el;
  }

  function updateAssistSourceHighlights(wrap, start, end) {
    wrap.querySelectorAll("#assist-preview-scroll .-line").forEach((el) => {
      const n = +el.dataset.line;
      el.className = assistLineClass(n, start, end);
    });
  }

  function updateAssistEllipsis(wrap, viewStart, viewEnd, total) {
    const top = wrap.querySelector(".-assist-preview-ellipsis-top");
    const bottom = wrap.querySelector(".-assist-preview-ellipsis-bottom");
    if (viewStart > 1) {
      const text = `… 上文第 1–${viewStart - 1} 行`;
      if (top) top.textContent = text;
      else {
        const el = document.createElement("div");
        el.className = "-assist-preview-ellipsis -assist-preview-ellipsis-top -muted";
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
        el.className = "-assist-preview-ellipsis -assist-preview-ellipsis-bottom -muted";
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
      scroll.querySelectorAll(".-line").forEach((el) => {
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
      scroll.querySelectorAll(".-line").forEach((el) => {
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
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-top -muted">… 上文第 1–${viewStart - 1} 行</div>`;
    }

    html += '<div class="-assist-preview" id="assist-preview-scroll">';
    for (let n = viewStart; n <= viewEnd; n++) {
      const line = state.doc.lines[n - 1] ?? "";
      html += `<div class="${assistLineClass(n, start, end)}" data-line="${n}">
        <span class="-lineno">${n}</span>
        <span class="-line-content">${esc(line)}</span>
      </div>`;
    }
    html += "</div>";

    if (viewEnd < total) {
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-bottom -muted">… 下文第 ${viewEnd + 1}–${total} 行</div>`;
    }

    wrap.innerHTML = html;
    bindAssistPreviewToolbar(wrap);
  }

  async function renderAssistMarkdownPreview(wrap, start, end, total, viewStart, viewEnd, opts = {}) {
    let html = assistPreviewToolbarHtml();

    if (viewStart > 1) {
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-top -muted">… 上文第 1–${viewStart - 1} 行</div>`;
    }

    html += '<div class="-assist-md -preview markdown-body" id="assist-md-scroll">';
    const lines = state.doc.lines;

    if (viewStart < start) {
      const chunk = lines.slice(viewStart - 1, start - 1).join("\n");
      html += `<div class="-assist-md-part">${MemoriaMarkdownPreview.renderHtml(chunk)}</div>`;
    }

    const rangeChunk = lines.slice(start - 1, end).join("\n");
    html += `<div class="-assist-md-part assist-md-range" id="assist-md-range">`;
    html += MemoriaMarkdownPreview.renderHtml(rangeChunk);
    html += '<div id="assist-md-range-end" class="assist-md-anchor" aria-hidden="true"></div>';
    html += "</div>";

    if (end < viewEnd) {
      const chunk = lines.slice(end, viewEnd).join("\n");
      html += `<div class="-assist-md-part">${MemoriaMarkdownPreview.renderHtml(chunk)}</div>`;
    }

    html += "</div>";

    if (viewEnd < total) {
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-bottom -muted">… 下文第 ${viewEnd + 1}–${total} 行</div>`;
    }

    wrap.innerHTML = html;
    bindAssistPreviewToolbar(wrap);

    const mdRoot = wrap.querySelector(".-assist-md");
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
        '<p class="-assist-preview-error">行号无效：终点不能早于起点</p>';
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
      const raw = localStorage.getItem("-kp-modal-size");
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
          "-kp-modal-size",
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
          <label for="c-${group}-${n}" class="candidate-line"><span class="-muted">L${n}</span> ${esc(text)}</label>
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
    const sidebar = $("#-sidebar");
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
    localStorage.setItem("-search-scope", state.toolbarSearchScope);
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
        showToolbarSearchPanel(`<div class="-search-placeholder">${hint}</div>`);
      } else {
        let html = "";
        if (items.length) {
          html += items
            .map(
              (it, i) =>
                `<button type="button" class="-suggest-item -toolbar-search-hit" data-search-kind="kp" data-search-idx="${i}">
                  <span class="-suggest-score" title="${esc((it.sources || []).join(", "))}">${esc(formatSearchHitScore(it, modes))}</span>
                  <span class="-suggest-label">${esc(it.label || it.name || it.id || "")}</span>
                  <span class="-muted -toolbar-search-file">${esc(basename(it.file || ""))}</span>
                </button>`
            )
            .join("");
        }
        if (bodyHits.length) {
          if (items.length) {
            html += `<div class="-search-section-label">正文定位</div>`;
          }
          html += bodyHits
            .map(
              (it, i) =>
                `<button type="button" class="-suggest-item -toolbar-search-hit -toolbar-search-body" data-search-kind="body" data-body-idx="${i}">
                  <span class="-suggest-score -suggest-score--muted" title="正文行匹配">L${esc(String(it.line || ""))}</span>
                  <span class="-suggest-label">${esc(it.label || it.snippet || "")}</span>
                  <span class="-muted -toolbar-search-file">${esc(basename(it.file || ""))}</span>
                </button>`
            )
            .join("");
        }
        showToolbarSearchPanel(html);
        $("#toolbar-search-panel")
          ?.querySelectorAll(".-toolbar-search-hit")
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
    if (document.body.dataset.HoverDragGuard) return;
    document.body.dataset.HoverDragGuard = "1";
    document.addEventListener(
      "pointerdown",
      (e) => {
        if (e.button !== 0) return;
        if (e.target.closest(".-kp-item")) return;
        if (e.target.closest(".-link-match-row")) return;
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
    $("#btn-insert-image").addEventListener("click", () => startInsertImage());
    // 图片插入按钮：mousedown 阻止焦点从预览区转移（不触发 focusin 的禁用刷新）。
    // 否则点击按钮的瞬间焦点离开预览区 → _caretInPreview=false → 按钮被禁用 → click 无法触发
    // （焦点状态机下"点击即失效"的经典缺陷）。阻止聚焦后 focus 保持在预览区，
    // 按钮保持可点，且预览区 selection 完好，插入位置定位（previewCursorSourceLine）不受影响。
    $("#btn-insert-image").addEventListener("mousedown", (e) => {
      if (e.button === 0) e.preventDefault();
    });
    // 文本光标位置变化时刷新按钮可用性（点击预览区/编辑器、方向键移动光标等都会触发）
    document.addEventListener("selectionchange", refreshImageInsertAvailability);
    // 焦点进入预览区 → 编辑光标真实存在于预览区（闪烁）→ 按钮可点；焦点离开（编辑器/文件树/弹窗等）→ 禁用。
    // 以 focus 状态机驱动，不依赖 selection 快照：切换文件后 selection 残留旧位置也不会误判。
    document.addEventListener("focusin", function (e) {
      const EH2 = window.MemoriaEditHandler;
      if (!EH2) return;
      const t = e.target;
      const inPreview = !!(t && t.nodeType === 1 && t.closest && t.closest("#preview"));
      EH2._caretInPreview = inPreview && EH2.editMode;
      refreshImageInsertAvailability();
    });
    refreshImageInsertAvailability();
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
    $("#check-modal .-modal-backdrop")?.addEventListener("click", closeCheckModal);
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
      if (!e.target.closest(".-graph-audit-goto")) return;
      const issue = firstGraphAuditWarn();
      if (issue) await gotoGraphAuditIssue(issue);
    });
    $("#graph-3d-hint")?.addEventListener("click", async (e) => {
      if (!e.target.closest(".-graph-audit-goto")) return;
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
    $("#kp-modal .-modal-backdrop").addEventListener("click", closeKpModal);
    $("#kp-delete").addEventListener("click", () => deleteKpFromModal());
    $("#kp-save").addEventListener("click", () => saveKpModal());
    $("#config-close").addEventListener("click", closeConfigModal);
    $("#config-close-btn").addEventListener("click", closeConfigModal);
    $("#config-modal .-modal-backdrop").addEventListener("click", closeConfigModal);
    $("#link-close").addEventListener("click", closeLinkModal);
    $("#link-cancel").addEventListener("click", closeLinkModal);
    $("#link-confirm").addEventListener("click", confirmLinkPicker);
    $("#import-conflict-close").addEventListener("click", closeImportConflictModal);
    $("#import-conflict-cancel").addEventListener("click", closeImportConflictModal);
    $("#import-conflict-modal .-modal-backdrop")?.addEventListener("click", closeImportConflictModal);
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
    $("#import-result-modal .-modal-backdrop")?.addEventListener("click", closeImportResultModal);
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
      const rowEl = e.target.closest(".-link-match-row");
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
      const rowEl = e.target.closest(".-link-match-row");
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
    $("#link-modal .-modal-backdrop").addEventListener("click", closeLinkModal);
    document.addEventListener("keydown", (e) => {
      if (e.altKey && e.key === "ArrowLeft") {
        e.preventDefault();
        navBack();
      } else if (e.altKey && e.key === "ArrowRight") {
        e.preventDefault();
        navForward();
      }
    });
    document.querySelectorAll(".-view-btn").forEach((btn) => {
      btn.addEventListener("click", () => setViewMode(btn.dataset.view));
    });
    // 格式工具栏
    bindFormatToolbar();
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
    if (window.MemoriaEditHandler) MemoriaEditHandler.bindPreviewClick();

    // ── 编辑模式切换 ──
    var editToggle = $("#edit-mode-toggle");
    if (editToggle) {
      editToggle.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (window.MemoriaEditHandler) MemoriaEditHandler.toggleEditMode();
        // 编辑模式切换后立即刷新图片插入按钮可用性（不依赖 selectionchange 的后续触发）
        refreshImageInsertAvailability();
      });
    }
    bindPreviewSelectionMenu();
    bindFormulaDragSelect();
    bindModalDrag();
  }

  // ════════════════════════════════════════════════════════════
  // 行内公式拖拽选择：contenteditable=false 的公式无法被浏览器原生拖拽选中
  // （按下不产生选区、跨过被跳过）。编辑模式下把 .-math 当作“原子字符”参与选择：
  // 在公式上按下 → 整体选中公式，继续拖动可扩展选区到前后文本；双击仍放行进入公式编辑。
  // ════════════════════════════════════════════════════════════
  let _mathDrag = null;       // 拖拽态 { el, anchorRange }
  let _mathLastDown = null;   // 双击检测 { el, t }
  let _mathDragRaf = null;
  const _MATH_DBL_MS = 350;

  /** 将选区设为整个公式（原子块） */
  function _selectFormulaRange(mathEl) {
    const r = document.createRange();
    r.setStart(mathEl, 0);
    r.setEnd(mathEl, 1);
    const sel = window.getSelection();
    if (sel) { sel.removeAllRanges(); sel.addRange(r); }
    return r;
  }

  /** 计算拖拽终点对应的选区端点（方向感知：相对锚点公式在前/在后） */
  function _mathDragEndPoint(clientX, clientY, anchorEl, anchorRange) {
    // 终点落在公式上：公式整体参与（与锚点比较文档位置决定方向）
    const under = document.elementFromPoint(clientX, clientY);
    const math2 = under && under.closest ? under.closest(".-math") : null;
    if (math2) {
      if (math2 === anchorEl) {
        return { sc: anchorRange.startContainer, so: anchorRange.startOffset, ec: anchorRange.endContainer, eo: anchorRange.endOffset };
      }
      const cmp = anchorEl.compareDocumentPosition(math2);
      if (cmp & Node.DOCUMENT_POSITION_FOLLOWING) {
        return { sc: anchorRange.startContainer, so: anchorRange.startOffset, ec: math2, eo: 1 };
      }
      return { sc: math2, so: 0, ec: anchorRange.endContainer, eo: anchorRange.endOffset };
    }
    // 终点在文本上：caretRangeFromPoint 取精确点，与锚点公式比较方向
    let pt = null;
    try { pt = document.caretRangeFromPoint ? document.caretRangeFromPoint(clientX, clientY) : null; } catch (err) { pt = null; }
    if (!pt || !pt.startContainer) return null;
    const before = pt.compareBoundaryPoints(Range.END_TO_START, anchorRange) <= 0;
    if (before) return { sc: pt.startContainer, so: pt.startOffset, ec: anchorRange.endContainer, eo: anchorRange.endOffset };
    return { sc: anchorRange.startContainer, so: anchorRange.startOffset, ec: pt.startContainer, eo: pt.startOffset };
  }

  /** 预览区 mousedown：编辑模式下按下公式 → 整体选中并可拖动扩展（双击放行进公式编辑） */
  function _onFormulaMousedown(e) {
    if (e.button !== 0) return;
    const EH = window.MemoriaEditHandler;
    if (!EH || !EH.editMode) return;
    const preview = $("#preview");
    const t = e.target;
    if (!preview || !t || !t.closest) return;
    if (!preview.contains(t)) return;
    const mathEl = t.closest(".-math");
    if (!mathEl) return;
    const now = Date.now();
    const isDbl = _mathLastDown && _mathLastDown.el === mathEl && now - _mathLastDown.t < _MATH_DBL_MS;
    _mathLastDown = { el: mathEl, t: now };
    if (isDbl) { _mathDrag = null; return; } // 双击：放行，dblclick 进入公式编辑
    e.preventDefault(); // 阻止浏览器把公式“跳过”的原生选择
    const anchorRange = _selectFormulaRange(mathEl);
    _mathDrag = { el: mathEl, anchorRange };
  }

  function _onFormulaDragMove(e) {
    if (!_mathDrag || _mathDragRaf) return;
    const x = e.clientX, y = e.clientY;
    _mathDragRaf = requestAnimationFrame(() => {
      _mathDragRaf = null;
      if (!_mathDrag) return;
      const ep = _mathDragEndPoint(x, y, _mathDrag.el, _mathDrag.anchorRange);
      if (!ep) return;
      const r = document.createRange();
      r.setStart(ep.sc, ep.so);
      r.setEnd(ep.ec, ep.eo);
      const sel = window.getSelection();
      if (sel) { sel.removeAllRanges(); sel.addRange(r); }
    });
  }

  function _onFormulaDragUp() {
    _mathDrag = null;
  }

  /** 绑定公式拖拽选择（需在 MemoriaEditHandler.bindPreviewClick 之后调用） */
  function bindFormulaDragSelect() {
    document.addEventListener("mousedown", _onFormulaMousedown, true);
    document.addEventListener("mousemove", _onFormulaDragMove);
    document.addEventListener("mouseup", _onFormulaDragUp);
  }

  /** 模态框标题栏拖拽：mousedown 在 header（排除交互元素）→ 移动整个 .-modal-box */
  function bindModalDrag() {
    const NO_DRAG =
      ".-icon-btn, button, input, textarea, select, a, [contenteditable], [data-no-drag]";
    let dragging = null;

    function readCurrentTranslate(box) {
      const t = (box.style.transform || "").match(/translate\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)px\s*\)/);
      if (!t) return { dx: 0, dy: 0 };
      return { dx: parseFloat(t[1]) || 0, dy: parseFloat(t[2]) || 0 };
    }

    document.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      const header = e.target.closest(".-modal-header");
      if (!header) return;
      if (e.target.closest(NO_DRAG)) return;
      const box = header.closest(".-modal-box");
      if (!box) return;
      const modal = box.closest(".-modal");
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
          const box = modal.querySelector(".-modal-box");
          if (box) box.style.transform = "";
        }
      }
    });
    document.querySelectorAll(".-modal").forEach((modal) => {
      observer.observe(modal, { attributes: true, attributeFilter: ["class"] });
    });
  }

  window.MemoriaBridge?.onReady?.(() => {
    bindEvents();
    initKb();
    hydrateCustomColorsFromDisk();
    window.MemoriaWindowChrome?.initWindowChrome?.();
  });

  window.MemoriaGraphShell = {
    getGraphGroupId() {
      return state.graphGroupId || window.MemoriaGraphGroups?.ALL_GROUP_ID || "all";
    },
  };
})();
