/**
 * task-63 A1 验收：主线程帧间隔 + 全量排版时间（v2，避免 async 序列化问题）
 *
 * 关键改动：不再在页面内跑 async 并返回大对象；
 *   1. 页面内 start 采样 + 触发 openFile（同步返回）
 *   2. Node 侧轮询页面状态直到完成
 *   3. 单独取 gaps 统计（页面内算好标量）
 */
import { writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('timeout')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: `(function(){ try { var __v = (${expr}); if (__v && typeof __v.then === 'function') return JSON.stringify({_promise:true}); return JSON.stringify(__v === undefined ? null : __v); } catch(e) { return JSON.stringify({_err:String(e && e.message || e)}); } })()`,
      returnByValue: true, userGesture: true
    });
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; return { _exc: String((d.exception && (d.exception.description || d.exception.value)) || d.text || '') }; }
    try { return r.result ? JSON.parse(r.result.value) : null; } catch (e) { return { _parseErr: true, raw: String(r.result && r.result.value).slice(0, 200) }; }
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2]);
const outPath = process.argv[3];
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';
const ROUNDS = Number(process.argv[5] || 10);
const ALT = process.argv[6] || 'homework/README.md';

function concurrency() {
  let mem = [], wv = 0;
  try {
    const o = execFileSync('powershell', ['-NoProfile', '-Command',
      "Get-Process -Name Memoria -EA SilentlyContinue | ForEach-Object { \"$($_.Id)|$([Math]::Round($_.CPU,1))\" }; 'WV:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count"],
      { encoding: 'utf8', timeout: 15000 });
    for (const line of o.split(/\r?\n/)) {
      if (line.startsWith('WV:')) wv = Number(line.slice(3));
      else if (line.includes('|')) { const [p, c] = line.split('|'); mem.push({ pid: +p, cpuSec: +c }); }
    }
  } catch (e) { /* */ }
  return { memoriaExe: mem, webview2Count: wv, at: new Date().toISOString() };
}

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
for (let i = 0; i < 300; i++) { const v = await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface'); if (v === true) break; await sleep(200); }

// 切 preview
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// 安装采样器（全同步）
const inst = await cdp.ev(`(function(){
  if (window.__fr) return { already: true };
  var F = { running: false, gaps: [], last: 0, rafId: null, startAt: 0 };
  window.__fr = F;
  F.start = function(){
    F.gaps = []; F.last = performance.now(); F.startAt = F.last; F.running = true;
    function tick(){
      if (!F.running) return;
      var now = performance.now();
      F.gaps.push(now - F.last);
      F.last = now;
      F.rafId = requestAnimationFrame(tick);
    }
    F.rafId = requestAnimationFrame(tick);
  };
  F.stop = function(){ F.running = false; if (F.rafId) cancelAnimationFrame(F.rafId); return 1; };
  F.stats = function(){
    var g = F.gaps.filter(function(x){ return isFinite(x) && x > 0; }).sort(function(a,b){ return a-b; });
    var n = g.length;
    function pct(p){ return n ? +g[Math.min(n-1, Math.floor(n*p))].toFixed(1) : null; }
    return {
      frameCount: n,
      maxGap: n ? +g[n-1].toFixed(1) : null,
      p50Gap: pct(0.5), p95Gap: pct(0.95), p99Gap: pct(0.99),
      longFrames: g.filter(function(x){ return x > 50; }).length,
      veryLongFrames: g.filter(function(x){ return x > 200; }).length,
      top10: g.slice(-10).map(function(x){ return +x.toFixed(1); }),
      elapsed: +(performance.now() - F.startAt).toFixed(1)
    };
  };
  window.__doc = function(){
    var pv = document.getElementById('preview');
    if (!pv) return { err: 'no preview' };
    var sup = pv.querySelectorAll('span.-math:not(:has(mjx-container))').length;
    var blk = pv.querySelectorAll('.-math-block:not(:has(mjx-container))').length;
    return {
      blocks: pv.querySelectorAll('.-src-block').length,
      mjx: pv.querySelectorAll('mjx-container').length,
      supMath: sup, blockMath: blk,
      done: (sup + blk) === 0 && pv.querySelectorAll('mjx-container').length > 0
    };
  };
  return { ok: true };
})()`);
console.log('探针: ' + JSON.stringify(inst));

const results = {
  schema: 'memoria-perf-a1-frames/v2',
  startedAt: new Date().toISOString(),
  head: '3516b39b', doc: DOC, alt: ALT, rounds: ROUNDS,
  mode: 'realapp + CDP', concurrencyBefore: concurrency(), rounds_raw: [],
};

// 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true})`);
await sleep(8000);

for (let i = 0; i < ROUNDS; i++) {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true})`);
  await sleep(1200);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); if(p) p.scrollTop=0; return 1; })()`);

  // 1) 启动采样 + t0
  await cdp.ev(`(function(){ window.__fr.start(); return 1; })()`);
  const t0 = Date.now();

  // 2) 触发 openFile（同步，不 await）
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);

  // 3) Node 侧轮询直到完成
  let done = false, lastState = null, stable = 0, lastMjx = -1;
  for (let k = 0; k < 600; k++) {
    await sleep(100);
    const d = await cdp.ev('window.__doc()');
    lastState = d;
    if (d && d.done) {
      if (d.mjx === lastMjx) stable++; else stable = 0;
      lastMjx = d.mjx;
      if (stable >= 3) { done = true; break; }
    } else stable = 0;
  }
  const totalMs = Date.now() - t0;

  // 4) 停止并取统计
  await cdp.ev('window.__fr.stop()');
  const st = await cdp.ev('window.__fr.stats()');

  const rec = {
    totalMs, doneOk: done, state: lastState,
    ...(st && !st._err ? st : {}),
  };
  results.rounds_raw.push(rec);
  console.log('[r' + (i + 1) + '] 全量=' + totalMs + 'ms mjx=' + (lastState && lastState.mjx) +
    ' 残留=' + (lastState ? lastState.supMath + lastState.blockMath : '?') +
    ' maxGap=' + (st && st.maxGap) + ' p95Gap=' + (st && st.p95Gap) +
    ' 长帧(>50)=' + (st && st.longFrames) + ' 超长(>200)=' + (st && st.veryLongFrames));
  await sleep(500);
}

function stats(arr) {
  const a = arr.filter(x => typeof x === 'number' && isFinite(x)).sort((x, y) => x - y);
  const n = a.length; if (!n) return null;
  const mean = a.reduce((s, x) => s + x, 0) / n;
  const sd = Math.sqrt(a.reduce((s, x) => s + (x - mean) ** 2, 0) / n);
  const pct = (p) => +a[Math.min(n - 1, Math.floor(n * p))].toFixed(1);
  return { n, mean: +mean.toFixed(1), sd: +sd.toFixed(1), p50: pct(0.5), p95: pct(0.95), max: +a[n-1].toFixed(1) };
}

const R = results.rounds_raw;
results.totalMs = stats(R.map(r => r.totalMs));
results.maxGap = stats(R.map(r => r.maxGap));
results.p95Gap = stats(R.map(r => r.p95Gap));
results.longFrames = stats(R.map(r => r.longFrames));
results.veryLongFrames = stats(R.map(r => r.veryLongFrames));
results.finalMjx = R.length ? R[R.length - 1].state?.mjx : null;
results.residualMath = R.length && R[R.length - 1].state ? (R[R.length - 1].state.supMath + R[R.length - 1].state.blockMath) : null;
results.allDone = R.every(r => r.doneOk);
results.concurrencyAfter = concurrency();

writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log('__FRAMES__' + JSON.stringify({
  out: outPath,
  rounds: R.length,
  totalP50: results.totalMs?.p50, totalP95: results.totalMs?.p95, totalMax: results.totalMs?.max,
  maxGapP50: results.maxGap?.p50, maxGapWorst: results.maxGap?.max,
  p95GapP50: results.p95Gap?.p50, p95GapWorst: results.p95Gap?.max,
  longFramesP50: results.longFrames?.p50,
  finalMjx: results.finalMjx, residualMath: results.residualMath, allDone: results.allDone,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
