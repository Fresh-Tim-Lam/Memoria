#!/usr/bin/env node
/**
 * realapp_humanlike.mjs —— 「拟人节奏」对照驱动
 *
 * 用途（协议 §7 偏差校验）：在**无法真人操作**的自动化环境里，给出「输入时序」对读数的
 * **下界影响估计**。它不是人工读数，不能冒充人工读数（报告里必须这样写）。
 *
 * 与 realapp_measure.mjs --driver auto 的唯一差别：
 *   每键之间插入**拟人停顿**（默认 120±60 ms，可设），其余一切相同（同一埋点、同一通道）。
 *   ⇒ 两者之差 = 「输入到达间隔」对 `beforeinput → insertText 返回` 的影响。
 *
 * 用法：
 *   node scripts/benchmark/surface/realapp_humanlike.mjs --port 9500 --keys 25 --interval 120
 */

import fs from 'node:fs';
import path from 'node:path';
import { findAppTarget, waitAppReady } from './realapp_probe.mjs';

function parseArgs(argv) {
  const a = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t.startsWith('--')) {
      const k = t.slice(2);
      const nxt = argv[i + 1];
      if (nxt && !nxt.startsWith('--')) { a[k] = nxt; i++; } else { a[k] = true; }
    } else a._.push(t);
  }
  return a;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._pending = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
  static connect(u) {
    return new Promise((res, rej) => {
      const ws = new WebSocket(u);
      const to = setTimeout(() => rej(new Error('CDP WS 超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); res(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); rej(new Error('CDP WS 失败')); });
    });
  }
  _on(d) {
    let m; try { m = JSON.parse(typeof d === 'string' ? d : String(d)); } catch { return; }
    if (m.id == null) return;
    const p = this._pending.get(m.id); if (!p) return;
    this._pending.delete(m.id);
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
  send(method, params = {}) { return new Promise((res, rej) => { const id = ++this._id; this._pending.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) throw new Error('eval 异常: ' + (r.exceptionDetails.text || ''));
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expr, { timeout = 60000, interval = 100, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) {
      let v; try { v = await this.evalJS(expr); } catch { v = false; }
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : ''));
      await sleep(interval);
    }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

function stats(arr) {
  const v = (arr || []).filter((x) => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return null;
  const q = (p) => { const h = (v.length - 1) * p; const lo = Math.floor(h), hi = Math.ceil(h); return lo === hi ? v[lo] : v[lo] + (v[hi] - v[lo]) * (h - lo); };
  const med = q(0.5); const r3 = (x) => +x.toFixed(3);
  return { n: v.length, min: r3(v[0]), median: r3(med), p95: r3(q(0.95)), max: r3(v[v.length - 1]), iqr: r3(q(0.75) - q(0.25)), iqrOverMedian: med > 0 ? r3((q(0.75) - q(0.25)) / med) : null, p95OverMedian: med > 0 ? r3(q(0.95) / med) : null };
}

/** 页面内埋点（只需 A 指标；与 realapp_measure.mjs 的 startKey 同口径） */
function INSTALL_KEY() {
  var R = window.__ramhl = { installed: true, lastArrive: null, keys: [], n: 0 };
  var pv = document.getElementById('preview');
  if (!pv) return { ok: false, reason: 'no-preview' };
  var ES = window.MemoriaEditSync;
  if (!ES || typeof ES.insertText !== 'function') return { ok: false, reason: 'no-editsync' };
  var orig = ES.insertText;
  ES.insertText = function () {
    var a = R.lastArrive; var t1 = performance.now();
    var r = orig.apply(this, arguments);
    var t2 = performance.now(); R.n++;
    R.keys.push({ seq: R.n, arriveToReturnMs: a != null ? +(t2 - a).toFixed(3) : null, insertMs: +(t2 - t1).toFixed(3) });
    return r;
  };
  R.uninstall = function () { try { ES.insertText = orig; } catch (e) {} };
  pv.addEventListener('beforeinput', function () { R.lastArrive = performance.now(); }, true);
  R.reset = function () { R.keys = []; R.n = 0; return true; };
  R.state = function () { return { n: R.n, keys: R.keys.slice() }; };
  return { ok: true };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const port = parseInt(args.port || '9500', 10);
  const keys = parseInt(args.keys || '25', 10);
  const interval = parseInt(args.interval || '120', 10);
  const jitter = parseInt(args.jitter || '60', 10);
  const warmup = parseInt(args['warmup-keys'] || '5', 10);
  const rounds = parseInt(args.rounds || '5', 10);
  const fileA = args['file-a'] || 'scale/scale-5k.md';
  const out = args.out || null;
  const result = { schema: 'memoria-realapp-humanlike/v1', port, keys, interval, jitter, rounds, fileA, startedAt: new Date().toISOString() };
  let cdp = null, exitCode = 1;
  try {
    const target = await findAppTarget(port);
    cdp = await CDP.connect(target.webSocketDebuggerUrl);
    await cdp.send('Runtime.enable');
    await waitAppReady(cdp);
    await cdp.evalJS('(function(){try{if(window.__ramhl&&window.__ramhl.uninstall)window.__ramhl.uninstall();}catch(e){}window.__ramhl=null;return true;})()');
    // 打开目标文件并确保预览
    await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(fileA)}, { skipNav: true })`);
    await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(fileA)} && !!window.state.doc`, { label: 'open' });
    const mode = await cdp.evalJS('(window.state||{}).viewMode');
    if (mode !== 'preview') {
      await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b)b.click();return true;})()`);
      await cdp.waitFor('(window.state||{}).viewMode === "preview"', { label: 'preview' });
    }
    await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 3`, { label: 'blocks' });
    await sleep(500);
    const inst = await cdp.evalJS('(' + INSTALL_KEY.toString() + ')()');
    if (!inst || !inst.ok) throw new Error('埋点失败: ' + JSON.stringify(inst));
    // 进入编辑态 + 点进首块
    await cdp.evalJS(`(function(){var EH=window.MemoriaEditHandler;if(EH&&!EH.editMode&&EH.toggleEditMode)EH.toggleEditMode();return !!(EH&&EH.editMode);})()`);
    await sleep(400);
    const box = await cdp.evalJS(`(function(){var b=document.querySelectorAll('#preview .-src-block')[0];if(!b)return null;b.scrollIntoView({block:'center'});var r=b.getBoundingClientRect();return {x:Math.round(r.left+30),y:Math.round(r.top+r.height/2)};})()`);
    if (box) {
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box.x, y: box.y, button: 'none', buttons: 0 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x, y: box.y, button: 'left', buttons: 1, clickCount: 1 });
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x, y: box.y, button: 'left', buttons: 0, clickCount: 1 });
    }
    await sleep(300);
    const typeKey = async () => {
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', text: 'z', unmodifiedText: 'z', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90 });
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90 });
    };
    // warmup（跟着拟人节奏敲，丢弃）
    for (let i = 0; i < warmup; i++) {
      await typeKey();
      await sleep(interval + (Math.random() * 2 - 1) * jitter);
    }
    await cdp.evalJS('window.__ramhl.reset()');
    const perRound = [];
    for (let r = 0; r < rounds; r++) {
      for (let i = 0; i < keys; i++) {
        await typeKey();
        await sleep(Math.max(10, interval + (Math.random() * 2 - 1) * jitter));
      }
      const st = await cdp.evalJS('window.__ramhl.state()');
      perRound.push(stats(st.keys.map((k) => k.arriveToReturnMs)));
      await cdp.evalJS('window.__ramhl.reset()');
    }
    result.perRound = perRound;
    result.roundMedians = perRound.filter(Boolean).map((x) => x.median);
    result.statsOfRoundMedians = stats(result.roundMedians);
    result.ok = true;
    exitCode = 0;
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) { try { await cdp.evalJS('(function(){try{if(window.__ramhl&&window.__ramhl.uninstall)window.__ramhl.uninstall();}catch(e){}return true;})()'); } catch { /* noop */ } cdp.close(); }
    setTimeout(() => process.exit(exitCode), 4000).unref();
  }
  const text = JSON.stringify(result, null, 2);
  if (out) { fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, text, 'utf8'); process.stdout.write('__HUMANLIKE__' + JSON.stringify({ ok: result.ok, out }) + '\n'); }
  else process.stdout.write(text + '\n');
  return exitCode;
}

const code = await main();
process.exitCode = code;
