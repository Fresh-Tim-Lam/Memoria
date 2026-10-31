/**
 * task-63 0.4.7 P0-1：拖拽黑屏基线
 *
 * 打开 08 章（惰性）→ 快速拖到 80%（10 帧扫）→ 每 50ms 采样视口占位
 * 记录「视口内 ph>0 的连续时长」
 *
 * 同时记录：
 *   - flush batch capped 日志（看批次序列）
 *   - 每 50ms 采样的 ph 序列（还原空白曲线）
 *   - 帧间隔（看是否冻结）
 */
import { writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 120000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr, awaitPromise = false) {
    const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise, userGesture: true });
    if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || ''));
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expr, timeoutMs = 60000) { const t0 = Date.now(); while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`)) return true; } catch (e) { /* */ } await sleep(150); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}
const port = Number(process.argv[2]);
const outPath = process.argv[3];
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';

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

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');

// 收日志
const logs = [];
cdp.ws.addEventListener('message', (e) => {
  let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : String(e.data)); } catch { return; }
  if (m.method !== 'Runtime.consoleAPICalled') return;
  const args = (m.params && m.params.args) || [];
  const txt = args.map(a => a.value === undefined ? (a.description || '') : String(a.value)).join(' ');
  if (/lazy/i.test(txt)) logs.push({ t: Date.now(), txt });
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

// 探针：50ms 采样视口占位 + 帧间隔
await cdp.ev(`(function(){
  if (window.__bw) return 1;
  var W = { on:false, samples:[], maxBlank:0, frameGaps:[], lastFrame:0 };
  window.__bw = W;
  W.pane = function(){ return document.getElementById('preview-pane'); };
  W.viewportPh = function(){
    var p = W.pane(); if (!p) return -1;
    var pr = p.getBoundingClientRect(); var n = 0;
    p.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) n++;
    });
    return n;
  };
  W.firstLine = function(){
    var p = W.pane(); if(!p) return null;
    var pr = p.getBoundingClientRect();
    var els = p.querySelectorAll('[data--src-line]');
    for (var i=0;i<els.length;i++){ var r=els[i].getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) return +els[i].getAttribute('data--src-line'); }
    return null;
  };
  W.start = function(){
    W.on = true; W.samples = []; W.maxBlank = 0; W.frameGaps = []; W.frames = []; W.lastFrame = performance.now();
    W.t0 = performance.now();
    // 帧采样（同时记 mjx / ph 增量，用于归因长帧）
    (function fr(){
      if (!W.on) return;
      var n = performance.now();
      var pv = document.getElementById('preview');
      var cc = pv ? (pv.querySelector('.-preview-content') || pv) : null;
      W.frames.push({
        gap: +(n - W.lastFrame).toFixed(1),
        mjx: pv ? pv.querySelectorAll('mjx-container').length : -1,
        ph: cc ? cc.querySelectorAll('.-pv-placeholder').length : -1,
        vph: W.viewportPh()
      });
      W.frameGaps.push(n - W.lastFrame); W.lastFrame = n;
      requestAnimationFrame(fr);
    })();
    // 50ms 采样视口占位
    var blankStart = null;
    (function poll(){
      if (!W.on) return;
      var now = performance.now();
      var ph = W.viewportPh();
      W.samples.push({ t: Math.round(now - W.t0), ph: ph, line: W.firstLine() });
      if (ph > 0) { if (blankStart === null) blankStart = now; }
      else if (blankStart !== null) { var d = now - blankStart; if (d > W.maxBlank) W.maxBlank = d; blankStart = null; }
      setTimeout(poll, 50);
    })();
  };
  W.stop = function(){
    W.on = false;
    var g = W.frameGaps.filter(function(x){ return isFinite(x) && x > 0; }).sort(function(a,b){ return a-b; });
    var n = g.length;
    var blankRun = 0, cur = 0;
    W.samples.forEach(function(s){ if (s.ph > 0) { cur++; if (cur > blankRun) blankRun = cur; } else cur = 0; });
    // ★ 找"最终卡住段"：最后一个连续 ph>0 的区间
    var tailStart = -1;
    for (var i = W.samples.length - 1; i >= 0; i--) {
      if (W.samples[i].ph > 0) tailStart = i; else break;
    }
    var tail = tailStart >= 0 ? W.samples.slice(tailStart) : [];
    return {
      maxBlankMs: Math.round(W.maxBlank),
      blankSamples: W.samples.filter(function(s){return s.ph>0;}).length,
      totalSamples: W.samples.length,
      longestBlankRunSamples: blankRun,
      longestBlankRunMs: blankRun * 50,
      tailStall: tail.length ? { fromT: tail[0].t, toT: tail[tail.length-1].t, durationMs: tail[tail.length-1].t - tail[0].t, line: tail[0].line, ph: tail[0].ph, samples: tail.length } : null,
      frame: { count: n, max: n ? +g[n-1].toFixed(1) : null, p95: n ? +g[Math.floor(n*0.95)].toFixed(1) : null,
               over100: g.filter(function(x){return x>100;}).length, over500: g.filter(function(x){return x>500;}).length },
      frames: (W.frames || []).slice(0, 600),
      samples: W.samples.slice(0, 400)
    };
  };
  return 1;
})()`);

// ★ 排队顺序诊断：包装 _materializeRange，记录每次物化的块下标区间
//   目的：证明/推翻"视口块排在最后"假设
await cdp.ev(`(function(){
  if (window.__mq) return 1;
  var Q = { calls: [] };
  window.__mq = Q;
  // 通过 MutationObserver 观察占位块被真块替换的顺序（不改产品代码，纯旁路观测）
  Q.observe = function(){
    Q.calls = []; Q.t0 = performance.now();
    var cc = document.querySelector('#preview .-preview-content') || document.getElementById('preview');
    if (!cc) return 'no-cc';
    Q.mo = new MutationObserver(function(muts){
      var now = Math.round(performance.now() - Q.t0);
      muts.forEach(function(m){
        // 占位块被移除（= 物化发生）
        var removed = [], added = [];
        for (var i = 0; i < m.removedNodes.length; i++) {
          var n = m.removedNodes[i];
          if (n.nodeType === 1 && n.classList && n.classList.contains('-pv-placeholder')) removed.push(n.getAttribute('data--block-index'));
        }
        for (var j = 0; j < m.addedNodes.length; j++) {
          var a = m.addedNodes[j];
          if (a.nodeType === 1 && a.classList && a.classList.contains('-src-block')) added.push(a.getAttribute('data--block-index'));
        }
        if (removed.length || added.length) Q.calls.push({ t: now, removed: removed.slice(0, 12), added: added.slice(0, 12), nRemoved: removed.length, nAdded: added.length });
      });
    });
    Q.mo.observe(cc, { childList: true, subtree: true });
    return 'observing';
  };
  Q.stop = function(){
    if (Q.mo) { Q.mo.disconnect(); Q.mo = null; }
    return { callCount: Q.calls.length, calls: Q.calls.slice(0, 300) };
  };
  return 1;
})()`);

// ★ flush 调度延迟诊断（Lead ① 的核心）
//   手法：包装 window.requestIdleCallback / setTimeout，记录"调度时刻 → 实际执行时刻"的延迟。
//   `_lazyScheduleFlush` 用的正是 requestIdleCallback（或 setTimeout 兜底）⇒ 直接量到 flush 被饿死的程度。
//   纯旁路：只包装、不改语义、执行前后各打一个时间戳。
await cdp.ev(`(function(){
  if (window.__sd) return 1;
  var D = { rics: [], touts: [] };
  window.__sd = D;
  D.t0 = performance.now();
  var origRIC = window.requestIdleCallback;
  if (typeof origRIC === 'function') {
    window.requestIdleCallback = function(cb, opts){
      var sched = performance.now();
      var wrapped = function(deadline){
        var ran = performance.now();
        D.rics.push({ sched: +(sched - D.t0).toFixed(1), ran: +(ran - D.t0).toFixed(1), delay: +(ran - sched).toFixed(1),
                      didTimeout: !!(deadline && deadline.didTimeout),
                      timeRemaining: deadline && deadline.timeRemaining ? +deadline.timeRemaining().toFixed(1) : null });
        return cb.apply(this, arguments);
      };
      return origRIC.call(window, wrapped, opts);
    };
  }
  var origST = window.setTimeout;
  window.setTimeout = function(fn, delay){
    // 只跟踪 0-100ms 的短定时器（flush 调度用 setTimeout(0) / 120ms 窗口）
    if (typeof fn === 'function' && delay !== undefined && delay <= 200) {
      var sched = performance.now();
      var wrapped = function(){
        var ran = performance.now();
        D.touts.push({ sched: +(sched - D.t0).toFixed(1), ran: +(ran - D.t0).toFixed(1), delay: +(ran - sched).toFixed(1), reqDelay: delay });
        return fn.apply(this, arguments);
      };
      return origST.call(window, wrapped, delay);
    }
    return origST.apply(window, arguments);
  };
  D.stop = function(){
    var r = D.rics.slice().sort(function(a,b){ return b.delay - a.delay; });
    var t = D.touts.slice().sort(function(a,b){ return b.delay - a.delay; });
    function stats(arr){ if(!arr.length) return null; var ds = arr.map(function(x){return x.delay;}).sort(function(a,b){return a-b;});
      return { n: ds.length, max: +ds[ds.length-1].toFixed(1), p95: +ds[Math.floor(ds.length*0.95)].toFixed(1),
               median: +ds[Math.floor(ds.length/2)].toFixed(1),
               over100: ds.filter(function(x){return x>100;}).length,
               over500: ds.filter(function(x){return x>500;}).length }; }
    return { ricc: stats(r), toutc: stats(t), ricTop: r.slice(0,10), toutTop: t.slice(0,10) };
  };
  return 1;
})()`);

// 打开文档
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
// 等首屏稳定
for (let k = 0; k < 100; k++) { await sleep(200); const ph = await cdp.ev('window.__bw.viewportPh()'); if (ph === 0) break; }
await sleep(1200);

const before = { ph: await cdp.ev('window.__bw.viewportPh()'), line: await cdp.ev('window.__bw.firstLine()') };
console.log('=== 拖拽前 ===');
console.log('  视口占位=' + before.ph + ' 首行=' + before.line);

// ⭐ 快速拖到 80%（10 帧扫）
logs.length = 0;
await cdp.ev('window.__bw.start()');
const moState = await cdp.ev('window.__mq.observe()');
console.log('  排队观测: ' + moState);
const t0 = Date.now();
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}
// 让物化完成
await sleep(6000);
const res = await cdp.ev('window.__bw.stop()');
const mqRes = await cdp.ev('window.__mq.stop()');
const sdRes = await cdp.ev('window.__sd.stop()');
const elapsed = Date.now() - t0;
const after = { ph: await cdp.ev('window.__bw.viewportPh()'), line: await cdp.ev('window.__bw.firstLine()') };

const cappedLogs = logs.filter(l => /flush batch capped/.test(l.txt));
const matLogs = logs.filter(l => /materializ/i.test(l.txt));

console.log('');
console.log('=== 拖到 80% 后 ===');
console.log('  视口占位=' + after.ph + ' 首行=' + after.line);
console.log('');
console.log('★★★ 视口空白持续时长: ' + res.maxBlankMs + 'ms' + (res.maxBlankMs > 100 ? '  ❌ 超100ms门槛' : '  ✅ ≤100ms'));
console.log('    空白采样数: ' + res.blankSamples + '/' + res.totalSamples);
console.log('    最长连续空白: ' + res.longestBlankRunSamples + ' 个采样 = ' + res.longestBlankRunMs + 'ms');
console.log('');
console.log('=== 帧间隔 ===');
console.log('  ' + JSON.stringify(res.frame));
console.log('');
console.log('=== lazy 日志 ===');
console.log('  capped: ' + cappedLogs.length + ' 次');
cappedLogs.slice(0, 8).forEach(l => console.log('    made=' + (l.txt.match(/made=(\d+)/) || [])[1] + ' overflow=' + (l.txt.match(/overflow=(\d+)/) || [])[1]));
console.log('');
console.log('=== 空白期间采样序列（前 40 个）===');
res.samples.slice(0, 40).forEach(s => {
  if (s.ph > 0) console.log('    t=' + s.t + 'ms  ph=' + s.ph + '  line=' + s.line);
});

// ★ 最终卡住段
console.log('');
console.log('=== 最终卡住段（滚动已停但块未物化）===');
if (res.tailStall) {
  const ts = res.tailStall;
  console.log('  从 t=' + ts.fromT + 'ms 到 t=' + ts.toT + 'ms，持续 ' + ts.durationMs + 'ms');
  console.log('  卡在 line=' + ts.line + '，残留 ' + ts.ph + ' 个占位块，共 ' + ts.samples + ' 次采样');
} else {
  console.log('  （无——结束时视口无占位）');
}

// ★ 排队顺序（Lead ①）
console.log('');
console.log('=== 排队顺序诊断（MutationObserver 记录物化顺序）===');
console.log('  物化批次回调数: ' + (mqRes ? mqRes.callCount : 0));
if (mqRes && mqRes.calls) {
  const first8 = mqRes.calls.slice(0, 8);
  first8.forEach(c => console.log('    t=' + c.t + 'ms  移除' + c.nRemoved + '块  新增' + c.nAdded + '块  下标=' + JSON.stringify(c.removed)));
  const totalRemoved = mqRes.calls.reduce((s, c) => s + (c.nRemoved || 0), 0);
  console.log('  累计物化块数: ' + totalRemoved);
}

// ★ 长帧归因（Lead ③）
console.log('');
console.log('=== 长帧归因（gap>100ms，看是否物化+排版同帧叠加）===');
const frames = res.frames || [];
const longFrames = [];
for (let i = 1; i < frames.length; i++) {
  if (frames[i].gap > 100) {
    longFrames.push({
      idx: i, gap: frames[i].gap,
      mjxDelta: frames[i].mjx - frames[i - 1].mjx,
      phDelta: frames[i - 1].ph - frames[i].ph,
      vph: frames[i].vph,
    });
  }
}
longFrames.forEach(f => {
  const both = (f.mjxDelta > 0 && f.phDelta > 0) ? ' ★同帧叠加' : '';
  console.log('  gap=' + f.gap + 'ms  mjx+' + f.mjxDelta + '  ph-' + f.phDelta + '  视口占位=' + f.vph + both);
});
if (!longFrames.length) console.log('  （无 >100ms 帧）');

// ★ 空白脉冲拆分（Lead ②）
console.log('');
console.log('=== 空白脉冲拆分 ===');
const smp = res.samples || [];
const pulses = [];
let cur = null;
for (const s of smp) {
  if (s.ph > 0) { if (!cur) cur = { fromT: s.t, toT: s.t, maxPh: s.ph, lineFrom: s.line, lineTo: s.line, n: 1 }; else { cur.toT = s.t; cur.maxPh = Math.max(cur.maxPh, s.ph); cur.lineTo = s.line; cur.n++; } }
  else if (cur) { pulses.push(cur); cur = null; }
}
if (cur) pulses.push(cur);
pulses.forEach((p, i) => {
  console.log('  脉冲' + (i + 1) + ': t=' + p.fromT + '–' + p.toT + 'ms (' + (p.toT - p.fromT) + 'ms) ' +
    'ph最高=' + p.maxPh + ' line ' + p.lineFrom + '→' + p.lineTo + ' 采样' + p.n + '次');
});
if (!pulses.length) console.log('  （无空白脉冲）');

// ★ flush 调度延迟
console.log('');
console.log('=== ⭐ flush 调度延迟（requestIdleCallback 调度→执行）===');
if (sdRes && sdRes.ricc) {
  const r = sdRes.ricc;
  console.log('  ★ requestIdleCallback: n=' + r.n + '  max=' + r.max + 'ms  p95=' + r.p95 + 'ms  median=' + r.median + 'ms');
  console.log('    延迟 >100ms: ' + r.over100 + ' 次   延迟 >500ms: ' + r.over500 + ' 次');
  console.log('  最慢 10 次:');
  (sdRes.ricTop || []).forEach(x => console.log('    调度@' + x.sched + 'ms → 执行@' + x.ran + 'ms  延迟=' + x.delay + 'ms  didTimeout=' + x.didTimeout));
} else {
  console.log('  （无 requestIdleCallback 记录）');
}
if (sdRes && sdRes.toutc) {
  const t = sdRes.toutc;
  console.log('  setTimeout(≤200ms): n=' + t.n + '  max=' + t.max + 'ms  p95=' + t.p95 + 'ms  median=' + t.median + 'ms  >100ms:' + t.over100);
}

const out = {
  head: '7fed5877', doc: DOC, mode: 'drag-to-80%-blank-baseline',
  before, after, elapsedMs: elapsed,
  blank: {
    maxBlankMs: res.maxBlankMs,
    blankSamples: res.blankSamples,
    totalSamples: res.totalSamples,
    longestBlankRunSamples: res.longestBlankRunSamples,
    longestBlankRunMs: res.longestBlankRunMs,
  },
  frame: res.frame,
  tailStall: res.tailStall,
  mutationOrder: mqRes ? { callCount: mqRes.callCount, calls: mqRes.calls.slice(0, 100) } : null,
  scheduleDelay: sdRes,
  cappedCount: cappedLogs.length,
  cappedSamples: cappedLogs.slice(0, 10).map(l => l.txt),
  samples: res.samples,
  concurrency: concurrency(),
};
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__BLANK__' + JSON.stringify({
  maxBlankMs: res.maxBlankMs,
  longestBlankRunMs: res.longestBlankRunMs,
  maxFrame: res.frame.max,
  capped: cappedLogs.length,
  afterPh: after.ph,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
