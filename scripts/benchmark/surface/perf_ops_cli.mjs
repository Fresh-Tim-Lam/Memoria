#!/usr/bin/env node
/**
 * perf_ops_cli.mjs —— 绩效操作矩阵 CLI（执行场景 + 落盘）
 *
 * 两种输入模式**互斥**：
 *   --url <harness URL>   自起无头 Edge 并导航（纯交互类可用；公式/首开受限）
 *   --cdp <CDP endpoint>  attach 已运行真机（首开/公式必须用这个）
 *
 * 用法：
 *   node perf_ops_cli.mjs --url http://127.0.0.1:8645/ --ops all --rounds 3 --out out.json
 *   node perf_ops_cli.mjs --cdp http://127.0.0.1:9500 --ops open,scroll --rounds 3 --out out.json
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { PERF_PROBE } from './perf_ops.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const EDGE_CANDIDATES = [
  process.env.MEMORIA_EDGE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);
function findEdge() {
  for (const p of EDGE_CANDIDATES) { try { if (fs.existsSync(p)) return p; } catch { /* noop */ } }
  throw new Error('找不到 msedge.exe；可用 MEMORIA_EDGE 指定');
}
async function httpJson(url) { const r = await fetch(url); return await r.json(); }

async function launchEdge() {
  const edgePath = findEdge();
  const cdpPort = 9222 + Math.floor(Math.random() * 3000);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'memoria-perfops-edge-'));
  const args = ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-background-networking', '--remote-allow-origins=*',
    // !! 取消 --disable-frame-rate-limit：实测会让 rAF 无节制（150 帧仅 1.2ms 间隔），
    //    帧间隔失去意义。保留 vsync（60Hz 基准 16.7ms）才是用户真实观感。
    //    滚动卡顿改用「帧间隔超出 1.5 帧预算的比例 + 长任务」判定（见 perf_ops.mjs opScroll）。
    `--remote-debugging-port=${cdpPort}`, `--user-data-dir=${userDataDir}`, 'about:blank'];
  const proc = spawn(edgePath, args, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d.toString(); });
  const base = `http://127.0.0.1:${cdpPort}`;
  const t0 = Date.now();
  let version = null;
  for (;;) {
    try { version = await httpJson(base + '/json/version'); if (version && version.webSocketDebuggerUrl) break; } catch { /* not up */ }
    if (Date.now() - t0 > 20000) { try { proc.kill(); } catch { /* noop */ } throw new Error('Edge CDP 未就绪: ' + stderr.slice(0, 500)); }
    await sleep(200);
  }
  const list = await httpJson(base + '/json/list').catch(() => []);
  let page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!page) { try { page = await httpJson(base + '/json/new?about:blank'); } catch { /* noop */ } }
  const wsUrl = (page && page.webSocketDebuggerUrl) || version.webSocketDebuggerUrl;
  return {
    proc, wsUrl, browser: version.Browser || 'Edge',
    cleanup() { try { proc.kill(); } catch { /* noop */ } try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { /* noop */ } },
  };
}

async function resolveCdpWs(endpoint) {
  const base = String(endpoint).replace(/\/+$/, '');
  const list = await httpJson(base + '/json/list').catch(() => null);
  if (!list) throw new Error('CDP endpoint 无响应：' + base);
  const pages = (list || []).filter((t) => t.type === 'page' && t.webSocketDebuggerUrl &&
    !/^devtools:\/\//.test(t.url || '') && !/^about:blank$/i.test(t.url || ''));
  if (!pages.length) throw new Error('找不到应用页面目标');
  return pages[0].webSocketDebuggerUrl;
}

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(u);
      const to = setTimeout(() => rej(new Error('CDP WS 超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('CDP WS 失败')); });
    });
  }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); }
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expr, { timeout = 60000, interval = 150, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) { let v; try { v = await this.evalJS(expr); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '')); await sleep(interval); }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }

  /** 受信任按键：keyDown(text) + keyUp，走 Blink 编辑管线（产生真实 beforeinput）。 */
  async pressKey(ch, opts = {}) {
    const down = { type: 'keyDown', text: ch, unmodifiedText: ch, key: ch };
    const up = { type: 'keyUp', key: ch };
    if (opts.ctrl) { down.modifiers = 2; up.modifiers = 2; }
    if (opts.code) { down.code = opts.code; up.code = opts.code; }
    const vk = opts.vk != null ? opts.vk : ch.toUpperCase().charCodeAt(0);
    if (Number.isFinite(vk)) { down.windowsVirtualKeyCode = vk; down.nativeVirtualKeyCode = vk; up.windowsVirtualKeyCode = vk; up.nativeVirtualKeyCode = vk; }
    await this.send('Input.dispatchKeyEvent', down);
    await this.send('Input.dispatchKeyEvent', up);
  }
}

// ══════════════════════════════════════════════════════════════════════════
// 真实按键驱动（Node 侧）：走 Input.dispatchKeyEvent => Blink 真实编辑管线
//   !! 为什么不用页面内 execCommand('insertText')：实测 p50 16.95ms 但 p95 60.65ms，
//   离散过大 —— 它走的是浏览器默认编辑路径，与用户真实按键路径不同。
//   受信任按键才和 phase1 既有 11.15ms 口径一致。
//   计时仍是页面内 performance.now()，保证度量与输入来源解耦。
// ══════════════════════════════════════════════════════════════════════════
async function focusEditable(cdp) {
  // !! 必须传**字符串**给 evalJS（在页面内求值）。首版误写成 (function(){...})()
  //    直接在 Node 里执行了 => ReferenceError: document is not defined。
  const t = await cdp.evalJS(`(function(){
    var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
    for (var i = 0; i < els.length; i++) {
      var c = String(els[i].className || '');
      if (c.indexOf('-code-block') < 0 && c.indexOf('-table') < 0 && c.indexOf('-math-block') < 0 &&
          c.indexOf('-mermaid') < 0 && c.indexOf('-blank-block') < 0 && c.indexOf('-frontmatter') < 0 &&
          els[i].textContent.trim().length > 4) {
        var r = els[i].getBoundingClientRect();
        return { ok: true, x: r.left + 24, y: r.top + Math.min(10, r.height / 2) };
      }
    }
    return { ok: false };
  })()`);
  if (t && t.ok) {
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: t.x, y: t.y });
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: t.x, y: t.y, button: 'left', clickCount: 1 });
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: t.x, y: t.y, button: 'left', clickCount: 1 });
  }
  await sleep(250);
}

async function runTypingReal(cdp, ctx) {
  await focusEditable(cdp);
  const keys = ctx.keys || 10, warm = ctx.warmup || 3;
  // 口径：一次按键的**编辑管线耗时**（beforeinput -> input/DOM 更新完成），
  //   完全在页面内测量并累加，只回传数组（避免 CDP 往返 ~33ms 淹没真实时延）。
  //   同时用 CDP 受信任按键驱动（Input.dispatchKeyEvent），保证走真实编辑管线。
  const res = await cdp.evalJS(`(async function(){
    window.__poKeys = [];
    var el = null;
    var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
    for (var i = 0; i < els.length; i++) {
      var c = String(els[i].className || '');
      if (c.indexOf('-code-block') < 0 && c.indexOf('-table') < 0 && c.indexOf('-math-block') < 0 &&
          c.indexOf('-mermaid') < 0 && c.indexOf('-blank-block') < 0 && c.indexOf('-frontmatter') < 0 &&
          els[i].textContent.trim().length > 4) { el = els[i]; break; }
    }
    if (!el) return { samples: [], error: 'no-editable-block' };
    window.__poTarget = el;
    window.__poArmed = true;
    return { armed: true };
  })()`);
  if (!res || !res.armed) return { samples: [], error: (res && res.error) || 'arm-failed' };

  // 页面内 hook：beforeinput 起测，input 收测（同步完成）
  await cdp.evalJS(`(function(){
    if (window.__poKeyHook) return 1;
    window.__poKeyHook = true;
    var _t0 = null;
    document.addEventListener('beforeinput', function(){ _t0 = performance.now(); }, true);
    document.addEventListener('input', function(){
      if (_t0 != null) { window.__poKeys.push(performance.now() - _t0); _t0 = null; }
    }, true);
    return 1;
  })()`);

  const samples = [];
  for (let i = 0; i < warm + keys; i++) {
    await cdp.pressKey('z', { code: 'KeyZ', vk: 90 });
    await sleep(70);   // 让页面内 hook 有机会记录
    if (i >= warm) {
      const got = await cdp.evalJS('window.__poKeys.length ? window.__poKeys[window.__poKeys.length-1] : null');
      if (got != null) samples.push(got);
    }
  }
  // 兜底：若 hook 一条未记录，退化为"页面内 execCommand 同步计时"
  if (!samples.length) {
    const fallback = await cdp.evalJS(`(function(){
      var out = [];
      var el = window.__poTarget || document.querySelector('#preview .-src-block');
      if (!el) return [];
      for (var i = 0; i < 10; i++) {
        var t0 = performance.now();
        document.execCommand('insertText', false, 'z');
        out.push(performance.now() - t0);
      }
      return out;
    })()`);
    return { samples: fallback || [], timingMode: 'fallback-execCommand' };
  }
  return { samples, timingMode: 'beforeinput-input' };
}
async function runUndoReal(cdp, ctx) {
  await focusEditable(cdp);
  const rounds = ctx.rounds || 5;
  const samples = [];
  for (let i = 0; i < rounds; i++) {
    await cdp.pressKey('x', { code: 'KeyX', vk: 88 });
    await cdp.evalJS('new Promise(r=>requestAnimationFrame(()=>r(1)))');
    await cdp.evalJS('window.__poT0 = performance.now(); 1');   // 页面内起测
    await cdp.pressKey('z', { code: 'KeyZ', vk: 90, ctrl: true });   // Ctrl+Z => app.js:7263
    samples.push(await cdp.evalJS('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(performance.now()-window.__poT0))))'));
  }
  return { samples };
}

async function runStructEditReal(cdp, ctx) {
  await focusEditable(cdp);
  const rounds = ctx.rounds || 4;
  const samples = [];
  for (let i = 0; i < rounds; i++) {
    await cdp.evalJS('window.__poT0 = performance.now(); 1');
    await cdp.pressKey('\r', { code: 'Enter', vk: 13 });             // 回车拆段
    samples.push(await cdp.evalJS('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(performance.now()-window.__poT0))))'));
    await sleep(150);
    await cdp.evalJS('window.__poT0 = performance.now(); 1');
    await cdp.pressKey('\b', { code: 'Backspace', vk: 8 });          // 退格合并
    samples.push(await cdp.evalJS('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(performance.now()-window.__poT0))))'));
    await sleep(150);
  }
  return { samples };
}

// ── 操作注册表（与 perf_ops.mjs 的 PO.opXxx 对应）──
//   tier: A 必测 / B 记录
//   mode: headless-ok / realapp-required
//   metric: latency（ms p50/p95）/ frames（帧间隔 p95 + 长任务）/ heap（MB delta）
const OPS = [
  { id: 'typing',        tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opTyping',     ctx: { keys: 10, warmup: 3 }, doc: 'scale/scale-5k.md' },
  { id: 'scroll',        tier: 'A', mode: 'headless-ok',       metric: 'frames',  fn: 'opScroll',     ctx: { scrollPx: 2000 },      doc: 'scale/scale-5k.md' },
  { id: 'select',        tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opSelect',     ctx: { rounds: 5 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'paste',         tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opPaste',      ctx: { rounds: 5 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'undo',          tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opUndo',       ctx: { rounds: 5 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'find',          tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opFind',       ctx: {},                      doc: 'corpus/03-block-boundaries.md' },
  { id: 'save',          tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opSave',       ctx: { rounds: 5 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'viewSwitch',    tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opViewSwitch', ctx: { rounds: 3 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'structEdit',    tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opStructEdit', ctx: { rounds: 4 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'format',        tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opFormat',     ctx: { rounds: 5 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'kpHover',       tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opKpHover',    ctx: { rounds: 5 },           doc: 'corpus/03-block-boundaries.md' },
  { id: 'open',          tier: 'A', mode: 'realapp-required',  metric: 'latency', fn: 'opOpen',       ctx: { rounds: 3, openFile: 'scale/scale-5k.md' }, doc: 'scale/scale-5k.md' },
  { id: 'tabSwitch',     tier: 'A', mode: 'headless-ok',       metric: 'latency', fn: 'opTabSwitch',  ctx: { rounds: 4 },           doc: 'corpus/01-ime-zh.md' },
  { id: 'memGrowth',     tier: 'B', mode: 'headless-ok',       metric: 'heap',    fn: 'opMemGrowth',  ctx: { cycles: 12 },          doc: 'corpus/01-ime-zh.md' },
];

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) { const k = t.slice(2); const n = argv[i + 1]; if (n && !n.startsWith('--')) { a[k] = n; i++; } else a[k] = true; }
    else a._.push(t);
  }
  return a;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const harnessUrl = typeof args.url === 'string' ? args.url : null;
  const cdpEndpoint = typeof args.cdp === 'string' ? args.cdp : null;
  const out = args.out || null;
  const rounds = parseInt(args.rounds || '3', 10);
  const inject = args.inject || null;      // 注入已知退化：busywait

  if (harnessUrl && cdpEndpoint) { process.stderr.write('错误：--url 与 --cdp 互斥\n'); return 2; }
  if (!harnessUrl && !cdpEndpoint) { process.stderr.write('错误：需 --url 或 --cdp\n'); return 2; }

  let want = String(args.ops || 'all');
  if (want === 'all') want = OPS.map((o) => o.id);
  else want = want.split(',').map((s) => s.trim()).filter(Boolean);
  const selected = OPS.filter((o) => want.includes(o.id));
  if (!selected.length) { process.stderr.write('错误：--ops 无匹配\n'); return 2; }

  const result = {
    schema: 'memoria-perf-ops-run/v1',
    mode: harnessUrl ? 'headless' : 'realapp',
    harnessUrl: harnessUrl || null,
    cdpEndpoint: cdpEndpoint || null,
    rounds, inject,
    startedAt: new Date().toISOString(),
    ops: {},
  };

  let edge = null, cdp = null, exitCode = 1;
  try {
    if (harnessUrl) {
      edge = await launchEdge();
      result.environment = { browser: edge.browser, mode: 'headless' };
      cdp = await CDP.connect(edge.wsUrl);
      await cdp.send('Page.enable'); await cdp.send('Runtime.enable');
      await cdp.send('Page.navigate', { url: harnessUrl });
      await cdp.waitFor('document.readyState === "complete"', { timeout: 60000, label: 'readyState' });
    } else {
      const wsUrl = await resolveCdpWs(cdpEndpoint);
      result.environment = { mode: 'realapp', cdpEndpoint };
      cdp = await CDP.connect(wsUrl);
      await cdp.send('Runtime.enable');
    }
    await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', { label: 'app', timeout: 90000 });

    // ── task-47 L1：--surface legacy|new（同会话切插头，用于 A/B 双侧对照）──
    //    ★ 必须能切到指定插头并确认生效，否则两侧测的是同一个插头 ⇒ 假"无差异"。
    const wantSurface = (typeof args.surface === 'string' && args.surface) ? String(args.surface) : null;
    if (wantSurface) {
      if (wantSurface !== 'legacy' && wantSurface !== 'new') {
        process.stderr.write('错误：--surface 只能是 legacy 或 new\n'); return 2;
      }
      const hasSurfaceApi = await cdp.evalJS('!!(window.MemoriaSurface && window.MemoriaSurface.switchTo)');
      if (!hasSurfaceApi) {
        process.stderr.write('错误：--surface 需要 window.MemoriaSurface（该构建未提供）\n'); return 2;
      }
      await cdp.evalJS(`window.MemoriaSurface.switchTo(${JSON.stringify(wantSurface)})`);
      await cdp.waitFor(`window.MemoriaSurface.current() === ${JSON.stringify(wantSurface)}`,
                        { timeout: 60000, label: 'surface:' + wantSurface });
      // 确认生效（读到实际 current，写进产物，供事后核对）
      result.surface = await cdp.evalJS('window.MemoriaSurface.current()');
      result.surfaceList = await cdp.evalJS('window.MemoriaSurface.list()');
    } else {
      result.surface = null;
      result.surfaceList = await cdp.evalJS('(window.MemoriaSurface && window.MemoriaSurface.list) ? window.MemoriaSurface.list() : null');
    }

    // 注入探针
    await cdp.evalJS('window.__perfops = ' + PERF_PROBE);


    // 可选：注入已知退化（用于自证判别力）
    if (inject === 'busywait') {
      await cdp.evalJS(`(function(){
        window.__injectBusywaitMs = 25;
        if (!window.__injectPatched) {
          window.__injectPatched = true;
          var origRAF = window.requestAnimationFrame.bind(window);
          window.requestAnimationFrame = function(cb) {
            return origRAF(function(t){
              var until = performance.now() + window.__injectBusywaitMs;
              while (performance.now() < until) { /* busy wait */ }
              cb(t);
            });
          };
        }
        return window.__injectBusywaitMs;
      })()`);
      result.injected = { kind: 'busywait', ms: 25 };
    }

    for (const op of selected) {
      const opResult = { id: op.id, tier: op.tier, mode: op.mode, metric: op.metric, doc: op.doc, runs: [] };
      try {
        // 每次进入正确文档
        await cdp.evalJS(`window.__perfops.openDoc(${JSON.stringify(op.doc)}, ${JSON.stringify({ requirePreview: true })})`)
          .catch(() => { /* openDoc 内部已容错 */ });
        await sleep(500);

        for (let r = 0; r < rounds; r++) {
          const ctx = JSON.stringify(op.ctx || {});
          let res;
          if (op.id === 'typing') { res = await runTypingReal(cdp, op.ctx || {}); }
          else if (op.id === 'undo') { res = await runUndoReal(cdp, op.ctx || {}); }
          else if (op.id === 'structEdit') { res = await runStructEditReal(cdp, op.ctx || {}); }
          else { res = await cdp.evalJS(`window.__perfops.${op.fn}(${ctx})`); }
          opResult.runs.push(res);
          await sleep(250);
        }
        opResult.status = 'ran';
      } catch (e) {
        opResult.status = 'error';
        opResult.error = String((e && e.message) || e);
      }
      result.ops[op.id] = opResult;
    }

    result.ok = true;
    exitCode = 0;
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) cdp.close();
    if (edge) edge.cleanup();
    setTimeout(() => process.exit(exitCode), 2000).unref();
  }

  const text = JSON.stringify(result, null, 2);
  if (out) {
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, text, 'utf8');
    process.stdout.write('__PERFOPS__' + JSON.stringify({ ok: result.ok, out, ops: Object.keys(result.ops) }) + '\n');
  } else process.stdout.write(text + '\n');
  return exitCode;
}

const code = await main();
process.exitCode = code;
