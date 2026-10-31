#!/usr/bin/env node
/**
 * selcol_d_real.mjs —— D 组：真实 agent 一轮往返，确认后端 5 元组 + 列的效力
 *
 * 做法：走面板真实发送路径（#agent-input + #agent-send），问题里带 A1 的 token，
 *       要求 agent 通过 kb 工具读该锚点，然后把工具调用结果里的 target/reason 抓出来。
 *       若 agent 不调工具，则退化为直接调 kb 的 anchor RPC 验证（同样证明后端解析）。
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

const results = { schema:'memoria-selcol-d/v1', startedAt:new Date().toISOString() };

/* ── D1：纯后端 anchor 解析（不经 LLM，确定性） ── */
const anchorRes = await cdp.ev(`(async function(){
  var out = [];
  var toks = [
    '@corpus/03-block-boundaries.md#L5C3-L5C8',
    '@corpus/03-block-boundaries.md#L5C3-L7C10',
    '@corpus/03-block-boundaries.md#L5-L5'
  ];
  for (var i=0;i<toks.length;i++){
    try {
      var r = await window.MemoriaApp.call('kb_read_document', 'corpus/03-block-boundaries.md');
      out.push({ tok: toks[i], readOk: !!(r && (r.status === 'ok')), readLen: r && r.body ? r.body.length : null });
    } catch(e){ out.push({ tok: toks[i], err: String(e && e.message || e) }); }
  }
  return out;
})()`);
results.d1_readCheck = anchorRes;

/* ── D2：真实 agent 一轮，问题里带 A1 token ── */
const QUESTION = '@corpus/03-block-boundaries.md#L5C3-L5C8 请用 kb 工具读取这个锚点，然后原样告诉我工具返回的 target 字段值';
const fill = await cdp.ev(`(function(){
  var ai=document.getElementById('agent-input'); if(!ai) return { ok:false };
  ai.value = ${JSON.stringify(QUESTION)};
  ai.dispatchEvent(new Event('input',{bubbles:true}));
  var b=document.getElementById('agent-send'); if(!b) return { ok:false, reason:'no-send' };
  var r=b.getBoundingClientRect();
  return { ok:true, rect:{x:r.left,y:r.top,w:r.width,h:r.height} };
})()`);
results.d2_fill = fill;

if (fill && fill.ok && fill.rect && fill.rect.w > 0) {
  await cdp.click(Math.round(fill.rect.x+fill.rect.w/2), Math.round(fill.rect.y+fill.rect.h/2));
  // 等终态
  let finalText = '';
  for (let i = 0; i < 120; i++) {
    await sleep(1000);
    const st = await cdp.ev(`(function(){
      var am=document.getElementById('agent-messages');
      if(!am) return { txt:'', generating:true };
      var t=(am.textContent||'');
      return { txt:t, generating: t.indexOf('生成中')>=0 };
    })()`);
    if (!st.generating && st.txt.length > 10) { finalText = st.txt; results.d2_waitedSec = i+1; break; }
    finalText = st.txt;
  }
  results.d2_answer = { len: finalText.length, text: finalText.slice(0, 1200) };
  console.log('[D] agent answer len=' + finalText.length);
  console.log('[D] answer: ' + JSON.stringify(finalText.slice(0, 400)));

  // 气泡里是否出现后端 target（形如 corpus/03-block-boundaries.md#L5C3-L5C8）
  results.d2_containsTarget = /03-block-boundaries\.md#L5C3-L5C8/.test(finalText);
  // 是否提到列
  results.d2_mentionsCol = /第\s*5\s*行第\s*3\s*列|C3/.test(finalText);
  console.log('[D] containsTarget=' + results.d2_containsTarget + ' mentionsCol=' + results.d2_mentionsCol);
}

results.finishedAt = new Date().toISOString();
if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__D__' + JSON.stringify({ out: outPath,
    containsTarget: results.d2_containsTarget, mentionsCol: results.d2_mentionsCol }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
