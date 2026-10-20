#!/usr/bin/env node
/**
 * realapp_probe.mjs —— attach 到**正在运行的真实 Memoria 应用**（WebView2）并验证可用性
 *
 * 不是启动器：应用由调用方用 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<port>
 * 启动好，本脚本只做「发现页面目标 → attach → 读状态」。
 *
 * 用法：
 *   node scripts/benchmark/surface/realapp_probe.mjs --port 9500
 *   node scripts/benchmark/surface/realapp_probe.mjs --port 9500 --out raw.json
 */

import fs from 'node:fs';
import path from 'node:path';

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
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function httpJson(url, timeoutMs = 3000) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    return await r.json();
  } finally { clearTimeout(to); }
}

/** 极简 CDP（与 cdp.mjs / interaction.mjs 同款，独立一份避免耦合） */
class CDP {
  constructor(ws) {
    this.ws = ws;
    this._id = 0;
    this._pending = new Map();
    ws.addEventListener('message', (ev) => this._onMessage(ev.data));
  }
  static connect(wsUrl) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl);
      const to = setTimeout(() => reject(new Error('CDP WebSocket 连接超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); resolve(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); reject(new Error('CDP 连接失败: ' + wsUrl)); });
    });
  }
  _onMessage(data) {
    let msg;
    try { msg = JSON.parse(typeof data === 'string' ? data : String(data)); } catch { return; }
    if (msg.id == null) return;
    const p = this._pending.get(msg.id);
    if (!p) return;
    this._pending.delete(msg.id);
    if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
    else p.resolve(msg.result);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this._id;
      this._pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async evalJS(expression, { awaitPromise = true } = {}) {
    const r = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise, userGesture: true,
    });
    if (r && r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error('evalJS 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]);
    }
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expression, { timeout = 30000, interval = 120, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) {
      let v;
      try { v = await this.evalJS(expression); } catch { v = false; }
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '') + ': ' + expression);
      await sleep(interval);
    }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

/**
 * 找到一个**应用页面**的目标（排除 devtools:// 与 about:blank）。
 * WebView2 的 DevTools 也会以 type=page 出现在 /json/list 里 ⇒ 必须按 URL 过滤。
 */
export async function findAppTarget(port, { timeoutMs = 30000, predicate = null } = {}) {
  const t0 = Date.now();
  let last = null;
  for (;;) {
    try {
      const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
      const pages = (list || []).filter((t) =>
        t.type === 'page' && t.webSocketDebuggerUrl &&
        !/^devtools:\/\//.test(t.url || '') && !/^about:blank$/.test(t.url || ''));
      last = pages;
      const hit = predicate ? pages.find(predicate) : pages[0];
      if (hit) return hit;
    } catch (e) { last = String(e && e.message || e); }
    if (Date.now() - t0 > timeoutMs) {
      throw new Error(`在 127.0.0.1:${port} 上找不到应用页面目标。最后看到: ${JSON.stringify(last)}`);
    }
    await sleep(300);
  }
}

/** 应用是否就绪（与 cdp.mjs 的 app-ready 判据一致） */
export async function waitAppReady(cdp, { timeout = 60000 } = {}) {
  await cdp.waitFor(
    `!!(window.MemoriaApp && window.state && window.state.kbPath && window.state.doc)`,
    { timeout, label: 'app-ready+doc' }
  );
  return true;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const port = parseInt(args.port || '9500', 10);
  const out = args.out || null;
  const result = { schema: 'memoria-realapp-probe/v1', port, startedAt: new Date().toISOString() };
  let cdp = null;
  let exitCode = 1;
  try {
    const version = await httpJson(`http://127.0.0.1:${port}/json/version`);
    result.browser = version.Browser;
    result.cdpWorks = true;
    const target = await findAppTarget(port);
    result.target = { id: target.id, title: target.title, url: target.url };
    cdp = await CDP.connect(target.webSocketDebuggerUrl);
    await cdp.send('Runtime.enable');
    await waitAppReady(cdp);
    result.appReady = true;
    result.state = await cdp.evalJS(`(function(){
      var s = window.state || {};
      return {
        kbPath: s.kbPath || null,
        currentPath: s.currentPath || null,
        viewMode: s.viewMode || null,
        docLines: (s.doc && s.doc.lines) ? s.doc.lines.length : null,
        files: (s.files || []).length,
        editMode: !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode),
      };
    })()`);
    result.preview = await cdp.evalJS(`(function(){
      return {
        blocks: document.querySelectorAll('#preview .-src-block').length,
        mjx: document.querySelectorAll('#preview mjx-container').length,
        mathSpans: document.querySelectorAll('#preview .-math').length,
        svg: document.querySelectorAll('#preview svg').length,
        loading: !!document.querySelector('#preview .-preview-loading'),
      };
    })()`);
    result.mathjax = await cdp.evalJS(`(function(){
      var M = window.MathJax;
      return { present: !!M, hasTypeset: !!(M && typeof M.typesetPromise === 'function') };
    })()`);
    // GPU / 渲染路径签名（真机 vs 无头的区分证据）
    result.gpu = await cdp.evalJS(`(function(){
      try {
        var c = document.createElement('canvas');
        var gl = c.getContext('webgl') || c.getContext('experimental-webgl');
        if (!gl) return { webgl: false };
        var dbg = gl.getExtension('WEBGL_debug_renderer_info');
        return {
          webgl: true,
          vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
          renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
        };
      } catch (e) { return { webgl: false, error: String(e) }; }
    })()`);
    result.ok = true;
    exitCode = 0;
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) cdp.close();
    // WebView2 的 DevTools 用的是 browser 级 WS：直接 process.exit 会在 libuv 里触发
    // `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)`（已实测）。
    // 先让 WS 优雅关闭、脚本自然退出；仅在卡住时兜底强制退出。
    setTimeout(() => process.exit(exitCode), 4000).unref();
  }
  const text = JSON.stringify(result, null, 2);
  if (out) {
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, text, 'utf8');
    process.stdout.write('__REALAPP_PROBE__' + JSON.stringify({ ok: result.ok, out }) + '\n');
  } else {
    process.stdout.write(text + '\n');
  }
  return exitCode;
}

if (import.meta.url === `file:///${process.argv[1].replace(/\\/g, '/')}`) {
  const code = await main();
  process.exitCode = code;
}
