/**
 * 上跳检测：滚动到底再回 50% 过程中，监测块 top 是否突然变小（内容上跳）
 * 独立脚本，聚焦单一项。
 */
import { writeFileSync } from 'node:fs';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('timeout')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 60000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) { const r = await this.send('Runtime.evaluate', { expression: `(function(){ try { var __v = (${expr}); if (__v && typeof __v.then === 'function') return JSON.stringify({_p:true}); return JSON.stringify(__v===undefined?null:__v); } catch(e){ return JSON.stringify({err:String(e&&e.message)});} })()`, returnByValue: true, userGesture: true }); if (r && r.exceptionDetails) return { _exc: String(r.exceptionDetails.text) }; try { return JSON.parse(r.result.value); } catch(e){ return { _parseErr:true }; } }
  close() { try { this.ws.close(); } catch {} }
}
const port = Number(process.argv[2]);
const outPath = process.argv[3];
const DOC = process.argv[4] || '教材/08_第8章_差错控制编码.md';

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l||[]).find(t => t.type==='page' && /^https?:/.test(t.url||'') && t.webSocketDebuggerUrl); if (page) break; } catch(e) {}
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
for (let i=0;i<300;i++){ if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
// 惰性开关：必须在 openFile 前注入
await cdp.ev(`(function(){ window.__MEMORIA_LAZY = true; try { localStorage.setItem("memoria.perf.lazy","1"); } catch(e){} return 1; })()`);
await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);
for (let k=0;k<400;k++){ await sleep(100); const st = await cdp.ev(`(function(){ var pv=document.getElementById('preview'); if(!pv) return null; var sup=pv.querySelectorAll('span.-math:not(:has(mjx-container))').length; var blk=pv.querySelectorAll('.-math-block:not(:has(mjx-container))').length; var sl=pv.querySelectorAll('[data--src-line]').length; return sl>3000 && sup+blk===0 ? 1 : null; })()`); if (st===1) break; }
await sleep(800);

// 安装上跳监测器（用 setInterval 轮询，记录每块 top 相对上次的减小量）
await cdp.ev(`(function(){
  window.__jump = { samples: [], maxShrink: 0 };
  var prev = {}; // line -> top
  function sample(){
    var pv = document.getElementById('preview');
    if (!pv) return;
    // 只采样视口附近的块（提高灵敏度，避免扫描全部 4001 块）
    var pane = document.getElementById('preview-pane');
    var pr = pane.getBoundingClientRect();
    var els = pv.querySelectorAll('[data--src-line]');
    var maxShrink = 0;
    for (var i=0;i<els.length;i++){
      var el = els[i];
      var top = el.getBoundingClientRect().top;
      // 只看视口上下 2000px 范围内的块
      if (top < pr.top - 2000 || top > pr.bottom + 2000) continue;
      var line = el.getAttribute('data--src-line');
      if (line in prev) {
        var shrink = prev[line] - top; // 正 = 该块上移了（内容上跳）
        if (shrink > maxShrink) maxShrink = shrink;
      }
      prev[line] = top;
    }
    if (maxShrink > window.__jump.maxShrink) window.__jump.maxShrink = maxShrink;
    window.__jump.samples.push(+(Date.now()).toString());
  }
  window.__jump.timer = setInterval(sample, 50);
  sample();
  return 1;
})()`);

// 先滚回顶部
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
await sleep(1200);

// 快速连续滚动：0 → 底 → 50%（触发最大 reflow）
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*1.0; return 1; })()`);
await sleep(600);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5; return 1; })()`);
await sleep(1200);

// 停止并取结果
const result = await cdp.ev(`(function(){
  clearInterval(window.__jump.timer);
  var maxShrink = window.__jump.maxShrink;
  return { maxShrink: +maxShrink.toFixed(1), sampleCount: window.__jump.samples.length };
})()`);
console.log('上跳检测结果:', JSON.stringify(result));
result.doc = DOC;
writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
console.log('__JUMP__' + JSON.stringify(result));
cdp.close();
setTimeout(()=>process.exit(0),300).unref();
