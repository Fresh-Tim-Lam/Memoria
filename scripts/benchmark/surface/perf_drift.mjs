/**
 * 高度账本漂移：极简直接测法（独立脚本，聚焦 drift 一项）
 */
import { writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
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

// 打开并等全量
await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);
for (let k=0;k<400;k++){ await sleep(100); const st = await cdp.ev(`(function(){ var pv=document.getElementById('preview'); if(!pv) return null; var sup=pv.querySelectorAll('span.-math:not(:has(mjx-container))').length; var blk=pv.querySelectorAll('.-math-block:not(:has(mjx-container))').length; var sl=pv.querySelectorAll('[data--src-line]').length; return sl>3000 && sup+blk===0 ? 1 : {sl:sl,res:sup+blk}; })()`); if (st===1) break; }
await sleep(800);

// 精确测：滚动到 50%，读第一个可见块的 src-line
console.log('=== 滚动前 ===');
console.log(JSON.stringify(await cdp.ev(`(function(){
  var p=document.getElementById('preview-pane');
  var pv=document.getElementById('preview');
  return { sh:p.scrollHeight, ch:p.clientHeight, st:p.scrollTop,
           sl: pv.querySelectorAll('[data--src-line]').length,
           paneSl: p.querySelectorAll('[data--src-line]').length };
})()`)));

// 滚动到 50%
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5; return 1; })()`);
await sleep(1500);

console.log('=== 滚动到 50% 后 ===');
const a50 = await cdp.ev(`(function(){
  var p=document.getElementById('preview-pane');
  var pr=p.getBoundingClientRect();
  var pv=document.getElementById('preview');
  var els=pv.querySelectorAll('[data--src-line]');
  var out={ st:p.scrollTop, sh:p.scrollHeight, ch:p.clientHeight, paneTop:pr.top, paneBottom:pr.bottom };
  var found=null;
  for(var i=0;i<els.length;i++){
    var r=els[i].getBoundingClientRect();
    var overlap=Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top);
    if(overlap>2){ found={ idx:i, line:els[i].getAttribute('data--src-line'), top:+r.top.toFixed(1), bottom:+r.bottom.toFixed(1), overlap:+overlap.toFixed(1) }; break; }
  }
  out.firstVisible=found;
  // 也打印前几个元素的 raw rect
  out.sample=[];
  for(var j=0;j<5;j++){ var rr=els[j].getBoundingClientRect(); out.sample.push({line:els[j].getAttribute('data--src-line'), top:+rr.top.toFixed(1)}); }
  return out;
})()`);
console.log(JSON.stringify(a50, null, 2));

// 滚到底再回 50%
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*1.0; return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5; return 1; })()`);
await sleep(1500);
const b50 = await cdp.ev(`(function(){
  var p=document.getElementById('preview-pane');
  var pr=p.getBoundingClientRect();
  var els=document.getElementById('preview').querySelectorAll('[data--src-line]');
  for(var i=0;i<els.length;i++){
    var r=els[i].getBoundingClientRect();
    if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) return { line: els[i].getAttribute('data--src-line') };
  }
  return null;
})()`);
console.log('回 50% 第一可见块 line =', JSON.stringify(b50));

const A = a50 && a50.firstVisible ? +a50.firstVisible.line : null;
const B = (b50 && (typeof b50 === 'object') && b50.line != null) ? +b50.line : (b50 ? +b50 : null);
const result = { A, B, drift: (A!=null && B!=null) ? Math.abs(A-B) : null,
  scrollHeight: a50 && a50.sh, clientHeight: a50 && a50.ch };
writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
console.log('');
console.log('__DRIFT__' + JSON.stringify(result));
cdp.close();
setTimeout(()=>process.exit(0),300).unref();
