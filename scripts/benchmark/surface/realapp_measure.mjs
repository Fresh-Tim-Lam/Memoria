#!/usr/bin/env node
/**
 * realapp_measure.mjs —— **真机应用**三项性能指标的页面内埋点驱动
 *
 * 口径契约：docs/design/realapp-measurement-protocol.md
 * 前提：应用已按协议 §2 启动（WebView2 暴露 CDP）；本脚本**不启动**应用，只 attach。
 *
 * 与无头探针（cdp.mjs）的关键差别 —— **读数与输入来源无关**：
 *   · 无头探针在 Node 侧用 `Date.now()` 计「派发 → 轮询看到完成」，含「CDP 往返 + 轮询间隔」，
 *     这部分是**测量装置**的开销，不是应用开销 ⇒ 合成输入与真人输入的读数天然不可比。
 *   · 本脚本把计时**全部埋在页面里**（`performance.now()`），并按「输入源」分开记录同一指标：
 *       - 自动化（`--driver auto`）：CDP Input 域派发真实事件（isTrusted=true）
 *       - 人工（`--driver manual`）：**不派发任何输入**，只开启埋点、等操作者做完、读表
 *     两种来源量的是**同一段页面内代码路径** ⇒ 差值 = 输入通道差异 + 人为误差，可量化。
 *
 * 三项指标（协议 §4）：
 *   B  `open_render_ms`   首开 → 块渲染完成 + 公式排版完成
 *   A  `key_to_source_ms` 按键（受信任输入）→ 真源落定
 *   C  `tab_switch_ms`    A→B→A 切页签，回到 A 可见可用
 *
 * 用法：
 *   node scripts/benchmark/surface/realapp_measure.mjs --port 9500 --driver auto \
 *        --kb-compare --file-a scale/scale-5k.md --file-b corpus/01-ime-zh.md --out raw.json
 *   node scripts/benchmark/surface/realapp_measure.mjs --port 9500 --driver manual --stage B
 *   node scripts/benchmark/surface/realapp_measure.mjs --port 9500 --driver manual --read
 */

import fs from 'node:fs';
import path from 'node:path';
import { findAppTarget, waitAppReady } from './realapp_probe.mjs';

// ─────────────────────────────────────────────────────────────────────────────
// 默认值与判据（必须与 docs/design/realapp-measurement-protocol.md §6 一致）
// ─────────────────────────────────────────────────────────────────────────────
export const REALAPP_DEFAULTS = {
  budgetOpenRenderMs: 3000,     // B 预算（首开→块+公式排版完成）
  budgetKeyToSourceMs: 16,      // A 预算（与 view-surface-contract §3.3 C9 同口径）
  budgetTabSwitchMs: 800,       // C 预算（A→B→A 回到 A 可见）
  noise: { maxIqrOverMedian: 0.25, maxP95OverMedian: 1.60, minSamples: 5 },
};

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) {
      const k = t.slice(2);
      const nxt = argv[i + 1];
      if (nxt && !nxt.startsWith('--')) { a[k] = nxt; i++; } else { a[k] = true; }
    } else a._.push(t);
  }
  return a;
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function httpJson(url, timeoutMs = 3000) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    return await r.json();
  } finally { clearTimeout(to); }
}

class CDP {
  constructor(ws) {
    this.ws = ws;
    this._id = 0;
    this._pending = new Map();
    ws.addEventListener('message', (ev) => this._onMessage(ev.data));
  }
  static connect(wsUrl) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl);
      const to = setTimeout(() => reject(new Error('CDP WebSocket 连接超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); resolve(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); reject(new Error('CDP 连接失败: ' + wsUrl)); });
    });
  }
  _onMessage(data) {
    let msg;
    try { msg = JSON.parse(typeof data === 'string' ? data : String(data)); } catch { return; }
    if (msg.id == null) return;
    const p = this._pending.get(msg.id);
    if (!p) return;
    this._pending.delete(msg.id);
    if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
    else p.resolve(msg.result);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this._id;
      this._pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async evalJS(expression, { awaitPromise = true } = {}) {
    const r = await this.send('Runtime.evaluate', { expression, awaitPromise, returnByValue: true, userGesture: true });
    if (r && r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error('evalJS 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]);
    }
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expression, { timeout = 60000, interval = 100, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) {
      let v;
      try { v = await this.evalJS(expression); } catch { v = false; }
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '') + ': ' + expression);
      await sleep(interval);
    }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

// ─────────────────────────────────────────────────────────────────────────────
// 页面内埋点（整体 stringify 后在页面 eval；闭包内只用页面全局）
//
// 设计要点（协议 §3）：
//   · 全部时间戳用页面 `performance.now()` ⇒ 与输入来源无关；
//   · 三个指标各自是**状态机**，开始/结束都发生在页面内；
//   · `open` 的完成条件是**块数 ≥ minBlocks 且 mjx-container 数连续 3 次采样不变**
//     ⇒ 「公式排版完成」是**真等到了**，不是等一个固定 sleep；
//   · 只读：不改任何应用状态，只往 `window.__ram` 写自己的记录。
// ─────────────────────────────────────────────────────────────────────────────
function INSTALL() {
  // 版本守卫：应用页面上可能残留**上一次**安装的旧版埋点（本脚本被反复运行时）。
  // 旧版没有新方法 ⇒ 必须重新安装，不能早退。
  if (window.__ram && window.__ram.installed && window.__ram.vi === 4) return window.__ram;
  window.__ram = null;
  var R = window.__ram = {
    installed: true,
    vi: 4,            // instrumentation 版本；改了 INSTALL 就 +1
    v: 1,
    marks: {},        // 手动打点：{ name: t }
    open: null,
    key: null,
    tab: null,
    log: [],
  };
  function now() { return performance.now(); }
  function rec(kind, obj) { R.log.push({ kind: kind, t: now(), ...obj }); }

  R.mark = function (name) { R.marks[name] = now(); return R.marks[name]; };

  // ── B：首开 → 块 + 公式排版完成 ────────────────────────────────────────
  // 完成判据：blocks >= minBlocks 且 (mjxCount 连续 3 次采样相同)
  R.startOpen = function (label, opts) {
    opts = opts || {};
    var minBlocks = opts.minBlocks || 5;
    var sampleMs = opts.sampleMs || 60;
    var graceMs = opts.graceMs || 30000;
    var t0 = now();
    var st = {
      label: label || null, t0: t0, minBlocks: minBlocks,
      done: false, blocks: 0, mjx: 0, loading: true,
      blocksReadyMs: null, typesetReadyMs: null, totalMs: null,
      typesetStable: false, timedOut: false, samples: [],
    };
    R.open = st;
    // ── 完成判据（协议 §4-B，务必读）──────────────────────────────────────
    // 实测（真机，scale-5k，3111 块 / 270 个 mjx-container）：
    //   块在 t≈0.1ms 就 ≥minBlocks —— 但那是**上一份文档**的旧块，尚未被清空；
    //   若用「3 次采样 mjx 数不变」当就绪，会在**替换刚开始**时误判「已完成」。
    // 完成条件 = 以下全部：
    //   ① 文档身份已是目标文件（window.state.currentPath === expectPath）；
    //   ② **公式排版队列已清空** —— 用应用自己的 `state._mathPending`（MathJax 排版链的末尾 Promise），
    //      见 app.js `queuePreviewMathTypeset`：它把每轮 typeset 串到 `state._mathPending`。
    //      这是**唯一**与"排版真的做完了"等价的可观测信号（探测 `MathJax.startup.document.state()`
    //      在 v3 SVG 输出下恒不返回 ready，实测不可用）。
    //   ③ 块数 ≥ minBlocks 且预览不在 loading 态；
    //   ④ 再连续 3 次采样块数与 mjx 数都不变（确认排版后无增量重渲）。
    var mathSettled = false;
    function watchMath() {
      var p = (window.state || {})._mathPending;
      if (!p || typeof p.then !== 'function') { mathSettled = true; return; }
      if (mathSettled) return;
      try { p.then(function () { mathSettled = true; }, function () { mathSettled = true; }); }
      catch (e) { mathSettled = true; }
    }
    // 每轮都重新挂：新的一次渲染会替换 state._mathPending
    function mathIdle() { return mathSettled; }
    var lastN = -1, lastM = -1, stable = 0, blocksAt = 0, sawReal = false;
    var curP = (window.state || {})._mathPending;
    (function armWatch() {
      // 轮询式重挂（每次 tick 检查 _mathPending 是否换了新 Promise）
      if ((window.state || {})._mathPending !== curP || !mathSettled) {
        curP = (window.state || {})._mathPending;
        mathSettled = false;
        watchMath();
      }
    })();
    function tick() {
      if (st.done) return;
      var p = (window.state || {})._mathPending;
      if (p !== curP) { curP = p; mathSettled = false; watchMath(); }
      var pv = document.querySelector('#preview');
      var n = pv ? pv.querySelectorAll('.-src-block').length : 0;
      var m = pv ? pv.querySelectorAll('mjx-container').length : 0;
      var loading = pv ? !!pv.querySelector('.-preview-loading') : true;
      var t = now();
      var curPath = (window.state || {}).currentPath || null;
      var pathOk = !st.expectPath || curPath === st.expectPath;
      st.blocks = n; st.mjx = m; st.loading = loading;
      if (st.samples.length < 60) st.samples.push({ t: +(t - t0).toFixed(2), blocks: n, mjx: m, loading: loading, pathOk: pathOk, mathIdle: mathSettled });
      if (n >= minBlocks && !loading && pathOk) {
        sawReal = true;
        if (!blocksAt) blocksAt = t;
        if (m === lastM && n === lastN && mathSettled) {
          stable++;
          if (stable >= 3) {
            st.done = true; st.typesetStable = true;
            st.blocksReadyMs = +(blocksAt - t0).toFixed(2);
            st.typesetReadyMs = +(t - t0).toFixed(2);
            st.totalMs = +(t - t0).toFixed(2);
            rec('open-done', { label: st.label, ms: st.totalMs, blocks: n, mjx: m });
            return;
          }
        } else { lastM = m; lastN = n; stable = 0; }
        if (t - blocksAt > graceMs) {
          st.done = true; st.typesetStable = false;
          st.blocksReadyMs = +(blocksAt - t0).toFixed(2);
          st.typesetReadyMs = +(t - t0).toFixed(2);
          st.totalMs = +(t - t0).toFixed(2);
          rec('open-grace-out', { label: st.label, ms: st.totalMs, blocks: n, mjx: m });
          return;
        }
      } else { lastM = -1; lastN = -1; stable = 0; blocksAt = 0; }
      if (!sawReal && t - t0 > (opts.hardTimeoutMs || 60000)) {
        st.done = true; st.timedOut = true;
        st.typesetReadyMs = +(t - t0).toFixed(2);
        st.totalMs = +(t - t0).toFixed(2);
        rec('open-timeout', { label: st.label, ms: st.totalMs, blocks: n, mjx: m });
        return;
      }
      setTimeout(tick, sampleMs);
    }
    setTimeout(tick, 0);
    return t0;
  };
  /** 告诉埋点「这次打开的应该是哪个文件」，用于排除旧文档的块。 */
  R.setOpenTarget = function (relPath) { if (R.open) R.open.expectPath = relPath || null; return true; };
  R.openState = function () {
    var s = R.open;
    if (!s) return null;
    return {
      label: s.label, expectPath: s.expectPath || null, done: s.done, blocks: s.blocks, mjx: s.mjx, loading: s.loading,
      blocksReadyMs: s.blocksReadyMs, typesetReadyMs: s.typesetReadyMs,
      totalMs: s.totalMs, typesetStable: s.typesetStable, timedOut: s.timedOut,
      samples: s.samples.slice(0, 20),
    };
  };

  // ── A：按键 → 真源落定 ─────────────────────────────────────────────────
  // 与 cdp.mjs C9 同口径：包 MemoriaEditSync.insertText，记录「到达→返回」。
  // **计时器在被测区间之外**（页面侧插桩，不在 insertText 内）。
  R.startKey = function (opts) {
    opts = opts || {};
    var st = {
      t0: now(), n: 0, keys: [], lastArrive: null, lastSettle: null,
      armed: false, inputChannel: null, errors: [],
    };
    R.key = st;
    var pv = document.getElementById('preview');
    if (!pv) { st.errors.push('no-preview'); return false; }
    var ES = window.MemoriaEditSync;
    if (!ES || typeof ES.insertText !== 'function') { st.errors.push('no-editsync'); return false; }
    if (!st.armed) {
      var orig = ES.insertText;
      st._orig = orig;
      ES.insertText = function () {
        var a = st.lastArrive;
        var t1 = now();
        var r = orig.apply(this, arguments);
        var t2 = now();
        st.n++;
        st.keys.push({
          seq: st.n,
          arriveToReturnMs: a != null ? +(t2 - a).toFixed(3) : null,
          insertMs: +(t2 - t1).toFixed(3),
        });
        st.lastSettle = t2;
        return r;
      };
      st.uninstall = function () { try { ES.insertText = orig; } catch (e) { /* noop */ } };
      st.armed = true;
    }
    pv.addEventListener('beforeinput', function () { st.lastArrive = now(); }, true);
    st.inputChannel = opts.inputChannel || 'unset';
    return true;
  };
  R.resetKey = function () { if (R.key) { R.key.keys = []; R.key.n = 0; } return true; };
  R.keyState = function () {
    var s = R.key;
    if (!s) return null;
    return { n: s.n, keys: s.keys.slice(), inputChannel: s.inputChannel, errors: s.errors.slice(), armed: s.armed };
  };
  R.stopKey = function () { if (R.key && R.key.uninstall) { R.key.uninstall(); R.key.uninstall = null; } return true; };

  // ── C：A→B→A 切页签 ────────────────────────────────────────────────────
  // 与 B 同样的陷阱：t≈0.1ms 时 `#preview` 里还是**上一份文档的旧块**（实测 blocks=16），
  // 此时若只判「blocks>=minBlocks && mode===preview」会立刻假完成（实测 0.1ms）。
  // 故完成条件 = ① currentPath 已是目标文件；② 块数 ≥ minBlocks；③ 不在 loading；
  //            ④ 块数/公式数连续 3 次采样不变；⑤ MathJax 队列（state._mathPending）已清。
  R.startTab = function (label, opts) {
    opts = opts || {};
    var minBlocks = opts.minBlocks || 5;
    var st = {
      label: label || null, t0: now(), done: false, totalMs: null, blocks: 0, mjx: 0,
      timeout: false, expectPath: null, samples: [],
    };
    R.tab = st;
    var graceMs = opts.graceMs || 40000;
    var sampleMs = opts.sampleMs || 50;
    var mathSettled = false, curP = (window.state || {})._mathPending;
    function watch(p) {
      if (!p || typeof p.then !== 'function') { mathSettled = true; return; }
      try { p.then(function () { mathSettled = true; }, function () { mathSettled = true; }); } catch (e) { mathSettled = true; }
    }
    mathSettled = false; watch(curP);
    var lastN = -1, lastM = -1, stable = 0, sawTarget = false;
    function tick() {
      if (st.done) return;
      var p = (window.state || {})._mathPending;
      if (p !== curP) { curP = p; mathSettled = false; watch(p); }
      var pv = document.querySelector('#preview');
      var n = pv ? pv.querySelectorAll('.-src-block').length : 0;
      var m = pv ? pv.querySelectorAll('mjx-container').length : 0;
      var loading = pv ? !!pv.querySelector('.-preview-loading') : true;
      var mode = (window.state || {}).viewMode || null;
      var curPath = (window.state || {}).currentPath || null;
      var pathOk = !st.expectPath || curPath === st.expectPath;
      var t = now();
      st.blocks = n; st.mjx = m;
      if (st.samples.length < 60) st.samples.push({ t: +(t - st.t0).toFixed(2), blocks: n, mjx: m, mode: mode, pathOk: pathOk, mathIdle: mathSettled });
      if (mode === 'preview' && n >= minBlocks && !loading && pathOk) {
        sawTarget = true;
        if (n === lastN && m === lastM && mathSettled) {
          stable++;
          if (stable >= 3) {
            st.done = true;
            st.totalMs = +(now() - st.t0).toFixed(2);
            rec('tab-done', { label: st.label, ms: st.totalMs, blocks: n, mjx: m });
            return;
          }
        } else { lastN = n; lastM = m; stable = 0; }
      } else { lastN = -1; lastM = -1; stable = 0; }
      if (!sawTarget && t - st.t0 > graceMs) {
        st.done = true; st.timeout = true;
        st.totalMs = +(now() - st.t0).toFixed(2);
        rec('tab-timeout', { label: st.label, ms: st.totalMs, blocks: n, mode: mode, pathOk: pathOk });
        return;
      }
      setTimeout(tick, sampleMs);
    }
    setTimeout(tick, 0);
    return true;
  };
  R.setTabTarget = function (relPath) { if (R.tab) R.tab.expectPath = relPath || null; return true; };
  R.tabState = function () {
    var s = R.tab;
    if (!s) return null;
    return {
      label: s.label, expectPath: s.expectPath || null, done: s.done, totalMs: s.totalMs,
      blocks: s.blocks, mjx: s.mjx, timeout: s.timeout, samples: s.samples.slice(0, 20),
    };
  };

  // ── 汇总：一次读全（人工模式就是要人「做完点一下，读一个数」）───────────
  R.dump = function () {
    function stat(arr) {
      var v = arr.filter(function (x) { return typeof x === 'number' && isFinite(x); }).sort(function (a, b) { return a - b; });
      if (!v.length) return null;
      function q(p) { var h = (v.length - 1) * p; var lo = Math.floor(h), hi = Math.ceil(h); return lo === hi ? v[lo] : v[lo] + (v[hi] - v[lo]) * (h - lo); }
      var med = q(0.5);
      return {
        n: v.length, min: v[0], median: med, p95: q(0.95), max: v[v.length - 1],
        q1: q(0.25), q3: q(0.75), iqr: q(0.75) - q(0.25),
        iqrOverMedian: med > 0 ? (q(0.75) - q(0.25)) / med : null,
        p95OverMedian: med > 0 ? q(0.95) / med : null,
      };
    }
    var ks = R.keyState();
    return {
      v: R.v,
      marks: R.marks,
      open: R.openState(),
      tab: R.tabState(),
      key: ks ? {
        n: ks.n, inputChannel: ks.inputChannel, errors: ks.errors,
        arriveToReturn: stat(ks.keys.map(function (k) { return k.arriveToReturnMs; })),
        insertOnly: stat(ks.keys.map(function (k) { return k.insertMs; })),
        keys: ks.keys.slice(0, 200),
      } : null,
      log: R.log.slice(-80),
    };
  };
  return R;
}

// ─────────────────────────────────────────────────────────────────────────────
// 交互原语（复用 interaction.mjs 的口径：全部走 CDP Input 域 ⇒ isTrusted=true）
// ─────────────────────────────────────────────────────────────────────────────
class Ix {
  constructor(cdp) { this.cdp = cdp; }
  async click(x, y) {
    await this.cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none', buttons: 0 });
    await this.cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
    await this.cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 });
  }
  /** 受信任逐字符输入（keyDown 带 text ⇒ 真实 beforeinput）。 */
  async typeText(text) {
    for (const ch of String(text)) {
      const cp = ch.codePointAt(0);
      const isLetter = /[a-zA-Z]/.test(ch);
      const isDigit = /[0-9]/.test(ch);
      const code = isLetter ? 'Key' + ch.toUpperCase() : (isDigit ? 'Digit' + ch : '');
      const vk = isLetter ? ch.toUpperCase().charCodeAt(0) : cp;
      const down = { type: 'keyDown', text: ch, unmodifiedText: ch, key: ch, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
      const up = { type: 'keyUp', key: ch, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
      if (code) { down.code = code; up.code = code; }
      await this.cdp.send('Input.dispatchKeyEvent', down);
      await this.cdp.send('Input.dispatchKeyEvent', up);
    }
  }
  /** IME 组合输入（中文）：imeSetComposition → insertText 提交。 */
  async imeCompose(text, { composeMs = 120 } = {}) {
    await this.cdp.send('Input.imeSetComposition', {
      text: String(text), selectionStart: String(text).length, selectionEnd: String(text).length,
    });
    await sleep(composeMs);
    await this.cdp.send('Input.insertText', { text: String(text) });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 应用侧助手（只读；不改应用状态）
// ─────────────────────────────────────────────────────────────────────────────
async function ensurePreviewView(cdp) {
  const mode = await cdp.evalJS('(window.state||{}).viewMode || null');
  if (mode === 'preview') return 'already';
  const ok = await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b){b.click();return true;}return false;})()`);
  if (!ok) return 'no-button';
  await cdp.waitFor('(window.state||{}).viewMode === "preview"', { timeout: 15000, label: 'viewMode=preview' });
  return 'switched';
}

/** 打开文件并等 currentPath + doc 落定（协议 §2 坑②③：视图偏好会复位、启动期异步自动开文件）。 */
async function openFileStable(cdp, relPath, { timeout = 90000 } = {}) {
  await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(relPath)}, { skipNav: true })`);
  await cdp.waitFor(
    `window.state.currentPath === ${JSON.stringify(relPath)} && !!window.state.doc`,
    { timeout, label: 'open ' + relPath }
  );
  return true;
}

function stats(arr) {
  const v = (arr || []).filter((x) => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  const q = (p) => {
    const h = (v.length - 1) * p;
    const lo = Math.floor(h), hi = Math.ceil(h);
    return lo === hi ? v[lo] : v[lo] + (v[hi] - v[lo]) * (h - lo);
  };
  const med = q(0.5);
  const r3 = (x) => (x == null ? null : +x.toFixed(3));
  return {
    n: v.length, min: r3(v[0]), median: r3(med), p95: r3(q(0.95)), max: r3(v[v.length - 1]),
    q1: r3(q(0.25)), q3: r3(q(0.75)), iqr: r3(q(0.75) - q(0.25)),
    iqrOverMedian: med > 0 ? r3((q(0.75) - q(0.25)) / med) : null,
    p95OverMedian: med > 0 ? r3(q(0.95) / med) : null,
  };
}

/** 三态判定（与 benchmark-measurement-protocol §6 同构：先噪声、后预算）。 */
function judge(s, budgetMs, noise = REALAPP_DEFAULTS.noise) {
  if (!s) return { decision: 'gray', reasons: ['no-samples'] };
  const reasons = [];
  if (s.n < noise.minSamples) reasons.push(`samples=${s.n} < minSamples=${noise.minSamples}`);
  if (s.iqrOverMedian != null && s.iqrOverMedian > noise.maxIqrOverMedian) reasons.push(`IQR/median=${s.iqrOverMedian} > ${noise.maxIqrOverMedian}`);
  if (s.p95OverMedian != null && s.p95OverMedian > noise.maxP95OverMedian) reasons.push(`p95/median=${s.p95OverMedian} > ${noise.maxP95OverMedian}`);
  const within = s.median != null && s.median <= budgetMs;
  const decision = reasons.length ? 'gray' : (within ? 'green' : 'red');
  return { decision, status: decision === 'gray' ? 'inconclusive' : decision, budgetMs, withinBudget: within, median: s.median, reasons: reasons.length ? reasons : ['噪声在阈值内，判据可判'] };
}

// ─────────────────────────────────────────────────────────────────────────────
// 主流程
// ─────────────────────────────────────────────────────────────────────────────
async function main() {
  const args = parseArgs(process.argv.slice(2));
  const port = parseInt(args.port || '9500', 10);
  const driver = args.driver || 'auto';         // auto | manual
  const stage = args.stage || 'all';            // A | B | C | all（manual 模式单阶段演练）
  const readOnly = !!args.read;                 // manual --read：只读表
  const out = args.out || null;
  const fileA = args['file-a'] || 'scale/scale-5k.md';
  const fileB = args['file-b'] || 'corpus/01-ime-zh.md';
  const rounds = parseInt(args.rounds || '3', 10);
  const warmup = parseInt(args['warmup-keys'] || '5', 10);
  const keysPerRound = parseInt(args.keys || '10', 10);
  const minBlocks = parseInt(args['min-blocks'] || '5', 10);

  const result = {
    schema: 'memoria-realapp-measure/v1',
    protocol: 'docs/design/realapp-measurement-protocol.md',
    port, driver, stage, fileA, fileB, rounds, warmup, keysPerRound, minBlocks,
    startedAt: new Date().toISOString(),
    budgets: REALAPP_DEFAULTS,
    environment: {},
    stages: {},
  };
  let cdp = null;
  let exitCode = 1;
  try {
    const version = await httpJson(`http://127.0.0.1:${port}/json/version`);
    result.environment.browser = version.Browser;
    const target = await findAppTarget(port);
    result.environment.target = { id: target.id, title: target.title, url: target.url };
    cdp = await CDP.connect(target.webSocketDebuggerUrl);
    await cdp.send('Runtime.enable');
    await waitAppReady(cdp);
    // ⚠️ `--read` 必须**只读不复位**：它要读的是另一进程（arm 阶段）留下的埋点状态。
    // 若在这里重装埋点，会把 open/tab/key 全部清成 null ⇒ 读数永远是空的（实测踩到）。
    if (driver === 'manual' && readOnly) {
      const has = await cdp.evalJS('!!(window.__ram && window.__ram.vi)');
      if (!has) {
        throw new Error('页面上没有埋点（window.__ram 不存在）—— 请先跑：--driver manual --stage all');
      }
      result.environment.instrumentationVersion = await cdp.evalJS('window.__ram.vi');
    } else {
      // 先清掉可能残留的旧版埋点，再装当前版（见 INSTALL 的版本守卫）
      await cdp.evalJS('(function(){try{ if(window.__ram&&window.__ram.key&&window.__ram.key.uninstall) window.__ram.key.uninstall(); }catch(e){} window.__ram=null; return true;})()');
      await cdp.evalJS('(' + INSTALL.toString() + ')()');
      const vi = await cdp.evalJS('(window.__ram && window.__ram.vi) || 0');
      if (vi !== 4) throw new Error('埋点版本不符：期望 4，实际 ' + vi);
      result.environment.instrumentationVersion = vi;
    }
    result.environment.gpu = await cdp.evalJS(`(function(){
      try { var c=document.createElement('canvas'); var gl=c.getContext('webgl');
        if(!gl) return {webgl:false};
        var d=gl.getExtension('WEBGL_debug_renderer_info');
        return {webgl:true, vendor:d?gl.getParameter(d.UNMASKED_VENDOR_WEBGL):null, renderer:d?gl.getParameter(d.UNMASKED_RENDERER_WEBGL):null};
      } catch(e){ return {webgl:false,error:String(e)}; }
    })()`);
    result.environment.viewport = await cdp.evalJS('({w: innerWidth, h: innerHeight, dpr: devicePixelRatio})');
    result.environment.kbPath = await cdp.evalJS('(window.state||{}).kbPath || null');

    // ── manual 模式：只开启埋点 / 只读表 ─────────────────────────────────
    if (driver === 'manual') {
      if (readOnly) {
        result.stages.read = await cdp.evalJS('window.__ram.dump()');
        result.ok = true; exitCode = 0;
        result.manualInstruction = '读表完成；把 stages.read 里的数字填进 §5 记录表。';
      } else {
        // manual 模式**不派发任何输入**：只武装埋点，等操作者做完
        if (stage === 'A' || stage === 'all') {
          await ensurePreviewView(cdp);
          await cdp.evalJS(`window.__ram.startKey({inputChannel: 'human-keyboard'})`);
        }
        if (stage === 'B' || stage === 'all') {
          await cdp.evalJS(`window.__ram.startOpen('manual', {minBlocks: ${minBlocks}})`);
          // 人工模式也必须声明目标文件：否则 pathOk 恒真，会立刻假完成（实测）
          await cdp.evalJS(`window.__ram.setOpenTarget(${JSON.stringify(fileA)})`);
        }
        if (stage === 'C' || stage === 'all') {
          await cdp.evalJS(`window.__ram.startTab('manual', {minBlocks: ${minBlocks}})`);
          await cdp.evalJS(`window.__ram.setTabTarget(${JSON.stringify(fileA)})`);
        }
        result.ok = true; exitCode = 0;
        result.manualInstruction =
          '埋点已武装、**脚本不会操作窗口**。请按 docs/design/realapp-measurement-protocol.md §5 做人手操作，' +
          '做完后运行：node scripts/benchmark/surface/realapp_measure.mjs --port ' + port + ' --driver manual --read';
      }
    } else {
      // ── auto 模式：CDP 驱动 ──────────────────────────────────────────
      const ix = new Ix(cdp);

      // 坑③：启动期会异步自动打开默认文件 ⇒ 等 currentPath 稳定
      await cdp.waitFor('!!(window.state && window.state.currentPath)', { timeout: 60000, label: 'first-open' });
      await sleep(1200);

      // ── B：首开 → 块 + 公式排版完成（重复 R 次；每次都强制先离开该文件）──
      if (stage === 'B' || stage === 'all') {
        const samples = [];
        const detail = [];
        for (let i = 0; i < rounds; i++) {
          // 每次迭代都是「从别的文件切到 A」⇒ 是真正的打开（第 1 次也是：先落到 B）
          await openFileStable(cdp, fileB).catch(() => {});
          await ensurePreviewView(cdp);
          await sleep(300);
          // 顺序很重要：先武装埋点（此时还不知道目标文件），再声明目标，再真正 openFile。
          await cdp.evalJS(`window.__ram.startOpen(${JSON.stringify('auto#')} + ${i}, {minBlocks: ${minBlocks}})`);
          await cdp.evalJS(`window.__ram.setOpenTarget(${JSON.stringify(fileA)})`);
          const t0 = Date.now();
          await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(fileA)}, { skipNav: true })`);
          await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(fileA)} && !!window.state.doc`, { timeout: 90000, label: 'openA#' + i });
          // 坑②：打开后视图会被「按文件视图偏好」复位 ⇒ 再确保一次。
          // 注意：这一步的代价**会计入**指标 B（它是用户真实等待的一部分），故不额外扣减。
          const v = await ensurePreviewView(cdp);
          await cdp.waitFor('(window.__ram.openState() && window.__ram.openState().done) ? true : false', { timeout: 90000, label: 'open-done#' + i }).catch(() => null);
          const os = await cdp.evalJS('window.__ram.openState()');
          if (os && os.totalMs != null) samples.push(os.totalMs);
          detail.push({ round: i, viewEnsure: v, ...(os || {}), wallMs: Date.now() - t0 });
          // 让下一次迭代前状态静止
          await sleep(500);
        }
        const s = stats(samples);
        result.stages.B = {
          metric: 'open_render_ms', what: '首开 → 块渲染完成 + 公式排版完成（页面内 perf.now）',
          samples, detail, stats: s, verdict: judge(s, REALAPP_DEFAULTS.budgetOpenRenderMs),
        };
      }

      // ── A：按键 → 真源落定 ────────────────────────────────────────────
      if (stage === 'A' || stage === 'all') {
        await openFileStable(cdp, fileA);
        await ensurePreviewView(cdp);
        // 进入编辑态并把光标放进第一个块
        await cdp.evalJS(`(function(){var EH=window.MemoriaEditHandler;if(EH&&!EH.editMode&&EH.toggleEditMode)EH.toggleEditMode();return !!(EH&&EH.editMode);})()`);
        await sleep(400);
        const box = await cdp.evalJS(`(function(){var b=document.querySelectorAll('#preview .-src-block')[0];if(!b)return null;b.scrollIntoView({block:'center'});var r=b.getBoundingClientRect();return {x:Math.round(r.left+30),y:Math.round(r.top+r.height/2)};})()`);
        if (box) await ix.click(box.x, box.y);
        await sleep(250);
        await cdp.evalJS(`window.__ram.startKey({inputChannel: 'cdp-Input.dispatchKeyEvent(keyDown+keyUp,text)'})`);
        // warmup：丢弃
        for (let i = 0; i < warmup; i++) await ix.typeText('z');
        await cdp.evalJS('window.__ram.resetKey()');
        const perRound = [];
        for (let r = 0; r < rounds; r++) {
          for (let k = 0; k < keysPerRound; k++) await ix.typeText('z');
          const ks = await cdp.evalJS('window.__ram.keyState()');
          perRound.push(stats(ks.keys.map((x) => x.arriveToReturnMs)));
          await cdp.evalJS('window.__ram.resetKey()');
        }
        const all = await cdp.evalJS('window.__ram.keyState()');
        await cdp.evalJS('window.__ram.stopKey()');
        const dump = await cdp.evalJS('window.__ram.dump()');
        // dump() 的形状：{ key: { n, arriveToReturn, insertOnly, keys:[...] } }
        const lastKeys = (dump && dump.key && Array.isArray(dump.key.keys)) ? dump.key.keys : [];
        const perRoundMedians = perRound.filter(Boolean).map((x) => x.median);
        const sRounds = perRoundMedians.length ? stats(perRoundMedians) : null;
        // 全部正式键的合并分布（跨轮池化，仅作参考；判据投在 perRoundMedians 上）
        const sPooled = lastKeys.length ? stats(lastKeys.map((k) => k.arriveToReturnMs)) : null;
        result.stages.A = {
          metric: 'key_to_source_ms', what: '按键（受信任输入）→ 真源落定（页面内 perf.now）',
          inputChannel: 'cdp-Input.dispatchKeyEvent(keyDown+keyUp,text)',
          warmupKeys: warmup, rounds, keysPerRound,
          perRound,
          lastRound: dump && dump.key ? { arriveToReturn: dump.key.arriveToReturn, insertOnly: dump.key.insertOnly } : null,
          stats: sRounds,
          pooledLastRound: sPooled,
          verdict: judge(sRounds, REALAPP_DEFAULTS.budgetKeyToSourceMs),
          note: '判据投在「每轮 median 的中位」上（与 benchmark-measurement-protocol §5.2 同口径）；pooledLastRound 仅参考',
          errors: (all && all.errors) || [],
          keysLastRound: lastKeys.slice(0, 80),
        };
      }

      // ── C：A→B→A 切页签 ───────────────────────────────────────────────
      if (stage === 'C' || stage === 'all') {
        const samples = [];
        for (let i = 0; i < rounds; i++) {
          await openFileStable(cdp, fileB);
          await ensurePreviewView(cdp);
          const t0 = Date.now();
          await cdp.evalJS(`window.__ram.startTab(${JSON.stringify('auto#')} + ${i}, {minBlocks: ${minBlocks}})`);
          await cdp.evalJS(`window.__ram.setTabTarget(${JSON.stringify(fileA)})`);
          await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(fileA)}, { skipNav: true })`);
          await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(fileA)} && !!window.state.doc`, { timeout: 90000, label: 'backA#' + i });
          await cdp.waitFor('(window.__ram.tabState() && window.__ram.tabState().done) ? true : false', { timeout: 60000, label: 'tab-done#' + i }).catch(() => null);
          const ts = await cdp.evalJS('window.__ram.tabState()');
          if (ts && ts.totalMs != null) samples.push(ts.totalMs);
          await sleep(150);
        }
        const s = stats(samples);
        result.stages.C = {
          metric: 'tab_switch_ms', what: 'A→B→A：回到 A 时「预览可选可见」完成（页面内 perf.now）',
          samples, stats: s, verdict: judge(s, REALAPP_DEFAULTS.budgetTabSwitchMs),
        };
      }

      result.dump = await cdp.evalJS('window.__ram.dump()');
      result.ok = true;
      exitCode = 0;
    }
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) cdp.close();
    setTimeout(() => process.exit(exitCode), 4000).unref();
  }
  const text = JSON.stringify(result, null, 2);
  if (out) {
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, text, 'utf8');
    process.stdout.write('__REALAPP_MEASURE__' + JSON.stringify({ ok: result.ok, out }) + '\n');
  } else {
    process.stdout.write(text + '\n');
  }
  return exitCode;
}

if (import.meta.url === `file:///${process.argv[1].replace(/\\/g, '/')}`) {
  const code = await main();
  process.exitCode = code;
}
