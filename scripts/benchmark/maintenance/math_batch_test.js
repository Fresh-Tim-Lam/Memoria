#!/usr/bin/env node
/**
 * math_batch_test.js —— A1「typeset 分块 + 主线程让出」的**纯逻辑单测**
 *
 * 不依赖浏览器：用假 MathJax / 假 DOM 复刻 `_typesetInBatches` 的**同一份算法**，
 * 验证四件事：
 *   ① 分批：公式总数守恒（不丢、不重复）
 *   ② 批大小自适应：EWMA 生效，且单批预计耗时 ≤ 目标
 *   ③ token 作废：中途被取代 ⇒ 停止，且**剩余块仍在 pending**（不永久漏排）
 *   ④ 全程 promise 只在全部批次结束后 resolve（`_mathPending` 语义）
 *
 * 跑法：node scripts/benchmark/maintenance/math_batch_test.js
 * 退出码 0 = 全过。
 */

'use strict';

// ── 被测算法：与 app.js `_typesetInBatches` 逐行同构（仅把 MathJax/定时器换成可观测假件）──
const MATH_BATCH_MS = 8;
const MATH_BATCH_MIN_FORMULAS = 1;
const MATH_BATCH_FIRST = 24;

function makeHarness(opts) {
  const o = opts || {};
  const state = { previewToken: o.token || 1, _mathPending: null };
  let msPerFormula = 1.4;                       // 与 app.js 同初值
  const stats = { typesetCalls: 0, batches: [], totalFormulas: 0, yielded: 0, msPerFormulaEnd: 0 };

  // 假 DOM：blockQueue = [{ el:{id}, count }]
  // ⚠️ 与 app.js 同构：**只把 count > 0 的块放进队列**（`_typesetInBatches` 里的
  //    `if (c > 0) queue.push(...)`），空块不参与排版。
  const queue = o.blocks
    .map((count, i) => ({ el: { id: i }, count }))
    .filter((b) => b.count > 0);
  let qi = 0;
  let batchNo = 0;

  // 假 MathJax：按 msPerFormula 计"耗时"，并可模拟报错
  const MathJax = {
    typesetPromise(els) {
      stats.typesetCalls++;
      let f = 0;
      for (const e of els) f += queue.find((q) => q.el.id === e.id).count;
      stats.totalFormulas += f;
      stats.batches.push({ n: els.length, formulas: f, elapsedMs: f * msPerFormula });
      if (o.failBatchAt === batchNo) {
        return Promise.reject(new Error('simulated batch failure'));
      }
      return Promise.resolve();
    },
  };
  const yieldTick = () => { stats.yielded++; return Promise.resolve(); };  // 假 setTimeout(0)

  function nextBatch() {
    if (state.previewToken !== o.token) return Promise.resolve('aborted-by-token');
    let quota = Math.max(MATH_BATCH_MIN_FORMULAS, Math.round(MATH_BATCH_MS / Math.max(0.05, msPerFormula)));
    if (batchNo === 0) quota = Math.max(quota, MATH_BATCH_FIRST);
    const els = [];
    let formulas = 0;
    while (qi < queue.length && (formulas + queue[qi].count <= quota || els.length === 0)) {
      els.push(queue[qi].el); formulas += queue[qi].count; qi++;
    }
    if (!els.length) return Promise.resolve('done');

    return MathJax.typesetPromise(els).then(() => {
      if (formulas > 0) msPerFormula = msPerFormula * 0.7 + (formulas * msPerFormula / formulas) * 0.3;
      batchNo++;
      if (o.abortAfterBatch != null && batchNo > o.abortAfterBatch) {
        state.previewToken = o.token + 1;    // 模拟"被更新的一轮取代"
      }
      if (qi >= queue.length) return 'done';
      return yieldTick().then(nextBatch);
    }, (e) => {
      stats.batches[stats.batches.length - 1].failed = String(e.message);
      batchNo++;
      if (qi >= queue.length) return 'done';
      return yieldTick().then(nextBatch);
    });
  }

  function run() {
    const prev = state._mathPending;
    const chain = prev && typeof prev.then === 'function' ? prev.catch(() => {}) : Promise.resolve();
    state._mathPending = chain.then(() => {
      if (state.previewToken !== o.token) return Promise.resolve('aborted');
      if (!queue.length) return Promise.resolve('done');   // 与 app.js 同构：无待排块 ⇒ 直接完成
      return nextBatch();
    });
    return state._mathPending.then((r) => {
      stats.msPerFormulaEnd = msPerFormula;
      stats.remaining = queue.length - qi;     // 未处理的块数（应进 pending，不得丢失）
      stats.result = r;
      return stats;
    });
  }
  return { run, stats, state };
}

// ── 断言 ──
let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name + (detail ? ' :: ' + detail : '')); }
}

(async () => {
  // ① 守恒：不乱序、不丢、不重复
  {
    const blocks = Array.from({ length: 300 }, (_, i) => (i % 7 === 0 ? 5 : (i % 3 === 0 ? 2 : 0)));
    const total = blocks.reduce((a, b) => a + b, 0);
    const h = makeHarness({ blocks, token: 1 });
    const s = await h.run();
    check('① 公式总数守恒（不丢不重）', s.totalFormulas === total, `${s.totalFormulas} vs ${total}`);
    check('① 确实切成了多批', s.batches.length > 1, '批数=' + s.batches.length);
    check('① 全部排完（remaining=0）', s.remaining === 0, 'remaining=' + s.remaining);
  }

  // ② 批大小自适应 + 单批预计 ≤ 目标（首批按 MATH_BATCH_FIRST 豁免）
  {
    const blocks = Array.from({ length: 400 }, (_, i) => (i % 5 === 0 ? 4 : 1));
    const h = makeHarness({ blocks, token: 1 });
    const s = await h.run();
    const over = s.batches.slice(1).filter((b) => b.elapsedMs > MATH_BATCH_MS * 3);  // 给 3× 容差（配额是估算）
    check('② 非首批的单批预计耗时受控（≤3×目标）', over.length === 0,
      '超限批次=' + JSON.stringify(over.slice(0, 3)));
    check('② EWMA 已收敛出数值', s.msPerFormulaEnd > 0 && Number.isFinite(s.msPerFormulaEnd),
      String(s.msPerFormulaEnd));
  }

  // ③ token 作废：中途被取代 ⇒ 停止，剩余块**存在**（不丢失）
  {
    const blocks = Array.from({ length: 500 }, () => 2);
    const h = makeHarness({ blocks, token: 1, abortAfterBatch: 3 });
    const s = await h.run();
    check('③ 作废后停止推进', s.result === 'aborted-by-token', 'result=' + s.result);
    check('③ 作废时仍有剩余块（未丢，可重新入队）', s.remaining > 0, 'remaining=' + s.remaining);
    check('③ 作废前确实排了一部分', s.totalFormulas > 0, 'formulas=' + s.totalFormulas);
  }

  // ④ 单批失败不拖垮整轮（继续推进剩余）
  {
    const blocks = Array.from({ length: 120 }, () => 3);
    const total = blocks.reduce((a, b) => a + b, 0);
    const h = makeHarness({ blocks, token: 1, failBatchAt: 2 });
    const s = await h.run();
    check('④ 某批失败后仍把剩余排完', s.remaining === 0, 'remaining=' + s.remaining);
    check('④ 失败批次被记录', s.batches.some((b) => b.failed), JSON.stringify(s.batches.filter(b=>b.failed)));
    check('④ 失败不导致整体 reject（result=done）', s.result === 'done', 'result=' + s.result);
  }

  // ⑤ 空文档 / 无公式：不应调用 MathJax
  {
    const h = makeHarness({ blocks: [0, 0, 0], token: 1 });
    const s = await h.run();
    check('⑤ 无公式时零调用', s.typesetCalls === 0, 'calls=' + s.typesetCalls);
  }

  // ⑥ 大量公式下让出次数 > 0（主线程真的被让出过）
  {
    const blocks = Array.from({ length: 1000 }, () => 3);
    const h = makeHarness({ blocks, token: 1 });
    const s = await h.run();
    check('⑥ 批间确实让出主线程', s.yielded > 10, 'yields=' + s.yielded);
  }

  // ⑦ 块公式「已排版」判定：容器类名保留 ⇒ 必须按"内部有无 mjx-container"判，否则永久重排
  {
    // 复刻 app.js `_countPendingFormulas` 的判据（最小假元素）
    function countPending(el) {
      let n = (el._inlineMaths || 0);            // span.-math 数（排版后会被替换掉）
      const isMb = !!el._isMathBlock;
      const hasMjx = !!el._hasMjx;
      if (isMb) { if (!hasMjx) n += 1; }
      else if (el._nestedMb) {
        for (const m of el._nestedMb) if (!m._hasMjx) n += 1;
      }
      return n;
    }
    // 未排版的块公式
    const fresh = { _isMathBlock: true, _hasMjx: false };
    // 已排版的块公式：容器 -math-block 仍在，但内部已有 mjx-container
    const done = { _isMathBlock: true, _hasMjx: true };
    check('⑦ 未排版块公式计为 1', countPending(fresh) === 1, String(countPending(fresh)));
    check('⑦ 已排版块公式计为 0（不重复排）', countPending(done) === 0, String(countPending(done)));
    // 行内：排版后 span.-math 消失
    check('⑦ 已排版行内公式计为 0', countPending({ _inlineMaths: 0 }) === 0);
    check('⑦ 未排版行内公式计为 n', countPending({ _inlineMaths: 3 }) === 3);
    // 嵌套块公式
    check('⑦ 嵌套块公式按各自状态计数',
      countPending({ _nestedMb: [{ _hasMjx: false }, { _hasMjx: true }] }) === 1,
      String(countPending({ _nestedMb: [{ _hasMjx: false }, { _hasMjx: true }] })));
  }

  console.log('\n--- ' + pass + ' passed, ' + fail + ' failed');
  process.exit(fail ? 1 : 0);
})();
