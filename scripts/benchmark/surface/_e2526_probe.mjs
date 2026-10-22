#!/usr/bin/env node
/**
 * E25 / E26 浏览器证据探针（零新依赖，CDP + 无头 Edge，与 interaction.mjs 同一条路）
 *
 * 用法：
 *   node scripts/benchmark/surface/_e2526_probe.mjs --url http://127.0.0.1:PORT/ \
 *        --phase before|after --out artifacts/agent/verify/e2526/probe-<phase>.json
 *
 * 证据项：
 *   E26-A 连续回车：光标越过视口 ⇒ 修后 scrollTop 跟随；修前 scrollTop 恒 0（光标留在视口外）
 *   E26-B 光标本就可见时回车 ⇒ scrollTop 必须一动不动
 *   E26-C IME：合成 input(isComposing=true) 不滚；compositionend 提交后滚；非组合 input 会滚
 *   E25  合成含 image/png 的 ClipboardEvent：修前被 text/plain 分支吞掉（defaultPrevented 但无插入），
 *        修后图片入库 + MD 独占行插入；同图重复粘贴 ⇒ 只有一份文件（MD5 去重）
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const EDGE_CANDIDATES = [
  process.env.MEMORIA_EDGE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);

function findEdge() {
  for (const p of EDGE_CANDIDATES) { try { if (fs.existsSync(p)) return p; } catch { /* noop */ } }
  throw new Error('找不到 msedge.exe；可用环境变量 MEMORIA_EDGE 指定。');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function httpJson(url) { const r = await fetch(url); return r.json(); }

class CDP {
  constructor(ws) {
    this.ws = ws; this._id = 0; this._pending = new Map();
    ws.addEventListener('message', (ev) => this._onMessage(ev.data));
  }
  static connect(wsUrl) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl);
      const to = setTimeout(() => reject(new Error('CDP 连接超时')), 15000);
      ws.addEventListener('open', () => { clearTimeout(to); resolve(new CDP(ws)); });
      ws.addEventListener('error', () => { clearTimeout(to); reject(new Error('CDP 连接失败')); });
    });
  }
  _onMessage(data) {
    let msg; try { msg = JSON.parse(typeof data === 'string' ? data : String(data)); } catch { return; }
    if (msg.id == null) return;
    const p = this._pending.get(msg.id); if (!p) return;
    this._pending.delete(msg.id);
    if (msg.error) p.reject(new Error(JSON.stringify(msg.error))); else p.resolve(msg.result);
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this._id; this._pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async evalJS(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
    if (r && r.exceptionDetails) {
      throw new Error('eval 异常: ' + (r.exceptionDetails.text || '') + ' ' +
        ((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || ''));
    }
    return r && r.result ? r.result.value : undefined;
  }
  async waitFor(expression, { timeout = 30000, interval = 120, label = '' } = {}) {
    const t0 = Date.now();
    for (;;) {
      let v; try { v = await this.evalJS(expression); } catch { v = false; }
      if (v) return v;
      if (Date.now() - t0 > timeout) throw new Error('等待超时' + (label ? '（' + label + '）' : '') + ': ' + expression);
      await sleep(interval);
    }
  }
  close() { try { this.ws.close(); } catch { /* noop */ } }
}

async function launchEdge() {
  const edgePath = findEdge();
  const net = await import('node:net');
  const port = await new Promise((resolve, reject) => {
    const srv = net.createServer(); srv.unref();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => { const a = srv.address(); const p = a && typeof a === 'object' ? a.port : 0; srv.close(() => resolve(p)); });
  });
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'memoria-e2526-edge-'));
  const args = ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--disable-background-networking', '--remote-allow-origins=*',
    '--window-size=1280,900', `--remote-debugging-port=${port}`, `--user-data-dir=${userDataDir}`, 'about:blank'];
  const proc = spawn(edgePath, args, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let stderr = ''; proc.stderr.on('data', (d) => { stderr += d.toString(); });
  const base = `http://127.0.0.1:${port}`;
  const t0 = Date.now();
  let version = null;
  for (;;) {
    try { version = await httpJson(base + '/json/version'); if (version && version.webSocketDebuggerUrl) break; } catch { /* not up */ }
    if (Date.now() - t0 > 20000) { try { proc.kill(); } catch { /* noop */ } throw new Error('Edge CDP 未就绪: ' + stderr.slice(0, 400)); }
    await sleep(200);
  }
  const list = await httpJson(base + '/json/list').catch(() => []);
  let page = (list || []).find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!page) {
    try { page = await fetch(base + '/json/new?about:blank', { method: 'PUT' }).then((r) => r.json()); } catch { /* noop */ }
  }
  const wsUrl = (page && page.webSocketDebuggerUrl) || version.webSocketDebuggerUrl;
  return { port, browser: version.Browser || 'Edge', wsUrl,
    cleanup() { try { proc.kill(); } catch { /* noop */ } try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch { /* noop */ } } };
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const k = a.slice(2);
    out[k] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  }
  return out;
}

// 三张互不相同的 1x1 PNG（真 PNG 字节；后端只按扩展名 + 内容哈希裁决，不做图像解码）
const PNG_PASTED = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC';
const PNG_MULTI_A = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNg+M8AAAICAQB7CYF4AAAAAElFTkSuQmCC';
const PNG_MULTI_B = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC';

const GEOM = `(function(){
  var p=document.getElementById('editor-pane');
  var sel=window.getSelection();
  var r=(sel&&sel.rangeCount)?sel.getRangeAt(0):null;
  var cr=r?r.getBoundingClientRect():{top:0,bottom:0,height:0,width:0};
  var lineEl=r&&r.startContainer?(r.startContainer.nodeType===3?r.startContainer.parentElement:r.startContainer):null;
  if(lineEl&&lineEl.closest) lineEl=lineEl.closest('.-line');
  var fallbackUsed=false;
  // 空行 / <br> 上的折叠光标 rect 全 0（br 没有盒子）⇒ 与产品代码同样退回所在行元素
  if((!cr.width&&!cr.height&&!cr.top&&!cr.left)&&lineEl&&lineEl.getBoundingClientRect){
    cr=lineEl.getBoundingClientRect(); fallbackUsed=true;
  }
  var pr=p.getBoundingClientRect();
  return {scrollTop:Math.round(p.scrollTop), clientHeight:p.clientHeight, scrollHeight:p.scrollHeight,
          paneTop:Math.round(pr.top), paneBottom:Math.round(pr.bottom),
          caretTop:Math.round(cr.top), caretBottom:Math.round(cr.bottom), caretHeight:Math.round(cr.height||0),
          fallbackUsed:fallbackUsed,
          line: lineEl? +lineEl.dataset.line : null,
          lines: document.querySelectorAll('#editor .-line').length,
          active: document.activeElement ? (document.activeElement.id||document.activeElement.className||document.activeElement.tagName) : null};
})()`;

async function pressEnter(cdp) {
  const p = { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 };
  await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', ...p });
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', ...p });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const phase = args.phase || 'after';
  const outPath = args.out || path.join('artifacts', 'agent', 'verify', 'e2526', `probe-${phase}.json`);
  const shotDir = args.shotDir || path.join('artifacts', 'agent', 'verify', 'e2526');
  fs.mkdirSync(shotDir, { recursive: true });

  const edge = await launchEdge();
  const cdp = await CDP.connect(edge.wsUrl);
  const rec = { phase, startedAt: new Date().toISOString(), browser: edge.browser, checks: [], e26: {}, e25: {} };
  const check = (id, ok, detail) => { rec.checks.push({ id, ok: !!ok, detail }); };

  async function shot(name) {
    try {
      const r = await cdp.send('Page.captureScreenshot', { format: 'png' });
      const file = path.join(shotDir, name + '.png');
      fs.writeFileSync(file, Buffer.from(r.data, 'base64'));
      return file;
    } catch { return null; }
  }

  try {
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Page.navigate', { url: args.url });
    await cdp.waitFor('document.readyState === "complete" && !!window.MemoriaApp', { timeout: 60000, label: 'app-ready' });
    await sleep(1200);
    await cdp.waitFor('!!window.state && !!window.state.doc', { timeout: 30000, label: 'doc' });

    // 固定：源码视图 + 编辑模式（E26 量的是源码面板滚动）
    await cdp.evalJS('window.MemoriaApp.surface.setMode("source")');
    await cdp.evalJS('(function(){var E=window.MemoriaEditHandler;if(E&&!E.editMode)E.toggleEditMode();return !!(E&&E.editMode);})()');
    await cdp.evalJS('window.MemoriaApp.openFile("notes/long.md", {})');
    await cdp.waitFor('(window.state||{}).currentPath === "notes/long.md"', { timeout: 30000, label: 'openFile' });
    await cdp.waitFor('document.querySelectorAll("#editor .-line").length > 100', { timeout: 30000, label: 'editor-lines' });
    await sleep(700);
    await cdp.evalJS('window.MemoriaApp.surface.setMode("source")');
    await sleep(300);
    rec.e26.initial = await cdp.evalJS(GEOM);

    const place = (line) => cdp.evalJS(`(function(){
      var c=document.querySelector('#line-${line} .-line-content'); if(!c) return false;
      c.focus();
      var sel=window.getSelection(), r=document.createRange(), n=c.firstChild;
      if(n) r.setStart(n, n.nodeType===3?n.textContent.length:0); else r.setStart(c,0);
      r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
      document.getElementById('editor-pane').scrollTop=0;
      return true;
    })()`);

    // ── E26-B：光标本就可见 ⇒ 绝不滚动 ──
    await place(1);
    await sleep(120);
    const visSteps = [];
    let movedWhileVisible = 0;
    for (let i = 0; i < 5; i++) {
      const before = await cdp.evalJS(GEOM);
      await pressEnter(cdp);
      await sleep(48);
      const after = await cdp.evalJS(GEOM);
      const visibleBefore = before.caretBottom > before.paneTop && before.caretTop < before.paneBottom;
      if (visibleBefore && after.scrollTop !== before.scrollTop) movedWhileVisible++;
      visSteps.push({ i, before, after, visibleBefore, scrolled: after.scrollTop !== before.scrollTop });
    }
    rec.e26.visibleSteps = visSteps;
    rec.e26.movedWhileVisible = movedWhileVisible;
    check('E26-B 光标本就可见时绝不滚动', movedWhileVisible === 0,
      `可见期间滚动次数=${movedWhileVisible}，末次 scrollTop=${visSteps[visSteps.length - 1].after.scrollTop}`);

    // ── E26-A：连续回车直到光标越过视口 ──
    const followSteps = [];
    let firstOffscreen = null;
    let badFollow = 0;
    for (let i = 0; i < 40; i++) {
      const before = await cdp.evalJS(GEOM);
      await pressEnter(cdp);
      await sleep(40);
      const after = await cdp.evalJS(GEOM);
      // 光标在"滚动内容"里的绝对位置（若从不滚动，它就是视口外的下方坐标）
      const caretInContent = after.caretBottom - after.paneTop + after.scrollTop;
      const visibleAfter = after.caretBottom <= after.paneBottom + 1 && after.caretTop >= after.paneTop - 1;
      const wouldBeOffscreen = caretInContent > after.clientHeight;
      if (wouldBeOffscreen) {
        if (firstOffscreen === null) firstOffscreen = { i, before, after, caretInContent };
        if (!visibleAfter) badFollow++;
      }
      followSteps.push({ i, line: after.line, scrollTop: after.scrollTop, caretTop: after.caretTop,
        caretBottom: after.caretBottom, paneTop: after.paneTop, paneBottom: after.paneBottom,
        caretInContent, visibleAfter, wouldBeOffscreen });
    }
    rec.e26.followSteps = followSteps;
    rec.e26.firstOffscreen = firstOffscreen;
    rec.e26.badFollowSteps = badFollow;
    const last = followSteps[followSteps.length - 1];
    const beforeFixed = followSteps.every((s) => s.scrollTop === 0) && last.caretTop > last.paneBottom;
    const afterFixed = followSteps.some((s) => s.scrollTop > 0) && badFollow === 0;
    rec.e26.last = last;
    check('E26-A 回车把光标带进视口（修后 scrollTop 跟随 / 修前恒 0）',
      phase === 'after' ? afterFixed : beforeFixed,
      `末步: line=${last.line} scrollTop=${last.scrollTop} caretTop=${last.caretTop} caretBottom=${last.caretBottom} paneBottom=${last.paneBottom} 可见=${last.visibleAfter}`);
    rec.e26.screenshot = await shot(`e26-${phase}-after-enters`);

    // ── E26-C：IME 组合期间不滚（合成事件直打真实监听器） ──
    const farLine = Math.min(160, (await cdp.evalJS(GEOM)).lines);
    await place(farLine);
    await sleep(150);
    const ime0 = await cdp.evalJS(GEOM);
    // C1：组合中（compositionstart 之后 + input.isComposing=true）⇒ 一像素不滚
    const c1 = await cdp.evalJS(`(function(){
      var c=document.querySelector('#line-${farLine} .-line-content'); if(!c) return null;
      c.focus();
      c.dispatchEvent(new CompositionEvent('compositionstart', {bubbles:true}));
      var p=document.getElementById('editor-pane'); var before=p.scrollTop;
      var ev=new InputEvent('input',{bubbles:true,isComposing:true,data:'sh'});
      c.dispatchEvent(ev);
      return {composingFlag: ev.isComposing, scrollBefore:Math.round(before), scrollAfter:Math.round(p.scrollTop)};
    })()`);
    await sleep(80);
    const imeAfterCompose = await cdp.evalJS(GEOM);
    // C2：compositionend 提交 ⇒ 组合结束这一拍补滚（光标应回到视口内）
    const c2 = await cdp.evalJS(`(function(){
      var c=document.querySelector('#line-${farLine} .-line-content'); if(!c) return null;
      c.dispatchEvent(new CompositionEvent('compositionend', {bubbles:true, data:'shi'}));
      return true;
    })()`);
    await sleep(250);
    const imeAfterEnd = await cdp.evalJS(GEOM);
    // C3：不在组合中的普通 input ⇒ 必须滚（证明 C1 的静止是守卫在起作用，不是"根本不滚"）
    await place(farLine);
    await sleep(120);
    const plainBefore = await cdp.evalJS(GEOM);
    const c3 = await cdp.evalJS(`(function(){
      var c=document.querySelector('#line-${farLine} .-line-content'); if(!c) return null;
      c.focus();
      var p=document.getElementById('editor-pane'); var before=p.scrollTop;
      c.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:false,data:'x'}));
      return {scrollBefore:Math.round(before), scrollAfter:Math.round(p.scrollTop)};
    })()`);
    await sleep(120);
    const plainAfter = await cdp.evalJS(GEOM);
    rec.e26.ime = { farLine, ime0, c1, imeAfterCompose, c2, imeAfterEnd, plainBefore, c3, plainAfter };
    check('E26-C composition 期间不滚', !!c1 && c1.scrollAfter === c1.scrollBefore, JSON.stringify(c1));
    check('E26-C compositionend 提交后跟随', imeAfterEnd.scrollTop > imeAfterCompose.scrollTop,
      `end: ${imeAfterCompose.scrollTop} -> ${imeAfterEnd.scrollTop}`);
    check('E26-C 非组合 input 会滚（证明守卫真的在起作用）', !!c3 && c3.scrollAfter > c3.scrollBefore,
      JSON.stringify(c3));

    // ── E26-D：用户刚手动滚过 ⇒ 700ms 内不强行拽回（豁免窗口） ──
    await place(farLine);                       // 光标放到视口外，scrollTop=0
    await sleep(120);
    const dScroll = await cdp.evalJS(`(function(){
      var p=document.getElementById('editor-pane');
      var before=p.scrollTop;
      // 合成一次 wheel：真实用户滚动意图（产品监听 wheel/touchmove/拖滚动条）
      p.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:-120,deltaMode:0}));
      return Math.round(before);
    })()`);
    const d1 = await cdp.evalJS(`(function(){
      var c=document.querySelector('#line-${farLine} .-line-content'); if(!c) return null;
      c.focus();
      var p=document.getElementById('editor-pane'); var before=p.scrollTop;
      c.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:false,data:'y'}));
      return {scrollBefore:Math.round(before), scrollAfter:Math.round(p.scrollTop)};
    })()`);
    await sleep(900);   // 超过 700ms 豁免窗口
    const d2 = await cdp.evalJS(`(function(){
      var c=document.querySelector('#line-${farLine} .-line-content'); if(!c) return null;
      c.focus();
      var p=document.getElementById('editor-pane'); var before=p.scrollTop;
      c.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:false,data:'z'}));
      return {scrollBefore:Math.round(before), scrollAfter:Math.round(p.scrollTop)};
    })()`);
    rec.e26.scrollGuard = { startScrollTop: dScroll, withinGrace: d1, afterGrace: d2 };
    check('E26-D 用户刚滚过 ⇒ 700ms 内不强行拽回', !!d1 && d1.scrollAfter === d1.scrollBefore, JSON.stringify(d1));
    check('E26-D 豁免到期后恢复跟随', !!d2 && d2.scrollAfter > d2.scrollBefore, JSON.stringify(d2));

    // ── E25：含 image/png 的 ClipboardEvent ──
    await cdp.evalJS('window.MemoriaApp.surface.setMode("source")');
    await sleep(200);
    await place(3);
    await sleep(150);
    const beforePaste = await cdp.evalJS('(function(){return {text: window.MemoriaApp.surface.collectText()};})()');
    const pasteInfo = await cdp.evalJS(`(function(){
      var bytes = Uint8Array.from(atob('${PNG_PASTED}'), function(c){return c.charCodeAt(0);});
      var file = new File([bytes], 'pasted.png', {type:'image/png'});
      var dt = new DataTransfer();
      dt.items.add(file);
      dt.setData('text/plain', '');        // 真实剪贴板形状：纯图时 text/plain 是空串
      var target = document.querySelector('#line-3 .-line-content') || document.querySelector('#editor .-line-content');
      target.focus();
      var sel=window.getSelection(), r=document.createRange(), n=target.firstChild;
      if(n) r.setStart(n, n.nodeType===3?n.textContent.length:0); else r.setStart(target,0);
      r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
      var ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles:true, cancelable:true});
      var notCanceled = target.dispatchEvent(ev);
      return {
        clipboardFiles: ev.clipboardData && ev.clipboardData.files ? ev.clipboardData.files.length : -1,
        clipboardText: ev.clipboardData ? ev.clipboardData.getData('text/plain') : null,
        defaultPrevented: !notCanceled,
      };
    })()`);
    rec.e25.pasteInfo = pasteInfo;
    await sleep(2500);   // 等异步 RPC 落盘 + 自动保存（markDirty 防抖）
    const afterPaste = await cdp.evalJS('(function(){return {text: window.MemoriaApp.surface.collectText(), status: (document.querySelector("#status-info")||{}).textContent || ""};})()');
    rec.e25.beforePaste = beforePaste;
    rec.e25.afterFirstPaste = afterPaste;
    rec.e25.insertedLinesFirst = afterPaste.text.split('\n').filter((l) => l.indexOf('.memoria/images/') >= 0);
    check('E25 图片粘贴不再被 text/plain 分支吞掉',
      rec.e25.insertedLinesFirst.length > 0,
      'defaultPrevented=' + pasteInfo.defaultPrevented + ' 插入行=' + JSON.stringify(rec.e25.insertedLinesFirst) +
      ' 状态栏=' + JSON.stringify(afterPaste.status));

    // 重复粘贴同一张 ⇒ MD5 去重（文件只有一份，MD 仍插入一行且指向同一路径）
    await cdp.evalJS(`(function(){
      var bytes = Uint8Array.from(atob('${PNG_PASTED}'), function(c){return c.charCodeAt(0);});
      var file = new File([bytes], 'pasted.png', {type:'image/png'});
      var dt = new DataTransfer(); dt.items.add(file); dt.setData('text/plain','');
      var target = document.querySelector('#editor .-line-content');
      target.focus();
      var sel=window.getSelection(), r=document.createRange(), n=target.firstChild;
      if(n) r.setStart(n, n.nodeType===3?n.textContent.length:0); else r.setStart(target,0);
      r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
      target.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles:true, cancelable:true}));
      return true;
    })()`);
    await sleep(2500);
    const afterSecond = await cdp.evalJS('(function(){return {text: window.MemoriaApp.surface.collectText(), status: (document.querySelector("#status-info")||{}).textContent || ""};})()');
    rec.e25.afterSecondPaste = afterSecond;
    rec.e25.imageRefs = afterSecond.text.split('\n').filter((l) => l.indexOf('.memoria/images/') >= 0);
    check('E25 重复粘贴同图 ⇒ MD 指向同一路径（去重命中）',
      rec.e25.imageRefs.length >= 2 && new Set(rec.e25.imageRefs).size === 1,
      JSON.stringify(rec.e25.imageRefs));

    // 多图（两张互不相同的新图）按顺序插入
    await cdp.evalJS(`(function(){
      var mk=function(b64,name){var b=Uint8Array.from(atob(b64),function(c){return c.charCodeAt(0);});return new File([b],name,{type:'image/png'});};
      var dt=new DataTransfer();
      dt.items.add(mk('${PNG_MULTI_A}','multi-a.png'));
      dt.items.add(mk('${PNG_MULTI_B}','multi-b.png'));
      dt.setData('text/plain','');
      var target=document.querySelector('#editor .-line-content'); target.focus();
      var sel=window.getSelection(), r=document.createRange(), n=target.firstChild;
      if(n) r.setStart(n,n.nodeType===3?n.textContent.length:0); else r.setStart(target,0);
      r.collapse(true); sel.removeAllRanges(); sel.addRange(r);
      target.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
      return true;
    })()`);
    await sleep(2500);
    const afterMulti = await cdp.evalJS('(function(){return {text: window.MemoriaApp.surface.collectText(), status: (document.querySelector("#status-info")||{}).textContent || ""};})()');
    rec.e25.afterMultiPaste = afterMulti;
    rec.e25.multiRefs = afterMulti.text.split('\n').filter((l) => /multi-a\.png|multi-b\.png/.test(l));
    check('E25 多图按顺序各插入一行',
      rec.e25.multiRefs.length === 2 &&
      rec.e25.multiRefs[0].indexOf('multi-a.png') >= 0 && rec.e25.multiRefs[1].indexOf('multi-b.png') >= 0,
      JSON.stringify(rec.e25.multiRefs));

    // 失败必须显式显示：扩展名不是图片（.txt）⇒ 后端拒绝，前端状态栏报错
    await cdp.evalJS(`(function(){
      var dt=new DataTransfer();
      var b=Uint8Array.from(atob('${PNG_MULTI_B}'),function(c){return c.charCodeAt(0);});
      dt.items.add(new File([b],'not-image.txt',{type:'image/png'}));
      dt.setData('text/plain','');
      var target=document.querySelector('#editor .-line-content'); target.focus();
      target.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));
      return true;
    })()`);
    await sleep(1800);
    const afterFail = await cdp.evalJS('(function(){return {status: (document.querySelector("#status-info")||{}).textContent || "", cls: (document.querySelector("#status-info")||{}).className || ""};})()');
    rec.e25.failure = afterFail;
    check('E25 失败显式可见（不假装成功）',
      /图片入库失败|不支持的图片格式/.test(afterFail.status), JSON.stringify(afterFail));

    rec.e25.screenshot = await shot(`e25-${phase}-after-paste`);

    // 撤销栈：Ctrl+Z 应能撤回最后一次粘贴
    const beforeUndo = await cdp.evalJS('(function(){return window.MemoriaApp.surface.collectText();})()');
    await cdp.evalJS('(function(){var c=document.querySelector("#editor .-line-content"); if(c)c.focus(); return true;})()');
    const mod = 2; // ctrl
    await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90, modifiers: mod });
    await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'z', code: 'KeyZ', windowsVirtualKeyCode: 90, nativeVirtualKeyCode: 90, modifiers: mod });
    await sleep(800);
    const afterUndo = await cdp.evalJS('(function(){return window.MemoriaApp.surface.collectText();})()');
    rec.e25.undo = { changed: beforeUndo !== afterUndo, beforeLines: beforeUndo.split('\n').length, afterLines: afterUndo.split('\n').length };
    check('E25 粘贴可 Ctrl+Z 撤销', beforeUndo !== afterUndo, JSON.stringify(rec.e25.undo));

    rec.finishedAt = new Date().toISOString();
    if (phase === 'after') {
      rec.ok = rec.checks.every((c) => c.ok);
    } else {
      // 修前：证据要证明"缺陷存在"（回车不跟随 / 图片被吞），而不是证明修后行为
      const lastAfter = rec.e26.last || {};
      rec.before = {
        e26_enter_never_scrolls: (rec.e26.followSteps || []).every((s) => s.scrollTop === 0),
        e26_caret_left_offscreen: lastAfter.caretTop > lastAfter.paneBottom,
        e25_image_swallowed: (rec.e25.insertedLinesFirst || []).length === 0,
        e25_paste_default_prevented: !!(rec.e25.pasteInfo && rec.e25.pasteInfo.defaultPrevented),
      };
      rec.ok = rec.before.e26_enter_never_scrolls && rec.before.e26_caret_left_offscreen &&
        rec.before.e25_image_swallowed && rec.before.e25_paste_default_prevented;
    }
  } catch (e) {
    rec.error = String((e && e.stack) || e);
    rec.ok = false;
  } finally {
    cdp.close();
    edge.cleanup();
  }
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(rec, null, 2), 'utf8');
  process.stdout.write('__E2526_JSON__' + JSON.stringify({ ok: rec.ok, out: path.resolve(outPath), phase, checks: rec.checks }) + '\n');
  process.exit(rec.ok ? 0 : 1);
}

main().catch((e) => { process.stderr.write(String((e && e.stack) || e) + '\n'); process.exit(1); });
