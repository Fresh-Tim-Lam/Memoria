// 跨块选区矩阵探针驱动（task-79）
//
// 干什么：对 `selection-matrix.json` 里每条用例，在真实预览编辑态里
//   ① 建立跨块选区（程序化 Range 为主；`mouseCases` 用 CDP 真实鼠标拖拽）
//   ② 执行操作：copy（Ctrl+C 原生）/ cut（**合成 beforeinput deleteByCut**，等价 Ctrl+X——
//      CDP 直接派发 Ctrl+X 会卡死 target，见任务说明）/ delete（真实 Delete 键）/
//      pasteReplace（写剪贴板 + 真实 Ctrl+V）
//   ③ 断言：选区建立 / 源码词集变化 / 选中词已删 / 未选词保留 / 无重复残留 /
//      **强制整篇重渲后不"回魂"** / 重渲不改源码 / **单次 Ctrl+Z 复原** / 剪贴板内容
// 产出：JSON（每用例 checks + pre/post/undo 源码 + 产品 console 日志）给 run_selection.py 出矩阵。
//
// 为什么复用 `../interaction.mjs`：CDP 连接 / Edge 启动 / 真实键鼠原语 / 真机 attach
// 都已在那里验证过（含 --user-data-dir 清理、CDP 端口竞态等坑），本驱动不复制。
//
// 用法：
//   node scripts/benchmark/surface/scenarios/selection-driver.mjs \
//     --url http://127.0.0.1:<port>/ --matrix .../selection-matrix.json --out .../raw.json --label baseline
//   node ... --cdp-port 9611   # attach 真机应用
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { withBrowser, withLiveApp, sleep } from '../interaction.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '../../../..');

// ─────────────────────────────────────────────────────────────────────────────
// 页面内助手（整段注入；不得引用驱动侧闭包变量）
// ─────────────────────────────────────────────────────────────────────────────
function pageHelpers() {
  var SYNTAX_WORDS = {
    python: 1, mermaid: 1, graph: 1, TD: 1, flowchart: 1, js: 1, bash: 1, text: 1,
  };
  var RE_WORD = /[A-Za-z][A-Za-z0-9_]*/g;

  function qsaBlocks() {
    return Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
  }
  /** 块序身份属性是 `data--block-index`（双连字符；`dataset.blockIndex` 取不到）。 */
  function blockIdx(el) {
    if (!el || !el.getAttribute) return null;
    var v = el.getAttribute('data--block-index');
    if (v == null) return null;
    var n = parseInt(v, 10);
    return isNaN(n) ? null : n;
  }
  function previewEl() { return document.getElementById('preview'); }
  function bodyText() { return (window.state && window.state.doc && window.state.doc.body) || ''; }

  /** 块内所有「词」（按 DOM 文本节点顺序，node+offset 精确定位）。 */
  function blockWords(el) {
    var out = [];
    if (!el) return out;
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    var n;
    while ((n = walker.nextNode())) {
      var p = n.parentElement;
      if (!p) continue;
      var tag = (p.tagName || '').toUpperCase();
      if (tag === 'SCRIPT' || tag === 'STYLE') continue;
      var s = n.nodeValue || '';
      var m;
      RE_WORD.lastIndex = 0;
      while ((m = RE_WORD.exec(s)) !== null) {
        out.push({ w: m[0], node: n, start: m.index, end: m.index + m[0].length });
      }
    }
    return out;
  }

  function findEndpoint(spec) {
    var blocks = qsaBlocks();
    var bi = -1, words = null, marker = spec.marker, target = spec.word;
    for (var i = 0; i < blocks.length; i++) {
      var ws = blockWords(blocks[i]);
      var hasMarker = false;
      for (var k = 0; k < ws.length; k++) { if (ws[k].w === marker) { hasMarker = true; break; } }
      if (!hasMarker) continue;
      bi = i; words = ws; break;
    }
    if (bi < 0) return { ok: false, reason: 'marker-not-in-dom:' + marker };
    for (var j = 0; j < words.length; j++) {
      if (words[j].w !== target) continue;
      var w = words[j];
      var off = spec.edge === 'end' ? w.end : w.start;
      return { ok: true, blockIndex: bi, wordIndex: j, node: w.node, offset: off, word: w };
    }
    return { ok: false, reason: 'word-not-in-block:' + marker + '/' + target };
  }

  function rangeOfWord(w) {
    var r = document.createRange();
    r.setStart(w.node, w.start);
    r.setEnd(w.node, w.end);
    return r;
  }

  /** rangeA 是否完整包含 rangeB */
  function containsRange(rangeA, rangeB) {
    return rangeA.compareBoundaryPoints(Range.START_TO_START, rangeB) <= 0 &&
           rangeA.compareBoundaryPoints(Range.END_TO_END, rangeB) >= 0;
  }

  function fullRange() {
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount || sel.isCollapsed) return null;
    return sel.getRangeAt(0);
  }

  function selInfo() {
    var sel = window.getSelection();
    if (!sel) return null;
    var out = { collapsed: sel.isCollapsed, rangeCount: sel.rangeCount, text: String(sel) };
    if (!sel.rangeCount) return out;
    var r = sel.getRangeAt(0);
    function bi(node) {
      var el = node && (node.nodeType === 1 ? node : node.parentElement);
      var b = el && el.closest ? el.closest('#preview .-src-block') : null;
      return b ? blockIdx(b) : null;
    }
    out.anchorBlock = bi(r.startContainer);
    out.focusBlock = bi(r.endContainer);
    return out;
  }

  /** 建立选区（程序化 setBaseAndExtent）。返回是否成功 + 端点块号。 */
  function selectRange(fromSpec, toSpec) {
    var pv = previewEl();
    if (!pv) return { ok: false, reason: 'no-preview' };
    var a = findEndpoint(fromSpec);
    if (!a.ok) return a;
    var b = findEndpoint(toSpec);
    if (!b.ok) return b;
    try { pv.focus({ preventScroll: true }); } catch (_) { pv.focus(); }
    var sel = window.getSelection();
    sel.removeAllRanges();
    try {
      sel.setBaseAndExtent(a.node, a.offset, b.node, b.offset);
    } catch (e) {
      return { ok: false, reason: 'setBaseAndExtent:' + ((e && e.message) || e) };
    }
    var info = selInfo();
    var okOrder = info && info.anchorBlock != null && info.focusBlock != null &&
      (info.anchorBlock < info.focusBlock ||
        (info.anchorBlock === info.focusBlock && info.text.length > 0));
    return {
      ok: !!okOrder, how: 'programmatic', anchorBlock: info && info.anchorBlock,
      focusBlock: info && info.focusBlock, text: info && info.text,
      reason: okOrder ? null : ('order/anchors: anchor=' + (info && info.anchorBlock) +
        ' focus=' + (info && info.focusBlock) + ' len=' + String((info && info.text || '').length) +
        ' from=' + a.blockIndex + ' to=' + b.blockIndex),
      fromBlock: a.blockIndex, toBlock: b.blockIndex,
    };
  }

  /** 端点屏幕坐标（用词的非折叠 rect；折叠 caret rect 实测可能全零）。 */
  function endpointPoints(fromSpec, toSpec) {
    var a = findEndpoint(fromSpec);
    var b = findEndpoint(toSpec);
    if (!a.ok || !b.ok) return { ok: false, reason: (a.reason || b.reason) };
    var blocks = qsaBlocks();
    blocks[a.blockIndex].scrollIntoView({ block: 'center' });
    function pt(w, preferEnd) {
      var r = rangeOfWord(w);
      var rects = r.getClientRects();
      var rect = rects.length ? (preferEnd ? rects[rects.length - 1] : rects[0]) : r.getBoundingClientRect();
      if (!rect || (!rect.width && !rect.height)) return null;
      return { x: Math.round(rect.left + Math.max(1, rect.width / 2)), y: Math.round(rect.top + rect.height / 2) };
    }
    var pa = pt(a.word, false);
    var pb = pt(b.word, true);
    if (!pa || !pb) return { ok: false, reason: 'no-rect' };
    var vh = window.innerHeight, vw = window.innerWidth;
    if (pa.y < 0 || pa.y > vh || pb.y < 0 || pb.y > vh || pa.y === pb.y) {
      return { ok: false, reason: 'not-both-visible', pa: pa, pb: pb };
    }
    return { ok: true, start: pa, end: pb };
  }

  /**
   * 把当前选区**吸附到词边界**。
   *
   * 真实鼠标拖拽的落点是任意字符 ⇒ 会切出"半词"（如 `delt` + `a`），而矩阵的词集断言
   * 以整词为口径。做法：取被**完整覆盖**的词序列，新选区 = 首词开头 → 末词结尾。
   * 这不是伪造选区：拖拽本身仍是真实 Input.dispatchMouseEvent；吸附只消除半词噪声。
   * @returns {{ok:boolean, coveredWords?:string[], reason?:string}}
   */
  function snapSelectionToWords() {
    var range = fullRange();
    if (!range) return { ok: false, reason: 'no-range' };
    var blocks = qsaBlocks();
    var picks = [];
    for (var bi = 0; bi < blocks.length; bi++) {
      var ws = blockWords(blocks[bi]);
      for (var k = 0; k < ws.length; k++) {
        if (containsRange(range, rangeOfWord(ws[k]))) picks.push({ bi: bi, w: ws[k] });
      }
    }
    if (!picks.length) return { ok: false, reason: 'no-whole-word-covered' };
    var a = picks[0], b = picks[picks.length - 1];
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.setBaseAndExtent(a.w.node, a.w.start, b.w.node, b.w.end);
    return {
      ok: true, count: picks.length, fromBlock: a.bi, toBlock: b.bi,
      coveredWords: picks.map(function (p) { return p.w.w; }), text: String(sel),
    };
  }

  function addTok(counter, tok, n) {
    if (!tok) return;
    counter[tok] = (counter[tok] || 0) + (n || 1);
  }
  function tokensOfLine(line) {
    var out = [];
    var m;
    RE_WORD.lastIndex = 0;
    while ((m = RE_WORD.exec(line)) !== null) out.push(m[0]);
    return out;
  }
  function blockSrcTokens(bi) {
    var map = window.__blockLineMap || [];
    var range = map[bi];
    var body = bodyText();
    var lines = body.split('\n');
    var out = [];
    if (!range) return out;
    var s = Math.max(0, range.startLine), e = Math.min(lines.length - 1, range.endLine);
    for (var i = s; i <= e; i++) out = out.concat(tokensOfLine(lines[i]));
    return out;
  }

  /**
   * 选区覆盖统计：
   *   · 整块被覆盖 → 用**源码行**词（能覆盖 MathJax/mermaid 排版后 DOM 里看不见的词）
   *   · 部分覆盖 → 用 DOM 词精确判定（端点块）
   * 返回 deleted（词→次数）+ coveredBlocks + partialBlocks + anomalies。
   */
  function coverage() {
    var range = fullRange();
    if (!range) return { ok: false, reason: 'no-range' };
    var blocks = qsaBlocks();
    var deleted = {};
    var coveredBlocks = [], partialBlocks = [], anomalies = [];
    for (var bi = 0; bi < blocks.length; bi++) {
      var el = blocks[bi];
      var elIdx = blockIdx(el);
      if (elIdx == null) elIdx = bi;
      var er = document.createRange();
      er.selectNodeContents(el);
      if (containsRange(range, er)) {
        coveredBlocks.push(elIdx);
        var toks = blockSrcTokens(elIdx);
        for (var t = 0; t < toks.length; t++) addTok(deleted, toks[t], 1);
        continue;
      }
      var ws = blockWords(el);
      var hit = 0;
      for (var k = 0; k < ws.length; k++) {
        if (containsRange(range, rangeOfWord(ws[k]))) { addTok(deleted, ws[k].w, 1); hit++; }
      }
      if (hit > 0) partialBlocks.push(elIdx);
    }
    if (!coveredBlocks.length && !partialBlocks.length) {
      anomalies.push('coverage-empty（选区没落到任何块文本上）');
    }
    return {
      ok: true, deleted: deleted, coveredBlocks: coveredBlocks,
      partialBlocks: partialBlocks, anomalies: anomalies, selText: String(window.getSelection()),
    };
  }

  function tokensOf(text) {
    var counter = {};
    var m;
    RE_WORD.lastIndex = 0;
    while ((m = RE_WORD.exec(String(text || ''))) !== null) addTok(counter, m[0], 1);
    return counter;
  }
  function domTokens() {
    var pv = previewEl();
    return pv ? tokensOf(pv.innerText || pv.textContent || '') : {};
  }

  /** 强制整篇重渲（回魂检测）：调 MemoriaApp.renderPreview(state.doc)，完成标志走 window.__RENDER_DONE。 */
  function renderFull() {
    window.__RENDER_DONE = false;
    var app = window.MemoriaApp;
    if (!app || typeof app.renderPreview !== 'function') { window.__RENDER_DONE = 'no-api'; return 'no-api'; }
    try {
      var p = app.renderPreview(window.state.doc);
      Promise.resolve(p).then(function () { window.__RENDER_DONE = true; },
                             function () { window.__RENDER_DONE = 'error'; });
    } catch (e) {
      window.__RENDER_DONE = 'throw:' + ((e && e.message) || e);
    }
    return 'started';
  }

  function undoOnce() {
    var es = window.MemoriaEditSync;
    if (!es || typeof es.undo !== 'function') return false;
    try { es.undo(); return true; } catch (e) { return 'throw:' + ((e && e.message) || e); }
  }

  function noticeText() {
    var arr = window.__NOTICE && window.__NOTICE.calls;
    if (!arr || !arr.length) return null;
    var last = arr[arr.length - 1];
    return last && (last.msg + (last.detail ? ' | ' + last.detail : ''));
  }

  /** 事件监听/剪贴板/提示 侦察桩（幂等）：只装一次。 */
  function installSpies() {
    if (window.__SEL_SPY) return true;
    window.__SEL_SPY = true;
    window.__CLIP = { writes: [], copyEvents: [], pasteEvents: [] };
    window.__NOTICE = { calls: [] };
    var pv = previewEl();
    if (pv) {
      document.addEventListener('copy', function (e) {
        try { window.__CLIP.copyEvents.push(e.clipboardData ? e.clipboardData.getData('text/plain') : null); }
        catch (_) { window.__CLIP.copyEvents.push(null); }
      }, true);
      document.addEventListener('paste', function (e) {
        try { window.__CLIP.pasteEvents.push(e.clipboardData ? e.clipboardData.getData('text/plain') : null); }
        catch (_) { window.__CLIP.pasteEvents.push(null); }
      }, true);
    }
    // 剪贴板写（Ctrl+X 路径 writeCutToClipboard）与提示（P0 静默失败要求可见提示）
    try {
      var clip = navigator.clipboard;
      if (clip && typeof clip.writeText === 'function') {
        var orig = clip.writeText.bind(clip);
        var wrapped = function (t) {
          window.__CLIP.writes.push(String(t == null ? '' : t));
          return orig(t);
        };
        try { clip.writeText = wrapped; } catch (_) {
          try { Object.defineProperty(clip, 'writeText', { value: wrapped, configurable: true }); } catch (_2) { /* 只读就放弃 */ }
        }
      }
    } catch (_) { /* 无剪贴板 API */ }
    var app = window.MemoriaApp;
    if (app) {
      ['showFlashError', 'showFlashInfo', 'setStatus', 'setStatusError'].forEach(function (fn) {
        var orig = app[fn];
        if (typeof orig !== 'function') return;
        try {
          app[fn] = function (msg, detail) {
            try { window.__NOTICE.calls.push({ fn: fn, msg: String(msg == null ? '' : msg), detail: String(detail == null ? '' : detail) }); } catch (_) { }
            return orig.apply(app, arguments);
          };
        } catch (_) { /* 不可写就只做 console */ }
      });
    }
    return true;
  }

  /** 合成 beforeinput（deleteByCut）——与真实 Ctrl+X 走**同一个产品 handler**，
   *  唯一差别是系统剪贴板写入被 spy 记录（CDP 不能安全派发 Ctrl+X）。 */
  function dispatchCut() {
    var pv = previewEl();
    if (!pv) return false;
    var ev;
    try {
      ev = new InputEvent('beforeinput', { inputType: 'deleteByCut', bubbles: true, cancelable: true });
    } catch (_) {
      ev = document.createEvent('Event');
      ev.initEvent('beforeinput', true, true);
      ev.inputType = 'deleteByCut';
    }
    pv.dispatchEvent(ev);
    return { prevented: ev.defaultPrevented };
  }

  function resetClip() { window.__CLIP = { writes: [], copyEvents: [], pasteEvents: [] }; window.__NOTICE = { calls: [] }; }

  /** 浏览器原生复制（无产品 handler，等价 Ctrl+C 的剪贴板填充路径）。
   *  用 execCommand('copy') 只为**兜底**：真机/无头下真实 Ctrl+C 偶发不触发 copy 事件时，
   *  由浏览器自己的 copy 管线填 clipboardData（我们只读取它，不改内容）。 */
  function copySelection() {
    var out = { ok: false, err: null };
    try { out.ok = document.execCommand('copy'); } catch (e) { out.err = (e && e.message) || String(e); }
    return out;
  }

  /** 合成 paste 事件（兜底）：ClipboardEvent 构造器在 Chromium 里支持 clipboardData。
   *  产品 paste handler 读 e.clipboardData，与本路径完全同源；仅事件来源不同（报告里标注）。 */
  function syntheticPaste(text) {
    var pv = previewEl();
    if (!pv) return { ok: false, reason: 'no-preview' };
    try {
      var dt = new DataTransfer();
      dt.setData('text/plain', text);
      var ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
      pv.dispatchEvent(ev);
      return { ok: true, prevented: ev.defaultPrevented };
    } catch (e) {
      return { ok: false, reason: (e && e.message) || String(e) };
    }
  }

  /** 读系统剪贴板（3s 超时兜底；headless 下 readText 可能一直 pending）。 */
  function readClipboard() {
    if (!navigator.clipboard || typeof navigator.clipboard.readText !== 'function') {
      return Promise.resolve('no-api');
    }
    return Promise.race([
      navigator.clipboard.readText().then(
        function (t) { return 'OK:' + t; },
        function (e) { return 'REJ:' + ((e && e.message) || e); }),
      new Promise(function (res) { setTimeout(function () { res('TIMEOUT'); }, 3000); }),
    ]);
  }

  function writeClipboard(text) {
    var pv = previewEl();
    function fallback(err) {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('data-sel-probe', '1');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        ta.style.top = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
        document.body.removeChild(ta);
        if (pv) { try { pv.focus({ preventScroll: true }); } catch (_2) { /* noop */ } }
        return ok ? 'execCommand' : ('failed:' + ((err && err.message) || err));
      } catch (e2) {
        return 'failed:' + ((e2 && e2.message) || e2);
      }
    }
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        return Promise.resolve(navigator.clipboard.writeText(text)).then(function () { return 'api'; }, fallback);
      }
    } catch (e) { return Promise.resolve(fallback(e)); }
    return Promise.resolve(fallback(new Error('no-clipboard-api')));
  }

  /** 选区失败时的现场诊断：端点节点是否 still connected / 是否在 #preview 内 / 祖先链。 */
  function debugSelect(fromSpec, toSpec) {
    var pv = previewEl();
    function chain(node) {
      var out = [];
      var el = node && (node.nodeType === 1 ? node : node.parentElement);
      while (el && out.length < 8) {
        out.push((el.tagName || '?') + (el.id ? '#' + el.id : '') +
          (el.className && typeof el.className === 'string' ? '.' + el.className.split(/\s+/).slice(0, 3).join('.') : ''));
        el = el.parentElement;
      }
      return out;
    }
    var a = findEndpoint(fromSpec);
    var b = findEndpoint(toSpec);
    var out = {
      previewExists: !!pv,
      blocksInPreview: qsaBlocks().length,
      viewMode: (window.state || {}).viewMode,
      editMode: !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode),
      a: a.ok ? { connected: !!a.node.isConnected, inPreview: pv ? pv.contains(a.node) : null, chain: chain(a.node), blockIndex: a.blockIndex, offset: a.offset } : a,
      b: b.ok ? { connected: !!b.node.isConnected, inPreview: pv ? pv.contains(b.node) : null, chain: chain(b.node), blockIndex: b.blockIndex, offset: b.offset } : b,
    };
    if (a.ok) {
      try { pv.focus({ preventScroll: true }); } catch (_) { /* noop */ }
      out.aAfterFocus = { connected: !!a.node.isConnected, inPreview: pv ? pv.contains(a.node) : null };
    }
    return out;
  }

  window.__SEL = {
    blocks: qsaBlocks,
    body: bodyText,
    words: blockWords,
    selInfo: selInfo,
    selectRange: selectRange,
    snapSelectionToWords: snapSelectionToWords,
    endpointPoints: endpointPoints,
    coverage: coverage,
    tokensOf: tokensOf,
    domTokens: domTokens,
    renderFull: renderFull,
    undoOnce: undoOnce,
    installSpies: installSpies,
    dispatchCut: dispatchCut,
    resetClip: resetClip,
    writeClipboard: writeClipboard,
    copySelection: copySelection,
    syntheticPaste: syntheticPaste,
    readClipboard: readClipboard,
    debugSelect: debugSelect,
    clip: function () { return window.__CLIP; },
    notice: noticeText,
    editMode: function () { return !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode); },
    forceEditMode: function () {
      var EH = window.MemoriaEditHandler;
      if (EH && !EH.editMode) EH.toggleEditMode();
      return !!(EH && EH.editMode);
    },
    viewMode: function () { return (window.state || {}).viewMode; },
    ensurePreview: function () {
      if ((window.state || {}).viewMode === 'preview') return 'preview';
      var b = document.querySelector('.-view-btn[data-view="preview"]');
      if (b) b.click();
      return (window.state || {}).viewMode;
    },
    blockLineMap: function () { return window.__blockLineMap || null; },
    // 隔离兜底：万一磁盘被 flush（切文件/失焦）写脏，用后端 force 覆盖回原始内容
    restoreDisk: function (file, pristine) {
      var app = window.MemoriaApp;
      if (!app || typeof app.call !== 'function') return 'no-api';
      return app.call('save_document', file, pristine, '', true);
    },
  };
  return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// 工具
// ─────────────────────────────────────────────────────────────────────────────
const SYNTAX_WORDS = new Set(['python', 'mermaid', 'graph', 'TD', 'flowchart', 'js', 'bash', 'text']);

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const k = a.slice(2);
    const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
    out[k] = v;
  }
  return out;
}

const norm = (s) => String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
const tokSum = (c) => Object.keys(c).reduce((n, k) => n + c[k], 0);

/** CDP 调用超时包装：页面主线程卡死 / websocket 掉线时，promise 永远不 settle ⇒ 显式失败定位。 */
function withTimeout(p, ms, label) {
  return Promise.race([
    p,
    new Promise((_, reject) => {
      const t = setTimeout(() => reject(new Error('CDP 超时 ' + ms + 'ms: ' + label)), ms);
      if (t.unref) t.unref();
    }),
  ]);
}

// 诊断守卫：CDP WebSocket 被关掉时 pending 的 promise 永远不会 settle，
// 事件循环一旦没有其它 handle，node 会**静默 exit(0)**（看起来像"什么都没发生"）。
// 这里显式报出来，避免把基础设施崩溃误诊成用例逻辑。
let _finished = false;
const _keepAlive = setInterval(() => { /* keep event loop alive */ }, 1000);
process.on('beforeExit', (code) => {
  if (!_finished) {
    process.stderr.write('[fatal] 事件循环在完成前耗尽（code=' + code +
      '）——通常是 CDP WebSocket 已关闭但仍有 await 未 settle（浏览器/渲染进程崩溃）\n');
    process.exit(97);
  }
});
function subCounts(a, b) {
  const out = Object.assign({}, a);
  for (const k of Object.keys(b)) {
    out[k] = (out[k] || 0) - b[k];
    if (out[k] <= 0) delete out[k];
  }
  return out;
}
function diffCounts(a, b) {
  const out = [];
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) {
    const d = (a[k] || 0) - (b[k] || 0);
    if (d > 0) out.push('+' + k + 'x' + d);
    else if (d < 0) out.push('-' + k + 'x' + (-d));
  }
  return out;
}

/**
 * 「词被拼接」调和（真实编辑语义，不是放宽断言）。
 *
 * 选区端点在**词边界**时，删除会把两侧的词直接贴在一起（实测：删 `" hotel … H2 mike "`
 * 后 `golf` 与 `november` 变成 `golfnovember`）。这不是内容丢失，而是"用户把分隔空格也选中了"
 * 的忠实结果。因此：若某个 extra 词可以**恰好**拆成若干 missing 词的顺序拼接，则两边都剔除。
 * 拆不掉（真丢词/真多词）就保留为 FAIL —— 这个调和只消除空白差异，不掩盖内容差异。
 *
 * @param {Object<string,number>} expected 期望词频
 * @param {Object<string,number>} actual   实际词频
 * @returns {{missing:string[], extra:string[], fused:string[]}}
 */
function reconcileFused(expected, actual) {
  const missing = diffCounts(expected, actual).filter((s) => s.startsWith('-'));
  const extra = diffCounts(actual, expected).filter((s) => s.startsWith('+'));
  const parse = (s) => {
    const m = /^([+-])(.*)x(\d+)$/.exec(s);
    return m ? { word: m[2], n: parseInt(m[3], 10) } : null;
  };
  const missingMap = new Map();
  for (const s of missing) { const p = parse(s); if (p) missingMap.set(p.word, (missingMap.get(p.word) || 0) + p.n); }
  const fused = [];
  for (const s of extra) {
    const p = parse(s);
    if (!p) continue;
    for (let rep = 0; rep < p.n; rep++) {
      // 贪心：用 missing 词（可重复消耗）从左到右拼出该 extra 词
      const word = p.word;
      let pos = 0;
      const used = [];
      while (pos < word.length) {
        let hit = null;
        for (const cand of Array.from(missingMap.keys()).sort((x, y) => y.length - x.length)) {
          if ((missingMap.get(cand) || 0) > 0 && word.startsWith(cand, pos)) { hit = cand; break; }
        }
        if (!hit) { used.length = 0; break; }
        missingMap.set(hit, missingMap.get(hit) - 1);
        used.push(hit);
        pos += hit.length;
      }
      if (used.length && pos === word.length) fused.push(word + '=' + used.join('+'));
      else { used.forEach((w) => missingMap.set(w, missingMap.get(w) + 1)); }
    }
  }
  const missLeft = [];
  for (const [w, n] of missingMap) if (n > 0) missLeft.push('-' + w + 'x' + n);
  return { missing: missLeft, extra: extra.filter((s) => { const p = parse(s); return !fused.some((f) => f.startsWith(p.word + '=')); }), fused };
}

/**
 * 重新打开语料并**等 openFile Promise 真正完成**。
 * 陷阱：只等 `state.currentPath === file && state.doc` 是无效隔离 —— 同一文件仍开着时
 * 这两个条件**一开始就为真**，于是读到的是上一例改过的内存 doc（实测 preBody 比 pristine 少 10 字节）。
 * 做法：页面侧把 openFile 的 promise 结果写进 `window.__OPEN_DONE`，node 侧轮询（不在页面里 await）。
 */
async function openFileFresh(cdp, file, label) {
  await cdp.evalJS(`(function(){
    window.__OPEN_DONE = 'pending';
    try {
      window.MemoriaApp.openFile(${JSON.stringify(file)}).then(
        function (r) { window.__OPEN_DONE = 'ok:' + String(r || ''); },
        function (e) { window.__OPEN_DONE = 'err:' + ((e && e.message) || e); }
      );
    } catch (e) { window.__OPEN_DONE = 'throw:' + ((e && e.message) || e); }
    return true;
  })()`);
  await cdp.waitFor(`typeof window.__OPEN_DONE === 'string' && window.__OPEN_DONE !== 'pending'`,
    { timeout: 45000, label: 'open-done ' + (label || '') });
  const st = await cdp.evalJS('window.__OPEN_DONE');
  if (String(st).indexOf('ok') !== 0) throw new Error('openFile 未成功: ' + st);
  return st;
}

/**
 * 把文档复位到 pristine（每例隔离）。
 *
 * 实测坑：`openFile` 同一文件后，**首轮**读到的 `state.doc.body` 偶尔仍是上一例的编辑结果
 * （产品内部有预览 DOM 缓存/延迟提交路径，`openFile` 的 promise 回来时缓存恢复可能晚一拍）。
 * 这里显式「打开 → 校验 → 不符则重开（并先 force 写回 pristine）」最多 3 轮；
 * 仍不符就如实抛错（绝不带着脏状态继续跑用例 —— 否则矩阵数字不可信）。
 */
async function resetToPristine(cdp, file, pristine, label) {
  // 快路径：上一例没有改动源码（复制 / 被 ABORT 的操作）⇒ 不必重开，省一轮 openFile+渲染
  const cur = await cdp.evalJS('window.__SEL.body()');
  if (cur === pristine) return { ok: true, attempts: 0, reused: true };
  let body = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) {
      // 先确保磁盘/缓存都是 pristine，再重开
      await cdp.evalJS(`window.__SEL.restoreDisk(${JSON.stringify(file)}, ${JSON.stringify(pristine)})`).catch(() => null);
      await sleep(200);
    }
    await openFileFresh(cdp, file, (label || 'reset') + '#' + attempt);
    body = await cdp.evalJS('window.__SEL.body()');
    if (body === pristine) return { ok: true, attempts: attempt + 1, reused: false };
    await sleep(250);
  }
  return { ok: false, attempts: 3, got: body };
}

async function settle(cdp, { ms = 220, timeout = 3000 } = {}) {
  const t0 = Date.now();
  let last = null, stable = 0;
  while (Date.now() - t0 < timeout) {
    const snap = await cdp.evalJS(`(function(){
      var b = document.querySelectorAll('#preview .-src-block');
      var pv = document.getElementById('preview');
      return { n: b.length, len: pv ? (pv.innerText || '').length : -1,
               loading: !!document.querySelector('#preview .-preview-loading') };
    })()`).catch(() => null);
    const key = snap ? snap.n + ':' + snap.len + ':' + (snap.loading ? 1 : 0) : 'n/a';
    if (key === last && !(snap && snap.loading)) {
      stable++;
      if (stable * ms >= 700) return true;
    } else {
      last = key; stable = 0;
    }
    await sleep(ms);
  }
  return false;
}

async function waitBodyChange(cdp, preBody, timeout = 1500) {
  const t0 = Date.now();
  for (;;) {
    const body = await cdp.evalJS('window.__SEL.body()').catch(() => null);
    if (body != null && body !== preBody) return body;
    if (Date.now() - t0 > timeout) return body;
    await sleep(120);
  }
}

/**
 * CDP 原生「编辑命令」派发：`commands:['Copy'|'Paste'|'Undo'|'Redo']`。
 *
 * 为什么不用纯 Ctrl+C / Ctrl+V 按键：headless 下 `Input.dispatchKeyEvent` 只是按键，
 * 浏览器不保证把「Copy/Paste」当成编辑命令执行（实测 copy 事件不触发、剪贴板为空；
 * 而 Ctrl+X 在真机 WebView2 上会卡死 target ⇒ 本探针的 cut 走合成 beforeinput）。
 * `commands` 是 Chromium 专门给编辑器命令的通道，等价用户按快捷键。
 */
async function editCommand(cdp, { key, code, vk, command }) {
  await cdp.send('Input.dispatchKeyEvent', {
    type: 'rawKeyDown', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk,
    modifiers: 2, commands: [command],
  });
  await cdp.send('Input.dispatchKeyEvent', {
    type: 'keyUp', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers: 2,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// 主流程
// ─────────────────────────────────────────────────────────────────────────────
async function runMatrix(cdp, ix, { matrix, file, only, onlyOps, label, origin }) {
  const cases = [];
  const consoleLines = [];
  const setup = {};
  // Runtime.consoleAPICalled 走 ws 推送；CDP 类只处理有 id 的响应，这里旁路收集。
  try {
    cdp.ws.addEventListener('message', (ev) => {
      let m;
      try { m = JSON.parse(String(ev.data)); } catch { return; }
      if (m.method !== 'Runtime.consoleAPICalled') return;
      const parts = (m.params && m.params.args || []).map((a) => {
        if (a.value !== undefined) return String(a.value);
        if (a.description) return String(a.description);
        return '';
      }).join(' ');
      if (!parts) return;
      if (!/deleteMulti|deleteSelection|STYLE|clip|paste|undo|copy/i.test(parts)) return;
      if (consoleLines.length < 4000) consoleLines.push(parts.slice(0, 400));
    });
  } catch { /* 收不到日志也继续 */ }

  await cdp.evalJS(`(${pageHelpers.toString()})()`);
  await cdp.evalJS('window.__SEL.installSpies()');

  // 剪贴板权限（headless Edge 默认拒绝 readText/writeText；grant 后 copy/paste 回读才可用）
  let grantInfo = 'skipped';
  if (origin) {
    try {
      await cdp.send('Browser.grantPermissions', {
        origin, permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite'],
      });
      grantInfo = 'ok';
    } catch (e) {
      grantInfo = 'failed:' + ((e && e.message) || e);
    }
  }
  setup.grantPermissions = grantInfo;

  // 应用默认可能是 source 视图 ⇒ 先切 preview
  await cdp.evalJS('window.__SEL.ensurePreview()');
  await cdp.waitFor('(window.state||{}).viewMode === "preview"', { timeout: 15000, label: 'viewMode' });
  await cdp.evalJS('window.__SEL.forceEditMode()');

  // 打开语料，记录 pristine
  await openFileFresh(cdp, file, 'pristine');
  await sleep(400);
  await cdp.evalJS('window.__SEL.ensurePreview()');
  await cdp.waitFor('document.querySelectorAll("#preview .-src-block").length > 10', { timeout: 30000, label: 'blocks' });
  await settle(cdp);
  const pristine = await cdp.evalJS('window.__SEL.body()');

  // 组装用例清单
  const list = [];
  const opsAll = matrix.ops || ['copy', 'cut', 'delete', 'pasteReplace'];
  const wantOps = onlyOps ? new Set(String(onlyOps).split(',').map((s) => s.trim()).filter(Boolean)) : null;
  const wantIds = only ? String(only).split(',').map((s) => s.trim()).filter(Boolean) : null;
  function want(id) { return !wantIds || wantIds.some((p) => id.indexOf(p) >= 0); }

  for (const g of matrix.groups || []) {
    for (const sp of g.spans || []) {
      const ops = (sp.ops || opsAll).filter((o) => !wantOps || wantOps.has(o));
      for (const op of ops) {
        const id = `${g.id}-${sp.span}-${op}`;
        if (!want(id)) continue;
        list.push({ id, type: g.type, span: sp.span, op, from: sp.from, to: sp.to, selMode: 'programmatic' });
      }
    }
  }
  for (const sb of matrix.sameBlock || []) {
    const ops = (sb.ops || opsAll).filter((o) => !wantOps || wantOps.has(o));
    for (const op of ops) {
      const id = `${sb.id}-${op}`;
      if (!want(id)) continue;
      list.push({ id, type: sb.type, span: sb.span, op, from: sb.from, to: sb.to, selMode: 'programmatic' });
    }
  }
  for (const m of matrix.mixed || []) {
    const ops = (m.ops || opsAll).filter((o) => !wantOps || wantOps.has(o));
    for (const op of ops) {
      const id = `${m.id}-${op}`;
      if (!want(id)) continue;
      list.push({ id, type: m.type, span: m.span, op, from: m.from, to: m.to, selMode: 'programmatic' });
    }
  }
  for (const mc of matrix.mouseCases || []) {
    const ops = (mc.ops || opsAll).filter((o) => !wantOps || wantOps.has(o));
    for (const op of ops) {
      const id = `${mc.id}-${op}`;
      if (!want(id)) continue;
      list.push({ id, type: mc.type, span: mc.span, op, from: mc.from, to: mc.to, selMode: 'mouse' });
    }
  }

  let idx = 0;
  for (const cs of list) {
    idx++;
    const rec = {
      id: cs.id, type: cs.type, span: cs.span, op: cs.op, selMode: cs.selMode,
      checks: {}, failChecks: [], pass: false, error: null, logs: [],
    };
    const logStart = consoleLines.length;
    try {
      // ── 隔离：每例重新打开（openFile 会 resetHistory + 从磁盘重读） ──
      const reset = await resetToPristine(cdp, file, pristine, cs.id);
      if (!reset.ok) {
        let d = 0;
        while (d < (reset.got || '').length && d < pristine.length && reset.got[d] === pristine[d]) d++;
        throw new Error('隔离失败：重开 3 次仍与 pristine 不一致 len=' + (reset.got || '').length + '/' + pristine.length +
          ' at=' + d + ' got=' + JSON.stringify((reset.got || '').slice(Math.max(0, d - 20), d + 40)) +
          ' want=' + JSON.stringify(pristine.slice(Math.max(0, d - 20), d + 40)));
      }
      if (reset.attempts > 1) rec.note = '重开 ' + reset.attempts + ' 次才复位';
      await cdp.evalJS('window.__SEL.ensurePreview()');
      await cdp.evalJS('window.__SEL.forceEditMode()');
      await settle(cdp);
      await cdp.evalJS('window.__SEL.resetClip()');
      const preBody = await cdp.evalJS('window.__SEL.body()');
      // 粘贴用例：剪贴板必须在**建立选区之前**写好（写剪贴板的 textarea 兜底会抢走选区）
      let pasteText = null, clipWrite = null;
      if (cs.op === 'pasteReplace') {
        pasteText = matrix.pasteText || 'PASTEQ zeta9 omega5';
        clipWrite = await cdp.evalJS(`window.__SEL.writeClipboard(${JSON.stringify(pasteText)})`).catch((e) => 'eval-error:' + e.message);
        await sleep(180);
        await cdp.evalJS('window.__SEL.forceEditMode()');
      }
      if (preBody !== pristine) {
        let d = 0;
        while (d < preBody.length && d < pristine.length && preBody[d] === pristine[d]) d++;
        throw new Error('隔离失败：openFile 后与 pristine 不一致 len=' + preBody.length + '/' + pristine.length +
          ' at=' + d + ' got=' + JSON.stringify(preBody.slice(Math.max(0, d - 20), d + 40)) +
          ' want=' + JSON.stringify(pristine.slice(Math.max(0, d - 20), d + 40)));
      }

      // ── 建立选区 ──
      let sel = { ok: false, reason: 'unset' };
      const selLabel = 'selectRange ' + cs.id;
      if (cs.selMode === 'mouse') {
        const pts = await withTimeout(cdp.evalJS(`window.__SEL.endpointPoints(${JSON.stringify(cs.from)}, ${JSON.stringify(cs.to)})`), 20000, 'endpointPoints ' + cs.id);
        if (pts && pts.ok) {
          await ix.drag(pts.start, pts.end, { steps: 14 });
          await sleep(200);
          const info = await withTimeout(cdp.evalJS('window.__SEL.selInfo()'), 20000, 'selInfo ' + cs.id);
          if (info && !info.collapsed && info.anchorBlock != null) {
            // 真实拖拽成立 ⇒ 吸附到词边界（消除半词），记录 how=mouse+snap
            const snap = await cdp.evalJS('window.__SEL.snapSelectionToWords()');
            if (snap && snap.ok) {
              sel = {
                ok: true, how: 'mouse+snap', anchorBlock: snap.fromBlock, focusBlock: snap.toBlock,
                text: snap.text, dragOk: true, snappedWords: snap.count,
              };
            } else {
              sel = { ok: false, reason: 'snap:' + ((snap && snap.reason) || 'unknown'), how: 'mouse' };
            }
          }
        }
        if (!sel.ok) {
          const r2 = await withTimeout(cdp.evalJS(`window.__SEL.selectRange(${JSON.stringify(cs.from)}, ${JSON.stringify(cs.to)})`), 20000, selLabel + ' (fallback)');
          sel = Object.assign({ how: 'programmatic-fallback' }, r2 || {});
        }
      } else {
        const r2 = await withTimeout(cdp.evalJS(`window.__SEL.selectRange(${JSON.stringify(cs.from)}, ${JSON.stringify(cs.to)})`), 20000, selLabel);
        sel = Object.assign({ how: 'programmatic' }, r2 || {});
      }
      rec.selection = { how: sel.how, text: sel.text, anchorBlock: sel.anchorBlock, focusBlock: sel.focusBlock };
      rec.checks.selReady = !!sel.ok;
      if (!sel.ok) {
        rec.selDebug = await cdp.evalJS(
          `window.__SEL.debugSelect(${JSON.stringify(cs.from)}, ${JSON.stringify(cs.to)})`).catch(() => null);
        throw new Error('选区建立失败: ' + (sel.reason || 'unknown'));
      }

      const cov = await cdp.evalJS('window.__SEL.coverage()');
      if (!cov || !cov.ok) throw new Error('覆盖统计失败: ' + ((cov && cov.reason) || 'unknown'));
      rec.coverageMeta = {
        coveredBlocks: cov.coveredBlocks, partialBlocks: cov.partialBlocks,
        anomalies: cov.anomalies, deletedWords: cov.deleted,
      };

      const preTokens = await cdp.evalJS(`window.__SEL.tokensOf(${JSON.stringify(preBody)})`);
      // 操作前 DOM 词集：用于判定「可见被选文字」（MathJax/mermaid 的公式与图内文字
      // 在纯文本剪贴板里本来就不存在；断言不该要求剪贴板包含它们）
      const domToksBefore = await cdp.evalJS('window.__SEL.domTokens()');
      let expectPost = subCounts(preTokens, cov.deleted);
      const deletedCount = Object.keys(cov.deleted).length;

      // ── 执行操作 ──
      let opNote = '';
      let pasteHow = null;
      let clipReadback = null;
      if (cs.op === 'copy') {
        // 复制 = 纯浏览器原生行为（产品无 copy handler）。真实 Ctrl+C 优先；
        // 无头下 copy 事件偶发不触发 ⇒ 退 execCommand('copy')（仍由浏览器 copy 管线填 clipboardData）
        await ix.press('c', { mods: ['ctrl'] });
        await sleep(350);
        let cc = await cdp.evalJS('window.__SEL.clip().copyEvents.length');
        if (!cc) {
          const cr = await cdp.evalJS('window.__SEL.copySelection()');
          opNote = 'copy:execCommand=' + JSON.stringify(cr);
          await sleep(250);
          cc = await cdp.evalJS('window.__SEL.clip().copyEvents.length');
          if (!cc) opNote += ' (copy 事件仍未触发)';
        }
        // copy 事件的 clipboardData 在 capture 阶段可能还没被浏览器填好 ⇒ 以 readText 为准
        clipReadback = await cdp.evalJS('window.__SEL.readClipboard()').catch(() => null);
      } else if (cs.op === 'cut') {
        const r = await cdp.evalJS('window.__SEL.dispatchCut()');
        opNote = 'cut:prevented=' + (r && r.prevented);
        await waitBodyChange(cdp, preBody, 1500);
        await settle(cdp);
      } else if (cs.op === 'delete') {
        await ix.press('Delete');
        await waitBodyChange(cdp, preBody, 1500);
        await settle(cdp);
      } else if (cs.op === 'pasteReplace') {
        opNote = 'clipboardWrite=' + clipWrite;
        // 真实 Ctrl+V 优先；无头下 paste 事件可能不来 ⇒ 合成 ClipboardEvent（同一产品 handler）
        await ix.press('v', { mods: ['ctrl'] });
        let bodyNow = await waitBodyChange(cdp, preBody, 1500);
        let pc = await cdp.evalJS('window.__SEL.clip().pasteEvents.length');
        if (!pc && bodyNow === preBody) {
          const sp = await cdp.evalJS(`window.__SEL.syntheticPaste(${JSON.stringify(pasteText)})`);
          pasteHow = 'synthetic:' + JSON.stringify(sp);
          bodyNow = await waitBodyChange(cdp, preBody, 1500);
        } else {
          pasteHow = 'ctrl+v';
        }
        rec.pasteHow = pasteHow;
        opNote += ' pasteHow=' + pasteHow;
        await settle(cdp);
        const ptoks = await cdp.evalJS(`window.__SEL.tokensOf(${JSON.stringify(pasteText)})`);
        for (const k of Object.keys(ptoks)) expectPost[k] = (expectPost[k] || 0) + ptoks[k];
        rec.pasteText = pasteText;
      }

      const postBody = await cdp.evalJS('window.__SEL.body()');
      const clip = await cdp.evalJS('window.__SEL.clip()');
      const notice = await cdp.evalJS('window.__SEL.notice()');
      const domToksAfterOp = await cdp.evalJS('window.__SEL.domTokens()');
      rec.preBody = preBody; rec.postBody = postBody; rec.notice = notice; rec.opNote = opNote;
      rec.selText = cov.selText;
      // 「只改 DOM、不改源码」证据（E30 同族：原生粘贴/拖拽没被 AST 管线接管时的特征）
      rec.domOnlyChange = (postBody === preBody) &&
        (JSON.stringify(domToksAfterOp) !== JSON.stringify(domToksBefore || {}));
      if (cs.op === 'pasteReplace' && rec.pasteText) {
        const pw = await cdp.evalJS(`window.__SEL.tokensOf(${JSON.stringify(rec.pasteText)})`);
        rec.pastedVisibleInDom = Object.keys(pw).every((w) => !!domToksAfterOp[w]);
      }

      // ── 断言 1：源码词集（复制 = 必须一字不动；其余 = 选中删净 + 未选保留 + 无重复残留） ──
      const isCopy = cs.op === 'copy';
      const postTokens = await cdp.evalJS(`window.__SEL.tokensOf(${JSON.stringify(postBody)})`);
      const rec3 = reconcileFused(expectPost, postTokens);
      const missing = rec3.missing;
      const extra = rec3.extra;
      rec.diff = { missing: missing.slice(0, 12), extra: extra.slice(0, 12), fused: (rec3.fused || []).slice(0, 8), deletedCount };
      if (isCopy) {
        rec.checks.copyNoop = postBody === preBody;
      } else {
        rec.checks.changed = postBody !== preBody;
        rec.checks.deletedGone = Object.keys(cov.deleted).every((w) => !postTokens[w]);
        rec.checks.keptPresent = missing.length === 0;
        rec.checks.noDuplicate = extra.length === 0;
        // task-79 阶段2 断言：**操作没发生 ⇒ 用户必须看到提示**（不许静默）
        if (postBody === preBody) {
          rec.checks.failureNotice = !!(notice && String(notice).trim());
        }
      }

      // ── 断言 2：强制整篇重渲 → 不回魂 / 不改源码 ──
      // 复制不改文档 ⇒ 没有"回魂"语义，跳过重渲省一轮渲染（本矩阵 31 条复制用例）。
      let bodyAfterRender = postBody;
      const domToks = {};
      if (!isCopy) {
        await cdp.evalJS('window.__SEL.renderFull()');
        await cdp.waitFor('window.__RENDER_DONE === true || (typeof window.__RENDER_DONE === "string")', { timeout: 30000, label: 'full-render' })
          .catch(() => null);
        await settle(cdp, { ms: 220, timeout: 8000 });
        bodyAfterRender = await cdp.evalJS('window.__SEL.body()');
        const dt = await cdp.evalJS('window.__SEL.domTokens()');
        Object.assign(domToks, dt || {});
        const ghost = Object.keys(cov.deleted).filter((w) => domToks[w] && !SYNTAX_WORDS.has(w));
        rec.checks.domNoGhost = ghost.length === 0;
        rec.ghost = ghost.slice(0, 12);
      }
      rec.checks.renderStable = bodyAfterRender === postBody;
      rec.bodyAfterRender = bodyAfterRender;

      // ── 断言 3：单次撤销回到操作前（复制必须无撤销单元 ⇒ 撤销不改文档） ──
      await ix.press('z', { mods: ['ctrl'] });
      await sleep(300);
      let undoBody = await cdp.evalJS('window.__SEL.body()');
      if (undoBody === postBody && postBody !== preBody) {
        const api = await cdp.evalJS('window.__SEL.undoOnce()');
        rec.note = (rec.note ? rec.note + '；' : '') + 'Ctrl+Z 未生效，回退 API undo=' + api;
        await sleep(250);
        undoBody = await cdp.evalJS('window.__SEL.body()');
      }
      rec.undoBody = undoBody;
      rec.checks.singleUndo = undoBody === preBody;

      // ── 断言 4：剪贴板 ──
      // 注意：`Selection.toString()` 在 contenteditable=false（表格/代码/公式）边界上**会丢文本**
      // （实测：真实剪贴板里有 C1+C2，toString() 只有 C1）⇒ 剪贴板正确性一律用**词集覆盖**判定：
      // 选中范围内每个词都必须出现在剪贴板文本里；缺失即「复制/剪切丢内容」。
      const clipWrites = (clip && clip.writes) || [];
      const clipCopies = (clip && clip.copyEvents) || [];
      const clipPastes = (clip && clip.pasteEvents) || [];
      const coveredWords = Object.keys(cov.deleted);
      // 剪贴板只应包含「可见内容词」：围栏信息（python/mermaid/graph/TD）与 MathJax/mermaid
      // 渲染后不在纯文本里的词（M1/MM1 等）不可能进剪贴板 ⇒ 用操作前 DOM 词集过滤。
      const clipCoveredWords = coveredWords.filter((w) => !SYNTAX_WORDS.has(w) && !!domToksBefore[w]);
      let clipText = null, clipSource = null;
      if (isCopy) {
        const got = clipCopies.length ? clipCopies[clipCopies.length - 1] : null;
        const rb = (typeof clipReadback === 'string' && clipReadback.indexOf('OK:') === 0) ? clipReadback.slice(3) : null;
        clipText = (rb != null && rb !== '') ? rb : got;
        clipSource = 'copyEvent/readText';
      } else if (cs.op === 'cut') {
        clipText = clipWrites.length ? clipWrites[clipWrites.length - 1] : null;
        clipSource = 'clipboard.writeText(spied)';
      } else if (cs.op === 'pasteReplace') {
        clipText = clipPastes.length ? clipPastes[clipPastes.length - 1] : null;
        clipSource = 'pasteEvent';
      }
      if (cs.op === 'copy' || cs.op === 'cut') {
        let clipTok = {};
        if (clipText) clipTok = await cdp.evalJS(`window.__SEL.tokensOf(${JSON.stringify(String(clipText))})`);
        const missingClip = clipCoveredWords.filter((w) => !clipTok[w]);
        rec.clipboard = {
          source: clipSource, text: clipText == null ? null : String(clipText).slice(0, 400),
          coveredCount: clipCoveredWords.length, missingCovered: missingClip.slice(0, 12),
        };
        rec.checks.clipboard = clipCoveredWords.length > 0 && missingClip.length === 0;
      } else if (cs.op === 'pasteReplace') {
        rec.clipboard = {
          source: clipSource, text: clipText == null ? null : String(clipText).slice(0, 200),
          want: rec.pasteText, count: clipPastes.length,
        };
        rec.checks.clipboard = clipPastes.length > 0 && norm(clipText) === norm(rec.pasteText);
      } else {
        rec.checks.clipboard = true;   // 删除不涉及剪贴板
      }

      rec.logs = consoleLines.slice(logStart).slice(-14);
      rec.failChecks = Object.keys(rec.checks).filter((k) => !rec.checks[k]);
      rec.pass = rec.failChecks.length === 0;
    } catch (e) {
      rec.error = String((e && e.message) || e);
      rec.failChecks = Object.keys(rec.checks).filter((k) => !rec.checks[k]);
      if (!rec.failChecks.length) rec.failChecks = ['selReady'];
      rec.pass = false;
      try { rec.logs = consoleLines.slice(logStart).slice(-14); } catch { /* noop */ }
    }
    cases.push(rec);
    process.stdout.write(`[sel] ${idx}/${list.length} ${rec.pass ? 'PASS' : 'FAIL'} ${rec.id}` +
      (rec.error ? ' :: ' + rec.error : '') + '\n');
  }

  return { cases, setup };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.matrix || !args.out) throw new Error('需要 --matrix 与 --out');
  const matrix = JSON.parse(fs.readFileSync(args.matrix, 'utf8'));
  const file = args.file || matrix.file || 'selection-matrix.md';
  const label = args.label || null;
  const startedAt = new Date().toISOString();
  const run = async (cdp, ix, env) => {
    // 全局 CDP 超时守护：任何一条命令 45s 不返回 ⇒ 抛错定位（否则未 settle 的 promise
    // 会让 node 静默 exit(0) 或挂死，把基础设施故障误诊成用例逻辑）。
    const _send = cdp.send.bind(cdp);
    cdp.send = (m, p = {}) => {
      if (process.env.SEL_TRACE) process.stderr.write('[cdp] ' + m + '\n');
      return withTimeout(_send(m, p), 45000, 'CDP ' + m);
    };
    const origin = env.live && env.target && env.target.url
      ? new URL(env.target.url).origin
      : (args.url ? new URL(args.url).origin : null);
    const { cases, setup } = await runMatrix(cdp, ix, {
      matrix, file, only: args.only && args.only !== true ? args.only : '',
      onlyOps: args['only-ops'] && args['only-ops'] !== true ? args['only-ops'] : '',
      label, origin,
    });
    const passed = cases.filter((c) => c.pass).length;
    return {
      schema: 'memoria-selection-matrix-run/v1',
      startedAt, finishedAt: new Date().toISOString(),
      label, matrix: path.basename(args.matrix), file,
      live: !!env.live, liveTarget: env.live ? env.target : null,
      browser: env.browser,
      meta: { mode: env.live ? 'attach' : 'headless', browser: env.browser, setup },
      summary: { total: cases.length, pass: passed, fail: cases.length - passed },
      cases,
    };
  };

  const out = args['cdp-port']
    ? await withLiveApp(parseInt(args['cdp-port'], 10), run)
    : await withBrowser(args.url, run);

  fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
  fs.writeFileSync(args.out, JSON.stringify(out, null, 2), 'utf8');
  process.stdout.write('__SELECTION_JSON__' + JSON.stringify({
    ok: out.summary.fail === 0, out: args.out, summary: out.summary, live: out.live,
  }) + '\n');
  process.exit(0);
}

main().catch((e) => {
  process.stderr.write(String((e && e.stack) || e) + '\n');
  process.exit(1);
});
