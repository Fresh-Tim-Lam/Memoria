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
        _lastSel = { type: "dir", path: dirPath };
        const expanded = ensureTreeExpandedSet();
        if (expanded.has(dirPath)) expanded.delete(dirPath);
        else expanded.add(dirPath);
        renderFileTree();
      });
    });
    el.querySelectorAll(".-tree-item").forEach((node) => {
      node.addEventListener("click", () => {
        _lastSel = { type: "file", path: node.dataset.path };
        navigateToFile(node.dataset.path);
      });
    });
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
      if (baseDir) ensureTreeExpandedSet().add(baseDir);
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
      if (baseDir) ensureTreeExpandedSet().add(baseDir);
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
    if (state.currentPath) ensureTreeExpandedForPath(state.currentPath);
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

  return {
    init,
    render: renderFileTree,                    // 原 renderFileTree（app.js refreshFiles/openFile/closeKb/closeTabAt/KP 写回后重绘）
    expandToPath: ensureTreeExpandedForPath,   // 原 ensureTreeExpandedForPath（openFile 展开当前文件所在目录）
  };
})(typeof window !== "undefined" ? window : globalThis);
