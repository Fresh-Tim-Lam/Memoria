#!/usr/bin/env node
/**
 * selcol_c1_d.mjs —— C1（气泡会话 token）+ D（后端 5 元组）真实往返
 *
 * C1 前置：必须先有**真实会话消息**（当前只有占位文本"还没有对话"）。
 *         路径：agent_get_config 看是否 enabled → agent_ask 发一轮 → 等 poll 出答案
 *         → 在 assistant 气泡里选段 → 读 composer token。
 * D  ：把 A1/B1 token 送进真实一轮，确认后端解析。若 agent 不可用，如实记为环境限制。
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
  async waitFor(x, t = 180000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('timeout: ' + x.slice(0, 70)); await sleep(200); } }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2] || 9500);
const outPath = Number(process.argv[3]) || process.argv[3] || '';
const file = 'corpus/03-block-boundaries.md';

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.waitFor('!!window.MemoriaApp && !!window.state', 120000);
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 40000);
await sleep(900);

const results = { schema:'memoria-selcol-c1d/v1', startedAt:new Date().toISOString() };

/* ── agent 配置 ── */
const cfg = await cdp.ev(`(async function(){
  try {
    var r = await window.MemoriaApp.call('agent_get_config');
    return { ok:true, cfg: r };
  } catch(e){ return { ok:false, err: String(e && e.message || e) }; }
})()`);
results.agentConfig = cfg;
const enabled = !!(cfg && cfg.ok && cfg.cfg && (cfg.cfg.enabled === true || cfg.cfg.enabled === 1));
console.log('[cd] agent config: ok=' + (cfg&&cfg.ok) + ' enabled=' + enabled +
  (cfg&&cfg.ok ? ' keys=' + JSON.stringify(Object.keys(cfg.cfg||{})) : ' err=' + (cfg&&cfg.err)));

/* ── C1 + D：若能发一轮，就发 ── */
if (!enabled) {
  results.c1 = { skip: 'agent 未启用（enabled=false），无法生成真实会话消息' };
  results.d  = { skip: 'agent 未启用，无法做真实后端往返' };
  console.log('[cd] agent disabled ⇒ C1/D 记为环境限制');
} else {
  // 构造带 A1 token 的问题（D 组同时验证后端 5 元组）
  const QUESTION = '@corpus/03-block-boundaries.md#L5C3-L5C8 请只回复 ok';
  const askRes = await cdp.ev(`(async function(){
    try {
      var r = await window.MemoriaApp.call('agent_ask_start', ${JSON.stringify(QUESTION)}, null);
      return { ok:true, res:r };
    } catch(e){ return { ok:false, err:String(e && e.message || e) }; }
  })()`);
  results.d_ask = askRes;
  console.log('[cd] agent_ask: ' + JSON.stringify(askRes).slice(0, 300));

  if (askRes && askRes.ok && askRes.res && askRes.res.job_id) {
    // poll 直到完成
    let cursor = 0, done = false, answer = '', tries = 0;
    while (!done && tries < 120) {
      tries++;
      const poll = await cdp.ev(`(async function(){
        try { var r = await window.MemoriaApp.call('agent_ask_poll', ${JSON.stringify(askRes.res.job_id)}, ${cursor}); return { ok:true, r:r }; }
        catch(e){ return { ok:false, err:String(e&&e.message||e) }; }
      })()`);
      if (!poll.ok) { results.d_pollErr = poll; break; }
      const p = poll.r || {};
      if (typeof p.text === 'string') answer += p.text;
      cursor = (p.cursor != null) ? p.cursor : cursor;
      if (p.done || p.status === 'done' || p.finished) done = true;
      await sleep(500);
    }
    results.d_answer = { done, len: answer.length, head: answer.slice(0, 300) };
    console.log('[cd] poll done=' + done + ' answerLen=' + answer.length);

    // 等气泡出现
    await sleep(1500);
    const msgState = await cdp.ev(`(function(){
      var am = document.getElementById('agent-messages');
      if (!am) return { exists:false };
      return { exists:true, childCount:am.children.length, textLen:(am.textContent||'').length,
               head:(am.textContent||'').slice(0,150) };
    })()`);
    results.messagesAfter = msgState;
    console.log('[cd] messages after: ' + JSON.stringify(msgState).slice(0, 200));

    // ── C1：在 assistant 气泡里选一段 ──
    const bsel = await cdp.ev(`(function(){
      var am = document.getElementById('agent-messages');
      if (!am) return { ok:false, reason:'no-messages' };
      // 排除空态占位
      var cands = am.querySelectorAll('[data-seq], .-agent-msg, .-msg, .-bubble, .-assistant, article');
      var pool = [];
      for (var i=0;i<cands.length;i++) pool.push(cands[i]);
      if (!pool.length) {
        // 退化：取 messages 的直接子节点里文本最长的
        for (var k=0;k<am.children.length;k++) pool.push(am.children[k]);
      }
      var best=null,bestLen=0;
      for (var j=0;j<pool.length;j++){
        var t=(pool[j].textContent||'').trim();
        if (String(pool[j].className||'').indexOf('-agent-empty')>=0) continue;
        if (t.length>bestLen){ best=pool[j]; bestLen=t.length; }
      }
      if (!best || bestLen<5) return { ok:false, reason:'no-real-bubble', poolN:pool.length };
      var w=document.createTreeWalker(best,NodeFilter.SHOW_TEXT,null);
      var n,nodes=[];
      while((n=w.nextNode())) if((n.nodeValue||'').trim()) nodes.push(n);
      if(!nodes.length) return { ok:false, reason:'no-text-nodes' };
      var f=nodes[0], e=Math.min(8, f.nodeValue.length);
      var r=document.createRange(); r.setStart(f,0); r.setEnd(f,e);
      var sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
      document.dispatchEvent(new Event('selectionchange'));
      return { ok:true, selText:String(sel.toString()), bubbleText:(best.textContent||'').slice(0,120),
               bubbleCls:String(best.className||''),
               seqAttr: best.getAttribute('data-seq'),
               hasSeqAncestor: (function(){
                 var el=best, hops=0;
                 while(el && hops<8){ if(el.getAttribute && el.getAttribute('data-seq')!=null) return el.getAttribute('data-seq'); el=el.parentElement; hops++; }
                 return null;
               })() };
    })()`);
    results.c1_select = bsel;
    console.log('[cd] C1 select: ok=' + bsel.ok + (bsel.ok ? ' sel=' + JSON.stringify(bsel.selText) + ' seq=' + bsel.seqAttr + '/' + bsel.hasSeqAncestor : ' err=' + bsel.reason));

    if (bsel && bsel.ok) {
      const before = await cdp.ev(`(function(){var el=document.getElementById('agent-input');return el?el.value:'';})()`);
      await cdp.ev(`(function(){ var b=document.getElementById('-agent-sel-add'); if(b) b.click(); return 1; })()`);
      await sleep(700);
      const after = await cdp.ev(`(function(){var el=document.getElementById('agent-input');return el?el.value:'';})()`);
      results.c1 = { before, after, changed: before !== after,
                     isSessionToken: /dsh-session:|#seq:/.test(after),
                     isFileToken: /\.md#L/.test(after) };
      console.log('[cd] C1 token=' + JSON.stringify(after) + ' isSession=' + results.c1.isSessionToken + ' isFile=' + results.c1.isFileToken);
    }
  } else {
    results.d = { skip: 'agent_ask 未返回 job_id', res: askRes };
  }
}

results.finishedAt = new Date().toISOString();
if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__C1D__' + JSON.stringify({ out: outPath,
    c1: results.c1 || null, d_ok: !!results.d_answer }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
