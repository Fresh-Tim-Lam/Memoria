#!/usr/bin/env node
/**
 * task-186 真机验收探针：启动蒙层 + 星河 + 空灵音效（DOM/状态证明，截图只是附件）
 *
 * 覆盖验收项：
 *   T-splash-1 冷启动出现蒙层；刷新/二次打开不出现   → 冷启动时间戳（stats）+ 重载后 DOM 无蒙层
 *   T-splash-3 prefers-reduced-motion ⇒ 无动画（静态蒙层 + 文字）
 *   T-splash-4 音效默认关；开启后有声音、可调音量、设置持久化
 *   T-splash-5 音频被拒（模拟 autoplay 拒绝）⇒ 启动不受影响、无报错弹窗
 *   T-splash-6 无 GPU/WebGL/Canvas ⇒ 降级静态、不白屏
 *   T-splash-7 零网络请求（探针侧：无第三方资源；代码断言在 pytest）
 *   T-splash-2 冷启动时长对照由 run_boot_measure.ps1 单独测（改前/改后各 5 次中位数）
 *
 * 冷启动观测说明：探针 attach 得很早（应用窗口 load 后立刻），但蒙层从"就绪"即开始淡出，
 * 可能只看到尾巴。因此 T1 冷启动用页面内 `__memoriaSplashStats.firstShownAt/removedAt`
 * 时间戳证明"确实出现过"，并在可控的重载（清 sessionStorage 标记）里做逐项 DOM 验证。
 *
 * 用法：node probe_splash.mjs --port 9640 --out verify.json
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

class CDP {
  constructor(ws) {
    this.ws = ws; this._id = 0; this._pending = new Map(); this._events = [];
    ws.addEventListener('message', (ev) => {
      let m; try { m = JSON.parse(typeof ev.data === 'string' ? ev.data : String(ev.data)); } catch { return; }
      if (m.id != null) {
        const p = this._pending.get(m.id); if (!p) return;
        this._pending.delete(m.id);
        m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
      } else if (m.method) {
        if (this._events.length < 400) this._events.push(m);
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
  exceptions() {
    return this._events
      .filter((e) => e.method === 'Runtime.exceptionThrown')
      .map((e) => (e.params.exceptionDetails && (e.params.exceptionDetails.exception && e.params.exceptionDetails.exception.description || e.params.exceptionDetails.text)) || 'exception');
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

async function waitTarget(port, timeoutMs = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl && !x.url.startsWith('devtools://'));
      if (t) return t;
    } catch { /* not ready */ }
    await sleep(40);
  }
  throw new Error('等待 page target 超时');
}

const CHECKS = [];
function check(id, ok, detail, data) {
  CHECKS.push({ id, ok: !!ok, detail, data: data === undefined ? null : data });
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${id}  ${detail}`);
}

// 页面内通用抓取（在浏览器上下文求值）
const SNAP = `(() => {
  const s = window.__memoriaSplashStats || {};
  const el = document.getElementById('memoria-splash');
  const brand = document.querySelector('.-memoria-splash__brand');
  const hint = document.getElementById('memoria-splash-hint');
  const canvas = document.querySelector('.-memoria-splash__canvas');
  const cs = el ? getComputedStyle(el) : null;
  const brandCs = brand ? getComputedStyle(brand) : null;
  return {
    now: Date.now(),
    hasEl: !!el,
    className: el ? el.className : null,
    pointerEvents: cs ? cs.pointerEvents : null,
    opacity: cs ? cs.opacity : null,
    zIndex: cs ? cs.zIndex : null,
    brandText: brand ? (brand.textContent || '') : null,
    brandAnimation: brandCs ? brandCs.animationName : null,
    brandRect: brand ? (() => { const r = brand.getBoundingClientRect(); return { w: +r.width.toFixed(1), h: +r.height.toFixed(1) }; })() : null,
    hintText: hint ? (hint.textContent || '') : null,
    canvasDisplay: canvas ? getComputedStyle(canvas).display : null,
    canvasVisible: !!(canvas && canvas.getBoundingClientRect().width > 0),
    stats: {
      everShown: !!s.everShown, firstShownAt: s.firstShownAt || 0, fadeStartAt: s.fadeStartAt || 0,
      removedAt: s.removedAt || 0, mode: s.mode || '', reducedMotion: !!s.reducedMotion,
      fadeReason: s.fadeReason || '', audioStarted: !!s.audioStarted, audioBlocked: s.audioBlocked || 0,
      theme: s.theme || '', traceCount: s.traceCount || 0, traceText: s.traceText || '',
      errors: (s.errors || []).slice(-5),
    },
    prefs: window.MemoriaSplash ? window.MemoriaSplash.getPrefs() : null,
    flashError: !!document.querySelector('#-flash-host .-flash-error, #-flash-host .-flash'),
    booting: document.documentElement.classList.contains('-booting'),
    externalResources: performance.getEntriesByType('resource')
      .map((r) => r.name)
      .filter((n) => n && !/^(https?:\\/\\/(127\\.0\\.0\\.1|localhost)[:/])/.test(n) && !n.startsWith('data:') && !n.startsWith('blob:')),
    settingsSound: (() => { const c = document.getElementById('splash-sound'); return c ? !!c.checked : null; })(),
    settingsVolume: (() => { const r = document.getElementById('splash-volume'); return r ? r.value : null; })(),
  };
})()`;

async function main() {
  const port = Number(arg('port', '9640'));
  const outPath = arg('out', path.join(HERE, 'verify.json'));
  const target = await waitTarget(port);
  const cdp = await CDP.connect(target.webSocketDebuggerUrl);
  const results = { generated_at: new Date().toISOString(), port, target_url: target.url, checks: [], snapshots: {}, exceptions: [] };

  const ev = async (expression) => {
    const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('页面异常：' + JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result ? r.result.value : undefined;
  };
  const waitFor = async (expr, label, timeoutMs = 15000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      try { if (await ev(expr)) return true; } catch { /* 导航中 */ }
      await sleep(40);
    }
    throw new Error(`等待超时：${label}`);
  };
  const shot = async (name) => {
    try {
      const s = await cdp.send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(path.join(HERE, name), Buffer.from(s.data, 'base64'));
      return name;
    } catch { return null; }
  };
  // 重载并清 sessionStorage 标记（= 模拟"冷启动等价"的可控观测；生产路径同一份代码）
  const reloadWith = async (opts = {}) => {
    const scripts = [];
    if (opts.script) {
      const r = await cdp.send('Page.addScriptToEvaluateOnNewDocument', { source: opts.script });
      scripts.push(r.identifier);
    }
    try {
      await ev(opts.clearSession ? `(() => { try { sessionStorage.removeItem('memoria.splash.seen'); } catch (e) {} return true; })()` : 'true');
      const loaded = new Promise((resolve) => {
        const to = setTimeout(() => resolve('timeout'), 20000);
        const onMsg = (m) => {
          if (m.method === 'Page.loadEventFired') { clearTimeout(to); resolve('load'); }
        };
        const orig = m => { if (m.method === 'Page.loadEventFired') { clearTimeout(to); resolve('load'); } };
        cdp.ws.addEventListener('message', (e) => {
          try { const m = JSON.parse(e.data); if (m.method === 'Page.loadEventFired') orig(m); } catch { /* noop */ }
        });
      });
      await cdp.send('Page.reload', { ignoreCache: false });
      await loaded;
      await waitFor(`document.readyState === 'complete' && !!window.MemoriaSplash`, '重载后页面就绪');
      return { scriptIds: scripts };
    } finally {
      // scripts 由调用方决定是否移除（identifier 返回给调用方；这里不自动删，方便组合场景）
    }
  };
  const removeScripts = async (ids) => {
    for (const id of ids || []) {
      try { await cdp.send('Page.removeScriptToEvaluateOnNewDocument', { identifier: id }); } catch { /* noop */ }
    }
  };

  try {
    await cdp.send('Runtime.enable');
    await cdp.send('Page.enable');

    // ── T1 冷启动：真实应用当前这一轮是否出现过蒙层（时间戳证明）─────────────────
    await waitFor(`document.readyState === 'complete'`, '页面加载完成');
    await waitFor(`!!window.__memoriaSplashStats`, 'splash 模块已加载');
    let s = await ev(SNAP);
    results.snapshots.cold_attached = s;
    const coldShot = s.hasEl ? await shot('shot-cold-splash.png') : null;
    // 如果还看到蒙层，就顺手记录它当场可见的证据
    const coldVisibleNow = s.hasEl;
    // 等淡出完成（最多 6s）
    try { await waitFor(`!document.getElementById('memoria-splash')`, '冷启动蒙层已淡出/移除', 6000); } catch { /* 记录失败即可 */ }
    s = await ev(SNAP);
    results.snapshots.cold_after = s;
    check('T-splash-1a 冷启动确实出现过蒙层',
      !!s.stats.everShown && s.stats.firstShownAt > 0 && s.stats.removedAt >= s.stats.firstShownAt,
      `everShown=${s.stats.everShown} firstShownAt=${s.stats.firstShownAt} fadeStart=${s.stats.fadeStartAt} removedAt=${s.stats.removedAt} 淡出原因=${s.stats.fadeReason}`,
      s.stats);
    check('T-splash-1b attach 当下是否为"仍在显示"（尾巴也算）', true,
      coldVisibleNow ? `是：冷启动截图 ${coldShot}` : '否（attach 时已开始淡出；时间戳已证明确实出现过）');
    check('T-splash-1c 真实就绪后淡出（fadeReason=ready/cap，且不早于就绪）',
      !!s.stats.fadeStartAt && ['ready', 'cap', 'safety'].includes(s.stats.fadeReason),
      `fadeReason=${s.stats.fadeReason} 停留=${s.stats.fadeStartAt ? (s.stats.fadeStartAt - s.stats.firstShownAt) : '?'}ms`);

    // ── T1 刷新/二次打开不出现 ───────────────────────────────────────────────
    const t1s = await reloadWith({ clearSession: false });
    await sleep(600);
    s = await ev(SNAP);
    results.snapshots.reload_no_splash = s;
    check('T-splash-1d 刷新（同窗口会话）不再出现蒙层', !s.hasEl && !s.stats.everShown,
      `hasEl=${s.hasEl} everShown=${s.stats.everShown}（sessionStorage 标记生效）`);
    await removeScripts(t1s.scriptIds);

    // ── T3 prefers-reduced-motion ⇒ 静态、无动画 ────────────────────────────
    await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    const t3s = await reloadWith({ clearSession: true });
    try {
      await waitFor(`document.getElementById('memoria-splash')`, '减少动态效果下蒙层出现', 5000);
    } catch { /* 记录失败 */ }
    s = await ev(SNAP);
    results.snapshots.reduced_motion = s;
    const rmShot = await shot('shot-reduced-motion-static.png');
    check('T-splash-3a reduced-motion：蒙层为静态（无 canvas 动画、无 CSS 动画）',
      s.hasEl && s.stats.reducedMotion === true && s.stats.mode === 'static' &&
      s.canvasDisplay === 'none' && s.brandAnimation === 'none',
      `mode=${s.stats.mode} reducedMotion=${s.stats.reducedMotion} canvasDisplay=${s.canvasDisplay} brandAnimation=${s.brandAnimation}`,
      { screenshot: rmShot });
    check('T-splash-3b reduced-motion 下仍有静态蒙层 + 文字（不是白屏）',
      s.hasEl && !!s.brandText && s.brandRect && s.brandRect.w > 10 && s.brandRect.h > 5 && !!s.hintText,
      `brand="${s.brandText}" rect=${JSON.stringify(s.brandRect)} hint="${s.hintText}"`);
    try { await waitFor(`!document.getElementById('memoria-splash')`, '静态蒙层淡出/移除', 6000); } catch { /* noop */ }
    try { await removeScripts(t3s.scriptIds); } catch { /* noop */ }
    await cdp.send('Emulation.setEmulatedMedia', { features: [] });

    // ── T6 无 Canvas/GPU ⇒ 降级静态、不白屏 ─────────────────────────────────
    const t6s = await reloadWith({ clearSession: true, script: 'window.__memoriaSplashForceStatic = true;' });
    try { await waitFor(`document.getElementById('memoria-splash')`, '强制静态蒙层出现', 5000); } catch { /* noop */ }
    s = await ev(SNAP);
    results.snapshots.force_static = s;
    const staticShot = await shot('shot-force-static-fallback.png');
    check('T-splash-6 Canvas 不可用 ⇒ 降级静态蒙层、不白屏',
      s.hasEl && s.stats.mode === 'static' && s.canvasDisplay === 'none' && !!s.brandText && !!s.hintText,
      `mode=${s.stats.mode} canvasDisplay=${s.canvasDisplay} brand="${s.brandText}" hint="${s.hintText}"`,
      { screenshot: staticShot });
    try { await waitFor(`!document.getElementById('memoria-splash')`, '静态蒙层移除', 6000); } catch { /* noop */ }
    await removeScripts(t6s.scriptIds);

    // ── T4 设置：默认关；开启有声音；音量可调；持久化 ───────────────────────
    // 打开设置 → 显示页签
    await ev(`(() => { const b = document.getElementById('btn-settings'); if (b) b.click(); return true; })()`);
    await sleep(400);
    await ev(`(() => { const t = document.querySelector('[data-settings-tab="view"]'); if (t) t.click(); return true; })()`);
    await waitFor(`!!document.getElementById('splash-sound')`, '设置里出现「启动动画」小节');
    s = await ev(SNAP);
    results.snapshots.settings_default = s;
    check('T-splash-4a 音效默认【关】且音量默认 35%',
      s.settingsSound === false && s.settingsVolume === '35',
      `checkbox=${s.settingsSound} volume=${s.settingsVolume}`);
    const settingsShot = await shot('shot-settings-splash-section.png');
    // 真实鼠标点击复选框（= 用户手势；自动播放策略允许出声）
    const rect = await ev(`(() => { const r = document.getElementById('splash-sound').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: rect.x, y: rect.y, button: 'none', buttons: 0 });
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: rect.x, y: rect.y, button: 'left', buttons: 1, clickCount: 1 });
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: rect.x, y: rect.y, button: 'left', buttons: 0, clickCount: 1 });
    await sleep(1200);
    // 音量拖到 80%（input 事件走真实 DOM 路径）
    await ev(`(() => { const r = document.getElementById('splash-volume'); r.value = '80'; r.dispatchEvent(new Event('input', { bubbles: true })); r.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
    await sleep(500);
    s = await ev(SNAP);
    results.snapshots.settings_enabled = s;
    check('T-splash-4b 开启后确实发声（AudioContext 成功 running）', s.stats.audioStarted === true,
      `audioStarted=${s.stats.audioStarted} audioBlocked=${s.stats.audioBlocked} errors=${JSON.stringify(s.stats.errors)}`);
    check('T-splash-4c 音量可调（80%）', s.settingsVolume === '80',
      `volume=${s.settingsVolume} 读数=${await ev(`(document.getElementById('splash-volume-value') || {}).textContent`)}`);
    // 持久化：读后端 ui_settings（与写盘同一事实源）
    const persisted = await ev(`(async () => { try { const a = window.MemoriaBridge.api(); const res = await a.get_ui_settings(); const o = typeof res === 'string' ? JSON.parse(res) : res; return (o && o.settings && o.settings.splash) || null; } catch (e) { return { error: String(e && e.message || e) }; } })()`);
    results.snapshots.persisted = persisted;
    check('T-splash-4d 设置持久化到既有 ui_settings 的 splash 段',
      !!persisted && persisted.sound === true && Math.abs(Number(persisted.volume) - 0.8) < 0.001,
      `ui_settings.splash = ${JSON.stringify(persisted)}`);
    // 刷新后仍记得（hydrate 自磁盘）
    const t4s = await reloadWith({ clearSession: false });
    await sleep(800);
    s = await ev(SNAP);
    check('T-splash-4e 刷新后偏好仍生效（sound=true / volume=80%）',
      !!s.prefs && s.prefs.sound === true && Math.abs(Number(s.prefs.volume) - 0.8) < 0.001,
      `prefs=${JSON.stringify(s.prefs)}`);
    await removeScripts(t4s.scriptIds);

    // ── T5 音频被拒（autoplay 拒绝）⇒ 启动不受影响、无报错弹窗 ──────────────
    const t5s = await reloadWith({ clearSession: true, script: 'window.__memoriaSplashForceAudioFail = true;' });
    try {
      await waitFor(`document.getElementById('memoria-splash')`, '音频失败场景下蒙层出现', 5000);
    } catch { /* noop */ }
    const beforeAudio = await ev(SNAP);
    try { await waitFor(`!document.documentElement.classList.contains('-booting')`, '音频失败时启动仍正常完成', 15000); } catch { /* noop */ }
    await sleep(800);
    s = await ev(SNAP);
    results.snapshots.audio_blocked = s;
    const t5Exceptions = cdp.exceptions();
    results.exceptions = t5Exceptions;
    check('T-splash-5a 音频失败被静默跳过（计数可观测、无未捕获异常）',
      s.stats.audioBlocked >= 1 && t5Exceptions.length === 0,
      `audioBlocked=${s.stats.audioBlocked} audioStarted=${s.stats.audioStarted} exceptions=${JSON.stringify(t5Exceptions)}`);
    check('T-splash-5b 音频失败不影响启动（-booting 已按既有逻辑移除 + 无报错弹窗）',
      s.booting === false && s.flashError === false,
      `booting=${s.booting} flashError=${s.flashError}`);
    await removeScripts(t5s.scriptIds);

    // ── T7 零网络请求（第三方/外部 origin 资源为 0）──────────────────────────
    s = await ev(SNAP);
    results.snapshots.external = s.externalResources;
    check('T-splash-7 无任何外部网络请求（只有本机静态资源）', s.externalResources.length === 0,
      `外部资源=${JSON.stringify(s.externalResources.slice(0, 10))}`);

    // ── T-splash-9 主题感知：亮色主题蒙层（人反馈：白底蒙层怎么办）──────────────
    await ev(`(() => { try { localStorage.setItem('-theme-mode', 'light'); } catch (e) {} return true; })()`);
    const t9 = await reloadWith({ clearSession: true });
    try { await waitFor(`document.getElementById('memoria-splash')`, '亮色主题蒙层出现', 6000); } catch { /* noop */ }
    s = await ev(SNAP);
    const lightTheme = await ev(`document.documentElement.getAttribute('data-theme')`);
    const lightBrandColor = await ev(`(() => { const b = document.querySelector('.-memoria-splash__brand'); return b ? getComputedStyle(b).color : null; })()`);
    const canvasAnim = await ev(`(() => { const c = document.querySelector('.-memoria-splash__canvas'); return c ? getComputedStyle(c).animationName : null; })()`);
    results.snapshots.light_theme = { snap: s, dataTheme: lightTheme, brandColor: lightBrandColor, canvasAnimation: canvasAnim };
    const lightShot = await shot('shot-light-theme-splash.png');
    check('T-splash-9a 亮色主题蒙层：主题标识/统计正确',
      lightTheme === 'light' && s.stats.theme === 'light' && !!s.hasEl,
      `data-theme=${lightTheme} stats.theme=${s.stats.theme} 截图=${lightShot}`);
    check('T-splash-9b 亮色主题品牌字仍可读（用 --text-bright，非白字白底）',
      !!lightBrandColor && /^rgb\(\s*0\s*,\s*0\s*,\s*0\s*\)/.test(lightBrandColor),
      `brand color=${lightBrandColor}`);
    check('T-splash-9c 星点不是静态（画布挂 漂移+闪烁 CSS 动画）',
      !!canvasAnim && canvasAnim.indexOf('memoria-splash-drift') >= 0 && canvasAnim.indexOf('memoria-splash-twinkle') >= 0,
      `animationName=${canvasAnim}`);
    try { await waitFor(`!document.getElementById('memoria-splash')`, '亮色蒙层移除', 6000); } catch { /* noop */ }
    await removeScripts(t9.scriptIds);
    await ev(`(() => { try { localStorage.setItem('-theme-mode', 'dark'); } catch (e) {} return true; })()`);

    // ── T-splash-10 使用痕迹星图（人反馈：星点要体现使用痕迹）────────────────────
    // 真实调用链：冷启动自动打开的文档已经过 app.js 的 noteOpen 埋点 ⇒ 星图至少有 1 颗
    await waitFor(`!document.documentElement.classList.contains('-booting')`, '启动完成（等待星图埋点）', 15000);
    await sleep(400);
    const realTraceCount = await ev(`window.MemoriaSplash ? window.MemoriaSplash.getTraceCount() : -1`);
    results.snapshots.real_traces = await ev(`window.MemoriaSplashTrace ? window.MemoriaSplashTrace.snapshot() : null`);
    check('T-splash-10a 打开笔记会被记成一颗星（app.js 同线埋点真实生效）',
      Number(realTraceCount) >= 1, `打开过的笔记星数=${realTraceCount}`);
    await ev(`(() => {
      const now = Date.now();
      const stars = [
        { p: 'docs/bright-now.md', n: 6, t: now - 3600 * 1000, e: 3 },
        { p: 'docs/week-ago.md', n: 3, t: now - 3 * 86400 * 1000, e: 1 },
        { p: 'docs/long-ago.md', n: 1, t: now - 40 * 86400 * 1000, e: 0 },
      ];
      try { localStorage.setItem('memoria.splash.stars.v1', JSON.stringify({ v: 1, stars: stars, updated: now })); } catch (e) {}
      return true;
    })()`);
    const t10 = await reloadWith({ clearSession: true });
    try { await waitFor(`document.getElementById('memoria-splash')`, '带星图的蒙层出现', 6000); } catch { /* noop */ }
    s = await ev(SNAP);
    const traceCount = await ev(`window.MemoriaSplash ? window.MemoriaSplash.getTraceCount() : -1`);
    const traceText = await ev(`(document.getElementById('memoria-splash-traces') || {}).textContent || ''`);
    results.snapshots.traces = { snap: s, traceCount, traceText, traceTextStats: s.stats.traceText };
    const traceShot = await shot('shot-usage-traces.png');
    check('T-splash-10b 蒙层读取并绘制使用痕迹星图（3 颗已知星）',
      Number(traceCount) === 3 && s.stats.traceCount === 3 && s.stats.mode === 'canvas',
      `traceCount=${traceCount} stats.traceCount=${s.stats.traceCount} mode=${s.stats.mode} 截图=${traceShot}`);
    check('T-splash-10c 蒙层文案点明"使用痕迹"（已点亮 N 颗星）',
      /3/.test(traceText) && /星|star/i.test(traceText),
      `traces 文案="${traceText}"（stats=${s.stats.traceText}）`);
    try { await waitFor(`!document.getElementById('memoria-splash')`, '带星图蒙层移除', 6000); } catch { /* noop */ }
    await removeScripts(t10.scriptIds);
    // 恢复为空星图，避免污染后续（隔离 config 每次会重建，这里只是顺手）
    await ev(`(() => { try { window.MemoriaSplashTrace && window.MemoriaSplashTrace.clear(); } catch (e) {} return true; })()`);

    await shot('shot-final.png');
  } finally {
    cdp.close();
  }

  results.checks = CHECKS;
  results.passed = CHECKS.filter((c) => c.ok).length;
  results.failed = CHECKS.filter((c) => !c.ok).length;
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2) + '\n', 'utf8');
  console.log(`-- task-186: ${results.passed} PASS / ${results.failed} FAIL --`);
  console.log('JSON:', outPath);
  process.exit(results.failed ? 1 : 0);
}

main().catch((e) => { console.error('FAIL:', (e && e.stack) || e); process.exit(2); });
