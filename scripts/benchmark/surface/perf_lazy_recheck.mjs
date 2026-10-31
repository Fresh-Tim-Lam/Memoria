/**
 * task-63 惰性 ON 独立复核：复核 Lead 的四个数
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

function concurrency() { let mem=[],wv=0; try { const o=execFileSync('powershell',['-NoProfile','-Command',"Get-Process -Name Memoria -EA SilentlyContinue | ForEach-Object { \"$($_.Id)|$([Math]::Round($_.CPU,1))\" }; 'WV:' + @(Get-Process -Name msedgewebview2 -EA SilentlyContinue).Count"],{encoding:'utf8',timeout:15000}); for(const line of o.split(/\r?\n/)){ if(line.startsWith('WV:'))wv=Number(line.slice(3)); else if(line.includes('|')){const[p,c]=line.split('|');mem.push({pid:+p,cpuSec:+c});} } }catch(e){} return {memoriaExe:mem,webview2Count:wv,at:new Date().toISOString()}; }

let page=null;
for(let a=0;a<40;a++){ try{ const l=await httpJson(`http://127.0.0.1:${port}/json/list`); page=(l||[]).find(t=>t.type==='page'&&/^https?:/.test(t.url||'')&&t.webSocketDebuggerUrl); if(page)break; }catch(e){} await sleep(1000); }
if(!page){ console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
for(let i=0;i<300;i++){ if(await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ window.__MEMORIA_LAZY=true; try{localStorage.setItem("memoria.perf.lazy","1");}catch(e){} return 1; })()`);

await cdp.ev(`(function(){
  if(window.__m) return 1;
  var M={gaps:[],rafId:null,on:false,last:0}; window.__m=M;
  M.pane=function(){return document.getElementById('preview-pane');};
  M.firstLine=function(){ var p=this.pane(); if(!p)return null; var pr=p.getBoundingClientRect(); var els=p.querySelectorAll('[data--src-line]'); for(var i=0;i<els.length;i++){var r=els[i].getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) return +els[i].getAttribute('data--src-line');} return null; };
  M.frameStart=function(){M.gaps=[];M.last=performance.now();M.on=true; function tick(){if(!M.on)return;var n=performance.now();M.gaps.push(n-M.last);M.last=n;M.rafId=requestAnimationFrame(tick);} M.rafId=requestAnimationFrame(tick);};
  M.frameStop=function(){M.on=false;if(M.rafId)cancelAnimationFrame(M.rafId); var g=M.gaps.filter(function(x){return isFinite(x)&&x>0;}).sort(function(a,b){return a-b;}); var n=g.length; return {count:n,max:n?+g[n-1].toFixed(1):null,p95:n?+g[Math.floor(n*0.95)].toFixed(1):null};};
  M.waitReadable=function(timeoutMs){ var t0=performance.now(); var p=this.pane(); return new Promise(function(res){ function tick(){ if(!p){res({ms:performance.now()-t0,ok:false});return;} var pr=p.getBoundingClientRect(); var ph=0,untyped=0,mj=0; p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)ph++;}); p.querySelectorAll('span.-math:not(:has(mjx-container))').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)untyped++;}); p.querySelectorAll('mjx-container').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)mj++;}); if(ph===0&&untyped===0){res({ms:+(performance.now()-t0).toFixed(1),ok:true,mj:mj});return;} if(performance.now()-t0>timeoutMs){res({ms:+(performance.now()-t0).toFixed(1),ok:false,ph:ph,untyped:untyped,mj:mj});return;} requestAnimationFrame(tick);} tick();});};
  return 1;
})()`);

function stats(arr){ const a=arr.filter(x=>typeof x==='number'&&isFinite(x)).sort((x,y)=>x-y); const n=a.length; if(!n)return null; return {n,min:+a[0].toFixed(1),mean:+(a.reduce((s,x)=>s+x,0)/n).toFixed(1),p50:+a[Math.floor(n*0.5)].toFixed(1),p95:+a[Math.floor(n*0.95)].toFixed(1),max:+a[n-1].toFixed(1)}; }

const R = { head:'208fb979', doc:DOC, lazy:'ON', concurrencyBefore: concurrency() };

// ═ 1. 打开 08 首块可见 + 帧 ═
{
  const firstVisible=[], maxGaps=[];
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);
  await sleep(6000);
  for(let i=0;i<3;i++){
    await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true}); return 1; })()`);
    await sleep(2500);
    await cdp.ev(`window.__m.frameStart()`);
    const t0=Date.now();
    await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);
    let fb=null;
    for(let k=0;k<300;k++){ await sleep(100); const v=await cdp.ev(`(function(){var p=document.getElementById('preview-pane'),pv=document.getElementById('preview');if(!p||!pv)return null;var b=pv.querySelector('[data--src-line]');if(!b)return null;var pr=p.getBoundingClientRect(),br=b.getBoundingClientRect();return (Math.min(pr.bottom,br.bottom)-Math.max(pr.top,br.top)>2)?1:null;})()`); if(v===1){fb=Date.now()-t0;break;} }
    const fg=await cdp.ev('window.__m.frameStop()');
    firstVisible.push(fb); maxGaps.push(fg&&fg.max);
    console.log('[open08-lazy] 首块='+fb+'ms 最大帧='+(fg&&fg.max)+'ms');
    await sleep(500);
  }
  R.open08 = { firstVisible: stats(firstVisible), maxGap: stats(maxGaps) };
}

// ═ 2. 滚动 50%/80% 该屏可读 ═
{
  const s50=[], s80=[];
  // waitReadable 改为轮询式（页面内同步计算状态，Node 侧计时）
  const waitReadable = async () => {
    const t0 = Date.now();
    for (let k=0;k<50;k++){
      await sleep(40);
      const st = await cdp.ev(`(function(){
        var p=document.getElementById('preview-pane'); if(!p) return null;
        var pr=p.getBoundingClientRect(); var ph=0,untyped=0,mj=0;
        p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)ph++;});
        p.querySelectorAll('span.-math:not(:has(mjx-container))').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)untyped++;});
        p.querySelectorAll('mjx-container').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)mj++;});
        return { ph:ph, untyped:untyped, mj:mj, ok: ph===0 && untyped===0 };
      })()`);
      if (st && st.ok) return { ms: Date.now()-t0, mj: st.mj, ok: true };
      if (st && st.mj>0 && st.untyped===0 && st.ph>0) { /* 占位还没物化完成，继续等 */ }
    }
    return { ms: Date.now()-t0, ok: false };
  };
  for(let i=0;i<3;i++){
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
    await sleep(800);
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5; return 1; })()`);
    const r50 = await waitReadable();
    s50.push(r50.ms);
    await sleep(500);
    await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.8; return 1; })()`);
    const r80 = await waitReadable();
    s80.push(r80.ms);
    console.log('[scroll-lazy] 50%='+r50.ms+'ms(mj='+r50.mj+') 80%='+r80.ms+'ms(mj='+r80.mj+') ok='+r50.ok+'/'+r80.ok);
    await sleep(400);
  }
  R.scroll = { s50: stats(s50), s80: stats(s80) };
}

// ═ 3. 高度漂移 ═
{
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
  await sleep(1000);
  const sh = await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); return p.scrollHeight; })()`);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5; return 1; })()`);
  await sleep(1200);
  const A = await cdp.ev('window.__m.firstLine()');
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*1.0; return 1; })()`);
  await sleep(1200);
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.5; return 1; })()`);
  await sleep(1200);
  const B = await cdp.ev('window.__m.firstLine()');
  const drift = (A!=null && B!=null) ? Math.abs(A-B) : null;
  console.log('[drift-lazy] scrollHeight='+sh+' A(50%)='+A+' B(回50%)='+B+' drift='+drift);
  R.drift = { scrollHeight: sh, A, B, drift };
}

R.concurrencyAfter = concurrency();
writeFileSync(outPath, JSON.stringify(R, null, 2), 'utf8');
console.log('__RECHECK__'+JSON.stringify({open08:R.open08, scroll:R.scroll, drift:R.drift}));
cdp.close();
setTimeout(()=>process.exit(0),300).unref();
