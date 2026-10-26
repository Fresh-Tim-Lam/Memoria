#!/usr/bin/env node
/* task-170 复现探针：分栏模式编辑 mermaid 时源码区 scrollTop 被谁改变。
 *
 * 记录：editorPane/previewPane 的 scrollTop 每次 set（含调用栈）、scrollIntoView、scroll 事件、
 *       #editor / #preview 的 DOM 变更计数，以及逐字输入时两端 scrollTop。
 * 用法：node split-mermaid-scroll-probe.mjs --cdp http://127.0.0.1:9598 --out <json> --label before
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
  var ep=document.getElementById('editor-pane'), pp=document.getElementById('preview-pane');
  var ed=document.getElementById('editor'), pv=document.getElementById('preview');
  return {
    viewMode:(window.state||{}).viewMode, currentPath:(window.state||{}).currentPath,
    editMode: window.MemoriaEditHandler ? !!window.MemoriaEditHandler.editMode : null,
    epScroll: ep?Math.round(ep.scrollTop):null, epMax: ep?Math.max(0,ep.scrollHeight-ep.clientHeight):null,
    ppScroll: pp?Math.round(pp.scrollTop):null,
    editorHeight: ed?Math.round(ed.getBoundingClientRect().height):null,
    editorChildCount: ed?ed.childElementCount:null,
    mermaidCount: pv?pv.querySelectorAll('.mermaid, .-mermaid-container, code.language-mermaid, .-mermaid-error').length:null,
    topSource: (function(){ try { return window.MemoriaApp.getViewTopSrcLine('source'); } catch(e){ return null; } })(),
    topPreview: (function(){ try { return window.MemoriaApp.getViewTopSrcLine('preview'); } catch(e){ return null; } })(),
    probe: window.__probe ? {scroll:window.__probe.scrollLog.length, into:window.__probe.intoLog.length,
      mutations:{editor:window.__probe.editorMutations, preview:window.__probe.previewMutations}} : null
  };
})()`;

const INSTALL = `(function(){
  if (window.__probeInstalled) return true;
  window.__probeInstalled = true;
  window.__probe = { scrollLog: [], intoLog: [], scrollEvents: [], editorMutations: 0, previewMutations: 0,
                     editorMutationTypes: {}, previewMutationTypes: {} };
  var ep=document.getElementById('editor-pane'), pp=document.getElementById('preview-pane');
  var ed=document.getElementById('editor'), pv=document.getElementById('preview');
  var desc=Object.getOwnPropertyDescriptor(Element.prototype,'scrollTop');
  if(desc && desc.set){
    Object.defineProperty(Element.prototype,'scrollTop',{ configurable:true, get:desc.get, set:function(v){
      if(this===ep||this===pp){
        try { window.__probe.scrollLog.push({t:Math.round(performance.now()), id:this.id,
          from:this.scrollTop, to:v,
          stack:(new Error().stack||'').split('\\n').slice(1,7).join(' | ')}); } catch(_){}
      }
      return desc.set.call(this,v);
    }});
  }
  var siv=Element.prototype.scrollIntoView;
  if(siv){ Element.prototype.scrollIntoView=function(){
    try { if(this.closest && this.closest('#editor-pane,#preview-pane')) window.__probe.intoLog.push({t:Math.round(performance.now()), tag:this.tagName, cls:this.className, stack:(new Error().stack||'').split('\\n').slice(1,7).join(' | ')}); } catch(_){}
    return siv.apply(this,arguments);
  }; }
  window.addEventListener('scroll', function(e){
    if(e.target===ep||e.target===pp){
      window.__probe.scrollEvents.push({t:Math.round(performance.now()), id:e.target.id, top:Math.round(e.target.scrollTop)});
    }
  }, true);
  function observe(root, name){
    if(!root) return;
    var mo=new MutationObserver(function(recs){
      window.__probe[name+'Mutations'] += recs.length;
      recs.forEach(function(r){ var k=(r.type+':'+(r.addedNodes?r.addedNodes.length:0)); window.__probe[name+'MutationTypes'][k]=(window.__probe[name+'MutationTypes'][k]||0)+1; });
    });
    mo.observe(root,{childList:true,subtree:true,characterData:true,attributes:true});
  }
  observe(ed,'editor'); observe(pv,'preview');
  return true;
})()`;

const SET_CARET = `(function(){
  var lineNull = null;
  var lines = [].slice.call(document.querySelectorAll('#editor .-line'));
  for (var i=0;i<lines.length;i++){
    var t = (lines[i].textContent||'');
    if (t.indexOf('A[开始]') >= 0 || t.indexOf('graph TD') >= 0) { lineNull = lines[i]; break; }
  }
  if(!lineNull) return {ok:false, err:'mermaid line not found', sample: lines.slice(0,5).map(function(x){return x.textContent;})};
  var content = lineNull.querySelector('.-line-content');
  var range = document.createRange(); range.selectNodeContents(content); range.collapse(false);
  var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  content.focus();
  var pane=document.getElementById('editor-pane');
  // 关键：把 mermaid 块顶对齐到分栏顶部（用户编辑块在视口顶部时的场景）
  try { window.MemoriaApp.scrollToSrcLine('split', parseInt(lineNull.id.replace('line-',''),10)); } catch (e) {}
  var r2=lineNull.getBoundingClientRect();
  return {ok:true, line:lineNull.id, lineText:(content.textContent||'').slice(0,60), epScroll:Math.round(pane.scrollTop),
          lineTop:Math.round(r2.top - pane.getBoundingClientRect().top),
          topSource:(function(){ try { return window.MemoriaApp.getViewTopSrcLine('source'); } catch(e){ return null; } })(),
          topPreview:(function(){ try { return window.MemoriaApp.getViewTopSrcLine('preview'); } catch(e){ return null; } })()};
})()`;

const INSERT = (ch) => `(function(){
  var sel=window.getSelection(); if(!sel||!sel.rangeCount) return false;
  var r=sel.getRangeAt(0); var node=r.startContainer;
  if(node.nodeType!==3){ return 'no-text-node'; }
  return true;
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9598");
  const label = String(args.label || "before");
  const OUT = path.resolve(String(args.out || "split-mermaid-scroll.json"));
  const shotDir = path.join(path.dirname(OUT), "split-mermaid-scroll-screens");
  fs.mkdirSync(shotDir, { recursive: true });
  const out = { label, startedAt: new Date().toISOString(), steps: {} };
  globalThis.__probeOut = out; globalThis.__probeOutPath = OUT;

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp } = conn;
  await cdp.send("Page.enable"); await cdp.send("Runtime.enable");
  async function shot(name) {
    const r = await cdp.send("Page.captureScreenshot", { format: "png" });
    const p = path.join(shotDir, label + "-" + name + ".png");
    fs.writeFileSync(p, Buffer.from(r.data, "base64"));
    return p;
  }
  async function clickAt(x, y) {
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
    await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 1, clickCount: 1 });
  }
  async function openSplit() {
    // 确保编辑模式开启并进入分栏
    await cdp.evalJS(`(function(){ try { if(window.MemoriaEditHandler && !window.MemoriaEditHandler.editMode) window.MemoriaEditHandler.toggleEditMode(); } catch(e){} return true; })()`);
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode('split'); } catch(e){} return true; })()`);
    await cdp.waitFor('(window.state||{}).viewMode === "split"', { timeout: 15000, label: "split" });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/mermaid-edit.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/mermaid-edit.md" && !!window.state.doc', { timeout: 30000, label: "open doc" });
    await cdp.waitFor('document.querySelectorAll("#editor .-line").length > 40', { timeout: 20000, label: "lines" });
    await sleep(1200);
  }

  await openSplit();
  out.steps.installed = await cdp.evalJS(INSTALL);
  const caret = await cdp.evalJS(SET_CARET);
  out.steps.caret = caret;
  await sleep(600);
  out.steps.before = await cdp.evalJS(READ);
  out.steps.beforeShot = await shot("before");

  // 清空已产生的日志，从输入前开始计
  await cdp.evalJS(`(function(){ window.__probe.scrollLog=[]; window.__probe.intoLog=[]; window.__probe.scrollEvents=[]; window.__probe.editorMutations=0; window.__probe.previewMutations=0; return true; })()`);

  const typed = [];
  const text = (args.text && String(args.text)) || "; P1[新A]; P2[新B]; P3[新C]"; // 合法 mermaid 追加（改变图形/高度）
  for (let i = 0; i < text.length; i++) {
    await cdp.evalJS(INSERT(text[i]));
    await cdp.send("Input.insertText", { text: text[i] });
    await sleep(150);
    typed.push(await cdp.evalJS(READ));
  }
  out.steps.typed = typed;
  out.steps.after = await cdp.evalJS(READ);
  await sleep(900);
  out.steps.afterSettled = await cdp.evalJS(READ);
  out.steps.afterShot = await shot("after");

  out.steps.logs = await cdp.evalJS(`(function(){ return {
    scrollLog: window.__probe.scrollLog,
    intoLog: window.__probe.intoLog,
    scrollEvents: window.__probe.scrollEvents,
    editorMutations: window.__probe.editorMutations,
    previewMutations: window.__probe.previewMutations,
    editorMutationTypes: window.__probe.editorMutationTypes,
    previewMutationTypes: window.__probe.previewMutationTypes
  }; })()`);
  // 编辑后统计：源码区 scrollTop 是否出现非用户变化（由探针日志判定）
  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf8");
  console.log("OUT=" + OUT);
  console.log("caret", JSON.stringify(out.steps.caret));
  console.log("before", JSON.stringify(out.steps.before));
  console.log("after", JSON.stringify(out.steps.after), "settled", JSON.stringify(out.steps.afterSettled));
  console.log("scrollLogCount", out.steps.logs.scrollLog.length, "intoCount", out.steps.logs.intoLog.length,
              "editorMut", out.steps.logs.editorMutations, "previewMut", out.steps.logs.previewMutations);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => {
  try { if (globalThis.__probeOutPath) fs.writeFileSync(globalThis.__probeOutPath, JSON.stringify(globalThis.__probeOut || {}, null, 2), "utf8"); } catch (_) { /* noop */ }
  console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2);
});
