/**
 * task-63：08 章打开路径分段明细（不改源码，运行时包装关键函数计时）
 *
 * 覆盖 Lead 列出的 6 段：
 *   parse / renderDocument / appendChild(含首次布局) / highlight / stampBlockLines / 全篇 querySelectorAll
 * 另加：renderPreview 整体、typeset 批次、mermaid
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
    try { return r.result ? JSON.parse(r.result.value) : null; } catch (e) { return { _parseErr: true }; }
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2]);
const outPath = process.argv[3];
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';
const ROUNDS = Number(process.argv[5] || 4);
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

await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// ── 安装分段计时探针 ──
const inst = await cdp.ev(`(function(){
  if (window.__seg) return { already: true };
  var S = { acc: {}, on: false, log: [] };
  window.__seg = S;
  S.reset = function(){ S.acc = {}; S.log = []; };
  // 注意：不用 S.on 做门控 —— 一旦 reset 就记录，避免 renderPreview 结束后
  // 的异步 typeset 批次被丢弃（v1 的教训：原实现在 renderPreview resolve 后立即
  // 置 on=false，结果异步链路的 typeset 全被漏掉）
  S.add = function(k, ms){
    if (!S.acc[k]) S.acc[k] = { n: 0, total: 0, max: 0, list: [] };
    var a = S.acc[k]; a.n++; a.total += ms; if (ms > a.max) a.max = ms;
    if (a.list.length < 60) a.list.push(+ms.toFixed(1));
  };
  S.snapshot = function(){ return S.acc; };

  // 包 P.parse
  if (window.MemoriaParser && typeof window.MemoriaParser.parse === 'function') {
    var op = window.MemoriaParser.parse;
    window.MemoriaParser.parse = function(){ var t=performance.now(); var r=op.apply(this,arguments); S.add('parse', performance.now()-t); return r; };
  }
  // 包 render-core 实例方法：通过 createRenderCore 工厂
  if (window.MemoriaRenderCore && typeof window.MemoriaRenderCore.createRenderCore === 'function' && !window.MemoriaRenderCore.__segWrapped) {
    var oc = window.MemoriaRenderCore.createRenderCore;
    window.MemoriaRenderCore.createRenderCore = function(){
      var inst = oc.apply(this, arguments);
      ['renderDocument','renderBlock','renderRange'].forEach(function(m){
        if (inst && typeof inst[m] === 'function' && !inst[m].__seg) {
          var o = inst[m];
          var w = function(){ var t=performance.now(); var r=o.apply(this,arguments); S.add(m, performance.now()-t); return r; };
          w.__seg = true;
          try { inst[m] = w; } catch(e){}
        }
      });
      return inst;
    };
    window.MemoriaRenderCore.__segWrapped = true;
  }
  // 包 MathJax.typesetPromise
  if (window.MathJax && typeof window.MathJax.typesetPromise === 'function' && !window.MathJax.__segWrapped) {
    var ot = window.MathJax.typesetPromise.bind(window.MathJax);
    window.MathJax.typesetPromise = function(items){
      var n = items && items.length || 0;
      var cnt = 0; try { if (items && items[0] && items[0].querySelectorAll) cnt = items[0].querySelectorAll('span.-math, .-math-block, mjx-container').length; } catch(e){}
      var t = performance.now();
      var pr = ot(items);
      S.add('typeset_call_sync', performance.now()-t);
      if (pr && pr.then) pr.then(function(){ S.add('typeset_call_async', performance.now()-t); }, function(){ S.add('typeset_call_async', performance.now()-t); });
      S.add('typeset_items=' + n, 0);
      return pr;
    };
    window.MathJax.__segWrapped = true;
  }
  // 包 stampBlockLines / _applyCodeHighlightToPreview（若暴露在 window）
  ['stampBlockLines','_applyCodeHighlightToPreview','postProcessWikilinks','bindPreviewLinks'].forEach(function(fn){
    if (typeof window[fn] === 'function' && !window[fn].__seg) {
      var o = window[fn];
      var w = function(){ var t=performance.now(); var r=o.apply(this,arguments); S.add(fn, performance.now()-t); return r; };
      w.__seg = true;
      window[fn] = w;
    }
  });
  return { ok: true, wrappedParse: !!(window.MemoriaParser && window.MemoriaParser.parse), wrappedTypeset: !!(window.MathJax && window.MathJax.typesetPromise) };
})()`);
console.log('分段探针: ' + JSON.stringify(inst));

// 包 renderPreview（app 暴露）
const rp = await cdp.ev(`(function(){
  if (!window.MemoriaApp || typeof window.MemoriaApp.renderPreview !== 'function') return { err: 'no renderPreview' };
  if (window.MemoriaApp.renderPreview.__seg) return { already: true };
  var o = window.MemoriaApp.renderPreview;
  var w = function(){
    var t = performance.now();
    var r = o.apply(this, arguments);
    var dt = performance.now() - t;
    window.__seg.add('renderPreview_sync', dt);
    if (r && r.then) { r.then(function(){ window.__seg.add('renderPreview_async', performance.now()-t); }, function(){ window.__seg.add('renderPreview_async', performance.now()-t); }); }
    return r;
  };
  w.__seg = true;
  window.MemoriaApp.renderPreview = w;
  return { ok: true };
})()`);
console.log('renderPreview 包装: ' + JSON.stringify(rp));

// longtask 观测
await cdp.ev(`(function(){
  window.__lt = [];
  try {
    var po = new PerformanceObserver(function(list){
      list.getEntries().forEach(function(e){ window.__lt.push({ start: +e.startTime.toFixed(1), dur: +e.duration.toFixed(1) }); });
    });
    po.observe({ entryTypes: ['longtask'] });
    window.__ltPO = po;
  } catch(e) { window.__ltErr = String(e && e.message); }
  return 1;
})()`);

const results = {
  schema: 'memoria-perf-segments/v1',
  startedAt: new Date().toISOString(),
  head: '3516b39b', doc: DOC, rounds: ROUNDS,
  mode: 'realapp + CDP', concurrencyBefore: concurrency(), rounds_raw: [],
};

// 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true})`);
await sleep(8000);

for (let i = 0; i < ROUNDS; i++) {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true})`);
  await sleep(1500);
  await cdp.ev(`(function(){ window.__seg.reset(); window.__lt = []; return 1; })()`);

  const t0 = Date.now();
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);

  // 等到全部公式排完（或超时）
  let done = false, st = null;
  for (let k = 0; k < 400; k++) {
    await sleep(100);
    st = await cdp.ev(`(function(){
      var pv = document.getElementById('preview');
      if (!pv) return { err: 'no preview' };
      var sup = pv.querySelectorAll('span.-math:not(:has(mjx-container))').length;
      var blk = pv.querySelectorAll('.-math-block:not(:has(mjx-container))').length;
      return { mjx: pv.querySelectorAll('mjx-container').length, residual: sup+blk, blocks: pv.querySelectorAll('.-src-block').length };
    })()`);
    if (st && st.mjx > 100 && st.residual === 0) { done = true; break; }
  }
  const totalMs = Date.now() - t0;

  const seg = await cdp.ev('window.__seg.snapshot()');
  const lt = await cdp.ev('(function(){ return (window.__lt||[]).slice(-30); })()');

  const rec = { totalMs, doneOk: done, state: st, segments: seg, longtasks: lt };
  results.rounds_raw.push(rec);

  const fmt = Object.entries(seg || {}).filter(([k]) => !k.startsWith('typeset_items'))
    .map(([k, v]) => k + '=' + v.n + 'x/' + v.max.toFixed(0) + 'ms').join(' ');
  console.log('[r' + (i + 1) + '] total=' + totalMs + 'ms done=' + done + ' mjx=' + (st && st.mjx) + ' | ' + fmt);
  if (lt && lt.length) {
    console.log('    longtasks: ' + lt.map(x => x.dur.toFixed(0) + 'ms@' + x.start.toFixed(0)).join(' '));
  }
  await sleep(500);
}

function agg(key) {
  const vals = [];
  for (const r of results.rounds_raw) {
    const a = r.segments && r.segments[key];
    if (a && a.list) vals.push(...a.list);
  }
  if (!vals.length) return null;
  vals.sort((x, y) => x - y);
  const n = vals.length;
  const mean = vals.reduce((s, x) => s + x, 0) / n;
  return { n, mean: +mean.toFixed(1), p50: +vals[Math.floor(n * 0.5)].toFixed(1), max: +vals[n - 1].toFixed(1) };
}

const keys = new Set();
for (const r of results.rounds_raw) for (const k of Object.keys(r.segments || {})) keys.add(k);
results.segmentAgg = {};
for (const k of keys) results.segmentAgg[k] = agg(k);
results.concurrencyAfter = concurrency();

writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');

console.log('');
console.log('=== 分段汇总（所有轮次合并）===');
const order = ['renderPreview_TOTAL', 'parse', 'renderDocument', 'renderBlock', 'stampBlockLines', 'typeset_call_sync', 'typeset_call_async'];
for (const k of order) {
  if (results.segmentAgg[k]) {
    const a = results.segmentAgg[k];
    console.log('  %-22s n=%-3d mean=%-8s p50=%-8s max=%s', k, a.n, a.mean, a.p50, a.max);
  }
}
for (const k of Object.keys(results.segmentAgg)) {
  if (!order.includes(k) && !k.startsWith('typeset_items')) {
    const a = results.segmentAgg[k];
    console.log('  %-22s n=%-3d mean=%-8s p50=%-8s max=%s', k, a.n, a.mean, a.p50, a.max);
  }
}

const allLt = [];
for (const r of results.rounds_raw) for (const x of (r.longtasks || [])) allLt.push(x.dur);
allLt.sort((a, b) => a - b);
console.log('');
console.log('=== Long Tasks ===');
console.log('  数量: ' + allLt.length + '  >200ms: ' + allLt.filter(x => x > 200).length);
if (allLt.length) console.log('  max=' + allLt[allLt.length-1].toFixed(0) + 'ms p50=' + allLt[Math.floor(allLt.length*0.5)].toFixed(0) + 'ms');

console.log('');
console.log('__SEG__' + JSON.stringify({
  out: outPath,
  segmentAgg: Object.fromEntries(Object.entries(results.segmentAgg).filter(([k]) => !k.startsWith('typeset_items'))),
  longtaskCount: allLt.length,
  longtaskOver200: allLt.filter(x => x > 200).length,
  longtaskMax: allLt.length ? +allLt[allLt.length-1].toFixed(0) : null,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
