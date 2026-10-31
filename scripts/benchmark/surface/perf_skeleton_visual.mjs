/**
 * 骨架可见性体感验证（只看视觉，不看空白时长）
 *
 * 关键：在"视口骨架覆盖率最高"的瞬间抓图（不是固定等 200ms —— 那会物化完）
 * 做法：拖到底后立刻进入高频轮询（每 20ms 查 cov），cov 首次 >0.6 时立即抓图
 *
 * 输出：截图 + 视口中心区域平均亮度 + 与背景的差异
 *
 * 用法: node perf_skeleton_visual.mjs <port> <outdir> <label>
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
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
const outdir = process.argv[3] || 'artifacts/agent/verify/skeleton-visual';
const LABEL = process.argv[4] || 'b5044bdb';
const DOC = process.argv[5] || '教材/08_第8章_差错控制编码.md';
mkdirSync(outdir, { recursive: true });

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Page.enable').catch(() => {});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} try{ window.__MEMORIA_DEFER=false; }catch(e){} return 1; })()`);

await cdp.ev(`(function(){
  if (window.__sv) return 1;
  var S = {}; window.__sv = S;
  S.pane = function(){ return document.getElementById('preview-pane'); };
  S.cc = function(){ return document.querySelector('#preview .-preview-content') || document.getElementById('preview'); };
  S.vph = function(){
    var p = S.pane(), cc = S.cc(); if (!p || !cc) return -1;
    var pr = p.getBoundingClientRect(); var n = 0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) n++;
    });
    return n;
  };
  S.cov = function(){
    var p = S.pane(), cc = S.cc(); if (!p || !cc) return -1;
    var pr = p.getBoundingClientRect(); var h = 0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      var vis = Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top);
      if (vis > 2) h += vis;
    });
    return p.clientHeight > 0 ? Math.min(1, h / p.clientHeight) : -1;
  };
  S.info = function(){
    var cc = S.cc(); var ph = cc ? cc.querySelector('.-pv-placeholder') : null;
    var cs = ph ? getComputedStyle(ph) : null;
    var pr = S.pane() ? S.pane().getBoundingClientRect() : null;
    return { placeholderBg: cs ? cs.backgroundColor : null,
             bodyBg: getComputedStyle(document.body).backgroundColor,
             theme: document.documentElement.getAttribute('data-theme') || '(none)',
             paneRect: pr ? { x: Math.round(pr.left), y: Math.round(pr.top), w: Math.round(pr.width), h: Math.round(pr.height) } : null };
  };
  return 1;
})()`);

const info = await cdp.ev('window.__sv.info()');
console.log('=== 主题与骨架色 ===');
console.log('  theme=' + info.theme + '  bodyBg=' + info.bodyBg);
console.log('  placeholderBg=' + info.placeholderBg);
console.log('  paneRect=' + JSON.stringify(info.paneRect));

// 打开 + 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
for (let k = 0; k < 150; k++) { await sleep(150); if (await cdp.ev('window.__sv.vph()') === 0) break; }
await sleep(1200);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sv.vph()') === 0) break; }
await sleep(600);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sv.vph()') === 0) break; }
await sleep(900);

// 拖到 80%
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}

// ★ 高频轮询，cov 首次 >0.55 立即抓图（那是"骨架最满"的瞬间）
let captured = null;
const t0 = Date.now();
for (let t = 0; t < 60; t++) {
  await sleep(20);
  const cov = await cdp.ev('window.__sv.cov()');
  if (cov >= 0.55) {
    try {
      const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
      if (shot && shot.data) captured = { cov, tMs: Date.now() - t0, buf: Buffer.from(shot.data, 'base64') };
    } catch (e) { /* */ }
    break;
  }
  if (cov < 0.05 && t > 20) break;
}
// 若没抓到高覆盖，退而在 150ms 处抓一张
if (!captured) {
  const shot = await cdp.send('Page.captureScreenshot', { format: 'png' }).catch(() => null);
  const cov = await cdp.ev('window.__sv.cov()');
  if (shot && shot.data) captured = { cov, tMs: Date.now() - t0, buf: Buffer.from(shot.data, 'base64'), fallback: true };
}

const outPath = outdir + '/' + LABEL + '-skeleton.png';
if (captured) {
  writeFileSync(outPath, captured.buf);
  console.log('');
  console.log('=== 抓图 ===');
  console.log('  时机: t=' + captured.tMs + 'ms  cov=' + (captured.cov * 100).toFixed(1) + '%' + (captured.fallback ? ' (fallback)' : ''));
  console.log('  路径: ' + outPath);
} else {
  console.log('  ❌ 抓图失败');
}

// 等物化完再抓一张"加载完成"对照图
for (let k = 0; k < 100; k++) { await sleep(100); if (await cdp.ev('window.__sv.vph()') === 0) break; }
await sleep(800);
const shotDone = await cdp.send('Page.captureScreenshot', { format: 'png' }).catch(() => null);
const donePath = outdir + '/' + LABEL + '-loaded.png';
if (shotDone && shotDone.data) {
  writeFileSync(donePath, Buffer.from(shotDone.data, 'base64'));
  console.log('  对照图(加载完成): ' + donePath);
}

const out = { head: 'b5044bdb', label: LABEL, info,
  capture: captured ? { tMs: captured.tMs, cov: captured.cov, fallback: !!captured.fallback, path: outPath } : null,
  loadedShot: shotDone ? donePath : null };
writeFileSync(outdir + '/result-' + LABEL + '.json', JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__VIS__' + JSON.stringify({ cov: captured ? +captured.cov.toFixed(2) : null, tMs: captured ? captured.tMs : null,
  path: outPath, bg: info.placeholderBg }));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
