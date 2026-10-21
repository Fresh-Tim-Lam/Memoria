/**
 * NewSurface —— 显示子系统插头「new」（阶段 2 · P2a + P2b + P2c + P4a：渲染最小闭环 + 编辑接线）
 *
 * 契约：docs/design/view-surface-contract.md
 *   §3.1 接口 / §4.2 交接 / §4.3 capabilities / §4.5 插头方法语义表
 *
 * ── P2a 实现范围（契约 §4.5.3）─────────────────────────────────────────────
 *   ✅ 必实现：mount / setText / flush / destroy（渲染最小闭环）
 *   ✅ isBlockFrozen：恒返回 false（P2a 只渲染，无块编辑/公式/表格冻结态）
 *   ⚠️ setMode：**记录 mode 且可查询（getMode()），不做视图 DOM 切换**。
 *      这是契约自身冲突的落地处理（见报告"契约偏离"节）：
 *        · §4.5.3 允许 setMode 抛 NotImpl；
 *        · 但 registry.js §4.2 交接第④步对 handoff.mode **无条件**调 setMode，
 *          throw 会被 catch ⇒ 回滚 ⇒ `switchTo('new')` 永远失败。
 *      故 P2a 取"记录 + 可查询 + 非法 mode 抛错"；三视图 DOM 仍归宿主 app.js。
 *      **P2b/P3 必须补真正的视图切换实现**（arch-contract 已登记）。
 *   ❌ 如实抛 NOT_IMPLEMENTED：无（P4c 起 getSrcRangeForSelection 已接通）
 *   ✅ P4a：applyEdit / undo / redo 复用**同一套编辑内核**（`MemoriaEditSync` +
 *      `MemoriaApp.surface.deleteRange/replaceRange`，门面委托，不复制实现）；
 *      预览区可编辑性随 `MemoriaEditHandler.editMode` 恢复（镜像 legacy app.js:1939）。
 *   ✅ P4c：getSrcRangeForSelection 复用 `MemoriaMapper.domToAst/astToSrc` 接通；
 *      applyBlockPatches 见文件内（块级增量 + 单步撤销 + 光标保持）。
 *   ✅ 最小实现：revealRange / getScrollAnchor / setScrollAnchor —— 只做"按块滚动"，
 *      不做 band/flash/选区（P4 EditCore 的范围）。它们被 registry 交接第④步调用，
 *      如实抛错会让真实 `switchTo('new')` 回滚，故按"可用即实现、不可用部分不伪造"落地。
 *
 * ── P2b 增量 ────────────────────────────────────────────────────────────────
 *   · setText 源码预处理补齐 `rewriteMdImagePaths`（与 legacy 同语义：本地图片 → `/files/...`）；
 *   · contentEditable 写入顺序与 legacy renderPreview 对齐（stamp 之后写）——
 *     属性插入顺序影响内联 HTML 序列化 ⇒ 影响 fidelity 签名的 htmlFingerprint；
 *   · 块类型扩展由 render-core 负责（code_block/table/image），本文件不感知具体 kind。
 *
 * ── 块身份（契约 §4.5.4）────────────────────────────────────────────────────
 *   · setText = `beginStamp({reset:true}) → 逐块 upsert → commit()`（全量重建，O(n)）；
 *   · 单例取 `window.MemoriaApp.blockIndex`（全 App 唯一实例）；缺失时（单测/非常规加载）
 *     退回自建实例，并在 `_indexSource` 上如实标注；
 *   · 本文件**不写** `data--src-line` / `data--src-line-end` / `data-block-id`
 *     —— 唯一写点是 `BlockIndex.upsert()`（门禁 check_line_attr_gate.js）；
 *   · flush 不碰索引；
 *   · id 语义：**id 标识身份，不保证内容不变**（Lead 裁决 task-22），不得用 id 变没变推断内容。
 *
 * ── capabilities（§4.3 正式字段）───────────────────────────────────────────
 *   全部如实：P2a 未做视口化 / 块级复用 / 块编辑 / 图片 caption 编辑 / 页内查找。
 */
window.createNewSurface = function createNewSurface(deps) {
  "use strict";
  var _name = "new";
  var _mode = null;                 // setMode 记录的 mode（可经 getMode() 查询）
  var _VALID_MODES = { source: 1, split: 1, preview: 1 };

  var _container = (deps && deps.container) || null;
  var _host = (deps && deps.host) || null;
  var _mounted = false;
  var _core = null;                 // MemoriaRenderCore 实例
  var _ownIndex = null;             // 仅当 window.MemoriaApp.blockIndex 缺失时的自建实例
  var _indexSource = null;          // "app" | "own"（诊断用）
  var _lastDoc = null;              // 最近一次渲染的 AST（只读快照引用）
  var _lastText = null;             // 最近一次渲染的正文真源
  var _lastUnsupported = [];        // 最近一次渲染中显式标记的未实现 kind

  /** 统一的"未实现"错误：带插头名 + 方法名 + 契约指针，便于日志定位。 */
  function _notImplemented(method, reason) {
    var err = new Error("[NewSurface] 未实现：" + method + "()");
    err.code = "NOT_IMPLEMENTED";
    err.surface = _name;
    err.method = method;
    err.reason = reason || "P2a 只实现渲染最小闭环（mount/setText/flush/destroy），编辑/选区能力留给后续片。";
    err.contract = "docs/design/view-surface-contract.md §4.5.3";
    return err;
  }

  function _state() { return (typeof window !== "undefined") ? window.state : null; }

  /** 渲染宿主：new surface 只接管**预览内容**；`#editor-split` 的 DOM 生命期归 app.js。 */
  function _previewEl() {
    if (typeof document === "undefined") return null;
    return document.getElementById("preview");
  }
  function _previewPaneEl() {
    if (typeof document === "undefined") return null;
    return document.getElementById("preview-pane") || _previewEl();
  }

  function _coreInstance() {
    if (!_core) {
      var RC = window.MemoriaRenderCore;
      if (!RC || typeof RC.createRenderCore !== "function") {
        throw new Error("[NewSurface] MemoriaRenderCore 未加载（index.html 脚本顺序：surface/render-core.js 须在 app.js 之前）");
      }
      // P6b：host 由 registry/app.js 注入（实现仍在 app.js）；DI 覆盖链接层/公式编排/块级重绘。
      var host = _host || (window.MemoriaSurface && window.MemoriaSurface.host) || null;
      _core = RC.createRenderCore({ host: host });
    }
    return _core;
  }

  /**
   * 块身份单例：优先复用 app.js 的唯一实例（契约 §4.5.4）；缺失时自建并如实标注。
   * 自建只用于单测/独立加载，**不得**与 app.js 实例并存（报告登记）。
   */
  function _index() {
    var app = window.MemoriaApp;
    if (app && app.blockIndex && typeof app.blockIndex.upsert === "function") {
      _indexSource = "app";
      return app.blockIndex;
    }
    if (!_ownIndex) {
      var BI = window.MemoriaBlockIndex;
      if (!BI || typeof BI.createBlockIndex !== "function") {
        throw new Error("[NewSurface] MemoriaBlockIndex 未加载，无法落块身份");
      }
      _ownIndex = BI.createBlockIndex();
    }
    _indexSource = "own";
    return _ownIndex;
  }

  /** 取块源码文本（供 BlockIndex 派生稳定 id）——与 app.js `_blockSrcTextOf` 同口径：
   *  从**真源正文**按 1-based 闭区间切片（不跑任何边界启发式）。 */
  function _blockSrcTextOf(block, rawText) {
    try {
      var st = _state();
      var src = (st && st.doc && typeof st.doc.body === "string") ? st.doc.body : String(rawText == null ? "" : rawText);
      var lines = src.split("\n");
      var out = [];
      for (var i = block.srcLine - 1; i <= block.srcLineEnd - 1 && i < lines.length; i++) out.push(lines[i]);
      return out.join("\n");
    } catch (e) {
      return "";
    }
  }

  // ── 源码预处理：本地图片相对路径 → `/files/...`（P2b）───────────────────────
  //   与 legacy `app.js rewriteMdImagePaths()` **同语义**：legacy 在 parse 前把
  //   `![x](./.memoria/images/x.png)` 重写成 `/files/...`，因此 DOM 里 img.src 是服务端路由；
  //   new 管线若不做这一步，A5/A6 与签名都会与 legacy 不同（且图片加载 404）。
  //   ⚠️ 已知重复：这段目前是 legacy 私有闭包逻辑的等价复刻（无法从 surface 门面调用）。
  //      待 P6 前收敛进 RenderCore 的 source-preprocess 契约（报告 §偏离登记）。
  function _escAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function _rewriteImagePath(src) {
    var MP = window.MemoriaMarkdownPreview;
    if (!MP || typeof MP.rewriteLocalImagePaths !== "function") return src;
    // 用带标记的 HTML 触发重写函数（与 legacy `_rewriteImagePath` 同一做法）
    var tmpHtml = '<img src="' + _escAttr(src) + '">';
    var rewritten = MP.rewriteLocalImagePaths(tmpHtml);
    var m = rewritten.match(/src="([^"]+)"/);
    return m ? m[1] : src;
  }
  function _rewriteMdImagePaths(md) {
    if (typeof md !== "string") return md;
    return md.replace(
      /!\[([^\]]*)\]\((?:<([^>]*)>|(\.[^\s)]+))(\s+"[^"]*")?\s*\)/g,
      function (full, alt, angleUrl, bareUrl, title) {
        var src = angleUrl !== undefined ? angleUrl : bareUrl;
        var rewritten = _rewriteImagePath(src);
        if (rewritten === src) return full; // 远程/绝对路径等未重写 ⇒ 保持原文（同 legacy）
        return "![" + alt + "](" + rewritten + (title || "") + ")";
      }
    );
  }

  // ── P6b：链接层 / 公式编排走 render-core 的**注入依赖**（实现仍在 app.js，不复制）──
  /**
   * 链接层后处理：调 `core.applyLinkLayer(preview)`（render-core 转发到 app.js 注入的 host，
   * 即 `postProcessWikilinks` + `bindPreviewLinks` 同一份实现）。
   * 缺失时如实 `onDegraded('link-layer:hook-missing')`（不伪造、不自造第二条路）。
   */
  function _applyHostLinkLayer(preview) {
    var core = _coreInstance();
    if (!core || typeof core.applyLinkLayer !== "function") {
      _callHost("onDegraded", "link-layer:hook-missing");
      return false;
    }
    try { core.applyLinkLayer(preview); return true; }
    catch (e) { _callHost("onDegraded", "link-layer:" + ((e && e.message) || e)); return false; }
  }

  // ── P2c：宿主渲染链接入（mermaid 替换 / 公式排版编排）──────────────────────────
  /** 与 legacy renderPreview 第 4/7 步同口径的不可编辑标记选择器（P2c 追加不可编辑块元素）。 */
  var _NON_EDITABLE_SEL = "mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error, .-lightbox-overlay, .-math-block, .-frontmatter";

  /** 给特殊元素写 `contentEditable=false`（幂等；legacy 第 4 步与第 7 步用同一集合）。 */
  function _setNonEditable(preview) {
    preview.querySelectorAll(_NON_EDITABLE_SEL).forEach(function (el) { el.contentEditable = "false"; });
  }

  /**
   * mermaid 渲染：**复用宿主公开链** `window.MemoriaMarkdownPreview.renderMermaidBlocks(container)`
   * （markdown-preview.js 导出；它负责把 `pre > code.language-mermaid` 替换成 `.-mermaid-container`，
   * 并经 BlockIndex 重投行号——不复制、不调 mermaid API）。返回宿主 Promise（可能为 null）。
   */
  function _runHostMermaidLayer(preview) {
    var MP = window.MemoriaMarkdownPreview;
    if (!MP || typeof MP.renderMermaidBlocks !== "function") {
      _callHost("onDegraded", "mermaid:hook-missing");
      return null;
    }
    try { return MP.renderMermaidBlocks(preview); }
    catch (e) { _callHost("onDegraded", "mermaid:" + ((e && e.message) || e)); return null; }
  }

  /**
   * 公式排版：调 `core.applyMathTypeset(preview, ast)`（render-core 转发到 app.js 注入的 host：
   * token 自增 → `queuePreviewMathTypeset` → 行内 mjx 打标；内部会写 `state.previewToken` /
   * `state._mathPending`，本文件**不碰**这两个状态）。缺省返回 null（调用方自行降级）。
   */
  function _applyHostMathTypeset(doc) {
    var core = _coreInstance();
    if (!core || typeof core.applyMathTypeset !== "function") {
      _callHost("onDegraded", "math-typeset:hook-missing");
      return null;
    }
    try { return core.applyMathTypeset(_previewEl(), doc); }
    catch (e) { _callHost("onDegraded", "math-typeset:" + ((e && e.message) || e)); return null; }
  }

  /** 解析 + 渲染 + 挂载 + BlockIndex 全量投射（setText 的唯一实现）。 */
  function _render(text, cause) {
    var preview = _previewEl();
    if (!preview) throw new Error("[NewSurface] setText: 找不到 #preview 容器");
    var st = _state();
    // ★ 真源优先级（修 P2c 尾块 bug）：**setText(text) 的 text 就是本次要渲染的正文**。
    //   legacy 适配器 `setText(text)` 的语义是：`state.doc.body = text; preview_body = null;
    //   renderPreview(doc)` ⇒ renderPreview 里的 `doc.preview_body || doc.body` 取到的是 text。
    //   而 `state.doc.preview_body` 是**上一次预览/编辑留下的派生字段**，可能与 handoff text 差一个
    //   末尾换行（后端 preview_body 保留文件尾 `\n`，body 已剥离）⇒ 若优先取它，会多 parse 出一个
    //   末尾 blank 块（scale-5k：legacy 3110 vs new 3111 的根因）。
    //   故与 legacy setText 同语义：**text 非空时一律以 text 为准**；text 缺失才回退到
    //   preview_body / body（仅用于非常规直接调用，不参与 surface 交接路径）。
    var rawSrc = (text != null)
      ? text
      : ((st && st.doc && st.doc.preview_body != null) ? st.doc.preview_body
        : (st && st.doc ? st.doc.body : null));
    var raw = (rawSrc == null) ? "" : String(rawSrc);

    // 与 legacy 同一份源码预处理（顺序也必须一致）：
    //   ① normalizeBody（公式/空白归一）② rewriteMdImagePaths（本地图片 → /files/...）
    var MP = window.MemoriaMarkdownPreview;
    var body = (MP && typeof MP.normalizeBody === "function") ? MP.normalizeBody(raw) : raw;
    body = _rewriteMdImagePaths(body);

    var P = window.MemoriaParser;
    if (!P || typeof P.parse !== "function") throw new Error("[NewSurface] setText: MemoriaParser 未加载");
    var doc = P.parse(body);
    // P4c：Mapper 的 domToAst/srcToAst/astToSrc 依赖其 `_currentDoc`；new 渲染用自己解析的
    // 同一份 body AST 同步过去（legacy renderPreview 也做 `M.setDoc(_doc)`，同口径）。
    var M = window.MemoriaMapper;
    if (M && typeof M.setDoc === "function") { try { M.setDoc(doc); } catch (e) { /* 映射失败不阻断渲染 */ } }

    var core = _coreInstance();
    var out = core.renderDocument(doc);

    // 挂载：与 legacy renderPreview 同形（清空 #preview 后追加 .-preview-content）
    preview.innerHTML = "";
    preview.appendChild(out.container);
    // P4a P1：镜像 legacy renderPreview（app.js:1939）——预览区可编辑性必须跟随 editMode，
    // 不能写死 false，否则编辑模式下 new 渲染后用户无法在预览区直接打字。
    preview.contentEditable = (window.MemoriaEditHandler && window.MemoriaEditHandler.editMode) ? "true" : "false";

    // 块身份：整篇路径 ⇒ beginStamp({reset:true}) → 逐块 upsert → commit（契约 §4.5.4）
    var idx = _index();
    idx.beginStamp({ reset: true });
    for (var i = 0; i < doc.blocks.length; i++) {
      var block = doc.blocks[i];
      // 行区间只认 parser 落盘值；缺字段如实跳过（与 app.js stampBlockLines 同判据）
      if (!(block.srcLine > 0) || !(block.srcLineEnd >= block.srcLine)) continue;
      idx.upsert({
        kind: block.type,
        srcLineStart: block.srcLine,
        srcLineEnd: block.srcLineEnd,
        blockSrcText: _blockSrcTextOf(block, raw),
        domEl: out.blockEls[i] || null,
      });
    }
    idx.commit();

    // 禁止特殊元素编辑（与 legacy renderPreview **第 4 步同一顺序**：stamp 之后才写
    // contentEditable）——属性插入顺序影响内联 HTML 序列化 ⇒ 影响 signatureNorm/htmlFingerprint。
    // P2c 追加 `.-math-block` / `.-frontmatter`：legacy 第 7 步对不可编辑块（math_block 等）
    // 的**块元素本身**也写 contentEditable，块元素不在第 4 步的标签选择器里。
    _setNonEditable(preview);

    // 链接层后处理（legacy renderPreview 第 5 步同序：stamp 之后）。
    // ★ 纪律：**不得复制** `postProcessWikilinks` / `bindPreviewLinks`——必须复用 app.js 同一函数
    //   （否则产生两份"真源"，legacy 一改 new 不改，C11 就测不出差异）。
    //   P6b：走 render-core 的注入依赖 `core.applyLinkLayer(root)`（host 实现在 app.js）。
    _applyHostLinkLayer(preview);

    // P2c：mermaid 替换 + 公式排版编排（**只调宿主链，绝不自己调 mermaid/MathJax API**）。
    //   legacy 顺序（renderPreview）：链接后处理 → await renderMermaidBlocks → 公式排队 → 第 7 步
    //   不可编辑标记。这里同序：mermaid 完成后补一次不可编辑标记（替换出来的容器/svg 才在 DOM 里），
    //   再交给 `core.applyMathTypeset`（token/typeset/行内打标全在 app.js 注入的 host 内）。
    var afterMermaid = function () {
      _setNonEditable(preview);
      _applyHostMathTypeset(doc);
    };
    var mmdPending = _runHostMermaidLayer(preview);
    if (mmdPending && typeof mmdPending.then === "function") mmdPending.then(afterMermaid, afterMermaid);
    else afterMermaid();

    _lastText = raw;
    _lastDoc = doc;
    _lastUnsupported = out.unsupported.slice();

    _callHost("onMeasure", {
      cause: cause || "external",
      blocks: out.count,
      unsupported: _lastUnsupported.slice(),
    });
    return doc;
  }

  function _callHost(name, a, b) {
    var h = _host || (window.MemoriaSurface && window.MemoriaSurface.host) || null;
    var fn = h && h[name];
    if (typeof fn === "function") {
      try { return fn(a, b); } catch (e) { /* 宿主回调异常不得影响引擎 */ }
    }
  }

  /** 按源码行滚动到块（只做滚动；band/flash 属 EditCore/P4）。返回是否找到目标块。 */
  function _scrollToLine(line, opts) {
    if (line == null) return false;
    var idx = _index();
    var hits = idx.atSrcLine(Number(line), { outermost: true });
    var handle = hits.length ? hits[0] : null;
    if (!handle || !handle.domEl) return false;
    if (opts && opts.scroll === false) return true;
    var pv = _previewPaneEl();
    if (!pv || typeof handle.domEl.getBoundingClientRect !== "function") return false;
    pv.scrollTop += handle.domEl.getBoundingClientRect().top - pv.getBoundingClientRect().top;
    return true;
  }

  /** P4c：捕获预览选区 → 源码坐标 + "指向的文本片段"（供 patch 后验证光标保持）。 */
  function _captureCursorState() {
    try {
      var sel = window.getSelection && window.getSelection();
      var preview = _previewEl();
      var M = window.MemoriaMapper;
      if (!sel || !sel.rangeCount || !preview || !M || typeof M.domToAst !== "function" || typeof M.astToSrc !== "function") return null;
      var r = sel.getRangeAt(0);
      if (!preview.contains(r.startContainer) || !preview.contains(r.endContainer)) return null;
      var ast = M.domToAst(r.startContainer, r.startOffset);
      if (!ast || ast.blockIndex < 0) return null;
      var src = M.astToSrc(ast.blockIndex, ast.nodePath || [], ast.offset || 0);
      if (!src) return null;
      var st = _state();
      var lines = (st && st.doc && typeof st.doc.body === "string") ? st.doc.body.split("\n") : [];
      var lineText = lines[src.line] || "";
      return {
        blockIndex: ast.blockIndex,
        nodePath: (ast.nodePath || []).slice(),
        offset: ast.offset || 0,
        line: src.line,          // 0-based
        lineNo: src.line + 1,    // 1-based（报告/验收口径）
        col: src.col,
        before: lineText.slice(Math.max(0, src.col - 24), src.col),
        after: lineText.slice(src.col, src.col + 24),
      };
    } catch (e) { return null; }
  }

  /** P4c：把光标放到块内第 textOffset 个渲染字符（Mapper 失败时的兜底）。 */
  function _placeTextOffset(domEl, textOffset) {
    if (!domEl) return null;
    try {
      var w = document.createTreeWalker(domEl, NodeFilter.SHOW_TEXT, null);
      var node = null; var remain = Math.max(0, textOffset);
      while (w.nextNode()) {
        var t = w.currentNode;
        if (remain <= t.data.length) { node = t; break; }
        remain -= t.data.length;
      }
      if (!node) return null;
      var r = document.createRange();
      r.setStart(node, remain);
      r.collapse(true);
      return r;
    } catch (e) { return null; }
  }

  /** P4c：批量 patch 后恢复光标（仅当光标块被 patch 时；未改块的 DOM/选区原样保留）。 */
  function _restoreCursorAfterPatches(cursorBefore, jobs) {
    if (!cursorBefore) return null;
    var job = null;
    for (var i = 0; i < jobs.length; i++) if (jobs[i].blockIndex === cursorBefore.blockIndex) { job = jobs[i]; break; }
    if (!job) return { touchedBlock: false, restored: false };   // 未改光标块 ⇒ 不动选区（DOM 未重建）
    var M = window.MemoriaMapper;
    var hs = _index().blocks();
    var handle = hs[job.blockIndex];
    var relLine = Math.max(0, cursorBefore.line - (job.oldStartLine - 1));
    var newLines = String(job.newText).split("\n");
    var tl = Math.min(relLine, newLines.length - 1);
    var tc = Math.min(cursorBefore.col, (newLines[tl] || "").length);
    // 光标块之前的所有 patch 的净行数增量（块数可能变化 ⇒ 不能再用 patch 前的 blockIndex/handle 定位）
    var deltaBefore = 0;
    for (var di = 0; di < jobs.length; di++) {
      if (jobs[di].blockIndex < cursorBefore.blockIndex) {
        deltaBefore += (String(jobs[di].newText).split("\n").length - jobs[di].oldLineCount);
      }
    }
    var targetLineNo = job.oldStartLine + deltaBefore + tl;   // 1-based（光标块被 patch）
    var abs0 = targetLineNo - 1;
    function readSel() {
      try {
        var s = window.getSelection && window.getSelection();
        if (!s || !s.rangeCount) return null;
        var r2 = s.getRangeAt(0);
        var a2 = M.domToAst(r2.startContainer, r2.startOffset);
        if (!a2 || a2.blockIndex < 0) return null;
        var s2 = M.astToSrc(a2.blockIndex, a2.nodePath || [], a2.offset || 0);
        return s2 ? { line: s2.line + 1, col: s2.col } : null;
      } catch (e) { return null; }
    }
    function put(range) {
      try { var s = window.getSelection(); s.removeAllRanges(); s.addRange(range); return true; } catch (e) { return false; }
    }
    var placed = null;
    var ast = null;
    if (M && handle && typeof M.srcToAst === "function" && typeof M.astToDom === "function") {
      ast = M.srcToAst(abs0, tc);
      var range = ast ? M.astToDom(ast.blockIndex, ast.nodePath || [], ast.offset || 0) : null;
      if (range && put(range)) placed = readSel();
    }
    // 兜底（块数可能变化 ⇒ patch 前的 blockIndex/handle 已失效）：按"新源码行号"重新找 DOM 块，
    // 把 (行内相对行, 列) 换算成块内文本偏移后直接落 Range。
    if (!placed || placed.line !== targetLineNo || placed.col !== tc) {
      try {
        var P2 = window.MemoriaParser;
        var st2 = _state();
        var body2 = (st2 && st2.doc && typeof st2.doc.body === "string") ? st2.doc.body : "";
        var fdoc = (P2 && typeof P2.parse === "function") ? P2.parse(body2) : null;
        if (fdoc && fdoc.blocks) {
          var domEl = null;
          var els = document.querySelectorAll("#preview .-src-block[data--src-line]");
          for (var ei = 0; ei < els.length; ei++) {
            var sLine = parseInt(els[ei].getAttribute("data--src-line"), 10);
            var eLine = parseInt(els[ei].getAttribute("data--src-line-end"), 10) || sLine;
            if (sLine > 0 && targetLineNo >= sLine && targetLineNo <= eLine) { domEl = els[ei]; break; }
          }
          if (domEl) {
            var relLine2 = targetLineNo - (parseInt(domEl.getAttribute("data--src-line"), 10) || targetLineNo);
            var bodyLines2 = body2.split("\n");
            var baseLine = (parseInt(domEl.getAttribute("data--src-line"), 10) || targetLineNo) - 1;
            var textOff = tc;
            for (var li = 0; li < relLine2; li++) textOff += (bodyLines2[baseLine + li] || "").length + 1;
            var r4 = _placeTextOffset(domEl, textOff);
            if (r4 && put(r4)) placed = readSel();
          }
        }
      } catch (e4) { /* 兜底失败：保留已放好的位置 */ }
    }
    if (placed) {
      var EH = window.MemoriaEditHandler;
      if (EH && M) {
        try {
          var selNow = window.getSelection();
          var a3 = M.domToAst(selNow.getRangeAt(0).startContainer, selNow.getRangeAt(0).startOffset);
          if (a3 && a3.blockIndex >= 0) EH.cursorAST = { blockIndex: a3.blockIndex, nodePath: (a3.nodePath || []).slice(), offset: a3.offset || 0 };
        } catch (e5) { /* noop */ }
      }
    }
    return { touchedBlock: true, restored: !!placed, intended: { line: targetLineNo, col: tc }, actual: placed, blockIndex: job.blockIndex };
  }

  /**
   * P4c：`applyBlockPatches(patches)` —— 块级增量替换（人机并发 B/C/D 层前置）。
   *
   * 契约：`patches: Array<{ blockId, srcLineStart, srcLineEnd, newText }>`
   *   · 按 `blockId`（BlockIndex 稳定 id）定位块；`srcLineStart/End` 仅作 id 失效时的兜底与校验。
   *   · 真源更新走既有 `MemoriaApp.surface.setBlockSource(..., {skipUndoGroup:true, skipRender:true})`，
   *     **不复制** splice/render 实现；行号属性仍只由 BlockIndex/宿主 `stampBlockLines` 写。
   *   · **按 `srcLineStart` 降序应用**：先改下面的块 ⇒ 上面块的 `__blockLineMap` 行区间不被移动，
   *     后续 patch 的定位才稳定；若升序，前面的插入会把后面块的行号推移导致错位。
   *   · 撤销：外层 `EditSync.beginUndoGroup()` + `endUndoGroup()` 包住全部写回 ⇒ 3 块 = **1 个撤销单元**。
   *   · 渲染：每个 patch 后调 `core.paintBlockPatch()`（render-core 注入的宿主块级 diff，只替换该块）；
   *     若块级 diff 不可用/失败 ⇒ 该步回退一次整篇 `renderPreview`（`_domBlockSig` 由宿主维护），
   *     **绝不静默留下"真源已改、画面未变"**。最后统一 `MemoriaApp.renderEditor(state.doc)` 一次。
   *   · 光标：未 patch 的块 DOM 不重建 ⇒ 选区原样保留（行号映射由 stampBlockLines 更新）；
   *     光标所在块被 patch ⇒ 按块内相对行/列 clamp 到新文本后经 Mapper 映射回 DOM，失败落到该块开头。
   * @returns {boolean} 全部 patch 成功返回 true；任一 blockId 无法解析/写回失败则 **fail-closed 返回 false**
   *   （解析阶段先整体校验，避免写了一半）。
   */
  function _applyBlockPatches(patches) {
    if (!Array.isArray(patches) || !patches.length) return false;
    var app = window.MemoriaApp;
    var st = _state();
    var BI = _index();
    if (!app || !app.surface || typeof app.surface.setBlockSource !== "function" || !st || !st.doc || !BI) return false;

    // 1) 解析全部 blockId → blockIndex（先全量校验，fail-closed，避免半写）
    var jobs = [];
    var byBi = {};
    for (var i = 0; i < patches.length; i++) {
      var p = patches[i] || {};
      var hs = BI.blocks();
      var bi = -1;
      for (var j = 0; j < hs.length; j++) { if (hs[j] && hs[j].id === p.blockId) { bi = j; break; } }
      if (bi < 0 && p.srcLineStart != null) {
        for (var j2 = 0; j2 < hs.length; j2++) {
          if (hs[j2] && hs[j2].srcLineStart === p.srcLineStart && hs[j2].srcLineEnd === p.srcLineEnd) { bi = j2; break; }
        }
      }
      if (bi < 0) return false;
      var text = String(p.newText == null ? "" : p.newText);
      if (byBi[bi] != null) { jobs[byBi[bi]].newText = text; continue; }   // 同块重复 patch ⇒ 后者覆盖
      byBi[bi] = jobs.length;
      jobs.push({ blockIndex: bi, blockId: p.blockId, oldStartLine: hs[bi].srcLineStart || 1, oldLineCount: Math.max(1, (hs[bi].srcLineEnd || hs[bi].srcLineStart || 1) - (hs[bi].srcLineStart || 1) + 1), newText: text });
    }
    // 2) 降序：先改下方的块，上方块的行区间保持稳定（见方法注释）
    jobs.sort(function (a, b) { return b.oldStartLine - a.oldStartLine; });

    var cursorBefore = _captureCursorState();
    var es = window.MemoriaEditSync;
    var grouped = !!(es && typeof es.beginUndoGroup === "function" && typeof es.endUndoGroup === "function");
    if (grouped) { try { es.beginUndoGroup(); } catch (e0) { grouped = false; } }
    var applied = 0;
    var fallbackRenders = 0;
    try {
      for (var k = 0; k < jobs.length; k++) {
        var job = jobs[k];
        var okWrite = app.surface.setBlockSource(job.blockIndex, job.newText, { skipUndoGroup: true, skipRender: true });
        if (!okWrite) return false;
        applied++;
        var painted = false;
        var core = _coreInstance();
        if (core && typeof core.paintBlockPatch === "function") painted = !!core.paintBlockPatch();
        if (!painted) {
          // 块级 diff 不可用 ⇒ 立即整篇重渲一次，刷新 map/_doc/_domBlockSig，后续 patch 才能继续定位
          fallbackRenders++;
          if (typeof app.renderPreview === "function") { try { app.renderPreview(st.doc); } catch (e1) { /* 兜底失败由最终渲染再补 */ } }
        }
      }
    } finally {
      if (grouped) { try { es.endUndoGroup(); } catch (e2) { /* 组收尾失败不阻断已写入真源 */ } }
    }
    // 3) 源码编辑器整篇只重建一次（不额外开窗：MemoriaApp.renderEditor 是公开门面）
    if (typeof app.renderEditor === "function") { try { app.renderEditor(st.doc); } catch (e3) { /* noop */ } }
    // 4) 光标保持（未改块不动；改所在块尽量恢复）
    var cursorAfter = _restoreCursorAfterPatches(cursorBefore, jobs);
    _lastText = st.doc.body;
    _lastPatchResult = { applied: applied, fallbackRenders: fallbackRenders, cursorBefore: cursorBefore, cursorAfter: cursorAfter, jobs: jobs.map(function (x) { return { blockIndex: x.blockIndex, blockId: x.blockId, oldStartLine: x.oldStartLine }; }) };
    return true;
  }

  var _lastPatchResult = null;

  var api = {
    /** 插头标识（诊断用）。 */
    name: _name,

    /** 契约 §4.3：能力声明 —— P2a 如实全 false / unsupported，不虚报。 */
    capabilities: {
      virtualization: false,      // 未做视口化（整篇真 DOM）
      incrementalRender: false,   // 未做块级复用（P2a 全量重建）
      blockEdit: false,           // 无代码/公式/表格/mermaid 块编辑
      imageCaption: false,        // 无图片 caption 编辑
      findInPage: "unsupported",  // 未建页内查找
    },

    /** §4.5.4：块身份单例来源（"app" = 复用 MemoriaApp.blockIndex；"own" = 单测自建）。 */
    getBlockIndexSource: function () { return _indexSource; },

    /** P2a 渲染覆盖（诊断）：已实现块 kind + 最近一次渲染中显式标记的未实现 kind。 */
    getRenderCoverage: function () {
      return {
        supportedBlockKinds: (_coreInstance() ? _coreInstance().supportedBlockKinds.slice() : []),
        unsupportedKindsSeen: _lastUnsupported.slice(),
      };
    },

    /** §4.5.1-① mount：空挂载即可（首次挂载不重放 setText/setMode，registry 已如此）。 */
    mount: function (container, host) {
      if (container) _container = container;
      if (host) _host = host;
      // P6b：核心实例可能先于 mount 创建 ⇒ 把注入的 host 补给它（同一引用，后来注入的方法也可见）
      if (_core && typeof _core.setHost === "function") _core.setHost(_host);
      _mounted = true;
    },

    /** §4.5.1-② setText：全量替换正文并全量重建块树。cause ∈ open|switch|reload|external。 */
    setText: function (text, cause) {
      if (!_mounted) throw new Error("[NewSurface] setText: 插头未 mount");
      _render(text, cause);
    },

    /**
     * §4.5.1-③ setMode：**只记录**，不切换视图 DOM（P2a 范围边界；三视图归宿主 app.js）。
     * 非法 mode ⇒ 抛错（契约失败语义，不静默接受任意字符串）。
     */
    setMode: function (mode) {
      if (typeof mode !== "string" || !_VALID_MODES[mode]) {
        var err = new Error("[NewSurface] setMode: 非法 mode '" + mode + "'（允许 source/split/preview）");
        err.code = "INVALID_MODE";
        err.surface = _name;
        throw err;
      }
      _mode = mode;
      // 如实上报"未做视图 DOM 切换"这一 P2a 降级（不伪造成功）。
      if (mode !== "preview") _callHost("onDegraded", "setMode:view-sync-not-implemented");
    },

    /** 查询记录的 mode（交接可验证性：getMode() === 请求的 mode）。 */
    getMode: function () { return _mode; },

    /** §4.5.1-④ applyEdit：P4a 起复用既有编辑内核（与 legacy 同一套门面委托，不复制实现）。
     *  - insertText / splitBlock / mergeBlock → `window.MemoriaEditSync`（真实编辑逻辑所在）
     *  - deleteRange / replaceRange → `MemoriaApp.surface`（与 legacy 相同的宿主门面）
     *  先 `flushRepaint()` 落定"停手才渲"的那一块（legacy F1 同口径）。
     */
    applyEdit: function (op) {
      if (!op || !op.kind) return false;
      var es = window.MemoriaEditSync;
      if (es && typeof es.flushRepaint === "function") { try { es.flushRepaint(); } catch (e) { /* 与 legacy 一致：停手重渲失败不阻塞编辑 */ } }
      if (!es) return false;
      var app = window.MemoriaApp;
      switch (op.kind) {
        case "insertText":
          return typeof es.insertText === "function" ? es.insertText(op.text || "") : false;
        case "splitBlock":
          return typeof es.splitParagraph === "function" ? es.splitParagraph() : false;
        case "mergeBlock":
          return typeof es.backspace === "function" ? es.backspace() : false;
        case "deleteRange": {
          var sDel = app && app.surface;
          return !!(sDel && typeof sDel.deleteRange === "function" && sDel.deleteRange(op.range || op.at || op));
        }
        case "replaceRange": {
          var sRep = app && app.surface;
          return !!(sRep && typeof sRep.replaceRange === "function" && sRep.replaceRange(op.range || op.at || op, op.text));
        }
        default:
          return false;
      }
    },

    /** §4.5.1-⑤ undo：复用 EditSync 的同一份撤销栈（P4a）。 */
    undo: function () {
      var es = window.MemoriaEditSync;
      if (es && typeof es.flushRepaint === "function") { try { es.flushRepaint(); } catch (e) { /* noop */ } }
      return !!(es && typeof es.undo === "function" && es.undo());
    },

    /** §4.5.1-⑥ redo：同上。 */
    redo: function () {
      var es = window.MemoriaEditSync;
      if (es && typeof es.flushRepaint === "function") { try { es.flushRepaint(); } catch (e) { /* noop */ } }
      return !!(es && typeof es.redo === "function" && es.redo());
    },

    /**
     * §4.5.1-⑦ revealRange：P2a 只做"按块滚动"（不做 band/flash，后者属 P4 EditCore）。
     * 失败（无块）如实返回，不抛（契约失败语义：落点失败不致命）。
     */
    /**
     * P4c §4.5 追加：`applyBlockPatches(patches)` —— 块级增量替换（人机并发 B/C/D 层前置）。
     * 契约见文件内 `_applyBlockPatches` 注释：按 blockId 定位、降序应用、单步撤销、块级渲染、
     * 光标保持；解析失败/写回失败 fail-closed 返回 false。
     */
    applyBlockPatches: function (patches) { return _applyBlockPatches(patches); },

    /** P4c 诊断出口（仅供探针/回归读最近一次 patch 的 applied/fallback/光标 before-after）。 */
    getLastPatchResult: function () { return _lastPatchResult; },

    revealRange: function (startLine, endLine, opts) {
      var ok = _scrollToLine(startLine, opts);
      if (!ok && startLine != null) _callHost("onDegraded", "revealRange:no-block");
    },

    /** §4.5.1-⑧ getScrollAnchor：读预览栏顶部块 → 源码行（1-based）。无 DOM 时返回 null。 */
    getScrollAnchor: function () {
      var pv = _previewPaneEl();
      var st = _state();
      var mode = _mode || (st ? st.viewMode : null) || "preview";
      if (!pv) return { mode: mode, srcLine: null };
      var top = pv.getBoundingClientRect().top;
      var blocks = _index().blocks();
      for (var i = 0; i < blocks.length; i++) {
        var el = blocks[i].domEl;
        if (!el || typeof el.getBoundingClientRect !== "function") continue;
        if (el.getBoundingClientRect().bottom >= top) return { mode: mode, srcLine: blocks[i].srcLineStart };
      }
      return { mode: mode, srcLine: null };
    },

    /** §4.5.1-⑨ setScrollAnchor：恢复滚动锚点（按块滚动；不恢复像素级 offset）。 */
    setScrollAnchor: function (a) {
      if (!a || a.srcLine == null) return;
      _scrollToLine(a.srcLine, { scroll: true });
    },

    /**
     * §4.5.1-⑩ getSrcRangeForSelection：预览选区 → 源码坐标（P4c 接通）。
     * 复用宿主 `MemoriaMapper.domToAst → astToSrc`（不复制映射实现），返回与 legacy 同形的
     * `{ startLine, startCol, endLine, endCol, collapsed }`（行 1-based；列 0-based，与 Data--src 口径一致）。
     * 选区不在预览内 / 映射失败 ⇒ 如实返回 null。
     */
    getSrcRangeForSelection: function () {
      var M = window.MemoriaMapper;
      var sel = window.getSelection && window.getSelection();
      var preview = _previewEl();
      if (!M || typeof M.domToAst !== "function" || typeof M.astToSrc !== "function") return null;
      if (!sel || !sel.rangeCount || !preview) return null;
      var r = sel.getRangeAt(0);
      if (!r || !preview.contains(r.startContainer) || !preview.contains(r.endContainer)) return null;
      var a = M.domToAst(r.startContainer, r.startOffset);
      var b = M.domToAst(r.endContainer, r.endOffset);
      if (!a || !b || a.blockIndex < 0 || b.blockIndex < 0) return null;
      var sa = M.astToSrc(a.blockIndex, a.nodePath || [], a.offset || 0);
      var sb = M.astToSrc(b.blockIndex, b.nodePath || [], b.offset || 0);
      if (!sa || !sb) return null;
      return {
        startLine: sa.line + 1,
        startCol: sa.col,
        endLine: sb.line + 1,
        endCol: sb.col,
        collapsed: !!sel.isCollapsed,
      };
    },

    /** §4.5.1-⑪ isBlockFrozen：P2a 无块编辑/公式/表格 ⇒ 恒不冻结。 */
    isBlockFrozen: function () { return false; },

    /** §4.5.1-⑫ destroy：尽力而为、不抛；不摘除 #preview（DOM 归宿主，切换方 setText 会重建）。 */
    destroy: function () {
      _mounted = false;
    },

    /** §4.5.1-⑬ flush：无"DOM 领先真源"窗口 ⇒ 返回当前快照；**不碰 BlockIndex**。 */
    flush: function () {
      var st = _state();
      var text = (st && st.doc && typeof st.doc.body === "string") ? st.doc.body : _lastText;
      return {
        text: text,
        cursor: null,               // P2a 无选区映射（getSrcRangeForSelection 抛 NotImpl）
        anchor: api.getScrollAnchor(),
        mode: _mode || (st ? st.viewMode : null),
        frozen: null,               // 冻结按需由 isBlockFrozen() 判定，不做预计算
      };
    },
  };

  return api;
};

/**
 * 自注册（不依赖 app.js 的装配块）。
 * 加载顺序：index.html 里 surface/registry.js → surface/render-core.js → new-surface.js →
 * app.js。P6c 起 legacy 适配器已删除；app.js 末尾装配块只 switchTo('new')。
 * 若 MemoriaSurface 缺失（单测/非常规加载）⇒ 不抛，留待宿主显式注册。
 *
 * 诊断出口（**只读**）：实例创建后挂 `window.__MemoriaNewSurface`，供 C11/保真对比等探针
 * 读取 getMode()/getRenderCoverage()/getBlockIndexSource() 等内部状态；生产路径不得依赖。
 */
(function selfRegister() {
  "use strict";
  try {
    var S = (typeof window !== "undefined") ? window.MemoriaSurface : null;
    if (S && typeof S.register === "function") {
      S.register("new", function (deps) {
        var inst = window.createNewSurface(deps);
        try { window.__MemoriaNewSurface = inst; } catch (e) { /* 诊断出口失败不得影响插头 */ }
        return inst;
      });
    }
  } catch (e) { /* 注册失败不得影响页面加载（插头缺省时 legacy 照常工作） */ }
})();
