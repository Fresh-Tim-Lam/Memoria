/**
 * task-63 P0：快速拖滚动条到底（真实用户路径，71b3f40f 修的正是它）
 *
 * 序列：打开 08 章（惰性）→ 一次性 scrollTop = scrollHeight（模拟拖到底）→ 立即回 50%
 * 测：
 *  1. 最大帧间隔（目标 ≤100ms）
 *  2. 长冻结次数（>500ms）
 *  3. 到达后视口正常（占位清零、公式已排、文本正确）
 *  4. flush batch capped 日志次数
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

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:/.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');

// 收日志
const logs = [];
cdp.ws.addEventListener('message', (e) => {
  let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : String(e.data)); } catch { return; }
  if (m.method === 'Runtime.consoleAPICalled') {
    const args = (m.params && m.params.args) || [];
    const txt = args.map(a => a.value === undefined ? (a.description || '') : String(a.value)).join(' ');
    if (/lazy/i.test(txt)) logs.push(txt);
  }
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
// 默认惰性（清钩子）
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

// 装探针
await cdp.ev(`(function(){
  if(window.__p0) return 1;
  var P={gaps:[],on:false,last:0}; window.__p0=P;
  P.start=function(){P.gaps=[];P.last=performance.now();P.on=true;
    function t(){if(!P.on)return;var n=performance.now();P.gaps.push(n-P.last);P.last=n;requestAnimationFrame(t);}
    requestAnimationFrame(t);};
  P.stop=function(){P.on=false;var g=P.gaps.filter(function(x){return isFinite(x)&&x>0;}).sort(function(a,b){return a-b;});
    var n=g.length; return {count:n,max:n?+g[n-1].toFixed(1):null,p95:n?+g[Math.floor(n*0.95)].toFixed(1):null,
      over100:g.filter(function(x){return x>100;}).length, over500:g.filter(function(x){return x>500;}).length,
      over1000:g.filter(function(x){return x>1000;}).length};};
  P.viewState=function(){
    var p=document.getElementById('preview-pane'), pv=document.getElementById('preview');
    if(!p||!pv) return null;
    var cc=pv.querySelector('.-preview-content')||pv;
    var pr=p.getBoundingClientRect();
    var phV=0, untyped=0, mj=0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)phV++;});
    pv.querySelectorAll('span.-math:not(:has(mjx-container))').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)untyped++;});
    pv.querySelectorAll('mjx-container').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)mj++;});
    return { scrollTop:+p.scrollTop.toFixed(0), scrollHeight:p.scrollHeight, phTotal:cc.querySelectorAll('.-pv-placeholder').length,
             phInViewport:phV, untypedInViewport:untyped, mjxInViewport:mj, mjxTotal:pv.querySelectorAll('mjx-container').length };
  };
  return 1;
})()`);

// 打开文档
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 8; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
await sleep(3000);

// 包 typesetPromise 记单次耗时（在拖拽前装，拖拽后取）
await cdp.ev(`(function(){
  window.__ts = [];
  var MJ = window.MathJax;
  if (!MJ || typeof MJ.typesetPromise !== 'function') { window.__tsErr = 'no typesetPromise'; return 1; }
  if (MJ.__tsWrapped) return 1;
  var orig = MJ.typesetPromise.bind(MJ);
  MJ.typesetPromise = function(items){
    var n = 0;
    try { if (items && items.length) { for (var i=0;i<items.length;i++) n += (items[i].querySelectorAll ? items[i].querySelectorAll('span.-math, .-math-block').length : 0); } } catch(e){}
    var t = performance.now();
    var pr = orig(items);
    if (pr && pr.then) pr.then(function(){ window.__ts.push({ n: n, ms: +(performance.now()-t).toFixed(1) }); },
                               function(){ window.__ts.push({ n: n, ms: +(performance.now()-t).toFixed(1), err: 1 }); });
    else window.__ts.push({ n: n, ms: +(performance.now()-t).toFixed(1) });
    return pr;
  };
  MJ.__tsWrapped = true;
  return 1;
})()`);

const before = await cdp.ev('window.__p0.viewState()');
console.log('=== 拖前 ===');
console.log('  ' + JSON.stringify(before));

// ⭐ 模拟"快速拖滚动条"：必须在**多帧内连续扫过**，否则 IO 只报告终态附近，
//    pending 永远到不了 200，测不到封顶逻辑（v1 的教训：一次赋值 scrollTop 只物化 120 块）。
logs.length = 0;
// 安装 longtask + 单一 rAF 循环（同时记 gap/mjx/ph/st，避免两个 rAF 循环互相干扰）
await cdp.ev(`(function(){
  window.__lt = [];
  try {
    var po = new PerformanceObserver(function(list){
      list.getEntries().forEach(function(e){ window.__lt.push({start:+e.startTime.toFixed(0), dur:+e.duration.toFixed(1)}); });
    });
    po.observe({entryTypes:['longtask']});
    window.__ltPO = po;
  } catch(e) { window.__ltErr = String(e&&e.message); }
  // 并入 __p0.start（唯一 rAF 循环），额外记 mjx/ph 增量
  var P = window.__p0;
  P.start = function(){
    P.gaps = []; P.frames = []; P.last = performance.now(); P.on = true;
    function t(){
      if(!P.on) return;
      var now = performance.now();
      var gap = now - P.last; P.last = now;
      P.gaps.push(gap);
      var pv = document.getElementById('preview');
      var cc = pv ? (pv.querySelector('.-preview-content') || pv) : null;
      var pane = document.getElementById('preview-pane');
      P.frames.push({
        gap: +gap.toFixed(1),
        mjx: pv ? pv.querySelectorAll('mjx-container').length : -1,
        ph: cc ? cc.querySelectorAll('.-pv-placeholder').length : -1,
        st: pane ? Math.round(pane.scrollTop) : -1
      });
      requestAnimationFrame(t);
    }
    requestAnimationFrame(t);
  };
  return 1;
})()`);
await cdp.ev('window.__p0.start()');
const t0 = Date.now();
// 分 10 帧快速扫到底（每帧 ~16ms，模拟拖拽），再立即回 50%
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(s / 10).toFixed(2)}; return 1; })()`);
  await sleep(16);
}
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5; return 1; })()`);
// 让物化完成
await sleep(5000);
const frames = await cdp.ev('window.__p0.stop()');
const elapsed = Date.now() - t0;
// 取归因数据
const longtasks = await cdp.ev('(function(){ return window.__lt || []; })()');
const frameDetail = await cdp.ev('(function(){ return (window.__p0.frames||[]).slice(0,300); })()');
const tsCalls = await cdp.ev('(function(){ return (window.__ts||[]).slice(0,60); })()');

const after = await cdp.ev('window.__p0.viewState()');
const cappedLogs = logs.filter(l => /flush batch capped|capped/i.test(l));
const matLogs = logs.filter(l => /materializ/i.test(l));

console.log('');
console.log('=== 拖到底 → 回 50% ===');
console.log('  帧: ' + JSON.stringify(frames));
console.log('  用时: ' + elapsed + 'ms');
console.log('  拖后状态: ' + JSON.stringify(after));
console.log('  capped 日志数: ' + cappedLogs.length);
console.log('  materialize 日志数: ' + matLogs.length);
if (cappedLogs.length) console.log('  capped 样本: ' + JSON.stringify(cappedLogs.slice(0, 5)));

const out = {
  head: '71b3f40f', doc: DOC, mode: 'drag-to-bottom-multiframe',
  before, after, frames, elapsedMs: elapsed,
  cappedLogCount: cappedLogs.length,
  cappedSamples: cappedLogs.slice(0, 10),
  matLogCount: matLogs.length,
  matSamples: matLogs.slice(0, 5),
  longtasks: longtasks || [],
  frameDetail: frameDetail || [],
  typesetCalls: tsCalls || [],
  pass: {
    maxGapUnder100: frames && frames.max !== null && frames.max <= 100,
    noFreeze500: frames && frames.over500 === 0,
    viewportClean: after && after.phInViewport === 0,
    formulasTypeset: after && after.untypedInViewport === 0,
    cappedActive: cappedLogs.length > 0,
  },
};
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('');
console.log('__P0__' + JSON.stringify(out.pass) + ' maxGap=' + (frames && frames.max) + ' over500=' + (frames && frames.over500) + ' capped=' + cappedLogs.length);
console.log('');
console.log('=== 350ms 归因 ===');
if (frameDetail && frameDetail.length) {
  // 找 maxGap 帧
  let mi = 0;
  for (let i = 1; i < frameDetail.length; i++) if (frameDetail[i].gap > frameDetail[mi].gap) mi = i;
  const mf = frameDetail[mi];
  const prevMjx = mi > 0 ? frameDetail[mi - 1].mjx : frameDetail[0].mjx;
  const prevPh = mi > 0 ? frameDetail[mi - 1].ph : frameDetail[0].ph;
  console.log('  maxGap 帧 idx=' + mi + ' gap=' + mf.gap + 'ms');
  console.log('    mjx: ' + prevMjx + ' → ' + mf.mjx + '（增量 ' + (mf.mjx - prevMjx) + '）');
  console.log('    ph : ' + prevPh + ' → ' + mf.ph + '（物化 ' + (prevPh - mf.ph) + ' 块）');
  console.log('    scrollTop=' + mf.st);
  console.log('  ★ 归因: ' + ((mf.mjx - prevMjx) > 100 ? 'styleset（mjx 暴增 ' + (mf.mjx - prevMjx) + '）' : (prevPh - mf.ph) > 0 ? 'DOM 物化（' + (prevPh - mf.ph) + ' 块）' : '其它（mjx 与 ph 均无显著变化）'));
  out.attribution = { maxGapFrame: mi, gap: mf.gap, mjxDelta: mf.mjx - prevMjx, phDelta: prevPh - mf.ph,
    verdict: ((mf.mjx - prevMjx) > 100 ? 'typeset' : (prevPh - mf.ph) > 0 ? 'dom-materialize' : 'other') };
  // 打印所有 gap>100 帧
  console.log('  所有 gap>100ms 帧:');
  frameDetail.forEach((f, i) => {
    if (f.gap > 100) {
      const pm = i > 0 ? frameDetail[i - 1].mjx : f.mjx;
      const pp = i > 0 ? frameDetail[i - 1].ph : f.ph;
      console.log('    idx=' + i + ' gap=' + f.gap + 'ms mjx+' + (f.mjx - pm) + ' ph-' + (pp - f.ph));
    }
  });
}
if (tsCalls && tsCalls.length) {
  const total = tsCalls.reduce((s, x) => s + x.ms, 0);
  const totalN = tsCalls.reduce((s, x) => s + (x.n || 0), 0);
  const maxCall = tsCalls.reduce((a, b) => (b.ms > a.ms ? b : a), tsCalls[0]);
  console.log('  typesetPromise 调用 ' + tsCalls.length + ' 次, 累计 ' + total.toFixed(1) + 'ms, 公式 ' + totalN + ' 个');
  console.log('    单次最慢: ' + maxCall.ms + 'ms（' + (maxCall.n || 0) + ' 公式）');
  if (totalN > 0) console.log('    平均: ' + (total / totalN).toFixed(3) + 'ms/公式');
  out.typesetSummary = { calls: tsCalls.length, totalMs: +total.toFixed(1), totalFormulas: totalN,
    maxCallMs: maxCall.ms, maxCallN: maxCall.n || 0, perFormulaMs: totalN > 0 ? +(total / totalN).toFixed(3) : null };
}
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
