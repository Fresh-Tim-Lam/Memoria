#!/usr/bin/env node
/* task-170 验证：contentMinPx.def 单源收口。
 *
 * 断言（真机 WebView2，真实 app.js/display-settings.js/agent-panel.js）：
 *   A. display-settings 的 def 是唯一来源：改 CONTENT_MIN_RANGE.def（运行时/文件）⇒
 *      agent-panel.getContentMinPx() 与实际 dock 计算口径（getDockState.contentMinPx）随之变化。
 *   B. agent-panel 的兜底常量不再是第二事实源：只把兜底改大（运行 B）但 display-settings 在场时
 *      生效值仍取 def；只有 display-settings 缺席时才回退到兜底。
 *
 * 用法：node contentmin-def-probe.mjs --cdp http://127.0.0.1:9597 --out <json> --label A|B
 */
"use strict";
import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith("--")) { const k = t.slice(2); const nxt = argv[i + 1]; if (nxt && !nxt.startsWith("--")) { a[k] = nxt; i++; } else a[k] = true; }
    else a._.push(t);
  }
  return a;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(url, timeoutMs = 3000) {
  const ctrl = new AbortController(); const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try { return await (await fetch(url, { signal: ctrl.signal })).json(); } finally { clearTimeout(to); }
}
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._pending = new Map(); ws.addEventListener("message", (e) => this._on(e.data)); }
  static connect(url) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(url);
      const to = setTimeout(() => rej(new Error("CDP 超时")), 15000);
      ws.addEventListener("open", () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener("error", () => { clearTimeout(to); rej(new Error("CDP 失败")); });
    });
  }
  _on(data) {
    let m; try { m = JSON.parse(typeof data === "string" ? data : String(data)); } catch { return; }
    if (m.id == null) return; const p = this._pending.get(m.id); if (!p) return;
    this._pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => { const id = ++this._id; this._pending.set(id, { resolve, reject }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
  async evalJS(expr, { timeoutMs = 20000 } = {}) {
    const p = this.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
    const guard = new Promise((_, rej) => setTimeout(() => rej(new Error("evalJS 超时")), timeoutMs));
    const r = await Promise.race([p, guard]);
    if (r && r.exceptionDetails) throw new Error("evalJS 异常: " + String((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text).slice(0, 300));
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expr, { timeout = 30000, label = "" } = {}) {
    const t0 = Date.now();
    for (;;) { let v; try { v = await this.evalJS(expr); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error("等待超时 " + label); await sleep(120); }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}
async function connectAppPage(cdpBase) {
  const list = await httpJson(cdpBase.replace(/\/$/, "") + "/json/list");
  for (const t of (list || []).filter((x) => x && x.type === "page" && x.webSocketDebuggerUrl)) {
    let cdp = null;
    try {
      cdp = await CDP.connect(t.webSocketDebuggerUrl);
      await cdp.waitFor('!!(window.MemoriaApp && window.MemoriaDisplaySettings && window.MemoriaAgentPanel)', { timeout: 25000, label: "app/modules" });
      return { cdp, target: t };
    } catch { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}

const READ = `(function(){
  var ds=window.MemoriaDisplaySettings, ap=window.MemoriaAgentPanel;
  var dock = ap && typeof ap.getDockState==='function' ? ap.getDockState() : null;
  var s = null;
  try { s = ds && typeof ds.load==='function' ? ds.load() : null; } catch(e) {}
  return {
    hasDs: !!ds,
    hasAp: !!ap,
    def: ds && typeof ds.getContentMinDef==='function' ? ds.getContentMinDef() : null,
    rangeDef: ds && ds.CONTENT_MIN_RANGE ? ds.CONTENT_MIN_RANGE.def : null,
    range: ds && ds.CONTENT_MIN_RANGE ? {min: ds.CONTENT_MIN_RANGE.min, max: ds.CONTENT_MIN_RANGE.max} : null,
    effective: ap && typeof ap.getContentMinPx==='function' ? ap.getContentMinPx() : null,
    dockContentMin: dock ? dock.contentMinPx : null,
    dockAvailable: dock ? dock.availablePx : null,
    storedContentMin: s ? (s.contentMinPx === undefined ? null : s.contentMinPx) : null
  };
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9597");
  const label = String(args.label || "A");
  const OUT = path.resolve(String(args.out || "contentmin-def-probe.json"));
  const out = { label, startedAt: new Date().toISOString(), steps: {} };
  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp } = conn;
  await cdp.send("Page.enable"); await cdp.send("Runtime.enable");

  out.steps.baseline = await cdp.evalJS(READ);
  // 说明：DEFAULTS.contentMinPx 在模块加载时引用 def；"只改 def 即生效"的验证是【文件级】
  //   （改 display-settings.js 的 def 后重启 app，见 run A/B），不在运行时改 def 后期待快照变化。

  // 默认值层面：只有 display-settings 缺席时，才应该看到 agent-panel 的最后兜底
  out.steps.hideDs = await cdp.evalJS(`(function(){ window.__dsRef = window.MemoriaDisplaySettings; window.MemoriaDisplaySettings = undefined; return true; })()`);
  await sleep(120);
  out.steps.afterHideDs = await cdp.evalJS(READ);
  out.steps.restoreDs = await cdp.evalJS(`(function(){ window.MemoriaDisplaySettings = window.__dsRef; return true; })()`);
  await sleep(120);
  out.steps.afterRestore = await cdp.evalJS(READ);

  // 用户存储覆盖 def（getContentMinPx 应优先用户值；agent 应取用户值）
  out.steps.setStored = await cdp.evalJS(`(function(){
    try { window.MemoriaDisplaySettings.save({contentMinPx: 300}); return true; } catch(e) { return String(e); }
  })()`);
  await sleep(250);
  out.steps.afterStored = await cdp.evalJS(READ);
  out.steps.resetStored = await cdp.evalJS(`(function(){
    try { window.MemoriaDisplaySettings.save({contentMinPx: window.MemoriaDisplaySettings.CONTENT_MIN_RANGE.def}); return true; } catch(e) { return String(e); }
  })()`);

  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf8");
  console.log("OUT=" + OUT);
  for (const k of ["baseline", "afterHideDs", "afterRestore", "afterStored"]) {
    console.log(k, JSON.stringify(out.steps[k]));
  }
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
