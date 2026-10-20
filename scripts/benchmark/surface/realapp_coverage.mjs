#!/usr/bin/env node
/**
 * realapp_coverage.mjs —— 真机补测驱动（task-27）
 *
 * 补上**无头环境测不了的 4 项**：
 *   1. kpHover      —— hover KP 项 → 预览高亮落地时延（p50/p95）
 *   2. inlineMath   —— A10 行内公式**按块**计数（源 $...$ vs 块内已排版节点）
 *   3. agentStream  —— agent 面板流式最小结构（.-agent-msg-body 块数>0、无占位、公式已排）
 *   4. assistantCard—— 助手弹窗 / 复阅卡最小结构（**不依赖 data--src-line**，P4b 已移除）
 *
 * 纪律：
 *   - 每项标注 mode=real，且**不与无头读数混比**（无头 MathJax 排不完：≈3 vs 真机 270）
 *   - 每项 ≥2 次（--rounds），报告 p50/p95
 *   - 只读测量，**不改 src/**；本文件独立，不修改 cdp.mjs / run_probe.py（写域冲突规避）
 *
 * 用法（由 run_realapp_coverage.ps1 调起，应用已带 --remote-debugging-port 启动）：
 *   node realapp_coverage.mjs --cdp http://127.0.0.1:9500 --ops all --rounds 3 --out out.json
 */

import fs from 'node:fs';
import path from 'node:path';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const OPS = [
  { id: 'kpHover',       tier: 'A', metric: 'latency' },
  { id: 'inlineMath',    tier: 'A', metric: 'count' },
  { id: 'agentStream',   tier: 'A', metric: 'structure' },
  { id: 'assistantCard', tier: 'A', metric: 'structure' },
];

// ─────────────────────────────────────────────────────────────────────────────
// 页面内探针（注入后求值）
// ─────────────────────────────────────────────────────────────────────────────
export const REAL_PROBE = String.raw`(function () {
  'use strict';
  var R = {};
  function now() { return performance.now(); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function nextFrame() { return new Promise(function (r) { requestAnimationFrame(function () { r(); }); }); }
  function nf(n) { n = n || 2; var p = Promise.resolve(); for (var i = 0; i < n; i++) p = p.then(nextFrame); return p; }

  R.meta = function () {
    return {
      headless: !!(navigator.userAgent && /Headless/i.test(navigator.userAgent)),
      kbPath: (window.state && (window.state.kbPath || window.state.root)) || null,
      currentPath: (window.state && window.state.currentPath) || null,
      viewMode: (window.state && window.state.viewMode) || null,
      mathjaxCount: document.querySelectorAll('#preview mjx-container').length,
      previewBlocks: document.querySelectorAll('#preview .-src-block').length,
    };
  };

  // 确保预览就绪：切到 preview 视图 + 等块 > 0 + 等公式排版落定。
  //   !! 首版漏了这步：真机启动后 viewMode 可能仍是 source（previewBlocks=0、mathjax=0）
  //   => inlineMath 会把"预览没加载"误判成"公式没排版"（假红）。
  R.ensurePreview = async function () {
    for (var i = 0; i < 8; i++) {
      var m = (window.state && window.state.viewMode) || null;
      if (m === 'preview') break;
      var b = document.querySelector('.-view-btn[data-view="preview"]');
      if (b) b.click();
      await sleep(400);
    }
    var t0 = now();
    while (now() - t0 < 30000 && document.querySelectorAll('#preview .-src-block').length === 0) await sleep(150);
    if (window.state && window.state._mathPending && typeof window.state._mathPending.then === 'function') {
      try { await window.state._mathPending; } catch (e) {}
    }
    await nf(4);
    return {
      viewMode: (window.state && window.state.viewMode) || null,
      blocks: document.querySelectorAll('#preview .-src-block').length,
      mathjax: document.querySelectorAll('#preview mjx-container').length,
    };
  };

  // ── 1. kpHover：hover KP 项 → 预览高亮落地 ──
  R.kpHover = async function (ctx) {
    var items = document.querySelectorAll('#kp-list .-kp-item');
    if (!items.length) {
      var t0 = now();
      while (now() - t0 < 8000 && !document.querySelectorAll('#kp-list .-kp-item').length) await sleep(200);
      items = document.querySelectorAll('#kp-list .-kp-item');
    }
    if (!items.length) return { samples: [], error: 'no-kp-item', kpCount: 0 };

    // !! 不得用 "await nextFrame() x2 后取时间差" —— 那只会得到 2x16.7ms 的固定帧等待，
    //    与"高亮是否落地"无关（是我反复踩过的循环论证）。
    //    正确做法：用 MutationObserver 记录**预览区真正发生变化的时刻**，
    //    结束于"最后一次变更后 3 帧无新记录"（idle 判据），并校验变化确实发生。
    var samples = [];
    var observed = [];
    var rounds = (ctx && ctx.items) || 5;
    var n = Math.min(rounds, items.length);
    var preview = document.getElementById('preview');
    if (!preview) return { samples: [], error: 'no-preview' };

    for (var i = 0; i < n; i++) {
      var it = items[i];
      var r = it.getBoundingClientRect();
      var recs = [];
      var mo = new MutationObserver(function (list) { recs.push(list.length); });
      mo.observe(preview, { subtree: true, attributes: true, childList: true, characterData: true });
      var t = now();
      it.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, clientX: r.left + 5, clientY: r.top + 5 }));
      it.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false, clientX: r.left + 5, clientY: r.top + 5 }));
      it.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: r.left + 5, clientY: r.top + 5 }));
      // idle 判据：连续 3 帧无新变更记录即视为落定（最多 20 帧）
      var idle = 0, frames = 0, totalRecs = 0;
      while (idle < 3 && frames < 20) {
        await nextFrame();
        frames++;
        var got = recs.reduce(function (a, b) { return a + b; }, 0);
        if (got > totalRecs) { totalRecs = got; idle = 0; } else { idle++; }
      }
      var dt = now() - t;
      mo.disconnect();
      observed.push({ i: i, records: totalRecs, frames: frames });
      // 只有真的产生了 DOM 变更才算有效读数；否则是空转
      if (totalRecs > 0) samples.push(dt);
      it.dispatchEvent(new MouseEvent('mouseleave', { bubbles: false }));
      it.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }));
      await nextFrame(); await nextFrame();
    }
    var effectiveCount = observed.filter(function (o) { return o.records > 0; }).length;
    return {
      samples: samples,
      kpCount: items.length,
      observed: observed,
      effectiveCount: effectiveCount,
      // 判别力守卫：一次 DOM 变化都没观测到 => 读数无效，不得当绿
      effective: effectiveCount > 0,
      note: effectiveCount > 0 ? null : 'hover 未引起预览区任何 DOM 变化（该 KB 可能无 KP band 高亮，或选择器不符）',
    };
  };

  // ── 2. inlineMath：A10 按块计数（真机判据） ──
  R.inlineMath = async function () {
    var body = window.state && window.state.doc && window.state.doc.body;
    if (!body) return { error: 'no-doc' };
    var doc = window.MemoriaParser.parse(body);
    // 等公式排版落定
    if (window.state && window.state._mathPending && typeof window.state._mathPending.then === 'function') {
      try { await window.state._mathPending; } catch (e) {}
    }
    await nf(3);
    var perBlock = [];
    var failures = [];
    for (var i = 0; i < doc.blocks.length; i++) {
      var blk = doc.blocks[i];
      var c = 0;
      (function walk(nd) {
        if (!nd) return;
        if (nd.type === 'math_inline') c++;
        if (nd.children) for (var j = 0; j < nd.children.length; j++) walk(nd.children[j]);
        if (nd.items) for (var j = 0; j < nd.items.length; j++) walk(nd.items[j]);
      })(blk);
      if (c === 0) continue;
      var el = document.querySelector('#preview .-src-block[data--block-index="' + i + '"]');
      var typeset = el ? el.querySelectorAll('mjx-container[data--inline-math="true"]').length : 0;
      perBlock.push({ i: i, astInline: c, domTypeset: typeset });
      if (typeset !== c) failures.push({ i: i, astInline: c, domTypeset: typeset });
    }
    return {
      applicable: perBlock.length > 0,
      blocksWithInline: perBlock.length,
      totalInline: perBlock.reduce(function (a, b) { return a + b.astInline; }, 0),
      totalTypeset: perBlock.reduce(function (a, b) { return a + b.domTypeset; }, 0),
      failures: failures,
      perBlock: perBlock,
      ok: failures.length === 0,
      mathjaxTotal: document.querySelectorAll('#preview mjx-container').length,
    };
  };

  // ── 3. agentStream：agent 面板最小结构 ──
  R.agentStream = async function () {
    // 真实容器是 #agent-messages（不是 #agent-panel），消息体为 .-agent-msg-body
    var toggle = document.getElementById('btn-agent');
    if (toggle) { toggle.click(); await sleep(500); }
    // 等面板/消息渲染
    var t0 = now();
    while (now() - t0 < 6000 && !document.querySelector('.-agent-msg-body') &&
           !document.querySelector('#agent-messages')) await sleep(200);
    await nf(3);
    var container = document.getElementById('agent-messages');
    var bodies = document.querySelectorAll('.-agent-msg-body');
    var emptyNodes = document.querySelectorAll('.-agent-empty');
    var placeholderRe = /^\s*(生成中|thinking|\.\.\.|…)\s*$/i;
    var placeholders = 0;
    var blockCounts = [];
    var mathTotal = 0;
    for (var i = 0; i < bodies.length; i++) {
      var t = (bodies[i].textContent || '').trim();
      if (placeholderRe.test(t)) placeholders++;
      var nb = bodies[i].querySelectorAll('p,li,h1,h2,h3,h4,h5,h6,pre,table,ul,ol').length;
      blockCounts.push(nb);
      mathTotal += bodies[i].querySelectorAll('mjx-container').length;
    }
    return {
      panelPresent: !!container,
      bodyCount: bodies.length,
      emptyNodeCount: emptyNodes.length,
      placeholderCount: placeholders,
      blockCounts: blockCounts,
      mathJaxInBodies: mathTotal,
      // 最小结构：有消息体 => 块数>0 且无占位
      ok: bodies.length > 0 && blockCounts.every(function (n) { return n > 0; }) && placeholders === 0,
      note: bodies.length === 0
        ? 'no-conversation-data：面板存在但无历史消息（需真实会话才能判流式结构）'
        : null,
    };
  };

  // ── 4. assistantCard：助手弹窗 / 复阅卡最小结构（**不依赖 data--src-line**） ──
  R.assistantCard = async function () {
    var out = { modes: {} };
    // 4a 复阅卡管理弹窗：入口 #btn-review → .-review-manage-box，卡片列表 #-rm-list
    var rm = document.querySelector('.-review-manage-box');
    if (!rm) {
      var btn = document.getElementById('btn-review');
      if (btn) { btn.click(); await sleep(900); }
      rm = document.querySelector('.-review-manage-box');
    }
    if (rm) {
      // 等卡片列表从 RPC 返回
      var t0 = now();
      while (now() - t0 < 5000 && rm.querySelectorAll('#-rm-list > *').length === 0) await sleep(200);
      var listEl = rm.querySelector('#-rm-list');
      var cardItems = listEl ? listEl.querySelectorAll(':scope > *').length : 0;
      var textNodes = rm.querySelectorAll('p,li,h1,h2,h3,h4,h5,h6,pre,table').length;
      out.modes.reviewCard = {
        present: true,
        listItems: cardItems,
        textBlocks: textNodes,
        mathJax: rm.querySelectorAll('mjx-container').length,
        // !! 明确不使用 data--src-line（P4b 已从该链移除），只数结构块
        usesSrcLineAttr: rm.querySelectorAll('[data--src-line]').length,
        // 最小结构：弹窗存在且列表/文本有内容
        ok: cardItems > 0 || textNodes > 0,
        note: (cardItems === 0 && textNodes === 0) ? 'review-manage 打开但列表为空（该 KB 无复习卡数据）' : null,
      };
      var closeBtn = rm.querySelector('#-rm-close');
      if (closeBtn) { try { closeBtn.click(); } catch (e) {} await sleep(300); }
    } else {
      out.modes.reviewCard = { present: false, ok: null, note: 'no-review-entry（#btn-review 不存在或未打开）' };
    }
    // 4b 助手预览弹窗（.-modal 中的 markdown 预览）
    var modals = document.querySelectorAll('.-modal:not(.hidden)');
    var assistant = null;
    for (var i = 0; i < modals.length; i++) {
      if (modals[i].querySelector('.-preview-content, .-src-block, .-md-body')) { assistant = modals[i]; break; }
    }
    if (assistant) {
      var ab = assistant.querySelectorAll('.-src-block, .-preview-content p, .-md-body p').length;
      out.modes.assistantModal = {
        present: true, blocks: ab,
        mathJax: assistant.querySelectorAll('mjx-container').length,
        usesSrcLineAttr: assistant.querySelectorAll('[data--src-line]').length,
        ok: ab > 0,
      };
    } else {
      out.modes.assistantModal = { present: false, ok: null, note: 'no-assistant-modal（需真实交互打开助手预览）' };
    }
    return out;
  };

  return R;
})()`;

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) { const k = t.slice(2); const n = argv[i + 1]; if (n && !n.startsWith('--')) { a[k] = n; i++; } else a[k] = true; }
    else a._.push(t);
  }
  return a;
}

async function httpJson(url) { const r = await fetch(url); return await r.json(); }

async function resolveCdpWs(endpoint) {
  const base = String(endpoint).replace(/\/+$/, '');
  const list = await httpJson(base + '/json/list').catch(() => null);
  if (!list) throw new Error('CDP endpoint 无响应：' + base);
  const pages = (list || []).filter((t) => t.type === 'page' && t.webSocketDebuggerUrl &&
    !/^devtools:\/\//.test(t.url || '') && !/^about:blank$/i.test(t.url || ''));
  if (!pages.length) throw new Error('找不到应用页面目标: ' + JSON.stringify(list).slice(0, 200));
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

function pct(vals, q) {
  const v = [...vals].sort((a, b) => a - b);
  const n = v.length;
  if (!n) return null;
  if (n === 1) return v[0];
  const h = (n - 1) * q;
  const lo = Math.floor(h), hi = Math.min(lo + 1, n - 1);
  return v[lo] + (v[hi] - v[lo]) * (h - lo);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpEndpoint = args.cdp || 'http://127.0.0.1:9500';
  const out = args.out || null;
  const rounds = parseInt(args.rounds || '3', 10);
  let want = String(args.ops || 'all');
  if (want === 'all') want = OPS.map((o) => o.id); else want = want.split(',').map((s) => s.trim()).filter(Boolean);
  const selected = OPS.filter((o) => want.includes(o.id));

  const result = {
    schema: 'memoria-realapp-coverage/v1',
    mode: 'real',
    cdpEndpoint,
    rounds,
    startedAt: new Date().toISOString(),
    ops: {},
  };

  let cdp = null;
  let exitCode = 1;
  try {
    const wsUrl = await resolveCdpWs(cdpEndpoint);
    cdp = await CDP.connect(wsUrl);
    await cdp.send('Runtime.enable');
    await cdp.waitFor('!!window.MemoriaApp && !!window.MemoriaParser', { label: 'app', timeout: 90000 });
    await cdp.evalJS('window.__realcov = ' + REAL_PROBE);
    // !! 必须先确保预览就绪，否则 previewBlocks=0 => inlineMath 假红
    result.previewReady = await cdp.evalJS('window.__realcov.ensurePreview()');
    result.meta = await cdp.evalJS('window.__realcov.meta()');

    for (const op of selected) {
      const opResult = { id: op.id, tier: op.tier, metric: op.metric, mode: 'real', runs: [] };
      try {
        for (let r = 0; r < rounds; r++) {
          const res = await cdp.evalJS(`window.__realcov.${op.id}({items: 5})`);
          opResult.runs.push(res);
          await sleep(300);
        }
        opResult.status = 'ran';
      } catch (e) {
        opResult.status = 'error';
        opResult.error = String((e && e.message) || e);
      }
      // 汇总
      if (op.metric === 'latency') {
        const all = [];
        for (const r of opResult.runs) for (const s of (r.samples || [])) all.push(s);
        opResult.samples = all.length;
        opResult.p50 = pct(all, 0.5) != null ? +pct(all, 0.5).toFixed(2) : null;
        opResult.p95 = pct(all, 0.95) != null ? +pct(all, 0.95).toFixed(2) : null;
        opResult.max = all.length ? +Math.max(...all).toFixed(2) : null;
        opResult.kpCount = (opResult.runs[0] || {}).kpCount || 0;
      } else if (op.metric === 'count') {
        const first = opResult.runs[0] || {};
        opResult.ok = opResult.runs.every((r) => r.ok === true);
        opResult.applicable = first.applicable;
        opResult.blocksWithInline = first.blocksWithInline;
        opResult.totalInline = first.totalInline;
        opResult.totalTypeset = first.totalTypeset;
        opResult.mathjaxTotal = first.mathjaxTotal;
        opResult.failures = first.failures || [];
      } else {
        const first = opResult.runs[0] || {};
        opResult.ok = opResult.runs.every((r) => r.ok === true);
        opResult.detail = first;
      }
      result.ops[op.id] = opResult;
    }
    result.ok = true;
    exitCode = 0;
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) cdp.close();
    if (out) {
      fs.mkdirSync(path.dirname(out), { recursive: true });
      fs.writeFileSync(out, JSON.stringify(result, null, 2), 'utf8');
      process.stdout.write('__REALCOV__' + JSON.stringify({ ok: result.ok, out, ops: Object.keys(result.ops) }) + '\n');
    } else {
      process.stdout.write(JSON.stringify(result, null, 2) + '\n');
    }
    setTimeout(() => process.exit(exitCode), 1500).unref();
  }
  return exitCode;
}

const code = await main();
process.exitCode = code;
