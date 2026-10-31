/**
 * task-63 0.4.7 矩阵门禁：窗口尺寸 × UI 缩放 × 字体
 *
 * 每个组合验 5 项：
 *   1. 打开 → 视口占位 = 0，视口内文本 == golden
 *   2. 滚动 50%/80% → 视口占位 = 0，文本正确
 *   3. 快速拖拽到底 → **视口空白持续时长 ≤100ms**（0.4.7 新指标）
 *   4. 高度漂移（滚 50%→底→回 50%）≤ 5 行
 *   5. 上跳 = 0
 *   附加：打开后 resize 再滚动（验证 _pvMetrics 失效时机缺陷）
 *
 * 用法:
 *   node text_gate_matrix.mjs <port> <out.json> <golden.json>
 */
import { writeFileSync, readFileSync, existsSync } from 'node:fs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 120000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr, awaitPromise = false) {
    const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise, userGesture: true });
    if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || ''));
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expr, timeoutMs = 60000) { const t0 = Date.now(); while (Date.now() - t0 < timeoutMs) { try { if (await this.ev(`!!(${expr})`)) return true; } catch (e) { /* */ } await sleep(150); } return false; }
  close() { try { this.ws.close(); } catch { /* */ } }
}

// ── 归一化（与 text_gate.mjs 保持一致）──
const MERMAID_RID_RE = /mermaid-[a-z0-9]{6,}/gi;
const ARROW_RID_RE = /\barrow-marker-[a-z0-9]{6,}/gi;
const MERMAID_PCT_RE = /\d+%适配/g;
function normText(s) {
  if (s == null) return '';
  let t = String(s);
  t = t.replace(/\u00a0/g, ' ');
  t = t.replace(/[\u200b\u200c\u200d\ufeff]/g, '');
  t = t.replace(MERMAID_RID_RE, 'mermaid-RID');
  t = t.replace(ARROW_RID_RE, 'arrow-marker-RID');
  t = t.replace(MERMAID_PCT_RE, '<PCT>%适配');
  t = t.replace(/\s+/g, ' ');
  return t.trim();
}

const port = Number(process.argv[2]);
const outPath = process.argv[3];
const goldenPath = process.argv[4];
if (!existsSync(goldenPath)) { console.error('golden 不存在: ' + goldenPath); process.exit(2); }
const golden = JSON.parse(readFileSync(goldenPath, 'utf8'));

let page = null;
for (let a = 0; a < 40; a++) {
  try { const l = await httpJson(`http://127.0.0.1:${port}/json/list`); page = (l || []).find(t => t.type === 'page' && /^https?:\/\//.test(t.url || '') && t.webSocketDebuggerUrl); if (page) break; } catch (e) { /* */ }
  await sleep(1000);
}
if (!page) { console.error('no page'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) { console.error('app not ready'); process.exit(2); }

// 页面内探针
const INSTALL = `(function(){
  if (window.__mx) return 1;
  var X = {}; window.__mx = X;
  X.norm = function(s){
    if (s == null) return '';
    var t = String(s);
    t = t.replace(/\\u00a0/g,' ').replace(/[\\u200b\\u200c\\u200d\\ufeff]/g,'');
    t = t.replace(/mermaid-[a-z0-9]{6,}/gi,'mermaid-RID');
    t = t.replace(/\\barrow-marker-[a-z0-9]{6,}/gi,'arrow-marker-RID');
    t = t.replace(/\\d+%适配/g,'<PCT>%适配');
    return t.replace(/\\s+/g,' ').trim();
  };
  X.pane = function(){ return document.getElementById('preview-pane'); };
  X.content = function(){ var pv=document.getElementById('preview'); return pv?(pv.querySelector('.-preview-content')||pv):null; };
  X.viewportStats = function(){
    var p=X.pane(), cc=X.content(); if(!p||!cc) return null;
    var pr=p.getBoundingClientRect();
    var ph=0, blocks=[];
    cc.querySelectorAll('.-src-block').forEach(function(el){
      var r=el.getBoundingClientRect();
      if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top) <= 2) return;
      var isPh = el.classList.contains('-pv-placeholder');
      if (isPh) ph++;
      blocks.push({ index: el.getAttribute('data--block-index'), srcLine: el.getAttribute('data--src-line'), isPh: isPh, text: X.norm(el.textContent||'') });
    });
    return { ph: ph, blocks: blocks, scrollTop: Math.round(p.scrollTop), scrollH: p.scrollHeight, clientH: p.clientHeight, paneW: p.clientWidth };
  };
  X.firstVisibleLine = function(){
    var p=X.pane(); if(!p) return null;
    var pr=p.getBoundingClientRect();
    var els=p.querySelectorAll('[data--src-line]');
    for (var i=0;i<els.length;i++){ var r=els[i].getBoundingClientRect(); if (Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) return +els[i].getAttribute('data--src-line'); }
    return null;
  };
  X.scrollTo = function(pct){ var p=X.pane(); if(!p) return -1; p.scrollTop=(p.scrollHeight-p.clientHeight)*pct; return p.scrollTop; };
  X.totalPh = function(){ var cc=X.content(); return cc?cc.querySelectorAll('.-pv-placeholder').length:-1; };
  // ★ 视口空白持续时长采样器：每 50ms 采一次 ph，记录连续 ph>0 的最长时长
  X.blankWatch = { on: false, maxBlank: 0, samples: [], startedAt: 0 };
  X.startBlankWatch = function(){
    var W = X.blankWatch;
    W.on = true; W.maxBlank = 0; W.samples = []; W.startedAt = performance.now();
    var blankStart = null;
    function tick(){
      if (!W.on) return;
      var st = X.viewportStats();
      var phv = st ? st.ph : -1;
      var now = performance.now();
      W.samples.push({ t: Math.round(now - W.startedAt), ph: phv });
      if (phv > 0) { if (blankStart === null) blankStart = now; }
      else { if (blankStart !== null) { var d = now - blankStart; if (d > W.maxBlank) W.maxBlank = d; blankStart = null; } }
      setTimeout(tick, 50);
    }
    tick();
  };
  X.stopBlankWatch = function(){
    var W = X.blankWatch;
    W.on = false;
    return { maxBlankMs: Math.round(W.maxBlank), sampleCount: W.samples.length,
             blankSamples: W.samples.filter(function(s){return s.ph>0;}).length,
             samples: W.samples.slice(0, 200) };
  };
  // 上跳采样：视口内块 top 相对上次的减小量最大值
  X.jumpWatch = { on: false, maxShrink: 0 };
  X.startJumpWatch = function(){
    var J = X.jumpWatch; J.on = true; J.maxShrink = 0;
    var prev = {};
    function tick(){
      if (!J.on) return;
      var p = X.pane(), cc = X.content();
      if (p && cc) {
        var pr = p.getBoundingClientRect();
        cc.querySelectorAll('.-src-block').forEach(function(el){
          var r = el.getBoundingClientRect();
          if (r.top < pr.top - 5 || r.top > pr.bottom + 5) return;
          var k = el.getAttribute('data--block-index');
          if (k in prev) { var sh = prev[k] - r.top; if (sh > J.maxShrink) J.maxShrink = sh; }
          prev[k] = r.top;
        });
      }
      setTimeout(tick, 50);
    }
    tick();
  };
  X.stopJumpWatch = function(){ var J=X.jumpWatch; J.on=false; return { maxShrink: Math.round(J.maxShrink*10)/10 }; };
  return 1;
})()`;
await cdp.ev(INSTALL);

async function openDoc(file) {
  await cdp.ev(`(function(){ try{ delete window.__MEMORIA_LAZY; }catch(e){} try{ localStorage.removeItem("memoria.perf.lazy"); }catch(e){} return 1; })()`);
  let opened = false;
  for (let attempt = 0; attempt < 8 && !opened; attempt++) {
    await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    try {
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 40000);
      let ok = 0;
      for (let s = 0; s < 3; s++) { await sleep(700); if (await cdp.ev('window.state.currentPath') === file) ok++; else break; }
      if (ok === 3) opened = true;
    } catch (e) { if (attempt === 7) throw e; }
    if (!opened) await sleep(1000);
  }
  if (!opened) throw new Error('openFile 不稳定');
  for (let i = 0; i < 10; i++) { if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break; await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1;})()`); await sleep(400); }
}

async function waitReadable(timeoutMs = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const st = await cdp.ev(`(function(){
      var p=document.getElementById('preview-pane'); if(!p) return null;
      var pr=p.getBoundingClientRect(); var ph=0, un=0;
      p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)ph++;});
      p.querySelectorAll('span.-math:not(:has(mjx-container))').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)un++;});
      return { ph: ph, un: un };
    })()`);
    if (st && st.ph === 0 && st.un === 0) return { ok: true, ms: Date.now() - t0 };
    await sleep(120);
  }
  return { ok: false, ms: Date.now() - t0 };
}

function diffViewport(vp, gBlocks) {
  const gm = new Map(gBlocks.map(b => [String(b.index), b]));
  const diffs = [];
  let matched = 0;
  for (const b of (vp.blocks || [])) {
    if (b.isPh) { diffs.push({ kind: 'ph-in-viewport', index: b.index }); continue; }
    const g = gm.get(String(b.index));
    if (!g) { diffs.push({ kind: 'extra', index: b.index }); continue; }
    if (normText(g.text) === normText(b.text)) { matched++; continue; }
    const a = normText(g.text), c = normText(b.text);
    let i = 0; while (i < a.length && i < c.length && a[i] === c[i]) i++;
    diffs.push({ kind: 'text-diff', index: b.index, at: i, golden: a.slice(Math.max(0, i - 15), i + 50), actual: c.slice(Math.max(0, i - 15), i + 50) });
  }
  return { matched, diffs };
}

// 代表性组合
const COMBOS = [
  { name: '1280x720@100%', width: 1280, height: 720, scale: 1.0 },
  { name: '1024x600@80%', width: 1024, height: 600, scale: 0.8 },
  { name: '1920x1080@150%', width: 1920, height: 1080, scale: 1.5 },
];

const DOCS = process.argv.slice(5);
const results = { schema: 'memoria-matrix-gate/v1', head: '317876e9', combos: [] };

for (const combo of COMBOS) {
  console.log('=== 组合 ' + combo.name + ' ===');
  // 应用视口覆盖
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: combo.width, height: combo.height,
    deviceScaleFactor: combo.scale, mobile: false,
  }).catch(e => console.log('  ⚠️ setDeviceMetricsOverride 失败: ' + e.message));
  await sleep(800);

  const comboRes = { combo: combo.name, docs: {} };

  for (const file of DOCS) {
    const G = golden.documents[file];
    if (!G) { console.log('  ' + file + ' ⚠️ golden 缺失'); continue; }
    console.log('  --- ' + file + ' ---');
    const dRes = { file, steps: [] };
    try {
      await openDoc(file);
      await waitReadable(12000);

      // 1 打开
      const vp0 = await cdp.ev('window.__mx.viewportStats()');
      const d0 = diffViewport(vp0, G.blocks);
      dRes.steps.push({ step: 'open', diffs: d0.diffs.length, matched: d0.matched, ph: vp0 && vp0.ph,
        viewportBlocks: vp0 && vp0.blocks ? vp0.blocks.length : 0, paneW: vp0 && vp0.paneW, clientH: vp0 && vp0.clientH });
      console.log('    打开: diffs=' + d0.diffs.length + ' ph=' + (vp0 && vp0.ph) + ' 视口块=' + (vp0 && vp0.blocks.length) + ' paneW=' + (vp0 && vp0.paneW));

      // 2 滚动 50% / 80%
      for (const pct of [0.5, 0.8]) {
        await cdp.ev(`window.__mx.scrollTo(${pct})`);
        await waitReadable(10000);
        const vp = await cdp.ev('window.__mx.viewportStats()');
        const d = diffViewport(vp, G.blocks);
        dRes.steps.push({ step: 'scroll-' + pct, diffs: d.diffs.length, matched: d.matched, ph: vp && vp.ph });
        console.log('    滚 ' + (pct * 100) + '%: diffs=' + d.diffs.length + ' ph=' + (vp && vp.ph));
      }

      // 3 快速拖拽到底 → 视口空白持续时长
      await cdp.ev('window.__mx.scrollTo(0.2)');
      await sleep(600);
      await cdp.ev('window.__mx.startBlankWatch()');
      await cdp.ev('window.__mx.startJumpWatch()');
      for (let s = 1; s <= 10; s++) {
        await cdp.ev(`(function(){ var p=document.getElementById('preview-pane'); p.scrollTop=(p.scrollHeight-p.clientHeight)*${(0.2 + s * 0.08).toFixed(3)}; return 1; })()`);
        await sleep(16);
      }
      await sleep(3000);
      const blank = await cdp.ev('window.__mx.stopBlankWatch()');
      const jump = await cdp.ev('window.__mx.stopJumpWatch()');
      dRes.steps.push({ step: 'drag-blank', maxBlankMs: blank && blank.maxBlankMs, samples: blank && blank.sampleCount, blankSamples: blank && blank.blankSamples });
      dRes.steps.push({ step: 'drag-jump', maxShrink: jump && jump.maxShrink });
      console.log('    ★ 拖拽: 视口空白最长=' + (blank && blank.maxBlankMs) + 'ms (采样' + (blank && blank.sampleCount) + '次, 空白' + (blank && blank.blankSamples) + '次) 上跳=' + (jump && jump.maxShrink) + 'px');

      // 4 高度漂移
      await cdp.ev('window.__mx.scrollTo(0)');
      await sleep(900);
      await cdp.ev('window.__mx.scrollTo(0.5)');
      await sleep(1200);
      const A = await cdp.ev('window.__mx.firstVisibleLine()');
      await cdp.ev('window.__mx.scrollTo(1.0)');
      await sleep(1500);
      await cdp.ev('window.__mx.scrollTo(0.5)');
      await sleep(1500);
      const B = await cdp.ev('window.__mx.firstVisibleLine()');
      const drift = (A != null && B != null) ? Math.abs(A - B) : null;
      dRes.steps.push({ step: 'drift', A, B, drift });
      console.log('    漂移: A=' + A + ' B=' + B + ' |Δ|=' + drift + ' 行');

      // 5 打开后 resize → 再滚动（验证 _pvMetrics 失效缺陷）
      await cdp.send('Emulation.setDeviceMetricsOverride', {
        width: Math.round(combo.width * 0.75), height: Math.round(combo.height * 0.75),
        deviceScaleFactor: combo.scale, mobile: false,
      }).catch(() => {});
      await sleep(1200);
      await cdp.ev('window.__mx.scrollTo(0)');
      await sleep(600);
      await cdp.ev('window.__mx.startJumpWatch()');
      await cdp.ev('window.__mx.scrollTo(0.6)');
      await sleep(2500);
      const jumpAfterResize = await cdp.ev('window.__mx.stopJumpWatch()');
      const vpAfter = await cdp.ev('window.__mx.viewportStats()');
      dRes.steps.push({ step: 'resize-then-scroll', maxShrink: jumpAfterResize && jumpAfterResize.maxShrink, ph: vpAfter && vpAfter.ph, paneW: vpAfter && vpAfter.paneW });
      console.log('    ★ resize 后滚动: 上跳=' + (jumpAfterResize && jumpAfterResize.maxShrink) + 'px ph=' + (vpAfter && vpAfter.ph) + ' paneW=' + (vpAfter && vpAfter.paneW));

      // 恢复组合视口
      await cdp.send('Emulation.setDeviceMetricsOverride', {
        width: combo.width, height: combo.height, deviceScaleFactor: combo.scale, mobile: false,
      }).catch(() => {});
      await sleep(600);

      const totalDiffs = dRes.steps.reduce((s, x) => s + (x.diffs || 0) + ((x.drift != null && x.drift > 5) ? 1 : 0) + ((x.maxShrink || 0) > 0 ? 1 : 0) + ((x.maxBlankMs || 0) > 100 ? 1 : 0), 0);
      dRes.totalIssues = totalDiffs;
      console.log('    => 问题数: ' + totalDiffs);
    } catch (e) {
      dRes.error = String(e && e.message || e).slice(0, 200);
      console.log('    ERROR: ' + dRes.error);
    }
    comboRes.docs[file] = dRes;
  }
  results.combos.push(comboRes);
}

// 清理视口覆盖
await cdp.send('Emulation.clearDeviceMetricsOverride').catch(() => {});
writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log('');
console.log('=== 汇总 ===');
let total = 0;
for (const c of results.combos) {
  for (const [f, d] of Object.entries(c.docs)) {
    total += (d.totalIssues || 0) || (d.error ? 1 : 0);
    console.log('  ' + c.combo + ' / ' + f.slice(-20) + ': issues=' + (d.totalIssues != null ? d.totalIssues : 'ERROR'));
  }
}
console.log('  合计问题: ' + total);
console.log('__MATRIX__' + JSON.stringify({ totalIssues: total, combos: results.combos.length }));
cdp.close();
setTimeout(() => process.exit(total === 0 ? 0 : 1), 300).unref();
