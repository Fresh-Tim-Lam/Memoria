// task-133 真机验证驱动：CDP attach 到**真实 Memoria 应用**（pywebview + WebView2），
// 用页面内 DOM 读出三份证据 + 截图；不依赖无头 harness。
//
// 用法：node drive.mjs --port 9577 --out <work>
// 输出：<out>/dom-pre.json / dom-post.json / dom-reload.json、pre.png / post.png / reload.png、
//       driver-result.json（含 gpu 真机凭证、时间线、每一步的 DOM 快照）
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const argOf = (name, def) => {
  const i = args.indexOf("--" + name);
  return i >= 0 ? args[i + 1] : def;
};
const PORT = Number(argOf("port", 9577));
const OUT = argOf("out", ".");
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function targets() {
  const res = await fetch(`http://127.0.0.1:${PORT}/json/list`);
  return res.json();
}

async function connect() {
  // 过滤 devtools:// 与 about:blank（真机里 DevTools 自身也会是一个 target）
  let target = null;
  for (let i = 0; i < 120 && !target; i += 1) {
    try {
      const list = await targets();
      target = list.find(
        (t) => t.type === "page" && !String(t.url).startsWith("devtools://") && String(t.url).startsWith("http://127.0.0.1")
      );
    } catch (_e) {
      /* CDP 未起 */
    }
    if (!target) await sleep(500);
  }
  if (!target) throw new Error("等不到可 attach 的真实页面 target");

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = (e) => reject(new Error("ws error: " + (e && e.message)));
  });
  let nextId = 0;
  const pending = new Map();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(JSON.stringify(msg.error)));
      else resolve(msg.result);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = ++nextId;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  return { target, ws, send };
}

async function main() {
  const t0 = Date.now();
  const { target, send } = await connect();
  await send("Runtime.enable");
  await send("Page.enable");

  const evaluate = async (expression, awaitPromise = true) => {
    const r = await send("Runtime.evaluate", {
      expression,
      awaitPromise,
      returnByValue: true,
      userGesture: true,
    });
    if (r && r.exceptionDetails) throw new Error("page eval failed: " + JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r && r.result ? r.result.value : undefined;
  };

  const debugExpr = `(async () => {
    const out = {
      title: document.title,
      readyState: document.readyState,
      hasApp: !!window.MemoriaApp,
      hasPanel: !!window.MemoriaAgentPanel,
      hasBridge: !!(window.MemoriaBridge && window.MemoriaBridge.api),
      kbPath: (window.MemoriaApp && window.MemoriaApp.state && window.MemoriaApp.state.kbPath) || '',
      btnAgent: !!document.querySelector('#btn-agent'),
      dock: (() => { const d = document.querySelector('#-agent-dock'); return d ? { cls: d.className, w: Math.round(d.getBoundingClientRect().width) } : null; })(),
      statusText: (document.querySelector('#status-agent') || {}).textContent || '',
      rows: document.querySelectorAll('#agent-messages .-agent-msg').length,
      settingKeys: null, agentCfg: null, loadRpc: null,
    };
    try {
      const api = window.MemoriaBridge.api();
      const s = await api.get_ui_settings();
      out.settingKeys = s && s.settings ? Object.keys(s.settings) : null;
      out.settingAgent = s && s.settings ? s.settings.agent : null;
      const c = await api.agent_get_config();
      out.agentCfg = c ? { status: c.status, enabled: c.enabled, base_url: c.base_url, model: c.model, has_key: c.has_key } : null;
      const kb = out.kbPath || null;
      const r = await api.agent_session_load('session-t133-realmachine', kb);
      out.loadRpc = r ? { status: r.status, rows: (r.messages || []).length, keys: Object.keys(r), ctx: r.context_usage || null } : null;
    } catch (e) { out.err = String((e && e.message) || e); }
    return out;
  })()`;

  const waitFor = async (label, expression, timeoutMs = 60000, intervalMs = 400) => {
    const deadline = Date.now() + timeoutMs;
    let last;
    while (Date.now() < deadline) {
      try {
        last = await evaluate(expression, true);
        if (last) return last;
      } catch (e) {
        last = String(e);
      }
      await sleep(intervalMs);
    }
    try {
      const dbg = await evaluate(debugExpr, true);
      writeFileSync(join(OUT, "dom-debug.json"), JSON.stringify({ label, last, debug: dbg }, null, 2), "utf8");
    } catch (_e) {}
    throw new Error(`等待超时[${label}] last=${JSON.stringify(last).slice(0, 400)}`);
  };

  const snapExpr = `(() => {
    const status = document.querySelector('#status-agent');
    const rows = Array.from(document.querySelectorAll('#agent-messages .-agent-msg'));
    const sys = Array.from(document.querySelectorAll('#agent-messages .-agent-msg--system'));
    const dock = document.querySelector('#-agent-dock');
    return {
      statusText: status ? status.textContent : '',
      statusTitle: status ? status.title : '',
      statusColorInline: status ? (status.style.color || '') : '',
      statusComputedColor: status ? getComputedStyle(status).color : '',
      rows: rows.length,
      systemRows: sys.length,
      systemTexts: sys.map((e) => e.textContent),
      tailRows: rows.slice(-3).map((e) => (e.textContent || '').slice(0, 120)),
      dockClass: dock ? dock.className : '',
      dockWidthPx: dock ? Math.round(dock.getBoundingClientRect().width) : 0,
      kbPath: (window.MemoriaApp && window.MemoriaApp.state && window.MemoriaApp.state.kbPath) || '',
      currentSession: (document.querySelector('#agent-history-current') || {}).textContent || '',
      viewport: { w: window.innerWidth, h: window.innerHeight },
      title: document.title,
    };
  })()`;

  const screenshot = async (name) => {
    const shot = await send("Page.captureScreenshot", { format: "png", fromSurface: true });
    writeFileSync(join(OUT, name), Buffer.from(shot.data, "base64"));
  };

  // 元素级放大截图（证据要能看清字）：给 clip 一个安全边界，scale=2
  const clipExpr = (selector) => `(() => {
    const e = document.querySelector(${JSON.stringify(selector)});
    if (!e) return null;
    const r = e.getBoundingClientRect();
    const x = Math.max(0, Math.floor(r.left) - 6);
    const y = Math.max(0, Math.floor(r.top) - 6);
    const width = Math.max(10, Math.min(window.innerWidth - x, Math.ceil(r.width) + 12));
    const height = Math.max(10, Math.min(window.innerHeight - y, Math.ceil(r.height) + 12));
    return { x, y, width, height };
  })()`;
  const clipShot = async (name, selector) => {
    const rect = await evaluate(clipExpr(selector));
    if (!rect) return null;
    const shot = await send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      clip: { x: rect.x, y: rect.y, width: rect.width, height: rect.height, scale: 2 },
    });
    writeFileSync(join(OUT, name), Buffer.from(shot.data, "base64"));
    return rect;
  };

  const result = { target: { id: target.id, title: target.title, url: target.url }, steps: [], startedAt: new Date().toISOString() };

  // ① 应用就绪 + 真机凭证（GPU 非软光栅）
  await waitFor(
    "app-ready",
    `document.readyState === 'complete' && !!window.MemoriaApp && !!window.MemoriaAgentPanel && !!document.querySelector('#agent-messages')`,
    90000
  );
  const gpu = await evaluate(`(() => {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    let renderer = '';
    try {
      const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
      renderer = gl ? String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : '';
    } catch (_e) {}
    return { webgl: !!gl, renderer: renderer, hardwareConcurrency: navigator.hardwareConcurrency };
  })()`);
  result.gpu = gpu;

  // ② 打开对话 dock（若折叠/自动隐藏），并等"上次会话"自动载入
  const dockState = () =>
    evaluate(`(() => {
      const d = document.querySelector('#-agent-dock');
      return d ? { cls: d.className, w: Math.round(d.getBoundingClientRect().width) } : null;
    })()`);
  let dock = await dockState();
  if (!dock || dock.w < 40) {
    await evaluate(`(() => { const b = document.querySelector('#btn-agent'); if (b) b.click(); return true; })()`);
    await sleep(1200);
  }
  // 再显式走一次公开入口：非折叠分支会 refreshConfig + refreshHistory → restoreLastSession
  await evaluate(`(() => { try { window.MemoriaAgentPanel.open(); return true; } catch (e) { return String(e); } })()`);
  await sleep(2500);
  // 兜底（真机健壮性）：若"上次会话"没被自动认领（Windows 8.3 短路径/长路径键不一致），
  // 用产品自己的公开 RPC 写一次同形状的 prefs，再走 onKbChanged（app.js 正常路径也是它）触发恢复。
  const restored = await evaluate(`(() => {
    const s = document.querySelector('#status-agent');
    return !!s && (s.textContent || '').includes('压缩预算');
  })()`);
  if (!restored) {
    const injected = await evaluate(`(async () => {
      const api = window.MemoriaBridge.api();
      const st = await api.get_ui_settings();
      const agent = (st && st.settings && st.settings.agent) || {};
      const kb = (window.MemoriaApp && window.MemoriaApp.state && window.MemoriaApp.state.kbPath) || '';
      const key = String(kb).replace(/\\//g, '\\\\').replace(/\\\\+$/, '').toLowerCase();
      const map = Object.assign({}, agent.lastSessionByKb || {}, { [key]: 'session-t133-realmachine' });
      await api.save_ui_settings({ agent: null });
      await api.save_ui_settings({ agent: { lastSessionByKb: map } });
      try { window.MemoriaAgentPanel.onKbChanged(); } catch (e) { return { key, err: String(e) }; }
      return { key: key, map: map };
    })()`);
    writeFileSync(join(OUT, "dom-prefs-injected.json"), JSON.stringify(injected, null, 2), "utf8");
    await sleep(2500);
  }
  await waitFor(
    "session-restored",
    `(() => {
      const s = document.querySelector('#status-agent');
      const rows = document.querySelectorAll('#agent-messages .-agent-msg');
      return !!s && (s.textContent || '').includes('压缩预算') && rows.length >= 10;
    })()`,
    90000
  );

  const pre = await evaluate(snapExpr);
  writeFileSync(join(OUT, "dom-pre.json"), JSON.stringify(pre, null, 2), "utf8");
  await screenshot("pre.png");
  await clipShot("status-pre.png", "#status-bar");
  result.steps.push({ name: "pre", atMs: Date.now() - t0, dom: pre });

  // ③ 发一条消息 ⇒ 后端在追加本轮前应触发一次**真实压缩**（历史 31500 字符 > 25600 阈值）
  await evaluate(`(() => {
    const i = document.querySelector('#agent-input');
    i.value = '真机验证：压缩之后请继续回答。';
    i.dispatchEvent(new Event('input', { bubbles: true }));
    const b = document.querySelector('#agent-send');
    if (b) b.click();
    return true;
  })()`);

  await waitFor(
    "compaction-turn-done",
    `(() => {
      const s = document.querySelector('#status-agent');
      const rows = document.querySelectorAll('#agent-messages .-agent-msg');
      const send = document.querySelector('#agent-send');
      const text = s ? (s.textContent || '') : '';
      return text.includes('已压缩') && rows.length >= ${pre.rows + 2} && send && !send.disabled;
    })()`,
    180000
  );
  await sleep(800); // 等预算刷新（轮末顺带 RPC）落定
  const post = await evaluate(snapExpr);
  writeFileSync(join(OUT, "dom-post.json"), JSON.stringify(post, null, 2), "utf8");
  await screenshot("post.png");
  await clipShot("status-post.png", "#status-bar");
  result.steps.push({ name: "post", atMs: Date.now() - t0, dom: post });

  // ④ 重载页面（等价于"关掉再打开会话"）⇒ 系统行必须仍在（可回放投影，非内存态）
  await send("Page.reload", { ignoreCache: false });
  await waitFor(
    "reload-ready",
    `document.readyState === 'complete' && !!window.MemoriaAgentPanel && !!document.querySelector('#agent-messages')`,
    90000
  );
  // 重载后 dock 可能又折叠 ⇒ 再打开一次（用户正常操作也会这么做）
  const dock2 = await dockState();
  if (!dock2 || dock2.w < 40) {
    await evaluate(`(() => { const b = document.querySelector('#btn-agent'); if (b) b.click(); return true; })()`);
  }
  await waitFor(
    "reload-system-row",
    `(() => {
      const s = document.querySelector('#status-agent');
      const sys = document.querySelectorAll('#agent-messages .-agent-msg--system');
      return sys.length >= 1 && !!s && (s.textContent || '').includes('压缩预算');
    })()`,
    90000
  );
  await sleep(800);
  const reload = await evaluate(snapExpr);
  writeFileSync(join(OUT, "dom-reload.json"), JSON.stringify(reload, null, 2), "utf8");
  await screenshot("reload.png");
  await clipShot("status-reload.png", "#status-bar");
  // 把系统行滚到视口中央再单独放大截图（证据：可回放投影，不是内存态）
  await evaluate(`(() => {
    const row = document.querySelector('#agent-messages .-agent-msg--system');
    if (row && row.scrollIntoView) row.scrollIntoView({ block: 'center' });
    return !!row;
  })()`);
  await sleep(500);
  const sysRect = await clipShot("system-row-reload.png", "#agent-messages .-agent-msg--system");
  result.systemRowClip = sysRect;
  result.steps.push({ name: "reload", atMs: Date.now() - t0, dom: reload });

  result.finishedAt = new Date().toISOString();
  result.durationMs = Date.now() - t0;
  writeFileSync(join(OUT, "driver-result.json"), JSON.stringify(result, null, 2), "utf8");
  console.log(JSON.stringify({ ok: true, gpu: gpu.renderer, durationMs: result.durationMs }));
  process.exit(0);
}

main().catch((e) => {
  console.error("DRIVER_FAIL:", e && e.stack ? e.stack : e);
  try {
    writeFileSync(join(OUT, "driver-fail.json"), JSON.stringify({ error: String(e) }, null, 2), "utf8");
  } catch (_e) {}
  process.exit(2);
});
