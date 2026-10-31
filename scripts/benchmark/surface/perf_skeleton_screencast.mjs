/**
 * 骨架可见性验证 v2：用 Page.startScreencast 持续推帧
 *
 * v1 失败原因：cdp.ev 往返延迟 ~20-40ms，物化太快 ⇒ 追不上 cov 高的瞬间
 * v2 方案：拖拽前开 screencast，浏览器按帧推图 ⇒ 帧率天然对齐渲染帧
 *          页面内 rAF 循环记录每帧 cov，按时间戳与 screencast 帧匹配
 *
 * 用法: node perf_skeleton_screencast.mjs <port> <outdir> <label>
 */
import { writeFileSync, mkdirSync } from 'node:fs';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); this.frames = []; this.meta = [];
    ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; }
    if (m.method === 'Page.screencastFrame') { this.frames.push({ data: m.params.data, ts: m.params.metadata && m.params.metadata.timestamp, seq: m.params.metadata && m.params.metadata.timestamp }); this.send('Page.screencastFrameAck', { sessionId: m.params.sessionId }).catch(() => {}); return; }
    if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
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

// 页面内每帧记录 cov（rAF 对齐渲染帧）
await cdp.ev(`(function(){
  if (window.__sc2) return 1;
  var S = {}; window.__sc2 = S;
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
    return { placeholderBg: cs ? cs.backgroundColor : null,
             bodyBg: getComputedStyle(document.body).backgroundColor,
             theme: document.documentElement.getAttribute('data-theme') || '(none)',
             phCount: cc ? cc.querySelectorAll('.-pv-placeholder').length : -1 };
  };
  S.watch = { on:false, series:[] };
  S.startWatch = function(){
    S.watch.on = true; S.watch.series = []; S.watch.t0 = performance.now();
    (function tick(){
      if (!S.watch.on) return;
      var t = performance.now();
      S.watch.series.push({ t: +(t - S.watch.t0).toFixed(1), wall: +t.toFixed(1), cov: +S.cov().toFixed(3), ph: S.vph() });
      requestAnimationFrame(tick);
    })();
  };
  S.stopWatch = function(){ S.watch.on = false; return S.watch.series; };
  return 1;
})()`);

const info = await cdp.ev('window.__sc2.info()');
console.log('=== 主题与骨架色 ===');
console.log('  theme=' + info.theme + '  bodyBg=' + info.bodyBg + '  phCount=' + info.phCount);

// 打开 + 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
for (let k = 0; k < 150; k++) { await sleep(150); if (await cdp.ev('window.__sc2.vph()') === 0) break; }
await sleep(1200);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sc2.vph()') === 0) break; }
await sleep(600);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sc2.vph()') === 0) break; }
await sleep(900);

// ★ 开 screencast
cdp.frames.length = 0;
await cdp.send('Page.startScreencast', { format: 'png', quality: 80, maxWidth: 1264, maxHeight: 821, everyNthFrame: 1 }).catch(e => console.log('  ⚠️ screencast 失败: ' + e.message));
await sleep(150);

// 开页面内 cov 记录
await cdp.ev('window.__sc2.startWatch()');
// 拖到 80%
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}
await sleep(3000);
await cdp.send('Page.stopScreencast').catch(() => {});
const series = await cdp.ev('window.__sc2.stopWatch()');

console.log('');
console.log('=== screencast 帧数: ' + cdp.frames.length + ' ===');
console.log('=== cov 采样点数: ' + (series ? series.length : 0) + ' ===');
if (series && series.length) {
  const withCov = series.filter(s => s.cov > 0.3);
  console.log('  cov>30% 的帧数: ' + withCov.length);
  const peak = series.reduce((a, b) => (b.cov > a.cov ? b : a), series[0]);
  console.log('  峰值 cov=' + (peak.cov * 100).toFixed(1) + '% @t=' + peak.t + 'ms ph=' + peak.ph);
  // 打印前 25 个高 cov 点
  console.log('  高 cov 采样（前 20）:');
  withCov.slice(0, 20).forEach(s => console.log('    t=' + s.t + 'ms  cov=' + (s.cov * 100).toFixed(0) + '%  ph=' + s.ph));
}

// 保存所有 screencast 帧，并与 cov 时间轴对齐（用相对顺序近似）
const saved = [];
if (cdp.frames.length) {
  // 取中间帧（拖拽过程中）
  const idxs = [0, Math.floor(cdp.frames.length / 4), Math.floor(cdp.frames.length / 2), Math.floor(cdp.frames.length * 3 / 4), cdp.frames.length - 1];
  for (const i of idxs) {
    const f = cdp.frames[i];
    if (!f) continue;
    const p = outdir + '/' + LABEL + '-frame' + String(i).padStart(2, '0') + '.png';
    writeFileSync(p, Buffer.from(f.data, 'base64'));
    // 帧对应的 cov 采样（按比例映射）
    const covIdx = series && series.length ? Math.min(series.length - 1, Math.round(i / cdp.frames.length * series.length)) : 0;
    const covAt = series && series[covIdx] ? series[covIdx].cov : null;
    saved.push({ frameIdx: i, path: p, approxCov: covAt });
    console.log('  保存帧 ' + i + ' → ' + p + '  (近似 cov=' + (covAt != null ? (covAt * 100).toFixed(0) + '%' : '?') + ')');
  }
}

const out = { head: 'b5044bdb', label: LABEL, info,
  frameCount: cdp.frames.length, seriesLen: series ? series.length : 0,
  covSeries: series ? series.slice(0, 300) : [], savedFrames: saved };
writeFileSync(outdir + '/screencast-' + LABEL + '.json', JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__SC__' + JSON.stringify({ frames: cdp.frames.length, seriesLen: series ? series.length : 0,
  peakCov: series ? Math.max(...series.map(s => s.cov)) : null, saved: saved.length }));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
