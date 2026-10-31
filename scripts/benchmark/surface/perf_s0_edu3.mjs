/**
 * task-63 S0-edu v3：修正首屏判据（等该屏可读）
 *
 * v2 的教训：
 *  - "块 DOM 出现" ≠ "可读"：公式还是裸 span.-math，没排版
 *  - 视口公式查询恒 0：因为视口判定时机在 DOM 未布局时
 *  - 全量 300s 未完成
 *
 * v3 修正：
 *  首屏定义（两个口径都给）：
 *    FS-A「元素可见」= openFile → 首块进入视口 + 双 rAF（v2 的口径，快但不可读）
 *    FS-B「该屏可读」= openFile → **视口内所有公式容器都已变成 mjx-container** + 双 rAF
 *                      （若 100ms 内未完成，记录 100ms 时刻的完成比例）
 *  首屏公式数：FS-A 时刻、FS-B 时刻、以及全量后视口内 mjx 数
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

const [,, portArg, outPath, roundsArg, docArg, altArg] = process.argv;
const port = Number(portArg);
const ROUNDS = Number(roundsArg || 15);
const DOC = docArg || '教材/08_第8章_差错控制编码.md';
const ALT = altArg || '教材/04_第4章_信息论基础.md';
const BUDGET = 100; // ms，人的体验预算

function concurrency() {
  let mem = [], wv = 0;
  try {
    const o = execFileSync('powershell', ['-NoProfile', '-Command',
      "Get-Process -Name Memoria -EA SilentlyContinue | ForEach-Object { \"$($_.Id)|$([Math]::Round($_.CPU,1))\" }; 'WV:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count"],
      { encoding: 'utf8', timeout: 15000 });
    for (const line of o.split(/\r?\n/)) {
      if (line.startsWith('WV:')) wv = Number(line.slice(3));
      else if (line.includes('|')) { const [p, c] = line.split('|'); mem.push({ pid: +p, cpuSec: +c }); }
    }
  } catch (e) { /* */ }
  return { memoriaExe: mem, webview2Count: wv, at: new Date().toISOString() };
}

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
for (let i = 0; i < 300; i++) { if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }
await cdp.ev(`(function(){ if((window.state||{}).viewMode!=='preview'){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); } return 1; })()`);
await sleep(1200);

// 安装探针
await cdp.ev(`(function(){
  if (window.__s3) return 1;
  var S = {}; window.__s3 = S;
  S.pane = function(){ return document.getElementById('preview-pane'); };
  S.blocks = function(){ return document.querySelectorAll('#preview .-src-block').length; };
  S.mjxAll = function(){ return document.querySelectorAll('#preview mjx-container').length; };
  // 精确的视口内公式统计
  //   未排版 = span.-math / .-math-block（不含内部已有 mjx-container 的）
  //   已排版 = mjx-container
  S.formulaView = function(){
    var p = this.pane(); if (!p) return { pending: 0, typeset: 0, total: 0, pendingSel: 0 };
    var pr = p.getBoundingClientRect();
    function inView(el){
      var r = el.getBoundingClientRect();
      if (r.width < 0.5 && r.height < 0.5) return false;
      return Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 0.5;
    }
    var typeset = 0, pending = 0;
    p.querySelectorAll('mjx-container').forEach(function(e){ if (inView(e)) typeset++; });
    // 未排版的：.-math 内部没有 mjx-container 的
    p.querySelectorAll('span.-math').forEach(function(e){
      if (e.querySelector('mjx-container')) return;
      if (inView(e)) pending++;
    });
    p.querySelectorAll('.-math-block').forEach(function(e){
      if (e.querySelector('mjx-container')) return;
      if (inView(e)) pending++;
    });
    return { pending: pending, typeset: typeset, total: pending + typeset };
  };
  // 首屏 A：块元素出现
  S.waitElements = function(timeoutMs){
    var t0 = performance.now(); var p = this.pane();
    return new Promise(function(res){
      function tick(){
        var has = p && p.querySelectorAll('[data--src-line]').length > 0;
        if (has) { requestAnimationFrame(function(){ requestAnimationFrame(function(){
          res({ms: performance.now()-t0, ok:true, view: window.__s3.formulaView()}); }); }); return; }
        if (performance.now()-t0 > timeoutMs) { res({ms: performance.now()-t0, ok:false, view: window.__s3.formulaView()}); return; }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  // 首屏 B：该屏可读（视口内无未排版公式）
  S.waitReadable = function(timeoutMs){
    var t0 = performance.now();
    return new Promise(function(res){
      function tick(){
        var v = window.__s3.formulaView();
        if (v.pending === 0) {
          requestAnimationFrame(function(){ requestAnimationFrame(function(){
            var v2 = window.__s3.formulaView();
            res({ms: performance.now()-t0, ok: v2.pending === 0, view: v2}); }); });
          return;
        }
        if (performance.now()-t0 > timeoutMs) { res({ms: performance.now()-t0, ok:false, view: v}); return; }
        setTimeout(tick, 10);
      }
      tick();
    });
  };
  return 1;
})()`);

const results = {
  schema: 'memoria-perf-s0-edu/v3',
  startedAt: new Date().toISOString(),
  doc: DOC, altDoc: ALT, rounds: ROUNDS, budgetMs: BUDGET,
  mode: 'realapp + CDP attach',
  kb: 'work copy artifacts/_kbwork_perf_edu',
  concurrencyBefore: concurrency(),
  rounds_raw: [],
};

// 预热一次（不计入）
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true})`);
await sleep(4000);

for (let i = 0; i < ROUNDS; i++) {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true})`);
  await sleep(900);

  const r = await cdp.ev(`(async function(){
    var t0 = performance.now();
    window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
    // A：元素出现
    var ea = await window.__s3.waitElements(30000);
    var tElem = performance.now() - t0;
    var viewAtElem = window.__s3.formulaView();
    // B：该屏可读（从 t0 起算，最多等 5s —— 超过就记预算失败）
    var rd = await window.__s3.waitReadable(5000);
    var tRead = performance.now() - t0;
    return {
      elemMs: tElem, elemOk: ea.ok,
      readableMs: tRead, readableOk: rd.ok,
      viewAtElem: viewAtElem, viewAtRead: rd.view,
      blocks: window.__s3.blocks(), mjxAll: window.__s3.mjxAll(),
    };
  })()`);
  results.rounds_raw.push(r);
  console.log('[r' + (i+1) + '] 元素=' + r.elemMs.toFixed(0) + 'ms  可读=' + r.readableMs.toFixed(0) +
    'ms  视口公式(元素时)p=' + r.viewAtElem.pending + '/t=' + r.viewAtElem.typeset +
    '  (可读时)t=' + r.viewAtRead.typeset + '  mjxAll=' + r.mjxAll + ' blocks=' + r.blocks);
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

results.elemMs = stats(results.rounds_raw.filter(r=>r.elemOk).map(r => r.elemMs));
results.readableMs = stats(results.rounds_raw.filter(r=>r.readableOk).map(r => r.readableMs));
results.readableAll = stats(results.rounds_raw.map(r => r.readableMs)); // 含超时值
results.viewTypesetAtElem = stats(results.rounds_raw.map(r => r.viewAtElem.typeset));
results.viewTypesetAtRead = stats(results.rounds_raw.map(r => r.viewAtRead.typeset));
results.viewPendingAtElem = stats(results.rounds_raw.map(r => r.viewAtElem.pending));
results.mjxTotal = results.rounds_raw[results.rounds_raw.length-1].mjxAll;
results.blocksTotal = results.rounds_raw[results.rounds_raw.length-1].blocks;
results.withinBudget = results.readableMs ? results.readableMs.p95 <= BUDGET : false;
results.concurrencyAfter = concurrency();

writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log('__S3__' + JSON.stringify({
  out: outPath,
  elemP50: results.elemMs && results.elemMs.p50,
  readableP50: results.readableMs && results.readableMs.p50,
  readableP95: results.readableMs && results.readableMs.p95,
  readableOkCount: results.readableMs ? results.readableMs.n : 0,
  readableAllP50: results.readableAll && results.readableAll.p50,
  viewTypesetAtElemP50: results.viewTypesetAtElem && results.viewTypesetAtElem.p50,
  viewPendingAtElemP50: results.viewPendingAtElem && results.viewPendingAtElem.p50,
  viewTypesetAtReadP50: results.viewTypesetAtRead && results.viewTypesetAtRead.p50,
  mjxTotal: results.mjxTotal,
  blocksTotal: results.blocksTotal,
  withinBudget100ms: results.withinBudget,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
