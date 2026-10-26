#!/usr/bin/env node
/* task-170 修复后验证：分栏编辑 mermaid/段落/代码/公式/表格时源码区不被抢滚；
 * 预览仍正常刷新；非编辑态「跟随滚动」不回归。
 *
 * 用法：node split-mermaid-edit-scroll-verify.mjs --cdp http://127.0.0.1:9598 --out <json>
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
      await cdp.waitFor('!!(window.MemoriaApp && window.state && typeof window.MemoriaApp.openFile === "function")', { timeout: 25000, label: "app" });
      return { cdp, target: t };
    } catch { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}

const SNAP = `(function(){
  var ep=document.getElementById('editor-pane'), pp=document.getElementById('preview-pane');
  var pv=document.getElementById('preview');
  var svgs=pv?pv.querySelectorAll('svg'):[];
  var h=0; for (var i=0;i<svgs.length;i++){ try { h += svgs[i].outerHTML.length; } catch(e){} }
  function top(mode){ try { return window.MemoriaApp.getViewTopSrcLine(mode); } catch(e){ return null; } }
  return { ep: ep?Math.round(ep.scrollTop):null, pp: pp?Math.round(pp.scrollTop):null,
           max: ep?Math.max(0,ep.scrollHeight-ep.clientHeight):null,
           sourceTop: top('source'), previewTop: top('preview'),
           svgCount: svgs.length, svgLen: h,
           previewLen: pv ? pv.textContent.length : null,
           viewMode:(window.state||{}).viewMode };
})()`;

const PREPARE = (needle, anchorNeedle, offset, center) => `(function(){
  var lines=[].slice.call(document.querySelectorAll('#editor .-line'));
  function find(n){ if(!n) return null; for (var i=0;i<lines.length;i++){ if ((lines[i].textContent||'').indexOf(n)>=0) return lines[i]; } return null; }
  var line=find(${JSON.stringify(needle)});
  if(!line) return {ok:false,err:'line not found: '+${JSON.stringify(needle)}};
  var anchor=find(${JSON.stringify(anchorNeedle || needle)}) || line;
  try { window.MemoriaApp.scrollToSrcLine('split', parseInt(anchor.id.replace('line-',''),10)); } catch(e) { return {ok:false,err:'scrollToSrcLine: '+e}; }
  var pane=document.getElementById('editor-pane');
  if (${center ? "true" : "false"}) {
    // 长源码区 + mermaid 在中间编辑：把光标行放到视口约 45% 处
    var rr=line.getBoundingClientRect(), pr=pane.getBoundingClientRect();
    pane.scrollTop = Math.max(0, pane.scrollTop + (rr.top - pr.top) - Math.round(pane.clientHeight*0.45));
  } else {
    // 目标块顶部再让出 40px，避免光标贴边触发 E26 的最小补滚（本验证只测"被同步抢滚"）
    pane.scrollTop = Math.max(0, pane.scrollTop - (${offset == null ? 40 : Number(offset)}));
  }
  var content=line.querySelector('.-line-content');
  if(!content) return {ok:false,err:'no line-content'};
  var r=document.createRange(); r.selectNodeContents(content); r.collapse(false);
  var sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(r); content.focus();
  return {ok:true, line:line.id, anchor:anchor.id, text:(content.textContent||'').slice(0,60),
          ep:Math.round(pane.scrollTop), pp:Math.round(document.getElementById('preview-pane').scrollTop)};
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9598");
  const OUT = path.resolve(String(args.out || "split-mermaid-edit-scroll-after.json"));
  const shotDir = path.join(path.dirname(OUT), "split-mermaid-edit-scroll-screens");
  fs.mkdirSync(shotDir, { recursive: true });
  const out = { label: String(args.label || "after"), startedAt: new Date().toISOString(), phases: {} };

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp } = conn;
  await cdp.send("Page.enable"); await cdp.send("Runtime.enable");
  async function shot(name) {
    const r = await cdp.send("Page.captureScreenshot", { format: "png" });
    const p = path.join(shotDir, (args.label || "after") + "-" + name + ".png");
    fs.writeFileSync(p, Buffer.from(r.data, "base64"));
    return p;
  }
  const snap = () => cdp.evalJS(SNAP);
  const prepare = (needle, anchorNeedle, offset, center) => cdp.evalJS(PREPARE(needle, anchorNeedle, offset, center));
  async function resetLogs() {
    await cdp.evalJS(`(function(){ window.__verify = { scrollSets: [] }; var d=Object.getOwnPropertyDescriptor(Element.prototype,'scrollTop');
      if(window.__verifyWrapped) return true;
      try { Object.defineProperty(Element.prototype,'scrollTop',{configurable:true,get:d.get,set:function(v){
        if(this && (this.id==='editor-pane'||this.id==='preview-pane')){
          window.__verify.scrollSets.push({id:this.id, from:this.scrollTop, to:v, stack:(new Error().stack||'').split('\\n').slice(1,6).join(' | ')});
        }
        return d.set.call(this,v);
      }}); window.__verifyWrapped=true; } catch(e) { window.__verify.wrapErr=String(e); }
      return true; })()`);
  }
  async function typeChars(text, gap) {
    const steps = [];
    for (const ch of text) {
      await cdp.send("Input.insertText", { text: ch });
      await sleep(gap == null ? 150 : gap);
      steps.push(await snap());
    }
    return steps;
  }
  async function runEditPhase(name, needle, anchor, text, { gap = 150, settle = 800, center = false } = {}) {
    const prep = await prepare(needle, anchor || needle, 40, center);
    if (!prep || !prep.ok) return { name, ok: false, prep };
    await sleep(450);
    const before = await snap();
    await resetLogs();
    const steps = await typeChars(text, gap);
    await sleep(settle);
    const after = await snap();
    const logs = await cdp.evalJS('JSON.parse(JSON.stringify(window.__verify || {}))');
    const epSeries = steps.map((s) => s.ep);
    const epMoved = epSeries.some((v) => v !== before.ep) || after.ep !== before.ep;
    const sourceSyncSets = (logs.scrollSets || []).filter((e) => e.id === "editor-pane");
    const previewSets = (logs.scrollSets || []).filter((e) => e.id === "preview-pane");
    const previewChanged = after.previewLen !== before.previewLen || after.svgLen !== before.svgLen || after.svgCount !== before.svgCount;
    return {
      name, ok: !epMoved && previewChanged,
      prep, before, after,
      epSeries, epMoved, previewChanged,
      previewSets: previewSets.slice(0, 12),
      sourceScrollSets: sourceSyncSets.slice(0, 12),
      previewDelta: { len: after.previewLen - before.previewLen, svgLen: after.svgLen - before.svgLen, svgCount: after.svgCount - before.svgCount }
    };
  }

  // 打开夹具并进入分栏
  await cdp.evalJS(`(function(){ try { if(window.MemoriaEditHandler && !window.MemoriaEditHandler.editMode) window.MemoriaEditHandler.toggleEditMode(); } catch(e){} return true; })()`);
  await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode('split'); } catch(e){} return true; })()`);
  await cdp.waitFor('(window.state||{}).viewMode === "split"', { timeout: 15000, label: "split" });
  await cdp.evalJS('window.MemoriaApp.openFile("docs/mermaid-edit.md", { skipNav: true })');
  await cdp.waitFor('window.state.currentPath === "docs/mermaid-edit.md" && !!window.state.doc', { timeout: 30000, label: "open" });
  await cdp.waitFor('document.querySelectorAll("#editor .-line").length > 400', { timeout: 20000, label: "lines" });
  await sleep(1500);
  out.started = await snap();
  out.beforeShot = await shot("before");

  // 主用例：mermaid（目标行在块顶下方 2 行，避免 E26 贴边补滚；块顶对齐后整体留 40px 余量）
  out.phases.mermaid = await runEditPhase("mermaid", "A[开始]", "```mermaid", "; P1[新A]; P2[新B]; P3[新C]", { center: true });
  out.afterMermaidShot = await shot("after-mermaid");

  // 非编辑态跟随滚动回归（预览→源码、源码→预览）
  await sleep(1600);
  const followBefore = await snap();
  await cdp.evalJS(`(function(){ var pp=document.getElementById('preview-pane'); pp.scrollTop += 500; return pp.scrollTop; })()`);
  await sleep(500);
  const followPreviewToSource = await snap();
  await cdp.evalJS(`(function(){ var ep=document.getElementById('editor-pane'); ep.scrollTop += 500; return ep.scrollTop; })()`);
  await sleep(500);
  const followSourceToPreview = await snap();
  out.follow = {
    before: followBefore,
    previewScroll_after: followPreviewToSource,
    sourceScroll_after: followSourceToPreview,
    previewToSourceWorks: followPreviewToSource.sourceTop !== followBefore.sourceTop || followPreviewToSource.ep !== followBefore.ep,
    sourceToPreviewWorks: followSourceToPreview.previewTop !== followPreviewToSource.previewTop || followSourceToPreview.pp !== followPreviewToSource.pp
  };

  // 回归：普通段落 / js 代码块 / 公式块 / 表格（每类输入若干字符，源码区不得被抢滚）
  out.phases.paragraph = await runEditPhase("paragraph", "第 10 段", "第 10 段", "XY");
  out.phases.code = await runEditPhase("code", "const a = 1;", "const a = 1;", " //x");
  out.phases.formula = await runEditPhase("formula", "x + y = z", "x + y = z", " + 1");
  out.phases.table = await runEditPhase("table", "| 1 | 2 |", "| 1 | 2 |", " z");
  out.afterAllShot = await shot("after-all");

  out.summary = {
    mermaidSourceStable: !out.phases.mermaid.epMoved,
    mermaidPreviewRefreshed: out.phases.mermaid.previewChanged,
    followPreviewToSource: out.follow.previewToSourceWorks,
    followSourceToPreview: out.follow.sourceToPreviewWorks,
    regressionsStable: ["paragraph", "code", "formula", "table"].every((k) => !out.phases[k].epMoved)
  };
  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf8");
  console.log("OUT=" + OUT);
  console.log("summary=" + JSON.stringify(out.summary));
  for (const k of ["mermaid", "paragraph", "code", "formula", "table"]) {
    const p = out.phases[k];
    console.log(k, "ok=" + p.ok, "epMoved=" + p.epMoved, "previewChanged=" + p.previewChanged,
                "epSeries=" + JSON.stringify(p.epSeries), "delta=" + JSON.stringify(p.previewDelta));
  }
  console.log("follow=" + JSON.stringify(out.follow.previewToSourceWorks) + "/" + JSON.stringify(out.follow.sourceToPreviewWorks));
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[verify] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
