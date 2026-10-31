#!/usr/bin/env node
/** p5perf_selfcheck2.mjs —— task-48：A 类计数器逐字节自检（新判据） */
import fs from 'node:fs';

const [aPath, bPath, outPath] = process.argv.slice(2);
const A = JSON.parse(fs.readFileSync(aPath, 'utf8'));
const B = JSON.parse(fs.readFileSync(bPath, 'utf8'));

const ops = Object.keys(A.ops || {});
const perOp = ops.map((k) => {
  const a = (A.ops[k] || {}).canonicalA;
  const b = (B.ops[k] || {}).canonicalA;
  const sig = (x) => x ? JSON.stringify({ M1: x.M1, M2: x.M2, M2add: x.M2add, M2del: x.M2del,
                                          attrWrites: x.attrWrites, blocksChanged: x.blocksChanged,
                                          blocksBefore: x.blocksBefore, blocksAfter: x.blocksAfter,
                                          calls: x.calls }) : null;
  const sa = sig(a), sb = sig(b);
  return {
    op: k,
    identical: sa !== null && sa === sb,
    A_a: a ? { M1: a.M1, M2: a.M2, calls: a.calls } : null,
    A_b: b ? { M1: b.M1, M2: b.M2, calls: b.calls } : null,
    errA: (A.ops[k].errors || [])[0] || null,
    errB: (B.ops[k].errors || [])[0] || null,
  };
});

/* B 类：只记录范围，判"两次是否都落在同一区间" */
const bClass = ops.map((k) => {
  const ra = (A.ops[k] || {}).B_range || {};
  const rb = (B.ops[k] || {}).B_range || {};
  const overlap = (x, y) => (x && y) ? (Math.min(x.max, y.max) >= Math.max(x.min, y.min)) : true;
  return {
    op: k,
    typeset: { a: ra.typeset, b: rb.typeset, rangesOverlap: overlap(ra.typeset, rb.typeset) },
    flushRepaint: { a: ra.flushRepaint, b: rb.flushRepaint, rangesOverlap: overlap(ra.flushRepaint, rb.flushRepaint) },
  };
});

const allA = perOp.every((x) => x.identical);
const totalA = perOp.length;
const sameA = perOp.filter((x) => x.identical).length;

const result = {
  schema: 'memoria-p5-selfcheck2/v1',
  fileA: aPath, fileB: bPath,
  side: A.side,
  pathCheckA: A.pathCheck, pathCheckB: B.pathCheck,
  A_class: { total: totalA, identical: sameA, allIdentical: allA, perOp },
  B_class: { note: '竞态计数器，不要求逐字节一致，只要求两次区间重叠', perOp: bClass },
  finishedAt: new Date().toISOString(),
};

console.log('[sc2] A 类: ' + sameA + '/' + totalA + ' 逐字节一致  allIdentical=' + allA);
console.log('[sc2] 通路: runA viewMode=' + (A.pathCheck || {}).viewMode + ' blocks=' + (A.pathCheck || {}).previewBlocks +
  ' | runB viewMode=' + (B.pathCheck || {}).viewMode + ' blocks=' + (B.pathCheck || {}).previewBlocks);
for (const x of perOp) {
  console.log('  ' + (x.identical ? '✓' : '✗') + ' ' + x.op.padEnd(11) +
    ' runA M1=' + (x.A_a ? x.A_a.M1 : 'null') + ' runB M1=' + (x.A_b ? x.A_b.M1 : 'null') +
    ' calls=' + (x.A_a ? JSON.stringify(x.A_a.calls) : '-'));
}
if (outPath) {
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
  console.log('__SC2__' + JSON.stringify({ ok: allA, out: outPath }));
}
