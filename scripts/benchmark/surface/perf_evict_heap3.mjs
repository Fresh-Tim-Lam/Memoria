/**
 * task-76 / W3：**堆不回退**验收（3 遍滚动 + 回顶 + GC 后 JS 堆稳定）。
 *
 * 口径与 `artifacts/agent/verify/task70-heap-report.md` §1 一致：
 *   真机 WebView2 + `MEMORIA_DEBUG=0`（无 DevTools 观察者效应），文档
 *   `教材/08_第8章_差错控制编码.md`（4001 块），`window.__MEMORIA_LAZY = true`；
 *   每遍：20 步滚到底（300ms/步）→ 等 workset 稳定 → 20 步滚回顶（300ms/步）→ 等稳定
 *   → `HeapProfiler.collectGarbage` ×2 → `Runtime.getHeapUsage` + `Memory.getDOMCounters`。
 *
 * 用途：确认「切片/降批」没有把 `MathJax.typesetClear` 漏掉（漏了会回到 85MB 级别）。
 *
 * 用法：node scripts/benchmark/surface/perf_evict_heap3.mjs <port> <out.json> [--passes 3] [--doc ...]
 */
import { writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function arg(name, def) { const i = process.argv.indexOf('--' + name); if (i < 0) return def; const v = process.argv[i + 1]; return v && !v.startsWith('--') ? v : true; }
const port = Number(process.argv[2]);
const outPath = process.argv[3];
const PASSES = Number(arg('passes', 3));
const DOC = arg('doc', '教材/08_第8章_差错控制编码.md');
if (!port || !outPath) { console.error('usage: node perf_evict_heap3.mjs <port> <out.json>'); process.exit(2); }

const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = (list || []).find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+\//.test(t.url || '') && !/devtools/.test(t.url || ''));
if (!page) { console.error('no page'); process.exit(2); }

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
let id = 0; const pend = new Map();
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (x) => {
  const r = await send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true, userGesture: true });
  if (r.result && r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  return r.result && r.result.result ? r.result.result.value : undefined;
};
await send('Runtime.enable'); await send('HeapProfiler.enable');
for (let i = 0; i < 120; i++) { if (await ev('!!(window.MemoriaApp && window.MemoriaApp.openFile)')) break; await sleep(500); }
await ev('window.__MEMORIA_LAZY = true; try{localStorage.setItem("memoria.perf.lazy","1")}catch(e){}');
await ev(`(()=>{const b=document.querySelector('.-view-btn[data-view="preview"]'); if(b)b.click(); return 1})()`);
await sleep(400);
await ev(`(async()=>{try{await window.MemoriaApp.openFile("homework/README.md",{skipNav:true})}catch(e){} return 1})()`);
await sleep(1500);
console.log('open 08:', await ev(`(async()=>{try{await window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true});return "ok"}catch(e){return "ERR:"+e.message}})()`));
for (let i = 0; i < 240; i++) {
  const n = await ev(`document.querySelectorAll('#preview .-pv-placeholder, #preview .-src-block').length`);
  if (n > 3800) break;
  await sleep(250);
}
await sleep(2500);

const pane = `document.getElementById('preview-pane')`;
const STATE = `(()=>{const d=MathJax.startup.document;let m=0,dis=0;for(const x of d.math){m++;if(x.typesetRoot&&!x.typesetRoot.isConnected)dis++;} const pv=document.getElementById('preview'); const pane=${pane}; return {math:m,mathDisconnected:dis,domPreview:pv?pv.getElementsByTagName('*').length:null,domBody:document.body.getElementsByTagName('*').length,ws:window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null,mjx:pv?pv.querySelectorAll('mjx-container').length:null,scrollTop:Math.round(pane.scrollTop),scrollHeight:pane.scrollHeight,clientHeight:pane.clientHeight};})()`;

async function heap() {
  await send('HeapProfiler.collectGarbage'); await sleep(300);
  await send('HeapProfiler.collectGarbage'); await sleep(200);
  const h = (await send('Runtime.getHeapUsage')).result;
  const d = (await send('Memory.getDOMCounters')).result;
  return { usedMB: +(h.usedSize / 1048576).toFixed(2), embedderMB: +(h.embedderHeapUsedSize / 1048576).toFixed(2), domNodes: d.nodes, listeners: d.jsEventListeners };
}
async function quiet(maxMs = 45000) {
  const t0 = Date.now(); let lastKey = null, stable = 0, last = null;
  while (Date.now() - t0 < maxMs) {
    await sleep(400);
    const s = await ev(`window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null`);
    if (!s) continue;
    last = s;
    const key = `${s.materialized}|${s.placeholders}|${s.evictTotal}`;
    if (key === lastKey) stable++; else { stable = 0; lastKey = key; }
    if (stable >= 4) return s;
  }
  return last;
}
async function pass(i) {
  console.log(`\n--- pass ${i} down ---`);
  for (let k = 1; k <= 20; k++) {
    await ev(`(()=>{const p=${pane};p.scrollTop=Math.round((p.scrollHeight-p.clientHeight)*${(k / 20).toFixed(4)});return 1;})()`);
    await sleep(300);
  }
  const q1 = await quiet();
  const bState = await ev(STATE); const bHeap = await heap();
  console.log('  bottom mat=' + (bState.ws && bState.ws.materialized) + ' ph=' + (bState.ws && bState.ws.placeholders)
    + ' dom=' + bState.domPreview + ' mjx=' + bState.mjx + ' heap=' + bHeap.usedMB + 'MB');
  console.log(`--- pass ${i} up ---`);
  for (let k = 19; k >= 0; k--) {
    await ev(`(()=>{const p=${pane};p.scrollTop=Math.round((p.scrollHeight-p.clientHeight)*${(k / 20).toFixed(4)});return 1;})()`);
    await sleep(300);
  }
  const q2 = await quiet();
  await sleep(1000);
  const st = await ev(STATE); const h = await heap();
  console.log('  top mat=' + (st.ws && st.ws.materialized) + ' ph=' + (st.ws && st.ws.placeholders)
    + ' dom=' + st.domPreview + ' mjx=' + st.mjx + ' heap=' + h.usedMB + 'MB math=' + st.math
    + ' detached=' + st.mathDisconnected);
  return { pass: i, bottomQuiet: q1, topQuiet: q2, bottom: { state: bState, heap: bHeap }, top: { state: st, heap: h } };
}

const result = {
  schema: 'memoria-evict-heap3/v1',
  at: new Date().toISOString(),
  head: (() => { try { return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { return null; } })(),
  scriptSha256: createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'),
  argv: process.argv.slice(2), port, doc: DOC,
  open: await heap(), openState: await ev(STATE), passes: [],
};
console.log('open baseline heap', JSON.stringify(result.open), 'mat=' + (result.openState.ws && result.openState.ws.materialized));
for (let i = 1; i <= PASSES; i++) result.passes.push(await pass(i));

const tops = result.passes.map((p) => p.top.heap.usedMB);
result.summary = {
  heapMB: tops,
  deltas: tops.map((v, i) => i === 0 ? null : +(((v - tops[i - 1]) / tops[i - 1]) * 100).toFixed(1)),
  openToLastPct: tops.length ? +(((tops[tops.length - 1] - result.open.usedMB) / result.open.usedMB) * 100).toFixed(1) : null,
  firstToLastPct: tops.length > 1 ? +(((tops[tops.length - 1] - tops[0]) / tops[0]) * 100).toFixed(1) : null,
  mathItems: result.passes.map((p) => p.top.state.math),
};
writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
console.log('\n[SUMMARY]', JSON.stringify(result.summary));
console.log('[out]', outPath);
ws.close(); setTimeout(() => process.exit(0), 300).unref();
