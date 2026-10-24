#!/usr/bin/env node
/**
 * p5perf_workload2.mjs —— task-48：工作量计数（新判据 A/B 分离）
 *
 * ⚠️⚠️ task-81/82 复核事实（grep 全仓，2026-10-24）：**本文件已无入口**。
 *   全仓 `grep -r p5perf_workload2` 只命中本文件自己的头注。
 *   真正在用的 v2 runner 是 **`p5perf_run2.mjs` + `_wl2_install.js.txt`**。
 *   本文件是历史草稿（定义了 INSTALL / OPS / helpers，但没有 main 流程）。
 *   ⇒ **已无入口，生产路径见 `p5perf_run2.mjs` + `_wl2_install.js.txt`**。
 *   ⇒ 修测量缺陷请改那两个文件；本文件保留仅为**历史与 A/B 对照**，**不要删**。
 *     本文件内的探针语义已与生产路径对齐（若将来补入口可直接用）。
 *
 * Lead 新判据：
 *   A 类（确定性，必须逐字节一致）：M1/M2/parse/render/renderRange/renderBlock/upsert/
 *                                    insertText/splitParagraph/undo/redo/backspace/renderPreview
 *   B 类（竞态，不要求一致，只记录范围）：typeset / flushRepaint
 *
 * 关键设计（避免 task-47 踩过的坑）：
 *   ① 先打印通路状态（viewMode / #preview 块数 / install ok），再判产品
 *   ② 探针**只装一次**（不在循环内重装 —— 重装会把 W.on 重置为 false）
 *   ③ openDoc 后**显式等待** viewMode==='preview'（不依赖点按钮）
 *   ④ save 前显式等 pending 落定
 *   ⑤ 每个 op 有独立的目标文档（KP 操作要用含 KP 的文档）
 */
import fs from 'node:fs';
import crypto from 'node:crypto';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) { return new Promise((res, rej) => { const ws = new WebSocket(u); const to = setTimeout(() => rej(new Error('t')), 20000); ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); }); ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('e')); }); }); }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(m, p = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method: m, params: p })); }); }
  async ev(x, timeoutMs) {
    const to = (typeof timeoutMs === 'number' && timeoutMs > 0) ? timeoutMs : 30000;
    const r = await Promise.race([
      this.send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true, userGesture: true }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('eval-timeout:' + to)), to)),
    ]);
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); }
    return r.result ? r.result.value : undefined;
  }
  async waitFor(x, t = 60000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('waitFor-timeout'); await sleep(120); } }
  async click(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  }
  async mouseMove(x, y) { await this.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none' }); }
  close() { try { this.ws.close(); } catch { /* */ } }
}

/* ══ 探针：只装一次；A/B 类分离 ══ */
const INSTALL = `(function(){
  if (window.__wl2) return { already:true, wrapped: window.__wl2.wrapped };
  var W = window.__wl2 = {
    v: 3, on: false,
    // A 类：确定性计数
    m1: 0, m2add: 0, m2del: 0, attrWrites: 0,
    // B 类：竞态计数
    typeset: 0, flushRepaint: 0,
    acc: {}, sigBefore: [], blocksBefore: 0
  };
  var counters = {};
  function resetAcc(){ counters = {}; }
  function inc(n){ counters[n] = (counters[n]||0) + 1; }

  var obs = new MutationObserver(function(recs){
    if (!W.on) return;
    W.m1 += recs.length;
    for (var i=0;i<recs.length;i++){
      var r = recs[i];
      if (r.type === 'attributes') { if (r.attributeName === 'data--src-line') W.attrWrites++; continue; }
      if (r.addedNodes) W.m2add += r.addedNodes.length;
      if (r.removedNodes) W.m2del += r.removedNodes.length;
    }
  });
  W.obs = obs;

  function wrap(obj, prop, label, isRacy){
    if (!obj || typeof obj[prop] !== 'function') return false;
    if (obj[prop].__wlWrapped) return true;
    var orig = obj[prop];
    var w = function(){
      if (W.on) { if (isRacy) { if (label==='typeset') W.typeset++; else W.flushRepaint++; } else inc(label); }
      return orig.apply(this, arguments);
    };
    w.__wlWrapped = true;
    try { obj[prop] = w; } catch(e){ return false; }
    return true;
  }

  // ── task-81：P6d 删除了 window.MemoriaRenderer ⇒ 旧写法 wrap 静默 false。
  //   修法（不是"改对一条 wrap"，而是**让可包装性可证**）：
  //     ① 由 BOOT_HOOK 在页面脚本执行前挂钩 window.MemoriaRenderCore.createRenderCore，
  //        包装 app 自己创建的实例（app.js _rcCore / new-surface / agent-panel）；
  //     ② collect 时 calls 的每个分项是「数字」或 "unsupported"，禁止缺省当 0；
  //     ③ wrapFailed[] + wrapIntegrity.ok 写进产物并吼到 stderr。
  //   若挂钩未生效（WebView2 不支持 addScriptToEvaluateOnNewDocument / reload 失败），
  //   则如实报 wrapFailed，calls 分项为 "unsupported"。
  W.wrapped = {
    // A 类
    parse: wrap(window.MemoriaParser, 'parse', 'parse', false),
    // render/renderRange/renderBlock/... 由 boot hook 包装，collect 时以 __wlCore.methods 为准
    render: false,
    renderRange: false,
    renderBlock: false,
    renderAll: false,
    renderInline: false,
    renderInlineList: false,
    renderPreview: wrap(window.MemoriaApp, 'renderPreview', 'renderPreview', false),
    insertText: wrap(window.MemoriaEditSync, 'insertText', 'insertText', false),
    splitParagraph: wrap(window.MemoriaEditSync, 'splitParagraph', 'splitParagraph', false),
    backspace: wrap(window.MemoriaEditSync, 'backspace', 'backspace', false),
    undo: wrap(window.MemoriaEditSync, 'undo', 'undo', false),
    redo: wrap(window.MemoriaEditSync, 'redo', 'redo', false),
    // B 类（竞态）
    typeset: wrap(window.MathJax, 'typesetPromise', 'typeset', true),
    flushRepaint: wrap(window.MemoriaEditSync, 'flushRepaint', 'flushRepaint', true)
  };

  // 探针可用性诊断（写进产物，禁止静默）
  W.probeAvailability = {
    MemoriaRendererExists: typeof window.MemoriaRenderer !== 'undefined',
    renderCoreExists: typeof window.MemoriaRenderCore !== 'undefined',
    note: 'P6d 删除 MemoriaRenderer；render-core 实例改由 boot hook 包装（见 wrapState()）。'
        + ' 若 wrapFailed 非空 ⇒ calls 分项为 "unsupported"，禁止读成 0。'
  };
  W.wrapState = function(){
    var C = window.__wlCore;
    var METHODS = ['render', 'renderRange', 'renderBlock', 'renderAll', 'renderInline', 'renderInlineList'];
    var wrapFailed = [];
    if (!C) { wrapFailed.push('boot-hook-not-installed'); }
    else {
      if (C.hookError) wrapFailed.push('boot-hook-error:' + C.hookError);
      if (!C.factorySeen) wrapFailed.push('render-core-factory-not-seen');
      if (C.instances === 0) wrapFailed.push('render-core-instance-not-created');
      for (var mi = 0; mi < METHODS.length; mi++) {
        var nm = METHODS[mi], st = C.methods && C.methods[nm];
        W.wrapped[nm] = !!(st && st.wrapped > 0 && st.failed === 0);
      }
      for (var mj = 0; mj < (C.wrapFailed || []).length; mj++) wrapFailed.push(C.wrapFailed[mj]);
    }
    W.probeAvailability.unwrappable = METHODS.filter(function(k){ return !W.wrapped[k]; });
    return { wrapped: W.wrapped, wrapFailed: wrapFailed,
             instances: C ? C.instances : 0,
             factorySeen: C ? !!C.factorySeen : false,
             hookError: C ? C.hookError : 'boot-hook-not-installed' };
  };
  // upsert（A 类）
  (function(){
    var BI = window.MemoriaApp && window.MemoriaApp.blockIndex;
    if (BI && typeof BI.upsert === 'function' && !BI.upsert.__wlWrapped) {
      var o = BI.upsert;
      var w = function(){ if (W.on) inc('upsert'); return o.apply(this, arguments); };
      w.__wlWrapped = true; BI.upsert = w; W.wrapped.upsert = true;
    }
  })();

  W.reset = function(){
    resetAcc();
    W.m1 = 0; W.m2add = 0; W.m2del = 0; W.attrWrites = 0; W.typeset = 0; W.flushRepaint = 0;
    // 清 boot-hook 侧的分方法计数（与 counters 分开存放，见 BOOT_HOOK 的 bump()）
    try { if (window.__wlCore) window.__wlCore.calls = {}; } catch (e) {}
    var p = document.getElementById('preview');
    // 每次 reset 重绑 observer 到**当前** #preview（openDoc 可能换节点）
    try { obs.disconnect(); } catch(e){}
    if (p) { try { obs.observe(p, { childList:true, subtree:true, attributes:true, attributeFilter:['data--src-line'] }); } catch(e){} }
    W.blocksBefore = p ? p.querySelectorAll('.-src-block').length : 0;
    W.sigBefore = [];
    if (p) { var bs = p.querySelectorAll('.-src-block');
      for (var i=0;i<bs.length;i++) W.sigBefore.push((bs[i].innerHTML||'').length + ':' + String(bs[i].className||'')); }
    W.on = true;
    return { blocksBefore: W.blocksBefore };
  };

  var CALL_LABELS = ['parse', 'parseRange', 'render', 'renderRange', 'renderBlock',
                     'renderAll', 'renderInline', 'renderInlineList',
                     'typeset', 'renderPreview', 'setBlockSource',
                     'insertText', 'splitParagraph', 'backspace', 'undo', 'redo', 'flushRepaint', 'upsert'];
  W.collect = function(){
    W.on = false;
    var p = document.getElementById('preview');
    var bs = p ? p.querySelectorAll('.-src-block') : [];
    var sigBefore = W.sigBefore || [];
    var changed = 0;
    for (var i=0;i<bs.length && i<sigBefore.length;i++){
      if (((bs[i].innerHTML||'').length + ':' + String(bs[i].className||'')) !== sigBefore[i]) changed++;
    }
    var ws = W.wrapState();
    var coreCalls = (window.__wlCore && window.__wlCore.calls) || {};
    var calls = {};
    for (var k = 0; k < CALL_LABELS.length; k++) {
      var label = CALL_LABELS[k];
      calls[label] = W.wrapped[label] ? ((counters[label] || 0) + (coreCalls[label] || 0)) : 'unsupported';
    }
    // 拆 A / B
    var A = { M1: W.m1, M2add: W.m2add, M2del: W.m2del, M2: W.m2add + W.m2del,
              attrWrites: W.attrWrites, blocksChanged: changed,
              blocksBefore: W.blocksBefore, blocksAfter: bs.length, calls: calls,
              wrapped: ws.wrapped, wrapFailed: ws.wrapFailed, rendererInstances: ws.instances };
    var B = { typeset: W.typeset, flushRepaint: W.flushRepaint };
    return { A: A, B: B };
  };
  return { ok:true, wrapped: W.wrapped, wrapState: W.wrapState, probeAvailability: W.probeAvailability };
})()`;

/* ══ task-81：boot hook（必须在页面脚本执行前注入；与 p5perf_workload.mjs 内副本一致）══
 * 为什么必须 reload：render-core 实例（app.js `_rcCore`）在首次 renderPreview 时创建，
 *   之后不可达；只有页面启动前包装工厂才能包到它。
 */
const BOOT_HOOK = `(function(){
  var S = window.__wlCore = {
    v: 1, installed: true, hookError: null, factorySeen: false, instances: 0,
    methods: { render: {wrapped:0, failed:0}, renderRange: {wrapped:0, failed:0}, renderBlock: {wrapped:0, failed:0},
               renderAll: {wrapped:0, failed:0}, renderInline: {wrapped:0, failed:0}, renderInlineList: {wrapped:0, failed:0} },
    calls: {}, wrapFailed: []
  };
  function bump(label){
    try { var W = window.__wl || window.__wl2; if (W && W.on) { S.calls[label] = (S.calls[label]||0)+1; } } catch(e){}
  }
  function patchInstance(inst){
    S.instances++;
    var MAP = { renderDocument: 'render', renderRange: 'renderRange', renderBlock: 'renderBlock',
                renderAll: 'renderAll', renderInline: 'renderInline', renderInlineList: 'renderInlineList' };
    for (var m in MAP) {
      if (!MAP.hasOwnProperty(m)) continue;
      var label = MAP[m];
      (function(m, label){
        if (!inst || typeof inst[m] !== 'function') { S.methods[label].failed++; S.wrapFailed.push(label + ':missing-on-instance'); return; }
        if (inst[m].__wlWrapped) { S.methods[label].wrapped++; return; }
        var f = inst[m];
        var w = function(){ bump(label); return f.apply(this, arguments); };
        w.__wlWrapped = true;
        try { inst[m] = w; S.methods[label].wrapped++; }
        catch (e) { S.methods[label].failed++; S.wrapFailed.push(label + ':assign-failed'); }
      })(m, label);
    }
    return inst;
  }
  try {
    var _val;
    Object.defineProperty(window, 'MemoriaRenderCore', {
      configurable: true,
      get: function(){ return _val; },
      set: function(v){
        try {
          if (v && typeof v.createRenderCore === 'function' && !v.createRenderCore.__wlWrapped) {
            var orig = v.createRenderCore;
            var wrappedFactory = function(){ return patchInstance(orig.apply(this, arguments)); };
            wrappedFactory.__wlWrapped = true;
            v.createRenderCore = wrappedFactory;
            S.factorySeen = true;
          }
        } catch (e) { S.hookError = String((e && e.message) || e); }
        _val = v;
      }
    });
  } catch (e) { S.hookError = String((e && e.message) || e); }
})()`;

async function installBootHook() {
  const out = { attempted: true, pageEnabled: false, hookAdded: false, reloaded: false, error: null };
  try {
    await cdp.send('Page.enable');
    out.pageEnabled = true;
    const r = await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: BOOT_HOOK });
    out.hookAdded = !!(r && r.identifier);
    out.hookIdentifier = (r && r.identifier) || null;
    if (!out.hookAdded) throw new Error('addScriptToEvaluateOnNewDocument 未返回 identifier');
    await cdp.send('Page.reload', { ignoreCache: false });
    out.reloaded = true;
    await sleep(1200);
    await cdp.waitFor('!!(window.MemoriaApp && window.state)', 120000);
    out.hookInstalledInPage = await cdp.ev('!!(window.__wlCore && window.__wlCore.installed)');
  } catch (e) {
    out.error = String((e && e.message) || e);
  }
  return out;
}

const port = Number(process.argv[2] || 9500);
const side = process.argv[3] || 'new';
const outPath = process.argv[4] || '';
const REPEAT = Number(process.argv[5] || 3);

const DEFAULT_DOC = 'corpus/03-block-boundaries.md';
const KP_DOC = 'corpus/06-links-and-kp.md';

/* ══ 操作定义：每个 op 有目标文档 + 执行逻辑 ══ */
const OPS = {
  // ── 原有 6 项 ──
  typing: { doc: DEFAULT_DOC, run: async () => { await caret(4); await cdp.key('q'); } },
  structEdit: { doc: DEFAULT_DOC, run: async () => { await caret(4); await cdp.ev(`(function(){ try{ window.MemoriaEditSync.splitParagraph(); }catch(e){} return 1; })()`); } },
  undo: { doc: DEFAULT_DOC, run: async () => { await caret(4); await cdp.ev(`(function(){ try{ window.MemoriaEditSync.insertText('u'); }catch(e){} return 1; })()`); await sleep(400); await cdp.ev(`(function(){ try{ window.MemoriaEditSync.undo(); }catch(e){} return 1; })()`); } },
  viewSwitch: { doc: DEFAULT_DOC, run: async () => { await doSetMode('source'); await doSetMode('preview'); } },
  open: { doc: DEFAULT_DOC, run: async () => { await openFile('corpus/01-ime-zh.md'); await sleep(400); await openFile(DEFAULT_DOC); await sleep(500); } },
  scroll: { doc: DEFAULT_DOC, run: async () => { await cdp.ev(`(function(){ var pv=document.getElementById('preview'); if(!pv) return 0; var el=pv.scrollHeight>pv.clientHeight?pv:(document.scrollingElement||document.documentElement); el.scrollTop=Math.min(el.scrollHeight, el.scrollTop+1200); return el.scrollTop; })()`); } },

  // ── task-47 补的 7 项 ──
  tabSwitch: { doc: DEFAULT_DOC, run: async () => { await openFile('corpus/01-ime-zh.md'); await sleep(400); await openFile(DEFAULT_DOC); await sleep(500); } },
  kpHover: { doc: KP_DOC, run: async () => {
      // 真实鼠标移到 KP 标记（先滚到可见，再用 Input.dispatchMouseEvent）
      const loc = await cdp.ev(`(function(){
        var it = document.querySelector('#kp-list .-kp-item');
        if (!it) return { ok:false, reason:'no-kp-item' };
        it.scrollIntoView({ block:'center' });
        var r = it.getBoundingClientRect();
        if (r.width < 2) return { ok:false, reason:'zero-size' };
        return { ok:true, x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
      })()`);
      if (!loc || !loc.ok) throw new Error('kpHover:' + (loc && loc.reason));
      await cdp.mouseMove(loc.x - 5, loc.y);
      await sleep(60);
      await cdp.mouseMove(loc.x, loc.y);
      await sleep(300);
    } },
  select: { doc: DEFAULT_DOC, run: async () => {
      // 真实拖选（#preview）：鼠标按下 → 拖动 → 抬起
      const loc = await cdp.ev(`(function(){
        var bs = document.querySelectorAll('#preview .-src-block');
        var el = null;
        for (var i=0;i<bs.length;i++){ var t=(bs[i].textContent||'').trim();
          if (t.length > 8 && !bs[i].classList.contains('-blank-block')) { el = bs[i]; break; } }
        if (!el) return { ok:false };
        el.scrollIntoView({ block:'center' });
        var r = el.getBoundingClientRect();
        return { ok:true, x1: Math.round(r.left+6), x2: Math.round(r.left+Math.min(80, r.width-6)), y: Math.round(r.top + r.height/2) };
      })()`);
      if (!loc || !loc.ok) throw new Error('select:no-block');
      await cdp.send('Input.dispatchMouseEvent', { type:'mousePressed', x:loc.x1, y:loc.y, button:'left', clickCount:1 });
      await cdp.send('Input.dispatchMouseEvent', { type:'mouseMoved', x:loc.x2, y:loc.y, button:'left' });
      await cdp.send('Input.dispatchMouseEvent', { type:'mouseReleased', x:loc.x2, y:loc.y, button:'left', clickCount:1 });
      await sleep(300);
    } },
  format: { doc: DEFAULT_DOC, run: async () => {
      await caret(4);
      await cdp.ev(`(function(){
        var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
        for (var i=0;i<els.length;i++){
          var c = String(els[i].className||'');
          if (c.indexOf('-code-block')<0 && c.indexOf('-table')<0 && c.indexOf('-math-block')<0 &&
              c.indexOf('-mermaid')<0 && c.indexOf('-blank-block')<0) {
            var w = document.createTreeWalker(els[i], NodeFilter.SHOW_TEXT, null);
            var n = w.nextNode();
            if (n) { var r = document.createRange(); r.setStart(n,0); r.setEnd(n,Math.min(3,n.nodeValue.length));
              var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
              document.dispatchEvent(new Event('selectionchange')); }
            break;
          }
        }
        return 1;
      })()`);
      await sleep(200);
      await cdp.ev(`(function(){ var b=document.querySelector('.-fmt-btn[data-fmt="bold"]'); if(b) b.click(); return 1; })()`);
      await sleep(300);
    } },
  paste: { doc: DEFAULT_DOC, run: async () => {
      // 走真实粘贴路径：先用 Input.insertText（等价于用户粘贴的文本注入），
      // 再派发 paste 事件（部分编辑器监听）
      await caret(4);
      await cdp.ev(`(function(){
        var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
        var t = null;
        for (var i=0;i<els.length;i++){ var c=String(els[i].className||'');
          if (c.indexOf('-code-block')<0&&c.indexOf('-table')<0&&c.indexOf('-math-block')<0&&
              c.indexOf('-mermaid')<0&&c.indexOf('-blank-block')<0){ t=els[i]; break; } }
        if (!t) return 0;
        var r = t.getBoundingClientRect();
        t.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,clientX:r.left+20,clientY:r.top+8}));
        t.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,clientX:r.left+20,clientY:r.top+8}));
        return 1;
      })()`);
      await sleep(200);
      // 真实粘贴的核心路径：insertText（应用把粘贴转成 insertText）
      await cdp.ev(`(function(){ try { return !!window.MemoriaEditSync.insertText('PP'); } catch(e){ return false; } })()`);
      await sleep(300);
    } },
  find: { doc: DEFAULT_DOC, run: async () => {
      // 先尝试打开查找框（Ctrl+F 或按钮），再输入
      const opened = await cdp.ev(`(function(){
        // 常见入口：Ctrl+F 由应用监听；也尝试点按钮
        var btn = document.querySelector('[data-action="find"], .-find-btn, #find-btn, button[title*="查找"]');
        if (btn) { btn.click(); return { via:'button' }; }
        document.dispatchEvent(new KeyboardEvent('keydown', { key:'f', code:'KeyF', ctrlKey:true, bubbles:true }));
        return { via:'ctrl-f' };
      })()`);
      await sleep(400);
      const r = await cdp.ev(`(function(){
        var cands = ['#find-input','.-find-input','input[placeholder*="查找"]','input[placeholder*="搜索"]','#search-input','.-search-input'];
        for (var i=0;i<cands.length;i++){ var el=document.querySelector(cands[i]); if (el) return { ok:true, sel:cands[i], tag:el.tagName.toLowerCase() }; }
        // 兜底：找所有 visible input
        var ins = Array.prototype.slice.call(document.querySelectorAll('input'));
        var vis = ins.filter(function(e){ var r=e.getBoundingClientRect(); return r.width>10 && r.height>10; });
        return { ok:false, inputCount: ins.length, visible: vis.map(function(e){ return { id:e.id, cls:String(e.className||''), ph:e.placeholder }; }) };
      })()`);
      if (!r || !r.ok) throw new Error('find:no-input ' + JSON.stringify(r));
      await cdp.ev(`(function(){
        var el = document.querySelector(${JSON.stringify(r.sel)});
        if (!el) return 0;
        el.focus();
        el.value = '第一段';
        el.dispatchEvent(new Event('input', { bubbles:true }));
        el.dispatchEvent(new KeyboardEvent('keydown', { key:'Enter', code:'Enter', bubbles:true }));
        return 1;
      })()`);
      await sleep(400);
    } },
  save: { doc: DEFAULT_DOC, run: async () => {
      await caret(4);
      await cdp.ev(`(function(){ try { window.MemoriaEditSync.insertText('Z'); } catch(e){} return 1; })()`);
      await sleep(400);
      // 显式等 pending 落定（带超时，不永久挂）
      await cdp.ev(`(async function(){
        var p = window.state && window.state._mathPending;
        if (!p) return 0;
        await Promise.race([ Promise.resolve(p).then(function(){},function(){}),
                             new Promise(function(r){ setTimeout(r, 2000); }) ]);
        return 1;
      })()`);
      await cdp.key('s', 'KeyS', 2);
      await sleep(600);
    } },
};

/* ══ helpers ══ */
let cdp;

async function openFile(f) {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(f)}, { skipNav: true })`);
  await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(f)} && !!window.state.doc`, 40000);
  await sleep(500);
}

/** 显式切模式并**等待真的生效**（不依赖点按钮成功） */
async function doSetMode(mode) {
  for (let i = 0; i < 12; i++) {
    const cur = await cdp.ev('(window.state||{}).viewMode || null');
    if (cur === mode) return true;
    await cdp.ev(`(function(){
      var b = document.querySelector('.-view-btn[data-view="${mode}"]');
      if (b) { try { b.click(); } catch(e){} }
      return 1;
    })()`);
    await sleep(250);
  }
  return (await cdp.ev('(window.state||{}).viewMode || null')) === mode;
}

/** 等待预览就绪：viewMode===preview 且 #preview 有块 */
async function waitPreviewReady(doc, minBlocks) {
  const ok = await doSetMode('preview');
  if (!ok) return { ok: false, reason: 'setmode-failed', viewMode: await cdp.ev('(window.state||{}).viewMode') };
  for (let i = 0; i < 40; i++) {
    const st = await cdp.ev(`(function(){
      return { blocks: document.querySelectorAll('#preview .-src-block').length,
               viewMode: (window.state||{}).viewMode };
    })()`);
    if (st && st.blocks >= (minBlocks || 1) && st.viewMode === 'preview') return { ok: true, ...st };
    await sleep(150);
  }
  const st2 = await cdp.ev(`(function(){ return { blocks: document.querySelectorAll('#preview .-src-block').length, viewMode:(window.state||{}).viewMode }; })()`);
  return { ok: false, reason: 'preview-not-ready', ...st2 };
}

async function caret(bi) {
  const loc = await cdp.ev(`(function(){
    var pv = document.getElementById('preview');
    if (!pv) return { ok:false, reason:'no-preview' };
    var b = pv.querySelectorAll('.-src-block')[${bi}];
    if (!b) return { ok:false, reason:'no-block' };
    b.scrollIntoView({ block:'center' });
    var r = b.getBoundingClientRect();
    if (r.width < 4) return { ok:false, reason:'zero-width' };
    return { ok:true, x: Math.round(r.left + Math.min(30, r.width/2)), y: Math.round(r.top + r.height/2) };
  })()`);
  if (!loc || !loc.ok) return false;
  await sleep(80);
  await cdp.click(loc.x, loc.y);
  await sleep(150);
  return true;
}

