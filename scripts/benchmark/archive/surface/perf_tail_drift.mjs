/**
 * W3.3 批尾布局 —— **用户可见高度漂移**独立验证（不依赖 app 内部 drift 指标）。
 *
 * 做法：固定在文档 35% 处，记录 `scrollTop` 与"视口顶部第一个可见块的源行号/相对屏幕位置"；
 * 深滚到 85%（触发视口上方大量换出），再**回到完全相同的 scrollTop**（触发换回物化）；
 * 比较同一 scrollTop 下看到的行号与像素偏移。高度若有漂移，行号/偏移就会变。
 *
 * 同 build 同实例交替 `legacy` / `pred`，每模式多循环。输出每次的 lineDelta / topDelta / shDelta。
 *
 * 用法: node scripts/benchmark/surface/perf_tail_drift.mjs <port> <out.json> [--cycles 3] [--f1 0.35] [--f2 0.85]
 */
import { writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  if (i < 0) return def;
  const v = process.argv[i + 1];
  return v && !v.startsWith('--') ? v : true;
}
const port = Number(process.argv[2]);
const outPath = process.argv[3];
if (!port || !outPath) { console.error('usage: node perf_tail_drift.mjs <port> <out.json>'); process.exit(2); }
const CYCLES = Number(arg('cycles', 3));
const F1 = Number(arg('f1', 0.35));
const F2 = Number(arg('f2', 0.85));
const DOC = arg('doc', '教材/08_第8章_差错控制编码.md');

async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000);
      ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); });
    });
  }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return;
    const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id);
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 300000) { return new Promise((res, rej) => { const id = ++this._id;
    const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs);
    this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } });
    this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr, awaitPromise = true) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise, userGesture: true });
    if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || ''));
    return r.result ? r.result.value : undefined; }
  async waitFor(expr, timeoutMs = 90000, stepMs = 200) { const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`, false)) return true; } catch { /* */ } await sleep(stepMs); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}

let page = null;
for (let a = 0; a < 60; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`);
    page = (l || []).find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+\//.test(t.url || '') && !/devtools/.test(t.url || '') && t.webSocketDebuggerUrl);
    if (page) break; } catch { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('HeapProfiler.enable').catch(() => {});
if (!(await cdp.waitFor('window.MemoriaApp && window.MemoriaApp.openFile', 120000))) { console.error('app not ready'); process.exit(2); }

await cdp.ev(`(function(){
  window.__MEMORIA_LAZY = true;
  try { localStorage.setItem('memoria.perf.lazy','1'); } catch(e) {}
  var b = document.querySelector('.-view-btn[data-view="preview"]'); if (b) b.click();
  if (window.__dft) return 1;
  var D = {}; window.__dft = D;
  D.quiet = async function(maxMs){
    maxMs = maxMs || 45000;
    var t0 = performance.now(), lastKey = null, stable = 0, last = null;
    while (performance.now() - t0 < maxMs) {
      await new Promise(function(r){ setTimeout(r, 300); });
      var s = window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null;
      if (!s) continue; last = s;
      var key = s.materialized + '|' + s.placeholders + '|' + s.evictTotal;
      if (key === lastKey) stable++; else { stable = 0; lastKey = key; }
      if (stable >= 5) return { quietMs:+(performance.now()-t0).toFixed(1), stats:s };
    }
    return { quietMs:+(performance.now()-t0).toFixed(1), stats:last, timeout:true };
  };
  D.topLine = function(){
    var pane = document.getElementById('preview-pane');
    var cc = document.querySelector('#preview .-preview-content');
    if (!pane || !cc) return null;
    var pr = pane.getBoundingClientRect();
    var kids = cc.children;
    var first = null;
    for (var i = 0; i < kids.length; i++) {
      var el = kids[i];
      if (!el.hasAttribute || !el.hasAttribute('data--src-line')) continue;
      var r = el.getBoundingClientRect();
      if (r.bottom > pr.top + 1) { first = el; break; }
    }
    if (!first) return { paneTop: pr.top, line: null, top: null, scrollTop: pane.scrollTop, sh: pane.scrollHeight, mat: -1 };
    var r1 = first.getBoundingClientRect();
    return {
      line: parseInt(first.getAttribute('data--src-line'), 10),
      top: +(r1.top - pr.top).toFixed(2),
      scrollTop: +pane.scrollTop.toFixed(2),
      sh: pane.scrollHeight,
      mat: window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS().materialized : -1,
    };
  };
  D.seek = async function(frac){
    var pane = document.getElementById('preview-pane');
    var max = Math.max(0, pane.scrollHeight - pane.clientHeight);
    pane.scrollTop = Math.round(max * frac);
    var q = await D.quiet(45000);
    return { targetScrollTop: Math.round(max * frac), actual: +pane.scrollTop.toFixed(2), quiet: q };
  };
  D.seekTo = async function(y){
    var pane = document.getElementById('preview-pane');
    pane.scrollTop = y;
    var q = await D.quiet(45000);
    return { requested: y, actual: +pane.scrollTop.toFixed(2), quiet: q };
  };
  return 1;
})()`);

async function openDoc() {
  await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile('homework/README.md', {skipNav:true}); } catch(e){} return 1; })()`);
  await sleep(1500);
  const r = await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); return 'ok'; } catch(e){ return 'ERR:'+e.message; } })()`);
  if (r !== 'ok') { console.error('openFile:', r); process.exit(3); }
  for (let attempt = 0; attempt < 4; attempt++) {
    for (let i = 0; i < 20; i++) { const vm = await cdp.ev('(window.state||{}).viewMode', false); if (vm === 'preview') break;
      await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`, false); await sleep(400); }
    for (let i = 0; i < 120; i++) { const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false); if (s && s.totalBlocks > 3900) break; await sleep(250); }
    const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
    if (s && s.totalBlocks > 3900) break;
    await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); } catch(e){} return 1; })()`);
    await sleep(2500);
  }
  return await cdp.ev('window.__dft.quiet(60000)');
}
console.log('[open]', JSON.stringify(await openDoc()));
{
  const st = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
  if (!st || st.totalBlocks < 3900) { console.error('OPEN FAILED totalBlocks=' + (st && st.totalBlocks)); process.exit(5); }
}

const R = { schema: 'memoria-tail-drift/v1', at: new Date().toISOString(), doc: DOC, f1: F1, f2: F2,
  scriptSha256: createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'), cycles: [] };

async function cycle(mode, i) {
  await cdp.ev(`window.__MEMORIA_TAIL_LAYOUT.setMode(${JSON.stringify(mode)})`, false);
  await cdp.ev('window.__dft.seek(0)');
  await cdp.ev('window.__dft.seek(' + F1 + ')');
  const a = await cdp.ev('window.__dft.topLine()', false);
  const deep = await cdp.ev('window.__dft.seek(' + F2 + ')');
  const back = await cdp.ev('window.__dft.seekTo(' + a.scrollTop + ')');
  const b = await cdp.ev('window.__dft.topLine()', false);
  const row = {
    cycle: i + 1, mode, A: a, B: b, deep,
    lineDelta: (a && b && a.line != null && b.line != null) ? b.line - a.line : null,
    topDelta: (a && b && a.top != null && b.top != null) ? +(b.top - a.top).toFixed(2) : null,
    scrollTopDelta: (a && b) ? +(b.scrollTop - a.scrollTop).toFixed(2) : null,
    shDelta: (a && b) ? b.sh - a.sh : null,
    back,
  };
  console.log(`[${mode}#${i + 1}] line ${a.line}->${b.line} Δ=${row.lineDelta} topΔ=${row.topDelta}px`
    + ` scrollTopΔ=${row.scrollTopDelta} shΔ=${row.shDelta} mat=${a.mat}->${b.mat}`);
  return row;
}

for (let i = 0; i < CYCLES; i++) {
  R.cycles.push(await cycle('legacy', i));
  R.cycles.push(await cycle('pred', i));
  R.cycles.push(await cycle('pred', i + 0.5));
  R.cycles.push(await cycle('legacy', i + 0.5));
}
const pick = (m) => R.cycles.filter((c) => c.mode === m);
const num = (x) => typeof x === 'number' && isFinite(x);
const absStats = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y);
  return { n: s.length, median: s[Math.floor(s.length / 2)], max: s[s.length - 1], values: a }; };
R.summary = {
  legacy: { lineAbs: absStats(pick('legacy').map((c) => c.lineDelta).filter(num).map(Math.abs)),
    topAbs: absStats(pick('legacy').map((c) => c.topDelta).filter(num).map(Math.abs)),
    shAbs: absStats(pick('legacy').map((c) => c.shDelta).filter(num).map(Math.abs)) },
  pred: { lineAbs: absStats(pick('pred').map((c) => c.lineDelta).filter(num).map(Math.abs)),
    topAbs: absStats(pick('pred').map((c) => c.topDelta).filter(num).map(Math.abs)),
    shAbs: absStats(pick('pred').map((c) => c.shDelta).filter(num).map(Math.abs)) },
};
writeFileSync(outPath, JSON.stringify(R, null, 2), 'utf8');
console.log('[SUMMARY]', JSON.stringify(R.summary));
console.log('[out]', outPath);
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
