/**
 * 轻提示（toast）：底部居中浮层，自动消失（2026-09-10 新增）。
 *
 * 用途：需要「操作已完成」这类瞬时反馈、但不适合占用状态栏或弹窗的场景。
 * 典型：弹窗打开时状态栏被遮住——复制类操作在弹窗内看不到反馈。
 *
 * 用法（文案由调用方经 T()/t() 取好再传入，本模块不持有任何文案、零 i18n 键）：
 *   MemoriaToast.show(T("check.copyDone"));
 *   MemoriaToast.show(T("check.copyFailed"), { type: "error" });
 *   MemoriaToast.show(msg, { ms: 5000 });
 *
 * 同一时刻只保留一条：新消息顶替旧消息并重置计时。
 */
window.MemoriaToast = (function (global) {
  "use strict";

  const DEFAULT_MS = 2400;

  let host = null;
  let hideTimer = null;

  /** 取（或按需创建）宿主节点：优先用 index.html 声明元素，缺失时兜底自建。 */
  function ensureHost() {
    if (host && host.isConnected) return host;
    host = document.getElementById("-toast");
    if (!host) {
      host = document.createElement("div");
      host.id = "-toast";
      host.className = "-toast";
      host.setAttribute("role", "status");
      host.setAttribute("aria-live", "polite");
      document.body.appendChild(host);
    }
    return host;
  }

  function show(text, opts) {
    const msg = String(text == null ? "" : text);
    if (!msg) return;
    const options = opts || {};
    const el = ensureHost();
    el.textContent = msg;
    el.classList.toggle("-toast--error", options.type === "error");
    el.classList.add("-toast--visible");
    if (hideTimer) clearTimeout(hideTimer);
    const ms = Number.isFinite(options.ms) ? options.ms : DEFAULT_MS;
    hideTimer = global.setTimeout(() => {
      hideTimer = null;
      el.classList.remove("-toast--visible");
    }, ms);
  }

  function hide() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    const el = document.getElementById("-toast");
    if (el) el.classList.remove("-toast--visible");
  }

  return { show, hide };
})(typeof window !== "undefined" ? window : globalThis);
