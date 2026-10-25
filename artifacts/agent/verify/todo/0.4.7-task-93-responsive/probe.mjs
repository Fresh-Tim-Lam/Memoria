// task-93 真机探针：CDP 执行 eval / captureScreenshot（批量，零依赖 WebSocket）。
// 用法：node probe.mjs --port 9579 --cmd <cmd.json>
// cmd.json: { "cmds": [ {"action":"eval","expr":"..."} | {"action":"shot","path":"a.png","clipSelector":"#content"} ] }
import { readFileSync, writeFileSync } from "node:fs";

const args = process.argv.slice(2);
const argOf = (n, d) => { const i = args.indexOf("--" + n); return i >= 0 ? args[i + 1] : d; };
const PORT = Number(argOf("port", 9579));
const CMD = argOf("cmd");
const spec = JSON.parse(readFileSync(CMD, "utf8"));

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const target = list.find((t) => t.type === "page" && !String(t.url).startsWith("devtools://") && String(t.url).startsWith("http://127.0.0.1"));
if (!target) { console.log(JSON.stringify({ error: "no target" })); process.exit(0); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("ws error")); });
let id = 0;
const pending = new Map();
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id);
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const i = ++id; pending.set(i, { resolve, reject }); ws.send(JSON.stringify({ id: i, method, params }));
});
await send("Runtime.enable");
await send("Page.enable");

if ((spec.cmds || []).some((c) => c.action === "listen")) {
  const events = [];
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.method === "Runtime.exceptionThrown") {
      const d = m.params.exceptionDetails || {};
      events.push({ kind: "exception", text: (d.exception && (d.exception.description || d.exception.value)) || d.text, url: d.url, line: d.lineNumber });
    } else if (m.method === "Runtime.consoleAPICalled") {
      const p = m.params;
      if (p.type === "error" || p.type === "warning") {
        events.push({ kind: "console-" + p.type, text: (p.args || []).map((a) => a.value || a.description || "").join(" ").slice(0, 500) });
      }
    } else if (m.method === "Log.entryAdded") {
      const e = m.params.entry || {};
      if (e.level === "error") events.push({ kind: "log-error", text: String(e.text || "").slice(0, 500) });
    }
  });
  await send("Log.enable");
  await send("Page.reload", { ignoreCache: true });
  await new Promise((r) => setTimeout(r, 9000));
  console.log(JSON.stringify({ ok: true, results: [{ action: "listen", events }] }));
  process.exit(0);
}

const out = [];
for (const c of spec.cmds || []) {
  if (c.action === "eval") {
    const r = await send("Runtime.evaluate", { expression: c.expr, awaitPromise: true, returnByValue: true, userGesture: true });
    out.push({ action: "eval", value: r && r.result ? r.result.value : null, exception: r && r.exceptionDetails ? String(JSON.stringify(r.exceptionDetails).slice(0, 400)) : null });
  } else if (c.action === "shot") {
    let clip = null;
    if (c.clipSelector) {
      const rect = await send("Runtime.evaluate", {
        expression: `(() => { const e = document.querySelector(${JSON.stringify(c.clipSelector)}); if (!e) return null; const r = e.getBoundingClientRect(); const x = Math.max(0, Math.floor(r.left) - 4); const y = Math.max(0, Math.floor(r.top) - 4); return { x, y, width: Math.max(10, Math.min(window.innerWidth - x, Math.ceil(r.width) + 8)), height: Math.max(10, Math.min(window.innerHeight - y, Math.ceil(r.height) + 8)) }; })()`,
        returnByValue: true,
      });
      clip = rect && rect.result ? rect.result.value : null;
    }
    const shot = await send("Page.captureScreenshot", { format: "png", fromSurface: true, ...(clip ? { clip: { ...clip, scale: 1 } } : {}) });
    writeFileSync(c.path, Buffer.from(shot.data, "base64"));
    out.push({ action: "shot", path: c.path, clip });
  } else if (c.action === "mouse") {
    // 受信任鼠标（拖拽/点击）：{action:"mouse", type:"mousePressed"|"mouseMoved"|"mouseReleased"|"mouseWheel", x,y, button}
    await send("Input.dispatchMouseEvent", {
      type: c.type, x: c.x, y: c.y, button: c.button || "left", clickCount: c.clickCount || 1,
      ...(c.type === "mouseWheel" ? { deltaX: c.deltaX || 0, deltaY: c.deltaY || 0 } : {}),
    });
    out.push({ action: "mouse", type: c.type, x: c.x, y: c.y });
  }
}
console.log(JSON.stringify({ ok: true, results: out }));
process.exit(0);
