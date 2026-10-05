#!/usr/bin/env node
/**
 * cdp.mjs —— 显示子系统探针：极简 CDP 客户端 + 探针驱动（零新依赖）
 *
 * 用 Node 内置的全局 `WebSocket` / `fetch`（Node >= 22）直连 Edge 的 CDP，
 * 不需要 selenium / playwright / puppeteer，不 npm install。
 *
 * 用法：
 *   node scripts/benchmark/surface/cdp.mjs --selftest
 *   node scripts/benchmark/surface/cdp.mjs --probe --url http://127.0.0.1:8643/ \
 *        --kb-root <kb 目录> --cases <cases.json> --out <raw.json> [--port 9333] [--screenshots]
 *
 * 关键字（受信任输入）说明：
 *   打字一律走 `Input.dispatchKeyEvent`（keyDown + keyUp，`text` 带字符）⇒ 浏览器产生**真实**
 *   `keydown` / `beforeinput`（true trusted event），而不是 `el.value=` / `dispatchEvent(new Event(...))`
 *   那种伪造输入。这是测契约 C3「打字当帧可见」的前提。
 */

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// ─────────────────────────────────────────────────────────────────────────────
// 1. Edge 可执行文件定位
// ─────────────────────────────────────────────────────────────────────────────
const EDGE_CANDIDATES = [
  process.env.MEMORIA_EDGE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);

function findEdge() {
  for (const p of EDGE_CANDIDATES) {
    try { if (fs.existsSync(p)) return p; } catch { /* noop */ }
  }
  throw new Error('找不到 msedge.exe；可用环境变量 MEMORIA_EDGE 指定。');
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. 极简 CDP 客户端
// ─────────────────────────────────────────────────────────────────────────────
class CDP {
  constructor(ws) {
    this.ws = ws;
    this._id = 0;
    this._pending = new Map();
    this._listeners = new Map();
    this.logs = [];
    ws.addEventListener('message', (ev) => this._onMessage(ev.data));
  }

  static connect(wsUrl) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl);
      const to = setTimeout(() => reject(new Error('CDP WebSocket 连接超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); resolve(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); reject(new Error('CDP WebSocket 连接失败: ' + wsUrl)); });
    });
  }

  _onMessage(data) {
    let msg;
    try { msg = JSON.parse(typeof data === 'string' ? data : String(data)); } catch { return; }
    if (msg.id != null) {
      const p = this._pending.get(msg.id);
      if (!p) return;
      this._pending.delete(msg.id);
      if (msg.error) p.reject(new Error(msg.method + ' -> ' + JSON.stringify(msg.error)));
      else p.resolve(msg.result);
      return;
    }
    if (msg.method) {
      const arr = this._listeners.get(msg.method);
      if (arr) for (const fn of arr) { try { fn(msg.params); } catch { /* noop */ } }
    }
  }

  on(event, fn) {
    if (!this._listeners.has(event)) this._listeners.set(event, []);
    this._listeners.get(event).push(fn);
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this._id;
      this._pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  waitEvent(event, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
      const to = setTimeout(() => reject(new Error('等待事件超时: ' + event)), timeoutMs);
      const fn = (params) => { clearTimeout(to); resolve(params); };
      this.on(event, fn);
    });
  }

  /** Runtime.evaluate -> 值（awaitPromise + returnByValue）。表达式异常 -> 抛错。 */
  async evalJS(expression, { awaitPromise = true } = {}) {
    const r = await this.send('Runtime.evaluate', {
      expression, awaitPromise, returnByValue: true, userGesture: true,
    });
    if (r && r.exceptionDetails) {
      const d = r.exceptionDetails;
      const msg = (d.exception && (d.exception.description || d.exception.value)) || d.text || 'eval error';
      throw new Error('evalJS 异常: ' + String(msg).split('\n')[0]);
    }
    return r && r.result ? r.result.value : undefined;
  }

  /** 轮询表达式直至返回真值。 */
  async waitFor(expression, { timeout = 45000, interval = 150, label = '' } = {}) {
    const t0 = Date.now();
    let lastErr = null;
    for (;;) {
      try {
        const v = await this.evalJS(expression);
        if (v) return v;
      } catch (e) { lastErr = e; }
      if (Date.now() - t0 > timeout) {
        throw new Error('waitFor 超时' + (label ? '(' + label + ')' : '') + ': ' + expression +
          (lastErr ? ' | last err: ' + lastErr.message : ''));
      }
      await sleep(interval);
    }
  }

  /**
   * 受信任文本输入：逐字符 keyDown(text) + keyUp。
   * keyDown 带 `text` ⇒ Blink 走编辑管线，派发真实的 `beforeinput`（可被应用 preventDefault 拦截）。
   */
  async typeText(text) {
    for (const ch of String(text)) {
      const cp = ch.codePointAt(0);
      const isLetter = /[a-zA-Z]/.test(ch);
      const isDigit = /[0-9]/.test(ch);
      const code = isLetter ? 'Key' + ch.toUpperCase() : (isDigit ? 'Digit' + ch : '');
      const vk = isLetter ? ch.toUpperCase().charCodeAt(0) : (isDigit ? cp : cp);
      const down = { type: 'keyDown', text: ch, unmodifiedText: ch, key: ch };
      const up = { type: 'keyUp', key: ch };
      if (code) { down.code = code; up.code = code; }
      if (Number.isFinite(vk)) { down.windowsVirtualKeyCode = vk; down.nativeVirtualKeyCode = vk; up.windowsVirtualKeyCode = vk; up.nativeVirtualKeyCode = vk; }
      await this.send('Input.dispatchKeyEvent', down);
      await this.send('Input.dispatchKeyEvent', up);
    }
  }

  /** 受信任的命名按键（如 Escape / Enter）。 */
  async pressKey(key, { code = '', vk = 0 } = {}) {
    const down = { type: 'keyDown', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
    const up = { type: 'keyUp', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
    await this.send('Input.dispatchKeyEvent', down);
    await this.send('Input.dispatchKeyEvent', up);
  }

  /** 备用：execCommand('insertText')（非受信任；用于 typeText 失效时的对照）。 */
  async insertTextByExecCommand(text) {
    return await this.evalJS(`document.execCommand('insertText', false, ${JSON.stringify(String(text))})`);
  }

  async screenshot(filePath) {
    const r = await this.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(filePath, Buffer.from(r.data, 'base64'));
    return filePath;
  }

  close() { try { this.ws.close(); } catch { /* noop */ } }
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function js(v) { return JSON.stringify(v); }

// ─────────────────────────────────────────────────────────────────────────────
// 3. Edge 启动 + 目标发现
// ─────────────────────────────────────────────────────────────────────────────
async function httpJson(url, timeoutMs = 2000) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    return await r.json();
  } finally { clearTimeout(to); }
}

async function launchEdge({ headless = true, port } = {}) {
  const edgePath = findEdge();
  const cdpPort = port || (9222 + Math.floor(Math.random() * 3000));
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'memoria-probe-edge-'));
  const args = [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-background-networking',
    '--remote-allow-origins=*',
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${userDataDir}`,
    'about:blank',
  ];
  const proc = spawn(edgePath, args, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d.toString(); });
  proc.on('error', () => { /* noop */ });

  // 等 /json/version 就绪
  const base = `http://127.0.0.1:${cdpPort}`;
  const t0 = Date.now();
  let version = null;
  for (;;) {
    try { version = await httpJson(base + '/json/version'); if (version && version.webSocketDebuggerUrl) break; }
    catch { /* not up yet */ }
    if (Date.now() - t0 > 20000) {
      try { proc.kill(); } catch { /* noop */ }
      throw new Error('Edge CDP 未在 20s 内就绪。stderr: ' + stderr.slice(0, 800));
    }
    await sleep(200);
  }

  // 找一个 page 目标
  let wsUrl = null;
  let list = await httpJson(base + '/json/list').catch(() => []);
  let page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!page) {
    try {
      const created = await fetch(base + '/json/new?about:blank', { method: 'PUT' }).then((r) => r.json());
      page = created && created.webSocketDebuggerUrl ? created : null;
    } catch { /* noop */ }
  }
  wsUrl = page ? page.webSocketDebuggerUrl : (version.webSocketDebuggerUrl || null);
  if (!wsUrl) { try { proc.kill(); } catch { /* noop */ } throw new Error('拿不到 webSocketDebuggerUrl'); }

  return {
    proc, port: cdpPort, userDataDir, wsUrl,
    browser: version.Browser || 'Edge',
    cleanup() {
      try { proc.kill(); } catch { /* noop */ }
      try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { /* noop */ }
    },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. 页面内探针助手（整体 stringify 后在页面 eval，闭包内只用页面全局）
// ─────────────────────────────────────────────────────────────────────────────
function PAGE_HELPERS() {
  window.__probe = (function () {
    function blocks() { return Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block')); }
    function txt(el) { return el ? (el.textContent || '') : ''; }
    function findBlock(substr) {
      var bs = blocks();
      for (var i = 0; i < bs.length; i++) { if (txt(bs[i]).indexOf(substr) >= 0) return bs[i]; }
      return null;
    }
    function blockByIndex(bi) { return document.querySelector('#preview .-src-block[data--block-index="' + bi + '"]'); }

    // 镜像 app.js `_getViewTopSrcLine`：首屏第一个（bottom >= 容器顶）块的源码行
    function firstScreenBlock(mode) {
      mode = mode || (window.state && window.state.viewMode) || 'preview';
      var pane = document.getElementById('preview-pane');
      var ed = document.getElementById('editor-pane');
      if ((mode === 'source' || mode === 'split') && ed) {
        var ct0 = ed.getBoundingClientRect().top;
        var lines = ed.querySelectorAll('.-line');
        for (var i = 0; i < lines.length; i++) {
          if (lines[i].getBoundingClientRect().bottom >= ct0) {
            return { pane: 'source', start: +(lines[i].dataset.line || 0) || null, end: +(lines[i].dataset.line || 0) || null, text: txt(lines[i]).slice(0, 80) };
          }
        }
      }
      if (!pane) return null;
      var ct = pane.getBoundingClientRect().top;
      var bs = pane.querySelectorAll('[data--src-line]');
      for (var j = 0; j < bs.length; j++) {
        if (bs[j].getBoundingClientRect().bottom >= ct) {
          var s = +(bs[j].dataset.SrcLine || 0);
          var e = +(bs[j].dataset.SrcLineEnd || s);
          return { pane: 'preview', start: s, end: e, text: txt(bs[j]).slice(0, 80) };
        }
      }
      return null;
    }

    function topSrcLine(mode) { var b = firstScreenBlock(mode); return b ? b.start : null; }
    function previewScrollTop() { var p = document.getElementById('preview-pane'); return p ? Math.round(p.scrollTop) : null; }

    function setCaretIn(blockEl, offset) {
      if (!blockEl) return { ok: false, reason: 'no-block' };
      var walker = document.createTreeWalker(blockEl, NodeFilter.SHOW_TEXT, null);
      var acc = 0, node = null, off = 0, n;
      while ((n = walker.nextNode())) {
        var len = (n.nodeValue || '').length;
        if (acc + len >= offset) { node = n; off = offset - acc; break; }
        acc += len;
      }
      if (!node) {
        var w2 = document.createTreeWalker(blockEl, NodeFilter.SHOW_TEXT, null);
        var last = null;
        while ((n = w2.nextNode())) last = n;
        node = last; off = last ? (last.nodeValue || '').length : 0;
      }
      var pv = document.getElementById('preview');
      if (pv && pv.focus) { try { pv.focus({ preventScroll: true }); } catch (e) { pv.focus(); } }
      var sel = window.getSelection();
      sel.removeAllRanges();
      var r = document.createRange();
      if (node) { r.setStart(node, off); } else { r.setStart(blockEl, 0); }
      r.collapse(true);
      sel.addRange(r);
      return { ok: !!node };
    }

    function caretMap() {
      var sel = window.getSelection();
      if (!sel || !sel.anchorNode || !window.MemoriaMapper) return null;
      var a = window.MemoriaMapper.domToAst(sel.anchorNode, sel.anchorOffset);
      return a ? { blockIndex: a.blockIndex, nodePath: a.nodePath, offset: a.offset } : null;
    }

    function srcLineText(lineNo) {
      var d = window.state && window.state.doc;
      if (!d || !d.lines) return null;
      return d.lines[lineNo - 1] != null ? d.lines[lineNo - 1] : null;
    }

    // 选定目标块 + 放置光标（offset 可为数字或 'end'）
    function setupBlock(substr, offset) {
      var el = findBlock(substr);
      if (!el) return { ok: false, reason: 'block-not-found', substr: substr };
      var bi = parseInt(el.getAttribute('data--block-index'), 10);
      var srcLine = parseInt(el.getAttribute('data--src-line'), 10);
      var off = (offset === 'end') ? txt(el).length : (offset || 0);
      var set = setCaretIn(el, off);
      window.__probe._bi = bi;
      window.__probe._match = substr;
      // 注意：增量重渲（reRenderBlock→renderRange）会**替换**块节点，而 `data--src-line` 由
      // `stampBlockLines` 打、行数不变时被跳过 ⇒ 编辑后新节点**没有**该属性。故此处先记下行号。
      window.__probe._srcLine = srcLine;
      var cm = caretMap();
      return {
        ok: true, blockIndex: bi, srcLine: srcLine, offset: off,
        caretSet: set.ok, caretMap: cm,
        caretMapsToBlock: !!(cm && cm.blockIndex === bi),
        blockTextLen: txt(el).length,
        blockTextHead: txt(el).slice(0, 80),
      };
    }

    // 按 blockIndex 重新定位（reRenderBlock 会替换 DOM 节点 ⇒ 不能缓存元素引用）
    function snapshotBlock(probeChar) {
      var bi = window.__probe._bi;
      var el = blockByIndex(bi);
      if (!el) return { ok: false, reason: 'block-gone', blockIndex: bi };
      var attrNow = el.getAttribute('data--src-line');           // 编辑后可能为 null（见 setupBlock 注释）
      var srcLine = (attrNow != null && !isNaN(parseInt(attrNow, 10)))
        ? parseInt(attrNow, 10) : window.__probe._srcLine;
      var dom = txt(el);
      var src = srcLineText(srcLine);
      var out = {
        ok: true, blockIndex: bi, srcLine: srcLine,
        srcLineAttrNow: attrNow == null ? null : String(attrNow),
        srcLineFromCaptured: (attrNow == null),
        domText: dom.slice(0, 160), srcLineText: src == null ? null : src.slice(0, 160),
        domLen: dom.length, srcLineLen: src == null ? null : src.length,
      };
      if (probeChar) {
        out.domHasChar = dom.indexOf(probeChar) >= 0;
        out.srcHasChar = src != null && src.indexOf(probeChar) >= 0;
        out.domStartsWithChar = dom.charAt(0) === probeChar;
        out.srcStartsWithChar = src != null && src.charAt(0) === probeChar;
      }
      return out;
    }

    function scrollBlockToTop(substr) {
      var el = findBlock(substr);
      if (!el) return false;
      el.scrollIntoView({ block: 'start' });
      return true;
    }

    // 预览滚动容器状态（判断"是否已到文档末尾被钳制"）
    function scrollInfo() {
      var p = document.getElementById('preview-pane');
      if (!p) return null;
      return {
        scrollTop: Math.round(p.scrollTop),
        scrollHeight: p.scrollHeight,
        clientHeight: p.clientHeight,
        maxScroll: Math.max(0, p.scrollHeight - p.clientHeight),
        clampedAtBottom: p.scrollTop >= (p.scrollHeight - p.clientHeight - 2),
      };
    }

    // 找源码行 L 所属块，并给出它在视口内的位置与可见性
    function blockInfoForLine(L) {
      var pane = document.getElementById('preview-pane');
      if (!pane) return null;
      var bs = pane.querySelectorAll('[data--src-line]');
      for (var i = 0; i < bs.length; i++) {
        var s = +(bs[i].dataset.SrcLine || 0);
        var e = +(bs[i].dataset.SrcLineEnd || s);
        if (s <= L && e >= L) {
          var r = bs[i].getBoundingClientRect();
          var pr = pane.getBoundingClientRect();
          return {
            start: s, end: e, text: txt(bs[i]).slice(0, 80),
            relTop: Math.round(r.top - pr.top), relBottom: Math.round(r.bottom - pr.top),
            visible: r.bottom > pr.top && r.top < pr.bottom,
          };
        }
      }
      return null;
    }

    function docLines() { return (window.state && window.state.doc && window.state.doc.lines) ? window.state.doc.lines.length : null; }
    function docBody() { return (window.state && window.state.doc) ? window.state.doc.body : null; }
    function headingLine(pattern) {
      var d = window.state && window.state.doc;
      if (!d || !d.lines) return null;
      for (var i = 0; i < d.lines.length; i++) {
        if (String(d.lines[i]).trim() === pattern) return i + 1;
      }
      return null;
    }

    // 性能插桩：包裹 MemoriaEditSync.insertText，记录 keydown→真源更新 的时延
    function installPerf() {
      if (window.__probePerf) return 'already';
      var ES = window.MemoriaEditSync;
      if (!ES || typeof ES.insertText !== 'function') return 'no-editsync';
      var orig = ES.insertText;
      window.__probePerf = { edits: [], lastKeyT: null };
      var pv = document.getElementById('preview');
      if (pv) {
        pv.addEventListener('keydown', function () { window.__probePerf.lastKeyT = performance.now(); }, true);
      }
      ES.insertText = function () {
        var t0 = performance.now();
        var r = orig.apply(this, arguments);
        var t1 = performance.now();
        var kt = window.__probePerf.lastKeyT;
        window.__probePerf.edits.push({ insertMs: t1 - t0, fromKeyMs: (kt != null ? t1 - kt : null) });
        return r;
      };
      return 'installed';
    }
    function perfEdits() { return window.__probePerf ? window.__probePerf.edits.slice() : []; }

    return {
      blocks: blocks, findBlock: findBlock, txt: txt,
      firstScreenBlock: firstScreenBlock, topSrcLine: topSrcLine,
      previewScrollTop: previewScrollTop, setCaretIn: setCaretIn, caretMap: caretMap,
      setupBlock: setupBlock, snapshotBlock: snapshotBlock, scrollBlockToTop: scrollBlockToTop,
      scrollInfo: scrollInfo, blockInfoForLine: blockInfoForLine,
      docLines: docLines, docBody: docBody, headingLine: headingLine,
      installPerf: installPerf, perfEdits: perfEdits,
      editMode: function () { var E = window.MemoriaEditHandler; return E ? { editMode: E.editMode, composing: E._composing, blockEditMode: !!E.blockEditMode } : null; },
      viewMode: function () { return window.state ? window.state.viewMode : null; },
    };
  })();
  return 'ok';
}

// 点击视图切换按钮（应用真实入口 setViewMode）
async function clickView(cdp, mode) {
  const ok = await cdp.evalJS(
    `(function(){var b=document.querySelector('.-view-btn[data-view=' + ${JSON.stringify(JSON.stringify(mode))} + ']');if(!b)return false;b.click();return true;})()`
  );
  return ok;
}

async function waitScrollSettled(cdp, { stableReads = 3, interval = 120, timeout = 6000 } = {}) {
  const t0 = Date.now();
  let last = null, stable = 0;
  for (;;) {
    const cur = await cdp.evalJS(`window.__probe.previewScrollTop()`);
    if (cur === last) stable++; else stable = 0;
    last = cur;
    if (stable >= stableReads) return cur;
    if (Date.now() - t0 > timeout) return cur;
    await sleep(interval);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. selftest：证明 CDP 连得上 Edge，且受信任输入可用
// ─────────────────────────────────────────────────────────────────────────────
async function selftest() {
  const edge = await launchEdge({ headless: true });
  const cdp = await CDP.connect(edge.wsUrl);
  try {
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    const loaded = cdp.waitEvent('Page.loadEventFired', 15000);
    await cdp.send('Page.navigate', { url: 'about:blank' });
    await loaded.catch(() => {});

    await cdp.evalJS(`document.body.innerHTML = '<div id="x" contenteditable="true" style="font-size:40px;outline:0">hi</div>'; true`);
    await cdp.evalJS(`(function(){
      var x=document.getElementById('x'); x.focus();
      var sel=window.getSelection(); sel.removeAllRanges();
      var r=document.createRange();
      r.setStart(x.firstChild, x.firstChild.nodeValue.length); r.collapse(true); sel.addRange(r);
      return true;
    })()`);
    await cdp.typeText('a');
    const text = await cdp.evalJS(`document.getElementById('x').textContent`);
    const ok = typeof text === 'string' && text.indexOf('a') >= 0;
    return {
      ok, browser: edge.browser, edgePath: findEdge(), edgePort: edge.port,
      typed: 'a', resultText: text,
      trustedInputWorks: ok,
      note: ok ? 'CDP 连得上 Edge，且 Input.dispatchKeyEvent 产生了真实文本输入。'
               : 'CDP 连得上，但受信任输入未落入 contenteditable（需排查）。',
    };
  } finally {
    cdp.close();
    edge.cleanup();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. probe：加载应用，逐条执行可测用例，产出原始读数 JSON
// ─────────────────────────────────────────────────────────────────────────────
async function openFile(cdp, file, opts = {}) {
  await cdp.evalJS(`window.MemoriaApp.openFile(${js(file)}, ${js(opts)})`);
}

async function ensurePreview(cdp) {
  await clickView(cdp, 'preview');
  await cdp.waitFor(`window.state && window.state.viewMode === 'preview'`, { label: 'viewMode=preview' });
  await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 0`, { label: 'preview blocks' });
}

async function runProbe({ url, kbRoot, casesPath, screenshotsDir }) {
  const cases = JSON.parse(fs.readFileSync(casesPath, 'utf8'));
  const caseById = {};
  for (const c of (cases.cases || [])) caseById[c.id] = c;

  const edge = await launchEdge({ headless: true });
  const cdp = await CDP.connect(edge.wsUrl);
  const result = {
    schema: 'surface-probe-raw/1',
    browser: edge.browser,
    edgePath: findEdge(),
    url,
    kbRoot,
    casesFile: casesPath,
    startedAt: new Date().toISOString(),
    cases: {},
    console: { editLogs: [], errors: [], total: 0 },
  };
  const t0 = Date.now();

  try {
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    cdp.on('Runtime.consoleAPICalled', (p) => {
      const text = (p.args || []).map((a) => (a.value !== undefined ? String(a.value) : (a.description || ''))).join(' ');
      result.console.total++;
      if (/\[EDIT\]/.test(text)) result.console.editLogs.push(text);
      if (p.type === 'error') result.console.errors.push(text);
    });

    const loaded = cdp.waitEvent('Page.loadEventFired', 30000);
    await cdp.send('Page.navigate', { url });
    await loaded.catch(() => {});

    // 等应用就绪（bridge 注入 → MemoriaBridge ready → initKb）
    await cdp.waitFor(
      `!!(window.MemoriaApp && window.state && window.MemoriaEditSync && window.MemoriaMapper && window.MemoriaEditHandler && window.state.kbPath)`,
      { timeout: 60000, label: 'app-ready' }
    );
    // 等自动打开的首个文件落定
    await cdp.waitFor(`!!(window.state.currentPath && window.state.doc)`, { timeout: 60000, label: 'first-doc' });

    await cdp.evalJS('(' + PAGE_HELPERS.toString() + ')()');
    result.appReady = true;
    result.editHandlerState = await cdp.evalJS('window.__probe.editMode()');

    // ── C2 文本保真：打开不编辑 → 真源 vs 磁盘逐字 ───────────────────────────
    try {
      const c2 = caseById['sel_text_fidelity'] || { target: { file: 'corpus/01-ime-zh.md' } };
      const file = c2.target.file;
      await openFile(cdp, file, { skipNav: true });
      await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'c2-open' });
      const body = await cdp.evalJS('window.__probe.docBody()');
      const lines = await cdp.evalJS('(window.state.doc.lines||[]).join("\\n")');
      const disk = fs.readFileSync(path.join(kbRoot, file), 'utf8');
      let diffAt = -1;
      const n = Math.min(body.length, disk.length);
      for (let i = 0; i < n; i++) { if (body[i] !== disk[i]) { diffAt = i; break; } }
      if (diffAt === -1 && body.length !== disk.length) diffAt = n;
      result.cases[c2.id] = {
        id: c2.id, covers: c2.covers || ['C2'], status: 'ran',
        evidence: {
          file, bodyEqualsDisk: body === disk, linesJoinEqualsDisk: lines === disk,
          bodyLen: body.length, diskLen: disk.length, diffAt,
          bodyHead: body.slice(0, 60), diskHead: disk.slice(0, 60),
        },
      };
    } catch (e) { result.cases['sel_text_fidelity'] = { id: 'sel_text_fidelity', covers: ['C2'], status: 'error', error: e.message }; }

    // ── C3 / C4 打字当帧可见 + 真源不落后 ────────────────────────────────────
    try {
      const c3 = caseById['sel_typing_ascii'];
      const file = c3.target.file;
      const matchText = '这是加粗之前可以打字的一句';
      await openFile(cdp, file, { skipNav: true });
      await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'c3-open' });
      await ensurePreview(cdp);
      await cdp.evalJS('window.__probe.installPerf()');
      const setup = await cdp.evalJS(`window.__probe.setupBlock(${js(matchText)}, 0)`);
      const before = await cdp.evalJS(`window.__probe.snapshotBlock()`);
      // 受信任单键输入；随后**立刻**读 DOM（不等 rAF）
      await cdp.typeText('a');
      const after = await cdp.evalJS(`window.__probe.snapshotBlock('a')`);
      const edits = await cdp.evalJS('window.__probe.perfEdits()');
      result.cases['sel_typing_ascii'] = {
        id: 'sel_typing_ascii', covers: ['C3', 'C4'], status: 'ran',
        evidence: {
          file, matchText, key: 'a',
          setup, before, after,
          edits,
          immediateRead: true,
          note: 'typeText 用 Input.dispatchKeyEvent(keyDown+keyUp, text) 注入受信任输入；读 DOM 未等 rAF。',
        },
      };
    } catch (e) { result.cases['sel_typing_ascii'] = { id: 'sel_typing_ascii', covers: ['C3', 'C4'], status: 'error', error: e.message }; }

    // ── C6 落点准确：跳转到「目标-头/中/尾」标题所在行 ───────────────────────
    try {
      const c6 = caseById['sel_jump_head_mid_tail'];
      const file = c6.target.file;
      await openFile(cdp, file, { skipNav: true });
      await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'c6-open' });
      await ensurePreview(cdp);
      const diskLines = fs.readFileSync(path.join(kbRoot, file), 'utf8').split('\n');
      const targets = ['目标-头', '目标-中', '目标-尾'];
      const rows = [];
      for (const h of targets) {
        let L = null;
        for (let i = 0; i < diskLines.length; i++) { if (diskLines[i].trim() === '## ' + h) { L = i + 1; break; } }
        // 应用的跳转入口：openFile(..., {lineHint}); → highlightRange(line,line) → highlightPreviewRange(scroll)
        await cdp.evalJS(`window.MemoriaApp.openFile(${js(file)}, ${js({ lineHint: L, skipNav: true })})`);
        await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'c6-jump' });
        await waitScrollSettled(cdp);
        const first = await cdp.evalJS('window.__probe.firstScreenBlock("preview")');
        const scroll = await cdp.evalJS('window.__probe.scrollInfo()');
        const target = await cdp.evalJS(`window.__probe.blockInfoForLine(${L})`);
        const inRange = !!(first && first.start != null && first.start <= (L + 1) && first.end >= (L - 1));
        rows.push({
          heading: h, targetLine: L, firstScreenBlock: first,
          inRangePlusMinus1: inRange,
          targetBlock: target,
          targetVisible: !!(target && target.visible),
          scrollClampedAtBottom: !!(scroll && scroll.clampedAtBottom),
          scroll,
        });
      }
      result.cases[c6.id] = {
        id: c6.id, covers: c6.covers || ['C6'], status: 'ran',
        evidence: { file, entry: 'MemoriaApp.openFile(file,{lineHint}) -> highlightRange -> highlightPreviewRange', rows },
      };
    } catch (e) { result.cases['sel_jump_head_mid_tail'] = { id: 'sel_jump_head_mid_tail', covers: ['C6'], status: 'error', error: e.message }; }

    // ── C7 切模式不漂：记锚点行 → preview↔split↔source → 再读锚点行 ────────────
    try {
      const c7 = caseById['sel_switch_mode'];
      const file = c7.target.file;
      const matchText = '中英混排的句子';
      await openFile(cdp, file, { skipNav: true });
      await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'c7-open' });
      await ensurePreview(cdp);
      await cdp.evalJS(`window.__probe.scrollBlockToTop(${js(matchText)})`);
      await waitScrollSettled(cdp);
      const sequence = [];
      const readAnchors = async (label) => {
        const pv = await cdp.evalJS('window.__probe.topSrcLine("preview")');
        const sm = await cdp.evalJS('window.__probe.firstScreenBlock("source")');
        sequence.push({ at: label, previewTopSrcLine: pv, sourceTopSrcLine: sm ? sm.start : null, scrollTop: await cdp.evalJS('window.__probe.previewScrollTop()') });
      };
      await readAnchors('preview#0');
      await clickView(cdp, 'split'); await cdp.waitFor(`window.state.viewMode === 'split'`); await waitScrollSettled(cdp);
      await readAnchors('split');
      await clickView(cdp, 'source'); await cdp.waitFor(`window.state.viewMode === 'source'`); await sleep(300);
      await readAnchors('source');
      await clickView(cdp, 'preview'); await cdp.waitFor(`window.state.viewMode === 'preview'`); await waitScrollSettled(cdp);
      await readAnchors('preview#1');
      const a0 = sequence[0].previewTopSrcLine;
      const a1 = sequence[sequence.length - 1].previewTopSrcLine;
      result.cases[c7.id] = {
        id: c7.id, covers: c7.covers || ['C7'], status: 'ran',
        evidence: { file, matchText, sequence, anchor0: a0, anchorFinal: a1, delta: (a0 != null && a1 != null) ? Math.abs(a1 - a0) : null },
      };
    } catch (e) { result.cases['sel_switch_mode'] = { id: 'sel_switch_mode', covers: ['C7'], status: 'error', error: e.message }; }

    // ── C9 性能预算：scale-5k.md 上打 ~30 字，测「按键 → 真源」 ──────────────
    try {
      const c9 = caseById['sel_scroll_stress'];
      const file = c9.target.file;
      await openFile(cdp, file, { skipNav: true });
      await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { timeout: 90000, label: 'c9-open' });
      await ensurePreview(cdp);
      const lineCount = await cdp.evalJS('window.__probe.docLines()');
      await cdp.evalJS('window.__probe.installPerf()');
      const setup = await cdp.evalJS(`window.__probe.setupBlock(${js('跳转示例')}, 'end')`);
      const N = 30;
      const t0 = Date.now();
      await cdp.typeText('z'.repeat(N));
      const wall = Date.now() - t0;
      const edits = await cdp.evalJS('window.__probe.perfEdits()');
      const fromKey = edits.map((e) => e.fromKeyMs).filter((v) => typeof v === 'number');
      const insertMs = edits.map((e) => e.insertMs).filter((v) => typeof v === 'number');
      const stat = (arr) => {
        if (!arr.length) return null;
        const s = arr.slice().sort((a, b) => a - b);
        const sum = s.reduce((a, b) => a + b, 0);
        const pct = (q) => s[Math.min(s.length - 1, Math.floor(q * s.length))];
        return { n: s.length, min: +s[0].toFixed(3), median: +pct(0.5).toFixed(3), p95: +pct(0.95).toFixed(3), max: +s[s.length - 1].toFixed(3), mean: +(sum / s.length).toFixed(3) };
      };
      result.cases[c9.id] = {
        id: c9.id, covers: c9.covers || ['C9'], status: 'ran',
        evidence: {
          file, docLines: lineCount, typedChars: N, setup,
          keyToSource: stat(fromKey), insertOnly: stat(insertMs),
          editsRaw: edits.slice(0, 40), wallMs: wall,
          budgetMs: 16, note: 'keyToSource = keydown 时刻 → insertText 返回（真源/预览已更新）。',
        },
      };
    } catch (e) { result.cases['sel_scroll_stress'] = { id: 'sel_scroll_stress', covers: ['C9'], status: 'error', error: e.message }; }

    if (screenshotsDir) {
      try {
        fs.mkdirSync(screenshotsDir, { recursive: true });
        result.screenshot = await cdp.screenshot(path.join(screenshotsDir, 'final.png'));
      } catch (e) { result.screenshotError = e.message; }
    }
  } finally {
    result.durationMs = Date.now() - t0;
    result.finishedAt = new Date().toISOString();
    cdp.close();
    edge.cleanup();
  }
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// 6b. mermaid diag：量 mermaid 渲染尺寸 + lightbox 交互（诊断/回归用）
//
//   node scripts/benchmark/surface/cdp.mjs --mermaid-diag \
//        --url http://127.0.0.1:8643/ --file corpus/04-non-editable.md \
//        --out <raw.json> [--screenshots] [--label before]
// ─────────────────────────────────────────────────────────────────────────────
async function runMermaidDiag({ url, file, out, screenshotsDir, label }) {
  const edge = await launchEdge({ headless: true });
  const cdp = await CDP.connect(edge.wsUrl);
  const result = {
    schema: 'mermaid-diag/1', browser: edge.browser, url, file, label,
    startedAt: new Date().toISOString(), console: { errors: [] }, steps: {},
  };
  try {
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    cdp.on('Runtime.consoleAPICalled', (p) => {
      if (p.type === 'error') {
        result.console.errors.push((p.args || []).map((a) => (a.value !== undefined ? String(a.value) : (a.description || ''))).join(' '));
      }
    });
    const loaded = cdp.waitEvent('Page.loadEventFired', 30000);
    await cdp.send('Page.navigate', { url });
    await loaded.catch(() => {});
    await cdp.waitFor(
      `!!(window.MemoriaApp && window.state && window.MemoriaEditSync && window.MemoriaMapper && window.MemoriaEditHandler && window.state.kbPath)`,
      { timeout: 60000, label: 'app-ready' }
    );
    await cdp.waitFor(`!!(window.state.currentPath && window.state.doc)`, { timeout: 60000, label: 'first-doc' });
    await cdp.evalJS('(' + PAGE_HELPERS.toString() + ')()');

    // 插桩 window.mermaid.render：记录「渲染那一刻」预览区可见性/宽度
    result.steps.patch = await cdp.evalJS(`(function(){
      if (window.__mmdDiag) return 'already';
      window.__mmdDiag = [];
      if (!(window.mermaid && typeof window.mermaid.render === 'function')) return 'no-mermaid';
      var orig = window.mermaid.render.bind(window.mermaid);
      window.mermaid.render = function(id, src){
        var pane = document.getElementById('preview-pane');
        var pv = document.getElementById('preview');
        window.__mmdDiag.push({
          srcLen: (src || '').length,
          paneClientWidth: pane ? pane.clientWidth : null,
          paneOffsetParentNull: pane ? pane.offsetParent === null : null,
          paneDisplay: pane ? getComputedStyle(pane).display : null,
          previewClientWidth: pv ? pv.clientWidth : null,
          previewOffsetParentNull: pv ? pv.offsetParent === null : null,
          viewMode: window.state ? window.state.viewMode : null,
        });
        return orig(id, src);
      };
      return 'installed';
    })()`);

    await openFile(cdp, file, { skipNav: true });
    await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'open' });
    await ensurePreview(cdp);
    await cdp.waitFor(`document.querySelectorAll('.-mermaid-container svg').length > 0`, { timeout: 40000, label: 'mermaid-rendered' });
    await sleep(300);

    result.steps.renderCalls = await cdp.evalJS('window.__mmdDiag || []');
    result.steps.counts = await cdp.evalJS(`(function(){return {
      preMermaid: document.querySelectorAll('pre.language-mermaid, pre code.language-mermaid').length,
      containers: document.querySelectorAll('.-mermaid-container').length,
      svgs: document.querySelectorAll('.-mermaid-container svg').length,
      errors: document.querySelectorAll('.-mermaid-error').length
    };})()`);
    result.steps.metrics = await cdp.evalJS(`(function(){
      var out = { ok: false };
      var c = document.querySelector('.-mermaid-container');
      if (c) {
        out.containerClientWidth = c.clientWidth;
        out.containerRectW = Math.round(c.getBoundingClientRect().width * 100) / 100;
        out.containerPadding = getComputedStyle(c).padding;
        var svg = c.querySelector('svg');
        if (svg) {
          var r = svg.getBoundingClientRect();
          out.svgRectW = Math.round(r.width * 100) / 100;
          out.svgRectH = Math.round(r.height * 100) / 100;
          out.svgAttrWidth = svg.getAttribute('width');
          out.svgAttrHeight = svg.getAttribute('height');
          out.svgStyleMaxWidth = svg.style.maxWidth;
          out.svgStyleWidth = svg.style.width;
          out.svgViewBox = svg.getAttribute('viewBox');
          out.svgPreserveAspectRatio = svg.getAttribute('preserveAspectRatio');
          var cs = getComputedStyle(svg);
          out.svgComputedMaxWidth = cs.maxWidth;
          out.svgComputedWidth = cs.width;
          out.svgComputedHeight = cs.height;
          out.svgFontSize = cs.fontSize;
          out.svgHtmlHead = String(svg.outerHTML).slice(0, 3000);
          var fos = [];
          svg.querySelectorAll('foreignObject').forEach(function (f) {
            var fr = f.getBoundingClientRect();
            var inner = f.firstElementChild;
            var ir = inner ? inner.getBoundingClientRect() : null;
            fos.push({ w: Math.round(fr.width), h: Math.round(fr.height), attrW: f.getAttribute('width'), innerW: inner ? inner.getAttribute('width') : null, innerStyleW: inner ? inner.style.width : null, text: (f.textContent || '').slice(0, 20) });
          });
          out.foreignObjects = fos;
          var nodes = [];
          svg.querySelectorAll('.node, .nodeLabel, .edgeLabel').forEach(function (n) {
            var nr = n.getBoundingClientRect();
            nodes.push({ cls: n.getAttribute('class'), w: Math.round(nr.width), h: Math.round(nr.height), tf: n.getAttribute('transform') });
          });
          out.nodesHead = nodes.slice(0, 12);
          try { var bb = svg.getBBox(); out.svgGetBBox = { x: Math.round(bb.x * 100) / 100, y: Math.round(bb.y * 100) / 100, w: Math.round(bb.width * 100) / 100, h: Math.round(bb.height * 100) / 100 }; } catch (e) { out.svgGetBBox = String(e); }
          out.svgOuter = String(svg.outerHTML);
        }
      }
      var p = document.querySelector('#preview p');
      if (p) { out.paragraphClientWidth = p.clientWidth; out.paragraphRectW = Math.round(p.getBoundingClientRect().width * 100) / 100; }
      var pane = document.getElementById('preview-pane');
      if (pane) { out.paneClientWidth = pane.clientWidth; out.paneOffsetParentNull = pane.offsetParent === null; out.paneDisplay = getComputedStyle(pane).display; }
      var pv = document.getElementById('preview');
      if (pv) { out.previewClientWidth = pv.clientWidth; out.previewOffsetParentNull = pv.offsetParent === null; }
      out.viewMode = window.state ? window.state.viewMode : null;
      out.windowInnerWidth = window.innerWidth;
      out.ok = true;out._containers=(function(){var arr=[];document.querySelectorAll('.-mermaid-container').forEach(function(k){var s=k.querySelector('svg');var r=s?s.getBoundingClientRect():{width:0,height:0,left:0,right:0};var cr=k.getBoundingClientRect();arr.push({index:arr.length,clientW:k.clientWidth,scrollW:k.scrollWidth,rectW:Math.round(cr.width*100)/100,rectLeft:Math.round(cr.left*100)/100,rectRight:Math.round(cr.right*100)/100,svgRectW:Math.round(r.width*100)/100,svgRectRight:Math.round(r.right*100)/100,svgAttrW:s?s.getAttribute('width'):null,svgStyleMaxW:s?s.style.maxWidth:null,svgComputedMaxW:s?getComputedStyle(s).maxWidth:null,textAlign:getComputedStyle(k).textAlign});});return arr;})();out.paneScrollWidth=pane?pane.scrollWidth:null;out.previewScrollWidth=pv?pv.scrollWidth:null;out.docElScrollWidth=document.documentElement.scrollWidth;out.docElClientWidth=document.documentElement.clientWidth;out.bodyScrollWidth=document.body.scrollWidth;out.windowInnerHeight=window.innerHeight;out.horizontalScrollbar=document.documentElement.scrollWidth>document.documentElement.clientWidth;out.ancestors=[];(function(){var e=c;while(e){var cs=getComputedStyle(e);out.ancestors.push({tag:e.tagName,id:e.id||'',cls:String(e.className||'').slice(0,48),clientW:e.clientWidth,scrollW:e.scrollWidth,minWidth:cs.minWidth,display:cs.display,flexGrow:cs.flexGrow,flexShrink:cs.flexShrink,overflowX:cs.overflowX,rectRight:Math.round(e.getBoundingClientRect().right*100)/100});e=e.parentElement;}})();
      return out;
    })()`);

    if (screenshotsDir) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
      result.screenshots = {};
      result.screenshots.diagram = await cdp.screenshot(path.join(screenshotsDir, (label || 'diag') + '-diagram.png'));
    }

    // 受控 A/B：同一 src，分别在「可见」与「隐藏 preview-pane」时 render，比对 viewBox
    result.steps.manualRender = await cdp.evalJS(`(async function(){
      var src = "flowchart TD\\n    A[开始] --> B{判断}\\n    B -->|是| C[结束]\\n    B -->|否| A";
      var out = {};
      var r1 = await window.mermaid.render('probe-visible-' + Date.now(), src);
      var d1 = document.createElement('div'); d1.innerHTML = r1.svg;
      var s1 = d1.querySelector('svg');
      out.visible = { viewBox: s1.getAttribute('viewBox'), styleMaxWidth: s1.style.maxWidth, attrWidth: s1.getAttribute('width') };
      var pane = document.getElementById('preview-pane');
      var prev = pane.style.display; pane.style.display = 'none';
      try {
        var r2 = await window.mermaid.render('probe-hidden-' + Date.now(), src);
        var d2 = document.createElement('div'); d2.innerHTML = r2.svg;
        var s2 = d2.querySelector('svg');
        out.hidden = { viewBox: s2.getAttribute('viewBox'), styleMaxWidth: s2.style.maxWidth, attrWidth: s2.getAttribute('width') };
      } finally { pane.style.display = prev; }
      return out;
    })()`);

    // 关键实验：包裹 SVGGraphicsElement.getBBox，记录一次 render 内所有 getBBox 调用与结果
    result.steps.getBBoxProbe = await cdp.evalJS(`(async function(){
      var proto = window.SVGGraphicsElement && window.SVGGraphicsElement.prototype;
      if (!proto || !proto.getBBox) return 'no-getBBox';
      var orig = proto.getBBox;
      var recs = [];
      proto.getBBox = function(){
        var b = orig.apply(this, arguments);
        recs.push({ tag: (this.tagName || ''), id: String(this.id || ''), cls: String((this.getAttribute && this.getAttribute('class')) || '').slice(0, 24), x: Math.round(b.x * 100) / 100, y: Math.round(b.y * 100) / 100, w: Math.round(b.width * 100) / 100, h: Math.round(b.height * 100) / 100 });
        return b;
      };
      try {
        var src = "flowchart TD\\n    A[开始] --> B{判断}\\n    B -->|是| C[结束]\\n    B -->|否| A";
        await window.mermaid.render('probe-gb-' + Date.now(), src);
      } finally { proto.getBBox = orig; }
      return recs;
    })()`);

    // 修复假设验证：隐藏 foreignObject 后再取 getBBox，是否得到「贴合内容」的紧致 bbox
    result.steps.bboxExcludeFoTests = await cdp.evalJS(`(function(){
      var svg = document.querySelector('.-mermaid-container svg');
      if (!svg) return null;
      var fos = Array.prototype.slice.call(svg.querySelectorAll('foreignObject'));
      function rb(b) { return { x: Math.round(b.x * 100) / 100, y: Math.round(b.y * 100) / 100, w: Math.round(b.width * 100) / 100, h: Math.round(b.height * 100) / 100 }; }
      var withFo = rb(svg.getBBox());
      fos.forEach(function (f) { f.style.display = 'none'; });
      var withoutFo = rb(svg.getBBox());
      fos.forEach(function (f) { f.style.display = ''; });
      // 直接给 foreignObject 打补丁：返回其 width/height 属性构成的 rect
      var proto = window.SVGGraphicsElement && window.SVGGraphicsElement.prototype;
      var orig = proto.getBBox; var recs = [];
      proto.getBBox = function () {
        if (this.tagName === 'foreignObject') {
          var w = parseFloat(this.getAttribute('width')) || 0, h = parseFloat(this.getAttribute('height')) || 0;
          var x = parseFloat(this.getAttribute('x')) || 0, y = parseFloat(this.getAttribute('y')) || 0;
          return { x: x, y: y, width: w, height: h };
        }
        return orig.apply(this, arguments);
      };
      var patched = rb(svg.getBBox());
      proto.getBBox = orig;
      return { foCount: fos.length, withFo: withFo, withoutFo: withoutFo, patchedFo: patched };
    })()`);

    // 隐藏态下的 getBBox（判断「渲染时预览不可见」时能否安全取 bbox）
    result.steps.hiddenBBox = await cdp.evalJS(`(function(){
      var c = document.querySelector('.-mermaid-container');
      if (!c) return null;
      var svg = c.querySelector('svg');
      var d = c.style.display; c.style.display = 'none';
      var b; try { b = svg.getBBox(); } catch (e) { b = String(e); }
      c.style.display = d;
      return (b && b.width !== undefined) ? { x: b.x, y: b.y, w: b.width, h: b.height } : b;
    })()`);

    // 候选修复：渲染期间把 foreignObject.getBBox 直接补丁掉（返回其声明 rect），再看 mermaid 自算的 viewBox
    result.steps.patchedRender = await cdp.evalJS(`(async function(){
      var proto = window.SVGGraphicsElement && window.SVGGraphicsElement.prototype;
      if (!proto || !proto.getBBox) return 'no-getBBox';
      var orig = proto.getBBox;
      proto.getBBox = function () {
        if (this.tagName === 'foreignObject') {
          var w = parseFloat(this.getAttribute('width')) || 0, h = parseFloat(this.getAttribute('height')) || 0;
          var x = parseFloat(this.getAttribute('x')) || 0, y = parseFloat(this.getAttribute('y')) || 0;
          return { x: x, y: y, width: w, height: h };
        }
        return orig.apply(this, arguments);
      };
      var r;
      try {
        var src = "flowchart TD\\n    A[开始] --> B{判断}\\n    B -->|是| C[结束]\\n    B -->|否| A";
        r = await window.mermaid.render('probe-patch-' + Date.now(), src);
      } finally { proto.getBBox = orig; }
      var d = document.createElement('div'); d.innerHTML = r.svg;
      var s = d.querySelector('svg');
      var shape = s.querySelector('rect.basic.label-container') || s.querySelector('polygon.label-container');
      var sb = shape ? shape.getBBox() : null;
      var rootG = s.querySelector('g');
      var gb = rootG ? rootG.getBBox() : null;
      return {
        viewBox: s.getAttribute('viewBox'), maxWidth: s.style.maxWidth, attrWidth: s.getAttribute('width'),
        shapeBBox: sb ? { w: Math.round(sb.width * 100) / 100, h: Math.round(sb.height * 100) / 100 } : null,
        rootGBBox: gb ? { x: Math.round(gb.x * 100) / 100, y: Math.round(gb.y * 100) / 100, w: Math.round(gb.width * 100) / 100, h: Math.round(gb.height * 100) / 100 } : null
      };
    })()`);

    // ── 交互：双击放大 + 滚轮 + 拖拽 + 关闭 ──
    await cdp.evalJS(`(function(){var c=document.querySelector('.-mermaid-container'); if(c) c.scrollIntoView({block:'center'}); return true;})()`);
    await sleep(400);
    const center = await cdp.evalJS(`(function(){
      var svg = document.querySelector('.-mermaid-container svg');
      if (!svg) return null;
      var r = svg.getBoundingClientRect();
      return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), w: Math.round(r.width), h: Math.round(r.height) };
    })()`);
    result.steps.svgCenter = center;

    // 放大入口 = 图右上角 `-mmd-zoom-btn`（2026-10-04 起：双击已归"进块编辑"，不再触发 lightbox）
    const zoomBtnCenter = await cdp.evalJS(`(function(){
      var b = document.querySelector('.-mermaid-container .-mmd-zoom-btn');
      if (!b) return null;
      b.scrollIntoView({ block: 'center' });
      var r = b.getBoundingClientRect();
      return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
    })()`);
    result.steps.zoomBtnCenter = zoomBtnCenter;
    const clickAt = async (pt) => {
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: pt.x, y: pt.y, button: 'left', buttons: 1, clickCount: 1 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: pt.x, y: pt.y, button: 'left', buttons: 0, clickCount: 1 });
    };

    const dblclickAt = async (x, y) => {
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 2 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 2 });
    };
    const readTf = `(function(){var b=document.querySelector('.-lightbox-overlay .-lightbox-image');return b?b.style.transform:null;})()`;

    if (center) {
      await clickAt(zoomBtnCenter || center);
      await sleep(150);
      result.steps.lightboxOpen = await cdp.evalJS(`(function(){
        var o = document.querySelector('.-lightbox-overlay');
        var big = o ? o.querySelector('.-lightbox-image') : null;
        return {
          open: !!o,
          childCount: o ? o.childElementCount : null,
          bigTag: big ? big.tagName : null,
          bigIsSvg: !!(big && big.tagName && big.tagName.toLowerCase() === 'svg'),
          bigIsImg: !!(big && big.tagName === 'IMG'),
          hint: o ? ((o.querySelector('.-lightbox-hint') || {}).textContent || null) : null,
          transform: big ? big.style.transform : null,
          styleWidth: big ? big.style.width : null
        };
      })()`);
      result.steps.blockEditAfterZoomClick = await cdp.evalJS('window.__probe.editMode()');

      const lbCenter = await cdp.evalJS(`(function(){var b=document.querySelector('.-lightbox-overlay .-lightbox-image'); if(!b) return null; var r=b.getBoundingClientRect(); return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), w:Math.round(r.width), h:Math.round(r.height)};})()`);
      result.steps.lightboxCenter = lbCenter;
      const px = (lbCenter || center).x, py = (lbCenter || center).y;

      const tfBefore = await cdp.evalJS(readTf);
      result.steps.dragEventLog = await cdp.evalJS(`(function(){
        window.__evLog = [];
        ['pointerdown','pointermove','pointerup','mousedown','mousemove','mouseup'].forEach(function(t){
          document.addEventListener(t, function(e){ window.__evLog.push(t + '@' + (e.target.tagName||'') + (e.target.getAttribute && e.target.getAttribute('class') ? '.' + String(e.target.getAttribute('class')).slice(0,20) : '')); }, true);
        });
        return 'installed';
      })()`);
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: px, y: py, deltaX: 0, deltaY: -120 });
      await sleep(90);
      const tfWheel = await cdp.evalJS(readTf);
      result.steps.wheel = { before: tfBefore, after: tfWheel };

      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: px, y: py, button: 'left', buttons: 1, clickCount: 1 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: px + 60, y: py + 40, button: 'none', buttons: 1 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: px + 120, y: py + 80, button: 'none', buttons: 1 });
      await sleep(50);
      const tfDrag = await cdp.evalJS(readTf);
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: px + 120, y: py + 80, button: 'left', buttons: 0, clickCount: 1 });
      await sleep(30);
      result.steps.drag = { before: tfWheel, during: tfDrag, after: await cdp.evalJS(readTf) };
      result.steps.dragEvents = await cdp.evalJS('(window.__evLog||[]).slice(-40)');
      result.steps.dragFlags = await cdp.evalJS(`(function(){var b=document.querySelector('.-lightbox-overlay .-lightbox-image');return { bigTag: b?b.tagName:null, overlayDragging: !!document.querySelector('.-lightbox-overlay.-lightbox-dragging') };})()`);
      if (screenshotsDir) result.screenshots.lightbox = await cdp.screenshot(path.join(screenshotsDir, (label || 'diag') + '-lightbox.png'));

      await cdp.pressKey('Escape', { code: 'Escape', vk: 27 });
      await sleep(90);
      result.steps.escapeClose = await cdp.evalJS(`!document.querySelector('.-lightbox-overlay')`);

      await clickAt(zoomBtnCenter || center);
      await sleep(150);
      const open2 = await cdp.evalJS(`!!document.querySelector('.-lightbox-overlay')`);
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: 6, y: 6, button: 'left', buttons: 1, clickCount: 1 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: 6, y: 6, button: 'left', buttons: 0, clickCount: 1 });
      await sleep(90);
      const closed2 = await cdp.evalJS(`!document.querySelector('.-lightbox-overlay')`);
      result.steps.backgroundClose = { reopened: open2, closedAfterBgClick: closed2 };

      result.steps.afterClose = await cdp.evalJS(`(function(){
        var svg = document.querySelector('.-mermaid-container svg');
        if (!svg) return { svgPresent: false };
        var r = svg.getBoundingClientRect();
        return { svgPresent: true, rectW: Math.round(r.width * 100) / 100, rectH: Math.round(r.height * 100) / 100, attrWidth: svg.getAttribute('width'), styleMaxWidth: svg.style.maxWidth, overlay: !!document.querySelector('.-lightbox-overlay') };
      })()`);
      if (screenshotsDir) result.screenshots.afterClose = await cdp.screenshot(path.join(screenshotsDir, (label || 'diag') + '-after-close.png'));
    }

    // 回归检查：既有图片 lightbox 仍按原样工作（scale 起点=1、元素仍是 <img>）
    result.steps.imageLightboxTest = await cdp.evalJS(`(function(){
      var pv = document.getElementById('preview');
      if (!pv) return 'no-preview';
      var dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="#39f"/></svg>');
      var img = document.createElement('img'); img.src = dataUrl; img.className = '-preview-image';
      pv.appendChild(img);
      window.MemoriaMarkdownPreview.attachImageLightbox(pv);
      img.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
      var o = document.querySelector('.-lightbox-overlay');
      var b = o ? o.querySelector('.-lightbox-image') : null;
      var out = { open: !!o, bigTag: b ? b.tagName : null, transform: b ? b.style.transform : null,
                  hint: o ? ((o.querySelector('.-lightbox-hint') || {}).textContent || null) : null };
      if (o) o.remove();
      img.remove();
      return out;
    })()`);
  } finally {
    result.finishedAt = new Date().toISOString();
    cdp.close();
    edge.cleanup();
  }
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// 6c. mermaid view：图内平移 / 把手改尺寸 / 复位 / 写回 / 撤销 交互实测（2026-10-04）
//
//   node scripts/benchmark/surface/cdp.mjs --mermaid-view \
//        --url http://127.0.0.1:8643/ --kb-root <kb> --file corpus/04-non-editable.md \
//        --out <raw.json> [--screenshots] [--label view]
//
// 前置：应用已含 `window.MemoriaApp.surface` 门面与 markdown-preview 的 `_attachMermaidView`。
// 指针一律走 CDP `Input.dispatchMouseEvent`（浏览器合成 pointerdown/move/up）。
// ─────────────────────────────────────────────────────────────────────────────
async function runMermaidView({ url, kbRoot, file, out, screenshotsDir, label }) {
  const edge = await launchEdge({ headless: true });
  const cdp = await CDP.connect(edge.wsUrl);
  const R = {
    schema: 'mermaid-view/1', browser: edge.browser, url, file, kbRoot, label,
    startedAt: new Date().toISOString(), console: { errors: [] }, steps: {},
  };
  const innerLine = (src) => (typeof src === 'string' ? (src.split('\n')[1] || null) : null);
  const hasDirective = (src) => /^\s*%%\s*memoria-view:/.test(innerLine(src) || '');
  const anyDirective = (src) => typeof src === 'string' && /(^|\n)\s*%%\s*memoria-view:/.test(src);

  const READ = `(function(){
    var c = document.querySelector('.-mermaid-container');
    if (!c) return null;
    var svg = c.querySelector('svg');
    var pan = c.querySelector('.-mermaid-pan');
    var r = svg ? svg.getBoundingClientRect() : { width: 0, height: 0 };
    var cr = c.getBoundingClientRect();
    return {
      blockIndex: c.getAttribute('data--block-index'),
      viewport: c.classList.contains('-mmd-viewport'),
      transform: pan ? (pan.style.transform || '') : null,
      containerW: Math.round(cr.width), containerH: Math.round(cr.height),
      containerInlineW: c.style.width, containerInlineH: c.style.height,
      svgW: Math.round(r.width), svgH: Math.round(r.height), svgInlineW: svg ? svg.style.width : null,
      hasHandle: !!c.querySelector('.-mermaid-resize'),
      interacting: c.getAttribute('data-mermaid-interacting') === '1'
    };
  })()`;
  const read = () => cdp.evalJS(READ);
  // 命中点：先把元素滚到视口中间（图可能很高、中心会落到视口外），再取中心并夹进视口
  const centerOf = async (sel) => {
    const p = await cdp.evalJS(`(function(){
      var e=document.querySelector(${JSON.stringify(sel)}); if(!e) return null;
      try { e.scrollIntoView({ block: 'center' }); } catch (_) {}
      var r=e.getBoundingClientRect();
      var x=r.left+r.width/2, y=r.top+r.height/2;
      x=Math.max(10,Math.min(window.innerWidth-130,x));
      y=Math.max(10,Math.min(window.innerHeight-90,y));
      return { x: Math.round(x), y: Math.round(y) };
    })()`);
    await sleep(120);
    return p;
  };
  const waitSvg = () => cdp.waitFor(`document.querySelectorAll('.-mermaid-container svg').length>0`, { timeout: 40000, label: 'mermaid' });
  const dragTo = async (from, dx, dy, steps = 1) => {
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: from.x, y: from.y, button: 'left', buttons: 1, clickCount: 1 });
    for (let i = 1; i <= steps; i++) {
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: from.x + Math.round((dx * i) / steps), y: from.y + Math.round((dy * i) / steps), button: 'none', buttons: 1 });
    }
    await sleep(50);
  };
  const releaseAt = async (from, dx, dy) => {
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: from.x + dx, y: from.y + dy, button: 'left', buttons: 0, clickCount: 1 });
  };
  const dblclickAt = async (x, y) => {
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 });
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 2 });
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 2 });
  };
  const blockEdit = () => cdp.evalJS('(function(){var E=window.MemoriaEditHandler;return E?{blockEditMode:!!E.blockEditMode,type:(E.blockEditMode&&E.blockEditMode.blockType)||null}:null;})()');
  const srcOf = (bi) => cdp.evalJS(`window.MemoriaApp.surface.getBlockSourceText(${bi})`);
  const bodySrc = () => cdp.evalJS('window.state.doc.body');
  const closeLightbox = () => cdp.evalJS('(function(){var o=document.querySelector(".-lightbox-overlay");if(o)o.remove();return true;})()');
  const lightboxPresent = () => cdp.evalJS('!!document.querySelector(".-lightbox-overlay")');

  try {
    await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
    cdp.on('Runtime.consoleAPICalled', (p) => {
      if (p.type === 'error') R.console.errors.push((p.args || []).map((a) => (a.value !== undefined ? String(a.value) : (a.description || ''))).join(' '));
    });
    const loaded = cdp.waitEvent('Page.loadEventFired', 30000);
    await cdp.send('Page.navigate', { url });
    await loaded.catch(() => {});
    await cdp.waitFor(`!!(window.MemoriaApp && window.state && window.MemoriaEditSync && window.MemoriaApp.surface && window.state.kbPath)`, { timeout: 60000, label: 'app-ready' });
    await cdp.waitFor(`!!(window.state.currentPath && window.state.doc)`, { timeout: 60000, label: 'first-doc' });
    await cdp.evalJS('(' + PAGE_HELPERS.toString() + ')()');
    R.appReady = true;
    R.surfaceExposed = await cdp.evalJS('!!(window.MemoriaApp.surface && window.MemoriaApp.surface.setBlockSource && window.MemoriaApp.surface.getBlockSourceRange && window.MemoriaApp.surface.getBlockSourceText)');
    R.editHandler = await cdp.evalJS('window.__probe.editMode()');

    await openFile(cdp, file, { skipNav: true });
    await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'open' });
    await ensurePreview(cdp);
    await waitSvg();
    await sleep(300);

    R.steps.before = await read();
    const bi = parseInt(R.steps.before.blockIndex, 10);
    R.steps.beforeBlockIndex = bi;
    R.steps.beforeSource = await srcOf(bi);
    R.steps.beforeHasDirective = hasDirective(R.steps.beforeSource);
    if (screenshotsDir) { fs.mkdirSync(screenshotsDir, { recursive: true }); R.screenshots = {}; R.screenshots.before = await cdp.screenshot(path.join(screenshotsDir, (label || 'view') + '-before.png')); }

    // ── 1) 图内平移：按住图拖 (120,80) ──
    const c1 = await centerOf('.-mermaid-container svg');
    await dragTo(c1, 120, 80);
    R.steps.panDuring = await read();
    await releaseAt(c1, 120, 80);
    await sleep(700); await waitSvg(); await sleep(300);
    R.steps.panBodySource = await bodySrc();
    R.steps.panBodyHasDirective = anyDirective(R.steps.panBodySource);
    R.steps.panSourceAfter = await srcOf(bi);
    R.steps.panAfter = await read();
    if (screenshotsDir) R.screenshots.pan = await cdp.screenshot(path.join(screenshotsDir, (label || 'view') + '-pan.png'));

    // ── 2) 右下把手改尺寸：拖 (100,60) ──
    const hc = await centerOf('.-mermaid-container .-mermaid-resize');
    R.steps.beforeResize = await read();
    await dragTo(hc, 100, 60);
    R.steps.resizeDuring = await read();
    await releaseAt(hc, 100, 60);
    await sleep(700); await waitSvg(); await sleep(300);
    R.steps.resizeSourceAfter = await srcOf(bi);
    R.steps.resizeAfter = await read();
    if (screenshotsDir) R.screenshots.resize = await cdp.screenshot(path.join(screenshotsDir, (label || 'view') + '-resize.png'));

    // ── 3) 复位：把手双击 ⇒ 指令行移除 + 自然尺寸 ──
    const hc2 = await centerOf('.-mermaid-container .-mermaid-resize');
    await dblclickAt(hc2.x, hc2.y);
    await sleep(700); await waitSvg(); await sleep(300);
    R.steps.resetSource = await srcOf(bi);
    R.steps.resetHasDirective = hasDirective(R.steps.resetSource);
    R.steps.resetAfter = await read();

    // ── 4) 撤销：新一次平移后 Ctrl+Z ⇒ 回到无指令 ──
    const c2 = await centerOf('.-mermaid-container svg');
    await dragTo(c2, 60, 40); await releaseAt(c2, 60, 40);
    await sleep(700); await waitSvg(); await sleep(300);
    R.steps.undoBeforeSource = await srcOf(bi);
    R.steps.undoBeforeHasDirective = hasDirective(R.steps.undoBeforeSource);
    await cdp.evalJS('(function(){var p=document.getElementById("preview");try{p.focus({preventScroll:true});}catch(e){p.focus();}return true;})()');
    await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90, modifiers: 2 });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90, modifiers: 2 });
    await sleep(800); await waitSvg(); await sleep(300);
    R.steps.undoBodySource = await bodySrc();
    R.steps.undoHasDirective = anyDirective(R.steps.undoBodySource);
    R.steps.undoAfter = await read();

    // ── 5) 交互不打架 ──
    // ① 双击（不移动）仍进 lightbox
    const c3 = await centerOf('.-mermaid-container svg');
    await dblclickAt(c3.x, c3.y);
    await sleep(200);
    R.steps.dblclickOpensLightbox = await lightboxPresent();
    R.steps.dblclickBlockEdit = await blockEdit();
    await closeLightbox(); await sleep(150);
    // ② 拖动后立刻双击 ⇒ 不进 lightbox（一次性拖动不该被当成双击）
    const c4 = await centerOf('.-mermaid-container svg');
    await dragTo(c4, 50, 30); await releaseAt(c4, 50, 30);
    await dblclickAt(c4.x, c4.y);
    await sleep(250);
    R.steps.dragThenDblclickOpensLightbox = await lightboxPresent();
    await closeLightbox();
    // ③ 拖动后不进块编辑（清场：万一命中源码态 <pre> 被切进块编辑，按 Esc 退出）
    R.steps.afterPanBlockEdit = await blockEdit();
    await cdp.pressKey('Escape', { code: 'Escape', vk: 27 });
    await sleep(150);
    R.steps.afterEscapeBlockEdit = await blockEdit();
    // ④ 既有图片 lightbox 仍正常
    R.steps.imageLightbox = await cdp.evalJS(`(function(){
      var pv = document.getElementById('preview'); if (!pv) return 'no-preview';
      var dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="#39f"/></svg>');
      var img = document.createElement('img'); img.src = dataUrl; img.className = '-preview-image'; pv.appendChild(img);
      window.MemoriaMarkdownPreview.attachImageLightbox(pv);
      img.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
      var o = document.querySelector('.-lightbox-overlay'); var b = o ? o.querySelector('.-lightbox-image') : null;
      var out = { open: !!o, bigTag: b ? b.tagName : null, transform: b ? b.style.transform : null };
      if (o) o.remove(); img.remove(); return out;
    })()`);

    // ── 6) 持久化：等写盘 → 磁盘指令行 → 切走再切回（重读磁盘）后视图被还原 ──
    await sleep(2500);
    try { R.steps.diskSource = fs.readFileSync(path.join(kbRoot, file), 'utf8'); } catch (e) { R.steps.diskReadError = String((e && e.message) || e); }
    R.steps.diskHasDirective = anyDirective(R.steps.diskSource || '');
    R.steps.diskInnerLine = innerLine(R.steps.diskSource || '');
    await openFile(cdp, 'corpus/01-ime-zh.md', { skipNav: true });
    await cdp.waitFor(`window.state.currentPath === 'corpus/01-ime-zh.md' && !!window.state.doc`, { label: 'switch-away' });
    await openFile(cdp, file, { skipNav: true });
    await cdp.waitFor(`window.state.currentPath === ${js(file)} && !!window.state.doc`, { label: 'reopen' });
    await ensurePreview(cdp); await waitSvg(); await sleep(400);
    R.steps.reopen = await read();
    R.steps.reopenSource = await srcOf(parseInt(R.steps.reopen && R.steps.reopen.blockIndex, 10));
    if (screenshotsDir) R.screenshots.reopen = await cdp.screenshot(path.join(screenshotsDir, (label || 'view') + '-reopen.png'));
  } catch (e) {
    R.error = String((e && e.stack) || e);
  } finally {
    R.finishedAt = new Date().toISOString();
    cdp.close();
    edge.cleanup();
  }
  return R;
}

// ─────────────────────────────────────────────────────────────────────────────
// 7. CLI
// ─────────────────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) {
      const k = t.slice(2);
      const nxt = argv[i + 1];
      if (nxt && !nxt.startsWith('--')) { a[k] = nxt; i++; } else { a[k] = true; }
    } else a._.push(t);
  }
  return a;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  try {
    if (args.selftest) {
      const r = await selftest();
      process.stdout.write(JSON.stringify(r, null, 2) + '\n');
      process.exit(r.ok ? 0 : 1);
    }
    if (args.probe) {
      if (!args.url || !args['kb-root'] || !args.cases || !args.out) {
        throw new Error('--probe 需要 --url/--kb-root/--cases/--out');
      }
      const r = await runProbe({
        url: args.url,
        kbRoot: args['kb-root'],
        casesPath: args.cases,
        screenshotsDir: args.screenshots ? path.dirname(args.out) : null,
      });
      fs.mkdirSync(path.dirname(args.out), { recursive: true });
      fs.writeFileSync(args.out, JSON.stringify(r, null, 2), 'utf8');
      process.stdout.write('__PROBE_JSON__' + JSON.stringify({ ok: true, out: args.out, cases: Object.keys(r.cases), durationMs: r.durationMs }) + '\n');
      process.exit(0);
    }
    if (args['mermaid-diag']) {
      if (!args.url || !args.out) throw new Error('--mermaid-diag 需要 --url/--out（--file 默认 corpus/04-non-editable.md）');
      const r = await runMermaidDiag({
        url: args.url,
        file: args.file || 'corpus/04-non-editable.md',
        out: args.out,
        label: typeof args.label === 'string' ? args.label : 'diag',
        screenshotsDir: args.screenshots ? path.dirname(args.out) : null,
      });
      fs.mkdirSync(path.dirname(args.out), { recursive: true });
      fs.writeFileSync(args.out, JSON.stringify(r, null, 2), 'utf8');
      process.stdout.write('__MERMAID_DIAG__' + JSON.stringify({ ok: true, out: args.out, metrics: r.steps.metrics, lightboxOpen: r.steps.lightboxOpen }) + '\n');
      process.exit(0);
    }
    if (args['mermaid-view']) {
      if (!args.url || !args.out) throw new Error('--mermaid-view 需要 --url/--out（--file 默认 corpus/04-non-editable.md，--kb-root 便于读盘校验）');
      const r = await runMermaidView({
        url: args.url,
        kbRoot: args['kb-root'] || process.cwd(),
        file: args.file || 'corpus/04-non-editable.md',
        out: args.out,
        label: typeof args.label === 'string' ? args.label : 'view',
        screenshotsDir: args.screenshots ? path.dirname(args.out) : null,
      });
      fs.mkdirSync(path.dirname(args.out), { recursive: true });
      fs.writeFileSync(args.out, JSON.stringify(r, null, 2), 'utf8');
      process.stdout.write('__MERMAID_VIEW__' + JSON.stringify({ ok: !r.error, out: args.out, steps: Object.keys(r.steps) }) + '\n');
      process.exit(r.error ? 1 : 0);
    }
    process.stderr.write('用法: node cdp.mjs --selftest | --probe --url ... --kb-root ... --cases ... --out ... | --mermaid-diag --url ... --out ... | --mermaid-view --url ... --kb-root ... --out ...\n');
    process.exit(2);
  } catch (e) {
    process.stdout.write('__PROBE_JSON__' + JSON.stringify({ ok: false, error: String(e && e.message || e) }) + '\n');
    process.stderr.write('[cdp.mjs] ' + (e && e.stack || e) + '\n');
    process.exit(1);
  }
}

main();
