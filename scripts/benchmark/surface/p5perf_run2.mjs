#!/usr/bin/env node
/**
 * p5perf_run2.mjs —— task-48：工作量计数（A/B 类分离 + 通路自检 + 只装一次）
 *
 * Lead 新判据：
 *   A 类（确定性，必须逐字节一致）：M1/M2/parse/render/renderRange/renderBlock/upsert/
 *                                    insertText/splitParagraph/undo
 *   B 类（竞态，不要求一致，只记录范围）：typeset / flushRepaint
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

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

const INSTALL = fs.readFileSync(new URL('./_wl2_install.js.txt', import.meta.url), 'utf8');

/* ═══════════════════════════════════════════════════════════════════════════
 * task-82 · BOOT_HOOK：在**任何页面脚本执行之前**挂钩 render-core 工厂
 *
 * 为什么必须由本文件注入（时机问题，实测）：
 *   · `window.MemoriaRenderer` 已在 P6d 删除（`_wl2_install.js.txt` 旧 wrap 静默 false）；
 *   · 真正在用的是 `MemoriaRenderCore.createRenderCore({})` 返回的**实例**；
 *   · app.js 的 `_rcCore` 是模块内 `let`（闭包私有）⇒ 页面加载完成后**不可达**；
 *   · 本脚本 connect 后就 `awaitMemoriaApp()`（应用已加载完）⇒ 此时再注入已太晚。
 * ⇒ 必须：`Page.enable` → `Page.addScriptToEvaluateOnNewDocument(源)` → `Page.reload`
 *    → 等应用重新就绪 → 再注入 INSTALL 探针。这样 app/新 surface/agent-panel
 *    创建的**每一个** render-core 实例都会被包装。
 *
 * 失败可见：若 CDP 不支持/重载失败 ⇒ 不抛死，而是让 `_wl2_install` 的
 *   `wrapState()` 报 `boot-hook-not-installed` ⇒ `wrapFailed[]` + `calls:"unsupported"`。
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

/** 安装 boot hook 并重载页面。返回结构化结果（失败也如实返回，不吞）。 */
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
    for (let i = 0; i < 150; i++) {
      if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break;
      await sleep(200);
    }
    out.hookInstalledInPage = await cdp.ev('!!(window.__wlCore && window.__wlCore.installed)');
  } catch (e) {
    out.error = String((e && e.message) || e);
  }
  return out;
}


/* ══ KB 完整性守卫（task-55）：测试开始前 + 结束后校验冻结语料 sha ══
 *   ★ 真实缺陷：2026-10-21 22:57:54 测试的自动保存把 ZZZ 写进冻结语料的
 *     03-block-boundaries.md（778B→814B，LF→CRLF），导致 p5_perf 基线失效。
 *   ⇒ 冻结语料只读；写类操作一律在副本上；每次真机测试前后校验 sha。 */
const SURFACE_DIR = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const GUARD_PY = path.join(SURFACE_DIR, '_kb_guard.py');

/** 建**副本** KB（冻结语料只读，整场测量用副本）。 */
function prepareWorkKb(frozen) {
  const py = [
    'import sys',
    'sys.path.insert(0, sys.argv[1])',
    'from _kb_guard import make_work_copy',
    'print(make_work_copy(sys.argv[2], label=sys.argv[3]))',
  ].join('\n');
  const out = execFileSync('python', ['-X', 'utf8', '-c', py, SURFACE_DIR, path.resolve(frozen), WORK_KB_LABEL],
    { encoding: 'utf8', timeout: 180000 });
  return String(out).trim().split(/\r?\n/).pop();
}

function kbGuardSnapshot(kbDir, outJson) {
  try {
    const out = execFileSync('python', ['-X', 'utf8', GUARD_PY, '--kb', kbDir, '--claim', '--manifest', outJson],
      { encoding: 'utf8', timeout: 120000 });
    return { ok: true, out: String(out).trim() };
  } catch (e) {
    return { ok: false, err: String(e && e.message || e) };
  }
}
function kbGuardVerify(kbDir, beforeJson) {
  try {
    const out = execFileSync('python', ['-X', 'utf8', GUARD_PY, '--kb', kbDir, '--verify', beforeJson],
      { encoding: 'utf8', timeout: 120000 });
    return { ok: true, verdict: 'green', out: String(out).trim() };
  } catch (e) {
    const stderr = String((e && e.stderr) || '');
    const stdout = String((e && e.stdout) || '');
    return { ok: false, verdict: 'RED', err: String(e && e.message || e), detail: (stdout + stderr).trim() };
  }
}

const port = Number(process.argv[2] || 9500);
const side = process.argv[3] || 'new';
const outPath = process.argv[4] || '';
const REPEAT = Number(process.argv[5] || 3);

const DEFAULT_DOC = 'corpus/03-block-boundaries.md';
const KP_DOC = 'corpus/06-links-and-kp.md';

const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
const cdp = await CDP.connect(page.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
// ★ task-82：先装 boot hook 再 reload —— 之后 app 创建的 render-core 实例才可包
//   （不装 ⇒ _wl2_install 的 wrapState 会报 boot-hook-not-installed，
//     calls 分项变 "unsupported"，**不会**静默成 0）
const boot = await installBootHook();
console.log('[wl2] bootHook: ' + JSON.stringify(boot));
if (!boot.hookAdded || !boot.reloaded) {
  console.error('[wl2] ⚠⚠ WRAP FAILED（boot hook 未生效）：calls 的 render* 分项将为 "unsupported"，**不得**读成 0。原因：' +
    JSON.stringify(boot.error));
}
for (let i = 0; i < 150; i++) {
  if (await cdp.ev('!!window.MemoriaApp && !!window.MemoriaSurface')) break;
  await sleep(200);
}

async function openFile(f) {
  await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(f)}, { skipNav: true })`);
  await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(f)} && !!window.state.doc`, 40000);
  await sleep(500);
}
async function doSetMode(mode) {
  for (let i = 0; i < 12; i++) {
    const cur = await cdp.ev('(window.state||{}).viewMode || null');
    if (cur === mode) return true;
    await cdp.ev(`(function(){ var b=document.querySelector('.-view-btn[data-view="${mode}"]'); if(b){try{b.click();}catch(e){}} return 1; })()`);
    await sleep(250);
  }
  return (await cdp.ev('(window.state||{}).viewMode || null')) === mode;
}
async function waitPreviewReady(minBlocks) {
  const ok = await doSetMode('preview');
  if (!ok) return { ok: false, reason: 'setmode-failed', viewMode: await cdp.ev('(window.state||{}).viewMode') };
  for (let i = 0; i < 40; i++) {
    const st = await cdp.ev(`(function(){ return { blocks: document.querySelectorAll('#preview .-src-block').length, viewMode:(window.state||{}).viewMode }; })()`);
    if (st && st.blocks >= (minBlocks || 1) && st.viewMode === 'preview') return { ok: true, ...st };
    await sleep(150);
  }
  const st2 = await cdp.ev(`(function(){ return { blocks: document.querySelectorAll('#preview .-src-block').length, viewMode:(window.state||{}).viewMode }; })()`);
  return { ok: false, reason: 'preview-not-ready', ...st2 };
}
async function caret(bi) {
  const loc = await cdp.ev(`(function(){
    var pv=document.getElementById('preview'); if(!pv) return {ok:false};
    var b=pv.querySelectorAll('.-src-block')[${bi}]; if(!b) return {ok:false};
    b.scrollIntoView({block:'center'});
    var r=b.getBoundingClientRect(); if(r.width<4) return {ok:false};
    return {ok:true, x:Math.round(r.left+Math.min(30,r.width/2)), y:Math.round(r.top+r.height/2)};
  })()`);
  if (!loc || !loc.ok) return false;
  await sleep(80);
  await cdp.click(loc.x, loc.y);
  await sleep(150);
  return true;
}
async function setSurface(s) {
  await cdp.ev(`window.MemoriaSurface.switchTo(${JSON.stringify(s)})`);
  await cdp.waitFor(`window.MemoriaSurface.current() === ${JSON.stringify(s)}`, 60000);
  await sleep(400);
  return await cdp.ev('window.MemoriaSurface.current()');
}

const OPS = {
  typing: { doc: DEFAULT_DOC, run: async () => { await caret(4); await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', text: 'q', key: 'q' }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'q' }); } },
  structEdit: { doc: DEFAULT_DOC, run: async () => { await caret(4); await cdp.ev(`(function(){ try{window.MemoriaEditSync.splitParagraph();}catch(e){} return 1; })()`); } },
  undo: { doc: DEFAULT_DOC, run: async () => { await caret(4); await cdp.ev(`(function(){ try{window.MemoriaEditSync.insertText('u');}catch(e){} return 1; })()`); await sleep(400); await cdp.ev(`(function(){ try{window.MemoriaEditSync.undo();}catch(e){} return 1; })()`); } },
  viewSwitch: { doc: DEFAULT_DOC, run: async () => { await doSetMode('source'); await doSetMode('preview'); } },
  open: { doc: DEFAULT_DOC, run: async () => { await openFile('corpus/01-ime-zh.md'); await sleep(400); await openFile(DEFAULT_DOC); await sleep(500); } },
  scroll: { doc: DEFAULT_DOC, run: async () => { await cdp.ev(`(function(){ var pv=document.getElementById('preview'); if(!pv) return 0; var el=pv.scrollHeight>pv.clientHeight?pv:(document.scrollingElement||document.documentElement); el.scrollTop=Math.min(el.scrollHeight,el.scrollTop+1200); return el.scrollTop; })()`); } },
  tabSwitch: { doc: DEFAULT_DOC, run: async () => { await openFile('corpus/01-ime-zh.md'); await sleep(400); await openFile(DEFAULT_DOC); await sleep(500); } },

  // KP 悬停：打开含 KP 的文档；若无 KP 项则探测 KP 面板实际结构
  kpHover: { doc: KP_DOC, run: async () => {
      const probe = await cdp.ev(`(function(){
        var out = { kpList: !!document.getElementById('kp-list'), items: document.querySelectorAll('#kp-list .-kp-item').length,
                    allKp: document.querySelectorAll('[class*="kp"]').length, ids: [] };
        document.querySelectorAll('[id*="kp"],[class*="kp"]').forEach(function(e,i){ if(i<10) out.ids.push({id:e.id, cls:String(e.className||'').slice(0,40)}); });
        return out;
      })()`);
      if (!probe || probe.items === 0) throw new Error('kpHover:no-kp-item ' + JSON.stringify(probe));
      const loc = await cdp.ev(`(function(){
        var it=document.querySelector('#kp-list .-kp-item');
        it.scrollIntoView({block:'center'});
        var r=it.getBoundingClientRect();
        return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
      })()`);
      await cdp.mouseMove(loc.x - 8, loc.y);
      await sleep(60);
      await cdp.mouseMove(loc.x, loc.y);
      await sleep(320);
    } },

  // 预览真实拖选
  select: { doc: DEFAULT_DOC, run: async () => {
      const loc = await cdp.ev(`(function(){
        var bs=document.querySelectorAll('#preview .-src-block');
        var el=null;
        for(var i=0;i<bs.length;i++){ var t=(bs[i].textContent||'').trim();
          if(t.length>8 && String(bs[i].className||'').indexOf('-blank-block')<0){ el=bs[i]; break; } }
        if(!el) return {ok:false};
        el.scrollIntoView({block:'center'});
        var r=el.getBoundingClientRect();
        return {ok:true,x1:Math.round(r.left+6),x2:Math.round(r.left+Math.min(80,r.width-6)),y:Math.round(r.top+r.height/2)};
      })()`);
      if (!loc || !loc.ok) throw new Error('select:no-block');
      await cdp.send('Input.dispatchMouseEvent', { type:'mousePressed', x:loc.x1, y:loc.y, button:'left', clickCount:1 });
      await cdp.send('Input.dispatchMouseEvent', { type:'mouseMoved', x:loc.x2, y:loc.y, button:'left' });
      await cdp.send('Input.dispatchMouseEvent', { type:'mouseReleased', x:loc.x2, y:loc.y, button:'left', clickCount:1 });
      await sleep(320);
      // ★ 通路自检：必须真的选中了文本，否则"0 计数"是无效测量
      const sel = await cdp.ev(`(function(){ var s=window.getSelection(); return { text:String(s||''), collapsed: s?s.isCollapsed:null, ranges: s?s.rangeCount:0 }; })()`);
      if (!sel || sel.collapsed || !sel.text) throw new Error('select-no-selection ' + JSON.stringify(sel));
      _lastSel = sel;
    } },

  format: { doc: DEFAULT_DOC, run: async () => {
      await caret(4);
      await cdp.ev(`(function(){
        var els=Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
        for(var i=0;i<els.length;i++){
          var c=String(els[i].className||'');
          if(c.indexOf('-code-block')<0&&c.indexOf('-table')<0&&c.indexOf('-math-block')<0&&c.indexOf('-mermaid')<0&&c.indexOf('-blank-block')<0){
            var w=document.createTreeWalker(els[i],NodeFilter.SHOW_TEXT,null); var n=w.nextNode();
            if(n){ var r=document.createRange(); r.setStart(n,0); r.setEnd(n,Math.min(3,n.nodeValue.length));
              var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
              document.dispatchEvent(new Event('selectionchange')); }
            break;
          }
        }
        return 1;
      })()`);
      await sleep(220);
      await cdp.ev(`(function(){ var b=document.querySelector('.-fmt-btn[data-fmt="bold"]'); if(b) b.click(); return 1; })()`);
      await sleep(320);
    } },

  paste: { doc: DEFAULT_DOC, run: async () => {
      await caret(4);
      const r = await cdp.ev(`(function(){
        try {
          var dt = new DataTransfer(); dt.setData('text/plain','PASTED');
          var target = document.activeElement || document.getElementById('preview');
          var ev = new ClipboardEvent('paste', { bubbles:true, cancelable:true, clipboardData: dt });
          var notCancelled = target.dispatchEvent(ev);
          return { dispatched:true, notCancelled: notCancelled };
        } catch(e){ return { dispatched:false, err:String(e.message) }; }
      })()`);
      await sleep(400);
      if (r && r.dispatched && r.notCancelled === false) return;   // 应用已处理
      const ins = await cdp.ev(`(function(){ try { return !!window.MemoriaEditSync.insertText('PASTED'); } catch(e){ return false; } })()`);
      if (!ins) throw new Error('paste:both-paths-failed');
    } },

  find: { doc: DEFAULT_DOC, run: async () => {
      await sleep(200);
      // 诊断实测：真实查找/搜索框是 #toolbar-search（placeholder「搜索知识点、标签…」）
      const r = await cdp.ev(`(function(){
        var cands=['#toolbar-search','.-toolbar-search','#find-input','.-find-input','input[placeholder*="搜索"]','input[placeholder*="查找"]'];
        for(var i=0;i<cands.length;i++){ var el=document.querySelector(cands[i]);
          if(el){ var rr=el.getBoundingClientRect(); if(rr.width>10&&rr.height>10) return {ok:true,sel:cands[i]}; } }
        var ins=Array.prototype.slice.call(document.querySelectorAll('input'));
        var vis=ins.filter(function(e){var r=e.getBoundingClientRect();return r.width>10&&r.height>10;});
        return {ok:false, inputs: vis.map(function(e){return {id:e.id,cls:String(e.className||'').slice(0,30),ph:e.placeholder};})};
      })()`);
      if (!r || !r.ok) throw new Error('find:no-input ' + JSON.stringify(r));
      await cdp.ev(`(function(){
        var el=document.querySelector(${JSON.stringify(r.sel)}); if(!el) return 0;
        el.focus(); el.value='第一段';
        el.dispatchEvent(new Event('input',{bubbles:true}));
        el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));
        return 1;
      })()`);
      await sleep(420);
    } },

  save: { doc: DEFAULT_DOC, run: async () => {
      await caret(4);
      await cdp.ev(`(function(){ try{window.MemoriaEditSync.insertText('Z');}catch(e){} return 1; })()`);
      await sleep(400);
      await cdp.ev(`(async function(){
        var p=window.state&&window.state._mathPending; if(!p) return 0;
        await Promise.race([Promise.resolve(p).then(function(){},function(){}), new Promise(function(r){setTimeout(r,2000);})]);
        return 1;
      })()`);
      await cdp.send('Input.dispatchKeyEvent', { type:'keyDown', key:'s', code:'KeyS', modifiers:2, windowsVirtualKeyCode:83 });
      await cdp.send('Input.dispatchKeyEvent', { type:'keyUp', key:'s', code:'KeyS', modifiers:2, windowsVirtualKeyCode:83 });
      await sleep(650);
    } },
};

let _lastSel = null;

/* ══ 冻结语料只读策略（task-55 硬规则）══════════════════════════════════════
 *   实测：直接用冻结语料跑 save/paste 等写类操作 ⇒ 守卫当场判红
 *        （03-block-boundaries.md 35e441de/778B → c1a6f193/814B）。
 *   根因：应用的**自动保存**把测试改动写回 MEMORIA_KB。
 *   ⇒ 本探针**整场在副本上跑**；冻结语料只在前后做 sha 校验（证明没被碰）。
 *      副本路径记录在产物的 kbWorkCopy 字段。
 * ═════════════════════════════════════════════════════════════════════════ */
const KB_DIR = process.env.MEMORIA_KB || 'artifacts/_p5_matrix_kb';
// ★ 冻结语料必须**独立于 MEMORIA_KB**：运行时可把 MEMORIA_KB 指向副本（写类测试），
//   但守卫要盯的始终是**不可变**的冻结语料。若二者共用 MEMORIA_KB，
//   守卫就会盯着副本 ⇒ 副本被写 ⇒ 假红（task-55 实测踩到）。
const FROZEN_KB_DIR = process.env.P5PERF_FROZEN_KB || 'artifacts/_p5_matrix_kb';
const USE_WORK_COPY = process.env.P5PERF_NO_WORKCOPY !== '1';
const WORK_KB_LABEL = process.env.P5PERF_WORKKB_LABEL || ('p5perf_' + (process.env.P5PERF_RUN_TAG || 'run'));
const results = {
  schema: 'memoria-p5-workload2/v1', side, repeatPerOp: REPEAT, mode: 'realapp',
  bootHook: boot,          // task-82：boot hook 安装结果（失败也如实记录）
  kb: KB_DIR,
  kbWorkCopy: null,        // 运行时填入（整场测量用的副本）
  kbPolicy: USE_WORK_COPY ? 'measure-on-copy' : 'DIAG-measure-on-frozen',
  kbSha256: (() => {
    try {
      const anchor = path.join(KB_DIR, 'scale/scale-5k.md');
      return crypto.createHash('sha256').update(fs.readFileSync(anchor)).digest('hex');
    } catch { return null; }
  })(),
  concurrencyHint: (process.env.P5PERF_CONCURRENCY || null),
  scriptSha256: crypto.createHash('sha256').update(fs.readFileSync(new URL(import.meta.url))).digest('hex'),
  argv: process.argv.slice(2), startedAt: new Date().toISOString(), ops: {},
};

/* ⓪-a KB 完整性守卫：**冻结语料**前快照（之后不再碰它） */
// ★ 前快照文件名必须**唯一**：固定名会被上一轮 run 覆盖，
//   导致本轮"前快照"实际是旧污染态 ⇒ 守卫误判红（task-55 实测踩到）。
const guardBefore = path.join(SURFACE_DIR, '_kbguard_before_' + side + '_' + process.pid + '_' + Date.now() + '.json');
const gb = kbGuardSnapshot(FROZEN_KB_DIR, guardBefore);
results.kbGuardBefore = gb;
console.log('[kb-guard] 冻结语料前快照: ' + (gb.ok ? 'OK' : 'FAIL ' + gb.err));

/* ⓪-b 整场测量改用**副本**（冻结语料只读） */
if (USE_WORK_COPY) {
  try {
    const work = prepareWorkKb(FROZEN_KB_DIR);
    results.kbWorkCopy = work;
    await cdp.ev(`window.MemoriaApp.openFile('', {skipNav:true})`).catch(() => {});
    // 通过应用 API 切换 KB 根（若可用），否则依赖环境变量在启动时生效
    const switched = await cdp.ev(`(function(){
      try {
        if (window.MemoriaApp && window.MemoriaApp.setKbRoot) { window.MemoriaApp.setKbRoot(${JSON.stringify('__WORK__')}); return 'setKbRoot'; }
      } catch(e){}
      return 'env-only';
    })()`.replace('__WORK__', work.replace(/\\/g, '\\\\')));
    results.kbWorkSwitch = switched;
    console.log('[kb-guard] 副本 KB: ' + work + '  (switch=' + switched + ')');
  } catch (e) {
    console.log('[kb-guard] ⚠️ 副本创建失败: ' + String(e && e.message || e));
  }
}

/* ① 通路自检 */
await setSurface(side);
await openFile(DEFAULT_DOC);
const pathReady = await waitPreviewReady(1);
const inst = await cdp.ev(INSTALL);
results.pathCheck = {
  installOk: !!(inst && inst.ok),
  wrapped: inst && inst.wrapped,
  // task-62：探针可用性诊断（P6d 删 MemoriaRenderer ⇒ render/renderRange/renderBlock 不可包装）
  probeAvailability: inst && inst.probeAvailability,
  previewReady: pathReady,
  viewMode: await cdp.ev('(window.state||{}).viewMode'),
  previewBlocks: await cdp.ev(`document.querySelectorAll('#preview .-src-block').length`),
  surfaceCurrent: await cdp.ev('window.MemoriaSurface.current()'),
};
console.log('[wl2] 通路: viewMode=' + results.pathCheck.viewMode +
  ' blocks=' + results.pathCheck.previewBlocks +
  ' installOk=' + results.pathCheck.installOk +
  ' surface=' + results.pathCheck.surfaceCurrent);
if (results.pathCheck.probeAvailability) {
  const pa = results.pathCheck.probeAvailability;
  console.log('[wl2] 探针可用性: MemoriaRenderer=' + pa.MemoriaRendererExists +
    ' 不可包装=[' + (pa.unwrappable || []).join(',') + ']');
  if ((pa.unwrappable || []).length) {
    console.log('[wl2] ⚠️ ' + pa.note);
  }
}
if (!pathReady.ok) console.log('[wl2] ⚠️ 预览未就绪 ' + JSON.stringify(pathReady));

/* ①-b task-82：包装完整性 —— **一等产物**（不是"看代码推断"）
 *   判定：render-range / render / render-block 三个关键实例方法必须真的被包上，
 *         且 wrapFailed 为空。失败 ⇒ calls 对应分项为 "unsupported"，禁止当 0 读。 */
const wrapState = await cdp.ev('window.__wl2 && window.__wl2.wrapState ? window.__wl2.wrapState() : null');
results.wrapIntegrity = {
  ok: !!(wrapState && wrapState.wrapped && wrapState.wrapped.renderRange === true &&
         wrapState.wrapped.render === true && wrapState.wrapped.renderBlock === true &&
         (wrapState.wrapFailed || []).length === 0),
  wrapped: wrapState ? wrapState.wrapped : null,
  wrapFailed: wrapState ? wrapState.wrapFailed : ['wrapState-unavailable'],
  rendererInstances: wrapState ? wrapState.instances : 0,
  factorySeen: wrapState ? wrapState.factorySeen : false,
  // 运行时布尔值（验收项：贴这个，不是贴代码）
  renderRangeWrappedBool: wrapState ? wrapState.wrapped.renderRange === true : false,
  callsSemantics: 'number=已包装并计数(0=测到且确实未调用) / "unsupported"=无法包装，禁止当 0 读',
};
console.log('[wl2] wrapIntegrity: ' + JSON.stringify(results.wrapIntegrity));
if (!results.wrapIntegrity.ok) {
  console.error('[wl2] ⚠⚠ WRAP FAILED：' + JSON.stringify(results.wrapIntegrity.wrapFailed) +
    ' ⇒ calls 中对应分项为 "unsupported"（不是 0）');
}

/* ② 逐 op（探针只装一次）*/
for (const [opName, def] of Object.entries(OPS)) {
  const runs = [];
  for (let r = 0; r < REPEAT; r++) {
    await openFile(def.doc);
    const ready = await waitPreviewReady(1);
    if (!ready.ok) { runs.push({ err: 'precondition:' + JSON.stringify(ready) }); continue; }
    await cdp.ev('window.__wl2.reset()');
    let err = null;
    try { await def.run(); } catch (e) { err = String(e && e.message || e); }
    await sleep(1000);
    const c = await cdp.ev('window.__wl2.collect()');
    runs.push({ A: c.A, B: c.B, err });
  }
  const sigA = (x) => (x && x.A) ? JSON.stringify(x.A) : 'ERR:' + (x && x.err);
  const sigs = runs.map(sigA);
  const warm = sigs.slice(1);
  const stableAWarm = warm.length > 0 && warm.every((s) => s === warm[0]);
  const stableAAll = sigs.every((s) => s === sigs[0]);
  const bRange = {};
  for (const key of ['typeset', 'flushRepaint']) {
    const vals = runs.map((x) => (x && x.B) ? x.B[key] : null).filter((v) => v != null);
    bRange[key] = vals.length ? { values: vals, min: Math.min(...vals), max: Math.max(...vals) } : null;
  }
  results.ops[opName] = {
    doc: def.doc, runs, A_stableWarm: stableAWarm, A_stableAll: stableAAll, B_range: bRange,
    canonicalA: stableAWarm ? runs[1].A : (stableAAll ? runs[0].A : null),
    selectionProbe: opName === 'select' ? _lastSel : undefined,
    errors: runs.map((x) => x.err).filter(Boolean),
  };
  const ca = results.ops[opName].canonicalA;
  console.log('[wl2] ' + side + '/' + opName + ' A_stableWarm=' + stableAWarm +
    ' ' + (ca ? 'A=' + JSON.stringify({ M1: ca.M1, M2: ca.M2, calls: ca.calls }) : 'UNSTABLE') +
    ' B=' + JSON.stringify(bRange) +
    (results.ops[opName].errors.length ? ' ERR=' + results.ops[opName].errors[0].slice(0, 90) : ''));
}

/* ②-b task-82：**度量存活自检** —— 防"整套指标恒零但没人发现"
 *
 *   同类历史缺陷（task-81 实测抓到）：`p5perf_workload.mjs` 从未调用 `W.reset()`
 *   ⇒ `W.on` 恒 false ⇒ MutationObserver 直接 return、wrap 的 `if (W.on)` 也不计数
 *   ⇒ M1/M2/calls **结构性恒 0**，而产物里看不出任何异常（"假零工作量"）。
 *
 *   判据（保守，避免把"确实没工作量"误判成"度量死了"）：
 *     · 任一 op 的 canonicalA.M1 > 0            ⇒ 度量活着（DOM 变异有计数）
 *     · 或任一 op 的 calls 里存在数值 > 0 的分项 ⇒ 度量活着（函数调用有计数）
 *   两者皆不成立 ⇒ metricsAlive=false ⇒ stderr 吼 + 产物字段（不改退出码，避免破坏上层）。
 */
const _allOps = Object.values(results.ops);
const _maxM1 = Math.max(0, ..._allOps.map((o) => (o.canonicalA && typeof o.canonicalA.M1 === 'number' ? o.canonicalA.M1 : 0)));
let _maxCall = 0;
for (const o of _allOps) {
  const cs = (o.canonicalA && o.canonicalA.calls) || {};
  for (const k of Object.keys(cs)) {
    const v = cs[k];
    if (typeof v === 'number' && v > _maxCall) _maxCall = v;
  }
}
const _unsupported = [...new Set(_allOps.flatMap((o) => {
  const cs = (o.canonicalA && o.canonicalA.calls) || {};
  return Object.keys(cs).filter((k) => cs[k] === 'unsupported');
}))];
results.metricsIntegrity = {
  ok: (_maxM1 > 0 || _maxCall > 0),
  maxM1AcrossOps: _maxM1,
  maxCallCountAcrossOps: _maxCall,
  unsupportedCallLabels: _unsupported,
  note: 'ok=false ⇒ 整套指标没有任何非零计数（reset 未生效/探针未装/页面空跑）⇒ 本产物不可用于工作量判断',
};
console.log('[wl2] metricsIntegrity: ' + JSON.stringify(results.metricsIntegrity));
if (!results.metricsIntegrity.ok) {
  console.error('[wl2] ⚠⚠ METRICS DEAD：所有 op 的 M1 与 calls 计数全为 0 ⇒ 本次工作量数据**无效**，不得当"零工作量"读');
}


/* ⓪ KB 完整性守卫：测试结束后校验（不一致 ⇒ 判红并点名） */
const gv = kbGuardVerify(FROZEN_KB_DIR, guardBefore);
results.kbGuardAfter = gv;
console.log('[kb-guard] 后校验: ' + gv.verdict + (gv.ok ? ' ✅' : ' ❌ ' + (gv.detail || gv.err)));
if (!gv.ok) {
  console.error('[kb-guard] ❌ 冻结语料在本次测试中被写入 —— 这是测试缺陷！');
  console.error(gv.detail || gv.err);
}

results.finishedAt = new Date().toISOString();
if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log('__WL2__' + JSON.stringify({ ok: true, side, out: outPath,
    wrapIntegrityOk: results.wrapIntegrity ? results.wrapIntegrity.ok : null,
    wrapFailed: results.wrapIntegrity ? results.wrapIntegrity.wrapFailed : null,
    renderRangeWrappedBool: results.wrapIntegrity ? results.wrapIntegrity.renderRangeWrappedBool : null,
    metricsAlive: results.metricsIntegrity ? results.metricsIntegrity.ok : null }));
}
cdp.close();
// KB 守卫红 ⇒ 退出码 1（让上层判红）
setTimeout(() => process.exit(gv.ok ? 0 : 1), 400).unref();
