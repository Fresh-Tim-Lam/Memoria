#!/usr/bin/env node
/**
 * selcol_c1_real.mjs —— C1 真实会话 token（走面板自己的发送路径，让气泡真正生成）
 *
 * 上一版失败原因：直接调 `agent_ask_start` RPC 绕过了面板渲染管线 ⇒ 气泡不更新。
 * 本版：写入 #agent-input → 点 #agent-send（= 用户真实操作）→ 等气泡出现
 *       → 在 assistant 气泡里选区 → 读 composer token。
 */
import fs from 'node:fs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('t')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('e')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(m, p = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method: m, params: p })); }); }
  async ev(x) { const r = await this.send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true, userGesture: true }); if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); } return r.result ? r.result.value : undefined; }
  async waitFor(x, t = 180000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('timeout: ' + x.slice(0, 70)); await sleep(250); } }
  async click(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2] || 9500);
const outPath = process.argv[3] || '';
const file = 'corpus/03-block-boundaries.md';

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.waitFor('!!window.MemoriaApp && !!window.state', 120000);
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 40000);
await sleep(900);

const results = { schema:'memoria-selcol-c1-real/v1', startedAt:new Date().toISOString() };

/* ── 1) 走面板真实发送：填 input → 点 #agent-send ── */
const fill = await cdp.ev(`(function(){
  var ai = document.getElementById('agent-input');
  if (!ai) return { ok:false, reason:'no-input' };
  ai.value = 'reply with the single word OK';
  ai.dispatchEvent(new Event('input', { bubbles: true }));
  ai.dispatchEvent(new Event('change', { bubbles: true }));
  var b = document.getElementById('agent-send');
  if (!b) return { ok:false, reason:'no-send-btn', value: ai.value };
  var r = b.getBoundingClientRect();
  return { ok:true, value: ai.value, disabled: !!b.disabled,
           rect:{x:r.left,y:r.top,w:r.width,h:r.height} };
})()`);
results.fill = fill;
console.log('[c1] fill: ' + JSON.stringify(fill));

if (fill && fill.ok && fill.rect && fill.rect.w > 0) {
  await cdp.click(Math.round(fill.rect.x + fill.rect.w/2), Math.round(fill.rect.y + fill.rect.h/2));
  console.log('[c1] clicked #agent-send');

  // 等气泡出现（最多 90s）
  let appeared = false;
  for (let i = 0; i < 90; i++) {
    await sleep(1000);
    const st = await cdp.ev(`(function(){
      var am=document.getElementById('agent-messages');
      if(!am) return { n:0, empty:true };
      var empty = !!am.querySelector('.-agent-empty');
      var txt = (am.textContent||'');
      var generating = txt.indexOf('智能体生成中') >= 0 || txt.indexOf('生成中') >= 0;
      return { n: am.children.length, empty: empty, textLen: txt.length, generating: generating };
    })()`);
    if (!st.empty && st.textLen > 30 && !st.generating) { appeared = true; results.waitedSec = i + 1; break; }
  }
  results.bubbleAppeared = appeared;
  console.log('[c1] bubble appeared=' + appeared + (appeared ? ' after ' + results.waitedSec + 's' : ''));
}

/* ── 2) 气泡结构 ── */
const msgs = await cdp.ev(`(function(){
  var am=document.getElementById('agent-messages');
  if(!am) return null;
  var kids=[];
  for(var i=0;i<am.children.length;i++){
    var c=am.children[i];
    kids.push({ i:i, tag:c.tagName.toLowerCase(), cls:String(c.className||''),
                text:(c.textContent||'').slice(0,120),
                seq: c.getAttribute('data-agent-seq'),
                childCount: c.children.length });
  }
  // 找带 data-seq 的元素
  var seqEls = am.querySelectorAll('[data-agent-seq]');
  var seqList = [];
  for (var k=0;k<seqEls.length;k++) seqList.push({ seq: seqEls[k].getAttribute('data-agent-seq'),
    cls:String(seqEls[k].className||''), text:(seqEls[k].textContent||'').slice(0,80) });
  return { childCount:am.children.length, textLen:(am.textContent||'').length, kids:kids, seqEls:seqList };
})()`);
results.messages = msgs;
console.log('[c1] messages: children=' + (msgs?msgs.childCount:null) + ' seqEls=' + (msgs?msgs.seqEls.length:null));

/* ── 3) 在 assistant 气泡里选区 → 读 composer ── */
if (msgs && msgs.seqEls && msgs.seqEls.length) {
  const bsel = await cdp.ev(`(function(){
    var am=document.getElementById('agent-messages');
    var els = am.querySelectorAll('[data-agent-seq]');
    // 取最后一个（assistant 回答）
    var best = els[els.length-1];
    var w=document.createTreeWalker(best,NodeFilter.SHOW_TEXT,null);
    var n,nodes=[];
    while((n=w.nextNode())) if((n.nodeValue||'').trim()) nodes.push(n);
    if(!nodes.length) return { ok:false, reason:'no-text-nodes' };
    var f=nodes[0], e=Math.min(6, f.nodeValue.length);
    var r=document.createRange(); r.setStart(f,0); r.setEnd(f,e);
    var sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
    document.dispatchEvent(new Event('selectionchange'));
    return { ok:true, selText:String(sel.toString()),
             bubbleText:(best.textContent||'').slice(0,120),
             seq: best.getAttribute('data-agent-seq'),
             bubbleCls: String(best.className||'') };
  })()`);
  results.c1_select = bsel;
  console.log('[c1] select: ' + JSON.stringify(bsel).slice(0,250));

  if (bsel && bsel.ok) {
    const btn = await cdp.ev(`(function(){
      var b=document.getElementById('-agent-sel-add');
      if(!b) return { exists:false };
      var r=b.getBoundingClientRect();
      return { exists:true, on:b.classList.contains('-on'), text:b.textContent,
               ctx:b.getAttribute('data-sel-ctx'), rect:{x:r.left,y:r.top,w:r.width,h:r.height} };
    })()`);
    results.c1_btn = btn;
    const before = await cdp.ev(`(function(){var el=document.getElementById('agent-input');return el?el.value:'';})()`);
    await cdp.ev(`(function(){ var b=document.getElementById('-agent-sel-add'); if(b) b.click(); return 1; })()`);
    await sleep(800);
    const after = await cdp.ev(`(function(){var el=document.getElementById('agent-input');return el?el.value:'';})()`);
    results.c1 = { btn, before, after, changed: before !== after,
                   isSessionToken: /dsh-session:|#seq:/.test(after),
                   isFileToken: /\.md#L/.test(after) };
    console.log('[c1] TOKEN=' + JSON.stringify(after) + ' isSession=' + results.c1.isSessionToken + ' isFile=' + results.c1.isFileToken);
  }
} else {
  console.log('[c1] 无 [data-seq] 气泡，无法选区');
}

results.finishedAt = new Date().toISOString();
if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__C1__' + JSON.stringify({ out: outPath,
    appeared: results.bubbleAppeared, c1: results.c1 || null }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
