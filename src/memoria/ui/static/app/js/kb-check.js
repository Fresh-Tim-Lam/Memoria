/**
 * 知识库完整性检查（原 app.js「KB 完整性检查」子系统，2026-09-04 抽出）。
 *
 * 自包含：validate_kb 校验运行（runKbValidate）+ 检查弹窗（#check-modal：逐条渲染 /
 * 点击 issue 打开定位 / 路径修复 / 文件清单同步）+「检查」按钮角标（#btn-check-badge）
 * + 状态栏「检查统计」块文案（statsChunk，由 app.js renderStatusStats 组装）+ 静默
 * 后台检查（MemoriaCheckSettings 间隔触发）。
 *
 * DOM/事件绑定全部由本模块 init() 完成，不依赖 app.js 的 bindEvents：
 *   - #btn-check → openCheckModal（原 app.js bindEvents）
 *   - #check-close / #check-dismiss / #check-rerun / #check-modal .-modal-backdrop
 *   - MemoriaCheckSettings.onChange → 知识库已打开时按新间隔重启静默检查（原 app.js bindEvents）
 *   - MemoriaI18n.addRefresh → 语言切换后重绘角标/状态栏检查统计与打开的检查弹窗
 *     （原 app.js bindEvents 中 addRefresh 的检查分支）
 * #status-stats 的 click 为与图谱审计共用的状态栏处理器，保留在 app.js（kbCheck 分支
 * 回调本模块 openCheckModal，保证两 dataset 并存时的短路顺序与原实现一致）。
 *
 * app.js 仍需调用的公开 API（见文件末尾 return）：
 *   runKbValidate / startKbSilentCheck / stopKbSilentCheck / resetIndicators
 *   statsChunk / openCheckModal / closeCheckModal / init
 *
 * 依赖 window.MemoriaApp（app.js 导出的应用服务门面）：
 *   state / call / T / esc / setStatus / setStatusError / openFile / refreshFiles / loadGraphData
 *   localizeCheckIssue / renderStatusStats / normRelPath / remapOpenTabsAfterPathRepair
 * （localizeCheckIssue / renderStatusStats / normRelPath / remapOpenTabsAfterPathRepair 为
 * 本次拆分在门面上追加的私有服务，见 app.js 门面注释）
 *
 * 文案全部经 T('key') 取当前语言（复用 check.* / app.* 键族，零新增键）。
 */
window.MemoriaKbCheck = (function () {
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

  // ── app.js 私有服务（门面追加项）：后端检查消息本地化 / 状态栏统计重绘 ──
  const localizeCheckIssue = (issue) => {
    const a = A();
    return a.localizeCheckIssue
      ? a.localizeCheckIssue(issue)
      : issue && issue.message
        ? issue.message
        : issue
          ? issue.code || String(issue)
          : "";
  };
  const renderStatusStats = () => A().renderStatusStats?.();
  const normRelPath = (p) =>
    A().normRelPath ? A().normRelPath(p) : String(p || "").replace(/\\/g, "/");
  const remapOpenTabsAfterPathRepair = (applied) =>
    A().remapOpenTabsAfterPathRepair?.(applied);
  const refreshFiles = () => A().refreshFiles?.();
  const loadGraphData = () => A().loadGraphData?.();
  const openFile = (relPath, opts) => A().openFile?.(relPath, opts);

  // ── 检查统计文案（状态栏块 + 弹窗汇总的词尾/着色段）───────────────

  /** 检查统计的单复数词尾（紧跟在数字 strong 之后，如「2 错误 / 1 error」）。 */
  function checkCountWord(n, kind) {
    const key = n === 1 ? `check.word.${kind}` : `check.word.${kind}s`;
    return T(key);
  }

  /** 底栏/汇总里整段着色的统计块（如「2 错误」）。 */
  function statCountHtml(n, kind) {
    const cls = kind === "error" ? "-stat-error" : "-stat-warn";
    const key = n === 1 ? `check.stat.${kind}s.one` : `check.stat.${kind}s.many`;
    return `<span class="${cls}">${T(key, { n })}</span>`;
  }

  /** 状态栏「检查统计」块（底栏由 app.js renderStatusStats 组装各子系统统计时调用）。 */
  function formatKbCheckStatsHtml(vr) {
    if (!vr) return "";
    const err = vr.errors || 0;
    const warn = vr.warnings || 0;
    if (err === 0 && warn === 0) return "";
    const parts = [T("check.stat.head")];
    if (err > 0) {
      parts.push(statCountHtml(err, "error"));
    }
    if (warn > 0) {
      parts.push(statCountHtml(warn, "warning"));
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
      badge.title =
        warn > 0
          ? T("check.badge.tooltipMixed", { err, warn })
          : T("check.badge.tooltipErrors", { n: err });
    } else {
      badge.classList.add("-toolbar-badge--warn");
      badge.title = T("check.badge.tooltipWarnings", { n: warn });
    }
  }

  function applyCheckIndicators(vr) {
    if (!vr) return;
    updateCheckButtonBadge(vr);
    renderStatusStats();
  }

  // ── 静默后台检查（沿用原 startKbSilentCheck/stopKbSilentCheck 语义）────────

  function startKbSilentCheck() {
    if (!window.MemoriaCheckSettings) return;
    MemoriaCheckSettings.startSilentCheck(scheduleSilentValidate);
  }

  /** G5.1：静默 validate 经调度内核执行（优先级/idle、按 KB 合并、关库 epoch 陈旧丢弃、忙时不跑）。 */
  function scheduleSilentValidate() {
    const S = window.MemoriaScheduler;
    if (!S || !state.kbPath) return;
    S.schedule({
      kind: "kb_check",
      key: "kb:" + state.kbPath,
      priority: 3,
      replace: true,
      dropStale: true,
      gen: S.epoch(),
      run: () => {
        if (!state.kbPath) return;
        const busy = window.__memoriaHasPendingEdits && window.__memoriaHasPendingEdits();
        if (busy) return; // 编辑/待保存未收敛：本次跳过，等下轮间隔
        runKbValidate({ silent: true });
      },
    });
  }

  function stopKbSilentCheck() {
    window.MemoriaCheckSettings?.stopSilentCheck?.();
  }

  // ── 校验运行 / 状态应用 ──────────────────────────────────────

  function applyKbValidateStatus(vr, opts = {}) {
    if (!vr) return;
    applyCheckIndicators(vr);
    if (opts.silent) return;
    if (vr.errors > 0 || vr.warnings > 0) {
      /* 底栏统计已由 renderStatusStats 着色；保留当前文件路径于 status-info */
      if (!state.currentPath) {
        setStatus(state.kbPath || T("check.kbName"));
      }
    } else if (vr.status === "ok" && !state.currentPath) {
      setStatus(state.kbPath || T("check.kbName"));
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
      if (!opts.silent) setStatus(T("check.status.checkFailed"), String(e.message || e));
      return null;
    }
  }

  // ── 检查弹窗渲染 ─────────────────────────────────────────────

  function checkItemHtml(issue, severity, path, openPath) {
    const sev = normalizeCheckSeverity(severity);
    const badge =
      sev === "error"
        ? `<span class="-check-badge -check-badge--error">${T("check.badge.error")}</span>`
        : `<span class="-check-badge -check-badge--warning">${T("check.badge.warning")}</span>`;
    const dataAttrs = [
      issue?.kp_id ? `data-check-kp="${esc(issue.kp_id)}"` : "",
      issue?.line ? `data-check-line="${issue.line}"` : "",
      issue?.kind ? `data-check-kind="${esc(issue.kind)}"` : "",
    ].filter(Boolean).join(" ");
    const openBtn = openPath
      ? `<button type="button" class="-btn secondary -check-open-btn" data-check-open="${esc(openPath)}" ${dataAttrs}>${T("check.open")}</button>`
      : "";
    const pathHtml = path
      ? `<div class="-check-item-path">${esc(path)}</div>`
      : "";
    return `<div class="-check-item -check-item--${sev}">
      ${badge}
      <div class="-check-item-main">
        <div>${esc(localizeCheckIssue(issue))}</div>
        ${pathHtml}
      </div>
      ${openBtn}
    </div>`;
  }

  function renderCheckModalBody(vr) {
    const body = $("#check-body");
    if (!body) return;
    if (!vr) {
      body.innerHTML = `<p class="-muted">${T("check.empty")}</p>`;
      return;
    }
    const errN = vr.errors || 0;
    const warnN = vr.warnings || 0;
    const summaryCls =
      errN > 0 ? "-check-summary -check-summary--error" : "-check-summary";
    const errWord = checkCountWord(errN, "error");
    const warnWord = checkCountWord(warnN, "warning");
    let html = `<div class="${summaryCls}">
      ${T("check.summaryChecked", { files: vr.files_checked || 0 })} ·
      ${errN > 0 ? `<strong class="-stat-error">${errN}</strong>` : `<strong>${errN}</strong>`} ${errWord} ·
      ${warnN > 0 ? `<strong class="-stat-warn">${warnN}</strong>` : `<strong>${warnN}</strong>`} ${warnWord}
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
      html += `<section class="-check-section"><h4 class="-check-section-title">${T("check.section.kb")}</h4>`;
      for (const issue of kbIssues) {
        const path = issue.paths?.[0] || "";
        html += checkItemHtml(
          issue,
          issue.severity,
          issue.paths?.length > 1 ? issue.paths.join(" · ") : path,
          path || null
        );
      }
      html += "</section>";
    }

    if (pathMoves.length) {
      html += `<section class="-check-section"><h4 class="-check-section-title">${T("check.section.pathMoves")}
        <button type="button" class="-btn secondary -btn--sm" id="check-repair-paths">${T("check.repairBtn")}</button>
      </h4>`;
      html += `<p class="-muted">${T("check.note.pathMovesRepair")}</p>`;
      for (const m of pathMoves) {
        const hint =
          m.kind === "md_sha256"
            ? T("check.pathmove.match")
            : m.kind === "sidecar_drift"
              ? T("check.pathmove.drift")
              : m.kind || "";
        html += checkItemHtml(
          { message: `${m.from} → ${m.to}` },
          m.severity,
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
          ? `<button type="button" class="-btn secondary -btn--sm" id="check-sync-manifest">${T("check.syncManifestBtn")}</button>`
          : "";
      html += `<section class="-check-section"><h4 class="-check-section-title">${T("check.section.manifest")} ${syncBtn}</h4>`;
      if (md.baseline_created) {
        html += `<p class="-muted">${T("check.note.manifestBaseline", { docs: md.file_count || 0 })}</p>`;
      } else if (!manifestIssues.length) {
        html += `<p class="-muted">${T("check.note.manifestConsistent", { docs: md.file_count || 0 })}</p>`;
      }
      for (const issue of manifestIssues) {
        const path = issue.paths?.[0] || "";
        html += checkItemHtml(
          issue,
          issue.severity,
          issue.paths?.length > 1 ? issue.paths.join(" · ") : path,
          path || null
        );
      }
      html += "</section>";
    }

    for (const fr of vr.files || []) {
      html += `<section class="-check-section"><h4 class="-check-section-title">${esc(fr.path)}</h4>`;
      for (const e of fr.errors || []) {
        html += checkItemHtml(e, "error", fr.path, fr.path);
      }
      for (const w of fr.warnings || []) {
        html += checkItemHtml(w, "warning", fr.path, fr.path);
      }
      html += "</section>";
    }

    const gaFiles = (vr.graph_audit?.files || []).filter(
      (f) => (f.issues || []).length
    );
    if (gaFiles.length) {
      html += `<section class="-check-section"><h4 class="-check-section-title">${T("check.section.graphEdges")}</h4>`;
      for (const gf of gaFiles) {
        for (const issue of gf.issues || []) {
          html += checkItemHtml(issue, issue.severity, gf.file, gf.file);
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
      html += `<p class="-muted">${T("check.noProblems")}</p>`;
    }
    body.innerHTML = html;
    body.querySelector("#check-sync-manifest")?.addEventListener("click", async () => {
      setStatus(T("check.status.syncStart"));
      const res = await call("sync_manifest");
      if (res.status === "ok") {
        setStatus(T("check.status.manifestUpdated"), T("check.countDocs", { n: res.file_count || 0 }));
        await runKbValidate({ silent: false });
      } else {
        setStatusError((res && localizeCheckIssue(res)) || T("check.status.syncFailed"));
        if (res.blocked && (res.path_moves || []).length) {
          await runKbValidate({ silent: false });
        }
      }
    });

    body.querySelector("#check-repair-paths")?.addEventListener("click", async () => {
      if (!window.confirm(T("check.confirm.repair"))) {
        return;
      }
      setStatus(T("check.status.repairing"));
      const res = await call("repair_path_cascade", true);
      if (res.status === "ok" || res.status === "partial") {
        setStatus(
          T("check.status.pathRepaired"),
          T("check.status.repairedStats", {
            done: res.applied_count ?? 0,
            total: res.move_count ?? 0,
          })
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
        setStatusError((res && localizeCheckIssue(res)) || T("check.status.repairFailed"));
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
      setStatus(T("app.openKbFirst"));
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

  // ── init：绑定本模块 DOM/事件与刷新订阅（原 app.js bindEvents 中对应分支）────────

  function init() {
    // 「检查」按钮 → 检查弹窗（原 app.js bindEvents）
    $("#btn-check")?.addEventListener("click", () => openCheckModal());
    // 检查弹窗：关闭按钮 / 重新检查 / backdrop 点击（原 app.js bindEvents）
    $("#check-close")?.addEventListener("click", closeCheckModal);
    $("#check-dismiss")?.addEventListener("click", closeCheckModal);
    $("#check-rerun")?.addEventListener("click", () => runKbValidate({ silent: false }));
    $("#check-modal .-modal-backdrop")?.addEventListener("click", closeCheckModal);
    // 静默检查设置变化：知识库已打开时按新间隔重启后台检查（原 app.js bindEvents）
    if (window.MemoriaCheckSettings) {
      MemoriaCheckSettings.onChange(() => {
        if (state.kbPath) startKbSilentCheck();
      });
    }
    // 语言切换后：重绘角标/状态栏检查统计与打开的检查弹窗（原 app.js bindEvents 的检查分支）
    if (window.MemoriaI18n) {
      MemoriaI18n.addRefresh(function () {
        if (state.kbValidateReport) {
          applyCheckIndicators(state.kbValidateReport);
          if ($("#check-modal") && !$("#check-modal").classList.contains("hidden")) {
            renderCheckModalBody(state.kbValidateReport);
          }
        }
      });
    }
  }

  return {
    init,
    runKbValidate,      // 原 runKbValidate（openKb/initKb 打开知识库后立即检查用）
    startKbSilentCheck, // 原 startKbSilentCheck
    stopKbSilentCheck,  // 原 stopKbSilentCheck（closeKb 用）
    resetIndicators: () => updateCheckButtonBadge(null), // 清空「检查」角标（closeKb 用）
    statsChunk: formatKbCheckStatsHtml, // 状态栏「检查统计」块文案（app.js renderStatusStats 组装）
    openCheckModal,     // 状态栏 #status-stats 的 kbCheck 分支回调（原 app.js bindEvents）
    closeCheckModal,    // closeKb 收尾用
  };
})(typeof window !== "undefined" ? window : globalThis);
