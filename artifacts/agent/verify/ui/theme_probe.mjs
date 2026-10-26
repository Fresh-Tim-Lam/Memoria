#!/usr/bin/env node
/**
 * theme_probe.mjs —— 主题 token 缺口「先量再改」的测量脚本（ui-designer，2026-10-26）
 *
 * 目的：验证 C7 报出的「`--border-subtle` / `--text-muted` 深色未定义且无兜底」是【真缺陷】
 *       还是【只是注释不准】。做法是把**真实 CSS**（theme/memoria.css + theme/light.css + app.css）
 *       加载进真实浏览器（Edge headless + 零依赖 CDP），把使用这些 token 的**真实选择器**元素
 *       摆进 DOM，读 computed style，深/浅两主题各跑一遍。
 *
 * 判据（不看代码，看浏览器算出来的值）：
 *   · 若 `border-top-color` 落到 `currentColor`（= 正文色）而不是描边 token 的色值 ⇒ `var()` 无效
 *     ⇒ 声明在 computed-value 阶段失效 ⇒ **真缺陷**
 *   · 若 token 已定义（浅色下 `--border-subtle:#e8e8e8`）⇒ 应读到 rgb(232,232,232)（对照）
 *
 * 阳性对照（证明探针不是瞎的）：
 *   · 同一页面放一个用**已定义** token（`--border-sep`）的元素：必须读到真实色值；
 *   · 同一页面放一个显式 `color: rgb(1,2,3)` 的元素：必须原样读到。
 *
 * 用法：node artifacts/agent/verify/ui/theme_probe.mjs [--out artifacts/agent/verify/ui/theme-probe.json]
 * 产物：JSON（每元素深/浅 computed 值 + 判定）+ 两张截图（dark/light）。
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..', '..', '..'); // 仓库根
const STATIC = path.join(ROOT, 'src', 'memoria', 'ui', 'static');

const EDGE_CANDIDATES = [
  process.env.MEMORIA_EDGE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);

function findEdge() {
  for (const p of EDGE_CANDIDATES) if (fs.existsSync(p)) return p;
  throw new Error('找不到 msedge.exe；可用 MEMORIA_EDGE 指定');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 1. 静态服务器（只读静态目录 + 动态 fixture 页）───────────────────────────
const MIME = {
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
};

// 被测元素：选择器来自 app.css 中「无兜底引用 --border-subtle / --text-muted」的真实位置
const SUBJECTS = [
  { id: 'E1-import-section-title@179', cls: '-import-section-title', prop: 'border-top', token: '--border-subtle', expect: 'borderTopColor' },
  { id: 'E2-suggest-score--muted@1644', cls: '-suggest-score--muted', prop: 'color', token: '--text-muted', expect: 'color' },
  { id: 'E3-search-section-label@1659', cls: '-search-section-label', prop: 'color', token: '--text-muted', expect: 'color' },
  { id: 'E4-search-section-label-border@1660', cls: '-search-section-label', prop: 'border-top', token: '--border-subtle', expect: 'borderTopColor' },
  { id: 'E5-toolbar-search-scope-btn@2507', cls: '-toolbar-search-scope-btn', prop: 'color', token: '--text-muted', expect: 'color' },
  { id: 'E6-link-match-section@2904', cls: '-link-match-section', prop: 'color', token: '--text-muted', expect: 'color' },
  { id: 'E7-link-match-check-placeholder@2879', cls: '-link-match-check-placeholder', prop: 'color', token: '--text-muted', expect: 'color' },
  // 阳性对照 1：已定义 token（--border-sep 深 #303030 / 浅 #e8e8e8）
  { id: 'CONTROL-defined-token', cls: '-border-sep-probe', prop: 'border-top', token: '--border-sep', expect: 'borderTopColor', control: true },
  // 阳性对照 2：显式字面量色
  { id: 'CONTROL-literal-color', cls: '-literal-probe', prop: 'color', token: '(literal)', expect: 'color', control: true },
  // 附加：--theme-color 浅色未覆盖（比 --accent 用了深色值）
  { id: 'E8-theme-color@7789', cls: '-theme-color-probe', prop: 'background', token: '--theme-color', expect: 'backgroundColor' },
];

function fixtureHtml(theme) {
  const body = SUBJECTS.map((s) => `<div id="${s.id}" class="${s.cls}">样本</div>`).join('\n');
  const extra = `<style>
    .-border-sep-probe { border-top: 1px solid var(--border-sep); }
    .-literal-probe { color: rgb(1, 2, 3); }
    .-theme-color-probe { width: 10px; height: 10px; background: var(--theme-color); }
    body { margin: 0; }
    #probe-root { font-size: 13px; }
  </style>`;
  return `<!doctype html><html${theme === 'light' ? ' data-theme="light"' : ''}>
<head><meta charset="utf-8">
<link rel="stylesheet" href="/theme/memoria.css">
<link rel="stylesheet" href="/app/css/app.css">
<link rel="stylesheet" href="/theme/mermaid.css">
${theme === 'light' ? '<link rel="stylesheet" href="/theme/light.css">' : ''}
${extra}
</head><body><div id="probe-root">${body}</div></body></html>`;
}

function startServer() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      try {
        const u = new URL(req.url, 'http://x');
        if (u.pathname === '/__fixture') {
          const theme = u.searchParams.get('theme') === 'light' ? 'light' : 'dark';
          const html = fixtureHtml(theme);
          res.writeHead(200, { 'content-type': MIME['.html'] });
          res.end(html);
          return;
        }
        const rel = decodeURIComponent(u.pathname).replace(/^\/+/, '').split('?')[0];
        const file = path.join(STATIC, rel);
        if (!file.startsWith(STATIC) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
          res.writeHead(404); res.end('not found'); return;
        }
        res.writeHead(200, { 'content-type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream' });
        res.end(fs.readFileSync(file));
      } catch (e) {
        res.writeHead(500); res.end(String(e));
      }
    });
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

// ── 2. 极简 CDP（够用就好；与 scripts/benchmark/surface/cdp.mjs 同款思路）────
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

async function waitTarget(port, urlSubstr, timeoutMs = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const list = await httpJson(`http://127.0.0.1:${port}/json/list`);
      const t = list.find((x) => x.type === 'page' && (!urlSubstr || x.url.includes(urlSubstr)));
      if (t && t.webSocketDebuggerUrl) return t;
    } catch { /* 还没起来 */ }
    await sleep(200);
  }
  throw new Error('等待 CDP target 超时');
}

async function measureTheme(edge, serverPort, theme) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'memoria-ui-probe-'));
  const debugPort = 9400 + Math.floor(Math.random() * 400);
  const pageUrl = `http://127.0.0.1:${serverPort}/__fixture?theme=${theme}`;
  const args = [
    '--headless=new', `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
    '--disable-gpu', '--hide-scrollbars', '--window-size=1200,800', pageUrl,
  ];
  const child = spawn(edge, args, { stdio: 'ignore' });
  let cdp = null;
  try {
    const target = await waitTarget(debugPort, '/__fixture');
    cdp = await CDP.connect(target.webSocketDebuggerUrl);
    await cdp.send('Runtime.enable');
    await cdp.send('Page.enable');
    // 等 fonts / 样式生效
    for (let i = 0; i < 40; i++) {
      const r = await cdp.send('Runtime.evaluate', { expression: 'document.readyState', returnByValue: true });
      if (r.result && r.result.value === 'complete') break;
      await sleep(100);
    }
    await sleep(200);
    const expr = `(() => {
      const out = { theme: document.documentElement.getAttribute('data-theme') || 'dark', rows: [], vars: {} };
      const rootStyle = getComputedStyle(document.documentElement);
      for (const t of ['--border-subtle','--text-muted','--border-sep','--border','--text-primary','--theme-color','--accent']) {
        out.vars[t] = rootStyle.getPropertyValue(t).trim() || '(undefined)';
      }
      const subs = ${JSON.stringify(SUBJECTS)};
      for (const s of subs) {
        const el = document.getElementById(s.id);
        const cs = getComputedStyle(el);
        out.rows.push({
          id: s.id, token: s.token, expectedProp: s.expect,
          value: cs[s.expect],
          borderTopWidth: cs.borderTopWidth,
          color: cs.color,
          fontSize: cs.fontSize,
          control: !!s.control,
        });
      }
      const body = getComputedStyle(document.body);
      out.body = { color: body.color, background: body.backgroundColor };
      return out;
    })()`;
    const res = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true });
    const data = res.result.value;
    // 截图留档
    try {
      const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(path.join(HERE, `theme-probe-${theme}.png`), Buffer.from(shot.data, 'base64'));
    } catch { /* 截图失败不阻断测量 */ }
    return data;
  } finally {
    if (cdp) cdp.close();
    try { child.kill(); } catch { /* noop */ }
    await sleep(300);
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* noop */ }
  }
}

// ── 3. 判定 ────────────────────────────────────────────────────────────────
function hexToRgb(hex) {
  const h = hex.replace('#', '');
  if (h.length === 3) return [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16)];
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
const rgbEq = (a, b) => {
  const pa = String(a).match(/\d+/g); const pb = String(b).match(/\d+/g);
  return pa && pb && pa.slice(0, 3).join(',') === pb.slice(0, 3).join(',');
};

function judge(dark, light) {
  const verdict = [];
  for (const s of SUBJECTS) {
    const d = dark.rows.find((r) => r.id === s.id);
    const l = light.rows.find((r) => r.id === s.id);
    if (!d || !l) { verdict.push({ id: s.id, status: 'NO-SAMPLE' }); continue; }
    let status = 'OK';
    let why = '';
    if (s.control) {
      status = 'CONTROL';
      why = `对照：深色 ${s.expect}=${d.value} / 浅色 ${l.value}`;
    } else if (s.token === '--theme-color') {
      const dAccent = dark.vars['--accent']; const lAccent = light.vars['--accent'];
      const dTheme = dark.vars['--theme-color']; const lTheme = light.vars['--theme-color'];
      status = rgbEq(lTheme, lAccent) ? 'OK' : 'THEME-ALIAS-DRIFT';
      why = `深色 theme=${dTheme}/accent=${dAccent}；浅色 theme=${lTheme}/accent=${lAccent}`;
    } else {
      const dv = dark.vars[s.token];
      if (dv === '(undefined)') {
        // 深色下 token 未定义 ⇒ 看是不是落到了 currentColor / 继承色
        const inherited = rgbEq(d[ s.expect ], d.color) || (s.expect === 'color' && rgbEq(d.value, dark.body.color));
        if (inherited) {
          status = 'REAL-DEFECT';
          why = `深色 ${s.token} 未定义 ⇒ ${s.expect} 落到 ${d.value}（= 正文/继承色 ${d.color}），声明在 computed-value 阶段失效；浅色同元素 = ${l.value}（token 已定义）`;
        } else {
          status = 'REAL-DEFECT';
          why = `深色 ${s.token} 未定义 ⇒ ${s.expect}=${d.value}（非期望 token 值）；浅色 = ${l.value}`;
        }
      } else {
        status = 'OK';
        why = `深色 ${s.token}=${dv} ⇒ ${s.expect}=${d.value}；浅色=${l.value}`;
      }
    }
    verdict.push({ id: s.id, token: s.token, prop: s.prop, dark: d.value, light: l.value, status, why });
  }
  return {
    generated_at: new Date().toISOString(),
    source: 'node artifacts/agent/verify/ui/theme_probe.mjs',
    real_css: ['theme/memoria.css', 'theme/light.css', 'app/css/app.css', 'theme/mermaid.css'],
    vars: { dark: dark.vars, light: light.vars },
    body: { dark: dark.body, light: light.body },
    rows: { dark: dark.rows, light: light.rows },
    verdict,
  };
}

async function main() {
  const outIdx = process.argv.indexOf('--out');
  const outPath = outIdx > -1 ? process.argv[outIdx + 1] : path.join(HERE, 'theme-probe.json');
  const edge = findEdge();
  const { server, port } = await startServer();
  try {
    const dark = await measureTheme(edge, port, 'dark');
    const light = await measureTheme(edge, port, 'light');
    const result = judge(dark, light);
    fs.writeFileSync(outPath, JSON.stringify(result, null, 2) + '\n', 'utf8');
    console.log('== theme probe ==');
    console.log('token vars (dark):', JSON.stringify(dark.vars));
    console.log('token vars (light):', JSON.stringify(light.vars));
    for (const r of result.verdict) console.log(`  [${r.status}] ${r.id}  ${r.why}`);
    const bad = result.verdict.filter((r) => r.status === 'REAL-DEFECT' || r.status === 'THEME-ALIAS-DRIFT').length;
    console.log(`-- ${bad} 项缺口 / 共 ${result.verdict.length} 项 --`);
    console.log('JSON:', outPath);
  } finally {
    server.close();
  }
}

main().catch((e) => { console.error('FAIL:', e && e.stack || e); process.exit(1); });
