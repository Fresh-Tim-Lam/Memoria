/**
 * task-63 v0.4.6 前提验证：「工作集是否无限增长」
 *
 * A. 长滚动后驻留量：打开 → 从头滚到底(20步,每步300ms) → 记录 DOM/块数/mjx/堆
 * B. 第二遍滚动性能：滚回顶部(20步) → 每步帧间隔，与第一遍对比
 * C. 对照：只滚到 40% 就返回
 *
 * ⚠️ 观察者效应：采样循环只做轻量读取（getBoundingClientRect 计数），
 *    不调 counters() 等可能触发副作用的函数。
 *
 * 用法: node perf_workset.mjs <port> <out.json> [scenario]  scenario=A|B|C
 */
import { writeFileSync } from 'node:fs';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 180000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, userGesture: true }); if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || '')); return r.result ? r.result.value : undefined; }
  async waitFor(expr, timeoutMs = 60000) { const t0 = Date.now(); while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`)) return true; } catch (e) { /* */ } await sleep(150); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}
const port = Number(process.argv[2]);
const outPath = process.argv[3];
const SCENARIO = process.argv[4] || 'AB';   // AB | C
const DOC = process.argv[5] || '教材/08_第8章_差错控制编码.md';

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Performance.enable').catch(() => {});
if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} try{ window.__MEMORIA_DEFER=false; }catch(e){} return 1; })()`);

// 轻量探针：只做计数，不调重函数
await cdp.ev(`(function(){
  if (window.__ws) return 1;
  var W = {}; window.__ws = W;
  W.pane = function(){ return document.getElementById('preview-pane'); };
  W.cc = function(){ return document.querySelector('#preview .-preview-content') || document.getElementById('preview'); };
  // 轻量计数
  W.snap = function(){
    var pv = document.getElementById('preview');
    var cc = W.cc();
    if (!pv || !cc) return null;
    var out = {
      domNodes: pv.getElementsByTagName('*').length,   // 含所有子孙
      srcBlocks: cc.querySelectorAll('.-src-block').length,
      placeholders: cc.querySelectorAll('.-pv-placeholder').length,
      mjx: pv.querySelectorAll('mjx-container').length,
      mathSpans: pv.querySelectorAll('span.-math').length,
      imgs: pv.querySelectorAll('img').length,
      tables: pv.querySelectorAll('table').length,
      svgs: pv.querySelectorAll('svg').length,
      scrollTop: Math.round(W.pane().scrollTop),
      scrollHeight: W.pane().scrollHeight
    };
    return out;
  };
  // 视口内占位块数（轻量）
  W.vph = function(){
    var p = W.pane(), cc = W.cc(); if (!p || !cc) return -1;
    var pr = p.getBoundingClientRect(); var n = 0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) n++;
    });
    return n;
  };
  // 帧间隔采集（只 push 数字，极轻）
  W.startFrames = function(){ W.on = true; W.gaps = []; W.last = performance.now();
    (function t(){ if(!W.on) return; var n=performance.now(); W.gaps.push(+(n-W.last).toFixed(1)); W.last=n; requestAnimationFrame(t); })(); };
  W.stopFrames = function(){ W.on = false; var g=(W.gaps||[]).filter(function(x){return isFinite(x)&&x>0;}).sort(function(a,b){return a-b;});
    var n=g.length; return { n: n, max: n?+g[n-1].toFixed(1):null, p95: n?+g[Math.floor(n*0.95)].toFixed(1):null,
      over100: g.filter(function(x){return x>100;}).length, over200: g.filter(function(x){return x>200;}).length }; };
  W.resetFrames = function(){ W.gaps = []; W.last = performance.now(); };
  return 1;
})()`);

async function heap() {
  try {
    const m = await cdp.send('Performance.getMetrics');
    const o = {};
    for (const x of (m.metrics || [])) o[x.name] = x.value;
    return { JSHeapUsedMB: o.JSHeapUsedSize ? +(o.JSHeapUsedSize / 1048576).toFixed(1) : null,
             JSHeapTotalMB: o.JSHeapTotalSize ? +(o.JSHeapTotalSize / 1048576).toFixed(1) : null,
             Nodes: o.Nodes ?? null, Documents: o.Documents ?? null,
             LayoutCount: o.LayoutCount ?? null, RecalcStyleCount: o.RecalcStyleCount ?? null };
  } catch (e) { return { err: String(e && e.message) }; }
}

async function openDoc() {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
  for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
  for (let k = 0; k < 150; k++) { await sleep(150); if (await cdp.ev('window.__ws.vph()') === 0) break; }
  await sleep(1500);
}

// 分步滚动，每步等 300ms，记录每步的帧间隔与驻留量
async function scrollPass(steps, fromPct, toPct, label) {
  const perStep = [];
  await cdp.ev('window.__ws.startFrames()');
  for (let i = 1; i <= steps; i++) {
    const pct = fromPct + (toPct - fromPct) * (i / steps);
    await cdp.ev('window.__ws.resetFrames()');
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${pct.toFixed(4)}; return 1; })()`);
    await sleep(300);
    const f = await cdp.ev('window.__ws.stopFrames()');
    const s = await cdp.ev('window.__ws.snap()');
    perStep.push({ step: i, pct: +pct.toFixed(3), frameMax: f.max, frameOver100: f.over100,
      domNodes: s ? s.domNodes : null, mjx: s ? s.mjx : null, placeholders: s ? s.placeholders : null,
      scrollTop: s ? s.scrollTop : null });
    // 重启帧采集（stopFrames 已关）
    await cdp.ev('window.__ws.startFrames()');
  }
  await cdp.ev('window.__ws.stopFrames()');
  return perStep;
}

const result = { head: '4e401d8c', doc: DOC, scenario: SCENARIO };

if (SCENARIO === 'C') {
  // C：只滚到 40% 就返回
  await openDoc();
  result.before = { snap: await cdp.ev('window.__ws.snap()'), heap: await heap() };
  console.log('=== C：只滚到 40% ===');
  const pass1 = await scrollPass(8, 0, 0.4, 'down');
  const midSnap = await cdp.ev('window.__ws.snap()');
  const midHeap = await heap();
  console.log('  滚到 40% 后: DOM=' + midSnap.domNodes + ' blocks=' + midSnap.srcBlocks +
    ' ph=' + midSnap.placeholders + ' mjx=' + midSnap.mjx + ' heap=' + midHeap.JSHeapUsedMB + 'MB');
  const pass2 = await scrollPass(8, 0.4, 0, 'up');
  const endSnap = await cdp.ev('window.__ws.snap()');
  const endHeap = await heap();
  console.log('  返回顶部后: DOM=' + endSnap.domNodes + ' blocks=' + endSnap.srcBlocks +
    ' ph=' + endSnap.placeholders + ' mjx=' + endSnap.mjx + ' heap=' + endHeap.JSHeapUsedMB + 'MB');
  result.pass1 = pass1; result.pass2 = pass2;
  result.mid = { snap: midSnap, heap: midHeap }; result.end = { snap: endSnap, heap: endHeap };
} else {
  // A + B：滚到底 + 滚回
  await openDoc();
  result.before = { snap: await cdp.ev('window.__ws.snap()'), heap: await heap() };
  console.log('=== 打开后（初始）===');
  console.log('  DOM=' + result.before.snap.domNodes + ' blocks=' + result.before.snap.srcBlocks +
    ' ph=' + result.before.snap.placeholders + ' mjx=' + result.before.snap.mjx +
    ' heap=' + result.before.heap.JSHeapUsedMB + 'MB');

  console.log('');
  console.log('=== A：从头滚到底（20 步 × 300ms）===');
  const passA = await scrollPass(20, 0, 1.0, 'down');
  const afterA = await cdp.ev('window.__ws.snap()');
  const heapA = await heap();
  console.log('  滚到底后: DOM=' + afterA.domNodes + ' blocks=' + afterA.srcBlocks +
    ' ph=' + afterA.placeholders + ' mjx=' + afterA.mjx + ' heap=' + heapA.JSHeapUsedMB + 'MB');

  console.log('');
  console.log('=== B：滚回顶部（20 步 × 300ms）===');
  const passB = await scrollPass(20, 1.0, 0, 'up');
  const afterB = await cdp.ev('window.__ws.snap()');
  const heapB = await heap();
  console.log('  回到顶部后: DOM=' + afterB.domNodes + ' blocks=' + afterB.srcBlocks +
    ' ph=' + afterB.placeholders + ' mjx=' + afterB.mjx + ' heap=' + heapB.JSHeapUsedMB + 'MB');

  result.passA = passA; result.passB = passB;
  result.afterA = { snap: afterA, heap: heapA };
  result.afterB = { snap: afterB, heap: heapB };

  // 逐位置对照（第一遍 step i 向下 vs 第二遍对应位置向上）
  console.log('');
  console.log('=== 第一遍 vs 第二遍 同位置帧间隔对照 ===');
  console.log('  %-8s %-12s %-12s %-10s' % ('位置', '第一遍帧max', '第二遍帧max', '变化'));
  const rows = [];
  for (let i = 0; i < 20; i++) {
    // 第一遍 step i (i+1)/20；第二遍对应同一 pct 的步骤：passB 从 1.0→0，step j 的 pct=1-j/20
    const pctA = passA[i] ? passA[i].pct : null;
    const matchB = passB.find(x => Math.abs(x.pct - pctA) < 0.026);
    const fmA = passA[i] ? passA[i].frameMax : null;
    const fmB = matchB ? matchB.frameMax : null;
    const change = (fmA != null && fmB != null && fmA > 0) ? ((fmB - fmA) / fmA * 100).toFixed(0) + '%' : '-';
    rows.push({ pct: pctA, frameMaxA: fmA, frameMaxB: fmB, change });
    console.log('  %-8s %-12s %-12s %-10s' % (pctA != null ? (pctA*100).toFixed(0)+'%' : '?',
      fmA != null ? fmA + 'ms' : '-', fmB != null ? fmB + 'ms' : '-', change));
  }
  result.comparison = rows;
}

writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
console.log('');
console.log('__WS__' + JSON.stringify({ scenario: SCENARIO,
  before: result.before ? { dom: result.before.snap.domNodes, mjx: result.before.snap.mjx, heapMB: result.before.heap.JSHeapUsedMB } : null,
  afterA: result.afterA ? { dom: result.afterA.snap.domNodes, mjx: result.afterA.snap.mjx, heapMB: result.afterA.heap.JSHeapUsedMB } : null,
  afterB: result.afterB ? { dom: result.afterB.snap.domNodes, mjx: result.afterB.snap.mjx, heapMB: result.afterB.heap.JSHeapUsedMB } : null,
  mid: result.mid ? { dom: result.mid.snap.domNodes, mjx: result.mid.snap.mjx, heapMB: result.mid.heap.JSHeapUsedMB } : null,
  end: result.end ? { dom: result.end.snap.domNodes, mjx: result.end.snap.mjx, heapMB: result.end.heap.JSHeapUsedMB } : null,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
