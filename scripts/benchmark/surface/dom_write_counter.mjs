#!/usr/bin/env node
/**
 * dom_write_counter.mjs —— 每键 DOM 写入计数器（页面内 instrumentation）
 *
 * 为什么需要它：阶段 1 引入 `BlockIndex.upsert()`，预期它会在每次按键时**多若干次 DOM 属性写**。
 * Lead 的硬闸是「阶段 1 后打字不得变慢」。但只看时延无法归因 —— 时延变了不知道是不是 DOM 写多了。
 * 本计数器给出**可归因的中间量**：每键写了几次、其中多少是 attributes、时延多少（三元组）。
 *
 * ── 为什么同时用两种机制（这是本文件最重要的设计决定）─────────────────────
 *   M1 **hook `Element.prototype.setAttribute` / `removeAttribute` / `classList.*` / `dataset` / `style`**
 *      —— 计「**调用次数**」（程序意图写了多少次）。
 *        优点：精确、逐调用可归属到栈帧；能看见「写了但值没变」的冗余写。
 *        缺点：① 只覆盖走这些 API 的写；② 直接改 `innerHTML` / `textContent` / 替换节点
 *              这类"结构性写"不计入；③ hook 本身刷新 IC。
 *   M2 **MutationObserver（`attributes: true` + `childList: true` + `characterData: true`）**
 *      —— 计「**浏览器实际观察到的变更记录数**」。
 *        优点：是**引擎真值**（不依赖是否走某 API）；能抓到 innerHTML 替换等结构性写。
 *        缺点：① 是**异步批处理**，`takeRecords()` 时机不对会漏/串键；
 *              ② 同一 tick 内对同一属性写多次**会被合并**（所以它 ≤ M1 的 attributes 写数）。
 *
 *   ⇒ 两者**不是二选一**：M1 回答"代码想写多少次"，M2 回答"浏览器实际记下多少变更"。
 *     二元组一起看才能区分两种坏情况：
 *       · M1 高、M2 低 ⇒ **冗余写**（写了重复值，浏览器合并掉了）—— 最常见的性能坑；
 *       · M1 低、M2 高 ⇒ **结构性写**（innerHTML/替换节点），M1 看不见的那一类。
 *
 * ── 归属到「键」的办法 ────────────────────────────────────────────────────
 *   每键的写入发生在三次任务里（beforeinput 处理 / insertText 同步段 / 之后的异步重渲）。
 *   本计数器以**本键 `beforeinput` 时刻为窗口起点**、**本键 `insertText` 返回后首次 `takeRecords` + 微任务
 *   落定**为窗口终点，把窗口内的计数记到这一键上。窗口在页面内闭合，不依赖 Node 侧轮询。
 */

/** 安装计数器。返回 {ok, v} 或 {ok:false, reason} */
function INSTALL_DOM_COUNTER() {
  if (window.__domw && window.__domw.vi === 2) return { ok: true, v: 2 };
  var W = window.__domw = { vi: 2, installed: true, keys: [], n: 0, cur: null, hooked: [] };
  var pv = document.getElementById('preview');
  if (!pv) return { ok: false, reason: 'no-preview' };
  var ES = window.MemoriaEditSync;
  if (!ES || typeof ES.insertText !== 'function') return { ok: false, reason: 'no-editsync' };

  function newBucket() {
    return { setAttribute: 0, removeAttribute: 0, classAdd: 0, classRemove: 0, classToggle: 0,
             datasetSet: 0, styleSet: 0, a_attr: 0, a_childList: 0, a_characterData: 0,
             insertMs: null, arriveToReturnMs: null, seq: null };
  }
  function bucket() { return W.cur || null; }
  function bump(k) { var b = bucket(); if (b) b[k]++; }

  // ── M1：hook DOM 写 API ────────────────────────────────────────────────
  var EP = Element.prototype;
  var origSetAttr = EP.setAttribute;
  var origRmAttr = EP.removeAttribute;
  EP.setAttribute = function () { bump('setAttribute'); return origSetAttr.apply(this, arguments); };
  EP.removeAttribute = function () { bump('removeAttribute'); return origRmAttr.apply(this, arguments); };
  W.hooked.push(['setAttribute'], ['removeAttribute']);

  // classList：包 add/remove/toggle（只计"真的改了"的调用）
  var CLP = DOMTokenList.prototype;
  ['add', 'remove', 'toggle'].forEach(function (m) {
    var orig = CLP[m];
    var key = m === 'add' ? 'classAdd' : (m === 'remove' ? 'classRemove' : 'classToggle');
    CLP[m] = function () { bump(key); return orig.apply(this, arguments); };
    W.hooked.push(['classList.' + m]);
  });

  // dataset：不改原型（它是 accessor），改为在 key 上打补丁不可行；
  // 用「MutationObserver 的 attributes」覆盖 dataset 写（dataset 写 = 属性写）。
  // 这里只显式 hook style（CSSStyleDeclaration.setProperty + style.prop= 走同一个 setter）。
  var origSetProp = CSSStyleDeclaration.prototype.setProperty;
  CSSStyleDeclaration.prototype.setProperty = function () { bump('styleSet'); return origSetProp.apply(this, arguments); };
  W.hooked.push(['style.setProperty']);

  // ── M2：MutationObserver 真值 ──────────────────────────────────────────
  // 只观察 #preview 子树（打字改的就是这里）；属性 + 子节点 + 文本。
  var mo = new MutationObserver(function (recs) {
    var b = bucket();
    if (!b) return;
    for (var i = 0; i < recs.length; i++) {
      var r = recs[i];
      if (r.type === 'attributes') b.a_attr++;
      else if (r.type === 'childList') b.a_childList++;
      else if (r.type === 'characterData') b.a_characterData++;
    }
  });
  // !! 必须观察 document.body，不能只观察 #preview：
  //   renderRange 先在离屏新建块、写好属性(data--block-index 等)之后才挂进 #preview。
  //   只观察 #preview 时这些写在“节点还没进观察范围”时发生 => 漏计。
  //   实测(真机 scale-5k, 10 键): 只观察 #preview 时 setAttribute 被调用 14 次，
  //   而 MutationObserver 的 attributes 记录为 0；改成观察 body 后才能对上。
  mo.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
  W.mo = mo;

  // ── 窗口：beforeinput 到达 → insertText 返回 → **本轮异步重渲完成** ────────
  //
  // 实测教训（第一版就是错在这里）：`insertText` 同步段几乎不写 DOM；
  // 真正的写（setAttribute / childList）发生在**之后的异步重渲**里。
  // 若窗口在 `insertText` 返回的微任务里就关闭 ⇒ 每键只记到 M1=1、attributes=0，
  // 而实际每次按键都在重渲。这不是"没有写"，是**窗口太短导致的漏计**。
  //
  // 修正：窗口终点 = 本键 insertText 之后**连续两次 rAF 内没有新的变更记录**（静默判据）。
  //   用 rAF 而不是固定 setTimeout(0)：重渲走的是渲染帧，rAF 与之同相位；
  //   "连续两次无新记录"能覆盖"重渲之后再触发一轮"的情况，同时不会无限等。
  //   上限 SECOND_IDLE_FRAMES 帧，超时则记为 truncated（如实标注，不假装完整）。
  var pendingBeforeInput = null;
  pv.addEventListener('beforeinput', function () { pendingBeforeInput = performance.now(); }, true);

  var IDLE_FRAMES = 3;      // 连续这么多帧没有新记录 ⇒ 认为本键结束
  var MAX_FRAMES = 40;      // 硬上限（约 0.6 s @60fps），防卡死
  function drainInto(b) {
    var recs;
    try { recs = W.mo.takeRecords(); } catch (e) { return 0; }
    for (var i = 0; i < recs.length; i++) {
      var rc = recs[i];
      if (rc.type === 'attributes') b.a_attr++;
      else if (rc.type === 'childList') b.a_childList++;
      else if (rc.type === 'characterData') b.a_characterData++;
    }
    return recs.length;
  }
  function closeWindowWhenIdle(b) {
    var idle = 0, frames = 0;
    function step() {
      frames++;
      var got = drainInto(b);
      if (got > 0) idle = 0; else idle++;
      if (idle >= IDLE_FRAMES || frames >= MAX_FRAMES) {
        b.domSettleMs = +(performance.now() - b.t0).toFixed(2);
        b.truncated = frames >= MAX_FRAMES && idle < IDLE_FRAMES;
        W.keys.push(b);
        if (W._cur === b) W._cur = null;   // 窗口关闭：之后的写不计入本键
        return;
      }
      requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  var origInsert = ES.insertText;
  ES.insertText = function () {
    var t1 = performance.now();
    var arrive = pendingBeforeInput;
    // 上一个窗口若还开着（键很快接键）⇒ 先把它结掉，避免串键
    if (W._cur) { drainInto(W._cur); W.keys.push(W._cur); W._cur = null; }
    var b = newBucket();
    b.t0 = t1;
    W.cur = b; W._cur = b;      // M1 hook 记到这里
    var r = origInsert.apply(this, arguments);
    var t2 = performance.now();
    b.insertMs = +(t2 - t1).toFixed(3);
    b.arriveToReturnMs = arrive != null ? +(t2 - arrive).toFixed(3) : null;
    W.n++;
    b.seq = W.n;
    pendingBeforeInput = null;
    // 同步段的 DOM 写先收一次，再进入"等异步重渲静默"的帧循环
    drainInto(b);
    closeWindowWhenIdle(b);
    return r;
  };
  W.uninstall = function () {
    try { EP.setAttribute = origSetAttr; EP.removeAttribute = origRmAttr; } catch (e) { /* noop */ }
    try { ES.insertText = origInsert; } catch (e) { /* noop */ }
    try { mo.disconnect(); } catch (e) { /* noop */ }
  };
  W.reset = function () { W.keys = []; W.n = 0; W.cur = null; W._cur = null; return true; };
  W.pending = function () { return W._cur ? 1 : 0; };
  W.state = function () {
    return {
      n: W.n,
      pendingWindows: W._cur ? 1 : 0,
      keys: W.keys.map(function (k) {
        return {
          seq: k.seq,
          arriveToReturnMs: k.arriveToReturnMs,
          insertMs: k.insertMs,
          domSettleMs: k.domSettleMs == null ? null : k.domSettleMs,
          truncated: !!k.truncated,
          setAttribute: k.setAttribute, removeAttribute: k.removeAttribute,
          classAdd: k.classAdd, classRemove: k.classRemove, classToggle: k.classToggle,
          styleSet: k.styleSet,
          // M1 合计（API 调用次数）
          m1Calls: k.setAttribute + k.removeAttribute + k.classAdd + k.classRemove + k.classToggle + k.styleSet,
          // M2 合计（观察到的变更记录数）
          m2Records: k.a_attr + k.a_childList + k.a_characterData,
          m2: { attr: k.a_attr, childList: k.a_childList, characterData: k.a_characterData }
        };
      })
    };
  };
  W.hookedList = function () { return W.hooked.map(function (h) { return h[0]; }); };
  return { ok: true, v: 2 };
}

// 同时导出（供 Node 侧 import 时复用同一份源码字符串）
export { INSTALL_DOM_COUNTER };
