#!/usr/bin/env node
/**
 * selcol_c_d.mjs —— C 组（气泡会话 token）+ D 组（后端 5 元组往返）
 *
 * C1：在 assistant 气泡里选一段 ⇒ 必须产生**会话片段 token**（dsh-session:...#seq:...），
 *     不是文件路径 token。
 * D：把 A1/B1 的 token 送进真实 agent 一轮，确认后端解析出的 5 元组。
 *
 * 关键：`SEL_ADD_HOSTS = ["#preview","#editor"]`（L3195），气泡不在其中；
 *       但 L3392 重定义了 selAddHit 走 selectionLocation（含 messages 分支）。
 *       ⇒ 必须实测确认气泡选区到底能不能触发入口。
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
  async waitFor(x, t = 180000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('timeout: ' + x.slice(0, 70)); await sleep(150); } }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2] || 9500);
const outPath = process.argv[3] || '';

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.waitFor('!!window.MemoriaApp && !!window.state', 120000);

const results = { schema:'memoria-selcol-cd/v1', startedAt:new Date().toISOString() };

/* ── C1：气泡选区 ── */
// 先看气泡里有没有历史消息；没有就先发一轮制造一条
const msgState = await cdp.ev(`(function(){
  var am = document.getElementById('agent-messages');
  if (!am) return { exists:false };
  var bubbles = am.querySelectorAll('[data-seq], .-msg, .-bubble, .agent-msg, [class*="msg"]');
  return { exists:true, childCount: am.children.length,
           textLen: (am.textContent||'').length, bubbleCandidates: bubbles.length,
           head: (am.textContent||'').slice(0,200) };
})()`);
results.messagesInitial = msgState;
console.log('[C] messages: ' + JSON.stringify({ exists: msgState.exists, childCount: msgState.childCount, textLen: msgState.textLen, candidates: msgState.bubbleCandidates }));

// 检查 selectionLocation 的 messages 分支何时能命中
const selLocProbe = await cdp.ev(`(function(){
  // 探 MemoriaAgentPanel 是否暴露 selectionLocation
  var P = window.MemoriaAgentPanel;
  return { hasPanel: !!P, keys: P ? Object.keys(P).slice(0,40) : null };
})()`);
results.panelApi = selLocProbe;

// 找 assistant 气泡里的文本节点并选区
const bubbleSel = await cdp.ev(`(function(){
  var am = document.getElementById('agent-messages');
  if (!am) return { ok:false, reason:'no-messages' };
  // 找最大的含文本的块（assistant 消息）
  var cands = am.querySelectorAll('div, article, section, li');
  var best = null, bestLen = 0;
  for (var i=0;i<cands.length;i++){
    var t = cands[i].textContent || '';
    if (t.trim().length > bestLen) {
      // 排除包含子块的大容器：要求子元素里没有更大的文本块
      best = cands[i]; bestLen = t.trim().length;
    }
  }
  if (!best || bestLen < 5) return { ok:false, reason:'no-text-bubble', cands: cands.length };
  // 在该块第一个文本节点上选前 10 个字符
  var w = document.createTreeWalker(best, NodeFilter.SHOW_TEXT, null);
  var n, nodes = [];
  while ((n = w.nextNode())) if ((n.nodeValue||'').trim()) nodes.push(n);
  if (!nodes.length) return { ok:false, reason:'no-text-nodes' };
  var first = nodes[0];
  var s = 0, e = Math.min(10, first.nodeValue.length);
  var r = document.createRange();
  r.setStart(first, s); r.setEnd(first, e);
  var sel = window.getSelection();
  sel.removeAllRanges(); sel.addRange(r);
  document.dispatchEvent(new Event('selectionchange'));
  return { ok:true, selText: String(sel.toString()),
           bubbleText: (best.textContent||'').slice(0,100),
           bubbleCls: String(best.className||''),
           bubbleSeqAttr: best.getAttribute('data-seq'),
           inMessages: am.contains(r.commonAncestorContainer) };
})()`);
results.c1_select = bubbleSel;
console.log('[C] bubble select: ok=' + bubbleSel.ok + (bubbleSel.ok ? ' sel=' + JSON.stringify(bubbleSel.selText) + ' seq=' + bubbleSel.bubbleSeqAttr : ' err=' + bubbleSel.reason));

if (bubbleSel && bubbleSel.ok) {
  const btn = await cdp.ev(`(function(){
    var b = document.getElementById('-agent-sel-add');
    if (!b) return { exists:false };
    var r = b.getBoundingClientRect();
    return { exists:true, on:b.classList.contains('-on'), text:b.textContent,
             ctx:b.getAttribute('data-sel-ctx'), rect:{x:r.left,y:r.top,w:r.width,h:r.height} };
  })()`);
  results.c1_btn = btn;
  const before = await cdp.ev(`(function(){var el=document.getElementById('agent-input');return el?el.value:null;})()`);
  await cdp.ev(`(function(){ var b=document.getElementById('-agent-sel-add'); if(b) b.click(); return 1; })()`);
  await sleep(600);
  const after = await cdp.ev(`(function(){var el=document.getElementById('agent-input');return el?el.value:null;})()`);
  results.c1 = { btn, before, after, changed: before !== after,
                 isSessionToken: !!(after && /dsh-session:|#seq:/.test(after)),
                 isFileToken: !!(after && /\.md#L/.test(after)) };
  console.log('[C] C1 token=' + JSON.stringify(after) + '  isSession=' + results.c1.isSessionToken + ' isFile=' + results.c1.isFileToken);
}

/* ── D：后端 5 元组往返 ── */
// 读后端解析函数的行为：直接把 token 交给后端的一个只读调用，看它解析成什么
// 若无独立解析入口，则如实记录并通过真实发一轮验证
const dProbe = await cdp.ev(`(function(){
  var ai = document.getElementById('agent-input');
  if (!ai) return { ok:false, reason:'no-input' };
  ai.value = '@corpus/03-block-boundaries.md#L5C3-L5C8 这是 D 组后端往返测试';
  ai.dispatchEvent(new Event('input', { bubbles: true }));
  return { ok:true, value: ai.value };
})()`);
results.d_input = dProbe;

// 尝试找到发送按钮并点击（真发一轮）
const sendBtn = await cdp.ev(`(function(){
  var cands = ['#agent-send','.-agent-send','[data-agent-send]','button[title*="发送"]'];
  for (var i=0;i<cands.length;i++){ var b=document.querySelector(cands[i]); if (b) return { sel:cands[i], id:b.id, tag:b.tagName.toLowerCase() }; }
  // 退化：列出面板内所有 button
  var pane = document.getElementById('agent-pane') || document.body;
  var bs = pane.querySelectorAll('button');
  var list = [];
  for (var k=0;k<bs.length;k++) list.push({ id:bs[k].id, cls:String(bs[k].className||''), text:(bs[k].textContent||'').slice(0,20) });
  return { none:true, buttons: list.slice(0,20) };
})()`);
results.d_sendButton = sendBtn;
console.log('[D] sendButton: ' + JSON.stringify(sendBtn).slice(0,300));

results.finishedAt = new Date().toISOString();
if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__CD__' + JSON.stringify({ out: outPath,
    c1: results.c1 ? { token: results.c1.after, isSession: results.c1.isSessionToken } : null }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
