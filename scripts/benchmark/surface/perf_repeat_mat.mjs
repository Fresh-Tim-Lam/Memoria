/**
 * task-63 v0.4.6 P2：回滚重复物化 —— 最小复现脚本
 *
 * 目标：精确识别「哪些块在回滚时被重复物化」，并给出证据链。
 *
 * 方法：
 *   1. 用 MutationObserver 记录每个占位块被替换为真块的时刻 + block-index
 *   2. 滚到底（第一遍），记录物化的 block-index 集合
 *   3. 滚回顶（第二遍），观察是否有"第一遍已物化的 index"再次被物化
 *   4. 若有，输出这些 index + 物化时刻 + 前后状态
 *
 * 判定：第二遍出现「第一遍已物化 index 再次物化」= 重复物化 bug。
 *
 * 用法: node perf_repeat_mat.mjs <port> <out.json>
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
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';

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

// MutationObserver 记录物化（占位块 → 真块）
await cdp.ev(`(function(){
  if (window.__rm2) return 1;
  var M = { events: [], phase: 0, t0: performance.now() };
  window.__rm2 = M;
  M.now = function(){ return +(performance.now() - M.t0).toFixed(1); };
  M.startObserve = function(){
    var cc = document.querySelector('#preview .-preview-content') || document.getElementById('preview');
    if (!cc) return 'no-cc';
    M.mo = new MutationObserver(function(muts){
      var now = M.now();
      muts.forEach(function(m){
        // 真块被加入（新增 -src-block 且非 -pv-placeholder）
        for (var i = 0; i < m.addedNodes.length; i++) {
          var n = m.addedNodes[i];
          if (!n || n.nodeType !== 1) continue;
          if (n.classList && n.classList.contains('-src-block') && !n.classList.contains('-pv-placeholder')) {
            var bi = n.getAttribute('data--block-index');
            if (bi != null) {
              M.events.push({ t: now, phase: M.phase, idx: +bi, kind: 'materialize' });
            }
          }
        }
        // 占位块被移回（可能重复物化的前兆）
        for (var j = 0; j < m.removedNodes.length; j++) {
          var r = m.removedNodes[j];
          if (!r || r.nodeType !== 1) continue;
          if (r.classList && r.classList.contains('-pv-placeholder')) {
            var rbi = r.getAttribute('data--block-index');
            if (rbi != null) {
              M.events.push({ t: now, phase: M.phase, idx: +rbi, kind: 'placeholder-removed' });
            }
          }
        }
      });
    });
    M.mo.observe(cc, { childList: true, subtree: true });
    return 'observing';
  };
  M.setPhase = function(p){ M.phase = p; };
  M.stop = function(){
    if (M.mo) { M.mo.disconnect(); M.mo = null; }
    return M.events;
  };
  M.pane = function(){ return document.getElementById('preview-pane'); };
  M.matCount = function(){ return document.querySelectorAll('#preview mjx-container').length; };
  return 1;
})()`);

// 打开
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
for (let k = 0; k < 150; k++) { await sleep(150); const ph = await cdp.ev(`(function(){var p=document.getElementById('preview-pane');if(!p)return -1;var pr=p.getBoundingClientRect();var n=0;p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect();if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;});return n;})()`); if (ph === 0) break; }
await sleep(1500);

await cdp.ev('window.__rm2.startObserve()');

// 第一遍：滚到底，phase=1
await cdp.ev('window.__rm2.setPhase(1)');
for (let s = 1; s <= 20; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(s / 20).toFixed(4)}; return 1; })()`);
  await sleep(300);
}
const mjxAfterDown = await cdp.ev('window.__rm2.matCount()');

// 第二遍：滚回顶，phase=2
await cdp.ev('window.__rm2.setPhase(2)');
for (let s = 1; s <= 20; s++) {
  const pct = 1.0 - (s / 20);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${pct.toFixed(4)}; return 1; })()`);
  await sleep(300);
}
const mjxAfterUp = await cdp.ev('window.__rm2.matCount()');

const events = await cdp.ev('window.__rm2.stop()');

// 分析：第一遍物化的 index 集合；第二遍是否再次物化
const matPhase1 = new Set();
const matPhase2 = new Set();
for (const e of events) {
  if (e.kind === 'materialize') {
    if (e.phase === 1) matPhase1.add(e.idx);
    else if (e.phase === 2) matPhase2.add(e.idx);
  }
}
// 第二遍物化里，哪些 index 第一遍已经物化过？
const repeated = [];
for (const idx of matPhase2) {
  if (matPhase1.has(idx)) repeated.push(idx);
}
repeated.sort((a, b) => a - b);

// ★ A/B 类区分：
//   按时间序对每个 index 建事件序列。第二次 materialize 之前是否有 placeholder-removed？
//   有 => A 类（被淘汰后重访，允许）；无 => B 类（未淘汰却重复物化，bug）
const evByIdx = {};
for (const e of events) {
  if (e.kind !== 'materialize' && e.kind !== 'placeholder-removed') continue;
  if (!evByIdx[e.idx]) evByIdx[e.idx] = [];
  evByIdx[e.idx].push(e);
}
const phase2MatEvents = events.filter(e => e.kind === 'materialize' && e.phase === 2);
const classA = new Set();   // 被淘汰后重物化（允许）
const classB = new Set();   // 未淘汰却重复物化（bug）
for (const me of phase2MatEvents) {
  const hist = evByIdx[me.idx] || [];
  // 找到该 materialize 事件在 hist 中的位置
  const meIdx = hist.indexOf(me);
  // 看它之前最近一次"该 index 的 materialize"（第一次物化）之后，是否有 placeholder-removed
  let sawEvict = false;
  for (let k = meIdx - 1; k >= 0; k--) {
    const h = hist[k];
    if (h.kind === 'placeholder-removed') { sawEvict = true; }
    if (h.kind === 'materialize' && h.phase === 1) { break; }  // 追到第一次物化即停
  }
  if (sawEvict) classA.add(me.idx);
  else classB.add(me.idx);
}

console.log('=== 回滚重复物化复现（含 A/B 类区分）===');
console.log('  第一遍物化 index 数: ' + matPhase1.size);
console.log('  第二遍物化 index 数: ' + matPhase2.size);
console.log('  第二遍中"第一遍已物化"的 index 数: ' + repeated.length);
console.log('');
console.log('  ★ A 类（被淘汰后重访）：' + classA.size + ' 个  ← 允许（淘汰设计内）');
console.log('  ★ B 类（未淘汰却重复物化）：' + classB.size + ' 个  ← 真 bug，必须 0');
if (typeof mjxAfterDown === 'number' && typeof mjxAfterUp === 'number') {
  console.log('  mjx: 滚到底 ' + mjxAfterDown + ' → 滚回顶 ' + mjxAfterUp + '（+' + (mjxAfterUp - mjxAfterDown) + '）');
}
console.log('');
console.log('  ★ 最终判定：' + (classB.size === 0 ? '✅ P2 通过（B 类 = 0）' : '❌ P2 不过（B 类 = ' + classB.size + '）'));

if (classB.size) {
  const bArr = Array.from(classB).sort((a, b) => a - b);
  console.log('  B 类 index 样本（前 30）: ' + JSON.stringify(bArr.slice(0, 30)));
  console.log('  B 类事件时间线（每个 index 的完整序列）:');
  let shownB = 0;
  for (const idx of bArr) {
    if (shownB >= 12) break;
    const hist = (evByIdx[idx] || []).map(e => (e.kind === 'materialize' ? 'mat' : 'evict') + '@' + e.t + 'ms(p' + e.phase + ')');
    console.log('    idx=' + idx + ': ' + hist.join(' → '));
    shownB++;
  }
}

const out = { head: '4e401d8c', doc: DOC,
  matPhase1: matPhase1.size, matPhase2: matPhase2.size, repeatedCount: repeated.length,
  classA: classA.size, classB: classB.size,
  classBIdx: Array.from(classB).sort((a, b) => a - b).slice(0, 200),
  mjxDown: mjxAfterDown, mjxUp: mjxAfterUp,
  events: events.slice(0, 1000) };
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__REPEAT__' + JSON.stringify({ p1: matPhase1.size, p2: matPhase2.size, repeated: repeated.length,
  classA: classA.size, classB: classB.size, mjxDown: mjxAfterDown, mjxUp: mjxAfterUp }));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
