/**
 * 骨架色可行性实验（不改代码，仅运行时注入 CSS 变量）
 *   对比 4 档透明度在深色主题下的可见性，各抓一张截图
 *
 * 用法: node perf_skeleton_color.mjs <port> <outdir>
 */
import { writeFileSync, mkdirSync } from 'node:fs';
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
const outdir = process.argv[3] || 'artifacts/agent/verify/skeleton-color';
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';
mkdirSync(outdir, { recursive: true });

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Page.enable').catch(() => {});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

// 探针
await cdp.ev(`(function(){
  if (window.__sk) return 1;
  var S = {}; window.__sk = S;
  S.pane = function(){ return document.getElementById('preview-pane'); };
  S.cc = function(){ return document.querySelector('#preview .-preview-content') || document.getElementById('preview'); };
  S.vph = function(){
    var p = S.pane(), cc = S.cc(); if (!p || !cc) return -1;
    var pr = p.getBoundingClientRect(); var n = 0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      if (Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 2) n++;
    });
    return n;
  };
  S.cov = function(){
    var p = S.pane(), cc = S.cc(); if (!p || !cc) return -1;
    var pr = p.getBoundingClientRect(); var h = 0;
    cc.querySelectorAll('.-pv-placeholder').forEach(function(e){
      var r = e.getBoundingClientRect();
      var vis = Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top);
      if (vis > 2) h += vis;
    });
    return p.clientHeight > 0 ? Math.min(1, h / p.clientHeight) : -1;
  };
  // 读主题与当前骨架色
  S.info = function(){
    var cc = S.cc(); var ph = cc ? cc.querySelector('.-pv-placeholder') : null;
    var cs = ph ? getComputedStyle(ph) : null;
    var root = getComputedStyle(document.documentElement);
    var bodyBg = getComputedStyle(document.body).backgroundColor;
    return { placeholderBg: cs ? cs.backgroundColor : null,
             bodyBg: bodyBg,
             themeAttr: document.documentElement.getAttribute('data-theme') || (document.body && document.body.getAttribute('data-theme')) || '(none)',
             pvPlaceholderVar: root.getPropertyValue('--pv-placeholder-bg').trim() || '(unset)' };
  };
  return 1;
})()`);

const info0 = await cdp.ev('window.__sk.info()');
console.log('=== 当前骨架色 ===');
console.log('  ' + JSON.stringify(info0));

// 4 档对比
const VARIANTS = [
  { name: 'v10-original', css: 'rgba(127,127,127,0.10)' },
  { name: 'v18', css: 'rgba(127,127,127,0.18)' },
  { name: 'v26', css: 'rgba(127,127,127,0.26)' },
  { name: 'v36', css: 'rgba(127,127,127,0.36)' },
];

const results = [];
for (const v of VARIANTS) {
  // 注入变量
  await cdp.ev(`(function(){ document.documentElement.style.setProperty('--pv-placeholder-bg', ${JSON.stringify(v.css)}); return 1; })()`);
  // 重开文档
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
  for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
  for (let k = 0; k < 150; k++) { await sleep(150); if (await cdp.ev('window.__sk.vph()') === 0) break; }
  await sleep(1000);
  // 预热
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
  for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sk.vph()') === 0) break; }
  await sleep(600);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
  for (let k = 0; k < 60; k++) { await sleep(100); if (await cdp.ev('window.__sk.vph()') === 0) break; }
  await sleep(800);
  // 拖到 80%，在"骨架覆盖高"的时刻抓图
  for (let s = 1; s <= 10; s++) {
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
    await sleep(16);
  }
  // 等骨架覆盖率高时抓图（最多等 400ms，取覆盖率最高的时刻）
  let best = { cov: -1, shot: null };
  for (let t = 0; t < 8; t++) {
    await sleep(50);
    const cov = await cdp.ev('window.__sk.cov()');
    if (cov > best.cov) {
      try {
        const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
        if (shot && shot.data) best = { cov, shot: Buffer.from(shot.data, 'base64') };
      } catch (e) { /* */ }
    }
    if (cov < 0.1 && t > 3) break;
  }
  const path = outdir + '/' + v.name + '.png';
  if (best.shot) writeFileSync(path, best.shot);
  const actualBg = await cdp.ev(`(function(){ var cc=document.querySelector('#preview .-preview-content'); var ph=cc?cc.querySelector('.-pv-placeholder'):null; return ph?getComputedStyle(ph).backgroundColor:null; })()`);
  results.push({ variant: v.name, css: v.css, actualBg, covAtShot: +best.cov.toFixed(3), screenshot: best.shot ? path : null });
  console.log('  ' + v.name.padEnd(14) + ' css=' + v.css.padEnd(24) + ' 实测bg=' + actualBg + ' 抓图时cov=' + (best.cov * 100).toFixed(0) + '%  ' + (best.shot ? '✓' : '✗'));
  // 等物化完
  for (let k = 0; k < 80; k++) { await sleep(100); if (await cdp.ev('window.__sk.vph()') === 0) break; }
  await sleep(500);
}

// 清理注入
await cdp.ev(`(function(){ document.documentElement.style.removeProperty('--pv-placeholder-bg'); return 1; })()`);

writeFileSync(outdir + '/result.json', JSON.stringify({ head: '0b0d9bf0', info0, results }, null, 2), 'utf8');
console.log('');
console.log('__SKEL__' + JSON.stringify({ theme: info0.themeAttr, bodyBg: info0.bodyBg,
  variants: results.map(r => ({ name: r.variant, cov: r.covAtShot, shot: !!r.screenshot })) }));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
