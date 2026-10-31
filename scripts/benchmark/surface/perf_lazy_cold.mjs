/**
 * task-63 惰性 ON：冷启动首开 vs 热轮（分开测）
 * 冷启动：实例起来后，第一次 openFile（含 MathJax startup 尚未完成）
 * 热轮：同一实例内，切走过再回来第二次+ openFile
 *
 * 每个实例只产出 1 个冷启动 + 2 个热轮。
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
for(let i=0;i<300;i++){ if(await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break; await sleep(200); }
// 先切 preview（不 openFile），然后注入惰性开关
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ window.__MEMORIA_LAZY=true; try{localStorage.setItem("memoria.perf.lazy","1");}catch(e){} return 1; })()`);

// 安装帧采样器
await cdp.ev(`(function(){ if(window.__fr)return 1; var F={gaps:[],on:false,last:0,rafId:null}; window.__fr=F; F.start=function(){F.gaps=[];F.last=performance.now();F.on=true;function t(){if(!F.on)return;var n=performance.now();F.gaps.push(n-F.last);F.last=n;F.rafId=requestAnimationFrame(t);}F.rafId=requestAnimationFrame(t);}; F.stop=function(){F.on=false;if(F.rafId)cancelAnimationFrame(F.rafId);var g=F.gaps.filter(function(x){return isFinite(x)&&x>0;}).sort(function(a,b){return a-b;});var n=g.length;return {max:n?+g[n-1].toFixed(1):null,p95:n?+g[Math.floor(n*0.95)].toFixed(1):null};}; return 1;})()`);

// 函数：测一次 openFile 首块可见 + 帧
async function measure(label){
  await cdp.ev(`window.__fr.start()`);
  const t0 = Date.now();
  await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(DOC)},{skipNav:true}); return 1; })()`);
  let fb = null;
  for(let k=0;k<400;k++){ await sleep(50); const v=await cdp.ev(`(function(){var p=document.getElementById('preview-pane'),pv=document.getElementById('preview');if(!p||!pv)return null;var b=pv.querySelector('[data--src-line]');if(!b)return null;var pr=p.getBoundingClientRect(),br=b.getBoundingClientRect();return (Math.min(pr.bottom,br.bottom)-Math.max(pr.top,br.top)>2)?1:null;})()`); if(v===1){fb=Date.now()-t0;break;} }
  const fg = await cdp.ev('window.__fr.stop()');
  console.log('['+label+'] 首块可见='+fb+'ms 最大帧='+(fg&&fg.max)+'ms p95='+(fg&&fg.p95)+'ms');
  return { firstVisible: fb, maxGap: fg&&fg.max, p95Gap: fg&&fg.p95 };
}

// 冷启动：第一次 openFile（此时 MathJax startup 可能未完成）
const cold = await measure('冷启动');
// 等全量排完
await sleep(6000);
// 切走
await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true}); return 1; })()`);
await sleep(2000);
// 热轮 1
const hot1 = await measure('热轮1');
await sleep(3000);
await cdp.ev(`(function(){ window.MemoriaApp.openFile(${JSON.stringify(ALT)},{skipNav:true}); return 1; })()`);
await sleep(2000);
const hot2 = await measure('热轮2');

const out = { head:'208fb979', lazy:'ON', cold, hot: [hot1, hot2], concurrency: concurrency() };
writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
console.log('__COLDOUT__'+JSON.stringify(out));
cdp.close();
setTimeout(()=>process.exit(0),300).unref();
