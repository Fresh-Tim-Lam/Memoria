/**
 * task-63 惰性物化门禁双组验证
 *
 * 组1（forceFull）：window.__MEMORIA_LAZY = false → 打开 13 篇 → 原 13 项计数
 *                  期望 13/13（证明"重构没改渲染语义"）
 * 组2（lazyMaterializeAll）：默认惰性 → 打开 → await __MEMORIA_MATERIALIZE_ALL() → 计数
 *                  期望 13/13 + placeholders===0 + 块数===astCount
 *
 * 用法: node perf_lazy_gate.mjs <port> <out.json> <group>
 *   group = full | lazy
 */
import { writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { PROBE_SOURCE, fidelitySignature } from './fidelity.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 180000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  // awaitPromise: true ⇒ 可以等页面内 Promise（MATERIALIZE_ALL 需要）
  async ev(expr, awaitPromise = false) {
    const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise, userGesture: true });
    if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || (r.exceptionDetails.exception && r.exceptionDetails.exception.description) || ''));
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expr, timeoutMs = 60000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      try { if (await this.ev(`!!(${expr})`, false)) return true; } catch (e) { /* */ }
      await sleep(200);
    }
    return false;
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2]);
const outPath = process.argv[3];
const GROUP = process.argv[4] || 'full';

const FILES = [
  'scale/scale-5k.md', 'scale/scale-1k.md', 'scale/scale-10k.md',
  'corpus/01-ime-zh.md', 'corpus/02-inline-edges.md', 'corpus/03-block-boundaries.md',
  'corpus/04-non-editable.md', 'corpus/05-images.md', 'corpus/06-links-and-kp.md',
  'corpus/07-extremes.md', 'README.md', 'docs/error_log_format.md', 'docs/ref/ppt/ocr.md',
];

let page = null;
for (let a = 0; a < 40; a++) {
  try {
    const l = await httpJson(`http://127.0.0.1:${port}/json/list`);
    page = (l || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || '') && t.webSocketDebuggerUrl);
    if (page) break;
  } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }

const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) {
  console.error('app not ready'); process.exit(2);
}

// 注入探针
await cdp.ev('window.__fidelity = ' + PROBE_SOURCE, false);
console.log('[gate] 探针已注入, group=' + GROUP);

// 组1：强制全量
if (GROUP === 'full') {
  await cdp.ev('window.__MEMORIA_LAZY = false');
  console.log('[gate] __MEMORIA_LAZY = false（强制全量）');
} else {
  // 组2：默认惰性（清掉任何残留钩子）
  await cdp.ev('(function(){ try { delete window.__MEMORIA_LAZY; } catch(e) { window.__MEMORIA_LAZY = undefined; } return 1; })()');
  await cdp.ev('(function(){ try { localStorage.removeItem("memoria.perf.lazy"); } catch(e){} return 1; })()');
  console.log('[gate] 默认惰性（已清除钩子与 localStorage）');
}

async function openDoc(file) {
  let opened = false;
  for (let attempt = 0; attempt < 4 && !opened; attempt++) {
    await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    try {
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 30000);
      await sleep(700);
      if (await cdp.ev('window.state.currentPath') === file) opened = true;
    } catch (e) { if (attempt === 3) throw e; }
  }
  if (!opened) throw new Error('openFile 不稳定: ' + file);
  // 切预览
  for (let i = 0; i < 8; i++) {
    const mode = await cdp.ev('(window.state||{}).viewMode || null');
    if (mode === 'preview') break;
    await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
    await sleep(400);
  }
}

const result = { schema: 'memoria-lazy-gate/v1', head: 'ca20e217', group: GROUP, documents: {} };

for (const file of FILES) {
  try {
    await openDoc(file);

    // 组2：物化全文
    let matResult = null;
    if (GROUP === 'lazy') {
      const t0 = Date.now();
      // awaitPromise: true ⇒ 等 Promise resolve，返回 made.length
      matResult = await cdp.ev('window.__MEMORIA_MATERIALIZE_ALL()', true);
      const matMs = Date.now() - t0;
      console.log('    [materializeAll] made=' + matResult + ' ms=' + matMs);
      await sleep(1200);
    }

    // 等渲染就绪
    let ready = null;
    try {
      ready = await cdp.ev(`window.__fidelity.waitForRenderReady(${JSON.stringify({ which: 'both', minFrames: 3, timeoutMs: 60000, awaitAppPending: true })})`, true);
    } catch (e) {
      ready = { status: 'failed', reason: String(e && e.message || e) };
    }

    // 采集状态断言
    const stateCheck = await cdp.ev(`(function(){
      var pv = document.getElementById('preview');
      var cc = pv ? (pv.querySelector('.-preview-content') || pv) : null;
      var blocks = pv ? pv.querySelectorAll('.-src-block').length : 0;
      var ph = cc ? cc.querySelectorAll('.-pv-placeholder').length : -1;
      var doc = window.state.doc;
      var mjx = pv ? pv.querySelectorAll('mjx-container').length : 0;
      // 触发 fidelity 快照
      var r = window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body));
      return {
        blocks: blocks, placeholders: ph,
        astCount: doc && doc.blocks ? doc.blocks.length : -1,
        mjx: mjx,
        sig: r && r.signatureNorm ? r.signatureNorm : null,
        ok: r ? r.ok : null
      };
    })()`, false);

    const sig = stateCheck && stateCheck.sig;
    const jsonOf = typeof sig === 'string' ? sig : JSON.stringify(sig || {});
    const sigHash = fidelitySignature(jsonOf);

    result.documents[file] = {
      status: 'ran',
      renderReady: ready && ready.status,
      materialized: matResult,
      blocks: stateCheck && stateCheck.blocks,
      placeholders: stateCheck && stateCheck.placeholders,
      astCount: stateCheck && stateCheck.astCount,
      mjx: stateCheck && stateCheck.mjx,
      fidelityOk: stateCheck && stateCheck.ok,
      signatureNorm: jsonOf,
      signature: sigHash,
    };
    console.log('  ' + file + ' | blocks=' + (stateCheck && stateCheck.blocks) + ' ph=' + (stateCheck && stateCheck.placeholders) +
      ' ast=' + (stateCheck && stateCheck.astCount) + ' mjx=' + (stateCheck && stateCheck.mjx) + ' ready=' + (ready && ready.status));
  } catch (e) {
    result.documents[file] = { status: 'error', error: String(e && e.message || e) };
    console.log('  ' + file + ' ❌ ' + String(e && e.message || e).slice(0, 100));
  }
}

writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
console.log('[gate] 落盘: ' + outPath);
cdp.close();
setTimeout(() => process.exit(0), 300).unref();
