/**
 * MemoriaRenderer — AST → DOM 渲染器
 * Phase 6: 将 AST 渲染为 contenteditable DOM
 * 依赖: MemoriaAST
 */

window.MemoriaRenderer = (function () {
  "use strict";

  var AST = MemoriaAST;
  var T = AST.TYPES;

  /**
   * 规范化图片尺寸值：纯数字 → px；`300px`/`50%` 原样；非法返回 null
   * @param {string} v
   * @returns {string|null}
   */
  function _normalizeImageSize(v) {
    var m = /^(\d+(?:\.\d+)?)(px|%)?$/.exec(String(v).trim());
    if (!m) return null;
    return m[2] ? m[0] : m[1] + "px";
  }

  /**
   * 渲染表格单元格的文本为行内 AST（支持 **加粗** / *斜体* / 荧光笔 /
   * 行内公式 $...$ / [[wiki]] 等）。失败时退化为纯文本。
   */
  function _renderTableCellText(el, text) {
    if (
      window.MemoriaLexer &&
      window.MemoriaParser &&
      typeof text === "string"
    ) {
      try {
        var _tokens = window.MemoriaLexer.tokenize(text);
        var _children = window.MemoriaParser.parseInline(_tokens);
        renderInlineList(_children, el);
        return;
      } catch (_e) {
        /* 解析失败退化纯文本 */
      }
    }
    el.textContent = text == null ? "" : String(text);
  }

  /**
   * @param {object} doc — Document AST
   * @returns {HTMLElement}
   */
  function render(doc) {
    var container = document.createElement("div");
    container.className = "-preview-content";

    if (!doc || !doc.blocks) return container;

    for (var i = 0; i < doc.blocks.length; i++) {
      var blockEl = renderBlock(doc.blocks[i], i);
      container.appendChild(blockEl);
    }

    return container;
  }

  /**
   * 渲染单个 block
   * @param {object} block
   * @param {number} blockIndex
   * @returns {HTMLElement}
   */
  function renderBlock(block, blockIndex) {
    var el;

    switch (block.type) {
      case T.BLANK_LINE:
        el = document.createElement("div");
        el.className = "-src-block -blank-block";
        el.setAttribute("data--block-index", blockIndex);
        el.innerHTML = "<br>";
        return el;

      case T.HEADING:
        el = document.createElement("h" + block.level);
        el.className = "-src-block";
        el.setAttribute("data--block-index", blockIndex);
        renderInlineList(block.children, el);
        // 空标题补 <br> 占位，否则零高度无法放置光标，输入会漂移到下一块
        if (!block.children || block.children.length === 0) el.innerHTML = "<br>";
        return el;

      case T.PARAGRAPH:
        el = document.createElement("p");
        el.className = "-src-block";
        el.setAttribute("data--block-index", blockIndex);
        renderInlineList(block.children, el);
        // 空段落同样补 <br> 占位
        if (!block.children || block.children.length === 0) el.innerHTML = "<br>";
        return el;

      case T.CODE_BLOCK:
        el = document.createElement("pre");
        el.className = "-src-block -code-block";
        el.setAttribute("data--block-index", blockIndex);
        var codeEl = document.createElement("code");
        if (block.lang) codeEl.className = "language-" + block.lang;
        codeEl.textContent = block.code;
        el.appendChild(codeEl);
        return el;

      case T.MATH_BLOCK:
        el = document.createElement("div");
        el.className = "-src-block -math-block";
        el.setAttribute("data--block-index", blockIndex);
        el.textContent = "$$" + block.formula + "$$";
        return el;

      case T.IMAGE:
        el = document.createElement("p");
        el.className = "-src-block -image-block";
        el.setAttribute("data--block-index", blockIndex);
        var img = document.createElement("img");
        img.src = block.url;
        img.alt = block.alt;
        img.className = "-preview-image";
        if (block.title) img.title = block.title;
        // 阶段 E 属性渲染：width/height → 内联样式；align → 容器对齐 class
        // 阶段 G 属性：name-size（名称字号）/ name=hide（隐藏名称）
        if (block.attrs) {
          for (var _ak in block.attrs) {
            if (_ak === "width" || _ak === "height") {
              var v = _normalizeImageSize(block.attrs[_ak]);
              if (v !== null) {
                img.style[_ak] = v;
                img.style.maxWidth = "100%"; // 显式尺寸生效，仅防溢出容器（覆盖默认 max-width:35% 钳制）
              }
            } else if (_ak === "align") {
              var a = block.attrs.align;
              if (a === "center" || a === "left" || a === "right") {
                el.classList.add("-image-align-" + a);
              }
            } else if (_ak !== "name-size" && _ak !== "name") {
              console.warn("[img-attrs] 未知图片属性 key=" + _ak + "（已忽略），支持 width/height/align/name-size/name");
            }
          }
        }
        el.appendChild(img);
        // 图片名称（alt）显示在图片下方（阶段 G）
        var cap = document.createElement("span");
        cap.className = "-image-caption";
        cap.setAttribute("data--image-caption", "1");
        cap.textContent = block.alt || "";
        if (block.attrs) {
          var ns = block.attrs["name-size"];
          if (ns) {
            var nsv = _normalizeImageSize(ns);
            if (nsv !== null) cap.style.fontSize = nsv;
          }
          if (block.attrs.name === "hide") cap.style.display = "none";
        }
        el.appendChild(cap);
        return el;

      case T.HORIZONTAL_RULE:
        el = document.createElement("hr");
        el.className = "-src-block";
        el.setAttribute("data--block-index", blockIndex);
        return el;

      case T.BLOCKQUOTE:
        el = document.createElement("blockquote");
        el.className = "-src-block";
        el.setAttribute("data--block-index", blockIndex);
        if (block.children) {
          // 内层段落渲染为普通 <p>（不带 -src-block / block-index），
          // 否则 domToAst 会定位到内层段落且多段落索引相同，导致映射错乱
          for (var qi = 0; qi < block.children.length; qi++) {
            var inner = block.children[qi];
            if (!inner) continue;
            var qEl = document.createElement("p");
            renderInlineList(inner.children, qEl);
            // 空引用段落补 <br> 占位
            if (!inner.children || inner.children.length === 0) qEl.innerHTML = "<br>";
            el.appendChild(qEl);
          }
        }
        return el;

      case T.LIST:
        el = document.createElement(block.ordered ? "ol" : "ul");
        el.className = "-src-block";
        el.setAttribute("data--block-index", blockIndex);
        // 列表被块级元素（公式/代码块等）隔断时会拆成多个 <ol>，
        // 用首项源编号保持编号连续，避免全部从 1 重新开始
        if (block.ordered && block.start && block.start > 1) {
          el.setAttribute("start", String(block.start));
        }
        if (block.items) {
          for (var li = 0; li < block.items.length; li++) {
            var liEl = document.createElement("li");
            renderInlineList(block.items[li].children, liEl);
            // 空列表项补 <br> 占位，保证可放置光标
            if (!block.items[li].children || block.items[li].children.length === 0) liEl.innerHTML = "<br>";
            el.appendChild(liEl);
          }
        }
        return el;

      case T.TABLE:
        el = document.createElement("table");
        el.className = "-src-block -table";
        el.setAttribute("data--block-index", blockIndex);
        if (block.header) {
          var thead = document.createElement("thead");
          var tr = document.createElement("tr");
          for (var hi = 0; hi < block.header.length; hi++) {
            var th = document.createElement("th");
            _renderTableCellText(th, block.header[hi]);
            tr.appendChild(th);
          }
          thead.appendChild(tr);
          el.appendChild(thead);
        }
        if (block.rows) {
          var tbody = document.createElement("tbody");
          for (var ri = 0; ri < block.rows.length; ri++) {
            var row = document.createElement("tr");
            for (var ci = 0; ci < block.rows[ri].length; ci++) {
              var td = document.createElement("td");
              _renderTableCellText(td, block.rows[ri][ci]);
              row.appendChild(td);
            }
            tbody.appendChild(row);
          }
          el.appendChild(tbody);
        }
        return el;

      case T.FRONTMATTER:
        el = document.createElement("pre");
        el.className = "-src-block -frontmatter";
        el.setAttribute("data--block-index", blockIndex);
        el.textContent = block.yaml;
        return el;

      case T.MERMAID:
        el = document.createElement("pre");
        el.className = "-src-block -mermaid";
        el.setAttribute("data--block-index", blockIndex);
        var mc = document.createElement("code");
        mc.className = "language-mermaid";
        mc.textContent = block.code;
        el.appendChild(mc);
        return el;

      default:
        el = document.createElement("div");
        el.className = "-src-block";
        el.setAttribute("data--block-index", blockIndex);
        return el;
    }
  }

  /**
   * 渲染 inline 节点数组到父元素
   * @param {Array} children
   * @param {HTMLElement} parentEl
   */
  function renderInlineList(children, parentEl) {
    if (!children) return;
    for (var i = 0; i < children.length; i++) {
      var nodeEl = renderInline(children[i]);
      if (nodeEl) parentEl.appendChild(nodeEl);
    }
  }

  // ── 颜色映射（从 markdown-preview.js 移植）──
  var _hlColorMap = {
    yellow: "#fff3cd", green: "#d4edda", red: "#f8d7da", blue: "#cce5ff", orange: "#ffe8cc"
  };
  var _fcColorMap = {
    red: "#dc3545", green: "#28a745", blue: "#007bff", orange: "#fd7e14",
    yellow: "#ffc107", purple: "#6f42c1", gray: "#6c757d"
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
    if (/^#[0-9a-fA-F]{6}$/.test(name)) return name;  // 支持 #RRGGBB 自定义
    return name;  // 其他 CSS 颜色名直通
  }

  /**
   * 渲染单个 inline 节点
   * @param {object} node
   * @returns {Node} — TextNode 或 HTMLElement
   */
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
        // 行内图片兜底渲染（段落内图片 / 行尾带空白未判为图片块的场景）；
        // 独立图片块走 renderBlock 的 T.IMAGE 分支（带 align/名称等完整处理）。
        var imgEl = document.createElement("img");
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
        var mEl = document.createElement("span");
        mEl.className = "-math";
        mEl.contentEditable = "false";
        mEl.setAttribute("data-formula", node.formula);
        mEl.textContent = "$" + node.formula + "$";
        return mEl;

      case T.ESCAPE:
        return document.createTextNode(node.char);

      default:
        return document.createTextNode("");
    }
  }

  /**
   * 增量渲染：替换指定范围的 block
   * @param {object} doc — Document AST
   * @param {number} startBlock
   * @param {number} endBlock — exclusive
   * @param {HTMLElement} container — 预览容器
   */
  function renderRange(doc, startBlock, endBlock, container) {
    if (!doc || !doc.blocks || !container) return;

    // 获取旧 block 元素（container 应为 block 的直接父级，如 .-preview-content）
    var oldBlocks = container.querySelectorAll(".-src-block");
    var targetIndices = [];
    for (var i = 0; i < oldBlocks.length; i++) {
      var idx = parseInt(oldBlocks[i].getAttribute("data--block-index"), 10);
      if (idx >= startBlock && idx < endBlock) {
        targetIndices.push(i);
      }
    }

    if (targetIndices.length === 0) return;

    var firstEl = oldBlocks[targetIndices[0]];
    var parent = firstEl.parentNode;

    // 插入锚点：移除范围后的下一个兄弟（必须在移除前确定）
    var lastIdx = targetIndices[targetIndices.length - 1];
    var anchor = (lastIdx + 1 < oldBlocks.length) ? oldBlocks[lastIdx + 1] : null;

    // 移除旧元素
    for (var j = targetIndices.length - 1; j >= 0; j--) {
      var el = oldBlocks[targetIndices[j]];
      if (el.parentNode) el.parentNode.removeChild(el);
    }

    // 创建新元素
    var fragment = document.createDocumentFragment();
    for (var k = startBlock; k < endBlock && k < doc.blocks.length; k++) {
      fragment.appendChild(renderBlock(doc.blocks[k], k));
    }

    // 插入新元素（保持原位）
    if (parent) {
      if (anchor && anchor.parentNode === parent) {
        parent.insertBefore(fragment, anchor);
      } else {
        parent.appendChild(fragment);
      }
    } else {
      container.appendChild(fragment);
    }
  }

  // ── 公开 API ──
  return {
    render: render,
    renderBlock: renderBlock,
    renderInline: renderInline,
    renderInlineList: renderInlineList,
    renderRange: renderRange,
  };
})();