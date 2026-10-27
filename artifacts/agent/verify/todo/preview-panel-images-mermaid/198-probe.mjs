#!/usr/bin/env node
/* task-198 真机探针：B1 图片编辑滚动 / B2 小窗 mermaid / B3 关闭小窗滚动与定位按钮 */
"use strict";
import fs from "node:fs";
import path from "node:path";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith("--")) { a[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true; }
  }
  return a;
}
async function httpJson(url, timeout = 3000) {
  const c = new AbortController(); const t = setTimeout(() => c.abort(), timeout);
  try { return await (await fetch(url, { signal: c.signal })).json(); } finally { clearTimeout(t); }
}
class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.p = new Map(); ws.addEventListener("message", (e) => this._msg(e.data)); }
  static connect(url) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(url); const to = setTimeout(() => rej(new Error("CDP timeout")), 15000);
      ws.addEventListener("open", () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener("error", () => { clearTimeout(to); rej(new Error("CDP error")); });
    });
  }
  _msg(raw) { let m; try { m = JSON.parse(typeof raw === "string" ? raw : String(raw)); } catch { return; } if (m.id == null) return; const p = this.p.get(m.id); if (!p) return; this.p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}) { return new Promise((resolve, reject) => { const id = ++this.id; this.p.set(id, { resolve, reject }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async js(expr, timeout = 20000) {
    const p = this.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
    const g = new Promise((_, rej) => setTimeout(() => rej(new Error("js timeout")), timeout));
    const r = await Promise.race([p, g]);
    if (r && r.exceptionDetails) throw new Error("js error: " + String(r.exceptionDetails.exception?.description || r.exceptionDetails.text).slice(0, 300));
    return r?.result?.value;
  }
  async waitFor(expr, timeout = 20000, label = "") {
    const t0 = Date.now();
    for (;;) { let v; try { v = await this.js(expr); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error("wait timeout: " + label); await sleep(150); }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}
async function attach(cdpBase) {
  const list = await httpJson(cdpBase.replace(/\/$/, "") + "/json/list");
  for (const t of (list || []).filter((x) => x?.type === "page" && x.webSocketDebuggerUrl)) {
    let cdp;
    try {
      cdp = await CDP.connect(t.webSocketDebuggerUrl);
      await cdp.waitFor("!!(window.MemoriaApp && window.MemoriaBridge)", 25000, "app");
      return cdp;
    } catch { try { cdp?.close(); } catch { /* noop */ } }
  }
  throw new Error("no app target");
}
const PAIR = `(function(){
  var p=document.getElementById('preview-pane'), e=document.getElementById('editor-pane');
  return {previewTop:p?p.scrollTop:null, editorTop:e?e.scrollTop:null};
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9600");
  const outPath = path.resolve(String(args.out || "t198.json"));
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const shots = path.join(path.dirname(outPath), "shots"); fs.mkdirSync(shots, { recursive: true });
  const out = { startedAt: new Date().toISOString(), steps: {} };
  const cdp = await attach(cdpBase);
  await cdp.send("Page.enable"); await cdp.send("Runtime.enable");
  const shot = async (name) => { const r = await cdp.send("Page.captureScreenshot", { format: "png" }); const p = path.join(shots, name + ".png"); fs.writeFileSync(p, Buffer.from(r.data, "base64")); return p; };

  // ── B1：长文 + 图片，中段滚动后编辑图片属性 ──
  await cdp.waitFor(`(function(){ return window.MemoriaApp.state.kbPath && !window.MemoriaApp.state.startupInFlight; })()`, 30000, "startup done");
  for (let i = 0; i < 20; i++) {
    const r = await cdp.js(`window.MemoriaApp.openFile('docs/long-image.md')`);
    out.steps.openLongImageResult = r;
    if (r !== "failed") break;
    await sleep(500);
  }
  await cdp.waitFor(`(function(){ return window.state && String(window.state.currentPath||'').indexOf('long-image')>=0 && document.querySelector('#preview'); })()`, 30000, "open long-image");
  await sleep(700);
  await cdp.js(`document.querySelector('[data-view="split"]')?.click()`);
  await sleep(800);
  // 惰性预览：图在中段，需先把预览定位到图片源码行（否则图块还没物化）
  const imgLine = await cdp.js(`(function(){
    var lines=window.MemoriaApp.state.doc.lines||[]; for(var i=0;i<lines.length;i++){ if(/^!\\[/.test(lines[i])) return i+1; } return 0;
  })()`);
  out.steps.b1ImageLine = imgLine;
  await cdp.js(`window.MemoriaApp.scrollToSrcLine('preview', ${imgLine})`);
  await sleep(900);
  out.steps.b1Debug = await cdp.js(`(function(){
    var p=document.getElementById('preview-pane');
    return {view:window.MemoriaApp.state.viewMode, line:window.MemoriaApp.state.doc.lines[${imgLine}-1],
            scroll:p?p.scrollTop:null, html:(document.getElementById('preview')||{}).innerHTML?.slice(0,1200)};
  })()`);
  try {
    await cdp.waitFor(`(function(){ var img=document.querySelector('#preview img'); return !!img; })()`, 6000, "image block");
  } catch (e) {
    console.log("B1 DEBUG=" + JSON.stringify(out.steps.b1Debug));
    throw e;
  }
  out.steps.b1Before = await cdp.js(`(function(){
    var img=document.querySelector('#preview img');
    img.scrollIntoView({block:'center'});
    return true;
  })()`);
  await sleep(900);
  await cdp.waitFor(`(function(){ var img=document.querySelector('#preview img'); return img && img.complete && img.naturalWidth>0; })()`, 15000, "image loaded");
  const before = await cdp.js(PAIR);
  out.steps.b1TopBefore = await cdp.js(`window.MemoriaApp.getViewTopSrcLine ? window.MemoriaApp.getViewTopSrcLine('preview') : null`);
  out.steps.b1ImgRectBefore = await cdp.js(`(function(){ var i=document.querySelector('#preview img'); if(!i) return null; var r=i.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,h:r.height}; })()`);
  const imgInfo = await cdp.js(`(function(){
    var img=document.querySelector('#preview img'); var b=img.closest('[data--src-line]');
    return {srcLine: b?Number(b.getAttribute('data--src-line')):0, width: Math.round(img.getBoundingClientRect().width), top: img.getBoundingClientRect().top};
  })()`);
  out.steps.b1Image = imgInfo;
  out.steps.b1ScrollBefore = before;
  out.steps.b1ShotBefore = await shot("b1-before-edit");
  // 走真实 UI 路径：图片工具栏提交属性（app.js 的 memoria:image-attr）
  await cdp.js(`document.dispatchEvent(new CustomEvent('memoria:image-attr',{detail:{srcLine:${imgInfo.srcLine}, attrs:{width:'360'}}}))`);
  await sleep(400);
  const mid = await cdp.js(PAIR);
  await sleep(1200);
  const after = await cdp.js(PAIR);
  out.steps.b1ScrollMid = mid;
  out.steps.b1TopAfter = await cdp.js(`window.MemoriaApp.getViewTopSrcLine ? window.MemoriaApp.getViewTopSrcLine('preview') : null`);
  out.steps.b1ImgRectAfter = await cdp.js(`(function(){ var i=document.querySelector('#preview img'); if(!i) return null; var r=i.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,h:r.height}; })()`);
  out.steps.b1ScrollAfter = after;
  out.steps.b1Delta = { preview: (after.previewTop ?? 0) - (before.previewTop ?? 0), editor: (after.editorTop ?? 0) - (before.editorTop ?? 0) };
  out.steps.b1Stats = await cdp.js(`window.__memoriaEditScrollStats ? window.__memoriaEditScrollStats() : null`);
  out.steps.b1ShotAfter = await shot("b1-after-edit");

  fs.writeFileSync(outPath + '.partial', JSON.stringify(out, null, 2), 'utf8');
  // ── B2/B3：跳转入口 → 小窗（mermaid）；关闭/定位 ──
  await cdp.js(`window.MemoriaApp.openFile('docs/link-source.md')`);
  await cdp.waitFor(`(function(){ return String(window.state.currentPath||'').indexOf('link-source')>=0; })()`, 20000, "open link-source");
  await sleep(500);
  await cdp.js(`(function(){
    var lines=window.MemoriaApp.state.doc.lines||[]; for(var i=0;i<lines.length;i++){ if(lines[i].indexOf('[[')>=0){ window.MemoriaApp.scrollToSrcLine('preview', i+1); return i+1; } } return 0;
  })()`);
  await sleep(900);
  await cdp.waitFor(`(function(){ return !!document.querySelector('#preview .memoria-link'); })()`, 20000, "wikilink in preview");
  await cdp.js(`document.querySelector('#preview .memoria-link').click()`);
  await cdp.waitFor(`(function(){ return !!document.getElementById('link-panel'); })()`, 15000, "link panel");
  await sleep(1200);
  out.steps.b2 = await cdp.js(`(function(){
    var panel=document.getElementById('link-panel'); var doc=panel?panel.querySelector('[data-panel-doc]'):null;
    return {
      panel: !!panel,
      svgCount: doc?doc.querySelectorAll('svg').length:0,
      mermaidCode: doc?doc.querySelectorAll('code.language-mermaid').length:0,
      mermaidDiv: doc?doc.querySelectorAll('.mermaid').length:0,
      text: doc?(doc.innerText||'').slice(0,400):''
    };
  })()`);
  out.steps.b2Shot = await shot("b2-panel-mermaid");

  // 滚动离开入口，再关闭小窗：测关闭是否把滚动拽回入口
  await cdp.js(`(function(){ var p=document.getElementById('preview-pane'); if(p)p.scrollTop=0; var e=document.getElementById('editor-pane'); if(e)e.scrollTop=0; return true; })()`);
  await sleep(500);
  const closeBefore = await cdp.js(PAIR);
  await cdp.js(`document.querySelector('#link-panel [data-panel-close]')?.click()`);
  await sleep(700);
  const closeAfter = await cdp.js(PAIR);
  out.steps.b3Close = {
    before: closeBefore, after: closeAfter,
    delta: { preview: (closeAfter.previewTop ?? 0) - (closeBefore.previewTop ?? 0), editor: (closeAfter.editorTop ?? 0) - (closeBefore.editorTop ?? 0) },
    panelGone: await cdp.js(`!document.getElementById('link-panel')`),
  };
  out.steps.b3ShotClosed = await shot("b3-after-close");

  // 修复后应存在的定位按钮：重新开小窗，滚远，点按钮 → 入口进入视口
  await cdp.js(`document.querySelector('#preview .memoria-link').click()`);
  await cdp.waitFor(`!!document.getElementById('link-panel')`, 15000, "panel reopen");
  await sleep(900);
  const locateBtn = await cdp.js(`!!document.querySelector('#link-panel [data-panel-locate]')`);
  out.steps.b3LocateButton = locateBtn;
  if (locateBtn) {
    await cdp.js(`(function(){ var p=document.getElementById('preview-pane'); if(p)p.scrollTop=0; var e=document.getElementById('editor-pane'); if(e)e.scrollTop=0; return true; })()`);
    await sleep(400);
    const locBefore = await cdp.js(PAIR);
    await cdp.js(`document.querySelector('#link-panel [data-panel-locate]').click()`);
    await sleep(900);
    const locAfter = await cdp.js(PAIR);
    out.steps.b3Locate = { before: locBefore, after: locAfter, delta: { preview: (locAfter.previewTop ?? 0) - (locBefore.previewTop ?? 0), editor: (locAfter.editorTop ?? 0) - (locBefore.editorTop ?? 0) }, panelGone: await cdp.js(`!document.getElementById('link-panel')`) };
  }
  // T-ui-4 回归：主预览 mermaid 仍由同一 renderMermaidBlocks 渲染（未因小窗复用而破坏）
  await cdp.js(`window.MemoriaApp.openFile('docs/link-target.md')`);
  await cdp.waitFor(`(function(){ return String(window.state.currentPath||'').indexOf('link-target')>=0; })()`, 20000, "open target");
  await cdp.waitFor(`(function(){ return !!document.querySelector('#preview svg'); })()`, 15000, "main mermaid svg");
  out.steps.mainMermaid = await cdp.js(`(function(){
    var p=document.getElementById('preview'); return {svg:p?p.querySelectorAll('svg').length:0, error:p?p.querySelectorAll('.-mermaid-error').length:0};
  })()`);
  out.steps.mainMermaidShot = await shot("main-mermaid-regression");
  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf8");
  console.log("OUT=" + outPath);
  console.log("B1 before=" + JSON.stringify(out.steps.b1ScrollBefore) + " after=" + JSON.stringify(out.steps.b1ScrollAfter) + " delta=" + JSON.stringify(out.steps.b1Delta));
  console.log("B2=" + JSON.stringify(out.steps.b2));
  console.log("B3 close=" + JSON.stringify(out.steps.b3Close));
  console.log("B3 locateButton=" + out.steps.b3LocateButton + " locate=" + JSON.stringify(out.steps.b3Locate));
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL", e?.stack || e); process.exit(2); });
