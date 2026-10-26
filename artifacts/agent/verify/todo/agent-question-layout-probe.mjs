#!/usr/bin/env node
/* task-162 实测探针：选择题卡片在「会话栏 260px / 10 选项长解释」下的改前/改后高度。
 *
 * 真机（WebView2）里用真实渲染器 `window.MemoriaAgentQuestion.cardEl(row)` 建卡，
 * 放进指定内容宽度的容器测真实布局高度（非截图估算）。
 * 同时截 narrow(260)/wide(700)/expanded/focus/已答态 截图。
 *
 * 用法：node agent-question-layout-probe.mjs --cdp http://127.0.0.1:9595 \
 *        --out artifacts/agent/verify/todo/agent-question-layout-before.json \
 *        --label before
 */
"use strict";
import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith("--")) { const k = t.slice(2); const nxt = argv[i + 1]; if (nxt && !nxt.startsWith("--")) { a[k] = nxt; i++; } else a[k] = true; }
    else a._.push(t);
  }
  return a;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function httpJson(url, timeoutMs = 3000) {
  const ctrl = new AbortController(); const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try { return await (await fetch(url, { signal: ctrl.signal })).json(); } finally { clearTimeout(to); }
}
class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._pending = new Map(); ws.addEventListener("message", (e) => this._on(e.data)); }
  static connect(url) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(url);
      const to = setTimeout(() => rej(new Error("CDP 超时")), 15000);
      ws.addEventListener("open", () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener("error", () => { clearTimeout(to); rej(new Error("CDP 失败")); });
    });
  }
  _on(data) {
    let m; try { m = JSON.parse(typeof data === "string" ? data : String(data)); } catch { return; }
    if (m.id == null) return; const p = this._pending.get(m.id); if (!p) return;
    this._pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => { const id = ++this._id; this._pending.set(id, { resolve, reject }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
  async evalJS(expr, { timeoutMs = 20000 } = {}) {
    const p = this.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true, userGesture: true });
    const guard = new Promise((_, rej) => setTimeout(() => rej(new Error("evalJS 超时")), timeoutMs));
    const r = await Promise.race([p, guard]);
    if (r && r.exceptionDetails) throw new Error("evalJS 异常: " + String((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text).slice(0, 300));
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expr, { timeout = 30000, label = "" } = {}) {
    const t0 = Date.now();
    for (;;) { let v; try { v = await this.evalJS(expr); } catch { v = false; } if (v) return v; if (Date.now() - t0 > timeout) throw new Error("等待超时 " + label); await sleep(120); }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}
async function connectAppPage(cdpBase) {
  const list = await httpJson(cdpBase.replace(/\/$/, "") + "/json/list");
  for (const t of (list || []).filter((x) => x && x.type === "page" && x.webSocketDebuggerUrl)) {
    let cdp = null;
    try {
      cdp = await CDP.connect(t.webSocketDebuggerUrl);
      await cdp.waitFor('!!(window.MemoriaApp && window.MemoriaAgentQuestion && window.MemoriaAgentQuestion.cardEl)', { timeout: 25000, label: "app/question" });
      return { cdp, target: t };
    } catch { try { cdp && cdp.close(); } catch { /* noop */ } }
  }
  throw new Error("没有可用 app target");
}

const LONG = "这是一段很长的解释文字，用来模拟窄会话栏里用户看到的真实情况：解释会被横向挤压，换行到很多行，从而把单个选项的高度撑得非常高，十个选项叠起来足以撑满整块会话区域，问题就在这里。";

/** 在页面里注入探针容器 + 用真实渲染器建卡；返回测量结果。 */
const MEASURE = (width) => `(function(){
  var old = document.getElementById('layout-probe');
  if (old) old.remove();
  var wrap = document.createElement('div');
  wrap.id = 'layout-probe';
  wrap.style.cssText = 'position:fixed;left:8px;top:8px;width:${width}px;max-height:calc(100vh - 16px);overflow:auto;z-index:99999;background:var(--bg-primary);padding:8px;box-sizing:border-box;';
  document.body.appendChild(wrap);
  var options = [];
  for (var i = 1; i <= 10; i++) {
    options.push({ label: '选项 ' + i + '：一个比较长的选项名称', description: ${JSON.stringify(LONG)} + '（第 ' + i + ' 项）' });
  }
  var row = { id: 'probe-q-' + Date.now(), questions: [{ id: 'probe-q1', header: '窄栏测试', question: '请选择一个选项', multiSelect: false, options: options }] };
  var card = window.MemoriaAgentQuestion.cardEl(row);
  wrap.appendChild(card);
  var q = card.querySelector('.-agent-question');
  var opts = card.querySelector('.-agent-question-opts');
  var rows = [].slice.call(card.querySelectorAll('.-agent-question-opt'));
  var descs = [].slice.call(card.querySelectorAll('.-agent-question-opt-desc'));
  function h(el){ return el ? Math.round(el.getBoundingClientRect().height) : null; }
  var res = {
    width: ${width},
    cardHeight: h(card),
    questionHeight: h(q),
    optsHeight: h(opts),
    rowHeights: rows.map(h),
    rowCount: rows.length,
    descHeights: descs.map(h),
    descClamped: descs.length ? (descs[0].scrollHeight > descs[0].clientHeight + 1) : null,
    descScrollHeight: descs.length ? descs[0].scrollHeight : null,
    descTitle: descs.length ? descs[0].getAttribute('title') : null,
    labelHeight: rows.length ? h(rows[0].querySelector('.-agent-question-opt-label')) : null,
    rowDisplay: rows.length ? getComputedStyle(rows[0]).display : null,
    rowDirection: rows.length ? getComputedStyle(rows[0]).flexDirection : null,
    descDisplay: descs.length ? getComputedStyle(descs[0]).display : null,
    descLineClamp: descs.length ? getComputedStyle(descs[0]).webkitLineClamp : null,
    focusH: null,
    doneH: null
  };
  // 聚焦第一项（键盘可达展开验证）
  // 注意：测量函数本身不改变焦点，保证窄/宽截图是"未聚焦的 2 行 clamp"状态
  // 已答态
  card.classList.add('-agent-question--done');
  res.doneH = h(card);
  card.classList.remove('-agent-question--done');
  window.__layoutProbe = { card: card, wrap: wrap };
  return res;
})()`;

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cdpBase = String(args.cdp || "http://127.0.0.1:9595");
  const label = String(args.label || "run");
  const OUT = path.resolve(String(args.out || "artifacts/agent/verify/todo/agent-question-layout.json"));
  const shotDir = path.join(path.dirname(OUT), "agent-question-layout-screens");
  fs.mkdirSync(shotDir, { recursive: true });
  const out = { label, startedAt: new Date().toISOString(), steps: {} };
  globalThis.__probeOut = out;
  globalThis.__probeOutPath = OUT;

  let conn = null, lastErr = null;
  for (let i = 0; i < 90; i++) { try { conn = await connectAppPage(cdpBase); break; } catch (e) { lastErr = e; await sleep(700); } }
  if (!conn) throw lastErr;
  const { cdp } = conn;
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  async function shot(name) {
    const r = await cdp.send("Page.captureScreenshot", { format: "png" });
    const p = path.join(shotDir, label + "-" + name + ".png");
    fs.writeFileSync(p, Buffer.from(r.data, "base64"));
    return p;
  }

  // 关闭可能挡住的浮层（无则无副作用）
  await cdp.evalJS(`(function(){ document.getElementById('layout-probe')?.remove(); return true; })()`);
  await sleep(400);

  out.steps.narrow260 = await cdp.evalJS(MEASURE(260));
  out.steps.narrow260.shot = await shot("narrow-260");
  await sleep(200);
  out.steps.narrow260.afterShot = await cdp.evalJS(MEASURE(260));
  // 展开态（聚焦第一项）单独截图
  await cdp.evalJS(`(function(){ var c=window.__layoutProbe.card; var i=c.querySelector('.-agent-question-opt input'); i.focus(); return true; })()`);
  await sleep(250);
  out.steps.expanded = await cdp.evalJS(`(function(){
    var c=window.__layoutProbe.card; var d=c.querySelector('.-agent-question-opt-desc');
    function h(el){return el?Math.round(el.getBoundingClientRect().height):null;}
    return { cardHeight:h(c), descHeight:h(d), descClamped: d? (d.scrollHeight>d.clientHeight+1):null, title:d?d.getAttribute('title'):null };
  })()`);
  out.steps.expanded.shot = await shot("expanded-focus");
  // 选中展开（鼠标点击后失焦也应保持展开——:has(input:checked)）
  out.steps.selected = await cdp.evalJS(`(function(){
    var c=window.__layoutProbe.card; var i=c.querySelector('.-agent-question-opt input');
    i.click(); i.blur();
    var d=c.querySelector('.-agent-question-opt-desc');
    function h(el){return el?Math.round(el.getBoundingClientRect().height):null;}
    return { cardHeight:h(c), descHeight:h(d), checked:i.checked,
             hasSupport:(function(){try{return document.querySelector('.-agent-question-opt:has(input:checked)')!==null;}catch(e){return false;}})(),
             expanded:(d.scrollHeight<=d.clientHeight+1) };
  })()`);
  await sleep(200);
  out.steps.selected.shot = await shot("selected-expanded");
  await cdp.evalJS(`(function(){ document.activeElement && document.activeElement.blur(); return true; })()`);

  out.steps.wide700 = await cdp.evalJS(MEASURE(700));
  out.steps.wide700.shot = await shot("wide-700");
  await sleep(150);

  // 已答态截图（真实 --done 类；先失焦，避免把"展开态"混进已答高度）
  await cdp.evalJS(MEASURE(260));
  await cdp.evalJS(`(function(){ document.activeElement && document.activeElement.blur(); return true; })()`);
  await sleep(200);
  await cdp.evalJS(`(function(){ window.__layoutProbe.card.classList.add('-agent-question--done'); return true; })()`);
  await sleep(200);
  out.steps.done = await cdp.evalJS(`(function(){
    var c=window.__layoutProbe.card; var i=c.querySelector('.-agent-question-opt');
    function h(el){return el?Math.round(el.getBoundingClientRect().height):null;}
    return { cardHeight:h(c), itemOpacity:getComputedStyle(c.querySelector('.-agent-question-item')).opacity, modeBadge:(c.querySelector('.-agent-question-mode')||{}).textContent||null };
  })()`);
  out.steps.done.shot = await shot("done-260");
  // 单选/多选徽标语义（只读校验，不改逻辑）
  out.steps.multiBadge = await cdp.evalJS(`(function(){
    var row = { id:'probe-multi-'+Date.now(), questions:[{ id:'probe-q2', header:'多选测试', question:'请选择', multiSelect:true, options:[{label:'A',description:'甲'},{label:'B',description:'乙'}] }] };
    var card = window.MemoriaAgentQuestion.cardEl(row);
    var badge = (card.querySelector('.-agent-question-mode')||{}).textContent || null;
    var inputs = card.querySelectorAll('input[type=checkbox]').length;
    card.remove();
    return { badge: badge, checkboxCount: inputs };
  })()`);
  // 清理
  await cdp.evalJS(`(function(){ document.getElementById('layout-probe')?.remove(); return true; })()`);

  cdp.close();
  out.finishedAt = new Date().toISOString();
  fs.writeFileSync(OUT, JSON.stringify(out, null, 2), "utf8");
  console.log("OUT=" + OUT);
  for (const k of ["narrow260", "expanded", "wide700", "done"]) console.log(k, JSON.stringify(out.steps[k]));
  return 0;
}
main().then((c) => process.exit(c)).catch((e) => {
  try { if (globalThis.__probeOutPath) fs.writeFileSync(globalThis.__probeOutPath, JSON.stringify(globalThis.__probeOut || {}, null, 2), "utf8"); } catch (_) { /* noop */ }
  console.error("[probe] FATAL:", e && e.stack ? e.stack : e); process.exit(2);
});
