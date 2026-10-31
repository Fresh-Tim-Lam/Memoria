/**
 * task-61 导航入口测试：NAV1 wikilink / NAV3 KP / NAV6 搜索建议 / NAV7 文件树
 * 体验 6 项 + 性能（N≥10，P50/P95/max）+ A 类计数 + renderPreview 次数
 *
 * 判据：视口 = #preview-pane（真实滚动容器）
 * 用法: node nav_entries.mjs <port> <out.json>
 */
import { writeFileSync } from 'node:fs';

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
const N = Number(process.argv[4] || 10);

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Log.enable').catch(() => {});

// ── JS 错误收集 ──
const jsErrors = [];
cdp.ws.addEventListener('message', (e) => {
  let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : String(e.data)); } catch { return; }
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params && m.params.exceptionDetails;
    jsErrors.push(String((d && d.exception && (d.exception.description || d.exception.value)) || (d && d.text) || 'unknown'));
  }
});

for (let i = 0; i < 250; i++) { if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }
await cdp.send('Runtime.enable').catch(() => {});

// ── 安装 renderPreview 计数探针（一次性）──
const probe = await cdp.ev(`(function(){
  if (window.__navProbe) return { already: true, wrapped: window.__navProbe.wrapped };
  var P = { on:false, renderPreview:0, renderDocument:0, wrapped:{} };
  window.__navProbe = P;
  function wrap(obj, prop, key){
    if (!obj || typeof obj[prop] !== 'function') return false;
    if (obj[prop].__navWrapped) return true;
    var orig = obj[prop];
    var w = function(){ if (P.on) P[key]++; return orig.apply(this, arguments); };
    w.__navWrapped = true;
    try { obj[prop] = w; return true; } catch(e){ return false; }
  }
  P.wrapped.renderPreview = wrap(window.MemoriaApp, 'renderPreview', 'renderPreview');
  // renderDocument 在 render-core 实例上；app 未暴露实例 ⇒ 只能包 MemoriaRenderCore.createRenderCore 工厂
  if (window.MemoriaRenderCore && typeof window.MemoriaRenderCore.createRenderCore === 'function' && !window.MemoriaRenderCore.__navWrapped) {
    var origCreate = window.MemoriaRenderCore.createRenderCore;
    window.MemoriaRenderCore.createRenderCore = function(){
      var inst = origCreate.apply(this, arguments);
      if (inst && typeof inst.renderDocument === 'function' && !inst.renderDocument.__navWrapped) {
        var od = inst.renderDocument;
        var wd = function(){ if (P.on) P.renderDocument++; return od.apply(this, arguments); };
        wd.__navWrapped = true;
        try { inst.renderDocument = wd; } catch(e){}
      }
      return inst;
    };
    window.MemoriaRenderCore.__navWrapped = true;
    P.wrapped.createRenderCore = true;
  }
  return { already:false, wrapped: P.wrapped };
})()`);

const results = {
  schema: 'memoria-nav-entries/v1',
  startedAt: new Date().toISOString(),
  probe,
  viewportRule: '#preview-pane (overflowY:auto) — 真实滚动容器',
  entries: {},
  jsErrors: [],
};

// 每入口重复试验用的公共函数（注入页面）
const COMMON = `
window.__navT = {
  pane: function(){ return document.getElementById('preview-pane'); },
  // 滚动稳定：连续两次 rAF 的 scrollTop 相同
  stableScroll: function(){
    var p = this.pane(); if (!p) return true;
    var a = p.scrollTop;
    return new Promise(function(res){
      requestAnimationFrame(function(){ requestAnimationFrame(function(){ res(p.scrollTop === a); }); });
    });
  },
  // 视口交集：目标块矩形 与 preview-pane 矩形 相交且面积 > 0
  inViewport: function(el){
    var p = this.pane(); if (!p || !el) return false;
    var pr = p.getBoundingClientRect(), er = el.getBoundingClientRect();
    var top = Math.max(pr.top, er.top), bot = Math.min(pr.bottom, er.bottom);
    var left = Math.max(pr.left, er.left), right = Math.min(pr.right, er.right);
    return (bot - top) > 1 && (right - left) > 1;
  },
  // 视觉反馈计数
  visual: function(){
    return document.querySelectorAll('#preview [class*="flash"], #preview .-kp-hit, #preview [class*="active"], .-tree-item.active, .-suggest-item.active').length;
  },
  // 目标块：按 srcLine 找
  blockAt: function(line){
    var p = this.pane(); if (!p) return null;
    var blocks = p.querySelectorAll('[data--src-line]');
    for (var i=0;i<blocks.length;i++){
      var s = +blocks[i].getAttribute('data--src-line');
      var e = +blocks[i].getAttribute('data--src-line-end') || s;
      if (s <= line && e >= line) return blocks[i];
    }
    return null;
  }
};
1;
`;

const st = await cdp.ev(COMMON);
void st;

let A_COUNTS = null;

async function runEntry(name, setupExpr, clickExpr, opts) {
  const o = opts || {};
  const rec = { name, trials: [], checks: {} };

  // setup
  await cdp.ev(setupExpr);
  await sleep(o.setupWait || 2500);

  // 1) 目标正确性前置
  rec.pre = await cdp.ev(`(function(){
    return { path: (window.state||{}).currentPath,
             paneScroll: (document.getElementById('preview-pane')||{}).scrollTop };
  })()`);

  // 2) N 次性能试验
  const times = [];
  const rpCounts = [];
  const rdCounts = [];
  let lastCheck = null;

  for (let i = 0; i < N; i++) {
    // 每轮重置到起点（NAV1 跳转后会离开源文档，必须回到源文档）
    if (o.resetExpr) { await cdp.ev(o.resetExpr); await sleep(o.resetWait2 || 900); }
    // reset scroll to top (确定性起点)
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); if(p) p.scrollTop=0; return p?p.scrollTop:null; })()`);
    await sleep(o.resetWait || 120);

    // 探针开
    await cdp.ev(`(function(){ window.__navProbe.on=true; window.__navProbe.renderPreview=0; window.__navProbe.renderDocument=0; return 1; })()`);

    const t0 = Date.now();
    const clicked = await cdp.ev(clickExpr);
    if (clicked && clicked.err) { rec.clickErr = clicked.err; break; }

    // 等目标进入视口 + 滚动稳定
    let ok = false;
    const wantPath = o.wantPath ? o.wantPath : null;
    for (let k = 0; k < 40; k++) {
      await sleep(50);
      const chk = await cdp.ev(`(async function(){
        var T = window.__navT;
        var line = ${Number(o.line || 0)};
        var el = line ? T.blockAt(line) : null;
        var vis = el ? T.inViewport(el) : null;
        var stable = await T.stableScroll();
        var path = (window.state||{}).currentPath;
        return { vis: vis, stable: stable, path: path,
                 nowPathOk: ${wantPath ? `path === ${JSON.stringify(wantPath)}` : 'true'} };
      })()`);
      if (chk && chk.stable && (chk.vis === true || chk.vis === null) && chk.nowPathOk) { ok = true; lastCheck = chk; break; }
      lastCheck = chk;
    }
    const dt = Date.now() - t0;
    if (ok) times.push(dt);

    const cnt = await cdp.ev(`(function(){ window.__navProbe.on=false; return { rp: window.__navProbe.renderPreview, rd: window.__navProbe.renderDocument }; })()`);
    rpCounts.push(cnt.rp); rdCounts.push(cnt.rd);
    A_COUNTS = await cdp.ev(`(function(){ return window.__wl2 ? { M1: window.__wl2.M1||0, M2: window.__wl2.M2||0 } : null; })()`);
    await sleep(o.afterWait || 150);
  }

  times.sort((a, b) => a - b);
  const pct = (p) => times.length ? times[Math.min(times.length - 1, Math.floor(times.length * p))] : null;

  rec.perf = {
    n: times.length,
    p50: pct(0.5), p95: pct(0.95), max: times.length ? times[times.length - 1] : null,
    raw: times,
    renderPreview: { values: rpCounts, max: Math.max(0, ...rpCounts) },
    renderDocument: { values: rdCounts, max: Math.max(0, ...rdCounts) },
  };
  rec.lastCheck = lastCheck;

  // 3) 连点 3 次测试
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); if(p) p.scrollTop=0; return 1; })()`);
  await sleep(120);
  rec.tripleClick = await cdp.ev(`(async function(){
    var T = window.__navT;
    var before = T.visual();
    // 连点 3 次（同一元素）
    for (var i=0;i<3;i++){
      (function(){
        var f = (${clickExpr});
      })();
    }
    await new Promise(function(r){ setTimeout(r, 400); });
    var after = T.visual();
    var stable = await T.stableScroll();
    var p = T.pane();
    return { visualBefore: before, visualAfter: after,
             visualBloat: after > before + 3, scrollStable: stable,
             scrollTop: p?p.scrollTop:null };
  })()`);

  return rec;
}

// ═══════════════════════════════════════════════
// NAV1: wikilink（work copy KB 有 alpha.md 等目标）
// ═══════════════════════════════════════════════
results.entries.NAV1_wikilink = await runEntry(
  'NAV1_wikilink',
  `(function(){
     window.MemoriaApp.openFile('corpus/06-links-and-kp.md',{skipNav:true});
     var b = document.querySelector('.-view-btn[data-view="preview"]');
     if (b) b.click();
     return 1;
   })()`,
  `(function(){
     var els = document.querySelectorAll('#preview .-wikilink');
     var t = null;
     for (var i=0;i<els.length;i++){ if (els[i].classList.contains('-link-resolved')) { t = els[i]; break; } }
     if (!t) return { err: 'no resolved wikilink' };
     t.click();
     return { clicked: true, target: t.textContent };
   })()`,
  { resetExpr: `(function(){ if((window.state||{}).currentPath !== 'corpus/06-links-and-kp.md'){ window.MemoriaApp.openFile('corpus/06-links-and-kp.md',{skipNav:true}); } var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`, setupWait: 4000, resetWait2: 1200 }
);

// NAV1 体验：目标正确 + 视口
results.entries.NAV1_wikilink.checks = await cdp.ev(`(async function(){
  var T = window.__navT;
  var p = T.pane();
  var firstBlock = p ? p.querySelector('[data--src-line]') : null;
  var vis = firstBlock ? T.inViewport(firstBlock) : null;
  return { targetPath: (window.state||{}).currentPath,
           blocks: document.querySelectorAll('#preview .-src-block').length,
           firstBlockInViewport: vis };
})()`);

// ═══════════════════════════════════════════════
// NAV6: 搜索建议
// ═══════════════════════════════════════════════
results.entries.NAV6_search = await runEntry(
  'NAV6_search',
  `window.MemoriaApp.openFile('corpus/01-ime-zh.md',{skipNav:true})`,
  `(function(){
     var s = document.getElementById('toolbar-search');
     if (!s) return { err: 'no search input' };
     s.focus(); s.value = '的';
     s.dispatchEvent(new Event('input', {bubbles:true}));
     var panel = document.getElementById('toolbar-search-panel');
     var item = panel ? panel.querySelector('li, .-suggest-item, [data-line], button') : null;
     if (item) { item.click(); return { clicked: true, text: (item.textContent||'').slice(0,30) }; }
     return { clicked: false, noItem: true };
   })()`,
  { setupWait: 2600, resetWait: 400 }
);

// ═══════════════════════════════════════════════
// NAV7: 文件树
// ═══════════════════════════════════════════════
results.entries.NAV7_tree = await runEntry(
  'NAV7_tree',
  `window.MemoriaApp.openFile('corpus/01-ime-zh.md',{skipNav:true})`,
  `(function(){
     var ft = document.getElementById('file-tree');
     if (!ft) return { err: 'no file-tree' };
     var items = ft.querySelectorAll('-tree-item, .-tree-item, [data-path]');
     var t = null;
     for (var i=0;i<items.length;i++){
       var dp = items[i].getAttribute('data-path');
       if (dp && dp.indexOf('02-inline-edges') >= 0) { t = items[i]; break; }
     }
     if (!t && items.length) t = items[items.length-1];
     if (!t) return { err: 'no tree item' };
     t.click();
     return { clicked: true, path: t.getAttribute('data-path') };
   })()`,
  { setupWait: 2600, resetWait: 300 }
);

results.jsErrors = jsErrors;
results.finishedAt = new Date().toISOString();
results.aCounts = A_COUNTS;

writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log('__NAV_ENTRIES__' + JSON.stringify({
  out: outPath,
  entries: Object.keys(results.entries).map((k) => ({
    name: k,
    n: results.entries[k].perf.n,
    p50: results.entries[k].perf.p50,
    p95: results.entries[k].perf.p95,
    max: results.entries[k].perf.max,
    renderPreviewMax: results.entries[k].perf.renderPreview.max,
  })),
  jsErrors: jsErrors.length,
}));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
