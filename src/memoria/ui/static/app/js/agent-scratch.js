/**
 * 脚本工作区面板（人 2026-09-24 拍板；设计见 `docs/design/agent-capabilities.md §3.4`）。
 *
 * **它是什么**：对话栏里的一块「工作区」——列出 `<kb>/.memoria/agent/scratch/` 里的文件，
 * 给每个文件「查看 / 运行 / 删除」三种动作，并在下方显示最近一次的读到/跑出的输出。
 *
 * **为什么"运行"在这里而不在模型手里**：人拍板的边界是「agent 写脚本，**人点运行**才执行」
 * （模型面只有 `scratch_list/read/write/delete` 四把工具，**没有**执行工具）。
 * 因此本模块只消费五条 RPC：`agent_scratch_status` / `_read` / `_write` / `_delete` / `_run`。
 *
 * **如实告知**（不粉饰）：后端不是沙箱 —— 脚本以当前用户身份运行、能读写文件与网络；
 * 后端只做超时、输出上限与**环境变量白名单**（密钥不会传进子进程）。这一行警告常显在面板上，
 * 点「运行」即视为你已知晓。
 *
 * **零依赖、零侵入**：只用应用门面 `window.MemoriaApp`（`call` / `T` / `esc` / `showFlashError` /
 * `state`），不改 `app.js` / `agent-panel.js`；DOM 由本模块**自建**并插在对话栏的输入区之前
 * （`index.html` 只多一行 `<script>`，追加在末尾 ⇒ 既有 `index.html:<行>` 锚点零漂移）。
 */
(function (global) {
  "use strict";

  const A = () => global.MemoriaApp || {};
  const T = (k, p) => (A().T ? A().T(k, p) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));

  function call(method, ...args) {
    const app = A();
    if (!app.call) return Promise.resolve({ status: "error", code: "no_bridge", message: "桥不可用" });
    return Promise.resolve(app.call(method, ...args));
  }

  function flash(message, detail) {
    const app = A();
    if (app.showFlashError) app.showFlashError(message, detail || "");
  }

  /** 后端回的稳定 code → 本地化（拿不到就原样显示 code，不猜）。 */
  function codeText(code, message) {
    const key = "agent.scratch.code." + String(code || "");
    const text = T(key);
    return text === key ? String(message || code || "") : text;
  }

  /** 面板状态（只此一份；每次 `refresh()` 整体覆盖）。 */
  let view = {
    files: [],
    interpreter: "",
    source: "",
    root: "",
    relDir: ".memoria/agent/scratch/",
    error: "",
    busy: "",
    output: null,
  };

  function dock() {
    const host = document.getElementById("-agent-dock");
    return host && host.isConnected ? host : null;
  }

  function shell() {
    const box = document.getElementById("-agent-scratch");
    return box && box.isConnected ? box : null;
  }

  function byteText(size) {
    const value = Number(size) || 0;
    if (value < 1024) return value + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(1).replace(/\.0$/, "") + " KB";
    return (value / (1024 * 1024)).toFixed(1).replace(/\.0$/, "") + " MB";
  }

  function sourceText(source) {
    const key = "agent.scratch.source." + String(source || "none");
    const text = T(key);
    return text === key ? String(source || "") : text;
  }

  function fileRow(item) {
    const path = String(item.path || "");
    return (
      '<li class="-agent-scratch-row" data-path="' + esc(path) + '">' +
      '<span class="-agent-scratch-name" title="' + esc(path) + '">' + esc(path) + "</span>" +
      '<span class="-agent-scratch-size">' + esc(byteText(item.size)) + "</span>" +
      '<button type="button" class="-btn secondary -btn--sm" data-act="view">' + esc(T("agent.scratch.view")) + "</button>" +
      '<button type="button" class="-btn secondary -btn--sm -agent-scratch-run" data-act="run" title="' +
      esc(T("agent.scratch.runTitle")) + '">' + esc(T("agent.scratch.run")) + "</button>" +
      '<button type="button" class="-btn secondary -btn--sm" data-act="delete">' + esc(T("agent.scratch.delete")) + "</button>" +
      "</li>"
    );
  }

  function outputHtml() {
    const out = view.output;
    if (!out) return "";
    const head =
      out.kind === "run"
        ? T("agent.scratch.exit", { code: out.exitCode, ms: out.ms }) +
          (out.timedOut ? " · " + T("agent.scratch.timeout", { s: out.timeoutS }) : "") +
          (out.truncated ? " · " + T("agent.scratch.truncated") : "")
        : T("agent.scratch.viewed", { path: out.path });
    const body = [out.stdout, out.stderr].filter(Boolean).join("\n");
    return (
      '<div class="-agent-scratch-out-wrap">' +
      '<div class="-agent-scratch-out-head ' + (out.exitCode === 0 && !out.timedOut ? "" : "-agent-scratch-out-bad") + '">' +
      esc(head) +
      "</div>" +
      '<pre class="-agent-scratch-out">' +
      esc(body || T("agent.scratch.noOutput")) +
      "</pre>" +
      "</div>"
    );
  }

  function render() {
    const box = shell();
    if (!box) return;
    const summary = box.querySelector(".-agent-scratch-summary");
    if (summary) {
      const count = view.files.length;
      summary.textContent =
        T("agent.scratch.title") + " · " + (count ? T("agent.scratch.summary", { n: count }) : T("agent.scratch.empty"));
    }
    const meta = box.querySelector(".-agent-scratch-meta");
    if (meta) {
      const interpreter = view.interpreter
        ? T("agent.scratch.interpreter", { path: view.interpreter, source: sourceText(view.source) })
        : T("agent.scratch.interpreterNone");
      meta.textContent = interpreter;
      meta.classList.toggle("-agent-scratch-meta--bad", !view.interpreter);
    }
    const list = box.querySelector(".-agent-scratch-list");
    if (list) {
      list.innerHTML = view.files.map(fileRow).join("");
      list.hidden = !view.files.length;
      Array.prototype.forEach.call(list.querySelectorAll("button"), (btn) => {
        const row = btn.closest(".-agent-scratch-row");
        const path = row ? String(row.getAttribute("data-path") || "") : "";
        const disabled = view.busy === path || (!view.interpreter && btn.getAttribute("data-act") === "run");
        btn.disabled = disabled;
      });
    }
    const empty = box.querySelector(".-agent-scratch-empty");
    if (empty) empty.hidden = !!view.files.length;
    const out = box.querySelector(".-agent-scratch-out-host");
    if (out) out.innerHTML = outputHtml();
    box.setAttribute("data-state", view.busy ? "busy" : view.interpreter ? "ready" : "no-interpreter");
  }

  function mount() {
    const host = dock();
    if (!host || shell()) return shell();
    const composer = host.querySelector(".-agent-composer");
    const box = document.createElement("details");
    box.id = "-agent-scratch";
    box.className = "-agent-scratch";
    box.innerHTML =
      '<summary class="-agent-scratch-summary"></summary>' +
      '<div class="-agent-scratch-body">' +
      '<div class="-agent-scratch-bar">' +
      '<span class="-agent-scratch-meta"></span>' +
      '<button type="button" class="-btn secondary -btn--sm" data-scratch="refresh">' +
      esc(T("agent.scratch.refresh")) +
      "</button>" +
      "</div>" +
      '<div class="-agent-scratch-warn">' + esc(T("agent.scratch.warn")) + "</div>" +
      '<ul class="-agent-scratch-list"></ul>' +
      '<div class="-agent-scratch-empty">' + esc(T("agent.scratch.emptyHint")) + "</div>" +
      '<div class="-agent-scratch-out-host"></div>' +
      "</div>";
    if (composer) host.insertBefore(box, composer);
    else host.appendChild(box);
    bind(box);
    render();
    return box;
  }

  function bind(box) {
    box.addEventListener("click", (event) => {
      const target = event.target;
      if (!target || !target.closest) return;
      if (target.closest("[data-scratch='refresh']")) {
        refresh(true);
        return;
      }
      const btn = target.closest("button[data-act]");
      if (!btn) return;
      const row = btn.closest(".-agent-scratch-row");
      const path = row ? String(row.getAttribute("data-path") || "") : "";
      if (!path) return;
      const act = btn.getAttribute("data-act");
      if (act === "view") viewFile(path);
      else if (act === "run") runFile(path);
      else if (act === "delete") deleteFile(path);
    });
  }

  /** 拉一次状态（`force` 只影响状态行的忙碌提示；失败给浮层但不炸面板）。 */
  async function refresh(force) {
    if (!dock()) return;
    mount();
    let res;
    try {
      res = await call("agent_scratch_status", (A().state || {}).kbPath || null);
    } catch (err) {
      res = { status: "error", message: String((err && err.message) || err) };
    }
    if (!res || res.status !== "ok") {
      if (force) flash(codeText(res && res.code, res && res.message));
      return;
    }
    view.files = Array.isArray(res.files) ? res.files : [];
    view.interpreter = String(res.interpreter || "");
    view.source = String(res.source || "");
    view.root = String(res.root || "");
    view.relDir = String(res.rel_dir || view.relDir);
    view.error = String(res.error || "");
    render();
  }

  async function viewFile(path) {
    view.busy = path;
    render();
    let res;
    try {
      res = await call("agent_scratch_read", path, (A().state || {}).kbPath || null);
    } catch (err) {
      res = { status: "error", message: String((err && err.message) || err) };
    }
    view.busy = "";
    if (!res || res.status !== "ok") {
      flash(T("agent.scratch.failed"), codeText(res && res.code, res && res.message));
      render();
      return;
    }
    view.output = {
      kind: "view",
      path: String(res.path || path),
      stdout: String(res.text || ""),
      stderr: "",
      exitCode: 0,
      truncated: !!res.truncated,
    };
    render();
  }

  /** 当前会话 id（审计要带上它）：读 `get_ui_settings` 的 `agent.lastSessionByKb`（与 `agent-panel.js` 同源）。
   *  取不到就返回 `null` —— 后端此时按 `audit.append` 的既有语义记 "skipped"，**不假装记过**。 */
  async function currentSessionId() {
    const kb = String((A().state || {}).kbPath || "");
    if (!kb) return null;
    try {
      const res = await call("get_ui_settings");
      const agent = res && res.status === "ok" && res.settings && res.settings.agent;
      const map = agent && agent.lastSessionByKb;
      if (!map || typeof map !== "object") return null;
      const key = kb.trim().replace(/\//g, "\\").replace(/\\+$/, "").toLowerCase();
      const id = typeof map[key] === "string" ? map[key].trim() : "";
      return id || null;
    } catch (_err) {
      return null;
    }
  }

  /** 运行一个脚本 —— **只有这一个入口**（模型面没有执行工具）；点它即视为你已读警告行。 */
  async function runFile(path) {
    if (!view.interpreter) {
      flash(T("agent.scratch.interpreterNone"), view.error || "");
      return;
    }
    view.busy = path;
    render();
    const sessionId = await currentSessionId();
    let res;
    try {
      res = await call(
        "agent_scratch_run",
        path,
        null,
        sessionId,
        (A().state || {}).kbPath || null
      );
    } catch (err) {
      res = { status: "error", message: String((err && err.message) || err) };
    }
    view.busy = "";
    if (!res || res.status !== "ok") {
      flash(T("agent.scratch.failed"), codeText(res && res.code, res && res.message));
      render();
      return;
    }
    view.output = {
      kind: "run",
      path: String(res.path || path),
      stdout: String(res.stdout || ""),
      stderr: String(res.stderr || ""),
      exitCode: Number(res.exit_code) || 0,
      ms: Number(res.duration_ms) || 0,
      timedOut: !!res.timed_out,
      truncated: !!res.truncated,
      timeoutS: Number(res.timeout_s) || 0,
    };
    render();
    refresh(); // 脚本可能自己写了新文件
  }

  async function deleteFile(path) {
    const question = T("agent.scratch.deleteConfirm", { path: path });
    if (global.confirm && !global.confirm(question)) return;
    let res;
    try {
      res = await call("agent_scratch_delete", path, (A().state || {}).kbPath || null);
    } catch (err) {
      res = { status: "error", message: String((err && err.message) || err) };
    }
    if (!res || res.status !== "ok") {
      flash(T("agent.scratch.failed"), codeText(res && res.code, res && res.message));
      return;
    }
    if (view.output && view.output.path === path) view.output = null;
    refresh();
  }

  //: 轮询钩子（同 `agent-question.js` 的手法）：**一轮结束**才刷一次列表（agent 这轮可能写了文件），
  //: 运行中不刷（省 RPC，也不打断正在看的东西）。
  (function bindPoll() {
    const facade = A();
    const base = facade && facade.call;
    if (typeof base !== "function") return;
    facade.call = function (fnName) {
      const pending = base.apply(this, arguments);
      if (fnName !== "agent_ask_poll") return pending;
      return Promise.resolve(pending).then((res) => {
        if (res && res.status && res.status !== "running") refresh();
        return res;
      });
    };
  })();

  /** 启动：等到对话栏真的在 DOM 里再挂（面板可能被折叠 / 换库后重建）。 */
  function boot() {
    if (!dock()) return;
    mount();
    refresh();
  }

  if (global.document) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
    // pywebview 桥就绪后（真机）再刷一次：语言包与 kb 路径此时才准
    global.addEventListener("pywebviewready", boot);
  }

  global.MemoriaAgentScratch = { refresh, render, viewState: () => view };
})(window);
