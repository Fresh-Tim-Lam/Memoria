/**
 * 联网「域名名单」设置（人 2026-09-24 选定：N 线插件化的第一片 —— 域名单；设计见
 * `docs/design/agent-capabilities.md §3.3`）。
 *
 * **它做什么**：在设置 →「Agent」页的端点配置里追加两行输入框（允许抓取的域 / 禁止抓取的域），
 * 并**现场回显归一化结果**——用户写 `*.example.com`、`https://example.com/docs`、`example.com:8443`
 * 这类写法都会被归一成裸域；写错的项被忽略，这里直接告诉你"忽略了几处"，不让它变成
 * "看起来配了其实没配"。
 *
 * **只消费两条 RPC**：`agent_net_domains`（读现状 + 归一化结果）、`agent_save_config`（浅合并写两个键）。
 * 后端闸在 `services/agent/web.py::WebClient._assert_domain()`（**每跳**校验，被拒 `WEB_BLOCKED_DOMAIN`）；
 * `web_search` 的结果里也会给"抓不了"的来源加一行提示，省掉"试抓→被拒→再试"的 token。
 *
 * **零依赖、零侵入**：只用应用门面 `window.MemoriaApp`（`call` / `T` / `esc` / `showFlashInfo` /
 * `showFlashError`）；DOM 由本模块自建后**追加**进 `#agent-settings`（`index.html` 一行未改
 * ⇒ 既有 `index.html:<行>` 锚点零漂移），并注册 `MemoriaI18n.addRefresh()` 跟随语言切换。
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

  const ID = "-net-domains";

  function host() {
    const box = document.getElementById("agent-settings");
    return box && box.isConnected ? box : null;
  }

  function shell() {
    const box = document.getElementById(ID);
    return box && box.isConnected ? box : null;
  }

  function input(key) {
    return document.getElementById("-net-" + key);
  }

  /** 文案（语言切换后会再跑一次）。 */
  function paintTexts() {
    const box = shell();
    if (!box) return;
    box.querySelector("[data-net='title']").textContent = T("settings.net.title");
    box.querySelector("[data-net='allow']").textContent = T("settings.net.allowLabel");
    box.querySelector("[data-net='deny']").textContent = T("settings.net.denyLabel");
    box.querySelector("[data-net='hint']").textContent = T("settings.net.hint");
    box.querySelector("[data-net='scope']").textContent = T("settings.net.scopeNote");
    const allow = input("allow");
    const deny = input("deny");
    if (allow) allow.setAttribute("placeholder", T("settings.net.allowPh"));
    if (deny) deny.setAttribute("placeholder", T("settings.net.denyPh"));
    paintParsed(state);
  }

  //: 最近一次读到的现状（`agent_net_domains` 的返回）。
  let state = { allow: "", deny: "", allow_rules: [], deny_rules: [], ignored: { allow: 0, deny: 0 } };

  /** 归一化回显：机器级规则 + **本库合并后真正生效的那一套** + 被忽略的写法计数。 */
  function paintParsed(data) {
    const box = shell();
    if (!box) return;
    const node = box.querySelector("[data-net='parsed']");
    if (!node) return;
    const allowRules = Array.isArray(data.allow_rules) ? data.allow_rules : [];
    const denyRules = Array.isArray(data.deny_rules) ? data.deny_rules : [];
    const merged = data.merged && typeof data.merged === "object" ? data.merged : {};
    const mergedAllow = Array.isArray(merged.allow) ? merged.allow : [];
    const mergedDeny = Array.isArray(merged.deny) ? merged.deny : [];
    const parts = [
      T("settings.net.parsedAllow", { list: allowRules.length ? allowRules.join("、") : T("settings.net.any") }),
      T("settings.net.parsedDeny", { list: denyRules.length ? denyRules.join("、") : T("settings.net.none") }),
    ];
    // 本库合并后（库级只能收紧 ⇒ 这里可能比上面更严，甚至变成"谁都抓不了"）
    parts.push(
      T("settings.net.merged", {
        allow: mergedAllow.length ? mergedAllow.join("、") : T("settings.net.any"),
        deny: mergedDeny.length ? mergedDeny.join("、") : T("settings.net.none"),
      })
    );
    const capability = data.capability && typeof data.capability === "object" ? data.capability : {};
    if (capability.fetch_enabled === false) parts.push(T("settings.net.capabilityOff"));
    const ignored = (Number(data.ignored && data.ignored.allow) || 0) + (Number(data.ignored && data.ignored.deny) || 0);
    if (ignored > 0) parts.push(T("settings.net.ignored", { n: ignored }));
    node.textContent = parts.join(" · ");
    node.classList.toggle("-net-parsed--bad", ignored > 0 || capability.fetch_enabled === false);
  }

  function render(data) {
    state = Object.assign({}, state, data || {});
    const allow = input("allow");
    const deny = input("deny");
    if (allow && document.activeElement !== allow) allow.value = String(state.allow || "");
    if (deny && document.activeElement !== deny) deny.value = String(state.deny || "");
    paintParsed(state);
  }

  async function refresh() {
    let res;
    try {
      res = await call("agent_net_domains");
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
      flash(T("settings.net.failed"), (res && (res.message || res.code)) || "");
      refresh(); // 回滚显示：以磁盘上的现状为准
      return;
    }
    const info = A().showFlashInfo;
    if (info) info(T("settings.net.saved"));
    refresh();
  }

  function mount() {
    const box = host();
    if (!box || shell()) return shell();
    const wrap = document.createElement("div");
    wrap.id = ID;
    wrap.className = "-net-domains";
    wrap.innerHTML =
      '<div class="-settings-section-head" data-net="title"></div>' +
      '<label class="-agent-field"><span data-net="allow"></span>' +
      '<input type="text" id="-net-allow" spellcheck="false" autocomplete="off"></label>' +
      '<label class="-agent-field"><span data-net="deny"></span>' +
      '<input type="text" id="-net-deny" spellcheck="false" autocomplete="off"></label>' +
      '<p class="-net-hint" data-net="hint"></p>' +
      '<p class="-net-parsed" data-net="parsed"></p>' +
      '<p class="-net-scope" data-net="scope"></p>';
    box.appendChild(wrap);
    const allow = input("allow");
    const deny = input("deny");
    // `change` = 失焦或回车后触发一次（不做按键级保存，避免半截域名被写进盘）
    if (allow) allow.addEventListener("change", () => save("fetch_allow_domains", allow.value));
    if (deny) deny.addEventListener("change", () => save("fetch_deny_domains", deny.value));
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

  global.MemoriaNetSettings = { mount, refresh, render };
})(window);
