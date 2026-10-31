/**
 * task-63 50% 异常点专项诊断
 *
 * 在拖到 50% 位置的过程中，高频采样：
 *   - MemoriaScheduler.counters() 快照（scheduled/executed/dropped/budget_exceeded/slice_count/frames_used）
 *   - _lazyMathQueue 长度（通过 -math-pending 数量代替）
 *   - 源码态帧数 / ph 数量
 * 同时捕获 [job] / lazy 日志
 *
 * 用法: node perf_50pct_forensics.mjs <port> <out.json> [target]
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

// 日志捕获（含 [job]）
const logs = [];
cdp.ws.addEventListener('message', (e) => {
  let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : String(e.data)); } catch { return; }
  if (m.method !== 'Runtime.consoleAPICalled') return;
  const args = (m.params && m.params.args) || [];
  const txt = args.map(a => a.value === undefined ? (a.description || '') : String(a.value)).join(' ');
  if (/job|lazy|sched|typeset|materializ|drop|epoch/i.test(txt)) logs.push({ t: Date.now(), txt });
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// 探针：scheduler counters + 队列 + 源码态，全部在页面内 rAF 采样
await cdp.ev(`(function(){
  if (window.__fz) return 1;
  var F = {}; window.__fz = F;
  F.pane = function(){ return document.getElementById('preview-pane'); };
  F.sample = function(){
    var p = F.pane(); if (!p) return null;
    var pr = p.getBoundingClientRect();
    var paneArea = p.clientHeight > 0 ? p.clientHeight : 1;
    var mjx = 0, ph = 0, rawArea = 0, rawCount = 0, pending = 0;
    p.querySelectorAll('mjx-container').forEach(function(e){ var r=e.getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) mjx++; });
    p.querySelectorAll('.-pv-placeholder').forEach(function(e){ var r=e.getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) ph++; });
    // -math-pending 数量（全篇，作为"待排版"代理）
    var cc = document.querySelector('#preview .-preview-content') || document.getElementById('preview');
    if (cc) pending = cc.querySelectorAll('.-math-pending').length;
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
    // scheduler counters
    var sc = null;
    try {
      var S = window.MemoriaScheduler;
      if (S) {
        var c = (typeof S.counters === 'function') ? S.counters() : null;
        var st = (typeof S.status === 'function') ? S.status() : null;
        sc = { counters: c, status: st };
      }
    } catch (e) { sc = { err: String(e && e.message) }; }
    return { mjx: mjx, ph: ph, rawCount: rawCount, rawArea: +(Math.min(1, rawArea/paneArea)).toFixed(3),
             pending: pending, sc: sc };
  };
  F.start = function(){
    F.on = true; F.t0 = performance.now(); F.series = [];
    (function tick(){
      if (!F.on) return;
      var s = F.sample();
      if (s) { s.t = +(performance.now() - F.t0).toFixed(0); F.series.push(s); }
      requestAnimationFrame(tick);
    })();
  };
  F.stop = function(){ F.on = false; return F.series; };
  // 单独探测 scheduler API 形状
  F.apiShape = function(){
    var S = window.MemoriaScheduler;
    if (!S) return { err: 'no MemoriaScheduler' };
    var keys = []; try { for (var k in S) keys.push(k); } catch(e){}
    var out = { keys: keys };
    try { if (typeof S.counters === 'function') out.counters = S.counters(); } catch(e) { out.countersErr = String(e && e.message); }
    try { if (typeof S.status === 'function') out.status = S.status(); } catch(e) { out.statusErr = String(e && e.message); }
    return out;
  };
  return 1;
})()`);

const apiShape = await cdp.ev('window.__fz.apiShape()');
console.log('=== MemoriaScheduler API 形状 ===');
console.log('  keys: ' + JSON.stringify(apiShape.keys || apiShape.err));
console.log('  counters: ' + JSON.stringify(apiShape.counters));
console.log('  status: ' + JSON.stringify(apiShape.status));

// 打开 + 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
for (let k = 0; k < 150; k++) { await sleep(150); const ph = await cdp.ev(`(function(){var p=document.getElementById('preview-pane');if(!p)return -1;var pr=p.getBoundingClientRect();var n=0;p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect();if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;});return n;})()`); if (ph === 0) break; }
await sleep(1200);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
await sleep(2500);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
await sleep(2000);

const before = await cdp.ev('window.__fz.apiShape()');
console.log('');
console.log('=== 测试前 counters ===');
console.log('  ' + JSON.stringify(before.counters));

logs.length = 0;
await cdp.ev('window.__fz.start()');
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(TARGET * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}
await sleep(6000);
const series = await cdp.ev('window.__fz.stop()');
const after = await cdp.ev('window.__fz.apiShape()');

console.log('');
console.log('=== 测试后 counters ===');
console.log('  ' + JSON.stringify(after.counters));
console.log('');
console.log('=== counters 增量 ===');
try {
  const b = before.counters || {}, a = after.counters || {};
  const delta = {};
  for (const k of Object.keys(a)) {
    if (typeof a[k] === 'number' && typeof b[k] === 'number') delta[k] = a[k] - b[k];
  }
  console.log('  ' + JSON.stringify(delta));
  if (delta.dropped > 0) console.log('  ⚠️ dropped=' + delta.dropped + ' 需检查是否 epoch 误丢');
  if (delta.budget_exceeded > 0) console.log('  ℹ️ budget_exceeded=' + delta.budget_exceeded + '（跨帧续跑，正常）');
} catch (e) { console.log('  计算失败: ' + e.message); }

// 找最长连续源码态段
const s = series || [];
let runs = []; let cur = null;
for (const x of s) {
  if (x.rawCount > 0) { if (!cur) cur = []; cur.push(x); }
  else if (cur) { runs.push(cur); cur = null; }
}
if (cur) runs.push(cur);
runs.sort((a, b) => (b[b.length-1].t - b[0].t) - (a[a.length-1].t - a[0].t));

console.log('');
console.log('=== 最长连续源码态段（前 3）===');
runs.slice(0, 3).forEach((r, i) => {
  console.log('  段' + (i+1) + ': t=' + r[0].t + '–' + r[r.length-1].t + 'ms (' + (r[r.length-1].t - r[0].t) + 'ms)');
  // 打印该段内 counters 变化
  const first = r[0], last = r[r.length-1];
  console.log('    起始: raw=' + first.rawCount + ' ph=' + first.ph + ' pending=' + first.pending + ' mjx=' + first.mjx);
  console.log('    结束: raw=' + last.rawCount + ' ph=' + last.ph + ' pending=' + last.pending + ' mjx=' + last.mjx);
  if (first.sc && first.sc.counters && last.sc && last.sc.counters) {
    const d = {};
    for (const k of Object.keys(last.sc.counters)) {
      if (typeof last.sc.counters[k] === 'number' && typeof first.sc.counters[k] === 'number')
        d[k] = last.sc.counters[k] - first.sc.counters[k];
    }
    console.log('    段内 counters 增量: ' + JSON.stringify(d));
  }
  // 段内每 10 帧采样
  console.log('    段内采样（每 ~10 帧）:');
  for (let j = 0; j < r.length; j += Math.max(1, Math.floor(r.length / 8))) {
    const x = r[j];
    const c = x.sc && x.sc.counters ? x.sc.counters : {};
    console.log('      t=' + String(x.t).padStart(4) + 'ms raw=' + String(x.rawCount).padStart(2) +
      ' ph=' + String(x.ph).padStart(2) + ' pending=' + String(x.pending).padStart(3) +
      ' mjx=' + String(x.mjx).padStart(3) +
      ' | exec=' + (c.executed != null ? c.executed : '?') + ' drop=' + (c.dropped != null ? c.dropped : '?') +
      ' bud=' + (c.budget_exceeded != null ? c.budget_exceeded : '?'));
  }
});

// 日志统计
console.log('');
console.log('=== 日志统计 ===');
const jobLogs = logs.filter(l => /\[job\]/.test(l.txt));
const dropLogs = logs.filter(l => /drop|stale|epoch/i.test(l.txt));
console.log('  [job] 日志: ' + jobLogs.length);
console.log('  drop/stale/epoch 日志: ' + dropLogs.length);
if (dropLogs.length) dropLogs.slice(0, 5).forEach(l => console.log('    ' + l.txt.slice(0, 120)));
console.log('  lazy/typeset 日志样本（最后 10）:');
logs.filter(l => /lazy|typeset/i.test(l.txt)).slice(-10).forEach(l => console.log('    ' + l.txt.slice(0, 130)));

const out = { head: '4e401d8c', doc: DOC, target: TARGET,
  apiShape, countersBefore: before.counters, countersAfter: after.counters,
  series: s.slice(0, 400), logs: logs.map(l => l.txt).slice(0, 300) };
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__FZ__' + JSON.stringify({
  before: before.counters, after: after.counters,
  jobLogs: jobLogs.length, dropLogs: dropLogs.length }));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
