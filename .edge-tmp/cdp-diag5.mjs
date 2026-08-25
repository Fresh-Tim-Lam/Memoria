
const pages = await (await fetch('http://127.0.0.1:9222/json/list')).json();
const page = pages.find(p => p.url && p.url.indexOf('8642') !== -1);
if (!page) { console.log('NO_PAGE'); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0;
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
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const msgId = ++id;
  pending.set(msgId, { resolve, reject });
  ws.send(JSON.stringify({ id: msgId, method, params }));
});
const evalJs = async (expr) => {
  const res = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  if (res.exceptionDetails) throw new Error('EVAL: ' + JSON.stringify(res.exceptionDetails.exception ? res.exceptionDetails.exception.description : res.exceptionDetails.text));
  return res.result.value;
};
const SELB = '.m0-tree-item[data-path="brush-test.md"]';
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
await send('Runtime.enable');
await send('DOM.enable');
const doc = await send('DOM.getDocument', { depth: 0 });
const rootId = doc.root ? doc.root.nodeId : (doc.result ? doc.result.root.nodeId : -1);
console.log('ROOTID=' + rootId);
const qr = await send('DOM.querySelector', { nodeId: rootId, selector: SELB });
let listeners = 'n/a';
try {
  const ls = await send('DOMDebugger.getEventListeners', { nodeId: qr.result.nodeId });
  listeners = JSON.stringify(ls.result.listeners.map(l => l.type + ':' + (l.useCapture ? 'cap' : 'bub')));
} catch (e) { listeners = 'ERR ' + e.message; }
const globals = await evalJs('JSON.stringify(Object.keys(window).filter(k => k.toLowerCase().indexOf("memoria") !== -1))');
const extraExpr = 'JSON.stringify((() => { const item = document.querySelector(' + JSON.stringify(SELB) + '); if (!item) return null; return { html: item.outerHTML.slice(0, 220), parent: item.parentElement ? item.parentElement.className : null }; })())';
const extra = await evalJs(extraExpr);
console.log('NODEID=' + qr.result.nodeId);
console.log('LISTENERS=' + listeners);
console.log('GLOBALS=' + globals);
console.log('EXTRA=' + extra);
ws.close();
process.exit(0);
