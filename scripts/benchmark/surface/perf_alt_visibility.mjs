/**
 * 判定 alt 文本中的 $A$ 是否可见（(a) 仅 img alt 属性 vs (b) 可见题注）
 *
 * 方法：打开 03 章 → 滚到 index=862/872 附近 → 检查该块的 DOM 结构：
 *   - 是否有 <img alt="...$A$...">
 *   - 是否有可见文本节点包含 $A$（非 alt 属性）
 *   - 计算 block.textContent（textContent 不含属性值 ⇒ 若 textContent 含 $A$ 即可见）
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

// 跳到目标行（源文 L1174 = 图3.3.15 题注）
await cdp.ev(`(function(){ try { window.MemoriaApp.scrollToSrcLine("preview", 1174); } catch(e){} return 1; })()`);
await sleep(3000);
// 再等一轮，确保排版完成
await sleep(2500);

const r = await cdp.ev(`(function(){
  var pv = document.getElementById('preview');
  var cc = pv ? (pv.querySelector('.-preview-content') || pv) : null;
  if (!cc) return { err: 'no content' };
  var out = { scanned: 0, matches: [] };
  var els = cc.querySelectorAll('.-src-block');
  for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var tc = el.textContent || '';
    // 找含 $ 的块
    if (tc.indexOf('$') < 0 && !el.querySelector('img[alt*="$"]')) continue;
    out.scanned++;
    if (out.matches.length >= 6) continue;
    var imgs = [];
    el.querySelectorAll('img').forEach(function(im){
      if ((im.alt||'').indexOf('$') >= 0) imgs.push({ alt: im.alt, src: (im.src||'').slice(-50), visible: !!(im.offsetWidth||im.offsetHeight||im.getClientRects().length) });
    });
    // 可见文本：遍历文本节点，排除 img
    var visibleTexts = [];
    (function walk(node){
      for (var c = node.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) {
          var t = (c.nodeValue || '').trim();
          if (t && t.indexOf('$') >= 0) visibleTexts.push(t.slice(0, 100));
        } else if (c.nodeType === 1) {
          var tag = c.tagName.toLowerCase();
          if (tag === 'mjx-container') continue;   // 已排版公式
          if (tag === 'img' || tag === 'svg') continue;
          walk(c);
        }
      }
    })(el);
    out.matches.push({
      blockIndex: el.getAttribute('data--block-index'),
      srcLine: el.getAttribute('data--src-line'),
      className: el.className,
      textContentHasDollar: tc.indexOf('$') >= 0,
      textContentSnippet: tc.slice(0, 140),
      imgsWithDollarAlt: imgs,
      visibleTextNodesWithDollar: visibleTexts
    });
  }
  return out;
})()`);

console.log('=== alt 文本可见性判定 ===');
console.log(JSON.stringify(r, null, 2));
console.log('');
if (r && r.matches) {
  for (const m of r.matches) {
    const hasVisible = (m.visibleTextNodesWithDollar || []).length > 0;
    const hasAltOnly = (m.imgsWithDollarAlt || []).length > 0 && !hasVisible;
    console.log('blockIndex=' + m.blockIndex + ' srcLine=' + m.srcLine);
    console.log('  textContentHasDollar=' + m.textContentHasDollar);
    console.log('  可见文本节点含$: ' + JSON.stringify(m.visibleTextNodesWithDollar));
    console.log('  img alt 含$: ' + JSON.stringify(m.imgsWithDollarAlt));
    console.log('  ★ 判定: ' + (hasVisible ? '(b) 可见题注 ⇒ 真 bug' : hasAltOnly ? '(a) 仅 img 属性 ⇒ 用户看不见' : '其它'));
    console.log('');
  }
}
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
