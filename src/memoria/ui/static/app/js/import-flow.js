/**
 * 平面文件导入（原 app.js「R11: 平面文件导入」子系统，2026-09-04 抽出）。
 *
 * 自包含：文件选择 → 预扫描 → 无冲突直导 / 冲突对话框逐条处理 → 结果对话框 → 刷新。
 * 事件绑定全部由本模块 init() 完成，不依赖 app.js 的 bindEvents。
 *
 * 依赖 window.MemoriaApp（app.js 导出的应用服务门面）：
 *   state / call / T / esc / setStatus / setStatusError
 *   refreshFiles / loadLinkTargets / loadGraphData / refreshKbPendingSummary / openFile
 */
window.MemoriaImportFlow = (function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const A = () => window.MemoriaApp || {};

  let _fileContents = null;
  let _scanResult = null;

  async function start() {
    const a = A();
    if (!a.state || !a.state.kbPath) {
      a.setStatus?.(a.T ? a.T("app.openKbFirst") : "app.openKbFirst");
      return;
    }
    const btn = $("#btn-import");
    if (btn) btn.disabled = true;
    try {
      const files = await a.call("select_import_files");
      if (!files || !files.length) {
        return;
      }
      _fileContents = files;
      a.setStatus?.(a.T ? a.T("import.preScanning") : "import.preScanning");
      const scan = await a.call("pre_scan_import", files);
      if (scan.status === "error") {
        a.setStatusError?.(scan.message || (a.T ? a.T("import.preScanFailed") : "import.preScanFailed"));
        return;
      }
      _scanResult = scan;
      if (!scan.has_conflicts) {
        await runDirect(files, {});
        return;
      }
      renderConflictDialog(scan);
      $("#import-conflict-modal")?.classList.remove("hidden");
    } catch (e) {
      a.setStatusError?.(a.T ? a.T("import.failed") : "import.failed", e.message || String(e));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function runDirect(files, conflictResolution) {
    const a = A();
    const btn = $("#btn-import");
    if (btn) btn.disabled = true;
    try {
      a.setStatus?.(a.T ? a.T("import.running") : "import.running");
      const result = await a.call("execute_import", files, conflictResolution);
      if (result.status === "error") {
        a.setStatusError?.(result.message || (a.T ? a.T("import.failed") : "import.failed"));
        return;
      }
      await afterImportRefresh(result);
      renderResultDialog(result);
      $("#import-result-modal")?.classList.remove("hidden");
    } catch (e) {
      a.setStatusError?.(a.T ? a.T("import.failed") : "import.failed", e.message || String(e));
    } finally {
      if (btn) btn.disabled = false;
    }
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
    const kp = (result.kp_imported || 0) + (result.kp_overwritten || 0) + (result.kp_renamed || 0);
    const files = result.files_written || 0;
    a.setStatus?.(
      a.T ? a.T("import.doneTitle") : "import.doneTitle",
      a.T ? a.T("import.doneStats", { files, kp }) : files + " · " + kp
    );
  }

  function renderConflictDialog(scanResult) {
    const a = A();
    const body = $("#import-conflict-body");
    if (!body) return;
    const t = (k, p) => (a.T ? a.T(k, p) : k);
    const esc = (s) => (a.esc ? a.esc(s) : String(s == null ? "" : s));
    const conflicts = scanResult.conflicts || [];
    let html = "";
    html += `<div class="-import-scan-summary">`;
    html += `<p>${t("import.scanSummary", {
      files: esc(String(scanResult.total_files || 0)),
      sections: esc(String(scanResult.total_sections || 0)),
      kps: esc(String(scanResult.total_kp_declarations || 0)),
    })}</p>`;
    html += `<p class="-stat-error">${t("import.conflictCount", { n: esc(String(conflicts.length)) })}</p>`;
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
      html += `<span class="-muted">${t("import.sourceLine", { source, line, file: existFile, name: existName })}</span>`;
      html += `</div>`;
      html += `<div class="-import-conflict-resolution">`;
      html += `<label><input type="radio" name="import-res-${i}" value="skip" checked> ${t("import.skip")}</label>`;
      html += `<label><input type="radio" name="import-res-${i}" value="overwrite"> ${t("import.overwrite")}</label>`;
      html += `<label><input type="radio" name="import-res-${i}" value="rename"> ${t("import.rename")}</label>`;
      html += `<input type="text" class="-import-rename-input hidden" data-conflict-idx="${i}" placeholder="${t("import.newIdPh")}">`;
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

  function collectResolution() {
    const a = A();
    const body = $("#import-conflict-body");
    if (!body) return {};
    const conflicts = (_scanResult && _scanResult.conflicts) || [];
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

  function renderResultDialog(result) {
    const a = A();
    const body = $("#import-result-body");
    if (!body) return;
    const t = (k, p) => (a.T ? a.T(k, p) : k);
    const esc = (s) => (a.esc ? a.esc(s) : String(s == null ? "" : s));
    let html = "";
    html += `<div class="-import-result-summary">`;
    html += `<p class="-stat-ok">${t("import.resultOk")}</p>`;
    html += `<p>${t("import.resultStats", {
      files: esc(String(result.files_written || 0)),
      imported: esc(String(result.kp_imported || 0)),
      overwritten: esc(String(result.kp_overwritten || 0)),
      renamed: esc(String(result.kp_renamed || 0)),
      skipped: esc(String(result.kp_skipped || 0)),
    })}</p>`;
    const errors = result.errors || [];
    if (errors.length) {
      html += `<p class="-stat-error">${t("import.errorsLabel", { n: esc(String(errors.length)) })}</p><ul>`;
      errors.forEach((e) => { html += `<li>${esc(String(e))}</li>`; });
      html += `</ul>`;
    }
    html += `</div>`;
    body.innerHTML = html;
  }

  function closeConflictModal() {
    $("#import-conflict-modal")?.classList.add("hidden");
    _fileContents = null;
    _scanResult = null;
  }

  function closeResultModal() {
    $("#import-result-modal")?.classList.add("hidden");
  }

  function copyReport() {
    const a = A();
    const ta = $("#import-conflict-report-text");
    if (ta) {
      ta.select();
      const done = () => a.setStatus?.(a.T ? a.T("import.copyDone") : "import.copyDone");
      navigator.clipboard.writeText(ta.value).then(done).catch(() => { document.execCommand("copy"); done(); });
    }
  }

  function init() {
    $("#btn-import")?.addEventListener("click", () => start());
    $("#import-conflict-close")?.addEventListener("click", closeConflictModal);
    $("#import-conflict-cancel")?.addEventListener("click", closeConflictModal);
    $("#import-conflict-modal .-modal-backdrop")?.addEventListener("click", closeConflictModal);
    $("#import-conflict-copy-report")?.addEventListener("click", copyReport);
    $("#import-conflict-confirm")?.addEventListener("click", async () => {
      const files = _fileContents;
      const resolution = collectResolution();
      closeConflictModal();
      if (files) await runDirect(files, resolution);
    });
    $("#import-result-close")?.addEventListener("click", closeResultModal);
    $("#import-result-dismiss")?.addEventListener("click", closeResultModal);
    $("#import-result-modal .-modal-backdrop")?.addEventListener("click", closeResultModal);
  }

  return { init, start };
})(typeof window !== "undefined" ? window : globalThis);
