/**
 * 骨架视觉亮度分析 v2（修正采样基准）
 *
 * v1 的两个 bug：
 *   ① 背景基准取左栏（亮度 37.1），但 preview 背景是 rgb(30,30,30)≈30 ⇒ 基准错
 *   ② 采样区域 w*0.30~0.65 与 paneRect(x=280,w=632 ⇒ 22%–72%) 不匹配，混入左右面板
 *
 * v2 做法：
 *   1. 先从页面读 paneRect（CSS 像素）
 *   2. 截图尺寸 1264×821 vs CSS 视口 —— 需按 DPR 换算
 *   3. 在 paneRect 内取"纯骨架区域"和"纯背景区域"分别算亮度
 *
 * 用法: node perf_visual_lum.mjs <port> <outdir> <label>
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); this.frames = []; ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; }
    if (m.method === 'Page.screencastFrame') { this.frames.push(m.params.data); this.send('Page.screencastFrameAck', { sessionId: m.params.sessionId }).catch(() => {}); return; }
    if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 120000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr) { const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, userGesture: true }); if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || '')); return r.result ? r.result.value : undefined; }
  async waitFor(expr, timeoutMs = 60000) { const t0 = Date.now(); while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`)) return true; } catch (e) { /* */ } await sleep(150); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}
const port = Number(process.argv[2]);
const outdir = process.argv[3] || 'artifacts/agent/verify/visual-lum';
const LABEL = process.argv[4] || 'b5044bdb';
const DOC = process.argv[5] || '教材/08_第8章_差错控制编码.md';
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
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} try{ window.__MEMORIA_DEFER=false; }catch(e){} return 1; })()`);

// 打开 + 预热
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(300); }
for (let k = 0; k < 150; k++) { await sleep(150); const ph = await cdp.ev(`(function(){var p=document.getElementById('preview-pane');if(!p)return -1;var pr=p.getBoundingClientRect();var n=0;p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect();if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)n++;});return n;})()`); if (ph === 0) break; }
await sleep(1200);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*0.4; return 1; })()`);
await sleep(3000);
await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=0; return 1; })()`);
await sleep(2500);

// 读几何：paneRect(CSS px) + 截图尺寸 + DPR
const geom = await cdp.ev(`(function(){
  var p = document.getElementById('preview-pane');
  var pr = p.getBoundingClientRect();
  return { pane: { x: pr.left, y: pr.top, w: pr.width, h: pr.height },
           innerW: window.innerWidth, innerH: window.innerHeight,
           dpr: window.devicePixelRatio,
           bgComputed: getComputedStyle(p).backgroundColor };
})()`);
console.log('=== 几何 ===');
console.log('  paneRect(CSS): x=' + geom.pane.x.toFixed(0) + ' y=' + geom.pane.y.toFixed(0) +
  ' w=' + geom.pane.w.toFixed(0) + ' h=' + geom.pane.h.toFixed(0));
console.log('  inner=' + geom.innerW + 'x' + geom.innerH + '  dpr=' + geom.dpr);

// 先抓一张"加载完成"帧作对照
const shotDone = await cdp.send('Page.captureScreenshot', { format: 'png' });
const donePath = outdir + '/' + LABEL + '-loaded.png';
writeFileSync(donePath, Buffer.from(shotDone.data, 'base64'));

// 开 screencast 抓骨架帧
cdp.frames.length = 0;
await cdp.send('Page.startScreencast', { format: 'png', quality: 100, maxWidth: 1264, maxHeight: 821, everyNthFrame: 1 }).catch(() => {});
await sleep(150);
for (let s = 1; s <= 10; s++) {
  await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.8 * s / 10).toFixed(3)}; return 1; })()`);
  await sleep(16);
}
await sleep(1500);
await cdp.send('Page.stopScreencast').catch(() => {});

console.log('');
console.log('=== screencast 帧数: ' + cdp.frames.length + ' ===');
// 保存所有帧
const framePaths = [];
cdp.frames.forEach((d, i) => {
  const p = outdir + '/' + LABEL + '-f' + String(i).padStart(2, '0') + '.png';
  writeFileSync(p, Buffer.from(d, 'base64'));
  framePaths.push(p);
});

writeFileSync(outdir + '/geom-' + LABEL + '.json', JSON.stringify({ geom, frameCount: cdp.frames.length, framePaths, donePath }, null, 2), 'utf8');
console.log('  已保存 ' + framePaths.length + ' 帧 + 1 张 loaded 对照');
console.log('');
console.log('__GEOM__' + JSON.stringify(geom));
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
