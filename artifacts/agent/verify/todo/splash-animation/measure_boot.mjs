#!/usr/bin/env node
/**
 * 冷启动耗时探针（task-186 T-splash-2 对照基线/改后测量）
 *
 * 口径（改前/改后完全一致）：
 *   总时长 = 本次应用进程启动时刻(t0, 由 run_boot_measure.ps1 传 --t0)
 *            → 页面里 `html.-booting` 被移除的时刻（= 既有"外框跑马灯"结束、首个文档已打开/8s 兜底）
 *   该标记是应用**既有**的"加载完成"指示，正好对应"从冷启动到可交互"。
 *
 * 证明方式：在页面里装 MutationObserver，记录 `-booting` 消失的 `Date.now()`；
 *   若探针 attach 时它**已经**消失 ⇒ 本次 trial 无效（记 invalid，调用方重跑），绝不猜。
 *
 * 用法：node measure_boot.mjs --port 9627 --t0 <epoch_ms> --out run.json
 */
import fs from 'node:fs';
import path from 'node:path';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function arg(name, def = null) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : def;
}

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
      const to = setTimeout(() => reject(new Error('CDP 连接超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); resolve(new CDP(ws)); });
      ws.addEventListener('error', () => reject(new Error('CDP 连接失败')));
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

async function main() {
  const port = Number(arg('port', '9627'));
  const t0 = Number(arg('t0', '0'));
  const out = arg('out', path.join(path.dirname(new URL(import.meta.url).pathname), 'run.json'));
  const target = await (async () => {
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl && !x.url.startsWith('devtools://'));
        if (t) return t;
      } catch { /* not ready */ }
      await sleep(50);
    }
    throw new Error('等待 page target 超时');
  })();
  const cdp = await CDP.connect(target.webSocketDebuggerUrl);
  const result = { valid: false, t0, port, attached_at: Date.now(), url: target.url };
  try {
    await cdp.send('Runtime.enable');
    const install = `(() => {
      window.__bootProbe = { installedAt: Date.now(), removedAt: 0, wasBootingAtInstall: document.documentElement.classList.contains('-booting') };
      const html = document.documentElement;
      const obs = new MutationObserver(() => {
        if (!html.classList.contains('-booting') && !window.__bootProbe.removedAt) {
          window.__bootProbe.removedAt = Date.now();
          obs.disconnect();
        }
      });
      obs.observe(html, { attributes: true, attributeFilter: ['class'] });
      return window.__bootProbe;
    })()`;
    const ev = async (expression) => {
      const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: false });
      if (r.exceptionDetails) throw new Error('页面异常：' + JSON.stringify(r.exceptionDetails).slice(0, 300));
      return r.result ? r.result.value : undefined;
    };
    let installed = null;
    // 页面可能还没到 app.js 执行（-booting 尚未加上）⇒ 等到它出现或已消失
    const instDeadline = Date.now() + 15000;
    while (Date.now() < instDeadline) {
      try {
        installed = await ev(install);
        if (installed && (installed.wasBootingAtInstall || (await ev(`document.readyState === 'complete'`)))) break;
      } catch { /* 页面重载中 */ }
      await sleep(40);
    }
    result.installed = installed;
    result.was_booting_at_install = !!(installed && installed.wasBootingAtInstall);
    // 等 -booting 消失（上限 20s）
    const waitDeadline = Date.now() + 20000;
    let removedAt = 0;
    while (Date.now() < waitDeadline) {
      removedAt = await ev(`(window.__bootProbe && window.__bootProbe.removedAt) || 0`);
      if (removedAt) break;
      await sleep(20);
    }
    result.removed_at = removedAt;
    result.perf = await ev(`(() => {
      const nav = performance.getEntriesByType('navigation')[0] || {};
      const paints = (performance.getEntriesByType('paint') || []).map((p) => ({ name: p.name, startTime: +p.startTime.toFixed(1) }));
      return { domContentLoadedEnd: nav.domContentLoadedEventEnd ? +nav.domContentLoadedEventEnd.toFixed(1) : null,
               loadEnd: nav.loadEventEnd ? +nav.loadEventEnd.toFixed(1) : null,
               responseEnd: nav.responseEnd ? +nav.responseEnd.toFixed(1) : null,
               paints, nowAtMeasure: +performance.now().toFixed(1), timeOrigin: performance.timeOrigin };
    })()`);
    result.boot_ms = removedAt && t0 ? removedAt - t0 : null;
    result.valid = !!(result.boot_ms && result.was_booting_at_install);
    if (!result.was_booting_at_install) result.invalid_reason = 'attach 时 -booting 已消失（无法测到真实起点）';
    else if (!removedAt) result.invalid_reason = '-booting 20s 内未消失';
    // 指向第 3 方域名的资源（T-splash-7 零网络请求的旁证）
    result.external_resources = await ev(`performance.getEntriesByType('resource')
        .filter((r) => r.name && !/^(https?:\\/\\/(127\\.0\\.0\\.1|localhost)[:/])/.test(r.name) && !r.name.startsWith('data:'))
        .map((r) => r.name).slice(0, 20)`);
    result.splash = await ev(`(() => {
      const s = document.getElementById('memoria-splash');
      return s ? { present: true, classes: s.className, opacity: getComputedStyle(s).opacity } : { present: false };
    })()`);
  } finally {
    cdp.close();
  }
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(result, null, 2) + '\n', 'utf8');
  console.log('[measure] ' + JSON.stringify(result));
  process.exit(result.valid ? 0 : 1);
}

main().catch((e) => { console.error('[measure] FAIL', (e && e.stack) || e); process.exit(2); });
