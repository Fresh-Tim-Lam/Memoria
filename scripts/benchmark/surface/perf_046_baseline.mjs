/**
 * task-63 0.4.6 阶段验收基线：A（打开/滚动计时）+ B（高度账本漂移）
 *
 * B 高度漂移测法（Lead 指定）：
 *   1. 打开 08 章，不滚动 → 记录 scrollHeight
 *   2. 滚到 50%，记录「第 1 个可见块的 data--src-line」= A
 *   3. 滚到底 → 滚回 50%，记录同样值 = B
 *   4. |A − B| = 漂移量（理想 0，<5 行可接受）
 *   5. 滚动过程是否"内容上跳"（某块 top 突然变小）
 *
 * A 计时：
 *   打开 08 章 → 首块可见 ms / 最大帧间隔
 *   打开 03 章 → 首屏可读 ms
 *   滚动 50%/80% → 该屏可读 ms
 */
import { writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('timeout')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 60000) {
    return new Promise((res, rej) => {
      const id = ++this._id;
      const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout: ' + method)); }, timeoutMs);
      this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async ev(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: `(function(){ try { var __v = (${expr}); if (__v && typeof __v.then === 'function') return JSON.stringify({_promise:true}); return JSON.stringify(__v === undefined ? null : __v); } catch(e) { return JSON.stringify({_err:String(e && e.message || e)}); } })()`,
      returnByValue: true, userGesture: true
    });
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; return { _exc: String((d.exception && (d.exception.description || d.exception.value)) || d.text || '') }; }
    try { return r.result ? JSON.parse(r.result.value) : null; } catch (e) { return { _parseErr: true }; }
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2]);
const outPath = process.argv[3];
const DOC08 = process.argv[4] || '教材/08_第8章_差错控制编码.md';
const DOC03 = process.argv[5] || '教材/03_第3章_模拟信号的数字编码.md';
const ALT = process.argv[6] || 'homework/README.md';

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

let page = null;
for (let a = 0; a < 40; a++) {
  try {
    const l = await httpJson(`http://127.0.0.1:${port}/json/list`);
    page = (l || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || '') && t.webSocketDebuggerUrl);
    if (page) break;
  } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('❌ 无法连接'); process.exit(2); }

const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
for (let i = 0; i < 300; i++) { const v = await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface'); if (v === true) break; await sleep(200); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// ── 安装页面内工具 ──
await cdp.ev(`(function(){
  if (window.__m) return 1;
  var M = { frameGaps: [], rafId: null, frameOn: false, lastFrame: 0 };
  window.__m = M;

  M.pane = function(){ return document.getElementById('preview-pane'); };
  M.blocks = function(){ return document.querySelectorAll('#preview .-src-block').length; };
  M.firstVisibleSrcLine = function(){
    var p = this.pane(); if (!p) return null;
    var pr = p.getBoundingClientRect();
    var els = p.querySelectorAll('[data--src-line]');
    for (var i=0;i<els.length;i++){
      var r = els[i].getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) {
        return +els[i].getAttribute('data--src-line');
      }
    }
    return null;
  };
  M.frameStart = function(){ M.frameGaps=[]; M.lastFrame=performance.now(); M.frameOn=true;
    function tick(){ if(!M.frameOn) return; var n=performance.now(); M.frameGaps.push(n-M.lastFrame); M.lastFrame=n; M.rafId=requestAnimationFrame(tick); }
    M.rafId=requestAnimationFrame(tick);
  };
  M.frameStop = function(){ M.frameOn=false; if(M.rafId) cancelAnimationFrame(M.rafId);
    var g=M.frameGaps.filter(function(x){return isFinite(x)&&x>0;}).sort(function(a,b){return a-b;});
    var n=g.length;
    return { count:n, max:n?+g[n-1].toFixed(1):null, p95:n?+g[Math.floor(n*0.95)].toFixed(1):null,
             over900:g.filter(function(x){return x>900;}).length, over200:g.filter(function(x){return x>200;}).length };
  };
  // 滚动到 pct（0-1），并等稳定
  M.scrollToPct = function(pct){
    var p = this.pane(); if (!p) return Promise.resolve({err:'no pane'});
    var target = (p.scrollHeight - p.clientHeight) * pct;
    p.scrollTop = target;
    return new Promise(function(res){
      var stable = 0; var last = -1;
      function tick(){
        var cur = p.scrollTop;
        if (cur === last) stable++; else stable = 0;
        last = cur;
        if (stable >= 3) { res({ top: cur, firstLine: window.__m.firstVisibleSrcLine() }); return; }
        requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  };
  // 检测上跳：滚动过程中记录所有可见块 top 的变化
  M.maxTopShrink = 0;
  M.watchScrollJump = function(durationMs){
    return new Promise(function(res){
      var prevTops = {}; var maxShrink = 0;
      var t0 = performance.now();
      function tick(){
        var p = window.__m.pane(); if (!p) { res({maxShrink:0}); return; }
        var els = p.querySelectorAll('[data--src-line]');
        for (var i=0;i<els.length && i<30;i++){
          var el = els[i]; var id = el.getAttribute('data--src-line');
          var top = el.getBoundingClientRect().top;
          if (id in prevTops) {
            var delta = prevTops[id] - top; // 正 = 上移
            if (delta > maxShrink) maxShrink = delta;
          }
          prevTops[id] = top;
        }
        if (performance.now() - t0 > durationMs) { res({ maxShrink: +maxShrink.toFixed(1) }); return; }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  return 1;
})()`);

const results = {
  schema: 'memoria-perf-046-baseline/v1',
  startedAt: new Date().toISOString(),
  head: (await cdp.ev('(typeof __HEAD !== "undefined") ? 0 : 0')), // 无；由外部补
  doc08: DOC08, doc03: DOC03,
  mode: 'realapp + CDP', concurrencyBefore: concurrency(),
};

function stats(arr) {
  const a = arr.filter(x => typeof x === 'number' && isFinite(x)).sort((x, y) => x - y);
  const n = a.length; if (!n) return null;
  return { n, min: +a[0].toFixed(1), mean: +(a.reduce((s,x)=>s+x,0)/n).toFixed(1), p50: +a[Math.floor(n*0.5)].toFixed(1), p95: +a[Math.floor(n*0.95)].toFixed(1), max: +a[n-1].toFixed(1) };
}

// ══════════ A1：打开 08 章 → 首块可见 + 帧间隔 ══════════
{
  const firstVisible = []; const maxGaps = [];
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC08)},{skipNav:true}); return 1; })()`);
  await sleep(10000); // 预热
  for (let i = 0; i < 3; i++) {
    await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true}); return 1; })()`);
    await sleep(2500);
    await cdp.ev(`(function(){ window.__m.frameStart(); return 1; })()`);
    const t0 = Date.now();
    await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC08)},{skipNav:true}); return 1; })()`);
    // 等首块可见
    let fb = null;
    for (let k = 0; k < 300; k++) {
      await sleep(100);
      const v = await cdp.ev(`(function(){
        var p=document.getElementById('preview-pane'); var pv=document.getElementById('preview');
        if(!p||!pv) return null;
        var b = pv.querySelector('[data--src-line]');
        if(!b) return null;
        var pr=p.getBoundingClientRect(), br=b.getBoundingClientRect();
        return (Math.min(pr.bottom,br.bottom)-Math.max(pr.top,br.top)>2) ? 1 : null;
      })()`);
      if (v === 1) { fb = Date.now() - t0; break; }
    }
    const fg = await cdp.ev('window.__m.frameStop()');
    firstVisible.push(fb); maxGaps.push(fg && fg.max);
    console.log('[open08] 首块可见=' + fb + 'ms 最大帧=' + (fg && fg.max) + 'ms over900=' + (fg && fg.over900));
    await sleep(500);
  }
  results.open08 = { firstVisible: stats(firstVisible), maxGap: stats(maxGaps) };
}

// ══════════ A2：打开 03 章 → 首屏可读 ══════════
{
  const firstVisible = [];
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC03)},{skipNav:true}); return 1; })()`);
  await sleep(10000);
  for (let i = 0; i < 3; i++) {
    await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true}); return 1; })()`);
    await sleep(2500);
    const t0 = Date.now();
    await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC03)},{skipNav:true}); return 1; })()`);
    let fb = null;
    for (let k = 0; k < 300; k++) {
      await sleep(100);
      const v = await cdp.ev(`(function(){
        var p=document.getElementById('preview-pane'); var pv=document.getElementById('preview');
        if(!p||!pv) return null;
        var b = pv.querySelector('[data--src-line]');
        if(!b) return null;
        var pr=p.getBoundingClientRect(), br=b.getBoundingClientRect();
        return (Math.min(pr.bottom,br.bottom)-Math.max(pr.top,br.top)>2) ? 1 : null;
      })()`);
      if (v === 1) { fb = Date.now() - t0; break; }
    }
    firstVisible.push(fb);
    console.log('[open03] 首块可见=' + fb + 'ms');
    await sleep(500);
  }
  results.open03 = { firstVisible: stats(firstVisible) };
}

// ══════════ B：高度账本漂移 ══════════
{
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC08)},{skipNav:true}); return 1; })()`);
  // 显式等全量完成：mjx>100 且 residual===0，且 data--src-line 已写入（>3000）
  for (let k = 0; k < 400; k++) {
    await sleep(100);
    const st = await cdp.ev(`(function(){
      var pv = document.getElementById('preview');
      if (!pv) return null;
      var sup = pv.querySelectorAll('span.-math:not(:has(mjx-container))').length;
      var blk = pv.querySelectorAll('.-math-block:not(:has(mjx-container))').length;
      var srcline = pv.querySelectorAll('[data--src-line]').length;
      return { mjx: pv.querySelectorAll('mjx-container').length, residual: sup+blk, srcline: srcline };
    })()`);
    if (st && st.mjx > 100 && st.residual === 0 && st.srcline > 3000) break;
  }
  await sleep(500);

  const b1 = {};
  b1.scrollHeight = await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); return p ? p.scrollHeight : null; })()`);
  b1.clientHeight = await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); return p ? p.clientHeight : null; })()`);

  // 滚到 50%，记第一可见块 src-line = A
  const at50 = await cdp.ev('window.__m.scrollToPct(0.5)');
  b1.A_firstLineAt50 = at50 && at50.firstLine;

  // 滚到底，再回 50%，记 = B（同时观察上跳）
  const jumpPromise = cdp.ev('window.__m.watchScrollJump(4000)');
  await cdp.ev('window.__m.scrollToPct(1.0)');
  await sleep(800);
  const at50b = await cdp.ev('window.__m.scrollToPct(0.5)');
  await sleep(500);
  const jump = await jumpPromise.catch(() => ({ maxShrink: null }));
  b1.B_firstLineAt50 = at50b && at50b.firstLine;
  b1.drift = (b1.A_firstLineAt50 != null && b1.B_firstLineAt50 != null)
    ? Math.abs(b1.A_firstLineAt50 - b1.B_firstLineAt50) : null;
  b1.topShrink = jump && jump.maxShrink;

  results.heightDrift = b1;
  console.log('[drift] scrollHeight=' + b1.scrollHeight + ' clientHeight=' + b1.clientHeight +
    ' A(50%)=' + b1.A_firstLineAt50 + ' B(回50%)=' + b1.B_firstLineAt50 +
    ' drift=' + b1.drift + ' 上跳=' + b1.topShrink + 'px');
}

// ══════════ A3：滚动 50%/80% 该屏可读 ══════════
{
  const scroll50 = []; const scroll80 = [];
  for (let i = 0; i < 3; i++) {
    // 先回顶部
    await cdp.ev('window.__m.scrollToPct(0)');
    await sleep(500);
    // 滚到 50%
    const t0 = Date.now();
    await cdp.ev('window.__m.scrollToPct(0.5)');
    scroll50.push(Date.now() - t0);
    await sleep(400);
    // 滚到 80%
    const t1 = Date.now();
    await cdp.ev('window.__m.scrollToPct(0.8)');
    scroll80.push(Date.now() - t1);
    await sleep(400);
  }
  results.scroll = { scroll50: stats(scroll50), scroll80: stats(scroll80) };
  console.log('[scroll] 50%=' + JSON.stringify(stats(scroll50)) + ' 80%=' + JSON.stringify(stats(scroll80)));
}

results.concurrencyAfter = concurrency();
writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log('');
console.log('__BASELINE__' + JSON.stringify({
  out: outPath,
  open08_firstVisible: results.open08.firstVisible,
  open08_maxGap: results.open08.maxGap,
  open03_firstVisible: results.open03.firstVisible,
  drift: results.heightDrift.drift,
  topShrink: results.heightDrift.topShrink,
  scroll: results.scroll,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
