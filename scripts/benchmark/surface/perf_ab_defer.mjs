/**
 * task-63 0.4.7：deferral 同运行 A/B + 骨架覆盖率 + 截图
 *
 * ① 同实例内 A/B：关→开→开→关（避免跨运行系统性差异）
 * ② 骨架覆盖率：(视口内 placeholder 累加高度) / paneClientHeight
 * ③ 首次到达 80% 瞬间截图（人眼证据）
 *
 * 每测一次都：重开文档 → 预热(拖40%回顶) → 测拖到80%
 *
 * 用法: node perf_ab_defer.mjs <port> <outdir>
 */
import { writeFileSync, mkdirSync } from 'node:fs';
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
const outdir = process.argv[3] || 'artifacts/agent/verify/ab-defer';
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';
mkdirSync(outdir, { recursive: true });

// A/B 顺序：关→开→开→关
const SEQUENCE = [
  { label: 'A1-off', defer: false },
  { label: 'B1-on', defer: true },
  { label: 'B2-on', defer: true },
  { label: 'A2-off', defer: false },
];

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Page.enable').catch(() => {});

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

// 探针：视口占位 + 骨架覆盖率 + 帧
await cdp.ev(`(function(){
  if (window.__ab) return 1;
  var A = {}; window.__ab = A;
  A.pane = function(){ return document.getElementById('preview-pane'); };
  A.cc = function(){ return document.querySelector('#preview .-preview-content') || document.getElementById('preview'); };
  A.vph = function(){
    var p = A.pane(), cc = A.cc(); if (!p || !cc) return -1;
    var pr = p.getBoundingClientRect(); var n = 0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) n++;
    });
    return n;
  };
  // ★ 骨架覆盖率 = 视口内占位块累加高度 / 视口高度
  A.skeletonCov = function(){
    var p = A.pane(), cc = A.cc(); if (!p || !cc) return -1;
    var pr = p.getBoundingClientRect();
    var h = 0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      var vis = Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top);
      if (vis > 2) h += vis;
    });
    return p.clientHeight > 0 ? Math.min(1, h / p.clientHeight) : -1;
  };
  // 骨架是否有可见底色（读 computed style）
  A.skeletonBg = function(){
    var cc = A.cc(); if (!cc) return null;
    var ph = cc.querySelector('.-pv-placeholder');
    if (!ph) return null;
    var cs = getComputedStyle(ph);
    return { background: cs.backgroundColor, bgImage: cs.backgroundImage ? cs.backgroundImage.slice(0,60) : null };
  };
  A.start = function(){
    A.on = true; A.maxBlank = 0; A.samples = []; A.t0 = performance.now();
    A.maxCov = 0; A.gaps = []; A.lastFrame = performance.now();
    (function fr(){
      if (!A.on) return;
      var n = performance.now(); A.gaps.push(+(n - A.lastFrame).toFixed(1)); A.lastFrame = n;
      requestAnimationFrame(fr);
    })();
    var blankStart = null;
    (function poll(){
      if (!A.on) return;
      var now = performance.now();
      var ph = A.vph(); var cov = A.skeletonCov();
      A.samples.push({ t: Math.round(now - A.t0), ph: ph, cov: cov });
      if (cov > A.maxCov) A.maxCov = cov;
      if (ph > 0) { if (blankStart === null) blankStart = now; }
      else if (blankStart !== null) { var d = now - blankStart; if (d > A.maxBlank) A.maxBlank = d; blankStart = null; }
      setTimeout(poll, 50);
    })();
  };
  A.stop = function(){
    A.on = false;
    var g = (A.gaps || []).filter(function(x){ return isFinite(x) && x > 0; }).sort(function(a,b){ return a-b; });
    var n = g.length;
    // 骨架覆盖持续时长：cov>0.5 的连续时长
    var covRun = 0, covMaxRun = 0;
    A.samples.forEach(function(s){ if (s.cov > 0.5) { covRun++; if (covRun > covMaxRun) covMaxRun = covRun; } else covRun = 0; });
    return { maxBlankMs: Math.round(A.maxBlank), maxCov: +(A.maxCov).toFixed(3),
             covOver50RunMs: covMaxRun * 50,
             blankSamples: A.samples.filter(function(s){return s.ph>0;}).length,
             totalSamples: A.samples.length,
             frameMax: n ? +g[n-1].toFixed(1) : null,
             frameOver800: g.filter(function(x){return x>800;}).length,
             samples: A.samples.slice(0, 200) };
  };
  return 1;
})()`);

async function measureOnce(entry, roundIdx) {
  // 设开关
  await cdp.ev(`(function(){ window.__MEMORIA_DEFER = ${entry.defer}; try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);
  // 重开文档
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
  for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
  for (let k = 0; k < 150; k++) { await sleep(150); if (await cdp.ev('window.__ab.vph()') === 0) break; }
  await sleep(1200);
  // 预热：40% 再回顶
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
  for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__ab.vph()') === 0) break; }
  await sleep(700);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
  for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__ab.vph()') === 0) break; }
  await sleep(900);

  // 测量
  logs.length = 0;
  await cdp.ev('window.__ab.start()');
  for (let s = 1; s <= 10; s++) {
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
    await sleep(16);
  }
  // ★ 到达 80% 后立即抓一张截图（人眼证据）
  await sleep(200);
  let shotPath = null;
  try {
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
    if (shot && shot.data) {
      shotPath = outdir + '/' + entry.label + '-r' + roundIdx + '.png';
      writeFileSync(shotPath, Buffer.from(shot.data, 'base64'));
    }
  } catch (e) { /* 截图失败不影响主指标 */ }
  await sleep(5000);
  const res = await cdp.ev('window.__ab.stop()');
  const deferLogs = logs.filter(l => /typeset DEFERRED/i.test(l));
  const deferVals = deferLogs.map(l => { const m = l.match(/defer\s+(\d+)\s*ms/i); return m ? +m[1] : null; }).filter(x => x !== null).sort((a,b)=>a-b);
  const bg = await cdp.ev('window.__ab.skeletonBg()');
  return { ...res, deferCount: deferLogs.length,
    deferMedian: deferVals.length ? deferVals[Math.floor(deferVals.length/2)] : null,
    deferMax: deferVals.length ? deferVals[deferVals.length-1] : null,
    skeletonBg: bg, screenshot: shotPath, defer: entry.defer };
}

const results = [];
for (let i = 0; i < SEQUENCE.length; i++) {
  const entry = SEQUENCE[i];
  const r = await measureOnce(entry, i + 1);
  results.push({ label: entry.label, ...r });
  console.log(entry.label.padEnd(8) + ': 空白=' + r.maxBlankMs + 'ms  骨架峰值=' + (r.maxCov*100).toFixed(1) + '%  骨架>50%持续=' + r.covOver50RunMs + 'ms' +
    '  defer=' + r.deferCount + '次(med ' + r.deferMedian + '/max ' + r.deferMax + ')  帧max=' + r.frameMax + 'ms  截图=' + (r.screenshot ? '✓' : '✗'));
}

const offVals = results.filter(r => r.defer === false).map(r => r.maxBlankMs).sort((a,b)=>a-b);
const onVals = results.filter(r => r.defer === true).map(r => r.maxBlankMs).sort((a,b)=>a-b);
const med = (a) => a.length ? a[Math.floor(a.length/2)] : null;

console.log('');
console.log('=== 同运行 A/B 汇总 ===');
console.log('  defer OFF: ' + JSON.stringify(offVals) + '  median=' + med(offVals) + 'ms');
console.log('  defer ON : ' + JSON.stringify(onVals) + '  median=' + med(onVals) + 'ms');
console.log('  骨架色: ' + JSON.stringify(results[0].skeletonBg));
console.log('  骨架覆盖率峰值: ' + results.map(r => r.label + '=' + (r.maxCov*100).toFixed(1) + '%').join('  '));

const out = { head: '0b0d9bf0', doc: DOC, results,
  summary: { deferOff: { values: offVals, median: med(offVals) },
             deferOn: { values: onVals, median: med(onVals) },
             skeletonBg: results[0].skeletonBg,
             skeletonCovPeak: results.map(r => ({ label: r.label, peak: r.maxCov, cov50RunMs: r.covOver50RunMs })) } };
writeFileSync(outdir + '/ab-result.json', JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__AB__' + JSON.stringify({ off: med(offVals), on: med(onVals),
  covPeaks: results.map(r => +(r.maxCov).toFixed(2)) }));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
