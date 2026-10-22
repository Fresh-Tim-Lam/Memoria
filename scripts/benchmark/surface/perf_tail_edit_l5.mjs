/**
 * W3.3 / L5 归因探针：pred 模式为什么让「编辑态 + 程序化滚动」的点击落空。
 * 复刻 lazy_gate L5 的前半段：50% 定位 → settle → 编辑态 → 选可见正文块 → 受信任点击/输入。
 * 记录点击前后 scrollTop、pick 坐标处的 elementFromPoint、caret 所属块、块是否被换出。
 * 同实例交替 legacy / pred。
 *
 * 用法: node scripts/benchmark/surface/perf_tail_edit_l5.mjs <port> <out.json> [--trials 4]
 */
import { writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function arg(name, def) { const i = process.argv.indexOf('--' + name); if (i < 0) return def; const v = process.argv[i + 1]; return v && !v.startsWith('--') ? v : true; }
const port = Number(process.argv[2]); const outPath = process.argv[3];
if (!port || !outPath) { console.error('usage: node perf_tail_edit_l5.mjs <port> <out.json>'); process.exit(2); }
const TRIALS = Number(arg('trials', 4));
const DOC = arg('doc', '教材/08_第8章_差错控制编码.md');

async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000);
    ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return;
    const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 300000) { return new Promise((res, rej) => { const id = ++this._id;
    const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs);
    this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } });
    this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr, awaitPromise = true) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise, userGesture: true });
    if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || '')); return r.result ? r.result.value : undefined; }
  async waitFor(expr, timeoutMs = 90000, stepMs = 200) { const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`, false)) return true; } catch { /* */ } await sleep(stepMs); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}
let page = null;
for (let a = 0; a < 60; a++) { try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`);
  page = (l || []).find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+\//.test(t.url || '') && !/devtools/.test(t.url || '') && t.webSocketDebuggerUrl);
  if (page) break; } catch { /* */ } await sleep(1000); }
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
if (!(await cdp.waitFor('window.MemoriaApp && window.MemoriaApp.openFile', 120000))) { console.error('app not ready'); process.exit(2); }

async function click(x, y) {
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none', buttons: 0 });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 });
}
async function typeText(t) { await cdp.send('Input.insertText', { text: t }); }

const SETUP = `(function(){
  window.__MEMORIA_LAZY = true;
  try { localStorage.setItem('memoria.perf.lazy','1'); } catch(e) {}
  var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b)b.click();
  if(window.__l5) return 1;
  var L={}; window.__l5=L;
  L.quiet=async function(maxMs){
    maxMs=maxMs||45000; var t0=performance.now(),lastKey=null,stable=0,last=null;
    while(performance.now()-t0<maxMs){
      await new Promise(function(r){setTimeout(r,250);});
      var s=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null; if(!s)continue; last=s;
      var key=s.materialized+'|'+s.placeholders+'|'+s.evictTotal;
      if(key===lastKey)stable++;else{stable=0;lastKey=key;}
      if(stable>=5)return {quietMs:+(performance.now()-t0).toFixed(1),stats:s};
    }
    return {quietMs:+(performance.now()-t0).toFixed(1),stats:last,timeout:true};
  };
  L.scrollToLine=function(targetLine){
    var pane=document.getElementById('preview-pane'),pv=document.getElementById('preview');
    var cc=pv?pv.querySelector('.-preview-content'):null; if(!pane||!cc)return null;
    var kids=cc.children,n=kids.length; if(!n)return null;
    function lineOf(el,w){var v=parseInt(el.getAttribute(w),10);return isNaN(v)?null:v;}
    var lo=0,hi=n-1,found=n;
    while(lo<=hi){var mid=(lo+hi)>>1;var se=lineOf(kids[mid],'data--src-line-end');if(se===null)se=lineOf(kids[mid],'data--src-line');
      if(se!==null&&se>=targetLine){found=mid;hi=mid-1;}else{lo=mid+1;}}
    if(found>=n)found=n-1; var el=kids[found]; if(!el)return null;
    try{pane.style.scrollBehavior='auto';}catch(e){}
    var paneTop=pane.getBoundingClientRect().top, elTop=el.getBoundingClientRect().top;
    var want=pane.scrollTop+(elTop-paneTop); pane.scrollTop=want;
    if(Math.abs(pane.scrollTop-want)>1)pane.scrollTop=want;
    return {targetBlock:parseInt(el.getAttribute('data--block-index'),10),scrollTop:+pane.scrollTop.toFixed(1),totalBlocks:window.__MEMORIA_WORKSET_STATS().totalBlocks};
  };
  L.settle=async function(){
    var t0=performance.now();
    for(var i=0;i<80;i++){
      await new Promise(function(r){setTimeout(r,60);});
      var pane=document.getElementById('preview-pane'),cc=document.querySelector('#preview .-preview-content');
      var pr=pane.getBoundingClientRect(),ph=0,real=0;
      for(var k=0;k<cc.children.length;k++){var el=cc.children[k];var r=el.getBoundingClientRect();
        if(r.bottom<=pr.top+1||r.top>=pr.bottom-1)continue;
        if(el.classList.contains('-pv-placeholder'))ph++;else real++;}
      if(ph===0&&real>=1){return {ms:Date.now()-t0,ph:ph,real:real};}
    }
    return {timeout:true};
  };
  L.pick=function(){
    var pane=document.getElementById('preview-pane'),cc=document.querySelector('#preview .-preview-content');
    var pr=pane.getBoundingClientRect(),kids=cc.children;
    for(var i=0;i<kids.length;i++){
      var el=kids[i]; if(el.classList.contains('-pv-placeholder'))continue;
      var r=el.getBoundingClientRect(); if(r.bottom<=pr.top+4||r.top>=pr.bottom-4)continue;
      var t=(el.textContent||'').replace(/\\s+/g,' ').trim(); if(t.length<60)continue;
      if(el.querySelector('pre,table,svg,mjx-container'))continue; if(el.closest('pre,table'))continue;
      var walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,null),node=null,x;
      while((x=walker.nextNode())){if((x.nodeValue||'').trim().length>20){node=x;break;}}
      if(!node)continue;
      var rng=document.createRange(); var off=Math.min(4,node.nodeValue.length-2);
      rng.setStart(node,off);rng.setEnd(node,Math.min(node.nodeValue.length,off+1));
      var rects=rng.getClientRects(),rr=rects.length?rects[0]:rng.getBoundingClientRect();
      if(!rr||(!rr.width&&!rr.height))continue;
      // 关键：点击行必须**完整落在 pane 可见区内**（否则 elementFromPoint 会命中工具栏，
      // 门禁 L5 的 latent flake 正是块与视口相交、但文字行被顶部裁剪）。
      if(rr.top < pr.top+2 || rr.bottom > pr.bottom-2 || rr.left < pr.left+2 || rr.right > pr.right-2) continue;
      return {blockIndex:+el.getAttribute('data--block-index'),x:Math.round(rr.left+Math.max(1,rr.width/2)),y:Math.round(rr.top+rr.height/2),
        text:t.slice(0,80),blockTop:+r.top.toFixed(1),blockBottom:+r.bottom.toFixed(1),scrollTop:+pane.scrollTop.toFixed(1),paneTop:+pr.top.toFixed(1),
        evictTotal:(window.__MEMORIA_WORKSET_STATS()||{}).evictTotal};
    }
    return null;
  };
  L.probe=function(p){
    var pane=document.getElementById('preview-pane');
    var e=document.elementFromPoint(p.x,p.y);
    var el=e&&e.closest?e.closest('[data--block-index]'):null;
    var s=window.getSelection(),r=s&&s.rangeCount?s.getRangeAt(0):null;
    function info(node,off){var el=node?(node.nodeType===1?node:node.parentElement):null;var b=el&&el.closest?el.closest('[data--block-index]'):null;
      return {offset:off,blockIndex:b?parseInt(b.getAttribute('data--block-index'),10):null};}
    return {scrollTop:+pane.scrollTop.toFixed(1),elementBlock:el?parseInt(el.getAttribute('data--block-index'),10):null,
      elementTag:e?e.tagName:null, caret:r?{collapsed:s.isCollapsed,anchor:info(r.startContainer,r.startOffset),focus:info(r.endContainer,r.endOffset),text:s.toString().slice(0,40)}:null,
      evictTotal:(window.__MEMORIA_WORKSET_STATS()||{}).evictTotal};
  };
  L.editMode=function(on){var E=window.MemoriaEditHandler;if(!E)return null;if(on&&!E.editMode&&E.toggleEditMode)E.toggleEditMode();if(!on&&E.editMode&&E.toggleEditMode)E.toggleEditMode();return !!E.editMode;};
  L.blockState=function(i){
    var el=document.querySelector('#preview .-preview-content [data--block-index="'+i+'"]');
    return {exists:!!el,ph:!!(el&&el.classList.contains('-pv-placeholder')),has:el?(el.textContent||'').indexOf('ZGATE')>=0:false,
      text:el?(el.textContent||'').replace(/\\s+/g,' ').trim().slice(0,120):null};
  };
  return 1;
})()`;

async function openDoc() {
  await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile('homework/README.md', {skipNav:true}); } catch(e){} return 1; })()`);
  await sleep(1500);
  const r = await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); return 'ok'; } catch(e){ return 'ERR:'+e.message; } })()`);
  if (r !== 'ok') { console.error('openFile:', r); process.exit(3); }
  for (let attempt = 0; attempt < 4; attempt++) {
    const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
    if (s && s.totalBlocks > 3900) break;
    await cdp.ev(`(async()=>{ try { await window.MemoriaApp.openFile(${JSON.stringify(DOC)}, {skipNav:true}); } catch(e){} return 1; })()`);
    await sleep(2500);
  }
  return await cdp.ev('window.__l5.quiet(60000)');
}
await cdp.ev(SETUP);
console.log('[open]', JSON.stringify(await openDoc()));
const st0 = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false);
if (!st0 || st0.totalBlocks < 3900) { console.error('OPEN FAILED'); process.exit(5); }

const R = { schema: 'memoria-tail-edit-l5/v1', at: new Date().toISOString(), scriptSha256: createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex'), trials: [] };

async function trial(mode, i) {
  await cdp.ev(`window.__MEMORIA_TAIL_LAYOUT.setMode(${JSON.stringify(mode)})`, false);
  await cdp.ev('window.__l5.scrollToLine(0)'); await cdp.ev('window.__l5.quiet(20000)');
  // 文档行数：用 DOM 最大 src-line-end 近似
  const totalLines = await cdp.ev(`(function(){var cc=document.querySelector('#preview .-preview-content');var m=0;
    for(var i=0;i<cc.children.length;i++){var v=parseInt(cc.children[i].getAttribute('data--src-line-end'),10);if(v>m)m=v;}return m;})()`, false);
  const sc = await cdp.ev(`window.__l5.scrollToLine(${Math.round(totalLines * 0.5)})`);
  const settle = await cdp.ev('window.__l5.settle()');
  await cdp.ev('window.__l5.editMode(true)'); await sleep(400);
  const pick = await cdp.ev('window.__l5.pick()');
  const before = pick ? await cdp.ev(`window.__l5.probe(${JSON.stringify({ x: pick.x, y: pick.y })})`, false) : null;
  if (!pick) { const row = { mode, i, ok: false, reason: 'no-pick', totalLines, sc, settle }; R.trials.push(row); return row; }
  await click(pick.x, pick.y); await sleep(250);
  const afterClick = await cdp.ev(`window.__l5.probe(${JSON.stringify({ x: pick.x, y: pick.y })})`, false);
  await typeText('ZGATE'); await sleep(800);
  const afterType = await cdp.ev(`window.__l5.blockState(${pick.blockIndex})`, false);
  const probeAfter = await cdp.ev(`window.__l5.probe(${JSON.stringify({ x: pick.x, y: pick.y })})`, false);
  const during = await cdp.ev(`(function(i){var el=document.querySelector('#preview .-preview-content [data--block-index="'+i+'"]');
    var ws=window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null;
    return {exists:!!el,ph:!!(el&&el.classList.contains('-pv-placeholder')),evictTotal:ws?ws.evictTotal:null};})(${pick.blockIndex})`, false);
  await cdp.ev('window.__l5.editMode(false)');
  const row = { mode, i, ok: !!(afterType && afterType.has), totalLines, sc, settle, pick, before, afterClick, afterType, probeAfter, during };
  console.log(`[${mode}#${i}] ok=${row.ok} block=${pick.blockIndex} pick=(${pick.x},${pick.y}) scrollTop ${pick.scrollTop}->${afterClick && afterClick.scrollTop}`
    + ` elementBlock=${before && before.elementBlock}->${afterClick && afterClick.elementBlock}`
    + ` caret=${JSON.stringify(afterClick && afterClick.caret && afterClick.caret.anchor)}`
    + ` afterType=${JSON.stringify(afterType)} during=${JSON.stringify(during)}`);
  R.trials.push(row);
  return row;
}

for (let i = 0; i < TRIALS; i++) {
  await trial('legacy', i);
  await trial('pred', i);
}
const okRate = (m) => { const a = R.trials.filter((t) => t.mode === m); return { n: a.length, ok: a.filter((t) => t.ok).length }; };
R.summary = { legacy: okRate('legacy'), pred: okRate('pred') };
writeFileSync(outPath, JSON.stringify(R, null, 2), 'utf8');
console.log('[SUMMARY]', JSON.stringify(R.summary));
cdp.close(); setTimeout(() => process.exit(0), 300).unref();
