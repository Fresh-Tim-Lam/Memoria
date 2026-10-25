// task-134 真机验证驱动：CDP attach 到真实 Memoria 应用，模拟"拖入 .txt 文档资源"链路。
// phase=before：记录修复前的用户可见故障（"只支持图片"提示、无 chip、后端无文件）。
// phase=after ：验证修复后 ①–⑥ 全链路（不报错 / RPC 落盘 / chip / 提示注入 / 发送后清空 / 移除按钮）。
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const argOf = (n, d) => {
  const i = args.indexOf("--" + n);
  return i >= 0 ? args[i + 1] : d;
};
const PORT = Number(argOf("port", 9587));
const OUT = argOf("out", ".");
const PHASE = argOf("phase", "before");
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connect() {
  let target = null;
  for (let i = 0; i < 160 && !target; i += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      target = list.find((t) => t.type === "page" && !String(t.url).startsWith("devtools://") && String(t.url).startsWith("http://127.0.0.1"));
    } catch (_e) {}
    if (!target) await sleep(500);
  }
  if (!target) throw new Error("等不到可 attach 的真实页面 target");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = (e) => rej(new Error("ws error"));
  });
  let id = 0;
  const pending = new Map();
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const mid = ++id;
      pending.set(mid, { resolve, reject });
      ws.send(JSON.stringify({ id: mid, method, params }));
    });
  return { target, send };
}

async function main() {
  const t0 = Date.now();
  const { target, send } = await connect();
  await send("Runtime.enable");
  await send("Page.enable");
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, userGesture: true });
    if (r && r.exceptionDetails) throw new Error("eval failed: " + JSON.stringify(r.exceptionDetails).slice(0, 300));
    return r && r.result ? r.result.value : undefined;
  };
  const waitFor = async (label, expr, timeoutMs = 60000, intervalMs = 350) => {
    const deadline = Date.now() + timeoutMs;
    let last;
    while (Date.now() < deadline) {
      try {
        last = await evaluate(expr);
        if (last) return last;
      } catch (e) {
        last = String(e);
      }
      await sleep(intervalMs);
    }
    throw new Error(`等待超时[${label}] last=${JSON.stringify(last).slice(0, 300)}`);
  };
  const shot = async (name) => {
    const s = await send("Page.captureScreenshot", { format: "png", fromSurface: true });
    writeFileSync(join(OUT, name), Buffer.from(s.data, "base64"));
  };
  const clipShot = async (name, selector) => {
    const rect = await evaluate(`(() => {
      const e = document.querySelector(${JSON.stringify(selector)});
      if (!e) return null;
      const r = e.getBoundingClientRect();
      const x = Math.max(0, Math.floor(r.left) - 6);
      const y = Math.max(0, Math.floor(r.top) - 6);
      return { x, y, width: Math.max(10, Math.min(window.innerWidth - x, Math.ceil(r.width) + 12)), height: Math.max(10, Math.min(window.innerHeight - y, Math.ceil(r.height) + 12)) };
    })()`);
    if (!rect) return null;
    const s = await send("Page.captureScreenshot", { format: "png", fromSurface: true, clip: { ...rect, scale: 2 } });
    writeFileSync(join(OUT, name), Buffer.from(s.data, "base64"));
    return rect;
  };

  const snapExpr = `(() => {
    const strip = document.querySelector('#agent-attachments');
    const chips = strip ? Array.from(strip.querySelectorAll('.-agent-attach-chip')) : [];
    const resChips = strip ? Array.from(strip.querySelectorAll('.-agent-resource-chip')) : [];
    const status = document.querySelector('#status-agent');
    const flash = document.querySelector('#-flash-host');
    const dock = document.querySelector('#-agent-dock');
    return {
      stripHidden: strip ? strip.hidden : null,
      chips: chips.length,
      resChips: resChips.length,
      chipTexts: resChips.map((e) => e.textContent),
      chipTitles: resChips.map((e) => e.title),
      statusText: status ? status.textContent : '',
      flashText: flash ? flash.textContent : '',
      rows: document.querySelectorAll('#agent-messages .-agent-msg').length,
      sendDisabled: !!(document.querySelector('#agent-send') || {}).disabled,
      dockWidth: dock ? Math.round(dock.getBoundingClientRect().width) : 0,
    };
  })()`;

  const dragTxt = (name) =>
    evaluate(`(() => {
      const dt = new DataTransfer();
      dt.items.add(new File(["task-134 resource: hello from txt\\n"], ${JSON.stringify(name)}, { type: "text/plain" }));
      const dock = document.querySelector('#-agent-dock');
      if (!dock) return 'no-dock';
      dock.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
      dock.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
      return 'dropped';
    })()`);

  const result = { phase: PHASE, target: { id: target.id, title: target.title, url: target.url }, steps: [], startedAt: new Date().toISOString() };

  await waitFor("app-ready", `document.readyState === 'complete' && !!window.MemoriaAgentPanel && !!document.querySelector('#agent-input')`, 120000);
  const gpu = await evaluate(`(() => { const c = document.createElement('canvas'); const gl = c.getContext('webgl'); return { webgl: !!gl, renderer: gl ? String(gl.getParameter(gl.RENDERER)) : '' }; })()`);
  result.gpu = gpu;

  // 打开对话 dock
  const dockW = await evaluate(`(() => { const d = document.querySelector('#-agent-dock'); return d ? Math.round(d.getBoundingClientRect().width) : 0; })()`);
  if (!dockW || dockW < 40) {
    await evaluate(`(() => { const b = document.querySelector('#btn-agent'); if (b) b.click(); return true; })()`);
    await sleep(1200);
    await evaluate(`(() => { try { window.MemoriaAgentPanel.open(); } catch (e) {} return true; })()`);
    await sleep(1200);
  }
  await waitFor("dock-open", `(() => { const d = document.querySelector('#-agent-dock'); return !!d && d.getBoundingClientRect().width > 40 && !!document.querySelector('#agent-attachments'); })()`, 30000);
  await shot(`pre-${PHASE}.png`);

  // ① 拖入 .txt
  const dragRes = await dragTxt("task134-note.txt");
  await sleep(3500); // 等 RPC（drag → uploadResource → agent_attach_resource）落定
  const dropState = await evaluate(snapExpr);
  writeFileSync(join(OUT, `dom-drop-${PHASE}.json`), JSON.stringify(dropState, null, 2), "utf8");
  await shot(`drop-${PHASE}.png`);
  await clipShot(`strip-${PHASE}.png`, "#agent-attachments");
  await clipShot(`status-${PHASE}.png`, "#status-bar");
  result.steps.push({ name: "drop", dragRes, dom: dropState });

  if (dropState.resChips >= 1) {
    // ⑥ 移除按钮
    await evaluate(`(() => {
      const b = document.querySelector('#agent-attachments .-agent-resource-chip .-agent-attach-remove[data-res-idx]');
      if (b) b.click();
      return !!b;
    })()`);
    await sleep(1500);
    const removedState = await evaluate(snapExpr);
    writeFileSync(join(OUT, `dom-removed-${PHASE}.json`), JSON.stringify(removedState, null, 2), "utf8");
    await shot(`removed-${PHASE}.png`);
    result.steps.push({ name: "remove", dom: removedState });

    // 再拖一次 → 发送（④/⑤）
    await dragTxt("task134-note-2.txt");
    await waitFor("chip-again", `(() => document.querySelectorAll('#agent-attachments .-agent-resource-chip').length >= 1)()`, 30000);
    // 上传期间 send 被禁用（uploadResource 开始就 disabled）；必须等上传完成后才能点发送
    await waitFor("send-enabled", `(() => { const s = document.querySelector('#agent-send'); const chips = document.querySelectorAll('#agent-attachments .-agent-resource-chip').length; return chips >= 1 && !!s && !s.disabled; })()`, 60000);
    // 诊断：捕获 click 是否真的到达按钮（不改产品代码，只加捕获监听）
    await evaluate(`(() => {
      window.__t134 = { clicked: 0, captured: 0 };
      document.addEventListener('click', (e) => { window.__t134.captured += 1; }, true);
      const b = document.querySelector('#agent-send');
      if (b) b.addEventListener('click', () => { window.__t134.clicked += 1; }, { capture: true, once: false });
      return true;
    })()`);
    await evaluate(`(() => {
      const i = document.querySelector('#agent-input');
      i.value = 'task-134 真机验证：这份 txt 资源你收到了吗？';
      i.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('#agent-send').click();
      return true;
    })()`);
    await sleep(1200);
    const clickDbg = await evaluate(`(() => {
      const i = document.querySelector('#agent-input');
      return {
        probe: window.__t134 || null,
        inputValue: i ? i.value : null,
        rows: document.querySelectorAll('#agent-messages .-agent-msg').length,
        statusText: (document.querySelector('#status-agent') || {}).textContent || '',
        flashText: (document.querySelector('#-flash-host') || {}).textContent || '',
      };
    })()`);
    writeFileSync(join(OUT, `dom-click-debug-${PHASE}.json`), JSON.stringify(clickDbg, null, 2), "utf8");
    // 发送后轮询：正常应很快出现 user+assistant 气泡；若卡住则把实时 DOM 写下来诊断
    let sendDebug = [];
    try {
      await waitFor("turn-done", `(() => { const rows = document.querySelectorAll('#agent-messages .-agent-msg').length; const s = document.querySelector('#agent-send'); return rows >= 2 && s && !s.disabled; })()`, 180000);
    } catch (e) {
      for (let k = 0; k < 6; k += 1) {
        sendDebug.push(await evaluate(snapExpr));
        await sleep(500);
      }
      writeFileSync(join(OUT, `dom-send-debug-${PHASE}.json`), JSON.stringify(sendDebug, null, 2), "utf8");
      throw e;
    }
    await sleep(1200);
    const sentState = await evaluate(snapExpr);
    writeFileSync(join(OUT, `dom-sent-${PHASE}.json`), JSON.stringify(sentState, null, 2), "utf8");
    await shot(`sent-${PHASE}.png`);
    await clipShot(`strip-sent-${PHASE}.png`, "#agent-attachments");
    result.steps.push({ name: "send", dom: sentState });
  } else {
    result.steps.push({ name: "send", skipped: "无资源 chip（修复前预期）" });
  }

  result.finishedAt = new Date().toISOString();
  result.durationMs = Date.now() - t0;
  writeFileSync(join(OUT, `driver-${PHASE}.json`), JSON.stringify(result, null, 2), "utf8");
  console.log(JSON.stringify({ ok: true, phase: PHASE, durationMs: result.durationMs, drop: dropState }));
  process.exit(0);
}

main().catch((e) => {
  console.error("DRIVER_FAIL:", e && e.stack ? e.stack : e);
  try {
    writeFileSync(join(OUT, `driver-${PHASE}-fail.json`), JSON.stringify({ error: String(e) }, null, 2), "utf8");
  } catch (_e) {}
  process.exit(2);
});
