/**
 * 0.3.0 统一导入向导（import-spec §7–§9，M3）。
 *
 * 流程：工具栏「导入」→ 源类型选择（flat_file / md_dir / kb_bundle）
 *   → select_import_sources → import_scan（只读预览）
 *   → 清单预览（文件/KP/冲突）+ 复制反馈（JSON/Markdown）
 *   → 冲突逐项/「应用到全部」→ import_execute → 结果。
 *
 * 复用 .-modal 通用浮层：#import-conflict-modal 承担「源选择/预览/冲突」，
 * #import-result-modal 展示结果。文案全部经 T()（import.* 键族）。
 */
window.MemoriaImportFlow = (function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const A = () => window.MemoriaApp || {};
  const t = (k, p) => {
    const a = A();
    return a.T ? a.T(k, p) : k;
  };
  const esc = (s) => {
    const a = A();
    return a.esc ? a.esc(s) : String(s == null ? "" : s);
  };

  let _kind = null;
  let _sources = null;
  let _preview = null; // import_scan 返回 { preview, markdown }
  let _conflicts = null; // 预览阶段冲突条目列表（含 kind/subject/options）
  let _busy = false;
  let _promptText = null; // Agent 整理提示词视图

  const KIND_FLAT = "flat_file";
  const KIND_MD = "md_dir";
  const KIND_BUNDLE = "kb_bundle";
  const KIND_PROMPT = "__prompt";

  // ── 入口 ─────────────────────────────────────────────────────────

  async function start() {
    const a = A();
    if (!a.state || !a.state.kbPath) {
      a.setStatus?.(t("app.openKbFirst"));
      return;
    }
    _resetState();
    renderKindChooser();
    setTitle(t("import.chooseTitle"));
    $("#import-conflict-modal")?.classList.remove("hidden");
  }

  function _resetState() {
    _kind = null;
    _sources = null;
    _preview = null;
    _conflicts = null;
    _promptText = null;
    setImportActionButtons(true);
  }

  function setImportActionButtons(showImport) {
    const confirmBtn = $("#import-conflict-confirm");
    const copyBtn = $("#import-conflict-copy-report");
    if (confirmBtn) confirmBtn.classList.toggle("hidden", !showImport);
    if (copyBtn) copyBtn.classList.toggle("hidden", !showImport);
  }

  function setTitle(text) {
    const span = document.querySelector(
      "#import-conflict-modal .-modal-header > span"
    );
    if (span) span.textContent = text;
  }

  // ── 1. 源类型选择 ────────────────────────────────────────────────

  function renderKindChooser() {
    const body = $("#import-conflict-body");
    if (!body) return;
    const kinds = [
      { id: KIND_FLAT, title: t("import.kindFlat"), desc: t("import.kindFlatDesc") },
      { id: KIND_MD, title: t("import.kindMdDir"), desc: t("import.kindMdDirDesc") },
      { id: KIND_BUNDLE, title: t("import.kindBundle"), desc: t("import.kindBundleDesc") },
      { id: KIND_PROMPT, title: t("import.copyAgentPrompt"), desc: t("import.copyAgentPromptDesc") },
    ];
    body.innerHTML =
      `<div class="-import-kind-list">` +
      kinds
        .map(
          (k) =>
            `<button type="button" class="-btn -import-kind-card" data-import-kind="${k.id}">
               <strong>${esc(k.title)}</strong>
               <span class="-muted">${esc(k.desc)}</span>
             </button>`
        )
        .join("") +
      `</div>`;
    body.querySelectorAll("[data-import-kind]").forEach((btn) => {
      btn.addEventListener("click", () => pickSource(btn.dataset.importKind));
    });
  }

  async function pickSource(kind) {
    const a = A();
    if (_busy) return;
    if (kind === KIND_PROMPT) {
      await loadPrompt();
      return;
    }
    _busy = true;
    try {
      a.setStatus?.(t("import.picking"));
      const picked = await a.call("select_import_sources", kind);
      if (picked.status === "error") {
        a.setStatusError?.(picked.message || t("import.failed"));
        return;
      }
      const sources = picked.sources || [];
      if (!sources.length) return; // 用户取消
      _kind = kind;
      _sources = sources;
      await scanPreview();
    } catch (e) {
      a.setStatusError?.(t("import.failed"), String(e.message || e));
    } finally {
      _busy = false;
    }
  }

  async function loadPrompt() {
    const a = A();
    if (_busy) return;
    _busy = true;
    try {
      a.setStatus?.(t("import.promptLoading"));
      const res = await a.call("get_agent_prompt", "zh-CN");
      if (res.status === "error") {
        a.setStatusError?.(res.message || t("import.failed"));
        return;
      }
      _promptText = res.text || "";
      showPrompt();
    } catch (e) {
      a.setStatusError?.(t("import.failed"), String(e.message || e));
    } finally {
      _busy = false;
    }
  }

  function showPrompt() {
    const body = $("#import-conflict-body");
    if (!body) return;
    setTitle(t("import.promptTitle"));
    setImportActionButtons(false);
    const usage = [
      t("import.promptUsage1"),
      t("import.promptUsage2"),
      t("import.promptUsage3"),
      t("import.promptUsage4"),
    ];
    let html = `<ul class="-import-file-list">`;
    usage.forEach((u, i) => { html += `<li>${i + 1}. ${esc(u)}</li>`; });
    html += `</ul>`;
    html += `<textarea id="import-prompt-text" class="-import-report-textarea" readonly rows="16">${esc(
      _promptText || ""
    )}</textarea>`;
    html += `<div class="-import-preview-actions"><button type="button" class="-btn secondary -btn--sm" data-feedback="prompt">${esc(
      t("import.copyPrompt")
    )}</button></div>`;
    body.innerHTML = html;
    const btn = body.querySelector('[data-feedback="prompt"]');
    if (btn) btn.addEventListener("click", () => copyFeedback("prompt"));
  }

  // ── 2. 扫描与预览 ────────────────────────────────────────────────

  async function scanPreview() {
    const a = A();
    if (!_kind || !_sources) return;
    a.setStatus?.(t("import.preScanning"));
    const res = await a.call("import_scan", _kind, _sources);
    if (res.status === "error") {
      a.setStatusError?.(res.message || t("import.preScanFailed"));
      return;
    }
    _preview = res;
    _conflicts = (res.preview && res.preview.conflicts) || [];
    setTitle(t("import.previewTitle"));
    renderPreview();
    $("#import-conflict-modal")?.classList.remove("hidden");
  }

  function renderPreview() {
    const body = $("#import-conflict-body");
    if (!body || !_preview) return;
    const pv = _preview.preview || {};
    const sum = pv.summary || {};
    const files = pv.files || [];
    const kps = pv.kp || [];
    const conflicts = _conflicts;
    let html = "";

    // 摘要
    html += `<div class="-import-scan-summary">`;
    html += `<p class="-stat-ok">${esc(
      t("import.pvSummary", {
        filesNew: sum.files_new || 0,
        filesOverwrite: sum.files_overwrite || 0,
        filesRename: sum.files_rename || 0,
        filesSkip: sum.files_skip || 0,
        filesUnchanged: sum.files_unchanged || 0,
        kpNew: sum.kp_new || 0,
        conflicts: sum.conflicts || 0,
      })
    )}</p>`;
    html += `</div>`;

    // 反馈复制
    html += `<div class="-import-preview-actions -btn-bar -btn-bar--start">`;
    html += `<button type="button" class="-btn secondary -btn--sm" data-feedback="json">${esc(t("import.copyJson"))}</button>`;
    html += `<button type="button" class="-btn secondary -btn--sm" data-feedback="md">${esc(t("import.copyMarkdown"))}</button>`;
    if (conflicts.length) {
      html += `<span class="-btn secondary -btn--sm" data-apply-all="1">${esc(t("import.applyAll"))}</span>`;
    }
    html += `</div>`;

    // 冲突（可决策）
    if (conflicts.length) {
      html += `<h4 class="-import-section-title">${esc(t("import.secConflicts"))}</h4>`;
      html += `<div class="-import-conflict-list">`;
      conflicts.forEach((c, i) => {
        const isFile = c.kind === "file_exists";
        const kindLabel = isFile ? t("import.confKindFile") : t("import.confKindKp");
        const opts = c.options || ["skip", "overwrite", "rename"];
        html += `<div class="-import-conflict-item" data-cidx="${i}" data-kind="${c.kind}">`;
        html += `<div class="-import-conflict-header">`;
        html += `<span class="-import-conflict-kp-id">${esc(kindLabel)} ${esc(c.subject)}</span>`;
        html += `<span class="-muted">${esc(c.detail || "")}</span>`;
        html += `</div>`;
        html += `<div class="-import-conflict-resolution">`;
        html += `<select data-cselect="${i}">`;
        opts.forEach((o) => {
          html += `<option value="${esc(o)}">${esc(t("import." + o))}</option>`;
        });
        html += `</select>`;
        html += `<input type="text" class="-import-rename-input hidden" data-crename="${i}" placeholder="${esc(
          isFile ? t("import.newRelPh") : t("import.newIdPh")
        )}">`;
        html += `</div></div>`;
      });
      html += `</div>`;
    }

    // 文件清单
    html += `<h4 class="-import-section-title">${esc(t("import.secFiles"))} (${files.length})</h4>`;
    html += `<ul class="-import-file-list">`;
    files.forEach((f) => {
      html += `<li><code>${esc(f.rel_path)}</code> <span class="-muted">· ${esc(t("import.act_" + f.action))}</span>${
        (f.kp_ids || []).length ? ` <span class="-muted">· ${(f.kp_ids || []).map(esc).join(", ")}</span>` : ""
      }</li>`;
    });
    html += `</ul>`;

    // KP 清单
    html += `<h4 class="-import-section-title">${esc(t("import.secKp"))} (${kps.length})</h4>`;
    html += `<ul class="-import-file-list">`;
    kps.forEach((k) => {
      const rangeNote = k.range === null && k.source !== "plain" ? ` ${esc(t("import.rangePending"))}` : "";
      html += `<li><code>${esc(k.id)}</code> ${esc(k.name || "")}<span class="-muted"> · ${esc(k.source)}${rangeNote}</span></li>`;
    });
    if (!kps.length) html += `<li class="-muted">${esc(t("import.noKp"))}</li>`;
    html += `</ul>`;

    // Agent 反馈文本（Markdown 预览，只读）
    html += `<textarea id="import-conflict-report-text" class="-import-report-textarea" readonly rows="5">${esc(
      _preview.markdown || ""
    )}</textarea>`;

    body.innerHTML = html;
    body.querySelectorAll("[data-feedback]").forEach((btn) => {
      btn.addEventListener("click", () => copyFeedback(btn.dataset.feedback));
    });
    const applyAll = body.querySelector('[data-apply-all="1"]');
    if (applyAll) applyAll.addEventListener("click", applyAllConflicts);
    body.querySelectorAll("[data-cselect]").forEach((sel) => {
      sel.addEventListener("change", () => toggleRenameInput(sel));
    });
  }

  function toggleRenameInput(sel) {
    const item = sel.closest(".-import-conflict-item");
    const input = item && item.querySelector(".-import-rename-input");
    if (input) input.classList.toggle("hidden", sel.value !== "rename");
  }

  function applyAllConflicts() {
    const body = $("#import-conflict-body");
    if (!body || !_conflicts) return;
    const action = window.prompt(t("import.applyAllPh")) || "";
    const normalized = action.trim().toLowerCase();
    if (!["skip", "overwrite", "rename"].includes(normalized)) {
      A().setStatus?.(t("import.applyAllInvalid"));
      return;
    }
    _conflicts.forEach((c, i) => {
      const sel = body.querySelector(`[data-cselect="${i}"]`);
      if (sel) sel.value = normalized;
      const input = body.querySelector(`[data-crename="${i}"]`);
      if (input) {
        if (normalized === "rename") {
          const base = c.subject.replace(/\.md$/i, "");
          input.value = c.kind === "file_exists" ? `${base}-2.md` : `${base}-2`;
          input.classList.remove("hidden");
        } else {
          input.classList.add("hidden");
        }
      }
    });
  }

  // ── 3. 反馈复制 ──────────────────────────────────────────────────

  function copyFeedback(mode) {
    const a = A();
    let text = "";
    if (mode === "prompt") {
      text = _promptText || "";
    } else if (mode === "json" && _preview) {
      text = JSON.stringify(_preview.preview || {}, null, 2);
    } else if (_preview && _preview.markdown) {
      text = _preview.markdown;
    }
    if (!text) return;
    const done = () => a.setStatus?.(t("import.copyDone"));
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => { done(); });
    } else {
      done();
    }
    const ta = $("#import-conflict-report-text");
    if (ta) ta.value = text;
  }

  // ── 4. 决策收集与执行 ────────────────────────────────────────────

  function collectDecisions() {
    const body = $("#import-conflict-body");
    const decisions = {};
    if (!body || !_conflicts) return decisions;
    _conflicts.forEach((c, i) => {
      const sel = body.querySelector(`[data-cselect="${i}"]`);
      if (!sel) return;
      const value = sel.value;
      if (value === "rename") {
        const input = body.querySelector(`[data-crename="${i}"]`);
        const target = (input && input.value.trim()) || c.subject;
        decisions[c.subject] = "rename:" + target;
      } else {
        decisions[c.subject] = value;
      }
    });
    return decisions;
  }

  async function confirmImport() {
    const a = A();
    if (!_kind || !_sources) return;
    const decisions = collectDecisions();
    a.setStatus?.(t("import.running"));
    const res = await a.call("import_execute", _kind, _sources, decisions);
    if (res.status === "error") {
      a.setStatusError?.(res.message || t("import.failed"));
      return;
    }
    closePreviewModal();
    await afterImportRefresh(res);
    renderResultDialog(res);
    $("#import-result-modal")?.classList.remove("hidden");
  }

  async function afterImportRefresh(result) {
    const a = A();
    await a.refreshFiles?.();
    await a.loadLinkTargets?.();
    await a.loadGraphData?.();
    await a.refreshKbPendingSummary?.();
    if (a.state?.currentPath) {
      await a.openFile?.(a.state.currentPath, { skipNav: true });
    }
    const kp =
      (result.kp_imported || 0) +
      (result.kp_overwritten || 0) +
      (result.kp_renamed || 0);
    const files = result.files_written || 0;
    a.setStatus?.(
      t("import.doneTitle"),
      t("import.doneStats", { files, kp })
    );
  }

  // ── 5. 结果对话框 ────────────────────────────────────────────────

  function renderResultDialog(result) {
    const body = $("#import-result-body");
    if (!body) return;
    let html = `<div class="-import-result-summary">`;
    html += `<p class="${result.errors && result.errors.length ? "-stat-error" : "-stat-ok"}">${esc(
      t(result.errors && result.errors.length ? "import.resultPartial" : "import.resultOk")
    )}</p>`;
    html += `<p>${esc(
      t("import.resultStats2", {
        files: result.files_written || 0,
        unchanged: result.files_unchanged || 0,
        overwritten: result.files_overwritten || 0,
        renamed: result.files_renamed || 0,
        skipped: result.files_skipped || 0,
        sidecars: result.sidecars_written || 0,
        imported: result.kp_imported || 0,
      })
    )}</p>`;
    html += `<p>${esc(
      t("import.resultStatsKp", {
        imported: result.kp_imported || 0,
        overwritten: result.kp_overwritten || 0,
        renamed: result.kp_renamed || 0,
        skipped: result.kp_skipped || 0,
      })
    )}</p>`;
    const errors = result.errors || [];
    if (errors.length) {
      html += `<p class="-stat-error">${esc(t("import.errorsLabel", { n: errors.length }))}</p><ul>`;
      errors.forEach((e) => { html += `<li>${esc(String(e))}</li>`; });
      html += `</ul>`;
    }
    html += `</div>`;
    body.innerHTML = html;
  }

  function closePreviewModal() {
    $("#import-conflict-modal")?.classList.add("hidden");
    _resetState();
  }

  function closeResultModal() {
    $("#import-result-modal")?.classList.add("hidden");
  }

  // ── 事件绑定 ─────────────────────────────────────────────────────

  function init() {
    $("#file-menu-import")?.addEventListener("click", () => start());
    // 兼容旧入口（如被复用）
    $("#btn-import")?.addEventListener("click", () => start());
    $("#import-conflict-close")?.addEventListener("click", closePreviewModal);
    $("#import-conflict-cancel")?.addEventListener("click", closePreviewModal);
    $("#import-conflict-modal .-modal-backdrop")?.addEventListener("click", closePreviewModal);
    $("#import-conflict-confirm")?.addEventListener("click", () => confirmImport());
    $("#import-conflict-copy-report")?.addEventListener("click", () => copyFeedback("md"));
    $("#import-result-close")?.addEventListener("click", closeResultModal);
    $("#import-result-dismiss")?.addEventListener("click", closeResultModal);
    $("#import-result-modal .-modal-backdrop")?.addEventListener("click", closeResultModal);
  }

  return { init, start };
})(typeof window !== "undefined" ? window : globalThis);
