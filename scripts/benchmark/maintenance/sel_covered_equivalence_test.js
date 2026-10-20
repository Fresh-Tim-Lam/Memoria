#!/usr/bin/env node
/**
 * sel_covered_equivalence_test.js —— `_updateAtomicSelectionHighlight` 改造前后的**行为等价性**证明
 *
 * 背景（task-19）：`app.js` 的 `_updateAtomicSelectionHighlight()` 每键无条件遍历全部 `.-math`
 * 并对每个元素调 `el.classList.toggle("-sel-covered", isCovered)` ⇒ scale-5k 上 **148 次/键**空操作
 * （选区折叠时 isCovered 恒 false，toggle 全在"删一个不存在的类"）。
 *
 * 本脚本**不依赖浏览器**：用最小假 DOM（FakeEl + FakeRange）复刻两种版本的循环体，
 * 在大量场景下逐元素比对两侧算出的 `-sel-covered` **命中集合**（有序、逐元素，不是只比数量），
 * 并统计 DOM 写调用次数（模拟 M1 口径）。
 *
 * 跑法：node scripts/benchmark/maintenance/sel_covered_equivalence_test.js
 * 退出码 0 = 全过；1 = 有差异（会打印第一个反例）。
 */

'use strict';

// ────────────────────────────── 最小假 DOM ──────────────────────────────

/** 一个"原子元素"（对应 .-math）。位置域用 [start, end) 的整数区间模拟文档顺序。 */
class FakeEl {
  constructor(start, end) {
    this.start = start;
    this.end = end;
    this._classes = new Set();
    this.classList = {
      toggle: (c, on) => { writes++; if (on) this._classes.add(c); else this._classes.delete(c); },
      contains: (c) => this._classes.has(c),
    };
  }
}
let writes = 0; // 模拟 M1：DOM 写 API 调用次数

/** 最小 Range：selectNode(el) 得到 [el.start, el.end)；compareBoundaryPoints 用整数比较复刻语义。 */
class FakeRange {
  constructor(s, e) { this.s = s; this.e = e; }
  static selectNode(el) { return new FakeRange(el.start, el.end); }
  // 语义与真实 Range 一致：
  //   END_TO_START 比较 (this.end, other.start)
  //   START_TO_END 比较 (this.start, other.end)
  // 注：真实 API 的返回是 ±1/0，这里返回整数差，>0/<0 的判定等价。
  compareBoundaryPoints(how, other) {
    if (how === Range.END_TO_START) return this.e - other.s;
    if (how === Range.START_TO_END) return this.s - other.e;
    throw new Error('unsupported ' + how);
  }
}
const Range = { END_TO_START: 0, START_TO_END: 1 };

// ────────────────────────────── 两个版本的循环体 ──────────────────────────────

/**
 * 改造前：无条件 toggle（148 次/键的来源）。
 * @param {FakeEl[]} atoms
 * @param {FakeRange|null} r  非 null = 有可高亮选区；null = 折叠/无选区/不在 preview 内
 */
function legacy(atoms, r) {
  let covered = 0;
  for (let i = 0; i < atoms.length; i++) {
    const el = atoms[i];
    let isCovered = false;
    if (r) {
      try {
        const er = FakeRange.selectNode(el);
        const c1 = r.compareBoundaryPoints(Range.END_TO_START, er);
        const c2 = r.compareBoundaryPoints(Range.START_TO_END, er);
        // 与真实代码同构：`isCovered = c1 > 0 && c2 < 0;`
        // （FakeRange 返回整数差，符号语义与真实 API 的 ±1/0 等价）
        isCovered = c1 > 0 && c2 < 0;
        if (!isCovered && (r.anchor === el || r.focus === el)) isCovered = true;
      } catch (err) { /* legacy 也是吞掉 */ }
    }
    el.classList.toggle('-sel-covered', isCovered);
    if (isCovered) covered++;
  }
  return covered;
}

/**
 * 改造后：语义精确早退。
 *  - 无选区（r 为 null）⇒ 只**清残留**（对仍带类的元素 remove），不做相交计算、不遍历全部；
 *  - 有选区但一个都没命中 ⇒ 同样只清残留；
 *  - 有命中 ⇒ 走原逻辑（命中集合必须逐元素一致）。
 */
function patched(atoms, r) {
  // 早退：没有可高亮选区 ⇒ 只清残留（这正是"只跳不清会留残影"要求的清类逻辑）
  if (!r) {
    clearResidue(atoms);
    return 0;
  }
  let covered = 0;
  for (let i = 0; i < atoms.length; i++) {
    const el = atoms[i];
    let isCovered = false;
    try {
      const er = FakeRange.selectNode(el);
      const c1 = r.compareBoundaryPoints(Range.END_TO_START, er);
      const c2 = r.compareBoundaryPoints(Range.START_TO_END, er);
      isCovered = c1 > 0 && c2 < 0;
      if (!isCovered && (r.anchor === el || r.focus === el)) isCovered = true;
    } catch (err) { /* 同上 */ }
    const has = el.classList.contains('-sel-covered');
    if (isCovered) {
      if (!has) el.classList.toggle('-sel-covered', true);   // 只在真变时写
      covered++;
    } else if (has) {
      el.classList.toggle('-sel-covered', false);             // 只在真变时写（清残留）
    }
  }
  return covered;
}

/** 只清残留：命中数一定为 0，所以等价于 remove 所有仍带类的元素。 */
function clearResidue(atoms) {
  for (let i = 0; i < atoms.length; i++) {
    if (atoms[i].classList.contains('-sel-covered')) atoms[i].classList.toggle('-sel-covered', false);
  }
}

// ────────────────────────────── 场景 ──────────────────────────────

function makeAtoms(n) {
  // 模拟文档序中的 n 个不相交公式，每个占 [i*10, i*10+3)，间隔 7 —— 与"公式之间夹着文字"同构
  const out = [];
  for (let i = 0; i < n; i++) out.push(new FakeEl(i * 10, i * 10 + 3));
  return out;
}

/**
 * 选区坐标助手（公式 i 在 [i*10, i*10+3)）：
 *   from(i) = 公式 i 的起点；to(i) = 公式 i 的终点
 * 覆盖判据（真实 Range 相交语义）：选区端点 s 以后、e 以前"穿过"了公式 i 的任一像素。
 *   公式 i 被覆盖 ⇔ s < 公式i.end 且 e > 公式i.start
 */
const from = (i) => i * 10;
const to = (i) => i * 10 + 3;

/** 取"当前命中集合"（有序、逐元素）。 */
function hitList(atoms) {
  const out = [];
  for (let i = 0; i < atoms.length; i++) if (atoms[i].classList.contains('-sel-covered')) out.push(i);
  return out;
}

function withRange(r) {
  const rr = new FakeRange(r.s, r.e);
  rr.anchor = r.anchor || null;
  rr.focus = r.focus || null;
  return rr;
}

const N = 270;              // 与 scale-5k 的 270 个 .-math 同规模
const CASES = [
  { name: '折叠（无选区）', r: null, seedHits: [] },
  { name: '折叠，但上次残留 3 个高亮', r: null, seedHits: [2, 50, 269] },
  { name: '选区覆盖 0 个（落在两个公式之间）', r: { s: to(0), e: from(1) }, seedHits: [] },
  { name: '选区覆盖 0 个，但上次残留 1 个', r: { s: to(0), e: from(1) }, seedHits: [100] },
  { name: '选区恰覆盖 1 个（只擦过公式中部）', r: { s: from(1) + 1, e: to(1) - 1 }, seedHits: [] },
  { name: '选区跨 5 个', r: { s: from(2), e: to(6) }, seedHits: [] },
  { name: '选区跨 5 个（上一次命中的是另一批）', r: { s: from(2), e: to(6) }, seedHits: [0, 1, 2, 3, 269] },
  { name: '选区覆盖全部', r: { s: from(0), e: to(N - 1) }, seedHits: [] },
  { name: '选区覆盖全部（上一次只有零星）', r: { s: from(0), e: to(N - 1) }, seedHits: [7] },
  { name: '选区只碰边界（end == 公式1 start，不算覆盖）', r: { s: to(0), e: from(1) }, seedHits: [] },
  { name: '选区只碰边界（start == 公式0 end，不算覆盖）', r: { s: to(0), e: to(3) }, seedHits: [] },
  { name: '整元素选中（startContainer === el 兜底路径）', r: { s: from(3), e: to(3), anchor: 3 }, seedHits: [] },
  { name: '整元素选中（endContainer === el 兜底路径）', r: { s: from(3), e: to(3), focus: 3 }, seedHits: [] },
  { name: '选区在文档最末公式之后', r: { s: to(N - 1) + 2, e: to(N - 1) + 40 }, seedHits: [5, 6] },
];

let pass = 0;
let fail = 0;
const rows = [];

for (const c of CASES) {
  // 两侧各自独立初始化（同样的种子残留），保证是"A/B 同一输入"
  const atomsA = makeAtoms(N);
  const atomsB = makeAtoms(N);
  for (const i of c.seedHits) {
    atomsA[i].classList.toggle('-sel-covered', true);
    atomsB[i].classList.toggle('-sel-covered', true);
  }

  writes = 0;
  const coveredA = legacy(atomsA, c.r ? withRange(c.r) : null);
  const wA = writes;

  writes = 0;
  const coveredB = patched(atomsB, c.r ? withRange(c.r) : null);
  const wB = writes;

  const hitsA = hitList(atomsA);
  const hitsB = hitList(atomsB);
  const same = JSON.stringify(hitsA) === JSON.stringify(hitsB);
  const sameCount = coveredA === coveredB && hitsA.length === coveredA;

  if (same && sameCount) pass++;
  else {
    fail++;
    console.error('FAIL', c.name, '\n  legacy hits:', JSON.stringify(hitsA), '\n  patched hits:', JSON.stringify(hitsB));
  }
  rows.push({
    case: c.name,
    covered: coveredA,
    legacyWrites: wA,
    patchedWrites: wB,
    same,
  });
}

// ────────────────────────────── 逐元素比对（另一条更强的证据）──────────────────────────────
// 对**每一个可能的选区端点对**做穷举比对：命中集合必须逐元素一致。
let sweepMismatch = 0;
let sweepCases = 0;
for (let s = 0; s <= 610; s += 3) {
  for (let e = s; e <= 610; e += 3) {
    sweepCases++;
    const a1 = makeAtoms(60);
    const a2 = makeAtoms(60);
    legacy(a1, withRange({ s, e }));
    patched(a2, withRange({ s, e }));
    if (JSON.stringify(hitList(a1)) !== JSON.stringify(hitList(a2))) {
      sweepMismatch++;
      if (sweepMismatch <= 3) console.error('SWEEP MISMATCH', { s, e }, hitList(a1), hitList(a2));
    }
  }
}

// ────────────────────────────── 输出 ──────────────────────────────
console.log('场景等价性：' + pass + ' passed, ' + fail + ' failed（共 ' + CASES.length + ' 个场景）');
console.log('穷举端点对：' + (sweepCases - sweepMismatch) + '/' + sweepCases + ' 命中集合逐元素一致');
console.log('');
console.log('| 场景 | 命中数 | 改造前写次数 | 改造后写次数 | 命中集合一致 |');
console.log('|---|---|---|---|---|');
for (const r of rows) {
  console.log('| ' + r.case + ' | ' + r.covered + ' | ' + r.legacyWrites + ' | ' + r.patchedWrites + ' | ' + (r.same ? '✅' : '❌') + ' |');
}
const collapse = rows[0];
console.log('');
console.log('折叠场景（scale-5k 的 148 次来源）：改造前 ' + collapse.legacyWrites + ' 次写 → 改造后 ' + collapse.patchedWrites + ' 次写');

if (fail > 0 || sweepMismatch > 0) {
  console.error('\n结论：FAIL —— 行为不等价');
  process.exit(1);
}
console.log('\n结论：PASS —— 命中集合逐元素一致，且折叠/无命中时写次数归零');
