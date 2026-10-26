#!/usr/bin/env node
/* task-156 Step2 真机验收：引用块内交互（结构转换 / Enter / Backspace）
 *
 * 判据（Lead Step2）：Q 列=磁盘字节；Enter 前后行数（拆行/续列 +1，退列表 -1 层）；
 *   未涉及行逐字节不变；每条交互源码模式 + 预览模式各验一遍。
 * 场景：
 *   H1 引用段落内敲 `- ` ⇒ 转成列表项
 *   H2 引用段落内 Enter（段末）⇒ 拆行，行数 +1
 *   H3 引用列表项内 Enter ⇒ 续列，行数 +1，新 item
 *   H4 空列表项 Enter ⇒ 退出列表（该行变空引用段落）
 *   H5 非首列表项行首 Backspace ⇒ 合并到上一项，行数 -1
 *   H6 首列表项行首 Backspace ⇒ 退列表（去 marker），行数不变
 *   H7 列表后段落行首 Backspace ⇒ 合并进上一项最后一行，行数 -1
 *   S1/S2 源码模式：引用行内 Enter / 行首 Backspace（回归：源码面板行级逻辑不受影响）
 *
 * 用法：node quote-list-step2-probe.mjs --cdp http://127.0.0.1:9591 --kb <临时KB> --out <json>
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
  async evalJS(expr, { timeoutMs = 15000 } = {}) {
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
           quoteHTML: bq?String(bq.innerHTML).slice(0,400):"",
           quoteUL: pv?pv.querySelectorAll('blockquote ul, blockquote ol').length:0,
           quoteLI: pv?pv.querySelectorAll('blockquote li').length:0,
           lines: d && Array.isArray(d.lines) ? d.lines.slice() : null };
})()`;

/** 预览里把光标放到 targetText 的「开头(idx=0)」或「末尾」 */
const FOCUS_PREVIEW = (targetText, atEnd) => `(function(){
  var root=document.getElementById('preview'); if(!root) return {ok:false};
  var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT), n;
  while((n=tw.nextNode())){
    var txt=n.textContent||''; var at=txt.indexOf(${JSON.stringify(targetText)});
    if(at<0) continue;
    var host=n.parentElement; if(!host) continue;
    var idx=at+${JSON.stringify(atEnd ? targetText : "")}.length;
    var r=document.createRange(); r.setStart(n,Math.min(idx,txt.length)); r.setEnd(n,Math.min(idx,txt.length));
    var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
    try{(host.closest('[contenteditable="true"]')||host).focus();}catch(e){}
    return {ok:true,text:txt,isLi:!!host.closest('li')};
  }
  return {ok:false};
})()`;

const FOCUS_EMPTY_QUOTE_LI = `(function(){
  var root=document.getElementById('preview'); if(!root) return {ok:false};
  var lis=root.querySelectorAll('blockquote li');
  for(var i=0;i<lis.length;i++){
    var li=lis[i];
    if((li.textContent||'').length!==0) continue;
    var r=document.createRange(); r.setStart(li,0); r.collapse(true);
    var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
    try{(li.closest('[contenteditable="true"]')||li).focus();}catch(e){}
    return {ok:true,index:i,html:li.outerHTML.slice(0,80)};
  }
  return {ok:false};
})()`;

const FOCUS_SOURCE_LINE = (needle, atStart) => `(function(){
  var els=[].slice.call(document.querySelectorAll('#editor .-line-content'));
  for(var i=0;i<els.length;i++){
    var el=els[i]; if((el.textContent||'').indexOf(${JSON.stringify(needle)})<0) continue;
    el.focus(); var t=el.firstChild; var r=document.createRange();
    if(t&&t.nodeType===3){ var off=${JSON.stringify(atStart ? 0 : -1)}; r.setStart(t, off<0?t.textContent.length:off); r.setEnd(t,off<0?t.textContent.length:off); }
    else { r.selectNodeContents(el); r.collapse(${JSON.stringify(!!atStart)}); }
    var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
    return {ok:true,line:i+1,text:el.textContent};
  }
  return {ok:false};
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9591");
  const kb = String(args.kb || "");
  if (!kb) throw new Error("缺少 --kb");
  const docAbs = path.join(kb, "docs", "q.md");
  const pristine = fs.readFileSync(docAbs, "utf8");
  const pristineLines = pristine.split(/\r?\n/);
  const pristineQuote = pristineLines.filter((l) => l.startsWith(">"));

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp, target } = conn;
  const out = { startedAt: new Date().toISOString(), target: { id: target.id }, pristine, pristineLineCount: pristineLines.length - 1, steps: {} };

  async function resetAndOpen(mode) {
    fs.writeFileSync(docAbs, pristine);
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode(${JSON.stringify(mode)}); } catch(e){} return true; })()`);
    await cdp.waitFor(`(window.state||{}).viewMode === ${JSON.stringify(mode)}`, { timeout: 20000, label: mode });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/q.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/q.md" && !!window.state.doc', { timeout: 60000, label: "open" });
    await sleep(700);
  }
  async function waitDiskChange(timeout = 12000) {
    const t0 = Date.now();
    let disk = fs.readFileSync(docAbs, "utf8");
    while (disk === pristine && Date.now() - t0 < timeout) { await sleep(150); disk = fs.readFileSync(docAbs, "utf8"); }
    return { changed: disk !== pristine, waitMs: Date.now() - t0, disk: disk };
  }
  async function snap(label) {
    const disk = fs.readFileSync(docAbs, "utf8");
    const lines = disk.split(/\r?\n/);
    const quote = lines.filter((l) => l.startsWith(">"));
    const diffs = [];
    const n = Math.max(pristineQuote.length, quote.length);
    for (let i = 0; i < n; i++) if (pristineQuote[i] !== quote[i]) diffs.push({ i: i, before: pristineQuote[i], after: quote[i] });
    const st = await cdp.evalJS(READ);
    return { label: label, disk: disk, quoteLines: quote, changedLines: diffs,
             lineCount: lines.length - 1, pristineLineCount: pristineLines.length - 1,
             lineDelta: (lines.length - 1) - (pristineLines.length - 1),
             state: st };
  }
  async function keyEnter() {
    // 真实按键序列（仓库既有探针验证过：keyDown 带 text:'\r' 才会触发 beforeinput insertParagraph）
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: "\r", unmodifiedText: "\r" });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
  }
  async function keyTab(shift) {
    const mods = shift ? 8 : 0;
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9, modifiers: mods });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9, nativeVirtualKeyCode: 9, modifiers: mods });
  }
  async function keyBackspace() {
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8, nativeVirtualKeyCode: 8 });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8, nativeVirtualKeyCode: 8 });
  }

  console.log("[s2] connected; H1 reset/open");
  // H1 段落内敲 `- ` 转换
  await resetAndOpen("split");
  console.log("[s2] H1 opened; focus");
  out.steps.H1 = { focus: await cdp.evalJS(FOCUS_PREVIEW("前言段落一", false)) };
  await cdp.send("Input.insertText", { text: "- " });
  out.steps.H1.wait = await waitDiskChange();
  Object.assign(out.steps.H1, await snap("H1"));

  console.log("[s2] H1 done; H2");
  // H2 段落 Enter 拆行（段末）
  await resetAndOpen("split");
  out.steps.H2 = { focus: await cdp.evalJS(FOCUS_PREVIEW("前言段落一", true)) };
  await keyEnter();
  out.steps.H2.wait = await waitDiskChange();
  Object.assign(out.steps.H2, await snap("H2"));

  console.log("[s2] H2 done; H3");
  // H3 列表项 Enter 续列
  await resetAndOpen("split");
  out.steps.H3 = { focus: await cdp.evalJS(FOCUS_PREVIEW("q1 ten", true)) };
  await keyEnter();
  out.steps.H3.wait = await waitDiskChange();
  Object.assign(out.steps.H3, await snap("H3"));

  console.log("[s2] H3 done; H4");
  // H4 空列表项 Enter 退出列表（先拆出空项，再 Enter）
  await resetAndOpen("split");
  out.steps.H4 = { focus: await cdp.evalJS(FOCUS_PREVIEW("q1 ten", true)) };
  await keyEnter();
  out.steps.H4.first = await waitDiskChange();
  await sleep(900);   // 等块重渲 + restoreCursor 完成（否则第二次 Enter 用旧 AST 光标）
  out.steps.H4.dbgAfterFirst = await cdp.evalJS(`(function(){
    var eh=window.MemoriaEditHandler||{}; var sel=window.getSelection();
    return { cursorAST: eh.cursorAST||null,
             anchor: sel&&sel.anchorNode?String(sel.anchorNode.nodeName||sel.anchorNode.nodeType):null,
             litxt: (function(){var l=sel&&sel.anchorNode&&sel.anchorNode.closest?sel.anchorNode.closest('li'):null;return l?l.outerHTML.slice(0,80):null;})() };
  })()`);
  const diskBeforeSecond = fs.readFileSync(docAbs, "utf8");
  out.steps.H4.focusEmpty = await cdp.evalJS(FOCUS_EMPTY_QUOTE_LI);
  await keyEnter();
  await sleep(500);
  {
    const t0 = Date.now(); let disk2 = fs.readFileSync(docAbs, "utf8");
    while (disk2 === diskBeforeSecond && Date.now() - t0 < 10000) { await sleep(150); disk2 = fs.readFileSync(docAbs, "utf8"); }
    out.steps.H4.second = { changed: disk2 !== diskBeforeSecond, waitMs: Date.now() - t0, disk: disk2 };
  }
  Object.assign(out.steps.H4, await snap("H4"));

  console.log("[s2] H4 done; H5");
  // H5 非首列表项行首 Backspace ⇒ 合并上一项
  await resetAndOpen("split");
  out.steps.H5 = { focus: await cdp.evalJS(FOCUS_PREVIEW("q2 eleven", false)) };
  await keyBackspace();
  out.steps.H5.wait = await waitDiskChange();
  Object.assign(out.steps.H5, await snap("H5"));

  console.log("[s2] H5 done; H6");
  // H6 首列表项行首 Backspace ⇒ 退列表
  await resetAndOpen("split");
  out.steps.H6 = { focus: await cdp.evalJS(FOCUS_PREVIEW("q1 ten", false)) };
  await keyBackspace();
  out.steps.H6.wait = await waitDiskChange();
  Object.assign(out.steps.H6, await snap("H6"));

  console.log("[s2] H6 done; H7");
  // H7 列表后段落行首 Backspace ⇒ 合并进上一项
  await resetAndOpen("split");
  out.steps.H7 = { focus: await cdp.evalJS(FOCUS_PREVIEW("后记段落二", false)) };
  await keyBackspace();
  out.steps.H7.wait = await waitDiskChange();
  Object.assign(out.steps.H7, await snap("H7"));

  console.log("[s2] H7 done; J1/J2 Tab");
  await resetAndOpen("split");
  out.steps.J1 = { focus: await cdp.evalJS(FOCUS_PREVIEW("q2 eleven", true)) };
  await keyTab(false);
  out.steps.J1.wait = await waitDiskChange();
  Object.assign(out.steps.J1, await snap("J1"));
  const diskBeforeUn = fs.readFileSync(docAbs, "utf8");
  out.steps.J1.refocusForUnindent = await cdp.evalJS(FOCUS_PREVIEW("q2 eleven", true));
  await keyTab(true);
  await sleep(300);
  {
    const t1 = Date.now(); let diskU = fs.readFileSync(docAbs, "utf8");
    while (diskU === diskBeforeUn && Date.now() - t1 < 10000) { await sleep(150); diskU = fs.readFileSync(docAbs, "utf8"); }
    const quoteU = diskU.split(/\r?\n/).filter((l) => l.startsWith(">"));
    out.steps.J1.afterUnindent = { changed: diskU !== diskBeforeUn, disk: diskU, quoteLines: quoteU,
      backToPristineQuote: quoteU.length === pristineQuote.length && quoteU.every((l, i) => l === pristineQuote[i]),
      preview: await cdp.evalJS(READ) };
  }

  console.log("[s2] J done; S1");
  // S1/S2 源码模式回归：引用行内 Enter / 行首 Backspace（源码面板行级逻辑）
  await resetAndOpen("source");
  out.steps.S1 = { focus: await cdp.evalJS(FOCUS_SOURCE_LINE("> 前言段落一", false)) };
  await keyEnter();
  out.steps.S1.wait = await waitDiskChange();
  Object.assign(out.steps.S1, await snap("S1"));

  await resetAndOpen("source");
  out.steps.S2 = { focus: await cdp.evalJS(FOCUS_SOURCE_LINE("> 前言段落一", true)) };
  await keyBackspace();
  out.steps.S2.wait = await waitDiskChange();
  Object.assign(out.steps.S2, await snap("S2"));

  cdp.close();
  out.finishedAt = new Date().toISOString();
  const outPath = args.out ? path.resolve(String(args.out)) : null;
  if (outPath) fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf8");

  {
    const j1 = out.steps.J1 || {}, un = j1.afterUnindent || {};
    console.log("== J1 Tab 降级: 磁盘变化=" + (j1.wait ? j1.wait.changed : "?") + " 行数Δ=" + j1.lineDelta +
      " 引用行=" + JSON.stringify(j1.quoteLines) + " 预览ul/li=" + ((j1.state || {}).quoteUL + "/" + (j1.state || {}).quoteLI));
    console.log("== J2 Shift+Tab 升级: 磁盘变化=" + un.changed + " 回到原引用行=" + un.backToPristineQuote +
      " 引用行=" + JSON.stringify(un.quoteLines) + " 预览ul/li=" + ((un.preview || {}).quoteUL + "/" + (un.preview || {}).quoteLI));
  }
  for (const k of ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "S1", "S2"]) {
    const s = out.steps[k] || {};
    console.log("== " + k + " focus=" + JSON.stringify(s.focus));
    console.log("   磁盘变化=" + (s.wait ? s.wait.changed : "?") + " 行数Δ=" + s.lineDelta +
      " 改动引用行=" + JSON.stringify((s.changedLines || []).map((d) => [d.before, d.after])) +
      " 预览ul/li=" + (s.state ? s.state.quoteUL + "/" + s.state.quoteLI : "?"));
    console.log("   磁盘引用行=" + JSON.stringify(s.quoteLines));
  }
  console.log("OUT=" + outPath);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
