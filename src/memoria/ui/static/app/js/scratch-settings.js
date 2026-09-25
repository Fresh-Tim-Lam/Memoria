/**
 * 脚本工作区的三个设置（人 2026-09-24 拍板：AG59 落地时这三个键**只能手改 `config/agent.json`**，
 * 台账里如实记着"暂无界面"；设计见 `docs/design/agent-capabilities.md §3.4`）。
 *
 * **它做什么**：在设置 →「Agent」→「对话」里追加一个小版块：解释器路径、是否允许用发布包内置的那一份、
 * 单次执行超时。下面一行**现场回显"最终会用哪个解释器、来源是哪一档"**（显式 / 内置 / 系统 / 没找到）——
 * 免得改了半天不知道有没有生效。
 *
 * **只消费两条 RPC**：`agent_script_settings`（读三键 + 解析结果，**不依赖知识库** ⇒ 没开库也能改）、
 * `agent_save_config`（浅合并写键）。**执行权不在设置里**：模型面没有运行工具，脚本只能由人在
 * 工作区面板点「运行」；且脚本以当前用户身份运行（**不是沙箱**）。
 *
 * **零依赖、零侵入**：只用应用门面 `window.MemoriaApp`（`call` / `T` / `esc` / `showFlashInfo` /
 * `showFlashError`）；DOM 由本模块自建后**追加**进 `#agent-settings`（`index.html` 只多一行 `<script>`
 * ⇒ 既有 `index.html:<行>` 锚点零漂移），并注册 `MemoriaI18n.addRefresh()` 跟随语言切换。
 */
(function (global) {
  "use strict";

  const A = () => global.MemoriaApp || {};
  const T = (k, p) => (A().T ? A().T(k, p) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));

  function call(method, ...args) {
    const app = A();
    // 兜底文案走 i18n（新文件不进 `scan_ui_strings.py` 的未迁移清单；同批兄弟模块里那几处同名硬编码属存量，见 i18n-inventory）。
    if (!app.call) return Promise.resolve({ status: "error", code: "no_bridge", message: T("settings.script.noBridge") });
    return Promise.resolve(app.call(method, ...args));
  }

  function flash(message, detail) {
    const app = A();
    if (app.showFlashError) app.showFlashError(message, detail || "");
  }

  const ID = "-script-settings";
  //: 三个键与 `llm/config.py` 的键名一一对应（**只增不改**）。
  const KEYS = { interpreter: "script_interpreter", bundled: "script_use_bundled", timeout: "script_timeout_s" };

  function host() {
    const box = document.getElementById("agent-settings");
    return box && box.isConnected ? box : null;
  }

  function shell() {
    const box = document.getElementById(ID);
    return box && box.isConnected ? box : null;
  }

  function field(name) {
    return document.getElementById("-script-" + name);
  }

  //: 最近一次读到的现状（`agent_script_settings` 的返回）；`limits` 缺席时用后端的兜底值。
  let state = {
    interpreter: "",
    use_bundled: true,
    timeout_s: 60,
    default_timeout_s: 60,
    resolved: { path: "", source: "none" },
    bundled_dir: "",
    bundled_name: "python",
    error: "",
    limits: { min_timeout_s: 5, max_timeout_s: 300 },
  };

  function limits() {
    const raw = state.limits && typeof state.limits === "object" ? state.limits : {};
    const min = Number(raw.min_timeout_s);
    const max = Number(raw.max_timeout_s);
    return {
      min: Number.isFinite(min) && min > 0 ? min : 5,
      max: Number.isFinite(max) && max > 0 ? max : 300,
    };
  }

  /** 文案（语言切换后会再跑一次）。 */
  function paintTexts() {
    const box = shell();
    if (!box) return;
    box.querySelector("[data-script='title']").textContent = T("settings.script.title");
    box.querySelector("[data-script='interpreter']").textContent = T("settings.script.interpreterLabel");
    box.querySelector("[data-script='bundled']").textContent = T("settings.script.useBundledLabel");
    box.querySelector("[data-script='timeout']").textContent = T("settings.script.timeoutLabel");
    box.querySelector("[data-script='hint']").textContent = T("settings.script.hint");
    const path = field("interpreter");
    if (path) path.setAttribute("placeholder", T("settings.script.interpreterPh"));
    paintResolved(state);
  }

  /** 解析结果回显：用哪个解释器 + 来源档 + 内置目录在不在 + 显式路径报错。 */
  function paintResolved(data) {
    const box = shell();
    if (!box) return;
    const node = box.querySelector("[data-script='resolved']");
    if (!node) return;
    const resolved = data.resolved && typeof data.resolved === "object" ? data.resolved : {};
    const source = String(resolved.source || "none");
    const sourceText = T("settings.script.source." + source);
    const parts = [];
    if (data.error) {
      parts.push(T("settings.script.badPath", { error: data.error }));
    } else if (source === "none") {
      parts.push(T("settings.script.noInterpreter"));
    } else {
      parts.push(T("settings.script.resolved", { path: resolved.path || "", source: sourceText }));
    }
    parts.push(
      data.bundled_dir
        ? T("settings.script.bundledPresent", { dir: data.bundled_dir })
        : T("settings.script.bundledMissing", { name: data.bundled_name || "python" })
    );
    const { min, max } = limits();
    parts.push(T("settings.script.timeoutRange", { min: min, max: max }));
    node.textContent = parts.join(" · ");
    node.classList.toggle("-script-resolved--bad", Boolean(data.error) || source === "none");
  }

  function render(data) {
    state = Object.assign({}, state, data || {});
    const path = field("interpreter");
    const bundled = field("bundled");
    const timeout = field("timeout");
    const { min, max } = limits();
    if (path && document.activeElement !== path) path.value = String(state.interpreter || "");
    if (bundled && document.activeElement !== bundled) bundled.checked = state.use_bundled !== false;
    if (timeout) {
      timeout.min = String(min);
      timeout.max = String(max);
      if (document.activeElement !== timeout) timeout.value = String(state.timeout_s || "");
    }
    paintResolved(state);
  }

  async function refresh() {
    let res;
    try {
      res = await call("agent_script_settings");
    } catch (err) {
      res = { status: "error", message: String((err && err.message) || err) };
    }
    if (!res || res.status !== "ok") return;
    render(res);
  }

  /** 存一个键（`agent_save_config` 是浅合并 ⇒ 只动这一键，不会碰同页其它设置）。 */
  async function save(key, value) {
    let res;
    try {
      res = await call("agent_save_config", { [key]: value });
    } catch (err) {
      res = { status: "error", message: String((err && err.message) || err) };
    }
    if (!res || res.status !== "ok") {
      flash(T("settings.script.failed"), (res && (res.message || res.code)) || "");
      refresh(); // 回滚显示：以磁盘上的现状为准
      return;
    }
    const info = A().showFlashInfo;
    if (info) info(T("settings.script.saved"));
    refresh(); // 重新解析一次 ⇒ 回显行立刻反映新选择
  }

  /** 超时输入：**正数**才收（非数字 / ≤0 ⇒ 报错并回滚显示）；正数但越界 ⇒ 夹到 5–300 再存。
   *
   * 为什么这样分：写侧（`llm/config.py::_coerce_timeout`）只校验"是正数"，真正的 5–300 夹取发生在
   * **执行时**（`scratch._clamp_timeout`）。所以前端把"越界但合法"的值先夹好、免得用户以为设了 999 就是 999；
   * 而 0 / 负数在写侧会被直接拒（`ConfigError`）—— 那些**照原样报错**，不偷偷改成 5（那会改变语义）。 */
  function saveTimeout(raw) {
    const text = String(raw == null ? "" : raw).trim();
    const { min, max } = limits();
    const value = Number(text);
    if (!text || !Number.isFinite(value) || value <= 0) {
      flash(T("settings.script.badTimeout"), text);
      refresh();
      return;
    }
    const clamped = Math.min(Math.max(value, min), max);
    if (clamped !== value) {
      const info = A().showFlashInfo;
      if (info) info(T("settings.script.clamped", { value: clamped }));
    }
    save(KEYS.timeout, clamped);
  }

  function mount() {
    const box = host();
    if (!box || shell()) return shell();
    const wrap = document.createElement("div");
    wrap.id = ID;
    wrap.className = "-script-settings";
    wrap.innerHTML =
      '<div class="-settings-section-head" data-script="title"></div>' +
      '<label class="-agent-field"><span data-script="interpreter"></span>' +
      '<input type="text" id="-script-interpreter" spellcheck="false" autocomplete="off"></label>' +
      '<label class="-script-switch"><input type="checkbox" id="-script-bundled">' +
      '<span data-script="bundled"></span></label>' +
      '<label class="-agent-field"><span data-script="timeout"></span>' +
      '<input type="number" id="-script-timeout" inputmode="numeric" step="1"></label>' +
      '<p class="-script-hint" data-script="hint"></p>' +
      '<p class="-script-resolved" data-script="resolved"></p>';
    box.appendChild(wrap);
    const path = field("interpreter");
    const bundled = field("bundled");
    const timeout = field("timeout");
    // `change` = 失焦或回车后触发一次（与 net-settings 同款：不做按键级保存，免得半截路径被写进盘）
    if (path) path.addEventListener("change", () => save(KEYS.interpreter, path.value.trim()));
    if (bundled) bundled.addEventListener("change", () => save(KEYS.bundled, Boolean(bundled.checked)));
    if (timeout) timeout.addEventListener("change", () => saveTimeout(timeout.value));
    paintTexts();
    refresh();
    return wrap;
  }

  if (global.MemoriaI18n && global.MemoriaI18n.addRefresh) {
    global.MemoriaI18n.addRefresh(paintTexts);
  }

  function boot() {
    if (!host()) return;
    mount();
  }

  if (global.document) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
    global.addEventListener("pywebviewready", boot);
  }

  global.MemoriaScriptSettings = { mount, refresh, render };
})(window);
