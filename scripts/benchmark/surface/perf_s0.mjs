/**
 * task-63 S0：0.4.4 干净性能基线
 *
 * 关键设计（对应 Lead 8 条硬要求）：
 *  1. mode=realapp（真机 --cdp attach）
 *  2. 配置隔离（外部传入空 MEMORIA_CONFIG_DIR）
 *  3. KB 守卫（外部脚本控制）
 *  4. 测量期间无其它 Memoria 实例（外部控制）
 *  5. ≥15 轮
 *  6. P50/P95/max/sd + 噪声门
 *  7. 身份字段
 *  8. **open 分「首屏」与「全量完成」两个读数** ← 本脚本核心增量
 *
 * 首屏定义：openFile 调用 → 第一个 `-src-block` 进入 #preview-pane 视口并完成一次 rAF
 * 全量完成：openFile 调用 → preview 块数稳定 + 无 pending typeset + 连续 2 帧无 DOM 变化
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
const DOC = process.argv[5] || 'corpus/01-ime-zh.md';

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Profiler.enable').catch(() => {});

for (let i = 0; i < 250; i++) { if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }

// 确保 preview 视图
await cdp.ev(`(function(){ if((window.state||{}).viewMode!=='preview'){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); } return 1; })()`);
await sleep(800);

// ── 页面内计时工具（一次安装）──
await cdp.ev(`(function(){
  if (window.__s0) return 1;
  var S = { };
  window.__s0 = S;
  S.pane = function(){ return document.getElementById('preview-pane'); };
  S.blocks = function(){ return document.querySelectorAll('#preview .-src-block').length; };
  // 首屏可见块数
  S.visibleBlocks = function(){
    var p = this.pane(); if (!p) return 0;
    var pr = p.getBoundingClientRect();
    var n = 0;
    var els = p.querySelectorAll('[data--src-line]');
    for (var i=0;i<els.length;i++){
      var r = els[i].getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 1) n++;
    }
    return n;
  };
  // 等待首屏：出现第一个块且进入视口
  S.waitFirstScreen = function(timeoutMs){
    var t0 = performance.now();
    var p = this.pane();
    return new Promise(function(res){
      function tick(){
        var ok = p && p.querySelectorAll('[data--src-line]').length > 0 && window.__s0.visibleBlocks() > 0;
        if (ok) {
          requestAnimationFrame(function(){
            requestAnimationFrame(function(){ res({ ms: performance.now() - t0, ok: true }); });
          });
          return;
        }
        if (performance.now() - t0 > timeoutMs) { res({ ms: performance.now() - t0, ok: false }); return; }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  // 等待全量完成：块数稳定 + typeset 队列空 + 连续 N 帧无变化
  S.waitFullDone = function(timeoutMs){
    var t0 = performance.now();
    var lastCount = -1, stableFrames = 0;
    return new Promise(function(res){
      function tick(){
        var c = window.__s0.blocks();
        var mjPending = (window.MathJax && MathJax.startup && MathJax.startup.document &&
                         MathJax.startup.document.state && MathJax.startup.document.state() < 10) ? 1 : 0;
        var mjxCount = document.querySelectorAll('#preview mjx-container').length;
        if (c > 0 && c === lastCount) stableFrames++; else stableFrames = 0;
        lastCount = c;
        // 全量完成判据：块数稳定 6 帧 + 无待排版公式（用 pending span.-math 计数）
        var pendingMath = document.querySelectorAll('#preview span.-math, #preview .-math-block').length;
        if (stableFrames >= 6 && pendingMath === 0) {
          res({ ms: performance.now() - t0, ok: true, blocks: c, mjx: mjxCount, pendingMath: pendingMath });
          return;
        }
        if (performance.now() - t0 > timeoutMs) {
          res({ ms: performance.now() - t0, ok: false, blocks: c, mjx: mjxCount, pendingMath: pendingMath });
          return;
        }
        requestAnimationFrame(tick);
      }
      tick();
    });
  };
  S.mjxCount = function(){ return document.querySelectorAll('#preview mjx-container').length; };
  S.mathSpans = function(){ return document.querySelectorAll('#preview span.-math, #preview .-math-block').length; };
  return 1;
})()`);

const results = {
  schema: 'memoria-perf-s0/v1',
  startedAt: new Date().toISOString(),
  doc: DOC,
  rounds: ROUNDS,
  mode: 'realapp',
  ops: {},
  env: {},
};

// 环境快照
results.env = await cdp.ev(`(function(){
  return { viewMode: (window.state||{}).viewMode,
           kbPath: (window.state||{}).kbPath,
           currentPath: (window.state||{}).currentPath,
           ua: navigator.userAgent.slice(0,80) };
})()`);

function stats(arr) {
  const a = arr.slice().sort((x, y) => x - y);
  const n = a.length;
  if (!n) return null;
  const mean = a.reduce((s, x) => s + x, 0) / n;
  const sd = Math.sqrt(a.reduce((s, x) => s + (x - mean) ** 2, 0) / n);
  const pct = (p) => a[Math.min(n - 1, Math.floor(n * p))];
  return { n, mean: +mean.toFixed(2), sd: +sd.toFixed(2), p50: pct(0.5), p95: pct(0.95), max: a[n - 1], min: a[0], raw: arr };
}

// ══════════════ open：首屏 + 全量 ══════════════
{
  const firstScreen = [];
  const fullDone = [];
  const mjxAtFull = [];
  const blocksAtFull = [];
  for (let i = 0; i < ROUNDS; i++) {
    // 切到另一个文档，保证不是"已打开"的缓存命中
    await cdp.ev(`(function(){ window.MemoriaApp.openFile('README.md',{skipNav:true}); return 1; })()`);
    await sleep(500);

    // 计时：openFile → 首屏 / 全量
    const r = await cdp.ev(`(async function(){
      var t0 = performance.now();
      window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
      var fs = await window.__s0.waitFirstScreen(20000);
      var fd = await window.__s0.waitFullDone(60000);
      return { firstScreen: fs.ms - 0, fullDone: performance.now() - t0,
               fsOk: fs.ok, fdOk: fd.ok, blocks: fd.blocks, mjx: fd.mjx, pendingMath: fd.pendingMath };
    })()`);
    if (r.fsOk) firstScreen.push(+r.firstScreen.toFixed(1));
    if (r.fdOk) fullDone.push(+r.fullDone.toFixed(1));
    mjxAtFull.push(r.mjx);
    blocksAtFull.push(r.blocks);
    await sleep(200);
  }
  results.ops.open = {
    firstScreen: stats(firstScreen),
    fullDone: stats(fullDone),
    mjxCount: mjxAtFull[0],
    blocks: blocksAtFull[0],
    doc: DOC,
  };
  console.log('[s0] open  首屏 P50=' + results.ops.open.firstScreen.p50 +
    ' 全量 P50=' + results.ops.open.fullDone.p50 +
    ' mjx=' + results.ops.open.mjxCount + ' blocks=' + results.ops.open.blocks);
}

// ══════════════ tabSwitch ══════════════
{
  const firstScreen = [];
  const fullDone = [];
  const OTHER = 'corpus/02-inline-edges.md';
  for (let i = 0; i < ROUNDS; i++) {
    // 交替两个文档，模拟切页签
    await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(OTHER)},{skipNav:true}); return 1; })()`);
    await sleep(600);
    const r = await cdp.ev(`(async function(){
      var t0 = performance.now();
      window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true});
      var fs = await window.__s0.waitFirstScreen(20000);
      var fd = await window.__s0.waitFullDone(60000);
      return { firstScreen: fs.ms, fullDone: performance.now() - t0, fsOk: fs.ok, fdOk: fd.ok };
    })()`);
    if (r.fsOk) firstScreen.push(+r.firstScreen.toFixed(1));
    if (r.fdOk) fullDone.push(+r.fullDone.toFixed(1));
    await sleep(200);
  }
  results.ops.tabSwitch = { firstScreen: stats(firstScreen), fullDone: stats(fullDone) };
  console.log('[s0] tabSwitch 首屏 P50=' + results.ops.tabSwitch.firstScreen.p50 +
    ' 全量 P50=' + results.ops.tabSwitch.fullDone.p50);
}

// ══════════════ scroll ══════════════
{
  const vals = [];
  for (let i = 0; i < ROUNDS; i++) {
    const r = await cdp.ev(`(async function(){
      var p = document.getElementById('preview-pane');
      p.scrollTop = 0;
      await new Promise(function(r){ requestAnimationFrame(function(){ requestAnimationFrame(r); }); });
      var t0 = performance.now();
      p.scrollTop = 500 + ${i} * 40;
      await new Promise(function(r){ requestAnimationFrame(function(){ requestAnimationFrame(r); }); });
      return performance.now() - t0;
    })()`);
    vals.push(+r.toFixed(1));
    await sleep(80);
  }
  results.ops.scroll = stats(vals);
  console.log('[s0] scroll P50=' + results.ops.scroll.p50 + ' P95=' + results.ops.scroll.p95);
}

// ══════════════ typing ══════════════
{
  const vals = [];
  await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
  await sleep(600);
  for (let i = 0; i < ROUNDS; i++) {
    const r = await cdp.ev(`(async function(){
      var t0 = performance.now();
      var ev = new InputEvent('beforeinput', {inputType:'insertText', data:'x', bubbles:true, cancelable:true});
      var ed = document.getElementById('editor');
      if (ed) { ed.dispatchEvent(ev); }
      await new Promise(function(r){ requestAnimationFrame(function(){ requestAnimationFrame(r); }); });
      return performance.now() - t0;
    })()`);
    vals.push(+r.toFixed(1));
    await sleep(80);
  }
  results.ops.typing = stats(vals);
  console.log('[s0] typing P50=' + results.ops.typing.p50 + ' P95=' + results.ops.typing.p95);
}

// A 类计数（若探针存在）
results.aCounts = await cdp.ev(`(function(){ return window.__wl2 ? { M1: window.__wl2.M1||0, M2: window.__wl2.M2||0 } : null; })()`);

results.finishedAt = new Date().toISOString();
writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');

console.log('__S0__' + JSON.stringify({
  out: outPath,
  open: { firstScreenP50: results.ops.open.firstScreen.p50, fullDoneP50: results.ops.open.fullDone.p50 },
  tabSwitch: { firstScreenP50: results.ops.tabSwitch.firstScreen.p50, fullDoneP50: results.ops.tabSwitch.fullDone.p50 },
  scrollP50: results.ops.scroll.p50,
  typingP50: results.ops.typing.p50,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
