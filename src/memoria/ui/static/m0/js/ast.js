/**
 * MemoriaAST — AST 节点类型定义、工厂函数、遍历工具
 * Phase 1: 类型契约，无依赖，所有后续 Phase 的接口基础
 */

window.MemoriaAST = (function () {
  "use strict";

  // ── 节点类型常量 ──
  const TYPES = {
    // Block
    DOCUMENT: "document",
    FRONTMATTER: "frontmatter",
    BLANK_LINE: "blank_line",
    HEADING: "heading",
    PARAGRAPH: "paragraph",
    CODE_BLOCK: "code_block",
    MATH_BLOCK: "math_block",
    IMAGE: "image",
    TABLE: "table",
    BLOCKQUOTE: "blockquote",
    HORIZONTAL_RULE: "horizontal_rule",
    LIST: "list",
    LIST_ITEM: "list_item",
    MERMAID: "mermaid",

    // Inline
    TEXT: "text",
    BOLD: "bold",
    ITALIC: "italic",
    BOLD_ITALIC: "bold_italic",
    STRIKETHROUGH: "strikethrough",
    CODE: "code",
    HIGHLIGHT: "highlight",
    FONT_COLOR: "font_color",
    FONT_SIZE: "font_size",
    FONT_BOLD: "font_bold",
    FONT_ITALIC: "font_italic",
    FONT_UNDERLINE: "font_underline",
    FONT_SUPERSCRIPT: "font_superscript",
    FONT_SUBSCRIPT: "font_subscript",
    WIKI_LINK: "wiki_link",
    LINK: "link",
    MATH_INLINE: "math_inline",
    ESCAPE: "escape",
  };

  // ── 工厂函数 ──

  /** @return {{type:"text", content:string}} */
  function text(content) {
    return { type: TYPES.TEXT, content: content };
  }

  /** @return {{type:"bold", children:Inline[]}} */
  function bold(children) {
    return { type: TYPES.BOLD, children: children };
  }

  /** @return {{type:"italic", children:Inline[]}} */
  function italic(children) {
    return { type: TYPES.ITALIC, children: children };
  }

  /** @return {{type:"bold_italic", children:Inline[]}} */
  function boldItalic(children) {
    return { type: TYPES.BOLD_ITALIC, children: children };
  }

  /** @return {{type:"strikethrough", children:Inline[]}} */
  function strikethrough(children) {
    return { type: TYPES.STRIKETHROUGH, children: children };
  }

  /** @return {{type:"code", code:string}} */
  function code(code) {
    return { type: TYPES.CODE, code: code };
  }

  /** @param {string|null} color — null 表示默认荧光笔 [[\h|...]]
   *  @return {{type:"highlight", color:string|null, children:Inline[]}} */
  function highlight(color, fgColor, children) {
    return { type: TYPES.HIGHLIGHT, color: color || null, fgColor: fgColor || null, children: children || [] };
  }

  /** @return {{type:"font_color", color:string, children:Inline[]}} */
  function fontColor(color, children) {
    return { type: TYPES.FONT_COLOR, color: color, children: children };
  }

  /** @return {{type:"font_size", size:string, children:Inline[]}} */
  function fontSize(size, children) {
    return { type: TYPES.FONT_SIZE, size: size, children: children };
  }

  /** @return {{type:"font_bold", children:Inline[]}} */
  function fontBold(children) {
    return { type: TYPES.FONT_BOLD, children: children };
  }

  /** @return {{type:"font_italic", children:Inline[]}} */
  function fontItalic(children) {
    return { type: TYPES.FONT_ITALIC, children: children };
  }

  /** @return {{type:"font_underline", children:Inline[]}} */
  function fontUnderline(children) {
    return { type: TYPES.FONT_UNDERLINE, children: children };
  }

  /** @return {{type:"font_superscript", children:Inline[]}} */
  function fontSuperscript(children) {
    return { type: TYPES.FONT_SUPERSCRIPT, children: children };
  }

  /** @return {{type:"font_subscript", children:Inline[]}} */
  function fontSubscript(children) {
    return { type: TYPES.FONT_SUBSCRIPT, children: children };
  }

  /** @param {string} target — 链接目标 kp_id
   *  @param {string} display — 显示文本
   *  @return {{type:"wiki_link", target:string, display:string}} */
  function wikiLink(target, display) {
    return { type: TYPES.WIKI_LINK, target: target, display: display || "" };
  }

  /** @return {{type:"link", text:string, url:string}} */
  function link(text, url) {
    return { type: TYPES.LINK, text: text, url: url };
  }

  /** @return {{type:"math_inline", formula:string}} */
  function mathInline(formula) {
    return { type: TYPES.MATH_INLINE, formula: formula };
  }

  /** @return {{type:"escape", char:string}} */
  function escape(char) {
    return { type: TYPES.ESCAPE, char: char };
  }

  // ── Block 工厂函数 ──

  /** @return {{type:"frontmatter", yaml:string}} */
  function frontmatter(yaml) {
    return { type: TYPES.FRONTMATTER, yaml: yaml };
  }

  /** @return {{type:"blank_line"}} */
  function blankLine() {
    return { type: TYPES.BLANK_LINE };
  }

  /** @param {1|2|3|4|5|6} level
   *  @return {{type:"heading", level:number, children:Inline[]}} */
  function heading(level, children) {
    return { type: TYPES.HEADING, level: level, children: children || [] };
  }

  /** @return {{type:"paragraph", children:Inline[]}} */
  function paragraph(children) {
    return { type: TYPES.PARAGRAPH, children: children || [] };
  }

  /** @return {{type:"code_block", lang:string, code:string}} */
  function codeBlock(lang, code) {
    return { type: TYPES.CODE_BLOCK, lang: lang || "", code: code || "" };
  }

  /** @return {{type:"math_block", formula:string}} */
  function mathBlock(formula) {
    return { type: TYPES.MATH_BLOCK, formula: formula };
  }

  /** @return {{type:"image", alt:string, url:string}} */
  function image(alt, url) {
    return { type: TYPES.IMAGE, alt: alt || "", url: url || "" };
  }

  /** @return {{type:"table", header:Row, rows:Row[]}} */
  function table(header, rows) {
    return { type: TYPES.TABLE, header: header, rows: rows || [] };
  }

  /** @return {{type:"blockquote", children:Block[]}} */
  function blockquote(children) {
    return { type: TYPES.BLOCKQUOTE, children: children || [] };
  }

  /** @return {{type:"horizontal_rule"}} */
  function horizontalRule() {
    return { type: TYPES.HORIZONTAL_RULE };
  }

  /** @param {boolean} ordered
   *  @return {{type:"list", ordered:boolean, items:ListItem[]}} */
  function list(ordered, items) {
    return { type: TYPES.LIST, ordered: !!ordered, items: items || [] };
  }

  /** @return {{type:"list_item", children:Inline[]}} */
  function listItem(children) {
    return { type: TYPES.LIST_ITEM, children: children || [] };
  }

  /** @return {{type:"mermaid", code:string}} */
  function mermaid(code) {
    return { type: TYPES.MERMAID, code: code || "" };
  }

  /** @return {{type:"document", blocks:Block[]}} */
  function document(blocks) {
    return { type: TYPES.DOCUMENT, blocks: blocks || [] };
  }

  // ── 遍历工具 ──

  /**
   * 深度优先遍历 AST 节点
   * @param {object} node
   * @param {function} visitor - (node, path, parent) => false 停止遍历
   * @param {number[]} [path=[]]
   * @param {object} [parent=null]
   */
  function walk(node, visitor, path, parent) {
    path = path || [];
    if (!node) return;
    if (visitor(node, path, parent) === false) return;

    var children = null;
    if (node.blocks) {
      children = node.blocks;
    } else if (node.children) {
      children = node.children;
    } else if (node.items) {
      children = node.items;
    }

    if (children && Array.isArray(children)) {
      for (var i = 0; i < children.length; i++) {
        walk(children[i], visitor, path.concat(i), node);
      }
    }
  }

  /**
   * 按路径获取节点
   * @param {object} root
   * @param {number[]} path
   * @returns {object|null}
   */
  function getNodeAt(root, path) {
    var node = root;
    for (var i = 0; i < path.length; i++) {
      var idx = path[i];
      if (node.blocks) {
        node = node.blocks[idx];
      } else if (node.children) {
        node = node.children[idx];
      } else if (node.items) {
        node = node.items[idx];
      } else {
        return null;
      }
      if (!node) return null;
    }
    return node;
  }

  /**
   * 提取节点的纯文本内容（递归）
   * @param {object} node
   * @returns {string}
   */
  function getText(node) {
    if (!node) return "";
    if (node.type === TYPES.TEXT) return node.content;
    if (node.type === TYPES.CODE) return node.code;
    if (node.type === TYPES.ESCAPE) return node.char;
    if (node.type === TYPES.MATH_INLINE) return node.formula;
    if (node.type === TYPES.IMAGE) return node.alt;
    if (node.type === TYPES.WIKI_LINK) return node.display || node.target;
    if (node.type === TYPES.LINK) return node.text;
    if (node.type === TYPES.CODE_BLOCK) return node.code;
    if (node.type === TYPES.MATH_BLOCK) return node.formula;
    if (node.type === TYPES.MERMAID) return node.code;
    if (node.type === TYPES.BLANK_LINE) return "";
    if (node.type === TYPES.HORIZONTAL_RULE) return "";

    var parts = [];
    var children = node.children || node.blocks || node.items || [];
    for (var i = 0; i < children.length; i++) {
      parts.push(getText(children[i]));
    }
    return parts.join("");
  }

  /**
   * 判断节点是否为 block 类型
   * @param {object} node
   * @returns {boolean}
   */
  function isBlock(node) {
    if (!node) return false;
    return [
      TYPES.HEADING, TYPES.PARAGRAPH, TYPES.BLANK_LINE, TYPES.CODE_BLOCK,
      TYPES.MATH_BLOCK, TYPES.IMAGE, TYPES.TABLE, TYPES.BLOCKQUOTE,
      TYPES.HORIZONTAL_RULE, TYPES.LIST, TYPES.LIST_ITEM, TYPES.MERMAID,
      TYPES.FRONTMATTER,
    ].indexOf(node.type) !== -1;
  }

  /**
   * 判断节点是否为 inline 类型
   * @param {object} node
   * @returns {boolean}
   */
  function isInline(node) {
    if (!node) return false;
    return [
      TYPES.TEXT, TYPES.BOLD, TYPES.ITALIC, TYPES.BOLD_ITALIC,
      TYPES.STRIKETHROUGH, TYPES.CODE, TYPES.HIGHLIGHT, TYPES.FONT_COLOR,
      TYPES.FONT_SIZE, TYPES.FONT_BOLD, TYPES.FONT_ITALIC, TYPES.FONT_UNDERLINE,
      TYPES.FONT_SUPERSCRIPT, TYPES.FONT_SUBSCRIPT,
      TYPES.WIKI_LINK, TYPES.LINK, TYPES.MATH_INLINE, TYPES.ESCAPE,
    ].indexOf(node.type) !== -1;
  }

  /**
   * 在文本节点中插入/删除字符（纯文本编辑，不改变结构）
   * @param {object} textNode — Text 节点
   * @param {number} offset — 编辑位置
   * @param {string} inserted — 插入的字符（空字符串 = 删除 1 个字符）
   * @returns {object} 修改后的 Text 节点
   */
  function editText(textNode, offset, inserted) {
    if (textNode.type !== TYPES.TEXT) return textNode;
    var c = textNode.content;
    if (inserted) {
      textNode.content = c.slice(0, offset) + inserted + c.slice(offset);
    } else {
      // 删除 offset 处字符
      textNode.content = c.slice(0, offset) + c.slice(offset + 1);
    }
    return textNode;
  }

  /**
   * 在 Text 节点中 Backspace（删除 offset-1 处字符）
   * @param {object} textNode
   * @param {number} offset
   * @returns {object}
   */
  function backspaceText(textNode, offset) {
    if (textNode.type !== TYPES.TEXT) return textNode;
    var c = textNode.content;
    if (offset > 0) {
      textNode.content = c.slice(0, offset - 1) + c.slice(offset);
    }
    return textNode;
  }

  /**
   * 拆分 Text 节点在 offset 处
   * @returns {[object, object]} [left, right]
   */
  function splitText(textNode, offset) {
    if (textNode.type !== TYPES.TEXT) return [textNode, text("")];
    return [
      text(textNode.content.slice(0, offset)),
      text(textNode.content.slice(offset)),
    ];
  }

  // ── 公开 API ──
  return {
    TYPES: TYPES,

    // Inline 工厂
    text: text,
    bold: bold,
    italic: italic,
    boldItalic: boldItalic,
    strikethrough: strikethrough,
    code: code,
    highlight: highlight,
    fontColor: fontColor,
    fontSize: fontSize,
    fontBold: fontBold,
    fontItalic: fontItalic,
    fontUnderline: fontUnderline,
    fontSuperscript: fontSuperscript,
    fontSubscript: fontSubscript,
    wikiLink: wikiLink,
    link: link,
    mathInline: mathInline,
    escape: escape,

    // Block 工厂
    frontmatter: frontmatter,
    blankLine: blankLine,
    heading: heading,
    paragraph: paragraph,
    codeBlock: codeBlock,
    mathBlock: mathBlock,
    image: image,
    table: table,
    blockquote: blockquote,
    horizontalRule: horizontalRule,
    list: list,
    listItem: listItem,
    mermaid: mermaid,
    document: document,

    // 遍历
    walk: walk,
    getNodeAt: getNodeAt,
    getText: getText,
    isBlock: isBlock,
    isInline: isInline,

    // 编辑
    editText: editText,
    backspaceText: backspaceText,
    splitText: splitText,
  };
})();