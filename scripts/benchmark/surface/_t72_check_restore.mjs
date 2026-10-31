// task-72 正确性探针 v2：按块下标追踪同一块"排版 → 换出 → 复入视口"前后的 DOM/几何。
const port = Number(process.argv[2] || 9634);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 120000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr, awaitPromise = true) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise, userGesture: true }); if (r && r.exceptionDetails) throw new Error('eval: ' + JSON.stringify(r.exceptionDetails).slice(0, 800)); return r.result ? r.result.value : undefined; }
  close() { try { this.ws.close(); } catch { } }
}
let page = null;
for (let a = 0; a < 40; a++) { try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^http:\/\//.test(t.url || '')); if (page) break; } catch { } await sleep(1000); }
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
for (let i = 0; i < 60; i++) { if (await cdp.ev('!!(window.MemoriaApp && MemoriaApp.openFile)', false)) break; await sleep(1000); }
const DOC = '教材/08_第8章_差错控制编码.md';
await cdp.ev(`(async()=>{try{await window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true});}catch(e){return 'ERR:'+e.message} return 'ok';})()`);
for (let i = 0; i < 5; i++) { const vm = await cdp.ev('(window.state||{}).viewMode', false); if (vm !== 'preview') await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b)b.click();return 1;})()`, false); await sleep(500); }
for (let i = 0; i < 120; i++) { const s = await cdp.ev('window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null', false); if (s && s.totalBlocks > 3900) break; await sleep(250); }
await sleep(2000);

await cdp.ev(`window.__t72 = {
  settle: async function(maxMs){
    var t0 = performance.now(), last=null, stable=0;
    while (performance.now()-t0 < (maxMs||8000)) {
      await new Promise(function(r){setTimeout(r,100);});
      var s = window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null;
      if (!s) continue;
      var k = s.materialized+'|'+s.placeholders+'|'+s.evictTotal;
      if (k===last) stable++; else { stable=0; last=k; }
      if (stable>=3) return { ms: Math.round(performance.now()-t0), s:s };
    }
    return { ms: -1, s: window.__MEMORIA_WORKSET_STATS ? window.__MEMORIA_WORKSET_STATS() : null };
  },
  go: function(frac){ var p=document.getElementById('preview-pane'); p.scrollTop=Math.round((p.scrollHeight-p.clientHeight)*frac); return p.scrollTop; },
  native: function(s){ return s.replace(/MJXT72-\\d+-/g,'MJX-').replace(/MJX-\\d+-/g,'MJX-'); },
  info: function(el){
    if (!el) return null;
    var r=el.getBoundingClientRect();
    var c=el.querySelector('mjx-container');
    var svg=c?c.querySelector('svg'):null;
    return {
      idx: el.getAttribute('data--block-index'),
      srcLine: el.getAttribute('data--src-line'),
      cls: el.className,
      h: Math.round(r.height*10)/10,
      mjx: !!c,
      cdisp: c?c.getAttribute('display'):null,
      svgW: svg?svg.getAttribute('width'):null,
      svgH: svg?svg.getAttribute('height'):null,
      svgViewBox: svg?svg.getAttribute('viewBox'):null,
      style: c?c.getAttribute('style'):null,
      ce: c?c.getAttribute('contenteditable'):null,
      formula: c?c.getAttribute('data-formula'):null,
      inl: c?c.getAttribute('data--inline-math'):null,
      html: c?this.native(c.outerHTML):null,
      htmlLen: c?c.outerHTML.length:0
    };
  },
  find: function(frac){
    var pv=document.getElementById('preview');
    var pr=document.getElementById('preview-pane').getBoundingClientRect();
    var els=pv.querySelectorAll('.-math-block, .-src-block');
    var mb=null, il=null;
    for (var i=0;i<els.length;i++){
      var rr=els[i].getBoundingClientRect();
      if (rr.top>=pr.top-10 && rr.bottom<=pr.bottom+10) {
        var c=els[i].querySelector('mjx-container');
        if (!c) continue;
        if (els[i].classList.contains('-math-block') && !mb) mb=els[i];
        else if (!els[i].classList.contains('-math-block') && c.getAttribute('display')!=='true' && !il) il=els[i];
      }
      if (mb && il) break;
    }
    return { block: mb?this.info(mb):null, inline: il?this.info(il):null,
      math: (function(){var d=window.MathJax&&MathJax.startup&&MathJax.startup.document;var n=0,de=0;if(d&&d.math){for(var it of d.math){n++;if(it.typesetRoot&&!it.typesetRoot.isConnected)de++;}}return {items:n,detached:de};})(),
      cache: window.__MEMORIA_TYPESET_CACHE_STATS?window.__MEMORIA_TYPESET_CACHE_STATS():null,
      ws: window.__MEMORIA_WORKSET_STATS?window.__MEMORIA_WORKSET_STATS():null };
  },
  byIdx: function(i){ var el=document.querySelector('#preview [data--block-index="'+i+'"]'); return { block:this.info(el) }; }
}; 1`);

await cdp.ev('window.__t72.go(0.5)');
await sleep(300);
await cdp.ev('window.__t72.settle(9000)');
const s1 = await cdp.ev('window.__t72.find(0.5)', false);
if (!s1.block && !s1.inline) { console.error('no math in viewport at 50%'); process.exit(6); }
const bidx = s1.block ? s1.block.idx : null;
const iidx = s1.inline ? s1.inline.idx : null;

await cdp.ev('window.__t72.go(0.03)');
await sleep(300);
await cdp.ev('window.__t72.settle(9000)');
const s2 = await cdp.ev('window.__t72.find(0.03)', false);

await cdp.ev('window.__t72.go(0.5)');
await sleep(300);
await cdp.ev('window.__t72.settle(9000)');
const b3 = bidx != null ? await cdp.ev(`window.__t72.byIdx(${bidx})`, false) : { block: null };
const i3 = iidx != null ? await cdp.ev(`window.__t72.byIdx(${iidx})`, false) : { block: null };
const c3 = await cdp.ev('window.__MEMORIA_TYPESET_CACHE_STATS ? window.__MEMORIA_TYPESET_CACHE_STATS() : null', false);
const m3 = await cdp.ev(`(function(){var d=window.MathJax&&MathJax.startup&&MathJax.startup.document;var n=0,de=0;if(d&&d.math){for(var it of d.math){n++;if(it.typesetRoot&&!it.typesetRoot.isConnected)de++;}}return {items:n,detached:de};})()`, false);

function cmp(a, b) {
  if (!a || !b) return { ok: false, why: 'missing', a: !!a, b: !!b };
  const keys = ['cls', 'mjx', 'cdisp', 'svgW', 'svgH', 'svgViewBox', 'style', 'html'];
  const diff = {};
  for (const k of keys) if (String(a[k]) !== String(b[k])) diff[k] = { before: String(a[k]).slice(0, 160), after: String(b[k]).slice(0, 160) };
  return { ok: Object.keys(diff).length === 0, diff, hBefore: a.h, hAfter: b.h, dh: +(b.h - a.h).toFixed(1) };
}
console.log(JSON.stringify({
  cacheEnabled: await cdp.ev('window.__MEMORIA_TYPESET_CACHE !== false', false),
  firstBlock: s1.block, firstInline: s1.inline, math1: s1.math, cache1: s1.cache, ws1: s1.ws,
  awayBlock: s2.block, awayInline: s2.inline, math2: s2.math, ws2: s2.ws,
  afterBlock: b3.block, afterInline: i3.block, math3: m3, cache3: c3,
  cmpBlock: cmp(s1.block, b3.block), cmpInline: cmp(s1.inline, i3.block),
  sameIdxs: { bidx: bidx, bidxAfter: b3.block && b3.block.idx, iidx: iidx, iidxAfter: i3.block && i3.block.idx }
}, null, 1));
cdp.close();
setTimeout(() => process.exit(0), 200);
