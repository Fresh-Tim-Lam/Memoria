/**
 * 图片插入与图片管理（原 app.js「图片插入与管理 / 图片管理视图 / 图片行内属性提交」子系统，
 * 2026-09-04 抽出）。
 *
 * 自包含：图片选择入库（btn-insert-image、源码区/预览区右键「插入图片」）→ 独占行写回源码并入撤销栈；
 * 预览区图片右键替换/删除（仅删引用）；图片管理弹窗（列表/刷新/诊断/清理/卡片插入/删除）；
 * 图片属性（align/width/name-size/name）与名称（alt）编辑的源码行写回（监听
 * memoria:image-attr / memoria:image-caption / memoria:open-image-manager，edit-handler.js 派发）。
 * DOM/事件绑定全部由本模块 init() 完成，不依赖 app.js 的 bindEvents：
 *   - btn-insert-image 可用性状态机（click/mousedown/focusin/selectionchange，原 app.js bindEvents）
 *   - 预览区图片右键菜单（原 app.js bindPreviewSelectionMenu 内图片分支）
 *   - 上述三个 CustomEvent 监听（原 app.js 顶层 document 监听）
 *
 * 依赖 window.MemoriaApp（app.js 导出的应用服务门面）：
 *   state / call / T / esc / setStatus / setStatusError
 *   closestLineEl / renumberSourceLines / scheduleRenderSync / markDirty
 *   srcPushBefore / srcAfterEdit / srcResetCoalesce
 *   renderEditor / renderPreview / showTreeContextMenu / confirmTreeAction
 * （源编辑器/撤销/重渲染/通用弹窗等私有服务为本次拆分在门面上追加，见 app.js 门面注释）
 *
 * 文案全部经 T('key') 取当前语言（复用 img.* / common.* / dialog.* / app.* 键族）。
 */
window.MemoriaImageTools = (function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const A = () => window.MemoriaApp || {};

  // app.js 导出 state 为同一对象引用（永不整体替换），捕获一次后属性读写均实时可见
  const state = A().state || {};

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
  const setStatusError = (...args) => {
    A().setStatusError?.(...args);
  };

  // ── app.js 私有服务（门面追加项）：源码行写回/撤销/重渲染/右键菜单/确认弹窗 ──
  const closestLineEl = (node) => A().closestLineEl?.(node) || null;
  const renumberSourceLines = () => A().renumberSourceLines?.();
  const scheduleRenderSync = () => A().scheduleRenderSync?.();
  const markDirty = () => A().markDirty?.();
  const _srcPushBefore = () => A().srcPushBefore?.();
  const _srcAfterEdit = () => A().srcAfterEdit?.();
  const srcResetCoalesce = () => A().srcResetCoalesce?.();
  const renderEditor = (doc) => A().renderEditor?.(doc);
  const renderPreview = (doc) => A().renderPreview?.(doc);
  const showTreeContextMenu = (x, y, items) => A().showTreeContextMenu?.(x, y, items);
  const confirmTreeAction = (title, message, okLabel, cb) =>
    A().confirmTreeAction?.(title, message, okLabel, cb);

  // ── 图片插入（复制入库 .memoria/images/，阶段 D） ────────────────

  async function startInsertImage(insertAtLine) {
    if (!state.kbPath) {
      setStatus(T("app.openKbFirst"));
      return;
    }
    if (!state.currentPath) {
      setStatus(T("img.insert.openDocFirst"));
      return;
    }
    const local = await call("select_image_file");
    if (!local) return;
    const res = await call("import_image", local);
    if (!res || res.status !== "ok") {
      setStatusError(T("img.insert.importFailed"), (res && res.message) || T("common.unknownError"));
      return;
    }
    const alt = String(res.name || "").replace(/\.[^.]+$/, "");
    // URL 用尖括号包裹：文件名可能含中文/空格（如 Windows 截图），裸 URL 会被
    // marked 在空格处截断导致不渲染为图片
    if (!insertSourceLine("![" + alt + "](<" + res.relPath + ">)", insertAtLine)) {
      setStatusError(T("img.insert.failed"), T("img.insert.noEditor"));
      return;
    }
    setStatus(T("img.insert.stored"), res.relPath);
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
    srcResetCoalesce();
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
    // 新增行遵循当前编辑模式（关闭编辑时新增行保持只读）
    content.contentEditable = !window.MemoriaEditHandler || window.MemoriaEditHandler.editMode ? "true" : "false";
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
    srcResetCoalesce();
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
      { label: T("img.edit.replace"), action: () => replaceImageAtLine(lineNum) },
      { label: T("img.edit.deleteRef"), danger: true, action: () => deleteImageAtLine(lineNum) },
    ]);
  }

  async function replaceImageAtLine(lineNum) {
    const local = await call("select_image_file");
    if (!local) return;
    const res = await call("import_image", local);
    if (!res || res.status !== "ok") {
      setStatusError(T("img.insert.importFailed"), (res && res.message) || T("common.unknownError"));
      return;
    }
    const lines = (state.doc.body || "").split("\n");
    const raw = lines[lineNum - 1] || "";
    const m = raw.match(/^!\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^)\s]+))((?:\s+"[^"]*")?)\)/);
    if (!m) {
      setStatusError(T("img.edit.replaceFailed"), T("img.edit.notImageLine"));
      return;
    }
    lines[lineNum - 1] = "![" + m[1] + "](<" + res.relPath + ">" + (m[4] || "") + ")";
    await applyImageEditLines(lines);
    setStatus(T("img.edit.replaced"), res.relPath);
  }

  function deleteImageAtLine(lineNum) {
    const lines = (state.doc.body || "").split("\n");
    if (lineNum - 1 >= lines.length) return;
    lines.splice(lineNum - 1, 1);
    applyImageEditLines(lines);
    setStatus(T("img.del.refsDone"));
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
          <span>${T("img.title")}</span>
          <span class="-image-mgr-close" data-act="close" title="${T("dialog.closeTitle")}">✕</span>
        </div>
        <div class="-image-mgr-toolbar">
          <span class="-image-mgr-stat" id="imgr-stat">${T("img.loading")}</span>
          <button type="button" class="-btn" data-act="refresh">${T("img.refresh")}</button>
          <button type="button" class="-btn" data-act="diagnose">${T("img.diagnose")}</button>
          <button type="button" class="-btn danger" data-act="cleanup">${T("img.cleanup")}</button>
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
      setStatusError(T("img.diag.failed"), (res && res.message) || T("common.unknownError"));
      return;
    }
    const unreg = res.unregistered || [];
    const missing = res.missing || [];
    const atLine = (doc, line) => T("img.atLine", { doc: esc(doc), line });
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.id = "-img-diagnose";
    let html = `
      <div class="-modal-backdrop"></div>
      <div class="-modal-box -img-diag-box">
        <div class="-modal-header">
          <span>${T("img.diag.title")}</span>
          <span class="-image-mgr-close" data-act="close" title="${T("dialog.closeTitle")}">✕</span>
        </div>`;
    if (!unreg.length && !missing.length) {
      html += `<div class="-img-diag-body"><div class="-img-diag-ok">${T("img.diag.clean")}</div></div></div>`;
    } else {
      if (unreg.length) {
        const reason = T("img.diag.unregReason");
        html += `<div class="-img-diag-body">
          <div class="-img-diag-title">${T("img.diag.unregTitle", { n: unreg.length, reason })}</div>
          <ul class="-img-diag-list">` +
          unreg.map((u) => `<li><code>${esc(u.src)}</code><span>${atLine(u.doc, u.line)}${u.exists ? "" : T("img.diag.fileMissing")}</span></li>`).join("") +
          `</ul>
          <button type="button" class="-btn" data-act="fix">${T("img.diag.fix")}</button>
        </div>`;
      }
      if (missing.length) {
        html += `<div class="-img-diag-body">
          <div class="-img-diag-title">${T("img.diag.missingTitle", { n: missing.length })}</div>
          <ul class="-img-diag-list">` +
          missing.map((u) => `<li><code>${esc(u.url)}</code><span>${atLine(u.doc, u.line)}${T("img.diag.fileNotExists")}</span></li>`).join("") +
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
          setStatus(T("img.status.fixDone"), T("img.status.rewritten", { n: r.fixed }));
          overlay.remove();
          renderImageList();
        } else {
          setStatusError(T("img.status.fixFailed"), (r && r.message) || T("common.unknownError"));
        }
      });
    }
  }

  async function renderImageList() {
    const grid = $("#imgr-grid");
    const stat = $("#imgr-stat");
    if (!grid || !stat) return;
    grid.innerHTML = `<div class="-image-mgr-empty">${T("img.loading")}</div>`;
    const res = await call("list_images");
    const imgs = (res && res.images) || [];
    const used = imgs.filter((x) => x.referenced).length;
    stat.textContent = T("img.statSummary", { total: imgs.length, used, unused: imgs.length - used });
    if (!imgs.length) {
      grid.innerHTML = `<div class="-image-mgr-empty">${T("img.emptyKb")}</div>`;
      return;
    }
    const sep = T("img.listSep");
    let html = "";
    for (const im of imgs) {
      const refs = im.referencedBy || [];
      const tag = im.referenced
        ? `<span class="-img-tag -img-tag-used">${T("img.tagUsed", { n: refs.length })}</span>`
        : `<span class="-img-tag -img-tag-unused">${T("img.tagUnused")}</span>`;
      const refTxt = im.referenced ? T("img.refsUsed", { files: refs.join(sep) }) : T("img.refsUnused");
      html += `<div class="-image-card" data-rel="${esc(im.relPath)}" data-name="${esc(im.name)}" data-referenced="${im.referenced ? 1 : 0}">
        <img class="-image-card-thumb" src="/files/${esc(im.relPath)}" alt="${esc(im.name)}" loading="lazy">
        <div class="-image-card-info">
          <div class="-image-card-name" title="${esc(im.name)}">${esc(im.name)}${tag}</div>
          <div class="-image-card-meta">${fmtImageSize(im.size || 0)}</div>
          <div class="-image-card-refs" title="${esc(refTxt)}">${esc(refTxt)}</div>
        </div>
        <div class="-image-card-actions">
          <button type="button" class="-btn" data-act="insert">${T("img.insert")}</button>
          <button type="button" class="-btn danger" data-act="delete">${T("img.delete")}</button>
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
      setStatus(T("img.insert.openDocFirst"));
      return;
    }
    const alt = String(name || "").replace(/\.[^.]+$/, "");
    if (insertSourceLine("![" + alt + "](<" + rel + '> "width=300")')) {
      setStatus(T("img.insert.done"), rel);
    } else {
      setStatusError(T("img.insert.failed"), T("img.insert.noEditor"));
    }
  }

  function deleteImageFromManager(rel, name, referenced) {
    if (referenced) {
      const n = (state.doc.lines || []).filter(
        (l) => l.includes(rel) || l.includes("/files/" + rel)
      ).length;
      if (!n) {
        confirmTreeAction(
          T("img.del.blockedTitle"),
          T("img.del.blockedBody"),
          T("img.del.gotIt"),
          () => {}
        );
        return;
      }
      confirmTreeAction(
        T("img.del.refTitle"),
        T("img.del.refBody", { n }),
        T("img.del.onlyRefs"),
        () => {
          const lines = (state.doc.body || "")
            .split("\n")
            .filter((l) => !(l.includes(rel) || l.includes("/files/" + rel)));
          applyImageEditLines(lines);
          setStatus(T("img.del.refsDone"));
          renderImageList();
        }
      );
    } else {
      confirmTreeAction(
        T("img.del.fileTitle"),
        T("img.del.fileBody", { name }),
        T("img.del.fileBtn"),
        async () => {
          const res = await call("cleanup_unused_images", [rel]);
          if (res && res.status === "ok" && (res.deleted || []).length) {
            setStatus(T("img.del.fileDone"), name);
            renderImageList();
          } else {
            setStatusError(T("img.del.failed"), (res && res.message) || T("img.del.fileGone"));
          }
        }
      );
    }
  }

  async function cleanupUnusedImages() {
    const res = await call("unused_images");
    const un = (res && res.images) || [];
    if (!un.length) {
      setStatus(T("img.cleanup.none"));
      renderImageList();
      return;
    }
    const sep = T("img.listSep");
    const names = un
      .slice(0, 5)
      .map((x) => x.name)
      .join(sep);
    const more = un.length > 5 ? T("img.cleanup.more", { n: un.length }) : "";
    confirmTreeAction(
      T("img.cleanup.title"),
      T("img.cleanup.body", { n: un.length, names, more }),
      T("img.cleanup.btn"),
      async () => {
        const r = await call("cleanup_unused_images");
        if (r && r.status === "ok") {
          setStatus(T("img.cleanup.done", { n: (r.deleted || []).length }));
          renderImageList();
        } else {
          setStatusError(T("img.cleanup.failed"), (r && r.message) || T("common.unknownError"));
        }
      }
    );
  }

  /** 更新图片源码行属性（阶段 F 工具栏：对齐/大小滑条；阶段 G：名称字号/显隐），返回新行或 null */
  function updateImageAttrsLine(line, attrs) {
    // url 允许含空格（`<...>` 尖括号包裹形式）或为空；属性串可缺省
    const m = line.match(/^(!\[[^\]]*\]\([\s\S]*?)(\s+"[^"]*")?(\s*\)\s*)$/);
    if (!m) return null;
    const title = m[2] ? m[2].replace(/^\s+"|"$/g, "") : "";
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
    const m = line.match(/^(!\[)([^\]]*)(\]\([\s\S]*?)(\s+"[^"]*")?(\s*\)\s*)$/);
    if (!m) return null;
    return m[1] + caption + m[3] + (m[4] || "") + m[5];
  }

  function init() {
    // 图片插入按钮 → 图片选择入库后写回源码（原 app.js bindEvents）
    $("#btn-insert-image")?.addEventListener("click", () => startInsertImage());
    // 图片插入按钮：mousedown 阻止焦点从预览区转移（不触发 focusin 的禁用刷新）。
    // 否则点击按钮的瞬间焦点离开预览区 → _caretInPreview=false → 按钮被禁用 → click 无法触发
    // （焦点状态机下"点击即失效"的经典缺陷）。阻止聚焦后 focus 保持在预览区，
    // 按钮保持可点，且预览区 selection 完好，插入位置定位（previewCursorSourceLine）不受影响。
    $("#btn-insert-image")?.addEventListener("mousedown", (e) => {
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

    // 图片加载失败提示：红框标出缺失图并给出明确文案（此前表现为“图片不显示”，难定位）。
    document.addEventListener(
      "error",
      (e) => {
        const t = e.target;
        if (!t || t.tagName !== "IMG") return;
        if (!(t.closest && t.closest("#preview"))) return;
        const src = t.currentSrc || t.getAttribute("src") || "";
        t.style.outline = "1px dashed #e5534b";
        t.style.filter = "opacity(.55)";
        const name = decodeURIComponent(src.split("/").pop() || src);
        t.title = `${T("img.missing")} ${name}`;
        if (!t.dataset.imgMissing) {
          t.dataset.imgMissing = "1";
          t.alt = (t.alt ? t.alt + " · " : "") + T("img.missing");
        }
        console.warn("[img] 加载失败（文件可能缺失）:", src);
      },
      true
    );

    // 图片注册表自动检查（轻量）：打开/切换知识库立即一次；此后长间隔兜底（降运行压力）。
    const autoCheck = async () => {
      const a = window.MemoriaApp || {};
      if (!(a.state && a.state.kbPath)) return;
      try {
        if (a.call) await a.call("image_registry_auto_check");
      } catch (_) { /* 后台任务失败不打扰用户 */ }
    };
    const _regAppState = () => (window.MemoriaApp && window.MemoriaApp.state) || {};
    const AUTO_CHECK_MS = 5 * 60 * 1000; // 长间隔
    let _regKb = _regAppState().kbPath || "";
    let _regLastRun = Date.now();
    const _regTick = () => {
      const kb = _regAppState().kbPath || "";
      const now = Date.now();
      if (!kb) {
        _regKb = "";
        return;
      }
      if (kb !== _regKb) {
        _regKb = kb;
        autoCheck();
        _regLastRun = now;
        return;
      }
      if (now - _regLastRun >= AUTO_CHECK_MS) {
        _regLastRun = now;
        autoCheck();
      }
    };
    setInterval(_regTick, 30 * 1000);
    _regTick();

    // 预览区图片右键：替换 / 删除（仅删引用）（原 app.js bindPreviewSelectionMenu 图片分支）
    const preview = $("#preview");
    if (preview) {
      preview.addEventListener("contextmenu", (e) => {
        // 编辑模式关闭（只读）：原生菜单已由 app.js 全局 handler 屏蔽，此处直接返回即可
        if (preview.contentEditable !== "true") return;
        const imgEl = e.target.closest("img.-preview-image");
        if (!imgEl) return;
        e.preventDefault();
        const blockEl = imgEl.closest(".-image-block");
        const lineNum = blockEl ? +(blockEl.getAttribute("data--src-line") || 0) : 0;
        if (lineNum > 0) {
          e.stopPropagation();
          showImageContextMenu(e.clientX, e.clientY, lineNum);
        }
      });
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
  }

  return {
    init,
    openImageManager,
    startInsertImage,
    showImageContextMenu,
    refreshImageInsertAvailability,
    previewCursorSourceLine,
  };
})(typeof window !== "undefined" ? window : globalThis);
