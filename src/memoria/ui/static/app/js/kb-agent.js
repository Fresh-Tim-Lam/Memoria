/**
 * 知识库级「创建 Trae 智能体」前端入口。
 *
 * 流程：工具栏「文件」→「创建 Trae 智能体」
 *   → install_kb_agent（幂等：写入/跳过 <KB>/.memoria/agent/**）
 *   → 结果摘要（写入 / 跳过 的文件列表 + agent_dir）
 *   → 使用步骤 + 只读指令 textarea（返回的 prompt 全文）
 *   → 「复制指令」（navigator.clipboard，失败回退 textarea + execCommand）
 *
 * 复用 .-modal 通用浮层 #kb-agent-modal（结构与 import-conflict-modal 镜像）。
 * 文案全部经 T()（toolbar.kbAgent / kbAgent.* 键族）；菜单项始终可点，
 * 未打开知识库时点击先唤起「打开知识库」目录选择，取消则中止。
 *
 * 依赖 window.MemoriaApp（app.js 导出的应用服务门面）：
 *   state / call / T / esc / setStatus / setStatusError / openKb
 */
window.MemoriaKbAgent = (function () {
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

  let _busy = false;
  let _lastResult = null; // 语言切换后重绘已打开的弹窗时复用

  /** 关闭「文件」下拉（菜单项点击后手动收起，与「导入」一致）。 */
  function closeFileMenu() {
    const menu = $("#file-menu");
    if (menu) menu.hidden = true;
    $("#btn-file")?.setAttribute("aria-expanded", "false");
  }

  // ── 入口：调用后端安装并渲染结果 ─────────────────────────────────

  async function start() {
    const a = A();
    // 未打开知识库：先唤起「打开知识库」（目录选择）；用户取消则中止
    if (!a.state || !a.state.kbPath) {
      await a.openKb?.();
      if (!a.state || !a.state.kbPath) return;
    }
    if (_busy) return;
    _busy = true;
    try {
      a.setStatus?.(t("kbAgent.running"));
      const res = await a.call("install_kb_agent");
      if (!res || res.status === "error") {
        a.setStatusError?.((res && res.message) || t("kbAgent.failed"));
        return;
      }
      _lastResult = res;
      renderResult(res);
      $("#kb-agent-modal")?.classList.remove("hidden");
      a.setStatus?.(t("kbAgent.done"));
    } catch (e) {
      a.setStatusError?.(t("kbAgent.failed"), String(e.message || e));
    } finally {
      _busy = false;
    }
  }

  // ── 打开知识库后自动补写 / 刷新工具包（幂等，不弹窗）──────────────

  /** 由 app.js 在打开/切换知识库后调用：补齐或升级 `.memoria/agent/`。
   *  仅在实际写入时给一条状态提示，失败静默（不阻塞、不打扰打开流程）。 */
  async function ensure() {
    const a = A();
    if (!a.state || !a.state.kbPath) return;
    try {
      const res = await a.call("install_kb_agent");
      if (!res || res.status === "error") {
        const msg = (res && res.message) || "unknown";
        console.warn("[kb-agent] 自动补写失败:", msg);
        a.setStatusError?.(t("kbAgent.failed"), msg);
        return;
      }
      const written = res.written || [];
      if (written.length) {
        console.log("[kb-agent] 已补写/刷新:", written.join(", "));
        a.setStatus?.(t("kbAgent.autoUpdated", { n: written.length }));
      }
    } catch (e) {
      console.warn("[kb-agent] 自动补写异常:", String((e && e.message) || e));
      a.setStatusError?.(t("kbAgent.failed"), String((e && e.message) || e));
    }
  }

  // ── 结果渲染 ─────────────────────────────────────────────────

  function fileListHtml(files) {
    if (!files || !files.length) return "";
    let html = `<ul class="-import-file-list">`;
    files.forEach((f) => {
      html += `<li><code>${esc(f)}</code></li>`;
    });
    html += `</ul>`;
    return html;
  }

  function renderResult(res) {
    const body = $("#kb-agent-body");
    if (!body) return;
    const written = res.written || [];
    const skipped = res.skipped || [];
    const usage = [
      t("kbAgent.step1"),
      t("kbAgent.step2"),
      t("kbAgent.step3"),
      t("kbAgent.step4"),
    ];

    let html = `<div class="-import-scan-summary">`;
    html += `<p><code>${esc(t("kbAgent.dir", { dir: res.agent_dir || "" }))}</code></p>`;
    html += `<p>${esc(t("kbAgent.written", { n: written.length }))}</p>`;
    html += fileListHtml(written);
    html += `<p>${esc(t("kbAgent.skipped", { n: skipped.length }))}</p>`;
    html += fileListHtml(skipped);
    html += `</div>`;

    html += `<h4 class="-import-section-title">${esc(t("kbAgent.usageTitle"))}</h4>`;
    html += `<ol class="-import-file-list">`;
    usage.forEach((u) => {
      html += `<li>${esc(u)}</li>`;
    });
    html += `</ol>`;

    html += `<textarea id="kb-agent-prompt-text" class="-import-report-textarea" readonly rows="14">${esc(
      res.prompt || ""
    )}</textarea>`;

    body.innerHTML = html;
  }

  // ── 复制指令（clipboard 优先，回退选区 + execCommand）─────────────

  function fallbackCopy(ta) {
    if (!ta) return false;
    try {
      ta.focus();
      ta.select();
      if (typeof ta.setSelectionRange === "function") {
        ta.setSelectionRange(0, ta.value.length);
      }
      const ok = document.execCommand("copy");
      window.getSelection?.()?.removeAllRanges?.();
      return !!ok;
    } catch (_) {
      return false;
    }
  }

  async function copyPrompt() {
    const a = A();
    const ta = $("#kb-agent-prompt-text");
    const text = ta ? ta.value : "";
    if (!text) return;
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) {
        throw new Error("no-clipboard");
      }
      await navigator.clipboard.writeText(text);
      a.setStatus?.(t("kbAgent.copied"));
    } catch (_) {
      if (fallbackCopy(ta)) {
        a.setStatus?.(t("kbAgent.copied"));
      } else {
        a.setStatusError?.(t("kbAgent.copyFailed"));
      }
    }
  }

  // ── 关闭 / 事件绑定 ─────────────────────────────────────────────

  function closeModal() {
    $("#kb-agent-modal")?.classList.add("hidden");
  }

  function init() {
    $("#file-menu-kb-agent")?.addEventListener("click", () => {
      closeFileMenu();
      start();
    });
    $("#kb-agent-copy")?.addEventListener("click", () => copyPrompt());
    $("#kb-agent-close")?.addEventListener("click", closeModal);
    $("#kb-agent-close-x")?.addEventListener("click", closeModal);
    $("#kb-agent-modal .-modal-backdrop")?.addEventListener("click", closeModal);
    // 语言切换后重绘已打开的弹窗
    if (window.MemoriaI18n) {
      MemoriaI18n.addRefresh(function () {
        if (_lastResult && !$("#kb-agent-modal")?.classList.contains("hidden")) {
          renderResult(_lastResult);
        }
      });
    }
  }

  return { init, start, ensure };
})(typeof window !== "undefined" ? window : globalThis);
