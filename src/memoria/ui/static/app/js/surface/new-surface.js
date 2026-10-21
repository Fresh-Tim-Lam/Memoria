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
 *   ❌ 如实抛 NOT_IMPLEMENTED：getSrcRangeForSelection
 *      （P4a 只接 applyEdit/undo/redo；选区→源码映射仍未实现，返回假空值是契约红线，绝不做）。
 *   ✅ P4a：applyEdit / undo / redo 复用**同一套编辑内核**（`MemoriaEditSync` +
 *      `MemoriaApp.surface.deleteRange/replaceRange`，门面委托，不复制实现）；
 *      预览区可编辑性随 `MemoriaEditHandler.editMode` 恢复（镜像 legacy app.js:1939）。
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
      _core = RC.createRenderCore();
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

  // ── 链接层后处理（K4 临时豁免，复用不重写）──────────────────────────────────
  /**
   * 调用宿主（app.js）的**同一份**链接层后处理：
   *   `window.MemoriaApp.surface.applyPreviewLinkLayer(root)`（Lead 2026-10-21 开窗）。
   *
   * ★ 纪律：本文件**不复制** `postProcessWikilinks` / `bindPreviewLinks` 的实现。
   *   复制 = 两份真源 = legacy 改后 new 不会跟 = C11 等价性失效。
   *   K4 终局（P6）：这两函数迁进 `render-core.js`，开窗与本调用一并删除。
   *
   * 入口缺失时的降级：如实 `onDegraded('link-layer:hook-missing')`（不伪造、不自造第二条路）。
   * 无 wikilink 的文档不受影响；含 wikilink 的文档此时签名会 diff，属明确信号。
   */
  function _applyHostLinkLayer(preview) {
    var app = (typeof window !== "undefined") ? window.MemoriaApp : null;
    var fn = app && app.surface && app.surface.applyPreviewLinkLayer;
    if (typeof fn === "function") {
      try { fn(preview); return true; }
      catch (e) { _callHost("onDegraded", "link-layer:" + ((e && e.message) || e)); return false; }
    }
    _callHost("onDegraded", "link-layer:hook-missing");
    return false;
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
   * 公式排版：**复用宿主编排入口** `MemoriaApp.surface.applyPreviewMathTypeset(root, ast)`
   * （app.js 开窗：token 自增 → `queuePreviewMathTypeset` → 行内 mjx 打标；内部会写
   * `state.previewToken` / `state._mathPending`，本文件**不碰**这两个状态）。
   */
  function _applyHostMathTypeset(doc) {
    var app = (typeof window !== "undefined") ? window.MemoriaApp : null;
    var fn = app && app.surface && app.surface.applyPreviewMathTypeset;
    if (typeof fn !== "function") {
      _callHost("onDegraded", "math-typeset:hook-missing");
      return null;
    }
    try { return fn(_previewEl(), doc); }
    catch (e) { _callHost("onDegraded", "math-typeset:" + ((e && e.message) || e)); return null; }
  }

  /** 解析 + 渲染 + 挂载 + BlockIndex 全量投射（setText 的唯一实现）。 */
  function _render(text, cause) {
    var preview = _previewEl();
    if (!preview) throw new Error("[NewSurface] setText: 找不到 #preview 容器");
    var st = _state();
    // ★ 真源优先级（修 P2c 尾块 bug）：**setText(text) 的 text 就是本次要渲染的正文**。
    //   legacy `legacy-surface.setText(text)` 的语义是：`state.doc.body = text; preview_body = null;
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
    //   K4 临时豁免入口（Lead 2026-10-21 开窗）：`MemoriaApp.surface.applyPreviewLinkLayer(root)`；
    //   终局 P6 把这两个函数迁进 render-core，本调用随之删除（见 app.js 该方法的注释）。
    _applyHostLinkLayer(preview);

    // P2c：mermaid 替换 + 公式排版编排（**只调宿主链，绝不自己调 mermaid/MathJax API**）。
    //   legacy 顺序（renderPreview）：链接后处理 → await renderMermaidBlocks → 公式排队 → 第 7 步
    //   不可编辑标记。这里同序：mermaid 完成后补一次不可编辑标记（替换出来的容器/svg 才在 DOM 里），
    //   再交给宿主的 `applyPreviewMathTypeset`（token/typeset/行内打标全在宿主内，见 app.js）。
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

    /** §4.5.1-⑩ getSrcRangeForSelection：P2a 无选区映射 ⇒ 如实抛 NotImpl（不返回假 null）。 */
    getSrcRangeForSelection: function () { throw _notImplemented("getSrcRangeForSelection"); },

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
 * 加载顺序：index.html 里 surface/registry.js → surface/render-core.js → legacy-surface.js →
 * new-surface.js → app.js，故此处 MemoriaSurface 已就绪；app.js 末尾装配块随后注册 legacy
 * 并 switchTo('legacy')，两者互不干扰 ⇒ list() 最终为 ['legacy', 'new']。
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
