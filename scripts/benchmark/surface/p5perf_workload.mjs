#!/usr/bin/env node
/**
 * p5perf_workload.mjs —— P5 性能总闸：**工作量计数**（主证据，密封）
 *
 * 依据 Lead 裁决：工作量计数「同输入 ⇒ 同计数，与并发无关」⇒ 完全密封，
 * 是判断"新管线是否做了更多工作"的**一等证据**；wall-time 只作辅证。
 *
 * 计数项：
 *   M1 = DOM 变异批次数（MutationObserver records 数）
 *   M2 = DOM 节点增删总数（added + removed nodes）
 *   调  parse / render / renderRange / typeset / postProcess / bind 的**调用次数**
 *   块  blocksChanged / attrWrites（data--src-line）
 *   upsert 次数（BlockIndex.upsert）
 *
 * 对每个操作，在**同一次会话内**分别于 new / legacy 两侧执行，得到两侧计数。
 * 计数若两侧不同 ⇒ 新管线做了不同工作量（必须解释）。
 *
 * 输出：p5-workload-<side>-<sha>.json（可逐字节比对，实现真自检）
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
    // ⚠️ 默认 30s 超时：Runtime.evaluate 若不设超时，页面内 await 一个永不 resolve 的
    //    promise（如 state._mathPending）会让整个测量永久挂住（本轮曾卡 30 分钟）。
    const to = (typeof timeoutMs === 'number' && timeoutMs > 0) ? timeoutMs : 30000;
    const evalP = this.send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true, userGesture: true });
    const r = await Promise.race([
      evalP,
      new Promise((_, rej) => setTimeout(() => rej(new Error('eval-timeout:' + to + 'ms:' + String(x).slice(0, 60))), to)),
    ]);
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); }
    return r.result ? r.result.value : undefined;
  }
  async waitFor(x, t = 180000) { const t0 = Date.now(); for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > t) throw new Error('timeout: ' + x.slice(0, 70)); await sleep(150); } }
  async click(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
    await this.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  }
  async key(ch, code, mods) {
    await this.send('Input.dispatchKeyEvent', { type: 'keyDown', text: ch, key: ch, code: code || '', windowsVirtualKeyCode: ch ? ch.charCodeAt(0) : 0, modifiers: mods || 0 });
    await this.send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch, code: code || '', modifiers: mods || 0 });
  }
  close() { try { this.ws.close(); } catch { /* */ } }
}

const port = Number(process.argv[2] || 9500);
const side = process.argv[3] || 'new';            // new | legacy
const outPath = process.argv[4] || '';
const file = 'corpus/03-block-boundaries.md';
const REPEAT = Number(process.argv[5] || 3);      // 每操作重复次数（取计数应恒定）

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
if (!page) { console.error('[wl] FATAL 未找到 page target（port=' + port + '）'); process.exit(2); }
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
// ⚠️ boot hook 的安装放在 BOOT_HOOK 常量定义**之后**（同类 const 有 TDZ：
//   在定义前调用会抛 "Cannot access before initialization"，正是 task-81
//   "失败必须可见"机制第一次实战抓出来的问题 —— 见下方 installBootHook 调用处）。

/* ═══════════════════════════════════════════════════════════════════════════
 * task-81 · 缺陷 2：wrap 静默失效（P6d 删除了 window.MemoriaRenderer）
 *
 * 事故：P6d 之后 `wrap(window.MemoriaRenderer, 'renderRange')` 直接返回 false
 *   （对象 undefined ⇒ `typeof obj[prop] !== 'function'`），`calls.renderRange`
 *   恒缺省/0 ⇒ 会被读成「零工作量」。
 *
 * 现状（实测，2026-10-24）：
 *   · window.MemoriaRenderer          = undefined（P6d 已删）
 *   · window.MemoriaRenderCore        = { createRenderCore, ... }（工厂，存在）
 *   · app.js `_rcCore` 是模块内 `let`，**未暴露到 window** ⇒ 页面加载后不可达
 *   · createRenderCore({}) 每次都返回**新实例**（无共享原型可 hook）
 *
 * ⇒ 唯一能包到"app 真正使用的实例"的办法：在**任何页面脚本执行之前**挂钩
 *   `window.MemoriaRenderCore` 的赋值（CDP `Page.addScriptToEvaluateOnNewDocument`
 *   + `Page.reload`），把 createRenderCore 的返回值包装起来。
 *   这样 app 自己创建的实例（`_rcCore`）、new-surface、agent-panel 的实例全部被包。
 *
 * 若挂钩失败（WebView2 不支持 / 未 reload）⇒ **绝不静默**：
 *   `calls.<method> = "unsupported"`（不是 0）+ `wrapFailed[]` + `wrapIntegrity.ok=false`。
 * ═══════════════════════════════════════════════════════════════════════════ */
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

const INSTALL = `(function(){
  if (window.__wl && window.__wl.v === 2) return { already:true };
  var W = window.__wl = { v:2, on:false, reset:function(){}, collect:function(){return null;} };

  var counters = {};
  function C(){ counters = {}; }
  function inc(name){ counters[name] = (counters[name]||0) + 1; }
  W.counters = function(){ return counters; };

  // ── DOM 变异：M1 批次数 / M2 节点增删数 ──
  var pv = document.getElementById('preview');
  var m1 = 0, m2add = 0, m2del = 0, attrWrites = 0;
  W.obs = new MutationObserver(function(recs){
    if (!W.on) return;
    m1 += recs.length;
    for (var i=0;i<recs.length;i++){
      var r = recs[i];
      if (r.type === 'attributes') { if (r.attributeName === 'data--src-line') attrWrites++; continue; }
      if (r.addedNodes) m2add += r.addedNodes.length;
      if (r.removedNodes) m2del += r.removedNodes.length;
    }
  });
  if (pv) W.obs.observe(pv, { childList:true, subtree:true, attributes:true, attributeFilter:['data--src-line'] });

  // ── 函数调用计数包装 ──
  function wrap(obj, prop, label){
    if (!obj || typeof obj[prop] !== 'function') return false;
    if (obj[prop].__wlWrapped) return true;
    var orig = obj[prop];
    var w = function(){ if (W.on) inc(label); return orig.apply(this, arguments); };
    w.__wlWrapped = true;
    try { obj[prop] = w; } catch(e){ return false; }
    return true;
  }
  // ★ task-81：render/renderRange/renderBlock 由 BOOT_HOOK 在页面脚本执行前包装
  //   （P6d 已删 window.MemoriaRenderer；render-core 实例是闭包私有）。
  //   这里**不再**对 undefined 目标调用 wrap —— 但"包没包上"由 WRAP_STATE_JS 如实汇报。
  W.wrapped = {
    parse: wrap(window.MemoriaParser, 'parse', 'parse'),
    parseRange: wrap(window.MemoriaParser, 'parseRange', 'parseRange'),
    render: false,          // 由 boot hook 决定，collect 时以 __wlCore.methods 为准
    renderRange: false,
    renderBlock: false,
    renderAll: false,
    renderInline: false,
    renderInlineList: false,
    typeset: wrap(window.MathJax, 'typesetPromise', 'typeset'),
    renderPreview: wrap(window.MemoriaApp, 'renderPreview', 'renderPreview'),
    setBlockSource: wrap(window.MemoriaApp && window.MemoriaApp.surface, 'setBlockSource', 'setBlockSource'),
    insertText: wrap(window.MemoriaEditSync, 'insertText', 'insertText'),
    splitParagraph: wrap(window.MemoriaEditSync, 'splitParagraph', 'splitParagraph'),
    backspace: wrap(window.MemoriaEditSync, 'backspace', 'backspace'),
    undo: wrap(window.MemoriaEditSync, 'undo', 'undo'),
    redo: wrap(window.MemoriaEditSync, 'redo', 'redo'),
    flushRepaint: wrap(window.MemoriaEditSync, 'flushRepaint', 'flushRepaint')
  };

  // ── BlockIndex.upsert 计数 ──
  (function(){
    var BI = window.MemoriaApp && window.MemoriaApp.blockIndex;
    if (BI && typeof BI.upsert === 'function' && !BI.upsert.__wlWrapped) {
      var origU = BI.upsert;
      var wu = function(){ if (W.on) inc('upsert'); return origU.apply(this, arguments); };
      wu.__wlWrapped = true;
      BI.upsert = wu;
      W.wrapped.upsert = true;
    }
  })();

  W.reset = function(){
    C(); m1 = 0; m2add = 0; m2del = 0; attrWrites = 0;
    // 清 boot-hook 侧的分方法计数（与 counters 分开存放，见 BOOT_HOOK 的 bump()）
    try { if (window.__wlCore) window.__wlCore.calls = {}; } catch (e) {}
    var p = document.getElementById('preview');
    // ★ 每次重置都**重新绑定** observer：#preview 节点可能已被 openDoc 换掉，
    //   旧 observer 挂在已脱离文档的节点上 ⇒ 计数恒 0 或抛错。
    try {
      if (W.obs) W.obs.disconnect();
      if (p) W.obs.observe(p, { childList:true, subtree:true, attributes:true, attributeFilter:['data--src-line'] });
    } catch(e){}
    W.blocksBefore = p ? p.querySelectorAll('.-src-block').length : 0;
    W.sigBefore = [];
    if (p) { var bs = p.querySelectorAll('.-src-block');
      for (var i=0;i<bs.length;i++) W.sigBefore.push((bs[i].innerHTML||'').length + ':' + String(bs[i].className||'')); }
    W.on = true;
    return { blocksBefore: W.blocksBefore };
  };
  // ★ task-81：calls 的每个分项必须是「实测数字」或 "unsupported"，**禁止缺省当 0**
  //   区分三态：
  //     number       = 已包装且计数（0 表示"测到了，确实没调用"）
  //     "unsupported"= 无法包装（P6d 删了目标对象 / 钩子没生效）⇒ 不可当 0 读
  var CALL_LABELS = ['parse', 'parseRange', 'render', 'renderRange', 'renderBlock',
                     'renderAll', 'renderInline', 'renderInlineList',
                     'typeset', 'renderPreview', 'setBlockSource',
                     'insertText', 'splitParagraph', 'backspace', 'undo', 'redo', 'flushRepaint', 'upsert'];
  /** 刷新并返回 render-core 侧的包装状态（实例可能在 INSTALL 之后才创建）。 */
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
    return { wrapped: W.wrapped, wrapFailed: wrapFailed,
             instances: C ? C.instances : 0,
             factorySeen: C ? !!C.factorySeen : false,
             hookError: C ? C.hookError : 'boot-hook-not-installed' };
  };
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
    return { M1: m1, M2add: m2add, M2del: m2del, M2: m2add + m2del,
             attrWrites: attrWrites, blocksChanged: changed,
             blocksBefore: W.blocksBefore, blocksAfter: bs.length,
             calls: calls,
             wrapped: ws.wrapped, wrapFailed: ws.wrapFailed,
             rendererInstances: ws.instances };
  };
  return { ok:true, wrapped: W.wrapped };
})()`;

/* ── 页面重载 + 钩子安装（Node 侧）─────────────────────────────────────────
 * 为什么必须 reload：boot hook 只能在页面脚本执行**之前**注入，否则
 * app.js 早已 `_rcCore = createRenderCore({})` 完成，实例不可达。
 * 返回结构化结果；失败也要如实返回（Node 侧写进产物 wrapIntegrity）。
 */
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

// ★ task-81：先在**文档开始前**挂钩 render-core 工厂，再 reload。
//   不做这步 ⇒ 只能得到 wrap(window.MemoriaRenderer=undefined) = 静默 false。
//   （必须在此处调用：BOOT_HOOK 是 const，前面调用会触发 TDZ。）
const boot = await installBootHook();
console.log('[wl] bootHook: ' + JSON.stringify(boot));
if (!boot.hookAdded || !boot.reloaded) {
  console.error('[wl] ⚠⚠ WRAP FAILED（boot hook 未生效）：calls 的 render* 分项将标为 "unsupported"，' +
    '**不得**把它们读成 0。原因：' + JSON.stringify(boot.error));
}
await cdp.waitFor('!!window.MemoriaApp && !!window.state', 120000);
async function openDoc() {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
  await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 40000);
  await sleep(800);
}
async function setMode(mode) {
  // ⚠️ 诊断发现：点 .-view-btn 后 state.viewMode 可能仍是 source（按钮选择器/时序问题）。
  //   这里做「点按钮 + 直接调用 app API」双保险，并**验证真的切过去了**。
  for (let i = 0; i < 10; i++) {
    const cur = await cdp.ev('(window.state||{}).viewMode || null');
    if (cur === mode) { await sleep(400); return true; }
    await cdp.ev(`(function(){
      var b=document.querySelector('.-view-btn[data-view="${mode}"]');
      if(b){ try{ b.click(); }catch(e){} }
      try { if (window.MemoriaApp && window.MemoriaApp.setMode) window.MemoriaApp.setMode('${mode}'); } catch(e){}
      return 1;
    })()`);
    await sleep(400);
  }
  const finalMode = await cdp.ev('(window.state||{}).viewMode || null');
  if (finalMode !== mode) { throw new Error('setMode-failed: want=' + mode + ' got=' + finalMode); }
  return true;
}
async function placeCaret(bi) {
  const loc = await cdp.ev(`(function(){
    var pv=document.getElementById('preview');
    var b=pv.querySelectorAll('.-src-block')[${bi}];
    if(!b) return {ok:false};
    b.scrollIntoView({block:'center'});
    var r=b.getBoundingClientRect();
    if(r.width<4||r.height<4) return {ok:false};
    return {ok:true,x:Math.round(r.left+Math.min(30,r.width/2)),y:Math.round(r.top+r.height/2)};
  })()`);
  if (!loc || !loc.ok) return false;
  await sleep(100);
  await cdp.click(loc.x, loc.y);
  await sleep(140);
  return true;
}

/* ── 操作定义：每个操作返回"施加动作"的闭包 ── */
const OPS = {
  typing: async () => {
    await setMode('preview');
    await placeCaret(4);
    await cdp.key('q');
  },
  structEdit: async () => {
    await setMode('preview');
    await placeCaret(4);
    await cdp.ev(`(function(){ try { window.MemoriaEditSync.splitParagraph(); } catch(e){} return 1; })()`);
  },
  undo: async () => {
    await setMode('preview');
    await placeCaret(4);
    await cdp.ev(`(function(){ try { window.MemoriaEditSync.insertText('u'); } catch(e){} return 1; })()`);
    await sleep(400);
    await cdp.ev(`(function(){ try { window.MemoriaEditSync.undo(); } catch(e){} return 1; })()`);
  },
  viewSwitch: async () => {
    await setMode('source');
    await setMode('preview');
  },
  open: async () => {
    // 切到别的文档再切回，制造一次完整 open
    await cdp.ev(`window.MemoriaApp.openFile('corpus/01-ime-zh.md',{skipNav:true})`);
    await cdp.waitFor(`window.state.currentPath === 'corpus/01-ime-zh.md'`, 30000);
    await sleep(500);
    await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)},{skipNav:true})`);
    await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 30000);
    await sleep(600);
  },
  scroll: async () => {
    await setMode('preview');
    await cdp.ev(`(function(){
      var pv=document.getElementById('preview');
      if(!pv) return 0;
      var el = pv.scrollHeight > pv.clientHeight ? pv : (document.scrollingElement||document.documentElement);
      el.scrollTop = Math.min(el.scrollHeight, el.scrollTop + 1500);
      return el.scrollTop;
    })()`);
  },

  /* ═══ task-47 L3：补齐剩余 7 操作（P6 删 legacy 前最后窗口）═══ */

  // ① tabSwitch —— 走全量重渲路径，既有红 1292ms，最可能暴露差异
  tabSwitch: async () => {
    await cdp.ev(`(async function(){
      try {
        window.MemoriaApp.openFile('corpus/01-ime-zh.md', { skipNav: true });
      } catch(e){}
      return 1;
    })()`);
    await cdp.waitFor(`window.state.currentPath === 'corpus/01-ime-zh.md'`, 30000);
    await sleep(500);
    // 切回主文档 = 一次完整 tabSwitch
    await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, 30000);
    await sleep(600);
  },

  // ② kpHover —— 大量 DOM 写（-sel-covered 等），直接可比
  kpHover: async () => {
    await setMode('preview');
    await cdp.ev(`(async function(){
      var item = document.querySelector('#kp-list .-kp-item');
      if (!item) return { ok:false, reason:'no-kp-item' };
      item.dispatchEvent(new MouseEvent('mouseenter', { bubbles:true, clientX:1, clientY:1 }));
      return { ok:true };
    })()`);
    await sleep(250);
  },

  // ③ select —— 跨块选区（涉及选区与反标）
  select: async () => {
    await setMode('preview');
    await cdp.ev(`(function(){
      var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      if (els.length < 3) return 0;
      var w = document.createTreeWalker(els[1], NodeFilter.SHOW_TEXT, null);
      var n = w.nextNode(); if (!n) return 0;
      var w2 = document.createTreeWalker(els[Math.min(els.length-1,4)], NodeFilter.SHOW_TEXT, null);
      var n2 = w2.nextNode(); if (!n2) return 0;
      var r = document.createRange();
      r.setStart(n, 0); r.setEnd(n2, Math.min(5, n2.nodeValue.length));
      var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
      document.dispatchEvent(new Event('selectionchange'));
      return 1;
    })()`);
    await sleep(250);
  },

  // ④ format —— 加粗按钮（选区内样式）
  format: async () => {
    await setMode('preview');
    await cdp.ev(`(function(){
      var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      var target = null;
      for (var i=0;i<els.length;i++){
        var c = String(els[i].className||'');
        if (c.indexOf('-code-block')<0 && c.indexOf('-table')<0 && c.indexOf('-math-block')<0 &&
            c.indexOf('-mermaid')<0 && c.indexOf('-blank-block')<0 && c.indexOf('-frontmatter')<0) { target = els[i]; break; }
      }
      if (!target) return 0;
      var w = document.createTreeWalker(target, NodeFilter.SHOW_TEXT, null);
      var n = w.nextNode(); if (!n) return 0;
      var r = document.createRange(); r.setStart(n,0); r.setEnd(n, Math.min(3, n.nodeValue.length));
      var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
      document.dispatchEvent(new Event('selectionchange'));
      return 1;
    })()`);
    await sleep(200);
    await cdp.ev(`(function(){
      var b = document.querySelector('.-fmt-btn[data-fmt="bold"]');
      if (b) b.click();
      return 1;
    })()`);
    await sleep(300);
  },

  // ⑤ paste —— 粘贴文本
  paste: async () => {
    await setMode('preview');
    await cdp.ev(`(function(){
      var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      var target = null;
      for (var i=0;i<els.length;i++){
        var c = String(els[i].className||'');
        if (c.indexOf('-code-block')<0 && c.indexOf('-table')<0 && c.indexOf('-math-block')<0 &&
            c.indexOf('-mermaid')<0 && c.indexOf('-blank-block')<0 && c.indexOf('-frontmatter')<0) { target = els[i]; break; }
      }
      if (!target) return 0;
      var r = target.getBoundingClientRect();
      if (r.width<4) return 0;
      target.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, clientX:r.left+20, clientY:r.top+8}));
      target.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, clientX:r.left+20, clientY:r.top+8}));
      return 1;
    })()`);
    await sleep(200);
    await cdp.ev(`(function(){
      try {
        var dt = new DataTransfer();
        dt.setData('text/plain', 'PASTED');
        var ev = new ClipboardEvent('paste', { bubbles:true, cancelable:true, clipboardData: dt });
        var el = document.activeElement || document.getElementById('preview');
        el.dispatchEvent(ev);
        return 1;
      } catch(e){ return 0; }
    })()`);
    await sleep(300);
  },

  // ⑥ find —— 查找
  find: async () => {
    await setMode('preview');
    await cdp.ev(`(function(){
      try {
        var inp = document.querySelector('#find-input, .-find-input, input[placeholder*="查找"]');
        if (inp) {
          inp.value = '第一段';
          inp.dispatchEvent(new Event('input', { bubbles:true }));
          return 1;
        }
        return 0;
      } catch(e){ return 0; }
    })()`);
    await sleep(350);
  },

  // ⑦ save —— 保存到磁盘（dry：只触发一次 syncToDisk 路径）
  save: async () => {
    await setMode('preview');
    await cdp.ev(`(function(){
      try {
        var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
        var target = null;
        for (var i=0;i<els.length;i++){
          var c = String(els[i].className||'');
          if (c.indexOf('-code-block')<0 && c.indexOf('-table')<0 && c.indexOf('-math-block')<0 &&
              c.indexOf('-mermaid')<0 && c.indexOf('-blank-block')<0) { target = els[i]; break; }
        }
        if (target) {
          var r = target.getBoundingClientRect();
          target.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, clientX:r.left+20, clientY:r.top+8}));
          target.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, clientX:r.left+20, clientY:r.top+8}));
        }
        return 1;
      } catch(e){ return 0; }
    })()`);
    await sleep(200);
    await cdp.ev(`(function(){ try { window.MemoriaEditSync.insertText('S'); } catch(e){} return 1; })()`);
    await sleep(400);
    await cdp.key('s', 'KeyS', 2);   // Ctrl+S
    await sleep(600);
  },
};

const results = { schema:'memoria-p5-workload/v2', side, file, repeatPerOp: REPEAT,
                  startedAt: new Date().toISOString(),
                  scriptSha256: crypto.createHash('sha256').update(fs.readFileSync(new URL(import.meta.url))).digest('hex'),
                  argv: process.argv.slice(2), ops: {}, bootHook: boot };

// 安装（在确认 surface 后）
await openDoc();
await cdp.ev(`window.MemoriaSurface.switchTo(${JSON.stringify(side)})`);
await cdp.waitFor(`window.MemoriaSurface.current() === ${JSON.stringify(side)}`, 60000);
await sleep(700);
const inst = await cdp.ev(INSTALL);
results.installed = inst;
console.log('[wl] installed: ' + JSON.stringify(inst));

// ★ task-81：包装完整性**一等产物**。wrapFailed 非空 ⇒ calls 分项存在 "unsupported"，
//   下游不得把缺失/0 读成"零工作量"。（不改变退出码，避免破坏既有流水线；但必须吼出来）
const wrapState = await cdp.ev(`window.__wl && window.__wl.wrapState ? window.__wl.wrapState() : null`);
results.wrapIntegrity = {
  ok: !!(wrapState && wrapState.wrapped && wrapState.wrapped.renderRange === true &&
         wrapState.wrapped.render === true && wrapState.wrapped.renderBlock === true &&
         (wrapState.wrapFailed || []).length === 0),
  wrapped: wrapState ? wrapState.wrapped : null,
  wrapFailed: wrapState ? wrapState.wrapFailed : ['wrapState-unavailable'],
  rendererInstances: wrapState ? wrapState.instances : 0,
  factorySeen: wrapState ? wrapState.factorySeen : false,
  // 运行时布尔值（task-81 验收项：不是"看代码"，是页面里真算出来的）
  renderRangeWrappedBool: wrapState ? wrapState.wrapped.renderRange === true : false,
  callsSemantics: 'number=已包装并计数(0=测到且确实未调用) / "unsupported"=无法包装，禁止当 0 读',
};
console.log('[wl] wrapIntegrity: ' + JSON.stringify(results.wrapIntegrity));
if (!results.wrapIntegrity.ok) {
  console.error('[wl] ⚠⚠ WRAP FAILED：' + JSON.stringify(results.wrapIntegrity.wrapFailed) +
    ' ⇒ calls 中对应分项为 "unsupported"（不是 0）');
}

let sealingTimeouts = 0;   // typeset 未在 5s 内落定的轮次数（如实记录，不掩盖）

for (const [opName, action] of Object.entries(OPS)) {
  const runs = [];
  for (let r = 0; r < REPEAT; r++) {
    // 每次都重置文档状态，保证输入相同
    await openDoc();
    await cdp.ev(`window.MemoriaSurface.switchTo(${JSON.stringify(side)})`);
    await cdp.waitFor(`window.MemoriaSurface.current() === ${JSON.stringify(side)}`, 60000);
    await sleep(500);
    // 诊断依据：`openFile(skipNav)` 后 viewMode 可能仍是 source ⇒ 基于 #preview 的操作会空跑。
    // 尽力切到预览（不抛错，失败也让 action 自己记录 err）。
    await setMode('preview');
    await sleep(200);
    // ★★ task-81 追加缺陷：本文件**从未调用过 W.reset()** ⇒ W.on 永远为 false
    //   ⇒ MutationObserver 直接 return、wrap 的 `if (W.on) inc(...)` 也不计数
    //   ⇒ M1/M2/calls **结构性地恒为 0**（"假零工作量"，与本次要修的 wrap 静默失败同类）。
    //   对比：p5perf_run2.mjs:371 有 `await cdp.ev('window.__wl2.reset()')`，本文件漏了。
    //   必须在 openDoc/setMode 之后、action 之前 reset（reset 会重绑 observer 到当前 #preview）。
    const resetInfo = await cdp.ev(`window.__wl.reset()`);
    await sleep(120);
    let err = null;
    try { await action(); } catch (e) { err = String(e && e.message || e); }
    // ★ 密封性：固定等待 1200ms 让异步排版链落定后**一次性**采集。
    //   不在页面内 await promise（曾因 _mathPending 永不 resolve 导致 Runtime.evaluate 永久挂住）。
    await sleep(1200);
    const c = await cdp.ev(`window.__wl.collect()`);
    runs.push(Object.assign({}, c, { err, reset: resetInfo }));
  }
  // 计数应跨轮恒定；若不恒定说明输入不稳定，如实记录
  const sigOf = (x) => JSON.stringify({ M1: x.M1, M2: x.M2, attrWrites: x.attrWrites,
                                        blocksChanged: x.blocksChanged, calls: x.calls });
  const sig = runs.map(sigOf);
  // 第 1 轮含冷启动开销（首次 parse/render 预热）⇒ 用后续轮次判稳定
  const warmSigs = sig.slice(1);
  const stableWarm = warmSigs.length > 0 && warmSigs.every((x) => x === warmSigs[0]);
  const allStable = sig.every((x) => x === sig[0]);
  results.ops[opName] = {
    runs,
    stable: allStable,          // 含第 1 轮
    stableWarm,                 // 丢弃冷启动后
    coldRoundDiffers: !allStable && stableWarm,
    canonical: stableWarm ? runs[1] : (allStable ? runs[0] : null),
  };
  console.log('[wl] ' + side + '/' + opName + ' stable=' + stableWarm + (allStable ? '' : '(含冷启动差异)') +
    ' M1=' + runs.map((x)=>x.M1).join(',') +
    ' M2=' + runs.map((x)=>x.M2).join(',') +
    ' calls=' + JSON.stringify(runs[0].calls) +
    (stableWarm ? '' : '  ⚠ 暖轮仍不稳定'));
}

results.sealingTimeouts = sealingTimeouts;
results.finishedAt = new Date().toISOString();
if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__WL__' + JSON.stringify({ ok:true, side, out: outPath,
    wrapIntegrityOk: results.wrapIntegrity ? results.wrapIntegrity.ok : null,
    wrapFailed: results.wrapIntegrity ? results.wrapIntegrity.wrapFailed : null }));
}
cdp.close();
setTimeout(() => process.exit(0), 400).unref();
