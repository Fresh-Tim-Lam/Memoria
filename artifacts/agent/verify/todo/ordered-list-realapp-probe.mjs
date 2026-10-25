#!/usr/bin/env node
/* task-157 真机探针：有序列表 start>1 重编号是否**可达写盘**
 *
 * 三条场景（每条独立重置磁盘）：
 *  A 源码模式编辑：在 `10. ten` 行内改一个字符 → 保存 → 数字是否变？
 *  B 预览模式编辑：在预览列表项 `ten` 内改一个字符 → 保存 → 数字是否变？（命中 commit→spliceBlockSource→generateBlock）
 *  C 预览模式编辑引用块普通段落：若 commit(blockquote) 触发，引用内 `> 10.` 是否变 `> 1.`？
 *
 * 判据：逐字节比较磁盘（不是长度）；同时记录 state.doc.body。
 * 用法：node ordered-list-realapp-probe.mjs --cdp http://127.0.0.1:9587 --kb <临时KB> --out <json>
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
    } catch (e) { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}

const READ = `(function(){
  var st = window.state || {}; var d = st.doc || null;
  return {
    currentPath: st.currentPath || null,
    viewMode: st.viewMode || null,
    body: (d && typeof d.body === 'string') ? d.body : null,
    editMode: !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode),
    pending: (typeof window.__memoriaHasPendingEdits === 'function') ? window.__memoriaHasPendingEdits() : null,
  };
})()`;

/** 在预览里把选区放到"第一个含 targetText 的可编辑文本节点"末尾（用于真实输入） */
const FOCUS_PREVIEW_TEXT = (targetText, mode) => `(function(){
  var root = document.getElementById('preview');
  if (!root) return { ok:false, reason:'no preview' };
  var tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  var n;
  while ((n = tw.nextNode())) {
    var txt = n.textContent || '';
    if (txt.indexOf(${JSON.stringify(targetText)}) < 0) continue;
    var host = n.parentElement;
    if (!host) continue;
    ${mode === "li" ? "if (!host.closest('li')) continue;" : "if (host.closest('li')) continue;"}
    var idx = txt.indexOf(${JSON.stringify(targetText)}) + ${JSON.stringify(targetText)}.length;
    var r = document.createRange(); r.setStart(n, Math.min(idx, txt.length)); r.setEnd(n, Math.min(idx, txt.length));
    var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    try { host.closest('[contenteditable="true"]')?.focus(); } catch(e) {}
    return { ok:true, text: txt, isLi: !!host.closest('li'), blockIndex: (function(){ var b = host.closest('[data--block-index]'); return b ? b.getAttribute('data--block-index') : null; })() };
  }
  return { ok:false, reason:'text not found' };
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
    try {
      const txt = fs.readFileSync(absPath, "utf8");
      if (txt.indexOf(needle) >= 0) return { ok: true, waitMs: Date.now() - t0, text: txt };
    } catch { /* noop */ }
    await sleep(180);
  }
  try { return { ok: false, waitMs: Date.now() - t0, text: fs.readFileSync(absPath, "utf8") }; } catch { return { ok: false, waitMs: Date.now() - t0, text: null }; }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9587");
  const kb = String(args.kb || "");
  if (!kb) throw new Error("缺少 --kb");
  const docAbs = path.join(kb, "docs", "ord.md");
  const pristine = fs.readFileSync(docAbs, "utf8");

  let conn = null; let lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp, target } = conn;
  const out = { startedAt: new Date().toISOString(), target: { id: target.id, url: target.url }, pristineTail: pristine.split(/\r?\n/).slice(0, 12), steps: {} };
  try {
    async function resetAndOpen(mode) {
      fs.writeFileSync(docAbs, pristine);
      await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode(${JSON.stringify(mode)}); } catch(e){} return true; })()`);
      await cdp.waitFor(`(window.state||{}).viewMode === ${JSON.stringify(mode)}`, { timeout: 20000, label: mode });
      await cdp.evalJS('window.MemoriaApp.openFile("docs/ord.md", { skipNav: true })');
      await cdp.waitFor('window.state.currentPath === "docs/ord.md" && !!window.state.doc', { timeout: 60000, label: "open" });
      await sleep(700);
    }

    // ── A. 源码模式：在 `10. ten` 行内改一个字符 ──
    await resetAndOpen("source");
    out.steps.A = { focus: await cdp.evalJS(FOCUS_SOURCE_LINE("10. ten")) };
    await cdp.send("Input.insertText", { text: "X" });
    await sleep(400);
    const aSaved = await waitSaved(cdp, docAbs, "tenX");
    out.steps.A.diskAfter = aSaved.text;
    out.steps.A.stateBodyAfter = (await cdp.evalJS(READ)).body;
    out.steps.A.numberPreserved = !!aSaved.text && aSaved.text.indexOf("10. tenX") >= 0 && aSaved.text.indexOf("11. eleven") >= 0;

    // ── B. 预览模式：在列表项 ten 内改一个字符 ──
    await resetAndOpen("split");
    out.steps.B = { editMode: (await cdp.evalJS(READ)).editMode, focus: await cdp.evalJS(FOCUS_PREVIEW_TEXT("ten", "li")) };
    await cdp.send("Input.insertText", { text: "Y" });
    await sleep(500);
    const bSaved = await waitSaved(cdp, docAbs, "tenY");
    out.steps.B.diskAfter = bSaved.text;
    out.steps.B.stateBodyAfter = (await cdp.evalJS(READ)).body;
    out.steps.B.numberPreserved = !!bSaved.text && bSaved.text.indexOf("10. tenY") >= 0 && bSaved.text.indexOf("11. eleven") >= 0;
    out.steps.B.renumbered = !!bSaved.text && /(^|\n)1\. tenY/.test(bSaved.text) && /(^|\n)2\. eleven/.test(bSaved.text);

    // ── C. 预览模式：在引用块普通段落里改一个字符（看 commit(blockquote) 是否连带重编号内层有序列表）──
    await resetAndOpen("split");
    out.steps.C = { focus: await cdp.evalJS(FOCUS_PREVIEW_TEXT("前言段落", "p")) };
    if (out.steps.C.focus && out.steps.C.focus.ok) {
      await cdp.send("Input.insertText", { text: "W" });
      await sleep(500);
      const cSaved = await waitSaved(cdp, docAbs, "前言段落W");
      out.steps.C.diskAfter = cSaved.text;
      out.steps.C.stateBodyAfter = (await cdp.evalJS(READ)).body;
      out.steps.C.quoteNumberPreserved = !!cSaved.text && cSaved.text.indexOf("> 10. qten") >= 0 && cSaved.text.indexOf("> 11. qeleven") >= 0;
      out.steps.C.quoteRenumbered = !!cSaved.text && /(^|\r?\n)> 1\. qten/.test(cSaved.text);
    }
  } finally {
    cdp.close();
  }
  out.finishedAt = new Date().toISOString();
  const outPath = args.out ? path.resolve(String(args.out)) : null;
  if (outPath) fs.writeFileSync(outPath, JSON.stringify(out, null, 2), "utf8");

  const A = out.steps.A || {}, B = out.steps.B || {}, C = out.steps.C || {};
  console.log("=== A 源码模式编辑（对照）===");
  console.log("  focus=" + JSON.stringify(A.focus) + "  数字保持=" + A.numberPreserved);
  console.log("  disk=" + JSON.stringify(String(A.diskAfter || "").split(/\r?\n/).slice(2, 6)));
  console.log("=== B 预览模式编辑（可达性核心）===");
  console.log("  editMode=" + B.editMode + "  focus=" + JSON.stringify(B.focus) + "  数字保持=" + B.numberPreserved + "  重编号=" + B.renumbered);
  console.log("  disk=" + JSON.stringify(String(B.diskAfter || "").split(/\r?\n/).slice(2, 6)));
  console.log("=== C 预览模式编辑引用块普通段落（引用内有序列表）===");
  console.log("  focus=" + JSON.stringify(C.focus) + "  引用数字保持=" + C.quoteNumberPreserved + "  引用重编号=" + C.quoteRenumbered);
  console.log("  disk 尾部=" + JSON.stringify(String(C.diskAfter || "").split(/\r?\n/).slice(-6)));
  console.log("OUT=" + outPath);
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => { console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2); });
