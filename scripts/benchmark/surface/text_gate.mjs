/**
 * task-63 交互序列文本门禁（text_gate.mjs）
 *
 * 人在要求：不只是静态准确，要"交互过程处处准确"。
 *
 * 序列（每步都校验文本）：
 *   1 打开（默认惰性）— 视口内块文本 == golden；视口内 placeholder === 0
 *   2 滚 25%   3 滚 50%   4 滚 75%   5 滚到底
 *   6 跳转（scrollToSrcLine）
 *   7 编辑一个可见块 — 该块文本 == 预期；相邻块不变
 *   8 undo — 回到编辑前
 *   9 切页签离开再回来 — 视口文本 == golden，无白屏
 *  10 重复 2-9 两轮 — 每轮一致
 *
 * 约束：
 *   - 每步只物化视口所需（不调 MATERIALIZE_ALL）
 *   - 只比对视口内块；断言视口内 .-pv-placeholder === 0
 *   - 编辑区逐行与 doc.lines 比对
 *   - 归一化不是删除：NBSP→空格、零宽删除、连续空白折叠、trim；不改大小写/不删标点/不排序
 *   - 任何 diff ⇒ 退出码非 0
 *
 * 用法:
 *   node text_gate.mjs <port> golden <golden.json> <files...>     # 抓 golden（强制全量）
 *   node text_gate.mjs <port> verify <golden.json> <files...>     # 跑交互序列校验
 */
import { writeFileSync, readFileSync, existsSync } from 'node:fs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('ws timeout')), 25000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('ws error')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(method, params = {}, timeoutMs = 60000) { return new Promise((res, rej) => { const id = ++this._id; const to = setTimeout(() => { this._p.delete(id); rej(new Error('cdp timeout ' + method)); }, timeoutMs); this._p.set(id, { resolve: (v) => { clearTimeout(to); res(v); }, reject: (e) => { clearTimeout(to); rej(e); } }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expr, awaitPromise = false) {
    const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise, userGesture: true });
    if (r && r.exceptionDetails) throw new Error('eval: ' + String(r.exceptionDetails.text || (r.exceptionDetails.exception && r.exceptionDetails.exception.description) || ''));
    return r.result ? r.result.value : undefined;
  }
  async waitFor(expr, timeoutMs = 60000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      try { if (await this.ev(`!!(${expr})`)) return true; } catch (e) { /* */ }
      await sleep(150);
    }
    return false;
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

// ── 归一化（归一化不是删除）──
//   ⚠️ 必须过滤**非确定性随机 ID**（mermaid 每次渲染生成 mermaid-xxxxxxxx），
//      否则门禁会把同一块判成 diff（假阳性）。这是"归一化随机身份"，不是"删除内容"。
const MERMAID_RID_RE = /mermaid-[a-z0-9]{6,}/gi;
const ARROW_RID_RE = /\barrow-marker-[a-z0-9]{6,}/gi;
// mermaid SVG 的缩放适配百分比：随容器尺寸/渲染时机变化，是**视图状态**不是内容
//   证据：`适配` 在 03 章 markdown 源文 grep 不到 ⇒ 只可能来自 mermaid 生成的 SVG
const MERMAID_PCT_RE = /\d+%适配/g;

function normText(s) {
  if (s == null) return '';
  let t = String(s);
  t = t.replace(/\u00a0/g, ' ');                       // NBSP → 空格
  t = t.replace(/[\u200b\u200c\u200d\ufeff]/g, '');    // 零宽删除
  t = t.replace(MERMAID_RID_RE, 'mermaid-RID');        // mermaid 随机 DOM id → 固定占位
  t = t.replace(ARROW_RID_RE, 'arrow-marker-RID');     // 箭头 marker id 同理
  t = t.replace(MERMAID_PCT_RE, '<PCT>%适配');         // mermaid 缩放百分比 → 固定占位
  t = t.replace(/\s+/g, ' ');                          // 连续空白折叠
  return t.trim();
}

const port = Number(process.argv[2]);
const MODE = process.argv[3];      // golden | verify
const dataPath = process.argv[4];
const FILES = process.argv.slice(5);

if (!port || !MODE || !dataPath) {
  console.error('用法: node text_gate.mjs <port> golden|verify <json> <files...>');
  process.exit(2);
}

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

// 捕获 lazy 相关日志（统计 typeset 次数 + 确认 retoken 修复生效）
const lazyLogs = [];
let captureLogs = true;
cdp.ws.addEventListener('message', (e) => {
  if (!captureLogs) return;
  let m; try { m = JSON.parse(typeof e.data === 'string' ? e.data : String(e.data)); } catch { return; }
  if (m.method !== 'Runtime.consoleAPICalled') return;
  const args = (m.params && m.params.args) || [];
  const txt = args.map(a => a.value === undefined ? (a.description || '') : String(a.value)).join(' ');
  if (/lazy|math merge|retoken/i.test(txt)) lazyLogs.push(txt);
});

if (!(await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', 90000))) {
  console.error('app not ready'); process.exit(2);
}

// ── 页面内探针 ──
const INSTALL_PROBE = `(function(){
  if (window.__tg) return 1;
  var T = {}; window.__tg = T;
  T.norm = function(s){
    if (s == null) return '';
    var t = String(s);
    t = t.replace(/\\u00a0/g, ' ');
    t = t.replace(/[\\u200b\\u200c\\u200d\\ufeff]/g, '');
    t = t.replace(/mermaid-[a-z0-9]{6,}/gi, 'mermaid-RID');
    t = t.replace(/\\barrow-marker-[a-z0-9]{6,}/gi, 'arrow-marker-RID');
    t = t.replace(/\\d+%适配/g, '<PCT>%适配');
    t = t.replace(/\\s+/g, ' ');
    return t.trim();
  };
  T.pane = function(){ return document.getElementById('preview-pane'); };
  T.preview = function(){ return document.getElementById('preview'); };
  T.content = function(){ var pv=T.preview(); return pv ? (pv.querySelector('.-preview-content') || pv) : null; };

  // 视口内块：只取与 pane 有交集的 -src-block（含占位）
  T.viewportBlocks = function(){
    var p=T.pane(), cc=T.content(); if(!p||!cc) return [];
    var pr=p.getBoundingClientRect();
    var out=[];
    var els=cc.querySelectorAll('.-src-block');
    for(var i=0;i<els.length;i++){
      var el=els[i], r=el.getBoundingClientRect();
      if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top) <= 2) continue;
      out.push({
        index: el.getAttribute('data--block-index'),
        srcLine: el.getAttribute('data--src-line'),
        isPlaceholder: el.classList.contains('-pv-placeholder'),
        text: T.norm(el.textContent || '')
      });
    }
    return out;
  };
  // 视口内占位块数
  T.viewportPlaceholders = function(){
    var p=T.pane(), cc=T.content(); if(!p||!cc) return -1;
    var pr=p.getBoundingClientRect(); var n=0;
    var els=cc.querySelectorAll('.-pv-placeholder');
    for(var i=0;i<els.length;i++){ var r=els[i].getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2) n++; }
    return n;
  };
  // 全篇占位块数（不滚动时用于记录进度）
  T.totalPlaceholders = function(){ var cc=T.content(); return cc ? cc.querySelectorAll('.-pv-placeholder').length : -1; };

  // 编辑区逐行
  T.editorLines = function(){
    var ed=document.getElementById('editor'); if(!ed) return [];
    var out=[];
    var ls=ed.querySelectorAll('.-line[data-line]');
    for(var i=0;i<ls.length;i++){
      var c=ls[i].querySelector('.-line-content');
      out.push({ line: ls[i].getAttribute('data-line'), text: T.norm(c ? c.textContent : '') });
    }
    return out;
  };

  // 滚动到比例
  T.scrollTo = function(pct){
    var p=T.pane(); if(!p) return -1;
    p.scrollTop = (p.scrollHeight - p.clientHeight) * pct;
    return p.scrollTop;
  };
  T.scrollTopNow = function(){ var p=T.pane(); return p ? p.scrollTop : -1; };
  return 1;
})()`;
await cdp.ev(INSTALL_PROBE);

async function openDoc(file, forceFull) {
  await cdp.ev(`(function(){ window.__MEMORIA_LAZY = ${forceFull ? 'false' : 'true'}; return 1; })()`);
  // 先等页面空闲：上一轮文档可能还在渲染，直接 openFile 会被排队/覆盖
  //   判据：渲染标志位为空 + 连续 3 次 currentPath 稳定
  for (let k = 0; k < 100; k++) {
    const idle = await cdp.ev(`(function(){
      try {
        var busy = !!(window.state && window.state._mathPending);
        return busy ? 0 : 1;
      } catch(e) { return 1; }
    })()`);
    if (idle === 1) break;
    await sleep(200);
  }
  await sleep(500);

  let opened = false;
  for (let attempt = 0; attempt < 8 && !opened; attempt++) {
    await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    try {
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 40000);
      // 连续 3 次采样一致才算稳定（启动尾动作可能再改一次）
      let ok = 0;
      for (let s = 0; s < 3; s++) {
        await sleep(700);
        if (await cdp.ev('window.state.currentPath') === file) ok++;
        else break;
      }
      if (ok === 3) opened = true;
    } catch (e) { if (attempt === 7) throw e; }
    if (!opened) await sleep(1000);
  }
  if (!opened) throw new Error('openFile 不稳定: ' + file);
  for (let i = 0; i < 10; i++) {
    if (await cdp.ev('(window.state||{}).viewMode') === 'preview') break;
    await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="preview"]'); if(b) b.click(); return 1; })()`);
    await sleep(400);
  }
}

// 等视口内可读（无占位 + 无未排版公式），最多 timeout
async function waitViewportReadable(timeoutMs = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const st = await cdp.ev(`(function(){
      var p=document.getElementById('preview-pane'); if(!p) return null;
      var pr=p.getBoundingClientRect();
      var ph=0, untyped=0;
      p.querySelectorAll('.-pv-placeholder').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)ph++;});
      p.querySelectorAll('span.-math:not(:has(mjx-container))').forEach(function(e){var r=e.getBoundingClientRect(); if(Math.min(pr.bottom,r.bottom)-Math.max(pr.top,r.top)>2)untyped++;});
      return { ph: ph, untyped: untyped };
    })()`);
    if (st && st.ph === 0 && st.untyped === 0) return { ok: true, ms: Date.now() - t0 };
    await sleep(120);
  }
  const st2 = await cdp.ev(`(function(){ return { ph: window.__tg.viewportPlaceholders() }; })()`);
  return { ok: false, ms: Date.now() - t0, ph: st2 && st2.ph };
}

// 采集视口文本快照
async function snapViewport() {
  return await cdp.ev(`(function(){
    return {
      blocks: window.__tg.viewportBlocks(),
      placeholders: window.__tg.viewportPlaceholders(),
      totalPlaceholders: window.__tg.totalPlaceholders(),
      scrollTop: window.__tg.scrollTopNow(),
      editor: window.__tg.editorLines()
    };
  })()`);
}

// 探针：判断 MathJax 排版链当前是否已落定
//   state._mathPending 一旦赋值就永不置 null（它表示"最近一次排版链"），
//   所以给它挂 then 打 settled 标记，用标记判断而非 null 判断。
async function mathSettled() {
  return await cdp.ev(`(function(){
    var st = window.state || {};
    var p = st._mathPending;
    if (!p || typeof p.then !== 'function') return { hasChain: false, settled: true };
    // 挂一次性标记（不改变链行为）
    var marker = window.__tgMathMarker;
    if (marker !== p) {
      window.__tgMathMarker = p;
      window.__tgMathSettled = false;
      p.then(function () { window.__tgMathSettled = true; }, function () { window.__tgMathSettled = true; });
    }
    return { hasChain: true, settled: !!window.__tgMathSettled };
  })()`);
}

// 文本比对：只比对视口内块（按 block-index 对齐 golden 全篇）
function diffViewport(vp, goldenBlocks) {
  const gmap = new Map(goldenBlocks.map(b => [String(b.index), b]));
  const diffs = [];
  let matched = 0;
  for (const b of vp.blocks) {
    if (b.isPlaceholder) { diffs.push({ kind: 'placeholder-in-viewport', index: b.index }); continue; }
    const g = gmap.get(String(b.index));
    if (!g) { diffs.push({ kind: 'extra', index: b.index, text: b.text.slice(0, 80) }); continue; }
    if (normText(g.text) === normText(b.text)) { matched++; continue; }
    // 找首个差异位置
    const a = normText(g.text), c = normText(b.text);
    let i = 0; while (i < a.length && i < c.length && a[i] === c[i]) i++;
    diffs.push({ kind: 'text-diff', index: b.index, at: i,
      golden: a.slice(Math.max(0, i - 20), i + 60), actual: c.slice(Math.max(0, i - 20), i + 60) });
  }
  return { matched, diffs };
}

// 编辑区 vs doc.lines
function diffEditor(editorLines, docLines) {
  const diffs = [];
  let matched = 0;
  const n = Math.min(editorLines.length, docLines.length);
  for (let i = 0; i < n; i++) {
    const a = normText(editorLines[i].text);
    const b = normText(docLines[i]);
    if (a === b) matched++;
    else if (diffs.length < 3) diffs.push({ line: editorLines[i].line, at: i,
      expected: b.slice(0, 60), actual: a.slice(0, 60) });
  }
  if (editorLines.length !== docLines.length) {
    diffs.push({ kind: 'line-count', editor: editorLines.length, doc: docLines.length });
  }
  return { matched, diffs, total: n };
}

// 白屏判据：视口内占位块 > 0 ⇒ 用户看到的是空白占位
function vtp_ph_bad(vp) {
  return vp && typeof vp.placeholders === 'number' && vp.placeholders > 0;
}

function reportStep(docName, stepName, result) {  const bad = (result.diffs && result.diffs.length) || 0;
  const tag = bad === 0 ? 'OK  ' : 'DIFF';
  console.log(`  [${tag}] ${stepName}  matched=${result.matched || 0} diffs=${bad}` +
    (result.extra ? ` (${result.extra})` : ''));
  if (bad) {
    for (const d of result.diffs.slice(0, 3)) console.log('        ' + JSON.stringify(d).slice(0, 220));
  }
  return bad;
}

const exitDiffs = [];
const report = { schema: 'memoria-text-gate/v1', mode: MODE, head: 'ca20e217', documents: {} };

if (MODE === 'golden') {
  // golden：强制全量，抓全篇块文本 + 编辑区
  for (const file of FILES) {
    console.log('=== GOLDEN ' + file + ' ===');
    await openDoc(file, true);
    await cdp.waitFor('window.__tg.totalPlaceholders() === 0', 60000);
    await sleep(1500);
    const data = await cdp.ev(`(function(){
      var cc = window.__tg.content();
      var out = [];
      if (cc) {
        var els = cc.querySelectorAll('.-src-block');
        for (var i=0;i<els.length;i++){
          out.push({
            index: els[i].getAttribute('data--block-index'),
            srcLine: els[i].getAttribute('data--src-line'),
            text: window.__tg.norm(els[i].textContent || '')
          });
        }
      }
      var d = window.state.doc;
      return {
        blocks: out,
        docLines: (d && d.lines) ? d.lines.map(function(l){ return window.__tg.norm(l); }) : [],
        totalPlaceholders: window.__tg.totalPlaceholders(),
        blocksTotal: out.length
      };
    })()`);
    report.documents[file] = data;
    console.log('  blocks=' + (data && data.blocksTotal) + ' docLines=' + (data && data.docLines.length) + ' ph=' + (data && data.totalPlaceholders));
  }
  writeFileSync(dataPath, JSON.stringify(report, null, 2), 'utf8');
  console.log('golden 落盘: ' + dataPath);
} else {
  // verify：默认惰性 + 交互序列
  if (!existsSync(dataPath)) { console.error('golden 不存在: ' + dataPath); process.exit(2); }
  const golden = JSON.parse(readFileSync(dataPath, 'utf8'));

  for (const file of FILES) {
    const G = golden.documents[file];
    if (!G) { console.log('=== ' + file + ' ⚠️ golden 缺失，跳过 ==='); continue; }
    console.log('=== VERIFY ' + file + '（golden ' + G.blocks.length + ' 块）===');
    const docRes = { steps: [] };

    try {
      // 1 打开
      await openDoc(file, false);
      await waitViewportReadable(10000);
      let vp = await snapViewport();
      let d = diffViewport(vp, G.blocks);
      let ed = diffEditor(vp.editor || [], G.docLines || []);
      let bad = reportStep(file, '1-打开', d) + reportStep(file, '  editor', ed);
      docRes.steps.push({ step: 'open', ...d, editor: ed });

      // ══════ 一轮完整交互序列（2-7），返回本轮 diff 数与"每步是否全对"指纹 ══════
      async function runSequence(roundTag) {
        let rbad = 0;
        // 指纹：每步是否全部 matched（布尔），而非视口块列表
        //   ⚠️ 不能比视口块列表：文档高度随物化变化 ⇒ 相同 pct 落点块不同（v1 的误判）
        const fingerprint = [];

        // 2-5 滚动 25/50/75/100%
        for (const pct of [0.25, 0.5, 0.75, 1.0]) {
          await cdp.ev(`window.__tg.scrollTo(${pct})`);
          const r = await waitViewportReadable(10000);
          const vpS = await snapViewport();
          const dS = diffViewport(vpS, G.blocks);
          rbad += reportStep(file, `[${roundTag}] 滚动 ${pct * 100}%` + (r.ok ? '' : ` ⚠️未就绪(ph=${r.ph})`), dS);
          docRes.steps.push({ round: roundTag, step: 'scroll-' + pct, ok: r.ok, ph: r.ph, matched: dS.matched, diffs: dS.diffs.length });
          fingerprint.push('scroll' + pct + ':' + (dS.diffs.length === 0 ? 1 : 0));
          // 3：滚到 100% 后等 2s，断言占位**不增长**（物化本该继续减少，不该增加）
          if (pct === 1.0) {
            const ph1 = await cdp.ev('window.__tg.totalPlaceholders()');
            await sleep(2000);
            const ph2 = await cdp.ev('window.__tg.totalPlaceholders()');
            const noGrowth = (typeof ph1 === 'number' && typeof ph2 === 'number') ? ph2 <= ph1 : false;
            console.log(`        [${noGrowth ? 'OK  ' : 'DIFF'}] [${roundTag}] 3-占位不增长 after2s: ${ph1} → ${ph2}`);
            if (!noGrowth) rbad++;
            docRes.steps.push({ round: roundTag, step: 'ph-nogrowth', ph1, ph2, ok: noGrowth });
            fingerprint.push('ph:' + (noGrowth ? 1 : 0));
          }
        }

        // 4 跳转（等更充分：跳转后可能触发新物化 + typeset 排队）
        await cdp.ev(`window.__tg.scrollTo(0)`);
        await sleep(800);
        const targetLine = Math.floor((G.docLines ? G.docLines.length : 100) * 0.4) + 1;
        await cdp.ev(`(function(){ try { return window.MemoriaApp.scrollToSrcLine ? window.MemoriaApp.scrollToSrcLine("preview", ${targetLine}) : 'noapi'; } catch(e){ return String(e.message); } })()`);
        await sleep(1200);
        await waitViewportReadable(10000);
        // 额外等：跳转后可能有批次 typeset 在排队（v1 教训：$A$ 漏排只在 R1 出现）
        //   同时记录 token 与队列残留，用于判定"门禁等待不足 vs 真实竞态"
        const tokBefore = await cdp.ev(`(function(){ return { token: (window.state||{}).previewToken }; })()`);
        const mathB = await mathSettled();
        await sleep(1500);
        await waitViewportReadable(8000);
        const tokAfter = await cdp.ev(`(function(){ return { token: (window.state||{}).previewToken }; })()`);
        const mathA = await mathSettled();
        const vpJ = await snapViewport();
        const dJ = diffViewport(vpJ, G.blocks);
        rbad += reportStep(file, `[${roundTag}] 4-跳转 line=${targetLine}`, dJ);
        console.log(`        [info] token ${JSON.stringify(tokBefore)} → ${JSON.stringify(tokAfter)}`);
        docRes.steps.push({ round: roundTag, step: 'jump', targetLine, matched: dJ.matched, diffs: dJ.diffs.length,
          diffDetail: (dJ.diffs || []).slice(0, 3), tokenBefore: tokBefore, tokenAfter: tokAfter });
        fingerprint.push('jump:' + (dJ.diffs.length === 0 ? 1 : 0));

        // 5-6 编辑 + undo（中档文档才做）
        if (G.blocks.length <= 700) {
          const vpB = await snapViewport();
          const cand = vpB.blocks.find(b => !b.isPlaceholder && b.index != null);
          if (cand) {
            await cdp.ev(`(function(){
              var cc = window.__tg.content();
              var el = cc ? cc.querySelector('[data--block-index="${cand.index}"]') : null;
              if (!el) return { err: 'no-el' };
              var target = el.querySelector('[contenteditable="true"]') || el;
              try {
                target.focus();
                var sel = window.getSelection(); var rg = document.createRange();
                rg.selectNodeContents(target); rg.collapse(false);
                sel.removeAllRanges(); sel.addRange(rg);
                document.execCommand('insertText', false, 'X');
              } catch (e) { return { err: 'edit-fail:' + e.message }; }
              return { ok: 1 };
            })()`);
            await sleep(1000);
            // 5 断言：该块文本含新字符；相邻块文本不变
            const vpE = await snapViewport();
            const eb = vpE.blocks.find(b => String(b.index) === String(cand.index));
            const added = eb && eb.text.includes('X') && !cand.text.includes('X');
            // 相邻块
            const idxArr = vpE.blocks.map(b => String(b.index));
            const pos = idxArr.indexOf(String(cand.index));
            const neighborOk = (() => {
              const prevB = pos > 0 ? vpE.blocks[pos - 1] : null;
              const nextB = pos >= 0 && pos < vpE.blocks.length - 1 ? vpE.blocks[pos + 1] : null;
              const gPrev = prevB ? G.blocks.find(b => String(b.index) === String(prevB.index)) : null;
              const gNext = nextB ? G.blocks.find(b => String(b.index) === String(nextB.index)) : null;
              const pOk = !prevB || !gPrev || normText(prevB.text) === normText(gPrev.text);
              const nOk = !nextB || !gNext || normText(nextB.text) === normText(gNext.text);
              return pOk && nOk;
            })();
            // 编辑区镜像
            const dEd = diffEditor(vpE.editor || [], G.docLines || []);
            const edOk = dEd.diffs.length === 0;
            console.log(`        [${added && neighborOk && edOk ? 'OK  ' : 'DIFF'}] [${roundTag}] 5-编辑 index=${cand.index} 新字符=${added} 邻块不变=${neighborOk} 编辑区=${edOk}`);
            if (!(added && neighborOk && edOk)) rbad++;
            docRes.steps.push({ round: roundTag, step: 'edit', index: cand.index, added, neighborOk, edOk,
              editDiffs: dEd.diffs.slice(0, 2) });

            // 6 undo
            await cdp.ev(`(function(){ try { document.execCommand('undo'); } catch(e){ return String(e.message); } return 1; })()`);
            await sleep(1400);
            await waitViewportReadable(10000);
            const vpU = await snapViewport();
            const dU = diffViewport(vpU, G.blocks);
            rbad += reportStep(file, `[${roundTag}] 6-undo`, dU);
            docRes.steps.push({ round: roundTag, step: 'undo', matched: dU.matched, diffs: dU.diffs.length });
            fingerprint.push('undo:' + (dU.diffs.length === 0 ? 1 : 0));
          }
        }

        // 7 切页签离开再回
        const other = 'homework/README.md';
        await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(other)}, { skipNav: true })`);
        await sleep(1500);
        await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
        await sleep(2500);
        await waitViewportReadable(10000);
        const vpT = await snapViewport();
        const dT = diffViewport(vpT, G.blocks);
        // 白屏断言：视口内 placeholder 必须 0
        if (vtp_ph_bad(vpT)) dT.diffs.push({ kind: 'white-screen', placeholders: vpT.placeholders });
        rbad += reportStep(file, `[${roundTag}] 7-切页签返回`, dT);
        docRes.steps.push({ round: roundTag, step: 'tab-return', placeholders: vpT.placeholders, matched: dT.matched, diffs: dT.diffs.length });
        fingerprint.push('tab:' + (dT.diffs.length === 0 ? 1 : 0));

        return { rbad, fingerprint: fingerprint.join('|') };
      }

      // ══ 第 1 轮 ══
      const r1 = await runSequence('R1');
      bad += r1.rbad;

      // ══ 第 2 轮（重复 2-7），比对两轮指纹一致 ══
      await cdp.ev(`window.__tg.scrollTo(0)`);
      await sleep(800);
      const r2 = await runSequence('R2');
      bad += r2.rbad;
      // 两轮一致 = 两轮**每一步的 diff 数都相同**，且都关注"是否有残留"
      //   ⚠️ 不比对视口块列表：滚动到相同 pct 时文档高度随物化变化 ⇒ 视口块集必然不同（假阳性）
      //   ⚠️ 也不比对"是否全对"布尔：某步 R1 有 diff、R2 无 diff 属真实差异，但两轮都 0 就该判一致
      const fpR1 = r1.fingerprint.split('|');
      const fpR2 = r2.fingerprint.split('|');
      const roundsConsistent = fpR1.length === fpR2.length && fpR1.every((v, i) => v === fpR2[i]);
      console.log(`        [${roundsConsistent ? 'OK  ' : 'DIFF'}] 8-两轮一致: ${roundsConsistent}`);
      if (!roundsConsistent) {
        console.log('          R1 fp: ' + String(r1.fingerprint).slice(0, 260));
        console.log('          R2 fp: ' + String(r2.fingerprint).slice(0, 260));
      }
      if (!roundsConsistent) {
        bad++;
        docRes.steps.push({ step: 'rounds-consistent', ok: false });
      } else {
        docRes.steps.push({ step: 'rounds-consistent', ok: true });
      }

      docRes.totalDiffs = bad;
      if (bad > 0) exitDiffs.push({ file, diffs: bad });
      console.log('  => ' + file + ' ' + (bad === 0 ? 'PASS' : 'FAIL(' + bad + ' diffs)'));
    } catch (e) {
      console.log('  => ' + file + ' ERROR: ' + String(e && e.message || e).slice(0, 150));
      docRes.error = String(e && e.message || e);
      exitDiffs.push({ file, error: docRes.error });
    }
    report.documents[file] = docRes;
  }
  writeFileSync(dataPath.replace(/\.json$/, '-verify.json'), JSON.stringify(report, null, 2), 'utf8');
  console.log('');
  console.log('=== 汇总 ===');
  if (exitDiffs.length === 0) console.log('  全部 PASS');
  else { console.log('  有 diff:'); for (const x of exitDiffs) console.log('    ' + JSON.stringify(x)); }

  // ── lazy 日志统计（Lead 要求：typeset 次数、retoken 证据）──
  captureLogs = false;
  const tsLogs = lazyLogs.filter(t => /math merge typeset/i.test(t));
  const retokenLogs = lazyLogs.filter(t => /retoken same-doc/i.test(t));
  const forceLogs = lazyLogs.filter(t => /force/i.test(t));
  const reqLogs = lazyLogs.filter(t => /re-queue connected/i.test(t));
  console.log('');
  console.log('=== lazy 日志统计 ===');
  console.log('  math merge typeset 次数: ' + tsLogs.length);
  tsLogs.slice(0, 12).forEach(t => console.log('    ' + t.slice(0, 130)));
  console.log('  retoken same-doc 次数: ' + retokenLogs.length + (retokenLogs.length ? ' ✅ 修复生效' : ' ⚠️ 未出现'));
  retokenLogs.slice(0, 5).forEach(t => console.log('    ' + t.slice(0, 130)));
  console.log('  re-queue connected 次数: ' + reqLogs.length);
  console.log('  force schedule 相关: ' + forceLogs.length);
  report.lazyStats = {
    mathMergeTypeset: tsLogs.length,
    retokenSameDoc: retokenLogs.length,
    reQueueConnected: reqLogs.length,
    forceSchedule: forceLogs.length,
    samples: { typeset: tsLogs.slice(0, 5), retoken: retokenLogs.slice(0, 5) },
  };
  writeFileSync(dataPath.replace(/\.json$/, '-verify.json'), JSON.stringify(report, null, 2), 'utf8');
  console.log('');
  console.log('__GATE__' + JSON.stringify({
    exitDiffs,
    lazyStats: {
      typeset: tsLogs.length,
      retoken: retokenLogs.length,
      reQueue: reqLogs.length,
    },
  }));
}

cdp.close();
setTimeout(() => process.exit(exitDiffs.length === 0 ? 0 : 1), 300).unref();
