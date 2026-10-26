#!/usr/bin/env node
/* task-168 真机验收：跳转小窗 8 方向自由缩放。
 *
 * 验证：
 *  - 原生 resize 已移除（getComputedStyle(panel).resize === "none"），无"双把手"
 *  - 8 个把手存在、命中区 ≥8px、cursor 映射正确
 *  - 8 方向各自拉伸：e/s 只变尺寸；w/n 尺寸+位置同步；nw/ne/sw/se 双轴
 *  - min/max 夹紧（360×260 ~ 720×640）
 *  - 缩放后持久化（ui-settings linkPanel），重开恢复
 *  - 折叠态把手隐藏且不可缩放
 *  - 标题栏拖动 / 双击复位 / 方向键微调 不回归
 *  - hover 时把手中边高亮（截图 + :hover + 背景色校验）
 *
 * 用法：node link-panel-resize-probe.mjs --cdp http://127.0.0.1:9596 --config <临时config> --out <json>
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
      await cdp.waitFor('!!(window.MemoriaApp && window.state && typeof window.MemoriaApp.openFile === "function")', { timeout: 25000, label: "app" });
      return { cdp, target: t };
    } catch { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}

const READ = `(function(){
  var panel=document.getElementById('link-panel');
  var r=panel?panel.getBoundingClientRect():null;
  function h(el){return el?Math.round(el.getBoundingClientRect().height):null;}
  function w(el){return el?Math.round(el.getBoundingClientRect().width):null;}
  var hs=[].slice.call(panel?panel.querySelectorAll('[data-panel-resize]'):[]);
  return {
    panelVisible: !!(panel && panel.offsetWidth>0),
    rect: r?{x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}:null,
    nativeResize: panel?getComputedStyle(panel).resize:null,
    handleCount: hs.length,
    handles: hs.map(function(el){
      var b=el.getBoundingClientRect();
      return {dir:el.dataset.panelResize,cursor:getComputedStyle(el).cursor,
              w:Math.round(b.width),h:Math.round(b.height),
              display:getComputedStyle(el).display, bg:getComputedStyle(el).backgroundColor,
              hover:el.matches(':hover')};
    }),
    collapsed: panel?panel.classList.contains('-collapsed'):null,
    currentPath:(window.state||{}).currentPath||null
  };
})()`;

const RESET = `(function(){
  var tb=document.querySelector('.-link-panel-titlebar');
  if(!tb) return false;
  tb.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true}));
  return true;
})()`;

const SYNTH_RESIZE = (dir, dx, dy) => `(function(){
  var panel=document.getElementById('link-panel');
  if(!panel) return {ok:false,err:'no panel'};
  var el=panel.querySelector('[data-panel-resize="${dir}"]');
  if(!el) return {ok:false,err:'no handle ${dir}'};
  var b=el.getBoundingClientRect();
  var x0=Math.round(b.left+Math.min(b.width/2,4));
  var y0=Math.round(b.top+Math.min(b.height/2,4));
  function pe(type,cx,cy){return new PointerEvent(type,{bubbles:true,cancelable:true,button:0,buttons:1,pointerId:1,pointerType:'mouse',clientX:cx,clientY:cy});}
  el.dispatchEvent(pe('pointerdown',x0,y0));
  window.dispatchEvent(pe('pointermove',x0+(${dx}),y0+(${dy})));
  window.dispatchEvent(pe('pointerup',x0+(${dx}),y0+(${dy})));
  var r=panel.getBoundingClientRect();
  return {ok:true, rect:{x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}};
})()`;

const SYNTH_DRAG = (dx, dy) => `(function(){
  var panel=document.getElementById('link-panel');
  var tb=panel&&panel.querySelector('.-link-panel-titlebar');
  if(!tb) return {ok:false};
  var b=tb.getBoundingClientRect();
  var x0=Math.round(b.left+b.width*0.6), y0=Math.round(b.top+b.height/2);
  function pe(type,cx,cy){return new PointerEvent(type,{bubbles:true,cancelable:true,button:0,buttons:1,pointerId:2,pointerType:'mouse',clientX:cx,clientY:cy});}
  tb.dispatchEvent(pe('pointerdown',x0,y0));
  window.dispatchEvent(pe('pointermove',x0+(${dx}),y0+(${dy})));
  window.dispatchEvent(pe('pointerup',x0+(${dx}),y0+(${dy})));
  var r=panel.getBoundingClientRect();
  return {ok:true, rect:{x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}};
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9596");
  const cfg = String(args.config || "");
  const OUT = path.resolve(String(args.out || "artifacts/agent/verify/todo/link-panel-resize.json"));
  const shotDir = path.join(path.dirname(OUT), "link-panel-resize-screens");
  fs.mkdirSync(shotDir, { recursive: true });
  const settingsPath = cfg ? path.join(cfg, "ui-settings.json") : "";
  const out = { startedAt: new Date().toISOString(), steps: {} };
  globalThis.__probeOut = out; globalThis.__probeOutPath = OUT;

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp } = conn;
  await cdp.send("Page.enable"); await cdp.send("Runtime.enable");
  async function shot(name) {
    const r = await cdp.send("Page.captureScreenshot", { format: "png" });
    const p = path.join(shotDir, name + ".png");
    fs.writeFileSync(p, Buffer.from(r.data, "base64"));
    return p;
  }
  async function clickAt(x, y) {
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 1, clickCount: 1 });
  }
  async function clickText(selector, text) {
    const pos = await cdp.evalJS(`(function(){
      var els=[].slice.call(document.querySelectorAll(${JSON.stringify(selector)}));
      for(var i=0;i<els.length;i++){ if((els[i].textContent||'').indexOf(${JSON.stringify(text)})>=0){
        els[i].scrollIntoView({block:'center'}); var r=els[i].getBoundingClientRect();
        return {ok:true,x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};
      }} return {ok:false};
    })()`);
    if (!pos || !pos.ok) throw new Error("未找到可点击: " + selector + "/" + text);
    await clickAt(pos.x, pos.y);
  }
  async function openA() {
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode('split'); } catch(e){} return true; })()`);
    await cdp.waitFor('(window.state||{}).viewMode === "split"', { timeout: 15000, label: "split" });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/a.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/a.md" && !!window.state.doc', { timeout: 30000, label: "open a" });
    await cdp.waitFor('document.querySelectorAll(".memoria-link").length >= 3', { timeout: 20000, label: "links" });
    await sleep(350);
  }
  async function openPanel() {
    await openA();
    await clickText(".memoria-link", "单目标");
    await cdp.waitFor('!!document.getElementById("link-panel")', { timeout: 20000, label: "panel" });
    await sleep(600);
  }
  function readSettings() {
    if (!settingsPath || !fs.existsSync(settingsPath)) return null;
    try { return JSON.parse(fs.readFileSync(settingsPath, "utf8")); } catch (_) { return null; }
  }

  await openPanel();
  await cdp.evalJS(RESET);
  await sleep(300);
  const base = await cdp.evalJS(READ);
  out.steps.default = base;
  out.steps.default.shot = await shot("default-handles-invisible");

  // hover 左边（真实鼠标移到面板左边缘；截图 + 校验高亮）
  const r0 = base.rect;
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: r0.x + 2, y: r0.y + Math.round(r0.h / 2) });
  await sleep(350);
  out.steps.hoverW = await cdp.evalJS(`(function(){
    var el=document.querySelector('[data-panel-resize="w"]');
    var cs=el?getComputedStyle(el):null;
    return {hover: !!(el&&el.matches(':hover')), bg: cs?cs.backgroundColor:null, opacity: cs?cs.opacity:null, cursor: cs?cs.cursor:null};
  })()`);
  out.steps.hoverW.shot = await shot("hover-w-edge");
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: r0.x + Math.round(r0.w / 2), y: r0.y + Math.round(r0.h / 2) });
  await sleep(150);

  // 8 方向逐个拉伸（每次先 dblclick 复位到 520×420）
  const cases = [
    { dir: "e", dx: 80, dy: 0, expect: "w+80" },
    { dir: "w", dx: -80, dy: 0, expect: "x-80,w+80" },
    { dir: "s", dx: 0, dy: 60, expect: "h+60" },
    { dir: "n", dx: 0, dy: -60, expect: "y-60,h+60" },
    { dir: "ne", dx: 80, dy: -60, expect: "w+80,y-60,h+60" },
    { dir: "nw", dx: -80, dy: -60, expect: "x-80,w+80,y-60,h+60" },
    { dir: "se", dx: 80, dy: 60, expect: "w+80,h+60" },
    { dir: "sw", dx: -80, dy: 60, expect: "x-80,w+80,h+60" },
  ];
  out.steps.directions = [];
  for (const c of cases) {
    await cdp.evalJS(RESET);
    await sleep(120);
    const before = await cdp.evalJS(READ);
    const r = await cdp.evalJS(SYNTH_RESIZE(c.dir, c.dx, c.dy));
    await sleep(500);
    const after = await cdp.evalJS(READ);
    const b = before.rect, a = after.rect;
    const checks = {
      widthChanged: a.w !== b.w,
      heightChanged: a.h !== b.h,
      xChanged: a.x !== b.x,
      yChanged: a.y !== b.y,
      // 逐方向校验
      e: c.dir === "e" ? (a.w === b.w + 80 && a.h === b.h && a.x === b.x) : null,
      w: c.dir === "w" ? (a.w === b.w + 80 && a.x === b.x - 80 && a.h === b.h) : null,
      s: c.dir === "s" ? (a.h === b.h + 60 && a.w === b.w && a.y === b.y) : null,
      n: c.dir === "n" ? (a.h === b.h + 60 && a.y === b.y - 60 && a.w === b.w) : null,
      ne: c.dir === "ne" ? (a.w === b.w + 80 && a.h === b.h + 60 && a.y === b.y - 60) : null,
      nw: c.dir === "nw" ? (a.w === b.w + 80 && a.x === b.x - 80 && a.h === b.h + 60 && a.y === b.y - 60) : null,
      se: c.dir === "se" ? (a.w === b.w + 80 && a.h === b.h + 60) : null,
      sw: c.dir === "sw" ? (a.w === b.w + 80 && a.x === b.x - 80 && a.h === b.h + 60) : null,
    };
    out.steps.directions.push({ ...c, before: b, after: a, ok: !!r.ok, checks });
  }

  // 夹紧 min/max
  await cdp.evalJS(RESET); await sleep(120);
  out.steps.clampMax = await cdp.evalJS(`(function(){
    var el=document.querySelector('[data-panel-resize="e"]');
    if(!el) return {err:'no handle'};
    var b=el.getBoundingClientRect();
    function pe(t,x,y){return new PointerEvent(t,{bubbles:true,cancelable:true,button:0,buttons:1,pointerId:3,pointerType:'mouse',clientX:x,clientY:y});}
    var x0=Math.round(b.left+b.width/2), y0=Math.round(b.top+b.height/2);
    el.dispatchEvent(pe('pointerdown',x0,y0));
    var panel=document.getElementById('link-panel');
    var s1=panel?getComputedStyle(panel):null;
    window.dispatchEvent(pe('pointermove',x0+2000,y0));
    var r1=panel?panel.getBoundingClientRect():null;
    var s2=panel?getComputedStyle(panel):null;
    window.dispatchEvent(pe('pointerup',x0+2000,y0));
    var r2=panel?panel.getBoundingClientRect():null;
    return {width1:r1?Math.round(r1.width):null,width2:r2?Math.round(r2.width):null,
            resizing1:panel?panel.classList.contains('-resizing'):null,
            resizing2:panel?panel.classList.contains('-resizing'):null,
            styleW1:s1?s1.width:null,styleW2:s2?s2.width:null,
            dbg:window.__linkPanelResizeDbg?JSON.parse(JSON.stringify(window.__linkPanelResizeDbg)):null};
  })()`);
  await sleep(700);
  out.steps.clampMaxSettled = await cdp.evalJS('(function(){ var p=document.getElementById("link-panel"); return p?{w:Math.round(p.getBoundingClientRect().width)}:null; })()');
  await cdp.evalJS(RESET); await sleep(120);
  out.steps.clampMin = await cdp.evalJS(`(function(){
    var el=document.querySelector('[data-panel-resize="e"]');
    if(!el) return {err:'no handle'};
    var b=el.getBoundingClientRect();
    function pe(t,x,y){return new PointerEvent(t,{bubbles:true,cancelable:true,button:0,buttons:1,pointerId:4,pointerType:'mouse',clientX:x,clientY:y});}
    var x0=Math.round(b.left+b.width/2), y0=Math.round(b.top+b.height/2);
    el.dispatchEvent(pe('pointerdown',x0,y0));
    window.dispatchEvent(pe('pointermove',x0-2000,y0));
    window.dispatchEvent(pe('pointerup',x0-2000,y0));
    var p=document.getElementById('link-panel');
    return {w:p?Math.round(p.getBoundingClientRect().width):null};
  })()`);
  await sleep(700);
  out.steps.clampMinSettled = await cdp.evalJS('(function(){ var p=document.getElementById("link-panel"); return p?{w:Math.round(p.getBoundingClientRect().width)}:null; })()');

  // 持久化：se 拉到 600×480 → 关面板 → 重开
  await cdp.evalJS(RESET); await sleep(120);
  await cdp.evalJS(SYNTH_RESIZE("se", 80, 60));
  await sleep(2000);
  const resized = await cdp.evalJS(READ);
  out.steps.persistResize = {ok:true, rect:resized.rect};
  out.steps.persistBeforeClose = resized.rect;
  out.steps.settingsBeforeClose = readSettings();
  out.steps.shotResizedSE = await shot("resized-se");
  await cdp.evalJS(`(function(){ var b=document.querySelector('[data-panel-close]'); if(b)b.click(); return true; })()`);
  await sleep(2500);
  out.steps.settingsAfterResize = readSettings();
  await openPanel();
  const reopened = await cdp.evalJS(READ);
  out.steps.persistAfterReopen = reopened.rect;
  out.steps.persistOk = !!(resized.rect && reopened.rect &&
    Math.abs(reopened.rect.w - resized.rect.w) <= 1 && Math.abs(reopened.rect.h - resized.rect.h) <= 1);

  // 从左侧拉伸（截图）——复位后 w 拉 -80
  await cdp.evalJS(RESET); await sleep(150);
  out.steps.westResize = await cdp.evalJS(SYNTH_RESIZE("w", -80, 0));
  await sleep(250);
  out.steps.afterWest = await cdp.evalJS(READ);
  out.steps.shotWest = await shot("resized-from-west");
  // 从下方拉伸（截图）
  out.steps.southResize = await cdp.evalJS(SYNTH_RESIZE("s", 0, 60));
  await sleep(250);
  out.steps.afterSouth = await cdp.evalJS(READ);
  out.steps.shotSouth = await shot("resized-from-south");

  // 折叠态不可缩放
  await cdp.evalJS(`(function(){ document.querySelector('[data-panel-collapse]').click(); return true; })()`);
  await sleep(300);
  const col = await cdp.evalJS(READ);
  out.steps.collapsed = { rect: col.rect, handles: col.handles.map((h) => ({ dir: h.dir, display: h.display })) };
  out.steps.collapsed.resizeAttempt = await cdp.evalJS(SYNTH_RESIZE("e", 80, 0));
  await sleep(250);
  const colAfter = await cdp.evalJS(READ);
  out.steps.collapsed.afterRect = colAfter.rect;
  out.steps.collapsed.unchanged = !!(col.rect && colAfter.rect && col.rect.w === colAfter.rect.w);
  out.steps.collapsed.shot = await shot("collapsed-no-handles");
  await cdp.evalJS(`(function(){ document.querySelector('[data-panel-collapse]').click(); return true; })()`);
  await sleep(300);

  // 标题栏拖动 / 双击复位 / 方向键微调
  await cdp.evalJS(RESET); await sleep(150);
  out.steps.titleDrag = await cdp.evalJS(SYNTH_DRAG(60, 40));
  await sleep(200);
  out.steps.titleDragAfter = (await cdp.evalJS(READ)).rect;
  await cdp.evalJS(RESET); await sleep(200);
  out.steps.afterDblclickReset = (await cdp.evalJS(READ)).rect;
  // 方向键微调（标题栏聚焦后 ArrowRight）
  out.steps.arrowKey = await cdp.evalJS(`(function(){
    var tb=document.querySelector('.-link-panel-titlebar');
    if(!tb) return {err:'no panel'};
    tb.focus();
    var panel=document.getElementById('link-panel');
    var before=panel.getBoundingClientRect();
    var ev=new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true});
    document.dispatchEvent(ev);
    return {before:{x:Math.round(before.left)},
            active:(document.activeElement||{}).className||null,
            titlebarFocused:document.activeElement===tb,
            defaultPrevented:ev.defaultPrevented};
  })()`);
  await sleep(500);
  out.steps.arrowKey.afterX = await cdp.evalJS('(function(){var p=document.getElementById("link-panel");return p?Math.round(p.getBoundingClientRect().left):null;})()');

  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf8");
  console.log("OUT=" + OUT);
  console.log("default", JSON.stringify(out.steps.default));
  console.log("directions", JSON.stringify(out.steps.directions.map((d) => ({ dir: d.dir, checks: d.checks, ok: d.ok }))));
  console.log("persistOk", out.steps.persistOk, "collapsed", JSON.stringify(out.steps.collapsed.unchanged), "arrow", JSON.stringify(out.steps.arrowKey));
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => {
  try { if (globalThis.__probeOutPath) fs.writeFileSync(globalThis.__probeOutPath, JSON.stringify(globalThis.__probeOut || {}, null, 2), "utf8"); } catch (_) { /* noop */ }
  console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2);
});
