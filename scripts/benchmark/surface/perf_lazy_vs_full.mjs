/**
 * 验证：惰性物化期间的门禁计数失真是否为"口径问题"而非"渲染错误"
 * 手法：同一实例内，同一文档，分别在 __MEMORIA_LAZY=false（全量）与 true（惰性）下采集签名，对比。
 * 若全量路径 == v3 基线，则确认是口径问题。
 */
import { writeFileSync } from 'node:fs';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('timeout')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 90000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) { const r = await this.send('Runtime.evaluate', { expression: `(function(){ try { var __v = (${expr}); if (__v && typeof __v.then === 'function') return JSON.stringify({_p:true}); return JSON.stringify(__v===undefined?null:__v); } catch(e){ return JSON.stringify({err:String(e&&e.message)});} })()`, returnByValue: true, userGesture: true }); if (r && r.exceptionDetails) return { _exc: String(r.exceptionDetails.text) }; try { return JSON.parse(r.result.value); } catch(e){ return { _parseErr:true }; } }
  close() { try { this.ws.close(); } catch {} }
}
const port = Number(process.argv[2]);
const outPath = process.argv[3];
const DOCS = (process.argv[4] || 'scale/scale-1k.md,corpus/07-extremes.md,docs/ref/ppt/ocr.md').split(',');

let page=null;
for(let a=0;a<40;a++){ try{const l=await httpJson(`http://127.0.0.1:${port}/json/list`); page=(l||[]).find(t=>t.type==='page'&&/^https?:/.test(t.url||'')&&t.webSocketDebuggerUrl); if(page)break;}catch(e){} await sleep(1000); }
if(!page){console.error('no page');process.exit(2);}
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
for(let i=0;i<300;i++){ if(await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);

// 采集当前 DOM 的关键计数（对应 fidelity 的字段口径）
const COLLECT = `(function(){
  var pv = document.getElementById('preview');
  if (!pv) return null;
  return {
    blocks: pv.querySelectorAll('.-src-block').length,
    placeholders: pv.querySelectorAll('.-pv-placeholder').length,
    mjx: pv.querySelectorAll('mjx-container').length,
    spanMath: pv.querySelectorAll('span.-math').length,
    mathBlock: pv.querySelectorAll('.-math-block').length,
    mermaid: pv.querySelectorAll('.-mermaid-container').length,
    img: pv.querySelectorAll('img').length,
    table: pv.querySelectorAll('table').length,
    pre: pv.querySelectorAll('pre').length,
    a: pv.querySelectorAll('a').length,
  };
})()`;

async function openAndWait(doc, lazyMode) {
  // 设定模式
  await cdp.ev(`(function(){ window.__MEMORIA_LAZY = ${lazyMode === 'full' ? 'false' : 'true'}; return 1; })()`);
  // 先切走，确保重渲染
  await cdp.ev(`(function(){ window.MemoriaApp.openFile('homework/README.md',{skipNav:true}); return 1; })()`);
  await sleep(1500);
  await cdp.ev(`(function(){ window.__MEMORIA_LAZY = ${lazyMode === 'full' ? 'false' : 'true'}; return 1; })()`);
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(doc)},{skipNav:true}); return 1; })()`);
  // 等稳定：块数 > 0 且连续 3 次不变
  let last = -1, stable = 0;
  for (let k = 0; k < 300; k++) {
    await sleep(100);
    const c = await cdp.ev(`(function(){ var pv=document.getElementById('preview'); return pv ? pv.querySelectorAll('.-src-block').length : 0; })()`);
    if (c > 0 && c === last) stable++; else stable = 0;
    last = c;
    if (stable >= 5) break;
  }
  await sleep(1500);
  return await cdp.ev(COLLECT);
}

const results = { head: '215d9e88', docs: {} };
for (const doc of DOCS) {
  const full = await openAndWait(doc, 'full');
  const lazy = await openAndWait(doc, 'lazy');
  results.docs[doc] = { full, lazy };
  console.log('=== ' + doc + ' ===');
  console.log('  全量: ' + JSON.stringify(full));
  console.log('  惰性: ' + JSON.stringify(lazy));
  if (full && lazy) {
    const diff = {};
    for (const k of Object.keys(full)) { if (full[k] !== lazy[k]) diff[k] = { full: full[k], lazy: lazy[k] }; }
    console.log('  差异字段: ' + (Object.keys(diff).length ? JSON.stringify(diff) : '（无）'));
  }
  console.log('');
}
writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log('__CMP__' + JSON.stringify(results));
cdp.close();
setTimeout(()=>process.exit(0),300).unref();
