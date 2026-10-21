#!/usr/bin/env node
/**
 * compare_signatures.mjs —— 新旧渲染管线「按 kind 过滤」的双跑签名对比（阶段 2 判等工具）
 *
 * 背景：P2a 阶段 `new` 只实现 5 类块，故本工具支持「按 kind 过滤」——未实现的 kind 记
 *   `unsupported` 而非 `diff`，否则 P2a 永远红、无法推进。
 *   **P2c 之后 `new` 已覆盖全部 12 kind**，默认集合随之改为全 12 kind（见 ALL_KINDS）。
 *
 * **四种结论，语义严格区分**：
 *   - `match`        ：该 kind 双方签名片段**完全一致**（逐块比 {tag, textNorm}）
 *   - `diff`         ：该 kind **双方都支持**，但签名**不一致** ⇒ **这才是失败**
 *   - `unsupported`  ：该 kind **至少一方未实现** ⇒ 不算失败（记录但不阻断）
 *   - `schema_error` ：某侧缺/坏 `signatureNorm` ⇒ **必须失败**（绝不静默 match）
 *
 * ## ⚠️ 默认口径的两面性（Lead 裁决，必读）
 *   默认值改成「全部 12 kind」修复了「漏 kind ⇒ 假 unsupported」；
 *   但反过来，**全默认会让「未实现 kind」永远被当成支持 ⇒ 也是假通过**。
 *   因此：未显式传 `--supported` 时，产物带 `supportedSource: "default-all"`，
 *   结论行打印提醒 —— 使用者必须知道自己在用哪个口径。
 *   若要验证「某 kind 未实现会被正确识别」，**必须显式传 `--supported`**。
 *
 * 用法：
 *   node compare_signatures.mjs --baseline <a.json> --current <b.json> \
 *        [--supported <k1,k2,...>] [--out diff.json]
 *
 * 退出码：0 = 无 diff（match + unsupported 均可接受）；1 = 存在 diff/schema_error；2 = 输入错误
 */

import fs from 'node:fs';
import path from 'node:path';

/**
 * DOM kindClass / tag -> P2a 的 5 类块名（+ 其余归一化名）。
 * 目的：让 --supported 用 AST 名声明时也能匹配 DOM 侧投影。
 */
function normalizeKind(raw) {
  const k = String(raw || '').trim();
  if (!k) return 'unknown';
  // 已实现块的后处理产物
  if (k === '-blank-block') return 'blank';
  if (k === '-code-block') return 'code_block';
  if (k === '-math-block') return 'math_block';
  if (k === '-mermaid-container' || k === '-mermaid-error' || k === 'pre' || k === '-mermaid') return 'mermaid';
  if (k === '-table') return 'table';
  if (k === '-image-block') return 'image';
  if (k === '-frontmatter') return 'frontmatter';
  // 基础标签
  if (k === 'p') return 'paragraph';
  if (/^h[1-6]$/.test(k)) return 'heading';
  if (k === 'ul' || k === 'ol') return 'list';
  if (k === 'li') return 'listItem';
  if (k === 'blockquote') return 'blockquote';
  if (k === 'hr') return 'hr';
  return k;
}

/**
 * 默认支持的 kind 集合（P2c 之后 new 已覆盖全部 12 类）。
 * 顺序与 task-33 口径一致：paragraph,heading,listItem,list,blockquote,hr,
 *                         code_block,table,image,blank,math_block,mermaid
 */
const ALL_KINDS = [
  'paragraph', 'heading', 'listItem', 'list', 'blockquote', 'hr',
  'code_block', 'table', 'image', 'blank', 'math_block', 'mermaid',
];

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (!t.startsWith('--')) continue;
    const k = t.slice(2);
    const n = argv[i + 1];
    if (n && !n.startsWith('--')) { a[k] = n; i++; } else a[k] = true;
  }
  return a;
}

function loadJson(p) {
  const txt = fs.readFileSync(p, 'utf8');
  return JSON.parse(txt);
}

/** 从 fidelity 结果里取出"每文档的 kind→片段"投影。 */
function kindProjection(fidelityResult) {
  const out = {};
  for (const [file, doc] of Object.entries(fidelityResult.documents || {})) {
    const r1 = doc.run1 || doc;
    const a1 = r1.aLevel || {};
    const a2 = a1.a2 || {};
    const kinds = a2.kinds || [];
    const tags = a2.tags || [];
    const sigNorm = r1.signatureNorm || '';
    // !! 防「假 match」：signatureNorm 缺失/不可解析时**必须显式标记**，
    //    绝不能退化成"文本恒空 ⇒ 只比 kind+tag ⇒ 判 match"。
    //    （这是本项目第三个假通过家族：字段缺失 => 恒空 => match。）
    let parsed = null;
    let schemaInvalid = null;
    if (!sigNorm) {
      schemaInvalid = 'missing-signatureNorm';
    } else {
      try { parsed = JSON.parse(sigNorm); } catch (e) {
        parsed = null;
        schemaInvalid = 'unparsable-signatureNorm';
      }
    }
    // 每个块的 kind + 其归一化文本（来自签名对象）
    const textNorm = (parsed && parsed.textNorm) || [];
    const blocks = kinds.map((k, i) => ({
      index: i,
      kind: normalizeKind(k),
      rawKind: String(k || ''),
      tag: tags[i] || '',
      text: textNorm[i] != null ? String(textNorm[i]) : '',
    }));
    out[file] = { signature: r1.signature || null, blocks, blockCount: blocks.length, parsed, schemaInvalid };
  }
  return out;
}

/** 把某个 kind 的块序列拼成可比较的片段。 */
function fragment(blocks, kind) {
  return blocks.filter((b) => b.kind === kind).map((b) => ({ tag: b.tag, text: b.text }));
}

function compareDocs(base, cur, supported) {
  const files = new Set([...Object.keys(base), ...Object.keys(cur)]);
  const perFile = {};
  const totals = { match: 0, diff: 0, unsupported: 0, missing: 0 };

  for (const file of files) {
    const b = base[file];
    const c = cur[file];
    if (!b || !c) {
      perFile[file] = { status: 'missing', side: !b ? 'baseline' : 'current' };
      totals.missing++;
      continue;
    }
    // schema 不完整 => 直接失败，不进入逐 kind 比较（否则就是假 match）
    if (b.schemaInvalid || c.schemaInvalid) {
      perFile[file] = {
        status: 'schema_error',
        side: b.schemaInvalid ? 'baseline' : 'current',
        reason: b.schemaInvalid || c.schemaInvalid,
      };
      totals.schema_error = (totals.schema_error || 0) + 1;
      continue;
    }
    const kinds = new Set();
    for (const x of b.blocks) kinds.add(x.kind);
    for (const x of c.blocks) kinds.add(x.kind);

    const rows = [];
    for (const kind of [...kinds].sort()) {
      const isSupported = supported.includes(kind);
      const fb = JSON.stringify(fragment(b.blocks, kind));
      const fc = JSON.stringify(fragment(c.blocks, kind));
      let status;
      if (!isSupported) {
        // 任一方不支持 ⇒ unsupported（不算失败）
        status = 'unsupported';
      } else if (fb === fc) {
        status = 'match';
      } else {
        status = 'diff';
      }
      rows.push({
        kind, status, supported: isSupported,
        baseCount: fragment(b.blocks, kind).length,
        curCount: fragment(c.blocks, kind).length,
      });
      totals[status] = (totals[status] || 0) + 1;
    }
    const fileStatus = rows.some((r) => r.status === 'diff') ? 'diff'
      : rows.every((r) => r.status === 'match' || r.status === 'unsupported') ? 'match' : 'unknown';
    perFile[file] = {
      status: fileStatus,
      baseBlockCount: b.blockCount,
      curBlockCount: c.blockCount,
      rows,
      // 整文档签名（仅供参考：P2a 阶段必然不同）
      signatureIdentical: b.signature === c.signature,
    };
  }

  // 总判定：只有存在 diff 才失败
  const ok = (totals.diff || 0) === 0 && (totals.missing || 0) === 0 && (totals.schema_error || 0) === 0;
  return { perFile, totals, ok };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const baselinePath = args.baseline;
  const currentPath = args.current || args.compare;
  if (!baselinePath || !currentPath || baselinePath === true || currentPath === true) {
    process.stderr.write('用法: node compare_signatures.mjs --baseline <a.json> --current <b.json> [--supported k1,k2] [--out out.json]\n');
    process.exitCode = 2;
    return;
  }
  // 口径来源：显式 --supported 还是默认全集（决定结论行的提醒）
  let supported = ALL_KINDS;
  let supportedSource = 'default-all';
  if (typeof args.supported === 'string') {
    supported = args.supported.split(',').map((s) => s.trim()).filter(Boolean);
    supportedSource = 'explicit';
  }

  let baseRaw, curRaw;
  try {
    baseRaw = loadJson(baselinePath);
    curRaw = loadJson(currentPath);
  } catch (e) {
    process.stderr.write('[compare] 读取失败: ' + (e && e.message) + '\n');
    process.exitCode = 2;
    return;
  }

  const base = kindProjection(baseRaw);
  const cur = kindProjection(curRaw);
  const result = compareDocs(base, cur, supported);

  const report = {
    schema: 'memoria-signature-compare/v1',
    baseline: baselinePath,
    current: currentPath,
    supportedKinds: supported,
    // 口径来源：'default-all' = 未显式传 --supported（全 12 kind）；'explicit' = 调用方指定
    //   默认全集修了"漏 kind ⇒ 假 unsupported"，但反过来说未实现 kind 也会被当支持 ⇒
    //   读者必须看这个字段判断自己用的是哪个口径。
    supportedSource: supportedSource,
    generatedAt: new Date().toISOString(),
    ok: result.ok,
    totals: result.totals,
    files: result.perFile,
    // 语义说明（写进产物，避免读者混淆）
    semantics: {
      match: '该 kind 双方签名片段完全一致',
      diff: '该 kind 双方都支持但签名不一致 —— **这才是失败**',
      unsupported: '该 kind 至少一方未实现（如 P2a 只覆盖 5 类块）—— **不算失败**，仅记录',
      missing: '某个文档只在一侧存在 —— 失败',
      schema_error: '该侧缺少/无法解析 signatureNorm（旧 schema）—— **失败，绝不静默 match**',
    },
  };

  if (args.out && args.out !== true) {
    fs.mkdirSync(path.dirname(args.out), { recursive: true });
    fs.writeFileSync(args.out, JSON.stringify(report, null, 2), 'utf8');
  }

  // 控制台摘要
  process.stdout.write('[compare] supported = ' + supported.join(',') +
    '  (source=' + supportedSource + ')\n');
  // ⚠️ 默认口径提醒（Lead 裁决要求）：默认全集会让"未实现 kind"永远被当成支持 ⇒ 也是假通过
  if (supportedSource === 'default-all') {
    process.stdout.write('⚠ 使用默认全 kind 集合（12 类）；若要验证「某 kind 未实现被正确识别」，' +
      '必须显式传 --supported\n');
  }
  for (const [file, info] of Object.entries(result.perFile)) {
    if (info.status === 'missing') {
      process.stdout.write('  ' + file + '  MISSING(' + info.side + ')\n');
      continue;
    }
    if (info.status === 'schema_error') {
      process.stdout.write('  ' + file + '  SCHEMA_ERROR(' + info.side + ': ' + info.reason + ')\n');
      continue;
    }
    const flags = { match: '✓', diff: '✗', unsupported: '·' };
    const parts = info.rows.map((r) => flags[r.status] + ' ' + r.kind + (r.status === 'diff' ? '(' + r.baseCount + '→' + r.curCount + ')' : ''));
    process.stdout.write('  ' + file + '  ' + info.status.toUpperCase() + '  ' + parts.join(' ') + '\n');
  }
  process.stdout.write('[compare] match=' + (result.totals.match || 0) +
    ' diff=' + (result.totals.diff || 0) +
    ' unsupported=' + (result.totals.unsupported || 0) +
    ' missing=' + (result.totals.missing || 0) +
    ' schema_error=' + (result.totals.schema_error || 0) + '\n');
  process.stdout.write('[compare] 结论: ' + (result.ok ? 'PASS（无 diff；unsupported 不计失败）' : 'FAIL（存在 diff）') + '\n');

  process.exitCode = result.ok ? 0 : 1;
}

main();
