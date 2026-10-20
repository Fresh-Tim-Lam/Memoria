#!/usr/bin/env node
/**
 * interaction.mjs —— 显示子系统「交互契约」测试骨架（零新依赖）
 *
 * 目的：为「文件显示区域」重构织安全网。核心能力：
 *   1) **受信任的鼠标**：press / move / release / 双击 / 拖拽选词/连选 / Shift+点击扩选；
 *   2) **受信任的键盘 + 修饰键**：Shift、Ctrl、Ctrl+Shift 组合（扩选、按词跳、到行首尾、全选）；
 *   3) **IME 组合输入**：`Input.imeSetComposition` + `Input.insertText`（纯键事件测不到中文输入）；
 *   4) **选区断言**：`window.getSelection()` 的 anchor/focus（节点 + 偏移 + 所属块）；
 *   5) **快照 + 双跑对比**：同一剧本可在「旧实现 / 新实现」上各跑一遍，比对快照差异。
 *
 * 为什么不用 playwright/puppeteer：CDP 的 `Input` 域本身就产生 `isTrusted=true` 的真实事件，
 * 与本仓既有 `cdp.mjs` 同一条路；再加依赖只是多一层包装。
 *
 * 用法：
 *   node scripts/benchmark/surface/interaction.mjs --selftest --url http://127.0.0.1:8643/
 *   node scripts/benchmark/surface/interaction.mjs --scenarios <in.json> --out <out.json> --url <url>
 */

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// ─────────────────────────────────────────────────────────────────────────────
// 0. 修饰键位掩码（CDP 规范）
// ─────────────────────────────────────────────────────────────────────────────
export const MOD = { none: 0, alt: 1, ctrl: 2, meta: 4, shift: 8 };
export function mods(names) {
  let m = 0;
  for (const n of names || []) m |= MOD[n] ?? 0;
  return m;
}

const EDGE_CANDIDATES = [
  process.env.MEMORIA_EDGE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);

function findEdge() {
  for (const p of EDGE_CANDIDATES) {
    try { if (fs.existsSync(p)) return p; } catch { /* noop */ }
  }
  throw new Error('找不到 msedge.exe；可用环境变量 MEMORIA_EDGE 指定。');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const js = (v) => JSON.stringify(v);

async function httpJson(url) {
  const r = await fetch(url);
  return r.json();
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. 极简 CDP 客户端（与 cdp.mjs 同款，独立一份避免互相耦合）
// ─────────────────────────────────────────────────────────────────────────────
class CDP {
  constructor(ws) {
    this.ws = ws;
    this._id = 0;
    this._pending = new Map();
    ws.addEventListener('message', (ev) => this._onMessage(ev.data));
  }

  static connect(wsUrl) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl);
      const to = setTimeout(() => reject(new Error('CDP WebSocket 连接超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); resolve(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); reject(new Error('CDP 连接失败: ' + wsUrl)); });
    });
  }

  _onMessage(data) {
    let msg;
    try { msg = JSON.parse(typeof data === 'string' ? data : String(data)); } catch { return; }
    if (msg.id == null) return;
    const p = this._pending.get(msg.id);
    if (!p) return;
    this._pending.delete(msg.id);
    if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
    else p.resolve(msg.result);
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this._id;
      this._pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true, userGesture: true,
    });
    if (r && r.exceptionDetails) {
      throw new Error('eval 异常: ' + (r.exceptionDetails.text || '') + ' ' +
        ((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || ''));
    }
    return r && r.result ? r.result.value : undefined;
  }

  async waitFor(expression, { timeout = 45000, interval = 150, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) {
      let v;
      try { v = await this.evalJS(expression); } catch { v = false; }
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '') + ': ' + expression);
      await sleep(interval);
    }
  }

  close() { try { this.ws.close(); } catch { /* noop */ } }
}

async function launchEdge({ headless = true, port } = {}) {
  const edgePath = findEdge();
  const cdpPort = port || (9222 + Math.floor(Math.random() * 3000));
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'memoria-ix-edge-'));
  const args = [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-background-networking', '--remote-allow-origins=*',
    '--window-size=1280,900',
    `--remote-debugging-port=${cdpPort}`, `--user-data-dir=${userDataDir}`, 'about:blank',
  ];
  const proc = spawn(edgePath, args, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let stderr = '';
  proc.stderr.on('data', (d) => { stderr += d.toString(); });

  const base = `http://127.0.0.1:${cdpPort}`;
  const t0 = Date.now();
  let version = null;
  for (;;) {
    try { version = await httpJson(base + '/json/version'); if (version && version.webSocketDebuggerUrl) break; } catch { /* not up */ }
    if (Date.now() - t0 > 20000) { try { proc.kill(); } catch { /* noop */ } throw new Error('Edge CDP 未就绪: ' + stderr.slice(0, 500)); }
    await sleep(200);
  }
  const list = await httpJson(base + '/json/list').catch(() => []);
  let page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!page) {
    try {
      const created = await fetch(base + '/json/new?about:blank', { method: 'PUT' }).then((r) => r.json());
      page = created && created.webSocketDebuggerUrl ? created : null;
    } catch { /* noop */ }
  }
  const wsUrl = page ? page.webSocketDebuggerUrl : (version.webSocketDebuggerUrl || null);
  if (!wsUrl) { try { proc.kill(); } catch { /* noop */ } throw new Error('拿不到 webSocketDebuggerUrl'); }
  return {
    port: cdpPort, browser: version.Browser || 'Edge', wsUrl,
    cleanup() { try { proc.kill(); } catch { /* noop */ } try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { /* noop */ } },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. 交互原语（全部走 CDP Input 域 ⇒ isTrusted=true）
// ─────────────────────────────────────────────────────────────────────────────
class Interactions {
  constructor(cdp) { this.cdp = cdp; this.mouse = { x: 0, y: 0 }; }

  // ── 鼠标 ────────────────────────────────────────────────────────────────
  async mouseMove(x, y, { buttons = 0, modifiers = 0 } = {}) {
    this.mouse = { x, y };
    await this.cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved', x, y, button: 'none', buttons, modifiers,
    });
  }

  async mouseDown(x, y, { button = 'left', clickCount = 1, modifiers = 0 } = {}) {
    this.mouse = { x, y };
    await this.cdp.send('Input.dispatchMouseEvent', {
      type: 'mousePressed', x, y, button, buttons: 1, clickCount, modifiers,
    });
  }

  async mouseUp(x, y, { button = 'left', clickCount = 1, modifiers = 0 } = {}) {
    this.mouse = { x, y };
    await this.cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseReleased', x, y, button, buttons: 0, clickCount, modifiers,
    });
  }

  async click(x, y, { button = 'left', clickCount = 1, modifiers = 0 } = {}) {
    await this.mouseMove(x, y, { modifiers });
    await this.mouseDown(x, y, { button, clickCount, modifiers });
    await this.mouseUp(x, y, { button, clickCount, modifiers });
  }

  /** 双击（clickCount=1 再 =2，浏览器据此做「选英文单词」）。 */
  async doubleClick(x, y, { modifiers = 0 } = {}) {
    await this.click(x, y, { clickCount: 1, modifiers });
    await sleep(20);
    await this.click(x, y, { clickCount: 2, modifiers });
  }

  /** 连续拖拽：press → N 次 move（带 buttons=1）→ release。**选区由此产生**。
   *  `moveButton`：Chromium 里拖拽选择的 mouseMoved 需要带 `button:'left'`（仅 buttons:1 不够，
   *  实测后者不扩选）。默认 'left'，可传 'none' 复现旧行为做对照。 */
  async drag(from, to, { steps = 12, modifiers = 0, moveButton = 'left', settleMs = 12 } = {}) {
    await this.mouseMove(from.x, from.y, { modifiers });
    await this.mouseDown(from.x, from.y, { modifiers });
    // 先在同一位置补一次 move（跨过拖拽判定的最小位移门槛），再向目标推进
    await this.cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved', x: from.x, y: from.y, button: moveButton, buttons: 1, modifiers,
    });
    let last = { x: from.x, y: from.y };
    for (let i = 1; i <= steps; i++) {
      const t2 = i / steps;
      const x = Math.round(from.x + (to.x - from.x) * t2);
      const y = Math.round(from.y + (to.y - from.y) * t2);
      await this.cdp.send('Input.dispatchMouseEvent', {
        type: 'mouseMoved', x, y, button: moveButton, buttons: 1, modifiers,
      });
      last = { x, y };
      await sleep(settleMs);
    }
    await this.mouseUp(last.x, last.y, { modifiers });
  }

  // ── 键盘 + 修饰键 ───────────────────────────────────────────────────────
  static VK = {
    ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40,
    Home: 36, End: 35, Enter: 13, Escape: 27, Tab: 9,
    Backspace: 8, Delete: 46, ' ': 32,
  };

  async keyDown(key, { code = '', vk = 0, modifiers = 0, text = undefined } = {}) {
    const p = { type: text ? 'keyDown' : 'rawKeyDown', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers };
    if (text != null) { p.text = text; p.unmodifiedText = text; }
    await this.cdp.send('Input.dispatchKeyEvent', p);
  }

  async keyUp(key, { code = '', vk = 0, modifiers = 0 } = {}) {
    await this.cdp.send('Input.dispatchKeyEvent', {
      type: 'keyUp', key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, modifiers,
    });
  }

  /**
   * 按一个键（可带修饰键）。`modifiers` 传名字数组，如 ['shift'] / ['ctrl','shift']。
   * 关键：Ctrl+Shift+方向 之类是浏览器原生「按词扩选」，必须真的带 modifiers 位，而不是模拟单个键。
   */
  async press(key, { mods: modNames = [], code = '', vk = 0 } = {}) {
    const m = mods(modNames);
    const v = vk || Interactions.VK[key] || 0;
    const c = code || (key.length === 1 ? (key === ' ' ? 'Space' : 'Key' + key.toUpperCase()) : key);
    await this.keyDown(key, { code: c, vk: v, modifiers: m });
    await this.keyUp(key, { code: c, vk: v, modifiers: m });
  }

  /** 受信任逐字符输入（同 cdp.mjs 口径）。 */
  async typeText(text) {
    for (const ch of String(text)) {
      const cp = ch.codePointAt(0);
      const isLetter = /[a-zA-Z]/.test(ch);
      const isDigit = /[0-9]/.test(ch);
      const code = isLetter ? 'Key' + ch.toUpperCase() : (isDigit ? 'Digit' + ch : '');
      const vk = isLetter ? ch.toUpperCase().charCodeAt(0) : cp;
      const down = { type: 'keyDown', text: ch, unmodifiedText: ch, key: ch, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
      const up = { type: 'keyUp', key: ch, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
      if (code) { down.code = code; up.code = code; }
      await this.cdp.send('Input.dispatchKeyEvent', down);
      await this.cdp.send('Input.dispatchKeyEvent', up);
    }
  }

  /**
   * IME 组合输入（中文等）：先 `imeSetComposition` 模拟「正在拼」，再 `insertText` 落字。
   * 纯 keyDown 事件测不到输入法路径 —— 本仓 `compositionend` 有专门逻辑（180ms 延迟等），
   * 只有走这条才真正覆盖它。
   */
  async imeCompose(text, { commit = true, composeMs = 120 } = {}) {
    await this.cdp.send('Input.imeSetComposition', {
      text: String(text), selectionStart: String(text).length, selectionEnd: String(text).length,
    });
    await sleep(composeMs);
    if (commit) {
      await this.cdp.send('Input.insertText', { text: String(text) });
    } else {
      await this.cdp.send('Input.imeSetComposition', { text: '', selectionStart: 0, selectionEnd: 0 });
    }
  }

  // ── 选区断言 ────────────────────────────────────────────────────────────
  /** 当前选区（anchor/focus 的节点、字符偏移、所属预览块、整段文本）。 */
  async selection() {
    return await this.cdp.evalJS(`(function(){
      var s = window.getSelection();
      if (!s) return null;
      var out = { collapsed: s.isCollapsed, rangeCount: s.rangeCount, text: s.toString() };
      if (!s.rangeCount) return out;
      var r = s.getRangeAt(0);
      function info(node, offset){
        if (!node) return null;
        var el = node.nodeType === 1 ? node : node.parentElement;
        var block = el && el.closest ? el.closest('#preview .-src-block') : null;
        var inPreview = el && el.closest ? !!el.closest('#preview') : false;
        return {
          nodeType: node.nodeType,
          offset: offset,
          textLen: node.nodeType === 3 ? node.nodeValue.length : null,
          blockIndex: block ? (block.dataset.blockIndex == null ? null : +block.dataset.blockIndex) : null,
          inPreview: inPreview,
          sample: (node.nodeType === 3 ? node.nodeValue : (el ? el.textContent : '')).slice(0, 48)
        };
      }
      out.anchor = info(r.startContainer, r.startOffset);
      out.focus  = info(r.endContainer, r.endOffset);
      return out;
    })()`);
  }

  /**
   * 计算「某块内第 from..to 个字符」的屏幕点，供拖拽选词。
   * 返回 { start, end, total, box }；坐标已 scrollIntoView（block:'center'）后取。
   */
  async pointsInBlock(selector, nth = 0, from = 0, to = 6) {
    return await this.cdp.evalJS(`(function(sel, nth, from, to){
      var scope = sel === '#preview' || sel === 'block'
        ? document.querySelectorAll('#preview .-src-block')[nth]
        : document.querySelectorAll(sel)[nth];
      if (!scope) return null;
      scope.scrollIntoView({ block: 'center' });
      var walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, null);
      var nodes = [], n;
      while ((n = walker.nextNode())) nodes.push(n);
      var total = 0; for (var i=0;i<nodes.length;i++) total += nodes[i].nodeValue.length;
      function locate(off){
        var acc = 0;
        for (var i=0;i<nodes.length;i++){
          var len = nodes[i].nodeValue.length;
          if (acc + len >= off) return { node: nodes[i], offset: Math.max(0, Math.min(len, off - acc)) };
          acc += len;
        }
        var last = nodes[nodes.length-1];
        return last ? { node: last, offset: last.nodeValue.length } : null;
      }
      function pt(off, preferEnd){
        var loc = locate(off); if (!loc) return null;
        var r = document.createRange();
        r.setStart(loc.node, loc.offset);
        r.setEnd(loc.node, Math.min(loc.node.nodeValue.length, loc.offset + 1));
        var rects = r.getClientRects();
        var rect = rects.length ? (preferEnd ? rects[rects.length-1] : rects[0]) : r.getBoundingClientRect();
        if (!rect || (!rect.width && !rect.height)) return null;
        return { x: Math.round(rect.left + Math.max(1, rect.width/2)), y: Math.round(rect.top + rect.height/2) };
      }
      var b = scope.getBoundingClientRect();
      return {
        start: pt(Math.max(0, from), false),
        end: pt(Math.max(0, Math.min(total, to)), true),
        total: total,
        box: { x: Math.round(b.left + b.width/2), y: Math.round(b.top + b.height/2) }
      };
    })(${js(selector)}, ${nth}, ${from}, ${to})`);
  }

  /**
   * 两个块内各取一个点（**一次 eval 算完**，避免两次 scrollIntoView 造成坐标错位）。
   * 用于「跨块拖选」：从 A 块某字符拖到 B 块某字符。
   */
  async pointsInTwoBlocks(na, offA, nb, offB) {
    return await this.cdp.evalJS(`(function(na, offA, nb, offB){
      var blocks = document.querySelectorAll('#preview .-src-block');
      var A = blocks[na], B = blocks[nb];
      if (!A || !B) return null;
      A.scrollIntoView({ block: 'center' });
      function ptIn(scope, off){
        var walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, null);
        var nodes = [], n;
        while ((n = walker.nextNode())) nodes.push(n);
        var target = null, acc = 0;
        for (var i=0;i<nodes.length;i++){
          var len = nodes[i].nodeValue.length;
          if (acc + len >= off || i === nodes.length-1) { target = { node: nodes[i], offset: Math.max(0, Math.min(len, off - acc)) }; break; }
          acc += len;
        }
        if (!target) return null;
        var r = document.createRange();
        r.setStart(target.node, target.offset);
        r.setEnd(target.node, Math.min(target.node.nodeValue.length, target.offset + 1));
        var rects = r.getClientRects();
        var rect = rects.length ? rects[rects.length-1] : r.getBoundingClientRect();
        if (!rect || (!rect.width && !rect.height)) return null;
        return { x: Math.round(rect.left + Math.max(1, rect.width/2)), y: Math.round(rect.top + rect.height/2) };
      }
      var a = ptIn(A, Math.max(0, offA));
      var b = ptIn(B, Math.max(0, offB));
      if (!a || !b) return null;
      return { start: a, end: b, blockA: na, blockB: nb };
    })(${na}, ${offA}, ${nb}, ${offB})`);
  }

  /** 找出「文本够多、且真的有文本节点」的块索引（避开公式块/图片块 ⇒ 那里没有可选文字）。 */
  async textBlocks(minLen = 40) {
    return await this.cdp.evalJS(`(function(minLen){
      var blocks = document.querySelectorAll('#preview .-src-block');
      var out = [];
      for (var i = 0; i < blocks.length; i++) {
        var b = blocks[i];
        var txt = (b.textContent || '').replace(/\\s+/g, ' ').trim();
        if (txt.length < minLen) continue;
        if (txt.indexOf('<!--') === 0) continue;   // 注释块不是正文，不拿它做选区用例
        var rb = b.getBoundingClientRect();
        if (!rb || (!rb.width && !rb.height)) continue;
        var walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT, null);
        var has = false, total = 0;
        while (walker.nextNode()) { has = true; total += walker.currentNode.nodeValue.length; }
        if (has && total >= minLen) out.push(i);
        if (out.length >= 8) break;
      }
      return out;
    })(${minLen})`);
  }

  /**
   * 找一对**都在视口内**的正文块（跨块拖拽/Shift+点击必须两点同时可见，
   * 否则 CDP 的鼠标事件落在视口外会被浏览器丢弃 —— 这是实测踩过的坑）。
   * 返回 { a, b } 两个块下标；找不到返回 null。
   */
  async visibleTextPair(minLen = 30) {
    return await this.cdp.evalJS(`(function(minLen){
      var blocks = document.querySelectorAll('#preview .-src-block');
      var vh = window.innerHeight;
      function cands(){
        var out = [];
        for (var i = 0; i < blocks.length; i++) {
          var b = blocks[i];
          var txt = (b.textContent || '').replace(/\\s+/g, ' ').trim();
          if (txt.length < minLen || txt.indexOf('<!--') === 0) continue;
          var r = b.getBoundingClientRect();
          if (!r.width || !r.height) continue;
          out.push({ i: i, top: r.top, bottom: r.bottom, len: txt.length });
        }
        return out;
      }
      function pick(list){
        for (var x = 0; x < list.length; x++) {
          var A = list[x];
          if (A.top < 0 || A.bottom > vh) continue;
          for (var y = x + 1; y < list.length; y++) {
            var B = list[y];
            if (B.top < 0 || B.bottom > vh) continue;
            return { a: A.i, b: B.i, aLen: A.len, bLen: B.len };
          }
        }
        return null;
      }
      var got = pick(cands());
      if (got) return got;
      // 视口内凑不齐 ⇒ 把第一个候选滚到顶部后重算（滚动是同步的，重新取 rect 即为新布局）
      var c0 = cands();
      if (c0.length) { blocks[c0[0].i].scrollIntoView({ block: 'start' }); }
      got = pick(cands());
      if (got) return got;
      // 放宽容差：允许顶部略出界
      var lst = cands();
      for (var x2 = 0; x2 < lst.length; x2++) {
        var A2 = lst[x2];
        if (A2.top < -24) continue;
        for (var y2 = x2 + 1; y2 < lst.length; y2++) {
          var B2 = lst[y2];
          if (B2.top < -24 || B2.bottom > vh + 24) continue;
          return { a: A2.i, b: B2.i, aLen: A2.len, bLen: B2.len };
        }
      }
      return null;
    })(${minLen})`);
  }

  /** 页面快照（用于新老双跑对比）：选区 + 每个块的可见文本 + 块数与身份属性。 */  async snapshot() {
    const sel = await this.selection();
    const outline = await this.cdp.evalJS(`(function(){
      var blocks = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
      return blocks.slice(0, 60).map(function(b){
        return {
          i: b.dataset.blockIndex == null ? null : +b.dataset.blockIndex,
          srcLine: b.dataset.srcLine == null ? null : +b.dataset.srcLine,
          text: (b.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80)
        };
      });
    })()`);
    return { url: await this.cdp.evalJS('location.href'), selection: sel, blocks: outline };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. 剧本执行器
// ─────────────────────────────────────────────────────────────────────────────
async function runScenarios(ix, cdp, scenarios, { onSnapshot } = {}) {
  const results = [];
  /** 把 "auto"/"auto1" 解析成「文本够多」的真实块索引（避开公式块/图片块）。 */
  async function resolveNth(v, caches) {
    if (typeof v !== 'string') return v;
    if (v === 'pairA' || v === 'pairB') {
      if (!caches.pair) caches.pair = await ix.visibleTextPair(30);
      if (!caches.pair) throw new Error('找不到视口内成对正文块（pairA/pairB）');
      return v === 'pairA' ? caches.pair.a : caches.pair.b;
    }
    if (!v.startsWith('auto')) return v;
    if (!caches.blocks) caches.blocks = await ix.textBlocks(40);
    if (!caches.blocks.length) throw new Error('找不到文本块（auto）');
    const idx = v === 'auto' ? 0 : (parseInt(v.slice(4), 10) || 0);
    return caches.blocks[Math.min(idx, caches.blocks.length - 1)];
  }
  for (const sc of scenarios) {
    const rec = { id: sc.id, steps: [], snapshots: {}, error: null };
    const caches = {};
    try {
      for (const st of sc.steps || []) {
        const log = { op: st.op };
        switch (st.op) {
          case 'open': {
            // 桥接/后端 RPC 可能尚未就绪（实测偶发「API 不可用」）⇒ 重试 3 次再判失败
            let lastErr = null;
            for (let attempt = 0; attempt < 3; attempt++) {
              try {
                await cdp.evalJS(`window.MemoriaApp.openFile(${js(st.file)}, ${js(st.opts || {})})`);
                await cdp.waitFor(`window.state.currentPath === ${js(st.file)} && !!window.state.doc`, { timeout: 20000, label: 'open ' + st.file });
                // 二次校验：确认没有被随后的启动/刷新动作覆盖
                await sleep(350);
                const stillThere = await cdp.evalJS(`window.state.currentPath === ${js(st.file)}`);
                if (!stillThere) throw new Error('打开后被其它动作覆盖: ' + st.file);
                lastErr = null;
                break;
              } catch (e) {
                lastErr = e;
                await sleep(600);
              }
            }
            if (lastErr) throw lastErr;
            // 视图必须显式切：默认可能是 source（源码视图），那时 #preview 是空的、没有任何块
            if (st.view) {
              const okV = await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view=' + ${js(st.view)} + ']');if(!b)return false;b.click();return true;})()`);
              if (!okV) throw new Error('找不到视图按钮: ' + st.view);
              await cdp.waitFor(`window.state.viewMode === ${js(st.view)}`, { label: 'viewMode ' + st.view });
            }
            // 预览就绪由 open 自己保证（调用方不必再 wait）：
            // 实测偶发「视图已切但 #preview 仍空」⇒ 再点一次视图按钮重试，仍失败才把现场诊断抛出。
            if (st.view && st.view !== 'source') {
              const blocksExpr = `document.querySelectorAll('#preview .-src-block').length > ${st.minBlocks || 3}`;
              try {
                await cdp.waitFor(blocksExpr, { timeout: 12000, label: 'blocks-in-open' });
              } catch (e1) {
                await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view=' + ${js(st.view)} + ']');if(b)b.click();return !!b;})()`);
                try {
                  await cdp.waitFor(blocksExpr, { timeout: 30000, label: 'blocks-in-open-retry' });
                } catch (e2) {
                  const diag = await cdp.evalJS(`(function(){var p=document.querySelector('#preview');return {viewMode:(window.state||{}).viewMode, curPath:(window.state||{}).currentPath, previewLen:p?p.innerHTML.length:-1, blocks:document.querySelectorAll('#preview .-src-block').length};})()`).catch(() => null);
                  throw new Error('预览未就绪（重试后仍空）: ' + JSON.stringify(diag));
                }
              }
            }
            break;
          }
          case 'view': {
            const okv = await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view=' + ${js(st.mode)} + ']');if(!b)return false;b.click();return true;})()`);
            if (!okv) throw new Error('找不到视图按钮: ' + st.mode);
            await cdp.waitFor(`window.state.viewMode === ${js(st.mode)}`, { label: 'viewMode ' + st.mode });
            break;
          }
          case 'wait':
            await cdp.waitFor(st.expr, { timeout: st.timeout || 45000, label: st.label || '' });
            break;
          case 'sleep':
            await sleep(st.ms || 200);
            break;
          case 'clickSelector': {
            const box = await cdp.evalJS(`(function(){var el=document.querySelectorAll(${js(st.selector)})[${st.nth || 0}];if(!el)return null;el.scrollIntoView({block:'nearest'});var r=el.getBoundingClientRect();return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2),w:Math.round(r.width)};})()`);
            if (!box || !box.w) throw new Error('元素不可点: ' + st.selector);
            await ix.click(box.x, box.y, { modifiers: mods(st.modifiers) });
            log.box = box;
            break;
          }
          case 'clickInBlock': {
            const pts = await ix.pointsInBlock(st.selector || 'block', await resolveNth(st.nth, caches), st.at || 0, (st.at || 0) + 1);
            if (!pts || !pts.start) throw new Error('拿不到块内点击坐标');
            await ix.click(pts.start.x, pts.start.y, { modifiers: mods(st.modifiers) });
            log.points = pts;
            break;
          }
          case 'dragSelect': {
            const pts = await ix.pointsInBlock(st.selector || 'block', await resolveNth(st.nth, caches), st.from || 0, st.to || 6);
            if (!pts || !pts.start || !pts.end) throw new Error('拿不到拖拽坐标');
            await ix.drag(pts.start, pts.end, { modifiers: mods(st.modifiers), steps: st.steps || 12 });
            log.points = pts;
            break;
          }
          case 'dragBetweenBlocks': {
            const pts = await ix.pointsInTwoBlocks(await resolveNth(st.fromBlock ?? 'auto', caches), st.fromOffset || 0, await resolveNth(st.toBlock ?? 'auto1', caches), st.toOffset || 0);
            if (!pts || !pts.start || !pts.end) throw new Error('拿不到跨块拖拽坐标');
            await ix.drag(pts.start, pts.end, { modifiers: mods(st.modifiers), steps: st.steps || 14 });
            log.points = pts;
            break;
          }
          case 'doubleClickInBlock': {
            const pts = await ix.pointsInBlock(st.selector || 'block', await resolveNth(st.nth, caches), st.at || 0, (st.at || 0) + 1);
            if (!pts || !pts.start) throw new Error('拿不到双击坐标');
            await ix.doubleClick(pts.start.x, pts.start.y, { modifiers: mods(st.modifiers) });
            log.points = pts;
            break;
          }
          case 'key':
            await ix.press(st.key, { mods: st.modifiers || [], code: st.code, vk: st.vk });
            break;
          case 'type':
            await ix.typeText(st.text || '');
            break;
          case 'ime':
            await ix.imeCompose(st.text || '', { commit: st.commit !== false });
            break;
          case 'eval':
            log.value = await cdp.evalJS(st.expr);
            break;
          case 'snapshot':
            rec.snapshots[st.label || ('s' + rec.steps.length)] = await ix.snapshot();
            if (onSnapshot) onSnapshot(sc.id, st.label, rec.snapshots[st.label]);
            break;
          default:
            throw new Error('未知 op: ' + st.op);
        }
        rec.steps.push(log);
      }
    } catch (e) {
      rec.error = String((e && e.message) || e);
    }
    results.push(rec);
  }
  return results;
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. CLI
// ─────────────────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const k = a.slice(2);
    const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
    out[k] = v;
  }
  return out;
}

/**
 * 等应用「启动自检」落定：实测应用启动时会**异步自动打开一个默认文件**，
 * 若剧本抢在它之前 open，会被它随后覆盖 ⇒ 出现「viewMode 对、curPath 却变成 README、preview 空」。
 * 判据：currentPath 连续 stableMs 不变，才算启动结束。
 */
async function waitAppSettled(cdp, { stableMs = 1200, timeout = 40000 } = {}) {
  let last = null, since = Date.now();
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    let cur = null, hasDoc = false;
    try {
      const st = await cdp.evalJS('({p: (window.state && window.state.currentPath) || null, d: !!(window.state && window.state.doc)})');
      cur = st && st.p; hasDoc = !!(st && st.d);
    } catch { /* 还没就绪 */ }
    // 必须「已真有文档」才算稳定：否则启动早期 currentPath=null 也会被误判为已落定，
    // 随后应用才去自动打开默认文件，把剧本的 open 覆盖掉（实测踩过）。
    if (cur !== last) { last = cur; since = Date.now(); }
    else if (cur && hasDoc && Date.now() - since >= stableMs) return cur;
    await sleep(200);
  }
  return last;
}

async function withBrowser(url, fn) {
  const edge = await launchEdge({ headless: true });
  const cdp = await CDP.connect(edge.wsUrl);
  try {
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.navigate', { url });
    // 应用启动偶发超时（机器忙 / 首次编译脚本）：readyState 或 MemoriaApp 等不到时 reload 重试，
    // 三次仍失败才抛错，并带上现场诊断（href/title/脚本数/body 长度），避免「只看到超时」无法定位。
    let ready = false;
    let lastErr = null;
    for (let attempt = 0; attempt < 3 && !ready; attempt++) {
      try {
        await cdp.waitFor('document.readyState === "complete"', { timeout: 60000, label: 'readyState' });
        await cdp.waitFor('!!window.MemoriaApp', { timeout: 60000, label: 'MemoriaApp' });
        ready = true;
      } catch (e) {
        lastErr = e;
        if (attempt < 2) {
          try { await cdp.send('Page.reload', { ignoreCache: true }); } catch { /* noop */ }
          await sleep(1500);
        }
      }
    }
    if (!ready) {
      const diag = await cdp.evalJS(`({href: location.href, title: document.title, scripts: document.scripts.length, hasApp: !!window.MemoriaApp, bodyLen: document.body ? document.body.innerHTML.length : -1})`).catch(() => null);
      throw new Error('应用未就绪（reload 重试后仍失败）: ' + JSON.stringify(diag) + ' | ' + (lastErr && lastErr.message));
    }
    const settledPath = await waitAppSettled(cdp);
    // 启动尾动作（恢复上次视图/刷新文件列表）可能再改一次 currentPath ⇒ 再等一会并复查
    await sleep(1500);
    await cdp.waitFor('!!window.state && !!window.state.doc', { timeout: 20000, label: 'doc-after-settle' });
    const ix = new Interactions(cdp);
    return await fn(cdp, ix, edge);
  } finally {
    cdp.close();
    edge.cleanup();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.selftest) {
    const url = args.url;
    if (!url) throw new Error('--selftest 需要 --url');
    const r = await withBrowser(url, async (cdp, ix) => {
      const info = await cdp.evalJS('({ href: location.href, hasApp: !!window.MemoriaApp, hasSel: typeof window.getSelection === "function" })');
      // 造一个受信任点击 + 一次键盘输入，验证通路
      await ix.mouseMove(10, 10);
      await ix.click(10, 10);
      const sel = await ix.selection();
      return { info, sel, ok: !!info.hasApp && !!info.hasSel };
    });
    process.stdout.write(JSON.stringify(r, null, 2) + '\n');
    process.exit(r.ok ? 0 : 1);
  }

  if (args.bench) {
    if (!args.url || !args.file) throw new Error('--bench 需要 --url 与 --file（--file-b 可选）');
    const fileA = args.file;
    const fileB = args['file-b'] || null;
    const minBlocks = parseInt(args['min-blocks'] || '5', 10);
    const out = await withBrowser(args.url, async (cdp, ix, edge) => {
      const rec = { schema: 'memoria-baseline-bench/v1', fileA, fileB, minBlocks, steps: {}, samples: {} };

      /** 等预览「块出现且数量稳定」（连续 3 次相同才算定）—— 这是「可见就绪」的判据。 */
      async function waitPreviewReady(timeout = 180000) {
        const t0 = Date.now();
        let lastN = -1, lastM = -1, stable = 0, n = 0, m = 0;
        let blocksAt = 0;
        const TYPESET_GRACE = 25000; // 块就绪后，最多再等这么久让公式排版稳定
        for (;;) {
          const snap = await cdp.evalJS(`(function(){
            return {
              n: document.querySelectorAll('#preview .-src-block').length,
              m: document.querySelectorAll('#preview mjx-container').length,
              loading: !!document.querySelector('#preview .-preview-loading')
            };
          })()`);
          n = snap.n; m = snap.m;
          if (n >= minBlocks && !snap.loading) {
            if (!blocksAt) blocksAt = Date.now();
            if (n === lastN && m === lastM) {
              stable++;
              if (stable >= 3) return { blocks: n, typeset: m, ms: Date.now() - t0, typesetStable: true };
            } else { lastN = n; lastM = m; stable = 0; }
            // 块已就绪但公式排版一直不稳 ⇒ 到宽限就收，如实标注（不假装稳定）
            if (Date.now() - blocksAt > TYPESET_GRACE) {
              return { blocks: n, typeset: m, ms: Date.now() - t0, typesetStable: false };
            }
          } else { lastN = -1; lastM = -1; stable = 0; blocksAt = 0; }
          if (Date.now() - t0 > timeout) throw new Error('预览就绪超时（blocks=' + n + ' typeset=' + m + '）');
          await sleep(80);
        }
      }

      /** 应用默认可能是 source 视图（此时 #preview 为空）⇒ 显式切到预览。 */
      async function ensurePreviewView() {
        const mode = await cdp.evalJS('(window.state||{}).viewMode');
        if (mode === 'preview') return;
        await cdp.evalJS(`(function(){var b=document.querySelector('.-view-btn[data-view="preview"]');if(b)b.click();return !!b;})()`);
        await cdp.waitFor('(window.state||{}).viewMode === "preview"', { timeout: 15000, label: 'viewMode-preview' });
      }

      // ① 首开（应用刚启动后的第一次打开）
      {
        await ensurePreviewView();
        const t0 = Date.now();
        await cdp.evalJS(`window.MemoriaApp.openFile(${js(fileA)}, {})`);
        // 打开后视图可能被「按文件的视图偏好」复位成 source ⇒ 再确保一次（不计入耗时）
        await ensurePreviewView();
        const r = await waitPreviewReady();
        rec.steps.coldOpen = { path: fileA, readyMs: Date.now() - t0, blocks: r.blocks, typeset: r.typeset };
      }

      // ② 切页签（A→B→A，重复 N 次；报告每次「回到 A 可见」的耗时）
      if (fileB) {
        const samples = [];
        await ensurePreviewView();
        for (let i = 0; i < 3; i++) {
          await cdp.evalJS(`window.MemoriaApp.openFile(${js(fileB)}, {})`);
          await ensurePreviewView();
          await waitPreviewReady();
          const t0 = Date.now();
          await cdp.evalJS(`window.MemoriaApp.openFile(${js(fileA)}, {})`);
          await ensurePreviewView();
          const r = await waitPreviewReady();
          samples.push({ ms: Date.now() - t0, blocks: r.blocks, typeset: r.typeset });
        }
        rec.samples.tabSwitchBackToA = samples;
        rec.steps.tabSwitch = { medianMs: samples.map((s) => s.ms).sort((a, b) => a - b)[1] };
      }

      // ③ 打字（进入编辑态 → 逐键；量「按键派发 → 预览 DOM 有变化」的时延）
      {
        await cdp.evalJS('(function(){var EH=window.MemoriaEditHandler;if(EH&&!EH.editMode)EH.toggleEditMode();return !!(EH&&EH.editMode);})()');
        await sleep(500);
        await cdp.evalJS(`(function(){var b=document.querySelectorAll('#preview .-src-block')[0];if(b)b.scrollIntoView({block:'center'});return !!b;})()`);
        const box = await cdp.evalJS(`(function(){var b=document.querySelectorAll('#preview .-src-block')[0];if(!b)return null;var r=b.getBoundingClientRect();return {x:Math.round(r.left+40),y:Math.round(r.top+r.height/2)};})()`);
        if (box) await ix.click(box.x, box.y);
        await sleep(200);
        await cdp.evalJS(`(function(){
          window.__bench = { samples: [], t0: 0 };
          var host = document.querySelector('#preview');
          var mo = new MutationObserver(function(){
            if (window.__bench.t0) { window.__bench.samples.push(performance.now() - window.__bench.t0); window.__bench.t0 = 0; }
          });
          mo.observe(host, { subtree: true, characterData: true, childList: true, attributes: true });
          window.__benchMo = mo;
          return true;
        })()`);
        const warmup = parseInt(args['warmup-keys'] || '5', 10);
        const keys = parseInt(args['keys'] || '30', 10);
        for (let i = 0; i < warmup + keys; i++) {
          await cdp.evalJS('window.__bench.t0 = performance.now(); true');
          await ix.typeText('a');
          await sleep(130);
        }
        const samples = await cdp.evalJS('(window.__bench && window.__bench.samples) || []');
        const measured = samples.slice(warmup);
        const sorted = measured.slice().sort((a, b) => a - b);
        const pick = (q) => sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] : null;
        rec.samples.typing = measured.map((v) => Math.round(v * 10) / 10);
        rec.steps.typing = {
          warmup, keys, n: measured.length,
          minMs: sorted.length ? Math.round(sorted[0] * 10) / 10 : null,
          medianMs: sorted.length ? Math.round(pick(0.5) * 10) / 10 : null,
          p95Ms: sorted.length ? Math.round(pick(0.95) * 10) / 10 : null,
          maxMs: sorted.length ? Math.round(sorted[sorted.length - 1] * 10) / 10 : null,
        };
      }

      // ④ 内存（Chromium 的 JS 堆；不是进程 RSS，标注清楚）
      const mem = await cdp.evalJS('(performance.memory ? {usedJSHeapMB: Math.round(performance.memory.usedJSHeapSize/1048576*10)/10, totalJSHeapMB: Math.round(performance.memory.totalJSHeapSize/1048576*10)/10} : null)');
      const blocks = await cdp.evalJS("document.querySelectorAll('#preview .-src-block').length");
      const nodes = await cdp.evalJS("document.querySelectorAll('#preview *').length");
      rec.steps.memory = { ...(mem || {}), blocks, domNodesInPreview: nodes };
      rec.browser = edge.browser;
      rec.finishedAt = new Date().toISOString();
      return rec;
    });
    fs.mkdirSync(path.dirname(args.out), { recursive: true });
    fs.writeFileSync(args.out, JSON.stringify(out, null, 2), 'utf8');
    process.stdout.write('__BENCH_JSON__' + JSON.stringify({ ok: true, out: args.out, steps: out.steps }) + '\n');
    process.exit(0);
  }

  if (args.scenarios) {
    if (!args.url || !args.out) throw new Error('--scenarios 需要 --url/--out');
    const spec = JSON.parse(fs.readFileSync(args.scenarios, 'utf8'));
    const startedAt = new Date().toISOString();
    const out = await withBrowser(args.url, async (cdp, ix, edge) => {
      const results = await runScenarios(ix, cdp, spec.scenarios || []);
      return {
        schema: 'memoria-interaction-run/v1',
        startedAt, finishedAt: new Date().toISOString(),
        url: args.url, browser: edge.browser, label: args.label || null,
        results,
      };
    });
    fs.mkdirSync(path.dirname(args.out), { recursive: true });
    fs.writeFileSync(args.out, JSON.stringify(out, null, 2), 'utf8');
    const failed = out.results.filter((r) => r.error).length;
    process.stdout.write('__INTERACTION_JSON__' + JSON.stringify({
      ok: failed === 0, out: args.out, scenarios: out.results.length, failed,
    }) + '\n');
    process.exit(failed === 0 ? 0 : 1);
  }

  process.stderr.write('用法：--selftest | --scenarios <json> --out <json>，均需 --url\n');
  process.exit(2);
}

main().catch((e) => { process.stderr.write(String((e && e.stack) || e) + '\n'); process.exit(1); });
