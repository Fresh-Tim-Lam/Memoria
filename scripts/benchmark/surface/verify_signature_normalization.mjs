#!/usr/bin/env node
/**
 * verify_signature_normalization.mjs —— 签名工具自证（task-28）
 *
 * 证明「阶段 2 判等工具」本身可用，共四组断言：
 *
 *   G1 **归一化剥离自证 · 不变**：只换 mermaid/MathJax 随机 id（语义不变）
 *      ⇒ 签名必须**完全不变**（否则剥离规则没生效）
 *   G2 **归一化剥离自证 · 变**  ：真改一处内容
 *      ⇒ 签名必须**变**（否则过度剥离，会漏判真退化）
 *   G3 **legacy-vs-legacy 双跑**：同一份 legacy 渲染两次
 *      ⇒ 签名 **0 diff**
 *   G4 **对比机制判红**：注入一处真实 DOM 变更后与基线对比
 *      ⇒ 对比**必须报 diff**
 *
 * 用法（由 run_signature_selfcheck.ps1 调起，应用已带 --remote-debugging-port）：
 *   node verify_signature_normalization.mjs --cdp http://127.0.0.1:9500 \
 *        --files corpus/04-non-editable.md --out out.json
 */

import fs from 'node:fs';
import path from 'node:path';
import { PROBE_SOURCE, fidelitySignature } from './fidelity.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) { const k = t.slice(2); const n = argv[i + 1]; if (n && !n.startsWith('--')) { a[k] = n; i++; } else a[k] = true; }
    else a._.push(t);
  }
  if (typeof a.files === 'string') a.files = a.files.split(',').map((s) => s.trim()).filter(Boolean);
  return a;
}

async function httpJson(url) { const r = await fetch(url); return await r.json(); }

async function resolveCdpWs(endpoint) {
  const base = String(endpoint).replace(/\/+$/, '');
  const list = await httpJson(base + '/json/list').catch(() => null);
  if (!list) throw new Error('CDP endpoint 无响应：' + base);
  const pages = (list || []).filter((t) => t.type === 'page' && t.webSocketDebuggerUrl &&
    !/^devtools:\/\//.test(t.url || '') && !/^about:blank$/i.test(t.url || ''));
  if (!pages.length) throw new Error('找不到应用页面目标');
  return pages[0].webSocketDebuggerUrl;
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

async function openDoc(cdp, file) {
  for (let attempt = 0; attempt < 4; attempt++) {
    await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(file)}, { skipNav: true })`);
    try {
      await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(file)} && !!window.state.doc`, { label: 'open', timeout: 20000 });
      await sleep(700);
      if (await cdp.evalJS('window.state.currentPath') === file) break;
    } catch (e) { if (attempt === 3) throw e; }
  }
  for (let i = 0; i < 6; i++) {
    const mode = await cdp.evalJS('(window.state||{}).viewMode || null');
    if (mode === 'preview') break;
    await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b)b.click();return true;})()`);
    await sleep(400);
  }
  await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 0`, { label: 'blocks', timeout: 25000 });
  // 等 typeset 落定
  await cdp.evalJS(`(async function(){
    if (window.state && window.state._mathPending) { try { await window.state._mathPending; } catch(e){} }
    return true; })()`).catch(() => {});
  await sleep(800);
  // !! **DOM 稳定判据**：等块数连续 8 帧不变。
  //    首版固定 sleep(800) 就取签名，结果基线那一次少了一个 -blank-block（渲染尚未完成）
  //    => G1 误判「签名变了」。必须等结构真正稳定。
  await cdp.evalJS(`(async function(){
    function frame(){ return new Promise(function(r){ requestAnimationFrame(function(){ r(); }); }); }
    var last = '', stable = 0;
    for (var i = 0; i < 600 && stable < 15; i++) {
      var pv = document.querySelector('#preview');
      var sig = pv ? (pv.querySelectorAll('.-src-block').length + '|' + pv.innerHTML.length) : '';
      if (sig === last && sig) stable++; else { stable = 0; last = sig; }
      await frame();
    }
    return last;
  })()`).catch(() => {});
  // 再补一段真实等待，覆盖 mermaid/公式的后置替换
  await sleep(2000);
}

const sigOf = (r) => fidelitySignature(r.signatureNorm);

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpEndpoint = args.cdp || 'http://127.0.0.1:9500';
  const out = args.out || null;
  const files = args.files || ['corpus/04-non-editable.md'];
  const result = {
    schema: 'memoria-signature-selfcheck/v1',
    mode: 'real',
    cdpEndpoint,
    startedAt: new Date().toISOString(),
    files,
    groups: {},
  };
  let cdp = null;
  let exitCode = 1;
  try {
    const wsUrl = await resolveCdpWs(cdpEndpoint);
    cdp = await CDP.connect(wsUrl);
    await cdp.send('Runtime.enable');
    await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', { label: 'app', timeout: 90000 });
    await cdp.evalJS('window.__fidelity = ' + PROBE_SOURCE);

    for (const file of files) {
      const perFile = { file, g1: null, g2: null, g3: null, g4: null };

      // ── 基线 + G3：同一份 legacy 渲染两次，签名必须 0 diff ──
      await openDoc(cdp, file);
      const r1 = await cdp.evalJS('window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))');
      const s1 = sigOf(r1);
      await sleep(600);
      const r2 = await cdp.evalJS('window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))');
      const s2 = sigOf(r2);
      perFile.g3 = { s1, s2, identical: s1 === s2, nondetStripped: r1.nondetStripped };

      // ── G1：只换随机 id（语义不变）⇒ 签名必须不变 ──
      // !! 基线必须与"变异前那一刻"取自**同一条渲染路径**：
      //    首版的 s1 取自首次 openDoc（页面刚加载，尾部空块可能尚未出现），
      //    而变异发生在第二次 openDoc 之后 => 块数差一个 => 误判成"签名变了"。
      //    故这里重新 openDoc 一次取 g1 基线。
      await openDoc(cdp, file);
      const rBase2 = await cdp.evalJS('window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))');
      const s1b = sigOf(rBase2);
      const mutated = await cdp.evalJS(`window.__fidelity.mutate('nondet-id-only')`);
      await sleep(400);
      const r3 = await cdp.evalJS('window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))');
      const s3 = sigOf(r3);
      // 差异定位：逐字符找第一处分歧，便于看到"到底哪里没被归一化"
      let g1Diff = null;
      if (s1b !== s3) {
        const a = (rBase2.normalizedHtml || ''), b = (r3.normalizedHtml || '');
        let k = 0;
        while (k < a.length && k < b.length && a[k] === b[k]) k++;
        g1Diff = {
          at: k,
          baseLen: a.length,
          afterLen: b.length,
          baseAround: a.slice(Math.max(0, k - 120), k + 160),
          afterAround: b.slice(Math.max(0, k - 120), k + 160),
        };
      }
      perFile.g1 = {
        mutation: mutated,
        baselineSig: s1b,
        afterSig: s3,
        unchanged: s1b === s3,
        nondetStrippedBase: r1.nondetStripped,
        nondetStrippedAfter: r3.nondetStripped,
        diff: g1Diff,
        verdict: s1b === s3 ? 'PASS' : 'FAIL',
      };

      // ── G2 + G4：真改内容 ⇒ 签名必须变 / 对比必须报 diff ──
      await openDoc(cdp, file);   // 重置
      const realMut = await cdp.evalJS(`window.__fidelity.mutate('real-change')`);
      await sleep(400);
      const r4 = await cdp.evalJS('window.__fidelity.runFidelity(window.MemoriaParser.parse(window.state.doc.body))');
      const s4 = sigOf(r4);
      perFile.g2 = {
        mutation: realMut,
        baselineSig: s1,
        afterSig: s4,
        changed: s1 !== s4,
        verdict: s1 !== s4 ? 'PASS' : 'FAIL',
      };
      perFile.g4 = {
        // 对比机制：用同一比较函数跑 baseline vs mutated
        diffDetected: s1 !== s4,
        verdict: s1 !== s4 ? 'PASS' : 'FAIL',
      };

      // 恢复
      await openDoc(cdp, file);
      result.groups[file] = perFile;
    }

    const all = Object.values(result.groups);
    result.summary = {
      g1_allUnchanged: all.every((g) => g.g1 && g.g1.verdict === 'PASS'),
      g2_allChanged: all.every((g) => g.g2 && g.g2.verdict === 'PASS'),
      g3_allZeroDiff: all.every((g) => g.g3 && g.g3.identical),
      g4_allDiffDetected: all.every((g) => g.g4 && g.g4.verdict === 'PASS'),
    };
    result.ok = result.summary.g1_allUnchanged && result.summary.g2_allChanged &&
                result.summary.g3_allZeroDiff && result.summary.g4_allDiffDetected;
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
      process.stdout.write('__SIGCHECK__' + JSON.stringify({ ok: result.ok, out, summary: result.summary }) + '\n');
    } else process.stdout.write(JSON.stringify(result, null, 2) + '\n');
    setTimeout(() => process.exit(exitCode), 1500).unref();
  }
  return exitCode;
}

const code = await main();
process.exitCode = code;
