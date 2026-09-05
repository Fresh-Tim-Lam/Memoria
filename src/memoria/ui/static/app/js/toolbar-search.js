/**
 * 工具条全局/当前文件搜索（原 app.js 搜索子系统，2026-09-04 抽出）。
 *
 * 自包含：Ctrl+K 聚焦、输入防抖搜索、范围切换（全库/当前文件）、结果面板渲染与跳转、
 * 文档内正文定位命中。事件绑定全部由本模块 init() 完成。
 *
 * 依赖 window.MemoriaApp（app.js 门面）：state/call/T/esc/setStatus/setStatusError/openFile。
 * 依赖 window.MemoriaSearchSettings（search-settings.js）。
 */
window.MemoriaToolbarSearch = (function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const A = () => window.MemoriaApp || {};

  let _timer = null;
  let _results = [];
  let _bodyHits = [];

  function t(key, params) {
    const a = A();
    return a.T ? a.T(key, params) : key;
  }
  function esc(s) {
    const a = A();
    return a.esc ? a.esc(s) : String(s == null ? "" : s);
  }
  function basename(p) {
    const parts = String(p || "").replace(/\\/g, "/").split("/");
    return parts[parts.length - 1];
  }

  function focusInput() {
    const input = $("#toolbar-search");
    if (!input) return;
    input.focus();
    input.select();
  }

  function hidePanel() {
    $("#toolbar-search-panel")?.classList.add("hidden");
  }

  function showPanel(html) {
    const panel = $("#toolbar-search-panel");
    if (!panel) return;
    panel.innerHTML = html;
    panel.classList.remove("hidden");
  }

  /** 刷新范围切换按钮的 active/disabled/title（openFile 等改变 currentPath 后由 app.js 调用） */
  function syncScope() {
    const a = A();
    const state = a.state || {};
    const scope = state.toolbarSearchScope === "file" ? "file" : "kb";
    $("#toolbar-search-scope-kb")?.classList.toggle("active", scope === "kb");
    $("#toolbar-search-scope-file")?.classList.toggle("active", scope === "file");
    const fileBtn = $("#toolbar-search-scope-file");
    if (fileBtn) {
      fileBtn.disabled = !state.currentPath;
      fileBtn.title = state.currentPath
        ? t("search.scopeFileNamed", { file: basename(state.currentPath) })
        : t("app.openFileFirst");
    }
    const scopeSwitch = $("#toolbar-search-scope");
    if (scopeSwitch) {
      scopeSwitch.setAttribute("aria-checked", scope === "file" ? "true" : "false");
      scopeSwitch.title =
        scope === "file"
          ? fileBtn?.title || t("search.scopeFileSwitchTitle")
          : t("search.scopeKbSwitchTitle");
    }
  }

  function toggleScope() {
    const a = A();
    const state = a.state || {};
    const cur = state.toolbarSearchScope === "file" ? "file" : "kb";
    setScope(cur === "file" ? "kb" : "file");
  }

  function setScope(scope) {
    const a = A();
    const state = a.state || {};
    if (scope === "file" && !state.currentPath) {
      a.setStatusError?.(t("app.openFileFirst"));
      return;
    }
    state.toolbarSearchScope = scope === "file" ? "file" : "kb";
    try {
      localStorage.setItem("-search-scope", state.toolbarSearchScope);
    } catch (_) { /* ignore */ }
    syncScope();
    const q = $("#toolbar-search")?.value?.trim();
    if (q) runSearch();
  }

  function tierLabel(tier) {
    return { high: t("search.tier.high"), medium: t("search.tier.medium"), low: t("search.tier.low") }[tier] || tier;
  }

  function formatScore(hit, modes) {
    const mode = (modes || "lexical").toLowerCase();
    const sem =
      hit.semantic_score != null
        ? hit.semantic_score
        : hit.confidence != null
          ? hit.confidence
          : null;
    const lex = hit.lexical_score != null ? hit.lexical_score : null;

    if (mode === "semantic" && sem != null) {
      return t("search.scoreSem", { n: Math.round(sem) });
    }
    if (mode === "both" || mode === "full") {
      const parts = [];
      if (lex != null && lex > 0) parts.push(t("search.scoreLex", { n: Math.round(lex) }));
      if (sem != null && sem > 0) parts.push(t("search.scoreSem", { n: Math.round(sem) }));
      if (hit.tier) parts.push(tierLabel(hit.tier));
      if (parts.length) return parts.join(" · ");
    }
    if (hit.tier && mode === "lexical") {
      return `${t("search.scoreLex", { n: Math.round(lex != null ? lex : hit.score || 0) })} · ${tierLabel(hit.tier)}`;
    }
    if (lex != null) return t("search.scoreLex", { n: Math.round(lex) });
    return String(Math.round(hit.score || 0));
  }

  async function runSearch(opts = {}) {
    const a = A();
    const state = a.state || {};
    if (!state.kbPath) {
      a.setStatusError?.(t("app.openKbFirst"));
      return;
    }
    const q = $("#toolbar-search")?.value?.trim() || "";
    if (!q) {
      hidePanel();
      return;
    }
    const shiftFile = !!opts.fileOnly && !!state.currentPath;
    const scope = shiftFile || state.toolbarSearchScope === "file" ? "file" : "kb";
    if (scope === "file" && !state.currentPath) {
      a.setStatusError?.(t("app.openFileFirst"));
      return;
    }
    const relPath = scope === "file" ? state.currentPath : "";
    const scopeHint = scope === "file" ? t("search.scopeFileSuffix", { file: basename(state.currentPath) }) : "";
    a.setStatus?.(t("search.statusSearching"), q + scopeHint);
    try {
      const modesRequested = window.MemoriaSearchSettings?.getSearchModes?.() || "lexical";
      const res = await a.call("search", q, scope, 20, modesRequested, relPath);
      if (res.status === "error") {
        hidePanel();
        a.setStatusError?.(t("search.statusSearchFailed"), res.message || "");
        return;
      }
      const items = res.results || [];
      const bodyHits = res.body_locate || [];
      _results = items;
      _bodyHits = bodyHits;
      const modes = res.modes || modesRequested;
      if (!items.length && !bodyHits.length) {
        let hint = t("search.noMatch", { q: esc(q) });
        if (
          modes !== "lexical" &&
          res.semantic?.available === false &&
          res.semantic?.reason
        ) {
          const reasonMap = {
            embedding_not_enabled: t("search.semReasonNotEnabled"),
            embedding_not_installed: t("search.semReasonNotInstalled"),
            embedding_index_empty: t("search.semReasonIndexEmpty"),
          };
          hint += ` · ${reasonMap[res.semantic.reason] || res.semantic.reason}`;
        }
        if (!window.MemoriaSearchSettings?.isBodyLocateEnabled?.()) {
          hint += t("search.bodyLocateTip");
        }
        showPanel(`<div class="-search-placeholder">${hint}</div>`);
      } else {
        let html = "";
        if (items.length) {
          html += items
            .map(
              (it, i) =>
                `<button type="button" class="-suggest-item -toolbar-search-hit" data-search-kind="kp" data-search-idx="${i}">
                  <span class="-suggest-score" title="${esc((it.sources || []).join(", "))}">${esc(formatScore(it, modes))}</span>
                  <div class="-toolbar-search-main">
                    <span class="-suggest-label">${esc(it.label || it.name || it.id || "")}</span>
                    <span class="-muted -toolbar-search-file">${esc(basename(it.file || ""))}</span>
                  </div>
                </button>`
            )
            .join("");
        }
        if (bodyHits.length) {
          if (items.length) {
            html += `<div class="-search-section-label">${t("search.bodySection")}</div>`;
          }
          html += bodyHits
            .map(
              (it, i) =>
                `<button type="button" class="-suggest-item -toolbar-search-hit -toolbar-search-body" data-search-kind="body" data-body-idx="${i}">
                  <span class="-suggest-score -suggest-score--muted" title="${t("search.bodyLineTitle")}">L${esc(String(it.line || ""))}</span>
                  <div class="-toolbar-search-main">
                    <span class="-suggest-label">${esc(it.label || it.snippet || "")}</span>
                    <span class="-muted -toolbar-search-file">${esc(basename(it.file || ""))}</span>
                  </div>
                </button>`
            )
            .join("");
        }
        showPanel(html);
        $("#toolbar-search-panel")
          ?.querySelectorAll(".-toolbar-search-hit")
          .forEach((btn) => {
            btn.addEventListener("click", async () => {
              const kind = btn.getAttribute("data-search-kind") || "kp";
              if (kind === "body") {
                const idx = parseInt(btn.getAttribute("data-body-idx") || "-1", 10);
                const hit = _bodyHits[idx];
                if (!hit?.file) return;
                hidePanel();
                await a.openFile?.(hit.file, { lineHint: hit.line });
                return;
              }
              const idx = parseInt(btn.getAttribute("data-search-idx") || "-1", 10);
              const hit = _results[idx];
              if (!hit?.file) return;
              hidePanel();
              await a.openFile?.(hit.file, { kpId: hit.kp_id || null });
            });
          });
      }
      const total = items.length + bodyHits.length;
      a.setStatus?.(t("search.statusDone"), t("search.resultCount", { total, q, suffix: scopeHint }));
    } catch (e) {
      hidePanel();
      a.setStatusError?.(t("search.statusSearchFailed"), String(e.message || e));
    }
  }

  function init() {
    $("#toolbar-search")?.addEventListener("input", () => {
      clearTimeout(_timer);
      _timer = setTimeout(() => {
        const q = $("#toolbar-search")?.value?.trim();
        if (q) runSearch();
        else hidePanel();
      }, 220);
    });
    $("#toolbar-search-scope")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleScope();
    });
    $("#toolbar-search-scope")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleScope();
      }
    });
    syncScope();
    $("#toolbar-search")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runSearch({ fileOnly: e.shiftKey });
      } else if (e.key === "Escape") {
        hidePanel();
        e.target.blur();
      }
    });
    $("#toolbar-search")?.addEventListener("focus", () => {
      const q = $("#toolbar-search")?.value?.trim();
      if (q) runSearch();
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".toolbar-search-wrap")) hidePanel();
    });
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        focusInput();
      }
    });
  }

  return { init, syncScope };
})(typeof window !== "undefined" ? window : globalThis);
