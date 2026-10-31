/**
 * task-63 S0-v2：真实教材 open 首屏/全量（带并发记录 + 首屏公式占比）
 *
 * 关键：
 *  - 首屏 = openFile → 首块进入 #preview-pane 视口 + 双 rAF
 *  - 全量 = openFile → 块数稳定 6 帧 + pendingMath=0
 *  - 首屏公式占比 = 视口内 mjx-container 数 / 全量后 mjx-container 总数（A 方案收益上界）
 *  - 并发记录：Memoria.exe pid + CPU + webview2 数
 */
import { writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('timeout')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true, userGesture: true }); if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '')); } return r.result ? r.result.value : undefined; }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2]);
const outPath = process.argv[3];
const ROUNDS = Number(process.argv[4] || 15);
const DOC = process.argv[5] || '教材/08_第8章_差错控制编码.md';
const ALT = process.argv[6] || '教材/04_第4章_信息论基础.md';

// 并发快照
function concurrency() {
  let mem = [], wv = 0;
  try {
    const o = execFileSync('powershell', ['-NoProfile', '-Command',
      "Get-Process -Name Memoria -EA SilentlyContinue | ForEach-Object { \"$($_.Id)|$([Math]::Round($_.CPU,1))|$([Math]::Round($_.WorkingSet64/1MB,0))\" }; 'WV:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count"],
      { encoding: 'utf8', timeout: 15000 });
    for (const line of o.split(/\r?\n/)) {
      if (line.startsWith('WV:')) wv = Number(line.slice(3));
      else if (line.includes('|')) { const [p, c, m] = line.split('|'); mem.push({ pid: +p, cpuSec: +c, memMB: +m }); }
    }
  } catch (e) { /* ignore */ }
  return { memoriaExe: mem, webview2Count: wv, at: new Date().toISOString() };
}

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');

for (let i = 0; i < 300; i++) { if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }

await cdp.ev(`(function(){ if((window.state||{}).viewMode!=='preview'){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); } return 1; })()`);
await sleep(1000);

// 安装页面内计时工具
await cdp.ev(`(function(){
  if (window.__s0) return 1;
  var S = {}; window.__s0 = S;
  S.pane = function(){ return document.getElementById('preview-pane'); };
  S.blocks = function(){ return document.querySelectorAll('#preview .-src-block').length; };
  S.mjxAll = function(){ return document.querySelectorAll('#preview mjx-container').length; };
  // 视口内 mjx-container 数
  S.mjxInViewport = function(){
    var p = this.pane(); if (!p) return 0;
    var pr = p.getBoundingClientRect(); var n = 0;
    var els = p.querySelectorAll('mjx-container');
    for (var i=0;i<els.length;i++){
      var r = els[i].getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 1) n++;
    }
    return n;
  };
  S.visibleBlocks = function(){
    var p = this.pane(); if (!p) return 0;
    var pr = p.getBoundingClientRect(); var n = 0;
    var els = p.querySelectorAll('[data--src-line]');
    for (var i=0;i<els.length;i++){
      var r = els[i].getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 1) n++;
    }
    return n;
  };
  S.waitFirstScreen = function(timeoutMs){
    var t0 = performance.now(); var p = this.pane();
    return new Promise(function(res){
      function tick(){
        var ok = p && p.querySelectorAll('[data--src-line]').length > 0 && window.__s0.visibleBlocks() > 0;
        if (ok) { requestAnimationFrame(function(){ requestAnimationFrame(function(){ res({ms: performance.now()-t0, ok:true}); }); }); return; }
        if (performance.now()-t0 > timeoutMs) { res({ms: performance.now()-t0, ok:false}); return; }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  S.waitFullDone = function(timeoutMs){
    var t0 = performance.now(); var lastCount = -1, stable = 0;
    return new Promise(function(res){
      function tick(){
        var c = window.__s0.blocks();
        if (c > 0 && c === lastCount) stable++; else stable = 0;
        lastCount = c;
        var pendingMath = document.querySelectorAll('#preview span.-math, #preview .-math-block').length;
        if (stable >= 6 && pendingMath === 0) {
          res({ms: performance.now()-t0, ok:true, blocks:c, mjx: window.__s0.mjxAll(), pendingMath: pendingMath});
          return;
        }
        if (performance.now()-t0 > timeoutMs) {
          res({ms: performance.now()-t0, ok:false, blocks:c, mjx: window.__s0.mjxAll(), pendingMath: pendingMath});
          return;
        }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  return 1;
})()`);

const results = {
  schema: 'memoria-perf-s0-edu/v1',
  startedAt: new Date().toISOString(),
  doc: DOC,
  altDoc: ALT,
  rounds: ROUNDS,
  mode: 'realapp（源码启动 + CDP attach）',
  concurrencyBefore: concurrency(),
  rounds_raw: [],
};

// 找 alt 文档（若不存在则用 README）
await cdp.ev(`(function(){ window.__s0alt = ${JSON.stringify(ALT)}; return 1; })()`);

for (let i = 0; i < ROUNDS; i++) {
  // 先切到 alt，保证 open 不是"当前已打开"
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true}); return 1; })()`);
  await sleep(700);

  const r = await cdp.ev(`(async function(){
    var t0 = performance.now();
    window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
    var fs = await window.__s0.waitFirstScreen(30000);
    var mjxAtFirst = window.__s0.mjxInViewport();
    var visBlocks = window.__s0.visibleBlocks();
    var fd = await window.__s0.waitFullDone(120000);
    var mjxAll = window.__s0.mjxAll();
    var mjxInViewAfter = window.__s0.mjxInViewport();
    return {
      firstScreen: fs.ms, fsOk: fs.ok,
      fullDone: performance.now() - t0, fdOk: fd.ok,
      blocks: fd.blocks, mjxAll: mjxAll,
      mjxAtFirstScreen: mjxAtFirst, mjxInViewAfter: mjxInViewAfter,
      visibleBlocks: visBlocks, pendingMath: fd.pendingMath,
    };
  })()`);
  results.rounds_raw.push(r);
  console.log('[s0-edu] round ' + (i+1) + ': 首屏=' + r.firstScreen.toFixed(0) + 'ms 全量=' + r.fullDone.toFixed(0) +
    'ms mjx=' + r.mjxAll + ' 首屏mjx=' + r.mjxAtFirstScreen + ' blocks=' + r.blocks);
  await sleep(300);
}

function stats(arr) {
  const a = arr.filter(x => typeof x === 'number' && isFinite(x)).sort((x, y) => x - y);
  const n = a.length; if (!n) return null;
  const mean = a.reduce((s, x) => s + x, 0) / n;
  const sd = Math.sqrt(a.reduce((s, x) => s + (x - mean) ** 2, 0) / n);
  const pct = (p) => a[Math.min(n - 1, Math.floor(n * p))];
  return { n, mean: +mean.toFixed(2), sd: +sd.toFixed(2), p50: +pct(0.5).toFixed(2), p95: +pct(0.95).toFixed(2), max: +a[n-1].toFixed(2), raw: a };
}

results.firstScreen = stats(results.rounds_raw.filter(r=>r.fsOk).map(r => r.firstScreen));
results.fullDone = stats(results.rounds_raw.filter(r=>r.fdOk).map(r => r.fullDone));
results.mjxAll = results.rounds_raw[results.rounds_raw.length-1].mjxAll;
results.blocks = results.rounds_raw[results.rounds_raw.length-1].blocks;
const mf = results.rounds_raw.map(r => r.mjxAtFirstScreen);
const mv = results.rounds_raw.map(r => r.mjxInViewAfter);
results.firstScreenMjx = stats(mf);
results.inViewMjxAfter = stats(mv);
results.firstScreenFormulaRatio = results.mjxAll ? +(results.firstScreenMjx.p50 / results.mjxAll).toFixed(4) : null;
results.concurrencyAfter = concurrency();

writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');

console.log('__S0EDU__' + JSON.stringify({
  out: outPath,
  doc: DOC,
  firstScreenP50: results.firstScreen.p50,
  firstScreenP95: results.firstScreen.p95,
  fullDoneP50: results.fullDone.p50,
  fullDoneP95: results.fullDone.p95,
  mjxAll: results.mjxAll,
  blocks: results.blocks,
  firstScreenMjxP50: results.firstScreenMjx.p50,
  firstScreenFormulaRatio: results.firstScreenFormulaRatio,
  roundsOk: results.firstScreen.n + '/' + ROUNDS,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
