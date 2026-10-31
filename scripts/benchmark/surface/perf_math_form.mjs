/**
 * 验证：-image-block 块里的 $A$ 在 DOM 是什么形态？
 *   - 若是 span.-math ⇒ withMath 能检测到，问题在别处
 *   - 若是裸文本 $A$ ⇒ withMath 检测不到，根因确认
 */
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
const DOC = process.argv[3] || '教材/03_第3章_模拟信号的数字编码.md';

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }
await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
await sleep(1500);
await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);

await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(DOC)}, { skipNav: true })`);
for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
await sleep(4000);

// 跳转到目标（复现 R1 跳转场景）
await cdp.ev(`(function(){ try { window.MemoriaApp.scrollToSrcLine("preview", 1174); } catch(e){} return 1; })()`);
await sleep(2500);
await sleep(2000);

const r = await cdp.ev(`(function(){
  var pv = document.getElementById('preview');
  var cc = pv ? (pv.querySelector('.-preview-content') || pv) : null;
  if (!cc) return { err: 'no content' };
  function inspect(idx){
    var el = cc.querySelector('[data--block-index="'+idx+'"]');
    if (!el) return { err: 'not found', idx: idx };
    var o = {
      idx: idx,
      className: el.className,
      // ★ 关键：withMath 检测用的选择器
      hasMathClass: !!el.querySelector('.-math, .-math-block'),
      hasMathClassSelf: el.classList.contains('-math-block'),
      mathEls: el.querySelectorAll('span.-math').length,
      mathBlockEls: el.querySelectorAll('.-math-block').length,
      mjx: el.querySelectorAll('mjx-container').length,
      textContent: (el.textContent || '').slice(0, 90),
      htmlSnippet: el.innerHTML.slice(0, 400)
    };
    // 找所有含 $ 的文本节点及其父元素
    var dollars = [];
    (function walk(n){
      for (var c = n.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) {
          var t = (c.nodeValue || '');
          if (t.indexOf('$') >= 0) {
            dollars.push({
              text: t.trim().slice(0, 60),
              parentTag: n.tagName ? n.tagName.toLowerCase() : '?',
              parentClass: n.className || ''
            });
          }
        } else if (c.nodeType === 1) {
          var tag = c.tagName.toLowerCase();
          if (tag === 'mjx-container') continue;
          walk(c);
        }
      }
    })(el);
    o.dollarTextNodes = dollars;
    return o;
  }
  return { b862: inspect(862), b870: inspect(870), b872: inspect(872) };
})()`);
console.log('=== -image-block 里 $A$ 的 DOM 形态 ===');
console.log(JSON.stringify(r, null, 2));
console.log('');
for (const k of ['b862', 'b870', 'b872']) {
  const x = r && r[k];
  if (!x || x.err) { console.log(k + ': ' + JSON.stringify(x)); continue; }
  console.log('[' + k + '] className=' + x.className);
  console.log('  ★ withMath 检测: hasMathClass=' + x.hasMathClass + ' hasMathClassSelf=' + x.hasMathClassSelf);
  console.log('     span.-math=' + x.mathEls + ' .-math-block=' + x.mathBlockEls + ' mjx=' + x.mjx);
  console.log('     含$文本节点: ' + JSON.stringify(x.dollarTextNodes));
  console.log('');
}
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
