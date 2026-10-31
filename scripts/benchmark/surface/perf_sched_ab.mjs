/**
 * task-63 最后一个实验：Scheduler 迁移 A/B
 *
 * A 组：MemoriaScheduler 正常（bypass 关）
 * B 组：window.__BENCH_DISABLE_SCHEDULER = true（作业同步立即执行 = 无调度器）
 *
 * 每组 3 次，每次：重开文档 → 预热(拖40%回顶) → 拖到 50%
 * 报：最长连续源码态 / 面积>10%连续 / 有源码帧 / 单帧 max
 *
 * 用法: node perf_sched_ab.mjs <port> <out.json>
 */
import { writeFileSync } from 'node:fs';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 120000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, userGesture: true }); if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || '')); return r.result ? r.result.value : undefined; }
  async waitFor(expr, timeoutMs = 60000) { const t0 = Date.now(); while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`)) return true; } catch (e) { /* */ } await sleep(150); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}
const port = Number(process.argv[2]);
const outPath = process.argv[3];
const TARGET = Number(process.argv[4] || 0.5);
const DOC = process.argv[5] || '教材/08_第8章_差错控制编码.md';

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// 探针：源码态 + 帧间隔，纯页面内 rAF（最少干扰）
await cdp.ev(`(function(){
  if (window.__ab2) return 1;
  var A = {}; window.__ab2 = A;
  A.pane = function(){ return document.getElementById('preview-pane'); };
  A.sample = function(){
    var p = A.pane(); if (!p) return null;
    var pr = p.getBoundingClientRect();
    var paneArea = p.clientHeight > 0 ? p.clientHeight : 1;
    var rawArea = 0, rawCount = 0, ph = 0;
    // 占位块
    p.querySelectorAll('.-pv-placeholder').forEach(function(e){ var r=e.getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) ph++; });
    // 未排版公式源码
    var walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null, false); var node;
    while ((node = walker.nextNode())) {
      var t = node.nodeValue || '';
      if (t.indexOf('$') < 0) continue;
      var par = node.parentElement; if (!par) continue;
      if (par.closest('mjx-container') || par.closest('pre') || par.closest('code') || par.closest('.-pv-placeholder')) continue;
      var r = par.getBoundingClientRect();
      var vis = Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top);
      if (vis > 2) { rawCount++; rawArea += vis; }
    }
    return { ph: ph, rawCount: rawCount, rawArea: +(Math.min(1, rawArea/paneArea)).toFixed(3) };
  };
  A.start = function(){
    A.on = true; A.t0 = performance.now(); A.series = []; A.gaps = []; A.lastFrame = performance.now();
    (function tick(){
      if (!A.on) return;
      var n = performance.now();
      A.gaps.push(+(n - A.lastFrame).toFixed(1)); A.lastFrame = n;
      var s = A.sample();
      if (s) { s.t = +(n - A.t0).toFixed(0); A.series.push(s); }
      requestAnimationFrame(tick);
    })();
  };
  A.stop = function(){
    A.on = false;
    var g = (A.gaps||[]).filter(function(x){ return isFinite(x)&&x>0; }).sort(function(a,b){return a-b;});
    var n = g.length;
    return { series: A.series, frame: { max: n?+g[n-1].toFixed(1):null, over100: g.filter(function(x){return x>100;}).length, over200: g.filter(function(x){return x>200;}).length } };
  };
  A.setBypass = function(on){ window.__BENCH_DISABLE_SCHEDULER = !!on; return !!window.__BENCH_DISABLE_SCHEDULER; };
  A.isBypass = function(){ try { return window.MemoriaScheduler && window.MemoriaScheduler.isBypass ? window.MemoriaScheduler.isBypass() : null; } catch(e){ return null; } };
  return 1;
})()`);

async function measureOnce(bypass) {
  const actual = await cdp.ev(`window.__ab2.setBypass(${bypass})`);
  const isB = await cdp.ev(`window.__ab2.isBypass()`);
  // 重开文档
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
  for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
  for (let k = 0; k < 150; k++) { await sleep(150); const ph = await cdp.ev(`(function(){var p=document.getElementById('preview-pane');if(!p)return -1;var pr=p.getBoundingClientRect();var n=0;p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect();if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;});return n;})()`); if (ph === 0) break; }
  await sleep(1200);
  // 预热
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
  await sleep(2500);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
  await sleep(2000);

  await cdp.ev('window.__ab2.start()');
  for (let s = 1; s <= 10; s++) {
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(TARGET * s / 10).toFixed(3)}; return 1; })()`);
    await sleep(16);
  }
  await sleep(5000);
  const r = await cdp.ev('window.__ab2.stop()');
  const s = r.series || [];

  let runStart = null, maxRun = 0, aStart = null, maxAreaRun = 0;
  s.forEach(x => {
    if (x.rawCount > 0) { if (runStart === null) runStart = x.t; }
    else { if (runStart !== null) { const d = x.t - runStart; if (d > maxRun) maxRun = d; runStart = null; } }
    if (x.rawArea > 0.1) { if (aStart === null) aStart = x.t; }
    else { if (aStart !== null) { const d = x.t - aStart; if (d > maxAreaRun) maxAreaRun = d; aStart = null; } }
  });
  if (runStart !== null) { const d = s[s.length-1].t - runStart; if (d > maxRun) maxRun = d; }
  if (aStart !== null) { const d = s[s.length-1].t - aStart; if (d > maxAreaRun) maxAreaRun = d; }

  return { bypassRequested: bypass, bypassActual: isB, maxRunMs: maxRun, maxArea10RunMs: maxAreaRun,
    withRawFrames: s.filter(x => x.rawCount > 0).length, totalFrames: s.length,
    peakArea: s.length ? Math.max(...s.map(x => x.rawArea)) : 0,
    frame: r.frame };
}

const results = { A: [], B: [] };
for (let i = 1; i <= 3; i++) {
  const a = await measureOnce(false);
  results.A.push(a);
  console.log('A' + i + ' (bypass=' + a.bypassActual + '): 最长=' + a.maxRunMs + 'ms  面积>10%连续=' + a.maxArea10RunMs +
    'ms  有源码帧=' + a.withRawFrames + '/' + a.totalFrames + '  峰值面积=' + (a.peakArea*100).toFixed(0) +
    '%  帧max=' + (a.frame.max) + 'ms');
  await sleep(800);
}
for (let i = 1; i <= 3; i++) {
  const b = await measureOnce(true);
  results.B.push(b);
  console.log('B' + i + ' (bypass=' + b.bypassActual + '): 最长=' + b.maxRunMs + 'ms  面积>10%连续=' + b.maxArea10RunMs +
    'ms  有源码帧=' + b.withRawFrames + '/' + b.totalFrames + '  峰值面积=' + (b.peakArea*100).toFixed(0) +
    '%  帧max=' + (b.frame.max) + 'ms');
  await sleep(800);
}

function med(arr) { const s = arr.slice().sort((a,b)=>a-b); return s[Math.floor(s.length/2)]; }
const A = results.A, B = results.B;
const aRuns = A.map(x => x.maxRunMs), bRuns = B.map(x => x.maxRunMs);
const aAreas = A.map(x => x.maxArea10RunMs), bAreas = B.map(x => x.maxArea10RunMs);

console.log('');
console.log('=== A/B 汇总 ===');
console.log('  A（调度器）最长连续: ' + JSON.stringify(aRuns) + '  中位=' + med(aRuns) + 'ms');
console.log('  B（bypass）最长连续: ' + JSON.stringify(bRuns) + '  中位=' + med(bRuns) + 'ms');
console.log('  ★ A（调度器）面积>10%连续: ' + JSON.stringify(aAreas) + '  中位=' + med(aAreas) + 'ms');
console.log('  ★ B（bypass）面积>10%连续: ' + JSON.stringify(bAreas) + '  中位=' + med(bAreas) + 'ms');
console.log('  A 有源码帧: ' + JSON.stringify(A.map(x=>x.withRawFrames)) + '   B: ' + JSON.stringify(B.map(x=>x.withRawFrames)));
console.log('  A 帧max: ' + JSON.stringify(A.map(x=>x.frame.max)) + '   B: ' + JSON.stringify(B.map(x=>x.frame.max)));

const dRun = (med(aRuns) - med(bRuns)) / Math.max(1, med(bRuns)) * 100;
const dArea = (med(aAreas) - med(bAreas)) / Math.max(1, med(bAreas)) * 100;
console.log('');
console.log('  差异（A vs B，负数=调度器更好）: 最长连续 ' + dRun.toFixed(1) + '%   面积连续 ' + dArea.toFixed(1) + '%');

const out = { head: '4e401d8c', doc: DOC, target: TARGET, A, B,
  summary: { aRuns, bRuns, aRunsMed: med(aRuns), bRunsMed: med(bRuns),
             aAreas, bAreas, aAreasMed: med(aAreas), bAreasMed: med(bAreas),
             deltaRunsPct: +dRun.toFixed(1), deltaAreasPct: +dArea.toFixed(1) } };
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__AB__' + JSON.stringify(out.summary));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
