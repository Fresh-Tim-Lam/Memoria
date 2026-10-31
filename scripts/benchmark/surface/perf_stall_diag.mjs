/**
 * task-63：物化停滞诊断
 *
 * 假定：_lazyFlushNow 内某处抛未捕获异常 ⇒ 余量已回队列但 _lazyScheduleFlush() 执行不到 ⇒ 永久停滞。
 *
 * 诊断项：
 *  1. 全程抓 Runtime.exceptionThrown + console.error，记录时间戳
 *  2. 记录 ph 序列（每 200ms 采样），找"第一次不再减少"的时刻
 *  3. 对比异常时刻与停滞时刻
 *  4. 停滞时：视口占位块是否在 DOM、data--block-index 是否异常
 *  5. 抓 lazy 相关日志，看 flush/capped 是否停止
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
const DOC = process.argv[4] || '教材/03_第3章_模拟信号的数字编码.md';

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Log.enable').catch(() => {});

// ── 抓异常 + console ──
const events = [];
const T0 = Date.now();
cdp.ws.addEventListener('message', (e) => {
  let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : String(e.data)); } catch { return; }
  const t = Date.now() - T0;
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params && m.params.exceptionDetails;
    events.push({ t, kind: 'exception',
      text: String((d && d.exception && (d.exception.description || d.exception.value)) || (d && d.text) || '').slice(0, 400) });
  }
  if (m.method === 'Runtime.consoleAPICalled') {
    const args = (m.params && m.params.args) || [];
    const txt = args.map(a => a.value === undefined ? (a.description || '') : String(a.value)).join(' ');
    const type = m.params && m.params.type;
    if (type === 'error' || /lazy|flush|materializ|typeset/i.test(txt)) {
      events.push({ t, kind: 'console-' + type, text: txt.slice(0, 300) });
    }
  }
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

// 安装 ph 采样器
await cdp.ev(`(function(){
  window.__phSeries = [];
  window.__phOn = true;
  function tick(){
    if(!window.__phOn) return;
    var pv = document.getElementById('preview');
    var cc = pv ? (pv.querySelector('.-preview-content')||pv) : null;
    var pane = document.getElementById('preview-pane');
    var pr = pane ? pane.getBoundingClientRect() : null;
    var phView = -1;
    if (cc && pr) { phView = 0; cc.querySelectorAll('.-pv-placeholder').forEach(function(e){ var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) phView++; }); }
    window.__phSeries.push({
      t: Math.round(performance.now()),
      phTotal: cc ? cc.querySelectorAll('.-pv-placeholder').length : -1,
      phView: phView,
      st: pane ? Math.round(pane.scrollTop) : -1
    });
    setTimeout(tick, 200);
  }
  tick();
  return 1;
})()`);

const stepLog = [];
// 打开
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
await sleep(4000);
stepLog.push({ step: 'open', t: Date.now() - T0, ph: await cdp.ev(`(function(){ var pv=document.getElementById('preview'); var cc=pv?(pv.querySelector('.-preview-content')||pv):null; return cc?cc.querySelectorAll('.-pv-placeholder').length:-1; })()`) });

// 滚动序列（模拟门禁）
for (const pct of [0.25, 0.5, 0.75, 1.0]) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${pct}; return 1; })()`);
  await sleep(3000);
  const ph = await cdp.ev(`(function(){ var pv=document.getElementById('preview'); var cc=pv?(pv.querySelector('.-preview-content')||pv):null; return cc?cc.querySelectorAll('.-pv-placeholder').length:-1; })()`);
  stepLog.push({ step: 'scroll' + pct, t: Date.now() - T0, ph });
}
// 跳转
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
await sleep(800);
await cdp.ev(`(function(){ try { window.MemoriaApp.scrollToSrcLine("preview", 1169); } catch(e){ return String(e.message); } return 1; })()`);
await sleep(4000);
const phAfterJump = await cdp.ev(`(function(){ var pv=document.getElementById('preview'); var cc=pv?(pv.querySelector('.-preview-content')||pv):null; return cc?cc.querySelectorAll('.-pv-placeholder').length:-1; })()`);
stepLog.push({ step: 'jump', t: Date.now() - T0, ph: phAfterJump });

// 再滚一轮（复现 R2 雪崩）
for (const pct of [0.25, 0.5, 0.75, 1.0]) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${pct}; return 1; })()`);
  await sleep(3000);
  const ph = await cdp.ev(`(function(){ var pv=document.getElementById('preview'); var cc=pv?(pv.querySelector('.-preview-content')||pv):null; return cc?cc.querySelectorAll('.-pv-placeholder').length:-1; })()`);
  stepLog.push({ step: 'R2-scroll' + pct, t: Date.now() - T0, ph });
}

// 停滞时刻诊断
const diag = await cdp.ev(`(function(){
  var pv = document.getElementById('preview');
  var cc = pv ? (pv.querySelector('.-preview-content')||pv) : null;
  var pane = document.getElementById('preview-pane');
  var pr = pane ? pane.getBoundingClientRect() : null;
  var out = { phTotal: cc ? cc.querySelectorAll('.-pv-placeholder').length : -1, viewportPlaceholders: [] };
  if (cc && pr) {
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) {
        if (out.viewportPlaceholders.length < 8) {
          out.viewportPlaceholders.push({
            bi: e.getAttribute('data--block-index'),
            sl: e.getAttribute('data--src-line'),
            connected: e.isConnected,
            h: Math.round(r.height),
            inDom: !!e.parentNode
          });
        }
      }
    });
  }
  out.series = (window.__phSeries || []).slice(-30);
  out.seriesLen = (window.__phSeries || []).length;
  return out;
})()`);
await cdp.ev('(function(){ window.__phOn = false; return 1; })()');

// 找停滞时刻：ph 序列里第一次"之后不再减少"
const series = diag.series || [];
let stallAt = null;
for (let i = 0; i < series.length - 5; i++) {
  const rest = series.slice(i + 1);
  if (rest.every(x => x.phTotal >= series[i].phTotal)) { stallAt = series[i]; break; }
}

const out = {
  head: '9de16a4e', doc: DOC, mode: 'stall-diagnosis',
  stepLog,
  finalPh: diag.phTotal,
  viewportPlaceholders: diag.viewportPlaceholders,
  stallPoint: stallAt,
  phSeriesTail: series,
  phSeriesLen: diag.seriesLen,
  events,
  exceptionCount: events.filter(e => e.kind === 'exception').length,
  errorCount: events.filter(e => e.kind === 'console-error').length,
};
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');

console.log('=== stepLog（每次操作后的 ph 总数）===');
for (const s of stepLog) console.log('  ' + String(s.t).padStart(6) + 'ms  ' + s.step.padEnd(14) + ' ph=' + s.ph);
console.log('');
console.log('=== 异常/错误 ===');
const exc = events.filter(e => e.kind === 'exception');
const errs = events.filter(e => e.kind === 'console-error');
console.log('  exception: ' + exc.length + '  console.error: ' + errs.length);
exc.slice(0, 5).forEach(e => console.log('   [EXC ' + e.t + 'ms] ' + e.text.slice(0, 200)));
errs.slice(0, 5).forEach(e => console.log('   [ERR ' + e.t + 'ms] ' + e.text.slice(0, 200)));
console.log('');
console.log('=== 停滞点 ===');
console.log('  ' + JSON.stringify(stallAt));
console.log('');
console.log('=== 视口占位块样本 ===');
console.log('  ' + JSON.stringify(diag.viewportPlaceholders.slice(0, 5)));
console.log('');
console.log('=== lazy 日志（最后 12 条）===');
const lazyLogs = events.filter(e => /lazy/i.test(e.text));
lazyLogs.slice(-12).forEach(e => console.log('   [' + e.t + 'ms] ' + e.text.slice(0, 160)));
console.log('   (lazy 日志总数: ' + lazyLogs.length + ')');

console.log('');
console.log('__STALL__' + JSON.stringify({
  exceptionCount: exc.length,
  errorCount: errs.length,
  finalPh: diag.phTotal,
  stallPh: stallAt ? stallAt.phTotal : null,
  lazyLogCount: lazyLogs.length,
  stepLog,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
