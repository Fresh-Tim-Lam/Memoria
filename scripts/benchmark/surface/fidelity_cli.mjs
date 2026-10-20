#!/usr/bin/env node
/**
 * fidelity_cli.mjs —— 渲染保真度指标 CLI（投影 + 断言 + 签名）
 *
 * ⚠️ 两种输入模式**互斥**，语义完全不同，别用错：
 *
 *   模式 1（默认，CI/常规）—— **`--url <harness URL>`**
 *     harness 只是 bottle **静态服务器**，它自己**不是** CDP 端点。
 *     本 CLI 会自己起一个无头 Edge，再 navigate 到该 URL。
 *       node fidelity_cli.mjs --url http://127.0.0.1:8644/ \
 *            --files corpus/03-block-boundaries.md,corpus/04-non-editable.md,corpus/07-extremes.md \
 *            --out results/fidelity-baseline_<sha>.json
 *
 *   模式 2（真机）—— **`--cdp <CDP endpoint>`**
 *     attach 到**已运行**的应用（应用须以 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<port> 启动）。
 *     本 CLI **不**启动浏览器、**不**导航（应用已加载）。
 *       node fidelity_cli.mjs --cdp http://127.0.0.1:9500 --files ... --out ...
 *
 * 共同选项：
 *   --files a.md,b.md      要测的文档（harness 模式为相对 KB 的路径；真机模式同）
 *   --out <json>           落盘路径
 *   --mutate <kind>        变异测试：char | math | strong | reorder（注入破坏，期望断言变红）
 *   --repeat               不动 DOM 连跑两次，校验签名一致（默认已跑，此开关只影响报告字段）
 *
 * 判定全部在页面内跑（PROBE_SOURCE 注入后求值）；Node 侧只做 CDP 连接、sha256 签名、落盘。
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { PROBE_SOURCE, fidelitySignature } from './fidelity.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const USAGE = `
fidelity_cli.mjs —— 渲染保真度指标（A 级硬门槛 / B 级 warn）

用法（两种模式互斥，必须二选一）：
  # 模式 1：harness 静态服务（本 CLI 自起无头 Edge 并导航）
  node fidelity_cli.mjs --url http://127.0.0.1:8644/ --files a.md,b.md --out out.json

  # 模式 2：attach 已运行的真机应用（不启浏览器、不导航）
  node fidelity_cli.mjs --cdp http://127.0.0.1:9500 --files a.md,b.md --out out.json

选项：
  --url   <harness URL>   harness 页面地址（bottle 静态服务，**不是** CDP 端点）
  --cdp   <CDP endpoint>  已运行应用的 CDP 端点（如 http://127.0.0.1:9500）
  --files <a,b,c>         待测文档（逗号分隔）
  --out   <path.json>     产物路径
  --mutate <kind>         变异测试：char | math | strong | reorder（期望断言变红）
  --help                  显示本帮助

注意：--url 与 --cdp **不可同时给**；两者都无则报错。
`;

// Edge 定位（与 cdp.mjs 同款）
const EDGE_CANDIDATES = [
  process.env.MEMORIA_EDGE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);
function findEdge() {
  for (const p of EDGE_CANDIDATES) { try { if (fs.existsSync(p)) return p; } catch { /* noop */ } }
  throw new Error('找不到 msedge.exe；可用环境变量 MEMORIA_EDGE 指定。');
}
async function httpJson(url) { const r = await fetch(url); return await r.json(); }

// 无头 Edge 启动（与 cdp.mjs launchEdge 同款；harness 只做静态服务，浏览器由这里起）
async function launchEdge({ url }) {
  const edgePath = findEdge();
  const cdpPort = 9222 + Math.floor(Math.random() * 3000);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'memoria-fidelity-edge-'));
  const args = [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-background-networking', '--remote-allow-origins=*',
    `--remote-debugging-port=${cdpPort}`, `--user-data-dir=${userDataDir}`, 'about:blank',
  ];
  const proc = spawn(edgePath, args, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d.toString(); });
  const base = `http://127.0.0.1:${cdpPort}`;
  const t0 = Date.now();
  let version = null;
  for (;;) {
    try { version = await httpJson(base + '/json/version'); if (version && version.webSocketDebuggerUrl) break; } catch { /* not up */ }
    if (Date.now() - t0 > 20000) { try { proc.kill(); } catch { /* noop */ } throw new Error('Edge CDP 未就绪: ' + stderr.slice(0, 500)); }
    await sleep(200);
  }
  let list = await httpJson(base + '/json/list').catch(() => []);
  let page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!page) { try { page = await httpJson(base + '/json/new?about:blank'); } catch { /* noop */ } }
  const wsUrl = page && page.webSocketDebuggerUrl ? page.webSocketDebuggerUrl : (version.webSocketDebuggerUrl || null);
  if (!wsUrl) { try { proc.kill(); } catch { /* noop */ } throw new Error('拿不到 webSocketDebuggerUrl'); }
  return {
    proc, port: cdpPort, userDataDir, wsUrl, browser: version.Browser || 'Edge',
    cleanup() { try { proc.kill(); } catch { /* noop */ } try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { /* noop */ } },
  };
}

function parseArgs(argv) {
  const a = { files: [], _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) {
      const k = t.slice(2);
      const nxt = argv[i + 1];
      if (nxt && !nxt.startsWith('--')) { a[k] = nxt; i++; } else { a[k] = true; }
    } else a._.push(t);
  }
  if (a.files && typeof a.files === 'string') a.files = a.files.split(',').map((s) => s.trim()).filter(Boolean);
  return a;
}

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
  send(method, params = {}) { return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) { const d = r.exceptionDetails; throw new Error('eval 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]); }
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expr, { timeout = 60000, interval = 150, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) { let v; try { v = await this.evalJS(expr); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '')); await sleep(interval); }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

// 连接 harness（已改为自起 Edge，见 launchEdge；此函数不再使用，移除）

// 真机 attach 模式：从 CDP endpoint 解析出应用页面的 webSocketDebuggerUrl
//   必须过滤 devtools:// 与 about:blank（WebView2 的 /json/list 会混入 DevTools 自身页面）
async function resolveCdpWs(endpoint) {
  const base = String(endpoint).replace(/\/+$/, '');
  const list = await httpJson(base + '/json/list').catch(() => null);
  if (!list) throw new Error('CDP endpoint 无响应：' + base + '（应用是否以 --remote-debugging-port 启动？）');
  const pages = (list || []).filter((t) =>
    t.type === 'page' && t.webSocketDebuggerUrl &&
    !/^devtools:\/\//.test(t.url || '') && !/^about:blank$/i.test(t.url || ''));
  if (!pages.length) throw new Error('CDP endpoint 上找不到应用页面目标：' + JSON.stringify(list).slice(0, 300));
  return pages[0].webSocketDebuggerUrl;
}

async function openDoc(cdp, file) {
  // ⚠️ 应用启动时会**异步自动打开默认文件**（README.md）并覆盖 currentPath。
  //   首次 openFile 可能被这次自动打开顶掉 ⇒ 重试直到 currentPath 稳定为目标文档。
  //   （Lead 的既有陷阱③：应用启动尾动作会再改一次 currentPath）
  let opened = false;
  for (let attempt = 0; attempt < 4 && !opened; attempt++) {
    await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    try {
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, { label: 'open:' + file, timeout: 20000 });
      // 再等一小会，确认没被启动尾动作覆盖
      await sleep(700);
      const p = await cdp.evalJS('window.state.currentPath');
      if (p === file) opened = true;
    } catch (e) {
      if (attempt === 3) throw e;
    }
  }
  if (!opened) throw new Error('openFile 未能稳定到目标文档：' + file);
  // 切预览（轮询式点击：应用可能在切换过程中重置 viewMode，单次 click 未必生效）
  for (let i = 0; i < 6; i++) {
    const mode = await cdp.evalJS('(window.state||{}).viewMode || null');
    if (mode === 'preview') break;
    await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b)b.click();return true;})()`);
    await sleep(400);
  }
  await cdp.waitFor(`window.state && window.state.viewMode === 'preview'`, { label: 'preview:' + file, timeout: 15000 });
  // 预览块就绪（偶发慢：首次渲染大文档），失败则重试一次 openFile
  try {
    await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 0`, { label: 'blocks:' + file, timeout: 25000 });
  } catch (e) {
    await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    await sleep(1200);
    await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 0`, { label: 'blocks-retry:' + file, timeout: 25000 });
  }
  // 渲染稳定：等 loading 消失 + typeset 落定
  await cdp.waitFor(`!document.querySelector('#preview-status .-preview-loading, .-preview-loading, #preview.-loading')`, { label: 'loading-gone', timeout: 30000 }).catch(() => {});
  await cdp.evalJS(`(async function(){
    if (window.state && window.state._mathPending) { try { await window.state._mathPending; } catch(e){} }
    return true;
  })()`).catch(() => {});
  await sleep(600);

  // ⚠️ 自洽守卫（首版漏了这条，导致 AST 与 DOM 来自不同文档快照 ⇒ A2 大面积假红）：
  //   必须等到「parse(state.doc.body).blocks.length == #preview .-src-block 数」。
  //   注意：state.doc 是**后端返回的文档**（有 .body），**没有 .blocks**；
  //   blocks 是 MemoriaParser.parse(body) 的产物 ⇒ 守卫必须现解析一次。
  const t0 = Date.now();
  let last = null;
  for (;;) {
    last = await cdp.evalJS(`(function(){
      try {
        var body = (window.state.doc && window.state.doc.body) || null;
        var n = body ? window.MemoriaParser.parse(body).blocks.length : -1;
        var d = document.querySelectorAll('#preview .-src-block').length;
        var path = window.state.currentPath || null;
        return { docBlocks: n, domBlocks: d, same: (n === d), path: path };
      } catch (e) { return { err: String(e && e.message || e) }; }
    })()`);
    if (last && last.same && last.docBlocks > 0 && last.path === file) return;
    if (Date.now() - t0 > 30000) {
      throw new Error(`文档/预览未自洽（${file}）：parse(body).blocks=${last && last.docBlocks} vs DOM=${last && last.domBlocks}，path=${last && last.path}，err=${last && last.err}`);
    }
    await sleep(150);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || args.h) { process.stdout.write(USAGE); return 0; }

  const harnessUrl = typeof args.url === 'string' ? args.url : null;
  const cdpEndpoint = typeof args.cdp === 'string' ? args.cdp : null;
  const files = args.files || [];
  const out = args.out || null;
  const mutateKind = args.mutate || null;

  // ── 两种模式互斥，报错要清楚（后来人最容易用错的地方）──
  if (harnessUrl && cdpEndpoint) {
    process.stderr.write(
      '错误：--url 与 --cdp 不能同时给，两者语义不同：\n' +
      '  --url <harness URL>  = harness 静态服务地址（本 CLI 自己起无头 Edge 并导航）\n' +
      '  --cdp <endpoint>     = 已运行应用的 CDP 端点（本 CLI 只 attach，不启浏览器、不导航）\n' +
      '请二选一（多数 CI 场景用 --url）。\n\n' + USAGE);
    return 2;
  }
  if (!harnessUrl && !cdpEndpoint) {
    process.stderr.write('错误：必须给 --url <harness URL> 或 --cdp <CDP endpoint> 之一。\n\n' + USAGE);
    return 2;
  }
  if (!files.length) {
    process.stderr.write('错误：--files 为空。请给逗号分隔的文档路径。\n');
    return 2;
  }

  const result = {
    schema: 'memoria-fidelity-run/v1',
    mode: harnessUrl ? 'harness' : 'cdp-attach',
    harnessUrl: harnessUrl || null,
    cdpEndpoint: cdpEndpoint || null,
    files, mutateKind,
    startedAt: new Date().toISOString(),
    documents: {},
  };
  let edge = null;
  let cdp = null;
  let exitCode = 1;
  try {
    if (harnessUrl) {
      // 模式 1：自起无头 Edge → 导航到 harness URL
      edge = await launchEdge({ url: harnessUrl });
      result.environment = { browser: edge.browser, mode: 'harness', harnessUrl };
      cdp = await CDP.connect(edge.wsUrl);
      await cdp.send('Page.enable');
      await cdp.send('Runtime.enable');
      await cdp.send('Page.navigate', { url: harnessUrl });
      // navigate 是异步的：先等文档加载完成，再等应用脚本就绪（否则会把"还在加载"当成失败）
      await cdp.waitFor('document.readyState === "complete"', { label: 'readyState', timeout: 60000 });
      // 应用启动偶发慢（首次编译脚本 / 机器忙）⇒ reload 重试，最多 3 次，失败时带现场诊断
      let ready = false;
      let lastErr = null;
      for (let attempt = 0; attempt < 3 && !ready; attempt++) {
        try {
          await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', { label: 'app+parser', timeout: 45000 });
          ready = true;
        } catch (e) {
          lastErr = e;
          if (attempt < 2) { try { await cdp.send('Page.reload', { ignoreCache: true }); } catch { /* noop */ } await sleep(1500); }
        }
      }
      if (!ready) {
        const diag = await cdp.evalJS(`({href: location.href, title: document.title, scripts: document.scripts.length, hasApp: !!window.MemoriaApp, hasParser: !!window.MemoriaParser, bodyLen: document.body ? document.body.innerHTML.length : -1})`).catch(() => null);
        throw new Error('应用未就绪（reload 重试后仍失败）: ' + JSON.stringify(diag) + ' | ' + (lastErr && lastErr.message));
      }
    } else {
      // 模式 2：attach 已运行应用（不启浏览器、不导航）
      const wsUrl = await resolveCdpWs(cdpEndpoint);
      result.environment = { mode: 'cdp-attach', cdpEndpoint, wsUrl };
      cdp = await CDP.connect(wsUrl);
      await cdp.send('Runtime.enable');
      // attach 模式：应用已在运行，只需等它就绪（harness 模式已在上面的分支里等过）
      await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', { label: 'app+parser(attach)', timeout: 90000 });
    }

    // 注入探针
    await cdp.evalJS('window.__fidelity = ' + PROBE_SOURCE);

    for (const file of files) {
      await openDoc(cdp, file);
      const doc = await cdp.evalJS(`(function(){
        var code = window.state.doc && window.state.doc.body;
        if (!code) return null;
        return window.MemoriaParser.parse(code);
      })()`);
      if (!doc) { result.documents[file] = { status: 'error', error: '解析失败（state.doc.body 不可用）' }; continue; }

      // 第一次：无变异
      const run1 = await cdp.evalJS(`window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))`);
      run1.signature = fidelitySignature(run1.signatureNorm);

      // 第二次（复现性）：重新取 DOM 投影再跑一次（不动 DOM）
      const run2 = await cdp.evalJS(`window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))`);
      run2.signature = fidelitySignature(run2.signatureNorm);

      // 变异测试（可选）
      let mutation = null;
      if (mutateKind) {
        await cdp.evalJS(`window.__fidelity.mutate(${JSON.stringify(mutateKind)})`);
        await sleep(300);
        const mut = await cdp.evalJS(`window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))`);
        mut.signature = fidelitySignature(mut.signatureNorm);
        mutation = { kind: mutateKind, ok: mut.ok, aLevel: mut.aLevel, signature: mut.signature };
      }

      result.documents[file] = {
        status: 'ran',
        run1: { ok: run1.ok, aLevel: run1.aLevel, bLevel: run1.bLevel, signature: run1.signature, astCount: run1.astCount, domCount: run1.domCount },
        run2: { ok: run2.ok, aLevel: run2.aLevel, signature: run2.signature },
        reproducible: run1.signature === run2.signature,
        mutation,
      };
    }
    // 全局：所有文档 A 级是否全绿
    result.allGreen = Object.values(result.documents).every((d) => d.status === 'ran' && (d.run1 && d.run1.ok));
    result.ok = true;
    exitCode = 0;
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) cdp.close();
    if (edge) edge.cleanup();
    setTimeout(() => process.exit(exitCode), 2000).unref();
  }
  const text = JSON.stringify(result, null, 2);
  if (out) { fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, text, 'utf8'); process.stdout.write('__FIDELITY__' + JSON.stringify({ ok: result.ok, allGreen: result.allGreen, out, docs: Object.keys(result.documents) }) + '\n'); }
  else process.stdout.write(text + '\n');
  return exitCode;
}

const code = await main();
process.exitCode = code;
