/**
 * task-63 0.4.7 验收：统一调度循环效果
 *
 * 一次跑完三项（Lead 指定判据）：
 *   1. 4 位置源码态最长连续时长（目标全 ≤200ms）
 *   2. 批次间隔分布（目标 ≤60ms）
 *   3. 单帧 max（目标 ≤200ms，不能回到 478ms）
 *
 * 用法: node perf_unified_verify.mjs <port> <outdir>
 */
import { writeFileSync, mkdirSync } from 'node:fs';
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
const outdir = process.argv[3] || 'artifacts/agent/verify/unified';
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';
mkdirSync(outdir, { recursive: true });

const POSITIONS = [0.3, 0.5, 0.7, 0.9];

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');

const logs = [];
cdp.ws.addEventListener('message', (e) => {
  let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : String(e.data)); } catch { return; }
  if (m.method !== 'Runtime.consoleAPICalled') return;
  const args = (m.params && m.params.args) || [];
  const txt = args.map(a => a.value === undefined ? (a.description || '') : String(a.value)).join(' ');
  if (/typeset|math merge|DEFERRED|materializ|flush|rAF|unified/i.test(txt)) logs.push({ t: Date.now(), txt });
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// 打点探针：包装 typesetPromise（记录每次调用）+ 帧间隔 + 源码态
await cdp.ev(`(function(){
  if (window.__uv) return 1;
  var U = {}; window.__uv = U;

  U.wrapTypeset = function(){
    var MJ = window.MathJax;
    if (!MJ || typeof MJ.typesetPromise !== 'function') return 'no-mj';
    if (MJ.__uvWrapped) return 'already';
    var orig = MJ.typesetPromise.bind(MJ);
    MJ.typesetPromise = function(items){
      var start = performance.now();
      var n = 0;
      try { if (items && items.length) { for (var i=0;i<items.length;i++){ var el=items[i]; if (el && el.querySelectorAll) n += el.querySelectorAll('[data--block-index]').length || 1; else n += 1; } } } catch(e){}
      var rec = { tStart: +start.toFixed(1), n: n, tEnd: null };
      if (!U.ts) U.ts = [];
      U.ts.push(rec);
      var pr = orig(items);
      if (pr && pr.then) { pr.then(function(){ rec.tEnd = +performance.now().toFixed(1); }, function(){ rec.tEnd = +performance.now().toFixed(1); rec.err=1; }); }
      else rec.tEnd = rec.tStart;
      return pr;
    };
    MJ.__uvWrapped = true;
    return 'wrapped';
  };

  U.pane = function(){ return document.getElementById('preview-pane'); };
  U.sample = function(){
    var p = U.pane(); if (!p) return null;
    var pr = p.getBoundingClientRect();
    var paneArea = p.clientHeight > 0 ? p.clientHeight : 1;
    var mjx = 0, ph = 0, rawArea = 0, rawCount = 0;
    p.querySelectorAll('mjx-container').forEach(function(e){ var r=e.getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) mjx++; });
    p.querySelectorAll('.-pv-placeholder').forEach(function(e){ var r=e.getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) ph++; });
    var walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null); var node;
    while ((node = walker.nextNode())) {
      var t = node.nodeValue || '';
      if (t.indexOf('$') < 0) continue;
      var par = node.parentElement; if (!par) continue;
      if (par.closest('mjx-container') || par.closest('pre') || par.closest('code') || par.closest('.-pv-placeholder')) continue;
      var r = par.getBoundingClientRect();
      var vis = Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top);
      if (vis > 2) { rawCount++; rawArea += vis; }
    }
    return { mjx: mjx, ph: ph, rawCount: rawCount, rawArea: +(Math.min(1, rawArea/paneArea)).toFixed(3) };
  };

  U.start = function(){
    U.on = true; U.t0 = performance.now(); U.series = []; U.gaps = []; U.lastFrame = performance.now();
    (function fr(){
      if (!U.on) return;
      var n = performance.now();
      U.gaps.push(+(n - U.lastFrame).toFixed(1)); U.lastFrame = n;
      var s = U.sample();
      if (s) { s.t = +(n - U.t0).toFixed(0); U.series.push(s); }
      requestAnimationFrame(fr);
    })();
  };
  U.stop = function(){
    U.on = false;
    var g = (U.gaps||[]).filter(function(x){ return isFinite(x)&&x>0; }).sort(function(a,b){return a-b;});
    var n = g.length;
    return { series: U.series, frame: { n: n, max: n?+g[n-1].toFixed(1):null, p95: n?+g[Math.floor(n*0.95)].toFixed(1):null,
             over100: g.filter(function(x){return x>100;}).length, over200: g.filter(function(x){return x>200;}).length } };
  };
  U.resetTs = function(){ U.ts = []; };
  U.getTs = function(){ return U.ts || []; };
  return 1;
})()`);

const wrapRes = await cdp.ev('window.__uv.wrapTypeset()');
console.log('  typeset 包装: ' + wrapRes);

// 打开 + 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
for (let k = 0; k < 150; k++) { await sleep(150); const ph = await cdp.ev(`(function(){var p=document.getElementById('preview-pane');if(!p)return -1;var pr=p.getBoundingClientRect();var n=0;p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect();if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;});return n;})()`); if (ph === 0) break; }
await sleep(1200);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
await sleep(2500);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
await sleep(2000);

const results = [];
let allTs = [];
let globalFrame = [];

for (const target of POSITIONS) {
  // 每轮重置到顶部（保证目标位置未物化）
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
  await sleep(1500);
  await cdp.ev('window.__uv.resetTs()');
  await cdp.ev('window.__uv.start()');
  for (let s = 1; s <= 10; s++) {
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(target * s / 10).toFixed(3)}; return 1; })()`);
    await sleep(16);
  }
  await sleep(5000);
  const r = await cdp.ev('window.__uv.stop()');
  const ts = await cdp.ev('window.__uv.getTs()');

  const s = r.series || [];
  // 最长连续源码态
  let runStart = null, maxRun = 0;
  s.forEach(x => {
    if (x.rawCount > 0) { if (runStart === null) runStart = x.t; }
    else { if (runStart !== null) { const d = x.t - runStart; if (d > maxRun) maxRun = d; runStart = null; } }
  });
  if (runStart !== null) { const d = s[s.length-1].t - runStart; if (d > maxRun) maxRun = d; }

  const withRaw = s.filter(x => x.rawCount > 0).length;
  const peakArea = s.length ? Math.max(...s.map(x => x.rawArea)) : 0;

  // 批次间隔
  const valid = (ts || []).filter(t => t.tEnd != null).sort((a,b)=>a.tStart-b.tStart);
  const intervals = [];
  for (let i = 1; i < valid.length; i++) intervals.push(+(valid[i].tStart - valid[i-1].tEnd).toFixed(1));
  const iv = intervals.slice().sort((a,b)=>a-b);
  const ivStats = iv.length ? { n: iv.length, median: iv[Math.floor(iv.length/2)], p95: iv[Math.min(iv.length-1,Math.floor(iv.length*0.95))], max: iv[iv.length-1] } : null;

  results.push({ target, maxRawRunMs: maxRun, withRawFrames: withRaw, totalFrames: s.length, peakRawArea: peakArea,
    typesetBatches: valid.length, batchIntervals: ivStats, frame: r.frame,
    _intervals: intervals, _ts: valid });
  allTs = allTs.concat(valid);
  globalFrame = globalFrame.concat(r.gaps || []);

  console.log('位置 ' + (target*100) + '%: 源码态最长=' + maxRun + 'ms  有源码帧=' + withRaw + '/' + s.length +
    '  峰值面积=' + (peakArea*100).toFixed(0) + '%  typeset批数=' + valid.length +
    '  批间隔(med/p95/max)=' + (ivStats ? ivStats.median + '/' + ivStats.p95 + '/' + ivStats.max : '-') +
    '  帧max=' + (r.frame.max) + 'ms over200=' + r.frame.over200);
  await sleep(1000);
}

// 汇总
const runs = results.map(r => r.maxRawRunMs);
const allIntervals = results.flatMap(r => r._intervals).sort((a,b)=>a-b);
const allFrames = globalFrame.filter(x => isFinite(x) && x > 0).sort((a,b)=>a-b);
const frameMax = allFrames.length ? allFrames[allFrames.length-1] : null;
const frameP95 = allFrames.length ? allFrames[Math.floor(allFrames.length*0.95)] : null;

console.log('');
console.log('=== 汇总（Lead 三项判据）===');
console.log('  ① 4 位置源码态最长连续: ' + JSON.stringify(runs));
console.log('     最大 = ' + Math.max(...runs) + 'ms  ' + (Math.max(...runs) <= 200 ? '✅ ≤200ms' : '❌ >200ms'));
console.log('  ② 批次间隔分布: n=' + allIntervals.length +
  (allIntervals.length ? '  median=' + allIntervals[Math.floor(allIntervals.length/2)] +
   'ms  p95=' + allIntervals[Math.min(allIntervals.length-1,Math.floor(allIntervals.length*0.95))] +
   'ms  max=' + allIntervals[allIntervals.length-1] + 'ms  ' +
   (allIntervals[Math.floor(allIntervals.length/2)] <= 60 ? '✅ ≤60ms' : '❌ >60ms') : ''));
console.log('  ③ 单帧: max=' + frameMax + 'ms  p95=' + frameP95 + 'ms  ' +
  (frameMax != null && frameMax <= 200 ? '✅ ≤200ms' : '❌ >200ms'));

const out = { head: 'pending', doc: DOC, positions: POSITIONS, results,
  summary: { rawRuns: runs, rawRunMax: Math.max(...runs),
    batchIntervals: allIntervals.length ? { n: allIntervals.length,
      median: allIntervals[Math.floor(allIntervals.length/2)],
      p95: allIntervals[Math.min(allIntervals.length-1,Math.floor(allIntervals.length*0.95))],
      max: allIntervals[allIntervals.length-1] } : null,
    frame: { max: frameMax, p95: frameP95 } } };
writeFileSync(outdir + '/unified-verify.json', JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__UNIFIED__' + JSON.stringify(out.summary));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
