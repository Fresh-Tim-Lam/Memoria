#!/usr/bin/env node
/**
 * source-cut-probe.mjs —— task-150 真机取证：**源码区 Ctrl+X / Ctrl+C 是否可用**
 *
 * 每个用例测 6 件事（缺一不算"可用"）：
 *   ① 剪贴板内容（OS 级读回，先写 sentinel 证明是本次覆盖，不是旧值/双写）
 *   ② 编辑器 DOM 行是否真的变成期望（删除/不变）
 *   ③ `state.doc.body` 是否 == 期望 canonical
 *   ④ 保存后**磁盘字节**是否 == 期望（逐字节）
 *   ⑤ Ctrl+Z 一次是否恢复原状（单撤销单元）
 *   ⑥ 切到另一篇再切回，被剪切内容**是否回魂**（E30 同类断言）
 * 另外：预览区同选区 Ctrl+X 作为**对照**（应当正常 ⇒ 差异在源码区）。
 *
 * 用法：
 *   node source-cut-probe.mjs --cdp http://127.0.0.1:9585 --kb <临时KB根> \
 *        --cliphelper <source-cut-clipboard.ps1> --out <json>
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execFileSync } from 'node:child_process';

// ── args / utils ─────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) {
      const k = t.slice(2); const nxt = argv[i + 1];
      if (nxt && !nxt.startsWith('--')) { a[k] = nxt; i++; } else { a[k] = true; }
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
  constructor(ws) { this.ws = ws; this._id = 0; this._pending = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(url) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(url);
      const to = setTimeout(() => rej(new Error('CDP 连接超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('CDP 连接失败: ' + url)); });
    });
  }
  _on(data) {
    let m; try { m = JSON.parse(typeof data === 'string' ? data : String(data)); } catch { return; }
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
    if (r && r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error('evalJS 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]);
    }
    return r && r.result ? r.result.value : undefined;
  }
  async evalJS(expression, { awaitPromise = true, timeoutMs = 90000 } = {}) {
    const p = this.send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true, userGesture: true });
    if (!timeoutMs) return this._unwrap(p);
    const guard = new Promise((_, rej) => setTimeout(() => rej(new Error('evalJS 超时 ' + timeoutMs + 'ms: ' + expression.slice(0, 90))), timeoutMs));
    return this._unwrap(Promise.race([p, guard]));
  }
  async waitFor(expr, { timeout = 60000, interval = 120, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) {
      let v; try { v = await this.evalJS(expr, { timeoutMs: Math.max(3000, Math.min(20000, timeout)) }); } catch { v = false; }
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '') + ': ' + expr.slice(0, 110));
      await sleep(interval);
    }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

async function connectAppPage(cdpBase, perTryMs = 20000) {
  const list = await httpJson(cdpBase.replace(/\/$/, '') + '/json/list');
  const pages = (list || []).filter((t) => t && t.type === 'page' && t.webSocketDebuggerUrl);
  const score = (t) => {
    const u = String(t.url || '');
    if (/^http:\/\/127\.0\.0\.1:/.test(u)) return 0;
    if (/index\.html/.test(u)) return 1;
    if (/^about:blank/i.test(u)) return 9;
    return 5;
  };
  pages.sort((a, b) => score(a) - score(b));
  for (const t of pages) {
    let cdp = null;
    try {
      cdp = await CDP.connect(t.webSocketDebuggerUrl);
      await cdp.waitFor('!!(window.MemoriaApp && window.MemoriaApp.surface && typeof window.MemoriaApp.openFile === "function" && window.state)', { timeout: perTryMs, label: 'app@' + (t.url || t.id) });
      return { cdp, target: t };
    } catch (e) {
      try { cdp && cdp.close(); } catch { /* noop */ }
    }
  }
  throw new Error('所有 page target 都没有 MemoriaApp');
}

// ── 夹具模型（与 source-cut-fixture-gen.py 逐字一致）────────────────────────
const CUT_LINES = [
  '# cut 用例（task-150）',
  '',
  '第2行：AAA-001 这一段有足够长的文字用于单行选区测试。',
  '第3行：BBB-002 这一段也有足够长的文字。',
  '第4行：CCC-003 第四行内容。',
  '第5行：DDD-004 第五行内容。',
  '第6行：EEE-005 第六行内容。',
  '第7行：FFF-006 第七行内容（末行，带尾换行）。',
];
const SECOND_LINES = [
  '# 第二篇（对照）',
  '',
  '第二篇正文：SECOND-001，用于验证切文件后内容不回魂。',
  '第二篇第4行。',
];
const DOC = 'docs/cut.md';
const DOC2 = 'docs/second.md';

function bodyLF(lines) { return lines.join('\n') + '\n'; }   // 夹具都是"单尾换行"
function splitlinesLF(s) {
  const p = s.split('\n');
  if (s.length && s.endsWith('\n')) p.pop();
  return p.length ? p : [''];
}

// ── 用例（选区 1-based 行/列；列=行内字符偏移）──────────────────────────────
const CASES = [
  {
    // 注意：夹具第 2 行是空行 —— 选区必须落在非空行，否则会退化成"折叠空选区"（假用例）
    id: 'S1', area: 'source', op: 'cut', title: '源码区 · 单行剪切',
    sel: { lineA: 3, colA: 6, lineB: 3, colB: 18 },
  },
  {
    id: 'S2', area: 'source', op: 'cut', title: '源码区 · 跨行剪切',
    sel: { lineA: 3, colA: 10, lineB: 5, colB: 6 },
  },
  {
    id: 'S3', area: 'source', op: 'copy', title: '源码区 · 单行复制',
    sel: { lineA: 4, colA: 6, lineB: 4, colB: 15 },
  },
  {
    id: 'S4', area: 'source', op: 'copy', title: '源码区 · 跨行复制',
    sel: { lineA: 4, colA: 6, lineB: 6, colB: 5 },
  },
  {
    id: 'S5', area: 'source', op: 'cut', title: '源码区 · 整行跨行剪切（行3行首→行4行尾）',
    sel: { lineA: 3, colA: 0, lineB: 4, colB: CUT_LINES[3].length },
  },
  {
    id: 'P1', area: 'preview', op: 'cut', title: '预览区 · 跨块剪切（对照）',
    sel: { type: 'preview-cross', colA: 4, colB: 8 },
  },
  // 修复后才跑（--include-failure）：构造"写剪贴板失败"⇒ 必须可见报错且不删内容。
  {
    id: 'F1', area: 'source', op: 'cut', title: '源码区 · 写剪贴板失败（构造）',
    sel: { lineA: 3, colA: 6, lineB: 3, colB: 18 },
    injectFail: true, fixOnly: true,
  },
];

// ── 期望值（独立计算，不从 DOM 回读）───────────────────────────────────────
function expectedFor(c) {
  const lines = CUT_LINES.slice();
  if (c.area === 'source') {
    const li = c.sel.lineA - 1, lj = c.sel.lineB - 1;
    const a = c.sel.colA, b = c.sel.colB;
    let text, expLines;
    if (li === lj) {
      text = lines[li].slice(a, b);
      expLines = lines.slice();
      if (c.op === 'cut') expLines[li] = lines[li].slice(0, a) + lines[li].slice(b);
    } else {
      // 期望文本 = 把各段用换行符连接（相邻行时中间段为空，不能多补一个换行 —— 曾把 S5 期望值算错）
      text = [lines[li].slice(a)].concat(lines.slice(li + 1, lj)).concat([lines[lj].slice(0, b)]).join('\n');
      expLines = lines.slice();
      if (c.op === 'cut') {
        expLines.splice(li, lj - li + 1, lines[li].slice(0, a) + lines[lj].slice(b));
      }
    }
    if (c.op === 'copy') expLines = lines;
    // 失败路径：写剪贴板失败 ⇒ 约定"不删内容" ⇒ 文档期望保持原样（选区文本仍按模型计算，用于校验选区）
    if (c.injectFail) expLines = lines.slice();
    return { text, expLines, expBody: bodyLF(expLines) };
  }
  // preview 对照：期望只做"内容确实被删/剪贴板非空"的方向性判定（精确文本取决于预览 DOM 文本节点）
  return { text: null, expLines: null, expBody: null };
}

// ── 页面内：选区 ────────────────────────────────────────────────────────────
const SELECT_SOURCE = (lineA, colA, lineB, colB) => `(function(){
  var elA = document.querySelector('#line-${lineA} .-line-content');
  var elB = document.querySelector('#line-${lineB} .-line-content');
  if (!elA || !elB) return { ok:false, reason:'no line el' };
  function tn(el, col){
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    var acc = 0, n;
    while ((n = w.nextNode())) {
      var len = (n.textContent || '').length;
      if (acc + len >= col) return { node:n, off: col - acc };
      acc += len;
    }
    return { node: el, off: el.childNodes.length };
  }
  var a = tn(elA, ${colA}), b = tn(elB, ${colB});
  elA.focus();   // 先聚焦（split 模式下 focus 可能注入假光标），再设选区
  a = tn(elA, ${colA}); b = tn(elB, ${colB});
  var r = document.createRange(); r.setStart(a.node, a.off); r.setEnd(b.node, b.off);
  var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  function lineOf(node){ var el = node && (node.nodeType === 1 ? node : node.parentElement); var ln = el && el.closest('[data-line]'); return ln ? +(ln.dataset.line||0) : -1; }
  return { ok:true, text: s.toString(), collapsed: s.isCollapsed, mode: (window.state||{}).viewMode,
           startLine: lineOf(r.startContainer), endLine: lineOf(r.endContainer) };
})()`;

const SELECT_PREVIEW = `(function(){
  var blocks = [].slice.call(document.querySelectorAll('#preview .-src-block'))
    .filter(function(b){ return (b.textContent||'').trim().length > 20; });
  if (blocks.length < 2) return { ok:false, reason:'preview blocks < 2', n: blocks.length };
  function tn(el, col){
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    var acc = 0, n;
    while ((n = w.nextNode())) {
      var len = (n.textContent || '').length;
      if (acc + len >= col) return { node:n, off: col - acc };
      acc += len;
    }
    return null;
  }
  var a = tn(blocks[0], 4), b = tn(blocks[1], 8);
  if (!a || !b) return { ok:false, reason:'no text node' };
  var r = document.createRange(); r.setStart(a.node, a.off); r.setEnd(b.node, b.off);
  var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  try { document.getElementById('preview').focus(); } catch(e) {}
  return { ok:true, text: s.toString(), collapsed: s.isCollapsed, mode:(window.state||{}).viewMode };
})()`;

const READ_DOM = `(function(){
  var st = window.state || {}; var d = st.doc || null;
  return {
    editorLines: [].slice.call(document.querySelectorAll('#editor .-line-content')).map(function(el){ return el.textContent || ''; }),
    body: (d && typeof d.body === 'string') ? d.body : null,
    currentPath: st.currentPath || null,
    viewMode: st.viewMode || null,
    pending: (typeof window.__memoriaHasPendingEdits === 'function') ? window.__memoriaHasPendingEdits() : null,
    editMode: !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode),
  };
})()`;

// ── 输入事件 ────────────────────────────────────────────────────────────────
async function dispatchKey(cdp, key, code, vk, modifiers) {
  await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers });
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers });
}
const ctrlX = (cdp) => dispatchKey(cdp, 'x', 'KeyX', 88, 2);
const ctrlC = (cdp) => dispatchKey(cdp, 'c', 'KeyC', 67, 2);
const ctrlZ = (cdp) => dispatchKey(cdp, 'z', 'KeyZ', 90, 2);

// ── 剪贴板（Node 侧读 OS 剪贴板；先写 sentinel 证明"本次覆盖"）──────────────
function makeClipboard(cliphelper) {
  const tmp = path.join(os.tmpdir(), 'memoria_t150_clip_' + process.pid + '.txt');
  return {
    read() {
      execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', cliphelper, '-Out', tmp], { timeout: 15000 });
      try { return fs.readFileSync(tmp, 'utf8'); } catch { return null; }
    },
  };
}

const SENTINEL = '___T150_SENTINEL___';

// ── 等条件 ──────────────────────────────────────────────────────────────────
async function pollUntil(fn, { timeout = 12000, interval = 100 } = {}) {
  const t0 = Date.now();
  let last = null;
  for (;;) {
    last = await fn();
    if (last && last.ok) return { ok: true, waitMs: Date.now() - t0, last };
    if (Date.now() - t0 > timeout) return { ok: false, waitMs: Date.now() - t0, last };
    await sleep(interval);
  }
}
function linesEqual(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
function firstLineDiff(a, b) {
  const n = Math.max(a ? a.length : 0, b ? b.length : 0);
  for (let i = 0; i < n; i++) if ((a || [])[i] !== (b || [])[i]) return { index: i, got: (a || [])[i], exp: (b || [])[i] };
  return null;
}
function shortText(s, n = 60) { const t = String(s == null ? '' : s); return t.length > n ? t.slice(0, n) + '…' : t; }

// ── 主流程 ──────────────────────────────────────────────────────────────────
async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || 'http://127.0.0.1:9585');
  const kb = String(args.kb || '');
  const cliphelper = String(args.cliphelper || '');
  if (!kb || !cliphelper) throw new Error('缺少 --kb / --cliphelper');

  let conn = null; let lastErr = null;
  for (let i = 0; i < 90; i++) {
    try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); }
  }
  if (!conn) throw lastErr || new Error('CDP 无 app target');
  const { cdp, target } = conn;
  const clip = makeClipboard(cliphelper);

  const fixMode = args['fix-mode'] === true;        // 修复后跑：剪贴板要求精确 LF、且包含失败路径用例
  const meta = { startedAt: new Date().toISOString(), cdp: cdpBase, kb, fixMode, target: { id: target.id, url: target.url }, cases: [], env: {} };
  let failures = 0;

  const cutPath = path.join(kb, 'docs', 'cut.md');
  const secondPath = path.join(kb, 'docs', 'second.md');
  const pristineCut = fs.readFileSync(cutPath);
  const pristineSecond = fs.readFileSync(secondPath);
  const cutBody = bodyLF(CUT_LINES);
  const secondBody = bodyLF(SECOND_LINES);

  try {
    await cdp.send('Runtime.enable').catch(() => {});
    // 先确保剪贴板 API 可用（记录实际实现：后端 or 浏览器）
    meta.env.writeClipboardText = await cdp.evalJS('(typeof (window.MemoriaApp||{}).writeClipboardText === "function")');
    meta.env.editMode = (await cdp.evalJS(READ_DOM)).editMode;

    for (const c of CASES) {
      if (c.fixOnly && !fixMode) continue;           // 失败路径用例只在修复后跑（改前无接管，桩不会生效）
      const caseRec = { id: c.id, title: c.title, area: c.area, op: c.op, sel: c.sel, steps: {}, ok: true, failures: [] };
      meta.cases.push(caseRec);
      const fail = (dim, detail) => { caseRec.ok = false; failures++; caseRec.steps[dim] = false; caseRec.failures.push(dim + ': ' + shortText(JSON.stringify(detail), 300)); };

      // 重置磁盘 + 切到源码文档
      fs.writeFileSync(cutPath, pristineCut);
      fs.writeFileSync(secondPath, pristineSecond);
      const mode = c.area === 'preview' ? 'split' : 'source';
      await cdp.evalJS(`(function(){ try { window.MemoriaApp.surface.setMode(${JSON.stringify(mode)}); } catch(e){} return (window.state||{}).viewMode; })()`);
      await cdp.waitFor(`(window.state||{}).viewMode === ${JSON.stringify(mode)}`, { timeout: 20000, label: 'mode' });
      await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(DOC)} && !!window.state.doc`, { timeout: 60000, label: 'open' });
      await cdp.waitFor(`document.querySelectorAll('#editor .-line-content').length === ${CUT_LINES.length}`, { timeout: 30000, label: 'lines' });
      await sleep(300);

      const pre = await cdp.evalJS(READ_DOM);
      const exp = expectedFor(c);
      caseRec.pre = { body: pre.body, lines: pre.editorLines };

      // 期望值自检（防"夹具/模型"错）：源码区打开后行必须等于模型
      if (c.area === 'source' && !linesEqual(pre.editorLines, CUT_LINES)) {
        fail('modelCheck', firstLineDiff(pre.editorLines, CUT_LINES));
        continue;
      }
      if (pre.body !== cutBody) { fail('modelCheckBody', { got: shortText(pre.body), exp: shortText(cutBody) }); continue; }

      // 剪贴板 sentinel：证明"读回的是本次写入，不是旧值"
      await cdp.evalJS(`window.MemoriaApp.writeClipboardText(${JSON.stringify(SENTINEL)})`);
      await sleep(150);
      const clipBefore = clip.read();
      caseRec.clipBefore = clipBefore;
      if (clipBefore !== SENTINEL) fail('sentinelSetup', { clipBefore });

      // 选区
      const selInfo = c.area === 'preview'
        ? await cdp.evalJS(SELECT_PREVIEW)
        : await cdp.evalJS(SELECT_SOURCE(c.sel.lineA, c.sel.colA, c.sel.lineB, c.sel.colB));
      caseRec.selInfo = selInfo;
      if (!selInfo || !selInfo.ok) { fail('select', selInfo); continue; }
      if (c.area === 'source') {
        const singleLine = c.sel.lineA === c.sel.lineB;
        if (!singleLine) {
          // ⚠️ 记录一条重要事实：多 contenteditable 根选区上 `Selection.toString()` 会被截断到单根
          //    （S2/S4 实测：跨行选区 toString 只返回首行尾部）——这本身就是"原生 cut 失效"的机理旁证。
          caseRec.steps.selectRange = (selInfo.collapsed === false &&
            selInfo.startLine === c.sel.lineA && selInfo.endLine === c.sel.lineB);
          if (!caseRec.steps.selectRange) fail('selectRange', { got: selInfo, exp: { lineA: c.sel.lineA, lineB: c.sel.lineB } });
        } else if (selInfo.text !== exp.text) {
          fail('selectText', { got: selInfo.text, exp: exp.text });
        }
      }

      // 构造失败路径：临时让写剪贴板永远失败（不改 src，只在页面内打桩）
      if (c.injectFail) {
        // 注意：app.js 的 writeClipboardText 是**本地函数**（不是 MemoriaApp 上的方法），所以必须打桩它真正用的通道：
        //   ① 后端 RPC `clipboard_set_text`（bridge.api() 上的方法） ② navigator.clipboard.writeText ③ execCommand
        caseRec.failInject = await cdp.evalJS(`(function(){
          var api = window.MemoriaBridge && window.MemoriaBridge.api ? window.MemoriaBridge.api() : null;
          window.__t150_restore = {
            apiClip: (api && api.clipboard_set_text) ? api.clipboard_set_text.bind(api) : null,
            navWrite: (navigator.clipboard && navigator.clipboard.writeText) ? navigator.clipboard.writeText.bind(navigator.clipboard) : null,
            exec: document.execCommand ? document.execCommand.bind(document) : null,
          };
          if (api) api.clipboard_set_text = function(){ return Promise.resolve({ status: 'error', message: 'T150_INJECTED' }); };
          try { if (navigator.clipboard) navigator.clipboard.writeText = function(){ return Promise.reject(new Error('T150_INJECTED')); }; } catch (e) {}
          document.execCommand = function(){ return false; };
          return { api: !!(api && api.clipboard_set_text), nav: !!(navigator.clipboard), exec: true };
        })()`);
      }

      // 触发快捷键（真实 CDP 按键）
      if (c.op === 'cut') await ctrlX(cdp); else await ctrlC(cdp);
      await sleep(600);

      // 等 pending 收敛（异步剪贴板 + 渲染/保存防抖）
      await pollUntil(async () => {
        const d = await cdp.evalJS(READ_DOM);
        return { ok: d.pending === false, d };
      }, { timeout: 15000, interval: 150 });
      const after = await cdp.evalJS(READ_DOM);
      const clipAfter = clip.read();
      caseRec.after = { body: after.body, lines: after.editorLines, pending: after.pending };
      caseRec.clipAfter = clipAfter;

      // ① 剪贴板（记录 raw 与归一化；Windows 原生 cut/copy 用 CRLF，我们自己的接管写 LF）
      const clipNorm = typeof clipAfter === 'string' ? clipAfter.replace(/\r\n/g, '\n') : clipAfter;
      const clipExact = typeof clipAfter === 'string' && clipAfter === exp.text;
      const clipNormalized = typeof clipAfter === 'string' && clipNorm === exp.text;
      caseRec.clipRaw = clipAfter;
      caseRec.clipExact = clipExact;
      caseRec.clipNormalized = clipNormalized;
      let clipMatch;
      if (c.injectFail) {
        // 失败路径：根本不应写剪贴板 ⇒ 必须仍是 sentinel（证明没有"半写"）
        clipMatch = (clipAfter === SENTINEL);
      } else if (c.area === 'preview') {
        clipMatch = typeof clipAfter === 'string' && clipAfter.length > 0 && clipAfter !== SENTINEL;
      } else if (fixMode && c.op === 'cut') {
        // 剪切：我们**完全接管** ⇒ 必须精确 LF（与文档模型一致），不接受 CRLF
        clipMatch = clipExact;
      } else {
        // 复制：保持原生（保留富文本能力），只校验内容（Windows 原生用 CRLF，归一化比较）
        clipMatch = clipNormalized;
      }
      caseRec.steps.clipboard = clipMatch;
      if (!clipMatch) fail('clipboard', { got: shortText(clipAfter, 140), exp: shortText(c.area === 'source' ? exp.text : '<非空预览选区文本>', 140), exact: clipExact, normalized: clipNormalized });

      // ② 编辑器 DOM 行
      if (c.area === 'source') {
        const domMatch = linesEqual(after.editorLines, exp.expLines);
        caseRec.steps.domLines = domMatch;
        if (!domMatch) fail('domLines', firstLineDiff(after.editorLines, exp.expLines));
        // ③ body
        const bodyMatch = after.body === exp.expBody;
        caseRec.steps.body = bodyMatch;
        if (!bodyMatch) fail('body', { got: shortText(after.body), exp: shortText(exp.expBody) });
        // ④ 磁盘（逐字节；夹具 CRLF，body LF ⇒ 保存文本模式会写 CRLF）
        const expBytes = Buffer.from(exp.expBody.replace(/\n/g, '\r\n'), 'utf8');
        const diskPoll = await pollUntil(async () => {
          let buf; try { buf = fs.readFileSync(cutPath); } catch { return { ok: false }; }
          return { ok: buf.equals(expBytes), buf };
        }, { timeout: 15000, interval: 100 });
        caseRec.steps.disk = diskPoll.ok;
        caseRec.diskWaitMs = diskPoll.waitMs;
        if (!diskPoll.ok) {
          const got = fs.readFileSync(cutPath);
          fail('disk', { gotBytes: got.length, expBytes: expBytes.length, gotTail: got.slice(-8).toString('hex'), expTail: expBytes.slice(-8).toString('hex') });
        }
      } else {
        // 预览对照：只断言"剪贴板非空 + 正文变短"（精确文本由预览 DOM 决定）
        const bodyChanged = after.body !== cutBody;
        caseRec.steps.previewBodyChanged = bodyChanged;
        if (!bodyChanged) fail('previewBodyChanged', { got: shortText(after.body) });
      }

      // ④b 失败路径：内容必须【未删】+ 必须有可见报错（构造路径专用）
      if (c.injectFail) {
        const contentKept = linesEqual(after.editorLines, CUT_LINES) && after.body === cutBody;
        caseRec.steps.contentKeptOnFailure = contentKept;
        if (!contentKept) fail('contentKeptOnFailure', { lines: firstLineDiff(after.editorLines, CUT_LINES), body: shortText(after.body) });
        const visPoll = await pollUntil(async () => {
          const v = await cdp.evalJS(`(function(){
            var info = document.getElementById('status-info');
            var host = document.getElementById('-flash-host');
            var errs = document.querySelectorAll('.-flash-error');
            return {
              statusInfo: info ? (info.textContent || '') : null,
              statusErrorClass: !!(info && info.classList.contains('-status-error')),
              flashText: host ? (host.textContent || '') : null,
              flashErrorCount: errs.length,
            };
          })()`);
          const hit = !!(v && ((v.statusInfo && /剪|剪切|剪贴板|clipboard/i.test(v.statusInfo)) ||
            (v.flashText && /剪|剪切|剪贴板|clipboard/i.test(v.flashText)) || v.flashErrorCount > 0));
          return { ok: hit, v: v };
        }, { timeout: 2500, interval: 100 });
        caseRec.visibleErrorRaw = visPoll.last ? visPoll.last.v : null;
        caseRec.steps.visibleError = visPoll.ok;
        if (!visPoll.ok) fail('visibleError', { visible: shortText(JSON.stringify(visPoll.last && visPoll.last.v), 240) });
        caseRec.steps.clipboardStillSentinel = (clipAfter === SENTINEL);
        if (clipAfter !== SENTINEL) fail('clipboardStillSentinel', { got: shortText(clipAfter, 120) });
        // 复原打桩
        await cdp.evalJS(`(function(){
          var r = window.__t150_restore || {};
          var api = window.MemoriaBridge && window.MemoriaBridge.api ? window.MemoriaBridge.api() : null;
          if (api && r.apiClip) api.clipboard_set_text = r.apiClip;
          try { if (navigator.clipboard && r.navWrite) navigator.clipboard.writeText = r.navWrite; } catch (e) {}
          if (document.execCommand && r.exec) document.execCommand = r.exec;
          return true;
        })()`);
        // 失败路径不继续"撤销/回魂"断言（没有发生编辑）
        console.log(`[${c.id}] ${c.title}  ok=${caseRec.ok}  ` + Object.keys(caseRec.steps).map((k) => k + '=' + caseRec.steps[k]).join(' '));
        if (caseRec.failures.length) caseRec.failures.forEach((f) => console.log('    ✗ ' + f));
        continue;
      }

      // ⑤ Ctrl+Z 一次恢复
      await ctrlZ(cdp);
      await sleep(700);
      await pollUntil(async () => {
        const d = await cdp.evalJS(READ_DOM);
        return { ok: d.pending === false, d };
      }, { timeout: 15000, interval: 150 });
      const undone = await cdp.evalJS(READ_DOM);
      const expectUndoBody = cutBody;
      const undoBodyOk = undone.body === expectUndoBody;
      const undoLinesOk = c.area === 'source' ? linesEqual(undone.editorLines, CUT_LINES) : true;
      caseRec.steps.undo = !!(undoBodyOk && undoLinesOk);
      if (!caseRec.steps.undo) fail('undo', { bodyOk: undoBodyOk, linesOk: undoLinesOk, gotBody: shortText(undone.body) });
      caseRec.afterUndo = { body: undone.body, lines: undone.editorLines };

      // ⑥ 切文件再切回：不回魂（E30 同类）
      await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(DOC2)}, { skipNav: true })`);
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(DOC2)}`, { timeout: 30000, label: 'open2' });
      await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(DOC)}`, { timeout: 30000, label: 'openBack' });
      await sleep(400);
      const back = await cdp.evalJS(READ_DOM);
      const noResurrect = back.body === cutBody;   // 撤销后应为原样；若剪切内容回魂会 != 原样
      caseRec.steps.noResurrect = noResurrect;
      if (!noResurrect) fail('noResurrect', { got: shortText(back.body), exp: shortText(cutBody) });

      // 恢复干净状态给下一个用例
      fs.writeFileSync(cutPath, pristineCut);
      await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(DOC)}`, { timeout: 30000, label: 'reset' });

      console.log(`[${c.id}] ${c.title}  ok=${caseRec.ok}  ` + Object.keys(caseRec.steps).map((k) => k + '=' + caseRec.steps[k]).join(' '));
      if (caseRec.failures.length) caseRec.failures.forEach((f) => console.log('    ✗ ' + f));
    }
  } finally {
    cdp.close();
  }

  meta.finishedAt = new Date().toISOString();
  meta.failures = failures;
  meta.ok = failures === 0;
  const out = args.out ? path.resolve(String(args.out)) : null;
  if (out) { fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, JSON.stringify(meta, null, 2), 'utf8'); }
  console.log('\n=== SUMMARY === ok=' + meta.ok + ' failures=' + failures + ' cases=' + meta.cases.length);
  for (const c of meta.cases) {
    console.log('  ' + c.id + ' ' + c.title + '  ok=' + c.ok + '  ' + Object.keys(c.steps).map((k) => k + '=' + c.steps[k]).join(' '));
  }
  console.log('OUT=' + out);
  return meta.ok ? 0 : 1;
}

main().then((c) => process.exit(c)).catch((e) => { console.error('[probe] FATAL:', e && e.stack ? e.stack : String(e)); process.exit(2); });
