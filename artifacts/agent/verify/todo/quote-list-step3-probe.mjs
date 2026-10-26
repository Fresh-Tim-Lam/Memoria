#!/usr/bin/env node
/* task-156 Step3 真机验收：有序列表"数字保号"（编辑后仍是原序列）
 *
 * 场景（Q=磁盘字节；逐行 diff）：
 *   K1 引用内有序项 `10. ten` 末 Enter 拆项 ⇒ 10. / 新 11. / 原 `11. eleven` 不动 / 12. 不动
 *   K2 顶层有序项 `10. flat ten` 末 Enter 拆项（12730）⇒ 10. / 新 11. / 原 `11. flat eleven` 不动
 *   K3 顶层跨两个有序项选中删除（13468）⇒ 合并项保留 10.，11. 行被删，其余不动
 *   K4 顶层有序项内多行粘贴替换（13574）⇒ 合成项继承原号，未触碰的 `11. flat eleven` 不动
 *   K5 引用内跨两个有序项选中删除（13468 引用分支）⇒ 合并项保留 > 10.，> 12. 不动
 *   K6 源码模式：在 `11. flat eleven` 行内改一个字符 ⇒ 只有该行变，其余逐字节不变
 *
 * 用法：node quote-list-step3-probe.mjs --cdp http://127.0.0.1:9592 --kb <临时KB> --out <json>
 */
"use strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

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
  var pv=document.getElementById('preview');
  return { body:(d&&typeof d.body==='string')?d.body:null,
           lines: d && Array.isArray(d.lines) ? d.lines.slice() : null,
           quoteUL: pv?pv.querySelectorAll('blockquote ul, blockquote ol').length:0,
           quoteLI: pv?pv.querySelectorAll('blockquote li').length:0,
           listUL: pv?pv.querySelectorAll(':scope > ul, :scope > ol').length:0 };
})()`;

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

const SELECT_PREVIEW_SPAN = (fromText, toText) => `(function(){
  var root=document.getElementById('preview'); if(!root) return {ok:false};
  var tw=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
  var fromN=null,toN=null,n;
  while((n=tw.nextNode())){
    var txt=n.textContent||'';
    if(!fromN && txt.indexOf(${JSON.stringify(fromText)})>=0) fromN=n;
    if(fromN && !toN && txt.indexOf(${JSON.stringify(toText)})>=0) toN=n;
  }
  if(!fromN||!toN) return {ok:false};
  var r=document.createRange();
  r.setStart(fromN,(fromN.textContent||'').indexOf(${JSON.stringify(fromText)})+${JSON.stringify(fromText)}.length);
  r.setEnd(toN,(toN.textContent||'').lastIndexOf(${JSON.stringify(toText)}));
  var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
  return {ok:true,from:fromN.textContent,to:toN.textContent};
})()`;

const FOCUS_SOURCE_LINE = (needle, atStart) => `(function(){
  var els=[].slice.call(document.querySelectorAll('#editor .-line-content'));
  for(var i=0;i<els.length;i++){
    var el=els[i]; if((el.textContent||'').indexOf(${JSON.stringify(needle)})<0) continue;
    el.focus(); var t=el.firstChild; var r=document.createRange();
    if(t&&t.nodeType===3){ var off=${JSON.stringify(atStart ? 0 : -1)}; r.setStart(t,off<0?t.textContent.length:off); r.setEnd(t,off<0?t.textContent.length:off); }
    else { r.selectNodeContents(el); r.collapse(${JSON.stringify(!!atStart)}); }
    var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
    return {ok:true,line:i+1,text:el.textContent};
  }
  return {ok:false};
})()`;

function setWindowsClipboard(text) {
  // 通过 base64→UTF8 传值，避免引号/换行转义问题
  const b64 = Buffer.from(text, "utf8").toString("base64");
  const script = `$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${b64}')); Set-Clipboard -Value $t;`;
  const enc = Buffer.from(script, "utf16le").toString("base64");
  execFileSync("powershell", ["-NoProfile", "-EncodedCommand", enc], { stdio: "ignore" });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9592");
  const kb = String(args.kb || "");
  if (!kb) throw new Error("缺少 --kb");
  const docAbs = path.join(kb, "docs", "q.md");
  const pristine = fs.readFileSync(docAbs, "utf8");
  const pristineLines = pristine.split(/\r?\n/);
  const pristineQuote = pristineLines.filter((l) => l.startsWith(">"));
  const pristineFlat = pristineLines.filter((l) => /^\d+\.\s/.test(l));

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp, target } = conn;
  const out = { startedAt: new Date().toISOString(), target: { id: target.id }, pristine, steps: {} };

  async function resetAndOpen(mode) {
    fs.writeFileSync(docAbs, pristine);
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode(${JSON.stringify(mode)}); } catch(e){} return true; })()`);
    await cdp.waitFor(`(window.state||{}).viewMode === ${JSON.stringify(mode)}`, { timeout: 20000, label: mode });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/q.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/q.md" && !!window.state.doc', { timeout: 60000, label: "open" });
    await sleep(700);
  }
  async function waitDiskChange(baseline, timeout = 12000) {
    const t0 = Date.now();
    let disk = fs.readFileSync(docAbs, "utf8");
    while (disk === baseline && Date.now() - t0 < timeout) { await sleep(150); disk = fs.readFileSync(docAbs, "utf8"); }
    // 等保存/尾巴归一收敛（结构编辑可能触发第二次写盘；task-147 尾换行归一也算一次）
    await sleep(800);
    disk = fs.readFileSync(docAbs, "utf8");
    return { changed: disk !== baseline, waitMs: Date.now() - t0, disk: disk };
  }
  function snapDisk(disk) {
    const lines = disk.split(/\r?\n/);
    return {
      disk: disk,
      lines: lines,
      quoteLines: lines.filter((l) => l.startsWith(">")),
      flatLines: lines.filter((l) => /^\d+\.\s/.test(l)),
      lineCount: lines.length - 1,
      pristineLineCount: pristineLines.length - 1,
    };
  }
  /** 未触碰行必须按原顺序仍是磁盘行的子序列（防止"被重编号/丢行"） */
  function subsequence(needle, hay) {
    let j = 0;
    for (let i = 0; i < hay.length && j < needle.length; i++) if (hay[i] === needle[j]) j++;
    return j === needle.length;
  }
  const keyEnter = async () => {
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: "\r", unmodifiedText: "\r" });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
  };
  const keyDelete = async () => {
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46 });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46 });
  };
  const keyCtrlV = async () => {
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "v", code: "KeyV", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "v", code: "KeyV", windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, modifiers: 2 });
  };

  // K1 引用内 10. Enter
  await resetAndOpen("split");
  out.steps.K1 = { focus: await cdp.evalJS(FOCUS_PREVIEW("ten", true)) };
  await keyEnter();
  out.steps.K1.wait = await waitDiskChange(pristine);
  Object.assign(out.steps.K1, snapDisk(out.steps.K1.wait.disk));
  out.steps.K1.untouchedPreserved = subsequence(
    pristineQuote.filter((l) => l !== "> 10. ten"), out.steps.K1.quoteLines);

  // K2 顶层 10. flat ten Enter（12730）
  await resetAndOpen("split");
  out.steps.K2 = { focus: await cdp.evalJS(FOCUS_PREVIEW("flat ten", true)) };
  await keyEnter();
  out.steps.K2.wait = await waitDiskChange(pristine);
  Object.assign(out.steps.K2, snapDisk(out.steps.K2.wait.disk));
  out.steps.K2.untouchedPreserved = subsequence(
    pristineFlat.filter((l) => l !== "10. flat ten"), out.steps.K2.flatLines);

  // K3 顶层跨 10./11. 选中删除（13468）
  await resetAndOpen("split");
  out.steps.K3 = { sel: await cdp.evalJS(SELECT_PREVIEW_SPAN("flat ten", "flat eleven")) };
  await keyDelete();
  out.steps.K3.wait = await waitDiskChange(pristine);
  Object.assign(out.steps.K3, snapDisk(out.steps.K3.wait.disk));

  // K4 顶层 10. 项内多行粘贴（13574）
  await resetAndOpen("split");
  out.steps.K4 = { focus: await cdp.evalJS(FOCUS_PREVIEW("flat ten", true)) };
  try {
    setWindowsClipboard("X\nY");
    await keyCtrlV();
    out.steps.K4.wait = await waitDiskChange(pristine);
    Object.assign(out.steps.K4, snapDisk(out.steps.K4.wait.disk));
    out.steps.K4.ok = true;
  } catch (e) {
    out.steps.K4.ok = false;
    out.steps.K4.error = String(e && e.message ? e.message : e);
  }

  // K5 引用内跨 10./11. 选中删除（13468 引用分支）
  await resetAndOpen("split");
  out.steps.K5 = { sel: await cdp.evalJS(SELECT_PREVIEW_SPAN("ten", "eleven")) };
  await keyDelete();
  out.steps.K5.wait = await waitDiskChange(pristine);
  Object.assign(out.steps.K5, snapDisk(out.steps.K5.wait.disk));

  // K6 源码模式：改 `11. flat eleven` 行内一个字符
  await resetAndOpen("source");
  out.steps.K6 = { focus: await cdp.evalJS(FOCUS_SOURCE_LINE("11. flat eleven", false)) };
  await cdp.send("Input.insertText", { text: "S" });
  out.steps.K6.wait = await waitDiskChange(pristine);
  Object.assign(out.steps.K6, snapDisk(out.steps.K6.wait.disk));
  out.steps.K6.otherLinesUnchanged = subsequence(
    pristineFlat.filter((l) => l !== "11. flat eleven"), out.steps.K6.flatLines);

  cdp.close();
  out.finishedAt = new Date().toISOString();
  const outPath = args.out ? path.resolve(String(args.out)) : null;
  if (outPath) fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf8");

  for (const k of ["K1", "K2", "K3", "K4", "K5", "K6"]) {
    const s = out.steps[k] || {};
    console.log("== " + k + " 磁盘变化=" + (s.wait ? s.wait.changed : "?") + " 行数Δ=" + ((s.lineCount || 0) - (s.pristineLineCount || 0)));
    if (s.quoteLines) console.log("   引用行=" + JSON.stringify(s.quoteLines));
    if (s.flatLines) console.log("   顶层有序行=" + JSON.stringify(s.flatLines));
    if (k === "K4") console.log("   ok=" + s.ok + " err=" + JSON.stringify(s.error || null));
    if (s.untouchedPreserved !== undefined) console.log("   未触碰行保序=" + s.untouchedPreserved);
    if (s.otherLinesUnchanged !== undefined) console.log("   其它行不变=" + s.otherLinesUnchanged);
  }
  console.log("OUT=" + outPath);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
