/**
 * NewSurface —— 显示子系统插头「new」（阶段 2 · P2a：渲染最小闭环）
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
 *   ❌ 如实抛 NOT_IMPLEMENTED：applyEdit / undo / redo / getSrcRangeForSelection
 *      （P2a 只渲染不编辑；返回假空值是契约红线，绝不做）。
 *   ✅ 最小实现：revealRange / getScrollAnchor / setScrollAnchor —— 只做"按块滚动"，
 *      不做 band/flash/选区（P4 EditCore 的范围）。它们被 registry 交接第④步调用，
 *      如实抛错会让真实 `switchTo('new')` 回滚，故按"可用即实现、不可用部分不伪造"落地。
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

  /** 解析 + 渲染 + 挂载 + BlockIndex 全量投射（setText 的唯一实现）。 */
  function _render(text, cause) {
    var preview = _previewEl();
    if (!preview) throw new Error("[NewSurface] setText: 找不到 #preview 容器");
    var st = _state();
    // 与 legacy renderPreview 同源：preview_body（后端预清洗）优先，其次传入 text
    var rawSrc = (st && st.doc && st.doc.preview_body != null) ? st.doc.preview_body : text;
    var raw = (rawSrc == null) ? "" : String(rawSrc);

    // 与 legacy 同一份源码预处理（normalizeBody）。P2a 不复刻 rewriteMdImagePaths：
    // image 块在 P2a 未实现 ⇒ 会显式 data-unsupported，不会静默丢内容（报告登记限制）。
    var MP = window.MemoriaMarkdownPreview;
    var body = (MP && typeof MP.normalizeBody === "function") ? MP.normalizeBody(raw) : raw;

    var P = window.MemoriaParser;
    if (!P || typeof P.parse !== "function") throw new Error("[NewSurface] setText: MemoriaParser 未加载");
    var doc = P.parse(body);

    var core = _coreInstance();
    var out = core.renderDocument(doc);

    // 挂载：与 legacy renderPreview 同形（清空 #preview 后追加 .-preview-content）
    preview.innerHTML = "";
    preview.appendChild(out.container);
    // 禁止特殊元素编辑（与 legacy renderPreview 第 4 步同一选择器；P2a 语料无这些块，
    // 但保留同口径以防后续片接入后行为漂移）
    preview.querySelectorAll(
      "mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error, .-lightbox-overlay"
    ).forEach(function (el) { el.contentEditable = "false"; });
    preview.contentEditable = "false";

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

    /** §4.5.1-④ applyEdit：P2a 只渲染不编辑 ⇒ 如实抛 NotImpl（绝不返回假空值）。 */
    applyEdit: function () { throw _notImplemented("applyEdit"); },

    /** §4.5.1-⑤ undo：同上。 */
    undo: function () { throw _notImplemented("undo"); },

    /** §4.5.1-⑥ redo：同上。 */
    redo: function () { throw _notImplemented("redo"); },

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
