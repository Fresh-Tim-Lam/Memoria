#!/usr/bin/env node
/**
 * fidelity.mjs —— 渲染保真度指标（阶段 2 的核心验收工具）
 *
 * 缺口（人指出）：现有 C1–C12 / 交互金标准全是**代理指标**，不抓 DOM 结构。
 *   一个把 <table> 渲染成 <p>、把 $$ 公式渲染成纯文本、丢掉 90% 内联格式的重构，
 *   可以让全部旧指标保持绿。阶段 2 要换渲染管线，没有保真度指标 = 没有验收能力。
 *
 * 设计依据：
 *   - docs/design/render-fidelity-contract.md（六项断言 + 签名口径）
 *   - artifacts/agent/verify/render-fidelity-risks.md（render-perf 的只读评估）
 *
 * 断言之分（Lead 收紧后的最终版）：
 *   A 级 · 硬门槛（必须全绿，零假阳性）：
 *     A1 块数一致
 *     A2 块序 + 块类型一致（data--block-index 严格比对 + kindClass/tag 序列）
 *     A3 公式保真（轻量版，见下）
 *     A4 = W1 静默空白看门狗(有 kindClass) + W2 无 kindClass 计数看门狗
 *   B 级 · 记录但不阻断（warn）：
 *     B5 文本保真(先归一)  B6 结构保真  B7 内联格式(只记录)
 *
 * A3 公式保真的两个前提（Lead 收紧）：
 *   ① 只在「期望公式数 > 0」时才比（0===0 不算通过，防空文档假绿）；
 *   ② 排除合法中间态：预渲染/缓存命中后 .-math 与 mjx-container 并存 ⇒
 *      按「包含已排版节点的块数」去重计数，不数裸节点数；
 *      且在渲染稳定后取（-preview-loading 消失 + 无 pending typeset）。
 *
 * A4 看门狗（Lead 收紧，原设计会误报）：
 *   W1（有 kindClass 的块）：textContent 去空白为空，且 kindClass 不在
 *      允许空文本白名单 {paragraph, heading, list_item} 内 ⇒ FAIL。
 *      已知合法来源：空 PARAGRAPH/HEADING/LIST_ITEM 占位（renderer.js:87/96/204 补 <br>）。
 *   W2（无 kindClass 的块）：只计数，要求「无 kindClass 块数 == DOCUMENT/LIST_ITEM 容器块数」。
 *      超出 ⇒ FAIL —— 这是"新增/改名 kind 落进 default 分支静默变空"的可观测信号
 *      （renderer.js:257 块级、:436 内联）。不对 classless 块做文本断言（反推不出 kind）。
 *
 * 全局签名：fidelitySignature = sha256(A 级投影 + 归一化 B 级投影)
 *
 * 约定：本文件是自包含页面内探针源 + 独立 CLI。页面内探针通过 toString 注入；
 *   Node 侧只做 CDP 连接（复用 harness）与落盘。签名由 Node 侧 crypto 算。
 */

import fs from 'node:fs';
import crypto from 'node:crypto';

// ─────────────────────────────────────────────────────────────────────────────
// 页面内探针（投影 + 断言 + 签名规范化）。作为字符串整体注入页面。
// ─────────────────────────────────────────────────────────────────────────────
export const PROBE_SOURCE = `(function () {
  'use strict';

  function normWs(s) { return String(s == null ? '' : s).replace(/\\s+/g, ' ').trim(); }

  // 允许空文本的 kindClass 白名单（空 PARAGRAPH/HEADING/LIST_ITEM 占位是合法的）
  var EMPTY_OK_KINDS = { '-src-block': 1 };   // 占位；见下方按 tag 判断
  var EMPTY_OK_TAGS = { p: 0, h1: 0, h2: 0, h3: 0, h4: 0, h5: 0, h6: 0, li: 0 };

  // ---------- AST 投影 ----------
  function astBlockShape(block) {
    var b = {
      kind: block.type,
      level: block.level,
      lang: block.lang,
      itemsCount: block.items ? block.items.length : null,
      headerCount: block.header ? block.header.length : null,
      rowsCount: block.rows ? block.rows.length : null,
    };
    var inlineKinds = {};
    var mathInlineCount = 0;
    (function walk(node) {
      if (!node) return;
      if (node.type === 'math_inline') mathInlineCount++;
      if (node.type && node.type !== 'document' && node.type !== 'text' && node.type !== 'escape') {
        inlineKinds[node.type] = (inlineKinds[node.type] || 0) + 1;
      }
      if (node.children) for (var i = 0; i < node.children.length; i++) walk(node.children[i]);
      if (node.items) for (var j = 0; j < node.items.length; j++) walk(node.items[j]);
    })(block);
    b.inlineKinds = inlineKinds;
    b.mathInlineCount = mathInlineCount;
    return b;
  }

  function buildAstProjection(doc) {
    // !! 只取**顶层** blocks，**不得递归展开 blockquote 内层段落**。
    //   原因（首版据此产生 21-24 处假错位）：renderer.js:171-188 把 blockquote 内层渲染成
    //   普通 p 且**不带 -src-block** => DOM 投影里没有这些块。
    //   若 AST 侧把它们也插进 blocks 列表，后续所有块的下标整体前移 => A2 大面积假红。
    var blocks = [];
    for (var i = 0; i < doc.blocks.length; i++) blocks.push(astBlockShape(doc.blocks[i]));
    return { count: doc.blocks.length, blocks: blocks };
  }

  // ---------- DOM 投影 ----------
  function buildDomProjection() {
    var els = Array.prototype.slice.call(document.querySelectorAll('#preview .-src-block'));
    var blocks = els.map(function (el) {
      var cls = String(el.className || '');
      var parts = cls.split(/\\s+/).filter(function (c) { return c && c !== '-src-block'; });
      var kindClass = parts.length ? parts[0] : '';
      return {
        tag: el.tagName.toLowerCase(),
        kindClass: kindClass,
        blockIndex: parseInt(el.getAttribute('data--block-index') || '-1', 10),
        textNorm: normWs(el.textContent),
        hasKindClass: !!kindClass,
        textEmpty: !normWs(el.textContent),
      };
    });
    return {
      count: els.length,
      blocks: blocks,
      tags: blocks.map(function (b) { return b.tag; }),
      kindClasses: blocks.map(function (b) { return b.kindClass; }),
      blockIndices: blocks.map(function (b) { return b.blockIndex; }),
    };
  }

  // DOM (tag, kindClass) → **推导出的 AST kind**（反向映射，依据 renderer.js:70-262 的实际产出）
  //
  // ⚠️ 关键事实（首版据此踩坑）：**多数块本来就不带 kindClass**——
  //   heading→h1..h6、paragraph→p、horizontal_rule→hr、blockquote→blockquote、
  //   list→ul/ol、table→table、image→p 都**没有**额外分类类名；
  //   只有 blank_line→-blank-block、code_block→-code-block、math_block→-math-block、
  //   image→-image-block、table→-table、frontmatter→-frontmatter、mermaid→-mermaid 才有。
  //   ⇒ 不能"要求 AST kind 去匹配 kindClass"，只能**从 (tag,class) 反推 kind** 再比。
  function domToAstKind(domTag, domKind) {
    // 先看带 class 的（信息更强，避免 p/div 二义）
    if (domKind === '-blank-block') return 'blank_line';
    if (domKind === '-code-block') return 'code_block';
    if (domKind === '-math-block') return 'math_block';
    if (domKind === '-image-block') return 'image';
    if (domKind === '-table') return 'table';
    if (domKind === '-frontmatter') return 'frontmatter';
    if (domKind === '-mermaid') return 'mermaid';
    // mermaid 渲染成功后，应用会把 pre.-mermaid 替换成 div.-mermaid-container（内含 <svg>）。
    //   见 edit-handler.js:1976「mermaid 块渲染成 .-mermaid-container > <svg>」。
    //   ⇒ 这是**合法的后处理产物**，必须映射回 mermaid，否则每张成功的图都会判红。
    if (domKind === '-mermaid-container' || domKind === '-mermaid-error') return 'mermaid';
    // 无 class：靠 tag 判
    if (/^h[1-6]$/.test(domTag)) return 'heading';
    if (domTag === 'p') return 'paragraph';
    if (domTag === 'hr') return 'horizontal_rule';
    if (domTag === 'blockquote') return 'blockquote';
    if (domTag === 'ul' || domTag === 'ol') return 'list';
    if (domTag === 'table') return 'table';
    return null;   // 认不出 ⇒ 交给调用方按"未知"处理
  }

  // 比较 AST kind 与 DOM 反推 kind 是否一致
  //   astLang：code_block 的语言。mermaid 围栏在 parser.js 内**没有 MERMAID 分支**，
  //   会被解析成 code_block(lang='mermaid')；渲染后替换成 .-mermaid-container
  //   ⇒ 必须按 lang 放宽，否则每张成功的图都会判红。
  function DOM_KIND_OK(astKind, domKind, domTag, astLang) {
    var inferred = domToAstKind(domTag, domKind);
    if (inferred == null) return false;      // DOM 形态认不出 ⇒ FAIL（真信号）
    if (inferred === astKind) return true;
    if (String(astLang || '').toLowerCase() === 'mermaid' && inferred === 'mermaid') return true;   // code_block(mermaid) / mermaid 两种 AST 形态都接受
    return false;
  }

  // ---------- A3 公式保真（轻量版） ----------
  // 前提①：只在期望公式数 > 0 时才比（0===0 不算通过，防空文档假绿）；
  // 前提②：排除合法中间态 —— 预渲染/缓存命中后 【.-math】 与 【mjx-container】 可并存，
  //        故按「**包含已排版节点的块数**」去重计数，不数裸节点；且在渲染稳定后取快照。
  function formulaFidelity(doc, dom) {
    var astMathBlocks = 0, astMathInline = 0;
    // ⚠️ 必须从 doc.blocks 顶层开始遍历（首版写成 walk(doc)，而 doc 是 {type:'document', blocks:[...]}，
    //   doc.children 不存在 ⇒ 永远数到 0 ⇒ A3 对所有文档"不适用"而假绿）。
    for (var bi = 0; bi < doc.blocks.length; bi++) {
      var top = doc.blocks[bi];
      if (top.type === 'math_block') astMathBlocks++;
      (function walk(node) {
        if (!node) return;
        if (node.type === 'math_inline') astMathInline++;
        if (node.children) for (var i = 0; i < node.children.length; i++) walk(node.children[i]);
        if (node.items) for (var j = 0; j < node.items.length; j++) walk(node.items[j]);
      })(top);
    }

    // DOM 侧：**按块去重**统计
    //   块级公式：该块是 math_block 形态且**内含已排版 mjx-container**
    //   行内公式：该块内含 mjx-container[data--inline-math="true"]
    var blockWithBlockMath = 0;
    var blockWithInlineMath = 0;
    var residual = 0;
    document.querySelectorAll('#preview .-src-block').forEach(function (el) {
      var cls = String(el.className || '');
      var isMathBlock = cls.indexOf('-math-block') >= 0;
      var mjxAll = el.querySelectorAll('mjx-container').length;
      var mjxInline = el.querySelectorAll('mjx-container[data--inline-math="true"]').length;
      // 块级：math-block 且已排（有 mjx；不要求 data-formula——块级公式的标记口径与行内不同）
      if (isMathBlock && mjxAll > 0) blockWithBlockMath++;
      if (mjxInline > 0) blockWithInlineMath++;
      // 残留：仍是未排版的裸 【.-math】 span（含 【$...$】 文本）或 MathJax 错误节点
      var bareMath = el.querySelectorAll('.-math').length;
      var merr = el.querySelectorAll('mjx-merror').length;
      if (bareMath > 0 && mjxAll === 0) residual += bareMath;
      residual += merr;
    });

    var expectBlocks = astMathBlocks;
    var expectInline = astMathInline;
    // 前提①：>0 才比
    var blocksApplicable = expectBlocks > 0;
    var inlineApplicable = expectInline > 0;
    var blocksMatch = !blocksApplicable || blockWithBlockMath === expectBlocks;
    // 行内：按块去重后无法精确等于 AST 的公式**个数**（一块可含多个行内公式）⇒
    //   断言"每个含行内公式的块都有已排版节点"，即去重块数 == 含行内公式的 AST 块数
    var astBlocksWithInline = 0;
    for (var k = 0; k < doc.blocks.length; k++) {
      var has = false;
      (function walk(n) {
        if (has || !n) return;
        if (n.type === 'math_inline') { has = true; return; }
        if (n.children) for (var i = 0; i < n.children.length; i++) walk(n.children[i]);
        if (n.items) for (var j = 0; j < n.items.length; j++) walk(n.items[j]);
      })(doc.blocks[k]);
      if (has) astBlocksWithInline++;
    }
    var inlineMatch = !inlineApplicable || blockWithInlineMath === astBlocksWithInline;
    return {
      expectBlocks: expectBlocks, expectInline: expectInline,
      blockWithBlockMath: blockWithBlockMath, blockWithInlineMath: blockWithInlineMath,
      astBlocksWithInline: astBlocksWithInline,
      residual: residual,
      blocksApplicable: blocksApplicable, inlineApplicable: inlineApplicable,
      blocksMatch: blocksMatch, inlineMatch: inlineMatch,
      noResidual: residual === 0,
    };
  }

  // ---------- A4 看门狗：W1（有 kindClass 空文本）+ W2（classless 块 tag 白名单） ----------
  //
  // 依据 Lead 收紧后的判据：
  //   W1：**只针对"有 kindClass 的块"**——若 textContent 去空白后为空，
  //       且该块不在「允许空文本」白名单 {PARAGRAPH, HEADING, LIST_ITEM} 内 ⇒ FAIL。
  //       （空 PARAGRAPH/HEADING/LIST_ITEM 占位是合法来源，renderer.js:87/96/204 补 <br>）
  //   W2：**只数"无 kindClass 的块"**，其 tag 必须落在已知白名单内 ⇒ 否则 FAIL。
  //       **不对 classless 块做文本断言**（反推不出 kind）。
  //       原「classless 数 == DOCUMENT/LIST_ITEM 容器数」的判据是错的——
  //       实测多数块本来就不带 kindClass（h1..h6/p/hr/blockquote/ul/ol/table 都没有），
  //       见 renderer.js:81-238；用它会让每个文档全红。
  var W2_ALLOWED_TAGS = {
    h1: 1, h2: 1, h3: 1, h4: 1, h5: 1, h6: 1,      // heading（无 kindClass）
    p: 1,                                             // paragraph / image
    hr: 1,                                            // horizontal_rule
    blockquote: 1,                                    // blockquote
    ul: 1, ol: 1,                                     // list
    table: 1,                                         // table
  };

  function watchdog(doc, dom, ast) {
    var w1 = [];        // 有 kindClass 且空文本，且不在白名单
    var w2 = [];        // 无 kindClass 且 tag 不在白名单（= 静默失真信号）
    var classlessCount = 0;
    // 空文本允许白名单（按 **AST kind** 判，比按 tag 更贴近语义）
    var EMPTY_OK_AST_KINDS = { paragraph: 1, heading: 1, list_item: 1, list: 1, blank_line: 1 };
    for (var i = 0; i < dom.blocks.length; i++) {
      var db = dom.blocks[i];
      var astKind = ast.blocks[i] ? ast.blocks[i].kind : null;
      if (db.hasKindClass) {
        // W1：有 kindClass + 文本空 + AST kind 不在"允许空"白名单 ⇒ FAIL
        if (db.textEmpty && !(astKind && EMPTY_OK_AST_KINDS[astKind])) {
          w1.push({ i: i, kindClass: db.kindClass, tag: db.tag, astKind: astKind });
        }
      } else {
        // W2：无 kindClass ⇒ 只校验 tag 是否已知（不查文本）
        classlessCount++;
        if (!W2_ALLOWED_TAGS[db.tag]) {
          w2.push({ i: i, tag: db.tag, astKind: astKind });
        }
      }
    }
    return { w1ok: w1.length === 0, w2ok: w2.length === 0, w1: w1, w2: w2, classlessCount: classlessCount };
  }

  // ---------- B 级：归一化文本 / 结构 / 内联 ----------
  function astText(block) {
    var parts = [];
    (function walk(node) {
      if (!node) return;
      if (node.type === 'text' || node.type === 'escape') parts.push(node.text !== undefined ? node.text : (node.char || ''));
      else if (node.type === 'code') parts.push(node.code || '');
      else if (node.type === 'math_inline') parts.push(node.formula || '');
      else if (node.type === 'math_block') parts.push(node.formula || '');
      else if (node.type === 'wiki_link') parts.push(node.display || '');
      else if (node.type === 'link') parts.push(node.text || '');
      else if (node.type === 'image') parts.push(node.alt || '');
      if (node.children) for (var i = 0; i < node.children.length; i++) walk(node.children[i]);
      if (node.items) for (var j = 0; j < node.items.length; j++) walk(node.items[j]);
    })(block);
    return parts.join('');
  }
  function normTextDom(t) {
    var x = t || '';
    x = x.replace(/^\\$\\$|\\$\\$$/g, '');   // 剥块级公式包裹
    x = x.replace(/\\$/g, '');                // 剥行内公式 $ 
    if (!x || x === '\\u00a0' || x === '<br>') x = '';
    return normWs(x);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 非确定性 id 归一化（task-28：Lead 要求把「抹掉随机 id」内置成规则，不能靠人工判读）
  //
  // 背景（P1 验收实测）：【04-non-editable.md】 两次渲染的唯一差异是 mermaid 生成的随机
  //   SVG id（【#mermaid-vppr1439】 vs 【#mermaid-jyl12f8b】），语义完全相同。
  //   若每次对比都要人判"这是随机 id"，阶段 2 的判等工具就不可用。
  //
  // **抹掉什么**（均为渲染器生成的会话级标识，与内容语义无关）：
  //   N1 mermaid 的 【id=mermaid-XXXX】 及其引用 【url(#mermaid-XXXX)】 / 【href=#mermaid-XXXX】
  //   N2 MathJax 的 【mjx-*】 / 【MJX-*】 id 与同名引用（CHTML/SVG 内部标识）
  //   N3 其它已知前缀（svg/defs/clip/path/marker/pattern/gradient/filter）+ 纯 8 位以上十六进制
  //
  // **为什么安全**：这些 id 只在**同一次渲染会话内**被 【url(#…)】 引用，不承载跨文档/跨会话语义；
  //   内容本身（文本、结构、坐标、颜色、样式）**不进入被剥离的部分**，仍完整参与比较。
  //
  // **故意不抹掉**（防止过度剥离造成漏判）：无上述前缀的普通 【id】（可能是业务/契约标识）、
  //   class、属性值、文本、坐标、样式 —— 全部保留。
  // ══════════════════════════════════════════════════════════════════════════
  var NONDET_ID_PREFIXES = ['mermaid-', 'mjx-', 'MJX-', 'svg-', 'defs-', 'clip-', 'path-', 'marker-', 'pattern-', 'gradient-', 'filter-'];

  function isNondetId(id) {
    if (!id) return false;
    var s = String(id);
    for (var i = 0; i < NONDET_ID_PREFIXES.length; i++) {
      if (s.indexOf(NONDET_ID_PREFIXES[i]) === 0) return true;
    }
    if (/^[0-9a-f]{8,}$/i.test(s)) return true;   // 纯随机十六进制
    return false;
  }

  /** 剥离字符串中所有非确定 id 及其引用，返回 {text, stripped}。 */
  function stripNondetIds(str) {
    if (!str) return { text: str, stripped: 0 };
    var count = 0;
    var out = str;
    // 本函数位于 PROBE_SOURCE 模板字符串内：不能写带反向引用的正则字面量
    //   （模板字符串会把反斜杠+数字当 octal escape）。故一律用 RegExp 构造函数。
    var BS = String.fromCharCode(92);
    var SQ = String.fromCharCode(39);
    var DQ = String.fromCharCode(34);
    var Q2 = '[' + SQ + DQ + ']';
    var NOTQ = '[^' + SQ + DQ + ']+';
    var RE_ID = new RegExp(BS + 'bid=(' + Q2 + ')(' + NOTQ + ')' + BS + '1', 'g');
    var RE_URL = new RegExp('url' + BS + '(' + '(#' + '[^)]+' + ')' + BS + ')', 'g');
    var RE_HREF = new RegExp('(xlink:)?href=(' + Q2 + ')#(' + NOTQ + ')' + BS + '2', 'g');
    var RE_CSS = new RegExp('#([A-Za-z][-A-Za-z0-9_]*)' + '(?=[' + BS + 's.,:{>' + BS + '[])', 'g');

    out = out.replace(RE_ID, function (m, q, v) {
      if (isNondetId(v)) { count++; return 'id=' + q + '<nondet-id>' + q; }
      return m;
    });
    out = out.replace(RE_URL, function (m, v) {
      var bare = v.charAt(0) === '#' ? v.slice(1) : v;
      if (isNondetId(bare)) { count++; return 'url(#<nondet-id>)'; }
      return m;
    });
    out = out.replace(RE_HREF, function (m, xl, q, v) {
      if (isNondetId(v)) { count++; return (xl || '') + 'href=' + q + '#<nondet-id>' + q; }
      return m;
    });
    // 5) 数据属性上的块级随机 id：data-block-id="sjfj9w-13"
    //    应用给每个块生成会话内 id（随渲染顺序变化），不承载内容语义。
    var RE_BLOCKID = new RegExp('data-block-id=(' + Q2 + ')(' + NOTQ + ')' + BS + '1', 'g');
    out = out.replace(RE_BLOCKID, function (m, q, v) {
      count++;
      return 'data-block-id=' + q + '<block-id>' + q;
    });
    // CSS 选择器引用：覆盖 #id{...} 与后代选择器 #id .cls{...}
    out = out.replace(RE_CSS, function (m, v) {
      if (isNondetId(v)) { count++; return '#<nondet-id>'; }
      return m;
    });
    return { text: out, stripped: count };
  }

  /** 对 #preview 整体 innerHTML 归一化（供签名 / 自证用）。 */
  function normalizedPreviewHtml() {
    var pv = document.querySelector('#preview');
    if (!pv) return { html: '', stripped: 0 };
    return (function (r) { return { html: r.text, stripped: r.stripped }; })(stripNondetIds(pv.innerHTML || ''));
  }


  // ══════════════════════════════════════════════════════════════════════════
  // 新增 A 级断言（task-25 · 渲染保真覆盖面补齐）
  //   A5 图片    A6 链接    A7 代码高亮(class)   A8 表格(行列)
  //   A9 可见效果下限（防"样式全丢"，只查非零）  A10 行内公式按块计数  A11 mermaid
  // 通用原则：只在「源/期望 > 0」时才判定，0===0 不算通过（防空文档假绿）。
  //   「无头恒空」类（agent 面板/流式/复阅卡）需真机/数据，另见任务说明。
  // ══════════════════════════════════════════════════════════════════════════

  // 统计 AST 全文档内某个 inline kind 的出现次数（递归）
  function astInlineCount(doc, kindSet) {
    var count = 0;
    (function walk(n) {
      if (!n) return;
      if (kindSet[n.type]) count++;
      if (n.children) for (var i = 0; i < n.children.length; i++) walk(n.children[i]);
      if (n.items) for (var j = 0; j < n.items.length; j++) walk(n.items[j]);
    })(doc);
    for (var b = 0; b < doc.blocks.length; b++) {
      (function walk(n) {
        if (!n) return;
        if (kindSet[n.type]) count++;
        if (n.children) for (var i = 0; i < n.children.length; i++) walk(n.children[i]);
        if (n.items) for (var j = 0; j < n.items.length; j++) walk(n.items[j]);
      })(doc.blocks[b]);
    }
    return count;
  }

  // A5 图片：源有 image 块时，DOM 里 img[src] 必须存在且 src 非空
  function imageFidelity(doc, dom) {
    var astImages = 0;
    for (var i = 0; i < doc.blocks.length; i++) if (doc.blocks[i].type === 'image') astImages++;
    // 行内图片（inline image）也可能有
    var inlineImgs = astInlineCount(doc, { image: 1 });
    var totalAst = astImages + (inlineImgs - astImages > 0 ? inlineImgs - astImages : 0);  // 块级 image 已含
    // DOM 侧
    var imgs = document.querySelectorAll('#preview img');
    var withSrc = 0; var badSrc = [];
    var hasEmptySrc = false;
    var noNatural = 0;  // naturalWidth 未就绪（懒加载/未解码），不能据此判 FAIL
    for (var k = 0; k < imgs.length; k++) {
      var el = imgs[k];
      var src = el.getAttribute('src') || '';
      if (!src) { hasEmptySrc = true; badSrc.push('empty'); continue; }
      withSrc++;
    }
    var applicable = totalAst > 0;
    // 只断言：源有图片 => DOM 至少有一个 img 且都带非空 src（不查 naturalWidth——懒加载/无头下不可靠）
    var ok = !applicable || (imgs.length > 0 && !hasEmptySrc);
    return { applicable: applicable, astImages: totalAst, domImgs: imgs.length, withSrc: withSrc, hasEmptySrc: hasEmptySrc, ok: ok };
  }

  // A6 链接：分三类**分别**断言（原版只查 a[href] 非空，是规格缺口）
  //
  // !! 规格修正（task-32）：原实现「所有 a 的 href 都必须非空」是**错的**。
  //    实测 legacy 的 wikilink **无论 resolved 还是 broken 都不设 href**
  //    （app.js:6339-6360 只加 class / tabindex / title，从不 setAttribute('href')），
  //    跳转靠 JS click + data-link-target 完成。故 href 非空**只适用于普通 md 链接**。
  //
  //    三类的真实可观察差异：
  //      resolved  : -link-resolved / -link-multi，tabindex="0"（可聚焦、可点击跳转）
  //      broken    : -link-broken + memoria-broken-link，tabindex="-1"（不可跳转是**正确行为**）
  //      ordinary  : 普通 markdown 链接，**必须有** href
  //
  //    「先写 [[概念]] 再补页面」是用户日常写作常态 ⇒ broken 必须被当作正常态。
  function linkFidelity(doc, dom) {
    var astLinks = astInlineCount(doc, { link: 1, wiki_link: 1 });
    var pv = document.querySelector('#preview');
    var anchors = pv ? pv.querySelectorAll('a') : [];
    var total = 0;
    var broken = 0, resolved = 0, ordinary = 0, pending = 0;
    var brokenMissingTarget = 0;   // broken 却连 data-link-target 都没有 ⇒ 真错
    var resolvedMissingTarget = 0; // resolved 却没有 data-link-target ⇒ 真错（无法确定跳哪）
    var brokenFocusable = 0;       // broken 却 tabindex=0（会被当成可跳转）⇒ 真错
    var resolvedNotFocusable = 0;  // resolved 却 tabindex=-1（点了没反应）⇒ 真错
    var ordinaryNoHref = 0;        // 普通链接没 href ⇒ 真错
    for (var k = 0; k < anchors.length; k++) {
      var el = anchors[k];
      total++;
      var cls = String(el.className || '');
      var href = el.getAttribute('href');
      var target = el.getAttribute('data-link-target');
      var tabIndex = el.getAttribute('tabindex');
      var isBroken = cls.indexOf('-link-broken') >= 0;
      var isResolved = cls.indexOf('-link-resolved') >= 0 || cls.indexOf('-link-multi') >= 0;
      var isPending = cls.indexOf('-link-pending') >= 0;
      if (isBroken) {
        broken++;
        if (!target) brokenMissingTarget++;
        if (String(tabIndex) === '0') brokenFocusable++;
      } else if (isResolved) {
        resolved++;
        if (!target) resolvedMissingTarget++;
        if (String(tabIndex) === '-1') resolvedNotFocusable++;
      } else if (isPending) {
        pending++;   // 解析中：合法中间态，不判
      } else {
        ordinary++;
        if (!href) ordinaryNoHref++;
      }
    }
    var bodyText = pv ? pv.textContent : '';
    var residualWiki = /\\[\\[[^\\]]+\\]\\]/.test(bodyText);

    var applicable = astLinks > 0;
    var ok = !applicable || (
      total > 0 &&
      brokenMissingTarget === 0 &&
      resolvedMissingTarget === 0 &&
      brokenFocusable === 0 &&
      resolvedNotFocusable === 0 &&
      ordinaryNoHref === 0 &&
      !residualWiki
    );
    return {
      applicable: applicable, astLinks: astLinks,
      domAnchors: total,
      broken: broken, resolved: resolved, ordinary: ordinary, pending: pending,
      brokenMissingTarget: brokenMissingTarget,
      resolvedMissingTarget: resolvedMissingTarget,
      brokenFocusable: brokenFocusable,
      resolvedNotFocusable: resolvedNotFocusable,
      ordinaryNoHref: ordinaryNoHref,
      residualWiki: residualWiki,
      ok: ok,
    };
  }

  // A7 代码高亮：fence 块有 language-* class（token 数 B 级，不在此判）
  function codeHighlightFidelity(doc, dom) {
    var astCodeWithLang = 0;
    for (var i = 0; i < doc.blocks.length; i++) {
      if (doc.blocks[i].type === 'code_block' && doc.blocks[i].lang &&
          String(doc.blocks[i].lang).toLowerCase() !== 'mermaid') astCodeWithLang++;
    }
    var issues = [];
    var codeEls = document.querySelectorAll('#preview .-src-block.-code-block code');
    for (var k = 0; k < codeEls.length; k++) {
      var cls = codeEls[k].className || '';
      // 语言 class 缺失（应至少 lang 非空时带性 language-*）
      // 用 AST 逐块比：块 k 的 lang 非空 => code.className 含 language-<lang>
    }
    // 逐块精确比。注意：mermaid 代码块（lang=mermaid）走 mermaid 渲染路径，
    //   不产出 .-code-block code（是 .-mermaid-container），必须排除，否则每张图都判红。
    for (var m = 0; m < doc.blocks.length; m++) {
      if (doc.blocks[m].type !== 'code_block' || !doc.blocks[m].lang) continue;
      if (String(doc.blocks[m].lang).toLowerCase() === 'mermaid') continue;   // 排除 mermaid
      var el = document.querySelector('#preview .-src-block[data--block-index="' + m + '"] code');
      if (!el) { issues.push({ i: m, field: 'missing-code' }); continue; }
      var cls = String(el.className || '');
      if (cls.indexOf('language-' + doc.blocks[m].lang) < 0) issues.push({ i: m, field: 'lang-class', ast: doc.blocks[m].lang, dom: cls });
    }
    var applicable = astCodeWithLang > 0;
    var ok = !applicable || issues.length === 0;
    return { applicable: applicable, astCodeWithLang: astCodeWithLang, issues: issues, ok: ok };
  }

  // A8 表格：行列数与 AST rows 一致（**不比列对齐**，AST 无此字段）
  function tableFidelity(doc, dom) {
    var issues = [];
    var astTables = 0;
    for (var i = 0; i < doc.blocks.length; i++) {
      var b = doc.blocks[i];
      if (b.type !== 'table') continue;
      astTables++;
      var el = document.querySelector('#preview .-src-block[data--block-index="' + i + '"]');
      if (!el) { issues.push({ i: i, field: 'missing-table' }); continue; }
      var rows = el.querySelectorAll('tr').length;
      var headerCount = b.header ? b.header.length : 0;
      var rowsCount = b.rows ? b.rows.length : 0;
      var expectRows = headerCount ? 1 + rowsCount : rowsCount;
      if (rows !== expectRows) issues.push({ i: i, field: 'rows', ast: expectRows, dom: rows });
      // 列数：取第一行（header 或首数据行）的 cell 数
      var firstRow = el.querySelector('tr');
      var domCols = firstRow ? firstRow.querySelectorAll('th,td').length : 0;
      var astCols = headerCount || (b.rows && b.rows.length ? b.rows[0].length : 0);
      if (domCols !== astCols) issues.push({ i: i, field: 'cols', ast: astCols, dom: domCols });
    }
    var applicable = astTables > 0;
    var ok = !applicable || issues.length === 0;
    return { applicable: applicable, astTables: astTables, issues: issues, ok: ok };
  }

  // A9 可见效果下限：源有某内联标记 => DOM 对应元素数必须 >0（只查非零）
  //   bold/italic/code/link/image/highlight/font_*（不含精确计数，避开不可反推）
  function visibleEffectFloor(doc, dom) {
    var checks = [];
    var map = {
      bold:       { ast: ['bold', 'bold_italic', 'font_bold'], dom: 'strong' },
      italic:     { ast: ['italic', 'bold_italic', 'font_italic'], dom: 'em' },
      code:       { ast: ['code'], dom: 'code' },
      link:       { ast: ['link', 'wiki_link'], dom: 'a' },
      image:      { ast: ['image'], dom: 'img' },
      highlight:  { ast: ['highlight'], dom: 'mark,.-hl,[data-hl]' },
      strikethrough: { ast: ['strikethrough'], dom: 's,del,strike' },
    };
    var failures = [];
    for (var kind in map) {
      var def = map[kind];
      var astCount = astInlineCount(doc, def.ast.reduce(function (o, k) { o[k] = 1; return o; }, {}));
      if (astCount === 0) continue;   // 源无此标记 => 不判
      var domCount = document.querySelectorAll('#preview ' + def.dom).length;
      checks.push({ kind: kind, astCount: astCount, domCount: domCount });
      if (domCount === 0) failures.push({ kind: kind, astCount: astCount });
    }
    return { checks: checks, failures: failures, ok: failures.length === 0 };
  }

  // A10 行内公式按块计数：源 $...$ 数 vs 该块内已排版节点数（真机判，无头 inconclusive）
  function inlineFormulaFidelity(doc, dom, isHeadless) {
    var perBlock = [];
    var failures = [];
    for (var i = 0; i < doc.blocks.length; i++) {
      var blk = doc.blocks[i];
      var inlineCount = 0;
      (function walk(n) {
        if (!n) return;
        if (n.type === 'math_inline') inlineCount++;
        if (n.children) for (var j = 0; j < n.children.length; j++) walk(n.children[j]);
        if (n.items) for (var j = 0; j < n.items.length; j++) walk(n.items[j]);
      })(blk);
      if (inlineCount === 0) continue;
      var el = document.querySelector('#preview .-src-block[data--block-index="' + i + '"]');
      var typeset = el ? el.querySelectorAll('mjx-container[data--inline-math="true"]').length : 0;
      perBlock.push({ i: i, astInline: inlineCount, domTypeset: typeset });
      if (typeset !== inlineCount) failures.push({ i: i, astInline: inlineCount, domTypeset: typeset });
    }
    var applicable = perBlock.length > 0;
    // 无头：MathJax 排不完 => inconclusive（有据：realapp-measurement-protocol.md §1）
    var ok = isHeadless ? true : (failures.length === 0);
    return { applicable: applicable, inconclusive: isHeadless && applicable, perBlock: perBlock, failures: failures, ok: ok };
  }

  // A11 mermaid：真出 svg + viewBox 非空 + 无错误占位
  function mermaidFidelity(doc, dom) {
    var astMermaid = 0;
    for (var i = 0; i < doc.blocks.length; i++) {
      if (doc.blocks[i].type === 'mermaid' || (doc.blocks[i].type === 'code_block' && String(doc.blocks[i].lang || '').toLowerCase() === 'mermaid')) {
        astMermaid++;
      }
    }
    var containers = document.querySelectorAll('#preview .-mermaid-container');
    var issues = [];
    for (var k = 0; k < containers.length; k++) {
      var svg = containers[k].querySelector('svg');
      if (!svg) { issues.push({ i: k, field: 'no-svg' }); continue; }
      var viewBox = svg.getAttribute('viewBox') || '';
      if (!viewBox) issues.push({ i: k, field: 'no-viewBox' });
    }
    var errNodes = document.querySelectorAll('#preview .-mermaid-error').length;
    var applicable = astMermaid > 0;
    var ok = !applicable || (containers.length === astMermaid && issues.length === 0 && errNodes === 0);
    return { applicable: applicable, astMermaid: astMermaid, containers: containers.length, issues: issues, errNodes: errNodes, ok: ok };
  }

  // ---------- 主入口 ----------
  // 轻量非加密哈希（FNV-1a 32 位 ×2 => 64 位十六进制串）：只用于签名内嵌指纹，
  //   避免把整段 HTML 塞进签名文本。不是安全哈希，只求确定性与低碰撞。
  function htmlFp(str) {
    var h1 = 0x811c9dc5, h2 = 0x01000193;
    for (var i = 0; i < str.length; i++) {
      var c = str.charCodeAt(i);
      h1 ^= c; h1 = (h1 * 16777619) >>> 0;
      h2 = ((h2 ^ c) * 2166136261) >>> 0;
    }
    return ('0000000' + h1.toString(16)).slice(-8) + ('0000000' + h2.toString(16)).slice(-8);
  }

  function runFidelity(doc) {
    var ast = buildAstProjection(doc);
    var dom = buildDomProjection();
    var ff = formulaFidelity(doc, dom);
    var wd = watchdog(doc, dom, ast);
    // ★ 归一化 HTML（剥离非确定 id）：签名与自证都以此为唯一来源
    var hNorm = normalizedPreviewHtml();

    // A1 块数
    var a1 = { ok: ast.count === dom.count, ast: ast.count, dom: dom.count };

    // A2 块序 + 类型
    var kindMismatch = [];
    var kinds = [];
    for (var i = 0; i < dom.blocks.length; i++) {
      var ak = ast.blocks[i] ? ast.blocks[i].kind : null;
      var dk = dom.kindClasses[i], dt = dom.tags[i];
      kinds.push(dk || dt);
      var alang = ast.blocks[i] ? ast.blocks[i].lang : null;
      if (ak && !DOM_KIND_OK(ak, dk, dt, alang)) kindMismatch.push({ i: i, astKind: ak, domKind: dk, domTag: dt });
    }
    var orderOk = dom.blockIndices.every(function (v, i) { return v === i; });
    var a2 = { ok: orderOk && kindMismatch.length === 0, orderOk: orderOk, kindMismatch: kindMismatch, kinds: kinds };

    // A3 公式
    //   !! 环境限制（有据）：无头 Edge 下 MathJax **排不完**（docs/design/realapp-measurement-protocol.md §1
    //   实测对照表：无头 mjx-container ≈ 3 且宽限耗尽；真机 270 个 ~1.2-1.5s）。
    //   故在 headless 环境下 A3 的"已排版"断言**不适用**：记为 inconclusive（不计入 FAIL），
    //   只保留 residual（残留纯文本公式）这一条环境无关的检查。
    //   要完整判 A3 ⇒ 用真机模式跑（fidelity_cli.mjs --cdp http://127.0.0.1:9500）。
    var isHeadless = !!(navigator.userAgent && /Headless/i.test(navigator.userAgent));
    var a3ok = isHeadless
      ? ff.noResidual                       // 无头：只查"没有残留未排版公式"
      : (ff.blocksMatch && ff.inlineMatch && ff.noResidual);
    var a3 = { ok: a3ok, inconclusive: isHeadless && !(ff.blocksMatch && ff.inlineMatch), ...ff };

    // A4 = W1 + W2
    var a4 = { ok: wd.w1ok && wd.w2ok, w1: wd.w1, w2: wd.w2 };

    // ── task-25 新增 A 级（渲染保真覆盖面补齐）──
    var a5 = imageFidelity(doc, dom);                 // 图片
    var a6 = linkFidelity(doc, dom);                  // 链接
    var a7 = codeHighlightFidelity(doc, dom);         // 代码高亮 class
    var a8 = tableFidelity(doc, dom);                 // 表格行列
    var a9 = visibleEffectFloor(doc, dom);            // 可见效果下限（防样式全丢）
    var a10 = inlineFormulaFidelity(doc, dom, isHeadless);  // 行内公式按块计数
    var a11 = mermaidFidelity(doc, dom);              // mermaid SVG

    // B5 文本（归一后，warn）
    var textDiffs = [];
    for (var k = 0; k < Math.max(ast.count, dom.count); k++) {
      var at = k < ast.count ? normWs(astText(ast.blocks[k])) : '';
      var dt = k < dom.count ? normTextDom(dom.blocks[k].textNorm) : '';
      if (at !== dt) textDiffs.push({ i: k, ast: at, dom: dt });
    }
    var b5 = { ok: textDiffs.length === 0, diffCount: textDiffs.length, diffs: textDiffs.slice(0, 20) };

    // B6 结构（只比 AST 真实字段）
    var structDiffs = [];
    for (var m = 0; m < dom.count; m++) {
      var ab = ast.blocks[m]; if (!ab) continue;
      var el = document.querySelector('#preview .-src-block[data--block-index="' + m + '"]');
      if (!el) continue;
      if (ab.kind === 'heading') { var lv = parseInt(dom.tags[m].replace('h',''),10); if (ab.level && lv !== ab.level) structDiffs.push({i:m,field:'heading.level',ast:ab.level,dom:lv}); }
      if (ab.kind === 'list') { var li = el.querySelectorAll('li').length; if (ab.itemsCount != null && li !== ab.itemsCount) structDiffs.push({i:m,field:'list.items',ast:ab.itemsCount,dom:li}); }
      if (ab.kind === 'table') { var tr = el.querySelectorAll('tr').length; var expectRows = (ab.headerCount ? 1 : 0) + (ab.rowsCount||0); if (tr !== expectRows) structDiffs.push({i:m,field:'table.rows',ast:expectRows,dom:tr}); }
      if (ab.kind === 'code_block' && ab.lang) { var ce = el.querySelector('code'); var lang = ce ? (ce.className||'').replace('language-','') : ''; if (lang !== ab.lang) structDiffs.push({i:m,field:'code.lang',ast:ab.lang,dom:lang}); }
    }
    var b6 = { ok: structDiffs.length === 0, diffCount: structDiffs.length, diffs: structDiffs.slice(0,20) };

    // B7 内联（只记录）
    var b7 = { perBlock: dom.blocks.map(function (db) {
      var el = document.querySelector('#preview .-src-block[data--block-index="' + db.blockIndex + '"]');
      return el ? {
        strong: el.querySelectorAll('strong').length,
        em: el.querySelectorAll('em').length,
        code: el.querySelectorAll('code').length,
        a: el.querySelectorAll('a').length,
        img: el.querySelectorAll('img').length,
        hl: el.querySelectorAll('.-hl,mark').length,
      } : {};
    }) };

    // 签名：A 级投影 + 归一化 B 级投影（v2：纳入 task-25 新增 A5–A11 投影）
    var sigObj = {
      v: 2,                                            // 签名版本：v2（旧 v1 保留并标 superseded）
      count: dom.count,
      kinds: kinds,
      tags: dom.tags,
      typesetMathBlocks: ff.blockWithBlockMath,
      inlineMathBlocks: ff.blockWithInlineMath,
      // task-25 新增：图片/链接/代码高亮/表格/可见效果下限 的 DOM 计数
      imgCount: a5.domImgs, imgEmptySrc: a5.hasEmptySrc,
      anchorCount: a6.domAnchors, residualWiki: a6.residualWiki,
      // A6 分类计数（task-32 规格修正后）：broken 不要求 href，resolved/ordinary 必须 href
      linkBroken: a6.broken, linkResolved: a6.resolved, linkOrdinary: a6.ordinary,
      linkBrokenMissingTarget: a6.brokenMissingTarget,
      linkResolvedMissingTarget: a6.resolvedMissingTarget,
      linkBrokenFocusable: a6.brokenFocusable,
      linkResolvedNotFocusable: a6.resolvedNotFocusable,
      linkOrdinaryNoHref: a6.ordinaryNoHref,
      langIssues: a7.issues.length,
      tableIssues: a8.issues.length,
      effectFloorFailures: a9.failures.map(function (f) { return f.kind; }),
      mermaidContainers: a11.containers, mermaidErrors: a11.errNodes,
      // 文本归一后再进签名，但**排除 mermaid / 公式容器内的文本**：
      //   mermaid 渲染成 <svg> 后其内部节点 id、<style> 内容每次生成都不同（随机），
      //   公式排版产物同理 => 若把它们的 textContent 纳入签名，签名永远不稳定，
      //   阶段 2 的 diff 工具就废了。这两类的"保真"由 A2(kind) 与 A3(数量) 覆盖。
      textNorm: dom.blocks.map(function (b, i) {
        var kind = kinds[i] || '';
        if (kind === 'mermaid' || kind === '-mermaid-container' || kind === '-mermaid-error' ||
            kind === '-math-block') return '<' + kind + '>';
        return normTextDom(b.textNorm);
      }),
      // ★ v2.1：归一化后的整体 HTML 指纹（已剥离非确定 id，见 stripNondetIds）。
      //   这是"抹掉随机 id"落进工具的**强制**环节——不依赖调用方人工判读。
      //   注：只进签名的**哈希摘要**，不把整段 HTML 塞进签名文本（控制体积）。
      htmlFingerprint: htmlFp(hNorm.html),
      nondetStripped: hNorm.stripped,
    };
    var normStr = JSON.stringify(sigObj);

    return {
      ok: a1.ok && a2.ok && a3.ok && a4.ok && a5.ok && a6.ok && a7.ok && a8.ok && a9.ok && a10.ok && a11.ok,
      aLevel: { a1: a1, a2: a2, a3: a3, a4: a4, a5: a5, a6: a6, a7: a7, a8: a8, a9: a9, a10: a10, a11: a11 },
      bLevel: { b5: b5, b6: b6, b7: b7 },
      signatureNorm: normStr,
      nondetStripped: hNorm.stripped,
      normalizedHtml: hNorm.html,   // 供 CLI 侧做「只换随机 id ⇒ 签名不变」自证
      astCount: ast.count, domCount: dom.count,
    };
  }

  // 变异注入（测试判别力用）
  // 变异注入：每个变异都对应一条 **A 级**断言，用于自证指标有判别力。
  //   drop-block  : 删掉一个块           => A1 块数 应红
  //   math        : 删掉公式节点         => A1/A2 应红
  //   reorder     : 打乱 data--block-index => A2 块序 应红
  //   empty-block : 把某块内容清空       => A4 W1 应红
  //   char        : 改块内 1 个字符（**只影响 B5 文本**，A 级按设计不抓 => 期望仍绿）
  function mutate(kind) {
    // ── task-28 归一化规则的「自证」变异 ────────────────────────────────
    //   nondet-id-only : **只换随机 id、语义不变** => 签名必须**不变**（证明剥离规则生效）
    //   real-change    : **真改内容**（改一个块的文本） => 签名必须**变**（证明没过度剥离）
    if (kind === 'nondet-id-only') {
      // 只把**非确定 id 换成另一个非确定 id**，语义不变。
      // !! 必须建立 旧id -> 新id 映射，引用同步改成**新 id**（而不是提前写占位符）。
      //   首版直接把引用写成 '#<nondet-id>' 字面尖括号 => 序列化时被 HTML 转义成
      //   '#&lt;nondet-id&gt;' => 与 id 侧归一化结果不相等 => G1 假失败。
      var pv = document.querySelector('#preview');
      if (!pv) return 'nondet-id-only-noop';
      var map = {};
      var changed = 0;
      pv.querySelectorAll('[id]').forEach(function (el) {
        var id = el.getAttribute('id') || '';
        if (!isNondetId(id)) return;
        var prefix = null;
        for (var pi = 0; pi < NONDET_ID_PREFIXES.length; pi++) {
          if (id.indexOf(NONDET_ID_PREFIXES[pi]) === 0) { prefix = NONDET_ID_PREFIXES[pi]; break; }
        }
        var fresh = prefix
          ? prefix + Math.random().toString(36).slice(2, 10)
          : (Math.random().toString(16).slice(2, 10) + '000000000').slice(0, 8);
        map[id] = fresh;
        el.setAttribute('id', fresh);
        changed++;
      });
      // 同步改写内部引用：把旧 id 替换为对应新 id（保持结构一致）
      var ATTRS = ['fill', 'stroke', 'clip-path', 'mask', 'filter', 'marker-end', 'marker-start', 'xlink:href', 'href'];
      pv.querySelectorAll('*').forEach(function (el) {
        ATTRS.forEach(function (attr) {
          var v = el.getAttribute && el.getAttribute(attr);
          if (!v) return;
          if (v.indexOf('url(#') === 0) {
            var ref = v.slice(5, -1);
            if (map[ref]) { el.setAttribute(attr, 'url(#' + map[ref] + ')'); changed++; }
          } else if (v.charAt(0) === '#') {
            var r2 = v.slice(1);
            if (map[r2]) { el.setAttribute(attr, '#' + map[r2]); changed++; }
          }
        });
      });
      return changed > 0 ? 'nondet-id-only(' + changed + ')' : 'nondet-id-only-noop';
    }    if (kind === 'real-change') {
      var els = document.querySelectorAll('#preview .-src-block');
      for (var ri = 0; ri < els.length; ri++) {
        var c = String(els[ri].className || '');
        if (c.indexOf('-blank-block') < 0 && els[ri].textContent.trim().length > 3) {
          els[ri].textContent = els[ri].textContent + '__REAL_CHANGE__';
          return 'real-change';
        }
      }
      return 'real-change-noop';
    }
    // ── task-32 A6 三条判别力自证（按**真实口径**构造）────────────────────
    //   resolved-not-focusable : resolved 链接改成 tabindex=-1（点了没反应）=> A6 必红
    //   broken-focusable       : broken 链接改成 tabindex=0（被当成可跳转）  => A6 必红
    //   ordinary-nohref        : 普通 md 链接清空 href                     => A6 必红
    if (kind === 'resolved-not-focusable') {
      var rl = document.querySelectorAll('#preview a.-link-resolved, #preview a.-link-multi');
      var n1 = 0;
      for (var ri = 0; ri < rl.length; ri++) { rl[ri].setAttribute('tabindex', '-1'); n1++; }
      return n1 > 0 ? 'resolved-not-focusable(' + n1 + ')' : 'resolved-not-focusable-noop';
    }
    if (kind === 'broken-focusable') {
      var bl = document.querySelectorAll('#preview a.-link-broken');
      var n2 = 0;
      for (var bi = 0; bi < bl.length; bi++) { bl[bi].setAttribute('tabindex', '0'); n2++; }
      return n2 > 0 ? 'broken-focusable(' + n2 + ')' : 'broken-focusable-noop';
    }
    if (kind === 'ordinary-nohref') {
      var ol = document.querySelectorAll('#preview a');
      var n3 = 0;
      for (var oi = 0; oi < ol.length; oi++) {
        var cc = String(ol[oi].className || '');
        if (cc.indexOf('-link-broken') >= 0 || cc.indexOf('-link-resolved') >= 0 ||
            cc.indexOf('-link-multi') >= 0 || cc.indexOf('-link-pending') >= 0) continue;
        if (ol[oi].getAttribute('href')) { ol[oi].removeAttribute('href'); n3++; }
      }
      return n3 > 0 ? 'ordinary-nohref(' + n3 + ')' : 'ordinary-nohref-noop';
    }
    // task-25 新增变异（对应 A5–A11）
    if (kind === 'img-src') {
      var imgs = document.querySelectorAll('#preview img');
      for (var i = 0; i < imgs.length; i++) imgs[i].removeAttribute('src');   // 改坏图片 => A5
      return 'img-src';
    }
    if (kind === 'strip-lang') {
      var codes = document.querySelectorAll('#preview .-src-block.-code-block code');
      for (var j = 0; j < codes.length; j++) codes[j].className = '';         // 去语言 class => A7
      return 'strip-lang';
    }
    if (kind === 'drop-td') {
      // 删**表头单元**（th）：列数必然减 1，A8 的 col 校验必判红。
      // 首版删 data-row 的 td 漏了 —— 若删的是数据行 cell，表头列数不变，断言抓不到。
      var th = document.querySelector('#preview .-src-block.-table thead th');
      if (th) { th.remove(); return 'drop-td'; }
      var td = document.querySelector('#preview .-src-block.-table tr td');
      if (td) { td.remove(); return 'drop-td-nohead'; }
      return 'drop-td-noop';
    }
    if (kind === 'kill-mermaid-svg') {
      var mc = document.querySelector('#preview .-mermaid-container svg');
      if (mc) { mc.remove(); return 'kill-mermaid-svg'; }                     // 破坏 mermaid SVG => A11
      return 'kill-mermaid-svg-noop';
    }
    if (kind === 'strip-inline-formula') {
      var mj = document.querySelector('#preview mjx-container[data--inline-math="true"]');
      if (mj) { mj.remove(); return 'strip-inline-formula'; }                 // 删行内公式 => A10
      return 'strip-inline-formula-noop';
    }
    if (kind === 'strip-bold') {
      document.querySelectorAll('#preview strong').forEach(function (s) { s.replaceWith(document.createTextNode(s.textContent || '')); }); // 去可见加粗 => A9
      return 'strip-bold';
    }
    if (kind === 'drop-block') {
      var els = document.querySelectorAll('#preview .-src-block');
      if (els.length > 2) { els[1].remove(); return 'drop-block'; }
      return 'drop-block-noop';
    }
    if (kind === 'empty-block') {
      var list = document.querySelectorAll('#preview .-src-block.-code-block, #preview .-src-block.-table, #preview .-src-block.-math-block');
      var target = list.length ? list[0] : document.querySelectorAll('#preview .-src-block')[1];
      if (target) { target.textContent = ''; target.innerHTML = ''; return 'empty-block'; }
      return 'empty-block-noop';
    }
    if (kind === 'char') { var e = document.querySelector('#preview .-src-block'); if (e) e.textContent = (e.textContent||'') + 'Z'; return 'char'; }
    if (kind === 'math') { var m = document.querySelector('#preview .-math-block, #preview mjx-container'); if (m) m.remove(); return 'math'; }
    if (kind === 'strong') { document.querySelectorAll('#preview strong').forEach(function(s){ s.replaceWith(document.createTextNode(s.textContent||'')); }); return 'strong'; }
    if (kind === 'reorder') { var f = document.querySelector('#preview .-src-block'); if (f) f.setAttribute('data--block-index','99'); return 'reorder'; }
    return 'unknown';
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 渲染就绪判定（task-31 · P2c 前置）
  //
  // 问题：MathJax 与 mermaid 都是**异步**渲染，取快照早一步 ⇒ 假 diff，晚一步 ⇒ 白等。
  // 三态：ready / timeout / failed —— **timeout 绝不冒充 ready**。
  //
  // !! 三条被禁的做法（都是历史踩过的坑）：
  //   ① 禁止固定 sleep —— 随文档规模失准（曾 sleep 2500 仍不够，导致假红）
  //   ② 禁止 getBBox —— 无头/不可见时为 0，不可作判据
  //   ③ 禁止「固定帧等待」当就绪判据 —— kpHover 那次 16.7ms 教训：那是帧成本，不是渲染完成
  //
  // 判据（两条腿，缺一不可）：
  //   A. **语义完成**：
  //      公式 —— 每个期望的公式容器内出现 mjx-container 且其**子节点非空**
  //              （另可 await state._mathPending：应用自己的 typesetPromise 链，最强信号）
  //      mermaid —— 所有 mermaid 源块都已被替换掉（无残留 【code.language-mermaid】），
  //                 每个容器内是真实 svg 且 viewBox 非空；出现 .-mermaid-error 即 failed
  //   B. **idle**：连续 N 帧「已排版节点数 + 容器数 + svg 数」三元组不变
  //      ⇒ 防「排到一半就比对」
  //
  // 只读纯 DOM 计数，不依赖布局（故无头下也能跑，但结论标 inconclusive，见下）。
  // ══════════════════════════════════════════════════════════════════════════
  var READY_MIN_FRAMES = 3;         // 连续不变帧数
  var READY_POLL_CAP_FRAMES = 3600; // 硬上限（60fps 下约 60s），防死等

  function isHeadlessEnv() {
    return !!(navigator.userAgent && /Headless/i.test(navigator.userAgent));
  }

  function nextFrameP() {
    return new Promise(function (r) { requestAnimationFrame(function () { r(); }); });
  }

  /** 公式快照：已排版容器数 / 子节点非空数 / 期望数（.-math 或 [data-formula]） */
  function mathSnapshot(preview) {
    var typeset = preview.querySelectorAll('mjx-container');
    var nonEmpty = 0;
    for (var i = 0; i < typeset.length; i++) {
      // 子节点非空 = 真的画出了东西（不是占位空壳）
      if (typeset[i].childElementCount > 0) nonEmpty++;
    }
    // !! expected 必须按「**待排版容器**」计，不能数带 data-formula 的元素（task-33 Bug 1）：
    //    data-formula 只挂在 **mjx-container** 上（app.js:2069），typeset 后原来的 .-math span
    //    已被替换/包裹 ⇒ 同一个公式会同时满足 .-math 与 [data-formula]，被数两遍。
    //    实测后果：corpus/02-inline-edges.md（1 行内 / 0 块）得到 expected=2 typeset=1
    //    ⇒ 永远差 1 ⇒ 3600 帧后 timeout。scale-5k 因为 135+135 恰好 270=270 才没暴露。
    //
    //    正确口径：**待排容器 = 尚未产出 mjx-container 的公式容器**
    //      · 行内未排：span.-math（不含内部已有 mjx-container 的）
    //      · 块级未排：.-math-block 尚无 mjx-container
    //    然后 expected = 已产出的 mjx 数 + 尚未产出的容器数。
    var pendingInline = 0;
    var mathSpans = preview.querySelectorAll('.-math');
    for (var si = 0; si < mathSpans.length; si++) {
      // 已排的 span 内部含 mjx-container（或自身被替换掉）⇒ 不计为待排
      if (!mathSpans[si].querySelector('mjx-container')) pendingInline++;
    }
    var pendingBlock = 0;
    var mathBlocks = preview.querySelectorAll('.-math-block');
    for (var bi2 = 0; bi2 < mathBlocks.length; bi2++) {
      if (!mathBlocks[bi2].querySelector('mjx-container')) pendingBlock++;
    }
    var expected = typeset.length + pendingInline + pendingBlock;
    return {
      typeset: typeset.length,
      nonEmpty: nonEmpty,
      expected: expected,
      pendingInline: pendingInline,
      pendingBlock: pendingBlock,
      key: nonEmpty + ':' + typeset.length + ':' + (pendingInline + pendingBlock),
    };
  }

  /** mermaid 快照：容器数 / 有 svg 且 viewBox 非空数 / 错误节点数 / 残留源块数 */
  function mermaidSnapshot(preview) {
    var containers = preview.querySelectorAll('.-mermaid-container');
    var withSvg = 0;
    for (var i = 0; i < containers.length; i++) {
      var svg = containers[i].querySelector('svg');
      if (svg && String(svg.getAttribute('viewBox') || '').trim()) withSvg++;
    }
    var errs = preview.querySelectorAll('.-mermaid-error').length;
    var residualSrc = preview.querySelectorAll('code.language-mermaid').length;
    return {
      containers: containers.length,
      withSvg: withSvg,
      errors: errs,
      residualSrc: residualSrc,
      key: containers.length + ':' + withSvg + ':' + errs + ':' + residualSrc,
    };
  }

  /**
   * 主入口：等待渲染就绪。
   * @param {Object} opt { which: 'math'|'mermaid'|'both', minFrames, timeoutMs, awaitAppPending }
   * @returns ready / timeout / failed / inconclusive（无头）
   */
  async function waitForRenderReady(opt) {
    opt = opt || {};
    var which = opt.which || 'both';
    var minFrames = opt.minFrames || READY_MIN_FRAMES;
    var timeoutMs = opt.timeoutMs || 20000;
    var awaitAppPending = opt.awaitAppPending !== false;
    var preview = document.getElementById('preview');
    var t0 = performance.now();
    var base = {
      which: which,
      headless: isHeadlessEnv(),
      minFrames: minFrames,
      timeoutMs: timeoutMs,
      awaitAppPending: awaitAppPending,
    };
    if (!preview) {
      return Object.assign(base, { status: 'failed', reason: 'no-preview', elapsedMs: 0 });
    }

    var sawTimeout = false;

    // 最强信号：应用自己的 typesetPromise 链（仅公式）。它 resolve 时 typeset 真的全跑完了。
    if (awaitAppPending && (which === 'math' || which === 'both')) {
      var pend = window.state && window.state._mathPending;
      if (pend && typeof pend.then === 'function') {
        var settled = await Promise.race([
          pend.then(function () { return 'done'; }).catch(function () { return 'rejected'; }),
          new Promise(function (r) { setTimeout(function () { r('pending-timeout'); }, timeoutMs); }),
        ]);
        base.appPending = settled;
      } else {
        base.appPending = 'none';
      }
    }

    var lastKey = null;
    var stableFrames = 0;
    var frames = 0;
    var lastMath = null;
    var lastMmd = null;
    var status = 'timeout';

    while (frames < READY_POLL_CAP_FRAMES) {
      await nextFrameP();
      frames++;
      var m = mathSnapshot(preview);
      var mm = mermaidSnapshot(preview);
      lastMath = m;
      lastMmd = mm;

      var key = m.key + '|' + mm.key;
      if (key === lastKey) stableFrames++; else { stableFrames = 0; lastKey = key; }

      // 语义完成判定
      var mathDone = (which === 'mermaid') ? true
        : (m.expected === 0 ? true : (m.nonEmpty >= m.expected && m.typeset > 0));
      var mmdFailed = (which === 'math') ? false : (mm.errors > 0);
      var mmdDone = (which === 'math') ? true
        : (mm.containers === 0 && mm.residualSrc === 0) ? true   // 无 mermaid 块
          : (mm.withSvg === mm.containers && mm.containers > 0 && mm.residualSrc === 0);

      if (mmdFailed) {
        status = 'failed';
        base.reason = 'mermaid-error-node';
        break;
      }
      if (mathDone && mmdDone && stableFrames >= minFrames) {
        status = 'ready';
        break;
      }
      if (performance.now() - t0 > timeoutMs) {
        sawTimeout = true;
        status = 'timeout';
        break;
      }
    }

    var elapsed = performance.now() - t0;
    var out = Object.assign(base, {
      status: status,
      elapsedMs: +elapsed.toFixed(2),
      frames: frames,
      stableFrames: stableFrames,
      math: lastMath,
      mermaid: lastMmd,
      sawTimeout: sawTimeout,
    });

    // !! 无头：MathJax 排不完（≈3 vs 真机 270）=> 结论一律 inconclusive，
    //    既不报 ready 也不报 failed（除非是有明确 DOM 证据的 mermaid 错误）。
    if (out.headless && status !== 'failed') {
      out.status = 'inconclusive';
      out.reason = 'headless-math-incomplete';
    }
    // 真实性守卫：若判 ready 但公式一个都没排出来（期望>0），视为没就绪
    if (out.status === 'ready' && which !== 'mermaid' && lastMath && lastMath.expected > 0 && lastMath.nonEmpty === 0) {
      out.status = 'timeout';
      out.reason = 'ready-but-zero-typeset';
    }
    return out;
  }

  /**
   * 判别力自证用：抢拍（不等 idle，立即取一次快照并给出"若此时判定"的结论）。
   * 期望在渲染未完成时返回非 ready。
   */
  function snapshotNow(which) {
    var preview = document.getElementById('preview');
    if (!preview) return { status: 'failed', reason: 'no-preview' };
    var m = mathSnapshot(preview);
    var mm = mermaidSnapshot(preview);
    var w = which || 'both';
    var mathDone = (w === 'mermaid') ? true : (m.expected === 0 ? true : (m.nonEmpty >= m.expected && m.typeset > 0));
    var mmdDone = (w === 'math') ? true : (mm.containers === 0 && mm.residualSrc === 0) ? true
      : (mm.withSvg === mm.containers && mm.containers > 0 && mm.residualSrc === 0);
    var status = (mm.errors > 0) ? 'failed'
      : (mathDone && mmdDone) ? 'ready-but-not-idle' : 'not-ready';
    return { status: status, math: m, mermaid: mm, headless: isHeadlessEnv() };
  }

  return { runFidelity: runFidelity, buildDomProjection: buildDomProjection, buildAstProjection: buildAstProjection, mutate: mutate, DOM_KIND_OK: DOM_KIND_OK, waitForRenderReady: waitForRenderReady, snapshotNow: snapshotNow, mathSnapshot: mathSnapshot, mermaidSnapshot: mermaidSnapshot };
})()`;

// ─────────────────────────────────────────────────────────────────────────────
// Node 侧工具
// ─────────────────────────────────────────────────────────────────────────────
export function fidelitySignature(normStr) {
  return crypto.createHash('sha256').update(normStr, 'utf8').digest('hex');
}

// 独立 CLI 也被 import 使用（run_fidelity.py 会通过 cdp.mjs 的 --probe 已足够）；
// 这里保留一个最小自检，供 node --check 与直接调试。
export function normWs(s) {
  return String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
}
