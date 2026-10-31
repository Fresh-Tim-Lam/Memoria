#!/usr/bin/env node
/**
 * p5perf_ab_interleaved.mjs —— task-47 L1：wall-time **同窗口交错** A/B 对照
 *
 * 为什么必须交错：先跑完 A 再跑完 B，环境漂移（CPU 竞争、GC、缓存）会被误当"差异"。
 * 本脚本按 **A→B→A→B→…** 交错，每轮记录两侧耗时，最后给 median/p95/IQR/CV 与比值。
 *
 * 输出：{ operation, side, median, p95, iqr, cv } + ratio + 并发数 + argv + 脚本 sha256
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import os from 'node:os';
import { execSync } from 'node:child_process';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('t')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('e')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(m, p = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method: m, params: p })); }); }
  async ev(x) { const r = await this.send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true, userGesture: true }); if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); } return r.result ? r.result.value : undefined; }
  async waitFor(x, t = 180000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('timeout: ' + x.slice(0, 70)); await sleep(150); } }
  close() { try { this.ws.close(); } catch { /* */ } }
}

function stats(arr) {
  const a = arr.filter((x) => typeof x === 'number' && isFinite(x)).slice().sort((x, y) => x - y);
  if (!a.length) return { n: 0, median: null, p95: null, iqr: null, cv: null, min: null, max: null };
  const q = (p) => { const i = (a.length - 1) * p; const lo = Math.floor(i), hi = Math.ceil(i); return lo === hi ? a[lo] : a[lo] + (a[hi] - a[lo]) * (i - lo); };
  const mean = a.reduce((s, x) => s + x, 0) / a.length;
  const sd = Math.sqrt(a.reduce((s, x) => s + (x - mean) ** 2, 0) / a.length);
  const q1 = q(0.25), q3 = q(0.75);
  return {
    n: a.length,
    median: +q(0.5).toFixed(2),
    p95: +q(0.95).toFixed(2),
    iqr: +(q3 - q1).toFixed(2),
    cv: mean > 0 ? +(sd / mean).toFixed(4) : null,
    min: +a[0].toFixed(2),
    max: +a[a.length - 1].toFixed(2),
  };
}

function countBrowsers() {
  try {
    const ps = execSync('powershell -NoProfile -Command "(Get-Process -Name msedge,msedgewebview2,chrome -ErrorAction SilentlyContinue | Measure-Object).Count"', { encoding: 'utf8', timeout: 20000 });
    return parseInt(ps.trim(), 10) || 0;
  } catch { return -1; }
}

const port = Number(process.argv[2] || 9500);
const opsArg = process.argv[3] || 'tabSwitch,kpHover,select,format,paste,find,save,typing,structEdit,undo,viewSwitch,scroll';
const cycles = Number(process.argv[4] || 5);
const outPath = process.argv[5] || '';
const file = 'corpus/03-block-boundaries.md';

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.waitFor('!!window.MemoriaApp && !!window.state && !!window.MemoriaSurface', 120000);

async function openDoc() {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
  await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 40000);
  await sleep(700);
}
async function setSurface(s) {
  await cdp.ev(`window.MemoriaSurface.switchTo(${JSON.stringify(s)})`);
  await cdp.waitFor(`window.MemoriaSurface.current() === ${JSON.stringify(s)}`, 60000);
  await sleep(400);
  return await cdp.ev('window.MemoriaSurface.current()');
}
async function setMode(mode) {
  for (let i = 0; i < 8; i++) {
    const cur = await cdp.ev('(window.state||{}).viewMode || null');
    if (cur === mode) { await sleep(400); return true; }
    await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="${mode}"]');if(b){b.click();return 1;}return 0;})()`);
    await sleep(300);
  }
  return (await cdp.ev('(window.state||{}).viewMode')) === mode;
}

/* ── 每个操作在页面内执行一次并返回耗时(ms) ── */
const RUN_OP = (opName) => `(async function(){
  var now = function(){ return performance.now(); };
  var nf = function(){ return new Promise(function(r){ requestAnimationFrame(function(){ r(); }); }); };
  var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  var op = ${JSON.stringify(opName)};
  var t0 = now();
  try {
    if (op === 'typing') {
      var els=Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      var t=null; for(var i=0;i<els.length;i++){var c=String(els[i].className||'');
        if(c.indexOf('-code-block')<0&&c.indexOf('-table')<0&&c.indexOf('-math-block')<0&&c.indexOf('-mermaid')<0&&c.indexOf('-blank-block')<0){t=els[i];break;}}
      if(!t) return { err:'no-editable' };
      var r=t.getBoundingClientRect();
      t.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:r.left+20,clientY:r.top+8}));
      t.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:r.left+20,clientY:r.top+8}));
      await sleep(80);
      t0 = now();
      window.MemoriaEditSync.insertText('k');
      await nf(); await nf();
    } else if (op === 'structEdit') {
      var els2=Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      var t2=null; for(var j=0;j<els2.length;j++){var c2=String(els2[j].className||'');
        if(c2.indexOf('-code-block')<0&&c2.indexOf('-table')<0&&c2.indexOf('-math-block')<0&&c2.indexOf('-mermaid')<0&&c2.indexOf('-blank-block')<0){t2=els2[j];break;}}
      if(!t2) return { err:'no-editable' };
      var r2=t2.getBoundingClientRect();
      t2.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:r2.left+20,clientY:r2.top+8}));
      t2.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:r2.left+20,clientY:r2.top+8}));
      await sleep(80);
      t0 = now();
      window.MemoriaEditSync.splitParagraph();
      await nf(); await nf();
    } else if (op === 'undo') {
      window.MemoriaEditSync.insertText('u');
      await sleep(120);
      t0 = now();
      window.MemoriaEditSync.undo();
      await nf(); await nf();
    } else if (op === 'viewSwitch') {
      t0 = now();
      var bs2=document.querySelector('.-view-btn[data-view="source"]'); if(bs2) bs2.click();
      await nf(); await nf();
      var bp2=document.querySelector('.-view-btn[data-view="preview"]'); if(bp2) bp2.click();
      await nf(); await nf();
    } else if (op === 'scroll') {
      var pv=document.getElementById('preview');
      var el2 = pv && pv.scrollHeight > pv.clientHeight ? pv : (document.scrollingElement||document.documentElement);
      t0 = now();
      el2.scrollTop = Math.min(el2.scrollHeight, el2.scrollTop + 1200);
      await nf(); await nf();
    } else if (op === 'tabSwitch') {
      window.MemoriaApp.openFile('corpus/01-ime-zh.md',{skipNav:true});
      await sleep(400);
      t0 = now();
      window.MemoriaApp.openFile(${JSON.stringify(file)},{skipNav:true});
      var guard = now();
      while (now() - guard < 20000) {
        if (window.state.currentPath === ${JSON.stringify(file)} &&
            document.querySelectorAll('#preview .-src-block').length > 0) break;
        await sleep(20);
      }
      await nf(); await nf();
    } else if (op === 'kpHover') {
      var item=document.querySelector('#kp-list .-kp-item');
      if(!item) return { err:'no-kp-item' };
      var ri=item.getBoundingClientRect();
      t0 = now();
      item.dispatchEvent(new MouseEvent('mouseenter',{bubbles:true,clientX:ri.left+5,clientY:ri.top+5}));
      await nf(); await nf();
      item.dispatchEvent(new MouseEvent('mouseleave',{bubbles:true}));
      await nf();
    } else if (op === 'select') {
      var els3=Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      if(els3.length<3) return { err:'not-enough-blocks' };
      t0 = now();
      var w=document.createTreeWalker(els3[1],NodeFilter.SHOW_TEXT,null); var n=w.nextNode();
      var w2=document.createTreeWalker(els3[Math.min(els3.length-1,4)],NodeFilter.SHOW_TEXT,null); var n2=w2.nextNode();
      if(!n||!n2) return { err:'no-text' };
      var rg=document.createRange(); rg.setStart(n,0); rg.setEnd(n2,Math.min(5,n2.nodeValue.length));
      var s=window.getSelection(); s.removeAllRanges(); s.addRange(rg);
      document.dispatchEvent(new Event('selectionchange'));
      await nf(); await nf();
    } else if (op === 'format') {
      var els4=Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      var t4=null; for(var k=0;k<els4.length;k++){var c4=String(els4[k].className||'');
        if(c4.indexOf('-code-block')<0&&c4.indexOf('-table')<0&&c4.indexOf('-math-block')<0&&c4.indexOf('-mermaid')<0&&c4.indexOf('-blank-block')<0){t4=els4[k];break;}}
      if(!t4) return { err:'no-editable' };
      var r4=t4.getBoundingClientRect();
      t4.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:r4.left+20,clientY:r4.top+8}));
      t4.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:r4.left+20,clientY:r4.top+8}));
      await sleep(120);
      var ww=document.createTreeWalker(t4,NodeFilter.SHOW_TEXT,null); var nn=ww.nextNode();
      if(nn){ var rr=document.createRange(); rr.setStart(nn,0); rr.setEnd(nn,Math.min(3,nn.nodeValue.length));
        var ss=window.getSelection(); ss.removeAllRanges(); ss.addRange(rr); }
      await sleep(80);
      var fb=document.querySelector('.-fmt-btn[data-fmt="bold"]');
      if(!fb) return { err:'no-fmt-btn' };
      t0 = now();
      fb.click();
      await nf(); await nf();
    } else if (op === 'paste') {
      var els5=Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      var t5=null; for(var m=0;m<els5.length;m++){var c5=String(els5[m].className||'');
        if(c5.indexOf('-code-block')<0&&c5.indexOf('-table')<0&&c5.indexOf('-math-block')<0&&c5.indexOf('-mermaid')<0&&c5.indexOf('-blank-block')<0){t5=els5[m];break;}}
      if(!t5) return { err:'no-editable' };
      var r5=t5.getBoundingClientRect();
      t5.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:r5.left+20,clientY:r5.top+8}));
      t5.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:r5.left+20,clientY:r5.top+8}));
      await sleep(120);
      t0 = now();
      try { var dt=new DataTransfer(); dt.setData('text/plain','PP');
        (document.activeElement||document.getElementById('preview')).dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:dt}));
      } catch(e){ return { err:'clipboard:'+e.message }; }
      await nf(); await nf();
    } else if (op === 'find') {
      var inp=document.querySelector('#find-input, .-find-input, input[placeholder*="查找"]');
      if(!inp) return { err:'no-find-input' };
      t0 = now();
      inp.value='第一段';
      inp.dispatchEvent(new Event('input',{bubbles:true}));
      await nf(); await nf();
    } else if (op === 'save') {
      var els6=Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      var t6=null; for(var p=0;p<els6.length;p++){var c6=String(els6[p].className||'');
        if(c6.indexOf('-code-block')<0&&c6.indexOf('-table')<0&&c6.indexOf('-math-block')<0&&c6.indexOf('-mermaid')<0&&c6.indexOf('-blank-block')<0){t6=els6[p];break;}}
      if(t6){ var r6=t6.getBoundingClientRect();
        t6.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:r6.left+20,clientY:r6.top+8}));
        t6.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:r6.left+20,clientY:r6.top+8})); }
      await sleep(120);
      window.MemoriaEditSync.insertText('Z');
      await sleep(200);
      t0 = now();
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'s',code:'KeyS',ctrlKey:true,bubbles:true}));
      await nf(); await nf();
    } else if (op === 'open') {
      t0 = now();
      window.MemoriaApp.openFile(${JSON.stringify(file)},{skipNav:true});
      var g2=now();
      while (now()-g2 < 20000) {
        if (window.state.currentPath === ${JSON.stringify(file)} && document.querySelectorAll('#preview .-src-block').length>0) break;
        await sleep(20);
      }
      await nf(); await nf();
    } else {
      return { err:'unknown-op:'+op };
    }
  } catch(e) {
    return { err: String(e && e.message || e) };
  }
  var dt = now() - t0;
  if (window.state && window.state._mathPending) { try { await window.state._mathPending; } catch(e){} }
  await nf(); await nf();
  var dt2 = now() - t0;
  return { ms: +dt.toFixed(2), msSettled: +dt2.toFixed(2) };
})()`;

const ops = opsArg.split(',').map((s) => s.trim()).filter(Boolean);
const results = {
  schema: 'memoria-p5-ab-interleaved/v1',
  mode: 'realapp',
  port,
  ops,
  cycles,
  interleaveOrder: 'A(new) -> B(legacy) per cycle',
  scriptSha256: crypto.createHash('sha256').update(fs.readFileSync(new URL(import.meta.url))).digest('hex'),
  argv: process.argv.slice(2),
  browsersAtStart: countBrowsers(),
  cpus: os.cpus().length,
  loadavg: os.loadavg(),
  startedAt: new Date().toISOString(),
  perOp: {},
};

await openDoc();

for (const op of ops) {
  const A = [];  // new
  const B = [];  // legacy
  const pairs = [];
  let errA = null, errB = null;

  for (let c = 0; c < cycles; c++) {
    // ── A：new ──
    await setSurface('new');
    await setMode('preview');
    await openDoc();
    await sleep(150);
    const ra = await cdp.ev(RUN_OP(op));
    if (ra && ra.err) errA = ra.err; else if (ra && typeof ra.msSettled === 'number') A.push(ra.msSettled);

    // ── B：legacy ──
    await setSurface('legacy');
    await setMode('preview');
    await openDoc();
    await sleep(150);
    const rb = await cdp.ev(RUN_OP(op));
    if (rb && rb.err) errB = rb.err; else if (rb && typeof rb.msSettled === 'number') B.push(rb.msSettled);

    pairs.push({ cycle: c + 1, new: ra ? ra.msSettled : null, legacy: rb ? rb.msSettled : null });
  }

  const sA = stats(A), sB = stats(B);
  const ratio = (sA.median != null && sB.median != null && sB.median > 0) ? +(sA.median / sB.median).toFixed(3) : null;
  results.perOp[op] = {
    new: sA, legacy: sB, ratioMedianNewOverLegacy: ratio,
    pairs, errA, errB,
    verdict: (errA || errB) ? 'skip:' + (errA || errB)
      : (ratio == null ? 'no-data'
        : (ratio > 1.15 ? 'SLOWER(>1.15x)' : 'ok(<=1.15x)')),
  };
  console.log('[ab] ' + op + '  new(med=' + sA.median + ' p95=' + sA.p95 + ' cv=' + sA.cv + ')' +
    '  legacy(med=' + sB.median + ' p95=' + sB.p95 + ' cv=' + sB.cv + ')' +
    '  ratio=' + ratio + '  ' + results.perOp[op].verdict +
    (errA || errB ? '  errA=' + errA + ' errB=' + errB : ''));
}

results.browsersAtEnd = countBrowsers();
results.finishedAt = new Date().toISOString();

if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__AB__' + JSON.stringify({ ok: true, out: outPath,
    summary: Object.fromEntries(Object.entries(results.perOp).map(([k, v]) => [k, v.ratioMedianNewOverLegacy])) }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
