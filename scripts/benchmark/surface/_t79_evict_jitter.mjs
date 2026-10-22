/**
 * task-79 —— 核查 `17ee05d9`（淘汰饥饿修复）是否引入“淘汰抖动 / 回流”。
 *
 * 口径（真机 pywebview + WebView2）：
 *   · 文档 `教材/08_第8章_差错控制编码.md`（4001 块），`window.__MEMORIA_LAZY=true`，预览态；
 *   · 测量可信门：WebGL 可用 + 打开后空转 rAF p50 ≤ 20ms + totalBlocks ≥ 3900；
 *   · 观测器只做 childList / 节点自身 class 判断（不做子树查询），block index 取
 *     `data--block-index`（真块与占位块都带）。
 *
 * 三项核心读数：
 *   1) 回流：同一 index 被换出（真块→占位）后 **≤ --back-ms（默认 2000）** 又被物化
 *      （占位→真块）⇒ back = 回流次数；backRate = back / evict。
 *   2) 淘汰量：workset.evictTotal 增量、`__MEMORIA_EVICT_PROFILE` 的 batches / blocks、
 *      `lazy_evict` 作业执行次数（包装 MemoriaScheduler.schedule 统计，按优先级与 kind）。
 *   3) 帧成本：逐位置 rAF 间隔 max/p95 + `MemoriaScheduler.counters().max_frame_ms` 增量。
 *
 * 工作负载（每次运行同一序列）：
 *   W1 down/up：19 个位置（5%..95%，5% 一步），每位置瞬时跳转 + 600ms 采样 + 稳定等待；
 *                第一遍 down 是硬判据。
 *   W2 pressure drag：注入 P2（每 60ms 一个 8ms 忙等作业）+ 每帧 900px 连续下拖 6s；
 *                这是 17ee05d9 的复现场景（修复前 maxMat 3228）。
 *   W3 oscillate：以 120px/帧 下拖 2 屏再上拖 2 屏，循环 6s（无注入）—— 最直接的回流压力。
 *
 * 用法：
 *   node scripts/benchmark/surface/_t79_evict_jitter.mjs --port 9635 --out <json> --variant V4
 */
import fs from 'node:fs';
import { createHash } from 'node:crypto';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  if (i < 0) return def;
  const v = process.argv[i + 1];
  return v && !v.startsWith('--') ? v : true;
}
const PORT = Number(arg('port', 9635));
const OUT = String(arg('out', ''));
const VARIANT = String(arg('variant', 'unknown'));
const DOC = String(arg('doc', '教材/08_第8章_差错控制编码.md'));
const WIN_MS = Number(arg('window-ms', 600));
const SETTLE_MAX_MS = Number(arg('settle-max-ms', 900));
const BACK_MS = Number(arg('back-ms', 2000));
const DRAG_MS = Number(arg('drag-ms', 6000));
const DRAG_STEP = Number(arg('drag-step', 900));
const P2_MS = Number(arg('p2-ms', 8));
const OSC_MS = Number(arg('osc-ms', 6000));
const OSC_STEP = Number(arg('osc-step', 120));
const OSC_SCREENS = Number(arg('osc-screens', 6));
const DRAG_REPS = Number(arg('drag-reps', 2));
const OSC_REPS = Number(arg('osc-reps', 2));
if (!OUT) { console.error('usage: --port <cdp> --out <json> --variant <label>'); process.exit(2); }

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
      ' ' + JSON.stringify((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || '').slice(0, 500));
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expr, timeoutMs = 90000, stepMs = 200) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      try { if (await this.ev(`!!(${expr})`, false)) return true; } catch { /* page settling */ }
      await sleep(stepMs);
    }
    return false;
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

/* ─────────────── 连页面 ─────────────── */
let page = null;
for (let a = 0; a < 90; a++) {
  try {
    const l = await httpJson(`http://127.0.0.1:${PORT}/json/list`);
    page = (l || []).find((t) => t.type === 'page' &&
      /^http:\/\/127\.0\.0\.1:\d+\//.test(t.url || '') &&
      !/devtools/.test(t.url || '') && t.webSocketDebuggerUrl);
  } catch { /* app booting */ }
  if (page) break;
  await sleep(1000);
}
if (!page) { console.error('no page on port ' + PORT); process.exit(2); }
console.log('[page]', page.title, page.url);

const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Performance.enable').catch(() => {});
await cdp.send('HeapProfiler.enable').catch(() => {});
if (!(await cdp.waitFor('window.MemoriaApp && window.MemoriaApp.openFile', 120000))) {
  console.error('app not ready'); process.exit(2);
}
// KB 列表就绪后再 openFile（启动期 app 会自动打开默认文件，抢跑会被覆盖 ⇒ 这是既有坑）
await cdp.waitFor('(window.state && String(state.kbPath||"").length>0 && Array.isArray(state.files) && state.files.length>0)', 90000, 300);
console.log('[pre]', JSON.stringify(await cdp.ev('({kbPath:(window.state||{}).kbPath, files:((window.state||{}).files||[]).length, currentPath:(window.state||{}).currentPath, viewMode:(window.state||{}).viewMode})', false)));

const gpu = await cdp.ev(`(function(){try{var c=document.createElement('canvas');var gl=c.getContext('webgl')||c.getContext('experimental-webgl');if(!gl)return {webgl:false};var e=gl.getExtension('WEBGL_debug_renderer_info');return {webgl:true,renderer:e?gl.getParameter(e.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)};}catch(err){return {webgl:false,err:String(err)}}})()`, false);
if (!gpu || !gpu.webgl) { console.error('webgl unavailable — 不是真机口径:', JSON.stringify(gpu)); process.exit(2); }
console.log('[gpu]', gpu.renderer);

/* ─────────────── 页面内探针 ─────────────── */
const PAGE = `(function () {
  var U = window.__t79 = {};
  U.backMs = __BACK_MS__;
  U._on = false; U._last = 0; U._frames = []; U._mo = null;
  U._st = null;
  U._sched = null;

  U.workset = function () {
    try { return window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null; } catch (e) { return null; }
  };
  U.token = function () { try { return (window.state && window.state.previewToken) | 0; } catch (e) { return 0; } };
  U.counters = function () {
    try { return window.MemoriaScheduler ? window.MemoriaScheduler.counters() : null; } catch (e) { return null; }
  };
  U.mathStats = function () {
    var items = 0, detached = 0;
    try {
      var d = window.MathJax && MathJax.startup && MathJax.startup.document;
      if (d && d.math) { for (var it of d.math) { items++; if (it.typesetRoot && !it.typesetRoot.isConnected) detached++; } }
    } catch (e) {}
    return { items: items, detached: detached };
  };
  U.dom = function () {
    var pv = document.getElementById('preview');
    return { nodes: pv ? pv.getElementsByTagName('*').length : null,
             mjx: pv ? pv.querySelectorAll('mjx-container').length : null };
  };

  /* ── 回流观测：只看 childList 的 addedNodes，判断节点自身 class ── */
  U.resetStats = function () {
    U._st = {
      evict: 0, remat: 0, back: 0, backDts: [], backBlocks: {},
      evictCounts: {}, repeat2: 0, lastEvict: {}, rebuilds: 0, t0: performance.now(),
    };
  };
  U.observe = function () {
    U.resetStats();
    // 观察 #preview 整棵子树：既能看到块事件，也能看到整段 .-preview-content 被重建替换
    // （整篇重渲染会重置产品内 _lazyEvictCount；若观察器只在旧容器上会永久失聪）。
    var host = document.getElementById('preview');
    if (!host) return 'no-host';
    if (U._mo) { try { U._mo.disconnect(); } catch (e) {} }
    U._mo = new MutationObserver(function (muts) {
      var S = U._st;
      // 先扫一遍：若本批含 .-preview-content 新增 ⇒ 整篇重建。
      // 重建会在同一个 task 内把 4001 个占位逐个 append（observer 会全部看到），
      // 它们**不是淘汰**；若按普通 addedNode 计数会虚增 4000+ 次“淘汰/回流”。
      var rebuilding = false;
      for (var pi = 0; pi < muts.length; pi++) {
        var pa = muts[pi].addedNodes;
        for (var pj = 0; pj < pa.length; pj++) {
          var pn = pa[pj];
          if (pn && pn.nodeType === 1 && pn.classList && pn.classList.contains('-preview-content')) {
            rebuilding = true; break;
          }
        }
        if (rebuilding) break;
      }
      if (rebuilding) { S.rebuilds++; S.lastEvict = {}; }
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        for (var a = 0; a < m.addedNodes.length; a++) {
          var n = m.addedNodes[a];
          if (!n || n.nodeType !== 1) continue;
          var cl0 = n.classList;
          if (cl0 && cl0.contains('-preview-content')) continue;
          if (!n.getAttribute) continue;
          var idx = parseInt(n.getAttribute('data--block-index'), 10);
          if (isNaN(idx) || idx < 0) continue;
          var cl = cl0;
          if (!cl) continue;
          if (cl.contains('-pv-placeholder')) {
            if (rebuilding) continue;   // 重建时的初始占位 ≠ 淘汰
            S.evict++;
            S.evictCounts[idx] = (S.evictCounts[idx] || 0) + 1;
            S.lastEvict[idx] = performance.now();
          } else if (cl.contains('-src-block')) {
            S.remat++;
            var te = S.lastEvict[idx];
            if (te != null) {
              var dt = performance.now() - te;
              if (dt <= U.backMs) {
                S.back++;
                if (S.backDts.length < 20000) S.backDts.push(dt);
                S.backBlocks[idx] = (S.backBlocks[idx] || 0) + 1;
                if (S.backBlocks[idx] === 2) S.repeat2++;
              }
              delete S.lastEvict[idx];
            }
          }
        }
      }
    });
    U._mo.observe(host, { childList: true, subtree: true });
    return 'observing';
  };
  function q(a, p) { if (!a.length) return null; var b = a.slice().sort(function (x, y) { return x - y; }); return +b[Math.min(b.length - 1, Math.floor(b.length * p))].toFixed(1); }
  U.readStats = function () {
    var S = U._st || { evict: 0, remat: 0, back: 0, backDts: [], backBlocks: {}, evictCounts: {}, repeat2: 0, rebuilds: 0 };
    var uniq = 0; for (var k in S.backBlocks) uniq++;
    var evUniq = 0; for (var k2 in S.evictCounts) evUniq++;
    return {
      evict: S.evict, remat: S.remat, back: S.back,
      backRatePct: S.evict ? +(S.back * 100 / S.evict).toFixed(1) : null,
      backBlocks: uniq, evictBlocks: evUniq, repeat2: S.repeat2 || 0,
      rebuilds: S.rebuilds || 0,
      backDtP50: q(S.backDts, 0.5), backDtP95: q(S.backDts, 0.95),
      backDtMax: S.backDts.length ? +Math.max.apply(null, S.backDts).toFixed(1) : null,
      windowMs: U.backMs,
    };
  };

  /* ── 调度器：按 priority / kind 统计入队与执行（只包一层计时，不改语义） ── */
  U.resetSched = function () {
    U._sched = { queued: {}, exec: {}, ms: {}, kind: {}, pk: {}, pkms: {}, qpk: {}, err: 0 };
  };
  U.installSched = function () {
    U.resetSched();
    var S = window.MemoriaScheduler;
    if (!S || typeof S.schedule !== 'function') return 'no-scheduler';
    if (S.__t79Patched) return 'already';
    var orig = S.schedule;
    S.schedule = function (spec) {
      try {
        var p = (spec && typeof spec.priority === 'number') ? spec.priority : 3;
        var k = (spec && spec.kind) || '?';
        var Q = U._sched.queued; Q[p] = (Q[p] || 0) + 1;
        var K = U._sched.kind; K[k] = (K[k] || 0) + 1;
        var QPK = U._sched.qpk; QPK[p + '|' + k] = (QPK[p + '|' + k] || 0) + 1;
        if (spec && typeof spec.run === 'function' && !spec.run.__t79Wrapped) {
          var r = spec.run;
          var w = function () {
            var t = performance.now(), out;
            try { out = r.apply(this, arguments); }
            catch (e) { U._sched.err++; throw e; }
            var d = performance.now() - t;
            var E = U._sched.exec, M = U._sched.ms;
            E[p] = (E[p] || 0) + 1; M[p] = (M[p] || 0) + d;
            var PK = U._sched.pk, PKM = U._sched.pkms;
            var kk = p + '|' + k;
            PK[kk] = (PK[kk] || 0) + 1; PKM[kk] = (PKM[kk] || 0) + d;
            return out;
          };
          w.__t79Wrapped = true;
          spec.run = w;
        }
      } catch (e) {}
      return orig.call(S, spec);
    };
    S.__t79Patched = true;
    return 'patched';
  };
  U.schedSnap = function () {
    return JSON.parse(JSON.stringify(U._sched || { queued: {}, exec: {}, ms: {}, kind: {}, pk: {}, pkms: {}, qpk: {}, err: 0 }));
  };
  function schedDelta(a, b) {
    var o = { queued: {}, exec: {}, ms: {}, kind: {}, pk: {}, pkms: {}, qpk: {}, err: (b.err || 0) - (a.err || 0) };
    ['queued', 'exec', 'ms', 'kind', 'pk', 'pkms', 'qpk'].forEach(function (g) {
      var A = a[g] || {}, B = b[g] || {};
      for (var k in B) { var d = B[k] - (A[k] || 0); if (d) o[g][k] = (g === 'ms' || g === 'pkms') ? +d.toFixed(1) : d; }
    });
    return o;
  }

  /* ── 淘汰 profile（产品内建，只在 enable 后计量） ── */
  U.resetProfile = function () {
    var P = window.__MEMORIA_EVICT_PROFILE;
    if (!P) return false;
    P.reset();
    return true;
  };
  U.readProfile = function () {
    var P = window.__MEMORIA_EVICT_PROFILE;
    if (!P) return null;
    var r = P.read();
    if (!r) return null;
    return { batches: r.batches, blocks: r.blocks, totalMs: +r.totalMs.toFixed(1),
             maxTotalMs: +r.maxTotalMs.toFixed(1), maxApplyMs: +r.maxApplyMs.toFixed(1),
             mathClearMs: +r.mathClearMs.toFixed(1), blocksWithMath: r.blocksWithMath };
  };

  /* ── 帧 ── */
  U.startFrames = function () {
    if (U._on) return 1;
    U._on = true; U._last = performance.now(); U._frames = [];
    (function tick() {
      if (!U._on) return;
      var now = performance.now();
      U._frames.push(now - U._last); U._last = now;
      requestAnimationFrame(tick);
    })();
    return 1;
  };
  U.stopFrames = function () { U._on = false; return 1; };
  U.readFrames = function () {
    var a = U._frames.slice();
    var n = a.length;
    function qq(p) { return n ? +a.slice().sort(function (x, y) { return x - y; })[Math.min(n - 1, Math.floor(n * p))].toFixed(1) : null; }
    return { n: n, p50: qq(0.5), p95: qq(0.95), max: n ? +Math.max.apply(null, a).toFixed(1) : null,
             over50: a.filter(function (x) { return x > 50; }).length,
             over100: a.filter(function (x) { return x > 100; }).length };
  };

  U.settle = async function (maxMs) {
    var t0 = performance.now(), last = null, stable = 0;
    while (performance.now() - t0 < maxMs) {
      await new Promise(function (r) { setTimeout(r, 80); });
      var s = U.workset(); if (!s) continue;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === last) stable++; else { stable = 0; last = key; }
      if (stable >= 2) return { ms: +(performance.now() - t0).toFixed(0), stats: s };
    }
    return { ms: +(performance.now() - t0).toFixed(0), stats: U.workset(), timeout: true };
  };
  U.toTop = async function () {
    var pane = document.getElementById('preview-pane');
    pane.scrollTop = 0;
    var t0 = performance.now(), last = null, stable = 0;
    while (performance.now() - t0 < 30000) {
      await new Promise(function (r) { setTimeout(r, 200); });
      var s = U.workset(); if (!s) continue;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === last) stable++; else { stable = 0; last = key; }
      if (stable >= 4) return { ms: +(performance.now() - t0).toFixed(0), stats: s };
    }
    return { ms: +(performance.now() - t0).toFixed(0), stats: U.workset(), timeout: true };
  };
  U.toBottom = async function () {
    var pane = document.getElementById('preview-pane');
    pane.scrollTop = Math.max(0, pane.scrollHeight - pane.clientHeight);
    var t0 = performance.now(), last = null, stable = 0;
    while (performance.now() - t0 < 30000) {
      await new Promise(function (r) { setTimeout(r, 200); });
      var s = U.workset(); if (!s) continue;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === last) stable++; else { stable = 0; last = key; }
      if (stable >= 4) return { ms: +(performance.now() - t0).toFixed(0), stats: s };
    }
    return { ms: +(performance.now() - t0).toFixed(0), stats: U.workset(), timeout: true };
  };

  /* ── W1：单位置（与 perf_updown_positions 同口径 + 回流/淘汰/调度增量） ── */
  U.measureAt = async function (frac, winMs, settleMaxMs) {
    var pane = document.getElementById('preview-pane');
    if (!pane) return { err: 'no-pane' };
    var max = Math.max(0, pane.scrollHeight - pane.clientHeight);
    var target = Math.round(max * frac);
    var c0 = U.counters(), s0 = U.schedSnap();
    var tk0 = U.token();
    U.resetStats(); U.resetProfile(); U.startFrames();
    U._frames = []; U._last = performance.now();
    var t0 = performance.now();
    pane.scrollTop = target;
    var jumpMs = performance.now() - t0;
    await new Promise(function (r) { setTimeout(r, winMs); });
    var frames = U.readFrames(); U.stopFrames();
    var c1 = U.counters(), s1 = U.schedSnap();
    var tk1 = U.token();
    var ws = U.workset(), dom = U.dom(), ev = U.readStats(), prof = U.readProfile(), mstat = U.mathStats();
    var settle = await U.settle(settleMaxMs);
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
      frac: frac, scrollTop: target, maxScroll: max, scrollHeight: Math.round(pane.scrollHeight),
      jumpMs: +jumpMs.toFixed(1), frames: frames, counters: dCounter, workset: ws, dom: dom,
      events: ev, profile: prof, sched: schedDelta(s0, s1),
      math: mstat, settleMs: settle.ms, settleTimeout: !!settle.timeout,
      tokenDelta: tk1 - tk0, max_frame_ms_abs: c1 ? c1.max_frame_ms : null,
      evictPressureSchedules: ws ? ws.evictPressureSchedules : null,
      evictPendingSkips: ws ? ws.evictPendingSkips : null,
    };
  };

  /* ── W2：压力场景（P2 积压 + 连续下拖） ── */
  U.pressureDrag = async function (ms, stepPx, p2Ms) {
    var pane = document.getElementById('preview-pane');
    var max = Math.max(0, pane.scrollHeight - pane.clientHeight);
    var c0 = U.counters(), s0 = U.schedSnap(), w0 = U.workset();
    var tk0 = U.token();
    U.resetStats(); U.resetProfile(); U.startFrames();
    U._frames = []; U._last = performance.now();
    var p2N = 0, p2Timer = null;
    if (p2Ms > 0) {
      p2Timer = setInterval(function () {
        try {
          MemoriaScheduler.schedule({ kind: 't79_p2_load', key: 't79-p2-' + (p2N++), priority: 2, replace: false,
            run: function () { var t = performance.now(); while (performance.now() - t < p2Ms) {} } });
        } catch (e) {}
      }, 60);
    }
    var t0 = performance.now(), maxMat = 0, evFrames = 0, lastEv = -1, frames = 0;
    var res = await new Promise(function (done) {
      (function tick() {
        var now = performance.now();
        pane.scrollTop = Math.min(max, pane.scrollTop + stepPx);
        var ws = U.workset();
        frames++;
        if (ws) {
          if (ws.materialized > maxMat) maxMat = ws.materialized;
          if (lastEv >= 0 && ws.evictTotal > lastEv) evFrames++;
          lastEv = ws.evictTotal;
        }
        if (now - t0 < ms && pane.scrollTop < max) return requestAnimationFrame(tick);
        done({ totalMs: +(performance.now() - t0).toFixed(0), frames: frames, endScrollTop: Math.round(pane.scrollTop),
               max: Math.round(max), maxMat: maxMat, evFrames: evFrames, hitBottom: pane.scrollTop >= max });
      })();
    });
    if (p2Timer) clearInterval(p2Timer);
    U.stopFrames();
    var c1 = U.counters(), s1 = U.schedSnap();
    var ev = U.readStats(), prof = U.readProfile(), w1 = U.workset();
    var tk1 = U.token();
    var dCounter = {};
    if (c0 && c1) {
      dCounter = { max_frame_ms: +(c1.max_frame_ms - c0.max_frame_ms).toFixed(1),
        frames_used: c1.frames_used - c0.frames_used, slice_count: c1.slice_count - c0.slice_count,
        budget_exceeded: c1.budget_exceeded - c0.budget_exceeded, executed: c1.executed - c0.executed,
        dropped: c1.dropped - c0.dropped };
    }
    var st = await U.settle(2500);
    var w2 = U.workset();
    return {
      drag: res, frames: U.readFrames(), counters: dCounter, events: ev, profile: prof,
      sched: schedDelta(s0, s1), p2n: p2N,
      before: { materialized: w0 && w0.materialized, evictTotal: w0 && w0.evictTotal, pressureSchedules: w0 && w0.evictPressureSchedules, pendingSkips: w0 && w0.evictPendingSkips },
      after: { materialized: w2 && w2.materialized, evictTotal: w2 && w2.evictTotal, pressureSchedules: w2 && w2.evictPressureSchedules, pendingSkips: w2 && w2.evictPendingSkips },
      settleMs: st.ms, tokenDelta: tk1 - tk0, rebuilds: ev.rebuilds,
      max_frame_ms_abs: c1 ? c1.max_frame_ms : null,
    };
  };

  /* ── W3：来回振荡（小步、反复跨越工作集边缘） ── */
  U.oscillate = async function (ms, stepPx, screens) {
    var pane = document.getElementById('preview-pane');
    var viewH = pane.clientHeight || 720;
    var span = Math.max(viewH, Math.round(viewH * screens));
    var start = pane.scrollTop;
    var lo = Math.max(0, start), hi = Math.min(Math.max(0, pane.scrollHeight - pane.clientHeight), start + span);
    var c0 = U.counters(), s0 = U.schedSnap(), w0 = U.workset();
    var tk0 = U.token();
    U.resetStats(); U.resetProfile(); U.startFrames();
    U._frames = []; U._last = performance.now();
    var dir = 1, maxMat = 0, evFrames = 0, lastEv = -1, swings = 0;
    var t0 = performance.now();
    var res = await new Promise(function (done) {
      (function tick() {
        var now = performance.now();
        pane.scrollTop = pane.scrollTop + dir * stepPx;
        if (pane.scrollTop >= hi) { pane.scrollTop = hi; dir = -1; swings++; }
        else if (pane.scrollTop <= lo) { pane.scrollTop = lo; dir = 1; swings++; }
        var ws = U.workset();
        if (ws) {
          if (ws.materialized > maxMat) maxMat = ws.materialized;
          if (lastEv >= 0 && ws.evictTotal > lastEv) evFrames++;
          lastEv = ws.evictTotal;
        }
        if (now - t0 < ms) return requestAnimationFrame(tick);
        done({ totalMs: +(performance.now() - t0).toFixed(0), maxMat: maxMat, evFrames: evFrames,
               swings: swings, lo: Math.round(lo), hi: Math.round(hi) });
      })();
    });
    U.stopFrames();
    var c1 = U.counters(), s1 = U.schedSnap();
    var ev = U.readStats(), prof = U.readProfile(), w2 = U.workset();
    var tk1 = U.token();
    var dCounter = {};
    if (c0 && c1) {
      dCounter = { max_frame_ms: +(c1.max_frame_ms - c0.max_frame_ms).toFixed(1),
        frames_used: c1.frames_used - c0.frames_used, slice_count: c1.slice_count - c0.slice_count,
        budget_exceeded: c1.budget_exceeded - c0.budget_exceeded, executed: c1.executed - c0.executed,
        dropped: c1.dropped - c0.dropped };
    }
    var st = await U.settle(2500);
    return {
      osc: res, frames: U.readFrames(), counters: dCounter, events: ev, profile: prof,
      sched: schedDelta(s0, s1),
      before: { materialized: w0 && w0.materialized, evictTotal: w0 && w0.evictTotal },
      after: { materialized: (U.workset() || {}).materialized, evictTotal: (U.workset() || {}).evictTotal },
      settleMs: st.ms, tokenDelta: tk1 - tk0, rebuilds: ev.rebuilds,
      max_frame_ms_abs: c1 ? c1.max_frame_ms : null,
    };
  };

  return 1;
})()`.replace('__BACK_MS__', String(BACK_MS));

const install = await cdp.ev(PAGE);
console.log('[probe] install=', install);

/* ─────────────── 预览态 + 打开文档 ─────────────── */
await cdp.ev(`(function(){ window.__MEMORIA_LAZY = true; try { localStorage.setItem('memoria.perf.lazy','1'); } catch(e) {}
  var b = document.querySelector('.-view-btn[data-view="preview"]'); if (b && (window.state||{}).viewMode !== 'preview') b.click();
  return 1; })()`);
await cdp.waitFor('(window.state||{}).viewMode === "preview"', 20000);

await sleep(2500);
async function openDoc() {
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await cdp.ev(`(async function(){ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); return 'ok'; } catch(e){ return 'ERR:'+(e&&e.message); } })()`);
    let lastS = null, lastVm = null;
    for (let i = 0; i < 120; i++) {
      const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
      const vm = await cdp.ev('(window.state||{}).viewMode', false);
      lastS = s; lastVm = vm;
      if (vm === 'preview' && s && s.totalBlocks >= 3900) return { ok: true, attempt: attempt + 1, stats: s, openResult: r };
      await sleep(250);
    }
    console.log('[open] retry', attempt + 1, 'result=' + r, 'vm=' + lastVm, 'blocks=' + (lastS && lastS.totalBlocks),
      'path=' + JSON.stringify(await cdp.ev('(window.state||{}).currentPath', false)));
    await sleep(1200);
  }
  const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
  return { ok: false, stats: s };
}
const open = await openDoc();
console.log('[open]', JSON.stringify(open));
if (!open.ok) { console.error('OPEN FAILED totalBlocks=' + (open.stats && open.stats.totalBlocks)); process.exit(5); }

// 等预览 token 稳定：openFile 可能在首帧渲染后还排着一次整篇重渲染，
// 它会替换 .-preview-content 并把产品内 evictTotal 归零（否则 W1 中段读数作废）。
async function waitTokenStable(need = 8, iters = 80, step = 250) {
  let lastTok = -1, stable = 0;
  for (let i = 0; i < iters; i++) {
    const tk = await cdp.ev('(window.state||{}).previewToken|0', false);
    if (tk === lastTok) stable++; else stable = 0;
    lastTok = tk;
    if (stable >= need) break;
    await sleep(step);
  }
  return { token: lastTok, stable };
}
{
  const s1 = await waitTokenStable(8);
  console.log('[stabilize] token=' + s1.token + ' stable=' + s1.stable);
  await sleep(600);
  // 预热跳转：第一次大幅跳转若会触发延迟重渲染/大量首屏物化，让它落在**测量窗口之外**。
  const tokBefore = await cdp.ev('(window.state||{}).previewToken|0', false);
  await cdp.ev('(function(){var p=document.getElementById("preview-pane");p.scrollTop=Math.round((p.scrollHeight-p.clientHeight)*0.35);return 1;})()');
  await sleep(3200);
  await cdp.ev('window.__t79.toTop()');
  await sleep(1400);
  const tokAfter = await cdp.ev('(window.state||{}).previewToken|0', false);
  console.log('[warm] token ' + tokBefore + ' -> ' + tokAfter);
  if (tokAfter !== tokBefore) await sleep(4500);
  const s2 = await waitTokenStable(12);
  console.log('[stabilize2] token=' + s2.token + ' stable=' + s2.stable);
  await sleep(600);
}

async function measureClean(f, tries = 3) {
  let last = null;
  for (let t = 0; t < tries; t++) {
    last = await cdp.ev(`window.__t79.measureAt(${f}, ${WIN_MS}, ${SETTLE_MAX_MS})`);
    const bad = last && ((last.tokenDelta || 0) > 0 || ((last.events || {}).rebuilds || 0) > 0);
    if (!bad) return last;
    console.log('[w1-retry] @' + Math.round(f * 100) + '% tokenDelta=' + last.tokenDelta +
      ' rebuilds=' + ((last.events || {}).rebuilds || 0) + ' ev=' + ((last.events || {}).evict));
    await sleep(1800);
  }
  return last;
}

async function runClean(expr, tag, tries = 2) {
  let last = null;
  for (let t = 0; t < tries; t++) {
    last = await cdp.ev(expr);
    const bad = last && ((last.tokenDelta || 0) > 0 || ((last.events || {}).rebuilds || 0) > 0);
    if (!bad) return last;
    console.log('[' + tag + '-retry] tokenDelta=' + last.tokenDelta + ' rebuilds=' + ((last.events || {}).rebuilds || 0));
    await sleep(1800);
    await cdp.ev('window.__t79.toTop()');
  }
  return last;
}

const top = await cdp.ev('window.__t79.toTop()');
console.log('[top]', JSON.stringify(top));

/* ─────────────── 测量可信门 ─────────────── */
const vis = await cdp.ev('({visibility:document.visibilityState, w:innerWidth, h:innerHeight, dpr:devicePixelRatio})', false);
const idle = await cdp.ev(`(function(){
  return new Promise(function(res){
    var g=[], last=performance.now(), n=0, to=setTimeout(function(){ res({timeout:true,n:n}); }, 6000);
    (function t(){
      var now=performance.now(); g.push(now-last); last=now;
      if (++n >= 145) { clearTimeout(to); g.sort(function(a,b){return a-b;});
        res({n:g.length,p50:+g[Math.floor(g.length*0.5)].toFixed(1),p95:+g[Math.floor(g.length*0.95)].toFixed(1),max:+g[g.length-1].toFixed(1)});
      } else requestAnimationFrame(t);
    })();
  });
})()`);
console.log('[idle-raf]', JSON.stringify(idle), 'visibility=' + vis.visibility);
if (idle.timeout || !(idle.p50 <= 20)) { console.error('MEASUREMENT INVALID: idle rAF p50=' + idle.p50 + 'ms'); process.exit(4); }
if (vis.visibility !== 'visible') { console.error('MEASUREMENT INVALID: visibility=' + vis.visibility); process.exit(4); }

console.log('[probe] observe=' + await cdp.ev('window.__t79.observe()', false));
console.log('[probe] sched=' + await cdp.ev('window.__t79.installSched()', false));

/* ─────────────── 跑工作负载 ─────────────── */
const FRACS = [];
for (let i = 1; i <= 19; i++) FRACS.push(Math.round(i * 5) / 100);

const R = {
  schema: 'memoria-evict-jitter/v1',
  at: new Date().toISOString(),
  variant: VARIANT,
  doc: DOC,
  argv: process.argv.slice(2),
  gpu, visibility: vis, idleRafBaseline: idle,
  window: await cdp.ev('({w:innerWidth,h:innerHeight,dpr:devicePixelRatio,ua:navigator.userAgent})', false),
  appTitle: page.title, pageUrl: page.url,
  open, top,
  w1: null, w2: [], w3: [],
};

// W1：第一遍 down（升序），第二遍 up（降序）
{
  const down = [], up = [];
  await cdp.ev('window.__t79.toTop()');
  for (const f of FRACS) down.push(await measureClean(f));
  await cdp.ev('window.__t79.toBottom()');
  for (let i = FRACS.length - 1; i >= 0; i--) up[i] = await measureClean(FRACS[i]);
  R.w1 = { down, up };
}

// W2：压力场景重复（每次都从顶部开始，复现 17ee05d9 的注入场景）
for (let r = 0; r < DRAG_REPS; r++) {
  await cdp.ev('window.__t79.toTop()');
  R.w2.push(await runClean(`window.__t79.pressureDrag(${DRAG_MS}, ${DRAG_STEP}, ${P2_MS})`, 'w2'));
}
// W3：来回振荡重复
for (let r = 0; r < OSC_REPS; r++) {
  await cdp.ev('window.__t79.toTop()');
  await cdp.ev('(function(){var p=document.getElementById("preview-pane");p.scrollTop=Math.round((p.scrollHeight-p.clientHeight)*0.45);return p.scrollTop;})()');
  await sleep(900);
  R.w3.push(await runClean(`window.__t79.oscillate(${OSC_MS}, ${OSC_STEP}, ${OSC_SCREENS})`, 'w3'));
}

R.final = {
  workset: await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false),
  counters: await cdp.ev('window.MemoriaScheduler ? MemoriaScheduler.counters() : null', false),
  math: await cdp.ev('window.__t79.mathStats()', false),
  sched: await cdp.ev('window.__t79.schedSnap()', false),
  heap: await (async () => {
    await cdp.send('HeapProfiler.collectGarbage').catch(() => {});
    await sleep(200);
    try { const h = await cdp.send('Runtime.getHeapUsage'); return { usedMB: +(h.usedSize / 1048576).toFixed(2) }; } catch { return null; }
  })(),
};

R.appjs = await cdp.ev(`(function(){try{var s=document.querySelector('script[src*="app/js/app.js"]');return s?s.src:null;}catch(e){return null;}})()`, false);

fs.writeFileSync(OUT, JSON.stringify(R, null, 2), 'utf8');
console.log(JSON.stringify({
  variant: VARIANT,
  openBlocks: open.stats && open.stats.totalBlocks,
  idle: idle.p50,
  downMaxMed: med((R.w1.down || []).map((x) => x.frames && x.frames.max)),
  downP95Med: med((R.w1.down || []).map((x) => x.frames && x.frames.p95)),
  w2: R.w2.map((x) => ({ maxMat: x.drag.maxMat, ev: x.events.evict, back: x.events.back, backRate: x.events.backRatePct, batches: x.profile && x.profile.batches, evictMs: x.profile && x.profile.totalMs, maxFrame: x.frames.max })),
  w3: R.w3.map((x) => ({ maxMat: x.osc.maxMat, ev: x.events.evict, back: x.events.back, backRate: x.events.backRatePct, batches: x.profile && x.profile.batches, maxFrame: x.frames.max })),
}, null, 2));
console.log('[out]', OUT);
cdp.close();
setTimeout(() => process.exit(0), 300).unref();

function med(a) {
  const b = a.filter((x) => typeof x === 'number').sort((x, y) => x - y);
  return b.length ? b[Math.floor(b.length / 2)] : null;
}
