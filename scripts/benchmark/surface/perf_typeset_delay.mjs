/**
 * task-63 0.4.7：测量「块物化完成 → typeset 开始」延迟分布
 *
 * 打点方式（纯旁路，不改产品代码）：
 *   t_mat : MutationObserver 捕获"占位块被真块替换"的时刻，记该块 index
 *   t_ts  : 包装 MathJax.typesetPromise，记录每次调用的开始/结束时刻 + 传入元素
 *
 * 匹配：对每个物化块，找到"包含它的第一次 typeset 调用"，算 t_ts - t_mat
 *
 * 用法: node perf_typeset_delay.mjs <port> <out.json> [target]
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
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} try{ window.__MEMORIA_DEFER=false; }catch(e){} return 1; })()`);

// 打点探针
await cdp.ev(`(function(){
  if (window.__td) return 1;
  var T = { mat: [], ts: [], t0: performance.now() };
  window.__td = T;
  T.now = function(){ return +(performance.now() - T.t0).toFixed(1); };

  // ① 包装 typesetPromise（记录调用开始/结束 + 传入元素的下标）
  T.wrapTypeset = function(){
    var MJ = window.MathJax;
    if (!MJ || typeof MJ.typesetPromise !== 'function') return 'no-typesetPromise';
    if (MJ.__tdWrapped) return 'already';
    var orig = MJ.typesetPromise.bind(MJ);
    MJ.typesetPromise = function(items){
      var start = T.now();
      var idxs = [];
      try {
        if (items && items.length) {
          for (var i = 0; i < items.length; i++) {
            var el = items[i];
            if (!el || !el.getAttribute) continue;
            var bi = el.getAttribute('data--block-index');
            if (bi != null) { idxs.push(+bi); continue; }
            // 可能是容器：找其内部所有块
            if (el.querySelectorAll) {
              el.querySelectorAll('[data--block-index]').forEach(function(e){
                var b = e.getAttribute('data--block-index');
                if (b != null) idxs.push(+b);
              });
            }
          }
        }
      } catch (e) {}
      var rec = { tStart: start, n: idxs.length, idxs: idxs.slice(0, 80), tEnd: null };
      T.ts.push(rec);
      var pr = orig(items);
      if (pr && pr.then) {
        pr.then(function(){ rec.tEnd = T.now(); }, function(){ rec.tEnd = T.now(); rec.err = 1; });
      } else { rec.tEnd = start; }
      return pr;
    };
    MJ.__tdWrapped = true;
    return 'wrapped';
  };

  // ② MutationObserver 观测"占位块 → 真块"替换
  T.observeMat = function(){
    var cc = document.querySelector('#preview .-preview-content') || document.getElementById('preview');
    if (!cc) return 'no-cc';
    T.mo = new MutationObserver(function(muts){
      var now = T.now();
      muts.forEach(function(m){
        for (var i = 0; i < m.addedNodes.length; i++) {
          var n = m.addedNodes[i];
          if (!n || n.nodeType !== 1) continue;
          if (n.classList && n.classList.contains('-src-block') && !n.classList.contains('-pv-placeholder')) {
            var bi = n.getAttribute('data--block-index');
            if (bi != null) T.mat.push({ t: now, idx: +bi, hasMath: !!(n.querySelector && (n.querySelector('.-math, .-math-block'))) });
          }
        }
      });
    });
    T.mo.observe(cc, { childList: true, subtree: true });
    return 'observing';
  };

  T.stop = function(){
    if (T.mo) { T.mo.disconnect(); T.mo = null; }
    return { mat: T.mat, ts: T.ts };
  };
  return 1;
})()`);

const wrapRes = await cdp.ev('window.__td.wrapTypeset()');
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

// 重置打点 + 开始观测
await cdp.ev(`(function(){ window.__td.mat = []; window.__td.ts = []; window.__td.t0 = performance.now(); return 1; })()`);
const obsRes = await cdp.ev('window.__td.observeMat()');
console.log('  物化观测: ' + obsRes);

console.log('');
console.log('=== 拖拽到 ' + (TARGET * 100) + '% ===');
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(TARGET * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}
await sleep(5000);
const data = await cdp.ev('window.__td.stop()');

const mats = data.mat || [];
const tss = data.ts || [];
console.log('  物化块数: ' + mats.length);
console.log('  typeset 调用数: ' + tss.length);

// 匹配：对每个物化块，找包含它的最早 typeset 调用
const results = [];
for (const m of mats) {
  let best = null;
  for (const t of tss) {
    if (t.tStart < m.t) continue;                       // 必须在物化之后
    if (t.idxs && t.idxs.indexOf(m.idx) >= 0) { best = t; break; }
  }
  // 若无精确匹配，退而求"物化后第一次 typeset"（近似，需标注）
  let approx = null;
  if (!best) {
    for (const t of tss) { if (t.tStart >= m.t) { approx = t; break; } }
  }
  if (best) results.push({ idx: m.idx, tMat: m.t, tTs: best.tStart, delay: +(best.tStart - m.t).toFixed(1), exact: true, hasMath: m.hasMath });
  else if (approx) results.push({ idx: m.idx, tMat: m.t, tTs: approx.tStart, delay: +(approx.tStart - m.t).toFixed(1), exact: false, hasMath: m.hasMath });
  else results.push({ idx: m.idx, tMat: m.t, tTs: null, delay: null, exact: false, hasMath: m.hasMath, noTypeset: true });
}

const withDelay = results.filter(r => r.delay != null).sort((a, b) => a.delay - b.delay);
const exact = withDelay.filter(r => r.exact);
const delays = withDelay.map(r => r.delay);
const eDelays = exact.map(r => r.delay);
const noTs = results.filter(r => r.noTypeset).length;

function stats(arr) {
  if (!arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  return { n: s.length, min: +s[0].toFixed(0), median: +s[Math.floor(s.length / 2)].toFixed(0),
           p95: +s[Math.min(s.length - 1, Math.floor(s.length * 0.95))].toFixed(0),
           max: +s[s.length - 1].toFixed(0),
           over100: s.filter(x => x > 100).length, over500: s.filter(x => x > 500).length };
}

console.log('');
console.log('=== ★ 物化 → typeset 开始 延迟 ===');
console.log('  【精确匹配】（typeset 批次实际包含该块）:');
console.log('    ' + JSON.stringify(stats(eDelays)));
console.log('  【含近似匹配】（物化后第一次 typeset，非精确包含）:');
console.log('    ' + JSON.stringify(stats(delays)));
console.log('  从未被 typeset 的物化块: ' + noTs);
console.log('');
console.log('=== typeset 调用明细（前 15 次）===');
tss.slice(0, 15).forEach((t, i) => {
  console.log('  #' + i + ' tStart=' + t.tStart + 'ms  tEnd=' + t.tEnd + 'ms  持续=' +
    (t.tEnd != null ? (t.tEnd - t.tStart).toFixed(0) : '?') + 'ms  块数=' + t.n);
});
console.log('');
console.log('=== 延迟最大的 10 个物化块 ===');
const slowest = withDelay.slice(-10).reverse();
slowest.forEach(r => console.log('  idx=' + r.idx + ' 物化@' + r.tMat + 'ms → typeset@' + r.tTs + 'ms  延迟=' + r.delay + 'ms  ' + (r.exact ? '(精确)' : '(近似)') + '  含公式=' + r.hasMath));

const out = {
  head: '13e64144', doc: DOC, target: TARGET,
  matCount: mats.length, tsCount: tss.length, noTypesetCount: noTs,
  exactStats: stats(eDelays), approxStats: stats(delays),
  results, typesetCalls: tss,
};
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__DELAY__' + JSON.stringify({ exact: stats(eDelays), approx: stats(delays), noTs }));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
