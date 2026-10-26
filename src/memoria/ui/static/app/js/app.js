(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const api = () => window.MemoriaBridge && window.MemoriaBridge.api();

  /** 按住主键拖拽（如图谱平移）时不触发悬停高亮 */
  function shouldSuppressHoverHighlight(e) {
    return !!(e && e.buttons);
  }

  // ── 图交互埋点（KG-v0 D-KG-07）──────────────────────────────────────────────
  //
  // ## 为什么有这个（裁决原文）
  // 「不是没设计指标，是指标所需数据从未采集」——
  // `nodeClick` 早就有事件（`graph-view-2d.js`）、消费者（`onGraphNodeClick`）和
  // 来源标记（`source:"graph"`），但**标记从未被统计消费**，且 `edge_id` 从未被记录。
  // 于是「这条边到底有没有用」在数据上无法回答，任何关于边价值的讨论都建在沙上。
  //
  // ## 隐私边界（硬约束，改动前先读）
  // **只记交互标识**：`node_id` / `kp_id` / 边标识（id/source/target/type/origin）/
  // 来源 / 时间戳（毫秒）。
  // **绝不记**：文档正文、用户输入、选区内容、任何可直接识别个人的信息。
  // **不落盘、不跨会话、不上报服务端、不建用户画像** —— 纯内存计数器，页面刷新即清零。
  // 这是「埋点」不是「遥测」：数据不出页面，只用于回答"点过没有"。
  const _graphInteractions = {
    nodes: new Map(),
    edges: new Map(),
    bySource: new Map(),
    total: 0,
  };

  /**
   * 记录一次图交互（**只记标识，不记内容**，见上方隐私边界）。
   * @param {string} kind 交互种类（当前只有 "nodeClick"）
   * @param {object} node 图节点（只取 id / kp_id）
   * @param {object|null} edgeId 边标识（来自 `_edgeIdForNode`，可为 null）
   */
  function recordGraphInteraction(kind, node, edgeId) {
    const ts = Date.now();
    _graphInteractions.total += 1;
    const src = "graph";
    _graphInteractions.bySource.set(src, (_graphInteractions.bySource.get(src) || 0) + 1);

    const nodeId = node && (node.id || node.kp_id);
    if (nodeId) {
      const cur = _graphInteractions.nodes.get(nodeId) || {
        count: 0,
        firstTs: ts,
        lastTs: ts,
        kp_id: node.kp_id || null,
      };
      cur.count += 1;
      cur.lastTs = ts;
      _graphInteractions.nodes.set(nodeId, cur);
    }

    if (edgeId && edgeId.id) {
      const cur = _graphInteractions.edges.get(edgeId.id) || {
        count: 0,
        firstTs: ts,
        lastTs: ts,
        type: edgeId.type || null,
        origin: edgeId.origin || null,
        source: edgeId.source || null,
        target: edgeId.target || null,
      };
      cur.count += 1;
      cur.lastTs = ts;
      _graphInteractions.edges.set(edgeId.id, cur);
    }
  }

  /** 可读统计（验收/调试用）：只含标识与计数，无任何文档内容。 */
  function graphInteractionStats() {
    return {
      total: _graphInteractions.total,
      nodes: [..._graphInteractions.nodes.entries()].map(([id, v]) => Object.assign({ node_id: id }, v)),
      edges: [..._graphInteractions.edges.entries()].map(([id, v]) => Object.assign({ edge_id: id }, v)),
      bySource: [..._graphInteractions.bySource.entries()].map(([s, c]) => ({ source: s, count: c })),
    };
  }

  /** 扁平快照（便于 dump / 断言）：`{total, nodeHits, edgeHits, edgeIds}`。 */
  function graphInteractionSnapshot() {
    const s = graphInteractionStats();
    return {
      total: s.total,
      nodeHits: s.nodes.length,
      edgeHits: s.edges.length,
      edgeIds: s.edges.map((e) => e.edge_id),
      edgeTypes: s.edges.map((e) => e.type),
    };
  }

  /** 清零（测试用；正常使用中页面刷新即清零，不需要手动调用）。 */
  function resetGraphInteractions() {
    _graphInteractions.nodes.clear();
    _graphInteractions.edges.clear();
    _graphInteractions.bySource.clear();
    _graphInteractions.total = 0;
  }

  let state = {
    kbPath: "",
    files: [],
    currentPath: null,
    doc: null,
    activeKpId: null,
    hoveredKpId: null,
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
    linkPopover: null,   // task-145：链接点击浮层（无模态遮罩）
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
    // 启动自动打开 vs 用户主动导航（2026-10-22）：
    // openSeq 单调递增，用户每次主动打开 ++；启动自动打开在 await 前记录 token，
    // await 后 token 变了（或 userNavigated=true）⇒ 放弃提交，绝不覆盖用户已选的页面。
    openSeq: 0,
    userNavigated: false,
    bootAutoOpenPending: false,
    // task-75：启动初始化窗口（initKb 的 ensure_kb_root→refreshFiles→loadLinkTargets 期间）。
    // 期间拒绝外部 openFile（明确 failed），避免与启动 RPC 交错把 boot 卡死；
    // 启动自动打开自己带 bootToken，可穿透（见 openFile 的前置判定）。
    startupInFlight: false,
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
  const DURABLE_FLUSH_IDLE_MS = 3000; // 自动保存后 3s 防抖兜底 fsync（durable_flush，G4 M6a）
  let _renderTimer = null;  // 内存实时同步计时器
  let _saveTimer  = null;  // 磁盘保存计时器
  let _durableTimer = null; // durable_flush 防抖计时器
  let _dirty = false;      // 是否有未写盘的编辑
  const _SYNC_LOG = true;  // 调试开关，设为 false 关闭日志

  function syncLog(...args) { if (_SYNC_LOG) console.log("[SYNC]", ...args); }

  /**
   * S13：`state.doc.body` 是否以 `\n` 结尾（"文件尾换行"这一位）。
   * DOM 的 `.-line-content` **无法表达**尾换行（N 行 ⇒ N-1 个分隔符），故必须从真源
   * `state.doc.body` 在第一次回读前把它记下来，之后按位回补——**不是**无条件加 `\n`。
   * 每次 `state.doc` 新载入（新对象）会重新判定，故不会把无尾换行的文件改成有。
   */
  function _docEndsWithNL(doc) {
    const d = doc || state.doc;
    if (!d) return false;
    if (typeof d.__endsWithNL === "boolean") return d.__endsWithNL;
    const b = typeof d.body === "string" ? d.body : "";
    d.__endsWithNL = b.length > 0 && b.endsWith("\n");
    return d.__endsWithNL;
  }

  /** 由 body 得 `state.doc.lines`：尾 `\n` 不产生空行（与后端 `load_document.lines` 同口径） */
  function _linesFromBody(body) {
    const b = body == null ? "" : String(body);
    return b.endsWith("\n") ? b.slice(0, -1).split("\n") : b.split("\n");
  }

  /** 按原文"是否有尾换行"补回（只在真源标记为 true 且当前 body 缺尾时补一位） */
  function _restoreDocTailNL(body) {
    if (body == null) return body;
    const b = String(body);
    return (_docEndsWithNL() && b.length > 0 && !b.endsWith("\n")) ? b + "\n" : b;
  }

  /** 收集源码编辑器的当前内容（逐行拼接；S13：按真源原样恢复尾换行） */
  function collectEditorBody() {
    const editor = $("#editor");
    if (!editor) { syncLog("collectEditorBody: editor DOM 不存在"); return null; }
    const lines = [...editor.querySelectorAll(".-line-content")];
    if (!lines.length) { syncLog("collectEditorBody: 无 .-line-content 行"); return null; }
    const body = lines.map((el) => {
      // 剔除视觉元素：分栏模式的"假光标"是注入源码行的 <span class="-sync-cursor">，
      // 它不是正文；若被读进来会随保存写进 .md（历史 bug："aaa"→"a|aa"、"<details>"→"<details>|"）
      if (!el.querySelector(".-sync-cursor")) return el.textContent ?? "";
      const clone = el.cloneNode(true);
      clone.querySelectorAll(".-sync-cursor").forEach((n) => n.remove());
      return clone.textContent ?? "";
    }).join("\n");
    // task-147（R0）：DOM 复算 `body` **恒等于 canonical 去掉最后一个尾换行**
    //   （后端 `lines = body.splitlines()` 恰好丢掉末尾那一项），所以"是否补 1 位"只看真源标记，
    //   **不能**再用 `!b.endsWith("\n")` —— 文件尾为 `\n\n` / `\n\n\n` 时 body 仍以 `\n` 结尾，
    //   会被误判成"已有尾换行"而少补 1 位 ⇒ 保存即永久丢 1 字节（R-01 未覆盖边界）。
    //   ⚠️ 不要合并 `_restoreDocTailNL`：它的另外两处调用（7697/11825 快照恢复）输入是**完整 body**，
    //   那里"已带尾换行就跳过"是对的，改成无条件补会**多**一个换行。
    const out = _docEndsWithNL() ? body + "\n" : body;
    syncLog("collectEditorBody: 收集到", lines.length, "行, 总长度", out.length, "(tailNL=", _docEndsWithNL(), ")");
    return out;
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
    state.doc.lines = _linesFromBody(body);
    state.doc.preview_body = null;
    // 2026-10-25 task-141：**锚点必须在重渲之前采**（AG105 同款教训：清屏后再量，量到的永远是第一行）。
    //   病根（真机 2×2 对照已证）：长文档走惰性物化 ⇒ `_buildLazyPreview` 为量真实 CSS 度量，会在
    //   "已清空、占位未建"的空态上**强制布局**（`_measurePreviewMetrics` 读 getBoundingClientRect）
    //   ⇒ 那一刻 maxScroll≈0，浏览器把 scrollTop 夹到 0；占位补回高度后**没有任何恢复** ⇒ 预览停在
    //   文件开头。全量路径清屏+重建在同一任务内完成，布局从未观察空态 ⇒ 不跳（medium 2180 全程不动）。
    //   修法两道：① `_buildLazyPreview` 跨过空态保住 scrollTop（根因处）；② 这里按**元素/行号锚点**
    //   精确恢复，且只在排版/物化落定后**补漂移**（绝不再重设落点 —— 与 task-140 同一不变量）。
    syncLog("syncSourceToPreview: 调用 renderPreview, body 前50字:", body.substring(0, 50));
    await _renderPreviewKeepScroll();
    syncLog("syncSourceToPreview: 完成");
  }

  // ── 源码编辑 ⇒ 预览重渲的**滚动保持**（2026-10-25 task-141）──────────────────────────────
  //  不变量（先问"要保证什么"）：
  //    E1 编辑前后**视口顶部锚点块**（srcLine）不变 —— 用元素/行号表达位置，不用 scrollTop 数值；
  //    E2 重建后若排版/惰性物化把锚点块挪了位置 ⇒ **只补差值**，绝不重设落点（与 task-140 I3 同一条）；
  //    E3 用户一旦自己滚预览 ⇒ 立刻放弃校准（不跟人抢滚动条）。
  var _editScrollGen = 0;          // 编辑代际：新一轮源码编辑 ⇒ 旧校准链立即失效
  var _editScrollGuard = null;     // 当前校准链守卫（用户滚动/新编辑会置 cancelled）
  var _editScrollStats = { restores: 0, restoredByAnchor: 0, restoredByPixel: 0, reanchors: 0, reanchorNoop: 0 };
  try {
    // 只读诊断（真机验证/回归用；不参与渲染）：证明"恢复分支真的执行"，而不只是"看起来没跳"
    window.__memoriaEditScrollStats = function () { return JSON.parse(JSON.stringify(_editScrollStats)); };
  } catch (_) { /* noop */ }

  try {
    // KG-v0 D-KG-07 埋点③：图交互计数的**只读**查询口（验收/调试用）。
    // 只暴露标识与计数；不含任何文档内容；不落盘、不上报（见上方隐私边界）。
    window.__memoriaGraphInteractionStats = graphInteractionStats;
    window.__memoriaGraphInteractionSnapshot = graphInteractionSnapshot;
    window.__memoriaGraphInteractionReset = resetGraphInteractions;
  } catch (_) { /* noop */ }

  /** 采「预览视口顶部第一个可见块」＝锚点（srcLine + 它相对视口顶的偏移）。 */
  function _capturePreviewScrollAnchor() {
    const pane = document.getElementById("preview-pane");
    if (!pane || state.viewMode === "source") return null;
    const preview = document.getElementById("preview");
    if (!preview) return null;
    // 整篇重建 ⇒ 上一轮跳转（task-140）的落点已失效：撤销其二次校准，避免两条校准链互抢滚动条
    if (_jumpAnchorGuard && !_jumpAnchorGuard.cancelled) _jumpAnchorGuard.cancelled = true;
    _jumpExpectedOffset = null;
    const pvTop = pane.getBoundingClientRect().top;
    const blocks = preview.querySelectorAll("[data--src-line]");
    for (const el of blocks) {
      if (el.closest("[data--src-line]") !== el) continue;   // 只取最外层块
      const r = el.getBoundingClientRect();
      if (r.bottom < pvTop) continue;
      const line = +(el.dataset.SrcLine || 0) || 0;
      if (!line) continue;
      return { line: line, offset: r.top - pvTop, scrollTop: pane.scrollTop, gen: _editScrollGen + 1 };
    }
    return { line: null, offset: 0, scrollTop: pane.scrollTop, gen: _editScrollGen + 1 };
  }

  /** 按锚点恢复：优先元素/行号（与 `_lazyResizeBound` 的锚点恢复同一思路），找不到才退裸像素。 */
  function _restorePreviewScrollAnchor(anchor) {
    if (!anchor) return false;
    const pane = document.getElementById("preview-pane");
    if (!pane) return false;
    const preview = document.getElementById("preview");
    if (anchor.line && preview) {
      const els = preview.querySelectorAll("[data--src-line]");
      for (const el of els) {
        if (el.closest("[data--src-line]") !== el) continue;
        const s = +(el.dataset.SrcLine || 0) || 0;
        const e = +(el.dataset.SrcLineEnd || s) || s;
        if (s && s <= anchor.line && anchor.line <= e) {
          const pvTop = pane.getBoundingClientRect().top;
          const delta = el.getBoundingClientRect().top - pvTop - anchor.offset;
          _editScrollStats.restores++;
          _editScrollStats.restoredByAnchor++;
          if (Math.abs(delta) >= 1) pane.scrollTop += delta;   // 只补差值（不是重设落点）
          return true;
        }
      }
    }
    _editScrollStats.restores++;
    _editScrollStats.restoredByPixel++;
    pane.scrollTop = anchor.scrollTop;   // 兜底：极端情况下找不到锚点元素
    return false;
  }

  /** 重渲后的**漂移收敛**：只在同一代编辑内、用户没自己滚的前提下补差值；绝不重设落点。 */
  function _scheduleEditScrollReanchor(anchor) {
    if (!anchor || !anchor.line) return;
    const gen = ++_editScrollGen;
    const pane = document.getElementById("preview-pane");
    if (!pane) return;
    const g = { cancelled: false };
    _editScrollGuard = g;
    const cancel = () => { g.cancelled = true; };
    ["wheel", "mousedown", "touchstart"].forEach((ev) => {
      pane.addEventListener(ev, cancel, { once: true, passive: true });
    });
    // 惰性物化/公式排版会晚一拍改高度 ⇒ 分几个稳定点补漂移（密集前段 + 覆盖 1.5s 收尾）
    [80, 260, 700, 1500].forEach((ms) => {
      window.setTimeout(() => {
        if (g.cancelled || _editScrollGuard !== g || gen !== _editScrollGen) return;
        if (state.viewMode === "source") return;
        try {
          const pv = document.getElementById("preview");
          const pp = document.getElementById("preview-pane");
          if (!pv || !pp) return;
          const pvTop = pp.getBoundingClientRect().top;
          let target = null;
          const els = pv.querySelectorAll("[data--src-line]");
          for (const el of els) {
            if (el.closest("[data--src-line]") !== el) continue;
            const s = +(el.dataset.SrcLine || 0) || 0;
            const e = +(el.dataset.SrcLineEnd || s) || s;
            if (s && s <= anchor.line && anchor.line <= e) { target = el; break; }
          }
          if (!target) return;
          const drift = target.getBoundingClientRect().top - pvTop - anchor.offset;
          if (Math.abs(drift) < 1) { _editScrollStats.reanchorNoop++; return; }
          pp.scrollTop += drift;   // 只补偏移
          _editScrollStats.reanchors++;
          log("SCROLL", "edit-reanchor(" + ms + "ms): drift=" + Math.round(drift));
        } catch (_) { /* noop */ }
      }, ms);
    });
  }

  /** **源码侧触发的整篇重渲**统一入口（task-141）：采锚点 → renderPreview → 恢复锚点 → 漂移收敛。
   *  为什么不能只在 `syncSourceToPreview` 里做：撤销/重做（`_srcApplySnapshot`）与结构编辑的
   *  兜底（`repaintPreview` → `renderPreview`）同样会整篇重渲，同样会在惰性文档上丢滚动位置。 */
  async function _renderPreviewKeepScroll(options) {
    const anchor = _capturePreviewScrollAnchor();
    try {
      return await renderPreview(state.doc, options);
    } finally {
      if (anchor) {
        _restorePreviewScrollAnchor(anchor);
        _scheduleEditScrollReanchor(anchor);
      }
    }
  }

  /** 内存实时同步：源码编辑时更新预览 */
  function scheduleRenderSync() {
    clearTimeout(_renderTimer);
    syncLog("scheduleRenderSync: 将在", RENDER_DEBOUNCE_MS, "ms 后执行 syncSourceToPreview");
    _renderTimer = setTimeout(() => {
      _renderTimer = null;
      syncSourceToPreview();
    }, RENDER_DEBOUNCE_MS);
  }

  /** 将当前内存内容写回磁盘（始终从源码编辑器收集，保证 markdown 格式完整） */
  async function syncToDisk() {
    syncLog("syncToDisk: dirty=", _dirty, "path=", state.currentPath);
    if (!state.currentPath || !_dirty || window.MemoriaWriteGuard?.deferIfBusy?.(markDirty)) {
      syncLog("syncToDisk: 跳过 (无路径或无修改)");
      return;
    }
    const body = collectEditorBody();
    if (body === null) { syncLog("syncToDisk: body 为 null，跳过"); return; }
    _dirty = false;
    syncLog("syncToDisk: 写入文件", state.currentPath, ", body长度", body.length, ", 前80字:", body.substring(0, 80));
    try {
      const res = await call("save_document", state.currentPath, body, state.doc?.version || "");
      if (res.status !== "ok") {
        window.MemoriaWriteGuard?.onSaveFailed?.(res, state.currentPath, body) || console.warn("[SYNC] 保存失败:", res.message);
      } else {
        if (state.doc && res.version) state.doc.version = res.version; syncLog("syncToDisk: 保存成功"); _previewCacheDrop(state.currentPath); // 2026-09-23 性能：写盘成功 ⇒ 该路径的预览缓存按新版本作废（下次切走时再存）
        if (res.cleanedImages && res.cleanedImages.length) {
          showFlashInfo(
            T("img.cleanup.doneList", {
              n: res.cleanedImages.length,
              files: res.cleanedImages.join(T("img.listSep")),
            })
          );
        }
        // M6b：每次保存后用 load_document 的权威解析静默校正列表与 state.doc（hover 数据源）。
        // 早期只在 ranges_resynced>0 时刷新，而多数换行/删行后端判为“无变化”导致必须手动刷新才同步。
        _silentRefreshKpPanel();
        // 自动保存后 ~3s 防抖兜底 fsync（G4 M6a：写缓存→稍后刷盘）
        scheduleDurableFlush();
      }
    } catch (e) {
      console.warn("[SYNC] 保存异常:", e);
    }
  }

  /** 标记文档为脏（有未保存编辑），启动写盘防抖计时器 */
  function markDirty() {
    syncLog("markDirty: _dirty", _dirty, "→ true, 将在", SAVE_DEBOUNCE_MS, "ms 后写盘");
    _dirty = true; _previewCacheDrop(state.currentPath); _previewDomKey = null; _preloadStop("edit"); // 2026-09-23 性能：本地编辑 ⇒ 当前文档的预览缓存作废，并中止在跑的后台预渲染
    clearTimeout(_saveTimer);
    clearTimeout(_durableTimer); // 有新编辑则推迟 durable_flush 兜底
    _saveTimer = setTimeout(() => {
      _saveTimer = null;
      syncToDisk();
    }, SAVE_DEBOUNCE_MS);
    scheduleEditorRangesResolve(); // M6b：停手后按当前正文即时权威解析 KP 范围（不依赖保存）
  }

  // ── M6b：即时 KP 范围解析（结构编辑后 420ms，正文当前态 → 后端解析 → 回写 hover/列表）──
  let _rangeTimer = null;
  let _docRev = 0;
  /** 供 kb-check 等判断“编辑/待保存尚未收敛”（G5.1：静默 validate 不在忙时触发） */
  window.__memoriaHasPendingEdits = () => !!_dirty || !!_saveTimer || !!_renderTimer || !!_rangeTimer;
  function scheduleEditorRangesResolve() {
    if (!state.doc || !state.currentPath || !(state.doc.knowledge_points || []).length) return;
    clearTimeout(_rangeTimer);
    const rev = ++_docRev;
    _rangeTimer = setTimeout(async () => {
      _rangeTimer = null;
      if (!state.doc || !state.currentPath) return;
      const body = collectEditorBody();
      if (body === null) return;
      try {
        const res = await call("resolve_kp_ranges", state.currentPath, body);
        if (
          res && res.status === "ok" && Array.isArray(res.knowledge_points) &&
          _docRev === rev && state.doc && state.currentPath
        ) {
          const known = new Set((state.doc.knowledge_points || []).map((k) => k.id));
          state.doc.knowledge_points = res.knowledge_points.filter((k) => known.has(k.id));
          renderKpList(state.doc);
          if (state.hoveredKpId) highlightKpHover(state.hoveredKpId);
        }
      } catch (_e) {
        // 静默：保存后 _silentRefreshKpPanel 仍会兜底校正
      }
    }, 420);
  }

  /** 立即写盘（如果脏），返回 Promise。用于文件切换前。 */
  async function flushSync() {
    syncLog("flushSync: dirty=", _dirty);
    clearTimeout(_saveTimer);
    _saveTimer = null;
    clearTimeout(_renderTimer);
    _renderTimer = null;
    await syncToDisk();
  }

  /** durable_flush 防抖兜底：自动保存后 ~3s 无新编辑则刷盘（fsync + manifest） */
  function scheduleDurableFlush() {
    clearTimeout(_durableTimer);
    _durableTimer = setTimeout(() => {
      _durableTimer = null;
      call("flush_durable")
        .then((res) => syncLog("durable_flush idle 触发:", res))
        .catch(() => syncLog("durable_flush idle 失败"));
    }, DURABLE_FLUSH_IDLE_MS);
  }

  /** 屏障持久化：先确保内存内容已写盘，再请求后端 fsync dirty 集 + manifest pending */
  async function flushDurableBarrier() {
    clearTimeout(_durableTimer);
    _durableTimer = null;
    await flushSync();
    try {
      const res = await call("flush_durable");
      syncLog("durable_flush 屏障触发:", res);
    } catch (_) {
      syncLog("durable_flush 屏障失败");
    }
  }

  // ── 静默刷新（经 M5 调度内核）：保存后 range 被后端重锚定时，不打断编辑地更新派生视图 ──

  /** 入队“KP 面板静默刷新”作业（P2 派生视图；同文件多次触发自动合并；idle 执行）。
   *  作业执行时若用户已切走文件（路径陈旧）则直接丢弃，不刷新错文件。 */
  function _silentRefreshKpPanel() {
    const S = window.MemoriaScheduler;
    const path = state.currentPath;
    if (!S || !path) return;
    S.schedule({
      kind: "kp_panel",
      key: path,
      priority: 2,
      replace: true,
      dropStale: true, // 文件切换(openFile/closeKb bump)后排队中的旧作业自动丢弃
      run: async () => {
        if (state.currentPath !== path) return; // 兜底：用户已切走 → 陈旧丢弃
        const doc = await call("load_document", path);
        if (doc && doc.status !== "error") {
          renderKpList(doc);
        }
      },
    });
  }

  function T(key, params) {
    return window.MemoriaI18n && window.MemoriaI18n.t
      ? window.MemoriaI18n.t(key, params)
      : key;
  }

  /** 后端 check issue 消息本地化：当前语言包含 check.issue.<code> 时翻译，否则回退后端中文 message。 */
  function localizeCheckIssue(issue) {
    if (issue && issue.code && window.MemoriaI18n) {
      const lang = window.MemoriaI18n.currentLang();
      if (lang !== window.MemoriaI18n.DEFAULT_LANG) {
        const key = "check.issue." + issue.code;
        if (window.MemoriaI18n.rawLookup(lang, key) != null) {
          return window.MemoriaI18n.t(key, issue.params || {});
        }
      }
    }
    if (issue && issue.message) return issue.message;
    return issue ? issue.code || String(issue) : "";
  }

  function setStatus(msg, stats, opts = {}) {
    const el = $("#status-info");
    el.textContent = msg;
    el.classList.toggle("-status-error", !!(opts && opts.error)); // 错误类提示底栏转红（见 app.css）
    if (stats !== undefined) {
      state.lastFileStats = stats == null ? "" : String(stats);
      renderStatusStats();
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
      // 「检查统计」块文案由 kb-check.js statsChunk 提供（KB 检查子系统拆分后自包含）
      chunks.push(window.MemoriaKbCheck?.statsChunk?.(vr) || "");
      el.dataset.kbCheck = "1";
    } else {
      delete el.dataset.kbCheck;
      if (vr?.status === "ok" && state.kbPath && !state.lastFileStats) {
        chunks.push(`<span class="-stat-ok">${T("check.stat.pass")}</span>`);
      }
    }

    const gw = vr?.graph_audit?.summary?.warn_count;
    if (gw && !state.lastFileStats) {
      chunks.push(`<span class="-stat-warn">${T("check.stat.graphTodo", { n: gw })}</span>`);
    }

    if (state.lastFileStats) {
      chunks.push(esc(state.lastFileStats));
    }

    const fileWarns = currentFileGraphAuditWarns();
    const kbWarns = collectKbGraphAuditWarns(state.graphAudit);
    if (fileWarns.length) {
      const first = fileWarns[0];
      chunks.push(
        `<span class="-stat-warn">${T("check.stat.graphIssuesFile", { n: fileWarns.length, file: esc(basename(first.file)) })}</span>`
      );
      el.classList.add("-status-clickable");
      el.dataset.graphAuditGoto = "1";
    } else if (kbWarns.length) {
      const first = kbWarns[0];
      const fileCount = new Set(kbWarns.map((w) => normRelPath(w.file))).size;
      chunks.push(
        `<span class="-stat-warn">${T("check.stat.graphIssuesKb", {
          n: kbWarns.length,
          file: esc(basename(first.file)),
          more: fileCount > 1 ? T("check.stat.moreFiles", { n: fileCount }) : "",
        })}</span>`
      );
      el.classList.add("-status-clickable");
      el.dataset.graphAuditGoto = "1";
    }

    el.innerHTML = chunks.filter(Boolean).join(" · ");
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
    setStatus(msg, detail, { error: true });
    showFlashError(msg, detail, opts);
  }

  // 知识库路径显示（2026-09-18 由顶栏 #kb-indicator 移到底栏 #status-kb）：
  // 文本 + title 同写；空路径 → 文本为空 ⇒ CSS `#status-kb:empty` 隐藏（不占位）。
  // 顺带同步「文件 → 关闭知识库」菜单项的可用态（同一"开库/关库"状态源，避免两处漂移）。
  function showKbIndicator(path) {
    const closeItem = $("#file-menu-close-kb");
    if (closeItem) closeItem.disabled = !path;
    const el = $("#status-kb");
    if (!el) return;
    el.textContent = path || "";
    el.title = path || "";
  }

  function showWelcome(show) {
    $("#welcome").classList.toggle("hidden", !show);
    $("#editor-wrap").classList.toggle("hidden", show);
  }

  // ── 启动恢复「最后停留的文件」（2026-10-22）──────────────────────────────
  // 设计约束：
  //   ① 同一浏览器可切换多个知识库 ⇒ 按键名分区，绝不能串库；
  //   ② 桌面壳（pywebview WebView2）默认 private_mode=True，每次启动会清 localStorage
  //      ⇒ localStorage 只作同进程快速缓存，磁盘 ui-settings.json 才是跨重启权威源；
  //   ③ 只在「文件真正打开成功」后写；打开失败/已从 KB 删除时清除，避免每次启动重试失败。
  const BOOT_LAST_PATH_LS_PREFIX = "memoria.lastPath.";
  const BOOT_SETTINGS_SECTION = "boot";

  /** KB 路径规范形：仅用于分区与碰撞校验（不改变真实路径的展示/使用）。 */
  function _bootKbIdentity(kbPath) {
    return String(kbPath || "")
      .trim()
      .replace(/\\/g, "/")
      .replace(/\/+$/, "")
      .toLowerCase();
  }

  /** FNV-1a 32-bit：短、稳定、无依赖；碰撞由记录里的 kb 全路径二次校验兜底。 */
  function _bootKbScope(kbPath) {
    const s = _bootKbIdentity(kbPath);
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(16).padStart(8, "0");
  }

  function _bootLastPathLsKey(kbPath) {
    return BOOT_LAST_PATH_LS_PREFIX + _bootKbScope(kbPath);
  }

  function _bootReadLocalLastPath(kbPath) {
    try {
      const raw = localStorage.getItem(_bootLastPathLsKey(kbPath));
      if (!raw) return "";
      const rec = JSON.parse(raw);
      if (typeof rec === "string") return rec;
      if (!rec || typeof rec !== "object" || !rec.path) return "";
      if (rec.kb && _bootKbIdentity(rec.kb) !== _bootKbIdentity(kbPath)) return "";
      return String(rec.path);
    } catch (_) {
      return "";
    }
  }

  function _bootWriteLocalLastPath(kbPath, relPath) {
    try {
      localStorage.setItem(
        _bootLastPathLsKey(kbPath),
        JSON.stringify({ kb: kbPath, path: relPath, at: Date.now() })
      );
    } catch (_) {
      /* 隐私模式/配额：磁盘仍为权威源 */
    }
  }

  function _bootClearLocalLastPath(kbPath) {
    try {
      localStorage.removeItem(_bootLastPathLsKey(kbPath));
    } catch (_) {
      /* ignore */
    }
  }

  // 磁盘 ui-settings 是「读整对象 → 改 boot → 写回」，快速连续打开时必须串行，
  // 否则旧快照晚写会覆盖新值（表现为重启回到更早的文件）。
  let _bootSettingsWriteChain = Promise.resolve();
  let _bootLastPersistKey = "";

  function _bootEnqueueSettings(task) {
    _bootSettingsWriteChain = _bootSettingsWriteChain.then(task).catch(() => {});
    return _bootSettingsWriteChain;
  }

  async function _bootReadSettingsSection() {
    try {
      const res = await call("get_ui_settings");
      const settings = res && res.status === "ok" ? res.settings : null;
      const boot =
        settings && typeof settings[BOOT_SETTINGS_SECTION] === "object"
          ? settings[BOOT_SETTINGS_SECTION]
          : null;
      return boot || {};
    } catch (_) {
      return {};
    }
  }

  /** 读「最后文件」：磁盘优先（跨重启），本地缓存兜底（网页模式/磁盘不可用时）。 */
  async function readPersistedLastFile(kbPath) {
    if (!kbPath) return "";
    const scope = _bootKbScope(kbPath);
    const boot = await _bootReadSettingsSection();
    const rec = boot.lastPathByKb && boot.lastPathByKb[scope];
    let diskPath = "";
    if (typeof rec === "string") {
      diskPath = rec;
    } else if (rec && typeof rec === "object" && typeof rec.path === "string") {
      if (!rec.kb || _bootKbIdentity(rec.kb) === _bootKbIdentity(kbPath)) diskPath = rec.path;
    }
    if (diskPath) return diskPath;
    return _bootReadLocalLastPath(kbPath);
  }

  /** 记录「最后停留的文件」：localStorage 同步写 + ui-settings 串行落盘。 */
  function rememberLastFile(relPath) {
    const kbPath = state.kbPath;
    if (!kbPath || !relPath) return;
    _bootWriteLocalLastPath(kbPath, relPath);
    const scope = _bootKbScope(kbPath);
    const persistKey = scope + "\u0000" + relPath;
    if (_bootLastPersistKey === persistKey) return;
    _bootLastPersistKey = persistKey;
    _bootEnqueueSettings(() => _bootPersistLastFile(kbPath, scope, relPath));
  }

  async function _bootPersistLastFile(kbPath, scope, relPath) {
    // KB 已切走 ⇒ 旧库的排队写入不得污染新库分区
    if (!kbPath || state.kbPath !== kbPath) return;
    const boot = await _bootReadSettingsSection();
    const map =
      boot.lastPathByKb && typeof boot.lastPathByKb === "object" ? { ...boot.lastPathByKb } : {};
    map[scope] = { kb: kbPath, path: relPath };
    await call("save_ui_settings", { boot: { lastPathByKb: map } });
  }

  /**
   * 清除持久化。expectedPath 用于防止误删用户随后打开的新值：
   * 只有磁盘里仍记录着「本次失败的那条」时才删除。
   */
  function clearPersistedLastFile(kbPath, expectedPath) {
    if (!kbPath) return;
    // 本地缓存只在仍记录着「本次失败的那条」时清除，避免误删用户随后打开的新值
    const local = _bootReadLocalLastPath(kbPath);
    if (!expectedPath || !local || local === expectedPath) _bootClearLocalLastPath(kbPath);
    if (_bootLastPersistKey === _bootKbScope(kbPath) + "\u0000" + expectedPath) _bootLastPersistKey = "";
    const scope = _bootKbScope(kbPath);
    _bootEnqueueSettings(() => _bootClearPersistedLastFile(kbPath, scope, expectedPath));
  }

  async function _bootClearPersistedLastFile(kbPath, scope, expectedPath) {
    if (!kbPath || state.kbPath !== kbPath) return;
    const boot = await _bootReadSettingsSection();
    const map =
      boot.lastPathByKb && typeof boot.lastPathByKb === "object" ? { ...boot.lastPathByKb } : {};
    if (!(scope in map)) return;
    const rec = map[scope];
    const current =
      rec && typeof rec === "object" ? rec.path : typeof rec === "string" ? rec : "";
    if (expectedPath && current && current !== expectedPath) return;
    delete map[scope];
    await call("save_ui_settings", { boot: { lastPathByKb: map } });
  }

  /**
 * 读取剪贴板文本。
 *
 * 优先走后端系统剪贴板（`clipboard_get_text`）：WebView2 下 `navigator.clipboard.readText()`
 * 需要 `clipboard-read` 权限（会弹「是否允许」把界面卡住），且要求瞬时用户激活
 * （右键菜单的异步回调里手势已过期，会直接失败并被 catch 吞掉 ⇒ 表现为「粘贴没反应」）。
 *
 * 后端读取无权限、无弹窗、同步可靠。仅在非 Windows 或后端失败时才回退浏览器 API。
 */
async function readClipboardText() {
  try {
    const res = await call("clipboard_get_text");
    if (res && res.status === "ok" && typeof res.text === "string") {
      // read_status==="ok" 表示真的读到了（可能是空串）；busy/unavailable/error 时回退
      if (res.read_status === "ok") return res.text;
      if (res.read_status === "unsupported") {
        /* 非 Windows：走下面的浏览器回退 */
      } else if (res.read_status === "unavailable") {
        // 剪贴板里没有文本（例如复制的是图片）⇒ 不再回退，直接当空处理
        return "";
      }
    }
  } catch (_) {
    /* 后端不可用：回退 */
  }
  try {
    if (navigator.clipboard && typeof navigator.clipboard.readText === "function") {
      return (await navigator.clipboard.readText()) || "";
    }
  } catch (_) {
    /* 权限被拒/无用户激活：当作读不到 */
  }
  return "";
}

/**
 * 写入剪贴板文本。
 *
 * 优先走后端系统剪贴板（`clipboard_set_text`）：WebView2 下 `navigator.clipboard.writeText()`
 * 也可能因窗口未聚焦/权限被拒而失败，而此时用户以为「复制成功了」—— 静默失败最坏。
 * 后端直写无权限、无焦点要求；仅在后端不可用时回退浏览器 API（含 execCommand 兜底）。
 *
 * @param {string} text
 * @returns {Promise<boolean>} 是否写入成功
 */
async function writeClipboardText(text) {
  const value = typeof text === "string" ? text : String(text == null ? "" : text);
  try {
    const res = await call("clipboard_set_text", value);
    if (res && res.status === "ok" && res.written) return true;
  } catch (_) {
    /* 后端不可用：回退 */
  }
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch (_) {
    /* 继续回退 */
  }
  try {
    return document.execCommand("copy");
  } catch (_) {
    return false;
  }
}

async function call(fn, ...args) {
    const a = api();
    if (!a || !a[fn]) throw new Error(T("app.apiUnavailable", { fn }));
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

  /**
   * 启动自动打开（2026-10-22 修）：
   *   优先级 ① 持久化的 lastPath（必须仍在 state.files）→ ② 既有启发式 → ③ 无文件 showWelcome。
   *   用户在此期间主动打开任何文件 ⇒ openSeq 前进 / userNavigated=true ⇒ 这里立即放弃，
   *   不再调用 openFile 做重活，也不回写覆盖用户选择。
   */
  async function bootAutoOpen() {
    if (state.userNavigated) {
      console.log("[boot] auto-open aborted: user navigated");
      return;
    }
    if (!state.files.length) {
      console.log("[boot] fallback: no files");
      showWelcome(true);
      return;
    }
    const token = state.openSeq;
    state.bootAutoOpenPending = true;
    try {
      const persisted = await readPersistedLastFile(state.kbPath);
      if (state.userNavigated || state.openSeq !== token) {
        console.log("[boot] auto-open aborted: user navigated");
        return;
      }
      if (persisted) {
        const exists = state.files.some((f) => f && f.path === persisted);
        if (exists) {
          console.log("[boot] restore last file: " + persisted);
          const outcome = await openFile(persisted, {
            skipNav: true,
            autoBoot: true,
            bootToken: token,
          });
          if (state.userNavigated || state.openSeq !== token) {
            console.log("[boot] auto-open aborted: user navigated");
            return;
          }
          if (outcome === "ok") return;
          console.log("[boot] fallback: restore open failed: " + persisted);
          clearPersistedLastFile(state.kbPath, persisted);
        } else {
          // KB 已删除/改名的旧路径：清掉，避免每次启动都重试失败
          console.log("[boot] fallback: last file missing from KB: " + persisted);
          clearPersistedLastFile(state.kbPath, persisted);
        }
      } else {
        console.log("[boot] fallback: no persisted last file");
      }
      if (state.userNavigated || state.openSeq !== token) {
        console.log("[boot] auto-open aborted: user navigated");
        return;
      }
      const preferred =
        state.files.find((f) => f.path === "navigation-demo.md") ||
        state.files.find((f) => f.path === "mdp.md") ||
        state.files[0];
      if (!preferred) {
        console.log("[boot] fallback: no preferred file");
        showWelcome(true);
        return;
      }
      console.log("[boot] fallback: heuristic " + preferred.path);
      await openFile(preferred.path, {
        skipNav: true,
        autoBoot: true,
        bootToken: token,
      });
    } finally {
      state.bootAutoOpenPending = false;
    }
  }

  async function initKb() {
    try {
      state.kbPath = await resolveStartupKbPath();
      console.log("[initKb] kbPath=" + state.kbPath);
      if (state.kbPath) {
        // task-75：启动初始化窗口开始（见 state.startupInFlight 注释）。
        // 结束点：本分支 finally（含异常路径）—— 期间只有带 bootToken 的内部调用可穿透。
        state.startupInFlight = true;
        // 确保服务端 _kb_root 同步（防止前端通过 remembered path 获取但服务端未设置）
        await call("ensure_kb_root", state.kbPath);
        // 对话面板：启动即已开库（initKb 在面板 init 之后跑）时刷新历史并恢复「上次会话」
        window.MemoriaAgentPanel?.onKbChanged?.();
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
        setStatus(T("app.status.kbLoaded"));
        // 静默后台检查（按设置的间隔轮询；本身已经是 P3 作业，不阻塞）
        window.MemoriaKbCheck?.startKbSilentCheck?.();
        // 打开知识库后自动补写/刷新 Trae 智能体工具包（幂等；不阻塞打开、不弹窗）
        window.MemoriaKbAgent?.ensure?.();
        // 2026-10-22：恢复「最后停留的文件」，且与用户主动导航竞态隔离（见 bootAutoOpen）
        await bootAutoOpen();
        // ★ 2026-10-24（task-84 P1）：图谱数据 + 全库校验**移出首文档关键路径**（见函数注释）
        //   注意必须排在 bootAutoOpen 之后：openFile 会 bumpEpoch（文件级陈旧语义），
        //   而图谱/校验是**库级**任务，若排在前面会被当陈旧作业丢弃（实测过）。
        schedulePostBootDerivedWork();
        state.startupInFlight = false;
      } else {
        state.startupInFlight = false;
        showWelcome(true);
        showKbIndicator("");
        setStatus("Memoria");
      }
    } catch (e) {
      state.startupInFlight = false;
      setStatus(T("app.status.waitingBackend"));
    }
  }

  /**
   * ★ 2026-10-24（task-84 P1）：把「图谱数据（含分组标签）」与「全库校验」移出首文档关键路径。
   *
   * 为什么（boot probe 实测 P50，真机 WebView2）：
   *   `await loadGraphData()`  ≈ 900 ms（含全库 graph_audit 审计）
   *   `await runKbValidate()`  ≈ 1026 ms（同步 validate_kb RPC）
   * 二者串行排在 `bootAutoOpen()` 之前 ⇒ 冷启动 4443ms 里约 1.9s 是在等"用户此刻不需要的东西"
   * （图谱页签/审计提示/状态栏检查统计）。首屏真正需要的只有 refreshFiles + 首文档。
   *
   * 怎么延后（**不自造调度器**，沿既有机制）：
   *  · 前端用 M5 `MemoriaScheduler` 的 P3 队列（与 kb-check.js 静默检查同层）排一个作业；
   *    后端没有 P3 概念，"延后"只能在前端调度里表达。
   *  · 校验复用 kb-check.js 既有的 `submitAsyncValidate()`（validate_kb_async 提交 + job_status
   *    轮询，真异步：提交 0.2–0.3ms、后台线程跑 987ms）；结果仍落 `state.kbValidateReport`，
   *    角标 / 状态栏统计 / 已打开的检查弹窗照旧更新，只是晚到 1~2s。
   *  · 图谱仍走原 `loadGraphData()`（含 refreshGraphGroupLabels + renderGraphGroupTabs +
   *    applyGraphGroupLayout）⇒ 标签与页签最终一定出现，不是"永不加载"。
   *  · 一致性：`state.kbPending` 的刷新路径（refreshKbPendingSummary）完全不动，语义保留。
   *  · 陈旧语义：**故意不用 dropStale/gen** —— 图谱数据与全库校验是**库级**任务，
   *    不应随"文件切换 bumpEpoch"被丢弃（openFile 每次切文件都会 bump）；改成运行前比对
   *    `state.kbPath`：换库/关库才丢弃，同库内切文件照跑。作业排在 bootAutoOpen 之后，
   *    避免与首文档打开争 CPU。
   *  · 调度器缺失（极旧宿主）：退化为下一宏任务，只失去"让位给首屏"，不丢功能。
   */
  function schedulePostBootDerivedWork() {
    const kb = state.kbPath;
    if (!kb) return;
    const run = async () => {
      if (!state.kbPath || state.kbPath !== kb) return; // 换库/关库 ⇒ 陈旧丢弃
      try {
        // ① 图谱数据（buildKb/用户操作可能已加载过 ⇒ 幂等跳过）
        if (!state.graphData) await loadGraphData();
      } catch (_) {
        /* 图谱失败不阻塞后续校验（loadGraphData 内部已有状态提示） */
      }
      if (!state.kbPath || state.kbPath !== kb) return;
      try {
        // ② 全库校验：优先既有真异步路径；旧宿主退化为同步校验（仍在 P3 里，不挡首屏）
        const KbCheck = window.MemoriaKbCheck;
        if (KbCheck && typeof KbCheck.submitAsyncValidate === "function") {
          await KbCheck.submitAsyncValidate();
        } else if (KbCheck && typeof KbCheck.runKbValidate === "function") {
          await KbCheck.runKbValidate({ silent: true });
        }
      } catch (_) {
        /* 校验失败不影响首屏；角标维持上次状态 */
      }
    };
    const S = window.MemoriaScheduler;
    if (S && typeof S.schedule === "function") {
      const id = S.schedule({
        kind: "post_boot",
        key: "post_boot:" + kb,
        priority: 3, // P3：首屏/交互优先，空闲才跑
        replace: true,
        // 不带 gen/dropStale：库级任务不能被"切文件 bumpEpoch"判陈旧（见上方注释）
        run,
      });
      S.note?.("post_boot 入队 #" + id + "（图谱+校验移出首屏）");
    } else {
      // 极旧宿主没有调度内核：退化为「立即执行」，等价于改动前的同步行为（只失去让位首屏）
      run();
    }
  }

  async function refreshKbPendingSummary() {    if (!state.kbPath) {
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

  function resetOpenDocumentUi() { _previewCacheClear(); _preloadResetForNewKb(); // 2026-09-23 性能：换库 ⇒ 预览缓存整库作废（路径键换了一套命名空间）
    _brushDisarmAll();   // S1：换库 = 离开一切可编辑语境 ⇒ 画笔武装一并收掉
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

  /** 在当前窗口装载指定知识库目录（「打开」选目录与「打开最近」共用同一序列）。 */
  async function openKbAt(path) {
    if (!path) return;
    // 先同步后端知识库根（服务实例 + 静态服务 _kb_root）：选目录路径由 select_directory 内部完成，
    // 直接按已知路径装载时必须在此补上，否则后续 list_files 等会返回「未打开知识库」。
    let res = null;
    try {
      res = await call("set_kb_path", path);
    } catch (err) {
      res = { status: "error", message: String(err) };
    }
    if (!res || res.status !== "ok") {
      setStatus(T("app.loadFailed"), (res && res.message) || "");
      return;
    }
    resetOpenDocumentUi();
    state.kbPath = path;
    window.MemoriaAgentPanel?.onKbChanged?.(); // 对话面板：作废跨库会话并尝试恢复本库「上次会话」
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
    setStatus(T("app.status.kbOpened"));
    await window.MemoriaKbCheck?.runKbValidate?.({ silent: false });
    window.MemoriaKbCheck?.startKbSilentCheck?.();
    // 打开知识库后自动补写/刷新 Trae 智能体工具包（幂等；不阻塞打开、不弹窗）
    window.MemoriaKbAgent?.ensure?.();
  }

  async function openKb() {
    const path = await call("select_directory");
    if (!path) return;
    await openKbAt(path);
  }

  async function closeKb() {
    // 关库 → 提升调度 epoch：排队中的旧库作业（如 kb_check）执行前陈旧丢弃（G5.1）
    const _S = window.MemoriaScheduler;
    _S?.bumpEpoch?.();
    _S?.note?.("kb 关闭 epoch→" + (_S.epoch?.() ?? "?") + "（排队旧库作业将陈旧丢弃）");
    // 关库屏障：先保存内存内容并 durable_flush（fsync + manifest pending）
    await flushDurableBarrier();
    try {
      await call("close_kb");
    } catch (_) {
      /* optional */
    }
    state.kbPath = "";
    window.MemoriaAgentPanel?.onKbChanged?.(); // 对话面板：关库后清空当前会话态
    state.files = [];
    state.dirs = []; // 关库需一并清空目录清单，否则文件树仍渲染旧库结构（点击无效）
    state.currentPath = null;
    state.doc = null;
    state.activeKpId = null;
    state.openTabs = []; _previewCacheClear(); _preloadResetForNewKb(); // 2026-09-23 性能：关库 ⇒ 预览缓存整体作废（并与换库同一套复位口径）
    // S1：关库 = 离开一切可编辑语境 ⇒ 画笔武装一并收掉（否则下次开库后仍是武装态）
    _brushDisarmAll();
    state.graphData = null;
    state.graphAudit = null;
    state.kbValidateReport = null;
    state.kbPending = null;
    state.lastFileStats = "";
    window.MemoriaKbCheck?.resetIndicators?.();
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
    window.MemoriaFileTree?.render?.();
    renderTabs();
    const editor = $("#editor");
    if (editor) editor.innerHTML = "";
    const preview = $("#preview");
    if (preview) preview.innerHTML = "";
    const kpList = $("#kp-list");
    if (kpList) kpList.innerHTML = '<div class="empty">' + T("app.status.kbEmpty") + '</div>';
    const kpCount = $("#kp-count");
    if (kpCount) kpCount.textContent = "";
    showWelcome(true);
    window.MemoriaKbCheck?.stopSilentCheck?.();
    setStatus(T("app.status.kbEmpty"), T("app.status.kbEmptyDetail"));
    window.MemoriaKbCheck?.closeCheckModal?.();
  }

  async function refreshFiles() {
    const res = await call("list_files");
    if (res.status !== "ok") {
      setStatus(res.message || T("app.listFailed"));
      return;
    }
    state.files = res.files || [];
    state.dirs = res.dirs || []; _previewCacheClear(); // 2026-09-23 性能：文件集合变了（重命名/删除/新建/导入/刷新）⇒ 预览缓存整体作废（避免留下失效的路径键）
    updateSidebarTabCounts();
    window.MemoriaFileTree?.render?.();
  }

  // 文件树渲染/展开折叠/点击切换文档/右键新建·重命名·删除等已随文件树子系统迁至 file-tree.js
  // （window.MemoriaFileTree；boot 在 MemoriaKbCheck.init 后 init，refreshFiles/openFile/
  //  closeKb/closeTabAt/KP 写回等经 render/expandToPath 触发重新渲染）。

  // ── 文件树右键浮层（通用 .-context-menu 渲染与确认弹窗：image-tools.js 亦经门面共用，保留）────

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
          <button type="button" class="-btn" data-act="cancel">${T("common.cancel")}</button>
          <button type="button" class="-btn danger" data-act="ok">${esc(okLabel || T("common.ok"))}</button>
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
        label: T("graph.group.allLabel"),
        title: T("graph.group.allTitle"),
        count: groups.length || null,
      },
      ...groups.map((g) => ({
        id: g.id,
        label: g.label || g.hubName || g.hubId || g.id,
        title: T("graph.group.tabTitle", {
          name: g.hubName || g.hubId || g.id,
          size: g.size,
          edges: g.edgeCount,
        }),
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
    const onGraphNodeClick = ({ node, edge_id }) => {
      // KG-v0 D-KG-07 埋点②：图节点点击**计数消费**（此前 `source:"graph"` 标记从未被统计）。
      //
      // ## 隐私边界（KG-v0 D-KG-07，必须保持）
      // 只记**交互标识**：节点 id / 边标识 / 来源 / 时间戳。
      // **不记文档正文、不记用户输入、不落盘、不跨会话、不建用户画像** —— 纯内存计数器，
      // 页面刷新即清零。它的唯一用途是回答「这条边/这个节点被点过吗」。
      recordGraphInteraction("nodeClick", node, edge_id);
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
    "distMode",
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

  // 构建是重活且**不可并发**：连点会让多条构建指令排队，表现为"构建完又构建"。
  // 用显式的在飞标志做幂等，而不是只靠按钮 disabled —— disabled 会被中途的状态刷新/重渲染绕过，
  // 且它保护不了非按钮入口（快捷键/命令面板）。后到的请求一律**忽略**（构建一次就够）。
  let buildInFlight = false;

  async function buildKb() {
    if (buildInFlight) {
      console.info("[BUILD] 已在构建中，忽略本次重复请求");
      return;
    }
    if (!state.kbPath) {
      setStatusError(T("app.openKbFirst"));
      return;
    }
    buildInFlight = true;
    const btn = $("#btn-build");
    if (btn) btn.disabled = true;
    setStatus(T("graph.build.building"), T("graph.build.buildingDetail"));
    try {
      const res = await call("build_kb");
      if (res.status === "error") {
        setStatus(res.message || T("graph.build.failed"));
        return;
      }
      await refreshFiles();
      await loadLinkTargets();
      await loadGraphData();
      if (state.currentPath) {
        await openFile(state.currentPath, { skipNav: true });
      }
      const msg = res.message || T("graph.build.done");
      const stats = res.warn_count
        ? T("graph.build.doneDetail", { msg, n: res.warn_count })
        : msg;
      setStatus(T("graph.build.done"), stats);
      if (res.warn_count > 0 && res.audit) {
        const kinds = Object.entries(res.audit.by_kind || {})
          .filter(([, n]) => n > 0)
          .map(([k, n]) => `${k}: ${n}`)
          .join(" · ");
        if (kinds) setStatus(T("graph.build.done"), T("graph.build.doneKinds", { stats, kinds }));
      }
    } catch (e) {
      setStatus(T("graph.build.failed"), String(e.message || e));
    } finally {
      buildInFlight = false;
      if (btn) btn.disabled = false;
    }
  }

  async function loadGraphData() {
    if (!state.kbPath) return;
    try {
      const res = await call("get_graph_data");
      if (res.status !== "ok") {
        setStatus(res.message || T("graph.loadFailed"));
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
      setStatus(T("graph.loadFailed"), String(e.message || e));
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
    // 审计条目跳转 = 用户定位：入栈并丢弃旧前向（openFile 内统一处理）
    await openFile(rel, { kpId: issue.kp_id || null, navSource: "audit" });
    if (issue.line) {
      highlightRange(issue.line, issue.line);
      document
        .getElementById(`line-${issue.line}`)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    setStatus(T("check.status.graphEdgeAt", { file: basename(rel) }), localizeCheckIssue(issue) || "");
    updateGraphAuditHint();
  }

  function graphAuditHintLabel(issue) {
    const fileLabel = basename(issue.file || "");
    const loc = issue.line ? `L${issue.line}` : "";
    if (fileLabel && loc) return `${fileLabel} · ${loc}`;
    return fileLabel || loc || T("check.pending");
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
      hint.innerHTML = `<span class="-graph-audit-warn">⚠ ${T("check.hint.file", {
        label: esc(graphAuditHintLabel(first)),
        message: esc(localizeCheckIssue(first)),
      })}</span>
        <button type="button" class="-btn secondary -btn--sm -graph-audit-goto">${T("check.openFile")}</button>`;
      return;
    }
    const kbWarns = collectKbGraphAuditWarns(state.graphAudit);
    if (kbWarns.length) {
      const first = kbWarns[0];
      const fileCount = new Set(kbWarns.map((w) => normRelPath(w.file))).size;
      hint.innerHTML = `<span class="-graph-audit-warn">⚠ ${T("check.hint.kb", {
        n: kbWarns.length,
        file: esc(basename(first.file)),
        more: fileCount > 1 ? T("check.stat.moreFiles", { n: fileCount }) : "",
        message: esc(localizeCheckIssue(first)),
      })}</span>
        <button type="button" class="-btn secondary -btn--sm -graph-audit-goto">${T("check.openFileNamed", { file: esc(basename(first.file)) })}</button>`;
      return;
    }
    hint.innerHTML =
      state.sidebarTab === "graph3d"
        ? `<span class="-muted">${T("graph.hint.idle3d")}</span>`
        : `<span class="-muted">${T("graph.hint.idle2d")}</span>`;
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
    // 2026-09-17：左栏「对话」页签已迁为右侧 #-agent-dock，旧 localStorage["-sidebar-tab"]
    // 若仍为 "agent" 会命中不到任何 [data-sidebar-view] ⇒ 三个视图全被隐藏。无对应视图即回退 files。
    if (!document.querySelector('[data-sidebar-view="' + tab + '"]')) tab = "files";
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

  // 文件树渲染已迁至 file-tree.js：app.js 各调用点经 window.MemoriaFileTree?.render?.() / expandToPath

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
    if (previewPane && tab.previewScroll != null) previewPane.scrollTop = tab.previewScroll;   // 2026-09-25 AG97：窗口化回退 ⇒ 裸像素照旧写（守卫随窗口化一起删除）
    if (kpList && tab.kpListScroll != null) kpList.scrollTop = tab.kpListScroll;
  }

  function closeTabAt(index) {
    const tab = state.openTabs[index];
    if (!tab) return;
    const wasActive = tab.path === state.currentPath;
    state.openTabs.splice(index, 1);
    _previewCacheDrop(tab.path); // 2026-09-23 性能：页签关闭 ⇒ 立刻丢掉它的预览缓存条目（不留下无主的 DocumentFragment）
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
      window.MemoriaFileTree?.render?.();
      renderKpList(null);
      window.MemoriaToolbarSearch?.syncScope?.();
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
    // 标签切换 = 用户导航：非 skipNav（如关闭标签后的自动激活）时交给 openFile 统一入栈；
    // skipNav=true 属程序自动激活，不产生历史条目。
    await openFile(path, {
      fromNav: !!opts.skipNav,
      skipTabUpsert: true,
      restoreScroll: true,
    });
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
        return `<div class="${cls}" data-tab-index="${i}" title="${esc(t.path)}" draggable="true">
          <span class="tab-label">${esc(t.label || basename(t.path))}</span>
          <span class="close-btn" data-tab-close="${i}" title="${T("common.close")}">×</span>
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

  // 树内点击切换文档（原 navigateToFile）已随文件树子系统迁至 file-tree.js

  async function openFile(relPath, opts = {}) {
    // ★ task-75（2026-10-24）：启动早期调用必须**先判可用性，再动任何状态**。
    //   旧行为：先 `state.openSeq++` / `state.userNavigated = true`，再去 `await load_document`；
    //   而启动早期 bridge/后端还没就绪 ⇒ `load_document` 直接抛「API 不可用」，但"用户已导航"
    //   标记已经落下 ⇒ bootAutoOpen 打印 `[boot] auto-open aborted: user navigated` 并放弃
    //   ⇒ 最终**一篇文档都不打开**（currentPath 永远 null）、调用方只看到 reject、
    //   应用日志里只有一条误导性的"用户已导航"。这就是「启动后立即调 openFile 静默失效」。
    //   现在：前置条件不满足时返回明确的 `"failed"` + 可见状态提示 + console.warn，
    //   **不触碰 openSeq/userNavigated** ⇒ 启动自动打开照常完成；调用方可稍后重试。
    if (!relPath || typeof relPath !== "string") {
      console.warn("[openFile] 参数无效（relPath 为空/非字符串），已拒绝");
      return "failed";
    }
    const _bridge = (window.MemoriaBridge && typeof window.MemoriaBridge.api === "function")
      ? window.MemoriaBridge.api() : null;
    if (!_bridge || typeof _bridge.load_document !== "function") {
      console.warn("[openFile] 后端尚未就绪（bridge.load_document 不可用），已拒绝：" + relPath);
      setStatus(T("app.status.waitingBackend"), relPath);
      return "failed";
    }
    if (!state.kbPath) {
      console.warn("[openFile] 知识库尚未就绪（state.kbPath 为空），已拒绝：" + relPath);
      setStatus(T("app.status.waitingBackend"), relPath);
      return "failed";
    }
    // task-75：启动初始化进行中（ensure_kb_root/refreshFiles/loadLinkTargets 在飞）⇒ 外部调用
    // 明确拒绝：此时发起 load_document 会与启动 RPC 交错，实测能把 boot 卡死（files 永远 0）。
    // 启动自动打开自身带 bootToken，穿透放行。
    if (state.startupInFlight && opts.bootToken == null) {
      console.warn("[openFile] 启动初始化尚未完成，已拒绝（请稍后重试）：" + relPath);
      setStatus(T("app.status.waitingBackend"), relPath);
      return "failed";
    }
    // 用户主动打开（文件树点击 / 命令面板 / 快捷键 / 搜索跳转 / 标签切换 …）一律优先：
    // 立即推进 openSeq 并置 userNavigated，使正在等待/渲染的启动自动打开作废。
    if (opts.skipNav !== true) {
      state.openSeq++;
      state.userNavigated = true;
      if (state.bootAutoOpenPending) console.log("[boot] auto-open aborted: user navigated");
    }
    // 启动自动打开：调用点已记录 token；若期间用户已导航（或又发生一次打开）⇒ 不进入重活。
    if (opts.bootToken != null && (state.openSeq !== opts.bootToken || state.userNavigated)) {
      if (opts.autoBoot) console.log("[boot] auto-open aborted: user navigated");
      return "aborted";
    }
    // 文件上下文切换 → 提升调度 epoch，使基于旧文件的排队作业（如 kp_panel）陈旧可弃
    window.MemoriaScheduler?.bumpEpoch?.(); _preloadStop("switch"); _lastSwitch.hit = false; const _t0Switch = performance.now(); _switchAbs = _t0Switch; _switchPhases = {}; if (!opts.fromNav && window.MemoriaPositionMemory) window.MemoriaPositionMemory.remember(); // 2026-10-06 位置记忆：**在 push/换文件之前**采当前视口顶部源码行（AG105 纪律）；fromNav 由调用方采 // 2026-09-23 性能：切页签即中止在跑的后台预渲染，并开始计时（见文件末尾「预览 DOM 缓存 + 后台预渲染」块）；2026-09-24：把起点交给**外层阶段计时**（`_markPhase`，读数里的「切页签阶段」）
    // 导航栈记录：凡「非 skipNav / 非 fromNav」的用户切换，push() 会丢弃当前指针往上的
    // 旧尾、插入本次切换目标并把指针移到新顶（因此前进随之不可用）。后退/前进按钮
    // （fromNav=true）与程序内部重载（skipNav=true）不产生新条目。
    if (!opts.skipNav && !opts.fromNav && window.MemoriaNavStack) {
      const cur = MemoriaNavStack.current();
      const targetKp = opts.kpId || null;
      if (!cur || cur.file !== relPath || (cur.kpId || null) !== targetKp) {
        MemoriaNavStack.push({
          file: relPath,
          kpId: targetKp,
          source: opts.navSource || "open",
        });
        updateNavButtons();
      }
    }
    // 切换文件前：同步当前文件到磁盘并触发 durable_flush 屏障（fsync+manifest）
    if (state.currentPath && state.currentPath !== relPath) {
      await flushDurableBarrier();
      _saveCurrentTabScroll();
    }
    // await 期间用户可能已经打开别的文件：在清理/搬运预览 DOM 之前再次作废。
    if (opts.bootToken != null && (state.openSeq !== opts.bootToken || state.userNavigated)) {
      if (opts.autoBoot) console.log("[boot] auto-open aborted: user navigated");
      return "aborted";
    }
    cancelKpHighlightTimers();
    clearHighlights();
    clearPreviewHighlights();
    clearGraphLinkHighlight();
    clearGraphKpHover(); if (state.currentPath && state.currentPath !== relPath) _previewCacheStash(state.currentPath); _markPhase("stash"); // 2026-09-23 性能：切页签前把当前预览 DOM 整体搬进缓存（移动节点，见文件末尾「预览 DOM 缓存 + 后台预渲染」块）；`stash` = 这段 + 之前那点收尾（含 `_estimatePreviewBytes` 的整树遍历）
    setStatus(T("app.loading"), relPath);
    const res = await call("load_document", relPath); _markPhase("load");   // `load` = 后端读文件 + 解析 AST + sha256 的 IPC 往返（有 FIFO 24 条文档缓存）
    // ★ 关键竞态点：load 期间用户可能已打开别的文件。此处必须在写任何 state 之前放弃，
    //   否则会把用户刚打开的页面「拽回」启动自动打开的目标。
    if (opts.bootToken != null && (state.openSeq !== opts.bootToken || state.userNavigated)) {
      if (opts.autoBoot) console.log("[boot] auto-open aborted: user navigated");
      return "aborted";
    }
    if (res.status !== "ok") {
      setStatus(res.message || T("app.loadFailed"));
      // KB 已删除该文件：清掉持久化，避免每次启动都重试一条不存在的路径
      clearPersistedLastFile(state.kbPath, relPath);
      return "failed";
    }
    state.currentPath = relPath;
    state.doc = res;
    state.activeKpId = opts.kpId || null;
    // load_document 成功 ⇒ 文件确实已打开：立刻记「最后停留文件」（本地同步 + 磁盘异步），
    // 不必等整篇渲染收尾，避免用户打开后马上退出导致丢记录。
    rememberLastFile(relPath);
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
    window.MemoriaFileTree?.expandToPath?.(relPath);
    window.MemoriaFileTree?.render?.();
    renderTabs();
    renderEditor(res);
    srcResetUndo();
    renderKpList(res); _markPhase("editor");
    // 2026-09-25 AG97：窗口化（K4a）已整体回退 ⇒ 跳转不再需要"先给窗口定锚"，回到"渲染完整篇后由 `highlightRange` / `_scrollToSrcLine` 定位"（本行原地保留以维持行号）
    // 同上：`setAnchorLine` 已随窗口化一起删除（本行原地保留以维持行号）
    // 恢复左侧知识点栏滚动位置（除非有 KP 跳转目标会滚动到特定 KP）
    const hasKpJump = opts.kpId || opts.errorHighlight?.kpId;
    if (!hasKpJump) {
      const tab = state.openTabs.find((t) => t.path === relPath);
      const kpList = $("#kp-list");
      if (tab && kpList && tab.kpListScroll != null) {
        kpList.scrollTop = tab.kpListScroll;
      }
    }
    _markPhase("viewIn"); await setViewMode(state.viewMode, { skipSave: true }); _markPhase("render"); // `render` = `setViewMode`（含其内部的预览渲染 ⇒ 命中时即上面的「切页签分段」）；减去它才知道下面 `settle` 里剩什么
    // 2026-09-23 性能：此处**不再**二次 `renderPreview(res)` —— 原写法被重入保护排成"重跑"，整篇解析/渲染/MathJax 全做两遍（实测 2712 行文档 mathjax 4.2s→见 §性能取证）。
    // 渲染可能因重入保护被"排队重跑"（重跑会重建 preview DOM 并清掉高亮），
    // 等最终一轮渲染结束再执行下方的高亮/定位，否则 band 会被重跑清掉
    await _waitRenderSettled(); _markPhase("settle");   // `settle` = 等同步渲染那一轮落定（**不等 MathJax**）。真机读数里这 729 ms 既不在恢复、也不在 MathJax ⇒ 看下面两个**异步标记**（paint / mathjax）
    // 切换文件：预览区是全新 DOM，旧文件的编辑光标不继承（selection 可能残留，显式清空）
    if (window.MemoriaEditHandler) window.MemoriaEditHandler._caretInPreview = false;
    // S1：切文件必须清画笔武装 —— 否则新文件里第一次拖动就会把样式涂上去（跨文件误写）
    _brushDisarmAll();
    window.MemoriaImageTools?.refreshImageInsertAvailability?.();
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
      // 知识点跳转（搜索/链接/审计/stale 重放）。2026-10-19 修「静默失败」：
      // 原写法只在 `rr?.ok` 时 `highlightRange`，失败（后端 `{ok:false,error}`，见 range/locator.py、
      // services/kp_resolver.py 的 `missing_snippet`）或 KP 不存在时**什么都不做** ⇒ 用户只看到停在文档顶部。
      // 现在：成功=现状；失败/找不到 ⇒ 有合法 `lineHint` 就降级为单行定位，并**一律**给底栏可见提示。
      // 注意：不改动上方 `restoreScroll` / `errorHighlight` 两条既有优先级（各有独立用途）。
      const kp = (res.knowledge_points || []).find((k) => k.id === opts.kpId);
      const rr = kp?.range_resolved;
      if (rr?.ok) {
        highlightRange(rr.start_line, rr.end_line);
      } else {
        // 降级目标行：优先 opts.lineHint，其次 KP 配置里的 line_hint（`range.start.line_hint`）
        const hintRaw = opts.lineHint != null && opts.lineHint !== "" ? opts.lineHint : kp?.range?.start?.line_hint;
        const hintLine = parseInt(String(hintRaw == null ? "" : hintRaw), 10);
        const hasHint = Number.isFinite(hintLine) && hintLine > 0;
        if (hasHint) {
          // 未解析的 KP 没有可信区间 ⇒ 只定到起始提示行（单行），不误标整段
          highlightRange(hintLine, hintLine);
        }
        // 未找到该 KP（无 kp / 无 range_resolved）≠ 范围解析失败，分开措辞
        const rrMissing = !kp || rr == null;
        if (!rrMissing) {
          // 范围解析失败：错误码经既有 errorLabel 本地化（start/end_snippet_not_found 等），只进 flash 详情
          showFlashInfo(
            T("app.jump.kpReason", { reason: rr.error ? errorLabel(rr.error) : T("app.jump.kpResolveFailed") })
          );
        }
        setStatusError(
          rrMissing || !hasHint
            ? T(rrMissing ? "app.jump.kpNotFound" : "app.jump.kpUnresolved")
            : T("app.jump.kpDegraded", { line: hintLine })
        );
      }
      // 左侧知识点栏定位到对应 KP（搜索跳转/直接跳转）
      scrollKpListItemIntoView(opts.kpId);
    } else if (opts.lineHint) {
      const line = parseInt(String(opts.lineHint), 10);
      if (Number.isFinite(line) && line > 0) {
        highlightRange(line, line);
      }
    }
    if (window.MemoriaPositionMemory) window.MemoriaPositionMemory.restoreForOpen(opts); let stats = T("app.stat.kpLines", {
      kp: res.knowledge_points.length,
      lines: res.lines.length,
    });
    const sv = res.sidecar_validation;
    if (sv && (!sv.ok || sv.warnings?.length)) {
      const parts = [];
      if (sv.errors?.length)
        parts.push(T("app.stat.errors", { n: sv.errors.length }));
      if (sv.warnings?.length)
        parts.push(T("app.stat.warnings", { n: sv.warnings.length }));
      stats += T("app.stat.sidecar", { parts: parts.join(" ") });
    }
    setStatus(relPath, stats);
    syncGraphAuditStatusBar(stats);
    updateGraphAuditHint();
    window.MemoriaToolbarSearch?.syncScope?.(); _markPhase("tail"); _lastSwitch.ms = Math.round(performance.now() - _t0Switch); _previewCacheNoteLoad(_lastSwitch.ms); // 2026-09-24 追加：把本次**冷加载**耗时交给池（切走时挂到该条画像上）；`tail` 前一步先落表 ⇒ 阶段表给出的就是"从点击到状态栏收尾"的完整账
    // 只在「真正打开成功且仍是当前文件」时记录最后停留文件：
    // 渲染期间用户已切到 B 的，A 不得把 B 的持久化覆盖回 A。
    if (state.currentPath === relPath) rememberLastFile(relPath);
    return "ok";
  }

  // 分栏模式滚动同步：源码滚动→预览跟随，预览滚动→源码跟随
  let splitSyncLock = false;
  // 回声抑制：程序化滚动会在**被同步的那一侧**再触发一次 scroll 事件；若让这次事件
  // 反向同步回来，就会出现"滚动被弹回"——因为反向对齐是把块**顶边**对到容器顶边，
  // 比用户原来的位置更高，每次来回都往上弹一截。块越高越明显（$$ 公式块/图片/代码块）。
  // 记下程序化滚动的落点，消费掉那一侧的下一次同位置 scroll 事件即可断开环。
  let splitEcho = null;

  function _markSplitEcho(mode, pane) {
    if (!pane) return;
    // 读回浏览器实际落点（目标可能被 clamp 到 max），保证回声判定能对上；
    // 300ms 内的同侧事件一并视为回声（Chromium 偶发对一次程序化滚动发多个 scroll）
    splitEcho = { mode: mode, top: pane.scrollTop, until: performance.now() + 300 };
  }

  function _consumeSplitEcho(mode, pane) {
    if (!splitEcho || splitEcho.mode !== mode) return false;
    const near = Math.abs(pane.scrollTop - splitEcho.top) <= 2;
    const fresh = performance.now() <= splitEcho.until;
    splitEcho = null;
    return near || fresh;
  }

  function _onSplitPaneScroll(mode, pane) {
    if (state.viewMode !== "split" || splitSyncLock) return;
    if (_consumeSplitEcho(mode, pane)) return;   // 刚被程序化滚动的回声 → 丢弃，不反向同步
    splitSyncLock = true;
    const line = _getViewTopSrcLine(mode);
    if (line != null) {
      const other = mode === "source" ? "preview" : "source";
      if (_scrollToSrcLine(other, line)) {
        _markSplitEcho(other, other === "source" ? $("#editor-pane") : $("#preview-pane"));
      }
    }
    requestAnimationFrame(() => { splitSyncLock = false; });
  }

  function setupSplitScrollSync() {
    const editorPane = $("#editor-pane");
    const previewPane = $("#preview-pane");
    // E26：用户滚动豁免监听**启动即绑**（而不是等第一次编辑时才懒绑）——
    // 否则「先滚上去看上文，再敲第一个字」这一拍还没有守卫，光标会被拽回。
    _bindUserScrollGuard(editorPane);
    _bindUserScrollGuard(previewPane);
    if (editorPane) {
      editorPane.addEventListener("scroll", () => _onSplitPaneScroll("source", editorPane));
    }
    if (previewPane) {
      previewPane.addEventListener("scroll", () => _onSplitPaneScroll("preview", previewPane));
    }
  }

  function renderEditor(doc) {
    const desc = (doc.sidecar && doc.sidecar.description) || "";
    $("#file-meta").textContent = desc;

    const editor = $("#editor");
    // 全量渲染遵循当前编辑模式（关闭编辑时行保持只读，视图切换后不恢复可编辑）
    const srcEditable =
      !window.MemoriaEditHandler || window.MemoriaEditHandler.editMode ? "true" : "false";
    editor.innerHTML = doc.lines
      .map((line, i) => {
        const n = i + 1;
        const content = esc(line) || "<br>";
        return `<div class="-line" data-line="${n}" id="line-${n}">
          <span class="-lineno">${n}</span>
          <span class="-line-content" contenteditable="${srcEditable}" spellcheck="false" tabindex="-1">${content}</span>
        </div>`;
      })
      .join("");
    // 行号列宽按总行数位数自适应（见 .-lineno 的 --lineno-ch）
    editor.style.setProperty(
      "--lineno-ch",
      String(Math.max(1, String(doc.lines.length).length))
    );
  }

  async function setViewMode(mode, opts) {
    const prevMode = state.viewMode;
    let alreadyRendered = false;
    state.viewMode = mode;
    if (!opts?.skipSave) {
      localStorage.setItem("-view", mode);
    }
    // 页签切换前：将源码编辑器内容同步到内存，刷新两个视图
    if (prevMode !== mode) { _previewCacheDrop(state.currentPath); _previewDomKey = null; // 2026-09-23 性能：视图模式变了 ⇒ 当前文档的预览缓存作废（渲染差异与视图模式相关）
      clearTimeout(_renderTimer);
      _renderTimer = null;
      syncLog("setViewMode:", prevMode, "→", mode, "| dirty=", _dirty);
      // 始终从源码编辑器收集（它是 markdown 源，不会丢失格式）
      const body = collectEditorBody();   var _viewAnchorBeforeRerender = _getViewTopSrcLine(prevMode); _saveCurrentViewScroll(prevMode);   // 2026-09-25 AG105：**锚点与滚动位置必须在重渲染之前采** —— 下面的 `renderEditor()`/`renderPreview()` 会把两个视图都刷回顶部，之后再量到的"顶部行"永远是第一行（人：「从预览区域切换分栏等其他模式仍有位置漂移」的根因）
      if (body !== null) {
        state.doc.body = body;
        state.doc.lines = _linesFromBody(body);
        state.doc.preview_body = null;
        syncLog("setViewMode: 更新 state.doc.body, 前80字:", body.substring(0, 80));
      }
      // 从内存重新渲染两个视图
      syncLog("setViewMode: 重新渲染编辑器和预览");
      // 2026-09-25 AG97：窗口化（K4a）已整体回退 ⇒ 此处不再需要"重渲染前把视口顶部行交给窗口"（本行原地保留以维持行号）
      renderEditor(state.doc);
      await renderPreview(state.doc);
      alreadyRendered = true;
      // 触发写盘
      if (_dirty) { clearTimeout(_saveTimer); _saveTimer = null; syncToDisk(); }
      // 2026-09-25 AG105：`_saveCurrentViewScroll(prevMode)` 已**上移到重渲染之前**（此处再存会存到"被刷回顶部"后的位置）—— 本行原地保留以维持行号
    }
    // 记录源码行号锚点：用于跨视图（源码↔预览）的文本位置映射
    let anchorLine = null;
    if (prevMode !== mode) {
      anchorLine = _viewAnchorBeforeRerender;   // 2026-09-25 AG105：用重渲染**之前**采到的锚点（原来在这里现量 ⇒ 量到的已是刷回顶部后的那一屏）
    }
    const split = $("#editor-split");
    split.classList.remove("view-source", "view-preview", "view-split");
    split.classList.add(`view-${mode}`);
    document.querySelectorAll(".-view-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === mode);
    });
    // 视图切换后预览区可见性变化，刷新图片插入按钮的可用状态
    window.MemoriaImageTools?.refreshImageInsertAvailability?.();
    if (mode !== "source" && state.doc && !alreadyRendered) {
      _markPhase("viewPre");   // 2026-09-24 读数：`渲染分段` 全程只有 100 ms 而 `postRender` 三万 ms ⇒ 那 33 s 在 `renderPreview` **之前**；这一段（`setViewMode` 里 `await renderPreview` 之前）由 `editor→viewIn`→`viewPre` 两次打点切开
      await renderPreview(state.doc); _markPhase("rpEnd");   // 2026-09-24：把 `render` 那一段从中间切开 —— 到这里 = `setViewMode` 里除"换类名"之外的全部（命中时即恢复那 390 ms）；它到 `render` 之间应≈0，否则说明慢在 `renderPreview` 之外
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

  // ── E26：编辑后保持光标可见（源码区 / 预览区共用）──────────────────────────
  // 只做**最小滚动**：光标矩形仍在 pane 视口内（含 margin）⇒ 一像素都不动，
  // 避免"每次输入都跳"；只有越出视口才按差值补 scrollTop。
  // pane 自身的 scroll 事件仍会走 `_onSplitPaneScroll`（分栏同步），与既有行为一致。
  //
  // 用户主动滚动的短时豁免：仓库原无 claimScroll 一类机制（全仓检索确认），
  // 这里是唯一实现点 —— 用 wheel / 触摸 / 拖滚动条三种**确定是用户意图**的输入打时间戳，
  // 命中后的 700 ms 内不自动补滚，避免"刚滚上去看上文，敲一个字又被拽回底部"。
  // 不监听 scroll 事件：分栏同步、懒加载锚点补偿也会改 scrollTop，会误判成用户滚动。
  var _lastUserScrollAt = 0;
  var USER_SCROLL_GRACE_MS = 700;

  function _keepCaretDebug() {
    return {
      userScrollAgoMs: _lastUserScrollAt ? Math.round(performance.now() - _lastUserScrollAt) : null,
      graceMs: USER_SCROLL_GRACE_MS,
    };
  }

  function _bindUserScrollGuard(pane) {
    if (!pane || pane._memoriaScrollGuardBound) return;
    pane._memoriaScrollGuardBound = true;
    const mark = () => { _lastUserScrollAt = performance.now(); };
    pane.addEventListener("wheel", mark, { passive: true });
    pane.addEventListener("touchmove", mark, { passive: true });
    // 拖滚动条：pointerdown 落在 pane 自身且横坐标越过内容宽度（= 竖向滚动条区域）
    pane.addEventListener("pointerdown", (e) => {
      if (e.target !== pane) return;
      if (e.offsetX >= pane.clientWidth) mark();
    }, { passive: true });
  }

  function _userScrolledRecently() {
    return !!_lastUserScrollAt && (performance.now() - _lastUserScrollAt) < USER_SCROLL_GRACE_MS;
  }

  function _caretRect(range, fallbackEl) {
    let rect = null;
    try { rect = range.getBoundingClientRect(); } catch (_) { rect = null; }
    // 空行 / <br> 上的折叠光标常给出全 0 的 rect ⇒ 退回所在行元素。
    if ((!rect || (rect.width === 0 && rect.height === 0 && rect.top === 0 && rect.left === 0)) && fallbackEl) {
      try { rect = fallbackEl.getBoundingClientRect(); } catch (_) { rect = null; }
    }
    return rect;
  }

  function _keepCaretVisible(pane, range, fallbackEl, margin) {
    if (!pane || !range) return false;
    _bindUserScrollGuard(pane);
    if (_userScrolledRecently()) return false;   // 用户刚手动滚过 ⇒ 短时间内不强行拽回
    const paneRect = pane.getBoundingClientRect();
    const caretRect = _caretRect(range, fallbackEl);
    if (!caretRect || (!caretRect.width && !caretRect.height && !caretRect.top)) return false;
    const m = margin == null ? 8 : margin;
    let delta = 0;
    if (caretRect.bottom > paneRect.bottom - m) {
      delta = caretRect.bottom - (paneRect.bottom - m);
    } else if (caretRect.top < paneRect.top + m) {
      delta = caretRect.top - (paneRect.top + m);
    }
    if (!delta) return false;
    const before = pane.scrollTop;
    const max = Math.max(0, pane.scrollHeight - pane.clientHeight);
    pane.scrollTop = Math.max(0, Math.min(before + delta, max));
    return pane.scrollTop !== before;
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
      if (previewPane && tab.previewScroll != null) previewPane.scrollTop = tab.previewScroll;   // 2026-09-25 AG97：与上面那处同款 —— 守卫随窗口化一起删除
    }
  }

  let _renderingPreview = false;
  let _renderPending = false;  // 全量渲染被重入保护跳过时置位，当前渲染完成后自动补一次
  // 渲染重入保护会产生"排队重跑"，重跑会清空并重建 preview DOM；
  // 依赖 DOM 的操作（如 KP 高亮 band）必须等最终一轮渲染完成后再执行。
  let _renderSettledWaiters = [];
  function _notifyRenderSettled() {
    const waiters = _renderSettledWaiters;
    _renderSettledWaiters = [];
    for (const fn of waiters) {
      try { fn(); } catch (_) { /* noop */ }
    }
  }
  function _waitRenderSettled() {
    return new Promise((resolve) => {
      if (!_renderingPreview && !_renderPending) return resolve();
      _renderSettledWaiters.push(resolve);
    });
  }
  var _blockLineMap = null;  // blockIndex → { startLine, endLine } (0-based)｜2026-10-20 P2：改为 **BlockIndex 的派生投影**（保留形状供既有消费者零改动）

  /**
   * ★ 块身份索引 —— **全 App 唯一实例**（Lead 裁决 2026-10-20，P2）
   *
   * 暴露：`window.MemoriaApp.blockIndex`（见门面）。消费者（KP 面板 / 编辑模块 / 助手面板）
   * **只读**：只可用 blocks() / get() / atSrcLine() / rangeOf() / blocksInRange() / isFrozen() / getMetrics()，
   * **不得**调 upsert() / commit() / remove() —— 写权限唯一属于渲染内核（stampBlockLines 薄壳、
   * reRenderBlock、renderPreview、缓存搬回）。违反 = 制造第二套坐标（宪章 §5.2 验收 #1 禁止的"绕开"）。
   *
   * 生命周期（见 docs/design/block-identity-design.md §7.3 + P2 草稿 §3.0）：
   *   · 本处创建（早于任何渲染）
   *   · 整篇路径（renderPreview / 差分渲染 / 换文件 / 缓存搬回）⇒ beginStamp({reset:true})
   *   · 局部路径（reRenderBlock 单块重渲，**打字热路径**）⇒ beginStamp() 不 reset + 显式 id 就地 upsert
   *   · 预渲染另一篇文档 ⇒ **独立临时实例**（用完即弃），绝不碰本实例（A14）
   */
  var BI = window.MemoriaBlockIndex.createBlockIndex();

  /**
   * 把 AST 的块行区间投射到 BlockIndex，并派生 `_blockLineMap` 兼容投影。
   *
   * 2026-10-20 P2 重写：**删掉原先 8 类正则启发式**（空行/fence/$$/表格/列表/引用）。
   * 行区间**只**来自 `parser.js emit()` 落盘的 `blk.srcLine / blk.srcLineEnd`（1-based 闭区间，
   * parser 注释自称"块↔源码行的单一事实源，不得再各自复写一套块边界判定"）。
   * `data--src-line` / `data--src-line-end` 的写入**只发生在 block-index.js 的 upsert() 内**
   * （R3：属性是派生投影；门禁 check_line_attr_gate.js 校验）。
   *
   * @param {HTMLElement} preview 容器（块元素的父级）
   * @param {object} doc AST（blocks[] 带 srcLine/srcLineEnd）
   * @param {object} [opts] opts.reset=true ⇒ 整篇重建（清空索引）；默认 false ⇒ 增量（局部路径）
   *                       opts.index ⇒ 投射到**指定实例**（默认主实例 BI）。
   *                         ★ 唯一用途：预加载另一篇文档时用**独立临时实例**（G2/A14：绝不污染 BI）。
   */
  function stampBlockLines(preview, doc, opts) {
    if (!doc || !doc.blocks || !preview) return;
    var reset = !!(opts && opts.reset);
    var target = (opts && opts.index) || BI;   // G2：预加载传独立实例 ⇒ 主实例零影响

    // block-index → 元素。
    // 2026-10-22 阶段0：整篇渲染路径已由 `renderDocument` 产出 `blockEls`（与 `doc.blocks` 一一对应、
    //   文档序）⇒ 直接复用，省掉一次全篇 `querySelectorAll`。其它调用方（编辑路径/预加载）不传 ⇒ 走原查询，
    //   **缺省行为逐字不变**。
    var byIdx = new Map();
    if (opts && Array.isArray(opts.blockEls) && opts.blockEls.length === doc.blocks.length) {
      // 长度必须与 AST 块数严格一致；不符 ⇒ 退回查询（宁可慢一次，不许错位）
      for (var _bi = 0; _bi < opts.blockEls.length; _bi++) byIdx.set(String(_bi), opts.blockEls[_bi]);
    } else {
      preview.querySelectorAll(".-src-block[data--block-index]").forEach(function (el) {
        byIdx.set(el.getAttribute("data--block-index"), el);
      });
    }

    target.beginStamp({ reset: reset });
    var mapped = 0;
    // 2026-10-22 性能修复（B1）：整篇 body 只切一次，循环内复用。
    // 原写法每个块都调 _blockSrcTextOf ⇒ 内部再 split 全文 ⇒ O(n²)（实测 4001 块 ≈715ms）。
    var _srcLines = (state.doc && state.doc.body) ? state.doc.body.split("\n") : [];
    for (var blockIdx = 0; blockIdx < doc.blocks.length; blockIdx++) {
      var block = doc.blocks[blockIdx];
      // 行区间只认 parser 落盘值；缺字段（理论上不该有）⇒ 跳过并如实计数，不猜
      if (!(block.srcLine > 0) || !(block.srcLineEnd >= block.srcLine)) continue;
      var el = byIdx.get(String(blockIdx)) || null;
      target.upsert({
        kind: block.type,
        srcLineStart: block.srcLine,
        srcLineEnd: block.srcLineEnd,
        blockSrcText: _blockSrcTextOf(block, _srcLines),
        domEl: el,
      });
      mapped++;
    }
    target.commit();

    // 兼容投影只在投射主实例时更新（临时实例不得动 _blockLineMap —— 否则预加载会篡改当前文档的映射）
    if (target === BI) {
      _blockLineMap = BI.blocks().map(function (h) {
        return { startLine: h.srcLineStart - 1, endLine: h.srcLineEnd - 1 };   // 兼容投影保持 0-based 旧口径
      });
    }
    log("STAMP", "mapped " + mapped + "/" + doc.blocks.length + " blocks ⇒ BlockIndex (" + (reset ? "reset" : "incremental") + (target === BI ? "" : "·temp") + ")");
  }

  /** 取一个块的源码文本（供 BlockIndex 派生稳定 id；纯函数、不读 DOM）。 */
  function _blockSrcTextOf(block, preSplitLines) {
    try {
      // 2026-10-22 性能修复（B1）：允许调用方预切好行数组。
      // 原先每块都 split 整篇 body ⇒ 4001 块 × 5879 行 = O(n²)，实测 ≈715ms。
      var lines = preSplitLines || (state.doc && state.doc.body ? state.doc.body.split("\n") : []);
      var out = [];
      for (var i = block.srcLine - 1; i <= block.srcLineEnd - 1 && i < lines.length; i++) out.push(lines[i]);
      return out.join("\n");
    } catch (e) { return ""; }
  }

  async function renderPreview(doc, options) {
    // 2026-09-25 AG97：窗口化（K4a）已整体回退 ⇒ 不再有"接管/跳过"这条链，本行原地保留以维持行号
    if (!doc || state.viewMode === "source") return;   // 2026-09-25 AG97：窗口化回退后，此行就是渲染侧唯一的入口闸门
    if (_renderingPreview) {
      // 上次全量渲染未完成（含 await MathJax/Mermaid 挂起窗口）：
      // 直接跳过会让"源码已更新但预览不刷新"（如预览区连续 Enter 拆行）。
      // 置 pending，当前渲染完成后自动补一次渲染最新文档。
      _renderPending = true;
      // 本次被排队：上一轮渲染完成后会自动补渲一次最新文档（见本函数尾部 `_renderPending`）
      log("render", "skip: already rendering → queue pending re-render");
      return;
    }
    _renderingPreview = true;
    const incremental = options?.incremental;
    const afterSync = options?.afterSync; if (!incremental && _previewCacheRestore(doc)) { _renderingPreview = false; return; } // 2026-09-23 性能：命中预览 DOM 缓存 ⇒ 直接搬回，跳过 parse/render/插 DOM/stamp/MathJax（见文件末尾「预览 DOM 缓存 + 后台预渲染」块）
    if (window.MemoriaMarkdownPreview?.setCurrentFileDir && state.currentPath) {
      const parts = state.currentPath.replace(/\\/g, "/").split("/");
      const dir = parts.length > 1 ? parts.slice(0, -1).join("/") + "/" : "";
      log("render", "currentFileDir=" + (dir || "(root)") + "  currentPath=" + state.currentPath);
      MemoriaMarkdownPreview.setCurrentFileDir(dir);
    }
    clearGraphLinkHighlight();
    const preview = $("#preview");
    hidePreviewStatus();
    if (!P || !M || !_rcRenderer()) {
      preview.innerHTML = '<p class="-preview-loading">' + T("preview.loadNotReady") + '</p>';
      _renderingPreview = false;
      return;
    }
    const token = ++state.previewToken;   // 2026-09-25 AG97：窗口化回退 ⇒ 清屏前不再需要"把视口顶部行交给窗口"
    // 2026-10-22 task-65：**换文档 / 整篇重渲**才提升调度 epoch（滚动不 bump）⇒
    //   排队中的惰性物化/排版作业执行前陈旧丢弃；并清空两条队列，避免"作业被丢、队列留孤儿"。
    //   `incremental: true`（同文档增量重渲）不 bump：job 仍属当前文档，误丢会造成漏物化/漏排版。
    //   同文档整篇重渲（视图切换 / 源→预览同步）只清队列、**不** bump：DOM 虽重建，但排队作业
    //   按块下标作用到新 DOM 仍是幂等的；bump 会误丢**同一文档**的其它 P2 派生作业（如 kp_panel 静默刷新）。
    if (!incremental) {
      var _lazyPrevPath = (_doc && _doc.path) || "";
      if (_lazyPrevPath !== ((doc && doc.path) || "")) _lazyPipelineReset("render:doc-change");
      else _lazyPipelineDropQueues();
    }
    if (!incremental) {   // 2026-09-25 AG97：窗口化回退 ⇒ 回到"全量重渲染前先插一句『渲染中』"的老行为（大文档编辑时会有一次高度塌陷/补齐，这是老路径固有代价）
      // 2026-10-22 task-70：换文档/整篇重渲前清掉旧 DOM 内的 MathJax MathItem，
      //   否则旧文档的 `mjx-container` 会被 `document.math` 永久钉住（打开新文档后仍残留）。
      _clearMathJaxWithin(preview);
      preview.innerHTML = '<p class="-preview-loading">' + T("preview.rendering") + '</p>';
    }
    preview.contentEditable = (window.MemoriaEditHandler && MemoriaEditHandler.editMode) ? "true" : "false";
    try {
      const t0 = performance.now();
      let body = doc.preview_body || doc.body || "";

      // 1. 数学标准化 + 本地图片路径重写（在源码层）
      // 注意：markdown-preview 是可选模块（可能未加载），必须经 window. 访问，
      // 直接裸读会在其缺失时抛 ReferenceError 导致整个预览失败
      const MP0 = window.MemoriaMarkdownPreview;
      body = MP0 && typeof MP0.normalizeBody === "function" ? MP0.normalizeBody(body) : body;
      body = rewriteMdImagePaths(body);

      // 2. AST 解析
      _doc = P.parse(body);
      M.setDoc(_doc);

      // 3. AST → DOM 渲染（P6a：切换为 render-core；**不再调用 legacy `R.render`**）
      //    render-core 与本函数既有管线同形：返回 `.-preview-content` 容器，块元素与 `_doc.blocks` 一一对应；
      //    行号/块身份仍由下面的 `stampBlockLines` 经 BlockIndex 写入（唯一写点不变）。
      // 2026-10-22 阶段0：透传 `blockEls` 省掉 `stampBlockLines` 内部全篇查询（见下）。
      // 2026-10-22 阶段1a：**惰性物化** —— 不再一次性建全文 4001 块，而是先建全文**占位**（O(块数)纯属性+高度估值），
      //   再同步物化"视口 ×2 高度"的块。其余块滚动靠近时物化（1b）。
      //   首屏之外的全篇 DOM 只以占位存在 ⇒ 浏览器不再为全文做 style/layout（实测这是打开 2.9s 的主因）。
      const _rc = _rcRenderer();
      const lazyOn = _lazyMaterializeEnabled(_doc);
      let _rendered, content;
      if (lazyOn) {
        content = _buildLazyPreview(_doc, preview);
        _rendered = { container: content, blockEls: _lazyBlockEls };
        _setupLazyScrollMaterialization(preview);   // 2026-10-22 1b：滚动追加物化
      } else {
        _teardownLazyScrollMaterialization();       // 非惰性路径 ⇒ 拆掉（若之前开过）
        _rendered = _rc.renderDocument(_doc);
        content = _rendered.container;
        preview.innerHTML = "";
        preview.appendChild(content);
        // 2026-10-22：明确记录"走了全量路径"，便于回归分辨大/小文档两种分支
        log("lazy", "lazy materialize OFF (full render): blocks=" + _doc.blocks.length + " threshold=" + LAZY_MIN_BLOCKS + " hook=" + (typeof window.__MEMORIA_LAZY === "boolean" ? String(window.__MEMORIA_LAZY) : "unset"));
      }
      // 3a. 代码块语法高亮（P6a 补丁：render-core 本片不做 token；复用 MemoriaCodeHighlight，
      //     与 legacy renderer.js:105-106 同源；必须早于 mermaid 替换 pre）
      _applyCodeHighlightToPreview(preview);

      // 3b. 构建 block→源行映射（整篇路径 ⇒ reset：清空旧索引，行区间与 id 全部按这份 AST 重建）
      // 2026-10-22 阶段1a：惰性物化时走 `querySelectorAll` 分支（占位块也在 DOM 里、带 data--block-index，
      //   所以 `blockEls` 无法复用 —— 传给 stampBlockLines 的会是占位元素，而非 renderDocument 的产物）。
      stampBlockLines(preview, _doc, { reset: true, blockEls: lazyOn ? undefined : _rendered.blockEls });
      _domBlockSig = _doc.blocks.map(_previewBlockSig);   // 2026-09-25 AG100：差分基准（纯 AST，不读 DOM，惰性物化不影响）

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
        if (MP.renderMermaidBlocks) { try { await MP.renderMermaidBlocks(preview); } catch (e) { log("render", "Mermaid: " + e.message); } }   // 2026-09-25 AG97：窗口化回退 ⇒ 这里回到"整篇逐块 await 渲染"（真机曾测到 27 s / 59 s，是本仓最大的单点重活；属于"渲染架构"要重做的清单，见 docs/design/preview-render-pipeline.md §3.7）
        if (MP.attachImageLightbox) { try { MP.attachImageLightbox(preview); } catch (e) { log("render", "Lightbox: " + e.message); } }
      }
      // 6.5 等 MathJax 真正就绪再排版（typesetPromise 在 startup 完成后才存在，
      //    加载慢时直接调用会被空值守卫跳过，导致公式一直以 $…$ 源码显示）
      if (window.MathJax?.startup?.promise) {
        try { await MathJax.startup.promise; } catch (e) { log("render", "MathJax startup: " + e.message); }
      }
      if (window.MathJax?.typesetPromise) {   // 2026-09-25 AG99：**回旧口径** —— 紧贴渲染末尾**排队**（`queuePreviewMathTypeset` 本身不是 await：实测 2.0–2.2 s 转后台 ⇒ 文件/编辑器/KP 立刻可用，公式"晚一拍"升级为渲染态是既有取舍）；AG73 那次"挪到两帧之后"是窗口化时期为"第一帧先出来"加的，回退窗口化后一并撤掉
        if (lazyOn) log("lazy", "typeset: mathEls=" + preview.querySelectorAll(".-math, .-math-block").length + " mjx=" + preview.querySelectorAll("mjx-container").length + " blocks=" + preview.querySelectorAll(".-src-block").length + " ph=" + preview.querySelectorAll(".-pv-placeholder").length);   // 2026-10-22 1a 诊断：定位惰性模式下 mjx=0 的根因
        const _orgC = _switchAbs; const _mp = queuePreviewMathTypeset(preview, token); _markAsyncAfter("mathjax", _mp, _orgC); _mp.then(function () { if (token === state.previewToken) _tagInlineMathContainers(preview, _doc); });   // 排版跑完的耗时读数（`切页签异步` 那行）+ 补一次行内公式标记
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
      _tagInlineMathContainers(preview, _doc); if (state._mathPending) state._mathPending.then(function () { if (token === state.previewToken) _tagInlineMathContainers(preview, _doc); }); // 2026-09-23 性能：MathJax 现在是后台跑的 ⇒ 排版完成后再补一次标记（`token` 守卫：只给"仍是最新一轮"的预览打）

      if (token !== state.previewToken) { _renderingPreview = false; return; }
      showPreviewReport({ ok: true });
      showLinkAuditPreviewHint(doc);
    } catch (e) {
      if (token !== state.previewToken) { _renderingPreview = false; return; }
      preview.innerHTML = '<p class="-preview-loading">' + T("preview.renderFail", { e: esc(String(e)) }) + '</p>';
      showPreviewReport({ ok: false, messages: [String(e)] });
    }
    _renderingPreview = false;
    // 渲染期间若有请求被重入保护跳过：补渲染一次最新文档，避免预览停留在旧内容
    if (_renderPending) {
      _renderPending = false;
      log("render", "re-run queued render");
      renderPreview(state.doc);
      return; // 新一轮渲染完成时会再次走本收尾并通知 _renderSettledWaiters
    }
    _notifyRenderSettled(); _preloadPruneStale(); _preloadSchedule(); _markPreviewDomCurrent(doc); _markPhase("postRender"); if (window.requestAnimationFrame) { const _o = _switchAbs; window.requestAnimationFrame(function () { _markAsync("frame1", _o); window.requestAnimationFrame(function () { _markAsync("paint", _o); }); }); } // 2026-09-23 性能：渲染收尾 ⇒ 登记「可缓存」指纹并排一次后台预渲染；2026-09-24：**先**按新候选集清掉过期的投机预渲染（避免滞留），**再**排新的；2026-09-24 读数：**冷渲染**这一路原本没有 `frame1`/`paint`（它们只打在那条"命中恢复"里）⇒ 一旦未命中，读数就成了瞎的（真机：`画面 — ms`、`render 1837` 无从归因）⇒ 这里补同款双 rAF（2026-09-25 AG97：窗口化回退 ⇒ 收尾不再有 `attach`）
  }

  /**
   * 标记行内公式的 mjx-container 元素
   * MathJax typeset 后 .-math span 可能被替换，导致 dblclick 无法定位。
   * 此函数遍历 AST 中所有 MATH_INLINE 节点，按 block → 顺序匹配 DOM 中的 mjx-container，
   * 打上 data--inline-math="true" 和 data-formula 属性。
   */
  function _tagInlineMathContainers(preview, doc) {
    if (!doc || !doc.blocks) return;
    var _nonEdTypes = { code_block: 1, math_block: 1, mermaid: 1, table: 1, frontmatter: 1 }; var byIdx = new Map(); preview.querySelectorAll(".-src-block[data--block-index]").forEach(function (el) { byIdx.set(el.getAttribute("data--block-index"), el); }); // 2026-09-23 性能：一次建索引（原为逐块全 DOM querySelector，3206 块时很贵）

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
      var blockEl = byIdx.get(String(bi));
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
    el.innerHTML = '<span>⚠ ' + esc(T("preview.linkAuditHint", { n })) + '</span>';
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
        state.currentPath || T("app.status.ready"),
        T("preview.okDetail", {
          rendered: report.mathRendered,
          expected: report.mathExpected,
        })
      );
      return;
    }
    el.classList.remove("hidden");
    el.classList.add("warn");
    const parts = report.messages?.length
      ? report.messages
      : [T("preview.incomplete")];
    el.innerHTML =
      '<span>⚠ ' +
      esc(T("preview.selfcheck", { parts: parts.join("；") })) +
      "</span>" +
      (report.mathErrors?.length
        ? `<details><summary>${esc(T("preview.math.texError"))}</summary><pre>${esc(report.mathErrors.join("\n"))}</pre></details>`
        : "");
    setStatus(
      state.currentPath || T("preview.brief"),
      T("preview.failDetail", {
        rendered: report.mathRendered,
        expected: report.mathExpected,
      })
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
      if (el) el.innerHTML = '<div class="empty">' + T("app.kpListSelectFile") + '</div>';
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
      el.innerHTML = '<div class="empty">' + T("app.kpListNoKp") + '</div>';
      return;
    }
    if (!kps.length) {
      el.innerHTML =
        '<div class="empty">' +
        T("app.kpListOnlyProposals", { n: proposals.length }) +
        '<br><span class="-muted">' +
        T("app.kpListOnlyProposalsHint") +
        "</span></div>";
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
        const tags = (Array.isArray(kp.tags) ? kp.tags : [])
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
    return { text: T("cfg.kpRange.unset"), ok: false };
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
            <span class="-muted">${esc(T("cfg.m4.sameFileNote"))}</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>${esc(T("cfg.m4.mergeBtn"))}</button>
          </div>
          <div class="-suggest-item -suggest-placeholder">
            <span class="-suggest-score">72%</span>
            <span class="-suggest-label">q-learning</span>
            <span class="-muted">${esc(T("cfg.m4.crossFileNote", { file: "q-learning.md" }))}</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>${esc(T("cfg.m4.citeBtn"))}</button>
          </div>`
        : `<div class="-suggest-item -suggest-placeholder">
            <span class="-suggest-score">91%</span>
            <span class="-suggest-label">[[q-learning|Q-learning]]</span>
            <span class="-muted">${esc(T("cfg.m4.bodyUnboundNote", { line: 42 }))}</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>${esc(T("cfg.m4.routeBtn"))}</button>
          </div>`;
    const title =
      kind === "kp" ? T("cfg.m4.mergeTitle") : T("cfg.m4.linkTitle");
    const hint =
      kind === "kp" ? T("cfg.m4.mergeHint") : T("cfg.m4.linkHint");
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
      { id: "kp", label: T("cfg.tab.kp"), count: counts.kp },
      { id: "links", label: T("cfg.tab.links"), count: counts.links },
      { id: "pending", label: T("cfg.tab.pending"), count: counts.pending },
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
      <button type="button" class="-btn primary -btn--sm" data-config-new-kp>${esc(T("cfg.kpTab.newKp"))}</button>
      <span class="-muted">${esc(T("cfg.kpTab.newKpHint"))}</span>
    </div>`;
    if (!confirmedKps.length) {
      html += `<p class="-muted">${esc(T("cfg.kpTab.empty"))}</p>`;
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
              <button type="button" class="-btn primary -btn--sm" data-kp-config="${esc(kp.id)}">${esc(T("cfg.kpTab.config"))}</button>
              <button type="button" class="-btn danger -btn--sm" data-kp-delete="${esc(kp.id)}" title="${esc(T("cfg.kpTab.deleteTitle"))}">${esc(T("common.delete"))}</button>
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
      parts.push(`<span class="-link-audit-bad" title="${esc(T("cfg.audit.missingTitle"))}">${esc(T("cfg.audit.missingLabel"))}</span>`);
    } else if (entry.status === "stale_instance") {
      parts.push(`<span class="-link-audit-bad" title="${esc(T("cfg.audit.staleTitle"))}">${esc(T("cfg.audit.staleLabel"))}</span>`);
    } else if (entry.status === "partial") {
      parts.push(`<span class="-link-audit-warn" title="${esc(T("cfg.audit.partialTitle"))}">${esc(T("cfg.audit.partialLabel"))}</span>`);
    }
    if (entry.targets_resolved === false) {
      parts.push(`<span class="-link-audit-warn" title="${esc(T("cfg.audit.unresolvedTitle"))}">${esc(T("cfg.audit.unresolvedLabel"))}</span>`);
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
      ? `<button type="button" class="-btn secondary -btn--sm" data-link-audit-fix="${esc(first.anchor_text)}">${esc(T("cfg.audit.openFirst"))}</button>`
      : "";
    return `<div class="-link-audit-banner" role="alert">
      <strong>${esc(T("cfg.audit.bannerTitle"))}</strong>
      <span>${esc(T("cfg.audit.bannerBody", { n }))}</span>
      ${fixBtn}
    </div>`;
  }

  function defaultLinkSearchOptions() {
    return { fuzzy_whitespace: true, fuzzy_suggest: true, case_insensitive: false };
  }

  function renderLinkSearchOptionsHtml(prefix, options) {
    const o = { ...defaultLinkSearchOptions(), ...(options || {}) };
    return `<div class="-link-search-options" data-search-options-root="${prefix}">
      <label class="-link-search-opt" title="${esc(T("cfg.search.ignoreSpaceTitle"))}">
        <input type="checkbox" data-search-opt="fuzzy_whitespace" ${o.fuzzy_whitespace ? "checked" : ""} />
        ${esc(T("cfg.search.ignoreSpace"))}
      </label>
      <label class="-link-search-opt" title="${esc(T("cfg.search.suggestTitle"))}">
        <input type="checkbox" data-search-opt="fuzzy_suggest" ${o.fuzzy_suggest ? "checked" : ""} />
        ${esc(T("cfg.search.suggest"))}
      </label>
      <label class="-link-search-opt -link-search-opt-future" title="${esc(T("cfg.search.caseTitle"))}">
        <input type="checkbox" data-search-opt="case_insensitive" disabled ${o.case_insensitive ? "checked" : ""} />
        ${esc(T("cfg.search.case"))}
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
        ? `<p class="-muted -link-match-empty">${esc(T("cfg.match.needInput"))}</p>`
        : "";
    }
    if (m.loading) {
      return `<p class="-muted -link-match-empty">${esc(T("cfg.match.scanning"))}</p>`;
    }

    const anchor = m.anchorText;
    const attached = m.matches.filter((x) => x.attached && !x.excluded).length;
    const excluded = m.matches.filter((x) => x.excluded).length;
    const hint = T("cfg.match.summary", {
      total: m.matches.length,
      attached,
      excluded,
      selected: m.selected.size,
    });
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
          ? T("cfg.match.locateBlocked", {
              reason: row.block_reason || T("cfg.match.blockedReason"),
            })
          : row.is_substring
          ? T("cfg.match.locateSubstring")
          : row.excluded
            ? T("cfg.match.locateExcluded")
            : T("cfg.match.locateRow");
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
        ? `<button type="button" class="-icon-btn" id="config-link-match-close" title="${esc(T("cfg.match.collapse"))}">×</button>`
        : "";

    let footer = "";
    if (variant === "config") {
      footer = `<div class="-config-link-match-footer -btn-bar">
        <button type="button" class="-btn secondary" id="config-link-match-cancel">${esc(T("common.cancel"))}</button>
        <button type="button" class="-btn primary" id="config-link-match-confirm" ${m.selected.size ? "" : "disabled"}>${esc(T("cfg.match.confirmWrap"))}</button>
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
    const allBtnLabel = allSelected ? T("cfg.match.clearAll") : T("cfg.match.selectAll");

    return `<div id="${panelId}" class="${panelCls}">
      <div class="-link-match-panel-header">
        <span class="-link-match-panel-title">${esc(T("cfg.match.panelTitle", { anchor: m.anchorText }))}</span>
        <span class="-muted -link-match-panel-hint">${esc(hint)}</span>
        ${closeBtn}
      </div>
      ${searchOptsHtml}
      <div class="-link-match-toolbar -btn-bar -btn-bar--start">
        <button type="button" class="-btn secondary -btn--sm" id="${prefix}-all">${esc(allBtnLabel)}</button>
        <button type="button" class="-btn secondary -btn--sm" id="${prefix}-plain">${esc(T("cfg.match.onlyUnwrapped"))}</button>
      </div>
      <div class="-link-match-list">${rows || `<p class="-muted">${esc(T("cfg.match.noMatch"))}</p>`}</div>
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
      setStatus(T("cfg.match.scanFail"), String(e.message || e));
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
      <button type="button" class="-btn primary -btn--sm" id="config-new-link">${esc(T("cfg.linktab.newLink"))}</button>
      <span class="-muted">${esc(T("cfg.linktab.newLinkHint"))}</span>
    </div>`;
    if (!fileLinks.length) {
      html += `<p class="-muted">${esc(T("cfg.linktab.empty"))}</p>`;
    } else {
      html += fileLinks
        .map((link) => {
          const anchor = link.anchor_text || "";
          const targets = (link.targets || []).join(", ");
          const pool =
            (link.pool || []).length > (link.targets || []).length
              ? T("cfg.linktab.poolNote", { n: link.pool.length })
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
              ? T("cfg.linktab.attachedNote", { n: auditEntry.preview_attached_count })
              : auditEntry && auditEntry.body_wrapped_count > 0
                ? T("cfg.linktab.bodyWrappedNote", { n: auditEntry.body_wrapped_count })
                : "";
          const matchPanelHtml =
            state.configLinkMatch?.anchorText === anchor
              ? renderConfigLinkMatchPanelHtml()
              : "";
          return `<div class="-config-link-block">
          <div class="-config-item -config-link-item${hl}" data-link-anchor="${esc(anchor)}" role="button" tabindex="0" title="${esc(T("cfg.linktab.locateTitle"))}">
            <div class="-config-item-main">
              <code class="-config-anchor">${esc(anchor)}</code>
              ${badge}
              <span class="-muted">→ ${esc(targets || T("cfg.linktab.unbound"))}${esc(pool)}${esc(instHint)}</span>
              ${auditEntry?.issues?.length ? `<span class="-link-audit-detail" title="${esc(auditEntry.issues.join("；"))}">${esc(auditEntry.issues[0])}</span>` : ""}
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn secondary -btn--sm" data-link-match="${esc(anchor)}" title="${esc(T("cfg.linktab.matchBtnTitle"))}">${esc(T("cfg.linktab.matchBtn"))}</button>
              <button type="button" class="-btn primary -btn--sm" data-link-edit="${esc(anchor)}">${esc(T("cfg.linktab.editBtn"))}</button>
              <button type="button" class="-btn danger -btn--sm" data-link-delete="${esc(anchor)}" title="${esc(T("cfg.linktab.deleteTitle"))}">${esc(T("common.delete"))}</button>
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
      <button type="button" class="-btn primary -btn--sm" data-config-confirm-all>${esc(T("cfg.pending.confirmAll"))}</button>
      <button type="button" class="-btn secondary -btn--sm" data-config-sync-pending>${esc(T("cfg.pending.refreshBtn"))}</button>
      ${kbTotal != null ? `<span class="-muted">${esc(T("cfg.pending.kbTotal", { n: kbTotal }))}</span>` : ""}
    </div>`;
    if (!counts.pending) {
      html += `<p class="-muted">${esc(T("cfg.pending.empty"))}</p>`;
      html += renderConfigPendingSuggestBlocks();
      return html;
    }
    if (pendingHeading.length) {
      html += `<div class="-config-kp-group"><div class="-config-kp-group-title">${esc(T("cfg.pending.grpHeading", { n: pendingHeading.length }))}</div>`;
      html += pendingHeading
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = headingP.indexOf(p);
          return `<div class="-config-item">
            <div class="-config-item-main">
              <span class="-config-tag">${esc(T("cfg.pending.tagHeading"))}</span>
              <span class="-config-kp-name">${esc(p.name)}</span>
              <span class="-muted">${lines}</span>
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn secondary -btn--sm" data-confirm-heading="${idx}">${esc(T("cfg.pending.confirmDirect"))}</button>
              <button type="button" class="-btn primary -btn--sm" data-heading-proposal="${idx}">${esc(T("cfg.pending.confirmConfig"))}</button>
              ${p.pending_id ? `<button type="button" class="-btn secondary -btn--sm" data-dismiss-pending="${esc(p.pending_id)}">${esc(T("cfg.pending.dismiss"))}</button>` : ""}
            </div>
          </div>`;
        })
        .join("");
      html += `</div>`;
    }
    if (pendingMention.length) {
      html += `<div class="-config-kp-group"><div class="-config-kp-group-title">${esc(T("cfg.pending.grpMention", { n: pendingMention.length }))}</div>`;
      html += pendingMention
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = mentionP.indexOf(p);
          return `<div class="-config-item">
            <div class="-config-item-main">
              <span class="-config-tag">${esc(T("cfg.pending.tagMention"))}</span>
              <span class="-config-kp-name">${esc(p.name)}</span>
              <span class="-muted">${lines}</span>
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn secondary -btn--sm" data-confirm-mention="${idx}">${esc(T("cfg.pending.confirmDirect"))}</button>
              <button type="button" class="-btn primary -btn--sm" data-mention-proposal="${idx}">${esc(T("cfg.pending.confirmConfig"))}</button>
              ${p.pending_id ? `<button type="button" class="-btn secondary -btn--sm" data-dismiss-pending="${esc(p.pending_id)}">${esc(T("cfg.pending.dismiss"))}</button>` : ""}
            </div>
          </div>`;
        })
        .join("");
      html += `</div>`;
    }
    if (pendingDefinition.length) {
      html += `<div class="-config-kp-group"><div class="-config-kp-group-title">${esc(T("cfg.pending.grpDefinition", { n: pendingDefinition.length }))}</div>`;
      html += pendingDefinition
        .map((p) => {
          const r = p.range || {};
          const lines = `L${r.start?.line_hint || "?"}–${r.end?.line_hint || "?"}`;
          const idx = definitionP.indexOf(p);
          return `<div class="-config-item">
            <div class="-config-item-main">
              <span class="-config-tag">${esc(T("cfg.pending.tagDefinition"))}</span>
              <span class="-config-kp-name">${esc(p.name)}</span>
              <span class="-muted">${lines}</span>
            </div>
            <div class="-config-item-actions">
              <button type="button" class="-btn secondary -btn--sm" data-confirm-definition="${idx}">${esc(T("cfg.pending.confirmDirect"))}</button>
              <button type="button" class="-btn primary -btn--sm" data-definition-proposal="${idx}">${esc(T("cfg.pending.confirmConfig"))}</button>
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
    body.querySelectorAll("[data-confirm-heading]").forEach((btn) => {
      btn.addEventListener("click", () => {
        confirmKpFromProposal(headingP[+btn.dataset.confirmHeading]);
      });
    });
    body.querySelectorAll("[data-mention-proposal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = mentionP[+btn.dataset.mentionProposal];
        openKpModalFromProposal(p, { returnTo: "config" });
      });
    });
    body.querySelectorAll("[data-confirm-mention]").forEach((btn) => {
      btn.addEventListener("click", () => {
        confirmKpFromProposal(mentionP[+btn.dataset.confirmMention]);
      });
    });
    body.querySelectorAll("[data-definition-proposal]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = definitionP[+btn.dataset.definitionProposal];
        openKpModalFromProposal(p, { returnTo: "config" });
      });
    });
    body.querySelectorAll("[data-confirm-definition]").forEach((btn) => {
      btn.addEventListener("click", () => {
        confirmKpFromProposal(definitionP[+btn.dataset.confirmDefinition]);
      });
    });

    body.querySelector("[data-config-confirm-all]")?.addEventListener("click", () => {
      confirmAllPending();
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

    $("#config-title").textContent = T("cfg.config.title", { name: basename(doc.path) });

    let html = `<p class="-config-summary">${esc(
      T("cfg.config.summary", {
        sidecar: hasSidecar ? T("cfg.config.metaDone") : T("cfg.config.metaNone"),
        kp: counts.kp,
        links: counts.links,
      })
    )}</p>`;
    if (validation.errors?.length) {
      html += `<p class="-config-error">${esc(T("cfg.config.errors", { msg: validation.errors.join("；") }))}</p>`;
    }
    if (validation.warnings?.length) {
      html += `<p class="-config-warn">${esc(T("cfg.config.warnings", { msg: validation.warnings.join("；") }))}</p>`;
    }
    if (tab === "links" && doc.link_audit && !doc.link_audit.ok) {
      const n = doc.link_audit.summary?.issue_count || 0;
      if (n) {
        html += `<p class="-config-warn">${esc(T("cfg.config.linkWarn", { n }))}</p>`;
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
        setStatusError(T("cfg.pending.ignoreFail"), res.message);
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
      setStatus(T("cfg.pending.ignored"));
    } catch (e) {
      setStatusError(T("cfg.pending.ignoreFail"), e.message);
    }
  }

  async function syncPendingFromConfig() {
    try {
      setStatus(T("cfg.pending.refreshing"));
      const res = await call("sync_pending");
      if (res.status !== "ok") {
        setStatusError(T("cfg.pending.refreshFail"), res.message);
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
      setStatus(T("cfg.pending.refreshed"), T("cfg.pending.items", { n: res.pending_count ?? 0 }));
    } catch (e) {
      setStatusError(T("cfg.pending.refreshFail"), e.message);
    }
  }

  function closeConfigModal() {
    closeConfigLinkMatch();
    $("#config-modal").classList.add("hidden");
  }

  function renderKpModalTabs(activeTab) {
    const tabs = [
      { id: "range", label: T("cfg.panel.tabs.range") },
      { id: "identity", label: T("cfg.panel.tabs.identity") },
      { id: "tags", label: T("cfg.panel.tabs.tags") },
      { id: "edges", label: T("cfg.panel.tabs.edges") },
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
      <label>${esc(T("cfg.range.start"))} <input type="number" class="-line-input" data-range-start min="1" max="${total || ""}" value="${a.startLine}"></label>
      <label>${esc(T("cfg.range.end"))} <input type="number" class="-line-input" data-range-end min="1" max="${total || ""}" value="${a.endLine}"></label>
      <span class="-muted">${esc(T("cfg.range.wheelNote"))}${total ? esc(T("cfg.range.totalNote", { total })) : ""}</span>
    </div>`;
    if (a.startCandidates.length > 1) {
      html += `<p class="-range-candidates-label"><strong>${esc(T("cfg.range.startCand"))}</strong></p>`;
      html += `<div class="-range-candidates">${renderCandidates("start", a.startCandidates)}</div>`;
    }
    if (a.endCandidates.length > 1) {
      html += `<p class="-range-candidates-label"><strong>${esc(T("cfg.range.endCand"))}</strong></p>`;
      html += `<div class="-range-candidates">${renderCandidates("end", a.endCandidates)}</div>`;
    }
    html += `<div data-range-preview class="-assist-preview-wrap"></div>`;
    html += `<p class="-muted">${esc(T("cfg.range.updateNote"))}</p>`;
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
      saveBtn.textContent = T("common.ok");
      saveBtn.title = T("common.ok");
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
      ? (panel.name
        ? T("cfg.kpModal.createTitleNamed", { name: panel.name })
        : T("cfg.kpModal.createTitlePlain"))
      : T("cfg.kpModal.editTitle", { name: kp.name || kp.id });
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
        <label class="-link-field">${esc(T("cfg.kpIdent.nameLabel"))} <input type="text" id="kp-field-name" value="${esc(nameVal)}" autocomplete="off"></label>
        <p class="-config-hint">${isCreate ? esc(T("cfg.kpIdent.createHint")) : esc(T("cfg.kpIdent.editHint"))}</p>
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
        <label class="-link-field">${esc(T("cfg.kpIdent.descLabel"))}
          <textarea id="kp-desc-input" rows="3" placeholder="${esc(T("cfg.kpIdent.descPlaceholder"))}">${esc(desc)}</textarea>
        </label>
        ${renderKpDescCandEditorHtml(panel, kp)}
        <div class="-kp-tags-zone-toolbar">
          <button type="button" id="kp-sync-aux" class="-btn secondary -btn--sm">${esc(T("cfg.kpIdent.syncAux"))}</button>
          <button type="button" id="kp-suggest-desc" class="-btn secondary -btn--sm">${esc(T("cfg.kpIdent.suggestDesc"))}</button>
        </div>
        <p class="-config-hint">${isCreate ? esc(T("cfg.kpIdent.descCreateHint")) : esc(T("cfg.kpIdent.descEditHint"))}</p>
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
    const labels = {
      contain: T("cfg.edge.typeContain"),
      reference: T("cfg.edge.typeReference"),
      extend: T("cfg.edge.typeExtend"),
    };
    const color = colors[type] || "#999";
    const label = labels[type] || type;
    return `<span class="-edge-type-badge" style="background:${color};color:#fff">${esc(label)}</span>`;
  }

  function edgeOriginLabel(edge) {
    if (edge.origin === "link") return T("cfg.edge.originLink");
    if (edge.origin === "range") return T("cfg.edge.originRange");
    if (edge.origin === "sidecar_edge") return T("cfg.edge.originManual");
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
    html += `<h4 class="-edge-section-title">${esc(T("cfg.edge.outTitle"))} <span class="-tab-count">${outgoing.length}</span></h4>`;
    if (outgoing.length) {
      html += `<div class="-edge-list">`;
      for (const e of outgoing) {
        html += `<div class="-edge-item" data-edge-type="${esc(e.type)}" data-edge-source="${esc(e.source_id)}" data-edge-target="${esc(e.target_id)}" data-edge-origin="${esc(e.origin || "")}" ${e.anchor_text ? `data-edge-anchor="${esc(e.anchor_text)}"` : ""}>`;
        html += `<div class="-edge-main">`;
        html += edgeTypeBadgeHtml(e.type);
        html += `<span class="-edge-arrow">${esc(kpNameForId(e.source_id))} → ${esc(kpNameForId(e.target_id))}</span>`;
        html += `<span class="-edge-relevance">${e.relevance != null ? Number(e.relevance).toFixed(2) : "—"}</span>`;
        html += `<span class="-edge-origin">${esc(edgeOriginLabel(e))}</span>`;
        if (e.no_build) html += `<span class="-edge-no-build">${esc(T("cfg.edge.suppressed"))}</span>`;
        html += `</div>`;
        html += `<div class="-edge-actions">`;
        if (e.type === "contain" && e.no_build) {
          html += `<button type="button" class="-btn secondary -btn--sm -edge-btn-restore" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}">${esc(T("cfg.edge.restoreBtn"))}</button>`;
        } else if (e.type === "contain" && !e.no_build) {
          html += `<button type="button" class="-btn secondary -btn--sm -edge-btn-suppress" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}">${esc(T("cfg.edge.suppressBtn"))}</button>`;
        }
        if (e.origin === "sidecar_edge") {
          html += `<button type="button" class="-btn danger -btn--sm -edge-btn-delete" data-source="${esc(e.source_id)}" data-target="${esc(e.target_id)}" data-type="${esc(e.type)}">${esc(T("common.delete"))}</button>`;
        }
        if (e.origin === "link" && e.anchor_text) {
          html += `<button type="button" class="-btn secondary -btn--sm -edge-btn-config-link" data-anchor="${esc(e.anchor_text)}">${esc(T("cfg.edge.configLinkBtn"))}</button>`;
        }
        html += `</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    } else {
      html += `<p class="-muted">${esc(T("cfg.edge.noOut"))}</p>`;
    }
    html += `</div>`;

    // Incoming edges section
    html += `<div class="-edge-section">`;
    html += `<h4 class="-edge-section-title">${esc(T("cfg.edge.inTitle"))} <span class="-tab-count">${incoming.length}</span></h4>`;
    if (incoming.length) {
      html += `<div class="-edge-list">`;
      for (const e of incoming) {
        html += `<div class="-edge-item" data-edge-type="${esc(e.type)}" data-edge-source="${esc(e.source_id)}" data-edge-target="${esc(e.target_id)}" data-edge-origin="${esc(e.origin || "")}">`;
        html += `<div class="-edge-main">`;
        html += edgeTypeBadgeHtml(e.type);
        html += `<span class="-edge-arrow">${esc(kpNameForId(e.source_id))} → ${esc(kpNameForId(e.target_id))}</span>`;
        html += `<span class="-edge-relevance">${e.relevance != null ? Number(e.relevance).toFixed(2) : "—"}</span>`;
        html += `<span class="-edge-origin">${esc(edgeOriginLabel(e))}</span>`;
        if (e.no_build) html += `<span class="-edge-no-build">${esc(T("cfg.edge.suppressed"))}</span>`;
        html += `</div>`;
        html += `</div>`;
      }
      html += `</div>`;
    } else {
      html += `<p class="-muted">${esc(T("cfg.edge.inScopeNote"))}</p>`;
    }
    html += `</div>`;

    // Create new edge form
    html += `<div class="-edge-section -edge-create-form">`;
    html += `<h4 class="-edge-section-title">${esc(T("cfg.edge.createTitle"))}</h4>`;
    html += `<div class="-edge-create-fields">`;
    html += `<label class="-link-field">${esc(T("cfg.edge.targetKp"))} <input type="text" id="kp-edge-target" placeholder="${esc(T("cfg.edge.targetPlaceholder"))}" autocomplete="off" spellcheck="false"></label>`;
    html += `<label class="-link-field">${esc(T("cfg.edge.typeLabel"))} <select id="kp-edge-type"><option value="reference">${esc(T("cfg.edge.optReference"))}</option><option value="extend">${esc(T("cfg.edge.optExtend"))}</option></select></label>`;
    html += `<label class="-link-field">${esc(T("cfg.edge.relevanceLabel"))} <input type="range" id="kp-edge-relevance" min="0" max="1" step="0.05" value="0.7"><span id="kp-edge-relevance-val">0.70</span></label>`;
    html += `<button type="button" id="kp-edge-create-btn" class="-btn primary -btn--sm">${esc(T("cfg.edge.createBtn"))}</button>`;
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
        setStatus(T("cfg.edge.suppressInProg"));
        const res = await call("set_contain_no_build", state.currentPath, parentId, childId, true);
        if (res.status !== "ok") {
          setStatus(res.message || T("cfg.edge.opFailed"));
          return;
        }
        setStatus(T("cfg.edge.suppressedContain"));
        await reloadDocAndRefreshEdges(kp.id);
      });
    });

    // Restore contain edge (remove no_build)
    body.querySelectorAll(".-edge-btn-restore").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const parentId = btn.dataset.source;
        const childId = btn.dataset.target;
        if (!state.currentPath || !parentId || !childId) return;
        setStatus(T("cfg.edge.restoreInProg"));
        const res = await call("set_contain_no_build", state.currentPath, parentId, childId, false);
        if (res.status !== "ok") {
          setStatus(res.message || T("cfg.edge.opFailed"));
          return;
        }
        setStatus(T("cfg.edge.restoredContain"));
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
        if (!window.confirm(T("cfg.edge.confirmDelete", { src: sourceId, tgt: targetId, type: edgeType }))) return;
        setStatus(T("cfg.edge.deleteInProg"));
        const res = await call("delete_edge", state.currentPath, sourceId, targetId, edgeType);
        if (res.status !== "ok") {
          setStatus(res.message || T("cfg.edge.opFailed"));
          return;
        }
        setStatus(T("cfg.edge.deleted"));
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
          setStatusError(T("cfg.edge.needTargetId"));
          return;
        }
        if (!state.currentPath) return;
        setStatus(T("cfg.edge.createInProg"));
        const res = await call("create_edge", state.currentPath, kp.id, targetId, edgeType, relevance);
        if (res.status !== "ok") {
          setStatus(res.message || T("cfg.edge.createFail"));
          return;
        }
        setStatus(T("cfg.edge.created"));
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
    const dismiss = `<button type="button" class="-kp-tag-chip-btn" data-alias-dismiss="${esc(alias)}" title="${esc(T("cfg.chip.remove"))}">×</button>`;
    const kindCls =
      kind === "selected"
        ? "-kp-tag-pick--selected"
        : kind === "cand-user"
          ? "-kp-tag-pick--cand-user"
          : "-kp-tag-pick--cand-system";
    const title = kind === "selected" ? esc(T("cfg.chip.moveToCand")) : esc(T("cfg.chip.applyToSel"));
    return `<span class="-kp-tag-pick ${kindCls}" data-alias="${esc(alias)}" data-alias-kind="${kind === "selected" ? "selected" : "candidate"}" title="${title}">
      <span class="-kp-tag-chip-label">${esc(alias)}</span>
      <span class="-kp-tag-chip-actions">${dismiss}</span>
    </span>`;
  }

  function renderKpDescCandChip(text, source) {
    const kindCls = source === "user" ? "-kp-tag-pick--cand-user" : "-kp-tag-pick--cand-system";
    const short = text.length > 72 ? text.slice(0, 70) + "…" : text;
    return `<span class="-kp-tag-pick ${kindCls} -kp-desc-cand" data-desc-cand="${esc(text)}" title="${esc(T("cfg.chip.fillDesc"))}">
      <span class="-kp-tag-chip-label">${esc(short)}</span>
      <button type="button" class="-kp-tag-chip-btn" data-desc-dismiss="${esc(text)}" title="${esc(T("cfg.chip.remove"))}">×</button>
    </span>`;
  }

  function renderKpAliasEditorHtml(panel, kp) {
    const as = ensureKpAliasState(panel, kp);
    const selHtml = as.selected.length
      ? as.selected.map((a) => renderKpAliasChip(a, "selected")).join("")
      : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.aliasSelEmpty"))}</span>`;
    const candHtml = as.candidates.length
      ? as.candidates
          .map((c) =>
            renderKpAliasChip(c.alias, c.source === "user" ? "cand-user" : "cand-system")
          )
          .join("")
      : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.aliasCandEmpty"))}</span>`;
    return `<div class="-kp-tags-editor -kp-alias-editor" id="kp-alias-editor">
      <div class="-kp-tags-zone -kp-tags-zone--selected">
        <div class="-kp-tags-zone-head">${esc(T("cfg.kpTag.zoneAliasSel"))} <span class="-muted">${esc(T("cfg.kpTag.partSearchNote"))}</span></div>
        <div id="kp-alias-selected" class="-kp-tags-chips">${selHtml}</div>
      </div>
      <div class="-kp-tags-zone -kp-tags-zone--candidate">
        <div class="-kp-tags-zone-head">${esc(T("cfg.kpTag.zoneAliasCand"))}</div>
        <div class="-kp-tags-zone-toolbar">
          <div class="-kp-tag-create-row">
            <input type="text" id="kp-alias-new-input" placeholder="${esc(T("cfg.kpTag.aliasNewPlaceholder"))}" autocomplete="off" spellcheck="false" />
            <button type="button" id="kp-alias-add-btn" class="-btn secondary -btn--sm">${esc(T("cfg.kpTag.addCandBtn"))}</button>
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
      : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.descCandEmpty"))}</span>`;
    return `<div class="-kp-desc-cand-editor" id="kp-desc-cand-editor">
      <div class="-kp-tags-zone-head">${esc(T("cfg.kpTag.zoneDescCand"))} <span class="-muted">${esc(T("cfg.kpTag.fillDescNote"))}</span></div>
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
      : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.aliasSelEmpty"))}</span>`;
    if (cand) {
      cand.innerHTML = as.candidates.length
        ? as.candidates
            .map((c) =>
              renderKpAliasChip(c.alias, c.source === "user" ? "cand-user" : "cand-system")
            )
            .join("")
        : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.aliasCandEmpty"))}</span>`;
    }
  }

  function refreshKpDescCandEditorDom(panel, kp) {
    const root = $("#kp-desc-candidates");
    if (!panel?.draft?.descCandState || !root) return;
    const ds = panel.draft.descCandState;
    root.innerHTML = ds.candidates.length
      ? ds.candidates.map((c) => renderKpDescCandChip(c.text, c.source)).join("")
      : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.descCandEmpty"))}</span>`;
  }

  function renderKpTagChip(tag, kind, opts = {}) {
    const score =
      opts.score != null
        ? `<span class="-kp-tag-pick-score">${esc(String(Math.round(opts.score)))}</span>`
        : "";
    const dismiss = `<button type="button" class="-kp-tag-chip-btn" data-tag-dismiss="${esc(tag)}" title="${esc(T("cfg.chip.remove"))}">×</button>`;
    const kindCls =
      kind === "selected"
        ? "-kp-tag-pick--selected"
        : kind === "cand-user"
          ? "-kp-tag-pick--cand-user"
          : "-kp-tag-pick--cand-system";
    const title =
      kind === "selected" ? esc(T("cfg.chip.moveToCand")) : esc(T("cfg.chip.applyToSel"));
    return `<span class="-kp-tag-pick ${kindCls}" data-tag="${esc(tag)}" data-tag-kind="${kind === "selected" ? "selected" : "candidate"}" title="${title}">
      <span class="-kp-tag-chip-label">${esc(tag)}</span>${score}
      <span class="-kp-tag-chip-actions">${dismiss}</span>
    </span>`;
  }

  function renderKpTagsEditorHtml(panel, kp, isCreate) {
    const ts = ensureKpTagState(panel, kp);
    const selectedHtml = ts.selected.length
      ? ts.selected.map((t) => renderKpTagChip(t, "selected")).join("")
      : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.tagSelEmpty"))}</span>`;
    const candHtml = ts.candidates.length
      ? ts.candidates
          .map((c) =>
            renderKpTagChip(c.tag, c.source === "user" ? "cand-user" : "cand-system", {
              score: c.score,
            })
          )
          .join("")
      : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.tagCandEmpty"))}</span>`;
    return `<div class="-kp-tags-editor" id="kp-tags-editor">
      <div class="-kp-tags-zone -kp-tags-zone--selected">
        <div class="-kp-tags-zone-head">${esc(T("cfg.kpTag.zoneTagsSel"))} <span class="-muted">${esc(T("cfg.kpTag.tagsSelNote"))}</span></div>
        <div id="kp-tags-selected" class="-kp-tags-chips">${selectedHtml}</div>
      </div>
      <div class="-kp-tags-zone -kp-tags-zone--candidate">
        <div class="-kp-tags-zone-head">${esc(T("cfg.kpTag.zoneTagsCand"))} <span class="-muted">${esc(T("cfg.kpTag.tagsCandNote"))}</span></div>
        <div class="-kp-tags-zone-toolbar">
          <button type="button" id="kp-suggest-tags" class="-btn secondary -btn--sm">${esc(T("cfg.kpTag.sysSuggestBtn"))}</button>
          <div class="-kp-tag-create-row">
            <input type="text" id="kp-tag-new-input" placeholder="${esc(T("cfg.kpTag.tagNewPlaceholder"))}" autocomplete="off" spellcheck="false" />
            <button type="button" id="kp-tag-add-btn" class="-btn secondary -btn--sm">${esc(T("cfg.kpTag.addCandBtn"))}</button>
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
        : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.tagSelEmpty"))}</span>`;
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
        : `<span class="-muted -kp-tags-empty">${esc(T("cfg.kpTag.tagCandEmpty"))}</span>`;
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
        setStatus(res.message || T("cfg.aux.syncFail"));
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
      setStatus(added ? T("cfg.aux.merged", { n: added }) : T("cfg.aux.none"));
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
      if (!items.length) setStatus(T("cfg.aux.noTagSuggest"));
      else if (added) setStatus(T("cfg.aux.tagAdded", { n: added }));
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
        `<p class="-config-hint">${T("cfg.aux.mergeHint")}</p>` +
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

  // ---- [bench] 知识点创建链路 L2 插桩（?bench=1 或 DevTools 设 window.__bench=true 开启；默认关）----
  // kind: "modal"=创建弹窗保存链（终点 modal_closed）；"quick"=配置弹窗直接确认链（终点 ui_done）
  const __benchMarks = [];
  let __benchKind = null;
  function __benchActive() {
    return (
      typeof window !== "undefined" &&
      (window.__bench === true || /[?&]bench=1([&#]|$)/.test(location.search))
    );
  }
  function benchMark(label, kind) {
    if (!__benchActive()) return;
    if (label === "start") {
      __benchMarks.length = 0;
      __benchKind = kind || "quick";
    }
    __benchMarks.push({ label, t: performance.now() });
    console.log("[KP-BENCH-t]", label, "kind=" + __benchKind);
    if (label === "modal_closed") benchReport();
    else if (label === "ui_done" && __benchKind !== "modal") benchReport();
  }
  function benchReport() {
    if (!__benchMarks.length) return;
    const list = __benchMarks;
    const t0 = list[0].t;
    const phases = [];
    for (let i = 1; i < list.length; i++) {
      phases.push(list[i].label + "+" + (list[i].t - list[i - 1].t).toFixed(1) + "ms");
    }
    const rec = {
      kind: __benchKind,
      flow: list.map((x) => x.label).join(">"),
      total_ms: +((list[list.length - 1].t - t0)).toFixed(1),
      phases,
    };
    (window.__benchLog = window.__benchLog || []).push(rec);
    console.log("[KP-BENCH]", JSON.stringify(rec));
    __benchMarks.length = 0;
    __benchKind = null;
  }

  /** 直接确认待确认提议：不弹配置弹窗，用提议的 id/名称/范围直接创建知识点 */
  async function confirmKpFromProposal(proposal) {
    if (!proposal || !state.currentPath) return;
    const r = proposal.range || {};
    const start = r.start?.line_hint || 1;
    const end = Math.max(start, r.end?.line_hint || start);
    const total = state.doc?.lines?.length || 1;
    if (end > total) {
      setStatusError(T("cfg.confirm.cannot"), T("cfg.confirm.endOutOfRange", { end, total }));
      return;
    }
    const kpId = (proposal.concept_id || slugify(proposal.name || "")).trim();
    const kpName = (proposal.name || "").trim();
    if (!kpId) {
      setStatusError(T("cfg.confirm.cannot"), T("cfg.confirm.missingId"));
      return;
    }
    if (!kpName) {
      setStatusError(T("cfg.confirm.cannot"), T("cfg.confirm.missingName"));
      return;
    }
    try {
      benchMark("start", "quick");
      const check = await call("check_kp_id", kpId, state.currentPath);
      if (check.status !== "ok" || !check.available) {
        setStatusError(check.message || T("cfg.confirm.idTaken"), check.files?.join(", "));
        return;
      }
      benchMark("check_ok");
    } catch (e) {
      setStatusError(T("cfg.confirm.validateFail"), String(e.message || e));
      return;
    }
    setStatus(T("cfg.confirm.inProg"));
    const res = await call("confirm_kp_range", state.currentPath, kpId, kpName, start, end);
    if (res.status !== "ok") {
      setStatusError(kpErrText(res));
      return;
    }
    benchMark("rpc_ok");
    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    window.MemoriaFileTree?.render?.();
    await setViewMode(state.viewMode, { skipSave: true });
    await renderPreview(res);
    state.activeKpId = kpId;
    renderKpList(state.doc);
    // 改范围/创建：只标记范围（不滚动不闪烁），避免打断用户当前视线
    markRangeQuiet(start, end);
    benchMark("ui_done");
    setStatus(T("cfg.confirm.done"), T("cfg.confirm.doneDetail", { kpId, start, end }));
    try {
      await saveKpCreateMetadata(kpId);
    } catch (_) {
      /* optional */
    }
    try {
      await loadGraphData();
      applyGraphGroupLayout({ relayout: true });
    } catch (_) {
      /* optional */
    }
    if (!$("#config-modal").classList.contains("hidden")) {
      openConfigModal({ tab: "pending" });
    }
  }

  /** 全部确认：按顺序逐个用提议默认 id/名称/范围直接确认；冲突/异常项跳过并汇总 */
  async function confirmAllPending() {
    if (!state.currentPath || !state.doc) return;
    const confirmed = state.doc.knowledge_points || [];
    const all = [
      ...(state.doc.heading_proposals || []),
      ...(state.doc.mention_proposals || []),
      ...(state.doc.definition_proposals || []),
    ].filter((p) => !isKpCoveredByConfirmed(p, confirmed));
    if (!all.length) {
      setStatus(T("cfg.confirm.nonePending"));
      return;
    }
    if (!window.confirm(T("cfg.confirm.confirmAll", { n: all.length }))) {
      return;
    }
    const ok = [];
    const skipped = [];
    for (let i = 0; i < all.length; i++) {
      const p = all[i];
      setStatus(T("cfg.confirm.working", { cur: i + 1, total: all.length, name: p.name || p.concept_id || "" }));
      const r = p.range || {};
      const start = r.start?.line_hint || 1;
      const end = Math.max(start, r.end?.line_hint || start);
      const total = state.doc?.lines?.length || 1;
      const kpId = (p.concept_id || slugify(p.name || "")).trim();
      const kpName = (p.name || "").trim();
      if (!kpId || !kpName) {
        skipped.push(T("cfg.confirm.skNoId", { name: kpName || "?" }));
        continue;
      }
      if (end > total) {
        skipped.push(T("cfg.confirm.skRange", { name: kpName }));
        continue;
      }
      try {
        const check = await call("check_kp_id", kpId, state.currentPath);
        if (check.status !== "ok" || !check.available) {
          skipped.push(T("cfg.confirm.skIdTaken", { name: kpName }));
          continue;
        }
      } catch (e) {
        skipped.push(T("cfg.confirm.skValidate", { name: kpName, msg: e.message || e }));
        continue;
      }
      const res = await call("confirm_kp_range", state.currentPath, kpId, kpName, start, end);
      if (res.status !== "ok") {
        skipped.push(T("cfg.confirm.skWrite", { name: kpName, msg: kpErrText(res) }));
        continue;
      }
      state.doc = res;
      ok.push(kpName);
    }
    renderEditor(state.doc);
    renderKpList(state.doc);
    window.MemoriaFileTree?.render?.();
    await setViewMode(state.viewMode, { skipSave: true });
    await renderPreview(state.doc);
    try {
      await loadGraphData();
      applyGraphGroupLayout({ relayout: true });
    } catch (_) {
      /* optional */
    }
    if (skipped.length) {
      setStatusError(T("cfg.confirm.result", { ok: ok.length, skip: skipped.length }), skipped[0]);
      window.alert(T("cfg.confirm.alert", { n: skipped.length, list: skipped.join("\n") }));
    } else {
      setStatus(T("cfg.confirm.allDone", { n: ok.length }));
    }
    if (!$("#config-modal").classList.contains("hidden")) {
      openConfigModal({ tab: "pending" });
    }
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
    window.MemoriaPositionMemory?.remember?.(); if (!opts.skipNav && window.MemoriaNavStack) {
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
    setStatus(T("cfg.jump.done", { label }), candidate.file);
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
      $("#link-confirm").textContent = T("cfg.jump.confirmBtn");
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
        setStatus(res.message || T("cfg.linkEdge.recommendFail"));
        return;
      }
      if (res.suggested != null) {
        props.relevance = normalizeLinkRelevance(res.suggested, props.edge_type);
        renderLinkTargetList({ preserveFields: false });
        setStatus(T("cfg.linkEdge.applied", { tid }), formatLinkRelevance(props.relevance));
      } else {
        setStatus(
          T("cfg.linkEdge.notIntegrated"),
          T("cfg.linkEdge.defaultDetail", {
            tid,
            rel: formatLinkRelevance(res.default ?? defaultRelevanceForEdgeType(props.edge_type)),
          })
        );
      }
    } catch (e) {
      setStatus(T("cfg.linkEdge.recommendFail"), String(e.message || e));
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
      <span class="-link-target-edge-label">${esc(T("cfg.linkEdge.typeLabel"))}</span>
      <select data-target-edge-type="${pickIndex}">
        <option value="reference"${et === "reference" ? " selected" : ""}>${esc(T("cfg.edge.typeReference"))}</option>
        <option value="extend"${et === "extend" ? " selected" : ""}>${esc(T("cfg.edge.typeExtend"))}</option>
      </select>
      <span class="-link-target-edge-label">${esc(T("cfg.linkEdge.strengthLabel"))}</span>
      <input type="range" data-target-edge-rel-range="${pickIndex}" min="0" max="1" step="0.05" value="${rel}" title="${esc(T("cfg.linkEdge.relTitle"))}" />
      <input type="number" data-target-edge-rel-num="${pickIndex}" class="-link-relevance-num" min="0" max="1" step="0.05" value="${formatLinkRelevance(rel)}" title="${esc(T("cfg.linkEdge.relTitle"))}" />
      <button type="button" class="-btn secondary -btn--sm" data-target-edge-suggest="${pickIndex}">${esc(T("cfg.linkEdge.suggestBtn"))}</button>
    </div>`;
  }

  function renderLinkTargetEdgesPanel(p) {
    if (!p.selectedOrder.length) {
      return `<div class="-link-edge-editor-panel" id="link-edge-editor-panel">
        <div class="-link-section-title">${esc(T("cfg.linkEdge.sectionTitle"))}</div>
        <p class="-muted -link-edge-empty">${esc(T("cfg.linkEdge.empty"))}</p>
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
      <div class="-link-section-title">${esc(T("cfg.linkEdge.sectionTitle"))}</div>
      <p class="-config-hint -link-edge-panel-hint">${esc(T("cfg.linkEdge.panelHint"))}</p>
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
    if (!p.selectedOrder.length) return T("cfg.linkSave.hintNoTarget");
    readLinkEditorFields();
    if (!(p.anchorText || "").trim()) {
      return T("cfg.linkSave.hintNeedAnchor");
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
    if (!p.selectedOrder.length) return T("cfg.linkSave.hintNoTarget");
    const n = p.selectedOrder.length;
    if (p.mode === "create") return T("cfg.linkSave.statusCreate", { n });
    return n > 1 ? T("cfg.linkSave.statusMulti", { n }) : T("cfg.linkSave.statusSingle");
  }

  function renderLinkEditMeta(p) {
    const text = p.anchorText || p.displayText || "";
    const searchOpts = p.searchOptions || defaultLinkSearchOptions();
    let html = `<div class="-link-edit-meta">`;
    html += `<label class="-link-field"><span>${esc(T("cfg.linkMeta.anchorLabel"))}</span>
      <div class="-link-anchor-field">
        <input type="text" id="link-edit-anchor" value="${esc(text)}" placeholder="${esc(T("cfg.linkMeta.anchorPlaceholder"))}" autocomplete="off" spellcheck="false" />
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
      html += `<p class="-config-hint -link-meta-hint">${T("cfg.linkMeta.metaHint")}</p>`;
      html += `<div class="-link-section-title">${esc(T("cfg.linkMeta.openTitle"))}</div>`;
      html += `<p class="-config-hint -link-targets-hint">${esc(T("cfg.linkMeta.targetsHint"))}</p>`;
    }

    if (isEdit) {
      html += `<div class="-link-pick-legend">
        <span><i class="-link-legend-dot sel"></i>${esc(T("cfg.linkMeta.legendSel"))}</span>
        <span><i class="-link-legend-dot"></i>${esc(T("cfg.linkMeta.legendUnsel"))}</span>
      </div>`;
    } else {
      html += `<div class="-link-pick-legend">
        <span><i class="-link-legend-dot primary"></i>${esc(T("cfg.linkMeta.legendPrimary"))}</span>
        <span><i class="-link-legend-dot sel"></i>${esc(T("cfg.linkMeta.legendQueued"))}</span>
        <span><i class="-link-legend-dot"></i>${esc(T("cfg.linkMeta.legendPlain"))}</span>
      </div>`;
    }

    if (!candidates.length && isEdit) {
      html += `<p class="-muted -link-empty">${esc(T("cfg.linkMeta.noTarget"))}</p>`;
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
          <button type="button" class="${dotCls}" data-pick-dot="${i}" aria-label="${esc(T("cfg.linkMeta.pickAria"))}">
            <span class="-pick-dot-inner"></span>
          </button>
          <div class="-link-pick-label">
            <div class="-link-pick-name">${esc(c.name || tid || c.file)}</div>
            <div class="-link-pick-file">${esc(c.file || tid)}</div>
          </div>
          ${isEdit ? `<button type="button" class="-link-remove-target" data-remove-target="${i}" title="${esc(T("cfg.chip.remove"))}">×</button>` : ""}
        </div>`;
      })
      .join("");

    if (isEdit) {
      html += `<div class="-link-add-row">
        <div class="-link-add-field">
          <input type="text" id="link-add-target" placeholder="${esc(T("cfg.linkMeta.addPlaceholder"))}" autocomplete="off" spellcheck="false" />
          <div class="-link-target-suggest hidden" id="link-add-target-suggest"></div>
        </div>
        <button type="button" id="link-add-target-btn">${esc(T("cfg.linkMeta.addBtn"))}</button>
      </div>`;
      html += renderLinkTargetEdgesPanel(p);
      html += `<details class="-suggest-block -link-tag-suggest">
        <summary>${esc(T("cfg.linkMeta.m4Summary"))}</summary>
        <p class="-config-hint">${esc(T("cfg.linkMeta.m4Hint"))}</p>
        <div class="-suggest-list -suggest-placeholder-list">
          <div class="-suggest-item -suggest-placeholder">
            <span class="-suggest-score">94%</span>
            <span class="-suggest-label">q-learning</span>
            <span class="-muted">tag:rl · q-learning.md</span>
            <button type="button" class="-btn secondary -btn--sm" disabled>${esc(T("cfg.linkMeta.pickBtn"))}</button>
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
          T("cfg.linkMeta.queuePrimary", {
            name: primary?.name || candidateTargetId(primary) || primary?.file,
          }) + (rest > 0 ? T("cfg.linkMeta.queueMore", { n: rest }) : "");
        confirmBtn.disabled = false;
      } else {
        hint.textContent = T("cfg.linkMeta.queueHint");
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
      setStatus(T("cfg.linkSave.targetExists"), tid);
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
      setStatus(T("cfg.linkSave.addFail"), String(e.message || e));
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
        ? T("cfg.linkSave.titleCreateNamed", { text: displayText.slice(0, 32) })
        : T("cfg.linkSave.titleCreate");
    } else {
      $("#link-title").textContent = T("cfg.linkSave.titleEdit", {
        text: displayText.slice(0, 32),
      });
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
      setStatus(T("cfg.linkSave.foundRoute"), overrides[t].join(", "));
    }
  }

  function showLinkPicker(title, candidates) {
    state.linkPicker = {
      mode: "jump",
      title,
      candidates,
      selectedOrder: candidates.length === 1 ? [0] : [],
    };
    $("#link-title").textContent = T("cfg.linkSave.titleMulti", { title });
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
      setStatus(T("cfg.linkSave.fail"), T("cfg.linkSave.needTarget"));
      return;
    }
    const searchQuery = (p.anchorText || "").trim();
    const selectedLines = p.match?.selected?.size ? [...p.match.selected] : [];
    const saveAnchor = resolveSaveAnchorFromSelection(p.match, selectedLines, searchQuery);
    if (!saveAnchor) {
      setStatus(T("cfg.linkSave.fail"), T("cfg.linkSave.needAnchor"));
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

    setStatus(T("cfg.linkSave.saving"));

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
        setStatus(res.message || T("cfg.linkSave.fail"));
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
          setStatus(applyRes.message || T("cfg.linkSave.attachFail"));
          return;
        }
        doc = applyRes.document;
      } else if (needsMatch && !selectedLines.length) {
        setStatus(T("cfg.linkSave.fail"), T("cfg.linkSave.needPositions"));
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

      setStatus(
        T("cfg.linkSave.saved"),
        res.warning ||
          T("cfg.linkSave.savedDetail", {
            saveAnchor,
            targets: targetIds.join(", "),
          })
      );
      if (returnTo === "config") {
        openConfigModal({ tab: "links", highlightLinkTarget: configHighlight });
      }
      if (jumpAfter && targetIds.length) {
        const jumpRes = await call("resolve_links", targetIds);
        const primary = jumpRes.candidates?.[0];
        if (primary) await jumpToTarget(primary, { source: "link" });
      }
    } catch (e) {
      setStatus(T("cfg.linkSave.fail"), String(e.message || e));
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
    if (m.blocked) return T("cfg.match.badgeConflict");
    if (m.excluded) return T("cfg.match.badgeExcluded");
    if (m.is_substring) return T("cfg.match.badgeSubstring");
    if (m.fuzzy) return T("cfg.match.badgeFuzzy");
    if (m.wrapped) return T("cfg.match.badgeWrapped");
    if (m.attached) return T("cfg.match.badgeAttached");
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
    setStatus(T("cfg.match.scanMatching"));
    let scan;
    try {
      scan = await call(
        "scan_link_text_matches",
        state.currentPath,
        anchor,
        searchOptions
      );
    } catch (e) {
      setStatus(T("cfg.match.scanFail"), String(e.message || e));
      return;
    }
    if (scan.status !== "ok") {
      setStatus(scan.message || T("cfg.match.scanFail"));
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
    setStatus(T("cfg.match.matched", { anchor }));
  }

  async function confirmConfigLinkMatch() {
    const m = state.configLinkMatch;
    if (!m || !state.currentPath) {
      setStatus(T("cfg.match.applyFail"), T("cfg.match.noTask"));
      return;
    }
    if (!m.selected.size) {
      const hasSubstring = m.matches.some((r) => r.is_substring && r.line);
      setStatus(
        T("cfg.match.applyFail"),
        hasSubstring
          ? T("cfg.match.substringNote")
          : T("cfg.match.selectNote")
      );
      return;
    }
    const searchQuery = (m.anchorText || "").trim();
    const saveAnchor = resolveSaveAnchorFromSelection(m, [...m.selected], searchQuery);
    if (!saveAnchor) {
      setStatus(T("cfg.match.applyFail"), T("cfg.match.needText"));
      return;
    }
    setStatus(T("cfg.match.applying"));
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
        setStatus(res.message || T("cfg.match.applyFail"));
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
      setStatus(
        T("cfg.match.attached"),
        T("cfg.match.attachDetail", {
          anchor: saveAnchor,
          n: m.selected.size,
        })
      );
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
      setStatus(T("cfg.match.applyFail"), String(e.message || e));
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
      T("cfg.linkOps.detachConfirm", { line: line || "?", label })
    );
    if (!ok) return;
    if (!line) {
      setStatus(T("cfg.linkOps.noLine"), T("cfg.linkOps.noLineDetail"));
      return;
    }
    setStatus(T("cfg.linkOps.removing"));
    try {
      const res = await call(
        "detach_link_instance",
        state.currentPath,
        payload.targetId,
        line
      );
      if (res.status !== "ok") {
        setStatus(res.message || T("cfg.linkOps.removeFail"));
        return;
      }
      const doc = res.document;
      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await renderPreview(doc);
      }
      setStatus(T("cfg.linkOps.detached"));
    } catch (e) {
      setStatus(T("cfg.linkOps.removeFail"), String(e.message || e));
    }
  }

  async function deleteLinkFromConfig(anchorText) {
    if (!state.currentPath) return;
    const anchor = (anchorText || "").trim();
    if (!anchor) return;
    const ok = window.confirm(T("cfg.linkOps.deleteConfirm", { anchor }));
    if (!ok) return;
    setStatus(T("cfg.linkOps.deleting"));
    try {
      const res = await call("delete_link_route", state.currentPath, anchor);
      if (res.status !== "ok") {
        setStatus(res.message || T("cfg.linkOps.deleteFail"));
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
      setStatus(T("cfg.linkOps.deleted"), anchor);
    } catch (e) {
      setStatus(T("cfg.linkOps.deleteFail"), String(e.message || e));
    }
  }

  async function removeLinkFromDocument(payload) {
    if (!state.currentPath) return;
    const ok = window.confirm(
      T("cfg.linkOps.unwrapConfirm", {
        text: payload.displayText || payload.targetId,
      })
    );
    if (!ok) return;
    setStatus(T("cfg.linkOps.removing"));
    try {
      const res = await call(
        "remove_link",
        state.currentPath,
        payload.targetId,
        payload.displayText !== payload.targetId ? payload.displayText : "",
        payload.linkType || ""
      );
      if (res.status !== "ok") {
        setStatus(res.message || T("cfg.linkOps.removeFail"));
        return;
      }
      const doc = res.document;
      if (doc?.status === "ok") {
        state.doc = doc;
        renderEditor(doc);
        renderKpList(doc);
        await renderPreview(doc);
      }
      setStatus(T("cfg.linkOps.unwrapped"));
    } catch (e) {
      setStatus(T("cfg.linkOps.removeFail"), String(e.message || e));
    }
  }

  // ── task-145：链接点击「小窗优先」──────────────────────────────────────────────
  // 所有可解析链接点击都先出链接旁圆角浮层（无全屏遮罩、不挡全文）：
  //   候选=1 ⇒ 直接一张卡片；候选>1 ⇒ 候选列表 +「全部打开」。
  // 卡片：①名称 ②解释（description；缺则区域首行摘要；再缺明确「无描述」）
  //       ③区域内联预览（限高 12 行、可滚动） ④「拉到编辑区」按钮。
  // 「拉到编辑区」= 既有 jumpToTarget（打开文件并定位该区域），浮层同时消失；**不是**插入引用。
  // 数据：resolve_links 给 name/file/start/end；description/区域正文用二次 RPC load_document 补齐（缓存，不猜）。
  const LINK_POP_PREVIEW_LINES = 12;   // 卡片最多显示行数
  const LINK_POP_FETCH_LINES = 32;     // 二次 RPC 最多取多少行（防超长）

  function linkPopT(key, params) {
    return T("cfg.linkPop." + key, params);
  }

  function _linkPopCandidateName(c) {
    return c?.name || c?.kp_id || c?.requested_id || c?.file || linkPopT("unknownName");
  }

  function _linkPopOutside(e) {
    const pop = state.linkPopover;
    if (!pop) return;
    const t = e.target;
    if ((pop.el && pop.el.contains(t)) || t === pop.anchorEl ||
        (pop.anchorEl && pop.anchorEl.contains && pop.anchorEl.contains(t))) return;
    closeLinkPopover();
  }

  function _linkPopKeydown(e) {
    const pop = state.linkPopover;
    if (!pop) return;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeLinkPopover({ focusBack: true });
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      e.stopPropagation();
      linkPopSetActive(pop.active + (e.key === "ArrowDown" ? 1 : -1), true);
      return;
    }
    if (e.key === "Enter") {
      if (e.target && String(e.target.tagName || "").toUpperCase() === "BUTTON") return;
      e.preventDefault();
      e.stopPropagation();
      linkPopActivate(pop.active);
    }
  }

  function _linkPopReposition() {
    const pop = state.linkPopover;
    if (!pop || !pop.el || !pop.anchorEl) return;
    _linkPopPosition(pop);
  }

  /** 定位：优先链接下方左对齐；不够位则翻上方；四边夹在视口内（无遮罩 ⇒ 必须不挡触发点） */
  function _linkPopPosition(pop) {
    const el = pop.el;
    const anchor = pop.anchorEl;
    if (!el || !anchor) return;
    const r = anchor.getBoundingClientRect();
    const pw = el.offsetWidth || 360;
    const ph = el.offsetHeight || 240;
    const vw = window.innerWidth || 1280;
    const vh = window.innerHeight || 800;
    const gap = 8;
    const margin = 8;
    let left = Math.min(Math.max(margin, r.left), Math.max(margin, vw - pw - margin));
    let top = r.bottom + gap;
    if (top + ph > vh - margin) {
      const above = r.top - gap - ph;
      top = above >= margin ? above : Math.max(margin, vh - ph - margin);
    }
    el.style.left = Math.round(left) + "px";
    el.style.top = Math.round(top) + "px";
    el.style.visibility = "";
  }

  function linkPopSetActive(idx, focus) {
    const pop = state.linkPopover;
    if (!pop || !pop.el) return;
    const cards = Array.from(pop.el.querySelectorAll(".-link-pop-card"));
    if (!cards.length) return;
    const clamped = Math.max(0, Math.min(cards.length - 1, Number(idx) || 0));
    pop.active = clamped;
    cards.forEach((card, i) => card.classList.toggle("-active", i === clamped));
    const card = cards[clamped];
    try { card.scrollIntoView({ block: "nearest" }); } catch (_) { /* noop */ }
    if (focus) {
      try { card.focus({ preventScroll: true }); } catch (_) { try { card.focus(); } catch (__) { /* noop */ } }
    }
  }

  function linkPopApply(pop, idx, data) {
    if (state.linkPopover !== pop || !pop.el) return;
    const card = pop.el.querySelectorAll(".-link-pop-card")[idx];
    if (!card) return;
    const descEl = card.querySelector("[data-link-pop-desc]");
    const preEl = card.querySelector("[data-link-pop-preview]");
    const truncEl = card.querySelector("[data-link-pop-trunc]");
    if (descEl) descEl.textContent = data.desc || linkPopT("noDesc");
    if (preEl) preEl.textContent = data.preview || linkPopT("noRegion");
    if (truncEl) truncEl.textContent = data.truncated ? " · " + data.truncated : "";
  }

  async function linkPopLoadDoc(pop, file) {
    if (!pop.docCache.has(file)) {
      pop.docCache.set(file, call("load_document", file).catch(() => null));
    }
    return pop.docCache.get(file);
  }

  /** 补齐：description（KP）+ 区域正文（start_line..end_line） */
  async function linkPopEnrich(pop, idx) {
    const c = pop.candidates[idx];
    if (!c) return;
    if (!c.file) {
      linkPopApply(pop, idx, { desc: linkPopT("noDesc"), preview: linkPopT("noRegion"), truncated: "" });
      return;
    }
    const doc = await linkPopLoadDoc(pop, c.file);
    if (state.linkPopover !== pop) return;
    if (!doc || doc.status !== "ok") {
      linkPopApply(pop, idx, { desc: linkPopT("noDesc"), preview: linkPopT("previewUnavailable"), truncated: "" });
      return;
    }
    const kp = (doc.knowledge_points || []).find((k) => k && k.id === c.kp_id) || null;
    const lines = Array.isArray(doc.lines) ? doc.lines : String(doc.body || "").split("\n");
    let region = [];
    let total = 0;
    if (c.start_line && c.end_line && c.end_line >= c.start_line) {
      const s = Math.max(0, Number(c.start_line) - 1);
      const e = Math.min(lines.length, Number(c.end_line));
      total = Math.max(0, e - s);
      region = lines.slice(s, Math.min(e, s + LINK_POP_FETCH_LINES));
    }
    const previewLines = region.slice(0, LINK_POP_PREVIEW_LINES);
    const firstLine = region.map((l) => String(l || "").trim()).find(Boolean) || "";
    const desc = String(kp?.description || "").trim() ||
      (firstLine ? firstLine.slice(0, 120) : "") ||
      linkPopT("noDesc");
    const truncated = total > LINK_POP_PREVIEW_LINES
      ? linkPopT("truncated", { shown: Math.min(total, LINK_POP_PREVIEW_LINES), total })
      : "";
    linkPopApply(pop, idx, {
      desc: desc,
      preview: previewLines.length ? previewLines.join("\n") : linkPopT("noRegion"),
      truncated: truncated,
    });
  }

  function linkPopActivate(idx) {
    const pop = state.linkPopover;
    if (!pop) return;
    const c = pop.candidates[Math.max(0, Math.min(pop.candidates.length - 1, Number(idx) || 0))];
    if (!c || !c.file) return;
    closeLinkPopover({ noFocus: true });
    jumpToTarget(c, { source: "link" });
  }

  async function linkPopOpenAll() {
    const pop = state.linkPopover;
    if (!pop) return;
    const items = (pop.candidates || []).filter((c) => c && c.file);
    if (!items.length) return;
    closeLinkPopover({ noFocus: true });
    for (let i = 0; i < items.length; i++) ensureOpenTab(items[i], { pending: i > 0 });
    renderTabs();
    await jumpToTarget(items[0], { source: "link", skipTabUpsert: true });
  }

  function closeLinkPopover(opts = {}) {
    const pop = state.linkPopover;
    if (!pop) return;
    if (pop.el && pop.el.parentNode) pop.el.parentNode.removeChild(pop.el);
    if (pop.anchorEl && pop.anchorEl.setAttribute) pop.anchorEl.setAttribute("aria-expanded", "false");
    document.removeEventListener("mousedown", _linkPopOutside, true);
    document.removeEventListener("keydown", _linkPopKeydown, true);
    window.removeEventListener("resize", _linkPopReposition, true);
    state.linkPopover = null;
    if (opts.focusBack && pop.anchorEl && pop.anchorEl.isConnected) {
      try { pop.anchorEl.focus(); } catch (_) { /* noop */ }
    } else if (!opts.noFocus && pop.opener && pop.opener !== document.body &&
               pop.opener.isConnected && typeof pop.opener.focus === "function") {
      try { pop.opener.focus(); } catch (_) { /* noop */ }
    }
  }

  /** 链接点击统一入口：单候选也先出浮层（task-145 核心变化） */
  function showLinkPopover(anchorEl, title, candidates) {
    const list = (candidates || []).filter(Boolean);
    if (!list.length || !anchorEl) return;
    if (state.linkPopover && state.linkPopover.anchorEl === anchorEl) {
      closeLinkPopover({ focusBack: true });
      return;
    }
    closeLinkPopover({ noFocus: true });
    const pop = {
      anchorEl,
      title: title || "",
      candidates: list,
      active: 0,
      docCache: new Map(),
      el: null,
      opener: document.activeElement,
    };
    state.linkPopover = pop;
    const multi = list.length > 1;
    const cards = list.map((c, i) => {
      const name = _linkPopCandidateName(c);
      const unresolved = !c.file;
      const range = (c.start_line && c.end_line) ? ` · L${c.start_line}–${c.end_line}` : "";
      const fileMeta = esc(c.file || linkPopT("unresolvedFile"));
      return `<div class="-link-pop-card" role="menuitem" tabindex="-1" data-idx="${i}" aria-label="${esc(name)}">` +
        `<div class="-link-pop-name">${esc(name)}</div>` +
        `<div class="-link-pop-desc -muted" data-link-pop-desc>${esc(linkPopT("loading"))}</div>` +
        `<pre class="-link-pop-preview" data-link-pop-preview aria-label="${esc(linkPopT("previewAria"))}">${esc(linkPopT("loading"))}</pre>` +
        `<div class="-link-pop-meta -muted"><span>${fileMeta}${range}</span><span data-link-pop-trunc></span></div>` +
        `<div class="-link-pop-actions"><button type="button" class="-btn primary -btn--sm" data-link-pop-pull data-idx="${i}"` +
        `${unresolved ? " disabled" : ""}>${esc(linkPopT("pull"))}</button></div>` +
        `</div>`;
    }).join("");
    const header = multi
      ? `<div class="-link-pop-header"><span class="-link-pop-title">${esc(title || "")}</span>` +
        `<span class="-link-pop-count -muted">${esc(linkPopT("count", { n: list.length }))}</span></div>`
      : "";
    const footer = multi
      ? `<div class="-link-pop-footer"><button type="button" class="-btn secondary -btn--sm" data-link-pop-all>` +
        `${esc(linkPopT("openAll", { n: list.length }))}</button></div>`
      : "";
    const el = document.createElement("div");
    el.id = "link-popover";
    el.className = "-link-popover";
    el.setAttribute("role", "menu");
    el.setAttribute("aria-label", linkPopT("menuLabel", { title: title || "" }));
    el.style.visibility = "hidden";
    el.innerHTML = header + `<div class="-link-pop-list">${cards}</div>` + footer;
    document.body.appendChild(el);
    pop.el = el;
    el.addEventListener("mousedown", (e) => e.stopPropagation());
    el.addEventListener("focusout", (e) => {
      if (!state.linkPopover || state.linkPopover !== pop) return;
      const to = e.relatedTarget;
      if (to && (el.contains(to) || to === anchorEl)) return;
      if (to) closeLinkPopover();
    });
    el.querySelectorAll(".-link-pop-card").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest("[data-link-pop-pull]")) return;
        linkPopActivate(Number(card.dataset.idx));
      });
      card.addEventListener("focus", () => linkPopSetActive(Number(card.dataset.idx), false));
    });
    el.querySelectorAll("[data-link-pop-pull]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        linkPopActivate(Number(btn.dataset.idx));
      });
    });
    const allBtn = el.querySelector("[data-link-pop-all]");
    if (allBtn) allBtn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); linkPopOpenAll(); });
    if (anchorEl.setAttribute) anchorEl.setAttribute("aria-expanded", "true");
    _linkPopPosition(pop);
    document.addEventListener("mousedown", _linkPopOutside, true);
    document.addEventListener("keydown", _linkPopKeydown, true);
    window.addEventListener("resize", _linkPopReposition, true);
    linkPopSetActive(0, true);
    list.forEach((c, i) => { linkPopEnrich(pop, i); });
  }

  async function onMemoriaLinkClick(el, ev) {
    if (_brush) return; // 画笔模式下不跳转，避免涂抹时误触链接
    const target = el.dataset.linkTarget;
    const type = el.dataset.linkType || "";
    if (!target) return;
    if (el.classList.contains("-link-broken")) {
      await openLinkEditorFromElement(el);
      return;
    }
    // task-145 快速通道（**待确认**）：Ctrl/Cmd+点击 = 直接跳转，跳过浮层。
    // 理由：高频连续跳转时的低风险逃生口；普通点击仍 100% 先出浮层。
    const quickSkip = !!(ev && (ev.ctrlKey || ev.metaKey));
    const title = el.textContent?.trim() || target;
    try {
      const multiRaw = el.dataset.linkTargets;
      let candidates = [];
      if (multiRaw) {
        let ids;
        try {
          ids = JSON.parse(multiRaw);
        } catch (_) {
          ids = [];
        }
        const res = await call("resolve_links", ids);
        if (res.status === "not_found" || res.status === "error") {
          setStatus(res.message || T("cfg.linkClick.unresolvable"), T("cfg.linkClick.unbound"));
          return;
        }
        candidates = res.candidates || [];
      } else {
        const routeIds = state.doc?.link_overrides?.[target];
        if (routeIds?.length) {
          const res = await call("resolve_links", routeIds);
          candidates = res.candidates || [];
        } else {
          const res = await call("resolve_link", target);
          if (res.status === "not_found" || res.status === "error") {
            setStatus(res.message || T("cfg.linkClick.notFound", { target }), T("cfg.linkClick.unbound"));
            return;
          }
          candidates = res.candidates || [];
        }
      }
      if (!candidates.length) {
        setStatus(T("cfg.linkClick.notFound", { target }), T("cfg.linkClick.unbound"));
        return;
      }
      if (quickSkip && candidates.length === 1) {
        closeLinkPopover({ noFocus: true });
        await jumpToTarget(candidates[0], { source: "link" });
        return;
      }
      // ★ 核心变化：单候选也先出浮层（不再直接跳转）
      showLinkPopover(el, title, candidates);
    } catch (e) {
      setStatus(T("cfg.linkClick.failed", { target }), String(e.message || e));
    }
    if (type) {
      /* edge_hint 预留 M2/M3 边类型展示 */
    }
  }

  async function navBack() {
    if (!window.MemoriaNavStack || !MemoriaNavStack.canBack()) return;
    window.MemoriaPositionMemory?.remember?.(); const frame = MemoriaNavStack.navBack();
    updateNavButtons();
    if (frame) await openFile(frame.file, { fromNav: true, kpId: frame.kpId, navAnchor: frame.anchorLine });
  }

  async function navForward() {
    if (!window.MemoriaNavStack || !MemoriaNavStack.canForward()) return;
    window.MemoriaPositionMemory?.remember?.(); const frame = MemoriaNavStack.navForward();
    updateNavButtons();
    if (frame) await openFile(frame.file, { fromNav: true, kpId: frame.kpId, navAnchor: frame.anchorLine });
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

  function postProcessWikilinks(root) {
    const preview = $("#preview");
    if (!preview) return;
    const lookup = state.linkTargetSet;
    const hasLookup = lookup instanceof Set;
    // 侧车 links[] 里已把该 [[]] 锚文本路由到具体 target（如 [[中文名]] → 英文 id）。
    // 判定“实跳转”需同时满足：锚文本本身可解析，或存在路由且至少一个路由目标
    // 落在可解析集合（KP id / 文件 stem）内；路由指向不存在目标时仍按虚链接
    // （-link-broken）处理，与 marked 显示路径（postProcessMemoriaLinks）保持一致。
    const overrides = state.doc?.link_overrides || {};
    (root || preview).querySelectorAll(".-wikilink").forEach((el) => {
      const target = el.getAttribute("data--target") || "";
      el.classList.add("memoria-link");
      el.setAttribute("role", "link");
      el.setAttribute("data-link-target", target);
      el.setAttribute("data-link-type", "");
      const blockEl = el.closest("[data--src-line]");
      const line = blockEl ? Number(blockEl.getAttribute("data--src-line")) || 0 : 0;
      el.setAttribute("data-link-line", String(line));
      const routeTargets = overrides[target] || [];
      const routeOk = routeTargets.length > 0;
      if (hasLookup) {
        const routeResolved = routeOk && routeTargets.some((t) => lookup.has(t));
        if (lookup.has(target) || routeResolved) {
          el.classList.add("-link-resolved");
          el.setAttribute("tabindex", "0");
          el.setAttribute("title", esc(T("preview.link.jump", { key: target })));
        } else {
          el.classList.add("-link-broken", "memoria-broken-link");
          el.setAttribute("tabindex", "-1");
          el.setAttribute("title", esc(T("cfg.linkClick.unboundTitle", { target })));
        }
      } else {
        el.classList.add("-link-pending");
        el.setAttribute("tabindex", "0");
      }
    });
  }

  function isKbMarkdownHref(href) {
    return (
      typeof href === "string" &&
      href.length > 0 &&
      !href.startsWith("#") &&
      !/^(https?:|data:|mailto:|javascript:|ftp:|\/\/|\/)/i.test(href) &&
      /\.(md|markdown)(?:[?#]|$)/i.test(href)
    );
  }

  function resolveKbMdTarget(href, currentPath) {
    if (!currentPath) return null;
    const curDir =
      currentPath.indexOf("/") >= 0
        ? currentPath.slice(0, currentPath.lastIndexOf("/") + 1)
        : "";
    const raw = href.split(/[?#]/)[0].replace(/^\.\//, "");
    const parts = [
      ...curDir.split("/").filter(Boolean),
      ...raw.split("/").filter(Boolean),
    ];
    const out = [];
    for (const p of parts) {
      if (p === ".") continue;
      if (p === "..") {
        out.pop();
        continue;
      }
      out.push(p);
    }
    return out.length ? out.join("/") : null;
  }

  function onPreviewMdLinkDelegate(e) {
    const t = e.target;
    if (!t || !t.closest) return;
    if (e.button !== 0 && e.button !== undefined) return;
    const a = t.closest("a[href]");
    if (!a) return;
    // wikilink/关系链接已由元素级处理，不在此拦截
    if (a.closest(".memoria-link, .-wikilink")) return;
    const href = (a.getAttribute("href") || "").trim();
    if (!isKbMarkdownHref(href)) return;
    const rel = resolveKbMdTarget(href, state.currentPath || "");
    if (!rel) return;
    const files = state.files;
    if (!Array.isArray(files)) return;
    // list_files 返回 items 数组（{path, ...}），兼容纯字符串形态
    const known = files.some((f) =>
      f ? (typeof f === "string" ? f === rel : f.path === rel) : false
    );
    if (!known) return;
    e.preventDefault();
    e.stopPropagation();
    openFile(rel).catch(() => {});
  }

  function bindPreviewLinks(root) {
    const preview = $("#preview");
    if (!preview) return;
    // 惰性绑定一次：#preview 容器级委托，把指向 KB 内 .md 的普通 markdown 链接
    // 转为应用内文件打开（避免 WebView 导航到静态路径 404）
    if (!preview.dataset.kbmdBound) {
      preview.dataset.kbmdBound = "1";
      preview.addEventListener("click", onPreviewMdLinkDelegate);
    }
    // 仅绑定未绑定过的元素，避免增量渲染时对旧链接重复绑定事件
    (root || preview).querySelectorAll(".memoria-link:not([data--bound])").forEach((el) => {
      el.setAttribute("data--bound", "1");
      el.addEventListener("click", (e) => {
        e.preventDefault();
        onMemoriaLinkClick(el, e);
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
        : ` <span class="-muted">${esc(T("cfg.linkClick.notInGraph"))}</span>`;
    hint.innerHTML = `<span class="-muted">${esc(T("cfg.linkClick.graphLinkWord"))}</span> ${esc(src)} → ${esc(tgt)}${note}`;
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

  // 源码区选区（键盘 Shift+方向键 / 鼠标跨行拖拽）已按
  // docs/conventions/frontend-modules.md 迁至 js/sel-source.js，
  // 由 bindEditorSelectInteraction() 末尾 MemoriaSelSource.init({...}) 装配。

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

  // ── task-150：源码区剪切（Ctrl+X）—— **完全接管** ─────────────────────────────
  //  为什么必须接管：源码区每行是**独立 contenteditable 根**（`.-line-content`）。真机实测（WebView2）：
  //   · 单行选区：原生 cut 可用；
  //   · 跨行选区：原生 cut **只删除第一个根内**的那部分，而剪贴板却拿到（近似）全文
  //     ⇒ 用户看到"剪贴板有、文档只少了一截"，属**静默部分删除/内容残留**（比完全失效更坏）；
  //   · 整行跨行选区：原生序列化还会丢空行（块边界被吞）。
  //  接管后不变量：① 剪贴板 = 序列化选区（LF，与文档模型一致）；② 删除走源码编辑管线，`_srcPushBefore`
  //  只打一次 ⇒ **单个撤销单元**；③ 写剪贴板失败 ⇒ **可见报错且不删内容**（静默吞掉是最坏失败）。
  /** 行内字符偏移（支持 range 端点是元素节点的情况；text 节点走既有 `offsetWithinLine`） */
  function _srcColInLine(node, offset, contentEl) {
    if (!node) return 0;
    if (node.nodeType === Node.TEXT_NODE) return offsetWithinLine(node, offset, contentEl);
    try {
      const pre = document.createRange();
      pre.setStart(contentEl, 0);
      pre.setEnd(node, offset || 0);
      return pre.toString().length;
    } catch (_) {
      return 0;
    }
  }
  /** 行纯文本：剔除分栏"假光标"等视觉元素（与 `collectEditorBody` 同口径） */
  function _srcLinePlainText(contentEl) {
    if (!contentEl) return "";
    if (!contentEl.querySelector(".-sync-cursor")) return contentEl.textContent || "";
    const clone = contentEl.cloneNode(true);
    clone.querySelectorAll(".-sync-cursor").forEach((n) => n.remove());
    return clone.textContent || "";
  }
  /** 读取当前源码选区 → 剪切计划；null = 无选区/不在源码区（交还原生，不做任何接管） */
  function _srcSelectionPlan() {
    const editor = $("#editor");
    const sel = window.getSelection();
    if (!editor || !sel || !sel.rangeCount) return null;
    const range = sel.getRangeAt(0);
    if (range.collapsed) return null;
    if (!editor.contains(range.startContainer) || !editor.contains(range.endContainer)) return null;
    const startLineEl = closestLineEl(range.startContainer);
    const endLineEl = closestLineEl(range.endContainer);
    if (!startLineEl || !endLineEl) return null;
    // 归一化成文档顺序（反向选区也要正确）
    const forward = !!(startLineEl.compareDocumentPosition(endLineEl) & Node.DOCUMENT_POSITION_FOLLOWING);
    const loEl = forward ? startLineEl : endLineEl;
    const hiEl = forward ? endLineEl : startLineEl;
    const loContent = loEl.querySelector(".-line-content");
    const hiContent = hiEl.querySelector(".-line-content");
    if (!loContent || !hiContent) return null;
    const loOff = _srcColInLine(forward ? range.startContainer : range.endContainer,
      forward ? range.startOffset : range.endOffset, loContent);
    const hiOff = _srcColInLine(forward ? range.endContainer : range.startContainer,
      forward ? range.endOffset : range.startOffset, hiContent);
    const loText = _srcLinePlainText(loContent);
    const hiText = _srcLinePlainText(hiContent);
    if (loEl === hiEl) {
      const s = Math.max(0, Math.min(loOff, hiOff));
      const e = Math.max(s, loOff, hiOff);
      return {
        kind: "single", loEl: loEl, hiEl: hiEl, loContent: loContent, hiContent: hiContent,
        loOff: s, hiOff: e, loText: loText, hiText: hiText,
        text: loText.slice(s, e), range: range.cloneRange(),
      };
    }
    const midText = [];
    let el = loEl.nextElementSibling;
    while (el && el !== hiEl) {
      const c = el.querySelector(".-line-content");
      midText.push(c ? _srcLinePlainText(c) : "");
      el = el.nextElementSibling;
    }
    const text = loText.slice(loOff) + "\n" + midText.map((m) => m + "\n").join("") + hiText.slice(0, hiOff);
    return {
      kind: "cross", loEl: loEl, hiEl: hiEl, loContent: loContent, hiContent: hiContent,
      loOff: loOff, hiOff: hiOff, loText: loText, hiText: hiText, midText: midText, text: text,
    };
  }
  /** 按计划删除选区（只改编辑器 DOM；撤销/渲染/滚动由调用方收尾） */
  function _srcApplyCutPlan(plan) {
    if (plan.kind === "single") {
      try { plan.range.deleteContents(); } catch (_) { /* 极端情况：继续走下方 normalize */ }
      const content = plan.loContent;
      try { content.normalize(); } catch (_) { /* noop */ }
      if (!content.textContent) content.innerHTML = "<br>";
      focusLineContent(content, plan.loOff);
      return { content: content };
    }
    plan.loContent.textContent = plan.loText.slice(0, plan.loOff) + plan.hiText.slice(plan.hiOff);
    if (!plan.loContent.textContent) plan.loContent.innerHTML = "<br>";
    let el = plan.loEl.nextElementSibling;
    while (el && el !== plan.hiEl) {
      const next = el.nextElementSibling;
      el.remove();
      el = next;
    }
    plan.hiEl.remove();
    renumberSourceLines();
    focusLineContent(plan.loContent, plan.loOff);
    return { content: plan.loContent };
  }
  /** 执行剪切：**先写剪贴板**（失败 ⇒ 可见报错且不删），成功才删（单撤销单元） */
  async function _srcCutExecute(plan) {
    let ok = false;
    try { ok = await writeClipboardText(plan.text); } catch (_) { ok = false; }
    if (!ok) {
      // 可见报错（双通道：底栏红字 + 顶部浮层）。静态原则：绝不"以为剪切成功、却没有可粘贴内容"。
      const msg = T("srcEdit.cutClipboardFailed");
      try { setStatusError(msg); } catch (_e1) {
        try { showFlashError(msg); } catch (_e2) { /* 极端兜底：下面的 syncLog 仍会留下痕迹 */ }
      }
      syncLog("srcCut: 写剪贴板失败 ⇒ 不删除内容（已可见报错）");
      return { ok: false };
    }
    _srcPushBefore();
    _srcCoalesceAt = 0;
    const res = _srcApplyCutPlan(plan);
    _srcAfterEdit();
    const pane = $("#editor-pane");
    const sel = window.getSelection();
    if (pane && sel && sel.rangeCount && res.content.contains(sel.getRangeAt(0).startContainer)) {
      _keepCaretVisible(pane, sel.getRangeAt(0), res.content.closest(".-line") || res.content);
    }
    scheduleRenderSync();
    markDirty();
    syncLog("srcCut: 完成 (" + plan.kind + ", 剪贴板写入成功, 单撤销单元)");
    return { ok: true, content: res.content };
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
    const _snapBody = _restoreDocTailNL(snap.body);
    state.doc.body = _snapBody;
    state.doc.lines = _linesFromBody(_snapBody);
    state.doc.preview_body = null;
    renderEditor(state.doc);
    await _renderPreviewKeepScroll();   // task-141：撤销/重做也是整篇重渲 ⇒ 同样要保住预览滚动位置
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
    const editor = $("#editor");
    if (editor) {
      editor.style.setProperty(
        "--lineno-ch",
        String(Math.max(1, String(els.length).length))
      );
    }
  }

  function bindEditorSelectInteraction() {
    const editor = $("#editor");
    if (!editor || editor.dataset.selectBound) return;
    editor.dataset.selectBound = "1";

    /** E26：源码区编辑后保持光标可见（IME 组合期间不滚，避免候选框/光标跳动）。 */
    function _keepSrcCaretVisible(contentEl) {
      if (!contentEl || _srcComposing) return;
      const pane = $("#editor-pane");
      const sel = window.getSelection();
      if (!pane || !sel || !sel.rangeCount) return;
      const range = sel.getRangeAt(0);
      if (!contentEl.contains(range.startContainer)) return;
      const lineEl = contentEl.closest(".-line") || contentEl;
      _keepCaretVisible(pane, range, lineEl);
    }

    // 方向键滚轮效果：pane 单步滚动（模拟滚轮一档约 6 行 @14px）。
    // 仅在"编辑模式关闭（只读）"时生效：编辑模式下上下键归属光标位置控制，
    // 源码/预览均正常移动光标，不做干预。
    const ARROW_SCROLL_STEP = 96;
    function scrollPaneBy(pane, dir) {
      if (!pane) return;
      const max = pane.scrollHeight - pane.clientHeight;
      if (dir > 0 && pane.scrollTop < max - 1) {
        pane.scrollTop = Math.min(pane.scrollTop + ARROW_SCROLL_STEP, max);
      } else if (dir < 0 && pane.scrollTop > 0) {
        pane.scrollTop = Math.max(pane.scrollTop - ARROW_SCROLL_STEP, 0);
      }
    }
    document.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
      const preview = $("#preview");
      if (!preview || preview.contentEditable === "true") return;
      // 焦点在可编辑区/输入控件/文件树/弹窗内：交还各自处理
      const ae = document.activeElement;
      if (ae) {
        if (ae.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName)) return;
        if (ae.closest && (ae.closest("#file-tree") || ae.closest(".-modal"))) return;
      }
      const mode = state.viewMode;
      if (mode !== "preview" && mode !== "split" && mode !== "source") return;
      let pane;
      if (mode === "source") {
        pane = $("#editor-pane");
      } else if (mode === "preview") {
        pane = $("#preview-pane");
      } else {
        // 分栏：焦点在源码侧滚源码面板，否则滚预览面板
        const editor = $("#editor");
        pane = ae && editor && editor.contains(ae) ? $("#editor-pane") : $("#preview-pane");
      }
      if (!pane) return;
      e.preventDefault();
      scrollPaneBy(pane, e.key === "ArrowDown" ? 1 : -1);
    });

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
      // E26：只在光标越出视口时补滚动（IME 组合中 _keepSrcCaretVisible 内部直接跳过）
      if (!e.isComposing) _keepSrcCaretVisible(content);
      scheduleRenderSync();
      markDirty();
    });

    // ── M6b：正文行结构变化（Enter/删行合并）实时同步 KP 行号范围与高亮 ──
    function _kpRr(kp) { return kp.range_resolved || {}; }
    function _kpStart(kp) {
      const r = _kpRr(kp);
      if (r.ok) return r.start_line || 1;
      return kp.range?.start?.line_hint || 1;
    }
    function _kpEnd(kp) {
      const s = _kpStart(kp);
      const r = _kpRr(kp);
      if (r.ok) return Math.max(s, r.end_line || s);
      return Math.max(s, kp.range?.end?.line_hint || s);
    }
    function _kpSetLines(kp, s, e) {
      if (!kp) return;
      e = Math.max(1, s, e);
      const r = _kpRr(kp);
      if (r.ok) {
        r.start_line = s;
        r.end_line = e;
      }
      const range = kp.range || {};
      range.start = range.start || {};
      range.start.line_hint = s;
      range.end = range.end || {};
      range.end.line_hint = e;
    }
    function _kpList() { return (state.doc && state.doc.knowledge_points) || []; }

    /** 插入 delta 行后调整。
     *  before=false：新行位于 p 行之后，后续 KP（起点 > p）顺延；
     *  before=true：新行插到 p 行之前，后续 KP（起点 >= p）顺延。
     *  absorbId：该 KP 吸收新行（并入区域）→ 仅终点 +delta。 */
    function adjustKpRangesAfterInsert(p, { before = false, absorbId = null, delta = 1 } = {}) {
      const kps = _kpList();
      for (const k of kps) {
        if (k.id === absorbId) {
          _kpSetLines(k, _kpStart(k), _kpEnd(k) + delta);
          continue;
        }
        const s = _kpStart(k);
        if ((before ? s >= p : s > p)) _kpSetLines(k, s + delta, _kpEnd(k) + delta);
      }
      refreshKpRangeUi();
    }

    /** 删除 R 行（内容并入上一行）后调整。 */
    function adjustKpRangesAfterRemove(R) {
      const kps = _kpList();
      for (const k of kps) {
        const s = _kpStart(k);
        const e = _kpEnd(k);
        if (s > R) { _kpSetLines(k, s - 1, e - 1); continue; }
        if (e < R) continue;
        // 覆盖 R：区域收缩一行；若删除的是区域首行则并入上一行（近似，保存后端重锚会校正）
        const ns = s === R ? Math.max(1, s - 1) : s;
        _kpSetLines(k, ns, Math.max(ns, e - 1));
      }
      if (window.__bench) {
        syncLog("[M6b] remove", JSON.stringify({ R, after: _kpList().map((k) => `${k.id}:${_kpStart(k)}-${_kpEnd(k)}`) }));
      }
      refreshKpRangeUi();
    }

    /** 块级源码替换（预览 AST 编辑提交）：按 0 基区间 [startIdx, endIdxExcl) 替换行数的差平移 KP 范围。
     *  与替换区重叠的 KP 以“内容并入/扩展”近似：起点在区前则保留，在区内则移到区新起点，终点随 delta 平移；
     *  完全在区后的 KP 整体顺延 delta。近似结果由保存后后端 resync 权威校正。 */
    function adjustKpRangesAfterSpanReplace(startIdx, endIdxExcl, oldCount, newCount) {
      const delta = newCount - oldCount;
      if (!delta) return;
      for (const k of _kpList()) {
        const s = _kpStart(k);
        const e = _kpEnd(k);
        const is = s - 1;
        const ie = e - 1;
        if (ie < startIdx) continue; // 完全在替换区之前
        if (is >= endIdxExcl) {
          _kpSetLines(k, s + delta, e + delta); // 之后整体顺延
          continue;
        }
        // 与替换区重叠
        const ns = is < startIdx ? s : startIdx + 1;
        _kpSetLines(k, ns, Math.max(ns, e + delta));
      }
      if (window.__bench) {
        syncLog("[M6b] span", JSON.stringify({ startIdx, oldCount, newCount, delta, after: _kpList().map((k) => `${k.id}:${_kpStart(k)}-${_kpEnd(k)}`) }));
      }
      refreshKpRangeUi();
    }

    // S5/S5b：本函数定义在 bindEditorSelectInteraction 作用域内；预览侧 commitRange 与门面 _surfaceSpliceRange
    // 在模块外层（词法上不可见）⇒ 经 window 暴露同一实现供两处调用，避免复制平移逻辑。
    window.__adjustKpRangesAfterSpanReplace = adjustKpRangesAfterSpanReplace;

    /** 找出“吸收新行”的 KP：覆盖 line，且光标不在该 KP 末行的行尾（行尾换行视为区域外）。 */
    function findAbsorbKp(line, offset, textLen) {
      for (const k of _kpList()) {
        const s = _kpStart(k);
        const e = _kpEnd(k);
        if (s <= line && line <= e) {
          if (e === line && offset >= textLen) continue;
          return k.id;
        }
      }
      return null;
    }

    /** 行前插空行时：若空行落在 KP 区域内部（start < line <= end）则该 KP 吸收（终点+1）。 */
    function findAbsorbKpBefore(line) {
      for (const k of _kpList()) {
        const s = _kpStart(k);
        const e = _kpEnd(k);
        if (s < line && line <= e) return k.id;
      }
      return null;
    }

    /** 定点同步：KP 列表行号文本 + 重绘当前 hover 高亮（沿用最新行号）。 */
    function refreshKpRangeUi() {
      const hoverId = state.hoveredKpId;
      let hoverItem = null;
      for (const k of _kpList()) {
        const item = document.querySelector(`.-kp-item[data-kp="${CSS.escape(k.id)}"]`);
        if (!item) continue;
        if (k.id === hoverId) hoverItem = item;
        const meta = item.querySelector(".-kp-meta span");
        if (!meta) continue;
        const r = _kpRr(k);
        if (r.ok) meta.textContent = `L${r.start_line}–${r.end_line}`;
        else if (k.range?.start?.line_hint) {
          const es = k.range?.end?.line_hint || k.range.start.line_hint;
          meta.textContent = `L${k.range.start.line_hint}–${es}`;
        }
      }
      if (hoverId && hoverItem && hoverItem.matches(":hover")) {
        highlightKpHover(hoverId);
      } else {
        state.hoveredKpId = null;
      }
    }

    // 源码编辑器：Backspace/Delete/Enter 行级操作
    editor.addEventListener("keydown", (e) => {
      const content = e.target.closest(".-line-content");
      if (!content) return;
      const lineEl = content.closest("[data-line]");
      if (!lineEl) return;
      const line = +(lineEl.dataset.line || 0);
      if (!line) return;

      // task-150：源码区 Ctrl+X —— **完全接管**（原生 cut 在跨 contenteditable 根选区上只删首根）。
      //   无选区时交还原生（不会删任何东西）；有选区时 preventDefault 阻止原生"写一半/删一半"。
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "x") {
        const cutPlan = _srcSelectionPlan();
        if (!cutPlan) return;
        e.preventDefault();
        _srcCutExecute(cutPlan).catch((err) => syncLog("srcCut: 异常 " + ((err && err.message) || err)));
        return;
      }

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
        adjustKpRangesAfterRemove(line); // M6b：删除当前行并并入上一行 → KP 范围收缩/顺延
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
        adjustKpRangesAfterRemove(line + 1); // M6b：行末 Delete 合并下一行 → KP 范围收缩/顺延
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
          newLineContent.contentEditable = !window.MemoriaEditHandler || window.MemoriaEditHandler.editMode ? "true" : "false";
          newLineContent.spellcheck = false;
          newLineContent.tabIndex = -1;
          newLineContent.innerHTML = "<br>";
          newLineEl.appendChild(newLineno);
          newLineEl.appendChild(newLineContent);
          lineEl.before(newLineEl);
          renumberSourceLines(line);
          _srcAfterEdit();
          // M6b：标题行前插空行 → 区域内吸收(终点+1)/后续 KP 顺延
          adjustKpRangesAfterInsert(line, { before: true, absorbId: findAbsorbKpBefore(line) });
          // 光标留在新空行中
          const br = newLineContent.querySelector("br");
          if (br) {
            const range = document.createRange();
            range.setStartBefore(br);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
          }
          // E26：新行进入视口（连续回车不把光标留在视口外）
          _keepSrcCaretVisible(newLineContent);
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
        newLineContent.contentEditable = !window.MemoriaEditHandler || window.MemoriaEditHandler.editMode ? "true" : "false";
        newLineContent.spellcheck = false;
        newLineContent.tabIndex = -1;
        newLineContent.textContent = after;
        if (!after) newLineContent.innerHTML = "<br>";
        newLineEl.appendChild(newLineno);
        newLineEl.appendChild(newLineContent);
        lineEl.after(newLineEl);
        renumberSourceLines(newNum + 1);
        _srcAfterEdit();
        // M6b：区域内换行 → 该 KP 吸收新行（终点+1）；后续 KP 顺延
        const absorbId = findAbsorbKp(line, offset, text.length);
        adjustKpRangesAfterInsert(line, { before: false, absorbId });
        // 光标移到新行开头
        const range = document.createRange();
        const firstText = newLineContent.firstChild;
        if (firstText) {
          range.setStart(firstText, firstText.nodeType === Node.TEXT_NODE ? 0 : 0);
          range.collapse(true);
          sel.removeAllRanges();
          sel.addRange(range);
        }
        // E26：回车后新行/光标必须进入视口
        _keepSrcCaretVisible(newLineContent);
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
      // E25：剪贴板里有图片 ⇒ 先走图片链。**只有确有图片时**才 preventDefault，
      // 纯文本粘贴完全走下面原有路径（原实现会先把图片当成空 text/plain 吞掉）。
      const imgs = clipboardImageFiles(e);
      if (imgs.length) {
        if (!editor.contains(t)) return;   // 不在源码编辑器内 ⇒ 不拦截
        e.preventDefault();
        insertClipboardImages(imgs, 0);
        return;
      }
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
        newLineContent.contentEditable = !window.MemoriaEditHandler || window.MemoriaEditHandler.editMode ? "true" : "false";
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
      // E26：多行粘贴后光标可能已在视口外
      if (cur) _keepSrcCaretVisible(cur);
      scheduleRenderSync();
      markDirty();
    }

    /** 右键「粘贴」：读剪贴板后复用 applyEditorPaste（合成 ClipboardEvent 的 clipboardData 只读，不可伪造） */
    async function pasteAtSourceEditor() {
      let text = "";
      try {
        text = (await readClipboardText()) || "";
      } catch (_) {
        text = "";
      }
      if (!text) {
        setStatus(T("cfg.clip.empty"));
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
        setStatus(T("cfg.clip.needCursor"));
        return;
      }
      applyEditorPaste(text, content);
    }

    // 源码编辑器右键：无选中文本 → 提供「粘贴」「插入图片」菜单
    // （全局捕获阶段已屏蔽原生右键菜单；有选区时交还 bindEditorSelectionMenu 弹链接/知识点菜单）
    editor.addEventListener("contextmenu", (e) => {
      if (!state.currentPath) return;
      // 编辑模式关闭（只读）：源码区不弹粘贴等编辑菜单
      if (window.MemoriaEditHandler && !window.MemoriaEditHandler.editMode) return;
      if (!(e.target && e.target.closest && e.target.closest(".-line-content"))) return;
      const info = getSelectionInContainer(editor);
      if (info) return;
      e.preventDefault();
      const row = e.target.closest(".-line");
      const srcLine = row ? +(row.dataset.line || 0) : 0;
      MemoriaLinkContextMenu.showForCursor(e, {
        onPaste: pasteAtSourceEditor,
        onInsertImage: () => window.MemoriaImageTools?.startInsertImage?.(srcLine || undefined),
      });
    });

    // IME 组合输入期间：input 事件不单独入栈，组合整体由 compositionend 后的状态兜底
    editor.addEventListener("compositionstart", () => { _srcComposing = true; });
    editor.addEventListener("compositionend", () => {
      _srcComposing = false;
      // E26：组合**期间**绝不滚（否则拼音候选阶段光标会跳）；提交后的这一拍才补一次。
      // 用 rAF 等浏览器把刚提交的字排进布局，避免用旧几何判断"是否可见"。
      requestAnimationFrame(() => {
        const sel = window.getSelection();
        if (!sel || !sel.rangeCount) return;
        const an = sel.anchorNode;
        const el = an && (an.nodeType === 3 ? an.parentElement : an);
        const content = el && el.closest ? el.closest(".-line-content") : null;
        if (content && editor.contains(content)) _keepSrcCaretVisible(content);
      });
    });

    // 源码区选区（键盘 Shift+方向键 / 鼠标跨行拖拽 / 双击整行）→ js/sel-source.js
    // 显式注入宿主能力，模块不读本文件闭包私有符号（见 docs/conventions/frontend-modules.md R2）
    if (window.MemoriaSelSource) {
      window.MemoriaSelSource.init({
        editor: editor,
        closestLineEl: closestLineEl,
        offsetWithinLine: offsetWithinLine,
      });
    }
  }

  // ═══════════════════════════════════════════════════════════
  //  PREVIEW EDITING — AST-based, built feature by feature
  // ═══════════════════════════════════════════════════════════

  // ── Logging ──
  const MAP_LOG = true;
  let _logBuf = [];
  let _logTimer = null;
  // 2026-09-22 修：调试浮窗日志原先写 `mapping-debug.log` / `undo-debug.log` 到**知识库根目录**
  // （`write_map_log` 按 `kb_path + rel_path` 落盘）⇒ 真机库根被 1000+ 行 debug 文件污染
  // （每个库都躺着一份，还不属于"检查"范围、也不是 `.md` ⇒ agent 的工具删不掉）。
  // 改落 `.memoria/cache/`（AGENTS.md §1：`.memoria/cache/**` 是**可再生缓存**、不作事实源）⇒
  // 调试能力不变，但库根干净。目录由 `write_map_log` 自行 `makedirs`。
  const LOG_FILE = ".memoria/cache/mapping-debug.log";

  function ts() { const d = new Date(); return "[" + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + ":" + String(d.getSeconds()).padStart(2, "0") + "." + String(d.getMilliseconds()).padStart(3, "0") + "]"; }
  function log(tag, msg) { if (!MAP_LOG) return; const l = ts() + " [" + tag + "] " + msg; console.log(l); _logBuf.push(l); _scheduleFlush(); }
  function _scheduleFlush() { if (_logTimer) clearTimeout(_logTimer); _logTimer = setTimeout(_flushNow, 300); }
  function _flushNow() { if (_logTimer) { clearTimeout(_logTimer); _logTimer = null; } if (!_logBuf.length) return; const c = _logBuf.join("\n") + "\n"; _logBuf = []; call("write_map_log", LOG_FILE, c).catch(function () { }); }
  window.addEventListener("beforeunload", function () { _flushNow(); try { call("flush_durable"); } catch (e) { /* ignore */ } });
  window.log = log;  // 导出给 edit-handler.js 等外部模块使用

  // ── AST pipeline shortcuts ──
  const L = window.MemoriaLexer;
  const P = window.MemoriaParser;
  const G = window.MemoriaSourceGen;
  const M = window.MemoriaMapper;
  const A = window.MemoriaAST;

  // ── Current AST document ──
  let _doc = null;

  // ── P6a：预览整篇渲染内核（render-core）──────────────────────────────────
  // 单向门：`renderPreview` 的 29 个调用点一字不动，只换内部实现。
  // 渲染器单例：render-core 的 createRenderCore 无状态，复用实例只省一次闭包创建。
  // P6d：legacy `renderer.js` 已删除；整篇 / 块级增量（renderBlock/renderRange）全部走 render-core。
  let _rcCore = null;
  function _rcRenderer() {
    const rc = window.MemoriaRenderCore;
    if (!rc || typeof rc.createRenderCore !== "function") return null;
    if (!_rcCore) _rcCore = rc.createRenderCore({});
    return _rcCore;
  }

  // ════ 2026-10-22 阶段1a：惰性块物化（占位 + 首屏物化）════════════════════════
  // 目标：打开大文档时**不再一次性建全文 4001 块 DOM**（那是 style/layout 2.88s 的来源），
  //   而是先建全文**占位**（纯 AST 属性 + 高度估值，O(块数) 且不触发布局），
  //   再同步物化"视口 ×2 高度"的块。其余滚动靠近时物化（1b）。
  //
  // 开关：`_lazyMaterializeEnabled` —— 默认关；开了才走惰性路径。回退只需关掉它
  //   （renderPreview 的 `lazyOn` 分支即回到全量 renderDocument，行为与阶段1前一致）。

  /** 惰性物化的**小文档阈值**：块数低于此值走原全量渲染。
   *
   *  为什么需要它（2026-10-22 Lead 裁决）：
   *   ① 小文档本来打开就快（几十块），惰性化收益为零，却引入占位/锁高/解锁一层新状态；
   *   ② **冻结渲染等价基线用的是小文档** —— 走原路径才能保证对照有效；
   *   ③ 占位高度估值在短文档上更容易出错（样本少）。
   *  阈值 200：08 章 4001 块、03 章 2028 块都远超；典型 homework（几十块）远低于。 */
  var LAZY_MIN_BLOCKS = 200;

  /** 惰性物化总开关。**默认开**（2026-10-22 四项验收通过后裁决）。
   *
   *  优先级（高 → 低）：
   *   ① `window.__MEMORIA_LAZY`（boolean）—— **测试钩子**，显式设置**覆盖阈值**，
   *      让回归脚本既能测得大文档惰性、也能测得小文档全量（否则小文档测不到惰性分支）。
   *   ② `localStorage["memoria.perf.lazy"]` —— `"0"` 显式关、`"1"` 显式开；其它值/缺失 ⇒ 默认开。
   *   ③ 默认：块数 ≥ `LAZY_MIN_BLOCKS` 才惰性。
   *
   *  即：**默认开 = "大文档惰性 + 小文档全量"**，不是无条件开。 */
  function _lazyMaterializeEnabled(doc) {
    var nBlocks = (doc && doc.blocks) ? doc.blocks.length : 0;
    // ① 测试钩子：显式 boolean ⇒ 连阈值一起覆盖（这是给回归用的唯一通道）
    if (typeof window.__MEMORIA_LAZY === "boolean") return window.__MEMORIA_LAZY;
    // ② 持久开关：显式 "0" 关 / "1" 开
    try {
      var v = localStorage.getItem("memoria.perf.lazy");
      if (v === "0") return false;
      if (v === "1") return true;
    } catch (e) { /* 隐私模式 localStorage 不可用 ⇒ 忽略 */ }
    // ③ 默认开，但小文档走原全量路径
    return nBlocks >= LAZY_MIN_BLOCKS;
  }

  /** 数一个 AST 块里的公式数（**纯 AST，不读 DOM**）：块公式=1，行内公式=递归 inline 子树里 `math_inline` 的个数。
   *
   *  为什么要分开数：物化前块还是占位 div（无 `.-math` 子节点），DOM 侧数不到；
   *  只有 AST 能告诉你"这个块物化后会有几个公式" ⇒ 物化批次才能按**公式数**（而不是块数）封顶。
   *  复杂度 = 本块自身 inline 节点数（不是全文）⇒ 便宜。 */
  function _countProcMath(node) {
    if (!node) return 0;
    if (node.type === "math_inline") return 1;
    var n = 0;
    if (node.children) for (var i = 0; i < node.children.length; i++) n += _countProcMath(node.children[i]);
    if (node.items) for (var j = 0; j < node.items.length; j++) if (node.items[j]) n += _countProcMath(node.items[j]);
    return n;
  }
  function _countBlockFormulas(block) {
    if (!block) return 0;
    if (block.type === "math_block") return 1;
    if (block.type === "list") {
      var ln = 0;
      if (block.items) for (var i = 0; i < block.items.length; i++) if (block.items[i]) ln += _countProcMath(block.items[i]);
      return ln;
    }
    return _countProcMath(block);
  }

  // ── 2026-10-22（人追加约束）：占位度量**不许硬编码** ─────────────────────────────
  // 人：「不同字体 / 窗口大小 / UI 缩放 下视口能显示的内容量不同」。
  // 硬编码 16px/120/240/720 在换字体、UI 缩放(80~150%)、窗口尺寸变化时全部失效
  // ⇒ 占位高度估错 ⇒ 漂移变大、**上跳复发**（我们刚修到 0）。
  // 对策：每次渲染**量一次**实际度量（不是每块读），之后所有估值都用它。
  var _pvMetrics = null;   // { fs, lhPx, paneW } —— 每次渲染/每次 resize 重新量

  /** 用**已挂载**宿主实测行盒高度（`line-height: normal` / 比例值也能量出像素值）。
   *
   *  做法：向宿主临时插入一个 `.-src-block` 探测块，内容为 3 行文本；块用
   *  `position: fixed` 完全脱离文档流（不产生滚动条、不推动任何内容），`visibility: hidden`
   *  仍保留布局盒 ⇒ `getBoundingClientRect()` 可读。`margin/padding/border` 全强制 0，
   *  故「总高 ÷ 3」就是每行行盒高度（不做任何比例推测）。
   *
   *  为什么必须这样量：`getComputedStyle(el).lineHeight` 在 `line-height: normal` 时返回字符串
   *  `"normal"`，拿不到像素；而「1.5×fontSize」只是猜——本仓实测真值 22.4px、猜测值 24px，
   *  偏高 7.1%，在 4001 块上累加成整篇 +17.7k px。只有「量一个真的排过版的块」才准确。
   *
   *  @returns {{fs:number, lhPx:number}|null} 宿主未挂载 / 取不到布局盒时返回 null（由调用方兜底）。
   */
  function _probeBlockMetrics(host, fsHint) {
    if (!host || !host.isConnected || !host.appendChild) return null;
    var probe = null;
    try {
      probe = document.createElement("div");
      probe.className = "-src-block -pv-metrics-probe";
      probe.setAttribute("aria-hidden", "true");
      probe.style.cssText = "position:fixed;left:-99999px;top:0;width:auto;white-space:nowrap;" +
        "margin:0;padding:0;border:0;visibility:hidden;pointer-events:none;z-index:-1;";
      probe.appendChild(document.createTextNode("Mg"));
      probe.appendChild(document.createElement("br"));
      probe.appendChild(document.createTextNode("Mg"));
      probe.appendChild(document.createElement("br"));
      probe.appendChild(document.createTextNode("Mg"));
      host.appendChild(probe);
      var cs = getComputedStyle(probe);
      var fs = parseFloat(cs.fontSize) || parseFloat(fsHint) || 0;
      var lh = cs && cs.lineHeight;
      var lhPx = (lh && /px$/.test(lh)) ? (parseFloat(lh) || 0) : 0;
      if (!(lhPx > 0) && probe.getBoundingClientRect) {
        var h = probe.getBoundingClientRect().height;   // 3 行、零内外边距 ⇒ 每行 = 总高 / 3
        if (h > 0) lhPx = h / 3;
      }
      return { fs: fs, lhPx: lhPx };
    } catch (_) {
      return null;
    } finally {
      try { if (probe && probe.parentNode) probe.parentNode.removeChild(probe); } catch (__) {}
    }
  }

  /** 量「分类型」的排版度量（与 `_probeBlockMetrics` 同法、同样只插一次性探测块）。
   *
   *  为什么正文行高不够：`.-preview` 的 `line-height:1.6`（div/空行 = 22.4px），但
   *  **段落**吃的是 `theme/memoria.css` 的 `.markdown-body p { line-height:1.7 }`
   *  ⇒ 实测 23.8px（+6.3%）；标题按级缩放（h2 = 20px×1.6 = 32px）。W3.4 前占位用
   *  单一 `lhPx` 估所有类型，段落系统性偏低、标题偏高。
   *
   *  这里把「段落行高 / h1–h3 单行高 / 图片失败骨架的 caption 高」一次量出来，
   *  全部走真实已挂载宿主，因此换字体、UI 缩放、窗口尺寸都自动跟随，仍**无硬编码 px**。
   *  取不到布局盒 ⇒ 返回 null，由调用方退回既有比例兜底。
   *  @returns {{pLhPx:number, captionH:number, headingH:Object<number,number>}|null}
   */
  function _probeTypeMetrics(host) {
    if (!host || !host.isConnected || !host.appendChild) return null;
    var wrap = null;
    try {
      wrap = document.createElement("div");
      wrap.className = "-pv-type-probe";
      wrap.setAttribute("aria-hidden", "true");
      wrap.style.cssText = "position:fixed;left:-99999px;top:0;visibility:hidden;" +
        "pointer-events:none;z-index:-1;";
      function add(tag, cls, text) {
        var el = document.createElement(tag);
        el.className = "-src-block -pv-metrics-probe" + (cls ? " " + cls : "");
        el.style.margin = "0";
        el.style.padding = "0";
        el.style.border = "0";
        el.textContent = text || "Mg";
        wrap.appendChild(el);
        return el;
      }
      var pEl = add("p", "", "Mg");
      var h1 = add("h1", "", "Mg");
      var h2 = add("h2", "", "Mg");
      var h3 = add("h3", "", "Mg");
      // 图片失败骨架的 caption 必须放在 `.-image-block` 内才命中 `.-image-block .-image-caption`
      var imgProbe = document.createElement("p");
      imgProbe.className = "-src-block -pv-metrics-probe -image-block";
      imgProbe.style.cssText = "margin:0;padding:0;border:0;";
      var cap = document.createElement("span");
      cap.className = "-image-caption";
      cap.textContent = "图";
      imgProbe.appendChild(cap);
      wrap.appendChild(imgProbe);
      host.appendChild(wrap);
      var out = { pLhPx: 0, captionH: 0, captionGap: 0, headingH: {} };
      var pcs = getComputedStyle(pEl);
      if (pcs && pcs.lineHeight && /px$/.test(pcs.lineHeight)) out.pLhPx = parseFloat(pcs.lineHeight) || 0;
      if (!(out.pLhPx > 0) && pEl.getBoundingClientRect) out.pLhPx = pEl.getBoundingClientRect().height || 0;
      if (cap.getBoundingClientRect) out.captionH = cap.getBoundingClientRect().height || 0;
      try {
        var ccs = getComputedStyle(cap);
        if (ccs && ccs.marginTop) out.captionGap = parseFloat(ccs.marginTop) || 0;
      } catch (_) {}
      var hs = [h1, h2, h3];
      for (var i = 0; i < hs.length; i++) {
        var hr = hs[i].getBoundingClientRect ? hs[i].getBoundingClientRect() : null;
        if (hr && hr.height > 0) out.headingH[i + 1] = Math.round(hr.height * 100) / 100;
      }
      return out;
    } catch (_) {
      return null;
    } finally {
      try { if (wrap && wrap.parentNode) wrap.parentNode.removeChild(wrap); } catch (__) {}
    }
  }

  /** 量一次预览区的真实排版度量。
   *
   *  **为什么必须量「已挂载」的块**：对 detached 元素调 `getComputedStyle` 拿到的是 initial 值
   *  （font-size 16px / line-height normal），不是页面实际 CSS ⇒ 旧实现回退 24px。
   *  所以本函数要求 `container`（或其宿主 `#preview`）已挂进文档；未挂载时也**绝不猜比例**，
   *  而是用已挂载的宿主插探测块实测（见 `_probeBlockMetrics`）。
   *
   *  **为什么要量"块"而不是量 `#preview-pane`**：`#preview-pane` 的行高是 `normal`，
   *  真正生效的行高在 `.‑preview-content` 的块上（`p`/`li`/`.‑src-block`）。
   *  只按 `fontSize` 推也不行：`18px/1.2` 与 `16px/1.5` 的**行高可能相同**，必须看解析后的像素值。
   */
  function _measurePreviewMetrics(pane, container) {
    var fs = 0, lhPx = 0, paneW = 800, src = "none", pLhPx = 0, captionH = 0, captionGap = 0, headingH = {};
    try {
      // 宿主解析顺序：已挂载的 container → 已挂载的 #preview（仍是 `.-preview` 祖先）
      //   → pane（最后手段）。detached container 永不作为测量宿主。
      var host = (container && container.isConnected) ? container : null;
      if (!host) {
        var pv = document.getElementById("preview");
        if (pv && pv.isConnected) host = pv;
        else if (pane && pane.isConnected) host = pane;
      }
      // ① **优先用已挂载宿主上的探测块实测**：它与正文同源（`.‑preview .‑src-block`），
      //   且 `line-height: normal` / 比例值也能读出像素；`src=probe`。
      //   ⚠️ 刻意**不优先**取「第一个已物化真块」：真块可能是 `h1/h2/...` 标题块
      //   （本仓实测标题 font-size=20.006px / line-height=32.01px），拿它当正文行高会把
      //   占位高度整体放大 43%——resize 重算时尤其明显（首块常是章标题）。
      var mp = _probeBlockMetrics(host, 0);
      if (mp) {
        if (mp.fs > 0) fs = mp.fs;
        if (mp.lhPx > 0) { lhPx = mp.lhPx; src = "probe"; }
      }
      // ①b 分类型度量（段落行高 / 标题单行高 / caption 高）：同样用已挂载宿主探针。
      //    失败不影响主流程（后面按比例兜底）。
      var mt = _probeTypeMetrics(host);
      if (mt) {
        if (mt.pLhPx > 0) pLhPx = mt.pLhPx;
        if (mt.captionH > 0) captionH = mt.captionH;
        if (mt.captionGap > 0) captionGap = mt.captionGap;
        if (mt.headingH) headingH = mt.headingH;
      }
      // ② 探测块取不到（宿主不可用/零布局）⇒ 退回**正文型**真块的 computed style，
      //   显式排除标题（h1~h6）；`line-height` 为 normal 时再实测。
      if (!(lhPx > 0)) {
        var real = (host && host.querySelector)
          ? host.querySelector(".-src-block:not(.-pv-placeholder):not(.-pv-metrics-probe):not(h1):not(h2):not(h3):not(h4):not(h5):not(h6)")
          : null;
        if (real) {
          var cs = getComputedStyle(real);
          if (!(fs > 0)) fs = parseFloat(cs.fontSize) || 0;
          var lh = cs.lineHeight;
          if (lh && /px$/.test(lh)) { lhPx = parseFloat(lh) || 0; if (lhPx > 0) src = "computed"; }
        }
      }
      if (!(fs > 0)) {
        var rootCs = getComputedStyle(document.documentElement);
        fs = parseFloat(rootCs.fontSize) || 16;
      }
      // ③ 连宿主布局都没有（如 DOM stub / 不可见窗口）才用 body 再试一次
      if (!(lhPx > 0)) {
        var mb = _probeBlockMetrics(document.body, fs);
        if (mb && mb.lhPx > 0) { lhPx = mb.lhPx; src = "probe-body"; }
      }
      // ④ 最后兜底：只在**完全拿不到布局**时发生。用 CSS 规范的比例 1.6（本仓 `.-preview` 的
      //    line-height 就是 1.6），仍好过旧实现的 1.5。
      if (!(lhPx > 0)) { lhPx = fs * 1.6; src = "fallback"; }
      if (pane && pane.clientWidth) paneW = pane.clientWidth;
    } catch (_) {
      fs = 16; lhPx = 0; paneW = 800;
    }
    if (!(fs > 0)) fs = 16;
    if (!(lhPx > 0)) { lhPx = fs * 1.6; src = "fallback"; }
    if (!(paneW > 0)) paneW = 800;
    // 分类型度量的兜底：段落行高按 CSS 规范 `.markdown-body p{line-height:1.7}`；
    // caption 按 `. -image-caption { font-size:.875rem; line-height:1.4 }`（rem 以根字号计）。
    if (!(pLhPx > 0)) pLhPx = fs * 1.7;
    if (!(captionH > 0)) {
      var rootFs = parseFloat(getComputedStyle(document.documentElement).fontSize) || fs;
      captionH = rootFs * 0.875 * 1.4;
      if (!(captionGap > 0)) captionGap = rootFs * 0.1875;
    }
    if (!(captionGap > 0)) captionGap = 3;
    // 文本可用宽度 = 内容容器宽度（不含 pane 左右 padding）。取不到再退回 paneW × 0.855
    // （本仓 624 → 534，实测容器宽/ pane 宽 = 0.856）。
    var availW = 0;
    try { if (container && container.isConnected && container.clientWidth > 0) availW = container.clientWidth; } catch (_) {}
    if (!(availW > 0)) availW = Math.round(paneW * 0.856);
    return { fs: fs, lhPx: lhPx, paneW: paneW, pLhPx: pLhPx, captionH: captionH,
             captionGap: captionGap, headingH: headingH, availW: availW, src: src };
  }
  /** 取当前度量（没有就按最保守默认造一份，保证任何时候都不崩）。
   *  默认值也只用于「还没渲染过」的瞬间；正常路径一定先走 `_measurePreviewMetrics`。 */
  function _pvM() {
    return _pvMetrics || { fs: 16, lhPx: 16 * 1.6, paneW: 800, pLhPx: 16 * 1.7,
                           captionH: 16 * 0.875 * 1.4, captionGap: 3, headingH: {},
                           availW: 800 * 0.856, src: "default" };
  }

  // ── W3.4（2026-10-23）：占位高度的「分类型实测标定」 ─────────────────────────
  // 旧实现用单一 lhPx 估所有类型 ⇒ 实测（08 章 4001 块，全量 175,616px）：
  //   paragraph 49.63 vs 24.97（-49.7%，中文段落折行没算）、math 62.11 vs 113.85（+83%，
  //   块公式高度与**源码行数**几乎无关）、image 41.58 vs 351（+744%，9:16 假设遇到图片
  //   未加载/加载失败时完全失真）、mermaid 211.6 vs 450（+113%）。逐类型错互相抵消后
  //   整篇仍 +3.41%。这里按实测重标：段落按「文本视觉宽度 ÷ 可用宽度」估折行；公式按
  //   公式长度（与渲染高度实测相关 0.74）；图片未加载/失败走骨架高度，加载成功后回写
  //   真实宽高比（见 `_pvWatchImage`）。
  /** 图片 URL → {ok:true,nw,nh} | {ok:false}。内存级缓存：内容寻址的 `.memoria/images/*`
   *  文件名本身就是内容哈希（不可变），故无需失效；仅用于占位阶段判断失败/真实宽高比。 */
  var _pvImgSizes = (typeof Map === "function") ? new Map() : null;

  /** 单个字符的视觉宽度（em）。用于「段落折行数」估算：CJK/全角≈0.95em、ASCII≈0.6em、
   *  空白 0.3em、标点 0.35em。系数由 08 章 1398 段实测标定（行数命中 94.3%）。 */
  function _chEmWidth(ch) {
    var o = ch.charCodeAt(0);
    if (o >= 0x2E80) return 0.95;
    if (ch === " " || ch === "\t") return 0.3;
    if (".,;:!?'\"()[]{}<>|/\\-—–".indexOf(ch) >= 0) return 0.35;
    return 0.6;
  }
  function _textEmWidth(s) {
    var em = 0;
    for (var i = 0; i < s.length; i++) em += _chEmWidth(s.charAt(i));
    return em;
  }
  /** inline AST 的视觉宽度（em）。行内公式/图片按经验宽度计（文本串里它们只有很短的字面）。 */
  function _inlineEmWidth(nodes) {
    if (!nodes || !nodes.length) return 0;
    var em = 0;
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (!n) continue;
      switch (n.type) {
        case "text": em += _textEmWidth(String(n.content == null ? "" : n.content)); break;
        case "escape": em += 0.6; break;
        case "math_inline":
          em += Math.max(1.2, 0.55 * String(n.formula == null ? (n.content || "") : n.formula).length);
          break;
        case "code": em += 0.6 * String(n.content == null ? (n.value || "") : n.content).length; break;
        case "image": em += 2; break;
        case "wiki_link":
          em += _inlineEmWidth(n.children) || (0.6 * String(n.target == null ? "" : n.target).length);
          break;
        default:
          if (n.children) em += _inlineEmWidth(n.children);
          else if (n.content) em += _textEmWidth(String(n.content));
      }
    }
    return em;
  }
  /** 段落折行数 = ceil(视觉宽度 × 字号 ÷ 可用宽度)。 */
  function _wrappedLines(block) {
    var m = _pvM();
    var em = _inlineEmWidth(block && block.children);
    if (!(em > 0)) return 1;
    var avail = m.availW > 0 ? m.availW : m.paneW * 0.856;
    if (!(avail > 0)) avail = 480;
    return Math.max(1, Math.ceil((em * m.fs) / avail));
  }
  /** 图片块在「未加载 / 加载失败」时的骨架高度：broken-img 行盒 + caption（含上边距）。
   *  08 章实测 46.39px（53 张图的真值中位），本式给 pLh(23.8)+caption(17.15)+gap(3)=43.95px
   *  （-5%，整篇影响 <0.1%）；成功加载后由 `_pvWatchImage` 回写真实宽高比。 */
  function _pvImageFallbackH() {
    var m = _pvM();
    var lineH = m.pLhPx > 0 ? m.pLhPx : m.lhPx;
    var cap = m.captionH > 0 ? m.captionH : m.fs * 0.875 * 1.4;
    var gap = m.captionGap > 0 ? m.captionGap : 3;
    return lineH + gap + cap;
  }
  /** 图片块估值：已知真实宽高比 ⇒ 按显示宽度（≤可用宽）算；未知/失败 ⇒ 骨架高度。 */
  function _pvImageHeight(block) {
    var m = _pvM();
    var url = block && block.url ? String(block.url) : "";
    var rec = (url && _pvImgSizes) ? _pvImgSizes.get(url) : null;
    if (rec && rec.ok && rec.nw > 0 && rec.nh > 0) {
      var avail = m.availW > 0 ? m.availW : m.paneW * 0.856;
      var w = Math.min(avail > 0 ? avail : m.paneW, rec.nw);
      var cap = m.captionH > 0 ? m.captionH : m.fs * 0.875 * 1.4;
      var gap = m.captionGap > 0 ? m.captionGap : 3;
      return (w * rec.nh) / rec.nw + gap + cap;
    }
    return _pvImageFallbackH();
  }
  /** 记录物化图片的真实结果（load/error 各一次）。只写缓存，不改已存在真块的高度：
   *  图片加载完成后浏览器自然会撑开块（与全量渲染同一行为），占位阶段则用缓存估下一次。 */
  function _pvWatchImage(real) {
    if (!real || !real.querySelector || !_pvImgSizes) return;
    if (!(real.classList && real.classList.contains("-image-block"))) return;
    var im = real.querySelector("img");
    if (!im) return;
    var url = im.getAttribute("src") || "";
    if (!url || _pvImgSizes.has(url)) return;
    var settled = false;
    function record() {
      if (settled) return;
      settled = true;
      try {
        if (im.naturalWidth > 0 && im.naturalHeight > 0) {
          if (_pvImgSizes.size > 4000) _pvImgSizes.clear();   // 会话级防无限增长（单库图片通常 <1500）
          _pvImgSizes.set(url, { ok: true, nw: im.naturalWidth, nh: im.naturalHeight });
        } else if (im.complete) {
          _pvImgSizes.set(url, { ok: false });
        }
      } catch (_) {}
    }
    try {
      if (im.complete) { record(); return; }
      im.addEventListener("load", record);
      im.addEventListener("error", record);
    } catch (_) {}
  }

  /** 按块类型估算占位高度（纯 AST + 实测度量；**无硬编码 px**）。
   *  W3.4：逐类型按实测标定；未知类型仍沿用旧的保守式（宁大勿小只在无证据时成立）。 */
  function _placeholderHeight(block) {
    var m = _pvM(), lh = m.lhPx;
    if (!block) return lh;
    var lines = Math.max(1, (block.srcLineEnd - block.srcLine + 1) || 1);
    switch (block.type) {
      case "blank_line":
        // 空行块自身 = 1 行（22.4px）；MathJax 公式的上下 1em 外边距记在公式块上（见下），
        // 不再靠把空行统一放大约 19% 来吸收（那会在纯文本文档里系统性偏高）。
        return lh;
      case "heading": {
        var lvl = Math.max(1, Math.min(6, block.level || 2));
        var hh = m.headingH && m.headingH[lvl];
        if (hh > 0) return hh;
        var scale = [0, 1.857, 1.429, 1.143, 1, 1, 1][lvl] || 1;
        return m.fs * scale * 1.6;
      }
      case "paragraph": {
        var pLh = m.pLhPx > 0 ? m.pLhPx : lh;
        return _wrappedLines(block) * pLh;
      }
      case "math_block": {
        // 块公式：高度与「源码行数」基本无关（本仓全部 3 行）。按 08 章 567 个公式实测
        // （真实布局贡献 = 渲染高 + **下** 1em 外边距）：h ≈ 24.76 + 0.1595×公式源长度
        // （相关 0.83；旧口径用渲染后 textContent 长度时为 0.74）。上 1em 外边距在布局里塌陷到**前一个空行块**上 ⇒ 记到空行
        // （见 `_pvBlockH`），不在这里重复计。
        var flen = block.formula != null ? String(block.formula).length : lines * 10;
        var est = lh * (1.105 + 0.0071 * flen);
        return Math.min(est, Math.max(lh * 3, m.availW || m.paneW) * 8);   // 防御性上限
      }
      case "code_block": {
        // parser 把所有围栏都产 `code_block`（`lang` 区分）；mermaid 围栏在预览里会被
        // 替换成 `.-mermaid-container`，真实高度≈源码行数×10px（08 章 402 源行→4021px），
        // 与普通代码块（等宽行）完全不同 ⇒ 必须按 lang 分流。
        if (block.lang && String(block.lang).toLowerCase() === "mermaid") {
          return Math.max(4 * lh, lines * lh * 0.45);
        }
        return lines * lh * 0.95;
      }
      case "table": return lines * lh * 1.5;          // 实测 33.4px/源行 = 1.49×lh（08 章 33 表）
      case "mermaid": return Math.max(4 * lh, lines * lh * 0.45);   // 实测 402 源行 → 4021px
      case "image": return _pvImageHeight(block);
      case "horizontal_rule": return lh * 1.3;
      default: return lines * lh * 1.05;
    }
  }

  /** MathJax 行间公式的 1em 外边距（上/下各一）。08 章实测 14px（= 1em @14px）。 */
  function _pvMathMarginH() {
    var m = _pvM();
    return m.fs > 0 ? m.fs : 14;
  }

  /** 带**邻居上下文**的占位高度：公式的 1em 上外边距在布局里会塌陷到前一个空行块，
   *  故「空行 + 下一块是公式」要额外加这一行外边距（否则空行会系统性偏低、公式偏高）。 */
  function _pvBlockH(doc, idx) {
    var blocks = doc && doc.blocks;
    if (!blocks || idx < 0 || idx >= blocks.length) return _pvM().lhPx;
    var block = blocks[idx];
    var h = _placeholderHeight(block);
    var nx = blocks[idx + 1];
    if (block && block.type === "blank_line" && nx && nx.type === "math_block") {
      h += _pvMathMarginH();
    }
    return h;
  }

  /** 清掉一批**即将离开文档 / 已被换出**的元素内部的 MathJax 记录。
   *
   *  2026-10-22 task-70（堆泄漏根治）：MathJax v3 的 `document.math`（`MathList`）会**一直持有**
   *  每个已排版 `MathItem`（`start.node` / `typesetRoot` 就是 `mjx-container`）。工作集淘汰只做
   *  `real.replaceWith(placeholder)` ⇒ MathItem 仍把整棵 detached SVG 子树钉在堆上 ⇒ 滚一趟 08 章
   *  堆从 17.9MB 涨到 85.1MB、`document.math` 16 → 2317 条（实测全是 `isConnected=false`）。
   *  `MathJax.typesetClear([el])` 是官方清理入口：按 `start.node` 包含关系把这棵子树里的
   *  MathItem 从 `MathList` 移除（已实测单块 75→74 条生效）；**不删除 DOM**、不影响仍在文档里的公式。
   *  ⚠️ 必须在元素仍保有子树时调用：换出后 `real` 仍含 `mjx-container`，故 `replaceWith` 之后调用同样成立；
   *  但**不能**先 `real.remove()` 再清。 */
  function _clearMathJaxWithin(els) {
    if (!els) return 0;
    var MJ = window.MathJax;
    if (!MJ || typeof MJ.typesetClear !== "function") return 0;
    var list = Array.isArray(els) ? els : [els];
    var live = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (el && el.querySelector) live.push(el);
    }
    if (!live.length) return 0;
    try {
      MJ.typesetClear(live);
      if (_evProf) {
        var _p0 = _evNow();
        _purgeDetachedMathItems();
        _evProf.purgeMs += _evNow() - _p0;
      } else {
        _purgeDetachedMathItems();
      }
      return live.length;
    } catch (e) {
      log("lazy", "math clear ERR " + ((e && e.message) || e));
      return 0;
    }
  }

  /** 兜底：清掉 `document.math` 里**已经脱离文档**的 MathItem。
   *
   *  `typesetClear([el])` 只按传入元素做包含匹配；换文档/缓存搬回时，旧文档可能已经整体被替换，
   *  这些 item 的 `typesetRoot` 早已 `isConnected=false`，却仍留在 `MathList` 里。
   *  这里只删 `typesetRoot` 已脱离文档的条目 —— 不碰仍挂着的公式，也不会误清可见内容。
   *  与 `typesetClear` 共用 MathJax 官方 `MathList.remove()`（内部 API，但 typesetClear 自身也走它）。 */
  function _purgeDetachedMathItems() {
    var MJ = window.MathJax;
    var doc = MJ && MJ.startup && MJ.startup.document;
    if (!doc || !doc.math || typeof doc.math.remove !== "function") return 0;
    var stale = [];
    try {
      for (var it of doc.math) {
        var tr = it && it.typesetRoot;
        if (!tr || !tr.isConnected) stale.push(it);
      }
    } catch (_) { return 0; }
    if (!stale.length) return 0;
    // ⚠️ 2026-10-22 task-76：`MathList.remove(...items)` 是**变参**签名（`clearMathItemsWithin`
    //   自己也用 `remove.apply(e, items)`）。原先写 `remove(stale)`（传数组）实测是**静默 no-op**：
    //   `document.math` 4455 条时 `remove([it])` 前后条数不变，`remove(...items)` 才下降。
    //   ⇒ 这个"兜底"此前从未生效；快拖时"typeset 在块被换出后才完成"产生的新 MathItem 只能靠这里清，
    //   结果全部留下（实测 3 遍快拖 21MB → 130MB）。变参不能一次上千个（栈风险）⇒ 每 500 条一批。
    try {
      for (var _pi = 0; _pi < stale.length; _pi += 500) {
        doc.math.remove.apply(doc.math, stale.slice(_pi, _pi + 500));
      }
    } catch (_) { return 0; }
    return stale.length;
  }

  // ════ 2026-10-23 task-72：**块级排版缓存（MathJax typeset 结果复用）** ════════════
  //
  // 问题（W3.2 收口实测，成因已定位）：
  //   · 45% 位置：单个 300 字矩阵 math_block 一次 typeset 40–60ms（按公式数切批切不动：math_block 恒计 1）；
  //   · 70%/90%：向上"到达即冷启动"，一窗内 typeset 65–75ms（下行只要 15–30ms）。
  //   ⇒ 换出再进入视口的块**每次都重新 typeset**，而内容完全没变。
  //
  // 做法：把 **mjx-container 的 outerHTML**（纯字符串，不是 DOM 节点）按
  //   `fontSize | display | formula` 为键缓存；重新物化时直接写回 `innerHTML`，跳过 typeset。
  //   选"字符串"而不是"DOM clone"是**内存与泄漏两方面的硬约束**：
  //     ① 字符串不持有 DOM 节点、不持有 MathJax 内部对象（MathItem/MathList）
  //        ⇒ 不会像 task-70 之前那样把 detached 的 MathItem 钉在堆上；
  //     ② 缓存**从不注册**到 `document.math`；换出时仍走既有 `_clearMathJaxWithin` /
  //        `_purgeDetachedMathItems`，原 MathItem 照常被清掉 ⇒ detached 恒 0。
  //   反过来说：**绝不能缓存 MathItem 或仍带着 MathItem 引用的活动 DOM**，否则泄漏复活。
  //
  // 上限与开关（硬性验收）：
  //   · 条数 ≤ `TS_MAX_ENTRIES`（默认 1024）、字符 ≤ `TS_MAX_CHARS`（默认 8M），超出按插入序 FIFO 逐出；
  //   · `window.__MEMORIA_TYPESET_CACHE === false` ⇒ 完全旁路（store/apply 都不做），行为与旧实现逐字节一致；
  //   · 换文档（`state.doc.path` 变化）⇒ 整表清空（缓存只对同一篇文档有效，也避免跨文档的公式编号串味）。
  //
  // 容量标定（2026-10-23 实测 08 章 4001 块、全量 down 一遍）：**827 条 / 7,066,821 字符**。
  //   取 1024/8M ⇒ 整章可容纳，向上第二遍**零逐出**。这不是拍脑袋放大：实测 2.5M 上限时
  //   恰好把文档**顶部**的公式逐出（FIFO），而向上第二遍最后到达的正是顶部 ⇒ 5%/20% 位置
  //   重新冷启动（20% 的 up/down 比值 1.188，已贴 1.2 红线）。缓存必须是**有界**的，
  //   但不能小到只能装半章 —— 否则本次要治的"70%/90% 到达即冷启动"会在另一端复现。
  //   真实字节量由 `__MEMORIA_TYPESET_CACHE_STATS().chars` 如实暴露；`Runtime.getHeapUsage`
  //   的 usedSize 不含长字符串内容（实测 5M 字符只 +0.45MB），heap 口径仍稳定在 21–22MB。
  var TS_MAX_ENTRIES = 1024;
  var TS_MAX_CHARS = 8000000;
  var _tsCache = (typeof Map === "function") ? new Map() : null;
  var _tsChars = 0;
  var _tsDocKey = null;
  var _tsRestoreSeq = 0;
  var _tsRestoredEls = (typeof WeakSet === "function") ? new WeakSet() : null;   // 已完整复用、无需再排版的块
  var _tsStats = { enabled: true, stores: 0, hits: 0, misses: 0, evictions: 0,
                   skipped: 0, restoreMs: 0, storeMs: 0, entries: 0, chars: 0 };

  /** 运行时开关：默认开；`window.__MEMORIA_TYPESET_CACHE === false` 时完全旁路（同一 build A/B 用）。 */
  function _tsEnabled() {
    if (!_tsCache) return false;
    return window.__MEMORIA_TYPESET_CACHE !== false;
  }
  function _tsMaxEntries() {
    var v = window.__MEMORIA_TYPESET_CACHE_MAX_ENTRIES;
    return (typeof v === "number" && v >= 0) ? v : TS_MAX_ENTRIES;
  }
  function _tsMaxChars() {
    var v = window.__MEMORIA_TYPESET_CACHE_MAX_CHARS;
    return (typeof v === "number" && v >= 0) ? v : TS_MAX_CHARS;
  }

  /** 换文档 ⇒ 清空（同文档内编辑不失效：键是公式原文，改过的公式自然不会命中）。 */
  function _tsSyncDoc() {
    var p = (state && state.doc && state.doc.path) ? String(state.doc.path) : "";
    if (p !== _tsDocKey) {
      _tsCache.clear(); _tsChars = 0; _tsDocKey = p;
      _tsStats.hits = 0; _tsStats.misses = 0; _tsStats.stores = 0; _tsStats.evictions = 0;
      _tsStats.skipped = 0; _tsStats.restoreMs = 0; _tsStats.storeMs = 0;
    }
  }

  /** 一个块里"会被 MathJax 排版的公式"列表（**DOM 文档序**；与 render-core 的渲染顺序一致）。
   *  `math_block` ⇒ 单条 display 公式；其它块 ⇒ 递归收集 `math_inline`。
   *  ⚠️ 只用于"数量对得上才缓存"：表格单元格里的 `$…$` 由文本二次解析，AST 里看不到 ⇒
   *  数量必然对不上 ⇒ 自动跳过（宁可少缓存，不可错配公式）。 */
  function _tsFormulasOf(block) {
    if (!block) return [];
    if (block.type === "math_block") {
      return [{ f: String(block.formula == null ? "" : block.formula), d: true }];
    }
    var out = [];
    function walk(n) {
      if (!n) return;
      if (n.type === "math_inline") {
        out.push({ f: String(n.formula == null ? (n.content || "") : n.formula), d: false });
        return;
      }
      if (n.children) for (var i = 0; i < n.children.length; i++) walk(n.children[i]);
      if (n.items) {
        for (var j = 0; j < n.items.length; j++) {
          var it = n.items[j];
          if (it && it.children) for (var k = 0; k < it.children.length; k++) walk(it.children[k]);
        }
      }
    }
    walk(block);
    return out;
  }

  function _tsKey(item) {
    var fs = Math.round((_pvM().fs || 0) * 100) / 100;
    return (item.d ? "D" : "I") + "|" + fs + "|" + item.f;
  }

  function _tsPut(key, html) {
    if (!html || _tsCache.has(key)) return false;
    _tsCache.set(key, html);
    _tsChars += html.length;
    var maxE = _tsMaxEntries(), maxC = _tsMaxChars();
    while ((_tsCache.size > maxE || _tsChars > maxC) && _tsCache.size > 1) {
      var k0 = _tsCache.keys().next().value;
      var v0 = _tsCache.get(k0);
      _tsCache.delete(k0);
      _tsChars -= (v0 ? v0.length : 0);
      _tsStats.evictions++;
    }
    _tsStats.stores++;
    return true;
  }

  /** 给缓存串里的 SVG `id="MJX-<n>-…"` 换成本次复用的唯一前缀。
   *  原因：MathJax 的 id 是**文档级递增**的（`fontCache: local` 下每个容器自带 `<defs>`）；
   *  同一公式在视口里出现两次时若沿用原 id 会产生重复 id。换前缀后每个容器自洽。
   *  只改前缀（`MJX-<n>-` 在 id 与 `xlink:href` 里同形出现），不动 `<use>`/`<path>` 的引用关系。 */
  function _tsRewriteIds(html) {
    _tsRestoreSeq++;
    var p = "MJXT72-" + _tsRestoreSeq + "-";
    return html.replace(/MJX-\d+-/g, p);
  }

  /** 缓存一批**刚 typeset 完成**的块。只在块仍 connected 时调用（换出的块不再序列化）。 */
  function _tsStoreEls(els) {
    if (!_tsEnabled() || !els || !els.length) return 0;
    _tsSyncDoc();
    var t0 = _evProf ? _evNow() : 0;
    var n = 0;
    var blocks = _doc && _doc.blocks ? _doc.blocks : null;
    if (!blocks) return 0;
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (!el || !el.isConnected || !el.getAttribute) continue;
      var idx = parseInt(el.getAttribute("data--block-index"), 10);
      if (isNaN(idx) || idx < 0 || idx >= blocks.length) continue;
      var spec = _tsFormulasOf(blocks[idx]);
      if (!spec.length) continue;
      var cs = el.querySelectorAll("mjx-container");
      if (cs.length !== spec.length) { _tsStats.skipped++; continue; }   // 对不上 ⇒ 不猜
      for (var j = 0; j < spec.length; j++) {
        var key = _tsKey(spec[j]);
        if (_tsCache.has(key)) continue;
        var html = "";
        try { html = cs[j].outerHTML || ""; } catch (_) {}
        if (html && _tsPut(key, html)) n++;
      }
    }
    if (_evProf && t0) _tsStats.storeMs += _evNow() - t0;
    _tsStats.entries = _tsCache.size; _tsStats.chars = _tsChars;
    return n;
  }

  /** 扫描一个容器（preview / 某批块）里所有已排版块并缓存（全量 typeset 收尾用）。 */
  function _tsStoreWithin(root) {
    if (!_tsEnabled() || !root || !root.querySelectorAll) return 0;
    var cs;
    try { cs = root.querySelectorAll("mjx-container"); } catch (_) { return 0; }
    if (!cs.length) return 0;
    var seen = [], seenSet = (typeof Set === "function") ? new Set() : null;
    for (var i = 0; i < cs.length; i++) {
      var b = null;
      try { b = cs[i].closest ? cs[i].closest(".-src-block") : null; } catch (_) {}
      if (!b) continue;
      if (seenSet) { if (seenSet.has(b)) continue; seenSet.add(b); }
      seen.push(b);
    }
    return _tsStoreEls(seen);
  }

  /** 把缓存产物写回一个**刚 renderBlock 出来、尚未插入文档**的块。
   *  @returns {boolean} true = 该块所有公式都命中（调用方据此跳过 typeset）。 */
  function _tsApplyBlock(el, block) {
    if (!_tsEnabled() || !el || !block) return false;
    var spec = _tsFormulasOf(block);
    if (!spec.length) return false;
    _tsSyncDoc();
    var t0 = _evProf ? _evNow() : 0;
    var ok = false, hitN = 0;
    try {
      if (block.type === "math_block") {
        var html = _tsCache.get(_tsKey(spec[0]));
        if (html) {
          el.innerHTML = _tsRewriteIds(html);
          var c0 = el.firstElementChild;
          if (c0 && c0.nodeName === "MJX-CONTAINER") c0.contentEditable = "false";
          ok = true; hitN = 1;
        }
      } else {
        var spans = el.querySelectorAll(".-math");
        if (spans.length === spec.length) {
          // 先全部取好再改，避免"改了一半才发现对不上"
          var htmls = new Array(spec.length), n = 0;
          for (var i = 0; i < spec.length; i++) {
            var h = _tsCache.get(_tsKey(spec[i]));
            htmls[i] = h || "";
            if (h) n++;
          }
          if (n) {
            for (var k = 0; k < spec.length; k++) {
              if (!htmls[k]) continue;
              spans[k].innerHTML = _tsRewriteIds(htmls[k]);
              var c = spans[k].firstElementChild;
              if (c && c.nodeName === "MJX-CONTAINER") {
                c.setAttribute("data--inline-math", "true");
                c.setAttribute("data-formula", spec[k].f);
                c.contentEditable = "false";
              }
            }
            hitN = n;
            ok = (n === spec.length);
          }
        }
      }
    } catch (e) {
      log("lazy", "typeset cache apply ERR " + ((e && e.message) || e));
      ok = false;
    }
    if (hitN) {
      _tsStats.hits += hitN;
      if (_tsRestoredEls && ok) _tsRestoredEls.add(el);
    }
    if (!ok) _tsStats.misses += (spec.length - hitN);
    if (_evProf && t0) _tsStats.restoreMs += _evNow() - t0;
    _tsStats.entries = _tsCache.size; _tsStats.chars = _tsChars;
    return ok;
  }

  function _tsWasRestored(el) {
    return !!(_tsRestoredEls && el && _tsRestoredEls.has(el));
  }

  /** 过滤出"仍需 typeset"的块：已完整复用排版产物的块不再入队。
   *  两条物化路径（idle 批 / 滚动 rAF 同步批）都走这里，避免"缓存命中却又空排一次"。 */
  function _tsFilterNeedTypeset(els) {
    if (!els || !els.length) return els;
    try {
      if (!_tsEnabled()) return els;
      var out = els.filter(function (el) { return !_tsWasRestored(el); });
      if (out.length !== els.length) {
        log("lazy", "typeset cache: skip " + (els.length - out.length) + "/" + els.length + " blocks (fully reused)");
      }
      return out;
    } catch (_) { return els; }
  }

  /** 只读统计（验收/诊断；不参与渲染）。 */
  function _tsStatsSnapshot() {
    return {
      enabled: _tsEnabled(),
      entries: _tsCache ? _tsCache.size : 0,
      chars: _tsChars,
      maxEntries: _tsMaxEntries(),
      maxChars: _tsMaxChars(),
      docKey: _tsDocKey,
      stores: _tsStats.stores, hits: _tsStats.hits, misses: _tsStats.misses,
      evictions: _tsStats.evictions, skipped: _tsStats.skipped,
      restoreMs: Math.round(_tsStats.restoreMs * 100) / 100,
      storeMs: Math.round(_tsStats.storeMs * 100) / 100,
    };
  }
  try { window.__MEMORIA_TYPESET_CACHE_STATS = _tsStatsSnapshot; } catch (_) {}
  try { window.__MEMORIA_TYPESET_CACHE_CLEAR = function () { _tsCache.clear(); _tsChars = 0; _tsDocKey = null; return 1; }; } catch (_) {}

  /** 建一个占位块元素（带连续编号 + 行号 + inline 高度 + aria-hidden）。 */
  function _makePlaceholder(block, i, doc) {
    var el = document.createElement("div");
    el.className = "-src-block -pv-placeholder";
    el.setAttribute("data--block-index", String(i));
    if (block.srcLine > 0) el.setAttribute("data--src-line", String(block.srcLine));
    if (block.srcLineEnd >= block.srcLine) el.setAttribute("data--src-line-end", String(block.srcLineEnd));
    el.style.height = Math.round(_pvBlockH(doc || _doc, i)) + "px";
    el.setAttribute("aria-hidden", "true");
    return el;
  }

  /**
   * 建全文占位 + 物化"视口 ×2 高度"的块。返回 `.-preview-content` 容器（已挂进 preview）。
   * 占位块与 doc.blocks 严格一一对应（0..N-1 连续 data--block-index），**保证 renderRange 永不遇到"连占位都没有"的区间**。
   */
  var _lazyBlockEls = null;   // 全文块元素（占位或已物化的引用，按 index；供后续物化/校验用）
  function _buildLazyPreview(doc, preview) {
    var container = document.createElement("div");
    container.className = "-preview-content";
    var N = doc.blocks.length;
    var pane = document.getElementById("preview-pane") || preview;
    // ★ 2026-10-22（v0.4.6 淘汰修复诊断）：**必须先挂进文档，再量度量**。
    //   旧顺序是先 `_measurePreviewMetrics(pane, container)` 再 `appendChild` ⇒ container 是
    //   detached 元素，`getComputedStyle` 拿到的是 initial 值（16px / normal）⇒ lineHeight 回退
    //   24px；而真实 `.-preview` 是 14px × 1.6 = 22.4px ⇒ 每个占位块系统性偏高 7.1%，
    //   4001 块累加 ≈ 整篇 192,981px vs 真值 175,282px（+17.7k px）。挂载后量到的才是页面 CSS。
    //   注意：这里只挂**空的** container（占位块还没建），不影响任何块序号/高度。
    //   ★ 2026-10-25 task-141：`_measurePreviewMetrics` 会**强制布局**（`_probeBlockMetrics` /
    //   `_probeTypeMetrics` 读 getBoundingClientRect），而此刻 preview 只有一个**空** container
    //   （占位块还没建）⇒ 该次布局看到的 maxScroll≈0，浏览器把 `scrollTop` **夹到 0**。
    //   于是"源码编辑 ⇒ 长文档预览跳回文件开头"。这里在根因处把 scrollTop 跨过空态保住，
    //   占位一齐（总高度恢复）就立刻还原；随后由 `syncSourceToPreview` 用元素锚点做精确校正。
    var _lazyKeepScrollTop = 0;
    try { _lazyKeepScrollTop = pane.scrollTop || 0; } catch (_) { _lazyKeepScrollTop = 0; }
    preview.innerHTML = "";
    preview.appendChild(container);
    _pvMetrics = _measurePreviewMetrics(pane, container);
    // ★ 可观测（验证用）：实测值必须落在 22.4 附近（旧 bug 是 24 = 16×1.5）。
    log("lazy", "metrics: fs=" + _pvMetrics.fs + "px lhPx=" + _pvMetrics.lhPx.toFixed(2) +
      "px paneW=" + Math.round(_pvMetrics.paneW) + " src=" + _pvMetrics.src);
    _lazyBlockEls = new Array(N);
    // 2026-10-22 1c：新一轮文档 ⇒ 重置工作集淘汰状态（LRU 时钟/暂停/计数都只对当前 DOM 有意义）
    _lazyTouch = new Array(N);
    _lazyEvictSuspended = false;
    _lazyEvictCount = 0;
    _lazyEvictQueuedPriority = 0;
    _lazyEvictPendingSkips = 0;
    _lazyEvictPressureSchedules = 0;
    _lazyHeightDriftPx = 0;      // 2026-10-22 1d：新文档 ⇒ 高度漂移计数从 0 开始（旧 DOM 的漂移无意义）
    _lazyAnchorFixes = 0;
    var frag = document.createDocumentFragment();
    for (var i = 0; i < N; i++) {
      var ph = _makePlaceholder(doc.blocks[i], i, doc);
      _lazyBlockEls[i] = ph;
      frag.appendChild(ph);
    }
    container.appendChild(frag);
    // 占位已齐 ⇒ 总高度恢复，此刻写回 scrollTop 不会被夹（task-141 根因处的还原）。
    //   注意：占位高是**估值**，可能与真块略有差 ⇒ 这里只保证"不跳到文件开头"，
    //   精确位置由 `syncSourceToPreview` 的元素锚点 + 漂移收敛负责。
    try {
      if (_lazyKeepScrollTop > 0 && pane.scrollTop < _lazyKeepScrollTop) {
        pane.scrollTop = _lazyKeepScrollTop;
        log("lazy", "restore scrollTop after empty-measure: " + Math.round(_lazyKeepScrollTop));
      }
    } catch (_) { /* noop */ }

    // 物化首屏：先按估值给一个**保守**首块数，之后用**实测块高反推**再决定是否补物化（不依赖任何硬编码）。
    var viewH = pane.clientHeight || (window.visualViewport && visualViewport.height) || 720;
    var avgH0 = N > 0 ? Math.max(_pvBlockH(doc, 0), _pvM().lhPx) : _pvM().lhPx;
    var firstCount = Math.min(N, Math.max(12, Math.ceil(viewH / avgH0)));   // 先物化约 1 屏
    var madeEls = _materializeRange(container, doc, 0, firstCount);
    var materialized = madeEls.length;

    // ★ ④ 用**实测块高**反推 avgH，补物化到 2 屏（换字体/缩放后自适应，不靠估值）
    try {
      if (materialized > 0) {
        var top0 = container.getBoundingClientRect().top;
        var usedH = 0;
        for (var q = materialized - 1; q >= 0; q--) {
          var e0 = madeEls[q];
          if (e0 && e0.getBoundingClientRect) {
            usedH = (e0.getBoundingClientRect().bottom - top0);
            if (usedH > 0) break;
          }
        }
        var avgReal = (usedH > 0 && materialized > 0) ? (usedH / materialized) : 0;
        if (avgReal > 0) {
          var target = Math.min(N, Math.ceil((viewH * 2) / avgReal));   // 目标 = 2 屏
          if (target > materialized) {
            var more = _materializeRange(container, doc, materialized, target);
            madeEls = madeEls.concat(more);
            materialized += more.length;
            log("lazy", "first-screen: avgRealH=" + Math.round(avgReal) + "px viewH=" + Math.round(viewH) + " ⇒ materialized " + materialized + " blocks (2 screens)");
          }
        }
      }
    } catch (e) { log("lazy", "first-screen measure ERR " + ((e && e.message) || e)); }

    // ── 自检（硬约束）：占位 + 已物化 必须 === 全文块数。不等 ⇒ 有块既没占位也没物化（严重缺陷）。──
    var placeholders = container.querySelectorAll(".-pv-placeholder").length;
    var ok = (placeholders + materialized) === N;
    var _pm = _pvM();
    log("lazy", "lazy materialize ON: blocks=" + N + " placeholders=" + placeholders + " materialized=" + materialized + " sum=" + (placeholders + materialized) + " eq=" + ok + " [fs=" + _pm.fs + " lh=" + _pm.lhPx.toFixed(2) + " paneW=" + Math.round(_pm.paneW) + " src=" + _pm.src + "]");
    if (!ok) {
      // 硬约束破 ⇒ 就地退回：清掉占位，走全量 renderDocument（绝不半坏状态）
      try { log("lazy", "CONSTRAINT BROKEN, falling back to full render"); } catch (_) {}
      preview.innerHTML = "";
      var _full = _rcRenderer().renderDocument(doc);
      preview.appendChild(_full.container);
      _lazyBlockEls = _full.blockEls;
      return _full.container;
    }
    return container;
  }

  /** 物化 `[start, end)` 区间：占位块 → renderBlock 产出的真块（原位替换，保持 data--block-index 连续）。
   *  @returns {HTMLElement[]} 本次新建的真块节点数组（供调用方对新块排版/后处理；失败/跳过不入）。 */
  function _materializeRange(container, doc, start, end) {
    var rc = _rcRenderer();
    if (!rc || !rc.renderBlock) return [];
    var all = container.querySelectorAll(".-pv-placeholder");
    // 按 data--block-index 建"占位下标 → 元素"（占位在区间 [start,end) 内才物化）
    var madeEls = [];
    for (var j = 0; j < all.length; j++) {
      var ph = all[j];
      var idx = parseInt(ph.getAttribute("data--block-index"), 10);
      if (idx < start || idx >= end) continue;
      if (idx >= doc.blocks.length) continue;
      var real;
      try { real = rc.renderBlock(doc.blocks[idx], idx); }
      catch (e) { log("render", "lazy materialize block " + idx + " ERR " + (e && e.message)); continue; }
      if (!real) continue;
      // ★ 2026-10-23 task-72：先尝试**复用上次 typeset 的产物**（纯 innerHTML 写回，不产生 MathItem）。
      //   命中 ⇒ 该块不需要再进 typeset 队列（见 `_tsFilterNeedTypeset`），这是本次改动的核心收益。
      try { _tsApplyBlock(real, doc.blocks[idx]); } catch (_) {}
      // 2026-10-22 修上跳（metrics 实测 maxShrink=114px）：**占位偏高时物化必然上跳**（D1 的"宁大勿小"只保证
      //   初值偏大，但物化那一刻真实高度若小于占位高度，下方内容就会弹上去 —— 这是 K4a 被回退的同类问题）。
      //   修法：物化前取占位高度，把真块的 `min-height` 锁到该值 ⇒ **替换瞬间高度只增不减**；
      //   等高块离开视口后再由 `_lazyReleaseMinHeight` 回落（用户看不见，且不产生上跳）。
      //   注意：**用计算出的估值、不量 DOM**（`getBoundingClientRect()` 会强制同步布局，批量物化时十几次代价高）；
      //   该值与 `_makePlaceholder` 写进 `style.height` 的值同源，故等价。
      //   注意：**优先用占位自带的块高**——换出时写进 `data--pv-r` 的是**真块自身 rect 高度**
      //   （见 `_lazyEvictNow`）。若这里改用估值（`_placeholderHeight`）锁高，就会把估值与真块的高度
      //   差重新引入（实测最大 332px/块），让"换出保高"白做、滚动绝对位置再次漂移。
      //   ⚠️ 用 `data--pv-r`（块自身高）而**不是** `data--pv-h`（垂直占位体积）：后者含塌陷外边距，
      //   拿来锁 min-height 会把外边距变成块内 padding ⇒ 高度反而涨回去。
      var _phH = _pvBlockH(doc, idx);
      var _recH = parseFloat(ph.getAttribute("data--pv-r"));
      if (_recH > 0) _phH = _recH;
      ph.replaceWith(real);
      // **无条件**锁 min-height：若真实高度 ≥ 占位 ⇒ min-height 不生效（零副作用）；
      // 若 < 占位 ⇒ 生效，挡住上跳。不比较、不量真块高度（省一次强制同步布局）。
      if (_phH > 0 && real.style) {
        _ensureLazyLockedIO();
        real.style.minHeight = Math.round(_phH) + "px";
        real.setAttribute("data--pv-locked", "1");
        if (!_lazyLockedEls) _lazyLockedEls = new Set();
        _lazyLockedEls.add(real);
        if (_lazyLockedIO) _lazyLockedIO.observe(real);
      }
      // 2026-10-22 1b：滚动物化的真块缺 data--src-line（stampBlockLines 只跑一次，管不到滚动新增的块）。
      //   物化时直接从 AST 补写（与 stampBlockLines 经 BlockIndex 写的口径一致，行号唯一真源仍是 parser）。
      var _blk = doc.blocks[idx];
      if (_blk && _blk.srcLine > 0) {
        real.setAttribute("data--src-line", String(_blk.srcLine));
        real.setAttribute("data--src-line-end", String(_blk.srcLineEnd >= _blk.srcLine ? _blk.srcLineEnd : _blk.srcLine));
      }
      _lazyBlockEls[idx] = real;
      // W3.4：图片块物化后记录真实加载结果（成功→宽高比，失败→标记），供后续占位估值使用。
      try { _pvWatchImage(real); } catch (_) {}
      _lazyTouchBlock(idx);       // 2026-10-22 1c：物化即"触碰"，供淘汰的 LRU 时钟使用
      madeEls.push(real);
    }
    return madeEls;
  }

  // ════ 2026-10-22 阶段1b：滚动追加物化（IntersectionObserver + 批量 idle 物化）══════
  // 滚动使占位块进入视口前 1 屏 ⇒ IO 回调只收集下标到 pending 集合 ⇒ idle 里批量物化 + 排版。
  // 绝不在 IO 回调里同步物化（会吃掉那一帧）；拖动时靠节流（IO 天然按帧节流，无需手写 debounce）。

  var _lazyIO = null;           // IntersectionObserver 实例
  var _lazyPending = null;      // Set：待物化块下标（收集后统一批量处理）
  var _lazyLockedEls = null;    // Set<Element>：物化时被锁 min-height 的块（等离开视口再回落）
  var _lazyLockedIO = null;    // 观察"被锁高块"的 IO：离开视口 ⇒ 解除 min-height

  /** 解除被锁高的块（真高度接管）。`el` 省略 ⇒ 全部解除（换文档/teardown 时兜底）。 */
  function _lazyReleaseMinHeight(el) {
    var list = el ? [el] : (_lazyLockedEls ? Array.from(_lazyLockedEls) : []);
    for (var i = 0; i < list.length; i++) {
      var x = list[i];
      if (!x) continue;
      try {
        x.style.minHeight = "";
        x.removeAttribute("data--pv-locked");
        if (_lazyLockedIO) _lazyLockedIO.unobserve(x);
      } catch (_) { /* 已脱离文档 ⇒ 忽略 */ }
      if (_lazyLockedEls) _lazyLockedEls.delete(x);
    }
  }

  /** 惰性创建"被锁高块"的 IO：这些块**离开视口**时解除 min-height（视口内永不回落 ⇒ 不上跳）。
   *
   *  ⚠️ 2026-10-22 1d 评估记录：曾尝试"只回落视口下方的块（视口上方保持锁高）"以消除
   *  "上方块变矮 ⇒ 可见内容整体上移"。**不可行**：视口上方保持锁高的块被换出时占位高度会被
   *  记录成估算值（因为它的 rect 仍被 min-height 撑着），滚回物化时真实高度更小 ⇒ 占位与真块
   *  高度不一致，反而在物化瞬间再次抽走高度，且块内留下大段空白。⇒ 保持原语义（离开视口即回落），
   *  高度一致性交给"换出时记录真实高度 + 回滚物化锁真实高度"（见 `_lazyEvictNow` / `_materializeRange`）。 */
  function _ensureLazyLockedIO() {
    if (_lazyLockedIO || typeof IntersectionObserver !== "function") return;
    _lazyLockedIO = new IntersectionObserver(function (entries) {
      var released = 0;
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) continue;      // 还在视口内 ⇒ 保持锁高，绝不回落
        _lazyReleaseMinHeight(entries[i].target);
        released++;
      }
      if (released) log("lazy", "unlock minHeight: " + released);
    }, { root: null, rootMargin: "0px", threshold: 0 });
  }

  /** 建立滚动物化：观察 `.-pv-placeholder`，进视口前 1 屏(long)时批量物化。仅惰性模式调用。 */
  function _setupLazyScrollMaterialization(preview) {
    if (typeof IntersectionObserver !== "function") return;   // 极老环境（应当没有）⇒ 不启用
    if (_lazyIO) _lazyIO.disconnect();
    _lazyIO = new IntersectionObserver(function (entries) {
      var hit = false;
      for (var i = 0; i < entries.length; i++) {
        if (!entries[i].isIntersecting) continue;
        var t = entries[i].target;
        if (!t || !t.classList || !t.classList.contains("-pv-placeholder")) continue;
        if (!_lazyPending) _lazyPending = new Set();
        var idx = parseInt(t.getAttribute("data--block-index"), 10);
        if (!isNaN(idx)) { _lazyPending.add(idx); hit = true; }
      }
      if (hit) { if (!_lazyCollectAt) _lazyCollectAt = (window.performance && performance.now) ? performance.now() : Date.now(); _lazyScheduleFlush(); }
    }, { root: preview.parentElement || document, rootMargin: "200% 0px", threshold: 0 });   // 2026-10-22 1b 调优：前 2 屏预取（100%→200%），滚动 141/187ms → ≤100ms；副作用（多物化/新冻结）待实测

    var phs = preview.querySelectorAll(".-pv-placeholder");
    for (var p = 0; p < phs.length; p++) _lazyIO.observe(phs[p]);
    _bindLazyViewportWatchers();   // 2026-10-22：字体/缩放/窗口变化 ⇒ 重算占位（幂等，只绑一次）
    _bindLazyScrollIdleSync(preview);   // 2026-10-22：滚动**停止**后同步补物化（不等 IO/idle）
    _lazyScheduleEvict();          // 2026-10-22 1c：首屏建成后排一次工作集淘汰（P3，不在渲染帧里做）
  }

  // ══ 2026-10-22（Lead 定性"饿死"+ 我观察到的"滚动停后静默停滞"）：滚动停止 ⇒ **同步**补物化 ══
  // 问题：拖动时 IO 收集 + idle 批物化（不卡手感，正确）；但**用户停下后**若视口内仍有占位块，
  //   IO 可能已把回调消费掉、pending 也被清空 ⇒ **没有任何东西再叫醒物化** ⇒ 空白持续上千 ms
  //   （metrics 实测 line=4707 卡住 683ms、滚动已停却迟迟不物化）。
  // 对策：scroll 停止 50ms 后，**不依赖 IO/pending，直接扫 DOM 里视口内的占位块同步物化**。
  //   这与会话中异步物化不冲突：拖动时 idle（不卡手感），停下时同步（保证"用户看得见"）。
  var LAZY_SCROLL_IDLE_MS = 50;
  var LAZY_SYNC_MAX = 50;          // rAF 同步物化单批上限（每帧都可能跑 ⇒ 必须小步，防单帧过重）
  var _lazyScrollIdleTimer = null;
  var _lazyScrollBound = false;
  var _lazySyncNeeded = false;      // ★ rAF 驱动：scroll 只置位，不 debounce
  var _lazySyncRAF = 0;
  var _lazyLastScrollAt = 0;        // 最近一次 scroll 的时刻（供"滚动中"判据）

  function _bindLazyScrollIdleSync(preview) {
    if (_lazyScrollBound) return;
    var pane = preview.parentElement || preview;
    if (!pane || !pane.addEventListener) return;
    _lazyScrollBound = true;
    // ★ 2026-10-22 改（Lead：`sync materialize` 恒 0 次）：**不再 debounce**。
    //   原写法在滚动中每次 scroll 都 `clearTimeout` 重置 50ms 定时器 ⇒ 持续拖动时**永远到不了执行点**。
    //   现在：scroll **只置位** `_lazySyncNeeded`，由 rAF 每帧检查一次并执行 ⇒ 滚动中每帧都有机会跑。
    pane.addEventListener("scroll", function () {
      _lazySyncNeeded = true;
      _lazyLastScrollAt = (window.performance && performance.now) ? performance.now() : Date.now();
      if (!_lazySyncRAF) {
        var tick = function () {
          _lazySyncRAF = 0;
          if (!_lazySyncNeeded) return;
          _lazySyncNeeded = false;
          try { _lazySyncMaterializeViewport(preview); } catch (e) { log("lazy", "scroll-rAF sync ERR " + ((e && e.message) || e)); }
        };
        _lazySyncRAF = (window.requestAnimationFrame) ? window.requestAnimationFrame(tick) : setTimeout(tick, 16);
      }
      // ★ 2026-10-22 task-65「滚动停止」兜底：拖动中由上面 rAF 每帧小步推进；**停下那一刻**
      //   若视口内仍有占位（最后一帧 rAF 已跑完 / 被其它任务插队），再同步推进一批。
      //   这里只是 UI debounce（50ms 内无新 scroll），**不是**惰性管线的调度源：
      //   物化/排版仍由 `MemoriaScheduler` 按 P1/P2 排队执行。
      if (_lazyScrollIdleTimer) clearTimeout(_lazyScrollIdleTimer);
      _lazyScrollIdleTimer = setTimeout(function () {
        _lazyScrollIdleTimer = null;
        try { _lazySyncMaterializeViewport(preview); } catch (e) { log("lazy", "scroll-stop sync ERR " + ((e && e.message) || e)); }
        // 2026-10-22 1c：滚动**停止**才排淘汰（滚动帧内绝不换出；P3 作业自己按帧预算切片）
        _lazyScheduleEvict();
      }, LAZY_SCROLL_IDLE_MS);
    }, { passive: true });
  }

  /** 最近 300ms 内是否发生过滚动（"滚动中"判据，供 typeset 降批/让路）。 */
  function _lazyIsScrolling() {
    if (!_lazyLastScrollAt) return false;
    var now = (window.performance && performance.now) ? performance.now() : Date.now();
    return (now - _lazyLastScrollAt) < 300;
  }

  /** **同步**物化当前视口内的占位块（滚动停止后调用；不排队、不等 idle）。
   *
   *  ⚠️ 2026-10-22 修复（Lead 实测本函数**从未触发**）：原实现遍历**全部**占位块并逐块
   *  `getBoundingClientRect()` —— 3978 个占位块 = 数千次强制同步布局 ⇒ 该函数本身要跑几百 ms~秒级，
   *  期间又被新的 scroll 事件重置 debounce ⇒ 实际**几乎永远跑不到 log 那行**（`scroll-idle sync` 0 次）。
   *  现在：占位块是 `.-preview-content` 的**直接子元素**且按 `data--block-index` 有序、布局位置单调递增
   *  ⇒ 用**二分查找**定位视口范围，只对命中区间做少量 `getBoundingClientRect`（O(log n)）。
   *  并且：**只要有视口占位就物化**（不再依赖 pending 集合），彻底消除"滚动停后无事件叫醒"的静默停滞。 */
  function _lazySyncMaterializeViewport(preview) {
    if (!_lazyMaterializeEnabled(_doc) || !_doc || !_doc.blocks) return 0;
    var pane = document.getElementById("preview-pane") || (preview && preview.parentElement);
    var cc = preview ? preview.querySelector(".-preview-content") : null;
    if (!pane || !cc) return 0;
    var phs = cc.querySelectorAll(".-pv-placeholder");
    if (!phs.length) return 0;

    var paneRect = pane.getBoundingClientRect();
    // 视口上下各留半屏余量（"用户停下"时也顺手把上下略远处物化好）
    var lo = paneRect.top - paneRect.height * 0.5;
    var hi = paneRect.bottom + paneRect.height * 0.5;

    // ── 二分：占位块按文档序排列、位置单调 ⇒ 找 top >= lo 的第一个 / bottom <= hi 的最后一个 ──
    var n = phs.length;
    function topOf(i) { return phs[i].getBoundingClientRect().top; }
    function bottomOf(i) { return phs[i].getBoundingClientRect().bottom; }
    var loI = 0, hiI = n - 1, firstHit = n;
    while (loI <= hiI) {                       // 找第一个 bottom >= lo 的块
      var mid = (loI + hiI) >> 1;
      if (bottomOf(mid) >= lo) { firstHit = mid; hiI = mid - 1; } else { loI = mid + 1; }
    }
    if (firstHit >= n) return 0;               // 视口上方没有占位块（都在下方或全已物化）
    var loI2 = firstHit, hiI2 = n - 1, lastHit = -1;
    while (loI2 <= hiI2) {                     // 找最后一个 top <= hi 的块
      var mid2 = (loI2 + hiI2) >> 1;
      if (topOf(mid2) <= hi) { lastHit = mid2; loI2 = mid2 + 1; } else { hiI2 = mid2 - 1; }
    }
    if (lastHit < firstHit) return 0;          // 视口内没有占位块 ⇒ 已全部物化（无操作）

    // 收集命中区间内的块下标（区间通常只有几屏，量很小）
    var idxs = [];
    for (var i = firstHit; i <= lastHit; i++) {
      var ix = parseInt(phs[i].getAttribute("data--block-index"), 10);
      if (!isNaN(ix)) idxs.push(ix);
    }
    if (!idxs.length) return 0;

    // 合并连续区间并**同步**物化。★ 单批上限收窄到 `LAZY_SYNC_MAX`（50）：
    //   rAF 每帧都可能调用本函数 ⇒ 必须小步快跑，绝不能在单帧里建上百块（否则又造长帧）。
    var made = [];
    idxs.sort(function (a, b) { return a - b; });
    for (var k = 0; k < idxs.length; k += LAZY_SYNC_MAX) {
      var chunk = idxs.slice(k, k + LAZY_SYNC_MAX);
      var s = chunk[0], e = chunk[chunk.length - 1] + 1;
      var els = _materializeRange(cc, _doc, s, e);
      made = made.concat(els);
    }
    if (made.length) {
      log("lazy", "scroll-rAF sync materialize: blocks=" + made.length + " (viewport[" + firstHit + ".." + lastHit + "])");
      // 排版走合并器（低优先级、可合并），后处理与首屏对齐
      _lazyEnqueueMath(_tsFilterNeedTypeset(made));
      _lazyRenderMermaidIn(made);
      _lazyPostProcessNewBlocks(made);
      try { _applyCodeHighlightToPreview(preview); postProcessWikilinks(); bindPreviewLinks(); } catch (_) {}
      // task-78：滚动中一旦工作集超压，立即把淘汰升到 P1 排队（不等 50ms 的 scroll-stop）。
      _lazyMaybeScheduleEvict();
    }
    return made.length;
  }

  /** 调度一次批量物化 —— **MemoriaScheduler 作业**（P1 交互可见，同起点合并）。
   *
   *  2026-10-22 task-65：把原来手写的 `setTimeout(0)` 队列换成 M5 调度内核作业，与排版管线（P2）
   *  共用**同一个**调度源 ⇒ 不再出现"两个宏任务队列互相排队"（实测批次间隔 median 119–134ms）。
   *
   *  合并：`key = lazy-materialize:<pending 最小块下标>` + `replace: true`
   *    ⇒ 同一区间的多次 IO 收集只留一个待执行作业；起点变了才另开一个（旧作业执行时
   *      `_materializeRange` 只处理**仍是占位**的块 ⇒ 幂等空跑，不会重复建 DOM）。
   *  陈旧：`gen = epoch()` + `dropStale` ⇒ 换文档 / 缓存搬回 `bumpEpoch()` 后，排队中的旧作业执行前丢弃。
   *    **滚动不 bump**（滚动只是同一份文档内的可见窗口变化）。
   *  活性：作业内部 `_lazyFlushNow()` 仍保留"有余量就续排"的 finally（不依赖调度器内部状态）；
   *    即使某次调度回调丢失，下一次 IO/滚动 stop 仍会重新 `schedule` ⇒ 不回到"队列有块但没人消费"。
   */
  var _lazyCollectAt = 0; // IO 收集到块、请求 flush 的时刻（用于量化 collect→flush 延迟）

  /** 调度内核引用（scheduler.js 在 index.html 中先于 app.js 加载；测试壳可能缺席 ⇒ 调用方需防御）。 */
  function _lazyJobScheduler() { return window.MemoriaScheduler || null; }

  /** pending 集合里最小的块下标（只用于生成作业 key；不修改队列）。 */
  function _lazyPendingStartKey() {
    if (!_lazyPending || !_lazyPending.size) return "none";
    var min = Infinity;
    _lazyPending.forEach(function (v) { if (v < min) min = v; });
    return String(min);
  }

  function _lazyScheduleFlush() {
    if (!_lazyPending || !_lazyPending.size) return;
    var S = _lazyJobScheduler();
    if (!S || typeof S.schedule !== "function") {
      // 防御性回退：调度内核缺席（旧壳/被裁剪的构建）时也不能让视口永久占位。
      // 正常生产路径**不会**走到这里（scheduler.js 先加载）。
      setTimeout(function () {
        try { _lazyFlushNow(); } catch (e) { log("lazy", "flush THREW (no scheduler): " + ((e && e.message) || e)); }
      }, 0);
      return;
    }
    S.schedule({
      kind: "lazy_materialize",
      key: "lazy-materialize:" + _lazyPendingStartKey(),
      priority: 1,            // P1 交互：可见性优先于排版（P2）
      replace: true,
      gen: (typeof S.epoch === "function") ? S.epoch() : 0,
      dropStale: true,
      run: function () {
        // 记录"收集 → 实际 flush"的延迟（metrics 用来量化调度等待）
        try {
          if (_lazyCollectAt) {
            log("lazy", "flush delay: collect→flush = " + Math.round(((window.performance && performance.now) ? performance.now() : Date.now()) - _lazyCollectAt) + " ms");
            _lazyCollectAt = 0;
          }
        } catch (_) {}
        try {
          _lazyFlushNow();
        } catch (e) {
          log("lazy", "flush THREW: " + ((e && e.message) || e));
          throw e;   // 交回调度器：作业标 error 并继续跑队列里的其它作业（不会卡住 pump）
        }
      },
    });
  }

  /** 换文档 / 缓存搬回：**惰性管线里唯一**提升调度 epoch 的地方（滚动不 bump）。
   *
   *  同时清空两条惰性管线队列：被 `dropStale` 丢弃的作业不会留下"队列有块但没人消费"的孤儿。
   *  （同文档增量重渲**不**调用 ⇒ 已排队作业按原 epoch 继续执行，避免误丢。） */
  function _lazyPipelineDropQueues() {
    if (_lazyPending) _lazyPending.clear();
    _lazyCollectAt = 0;
    _lazyMathQueue = null;
    if (_lazyMathQueueTimer) { clearTimeout(_lazyMathQueueTimer); _lazyMathQueueTimer = null; }
    try { _lazyRevealAllMathPending(); } catch (_) {}
  }

  /** 提升 epoch + 作废两条队列（换文档/缓存搬回用）。 */
  function _lazyPipelineReset(reason) {
    var S = _lazyJobScheduler();
    var ep = (S && typeof S.bumpEpoch === "function") ? S.bumpEpoch() : null;
    _lazyPipelineDropQueues();
    // 2026-10-22 1c：换文档/缓存搬回 ⇒ 解除 `__MEMORIA_MATERIALIZE_ALL` 的淘汰暂停
    //   （该暂停只属于"当时那份被强制全量物化的 DOM"，不能跨文档残留）。
    _lazyEvictSuspended = false;
    _lazyEvictQueuedPriority = 0;
    try { log("lazy", "pipeline epoch→" + (ep == null ? "n/a" : ep) + " (" + reason + ")"); } catch (_) {}
  }

  /** 批量物化 pending 里的块 + 对新块排版。
   *
   *  ⚠️ 2026-10-22 修复（Lead 实测 `MATERIALIZE_ALL` 冻结 20 分钟引发）：**单批必须有上限**。
   *  真实场景：用户**快速拖滚动条到底** ⇒ IO 在一两帧内把沿途**所有**占位块收进 pending
   *  （`rootMargin: 200%` 还会放大范围）⇒ 原先这里一次全物化 = 数千块同步建 DOM = 长时间冻结。
   *  现在：每次 float 最多物化 `LAZY_FLUSH_MAX` 块，**余量放回 pending 并重新调度**
   *  ⇒ 每次只占一小段主线程，其余留给下一批调度作业（MemoriaScheduler 帧预算）。 */
  // 单批物化上限。**依据实测**（Lead，拖到底场景 08 章）：130.8ms 帧 / 200 块 ≈ **0.65ms/块**
  // ⇒ 100 块 ≈ 65ms，为 100ms 预算留余量。
  // 若后续出现"块更复杂导致单批仍超 100ms"，继续降到 50 —— **有实测依据才调，不凭感觉改**。
  var LAZY_FLUSH_MAX = 100;

  // 公式数上限 —— **当前不生效（0 = 关闭）**。
  //
  // 【为什么不启用】2026-10-22 实测 A/B（Lead，08 章真拖拽）：
  //   v4（本上限关闭）：9 次 typeset 调用 → 574.1ms / 452 公式 → **1.270 ms/公式**
  //   v5（本上限 = 32）：19 次 typeset 调用 → 1244.7ms / 445 公式 → **2.797 ms/公式**（2.2×）
  //   ⇒ **同样公式量、调用次数翻倍 ⇒ 总成本翻倍**：`typesetPromise` 每次调用有显著**固定开销**，
  //     批次越碎越亏（U 形曲线：批次减少省下的主线程峰值，被固定开销反噬掉）。
  //   ⇒ 32 是**过度优化**。保留代码与 `_countBlockFormulas`（纯 AST 计数，另有用处），
  //     但**待"物化/排版解耦"落地后重新评估**——解耦后 typeset 调用次数由合并策略决定，
  //     与物化批次数脱钩，届时本上限才可能重新有意义。
  var LAZY_FLUSH_MAX_FORMULAS = 0;   // 0 = 不限制（回到 v4 配置：块 100 / 无公式上限）

  function _lazyFlushNow() {
    if (!_lazyPending || !_lazyPending.size) return;
    if (!_doc || !_doc.blocks) { _lazyPending.clear(); return; }
    var container = $("#preview");
    if (!container) return;
    var cc = container.querySelector(".-preview-content") || container;
    var pendingArr = Array.from(_lazyPending).sort(function (a, b) { return a - b; });

    // 2026-10-22 加固：**先算余量、先把余量放回队列，再物化**。
    // 原写法「先 clear → 再算 overflow → 物化完才放回」存在一个脆弱时序：
    // 若在 clear 与放回之间抛异常，overflow（本批之外的块）会**永久丢失** ⇒
    // 用户滚过去看到永久占位（静默、不报错，属最难发现的失效）。
    // 现在：即便物化阶段抛错，余量已在队列里 ⇒ 最坏只是本批延后，绝不漏块。
    var overflow = null;
    if (pendingArr.length > LAZY_FLUSH_MAX) {
      overflow = pendingArr.slice(LAZY_FLUSH_MAX);
      pendingArr = pendingArr.slice(0, LAZY_FLUSH_MAX);
    }
    // ★ 2026-10-22：**双上限**（块数 + 公式数，先到者生效）。按 AST 累计本批公式数，
    //   超过 `LAZY_FLUSH_MAX_FORMULAS` 就把超额块截到 overflow。公式数是纯 AST 计数（不读 DOM）。
    //   ⚠️ `LAZY_FLUSH_MAX_FORMULAS <= 0` ⇒ **不限制**（当前即此态：实测批次数增加会放大 typeset 固定开销）。
    if (pendingArr.length && LAZY_FLUSH_MAX_FORMULAS > 0) {
      var fAcc = 0, fCut = pendingArr.length;
      for (var fi = 0; fi < pendingArr.length; fi++) {
        var _f = _countBlockFormulas(_doc.blocks[pendingArr[fi]]);
        if (fAcc + _f > LAZY_FLUSH_MAX_FORMULAS) { fCut = fi; break; }   // 本批停在 fi 之前（第 fi 块若加入会越界 ⇒ 进余量）
        fAcc += _f;
      }
      if (fCut < pendingArr.length) {
        var fOverflow = pendingArr.slice(fCut);
        overflow = overflow ? overflow.concat(fOverflow) : fOverflow;
        pendingArr = pendingArr.slice(0, fCut);
      }
    }
    _lazyPending.clear();
    if (overflow) {
      for (var oi = 0; oi < overflow.length; oi++) _lazyPending.add(overflow[oi]);
    }

    // 物化：把本批的下标合并成连续区间，逐段物化。
    // ⚠️ 2026-10-22 P0 修复（Lead 定位到"物化停滞"）：**必须 try/catch/finally**。
    //   `_materializeRange` 里除 `renderBlock` 外的调用（`ph.replaceWith` / `observe` 等）**没有保护**，
    //   一旦抛未捕获异常，原代码会**跳过下面的 `_lazyScheduleFlush()`** ⇒
    //   队列里明明有块却没有任何调度 ⇒ **后续物化永久停滞**（用户看到视口永远是占位块/空白）。
    //   与 metrics 观察吻合：从某一刻起 ph 不再减少。
    //   ⇒ 现在：异常只记日志并中止**本批**，但调度**无条件续命**（finally）。
    var made = [];
    try {
      for (var i = 0; i < pendingArr.length; i++) {
        var s = pendingArr[i];
        var e = s + 1;
        // 向后合并连续下标
        while (i + 1 < pendingArr.length && pendingArr[i + 1] === e) { i++; e++; }
        var els = _materializeRange(cc, _doc, s, e);
        made = made.concat(els);
      }
    } catch (eMat) {
      log("lazy", "materialize batch FAILED: " + ((eMat && eMat.message) || eMat) + " (batch=" + pendingArr.length + " made=" + made.length + ")");
      // 本批未物化成功的块**放回队列**（它们仍是占位块，还需要物化）——
      //   否则异常会让这些块永远停在占位态（与上面"调度停滞"是两个独立的漏排来源）。
      try {
        var _doneSet = null;   // 已成功物化的块下标集合（从 made 反推不划算，这里按"是否仍是占位"判断）
        if (!_lazyPending) _lazyPending = new Set();
        for (var ri = 0; ri < pendingArr.length; ri++) {
          var _ix2 = pendingArr[ri];
          var _el2 = _lazyBlockEls ? _lazyBlockEls[_ix2] : null;
          // 该下标对应元素仍是占位（或找不到）⇒ 说明没物化成功 ⇒ 回队列重试
          if (!_el2 || (typeof _el2.classList !== "undefined" && _el2.classList && _el2.classList.contains("-pv-placeholder"))) {
            _lazyPending.add(_ix2);
          }
        }
      } catch (_) { /* 回收失败也不能阻断下面的续命调度 */ }
    } finally {
      // ★ 核心原则：**只要有残留待物化块，就必须保证下一批会被调度**（绝不会"队列有块但没人管"）。
      if ((overflow && overflow.length) || (_lazyPending && _lazyPending.size)) {
        try {
          log("lazy", "flush continue: made=" + made.length + " overflow=" + (overflow ? overflow.length : 0) + " pending=" + (_lazyPending ? _lazyPending.size : 0));
        } catch (_) {}
        _lazyScheduleFlush();
      }
    }

    if (!made.length) return;
    // task-78：物化批次同样检查压力 —— P1 物化连续非空时，P3 淘汰会被无限推后。
    _lazyMaybeScheduleEvict();

    // ★ 2026-10-22「物化/排版**解耦**」：不再"每批 flush ⇒ 立即 typeset 该批"。
    //
    // 依据实测（Lead，08 章真拖拽 A/B）：
    //   v4（每批一次 typeset）9 次调用 → 574.1ms / 452 公式 → 1.270 ms/公式
    //   v5（批次更碎）        19 次调用 → 1244.7ms / 445 公式 → 2.797 ms/公式（2.2×）
    //   ⇒ `typesetPromise` **每次调用有显著固定开销** ⇒ 调用次数与成本正相关 ⇒ 应**合并**。
    // 做法：本批物化出的含公式块先**累积**到 `_lazyMathQueue`，由一个合并器在 idle 里**一次性**排掉；
    //   拖到底期间 6 批物化 ⇒ 预期只触发 1–2 次 typeset（而非 6 次）。
    // **必须保证公式不会长期不排** ⇒ `_lazyMathQueueTimer` 硬上限 `LAZY_MATH_MERGE_MAX_WAIT`（500ms）必排。
    if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
      // ★ 2026-10-22 P0 修复（Lead 定性真 bug）：**删掉 `withMath` 按 `.-math` 类名的二元过滤**。
      //
      // 根因：`withMath` 只认 `.-math` / `.-math-block` 类名 ⇒ 把 `-image-block`（其可见题注是**裸文本**
      //   `图3.3.15 $A$ 律变换...`，MathJax 靠**分隔符**识别、**不依赖类名**）排除掉了 ⇒ 题注里的 `$A$`
      //   永不入 typeset 队列 ⇒ 永不排版 ⇒ golden 是 `A`、惰性是 `$A$`（R1 漏排）。
      // 全量路径是 `typesetPromise([preview])` **整篇扫**、根本不做"哪块有公式"的预判 —— 这个过滤
      //   本就是我早前留下的**多余优化**，制造了漏排。现在回到全量路径语义：
      //   **本批所有物化块都入队**；MathJax 对无公式块是低成本 no-op（扫一遍无 `$`/`\(` 就返回）。
      // 成本结论：调用次数不变（合并器保证），只有"每次调用扫的块数"略增；公式数不变则成本基本不变。
      // task-72：已完整复用排版产物的块**不再入队**（否则会被 `-math-pending` 隐藏再空排一次）。
      _lazyEnqueueMath(_tsFilterNeedTypeset(made));
    }
    // 补齐行内公式标记（排版后会替换 .-math ⇒ mjx-container，需重打 data--inline-math）
    var token2 = state.previewToken;
    var prev2 = state._mathPending;
    if (prev2 && typeof prev2.then === "function") {
      prev2.then(function () { if (token2 === state.previewToken) { try { _tagInlineMathContainers($("#preview"), _doc); } catch (_) {} } });
    }
    // 代码高亮 / 链接后处理（新块可能有 code / wikilink）
    // ⚠️ `_applyCodeHighlightToPreview` **故意跳过** `code.language-mermaid`（mermaid 由 renderMermaidBlocks 接管）
    // ⇒ 新物化的 mermaid 块**必须**显式交给 mermaid 渲染，否则永远停在 `<pre><code>` 源码态（2026-10-22 交互门禁实测到）。
    try { _applyCodeHighlightToPreview(container); postProcessWikilinks(); bindPreviewLinks(); } catch (_) {}
    _lazyRenderMermaidIn(made);
    _lazyPostProcessNewBlocks(made);   // 2026-10-22：补齐 contentEditable / 灯箱（与首屏路径对齐，见函数注释）
    // 2026-10-22 1c：一批物化完成后顺手排一次淘汰（P3；`_lazyEvictNow` 会在 pending 非空时自行让路）
    _lazyScheduleEvict();
  }

  /** 对新物化的块补做**首屏路径做过、滚动批次曾漏掉**的后处理（2026-10-22 系统性对齐）。
   *
   *  背景：首屏 `renderPreview` 有一整串收尾（禁编辑 / 灯箱 / 行号 / 后续 mermaid），
   *  滚动批次只做了"代码高亮 + 链接 + 公式"，于是门禁逐条抓到漏处理：
   *    · mermaid 显示源码（已修）
   *    · `contentEditable` 没设 ⇒ 代码块/表格/公式块**可被误编辑**（真可感知缺陷）
   *    · 灯箱未绑定 ⇒ 点图不放大
   *    · `data-block-id` / 行号属性缺失（行号已在 `_materializeRange` 里直接补）
   *  本函数把"按块集合就能做"的收尾统一补齐；**只作用于本批块**，不扫全篇。 */
  function _lazyPostProcessNewBlocks(madeEls) {
    if (!madeEls || !madeEls.length) return;
    // ① 禁编辑：与首屏路径同一份 kind 白名单（app.js:2056 的 _nonEditableTypes）与同一组子选择器
    var _nonEdTypes = { code_block: 1, math_block: 1, mermaid: 1, table: 1, frontmatter: 1 };
    for (var i = 0; i < madeEls.length; i++) {
      var blkEl = madeEls[i];
      if (!blkEl || !blkEl.getAttribute) continue;
      var bi = parseInt(blkEl.getAttribute("data--block-index"), 10);
      if (!isNaN(bi) && _doc && _doc.blocks[bi] && _nonEdTypes[_doc.blocks[bi].type]) {
        blkEl.contentEditable = "false";
        blkEl.querySelectorAll('pre, code, table, svg, mjx-container, .-mermaid-container, .-mermaid-error').forEach(function (el) {
          el.contentEditable = "false";
        });
      } else {
        // 非白名单块：其内部仍可能有 pre/code/table/svg（如嵌套），按首屏的通用列表补一遍
        blkEl.querySelectorAll('mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error').forEach(function (el) {
          el.contentEditable = "false";
        });
      }
    }
    // ② 灯箱：`attachImageLightbox` 不是幂等的 ⇒ 只对本批块调用（传入块集合，不传 preview）
    var MP = window.MemoriaMarkdownPreview;
    if (MP && typeof MP.attachImageLightbox === "function") {
      for (var k = 0; k < madeEls.length; k++) {
        var e2 = madeEls[k];
        if (!e2 || !e2.querySelector || !e2.querySelector("img")) continue;
        try { MP.attachImageLightbox(e2); } catch (_) { /* 可选增强 */ }
      }
    }
  }

  /** 对新物化的块渲染 mermaid（只处理这批块里的 `code.language-mermaid`）。
   *
   *  ⚠️ 2026-10-22 P0 修复：滚动批次原先**没有**这一步 ⇒ 物化后的 mermaid 永远显示源码
   *  （交互文本门禁实测：golden 是已渲染的 SVG/CSS，actual 是 `graph LR x["x(k)"] --> ...` 源码）。
   *  首屏路径（renderPreview）与编辑路径（_paintBlockSpan）都有对应调用，唯独滚动批次漏了。
   *  `renderMermaidBlocks(scope)` 接受任意容器 ⇒ 传入每个新块即可，作用域天然限定在本批。 */
  function _lazyRenderMermaidIn(madeEls) {
    var MP = window.MemoriaMarkdownPreview;
    if (!MP || typeof MP.renderMermaidBlocks !== "function" || !madeEls || !madeEls.length) return;
    for (var i = 0; i < madeEls.length; i++) {
      var el = madeEls[i];
      if (!el || !el.querySelector) continue;
      // 只有确实含 mermaid 源码的块才调（避免每块都起一次渲染流程）
      if (!el.querySelector("code.language-mermaid")) continue;
      try { MP.renderMermaidBlocks(el); } catch (e) { log("render", "lazy mermaid ERR " + ((e && e.message) || e)); }
    }
  }

  // ══ 2026-10-22「物化 / 排版解耦」的合并器 ═══════════════════════════════════════
  // 目的：`typesetPromise` **每次调用有显著固定开销**（实测 v4 1.27ms/公式 vs v5 更碎批次 2.80ms/公式）。
  //   物化批次（每批 ≤100 块）与 typeset 调用**脱钩**：把待排块累积起来，合并成一次调用。
  // 三条保证：
  //   ① **不会长期不排**：硬上限 `LAZY_MATH_MERGE_MAX_WAIT = 500ms` 到点必排；
  //   ② **不会永久漏排**：token 守卫失败（文档已换）时，**已累积的块不丢弃**（它们已在 DOM 里，
  //      但本函数负责"已请求"语义）—— 做法是把队列**保留**并重试一次调度，由下一轮/新文档收走；
  //   ③ **不重复排**：排完即清空队列；对已排过的元素再排是幂等空扫，但有成本，故仍避免。
  var _lazyMathQueue = null;        // Array<Element>：待排版的块（本批新物化且含公式）
  var _lazyMathQueueTimer = null;   // 硬上限计时器
  var LAZY_MATH_MERGE_MAX_WAIT = 500;   // ms：合并窗口上限（到点必排，保证公式不会长期不显示）
  var LAZY_MATH_MERGE_IDLE = 120;       // ms：空闲合并窗口（拖到底期间把多批合并成一次）
  var LAZY_MATH_DEFER_MAX = 1000;       // ms：为"让路给物化"最多推迟多久（防公式永不上屏）

  // ══ 2026-10-22 方案 C：**排版前隐藏公式源码**（metrics 裁决）═══════════════════════════
  // 依据：08 章拖到 80%，源码态帧仅 9/492（2%）但**面积峰值 89.9%、持续 375ms** ⇒ 用户看到大片 `$…$`。
  //   方案 A（整块骨架）不可行：08/03 章含公式块占 63.7~65.4% ⇒ 会变成大片骨架，更糟。
  //   方案 B（同步 typeset）会让单帧 300ms+ ⇒ 回到刚消除的长帧问题。
  //   ⇒ C：物化批次给"含公式的块"打 `-math-pending`，CSS 用 **`visibility:hidden`**（**保留布局**，
  //      不引发高度漂移 —— R1 回退项不可再碰），该批 typeset 完成（含异常）后**finally 式**移除。
  //
  // ⚠️ 漏清理是本方案最大风险（公式永久不可见 > 看到源码）。四条真实路径都要覆盖：
  //   ① typeset 抛异常 → `finally`
  //   ② 批次被 defer 推迟 / 被公式上限切分 → 只给**真正进入本次 typeset 的那批**打标记；余量不打
  //   ③ 文档切换 / token 作废 → `_lazyRevealAllMathPending()` 兜底全清
  //   ④ 已物化未排版的存量块（缓存恢复/跳转）→ 同样走 enqueue 时打标
  //   做法：用 WeakSet 记录"本批打了标记的元素"，只有那批 reveal 才清；另加全局兜底清扫。
  var _lazyHiddenByBatch = null;   // WeakSet<Element>：当前被隐藏的块（供诊断/兜底）

  /** 给一批块打 `-math-pending`（只对**真的含公式**的块；不改变布局，仅 visibility）。 */
  function _lazyHideMathIn(els) {
    if (!els || !els.length) return 0;
    if (!_lazyHiddenByBatch) _lazyHiddenByBatch = new WeakSet();
    var n = 0;
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (!el || !el.classList || el.classList.contains("-math-pending")) continue;
      // 只有"确实有未排版公式"的块才隐藏（已排好的 mjx-container 不该被藏）
      var hasRaw = el.querySelector && el.querySelector(".-math, .-math-block");
      if (!hasRaw) continue;
      el.classList.add("-math-pending");
      _lazyHiddenByBatch.add(el);
      n++;
    }
    if (n) log("lazy", "math hidden for typeset: " + n + " blocks");
    return n;
  }

  /** 移除一批块的 `-math-pending`（幂等；只清传进来的，不动别的批）。 */
  function _lazyRevealMathIn(els) {
    if (!els || !els.length) return 0;
    var n = 0;
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (!el || !el.classList || !el.classList.contains("-math-pending")) continue;
      el.classList.remove("-math-pending");
      if (_lazyHiddenByBatch) _lazyHiddenByBatch["delete"](el);
      n++;
    }
    if (n) log("lazy", "math revealed: " + n + " blocks");
    return n;
  }

  /** **兜底全清**（文档切换 / token 作废 / teardown）：保证不会有块永久停在隐藏态。 */
  function _lazyRevealAllMathPending() {
    try {
      var preview = $("#preview");
      if (!preview) return 0;
      var els = preview.querySelectorAll(".-math-pending");
      if (!els.length) return 0;
      for (var i = 0; i < els.length; i++) els[i].classList.remove("-math-pending");
      if (_lazyHiddenByBatch) _lazyHiddenByBatch = null;
      log("lazy", "math revealed (sweep): " + els.length + " blocks");
      return els.length;
    } catch (_) { return 0; }
  }
  // ★ deferral 总开关：**默认关**（2026-10-22 实测负收益：median 273→381ms、CV 28%→68%）。
  //   保留开关以便**同一运行内 A/B**（跨运行比较受机器状态/WebView2 缓存影响，不可靠）。
  //   可用 `window.__MEMORIA_DEFER` 运行时覆盖（CDP 注入，免改代码）。
  var LAZY_MATH_DEFER_ENABLED = false;
  function _deferEnabled() {
    if (typeof window.__MEMORIA_DEFER === "boolean") return window.__MEMORIA_DEFER;
    return LAZY_MATH_DEFER_ENABLED;
  }
  var LAZY_MATH_FORMULAS_SCROLLING = 60;   // 滚动中单批公式上限（≈60×1.27≈76ms）
  var LAZY_MATH_FORMULAS_IDLE = 200;       // 静止时单批公式上限（≈200×1.27≈254ms，静止可接受）

  /** W3.2：typeset 单批上限的**运行时覆盖**（同一 build/实例内交替 A/B 用；CDP 注入即可，无需改码）。
   *  背景（真机 08 章 4001 块、逐位置帧采样）：第二遍（向上）在 45%/70%/90% 的长帧不是物化、
   *  也不是淘汰，而是 **MathJax 单批 typeset**——LoAF 里 `styleAndLayoutStart` 之前的 script 段
   *  与 `MathJax.typesetPromise` 的包裹耗时对得上（45%: 单批 max 41–58ms / 帧 88–108ms）。
   *  向上滚动时队列更容易在"静止窗口"里攒大批（idle=200），一次 flush 就是一根长帧。
   *  这条覆盖只影响**每批切多大**，不改变总公式量与排版顺序（剩余批次回到队列下一轮继续）。 */
  function _mathBatchCaps() {
    var sc = (typeof window.__MEMORIA_MATH_BATCH_SCROLLING === "number" && window.__MEMORIA_MATH_BATCH_SCROLLING > 0)
      ? window.__MEMORIA_MATH_BATCH_SCROLLING : LAZY_MATH_FORMULAS_SCROLLING;
    var idle = (typeof window.__MEMORIA_MATH_BATCH_IDLE === "number" && window.__MEMORIA_MATH_BATCH_IDLE > 0)
      ? window.__MEMORIA_MATH_BATCH_IDLE : LAZY_MATH_FORMULAS_IDLE;
    return { scrolling: sc, idle: idle };
  }
  var _lazyMathDeferStart = 0;          // 本批次开始被推迟的时刻
  var _lazyMathDeferred = false;        // 当前是否正处于"让路推迟"中（供诊断）

  /** **视口内是否还有占位块**（决定 typeset 是否必须让路）。
   *  用二分定位（占位块是 `.-preview-content` 直接子元素、布局位置单调），只 O(log n) 次测量。 */
  function _lazyViewportHasPlaceholder() {
    try {
      var preview = $("#preview");
      if (!preview) return false;
      var cc = preview.querySelector(".-preview-content");
      if (!cc) return false;
      var phs = cc.querySelectorAll(".-pv-placeholder");
      if (!phs.length) return false;
      var pane = document.getElementById("preview-pane") || preview.parentElement;
      if (!pane) return false;
      var pr = pane.getBoundingClientRect();
      var n = phs.length, a = 0, b = n - 1, firstHit = n;
      while (a <= b) {                       // 第一个 bottom >= 视口顶 的占位块
        var m = (a + b) >> 1;
        if (phs[m].getBoundingClientRect().bottom >= pr.top) { firstHit = m; b = m - 1; } else { a = m + 1; }
      }
      if (firstHit >= n) return false;
      // 它是否真的在视口内（top <= 视口底）⇒ 是则说明视口里有占位
      return phs[firstHit].getBoundingClientRect().top <= pr.bottom;
    } catch (_) { return false; }
  }

  /** 把一批块加入待排队列，并调度合并排版。
   *
   *  2026-10-22 P0 之后：入队的**不再过滤"是否含公式"**（正是那次过滤漏掉了 `-image-block` 的裸文本 `$A$`）。
   *  所以队列现在可能涨得很快 ⇒ 用 `LAZY_MATH_QUEUE_MAX_BLOCKS` 给**单次 typeset 的块数**设上限，
   *  防止合并窗口（120ms）内累积上千块后一次 `typesetPromise` 变长、又涨回 maxGap。
   *  超限 ⇒ **先 flush 现有队列**，再入新块（调用次数略增，但换来单次调用体积受控）。 */
  var LAZY_MATH_QUEUE_MAX_BLOCKS = 400;   // 单次 typeset 最多扫这么多块（含无公式块；公式数未变则成本基本不变）

  function _lazyEnqueueMath(els) {
    if (els && els.length) {
      if (!_lazyMathQueue) _lazyMathQueue = [];
      for (var i = 0; i < els.length; i++) _lazyMathQueue.push(els[i]);
      // 队列超限 ⇒ 立即排掉现有的（避免单次 typeset 过大）
      if (_lazyMathQueue.length >= LAZY_MATH_QUEUE_MAX_BLOCKS) {
        _lazyForceScheduleMathFlush();
        return;
      }
    }
    if (!_lazyMathQueue || !_lazyMathQueue.length) return;   // 空队列 ⇒ 无需调度
    _lazyScheduleMathFlush();
  }

  /** 调度一次合并排版 —— **MemoriaScheduler 作业**（P2 派生视图，同起点合并）。
   *
   *  保留 `LAZY_MATH_MERGE_MAX_WAIT` 硬上限计时器：它是**截止期**（deadline），不是调度源 ——
   *  保证合并窗口内公式一定会排；即使调度器回调被推迟，到点也会直接 flush。
   *  ⚠️ 单独抽出来是必须的：**token 回收路径**要"队列已填、只补调度"，
   *  若复用 `_lazyEnqueueMath([])` 会被它的空数组早退挡掉 ⇒ 回收的块**永远不排**（正是要修的漏排）。 */
  function _lazyMathStartKey() {
    if (!_lazyMathQueue || !_lazyMathQueue.length) return "none";
    var el = _lazyMathQueue[0];
    var bi = (el && el.getAttribute) ? parseInt(el.getAttribute("data--block-index"), 10) : NaN;
    return isNaN(bi) ? String(_lazyMathQueue.length) : String(bi);
  }

  function _lazyScheduleMathFlush() {
    if (!_lazyMathQueue || !_lazyMathQueue.length) return;
    // 硬上限：从**首次入队**起算，500ms 后无条件排（即便还在持续物化）⇒ 公式不会长期停在 `$…$`
    if (!_lazyMathQueueTimer) {
      _lazyMathQueueTimer = setTimeout(function () {
        _lazyMathQueueTimer = null;
        _lazyFlushMathNow("max-wait");
      }, LAZY_MATH_MERGE_MAX_WAIT);
    }
    var S = _lazyJobScheduler();
    if (!S || typeof S.schedule !== "function") {
      // 防御性回退（正常生产路径不会走到：scheduler.js 先于 app.js 加载）
      setTimeout(function () { _lazyFlushMathNow("timer"); }, 0);
      return;
    }
    S.schedule({
      kind: "lazy_typeset",
      key: "lazy-typeset:" + _lazyMathStartKey(),
      priority: 2,            // P2 派生：让物化（P1 交互）先跑
      replace: true,
      gen: (typeof S.epoch === "function") ? S.epoch() : 0,
      dropStale: true,
      run: function () { _lazyFlushMathNow("scheduler"); },
    });
  }

  /** 把队列里的块合并成**一次** typesetPromise；进 `_mathPending` 链（保持"已请求批次排完"语义）。
   *
   *  2026-10-22 P0 三处加固（Lead 定性为真 bug：03 章 R1 跳转 `$A$`/`$\mu$` 未排 ⇒ 可见题注残留源码）：
   *   ① **token 判定要区分"重渲"与"换文档"**（根因）：
   *      `state.previewToken` 每轮渲染都 +1（同文档跳转/重渲也会变），而 `state.doc.path` 只在**换文档**时变。
   *      原实现只看 token ⇒ 同文档重渲时把**仍然有效**的块整批拦下 ⇒ 队列孤儿 ⇒ 那些块永不排版。
   *      现在：**path 未变 ⇒ 文档没换 ⇒ 直接排**（不拦）；path 变了 ⇒ 才过滤 `isConnected` 后回收/丢弃。
   *   ② 全程 **try/finally**：`finally` 里队列非空 ⇒ **无条件续命调度**（异常不再让队列变孤儿）。
   *   ③ token 分支的重新调度走 `_lazyForceScheduleMathFlush()`：**不受幂等守卫影响**，保证一定有一次 flush。 */
  function _lazyFlushMathNow(reason) {
    if (!_lazyMathQueue || !_lazyMathQueue.length) return;
    var batch = _lazyMathQueue;
    _lazyMathQueue = null;
    if (_lazyMathQueueTimer) { clearTimeout(_lazyMathQueueTimer); _lazyMathQueueTimer = null; }
    if (!window.MathJax || typeof window.MathJax.typesetPromise !== "function") return;

    // ★ 2026-10-22（Lead 长帧归因定死了方向）：**typeset 必须给物化让路**。
    //   实测：gap=672.8ms / mjx+246 / ph-0 / 视口占位=15 ⇒ **纯 typeset 帧把物化挤掉，用户在黑屏**。
    //   双 rAF 让出不够：让出后 typeset 仍是一大块，物化的 `setTimeout(0)` 排在它后面。
    //
    //   ⚠️ 判据**不是** `_lazyPending.size`：它表示"视口外 ±2 屏的**预取**工作"，
    //      滚动时几乎永远非空 ⇒ 拿它判会把"用户看得见的排版"无限推迟。
    //      正确判据 = **视口内是否还有占位块**（`_lazySyncNeeded` 或二分实测视口占位）。
    //   防饿死：最多推迟 `LAZY_MATH_DEFER_MAX`（1s），到点必排 ⇒ 公式不会永不上屏。
    // ⚠️ 2026-10-22 **可关开关**（Lead 实测 deferral 为负收益，且跨运行比较不可靠）：
    //   同口径 5 轮：`40474734`（无 defer）median 273ms/CV 28%；`8cc1da1c`（+defer）median 381ms/CV 68%
    //   ⇒ **deferral 方向证伪**（中位 +108ms、长尾 1345ms）。
    //   推断：推迟 typeset 期间那些块**仍占着视口位置**、物化并没变快；而 1s 上限造成"到点集中爆排" ⇒ 长尾。
    //   保留为开关是为了能在**同一运行内 A/B**（关→开→开→关交替，消除跨运行/缓存顺序效应）。
    //   默认 **false**（当前实测负收益）。置 true 可复现 defer 行为。
    if (_deferEnabled() && reason !== "force-deadline") {
      var nowMs = (window.performance && performance.now) ? performance.now() : Date.now();
      if (!_lazyMathDeferStart) _lazyMathDeferStart = nowMs;
      var deferredTooLong = (nowMs - _lazyMathDeferStart) >= LAZY_MATH_DEFER_MAX;
      if (!deferredTooLong && _lazyViewportHasPlaceholder()) {
        _lazyMathDeferred = true;
        // 把批次放回队列头部，稍后重试（不动 `_lazyMathDeferStart`，让 1s 上限累计）
        if (!_lazyMathQueue) _lazyMathQueue = [];
        _lazyMathQueue = batch.concat(_lazyMathQueue);
        log("lazy", "typeset DEFERRED for materialization: blocks=" + batch.length + " (defer " + Math.round(nowMs - _lazyMathDeferStart) + "ms)");
        _lazyForceScheduleMathFlush();
        return;
      }
    }
    _lazyMathDeferStart = 0;
    _lazyMathDeferred = false;

    // ★ 2026-10-22 ②（Lead：单批 246 公式 ≈300ms+ 独占主线程）：
    //   **滚动期间更严**：最近 300ms 有 scroll ⇒ 单批 ≤ `LAZY_MATH_FORMULAS_SCROLLING`(60) 公式；
    //   静止时放宽到 `LAZY_MATH_FORMULAS_IDLE`(200)。超出部分**留回队列**，下一轮再排。
    //   W3.2：两档都可经 `window.__MEMORIA_MATH_BATCH_{SCROLLING,IDLE}` 覆盖（同实例 A/B）。
    var _caps = _mathBatchCaps();
    var batchLimit = _lazyIsScrolling() ? _caps.scrolling : _caps.idle;
    var fAcc = 0, cut = batch.length;
    for (var fi = 0; fi < batch.length; fi++) {
      var _f = _countBlockFormulas(_doc && _doc.blocks ? _doc.blocks[parseInt(batch[fi].getAttribute("data--block-index"), 10)] : null);
      if (fAcc + _f > batchLimit && fi > 0) { cut = fi; break; }
      fAcc += _f;
    }
    if (cut < batch.length) {
      var rest = batch.slice(cut);
      batch = batch.slice(0, cut);
      if (!_lazyMathQueue) _lazyMathQueue = [];
      _lazyMathQueue = rest.concat(_lazyMathQueue);
      log("lazy", "typeset batch SPLIT (" + (_lazyIsScrolling() ? "scrolling" : "idle") + " limit=" + batchLimit + "): this=" + batch.length + " rest=" + rest.length);
    }

    // ★ 方案 C：给**真正进入本次 typeset 的这批**打隐藏标记（切分后的 `rest` 不打 —— 它们还没排）。
    //   打标在这一刻（已确定要排），保证"隐藏的块一定会被 reveal"。
    var hiddenBatch = batch.slice();   // 记下本批元素，供 finally reveal
    _lazyHideMathIn(hiddenBatch);

    var token = state.previewToken;
    var pathAt = (state.doc && state.doc.path) || "";   // ★ 记下"这批块属于哪个文档"
    var prev = state._mathPending;
    var chain = prev && typeof prev.then === "function" ? prev.catch(function () {}) : Promise.resolve();
    state._mathPending = chain.then(function () {
      try {
        var pathNow = (state.doc && state.doc.path) || "";
        // ★ 关键：**文档没换 ⇒ 不拦**。token 变化只代表"又重渲了一轮"，这些块仍是当前文档的一部分，
        //   必须照常排版（否则就是 R1 跳转漏排的根因）。
        if (pathNow === pathAt) {
          // ★ 2026-10-22 task-76：**先剔除已被工作集淘汰的块再排版**。
          //   本批在入队后可能已被 `lazy_evict` 换出（快拖时几乎必然发生）。对已 detached 的块排版
          //   会创建 `MathItem`（`start.node`/`typesetRoot` 都在文档外），而淘汰批的 `typesetClear`
          //   **早已跑过** ⇒ 没人再清它 ⇒ `document.math` 无限增长（实测快拖 3 遍 16MB → 130MB、
          //   4455 条 item / 4446 条 detached）。这里直接不排，从源头断掉"给死块排版"。
          var liveBatch = batch.filter(function (el) { return el && el.isConnected; });
          if (!liveBatch.length) {
            log("lazy", "math merge SKIP (all " + batch.length + " blocks evicted)");
            _lazyRevealMathIn(hiddenBatch);
            return Promise.resolve();
          }
          if (liveBatch.length !== batch.length) {
            log("lazy", "math merge SKIP evicted blocks: " + (batch.length - liveBatch.length) + "/" + batch.length);
          }
          batch = liveBatch;
          log("lazy", "math merge typeset (" + reason + "): blocks=" + batch.length + (token !== state.previewToken ? " [retoken same-doc ⇒ still typeset]" : ""));
          // ★ 2026-10-22 修正（Lead 实测**最长连续源码态 1.3–1.8s**）：
          //   这里原来每次都要"让出 1 个宏任务 + **双 rAF**"才排。单看一批只多 2 帧，但
          //   **`_mathPending` 是串行链**：滚动时批次源源不断入队，每批都要在这条链上排队，
          //   每批再各等 2 帧 ⇒ 积压 N 批就是 2N 帧 ⇒ **入队速度 ≥ 出队速度 ⇒ 队列越积越长**
          //   ⇒ 这正是"公式 1.8s 还不上屏"的主因（不是单批 typeset 慢，是排队）。
          //   现在：**只在链上让出一个宏任务边界**（保证不与刚结束的物化同帧、且让链有机会推进），
          //   **不再等双 rAF**。单帧风险由下面的"公式数上限"和既有批次上限控制。
          return new Promise(function (r) { setTimeout(r, 0); }).then(function () {
            if (!window.MathJax || typeof MathJax.typesetPromise !== "function") return;
            return MathJax.typesetPromise(batch).catch(function (err) { log("render", "lazy typeset: " + (err && err.message)); });
          }).then(function () {
            // ★ 2026-10-23 task-72：排版完成 ⇒ 立刻把本批产物缓存成字符串（供换出后复用）。
            //   只序列化**仍 connected**的块；失败不影响 reveal/后续流程。
            try { _tsStoreEls(batch); } catch (_) {}
            // ★ 方案 C：**排版完成 ⇒ reveal**（成功路径）
            _lazyRevealMathIn(hiddenBatch);
          }, function (e2) {
            // ★ 方案 C：**排版失败也必须 reveal**（否则公式永久不可见 —— 比看到源码严重）
            log("lazy", "typeset FAILED, reveal anyway: " + ((e2 && e2.message) || e2));
            _lazyRevealMathIn(hiddenBatch);
          });
        }
        // 文档真的换了 ⇒ 这批 DOM 多半已脱离（仍连上的才回收，避免内存泄漏）
        var still = batch.filter(function (el) { return el && el.isConnected; });
        if (still.length) {
          log("lazy", "math merge: doc changed, re-queue connected blocks=" + still.length);
          if (!_lazyMathQueue) _lazyMathQueue = [];
          for (var i = 0; i < still.length; i++) _lazyMathQueue.push(still[i]);
        }
        return Promise.resolve();
      } catch (e) {
        log("lazy", "math merge THREW: " + ((e && e.message) || e));
        // 异常：把这批仍连上的块回队列，绝不丢弃
        try {
          var alive = batch.filter(function (el) { return el && el.isConnected; });
          if (alive.length) {
            if (!_lazyMathQueue) _lazyMathQueue = [];
            for (var k = 0; k < alive.length; k++) _lazyMathQueue.push(alive[k]);
          }
        } catch (_) {}
        return Promise.resolve();
      } finally {
        // ★ 方案 C 兜底：无论走哪条路径（成功/文档换/异常），本批打的标记都要清。
        //   这一层是"双保险"：上面 .then 已 reveal，这里再清一次是幂等的（`_lazyRevealMathIn` 会跳过已清的）。
        //   覆盖"文档真的换了"那条 return 分支 —— 那里没走排版，但标记已打，必须清。
        try { _lazyRevealMathIn(hiddenBatch); } catch (_) {}
        // ★ 队列非空 ⇒ 无条件续命（不受幂等守卫影响），杜绝"队列孤儿"
        try {
          if (_lazyMathQueue && _lazyMathQueue.length) _lazyForceScheduleMathFlush();
        } catch (_) {}
      }
    });
  }

  /** 强制调度一次合并排版：**清除截止期计时器**，保证一定有一次 flush。
   *  用于"队列孤儿"救援（token 变化 / 异常回队）：普通 `_lazyScheduleMathFlush` 可能因
   *  同键合并而被顶替，但 `replace: true` 的语义本身就是"用新作业顶替旧的排队作业"
   *  ⇒ 重新 schedule 后**一定**有一个待执行作业；若已有作业在跑，会再追加一个。
   *  ⚠️ 2026-10-22 task-65：不再用 `setTimeout(0)` 直排（那是第二个调度源，正是要消除的竞争）。 */
  function _lazyForceScheduleMathFlush() {
    if (!_lazyMathQueue || !_lazyMathQueue.length) return;
    if (_lazyMathQueueTimer) { clearTimeout(_lazyMathQueueTimer); _lazyMathQueueTimer = null; }
    _lazyScheduleMathFlush();
  }

  // ══ 2026-10-22（人追加约束）：**窗口尺寸 / UI 缩放 / 字体变化 ⇒ 必须重算占位** ══════════════
  // 硬化前的实现：占位高度与首屏物化量都硬编码 ⇒ 换字体、Ctrl+±、拖窗口后布局全错、上跳复发。
  // 现在：监听 resize / visualViewport.resize / DPR 变化 ⇒ 重新量度量 → 重设所有占位高度
  //   → 重算视口物化窗口并补物化 → **用 data--src-line 锚定滚动位置**（绝不用像素锚）。
  var _lazyResizeTimer = null;
  var _lazyDPRMedia = null;
  var _lazyResizeBound = false;

  /** 取"当前视口顶部第一个有行号的块"的源行号，作为重算后的滚动锚点。
   *  **用行号而不是像素**：像素在缩放/尺寸变化后完全失去意义，行号是稳定的。 */
  function _lazyCaptureAnchorLine(pane) {
    try {
      var cc = pane ? pane.querySelector(".-preview-content") : null;
      if (!cc) return null;
      var paneTop = pane.getBoundingClientRect().top;
      var els = cc.querySelectorAll(".-src-block[data--src-line]");
      for (var i = 0; i < els.length; i++) {
        var r = els[i].getBoundingClientRect();
        if (r.bottom > paneTop) {                    // 第一个"底边在视口内/下方"的块 = 视口顶部那块
          var l = parseInt(els[i].getAttribute("data--src-line"), 10);
          if (!isNaN(l)) return l;
        }
      }
    } catch (_) {}
    return null;
  }

  /** resize / zoom 后重建：重算度量 → 重设全部占位高度 → 补物化视口 → 按行号恢复滚动位置。 */
  function _lazyHandleViewportChange(reason) {
    if (!_lazyMaterializeEnabled(_doc) || !_doc || !_doc.blocks) return;
    var pane = document.getElementById("preview-pane");
    var preview = $("#preview");
    if (!pane || !preview) return;
    var cc = preview.querySelector(".-preview-content");
    if (!cc) return;
    if (!cc.querySelector(".-pv-placeholder")) return;   // 已全物化 ⇒ 无需重算

    // ① 锚点必须在**重设高度之前**采（用旧布局找"视口顶部是哪个源行"）
    var anchorLine = _lazyCaptureAnchorLine(pane);
    var oldScrollTop = pane.scrollTop;

    // ② 重新量度量（cc 已挂载 ⇒ 这里的量法与 `_buildLazyPreview` 完全一致）
    _pvMetrics = _measurePreviewMetrics(pane, cc);
    log("lazy", "resize metrics: fs=" + _pvMetrics.fs + "px lhPx=" + _pvMetrics.lhPx.toFixed(2) +
      "px paneW=" + Math.round(_pvMetrics.paneW) + " src=" + _pvMetrics.src + " reason=" + (reason || ""));

    // ③ 重设**所有未物化占位块**的高度（已物化的真块不动；它们的 min-height 由解锁机制处理）
    var phs = cc.querySelectorAll(".-pv-placeholder");
    for (var i = 0; i < phs.length; i++) {
      var idx = parseInt(phs[i].getAttribute("data--block-index"), 10);
      if (isNaN(idx) || idx >= _doc.blocks.length) continue;
      phs[i].style.height = Math.round(_pvBlockH(_doc, idx)) + "px";
      // 2026-10-22 1d：度量已变 ⇒ 换出时记录的真块高度作废（否则 `_materializeRange` 会用旧高度锁高）
      phs[i].removeAttribute("data--pv-h");
      phs[i].removeAttribute("data--pv-r");
    }

    // ④ 重算视口物化窗口并补物化：按新度量定位"锚点附近 ± 2 屏"的块
    if (anchorLine != null) {
      var viewH = pane.clientHeight || (window.visualViewport && visualViewport.height) || 720;
      var lh = _pvM().lhPx;
      // 粗定位：用锚点行号找块下标（block 的 srcLine/srcLineEnd 覆盖该行）
      var centerIdx = 0;
      for (var bi = 0; bi < _doc.blocks.length; bi++) {
        var b = _doc.blocks[bi];
        if (b && b.srcLine > 0 && b.srcLineEnd >= anchorLine && b.srcLine <= anchorLine) { centerIdx = bi; break; }
        if (b && b.srcLine > anchorLine) { centerIdx = bi; break; }
      }
      var spanBlocks = Math.max(20, Math.ceil((viewH * 2) / Math.max(lh, 1)));
      var s0 = Math.max(0, centerIdx - Math.floor(spanBlocks / 2));
      _materializeRange(cc, _doc, s0, Math.min(_doc.blocks.length, centerIdx + spanBlocks));

      // ⑤ 恢复滚动位置：**重算后**用锚点块的当前位置补偿（不是恢复旧像素）
      try {
        var target = null;
        var all = cc.querySelectorAll(".-src-block[data--src-line]");
        for (var k = 0; k < all.length; k++) {
          var sl = parseInt(all[k].getAttribute("data--src-line"), 10);
          var se = parseInt(all[k].getAttribute("data--src-line-end"), 10);
          if (isNaN(sl)) continue;
          if (anchorLine >= sl && anchorLine <= (isNaN(se) ? sl : se)) { target = all[k]; break; }
        }
        if (target) {
          var delta = target.getBoundingClientRect().top - pane.getBoundingClientRect().top;
          pane.scrollTop = pane.scrollTop + delta;    // 让锚点块回到视口顶部
        } else {
          pane.scrollTop = oldScrollTop;              // 找不到锚点 ⇒ 退回旧像素（总比乱跳好）
        }
      } catch (_) { try { pane.scrollTop = oldScrollTop; } catch (__) {} }
    }

    log("lazy", "viewport change (" + reason + "): fs=" + _pvM().fs + " lh=" + Math.round(_pvM().lhPx) + " paneW=" + Math.round(_pvM().paneW) + " anchorLine=" + anchorLine);
    // ⑥ 重设后可能又有新块进入视口 ⇒ 触发一次批量物化
    _lazyScheduleFlush();
    _lazyScheduleEvict();   // 2026-10-22 1c：度量/窗口变了 ⇒ 保留窗口也变了，重新淘汰
  }

  /** 绑定 resize / visualViewport / DPR 监听（幂等，只绑一次）。 */
  function _bindLazyViewportWatchers() {
    if (_lazyResizeBound) return;
    _lazyResizeBound = true;
    var onAny = function (reason) {
      // 节流：resize 会高频触发，合并到一次（150ms）避免每次拖拽都全量重设占位
      if (_lazyResizeTimer) clearTimeout(_lazyResizeTimer);
      _lazyResizeTimer = setTimeout(function () {
        _lazyResizeTimer = null;
        try { _lazyHandleViewportChange(reason); } catch (e) { log("lazy", "viewport change ERR " + ((e && e.message) || e)); }
      }, 150);
    };
    try { window.addEventListener("resize", function () { onAny("window.resize"); }); } catch (_) {}
    try {
      if (window.visualViewport && window.visualViewport.addEventListener) {
        window.visualViewport.addEventListener("resize", function () { onAny("visualViewport.resize"); });
      }
    } catch (_) {}
    // DPR 变化（跨屏拖动 / 浏览器缩放）：matchMedia 对"当前 dppx"不再匹配时会触发
    try {
      var dpr = window.devicePixelRatio || 1;
      _lazyDPRMedia = window.matchMedia("(resolution: " + dpr + "dppx)");
      var dprHandler = function () { onAny("dpr.change"); };
      if (_lazyDPRMedia.addEventListener) _lazyDPRMedia.addEventListener("change", dprHandler);
      else if (_lazyDPRMedia.addListener) _lazyDPRMedia.addListener(dprHandler);
    } catch (_) {}
  }

  /** 拆掉滚动物化（换库/换文档/切走时清理，避免观察已移除的占位）。 */
  function _teardownLazyScrollMaterialization() {
    if (_lazyIO) { _lazyIO.disconnect(); _lazyIO = null; }
    if (_lazyPending) _lazyPending.clear();
    _lazyCollectAt = 0;
    // 2026-10-22 task-65：排版队列/截止期计时器也一并作废（DOM 即将被替换 ⇒ 队列里的元素不再有意义）。
    //   换文档/整篇重渲另由 `_lazyPipelineReset()` 提升 epoch，让排队中的调度作业陈旧丢弃。
    _lazyMathQueue = null;
    if (_lazyMathQueueTimer) { clearTimeout(_lazyMathQueueTimer); _lazyMathQueueTimer = null; }
    // 2026-10-22：被锁高块在换文档/关库时全部解锁并拆 IO，避免死引用与遗留 min-height
    _lazyReleaseMinHeight();
    if (_lazyLockedIO) { _lazyLockedIO.disconnect(); _lazyLockedIO = null; }
    _lazyLockedEls = null;
    // 2026-10-22 方案 C：换文档/关库时**兜底全清** `-math-pending`
    //（否则切换瞬间被打标但未排版的块会永久停在隐藏态 = 公式永久不可见）
    _lazyRevealAllMathPending();
    // 2026-10-22：resize 定时器与 DPR 监听也一并清（watcher 本身保持绑定，重进惰性路径会复用）
    if (_lazyResizeTimer) { clearTimeout(_lazyResizeTimer); _lazyResizeTimer = null; }
    _pvMetrics = null;   // 度量作废 ⇒ 下次渲染重新量
    // 2026-10-22 1c：工作集淘汰状态一并作废（旧块的 LRU 时钟/暂停标记对新 DOM 无意义）
    _lazyTouch = null;
    _lazyEvictSuspended = false;
    _lazyEvictQueuedPriority = 0;
  }

  // ════ 2026-10-22 阶段1c：**工作集淘汰**（缺页装入 + 换出）════════════════════════
  // 问题（08 章 4001 块实测）：惰性路径只装入不回收 ⇒ 滚到底 DOM 105,428 (25×)、堆 84.2MB (3.4×)、
  //   滚回顶 122,617 (29×)；第二遍滚动顶部帧 +320%~+421%。类比 OS 只缺页装入、从不换出。
  // 对策：把"视口 ±N 屏"之外的**已物化块退回占位形态**（`_makePlaceholder` → `real.replaceWith(ph)`），
  //   让真块子树脱离文档可被 GC。占位仍保留块身份/行号/高度 ⇒ 滚回时 IO 照常重新物化。
  //
  // 三条纪律：
  //   ① **不在滚动帧里做**：只由 `MemoriaScheduler` 的 P3 作业（`lazy_evict`）执行，滚动回调只 enqueue；
  //   ② **单批上限** `LAZY_EVICT_BATCH_MAX`，避免长帧；有余量则续排下一批（跨帧推进）；
  //   ③ 保留窗口 `LAZY_EVICT_KEEP_SCREENS` 必须 ≥ 物化预取（IO `rootMargin: 200%` = 2 屏）⇒ 不抖动。
  // 参数（初值，需真机 metrics 复核后调；**不凭感觉改**）：
  //   · `LAZY_EVICT_KEEP_SCREENS = 4`：视口上下各保留 4 屏（约 8 屏总量）；
  //   · `LAZY_EVICT_BATCH_MAX = 60`：单批淘汰 ≤60 块（按物化实测 0.65ms/块 ≈ 39ms，P3 可切片）；
  //   · `LAZY_EVICT_RECENT_MS`：LRU 时钟的"近期"窗口（评分按秒折算，不单独 pin）。
  var LAZY_EVICT_KEEP_SCREENS = 4;
  var LAZY_EVICT_BATCH_MAX = 60;
  var LAZY_EVICT_RECENT_MS = 1500;

  /** W3.2：淘汰单批上限的运行时覆盖（同实例 A/B；CDP 注入 `window.__MEMORIA_EVICT_BATCH_MAX`）。
   *  背景：逐位置帧采样里，第二遍向上的长帧除 typeset 外还有一段 `scheduler.js` 同步工作
   *  （LoAF: 12.8–14.1ms），与淘汰单批同步耗时同量级。pred 批尾零强制布局之后，单批拆小
   *  **不再**按批数付一次全篇 reflow ⇒ 可以只按"每帧预算"切，而不伤总量。 */
  function _lazyEvictBatchMax() {
    var v = window.__MEMORIA_EVICT_BATCH_MAX;
    return (typeof v === "number" && v > 0) ? v : LAZY_EVICT_BATCH_MAX;
  }

  var _lazyTouch = null;            // Array<number>：每个块最近一次物化/进入工作集的时刻（LRU 时钟）
  var _lazyEvictCount = 0;          // 本文件累计淘汰块数（诊断/metrics）
  var _lazyEvictSuspended = false;  // `__MEMORIA_MATERIALIZE_ALL`（门禁强制全量）期间/之后禁用淘汰

  // 2026-10-23 task-78：**淘汰防饥饿（pressure 升级）**。
  //   实测根因（见 results/t78-*）：惰性淘汰是 P3，物化是 P1、typeset 是 P2。长滚期间
  //   P1/P2 任一条队列持续非空时，调度器按优先级取作业 ⇒ P3 可以连续多帧甚至整轮滚动
  //   一次都跑不到。08 章 4001 块上注入 P2 积压后，6s 连续拖动里 `evictTotal` 只涨 49，
  //   物化块冲到 3228（= 只装入不回收）——这正是「偶发超 8 屏」的机制，且与机器快慢有关。
  //   对策：物化块数超过 `LAZY_EVICT_PRESSURE_SCREENS` 屏时，把**同一个** `lazy_evict`
  //   作业以 P1 排队（仍在调度器里执行，不新增任何手写调度）；压力解除后回到 P3。
  //   另外：因「物化优先」让路时不再把淘汰链丢掉（见 `_lazyEvictNow` ⑤ 前的 re-arm）。
  var LAZY_EVICT_PRESSURE_SCREENS = 4;
  var _lazyEvictQueuedPriority = 0;   // 0 = 当前没有已排队的 lazy_evict；1/3 = 该作业的优先级
  var _lazyEvictPendingSkips = 0;     // 因 `_lazyPending` 非空而让路的次数（诊断）
  var _lazyEvictPressureSchedules = 0;// 因超过压力阈值而升到 P1 的次数（诊断）


  // 2026-10-22 task-76：**淘汰单批耗时分解**（默认关闭 ⇒ `_evProf` 为 null，只多一次判空）。
  //   动机：`counters().max_frame_ms` 只给"整批最慢一次"，无法回答"淘汰 / typesetClear / BlockIndex 同步
  //   各占多少"，而调参（批上限 / 切片粒度）必须先知道这个比例。
  //   用法：页面内 `window.__MEMORIA_EVICT_PROFILE.enable()` → 滚一轮 → `.read()`；`.disable()` 关。
  //   口径：全部 `performance.now()` 差值，单位 ms；`mathClearMs` 含 `purgeMs`（后者是前者的子集）。
  var _evProf = null;
  function _evNow() { return (window.performance && performance.now) ? performance.now() : Date.now(); }
  window.__MEMORIA_EVICT_PROFILE = {
    enable: function () {
      _evProf = {
        batches: 0, blocks: 0, totalMs: 0,
        keepMs: 0, scanMs: 0, readMs: 0, applyMs: 0,
        blockIndexMs: 0, mathClearMs: 0, purgeMs: 0, anchorMs: 0,
        tailShMs: 0, tailAnchorReadMs: 0, tailWriteMs: 0,
        maxTotalMs: 0, maxMathClearMs: 0, maxApplyMs: 0, maxBlockIndexMs: 0,
        tailSkips: 0, tailVerifies: 0,
        blocksWithMath: 0, last: [],
      };
      return true;
    },
    disable: function () { _evProf = null; return true; },
    reset: function () { return this.enable(); },
    read: function () { return _evProf ? JSON.parse(JSON.stringify(_evProf)) : null; },
  };
  // 2026-10-22 1d：**换出高度稳定性**的可观测指标。
  //   问题（真机实测）：换出时用 `_placeholderHeight` 估值当占位高度，而估值与真块排版高度可能差
  //   上百 px（实测：真块 214px ⇒ 估值 25px、真块 415px ⇒ 估值 227px、真块 415→227 等），
  //   整篇 `scrollHeight` 因此随换出而漂移 ⇒ 用户滚回原处时**绝对位置**对不上（同一 scrollTop 看到的内容位移若干行）。
  //   对策 A：换出前量真块的**垂直占位体积**（rect.top → 下一块 rect.top，含塌陷外边距），
  //          直接用它当占位高度（治本；实测换出批次高度变化从 ±100~330px/块 降到累计 ≈0）；
  //   对策 B：淘汰批次用**视口顶部首个可见块**做锚点补偿 `scrollTop`（兜底残余高度变化）。
  //   `heightDriftPx` = 累计 |本批 scrollHeight 变化| —— 修复后应稳定在 0 附近；一旦增长即回归。
  var _lazyHeightDriftPx = 0;       // 累计 |scrollHeight 变化|（换出批次；metrics 量化用）
  var _lazyAnchorFixes = 0;         // 发生过 scrollTop 补偿的淘汰批次数（诊断）

  // ══ W3.3（2026-10-23）：**批尾强制布局**策略 ══════════════════════════════════════
  // 实测（`__MEMORIA_EVICT_PROFILE`，08 章 4001 块、快拖 1 轮 66 批）：
  //   keep 16.7% / scan 6.3% / apply 12.8% / typesetClear 5.0% / **批尾 58.7%**；
  //   批尾里 `pane.scrollHeight` 是唯一真正强制布局的读（anchor rect 紧随其后，同一次布局）。
  //   ⇒ 每批一次全篇 reflow，批均 ~21ms、尖峰 150–180ms；**不是块数**（每块边际仅 0.077ms）。
  //
  // 三种模式（运行时可切，供**同 build 交错 A/B**）：
  //   · `legacy`：现行为（读 scrollHeight + anchor rect + 必要 scrollTop 补偿）
  //   · `noSh`  ：只去掉 scrollHeight 读，保留 anchor rect / 补偿（诊断用，隔离 scrollHeight 代价）
  //   · `pred`  ：批尾**零强制布局**。换出时占位高度 = 真块 advance 高度（差仅 ±0.05px/块），
  //               于是"视口上方内容高度变化"可由 `Σ(新占位高 - advH)` **预测**；累计超过阈值
  //               （或每 N 批）才在**渲染之后的空帧**做一次真实核对（此时布局已由渲染阶段完成，
  //               读取几乎免费），把实测误差记入 `heightDriftErrPx`。
  //   `pred` 模式不写 scrollTop：高度变化仅 ±亚像素，交给浏览器 scroll anchoring；
  //   实测 legacy 的 anchorFixes ≈ 10% 批次且 |Δ|<0.5px。
  // 默认 `pred`（批尾零强制布局）；`legacy`/`noSh` 仅用于同 build A/B 与诊断。
  var _tailLayoutMode = "pred";
  var _tailBatchCount = 0;          // pred：距上次核对的批数
  var _tailPredDriftPx = 0;         // pred：距上次核对的**有符号**预测高度变化（锚点上方）
  var _tailPredTotalPx = 0;         // pred：距上次核对的**有符号**预测全篇高度变化（用于核对 scrollHeight）
  var _tailPendingAbsDriftPx = 0;   // pred：距上次核对的 |预测全篇变化| 累加（诚实计入 heightDriftPx）
  var _tailShCache = 0;             // 上次真实读到的 pane.scrollHeight
  var _tailVerifyScheduled = false;
  var _tailVerifies = 0;            // 真实核对次数
  var _tailSkips = 0;               // 跳过强制布局的批数
  var _tailWouldFix = 0;            // pred：若按 legacy 的 0.5px 阈值"本应补偿"的批数（诊断）
  var _tailAnchorPredMax = 0;       // pred：|预测锚点位移| 最大值（px）
  var _tailDriftErrPx = 0;          // 核对时 |实测 - 预测| 累加（偏差告警）
  var _tailDeferredReadMs = 0;      // 延迟核对里 scrollHeight 读取耗时（应接近 0：布局已干净）
  var _TAIL_VERIFY_BATCHES = 8;
  var _TAIL_VERIFY_PX = 4;

  function _tailSetMode(m) {
    if (m !== "legacy" && m !== "noSh" && m !== "pred") return _tailLayoutMode;
    _tailLayoutMode = m;
    _tailBatchCount = 0;
    _tailPredDriftPx = 0;
    _tailPredTotalPx = 0;
    _tailPendingAbsDriftPx = 0;
    _tailShCache = 0;
    return _tailLayoutMode;
  }

  /** 在"渲染之后"的空帧做真实核对：rAF 回调在渲染前，因此再跳一个 setTimeout(0)
   *  ⇒ 该宏任务通常落在本帧渲染/布局完成之后，`scrollHeight` 读取不再触发布局。 */
  function _tailScheduleVerify() {
    if (_tailVerifyScheduled) return;
    _tailVerifyScheduled = true;
    var go = function () {
      setTimeout(function () {
        _tailVerifyScheduled = false;
        try { _tailVerifyNow(); } catch (_) {}
      }, 0);
    };
    if (window.requestAnimationFrame) requestAnimationFrame(go);
    else setTimeout(go, 16);
  }

  function _tailVerifyNow() {
    if (_tailLayoutMode !== "pred") {
      // 模式已切走（A/B 切换残留的延迟核对）⇒ 丢弃本次，避免污染另一种模式的统计。
      _tailPredDriftPx = 0;
      _tailPredTotalPx = 0;
      _tailPendingAbsDriftPx = 0;
      _tailBatchCount = 0;
      return;
    }
    var pane = document.getElementById("preview-pane");
    if (!pane) return;
    var t0 = _evNow();
    var sh = pane.scrollHeight;      // 布局已由渲染阶段完成 ⇒ 这里应是一次读缓存
    _tailDeferredReadMs += _evNow() - t0;
    if (_tailShCache > 0) {
      var pred = _tailShCache + _tailPredTotalPx;
      var err = sh - pred;
      if (Math.abs(err) > 0.5) _tailDriftErrPx += Math.abs(err);
    }
    // 诚实记账：跳过批次的 |预测变化| 计入高度漂移指标（实测/预测口径见 stats）。
    _lazyHeightDriftPx += _tailPendingAbsDriftPx;
    _tailShCache = sh;
    _tailPredDriftPx = 0;
    _tailPredTotalPx = 0;
    _tailPendingAbsDriftPx = 0;
    _tailBatchCount = 0;
    _tailVerifies++;
  }

  window.__MEMORIA_TAIL_LAYOUT = {
    getMode: function () { return _tailLayoutMode; },
    setMode: function (m) {
      var r = _tailSetMode(m);
      log("lazy", "tail-layout mode = " + r);
      return r;
    },
    stats: function () {
      return {
        mode: _tailLayoutMode,
        batches: _tailBatchCount,
        verifies: _tailVerifies,
        skips: _tailSkips,
        driftErrPx: Math.round(_tailDriftErrPx * 10) / 10,
        deferredReadMs: Math.round(_tailDeferredReadMs * 100) / 100,
        shCache: _tailShCache,
        predDriftPx: Math.round(_tailPredDriftPx * 100) / 100,
        predTotalPx: Math.round(_tailPredTotalPx * 100) / 100,
        wouldFix: _tailWouldFix,
        anchorPredMax: Math.round(_tailAnchorPredMax * 100) / 100,
        driftMode: _tailLayoutMode === "pred" ? "predicted+verified" : "measured",
      };
    },
    /** 静止（布局已干净）时强制结算一次：让本轮 skip 的预测漂移落到实测口径上。 */
    flushVerify: function () {
      if (_tailLayoutMode !== "pred") return false;
      _tailVerifyScheduled = false;
      try { _tailVerifyNow(); return true; } catch (_) { return false; }
    },
  };

  /** 触碰一个块（LRU 时钟）。越界/无时钟表 ⇒ 静默忽略。 */
  function _lazyTouchBlock(idx) {
    try {
      if (!_lazyTouch || idx < 0 || idx >= _lazyTouch.length) return;
      _lazyTouch[idx] = (window.performance && performance.now) ? performance.now() : Date.now();
    } catch (_) {}
  }

  /** 节点所属的块下标（`data--block-index`）；不在 `.-preview-content` 内 ⇒ -1。 */
  function _lazyBlockPosOfNode(node, cc) {
    try {
      var n = node;
      if (n && n.nodeType !== 1) n = n.parentElement;      // 文本节点 ⇒ 父元素
      if (!n || !n.closest) return -1;
      var el = n.closest("[data--block-index]");
      if (!el || !cc.contains(el)) return -1;
      var idx = parseInt(el.getAttribute("data--block-index"), 10);
      return isNaN(idx) ? -1 : idx;
    } catch (_) { return -1; }
  }

  /** 计算"保留窗口"：视口上下各 `LAZY_EVICT_KEEP_SCREENS` 屏对应的块下标区间。
   *  `cc.children` 按块序排列、位置单调 ⇒ 二分 O(log n)；**不做全量 getBoundingClientRect**。
   *  同时顺带二分出"视口顶边覆盖的块"（`anchorEl`）——换出后用它做滚动锚定补偿（B）。
   *  四次二分共享同一布局快照 ⇒ 仍是 O(log n) 次 rect 读，不随文档规模线性增长。 */
  function _lazyEvictKeepRange(cc, pane) {
    var paneRect = pane.getBoundingClientRect();
    var viewH = pane.clientHeight || paneRect.height || 720;
    var keepTop = paneRect.top - viewH * LAZY_EVICT_KEEP_SCREENS;
    var keepBottom = paneRect.bottom + viewH * LAZY_EVICT_KEEP_SCREENS;
    var centerY = (paneRect.top + paneRect.bottom) / 2;
    var kids = cc.children, n = kids.length;
    if (!n) return { lo: 0, hi: -1, center: 0, viewH: viewH, none: true, anchorEl: null, anchorLine: null };

    // 第一个 bottom >= keepTop
    var a = 0, b = n - 1, first = n;
    while (a <= b) {
      var m = (a + b) >> 1;
      if (kids[m].getBoundingClientRect().bottom >= keepTop) { first = m; b = m - 1; } else { a = m + 1; }
    }
    // 最后一个 top <= keepBottom
    var c = 0, d = n - 1, last = -1;
    while (c <= d) {
      var m2 = (c + d) >> 1;
      if (kids[m2].getBoundingClientRect().top <= keepBottom) { last = m2; c = m2 + 1; } else { d = m2 - 1; }
    }
    // 视口中心所在块（用于距离加权；找不到 ⇒ 0）
    var e = 0, f = n - 1, center = 0;
    while (e <= f) {
      var m3 = (e + f) >> 1;
      if (kids[m3].getBoundingClientRect().bottom >= centerY) { center = m3; f = m3 - 1; } else { e = m3 + 1; }
    }
    // 视口顶边覆盖的块（锚点；必须在保留窗口内，故换出不会动它 ⇒ 换出后仍可读它的 rect）
    var g = 0, h = n - 1, anchorPos = -1;
    var anchorEdge = paneRect.top + 1;
    while (g <= h) {
      var m4 = (g + h) >> 1;
      if (kids[m4].getBoundingClientRect().bottom > anchorEdge) { anchorPos = m4; h = m4 - 1; } else { g = m4 + 1; }
    }
    var anchorEl = anchorPos >= 0 ? kids[anchorPos] : null;
    var anchorLine = anchorEl ? parseInt(anchorEl.getAttribute("data--src-line"), 10) : NaN;
    function idxOf(pos) {
      if (pos < 0 || pos >= n) return pos < 0 ? -1 : n;
      var v = parseInt(kids[pos].getAttribute("data--block-index"), 10);
      return isNaN(v) ? pos : v;
    }
    return {
      lo: idxOf(first), hi: idxOf(last), center: idxOf(center), viewH: viewH, none: false,
      anchorEl: anchorEl, anchorLine: isNaN(anchorLine) ? null : anchorLine,
    };
  }

  /** 当前工作集是否已超过"压力阈值"（约 `LAZY_EVICT_PRESSURE_SCREENS` 屏的块数）。
   *  只用于**调度优先级**与"是否给物化让路"的判据 —— 不会因此换出保留窗口内的块。
   *  成本：1 次 `querySelectorAll` + 1 次 `children.length`（O(块数)，每批一次，可忽略）。 */
  function _lazyEvictIsPressure(cc, pane) {
    try {
      if (!cc || !pane) return false;
      var viewH = pane.clientHeight || pane.getBoundingClientRect().height || 720;
      var perScreen = Math.max(1, Math.ceil(viewH / Math.max(1, _pvM().lhPx)));
      var ph = cc.querySelectorAll(".-pv-placeholder").length;
      var mat = cc.children.length - ph;
      return mat > perScreen * LAZY_EVICT_PRESSURE_SCREENS;
    } catch (_) { return false; }
  }

  /** 物化之后调用：只有确实超过压力阈值才排 P1 淘汰；否则什么都不做
   *  （常规节奏仍由滚动停止 / 淘汰续排驱动，避免每批物化都多排一个作业）。 */
  function _lazyMaybeScheduleEvict() {
    try {
      var preview = $("#preview");
      var cc = preview ? preview.querySelector(".-preview-content") : null;
      var pane = document.getElementById("preview-pane");
      if (!cc || !pane) return;
      if (_lazyEvictIsPressure(cc, pane)) _lazyScheduleEvict(true);
    } catch (_) {}
  }

  /** 淘汰一批：把保留窗口之外的已物化块换回占位。**只应由调度器作业调用**。 */
  function _lazyEvictNow(reason) {
    if (!_lazyMaterializeEnabled(_doc) || !_doc || !_doc.blocks) return 0;
    if (_lazyEvictSuspended) return 0;
    var _pf = _evProf, _ptot0 = _pf ? _evNow() : 0, _pseg = _pf ? _evNow() : 0;
    // 单批增量起点（`_pf.*` 是累计值；max 必须按"单批增量"取，不能用累计值）
    var _pb = _pf ? { keep: _pf.keepMs, scan: _pf.scanMs, read: _pf.readMs, apply: _pf.applyMs,
      bi: _pf.blockIndexMs, math: _pf.mathClearMs, purge: _pf.purgeMs, total: _pf.totalMs } : null;
    try {
      var preview = $("#preview");
      if (!preview) return 0;
      var cc = preview.querySelector(".-preview-content");
      if (!cc || !cc.children.length) return 0;
      // 灯箱打开时不换出：放大中的图可能就在待换出的块里，移出文档会让灯箱引用空节点。
      if (document.querySelector(".-lightbox-overlay")) return 0;
      var pane = document.getElementById("preview-pane") || preview.parentElement;
      if (!pane) return 0;
      // task-78：超过压力阈值时**不再**给物化让路 —— 否则「P1 连续非空 ⇒ P3 永远排不到」
      //   会让工作集只涨不落（注入 P2 积压实测 6s 冲到 3228 块）。淘汰只动保留窗口外的块，
      //   不会影响视口可见性；压力解除后立即回到「物化优先」。
      var _pressureNow = _lazyEvictIsPressure(cc, pane);
      // 物化优先：还有待物化块 ⇒ 本帧让路；但**必须把淘汰链续上**，不能因一次让路就
      //   永久丢掉调度（滚动停止的 50ms debounce 在连续滚动时不会触发 ⇒ 旧实现会一直不回收）。
      if (!_pressureNow && _lazyPending && _lazyPending.size) {
        _lazyEvictPendingSkips++;
        _lazyScheduleEvict(false);
        return 0;
      }

      var blocks = _doc.blocks, N = blocks.length;
      if (!_lazyTouch || _lazyTouch.length !== N) _lazyTouch = new Array(N);

      var keep = _lazyEvictKeepRange(cc, pane);
      if (keep.none) return 0;
      if (_pf) { _pf.keepMs += _evNow() - _pseg; _pseg = _evNow(); }

      // ③ 保护区（**编辑模式也允许淘汰远处块**，否则永不回收）：
      //    · 当前选区锚点/焦点所在块及邻块（正在选字/拖选）；
      //    · `document.activeElement`（焦点在某个 contenteditable 里）；
      //    · `MemoriaEditHandler.blockEditMode` 正在编辑的节点（块编辑器/行内公式编辑器）。
      //    ⇒ 只保护"用户正踩着的块"，其余远处块照常换出。
      var selLo = -1, selHi = -1;
      function _protectNode(node) {
        var p = _lazyBlockPosOfNode(node, cc);
        if (p < 0) return;
        var lo = p - 1, hi = p + 1;
        if (selLo < 0) { selLo = lo; selHi = hi; }
        else { selLo = Math.min(selLo, lo); selHi = Math.max(selHi, hi); }
      }
      try {
        var sel = window.getSelection();
        if (sel && sel.rangeCount) { _protectNode(sel.anchorNode); _protectNode(sel.focusNode); }
      } catch (_) {}
      try { if (document.activeElement) _protectNode(document.activeElement); } catch (_) {}
      try {
        var EH = window.MemoriaEditHandler;
        if (EH && EH.blockEditMode) {
          var bm = EH.blockEditMode;
          _protectNode(bm.mathEl); _protectNode(bm.editor); _protectNode(bm.blockEl); _protectNode(bm.el);
        }
      } catch (_) {}

      // ④ 收集候选：已物化 + 在保留窗口外 + 不在保护区
      var nowMs = (window.performance && performance.now) ? performance.now() : Date.now();
      var materializedBefore = 0;
      var cand = [];
      for (var i = 0; i < cc.children.length; i++) {
        var el = cc.children[i];
        if (!el || !el.classList || el.classList.contains("-pv-placeholder")) continue;
        var idx = parseInt(el.getAttribute("data--block-index"), 10);
        if (isNaN(idx) || idx < 0 || idx >= N) continue;
        materializedBefore++;
        if (idx >= keep.lo && idx <= keep.hi) continue;
        if (selLo >= 0 && idx >= selLo && idx <= selHi) continue;
        cand.push({ idx: idx, el: el });
      }
      if (!cand.length) return 0;

      // ⑤ 距离加权 + LRU：远者先淘汰；同距离时"更久未访问"先淘汰。
      //    score = 屏距 + 冷度(秒)×0.05（60s 上限 ⇒ 最多加 3 屏，避免久置文档分数爆掉）。
      var perScreen = Math.max(1, Math.ceil((keep.viewH || 720) / Math.max(1, _pvM().lhPx)));
      for (var k = 0; k < cand.length; k++) {
        var c0 = cand[k];
        var distScreens = Math.abs(c0.idx - keep.center) / perScreen;
        var touched = _lazyTouch[c0.idx] || 0;
        var staleSec = Math.min(60, Math.max(0, (nowMs - touched) / 1000));
        c0.score = distScreens + staleSec * 0.05;
      }
      cand.sort(function (x, y) { return (y.score - x.score) || (Math.abs(y.idx - keep.center) - Math.abs(x.idx - keep.center)); });

      var batch = cand.slice(0, _lazyEvictBatchMax());
      if (_pf) { _pf.scanMs += _evNow() - _pseg; _pseg = _evNow(); }
      // ── ⑤.5【先读后写】换出高度/锚点必须在**任何 DOM 变更之前**量完 ───────────────────
      //   · `_advH[q]`：块的**垂直占位体积** = 本块 rect.top → 下一块 rect.top（含塌陷外边距）。
      //     ⚠️ 不能用 `rect.height`：真块内部的 `mjx-container`/`pre` 等外边距会**塌陷穿过**
      //     `.‑src-block`（本块 margin:0、无 padding/border），不进入本块 rect.height，但确实占版面。
      //     实测：62 个真块的 Σrect.height=3153px，Σ(top 到下一块 top)=3405px（相差 252px，单块最大 14px）。
      //     若用 rect.height 当占位高度，每次换出都会**丢掉这部分**⇒ scrollHeight 系统性缩水
      //     （实测 5%→35% 滚一轮缩 5204px）⇒ 用户绝对位置漂移。用 adv 才是"整篇高度不变"。
      //   · `_rectH[q]`：块自身 rect 高度（回滚物化时只锁到这个值，不能锁 adv ⇒ 否则会把
      //     塌陷外边距变成块内 padding，高度反而涨回去）。
      //   · `_anchorTop` / `_shBefore`：视口顶部锚点屏幕位置 + 本批前 scrollHeight（B 补偿/量化用）。
      //   这一段只有读：不会与写交错 ⇒ 整批仍只多一次布局（不是 60 次强制同步布局）。
      var _rectH = new Array(batch.length), _advH = new Array(batch.length);
      for (var q0 = 0; q0 < batch.length; q0++) {
        try {
          var _el0 = batch[q0].el;
          if (!_el0 || !_el0.parentNode) { _rectH[q0] = 0; _advH[q0] = 0; continue; }
          var _r0 = _el0.getBoundingClientRect();
          _rectH[q0] = _r0.height;
          var _nx0 = _el0.nextElementSibling;
          var _adv0 = (_nx0 && _nx0.getBoundingClientRect) ? (_nx0.getBoundingClientRect().top - _r0.top) : _r0.height;
          _advH[q0] = (_adv0 > 0) ? _adv0 : _r0.height;
        } catch (_) { _rectH[q0] = 0; _advH[q0] = 0; }
      }
      var _anchorEl = keep.anchorEl, _anchorTop = NaN, _shBefore = 0;
      try {
        if (_anchorEl && _anchorEl.parentNode) _anchorTop = _anchorEl.getBoundingClientRect().top;
        _shBefore = pane.scrollHeight;
      } catch (_) { _anchorTop = NaN; _shBefore = 0; }
      // W3.3：pred 模式用**预测**替代批尾读取。`_anchorIdx` = 视口顶部块下标；
      //   只有"位于锚点上方"的块高度变化才会移动视口（下方变化不影响当前位置）。
      var _anchorIdx = -1;
      try { if (_anchorEl) _anchorIdx = parseInt(_anchorEl.getAttribute("data--block-index"), 10); } catch (_) {}
      if (isNaN(_anchorIdx)) _anchorIdx = -1;
      if (_tailLayoutMode === "pred" && _tailShCache <= 0 && _shBefore > 0) _tailShCache = _shBefore;
      var _predAbove = 0;            // 本批：锚点上方内容高度的预测变化（px，有符号）
      var _predTotalPx = 0;          // 本批：全篇高度的预测变化（px，有符号）
      var _predAboveN = 0;
      var _predUnknown = false;

      var n = 0, evicted = null, _mathEvicted = null;
      if (_pf) { _pf.readMs += _evNow() - _pseg; _pseg = _evNow(); }
      for (var q = 0; q < batch.length; q++) {
        var it = batch[q];
        var real = it.el, bi = it.idx, blk = blocks[bi];
        if (!real || !blk || !real.parentNode) continue;
        try {
          // A. 清理该块的 `-math-pending` 标记（四层清理之一：换出即不再等排版）
          if (real.classList && real.classList.contains("-math-pending")) {
            real.classList.remove("-math-pending");
            if (_lazyHiddenByBatch) _lazyHiddenByBatch["delete"](real);
          }
          // B. 解除 min-height 锁 + 停止观察（否则 `_lazyLockedEls` 持死引用）
          _lazyReleaseMinHeight(real);
          // C. 生成占位（data--block-index / data--src-line 由 AST 决定）
          var ph = _makePlaceholder(blk, bi, _doc);
          // ★★ 治本（A）：**用换出前的真实占位体积**覆盖估值 —— 估值与真块排版高度可差上百 px
          //  （实测：真块 214px ⇒ 估值 25px；真块 415px ⇒ 估值 227px），用估值换出会让整篇
          //  scrollHeight 漂移 ⇒ 用户滚回原处时绝对位置对不上。
          //  `data--pv-h`（adv，供诊断）/ `data--pv-r`（块自身 rect 高，回滚物化时锁高）
          //  ⇒ 保证"换出 → 滚回物化"这一整圈高度不变。
          var _advHv = _advH[q], _rectHv = _rectH[q];
          if (_advHv > 0) {
            ph.style.height = (Math.round(_advHv * 10) / 10) + "px";
            ph.setAttribute("data--pv-h", String(Math.round(_advHv * 10) / 10));
          }
          if (_rectHv > 0) ph.setAttribute("data--pv-r", String(Math.round(_rectHv * 10) / 10));
          // W3.3：预测"锚点上方内容高度变化" —— 占位高 = round(adv, 0.1) ⇒ 每块误差 ≤0.05px。
          if (_advHv > 0) {
            var _newHv = Math.round(_advHv * 10) / 10;
            _predTotalPx += (_newHv - _advHv);
            if (bi < _anchorIdx) {
              _predAbove += (_newHv - _advHv);
              _predAboveN++;
            }
          } else {
            _predUnknown = true;   // 量不到 advance 高度的块 ⇒ 预测不可信，本批结束时核对
          }
          // 2026-10-22 task-70：换出前登记"含 MathJax 产物"的块；整批换出后统一 typesetClear（见下）。
          //   必须在 `replaceWith` 之前/之后但**子树仍在 `real` 内**时清理；不能先 remove 子树。
          if (real.querySelector && real.querySelector("mjx-container, .-math, .-math-block")) {
            if (!_mathEvicted) _mathEvicted = [];
            _mathEvicted.push(real);
          }
          real.replaceWith(ph);
          _lazyBlockEls[bi] = ph;
          // 2026-10-22 task-70：BlockIndex 的 handle 仍持有换出前的 `domEl`（真块）⇒ 即使 DOM 已
          //   换出，`MemoriaApp.blockIndex.blocks()[i].domEl` 仍钉住整棵子树（实测 mermaid 块
          //   经 `byOrder → domEl → -mermaid-pan → SVGSVGElement` 被保留）。这里把 handle 的
          //   `domEl` 同步成新占位；`BI.get(id)` 是 O(1)，不是全表扫描。
          try {
            var _pbi = _pf ? _evNow() : 0;
            var _bid = real.getAttribute ? real.getAttribute("data-block-id") : null;
            if (_bid && BI && typeof BI.get === "function") {
              var _bh = BI.get(_bid);
              if (_bh && _bh.domEl === real) _bh.domEl = ph;
            }
            if (_pf) _pf.blockIndexMs += _evNow() - _pbi;
          } catch (_) {}
          // D. 新占位重新纳入 IO ⇒ 滚回时可以再次物化
          if (_lazyIO) { try { _lazyIO.observe(ph); } catch (_) {} }
          if (!evicted) evicted = new Set();
          evicted.add(real);
          _lazyEvictCount++;
          n++;
        } catch (e) {
          log("lazy", "evict block " + bi + " ERR " + ((e && e.message) || e));
        }
      }
      if (_pf) { _pf.applyMs += _evNow() - _pseg; _pseg = _evNow(); }

      // ⑥.0 2026-10-22 task-70（堆泄漏根治）：把已换出块里的 MathJax MathItem 从 `document.math`
      //   移除。`replaceWith` 只把 DOM 换出文档；MathJax 的 `MathList` 仍持有 MathItem →
      //   MathItem.typesetRoot 指向 detached 的 `mjx-container`，整棵 SVG 子树因此不可回收。
      //   本批只对**确实含公式产物**的块调用（`_mathEvicted`），无公式的块不付这笔扫描成本。
      if (_mathEvicted) {
        var _mc = _clearMathJaxWithin(_mathEvicted);
        if (_mc) log("lazy", "math clear on evict: " + _mc + " blocks / " + _mathEvicted.length);
      }
      if (_pf) { _pf.mathClearMs += _evNow() - _pseg; _pseg = _evNow(); }

      // ⑥ 清掉排版队列里对已换出元素的引用（否则队列长期持死 DOM ⇒ 淘汰白做）
      if (evicted && _lazyMathQueue && _lazyMathQueue.length) {
        try {
          _lazyMathQueue = _lazyMathQueue.filter(function (x) { return !evicted.has(x); });
          if (!_lazyMathQueue.length) {
            _lazyMathQueue = null;
            if (_lazyMathQueueTimer) { clearTimeout(_lazyMathQueueTimer); _lazyMathQueueTimer = null; }
          }
        } catch (_) {}
      }

      // ── ⑥.5【兜底 B】滚动锚定补偿：A 已让高度稳定，这里只吸收**残余**变化 ───────────────
      //   做法：同一锚点块（换出不会碰它，它在保留窗口内）在批次前后的 `rect.top` 之差 =
      //   视口上方内容高度变化 ⇒ 反向加回 `scrollTop`，用户的可见位置一像素不动。
      //   成本：1 次 rect 读 + 1 次 scrollHeight 读（同一布局），复用 `_lazyEvictKeepRange` 的二分锚点，
      //   **不遍历全篇 rect**；无补偿时不写 scrollTop、不打日志。
      if (n) {
        var _tailT0 = _pf ? _evNow() : 0;
        if (_tailLayoutMode === "legacy") {
          try {
            var _shAfter = pane.scrollHeight;
            if (_pf) { _pf.tailShMs += _evNow() - _tailT0; _tailT0 = _evNow(); }
            if (_shBefore > 0) _lazyHeightDriftPx += Math.abs(_shAfter - _shBefore);
            if (!isNaN(_anchorTop) && _anchorEl && _anchorEl.parentNode) {
              var _nowTop = _anchorEl.getBoundingClientRect().top;
              if (_pf) { _pf.tailAnchorReadMs += _evNow() - _tailT0; _tailT0 = _evNow(); }
              var _anchorDelta = _nowTop - _anchorTop;
              if (Math.abs(_anchorDelta) >= 0.5) {
                pane.scrollTop = pane.scrollTop + _anchorDelta;   // 越界由浏览器自行 clamp
                _lazyAnchorFixes++;
                log("lazy", "evict scroll-anchor: line=" + (keep.anchorLine == null ? "?" : keep.anchorLine) +
                  " Δ=" + Math.round(_anchorDelta) + "px");
              }
            }
            if (_pf) _pf.tailWriteMs += _evNow() - _tailT0;
          } catch (_) {}
        } else if (_tailLayoutMode === "noSh") {
          // 诊断模式：只去掉 scrollHeight 读，anchor rect 仍然强制布局。
          // 高度漂移无法实测 ⇒ 用预测绝对值诚实记账（核对项见 heightDriftErrPx）。
          try {
            _lazyHeightDriftPx += Math.abs(_predTotalPx);
            if (!isNaN(_anchorTop) && _anchorEl && _anchorEl.parentNode) {
              var _nowTop2 = _anchorEl.getBoundingClientRect().top;
              if (_pf) { _pf.tailAnchorReadMs += _evNow() - _tailT0; _tailT0 = _evNow(); }
              var _anchorDelta2 = _nowTop2 - _anchorTop;
              if (Math.abs(_anchorDelta2) >= 0.5) {
                pane.scrollTop = pane.scrollTop + _anchorDelta2;
                _lazyAnchorFixes++;
              }
            }
            if (_pf) _pf.tailWriteMs += _evNow() - _tailT0;
          } catch (_) {}
        } else {
          // pred：**批尾零强制布局**。高度预测见 ⑤.5；真实核对延后到渲染后的空帧。
          _tailPredDriftPx += _predAbove;
          _tailPredTotalPx += _predTotalPx;
          _tailPendingAbsDriftPx += Math.abs(_predTotalPx);
          if (Math.abs(_predAbove) >= 0.5) _tailWouldFix++;
          if (Math.abs(_predAbove) > _tailAnchorPredMax) _tailAnchorPredMax = Math.abs(_predAbove);
          _tailBatchCount++;
          _tailSkips++;
          if (_pf) _pf.tailSkips++;
          if (_predUnknown || Math.abs(_tailPredDriftPx) >= _TAIL_VERIFY_PX ||
              _tailBatchCount >= _TAIL_VERIFY_BATCHES) {
            _tailScheduleVerify();
          }
        }
      }

      if (n) {
        var kept = Math.max(0, materializedBefore - n);
        log("lazy", "evict: " + n + " blocks (kept=" + kept + ", viewport=" + keep.lo + ".." + keep.hi + ", reason=" + reason + ")");
        // 有余量 ⇒ 续排下一批（跨帧推进；单批仍受 LAZY_EVICT_BATCH_MAX 限制）
        if (cand.length > batch.length) _lazyScheduleEvict(_lazyEvictIsPressure(cc, pane));
      }
      if (_pf) {
        _pf.anchorMs += _evNow() - _pseg;
        var _lastSeg = _evNow() - _ptot0;
        _pf.totalMs += _lastSeg;                // 本批同步耗时（整批）
        var _bTotal = _pf.totalMs - _pb.total;  // 本批同步耗时合计（写 DOM + 强制布局 + 清理）
        var _bApply = _pf.applyMs - _pb.apply;
        var _bMath = _pf.mathClearMs - _pb.math;
        var _bBi = _pf.blockIndexMs - _pb.bi;
        _pf.batches++;
        _pf.blocks += n;
        _pf.blocksWithMath += (_mathEvicted ? _mathEvicted.length : 0);
        if (_bTotal > _pf.maxTotalMs) _pf.maxTotalMs = _bTotal;
        if (_bApply > _pf.maxApplyMs) _pf.maxApplyMs = _bApply;
        if (_mathEvicted && _bMath > _pf.maxMathClearMs) _pf.maxMathClearMs = _bMath;
        if (_bBi > _pf.maxBlockIndexMs) _pf.maxBlockIndexMs = _bBi;
        if (_pf.last.length < 600) {
          _pf.last.push({
            n: n, total: Math.round(_bTotal * 100) / 100,
            apply: Math.round(_bApply * 100) / 100,
            math: Math.round(_bMath * 100) / 100,
            bi: Math.round(_bBi * 100) / 100,
          });
        }
      }
      return n;
    } catch (e) {
      log("lazy", "evict ERR " + ((e && e.message) || e));
      return 0;
    }
  }

  /** 调度一次工作集淘汰 —— **MemoriaScheduler 作业**（同键合并 ⇒ 任意多次请求只留一个）。
   *  绝不在这里同步淘汰：滚动回调只 enqueue，重活留给调度器帧预算。
   *
   *  @param {boolean} [pressure] 工作集已超压力阈值 ⇒ 以 P1 排队（防 P2 typeset / P1 物化
   *    连续非空时 P3 被饿死）。压力解除后恢复 P3。
   *  task-78：同一 key 只留一个作业；**不降级**已排队的 P1 作业（P3 请求不得把它顶掉）。 */
  function _lazyScheduleEvict(pressure) {
    if (_lazyEvictSuspended) return;
    if (!_lazyMaterializeEnabled(_doc)) return;
    var S = _lazyJobScheduler();
    if (!S || typeof S.schedule !== "function") return;
    var prio = pressure ? 1 : 3;
    if (_lazyEvictQueuedPriority && prio >= _lazyEvictQueuedPriority) return;
    _lazyEvictQueuedPriority = prio;
    if (pressure) _lazyEvictPressureSchedules++;
    S.schedule({
      kind: "lazy_evict",
      key: "lazy-evict",
      priority: prio,          // P3 后台；压力时 P1（仍走调度器，不抢同步帧）
      replace: true,
      gen: (typeof S.epoch === "function") ? S.epoch() : 0,
      dropStale: true,
      run: function () {
        _lazyEvictQueuedPriority = 0;
        _lazyEvictNow("scheduler" + (pressure ? "-pressure" : ""));
      },
    });
  }

  /** 工作集统计（metrics / 门禁量化用）：当前实际物化块数 / 占位数 / 全文块数。 */
  window.__MEMORIA_WORKSET_STATS = function () {
    var out = {
      materialized: 0,
      placeholders: 0,
      totalBlocks: 0,
      evictTotal: _lazyEvictCount,
      keepScreens: LAZY_EVICT_KEEP_SCREENS,
      pressureScreens: LAZY_EVICT_PRESSURE_SCREENS,
      evictPressureSchedules: _lazyEvictPressureSchedules,
      evictPendingSkips: _lazyEvictPendingSkips,
      suspended: !!_lazyEvictSuspended,
      // 2026-10-22 1d：换出高度稳定性指标 —— 累计 |本批 scrollHeight 变化|（px，越小越好；修复后≈0）
      heightDriftPx: Math.round(_lazyHeightDriftPx * 10) / 10,
      anchorFixes: _lazyAnchorFixes,     // 发生过 scrollTop 补偿的批次数（B 兜底触发次数）
      // 2026-10-22：**实测排版度量**（验证 detached 度量 bug 用）。
      //   lhPx 应为 22.4（.-preview 14px × 1.6），旧 bug 为 24（detached ⇒ 16 × 1.5）。
      fsPx: Math.round(_pvM().fs * 100) / 100,
      lhPx: Math.round(_pvM().lhPx * 100) / 100,
      metricsSrc: _pvM().src || "default",
    };
    try {
      var preview = $("#preview");
      var cc = preview ? preview.querySelector(".-preview-content") : null;
      var total = (_doc && _doc.blocks) ? _doc.blocks.length : 0;
      out.totalBlocks = total;
      if (cc) {
        var ph = cc.querySelectorAll(".-pv-placeholder").length;
        out.placeholders = ph;
        out.materialized = Math.max(0, total - ph);
      }
    } catch (_) {}
    return out;
  };

  /** P6d：单块增量重渲的薄封装（render-core.renderRange；缺内核时返回 undefined，调用方已有兜底）。 */
  function _supplyRangeRender(blockIndex, container) {
    const rc = _rcRenderer();
    return rc ? rc.renderRange(_doc, blockIndex, blockIndex + 1, container) : undefined;
  }

  /**
   * F1: AST-based preview rendering.
   * Parses source body → AST → renders to DOM.
   * No contenteditable, no cursor, just display.
   */
  function renderPreviewAST(body) {
    if (!P || !M || !_rcRenderer()) { log("F1", "modules missing"); return null; }
    const t0 = performance.now();
    _doc = P.parse(body || "");
    M.setDoc(_doc);
    const preview = $("#preview");
    if (!preview) return null;
    // P6a：整篇渲染切 render-core（不再调用 legacy `R.render`）
    const content = _rcRenderer().renderDocument(_doc).container;
    preview.innerHTML = "";
    preview.appendChild(content);
    _applyCodeHighlightToPreview(preview);   // 与 renderPreview 同口径
    log("F1", "rendered " + _doc.blocks.length + " blocks in " + (performance.now() - t0).toFixed(1) + "ms");
    return _doc;
  }

  // ════════════════════════════════════════════════════════════════
  //  预览 → 源码 编辑同步（AST 锚点编辑管线）
  //  beforeinput 拦截 → 修改 AST → 反向生成源码 → 增量渲染 → 恢复光标
  // ════════════════════════════════════════════════════════════════
  window.MemoriaEditSync = (function () {
    "use strict";

    // ── 独立撤销/重做日志：单独写一份，避免与 mapping 日志混杂 ──
    // 落点同 `LOG_FILE`（`.memoria/cache/**`，可再生缓存）—— 不写知识库根目录（2026-09-22 修）
    var UNDO_LOG_FILE = ".memoria/cache/undo-debug.log";
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
      call("write_map_log", UNDO_LOG_FILE, c).catch(function () { });
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
      var endExcl = end + 1;
      var oldCount = endExcl - start;
      var merged = rawLines.slice(0, start).concat(newLines, rawLines.slice(endExcl));
      state.doc.body = merged.join("\n");
      state.doc.lines = merged;
      // M6b：块替换后按行数差平移 KP 范围并同步列表/hover（预览区编辑实时同步）
      if (typeof window.__adjustKpRangesAfterSpanReplace === "function") {
        window.__adjustKpRangesAfterSpanReplace(start, endExcl, oldCount, newLines.length);
      }
      return { start: start, oldCount: oldCount, newCount: newLines.length };   // 2026-09-25 AG101：把"改了哪几行"交给调用方 ⇒ 源码面板可**只更新这几行**（原来每次按键整篇重建）
    }

    /** 增量重渲染预览中的单个 block。
     *  `keepLineMap`（2026-09-25 AG102）：**行数没变时不要重算 `stampBlockLines()`** —— 那一趟是 **O(文档)** 的
     *  （逐行走正则、逐块写 `data--src-line`），而打字/行内格式化根本不改"块→行"映射（行数没变 ⇒ 映射逐字不动）。
     *  真机：5888 行文档里每次按键都白付这一笔，是人说的「输入进去要等好一会才显示」里最大的一项固定开销。 */
    function reRenderBlock(blockIndex, keepLineMap) {
      var preview = $("#preview");
      if (!preview) return;
      var container = preview.querySelector(".-preview-content") || preview;
      // 2026-10-20 P2：**局部路径（G1）** —— 不再"整趟跳过"（那会造成 X2：新块节点不带 data--src-line），
      // 而是 beginStamp()（**不 reset**）+ 用**显式 id** 就地 upsert 这一块 ⇒ O(1)。
      // id 来源：**渲染前**从旧节点读 data-block-id（renderRange 会换掉节点，之后就读不到了）。
      var _oldEl = container.querySelector('.-src-block[data--block-index="' + blockIndex + '"]');
      var _keepId = _oldEl ? _oldEl.getAttribute("data-block-id") : null;
      var _made = _supplyRangeRender(blockIndex, container);   // P2：现返回新建顶层节点数组
      var _blk = _doc && _doc.blocks ? _doc.blocks[blockIndex] : null;
      if (_blk && _blk.srcLine > 0 && _blk.srcLineEnd >= _blk.srcLine) {
        // ★ 性能：兼容投影 `_blockLineMap` 只在**这一块的行区间真变了**时才重建（O(块数)）。
        //   打字/行内格式化不改行区间 ⇒ 跳过重建（这正是旧 `keepLineMap` 想省的那笔，但现在
        //   不再以"整趟跳过 upsert"为代价 —— upsert 仍做，X2 因此被消灭）。
        var _prevRange = (_blockLineMap && _blockLineMap[blockIndex]) || null;
        var _rangeChanged = !_prevRange || _prevRange.startLine !== (_blk.srcLine - 1) || _prevRange.endLine !== (_blk.srcLineEnd - 1);
        BI.beginStamp();
        BI.upsert({
          id: _keepId || undefined,          // 有旧 id ⇒ 就地更新（不产生孤儿）；无（首次）⇒ upsert 自动生成
          kind: _blk.type,
          srcLineStart: _blk.srcLine,
          srcLineEnd: _blk.srcLineEnd,
          blockSrcText: _blockSrcTextOf(_blk),
          domEl: (Array.isArray(_made) && _made[0]) ? _made[0] : null,
        });
        BI.commit();
        if (_rangeChanged) {
          _blockLineMap = BI.blocks().map(function (h) { return { startLine: h.srcLineStart - 1, endLine: h.srcLineEnd - 1 }; });
        }
      } else if (!keepLineMap) {
        stampBlockLines(preview, _doc);      // 兜底：AST 缺行区间（理论上不该发生）⇒ 退回整篇投影
      }
      if (_domBlockSig && _doc && _doc.blocks && _domBlockSig.length === _doc.blocks.length) _domBlockSig[blockIndex] = _previewBlockSig(_doc.blocks[blockIndex]);   // 单块重渲 ⇒ 差分基准只跟着这一块走（不更新的话，块级提交会把这块误判成"没变"）
      // 增量渲染替换了 block DOM：.-math span 是新节点，需重新触发 MathJax 排版，
      // 否则行内公式会以裸文本显示（样式应用/笔刷后“公式预览失败”，全量刷新才恢复）
      // 2026-09-25 AG101：**只对"这一块"做后处理** —— 原来 `typesetPromise([container])` 把**整篇预览**重排一遍、
      // `postProcessWikilinks()` 扫全部 `.-wikilink`、`bindPreviewLinks()` 扫全部 `.memoria-link`，
      // 每次按键都付整篇的钱 ⇒ 真机「输入进去没有反应，要等渲染之后才显示编辑内容」（人 2026-09-25）。
      var _madeBlock = (Array.isArray(_made) && _made[0]) ? _made[0] : container.querySelector('.-src-block[data--block-index="' + blockIndex + '"]');
      if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
        try { window.MathJax.typesetPromise(_madeBlock ? [_madeBlock] : [container]); } catch (e) { }
      }
      // 增量渲染出的新 block 里可能有 wikilink，需重新做后处理并绑定跳转事件
      postProcessWikilinks(_madeBlock || undefined);
      bindPreviewLinks(_madeBlock || undefined);
    }

    /** 恢复预览区光标到 AST 坐标 */
    function restoreCursor(blockIndex, nodePath, offset) {
      hlog("restoreCursor bi=" + blockIndex + " path=[" + (nodePath || []).join(",") + "] off=" + offset);
      var range = M.astToDom(blockIndex, nodePath, offset);
      if (!range) { hlog("restoreCursor -> FAIL (no range)"); return; }
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      // ── E26：预览区输入/回车/IME 提交后保持光标可见 ──
      // 仅当预览区真正持有焦点、且不处于 IME 组合中时才滚；`_keepCaretVisible`
      // 只在光标越出 pane 视口（含 8px 余量）时补差值 ⇒ 正常打字不会每键跳动。
      // 用户主动滚动后没有新的编辑提交 ⇒ 不会被这里拽回。
      var _pv = document.getElementById("preview");
      var _pp = document.getElementById("preview-pane");
      var _eh = window.MemoriaEditHandler;
      if (_pv && _pp && !(_eh && _eh._composing) &&
          (document.activeElement === _pv ||
           (document.activeElement && _pv.contains(document.activeElement)))) {
        var _fallback = range.startContainer;
        if (_fallback && _fallback.nodeType === 3) _fallback = _fallback.parentElement;
        _keepCaretVisible(_pp, range, _fallback);
      }
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

    /**
     * 端点切分（容忍"块边界"端点）：nodePath 为空表示端点落在块边界——
     * 空行块、图片块等**无 inline 文本**的块，或元素级位置。
     * splitInlineAt 对空路径一律返回 null，会让整次跨块删除静默失败
     * （表现为"选中了却删不掉"）；此处按"块开头"处理：左侧为空、右侧为整块内容。
     */
    function splitInlineAtEdge(children, nodePath, offset) {
      if (!nodePath || !nodePath.length) {
        return { left: [], right: (children || []).slice() };
      }
      return splitInlineAt(children, nodePath, offset);
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
      if (block.type === "blockquote") {
        // task-156 Step2：引用块的"块首"取决于**child/item 的 inline 根**（一期新形状）：
        //   段落 child → path=[childIdx,…inline]；list child → path=[childIdx,itemIdx,…inline]。
        var qp = _parseEditPath(block, cursor.nodePath || []);
        if (!qp) return false;
        children = qp.inlineRoot || [];
        path = qp.inlinePath || [];
        var qfp = firstTextPath(children);
        if (!qfp) return path.length === 0;
        if (path.length !== qfp.path.length) return false;
        for (var qi2 = 0; qi2 < path.length; qi2++) {
          if (path[qi2] !== qfp.path[qi2]) return false;
        }
        return true;
      }
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

    /** **原生优先：预览区打字不再"每键重渲那一块"**（2026-09-25 AG103）。
     *  人：「**看到预览区域输入的时候，是先在源码区域输入的，这个是不对的，因为我们基础设施是双向映射，可以双向同步，
     *  你这个南辕北辙会导致输入卡顿，而且现在仍然是输入等一会才有反应**」。
     *  事实：在预览里敲字，**DOM 里的字是浏览器原生敲进去的**（那一刻就已经对了）—— 旧写法每按一键就把这个块
     *  重渲一遍（解析 → 建 DOM → 替换节点 → MathJax → 补链接），既把这一帧占满，又会打断 IME 组合/光标。
     *  ⇒ 改成**双向映射的正确姿势**：预览侧保持原生结果，只把**另一侧（AST + 源码面板）**同步过去；
     *  预览那一块的"渲染态归一"（把 `**粗**`、`# ` 自动转换等记号洗成渲染态）**推迟到停手 ~180 ms 后做一次**。
     *  三条护栏：① IME 组合中不重渲（等 `compositionend` 之后那次停手）；② 停手期间又敲了 ⇒ 计时重来；
     *  ③ 重渲时若光标仍在那一块 ⇒ 按 `EH.cursorAST` 把光标放回去（否则只重渲、不动选区）。
     *  另：**结构性提交（回车/合并/跨块删除）会先把挂起的重渲冲掉**（见 `_flushBlockRepaint`），
     *  免得块级提交的差分基准里混着"还没归一"的块。 */
    var _repaintTimer = null, _repaintBlock = -1;
    function _flushBlockRepaint() {
      if (_repaintTimer) { clearTimeout(_repaintTimer); _repaintTimer = null; }
      var bi = _repaintBlock; _repaintBlock = -1;
      if (bi < 0 || !_doc || !_doc.blocks || bi >= _doc.blocks.length) return;
      var EH = window.MemoriaEditHandler; if (EH && EH._composing) { _repaintBlock = bi; _repaintTimer = setTimeout(function () { _repaintTimer = null; _flushBlockRepaint(); }, 180); return; }   // AG105：定时器到点时可能又开始了新一次 IME 组合 ⇒ 此刻重渲会把用户正在组合的那个 DOM 节点换掉（浏览器会中断组合）⇒ 再往后推
      var cur = EH && EH.cursorAST;
      var keepCaret = !!(cur && cur.blockIndex === bi);
      reRenderBlock(bi, true);   // 行数没变（打字不改行数）⇒ 不重算块→行映射
      if (keepCaret) restoreCursor(cur.blockIndex, cur.nodePath, cur.offset);
    }
    function _scheduleBlockRepaint(blockIndex) {
      var EH = window.MemoriaEditHandler;
      if (EH && EH._composing) return;   // ① 组合中 ⇒ 交给 compositionend 之后那次停手
      _repaintBlock = blockIndex;
      if (_repaintTimer) clearTimeout(_repaintTimer);
      _repaintTimer = setTimeout(function () { _repaintTimer = null; _flushBlockRepaint(); }, 180);   // ② 停手才渲
    }

    function _cancelBlockRepaint() {   // 结构性提交前用：那一块**马上会被块级提交重渲**，挂起的定时器只会重复劳动
      if (_repaintTimer) { clearTimeout(_repaintTimer); _repaintTimer = null; }
      _repaintBlock = -1;
    }

    /** AST 已修改后的统一提交：生成源码 → 更新源码编辑器 → 增量重渲染 → 恢复光标 → 标记脏。 `nativeDone`（2026-09-25 AG105）：**浏览器已把字原生插进 DOM**（IME 的 `compositionend` 那条路）⇒ 预览那一格不用我们画，只把"渲染态归一"推迟（别在 IME 组合里动 DOM）；其余入口（`beforeinput` 里我们 `preventDefault()` 了）**必须当刻把预览画出来** —— 否则那 180 ms 里用户看到的是"源码面板先变、预览不动"（人：「是先在源码区域输入的」）。 */
    function commit(block, cursor, nativeDone) {
      hlog("commit cursor=" + _fmtCursor(cursor));
      var _t0 = (window.performance && performance.now) ? performance.now() : 0;   // AG102：给"按键 → 预览更新"整条链计时（> 20 ms 才打一行，见函数尾）
      var _sp = spliceBlockSource(cursor.blockIndex, G.generateBlock(block));
      if (nativeDone) _scheduleBlockRepaint(cursor.blockIndex);   // 原生路：DOM 已是原生结果 ⇒ 只有"归一"推迟
      else reRenderBlock(cursor.blockIndex, !!_sp && _sp.oldCount === _sp.newCount);   // AG105：非原生路 ⇒ **先画预览**（预览在前、源码面板在后）
      if (!_sp || !patchEditorLines(_sp.start, _sp.oldCount, _sp.newCount)) renderEditor(state.doc);   // 2026-09-25 AG101：源码面板只更新改动那几行（整篇重建是"输入没反应"的主因）
      restoreCursor(cursor.blockIndex, cursor.nodePath, cursor.offset); markDirty();
      if (_t0) { var _ms = performance.now() - _t0; if (_ms > 20) log("EDIT", "按键提交 " + Math.round(_ms) + "ms · 行 " + (_sp ? _sp.oldCount + "→" + _sp.newCount : "?") + " · 块 " + cursor.blockIndex + (state.doc && state.doc.lines ? "（全篇 " + state.doc.lines.length + " 行）" : "")); }
      return true;
    }

    /** 同 commit，但提交后恢复为非折叠选区（selStart/selEnd 为 AST 坐标） */
    function commitSelection(block, blockIndex, selStart, selEnd) {
      hlog("commitSelection bi=" + blockIndex + " start=" + _fmtCursor({ blockIndex: blockIndex, nodePath: selStart.nodePath, offset: selStart.offset }) +
        " end=" + _fmtCursor({ blockIndex: blockIndex, nodePath: selEnd.nodePath, offset: selEnd.offset }));
      var _sp2 = spliceBlockSource(blockIndex, G.generateBlock(block));
      if (!_sp2 || !patchEditorLines(_sp2.start, _sp2.oldCount, _sp2.newCount)) renderEditor(state.doc);   // 同上：只更新改动那几行
      reRenderBlock(blockIndex, !!_sp2 && _sp2.oldCount === _sp2.newCount);   // AG102：行数没变 ⇒ 不重算块→行映射
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
    // task-138：结构编辑（拆段/块级重渲）的"完成"信号。拆段后的 restoreCursor 在
    // repaintPreview().then(...) 里异步执行；多行粘贴必须在插下一行前等它，否则 cursorAST
    // 还指向拆段前的旧位置 ⇒ 后续行插入失败且静默丢失（真机 10/10 复现）。
    var _pendingStructural = null;

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
      var _snapBody = _restoreDocTailNL(snap.body);
      state.doc.body = _snapBody;
      state.doc.lines = _linesFromBody(_snapBody);
      state.doc.preview_body = null;  // 撤销/重做后 preview_body 缓存过期，必须清空否则渲染旧内容
      renderEditor(state.doc);
      repaintPreview().then(function () {   // 2026-09-25：撤销/重做也走**块级提交**（原来整篇重渲 ⇒ 每步 undo 都闪一次）
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

    // ── task-156 二期 Step0：编辑路径 / 行区间 helper（所有改动的单一口径）──
    // 一期新形状：blockquote.children 可以是**跨多行**的 list；nodePath 有两种语义
    //   paragraph child → [childIdx, …inline]
    //   list child      → [childIdx, itemIdx, …inline]
    // 每个 child 落 srcLine/srcLineEnd（绝对 1-based）⇒ 行区间换算只允许走这里。

    /** _segPos：块内"段/项"序位（用于判断选区是否跨段/跨项）。
     *  引用块段落 → childIdx 序位；引用内 list → childIdx+itemIdx 序位（列表项更细）；其它块 → nodePath[0]。 */
    function _segPos(block, cursor) {
      var p = (cursor && cursor.nodePath) || [];
      if (block && block.type === "blockquote") {
        var qi = p.length ? p[0] : -1;
        if (qi < 0) return -1;
        var child = block.children && block.children[qi];
        if (child && child.type === "list") {
          var ii = p.length > 1 ? p[1] : 0;
          return qi * 100000 + ii + 1;
        }
        return qi * 100000;
      }
      return p.length ? p[0] : -1;
    }

    /**
     * block 内第 childIdx 个 child 的源码行区间（0-based 闭区间，供 commitRange 用）。
     * 依据一期 child.srcLine/srcLineEnd；旧 AST（外部构造、无跨度）退回"1 child = 1 行"。
     * @returns {{startLine:number,endLine:number}|null}
     */
    function _childLineRange(blockIndex, childIdx) {
      var rng = _blockLineMap && _blockLineMap[blockIndex];
      var block = _doc && _doc.blocks && _doc.blocks[blockIndex];
      if (!rng || !block) return null;
      var kids = block.children || [];
      var child = (childIdx >= 0 && childIdx < kids.length) ? kids[childIdx] : null;
      if (!child) return null;   // 越界 ⇒ 不猜（旧 AST 兜底只对**存在**的 child 生效）
      var base = rng.startLine;
      var off = childIdx >= 0 ? childIdx : 0;
      var blockStart = block.srcLine > 0 ? block.srcLine : 1;
      if (child && child.srcLine > 0) {
        var s = base + (child.srcLine - blockStart);
        var e = (child.srcLineEnd >= child.srcLine) ? base + (child.srcLineEnd - blockStart) : s;
        return { startLine: s, endLine: e >= s ? e : s };
      }
      return { startLine: base + off, endLine: base + off };
    }

    /** 引用块内 list child 的第 itemIdx 项的源码行（0-based）。
     *  一期 parser 里 item.srcLine 是"引用切片内相对 1-based"，而 child 首行 = _childLineRange.startLine。 */
    function _quoteItemLineRange(blockIndex, childIdx, itemIdx) {
      var rng = _blockLineMap && _blockLineMap[blockIndex];
      var block = _doc && _doc.blocks && _doc.blocks[blockIndex];
      var child = block && block.children && block.children[childIdx];
      var item = child && child.items && child.items[itemIdx];
      if (!rng || !block || !item) return null;
      // ★ 一期 parser 里 item.srcLine 是「引用切片内相对 1-based」（切片起点 = 引用块首行），
      //   不是相对 list child 起点 ⇒ 正确公式 = 块首行(0-based) + (item.srcLine - 1)。
      //   （写成 child 首行 + item.srcLine - 1 会整体偏 1 行 ⇒ Enter/Backspace 改错行，已真机抓过）
      if (item.srcLine > 0) {
        var ln = rng.startLine + (item.srcLine - 1);
        return { startLine: ln, endLine: ln };
      }
      var cr = _childLineRange(blockIndex, childIdx);   // 旧 AST 兜底：child 内第 itemIdx 行
      var first = cr ? cr.startLine : rng.startLine;
      return { startLine: first + itemIdx, endLine: first + itemIdx };
    }

    /**
     * 统一解析编辑光标 nodePath → 容器/子块/列表项/行内根。
     * @returns {{kind:"quote"|"list"|"block", childIdx:number|null, child:object|null,
     *            itemIdx:number|null, item:object|null,
     *            inlineRoot:Array, inlinePath:number[]}|null}
     */
    function _parseEditPath(block, nodePath) {
      var path = nodePath || [];
      if (!block) return null;
      if (block.type === "blockquote") {
        if (!path.length) return null;
        var qi = path[0];
        var child = block.children && block.children[qi];
        if (!child) return null;
        if (child.type === "list") {
          if (path.length < 2) {
            return { kind: "quote", childIdx: qi, child: child, itemIdx: null, item: null,
                     inlineRoot: [], inlinePath: [] };
          }
          var ii = path[1];
          var item = child.items && child.items[ii];
          if (!item) return null;
          return { kind: "quote", childIdx: qi, child: child, itemIdx: ii, item: item,
                   inlineRoot: item.children || [], inlinePath: path.slice(2) };
        }
        return { kind: "quote", childIdx: qi, child: child, itemIdx: null, item: null,
                 inlineRoot: child.children || [], inlinePath: path.slice(1) };
      }
      if (block.type === "list") {
        if (!path.length) return null;
        var li = path[0];
        var lit = block.items && block.items[li];
        if (!lit) return null;
        return { kind: "list", childIdx: null, child: null, itemIdx: li, item: lit,
                 inlineRoot: lit.children || [], inlinePath: path.slice(1) };
      }
      return { kind: "block", childIdx: null, child: null, itemIdx: null, item: null,
               inlineRoot: block.children || [], inlinePath: path };
    }
    // ── end: edit path helpers ──

    // ── 结构标记自动转换（# / ## / - / * / + / 1. 等）──

    /** 检测段落源码行是否构成块级标记，返回 {type, level?, ordered?} 或 null */
    function detectStructuralMarker(line) {
      if (!line) return null;
      var hm = line.match(/^(#{1,6})\s/);
      if (hm) return { type: "heading", level: hm[1].length };
      // E28（2026-10-22）：`>` + 一个空格/制表符 ⇒ 引用块。
      // 语义与 lexer 的 `^(\s*)((?:>[ \t]?)+)` 对齐：`>` 后的**第一个**空白属于标记，
      // 再往后的空白才是正文内容。
      // ★ 只在**空白已落下**时才转换（不匹配裸 `>`）：若敲 `>` 就转成引用块，紧随的
      //   空格会被当成"正文空格"写进空段落 ⇒ 源码多一个空格（`>  `），与用户输入不符。
      if (/^>[ \t]/.test(line)) return { type: "blockquote" };
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
      // E28：引用块的 children 是**块级段落**（每行一个，与 parser 一致），
      // 光标必须落到第一段内部（nodePath[0] = 段落索引），否则会指向 blockquote
      // 本身 ⇒ 后续 insertText 会把 text 直接挂到 blockquote.children 上（坏 AST）。
      // ★ task-156：一期后 children 也可能是**跨多行 list** ⇒ 光标必须再下钻到
      //   item（nodePath=[childIdx, itemIdx, …]），绝不能指向 list 块本身。
      if (block.type === "blockquote") {
        var qKids0 = block.children || [];
        if (!qKids0.length) return { nodePath: [0], offset: 0 };
        var qChild0 = qKids0[0];
        if (qChild0 && qChild0.type === "list") {
          var qItem0 = qChild0.items && qChild0.items[0];
          var qip0 = qItem0 ? firstTextPath(qItem0.children || []) : null;
          return { nodePath: qip0 ? [0, 0].concat(qip0.path) : [0, 0], offset: 0 };
        }
        var qPara = qChild0;
        var qfp = qPara ? firstTextPath(qPara.children || []) : null;
        return { nodePath: qfp ? [0].concat(qfp.path) : [0], offset: 0 };
      }
      var pfp = firstTextPath(block.children || []);
      return { nodePath: pfp ? pfp.path : [], offset: 0 };
    }

    /**
     * 若段落已构成块级标记（标题/列表），则原地转换为对应 block 并修正光标。
     * @returns {boolean} 是否发生了转换
     */
    function convertStructuralBlock(block, cursor) {
      // task-156 Step2：引用块内的段落转换（只支持列表标记；受 parser 限制）
      if (block.type === "blockquote") return _convertStructuralBlockInQuote(block, cursor);
      if (block.type !== "paragraph") return false;
      var line = G.generateBlock(block);
      var marker = detectStructuralMarker(line);
      if (!marker) return false;

      var newBlock = P.parseBlocks([line])[0];
      if (!newBlock || newBlock.type === "paragraph") return false;

      // ★ E28（2026-10-22）：**保留原块的源码行号**。
      // `P.parseBlocks([line])` 拿到的是一段"单行切片"，它给 newBlock 的 srcLine 恒为 1。
      // 若把这个 1 抄进真实块（第 5 块就会变成 srcLine=1），随后：
      //   ① reRenderBlock 判定"行区间变了" ⇒ 重建 `_blockLineMap`；
      //   ② 下一次按键的 spliceBlockSource 用错的行区间 ⇒ **改到文档开头**（真机实测：
      //      `# E28 probe\n\n> \n\n正文行\n> ` 敲一个 x 后变成 `> x\n\n> \n\n正文行\n> `，
      //      heading 被覆盖、正文尾部多出一截）。
      // 转换是"一行换一行"，行号本就不该变 ⇒ 显式保住。
      var keepSrcLine = block.srcLine;
      var keepSrcLineEnd = block.srcLineEnd;

      // 原地替换 block 属性（block 即 _doc.blocks[cursor.blockIndex]）
      var k;
      for (k in block) { if (Object.prototype.hasOwnProperty.call(block, k)) delete block[k]; }
      for (k in newBlock) { if (Object.prototype.hasOwnProperty.call(newBlock, k)) block[k] = newBlock[k]; }
      if (keepSrcLine > 0) block.srcLine = keepSrcLine;
      if (keepSrcLineEnd > 0) block.srcLineEnd = keepSrcLineEnd;

      var nc = blockContentStart(block);
      cursor.nodePath = nc.nodePath;
      cursor.offset = nc.offset;
      return true;
    }

    /**
     * 在预览区插入文本（insertText）
     * @param {string} text — 插入的字符。 `nativeDone`（2026-09-25 AG105）：**浏览器已把字原生插进 DOM**（IME 的 `compositionend` 那条路）⇒ 预览那一格不重渲，只推迟"归一"
     * @returns {boolean} 是否成功
     */
    // ── task-156 Step2：引用块内列表交互（单一口径：行区间/前缀都走一期 + Step0 helper）──

    /** 引用块某源码行（0-based）的**原始前缀**（`>` / `> ` / `>> `…），用于重建该行时保真。 */
    function _quotePrefixAt(block, blockIndex, lineIdx0) {
      var rng = _blockLineMap && _blockLineMap[blockIndex];
      var idx = rng ? (lineIdx0 - rng.startLine) : -1;
      if (block && block.prefixes && idx >= 0 && idx < block.prefixes.length && block.prefixes[idx]) {
        return block.prefixes[idx];
      }
      var rawLine = (state.doc && state.doc.lines && state.doc.lines[lineIdx0]) || "";
      var m = rawLine.match(/^(\s*(?:>[ \t]?)+)/);
      return m ? m[1] : "> ";
    }

    /** 该源码行去掉引用前缀后的内层文本 */
    function _quoteInnerOfLine(block, blockIndex, lineIdx0) {
      var pfx = _quotePrefixAt(block, blockIndex, lineIdx0);
      var rawLine = (state.doc && state.doc.lines && state.doc.lines[lineIdx0]) || "";
      if (rawLine.indexOf(pfx) === 0) return rawLine.slice(pfx.length);
      var alt = rawLine.match(/^(\s*(?:>[ \t]?)+)/);
      return alt ? rawLine.slice(alt[1].length) : rawLine;
    }

    /** ① 引用段落内敲 `- ` / `1. ` ⇒ 该 child 原地换成 list child（与顶层段落转换同语义）。
     *  引用内**只支持列表**：标题/嵌套引用受 parser 限制，不转换（保持文本）。 */
    function _convertStructuralBlockInQuote(block, cursor) {
      var path = cursor.nodePath || [];
      var qi = path.length ? path[0] : -1;
      var child = qi >= 0 ? (block.children || [])[qi] : null;
      if (!child || child.type !== "paragraph") return false;
      var line = G.generateBlock(child);
      var marker = detectStructuralMarker(line);
      if (!marker || marker.type !== "list") return false;
      var newChild = P.parseBlocks([line])[0];
      if (!newChild || newChild.type !== "list" || !(newChild.items && newChild.items.length)) return false;
      var keepS = child.srcLine > 0 ? child.srcLine : 0;
      var keepE = child.srcLineEnd > 0 ? child.srcLineEnd : keepS;
      block.children[qi] = newChild;
      if (keepS > 0) { newChild.srcLine = keepS; newChild.srcLineEnd = keepE; }
      var item0 = newChild.items[0];
      var fp0 = item0 ? firstTextPath(item0.children || []) : null;
      cursor.nodePath = fp0 ? [qi, 0].concat(fp0.path) : [qi, 0];
      cursor.offset = 0;
      return true;
    }

    /** ② 引用内 Enter：段落拆两段 / 列表项续列（空项 ⇒ 退出列表为该行空引用段落）。
     *  统一走 commitRange（单个撤销单元 + 只改目标行），未涉及行逐字节不变。 */
    function _splitParagraphInQuote(block, cursor, preCursor, blockIndex) {
      var path = cursor.nodePath || [];
      var qi = path.length ? path[0] : -1;
      var child = qi >= 0 ? (block.children || [])[qi] : null;
      if (!child) return false;

      if (child.type === "paragraph") {
        var sp = splitInlineAt(child.children || [], path.slice(1), cursor.offset);
        if (!sp) return false;
        var range = _childLineRange(blockIndex, qi);
        if (!range) return false;
        var pfx = _quotePrefixAt(block, blockIndex, range.startLine);
        var left = G.generateBlock(A.paragraph(sp.left));
        var right = G.generateBlock(A.paragraph(sp.right));
        var newLines, nc;
        if (!sp.left.length && sp.right.length) {
          // 段首：上方插入空引用行
          newLines = [pfx, pfx + right];
          nc = { blockIndex: blockIndex, nodePath: [qi], offset: 0 };
        } else if (!sp.right.length) {
          // 段末：下方插入空引用行
          newLines = [pfx + left, pfx];
          nc = { blockIndex: blockIndex, nodePath: [qi + 1], offset: 0 };
        } else {
          newLines = [pfx + left, pfx + right];
          var fp = firstTextPath(sp.right);
          nc = { blockIndex: blockIndex, nodePath: fp ? [qi + 1].concat(fp.path) : [qi + 1], offset: 0 };
        }
        return commitRange(range.startLine, range.startLine, newLines, nc, preCursor, "enter");
      }

      if (child.type !== "list") return false;
      var itemIdx = path.length > 1 ? path[1] : 0;
      var item = child.items && child.items[itemIdx];
      var itemRange = _quoteItemLineRange(blockIndex, qi, itemIdx);
      if (!item || !itemRange) return false;
      var pfx2 = _quotePrefixAt(block, blockIndex, itemRange.startLine);
      var inner = _quoteInnerOfLine(block, blockIndex, itemRange.startLine);
      var mLead = inner.match(/^([ \t]*)([-*+]|\d+\.)[ \t]/);
      var lead = mLead ? mLead[0] : (child.ordered ? "1. " : "- ");   // mLead[0] 含 marker + 分隔空格
      var sp2 = splitInlineAt(item.children || [], path.slice(2), cursor.offset);
      if (!sp2) {
        if ((item.children || []).length === 0) sp2 = { left: [], right: [] };
        else return false;
      }
      if (!sp2.left.length && !sp2.right.length) {
        // 空项 + Enter ⇒ 退出列表：该行变空引用段落
        return commitRange(itemRange.startLine, itemRange.startLine, [pfx2],
          { blockIndex: blockIndex, nodePath: [qi], offset: 0 }, preCursor, "enter");
      }
      var left2 = G.generateBlock(A.paragraph(sp2.left));
      var right2 = G.generateBlock(A.paragraph(sp2.right));
      var rightLead = lead;
      if (child.ordered && mLead) {
        var n = parseInt(mLead[2], 10);
        if (isFinite(n)) rightLead = mLead[1] + (n + 1) + ". ";
      }
      return commitRange(itemRange.startLine, itemRange.startLine,
        [pfx2 + lead + left2, pfx2 + rightLead + right2],
        { blockIndex: blockIndex, nodePath: [qi, itemIdx + 1, 0], offset: 0 }, preCursor, "enter");
    }

    /** ③ 引用内行首 Backspace：合并到上一 child / 列表项合并上一项 / 首项退列表。
     *  只替换目标行区间（不碰未涉及行）；跨嵌套列表等复杂情况保守返回 false。 */
    function _backspaceAtBlockStartInQuote(block, cursor, preCursor) {
      var blockIndex = cursor.blockIndex;
      var path = cursor.nodePath || [];
      var qi = path.length ? path[0] : -1;
      var child = qi >= 0 ? (block.children || [])[qi] : null;
      if (!child) return false;

      if (child.type === "list") {
        var itemIdx = path.length > 1 ? path[1] : 0;
        var item = child.items && child.items[itemIdx];
        var itemRange = _quoteItemLineRange(blockIndex, qi, itemIdx);
        if (!item || !itemRange) return false;
        var pfx = _quotePrefixAt(block, blockIndex, itemRange.startLine);
        var inner = _quoteInnerOfLine(block, blockIndex, itemRange.startLine);
        var itemEmpty = !(item.children && item.children.length);

        if (itemIdx === 0) {
          // 首项：退列表（去掉 marker；空项 ⇒ 空引用段落）
          var lead0 = inner.match(/^([ \t]*)([-*+]|\d+\.)[ \t]/);
          var rest0 = lead0 ? inner.slice(lead0[0].length) : inner;
          return commitRange(itemRange.startLine, itemRange.startLine, [pfx + rest0],
            { blockIndex: blockIndex, nodePath: itemEmpty ? [qi] : [qi, 0], offset: 0 }, preCursor, "backspace");
        }
        // 非首项：合并到上一项（上一项行 + 当前项内容）；只允许相邻行（防误删松散空行）
        var prevRange = _quoteItemLineRange(blockIndex, qi, itemIdx - 1);
        if (!prevRange || itemRange.startLine - prevRange.startLine !== 1) return false;
        var prevInner = _quoteInnerOfLine(block, blockIndex, prevRange.startLine);
        var curLead = inner.match(/^([ \t]*)([-*+]|\d+\.)[ \t]/);
        var curBody = curLead ? inner.slice(curLead[0].length) : inner;
        var prevPfx = _quotePrefixAt(block, blockIndex, prevRange.startLine);
        var prevItem = child.items[itemIdx - 1];
        var mergedKids = mergeAdjacentInline((prevItem.children || []).concat(item.children || []));
        var lp = lastTextPath(mergedKids);
        return commitRange(prevRange.startLine, itemRange.startLine,
          [prevPfx + prevInner + curBody],
          { blockIndex: blockIndex, nodePath: lp ? [qi, itemIdx - 1].concat(lp.path) : [qi, itemIdx - 1],
            offset: lp ? lp.offset : 0 }, preCursor, "backspace");
      }

      if (child.type !== "paragraph") return false;
      if (qi === 0) return false;   // 引用块首 child：暂不跨出引用块合并
      var curRange = _childLineRange(blockIndex, qi);
      var prevChild = (block.children || [])[qi - 1];
      if (!curRange || !prevChild) return false;
      var curBody2 = _quoteInnerOfLine(block, blockIndex, curRange.startLine);

      if (prevChild.type === "list") {
        var lastIdx = (prevChild.items || []).length - 1;
        var lastRange = _quoteItemLineRange(blockIndex, qi - 1, lastIdx);
        var prevSpan = _childLineRange(blockIndex, qi - 1);
        // 保守：上一 child 最后一项必须就是它的最后一行（有嵌套/松散尾行时不合并，防误删）
        if (lastIdx < 0 || !lastRange || !prevSpan || lastRange.startLine !== prevSpan.endLine) return false;
        if (curRange.startLine - lastRange.startLine !== 1) return false;
        var lastItem = prevChild.items[lastIdx];
        var prevPfx = _quotePrefixAt(block, blockIndex, lastRange.startLine);
        var prevInner = _quoteInnerOfLine(block, blockIndex, lastRange.startLine);
        var mergedKids2 = mergeAdjacentInline((lastItem.children || []).concat(child.children || []));
        var lp2 = lastTextPath(mergedKids2);
        return commitRange(lastRange.startLine, curRange.startLine,
          [prevPfx + prevInner + curBody2],
          { blockIndex: blockIndex, nodePath: lp2 ? [qi - 1, lastIdx].concat(lp2.path) : [qi - 1, lastIdx],
            offset: lp2 ? lp2.offset : 0 }, preCursor, "backspace");
      }
      if (prevChild.type !== "paragraph") return false;
      var prevRange2 = _childLineRange(blockIndex, qi - 1);
      if (!prevRange2 || curRange.startLine - prevRange2.startLine !== 1) return false;
      var prevPfx2 = _quotePrefixAt(block, blockIndex, prevRange2.startLine);
      var prevBody = _quoteInnerOfLine(block, blockIndex, prevRange2.startLine);
      var mergedKids3 = mergeAdjacentInline((prevChild.children || []).concat(child.children || []));
      var lp3 = lastTextPath(mergedKids3);
      return commitRange(prevRange2.startLine, curRange.startLine,
        [prevPfx2 + prevBody + curBody2],
        { blockIndex: blockIndex, nodePath: lp3 ? [qi - 1].concat(lp3.path) : [qi - 1],
          offset: lp3 ? lp3.offset : 0 }, preCursor, "backspace");
    }

    function insertText(text, forceGroup, nativeDone) {
      if (!text) return false;

      // 停在不可编辑块边界（代码块/表格等）时键入 → 先建空行再写入
      var EH1 = window.MemoriaEditHandler;
      if (EH1 && insertAtNonEditableDock(EH1.cursorAST, text)) return true;

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
      // ── E28（2026-10-22）：引用块写入必须落在**引用内段落**上 ──
      // 事故（真机实测，CDP 9621）：在空引用行（`> `）里敲空格时，domToAst 给出的
      // nodePath 是 `[0]`（指向引用内的空段落），旧代码把它当"非 inline 叶子"处理，
      // 于是 `block.children = [text(" ")]` ——
      //   ① blockquote.children 里直接出现 text（parser 永远不会产出这种形状）；
      //   ② SourceGen.generateBlock(blockquote) 对 text 子节点生成 ""，⇒ 源码**一个字符都不变**，
      //      预览也不刷新 ⇒ 用户看到的就是「敲空格没反应」（真机 bodyLen 21→21，DOM 不变）；
      //   ③ 之后再敲字母也写不进去。
      // 修法：先把写入目标归一化到「引用内段落」，text 只能落在段落的 children 上。
      var inlineHost = block;
      var inlinePath = (cursor.nodePath || []).slice();
      var quoteIdx = -1;
      var quoteItemIdx = -1;
      if (block.type === "blockquote") {
        quoteIdx = inlinePath.length ? inlinePath[0] : 0;
        var qChild = (block.children || [])[quoteIdx];
        if (!qChild) {
          // 空引用块：补一个空段落，与 parser 的 `AST.blockquote([AST.paragraph([])])` 同形
          qChild = A.paragraph([]);
          if (!block.children) block.children = [];
          block.children[quoteIdx] = qChild;
          inlinePath = [quoteIdx];
          cursor.nodePath = inlinePath.slice();
        }
        if (qChild.type === "list") {
          // task-156：引用内列表 —— 写入目标必须是**item.children**。
          // 旧实现会把 list child 当段落覆盖成一段文字（list 整块丢失，随后 commit 写盘）⇒ R0。
          quoteItemIdx = inlinePath.length > 1 ? inlinePath[1] : 0;
          var qItem = qChild.items && qChild.items[quoteItemIdx];
          if (!qItem) return false;
          inlineHost = qItem;
          inlinePath = inlinePath.slice(2);
        } else {
          inlineHost = qChild;
          inlinePath = inlinePath.slice(1);
        }
      }
      if (inlinePath.length) {
        node = A.getNodeAt(inlineHost, inlinePath);
      }

      if (node && node.type === "text") {
        A.editText(node, cursor.offset, text);
        cursor.offset += text.length;
      } else if (!node || !A.isInline(node)) {
        // 空 block / 空 list item / 空引用段落：新建 Text 节点
        node = A.text(text);
        if (block.type === "list") {
          var itemIdx = (cursor.nodePath && cursor.nodePath.length) ? cursor.nodePath[0] : 0;
          var item = block.items && block.items[itemIdx];
          if (!item) return false;
          item.children = [node];
          cursor.nodePath = [itemIdx, 0];
        } else if (block.type === "blockquote") {
          // ★ 只写进引用内段落 / 列表项的 children，绝不写进 blockquote.children 或 list 块
          inlineHost.children = [node];
          cursor.nodePath = quoteItemIdx >= 0 ? [quoteIdx, quoteItemIdx, 0] : [quoteIdx, 0];
        } else {
          block.children = [node];
          cursor.nodePath = [0];
        }
        cursor.offset = text.length;
      } else {
        // 叶子但非 Text（CODE/MATH_INLINE/WIKI_LINK/LINK/ESCAPE）：暂不支持纯文本插入
        return false;
      }

      // 结构标记自动转换（段落输入 "# " / "- " / "1. " / "> " 等 → 标题/列表/引用）
      convertStructuralBlock(block, cursor);

      beginUndo("insert", preCursor, forceGroup);
      var ok = commit(block, cursor, nativeDone);
      if (ok) recordGroup("insert", cursor);
      return ok;
    }

    /**
     * 全量替换源码行范围 [startLine, endLine] 为新行，重渲染并恢复光标
     * 用于跨 block 操作（合并/删除空行等 block 结构变化场景）
     */
    function commitRange(startLine, endLine, newLines, newCursor, preCursor, kind) {
      beginUndo(kind, preCursor, true);
      _cancelBlockRepaint();   // AG103：这一段马上会被块级提交重渲 ⇒ 挂起的"停手重渲"只会重复劳动
      var rawLines = (state.doc.body || "").split("\n");
      var merged = rawLines.slice(0, startLine).concat(newLines, rawLines.slice(endLine + 1));
      state.doc.body = merged.join("\n");
      state.doc.lines = merged;
      state.doc.preview_body = null;  // 本地编辑使 preview_body 缓存过期，必须清空否则渲染旧内容
      if (!patchEditorLines(startLine, endLine - startLine + 1, newLines.length)) renderEditor(state.doc);   // 2026-09-25 AG101：源码面板只更新这一段（回车/合并原来整篇重建 5888 行）
      // M6b：预览侧结构编辑（回车拆段/合并/跨块删除）按行数差平移 KP 范围并同步列表/hover
      if (typeof window.__adjustKpRangesAfterSpanReplace === "function") {
        window.__adjustKpRangesAfterSpanReplace(startLine, endLine + 1, endLine - startLine + 1, newLines.length);
      }
      repaintPreview().then(function () {   // 2026-09-25：**结构性编辑的块级提交**（回车拆段/合并/跨块删除都经这里 ⇒ 不再整篇重渲、不再"渲染中"塌高度）
        restoreCursor(newCursor.blockIndex, newCursor.nodePath, newCursor.offset);
      });
      markDirty();
      recordGroup(kind, newCursor);
      return true;
    }

    /**
     * ★ 2026-10-23（0.4.7 任务 4 / N5）：**列表结构被编辑后，清空行号缓存**。
     *
     * 契约：`item.srcLine`（每项源码行，1-based）与 `list.itemSrcLine`（顶层项行号数组）
     * 都是**解析产物**。它们只在「AST 与源码一一对应」时可信（用于：
     *   ① 松散列表项间空行的逐字节重建 ② 多级列表空行重建）。
     * 一旦编辑增删/移动了项，行号就**全部失真**且不再连续 —— 若继续使用，
     * source-gen 会按「上一项行号差」补空行 ⇒ **凭空多出空行**（实测：删一个子项多 1 空行）。
     *
     * 因此**任何改动列表结构的编辑路径都必须调用本函数**（递归清到所有层级）。
     * 清空后 source-gen 自动退回「不补空行」的安全行为（宁可少一个空行，不可错乱）。
     *
     * @param {object} blockOrList 列表块或其子列表节点
     */
    function _invalidateListItemLines(blockOrList) {
      if (!blockOrList || !blockOrList.items) return;
      blockOrList.itemSrcLine = null;
      for (var li2 = 0; li2 < blockOrList.items.length; li2++) {
        var it2 = blockOrList.items[li2];
        if (!it2) continue;
        it2.srcLine = null;
        if (it2.list) _invalidateListItemLines(it2.list);
      }
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

      // ── 引用块内行首退格（task-156 Step2）：合并上一 child / 列表项合并 / 首项退列表 ──
      if (block.type === "blockquote") {
        return _backspaceAtBlockStartInQuote(block, cursor, preCursor);
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
        // ★ 2026-10-23（0.4.7 任务 4 / N5）：**改列表结构后必须清空行号缓存**。
        //   `srcLine` / `itemSrcLine` 是解析产物；删项后仍在但已失真 ⇒
        //   source-gen 会按「上一项行号差」补空行，导致**凭空多出空行**。
        _invalidateListItemLines(block);
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
     * 光标停在**不可编辑块边界**时（代码块/表格等，见 edit-handler 的 dockAtNonEditableBlock）
     * 键入或回车：先在块**下方**（offset>0）或**上方**（offset=0）新建空行，再写入文字。
     * text === "" 表示只新建空行（回车）。与图片块既有路径同款（见 splitParagraph 的 image 分支）。
     * @returns {boolean} true = 已处理
     */
    function insertAtNonEditableDock(cursor, text) {
      var EH = window.MemoriaEditHandler;
      var dock = EH && EH.dockAfter;
      if (!dock || dock.blockIndex < 0) return false;
      if (!_doc || !_doc.blocks) return false;
      var block = _doc.blocks[dock.blockIndex];
      if (!block || !NON_EDITABLE[block.type]) return false;
      var range = (_blockLineMap && _blockLineMap[dock.blockIndex]) || null;
      if (!range) return false;

      var raw = (state.doc.body || "").split("\n");
      var after = !dock.before;                                        // 停靠在块后
      var insertAt = after ? range.endLine + 1 : range.startLine;      // 块后 / 块前
      var newCursor = { blockIndex: dock.blockIndex + (after ? 1 : 0), nodePath: [], offset: 0 };
      var preCursor = cloneCursor(cursor || { blockIndex: dock.blockIndex, nodePath: [], offset: 0 });
      EH.dockAfter = null;                                             // 标记消费掉
      hlog("dock insert bi=" + dock.blockIndex + " after=" + after + " line=" + insertAt +
        " text=" + JSON.stringify(text));

      beginUndo(text ? "dockInsert" : "enter", preCursor, true);
      raw.splice(insertAt, 0, text || "");
      state.doc.body = raw.join("\n");
      state.doc.lines = raw;
      state.doc.preview_body = null;   // 本地编辑使缓存过期，必须清空否则渲染旧内容
      renderEditor(state.doc);
      repaintPreview().then(function () {   // 2026-09-25：边界插空行也走块级提交
        restoreCursor(newCursor.blockIndex, newCursor.nodePath, newCursor.offset);
        // 有文字：重渲染后递归走正常插入路径（此时新块已可编辑），保证字序与撤销分组正确
        if (text) insertText(text, true);
      });
      markDirty();
      if (!text) recordGroup("enter", newCursor);
      return true;
    }

    /**
     * Enter 拆分段落（insertParagraph）
     * 支持：段落、标题（后段变普通段落）、列表项（同列表内拆两项）
     * 拆分后全量重渲染并恢复光标到新块开头
     */
    function splitParagraph() {
      // 停在不可编辑块边界（代码块/表格等）按回车 → 在上/下方新建空行
      var EH0 = window.MemoriaEditHandler;
      if (EH0 && insertAtNonEditableDock(EH0.cursorAST, "")) return true;
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
          repaintPreview().then(function () {   // 2026-09-25：图片块结构编辑也走块级提交
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
      } else if (block.type === "blockquote") {
        // task-156 Step2：引用内 Enter（段落拆行 / 列表项续列 / 空项退列表）
        return _splitParagraphInQuote(block, cursor, preCursor, blockIndex);
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
        // Step3：左半沿用原项序号；右半新项 = 原号+1（有序时）；**其余项保持自己的 number**
        var _splitSrcItem = block.items[itemIdx];
        var _splitRightNo = (block.ordered && _splitSrcItem && _splitSrcItem.number > 0)
          ? _splitSrcItem.number + 1 : null;
        var newItems = block.items.slice(0, itemIdx + 1);
        newItems[itemIdx] = _listItemWithNumber(_splitSrcItem, sp2.left);
        newItems = newItems.concat([_listItemWithNumber(_splitSrcItem, sp2.right, _splitRightNo)],
          block.items.slice(itemIdx + 1));
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

      // 2026-09-25：**回车拆段（最常走的那条）改为块级提交** —— 原来这里整篇重渲 ⇒ 「按回车卡顿一下 + 画面上下闪」
      _cancelBlockRepaint();   // AG103：同上 —— 块级提交马上会重渲这一段
      _pendingStructural = repaintPreview().then(function () {
        var rb = (_doc && _doc.blocks && _doc.blocks[newCursor.blockIndex]) || null;
        hlog("splitParagraph re-rendered blocks=" + (_doc && _doc.blocks ? _doc.blocks.length : 0) +
          " block[" + newCursor.blockIndex + "].type=" + (rb ? rb.type : "?") +
          " items=" + (rb && rb.items ? rb.items.length : "-"));
        hlog("splitParagraph re-rendered, restore new cursor=" + _fmtCursor(newCursor));
        restoreCursor(newCursor.blockIndex, newCursor.nodePath, newCursor.offset);
      })["catch"](function (e) {
        // 结构性重渲失败：不让异常变成未处理 rejection；调用方（多行粘贴）通过
        // whenStructuralIdle 等待后仍会看到 cursorAST 未恢复，从而走"失败可见"分支。
        console.error("[MemoriaEditSync] splitParagraph 重渲失败：", e);
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
      if (NON_EDITABLE[ctx.block.type]) return { ok: false, message: T("cfg.style.notEditable") };
      var preCursor = cloneCursor(ctx.start);
      log("STYLE", "single before=[" + _fmtNodes(ctx.before) + "] middle=[" + _fmtNodes(ctx.middle) + "] after=[" + _fmtNodes(ctx.after) + "]");
      var sel = _applyStyleToBlock(ctx, formatType, color, forceApply ? "apply" : undefined);
      log("STYLE", "single selStart=" + _fmtCursor(sel.selStart) + " selEnd=" + _fmtCursor(sel.selEnd));
      beginUndo("format", preCursor, true);
      var ok = commitSelection(ctx.block, ctx.blockIndex, sel.selStart, sel.selEnd);
      log("STYLE", "single commit ok=" + ok);
      if (ok) recordGroup("format", { blockIndex: ctx.blockIndex, nodePath: sel.selEnd.nodePath, offset: sel.selEnd.offset });
      return { ok: ok, message: ok ? "" : T("cfg.style.applyFailed") };
    }

    /** 跨 block 样式应用：逐块变换，作为一个撤销单元提交，最后恢复跨块选区 */
    function _commitMultiStyle(formatType, color, range, forceApply) {
      var start = M.domToAst(range.startContainer, range.startOffset);
      var end = M.domToAst(range.endContainer, range.endOffset);
      log("STYLE", "multi domToAst start=" + (start ? JSON.stringify(start) : "null") + " end=" + (end ? JSON.stringify(end) : "null"));
      if (!start || !end || start.blockIndex >= end.blockIndex) {
        return { ok: false, message: T("cfg.style.rangeBoundary") };
      }

      var infos = [];
      for (var bi = start.blockIndex; bi <= end.blockIndex; bi++) {
        var block = _doc.blocks[bi];
        if (!block) return { ok: false, message: T("cfg.style.invalidBlock") };
        if (NON_EDITABLE[block.type]) return { ok: false, message: T("cfg.style.uneditableContent") };
        if (block.type === "list") return { ok: false, message: T("cfg.style.crossList") };
        if (block.type === "blockquote") return { ok: false, message: T("cfg.style.crossQuote") };

        var before = [], middle = [], after = [];
        if (bi === start.blockIndex) {
          var startChildren = block.children || [];
          if (!startChildren.length) {
            // 起点块是空行（nodePath=[] off=0）：无内容可拆，middle 为空
            before = []; middle = []; after = [];
          } else {
            var sp = splitInlineAt(startChildren, start.nodePath || [], start.offset);
            if (!sp) return { ok: false, message: T("cfg.style.boundaryUnsplit") };
            before = sp.left; middle = sp.right; after = [];
          }
        } else if (bi === end.blockIndex) {
          var endChildren = block.children || [];
          if (!endChildren.length) {
            // 终点块是空行（nodePath=[] off=0）：选区延伸到行尾，无内容可拆
            before = []; middle = []; after = [];
          } else {
            var ep = splitInlineAt(endChildren, end.nodePath || [], end.offset);
            if (!ep) return { ok: false, message: T("cfg.style.boundaryUnsplit") };
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
      return { ok: touched > 0, message: touched > 0 ? "" : T("cfg.style.applyFailed") };
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
      if (!_isSupportedFormat(formatType)) return { ok: false, message: T("cfg.style.unsupportedType") };
      log("STYLE", "applyStyle fmt=" + formatType + " color=" + (color || "null") + (forceApply ? " force=apply" : ""));
      // 点击应用 debug：选区将先经 domToAst 定位到 AST 节点（_extract 打印 cursor/middle），
      // 单段走 _commitSingleStyle（改写该 inline 树并提交源码行），跨段走 _commitMultiStyle
      console.log("[APPLY] fmt=" + formatType + " color=" + (color || "null") +
        " range=" + (typeof _describeRange === "function" ? _describeRange(range) : String(range)));

      var single = _extractSelectionMiddle(range);
      if (single) {
        console.log("[APPLY] single blockIndex=" + single.blockIndex +
          " blockType=" + (single.block && single.block.type) +
          " start=" + _fmtCursor(single.start) +
          " beforeN=" + (single.before || []).length +
          " middleN=" + (single.middle || []).length +
          " afterN=" + (single.after || []).length +
          " middle=" + _fmtNodes(single.middle));
        return _commitSingleStyle(single, formatType, color, forceApply);
      }
      console.log("[APPLY] multi: range → _commitMultiStyle（跨块或多块）");
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
     *
     * ★ 2026-10-24（task-79 阶段3）：**引用块跨段 / 同块内跨 item 也被接住**。
     *   背景：`_extractSelectionMiddle()` 对「跨引用段」「跨 list item」返回 null ⇒ 走到这里；
     *   而这里原来只接受 `start.blockIndex < end.blockIndex`，同一块内跨段直接 return false
     *   ⇒ 选区落在同一引用块的两段 / 同一列表的两项时，Delete 静默无效。
     *   现在按「段/项 = 源码行」的**块内粒度**映射：
     *     · quote：parser 逐行产出 `AST.paragraph`（block.prefixes 等长）⇒ 段索引 = 行偏移；
     *     · list ：每项一行（与既有 `listItemIndex` 行定位同口径）⇒ 项索引 = 行偏移。
     */
    function deleteSelectionMulti(range) {
      var start = M.domToAst(range.startContainer, range.startOffset);
      var end = M.domToAst(range.endContainer, range.endOffset);
      if (!start || !end) return false;
      var startBlock0 = _doc.blocks[start.blockIndex];
      var endBlock0 = _doc.blocks[end.blockIndex];
      if (!startBlock0 || !endBlock0) return false;

      // 同一 block 内跨「段/项」：只有 blockquote / list 是"多段容器"，其它类型同块 = 同一 inline 树
      var sameBlockSpan = false;
      if (start.blockIndex === end.blockIndex) {
        // task-156：引用内 list 的"段"是 item（原实现用 nodePath[0]=child 判不出跨 item）
        var sSeg = _segPos(startBlock0, start);
        var eSeg = _segPos(startBlock0, end);
        if (startBlock0.type === "blockquote" || startBlock0.type === "list") {
          if (sSeg < 0 || eSeg <= sSeg) return false;
          sameBlockSpan = true;
        } else {
          return false;
        }
      } else if (start.blockIndex >= end.blockIndex) {
        return false;
      }

      // 校验范围内所有 block 是否可随选区删除（stage4 语义，Lead 2026-10-24 裁决）
      //   · 原子块（表格 / 代码块 / 公式块 / mermaid）：**允许整块删除**。
      //     理由：这些块 contenteditable=false，Chromium 会把选区端点吸附到块边界 ⇒
      //     真实用户能表达的只有「整块被跨过 / 端点贴边界」，「只删半个表格」不可表达，
      //     所以按整块行区间删除是安全且一致的语义；单撤销可完整恢复。
      //   · frontmatter：**必须继续拒绝**（删掉 = 文档头损坏），返回 false 由调用方给可见提示。
      var delCounts = {};
      for (var bi = start.blockIndex; bi <= end.blockIndex; bi++) {
        var blk = _doc.blocks[bi];
        if (!blk) { log("STYLE", "deleteMulti ABORT: block " + bi + " 缺失"); return false; }
        if (blk.type === "frontmatter") {
          log("STYLE", "deleteMulti ABORT: block " + bi + " type=frontmatter 不可删除（文档头）");
          return false;
        }
        delCounts[blk.type] = (delCounts[blk.type] || 0) + 1;
      }

      var startBlock = startBlock0;
      var endBlock = endBlock0;
      var preCursor = cloneCursor(start);

      /**
       * 块内 inline 根 + 相对路径：列表 / 引用需下钻到 item / 段落内部，
       * 否则会把 item 容器当成 inline 节点处理（AST 非法嵌套、文本丢失）。
       */
      function inlineCtx(block, cursor) {
        var path = cursor.nodePath || [];
        if (block.type === "list") {
          var ii = path.length ? path[0] : 0;
          var item = block.items && block.items[ii];
          if (!item) return null;
          return { children: item.children || [], path: path.slice(1) };
        }
        if (block.type === "blockquote") {
          var qi = path.length ? path[0] : 0;
          var inner = block.children && block.children[qi];
          if (!inner) return null;
          if (inner.type === "list") {
            // task-156：引用内列表 ⇒ 下钻到 item（否则把 list 当 inline 容器 = 丢项）
            var qii = path.length > 1 ? path[1] : 0;
            var qItem = inner.items && inner.items[qii];
            if (!qItem) return null;
            return { children: qItem.children || [], path: path.slice(2),
                     quoteChild: inner, quoteItemIdx: qii };
          }
          return { children: inner.children || [], path: path.slice(1), quoteChild: inner };
        }
        return { children: block.children || [], path: path };
      }
      var sc = inlineCtx(startBlock, start);
      var ec = inlineCtx(endBlock, end);

      // 拆分首块左半、末块右半（端点落在块边界/无文本块时走 splitInlineAtEdge，不再静默失败）
      var sp = sc ? splitInlineAtEdge(sc.children, sc.path, start.offset) : null;
      var ep = ec ? splitInlineAtEdge(ec.children, ec.path, end.offset) : null;
      if (!sp || !ep) {
        log("STYLE", "deleteMulti ABORT: split=null start=" + _fmtCursor(start) + " end=" + _fmtCursor(end));
        return false;
      }

      var before = sp.left;
      var after = ep.right;
      var joined = mergeAdjacentInline(before.concat(after));

      // 结果 block 沿用首块类型（heading 保留级别；列表保留列表形态，item 前缀 `- ` 不丢；
      // 引用块保留为引用块，前缀由 source-gen 默认写 `> `）；
      // 全部删空则退化为空行
      var newBlock;
      if (startBlock.type === "list" && before.length) {
        // Step3：合并结果沿用起始项的序号
        var _delStartItemIdx = (start.listItemIndex != null)
          ? start.listItemIndex : ((start.nodePath && start.nodePath[0]) || 0);
        var _delStartItem = (startBlock.items && startBlock.items[_delStartItemIdx]) || null;
        newBlock = A.list(startBlock.ordered, [_listItemWithNumber(_delStartItem, joined)]);
      } else if (startBlock.type === "heading") {
        newBlock = A.heading(startBlock.level, joined);
      } else if (startBlock.type === "blockquote") {
        // stage3/task-156：合并结果留在引用块内；**保留被编辑 child 的形态**：
        //   段落 child → 单段引用；list child → 单 item 列表（否则整块 list 被压成一段 = 丢项）
        var qStartChild = sc && sc.quoteChild;
        var qStartItem = (qStartChild && qStartChild.type === "list" && sc && sc.quoteItemIdx != null)
          ? ((qStartChild.items || [])[sc.quoteItemIdx] || null) : null;
        var qInner = (qStartChild && qStartChild.type === "list")
          ? A.list(qStartChild.ordered, [_listItemWithNumber(qStartItem, joined)])
          : A.paragraph(joined);
        newBlock = A.blockquote([qInner]);
      } else {
        newBlock = A.paragraph(joined);
      }
      var newLines = joined.length ? [G.generateBlock(newBlock)] : [""];

      // 计算要替换的源码行范围（0-based）
      // ★ 用真实的 block→行映射（_blockLineMap，按真实源码行表构建），不能用 M.astToSrc：
      //   后者按"逐块行数累加"推行号，一旦存在不属于任何块的行（块间空行等）就整体偏移。
      //   实测：block3 实际在 L5，astToSrc 却返回 3 → 删除整体上移一行且漏删末块所在行。
      var blm = window.__blockLineMap || null;
      var startLine, endLine;
      if (blm && blm[start.blockIndex] && blm[end.blockIndex]) {
        // 列表块一个 item 一行：用 item 索引精确定位到行，
        // 否则"从列表头部删到中段"会连带删掉**后面没被选中**的 item（_blockLineMap 只到整块粒度）
        startLine = blm[start.blockIndex].startLine + (start.listItemIndex || 0);
        endLine = (endBlock.type === "list")
          ? (blm[end.blockIndex].startLine + (end.listItemIndex || 0))
          : blm[end.blockIndex].endLine;
        // ★ stage3：引用块「一段 = 一行」（parser 逐行产出 paragraph，prefixes 等长）
        //   ⇒ 段索引 nodePath[0] 就是块内行偏移。没有这条映射时只能整块粒度删除，
        //   会把末段之后未被选中的引用内容一起删掉。
        // task-156：引用块行区间必须按 child 的**真实行跨度**（list child 可跨多行），
        //   旧实现 `blm.startLine + nodePath[0]` 只在"1 child = 1 行"时成立。
        if (startBlock.type === "blockquote") {
          var sChildIdx = (start.nodePath && start.nodePath.length) ? start.nodePath[0] : -1;
          var sChild = sChildIdx >= 0 ? (startBlock.children || [])[sChildIdx] : null;
          var sRange = _childLineRange(start.blockIndex, sChildIdx);
          if (sRange) startLine = sRange.startLine;
          if (sChild && sChild.type === "list" && start.nodePath.length > 1) {
            var sItemRange = _quoteItemLineRange(start.blockIndex, sChildIdx, start.nodePath[1]);
            if (sItemRange) startLine = sItemRange.startLine;
          }
        }
        if (endBlock.type === "blockquote") {
          var eChildIdx = (end.nodePath && end.nodePath.length) ? end.nodePath[0] : -1;
          var eChild = eChildIdx >= 0 ? (endBlock.children || [])[eChildIdx] : null;
          var eRange = _childLineRange(end.blockIndex, eChildIdx);
          if (eRange) endLine = eRange.endLine;
          if (eChild && eChild.type === "list" && end.nodePath.length > 1) {
            var eItemRange = _quoteItemLineRange(end.blockIndex, eChildIdx, end.nodePath[1]);
            if (eItemRange) endLine = eItemRange.endLine;
          }
        }
      } else {
        var startSrc = M.astToSrc(start.blockIndex, start.nodePath || [], start.offset);
        var endSrc = M.astToSrc(end.blockIndex, end.nodePath || [], end.offset);
        if (!startSrc || !endSrc) return false;
        startLine = startSrc.line;
        endLine = endSrc.line;
      }
      if (startLine > endLine) return false;

      // 新光标：合并处（before 末尾）。首块为列表/引用时合并结果只剩一个 item / 一个内部段落，
      // 路径需带 item / 段落前缀
      var cursorPrefix = (startBlock.type === "list" && before.length) ? [0]
        : (startBlock.type === "blockquote"
            ? ((sc && sc.quoteChild && sc.quoteChild.type === "list")
                ? [((start.nodePath && start.nodePath[0]) || 0), 0]
                : [((start.nodePath && start.nodePath[0]) || 0)])
            : []);
      var beforeLen = renderedLenOfNodes(before);
      var cursorRel = joined.length ? renderedOffsetToPath(joined, beforeLen) : null;
      var newCursor = cursorRel
        ? { blockIndex: start.blockIndex, nodePath: cursorPrefix.concat(cursorRel.nodePath || []), offset: cursorRel.offset }
        : { blockIndex: start.blockIndex, nodePath: cursorPrefix, offset: 0 };

      log("STYLE", "deleteMulti blocks=" + (end.blockIndex - start.blockIndex + 1) +
        " srcLines=[" + startLine + "," + endLine + "]" +
        " blm=[s" + JSON.stringify(blm && blm[start.blockIndex]) + " e" + JSON.stringify(blm && blm[end.blockIndex]) + "]" +
        " newSrc=" + JSON.stringify(newLines[0]));
      var okDel = commitRange(startLine, endLine, newLines, newCursor, preCursor, "deleteSelection");
      if (okDel) _notifyDeletionSummary(delCounts);
      return okDel;
    }

    // ── stage4：删除摘要提示（原子块被整删时）────────────────────────────
    var _DEL_NAME_KEY = {
      paragraph: "blockNameParagraph", heading: "blockNameHeading", list: "blockNameList",
      blockquote: "blockNameQuote", table: "blockNameTable", code_block: "blockNameCode",
      math_block: "blockNameMath", mermaid: "blockNameMermaid",
    };
    var _DEL_ORDER = ["paragraph", "heading", "list", "blockquote", "table", "code_block", "math_block", "mermaid"];
    var _DEL_ATOMIC = { code_block: 1, table: 1, math_block: 1, mermaid: 1 };

    /**
     * 删除范围含**原子块**时给事后摘要提示（不是确认框）。
     *
     * 为什么必须提示：长选区滚出视口后，用户可能没意识到中间夹着整块表格/代码；
     * 数据已经删除，必须让用户知道"刚才删掉了什么"，否则连是否该撤销都无从判断。
     * 为什么纯可编辑块不提示：删段落/列表/引用是高频动作，每次都弹 = 噪音。
     * 通道：复用 `showFlashInfo`（阶段2 的 showFlashError 是失败提示，两者不混）。
     *
     * @param {Object<string,number>} counts — 被删除块的类型计数
     */
    function _notifyDeletionSummary(counts) {
      if (!counts) return;
      var hasAtomic = false;
      for (var t in _DEL_ATOMIC) { if (counts[t] > 0) { hasAtomic = true; break; } }
      if (!hasAtomic) return;
      var parts = [];
      for (var i = 0; i < _DEL_ORDER.length; i++) {
        var ty = _DEL_ORDER[i];
        var n = counts[ty] || 0;
        if (n <= 0 || !_DEL_NAME_KEY[ty]) continue;
        parts.push(T("cfg.clip.blockCount", { name: T("cfg.clip." + _DEL_NAME_KEY[ty]), n: n }));
      }
      if (!parts.length) return;
      var msg = T("cfg.clip.deletedSummary", { parts: parts.join("、") });
      try { showFlashInfo(msg); } catch (e) { /* 提示失败不影响删除结果 */ }
      log("STYLE", "deleteMulti summary: " + msg);
    }

    /**
     * task-156 Step3：重建列表项时**继承原项的手写序号**（有序）与缩进。
     * 目的：Enter 拆项 / 选区删除合并 / 粘贴替换时，**未触碰的其它项行逐字节不变**
     *   （task-157 的保真契约）——而不是整层回退 base+idx 把用户序号全部重排。
     *  · 原项有序且 number>0 ⇒ 沿用；`numberOverride` 用于"拆出的右半新项"= 原号+1。
     *  · 无序项 / 旧 AST（无 number）⇒ 不设 number，让 source-gen 走既有兜底。
     */
    function _listItemWithNumber(srcItem, children, numberOverride) {
      var item = A.listItem(children || []);
      if (srcItem) {
        if (srcItem.indent != null) item.indent = String(srcItem.indent);
        if (numberOverride != null && numberOverride > 0) item.number = numberOverride;
        else if (srcItem.number > 0) item.number = srcItem.number;
      } else if (numberOverride != null && numberOverride > 0) {
        item.number = numberOverride;
      }
      return item;
    }

    /**
     * 以「首块类型」造一个块（列表→单 item 列表 / 引用→单段引用 / 标题→同级别标题 / 其它→段落）。
     * 用于 stage4 删除合并块与 stage5 粘贴替换的首/尾块。
     * 原子块（表格/代码/公式/mermaid）在这里**降级为段落**：它们不能承载内联文本。
     */
    function _blockLike(kindBlock, inlineNodes, shapeChild, srcItem) {
      var nodes = inlineNodes || [];
      if (!kindBlock) return A.paragraph(nodes);
      if (kindBlock.type === "list") {
        // Step3：被替换的那个 item 若有序，合并结果沿用它的手写序号（未触碰项不变）
        return A.list(kindBlock.ordered, [_listItemWithNumber(srcItem, nodes)]);
      }
      if (kindBlock.type === "heading") return A.heading(kindBlock.level, nodes);
      if (kindBlock.type === "blockquote") {
        // task-156：被编辑的引用 child 是 list 时，结果必须仍是"引用 + 单 item 列表"，
        //   否则删除/粘贴会把整块 list 压成一段 = 丢项（静默数据损坏）。
        if (shapeChild && shapeChild.type === "list") {
          return A.blockquote([A.list(shapeChild.ordered, [_listItemWithNumber(srcItem, nodes)])]);
        }
        return A.blockquote([A.paragraph(nodes)]);
      }
      return A.paragraph(nodes);
    }

    /** 把「粘贴内容的中段」按 markdown 解析成块；**frontmatter 一律降级为段落**
     *  （粘贴绝不能造出文档头；内容仍可见、而单撤销可回退）。 */
    function _parsePastedBlocks(chunk) {
      var text = String(chunk == null ? "" : chunk);
      if (!text) return [];
      var blocks = [];
      try { blocks = P.parseBlocks(text.split("\n")) || []; } catch (e) { blocks = []; }
      if (!blocks.length) return [A.paragraph([A.text(text)])];
      var out = [];
      for (var i = 0; i < blocks.length; i++) {
        var b = blocks[i];
        if (!b) continue;
        if (b.type === "frontmatter") {
          log("STYLE", "pasteReplace: frontmatter 降级为段落（粘贴不得造文档头）");
          out.push(A.paragraph([A.text(String(b.yaml || ""))]));
        } else {
          out.push(b);
        }
      }
      return out;
    }

    /** 块数组 → 源码行数组（每块至少一行；空数组退化为一个空行）。 */
    function _blocksToSrcLines(blocks) {
      var out = [];
      for (var i = 0; i < (blocks || []).length; i++) {
        var src = String(G.generateBlock(blocks[i]));
        var ls = src.split("\n");
        for (var k = 0; k < ls.length; k++) out.push(ls[k]);
      }
      return out.length ? out : [""];
    }

    /**
     * ★ stage5（task-83）：**粘贴 = 替换选区**（单行/多行、跨块/同块跨段都支持；单撤销）。
     *
     * 关键设计（Lead 2026-10-24 裁决，不要改）：
     *  · **不做"先删再插"两次编辑**：直接算好「删除行区间 + 新行集合」，**一次 `commitRange`**
     *    提交 ⇒ 天然只有一个 undo 条目 ⇒ 不可能出现"内容删了但没粘上"的半成品（静默数据损坏）。
     *  · 单行粘贴 = 纯文本内联替换（**不解析** markdown：粘一句 `# x` 不该变成标题）。
     *  · 多行粘贴 = 三段式：`[首块类型(before + 第 1 行)] + [中段按 markdown 解析] + [末块类型(最后 1 行 + after)]`；
     *    中段解析出的 frontmatter 降级为段落。
     *  · 光标落在**粘贴内容末尾**（after 非空时也是粘贴内容末尾：否则下一次输入会跳到旧文本后面）。
     *  · 选区含原子块（表格/代码/公式/mermaid）⇒ 与删除同一语义（整块跨过即整删）+ 删除摘要；
     *    frontmatter ⇒ 拒绝并回 false（调用方给可见提示）。
     *
     * @param {Range} range — 浏览器选区（可跨块）
     * @param {string} rawText — 剪贴板 text/plain
     * @returns {boolean}
     */
    function replaceSelectionWithText(range, rawText) {
      var text = String(rawText == null ? "" : rawText).replace(/\r\n?/g, "\n");
      // 复制的跨行文本常带一个结尾换行：只去掉**一个**（否则会凭空多一个空行块）
      if (text.length > 1 && text.charAt(text.length - 1) === "\n") text = text.slice(0, -1);
      if (!range || !text) return false;
      var start = M.domToAst(range.startContainer, range.startOffset);
      var end = M.domToAst(range.endContainer, range.endOffset);
      if (!start || !end) return false;
      var startBlock = _doc.blocks[start.blockIndex];
      var endBlock = _doc.blocks[end.blockIndex];
      if (!startBlock || !endBlock) return false;
      var lines = text.split("\n");

      if (start.blockIndex === end.blockIndex) {
        // 同一行内树 ⇒ 内联替换（保块类型）
        var ctx = _extractSelectionMiddle(range);
        if (ctx) return _replaceInlineSingle(ctx, lines);
        // 同块跨段/跨项（quote/list）⇒ 走行粒度多块替换
        if (startBlock.type !== "blockquote" && startBlock.type !== "list") return false;
        var sSeg = (start.nodePath && start.nodePath.length) ? start.nodePath[0] : -1;
        var eSeg = (end.nodePath && end.nodePath.length) ? end.nodePath[0] : -1;
        if (sSeg < 0 || eSeg <= sSeg) return false;
      } else if (start.blockIndex > end.blockIndex) {
        return false;
      }
      return _replaceMulti(start, end, startBlock, endBlock, lines);
    }

    /** 单块内联替换（同一 inline 树；ctx 来自 _extractSelectionMiddle）。 */
    function _replaceInlineSingle(ctx, lines) {
      var preCursor = cloneCursor(ctx.start);
      if (lines.length === 1) {
        var merged = mergeAdjacentInline(ctx.before.concat([A.text(lines[0])], ctx.after));
        if (ctx.isList) ctx.block.items[ctx.itemIdx].children = merged;
        else if (ctx.isQuote) ctx.block.children[ctx.quoteIdx].children = merged;
        else ctx.block.children = merged;
        var prefix = ctx.isList ? [ctx.itemIdx] : (ctx.isQuote ? [ctx.quoteIdx] : []);
        var pastedEnd = renderedLenOfNodes(ctx.before) + lines[0].length;
        var rel = renderedOffsetToPath(merged, pastedEnd);
        if (!rel) { var lp = lastTextPath(merged); rel = lp ? { nodePath: lp.path, offset: lp.offset } : { nodePath: [], offset: 0 }; }
        var cursor = { blockIndex: ctx.blockIndex, nodePath: prefix.concat(rel.nodePath || []), offset: rel.offset };
        beginUndo("pasteReplace", preCursor, true);
        var ok = commit(ctx.block, cursor);
        if (ok) recordGroup("pasteReplace", cursor);
        return ok;
      }
      // 多行：容器所在源码行 → 块序列
      var blm = window.__blockLineMap || null;
      var rng = blm && blm[ctx.blockIndex];
      if (!rng) return false;
      var startLine = rng.startLine, endLine = rng.endLine;
      if (ctx.isList) { startLine = rng.startLine + ctx.itemIdx; endLine = startLine; }
      else if (ctx.isQuote) { startLine = rng.startLine + ctx.quoteIdx; endLine = startLine; }
      var blocks = [];
      blocks.push(_blockLike(ctx.block, ctx.before.concat([A.text(lines[0])])));
      if (lines.length > 2) blocks = blocks.concat(_parsePastedBlocks(lines.slice(1, lines.length - 1).join("\n")));
      var tailInline = [A.text(lines[lines.length - 1])].concat(ctx.after);
      blocks.push(_blockLike(ctx.block, tailInline));
      var newLines = _blocksToSrcLines(blocks);
      var tailIdx = ctx.blockIndex + blocks.length - 1;
      var tailPrefix = (ctx.isList || ctx.isQuote) ? [0] : [];
      var lastLineLen = lines[lines.length - 1].length;
      var relT = renderedOffsetToPath(tailInline, lastLineLen);
      var cursorT = { blockIndex: tailIdx, nodePath: tailPrefix.concat(relT ? relT.nodePath : []), offset: relT ? relT.offset : 0 };
      return commitRange(startLine, endLine, newLines, cursorT, preCursor, "pasteReplace");
    }

    /** 跨块 / 同块跨段的多块替换（语义与 deleteSelectionMulti 对齐；**必须与它同步维护**）。 */
    function _replaceMulti(start, end, startBlock, endBlock, lines) {
      var preCursor = cloneCursor(start);
      function inlineCtx(block, cursor) {
        var path = cursor.nodePath || [];
        if (block.type === "list") {
          var ii = path.length ? path[0] : 0;
          var item = block.items && block.items[ii];
          if (!item) return null;
          return { children: item.children || [], path: path.slice(1) };
        }
        if (block.type === "blockquote") {
          var qi = path.length ? path[0] : 0;
          var inner = block.children && block.children[qi];
          if (!inner) return null;
          if (inner.type === "list") {
            var qii = path.length > 1 ? path[1] : 0;
            var qItem = inner.items && inner.items[qii];
            if (!qItem) return null;
            return { children: qItem.children || [], path: path.slice(2),
                     quoteChild: inner, quoteItemIdx: qii };
          }
          return { children: inner.children || [], path: path.slice(1), quoteChild: inner };
        }
        return { children: block.children || [], path: path };
      }
      var sc = inlineCtx(startBlock, start);
      var ec = inlineCtx(endBlock, end);
      // Step3：取"被替换的原列表项"（有序项要在合并结果里继承其手写序号）
      function _srcItemOf(block0, cur, qChild) {
        if (!block0 || !cur) return null;
        if (block0.type === "list") {
          var ii = (cur.listItemIndex != null) ? cur.listItemIndex : ((cur.nodePath && cur.nodePath[0]) || 0);
          return (block0.items && block0.items[ii]) || null;
        }
        if (block0.type === "blockquote" && qChild && qChild.type === "list") {
          var qii = (cur.nodePath && cur.nodePath.length > 1) ? cur.nodePath[1] : 0;
          return (qChild.items && qChild.items[qii]) || null;
        }
        return null;
      }
      var _startSrcItem = _srcItemOf(startBlock, start, sc && sc.quoteChild);
      var _endSrcItem = _srcItemOf(endBlock, end, ec && ec.quoteChild);
      var sp = sc ? splitInlineAtEdge(sc.children, sc.path, start.offset) : null;
      var ep = ec ? splitInlineAtEdge(ec.children, ec.path, end.offset) : null;
      if (!sp || !ep) {
        log("STYLE", "pasteReplace ABORT: split=null start=" + _fmtCursor(start) + " end=" + _fmtCursor(end));
        return false;
      }
      // 校验（与 deleteSelectionMulti 同语义）：frontmatter 拒绝；原子块允许整块跨过
      var delCounts = {};
      for (var bi = start.blockIndex; bi <= end.blockIndex; bi++) {
        var blk = _doc.blocks[bi];
        if (!blk) return false;
        if (blk.type === "frontmatter") {
          log("STYLE", "pasteReplace ABORT: block " + bi + " type=frontmatter 不可删除（文档头）");
          return false;
        }
        delCounts[blk.type] = (delCounts[blk.type] || 0) + 1;
      }
      var blocks = [];
      if (lines.length === 1) {
        var mergedOne = mergeAdjacentInline(sp.left.concat([A.text(lines[0])], ep.right));
        blocks.push(_blockLike(startBlock, mergedOne, sc && sc.quoteChild, _startSrcItem));
      } else {
        blocks.push(_blockLike(startBlock, sp.left.concat([A.text(lines[0])]), sc && sc.quoteChild, _startSrcItem));
        if (lines.length > 2) blocks = blocks.concat(_parsePastedBlocks(lines.slice(1, lines.length - 1).join("\n")));
        blocks.push(_blockLike(endBlock, [A.text(lines[lines.length - 1])].concat(ep.right), ec && ec.quoteChild, _endSrcItem));
      }
      var newLines = _blocksToSrcLines(blocks);

      // 行区间（与 deleteSelectionMulti 同一套映射：引用块一段=一行；列表一项=一行）
      var blm = window.__blockLineMap || null;
      var startLine, endLine;
      if (blm && blm[start.blockIndex] && blm[end.blockIndex]) {
        startLine = blm[start.blockIndex].startLine + (start.listItemIndex || 0);
        endLine = (endBlock.type === "list")
          ? (blm[end.blockIndex].startLine + (end.listItemIndex || 0))
          : blm[end.blockIndex].endLine;
        // task-156：引用块行区间按 child 真实跨度（list child 可跨多行）
        if (startBlock.type === "blockquote") {
          var rsChildIdx = (start.nodePath && start.nodePath.length) ? start.nodePath[0] : -1;
          var rsChild = rsChildIdx >= 0 ? (startBlock.children || [])[rsChildIdx] : null;
          var rsRange = _childLineRange(start.blockIndex, rsChildIdx);
          if (rsRange) startLine = rsRange.startLine;
          if (rsChild && rsChild.type === "list" && start.nodePath.length > 1) {
            var rsItem = _quoteItemLineRange(start.blockIndex, rsChildIdx, start.nodePath[1]);
            if (rsItem) startLine = rsItem.startLine;
          }
        }
        if (endBlock.type === "blockquote") {
          var reChildIdx = (end.nodePath && end.nodePath.length) ? end.nodePath[0] : -1;
          var reChild = reChildIdx >= 0 ? (endBlock.children || [])[reChildIdx] : null;
          var reRange = _childLineRange(end.blockIndex, reChildIdx);
          if (reRange) endLine = reRange.endLine;
          if (reChild && reChild.type === "list" && end.nodePath.length > 1) {
            var reItem = _quoteItemLineRange(end.blockIndex, reChildIdx, end.nodePath[1]);
            if (reItem) endLine = reItem.endLine;
          }
        }
      } else {
        var startSrc = M.astToSrc(start.blockIndex, start.nodePath || [], start.offset);
        var endSrc = M.astToSrc(end.blockIndex, end.nodePath || [], end.offset);
        if (!startSrc || !endSrc) return false;
        startLine = startSrc.line;
        endLine = endSrc.line;
      }
      if (startLine > endLine) return false;

      // 光标：粘贴内容末尾
      var tailIdx = start.blockIndex + blocks.length - 1;
      // task-156：引用内列表 ⇒ 结果落在 [childIdx, itemIdx]；引用内段落 ⇒ [childIdx]
      var prefix;
      if (startBlock.type === "list") {
        prefix = [0];
      } else if (startBlock.type === "blockquote") {
        var pChildIdx = (start.nodePath && start.nodePath.length) ? start.nodePath[0] : 0;
        prefix = (sc && sc.quoteChild && sc.quoteChild.type === "list") ? [pChildIdx, 0] : [pChildIdx];
      } else {
        prefix = [];
      }
      var cursor;
      if (lines.length === 1) {
        var joinedOne = mergeAdjacentInline(sp.left.concat([A.text(lines[0])], ep.right));
        var offOne = renderedLenOfNodes(sp.left) + lines[0].length;
        var relOne = renderedOffsetToPath(joinedOne, offOne);
        cursor = { blockIndex: start.blockIndex, nodePath: prefix.concat(relOne ? relOne.nodePath : []), offset: relOne ? relOne.offset : 0 };
      } else {
        var tailInlineM = [A.text(lines[lines.length - 1])].concat(ep.right);
        var relM = renderedOffsetToPath(tailInlineM, lines[lines.length - 1].length);
        cursor = { blockIndex: tailIdx, nodePath: prefix.concat(relM ? relM.nodePath : []), offset: relM ? relM.offset : 0 };
      }
      log("STYLE", "pasteReplace blocks=" + (end.blockIndex - start.blockIndex + 1) +
        " srcLines=[" + startLine + "," + endLine + "] lines=" + lines.length +
        " newBlocks=" + blocks.length + " newSrc0=" + JSON.stringify(newLines[0]));
      var okRep = commitRange(startLine, endLine, newLines, cursor, preCursor, "pasteReplace");
      if (okRep) _notifyDeletionSummary(delCounts);
      return okRep;
    }

    /**
     * task-156 Step2：引用块内列表的 Tab（降级 dir=+1）/ Shift+Tab（升级 dir=-1）。
     * 与顶层 `indentListLevel` **同构**（同一种树操作），差异只在回写方式：
     *   · 在 list 的**克隆**上改树（失败/行数变化都不污染真实 AST）；
     *   · 用 source-gen 生成该 list child 的内层行，再逐行加回**原引用前缀**，只替换该 child 行区间；
     *   · 行数必须不变（缩进/升降级只改层级，不改行数）⇒ 否则拒绝，避免写坏引用块。
     */
    function _indentQuoteListLevel(block, cursor, dir) {
      var blockIndex = cursor.blockIndex;
      var path = cursor.nodePath || [];
      var qi = path.length ? path[0] : -1;
      var listChild = qi >= 0 ? (block.children || [])[qi] : null;
      if (!listChild || listChild.type !== "list" || !listChild.items || !listChild.items.length) return false;
      var rng = _childLineRange(blockIndex, qi);
      if (!rng) return false;
      var expected = rng.endLine - rng.startLine + 1;
      var cloned;
      try { cloned = JSON.parse(JSON.stringify(listChild)); } catch (e) { return false; }

      var EH = window.MemoriaEditHandler;
      var listPath = (EH && EH.listPath && EH.listPath.length) ? EH.listPath.slice() : null;
      if (!listPath) {
        var topIdx = path.length > 1 ? path[1] : 0;
        listPath = [topIdx];
      }
      function pathToHit(root, lp) {
        var list2 = root;
        var parentItem = null;
        for (var d = 0; d < lp.length; d++) {
          var ii = lp[d];
          if (!list2 || !list2.items || ii < 0 || ii >= list2.items.length) return null;
          var it = list2.items[ii];
          if (d === lp.length - 1) return { parentList: list2, index: ii, parentItem: parentItem, item: it };
          if (!it.list) return null;
          parentItem = it;
          list2 = it.list;
        }
        return null;
      }
      var found = pathToHit(cloned, listPath);
      if (!found) return false;
      var curItem = found.item;
      var curList = found.parentList;
      var curListParentItem = found.parentItem;

      if (dir > 0) {
        if (found.index === 0) return false;
        var prevSib = found.parentList.items[found.index - 1];
        if (!prevSib) return false;
        if (!prevSib.list) prevSib.list = A.list(curList.ordered, []);
        found.parentList.items.splice(found.index, 1);
        curItem.indent = (prevSib.indent != null ? prevSib.indent : "") + "  ";
        delete curItem.number;   // 换层 ⇒ 该层按 1.. 重新编号（与顶层 Tab 行为一致）
        prevSib.list.items.push(curItem);
      } else {
        if (!curListParentItem) return false;
        var parentPath = listPath.length > 1 ? listPath.slice(0, listPath.length - 1) : null;
        var grand = parentPath ? pathToHit(cloned, parentPath) : null;
        if (!grand) return false;
        found.parentList.items.splice(found.index, 1);
        curItem.indent = curListParentItem.indent != null ? curListParentItem.indent : "";
        delete curItem.number;
        grand.parentList.items.splice(grand.index + 1, 0, curItem);
        if (curList.items.length === 0 && curListParentItem) delete curListParentItem.list;
      }

      _invalidateListItemLines(cloned);
      var innerLines = G.generateBlock(cloned).split("\n");
      if (innerLines.length !== expected) return false;   // 行数不变是安全前提
      var base = (_blockLineMap && _blockLineMap[blockIndex]) ? _blockLineMap[blockIndex].startLine : 0;
      var newLines = [];
      for (var k = 0; k < innerLines.length; k++) {
        var pfxIdx = rng.startLine - base + k;
        var pfx = (block.prefixes && block.prefixes[pfxIdx] != null) ? block.prefixes[pfxIdx] : "> ";
        newLines.push(pfx + innerLines[k]);
      }
      // 光标落到**被移动项所属的顶层项**开头（nodePath 只支持顶层 item 下标；嵌套精确落点由后续点击决定）
      var topAfter = 0;
      if (dir > 0) {
        topAfter = listPath.length ? listPath[0] : 0;
      } else {
        topAfter = (listPath.length <= 1) ? (grand.index + 1) : listPath[0];
      }
      var preCursor = cloneCursor(cursor);
      commitRange(rng.startLine, rng.endLine, newLines,
        { blockIndex: blockIndex, nodePath: [qi, topAfter], offset: 0 }, preCursor, "indent");
      return true;
    }

    /**
     * ★ 2026-10-23（0.4.7 任务 4 / N4）：多级列表**升降级**。
     *
     * `dir = +1` 降级（Tab）：把当前项从所在列表移出，挂到「同级的前一项」的子列表末尾。
     *   - 若是列表首项 ⇒ 无处可降 ⇒ 返回 false（交调用方决定，比如插空格）
     * `dir = -1` 升级（Shift+Tab）：把当前项从子列表移出，插到其父项**之后**（同级）。
     *   - 若已在顶层 ⇒ 返回 false
     *
     * 实现方式：直接改 AST 的 list 结构，再用 `G.generateBlock` 重写该块源码行，
     * 经 `commitRange` 提交（**单个撤销单元**）。
     * ⚠️ 改动结构后**必须调 `_invalidateListItemLines`** —— 见其注释里的契约。
     *
     * @returns {boolean} 是否执行了升降级
     */
    function indentListLevel(dir) {
      var ctx = getEditContext();
      if (!ctx) return false;
      var block = ctx.block;
      // task-156 Step2：引用块内列表的 Tab/Shift+Tab（复用同构树逻辑，只是回写该 list child 行区间）
      if (block && block.type === "blockquote") {
        return _indentQuoteListLevel(block, ctx.cursor, dir);
      }
      if (!block || block.type !== "list") return false;
      var cursor = ctx.cursor;

      var range = (_blockLineMap && _blockLineMap[cursor.blockIndex]) || null;
      if (!range) return false;
      var preCursor = cloneCursor(cursor);

      /**
       * ★ 定位当前项：用**扁平 li 索引**反查树路径（方案 C，2026-10-23）。
       *
       * 为什么不用 `cursor.nodePath`：现有 6 处代码一律按「nodePath[0]=顶层 item 下标、
       * nodePath.slice(1)=inline 路径」解释（L10992/11143/11236/11686/11819/12142、L11071）。
       * 嵌套后 nodePath 前缀的语义无法与 inline 索引区分 ⇒ 本函数改用
       * `EH.listItemIndex`（`getPreviewCursor()` 产出的**扁平 li 索引**，
       * 对应 `blockEl.querySelectorAll("li")` 的文档序），自己遍历树反查路径。
       * 这样**不动既有 6 处代码、不动 syncFromSelection**，改动最小。
       */
      function flatLiToTreePath(rootList, flatIdx) {
        var n = 0;
        var hit = null;
        function walk(list, parentItem, path) {
          for (var i4 = 0; i4 < list.items.length; i4++) {
            var it4 = list.items[i4];
            if (n === flatIdx) {
              hit = {
                parentList: list,
                index: i4,
                parentItem: parentItem,
                path: path.concat([i4]),
                item: it4,
              };
              return true;
            }
            n++;
            if (it4.list && walk(it4.list, it4, path.concat([i4]))) return true;
          }
          return false;
        }
        walk(rootList, null, []);
        return hit;
      }

      /**
       * ★ 2026-10-23（task-80）：用**树路径**定位当前项，两种来源按优先级取：
       *
       * ① **首选** `EH.listPath` —— 由 `mapper.domToAst()` 的 `resolveListItem()`
       *    按 DOM 真实父子关系递归解析得出（如 `[0,1]`）。这是权威层级坐标，
       *    **不需要任何扁平索引反查**，因此天然不受「domToAst 扁平/树口径不一致」影响。
       * ② **兜底** `flatLiToTreePath(block, EH.listItemIndex)` —— 旧路径，保留给
       *    `listPath` 缺失的场合（如旧缓存光标、非列表 block 的边缘态）。
       *
       * 两者都返回同一形状 `{parentList,index,parentItem,item}`，下游逻辑共用。
       */
      function pathToTreeHit(rootList, listPath) {
        if (!listPath || !listPath.length) return null;
        var list2 = rootList;
        var parentItem = null;
        for (var d = 0; d < listPath.length; d++) {
          var ii = listPath[d];
          if (!list2 || !list2.items || ii < 0 || ii >= list2.items.length) return null;
          var it5 = list2.items[ii];
          var isLast = (d === listPath.length - 1);
          if (isLast) {
            return { parentList: list2, index: ii, parentItem: parentItem, item: it5 };
          }
          if (!it5.list) return null;
          parentItem = it5;
          list2 = it5.list;
        }
        return null;
      }

      var EH = (typeof window.MemoriaEditHandler !== "undefined") ? window.MemoriaEditHandler : null;
      var found = null;
      if (EH && EH.listPath) {
        found = pathToTreeHit(block, EH.listPath);
      }
      if (!found) {
        var flatIdx = (EH && EH.listItemIndex != null) ? EH.listItemIndex : 0;
        found = flatLiToTreePath(block, flatIdx);
      }
      if (!found) return false;
      var curItem = found.item;
      var curList = found.parentList;
      var curListParentItem = found.parentItem;

      if (dir > 0) {
        // ── 降级：挂到同级前一项的子列表 ──
        if (found.index === 0) return false;          // 首项无处可降
        var prevSib = found.parentList.items[found.index - 1];
        if (!prevSib) return false;
        if (!prevSib.list) {
          prevSib.list = A.list(curList.ordered, []);
        }
        found.parentList.items.splice(found.index, 1);
        // 缩进：父项缩进 + 2 空格（清空 srcLine 后由 source-gen 按 fallbackIndent 推算；
        // 这里显式给一个，保证中间态也正确）
        curItem.indent = (prevSib.indent != null ? prevSib.indent : "") + "  ";
        prevSib.list.items.push(curItem);
      } else {
        // ── 升级：从当前列表移出，插到父项之后（同级） ──
        if (!curListParentItem) return false;         // 已在顶层
        /**
         * ★ 2026-10-23（task-80）：这里原先调 `findItem(block, curListParentItem, null)`，
         *   但 **`findItem` 在整个 app.js 里从未定义过**（HEAD 与工作区都只有这一处调用）
         *   ⇒ 运行时抛 ReferenceError ⇒ 被 keydown 的 try/catch 吞成 `did=false`
         *   ⇒ **升级（Shift+Tab）永远静默失效**。
         *
         *   改法：父项在**父层列表**中的下标 = 当前路径去掉最后一段后，
         *   再走一遍同一个 `pathToTreeHit()` —— 已经有权威路径，不需要再按对象引用搜索。
         *   （`found.parentItem` 来自路径解析；`grand.parentList` 即 `curList` 的归属列表。）
         */
        var parentPath = (EH && EH.listPath && EH.listPath.length > 1)
          ? EH.listPath.slice(0, EH.listPath.length - 1) : null;
        var grand = parentPath ? pathToTreeHit(block, parentPath) : null;
        if (!grand) return false;
        found.parentList.items.splice(found.index, 1);
        curItem.indent = curListParentItem.indent != null ? curListParentItem.indent : "";
        grand.parentList.items.splice(grand.index + 1, 0, curItem);
        // 子列表空了就摘掉，避免残留空 <ul>
        if (curList.items.length === 0 && curListParentItem) delete curListParentItem.list;
      }

      _invalidateListItemLines(block);

      var newSrcLines = G.generateBlock(block).split("\n");
      if (!newSrcLines.length) return false;
      // 光标落在**顶层列表**的首项开头（保守：结构变了，精确落点由后续点击决定）
      var newCursor = {
        blockIndex: cursor.blockIndex,
        nodePath: [0],
        offset: 0,
      };
      commitRange(range.startLine, range.endLine, newSrcLines, newCursor, preCursor, "indent");
      return true;
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
      flushRepaint: _flushBlockRepaint,   // AG103：把"停手才渲"的那一块立刻渲掉（切走/暂存预览前要调，别把没归一的 DOM 存进缓存）
      backspace: backspace,
      deleteForward: deleteForward,
      splitParagraph: splitParagraph,
      revertBlock: revertBlock,
      applyStyle: applyStyle,
      getSelectionStyles: getSelectionStyles,
      deleteSelection: deleteSelection,
      // stage5（task-83）：粘贴 = 替换选区（单行内联 / 多行三段式；一次 commitRange ⇒ 单撤销）
      replaceSelectionWithText: replaceSelectionWithText,
      // 0.4.7 任务 4 / N4：多级列表升降级（dir=+1 降级 / -1 升级）
      indentListLevel: indentListLevel,
      beginUndoGroup: beginUndoGroup,
      endUndoGroup: endUndoGroup,
      // task-138：多行粘贴等待"拆段 + 异步光标恢复"完成（否则下一行读到旧 cursorAST）
      whenStructuralIdle: function () { return _pendingStructural || Promise.resolve(); },
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
      // 编辑模式关闭（只读）：源码区不弹创建链接/知识点菜单
      if (window.MemoriaEditHandler && !window.MemoriaEditHandler.editMode) return;
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
      // 编辑模式关闭（只读）：不弹任何编辑类右键菜单（粘贴/插入图片/选区编辑/图片操作）。
      // 原生菜单已由全局 handler 屏蔽，此处直接 return 即可。
      if (preview.contentEditable !== "true") return;
      // 图片右键：替换/删除菜单已随图片子系统迁至 image-tools.js（init 绑定），此处放行交由其处理
      if (e.target.closest("img.-preview-image")) return;
      if (e.target.closest(".memoria-link, .-wikilink, a[href]")) return;
      if (!state.currentPath) return;
      const info = getSelectionInContainer(preview);
      if (!info) {
        // 无选中文本（光标折叠）→ 提供「粘贴」「插入图片」
        if (!syncPreviewCursorForPaste()) return;
        const insLine = window.MemoriaImageTools?.previewCursorSourceLine?.() || 0;
        MemoriaLinkContextMenu.showForCursor(e, {
          onPaste: pasteAtCursor,
          onInsertImage: () => window.MemoriaImageTools?.startInsertImage?.(insLine || undefined),
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
        // 右键"高光/字体颜色"：不关闭当前右键菜单，在其旁侧展开工具栏同款预设色下拉
        // （右侧优先，放不下放左侧，再不行放菜单下方），选色应用到右键时捕获的选区
        onPickStyle: (fmt, x, y) => {
          closeAllDropdowns();
          const ddBtn = document.querySelector(
            `.-fmt-dropdown > .-fmt-btn[data-fmt="${fmt}"]`
          );
          const dd = ddBtn ? ddBtn.closest(".-fmt-dropdown") : null;
          if (!dd) {
            applyFormat(fmt, fmt === "highlight" ? "yellow" : "red");
            return;
          }
          dd.classList.add("open");
          const menu = dd.querySelector(".-fmt-dropdown-menu");
          if (!menu) return;
          const mw = menu.offsetWidth;
          const mh = menu.offsetHeight;
          const ctx = document.getElementById("-link-context-menu");
          let left = x;
          let top = y;
          if (ctx) {
            const cr = ctx.getBoundingClientRect();
            top = Math.max(4, cr.top);
            const rightX = cr.right + 6;
            if (rightX + mw <= window.innerWidth - 4) {
              left = rightX;
            } else {
              const leftX = cr.left - mw - 6;
              if (leftX >= 4) {
                left = leftX;
              } else {
                left = Math.max(4, cr.left);
                top = cr.bottom + 6;
              }
            }
          }
          if (top + mh > window.innerHeight) {
            if (ctx) {
              const cr = ctx.getBoundingClientRect();
              top = Math.max(4, cr.top - mh - 4);
            } else {
              top = Math.max(4, y - mh - 4);
            }
          }
          menu.style.position = "fixed";
          menu.style.left = `${Math.max(4, left)}px`;
          menu.style.right = "auto";
          menu.style.top = `${Math.max(4, top)}px`;
          menu.style.bottom = "auto";
          menu.style.zIndex = "100000";
        },
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

  /** 把给定文本插入预览区光标处（多行逐行拆分、整体作为一个撤销单元）。
   *  由 Ctrl+V（paste 事件）与右键「粘贴」共用。
   *
   *  task-138 修复（真机 10/10 丢行）：拆段后的光标恢复在 `repaintPreview().then(...)`
   *  异步里执行；原实现**同步**继续插下一行 ⇒ 读到拆段前的旧 cursorAST，
   *  `insertText(lines[i])` 返回 false 且结果被丢弃 ⇒ 用户以为粘贴成功、实际只留第 1 行。
   *  现在每拆一段都 `await whenStructuralIdle()` 再插下一行；任何一行失败都走
   *  `setStatusError` + `console.error`（L6：失败必须可见，绝不静默吞掉）。 */
  async function pasteTextAtCursor(text) {
    const EditSync = window.MemoriaEditSync;
    if (!EditSync || typeof EditSync.insertText !== "function") {
      setStatus(T("cfg.clip.editorNotReady"));
      return false;
    }

    // ★ stage5（task-83）：右键「粘贴」时预览区若有非折叠选区 ⇒ 同样按「替换选区」处理
    //   （与 Ctrl+V 路径同一实现 ⇒ 行为一致，不出现两个入口两套语义）。
    const selP = window.getSelection();
    const pvP = $("#preview");
    if (selP && !selP.isCollapsed && selP.rangeCount && pvP) {
      const rP = selP.getRangeAt(0);
      if (pvP.contains(rP.startContainer) && pvP.contains(rP.endContainer)) {
        const okP = (typeof EditSync.replaceSelectionWithText === "function")
          ? EditSync.replaceSelectionWithText(rP.cloneRange(), text) : false;
        if (!okP) { setStatusError(T("cfg.clip.pasteReplaceFail"), T("cfg.clip.selFailDetail")); return false; }
        setStatus(T("cfg.clip.pasteReplaced"));
        return true;
      }
    }

    const lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    const waitStructural = async () => {
      if (typeof EditSync.whenStructuralIdle !== "function") return;
      try { await EditSync.whenStructuralIdle(); } catch (_) { /* 重渲失败由下方"失败可见"兜底 */ }
    };
    // 作为单个撤销单元：分组包裹，子操作（insertText/splitParagraph）不各自入栈
    if (typeof EditSync.beginUndoGroup === "function") EditSync.beginUndoGroup();
    let failedAt = -1;
    try {
      if (!EditSync.insertText(lines[0])) {
        failedAt = 0;
      } else {
        for (let i = 1; i < lines.length; i++) {
          if (!EditSync.splitParagraph()) { failedAt = i; break; }
          // ★ 关键修复：等拆段的异步光标恢复完成，再插下一行
          await waitStructural();
          if (!lines[i]) continue;             // 空行：拆段已产生空段落
          if (!EditSync.insertText(lines[i])) { failedAt = i; break; }
        }
      }
    } finally {
      if (typeof EditSync.endUndoGroup === "function") EditSync.endUndoGroup();
    }
    if (failedAt >= 0) {
      // L6：失败必须可见 —— 不静默吞掉，也不谎报"已粘贴"
      console.error("[Memoria] 多行粘贴在第 " + (failedAt + 1) + "/" + lines.length +
        " 行失败（已插入 " + failedAt + " 行），文档可能不完整");
      setStatusError(T("cfg.clip.pasteFail"), String(failedAt + 1) + "/" + String(lines.length));
      return false;
    }
    setStatus(T("cfg.clip.pasted"));
    return true;
  }

  /** 读取剪贴板并在光标位置粘贴（右键菜单入口；经 clipboard API，WebView2 会询问权限） */
  async function pasteAtCursor() {
    let text = "";
    try {
      text = (await readClipboardText()) || "";
    } catch (_) {
      text = "";
    }
    if (!text) {
      setStatus(T("cfg.clip.empty"));
      return;
    }
    pasteTextAtCursor(text);
  }

  /* ── E25：Ctrl+V 粘贴图片（扩展既有 .memoria/images/ 图片链，不另造第二条）──────
     链路：剪贴板 File/Blob → (前端) base64 → RPC `import_image_base64`
           → `DocumentService._import_image_bytes`（与本地文件导入共用：白名单 + MD5 去重 +
             重名追加 + relPath 口径）→ 插入 `![alt](<rel>)` 独占行（并入源码撤销栈）。
     纯文本粘贴路径**完全不动**：只有剪贴板里确有图片文件时才 preventDefault。 */

  /** 从 ClipboardEvent 取图片 File（files 优先，items 兜底）。无图片返回 []。 */
  function clipboardImageFiles(e) {
    const clip = e && (e.clipboardData || window.clipboardData);
    if (!clip) return [];
    const out = [];
    const seen = new Set();
    const add = (f) => {
      if (!f) return;
      const type = String(f.type || "").toLowerCase();
      if (type.indexOf("image/") !== 0) return;   // 只认图片；文本/文件走原路径
      if (seen.has(f)) return;
      seen.add(f);
      out.push(f);
    };
    const files = clip.files;
    if (files && files.length) {
      for (let i = 0; i < files.length; i++) add(files[i]);
    }
    if (!out.length) {
      const items = clip.items;
      if (items && items.length) {
        for (let i = 0; i < items.length; i++) {
          const it = items[i];
          if (it && it.kind === "file") add(it.getAsFile());
        }
      }
    }
    return out;
  }

  /** File/Blob → data URL（后端同时接受裸 base64 与 data URL，用它补扩展名）。 */
  function _clipboardFileDataURL(file) {
    return new Promise((resolve, reject) => {
      try {
        const fr = new FileReader();
        fr.onload = () => resolve(String(fr.result || ""));
        fr.onerror = () => reject(fr.error || new Error("read failed"));
        fr.readAsDataURL(file);
      } catch (err) {
        reject(err);
      }
    });
  }

  /**
   * 在源码编辑器插入一行独占 Markdown（图片必须独占一行才渲染），光标落到行尾。
   * 与 `image-tools.js insertSourceLine` 同一套机制（独占行 + 光标落点 + 走源码撤销栈）；
   * 该函数未在 MemoriaImageTools 门面导出，故此处按同一契约实现一份，供粘贴路径复用。
   * @returns {boolean} false = 没有源码编辑器（调用方须显式报错）
   */
  function _insertExclusiveSourceLine(text, lineNum) {
    const editor = $("#editor");
    if (!editor) return false;
    const sel = window.getSelection();
    let baseLine = null;
    if (sel && sel.rangeCount && sel.anchorNode) {
      baseLine = closestLineEl(sel.anchorNode);
      if (!editor.contains(baseLine)) baseLine = null;
    }
    if (!baseLine && lineNum > 0) baseLine = document.getElementById("line-" + lineNum);
    if (!baseLine) {
      // 预览区粘贴：光标锚点在预览 DOM 上，用既有"预览光标所在源码行"定位
      const pLine = window.MemoriaImageTools?.previewCursorSourceLine?.() || 0;
      if (pLine > 0) baseLine = document.getElementById("line-" + pLine);
    }
    if (!baseLine) {
      const all = editor.querySelectorAll(".-line");
      baseLine = all[all.length - 1] || null;
    }
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
    // 与既有插入一致：关闭编辑模式时新增行保持只读
    content.contentEditable = !window.MemoriaEditHandler || window.MemoriaEditHandler.editMode ? "true" : "false";
    content.spellcheck = false;
    content.tabIndex = -1;
    content.textContent = text;
    newLineEl.appendChild(lineno);
    newLineEl.appendChild(content);
    if (baseLine) baseLine.after(newLineEl);
    else editor.appendChild(newLineEl);
    renumberSourceLines();
    // 光标落到插入点之后（行尾）
    const node = content.firstChild;
    const r = document.createRange();
    if (node) r.setStart(node, node.nodeType === Node.TEXT_NODE ? node.textContent.length : 0);
    else r.setStart(content, 0);
    r.collapse(true);
    if (sel) {
      sel.removeAllRanges();
      sel.addRange(r);
    }
    // E26：插入的图片行若在视口外 ⇒ 带进视野（用户刚手动滚过则不动）
    const pane = $("#editor-pane");
    if (pane) _keepCaretVisible(pane, r, newLineEl);
    scheduleRenderSync();
    markDirty();
    return true;
  }

  /**
   * 粘贴图片主流程：逐张入库（单张失败不影响其它）→ 按顺序插入独占行 → 一个撤销单元。
   * 失败必须显式显示（绝不假装成功）。
   * @param {File[]} files 剪贴板里的图片文件（已按剪贴板顺序）
   * @param {number} lineNum 目标源码行（0 = 跟随当前光标）
   */
  async function insertClipboardImages(files, lineNum) {
    if (!state.kbPath) {
      setStatusError(T("app.openKbFirst"));
      return;
    }
    if (!state.currentPath) {
      setStatusError(T("img.insert.openDocFirst"));
      return;
    }
    const imported = [];
    const failures = [];
    for (const f of files) {
      try {
        const dataUrl = await _clipboardFileDataURL(f);
        const res = await call("import_image_base64", f.name || "image.png", dataUrl);
        if (res && res.status === "ok" && res.relPath) imported.push(res);
        else failures.push((res && res.message) || T("common.unknownError"));
      } catch (err) {
        failures.push((err && err.message) || String(err));
      }
    }
    if (imported.length) {
      // 整次粘贴 = 一个撤销单元（与源码区多行文本粘贴同口径）
      _srcPushBefore();
      _srcCoalesceAt = 0;
      let base = lineNum || 0;
      for (const r of imported) {
        const alt = String(r.name || "").replace(/\.[^.]+$/, "");
        // 尖括号包裹：文件名可能含中文/空格（裸 URL 会被 marked 在空格处截断）
        if (!_insertExclusiveSourceLine("![" + alt + "](<" + r.relPath + ">)", base)) {
          failures.push(T("img.insert.noEditor"));
          break;
        }
        base = 0;   // 后续图片顺延到上一张插入行之后（光标已在那里）
      }
      _srcAfterEdit();
      setStatus(T("img.insert.stored"), imported[imported.length - 1].relPath);
    }
    if (failures.length) {
      // 有失败就必须看得见（部分成功也照实报错）
      setStatusError(T("img.insert.importFailed"), failures.join("；"));
    }
  }

  /** 预览区 Ctrl+V：走原生 paste 事件读 clipboardData（**不触发 WebView2 剪贴板权限询问**），
   *  并与源码区（见编辑器 paste 监听）保持同一模式：拦截原生粘贴、改由 AST 管线插入。 */
  function bindPreviewPaste() {
    const preview = document.getElementById("preview");
    if (!preview || preview._memoriaPasteBound) return;
    preview._memoriaPasteBound = true;
    preview.addEventListener("paste", (e) => {
      if (window.MemoriaEditHandler && !window.MemoriaEditHandler.editMode) return;
      if (state.viewMode === "source") return;
      const clip = e.clipboardData || window.clipboardData;
      if (!clip) return;
      // E25：剪贴板里有图片 ⇒ 走图片链（否则会被下面的 text/plain 分支吞掉：纯图时
      // text/plain 是空串，原逻辑 preventDefault 后插入了空文本，图片静默丢失）
      const imgs = clipboardImageFiles(e);
      if (imgs.length) {
        e.preventDefault();
        const insLine = window.MemoriaImageTools?.previewCursorSourceLine?.() || 0;
        insertClipboardImages(imgs, insLine);
        return;
      }
      const raw = clip.getData("text/plain");
      if (raw === null || raw === undefined) return;
      // ★ stage5（task-83）：选区非折叠 ⇒ 粘贴 = **替换选区**（含跨块/同块跨段）。
      //   必须先 preventDefault 再走 AST 管线：否则浏览器原生粘贴"只改 DOM 不改源码"
      //   （E30 同族：下一次重渲回魂 / 源码与画面不一致）。失败给可见提示，绝不静默。
      const selPaste = window.getSelection();
      const rngPaste = selPaste && selPaste.rangeCount ? selPaste.getRangeAt(0) : null;
      if (rngPaste && !rngPaste.collapsed &&
          preview.contains(rngPaste.startContainer) && preview.contains(rngPaste.endContainer)) {
        e.preventDefault();
        const ES = window.MemoriaEditSync;
        const okReplace = (ES && typeof ES.replaceSelectionWithText === "function")
          ? ES.replaceSelectionWithText(rngPaste.cloneRange(), raw) : false;
        if (!okReplace) {
          setStatusError(T("cfg.clip.pasteReplaceFail"), T("cfg.clip.selFailDetail"));
          return;
        }
        setStatus(T("cfg.clip.pasteReplaced"));
        return;
      }
      // 与右键「粘贴」一致：先从当前选区解析出 AST 光标锚点。
      // 解析不到（光标不在预览区 / 无法映射）则**不拦截**，退回浏览器原生粘贴——宁可有原生行为，也不吞掉用户的粘贴。
      if (!syncPreviewCursorForPaste()) return;
      e.preventDefault();
      pasteTextAtCursor(raw);
    });
  }

  /* ── Format toolbar ── */
  let _pendingPreviewRange = null;

  /** 在 mousedown 阶段捕获预览区非折叠选区（点击按钮会导致 contenteditable 失焦）。
   *  只在拿到有效选区时才写入 _pendingPreviewRange，绝不把已有捕获清掉——
   *  否则第一次点击后失焦，第二次点击会因 pending 丢失而误入笔刷模式。 */
  function capturePreviewSelection() {
    const sel = window.getSelection();
    const preview = $("#preview");
    if (!sel || !sel.rangeCount || !preview) return;
    const range = sel.getRangeAt(0);
    if (range.collapsed) return;
    if (!preview.contains(range.startContainer) || !preview.contains(range.endContainer)) return;
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

  // ── 颜色下拉 hover 实时预览：临时给选区文本包色 span，不改源码/AST，移出即恢复 ──
  // 稳定性设计：不依赖"实时选区在我们 split/unwrap 后仍不变"这一脆弱前提。
  // 捕获一次锚点 =（所在 .-src-block + 块内字符偏移）。hover 期间我们只增删文本节点
  // 缝（span），块元素与其文本长度恒定，故每次 hover 都从锚点重建出同一段 Range。
  // 每次清理后把实时选区还原到锚点，保证点击应用时拿到的仍是原始那段文字。
  let _tintSpans = [];
  let _tintAnchor = null; // { startBlock, startChar, endBlock, endChar }

  /** 找到 node 所在的渲染块（.-src-block）；找不到则退回 #preview */
  function _tintBlockOf(node) {
    let el = node && node.nodeType === 1 ? node : (node && node.parentElement);
    while (el && el !== document.body) {
      if (el.classList && el.classList.contains("-src-block")) return el;
      el = el.parentElement;
    }
    return null;
  }

  /** 边界点 (container, offset) 在其所在块文本中的字符位置（块文本 start → 边界 的 toString 长度） */
  function _tintCharOffsetOf(blockEl, container, offset) {
    if (!blockEl || !container || !blockEl.contains(container)) return -1;
    const r = document.createRange();
    r.selectNodeContents(blockEl);
    try {
      r.setStart(blockEl, 0);
      r.setEnd(container, offset);
    } catch (_) {
      return -1;
    }
    return r.toString().length;
  }

  /** 按块内字符位置反查 (文本节点, 节点内偏移)；位置恰在节点尾时锚在该节点尾 */
  function _tintTextAtOffset(blockEl, targetChar) {
    const walker = document.createTreeWalker(blockEl, NodeFilter.SHOW_TEXT);
    let acc = 0;
    let last = null;
    let lastLen = 0;
    while (walker.nextNode()) {
      const n = walker.currentNode;
      const len = n.data.length;
      last = n;
      lastLen = len;
      if (targetChar < acc + len) return { node: n, off: targetChar - acc };
      if (targetChar === acc + len) return { node: n, off: len };
      acc += len;
    }
    if (targetChar === acc && last) return { node: last, off: lastLen };
    return null;
  }

  /** 从当前实时/捕获选区建立锚点（只在尚未建锚且 DOM 未被我方改动时调用） */
  function _captureTintAnchor() {
    _tintAnchor = null;
    const preview = $("#preview");
    if (!preview) return null;
    const r = getPreviewSelectionRange();
    if (!r || r.collapsed) return null;
    const sb = _tintBlockOf(r.startContainer) || preview;
    const eb = _tintBlockOf(r.endContainer) || preview;
    const sc = _tintCharOffsetOf(sb, r.startContainer, r.startOffset);
    const ec = _tintCharOffsetOf(eb, r.endContainer, r.endOffset);
    if (sc < 0 || ec < 0) return null;
    _tintAnchor = { startBlock: sb, startChar: sc, endBlock: eb, endChar: ec };
    return _tintAnchor;
  }

  /** 按锚点重建当前 DOM 上的 Range（块内只可能多出相邻文本节点缝，不影响字符位置） */
  function _tintAnchorRange() {
    const a = _tintAnchor;
    if (!a) return null;
    if (!a.startBlock.isConnected || !a.endBlock.isConnected) { _tintAnchor = null; return null; }
    const st = _tintTextAtOffset(a.startBlock, a.startChar);
    const en = _tintTextAtOffset(a.endBlock, a.endChar);
    if (!st || !en) return null;
    const r = document.createRange();
    try {
      r.setStart(st.node, st.off);
      r.setEnd(en.node, en.off);
    } catch (_) {
      return null;
    }
    if (r.collapsed) return null;
    return r;
  }

  /** 把实时选区还原为锚点对应的文字（removeAllRanges 后立即 addRange，选区不消失） */
  function _restoreTintSelection() {
    const r = _tintAnchorRange();
    if (!r) return;
    const sel = window.getSelection();
    if (!sel) return;
    try {
      sel.removeAllRanges();
      sel.addRange(r);
    } catch (_) { /* noop */ }
  }

  function _dropTintAnchor() {
    _tintAnchor = null;
  }

  function _clearColorTint() {
    const hadSpans = _tintSpans.length > 0;
    for (const el of _tintSpans) {
      const parent = el.parentNode;
      if (parent) {
        while (el.firstChild) parent.insertBefore(el.firstChild, el);
        parent.removeChild(el);
      }
    }
    _tintSpans = [];
    // 不做 normalize：合并相邻文本节点会让浏览器把 range 端点挪到元素级（实测选区漂移）。
    // 保留拆分缝无害（相邻文本节点渲染/映射与合并前等价），且端点始终留在文本节点内。
    const preview = $("#preview");
    if (preview) preview.classList.remove("-color-tinting");
    // 我方刚拆过 DOM 时，把实时选区还原到锚点，避免漂移影响下一次 hover/点击应用
    if (hadSpans && _tintAnchor) _restoreTintSelection();
  }

  function _applyColorTint(colorCss, applyAs = "backgroundColor") {
    _clearColorTint();
    const preview = $("#preview");
    if (!preview) return;
    if (!_tintAnchor) _captureTintAnchor();
    const r = _tintAnchorRange();
    if (!r) return;
    const root =
      r.commonAncestorContainer.nodeType === 1
        ? r.commonAncestorContainer
        : r.commonAncestorContainer.parentNode;
    if (!root || !preview.contains(root)) return;
    preview.classList.add("-color-tinting");
    // 先收集受影响的文本节点与偏移（处理过程中会 splitText，range 会失效，须先取数）
    const jobs = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!r.intersectsNode(node) || !node.data) continue;
      let s = 0;
      let e = node.length;
      if (node === r.startContainer) s = r.startOffset;
      if (node === r.endContainer) e = r.endOffset;
      if (e <= s) continue;
      jobs.push({ node, s, e });
    }
    const spans = [];
    for (const j of jobs) {
      // splitText 语义：mid = [s, len)，再切出 seg=[e, len)，mid 即选区段 [s, e)。
      // 只在必要时切分，避免 splitText(0)/splitText(len) 产生空文本节点——
      // 空节点会把 range 端点顶到元素级，导致第二次 hover 起选区漂移
      let mid = j.node;
      if (j.s > 0) mid = j.node.splitText(j.s);
      const wrap = document.createElement("span");
      wrap.style[applyAs] = colorCss;
      if (j.e < j.node.length) {
        const seg = mid.splitText(j.e - j.s);
        seg.parentNode.insertBefore(wrap, seg);
      } else {
        mid.parentNode.insertBefore(wrap, mid.nextSibling);
      }
      wrap.appendChild(mid);
      spans.push(wrap);
    }
    _tintSpans = spans;
    // 包完 span 后立即把实时选区还原到锚点文字（其边界此刻可能悬在临时 span 上）
    if (spans.length) _restoreTintSelection();
    console.log("[TINT] spans=" + spans.length + " texts=" +
      spans.map((sp) => JSON.stringify(sp.textContent)).join(","));
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
    // 2026-10-20 task-19：无选区 / 选区折叠 / 选区不在预览内 ⇒ 没有任何原子块可高亮。
    // 此时**只需清掉上一轮残留**，不必遍历全部 `.-math`（scale-5k 上 270 个元素逐个 toggle
    // ⇒ 每键 148 次空操作；M1=151 而 M2=5 的 30 倍差就是它）。真机口径见
    // `artifacts/agent/verify/typing-dom-write-baseline.md`。
    // 注意：**只跳不清会留残影** —— 折叠前被涂亮的公式必须在这里摘掉 `-sel-covered`。
    if (!r) {
      for (let k = 0; k < atoms.length; k++) {
        if (atoms[k].classList.contains("-sel-covered")) atoms[k].classList.toggle("-sel-covered", false);
      }
      log("MAP", "selHighlight sel=" + domDesc + " mathTotal=" + atoms.length + " covered=0 (no-selection early-exit)");
      return;
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
      // 2026-10-20 task-19：**仅在状态真变时写**（原来无条件 toggle ⇒ 有选区但一个都没命中时
      // 仍要付 atoms.length 次空操作）。`contains` 读的是同一次 StyleDeclaration，
      // 不产生写；命中集合的判定逻辑（上面 c1/c2 与 startContainer/endContainer 兜底）**一字未动**。
      const hasCovered = el.classList.contains("-sel-covered");
      if (isCovered !== hasCovered) el.classList.toggle("-sel-covered", isCovered);
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
    // 全局 mousedown（捕获阶段）维护预览区选区捕获：
    // - 按在预览区外（工具栏/右键菜单/色板下拉）：捕获实时选区，防止按钮点击后 contenteditable 失焦丢失
    // - 按在预览区内：用户将新建选区/光标，作废此前捕获
    if (!window.__previewSelDocGuard) {
      window.__previewSelDocGuard = 1;
      document.addEventListener(
        "mousedown",
        (e) => {
          const preview = $("#preview");
          if (!preview) return;
          if (preview.contains(e.target)) {
            if (_pendingPreviewRange) _pendingPreviewRange = null;
            return;
          }
          capturePreviewSelection();
        },
        true
      );
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
      // hover 实时预览：仅临时给选区文本着色（不改源码/AST），移出色块即恢复
      sw.addEventListener("mouseenter", () => {
        if (hasExistingSelection()) {
          _applyColorTint(getComputedStyle(sw).backgroundColor);
        }
      });
      sw.addEventListener("mouseleave", _clearColorTint);
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
      // hover 实时预览：仅临时给选区文字染色（不改源码/AST），移出色块即恢复
      sw.addEventListener("mouseenter", () => {
        if (hasExistingSelection()) {
          _applyColorTint(getComputedStyle(sw).backgroundColor, "color");
        }
      });
      sw.addEventListener("mouseleave", _clearColorTint);
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
    if (!window.__previewResizeBound) {
      window.__previewResizeBound = 1;
      window.addEventListener("resize", () => {
        document.querySelectorAll(".-fmt-dropdown.open").forEach((dd) => positionDropdown(dd));
      });
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
      '  <div class="-cp-title">' + T("color.customTitle") + "</div>" +
      '  <div class="-cp-preview"></div>' +
      '  <div class="-cp-sv"><div class="-cp-cursor"></div></div>' +
      '  <input type="range" class="-cp-hue" min="0" max="360" step="1" value="0">' +
      '  <div class="-cp-presets"></div>' +
      '  <div class="-cp-row">' +
      '    <input type="text" class="-cp-hex" value="#ff0000" spellcheck="false" maxlength="7">' +
      '    <button type="button" class="-cp-cancel">' + T("common.cancel") + "</button>" +
      '    <button type="button" class="-cp-ok">' + T("common.ok") + "</button>" +
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
    head.innerHTML = '<span class="-ctx-head">' + T("color.ctxHead", { hex: hex }) + "</span>";
    menu.appendChild(head);

    const div = document.createElement("div");
    div.className = "-ctx-divider";
    menu.appendChild(div);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "-ctx-item danger";
    del.setAttribute("role", "menuitem");
    del.textContent = T("color.ctxDelete");
    del.addEventListener("click", (ev) => {
      ev.stopPropagation();
      hideSwatchCtxMenu();
      saveCustomColors(kind, getCustomColors(kind).filter((c) => c !== hex));
      renderCustomSwatches(kind);
      setStatus(T("color.deleted", { hex: hex }));
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
      btn.title = T("color.swatchTitle", { hex: hex });
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
    openColorPicker(T("color.customTitle"), (hex) => {
      if (!hex) return; // 取消
      const colors = getCustomColors(kind);
      if (colors.indexOf(hex) !== -1) {
        setStatus(T("color.inPalette", { hex: hex }));
        armBrush(kind === "highlight" ? "highlight" : "fontcolor", hex);
        return;
      }
      colors.push(hex);
      saveCustomColors(kind, colors);
      renderCustomSwatches(kind);
      setStatus(T("color.added", { hex: hex }));
      // 添加成功即进入画笔模式，拖动即可涂抹新颜色
      armBrush(kind === "highlight" ? "highlight" : "fontcolor", hex);
    });
  }

  function closeAllDropdowns() {
    // 收起下拉时一并清除 hover 预览的临时着色，并丢弃选区锚点（下拉已关，旧锚点不再适用）
    _clearColorTint();
    _dropTintAnchor();
    document.querySelectorAll(".-fmt-dropdown.open").forEach((d) => d.classList.remove("open"));
  }

  // ═══════════════════════════════════════════════════════════════
  //  画笔模式：点击颜色后鼠标变画笔，在预览/源码区拖动选择文字即应用目标样式
  // ═══════════════════════════════════════════════════════════════
  let _brush = null; // 多槽位画笔：{ bold: bool, italic: bool, highlight: color|null, fontcolor: color|null }

  /** 画笔样式的中文名 */
  function _brushLabel(fmt) {
    return fmt === "highlight" ? T("brush.style.highlight") :
      fmt === "fontcolor" ? T("brush.style.fontcolor") :
      fmt === "bold" ? T("brush.style.bold") : T("brush.style.italic");
  }

  /** 鼠标目标对应的样式类型（B/I/H/色 两个色板按钮/对应色块，含自定义色块），否则 null */
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

  /**
   * **编辑态闸门**（2026-10-20 · S2 修复）：样式写入只允许在「编辑模式开启」时发生。
   * 旧版 `applyFormat` / `_brushOnMouseUp` 都不查 `EH.editMode` ⇒ 只读态下预览区
   * `contentEditable=false` 但浏览器仍能产生选区，于是画笔/右键/工具栏还能改源码（危险）。
   * @returns {boolean} true=允许应用样式
   */
  function _styleEditAllowed() {
    var EH = window.MemoriaEditHandler;
    return !!(EH && EH.editMode);
  }

  /** 只读态拒绝应用样式时的**可见**提示（不静默） */
  function _notifyStyleReadonly() {
    setStatus(T("cfg.style.readonly"));
  }

  /**
   * **画笔生命周期收尾**（2026-10-20 · S1 修复）：把画笔武装整体清掉。
   * 旧版 `_brush` 只在「Esc」与「右键取消最后一个槽位」时清理 ⇒ 切文件后画笔仍武装，
   * 新文件里第一次拖动就把样式涂上去（跨文件误写）。这里统一收口，挂在四类入口：
   *   ① 切文件（`openFile` 落定后）② 编辑模式关闭（`EH.toggleEditMode` 回调）
   *   ③ 进入块编辑（`enterBlockEditMode`）/ 块编辑因重渲染失效
   *   ④ 关闭知识库
   * @returns {boolean} 是否真的清掉了武装
   */
  function _brushDisarmAll() {
    if (!_brush) return false;
    _brush = null;
    if (document.body) document.body.classList.remove("-brush-active");
    document.querySelectorAll(".-fmt-btn.brush-armed").forEach(function (b) { b.classList.remove("brush-armed"); });
    try { _clearColorTint(); } catch (_) { /* 预览区/工具栏此刻可能还没建好 */ }
    try { _dropTintAnchor(); } catch (_) { /* 同上 */ }
    try { updateFormatToolbarState(); } catch (_) { /* 工具栏此刻可能还没建好 */ }
    return true;
  }

  /** 供 edit-handler.js / image-tools.js 等其它模块在"退出可编辑语境"时调用（S1 收尾的公共入口） */
  window.MemoriaStyleBrush = window.MemoriaStyleBrush || {};
  window.MemoriaStyleBrush.disarm = _brushDisarmAll;
  window.MemoriaStyleBrush.isAllowed = _styleEditAllowed;

  /** 进入画笔模式：选中（或切换）某个样式的槽位，其余已选样式保留 */
  function armBrush(fmt, color) {
    // 只读态不武装画笔（否则光标变画笔却涂不上，等于误导）
    if (!_styleEditAllowed()) { _notifyStyleReadonly(); return; }
    if (!_brush) _brush = { bold: false, italic: false, highlight: null, fontcolor: null };
    if (fmt === "bold") _brush.bold = true;
    else if (fmt === "italic") _brush.italic = true;
    else if (fmt === "highlight") _brush.highlight = color;
    else if (fmt === "fontcolor") _brush.fontcolor = color;
    closeAllDropdowns();
    document.body.classList.add("-brush-active");
    updateFormatToolbarState();
    setStatus(T("brush.ready"));
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
      setStatus(T("brush.cancelled"));
      return;
    }
    updateFormatToolbarState();
    setStatus(T("brush.cancelPart", { x: _brushLabel(fmt) }));
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
    if (!styles.length) return { ok: false, message: T("brush.noStyle") };
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
    return { ok: applied > 0, message: applied > 0 ? "" : T("brush.applyFail"), applied };
  }

  /** 画笔 mouseup：预览区内拖动结束 → 应用目标样式（保持画笔可连续涂抹）；右键取消由 contextmenu 捕获阶段处理 */
  function _brushOnMouseUp(e) {
    if (!_brush) return;
    if (e.button !== 0) return;
    if (!e.target || !e.target.closest) return;
    // S2：只读态闸门 —— 编辑模式关闭时不应用（并给可见提示），画笔武装同时收掉
    if (!_styleEditAllowed()) {
      _brushDisarmAll();
      _notifyStyleReadonly();
      return;
    }
    // 色块 / 下拉开关 / 添加颜色 / 取色面板 / 右键菜单：交给各自的 click 处理（重新武装或保持）
    if (e.target.closest(".-hl-swatch, .-fc-swatch, .-hl-custom, .-fc-custom, .-fmt-dropdown > .-fmt-btn, .-color-picker-mask, .-context-menu")) return;
    // 工具栏按钮 / 文档区域之外点击：保持画笔（不取消），可继续回来涂抹；
    // 画笔类型切换由各按钮自身的 click（armBrush 覆盖）负责
    if (e.target.closest(".-fmt-btn, .-view-btn, #block-edit-bar, .-kp-toolbar")) return;
    // 笔刷仅作用于预览区：源码编辑器内涂抹不应用样式（笔刷保持武装，可回到预览继续涂）
    if (!e.target.closest("#preview")) return;

    const sel = window.getSelection();
    if (!sel || !sel.rangeCount || sel.getRangeAt(0).collapsed) {
      setStatus(T("brush.standby", { x: _brushListLabel() }));
      return;
    }
    const r = sel.getRangeAt(0);
    const preview = $("#preview");
    const ES = window.MemoriaEditSync;
    if (preview && preview.contains(r.startContainer) && preview.contains(r.endContainer)) {
      if (ES && typeof ES.applyStyle === "function") {
        const res = _applyBrushToRange(ES, r);
        if (res.ok) {
          setStatus(T("brush.applied", { x: _brushListLabel() }));
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
      setStatus(T("cfg.style.singleLineOnly"));
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
    // 点击色块前先移除 hover 预览的临时着色，避免干扰真实应用
    _clearColorTint();
    if (!state.currentPath) return;
    // S2：只读态闸门 —— 编辑模式关闭时一律不写源码（预览 AST 管线与源码兜底两条路都堵住），并给可见提示
    if (!_styleEditAllowed()) {
      _pendingPreviewRange = null;
      _notifyStyleReadonly();
      log("STYLE", "applyFormat BLOCKED: readonly mode fmt=" + formatType);
      return;
    }
    log("STYLE", "applyFormat fmt=" + formatType + " color=" + (color || "null") + " path=" + state.currentPath);

    // 预览区选区优先：走 AST 包裹管线（顶栏按钮点击时选区可能已失焦，用捕获的选区兜底）
    const previewRange = getPreviewSelectionRange();
    if (previewRange && window.MemoriaEditSync && typeof window.MemoriaEditSync.applyStyle === "function") {
      const res = window.MemoriaEditSync.applyStyle(formatType, color, previewRange);
      log("STYLE", "applyFormat res=" + JSON.stringify(res));
      _pendingPreviewRange = null;
      if (res && res.ok) {
        setStatus(T("cfg.style.applied"));
      } else if (res && res.message) {
        setStatus(res.message);
      } else {
        setStatus(T("cfg.style.applyFailed"));
      }
      return;
    }

    // 移除样式（无色）仅支持预览区 AST 管线；源码区暂不支持
    if (formatType === "unhighlight" || formatType === "unfontcolor") {
      setStatus(T("cfg.style.needPreviewSel"));
      return;
    }

    const info = getEditorSelectionInfo();
    if (!info) {
      setStatus(T("cfg.style.needSourceSel"));
      return;
    }
    if (info.startCol === info.endCol) {
      // No selection — insert empty wrapper at cursor
      const res = await call("format_text", state.currentPath, info.line, info.startCol, info.endCol, formatType, color || null);
      if (res.status !== "ok") {
        setStatus(res.message || T("cfg.style.formatFail"));
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
        setStatus(res.message || T("cfg.style.formatFail"));
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
      start_snippet_not_found: T("cfg.kpErr.startSnippet"),
      end_snippet_not_found: T("cfg.kpErr.endSnippet"),
      end_before_start: T("cfg.kpErr.endBeforeStart"),
      missing_snippet: T("cfg.kpErr.missingSnippet"),
    };
    return map[err] || err;
  }

  /** 后端 confirm/update 类错误的本地化：优先按 `code` 取文案（与 cfg.kpSave.* 同源），
   *  缺失 code 时回退后端 message（保持既有行为）。 */
  function kpErrText(res) {
    const codeMap = {
      kp_range_invalid: "cfg.kpSave.invalidRange",
      kp_range_start_empty: "cfg.kpSave.startEmpty",
      kp_range_end_empty: "cfg.kpSave.endEmpty",
    };
    const key = res && res.code ? codeMap[res.code] : null;
    if (key) return T(key, res.params || {});
    return (res && res.message) || T("cfg.confirm.writeFail");
  }

  function onKpClick(kpId, opts = {}) {
    const kp = (state.doc.knowledge_points || []).find((k) => k.id === kpId);
    if (!kp) return;
    window.MemoriaPositionMemory?.remember?.(); if (!opts.skipNav && state.currentPath && window.MemoriaNavStack) {
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
    state.hoveredKpId = null;
    document.querySelectorAll(".-line.kp-hover").forEach((el) => {
      el.classList.remove("in-range", "kp-hover");
    });
    if (state.kpHighlightClearTimer == null && state.kpHighlightFadeTimer == null) {
      clearPreviewHighlights();
    }
  }

  function highlightKpHover(kpId) {
    state.hoveredKpId = kpId || null;
    const kp = (state.doc?.knowledge_points || []).find((k) => k.id === kpId);
    if (window.__bench && kp) {
      const rr = kp.range_resolved || {};
      syncLog("[M6b] hover", JSON.stringify({ id: kpId, rr, hint: [kp.range?.start?.line_hint, kp.range?.end?.line_hint] }));
    }
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

  /**
   * **源码区跳转滚动**（2026-10-25 task-140）：与预览侧同一套不变量。
   *   I1 目标行区间任意部分已可见 ⇒ 不动；I2 完全不可见 ⇒ 居中（不是顶对齐）。
   * 旧实现在 `highlightRange` / `highlightRangeWithError` 里用 `block:"start"`，
   * 与预览侧同病：把目标**首行**顶到编辑区顶部，且已可见时也硬滚。
   * @param {number} startLine 1-based 首行
   * @param {number} endLine 1-based 末行（含）
   */
  function _scrollSourceRangeIntoViewCentered(startLine, endLine) {
    const pane = document.getElementById("editor-pane");
    if (!pane) return;
    const firstEl = document.getElementById("line-" + startLine);
    const lastEl = document.getElementById("line-" + endLine) || firstEl;
    if (!firstEl || !lastEl) return;
    const pr = pane.getBoundingClientRect();
    const fr = firstEl.getBoundingClientRect();
    const lr = lastEl.getBoundingClientRect();
    // 相对视口：负数=在视口上方
    const top = fr.top - pr.top;
    const bottom = lr.bottom - pr.top;
    const vh = pane.clientHeight;
    const EPS = 1;
    // I1：任意部分可见 ⇒ 不动
    if (Math.min(bottom, vh) - Math.max(top, 0) > EPS) return;
    // I2：居中；目标比视口高时顶边贴齐
    const h = lr.bottom - fr.top;
    const targetTop = vh > h ? (vh - h) / 2 : 0;
    pane.scrollTop += top - targetTop;
  }

  /**
   * 只标记 KP 范围：不滚动、不闪烁、不自动消失。
   * 用于「修改范围 / 创建知识点」等**用户正在看屏幕上内容**的场合——
   * 这些场景只需要把范围标出来，滚动+闪烁会打断阅读/输入（与跳转语义区分）。
   */
  function markRangeQuiet(startLine, endLine) {
    dismissKpRangeHighlight();
    for (let n = startLine; n <= endLine; n++) {
      const line = document.getElementById("line-" + n);
      if (line) line.classList.add("in-range");
    }
    if (state.viewMode !== "source") {
      highlightPreviewRange(startLine, endLine, { scroll: false, flash: false });
    }
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
      _scrollSourceRangeIntoViewCentered(startLine, endLine);
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
      _scrollSourceRangeIntoViewCentered(startLine, endLine);
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

  /** 目标范围相对**滚动视口**（`#preview-pane`）的矩形。
   *  2026-10-25（task-140）：`layoutPreviewRangeBand` 原先只返回 `first` 元素，把已经算好的
   *  top/bottom 并集**丢掉了**——而"目标占了视口哪一块"正是跳转滚动唯一需要的不变量。
   *  现在直接用 `layoutPreviewRangeBand` 返回的几何（`{top, bottom}`，相对 `#preview`），
   *  换算到 `#preview-pane` 视口坐标（`#preview` 有 1.5rem/48px padding，不能直接当视口）。 */
  function previewRangeViewportRect(preview, laid) {
    if (!preview || !laid) return null;
    const pane = document.getElementById("preview-pane");
    if (!pane) return null;
    // `laid.top/bottom` 相对 `#preview` 的 border-box；`#preview` 自身随 pane 滚动 ⇒
    // 只需把 `#preview` 顶边换成 pane 视口顶边。
    const pr = preview.getBoundingClientRect();
    const paneR = pane.getBoundingClientRect();
    const offset = pr.top - paneR.top;      // 当前 `#preview` 顶边相对视口顶（通常为负=已滚过）
    const top = laid.top + offset;
    const bottom = laid.bottom + offset;
    return {
      top: top,
      bottom: bottom,
      height: Math.max(0, bottom - top),
      viewportH: pane.clientHeight,
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

    if (!Number.isFinite(top) || bottom <= top) {
      // 单行/零高目标（例如点击一个空行块的 band 高度为 0）：仍要给出几何，否则跳转无法居中。
      if (!Number.isFinite(top)) return { first: first, band: null, top: 0, bottom: 0 };
      return { first: first, band: null, top: top, bottom: Math.max(bottom, top) };
    }

    let band = document.getElementById("-preview-range-band");
    if (!band) {
      band = document.createElement("div");
      band.id = "-preview-range-band";
      band.className = "-preview-range-band";
      band.setAttribute("aria-hidden", "true");
      preview.appendChild(band);
    }

    band.style.top = `${Math.max(0, top)}px`;
    band.style.height = `${bottom - top}px`; band.dataset.srcRange = startLine + "-" + endLine; // 记下行区间 ⇒ 布局后移时由「预览带跟随布局」重定位（见 app.js 末尾块）
    // 2026-10-25 task-140：**同时返回几何**（top/bottom 相对 `#preview`）。
    // 旧签名只返回 `first`，把这里已经算好的并集丢掉了 —— 那是跳转唯一需要的不变量。
    return { first: first, band: band, top: top, bottom: bottom };
  }

  function highlightPreviewRange(startLine, endLine, opts) {
    if (!state.doc) return;
    const preview = $("#preview");
    if (!preview) return;   // 2026-09-25 AG97：窗口化回退 ⇒ 目标块永远是真身，不需要先"物化"
    if (opts?.flash !== false) {
      clearPreviewHighlights();
    }
    const laid = layoutPreviewRangeBand(preview, startLine, endLine);
    const first = laid && laid.first;
    const band = document.getElementById("-preview-range-band");
    if (band) {
      band.classList.toggle("error", !!opts?.error);
    }
    if (opts?.scroll && first) {
      _jumpScrollToRange(preview, laid);
      _reanchorJumpScroll(startLine, endLine);   // AG104：排版在跳转后才落定 ⇒ 之后只补偏移（不再重设落点）
    }
  }

  /**
   * **跳转滚动落点**（2026-10-25 task-140 重写）。
   *
   * 不变量（这才是函数该保证的东西）：
   *   I1 用户已经能看到目标（哪怕只露出一部分）⇒ **一个像素都不动**。
   *      人原话：「如果正在显示的内容已经有目标的部分区域（至少），仍然进行了滚动定位 … 不需要滚动定位」。
   *   I2 完全看不见目标 ⇒ 把目标**整体居中**（`block:"center"` 的语义），而不是顶到顶部。
   *   I3 记录"居中后目标顶边应处的视口偏移"，供二次校准**只补差值**用；绝不在这里或那里重设落点。
   *
   * 旧实现用 `first.scrollIntoView({block:"start"})`：
   *   ① 不看可见性 ⇒ 已可见也滚（违反 I1）；
   *   ② `start` = 顶对齐 ⇒ 居中后又被拉到顶部（违反 I2）；
   *   ③ 因为①+②叠加，视觉上永远是"往下挪一点"（人说的"固定从上往下滚的模式"）。
   * @returns {{scrolled:boolean, reason:string}}
   */
  function _jumpScrollToRange(preview, laid) {
    const pane = document.getElementById("preview-pane");
    if (!pane) return { scrolled: false, reason: "no-pane" };
    const rect = previewRangeViewportRect(preview, laid);
    if (!rect) return { scrolled: false, reason: "no-rect" };

    // I1：任意部分可见 ⇒ 不动。（人明确要求"至少部分区域"即满足）
    const EPS = 1;   // 亚像素容差：允许 1px 边界误差算"已见"
    const visibleTop = Math.max(rect.top, 0);
    const visibleBottom = Math.min(rect.bottom, rect.viewportH);
    if (visibleBottom - visibleTop > EPS) {
      log("SCROLL", "jump: target already visible (visible=" + Math.round(visibleBottom - visibleTop) +
        "px of " + Math.round(rect.height) + ") → no scroll");
      // 仍记录期望偏移：此时期望 = 目标当前偏移（保持用户所见，不做居中）
      _jumpExpectedOffset = null;   // null = "本次不居中，校准只需保证不漂"
      return { scrolled: false, reason: "already-visible" };
    }

    // I2：完全不可见 ⇒ 居中。目标比视口还高时退化为"顶边贴齐视口顶"（否则居中会让目标顶跑到视口上方）。
    const targetTop = rect.viewportH > rect.height
      ? Math.max(0, (rect.viewportH - rect.height) / 2)
      : 0;
    const delta = rect.top - targetTop;   // >0 说明目标在视口下方（需向下滚）
    if (Math.abs(delta) < 1) {
      _jumpExpectedOffset = targetTop;
      return { scrolled: false, reason: "already-centered" };
    }
    _jumpExpectedOffset = targetTop;
    _lastJumpPane = pane;
    pane.scrollTop += delta;
    log("SCROLL", "jump: center target delta=" + Math.round(delta) +
      " (rect.top=" + Math.round(rect.top) + " h=" + Math.round(rect.height) +
      " vp=" + rect.viewportH + " expected=" + Math.round(targetTop) + ")");
    return { scrolled: true, reason: "centered" };
  }

  /** 首次滚动后目标顶边应处的视口偏移（px）；null = 本次未居中（目标本已可见）。 */
  var _jumpExpectedOffset = null;
  /** 首次滚动操作的那个滚动容器，供二次校准确认"还是同一个视口"。 */
  var _lastJumpPane = null;

  /** **跳转落点的二次校准**（AG104 原意 + 2026-10-25 task-140 重写）。
   *
   *  **原意（保留）**：`highlightPreviewRange` 那次滚动发生在**布局还没最终定形**时 —— MathJax 是"排队跑、
   *  不 await"的（公式一排版，行高就变），懒加载图片在未加载前是 0 高 ⇒ 目标之后再结算一次高度，落点就漂了
   *  （表现出来就是"跳过去差一截"）。
   *
   *  **旧实现错在哪（task-140 人反馈）**：它把"补偏移"做成了"重设落点" ——
   *  在 350 ms / 1400 ms 又各调一次 `scrollIntoView({block:"start"})`，
   *  于是①过一小会被拉到顶部（人：「过一小会就把目标的开始行对齐到编辑区域的顶部，错误」）、
   *  ②已在视口内的目标也被强行滚动。
   *
   *  **新不变量**：二次校准**只修正漂移，绝不重新决定落点**。
   *   · 目标仍完整可见 ⇒ 什么都不做（排版变化没影响可见性，用户看到的不需要动）
   *   · 目标不可见且有期望偏移（本次是居中跳过来的）⇒ 只补 `当前偏移 - 期望偏移` 的差值
   *   · 本次跳转时目标本就可见（`_jumpExpectedOffset === null`）⇒ 什么都不做（用户视野优先）
   *   · 用户已滚动过（既有 guard）⇒ 放弃
   *   · **绝不**调用 `scrollIntoView`
   *
   *  **绝不跟人抢滚动条**：一旦检测到用户自己滚轮/点击/触摸/按键（窗口期内任意一次），立刻放弃校正。 */
  var _jumpAnchorGuard = null;
  function _reanchorJumpScroll(startLine, endLine) {
    try {
      var pane = document.getElementById("preview-pane");
      if (!pane) return;
      // 本次跳转没居中（目标本已可见）⇒ 不做任何校准（I1：已可见不打扰）
      if (_jumpExpectedOffset === null || _lastJumpPane !== pane) return;
      var expected = _jumpExpectedOffset;
      var g = { cancelled: false };
      _jumpAnchorGuard = g;   // 新一轮跳转 ⇒ 顶掉上一轮的守卫
      var mark = function () { g.cancelled = true; };
      ["wheel", "mousedown", "touchstart", "keydown"].forEach(function (ev) {
        pane.addEventListener(ev, mark, { passive: true, once: true });
      });
      var tick = function (delay) {
        setTimeout(function () {
          if (g.cancelled || _jumpAnchorGuard !== g) return;
          var pv = document.getElementById("preview");
          if (!pv) return;
          var laid = layoutPreviewRangeBand(pv, startLine, endLine);   // 刷新 band 几何（排版可能已变）
          if (!laid || !laid.first) return;
          var rect = previewRangeViewportRect(pv, laid);
          if (!rect) return;
          // 目标整体已可见（哪怕排版让它挪了位置）⇒ 不动
          if (rect.top >= 0 && rect.bottom <= rect.viewportH) {
            log("SCROLL", "reanchor(" + delay + "ms): fully visible → no adjust");
            return;
          }
          // 只补差值：把目标顶边拉回期望偏移，不重设落点、不居中、不顶对齐
          var drift = rect.top - expected;
          if (Math.abs(drift) < 1) return;
          pane.scrollTop += drift;
          log("SCROLL", "reanchor(" + delay + "ms): drift=" + Math.round(drift) +
            " → scrollTop+=" + Math.round(drift) + " (rect.top=" + Math.round(rect.top) +
            " expected=" + Math.round(expected) + ")");
        }, delay);
      };
      tick(350); tick(1400);
    } catch (e) { /* 校准失败不影响主流程 */ }
  }

  function openAssistForNewKp(opts = {}) {
    openKpModalForCreate(opts);
  }

  function openAssistFromSelection({ text, lines }) {
    if (!lines?.length) return;
    const lo = Math.min(...lines);
    const hi = Math.max(...lines);
    const name = (text || "").split(/\n/)[0].trim().slice(0, 80) || T("cfg.assist.defaultName");
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
      <span class="-muted">${esc(T("cfg.assist.rangeLabel"))}</span>
      <div class="-view-toggle" role="tablist" aria-label="${esc(T("cfg.assist.previewModeAria"))}">
        <button type="button" class="-view-btn${mode === "source" ? " active" : ""}" data-assist-view="source">${esc(T("cfg.assist.viewSource"))}</button>
        <button type="button" class="-view-btn${mode === "markdown" ? " active" : ""}" data-assist-view="markdown">${esc(T("cfg.assist.viewMarkdown"))}</button>
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
      const text = T("cfg.assist.ellipsisTop", { to: viewStart - 1 });
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
      const text = T("cfg.assist.ellipsisBottom", { from: viewEnd + 1, total });
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
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-top -muted">${esc(T("cfg.assist.ellipsisTop", { to: viewStart - 1 }))}</div>`;
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
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-bottom -muted">${esc(T("cfg.assist.ellipsisBottom", { from: viewEnd + 1, total }))}</div>`;
    }

    wrap.innerHTML = html;
    bindAssistPreviewToolbar(wrap);
  }

  async function renderAssistMarkdownPreview(wrap, start, end, total, viewStart, viewEnd, opts = {}) {
    let html = assistPreviewToolbarHtml();

    if (viewStart > 1) {
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-top -muted">${esc(T("cfg.assist.ellipsisTop", { to: viewStart - 1 }))}</div>`;
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
      html += `<div class="-assist-preview-ellipsis -assist-preview-ellipsis-bottom -muted">${esc(T("cfg.assist.ellipsisBottom", { from: viewEnd + 1, total }))}</div>`;
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
        `<p class="-assist-preview-error">${esc(T("cfg.assist.rangeError"))}</p>`;
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
      setStatusError(res.message || T("cfg.kpSave.fail"));
      return false;
    }
    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    window.MemoriaFileTree?.render?.();
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
      setStatusError(T("cfg.kpSave.fail"), T("cfg.kpSave.nameEmpty"));
      return false;
    }
    if (newId !== oldId) {
      if (
        !window.confirm(
          T("cfg.kpSave.renameConfirm", { oldId, newId })
        )
      ) {
        return false;
      }
      setStatus(T("cfg.kpSave.migrating"));
      const renameRes = await call("rename_kp_id", oldId, newId);
      if (renameRes.status !== "ok") {
        setStatusError(renameRes.message || T("cfg.kpSave.migrateFail"));
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
        ? T("cfg.kpSave.migrateStats", {
            n: renameRes.sidecar_files.length,
            m: renameRes.md_replacements || 0,
          })
        : "";
      setStatus(T("cfg.kpSave.migrated", { old: oldId, new: newId }), stats);
    }
    setStatus(T("cfg.kpSave.savingCfg"));
    const res = await call("update_kp", state.currentPath, panel.kpId, name);
    return reloadDocAfterKpChange(res, panel.kpId, T("cfg.kpSave.updated", { kpId: panel.kpId }));
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
    setStatus(T("cfg.kpSave.savingCfg"));
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
    return reloadDocAfterKpChange(res, panel.kpId, T("cfg.kpSave.updatedTags", { kpId: panel.kpId }));
  }

  async function saveKpModal() {
    const panel = state.kpPanel;
    syncKpPanelFromForm();
    if (panel?.mode === "create") {
      benchMark("start", "modal");
      const ok = await saveKpRange();
      if (ok) {
        closeKpModal();
        benchMark("modal_closed");
      }
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
        T("cfg.kpSave.deleteConfirm", { label })
      )
    ) {
      return;
    }
    setStatus(T("cfg.kpSave.deleting"));
    const res = await call("delete_kp", state.currentPath, kpId);
    if (res.status !== "ok") {
      setStatus(res.message || T("cfg.kpSave.deleteFail"));
      return;
    }
    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    window.MemoriaFileTree?.render?.();
    setViewMode(state.viewMode, { skipSave: true });
    renderPreview(res);
    setStatus(T("cfg.kpSave.deleted"), kpId);
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
      window.MemoriaFileTree?.render?.();
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
      setStatusError(T("cfg.kpSave.invalidRange"), T("cfg.kpSave.endBeforeStart"));
      return false;
    }
    if (end > total) {
      setStatusError(
        T("cfg.kpSave.invalidRange"),
        T("cfg.kpSave.endBeyond", { end, total })
      );
      return false;
    }
    if (!lineHasRangeSnippet(start)) {
      setStatusError(T("cfg.kpSave.cannotSave"), T("cfg.kpSave.startEmpty", { start }));
      return false;
    }
    if (!lineHasRangeSnippet(end)) {
      setStatusError(T("cfg.kpSave.cannotSave"), T("cfg.kpSave.endEmpty", { end }));
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
        setStatusError(T("cfg.kpSave.fail"), T("cfg.kpSave.idEmpty"));
        return false;
      }
      if (!kpName) {
        setStatusError(T("cfg.kpSave.fail"), T("cfg.kpSave.nameEmpty"));
        return false;
      }
      try {
        const check = await call("check_kp_id", kpId, state.currentPath);
        if (check.status !== "ok" || !check.available) {
          setStatusError(check.message || T("cfg.confirm.idTaken"), check.files?.join(", "));
          return false;
        }
      } catch (e) {
        setStatusError(T("cfg.confirm.validateFail"), String(e.message || e));
        return false;
      }
      benchMark("check_ok");
    }

    setStatus(T("cfg.kpSave.savingCfg"));
    const res = await call(
      "confirm_kp_range",
      state.currentPath,
      kpId,
      kpName,
      start,
      end
    );
    if (res.status !== "ok") {
      setStatusError(res.message || T("cfg.confirm.writeFail"));
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
    if (a.mode === "create") benchMark("rpc_ok");

    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    window.MemoriaFileTree?.render?.();
    await setViewMode(state.viewMode, { skipSave: true });
    await renderPreview(res);
    // 与 openFile 的 kpId 跳转路径不同：这里只标记范围（不滚动不闪烁），
    // 避免保存/创建后把用户视线拽走（跳转语义仍走 highlightRange）
    state.activeKpId = kpId;
    renderKpList(state.doc);
    markRangeQuiet(start, end);
    if (a.mode === "create") benchMark("ui_done");
    const created = a.mode === "create";
    setStatus(
      created ? T("cfg.kpSave.created") : T("cfg.kpSave.updatedRange"),
      T("cfg.confirm.doneDetail", { kpId, start, end })
    );
    if (created) {
      try {
        await saveKpCreateMetadata(kpId);
      } catch (_) {
        /* optional */
      }
    }
    // 图谱刷新与「弹窗关闭」解耦：host=kp（创建/编辑弹窗）先返回关窗，
    // 让用户立即看到定位+高亮，图数据异步补刷，避免窗口关闭被 relayout 拖住。
    if (host === "kp") {
      loadGraphData()
        .then(() => applyGraphGroupLayout({ relayout: true }))
        .catch(() => {});
      return true;
    }
    try {
      await loadGraphData();
      applyGraphGroupLayout({ relayout: true });
    } catch (_) {
      /* optional */
    }

    if (returnTo === "config") {
      openConfigModal({ tab: "kp" });
    }
    return true;
  }

  /** 侧栏宽度钳制：180 px ~ 窗口宽×75%（硬顶 1400px） */
  function _clampSidebarWidth(px) {
    const maxW = Math.max(480, Math.min(1400, Math.round(window.innerWidth * 0.75)));
    return Math.max(180, Math.min(maxW, Math.round(px)));
  }

  /**
   * 应用侧栏宽度；persist=true 时落盘到 ui-settings.json 的 layout.sidebarWidth。
   * ★ 只写 localStorage 是不够的：桌面壳（pywebview WebView2）默认 private_mode=True，
   *   每次启动清空本地存储 → 必须写应用自己的配置文件（磁盘为权威源）。
   */
  function applySidebarWidth(px, persist) {
    const sidebar = $("#-sidebar");
    if (!sidebar) return;
    const w = _clampSidebarWidth(px);
    sidebar.style.width = w + "px";
    _sidebarExpectedWidth = w; // 响应式假想几何用「期望宽」（折叠时也记得用户想要的宽度）
    if (!persist) return;
    try { localStorage.setItem("-sidebar-width", String(w)); } catch (e) { /* ignore */ }
    call("save_ui_settings", { layout: { sidebarWidth: w } }).catch(() => {});
  }

  /** 启动时从程序配置同步侧栏宽度（磁盘优先，覆盖本地缓存） */
  async function hydrateLayoutFromDisk() {
    try {
      const res = await call("get_ui_settings");
      const lay = res && res.status === "ok" && res.settings && res.settings.layout;
      const w = lay ? parseInt(lay.sidebarWidth, 10) : NaN;
      if (!isNaN(w)) applySidebarWidth(w, false);
    } catch (_) { /* 非桌面环境忽略 */ }
  }

  function setupSidebarResize() {
    const sidebar = $("#-sidebar");
    const resizer = $("#sidebar-resizer");
    let dragging = false;
    // 首帧先用本地缓存（若有），随后 hydrateLayoutFromDisk 用磁盘值覆盖
    const saved = parseInt(localStorage.getItem("-sidebar-width") || "", 10);
    if (!isNaN(saved)) applySidebarWidth(saved, false);
    resizer.addEventListener("mousedown", (e) => {
      dragging = true;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      applySidebarWidth(e.clientX, false);
    });
    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      applySidebarWidth(parseInt(sidebar.style.width, 10), true);
      applyResponsiveLayout("sidebar-width-commit");
    });
  }

  // 左栏（文件树/图谱）整体收起/展开。
  // 2026-09-18：边缘浮动按钮 `#sidebar-collapse-btn` 已删除，唯一入口改为顶栏最左的
  // 图标按钮 `#btn-toggle-sidebar`（VSCode 式），故不再需要任何"贴侧栏右缘"的定位代码。
  let _sideCollapseTimer = null;
  let _sidebarCollapsed = localStorage.getItem("-sidebar-collapsed") === "1";

  // ── 响应式布局派生状态（0.4.7 D3=A；**全部不落盘**）────────────────────────
  // 与"用户意图"严格分开：_sidebarCollapsed 是用户意图（落盘），以下是派生态（永不落盘）。
  let _sidebarAutoCollapsed = false;     // 因「两栏都想开 + 文档区不够」被自动折叠
  let _sidebarExpectedWidth = 280;       // 假想几何用：用户期望左栏宽（折叠时也记得）
  let _responsiveEngaged = false;        // 迟滞态：是否处于联动区（进入 720 / 退出 760）
  let _responsivePreviewEngaged = false; // ② 分屏→预览 的迟滞态
  let _autoViewModeFrom = null;          // 响应式切走前的 viewMode（null = 没切过）
  let _autoViewModeTo = null;            // 响应式切到的 viewMode
  let _lastPanelExpanded = null;         // 最近由用户展开的面板：'dock' | 'sidebar' | null
  let _responsiveRaf = 0;
  const _responsiveStats = { passes: 0, changes: 0, transitions: [] };
  const RESPONSIVE_CONTENT_PX = 720;     // 进入阈值：假想文档区宽 < 720 ⇒ 触发联动
  const RESPONSIVE_EXIT_PX = 760;        // 退出阈值（迟滞 40px，防边界抖动）

  /** 顶栏左栏按钮的文案/可按压态（语言切换后也走这里刷新，避免残留旧语言 title） */
  function _syncSidebarToggleBtn() {
    const btn = $("#btn-toggle-sidebar");
    if (!btn) return;
    // 生效折叠态 = 用户手动折叠 OR 响应式派生折叠（后者不落盘，见 applyResponsiveLayout）
    const eff = _sidebarCollapsed || _sidebarAutoCollapsed;
    // 0.4.7 task-136：三态 tooltip —— 自动折叠 / 用户折叠 / 展开。
    // 自动折叠态必须点明"展开会收起对话栏"（否则用户点开后面板又消失一次）。
    let titleKey;
    if (_sidebarAutoCollapsed) titleKey = "side.autoCollapsedTitle";
    else if (_sidebarCollapsed) titleKey = "side.expandTitle";
    else titleKey = "side.collapseTitle";
    btn.title = T(titleKey);
    btn.setAttribute("aria-label", btn.title);
    // 视觉弱强调（方案 i）：自动折叠是"系统临时收起"，与用户主动折叠区分；只用既有主题令牌。
    btn.classList.toggle("-sidebar-auto-collapsed", _sidebarAutoCollapsed);
    // aria-pressed = 当前是否展开（与右栏 `#btn-agent` 同一口径）
    btn.setAttribute("aria-pressed", String(!eff));
  }

  function _renderSidebarCollapsed(persist) {
    const sidebar = $("#-sidebar");
    if (!sidebar) return;
    sidebar.classList.toggle("-sidebar--collapsed", _sidebarCollapsed || _sidebarAutoCollapsed);
    _syncSidebarToggleBtn();
    if (persist) localStorage.setItem("-sidebar-collapsed", _sidebarCollapsed ? "1" : "0");
    clearTimeout(_sideCollapseTimer);
    // 等宽度过渡结束后让图谱画布/布局重新量算
    _sideCollapseTimer = setTimeout(() => {
      window.dispatchEvent(new Event("resize"));
      window.MemoriaGraphGroups?.notifyLayoutChanged?.();
    }, 220);
  }

  function _applySidebarCollapsed() {
    _renderSidebarCollapsed(true);
  }

  function setupSidebarCollapse() {
    const btn = $("#btn-toggle-sidebar");
    if (!btn) return;
    // task-136：标题由本函数按三态（自动折叠/用户折叠/展开）接管 ⇒ 摘掉静态
    // `data-i18n-attr="title:side.collapseTitle"`，否则 i18n 静态刷新会在启动时把
    // 自动折叠态的专用文案覆盖成"收起侧栏"（真机实测踩到）。语言切换仍由 addRefresh 更新。
    btn.removeAttribute("data-i18n-attr");
    btn.addEventListener("click", () => {
      // 自动折叠态下的点击 = 「请展开这一栏」：清派生折叠，让另一面板让位（规则③）
      if (_sidebarAutoCollapsed) {
        _sidebarAutoCollapsed = false;
        _sidebarCollapsed = false;
        _lastPanelExpanded = "sidebar";
        _renderSidebarCollapsed(true);
        applyResponsiveLayout("user-expand-sidebar");
        return;
      }
      _sidebarCollapsed = !_sidebarCollapsed;
      _lastPanelExpanded = _sidebarCollapsed ? null : "sidebar";
      _renderSidebarCollapsed(true);
      applyResponsiveLayout("user-toggle-sidebar");
    });
    window.MemoriaI18n?.addRefresh?.(_syncSidebarToggleBtn);
    _applySidebarCollapsed();
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 响应式布局（2026-10-25，0.4.7 D3=A：按原话自动联动 + 保守阈值 720px）
  //
  // 人裁决：文档区 `#content` 宽 < 720px 时才触发；**每次按窗口状态算、不记忆**。
  // 三条联动（人原话）：
  //   ① dock 展开      → 收缩文件树（折叠左栏；派生态，不落盘）
  //   ② 文件树已折叠 + 分屏 → 切预览（skipSave，记原 mode；dock 未展开时不强制切）
  //   ③ 文件树同理：展开文件树 → 收起 dock（响应式隐藏，不落盘）
  //
  // ★ 防振荡（本层最关键的约束）：
  //   判据用「**假想几何**」= `#main` 内宽 − 左栏**期望**宽 − dock **期望**宽 ——
  //   它假设两栏都展开，**不随折叠/隐藏而变化** ⇒ 不会出现
  //   "折了左栏→变宽→条件不成立→还原→又变窄→再折" 的自否定循环。
  //   **不主动还原**：只有窗口变宽到假想文档区 ≥ 760（迟滞退出）或用户展开另一面板时才还原。
  //   另用迟滞：进入 720 / 退出 760（边界抖动不会反复切换）。
  //
  // ★ 不覆盖用户手调：dockWidthRem / layout.sidebarWidth / 用户 _sidebarCollapsed 一律只读；
  //   本层只改"可见性派生态"，窗口变宽自动还原。
  // ══════════════════════════════════════════════════════════════════════════

  /** 假想几何：假设左右两栏都按**期望宽**展开时，文档区能有多少 px（折叠后该值不变）。 */
  function _responsiveMetrics() {
    const main = $("#main");
    const mainW = main ? main.clientWidth : window.innerWidth;
    // ★ 用「期望宽」而不是 DOM 当前宽：折叠动画（0.18s）期间 DOM 宽会在 280→0 之间变化，
    //   若拿它算假想几何，判据会在动画帧里来回跨阈值 ⇒ 这正是要避免的自我否定/闪烁。
    //   `_sidebarExpectedWidth` 只在用户拖拽/磁盘 hydrate 时更新（applySidebarWidth），
    //   自动折叠不碰它 ⇒ 假想几何在折叠前后**恒定**。
    const sidebarExpected = _sidebarExpectedWidth || 280;
    const dockState = window.MemoriaAgentPanel?.getDockState?.() || null;
    const dockExpected = dockState
      ? Math.round(Number(dockState.expectedRem) * Number(dockState.unit || 16))
      : 352;
    return {
      mainW,
      sidebarExpected,
      dockExpected,
      // 假想文档区宽（关键判据；折叠/隐藏都不变）
      hypothetical: mainW - sidebarExpected - dockExpected,
      dockState,
    };
  }

  function _responsiveRestoreAuto() {
    let changed = false;
    if (_sidebarAutoCollapsed) {
      _sidebarAutoCollapsed = false;
      _renderSidebarCollapsed(false); // 不落盘
      changed = true;
    }
    if (window.MemoriaAgentPanel?.getDockState?.()?.responsiveHidden) {
      window.MemoriaAgentPanel.setDockResponsiveHidden(false);
      changed = true;
    }
    return changed;
  }

  /** ② 分屏→预览（含迟滞；dock 未展开时不强制切）。返回是否发生了派生切换。 */
  function _responsiveSyncPreview(m, dockIntent, sidebarIntent) {
    const sidebarUsable = sidebarIntent && !_sidebarAutoCollapsed;
    const widthWithDockOnly = m.mainW - m.dockExpected; // 左栏折叠后的**实际**文档区宽
    let need = false;
    if (!sidebarUsable && dockIntent) {
      need = _responsivePreviewEngaged
        ? widthWithDockOnly < RESPONSIVE_EXIT_PX
        : widthWithDockOnly < RESPONSIVE_CONTENT_PX;
    }
    _responsivePreviewEngaged = need;
    let changed = false;
    if (need && !_autoViewModeFrom) {
      if (state.viewMode === "split") {
        _autoViewModeFrom = "split";
        _autoViewModeTo = "preview";
        setViewMode("preview", { skipSave: true }); // 不写 localStorage["-view"]
        changed = true;
      }
    } else if (!need && _autoViewModeFrom) {
      // 只有用户没手动改过视图时才还原（用户改过 = 他的选择优先）
      if (state.viewMode === _autoViewModeTo) setViewMode(_autoViewModeFrom, { skipSave: true });
      _autoViewModeFrom = null;
      _autoViewModeTo = null;
      changed = true;
    }
    return changed;
  }

  function _applyResponsiveNow(reason) {
    _responsiveStats.passes += 1;
    const panel = window.MemoriaAgentPanel;
    const m = _responsiveMetrics();
    const dockState = m.dockState;
    // 「用户意图」而非「当前可见性」：折叠/自动隐藏/响应隐藏都不算用户想展开
    const dockIntent = dockState ? !dockState.collapsed : true;
    const sidebarIntent = !_sidebarCollapsed;
    const bothIntent = dockIntent && sidebarIntent;

    // 迟滞：只有「两栏都想开」才有联动；进入 720 / 退出 760
    _responsiveEngaged = bothIntent
      ? _responsiveEngaged
        ? m.hypothetical < RESPONSIVE_EXIT_PX
        : m.hypothetical < RESPONSIVE_CONTENT_PX
      : false;

    let changed = false;
    if (!bothIntent) {
      changed = _responsiveRestoreAuto() || changed;
    } else if (_responsiveEngaged) {
      if (_lastPanelExpanded === "sidebar") {
        // ③ 用户刚展开左栏 ⇒ dock 让位（响应式隐藏，不落盘）
        if (!dockState?.responsiveHidden) {
          panel?.setDockResponsiveHidden?.(true);
          changed = true;
        }
        if (_sidebarAutoCollapsed) {
          _sidebarAutoCollapsed = false;
          _renderSidebarCollapsed(false);
          changed = true;
        }
      } else {
        // ① 用户刚展开 dock（或启动兜底）⇒ 折叠左栏（派生，不落盘）
        if (!_sidebarAutoCollapsed) {
          _sidebarAutoCollapsed = true;
          _renderSidebarCollapsed(false);
          changed = true;
        }
        if (dockState?.responsiveHidden) {
          panel?.setDockResponsiveHidden?.(false);
          changed = true;
        }
      }
    } else {
      // 宽屏（假想文档区 ≥ 退出阈值 760）：恢复所有派生改动（迟滞带内 720~760 才"保持现状"）
      changed = _responsiveRestoreAuto() || changed;
    }

    changed = _responsiveSyncPreview(m, dockIntent, sidebarIntent) || changed;
    if (changed) {
      _responsiveStats.changes += 1;
      _responsiveStats.transitions.push({
        reason: reason || "",
        hypothetical: m.hypothetical,
        sidebarAuto: _sidebarAutoCollapsed,
        dockResponsiveHidden: !!panel?.getDockState?.()?.responsiveHidden,
        viewMode: state.viewMode,
      });
      if (_responsiveStats.transitions.length > 50) _responsiveStats.transitions.shift();
    }
  }

  /** rAF 合流入口：所有触发（resize / ResizeObserver / 面板事件 / 用户操作）都走这里。 */
  function applyResponsiveLayout(reason) {
    cancelAnimationFrame(_responsiveRaf);
    _responsiveRaf = requestAnimationFrame(() => {
      _responsiveRaf = 0;
      _applyResponsiveNow(reason || "raf");
    });
  }

  /**
   * dock 展开请求（agent-panel 在"空间不足被拒"时调用）：若有左栏可让位，
   * 把左栏折叠成派生态（不落盘）并返回 true；否则 false（调用方保留原提示）。
   */
  function requestDockSpace() {
    const m = _responsiveMetrics();
    if (m.hypothetical >= RESPONSIVE_CONTENT_PX) return false; // 假想宽度够，无需让位
    if (_sidebarCollapsed) return false; // 左栏已按用户意图收起，仍不够 ⇒ 交给 dock 自身降级
    _lastPanelExpanded = "dock";
    _sidebarAutoCollapsed = true;
    _renderSidebarCollapsed(false);
    applyResponsiveLayout("request-dock-space");
    return true;
  }

  function getResponsiveState() {
    const m = _responsiveMetrics();
    return {
      contentPx: m.hypothetical,
      enterPx: RESPONSIVE_CONTENT_PX,
      exitPx: RESPONSIVE_EXIT_PX,
      engaged: _responsiveEngaged,
      sidebarAutoCollapsed: _sidebarAutoCollapsed,
      sidebarUserCollapsed: _sidebarCollapsed,
      sidebarExpectedPx: m.sidebarExpected,
      dockExpectedPx: m.dockExpected,
      dockResponsiveHidden: !!m.dockState?.responsiveHidden,
      viewMode: state.viewMode,
      autoViewFrom: _autoViewModeFrom,
      autoViewTo: _autoViewModeTo,
      lastPanelExpanded: _lastPanelExpanded,
      stats: {
        passes: _responsiveStats.passes,
        changes: _responsiveStats.changes,
        transitions: _responsiveStats.transitions.slice(-12),
      },
    };
  }

  function setupResponsiveLayout() {
    const sidebar = $("#-sidebar");
    if (sidebar && !_sidebarExpectedWidth) _sidebarExpectedWidth = Math.round(sidebar.getBoundingClientRect().width) || 280;
    window.addEventListener("resize", () => applyResponsiveLayout("window-resize"));
    if (typeof ResizeObserver !== "undefined") {
      const main = $("#main");
      if (main) new ResizeObserver(() => applyResponsiveLayout("main-ro")).observe(main);
    }
    // 面板侧的用户操作/布局变化（dock 展开/折叠、拖完宽）通过自定义事件通知本层
    window.addEventListener("memoria:panels-changed", (ev) => {
      const d = ev && ev.detail ? ev.detail : {};
      if (d.expanded) _lastPanelExpanded = d.panel || "dock";
      applyResponsiveLayout("panel:" + (d.reason || d.panel || "change"));
    });
    // 首帧 + 等 dock 面板 init / layout hydrate 落定后再算一次
    applyResponsiveLayout("startup");
    setTimeout(() => applyResponsiveLayout("startup-late"), 0);
    setTimeout(() => applyResponsiveLayout("startup-late2"), 260);
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
    const fileMenuEl = $("#file-menu");
    const recentPanelEl = $("#file-menu-recent");
    const closeFileMenu = () => {
      if (fileMenuEl) fileMenuEl.hidden = true;
      if (recentPanelEl) recentPanelEl.hidden = true;
      $("#btn-file")?.setAttribute("aria-expanded", "false");
    };
    $("#btn-file")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = !!(fileMenuEl && fileMenuEl.hidden);
      if (fileMenuEl) fileMenuEl.hidden = !willOpen;
      if (!willOpen && recentPanelEl) recentPanelEl.hidden = true;
      $("#btn-file")?.setAttribute("aria-expanded", String(willOpen));
    });
    document.addEventListener("click", (e) => {
      const btn = $("#btn-file");
      if (fileMenuEl && btn && !fileMenuEl.contains(e.target) && !btn.contains(e.target)) {
        closeFileMenu();
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeFileMenu();
    });
    $("#file-menu-open")?.addEventListener("click", () => { closeFileMenu(); openKb(); });
    $("#file-menu-import")?.addEventListener("click", () => {
      closeFileMenu();
      window.MemoriaImportFlow?.start();
    });

    /** 请求后端启动一个新的 Memoria 窗口进程（可选携带知识库目录）。 */
    async function spawnNewWindow(kbPath) {
      let res = null;
      try {
        res = await call("open_new_window", kbPath || "");
      } catch (err) {
        res = { status: "error", message: String(err) };
      }
      if (!res || res.status !== "ok") {
        setStatus(T("toolbar.newWindowFailed"), (res && res.message) || "");
      }
    }

    /** 归一化比较两个知识库目录路径（分隔符 / 末尾斜杠 / 大小写不敏感）。 */
    function samePath(a, b) {
      const norm = (p) => String(p || "").replace(/[\\/]+/g, "/").replace(/\/+$/, "").toLowerCase();
      const na = norm(a);
      return !!na && na === norm(b);
    }

    /** 拉取最近打开的知识库并渲染「打开最近」二级列表（按上次打开时间降序）。 */
    async function renderRecentKbMenu() {
      if (!recentPanelEl) return;
      recentPanelEl.textContent = "";
      const makeItem = (label, opts) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = label;
        if (opts && opts.title) b.title = opts.title;
        if (opts && opts.disabled) b.disabled = true;
        recentPanelEl.appendChild(b);
        return b;
      };
      let res = null;
      try {
        res = await call("get_recent_kbs");
      } catch (_) {
        res = null;
      }
      const items = (res && Array.isArray(res.items)) ? res.items : null;
      if (!items) {
        makeItem(T("toolbar.recentLoadFailed"), { disabled: true });
        return;
      }
      if (!items.length) {
        makeItem(T("toolbar.recentEmpty"), { disabled: true });
        return;
      }
      for (const it of items) {
        const label = it.name || it.path || "";
        makeItem(label, { title: it.path }).addEventListener("click", () => {
          closeFileMenu();
          // 当前窗口未开库 → 直接在本窗口装载；已开着别的库 → 另开窗口（不打断当前会话）；
          // 同一个库 → 忽略，避免重复装载。
          if (!state.kbPath) {
            openKbAt(it.path);
            return;
          }
          if (!samePath(state.kbPath, it.path)) spawnNewWindow(it.path);
        });
      }
    }

    $("#file-menu-new-window")?.addEventListener("click", () => {
      closeFileMenu();
      spawnNewWindow("");
    });
    $("#file-menu-open-recent")?.addEventListener("click", () => {
      const willShow = !!(recentPanelEl && recentPanelEl.hidden);
      if (recentPanelEl) recentPanelEl.hidden = !willShow;
      if (willShow) renderRecentKbMenu();
    });
    // 图片插入按钮（btn-insert-image）的 click/mousedown 与可用性状态机
    // （focusin/selectionchange/初始刷新）已随图片子系统迁至 image-tools.js，由 boot init
    // 「关闭知识库」= 原顶栏 `#btn-kb-close`（退出）按钮的行为，2026-09-18 移入文件菜单；
    // 可用态由 showKbIndicator() 统一同步（未开库 → disabled）
    $("#file-menu-close-kb")?.addEventListener("click", () => { closeFileMenu(); closeKb(); });
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
    // 「检查」按钮 click 已随 KB 完整性检查子系统迁至 kb-check.js，由 boot init
    // 工具条搜索（Ctrl+K/输入/范围切换/结果面板）已抽至 toolbar-search.js，由 boot init
    // 界面整体缩放快捷键：Ctrl+= 放大 / Ctrl+- 缩小 / Ctrl+0 复位
    if (window.MemoriaDisplaySettings) {
      document.addEventListener("keydown", (e) => {
        if (!(e.ctrlKey || e.metaKey)) return;
        const k = e.key.toLowerCase();
        if (k === "=" || k === "+") {
          e.preventDefault();
          MemoriaDisplaySettings.adjustUiScale(0.1);
        } else if (k === "-") {
          e.preventDefault();
          MemoriaDisplaySettings.adjustUiScale(-0.1);
        } else if (k === "0") {
          e.preventDefault();
          MemoriaDisplaySettings.resetUiScale();
        }
      });
    }
    // 检查弹窗的关闭/重新检查/backdrop 点击已随 KB 完整性检查子系统迁至 kb-check.js，由 boot init
    $("#status-stats")?.addEventListener("click", async () => {
      if ($("#status-stats").dataset.kbCheck) {
        window.MemoriaKbCheck?.openCheckModal?.();
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
        setStatusError(T("app.openFileFirst"));
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
          setStatus(T("cfg.match.located", { ln }), match?.is_substring ? T("cfg.match.substringBlocked") : T("cfg.match.checkboxHint"));
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
          setStatus(T("cfg.match.located", { ln }), match?.is_substring ? T("cfg.match.substringBlocked") : "");
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
    setupSidebarCollapse();
    setupResponsiveLayout();
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
    // 静默检查设置订阅（MemoriaCheckSettings.onChange）已随 KB 完整性检查子系统迁至 kb-check.js init
    if (window.MemoriaDisplaySettings) {
      MemoriaDisplaySettings.hydrateFromDisk();
    }
    if (window.MemoriaI18n) {
      MemoriaI18n.hydrate();
      // 语言切换后的检查弹窗/角标重绘分支已随 KB 完整性检查子系统迁至 kb-check.js init
      MemoriaI18n.addRefresh(function () {
        if (window.MemoriaGraphSettings && window.MemoriaGraphSettings.rerenderCurrentTab) {
          window.MemoriaGraphSettings.rerenderCurrentTab();
        }
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
        // S1：关闭编辑模式 ⇒ 画笔武装必须一起收掉（只读态涂不上，留着只会误导）；
        // 开启编辑模式时不动画笔（保持原有"涂完可继续涂"的连续涂抹语义）
        if (window.MemoriaEditHandler && !window.MemoriaEditHandler.editMode) _brushDisarmAll();
        // 编辑模式切换后立即刷新图片插入按钮可用性（不依赖 selectionchange 的后续触发）
        window.MemoriaImageTools?.refreshImageInsertAvailability?.();
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

  /**
   * 应用服务门面：暴露给拆分出去的功能模块（import-flow 等）回调使用。
   * 新增需要被外部模块调用的 app 私有服务时，在此追加。
   */
  window.MemoriaApp = {
    state,
    call,
    readClipboardText,
    writeClipboardText,
    T,
    esc,
    setStatus,
    setStatusError,
    showFlashError,
    showFlashInfo,
    refreshFiles,
    loadLinkTargets,
    loadGraphData,
    refreshKbPendingSummary,
    openFile,
    openKb,
    // ── 图片子系统（image-tools.js）追加的私有服务 ──────────────────
    // 源码行写回/撤销/重渲染/右键菜单/确认弹窗，均为 app.js 闭包内实现，
    // 通过门面供 image-tools.js 调用（行为与原先在 app.js 内一致）。
    closestLineEl,
    renumberSourceLines,
    scheduleRenderSync,
    markDirty,
    srcPushBefore: _srcPushBefore,
    srcAfterEdit: _srcAfterEdit,
    srcResetCoalesce: () => {
      _srcCoalesceAt = 0;
    },
    renderEditor,
    renderPreview,
    showTreeContextMenu,
    confirmTreeAction,
    // ── 文件树子系统（file-tree.js）追加的私有服务 ─────────────────
    // 标签栏重绘（重命名改签）、关闭标签（删除被删文件）、导航按钮刷新（树内点击切换），
    // 均为 app.js 闭包内实现，通过门面供 file-tree.js 调用（行为与原先在 app.js 内一致）。
    renderTabs,
    closeTabAt,
    updateNavButtons,
    // ── 块身份索引（2026-10-20 P2，Lead 裁决）─────────────────────────
    // 全 App **唯一** BlockIndex 实例。★ **消费者只读**：KP 面板 / 编辑模块 / 助手面板
    // 只能用 blocks()/get()/atSrcLine()/rangeOf()/blocksInRange()/isFrozen()/getMetrics()，
    // **不得**调 upsert()/commit()/remove()（写权限唯一属于渲染内核）。
    // 设计：docs/design/block-identity-design.md §7.3；生命周期见 P2 草稿 §3.0。
    blockIndex: BI,
    // ── KB 完整性检查模块（kb-check.js）追加的私有服务 ─────────────────
    // 后端检查消息本地化（i18n.md §5.1 助手，图谱审计提示等 app.js 侧亦复用）、
    // 状态栏统计重绘、路径规范化、路径修复后的打开标签重映射，均为 app.js 闭包内实现，
    // 通过门面供 kb-check.js 调用（行为与原先在 app.js 内一致）。
    localizeCheckIssue,
    renderStatusStats,
    normRelPath,
    remapOpenTabsAfterPathRepair, getViewTopSrcLine: _getViewTopSrcLine, scrollToSrcLine: _scrollToSrcLine,
    // ── 响应式布局（0.4.7 D3=A）───────────────────────────────────────
    // 任务-93：`applyResponsiveLayout()` 可被探针手动触发（生产由 resize/RO/面板事件驱动）；
    // `getResponsiveState()` 只读；`requestDockSpace()` 供 agent-panel 在"dock 展开被拒"时请求左栏让位。
    applyResponsiveLayout,
    getResponsiveState,
    requestDockSpace,
  };

  window.MemoriaBridge?.onReady?.(() => {
    bindEvents();
    window.MemoriaImportFlow?.init?.();
    window.MemoriaToolbarSearch?.init?.();
    window.MemoriaImageTools?.init?.();
    window.MemoriaKbCheck?.init?.();
    window.MemoriaKbAgent?.init?.();
    window.MemoriaFileTree?.init?.();
    window.MemoriaAgentPanel?.init?.();
    bindPreviewPaste();
    initKb();
    hydrateCustomColorsFromDisk();
    hydrateLayoutFromDisk();
    window.MemoriaWindowChrome?.initWindowChrome?.();
  });

  window.MemoriaGraphShell = {
    getGraphGroupId() {
      return state.graphGroupId || window.MemoriaGraphGroups?.ALL_GROUP_ID || "all";
    },
  };

  /* ===== 预览高亮条「跟随布局」（2026-09-20）=============================================
     用户报障：「预览区域高亮位置还是不对…偏移以前知识点点击跳转的时候也出现过，常常发生在
     文件很长的情况」。根因（真机只读实测，非推断）：`#-preview-range-band` 是**一次性像素定位**
     ——`layoutPreviewRangeBand()` 在渲染流程里量一次 `getBoundingClientRect()` 定下 `top/height`
     就不再更新；而预览的最终布局此时并未定型：Mermaid 替换容器（`markdown-preview.js`）与
     MathJax 排版在 `mermaid.render`/`typesetPromise` 的 promise 之后**还会继续改变高度**
     （SVG 内文本量算、字体、图片解码、`foreignObject` 重排都会晚一拍），长文件里这些变化累积
     在高亮行**上方**，于是 band 停在被抬升前的位置（实测 `test-content.md` 第 300 行偏移
     **302px**：band 8678 vs 块 8980，且布局稳定后也不自恢复）。
     修法 = 让 band 自己跟着布局走：band 上记下它当前代表的行区间（`dataset.srcRange`，在
     `layoutPreviewRangeBand` 里写），此处用 **ResizeObserver 盯内容容器**（内容尺寸一变就按记下
     的区间重算），并补一条图片 `load/error` 捕获（同尺寸替换时 RO 不触发）。band 被摘掉
     （`clearPreviewHighlights`）后 RO 回调找不到 band 即空转 ⇒ 无需清理、也不会有脏状态。
     幂等：重算只改 `top/height`，不碰滚动、不重建 DOM，因此不会与 `fade-out` 计时器打架。
     落点纪律：本块**追加在 IIFE 末尾**（`window.MemoriaApp` 门面之后、`})();` 之前）⇒ 仅其后
     的「顶部文件标签栏滚轮」块行号 +N（该块锚点已在 02 篇就地更新），其余锚点零漂移。 */
  (function watchPreviewBandLayout() {
    const preview = $("#preview");
    if (!preview || typeof ResizeObserver === "undefined") return;
    const retarget = function () {
      const band = document.getElementById("-preview-range-band");
      if (!band || !band.dataset.srcRange) return;
      const parts = String(band.dataset.srcRange).split("-");
      const s = Number(parts[0]);
      const e = Number(parts[1]);
      if (!(s > 0) || !(e >= s)) return;
      layoutPreviewRangeBand(preview, s, e);
    };
    const target = preview.querySelector(".-preview-content") || preview;
    new ResizeObserver(retarget).observe(target);
    preview.addEventListener("load", retarget, true);
    preview.addEventListener("error", retarget, true);
  })();

  /**
   * 2026-09-23 性能：预览的 MathJax 排版改为**后台跑**，且**只给「最新一轮渲染」做**。
   *
   * 为什么不能简单地 await 掉：实测一篇 2712 行的教材，`MathJax.typesetPromise` 要约 **2.0–2.2 s**；
   * 它以前被 `renderPreview` 等着，整条「切文件」链路被拖长同样多。改成不 await 后，文件正文 / 编辑器 /
   * KP 列表立刻可用，公式在随后「晚一拍」升级成渲染态（期间看到的是 `$…$` 原文）。
   *
   * 为什么还要「链在前一个后面 + 比 token」：MathJax 内部是**串行队列**，连点几个文件会排成一长串
   * 各自的排版（旧预览的 DOM 早被换掉了，纯属白干）⇒ 先等前一个跑完，再比 `token` 与
   * `state.previewToken`：**已经不是最新一轮的直接跳过**。
   *
   * 定义必须留在本 IIFE 内（`state` / `log` 都在这儿）—— 2026-09-23 实测踩过一次坑：把它追加到文件
   * 末尾的**另一个** IIFE 里 ⇒ `renderPreview` 报 `ReferenceError`，整个预览被错误条替换。
   */
  function queuePreviewMathTypeset(preview, token) {
    const run = () => {
      if (token !== state.previewToken) return Promise.resolve(); // 已被更新的一轮取代 ⇒ 不排了
      if (!window.MathJax?.typesetPromise) return Promise.resolve();
      // ★ 2026-10-23 task-72：整篇/首屏这一轮排完后同样入缓存（滚动路径之外的公式也要能复用）。
      return MathJax.typesetPromise([preview])
        .then(function (v) { try { _tsStoreWithin(preview); } catch (_) {} return v; })
        .catch((e) => log("render", "MathJax: " + e.message));
    };
    const prev = state._mathPending;
    const chain = prev && typeof prev.then === "function" ? prev.catch(() => {}) : Promise.resolve();
    state._mathPending = chain.then(run);
    return state._mathPending;
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-23 追加：**页签切换提速** —— 预览 DOM 缓存 + 可选后台预渲染
  //
  // 背景（人：「出现在页签的文件能不能内存预加载减小切换速度？或者后台提供 后台预加载开关，
  // 并且说明更大的硬件开销和更流畅的体验（推荐大型知识库）」）：
  // 实测一篇 2712 行 / 2003 块的文档切页签约 1.5 s —— 其中后端 `load_document` 仅 ~49 ms
  // （且已服务端缓存），MathJax ~2.0–2.2 s（已改为后台跑），**主耗时在预览渲染链**：
  // `Parser.parse` → `Renderer.render` → 插 DOM → `stampBlockLines` → contentEditable 处理 → 布局。
  // 因此这里缓存的是**渲染好的预览 DOM 本身**（节点整体搬移，不是克隆 ⇒ 已挂的事件监听与已排版好的
  // MathJax/Mermaid 产物一并保留）。**不做第二份文档数据缓存**：后端已按 (路径, mtime, size) 缓存，
  // 前端再来一份只会多一处过期风险，而收益只有几十毫秒。
  //
  // 三条不变量（宁可慢一次，也绝不显示过期内容）：
  //   ① 有条目 ⇒ 它的 DOM 一定**不在** `#preview` 里（切走时搬出、切回时搬回并删除条目）；
  //   ② 条目里同时存 **正文指纹**（`_bodyFingerprint`）与后端 **版本号**（`load_document` 追加的
  //      `version` = 文件内容 sha256）—— 任一不符立即丢弃，重走全量渲染；
  //   ③ （2026-10-19 修订）**缓存有效性 = 渲染那一刻的正文指纹**，不再是"本会话没编辑过"这条代理判据。
  //      旧写法 `if (_dirty) return; if (!state.doc.preview_body) return;` 让**任何编辑过的文档永远进不了池**
  //      （编辑路径一律把 `preview_body` 置 null，见 `state.doc.preview_body = null;` 各处）⇒ 教材场景命中率恒 0，
  //      整篇 parse/render 全是净亏。新判据：只要 `#preview` 里那份 DOM **确实**是由指纹为 `fpNow` 的正文渲染出来的，
  //      它就可以缓存 —— `_markPreviewDomCurrent()` 在渲染收尾时记下 `fpNow`（即"这棵 DOM 的出身"）。
  //      `_dirty` 不再参与：它只代表"有未写盘编辑"，而缓存命中的正确性由 **version + fp 双校验**（见 ②）封底。
  //
  // 本块必须留在既有 IIFE **内部**（要用闭包里的 `state` / `_doc` / `_blockLineMap` / `M` / `P` / `R`；
  // 同文件 12904 行那条教训说的就是这个）。位置选在 IIFE 收尾之前 ⇒ 只推动其后的末尾块（见交付说明）。
  // ══════════════════════════════════════════════════════════════════════════════

  // 本块的位置在 `MemoriaBridge.onReady(...)` 调用点**之后**，而 bridge 在 api 已装好时会**同步**
  // 回调（`bridge.js:62-65`）⇒ 极端情况下（桥存在但缺 `get_ui_settings`）`applyAll()` 会同步跑到
  // `setBackgroundPreload(false)`。故这里一律用 `var`（提升到 undefined，不落 TDZ）：那条路径下
  // 各值是 undefined，函数体自然变成空操作，不会抛 ReferenceError。
  var PREVIEW_CACHE_MAX = 8;         // 兜底（生效值 = 设置 →「显示」→「性能」的「池容量」）：超出按分逐出
  var PREVIEW_CACHE_MAX_LINES = 4000; // 兜底（生效值 = 「缓存行数上限」，默认 8000）：超过该行数的文档不建缓存
  var PRELOAD_MAX_LINES = 1200;      // 兜底（生效值 = 「预渲染行数上限」，默认 4000）：后台预渲染只做中小文档
  var PRELOAD_MAX_TABS = 4;          // 兜底（生效值 = 「预渲染次数上限」，默认 8）：单次会话最多预渲染几个页签
  var _previewDomCache = new Map();  // relPath → { frag, map, ast, version, fp, scrollTop, bytes, prerendered }
  var _preloadTried = new Set();     // 后台预渲染试过的路径（跳过的/失败的都不再重试）
  var _previewDomKey = null;         // `#preview` 里这份 DOM 对应的 { path, version, fp }；null = 当前不可缓存。`fp` = **这棵 DOM 的出身**（2026-10-19）
  var _preloadEnabled = false;       // 「后台预加载」开关（由 display-settings 经 applyAll 通告）
  var _preloadAbort = 0;             // 递增即中止在跑的预渲染
  var _preloadIdle = null;           // requestIdleCallback / setTimeout 句柄
  var _preloadRunning = false;       // 一次空闲回调只做一个页签 ⇒ 用它防重入
  var _preloadDone = 0;              // 本次会话已成功预渲染的页签数（上限 PRELOAD_MAX_TABS）
  var _lastSwitch = { ms: 0, hit: false }; // 最近一次切页签耗时 / 是否走了缓存搬回（诊断用）

  /** 预览 DOM 缓存条目的版本号（后端 `load_document` 追加的 sha256；缺失一律当空串）。 */
  function _docVersionOf(doc) {
    return doc && typeof doc.version === "string" ? doc.version : "";
  }

  /** 正文快速指纹（djb2，32 位）：长度 + 哈希 —— 确认"缓存的预览 DOM 还对应这份正文"。
   *  为什么不直接比字符串：条目里再存一份正文（每页签 ~100 KB）纯属浪费；指纹一趟 O(n) 只花零点几毫秒。 */
  function _bodyFingerprint(body) {
    const s = body == null ? "" : String(body);
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return s.length + ":" + (h >>> 0).toString(36);
  }

  /** 渲染前喂给解析器的正文（与 `renderPreview` 内一致）。**不含图片路径重写** —— 重写结果由文件路径
   *  唯一决定、且已烘进缓存的 DOM，不需要（也不能）参与指纹计算：它依赖模块级的"当前文件目录"，
   *  在页签切换的瞬间那份目录还停在上一篇上。 */
  function _previewSourceBody(doc) {
    if (!doc) return "";
    const body = doc.preview_body || doc.body || "";
    const MP = window.MemoriaMarkdownPreview;
    return MP && typeof MP.normalizeBody === "function" ? MP.normalizeBody(body) : body;
  }

  /** 库内相对路径所在目录（与 `renderPreview` 里算 `currentFileDir` 的口径一致）。 */
  function _relDirOf(relPath) {
    const parts = String(relPath || "").replace(/\\/g, "/").split("/");
    return parts.length > 1 ? parts.slice(0, -1).join("/") + "/" : "";
  }

  /** 缓存条目的粗略内存占用（节点数 × 经验单节点开销 + 文本字符数 × 2）。**只是估算**，用于诊断展示。 */
  function _estimatePreviewBytes(root) {
    let nodes = 0;
    let chars = 0;
    const walk = (el) => {
      for (let n = el.firstChild; n; n = n.nextSibling) {
        nodes++;
        if (n.nodeType === 3) chars += (n.nodeValue || "").length;
        else if (n.nodeType === 1) walk(n);
      }
    };
    walk(root);
    return nodes * 120 + chars * 2;
  }

  /** 丢掉某路径的缓存条目；若它正是"当前可见 DOM 的登记项"则一并注销（该 DOM 不再可作为缓存源）。 */
  function _previewCacheDrop(path) {
    if (!path) return;
    _previewDomCache.delete(path);
    if (_previewDomKey && _previewDomKey.path === path) _previewDomKey = null;
  }

  /** 整体作废：既丢他页签的条目，也注销当前 DOM（换库 / 重命名 / 删除 / 导入后走这条）。 */
  function _previewCacheClear() {
    _previewDomCache.clear(); _previewForgetAll(); // 2026-09-24：换库/重命名/删除/导入 ⇒ 历史画像也一并作废
    _previewDomKey = null;
    _teardownLazyScrollMaterialization();   // 2026-10-22 1b：换库/文件集合变 ⇒ 拆掉滚动物化（观察对象已失效）
  }

  /** 渲染成功后登记「这份 `#preview` DOM 对应哪份文档的哪个版本」。
   *  失败 / 占位（`.-preview-loading`）不算有效渲染 ⇒ 不登记，绝不把错误页缓存起来。
   *
   *  `fp`（2026-10-19）：**这棵 DOM 的出身指纹** —— 必须是 `renderPreview` **喂给解析器的那份正文**的指纹
   *  （`_previewSourceBody(doc)`，含 `normalizeBody`），因为 DOM 就是从它渲染出来的。
   *  `_previewCacheStash` 拿它与"切走那一刻的正文指纹"比对：相等 ⇒ 这份 DOM 没过期，可以缓存；
   *  不等 ⇒ 期间正文变过（编辑 / 撤销）⇒ 不缓存（下一个判据 `fp` 双校验也封得住，两道保险）。 */
  function _markPreviewDomCurrent(doc) {
    const pv = $("#preview");
    const first = pv && pv.firstElementChild;
    if (!first || first.classList.contains("-preview-loading")) { _previewDomKey = null; return; }
    _previewDomKey = {
      path: (doc && doc.path) || state.currentPath,
      version: _docVersionOf(doc),
      fp: doc === state.doc ? _bodyFingerprint(_previewSourceBody(doc)) : "",
    };
  }

  /** 只丢他页签的条目、保留当前 DOM 的可缓存性（语言 / 主题变化走这条：可见 DOM 与恢复后的观感一致）。 */
  function _previewCachePurge() {
    _previewDomCache.clear();
  }

  /**
   * 切走页签前：把当前预览 DOM **整体搬进**缓存。
   * 任一"不安全"条件命中就直接不缓存 —— 切页签慢一次无所谓，显示过期内容是不可接受的。
   */
  function _previewCacheStash(path) {
    if (!path || !state.doc || state.currentPath !== path) return;
    // 2026-10-19：**不再用 `_dirty` / `preview_body` 当判据**（见块首 ③）。改为"这份 DOM 的出身 == 此刻正文"
    // —— 二者都是"渲染/暂存这一刻的正文指纹"，不走 `state.doc.body.split()`，所以**不受 `body` 可能落步影响**：
    // 渲染收尾那一次有 `doc === state.doc` 校验，这里的 `fpNow` 由 `_previewSourceBody` 现算，同源同口径。
    if (state.viewMode === "source") return;                  // 源码视图不渲染预览 ⇒ 预览区内容陈旧
    if (!_previewDomKey || _previewDomKey.path !== path) return;
    const fpNow = _bodyFingerprint(_previewSourceBody(state.doc));
    if (_previewDomKey.fp !== fpNow) return;                   // 渲染之后正文又变过（编辑/撤销）⇒ 这份 DOM 已过期，不缓存
    if (_previewDomKey.version !== _docVersionOf(state.doc)) return;
    if ((state.doc.lines || []).length > _previewCacheLineLimit()) return;
    const preview = $("#preview");
    if (!preview || !preview.firstChild) return; if (window.MemoriaEditSync && typeof window.MemoriaEditSync.flushRepaint === "function") window.MemoriaEditSync.flushRepaint();   // 2026-09-25 AG103：**先把"停手才渲"的那一块渲掉再暂存** —— 否则缓存里存的是"还没归一"的 DOM（下次搬回来会显示 `**粗**` 原文而不是粗体）；2026-09-25 AG97：窗口化回退 ⇒ 预览里**本来就是整篇真 DOM**，切走时不再需要"先量锚点再全量物化"
    // 后台 mermaid 可能还没写回就被切走：清掉一次性标记，下次恢复时重试（否则该块永远停在源码态）
    preview.querySelectorAll("code.language-mermaid").forEach(function (code) {
      const pre = code.parentElement;
      if (pre) delete pre.dataset.mermaidRendered;
    });
    const frag = document.createDocumentFragment();
    while (preview.firstChild) frag.appendChild(preview.firstChild);
    const pane = $("#preview-pane");
    _previewCacheDrop(path);
    _previewDomCache.set(path, {
      frag: frag,
      map: _blockLineMap,
      ast: _doc,
      version: _docVersionOf(state.doc),
      fp: fpNow,   // 2026-10-19：与 `_previewDomKey.fp` 同一口径（上面刚比对过相等）
      scrollTop: pane ? pane.scrollTop : 0,   // 2026-09-25 AG97：窗口化回退 ⇒ 条目里不再存"槽锚点"（`anchor`），只留裸像素（老口径）
      bytes: _estimatePreviewBytes(frag),
      prerendered: false,
    });
    _previewCacheAfterInsert(path, "foreground");
    _previewDomKey = null;   // 预览区已空 ⇒ 等新文档渲染完成后重新登记
  }

  /**
   * P6a 补丁：为预览里的**围栏代码块**恢复语法高亮（render-core 本片不做 token；原 legacy
   * `renderer.js:105-106` 在渲染期内联调用 `MemoriaCodeHighlight.render`）。
   *
   * 复用既有纯函数实现（不复制 token 规则）：
   *   · 目标 `pre.-code-block > code`（块级代码块；render-core/legacy 同形）；
   *   · **跳过** `code.language-mermaid`（mermaid 由 `renderMermaidBlocks` 接管，不能当代码高亮）；
   *   · `Hl.render(text, lang)` 返回**已转义 HTML**：未知语言/异常降级为转义纯文本（与旧路径一致），
   *     只加 `<span>`、不改 `textContent` ⇒ 冻结签名/textNorm 不变；
   *   · 无高亮模块/无代码块 ⇒ 零开销早退。
   * 时点：必须在块挂载后、mermaid/MathJax 后处理之前（与 legacy 渲染期内联高亮同序，
   * 否则 mermaid 已把 `pre` 换掉）。
   * 终局：P6b/P6d 应把高亮下沉到 render-core 的 code_block，本函数随之删除。
   * @returns {number} 实际写入高亮的 code 元素数（诊断用）
   */
  function _applyCodeHighlightToPreview(preview) {
    const Hl = window.MemoriaCodeHighlight;
    if (!preview || !Hl || typeof Hl.render !== "function") return 0;
    const codes = preview.querySelectorAll("pre.-code-block > code");
    if (!codes.length) return 0;
    let n = 0;
    codes.forEach(function (codeEl) {
      const cls = String(codeEl.className || "");
      if (/(^|\s)language-mermaid(\s|$)/.test(cls)) return;   // mermaid 块不参与代码高亮
      const m = /(?:^|\s)language-([^\s]+)/.exec(cls);
      const lang = m ? m[1] : "";
      const text = codeEl.textContent || "";
      try {
        const html = Hl.render(text, lang);
        if (typeof html === "string" && html !== codeEl.innerHTML) { codeEl.innerHTML = html; n++; }
      } catch (e) {
        // 降级：保持已转义纯文本（codeEl 本来就只有 textContent），绝不吞内容
        log("render", "code highlight fallback: " + ((e && e.message) || e));
      }
    });
    return n;
  }

  /** 预览的"静态收尾"：禁止特殊元素编辑 + 行内公式标记。
   *  普通（切走时缓存）条目的这些属性随节点一并保留，无需重做；只有后台预渲染的条目要在恢复时补做。 */
  function _applyPreviewStaticPass(preview, ast) {
    preview.querySelectorAll('mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error, .-lightbox-overlay').forEach(function (el) { el.contentEditable = "false"; });
    const nonEditable = { code_block: 1, math_block: 1, mermaid: 1, table: 1, frontmatter: 1 };
    preview.querySelectorAll(".-src-block").forEach(function (blkEl) {
      const bi = parseInt(blkEl.getAttribute("data--block-index"), 10);
      if (!isNaN(bi) && ast && ast.blocks[bi] && nonEditable[ast.blocks[bi].type]) {
        blkEl.contentEditable = "false";
        blkEl.querySelectorAll("pre, code, table, svg, mjx-container, .-mermaid-container, .-mermaid-error").forEach(function (el) { el.contentEditable = "false"; });
      }
    });
    _tagInlineMathContainers(preview, ast);
  }

  /** 预渲染条目恢复时**只补"行内公式标记"那一半**（2026-09-24 真机读数跟进）。
   *
   * `_applyPreviewStaticPass()` 做两件事：① 把公式/代码/表格/图形标成 `contentEditable="false"`；
   * ② `_tagInlineMathContainers()` 给行内公式的 `mjx-container` 打 `data--inline-math`。
   * ① 在**预渲染阶段就做过了**（`_preloadOne` 里对 holder 调过同一个函数），而 `contentEditable` 会落到
   * **属性**上 ⇒ 随节点一起搬回来 ⇒ 恢复时重跑它是白做。整轮重跑在真机上是 **354 ms**（占那次切换 26%）。
   * ② **必须**留到恢复后：它靠 `mjx-container` 与 AST 的**顺序对应**来认哪一个是行内公式，而预渲染时刻意
   * 不跑 MathJax（没有 `mjx-container`）⇒ 那一半在预渲染阶段本就做不到。
   * ⇒ 恢复时只做 ②。抛错不影响预览（标记只是增强）。 */
  function _retagInlineMathOnly(preview, ast) {
    try { _tagInlineMathContainers(preview, ast); } catch (_) { /* 标记失败不该影响预览 */ }
  }

  /**
   * 命中缓存 ⇒ 把整棵预览 DOM 搬回 `#preview`，并回填 `_blockLineMap` / `window.__blockLineMap` / AST。
   * 返回 true = 已接管本轮渲染（调用方直接返回，跳过 parse / render / 插 DOM / stamp / 等待 MathJax）。
   */
  function _previewCacheRestore(doc) {
    if (!doc || !doc.path || state.currentPath !== doc.path) return false;
    if (state.viewMode === "source") return false;
    const entry = _previewDomCache.get(doc.path);
    if (!entry) return false;
    if (entry.version !== _docVersionOf(doc) || entry.fp !== _bodyFingerprint(_previewSourceBody(doc))) {
      _previewCacheDrop(doc.path);   // 盘上内容或正文变了 ⇒ 丢弃
      return false;
    }
    const preview = $("#preview");
    if (!preview) return false; _beginSwitchTiming();   // 2026-09-24：从这里起给"命中恢复"分段计时（读数里看 `切页签分段`）
    _previewDomCache.delete(doc.path);   // 节点即将回到可见区 ⇒ 条目作废（下次切走时重新存）
    // 换一轮 token：作废在跑的旧排版（MathJax 的 token 守卫会跳过非最新一轮）
    state.previewToken = (state.previewToken || 0) + 1;
    const token = state.previewToken;
    // 本次渲染被整段跳过 ⇒ `renderPreview` 里那段 `setCurrentFileDir` 没机会跑，这里补上；
    // 否则后续编辑的本地图片路径重写仍会按**上一篇**的目录算。
    const MP0 = window.MemoriaMarkdownPreview;
    if (MP0 && MP0.setCurrentFileDir) MP0.setCurrentFileDir(_relDirOf(doc.path));
    _blockLineMap = entry.map || [];
    window.__blockLineMap = _blockLineMap;
    _doc = entry.ast;
    if (M && typeof M.setDoc === "function") M.setDoc(_doc);
    _domBlockSig = _doc.blocks.map(_previewBlockSig);   // 与"刚搬回来的这份 DOM"对齐（同上：块级提交的差分基准）
    preview.innerHTML = "";
    preview.appendChild(entry.frag); _markSwitch("attach");   // 2026-09-25 AG97：窗口化回退 ⇒ 搬回的就是整篇真 DOM（老口径），不再"只挂一窗"
    // 2026-10-22 task-65：缓存搬回 = **换了一轮整篇 DOM** ⇒ 提升调度 epoch、作废上一文档的排队作业；
    //   同时（在挂回后）兜底清一遍 `-math-pending`：缓存期间若有块停在隐藏态，这里直接放出来。
    _lazyPipelineReset("cache-restore");
    // 2026-10-22 1a/问题2：缓存条目可能是惰性化的（占位 + 首屏真块）。恢复后必须对**当前视口**重新物化，
    // 否则切回时视口若落在占位区 ⇒ 白屏。物化范围 = 恢复的 scrollTop 上下 ± 视口×2 高度。
    if (_lazyMaterializeEnabled(doc)) {
      var _lzContainer = preview.querySelector(".-preview-content");
      if (_lzContainer && _lzContainer.querySelector(".-pv-placeholder")) {
        // 重建块元素数组（占位/真块都按 data--block-index 对位），供 _materializeRange 就地更新
        _lazyBlockEls = new Array(_doc.blocks.length);
        var _lzAll = _lzContainer.querySelectorAll(".-src-block[data--block-index]");
        for (var _lzz = 0; _lzz < _lzAll.length; _lzz++) {
          var _ix = parseInt(_lzAll[_lzz].getAttribute("data--block-index"), 10);
          if (_ix >= 0 && _ix < _lazyBlockEls.length) _lazyBlockEls[_ix] = _lzAll[_lzz];
        }
        var _lzPane = $("#preview-pane");
        var _lzScrollTop = (entry.scrollTop != null) ? entry.scrollTop : (_lzPane ? _lzPane.scrollTop : 0);
        var _lzViewH = (_lzPane && _lzPane.clientHeight) || 720;
        // 用平均占位高定位当前视口对应的块区间（估算 + 上下各扩一屏）
        var _lzN = _doc.blocks.length;
        var _lzAvg = Math.max(_pvBlockH(_doc, 0), 64);
        var _lzCenter = Math.floor(_lzScrollTop / _lzAvg);
        var _lzHalf = Math.max(10, Math.ceil((_lzViewH * 2) / _lzAvg));
        var _lzStart = Math.max(0, _lzCenter - _lzHalf);
        var _lzEnd = Math.min(_lzN, _lzCenter + _lzHalf);
        _materializeRange(_lzContainer, _doc, _lzStart, _lzEnd);
        // 注：新物化块的排版由下面既有的 MathJax 排队（stampBlockLines 之后那段，双 rAF + queuePreviewMathTypeset）
        // 覆盖 —— 不必在此单独排（否则双重排队，第二次对已排块空扫）。
      }
    }
    // 2026-10-20 P2：缓存搬回是**整篇路径** ⇒ 用搬回来的 AST 重建 BlockIndex（reset）。
    // 缓存条目里存的是**投影 map**（不存实例，见 _preloadOne G2）⇒ 这里按 AST 重新 upsert 一遍，
    // 成本 O(n)（与搬回 DOM 同量级，且 upsert 已有"值未变不写"守卫 ⇒ 属性多半已对，写入极少）。
    stampBlockLines(preview, _doc, { reset: true });
    const _wantEditable = (window.MemoriaEditHandler && MemoriaEditHandler.editMode) ? "true" : "false"; if (preview.contentEditable !== _wantEditable) preview.contentEditable = _wantEditable; // 2026-09-24：**只在真变时才写** —— 写同值也会让 Blink 走一遍"可编辑性"样式传播（30 万节点真机实测 ~351 ms，正是下面 `static` 那一段）
    _previewDomKey = { path: doc.path, version: entry.version, fp: entry.fp };   // 2026-10-19：`fp` 必须一起搬回（这棵 DOM 的出身仍是 `entry.fp`）⇒ 再切走时还能连续命中
    // 2026-09-24 二次修正：这一行**曾经**调 `_retagInlineMathOnly()`，但它注定空跑 —— 预渲染刻意不跑 MathJax ⇒ 此刻 DOM 里还没有 `mjx-container` 可打标记（而 `contentEditable` 早已随节点搬回）；真正的补标记在下面 MathJax 落定之后那一行（`_markAsyncAfter("mathjax", …)`）。真机读数：这一行曾占 `static` 349 ms（28%）。
    _markSwitch("static");
    postProcessWikilinks();      // 幂等：链接目标集合可能在上次渲染之后才加载完（-link-pending → 实链接）
    _markSwitch("wikilinks");    // ↑ 上面这两步都是**全量 O(n) 扫描**（25 万节点时是主要嫌疑之一）
    bindPreviewLinks();          // 幂等：靠 data--bound 去重
    _markSwitch("bind");
    if (entry.prerendered) {
      // 灯箱 / 图片双击绑定**不是**幂等的 ⇒ 只给预渲染条目补绑（切走时缓存的条目早就绑过，监听随节点保留）
      const MP = window.MemoriaMarkdownPreview;
      if (MP && MP.attachImageLightbox) { try { MP.attachImageLightbox(preview); } catch (_) { /* 可选增强 */ } }
    }
    // 两件"可晚一拍"的事一律后台补做：mermaid（预渲染时跳过 / 被切走时的半成品重试）与 MathJax
    // （缓存时刻可能正排版到一半；已排版好的部分是 mjx-container，再跑一遍只会空扫描一遍）。
    const MP2 = window.MemoriaMarkdownPreview;
    if (MP2 && MP2.renderMermaidBlocks) { try { MP2.renderMermaidBlocks(preview); } catch (_) { /* 失败由错误块兜底 */ } }
    _markSwitch("mermaid");      // ↑ 同步渲染 mermaid（这章有 19 个图）—— 另一个主要嫌疑
    // 2026-09-24 修既有缺口：常规渲染路径在 `app.js:1983` 有"MathJax 打完之后再补一次行内公式标记"，
    // 但**命中缓存这条路提前 return、从没走到那行**。对预渲染条目尤其致命 —— 它的 `mjx-container` 是恢复后才
    // 由 MathJax 生成的 ⇒ 此前**没人给它们打 `data--inline-math`**（双击定位/编辑受影响）。这里按同样的 `token` 守卫补上。
    if (window.MathJax?.typesetPromise) { const _orgH = _switchAbs; const _runMathH = function () { if (token !== state.previewToken) return; const _mp = queuePreviewMathTypeset(preview, token); _markAsyncAfter("mathjax", _mp, _orgH); _mp.then(function () { if (token === state.previewToken) _retagInlineMathOnly(preview, _doc); }); }; if (window.requestAnimationFrame) window.requestAnimationFrame(function () { window.requestAnimationFrame(_runMathH); }); else _runMathH(); }   // 2026-09-24 修既有缺口 + 读数跟进：常规渲染路径在 `app.js:1983` 有"MathJax 打完后补一次行内公式标记"，而**命中缓存这条路提前 return、从没走到那行** ⇒ 预渲染条目的 `mjx-container` 此前没人打 `data--inline-math`；同时把排队挪到**两帧之后**（同冷路径：MathJax 是主线程重活，紧贴恢复末尾排队会挡住第一帧；真机读数里 `mathjax` 打点==`render` 累计就是它在等链）
    _markSwitch("math");         // ↑ 只是**排队**（异步），这里应该接近 0
    showPreviewReport({ ok: true });
    showLinkAuditPreviewHint(doc);
    const pane = $("#preview-pane");
    if (pane && entry.scrollTop) pane.scrollTop = entry.scrollTop;   // 2026-09-25 AG97：窗口化回退 ⇒ 裸像素照旧写（守卫随窗口化一起删除）
    _markSwitch("scroll");       // ↑ 写 `scrollTop` 会**强制同步布局**（25 万节点时可能是大头）
    // 2026-09-24：**异步标记** —— 双 rAF 拆成两段：`frame1` = "渲染时机到了"（若**主线程**被别的东西占住，这里就会晚 ——
    // 真机读数 `paint 1788` 而脚本只花 335 ms ⇒ 必须先分清"帧慢"还是"线程被别人占"）；`paint` = 这一帧真的画完
    // ⇒ **两者之差**才是帧自己的样式/布局/绘制耗时。起点**在注册时**捕获（原来在回调里读 `_switchAbs`，恒等于自己 ⇒ 旧一轮永远丢不掉）。
    if (window.requestAnimationFrame) { const _org = _switchAbs;
      window.requestAnimationFrame(function () {
        _markAsync("frame1", _org); window.requestAnimationFrame(function () { _markAsync("paint", _org); });
      });
    }
    _lastSwitch.hit = true; _previewCacheTouch(doc.path); // 2026-09-24 追加：命中即刷新该条画像（次数 + 新鲜度 + 老化戳）
    _preloadSchedule();
    return true;
  }

  /** 预览缓存的诊断快照（`MemoriaApp.previewCacheStats()`；用于设置页文案取证与人工排查）。 */
  function previewCacheStats() {
    let bytes = 0;
    for (const entry of _previewDomCache.values()) bytes += entry.bytes || 0;
    return {
      entries: _previewDomCache.size,
      bytes: bytes,
      paths: Array.from(_previewDomCache.keys()),
      enabled: _preloadEnabled,
      prerendered: _preloadDone,
      lastSwitchMs: _lastSwitch.ms,
      lastSwitchHit: _lastSwitch.hit,
    };
  }

  // ── B 档：后台预渲染（设置 →「显示」→「性能」开关；关掉时下面的函数全是空操作） ──

  function _preloadCancelIdle() {
    if (_preloadIdle == null) return;
    if (typeof window.cancelIdleCallback === "function") { try { window.cancelIdleCallback(_preloadIdle); } catch (_) { /* 句柄可能已消费 */ } }
    else clearTimeout(_preloadIdle);
    _preloadIdle = null;
  }

  /** 中止在跑的预渲染（切页签 / 开始编辑 / 关开关 / 换库都走这里）。 */
  function _preloadStop(reason) {
    const wasPending = _preloadIdle != null || _preloadRunning;   // 只在真的打断了一次作业时才打日志（markDirty 每敲一键都会进来）
    _preloadAbort++;
    _preloadCancelIdle();
    if (reason && wasPending) syncLog("[preload] 中止：", reason);
  }

  /** 换库时复位预渲染会话状态（已预渲染计数与"试过"清单都属于上一本库）。 */
  function _preloadResetForNewKb() {
    _preloadStop("kb-change");
    _preloadTried.clear();
    _preloadDone = 0;
  }

  /** 下一个可预渲染的目标：**候选池按"预期收益"排序**取第一（2026-09-24 起）。
   *
   * **候选池有两个来源**（见 `_preloadPool`）：① 打开着的页签（非当前、未缓存、未试过）；
   * ② **导航预测里收益最高的那几个文件 —— 可以是还没打开的**（第二层的意义就在这儿：不是重排页签，
   * 而是把"你下一步最可能看的那一章"先渲染好）。规则见 `docs/design/preview-render-pipeline.md` §3.5。
   *
   * 排序：① 有导航模型 ⇒ `S(文件) × T̂(加载耗时)`（慢文件更要提前做，快文件不值得抢 CPU）；
   * ② 模型没热（样本 < `MIN_SAMPLES`）或模块缺席 ⇒ 回退**启发式**（目录相邻 > 最近打开 > 页签顺序），
   * 同样乘 `T̂`；③ 全都排不出分 ⇒ **保持原来的页签顺序** ⇒ 行为与接线前一致，不会更差。
   * 排序细节见 `_preloadRanked()` / `_preloadGain()`。 */
  function _nextPreloadCandidate() {
    const pool = _preloadPool();
    if (!pool.length) return null;
    return _preloadRanked(pool)[0] || pool[0];
  }

  /** 本轮渲染收尾后：有空闲就排一次"预渲染一个页签"的作业。 */
  function _preloadSchedule() {
    if (!_preloadEnabled || _preloadIdle != null || _preloadRunning || !_preloadDocumentOpen()) return;
    if (_preloadDone >= _preloadTabLimit()) return;
    if (_nextPreloadCandidate() === null) return;
    const fire = function () { _preloadIdle = null; _preloadTick(); };
    const arm = function () { if (_preloadIdle !== -1) return; if (typeof window.requestIdleCallback === "function") _preloadIdle = window.requestIdleCallback(fire, { timeout: 4000 }); else _preloadIdle = setTimeout(fire, 600); };   // 2026-09-24 真机读数：预渲染是**整篇 parse + render**（约 1 s 的**主线程长任务**），而原来 `timeout` 只有 1200 ⇒ 浏览器还没真正空闲就把它强行拉起来，正好压在**刚切过去的那一帧**上（`paint 1788 ms` 而脚本只花 335 ms）。⇒ ① 先等**两帧**（下面 rAF）再排，② timeout 放宽到 4 s：宁可少做几次，也别抢用户这一帧。**③ 首行那个守卫是必须的**：`cancelIdleCallback` 取消不了已经排进 rAF 的那一步 ⇒ 切页签时 `_preloadStop` 把 `_preloadIdle` 置 null 后，这个 `arm` 仍会被 rAF 调到；没有守卫时它照样排一次空闲回调 ⇒ 切完之后又冒出一次 ~1 s 的主线程长任务（真机：`frame1` 迟至 1504 ms、期间**滚轮/输入全冻**）
    _preloadIdle = -1; if (window.requestAnimationFrame) window.requestAnimationFrame(function () { window.requestAnimationFrame(arm); }); else arm();   // `-1` 是"arm 排队中"的占位（arm 要两帧后才登记真句柄），否则窗口期内重入调度会重复排队
  }

  /** 一个空闲回调只做一个页签：做完再排下一个，任何时候被中止都立刻停手。 */
  async function _preloadTick() {
    if (!_preloadEnabled) return;
    if (_dirty || _renderingPreview || document.hidden || !_preloadDocumentOpen()) return;   // 正在编辑 / 正在渲染 / 窗口不可见 / **文件还没打开**（规则见 `_preloadDocumentOpen`）⇒ 本轮放弃，等下一次渲染收尾再排
    const path = _nextPreloadCandidate();
    if (!path) return;
    _preloadTried.add(path);
    const token = _preloadAbort;
    _preloadRunning = true;
    let ok = false;
    try { ok = await _preloadOne(path); } catch (_) { ok = false; }
    _preloadRunning = false;
    if (_preloadAbort !== token || !_preloadEnabled) return;   // 期间被中止 ⇒ 不再续排
    if (ok) _preloadDone++;
    _preloadSchedule();
  }

  /**
   * 预渲染一个页签：解析 → 渲染 → 打行号 → 静态收尾，全部在**脱离文档**的容器里完成，
   * 结束后整棵树搬进缓存条目。全程不碰 `#preview` / `#editor` / 撤销栈 / 滚动位置。
   * 异步部分（mermaid / MathJax / 图片灯箱）留给恢复时补做 —— 见 `_previewCacheRestore`。
   */
  async function _preloadOne(path) {
    let res;
    try { res = await call("load_document", path); } catch (_) { return false; }
    // await 期间用户可能已切到该页签 / 开始编辑 / 关掉开关 / 关掉该页签 ⇒ 立即放弃（不写缓存、不打扰可见界面）
    if (!_preloadEnabled || path === state.currentPath || _dirty) return false;
    if (!_preloadStillWanted(path)) return false;
    if (!res || res.status !== "ok" || !(res.blocks && res.blocks.length)) return false;
    if ((res.lines || []).length > _preloadLineLimit()) return false;
    if (_previewDomCache.has(path)) return true;   // 已被普通切换缓存过
    if (!P || !M || !_rcRenderer()) return false;

    const MP = window.MemoriaMarkdownPreview;
    const holder = document.createElement("div");
    const savedDoc = state.doc;
    const savedMap = _blockLineMap;
    const savedMapperDoc = typeof M.getDoc === "function" ? M.getDoc() : null;
    const savedDir = _relDirOf(state.currentPath);
    const rawBody = _previewSourceBody(res);
    const fp = _bodyFingerprint(rawBody);
    let ast = null;
    let map = null;
    // G2/A14（Lead 裁决 2026-10-20）：预加载的是**另一篇文档** ⇒ 用**独立临时实例**投射，
    // **绝不碰主实例 BI**（否则会把当前文档的索引清成这一篇的）。用完即弃：finally 置 null、不挂全局、不进缓存条目。
    let tempIndex = window.MemoriaBlockIndex.createBlockIndex();
    try {
      if (MP && MP.setCurrentFileDir) MP.setCurrentFileDir(_relDirOf(path));
      ast = P.parse(rewriteMdImagePaths(rawBody));
      // P6a：预渲染缓存与普通渲染同源（render-core），不得再走 legacy `R.render`
      holder.appendChild(_rcRenderer().renderDocument(ast).container);
      // 已挂载；高亮与普通渲染同口径（否则预渲染缓存恢复会搬回无高亮 DOM）
      _applyCodeHighlightToPreview(holder);
      // 行号映射：`stampBlockLines` 读的是 `state.doc.body`（**当前**文档）⇒ 临时换成被预渲染的那份。
      // 本段同步执行（解析 / 渲染 / 打标记都不 await）⇒ 不会与任何渲染或编辑交错；finally 里立刻还原。
      state.doc = res;
      stampBlockLines(holder, ast, { index: tempIndex });
      map = tempIndex.blocks().map(function (h) { return { startLine: h.srcLineStart - 1, endLine: h.srcLineEnd - 1 }; });
      _applyPreviewStaticPass(holder, ast);
    } catch (_) {
      return false;
    } finally {
      state.doc = savedDoc;
      _blockLineMap = savedMap;
      tempIndex = null;                      // ★ 用完即弃（显式断引用，不等 GC）
      if (typeof M.setDoc === "function") M.setDoc(savedMapperDoc);
      if (MP && MP.setCurrentFileDir) MP.setCurrentFileDir(savedDir);
    }
    const frag = document.createDocumentFragment();
    while (holder.firstChild) frag.appendChild(holder.firstChild);
    _previewCacheDrop(path);
    _previewDomCache.set(path, {
      frag: frag,
      map: map,
      ast: ast,
      version: _docVersionOf(res),
      fp: fp,
      scrollTop: 0,
      bytes: _estimatePreviewBytes(frag),
      prerendered: true,
    });
    _previewCacheAfterInsert(path, "preload");
    return true;
  }

  /** 「后台预加载」开关（设置 →「显示」→「性能」）：由 display-settings 的 `applyAll()` 每次设置变更时通告。 */
  function setBackgroundPreload(on) {
    const next = !!on;
    if (next === _preloadEnabled) return;
    _preloadEnabled = next;
    if (!next) { _preloadStop("toggle-off"); return; }
    _preloadAbort++;          // 新会话：让上一轮可能残留的续排失效
    _preloadTried.clear();
    _preloadDone = 0;
    _preloadSchedule();
  }

  window.MemoriaApp.setBackgroundPreload = setBackgroundPreload;   // 2026-09-25 AG97：`pvPostWikilinks` / `pvBindLinks` 两个导出点随窗口化一起删除（它们只为"窗口内就地补链接"服务）
  window.MemoriaApp.previewCacheStats = previewCacheStats;

  // ══ 2026-10-22 测试专用接口：强制把全文占位块物化为真块（**给门禁/回归用，不是生产路径**）══
  // 为什么需要：冻结门禁按"DOM 里实际存在的元素"统计内容（公式/图片/表格/语言），而惰性模式下
  //   绝大多数块只是占位 div ⇒ 门禁会把"没物化"误判成"渲染丢了内容"（typesetMathBlocks 270→2 等）。
  //   **更推荐**门禁直接用 `window.__MEMORIA_LAZY = false` 走全量生产路径（钩子优先于小文档阈值），
  //   本接口留给"必须验证惰性路径本身"的场景。
  //
  // ⚠️ 2026-10-22 重写（Lead 实测旧版在 3111 块上冻结 20 分钟）：
  //   旧版一次同步 `_materializeRange(0, N)` ⇒ 数千块同步建 DOM + 逐块 replaceWith/min-height/IO.observe
  //   ⇒ 主线程长时间不可响应（连 CDP 都不回）。**这与惰性物化要避免的正是同一件事**。
  //   现在：**分批（每批 `MATERIALIZE_BATCH` 块）+ 批间 `setTimeout(0)` 让出**，任何时候不阻塞 >100ms；
  //   支持中断（`state.previewToken` 变 ⇒ 停止，resolve 已物化数）；幂等（无占位 ⇒ resolve(0)）。
  var MATERIALIZE_BATCH = 200;
  window.__MEMORIA_MATERIALIZE_ALL = function () {
    try {
      var preview = $("#preview");
      var cc = preview ? (preview.querySelector(".-preview-content") || preview) : null;
      if (!cc || !_doc || !_doc.blocks) return Promise.resolve(0);
      // 2026-10-22 1c：这是**门禁专用**的"强制全量物化"路径 ⇒ 全程禁用工作集淘汰，
      //   否则门禁按 DOM 统计内容时会把"被淘汰的块"误判成渲染缺失。下次 `_buildLazyPreview` 会重置。
      _lazyEvictSuspended = true;
      _lazyEvictQueuedPriority = 0;
      if (!cc.querySelector(".-pv-placeholder")) return Promise.resolve(0);   // 幂等：已全物化/非惰性

      var total = _doc.blocks.length;
      var token = state.previewToken;
      var done = 0;

      // 一批：物化 [from, to) 里有占位的那部分（_materializeRange 自己跳过已物化的）
      function runBatch(from) {
        if (token !== state.previewToken) {                       // ③ 中断：文档已换 ⇒ 停止
          log("lazy", "__MEMORIA_MATERIALIZE_ALL aborted by token: materialized=" + done + "/" + total);
          return Promise.resolve(done);
        }
        if (from >= total) {
          // 全部物化完成 ⇒ 一次性排版（MathJax 自身是异步分片的，且此时只排一次）
          var p = Promise.resolve();
          if (done && window.MathJax && typeof window.MathJax.typesetPromise === "function") {
            p = queuePreviewMathTypeset(preview, token) || Promise.resolve();
          }
          return p.then(function () {
            try { if (token === state.previewToken) _tagInlineMathContainers(preview, _doc); } catch (_) {}
            try { _applyCodeHighlightToPreview(preview); } catch (_) {}
            try { postProcessWikilinks(); bindPreviewLinks(); } catch (_) {}
            var remain = cc.querySelectorAll(".-pv-placeholder").length;
            log("lazy", "__MEMORIA_MATERIALIZE_ALL done: materialized=" + done + " remainingPlaceholders=" + remain + " blocks=" + total);
            return done;
          });
        }
        var to = Math.min(total, from + MATERIALIZE_BATCH);
        var made = _materializeRange(cc, _doc, from, to);
        done += made.length;
        log("lazy", "__MEMORIA_MATERIALIZE_ALL: materialized=" + done + "/" + total);
        // ② 批间让出（宏任务边界 ⇒ 帧/输入有机会跑）
        return new Promise(function (r) { setTimeout(r, 0); }).then(function () { return runBatch(to); });
      }

      return runBatch(0);
    } catch (e) {
      log("lazy", "__MEMORIA_MATERIALIZE_ALL ERR " + ((e && e.message) || e));
      return Promise.resolve(0);
    }
  };

  // 语言 / 主题变了：已缓存的他页签预览里含本地化文案与 mermaid 主题色 ⇒ 整体作废重渲染
  window.addEventListener("memoria:langchange", function () { _previewCachePurge(); });
  window.addEventListener("memoria:themechange", function () { _previewCachePurge(); });

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-24 追加：预览池的**智能替换**（评分 + 老化 + 后台预渲染的入场闸）
  //
  // 人：「后台预加载的加载池需要有一个智能替换机制，我们给资源计算优先级……优先级最低的优先被替换，
  // 新入池的资源优先级都重新初始化……权重参数应该在设置内「性能」板块调整，显示计算公式，支持恢复默认」。
  // **模型与公式的来处**（GDSF 的老化 / TinyLFU 的入场闸 / Hyperbolic 的按占用折算）见
  // `js/preview-cache-policy.js` 文件头；本块只负责把它接到**真实的池**上。
  //
  // 三条边界（不新造机制）：
  //   ① 算法是**纯函数**（`window.MemoriaPreviewPolicy`）⇒ 可单独测、可单独解释；它缺席时
  //      `_previewCacheEvict()` **回落**到原来的"按插入序逐出最旧"（宁可没优化，也不许坏）；
  //   ② 画像（`hits` / `lastOpenAt` / `loadMs` / 老化戳）按**路径**存活，**不随"出池"清掉** ——
  //      切走再切回本来就是一次"出池 → 入池"，若跟着清零，`hits` 恒为 0、频次项就废了（评分会退化成
  //      只按耗时/占用排序）。"新入池重新初始化"指的是**首次见到这个路径**（`_previewForgetAll()` 之后同理）；
  //   ③ 人**当前看着**的页签走 `"foreground"` ⇒ **不进入场闸**（它正被付代价，不该被投机项挤掉）；
  //      只有后台预渲染那条**投机**路径走 `"preload"` ⇒ 过闸，不够格就地丢掉（而不是先挤掉别人再留下自己）。
  //
  // 位置：仍在既有 IIFE **内部**（要用闭包里的 `_previewDomCache` / `_previewCacheDrop` 等），
  // 追加在最末 ⇒ 只把 `})();` 往后推一行，其上所有引用零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  var PREVIEW_META_MAX = 64;     // 画像条数上限：用户可能翻过几百个文件，画像不能无限堆积
  var _previewMeta = new Map();  // relPath → { hits, lastOpenAt, loadMs, agingStamp }
  var _previewEvicts = 0;        // 池内累计淘汰次数（老化那个离散时钟；`_previewForgetAll` 归零）
  var _previewPendingLoad = 0;   // 最近一次**冷加载**的实测耗时（`_previewCacheNoteLoad` 记，切走时挂到画像上）
  var _previewPolicy = null;     // display-settings 通告的已清洗策略；null ⇒ 用策略模块的 DEFAULTS

  /** 策略模块（缺席 ⇒ null，各调用方自行回落）。 */
  function _previewPolicyMod() { return window.MemoriaPreviewPolicy || null; }

  /** 当前生效的策略（模块缺席 ⇒ null ⇒ 各调用方用旧常量兜底）。 */
  function _previewPolicyOf() { return _previewPolicy || (_previewPolicyMod() ? _previewPolicyMod().DEFAULTS : null); }

  /** 从策略里取一个**正整数**上限（缺失/非法 ⇒ 用兜底常量 ⇒ 策略模块缺席时行为与接线前一致）。 */
  function _previewLimitOf(key, fallback) {
    const p = _previewPolicyOf();
    const n = p ? Number(p[key]) : NaN;
    return Number.isFinite(n) && n >= 1 ? Math.round(n) : fallback;
  }

  /** 池的**有效**条数上限（设置可调；缺失/非法 ⇒ 旧常量 `PREVIEW_CACHE_MAX`）。 */
  function _previewLimit() { return _previewLimitOf("previewCacheMax", PREVIEW_CACHE_MAX); }

  /** 生效的**缓存行数上限**（超过就不建缓存条目：单页 DOM 太大，省下的时间抵不上内存）。 */
  function _previewCacheLineLimit() { return _previewLimitOf("previewCacheMaxLines", PREVIEW_CACHE_MAX_LINES); }

  /** 生效的**预渲染行数上限**（超过就不预渲染：大文档的渲染本身就是一次长任务）。 */
  function _preloadLineLimit() { return _previewLimitOf("preloadMaxLines", PRELOAD_MAX_LINES); }

  /** 生效的**单会话预渲染次数上限**（避免打开大库后长时间占着 CPU）。 */
  function _preloadTabLimit() { return _previewLimitOf("preloadMaxTabs", PRELOAD_MAX_TABS); }

  /** 取（或**首次创建**）某路径的画像 —— 首次创建即"新入池的优先级重新初始化"（全零 + 当前老化戳）。 */
  function _previewMetaOf(path) {
    let meta = _previewMeta.get(path);
    if (meta) return meta;
    meta = { hits: 0, lastOpenAt: Date.now(), loadMs: 0, agingStamp: _previewEvicts };
    _previewMeta.set(path, meta);
    if (_previewMeta.size > PREVIEW_META_MAX) {
      // 画像只服务于"哪些页签值得留" ⇒ 超限就丢**最久没被碰到**的那个（它多半早不在池里了）
      let oldestPath = null;
      let oldestAt = Infinity;
      for (const [p, m] of _previewMeta) {
        if (p !== path && m.lastOpenAt < oldestAt) { oldestAt = m.lastOpenAt; oldestPath = p; }
      }
      if (oldestPath) _previewMeta.delete(oldestPath);
    }
    return meta;
  }

  /** 整体作废画像（换库 / 重命名 / 删除 / 导入，由 `_previewCacheClear()` 调）。 */
  function _previewForgetAll() {
    _previewMeta.clear();
    _previewEvicts = 0;
    _previewPendingLoad = 0;
  }

  /** 命中缓存 ⇒ 刷新该条画像：次数 +1、新鲜度归零、老化戳跳到当前淘汰总数。 */
  function _previewCacheTouch(path) {
    if (!path) return;
    const meta = _previewMetaOf(path);
    meta.hits += 1;
    meta.lastOpenAt = Date.now();
    meta.agingStamp = _previewEvicts;
  }

  /** 记下最近一次**冷加载**（未命中）的实测耗时；切走入库时由 `_previewCacheAfterInsert` 挂到画像上。 */
  function _previewCacheNoteLoad(ms) {
    const value = Number(ms);
    if (Number.isFinite(value) && value > 0) _previewPendingLoad = value;
  }

  /** 池内条目 → 交给算法的输入（`bytes` 取条目、其余取画像；可排除某条，入场闸要排除候选自己）。 */
  function _previewPoolEntries(exceptPath) {
    const out = [];
    for (const [path, entry] of _previewDomCache) {
      if (path === exceptPath) continue;
      const meta = _previewMeta.get(path);
      out.push({
        path: path,
        bytes: (entry && entry.bytes) || 0,
        hits: meta ? meta.hits : 0,
        lastOpenAt: meta ? meta.lastOpenAt : 0,
        loadMs: meta ? meta.loadMs : 0,
        agingStamp: meta ? meta.agingStamp : _previewEvicts,
      });
    }
    return out;
  }

  /** 按当前策略淘汰到上限。**策略模块缺席 ⇒ 回落"按插入序逐出最旧"**（与接线前的行为一致）。 */
  function _previewCacheEvict() {
    const mod = _previewPolicyMod();
    const limit = _previewLimit();
    while (_previewDomCache.size > limit) {
      if (!mod) {
        _previewCacheDrop(_previewDomCache.keys().next().value);
        continue;
      }
      const victim = mod.pickVictim(_previewPoolEntries(), _previewPolicyOf(), Date.now(), _previewEvicts);
      if (!victim) return;
      _previewEvicts += 1;              // 老化时钟：淘汰一次上浮一格（所有仍驻留的条目相对地更"旧"了）
      _previewCacheDrop(victim.path);
    }
  }

  /**
   * 新条目入池后的统一收口：**先落画像，再决定去留**。
   * `kind` = `"foreground"`（人看过的页签被切走 ⇒ 无条件入池）或 `"preload"`（后台预渲染 ⇒ 过入场闸）。
   */
  function _previewCacheAfterInsert(path, kind) {
    const meta = _previewMetaOf(path);
    meta.lastOpenAt = Date.now();
    meta.agingStamp = _previewEvicts;
    if (kind === "foreground") {
      if (_previewPendingLoad > 0) {
        // EWMA(α=0.3)：一次异常快/慢的加载不该把它钉死
        meta.loadMs = meta.loadMs > 0 ? meta.loadMs * 0.7 + _previewPendingLoad * 0.3 : _previewPendingLoad;
      }
    }
    // 无论哪条路都清掉待挂样本：它不是这个页签的（预渲染路径**没有**冷加载计时点，如实不编数）
    _previewPendingLoad = 0;
    const mod = _previewPolicyMod();
    const policy = _previewPolicyOf();
    if (kind === "preload" && mod && policy && policy.perfAdmission) {
      const entry = _previewDomCache.get(path);
      const candidate = {
        path: path,
        bytes: (entry && entry.bytes) || 0,
        hits: meta.hits,
        lastOpenAt: meta.lastOpenAt,
        loadMs: meta.loadMs,
        agingStamp: meta.agingStamp,
      };
      const pool = _previewPoolEntries(path);   // 排除候选自己，否则"跟比自己"永远不成立
      if (!mod.admits(candidate, pool, policy, Date.now(), _previewEvicts, _previewLimit())) {
        _previewCacheDrop(path);                // 不够格 ⇒ 就地丢掉（不挤别人）
        return;
      }
    }
    _previewCacheEvict();
    // 后台预渲染的条目**确实留在池里**才算"预渲染过" ⇒ 用它当预测命中率的分母（§3.5 的线上读数）
    if (kind === "preload" && _previewDomCache.has(path) && window.MemoriaNavPredictor
      && typeof window.MemoriaNavPredictor.notePreloaded === "function") {
      try { window.MemoriaNavPredictor.notePreloaded(path); } catch (_) { /* 预测器可选 */ }
    }
  }

  /** 「性能」设置通告：清洗 + 立即生效（池上限可能被调小 ⇒ 当场收口）。
   *
   * 门槛**变了**（尤其"预渲染行数上限"放大）⇒ 还要让之前被门槛挡下的页签**重新有机会**预渲染：
   * `_preloadTried` 是"试过就不再试"的清单，不清掉的话用户放宽门槛后**什么都看不到**
   * （真机反馈"教材第 8 章切得慢"时，它整章就是被 1200 行的门槛挡在门外、并已记进该清单）。 */
  function setPreviewCachePolicy(policy) {
    const mod = _previewPolicyMod();
    const next = mod ? mod.sanitize(policy) : (policy || null);
    const changed = JSON.stringify(next) !== JSON.stringify(_previewPolicy);
    _previewPolicy = next;
    _previewCacheEvict();   // 池上限可能被调小 ⇒ 当场收口
    // 导航预测器（§3.5）与缓存策略同一份设置来源 ⇒ 顺手转发（它自己会清洗）
    if (window.MemoriaNavPredictor && typeof window.MemoriaNavPredictor.setPolicy === "function") {
      try { window.MemoriaNavPredictor.setPolicy(policy || {}); } catch (_) { /* 预测器可选 */ }
    }
    // 2026-09-25 AG97：窗口化（K4a）已整体回退 —— 这里不再往窗口模块转发任何开关（下列两行原地保留以维持行号）
    // （原「窗口化总开关」转发点，已删）
    // （原窗口化开关的 `setEnabled` 调用点，已删）
    if (changed) {
      _preloadTried.clear();
      _preloadDone = 0;
      _preloadSchedule();
    }
  }

  /** 预测目标预渲染的**上限**（只做收益最高的这几个；再多就是烧 CPU 赌运气，与其猜不如让位给页签）。 */
  var PRELOAD_PREDICT_MAX = 2;
  /** 累计清掉的过期投机条目（读数用）。 */
  var _preloadPrunedStale = 0;

  /** 「文件已打开」：当前文档已加载完成，且处于三种视图之一（预览 / 源码 / 分栏）。
   *
   * **规则（人 2026-09-24）**：「预渲染要在文件（预览或者源码或者分栏模式）打开之后」——
   * 打开过程中抢 CPU 会拖慢你正要看的这一份；没有打开任何文件时更不该预渲染。
   * 与视图模式**无关**（三种都算"打开"），只要求"这份文档确实是当前文档、且视图已就绪"。 */
  function _preloadDocumentOpen() {
    if (!state.currentPath) return false;
    const doc = state.doc;
    if (!doc || doc.path !== state.currentPath) return false;
    const mode = state.viewMode;
    return mode === "preview" || mode === "source" || mode === "split";
  }

  /** 导航预测给出的、**值得提前渲染**的文件（`收益 = 概率分 × T̂`，降序；**可含还没打开的**）。
   *  排除已在池的与当前文件（那些没必要再预渲染）。这是第二层的意义所在：把"你下一步要看的那一章"先渲染好。 */
  function _preloadPredictedFiles() {
    const nav = window.MemoriaNavPredictor;
    if (!nav || typeof nav.predictNext !== "function") return [];
    let predicted = null;
    try {
      const exclude = new Set(_previewDomCache.keys());
      if (state.currentPath) exclude.add(state.currentPath);
      predicted = nav.predictNext({ exclude: exclude });
    } catch (_) { return []; }
    if (!predicted || !predicted.length) return [];
    const open = new Set();
    for (const tab of state.openTabs || []) if (tab && tab.path) open.add(tab.path);
    return predicted
      .map(function (item) { return { path: item.file, gain: _preloadGain(item.file, item.score) }; })
      .filter(function (item) { return item.gain > 0 && !open.has(item.path) && item.path !== state.currentPath; })
      .sort(function (a, b) { return b.gain - a.gain; });
  }

  /** 预渲染**候选池**（`_preloadRanked` 排序前的集合）：① 打开着的页签 + ② **预测目标**（限 `PRELOAD_PREDICT_MAX` 个）。
   *  两条来源都要过"未在池、未试过"这关；预测那条**可以不在页签里**（第二层要提前渲染"你还没打开的下一章"）。 */
  function _preloadPool() {
    const pool = [];
    for (const tab of state.openTabs || []) {
      const path = tab && tab.path;
      if (!path || path === state.currentPath) continue;
      if (_previewDomCache.has(path) || _preloadTried.has(path)) continue;
      pool.push(path);
    }
    for (const item of _preloadPredictedFiles().slice(0, PRELOAD_PREDICT_MAX)) {
      if (pool.indexOf(item.path) >= 0) continue;
      if (_previewDomCache.has(item.path) || _preloadTried.has(item.path)) continue;
      pool.push(item.path);
    }
    return pool;
  }

  /** `_preloadOne` 的守卫：这个路径**还值得**预渲染吗（打开着的页签，**或仍在预测目标里**）。
   *  `await load_document` 期间用户可能换了文件 / 关了页签 / 预测变了 ⇒ 那些就不该再往池里塞。 */
  function _preloadStillWanted(path) {
    if (!path) return false;
    for (const tab of state.openTabs || []) if (tab && tab.path === path) return true;
    return _preloadPredictedFiles().some(function (item) { return item.path === path; });
  }

  /** **规则（人 2026-09-24）**：当前显示的文件切换之后，把**投机的预渲染产物**与**新的候选集比对**，删掉不再需要的，避免滞留。
   *
   * - 只动 `prerendered === true` 的条目 —— 那是"我们替你提前渲染、你还没看过"的**投机产物**；
   *   人**真正打开过**的条目在 `_previewCacheStash` 里被写成 `prerendered: false` ⇒ **一律保留**（那是第一层的正经缓存）。
   * - 保留集 = `openTabs` ∪ **仍被预测的文件** ⇒ 只有"预测变了 / 那块地不再要了"的才会被清 —— 正是"避免滞留"。
   * - 返回清掉的条数（`previewCacheScores().stalePruned` 累计值供读数）。 */
  function _preloadPruneStale() {
    let dropped = 0;
    if (!_previewDomCache.size) return dropped;
    const keep = new Set();
    for (const tab of state.openTabs || []) if (tab && tab.path) keep.add(tab.path);
    if (state.currentPath) keep.add(state.currentPath);
    for (const item of _preloadPredictedFiles()) keep.add(item.path);
    for (const path of Array.from(_previewDomCache.keys())) {
      const entry = _previewDomCache.get(path);
      if (!entry || !entry.prerendered) continue;   // 只清投机产物，绝不碰人看过的那条
      if (keep.has(path)) continue;
      _previewCacheDrop(path);
      dropped += 1;
    }
    if (dropped) _preloadPrunedStale += dropped;
    return dropped;
  }

  /** **外层阶段计时**：`openFile` 全程（点击 → 状态栏收尾）的五段，与上面的「切页签分段」互补。
   *
   * 真机读数（2026-09-24）：`最近一次切页签 1571 ms`，而命中恢复的分段之和只有 **428 ms** ⇒
   * **大头在恢复之外**。`_lastSwitch.ms` 的起点在 `openFile` 开头（`_t0Switch`），所以那 1571 覆盖的是
   * 整条打开流水线：切走时的 stash（含 `_estimatePreviewBytes` 整树遍历）/ `load_document` 的 IPC 与后端解析 /
   * **源码编辑器整篇填充** + 知识点列表 / 预览渲染（含「切页签分段」）/ 状态栏与图审计收尾。
   * 只靠"命中恢复分段"会把这 1143 ms 误读成"预览的问题" ⇒ 必须把全程也拆开。
   *
   * 口径：存的是**距 `_t0Switch` 的绝对增量**（读数侧再做两两相减 ⇒ 每段自己的耗时）。 */
  var _switchAbs = 0;
  var _switchPhases = null;

  function _markPhase(name) {
    if (!_switchPhases || !_switchAbs) return;
    const now = (window.performance && performance.now) ? performance.now() : Date.now();
    _switchPhases[name] = Math.round(now - _switchAbs);
    _lastSwitch.phases = _switchPhases;
  }

  // ── **异步标记**（2026-09-24）：同步分段/阶段抓不到的那些时刻 ────────────────────────────────
  //
  // 真机读数：`切页签阶段 view 1104 ms`，但恢复内的同步分段只有 **375 ms** ⇒ 剩 729 ms
  // **既不在恢复的同步代码里、也不在 MathJax 里**（`_waitRenderSettled` 只等同步那一轮）。
  // 唯一解释：**浏览器对新挂上来的 30 万节点做布局/绘制的时间，落在两次 `await` 之间**。
  // ⇒ 用双 `requestAnimationFrame`（≈"这一帧含布局绘制真的画完了"）与"MathJax promise 落定"两个**异步**标记来量它。
  // 口径：都是**相对本次切换起点**（`_switchAbs`）的绝对 ms；旧一轮的异步回调（起点已不同）**丢弃**，避免读成怪数。
  var _switchAsync = null;

  function _asyncStamp(name, origin) {
    if (!origin || origin !== _switchAbs) return;
    const now = (window.performance && performance.now) ? performance.now() : Date.now();
    if (!_switchAsync) _switchAsync = {};
    _switchAsync[name] = Math.round(now - origin);
    _lastSwitch.async = _switchAsync;
  }

  function _markAsync(name, origin) {   // 2026-09-24：起点**由调用方传入**（注册时捕获）—— 原来在这里读 `_switchAbs` 恒等于自己，上面那条"旧一轮丢弃"守卫永远不生效
    _asyncStamp(name, origin == null ? _switchAbs : origin);
  }

  function _markAsyncAfter(name, promise, origin) {   // `origin` 可选：**注册时**捕获的起点（见下）。不传 ⇒ 用当前起点
    if (!promise || typeof promise.then !== "function") return; if (origin == null) origin = _switchAbs;
    promise.then(function () { _asyncStamp(name, origin); }).catch(function () { /* 排版失败不该影响读数 */ });
  }

  /** 「缓存命中」那次切页签的**分段计时**（2026-09-24 追加）。
   *
   * **动机（真机读数）**：池里 2 条、每条约 **25 万节点**，读数给出"走了缓存搬回**还要 360 ms**"。
   * 命中已经跳过了 markdown 解析与 MathJax 重排 ⇒ 这笔钱只可能花在**挂进可见文档之后的收尾**上：
   * 两轮全量 O(n) 扫描（`postProcessWikilinks` / `bindPreviewLinks`）、同步渲染 mermaid、
   * 以及写 `scrollTop` 触发的**强制同步布局**。**猜测不算数 ⇒ 分段量出来**。
   *
   * 口径：每段是**距上一段的增量**（ms，四舍五入），所以"各段之和 ≈ `lastSwitchMs`"；
   * 只在**命中**路径打点（未命中是整篇渲染，另有 `lastSwitchMs` 兜着），开销 = 8 次 `performance.now()`。 */
  var _switchT0 = 0;
  var _switchParts = null;

  function _beginSwitchTiming() {
    _switchT0 = (window.performance && performance.now) ? performance.now() : Date.now();
    _switchParts = {};
    _lastSwitch.parts = _switchParts;
  }

  function _markSwitch(name) {
    if (!_switchParts) return;
    const now = (window.performance && performance.now) ? performance.now() : Date.now();
    _switchParts[name] = Math.round(now - _switchT0);
    _switchT0 = now;
  }

  /** 池的**实测占用**：条目数 / 节点数（真数，遍历缓存子树数出来的）/ 文本字符数 / 各条目已存的估算字节。
   *
   * - 节点数是**数出来的**，不是估的 ⇒ 配合 `MemoriaPreviewPolicy.estimateBand()` 就能回答
   *   "改成序列化 HTML 能省多少"（设计 §3.3 要的第一组数），不必先做完整实测。
   * - `astBlocks` 是**附带常驻**的块数：条目里还留着 `ast`（恢复时直接用，不必重解析）——
   *   它也是池的成本，且**改存 HTML 时正好可以一并放掉**（那一项省不省取决于要不要按需重解析）。
   * - 只在点「刷新读数」时算一次（8 条 × 几千节点，遍历几十毫秒级）⇒ 不进热路径。 */
  function _previewPoolFootprint() {
    let nodes = 0;
    let chars = 0;
    let bytes = 0;
    let astBlocks = 0;
    for (const path of Array.from(_previewDomCache.keys())) {
      const entry = _previewDomCache.get(path);
      if (!entry) continue;
      bytes += Number(entry.bytes) || 0;
      if (entry.ast && Array.isArray(entry.ast.blocks)) astBlocks += entry.ast.blocks.length;
      if (!entry.frag) continue;
      nodes += 1;   // 条目根（DocumentFragment）
      const walk = function (el) {
        for (let n = el.firstChild; n; n = n.nextSibling) {
          nodes += 1;
          if (n.nodeType === 3) chars += (n.nodeValue || "").length;
          else if (n.nodeType === 1) walk(n);
        }
      };
      walk(entry.frag);
    }
    return { entries: _previewDomCache.size, nodes: nodes, chars: chars, bytes: bytes, astBlocks: astBlocks };
  }

  /** 目录相邻的**启发式**分（模型未热 / 模块缺席时的回退）：同章上下节 1.0 > 隔一节 0.4 > 隔几节 0.15 > 同目录 0.2。 */
  function _preloadAdjacency(path, current) {
    if (!path || !current) return 0;
    const leafNum = function (p) {
      const leaf = String(p || "").split(/[\\/]/).pop() || "";
      const m = /^(\d+)/.exec(leaf);
      return m ? parseInt(m[1], 10) : null;
    };
    const a = leafNum(path);
    const b = leafNum(current);
    if (a !== null && b !== null) {
      const gap = Math.abs(a - b);
      if (gap === 1) return 1;
      if (gap === 2) return 0.4;
      if (gap <= 4) return 0.15;
    }
    const dirOf = function (p) {
      const s = String(p || "");
      const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
      return i < 0 ? "" : s.slice(0, i);
    };
    const dir = dirOf(path);
    return dir && dir === dirOf(current) ? 0.2 : 0;
  }

  /** 单个候选的**预期收益** = 概率分 × `T̂(加载耗时)`（`T̂` 就是 AG64 那个因子；没样本 ⇒ 中性值）。 */
  function _preloadGain(path, probability) {
    const mod = _previewPolicyMod();
    const meta = _previewMeta.get(path);
    const t = mod ? mod.costTerm(meta ? meta.loadMs : 0, _previewPolicyOf()) : 0.5;
    return Math.max(0, probability) * t;
  }

  /** 给候选池排序（**只改顺序，不改集合**）：导航模型优先，排不出分的保持原页签顺序在后面。 */
  function _preloadRanked(pool) {
    if (!pool || !pool.length) return [];
    const nav = window.MemoriaNavPredictor;
    if (nav && typeof nav.predictNext === "function") {
      let predicted = null;
      try {
        const exclude = new Set(_previewDomCache.keys());
        if (state.currentPath) exclude.add(state.currentPath);
        predicted = nav.predictNext({ exclude: exclude });
      } catch (_) { predicted = null; }
      if (predicted && predicted.length) {
        const scoreOf = Object.create(null);
        for (const item of predicted) scoreOf[item.file] = item.score;
        const scored = pool
          .map(function (path) { return { path: path, gain: _preloadGain(path, scoreOf[path] || 0) }; })
          .filter(function (item) { return item.gain > 0; })
          .sort(function (a, b) { return b.gain - a.gain; });
        const head = scored.map(function (item) { return item.path; });
        const rest = pool.filter(function (path) { return head.indexOf(path) < 0; });
        if (head.length) return head.concat(rest);
      }
    }
    const ranked = pool.map(function (path, index) {
      const meta = _previewMeta.get(path);
      const recent = meta && meta.lastOpenAt ? 0.3 : 0;
      return { path: path, index: index, gain: _preloadGain(path, _preloadAdjacency(path, state.currentPath) + recent) };
    }).sort(function (a, b) { return (b.gain - a.gain) || (a.index - b.index); });
    return ranked.map(function (item) { return item.path; });
  }

  /** 逐条分数快照（设置页"当前池内排名"与人工排查用；按分升序 ⇒ **第一行就是下一个被淘汰的**）。 */
  function previewCacheScores() {
    const mod = _previewPolicyMod();
    const policy = _previewPolicyOf();
    const now = Date.now();
    const rows = _previewPoolEntries().map(function (item) {
      return {
        path: item.path,
        bytes: item.bytes,
        hits: item.hits,
        idleH: item.lastOpenAt > 0 ? Math.round((now - item.lastOpenAt) / 36000) / 100 : 0,
        loadMs: item.loadMs,
        t: mod ? mod.costTerm(item.loadMs, policy) : 0,
        score: mod ? mod.score(item, policy, now, _previewEvicts) : 0,
      };
    });
    rows.sort(function (a, b) { return a.score - b.score; });
    return {
      evicts: _previewEvicts,
      limit: _previewLimit(),
      limits: {
        cacheLines: _previewCacheLineLimit(),
        preloadLines: _preloadLineLimit(),
        preloadTabs: _preloadTabLimit(),
        preloadDone: _preloadDone,
      },
      lastSwitchMs: _lastSwitch.ms,
      lastSwitchHit: _lastSwitch.hit,
      lastSwitchParts: _lastSwitch.parts || null,   // 命中时的**分段耗时**（各段增量 ms）⇒ 看那几百毫秒花在哪
      lastSwitchPhases: _lastSwitch.phases || null, // 全程五阶段（绝对增量 ms，含 stash/load/editor/render/settle/tail）⇒ 看那 1406 ms 花在哪
      lastSwitchAsync: _lastSwitch.async || null,   // **异步**标记（相对起点 ms）：`paint`（双 rAF ≈ 画面更新）/ `mathjax`（排版跑完）
      entries: _previewDomCache.size,
      enabled: _preloadEnabled,
      stalePruned: _preloadPrunedStale,
      predictMax: PRELOAD_PREDICT_MAX,
      pool: _previewPoolFootprint(),   // 池的**实测**占用（节点数是数出来的）⇒ 决定"要不要改缓存形态"的第一组数
      nav: (window.MemoriaNavPredictor && typeof window.MemoriaNavPredictor.stats === "function")
        ? window.MemoriaNavPredictor.stats()
        : null,
      policy: policy,
      rows: rows,   // 2026-09-25 AG99：`win` 字段（窗口化读数：滚轮/换窗/编辑五段/渲染分段/漂移）已随 K4a 回退一起删除
    };
  }

  /* ══ 2026-09-25：预览区编辑的**块级提交**（人：「预览区域编辑你尝试改源码区重新渲染预览区，这个是错的 —— 我们
     原有的基础设施就是做的双向同步，这也是导致编辑卡顿、上下闪动的原因」）════════════════════════════════════
     病根（预览区编辑有两条提交路，只有一条是对的）：
       · **普通输入**：`MemoriaEditSync.commit()` → `spliceBlockSource()` + `reRenderBlock()` ⇒ **块级**，便宜不闪 ✔
       · **结构性编辑**（回车拆段 / 退格合并 / 跨块删除 / 边界插空行 / 撤销重做）：改完源码后调
         `renderPreview(state.doc)` ⇒ 整篇重解析 + 重建 30 万节点 DOM + 整篇 MathJax/mermaid，而且 `renderPreview`
         还会先插一句"渲染中"把高度塌掉 ⇒ 真机表现＝**卡顿 + 上下闪动 + 光标乱跳**（人反复反馈的那几样）。
     本块把第二条也变成块级：**源码已由调用方改完**，这里只把预览跟着改，而且**只重建真正变了的那几个块**。
     四条纪律：
       ① **全量解析 + 公共前后缀差分**（不是"只解析改动那几行"）：解析很便宜（真机 `解析` 段 30–90 ms），
          而这样 AST 与"整篇解析"**永远一致** ⇒ 调用方算好的 `newCursor.blockIndex` 与 undo 快照语义不会错；
       ② 只对**新块**排 MathJax / 补 wikilink / 按需渲 mermaid —— 不碰整篇；
       ③ 重建后**重编块下标**（`stampBlockLines()` 是按 `data--block-index` **反查**元素的，而后面所有块都位移了）；
       ④ **任一不变量不成立**（无预览 / 无文档 / 块数对不上 / 找不着落点 / 抛异常）⇒ 返回 false，
          由 `repaintPreview()` 退回 `renderPreview()`（老路径）—— **宁可慢一步，绝不停在半坏状态**。
     注：本块落在**外层 IIFE 内**、`MemoriaEditSync` 之后 ⇒ 嵌套 IIFE 里的函数按词法作用域直接可见（函数声明会提升）。 */
  /** 「当前预览 DOM **逐块渲染的是什么**」的签名表（与 `_doc.blocks` **同下标对齐**）。
   *  ⚠️ 它是块级提交差分的**基准**：编辑路径会**先就地改 AST、再改源码**（如"行首退格合并"直接改上一块），
   *  所以绝不能用 `_doc.blocks` 当基准 —— 否则"已被就地改过的块"会被判成"没变"而**跳过重渲**，
   *  DOM 停在旧内容、AST/源码却是新内容（真机：`ada⏎啊SD…` 行首退格后**预览只剩 `ada`**）。
   *  维护点：整篇渲染 / 缓存搬回（整份建立）、`reRenderBlock()`（单块）、块级提交（区间 splice）。 */
  var _domBlockSig = null;
  function _previewBlockSig(b) { try { return b && (b.type + "\u0000" + G.generateBlock(b)); } catch (_) { return null; } }

  /** **源码面板的增量更新**（2026-09-25 AG101；人：「预览区域编辑体感很差，因为输入进去没有反应，
   *  是等渲染之后才显示编辑内容，为什么不是先显示编辑内容然后再同步呢」）。
   *  `renderEditor()` 是**整篇重建**（每行一个 `.-line` 元素）—— 5888 行的文档**每敲一个键**就重建 5888 个元素，
   *  主线程被占住 ⇒ 用户敲进去的字符要等这次重建画完才出现（"没反应"）。这里只动**受影响的那几行**：
   *    · 行数不变（打字 / 行内格式化）⇒ 只改那几行的 `.-line-content`（**O(改动行)**，热路径）；
   *    · 行数变了（回车 / 合并 / 跨块删除）⇒ 替换那几段元素 + **重编后续行的 `data-line` 与行号**（O(文档)，但只在结构性编辑时）。
   *  `data-line` 必须准确（源码侧的选区 / 光标 / 跳转映射全靠它）⇒ 行数变化时不做"先错着、以后再修"。
   *  返回 false ⇒ 调用方退回整篇 `renderEditor()`（找不到落点 / 结构不符：**宁可慢一步，不许错**）。 */
  function patchEditorLines(startLine, oldCount, newCount) {
    try {
      var editor = document.getElementById("editor");
      if (!editor || !state.doc || !state.doc.lines) return false;
      if (startLine < 0 || oldCount < 0 || newCount < 0) return false;
      var first = editor.querySelector("#line-" + (startLine + 1));
      if (!first) return false;
      var srcEditable = (!window.MemoriaEditHandler || window.MemoriaEditHandler.editMode) ? "true" : "false";
      var lines = state.doc.lines;
      if (oldCount === newCount) {   // 快路：只改文本（不重建元素、不重编行号）—— 打字/行内格式化的常走路
        for (var a = 0; a < newCount; a++) {
          var el = editor.querySelector("#line-" + (startLine + 1 + a));
          var span = el && el.querySelector(".-line-content");
          if (!span) return false;
          var html = esc(lines[startLine + a]) || "<br>";
          if (span.innerHTML !== html) span.innerHTML = html;
        }
        return true;
      }
      // 慢路：行数变了 ⇒ 替换这一段，并把后续行号整体重编
      var frag = document.createElement("div");
      for (var b = 0; b < newCount; b++) {
        var n = startLine + 1 + b;
        frag.insertAdjacentHTML("beforeend",
          '<div class="-line" data-line="' + n + '" id="line-' + n + '">' +
          '<span class="-lineno">' + n + "</span>" +
          '<span class="-line-content" contenteditable="' + srcEditable + '" spellcheck="false" tabindex="-1">' + (esc(lines[startLine + b]) || "<br>") + "</span>" +
          "</div>");
      }
      var cur = first;
      for (var c = 0; c < oldCount && cur; c++) { var nx = cur.nextElementSibling; editor.removeChild(cur); cur = nx; }
      var anchor = editor.children[startLine] || null;   // 删完这一段后，同位置的那个元素就是"这段之后第一个"
      while (frag.firstChild) editor.insertBefore(frag.firstChild, anchor);
      var all = editor.querySelectorAll(".-line");
      for (var d = startLine + newCount; d < all.length; d++) {
        var ln = d + 1, e2 = all[d];
        if (e2.getAttribute("data-line") !== String(ln)) {
          e2.setAttribute("data-line", String(ln)); e2.id = "line-" + ln;
          var lno = e2.querySelector(".-lineno"); if (lno) lno.textContent = String(ln);
        }
      }
      editor.style.setProperty("--lineno-ch", String(Math.max(1, String(lines.length).length)));
      return true;
    } catch (e) { log("editor", "patchEditorLines 失败 ⇒ 退回整篇重建: " + ((e && e.message) || e)); return false; }
  }

  function paintPreviewAfterSourceEdit() {
    try {
      var preview = document.getElementById("preview");
      if (!preview || !_doc || !_doc.blocks || !state.doc || typeof state.doc.body !== "string") return false;
      var container = preview.querySelector(".-preview-content") || preview;
      // ⚠️ **必须与 `renderPreview()` 用同一份"准备好的源"**（数学标准化 + 本地图片路径重写），否则 AST 会与
      // 整篇解析不一致（公式归一化甚至会**插行**）⇒ 差分会误判成大跨度、光标下标也可能对不上。
      var MP0 = window.MemoriaMarkdownPreview;
      var body = state.doc.body;
      body = MP0 && typeof MP0.normalizeBody === "function" ? MP0.normalizeBody(body) : body;
      body = rewriteMdImagePaths(body);
      var fresh = P.parse(body);
      if (!fresh || !fresh.blocks) return false;
      var oldB = _doc.blocks, newB = fresh.blocks;
      // ⚠️ **差分的基准是"这个 DOM 现在渲染的是哪些块"（`_domBlockSig`），不是 `_doc.blocks`**：
      // 编辑路径习惯**先就地改 AST、再改源码**（例如"行首退格合并"会直接把上一块合并好），若拿 `_doc` 当基准，
      // 那个"已被就地改过的块"会被判成"没变"而**跳过重渲** ⇒ DOM 停在旧内容、AST/源码却是新内容
      // （真机：`ada⏎啊SD…` 行首退格后**预览只剩 `ada`**，再退格一次才露出合并结果 —— 典型的 AST↔DOM 错位）。
      if (!_domBlockSig || _domBlockSig.length !== oldB.length) return false;   // 没有登记 / 与块数不符 ⇒ 老实整篇重渲
      var same = function (sig, b) {
        try { return sig != null && sig === _previewBlockSig(b); } catch (_) { return false; }
      };
      var i = 0, lim = Math.min(oldB.length, newB.length);
      while (i < lim && same(_domBlockSig[i], newB[i])) i++;
      var k = 0, lim2 = Math.min(oldB.length - i, newB.length - i);
      while (k < lim2 && same(_domBlockSig[oldB.length - 1 - k], newB[newB.length - 1 - k])) k++;
      var oldSpan = oldB.length - i - k, newSpan = newB.length - i - k;
      _doc = fresh; if (M && typeof M.setDoc === "function") M.setDoc(_doc);   // 换 AST（与整篇解析同源）；mapper 也必须跟着换，`restoreCursor()` 靠它把 AST 坐标换回 DOM
      if (oldSpan === 0 && newSpan === 0) { stampBlockLines(preview, _doc, { reset: true }); window.__blockLineMap = _blockLineMap; return true; }   // 内容一字未变（例如只是 `preview_body` 作废）⇒ 连 DOM 都不用动；整篇 reset 是幂等重建（同文本同序 ⇒ 同 id）
      var ok = _paintBlockSpan(container, preview, i, oldSpan, newSpan);
      if (ok) {   // 差分基准跟着这次替换走（只动变动区间；长度对不上就整份重建）
        if (_domBlockSig && _domBlockSig.length === oldB.length) {
          var sigs = [];
          for (var n3 = 0; n3 < newSpan; n3++) sigs.push(_previewBlockSig(newB[i + n3]));
          Array.prototype.splice.apply(_domBlockSig, [i, oldSpan].concat(sigs));
        } else { _domBlockSig = newB.map(_previewBlockSig); }
      }
      return ok;
    } catch (e) { log("render", "块级提交失败 ⇒ 退回整篇重渲: " + ((e && e.message) || e)); return false; }
  }

  /** 只重建 `[i, i+oldSpan)` 这几个块（`_doc` 已换成新 AST）。返回是否成功（false ⇒ 调用方整篇重渲）。 */
  function _paintBlockSpan(container, preview, i, oldSpan, newSpan) {
    var els = container.querySelectorAll(".-src-block[data--block-index]");
    var first = null, anchor = null;
    for (var q = 0; q < els.length; q++) {
      var ix = parseInt(els[q].getAttribute("data--block-index"), 10);
      if (ix === i) first = els[q];
      if (ix === i + oldSpan) { anchor = els[q]; break; }
    }
    if (!first && oldSpan > 0) return false;                 // 要替换的块在 DOM 里找不到 ⇒ 交给整篇重渲
    var parent = first ? first.parentNode : container;       // 尾插（`i` 已是末块之后）：直接挂到容器
    if (!parent) return false;
    var toRemove = [], cur = first;
    for (var n = 0; n < oldSpan && cur; n++) { toRemove.push(cur); cur = cur.nextElementSibling; }
    var frag = document.createDocumentFragment(), made = [];
    var _rc = _rcRenderer();
    if (!_rc) return false;
    for (var b = i; b < i + newSpan && b < _doc.blocks.length; b++) { var el = _rc.renderBlock(_doc.blocks[b], b); frag.appendChild(el); made.push(el); }
    parent.insertBefore(frag, toRemove.length ? toRemove[0] : anchor);
    for (var m = 0; m < toRemove.length; m++) if (toRemove[m].parentNode) toRemove[m].parentNode.removeChild(toRemove[m]);
    // **重编块下标**：不变量是「`.-src-block` 与 `doc.blocks` 一一对应、DOM 序即块序」（renderer 每个块恰好一个
    // `.-src-block`）。对不上就放弃 —— 调用方马上整篇重渲，那会把 DOM 修回一致，所以这里无需回滚。
    var all = container.querySelectorAll(".-src-block[data--block-index]");
    if (all.length !== _doc.blocks.length) return false;
    for (var j = 0; j < all.length; j++) all[j].setAttribute("data--block-index", String(j));
    stampBlockLines(preview, _doc, { reset: true });        // 行号映射（整篇路径 ⇒ reset：下标刚被整体重编，索引语义已失效）
    window.__blockLineMap = _blockLineMap;                   // ⚠️ `stampBlockLines()` 是**重新绑定** `_blockLineMap` 的 ⇒ 外部读的那份（编辑模块 9575 行用它做选区/粘贴映射、keys-debug 也用）必须同步换掉，否则拿到的是旧数组
    if (made.length) {                                       // 只处理**新块**：禁编辑 / 公式 / wikilink / mermaid
      var NEC = 'mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error, .-lightbox-overlay';   // 与 `renderPreview()` 第 4 步同一份选择器（否则新出现的代码块/表格还能被编辑）
      for (var e4 = 0; e4 < made.length; e4++) {
        try { if (made[e4].matches && made[e4].matches(NEC)) made[e4].contentEditable = "false"; } catch (_) { /* matches 不支持就只扫后代 */ }
        made[e4].querySelectorAll(NEC).forEach(function (x) { x.contentEditable = "false"; });
      }
      if (window.MathJax && typeof window.MathJax.typesetPromise === "function") { try { window.MathJax.typesetPromise(made); } catch (_) { /* 排版失败不影响可编辑性 */ } }
      try { postProcessWikilinks(); bindPreviewLinks(); } catch (e2) { log("render", "新块补链接失败: " + ((e2 && e2.message) || e2)); }
      var MPx = window.MemoriaMarkdownPreview;
      if (MPx && typeof MPx.renderMermaidBlocks === "function") {
        for (var t = 0; t < made.length; t++) {
          if (!made[t].querySelector("code.language-mermaid")) continue;
          try { MPx.renderMermaidBlocks(made[t]); } catch (e3) { log("render", "新块 mermaid 失败: " + ((e3 && e3.message) || e3)); }
        }
      }
    }
    return true;
  }

  /** 预览区编辑提交后的统一入口：**能块级就块级，不能就整篇**（两种分支都返回 Promise，`.then` 里恢复光标）。
   *  调用方写法与原「先整篇渲一次、再恢复光标」**完全同形** ⇒ 改动只落在调用点那一行。 */
  function repaintPreview() {
    try { if (paintPreviewAfterSourceEdit()) return Promise.resolve(false); }
    catch (e) { log("render", "块级提交异常 ⇒ 整篇重渲: " + ((e && e.message) || e)); }
    // 2026-10-25 task-141 说明：这里**保持**原样 `renderPreview(state.doc)`（整篇兜底），
    //   不改成 _renderPreviewKeepScroll()。原因：`tests/test_preview_block_commit.py` 把"兜底=整篇重渲"
    //   写成了契约断言，而本任务的症状（源码区编辑）不经过这条路径（源码侧走 syncSourceToPreview /
    //   _srcApplySnapshot，已覆盖）。预览侧结构编辑的兜底丢滚动是**另一个入口**，见报告 §9 残留项。
    return renderPreview(state.doc);
  }

  window.MemoriaApp.setPreviewCachePolicy = setPreviewCachePolicy;
  window.MemoriaApp.previewCacheScores = previewCacheScores;

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-10-04 追加：显示子系统 · mermaid 视图交互的**块级写回门面**
  //
  // 用途（只服务 Surface / mermaid-view，不外泄内部函数名）：
  //   预览区 mermaid 图支持「图内平移 / 右下把手改尺寸 / 把手双击复位」，交互层见
  //   `markdown-preview.js` 的 `_attachMermaidView`。这些改动要**写进文档**（跟文件走）：
  //   围栏内首行指令 `%% memoria-view: zoom=<float> [pan=<x>,<y>]`（2026-10-04 起；旧 `w=/h=` 兼容读取、只取 pan）。
  //   块级写回管线（`spliceBlockSource` + 撤销快照 + 重渲 + 标脏）都在 `MemoriaEditSync`
  //   的**内层闭包**里，模块外拿不到 ⇒ 在此暴露三件**契约语义**：
  //     setBlockSource(bi, src)  替换第 bi 块源码（记撤销 → 更新真源 → 重渲 → 标脏）
  //     getBlockSourceRange(bi)  返回 {startLine,endLine}（0-based，含端点）或 null
  //     getBlockSourceText(bi)   返回第 bi 块当前源码文本 或 null
  //
  // 实现（零行漂移）：`spliceBlockSource` 在内层闭包、外部不可达，故本门面用等价全局出口复现：
  //   块→行映射取 `window.__blockLineMap`（app.js 渲染链已导出），真源取 `MemoriaApp.state`，
  //   撤销走 `MemoriaEditSync.beginUndoGroup/endUndoGroup`（同一份预览撤销栈；edit-handler 的
  //   Ctrl+Z 即 `EditSync.undo`），重渲走 `renderEditor` + `renderPreview({incremental:true})`
  //   （**重解析** ⇒ `_doc`/映射/DOM 一致；与原 legacy 适配器 `setText` 同口径；该适配器 P6c 已删除）。
  //   位置在**主 IIFE 收尾之前** ⇒ 只把 `})();` 往后推，其上既有 `app.js:<行>` 锚点一个不动
  //   （其后的文件末尾装配块整体后移，无锚点引用）。
  // ══════════════════════════════════════════════════════════════════════════════
  // ── P6b：三个宿主能力（链接层 / 公式编排 / 块级重绘）通过**依赖注入**交给 render-core ──
  // 实现仍在本 IIFE（单一事实源）；不再挂 `window.MemoriaApp.surface` 门面。
  // render-core.createRenderCore({host}) 只转发，不复制实现；new-surface / agent-panel 调
  // `core.applyLinkLayer(root)` / `core.applyMathTypeset(root, ast)` / `core.paintBlockPatch()`。
  function _hostApplyPreviewLinkLayer(root) {
    var scope = root || undefined;
    postProcessWikilinks(scope);
    bindPreviewLinks(scope);
    return true;
  }
  function _hostApplyPreviewMathTypeset(root, ast) {
    var preview = root || document.getElementById("preview");
    var docAst = ast || state.doc;
    state.previewToken = (state.previewToken || 0) + 1;
    var token = state.previewToken;
    var pending = queuePreviewMathTypeset(preview, token);
    var finish = function () {
      try { _tagInlineMathContainers(preview, docAst); } catch (_) { /* 打标失败不阻断排版 */ }
    };
    finish();
    if (pending && typeof pending.then === "function") pending.then(finish, finish);
    return pending || Promise.resolve();
  }
  function _hostPaintPreviewBlockPatch() {
    try { return !!paintPreviewAfterSourceEdit(); }
    catch (e) { log("render", "host.paintBlockPatch: " + ((e && e.message) || e)); return false; }
  }
  // 注入到 surface 插件共用的 host 对象（registry 创建、new-surface mount 时取用；同一引用）
  (function _injectSurfaceHost() {
    var h = window.MemoriaSurface && window.MemoriaSurface.host;
    if (!h) return;
    h.applyLinkLayer = _hostApplyPreviewLinkLayer;
    h.applyMathTypeset = _hostApplyPreviewMathTypeset;
    h.paintBlockPatch = _hostPaintPreviewBlockPatch;
  })();

  window.MemoriaApp.surface = {
    /**
     * 块级写回：替换第 bi 块源码（记撤销 → 更新真源 → 重渲 → 标脏）。
     *
     * P4c 追加可选 `opts`（**默认 false，现有调用零变化**）：
     *   · `skipUndoGroup: true` —— 不自己开/收撤销组；由调用方用 `EditSync.beginUndoGroup/endUndoGroup`
     *     把**多次**块写回合成**一个撤销单元**（批量 patch 必须单步撤销）。
     *   · `skipRender: true` —— **精准语义**：仍更新 `state.doc.body/lines/preview_body=null` 与 `markDirty()`，
     *     但**不调 `renderEditor()` / `renderPreview()`**。调用方**必须**在批量结束后统一渲染一次
     *     （`MemoriaApp.renderEditor(state.doc)` + `paintPreviewBlockPatch()` 或 `renderPreview`），
     *     否则会出现「真源已改、画面未变」的静默不一致。
     */
    setBlockSource: function (blockIndex, newBlockSrc, opts) {
      var o = opts || {};
      var es = window.MemoriaEditSync;
      var bi = Number(blockIndex);
      var map = window.__blockLineMap;
      if (!state.doc || !map || !map[bi]) return false;
      var src = String(newBlockSrc == null ? "" : newBlockSrc);
      try { if (es && typeof es.flushRepaint === "function") es.flushRepaint(); } catch (_) { /* 挂起重渲冲掉失败不阻断写回 */ }
      if (!o.skipUndoGroup && es && typeof es.beginUndoGroup === "function") { try { es.beginUndoGroup(); } catch (_) { /* noop */ } }
      var rawLines = (state.doc.body || "").split("\n");
      var range = map[bi];
      var start = range.startLine;
      var endExcl = range.endLine + 1;
      var newLines = src.split("\n");
      state.doc.body = rawLines.slice(0, start).concat(newLines, rawLines.slice(endExcl)).join("\n");
      state.doc.lines = _linesFromBody(state.doc.body);
      state.doc.preview_body = null;
      if (!o.skipUndoGroup && es && typeof es.endUndoGroup === "function") { try { es.endUndoGroup(); } catch (_) { /* noop */ } }
      if (!o.skipRender) {
        try { renderEditor(state.doc); } catch (e) { log("render", "surface.setBlockSource renderEditor: " + ((e && e.message) || e)); }
        try { var p = renderPreview(state.doc, { incremental: true }); if (p && typeof p.catch === "function") p.catch(function () { }); } catch (e2) { log("render", "surface.setBlockSource renderPreview: " + ((e2 && e2.message) || e2)); }
      }
      markDirty();
      return true;
    },
    getBlockSourceRange: function (blockIndex) {
      var map = window.__blockLineMap;
      var range = map && map[Number(blockIndex)];
      if (!range) return null;
      return { startLine: range.startLine, endLine: range.endLine };
    },
    getBlockSourceText: function (blockIndex) {
      var map = window.__blockLineMap;
      var range = map && map[Number(blockIndex)];
      if (!range || !state.doc || !state.doc.lines) return null;
      return state.doc.lines.slice(range.startLine, range.endLine + 1).join("\n");
    },

    // ── 2026-10-05 追加：显示子系统契约（view-surface-contract.md）§3.1 的**语义键** ──
    // 只挂契约语义（不吐内部函数名）；P6c 起 legacy 适配器已删除，new 插头用等价的全局/真实入口。
    // 这些闭包（setViewMode/collectEditorBody/highlightRange/_getViewTopSrcLine/_scrollToSrcLine）
    // 都在本主 IIFE 内、从外面够不着 ⇒ 在此开窗；**不改动任何既有调用路径**（只开窗，不迁移）。

    /** 契约 §3.1 setMode(mode)：视图模式 source | split | preview（内部 setViewMode）。 */
    setMode: function (mode) { return setViewMode(mode); },

    /** 契约 §3.1 的真源文本读数（§3.2 onTextChange 的来源）：内部 collectEditorBody()。 */
    collectText: function () { return collectEditorBody(); },

    /** 契约 §3.1 revealRange(startLine, endLine, opts)：跳转落点 —— **真实高亮路径**
     *  （内部 highlightRange → highlightPreviewRange：band + flash + AG104 二次校准）。
     *  opts.scroll === false（如切换插头恢复光标）⇒ 走 markRangeQuiet：只标范围、不滚动不闪。 */
    revealRange: function (startLine, endLine, opts) {
      var a = Number(startLine);
      var b = (endLine == null) ? a : Number(endLine);
      if (!isFinite(a) || !isFinite(b)) return false;
      if (a > b) { var t = a; a = b; b = t; }
      if (opts && opts.scroll === false) { markRangeQuiet(a, b); return true; }
      highlightRange(a, b);
      return true;
    },

    /** 契约 §3.1 getScrollAnchor()：当前视图顶部源码行（内部 _getViewTopSrcLine；按当前视图模式）。 */
    getScrollAnchor: function () {
      var m = state.viewMode || "preview";
      return { mode: m, srcLine: _getViewTopSrcLine(m) };
    },

    /** 契约 §3.1 setScrollAnchor(a)：滚到锚点源码行（内部 _scrollToSrcLine；按锚点/当前视图模式）。 */
    setScrollAnchor: function (a) {
      if (!a || a.srcLine == null) return false;
      var m = a.mode || state.viewMode || "preview";
      return _scrollToSrcLine(m, a.srcLine);
    },

    /** 契约 §3.1 EditOp kind:'deleteRange' —— 行区间删除（**等价入口**，见下方 _surfaceSpliceRange；text=null 表示不插入新行）。 */
    deleteRange: function (range) { return _surfaceSpliceRange(range, null); },

    /** 契约 §3.1 EditOp kind:'replaceRange' —— 行区间替换（**等价入口**，见下方 _surfaceSpliceRange）。 */
    replaceRange: function (range, text) { return _surfaceSpliceRange(range, text == null ? "" : String(text)); },

    /** 契约 §3.1 样式类编辑（内部 MemoriaEditSync.applyStyle ⇒ commitSelection；range 为 DOM Range）。 */
    applySelectionStyle: function (formatType, color, range, forceApply) {
      // S2：只读态闸门（与 applyFormat / _brushOnMouseUp 同一口径，避免从门面绕过）
      if (!_styleEditAllowed()) { _notifyStyleReadonly(); return { ok: false, readonly: true }; }
      var es = window.MemoriaEditSync;
      return (es && typeof es.applyStyle === "function") ? es.applyStyle(formatType, color, range, forceApply) : { ok: false };
    },
  };

  /** 行区间拼接（`MemoriaApp.surface.replaceRange/deleteRange` 的**等价入口**）。
   *  为什么不用 `MemoriaEditSync.commitRange`：其签名 (startLine,endLine,newLines,newCursor,preCursor,kind) 需要
   *  **AST 光标**（`beginUndo` 的 preCursor 走 cloneCursor，传 null 会抛）⇒ 契约的文本坐标无法无损构造；
   *  故沿用 `surface.setBlockSource`（mermaid 门面）的同一管线：beginUndoGroup → 改真源 → renderEditor + renderPreview → markDirty。
   *  口径：`range = {startLine, endLine}` **1-based 含端点**（与 data--src-line / getSrcRangeForSelection / revealRange 一致）；
   *  粒度为**整行**（列信息 startCol/endCol 忽略）。 */
  function _surfaceSpliceRange(range, text) {
    if (!range || range.startLine == null) return false;
    var s = state;
    if (!s || !s.doc || typeof s.doc.body !== "string") return false;
    var start1 = Number(range.startLine);
    var end1 = (range.endLine == null) ? start1 : Number(range.endLine);
    if (!isFinite(start1) || !isFinite(end1)) return false;
    if (start1 > end1) { var t = start1; start1 = end1; end1 = t; }
    var rawLines = s.doc.body.split("\n");
    var start0 = start1 - 1;          // 1-based 含端点 → 0-based
    var endExcl = end1;               // 含端点：end1(1-based) 对应排他下标
    if (start0 < 0 || start0 > rawLines.length) return false;
    if (endExcl > rawLines.length) endExcl = rawLines.length;
    if (start0 > endExcl) return false;
    var es = window.MemoriaEditSync;
    try { if (es && typeof es.flushRepaint === "function") es.flushRepaint(); } catch (_) { /* 挂起重渲冲掉失败不阻断写回 */ }
    if (es && typeof es.beginUndoGroup === "function") { try { es.beginUndoGroup(); } catch (_) { /* noop */ } }
    var newLines = (text == null) ? [] : String(text).split("\n");   // null = 删除（不插入新行）；"" = 替换为一个空行
    var merged = rawLines.slice(0, start0).concat(newLines, rawLines.slice(endExcl));
    if (!merged.length) merged = [""];                               // 整篇删空 ⇒ 保留一个空行
    s.doc.body = merged.join("\n");
    s.doc.lines = merged.slice();
    s.doc.preview_body = null;
    if (es && typeof es.endUndoGroup === "function") { try { es.endUndoGroup(); } catch (_) { /* noop */ } }
    try { renderEditor(s.doc); } catch (e) { log("render", "surface.spliceRange renderEditor: " + ((e && e.message) || e)); }
    try { var p = renderPreview(s.doc, { incremental: true }); if (p && typeof p.catch === "function") p.catch(function () { }); } catch (e2) { log("render", "surface.spliceRange renderPreview: " + ((e2 && e2.message) || e2)); }
    // M6b：门面行区间拼接（deleteRange/replaceRange）按行数差平移 KP 范围并同步列表/hover
    if (typeof window.__adjustKpRangesAfterSpanReplace === "function") {
      window.__adjustKpRangesAfterSpanReplace(start0, endExcl, endExcl - start0, newLines.length);
    }
    markDirty();
    return true;
  }
})();

/* ===== 顶部文件标签栏：滚轮 → 横向滚动（2026-09-19）=========================
   `#tabs`（index.html:152）是 `overflow-x: auto` 的**横向**标签条，但竖直滚轮对它无效
   （浏览器默认只用竖直增量驱动纵向容器）⇒ 标签一多到溢出，就只能去拖那根很细的滑块。
   此处把指针在标签条区域内的滚轮纵向增量转成横向滚动；横向增量优先，以兼容 Shift+滚轮
   与触控板横向手势（写法与图谱分组标签条的 `bindGraphGroupTabWheel` 一致，app.js:784）。
   零漂移：整块**追加在 app.js 末尾**（既有行号锚点不动）。app.js 于 body 末尾加载
   （index.html:477），`#tabs` 此时已存在，无需等 DOMContentLoaded。 */
(function bindFileTabWheelScroll() {
  const tabs = document.getElementById("tabs");
  if (!tabs || tabs.dataset.wheelBound) return;
  tabs.dataset.wheelBound = "1";
  tabs.addEventListener(
    "wheel",
    (e) => {
      if (e.ctrlKey) return; // Ctrl+滚轮是缩放，不抢
      const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (!delta) return;
      // 无需横向滚动时交还默认行为，避免无谓地吞掉滚轮
      if (tabs.scrollWidth - tabs.clientWidth <= 0) return;
      e.preventDefault();
      tabs.scrollLeft += delta;
    },
    { passive: false }
  );
})();

/* ===== 顶栏文件页签 → 对话栏（2026-09-20）=====================================
   用户：「显示区域的顶栏文件页签也支持拖拽到对话栏」。页签本来就是"打开的文件"，拖进对话栏
   应当与文件树拖拽**完全等价**（同 MIME、同 JSON 形状、同落点语义）⇒ 载荷交给
   `window.MemoriaMentionDrag.set()`（agent-panel 暴露的**唯一**生产者入口），接收端一行不改。
   为什么读 `title` 而不是 `state.openTabs`：本块追加在 IIFE **之外**（app.js 末尾）拿不到闭包里的
   state，而页签模板里 `title` 就是相对路径（`renderTabs()` 的 `esc(t.path)`）。
   事件委托绑在 `#tabs` 容器上 ⇒ `renderTabs()` 重建内部节点也不会丢绑定。
   零漂移：整块**追加在 app.js 末尾**（既有行号锚点不动）。 */
(function bindTabDragToChat() {
  const tabs = document.getElementById("tabs");
  if (!tabs || tabs.dataset.dragBound) return;
  tabs.dataset.dragBound = "1";
  tabs.addEventListener("dragstart", (e) => {
    const t = e.target;
    if (!t || !t.closest || t.closest("[data-tab-close]")) return; // 拖「×」不算拖页签
    const tab = t.closest("[data-tab-index]");
    if (!tab || !window.MemoriaMentionDrag) return;
    const path = tab.getAttribute("title") || "";
    window.MemoriaMentionDrag.set(e, path, "file");
  });
})();

/* ===== 写冲突保护（§9 口径，2026-09-20）============================================
   策略：`docs/design/agent-plugin-design.md §9`（人已拍板）——
   ① **盘上版本 = 唯一权威**（不一致即拒写，绝不基于过期版本写）；
   ② **人的当下操作最高**（agent 批量写期间，人机保存重新入队让路）；
   ③ **冲突由人明示决定**：本块给「重载 / 以我为准 / 稍后」三选一 ——
   **agent 不自动合并、不静默赢；人的过期 buffer 也不自动赢**（否则会静默抹掉对方）。

   为什么整块追加在 app.js 末尾（IIFE **之外**）：零行漂移纪律 —— 既有 `app.js:<行>` 锚点
   （670 / 721 / 1388 / 1866 / 12794 / 12924 …）一个都不动；IIFE 内只做**三处同行内替换**
   （`syncToDisk` 的守卫行 / 保存调用行 / 成功行）。跨闭包只经 `window.MemoriaApp` 门面，
   而门面导出的 `state` 是同一对象引用 ⇒ `state.doc.version` 可直接读写。

   版本从哪来：后端 `load_document` 现在**追加** `version`（文件内容 sha256，只增不改），
   `save_document` 追加可选 `base_version`（空串 = 不校验）与 `force`（覆盖前先备份，可撤销）。 */
(function memoriaWriteGuard() {
  const A = () => window.MemoriaApp || {};
  const T = (k, p) => (A().T ? A().T(k, p) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));
  let busy = false;        // agent 批量写（apply）期间置位 ⇒ 人机保存重新入队（规则 ②）
  let dialogOpen = false;  // 同时只弹一个冲突框（自动保存可能连续触发）

  function showConflictDialog(path, res, body) {
    if (dialogOpen) return;
    dialogOpen = true;
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML = `
      <div class="-modal-backdrop"></div>
      <div class="-modal-box" style="width:min(460px,92vw)">
        <div class="-modal-header" style="cursor:default"><span>${esc(T("writeConflict.title"))}</span></div>
        <div class="-modal-body">${esc(T("writeConflict.body", { path }))}</div>
        <div class="-modal-footer -btn-bar">
          <span class="-modal-footer-spacer"></span>
          <button type="button" class="-btn" data-act="later">${esc(T("writeConflict.later"))}</button>
          <button type="button" class="-btn danger" data-act="force">${esc(T("writeConflict.force"))}</button>
          <button type="button" class="-btn" data-act="reload">${esc(T("writeConflict.reload"))}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const close = () => { dialogOpen = false; overlay.remove(); };
    overlay.querySelector(".-modal-backdrop").addEventListener("click", close);
    overlay.querySelector('[data-act="later"]').addEventListener("click", close);
    overlay.querySelector('[data-act="reload"]').addEventListener("click", async () => {
      close();
      await A().openFile?.(path);  // 丢弃本地编辑、跟盘上走（openFile 会重设 state.doc 含新 version）
      A().setStatus?.(T("writeConflict.reloaded"), path);
    });
    overlay.querySelector('[data-act="force"]').addEventListener("click", async () => {
      close();
      const r = await A().call?.("save_document", path, body, "", true);  // force ⇒ 后端先备份再覆盖
      const st = A().state;
      if (r && r.status === "ok") {
        if (st && st.doc) st.doc.version = r.version || "";
        A().setStatus?.(T("writeConflict.forced"), path);
      } else {
        A().showFlashError?.(T("writeConflict.forceFail"), (r && r.message) || "");
      }
    });
  }

  window.MemoriaWriteGuard = {
    isBusy: () => busy,
    /** agent 批量写前后调用：apply 期间人机保存让路（§9 规则 ②） */
    setBusy: (v) => { busy = !!v; },
    /** IIFE 内 `syncToDisk` 守卫：忙 ⇒ 重新入队（`rearm` = `markDirty`）并跳过本次 */
    deferIfBusy: (rearm) => {
      if (!busy) return false;
      try { rearm && rearm(); } catch (e) { /* 入队失败也不能让保存直接冲进去 */ }
      return true;
    },
    /** IIFE 内保存失败的唯一出口：返回 true = 已接管（不再 `console.warn`） */
    onSaveFailed: (res, path, body) => {
      if (!res || res.code !== "stale_write") return false;
      showConflictDialog(path, res, body);
      return true;
    },
  };
})();

/* ===== 显示子系统插口（Surface 插头，2026-10-02；P6c 起仅 new）=====================
   只立「插口 + 注册 + 切换协议 + 如实声明能力」；**不迁移**任何既有调用路径 ——
   app.js 现有调用照旧（把现有调用改成"经插口调用"会在宿主侧留下"半所有权"状态，
   是本仓已知红线；留待 NewSurface 能跑时再迁）。契约：docs/design/view-surface-contract.md §4。

   零行漂移：整块**追加在 app.js 最末尾**（主 IIFE 之外）⇒ 其上既有 `app.js:<行>` 锚点
   一个不动。本块只用全局入口（`window.MemoriaSurface`），`#editor-split` 此时已存在
   （脚本在 body 末尾加载）。
   ⚠️ 主 IIFE 内的闭包（setViewMode / highlightRange / _getViewTopSrcLine …）在此**不可见**、
   也不通过门面暴露 ⇒ new 插头改用等价的全局/真实入口（见 surface/new-surface.js 头部说明）。
   （2026-10-06 例外：`_getViewTopSrcLine` / `_scrollToSrcLine` 两个**只读视图入口**已单独经
   `window.MemoriaApp` 门面暴露，供本文件末尾 `memoriaPositionMemory()` 块复用。） */
(function initSurfaceSocket() {
  var S = window.MemoriaSurface;
  if (!S || !S.registry || typeof S.switchTo !== "function") return;

  // P6c（不可逆）：legacy 插头已删除，唯一生产插头是 new（new-surface.js 自注册）。
  // 首次挂载＝采用宿主现存状态（不重放 setText/setMode ⇒ 加载期零重渲）。
  // 若 new 缺失（脚本顺序错误/损坏），switchTo 会落到 §4.4 的显式失败路径并保持无插头，
  // 不会退回 legacy（已不存在）。
  S.switchTo("new", { container: document.getElementById("editor-split") })
    .catch(function (e) { try { console.warn("[MemoriaSurface] switchTo('new') 失败:", (e && e.message) || e); } catch (_) { /* noop */ } });

  // `window.MemoriaSurface` 已由 surface/registry.js 暴露（控制台可用 current() / switchTo()）
})();

/* ===== 前进/后退 + 按文件的位置记忆（2026-10-06）=====================================
   人报障：「memoria 的『前进/后退』按钮跳转文件之后**从头开始看**，而不是文件的旧位置，不好」。
   根因：位置记忆只接在「切模式」链路（`setViewMode` 的 `_saveCurrentViewScroll` / `_scrollToSrcLine`），
   而 `navBack/navForward → openFile` 这条路**既不按文件存、打开时也不恢复**（frame 里也不带位置）；
   文件树双击（`openFileFromTree → openFile`）同样从头。
   本块（**整块追加在 app.js 最末尾**，主 IIFE 之外；跨闭包只经 `window.MemoriaApp` + `window.MemoriaNavStack`：
    (b) 每次「离开当前文件/帧之前」把视口顶部源码行写进导航栈**该帧自己的** `anchorLine`
        （`MemoriaNavStack.rememberAnchor`）；后退/前进时把该帧的 `anchorLine` 经 `openFile({navAnchor})`
        恢复（复用 `_scrollToSrcLine`）⇒ 同一文件的不同位置也能像浏览器一样分别记住。
    (a) 另存一张**内存**表 `kbPath\\0路径 → 顶部源码行`（不写盘、不进 `.memoria/**`）；`openFile` 无显式
        跳转目标（kpId/errorHighlight/lineHint）时据此恢复 ⇒ 文件树双击/重开也回到原处。
   采集纪律（AG105 老坑）：`remember()` 一律在**重渲染/换文件/入栈之前**被调用（见各调用点的行内插入）。
   零行漂移：主 IIFE 内只做**同行内替换**；本块整块末尾追加；`nav-stack.js` 只加一个同行方法。 */
(function memoriaPositionMemory() {
  var memo = Object.create(null);   // kbPath \u0000 路径 → 顶部源码行（内存 only）
  var guard = null;                 // 二次校准守卫（与 AG104 同款：人一动就放弃校正，不抢滚动条）

  function key(path) {
    var st = window.state || {};
    return String(st.kbPath || "") + "\u0000" + String(path || "");
  }

  // 当前视口顶部对应的源码行（复用主 IIFE 的 _getViewTopSrcLine，经门面）
  function topLine() {
    var A = window.MemoriaApp;
    if (!A || typeof A.getViewTopSrcLine !== "function") return null;
    var st = window.state;
    var line = null;
    try { line = A.getViewTopSrcLine(st ? st.viewMode : "preview"); } catch (e) { line = null; }
    return line || null;
  }

  /** 采当前视口位置：写入内存表 + 写进导航栈**当前那个文件所在的帧**。返回行号（无则 null）。 */
  function remember() {
    var st = window.state;
    if (!st || !st.currentPath) return null;
    var line = topLine();
    if (!line) return null;
    memo[key(st.currentPath)] = line;
    if (window.MemoriaNavStack && typeof window.MemoriaNavStack.rememberAnchor === "function") {
      window.MemoriaNavStack.rememberAnchor(st.currentPath, line);
    }
    return line;
  }

  function applyLine(line) {
    var A = window.MemoriaApp;
    var st = window.state;
    if (!A || typeof A.scrollToSrcLine !== "function" || !st) return false;
    var ok = false;
    try { ok = !!A.scrollToSrcLine(st.viewMode, line); } catch (e) { ok = false; }
    scheduleReanchor(line);
    return ok;
  }

  // AG104 教训：后面 MathJax/懒图结算会改变行高 ⇒ 落点先定一次、布局落定后再校两次；人一动就不校。
  function scheduleReanchor(line) {
    var st = window.state;
    if (!st) return;
    var path = st.currentPath;
    var g = { cancelled: false };
    guard = g;
    var mark = function () { g.cancelled = true; };
    ["preview-pane", "editor-pane"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      ["wheel", "mousedown", "touchstart", "keydown"].forEach(function (ev) {
        el.addEventListener(ev, mark, { passive: true, once: true });
      });
    });
    [350, 1400].forEach(function (delay) {
      setTimeout(function () {
        if (g.cancelled || guard !== g) return;
        if (window.state.currentPath !== path) return;
        try { window.MemoriaApp.scrollToSrcLine(window.state.viewMode, line); } catch (e) { /* noop */ }
      }, delay);
    });
  }

  /** `openFile` 收尾调用：恢复本帧（b）/本文件（a）的位置。 */
  function restoreForOpen(opts) {
    var st = window.state;
    if (!st || !st.currentPath) return false;
    var line = (opts && opts.navAnchor) || null;                                    // (b) 帧内记录优先
    var hasJump = !!(opts && (opts.kpId || opts.errorHighlight || opts.lineHint));  // 显式跳转目标优先于按文件记忆
    if (!line && !hasJump && !(opts && opts.restoreScroll)) {
      line = memo[key(st.currentPath)] || null;                                     // (a) 按文件
    }
    if (!line) return false;
    return applyLine(line);
  }

  window.MemoriaPositionMemory = { remember: remember, restoreForOpen: restoreForOpen };
})();

/* ═══════════════════════════════════════════════════════════════════════════
   task-144 ⑥：窗口恢复体感（a 抑制恢复动画 / c 启动加载感）
   · (a) 最小化→恢复：WebView2 恢复首帧会重新布局，右栏会重放"收缩→伸展"过渡
         ⇒ 恢复时给 <html> 加 .-no-transition（CSS 只关左右侧栏的 width transition），
         240ms 后移除；用户主动操作不受影响。
   · (c) 首屏数据就绪前：<html> 保持 .-booting（logo 轻脉冲 + 顶部进度条，见 app.css），
         首个文档打开后移除；8s 兜底防"永远转圈"。
   ═══════════════════════════════════════════════════════════════════════════ */
(function memoriaBootUX() {
  var root = document.documentElement;
  if (!root) return;
  // (c) 启动加载态
  root.classList.add("-booting");
  var bootStart = Date.now();
  var bootTimer = setInterval(function () {
    var ready = (window.state && window.state.currentPath) || (Date.now() - bootStart > 8000);
    if (ready) {
      clearInterval(bootTimer);
      root.classList.remove("-booting");
    }
  }, 120);
  // (a) 恢复时抑制过渡（只在"窗口从不可见/失焦回来"时，用户主动操作不抑制）
  var suppressTimer = 0;
  function suppressRestoreTransitions() {
    root.classList.add("-no-transition");
    if (suppressTimer) clearTimeout(suppressTimer);
    suppressTimer = setTimeout(function () {
      suppressTimer = 0;
      root.classList.remove("-no-transition");
    }, 240);
  }
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) suppressRestoreTransitions();
  });
  window.addEventListener("focus", suppressRestoreTransitions);
})();
