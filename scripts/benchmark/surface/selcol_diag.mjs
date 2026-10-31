#!/usr/bin/env node
/** selcol_diag.mjs —— 诊断：编辑器/预览/气泡的真实 DOM 结构 + 选区通路是否有效 */
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
const file = process.argv[3] || 'corpus/03-block-boundaries.md';
const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.waitFor('!!window.MemoriaApp && !!window.state', 120000);
await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)},{skipNav:true})`);
await cdp.waitFor(`window.state.currentPath===${JSON.stringify(file)} && !!window.state.doc`, 40000);
await sleep(1200);

const out = await cdp.ev(`(function(){
  var r = {};
  // ── 编辑器结构 ──
  var ed = document.getElementById('editor');
  r.editor = { exists: !!ed, contentEditable: ed ? ed.contentEditable : null,
               childCount: ed ? ed.children.length : null,
               textLen: ed ? (ed.textContent||'').length : null,
               textHead: ed ? (ed.textContent||'').slice(0,120) : null };
  if (ed && ed.children.length) {
    r.editor.firstChildren = [];
    for (var i=0;i<Math.min(4, ed.children.length);i++){
      var c = ed.children[i];
      r.editor.firstChildren.push({ tag:c.tagName.toLowerCase(), cls:String(c.className||''),
        textLen:(c.textContent||'').length, text:(c.textContent||'').slice(0,50),
        childNodes:c.childNodes.length });
    }
    // 找第一个有文本的后代
    var w = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT, null);
    var t, first=[];
    while ((t=w.nextNode()) && first.length<5) first.push({ text: t.nodeValue.slice(0,40), parentCls: t.parentElement?String(t.parentElement.className||''):'',
      parentTag: t.parentElement?t.parentElement.tagName.toLowerCase():'' });
    r.editor.firstTextNodes = first;
  }
  // 行元素候选数
  r.editor.lineCandidates = {};
  ['[data--line]','.-line','.-src-line','.-line-content','.-code-line','div.line'].forEach(function(s){
    try { r.editor.lineCandidates[s] = ed ? ed.querySelectorAll(s).length : 0; } catch(e){ r.editor.lineCandidates[s] = 'ERR'; }
  });
  // ── 预览结构 ──
  var pv = document.getElementById('preview');
  r.preview = { exists: !!pv, blockCount: pv ? pv.querySelectorAll('.-src-block').length : 0 };
  if (pv) {
    r.preview.blocks = [];
    var bs = pv.querySelectorAll('.-src-block');
    for (var k=0;k<Math.min(4,bs.length);k++){
      var b = bs[k];
      var wn = document.createTreeWalker(b, NodeFilter.SHOW_TEXT, null);
      var n, cnt=0;
      while (wn.nextNode()) cnt++;
      r.preview.blocks.push({ i:k, tag:b.tagName.toLowerCase(), cls:String(b.className||''),
        textLen:(b.textContent||'').length, text:(b.textContent||'').slice(0,50),
        textNodeCount: cnt, srcLine: b.getAttribute('data--src-line') });
    }
  }
  // ── composer ──
  var ai = document.getElementById('agent-input');
  r.composer = { exists: !!ai, tag: ai?ai.tagName.toLowerCase():null, value: ai?ai.value:null };
  // ── 气泡 ──
  var am = document.getElementById('agent-messages');
  r.messages = { exists: !!am, childCount: am?am.children.length:null,
                 textLen: am?(am.textContent||'').length:null };
  // ── 全局可用的面板 API ──
  r.api = { MemoriaAgentPanel: window.MemoriaAgentPanel ? Object.keys(window.MemoriaAgentPanel).slice(0,40) : null };
  return r;
})()`);
console.log(JSON.stringify(out, null, 2));
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
