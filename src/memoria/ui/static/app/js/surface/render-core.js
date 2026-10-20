/**
 * MemoriaRenderCore —— 新渲染管线（阶段 2 · P2a：块级骨架）
 *
 * ── 定位 ─────────────────────────────────────────────────────────────────────
 *   `RenderCore` = AST → 块 DOM 的**新实现**（契约 `view-surface-contract.md` §2）。
 *   本片（P2a）只实现 5 类块：
 *     paragraph / heading / list(+ list_item) / blockquote / horizontal_rule
 *   以及任何文档都必带的 blank_line（空行是顶层块，5 类块的对比语料里必然出现）。
 *
 *   **其余块 kind 一律显式标记 `data-unsupported="<kind>"`**（`.-unsupported-block`），
 *   绝不静默渲染成空块 / 静默丢内容。这是 `renderer.js` `default:` 分支（内容静默消失）
 *   那条历史教训的直接反制。需要"遇到未实现直接失败"时传 `{ strictUnsupported: true }`。
 *
 * ── 与 legacy 的关系（P2a 的验收口径）─────────────────────────────────────
 *   本实现的 DOM 产出必须与 `renderer.js` 对同一 AST 的产出**逐属性等价**（签名 0 diff，
 *   见 `docs/design/render-fidelity-contract.md` §4）。因此：
 *     · 块元素的创建顺序 / class / 属性插入顺序 / 空块 `<br>` 占位 / 列表 `start`
 *       全部照渲染事实复刻（否则 `#preview.innerHTML` 指纹必然不同）；
 *     · inline 渲染（text/bold/italic/code/...）同样复刻，因为段落内容在签名内。
 *   **不改 `renderer.js`**：它是参考实现与回退路径（P6 前必须可切回）。
 *
 * ── 块身份（BlockIndex）────────────────────────────────────────────────────
 *   本模块**不写** `data--src-line` / `data--src-line-end` / `data-block-id`。
 *   块身份只经 `BlockIndex.upsert(handle)` 落属性（门禁 `check_line_attr_gate.js`
 *   要求这些属性只有一个写入点）。本模块只负责创建 `-src-block` 节点并返回，
 *   由 `new-surface.js` 调 `beginStamp({reset:true}) → upsert → commit`。
 *
 * 对外：`window.MemoriaRenderCore = { createRenderCore, SUPPORTED_BLOCK_KINDS, renderUnsupportedBlock }`
 */
window.MemoriaRenderCore = (function () {
  "use strict";

  var AST = window.MemoriaAST;
  var T = AST ? AST.TYPES : null;

  /**
   * P2a 已实现的顶层块 kind（与 `renderer.js` 的 AST kind 同名）。
   * list_item 不是顶层块，但它是 `list` 的组成部分，故一并声明。
   */
  var SUPPORTED_BLOCK_KINDS = [
    "paragraph",
    "heading",
    "blank_line",
    "list",
    "list_item",
    "blockquote",
    "horizontal_rule",
  ];

  // ── 图片尺寸规范化（复刻 renderer.js `_normalizeImageSize`）──────────────────
  function _normalizeImageSize(v) {
    var m = /^(\d+(?:\.\d+)?)(px|%)?$/.exec(String(v).trim());
    if (!m) return null;
    return m[2] ? m[0] : m[1] + "px";
  }

  // ── 颜色映射（复刻 renderer.js 从 markdown-preview.js 移植的两张表）──────────
  var _hlColorMap = {
    yellow: "#fff3cd",
    green: "#d4edda",
    red: "#f8d7da",
    blue: "#cce5ff",
    orange: "#ffe8cc",
  };
  var _fcColorMap = {
    red: "#dc3545",
    green: "#28a745",
    blue: "#007bff",
    orange: "#fd7e14",
    yellow: "#ffc107",
    purple: "#6f42c1",
    gray: "#6c757d",
  };
  function _fcColorHex(name) {
    if (!name) return "";
    var hex = _fcColorMap[name];
    if (hex) return hex;
    if (/^#[0-9a-fA-F]{6}$/.test(name)) return name;
    return name;
  }
  function _hlColorHex(name) {
    if (!name) return "";
    var hex = _hlColorMap[name];
    if (hex) return hex;
    if (/^#[0-9a-fA-F]{6}$/.test(name)) return name; // 支持 #RRGGBB 自定义
    return name; // 其他 CSS 颜色名直通
  }

  // ── inline 渲染（与 renderer.js `renderInline` 逐分支等价）────────────────────
  function renderInlineList(children, parentEl) {
    if (!children) return;
    for (var i = 0; i < children.length; i++) {
      var nodeEl = renderInline(children[i]);
      if (nodeEl) parentEl.appendChild(nodeEl);
    }
  }

  function renderInline(node) {
    if (!node) return document.createTextNode("");

    switch (node.type) {
      case T.TEXT:
        return document.createTextNode(node.content);

      case T.BOLD:
        var bEl = document.createElement("strong");
        renderInlineList(node.children, bEl);
        return bEl;

      case T.ITALIC:
        var iEl = document.createElement("em");
        renderInlineList(node.children, iEl);
        return iEl;

      case T.BOLD_ITALIC:
        var biEl = document.createElement("strong");
        var biEm = document.createElement("em");
        renderInlineList(node.children, biEm);
        biEl.appendChild(biEm);
        return biEl;

      case T.STRIKETHROUGH:
        var sEl = document.createElement("del");
        renderInlineList(node.children, sEl);
        return sEl;

      case T.CODE:
        var cEl = document.createElement("code");
        cEl.textContent = node.code;
        return cEl;

      case T.HIGHLIGHT:
        var hlEl = document.createElement("span");
        hlEl.className = "-hl";
        hlEl.style.backgroundColor = _hlColorHex(node.color || "yellow");
        if (node.color && _hlColorMap[node.color]) hlEl.className += " -hl-" + node.color;
        if (node.fgColor) hlEl.style.color = _fcColorHex(node.fgColor);
        renderInlineList(node.children, hlEl);
        return hlEl;

      case T.FONT_COLOR:
        var fcEl = document.createElement("span");
        fcEl.style.color = _fcColorHex(node.color);
        renderInlineList(node.children, fcEl);
        return fcEl;

      case T.FONT_SIZE:
        var fsEl = document.createElement("span");
        fsEl.style.fontSize = node.size;
        renderInlineList(node.children, fsEl);
        return fsEl;

      case T.FONT_BOLD:
        var fbEl = document.createElement("span");
        fbEl.style.fontWeight = "bold";
        renderInlineList(node.children, fbEl);
        return fbEl;

      case T.FONT_ITALIC:
        var fiEl = document.createElement("span");
        fiEl.style.fontStyle = "italic";
        renderInlineList(node.children, fiEl);
        return fiEl;

      case T.FONT_UNDERLINE:
        var fuEl = document.createElement("span");
        fuEl.style.textDecoration = "underline";
        renderInlineList(node.children, fuEl);
        return fuEl;

      case T.FONT_SUPERSCRIPT:
        var supEl = document.createElement("sup");
        renderInlineList(node.children, supEl);
        return supEl;

      case T.FONT_SUBSCRIPT:
        var subEl = document.createElement("sub");
        renderInlineList(node.children, subEl);
        return subEl;

      case T.WIKI_LINK:
        var wlEl = document.createElement("a");
        wlEl.className = "-wikilink";
        wlEl.setAttribute("data--target", node.target);
        wlEl.textContent = node.display || node.target;
        wlEl.contentEditable = "false";
        return wlEl;

      case T.LINK:
        var lEl = document.createElement("a");
        lEl.href = node.url;
        lEl.textContent = node.text;
        lEl.contentEditable = "false";
        return lEl;

      case T.IMAGE:
        // 行内图片兜底（与 renderer.js `renderInline` 的 IMAGE 分支同形）。
        // 注意：**块级 image 块**在 P2a 未实现 ⇒ 显式 unsupported（见 renderBlock）。
        var imgEl = document.createElement("img");
        imgEl.loading = "lazy";
        imgEl.src = node.url;
        imgEl.alt = node.alt;
        imgEl.className = "-preview-image";
        if (node.title) imgEl.title = node.title;
        if (node.attrs) {
          for (var _ik in node.attrs) {
            if (_ik === "width" || _ik === "height") {
              var _iv = _normalizeImageSize(node.attrs[_ik]);
              if (_iv !== null) {
                imgEl.style[_ik] = _iv;
                imgEl.style.maxWidth = "100%";
              }
            }
          }
        }
        return imgEl;

      case T.MATH_INLINE:
        // P2a 只产源码态 `-math` 节点；排版（MathJax 升级）是 P3 的范围。
        var mEl = document.createElement("span");
        mEl.className = "-math";
        mEl.contentEditable = "false";
        mEl.setAttribute("data-formula", node.formula);
        mEl.textContent = "$" + node.formula + "$";
        return mEl;

      case T.ESCAPE:
        return document.createTextNode(node.char);

      default:
        // 与 legacy 一致的兜底（空文本节点）——但**块级**未实现绝不走这里，见 renderBlock。
        return document.createTextNode("");
    }
  }

  // ── 块元素工厂（属性插入顺序与 renderer.js 一致：class → data--block-index）────
  function _newBlockEl(tag, kindClass, blockIndex) {
    var el = document.createElement(tag);
    el.className = kindClass ? "-src-block " + kindClass : "-src-block";
    el.setAttribute("data--block-index", blockIndex);
    return el;
  }

  // ── P2a 块渲染器 ────────────────────────────────────────────────────────────
  var BLOCK_RENDERERS = {
    blank_line: function (block, blockIndex) {
      var el = _newBlockEl("div", "-blank-block", blockIndex);
      el.innerHTML = "<br>";
      return el;
    },

    heading: function (block, blockIndex) {
      var el = _newBlockEl("h" + block.level, "", blockIndex);
      renderInlineList(block.children, el);
      // 空标题补 <br> 占位（同 renderer.js：否则零高度无法放置光标）
      if (!block.children || block.children.length === 0) el.innerHTML = "<br>";
      return el;
    },

    paragraph: function (block, blockIndex) {
      var el = _newBlockEl("p", "", blockIndex);
      renderInlineList(block.children, el);
      if (!block.children || block.children.length === 0) el.innerHTML = "<br>";
      return el;
    },

    horizontal_rule: function (block, blockIndex) {
      return _newBlockEl("hr", "", blockIndex);
    },

    blockquote: function (block, blockIndex) {
      var el = _newBlockEl("blockquote", "", blockIndex);
      if (block.children) {
        // 内层段落渲染为普通 <p>（**不带** -src-block / data--block-index），
        // 与 renderer.js 同理：否则 domToAst 会定位到内层段落、多段落索引相同。
        for (var qi = 0; qi < block.children.length; qi++) {
          var inner = block.children[qi];
          if (!inner) continue;
          var qEl = document.createElement("p");
          renderInlineList(inner.children, qEl);
          if (!inner.children || inner.children.length === 0) qEl.innerHTML = "<br>";
          el.appendChild(qEl);
        }
      }
      return el;
    },

    list: function (block, blockIndex) {
      var el = _newBlockEl(block.ordered ? "ol" : "ul", "", blockIndex);
      // 列表被块级元素隔断时会拆成多个 <ol>；首项源编号保留（同 renderer.js）
      if (block.ordered && block.start && block.start > 1) {
        el.setAttribute("start", String(block.start));
      }
      if (block.items) {
        for (var li = 0; li < block.items.length; li++) {
          var liEl = document.createElement("li");
          renderInlineList(block.items[li].children, liEl);
          if (!block.items[li].children || block.items[li].children.length === 0) liEl.innerHTML = "<br>";
          el.appendChild(liEl);
        }
      }
      return el;
    },
  };

  /**
   * 未实现 kind 的**显式**表示（不静默、不空块）。
   * 同时带 `data-unsupported`（机器可查）与可见占位文本（人可查）。
   */
  function renderUnsupportedBlock(block, blockIndex) {
    var kind = (block && block.type) ? String(block.type) : "unknown";
    var el = _newBlockEl("div", "-unsupported-block", blockIndex);
    el.setAttribute("data-unsupported", kind);
    el.textContent = "[" + kind + ": P2a RenderCore 尚未实现]";
    return el;
  }

  /**
   * 渲染单个块。
   * @param {object} block AST 块节点
   * @param {number} blockIndex 文档内下标（写 data--block-index，与 legacy 同口径）
   * @param {object} [opts] opts.strictUnsupported=true ⇒ 未实现 kind 直接抛 UNSUPPORTED_BLOCK
   */
  function renderBlock(block, blockIndex, opts) {
    var fn = block && block.type ? BLOCK_RENDERERS[block.type] : null;
    if (fn) return fn(block, blockIndex);
    if (opts && opts.strictUnsupported) {
      var err = new Error("[MemoriaRenderCore] 未实现的块 kind: " + (block && block.type));
      err.code = "UNSUPPORTED_BLOCK";
      err.kind = block && block.type;
      throw err;
    }
    return renderUnsupportedBlock(block, blockIndex);
  }

  /**
   * 渲染整篇文档 → `.-preview-content` 容器 + 与 `doc.blocks` 等长的块元素数组。
   * 不接触 DOM 树（调用方负责挂载）——便于双跑对比时离屏渲染。
   * @returns {{container:HTMLElement, blockEls:HTMLElement[], unsupported:string[], count:number, doc:object}}
   */
  function renderDocument(doc, opts) {
    var container = document.createElement("div");
    container.className = "-preview-content";
    var blockEls = [];
    var unsupported = [];
    if (!doc || !doc.blocks) {
      return { container: container, blockEls: blockEls, unsupported: unsupported, count: 0, doc: doc || null };
    }
    for (var i = 0; i < doc.blocks.length; i++) {
      var block = doc.blocks[i];
      if (!block || !BLOCK_RENDERERS[block.type]) unsupported.push(block && block.type ? String(block.type) : "unknown");
      var el = renderBlock(block, i, opts);
      blockEls.push(el);
      container.appendChild(el);
    }
    return { container: container, blockEls: blockEls, unsupported: unsupported, count: doc.blocks.length, doc: doc };
  }

  /**
   * 契约 §2.1 的 `renderAll(text, container)`：解析 + 渲染 + 挂载。
   * @returns {{container, blockEls, unsupported, count, doc, text}}
   */
  function renderAll(text, container, opts) {
    var P = window.MemoriaParser;
    if (!P || typeof P.parse !== "function") {
      var err = new Error("[MemoriaRenderCore] MemoriaParser 未加载，无法解析 text");
      err.code = "PARSER_NOT_READY";
      throw err;
    }
    var src = (text == null) ? "" : String(text);
    var doc = P.parse(src);
    var out = renderDocument(doc, opts);
    if (container) {
      container.innerHTML = "";
      container.appendChild(out.container);
    }
    out.text = src;
    return out;
  }

  /**
   * @param {object} [opts] opts.strictUnsupported=true ⇒ 未实现 kind 抛错（默认显式标记）
   */
  function createRenderCore(opts) {
    opts = opts || {};
    return {
      name: "MemoriaRenderCore",
      phase: "P2a",
      supportedBlockKinds: SUPPORTED_BLOCK_KINDS.slice(),
      isSupportedKind: function (kind) { return !!BLOCK_RENDERERS[kind]; },
      renderBlock: function (block, blockIndex) { return renderBlock(block, blockIndex, opts); },
      renderDocument: function (doc) { return renderDocument(doc, opts); },
      renderAll: function (text, container) { return renderAll(text, container, opts); },
      renderInline: renderInline,
      renderInlineList: renderInlineList,
    };
  }

  return {
    createRenderCore: createRenderCore,
    renderUnsupportedBlock: renderUnsupportedBlock,
    SUPPORTED_BLOCK_KINDS: SUPPORTED_BLOCK_KINDS,
  };
})();
