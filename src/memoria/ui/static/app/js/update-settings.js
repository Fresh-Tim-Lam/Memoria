#!/usr/bin/env node
/* 版本更新设置页（task-180）
 *
 * 宿主：`graph-settings.js` 的「设置」弹窗新增「更新」页签（动态注入本脚本，
 * 不改 index.html 的静态结构）。本模块只负责：
 *   ① 检查更新（手动；启动后 6s 延迟静默检查，24h 限频由后端保证）
 *   ② 展示当前/最新版本、发布日期、更新说明、资产（lite 默认推荐，full 需显式选择）
 *   ③ 下载到 Downloads（进度可见 / 可取消）、下载后调用后端校验并显示结果
 *   ④ 手动替换说明（**绝不自动替换**；关闭进程 / 只换应用文件夹 / 配置不受影响 / lite 别删 hf）
 *
 * 文案纪律（人 2026-10-26 裁决）：**禁止**出现「防篡改 / 安全 / 已签名」；
 * 正确表述：「已校验包结构与完整性（不含数字签名）」。
 */
(function (global) {
  "use strict";

  const T = (k, p) => (global.MemoriaI18n ? global.MemoriaI18n.t(k, p) : k);
  const esc = (s) =>
    String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const state = {
    root: null,
    busy: false,
    info: null,        // get_update_state()
    result: null,      // check_for_update() 结果
    jobId: "",
    pollTimer: null,
    done: null,        // 下载完成状态
    verify: null,
    selected: "",
  };

  function api() {
    return global.MemoriaBridge && global.MemoriaBridge.api();
  }

  async function call(fn, ...args) {
    const a = api();
    if (!a || typeof a[fn] !== "function") throw new Error(T("update.apiUnavailable", { fn }));
    return await a[fn](...args);
  }

  function formatDate(iso) {
    const raw = String(iso || "").trim();
    if (!raw) return "—";
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return raw;
    try {
      return d.toLocaleString();
    } catch (_) {
      return raw;
    }
  }

  function injectStyle() {
    if (document.getElementById("memoria-update-style")) return;
    const style = document.createElement("style");
    style.id = "memoria-update-style";
    style.textContent = `
      .-update-card{border:1px solid var(--border-color,#3a3a3a);border-radius:8px;padding:12px;margin:8px 0;background:var(--panel-bg,rgba(127,127,127,.06))}
      .-update-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:6px 0}
      .-update-label{min-width:7em;color:var(--text-secondary,#aaa)}
      .-update-notes{white-space:pre-wrap;max-height:14em;overflow:auto;border-left:3px solid var(--theme-color,#007acc);padding:6px 10px;margin:6px 0;font-family:inherit;font-size:.92em}
      .-update-warn{color:#c78a00;margin:6px 0}
      .-update-progress{height:8px;border-radius:4px;background:rgba(127,127,127,.25);overflow:hidden;margin:6px 0}
      .-update-progress > i{display:block;height:100%;width:0;background:var(--theme-color,#007acc);transition:width .2s}
      .-update-steps{margin:6px 0 0 1.2em;line-height:1.8}
      .-update-badge{display:inline-block;width:7px;height:7px;border-radius:50%;background:#e05a00;margin-left:4px;vertical-align:top}
      .-update-muted{color:var(--text-secondary,#999);font-size:.92em}
    `;
    document.head.appendChild(style);
  }

  function loadingHtml() {
    return `<p class="-muted">${esc(T("update.loading"))}</p>`;
  }

  function outboundOfflineHtml() {
    return `<div class="-update-card"><strong>${esc(T("update.offlineTitle"))}</strong>
      <p class="-muted">${esc(T("update.offlineNote"))}</p></div>`;
  }

  function assetRow(asset, checked) {
    const isLite = asset.kind === "lite";
    const isFull = asset.kind === "full";
    const label = isLite
      ? T("update.assetLite")
      : isFull
        ? T("update.assetFull")
        : asset.name;
    return `<label class="-update-row" data-update-asset-row="${esc(asset.name)}">
      <input type="radio" name="update-asset" value="${esc(asset.name)}" ${checked ? "checked" : ""}>
      <span>${esc(label)}</span>
      <span class="-update-muted">${esc(asset.size_human || "")}</span>
      ${isLite ? `<span class="-update-muted">· ${esc(T("update.recommended"))}</span>` : ""}
      ${isFull ? `<span class="-update-muted">· ${esc(T("update.fullChoice"))}</span>` : ""}
    </label>`;
  }

  function renderCheckResult() {
    const r = state.result;
    if (!r) return `<p class="-muted">${esc(T("update.notChecked"))}</p>`;
    if (r.status === "offline") return "";
    if (r.status === "error") {
      return `<p class="-update-warn">${esc(T("update.checkFailed"))}${r.detail ? `（${esc(String(r.detail).slice(0, 160))}）` : ""}</p>`;
    }
    if (!r.latest_version) return `<p class="-update-warn">${esc(T("update.checkFailed"))}</p>`;
    const rows = [
      `<div class="-update-row"><span class="-update-label">${esc(T("update.current"))}</span><span>${esc(r.current_version)}</span></div>`,
      `<div class="-update-row"><span class="-update-label">${esc(T("update.latest"))}</span><span>${esc(r.latest_version)}</span></div>`,
      `<div class="-update-row"><span class="-update-label">${esc(T("update.published"))}</span><span>${esc(formatDate(r.published_at))}</span></div>`,
    ];
    if (!r.update_available) {
      rows.push(`<p class="-muted">${esc(T("update.upToDate"))}</p>`);
      return rows.join("");
    }
    const assets = (r.assets || []).filter((a) => a.kind === "lite" || a.kind === "full");
    const selected = state.selected || (assets.find((a) => a.kind === "lite") || assets[0] || {}).name || "";
    state.selected = selected;
    const assetRows = assets.map((a) => assetRow(a, a.name === selected)).join("");
    return `<div class="-update-card">
        <div class="-update-row"><strong>${esc(T("update.available", { latest: r.latest_version }))}</strong></div>
        ${rows.join("")}
        <div class="-update-row"><span class="-update-label">${esc(T("update.notes"))}</span></div>
        <pre class="-update-notes" id="update-notes"></pre>
        <div class="-update-row"><span class="-update-label">${esc(T("update.assets"))}</span></div>
        ${assetRows}
        <p class="-muted" id="update-asset-warn"></p>
        <div class="-settings-actions">
          <button type="button" class="-btn primary" id="update-download">${esc(T("update.download"))}</button>
        </div>
        <p class="-update-muted">${esc(T("update.verifyNote"))}</p>
      </div>`;
  }

  function renderDownloadArea() {
    if (state.done && state.done.status === "done") {
      const v = state.verify || {};
      const manifestMode = v.mode === "manifest";
      const steps = [
        T("update.step1"),
        T("update.step2"),
        T("update.step3", { configDir: (state.info && state.info.config_dir) || "" }),
      ];
      if (state.done.assetKind === "lite") steps.push(T("update.stepLite"));
      return `<div class="-update-card">
        <strong>${esc(T("update.downloaded"))}</strong>
        <div class="-update-row"><span class="-update-label">${esc(T("update.savedTo"))}</span><span>${esc(state.done.path || "")}</span></div>
        <div class="-update-row"><span class="-update-label">${esc(T("update.integrity"))}</span><span>${esc(manifestMode ? T("update.verifiedManifest") : T("update.verifiedZipOnly"))}</span></div>
        ${manifestMode ? "" : `<p class="-update-warn">${esc(T("update.unverifiedWarn"))}</p>`}
        <div class="-settings-actions">
          <button type="button" class="-btn secondary" id="update-open-folder">${esc(T("update.openFolder"))}</button>
        </div>
        <h4>${esc(T("update.manualTitle"))}</h4>
        <ol class="-update-steps">${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
        <p class="-update-warn">${esc(T("update.noAuto"))}</p>
      </div>`;
    }
    if (state.done && state.done.status === "failed") {
      const reasons = (state.done.failures || []).map((x) => `<li>${esc(x)}</li>`).join("");
      return `<div class="-update-card"><strong>${esc(T("update.downloadFailed"))}</strong>
        <ul class="-update-steps">${reasons || `<li>${esc(T("update.unknownReason"))}</li>`}</ul>
        <p class="-muted">${esc(T("update.downloadRetry"))}</p></div>`;
    }
    if (state.done && state.done.status === "cancelled") {
      return `<p class="-muted">${esc(T("update.cancelled"))}</p>`;
    }
    if (state.jobId) {
      return `<div class="-update-card" id="update-progress-card">
        <strong>${esc(T("update.downloading"))}</strong>
        <div class="-update-progress"><i id="update-progress-bar"></i></div>
        <div class="-update-row"><span id="update-progress-text"></span></div>
        <div class="-settings-actions">
          <button type="button" class="-btn secondary" id="update-cancel">${esc(T("update.cancel"))}</button>
        </div>
      </div>`;
    }
    return "";
  }

  function render() {
    if (!state.root) return;
    injectStyle();
    const info = state.info || {};
    const outbound = info.outbound_enabled !== false;
    const html = `<div class="-settings-layout -settings-layout--solo"><div class="-settings-form">
      <section class="-settings-section">
        <h3 class="-settings-heading">${esc(T("update.title"))}</h3>
        ${outbound ? "" : outboundOfflineHtml()}
        <div class="-update-row"><span class="-update-label">${esc(T("update.current"))}</span><span>${esc(info.current_version || "—")}</span></div>
        <label class="-update-row"><input type="checkbox" id="update-auto-check" ${info.auto_check ? "checked" : ""} ${outbound ? "" : "disabled"}>
          <span>${esc(T("update.autoCheck"))}</span></label>
        <p class="-muted">${esc(T("update.autoCheckNote"))}</p>
        <div class="-settings-actions">
          <button type="button" class="-btn primary" id="update-check" ${outbound ? "" : "disabled"}>${esc(state.busy ? T("update.checking") : T("update.check"))}</button>
        </div>
        ${outbound ? renderCheckResult() : ""}
        ${renderDownloadArea()}
        <p class="-update-muted">${esc(T("update.privacyNote"))}</p>
      </section>
    </div></div>`;
    state.root.innerHTML = html;
    bind();
    if (state.result && state.result.notes) {
      const notes = state.root.querySelector("#update-notes");
      if (notes) notes.textContent = state.result.notes;
    }
    updateAssetWarn();
  }

  function updateAssetWarn() {
    const el = state.root && state.root.querySelector("#update-asset-warn");
    if (!el) return;
    const full = (state.result && state.result.assets || []).find((a) => a.name === state.selected && a.kind === "full");
    el.textContent = full ? T("update.fullWarn") : "";
  }

  function bind() {
    const root = state.root;
    if (!root) return;
    root.querySelector("#update-check")?.addEventListener("click", manualCheck);
    root.querySelector("#update-auto-check")?.addEventListener("change", async (e) => {
      try {
        await call("save_ui_settings", { update: { autoCheck: !!e.target.checked } });
        if (state.info) state.info.auto_check = !!e.target.checked;
      } catch (_) {
        /* 设置写失败不阻断其余功能 */
      }
    });
    root.querySelectorAll('input[name="update-asset"]').forEach((input) => {
      input.addEventListener("change", () => {
        state.selected = input.value;
        updateAssetWarn();
      });
    });
    root.querySelector("#update-download")?.addEventListener("click", startDownload);
    root.querySelector("#update-cancel")?.addEventListener("click", cancelDownload);
    root.querySelector("#update-open-folder")?.addEventListener("click", async () => {
      try {
        await call("open_update_folder");
      } catch (_) {
        /* 忽略 */
      }
    });
    if (state.jobId) applyProgress({ progress: 0, received_human: "", total_human: "" });
  }

  async function manualCheck() {
    if (state.busy) return;
    state.busy = true;
    render();
    try {
      state.result = await call("check_for_update", true);
      if (state.result && state.result.update_available) markBadge();
    } catch (e) {
      state.result = { status: "error", message: String(e) };
    } finally {
      state.busy = false;
      render();
    }
  }

  async function startDownload() {
    const asset = (state.result && state.result.assets || []).find((a) => a.name === state.selected);
    if (!asset) return;
    if (asset.kind === "full" && !global.confirm) {
      /* 无 confirm 的环境（测试）也允许；按钮本身就是显式选择 */
    }
    try {
      const res = await call("start_update_download", asset.name);
      if (res.status === "ok" && res.job_id) {
        state.jobId = res.job_id;
        state.done = null;
        state.verify = null;
        state.done = { status: "running", assetKind: asset.kind };
        render();
        startPolling();
      } else {
        state.done = { status: "failed", failures: [res.message || T("update.startFailed")] };
        render();
      }
    } catch (e) {
      state.done = { status: "failed", failures: [String(e)] };
      render();
    }
  }

  function startPolling() {
    stopPolling();
    const tick = async () => {
      if (!state.jobId) return;
      let st = null;
      try {
        st = await call("get_update_download_status", state.jobId);
      } catch (_) {
        return;
      }
      if (!st) return;
      if (["done", "failed", "cancelled"].includes(st.status)) {
        state.jobId = "";
        // 保留下载前选择的资产类型（决定 lite 的 hf/ 提示）
        state.done = Object.assign({}, st, { assetKind: (state.done && state.done.assetKind) || "" });
        state.verify = st.verification || null;
        stopPolling();
        render();
        return;
      }
      applyProgress(st);
    };
    state.pollTimer = global.setInterval(tick, 500);
  }

  function stopPolling() {
    if (state.pollTimer) {
      global.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function applyProgress(st) {
    const bar = state.root && state.root.querySelector("#update-progress-bar");
    const text = state.root && state.root.querySelector("#update-progress-text");
    if (!bar || !text) return;
    const pct = Number(st.progress || 0);
    bar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    text.textContent = `${pct.toFixed(1)}%  (${st.received_human || ""} / ${st.total_human || ""})`;
  }

  async function cancelDownload() {
    if (!state.jobId) return;
    try {
      await call("cancel_update_download", state.jobId);
    } catch (_) {
      /* 忽略；下一次轮询会反映状态 */
    }
  }

  function markBadge() {
    const btn = document.getElementById("btn-settings");
    if (!btn || btn.querySelector(".-update-badge")) return;
    const dot = document.createElement("span");
    dot.className = "-update-badge";
    dot.title = T("update.badgeTitle");
    btn.appendChild(dot);
  }

  async function openSettings(root) {
    state.root = root;
    root.innerHTML = loadingHtml();
    try {
      state.info = await call("get_update_state");
    } catch (e) {
      state.info = { status: "error", message: String(e) };
    }
    const cached = state.info && state.info.cached;
    if (cached && !state.result) state.result = cached;
    render();
  }

  /** 启动后延迟静默检查（不阻塞窗口显示；出网关闭时后端会直接返回且零请求）。 */
  function init() {
    injectStyle();
    global.setTimeout(async () => {
      try {
        const info = await call("get_update_state");
        if (!info || info.outbound_enabled === false) return;
        if (info.cached && info.cached.update_available) markBadge();
        if (!info.auto_check) return;
        const res = await call("check_for_update", false);
        if (res && res.update_available) markBadge();
        if (state.root && state.info) {
          state.info = info;
          if (!state.result) state.result = res;
        }
      } catch (_) {
        /* 静默失败：更新检查永不影响主功能 */
      }
    }, 6000);
  }

  global.MemoriaUpdateSettings = {
    init,
    openSettings,
    renderSettingsBody: () => "",
    bindSettingsForm: () => {},
    _state: state,
  };
})(typeof window !== "undefined" ? window : globalThis);
