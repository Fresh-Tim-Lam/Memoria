#!/usr/bin/env node
/**
 * realapp_domwrites.mjs —— 真机「每键 DOM 写入 / attributes 变更 / 打字时延」三元组基线
 *
 * 目的（Lead 阶段 1 硬闸）：`BlockIndex.upsert()` 会在每键多加若干次 DOM 属性写。
 * 本脚本在**改造前**代码上取基线，供 P1 落地后逐项对照。
 *
 * 复用真机链路（与 realapp_measure.mjs 同款）：attach 已运行的应用（WebView2 已开 CDP），
 * 页面内埋点用 performance.now()，读数与输入来源无关。
 *
 * 用法：
 *   node scripts/benchmark/surface/realapp_domwrites.mjs --port 9500 --out raw.json
 *   node scripts/benchmark/surface/realapp_domwrites.mjs --port 9500 --rounds 5 --keys 10
 *
 * 计数器方法见 dom_write_counter.mjs（M1 = hook DOM 写 API 计调用次数；M2 = MutationObserver 计变更记录）。
 * **两种都报**，理由见该文件头注释。
 */

import fs from 'node:fs';
import path from 'node:path';
import { findAppTarget, waitAppReady } from './realapp_probe.mjs';
import { INSTALL_DOM_COUNTER } from './dom_write_counter.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

class CDP {
  constructor(ws) { this.ws = ws; this._id = 0; this._p = new Map(); ws.addEventListener('message', (e) => this._on(e.data)); }
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
    const p = this._p.get(m.id); if (!p) return;
    this._p.delete(m.id);
    m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result);
  }
  send(method, params = {}) {
    return new Promise((res, rej) => { const id = ++this._id; this._p.set(id, { resolve: res, reject: rej }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) {
      const d = r.exceptionDetails;
      throw new Error('eval 异常: ' + String((d.exception && (d.exception.description || d.exception.value)) || d.text || '').split('\n')[0]);
    }
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
  return {
    n: v.length, min: r3(v[0]), median: r3(med), p95: r3(q(0.95)), max: r3(v[v.length - 1]),
    iqr: r3(q(0.75) - q(0.25)),
    iqrOverMedian: med > 0 ? r3((q(0.75) - q(0.25)) / med) : null,
    p95OverMedian: med > 0 ? r3(q(0.95) / med) : null,
  };
}

async function ensurePreview(cdp) {
  const mode = await cdp.evalJS('(window.state||{}).viewMode || null');
  if (mode === 'preview') return 'already';
  await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b)b.click();return true;})()`);
  await cdp.waitFor('(window.state||{}).viewMode === "preview"', { label: 'viewMode=preview', timeout: 15000 });
  return 'switched';
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const port = parseInt(args.port || '9500', 10);
  const fileA = args['file-a'] || 'scale/scale-5k.md';
  const rounds = parseInt(args.rounds || '5', 10);
  const keysPerRound = parseInt(args.keys || '10', 10);
  const warmup = parseInt(args['warmup-keys'] || '5', 10);
  const out = args.out || null;

  const result = {
    schema: 'memoria-realapp-domwrites/v1',
    purpose: '阶段 1（BlockIndex）落地前的「每键 DOM 写入」基线',
    port, fileA, rounds, keysPerRound, warmup,
    startedAt: new Date().toISOString(),
    counterMethod: {
      m1: 'hook Element.prototype.setAttribute/removeAttribute + DOMTokenList.add/remove/toggle + CSSStyleDeclaration.setProperty ⇒ 计**调用次数**（程序想写多少次）',
      m2: 'MutationObserver(#preview, {subtree,childList,characterData,attributes}) ⇒ 计**浏览器实际观察到的变更记录数**',
      window: '本键 beforeinput 到达 → insertText 返回 → 微任务落定（takeRecords 补收）',
      why_both: 'M1 高而 M2 低 ⇒ 冗余写（写重复值被合并）；M1 低而 M2 高 ⇒ 结构性写（innerHTML/换节点）M1 看不见。二者不可互相替代。',
    },
    environment: {},
    rounds: [],
  };
  let cdp = null;
  let exitCode = 1;
  try {
    const version = await (async () => {
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), 3000);
      try { const r = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: ctrl.signal }); return await r.json(); }
      finally { clearTimeout(to); }
    })();
    result.environment.browser = version.Browser;
    const target = await findAppTarget(port);
    result.environment.target = { id: target.id, title: target.title, url: target.url };
    cdp = await CDP.connect(target.webSocketDebuggerUrl);
    await cdp.send('Runtime.enable');
    await waitAppReady(cdp);
    result.environment.gpu = await cdp.evalJS(`(function(){
      try { var c=document.createElement('canvas'); var gl=c.getContext('webgl');
        if(!gl) return {webgl:false};
        var d=gl.getExtension('WEBGL_debug_renderer_info');
        return {webgl:true, renderer:d?gl.getParameter(d.UNMASKED_RENDERER_WEBGL):null};
      } catch(e){ return {webgl:false,error:String(e)}; }
    })()`);
    result.environment.viewport = await cdp.evalJS('({w: innerWidth, h: innerHeight, dpr: devicePixelRatio})');
    result.environment.kbPath = await cdp.evalJS('(window.state||{}).kbPath || null');

    // ── 改造前取证：BlockIndex 是否存在、是否已被 index.html 加载 ──────────
    result.environment.blockIndex = await cdp.evalJS(`(function(){
      var s = Array.prototype.slice.call(document.scripts).map(function(x){return x.src||'';});
      return {
        globalPresent: typeof window.MemoriaBlockIndex !== 'undefined',
        scriptLoaded: s.some(function(u){ return u.indexOf('block-index') >= 0; }),
      };
    })()`);

    // 打开目标文档 + 预览
    await cdp.evalJS(`window.MemoriaApp.openFile(${JSON.stringify(fileA)}, { skipNav: true })`);
    await cdp.waitFor(`window.state.currentPath === ${JSON.stringify(fileA)} && !!window.state.doc`, { label: 'open', timeout: 90000 });
    await ensurePreview(cdp);
    await cdp.waitFor(`document.querySelectorAll('#preview .-src-block').length > 3`, { label: 'blocks', timeout: 60000 });
    await sleep(1200);
    result.environment.docLines = await cdp.evalJS('(window.state.doc.lines||[]).length');
    result.environment.blocks = await cdp.evalJS(`document.querySelectorAll('#preview .-src-block').length`);

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

    // 安装计数器（先清残留）
    await cdp.evalJS(`(function(){try{if(window.__domw&&window.__domw.uninstall)window.__domw.uninstall();}catch(e){}window.__domw=null;return true;})()`);
    const inst = await cdp.evalJS('(' + INSTALL_DOM_COUNTER.toString() + ')()');
    if (!inst || !inst.ok) throw new Error('计数器安装失败: ' + JSON.stringify(inst));
    result.environment.counterVersion = inst.v;
    result.environment.hookedAPIs = await cdp.evalJS('window.__domw.hookedList()');

    // 逐键输入：受信任 keyDown(text)+keyUp，每键等一次微任务落定（页面内已处理）
    const typeKey = async () => {
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', text: 'z', unmodifiedText: 'z', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90 });
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90 });
      // 让页面内微任务窗口闭合（不计入被测区间：窗口终点在页面内，已在 insertText 后立即排微任务）
      await sleep(8);
    };

    // warmup（丢弃）
    for (let i = 0; i < warmup; i++) await typeKey();
    await cdp.evalJS('window.__domw.reset()');

    const allKeys = [];
    for (let r = 0; r < rounds; r++) {
      for (let k = 0; k < keysPerRound; k++) await typeKey();
      // 等本键窗口（rAF 静默判据）关闭：轮询 pendingWindows 归零
      await cdp.waitFor('(window.__domw.state().pendingWindows === 0) ? true : false', { timeout: 20000, interval: 60, label: 'windows-closed#' + r }).catch(function(){});
      const st = await cdp.evalJS('window.__domw.state()');
      const ks = (st && st.keys) || [];
      const roundKeys = ks.slice(r * keysPerRound);
      allKeys.push(...roundKeys);
      result.rounds.push({
        round: r,
        keys: roundKeys.length,
        m1Calls: stats(roundKeys.map((x) => x.m1Calls)),
        m2Records: stats(roundKeys.map((x) => x.m2Records)),
        m2Attr: stats(roundKeys.map((x) => x.m2.attr)),
        m2ChildList: stats(roundKeys.map((x) => x.m2.childList)),
        m2CharacterData: stats(roundKeys.map((x) => x.m2.characterData)),
        setAttribute: stats(roundKeys.map((x) => x.setAttribute)),
        classOps: stats(roundKeys.map((x) => x.classAdd + x.classRemove + x.classToggle)),
        arriveToReturnMs: stats(roundKeys.map((x) => x.arriveToReturnMs)),
        insertMs: stats(roundKeys.map((x) => x.insertMs)),
        rawKeys: roundKeys,
      });
    }

    // ── 汇总三元组（每轮 median 的中位，与 benchmark-measurement-protocol §5.2 同口径）──
    const medOf = (arr) => { const s = stats(arr); return s ? s.median : null; };
    const roundMedians = {
      m1Calls: result.rounds.map((r) => r.m1Calls && r.m1Calls.median),
      m2Records: result.rounds.map((r) => r.m2Records && r.m2Records.median),
      m2Attr: result.rounds.map((r) => r.m2Attr && r.m2Attr.median),
      arriveToReturnMs: result.rounds.map((r) => r.arriveToReturnMs && r.arriveToReturnMs.median),
    };
    result.triple = {
      m1CallsPerKey: medOf(roundMedians.m1Calls),
      m2RecordsPerKey: medOf(roundMedians.m2Records),
      m2AttributesPerKey: medOf(roundMedians.m2Attr),
      typingMsPerKey: medOf(roundMedians.arriveToReturnMs),
      roundMedians,
      pooled: {
        m1Calls: stats(allKeys.map((x) => x.m1Calls)),
        m2Records: stats(allKeys.map((x) => x.m2Records)),
        m2Attr: stats(allKeys.map((x) => x.m2.attr)),
        arriveToReturnMs: stats(allKeys.map((x) => x.arriveToReturnMs)),
      },
    };
    result.allKeys = allKeys;
    result.ok = true;
    exitCode = 0;
  } catch (e) {
    result.ok = false;
    result.error = String((e && e.stack) || e);
  } finally {
    result.finishedAt = new Date().toISOString();
    if (cdp) { try { await cdp.evalJS('(function(){try{if(window.__domw&&window.__domw.uninstall)window.__domw.uninstall();}catch(e){}return true;})()'); } catch { /* noop */ } cdp.close(); }
    setTimeout(() => process.exit(exitCode), 4000).unref();
  }
  const text = JSON.stringify(result, null, 2);
  if (out) {
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, text, 'utf8');
    process.stdout.write('__DOMWRITES__' + JSON.stringify({ ok: result.ok, out, triple: result.triple && {
      m1: result.triple.m1CallsPerKey, m2: result.triple.m2RecordsPerKey,
      attr: result.triple.m2AttributesPerKey, ms: result.triple.typingMsPerKey } }) + '\n');
  } else {
    process.stdout.write(text + '\n');
  }
  return exitCode;
}

const code = await main();
process.exitCode = code;
