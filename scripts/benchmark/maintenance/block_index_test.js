#!/usr/bin/env node
/* MemoriaBlockIndex 单测：UMD 双出口 + 块身份 + 块↔源行区间 契约断言。
   用法：node scripts/benchmark/maintenance/block_index_test.js
   覆盖：A1–A12（对应 block-identity-build-plan.md P1 断言清单）。 */
"use strict";
const path = require("path");

const MOD = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "block-index.js");

let failures = 0;
let passes = 0;
function check(name, cond, extra) {
  if (cond) { passes++; console.log("PASS  " + name); }
  else { failures++; console.log("FAIL  " + name + (extra !== undefined ? "  " + JSON.stringify(extra) : "")); }
}

// ── UMD 双出口（A0，先证 require 这条路通）───────────────────────────────
let BlockIndex, hashBlockId;
try {
  const m = require(MOD);
  BlockIndex = m.BlockIndex;
  hashBlockId = m.hashBlockId;
  check("A0-UMD  require 返回对象", typeof m === "object" && m !== null);
  check("A0-UMD  BlockIndex 是函数", typeof BlockIndex === "function");
  check("A0-UMD  hashBlockId 是函数", typeof hashBlockId === "function");
} catch (e) {
  check("A0-UMD  require 成功", false, e.message);
  console.error("UMD 加载失败，中止：" + e.message);
  process.exit(1);
}

// ── 工具：造一个确定性文档的块集合，返回 {bi, handles} ──────────────────
function makeDoc(blocksSpec) {
  // blocksSpec: [{kind, srcLineStart, srcLineEnd, text}]（1-based 闭区间）
  const bi = BlockIndex();
  bi.beginStamp();
  const handles = [];
  for (const b of blocksSpec) {
    handles.push(bi.upsert({
      kind: b.kind, srcLineStart: b.srcLineStart, srcLineEnd: b.srcLineEnd,
      blockSrcText: b.text != null ? b.text : ("line" + b.srcLineStart),
    }));
  }
  bi.commit();
  return { bi, handles };
}

// =========================================================================
// A1 同文本同类型 ⇒ 同 id（I3）
(function () {
  const a = hashBlockId("paragraph", "hello", 0);
  const b = hashBlockId("paragraph", "hello", 0);
  check("A1  同文本同类型同序 ⇒ 同 id", a === b);
})();

// A3 同 hash 出现序消歧
(function () {
  const a = hashBlockId("paragraph", "same", 0);
  const b = hashBlockId("paragraph", "same", 1);
  check("A3  同 hash 出现序 0/1 不同", a !== b);
})();

// A12 纯函数性（两次调用同 id）
(function () {
  const a1 = hashBlockId("list", "- x", 2);
  const a2 = hashBlockId("list", "- x", 2);
  check("A12 纯函数：两次调用同 id", a1 === a2);
})();

// A2 改一块 ⇒ 其余块 id 全不变（C1）
(function () {
  const { bi, handles } = makeDoc([
    { kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, text: "aaa" },
    { kind: "paragraph", srcLineStart: 2, srcLineEnd: 2, text: "bbb" },
    { kind: "list",     srcLineStart: 3, srcLineEnd: 5, text: "- a\n- b" },
    { kind: "paragraph", srcLineStart: 6, srcLineEnd: 6, text: "ddd" },
  ]);
  const before = handles.map(h => h.id);

  // 改第 2 块（index 1）的文本 ⇒ 该块 id 应变；其余 id 不变
  const bi2 = BlockIndex();
  bi2.beginStamp();
  bi2.upsert({ kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, blockSrcText: "aaa" });
  bi2.upsert({ kind: "paragraph", srcLineStart: 2, srcLineEnd: 2, blockSrcText: "bbb-CHANGED" });
  bi2.upsert({ kind: "list",     srcLineStart: 3, srcLineEnd: 5, blockSrcText: "- a\n- b" });
  bi2.upsert({ kind: "paragraph", srcLineStart: 6, srcLineEnd: 6, blockSrcText: "ddd" });
  bi2.commit();
  const after = bi2.blocks().map(h => h.id);

  const changed = after[1] !== before[1];
  const othersSame = before[0] === after[0] && before[2] === after[2] && before[3] === after[3];
  check("A2  改一块 ⇒ 该块 id 变", changed);
  check("A2  改一块 ⇒ 其余块 id 全不变（C1）", othersSame);
})();

// A4 blocksInRange 与朴素 filter 在 200 组随机区间上逐条一致
(function () {
  // 确定性伪随机（LCG，避免依赖 Math.random 且在两次运行间可复现）
  let seed = 20261020;
  function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }

  // 造 300 块：srcLineStart 递增、每块 1–3 行、kind 轮换
  const bi = BlockIndex();
  bi.beginStamp();
  const kinds = ["paragraph", "list", "heading", "code_block", "table"];
  let line = 1;
  const spec = [];
  for (let i = 0; i < 300; i++) {
    const len = 1 + Math.floor(rnd() * 3);   // 1..3 行
    const s = line, e = line + len - 1;
    bi.upsert({ kind: kinds[i % kinds.length], srcLineStart: s, srcLineEnd: e, blockSrcText: "blk" + i });
    spec.push({ start: s, end: e });
    line += len;
  }
  bi.commit();
  const totalLines = line - 1;
  const handles = bi.blocks();

  let mismatches = 0;
  for (let t = 0; t < 200; t++) {
    const a = 1 + Math.floor(rnd() * totalLines);
    const b = 1 + Math.floor(rnd() * totalLines);
    const start = Math.min(a, b), end = Math.max(a, b);

    // 朴素 filter（定义即真值）
    const naive = handles.filter(h => h.srcLineStart <= end && h.srcLineEnd >= start).map(h => h.id);
    const fast = bi.blocksInRange(start, end).map(h => h.id);

    if (naive.length !== fast.length) { mismatches++; continue; }
    for (let k = 0; k < naive.length; k++) if (naive[k] !== fast[k]) { mismatches++; break; }
  }
  check("A4  blocksInRange 与朴素 filter 200 组一致", mismatches === 0, { mismatches });
})();

// A5 一行被多块覆盖 ⇒ 回多个；outermost 只回最外层
(function () {
  const { bi } = makeDoc([
    { kind: "list", srcLineStart: 1, srcLineEnd: 6, text: "- outer\n  - inner" },   // 外层列表覆盖 1..6
    { kind: "list", srcLineStart: 3, srcLineEnd: 4, text: "  - nested" },          // 内层列表覆盖 3..4
  ]);
  const all = bi.atSrcLine(4);
  check("A5  一行多块覆盖 ⇒ 回多个", all.length === 2);
  const outer = bi.atSrcLine(4, { outermost: true });
  check("A5  outermost 只回最外层（start 最小）", outer.length === 1 && outer[0].srcLineStart === 1);
})();

// A6 upsert 后 get 立即可见新行区间
(function () {
  const bi = BlockIndex();
  bi.beginStamp();
  const h = bi.upsert({ kind: "paragraph", srcLineStart: 5, srcLineEnd: 7, blockSrcText: "x" });
  bi.commit();
  const got = bi.get(h.id);
  check("A6  upsert 后 get 可见", !!got && got.srcLineStart === 5 && got.srcLineEnd === 7);
})();

// A7 行数不变 ⇒ startsValid 保持 true（打字路径不重建，性能闸前提）
(function () {
  const bi = BlockIndex();
  bi.beginStamp();
  bi.upsert({ id: "b-1", kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, blockSrcText: "one" });
  bi.upsert({ id: "b-2", kind: "paragraph", srcLineStart: 2, srcLineEnd: 2, blockSrcText: "two" });
  bi.commit();
  // 首次 build 后前缀待重算（_touched）⇒ 先触发一次查询结算到 true
  bi.blocksInRange(1, 2);
  check("A7  结算后 startsValid=true", bi._diagnose().startsValid === true);

  // 行数不变的编辑（打字，区间长度同为 1）：同 id、改文本，区间仍 1..1
  bi.beginStamp();
  bi.upsert({ id: "b-1", kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, blockSrcText: "one-EDIT" });  // 行数没变
  bi.commit();
  check("A7  行数不变 ⇒ startsValid 保持 true", bi._diagnose().startsValid === true);
})();

// A8 行数变 ⇒ startsValid=false（懒失效），重构后结果正确
(function () {
  const bi = BlockIndex();
  bi.beginStamp();
  bi.upsert({ id: "blk-1", kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, blockSrcText: "one" });
  bi.upsert({ id: "blk-2", kind: "paragraph", srcLineStart: 2, srcLineEnd: 2, blockSrcText: "two" });
  bi.commit();
  bi.blocksInRange(1, 2);   // 结算前缀到 true
  check("A8  行数变前 startsValid=true", bi._diagnose().startsValid === true);

  bi.beginStamp();
  // 同一 id、同一文本，但行区间从 1 行变 3 行（映射变化，非文本变化）
  bi.upsert({ id: "blk-1", kind: "paragraph", srcLineStart: 1, srcLineEnd: 3, blockSrcText: "one" });
  bi.commit();
  check("A8  行数变 ⇒ startsValid=false", bi._diagnose().startsValid === false);

  // 触发懒重建：blocksInRange 会 ensure，之后 startsValid 回到 true
  const r = bi.blocksInRange(1, 3);
  const blk1 = r.find(x => x.id === "blk-1");
  check("A8  懒重建后查询正确（blk-1 区间=3）", !!blk1 && blk1.srcLineEnd === 3);
  check("A8  懒重建后 startsValid 恢复 true", bi._diagnose().startsValid === true);
})();

// A9 commit().removedIds 正确
(function () {
  const { bi, handles } = makeDoc([
    { kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, text: "a" },
    { kind: "paragraph", srcLineStart: 2, srcLineEnd: 2, text: "b" },
  ]);
  bi.beginStamp();
  bi.remove(handles[0].id);
  const res = bi.commit();
  check("A9  removedIds 含被删 id", res.removedIds.length === 1 && res.removedIds[0] === handles[0].id);
  check("A9  删除后 get 返回 null", bi.get(handles[0].id) === null);
})();

// A10 isFrozen 是方法、非字段（R6）
(function () {
  const { bi, handles } = makeDoc([{ kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, text: "x" }]);
  check("A10 isFrozen 是函数", typeof bi.isFrozen === "function");
  check("A10 handle 无 frozen 字段", !("frozen" in handles[0]));
  bi.setFrozen(handles[0].id, true);
  check("A10 setFrozen 后 isFrozen=true", bi.isFrozen(handles[0].id) === true);
  bi.setFrozen(handles[0].id, false);
  check("A10 清除后 isFrozen=false", bi.isFrozen(handles[0].id) === false);
})();

// A11 _metrics 侧表不泄漏进 handle（R5）
(function () {
  const { bi, handles } = makeDoc([{ kind: "paragraph", srcLineStart: 1, srcLineEnd: 1, text: "x" }]);
  bi.setMetrics(handles[0].id, { estHeight: 24, realHeight: 28 });
  check("A11 handle 无 estHeight/realHeight", !("estHeight" in handles[0]) && !("realHeight" in handles[0]));
  const m = bi.getMetrics(handles[0].id);
  check("A11 getMetrics 侧表可读", !!m && m.estHeight === 24 && m.realHeight === 28);
})();

// ── 汇总 ────────────────────────────────────────────────────────────────
console.log("\n" + passes + " passed, " + failures + " failed");
process.exit(failures === 0 ? 0 : 1);
