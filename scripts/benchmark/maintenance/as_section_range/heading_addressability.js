#!/usr/bin/env node
/**
 * AS-SECTION-RANGE 检验脚本：md heading 能否被稳定解析为可寻址区间
 *
 * task-118。方法：真实语料实测，**不启发式猜测**。
 *
 * 关键检验项（对应 task 要求）：
 *   1. heading 覆盖率（有多少 md 有 heading）
 *   2. 层级分布（h1..h6）
 *   3. **重复 heading 文本** ← 关键风险：同文本 heading 出现多次 ⇒ 无法唯一定位
 *   4. **围栏代码块内的 # 是否被误判** ← 现有两个解析器都用 ^ 行首匹配，不判代码块
 *   5. frontmatter 内的 # 是否被误判
 *   6. 行内代码里的 # （不构成行首标题，但要看）
 *   7. 大文件解析耗时
 *
 * 输出：JSON（带 sha256，供 E4.2 溯源）
 *
 * 用法: node heading_addressability.js --kb <dir> [--kb <dir2> ...] --out <json>
 */
"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// ── 现有产品代码里的两个 heading 正则（**逐字复制，不改进**）────────────
// 目的是测"现状能否用"，不是测"我能不能写个更好的"。
const RE_DOCUMENT = /^(#{1,6})\s+/;      // document.py:420
const RE_PROPOSALS = /^(#{2,6})\s+/;     // heading_proposals.py:9

/**
 * 解析一篇 md 的 heading 结构。
 * ★ 关键：同时产出「朴素解析」（现有实现：只按 ^ 行首匹配）
 *   与「围栏感知解析」（先剔除围栏代码块再匹配）两种结果，
 *   两者的差异就是现有实现的**误判量**。
 */
function analyzeDoc(text) {
  const lines = text.split("\n");

  // ── 1. frontmatter 边界 ──
  let fmEnd = -1;   // frontmatter 结束行索引（含）
  if (lines.length > 0 && lines[0].trim() === "---") {
    for (let i = 1; i < lines.length; i++) {
      if (lines[i].trim() === "---") { fmEnd = i; break; }
    }
  }

  // ── 2. 围栏代码块区间 ──
  const fenceRanges = [];
  let fenceStart = -1, fenceChar = null, fenceLen = 0;
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    const m = t.match(/^(`{3,}|~{3,})/);
    if (!m) continue;
    const ch = m[1][0], len = m[1].length;
    if (fenceStart < 0) { fenceStart = i; fenceChar = ch; fenceLen = len; }
    else if (ch === fenceChar && len >= fenceLen) {
      fenceRanges.push([fenceStart, i]);
      fenceStart = -1; fenceChar = null; fenceLen = 0;
    }
  }
  if (fenceStart >= 0) fenceRanges.push([fenceStart, lines.length - 1]);  // 未闭合

  const inFence = (i) => fenceRanges.some(([a, b]) => i >= a && i <= b);
  const inFrontmatter = (i) => fmEnd >= 0 && i <= fmEnd;

  // ── 3. 朴素解析（现有实现口径）──
  const naive = [];      // {line, level, text}
  const naiveAll = [];   // document.py 的 {1,6}
  const naiveProposals = []; // heading_proposals.py 的 {2,6}
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m1 = line.match(RE_DOCUMENT);
    if (m1) {
      naiveAll.push({ line: i, level: m1[1].length, text: line.trim() });
      naive.push({ line: i, level: m1[1].length, text: line.trim() });
    }
    const m2 = line.match(RE_PROPOSALS);
    if (m2) naiveProposals.push({ line: i, level: m2[1].length, text: line.trim() });
  }

  // ── 4. 围栏感知解析（正确口径）──
  const aware = [];
  for (let i = 0; i < lines.length; i++) {
    if (inFence(i) || inFrontmatter(i)) continue;
    const m = lines[i].match(RE_DOCUMENT);
    if (m) aware.push({ line: i, level: m[1].length, text: lines[i].trim() });
  }

  // ── 5. 误判分类 ──
  const falseInFence = naiveAll.filter(h => inFence(h.line));
  const falseInFm = naiveAll.filter(h => inFrontmatter(h.line));

  // ── 6. 重复 heading 文本（按归一化文本）──
  const norm = (s) => s.replace(/^#{1,6}\s+/, "").trim().replace(/\s+/g, " ").toLowerCase();
  const byText = new Map();
  for (const h of aware) {
    const k = norm(h.text);
    if (!byText.has(k)) byText.set(k, []);
    byText.get(k).push(h.level);
  }
  const dups = [];
  for (const [k, levels] of byText) if (levels.length > 1) dups.push({ text: k, count: levels.length, levels });

  // ── 7. 层级分布 ──
  const levelDist = {};
  for (const h of aware) levelDist[h.level] = (levelDist[h.level] || 0) + 1;

  // ── 8. 末节边界可算性：最后一条 heading 之后的结尾 ──
  const lastHeadingLine = aware.length ? aware[aware.length - 1].line : -1;

  return {
    lines: lines.length,
    bytes: Buffer.byteLength(text, "utf8"),
    hasFrontmatter: fmEnd >= 0,
    fenceBlocks: fenceRanges.length,
    // 朴素（现有实现）
    naiveHeadingCount: naiveAll.length,
    naiveProposalsCount: naiveProposals.length,
    // 围栏感知（正确）
    awareHeadingCount: aware.length,
    // 误判
    falseHeadingInFence: falseInFence.length,
    falseHeadingInFrontmatter: falseInFm.length,
    // 重复文本
    duplicateTextCount: dups.length,
    duplicateHeadingsAffected: dups.reduce((a, d) => a + d.count, 0),
    duplicateSamples: dups.slice(0, 8),
    levelDist,
    lastHeadingLine,
    awareHeadings: aware.slice(0, 200),   // 采样，供人工核对
  };
}

function walk(dir, acc) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    const st = fs.statSync(p);
    if (st.isDirectory()) {
      if (name === "node_modules" || name === ".git" || name === ".memoria") continue;
      walk(p, acc);
    } else if (/\.md$/i.test(name)) acc.push(p);
  }
  return acc;
}

function main() {
  const argv = process.argv.slice(2);
  const kbs = [], out = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--kb") kbs.push(argv[++i]);
    else if (argv[i] === "--out") out.push(argv[++i]);
  }
  if (!kbs.length || !out.length) {
    console.error("用法: node heading_addressability.js --kb <dir> [--kb <dir2>] --out <json>");
    process.exit(2);
  }
  const REPO = path.resolve(__dirname, "..", "..", "..", "..");
  const outPath = path.isAbsolute(out[0]) ? out[0] : path.resolve(REPO, out[0]);

  const result = {
    schema: "as-section-range-measure/v1",
    measuredAt: new Date().toISOString(),
    kbSourceLabel: "真实 KB 目录（docs/example/*）",
    note: "existing_regex_document = " + RE_DOCUMENT.source + " (document.py:420); " +
          "existing_regex_proposals = " + RE_PROPOSALS.source + " (heading_proposals.py:9)",
    kbs: [],
    totals: null,
  };

  const tot = {
    docs: 0, lines: 0, bytes: 0,
    docsWithHeading: 0, docsWithoutHeading: 0,
    awareHeadingCount: 0, naiveHeadingCount: 0,
    falseHeadingInFence: 0, falseHeadingInFrontmatter: 0,
    duplicateTextCount: 0, duplicateHeadingsAffected: 0,
    docsWithDuplicateHeading: 0,
    docsFullyAddressable: 0,     // 无重复文本 & 无误判 ⇒ 每个 heading 可唯一定位
    maxFileBytes: 0, maxFileMs: 0,
  };

  for (const kbArg of kbs) {
    const dir = path.isAbsolute(kbArg) ? kbArg : path.resolve(REPO, kbArg);
    if (!fs.existsSync(dir)) { result.kbs.push({ dir: kbArg, error: "not found" }); continue; }
    const files = walk(dir, []).sort();
    const perDocs = [];
    const kbTotals = {
      docs: 0, awareHeadingCount: 0, falseHeadingInFence: 0, falseHeadingInFrontmatter: 0,
      duplicateTextCount: 0, docsWithHeading: 0, docsWithoutHeading: 0,
      docsFullyAddressable: 0, docsWithDuplicateHeading: 0,
    };
    for (const f of files) {
      let text;
      try { text = fs.readFileSync(f, "utf8"); } catch { continue; }
      const t0 = process.hrtime.bigint();
      const a = analyzeDoc(text);
      const ms = Number(process.hrtime.bigint() - t0) / 1e6;
      const rel = path.relative(dir, f).replace(/\\/g, "/");
      const fullyAddressable = a.duplicateTextCount === 0 && a.falseHeadingInFence === 0 && a.falseHeadingInFrontmatter === 0;

      perDocs.push({ file: rel, ...a, parseMs: +ms.toFixed(3), fullyAddressable });
      kbTotals.docs++;
      kbTotals.awareHeadingCount += a.awareHeadingCount;
      kbTotals.falseHeadingInFence += a.falseHeadingInFence;
      kbTotals.falseHeadingInFrontmatter += a.falseHeadingInFrontmatter;
      kbTotals.duplicateTextCount += a.duplicateTextCount;
      if (a.awareHeadingCount > 0) kbTotals.docsWithHeading++; else kbTotals.docsWithoutHeading++;
      if (a.duplicateTextCount > 0) kbTotals.docsWithDuplicateHeading++;
      if (fullyAddressable) kbTotals.docsFullyAddressable++;

      tot.docs++; tot.lines += a.lines; tot.bytes += a.bytes;
      tot.awareHeadingCount += a.awareHeadingCount;
      tot.naiveHeadingCount += a.naiveHeadingCount;
      tot.falseHeadingInFence += a.falseHeadingInFence;
      tot.falseHeadingInFrontmatter += a.falseHeadingInFrontmatter;
      tot.duplicateTextCount += a.duplicateTextCount;
      tot.duplicateHeadingsAffected += a.duplicateHeadingsAffected;
      if (a.awareHeadingCount > 0) tot.docsWithHeading++; else tot.docsWithoutHeading++;
      if (a.duplicateTextCount > 0) tot.docsWithDuplicateHeading++;
      if (fullyAddressable) tot.docsFullyAddressable++;
      if (a.bytes > tot.maxFileBytes) { tot.maxFileBytes = a.bytes; tot.maxFilePath = rel; }
      if (ms > tot.maxFileMs) { tot.maxFileMs = +ms.toFixed(3); tot.maxFileMsPath = rel; }
    }
    result.kbs.push({ dir: kbArg, totals: kbTotals, docs: perDocs });
  }
  result.totals = tot;

  // ★ E4/null-sequential 修正（2026-10-25，自查发现）：
  //   初版把 maxFileMs（计时）混进 totals ⇒ 两次跑的 sha 因计时抖动而不同 ⇒ 产物不可复现。
  //   现在把**计时与统计分离**：确定性产物只含统计数字，计时单独放 timing 段并从 sha 计算中剔除。
  const timing = {
    maxFileMs: tot.maxFileMs,
    maxFileMsPath: tot.maxFileMsPath,
    note: "本段是墙钟计时，**不参与 artifactSha256**（计时天然抖动，混入会破坏可复现性）",
  };
  delete tot.maxFileMs;
  delete tot.maxFileMsPath;
  for (const k of result.kbs) {
    if (!k.docs) continue;
    for (const d of k.docs) {
      if (d.parseMs !== undefined) { d.parseMsMeasured = d.parseMs; delete d.parseMs; }
    }
  }
  result.timing = timing;

  // 产物 sha（供 E4.2）—— 只对**确定性部分**计算：剔除 measuredAt / timing / parseMsMeasured
  const canon = JSON.parse(JSON.stringify(result));
  delete canon.measuredAt;
  delete canon.timing;
  for (const k of canon.kbs) {
    if (!k.docs) continue;
    for (const d of k.docs) delete d.parseMsMeasured;
  }
  result.artifactSha256 = crypto.createHash("sha256").update(JSON.stringify(canon)).digest("hex");
  result.shaCoversNote = "artifactSha256 覆盖：确定性统计部分（不含 measuredAt / timing / parseMsMeasured）";

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(result, null, 1), "utf8");
  console.log(JSON.stringify({
    out: outPath, artifactSha256: result.artifactSha256, totals: tot,
    perKb: result.kbs.map(k => ({ dir: k.dir, t: k.totals })),
  }, null, 1));
}

main();
