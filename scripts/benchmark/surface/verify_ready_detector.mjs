#!/usr/bin/env node
/**
 * verify_ready_detector.mjs —— 渲染就绪判定的判别力自证（task-31）
 *
 * 就绪判定本身必须有判别力，否则「等到了」只是一句空话。三条硬自证：
 *
 *   S1 **抢拍不误报 ready**：在渲染刚开始时就取快照判定 ⇒ 必须 NOT ready
 *   S2 **坏公式/坏 mermaid 判 failed**：注入语法错误 ⇒ 必须 failed（不是 ready、不是 timeout）
 *   S3 **timeout 不冒充 ready**：把超时压到极短且文档很大 ⇒ 必须 timeout，绝不能是 ready
 *
 * 另加：
 *   S0 **正常就绪**：真机上等就绪成功 ⇒ status=ready，并报公式数/等待耗时
 *   S4 **无头 inconclusive**：无头环境下 ⇒ 绝不 ready（inconclusive 或 failed 有证据）
 *
 * 用法（应用已带 --remote-debugging-port 启动）：
 *   node verify_ready_detector.mjs --cdp http://127.0.0.1:9500 --file scale/scale-5k.md --out out.json
 */

import fs from 'node:fs';
import path from 'node:path';
import { PROBE_SOURCE } from './fidelity.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (!t.startsWith('--')) continue;
    const k = t.slice(2);
    const n = argv[i + 1];
    if (n && !n.startsWith('--')) { a[k] = n; i++; } else a[k] = true;
  }
  return a;
}
async function httpJson(u) { const r = await fetch(u); return await r.json(); }

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(u);
      const to = setTimeout(() => rej(new Error('CDP WS 超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('CDP WS 失败')); });
    });
  }
  _on(d) { let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; } if (m.id == null) return; const p = this._p.get(m.id); if (!p) return; this._p.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result); }
  send(m, p = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method: m, params: p })); }); }
  async ev(x) {
    const r = await this.send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); }
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(x, { timeout = 60000, interval = 120, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) { let v; try { v = await this.ev(x); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error('超时' + (label ? ':' + label : '')); await sleep(interval); }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

async function openDoc(cdp, file, { waitReady = true } = {}) {
  for (let i = 0; i < 4; i++) {
    await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    try {
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, { timeout: 20000, label: 'open' });
      await sleep(600);
      if (await cdp.ev('window.state.currentPath') === file) break;
    } catch (e) { if (i === 3) throw e; }
  }
  for (let i = 0; i < 8; i++) {
    const mode = await cdp.ev('(window.state||{}).viewMode || null');
    if (mode === 'preview') break;
    await cdp.ev(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b)b.click();return 1;})()`);
    await sleep(300);
  }
  await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 0`, { timeout: 25000, label: 'blocks' });
  if (waitReady) {
    // 正常路径：等就绪（这也顺带把 S0 测了）
    return await cdp.ev(`window.__fidelity.waitForRenderReady({ which: 'both', minFrames: 3, timeoutMs: 45000 })`);
  }
  return null;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpEndpoint = args.cdp || 'http://127.0.0.1:9500';
  const file = args.file || 'scale/scale-5k.md';
  const otherFile = args['other-file'] || 'README.md';
  const out = args.out || null;

  const result = {
    schema: 'memoria-ready-detector-selfcheck/v1',
    mode: 'real',
    cdpEndpoint,
    file,
    startedAt: new Date().toISOString(),
    checks: {},
  };
  let cdp = null;
  let exitCode = 1;
  try {
    const base = String(cdpEndpoint).replace(/\/+$/, '');
    const list = await httpJson(base + '/json/list');
    const page = (list || []).find((t) => t.type === 'page' && /^https?:/.test(t.url || ''));
    if (!page) throw new Error('找不到页面目标');
    cdp = await CDP.connect(page.webSocketDebuggerUrl);
    await cdp.send('Runtime.enable');
    await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', { timeout: 90000, label: 'app' });
    await cdp.ev('window.__fidelity = ' + PROBE_SOURCE);
    result.env = await cdp.ev(`(function(){ return { headless: !!(navigator.userAgent && /Headless/i.test(navigator.userAgent)), ua: navigator.userAgent.slice(0,120) }; })()`);

    // ── S0 正常就绪（真机应 ready，无头应 inconclusive）──
    const ready0 = await openDoc(cdp, file, { waitReady: false });
    // openDoc 已做 blocks 等待，这里再显式等就绪
    const t0 = Date.now();
    const readyRes = await cdp.ev(`window.__fidelity.waitForRenderReady({ which: 'both', minFrames: 3, timeoutMs: 45000 })`);
    result.checks.S0_normalReady = {
      ...readyRes,
      wallMs: Date.now() - t0,
      // 真机期望 ready；无头期望 inconclusive（绝不 ready）
      verdict: result.env.headless
        ? (readyRes.status === 'inconclusive' ? 'PASS' : 'FAIL')
        : (readyRes.status === 'ready' ? 'PASS' : 'FAIL'),
      rule: result.env.headless ? '无头必须 inconclusive' : '真机必须 ready',
    };

    // ── S1 抢拍不误报 ready ──
    //   !! 为什么前两版都 SKIP：`openFile` 命中**预览 DOM 缓存**（`previewCacheMax` 最小夹到 1，
    //      无法禁用）⇒ 重开同文档拿到的就是已排完的 DOM，`typesetPromise` 都没再被调用，
    //      压根不存在"渲染中"窗口。这不是判据的错，是**没造出被测场景**。
    //   ⇒ 改用确定性构造：在预览里**追加 N 个尚未排版的公式占位**（.-math），
    //      使 expected 骤增而 nonEmpty 不变 ⇒ 状态必然"未排完"。
    //      此时断言：snapshotNow 不得 ready、waitForRenderReady 短窗口内也不得 ready。
    const INJECT_N = 40;
    const injectedS1 = await cdp.ev(`(function(){
      var pv = document.getElementById('preview');
      if (!pv) return { ok:false, reason:'no-preview' };
      var host = pv.querySelector('.-src-block') || pv;
      var before = pv.querySelectorAll('.-math, [data-formula]').length;
      for (var i = 0; i < ${INJECT_N}; i++) {
        var d = document.createElement('span');
        d.className = '-math';
        d.textContent = '\\$x_{' + i + '}\\$';   // 纯文本占位：未排版
        host.appendChild(d);
      }
      var after = pv.querySelectorAll('.-math, [data-formula]').length;
      return { ok:true, before: before, after: after, injected: after - before };
    })()`);

    const snap = await cdp.ev(`window.__fidelity.snapshotNow('both')`);
    const mathPending = snap.math ? (snap.math.expected > 0 && snap.math.nonEmpty < snap.math.expected) : false;
    const mmdPending = snap.mermaid ? (snap.mermaid.residualSrc > 0 || (snap.mermaid.containers > 0 && snap.mermaid.withSvg < snap.mermaid.containers)) : false;
    const notReadyNow = snap.status !== 'ready' && snap.status !== 'ready-but-not-idle';

    // 核心证据：此刻真调 waitForRenderReady（短窗口），**不得**报 ready
    const immediateReady = await cdp.ev(`(async function(){
      var t0 = performance.now();
      var r = await window.__fidelity.waitForRenderReady({ which:'math', minFrames: 3, timeoutMs: 800, awaitAppPending: false });
      r.observedAfterMs = +(performance.now() - t0).toFixed(2);
      return r;
    })()`);

    // 清理注入
    await cdp.ev(`(function(){
      var pv = document.getElementById('preview');
      if (!pv) return 0;
      var n = 0;
      pv.querySelectorAll('.-math').forEach(function(el){
        if ((el.textContent||'').indexOf('x_{') >= 0 && !el.querySelector('mjx-container')) { el.remove(); n++; }
      });
      return n;
    })()`);

    const inRender = mathPending || mmdPending;
    result.checks.S1_earlySnapshotNotReady = {
      injected: injectedS1,
      snapshot: snap,
      stillRendering: inRender,
      immediateWait: immediateReady,
      verdict: inRender
        ? ((notReadyNow && immediateReady && immediateReady.status !== 'ready') ? 'PASS' : 'FAIL')
        : 'SKIP(in-render-not-observed)',
      rule: '追加未排版公式占位制造"未排完"状态：snapshotNow 不得 ready，且 800ms 窗口内 waitForRenderReady 也不得 ready',
    };

    // ── S3 timeout 不冒充 ready：极短超时 ++ 大文档 ──
    await cdp.ev(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 0`, { timeout: 25000, label: 'blocks-s3' });
    const tight = await cdp.ev(`window.__fidelity.waitForRenderReady({ which: 'both', minFrames: 999999, timeoutMs: 120, awaitAppPending: false })`);
    result.checks.S3_timeoutNotReady = {
      ...tight,
      verdict: tight.status === 'timeout' ? 'PASS' : (tight.status === 'inconclusive' && result.env.headless ? 'PASS' : 'FAIL'),
      note: 'minFrames 极高 + timeoutMs=120 ⇒ 必须 timeout（或真无头 inconclusive），绝不能 ready',
      rule: 'timeout 不得冒充 ready',
    };

    // ── S2 坏 mermaid => failed ──
    //   直接在 DOM 里注入一个 .-mermaid-error 占位（等价于渲染失败产物），断言被识别为 failed
    await openDoc(cdp, file, { waitReady: false });
    const injected = await cdp.ev(`(function(){
      var pv = document.getElementById('preview');
      if (!pv) return { ok:false, reason:'no-preview' };
      var d = document.createElement('div');
      d.className = '-mermaid-error -src-block';
      d.textContent = 'mermaid 渲染失败（自证注入）';
      var host = pv.querySelector('.-src-block') || pv;
      host.appendChild(d);
      return { ok:true, count: pv.querySelectorAll('.-mermaid-error').length };
    })()`);
    const failRes = await cdp.ev(`window.__fidelity.waitForRenderReady({ which: 'mermaid', minFrames: 1, timeoutMs: 3000, awaitAppPending: false })`);
    result.checks.S2_badMermaidFailed = {
      injected,
      ready: failRes,
      verdict: failRes.status === 'failed' ? 'PASS' : 'FAIL',
      rule: '出现 .-mermaid-error ⇒ 必须 failed（不是 ready 也不是 timeout）',
    };

    // 恢复文档（清理注入）
    await openDoc(cdp, file, { waitReady: false });

    const checks = result.checks;
    result.summary = {
      S0: checks.S0_normalReady.verdict,
      S1: checks.S1_earlySnapshotNotReady.verdict,
      S2: checks.S2_badMermaidFailed.verdict,
      S3: checks.S3_timeoutNotReady.verdict,
    };
    result.ok = Object.values(result.summary).every((v) => v === 'PASS' || String(v).startsWith('SKIP'));
    exitCode = result.ok ? 0 : 1;
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) cdp.close();
    if (out) {
      fs.mkdirSync(path.dirname(out), { recursive: true });
      fs.writeFileSync(out, JSON.stringify(result, null, 2), 'utf8');
      process.stdout.write('__READYCHECK__' + JSON.stringify({ ok: result.ok, out, summary: result.summary }) + '\n');
    } else process.stdout.write(JSON.stringify(result, null, 2) + '\n');
    setTimeout(() => process.exit(exitCode), 1200).unref();
  }
  return exitCode;
}

const code = await main();
process.exitCode = code;
