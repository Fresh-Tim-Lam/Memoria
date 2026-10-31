/**
 * task-63 A1 验收：主线程是否不再冻结（帧间隔采样）+ 全量排版时间
 *
 * 关键测量：
 *  - 页面内 rAF 采样器记录每帧间隔（gap）
 *  - 打开文档 → 等待全量排版完成（supMath + blockMath === 0 且 mjx > 0）
 *  - 报 max gap / p95 gap / 长帧(>50ms)计数
 *
 * 用法: node perf_a1_frames.mjs <port> <out.json> <doc> [rounds] [alt]
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
    const r = await this.send('Runtime.evaluate', { expression: `(function(){ var __v = (${expr}); try { return JSON.stringify(__v === undefined ? null : __v); } catch(e) { return JSON.stringify({_serErr:true}); } })()`, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '')); }
    return r.result ? JSON.parse(r.result.value) : null;
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

for (let i = 0; i < 300; i++) { if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }

// 初始切 preview（模拟真实使用）
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// ── 安装帧采样器 + 完成判定 ──
await cdp.ev(`(function(){
  if (window.__fr) return 1;
  var F = { running: false, gaps: [], last: 0, rafId: null };
  window.__fr = F;

  F.start = function(){
    F.gaps = []; F.last = performance.now(); F.running = true;
    function tick(){
      if (!F.running) return;
      var now = performance.now();
      F.gaps.push(now - F.last);
      F.last = now;
      F.rafId = requestAnimationFrame(tick);
    }
    F.rafId = requestAnimationFrame(tick);
  };
  F.stop = function(){
    F.running = false;
    if (F.rafId) cancelAnimationFrame(F.rafId);
    return F.gaps.slice();
  };

  // 文档状态
  window.__doc = function(){
    var pv = document.getElementById('preview');
    if (!pv) return { err: 'no preview' };
    var sup = pv.querySelectorAll('span.-math:not(:has(mjx-container))').length;
    var blk = pv.querySelectorAll('.-math-block:not(:has(mjx-container))').length;
    return {
      blocks: pv.querySelectorAll('.-src-block').length,
      mjx: pv.querySelectorAll('mjx-container').length,
      supMath: sup, blockMath: blk,
      done: (sup + blk) === 0
    };
  };

  // 等全量排版完成（supMath+blockMath===0 且 mjx>0 且连续 4 帧稳定）
  window.__waitDone = function(timeoutMs){
    var t0 = performance.now(); var stable = 0; var last = -1;
    return new Promise(function(res){
      function tick(){
        var d = window.__doc();
        if (d.mjx > 0 && d.done) {
          if (d.mjx === last) stable++; else stable = 0;
          last = d.mjx;
          if (stable >= 4) { res({ ms: performance.now()-t0, ok: true, state: d }); return; }
        } else { stable = 0; }
        if (performance.now()-t0 > timeoutMs) { res({ ms: performance.now()-t0, ok: false, state: d }); return; }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  return 1;
})()`);

const results = {
  schema: 'memoria-perf-a1-frames/v1',
  startedAt: new Date().toISOString(),
  head: '3516b39b',
  doc: DOC, alt: ALT, rounds: ROUNDS,
  mode: 'realapp + CDP',
  concurrencyBefore: concurrency(),
  rounds_raw: [],
};

// 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true})`);
await sleep(6000);

for (let i = 0; i < ROUNDS; i++) {
  // 切到 alt
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true})`);
  await sleep(1200);

  // 开始采样 → 打开 → 等完成 → 停止（分两步：先跑，再单独取 gaps，避免大数组序列化失败）
  const r = await cdp.ev(`(async function(){
    var pv = document.getElementById('preview');
    if (pv) pv.scrollTop = 0;
    window.__fr.start();
    var t0 = performance.now();
    window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
    var done = await window.__waitDone(60000);
    var total = performance.now() - t0;
    var gaps = window.__fr.stop();
    // 在页面内先算好统计量，只回传标量 + 精简 gaps（避免超大数组）
    var g = gaps.filter(function(x){ return isFinite(x) && x > 0; }).sort(function(a,b){ return a-b; });
    var n = g.length;
    function pct(p){ return n ? g[Math.min(n-1, Math.floor(n*p))] : null; }
    return {
      totalMs: total, doneOk: done.ok, state: done.state,
      frameCount: n,
      maxGap: n ? g[n-1] : null,
      p50Gap: pct(0.5), p95Gap: pct(0.95), p99Gap: pct(0.99),
      longFrames: g.filter(function(x){ return x > 50; }).length,
      veryLongFrames: g.filter(function(x){ return x > 200; }).length,
      top10: g.slice(-10)
    };
  })()`);

  if (!r || r._serErr || r.frameCount === undefined) {
    console.log('[r' + (i + 1) + '] ⚠️ 取数失败: ' + JSON.stringify(r).slice(0, 200));
    continue;
  }
  const g = []; // 不再需要原始数组，统计已在页面内完成
  const n = g.length;
  const rec = {
    totalMs: +r.totalMs.toFixed(1),
    doneOk: r.doneOk,
    state: r.state,
    frameCount: r.frameCount,
    maxGap: r.maxGap === null ? null : +r.maxGap.toFixed(1),
    p50Gap: r.p50Gap === null ? null : +r.p50Gap.toFixed(1),
    p95Gap: r.p95Gap === null ? null : +r.p95Gap.toFixed(1),
    p99Gap: r.p99Gap === null ? null : +r.p99Gap.toFixed(1),
    longFrames: r.longFrames,
    veryLongFrames: r.veryLongFrames,
    top10: r.top10,
  };
  results.rounds_raw.push(rec);
  console.log('[r' + (i + 1) + '] 全量=' + rec.totalMs + 'ms mjx=' + (r.state && r.state.mjx) +
    ' 残留=' + ((r.state ? r.state.supMath + r.state.blockMath : '?')) +
    ' maxGap=' + rec.maxGap + 'ms p95Gap=' + rec.p95Gap + 'ms 长帧(>50)=' + rec.longFrames + ' 超长(>200)=' + rec.veryLongFrames);
  await sleep(400);
}

function stats(arr) {
  const a = arr.filter(x => typeof x === 'number' && isFinite(x)).sort((x, y) => x - y);
  const n = a.length; if (!n) return null;
  const mean = a.reduce((s, x) => s + x, 0) / n;
  const sd = Math.sqrt(a.reduce((s, x) => s + (x - mean) ** 2, 0) / n);
  const pct = (p) => +a[Math.min(n - 1, Math.floor(n * p))].toFixed(1);
  return { n, mean: +mean.toFixed(1), sd: +sd.toFixed(1), p50: pct(0.5), p95: pct(0.95), max: +a[n-1].toFixed(1), raw: a };
}

results.totalMs = stats(results.rounds_raw.map(r => r.totalMs));
results.maxGap = stats(results.rounds_raw.map(r => r.maxGap));
results.p95Gap = stats(results.rounds_raw.map(r => r.p95Gap));
results.longFrames = stats(results.rounds_raw.map(r => r.longFrames));
results.veryLongFrames = stats(results.rounds_raw.map(r => r.veryLongFrames));
results.finalMjx = results.rounds_raw[results.rounds_raw.length - 1].state?.mjx;
results.residualMath = results.rounds_raw[results.rounds_raw.length - 1].state ?
  (results.rounds_raw[results.rounds_raw.length - 1].state.supMath + results.rounds_raw[results.rounds_raw.length - 1].state.blockMath) : null;
results.concurrencyAfter = concurrency();

writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log('__FRAMES__' + JSON.stringify({
  out: outPath,
  totalP50: results.totalMs?.p50, totalP95: results.totalMs?.p95,
  maxGapWorst: results.maxGap?.max, maxGapP50: results.maxGap?.p50,
  p95GapP50: results.p95Gap?.p50, p95GapWorst: results.p95Gap?.max,
  longFramesP50: results.longFrames?.p50,
  finalMjx: results.finalMjx, residualMath: results.residualMath,
  rounds: results.rounds_raw.length,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
