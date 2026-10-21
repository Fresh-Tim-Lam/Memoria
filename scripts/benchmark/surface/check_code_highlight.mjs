#!/usr/bin/env node
/**
 * check_code_highlight.mjs —— P6a 补丁的独立断言：预览代码块高亮完整性（不污染冻结签名）。
 *
 * 断言（对每篇含围栏代码的文档）：
 *   `#preview pre.-code-block > code` 的**归一化 innerHTML（tag + class 序列）**
 *   === `MemoriaCodeHighlight.render(sameText, sameLang)` 的直接输出（同序列）。
 * 覆盖：高亮缺失、降级成纯文本、错 class、文本被改。
 *
 * 判别力自证（同一进程内）：
 *   ① 把 code 的 innerHTML 掏空成纯文本（= 高亮未执行时的形态）⇒ 断言必须 RED；
 *   ② 重新 `MemoriaApp.renderPreview(state.doc)` 走生产后处理恢复 ⇒ 断言必须 GREEN。
 *
 * 用法：node scripts/benchmark/surface/check_code_highlight.mjs --cdp <endpoint> --kb <abs> --files a,b --out <json>
 */
import fs from 'node:fs';
import path from 'node:path';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(url) { const r = await fetch(url); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('CDP WS 超时')), 20000);
      ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('CDP WS 失败')); });
    });
  }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); }
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expr, { timeout = 90000, label = '' } = {}) { const t0 = Date.now(); for (;;) { let v; try { v = await this.evalJS(expr); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '')); await sleep(150); } }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

function args(argv) { const a = {}; for (let i = 0; i < argv.length; i++) { if (!argv[i].startsWith('--')) continue; const k = argv[i].slice(2); const n = argv[i + 1]; if (n && !n.startsWith('--')) { a[k] = n; i++; } else a[k] = true; } return a; }

async function resolveCdpWs(endpoint) {
  const base = endpoint.replace(/\/+$/, '');
  const t0 = Date.now();
  for (;;) {
    const list = await httpJson(base + '/json/list').catch(() => null);
    const pages = (list || []).filter((t) => t.type === 'page' && t.webSocketDebuggerUrl);
    const page = pages.find((t) => /^https?:\/\/(127\.0\.0\.1|localhost)[:/]/i.test(t.url || ''));
    if (page) return page.webSocketDebuggerUrl;
    if (Date.now() - t0 > 45000) throw new Error('CDP no local page');
    await sleep(700);
  }
}

const HELPERS = `(function(){
  var Hl = window.MemoriaCodeHighlight;
  function normText(s){ return String(s==null?'':s).replace(/\\s+/g,' ').trim(); }
  // 归一化"标签+class 序列"：忽略属性顺序/空白/文本，只留结构性 token
  function tagSeqFromHtml(html){
    var tpl=document.createElement('template'); tpl.innerHTML=String(html||'');
    var out=[];
    (function walk(nodes){
      for(var i=0;i<nodes.length;i++){
        var n=nodes[i];
        if(n.nodeType!==1) continue;
        var cls=Array.prototype.slice.call(n.classList||[]).sort().join('.');
        out.push(n.tagName.toLowerCase()+(cls?'.'+cls:''));
        walk(n.childNodes);
      }
    })(tpl.content.childNodes);
    return out;
  }
  function tagSeqFromCodeEl(codeEl){
    var out=[];
    (function walk(nodes){
      for(var i=0;i<nodes.length;i++){
        var n=nodes[i];
        if(n.nodeType!==1) continue;
        var cls=Array.prototype.slice.call(n.classList||[]).sort().join('.');
        out.push(n.tagName.toLowerCase()+(cls?'.'+cls:''));
        walk(n.childNodes);
      }
    })(codeEl.childNodes);
    return out;
  }
  function langOf(codeEl){
    var m=/(?:^|\\s)language-([^\\s]+)/.exec(String(codeEl.className||''));
    return m?m[1]:'';
  }
  function checkDoc(){
    var preview=document.getElementById('preview');
    var codes=preview?preview.querySelectorAll('pre.-code-block > code'):[];
    var rows=[]; var mismatch=0; var textMismatch=0; var tokenSpans=0;
    for(var i=0;i<codes.length;i++){
      var codeEl=codes[i];
      var text=codeEl.textContent||'';
      var lang=langOf(codeEl);
      var expectedHtml = (Hl&&typeof Hl.render==='function') ? Hl.render(text,lang) : null;
      var actualSeq = tagSeqFromCodeEl(codeEl);
      var expectedSeq = expectedHtml==null ? null : tagSeqFromHtml(expectedHtml);
      var eq = expectedSeq!==null && actualSeq.length===expectedSeq.length && actualSeq.every(function(v,j){return v===expectedSeq[j];});
      var tpl=document.createElement('template'); if(expectedHtml!=null) tpl.innerHTML=expectedHtml;
      var expectedText = normText(tpl.content.textContent);
      var textEq = normText(text)===expectedText;
      var spans = codeEl.querySelectorAll('span').length;
      tokenSpans += spans;
      if(!eq) mismatch++;
      if(!textEq) textMismatch++;
      rows.push({i:i,lang:lang,chars:text.length,spans:spans,expectedSpans:(expectedSeq||[]).filter(function(x){return x.indexOf('span')===0;}).length,eq:eq,textEq:textEq,actualSeq:actualSeq.slice(0,12),expectedSeq:(expectedSeq||[]).slice(0,12)});
    }
    return {codes:codes.length,tokenSpans:tokenSpans,mismatch:mismatch,textMismatch:textMismatch,rows:rows};
  }
  // 模拟"高亮未执行"：把 code 内容改回纯文本（等价于 P6a 修复前的 DOM 形态）
  function stripHighlight(){
    var codes=document.querySelectorAll('#preview pre.-code-block > code');
    for(var i=0;i<codes.length;i++){ codes[i].textContent = codes[i].textContent; }
    return codes.length;
  }
  function mermaidSanity(){
    var mm=document.querySelectorAll('#preview .-mermaid-container').length;
    var mmCode=document.querySelectorAll('#preview .-mermaid-container code.language-mermaid').length;
    var mmTok=document.querySelectorAll('#preview .-mermaid-container span[class^="-tk-"]').length;
    return {mermaidContainers:mm,residualMermaidCode:mmCode,mermaidHighlightSpans:mmTok};
  }
  window.__p6h={checkDoc:checkDoc,stripHighlight:stripHighlight,mermaidSanity:mermaidSanity,normText:normText,tagSeqFromHtml:tagSeqFromHtml};
  return {ok:true};
})()`;

async function openForcePreview(cdp, file) {
  await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
  await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, { label: 'open:' + file, timeout: 30000 });
  await sleep(400);
  if ((await cdp.evalJS('window.state.viewMode')) !== 'preview') {
    await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b)b.click();})()`).catch(() => { });
    await sleep(300);
  }
  await cdp.waitFor(`window.state.viewMode === 'preview'`, { label: 'preview:' + file, timeout: 15000 }).catch(() => { });
  await sleep(1200);   // mermaid/math 落定
}

async function main() {
  const a = args(process.argv.slice(2));
  const endpoint = typeof a.cdp === 'string' ? a.cdp : null;
  const kb = typeof a.kb === 'string' ? a.kb : null;
  const files = typeof a.files === 'string' ? a.files.split(',').map((s) => s.trim()).filter(Boolean) : [];
  if (!endpoint || !kb || !files.length) { process.stderr.write('用法: node check_code_highlight.mjs --cdp <endpoint> --kb <abs> --files a,b --out <json>\n'); return 2; }
  const out = { schema: 'memoria-p6a-code-highlight/v1', cdpEndpoint: endpoint, kb, files, startedAt: new Date().toISOString(), docs: {} };
  let cdp = null; let exitCode = 1;
  try {
    cdp = await CDP.connect(await resolveCdpWs(endpoint));
    await cdp.send('Runtime.enable');
    let ready = false;
    for (let i = 0; i < 5 && !ready; i++) {
      try { await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser && !!window.MemoriaCodeHighlight', { label: 'app', timeout: 90000 }); ready = true; }
      catch { try { await cdp.send('Page.reload', { ignoreCache: true }); } catch { } await sleep(3000); }
    }
    if (!ready) throw new Error('应用未就绪');
    await cdp.evalJS(HELPERS);
    for (const f of files) {
      try { await openForcePreview(cdp, f); out.docs[f] = await cdp.evalJS('window.__p6h.checkDoc()'); }
      catch (e) { out.docs[f] = { error: String((e && e.message) || e) }; }
    }

    // 判别力自证：找一个含代码块的文档
    const target = files.find((f) => out.docs[f] && out.docs[f].codes > 0) || null;
    out.discrimination = { target, red: null, green: null, ok: false };
    if (target) {
      await openForcePreview(cdp, target);
      const before = await cdp.evalJS('window.__p6h.checkDoc()');
      await cdp.evalJS('window.__p6h.stripHighlight()');
      const red = await cdp.evalJS('window.__p6h.checkDoc()');
      await cdp.evalJS('window.MemoriaApp.renderPreview(window.state.doc)');
      await sleep(1500);
      const green = await cdp.evalJS('window.__p6h.checkDoc()');
      out.discrimination = {
        target,
        baseline: { codes: before.codes, tokenSpans: before.tokenSpans, mismatch: before.mismatch },
        shortCircuit: { codes: red.codes, tokenSpans: red.tokenSpans, mismatch: red.mismatch, red: red.mismatch > 0 },
        restored: { codes: green.codes, tokenSpans: green.tokenSpans, mismatch: green.mismatch, textMismatch: green.textMismatch, green: green.mismatch === 0 && green.textMismatch === 0 },
        ok: red.mismatch > 0 && green.mismatch === 0 && green.textMismatch === 0,
      };
      out.mermaid = await cdp.evalJS('window.__p6h.mermaidSanity()');
    }

    const docsWithCode = Object.entries(out.docs).filter(([, v]) => v && typeof v.codes === 'number' && v.codes > 0);
    const totalCodes = docsWithCode.reduce((s, [, v]) => s + v.codes, 0);
    const totalSpans = docsWithCode.reduce((s, [, v]) => s + v.tokenSpans, 0);
    const totalMismatch = docsWithCode.reduce((s, [, v]) => s + v.mismatch, 0);
    const totalTextMismatch = docsWithCode.reduce((s, [, v]) => s + v.textMismatch, 0);
    out.totals = {
      docs: Object.keys(out.docs).length,
      docsWithCode: docsWithCode.length,
      codeBlocks: totalCodes,
      tokenSpans: totalSpans,
      mismatch: totalMismatch,
      textMismatch: totalTextMismatch,
    };
    out.ok = totalCodes > 0 && totalMismatch === 0 && totalTextMismatch === 0 && out.discrimination.ok === true
      && (!out.mermaid || (out.mermaid.residualMermaidCode === 0 && out.mermaid.mermaidHighlightSpans === 0));
    exitCode = out.ok ? 0 : 1;
  } catch (e) { out.error = String((e && e.stack) || e); out.ok = false; exitCode = 1; }
  finally {
    out.finishedAt = new Date().toISOString();
    if (cdp) cdp.close();
    const outPath = typeof a.out === 'string' ? a.out : null;
    if (outPath) { fs.mkdirSync(path.dirname(outPath), { recursive: true }); fs.writeFileSync(outPath, JSON.stringify(out, null, 2), 'utf8'); }
    process.stdout.write('__P6H__' + JSON.stringify({ ok: out.ok, out: outPath, error: out.error || null, totals: out.totals, discrimination: out.discrimination, mermaid: out.mermaid, docs: Object.fromEntries(Object.entries(out.docs).map(([k, v]) => [k, v && v.codes != null ? { codes: v.codes, tokenSpans: v.tokenSpans, mismatch: v.mismatch, textMismatch: v.textMismatch } : v])) }) + '\n');
    setTimeout(() => process.exit(exitCode), 500).unref();
  }
  return exitCode;
}
const code = await main();
process.exitCode = code;
