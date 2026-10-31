/**
 * task-63 C：量化「每批固定开销」
 *
 * 1. typesetPromise 空集/1 公式调用耗时（纯固定成本）
 * 2. _ensureLazyLockedIO() 是否每批新建 IntersectionObserver
 * 3. min-height 锁是否每批触发 style recalc（Performance.getMetrics 的 RecalcStyleDuration 增量）
 */
import { writeFileSync } from 'node:fs';
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

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:/.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Performance.enable').catch(() => {});
if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }

await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

const R = { head: 'e73a41ce', doc: DOC };

// ── 1. typesetPromise 固定开销：空集 / 1 公式 ──
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
await sleep(5000);

R.typesetFixedCost = await cdp.ev(`(async function(){
  var MJ = window.MathJax;
  if (!MJ || typeof MJ.typesetPromise !== 'function') return { err: 'no typesetPromise' };
  var out = { empty: [], one: [], div: [] };
  // 空集：传一个无公式的空 div
  var emptyDiv = document.createElement('div');
  document.body.appendChild(emptyDiv);
  for (var i=0;i<5;i++){ var t=performance.now(); try { await MJ.typesetPromise([emptyDiv]); } catch(e){} out.empty.push(+(performance.now()-t).toFixed(1)); }
  // 1 公式
  var oneDiv = document.createElement('div');
  oneDiv.innerHTML = '<span class="-math">x^2+y^2=z^2</span>';
  document.body.appendChild(oneDiv);
  for (var j=0;j<5;j++){ var t2=performance.now(); try { await MJ.typesetPromise([oneDiv]); } catch(e){} out.one.push(+(performance.now()-t2).toFixed(1)); }
  document.body.removeChild(emptyDiv);
  document.body.removeChild(oneDiv);
  return out;
})()`, true);
console.log('[1] typeset 固定开销: ' + JSON.stringify(R.typesetFixedCost));

// ── 2. _ensureLazyLockedIO 是否每批新建 IO（看 IO 实例数 / unobserve 行为）──
//    惰性模式下不直接暴露内部变量，改用"批量物化时观察 IO 创建"的间接法：
//    统计拖拽前后 IntersectionObserver 的活跃观察目标数变化（无法直接取）
//    改用：检查 source 是否每次 new（静态可判），并在运行时看是否有多个 observer 行为
R.ioAudit = await cdp.ev(`(function(){
  // 静态判断已由代码审查给出；运行时只能测"拖拽前后是否出现重复 observe 导致回调倍增"
  return { note: 'code-level: _ensureLazyLockedIO 有 if (_lazyLockedIO) return 守卫' };
})()`);
console.log('[2] IO 审计: ' + JSON.stringify(R.ioAudit));

// ── 3. min-height 锁的 style recalc 增量 ──
async function getMetrics() {
  const m = await cdp.send('Performance.getMetrics');
  const o = {};
  for (const x of (m.metrics || [])) o[x.name] = x.value;
  return o;
}
const mBefore = await getMetrics();

// 触发拖拽（10 帧扫到底）
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(s / 10).toFixed(2)}; return 1; })()`);
  await sleep(16);
}
await sleep(5000);
const mAfter = await getMetrics();

const d = {};
for (const k of ['RecalcStyleDuration', 'LayoutDuration', 'TaskDuration', 'ScriptDuration', 'RecalcStyleCount', 'LayoutCount']) {
  if (mBefore[k] !== undefined && mAfter[k] !== undefined) d[k] = +(mAfter[k] - mBefore[k]).toFixed(3);
}
R.recalcDelta = d;
console.log('[3] 拖拽期间指标增量: ' + JSON.stringify(d));

// ── 补充：单批物化的 DOM 成本（用一次小批测量）──
// 记录拖拽后的状态
R.afterState = await cdp.ev(`(function(){
  var pv=document.getElementById('preview'); var cc=pv?(pv.querySelector('.-preview-content')||pv):null;
  return { ph: cc?cc.querySelectorAll('.-pv-placeholder').length:-1, mjx: pv?pv.querySelectorAll('mjx-container').length:0 };
})()`);
console.log('[4] 拖后状态: ' + JSON.stringify(R.afterState));

writeFileSync(outPath, JSON.stringify(R, null, 2), 'utf8');
console.log('');
console.log('__C__' + JSON.stringify({
  emptyTypesetAvg: R.typesetFixedCost && R.typesetFixedCost.empty ?
    +(R.typesetFixedCost.empty.reduce((s, x) => s + x, 0) / R.typesetFixedCost.empty.length).toFixed(1) : null,
  oneTypesetAvg: R.typesetFixedCost && R.typesetFixedCost.one ?
    +(R.typesetFixedCost.one.reduce((s, x) => s + x, 0) / R.typesetFixedCost.one.length).toFixed(1) : null,
  recalcStyleDuration: d.RecalcStyleDuration,
  layoutDuration: d.LayoutDuration,
  recalcCount: d.RecalcStyleCount,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
