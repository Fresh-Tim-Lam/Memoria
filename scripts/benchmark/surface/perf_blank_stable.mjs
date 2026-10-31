/**
 * task-63 稳定版视口空白测量：多次取中位数
 *
 * 背景：同一版本连续两次测得 763ms vs 1649ms（差 2.2 倍）⇒ 单次测量噪声过大，
 *       不足以支撑"修复是否有效"的判定。
 *
 * 做法：
 *   同一实例内跑 N 轮（每轮：回到顶部 → 等稳定 → 10帧扫到 80% → 采样 → 等稳定）
 *   报告：每轮原始值 + 中位数 + min/max + 变异系数
 *
 * 用法: node perf_blank_stable.mjs <port> <out.json> [rounds]
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
const ROUNDS = Number(process.argv[4] || 5);
const DOC = process.argv[5] || '教材/08_第8章_差错控制编码.md';

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
  if (/lazy|typeset|defer|materializ|flush/i.test(txt)) logs.push(txt);
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

// 探针
await cdp.ev(`(function(){
  if (window.__sb) return 1;
  var S = { on:false }; window.__sb = S;
  S.pane = function(){ return document.getElementById('preview-pane'); };
  S.vph = function(){
    var p = S.pane(); if (!p) return -1;
    var pr = p.getBoundingClientRect(); var n = 0;
    var cc = document.querySelector('#preview .-preview-content') || document.getElementById('preview');
    if (!cc) return -1;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) n++;
    });
    return n;
  };
  S.totalPh = function(){
    var cc = document.querySelector('#preview .-preview-content') || document.getElementById('preview');
    return cc ? cc.querySelectorAll('.-pv-placeholder').length : -1;
  };
  S.start = function(){
    S.on = true; S.maxBlank = 0; S.samples = []; S.t0 = performance.now();
    S.gaps = []; S.lastFrame = performance.now();
    // 帧采样（用于 max 帧 + >800ms 长帧判定）
    (function fr(){
      if (!S.on) return;
      var n = performance.now();
      S.gaps.push(+(n - S.lastFrame).toFixed(1));
      S.lastFrame = n;
      requestAnimationFrame(fr);
    })();
    var blankStart = null;
    (function poll(){
      if (!S.on) return;
      var now = performance.now();
      var ph = S.vph();
      S.samples.push({ t: Math.round(now - S.t0), ph: ph });
      if (ph > 0) { if (blankStart === null) blankStart = now; }
      else if (blankStart !== null) { var d = now - blankStart; if (d > S.maxBlank) S.maxBlank = d; blankStart = null; }
      setTimeout(poll, 50);
    })();
  };
  S.stop = function(){
    S.on = false;
    var run = 0, cur = 0;
    S.samples.forEach(function(s){ if (s.ph > 0) { cur++; if (cur > run) run = cur; } else cur = 0; });
    var g = (S.gaps || []).filter(function(x){ return isFinite(x) && x > 0; }).sort(function(a,b){ return a-b; });
    var n = g.length;
    return { maxBlankMs: Math.round(S.maxBlank), blankSamples: S.samples.filter(function(s){return s.ph>0;}).length,
             totalSamples: S.samples.length, longestRunMs: run * 50,
             frameMax: n ? +g[n-1].toFixed(1) : null,
             frameP95: n ? +g[Math.floor(n*0.95)].toFixed(1) : null,
             frameOver100: g.filter(function(x){return x>100;}).length,
             frameOver800: g.filter(function(x){return x>800;}).length,
             topGaps: g.slice(-5).reverse() };
  };
  return 1;
})()`);

// 打开文档
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
// 等首屏稳定
for (let k = 0; k < 150; k++) { await sleep(200); if (await cdp.ev('window.__sb.vph()') === 0) break; }
await sleep(2000);
console.log('首屏稳定，开始 ' + ROUNDS + ' 轮测量');

const rounds = [];
for (let r = 1; r <= ROUNDS; r++) {
  // ★ 每轮必须重置到"目标区域未物化"状态：
  //   重开文档 ⇒ 重走惰性路径 ⇒ 全文回到占位
  //   （实测教训：同实例连续拖到同一位置，只有 R1 有空白、R2-R5 全 0ms
  //     ⇒ 若不重开，"取中位数"会被 4 个 0 掩盖真问题）
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
  for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
  // 等首屏物化完
  for (let k = 0; k < 150; k++) { await sleep(150); if (await cdp.ev('window.__sb.vph()') === 0) break; }
  await sleep(1200);

  // 预热：拖到 40% 再回顶（让 MathJax/字体/布局缓存就绪，统一各轮起点状态）
  logs.length = 0;
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
  for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sb.vph()') === 0) break; }
  await sleep(800);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
  for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sb.vph()') === 0) break; }
  await sleep(1000);

  // 正式测量：拖到 80%（该区域此时仍未物化）
  logs.length = 0;
  await cdp.ev('window.__sb.start()');
  for (let s = 1; s <= 10; s++) {
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
    await sleep(16);
  }
  await sleep(5000);
  const res = await cdp.ev('window.__sb.stop()');
  const syncCount = logs.filter(l => /scroll-idle sync materialize/.test(l)).length;
  // defer 日志真实文案：`[lazy] typeset DEFERRED for materialization: blocks=N (defer Xms)`
  const deferLogs = logs.filter(l => /typeset DEFERRED/i.test(l));
  const deferVals = deferLogs.map(l => {
    const m = l.match(/defer\s+(\d+)\s*ms/i); return m ? +m[1] : null;
  }).filter(x => x !== null).sort((a, b) => a - b);
  const batchVals = deferLogs.map(l => {
    const m = l.match(/blocks=(\d+)/i); return m ? +m[1] : null;
  }).filter(x => x !== null);
  const flushDelays = logs.filter(l => /flush delay/.test(l)).map(l => {
    const m = l.match(/=\s*(\d+)\s*ms/); return m ? +m[1] : null;
  }).filter(x => x !== null);
  const rd = { round: r, maxBlankMs: res.maxBlankMs, longestRunMs: res.longestRunMs,
    blankSamples: res.blankSamples, totalSamples: res.totalSamples,
    syncLogs: syncCount, flushDelayCount: flushDelays.length,
    flushDelayMax: flushDelays.length ? Math.max(...flushDelays) : null,
    deferCount: deferLogs.length,
    deferMedian: deferVals.length ? deferVals[Math.floor(deferVals.length / 2)] : null,
    deferMax: deferVals.length ? deferVals[deferVals.length - 1] : null,
    deferBatchMedian: batchVals.length ? batchVals.slice().sort((a, b) => a - b)[Math.floor(batchVals.length / 2)] : null,
    deferNear1000: deferVals.filter(x => x >= 900).length,
    frameMax: res.frameMax, frameP95: res.frameP95,
    frameOver100: res.frameOver100, frameOver800: res.frameOver800,
    topGaps: res.topGaps };
  rounds.push(rd);
  console.log('  R' + r + ': 空白=' + rd.maxBlankMs + 'ms 最长连续=' + rd.longestRunMs + 'ms 空白采样=' + rd.blankSamples + '/' + rd.totalSamples +
    '  sync=' + rd.syncLogs + '  defer=' + rd.deferCount + '次(med ' + rd.deferMedian + 'ms/max ' + rd.deferMax + 'ms, ≈1s:' + rd.deferNear1000 + ')' +
    '  flushDelay(max)=' + rd.flushDelayMax + 'ms  帧max=' + rd.frameMax + 'ms >800ms:' + rd.frameOver800);
  if (deferLogs.length) console.log('      defer样本: ' + deferLogs.slice(0, 2).map(x => x.slice(0, 100)).join(' | '));
}

// 统计
const vals = rounds.map(r => r.maxBlankMs).sort((a, b) => a - b);
const med = vals[Math.floor(vals.length / 2)];
const mean = vals.reduce((s, x) => s + x, 0) / vals.length;
const sd = Math.sqrt(vals.reduce((s, x) => s + (x - mean) ** 2, 0) / vals.length);
const cv = mean > 0 ? (sd / mean) : 0;
const syncTotal = rounds.reduce((s, r) => s + r.syncLogs, 0);

console.log('');
console.log('=== 统计（' + ROUNDS + ' 轮）===');
console.log('  原始值: ' + JSON.stringify(vals));
console.log('  ★ 中位数: ' + med + 'ms   min=' + vals[0] + '  max=' + vals[vals.length - 1]);
console.log('  均值=' + mean.toFixed(0) + 'ms  sd=' + sd.toFixed(0) + 'ms  变异系数 CV=' + (cv * 100).toFixed(1) + '%' +
  (cv > 0.3 ? '  ⚠️ 噪声大（CV>30%）' : '  ✅ 稳定'));
console.log('  scroll-idle sync materialize 总日志数: ' + syncTotal + (syncTotal === 0 ? '  ⚠️ 仍未触发' : ''));
const deferTotal = rounds.reduce((s, r) => s + (r.deferCount || 0), 0);
const deferMedians = rounds.map(r => r.deferMedian).filter(x => x != null);
const deferMaxes = rounds.map(r => r.deferMax).filter(x => x != null);
const frameMaxes = rounds.map(r => r.frameMax).filter(x => x != null);
const over800 = rounds.reduce((s, r) => s + (r.frameOver800 || 0), 0);
console.log('  defer 总次数: ' + deferTotal +
  (deferTotal ? '  (median of medians=' + (deferMedians.length ? deferMedians.sort((a,b)=>a-b)[Math.floor(deferMedians.length/2)] : '-') +
    'ms, 各轮max=' + JSON.stringify(deferMaxes) + ', ≈1s 记录=' + rounds.reduce((s,r)=>s+(r.deferNear1000||0),0) + ')' : ''));
console.log('  帧 max 各轮: ' + JSON.stringify(frameMaxes) + '  >800ms 总次数=' + over800);

const out = { head: '40474734', doc: DOC, rounds: ROUNDS, raw: rounds,
  stats: { values: vals, median: med, min: vals[0], max: vals[vals.length - 1],
           mean: +mean.toFixed(0), sd: +sd.toFixed(0), cv: +cv.toFixed(3), syncLogTotal: syncTotal } };
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__STABLE__' + JSON.stringify(out.stats));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
