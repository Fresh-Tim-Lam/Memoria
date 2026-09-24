/**
 * 能力插件面板（设置 → 「能力」页签）：列**本库**的能力插件 + 库级启停。
 *
 * 契约与口径：`docs/design/agent-plugin-design.md §1/§2`（声明面）、`dsh-agent-port.md §6.25`（契约接线）。
 * 数据**只来自后端网关** `agent_plugins` / `agent_plugin_set`（`services/agent/plugins.py`）——
 * 本模块不读任何文件、不拼任何路径，只把网关返回摊开给人看、把人的开关回传。
 *
 * 三条必须让用户看明白的事（都写进界面文案，避免被当成"全局开关"或"点了没反应"）：
 *   1. **开关是「库级」的**：落在 `<库>/.memoria/agent/capabilities.json` 的 `enabled[]`，随库走；
 *   2. **关掉 = 该动作类在本库不可用**：写 op 会被拒（`capability_disabled`），且模型在
 *      `propose_write` 的描述里就能看到「本库已启用的能力动作」⇒ 不会瞎试；
 *   3. **清单本身来自内置声明**（`resources/agent-capabilities/**`，随版本分发、只读）——
 *      面板只能启停，不能在界面上新建/编辑声明（编辑属导入器，未做）。
 *
 * 依赖：应用门面 `window.MemoriaApp`（`call` / `T` / `esc`）；缺席时降级为"不可用"，不抛异常。
 * 挂载：由 `graph-settings.js` 的页签分发调用（与 `MemoriaDisplaySettings` 同款形状）。
 */
(function (global) {
  "use strict";

  const A = () => global.MemoriaApp || {};
  const T = (k) => (A().T ? A().T(k) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));

  /** 网关调用（`MemoriaApp.call(method, ...args)` → Promise） */
  function call(method, ...args) {
    const app = A();
    if (!app.call) return Promise.resolve({ status: "error", code: "no_bridge", message: "桥不可用" });
    return Promise.resolve(app.call(method, ...args));
  }

  function sourceLabel(src) {
    const key = "settings.plugins.source." + String(src || "");
    const out = T(key);
    return out === key ? String(src || "") : out;
  }

  /** 该插件的**库级参数**（`config` 值位的第一例 = `web-fetch` 的 allow/deny 域名名单）。
   *
   *  没参数位的插件返回空串 ⇒ 面板与接线前逐字一致（`settings.plugins.param.<name>` 缺键时回落成参数名）。 */
  function configHtml(item) {
    const params = Array.isArray(item.params) ? item.params : [];
    if (!params.length) return "";
    const config = item.config && typeof item.config === "object" ? item.config : {};
    const fields = params
      .map((name) => {
        const value = Array.isArray(config[name]) ? config[name].join(", ") : "";
        const label = T("settings.plugins.param." + String(name));
        return `<label class="-plugins-cfg-field"><span>${esc(
          label === "settings.plugins.param." + String(name) ? String(name) : label
        )}</span><input type="text" spellcheck="false" data-plugin-config="${esc(item.id)}" data-param="${esc(
          name
        )}" value="${esc(value)}"></label>`;
      })
      .join("");
    return `<div class="-plugins-config"><p class="-plugins-k">${esc(
      T("settings.plugins.configLabel")
    )}</p>${fields}<p class="-plugins-cfg-hint">${esc(T("settings.plugins.configHint"))}</p></div>`;
  }

  function rowsHtml(state) {
    const plugins = Array.isArray(state.plugins) ? state.plugins : [];
    if (!plugins.length) {
      return `<p class="-plugins-empty">${esc(T("settings.plugins.empty"))}</p>`;
    }
    return plugins
      .map((item) => {
        const tools = Array.isArray(item.tools) ? item.tools : [];
        const read = Array.isArray(item.read) ? item.read : [];
        const write = Array.isArray(item.write) ? item.write : [];
        const approval = item.approval && typeof item.approval === "object" ? item.approval : {};
        const checked = item.enabled ? " checked" : "";
        return `<div class="-plugins-row" data-plugin-id="${esc(item.id)}">
          <label class="-plugins-switch">
            <input type="checkbox" data-plugin-toggle="${esc(item.id)}"${checked}
              aria-label="${esc(item.name || item.id)}">
            <span class="-plugins-name">${esc(item.name || item.id)}</span>
          </label>
          <span class="-plugins-id">${esc(item.id)}</span>
          <span class="-plugins-src">${esc(sourceLabel(item.source))}</span>
          <p class="-plugins-tools" title="${esc(tools.join("、"))}">
            <span class="-plugins-k">${esc(T("settings.plugins.toolsLabel"))}</span>${esc(tools.join("、")) || "—"}
          </p>
          <p class="-plugins-perms" title="${esc([read.join("、"), write.join("、")].join(" ｜ "))}">
            <span class="-plugins-k">${esc(T("settings.plugins.readLabel"))}</span>${esc(read.join("、")) || "—"}
            <span class="-plugins-k">${esc(T("settings.plugins.writeLabel"))}</span>${esc(write.join("、")) || "—"}
            <span class="-plugins-k">${esc(T("settings.plugins.approvalLabel"))}</span>${esc(
              "read=" + (approval.read || "—") + " / write=" + (approval.write || "—")
            )}
          </p>
          ${configHtml(item)}
        </div>`;
      })
      .join("");
  }

  function issuesHtml(state) {
    const warnings = Array.isArray(state.warnings) ? state.warnings : [];
    const errors = Array.isArray(state.errors) ? state.errors : [];
    let html = "";
    if (warnings.length) {
      html += `<div class="-plugins-warn"><p class="-plugins-warn-title">${esc(
        T("settings.plugins.warnTitle")
      )} · ${warnings.length}</p><ul>${warnings
        .map((w) => `<li>${esc((w && w.kind) || "")}：${esc((w && w.message) || "")}</li>`)
        .join("")}</ul></div>`;
    }
    if (errors.length) {
      html += `<div class="-plugins-err"><p class="-plugins-warn-title">${esc(
        T("settings.plugins.errTitle")
      )} · ${errors.length}</p><ul>${errors
        .map((e) => `<li>${esc((e && e.kind) || "")}：${esc((e && e.message) || "")}</li>`)
        .join("")}</ul></div>`;
    }
    return html;
  }

  function listHtml(state) {
    const enforced = state && state.enforced;
    const head = `<p class="-plugins-meta">${esc(T("settings.plugins.enforced"))}：${
      enforced ? esc(T("settings.plugins.enforcedOn")) : esc(T("settings.plugins.enforcedOff"))
    }</p>`;
    const registry = `<p class="-plugins-path" title="${esc(state.registry_path || "")}">${esc(
      T("settings.plugins.registry")
    )}：${esc(state.registry_path || "—")}</p>`;
    return head + rowsHtml(state || {}) + issuesHtml(state || {}) + registry;
  }

  function renderSettingsBody() {
    return `<div class="-plugins-panel">
      <p class="-plugins-hint">${esc(T("settings.plugins.hint"))}</p>
      <div class="-plugins-status" id="-plugins-status" role="status" aria-live="polite"></div>
      <div class="-plugins-list" id="-plugins-list">${esc(T("settings.plugins.loading"))}</div>
    </div>`;
  }

  function paint(root, state) {
    const list = root.querySelector("#-plugins-list");
    if (!list) return;
    if (!state || state.status !== "ok") {
      const message = (state && state.message) || T("settings.plugins.failed");
      const code = state && state.code === "no_kb" ? T("settings.plugins.noKb") : message;
      list.innerHTML = `<p class="-plugins-empty">${esc(code)}</p>`;
      return;
    }
    list.innerHTML = listHtml(state);
    bindToggles(root);
    bindConfigs(root, state);
  }

  /** 库级参数的就地保存（失焦 / 回车触发）：走 `agent_plugin_set(id, on, kb, config)`。
   *
   *  为什么"单键提交"：另一个键的值从**当前 state** 里带上 ⇒ 不会把同插件另一项清空；
   *  后端 `normalize_plugin_config()` 会归一 + 对坏写法**拒写**并回 `bad_plugin_config`（原样显示）。 */
  function bindConfigs(root, state) {
    const inputs = root.querySelectorAll("[data-plugin-config]");
    Array.prototype.forEach.call(inputs, (input) => {
      input.addEventListener("change", async () => {
        const id = String(input.getAttribute("data-plugin-config") || "");
        const name = String(input.getAttribute("data-param") || "");
        const row = (Array.isArray(state.plugins) ? state.plugins : []).find((item) => item && item.id === id) || {};
        const config = Object.assign({}, row.config || {});
        config[name] = String(input.value || "")
          .split(/[,;，；、\s]+/)
          .filter(Boolean);
        setStatus(root, T("settings.plugins.saving"));
        let res;
        try {
          res = await call("agent_plugin_set", id, !!row.enabled, null, config);
        } catch (err) {
          res = { status: "error", message: String((err && err.message) || err) };
        }
        if (!res || res.status !== "ok") {
          setStatus(root, (res && (res.message || res.code)) || T("settings.plugins.failed"));
          return;
        }
        paint(root, res);
        setStatus(root, T("settings.plugins.saved"));
      });
    });
  }

  function setStatus(root, text) {
    const box = root.querySelector("#-plugins-status");
    if (box) box.textContent = text || "";
  }

  function bindToggles(root) {
    root.querySelectorAll("[data-plugin-toggle]").forEach((box) => {
      box.addEventListener("change", async () => {
        const id = box.dataset.pluginToggle;
        const next = !!box.checked;
        box.disabled = true;
        setStatus(root, T("settings.plugins.saving"));
        let res = null;
        try {
          res = await call("agent_plugin_set", id, next);
        } catch (err) {
          res = { status: "error", message: String((err && err.message) || err) };
        }
        if (!res || res.status !== "ok") {
          setStatus(root, ((res && res.message) || T("settings.plugins.failed")) + " (" + id + ")");
          box.checked = !next; // 回滚勾选：没落盘就别显示成"已改"
          box.disabled = false;
          return;
        }
        setStatus(root, (next ? T("settings.plugins.savedOn") : T("settings.plugins.savedOff")) + " · " + id);
        paint(root, res); // 网关回的是**写后重算**的能力面 ⇒ 直接用，省一次往返
      });
    });
  }

  async function bindSettingsForm(root) {
    if (!root) return;
    setStatus(root, "");
    let state = null;
    try {
      state = await call("agent_plugins", null);
    } catch (err) {
      state = { status: "error", message: String((err && err.message) || err) };
    }
    paint(root, state);
  }

  global.MemoriaPluginSettings = { renderSettingsBody, bindSettingsForm };
})(window);
