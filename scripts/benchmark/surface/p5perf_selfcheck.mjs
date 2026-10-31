#!/usr/bin/env node
/**
 * p5perf_selfcheck.mjs —— 两次运行产物的**逐字节比对**（org.md §12 密封性自检）
 *
 * 工作量计数是密封的 ⇒ 同 commit + 同脚本 + 同参数连跑两次，
 * 两次产物的计数部分应**逐字节相同**（只允许时间戳/路径不同）。
 */
import fs from 'node:fs';

const a = process.argv[2];
const b = process.argv[3];
const outPath = process.argv[4] || '';

function load(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }

function stripVolatile(obj) {
  const clone = JSON.parse(JSON.stringify(obj));
  delete clone.startedAt;
  delete clone.finishedAt;
  // 路径/argv 中的输出文件不同属正常
  if (clone.argv) clone.argv = clone.argv.map((x) => (typeof x === 'string' ? x.replace(/[^/\\]*\.json$/, '<OUT>.json') : x));
  return clone;
}

const A = load(a), B = load(b);
const sa = JSON.stringify(stripVolatile(A), Object.keys(stripVolatile(A)).sort());
const sb = JSON.stringify(stripVolatile(B), Object.keys(stripVolatile(B)).sort());

/* 逐操作比对计数（核心密封部分） */
function countsOf(doc) {
  const out = {};
  for (const [k, v] of Object.entries(doc.ops || {})) {
    const c = v.canonical;
    out[k] = c ? {
      M1: c.M1, M2: c.M2, M2add: c.M2add, M2del: c.M2del,
      attrWrites: c.attrWrites, blocksChanged: c.blocksChanged,
      blocksBefore: c.blocksBefore, blocksAfter: c.blocksAfter,
      calls: c.calls,
    } : null;
  }
  return out;
}
const ca = countsOf(A), cb = countsOf(B);

const ops = Object.keys(ca);
const perOp = ops.map((k) => ({
  op: k,
  identical: JSON.stringify(ca[k]) === JSON.stringify(cb[k]),
  a: ca[k], b: cb[k],
}));

const allIdentical = perOp.every((x) => x.identical);
const result = {
  schema: 'memoria-p5-selfcheck/v1',
  fileA: a, fileB: b,
  side: A.side,
  opsCompared: ops,
  perOp,
  countsIdentical: allIdentical,
  // 整个产物（去掉时间戳后）是否一致
  wholeDocIdentical: sa === sb,
  // 稳定性：每操作在各自 run 内的轮间稳定性
  stabilityA: Object.fromEntries(ops.map((k) => [k, { stable: A.ops[k].stable, stableWarm: A.ops[k].stableWarm }])),
  stabilityB: Object.fromEntries(ops.map((k) => [k, { stable: B.ops[k].stable, stableWarm: B.ops[k].stableWarm }])),
  finishedAt: new Date().toISOString(),
};

console.log('[selfcheck] side=' + A.side + ' ops=' + ops.length + ' countsIdentical=' + allIdentical + ' wholeDoc=' + result.wholeDocIdentical);
for (const x of perOp) {
  if (!x.identical) {
    console.log('  ✗ ' + x.op + '  A=' + JSON.stringify(x.a) + '  B=' + JSON.stringify(x.b));
  }
}

if (outPath) {
  fs.mkdirSync(outPath.replace(/[\/\\][^\/\\]+$/, ''), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
  console.log('__SELFCHECK__' + JSON.stringify({ ok: allIdentical, out: outPath }));
}
