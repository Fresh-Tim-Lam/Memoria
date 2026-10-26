#!/usr/bin/env node
/* task-161 真机验收：链接面板 v2（可拖动/折叠 + 默认预览可切源码 + 候选面板内切换）
 *
 * 场景：
 *   P1 单链接 ⇒ 可拖动面板：默认预览（渲染 HTML）、单文档区、路径·行范围、拉到编辑区；不直接跳转
 *   P2 切「源码」⇒ 原始 markdown 等宽只读；关闭再开 ⇒ 模式记住
 *   P3 多候选：面板内 ‹ 名称 2/2 › 切换同一文档区（不并列两个文档区）
 *   P4 拖动标题栏 ⇒ 位置变化；关掉再开 ⇒ 几何/模式持久化；ui-settings.json 里有 linkPanel
 *   P5 前端 reload（模拟重启）⇒ 从磁盘读回几何/模式
 *   P6 折叠 [−] ⇒ 只剩标题栏；[+] 展开
 *   P7 缩放右下角 ⇒ 尺寸变化并持久化
 *   P8 不回归：Ctrl+点击直跳不出面板 / Esc / 点外部 / 拉到编辑区 / 断链模态 / 焦点 trap
 *
 * 用法：node link-panel-v2-probe.mjs --cdp http://127.0.0.1:9594 --kb <临时KB> --config <临时config> --out <json>
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
  constructor(ws) { this.ws = ws; this._id = 0; this._pending = new Map(); this.events = []; ws.addEventListener("message", (e) => this._on(e.data)); }
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
    if (m.id == null) { if (m.method) this.events.push(m); return; } const p = this._pending.get(m.id); if (!p) return;
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
  var panel=document.getElementById('link-panel');
  var rect=panel?panel.getBoundingClientRect():null;
  var docEl=panel?panel.querySelector('[data-panel-doc]'):null;
  var titlebar=panel?panel.querySelector('.-link-panel-titlebar'):null;
  function visible(el){return !!(el && el.offsetWidth>0 && el.offsetHeight>0 && getComputedStyle(el).display!=='none');}
  return {
    currentPath: st.currentPath||null,
    activeKpId: st.activeKpId||null,
    panelVisible: visible(panel),
    collapsed: panel?panel.classList.contains('-collapsed'):null,
    rect: rect?{x:Math.round(rect.left),y:Math.round(rect.top),w:Math.round(rect.width),h:Math.round(rect.height)}:null,
    name: panel?((panel.querySelector('[data-panel-name]')||{}).textContent||''):'',
    counter: panel?((panel.querySelector('[data-panel-counter]')||{}).textContent||''):'',
    modeActive: (function(){var b=panel?panel.querySelector('[data-panel-mode].-active'):null;return b?b.dataset.panelMode:null;})(),
    docCount: panel?panel.querySelectorAll('[data-panel-doc]').length:0,
    previewHtml: docEl?docEl.innerHTML.slice(0,600):'',
    bodyVisible: visible(panel?panel.querySelector('.-link-panel-body'):null),
    statusVisible: visible(panel?panel.querySelector('.-link-panel-status'):null),
    meta: panel?((panel.querySelector('[data-panel-meta]')||{}).textContent||''):'',
    pullVisible: visible(panel?panel.querySelector('[data-panel-pull]'):null),
    navVisible: visible(panel?panel.querySelector('[data-panel-nav]'):null),
    openAllVisible: visible(panel?panel.querySelector('[data-panel-open-all]'):null),
    role: panel?panel.getAttribute('role'):null,
    backdropVisible: [].slice.call(document.querySelectorAll('.-modal-backdrop')).some(function(b){return b.offsetParent!==null;}),
    modalVisible: (function(){var m=document.getElementById('link-modal');return !!(m&&!m.classList.contains('hidden'));})(),
    ariaExpanded: (function(){var l=document.querySelector('.memoria-link');return l?l.getAttribute('aria-expanded'):null;})(),
    openTabs: (st.openTabs||[]).length,
    activeEl: document.activeElement?(document.activeElement.className||document.activeElement.tagName):null,
    titlebarFocused: titlebar?document.activeElement===titlebar:false,
    status: (document.getElementById('status-info')||{}).textContent||'',
    previewErr: window.__linkPanelPreviewErr || null,
    pinPressed: (function(){var b=document.querySelector('[data-panel-pin]');return b?b.getAttribute('aria-pressed'):null;})(),
    pinFill: (function(){var b=document.querySelector('[data-panel-pin] .-pin-base');return b?getComputedStyle(b).fill:null;})(),
    panelCount: document.querySelectorAll('#link-panel').length,
    listCount: document.querySelectorAll('[data-panel-list] [data-panel-row]').length,
    listRows: (function(){
      var rows=[].slice.call(document.querySelectorAll('[data-panel-list] [data-panel-row]'));
      return rows.map(function(r){
        return {
          badge: (r.querySelector('.-link-panel-badge')||{}).textContent||'',
          name: (r.querySelector('.-link-panel-row-name')||{}).textContent||'',
          desc: (r.querySelector('.-link-panel-row-desc')||{}).textContent||'',
          tags: [].slice.call(r.querySelectorAll('.-link-panel-tag')).map(function(x){return x.textContent;}),
          selected: r.getAttribute('aria-selected')
        };
      });
    })(),
    rpcFiles: (window.state && window.state.linkPanel && window.state.linkPanel.rpcFiles) || null,
    countLabel: (function(){var e=document.querySelector('.-link-panel-count-label');return e?e.textContent:null;})(),
    metaKb: (function(){var e=document.querySelector('[data-panel-meta]');return e?e.textContent:null;})()
  };
})()`;

const CLICK_BY_TEXT = (selector, text) => `(function(){
  var els=[].slice.call(document.querySelectorAll(${JSON.stringify(selector)}));
  for(var i=0;i<els.length;i++){ if((els[i].textContent||'').indexOf(${JSON.stringify(text)})>=0){
    els[i].scrollIntoView({block:'center'}); var r=els[i].getBoundingClientRect();
    return {ok:true,x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};
  }}
  return {ok:false};
})()`;

/** 面板内元素中心点 */
const RECT_OF = (selector) => `(function(){
  var el=document.querySelector(${JSON.stringify(selector)});
  if(!el) return {ok:false};
  el.scrollIntoView({block:'nearest',inline:'nearest'});
  var r=el.getBoundingClientRect();
  return {ok:true,x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2),
          left:Math.round(r.left),top:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)};
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9594");
  const kb = String(args.kb || "");
  const cfgDir = String(args.config || "");
  if (!kb) throw new Error("缺少 --kb");
  const settingsPath = cfgDir ? path.join(cfgDir, "ui-settings.json") : "";
  const OUTDIR = path.resolve(String(args.out || path.join(kb, "..", "link-panel-v2-realapp.json")));
  const shotDir = path.join(path.dirname(OUTDIR), "link-panel-v2-screens");
  globalThis.__probeOutPath = OUTDIR;
  fs.mkdirSync(shotDir, { recursive: true });
  const out = { startedAt: new Date().toISOString(), steps: {} };
  globalThis.__probeOut = out;

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  let { cdp, target } = conn;
  out.target = { id: target.id };
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");

  async function shot(name) {
    const r = await cdp.send("Page.captureScreenshot", { format: "png" });
    const p = path.join(shotDir, name + ".png");
    fs.writeFileSync(p, Buffer.from(r.data, "base64"));
    return p;
  }
  async function clickAt(x, y, modifiers = 0) {
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1, modifiers });
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1, modifiers });
  }
  async function clickText(selector, text, modifiers = 0) {
    const pos = await cdp.evalJS(CLICK_BY_TEXT(selector, text));
    if (!pos || !pos.ok) throw new Error("未找到可点击元素: " + selector + " / " + text);
    await clickAt(pos.x, pos.y, modifiers);
    return pos;
  }
  async function clickRect(selector) {
    const pos = await cdp.evalJS(RECT_OF(selector));
    if (!pos || !pos.ok) throw new Error("未找到元素: " + selector);
    await clickAt(pos.x, pos.y);
    return pos;
  }
  async function drag(x0, y0, x1, y1) {
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: x0, y: y0 });
    await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x: x0, y: y0, button: "left", buttons: 1, clickCount: 1 });
    for (let i = 1; i <= 6; i++) {
      await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: Math.round(x0 + (x1 - x0) * i / 6), y: Math.round(y0 + (y1 - y0) * i / 6), button: "left", buttons: 1 });
      await sleep(30);
    }
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: x1, y: y1, button: "left", clickCount: 1 });
    await sleep(250);
  }
  async function openA() {
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode('split'); } catch(e){} return true; })()`);
    await cdp.waitFor('(window.state||{}).viewMode === "split"', { timeout: 15000, label: "split" });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/a.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/a.md" && !!window.state.doc', { timeout: 30000, label: "open a" });
    await cdp.waitFor('document.querySelectorAll(".memoria-link").length >= 3', { timeout: 20000, label: "links" });
    await sleep(400);
  }
  function readSettings() {
    if (!settingsPath || !fs.existsSync(settingsPath)) return null;
    try { return JSON.parse(fs.readFileSync(settingsPath, "utf8")); } catch (_) { return null; }
  }
  async function waitPanel(tag) {
    const t0 = Date.now();
    for (;;) {
      let v = false;
      try { v = await cdp.evalJS('!!document.getElementById("link-panel")'); }
      catch (e) { console.log("waitPanel eval err:", String(e && e.message ? e.message : e).slice(0, 300)); }
      if (v) { await sleep(400); return; }
      if (Date.now() - t0 > 15000) { console.log("waitPanel TIMEOUT tag=" + (tag||""), JSON.stringify(await cdp.evalJS(READ)).slice(0,800)); throw new Error("等待超时 panel " + (tag||"")); }
      await sleep(150);
    }
  }

  // P1 单链接 ⇒ 可拖动面板默认预览
  await openA();
  out.steps.P1 = { click: await clickText(".memoria-link", "单目标") };
  out.steps.P1.timeline = [];
  for (let i = 0; i < 20; i++) {
    await sleep(200);
    const st = await cdp.evalJS('({has:!!document.getElementById("link-panel"), stacks:(window.__linkPanelCloseStacks||[]).slice(-3)})');
    out.steps.P1.timeline.push({ t: (i + 1) * 200, has: st.has, stacks: st.stacks });
    if (!st.has) break;
  }
  console.log("P1TIMELINE", JSON.stringify(out.steps.P1.timeline).slice(0, 4000));
  await sleep(200);
  out.steps.P1.early = await cdp.evalJS(READ);
  out.steps.P1.events = cdp.events.filter((e) => /exception|console/i.test(e.method)).slice(-20);
  console.log("P1DEBUG", JSON.stringify(out.steps.P1.early));
  console.log("P1EVENTS", JSON.stringify(out.steps.P1.events).slice(0, 3000));
  await waitPanel("P1");
  await sleep(700);
  out.steps.P1.after = await cdp.evalJS(READ);
  out.steps.P1.events = cdp.events.filter((e) => /exception|console/i.test(e.method)).slice(-20);
  out.steps.P1.shot = await shot("P1-single-preview");

  // P2 切源码；关闭再开 ⇒ 模式记住
  out.steps.P2 = { clickSource: await clickRect("[data-panel-mode='source']") };
  await sleep(500);
  out.steps.P2.afterSource = await cdp.evalJS(READ);
  console.log("P2 source ok");
  out.steps.P2.shot = await shot("P2-source-mode");
  await clickRect("[data-panel-close]");
  await sleep(400);
  console.log("P2 closed; reopen");
  await openA();
  await clickText(".memoria-link", "单目标");
  await sleep(1200);
  console.log("P2 reopened state", JSON.stringify(await cdp.evalJS(READ)).slice(0,600));
  await waitPanel("P2reopen");
  out.steps.P2.afterReopen = await cdp.evalJS(READ);

  // P3 多候选：面板内切换（同一文档区）
  await clickRect("[data-panel-close]");
  await sleep(300);
  await openA();
  out.steps.P3 = { click: await clickText(".memoria-link", "多目标") };
  await waitPanel("P3");
  await sleep(1200);
  out.steps.P3.beforeSwitch = await cdp.evalJS(READ);
  out.steps.P3.clickRow1 = await clickRect('[data-panel-row="1"]');
  await sleep(900);
  out.steps.P3.afterSwitch = await cdp.evalJS(READ);
  out.steps.P3.shot = await shot("P3-candidate-list");
  // 纯文件引用（第四行：plain-note）
  out.steps.P3.clickRef = await clickRect('[data-panel-row="3"]');
  await sleep(900);
  out.steps.P3.afterReference = await cdp.evalJS(READ);
  out.steps.P3.refShot = await shot("P3-pure-reference-selected");
  // 区域缺失（第五行：norang）
  out.steps.P3.clickMissing = await clickRect('[data-panel-row="4"]');
  await sleep(900);
  out.steps.P3.afterMissing = await cdp.evalJS(READ);

  // P4 拖动 + 关闭重开 ⇒ 几何持久化 + ui-settings 键
  const before = out.steps.P3.afterSwitch.rect;
  out.steps.P4 = { beforeDrag: before };
  await drag(before.x + 120, before.y + 16, before.x + 220, before.y + 96);
  out.steps.P4.afterDrag = await cdp.evalJS(READ);
  if (out.steps.P4.afterDrag.rect && out.steps.P4.afterDrag.rect.x === before.x) {
    // WebView2 下 CDP 合成鼠标不产生 pointer 事件 ⇒ 用真实 PointerEvent 序列验证拖动处理链
    out.steps.P4.via = "synthetic-pointer";
    out.steps.P4.synthetic = await cdp.evalJS(`(function(){
      var tb=document.querySelector('.-link-panel-titlebar');
      var panel=document.getElementById('link-panel');
      var b=panel.getBoundingClientRect();
      function pe(type,x,y){return new PointerEvent(type,{bubbles:true,cancelable:true,button:0,buttons:1,clientX:x,clientY:y,pointerId:1});}
      tb.dispatchEvent(pe('pointerdown',${before.x + 120},${before.y + 16}));
      window.dispatchEvent(pe('pointermove',${before.x + 220},${before.y + 96}));
      window.dispatchEvent(pe('pointerup',${before.x + 220},${before.y + 96}));
      var a=panel.getBoundingClientRect();
      return {before:{x:Math.round(b.left),y:Math.round(b.top)},after:{x:Math.round(a.left),y:Math.round(a.top)}};
    })()`);
    await sleep(350);
    out.steps.P4.afterDrag = await cdp.evalJS(READ);
  }
  out.steps.P4.shot = await shot("P4-dragged");
  await clickRect("[data-panel-close]");
  await sleep(400);
  await openA();
  await clickText(".memoria-link", "单目标");
  await waitPanel("P4reopen");
  out.steps.P4.afterReopen = await cdp.evalJS(READ);
  out.steps.P4.settings = readSettings();

  // P5 前端 reload（模拟重启）⇒ 从磁盘读回几何/模式
  await cdp.send("Page.reload", { ignoreCache: false });
  await sleep(1500);
  try { await cdp.waitFor('!!(window.MemoriaApp && window.state)', { timeout: 30000, label: "reload app" }); } catch (_) { await sleep(2000); }
  await sleep(1200);
  await openA();
  await clickText(".memoria-link", "单目标");
  await waitPanel("P5reload");
  out.steps.P5 = { afterReload: await cdp.evalJS(READ), settings: readSettings() };

  // P6 折叠 / 展开
  await clickRect("[data-panel-collapse]");
  await sleep(400);
  out.steps.P6 = { collapsed: await cdp.evalJS(READ) };
  out.steps.P6.shot = await shot("P6-collapsed");
  await clickRect("[data-panel-collapse]");
  await sleep(400);
  out.steps.P6.expanded = await cdp.evalJS(READ);

  // P7 右下角缩放
  const r7 = out.steps.P6.expanded.rect;
  out.steps.P7 = { before: r7 };
  await drag(r7.x + r7.w - 4, r7.y + r7.h - 4, r7.x + r7.w + 56, r7.y + r7.h + 40);
  out.steps.P7.afterResize = await cdp.evalJS(READ);
  await clickRect("[data-panel-close]");
  await sleep(400);
  out.steps.P7.settings = readSettings();

  // P8 不回归：Esc / 点外部 / Ctrl+点击 / 拉到编辑区 / 断链 / focus trap
  await openA();
  await clickText(".memoria-link", "单目标");
  await waitPanel("P8esc");
  await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  await sleep(300);
  out.steps.P8 = { afterEsc: await cdp.evalJS(READ) };

  await openA();
  await clickText(".memoria-link", "单目标");
  await waitPanel("P8outside");
  await clickAt(6, 6);
  await sleep(300);
  out.steps.P8.afterOutside = await cdp.evalJS(READ);

  await openA();
  out.steps.P8.ctrlClick = await clickText(".memoria-link", "单目标", 2);
  await sleep(900);
  out.steps.P8.afterCtrlClick = await cdp.evalJS(READ);

  await openA();
  await clickText(".memoria-link", "单目标");
  await waitPanel("P8pull");
  await cdp.waitFor('!!document.querySelector("[data-panel-pull]")', { timeout: 15000, label: "pull" });
  out.steps.P8.clickPull = await clickRect("[data-panel-pull]");
  await cdp.waitFor('!document.getElementById("link-panel")', { timeout: 20000, label: "closed P8 pull" });
  await cdp.waitFor('window.state.currentPath === "docs/target.md"', { timeout: 30000, label: "jump P8" });
  out.steps.P8.afterPull = await cdp.evalJS(READ);

  await openA();
  out.steps.P8.broken = await clickText(".memoria-link.-link-broken", "ghost-kp");
  await sleep(900);
  out.steps.P8.afterBroken = await cdp.evalJS(READ);

  // focus trap：面板打开后连按 Tab，焦点应仍在面板内
  // 先关掉 P8 断链打开的编辑链接模态
  try { await clickRect("#link-close"); } catch (_) {}
  await sleep(400);
  await openA();
  await clickText(".memoria-link", "多目标");
  await waitPanel("P8tabs");
  for (let i = 0; i < 6; i++) {
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9 });
    await sleep(60);
  }
  out.steps.P8.afterTabs = await cdp.evalJS(READ);

  // ── P9 钉住：点外部/焦点离开不关闭；Esc 仍可关 ─────────────────────────────
  await openA();
  await clickText(".memoria-link", "单目标");
  await waitPanel("P9");
  await sleep(500);
  out.steps.P9 = { initial: await cdp.evalJS(READ) };
  await out.steps.P9.initial.pinPressed;
  // 2x 图标截图（未钉住）
  try {
    const r9 = out.steps.P9.initial.rect;
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 2, mobile: false });
    await sleep(300);
    const capU = await cdp.send("Page.captureScreenshot", { format: "png", clip: { x: r9.x, y: r9.y, width: r9.w, height: 40, scale: 1 } });
    fs.writeFileSync(path.join(shotDir, "P9-pin-icon-unpinned-2x.png"), Buffer.from(capU.data, "base64"));
    await cdp.send("Emulation.clearDeviceMetricsOverride");
    await sleep(300);
  } catch (_) { /* 截图失败不影响断言 */ }
  out.steps.P9.clickPin = await clickRect("[data-panel-pin]");
  await sleep(400);
  out.steps.P9.afterPin = await cdp.evalJS(READ);
  try {
    const r9b = out.steps.P9.afterPin.rect;
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 2, mobile: false });
    await sleep(300);
    const capP = await cdp.send("Page.captureScreenshot", { format: "png", clip: { x: r9b.x, y: r9b.y, width: r9b.w, height: 40, scale: 1 } });
    fs.writeFileSync(path.join(shotDir, "P9-pin-icon-pinned-2x.png"), Buffer.from(capP.data, "base64"));
    await cdp.send("Emulation.clearDeviceMetricsOverride");
    await sleep(300);
  } catch (_) { /* noop */ }
  await clickAt(6, 6);
  await sleep(300);
  out.steps.P9.afterOutside = await cdp.evalJS(READ);
  await clickAt(300, 430);   // 主界面编辑区交互
  await sleep(300);
  out.steps.P9.afterEditorClick = await cdp.evalJS(READ);
  out.steps.P9.shot = await shot("P9-pinned-after-outside");
  await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  await sleep(300);
  out.steps.P9.afterEsc = await cdp.evalJS(READ);

  // ── P10 pinned 持久化 + 点另一个链接复用同一面板（不新开/不重定位）──────────
  await openA();
  await clickText(".memoria-link", "单目标");
  await waitPanel("P10");
  await sleep(500);
  out.steps.P10 = { reopened: await cdp.evalJS(READ) };
  const rectBefore = out.steps.P10.reopened.rect;
  const pinPressedBefore = out.steps.P10.reopened.pinPressed;
  await clickText(".memoria-link", "多目标");
  await sleep(1200);
  out.steps.P10.afterSwitchLink = await cdp.evalJS(READ);
  out.steps.P10.sameRect = !!(out.steps.P10.afterSwitchLink.rect && rectBefore &&
    out.steps.P10.afterSwitchLink.rect.x === rectBefore.x && out.steps.P10.afterSwitchLink.rect.y === rectBefore.y);
  out.steps.P10.pinStillPressed = pinPressedBefore === "true" && out.steps.P10.afterSwitchLink.pinPressed === "true";
  out.steps.P10.samePanel = out.steps.P10.afterSwitchLink.panelCount === 1 && out.steps.P10.afterSwitchLink.listCount === 5;
  out.steps.P10.shot = await shot("P10-pinned-switch-link");

  // ── P11 钉住态 × / Esc 两个逃生口都能关 ─────────────────────────────────────
  await clickRect("[data-panel-close]");
  await sleep(400);
  out.steps.P11 = { afterClose: await cdp.evalJS(READ) };
  await clickText(".memoria-link", "单目标");
  await waitPanel("P11");
  await sleep(400);
  out.steps.P11.reopened = await cdp.evalJS(READ);
  await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  await sleep(300);
  out.steps.P11.afterEsc = await cdp.evalJS(READ);

  cdp.close();
  out.finishedAt = new Date().toISOString();
  globalThis.__probeOutPath = OUTDIR;
  fs.writeFileSync(OUTDIR, JSON.stringify(out, null, 2), "utf8");
  for (const k of ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11"]) {
    const s = out.steps[k] || {};
    console.log("== " + k + " " + JSON.stringify(Object.fromEntries(Object.entries(s).filter(([kk]) => !/shot$/.test(kk)))));
  }
  console.log("OUT=" + OUTDIR);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => {
  try { if (globalThis.__probeOutPath) fs.writeFileSync(globalThis.__probeOutPath, JSON.stringify(globalThis.__probeOut || {}, null, 2), "utf8"); } catch (_) {}
  console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
