#!/usr/bin/env node
/**
 * task-183 真机 DOM 验收探针（ui-designer，2026-10-26）
 *
 * 目的：证明「缓存命中率」**真的**从 agent 状态条移到了输入框下方（与上下文圆环同一行），
 * 而不是 CSS 藏旧 + 另渲染一份。全部用 DOM 查询 / boundingClientRect / computed style 判定，
 * 截图只是附件。
 *
 * 覆盖 task-183 验收 T1–T6：
 *   T1 状态条区域不再含命中率（DOM subtree 文本 + 节点检查）
 *   T2 命中率在输入框下方（composer 内、input 之后）、与圆环包围盒不相交、圆环在左
 *   T3 悬停明细含 hit/miss/rate 口径（加载 fixture 会话后数字必须是 60 / 40 / 60%）
 *   T4 状态条无空壳（事实串 3 项、无空段、无多余分隔符）
 *   T5 输入框高度变化（真指针拖 #agent-input-resize）后跟随、不重叠、不被遮挡
 *   T6 面板 260 / 520px 两种宽度下不换行错乱、不溢出、不重叠
 *
 * 用法：node probe.mjs --port 9623 --out verify.json
 * 前置：应用以 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<port> 启动（run_probe.ps1）。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function arg(name, def = null) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : def;
}

// ── 极简 CDP（与 scripts/benchmark/surface/cdp.mjs 同款思路，零依赖）──────────
class CDP {
  constructor(ws) {
    this.ws = ws; this._id = 0; this._pending = new Map();
    ws.addEventListener('message', (ev) => {
      let m; try { m = JSON.parse(typeof ev.data === 'string' ? ev.data : String(ev.data)); } catch { return; }
      if (m.id != null) {
        const p = this._pending.get(m.id); if (!p) return;
        this._pending.delete(m.id);
        m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
      }
    });
  }
  static connect(url) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      const to = setTimeout(() => reject(new Error('CDP 连接超时 ' + url)), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); resolve(new CDP(ws)); });
      ws.addEventListener('error', () => reject(new Error('CDP 连接失败 ' + url)));
    });
  }
  send(method, params = {}) {
    const id = ++this._id;
    return new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

async function httpJson(url) {
  const r = await fetch(url);
  return r.json();
}

async function waitTarget(port, timeoutMs = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
      const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl && !x.url.startsWith('devtools://'));
      if (t) return t;
    } catch { /* 还没起来 */ }
    await sleep(250);
  }
  throw new Error('等待 CDP page target 超时（端口 ' + port + '）');
}

const CHECKS = [];
function check(id, ok, detail, data) {
  CHECKS.push({ id, ok: !!ok, detail, data: data === undefined ? null : data });
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${id}  ${detail}`);
}

// ── 页面内工具（在浏览器上下文执行）──────────────────────────────────────────
const PAGE_HELPERS = `
  window.__t183 = {
    rect(el) {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: +r.x.toFixed(2), y: +r.y.toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2),
               top: +r.top.toFixed(2), bottom: +r.bottom.toFixed(2), left: +r.left.toFixed(2), right: +r.right.toFixed(2) };
    },
    overlap(a, b) {
      if (!a || !b) return false;
      return Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 &&
             Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5;
    },
    pick() {
      return {
        bar: document.querySelector('#agent-statusbar'),
        facts: document.querySelector('#agent-statusbar-facts'),
        composer: document.querySelector('.-agent-composer'),
        input: document.querySelector('#agent-input'),
        row: document.getElementById('agent-ctx-ring-row'),
        ring: document.getElementById('agent-ctx-ring'),
        cache: document.getElementById('agent-cache-hit'),
        actions: document.querySelector('.-agent-composer-actions'),
      };
    },
    snapshot() {
      const p = window.__t183.pick();
      const barText = (p.bar ? (p.bar.innerText || p.bar.textContent || '') : '').replace(/\\s+/g, ' ').trim();
      const factsText = (p.facts ? (p.facts.textContent || '') : '').replace(/\\s+/g, ' ').trim();
      const segs = factsText.split('·').map((s) => s.trim());
      const cs = p.cache ? getComputedStyle(p.cache) : null;
      return {
        barText, factsText, factsSegments: segs,
        factsEmptySegments: segs.filter((s) => s === '').length,
        separatorCount: (factsText.match(/·/g) || []).length,
        cacheInStatusbar: !!(p.bar && p.cache && p.bar.contains(p.cache)),
        cacheText: p.cache ? (p.cache.textContent || '') : null,
        cacheTitle: p.cache ? (p.cache.title || '') : null,
        cacheAria: p.cache ? (p.cache.getAttribute('aria-label') || '') : null,
        cacheParentId: p.cache && p.cache.parentNode ? p.cache.parentNode.id : null,
        rowParentIsComposer: !!(p.row && p.composer && p.row.parentNode === p.composer),
        cacheInComposer: !!(p.composer && p.cache && p.composer.contains(p.cache)),
        cacheRect: window.__t183.rect(p.cache),
        ringRect: window.__t183.rect(p.ring),
        inputRect: window.__t183.rect(p.input),
        rowRect: window.__t183.rect(p.row),
        composerRect: window.__t183.rect(p.composer),
        actionsRect: window.__t183.rect(p.actions),
        cacheStyle: cs ? { fontSize: cs.fontSize, color: cs.color, whiteSpace: cs.whiteSpace,
                           overflow: cs.overflow, textOverflow: cs.textOverflow, order: cs.order } : null,
        ringOrder: p.ring ? getComputedStyle(p.ring).order : null,
        rowScroll: p.row ? { scrollWidth: p.row.scrollWidth, clientWidth: p.row.clientWidth } : null,
        dockWidth: document.querySelector('#-agent-dock') ? document.querySelector('#-agent-dock').getBoundingClientRect().width : null,
        inputHeight: p.input ? p.input.getBoundingClientRect().height : null,
        hasMemoriaAgentPanel: !!window.MemoriaAgentPanel,
        historyRows: document.querySelectorAll('[data-hist-id]').length,
      };
    },
    overlapCacheRing() {
      return window.__t183.overlap(window.__t183.rect(document.getElementById('agent-cache-hit')),
                                   window.__t183.rect(document.getElementById('agent-ctx-ring')));
    },
  };
  true;
`;

// ── main ─────────────────────────────────────────────────────────────────────
async function main() {
  const port = Number(arg('port', '9623'));
  const outPath = arg('out', path.join(HERE, 'verify.json'));
  const target = await waitTarget(port);
  const cdp = await CDP.connect(target.webSocketDebuggerUrl);
  const results = { generated_at: new Date().toISOString(), port, target_url: target.url,
                    app: 'memoria.app.desktop (pywebview/WebView2, MEMORIA_MODE=dev)',
                    kb_fixture: 'artifacts/agent/verify/todo/agent-panel-cache-indicator/kb (tests/probe-kb copy + fixture session)',
                    checks: [], snapshots: {} };

  async function evalJs(expression) {
    const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('页面脚本异常：' + JSON.stringify(r.exceptionDetails).slice(0, 500));
    return r.result ? r.result.value : undefined;
  }
  async function waitFor(expr, label, timeoutMs = 20000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      try { if (await evalJs(expr)) return true; } catch { /* 页面未就绪 */ }
      await sleep(200);
    }
    throw new Error(`等待超时：${label}`);
  }
  async function screenshot(name) {
    try {
      const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(path.join(HERE, name), Buffer.from(shot.data, 'base64'));
      return name;
    } catch { return null; }
  }

  try {
    await cdp.send('Runtime.enable');
    await cdp.send('Page.enable');
    await waitFor(`document.readyState === 'complete'`, '页面加载完成');
    await waitFor(`document.querySelector('#-agent-dock') && document.querySelector('.-agent-composer')`, 'agent dock 就绪', 30000);
    await waitFor(`window.MemoriaAgentPanel && document.getElementById('agent-cache-hit')`, '缓存格已挂载', 30000);
    await evalJs(PAGE_HELPERS);
    try { await evalJs(`window.MemoriaAgentPanel.open && window.MemoriaAgentPanel.open(); true`); } catch { /* 异步 open，忽略 */ }
    await sleep(900);

    // ── T1 状态条不再出现命中率 ────────────────────────────────────────────
    let s = await evalJs(`window.__t183.snapshot()`);
    results.snapshots.t1 = s;
    check('T1-状态条无命中率文本', !/缓存命中率|Cache hit/i.test(s.barText),
      `#agent-statusbar 文本 = "${s.barText}"`);
    check('T1-命中率不是"藏"在状态条里',
      !s.cacheInStatusbar && s.cacheParentId === 'agent-ctx-ring-row',
      `cache 父节点 = #${s.cacheParentId}；在状态条内 = ${s.cacheInStatusbar}`);
    check('T1-旧槽位无残留节点',
      (await evalJs(`document.querySelectorAll('#agent-statusbar-facts > .-agent-statusbar-hit, #agent-statusbar-facts [data-statusbar-hit]').length`)) === 0,
      '状态条事实串里没有旧的命中率槽节点');

    // ── T4 状态条无空壳 ────────────────────────────────────────────────────
    check('T4-事实串 3 项且无空段/多余分隔符',
      s.factsSegments.length === 3 && s.factsEmptySegments === 0 && s.separatorCount === 2,
      `facts = "${s.factsText}"（${s.factsSegments.length} 项 / 空段 ${s.factsEmptySegments} / 分隔符 ${s.separatorCount}）`);

    // ── T2 输入框下方、与圆环不重叠 ───────────────────────────────────────
    check('T2-缓存格在输入框下方且在 composer 内',
      !!s.cacheRect && !!s.inputRect && s.cacheRect.top >= s.inputRect.bottom - 1 && s.cacheInComposer,
      `cache.top=${s.cacheRect && s.cacheRect.top} / input.bottom=${s.inputRect && s.inputRect.bottom} / 在 composer 内=${s.cacheInComposer}`);
    check('T2-缓存格与圆环包围盒不相交',
      !(await evalJs(`window.__t183.overlapCacheRing()`)),
      `ring=${JSON.stringify(s.ringRect)} cache=${JSON.stringify(s.cacheRect)}`);
    check('T2-圆环在左、命中率在右',
      !!s.cacheRect && !!s.ringRect && s.cacheRect.left >= s.ringRect.right - 0.5 && s.cacheStyle.order === '1' && s.ringOrder === '0',
      `ring.right=${s.ringRect && s.ringRect.right} <= cache.left=${s.cacheRect && s.cacheRect.left}；order(cache)=${s.cacheStyle && s.cacheStyle.order}/order(ring)=${s.ringOrder}`);
    check('T2-不与发送按钮行重叠',
      !(await evalJs(`window.__t183.overlap(window.__t183.rect(document.getElementById('agent-cache-hit')), window.__t183.rect(document.querySelector('.-agent-composer-actions')))`)),
      `actions=${JSON.stringify(s.actionsRect)}`);
    check('T2-字号与状态条一致（11px 次要色）',
      !!s.cacheStyle && s.cacheStyle.fontSize === '11px' && /^rgb\(\s*133\s*,\s*133\s*,\s*133/.test(s.cacheStyle.color || ''),
      `font-size=${s.cacheStyle && s.cacheStyle.fontSize} color=${s.cacheStyle && s.cacheStyle.color}`);

    // ── T3 悬停明细（先看无会话口径，再载入 fixture 会话看数字）───────────
    check('T3-无会话时明说未知且不瞎报 0%',
      /未知|unknown/i.test(s.cacheTitle || '') && !/0%/.test(s.cacheTitle || ''),
      `初始 title = ${JSON.stringify((s.cacheTitle || '').split('\n'))}`);
    await evalJs(`(() => { const b = document.querySelector('[data-sidebar-tab="history"]'); if (b) b.click(); return true; })()`);
    await waitFor(`document.querySelectorAll('[data-hist-id]').length > 0`, '历史会话列表出现');
    const histCount = await evalJs(`document.querySelectorAll('[data-hist-id]').length`);
    const sid = await evalJs(`document.querySelector('[data-hist-id]').getAttribute('data-hist-id')`);
    await evalJs(`document.querySelector('[data-hist-id]').click(); true`);
    await waitFor(`(() => { const t = (document.getElementById('agent-cache-hit') || {}).title || ''; return /60%/.test(t); })()`, '缓存明细随会话回放刷新', 25000);
    const s3 = await evalJs(`window.__t183.snapshot()`);
    results.snapshots.t3 = s3;
    const titleLines = (s3.cacheTitle || '').split('\n');
    check('T3-悬停明细含 hit/miss/rate 完整口径',
      titleLines.length >= 2 && /60/.test(s3.cacheTitle) && /40/.test(s3.cacheTitle) && /60%/.test(s3.cacheTitle),
      `会话 ${sid}（列表 ${histCount} 条）载入后 title = ${JSON.stringify(titleLines)}`);
    check('T3-载入会话后状态条仍无命中率', !/缓存命中率|Cache hit/i.test(s3.barText), `状态条 = "${s3.barText}"`);
    check('T3-aria-label 与可见文本一致', s3.cacheAria === s3.cacheText, `aria="${s3.cacheAria}" text="${s3.cacheText}"`);
    await screenshot('shot-t3-session-loaded.png');

    // ── T5 输入框高度变化：真指针拖 #agent-input-resize ────────────────────
    async function dragHandle(dy) {
      const geo = await evalJs(`(() => {
        const r = document.querySelector('#agent-input-resize').getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2, h: document.querySelector('#agent-input').getBoundingClientRect().height };
      })()`);
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: geo.x, y: geo.y, button: 'none', buttons: 0 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: geo.x, y: geo.y, button: 'left', buttons: 1, clickCount: 1 });
      for (let i = 1; i <= 6; i++) {
        await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: geo.x, y: geo.y + (dy * i) / 6, button: 'left', buttons: 1 });
        await sleep(16);
      }
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: geo.x, y: geo.y + dy, button: 'left', buttons: 0, clickCount: 1 });
      await sleep(300);
      return geo.h;
    }
    const h0 = await evalJs(`document.querySelector('#agent-input').getBoundingClientRect().height`);
    await dragHandle(-80);   // 向上拖 = 调高（把手在输入框下沿）
    const s5a = await evalJs(`window.__t183.snapshot()`);
    results.snapshots.t5a = s5a;
    const h1 = s5a.inputHeight;
    check('T5-把手真的调高了输入框', h1 > h0 + 20, `input height ${h0} -> ${h1}`);
    check('T5-调高后仍跟随且不重叠',
      s5a.cacheRect.top >= s5a.inputRect.bottom - 1 && !(await evalJs(`window.__t183.overlapCacheRing()`)),
      `input.bottom=${s5a.inputRect.bottom} cache.top=${s5a.cacheRect.top}`);
    await dragHandle(120);   // 向下拖 = 调低
    const s5b = await evalJs(`window.__t183.snapshot()`);
    results.snapshots.t5b = s5b;
    const h2 = s5b.inputHeight;
    check('T5-调低后仍跟随且不重叠', h2 < h1 && s5b.cacheRect.top >= s5b.inputRect.bottom - 1 &&
      !(await evalJs(`window.__t183.overlapCacheRing()`)), `input height ${h1} -> ${h2}`);
    check('T5-缓存格未被输入框/发送按钮遮挡',
      s5b.cacheRect.bottom <= s5b.actionsRect.top + 0.5 && s5b.cacheRect.top >= s5b.inputRect.bottom - 1,
      `cache.bottom=${s5b.cacheRect.bottom} <= actions.top=${s5b.actionsRect.top}`);
    await screenshot('shot-t5-resized-input.png');

    // ── T6 面板宽度 260 / 520 ──────────────────────────────────────────────
    for (const targetPx of [260, 520]) {
      const rem = Number((targetPx / 16).toFixed(4));
      await evalJs(`window.MemoriaAgentPanel.setDockWidthForTest(${rem}); true`);
      await sleep(500);
      const w = await evalJs(`window.__t183.snapshot()`);
      results.snapshots['t6_' + targetPx] = w;
      const noOverlap = !(await evalJs(`window.__t183.overlapCacheRing()`));
      const singleLine = !!w.cacheRect && w.cacheRect.h <= 20;
      const noOverflow = !!w.rowScroll && w.rowScroll.scrollWidth <= w.rowScroll.clientWidth + 1;
      const inside = !!w.cacheRect && !!w.composerRect &&
        w.cacheRect.left >= w.composerRect.left - 1 && w.cacheRect.right <= w.composerRect.right + 1;
      check(`T6-${targetPx}px 不重叠/不换行/不溢出/在面板内`,
        noOverlap && singleLine && noOverflow && inside,
        `dock=${w.dockWidth && w.dockWidth.toFixed(1)}px cache=${JSON.stringify(w.cacheRect)} 单行=${singleLine} 不重叠=${noOverlap} 不溢出=${noOverflow} 在面板内=${inside}`);
      await screenshot(`shot-t6-${targetPx}px.png`);
    }

    results.final = await evalJs(`window.__t183.snapshot()`);
    await screenshot('shot-final.png');
  } finally {
    cdp.close();
  }

  results.checks = CHECKS;
  results.passed = CHECKS.filter((c) => c.ok).length;
  results.failed = CHECKS.filter((c) => !c.ok).length;
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2) + '\n', 'utf8');
  console.log(`-- T1–T6: ${results.passed} PASS / ${results.failed} FAIL --`);
  console.log('JSON:', outPath);
  process.exit(results.failed ? 1 : 0);
}

main().catch((e) => { console.error('FAIL:', (e && e.stack) || e); process.exit(2); });
