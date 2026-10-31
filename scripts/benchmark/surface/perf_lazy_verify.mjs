/**
 * task-63 上跳修复(99b2ba23)复测：4 项
 *  1. 视口内 maxShrink === 0
 *  2. 高度漂移 ≤5 行
 *  3. 冷启动 ≤500ms
 *  4. unlock minHeight 日志 / data--pv-locked 块离开视口后解锁
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
const ALT = process.argv[5] || 'homework/README.md';

function concurrency(){ let mem=[],wv=0; try{const o=execFileSync('powershell',['-NoProfile','-Command',"Get-Process -Name Memoria -EA SilentlyContinue | ForEach-Object { \"$($_.Id)|$([Math]::Round($_.CPU,1))\" }; 'WV:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count"],{encoding:'utf8',timeout:15000}); for(const line of o.split(/\r?\n/)){ if(line.startsWith('WV:'))wv=Number(line.slice(3)); else if(line.includes('|')){const[p,c]=line.split('|');mem.push({pid:+p,cpuSec:+c});} } }catch(e){} return {memoriaExe:mem,webview2Count:wv,at:new Date().toISOString()}; }

let page=null;
for(let a=0;a<40;a++){ try{const l=await httpJson(`http://127.0.0.1:${port}/json/list`); page=(l||[]).find(t=>t.type==='page'&&/^https?:/.test(t.url||'')&&t.webSocketDebuggerUrl); if(page)break;}catch(e){} await sleep(1000); }
if(!page){console.error('no page');process.exit(2);}
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Log.enable').catch(()=>{});
const unlockLogs = [];
cdp.ws.addEventListener('message', (e) => { let m; try{ m=JSON.parse(typeof e.data==='string'?e.data:String(e.data)); }catch{return;} if(m.method==='Runtime.consoleAPICalled'){ const t=(m.params&&m.params.type)||''; const args=(m.params&&m.params.args)||[]; const txt=args.map(a=>a.value===undefined?(a.description||''):String(a.value)).join(' '); if(/unlock minHeight|lazy/i.test(txt)) unlockLogs.push(txt); } });
for(let i=0;i<300;i++){ if(await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ window.__MEMORIA_LAZY=true; try{localStorage.setItem("memoria.perf.lazy","1");}catch(e){} return 1; })()`);

// 安装工具
await cdp.ev(`(function(){
  if(window.__j) return 1;
  var J={prev:{},maxShrinkInView:0}; window.__j=J;
  J.pane=function(){return document.getElementById('preview-pane');};
  J.firstLine=function(){var p=this.pane();if(!p)return null;var pr=p.getBoundingClientRect();var els=p.querySelectorAll('[data--src-line]');for(var i=0;i<els.length;i++){var r=els[i].getBoundingClientRect();if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)return +els[i].getAttribute('data--src-line');}return null;};
  // 采样视口内块 top，检测上跳（只算视口内块）
  J.sampleViewport=function(){
    var p=this.pane(); if(!p) return;
    var pr=p.getBoundingClientRect();
    var els=p.querySelectorAll('[data--src-line]');
    for(var i=0;i<els.length;i++){
      var el=els[i]; var top=el.getBoundingClientRect().top;
      if(top < pr.top-5 || top > pr.bottom+5) continue; // 只视口内
      var line=el.getAttribute('data--src-line');
      if(line in this.prev){ var shrink=this.prev[line]-top; if(shrink>this.maxShrinkInView) this.maxShrinkInView=shrink; }
      this.prev[line]=top;
    }
  };
  J.reset=function(){this.prev={};this.maxShrinkInView=0;};
  // 锁高块统计
  J.lockedCount=function(){return document.querySelectorAll('[data--pv-locked]').length;};
  J.frameStart=function(){J._g=[];J._last=performance.now();J._on=true;function t(){if(!J._on)return;var n=performance.now();J._g.push(n-J._last);J._last=n;requestAnimationFrame(t);}requestAnimationFrame(t);};
  J.frameStop=function(){J._on=false;var g=J._g.filter(function(x){return isFinite(x)&&x>0;}).sort(function(a,b){return a-b;});return {max:g.length?+g[g.length-1].toFixed(1):null};};
  return 1;
})()`);

// ═ 1. 冷启动首块可见 + 帧 ═
await cdp.ev(`window.__j.frameStart()`);
const coldT0 = Date.now();
await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);
let coldFb=null;
for(let k=0;k<400;k++){ await sleep(50); const v=await cdp.ev(`(function(){var p=document.getElementById('preview-pane'),pv=document.getElementById('preview');if(!p||!pv)return null;var b=pv.querySelector('[data--src-line]');if(!b)return null;var pr=p.getBoundingClientRect(),br=b.getBoundingClientRect();return (Math.min(pr.bottom,br.bottom)-Math.max(pr.top,br.top)>2)?1:null;})()`); if(v===1){coldFb=Date.now()-coldT0;break;} }
const coldFg = await cdp.ev('window.__j.frameStop()');
console.log('[cold] 首块='+coldFb+'ms 最大帧='+(coldFg&&coldFg.max)+'ms');

// 等全量完成（占位清零）
for(let k=0;k<400;k++){ await sleep(100); const st=await cdp.ev(`(function(){var pv=document.getElementById('preview');if(!pv)return null;var ph=pv.querySelectorAll('.-pv-placeholder').length;var sl=pv.querySelectorAll('[data--src-line]').length;return {ph:ph,sl:sl};})()`); if(st && st.ph===0 && st.sl>3000) break; }
await sleep(800);

// ═ 2. 上跳检测：滚到底再回，采样视口内 shrink ═
await cdp.ev('window.__j.reset()');
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
await sleep(1000);
await cdp.ev('window.__j.sampleViewport()');
// 逐段滚动（模拟真实拖动，分多步）
for(let s=0;s<10;s++){
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*((s+1)/10); return 1; })()`.replace('(s+1)/10', String((s+1)/10)));
  await sleep(300);
  await cdp.ev('window.__j.sampleViewport()');
}
const maxShrinkInView = await cdp.ev('window.__j.maxShrinkInView');
console.log('[jump] 视口内 maxShrink='+maxShrinkInView+'px');

// ═ 3. 高度漂移 ═
const sh = await cdp.ev(`(function(){var p=document.getElementById('preview-pane');return p.scrollHeight;})()`);
await cdp.ev(`(function(){var p=document.getElementById('preview-pane');p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5;return 1;})()`);
await sleep(1200);
const A = await cdp.ev('window.__j.firstLine()');
// 滚到底再回 50%
await cdp.ev(`(function(){var p=document.getElementById('preview-pane');p.scrollTop=(p.scrollHeight-p.clientHeight)*1.0;return 1;})()`);
await sleep(1500);
await cdp.ev(`(function(){var p=document.getElementById('preview-pane');p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5;return 1;})()`);
await sleep(1500);
const B = await cdp.ev('window.__j.firstLine()');
const drift = (A!=null&&B!=null)?Math.abs(A-B):null;
console.log('[drift] A='+A+' B='+B+' drift='+drift+' sh='+sh);

// ═ 4. unlock 日志 + locked 块解锁 ═
const lockedBefore = await cdp.ev('window.__j.lockedCount()');
// 滚到顶部（让之前物化的锁高块离开视口，触发解锁）
await cdp.ev(`(function(){var p=document.getElementById('preview-pane');p.scrollTop=0;return 1;})()`);
await sleep(3000);
const lockedAfter = await cdp.ev('window.__j.lockedCount()');
console.log('[unlock] locked块 before='+lockedBefore+' after='+lockedAfter+' unlockLogs='+unlockLogs.length);

const out = {
  head:'99b2ba23', lazy:'ON', doc:DOC,
  cold: { firstVisible: coldFb, maxGap: coldFg&&coldFg.max },
  maxShrinkInView: maxShrinkInView,
  drift: { A, B, drift, scrollHeight: sh },
  unlock: { lockedBefore, lockedAfter, logCount: unlockLogs.length, sample: unlockLogs.slice(0,5) },
  concurrency: concurrency(),
};
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('__VERIFY__'+JSON.stringify(out));
cdp.close();
setTimeout(()=>process.exit(0),300).unref();
