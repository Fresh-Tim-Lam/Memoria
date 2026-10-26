#!/usr/bin/env node
/* 既有 R0 判定（HEAD 版 app.js，不带 Step1 改动）：
 *   预览模式编辑「多 child 引用块」的**第 2 段** / **引用内列表项** ⇒ 是否覆盖第 1 段并**写盘**？
 *
 * 判据：只看【磁盘字节】（task-157 方法论）；并 reopen 验证持久化。
 * 用法：node quote-corrupt-head-probe.mjs --cdp http://127.0.0.1:9589 --kb <临时KB> --out <json>
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
    if (r && r.exceptionDetails) throw new Error("evalJS 异常: " + String((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text).slice(0, 200));
    return r && r.result ? r.result.value : undefined;
  }
  async evalJS(expr, { timeoutMs = 60000 } = {}) {
    const p = this.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
    if (!timeoutMs) return this._unwrap(p);
    const guard = new Promise((_, rej) => setTimeout(() => rej(new Error("evalJS 超时")), timeoutMs));
    return this._unwrap(Promise.race([p, guard]));
  }
  async waitFor(expr, { timeout = 60000, label = "" } = {}) {
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
  var st=window.state||{}, d=st.doc||null;
  var pv=document.getElementById('preview'); var bq=pv?pv.querySelector('blockquote'):null;
  return { body:(d&&typeof d.body==='string')?d.body:null, currentPath:st.currentPath||null,
           quoteHTML: bq?String(bq.innerHTML).slice(0,300):"" };
})()`;
const FOCUS_PREVIEW_TEXT = (targetText) => `(function(){
  var root=document.getElementById('preview'); if(!root) return {ok:false};
  var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT), n;
  while((n=tw.nextNode())){
    var txt=n.textContent||''; if(txt.indexOf(${JSON.stringify(targetText)})<0) continue;
    var host=n.parentElement; if(!host) continue;
    var idx=txt.indexOf(${JSON.stringify(targetText)})+${JSON.stringify(targetText)}.length;
    var r=document.createRange(); r.setStart(n,Math.min(idx,txt.length)); r.setEnd(n,Math.min(idx,txt.length));
    var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
    try{(host.closest('[contenteditable="true"]')||host).focus();}catch(e){}
    return {ok:true,text:txt,isLi:!!host.closest('li')};
  }
  return {ok:false};
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9589");
  const kb = String(args.kb || "");
  if (!kb) throw new Error("缺少 --kb");
  const docAbs = path.join(kb, "docs", "q.md");
  const pristine = fs.readFileSync(docAbs, "utf8");

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp, target } = conn;
  const out = { startedAt: new Date().toISOString(), target: { id: target.id }, pristine, steps: {} };

  async function openFresh() {
    fs.writeFileSync(docAbs, pristine);
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode('split'); } catch(e){} return true; })()`);
    await cdp.waitFor('(window.state||{}).viewMode === "split"', { timeout: 20000, label: "split" });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/q.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/q.md" && !!window.state.doc', { timeout: 60000, label: "open" });
    await sleep(700);
  }
  /** 输入后等【磁盘字节变化】（最多 15s），返回磁盘内容（未变则=pristine） */
  async function typeAndWaitDisk(text) {
    await cdp.send("Input.insertText", { text });
    const t0 = Date.now();
    for (;;) {
      const cur = fs.readFileSync(docAbs, "utf8");
      if (cur !== pristine) return { changed: true, waitMs: Date.now() - t0, disk: cur };
      if (Date.now() - t0 > 15000) return { changed: false, waitMs: Date.now() - t0, disk: cur };
      await sleep(150);
    }
  }
  async function reopenAndRead() {
    await cdp.evalJS('window.MemoriaApp.openFile("docs/q.md", { skipNav: true })');
    await sleep(900);
    return await cdp.evalJS(READ);
  }
  const diffQuote = (disk) => {
    const pr = pristine.split(/\r?\n/).filter((l) => l.startsWith(">"));
    const af = disk.split(/\r?\n/).filter((l) => l.startsWith(">"));
    return { before: pr, after: af, identical: pr.length === af.length && pr.every((l, i) => l === af[i]) };
  };

  // 场景 C：编辑第 2 段（后记段落二）
  await openFresh();
  const cFocus = await cdp.evalJS(FOCUS_PREVIEW_TEXT("后记段落二"));
  const cRes = await typeAndWaitDisk("Z");
  const cDiskDiff = diffQuote(cRes.disk);
  out.steps.C = {
    focus: cFocus, diskChanged: cRes.changed, waitMs: cRes.waitMs,
    stateBody: (await cdp.evalJS(READ)).body,
    diskQuoteDiff: cDiskDiff,
    disk: cRes.disk,
  };
  out.steps.C.reopen = await reopenAndRead();

  // 场景 B：编辑引用内列表项（q1 ten）
  await openFresh();
  const bFocus = await cdp.evalJS(FOCUS_PREVIEW_TEXT("q1 ten"));
  const bRes = await typeAndWaitDisk("Y");
  const bDiskDiff = diffQuote(bRes.disk);
  out.steps.B = {
    focus: bFocus, diskChanged: bRes.changed, waitMs: bRes.waitMs,
    stateBody: (await cdp.evalJS(READ)).body,
    diskQuoteDiff: bDiskDiff,
    disk: bRes.disk,
  };
  out.steps.B.reopen = await reopenAndRead();

  // 对照 A：编辑第 1 段（首段）应正常追加
  await openFresh();
  const aFocus = await cdp.evalJS(FOCUS_PREVIEW_TEXT("前言段落一"));
  const aRes = await typeAndWaitDisk("A");
  out.steps.A = {
    focus: aFocus, diskChanged: aRes.changed, waitMs: aRes.waitMs,
    stateBody: (await cdp.evalJS(READ)).body,
    diskQuoteDiff: diffQuote(aRes.disk),
    disk: aRes.disk,
  };

  cdp.close();
  out.finishedAt = new Date().toISOString();
  const outPath = args.out ? path.resolve(String(args.out)) : null;
  if (outPath) fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf8");

  for (const k of ["A", "B", "C"]) {
    const s = out.steps[k] || {};
    const d = s.diskQuoteDiff || {};
    console.log("== " + k + " focus=" + JSON.stringify(s.focus));
    console.log("   磁盘变化=" + s.diskChanged + " 等待=" + s.waitMs + "ms");
    console.log("   before=" + JSON.stringify(d.before));
    console.log("   after =" + JSON.stringify(d.after));
    if (s.reopen) console.log("   reopen.body=" + JSON.stringify(s.reopen.body));
  }
  console.log("OUT=" + outPath);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
