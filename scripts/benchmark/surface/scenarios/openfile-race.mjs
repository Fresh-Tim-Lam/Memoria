// task-75：openFile 启动期竞态探针（真机 WebView2）
//
// 为什么用「document_start 注入 + 重载」而不是"抢在导航前 attach"：
//   WebView2 首次导航前 attach 可能拿到导航前的执行上下文（实测拿不到 state），
//   时序不可控；注入脚本在 document_start 先于所有应用脚本执行 ⇒ 能精确落在
//   「MemoriaApp 定义完成的第一个 tick / 自动打开进行中 / 首文档已出」三个窗口内。
//   注入式重载 与 冷启动 走同一条 JS 引导路径（backend 已热，差异会在报告里标注）。
//
// 用法（由 run_openfile_race.py 调起）：
//   node scenarios/openfile-race.mjs --port 9681 --out <json> [--settle 15000]
import fs from 'node:fs';
import { CDP, sleep } from '../interaction.mjs';

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
const port = Number(args.port || 9681);
const out = args.out || 'artifacts/agent/verify/openfile-race.json';
const settle = Number(args.settle || 15000);
const T1 = args.target || 'homework/hw-001-conv-exp-gate.md';
const T2 = args.target2 || '跳转渲染测试.md';

function httpJson(url) {
  return fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);
}

async function waitAppTarget(deadlineMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < deadlineMs) {
    const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
    const pages = (list || []).filter((t) => t.type === 'page' && t.webSocketDebuggerUrl &&
      !/^devtools:\/\//.test(t.url || '') && !/^about:blank$/.test(t.url || ''));
    if (pages.length) return pages[0];
    await sleep(50);
  }
  return null;
}

const INJECT = `(function(){
  if (window.__RACE_INSTALLED__) return;
  window.__RACE_INSTALLED__ = true;
  var R = window.__RACE__ = { t0: Math.round(performance.now()), console: [], calls: [], errors: [], transitions: [] };
  try {
    var orig = { log: console.log, warn: console.warn, error: console.error };
    function cap(lvl) {
      return function () {
        try {
          var parts = [];
          for (var i = 0; i < arguments.length; i++) {
            var a = arguments[i];
            parts.push(typeof a === 'string' ? a : (a && a.message) ? a.message : String(a));
          }
          R.console.push({ t: Math.round(performance.now()), lvl: lvl, text: parts.join(' ') });
          if (R.console.length > 600) R.console.splice(0, 300);
        } catch (e) { /* noop */ }
        return orig[lvl].apply(console, arguments);
      };
    }
    console.log = cap('log'); console.warn = cap('warn'); console.error = cap('error');
  } catch (e) { R.errors.push({ where: 'console-hook', err: String(e) }); }

  function snap() {
    var s = window.state || {};
    return {
      tMs: Math.round(performance.now()),
      hasApp: !!window.MemoriaApp,
      hasOpenFile: !!(window.MemoriaApp && typeof window.MemoriaApp.openFile === 'function'),
      kbPath: s.kbPath || null,
      files: (s.files || []).length,
      currentPath: s.currentPath || null,
      bootPending: !!s.bootAutoOpenPending,
      validateReport: !!s.kbValidateReport,
      graphNodes: (s.graphData && s.graphData.nodes) ? s.graphData.nodes.length : 0,
      openSeq: (typeof s.openSeq === 'number') ? s.openSeq : null,
      userNavigated: !!s.userNavigated
    };
  }

  function fire(tag, path) {
    try {
      var before = snap();
      var p = window.MemoriaApp.openFile(path, {});
      var rec = { tag: tag, path: path, atMs: before.tMs, before: before, returnValue: null, resolvedAtMs: null, after: null, settled: null };
      R.calls.push(rec);
      Promise.resolve(p).then(function (v) {
        rec.returnValue = v;
        rec.resolvedAtMs = Math.round(performance.now());
        rec.after = snap();
        setTimeout(function () { rec.settled = snap(); }, 1500);
      }, function (e) {
        rec.returnValue = 'THROW:' + String((e && e.message) || e);
        rec.resolvedAtMs = Math.round(performance.now());
        rec.after = snap();
      });
    } catch (e) {
      R.errors.push({ where: 'fire:' + tag, err: String((e && e.message) || e), atMs: Math.round(performance.now()) });
    }
  }

  // 状态迁移流水（用于证明"哪一刻在哪个窗口"）
  var lastKey = '';
  var watch = setInterval(function () {
    var s = snap();
    var key = [s.hasOpenFile, s.files, s.kbPath, s.currentPath, s.bootPending, s.validateReport].join('|');
    if (key !== lastKey) {
      lastKey = key;
      R.transitions.push(s);
      if (R.transitions.length > 200) R.transitions.splice(0, 100);
    }
    if (s.tMs > 30000) clearInterval(watch);
  }, 5);

  // 时机 1/2/3
  var iv = setInterval(function () {
    R.ivTicks = (R.ivTicks || 0) + 1;
    if (R.ivTicks % 200 === 1) R.ivTicksAt = Math.round(performance.now());
    if (!window.MemoriaApp || typeof window.MemoriaApp.openFile !== 'function') {
      R.ivNoApp = (R.ivNoApp || 0) + 1;
      return;
    }
    clearInterval(iv);
    R.ivFiredAt = Math.round(performance.now());
    fire('T1-at-openFile-defined', ${JSON.stringify(T1)});
    setTimeout(function () { fire('T1b-at-openFile+50ms', ${JSON.stringify(T2)}); }, 50);
    var iv2 = setInterval(function () {
      var s = snap();
      if (s.bootPending && !R.firedBoot) { R.firedBoot = true; fire('T2-during-boot-pending', ${JSON.stringify(T2)}); }
      if (s.currentPath && !R.firedAfterDoc) {
        R.firedAfterDoc = true;
        fire('T3-after-first-doc', ${JSON.stringify(T1)});
        setTimeout(function () { fire('T3b-after-first-doc-burst', ${JSON.stringify(T2)}); }, 60);
        setTimeout(function () { fire('T3c-after-first-doc-burst', ${JSON.stringify(T1)}); }, 140);
        clearInterval(iv2);
      }
      if (s.tMs > 30000) clearInterval(iv2);
    }, 5);
  }, 5);
})();`;

const res = {
  schema: 'openfile-race/v2',
  port, targets: [T1, T2],
  startedAt: new Date().toISOString(),
  phases: {},
  ok: false,
};
let cdp = null;
try {
  res.t0 = Date.now();
  const target = await waitAppTarget(60000);
  if (!target) throw new Error('60s 内未找到应用页面目标');
  res.phases.targetFoundMs = Date.now() - res.t0;
  cdp = await CDP.connect(target.webSocketDebuggerUrl);
  await cdp.send('Runtime.enable').catch(() => null);
  await cdp.send('Page.enable').catch(() => null);
  res.phases.connectedMs = Date.now() - res.t0;

  // 等首次导航的页面可用（能拿到 state），再装注入 + reload
  let ready = false;
  for (let i = 0; i < 1200; i++) {
    try {
      ready = !!(await cdp.evalJS('!!(window.MemoriaApp && window.state)'));
    } catch { ready = false; }
    if (ready) break;
    await sleep(25);
  }
  if (!ready) throw new Error('首次页面不可用（拿不到 MemoriaApp/state）');
  res.phases.firstBootUsableMs = Date.now() - res.t0;
  const firstBoot = await cdp.evalJS(`(function(){var s=window.state||{};return {currentPath:s.currentPath||null,files:(s.files||[]).length,kbPath:s.kbPath||null,validate:!!s.kbValidateReport,graphNodes:(s.graphData&&s.graphData.nodes)?s.graphData.nodes.length:0};})()`);
  res.phases.firstBootState = firstBoot;

  await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: INJECT });
  res.phases.injectInstalledMs = Date.now() - res.t0;
  const tReload = Date.now();
  await cdp.send('Page.reload', { ignoreCache: true });
  // 等页面的 __RACE__ 出现并稳定
  let race = null;
  for (let i = 0; i < Math.ceil(settle / 100); i++) {
    await sleep(100);
    try {
      race = await cdp.evalJS('window.__RACE__ ? JSON.parse(JSON.stringify(window.__RACE__)) : null');
    } catch { race = race || null; }
    if (race && race.calls && race.calls.length >= 5) {
      // 等最后一批 settled 时长
      const hasSettled = race.calls.every((c) => c && (c.settled || c.returnValue === undefined));
      if (hasSettled) break;
    }
  }
  res.phases.raceReadMs = Date.now() - tReload;
  if (!race) throw new Error('重载后未取到 __RACE__（注入未生效？）');
  res.race = race;
  res.finalState = await cdp.evalJS(`(function(){var s=window.state||{};return {currentPath:s.currentPath||null, files:(s.files||[]).length, kbPath:s.kbPath||null, validate:!!s.kbValidateReport, graphNodes:(s.graphData&&s.graphData.nodes)?s.graphData.nodes.length:0};})()`);
  res.ok = true;
} catch (e) {
  res.error = String((e && e.stack) || e);
} finally {
  res.finishedAt = new Date().toISOString();
  try { if (cdp) cdp.close(); } catch { /* noop */ }
  fs.mkdirSync(out.replace(/[\\/][^\\/]+$/, ''), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(res, null, 2), 'utf8');
  const n = (res.race && res.race.calls && res.race.calls.length) || 0;
  console.log('__OPENFILE_RACE__' + JSON.stringify({ ok: res.ok, out, calls: n }));
  process.exit(res.ok ? 0 : 1);
}
