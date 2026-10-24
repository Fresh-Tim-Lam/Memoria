#!/usr/bin/env node
"use strict";
const j = require("../../../../artifacts/agent/verify/debate/assumptions/as-section-range-measure.json");
const t = j.totals;
const pct = (a, b) => ((a / b) * 100).toFixed(2) + "%";

console.log("=== 关键比率 ===");
console.log("文档有 heading:", t.docsWithHeading + "/" + t.docs, pct(t.docsWithHeading, t.docs));
console.log("完全可寻址文档:", t.docsFullyAddressable + "/" + t.docs, pct(t.docsFullyAddressable, t.docs));
console.log("");
console.log("=== 风险量化（分母 = 真 heading " + t.awareHeadingCount + "）===");
console.log("现有实现误判(围栏内#):", t.falseHeadingInFence, pct(t.falseHeadingInFence, t.awareHeadingCount));
console.log("重复文本影响 heading:", t.duplicateHeadingsAffected, pct(t.duplicateHeadingsAffected, t.awareHeadingCount));
console.log("二阶影响合计:", t.falseHeadingInFence + t.duplicateHeadingsAffected,
  pct(t.falseHeadingInFence + t.duplicateHeadingsAffected, t.awareHeadingCount));
console.log("");
console.log("=== 重复 heading 样本 ===");
for (const kb of j.kbs.filter(k => k.docs)) {
  const kbName = kb.dir.split(/[\\/]/).pop();
  const dups = kb.docs.filter(d => d.duplicateTextCount > 0);
  for (const d of dups.slice(0, 3)) {
    console.log("  [" + kbName + "] " + d.file + " -> " + d.duplicateTextCount + " 组重复");
    for (const s of d.duplicateSamples.slice(0, 2)) {
      console.log('      "' + s.text + '" x' + s.count + " (levels " + s.levels.join(",") + ")");
    }
  }
}
console.log("");
console.log("=== 围栏误判样本（现有实现会把这些当成 heading）===");
for (const kb of j.kbs.filter(k => k.docs)) {
  const kbName = kb.dir.split(/[\\/]/).pop();
  for (const d of kb.docs.filter(x => x.falseHeadingInFence > 0).slice(0, 3)) {
    console.log("  [" + kbName + "] " + d.file + " -> " + d.falseHeadingInFence + " 个误判 / " + d.fenceBlocks + " 个围栏块");
  }
}
console.log("");
console.log("=== 层级分布（正确口径）===");
const lv = {};
for (const kb of j.kbs.filter(k => k.docs)) {
  for (const d of kb.docs) for (const [k, v] of Object.entries(d.levelDist || {})) lv[k] = (lv[k] || 0) + v;
}
for (const k of Object.keys(lv).sort()) console.log("  h" + k + ": " + lv[k]);
