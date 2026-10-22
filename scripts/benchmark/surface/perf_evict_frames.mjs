/**
 * task-76 / W3：`lazy_evict` 单批长帧 —— **真机 9 轮**帧度量 + 逐 job 归因 + 淘汰单批耗时分解。
 *
 * 口径（与 `docs/design/maintenance-jobs.md` §3.5 的真机表一致）：
 *   · 真机 pywebview + WebView2，`MEMORIA_MODE=dev`、`MEMORIA_DEBUG=0`（关 DevTools，避免
 *     `blink::InspectorDOMAgent` 额外保留 detached DOM）、`MEMORIA_FRAMELESS=0`；
 *   · 文档 `教材/08_第8章_差错控制编码.md`（4001 块），`window.__MEMORIA_LAZY = true`；
 *   · `max_frame_ms` / `slice_count` / `budget_exceeded` 全部来自 `MemoriaScheduler.counters()`，
 *     每轮 `resetCounters()` 后单轮读取（**不在每帧回调里读**，避免观察者效应）；
 *   · 帧间隔由页面内 rAF 采样（只 push 数字），逐 job 同步耗时对 `schedule().run` 的同步前缀计时
 *     —— 均**不改变调度语义**；
 *   · 淘汰单批分段（keep/scan/read/apply/blockIndex/mathClear/anchor）来自 app.js 内建的
 *     `window.__MEMORIA_EVICT_PROFILE`（默认关闭，本脚本显式 enable）。
 *
 * 用法：
 *   node scripts/benchmark/surface/perf_evict_frames.mjs <port> <out.json> [--doc <path>]
 *        [--fast 5] [--slow 4] [--fast-frames 80] [--slow-steps 30] [--slow-interval 100]
 *        [--timeout-ms 300000] [--no-profile]
 *
 * 产物：JSON（含 head sha / 脚本 sha256 / argv / port / 窗口尺寸 / 每轮原始读数），
 *       文件名由调用方带 sha。
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
if (!port || !outPath) {
  console.error('usage: node perf_evict_frames.mjs <port> <out.json> [opts]');
  process.exit(2);
}
const DOC = arg('doc', '教材/08_第8章_差错控制编码.md');
const FAST = Number(arg('fast', 5));
const SLOW = Number(arg('slow', 4));
const FAST_FRAMES = Number(arg('fast-frames', 80));
const SLOW_STEPS = Number(arg('slow-steps', 30));
const SLOW_INTERVAL = Number(arg('slow-interval', 100));
const PROFILE = !arg('no-profile', false);

/* ────────────────────────── CDP ────────────────────────── */
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
  /** 求值；异常一律抛出（测量脚本不能吞错）。 */
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
      try { if (await this.ev(`!!(${expr})`, false)) return true; } catch { /* 页面可能在重载 */ }
      await sleep(stepMs);
    }
    return false;
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

/* ────────────────────────── 连页面 ────────────────────────── */
let page = null;
for (let a = 0; a < 60; a++) {
  try {
    const l = await httpJson(`http://127.0.0.1:${port}/json/list`);
    page = (l || []).find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+\//.test(t.url || '') &&
      !/devtools/.test(t.url || '') && t.webSocketDebuggerUrl);
    if (page) break;
  } catch { /* 应用还没起 */ }
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
// 真机凭证：GPU 必须是硬件（软光栅读数不可作真机口径）
const gpu = await cdp.ev(`(function(){try{var c=document.createElement('canvas');var gl=c.getContext('webgl')||c.getContext('experimental-webgl');if(!gl)return {webgl:false};var e=gl.getExtension('WEBGL_debug_renderer_info');return {webgl:true,renderer:e?gl.getParameter(e.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)};}catch(err){return {webgl:false,err:String(err)}}})()`, false);
if (!gpu || !gpu.webgl) { console.error('webgl unavailable — 不是真机口径:', JSON.stringify(gpu)); process.exit(2); }
console.log('[gpu]', gpu.renderer);

/* ────────────────────────── 页面内探针 ────────────────────────── */
await cdp.ev(`(function(){
  window.__MEMORIA_LAZY = true;
  try { localStorage.setItem('memoria.perf.lazy','1'); } catch(e) {}
  var b = document.querySelector('.-view-btn[data-view="preview"]'); if (b) b.click();
  if (window.__ep) return 1;
  var EP = {}; window.__ep = EP;

  // ── 帧间隔采样（只在 rAF 里 push 数字） ──
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

  // ── 长任务（若可用） ──
  EP.startLong = function(){
    EP._lt = { n:0, max:0, over50:0 };
    try { EP._ltObs && EP._ltObs.disconnect(); } catch(e) {}
    try { EP._ltObs = new PerformanceObserver(function(list){ list.getEntries().forEach(function(e){ EP._lt.n++; if(e.duration>EP._lt.max)EP._lt.max=e.duration; if(e.duration>50)EP._lt.over50++; }); }); EP._ltObs.observe({entryTypes:['longtask']}); } catch(e) {}
  };
  EP.stopLong = function(){ try { EP._ltObs && EP._ltObs.disconnect(); } catch(e) {} return EP._lt || null; };

  // ── 逐 job 同步前缀计时（包 schedule().run；不改变调度语义） ──
  EP.installJobProf = function(){
    var S = window.MemoriaScheduler;
    if (!S || typeof S.schedule !== 'function') return { ok:false };
    if (S.__epPatched) return { ok:true, reused:true };
    var orig = S.schedule;
    EP._jobs = {};
    S.schedule = function(spec){
      try {
        if (spec && typeof spec.run === 'function' && !spec.run.__epWrapped) {
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
          w.__epWrapped = true;
          spec.run = w;
        }
      } catch(e) {}
      return orig.call(S, spec);
    };
    S.__epPatched = true;
    return { ok:true };
  };
  EP.resetJobs = function(){ EP._jobs = {}; };
  EP.readJobs = function(){
    var o = {};
    for (var k in EP._jobs) { var j = EP._jobs[k]; o[k] = { n:j.n, max:+j.max.toFixed(2), sum:+j.sum.toFixed(1) }; }
    return o;
  };

  // ── 轻量读出（不在滚动帧里调用） ──
  EP.snap = function(){
    var pv = document.getElementById('preview');
    var pane = document.getElementById('preview-pane');
    var ws = window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null;
    var mj = 0, mjDis = 0;
    try { var d = window.MathJax && MathJax.startup && MathJax.startup.document; if (d && d.math) { for (var it of d.math) { mj++; if (it.typesetRoot && !it.typesetRoot.isConnected) mjDis++; } } } catch(e) {}
    return {
      ws: ws,
      domPreview: pv ? pv.getElementsByTagName('*').length : null,
      domBody: document.body.getElementsByTagName('*').length,
      mjx: pv ? pv.querySelectorAll('mjx-container').length : null,
      mathItems: mj, mathDetached: mjDis,
      scrollTop: pane ? Math.round(pane.scrollTop) : null,
      scrollHeight: pane ? pane.scrollHeight : null,
      clientHeight: pane ? pane.clientHeight : null,
      viewMode: (window.state||{}).viewMode || null,
    };
  };

  EP.counters = function(){ try { return window.MemoriaScheduler ? MemoriaScheduler.counters() : null; } catch(e){ return {err:String(e)}; } };
  EP.resetCounters = function(){ try { MemoriaScheduler.resetCounters(); return 1; } catch(e){ return 0; } };

  // ── 快速拖到底：连续 N 个 rAF 帧把 scrollTop 从 0 推到 max（真实拖动语义） ──
  EP.fastDrag = function(frames){
    return new Promise(function(res){
      var p = document.getElementById('preview-pane');
      var max = Math.max(0, p.scrollHeight - p.clientHeight);
      var i = 0, t0 = performance.now();
      function step(){
        i++;
        p.scrollTop = Math.round(max * (i / frames));
        if (i < frames) requestAnimationFrame(step);
        else res({ frames:i, ms: +(performance.now()-t0).toFixed(1), maxScroll:max });
      }
      requestAnimationFrame(step);
    });
  };

  // ── 慢滚：30 步 × 100ms ──
  EP.slowScroll = function(steps, intervalMs){
    return (async function(){
      var p = document.getElementById('preview-pane');
      var max = Math.max(0, p.scrollHeight - p.clientHeight);
      var t0 = performance.now();
      for (var k = 1; k <= steps; k++) {
        p.scrollTop = Math.round(max * (k/steps));
        await new Promise(function(r){ setTimeout(r, intervalMs); });
      }
      return { steps:steps, ms:+(performance.now()-t0).toFixed(1), maxScroll:max };
    })();
  };

  // ── 等 workset 稳定（只读 __MEMORIA_WORKSET_STATS） ──
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

  EP.enableEvictProfile = function(){ try { return window.__MEMORIA_EVICT_PROFILE ? window.__MEMORIA_EVICT_PROFILE.enable() : false; } catch(e){ return false; } };
  EP.resetEvictProfile = function(){ try { return window.__MEMORIA_EVICT_PROFILE ? window.__MEMORIA_EVICT_PROFILE.reset() : false; } catch(e){ return false; } };
  EP.readEvictProfile = function(){ try { return window.__MEMORIA_EVICT_PROFILE ? window.__MEMORIA_EVICT_PROFILE.read() : null; } catch(e){ return null; } };
  return 1;
})()`);

const jobProf = await cdp.ev('window.__ep.installJobProf()', false);
console.log('[jobProf]', JSON.stringify(jobProf));
if (PROFILE) await cdp.ev('window.__ep.enableEvictProfile()', false);

/* ── 测量可信门：窗口必须可见（最小化/遮挡时 Chromium 把 rAF 节流到 1Hz ⇒ 读数作废） ── */
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
  console.error('MEASUREMENT INVALID: 空转 rAF 基线不合格（p50=' + idle.p50 + 'ms）——窗口可能被最小化/遮挡，' +
    'Chromium 把 rAF 节流到 1Hz。请让应用窗口可见后重跑。');
  process.exit(4);
}

/* ────────────────────────── 打开文档 ────────────────────────── */
async function openDoc() {
  // 先用小文件把启动期「自动打开 + 恢复视图」的竞态顶掉（见 realapp-measurement-protocol §2.5）
  await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile('homework/README.md', {skipNav:true}); } catch(e){} return 1; })()`);
  await sleep(1500);
  const r = await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); return 'ok'; } catch(e){ return 'ERR:'+e.message; } })()`);
  if (r !== 'ok') { console.error('openFile:', r); process.exit(3); }
  // 启动期 openFile 有竞态（§2.5 坑③）：打开失败/被自动打开顶掉时重试，不能静默继续
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
  const q = await cdp.ev('window.__ep.quiet(60000)');
  return q;
}

/* 打开失败必须 loud-fail：否则会在空文档上量出 0.2ms 这种"完美"假读数 */
{
  const st = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
  if (!st || !(st.totalBlocks >= 3900)) {
    console.error('OPEN FAILED: totalBlocks=' + (st && st.totalBlocks) + ' materialized=' + (st && st.materialized) +
      ' —— 08 章没打开（启动期 openFile 竞态或页面异常）。测量作废。');
    process.exit(5);
  }
}

async function heap() {
  await cdp.send('HeapProfiler.collectGarbage').catch(() => {});
  await sleep(250);
  await cdp.send('HeapProfiler.collectGarbage').catch(() => {});
  await sleep(150);
  const h = await cdp.send('Runtime.getHeapUsage');
  const d = await cdp.send('Memory.getDOMCounters');
  return {
    usedMB: +(h.usedSize / 1048576).toFixed(2),
    embedderMB: +(h.embedderHeapUsedSize / 1048576).toFixed(2),
    domNodes: d.nodes, listeners: d.jsEventListeners,
  };
}

/* 并发环境（同机可能有其它 agent 跑着 Memoria/WebView2 实例 ⇒ 读数不是独占机器的读数） */
function concurrency() {
  try {
    const o = execFileSync('powershell', ['-NoProfile', '-Command',
      "'py:' + @(Get-Process -Name python -EA SilentlyContinue).Count + ' wv2:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count + ' node:' + @(Get-Process -Name node -EA SilentlyContinue).Count + ' cpu:' + [math]::Round((Get-Counter '\\Processor(_Total)\\% Processor Time' -MaxSamples 1).CounterSamples[0].CookedValue,1)"],
      { encoding: 'utf8', timeout: 20000 });
    return o.trim();
  } catch (e) { return 'unavailable'; }
}

const R = {
  schema: 'memoria-evict-frames/v1',
  at: new Date().toISOString(),
  concurrencyBefore: concurrency(),
  head: (() => { try { return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { return null; } })(),
  dirty: (() => { try { return execFileSync('git', ['status', '--porcelain', '--', 'src/memoria/ui/static/app/js'], { encoding: 'utf8' }).trim(); } catch { return null; } })(),
  scriptSha256: createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'),
  argv: process.argv.slice(2),
  env: { mode: 'realapp-webview2', port, doc: DOC, profile: PROFILE, fastFrames: FAST_FRAMES, slowSteps: SLOW_STEPS, slowInterval: SLOW_INTERVAL },
  gpu,
  visibility: vis,
  idleRafBaseline: idle,
  window: await cdp.ev('({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,ua:navigator.userAgent})', false),
  appVersion: await cdp.ev('(window.MemoriaApp && (MemoriaApp.version || (document.title||"").trim())) || null', false),
  rounds: [],
};

console.log('[open]', JSON.stringify(await openDoc()));
R.open = { snap: await cdp.ev('window.__ep.snap()'), heap: await heap() };
console.log('[open] snap', JSON.stringify(R.open.snap.ws), 'heap', R.open.heap.usedMB + 'MB');

/* ────────────────────────── 9 轮 ────────────────────────── */
async function runRound(kind, idx) {
  const top = await cdp.ev('window.__ep.toTop()');
  await cdp.ev('window.__ep.resetCounters()', false);
  await cdp.ev('window.__ep.resetJobs()', false);
  if (PROFILE) await cdp.ev('window.__ep.resetEvictProfile()', false);
  await cdp.ev('window.__ep.startFrames()', false);
  await cdp.ev('window.__ep.startLong()', false);

  const scroll = kind === 'fast'
    ? await cdp.ev(`window.__ep.fastDrag(${FAST_FRAMES})`)
    : await cdp.ev(`window.__ep.slowScroll(${SLOW_STEPS}, ${SLOW_INTERVAL})`);

  const q = await cdp.ev('window.__ep.quiet(60000)');
  const frames = await cdp.ev('window.__ep.stopFrames()', false);
  const long = await cdp.ev('window.__ep.stopLong()', false);
  const counters = await cdp.ev('window.__ep.counters()', false);
  const jobs = await cdp.ev('window.__ep.readJobs()', false);
  const evp = PROFILE ? await cdp.ev('window.__ep.readEvictProfile()', false) : null;
  const snap = await cdp.ev('window.__ep.snap()');
  const hp = await heap();

  const row = {
    round: idx + 1, kind, topQuiet: top && top.stats ? top.stats.materialized : null,
    scroll, quiet: q, frames, longtask: long, counters, jobs, evictProfile: evp, snap, heap: hp,
  };
  console.log(`[${kind}#${idx + 1}] max_frame_ms=${counters && counters.max_frame_ms} slice=${counters && counters.slice_count}`
    + ` budget_exceeded=${counters && counters.budget_exceeded}/${counters && counters.frames_used}`
    + ` | workset mat=${snap.ws && snap.ws.materialized} ph=${snap.ws && snap.ws.placeholders} evictTotal=${snap.ws && snap.ws.evictTotal}`
    + ` | dom=${snap.domPreview} mjx=${snap.mjx} heap=${hp.usedMB}MB`
    + ` | evictJob=${jobs.lazy_evict ? jobs.lazy_evict.max : '-'}ms`
    + (evp ? ` | evp: batchMax=${evp.maxTotalMs.toFixed(1)} applyMax=${evp.maxApplyMs.toFixed(1)} mathMax=${evp.maxMathClearMs.toFixed(1)}` : ''));
  return row;
}

for (let i = 0; i < FAST; i++) R.rounds.push(await runRound('fast', i));
for (let i = 0; i < SLOW; i++) R.rounds.push(await runRound('slow', i));

/* ────────────────────────── 汇总 ────────────────────────── */
const nums = (f) => R.rounds.map(f).filter((x) => typeof x === 'number' && isFinite(x));
const maxes = nums((r) => r.counters && r.counters.max_frame_ms);
R.summary = {
  rounds: R.rounds.length,
  max_frame_ms: maxes.map((x) => +x.toFixed(1)),
  max_frame_ms_max: maxes.length ? +Math.max(...maxes).toFixed(1) : null,
  over200: maxes.filter((x) => x > 200).length,
  slice_count: nums((r) => r.counters && r.counters.slice_count),
  budget_exceeded: nums((r) => r.counters && r.counters.budget_exceeded),
  evict_job_max: nums((r) => r.jobs && r.jobs.lazy_evict && r.jobs.lazy_evict.max),
  materialize_job_max: nums((r) => r.jobs && r.jobs.lazy_materialize && r.jobs.lazy_materialize.max),
  typeset_job_max: nums((r) => r.jobs && r.jobs.lazy_typeset && r.jobs.lazy_typeset.max),
  evictTotal: R.rounds.map((r) => r.snap.ws && r.snap.ws.evictTotal),
  evict_blocks_per_round: (() => {
    let prev = R.open.snap.ws ? R.open.snap.ws.evictTotal : 0;
    return R.rounds.map((r) => { const v = r.snap.ws ? r.snap.ws.evictTotal : prev; const d = v - prev; prev = v; return d; });
  })(),
  heapMB: R.rounds.map((r) => r.heap.usedMB),
  domPreview: R.rounds.map((r) => r.snap.domPreview),
  materialized: R.rounds.map((r) => r.snap.ws && r.snap.ws.materialized),
  heightDriftPx: R.rounds.map((r) => r.snap.ws && r.snap.ws.heightDriftPx),
};

writeFileSync(outPath, JSON.stringify(R, null, 2), 'utf8');
console.log('[concurrency]', R.concurrencyBefore, '->', concurrency());
console.log('\n[SUMMARY]', JSON.stringify(R.summary));
console.log('[out]', outPath);
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
