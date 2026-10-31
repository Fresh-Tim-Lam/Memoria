/**
 * task-63 S0-edu v2：真实教材首屏/全量（修正版）
 *
 * 修正点（v1 的教训）：
 *  1. v1 `首屏mjx=0` 是对的 —— MathJax 在全量渲染后才排版，首屏时刻还没有 mjx-container
 *     ⇒ 首屏公式数要在**首屏渲染完成后**延后采样（多时间点），才能看清"首屏可读时有多少公式"
 *  2. v1 全量超时 120s 打满 15 轮 = 30 分钟不可接受
 *     ⇒ 全量只测 **3 轮**（记录性质，非门禁），首屏测 15 轮（门禁）
 *  3. 增加**时间线采样**：首屏后 0/100/200/500/1000/2000/5000ms 的 mjx 数
 *     ⇒ 精确回答"首屏可读时该屏有多少公式已排版"
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
const FS_ROUNDS = Number(process.argv[4] || 15);
const FULL_ROUNDS = Number(process.argv[5] || 3);
const DOC = process.argv[6] || '教材/08_第8章_差错控制编码.md';
const ALT = process.argv[7] || '教材/04_第4章_信息论基础.md';

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

await cdp.ev(`(function(){
  if (window.__s0) return 1;
  var S = {}; window.__s0 = S;
  S.pane = function(){ return document.getElementById('preview-pane'); };
  S.blocks = function(){ return document.querySelectorAll('#preview .-src-block').length; };
  S.mjxAll = function(){ return document.querySelectorAll('#preview mjx-container').length; };
  S.visibleBlocks = function(){
    var p = this.pane(); if (!p) return 0; var pr = p.getBoundingClientRect(); var n = 0;
    var els = p.querySelectorAll('[data--src-line]');
    for (var i=0;i<els.length;i++){ var r=els[i].getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top) > 1) n++; }
    return n;
  };
  // 视口内「公式容器」（未排版的 span.-math / .-math-block + 已排版的 mjx-container）
  S.formulaInViewport = function(){
    var p = this.pane(); if (!p) return { raw: 0, typeset: 0, total: 0 };
    var pr = p.getBoundingClientRect();
    function inView(el){ var r = el.getBoundingClientRect(); return Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top) > 1; }
    var raw = 0, ts = 0;
    p.querySelectorAll('span.-math, .-math-block').forEach(function(e){ if (inView(e)) raw++; });
    p.querySelectorAll('mjx-container').forEach(function(e){ if (inView(e)) ts++; });
    return { raw: raw, typeset: ts, total: raw + ts };
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
  // 等 pendingMath===0 且块数稳定（真正的全量完成）
  S.waitFullDone = function(timeoutMs){
    var t0 = performance.now(); var lastCount = -1, stable = 0;
    return new Promise(function(res){
      function tick(){
        var c = window.__s0.blocks();
        if (c > 0 && c === lastCount) stable++; else stable = 0;
        lastCount = c;
        var pendingMath = document.querySelectorAll('#preview span.-math, #preview .-math-block').length;
        var mjx = window.__s0.mjxAll();
        // 全量 = 块稳定 6 帧 + 无未排版公式 + mjx 数 > 0
        if (stable >= 6 && pendingMath === 0 && mjx > 0) {
          res({ms: performance.now()-t0, ok:true, blocks:c, mjx:mjx, pendingMath: pendingMath}); return;
        }
        if (performance.now()-t0 > timeoutMs) {
          res({ms: performance.now()-t0, ok:false, blocks:c, mjx:mjx, pendingMath: pendingMath}); return;
        }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  return 1;
})()`);

const results = {
  schema: 'memoria-perf-s0-edu/v2',
  startedAt: new Date().toISOString(),
  doc: DOC, altDoc: ALT,
  firstScreenRounds: FS_ROUNDS, fullRounds: FULL_ROUNDS,
  mode: 'realapp（源码启动 + CDP attach）',
  concurrencyBefore: concurrency(),
  firstScreen_raw: [],
  timeline: [],
  full_raw: [],
};

// ═══ A. 首屏（门禁）：15 轮 ═══
for (let i = 0; i < FS_ROUNDS; i++) {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true})`);
  await sleep(800);
  const r = await cdp.ev(`(async function(){
    var t0 = performance.now();
    window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
    var fs = await window.__s0.waitFirstScreen(30000);
    var elapsed = performance.now() - t0;
    var fv = window.__s0.formulaInViewport();
    return { firstScreen: fs.ms, totalToFirstScreen: elapsed, fsOk: fs.ok,
             blocks: window.__s0.blocks(), mjxAll: window.__s0.mjxAll(),
             viewFormulas: fv, visibleBlocks: window.__s0.visibleBlocks() };
  })()`);
  results.firstScreen_raw.push(r);
  console.log('[fs] ' + (i+1) + ': 首屏=' + r.firstScreen.toFixed(0) + 'ms blocks=' + r.blocks +
    ' mjxAll=' + r.mjxAll + ' 视口公式raw=' + r.viewFormulas.raw + ' ts=' + r.viewFormulas.typeset);
  await sleep(250);
}

// ═══ B. 时间线采样（一次性，看清公式何时出现）═══
{
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true})`);
  await sleep(900);
  const tl = await cdp.ev(`(async function(){
    var t0 = performance.now();
    window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
    var fs = await window.__s0.waitFirstScreen(30000);
    var out = [{ at: Math.round(performance.now()-t0), phase: 'firstScreen',
                 mjx: window.__s0.mjxAll(), view: window.__s0.formulaInViewport(),
                 blocks: window.__s0.blocks() }];
    var marks = [100, 300, 500, 1000, 2000, 3000, 5000];
    for (var k=0;k<marks.length;k++){
      await new Promise(function(r){ setTimeout(r, k===0 ? marks[0] : marks[k]-marks[k-1]); });
      out.push({ at: Math.round(performance.now()-t0), phase: 'mark'+marks[k],
                 mjx: window.__s0.mjxAll(), view: window.__s0.formulaInViewport(),
                 blocks: window.__s0.blocks() });
    }
    return out;
  })()`);
  results.timeline = tl;
  console.log('[timeline] ' + tl.map(t => t.at + 'ms:mjx' + t.mjx + '/view' + t.view.total).join(' '));
}

// ═══ C. 全量（记录性质，3 轮）═══
for (let i = 0; i < FULL_ROUNDS; i++) {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true})`);
  await sleep(900);
  const r = await cdp.ev(`(async function(){
    var t0 = performance.now();
    window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
    var fd = await window.__s0.waitFullDone(300000);
    return { fullDone: performance.now() - t0, fdOk: fd.ok, blocks: fd.blocks,
             mjx: fd.mjx, pendingMath: fd.pendingMath };
  })()`);
  results.full_raw.push(r);
  console.log('[full] ' + (i+1) + ': 全量=' + (r.fullDone/1000).toFixed(1) + 's ok=' + r.fdOk +
    ' mjx=' + r.mjx + ' pending=' + r.pendingMath);
  await sleep(400);
}

function stats(arr) {
  const a = arr.filter(x => typeof x === 'number' && isFinite(x)).sort((x, y) => x - y);
  const n = a.length; if (!n) return null;
  const mean = a.reduce((s, x) => s + x, 0) / n;
  const sd = Math.sqrt(a.reduce((s, x) => s + (x - mean) ** 2, 0) / n);
  const pct = (p) => a[Math.min(n - 1, Math.floor(n * p))];
  return { n, mean: +mean.toFixed(2), sd: +sd.toFixed(2), p50: +pct(0.5).toFixed(2), p95: +pct(0.95).toFixed(2), max: +a[n-1].toFixed(2), raw: a };
}

results.firstScreen = stats(results.firstScreen_raw.filter(r=>r.fsOk).map(r => r.firstScreen));
results.viewFormulasRaw = stats(results.firstScreen_raw.map(r => r.viewFormulas.raw));
results.viewFormulasTypeset = stats(results.firstScreen_raw.map(r => r.viewFormulas.typeset));
results.visibleBlocks = stats(results.firstScreen_raw.map(r => r.visibleBlocks));
results.blocksTotal = results.firstScreen_raw[results.firstScreen_raw.length-1].blocks;
results.mjxTotal = results.firstScreen_raw[results.firstScreen_raw.length-1].mjxAll;
results.fullDone = stats(results.full_raw.filter(r=>r.fdOk).map(r => r.fullDone));
results.concurrencyAfter = concurrency();

writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');

console.log('__S0EDU2__' + JSON.stringify({
  out: outPath,
  firstScreenP50: results.firstScreen && results.firstScreen.p50,
  firstScreenP95: results.firstScreen && results.firstScreen.p95,
  viewFormulaRawP50: results.viewFormulasRaw && results.viewFormulasRaw.p50,
  viewFormulaTypesetP50: results.viewFormulasTypeset && results.viewFormulasTypeset.p50,
  blocksTotal: results.blocksTotal,
  mjxTotal: results.mjxTotal,
  fullDoneP50: results.fullDone && results.fullDone.p50,
  fullDoneOk: results.fullDone && results.fullDone.n,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
