// task-133 诊断：判断 agent-panel.js 中 `return { ... }` 之后的追加块是否**可达**。
// 做法（只读，不改任何源码）：在 post-return 首行（`askRecordText` 前）与 return 之前各设一个断点，
// 然后 reload；看哪些断点被命中。若 post-return 行从不命中 ⇒ 那些追加块是死代码。
import { writeFileSync } from "node:fs";

const PORT = Number(process.argv[2] || 9577);
const OUT = process.argv[3] || ".";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
const target = list.find((t) => t.type === "page" && String(t.url).startsWith("http://127.0.0.1"));
if (!target) throw new Error("no target");
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0;
const pending = new Map();
const events = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id); pending.delete(m.id);
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
  } else if (m.method) {
    events.push(m);
    if (m.method === "Debugger.paused") {
      // 记录后立刻放行，才能命中后续断点
      const mid = ++id;
      ws.send(JSON.stringify({ id: mid, method: "Debugger.resume", params: {} }));
    }
  }
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const mid = ++id; pending.set(mid, { resolve, reject });
  ws.send(JSON.stringify({ id: mid, method, params }));
});

await send("Page.enable");
await send("Debugger.enable");
// 行号 0 基：pre = 1-based 6832（return 之前的函数体，应命中）；
// post = 1-based 6921/6928（return 之后的注释/函数声明）——函数声明 hoist，但**语句**不执行；
// 用 post_stmt = 7062（`const baseIntakeImageFiles = intakeImageFiles;`，一条**语句**）最稳。
const bpPre = await send("Debugger.setBreakpointByUrl", { lineNumber: 6589, urlRegex: "agent-panel\\.js" }); // 6589 0-based ~ 6590（restoreTurnUsage 语句区）
const bpPost = await send("Debugger.setBreakpointByUrl", { lineNumber: 7061, urlRegex: "agent-panel\\.js" }); // 7062 1-based：const baseIntakeImageFiles = ...
const bpPost2 = await send("Debugger.setBreakpointByUrl", { lineNumber: 7251, urlRegex: "agent-panel\\.js" }); // 7252 1-based：我加的 baseRenderStatusUsageForCompact
const bpReturn = await send("Debugger.setBreakpointByUrl", { lineNumber: 6873, urlRegex: "agent-panel\\.js" }); // 6874：return {

await send("Page.reload", { ignoreCache: true });
await sleep(9000);
const paused = events.filter((e) => e.method === "Debugger.paused");
const hitLines = [];
for (const p of paused) {
  for (const f of p.params.callFrames || []) {
    if (String(f.url).includes("agent-panel.js")) hitLines.push(f.location.lineNumber + 1);
  }
}
const hits = (bp) => (bp.locations || []).map((l) => l.lineNumber + 1);
writeFileSync(
  `${OUT}/deadcode-probe.json`,
  JSON.stringify(
    {
      breakpoints: { pre: hits(bpPre), returnStmt: hits(bpReturn), postStmt: hits(bpPost), myPostBlock: hits(bpPost2) },
      pausedCount: paused.length,
      hitLinesSample: Array.from(new Set(hitLines)).sort((a, b) => a - b).slice(0, 40),
      hitStatements: {
        return_6874: hitLines.includes(6874),
        post_7062: hitLines.includes(7062),
        my_7252: hitLines.includes(7252),
        pre_6590: hitLines.includes(6590) || hitLines.includes(6589),
      },
    },
    null,
    2
  ),
  "utf8"
);
console.log(JSON.stringify({ pausedCount: paused.length, hitStatements: { return_6874: hitLines.includes(6874), post_7062: hitLines.includes(7062), my_7252: hitLines.includes(7252) } }));
process.exit(0);
