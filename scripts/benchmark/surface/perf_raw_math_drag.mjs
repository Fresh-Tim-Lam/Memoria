/**
 * 拖拽过程中「公式源码态」量化（修正 v1 的时机错误）
 *
 * v1 错误：在"拖拽停止后"测 ⇒ 得到 0ms
 * v2 正确：在"拖拽过程中"高频采样（每 30ms），记录：
 *   - 视口内 mjx-container 数
 *   - 视口内"含 $ 的文本"（未排版公式源码）数
 *   - 源码态占视口面积比例
 *   - 源码态连续持续时长
 *
 * 用法: node perf_raw_math_drag.mjs <port> <out.json>
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
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';
const TARGET = Number(process.argv[5] || 0.8);

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

// 页面内采样器：在 rAF 里记录，避免 CDP 往返延迟
await cdp.ev(`(function(){
  if (window.__rm) return 1;
  var R = {}; window.__rm = R;
  R.sample = function(){
    var p = document.getElementById('preview-pane');
    if (!p) return null;
    var pr = p.getBoundingClientRect();
    var paneArea = p.clientHeight > 0 ? p.clientHeight : 1;
    var mjx = 0, rawEls = [], rawArea = 0, ph = 0, phArea = 0;
    // mjx
    p.querySelectorAll('mjx-container').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) mjx++;
    });
    // 占位块
    p.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      var vis = Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top);
      if (vis > 2) { ph++; phArea += vis; }
    });
    // 未排版公式源码：文本含 $ 且不在 mjx/pre/code 内
    var walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var t = node.nodeValue || '';
      if (t.indexOf('$') < 0) continue;
      var par = node.parentElement;
      if (!par) continue;
      if (par.closest('mjx-container') || par.closest('pre') || par.closest('code') || par.closest('.-pv-placeholder')) continue;
      var r = par.getBoundingClientRect();
      var vis = Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top);
      if (vis > 2) {
        rawEls.push(t.trim().slice(0, 40));
        rawArea += vis;
      }
    }
    return { mjx: mjx, rawCount: rawEls.length, rawAreaRatio: +(Math.min(1, rawArea / paneArea)).toFixed(3),
             ph: ph, phAreaRatio: +(Math.min(1, phArea / paneArea)).toFixed(3),
             rawSamples: rawEls.slice(0, 2) };
  };
  R.start = function(){
    R.on = true; R.t0 = performance.now(); R.series = [];
    (function tick(){
      if (!R.on) return;
      var s = R.sample();
      if (s) { s.t = +(performance.now() - R.t0).toFixed(0); R.series.push(s); }
      requestAnimationFrame(tick);
    })();
  };
  R.stop = function(){ R.on = false; return R.series; };
  return 1;
})()`);

// 打开 + 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
for (let k = 0; k < 150; k++) { await sleep(150); if (await cdp.ev('(function(){var p=document.getElementById("preview-pane");if(!p)return -1;var pr=p.getBoundingClientRect();var n=0;p.querySelectorAll(".-pv-placeholder").forEach(function(e){var r=e.getBoundingClientRect();if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;});return n;})()') === 0) break; }
await sleep(1200);
// 预热
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
await sleep(2500);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
await sleep(2000);

console.log('=== 拖拽到 ' + (TARGET * 100) + '% 过程中的公式源码态 ===');
await cdp.ev('window.__rm.start()');
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(TARGET * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}
// 拖完再持续采样 5 秒（看源码态多久消失）
await sleep(5000);
const series = await cdp.ev('window.__rm.stop()');

console.log('  采样帧数: ' + (series ? series.length : 0));
if (series && series.length) {
  // 源码态统计
  const withRaw = series.filter(s => s.rawCount > 0);
  const withRawArea = series.filter(s => s.rawAreaRatio > 0.1);
  const maxRawArea = series.reduce((a, b) => (b.rawAreaRatio > a.rawAreaRatio ? b : a), series[0]);
  const maxRawCount = series.reduce((a, b) => (b.rawCount > a.rawCount ? b : a), series[0]);

  // 最长连续"有源码态"时长
  let runStart = null, maxRun = 0;
  series.forEach(s => {
    if (s.rawCount > 0) { if (runStart === null) runStart = s.t; }
    else { if (runStart !== null) { const d = s.t - runStart; if (d > maxRun) maxRun = d; runStart = null; } }
  });
  if (runStart !== null) { const d = series[series.length - 1].t - runStart; if (d > maxRun) maxRun = d; }

  // 源码态面积 >10% 的连续时长
  let runStart2 = null, maxRun2 = 0;
  series.forEach(s => {
    if (s.rawAreaRatio > 0.1) { if (runStart2 === null) runStart2 = s.t; }
    else { if (runStart2 !== null) { const d = s.t - runStart2; if (d > maxRun2) maxRun2 = d; runStart2 = null; } }
  });
  if (runStart2 !== null) { const d = series[series.length - 1].t - runStart2; if (d > maxRun2) maxRun2 = d; }

  console.log('  ★ 有源码态的帧: ' + withRaw.length + '/' + series.length + ' (' + (withRaw.length * 100 / series.length).toFixed(0) + '%)');
  console.log('  ★ 源码态面积>10% 的帧: ' + withRawArea.length + '/' + series.length + ' (' + (withRawArea.length * 100 / series.length).toFixed(0) + '%)');
  console.log('  ★ 最长连续"有源码态"时长: ' + maxRun + 'ms');
  console.log('  ★ 最长连续"源码态面积>10%"时长: ' + maxRun2 + 'ms');
  console.log('  源码面积峰值: ' + (maxRawArea.rawAreaRatio * 100).toFixed(0) + '%  @t=' + maxRawArea.t + 'ms (rawCount=' + maxRawArea.rawCount + ', mjx=' + maxRawArea.mjx + ')');
  console.log('  源码块数峰值: ' + maxRawCount.rawCount + '  @t=' + maxRawCount.t + 'ms');
  console.log('');
  console.log('  序列（每 5 帧取一个，显示 t/rawCount/rawArea/mjx/ph）:');
  series.filter((s, i) => i % 5 === 0).forEach(s => {
    console.log('    t=' + String(s.t).padStart(5) + 'ms  raw=' + String(s.rawCount).padStart(2) +
      '  rawArea=' + (s.rawAreaRatio * 100).toFixed(0).padStart(3) + '%  mjx=' + String(s.mjx).padStart(3) +
      '  ph=' + String(s.ph).padStart(2) + (s.rawSamples.length ? '  e.g. ' + s.rawSamples[0] : ''));
  });

  const out = { head: 'b5044bdb', doc: DOC, target: TARGET,
    stats: { frames: series.length, withRaw: withRaw.length, withRawArea10: withRawArea.length,
             maxRawRunMs: maxRun, maxRawArea10RunMs: maxRun2,
             peakRawArea: maxRawArea.rawAreaRatio, peakRawCount: maxRawCount.rawCount },
    series };
  writeFileSync(outPath.replace('.json', '-rawmath.json'), JSON.stringify(out, null, 2), 'utf8');
  console.log('');
  console.log('__RAWMATH__' + JSON.stringify(out.stats));
}
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
