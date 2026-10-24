/**
 * W3.3 批尾强制布局 —— **同 build、同实例、交错 A/B** 探针。
 *
 * 背景：`lazy_evict` 每批批尾读一次 `pane.scrollHeight` ⇒ 强制全篇布局（批均 ~21ms、尖峰 150–180ms）。
 * 本探针在同一页面实例里交替切换 `window.__MEMORIA_TAIL_LAYOUT.setMode('legacy'|'pred'|'noSh')`，
 * 因此 A/B 不受整机负载/跨会话漂移影响（上一轮跨轮数据曾差 2–8×）。
 *
 * 口径：
 *   · 真机 pywebview + WebView2（GPU 必须是硬件）；`MEMORIA_DEBUG=0`；
 *   · `max_frame_ms` 来自 `MemoriaScheduler.counters()`，每轮 reset 后读取（不在帧回调里读）；
 *   · 帧间隔 rAF、长任务 PerformanceObserver（页面内只 push 数字）；
 *   · 独立高度稳定性：每轮**回到顶部并 quiet 后**记录 `scrollHeight`（跨轮比较；不依赖 app 内部指标）；
 *   · `Performance.getMetrics` 的 LayoutCount/LayoutDuration/RecalcStyle* 每轮前后差值（真实布局工作量）；
 *   · 打开前先量空转 rAF（p50 ≤ 20ms 才采信），`totalBlocks >= 3900` 否则拒跑。
 *
 * 用法：
 *   node scripts/benchmark/surface/perf_tail_ab.mjs <port> <out.json> [--rounds 12] [--fast-frames 80]
 *        [--warmup 1] [--order LPPLLPPLLPPL] [--timeout-ms 600000]
 */
import { writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  if (i < 0) return def;
  const v = process.argv[i + 1];
  return v && !v.startsWith('--') ? v : true;
}
const port = Number(process.argv[2]);
const outPath = process.argv[3];
if (!port || !outPath) { console.error('usage: node perf_tail_ab.mjs <port> <out.json>'); process.exit(2); }
const DOC = arg('doc', '教材/08_第8章_差错控制编码.md');
const FAST_FRAMES = Number(arg('fast-frames', 80));
const WARMUP = Number(arg('warmup', 1));
const ORDER = String(arg('order', 'LPPLLPPLLPPL'));
const ROUNDS = Math.min(Number(arg('rounds', ORDER.length)), ORDER.length);
const QUIET_MS = Number(arg('quiet-ms', 60000));
const MODE = { L: 'legacy', P: 'pred', N: 'noSh' };

async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) {
    this.ws = ws; this._id = 0; this._p = new Map();
    ws.addEventListener('message', (e) => this._on(e.data));
  }
  static connect(u) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(u);
      const to = setTimeout(() => rej(new Error('ws timeout')), 25000);
      ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); });
    });
  }
  _on(d) {
    let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; }
    if (m.id == null) return;
    const p = this._p.get(m.id); if (!p) return;
    this._p.delete(m.id);
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
  send(method, params = {}, timeoutMs = 300000) {
    return new Promise((res, rej) => {
      const id = ++this._id;
      const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs);
      this._p.set(id, {
        resolve: (v) => { clearTimeout(to); res(v); },
        reject: (e) => { clearTimeout(to); rej(e); },
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async ev(expr, awaitPromise = true) {
    const r = await this.send('Runtime.evaluate', {
      expression: expr, returnByValue: true, awaitPromise, userGesture: true,
    });
    if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || '') +
      ' ' + JSON.stringify(r.exceptionDetails.exception && r.exceptionDetails.exception.description || '').slice(0, 400));
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expr, timeoutMs = 90000, stepMs = 200) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      try { if (await this.ev(`!!(${expr})`, false)) return true; } catch { /* reloading */ }
      await sleep(stepMs);
    }
    return false;
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

let page = null;
for (let a = 0; a < 60; a++) {
  try {
    const l = await httpJson(`http://127.0.0.1:${port}/json/list`);
    page = (l || []).find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+\//.test(t.url || '') &&
      !/devtools/.test(t.url || '') && t.webSocketDebuggerUrl);
    if (page) break;
  } catch { /* app not up */ }
  await sleep(1000);
}
if (!page) { console.error('no page on port ' + port); process.exit(2); }
console.log('[page]', page.title, page.url);

const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Performance.enable').catch(() => {});
await cdp.send('HeapProfiler.enable').catch(() => {});

if (!(await cdp.waitFor('window.MemoriaApp && window.MemoriaApp.openFile', 120000))) {
  console.error('app not ready'); process.exit(2);
}
const gpu = await cdp.ev(`(function(){try{var c=document.createElement('canvas');var gl=c.getContext('webgl')||c.getContext('experimental-webgl');if(!gl)return {webgl:false};var e=gl.getExtension('WEBGL_debug_renderer_info');return {webgl:true,renderer:e?gl.getParameter(e.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)};}catch(err){return {webgl:false,err:String(err)}}})()`, false);
if (!gpu || !gpu.webgl) { console.error('webgl unavailable — 不是真机口径:', JSON.stringify(gpu)); process.exit(2); }
console.log('[gpu]', gpu.renderer);

/* ── 页面内探针（幂等） ── */
await cdp.ev(`(function(){
  window.__MEMORIA_LAZY = true;
  try { localStorage.setItem('memoria.perf.lazy','1'); } catch(e) {}
  var b = document.querySelector('.-view-btn[data-view="preview"]'); if (b) b.click();
  if (window.__tab) return 1;
  var EP = {}; window.__tab = EP;

  EP.startFrames = function(){
    EP._on = true; EP._gaps = []; EP._last = performance.now();
    (function t(){ if(!EP._on) return; var n=performance.now(); EP._gaps.push(n-EP._last); EP._last=n; requestAnimationFrame(t); })();
  };
  EP.stopFrames = function(){
    EP._on = false;
    var g = (EP._gaps||[]).filter(function(x){return isFinite(x) && x>0;}).sort(function(a,b){return a-b;});
    var n = g.length;
    function q(p){ return n ? +g[Math.min(n-1, Math.floor(n*p))].toFixed(1) : null; }
    return { n: n, p50: q(0.5), p95: q(0.95), max: n ? +g[n-1].toFixed(1) : null,
             over50: g.filter(function(x){return x>50;}).length,
             over100: g.filter(function(x){return x>100;}).length,
             over200: g.filter(function(x){return x>200;}).length };
  };
  EP.startLong = function(){
    EP._lt = { n:0, max:0, over50:0, over100:0, over200:0, sum:0 };
    try { EP._ltObs && EP._ltObs.disconnect(); } catch(e) {}
    try { EP._ltObs = new PerformanceObserver(function(list){ list.getEntries().forEach(function(e){
      EP._lt.n++; EP._lt.sum += e.duration; if(e.duration>EP._lt.max)EP._lt.max=e.duration;
      if(e.duration>50)EP._lt.over50++; if(e.duration>100)EP._lt.over100++; if(e.duration>200)EP._lt.over200++;
    }); }); EP._ltObs.observe({entryTypes:['longtask']}); } catch(e) {}
  };
  EP.stopLong = function(){ try { EP._ltObs && EP._ltObs.disconnect(); } catch(e) {}
    var o = EP._lt || null; if (o) { o.max=+o.max.toFixed(1); o.sum=+o.sum.toFixed(1); } return o; };

  EP.installJobProf = function(){
    var S = window.MemoriaScheduler;
    if (!S || typeof S.schedule !== 'function') return { ok:false };
    if (S.__tabPatched) return { ok:true, reused:true };
    var orig = S.schedule;
    EP._jobs = {};
    S.schedule = function(spec){
      try {
        if (spec && typeof spec.run === 'function' && !spec.run.__tabWrapped) {
          var r = spec.run, kind = spec.kind || '?';
          var w = function(ctx){
            var t = performance.now();
            try { return r.call(this, ctx); }
            finally {
              var d = performance.now() - t;
              var j = EP._jobs[kind] || (EP._jobs[kind] = { n:0, max:0, sum:0 });
              j.n++; j.sum += d; if (d > j.max) j.max = d;
            }
          };
          w.__tabWrapped = true;
          spec.run = w;
        }
      } catch(e) {}
      return orig.call(S, spec);
    };
    S.__tabPatched = true;
    return { ok:true };
  };
  EP.resetJobs = function(){ EP._jobs = {}; };
  EP.readJobs = function(){
    var o = {};
    for (var k in EP._jobs) { var j = EP._jobs[k]; o[k] = { n:j.n, max:+j.max.toFixed(2), sum:+j.sum.toFixed(1) }; }
    return o;
  };

  EP.snap = function(){
    var pv = document.getElementById('preview');
    var pane = document.getElementById('preview-pane');
    var ws = window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null;
    var tl = window.__MEMORIA_TAIL_LAYOUT ? window.__MEMORIA_TAIL_LAYOUT.stats() : null;
    return {
      ws: ws, tail: tl,
      domPreview: pv ? pv.getElementsByTagName('*').length : null,
      domBody: document.body.getElementsByTagName('*').length,
      mjx: pv ? pv.querySelectorAll('mjx-container').length : null,
      scrollTop: pane ? Math.round(pane.scrollTop) : null,
      scrollHeight: pane ? pane.scrollHeight : null,
      clientHeight: pane ? pane.clientHeight : null,
      viewMode: (window.state||{}).viewMode || null,
    };
  };

  EP.counters = function(){ try { return window.MemoriaScheduler ? MemoriaScheduler.counters() : null; } catch(e){ return {err:String(e)}; } };
  EP.resetCounters = function(){ try { MemoriaScheduler.resetCounters(); return 1; } catch(e){ return 0; } };
  EP.setMode = function(m){ try { return window.__MEMORIA_TAIL_LAYOUT ? window.__MEMORIA_TAIL_LAYOUT.setMode(m) : null; } catch(e){ return 'ERR:'+e.message; } };

  EP.fastDrag = function(frames){
    return new Promise(function(res){
      var p = document.getElementById('preview-pane');
      var max = Math.max(0, p.scrollHeight - p.clientHeight);
      var i = 0, t0 = performance.now();
      (function step(){
        i++;
        p.scrollTop = Math.round(max * (i / frames));
        if (i < frames) requestAnimationFrame(step);
        else res({ frames:i, ms: +(performance.now()-t0).toFixed(1), maxScroll:max });
      })();
    });
  };

  EP.quiet = async function(maxMs){
    maxMs = maxMs || 45000;
    var t0 = performance.now(), lastKey = null, stable = 0, last = null;
    while (performance.now() - t0 < maxMs) {
      await new Promise(function(r){ setTimeout(r, 350); });
      var s = window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null;
      if (!s) continue;
      last = s;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === lastKey) stable++; else { stable = 0; lastKey = key; }
      if (stable >= 4) return { quietMs:+(performance.now()-t0).toFixed(1), stats:s };
    }
    return { quietMs:+(performance.now()-t0).toFixed(1), stats:last, timeout:true };
  };

  EP.toTop = async function(){
    var p = document.getElementById('preview-pane');
    p.scrollTop = 0;
    return await EP.quiet(30000);
  };

  // 每轮前的负载/可见性门（窗口被遮挡时 rAF 会掉到 1Hz；整机负载高时 p50 升高）
  EP.idleRaf = function(n){
    n = n || 36;
    return new Promise(function(res){
      var g=[], last=performance.now(), k=0, to=setTimeout(function(){ res({timeout:true,n:k}); }, 4000);
      (function t(){
        var now=performance.now(); g.push(now-last); last=now;
        if (++k >= n) {
          clearTimeout(to); g.sort(function(a,b){return a-b;});
          res({ n:g.length, p50:+g[Math.floor(g.length*0.5)].toFixed(1), p95:+g[Math.floor(g.length*0.95)].toFixed(1), max:+g[g.length-1].toFixed(1) });
        } else requestAnimationFrame(t);
      })();
    });
  };

  EP.enableEvictProfile = function(){ try { return window.__MEMORIA_EVICT_PROFILE ? window.__MEMORIA_EVICT_PROFILE.enable() : false; } catch(e){ return false; } };
  EP.resetEvictProfile = function(){ try { return window.__MEMORIA_EVICT_PROFILE ? window.__MEMORIA_EVICT_PROFILE.reset() : false; } catch(e){ return false; } };
  EP.readEvictProfile = function(){ try { return window.__MEMORIA_EVICT_PROFILE ? window.__MEMORIA_EVICT_PROFILE.read() : null; } catch(e){ return null; } };
  return 1;
})()`);
await cdp.ev('window.__tab.installJobProf()', false);
await cdp.ev('window.__tab.enableEvictProfile()', false);

/* ── 测量可信门 ── */
const vis = await cdp.ev('({visibility:document.visibilityState, hasFocus:document.hasFocus(), w:innerWidth, h:innerHeight})', false);
const idle = await cdp.ev(`(function(){
  return new Promise(function(res){
    var g=[], last=performance.now(), n=0, to=setTimeout(function(){ res({timeout:true, n:n}); }, 6000);
    (function t(){
      var now=performance.now(); g.push(now-last); last=now;
      if (++n >= 145) {
        clearTimeout(to);
        g.sort(function(a,b){return a-b;});
        res({ n:g.length, p50:+g[Math.floor(g.length*0.5)].toFixed(1), p95:+g[Math.floor(g.length*0.95)].toFixed(1), max:+g[g.length-1].toFixed(1) });
      } else requestAnimationFrame(t);
    })();
  });
})()`);
console.log('[idle-raf]', JSON.stringify(idle), 'visibility=' + vis.visibility);
if (idle.timeout || !(idle.p50 <= 20)) {
  console.error('MEASUREMENT INVALID: 空转 rAF p50=' + idle.p50 + 'ms —— 窗口被最小化/遮挡？');
  process.exit(4);
}

/* ── 打开文档（重试竞态） ── */
async function openDoc() {
  await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile('homework/README.md', {skipNav:true}); } catch(e){} return 1; })()`);
  await sleep(1500);
  const r = await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); return 'ok'; } catch(e){ return 'ERR:'+e.message; } })()`);
  if (r !== 'ok') { console.error('openFile:', r); process.exit(3); }
  for (let attempt = 0; attempt < 4; attempt++) {
    for (let i = 0; i < 20; i++) {
      const vm = await cdp.ev('(window.state||{}).viewMode', false);
      if (vm === 'preview') break;
      await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`, false);
      await sleep(400);
    }
    for (let i = 0; i < 120; i++) {
      const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
      if (s && s.totalBlocks > 3900) break;
      await sleep(250);
    }
    const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
    if (s && s.totalBlocks > 3900) break;
    console.log('[open] retry ' + (attempt + 1) + '（totalBlocks=' + (s && s.totalBlocks) + '）');
    await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); } catch(e){} return 1; })()`);
    await sleep(2500);
  }
  const q = await cdp.ev('window.__tab.quiet(60000)');
  return q;
}
console.log('[open]', JSON.stringify(await openDoc()));
{
  const st = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
  if (!st || !(st.totalBlocks >= 3900)) {
    console.error('OPEN FAILED: totalBlocks=' + (st && st.totalBlocks) + ' —— 测量作废。'); process.exit(5);
  }
}

async function heap() {
  await cdp.send('HeapProfiler.collectGarbage').catch(() => {});
  await sleep(250);
  await cdp.send('HeapProfiler.collectGarbage').catch(() => {});
  await sleep(150);
  const h = await cdp.send('Runtime.getHeapUsage');
  const d = await cdp.send('Memory.getDOMCounters');
  return { usedMB: +(h.usedSize / 1048576).toFixed(2), embedderMB: +(h.embedderHeapUsedSize / 1048576).toFixed(2),
    domNodes: d.nodes, listeners: d.jsEventListeners };
}

async function perfMetrics() {
  try {
    const r = await cdp.send('Performance.getMetrics');
    const m = {};
    (r.metrics || []).forEach((x) => { m[x.name] = x.value; });
    return m;
  } catch { return null; }
}
function perfDelta(a, b, key) {
  if (!a || !b || typeof a[key] !== 'number' || typeof b[key] !== 'number') return null;
  return +(b[key] - a[key]).toFixed(2);
}

function concurrency() {
  try {
    const o = execFileSync('powershell', ['-NoProfile', '-Command',
      "'py:' + @(Get-Process -Name python -EA SilentlyContinue).Count + ' wv2:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count + ' cpu:' + [math]::Round((Get-Counter '\\Processor(_Total)\\% Processor Time' -MaxSamples 1).CounterSamples[0].CookedValue,1)"],
      { encoding: 'utf8', timeout: 20000 });
    return o.trim();
  } catch { return 'unavailable'; }
}

const R = {
  schema: 'memoria-tail-ab/v1',
  at: new Date().toISOString(),
  head: (() => { try { return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { return null; } })(),
  dirty: (() => { try { return execFileSync('git', ['status', '--porcelain', '--', 'src/memoria/ui/static/app/js'], { encoding: 'utf8' }).trim(); } catch { return null; } })(),
  scriptSha256: createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'),
  argv: process.argv.slice(2),
  gpu, visibility: vis, idleRafBaseline: idle,
  concurrencyBefore: concurrency(),
  window: await cdp.ev('({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,ua:navigator.userAgent})', false),
  order: ORDER.slice(0, ROUNDS),
  rounds: [],
};
R.open = {
  snap: await cdp.ev('window.__tab.snap()'),
  heap: await heap(),
  metrics: await perfMetrics(),
};
console.log('[open] snap', JSON.stringify(R.open.snap.ws), 'heap', R.open.heap.usedMB + 'MB');

async function runRound(letter, idx, warmup) {
  const mode = MODE[letter] || 'legacy';
  const m0 = await cdp.ev(`window.__tab.setMode(${JSON.stringify(mode)})`, false);
  const top0 = await cdp.ev('window.__tab.toTop()');
  const snapTop0 = await cdp.ev('window.__tab.snap()', false);
  const shTopBefore = snapTop0.scrollHeight;
  const driftBefore = snapTop0.ws ? snapTop0.ws.heightDriftPx : null;
  const errBefore = snapTop0.tail ? snapTop0.tail.driftErrPx : null;
  const idleRound = await cdp.ev('window.__tab.idleRaf(36)');
  const roundValid = !idleRound.timeout && idleRound.p50 <= 20;

  await cdp.ev('window.__tab.resetCounters()', false);
  await cdp.ev('window.__tab.resetJobs()', false);
  await cdp.ev('window.__tab.resetEvictProfile()', false);
  const pm0 = await perfMetrics();

  await cdp.ev('window.__tab.startFrames()', false);
  await cdp.ev('window.__tab.startLong()', false);
  const t0 = Date.now();
  const scroll = await cdp.ev(`window.__tab.fastDrag(${FAST_FRAMES})`);
  const q = await cdp.ev(`window.__tab.quiet(${QUIET_MS})`);
  const wallMs = Date.now() - t0;
  const frames = await cdp.ev('window.__tab.stopFrames()', false);
  const long = await cdp.ev('window.__tab.stopLong()', false);
  if (mode === 'pred') await cdp.ev('window.__MEMORIA_TAIL_LAYOUT && window.__MEMORIA_TAIL_LAYOUT.flushVerify ? window.__MEMORIA_TAIL_LAYOUT.flushVerify() : 0', false);
  const counters = await cdp.ev('window.__tab.counters()', false);
  const jobs = await cdp.ev('window.__tab.readJobs()', false);
  const evp = await cdp.ev('window.__tab.readEvictProfile()', false);
  const pm1 = await perfMetrics();
  const snapBottom = await cdp.ev('window.__tab.snap()');

  // 回顶并 quiet：独立测"整篇高度是否跨轮稳定"（不依赖 app 自己的 drift 指标）
  const top1 = await cdp.ev('window.__tab.toTop()');
  const shTopAfter = (await cdp.ev('window.__tab.snap()', false)).scrollHeight;
  const heapAfter = await heap();

  const row = {
    round: idx + 1, letter, mode, warmup: !!warmup, setMode: m0, roundValid, idleRound,
    heap: heapAfter,
    topQuiet: top0 && top0.stats ? top0.stats.materialized : null,
    shTopBefore, shTopAfter, shTopDelta: (shTopBefore != null && shTopAfter != null) ? shTopAfter - shTopBefore : null,
    scroll, quiet: q, wallMs, frames, longtask: long, counters, jobs, evictProfile: evp,
    driftBefore, driftAfter: snapBottom.ws ? snapBottom.ws.heightDriftPx : null,
    driftDelta: (driftBefore != null && snapBottom.ws) ? +(snapBottom.ws.heightDriftPx - driftBefore).toFixed(1) : null,
    driftErrDelta: (errBefore != null && snapBottom.tail) ? +(snapBottom.tail.driftErrPx - errBefore).toFixed(1) : null,
    layout: {
      LayoutCount: perfDelta(pm0, pm1, 'LayoutCount'),
      LayoutDuration: perfDelta(pm0, pm1, 'LayoutDuration'),
      RecalcStyleCount: perfDelta(pm0, pm1, 'RecalcStyleCount'),
      RecalcStyleDuration: perfDelta(pm0, pm1, 'RecalcStyleDuration'),
      ScriptDuration: perfDelta(pm0, pm1, 'ScriptDuration'),
      TaskDuration: perfDelta(pm0, pm1, 'TaskDuration'),
    },
    snap: snapBottom, snapTopAfter: shTopAfter,
  };
  if (!warmup) console.log(`[${letter}#${idx + 1} ${mode}]${roundValid ? '' : ' INVALID'} idle=${idleRound.p50}`
    + ` max_frame=${counters && counters.max_frame_ms}`
    + ` frames p50/p95/max=${frames.p50}/${frames.p95}/${frames.max} over100=${frames.over100} over200=${frames.over200}`
    + ` long.max=${long && long.max} wall=${wallMs}ms shTop=${shTopAfter}`
    + ` layout=${row.layout.LayoutCount}/${row.layout.LayoutDuration}ms`
    + ` evictJobMax=${jobs.lazy_evict ? jobs.lazy_evict.max : '-'}`
    + (evp ? ` tail(anchor=${evp.anchorMs.toFixed(0)} sh=${evp.tailShMs.toFixed(0)} skip=${evp.tailSkips})` : '')
    + ` drift=${snapBottom.ws && snapBottom.ws.heightDriftPx}`);
  return row;
}

for (let i = 0; i < WARMUP; i++) {
  R.rounds.push(await runRound('L', -(i + 1), true));
}
for (let i = 0; i < ROUNDS; i++) {
  R.rounds.push(await runRound(ORDER[i], i, false));
}
R.heapEnd = await heap();

const counted = R.rounds.filter((r) => !r.warmup);
const byMode = {};
for (const m of ['legacy', 'pred', 'noSh']) {
  const all = counted.filter((r) => r.mode === m);
  const rs = all.filter((r) => r.roundValid !== false);
  if (!rs.length) continue;
  const vals = (f) => rs.map(f).filter((x) => typeof x === 'number' && isFinite(x));
  const med = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); return +s[Math.floor(s.length / 2)].toFixed(2); };
  const p95 = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.floor(s.length * 0.95))].toFixed(2); };
  const mf = vals((r) => r.counters && r.counters.max_frame_ms);
  const fp95 = vals((r) => r.frames && r.frames.p95);
  const fmax = vals((r) => r.frames && r.frames.max);
  const lmax = vals((r) => r.longtask && r.longtask.max);
  const wall = vals((r) => r.wallMs);
  byMode[m] = {
    n: rs.length,
    nInvalid: all.length - rs.length,
    idleP50: rs.map((r) => r.idleRound && r.idleRound.p50),
    max_frame_ms: mf,
    max_frame_ms_median: med(mf), max_frame_ms_p95: p95(mf),
    frames_p95: fp95, frames_p95_median: med(fp95), frames_p95_p95: p95(fp95),
    frames_max: fmax, frames_max_max: fmax.length ? Math.max(...fmax) : null,
    longtask_max: lmax, longtask_max_median: med(lmax),
    over200_rounds: mf.filter((x) => x > 200).length,
    wall_median: med(wall),
    heightDriftPx: rs.map((r) => r.snap.ws && r.snap.ws.heightDriftPx),
    driftDelta: rs.map((r) => r.driftDelta),
    driftDelta_median: med(vals((r) => r.driftDelta)),
    tailVerify: rs.map((r) => r.snap.tail && r.snap.tail.verifies),
    tailDriftErrPx: rs.map((r) => r.snap.tail && r.snap.tail.driftErrPx),
    driftErrDelta: rs.map((r) => r.driftErrDelta),
    shTop: rs.map((r) => r.shTopAfter),
    shTopDelta: rs.map((r) => r.shTopDelta),
    layoutCount: vals((r) => r.layout.LayoutCount),
    layoutDuration: vals((r) => r.layout.LayoutDuration),
    evictJobMax: vals((r) => r.jobs.lazy_evict && r.jobs.lazy_evict.max),
    evictSum: vals((r) => r.jobs.lazy_evict && r.jobs.lazy_evict.sum),
    tail: rs.map((r) => r.evictProfile ? {
      batches: r.evictProfile.batches, blocks: r.evictProfile.blocks,
      totalMs: +r.evictProfile.totalMs.toFixed(1), anchorMs: +r.evictProfile.anchorMs.toFixed(1),
      keepMs: +r.evictProfile.keepMs.toFixed(1), scanMs: +r.evictProfile.scanMs.toFixed(1),
      applyMs: +r.evictProfile.applyMs.toFixed(1), mathClearMs: +r.evictProfile.mathClearMs.toFixed(1),
      tailShMs: +(r.evictProfile.tailShMs || 0).toFixed(1),
      tailAnchorReadMs: +(r.evictProfile.tailAnchorReadMs || 0).toFixed(1),
      tailWriteMs: +(r.evictProfile.tailWriteMs || 0).toFixed(1),
      tailSkips: r.evictProfile.tailSkips || 0, tailVerifies: r.evictProfile.tailVerifies || 0,
    } : null),
    heapMB: rs.map((r) => r.heap && r.heap.usedMB),
  };
}
R.summary = {
  byMode,
  paired: counted.map((r) => ({ mode: r.mode, max_frame_ms: r.counters && r.counters.max_frame_ms,
    frames_p95: r.frames && r.frames.p95, wallMs: r.wallMs, shTopAfter: r.shTopAfter,
    drift: r.snap.ws && r.snap.ws.heightDriftPx, layoutDuration: r.layout.LayoutDuration })),
  heapOpenMB: R.open.heap.usedMB, heapEndMB: R.heapEnd.usedMB,
  domOpen: R.open.heap.domNodes, domEnd: R.heapEnd.domNodes,
};
writeFileSync(outPath, JSON.stringify(R, null, 2), 'utf8');
console.log('[concurrency]', R.concurrencyBefore, '->', concurrency());
console.log('\n[SUMMARY]', JSON.stringify(R.summary.byMode, null, 1));
console.log('[out]', outPath);
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
