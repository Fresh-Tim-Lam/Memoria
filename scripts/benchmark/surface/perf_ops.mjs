#!/usr/bin/env node
/**
 * perf_ops.mjs —— 绩效操作覆盖矩阵（页面内探针 + 场景驱动）
 *
 * 缺口（人指出，已犯过两次同类错误）：性能指标只覆盖 3 个操作（打字/首开/切页签），
 *   滚动/框选/粘贴/撤销/查找/保存/视图切换/结构编辑/样式画笔/KP/内存增长等**全无指标**。
 *   阶段 2 换管线后这些退化了也看不见。
 *
 * 设计：每个操作 = { id, tier, mode, metric, run(page) }。
 *   tier: 'A'（用户直接感知，必测）/ 'B'（记录）
 *   mode: 'headless-ok'（纯交互，可无头）/ 'realapp-required'（公式/首开，必须真机）
 *   度量一律用页面内 performance.now()，与输入来源无关。
 *
 * ⚠️ 滚动指标（Lead 特别要求）：不用"滚完耗时"（那会随文档长度线性增长、掩盖卡顿），
 *   而用**连续滚动期间的帧间隔 p95 + 长任务数** —— 窗口化边界跨越最易被打坏，
 *   也最易被用户感知为"卡"。帧间隔由 rAF 采样得到。
 *
 * 本文件是自包含页面内探针源（注入字符串）+ 数据表；CLI 见 run_perf_ops.py 调起的部分。
 */

// ─────────────────────────────────────────────────────────────────────────────
// 页面内探针（注入后求值）：提供 window.__perfops
// ─────────────────────────────────────────────────────────────────────────────
export const PERF_PROBE = `(function () {
  'use strict';
  var PO = {};

  function now() { return performance.now(); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // ── 通用：两帧之间等渲染落定 ──
  function nextFrame() { return new Promise(function (r) { requestAnimationFrame(function () { r(); }); }); }
  async function settle(frames) {
    frames = frames || 2;
    for (var i = 0; i < frames; i++) await nextFrame();
  }

  // ── 长任务观测（PerformanceObserver longtask）──
  PO.longTasks = { supported: false, entries: [] };
  try {
    if (typeof PerformanceObserver !== 'undefined' && PerformanceObserver.supportedEntryTypes &&
        PerformanceObserver.supportedEntryTypes.indexOf('longtask') >= 0) {
      PO.longTasks.supported = true;
      var po = new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (e) { PO.longTasks.entries.push(e.duration); });
      });
      po.observe({ entryTypes: ['longtask'] });
      PO._po = po;
    }
  } catch (e) { /* 不支持则退化为帧间隔判据 */ }
  PO.resetLongTasks = function () { PO.longTasks.entries = []; };

  // ── 帧间隔采样：在 durationMs 内用 rAF 记录每帧间隔 ──
  PO.sampleFrames = function (durationMs) {
    return new Promise(function (resolve) {
      var gaps = [];
      var last = null;
      var t0 = now();
      function tick() {
        var t = now();
        if (last != null) gaps.push(t - last);
        last = t;
        if (t - t0 < durationMs) requestAnimationFrame(tick);
        else resolve(gaps);
      }
      requestAnimationFrame(tick);
    });
  };

  // ═══════════════════════════════════════════════════════════════════════
  // 各操作实现：返回 { samples: [ms...], extra: {...} }
  // ═══════════════════════════════════════════════════════════════════════

  // 打开文档并保证自洽（AST 块数 == DOM 块数）
  PO.openDoc = async function (file, { requirePreview } = {}) {
    window.MemoriaApp.openFile(file, { skipNav: true });
    var t0 = now();
    while (now() - t0 < 60000) {
      if (window.state && window.state.currentPath === file && window.state.doc) break;
      await sleep(80);
    }
    if (requirePreview) {
      var b = document.querySelector('.-view-btn[data-view="preview"]');
      if (b && window.state.viewMode !== 'preview') b.click();
      var t1 = now();
      while (now() - t1 < 20000 && (window.state.viewMode !== 'preview')) await sleep(80);
      var t2 = now();
      while (now() - t2 < 40000 && document.querySelectorAll('#preview .-src-block').length === 0) await sleep(80);
    }
    await sleep(400);
    return { path: window.state.currentPath, blocks: document.querySelectorAll('#preview .-src-block').length };
  };

  function paneScroll() { return document.getElementById('preview-pane'); }
  function editableBlock() {
    var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
    for (var i = 0; i < els.length; i++) {
      var c = String(els[i].className || '');
      if (c.indexOf('-code-block') < 0 && c.indexOf('-table') < 0 && c.indexOf('-math-block') < 0 &&
          c.indexOf('-mermaid') < 0 && c.indexOf('-blank-block') < 0 && c.indexOf('-frontmatter') < 0 &&
          els[i].textContent.trim().length > 4) return els[i];
    }
    return els[0] || null;
  }
  function clickAt(x, y) {
    var el = document.elementFromPoint(x, y);
    if (!el) return false;
    ['mousedown', 'mouseup', 'click'].forEach(function (t) {
      el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window }));
    });
    return true;
  }

  // ── A: 打字（单键时延，复用既有口径）──
  PO.opTyping = async function (ctx) {
    var el = editableBlock();
    if (!el) return { samples: [], error: 'no-editable-block' };
    var r = el.getBoundingClientRect();
    clickAt(r.left + 20, r.top + Math.min(10, r.height / 2));
    await sleep(200);
    var samples = [];
    var keys = ctx.keys || 10, warm = ctx.warmup || 3;
    for (var i = 0; i < warm + keys; i++) {
      var t0 = now();
      var ev = new InputEvent('beforeinput', { inputType: 'insertText', data: 'z', bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      document.execCommand('insertText', false, 'z');
      await nextFrame();
      var dt = now() - t0;
      if (i >= warm) samples.push(dt);
    }
    return { samples: samples };
  };

  // ── A: 滚动（帧间隔 p95 + 长任务；Lead 重点项）──
  PO.opScroll = async function (ctx) {
    var pane = paneScroll();
    if (!pane) return { samples: [], error: 'no-preview-pane' };
    var totalPx = ctx.scrollPx || 2000;
    pane.scrollTop = 0;
    await settle(2);
    PO.resetLongTasks();
    var t0 = now();
    // 边采样帧间隔边连续滚动（模拟真人滚轮，避免一次性跳转掩盖卡顿）
    var frames = [];
    var last = null;
    var step = 40;                 // 每帧滚 40px ≈ 平滑滚动
    var scrolled = 0;
    var stop = false;
    function tick() {
      var t = now();
      if (last != null) frames.push(t - last);
      last = t;
      if (scrolled < totalPx) {
        scrolled += step;
        pane.scrollTop = Math.min(scrolled, pane.scrollHeight - pane.clientHeight);
        requestAnimationFrame(tick);
      } else stop = true;
    }
    requestAnimationFrame(tick);
    var guard = now();
    while (!stop && now() - guard < 15000) await sleep(30);
    var elapsed = now() - t0;
    await settle(2);
    var longTasks = PO.longTasks.entries.slice();
    // 卡顿比例：帧间隔 > 1.5 帧预算（1.5 x 16.7ms = 25ms）的帧占比。
    //   这是用户真正感知的"卡"；单纯 p95 在 vsync 下会被钳在 ~16.7ms，看不出差别。
    var FRAME = 1000 / 60;
    var jankThreshold = FRAME * 1.5;
    var jankFrames = frames.filter(function (g) { return g > jankThreshold; }).length;
    return {
      samples: frames.length ? frames : [],
      extra: {
        frames: frames.length,
        scrolledPx: scrolled,
        elapsedMs: elapsed,
        longTaskCount: longTasks.length,
        longTaskMaxMs: longTasks.length ? Math.max.apply(null, longTasks) : 0,
        longTaskTotalMs: longTasks.reduce(function (a, b) { return a + b; }, 0),
        jankFrames: jankFrames,
        jankRatio: frames.length ? +(jankFrames / frames.length).toFixed(4) : null,
        jankThresholdMs: +jankThreshold.toFixed(1),
      },
    };
  };

  // ── A: 框选（跨块拖选）──
  PO.opSelect = async function (ctx) {
    var pane = paneScroll();
    var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
    if (els.length < 3) return { samples: [], error: 'not-enough-blocks' };
    var samples = [];
    var rounds = ctx.rounds || 5;
    for (var k = 0; k < rounds; k++) {
      var a = els[1].getBoundingClientRect();
      var b = els[Math.min(els.length - 1, 4)].getBoundingClientRect();
      var t0 = now();
      var sel = window.getSelection();
      sel.removeAllRanges();
      var range = document.createRange();
      try {
        range.setStart(els[1], 0);
        range.setEnd(els[Math.min(els.length - 1, 4)], Math.min(3, (els[Math.min(els.length - 1, 4)].childNodes.length) || 1));
      } catch (e) { /* 跨块 selection 失败则退化为 selectNodeContents */ }
      sel.addRange(range);
      // 触发应用的 selectionchange → 高亮更新
      document.dispatchEvent(new Event('selectionchange', { bubbles: true }));
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
    }
    return { samples: samples };
  };

  // ── A: 粘贴（短文本多轮 / 一次性大文本）──
  PO.opPaste = async function (ctx) {
    var el = editableBlock();
    if (!el) return { samples: [], error: 'no-editable-block' };
    var r = el.getBoundingClientRect();
    clickAt(r.left + 20, r.top + Math.min(10, r.height / 2));
    await sleep(200);
    var text = ctx.pasteText || 'paste-bench-text';
    var samples = [];
    var rounds = ctx.rounds || 5;
    for (var i = 0; i < rounds; i++) {
      var t0 = now();
      var dt = new DataTransfer();
      dt.setData('text/plain', text);
      var ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
      el.dispatchEvent(ev);
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
    }
    return { samples: samples };
  };

  // ── A: 撤销 / 重做 ──
  PO.opUndo = async function (ctx) {
    var el = editableBlock();
    if (!el) return { samples: [], error: 'no-editable-block' };
    var r = el.getBoundingClientRect();
    clickAt(r.left + 20, r.top + Math.min(10, r.height / 2));
    await sleep(200);
    var samples = [];
    var rounds = ctx.rounds || 5;
    for (var i = 0; i < rounds; i++) {
      // 先制造一次可撤销的编辑
      document.execCommand('insertText', false, 'x');
      await nextFrame();
      var t0 = now();
      document.execCommand('undo');
      // 应用自己的 Ctrl+Z 监听（app.js:7263）
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true, cancelable: true }));
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
    }
    return { samples: samples };
  };

  // ── A: 查找（工具栏搜索框输入 → 结果面板）──
  PO.opFind = async function (ctx) {
    var input = document.getElementById('toolbar-search');
    var panel = document.getElementById('toolbar-search-panel');
    if (!input) return { samples: [], error: 'no-toolbar-search' };
    var samples = [];
    var terms = ctx.terms || ['e', 't', 'a', 's', 'i'];
    for (var i = 0; i < terms.length; i++) {
      var t0 = now();
      input.value = terms[i];
      input.dispatchEvent(new Event('input', { bubbles: true }));
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
    }
    return { samples: samples, extra: { panelVisible: panel ? !panel.classList.contains('hidden') : null } };
  };

  // ── A: 保存（应用保存入口；按 Esc 退出编辑后触发）──
  PO.opSave = async function (ctx) {
    var samples = [];
    var rounds = ctx.rounds || 5;
    for (var i = 0; i < rounds; i++) {
      var t0 = now();
      if (window.MemoriaApp && typeof window.MemoriaApp.save === 'function') {
        try { await window.MemoriaApp.save(); } catch (e) { /* 忽略 */ }
      } else {
        // 退化：走 Ctrl+S 真实按键路径
        var pane = document.getElementById('preview');
        if (pane) pane.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true, bubbles: true, cancelable: true }));
      }
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
    }
    return { samples: samples };
  };

  // ── A: 视图切换（source → preview → split 往返）──
  PO.opViewSwitch = async function (ctx) {
    var modes = ['preview', 'source', 'split'];
    var samples = [];
    var rounds = ctx.rounds || 3;
    for (var i = 0; i < rounds; i++) {
      for (var m = 0; m < modes.length; m++) {
        var btn = document.querySelector('.-view-btn[data-view="' + modes[m] + '"]');
        if (!btn) continue;
        var t0 = now();
        btn.click();
        var t1 = now();
        while (now() - t1 < 8000 && window.state.viewMode !== modes[m]) await sleep(20);
        await nextFrame(); await nextFrame();
        samples.push(now() - t0);
      }
    }
    return { samples: samples };
  };

  // ── A: 结构编辑（回车拆段 / 合并）──
  PO.opStructEdit = async function (ctx) {
    var el = editableBlock();
    if (!el) return { samples: [], error: 'no-editable-block' };
    var r = el.getBoundingClientRect();
    clickAt(r.left + 30, r.top + Math.min(10, r.height / 2));
    await sleep(200);
    var samples = [];
    var rounds = ctx.rounds || 4;
    for (var i = 0; i < rounds; i++) {
      var t0 = now();
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
      await sleep(120);
      // 合并回去（退格）
      var t1 = now();
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true, cancelable: true }));
      await nextFrame(); await nextFrame();
      samples.push(now() - t1);
      await sleep(120);
    }
    return { samples: samples };
  };

  // ── A: 样式画笔（点 bold 按钮切换 + 涂抹）──
  PO.opFormat = async function (ctx) {
    var btn = document.querySelector('.-fmt-btn[data-fmt="bold"]');
    if (!btn) return { samples: [], error: 'no-fmt-btn' };
    var el = editableBlock();
    if (!el) return { samples: [], error: 'no-editable-block' };
    var r = el.getBoundingClientRect();
    clickAt(r.left + 20, r.top + Math.min(10, r.height / 2));
    await sleep(150);
    var samples = [];
    var rounds = ctx.rounds || 5;
    for (var i = 0; i < rounds; i++) {
      var t0 = now();
      btn.click();
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
    }
    return { samples: samples };
  };

  // ── A: KP 悬停（列表项 hover → 区间高亮）──
  PO.opKpHover = async function (ctx) {
    var item = document.querySelector('#kp-list .-kp-item');
    if (!item) return { samples: [], error: 'no-kp-item' };
    var samples = [];
    var rounds = ctx.rounds || 5;
    for (var i = 0; i < rounds; i++) {
      var r = item.getBoundingClientRect();
      var t0 = now();
      item.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, clientX: r.left + 5, clientY: r.top + 5 }));
      await nextFrame(); await nextFrame();
      samples.push(now() - t0);
      item.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }));
      await nextFrame();
    }
    return { samples: samples };
  };

  // ── A: 首开（openFile → 块就绪 + 公式落定；真机才有意义）──
  PO.opOpen = async function (ctx) {
    var file = ctx.openFile || 'scale/scale-5k.md';
    var samples = [];
    var rounds = ctx.rounds || 3;
    for (var i = 0; i < rounds; i++) {
      // 先切走，保证每次都是"首开"
      await PO.openDoc('corpus/01-ime-zh.md', {});
      var t0 = now();
      window.MemoriaApp.openFile(file, { skipNav: true });
      var t1 = now();
      while (now() - t1 < 60000) {
        var ok = window.state && window.state.currentPath === file && window.state.doc;
        var blocks = document.querySelectorAll('#preview .-src-block').length;
        if (ok && blocks >= (ctx.minBlocks || 5)) break;
        await sleep(30);
      }
      // 等公式落定（真机才排得完）
      var mp = window.state && window.state._mathPending;
      if (mp && typeof mp.then === 'function') { try { await mp; } catch (e) {} }
      await settle(3);
      samples.push(now() - t0);
      await sleep(200);
    }
    return { samples: samples, extra: { blocks: document.querySelectorAll('#preview .-src-block').length } };
  };

  // ── A: 切页签（文件间切换）──
  PO.opTabSwitch = async function (ctx) {
    var files = ctx.tabFiles || ['corpus/01-ime-zh.md', 'corpus/02-inline-edges.md'];
    var samples = [];
    var rounds = ctx.rounds || 4;
    for (var i = 0; i < rounds; i++) {
      var f = files[i % files.length];
      var t0 = now();
      window.MemoriaApp.openFile(f, { skipNav: true });
      var t1 = now();
      while (now() - t1 < 30000) {
        if (window.state.currentPath === f && window.state.doc && document.querySelectorAll('#preview .-src-block').length > 0) break;
        await sleep(20);
      }
      await settle(2);
      samples.push(now() - t0);
      await sleep(120);
    }
    return { samples: samples };
  };

  // ── B: 长会话内存增长（反复切页签 N 次后 heap delta）──
  PO.opMemGrowth = async function (ctx) {
    if (!performance.memory) return { samples: [], extra: { supported: false } };
    var files = ctx.tabFiles || ['corpus/01-ime-zh.md', 'corpus/02-inline-edges.md'];
    var cycles = ctx.cycles || 12;
    var before = performance.memory.usedJSHeapSize;
    for (var i = 0; i < cycles; i++) {
      window.MemoriaApp.openFile(files[i % files.length], { skipNav: true });
      var t1 = now();
      while (now() - t1 < 20000) {
        if (window.state.currentPath === files[i % files.length] && window.state.doc) break;
        await sleep(30);
      }
      await settle(2);
    }
    // 给 GC 一个机会（无法强制，只能等待）
    await sleep(800);
    var after = performance.memory.usedJSHeapSize;
    return {
      samples: [],
      extra: {
        supported: true,
        heapBeforeMB: +(before / 1048576).toFixed(2),
        heapAfterMB: +(after / 1048576).toFixed(2),
        heapDeltaMB: +((after - before) / 1048576).toFixed(2),
        cycles: cycles,
      },
    };
  };

  return PO;
})()`;
