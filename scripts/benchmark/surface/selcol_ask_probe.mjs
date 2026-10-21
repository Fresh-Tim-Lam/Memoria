#!/usr/bin/env node
/** selcol_ask_probe.mjs —— 摸清 agent_ask_start/poll 的真实响应结构与气泡更新时机 */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('t')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('e')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(m, p = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method: m, params: p })); }); }
  async ev(x) { const r = await this.send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true, userGesture: true }); if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); } return r.result ? r.result.value : undefined; }
  async waitFor(x, t = 120000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('timeout'); await sleep(150); } }
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

const out = { schema:'memoria-ask-probe/v1' };

// 发一轮
const ask = await cdp.ev(`(async function(){
  try { var r = await window.MemoriaApp.call('agent_ask_start', 'reply with the single word OK', null); return { ok:true, r:r }; }
  catch(e){ return { ok:false, err:String(e&&e.message||e) }; }
})()`);
out.ask = ask;
console.log('[ask] start: ' + JSON.stringify(ask).slice(0,300));

if (ask.ok && ask.r && ask.r.job_id) {
  // 头 3 次 poll 完整打印结构
  let cursor = 0;
  const polls = [];
  for (let i = 0; i < 6; i++) {
    const p = await cdp.ev(`(async function(){
      try { var r = await window.MemoriaApp.call('agent_ask_poll', ${JSON.stringify(ask.r.job_id)}, ${cursor}); return { ok:true, r:r }; }
      catch(e){ return { ok:false, err:String(e&&e.message||e) }; }
    })()`);
    polls.push(p);
    console.log('[ask] poll#' + (i+1) + ': ' + JSON.stringify(p).slice(0, 500));
    if (p.ok && p.r) {
      if (typeof p.r.cursor === 'number') cursor = p.r.cursor;
      const st = p.r.status || p.r.state || (p.r.job && p.r.job.status);
      if (st === 'done' || st === 'error' || p.r.finished) break;
    }
    await sleep(1200);
  }
  out.polls = polls;

  // 气泡状态
  const msgs = await cdp.ev(`(function(){
    var am=document.getElementById('agent-messages');
    if(!am) return null;
    var kids=[]; for(var i=0;i<am.children.length;i++){var c=am.children[i];kids.push({tag:c.tagName.toLowerCase(),cls:String(c.className||''),text:(c.textContent||'').slice(0,120)});}
    return { childCount:am.children.length, textLen:(am.textContent||'').length, kids:kids };
  })()`);
  out.messages = msgs;
  console.log('[ask] messages: ' + JSON.stringify(msgs).slice(0,600));
}

if (outPath) {
  const fs = await import('node:fs');
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8');
  console.log('__ASK__' + JSON.stringify({ out: outPath }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
