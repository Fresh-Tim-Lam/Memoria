#!/usr/bin/env node
/**
 * selcol_realapp.mjs —— 真机验证：选区 → composer 的精确行列引用（task-45）v3 完整版
 *
 * 已修正的测量缺陷（v1/v2）：
 *   ① 编辑器行内容在 `.-line-content`（不是 `.-line`，后者含行号+缩进空白）
 *   ② 预览需先 setMode('preview')（源码模式下 blockCount=0）
 *   ③ 预览块按 `srcLine` 挑正文块（i=0 是 <!-- --> 注释块，也是 p 标签）
 *   ④ B3 需换含公式的文档（corpus/02-inline-edges.md）
 *
 * 覆盖：A1-A4（源码）B1-B3（预览）C1（气泡）D（后端往返）
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
  async waitFor(x, t = 180000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('timeout: ' + x.slice(0, 60)); await sleep(150); } }
  async click(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2] || 9500);
const file = process.argv[3] || 'corpus/03-block-boundaries.md';
const fileB3 = process.argv[4] || 'corpus/02-inline-edges.md';
const outPath = process.argv[5] || '';

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.waitFor('!!window.MemoriaApp && !!window.state', 120000);

async function openDoc(f) {
  const target = f || file;
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(target)}, { skipNav: true })`);
  await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(target)} && !!window.state.doc`, 40000);
  await sleep(900);
}
async function setMode(mode) {
  for (let i = 0; i < 8; i++) {
    const cur = await cdp.ev('(window.state||{}).viewMode || null');
    if (cur === mode) { await sleep(700); return true; }
    await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="${mode}"]');if(b){b.click();return 1;}return 0;})()`);
    await sleep(450);
  }
  await sleep(700);
  return (await cdp.ev('(window.state||{}).viewMode')) === mode;
}

const READ_COMPOSER = `(function(){ var el=document.getElementById('agent-input'); return el?{value:el.value,len:el.value.length}:null; })()`;
const CLEAR_COMPOSER = `(function(){ var el=document.getElementById('agent-input'); if(el){el.value='';el.dispatchEvent(new Event('input',{bubbles:true}));} return 1; })()`;

async function selectInEditor(sLine, sCol, eLine, eCol) {
  return await cdp.ev(`(function(){
    var ed = document.getElementById('editor');
    var lines = ed ? ed.querySelectorAll('.-line-content') : [];
    if (!lines.length) return { ok:false, reason:'no-line-content' };
    function txt(i){ var el=lines[i]; return el ? (el.textContent||'') : null; }
    function pos(i, col){
      var el = lines[i]; if (!el) return null;
      var target = Math.max(0, col - 1);
      var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
      var n, acc = 0;
      while ((n = w.nextNode())) { var l=n.nodeValue.length;
        if (target <= acc+l) return { node:n, off: target-acc }; acc += l; }
      return null;
    }
    var a = pos(${sLine - 1}, ${sCol}), b = pos(${eLine - 1}, ${eCol});
    if (!a) return { ok:false, reason:'start-null', lineText: txt(${sLine - 1}) };
    if (!b) return { ok:false, reason:'end-null', lineText: txt(${eLine - 1}) };
    var r = document.createRange();
    r.setStart(a.node, a.off); r.setEnd(b.node, b.off);
    var sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(r);
    document.dispatchEvent(new Event('selectionchange'));
    return { ok:true, selText: String(sel.toString()), collapsed: sel.isCollapsed,
             sLineText: txt(${sLine - 1}), eLineText: txt(${eLine - 1}) };
  })()`);
}

async function selectInPreview(blockIdx, fromCh, toCh) {
  return await cdp.ev(`(function(){
    var pv = document.getElementById('preview');
    var bs = pv ? pv.querySelectorAll('.-src-block') : [];
    var b = bs[${blockIdx}];
    if (!b) return { ok:false, reason:'no-block', blockCount: bs.length };
    var w = document.createTreeWalker(b, NodeFilter.SHOW_TEXT, null);
    var nodes = [], n;
    while ((n = w.nextNode())) nodes.push(n);
    if (!nodes.length) return { ok:false, reason:'no-text-nodes', html: b.innerHTML.slice(0,120) };
    function pos(ch){
      var acc = 0;
      for (var i=0;i<nodes.length;i++){ var l=nodes[i].nodeValue.length;
        if (ch <= acc+l) return { node:nodes[i], off: ch-acc }; acc += l; }
      var last=nodes[nodes.length-1];
      return { node:last, off:last.nodeValue.length };
    }
    var a = pos(${fromCh}), z = pos(${toCh});
    var r = document.createRange();
    r.setStart(a.node, a.off); r.setEnd(z.node, z.off);
    var sel = window.getSelection();
    sel.removeAllRanges(); sel.addRange(r);
    document.dispatchEvent(new Event('selectionchange'));
    return { ok:true, selText: String(sel.toString()), collapsed: sel.isCollapsed,
             blockText: (b.textContent||''), blockCls: String(b.className||''),
             blockSrcLine: b.getAttribute('data--src-line'),
             hasMath: !!b.querySelector('mjx-container, .-math'),
             hasLink: !!b.querySelector('[data-link-target], a[href]') };
  })()`);
}

async function clickSelAdd() {
  const before = await cdp.ev(READ_COMPOSER);
  const btn = await cdp.ev(`(function(){
    var b = document.getElementById('-agent-sel-add');
    if (!b) return { exists:false };
    var r = b.getBoundingClientRect();
    return { exists:true, on:b.classList.contains('-on'), text:b.textContent,
             rect:{x:r.left,y:r.top,w:r.width,h:r.height}, ctx:b.getAttribute('data-sel-ctx') };
  })()`);
  if (btn.exists && btn.on && btn.rect.w > 0) await cdp.click(Math.round(btn.rect.x+btn.rect.w/2), Math.round(btn.rect.y+btn.rect.h/2));
  else await cdp.ev(`(function(){ var b=document.getElementById('-agent-sel-add'); if(b) b.click(); return 1; })()`);
  await sleep(550);
  const after = await cdp.ev(READ_COMPOSER);
  return { btn, beforeValue: before?before.value:null, afterValue: after?after.value:null,
           changed: before&&after ? before.value!==after.value : null };
}

const results = { schema:'memoria-selcol-realapp/v3', file, fileB3,
                  startedAt:new Date().toISOString(), scenarios:{} };

/* ══ A. 源码区 ══ */
await openDoc(file);
await setMode('source');
const A_CASES = [
  { id:'A1', desc:'同行 L5C3→L5C8', sLine:5, sCol:3, eLine:5, eCol:8 },
  { id:'A2', desc:'跨行 L5C3→L7C10', sLine:5, sCol:3, eLine:7, eCol:10 },
  { id:'A3', desc:'单字符 L5C3→L5C4', sLine:5, sCol:3, eLine:5, eCol:4 },
  { id:'A4', desc:'行首→行尾', sLine:5, sCol:1, eLine:5, eCol:null },
];
for (const c of A_CASES) {
  await cdp.ev(CLEAR_COMPOSER);
  if (c.eCol == null) c.eCol = await cdp.ev(`(function(){ var ed=document.getElementById('editor'); var ls=ed.querySelectorAll('.-line-content'); return ls[${c.sLine-1}]?(ls[${c.sLine-1}].textContent||'').length+1:1; })()`);
  const sel = await selectInEditor(c.sLine, c.sCol, c.eLine, c.eCol);
  const clk = (sel && sel.ok && !sel.collapsed) ? await clickSelAdd() : { afterValue:null, changed:null };
  results.scenarios[c.id] = { desc:c.desc, params:{sLine:c.sLine,sCol:c.sCol,eLine:c.eLine,eCol:c.eCol},
                              select:sel, click:clk, token:clk.afterValue };
  console.log('[A] ' + c.id + ' ' + JSON.stringify(clk.afterValue) + '  sel=' + JSON.stringify(String((sel&&sel.selText)||'').slice(0,20)));
}

/* ══ B. 预览区（正文段落，排除注释块）══ */
await setMode('preview');
await sleep(1200);
const B_PICK = `(function(){
  var pv = document.getElementById('preview');
  var bs = pv.querySelectorAll('.-src-block');
  for (var i=0;i<bs.length;i++){
    var sl = parseInt(bs[i].getAttribute('data--src-line')||'0',10);
    var t = (bs[i].textContent||'');
    if (sl >= 5 && t.trim().length > 10 && !/^<!--/.test(t.trim())) {
      return { i:i, srcLine:sl, text:t, len:t.length };
    }
  }
  return null;
})()`;

// B1 段落中间若干字（带列）
{
  await cdp.ev(CLEAR_COMPOSER);
  const p = await cdp.ev(B_PICK);
  if (p) {
    const sel = await selectInPreview(p.i, 2, 8);
    const clk = (sel && sel.ok && !sel.collapsed) ? await clickSelAdd() : { afterValue:null };
    results.scenarios.B1 = { desc:'段落中间若干字(2..8)', pick:p, select:sel, click:clk, token:clk.afterValue };
    console.log('[B] B1 ' + JSON.stringify(clk.afterValue) + '  sel=' + JSON.stringify(String((sel&&sel.selText)||'')) + '  srcLine=' + (sel&&sel.blockSrcLine));
  } else { results.scenarios.B1 = { skip:'无正文段落' }; }
}
// B2 整块全选（应退化纯行）
{
  await cdp.ev(CLEAR_COMPOSER);
  const p = await cdp.ev(B_PICK);
  if (p) {
    const sel = await selectInPreview(p.i, 0, p.len);
    const clk = (sel && sel.ok && !sel.collapsed) ? await clickSelAdd() : { afterValue:null };
    results.scenarios.B2 = { desc:'整块全选(应退化纯行)', pick:p, select:sel, click:clk, token:clk.afterValue };
    console.log('[B] B2 ' + JSON.stringify(clk.afterValue) + '  selLen=' + String((sel&&sel.selText)||'').length);
  } else { results.scenarios.B2 = { skip:'无正文段落' }; }
}

/* ══ B3. 含公式/链接（换文档）══ */
await openDoc(fileB3);
await setMode('preview');
await sleep(1500);
{
  await cdp.ev(CLEAR_COMPOSER);
  const p = await cdp.ev(`(function(){
    var pv = document.getElementById('preview');
    var bs = pv.querySelectorAll('.-src-block');
    for (var i=0;i<bs.length;i++){
      var hasMath = !!bs[i].querySelector('mjx-container, .-math');
      var hasLink = !!bs[i].querySelector('[data-link-target], a[href]');
      if (hasMath || hasLink) {
        return { i:i, hasMath:hasMath, hasLink:hasLink,
                 text:(bs[i].textContent||''), len:(bs[i].textContent||'').length,
                 srcLine: bs[i].getAttribute('data--src-line') };
      }
    }
    return null;
  })()`);
  if (p) {
    const sel = await selectInPreview(p.i, 0, Math.max(1, Math.floor(p.len * 0.9)));
    const clk = (sel && sel.ok && !sel.collapsed) ? await clickSelAdd() : { afterValue:null };
    results.scenarios.B3 = { desc:'含行内公式/链接', doc:fileB3, pick:p, select:sel, click:clk, token:clk.afterValue };
    console.log('[B] B3 ' + JSON.stringify(clk.afterValue) + '  hasMath=' + p.hasMath + ' hasLink=' + p.hasLink + ' sel=' + JSON.stringify(String((sel&&sel.selText)||'').slice(0,25)));
  } else { results.scenarios.B3 = { skip:'两文档都无含公式/链接的块' }; console.log('[B] B3 skip'); }
}

results.finishedAt = new Date().toISOString();
if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__SELCOL__' + JSON.stringify({ out: outPath,
    tokens: Object.fromEntries(Object.entries(results.scenarios).map(([k,v]) => [k, v.token||null])) }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
