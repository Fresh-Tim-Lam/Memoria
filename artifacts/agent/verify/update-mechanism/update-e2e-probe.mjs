#!/usr/bin/env node
/* task-180 真机验证：设置 → 更新页签（检查 / 下载 / 取消 / 手动说明 / 出网关闭零请求 / 隐私请求头）。
 *
 * 用法：
 *   node update-e2e-probe.mjs --cdp http://127.0.0.1:9600 --out <json> \
 *        --requests <mock-server-requests.jsonl> [--offline] [--app-config <config dir>]
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
    if (r && r.exceptionDetails) throw new Error("evalJS 异常: " + String((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text).slice(0, 400));
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expr, { timeout = 30000, label = "" } = {}) {
    const t0 = Date.now();
    for (;;) { let v; try { v = await this.evalJS(expr); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error("等待超时 " + label); await sleep(150); }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}
async function connectAppPage(cdpBase) {
  const list = await httpJson(cdpBase.replace(/\/$/, "") + "/json/list");
  for (const t of (list || []).filter((x) => x && x.type === "page" && x.webSocketDebuggerUrl)) {
    let cdp = null;
    try {
      cdp = await CDP.connect(t.webSocketDebuggerUrl);
      await cdp.waitFor('!!(window.MemoriaApp && window.MemoriaBridge)', { timeout: 25000, label: "app" });
      return { cdp, target: t };
    } catch { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}
function readLog(file) {
  try {
    return fs.readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
  } catch { return []; }
}

const bodyText = `(function(){ var m=document.querySelector('#settings-body'); return m ? m.innerText : ''; })()`;
const settingsOpen = `(function(){ var m=document.getElementById('settings-modal'); return !!m && !m.classList.contains('hidden'); })()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9600");
  const OUT = path.resolve(String(args.out || "update-e2e.json"));
  const shotDir = path.join(path.dirname(OUT), "shots");
  fs.mkdirSync(shotDir, { recursive: true });
  const requestsPath = String(args.requests || "");
  const downloadsDir = String(args.downloads || "");
  const offline = !!args.offline;
  const out = { offline, startedAt: new Date().toISOString(), steps: {} };

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp } = conn;
  await cdp.send("Page.enable"); await cdp.send("Runtime.enable");
  async function shot(name) {
    const r = await cdp.send("Page.captureScreenshot", { format: "png" });
    const p = path.join(shotDir, (offline ? "offline-" : "normal-") + name + ".png");
    fs.writeFileSync(p, Buffer.from(r.data, "base64"));
    return p;
  }
  function logCount() { return readLog(requestsPath).length; }

  // 启动后延迟自动检查：先等过 6s 调度点（正常模式应看到 ≥1 个 /latest 请求）
  await sleep(8000);
  out.steps.requestsBeforeManual = logCount();
  out.steps.autoCheckEvidence = readLog(requestsPath).filter((e) => e.path === "/latest").length;

  await cdp.evalJS(`(function(){ document.getElementById('btn-settings')?.click(); return true; })()`);
  await cdp.waitFor(settingsOpen, { timeout: 10000, label: "settings open" });
  await cdp.evalJS(`(function(){ var b=document.querySelector('[data-settings-tab="update"]'); if(!b) return false; b.click(); return true; })()`);
  await cdp.waitFor(`!!document.querySelector('#settings-body [id="update-check"], #settings-body .-update-card')`, { timeout: 15000, label: "update tab" });
  await sleep(800);
  out.steps.bodyInitial = await cdp.evalJS(bodyText);
  out.steps.shotInitial = await shot("update-tab");
  out.steps.forbiddenWords = ["防篡改", "已签名", "安全"].filter((w) => out.steps.bodyInitial.includes(w));

  if (offline) {
    out.steps.offlineUI = {
      hasOfflineNote: out.steps.bodyInitial.includes("出网") && out.steps.bodyInitial.includes("关闭"),
      checkDisabled: await cdp.evalJS('!!document.querySelector("#update-check") && document.querySelector("#update-check").disabled'),
    };
    out.steps.requestsAfterManualAttempt = logCount();
    out.steps.requestLogs = readLog(requestsPath);
    out.steps.shotOffline = await shot("offline");
    cdp.close();
    out.finishedAt = new Date().toISOString();
    fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf8");
    console.log("OUT=" + OUT);
    console.log("offlineUI=" + JSON.stringify(out.steps.offlineUI) + " requests=" + out.steps.requestsAfterManualAttempt);
    return 0;
  }

  // 手动检查
  await cdp.evalJS(`document.querySelector('#update-check')?.click()`);
  await cdp.waitFor(`(function(){ var t=document.querySelector('#settings-body')?.innerText||''; return t.indexOf('0.4.10')>=0 && (t.indexOf('安装包')>=0 || t.indexOf('已是最新')>=0); })()`, { timeout: 20000, label: "check result" });
  await sleep(500);
  out.steps.bodyChecked = await cdp.evalJS(bodyText);
  out.steps.shotChecked = await shot("checked");

  // 显式选 full（验证体积警告），取消下载
  const fullClicked = await cdp.evalJS(`(function(){
    var rows=[].slice.call(document.querySelectorAll('[data-update-asset-row]'));
    for (var i=0;i<rows.length;i++){ if(rows[i].textContent.indexOf('full')>=0){ var r=rows[i].querySelector('input'); if(r){ r.click(); return true; } } }
    return false;
  })()`);
  out.steps.fullSelected = fullClicked;
  out.steps.fullWarn = await cdp.evalJS(`(function(){ var el=document.querySelector('#update-asset-warn'); return el?el.textContent:''; })()`);
  await cdp.evalJS(`document.querySelector('#update-download')?.click()`);
  await sleep(1200);
  out.steps.downloadingUI = await cdp.evalJS(`(function(){
    var b=document.querySelector('#settings-body');
    return { text:(b?b.innerText:''), progress:(document.querySelector('#update-progress-text')||{}).textContent||'',
             hasCancel:!!document.querySelector('#update-cancel') };
  })()`);
  await cdp.evalJS(`document.querySelector('#update-cancel')?.click()`);
  await cdp.waitFor(`(function(){ var t=document.querySelector('#settings-body')?.innerText||''; return t.indexOf('已取消下载')>=0; })()`, { timeout: 12000, label: "cancel" });
  out.steps.cancelUI = {
    text: await cdp.evalJS(`(function(){ var t=document.querySelector('#settings-body')?.innerText||''; return t.indexOf('已取消下载')>=0; })()`),
    files: (() => { try { return fs.readdirSync(downloadsDir); } catch (e) { return [String(e)]; } })(),
  };

  // 选 lite 并下载到完成
  const liteClicked = await cdp.evalJS(`(function(){
    var rows=[].slice.call(document.querySelectorAll('[data-update-asset-row]'));
    for (var i=0;i<rows.length;i++){ if(rows[i].textContent.indexOf('lite')>=0){ var r=rows[i].querySelector('input'); if(r){ r.click(); return true; } } }
    return false;
  })()`);
  out.steps.liteSelected = liteClicked;
  await cdp.evalJS(`document.querySelector('#update-download')?.click()`);
  await cdp.waitFor(`(function(){ return !!document.querySelector('#update-open-folder') || (document.querySelector('#settings-body')?.innerText||'').indexOf('下载失败')>=0; })()`, { timeout: 40000, label: "download done" });
  await sleep(500);
  out.steps.bodyDone = await cdp.evalJS(bodyText);
  await cdp.evalJS(`(function(){ var b=document.querySelector('#settings-body'); if(b) b.scrollTop=b.scrollHeight; return true; })()`);
  await sleep(300);
  out.steps.shotDone = await shot("downloaded-bottom");
  out.steps.updateState = await cdp.evalJS(`(function(){ try { var s=window.MemoriaUpdateSettings._state; return {jobId:s.jobId, done:s.done, verify:s.verify}; } catch(e){ return String(e); } })()`);
  out.steps.done = {
    downloaded: out.steps.bodyDone.includes("下载完成"),
    failed: out.steps.bodyDone.includes("下载失败"),
    manifestVerified: out.steps.bodyDone.includes("已校验包结构与完整性（不含数字签名）"),
    zipOnly: out.steps.bodyDone.includes("发布包内没有完整性清单"),
    steps: {
      close: out.steps.bodyDone.includes("关闭 Memoria 进程"),
      appFolder: out.steps.bodyDone.includes("只替换应用文件夹"),
      config: out.steps.bodyDone.includes("配置在") && out.steps.bodyDone.includes("config"),
      liteHf: out.steps.bodyDone.includes("hf/"),
      noAuto: out.steps.bodyDone.includes("不会自动替换"),
    },
    savedPath: await cdp.evalJS(`(function(){ var m=(document.querySelector('#settings-body')?.innerText||'').match(/保存到\\s*\\n?([^\\n]+)/); return m?m[1].trim():''; })()`),
  };

  // 隐私：请求日志里只允许 GET、无 cookie/auth；路径只应命中 /latest 和 /asset/
  const logs = readLog(requestsPath);
  out.steps.requestLogs = logs;
  out.steps.privacy = {
    count: logs.length,
    allGet: logs.every((e) => e.method === "GET"),
    noCookies: logs.every((e) => !e.has_cookie),
    noAuth: logs.every((e) => !e.has_auth),
    paths: [...new Set(logs.map((e) => e.path))],
    headerNames: [...new Set(logs.flatMap((e) => e.header_names || []))].sort(),
    autoBeforeManual: logs.filter((e) => e.path === "/latest").length,
  };

  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf8");
  console.log("OUT=" + OUT);
  console.log("autoRequestBeforeManual=" + out.steps.autoCheckEvidence);
  console.log("forbiddenWords=" + JSON.stringify(out.steps.forbiddenWords));
  console.log("done=" + JSON.stringify(out.steps.done));
  console.log("privacy=" + JSON.stringify(out.steps.privacy));
  console.log("cancel=" + JSON.stringify(out.steps.cancelUI));
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
