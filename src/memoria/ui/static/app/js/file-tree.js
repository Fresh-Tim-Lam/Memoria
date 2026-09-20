/**
 * 知识库侧栏文件树（原 app.js「知识库文件树」子系统，2026-09-04 抽出）。
 *
 * 自包含：#file-tree 渲染（目录/文件分层、展开/折叠状态 treeExpanded、目录与文件图标、
 * 侧车缺失标记、当前文件高亮）、树内点击切换文档（navigateToFile）、右键上下文菜单
 * （文件 → 重命名/删除；文件夹 → 重命名/新建文件/新建文件夹；空白区另含图片管理入口）、
 * 新建/重命名/删除的后端调用与结果状态提示（确认弹窗复用应用内轻量 .-modal 浮层）。
 * 重命名（文件/文件夹）走完整自维护链路：后端迁移磁盘 + 侧车镜像/file 字段 + pending
 * + manifest + 图片注册表；前端 applyRenameUi 统一重映射标签页/展开集/当前文件并刷新。
 * 快捷键：点击文件或文件夹后按 F2 触发重命名（输入框/浮层激活时不劫持）。
 *
 * DOM/事件绑定全部由渲染后的 bindFileTreeInteraction 完成（沿用原 app.js 行为，属性
 * 赋值避免 render 重建重复绑定）；init() 仅为与其他子系统统一的 boot 入口（树无独立
 * 全局事件需在 init 注册）。重新渲染由 app.js 侧状态变更后调用：refreshFiles / openFile
 * / closeKb / closeTabAt / KP 写回（见公开 API render/expandToPath）。
 *
 * app.js 仍需调用的公开 API（见文件末尾 return）：
 *   init / render（原 renderFileTree）/ expandToPath（原 ensureTreeExpandedForPath）
 *
 * 依赖 window.MemoriaApp（app.js 导出的应用服务门面）：
 *   state / call / T / esc / setStatus / refreshFiles / openFile
 *   showTreeContextMenu / confirmTreeAction（通用 .-context-menu / .-modal 浮层，
 *     image-tools.js 亦经门面使用，故留在 app.js）
 *   renderTabs / closeTabAt / updateNavButtons（本次拆分在门面上追加的私有服务，
 *     见 app.js 门面注释）
 *
 * 文案全部经 T('key') 取当前语言：右键菜单项/新建/重命名/删除弹窗与状态提示新增
 * tree.* 键族（zh-CN/en 成对），确认/取消/确定复用 common.*，图片管理入口复用
 * img.menuLabel。DOM id/class、事件语义、样式与多 KB 切换状态语义均与原 app.js 一致。
 */
window.MemoriaFileTree = (function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const A = () => window.MemoriaApp || {};

  // 拖拽到右侧对话栏用：自定义 MIME 携带结构化载荷 `{path, kind:"file"|"dir"}`；
  // 另写 `text/plain`（相对路径、目录带尾斜杠）供其它输入框兜底。
  // 接收端在 js/agent-panel.js（同一字面量，两文件各自持有常量 —— 按 frontend-modules.md R5
  // 不跨文件互借私有符号；改这里必须同步改那边）。
  const DRAG_MIME = "application/x-memoria-path";

  // app.js 导出 state 为同一对象引用（永不整体替换），捕获一次后属性读写均实时可见
  const state = A().state || {};

  // 最近一次左键点中的树节点（用于 F2 快捷键重命名）；type: 'file' | 'dir'
  let _lastSel = null;

  /** 把路径 oldPath 相关的引用路径重映射到 newPath（自身或子树前缀），不相关返回 null */
  function remapPath(p, oldPath, newPath) {
    if (!p) return null;
    if (p === oldPath) return newPath;
    const pre = oldPath + "/";
    return p.startsWith(pre) ? newPath + p.slice(oldPath.length) : null;
  }

  /** 重命名成功后统一刷新界面状态：树展开集 / 打开标签页 / 当前文件；返回重映射后的当前文件路径 */
  function applyRenameUi(oldPath, newPath) {
    // 结构变更 → 提升调度 epoch，使基于旧路径/旧结构的排队派生作业陈旧可弃
    window.MemoriaScheduler?.bumpEpoch?.();
    const mappedCur = remapPath(state.currentPath, oldPath, newPath);
    const expanded = ensureTreeExpandedSet();
    for (const k of Array.from(expanded)) {
      const nk = remapPath(k, oldPath, newPath);
      if (nk) {
        expanded.delete(k);
        expanded.add(nk);
      }
    }
    for (const t of state.openTabs) {
      const nk = remapPath(t.path, oldPath, newPath);
      if (nk) {
        t.path = nk;
        t.label = basename(nk);
      }
    }
    renderTabs();
    return mappedCur;
  }

  function T(key, params) {
    const a = A();
    return a.T ? a.T(key, params) : key;
  }
  function esc(s) {
    const a = A();
    return a.esc ? a.esc(s) : String(s == null ? "" : s);
  }
  const call = (...args) => {
    const a = A();
    return a.call ? a.call(...args) : undefined;
  };
  const setStatus = (...args) => {
    A().setStatus?.(...args);
  };
  const refreshFiles = () => A().refreshFiles?.();
  const openFile = (relPath, opts) => A().openFile?.(relPath, opts);
  const renderTabs = () => A().renderTabs?.();
  const closeTabAt = (index) => A().closeTabAt?.(index);
  const updateNavButtons = () => A().updateNavButtons?.();
  const showTreeContextMenu = (x, y, items) =>
    A().showTreeContextMenu?.(x, y, items);
  const confirmTreeAction = (title, message, okLabel, cb) =>
    A().confirmTreeAction?.(title, message, okLabel, cb);

  function basename(p) {
    const parts = String(p || "").replace(/\\/g, "/").split("/");
    return parts[parts.length - 1];
  }

  function ensureTreeExpandedSet() {
    if (!state.treeExpanded) {
      state.treeExpanded = new Set();
    }
    return state.treeExpanded;
  }

  function ensureTreeExpandedForPath(relPath, respectUserCollapsed) {
    if (!relPath) return;
    const expanded = ensureTreeExpandedSet();
    const parts = relPath.replace(/\\/g, "/").split("/");
    let acc = "";
    for (let i = 0; i < parts.length - 1; i++) {
      acc = acc ? `${acc}/${parts[i]}` : parts[i];
      if (!(respectUserCollapsed && userCollapsedSet().has(acc))) { if (!respectUserCollapsed) userCollapsedSet().delete(acc); expanded.add(acc); }
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
      <div class="-tree-dir-head" data-dir-toggle="${esc(node.path)}" draggable="true" style="padding-left:${pad}px">${treeGuides(depth)}
        <span class="-tree-twisty">${icon("triangleRight", expanded ? "is-open" : "")}</span>
        <span class="-tree-icon">${icon(expanded ? "folderOpen" : "folderClose")}</span>
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
    const iconName = FT_CATEGORY_ICON[classifyFileType(f.path)] || "ftOther";
    const pad = 12 + depth * 14;
    const label = basename(f.path);
    return `<div class="-tree-item${active}${side}" data-path="${esc(f.path)}" title="${esc(f.path)}" draggable="true" style="padding-left:${pad}px">${treeGuides(depth)}
      <span class="-tree-icon">${icon(iconName)}</span>
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
        _lastSel = { type: "dir", path: dirPath };
        const expanded = ensureTreeExpandedSet();
        if (expanded.has(dirPath)) collapseDir(dirPath);
        else expandDir(dirPath);
        renderFileTree();
      });
    });
    el.querySelectorAll(".-tree-item").forEach((node) => {
      node.addEventListener("click", () => {
        _lastSel = { type: "file", path: node.dataset.path };
        navigateToFile(node.dataset.path);
      });
    });
    // 拖拽到右侧对话栏：载荷 = 相对路径（目录带尾斜杠），另附自定义 MIME 供接收端区分类型。
    // 用**属性赋值**而非 addEventListener —— 本函数每次 render 都会跑，而 el 是常驻节点，
    // addEventListener 会逐次叠加（与下方 oncontextmenu 同理）。
    el.ondragstart = (e) => {
      const t = e.target;
      if (!t || !t.closest) return;
      const item = t.closest(".-tree-item");
      const head = item ? null : t.closest(".-tree-dir-head");
      const path = item ? item.dataset.path : head ? head.dataset.dirToggle : "";
      if (!path) return;
      const kind = item ? "file" : "dir";
      if (window.MemoriaMentionDrag) { window.MemoriaMentionDrag.set(e, path, kind); } else if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "copy";
        try {
          e.dataTransfer.setData(DRAG_MIME, JSON.stringify({ path, kind }));
        } catch (_err) {
          // 个别宿主不接受自定义 MIME：此时对话栏接不到这次拖拽
          //（text/plain 仍写着，供其它输入框或外部程序使用）
        }
        e.dataTransfer.setData("text/plain", kind === "dir" ? path.replace(/\/+$/, "") + "/" : path);
      }
      _lastSel = { type: kind, path };
    };
    // 右键菜单（事件委托，属性赋值避免 render 重建重复绑定）：
    // 文件 → 重命名/删除；文件夹 → 重命名/新建文件/新建文件夹；空白区 → 根目录下新建
    el.oncontextmenu = (e) => {
      const t = e.target;
      if (!t || !t.closest) return;
      const item = t.closest(".-tree-item");
      if (item) {
        e.preventDefault();
        e.stopPropagation();
        _lastSel = { type: "file", path: item.dataset.path };
        showTreeContextMenu(e.clientX, e.clientY, [
          { label: T("tree.rename"), action: () => renameTreeFile(item.dataset.path) },
          { label: T("tree.delete"), danger: true, action: () => deleteTreeFile(item.dataset.path) },
        ]);
        return;
      }
      const dirHead = t.closest(".-tree-dir-head");
      if (dirHead) {
        e.preventDefault();
        e.stopPropagation();
        const base = dirHead.dataset.dirToggle || "";
        _lastSel = { type: "dir", path: base };
        showTreeContextMenu(e.clientX, e.clientY, [
          { label: T("tree.rename"), action: () => renameTreeDir(base) },
          { divider: true },
          { label: T("tree.newFile"), action: () => createTreeFile(base) },
          { label: T("tree.newFolder"), action: () => createTreeDir(base) },
        ]);
        return;
      }
      if (t.closest("#file-tree")) {
        e.preventDefault();
        e.stopPropagation();
        showTreeContextMenu(e.clientX, e.clientY, [
          { label: T("tree.newFile"), action: () => createTreeFile("") },
          { label: T("tree.newFolder"), action: () => createTreeDir("") },
          { label: T("img.menuLabel"), action: () => window.MemoriaImageTools?.openImageManager?.() },
        ]);
      }
    };
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
          <button type="button" class="-btn" data-act="cancel">${T("common.cancel")}</button>
          <button type="button" class="-btn primary" data-act="ok">${esc(okLabel || T("common.ok"))}</button>
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

  async function navigateToFile(relPath) {
    if (window.MemoriaNavStack) {
      window.MemoriaNavStack.openFileFromTree(relPath);
      updateNavButtons();
    }
    await openFile(relPath, { fromNav: true });
  }

  async function renameTreeFile(relPath) {
    const oldName = basename(relPath);
    promptTreeInput(T("tree.renameTitle"), T("tree.renamePh"), oldName, T("tree.rename"), async (val) => {
      if (!val || val === oldName) return;
      const res = await call("file_rename", relPath, val);
      if (!res || res.status !== "ok") {
        setStatus((res && res.message) || T("tree.renameFail"));
        return;
      }
      setStatus(T("tree.renamed"), res.path);
      if (res.synced) {
        const n = res.md_replacements || 0;
        const m = (res.md_files || []).length;
        const s = (res.sidecar_files || []).length;
        setStatus(T("tree.renamedSynced", { n, m, s }), res.path);
      }
      const mappedCur = applyRenameUi(relPath, res.path);
      await refreshFiles();
      if (mappedCur) {
        await openFile(mappedCur, { fromNav: true });
      }
    });
  }

  async function renameTreeDir(relPath) {
    const oldName = basename(relPath);
    promptTreeInput(T("tree.renameDirTitle"), T("tree.renameDirPh"), oldName, T("tree.rename"), async (val) => {
      if (!val || val === oldName) return;
      const res = await call("dir_rename", relPath, val);
      // 后端可能返回 "partial"（部分文档级联失败）——此时同样提示，不再误判为成功
      if (!res || res.status !== "ok") {
        setStatus((res && res.message) || T("tree.renameFail"));
        return;
      }
      setStatus(T("tree.dirRenamed"), res.path);
      if (res.files) {
        setStatus(
          T("tree.dirRenamedSynced", {
            files: res.files,
            sidecars: (res.sidecar_files || []).length,
            pending: res.pending_updated || 0,
          }),
          res.path
        );
      }
      const mappedCur = applyRenameUi(relPath, res.path);
      await refreshFiles();
      if (mappedCur) {
        await openFile(mappedCur, { fromNav: true });
      }
    });
  }

  async function deleteTreeFile(relPath) {
    confirmTreeAction(
      T("tree.deleteTitle"),
      T("tree.deleteBody", { name: basename(relPath) }),
      T("tree.delete"),
      async () => {
        const res = await call("file_delete", relPath);
        if (res.status !== "ok") {
          setStatus(res.message || T("tree.deleteFail"));
          return;
        }
        setStatus(T("tree.deleted"), basename(relPath));
        const tabIdx = state.openTabs.findIndex((t) => t.path === relPath);
        if (tabIdx >= 0) {
          closeTabAt(tabIdx);
        }
        await refreshFiles();
      }
    );
  }

  async function createTreeFile(baseDir) {
    promptTreeInput(T("tree.newFile"), T("tree.newFilePh"), "", T("tree.createBtn"), async (val) => {
      if (!val) return;
      const rel = baseDir ? `${baseDir}/${val}` : val;
      const res = await call("file_create", rel);
      if (res.status !== "ok") {
        setStatus(res.message || T("tree.createFail"));
        return;
      }
      setStatus(T("tree.created"), res.path);
      if (baseDir) { userCollapsedSet().delete(baseDir); ensureTreeExpandedSet().add(baseDir); }
      await refreshFiles();
      await openFile(res.path, { fromNav: true });
    });
  }

  async function createTreeDir(baseDir) {
    promptTreeInput(T("tree.newFolder"), T("tree.newFolderPh"), "", T("tree.createBtn"), async (val) => {
      if (!val) return;
      const rel = baseDir ? `${baseDir}/${val}` : val;
      const res = await call("dir_create", rel);
      if (res.status !== "ok") {
        setStatus(res.message || T("tree.createFail"));
        return;
      }
      setStatus(T("tree.createdFolder"), res.path);
      if (baseDir) { userCollapsedSet().delete(baseDir); ensureTreeExpandedSet().add(baseDir); }
      await refreshFiles();
    });
  }

  function renderFileTree() {
    const el = $("#file-tree");
    if (!el) return;
    if (!state.files.length && !(state.dirs || []).length) {
      el.innerHTML = `<div class="empty">${T("tree.empty")}</div>`;
      return;
    }
    if (state.currentPath) ensureTreeExpandedForPath(state.currentPath, true);
    const root = buildFileTreeRoot(state.files, state.dirs);
    // 末尾固定留白区：保证滚轮到底后仍有空白可右键「根目录新建」，也避免末项贴底难以触发根菜单
    el.innerHTML =
      renderTreeLevel(root, 0) +
      '<div class="-tree-root-zone" style="height:64px;cursor:default" title=""></div>';
    bindFileTreeInteraction(el);
  }

  /**
   * init：与 import-flow/toolbar-search/image-tools/kb-check 等子系统统一入口
   * （app.js boot 在 MemoriaKbCheck.init 后调用）。文件树的事件均在每次渲染后由
   * bindFileTreeInteraction 绑定（原 app.js 行为），无独立全局事件需在 init 注册；
   * 重新渲染由 app.js 侧状态变更后调用公开 API render 触发。
   */
  function init() {
    // F2 重命名快捷键：左键/右键点中文件或文件夹后按 F2 打开重命名弹窗。
    // 点击文件后焦点通常已进入可编辑预览区，因此 contenteditable 不拦截（F2 为功能键）；
    // 仅避开真正的文本输入控件与已打开的浮层，避免与输入/其它弹窗冲突。
    if (!window.__memoriaFileTreeF2) {
      window.__memoriaFileTreeF2 = 1;
      // 捕获阶段注册：预览/编辑器等内部 keydown 可能 stopPropagation，冒泡阶段收不到；
      // 捕获在 document 处最先执行，可绕过内部拦截。
      document.addEventListener(
        "keydown",
        (e) => {
          if (e.key !== "F2") return;
          const t = e.target;
          if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) {
            return;
          }
          // 仅当有“可见”弹窗时拦截（index.html 常驻多个 .-modal.hidden，不可见的不算）
          const openModal = Array.from(document.querySelectorAll(".-modal")).some(
            (m) => !m.classList.contains("hidden")
          );
          if (openModal) return;
          if (!_lastSel) return;
          e.preventDefault();
          e.stopPropagation();
          if (_lastSel.type === "dir") renameTreeDir(_lastSel.path);
          else renameTreeFile(_lastSel.path);
        },
        true
      );
    }
  }

  /**
   * 在树中展开并定位一个目录（右侧对话栏里点击「文件夹引用」chip 时调用）。
   * 展开目标目录**自身与全部祖先**，重绘后滚到可见处。
   */
  function revealDir(dirPath) {
    const p = String(dirPath || "").replace(/\\/g, "/").replace(/\/+$/, "");
    if (!p) return;
    const expanded = ensureTreeExpandedSet();
    let acc = "";
    for (const seg of p.split("/")) {
      if (!seg) continue;
      acc = acc ? `${acc}/${seg}` : seg;
      userCollapsedSet().delete(acc); expanded.add(acc);
    }
    renderFileTree();
    for (const head of document.querySelectorAll("#file-tree .-tree-dir-head")) {
      if (head.dataset.dirToggle === p) {
        head.scrollIntoView({ block: "nearest" });
        break;
      }
    }
  }

  /* ============================ 末尾追加块（2026-09-19） ============================
   * 本块之后紧接 return —— 新增代码一律进这里，本块之前的行/行号锚点零漂移。
   *
   * A. 文件夹折叠记忆（bug 修复）
   *    现象：点目录头 [data-dir-toggle] 折叠后，renderFileTree() 会立刻用
   *    ensureTreeExpandedForPath(state.currentPath) 把「当前打开文件所在目录」重新展开
   *    ⇒ 含当前文件的文件夹永远合不上。
   *    语义（用户确认：「我可以显示折叠，但是其他文件 reveal 也可以覆盖」）：
   *    记住用户的**显式折叠**（_userCollapsedDirs），让它压过「同一次重渲里为当前文件做的自动展开」；
   *    但任何**真正的 reveal**（openFile → expandToPath、对话栏 chip → revealDir、在目录内新建文件/文件夹）
   *    都会清掉该记忆并重新展开 —— 折叠只是「这一轮不想看」，不是永久禁用。
   *    设置点：collapseDir()（目录头点击的折叠分支）；
   *    清除点：expandDir()（展开分支）、ensureTreeExpandedForPath() 不带 respectUserCollapsed 时
   *    （即公开 API expandToPath，app.js openFile 调用）、revealDir()、createTreeFile/createTreeDir 的 baseDir；
   *    守卫点：renderFileTree() 的 ensureTreeExpandedForPath(state.currentPath, true)
   *    —— 重渲时只跳过用户折叠过的目录，其余祖先照常展开（不违反 hard-constraints §7「保持展开态」）。
   *    生命周期：仅内存 Set，随重开库/重开应用自然失效（与原 treeExpanded 一致）。
   */
  let _userCollapsedDirs = null;

  /** 用户显式折叠过的目录集合（惰性创建） */
  function userCollapsedSet() {
    if (!_userCollapsedDirs) _userCollapsedDirs = new Set();
    return _userCollapsedDirs;
  }

  /** 折叠分支：记入折叠记忆 + 移出展开集 */
  function collapseDir(path) {
    ensureTreeExpandedSet().delete(path);
    userCollapsedSet().add(path);
  }

  /** 展开分支：清掉折叠记忆 + 加入展开集 */
  function expandDir(path) {
    userCollapsedSet().delete(path);
    ensureTreeExpandedSet().add(path);
  }

  /* ---------------------------------------------------------------------------
   * B. 图标（借用 deepseek-harness「dsh」，MIT，pin 0d1f5000）
   *    上游：dsh-src/packages/client/ui-primitives/src/icons/index.tsx
   *          （IconTriangleRightFill14、IconFolderClose16、IconFolderOpen16、IconTreeCorner8x10）
   *          dsh-src/packages/client/ui-primitives/src/FileTypeIcon.tsx
   *          （FILE_BODY / FILE_FOLD / 各类型 mark）
   *    path 数据**逐字复制**，颜色统一为 currentColor（根节点 fill="currentColor"，
   *    内部用 fill-opacity 分层）⇒ 深浅主题由既有 --text-* / --theme-color / --border 等 token 驱动。
   *    品牌/商标类徽标（CodeFileIcon / code-file-icon-artwork.ts 的 48 个）**不移植**：
   *    代码类文件统一落通用 code 图标。登记见仓库根 THIRD_PARTY_NOTICES.md。
   */
  const FT_FILE_BODY =
    "M8.48924 28H19.5108C21.6479 28 22.7165 28 23.5594 27.6509C24.6833 27.1853 25.5762 26.2924 26.0417 25.1685C26.3909 24.3256 26.3909 23.257 26.3909 21.1199V8.79443C26.3909 8.32877 26.3909 8.09593 26.3471 7.87507C26.2887 7.58058 26.173 7.30042 26.0067 7.05048C25.882 6.86303 25.7177 6.69799 25.3893 6.36792L20.0611 1.01354C19.7304 0.681235 19.5651 0.515081 19.3769 0.38885C19.126 0.220541 18.8443 0.103463 18.5481 0.0443412C18.3259 0 18.0915 0 17.6226 0H8.48924C6.35209 0 5.28351 0 4.4406 0.349145C3.31672 0.814671 2.4238 1.70759 1.95828 2.83147C1.60913 3.67438 1.60913 4.74296 1.60913 6.88011V21.1199C1.60913 23.257 1.60913 24.3256 1.95828 25.1685C2.4238 26.2924 3.31672 27.1853 4.4406 27.6509C5.28351 28 6.35209 28 8.48924 28Z";
  const FT_FILE_FOLD =
    "M26.3909 7.37445L19.0525 0V3.77445C19.0525 4.89271 19.0525 5.45184 19.2352 5.89289C19.4788 6.48096 19.946 6.94818 20.5341 7.19176C20.9751 7.37445 21.5342 7.37445 22.6525 7.37445H26.3909Z";
  const FT_MARK_T = "translate(14 16) scale(1.12) translate(-14 -16)";        // dsh FILE_MARK_TRANSFORM
  const FT_MARK_T_LARGE = "translate(14 16) scale(1.22) translate(-14 -16)";  // dsh LARGE_FILE_MARK_TRANSFORM

  /** dsh FileGlyph：文件体（淡）+ 折角（中）+ 类目标记（实），全走 currentColor + fill-opacity */
  function ftGlyph(mark, transform) {
    const body = `<path d="${FT_FILE_BODY}" fill-opacity="0.18"/>`;
    const fold = `<path d="${FT_FILE_FOLD}" fill-opacity="0.45"/>`;
    const g = mark ? `<g transform="${transform || FT_MARK_T}">${mark}</g>` : "";
    return body + fold + g;
  }
  const FT_MARK_CODE =
    '<path d="M8.61 16.3601L11.76 18.3901V20.1401L7 17.0601V15.6601L11.76 12.5801V14.3301L8.61 16.3601Z"/><path d="M16.1918 14.3301V12.5801L20.9518 15.6601V17.0601L16.1918 20.1401V18.3901L19.3418 16.3601L16.1918 14.3301Z"/>';
  const FT_MARK_IMAGE =
    '<path d="M10.4212 15.9204C10.5756 15.6558 10.9579 15.6558 11.1123 15.9204L13.6493 20.2696C13.8048 20.5362 13.6125 20.8711 13.3037 20.8711H8.22974C7.92102 20.8711 7.72868 20.5362 7.88423 20.2696L10.4212 15.9204Z"/><path d="M15.4981 13.186C15.6505 12.9117 16.0451 12.9117 16.1975 13.186L20.1368 20.2769C20.2849 20.5435 20.0922 20.8711 19.7872 20.8711H11.9084C11.6034 20.8711 11.4107 20.5435 11.5588 20.2769L15.4981 13.186Z"/><path d="M11.8603 11.3997C11.8603 12.286 11.1418 13.0045 10.2555 13.0045C9.36924 13.0045 8.65076 12.286 8.65076 11.3997C8.65076 10.5134 9.36924 9.79492 10.2555 9.79492C11.1418 9.79492 11.8603 10.5134 11.8603 11.3997Z"/>';
  const FT_MARK_HTML =
    '<path fill-rule="evenodd" clip-rule="evenodd" d="M13.9994 9.68298C17.212 9.68298 19.8167 12.2872 19.8168 15.4997C19.8168 18.7123 17.2121 21.3171 13.9994 21.3171C10.7869 21.3169 8.18274 18.7122 8.18274 15.4997C8.1829 12.2873 10.787 9.68315 13.9994 9.68298ZM9.26213 16.0247C9.47025 17.9241 10.7936 19.4876 12.5639 20.0463C12.42 19.7977 12.2952 19.5152 12.1879 19.2116C11.885 18.3541 11.693 17.2434 11.6424 16.0247H9.26213ZM16.3565 16.0247C16.3059 17.2434 16.1145 18.3542 15.8116 19.2116C15.7044 19.5151 15.5788 19.7971 15.435 20.0456C17.2054 19.487 18.5293 17.9242 18.7374 16.0247H16.3565ZM12.6938 16.0247C12.7439 17.1459 12.9212 18.1334 13.1784 18.8616C13.332 19.2962 13.503 19.61 13.6686 19.805C13.834 19.9996 13.9473 20.0256 13.9994 20.0258C14.0514 20.0258 14.1651 20.0002 14.331 19.805C14.4966 19.61 14.6676 19.2962 14.8211 18.8616C15.0784 18.1334 15.2557 17.1459 15.3058 16.0247H12.6938ZM13.9994 10.733C13.9473 10.7331 13.834 10.7598 13.6686 10.9545C13.503 11.1494 13.3319 11.4633 13.1784 11.8978C12.903 12.6777 12.7188 13.7545 12.6849 14.9747H15.3147C15.2808 13.7545 15.0966 12.6777 14.8211 11.8978C14.6676 11.4633 14.4965 11.1494 14.331 10.9545C14.1651 10.7593 14.0514 10.733 13.9994 10.733ZM15.5888 11.0051C15.6701 11.1756 15.7444 11.3576 15.8116 11.5478C16.1343 12.4613 16.3308 13.6619 16.3647 14.9747H18.7374C18.5352 13.1307 17.2817 11.6036 15.5888 11.0051ZM12.4101 11.0051C10.7174 11.6037 9.46428 13.1308 9.26213 14.9747H11.6349C11.6688 13.6619 11.8652 12.4613 12.1879 11.5478C12.2551 11.3577 12.3288 11.1756 12.4101 11.0051Z"/>';
  const FT_MARK_VIDEO =
    '<path d="M17.5 14.634C18.1667 15.0189 18.1667 15.9811 17.5 16.366L11.5 19.8301C10.8333 20.215 10 19.7339 10 18.9641L10 12.0359C10 11.2661 10.8333 10.785 11.5 11.1699L17.5 14.634Z"/>';
  const FT_MARK_MARKDOWN =
    '<path d="M8.7588 19.5V14.6H9.8998L11.9298 17.932H11.3278L13.3018 14.6H14.4428L14.4568 19.5H13.1828L13.1688 16.539H13.3858L11.9088 19.017H11.2928L9.7738 16.539H10.0398V19.5H8.7588ZM15.4375 19.5V14.6H17.7545C18.2958 14.6 18.7718 14.7003 19.1825 14.901C19.5932 15.1017 19.9128 15.384 20.1415 15.748C20.3748 16.112 20.4915 16.546 20.4915 17.05C20.4915 17.5493 20.3748 17.9833 20.1415 18.352C19.9128 18.716 19.5932 18.9983 19.1825 19.199C18.7718 19.3997 18.2958 19.5 17.7545 19.5H15.4375ZM16.8235 18.394H17.6985C17.9785 18.394 18.2212 18.3427 18.4265 18.24C18.6365 18.1327 18.7998 17.9787 18.9165 17.778C19.0332 17.5727 19.0915 17.33 19.0915 17.05C19.0915 16.7653 19.0332 16.5227 18.9165 16.322C18.7998 16.1213 18.6365 15.9697 18.4265 15.867C18.2212 15.7597 17.9785 15.706 17.6985 15.706H16.8235V18.394Z"/>';
  const FT_MARK_PDF =
    '<path d="M6.80616 19.5V14.6H9.04616C9.49416 14.6 9.87916 14.6723 10.2012 14.817C10.5278 14.9617 10.7798 15.1717 10.9572 15.447C11.1345 15.7177 11.2232 16.0397 11.2232 16.413C11.2232 16.7817 11.1345 17.1013 10.9572 17.372C10.7798 17.6427 10.5278 17.8527 10.2012 18.002C9.87916 18.1467 9.49416 18.219 9.04616 18.219H7.57616L8.19216 17.617V19.5H6.80616ZM8.19216 17.764L7.57616 17.127H8.96216C9.2515 17.127 9.46616 17.064 9.60616 16.938C9.75083 16.812 9.82316 16.637 9.82316 16.413C9.82316 16.1843 9.75083 16.007 9.60616 15.881C9.46616 15.755 9.2515 15.692 8.96216 15.692H7.57616L8.19216 15.055V17.764ZM11.8989 19.5V14.6H14.2159C14.7573 14.6 15.2333 14.7003 15.6439 14.901C16.0546 15.1017 16.3743 15.384 16.6029 15.748C16.8363 16.112 16.9529 16.546 16.9529 17.05C16.9529 17.5493 16.8363 17.9833 16.6029 18.352C16.3743 18.716 16.0546 18.9983 15.6439 19.199C15.2333 19.3997 14.7573 19.5 14.2159 19.5H11.8989ZM13.2849 18.394H14.1599C14.4399 18.394 14.6826 18.3427 14.8879 18.24C15.0979 18.1327 15.2613 17.9787 15.3779 17.778C15.4946 17.5727 15.5529 17.33 15.5529 17.05C15.5529 16.7653 15.4946 16.5227 15.3779 16.322C15.2613 16.1213 15.0979 15.9697 14.8879 15.867C14.6826 15.7597 14.4399 15.706 14.1599 15.706H13.2849V18.394ZM17.6821 19.5V14.6H21.5251V15.671H19.0681V19.5H17.6821ZM18.9701 17.82V16.749H21.2311V17.82H18.9701Z"/>';
  const FT_MARK_PPT =
    '<path d="M11.0132 20.5V13.5H14.2132C14.8532 13.5 15.4032 13.6033 15.8632 13.81C16.3299 14.0167 16.6899 14.3167 16.9432 14.71C17.1966 15.0967 17.3232 15.5567 17.3232 16.09C17.3232 16.6167 17.1966 17.0733 16.9432 17.46C16.6899 17.8467 16.3299 18.1467 15.8632 18.36C15.4032 18.5667 14.8532 18.67 14.2132 18.67H12.1132L12.9932 17.81V20.5H11.0132ZM12.9932 18.02L12.1132 17.11H14.0932C14.5066 17.11 14.8132 17.02 15.0132 16.84C15.2199 16.66 15.3232 16.41 15.3232 16.09C15.3232 15.7633 15.2199 15.51 15.0132 15.33C14.8132 15.15 14.5066 15.06 14.0932 15.06H12.1132L12.9932 14.15V18.02Z"/>';
  const FT_MARK_WORD =
    '<path d="M10.5118 20.5L8.24179 13.5H10.2818L12.1918 19.56H11.1618L13.1718 13.5H14.9918L16.8918 19.56H15.9018L17.8718 13.5H19.7618L17.4918 20.5H15.3718L13.7518 15.35H14.3218L12.6318 20.5H10.5118Z"/>';
  const FT_MARK_EXCEL =
    '<path d="M10.2932 20.5L13.3532 16.25L13.3432 17.66L10.4032 13.5H12.6332L14.5132 16.21L13.5632 16.22L15.4132 13.5H17.5532L14.6132 17.58V16.18L17.7132 20.5H15.4332L13.5232 17.65H14.4332L12.5532 20.5H10.2932Z"/>';
  // 目录 close/open（icons/index.tsx:685 / :677）
  const ICON_FOLDER_CLOSE =
    '<path d="M5.05582 0.518756L4.50669 0.86654L5.05582 0.518756ZM13 9.4837L13.65 9.4837L13.65 3.53962L13 3.53962L12.35 3.53962L12.35 9.4837L13 9.4837ZM11.3264 1.86603L11.3264 1.21603L6.52313 1.21603L6.52313 1.86603L6.52313 2.51603L11.3264 2.51603L11.3264 1.86603ZM5.58054 1.34727L6.12968 0.999489L5.60495 0.170972L5.05582 0.518756L4.50669 0.86654L5.03141 1.69506L5.58054 1.34727ZM4.11323 1.23058e-13L4.11323 -0.65L1.67359 -0.65L1.67359 5.00699e-14L1.67359 0.65L4.11323 0.65L4.11323 1.23058e-13ZM0 1.67359L-0.65 1.67359L-0.65 9.4837L0 9.4837L0.65 9.4837L0.65 1.67359L0 1.67359ZM11.3264 11.1573L11.3264 10.5073L1.67359 10.5073L1.67359 11.1573L1.67359 11.8073L11.3264 11.8073L11.3264 11.1573ZM0 9.4837L-0.65 9.4837C-0.65 10.767 0.390308 11.8073 1.67359 11.8073L1.67359 11.1573L1.67359 10.5073C1.10828 10.5073 0.65 10.049 0.65 9.4837L0 9.4837ZM1.67359 5.00699e-14L1.67359 -0.65C0.390307 -0.65 -0.65 0.390309 -0.65 1.67359L0 1.67359L0.65 1.67359C0.65 1.10828 1.10828 0.65 1.67359 0.65L1.67359 5.00699e-14ZM5.05582 0.518756L5.60495 0.170972C5.28121 -0.340193 4.71829 -0.65 4.11323 -0.65L4.11323 1.23058e-13L4.11323 0.65C4.27282 0.65 4.4213 0.731715 4.50669 0.86654L5.05582 0.518756ZM6.52313 1.86603L6.52313 1.21603C6.36354 1.21603 6.21507 1.13431 6.12968 0.999489L5.58054 1.34727L5.03141 1.69506C5.35515 2.20622 5.91808 2.51603 6.52313 2.51603L6.52313 1.86603ZM13 3.53962L13.65 3.53962C13.65 2.25634 12.6097 1.21603 11.3264 1.21603L11.3264 1.86603L11.3264 2.51603C11.8917 2.51603 12.35 2.97431 12.35 3.53962L13 3.53962ZM13 9.4837L12.35 9.4837C12.35 10.049 11.8917 10.5073 11.3264 10.5073L11.3264 11.1573L11.3264 11.8073C12.6097 11.8073 13.65 10.767 13.65 9.4837L13 9.4837Z"/>';
  const ICON_FOLDER_OPEN =
    '<path d="M5.19629 1.57104C5.81144 1.5711 6.38623 1.8786 6.72754 2.39038L7.19922 3.09839C7.28454 3.22635 7.42824 3.30344 7.58203 3.30347H12.1699C13.5039 3.30348 14.5859 4.38548 14.5859 5.71948V6.62671C15.2694 7.02689 15.6605 7.85012 15.4385 8.68726L14.3848 12.658C14.1037 13.7164 13.1449 14.4527 12.0498 14.4529H2.91699C1.51651 14.4529 0.451662 13.2814 0.501954 11.9519V3.98706C0.501954 2.65305 1.58396 1.57104 2.91797 1.57104H5.19629ZM3.7793 7.75562C3.30994 7.75562 2.89883 8.07153 2.77832 8.52515L1.91602 11.7722C1.74167 12.4291 2.23734 13.073 2.91699 13.073H12.0498C12.5191 13.0728 12.9304 12.757 13.0508 12.3035L14.1045 8.33374C14.1819 8.04202 13.9619 7.756 13.6602 7.75562H3.7793ZM2.91797 2.9519C2.34625 2.9519 1.88281 3.41534 1.88281 3.98706V7.2937C2.33068 6.7269 3.02249 6.37476 3.7793 6.37476H13.2051V5.71948C13.2051 5.14777 12.7416 4.68434 12.1699 4.68433H7.58203C6.96675 4.6843 6.39209 4.37595 6.05078 3.86401L5.5791 3.15601C5.49379 3.02821 5.34995 2.95196 5.19629 2.9519H2.91797Z"/>'
    + '<path opacity="0.2" d="M13.6602 7.75525C13.9618 7.7556 14.1815 8.04179 14.1045 8.33337L13.0508 12.3031C12.9304 12.7567 12.5191 13.0725 12.0498 13.0726H2.91701C2.23744 13.0725 1.7417 12.4287 1.91603 11.7719L2.77834 8.52478C2.89898 8.07146 3.31018 7.75532 3.77931 7.75525H13.6602ZM5.1963 2.95154C5.34985 2.95159 5.49377 3.02803 5.57912 3.15564L6.0508 3.86365C6.39205 4.37553 6.96685 4.68385 7.58205 4.68396H12.1699C12.7416 4.68396 13.2049 5.14754 13.2051 5.71912V6.37439H3.77931C3.02267 6.37444 2.33067 6.72671 1.88283 7.29333V3.98669C1.88299 3.4152 2.34649 2.95168 2.91798 2.95154H5.1963Z"/>';

  const ICON_BOXES = {
    // icons/index.tsx:192（注释：树展开箭头，消费方展开时旋转 90°）；:685 / :677；:692
    triangleRight: "0 0 14 14",
    folderClose: "0 0 16 16",
    folderOpen: "0 0 16 16",
    treeCorner: "-0.5 0 8.5 10.5",
    // FileTypeIcon.tsx：FileGlyph 一律 viewBox 0 0 28 28
    ftMarkdown: "0 0 28 28",
    ftCode: "0 0 28 28",
    ftImage: "0 0 28 28",
    ftHtml: "0 0 28 28",
    ftPdf: "0 0 28 28",
    ftPpt: "0 0 28 28",
    ftVideo: "0 0 28 28",
    ftWord: "0 0 28 28",
    ftExcel: "0 0 28 28",
    ftOther: "0 0 28 28",
    ftFolder: "0 0 16 16",
  };
  const ICON_BODIES = {
    triangleRight: '<path d="M4.25 2.82782L4.25 11.1722C4.25 11.6622 4.84243 11.9076 5.18891 11.5611L9.36109 7.38891C9.57588 7.17412 9.57588 6.82588 9.36109 6.61109L5.18891 2.43891C4.84243 2.09243 4.25 2.33782 4.25 2.82782Z"/>',
    folderClose: ICON_FOLDER_CLOSE,
    folderOpen: ICON_FOLDER_OPEN,
    treeCorner: '<path d="M0 0L-0.5 0L-0.5 7L0 7L0.5 7L0.5 0L0 0ZM3 10L3 10.5L8 10.5L8 10L8 9.5L3 9.5L3 10ZM0 7L-0.5 7C-0.5 8.933 1.067 10.5 3 10.5L3 10L3 9.5C1.61929 9.5 0.5 8.38071 0.5 7L0 7Z"/>',
    ftMarkdown: ftGlyph(FT_MARK_MARKDOWN, FT_MARK_T_LARGE),
    ftCode: ftGlyph(FT_MARK_CODE),
    ftImage: ftGlyph(FT_MARK_IMAGE),
    ftHtml: ftGlyph(FT_MARK_HTML),
    ftPdf: ftGlyph(FT_MARK_PDF, FT_MARK_T_LARGE),
    ftPpt: ftGlyph(FT_MARK_PPT, FT_MARK_T_LARGE),
    ftVideo: ftGlyph(FT_MARK_VIDEO),
    ftWord: ftGlyph(FT_MARK_WORD, FT_MARK_T_LARGE),
    ftExcel: ftGlyph(FT_MARK_EXCEL, FT_MARK_T_LARGE),
    ftOther: ftGlyph("", null),
    // folder 类：树里由 16px open/close 对承担；文件分类不会产出 folder，此处复用 close 图形补齐类目
    ftFolder: ICON_FOLDER_CLOSE,
  };

  /** 生成一个内联 SVG 图标；cls 为附加 class。未知名返回空串（不抛错） */
  function icon(name, cls) {
    const box = ICON_BOXES[name];
    const body = ICON_BODIES[name];
    if (!box || !body) return "";
    return `<svg class="${cls || ""}" viewBox="${box}" fill="currentColor" aria-hidden="true" focusable="false">${body}</svg>`;
  }

  /* ---------------------------------------------------------------------------
   * C. 文件类型分类（口径同 FileTypeIcon.tsx 的 EXTENSION_TYPES / NAME_TYPES；
   *    代码类一律 'code'——上游按品牌分支的 CodeFileType 徽标不移植）
   */
  const FT_EXT_TYPES = {
    md: "markdown", mdx: "markdown", markdown: "markdown",
    html: "html", htm: "html",
    png: "image", jpg: "image", jpeg: "image", gif: "image", svg: "image", webp: "image",
    avif: "image", bmp: "image", ico: "image", tif: "image", tiff: "image", heic: "image", heif: "image",
    pdf: "pdf",
    ppt: "ppt", pptx: "ppt", key: "ppt",
    mp4: "video", mov: "video", m4v: "video", webm: "video", mkv: "video", avi: "video", mpg: "video", mpeg: "video",
    doc: "word", docx: "word", rtf: "word", odt: "word", pages: "word",
    xls: "excel", xlsx: "excel", xlsm: "excel", numbers: "excel",
    scss: "code", sass: "code", less: "code", vue: "code", svelte: "code", astro: "code",
    bat: "code", cmd: "code", csv: "code", tsv: "code", css: "code", xml: "code",
    js: "code", jsx: "code", ts: "code", tsx: "code", mjs: "code", cjs: "code", cts: "code", mts: "code",
    json: "code", json5: "code", jsonc: "code", yaml: "code", yml: "code", toml: "code",
    ini: "code", cfg: "code", env: "code",
    py: "code", pyi: "code", pyw: "code", pyx: "code", rb: "code", rs: "code", go: "code",
    java: "code", kt: "code", kts: "code", c: "code", cc: "code", cpp: "code", cxx: "code",
    h: "code", hh: "code", hpp: "code", hxx: "code", cs: "code", php: "code", swift: "code",
    sql: "code", sh: "code", bash: "code", zsh: "code", fish: "code", ps1: "code",
    psd1: "code", psm1: "code", lua: "code", r: "code", pl: "code", scala: "code",
    clj: "code", cljs: "code", ex: "code", exs: "code", erl: "code", hs: "code", dart: "code",
    proto: "code", graphql: "code", gql: "code", zig: "code", wasm: "code", sol: "code",
  };
  const FT_NAME_TYPES = { readme: "markdown", changelog: "markdown", contributing: "markdown" };
  const FT_CATEGORY_ICON = {
    markdown: "ftMarkdown", code: "ftCode", image: "ftImage", html: "ftHtml", pdf: "ftPdf",
    ppt: "ftPpt", video: "ftVideo", word: "ftWord", excel: "ftExcel", folder: "ftFolder", other: "ftOther",
  };

  /** 路径 → 文件类型类目（大小写不敏感；无扩展名/未知 → 'other'） */
  function classifyFileType(filePath) {
    const name = basename(filePath).toLowerCase();
    const dot = name.lastIndexOf(".");
    const ext = dot < 0 ? "" : name.slice(dot + 1);
    return FT_NAME_TYPES[name] || FT_EXT_TYPES[ext] || "other";
  }

  /* ---------------------------------------------------------------------------
   * D. 缩进连接线：IconTreeCorner8x10（icons/index.tsx:692）逐层画竖直导轨，末层画折角。
   *    颜色走 CSS 的 --border，深浅主题同源。
   */
  function treeGuides(depth) {
    if (!depth) return "";
    let inner = "";
    for (let i = 1; i < depth; i++) inner += '<span class="-tree-guide-rail"></span>';
    inner += `<span class="-tree-guide-corner">${icon("treeCorner")}</span>`;
    return `<span class="-tree-guides" aria-hidden="true">${inner}</span>`;
  }

  // 供 Node VM 单测（scripts/benchmark/maintenance/file_tree_icons_test.js）读取；
  // 浏览器里 = window.MemoriaTreeIcons（只读自检面，不参与渲染）。
  if (typeof window !== "undefined") {
    window.MemoriaTreeIcons = {
      icon, classifyFileType, treeGuides,
      names: Object.keys(ICON_BODIES),
      categories: FT_CATEGORY_ICON,
    };
  }

  return {
    init,
    render: renderFileTree,                    // 原 renderFileTree（app.js refreshFiles/openFile/closeKb/closeTabAt/KP 写回后重绘）
    expandToPath: ensureTreeExpandedForPath,   // 原 ensureTreeExpandedForPath（openFile 展开当前文件所在目录）
    revealDir,                                 // 对话栏「文件夹引用」chip 的跳转目标（展开并滚动到位）
  };
})(typeof window !== "undefined" ? window : globalThis);
