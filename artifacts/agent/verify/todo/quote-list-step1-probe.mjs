#!/usr/bin/env node
/* task-156 Step1 真机验收：引用块内"既有段落又有列表"两种 child 上编辑，互不破坏。
 *
 * 判据（Lead 第1步验收，R0 级）：
 *   · 每次编辑后**保存到磁盘**，逐字节比较：未被编辑的 `> ` 行必须完全不变；
 *     被编辑的 child 不应导致**其它 child** 被重写/丢失。
 *   A 预览模式：编辑引用内段落（child=paragraph，跨 list 相邻）→ list 行逐字节不变
 *   B 预览模式：编辑引用内列表项（child=list，跨多行）→ 段落/其它项/编号逐字节不变
 *   C 预览模式：编辑引用内第二段的段落（list 之后）→ list 行不变
 *   D 预览模式：跨两个列表项选中删除 → 合并为一项，其它 child 不变（step1: deleteSelectionMulti 路径）
 *   E 源码模式：在引用段落行/列表行内各改一个字符 → 保存后仅该行变，其余逐字节不变
 *   F Enter 行为确认（Lead 第③条）：引用段落内 / 引用列表项内按 Enter，是否"完全无反应"
 *
 * 用法：node quote-list-step1-probe.mjs --cdp http://127.0.0.1:9588 --kb <临时KB> --out <json>
 */
"use strict";
import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith("--")) {
      const k = t.slice(2); const nxt = argv[i + 1];
      if (nxt && !nxt.startsWith("--")) { a[k] = nxt; i++; } else a[k] = true;
    } else a._.push(t);
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
    if (m.id == null) return;
    const p = this._pending.get(m.id); if (!p) return;
    this._pending.delete(m.id);
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this._id; this._pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
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
    for (;;) {
      let v; try { v = await this.evalJS(expr); } catch { v = false; }
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error("等待超时 " + label);
      await sleep(120);
    }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}
async function connectAppPage(cdpBase) {
  const list = await httpJson(cdpBase.replace(/\/$/, "") + "/json/list");
  const pages = (list || []).filter((t) => t && t.type === "page" && t.webSocketDebuggerUrl);
  for (const t of pages) {
    let cdp = null;
    try {
      cdp = await CDP.connect(t.webSocketDebuggerUrl);
      await cdp.waitFor('!!(window.MemoriaApp && window.state && typeof window.MemoriaApp.openFile === "function")', { timeout: 20000, label: "app" });
      return { cdp, target: t };
    } catch { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}

const READ = `(function(){
  var st = window.state || {}; var d = st.doc || null;
  var pv = document.getElementById('preview');
  var quoteUL = 0, quoteLI = 0, quoteHTML = "";
  if (pv) {
    var qs = pv.querySelectorAll('blockquote ul, blockquote ol');
    quoteUL = qs.length;
    var lis = pv.querySelectorAll('blockquote li');
    quoteLI = lis.length;
    var bq = pv.querySelector('blockquote');
    quoteHTML = bq ? String(bq.innerHTML).slice(0, 300) : "";
  }
  return { currentPath: st.currentPath || null, viewMode: st.viewMode || null,
           body: (d && typeof d.body === 'string') ? d.body : null,
           quoteUL: quoteUL, quoteLI: quoteLI, quoteHTML: quoteHTML,
           editMode: !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode) };
})()`;

/** 在预览里把选区放到指定文本末尾（limitText 用于多个匹配时选第 N 个） */
const FOCUS_PREVIEW_TEXT = (targetText) => `(function(){
  var root = document.getElementById('preview'); if (!root) return { ok:false };
  var tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); var n;
  while ((n = tw.nextNode())) {
    var txt = n.textContent || '';
    if (txt.indexOf(${JSON.stringify(targetText)}) < 0) continue;
    var host = n.parentElement; if (!host) continue;
    var idx = txt.indexOf(${JSON.stringify(targetText)}) + ${JSON.stringify(targetText)}.length;
    var r = document.createRange(); r.setStart(n, Math.min(idx, txt.length)); r.setEnd(n, Math.min(idx, txt.length));
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    try { (host.closest('[contenteditable="true"]') || host).focus(); } catch (e) {}
    return { ok:true, text: txt, isLi: !!host.closest('li') };
  }
  return { ok:false };
})()`;

/** 在预览里选 "fromText 的末尾" → "toText 的末尾"（跨节点选区，用于跨项删除） */
const SELECT_PREVIEW_SPAN = (fromText, toText) => `(function(){
  var root = document.getElementById('preview'); if (!root) return { ok:false };
  var tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  var fromN = null, toN = null, n;
  while ((n = tw.nextNode())) {
    var txt = n.textContent || '';
    if (!fromN && txt.indexOf(${JSON.stringify(fromText)}) >= 0) fromN = n;
    if (!toN && fromN && txt.indexOf(${JSON.stringify(toText)}) >= 0) toN = n;
  }
  if (!fromN || !toN) return { ok:false };
  var r = document.createRange();
  r.setStart(fromN, (fromN.textContent || '').indexOf(${JSON.stringify(fromText)}) + ${JSON.stringify(fromText)}.length);
  r.setEnd(toN, (toN.textContent || '').lastIndexOf(${JSON.stringify(toText)}));
  var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  return { ok:true, from: fromN.textContent, to: toN.textContent };
})()`;

const FOCUS_SOURCE_LINE = (needle) => `(function(){
  var lines = [].slice.call(document.querySelectorAll('#editor .-line-content'));
  for (var i = 0; i < lines.length; i++) {
    var el = lines[i];
    if ((el.textContent || '').indexOf(${JSON.stringify(needle)}) < 0) continue;
    el.focus();
    var t = el.firstChild; var r = document.createRange();
    if (t && t.nodeType === 3) { r.setStart(t, t.textContent.length); r.setEnd(t, t.textContent.length); }
    else { r.selectNodeContents(el); r.collapse(false); }
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    return { ok:true, line: i + 1, text: el.textContent };
  }
  return { ok:false };
})()`;

async function waitSaved(cdp, absPath, needle, timeout = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try { const txt = fs.readFileSync(absPath, "utf8"); if (txt.indexOf(needle) >= 0) return { ok: true, text: txt }; } catch { /* noop */ }
    await sleep(180);
  }
  try { return { ok: false, text: fs.readFileSync(absPath, "utf8") }; } catch { return { ok: false, text: null }; }
}
const linesOf = (txt) => String(txt == null ? "" : txt).split(/\r?\n/);
const quoteLines = (txt) => linesOf(txt).filter((l) => l.startsWith(">"));

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9588");
  const kb = String(args.kb || "");
  if (!kb) throw new Error("缺少 --kb");
  const docAbs = path.join(kb, "docs", "q.md");
  const pristine = fs.readFileSync(docAbs, "utf8");
  const pristineQuote = quoteLines(pristine);

  let conn = null; let lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp, target } = conn;
  const out = { startedAt: new Date().toISOString(), target: { id: target.id, url: target.url },
                pristineQuote, steps: {} };
  const log = (k, v) => { if (v !== undefined) out.steps[k] = v; if (out.steps[k] == null) out.steps[k] = {}; return out.steps[k]; };

  async function resetAndOpen(mode) {
    fs.writeFileSync(docAbs, pristine);
    await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode(${JSON.stringify(mode)}); } catch(e){} return true; })()`);
    await cdp.waitFor(`(window.state||{}).viewMode === ${JSON.stringify(mode)}`, { timeout: 20000, label: mode });
    await cdp.evalJS('window.MemoriaApp.openFile("docs/q.md", { skipNav: true })');
    await cdp.waitFor('window.state.currentPath === "docs/q.md" && !!window.state.doc', { timeout: 60000, label: "open" });
    await sleep(700);
  }
  const after = async (needle, label) => {
    // task-157 方法论：判定"是否写盘"必须等**磁盘任意变化**，不能等目标 needle
    // （旧写法在"写错行"时 needle 永不出现 ⇒ 把"已经写坏盘"误判为未保存）。
    const t0 = Date.now();
    let disk = fs.readFileSync(docAbs, "utf8");
    let changed = disk !== pristine;
    while (!changed && Date.now() - t0 < 15000) {
      await sleep(150);
      disk = fs.readFileSync(docAbs, "utf8");
      changed = disk !== pristine;
    }
    const af = quoteLines(disk);
    const diffs = [];
    const n = Math.max(pristineQuote.length, af.length);
    for (let i = 0; i < n; i++) {
      if (pristineQuote[i] !== af[i]) diffs.push({ i: i, before: pristineQuote[i], after: af[i] });
    }
    return {
      saved: changed, diskChanged: changed, disk: disk,
      quoteLinesAfter: af,
      changedLines: diffs,
      changedCount: diffs.length,
      targetLineChanged: changed && diffs.some((d) => String(d.after || "").indexOf(needle) >= 0),
      quoteIdentical: pristineQuote.length === af.length && pristineQuote.every((l, i) => l === af[i]),
      stateBody: (await cdp.evalJS(READ)).body,
      preview: (await cdp.evalJS(READ)),
    };
  };

  // ── A. 预览：编辑引用内**段落**（两侧都有 list）──
  await resetAndOpen("split");
  log("A", { focus: await cdp.evalJS(FOCUS_PREVIEW_TEXT("前言段落一")) });
  await cdp.send("Input.insertText", { text: "A" });
  await sleep(400);
  Object.assign(log("A"), await after("前言段落一A", "A"));

  // ── B. 预览：编辑引用内**列表项**（list child 跨多行）──
  await resetAndOpen("split");
  log("B", { focus: await cdp.evalJS(FOCUS_PREVIEW_TEXT("q1 ten")) });
  await cdp.send("Input.insertText", { text: "B" });
  await sleep(400);
  Object.assign(log("B"), await after("q1 tenB", "B"));

  // ── C. 预览：编辑 list **之后**的段落（child 顺序 段落,list,段落,list）──
  await resetAndOpen("split");
  log("C", { focus: await cdp.evalJS(FOCUS_PREVIEW_TEXT("后记段落二")) });
  await cdp.send("Input.insertText", { text: "C" });
  await sleep(400);
  Object.assign(log("C"), await after("后记段落二C", "C"));

  // ── C3. 预览：编辑第 3 段（尾段段落三）──
  await resetAndOpen("split");
  log("C3", { focus: await cdp.evalJS(FOCUS_PREVIEW_TEXT("尾段段落三")) });
  await cdp.send("Input.insertText", { text: "C3" });
  await sleep(400);
  Object.assign(log("C3"), await after("尾段段落三C3", "C3"));

  // ── D. 预览：跨两个列表项选中删除（应合并为一项，其它 child 不变）──
  await resetAndOpen("split");
  log("D", { sel: await cdp.evalJS(SELECT_PREVIEW_SPAN("q1 ten", "q2 eleven")) });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46, key: "Delete", code: "Delete" });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", windowsVirtualKeyCode: 46, nativeVirtualKeyCode: 46, key: "Delete", code: "Delete" });
  await sleep(500);
  {
    const d0 = Date.now();
    let diskD = fs.readFileSync(docAbs, "utf8");
    while (diskD === pristine && Date.now() - d0 < 15000) { await sleep(150); diskD = fs.readFileSync(docAbs, "utf8"); }
    const afD = quoteLines(diskD);
    log("D").after = {
      diskChanged: diskD !== pristine, disk: diskD,
      quoteLinesAfter: afD,
      changedCount: Math.max(pristineQuote.length, afD.length) -
        pristineQuote.filter((l, i) => l === afD[i]).length,
      stateBody: (await cdp.evalJS(READ)).body,
      preview: await cdp.evalJS(READ),
    };
  }

  // ── E. 源码模式：分别改引用段落行 / 列表行 ──
  await resetAndOpen("source");
  log("E", { focus1: await cdp.evalJS(FOCUS_SOURCE_LINE("前言段落一")) });
  await cdp.send("Input.insertText", { text: "S" });
  await sleep(400);
  Object.assign(log("E"), await after("前言段落一S", "E"));
  await resetAndOpen("source");
  log("E2", { focus2: await cdp.evalJS(FOCUS_SOURCE_LINE("> - q1 ten")) });
  await cdp.send("Input.insertText", { text: "T" });
  await sleep(400);
  Object.assign(log("E2"), await after("q1 tenT", "E2"));

  // ── F. Enter 行为确认：引用段落内 / 引用列表项内 ──
  await resetAndOpen("split");
  const beforeF = fs.readFileSync(docAbs, "utf8");
  log("F", { focusPara: await cdp.evalJS(FOCUS_PREVIEW_TEXT("前言段落一")) });
  await cdp.send("Input.dispatchKeyEvent", { type: "rawKeyDown", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, key: "Enter", code: "Enter" });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, key: "Enter", code: "Enter" });
  await sleep(700);
  const afterF = fs.readFileSync(docAbs, "utf8");
  log("F").after = { diskChanged: afterF !== beforeF, disk: afterF,
    stateBody: (await cdp.evalJS(READ)).body, preview: await cdp.evalJS(READ) };
  await resetAndOpen("split");
  const beforeF2 = fs.readFileSync(docAbs, "utf8");
  log("F2", { focusLi: await cdp.evalJS(FOCUS_PREVIEW_TEXT("q2 eleven")) });
  await cdp.send("Input.dispatchKeyEvent", { type: "rawKeyDown", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, key: "Enter", code: "Enter" });
  await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, key: "Enter", code: "Enter" });
  await sleep(700);
  const afterF2 = fs.readFileSync(docAbs, "utf8");
  log("F2").after = { diskChanged: afterF2 !== beforeF2, disk: afterF2, stateBody: (await cdp.evalJS(READ)).body };

  cdp.close();
  out.finishedAt = new Date().toISOString();
  const outPath = args.out ? path.resolve(String(args.out)) : null;
  if (outPath) fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf8");

  // 简洁汇总
  const summary = (k) => {
    const s = out.steps[k] || {};
    return k + ": 磁盘保存=" + !!s.saved + " 引用行逐字节不变=" + s.quoteIdentical +
      " 预览 ul/li=" + (s.preview ? s.preview.quoteUL + "/" + s.preview.quoteLI : "?");
  };
  for (const k of ["A", "B", "C", "C3", "E", "E2"]) console.log(summary(k));
  for (const k of ["A", "B", "C", "C3", "E", "E2"]) {
    const s = out.steps[k] || {};
    console.log("   Q[" + k + "]: 磁盘变化=" + s.diskChanged + " 改动行数=" + s.changedCount +
      " 目标行命中=" + s.targetLineChanged + " changed=" + JSON.stringify(s.changedLines));
  }
  const D = out.steps.D || {};
  console.log("D 跨项删除: sel=" + JSON.stringify(D.sel) + " disk=" + JSON.stringify(String(D.after && D.after.disk).split(/\r?\n/).filter((l) => l.startsWith(">"))));
  const F = out.steps.F || {};
  console.log("F Enter@引用段落: diskChanged=" + (F.after && F.after.diskChanged) + " body=" + JSON.stringify(String(F.after && F.after.stateBody)));
  const F2 = out.steps.F2 || {};
  console.log("F2 Enter@引用列表项: diskChanged=" + (F2.after && F2.after.diskChanged) + " body=" + JSON.stringify(String(F2.after && F2.after.stateBody)));
  console.log("OUT=" + outPath);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
