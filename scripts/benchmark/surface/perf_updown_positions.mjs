/**
 * W3.2 —— 第二遍（向上）滚动逐位置帧成本 vs 第一遍（向下）。
 *
 * 口径（真机 pywebview + WebView2；`MEMORIA_MODE=dev`、`MEMORIA_DEBUG=0`、`MEMORIA_FRAMELESS=0`）：
 *   · 文档 `教材/08_第8章_差错控制编码.md`（4001 块），`window.__MEMORIA_LAZY = true`；
 *   · 位置 = 滚动比例的 5%..95%，每 5% 一个（19 个位置，覆盖旧基线的 35%–50% 长尾区）；
 *   · 第一遍：位置升序（向下）；第二遍：位置降序（向上）；
 *   · 每个位置：瞬时设 scrollTop → 固定窗口 `--window-ms`（默认 600ms）内 **rAF 帧间隔**取 max/p95，
 *     同时记 `MemoriaScheduler.counters()` 的逐位置增量（max_frame_ms / frames_used / slice_count）、
 *     工作集统计（materialized / placeholders / evictTotal）、以及 MutationObserver 的
 *     物化 / 淘汰 / mjx 创建 / mermaid 容器替换计数（**只数节点自身的类与 nodeName，不做子树查询**，
 *     避免观察者效应污染帧成本）；
 *   · 位置之间：等 `materialized|placeholders|evictTotal` 连续稳定（最多 `--settle-max-ms`）再进入下一位置；
 *   · 多轮（默认 3）取每位置的中位比值；**只采信同一次运行内的 down/up 对比**（同 build、同实例）。
 *
 * 测量可信门（与 perf_evict_frames.mjs 一致）：
 *   · WebGL 必须可用（硬件 GPU 凭证）；
 *   · 空转 rAF p50 ≤ 20ms（窗口最小化/遮挡会被 Chromium 节流 ⇒ 读数作废）；
 *   · `totalBlocks ≥ 3900` 才继续（08 章打开失败会在空文档上量出假读数）。
 *
 * 用法：
 *   node scripts/benchmark/surface/perf_updown_positions.mjs <port> <out.json>
 *        [--doc <path>] [--rounds 3] [--window-ms 600] [--positions 19]
 *        [--settle-max-ms 900] [--timeout-ms 300000]
 *
 * 产物：JSON（head / 脚本 sha256 / argv / GPU / 可信门读数 / 每轮每位置读数 / 汇总比值）。
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
  console.error('usage: node perf_updown_positions.mjs <port> <out.json> [opts]');
  process.exit(2);
}
const DOC = arg('doc', '教材/08_第8章_差错控制编码.md');
const ROUNDS = Number(arg('rounds', 3));
const WIN_MS = Number(arg('window-ms', 600));
const POSITIONS = Number(arg('positions', 19));
const SETTLE_MAX_MS = Number(arg('settle-max-ms', 900));
const ORDER = String(arg('order', 'downup'));   // downup（默认：第一遍向下、第二遍向上）| updown（对照）
// 同实例 A/B：A 臂 = 200/60（当前默认），B 臂 = 48/24（W3.2 候选）。传 --ab 开启交替。
const AB = !!arg('ab', false);
const AB_A = { idle: Number(arg('ab-a-idle', 200)), scrolling: Number(arg('ab-a-scrolling', 60)), evict: Number(arg('ab-a-evict', 60)) };
const AB_B = { idle: Number(arg('ab-b-idle', 48)), scrolling: Number(arg('ab-b-scrolling', 24)), evict: Number(arg('ab-b-evict', 60)) };
const AB_MMD = !!arg('ab-mmd', false);   // 仅 A/B mermaid 缓存（A=off, B=on）
const MMD = arg('mmd', '');              // 固定 mermaid 缓存开关：on|off（空=产品默认）
const AB_ORDER = ['A', 'B', 'B', 'A', 'A', 'B', 'B', 'A'];

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
      try { if (await this.ev(`!!(${expr})`, false)) return true; } catch { /* reload */ }
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
    page = (l || []).find((t) => t.type === 'page' &&
      /^http:\/\/127\.0\.0\.1:\d+\//.test(t.url || '') &&
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

/* ────────────────────────── 页面内探针 ────────────────────────── */
await cdp.ev(`(function(){
  window.__MEMORIA_LAZY = true;
  try { localStorage.setItem('memoria.perf.lazy','1'); } catch(e) {}
  var b = document.querySelector('.-view-btn[data-view="preview"]'); if (b) b.click();
  // 复用同一页面重跑时：先停掉旧探针（rAF 采样循环），否则会叠加观察者效应
  try { if (window.__ud && window.__ud._on) window.__ud._on = false; } catch(e) {}
  try { delete window.__ud; } catch(e) {}
  var U = {}; window.__ud = U;

  U._on = false; U._pos = -1; U._last = 0; U._frames = [];
  U._ev = { mat:0, evict:0, mjx:0, mmd:0 };

  U.startFrames = function(){
    if (U._on) return 1;
    U._on = true; U._last = performance.now(); U._frames = [];
    (function tick(){
      if (!U._on) return;
      var now = performance.now();
      U._frames.push(now - U._last);
      U._last = now;
      requestAnimationFrame(tick);
    })();
    return 1;
  };
  U.setPos = function(p){ U._pos = p; };
  U.resetEvents = function(){ U._ev = { mat:0, evict:0, mjx:0, mmd:0 }; };
  U.readEvents = function(){ return U._ev; };

  // 只观察 childList：每个 added/removed 节点只做 nodeName / classList 判断（无子树查询）
  U.observe = function(){
    var cc = document.querySelector('#preview .-preview-content') || document.getElementById('preview');
    if (!cc) return 'no-cc';
    if (U._mo) { try { U._mo.disconnect(); } catch(e){} }
    U._mo = new MutationObserver(function(muts){
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        for (var a = 0; a < m.addedNodes.length; a++) {
          var n = m.addedNodes[a];
          if (!n || n.nodeType !== 1) continue;
          var cn = n.classList;
          if (cn && cn.contains('-src-block') && !cn.contains('-pv-placeholder')) U._ev.mat++;
          if (n.nodeName === 'MJX-CONTAINER') U._ev.mjx++;
          if (cn && cn.contains('-mermaid-container')) U._ev.mmd++;
        }
        for (var r = 0; r < m.removedNodes.length; r++) {
          var x = m.removedNodes[r];
          if (!x || x.nodeType !== 1) continue;
          if (x.classList && x.classList.contains('-pv-placeholder')) U._ev.evict++;
        }
      }
    });
    U._mo.observe(cc, { childList: true, subtree: true });
    return 'observing';
  };

  U.counters = function(){
    try { return window.MemoriaScheduler ? MemoriaScheduler.counters() : null; } catch(e){ return null; }
  };
  U.workset = function(){
    try { return window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null; } catch(e){ return null; }
  };
  U.dom = function(){
    var pv = document.getElementById('preview');
    return {
      nodes: pv ? pv.getElementsByTagName('*').length : null,
      mjx: pv ? pv.querySelectorAll('mjx-container').length : null,
    };
  };

  // MathJax 内部 MathItem 计数（淘汰 purge 修复的回归观测；只读，窗口外调用）
  U.mathStats = function(){
    var items = 0, detached = 0;
    try {
      var d = window.MathJax && MathJax.startup && MathJax.startup.document;
      if (d && d.math) { for (var it of d.math) { items++; if (it.typesetRoot && !it.typesetRoot.isConnected) detached++; } }
    } catch(e) {}
    return { items: items, detached: detached };
  };

  // 真实排版/渲染耗时（在调度 job 之外，经 setTimeout/await 执行 ⇒ 只能包 API 才能归因）
  //   计数挂在 window.__udCost（稳定位置），页内重跑探针时不必重复包 API。
  U._ts = { n:0, ms:0, max:0 };
  U._mmd = { n:0, ms:0, max:0 };
  U._udCost = window.__udCost || (window.__udCost = {
    ts: { n:0, ms:0, max:0 }, mmd: { n:0, ms:0, max:0 },
  });
  U.installCostProbes = function(){
    var C = U._udCost;
    try {
      var MJ = window.MathJax;
      if (MJ && typeof MJ.typesetPromise === 'function' && !MJ.__udWrapped) {
        var origTs = MJ.typesetPromise.bind(MJ);
        MJ.typesetPromise = function(){
          var t = performance.now();
          var pr = origTs.apply(null, arguments);
          try {
            return pr.then(function(v){
              var d = performance.now() - t;
              C.ts.n++; C.ts.ms += d; if (d > C.ts.max) C.ts.max = d;
              return v;
            }, function(e){
              var d = performance.now() - t;
              C.ts.n++; C.ts.ms += d; if (d > C.ts.max) C.ts.max = d;
              throw e;
            });
          } catch (e) { return pr; }
        };
        MJ.__udWrapped = true;
      }
    } catch(e) {}
    try {
      var M = window.mermaid;
      if (M && typeof M.render === 'function' && !M.__udWrapped) {
        var origR = M.render.bind(M);
        M.render = function(){
          var t = performance.now();
          var pr = origR.apply(null, arguments);
          try {
            return Promise.resolve(pr).then(function(v){
              var d = performance.now() - t;
              C.mmd.n++; C.mmd.ms += d; if (d > C.mmd.max) C.mmd.max = d;
              return v;
            }, function(e){
              var d = performance.now() - t;
              C.mmd.n++; C.mmd.ms += d; if (d > C.mmd.max) C.mmd.max = d;
              throw e;
            });
          } catch (e) { return pr; }
        };
        M.__udWrapped = true;
      }
    } catch(e) {}
    return { mathjax: !!(window.MathJax && MathJax.__udWrapped), mermaid: !!(window.mermaid && window.mermaid.__udWrapped) };
  };
  U.resetCost = function(){ U._udCost.ts = { n:0, ms:0, max:0 }; U._udCost.mmd = { n:0, ms:0, max:0 }; };
  U.readCost = function(){
    var C = U._udCost;
    return { typeset: { n:C.ts.n, ms:+C.ts.ms.toFixed(1), max:+C.ts.max.toFixed(1) },
             mermaid: { n:C.mmd.n, ms:+C.mmd.ms.toFixed(1), max:+C.mmd.max.toFixed(1) } };
  };

  // LoAF（long-animation-frame）：把长帧拆成 script / style+layout / render
  //   同页重跑时复用同一个 observer 与数组（window.__udLoaf）
  U._loaf = window.__udLoaf || (window.__udLoaf = []);
  U.installLoaf = function(){
    if (window.__udLoafObs) return 'already';
    try {
      window.__udLoafObs = new PerformanceObserver(function(list){
        var es = list.getEntries();
        for (var i = 0; i < es.length; i++) {
          var e = es[i];
          if (window.__udLoaf.length > 400) window.__udLoaf.shift();
          window.__udLoaf.push({
            start: +e.startTime.toFixed(1),
            dur: +e.duration.toFixed(1),
            renderStart: e.renderStart ? +(e.renderStart - e.startTime).toFixed(1) : null,
            styleLayoutStart: e.styleAndLayoutStart ? +(e.styleAndLayoutStart - e.startTime).toFixed(1) : null,
            blocking: e.blockingDuration ? +e.blockingDuration.toFixed(1) : null,
            scripts: (e.scripts || []).map(function(s){ return { src: (s.sourceURL||'').split('/').pop(), fn: s.sourceFunctionName||'', dur: +s.duration.toFixed(1) }; }),
          });
        }
      });
      window.__udLoafObs.observe({ type: 'long-animation-frame', buffered: true });
      return 'observing';
    } catch (e) { return 'unsupported:' + String(e && e.message || e); }
  };

  // 逐 kind 的 job 同步耗时（包 schedule().run；不改变调度语义）
  U._jobs = {};
  U.installJobProf = function(){
    var S = window.MemoriaScheduler;
    if (!S || typeof S.schedule !== 'function') return { ok:false };
    if (S.__udPatched) return { ok:true, reused:true };
    var orig = S.schedule;
    S.schedule = function(spec){
      try {
        if (spec && typeof spec.run === 'function' && !spec.run.__udWrapped) {
          var r = spec.run, kind = spec.kind || '?';
          var w = function(ctx){
            var t = performance.now();
            try { return r.call(this, ctx); }
            finally {
              var d = performance.now() - t;
              var j = U._jobs[kind] || (U._jobs[kind] = { n:0, max:0, sum:0 });
              j.n++; j.sum += d; if (d > j.max) j.max = d;
            }
          };
          w.__udWrapped = true;
          spec.run = w;
        }
      } catch(e) {}
      return orig.call(S, spec);
    };
    S.__udPatched = true;
    return { ok:true };
  };
  U.resetJobs = function(){ U._jobs = {}; };
  U.readJobs = function(){
    var o = {};
    for (var k in U._jobs) { var j = U._jobs[k]; o[k] = { n:j.n, max:+j.max.toFixed(2), sum:+j.sum.toFixed(1) }; }
    return o;
  };

  function gapStats(g){
    var a = (g || []).filter(function(x){ return isFinite(x) && x > 0; }).sort(function(x,y){ return x-y; });
    var n = a.length;
    function q(p){ return n ? +a[Math.min(n-1, Math.floor(n*p))].toFixed(1) : null; }
    return { n:n, p50:q(0.5), p95:q(0.95), max:n ? +a[n-1].toFixed(1) : null,
             over50: a.filter(function(x){ return x>50; }).length,
             over100: a.filter(function(x){ return x>100; }).length,
             over200: a.filter(function(x){ return x>200; }).length,
             sum: n ? +a.reduce(function(s,x){ return s+x; },0).toFixed(1) : null };
  }

  // 单个位置：瞬时跳转 + 固定窗口采样（窗口内不读 DOM/布局，避免观察者效应）
  U.measureAt = async function(frac, winMs, settleMaxMs){
    var pane = document.getElementById('preview-pane');
    if (!pane) return { err: 'no-pane' };
    var max = Math.max(0, pane.scrollHeight - pane.clientHeight);
    var target = Math.round(max * frac);
    var c0 = U.counters();
    U.resetEvents();
    U.resetJobs();
    U.resetCost();
    U.setPos(frac);
    U._frames = []; U._last = performance.now();
    var t0 = performance.now();
    pane.scrollTop = target;
    var jumpMs = performance.now() - t0;
    await new Promise(function(r){ setTimeout(r, winMs); });
    var gaps = U._frames.slice();
    var c1 = U.counters();
    var ws = U.workset();
    var dom = U.dom();
    var ev = U.readEvents();
    var jobs = U.readJobs();
    var mstat = U.mathStats();
    var cost = U.readCost();
    var loaf = U._loaf.filter(function(e){ return e.start >= t0; });
    // 位置之间等稳定（最多 settleMaxMs）：连续 2 次三计数不变
    var t1 = performance.now(), stable = 0, lastKey = null, settleMs = 0, settleTimeout = false;
    while (performance.now() - t1 < settleMaxMs) {
      await new Promise(function(r){ setTimeout(r, 80); });
      var s = U.workset();
      if (!s) continue;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === lastKey) stable++; else { stable = 0; lastKey = key; }
      if (stable >= 2) { settleMs = performance.now() - t1; break; }
    }
    if (!settleMs) { settleMs = performance.now() - t1; settleTimeout = true; }
    var dCounter = {};
    if (c0 && c1) {
      dCounter = {
        max_frame_ms: +(c1.max_frame_ms - c0.max_frame_ms).toFixed(1),
        frames_used: c1.frames_used - c0.frames_used,
        slice_count: c1.slice_count - c0.slice_count,
        budget_exceeded: c1.budget_exceeded - c0.budget_exceeded,
        executed: c1.executed - c0.executed,
        dropped: c1.dropped - c0.dropped,
      };
    }
    return {
      frac: frac, scrollTop: target, maxScroll: max,
      scrollHeight: Math.round(pane.scrollHeight),
      jumpMs: +jumpMs.toFixed(1),
      frames: gapStats(gaps),
      counters: dCounter,
      workset: ws,
      dom: dom,
      events: ev,
      jobs: jobs,
      math: mstat,
      cost: cost,
      loaf: loaf,
      settleMs: +settleMs.toFixed(0), settleTimeout: settleTimeout,
    };
  };

  U.toTop = async function(){
    var pane = document.getElementById('preview-pane');
    pane.scrollTop = 0;
    var t0 = performance.now(), last = null, stable = 0;
    while (performance.now() - t0 < 30000) {
      await new Promise(function(r){ setTimeout(r, 200); });
      var s = U.workset();
      if (!s) continue;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === last) stable++; else { stable = 0; last = key; }
      if (stable >= 4) return { ms:+(performance.now()-t0).toFixed(0), stats:s };
    }
    return { ms:+(performance.now()-t0).toFixed(0), stats:U.workset(), timeout:true };
  };
  U.toBottom = async function(){
    var pane = document.getElementById('preview-pane');
    pane.scrollTop = Math.max(0, pane.scrollHeight - pane.clientHeight);
    var t0 = performance.now(), last = null, stable = 0;
    while (performance.now() - t0 < 30000) {
      await new Promise(function(r){ setTimeout(r, 200); });
      var s = U.workset();
      if (!s) continue;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === last) stable++; else { stable = 0; last = key; }
      if (stable >= 4) return { ms:+(performance.now()-t0).toFixed(0), stats:s };
    }
    return { ms:+(performance.now()-t0).toFixed(0), stats:U.workset(), timeout:true };
  };
  return 1;
})()`);

/* ── 测量可信门 ── */
const vis = await cdp.ev('({visibility:document.visibilityState, w:innerWidth, h:innerHeight})', false);
const idle = await cdp.ev(`(function(){
  return new Promise(function(res){
    var g=[], last=performance.now(), n=0, to=setTimeout(function(){ res({timeout:true, n:n}); }, 6000);
    (function t(){
      var now=performance.now(); g.push(now-last); last=now;
      if (++n >= 145) {
        clearTimeout(to);
        g.sort(function(a,b){ return a-b; });
        res({ n:g.length, p50:+g[Math.floor(g.length*0.5)].toFixed(1), p95:+g[Math.floor(g.length*0.95)].toFixed(1), max:+g[g.length-1].toFixed(1) });
      } else requestAnimationFrame(t);
    })();
  });
})()`);
console.log('[idle-raf]', JSON.stringify(idle), 'visibility=' + vis.visibility);
if (idle.timeout || !(idle.p50 <= 20)) {
  console.error('MEASUREMENT INVALID: 空转 rAF p50=' + idle.p50 + 'ms（窗口可能被最小化/遮挡）');
  process.exit(4);
}
if (vis.visibility !== 'visible') {
  console.error('MEASUREMENT INVALID: document.visibilityState=' + vis.visibility);
  process.exit(4);
}

/* ────────────────────────── 打开文档 ────────────────────────── */
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

function concurrency() {
  try {
    const o = execFileSync('powershell', ['-NoProfile', '-Command',
      "'py:' + @(Get-Process -Name python -EA SilentlyContinue).Count + ' wv2:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count + ' node:' + @(Get-Process -Name node -EA SilentlyContinue).Count + ' cpu:' + [math]::Round((Get-Counter '\\Processor(_Total)\\% Processor Time' -MaxSamples 1).CounterSamples[0].CookedValue,1)"],
      { encoding: 'utf8', timeout: 20000 });
    return o.trim();
  } catch (e) { return 'unavailable'; }
}

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
  return await cdp.ev('window.__ud.toTop()');
}

const R = {
  schema: 'memoria-updown-positions/v1',
  at: new Date().toISOString(),
  concurrencyBefore: concurrency(),
  head: (() => { try { return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { return null; } })(),
  dirty: (() => { try { return execFileSync('git', ['status', '--porcelain', '--', 'src/memoria/ui/static/app/js'], { encoding: 'utf8' }).trim(); } catch { return null; } })(),
  scriptSha256: createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'),
  argv: process.argv.slice(2),
  env: { mode: 'realapp-webview2', port, doc: DOC, rounds: ROUNDS, windowMs: WIN_MS, positions: POSITIONS },
  gpu, visibility: vis, idleRafBaseline: idle,
  window: await cdp.ev('({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,ua:navigator.userAgent})', false),
  appVersion: await cdp.ev('(window.MemoriaApp && (MemoriaApp.version || (document.title||"").trim())) || null', false),
  rounds: [],
};

{
  // 打开之后才做规模校验（页面启动时可能还停在小文件上）
}
R.open = { top: await openDoc(), heap: await heap() };
{
  const st0 = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
  if (!st0 || !(st0.totalBlocks >= 3900)) {
    console.error('OPEN FAILED: totalBlocks=' + (st0 && st0.totalBlocks) + ' materialized=' + (st0 && st0.materialized));
    process.exit(5);
  }
  R.open.stats = st0;
}
console.log('[open] totalBlocks=' + ((R.open.top.stats || {}).totalBlocks) + ' heap=' + R.open.heap.usedMB + 'MB');

console.log('[probe] observe=' + await cdp.ev('window.__ud.observe()', false));
console.log('[probe] jobProf=' + JSON.stringify(await cdp.ev('window.__ud.installJobProf()', false)));
console.log('[probe] costProbes=' + JSON.stringify(await cdp.ev('window.__ud.installCostProbes()', false)));
console.log('[probe] loaf=' + await cdp.ev('window.__ud.installLoaf()', false));
if (MMD === 'on' || MMD === 'off') {
  await cdp.ev(`(function(){ window.__MEMORIA_MMD_CACHE = ${MMD === 'on'}; return 1; })()`, false);
  console.log('[probe] mermaid cache =', MMD);
}
await cdp.ev('window.__ud.startFrames()', false);

const FRACS = [];
for (let i = 1; i <= POSITIONS; i++) FRACS.push(+(i / (POSITIONS + 1)).toFixed(4));

function summarize(run) {
  const down = run.down, up = run.up;
  const rows = [];
  for (let i = 0; i < down.length; i++) {
    const d = down[i], u = up[i];
    const dm = d && d.frames ? d.frames.max : null;
    const um = u && u.frames ? u.frames.max : null;
    rows.push({
      frac: d ? d.frac : null,
      downMax: dm, upMax: um,
      ratio: (dm && um) ? +(um / dm).toFixed(3) : null,
      downP95: d && d.frames ? d.frames.p95 : null,
      upP95: u && u.frames ? u.frames.p95 : null,
      downNode: d && d.frames ? d.frames.p50 : null,
      upNode: u && u.frames ? u.frames.p50 : null,
      upEvents: u ? u.events : null,
      downCounters: d ? d.counters : null,
      upCounters: u ? u.counters : null,
      downJobs: d ? d.jobs : null,
      upJobs: u ? u.jobs : null,
      upMath: u ? u.math : null,
      upWorkset: u ? u.workset : null,
      downCost: d ? d.cost : null,
      upCost: u ? u.cost : null,
      upLoaf: u ? u.loaf : null,
      downLoaf: d ? d.loaf : null,
    });
  }
  return rows;
}

for (let r = 0; r < ROUNDS; r++) {
  const arm = AB ? AB_ORDER[r % AB_ORDER.length] : null;
  if (AB) {
    const caps = arm === 'A' ? AB_A : AB_B;
    await cdp.ev(`(function(){ window.__MEMORIA_MATH_BATCH_IDLE=${caps.idle}; window.__MEMORIA_MATH_BATCH_SCROLLING=${caps.scrolling}; window.__MEMORIA_EVICT_BATCH_MAX=${caps.evict};`
      + (AB_MMD ? ` window.__MEMORIA_MMD_CACHE=${arm === 'B'};` : '')
      + ` return 1; })()`, false);
  }
  await cdp.ev('window.__ud.toTop()');
  const run = { round: r + 1, arm, caps: AB ? (arm === 'A' ? AB_A : AB_B) : null, order: ORDER, down: [], up: [], concurrency: concurrency() };
  const t0 = Date.now();
  if (ORDER === 'updown') {
    // 对照：先向上（从底部），再向下。用于区分"第二遍"效应 vs "向上"方向效应。
    await cdp.ev('window.__ud.toBottom()');
    const tA = Date.now();
    for (let i = FRACS.length - 1; i >= 0; i--) {
      run.up[i] = await cdp.ev(`window.__ud.measureAt(${FRACS[i]}, ${WIN_MS}, ${SETTLE_MAX_MS})`);
    }
    run.upWallMs = Date.now() - tA;
    const tB = Date.now();
    for (let i = 0; i < FRACS.length; i++) {
      run.down[i] = await cdp.ev(`window.__ud.measureAt(${FRACS[i]}, ${WIN_MS}, ${SETTLE_MAX_MS})`);
    }
    run.downWallMs = Date.now() - tB;
  } else {
    for (const f of FRACS) {
      run.down.push(await cdp.ev(`window.__ud.measureAt(${f}, ${WIN_MS}, ${SETTLE_MAX_MS})`));
    }
    run.downWallMs = Date.now() - t0;
    const t1 = Date.now();
    for (let i = FRACS.length - 1; i >= 0; i--) {
      run.up[i] = await cdp.ev(`window.__ud.measureAt(${FRACS[i]}, ${WIN_MS}, ${SETTLE_MAX_MS})`);
    }
    run.upWallMs = Date.now() - t1;
  }
  run.rows = summarize({ down: run.down, up: run.up });
  run.heap = await heap();
  run.concurrencyAfter = concurrency();
  R.rounds.push(run);
  const ratios = run.rows.map(x => x.ratio).filter(x => typeof x === 'number');
  const sorted = ratios.slice().sort((a, b) => a - b);
  const med = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null;
  console.log(`[round ${r + 1}${arm ? ' ' + arm : ''}] order=${ORDER} down=${run.downWallMs}ms up=${run.upWallMs}ms`
    + ` ratio(up/down) med=${med} min=${sorted[0]} max=${sorted[sorted.length - 1]}` + ` heap=${run.heap.usedMB}MB`);
  for (const x of run.rows) if (x.ratio && x.ratio > 1.2) console.log(`   >1.2 @${(x.frac * 100).toFixed(0)}% : ${x.downMax} → ${x.upMax} (${x.ratio}×)`);
}

/* ────────────────────────── 汇总 ────────────────────────── */
function pctOf(arr, p) { return arr.length ? arr[Math.min(arr.length - 1, Math.floor(arr.length * p))] : null; }

function analyze(runs) {
  const posCount = runs[0] ? runs[0].rows.length : 0;
  const perPos = [];
  for (let i = 0; i < posCount; i++) {
    const rs = runs.map(r => r.rows[i].ratio).filter(x => typeof x === 'number').sort((a, b) => a - b);
    const downs = runs.map(r => r.rows[i].downMax).filter(x => typeof x === 'number').sort((a, b) => a - b);
    const ups = runs.map(r => r.rows[i].upMax).filter(x => typeof x === 'number').sort((a, b) => a - b);
    perPos.push({
      frac: runs[0].rows[i].frac,
      pct: Math.round(runs[0].rows[i].frac * 1000) / 10,
      ratioMed: rs.length ? +rs[Math.floor(rs.length / 2)].toFixed(3) : null,
      downMed: downs.length ? downs[Math.floor(downs.length / 2)] : null,
      upMed: ups.length ? ups[Math.floor(ups.length / 2)] : null,
      upToDownRatioOfMed: (downs.length && ups.length)
        ? +(ups[Math.floor(ups.length / 2)] / downs[Math.floor(downs.length / 2)]).toFixed(3) : null,
      upTypesetMed: (() => {
        const v = runs.map(r => ((r.rows[i].upCost || {}).typeset || {}).ms).filter(x => typeof x === 'number').sort((a, b) => a - b);
        return v.length ? v[Math.floor(v.length / 2)] : null;
      })(),
      upMermaidMed: (() => {
        const v = runs.map(r => ((r.rows[i].upCost || {}).mermaid || {}).ms).filter(x => typeof x === 'number').sort((a, b) => a - b);
        return v.length ? v[Math.floor(v.length / 2)] : null;
      })(),
    });
  }
  const allRatios = perPos.map(x => x.ratioMed).filter(x => typeof x === 'number').sort((a, b) => a - b);
  const worst = perPos.filter(x => typeof x.ratioMed === 'number').sort((a, b) => b.ratioMed - a.ratioMed)[0] || null;
  const keyPositions = [30, 50, 70, 90].map((pctv) => {
    const row = perPos.reduce((best, x) => Math.abs(x.pct - pctv) < Math.abs((best && best.pct) - pctv) ? x : best, null);
    return row ? { pct: pctv, ratio: row.ratioMed, down: row.downMed, up: row.upMed, pass: (row.ratioMed != null && row.ratioMed <= 1.2) } : { pct: pctv, ratio: null, pass: false };
  });
  return {
    n: runs.length,
    perPos,
    ratioMed: pctOf(allRatios, 0.5),
    ratioP90: pctOf(allRatios, 0.9),
    ratioWorst: worst ? { pct: worst.pct, ratio: worst.ratioMed, down: worst.downMed, up: worst.upMed } : null,
    over12: perPos.filter(x => typeof x.ratioMed === 'number' && x.ratioMed > 1.2).map(x => ({ pct: x.pct, ratio: x.ratioMed })),
    keyPositions, gate4: keyPositions.filter(k => k.pass).length,
    anyFrameOver200: runs.some(r => r.down.concat(r.up).some(m => m && m.frames && m.frames.max > 200)),
    heapMB: runs.map(r => r.heap.usedMB),
    domNodesMax: Math.max(...runs.map(r => Math.max(...r.down.concat(r.up).map(m => (m.dom && m.dom.nodes) || 0)))),
    downWallMs: runs.map(r => r.downWallMs), upWallMs: runs.map(r => r.upWallMs),
    downWallMed: pctOf(runs.map(r => r.downWallMs).sort((a, b) => a - b), 0.5),
    upWallMed: pctOf(runs.map(r => r.upWallMs).sort((a, b) => a - b), 0.5),
    heightDrift: runs.map(r => (r.up[r.up.length - 1] || {}).workset ? r.up[r.up.length - 1].workset.heightDriftPx : null),
  };
}

R.summary = Object.assign({
  rounds: ROUNDS, positions: POSITIONS, windowMs: WIN_MS, order: ORDER,
  concurrency: { before: R.concurrencyBefore, after: concurrency() },
}, analyze(R.rounds));

if (AB) {
  const armA = R.rounds.filter(r => r.arm === 'A');
  const armB = R.rounds.filter(r => r.arm === 'B');
  R.summary.ab = {
    order: AB_ORDER.slice(0, ROUNDS), capsA: AB_A, capsB: AB_B, mmdAB: AB_MMD,
    A: armA.length ? analyze(armA) : null,
    B: armB.length ? analyze(armB) : null,
  };
  const fmt = (s) => s ? `gate4=${s.gate4}/4 med=${s.ratioMed} p90=${s.ratioP90} over12=${s.over12.length} wall(d/u)=${s.downWallMed}/${s.upWallMed} heap=${Math.max(...s.heapMB)}` : '-';
  console.log('\n[AB] A(200/60):', fmt(R.summary.ab.A));
  console.log('[AB] B(48/24):', fmt(R.summary.ab.B));
}

writeFileSync(outPath, JSON.stringify(R, null, 2), 'utf8');
console.log('\n[SUMMARY]', JSON.stringify(R.summary, null, 1));
console.log('[concurrency]', R.summary.concurrency.before, '->', R.summary.concurrency.after);
console.log('[out]', outPath);
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
