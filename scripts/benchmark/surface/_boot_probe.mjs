#!/usr/bin/env node
/**
 * _boot_probe.mjs —— 真机 WebView2 冷启动**分阶段**探针（task-69 测量阶段）
 *
 * 与 `realapp_probe.mjs` 的分工：
 *   · realapp_probe = attach 后读一次状态（可用性）；
 *   · 本脚本 = 从**进程启动**开始按时间轴记录：CDP 目标出现 → attach → 首次导航 →
 *     桥就绪 → 每个 RPC 往返 → 各渲染/状态里程碑，并可对同一页面做一次
 *     **注入式重载**（`Page.addScriptToEvaluateOnNewDocument` 在 document_start 打点），
 *     把前端阶段拆到毫秒级。
 *
 * 用法（一般由 run_boot_profile.py 调用）：
 *   node scripts/benchmark/surface/_boot_probe.mjs \
 *     --port 9661 --out <raw.json> --launch-epoch <ms> [--no-reload] [--boot-timeout 120000]
 *
 * 设计纪律（踩过的坑都在这）：
 *   1. **轮询写在 node 侧**（每次 Runtime.evaluate 立即返回）；页面内不跑 async 轮询，
 *      避免 `awaitPromise` 超时把 target 拖死。
 *   2. 折叠 range 的 `getBoundingClientRect()` 恒为 0 ⇒ 里程碑一律用**元素 rect / 选择器命中**，
 *      不用 Range。
 *   3. 视图复位：`openFile` 后 viewMode 可能被改写 ⇒ 本脚本只**记录** `state.viewMode` 的变化序列，
 *      不假定它是 preview，也不主动切视图。
 *   4. 只读：不改 KB、不写 localStorage（除了页面自己写）、不点按钮。
 *
 * 输出 schema：memoria-boot-probe/v1
 */

import fs from 'node:fs';
import path from 'node:path';

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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function httpJson(url, timeoutMs = 2000) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    return await r.json();
  } finally { clearTimeout(to); }
}

/** 极简 CDP 客户端（与 realapp_probe.mjs 同款；事件订阅版） */
class CDP {
  constructor(ws) {
    this.ws = ws;
    this._id = 0;
    this._pending = new Map();
    this._listeners = new Map();
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
  on(method, fn) {
    if (!this._listeners.has(method)) this._listeners.set(method, []);
    this._listeners.get(method).push(fn);
  }
  _onMessage(data) {
    let msg;
    try { msg = JSON.parse(typeof data === 'string' ? data : String(data)); } catch { return; }
    if (msg.id == null) {
      const fns = this._listeners.get(msg.method);
      if (fns) for (const fn of fns) { try { fn(msg.params || {}); } catch { /* noop */ } }
      return;
    }
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
  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: false, userGesture: false,
    });
    if (r && r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error('evalJS 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]);
    }
    return r && r.result ? r.result.value : undefined;
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

/**
 * document_start 注入脚本。
 * 目标：**不依赖产品任何测试钩子**，只按 DOM/公开对象/事件打点：
 *   · PerformanceObserver: paint / longtask（真机主线程阻塞证据）
 *   · console.log 包装：抓产品自带的 [boot]/[initKb] 日志（精确阶段边界）
 *   · 'memoriaready' 事件（bridge.js 派发）：桥就绪，并在此把 memoria.api 的每个 RPC 套上计时
 *   · window.MemoriaApp / window.state 赋值拦截 + 关键字段 setter：状态里程碑
 *   · rAF 循环：首帧 / pywebview api 出现 / DOM 命中（文件树、编辑器行、预览块）
 * 所有时间都是相对 document_start 的 performance.now()；`timeOrigin` 可与 epoch 对齐。
 */
const INJECT = String.raw`
(function () {
  if (window.__BOOTPROBE__) return;
  var perf = window.performance || {};
  var T0 = (perf.now ? perf.now() : Date.now());
  var P = {
    t0: +T0.toFixed(3),
    timeOrigin: perf.timeOrigin || null,
    marks: [],
    console: [],
    rpc: [],
    longtasks: [],
    stateSeq: [],
    dom: {},
    readyStateSeq: [],
    nav: null,
    paints: [],
    frames: 0,
    has: {}
  };
  window.__BOOTPROBE__ = P;
  function nowMs() { return (perf.now ? perf.now() : Date.now()); }
  function rel(t) { return +(t - T0).toFixed(1); }
  function mark(name, extra) {
    var m = { name: name, t: rel(nowMs()), wall: Date.now() };
    if (extra) for (var k in extra) m[k] = extra[k];
    P.marks.push(m);
    return m;
  }
  mark('document_start', { readyState: document.readyState });

  // ── paint / longtask ────────────────────────────────────────────────
  try {
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (e) {
        var rec = { name: e.name, start: +(e.startTime).toFixed(1), t: rel(e.startTime), wall: Date.now() };
        P.paints.push(rec);
        mark('paint:' + e.name, { start: rec.start });
      });
    }).observe({ type: 'paint', buffered: true });
  } catch (e) { P.has.paintObserver = false; }
  try {
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (e) {
        P.longtasks.push({ start: +(e.startTime).toFixed(1), dur: +(e.duration).toFixed(1), name: e.name, wall: Date.now() });
      });
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) { P.has.longtaskObserver = false; }

  // ── console.log（产品自带 [boot]/[initKb] 日志）─────────────────────
  try {
    var origLog = console.log;
    console.log = function () {
      try {
        var parts = [];
        for (var i = 0; i < arguments.length; i++) {
          var a = arguments[i];
          parts.push(typeof a === 'string' ? a : String(a));
        }
        P.console.push({ t: rel(nowMs()), wall: Date.now(), msg: parts.join(' ').slice(0, 500) });
      } catch (e) { /* noop */ }
      return origLog.apply(console, arguments);
    };
  } catch (e) { /* noop */ }

  // ── readyState 序列 ─────────────────────────────────────────────────
  try {
    document.addEventListener('readystatechange', function () {
      P.readyStateSeq.push({ t: rel(nowMs()), state: document.readyState });
      mark('readyState:' + document.readyState);
    });
  } catch (e) { /* noop */ }

  // ── RPC 计时：memoria.api 的每个方法 ────────────────────────────────
  function hookApi() {
    try {
      var api = window.memoria && window.memoria.api;
      if (!api || api.__bootprobe_hooked) return false;
      var wrapped = {};
      var count = 0;
      for (var k in api) {
        var v = api[k];
        if (typeof v === 'function') {
          (function (name, fn) {
            wrapped[name] = function () {
              var t0 = nowMs();
              var rec = { fn: name, t: rel(t0), wall: Date.now() };
              if (arguments.length && Array.isArray(arguments[0])) rec.arg0len = arguments[0].length;
              var ret;
              try {
                ret = fn.apply(api, arguments);
              } catch (e) {
                rec.ms = +(nowMs() - t0).toFixed(1);
                rec.syncErr = String(e);
                P.rpc.push(rec);
                throw e;
              }
              if (ret && typeof ret.then === 'function') {
                P.rpc.push(rec);
                return ret.then(function (r) {
                  rec.ms = +(nowMs() - t0).toFixed(1);
                  return r;
                }, function (e) {
                  rec.ms = +(nowMs() - t0).toFixed(1);
                  rec.err = String(e);
                  throw e;
                });
              }
              rec.ms = +(nowMs() - t0).toFixed(1);
              rec.sync = true;
              P.rpc.push(rec);
              return ret;
            };
          })(k, v);
          count++;
        } else {
          wrapped[k] = v;
        }
      }
      wrapped.__bootprobe_hooked = true;
      window.memoria.api = wrapped;
      mark('api_hooked', { count: count });
      return true;
    } catch (e) {
      mark('api_hook_error', { err: String(e) });
      return false;
    }
  }
  window.addEventListener('memoriaready', function () {
    mark('bridge_ready');
    if (!hookApi()) { setTimeout(hookApi, 0); setTimeout(hookApi, 50); }
  }, { once: false });

  // ── MemoriaApp / state 拦截 ─────────────────────────────────────────
  try {
    var _app;
    Object.defineProperty(window, 'MemoriaApp', {
      configurable: true,
      get: function () { return _app; },
      set: function (v) { _app = v; mark('memoriaapp_defined'); }
    });
  } catch (e) { /* noop */ }

  function hookState(st) {
    var keys = ['kbPath', 'files', 'dirs', 'graphData', 'graphAudit', 'doc', 'currentPath',
                'viewMode', 'kbValidateReport', 'openTabs', 'kbPending'];
    keys.forEach(function (k) {
      var val = st[k];
      try {
        Object.defineProperty(st, k, {
          configurable: true,
          enumerable: true,
          get: function () { return val; },
          set: function (nv) {
            val = nv;
            var info = { key: k, t: rel(nowMs()), wall: Date.now() };
            if (Array.isArray(nv)) info.len = nv.length;
            else if (typeof nv === 'string') info.len = nv.length;
            else if (nv && typeof nv === 'object') {
              if (Array.isArray(nv.files)) info.n_files = nv.files.length;
              if (Array.isArray(nv.nodes)) info.n_nodes = nv.nodes.length;
              if (Array.isArray(nv.edges)) info.n_edges = nv.edges.length;
              if (nv.status) info.status = String(nv.status);
            }
            var j = 0;
            for (var i = 0; i < P.stateSeq.length; i++) if (P.stateSeq[i].key === k) j = i + 1;
            P.stateSeq.push(info);
            if (j === 0) mark('state:' + k, { len: info.len });
          }
        });
      } catch (e) { /* noop */ }
    });
    mark('state_hooked');
  }
  try {
    var _state;
    Object.defineProperty(window, 'state', {
      configurable: true,
      get: function () { return _state; },
      set: function (v) { _state = v; hookState(v); }
    });
  } catch (e) { /* noop */ }

  // ── rAF 循环：首帧 / pywebview api / DOM 里程碑 ─────────────────────
  var sel = {
    'dom:file-tree-items': '#file-tree .-tree-item, #file-tree li, #file-tree a',
    'dom:editor-lines': '#editor .-line',
    'dom:preview-blocks': '#preview .-src-block',
    'dom:preview-content': '#preview .-preview-content',
    'dom:welcome': '#welcome, .-welcome'
  };
  var seen = {};
  function pollDom() {
    try {
      for (var name in sel) {
        if (seen[name]) continue;
        if (document.querySelector(sel[name])) {
          seen[name] = true;
          P.dom[name] = rel(nowMs());
          mark(name);
        }
      }
    } catch (e) { /* noop */ }
  }
  function raf() {
    P.frames += 1;
    if (P.frames === 1) mark('first_raf');
    if (P.frames === 2) mark('second_raf');
    if (!P.has.pywebviewApi && window.pywebview && window.pywebview.api) {
      P.has.pywebviewApi = true;
      mark('pywebview_api');
    }
    pollDom();
    window.requestAnimationFrame(raf);
  }
  try { window.requestAnimationFrame(raf); } catch (e) { /* noop */ }

  // ── dump ────────────────────────────────────────────────────────────
  window.__BOOTPROBE_DUMP__ = function () {
    var nav = null;
    try {
      var ns = performance.getEntriesByType('navigation');
      if (ns && ns.length) {
        nav = {
          type: ns[0].type,
          startTime: +ns[0].startTime.toFixed(1),
          responseStart: +ns[0].responseStart.toFixed(1),
          responseEnd: +ns[0].responseEnd.toFixed(1),
          domInteractive: +ns[0].domInteractive.toFixed(1),
          domContentLoadedEventEnd: +ns[0].domContentLoadedEventEnd.toFixed(1),
          loadEventEnd: +ns[0].loadEventEnd.toFixed(1),
          transferSize: ns[0].transferSize,
          decodedBodySize: ns[0].decodedBodySize
        };
      }
    } catch (e) { /* noop */ }
    var st = window.state || {};
    var snap = {
      readyState: document.readyState,
      t0: P.t0,
      timeOrigin: P.timeOrigin,
      tNow: +nowMs().toFixed(1),
      wallNow: Date.now(),
      nav: nav,
      paints: P.paints,
      longtasks: P.longtasks,
      marks: P.marks,
      stateSeq: P.stateSeq,
      console: P.console,
      rpc: P.rpc,
      dom: P.dom,
      frames: P.frames,
      has: P.has,
      runtime: {
        kbPath: st.kbPath || null,
        files: (st.files || []).length,
        currentPath: st.currentPath || null,
        viewMode: st.viewMode || null,
        graphNodes: (st.graphData && st.graphData.nodes) ? st.graphData.nodes.length : null,
        validateReport: !!st.kbValidateReport,
        docLines: (st.doc && st.doc.lines) ? st.doc.lines.length : null,
        previewBlocks: 0,
        editMode: !!(window.MemoriaEditHandler && window.MemoriaEditHandler.editMode)
      },
      storage: (function () {
        try {
          var keys = [];
          for (var i = 0; i < localStorage.length; i++) keys.push(localStorage.key(i));
          return { href: location.href, origin: location.origin, keys: keys, view: localStorage.getItem('-view') };
        } catch (e) { return { error: String(e) }; }
      })()
    };
    try {
      snap.runtime.previewBlocks = document.querySelectorAll('#preview .-src-block').length;
      snap.runtime.previewChildren = (document.querySelector('#preview .-preview-content') || { childElementCount: 0 }).childElementCount;
      snap.runtime.editorLines = document.querySelectorAll('#editor .-line').length;
      snap.runtime.fileTreeItems = document.querySelectorAll('#file-tree .-tree-item, #file-tree li').length;
    } catch (e) { /* noop */ }
    try {
      var M = window.MemoriaApp;
      if (M && typeof M.previewCacheScores === 'function') {
        var s = M.previewCacheScores();
        snap.lastSwitch = {
          ms: s.lastSwitchMs,
          hit: s.lastSwitchHit,
          phases: s.lastSwitchPhases || null,
          parts: s.lastSwitchParts || null,
          async: s.lastSwitchAsync || null,
          entries: s.entries
        };
      }
    } catch (e) { snap.lastSwitchError = String(e); }
    return snap;
  };
})();
`;

/** 页面侧状态快照（node 轮询用；纯同步、立即返回） */
const STATE_EXPR = `(function(){
  var s = window.state || {};
  var r = {
    hasApp: !!window.MemoriaApp,
    hasState: !!window.state,
    readyState: document.readyState,
    kbPath: !!s.kbPath,
    files: (s.files || []).length,
    graphNodes: (s.graphData && s.graphData.nodes) ? s.graphData.nodes.length : 0,
    validateReport: !!s.kbValidateReport,
    currentPath: s.currentPath || null,
    viewMode: s.viewMode || null,
    docLines: (s.doc && s.doc.lines) ? s.doc.lines.length : 0,
    previewBlocks: document.querySelectorAll('#preview .-src-block').length,
    editorLines: document.querySelectorAll('#editor .-line').length,
    fileTreeItems: document.querySelectorAll('#file-tree .-tree-item, #file-tree li').length,
    probe: !!window.__BOOTPROBE__
  };
  return r;
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const port = parseInt(args.port || '9661', 10);
  const out = args.out || '';
  const launchEpoch = Number(args['launch-epoch'] || 0) || Date.now();
  const doReload = !args['no-reload'];
  const bootTimeout = parseInt(args['boot-timeout'] || '120000', 10);
  const reloadTimeout = parseInt(args['reload-timeout'] || '120000', 10);
  const nodeStart = Date.now();
  const tRel = (ms) => +(ms - launchEpoch);

  const result = {
    schema: 'memoria-boot-probe/v1',
    port,
    launchEpoch,
    nodeStartEpoch: nodeStart,
    nodeStartRelMs: tRel(nodeStart),
    reload: doReload,
    events: [],
    targets: [],
    firstBoot: null,
    instrumented: null,
    ok: false,
    error: null,
    limitations: [
      '真机 WebView2 + 真实窗口（非无头）；CDP 通过 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port 介入。',
      '首次导航可能在 attach 之前已开始 ⇒ 首次导航只能取 performance 的 navigation/paint 条目 + 里程碑轮询（node 侧 100ms）；注入式重载给毫秒级分阶段，但其资产/OS 缓存已暖 ⇒ 各段比首次略低。',
      'RPC 计时来自页面侧包装 memoria.api（每方法耗时含 JS 桥 + Python 执行 + 返回），Python 侧净执行时间见 boot-timeline 的 backendSpans。'
    ]
  };
  const pushEvent = (name, extra) => {
    result.events.push(Object.assign({ name, recvRelMs: tRel(Date.now()), recvEpoch: Date.now() }, extra || {}));
  };

  let cdp = null;
  let exitCode = 1;
  try {
    // ── 1) 等 CDP 端口 ───────────────────────────────────────────────
    const tCdp0 = Date.now();
    let version = null;
    for (;;) {
      try { version = await httpJson(`http://127.0.0.1:${port}/json/version`); break; } catch { /* retry */ }
      if (Date.now() - tCdp0 > 120000) throw new Error('CDP 端口 120s 未就绪');
      await sleep(25);
    }
    result.browser = version.Browser;
    result.cdpPortReadyRelMs = tRel(Date.now());
    pushEvent('cdp_port_ready');

    // ── 2) 等应用页面目标（并记录 URL/端口快照）───────────────────────
    let target = null;
    const tTarget0 = Date.now();
    const targetsSeen = [];
    for (;;) {
      try {
        const list = await httpJson(`http://127.0.0.1:${port}/json/list`, 2000);
        const pages = (list || []).filter((t) => t.type === 'page' && t.webSocketDebuggerUrl &&
          !/^devtools:\/\//.test(t.url || ''));
        if (pages.length) {
          targetsSeen.push({ relMs: tRel(Date.now()), pages: pages.map((p) => ({ id: p.id, url: p.url, title: p.title })) });
          const app = pages.find((p) => /^http:\/\/127\.0\.0\.1:\d+/.test(p.url || '') || /^http:\/\/localhost/.test(p.url || ''));
          if (app) { target = app; break; }
        }
      } catch { /* retry */ }
      if (Date.now() - tTarget0 > 120000) throw new Error('120s 未见应用页面目标');
      await sleep(25);
    }
    result.targets = targetsSeen.slice(0, 400);
    result.targetFirstSeenRelMs = targetsSeen.length ? targetsSeen[0].relMs : null;
    result.target = { id: target.id, url: target.url, title: target.title };
    try {
      const u = new URL(target.url);
      result.origin = u.origin;
      result.httpPort = Number(u.port || 80);
    } catch { /* noop */ }
    pushEvent('page_target_found');

    // ── 3) attach ────────────────────────────────────────────────────
    cdp = await CDP.connect(target.webSocketDebuggerUrl);
    result.attachRelMs = tRel(Date.now());
    pushEvent('cdp_attached');
    await cdp.send('Runtime.enable');
    try { await cdp.send('Page.enable'); } catch { /* noop */ }
    try { await cdp.send('Page.setLifecycleEventsEnabled', { enabled: true }); } catch { /* noop */ }
    try { await cdp.send('Log.enable'); } catch { /* noop */ }

    cdp.on('Page.frameStartedLoading', () => pushEvent('frame_started_loading'));
    cdp.on('Page.frameNavigated', (p) => pushEvent('frame_navigated', { url: (p.frame || {}).url }));
    cdp.on('Page.domContentEventFired', () => pushEvent('dom_content_loaded'));
    cdp.on('Page.loadEventFired', () => pushEvent('load_event_fired'));
    cdp.on('Page.lifecycleEvent', (p) => pushEvent('lifecycle:' + (p.name || ''), { ts: p.timestamp }));
    cdp.on('Runtime.consoleAPICalled', (p) => {
      const txt = (p.args || []).map((a) => (a.value !== undefined ? String(a.value) : (a.description || ''))).join(' ').slice(0, 500);
      pushEvent('console', { level: p.type, text: txt, ts: p.timestamp, wallMs: p.timestamp ? Math.round(p.timestamp * 1000) : null, relFromLaunchMs: p.timestamp ? Math.round(p.timestamp * 1000 - launchEpoch) : null });
    });

    // ── 4) 安装 document_start 注入（对**下一次**导航生效）───────────
    await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: INJECT });
    result.injectInstalledRelMs = tRel(Date.now());
    pushEvent('inject_installed');

    // ── 5) 首次导航现状快照 + 里程碑轮询（不 reload）────────────────
    const first = {
      milestones: {},
      snapshots: [],
      stateAtAttach: null,
      navAtAttach: null,
      bootComplete: false
    };
    const firstT0 = Date.now();
    const observe = async (bucket) => {
      let st;
      try { st = await cdp.evalJS(STATE_EXPR); } catch { return null; }
      if (!st) return null;
      const now = Date.now();
      for (const k of ['hasApp', 'kbPath', 'files', 'graphNodes', 'validateReport', 'currentPath', 'previewBlocks', 'editorLines', 'fileTreeItems', 'probe']) {
        const v = st[k];
        const truthy = (typeof v === 'number') ? v > 0 : !!v;
        if (truthy && bucket.milestones[k] === undefined) {
          bucket.milestones[k] = tRel(now);
          pushEvent('milestone:' + k, { value: v, epoch: now });
        }
      }
      return st;
    };
    first.stateAtAttach = await observe(first);
    try {
      first.navAtAttach = await cdp.evalJS(`(function(){
        var n = performance.getEntriesByType('navigation')[0];
        return n ? {type:n.type, responseEnd:+n.responseEnd.toFixed(1), domInteractive:+n.domInteractive.toFixed(1),
                    domContentLoadedEventEnd:+n.domContentLoadedEventEnd.toFixed(1), loadEventEnd:+n.loadEventEnd.toFixed(1),
                    timeOrigin: performance.timeOrigin} : null;
      })()`);
    } catch { /* noop */ }

    const bootDone = (st) => !!(st && st.currentPath && (st.previewBlocks > 0 || st.editorLines > 0));

    let lastSnapStr = '';
    while (Date.now() - firstT0 < bootTimeout) {
      const st = await observe(first);
      if (st) {
        const key = [st.kbPath, st.files, st.graphNodes, st.validateReport, st.currentPath, st.previewBlocks, st.editorLines].join('|');
        if (key !== lastSnapStr) {
          lastSnapStr = key;
          first.snapshots.push({ relMs: tRel(Date.now()), st });
        }
        if (bootDone(st)) { first.bootComplete = true; break; }
      }
      await sleep(100);
    }
    result.firstBoot = first;
    pushEvent('first_boot_done', { complete: first.bootComplete });

    // 首次导航的最终快照（含 lastSwitch / storage / nav 条目）
    if (!first.bootComplete && !(await cdp.evalJS('!!window.MemoriaApp'))) {
      // 页面可能还没开始跑我们的状态轮询：直接取一次原始快照
    }
    try {
      const probePresent = await cdp.evalJS('!!window.__BOOTPROBE__');
      if (probePresent) {
        first.final = await cdp.evalJS('window.__BOOTPROBE_DUMP__()');
      }
      first.raw = await cdp.evalJS(`(function(){
        var n = performance.getEntriesByType('navigation')[0] || null;
        var p = performance.getEntriesByType('paint').map(function(e){return {name:e.name,start:+e.startTime.toFixed(1)};});
        var st = window.state || {};
        var ls = {}; try { for (var i=0;i<localStorage.length;i++){var k=localStorage.key(i); ls[k]=localStorage.getItem(k);} } catch(e){}
        return {
          readyState: document.readyState,
          timeOrigin: performance.timeOrigin,
          href: location.href, origin: location.origin,
          nav: n ? {type:n.type, responseStart:+n.responseStart.toFixed(1), responseEnd:+n.responseEnd.toFixed(1),
                    domInteractive:+n.domInteractive.toFixed(1), domContentLoadedEventEnd:+n.domContentLoadedEventEnd.toFixed(1),
                    loadEventEnd:+n.loadEventEnd.toFixed(1)} : null,
          paints: p,
          runtime: {kbPath: st.kbPath||null, files:(st.files||[]).length, currentPath: st.currentPath||null,
                    viewMode: st.viewMode||null, docLines:(st.doc&&st.doc.lines)?st.doc.lines.length:null,
                    previewBlocks: document.querySelectorAll('#preview .-src-block').length,
                    editorLines: document.querySelectorAll('#editor .-line').length,
                    graphNodes:(st.graphData&&st.graphData.nodes)?st.graphData.nodes.length:null},
          storage: {origin: location.origin, keys: Object.keys(ls), view: ls['-view'] || null}
        };
      })()`);
      try {
        first.lastSwitch = await cdp.evalJS(`(function(){
          var M = window.MemoriaApp; if (!M || typeof M.previewCacheScores !== 'function') return null;
          var s = M.previewCacheScores();
          return {ms:s.lastSwitchMs, hit:s.lastSwitchHit, phases:s.lastSwitchPhases||null,
                  parts:s.lastSwitchParts||null, async:s.lastSwitchAsync||null, entries:s.entries};
        })()`);
      } catch (e) { first.lastSwitchError = String(e); }
    } catch (e) { first.snapshotError = String(e); }

    // ── 6) 注入式重载：毫秒级分阶段 ──────────────────────────────────
    if (doReload) {
      const rel = { milestones: {}, samples: [], events: [], complete: false };
      const markIdx = result.events.length;
      pushEvent('reload_requested');
      await cdp.send('Page.reload', { ignoreCache: false });
      const tReload = Date.now();
      rel.reloadRequestedRelMs = tRel(tReload);
      while (Date.now() - tReload < reloadTimeout) {
        let st;
        try { st = await cdp.evalJS(STATE_EXPR); } catch { st = null; }
        if (st) {
          const now = Date.now();
          for (const k of ['probe', 'hasApp', 'kbPath', 'files', 'graphNodes', 'validateReport', 'currentPath', 'previewBlocks', 'editorLines', 'fileTreeItems']) {
            const v = st[k];
            const truthy = (typeof v === 'number') ? v > 0 : !!v;
            if (truthy && rel.milestones[k] === undefined) {
              rel.milestones[k] = tRel(now);
              pushEvent('reload-milestone:' + k, { value: v, epoch: now });
            }
          }
          if (st.currentPath && (st.previewBlocks > 0 || st.editorLines > 0)) { rel.complete = true; break; }
        }
        await sleep(100);
      }
      rel.events = result.events.slice(markIdx);
      try {
        rel.dump = await cdp.evalJS('window.__BOOTPROBE_DUMP__ ? window.__BOOTPROBE_DUMP__() : null');
      } catch (e) { rel.dumpError = String(e); }
      if (rel.dump) {
        rel.absolute = {
          timeOrigin: rel.dump.timeOrigin,
          marks: rel.dump.marks.map((m) => ({ name: m.name, t: m.t, epoch: (rel.dump.timeOrigin || 0) + m.t })),
          paints: (rel.dump.paints || []).map((p) => ({ name: p.name, start: p.start, epoch: (rel.dump.timeOrigin || 0) + p.start })),
          stateSeq: (rel.dump.stateSeq || []).map((s) => ({ key: s.key, t: s.t, epoch: (rel.dump.timeOrigin || 0) + s.t, len: s.len })),
          console: (rel.dump.console || []).map((c) => ({ t: c.t, epoch: (rel.dump.timeOrigin || 0) + c.t, msg: c.msg })),
          rpc: (rel.dump.rpc || []).map((r) => ({ fn: r.fn, t: r.t, epoch: (rel.dump.timeOrigin || 0) + r.t, ms: r.ms, err: r.err }))
        };
      }
      result.instrumented = rel;
      pushEvent('reload_done', { complete: rel.complete });
    }

    // ── 7) 可选：切换视图（source/preview/split）后再额外打开一个文档 ─────
    if (args['extra-open'] && args['extra-open-view']) {
      const wanted = String(args['extra-open-view']);
      try {
        const clicked = await cdp.evalJS(`(function(){ var b=document.querySelector('.-view-btn[data-view="${wanted}"]'); if(!b) return false; b.click(); return true; })()`);
        result.extraOpenViewClick = { wanted, clicked: !!clicked };
        const tView = Date.now();
        while (Date.now() - tView < 15000) {
          const st = await cdp.evalJS(`(function(){ var s=window.state||{}; return {viewMode: s.viewMode||null, previewBlocks: document.querySelectorAll('#preview .-src-block').length}; })()`);
          if (st && st.viewMode === wanted) break;
          await sleep(100);
        }
        await sleep(300); // 等这次切换的渲染落定
        result.extraOpenViewClick.settledViewMode = (await cdp.evalJS(`(window.state||{}).viewMode || null`));
        result.extraOpenViewClick.settleMs = tRel(Date.now());
      } catch (e) { result.extraOpenViewClick = { error: String(e) }; }
    }
    if (args['extra-open']) {
      const openPath = String(args['extra-open']);
      const ex = { path: openPath, done: false };
      try {
        const prev = await cdp.evalJS(`(function(){ var M=window.MemoriaApp;
          if (!M || typeof M.previewCacheScores !== 'function') return null;
          var s = M.previewCacheScores(); return s ? { ms: s.lastSwitchMs, path: (window.state||{}).currentPath || null } : null; })()`);
        ex.before = prev;
        await cdp.evalJS(`(function(){ window.__OPENPROBE__ = { t0: performance.now(), done: false, err: null };
          try {
            var p = window.MemoriaApp.openFile(${JSON.stringify(openPath)}, {});
            if (p && p.then) p.then(function(){ window.__OPENPROBE__.done = true; }, function(e){ window.__OPENPROBE__.err = String(e); });
            else window.__OPENPROBE__.done = true;
          } catch (e) { window.__OPENPROBE__.err = String(e); }
          return true; })()`);
        const tOpen = Date.now();
        while (Date.now() - tOpen < 60000) {
          const st = await cdp.evalJS(`(function(){ var s = window.state || {};
            return { op: window.__OPENPROBE__ || null, currentPath: s.currentPath || null,
                     editorLines: document.querySelectorAll('#editor .-line').length,
                     previewBlocks: document.querySelectorAll('#preview .-src-block').length }; })()`);
          if (st && st.op && (st.op.done || st.op.err)) { ex.done = !!st.op.done; ex.err = st.op.err || null; break; }
          await sleep(100);
        }
        await sleep(500); // 等 tail / 异步 paint 标记落地
        ex.waitRelMs = tRel(tOpen);
        ex.lastSwitch = await cdp.evalJS(`(function(){ var M = window.MemoriaApp;
          if (!M || typeof M.previewCacheScores !== 'function') return null;
          var s = M.previewCacheScores();
          return { ms: s.lastSwitchMs, hit: s.lastSwitchHit, phases: s.lastSwitchPhases || null,
                   parts: s.lastSwitchParts || null, async: s.lastSwitchAsync || null }; })()`);
        ex.runtime = await cdp.evalJS(`(function(){ var s = window.state || {};
          return { currentPath: s.currentPath || null, viewMode: s.viewMode || null,
                   docLines: (s.doc && s.doc.lines) ? s.doc.lines.length : null,
                   editorLines: document.querySelectorAll('#editor .-line').length,
                   previewBlocks: document.querySelectorAll('#preview .-src-block').length }; })()`);
      } catch (e) { ex.error = String((e && e.stack) || e); }
      result.extraOpen = ex;
      pushEvent('extra_open_done', { path: openPath, done: ex.done });
    }

    result.ok = true;
    exitCode = 0;
  } catch (e) {
    result.error = String((e && e.stack) || e);
    result.ok = false;
  } finally {
    result.finishedEpoch = Date.now();
    result.finishedRelMs = tRel(result.finishedEpoch);
    if (cdp) cdp.close();
    const text = JSON.stringify(result, null, 2);
    if (out) {
      fs.mkdirSync(path.dirname(out), { recursive: true });
      fs.writeFileSync(out, text, 'utf8');
      process.stdout.write('__BOOT_PROBE__' + JSON.stringify({ ok: result.ok, out }) + '\n');
    } else {
      process.stdout.write(text + '\n');
    }
    // WebView2 的 browser 级 WS 直接 process.exit 会触发 libuv 断言（realapp_probe 实测）
    setTimeout(() => process.exit(exitCode), 3000).unref();
  }
  return exitCode;
}

if (import.meta.url === `file:///${process.argv[1].replace(/\\/g, '/')}`) {
  const code = await main();
  process.exitCode = code;
}
