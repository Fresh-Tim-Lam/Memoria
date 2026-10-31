/**
 * 诊断：scroll-idle sync materialize 为何 0 次
 *   1. _setupLazyScrollMaterialization 是否被调用（IO 是否建立）
 *   2. scroll 事件是否触发
 *   3. _lazySyncMaterializeViewport 是否被执行、返回值
 */
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
const DOC = process.argv[3] || '教材/08_第8章_差错控制编码.md';

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
  if (/lazy|scroll/i.test(txt)) logs.push(txt);
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

// 装 scroll 事件计数器（在应用绑定之前/之后都能数到）
await cdp.ev(`(function(){
  window.__sc = { scrollEvents: 0, syncCalls: 0, syncLogs: [] };
  var pane = document.getElementById('preview-pane');
  if (pane) pane.addEventListener('scroll', function(){ window.__sc.scrollEvents++; }, { passive: true });
  return 1;
})()`);

await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
// 等首屏
for (let k = 0; k < 100; k++) {
  await sleep(200);
  const ph = await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); if(!p)return -1; var pr=p.getBoundingClientRect(); var n=0; p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;}); return n; })()`);
  if (ph === 0) break;
}
await sleep(1500);

console.log('=== 打开后状态 ===');
const st = await cdp.ev(`(function(){
  var p = document.getElementById('preview-pane');
  var pv = document.getElementById('preview');
  return {
    paneExists: !!p, previewExists: !!pv,
    previewParentId: pv && pv.parentElement ? pv.parentElement.id : null,
    paneScrollHeight: p ? p.scrollHeight : -1,
    paneClientHeight: p ? p.clientHeight : -1,
    phTotal: pv ? pv.querySelectorAll('.-pv-placeholder').length : -1,
    scrollEvents: window.__sc.scrollEvents
  };
})()`);
console.log('  ' + JSON.stringify(st));
console.log('');
console.log('  ★ preview.parentElement.id = ' + st.previewParentId);
console.log('    _bindLazyScrollIdleSync 绑的是 preview.parentElement || preview');
console.log('    ⇒ 绑定目标 = ' + (st.previewParentId || '(preview 自身)'));

// 触发一次滚动，看 scroll 事件是否被捕获
logs.length = 0;
await cdp.ev('window.__sc.scrollEvents = 0');
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop = (p.scrollHeight-p.clientHeight)*0.3; return 1; })()`);
await sleep(1500);

const after = await cdp.ev(`(function(){
  var p = document.getElementById('preview-pane');
  var pr = p.getBoundingClientRect(); var n=0;
  p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;});
  return { scrollEvents: window.__sc.scrollEvents, viewportPh: n, scrollTop: Math.round(p.scrollTop) };
})()`);
console.log('');
console.log('=== 滚到 30% 后 ===');
console.log('  ' + JSON.stringify(after));
console.log('');
console.log('=== 期间的 lazy/scroll 日志 ===');
logs.forEach(l => console.log('  ' + l.slice(0, 150)));
const syncLogs = logs.filter(l => /scroll-idle sync/i.test(l));
console.log('');
console.log('★ scroll-idle sync materialize 日志数: ' + syncLogs.length);
console.log('★ scroll 事件数: ' + after.scrollEvents);
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
