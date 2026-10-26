#!/usr/bin/env node
/* task-145 真机验收：链接点击「小窗优先」浮层
 *
 * 场景：
 *   S1 单链接点击 ⇒ 浮层单卡片（名称/解释/区域预览/拉到编辑区），不直接跳转、不开整页模态
 *   S2 Esc 关闭 ⇒ 浮层消失、aria-expanded=false
 *   S3 多目标链接 ⇒ 浮层 2 张卡片 +「全部打开」
 *   S4 点「拉到编辑区」⇒ 浮层消失 + 打开目标文件并定位 KP
 *   S5 「全部打开」⇒ 多标签能力保留（tabs>=2）且跳到首个目标
 *   S6 点外部 ⇒ 关闭
 *   S7 键盘：Enter = 拉到编辑区（预览模式）
 *   S8 Ctrl+点击 = 直接跳转（快速通道·待确认）⇒ 不出浮层
 *   S9 断链点击 ⇒ 仍走原「编辑链接」整页模态（不回归）
 *
 * 用法：node link-popover-probe.mjs --cdp http://127.0.0.1:9593 --kb <临时KB> --out <json>
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
  async _unwrap(p) {
    const r = await p;
    if (r && r.exceptionDetails) throw new Error("evalJS 异常: " + String((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text).slice(0, 240));
    return r && r.result ? r.result.value : undefined;
  }
  async evalJS(expr, { timeoutMs = 20000 } = {}) {
    const p = this.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
    if (!timeoutMs) return this._unwrap(p);
    const guard = new Promise((_, rej) => setTimeout(() => rej(new Error("evalJS 超时")), timeoutMs));
    return this._unwrap(Promise.race([p, guard]));
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
    try { cdp = await CDP.connect(t.webSocketDebuggerUrl); await cdp.waitFor('!!(window.MemoriaApp && window.state && typeof window.MemoriaApp.openFile === "function")', { timeout: 20000, label: "app" }); return { cdp, target: t }; }
    catch { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}

const READ = `(function(){
  var st=window.state||{};
  var pop=document.getElementById('link-popover');
  var cards=pop?[].slice.call(pop.querySelectorAll('.-link-pop-card')):[];
  var lm=document.getElementById('link-modal');
  return {
    currentPath: st.currentPath||null,
    activeKpId: st.activeKpId||null,
    viewMode: st.viewMode||null,
    popVisible: !!(pop && pop.offsetWidth > 0 && getComputedStyle(pop).visibility !== 'hidden'),
    popCards: cards.length,
    popCardTexts: cards.map(function(c){return {name:(c.querySelector('.-link-pop-name')||{}).textContent||'',
      desc:(c.querySelector('.-link-pop-desc')||{}).textContent||'',
      preview:((c.querySelector('.-link-pop-preview')||{}).textContent||'').slice(0,300),
      hasPull:!!c.querySelector('[data-link-pop-pull]'),
      pullText:(c.querySelector('[data-link-pop-pull]')||{}).textContent||''};}),
    hasAll: !!(pop && pop.querySelector('[data-link-pop-all]')),
    popRole: pop?pop.getAttribute('role'):null,
    menuitemCount: pop?pop.querySelectorAll('[role="menuitem"]').length:0,
    backdropVisible: [].slice.call(document.querySelectorAll('.-modal-backdrop')).some(function(b){return b.offsetParent!==null;}),
    linksBound: document.querySelectorAll('.memoria-link[data--bound="1"]').length,
    linksTotal: document.querySelectorAll('.memoria-link').length,
    hasContextMenuApi: !!window.MemoriaLinkContextMenu,
    allText: pop?((pop.querySelector('[data-link-pop-all]')||{}).textContent||''):'',
    modalVisible: !!(lm && !lm.classList.contains('hidden')),
    tabs: ((st.openTabs||[]).length),
    ariaExpanded: (function(){var l=document.querySelector('.memoria-link');return l?l.getAttribute('aria-expanded'):null;})()
  };
})()`;

/** 真实鼠标点击：按可视文本找 .memoria-link / 卡片内按钮，返回 rect 并点击 */
const CLICK_BY_TEXT = (selector, text, modifiers) => `(function(){
  var els=[].slice.call(document.querySelectorAll(${JSON.stringify(selector)}));
  var el=null;
  for(var i=0;i<els.length;i++){ if((els[i].textContent||'').indexOf(${JSON.stringify(text)})>=0){ el=els[i]; break; } }
  if(!el) return {ok:false};
  el.scrollIntoView({block:'center'});
  var r=el.getBoundingClientRect();
  return {ok:true, x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9593");
  const kb = String(args.kb || "");
  if (!kb) throw new Error("缺少 --kb");
  const OUTDIR = path.resolve(String(args.out || path.join(kb, "..", "link-popover-realapp.json")));
  const shotDir = path.join(path.dirname(OUTDIR), "link-popover-screens");
  fs.mkdirSync(shotDir, { recursive: true });

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp, target } = conn;
  const out = { startedAt: new Date().toISOString(), target: { id: target.id }, steps: {} };
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");

  async function shot(name) {
    const r = await cdp.send("Page.captureScreenshot", { format: "png" });
    const p = path.join(shotDir, name + ".png");
    fs.writeFileSync(p, Buffer.from(r.data, "base64"));
    return p;
  }
  async function clickText(selector, text, modifiers = 0) {
    const pos = await cdp.evalJS(CLICK_BY_TEXT(selector, text, modifiers));
    if (!pos || !pos.ok) throw new Error("未找到可点击元素: " + selector + " / " + text);
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: pos.x, y: pos.y });
    await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x: pos.x, y: pos.y, button: "left", clickCount: 1, modifiers });
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: pos.x, y: pos.y, button: "left", clickCount: 1, modifiers });
    return pos;
  }
  async function clickAt(x, y) {
    await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
  }
  async function openA() {
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode('split'); } catch(e){} return true; })()`);
    await cdp.waitFor('(window.state||{}).viewMode === "split"', { timeout: 15000, label: "split" });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/a.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/a.md" && !!window.state.doc', { timeout: 30000, label: "open a" });
    await cdp.waitFor('document.querySelectorAll(".memoria-link").length >= 3', { timeout: 20000, label: "links" });
    await sleep(400);
  }
  async function pressEscape() {
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  }

  // S1 单链接 ⇒ 浮层单卡片，不跳转
  await openA();
  out.steps.S1 = { click: await clickText(".memoria-link", "单目标") };
  await cdp.waitFor('!!document.getElementById("link-popover")', { timeout: 20000, label: "popover S1" });
  await sleep(900);   // 等二次 RPC 补齐 description/预览
  out.steps.S1.afterClick = await cdp.evalJS(READ);
  out.steps.S1.shot = await shot("S1-single-popover");

  // S2 Esc 关闭
  await pressEscape();
  await sleep(300);
  out.steps.S2 = { afterEsc: await cdp.evalJS(READ) };

  // S3 多目标 ⇒ 2 卡片 + 全部打开
  await openA();
  out.steps.S3 = { click: await clickText(".memoria-link", "多目标") };
  await cdp.waitFor('!!document.getElementById("link-popover")', { timeout: 20000, label: "popover S3" });
  await sleep(1100);
  out.steps.S3.afterClick = await cdp.evalJS(READ);
  out.steps.S3.shot = await shot("S3-multi-popover");

  // S4 拉到编辑区（第一张卡片按钮）
  out.steps.S4 = { click: await clickText("#link-popover [data-link-pop-pull]", "拉到编辑区") };
  await cdp.waitFor('!document.getElementById("link-popover")', { timeout: 20000, label: "popover closed S4" });
  await cdp.waitFor('window.state.currentPath === "docs/target.md"', { timeout: 30000, label: "jump target S4" });
  await sleep(700);
  out.steps.S4.afterPull = await cdp.evalJS(READ);
  out.steps.S4.shot = await shot("S4-after-pull");

  // S5 全部打开：多标签能力保留
  await openA();
  await clickText(".memoria-link", "多目标");
  await cdp.waitFor('!!document.getElementById("link-popover")', { timeout: 20000, label: "popover S5" });
  await sleep(500);
  out.steps.S5 = { clickAll: await clickText("#link-popover [data-link-pop-all]", "全部打开") };
  await cdp.waitFor('!document.getElementById("link-popover")', { timeout: 20000, label: "closed S5" });
  await cdp.waitFor('window.state.currentPath === "docs/target.md"', { timeout: 30000, label: "jump S5" });
  await sleep(600);
  out.steps.S5.afterAll = await cdp.evalJS(READ);

  // S6 点外部关闭
  await openA();
  await clickText(".memoria-link", "单目标");
  await cdp.waitFor('!!document.getElementById("link-popover")', { timeout: 20000, label: "popover S6" });
  await clickAt(6, 6);
  await sleep(300);
  out.steps.S6 = { afterOutside: await cdp.evalJS(READ) };

  // S7 键盘 Enter 触发当前项
  await openA();
  await clickText(".memoria-link", "单目标");
  await cdp.waitFor('!!document.getElementById("link-popover")', { timeout: 20000, label: "popover S7" });
  await sleep(300);
  await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: "\r", unmodifiedText: "\r" });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
  await cdp.waitFor('!document.getElementById("link-popover")', { timeout: 20000, label: "closed S7" });
  await cdp.waitFor('window.state.currentPath === "docs/target.md"', { timeout: 30000, label: "jump S7" });
  out.steps.S7 = { afterEnter: await cdp.evalJS(READ) };

  // S8 Ctrl+点击快速通道 ⇒ 不出浮层，直接跳
  await openA();
  out.steps.S8 = { click: await clickText(".memoria-link", "单目标", 2) };  // modifiers=2 ⇒ Ctrl
  await sleep(900);
  out.steps.S8.afterCtrlClick = await cdp.evalJS(READ);

  // S9 断链 ⇒ 原编辑链接模态（不回归）
  await openA();
  out.steps.S9 = { click: await clickText(".memoria-link.-link-broken", "ghost-kp") };
  await sleep(900);
  out.steps.S9.afterClick = await cdp.evalJS(READ);

  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(OUTDIR, JSON.stringify(out, null, 2), "utf8");
  for (const k of ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]) {
    const s = out.steps[k] || {};
    const snap = s.afterClick || s.afterEsc || s.afterPull || s.afterAll || s.afterOutside || s.afterEnter || s.afterCtrlClick || {};
    console.log("== " + k +
      " pop=" + snap.popVisible + " cards=" + snap.popCards + " all=" + snap.hasAll +
      " modal=" + snap.modalVisible + " path=" + snap.currentPath + " kp=" + snap.activeKpId +
      " tabs=" + snap.tabs + " aria=" + snap.ariaExpanded);
    if (snap.popCardTexts && snap.popCardTexts.length) console.log("   cards=" + JSON.stringify(snap.popCardTexts));
  }
  console.log("OUT=" + OUTDIR);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
