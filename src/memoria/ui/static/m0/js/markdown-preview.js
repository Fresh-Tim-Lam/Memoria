/**
 * Markdown 预览：marked (GFM) + MathJax 3 full (TeX 最高兼容)
 * 行内 / 块级公式分离占位，避免行内公式被 marked 拆成独立段落。
 */
window.MemoriaMarkdownPreview = (function () {
  "use strict";

  const BLOCK_PH = "MEMORIA_MATH_BLOCK_";
  const INLINE_START = "\uE000";
  const INLINE_END = "\uE001";

  let mathJaxReady = null;

  function initMathJax() {
    if (window.MathJax?.typesetPromise) {
      return window.MathJax.startup?.promise || Promise.resolve();
    }
    if (mathJaxReady) return mathJaxReady;
    mathJaxReady = new Promise((resolve, reject) => {
      let tries = 0;
      const tick = () => {
        if (window.MathJax?.startup?.promise) {
          window.MathJax.startup.promise.then(resolve).catch(reject);
          return;
        }
        if (window.MathJax?.typesetPromise) {
          resolve();
          return;
        }
        if (++tries > 400) {
          reject(new Error("MathJax 加载超时"));
          return;
        }
        setTimeout(tick, 50);
      };
      tick();
    });
    return mathJaxReady;
  }

  function normalizeBody(body) {
    if (window.MemoriaMathNormalize) {
      return MemoriaMathNormalize.normalize(body);
    }
    return body;
  }

  function protectDisplayBlocks(text, allBlocks) {
    const lines = text.split("\n");
    const out = [];
    let i = 0;
    while (i < lines.length) {
      if (lines[i].trim() === "$$") {
        const start = i;
        i += 1;
        while (i < lines.length && lines[i].trim() !== "$$") i += 1;
        if (i < lines.length) {
          const chunk = lines.slice(start, i + 1).join("\n");
          allBlocks.push({
            kind: "block",
            tex: chunk,
            srcStart: start + 1,
            srcEnd: i + 1,
          });
          out.push(`\n\n${BLOCK_PH}${allBlocks.length - 1}\n\n`);
          i += 1;
          continue;
        }
        out.push(lines[start]);
        i = start + 1;
        continue;
      }
      out.push(lines[i]);
      i += 1;
    }
    return out.join("\n");
  }

  function stashBlock(allBlocks, tex) {
    allBlocks.push({ kind: "block", tex, srcStart: null, srcEnd: null });
    return `\n\n${BLOCK_PH}${allBlocks.length - 1}\n\n`;
  }

  function wrapBlockMath(b) {
    if (!b) return "";
    let tex = b.tex.trim();
    // Strip outer $$ delimiters
    if (tex.startsWith("$$")) tex = tex.slice(2);
    if (tex.endsWith("$$")) tex = tex.slice(0, -2);
    // Strip outer \[ \] delimiters
    if (tex.startsWith("\\[")) tex = tex.slice(2);
    if (tex.endsWith("\\]")) tex = tex.slice(0, -2);
    tex = tex.trim();
    // HTML-escape so &, <, > survive innerHTML parsing;
    // MathJax reads textContent, which decodes entities back.
    const escaped = tex
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return "\\[" + escaped + "\\]";
  }

  function stashInline(allBlocks, tex) {
    allBlocks.push({ kind: "inline", tex });
    const idx = allBlocks.length - 1;
    return `${INLINE_START}MI${idx}${INLINE_END}`;
  }

  function protectMath(text) {
    const allBlocks = [];
    let out = protectDisplayBlocks(text, allBlocks);

    // Single-line display math: $$...$$ on one line (not $$ on its own line,
    // which is already handled by protectDisplayBlocks). Must come BEFORE
    // \begin{...}...\end{...} so that \begin{cases} etc. inside $$...$$
    // are captured as part of the $$ block rather than stashed separately
    // (which would insert newlines that break the single-line $$ regex).
    // Also must come before inline $...$ to prevent inner $ from being
    // matched as inline math and wrongly converted to \(...\).
    out = out.replace(/\$\$((?:\\.|[^\$\n\\])+?)\$\$/g, (m) =>
      stashBlock(allBlocks, m)
    );
    // Standalone \begin{...}...\end{...} environments NOT inside $$...$$
    out = out.replace(/\\begin\{([a-zA-Z*]+)\*?\}[\s\S]+?\\end\{\1\*?\}/g, (m) =>
      stashBlock(allBlocks, m)
    );
    out = out.replace(/\\\[([\s\S]+?)\\\]/g, (m) => stashBlock(allBlocks, m));
    out = out.replace(/\\\(([\s\S]+?)\\\)/g, (m) => stashInline(allBlocks, m));
    // Inline math: $...$ where the $ is not part of $$ (block).
    // Match only within a single line to prevent swallowing ** or other
    // markdown delimiters across lines when stray $ signs exist in the text.
    // Multi-line math should use $$...$$ block delimiters instead.
    out = out.replace(/\$(?!\$)((?:\\.|[^\$\n\\])+?)\$/g, (m) =>
      stashInline(allBlocks, m)
    );

    return { text: out, blocks: allBlocks };
  }

  function toInlineDelimiters(tex) {
    const t = tex.trim();
    if (t.startsWith("\\(") && t.endsWith("\\)")) return t;
    // Only convert single-$ delimiters; $$...$$ is block math and should
    // never be converted to inline \(...\).
    if (t.startsWith("$") && t.endsWith("$") && !t.startsWith("$$") && !t.endsWith("$$")) {
      return "\\(" + t.slice(1, -1) + "\\)";
    }
    return t;
  }

  function fixLoneInlineMathParagraphs(html) {
    return html.replace(
      /<p(\s[^>]*)?>(\s*)\$(?!\$)((?:\\.|[^$\n\\])+?)\$(\s*)<\/p>/g,
      (_, attrs, pre, inner, post) =>
        `<p${attrs || ""}>${pre}\\(${inner}\\)${post}</p>`
    );
  }

  function restoreMath(html, blocks) {
    html = html.replace(
      new RegExp(`<p>\\s*${BLOCK_PH}(\\d+)\\s*</p>`, "g"),
      (_, n) => wrapBlockMath(blocks[+n])
    );
    html = html.replace(new RegExp(`${BLOCK_PH}(\\d+)`, "g"), (_, n) =>
      wrapBlockMath(blocks[+n])
    );
    html = html.replace(
      new RegExp(`${INLINE_START}MI(\\d+)${INLINE_END}`, "g"),
      (_, n) => {
        const b = blocks[+n];
        if (!b) return "";
        return b.kind === "inline" ? toInlineDelimiters(b.tex) : b.tex;
      }
    );
    return fixLoneInlineMathParagraphs(html);
  }

  // ── Mermaid rendering ──
  let mermaidInited = false;
  function initMermaid() {
    if (mermaidInited) return;
    if (!window.mermaid) return;
    window.mermaid.initialize({
      startOnLoad: false,
      theme: "default",
      securityLevel: "loose",
      fontFamily: "inherit",
    });
    mermaidInited = true;
  }

  async function renderMermaidBlocks(container) {
    initMermaid();
    if (!window.mermaid?.render) return;
    const els = container.querySelectorAll("code.language-mermaid");
    for (const el of els) {
      const pre = el.parentElement;
      if (!pre) continue;
      const src = el.textContent || "";
      const id = "mermaid-" + Math.random().toString(36).slice(2, 10);
      try {
        const { svg } = await window.mermaid.render(id, src);
        const div = document.createElement("div");
        div.className = "m0-mermaid-container";
        // 保留 m0-src-block 和 data-m0-block-index 以便双击编辑
        if (pre.classList.contains("m0-src-block")) {
          div.classList.add("m0-src-block");
          div.setAttribute("data-m0-block-index", pre.getAttribute("data-m0-block-index") || "");
        }
        div.innerHTML = svg;
        pre.replaceWith(div);
      } catch (e) {
        const div = document.createElement("div");
        div.className = "m0-mermaid-error";
        if (pre.classList.contains("m0-src-block")) {
          div.classList.add("m0-src-block");
          div.setAttribute("data-m0-block-index", pre.getAttribute("data-m0-block-index") || "");
        }
        div.textContent = "Mermaid 渲染失败: " + (e.message || e);
        pre.replaceWith(div);
      }
    }
  }

  // ── Highlighter [[\h|text]] and format [[\c|...]], [[\b|...]], [[\i|...]] ──
  const HL_COLORS = ["yellow", "green", "red", "blue", "orange"];
  const HL_DEFAULT = "yellow";

  const HL_COLOR_MAP = {
    yellow: "#fff3cd",
    green: "#d4edda",
    red: "#f8d7da",
    blue: "#cce5ff",
    orange: "#ffe8cc"
  };

  const FC_COLOR_MAP = {
    red: "#dc3545",
    green: "#28a745",
    blue: "#007bff",
    orange: "#fd7e14",
    yellow: "#ffc107",
    purple: "#6f42c1",
    gray: "#6c757d"
  };

  const FC_COLORS = Object.keys(FC_COLOR_MAP);

  /**
   * Stack-based parser for [[\...]] syntax.
   * Handles nested [[...]] inside format commands by tracking bracket depth.
   *
   * Supported:
   *   [[\h|text]]              → yellow highlight
   *   [[\h:color|text]]        → colored highlight
   *   [[\h:bg:fg|text]]        → bg + fg highlight
   *   [[\h:id|text]]           → named highlight
   *   [[\h:id:color|text]]     → named + colored
   *   [[\h:id:bg:fg|text]]     → named + bg + fg (3 params after \h)
   *   [[\c:color|text]]        → font color
   *   [[\b|text]]              → bold
   *   [[\i|text]]              → italic
   */
  function renderHighlightSyntax(html) {
    const len = html.length;
    const result = [];
    let i = 0;

    while (i < len) {
      // Check for [[\ at current position
      if (i + 2 < len && html[i] === "[" && html[i + 1] === "[" && html[i + 2] === "\\") {
        // Try to parse a format command
        const parsed = tryParseFormatCmd(html, i);
        if (parsed) {
          // Find matching ]] by counting bracket depth
          const contentStart = parsed.pipeEnd + 1; // after the |
          let depth = 1;
          let j = contentStart;
          while (j < len && depth > 0) {
            if (j + 1 < len && html[j] === "[" && html[j + 1] === "[") {
              depth++;
              j += 2;
            } else if (j + 1 < len && html[j] === "]" && html[j + 1] === "]") {
              depth--;
              if (depth === 0) break;
              j += 2;
            } else {
              j++;
            }
          }
          if (depth === 0) {
            // Found matching ]]
            const innerText = html.substring(contentStart, j);
            const rendered = renderCommand(parsed.cmd, parsed.params, innerText);
            result.push(rendered);
            i = j + 2; // skip past the closing ]]
            continue;
          }
          // No matching ]] found — treat as plain text
        }
      }
      result.push(html[i]);
      i++;
    }
    return result.join("");
  }

  /**
   * Try to parse a format command starting at position `start`.
   * Returns { cmd, params, pipeEnd } or null.
   * `pipeEnd` is the index of the `|` character.
   */
  function tryParseFormatCmd(html, start) {
    // html[start..start+2] === "[[\"
    const cmdStart = start + 3; // after "[[\"
    if (cmdStart >= html.length) return null;

    const cmdChar = html[cmdStart];
    if (cmdChar === "h") {
      return parseHParams(html, start, cmdStart);
    } else if (cmdChar === "c") {
      return parseSimpleParams(html, start, cmdStart, "c", true);
    } else if (cmdChar === "b") {
      return parseSimpleParams(html, start, cmdStart, "b", false);
    } else if (cmdChar === "i") {
      return parseSimpleParams(html, start, cmdStart, "i", false);
    }
    return null;
  }

  /**
   * Parse [[\h:...|  — collect all colon-separated tokens before |
   */
  function parseHParams(html, start, cmdStart) {
    // cmdStart points to 'h'
    let pos = cmdStart + 1; // after 'h'
    const tokens = [];
    // Read optional :token:token:token|
    while (pos < html.length && html[pos] === ":") {
      pos++; // skip ':'
      const tokStart = pos;
      while (pos < html.length && html[pos] !== ":" && html[pos] !== "|") {
        pos++;
      }
      if (pos === tokStart) return null; // empty token
      tokens.push(html.substring(tokStart, pos));
    }
    if (pos >= html.length || html[pos] !== "|") return null;
    // Classify tokens for \h
    const params = classifyHParams(tokens);
    return { cmd: "h", params, pipeEnd: pos };
  }

  /**
   * Classify \h params:
   *  0 tokens → default yellow, no id
   *  1 token  → color (if known) or id
   *  2 tokens → could be id:color, color:fg, or bg:fg
   *  3 tokens → id:bg:fg
   */
  function classifyHParams(tokens) {
    const result = { bg: HL_DEFAULT, fg: null, id: null };

    if (tokens.length === 0) return result;

    if (tokens.length === 1) {
      const t = tokens[0];
      if (HL_COLORS.includes(t)) {
        result.bg = t;
      } else {
        result.id = t;
      }
      return result;
    }

    if (tokens.length === 2) {
      const t0 = tokens[0];
      const t1 = tokens[1];
      // Both are colors → bg:fg
      if (HL_COLORS.includes(t0) && HL_COLORS.includes(t1)) {
        result.bg = t0;
        result.fg = t1;
      }
      // t0 is id, t1 is color
      else if (!HL_COLORS.includes(t0) && HL_COLORS.includes(t1)) {
        result.id = t0;
        result.bg = t1;
      }
      // t0 is color, t1 is fg
      else if (HL_COLORS.includes(t0) && !HL_COLORS.includes(t1)) {
        result.bg = t0;
        result.fg = t1;
      }
      // Neither is a known color → id:fg (t1 is fg color value)
      else {
        result.id = t0;
        result.fg = t1;
      }
      return result;
    }

    if (tokens.length === 3) {
      // id:bg:fg
      result.id = tokens[0];
      result.bg = tokens[1];
      result.fg = tokens[2];
      return result;
    }

    return result;
  }

  /**
   * Parse [[\c:color|, [[\b|, [[\i|
   */
  function parseSimpleParams(html, start, cmdStart, cmd, needsParam) {
    let pos = cmdStart + 1; // after cmd letter
    const tokens = [];
    while (pos < html.length && html[pos] === ":") {
      pos++; // skip ':'
      const tokStart = pos;
      while (pos < html.length && html[pos] !== ":" && html[pos] !== "|") {
        pos++;
      }
      if (pos === tokStart) return null;
      tokens.push(html.substring(tokStart, pos));
    }
    if (pos >= html.length || html[pos] !== "|") return null;
    if (needsParam && tokens.length === 0) return null;
    return { cmd, params: { color: tokens[0] || null }, pipeEnd: pos };
  }

  /**
   * Render a parsed command into HTML.
   */
  function renderCommand(cmd, params, innerText) {
    if (cmd === "h") return renderHighlight(params, innerText);
    if (cmd === "c") return renderFontColor(params, innerText);
    if (cmd === "b") return `<strong class="m0-fmt-b">${innerText}</strong>`;
    if (cmd === "i") return `<em class="m0-fmt-i">${innerText}</em>`;
    return innerText;
  }

  /**
   * Render \h → <mark ...>text</mark>
   */
  function renderHighlight(params, innerText) {
    const attrs = [];

    // Background: use CSS class if named, otherwise inline style
    if (params.bg && params.bg !== HL_DEFAULT) {
      if (HL_COLORS.includes(params.bg)) {
        attrs.push(`class="hl-${params.bg}"`);
      } else {
        attrs.push(`style="background:${escAttr(params.bg)}"`);
      }
    }

    // Foreground: always inline style
    if (params.fg) {
      const fgValue = FC_COLOR_MAP[params.fg] || params.fg;
      const fgAttr = `color:${escAttr(fgValue)}`;
      const existing = attrs.findIndex(a => a.startsWith("style="));
      if (existing >= 0) {
        attrs[existing] = attrs[existing].replace(/"$/, `;${fgAttr}"`);
      } else {
        attrs.push(`style="${fgAttr}"`);
      }
    }

    // Named id
    if (params.id) {
      attrs.push(`data-hl-id="${escAttr(params.id)}"`);
    }

    const attrStr = attrs.length > 0 ? " " + attrs.join(" ") : "";
    return `<mark${attrStr}>${innerText}</mark>`;
  }

  /**
   * Render \c:color → <span class="m0-fc-color"> or <span style="color:...">
   */
  function renderFontColor(params, innerText) {
    const color = params.color;
    if (!color) return innerText;
    if (FC_COLORS.includes(color)) {
      return `<span class="m0-fc-${escAttr(color)}">${innerText}</span>`;
    }
    return `<span style="color:${escAttr(color)}">${innerText}</span>`;
  }

  // ── Image Lightbox ──
  function attachImageLightbox(container) {
    container.querySelectorAll("img").forEach((img) => {
      if (img.closest(".m0-lightbox-overlay")) return;
      img.style.cursor = "zoom-in";
      // 诊断：检查图片加载状态
      console.log("[img-debug] src:", img.src, "naturalWidth:", img.naturalWidth, "complete:", img.complete, "display:", getComputedStyle(img).display, "width:", getComputedStyle(img).width, "height:", getComputedStyle(img).height, "maxWidth:", getComputedStyle(img).maxWidth);
      img.addEventListener("error", () => console.error("[img-debug] LOAD ERROR:", img.src));
      img.addEventListener("load", () => console.log("[img-debug] LOAD OK:", img.src, "naturalWidth:", img.naturalWidth));
      img.addEventListener("click", () => {
        const overlay = document.createElement("div");
        overlay.className = "m0-lightbox-overlay";
        const bigImg = document.createElement("img");
        bigImg.src = img.src;
        bigImg.className = "m0-lightbox-image";
        overlay.appendChild(bigImg);
        overlay.addEventListener("click", () => overlay.remove());
        document.body.appendChild(overlay);
      });
    });
  }

  // ── Local image path rewriting ──
  let _kbRootForImages = null;
  let _currentFileDir = ""; // relative dir of current file within KB (e.g. "subdir/" or "")
  function setKbRootForImages(root) { _kbRootForImages = root; }
  function setCurrentFileDir(dir) { _currentFileDir = dir; }
  function rewriteLocalImagePaths(html) {
    if (!_kbRootForImages) { console.log("[img-rewrite] SKIP: _kbRootForImages 未设置"); return html; }
    console.log("[img-rewrite] _kbRootForImages=" + _kbRootForImages + " _currentFileDir=" + (_currentFileDir || "(root)"));
    // Match any <img src="..."> and rewrite relative paths.
    return html.replace(
      /(<img\s[^>]*src=")([^"]+)"/g,
      (_, prefix, src) => {
        // Skip absolute URLs and data URIs
        if (/^(https?:|data:|\/)/i.test(src)) return prefix + src + '"';
        // Normalize: remove leading ./
        const clean = src.replace(/^\.\//, "");
        // Resolve relative to current file's directory within KB
        const relPath = _currentFileDir + clean;
        // Encode each path segment so / remains as separator
        const encoded = relPath.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/");
        const apiBase = window.MemoriaBridge?.apiBase || "";
        const url = apiBase + "/files/" + encoded;
        console.log("[img-rewrite]", src, "→", url, "(relPath=" + relPath + ")");
        return prefix + url + '"';
      }
    );
  }

  function postProcessMemoriaLinks(html, knownTargets, linkOverrides, blockStartLine, blockMarkdown) {
    const lookup =
      knownTargets instanceof Set
        ? knownTargets
        : knownTargets && typeof knownTargets.has === "function"
          ? knownTargets
          : null;
    const overrides =
      linkOverrides && typeof linkOverrides === "object" ? linkOverrides : null;

    function routeTargetsFor(key) {
      return overrides?.[key.trim()] || null;
    }

    function resolvedTargetsFor(key) {
      const route = routeTargetsFor(key);
      if (!route?.length) return null;
      if (!lookup) return route;
      return route.filter((t) => lookup.has(t));
    }

    function isDirectTarget(key) {
      return lookup ? lookup.has(key) : false;
    }

    function isRoutedTarget(key, routeTargets) {
      if (!routeTargets?.length) return false;
      const resolved = lookup
        ? routeTargets.filter((t) => lookup.has(t))
        : routeTargets;
      if (!resolved.length) return false;
      if (resolved.length > 1) return true;
      return resolved[0] !== key || !isDirectTarget(key);
    }

    function isResolved(id) {
      const key = id.trim();
      const resolved = resolvedTargetsFor(key);
      if (resolved !== null) {
        return resolved.length > 0;
      }
      return lookup ? lookup.has(key) : null;
    }

    function linkTitle(key, routeTargets, resolved) {
      const resolvedList = lookup
        ? (routeTargets || []).filter((t) => lookup.has(t))
        : routeTargets || [];
      const total = routeTargets?.length || 0;
      if (resolved === false) {
        return `未绑定目标 · ${key}（${total} 个目标均无法解析）`;
      }
      if (routeTargets?.length) {
        if (resolvedList.length > 1) {
          return `多目标链接 · ${resolvedList.length}/${total} 可跳转`;
        }
        if (resolvedList.length === 1) {
          return `路由链接 · 跳转到 ${resolvedList[0]}`;
        }
      }
      if (resolved === true) {
        return `跳转到 ${key}`;
      }
      return "链接跳转";
    }

    const srcMd = blockMarkdown != null ? String(blockMarkdown) : "";
    const baseLine = Number(blockStartLine) || 1;
    const lineByIndex = [];
    if (srcMd) {
      const re = /\[\[([^\]|#\]]+)(?:#([^\]|#]+))?(?:\|([^\]]+))?\]\]/g;
      let m;
      while ((m = re.exec(srcMd))) {
        lineByIndex.push(baseLine + (srcMd.slice(0, m.index).match(/\n/g) || []).length);
      }
    }
    let wlIdx = 0;

    return html.replace(
      /\[\[([^\]|#\]]+)(?:#([^\]|#]+))?(?:\|([^\]]+))?\]\]/g,
      (_, id, type, display) => {
        const key = id.trim();
        const safeId = escAttr(key);
        const safeType = type ? escAttr(type.trim()) : "";
        const label = display
          ? escAttr(display.trim())
          : safeType
            ? `${safeId}<span class="m0-link-type">#${safeType}</span>`
            : safeId;
        const routeTargets = overrides?.[key];
        const resolved = isResolved(id);
        const routed = isRoutedTarget(key, routeTargets);
        let linkCls = "m0-link-pending";
        if (resolved === true) {
          linkCls = routed ? "m0-link-multi" : "m0-link-resolved";
        } else if (resolved === false) {
          linkCls = "m0-link-broken memoria-broken-link";
        }
        const title = linkTitle(key, routeTargets, resolved);
        const tabIndex = linkCls.includes("m0-link-broken") ? "-1" : "0";
        const linkLine = lineByIndex[wlIdx] ?? baseLine;
        wlIdx += 1;
        let attrs =
          `class="memoria-link ${linkCls}" role="link" tabindex="${tabIndex}" ` +
          `title="${title}" data-link-target="${safeId}" data-link-type="${safeType}" ` +
          `data-link-line="${linkLine}"`;
        if (routed && routeTargets?.length) {
          const json = JSON.stringify(routeTargets).replace(/'/g, "&#39;");
          attrs += ` data-link-targets='${json}'`;
        }
        return `<span ${attrs}>${label}</span>`;
      }
    );
  }

  function escAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function isBlankLine(line) {
    return line.trim() === "";
  }

  function isAtxHeading(line) {
    return /^#{1,6}(?:\s|$)/.test(line);
  }

  function isFenceLine(line) {
    return /^(`{3,}|~{3,})/.test(line.trim());
  }

  function isHrLine(line) {
    return /^(\*{3,}|-{3,}|_{3,})\s*$/.test(line.trim());
  }

  function isUlItem(line) {
    return /^(\s*)[-*+]\s+/.test(line);
  }

  function isOlItem(line) {
    return /^(\s*)\d+\.\s+/.test(line);
  }

  function isBlockquoteLine(line) {
    return /^>\s?/.test(line);
  }

  function splitSourceBlocks(body) {
    const lines = body.split("\n");
    const blocks = [];
    let i = 0;

    if (lines[0]?.trim() === "---") {
      let j = 1;
      while (j < lines.length && lines[j].trim() !== "---") j += 1;
      if (j < lines.length) {
        blocks.push({
          kind: "frontmatter",
          startLine: 1,
          endLine: j + 1,
          markdown: lines.slice(0, j + 1).join("\n"),
        });
        i = j + 1;
        while (i < lines.length && isBlankLine(lines[i])) i += 1;
      }
    }

    while (i < lines.length) {
      if (isBlankLine(lines[i])) {
        // 每个空行一个独立 block，允许在预览区域逐行定位和编辑
        blocks.push({
          kind: "blank",
          startLine: i + 1,
          endLine: i + 1,
          markdown: "",
        });
        i += 1;
        continue;
      }

      const start = i;

      if (lines[i].trim() === "$$") {
        let j = i + 1;
        while (j < lines.length && lines[j].trim() !== "$$") j += 1;
        if (j < lines.length) {
          blocks.push({
            kind: "display-math",
            startLine: start + 1,
            endLine: j + 1,
            markdown: lines.slice(start, j + 1).join("\n"),
          });
          i = j + 1;
          continue;
        }
      }

      if (isFenceLine(lines[i])) {
        const fence = lines[i].trim().match(/^[`~]+/)[0];
        let j = i + 1;
        while (j < lines.length) {
          if (lines[j].trim().startsWith(fence)) {
            j += 1;
            break;
          }
          j += 1;
        }
        blocks.push({
          kind: "fence",
          startLine: start + 1,
          endLine: j,
          markdown: lines.slice(start, j).join("\n"),
        });
        i = j;
        continue;
      }

      if (isAtxHeading(lines[i])) {
        blocks.push({
          kind: "heading",
          startLine: start + 1,
          endLine: start + 1,
          markdown: lines[i],
        });
        i += 1;
        continue;
      }

      if (isHrLine(lines[i])) {
        blocks.push({
          kind: "hr",
          startLine: start + 1,
          endLine: start + 1,
          markdown: lines[i],
        });
        i += 1;
        continue;
      }

      if (isBlockquoteLine(lines[i])) {
        let j = i + 1;
        while (j < lines.length && !isBlankLine(lines[j]) && isBlockquoteLine(lines[j])) {
          j += 1;
        }
        blocks.push({
          kind: "blockquote",
          startLine: start + 1,
          endLine: j,
          markdown: lines.slice(start, j).join("\n"),
        });
        i = j;
        continue;
      }

      if (isUlItem(lines[i]) || isOlItem(lines[i])) {
        let j = i + 1;
        while (j < lines.length) {
          if (isBlankLine(lines[j])) {
            let k = j + 1;
            while (k < lines.length && isBlankLine(lines[k])) k += 1;
            if (k < lines.length && (isUlItem(lines[k]) || isOlItem(lines[k]))) {
              j = k;
              continue;
            }
            break;
          }
          if (isUlItem(lines[j]) || isOlItem(lines[j])) {
            j += 1;
            continue;
          }
          if (/^\s{2,}\S/.test(lines[j])) {
            j += 1;
            continue;
          }
          break;
        }
        blocks.push({
          kind: "list",
          startLine: start + 1,
          endLine: j,
          markdown: lines.slice(start, j).join("\n"),
        });
        i = j;
        continue;
      }

      let j = i + 1;
      while (j < lines.length) {
        if (isBlankLine(lines[j])) break;
        if (lines[j].trim() === "$$") break;
        if (isAtxHeading(lines[j])) break;
        if (isFenceLine(lines[j])) break;
        if (isHrLine(lines[j])) break;
        if (isBlockquoteLine(lines[j])) break;
        if (isUlItem(lines[j]) || isOlItem(lines[j])) break;
        j += 1;
      }
      blocks.push({
        kind: "paragraph",
        startLine: start + 1,
        endLine: j,
        markdown: lines.slice(start, j).join("\n"),
      });
      i = j;
    }

    return blocks;
  }

  function attachLineAttrs(html, block) {
    html = String(html || "").trim();
    if (!html) return "";

    const extraClass =
      block.kind === "display-math" ? "m0-display-math m0-src-block" : "m0-src-block";
    const lineAttrs =
      `data-m0-src-line="${block.startLine}" data-m0-src-line-end="${block.endLine}"`;
    const singleRoot = /^<([a-zA-Z][a-zA-Z0-9]*)([^>]*)>[\s\S]*<\/\1>$/.test(html);
    const tagMatch = singleRoot ? html.match(/^<([a-zA-Z][a-zA-Z0-9]*)([^>]*)>/) : null;

    if (tagMatch) {
      const tag = tagMatch[1];
      let rest = tagMatch[2];
      if (/class=/.test(rest)) {
        rest = rest.replace(/class=(["'])([^"']*)\1/, (_, q, cls) =>
          cls.includes("m0-src-block") ? `class=${q}${cls}${q}` : `class=${q}${cls} ${extraClass}${q}`
        );
      } else {
        rest += ` class="${extraClass}"`;
      }
      if (!/data-m0-src-line=/.test(rest)) {
        rest += ` ${lineAttrs}`;
      }
      return html.replace(/^<[a-zA-Z][a-zA-Z0-9]*[^>]*>/, `<${tag}${rest}>`);
    }

    return `<div class="${extraClass}" ${lineAttrs}>${html}</div>`;
  }

  function renderDisplayMathBlock(block) {
    // Strip $$ delimiters and use \[...\] instead, with HTML-escaping.
    // Raw $$...$$ as innerHTML is unreliable: the browser's HTML parser may
    // misinterpret LaTeX special chars (e.g. &= in aligned environments),
    // and MathJax's delimiter scanning can miss $$ in certain DOM contexts.
    let tex = block.markdown.trim();
    if (tex.startsWith("$$")) tex = tex.slice(2);
    if (tex.endsWith("$$")) tex = tex.slice(0, -2);
    tex = tex.trim();
    // HTML-escape so &, <, > survive innerHTML parsing intact;
    // MathJax reads textContent, which decodes entities back to the originals.
    const escaped = tex
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return attachLineAttrs(`\\[${escaped}\\]`, block);
  }

  function splitByWikilinks(body) {
    const parts = [];
    const re = /\[\[[^\]]+\]\]/g;
    let last = 0;
    let m;
    while ((m = re.exec(body))) {
      if (m.index > last) {
        parts.push({ type: "plain", text: body.slice(last, m.index) });
      }
      parts.push({ type: "wl", text: m[0] });
      last = m.index + m[0].length;
    }
    if (last < body.length) {
      parts.push({ type: "plain", text: body.slice(last) });
    }
    return parts.length ? parts : [{ type: "plain", text: body }];
  }

  /** 侧车已配置、正文尚未 [[]] 包裹的 anchor 文本 → 虚拟维基链接（仅预览/渲染） */
  function injectSidecarPlainLinks(body, sidecarLinks) {
    const links = (sidecarLinks || []).filter(
      (l) => l && String(l.anchor_text || "").trim() && (l.targets || []).length
    );
    if (!links.length || !body) return body;

    const byLen = [...links].sort(
      (a, b) => String(b.anchor_text).length - String(a.anchor_text).length
    );

    return splitByWikilinks(body)
      .map((part) => {
        if (part.type !== "plain") return part.text;
        let text = part.text;
        const lines = text.split("\n");
        for (const link of byLen) {
          const anchor = String(link.anchor_text).trim();
          if (!anchor) continue;
          const inst = link.instances;
          if (inst && inst.length) {
            const instLines = new Set(
              inst.map((x) => Number(x.line)).filter((n) => n > 0)
            );
            const excluded = new Set(
              (link.excluded || []).map((x) => Number(x.line)).filter((n) => n > 0)
            );
            const wrapped = `[[${anchor}]]`;
            lines.forEach((row, i) => {
              const ln = i + 1;
              if (!instLines.has(ln) || excluded.has(ln)) return;
              if (row.includes(wrapped) || !row.includes(anchor)) return;
              lines[i] = row.split(anchor).join(wrapped);
            });
            text = lines.join("\n");
            continue;
          }
          const wrapped = `[[${anchor}]]`;
          text = text.split(anchor).join(wrapped);
        }
        return text;
      })
      .join("");
  }

  // ── Source-Preview Position Mapping (Segment Annotation) ──

  /**
   * Parse a source line to identify inline markdown tokens and their positions.
   * Returns an ordered array of segments, each with source column info.
   *
   * Example: "## Hello **world** and *foo*"
   * → [
   *     { type: "text",   srcCol: 3,  srcEnd: 9,  text: "Hello " },
   *     { type: "bold",   srcCol: 11, srcEnd: 16, text: "world", prefix: "**", suffix: "**" },
   *     { type: "text",   srcCol: 18, srcEnd: 23, text: " and " },
   *     { type: "italic", srcCol: 24, srcEnd: 27, text: "foo",   prefix: "*",  suffix: "*" },
   *   ]
   */
  function parseInlineTokens(sourceLine) {
    const tokens = [];
    const len = sourceLine.length;
    let i = 0;

    // Skip leading whitespace / markdown prefix (##, -, >, |, 1., etc.)
    // The prefix is not part of any inline token — it's block-level structure.
    const prefixMatch = sourceLine.match(/^(\s*(?:#{1,6}\s|[-*+]\s+|>\s?|\|\s?|\d+\.\s+)?)/);
    if (prefixMatch) {
      i = prefixMatch[1].length;
    }

    while (i < len) {
      // ── Bold: **...** or __...__ (单行匹配，不跨行) ──
      let m;
      if ((m = sourceLine.slice(i).match(/^(\*\*|__)([^\n]+?)\1/))) {
        const fullLen = m[0].length;
        const contentStart = i + m[1].length; // after opening delimiter
        tokens.push({
          type: "bold", srcCol: contentStart, srcEnd: contentStart + m[2].length,
          text: m[2], prefix: m[1], suffix: m[1],
        });
        i += fullLen;
        continue;
      }

      // ── Italic: *...* or _..._ (单行匹配，不跨行) ──
      if ((m = sourceLine.slice(i).match(/^(\*|_)(?!\1)([^\n]+?)\1/))) {
        const fullLen = m[0].length;
        const contentStart = i + m[1].length;
        tokens.push({
          type: "italic", srcCol: contentStart, srcEnd: contentStart + m[2].length,
          text: m[2], prefix: m[1], suffix: m[1],
        });
        i += fullLen;
        continue;
      }

      // ── Strikethrough: ~~...~~ (单行匹配) ──
      if ((m = sourceLine.slice(i).match(/^(~~)([^\n]+?)\1/))) {
        const fullLen = m[0].length;
        const contentStart = i + m[1].length;
        tokens.push({
          type: "strike", srcCol: contentStart, srcEnd: contentStart + m[2].length,
          text: m[2], prefix: m[1], suffix: m[1],
        });
        i += fullLen;
        continue;
      }

      // ── Inline code: `...` ──
      if ((m = sourceLine.slice(i).match(/^`([^`]+)`/))) {
        const fullLen = m[0].length;
        const contentStart = i + 1;
        tokens.push({
          type: "code", srcCol: contentStart, srcEnd: contentStart + m[1].length,
          text: m[1], prefix: "`", suffix: "`",
        });
        i += fullLen;
        continue;
      }

      // ── Highlight: [[\h:...|text]] or [[\h|text]] (单行匹配) ──
      if ((m = sourceLine.slice(i).match(/^\[\[\\h(?::[^|]*)?\|([^\n]+?)\]\]/))) {
        const fullMatch = m[0];
        const innerText = m[1];
        const contentStart = i + fullMatch.indexOf(innerText);
        tokens.push({
          type: "highlight", srcCol: contentStart, srcEnd: contentStart + innerText.length,
          text: innerText, prefix: fullMatch.slice(0, fullMatch.indexOf(innerText)),
          suffix: "]]",
        });
        i += fullMatch.length;
        continue;
      }

      // ── Font color: [[\c:color|text]] (单行匹配) ──
      if ((m = sourceLine.slice(i).match(/^\[\[\\c:[^|]+\|([^\n]+?)\]\]/))) {
        const fullMatch = m[0];
        const innerText = m[1];
        const contentStart = i + fullMatch.indexOf(innerText);
        tokens.push({
          type: "fontcolor", srcCol: contentStart, srcEnd: contentStart + innerText.length,
          text: innerText, prefix: fullMatch.slice(0, fullMatch.indexOf(innerText)),
          suffix: "]]",
        });
        i += fullMatch.length;
        continue;
      }

      // ── Wikilink: [[target]] or [[target|display]] ──
      if ((m = sourceLine.slice(i).match(/^\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]/))) {
        const fullMatch = m[0];
        const displayText = m[2] || m[1]; // display text or target
        const contentStart = i + fullMatch.indexOf(displayText);
        tokens.push({
          type: "wikilink", srcCol: contentStart, srcEnd: contentStart + displayText.length,
          text: displayText, prefix: "[[", suffix: "]]",
        });
        i += fullMatch.length;
        continue;
      }

      // ── Link: [text](url) ──
      if ((m = sourceLine.slice(i).match(/^\[([^\]]+)\]\([^)]+\)/))) {
        const fullMatch = m[0];
        const linkText = m[1];
        const contentStart = i + 1; // after the opening [
        tokens.push({
          type: "link", srcCol: contentStart, srcEnd: contentStart + linkText.length,
          text: linkText, prefix: "[", suffix: "](" + fullMatch.slice(fullMatch.indexOf("](") + 2),
        });
        i += fullMatch.length;
        continue;
      }

      // ── Inline math: $...$ (single dollar, not $$) ──
      if ((m = sourceLine.slice(i).match(/^\$((?:\\.|[^$\n\\])+?)\$/))) {
        const fullLen = m[0].length;
        const contentStart = i + 1;
        tokens.push({
          type: "math", srcCol: contentStart, srcEnd: contentStart + m[1].length,
          text: m[1], prefix: "$", suffix: "$",
        });
        i += fullLen;
        continue;
      }

      // ── Plain text: accumulate until next token or end ──
      let textStart = i;
      let textEnd = i;
      while (textEnd < len) {
        const rest = sourceLine.slice(textEnd);
        // Check if any inline token starts here
        if (/^(\*\*|__|\*|_|~~|`|\[\[\\|\[\[|\[[^[]|\$)/.test(rest)) break;
        textEnd++;
      }
      if (textEnd > textStart) {
        tokens.push({
          type: "text", srcCol: textStart, srcEnd: textEnd,
          text: sourceLine.slice(textStart, textEnd), prefix: "", suffix: "",
        });
      }
      i = textEnd;
    }

    return tokens;
  }

  /**
   * Post-process rendered HTML to annotate text nodes with source position data.
   * Wraps each text segment in <span class="m0-seg" data-line="L" data-col="C">.
   *
   * Strategy: for each m0-src-block, align rendered DOM text nodes
   * with parseInlineTokens output, then wrap with position spans.
   */
  function annotateSegments(html, sourceLines, startLine) {
    if (!html || !sourceLines) return html;

    // For single-line blocks, parse inline tokens from the source line
    // and align them with the rendered HTML text content.
    // We work on the HTML string directly by walking text nodes after
    // setting innerHTML on a temporary container.
    const tmp = document.createElement("div");
    tmp.innerHTML = html;

    // For each m0-src-block element (or the root if single element)
    const rootEl = tmp.firstElementChild;
    if (!rootEl) return html;

    const lineNum = startLine;
    const srcLine = sourceLines[lineNum - 1] || "";
    const tokens = parseInlineTokens(srcLine);

    if (!tokens.length) return html;

    // Walk all text nodes in the rendered block, aligning with tokens
    const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    let n;
    while ((n = walker.nextNode())) {
      // Skip text inside non-editable containers (mjx-container, pre, code, etc.)
      const parent = n.parentElement;
      if (parent && parent.closest('mjx-container, pre, code, .m0-mermaid-container')) continue;
      const txt = n.textContent;
      if (txt) textNodes.push({ node: n, text: txt });
    }

    if (!textNodes.length) return html;

    // Build the rendered text content (what user sees) for alignment
    const renderedText = textNodes.map(t => t.text).join("");

    // Build token text content (what the tokens produce)
    const tokenText = tokens.map(t => t.text).join("");

    // Simple alignment: try to match rendered text with token text.
    // They may differ slightly due to rendering (e.g., math → rendered symbols),
    // but for common inline formats (bold, italic, links, highlights) they match.
    // We use a greedy left-to-right alignment.
    let tokenIdx = 0;
    let tokenCharIdx = 0; // position within current token's text
    const segments = []; // { node, nodeOffset, nodeLen, line, col }

    for (const tn of textNodes) {
      let pos = 0;
      while (pos < tn.text.length && tokenIdx < tokens.length) {
        const tok = tokens[tokenIdx];
        const remaining = tok.text.length - tokenCharIdx;
        const avail = tn.text.length - pos;

        if (remaining <= avail) {
          // Current token ends within this text node
          segments.push({
            node: tn.node,
            start: pos,
            end: pos + remaining,
            line: lineNum,
            col: tok.srcCol + tokenCharIdx,
          });
          pos += remaining;
          tokenIdx++;
          tokenCharIdx = 0;
        } else {
          // Current token spans beyond this text node
          segments.push({
            node: tn.node,
            start: pos,
            end: tn.text.length,
            line: lineNum,
            col: tok.srcCol + tokenCharIdx,
          });
          tokenCharIdx += avail;
          pos = tn.text.length;
        }
      }
    }

    // Now wrap each segment's portion of its text node in a span.
    // We process segments in reverse order to avoid offset shifts.
    for (let s = segments.length - 1; s >= 0; s--) {
      const seg = segments[s];
      const textNode = seg.node;
      const fullText = textNode.textContent;

      if (seg.start === 0 && seg.end === fullText.length) {
        // Entire text node becomes one segment span
        const span = document.createElement("span");
        span.className = "m0-seg";
        span.dataset.line = String(seg.line);
        span.dataset.col = String(seg.col);
        textNode.parentNode.replaceChild(span, textNode);
        span.textContent = fullText;
      } else {
        // Partial text node — split and wrap
        const before = fullText.slice(0, seg.start);
        const segText = fullText.slice(seg.start, seg.end);
        const after = fullText.slice(seg.end);
        const parent = textNode.parentNode;
        const span = document.createElement("span");
        span.className = "m0-seg";
        span.dataset.line = String(seg.line);
        span.dataset.col = String(seg.col);
        span.textContent = segText;

        const frag = document.createDocumentFragment();
        if (before) frag.appendChild(document.createTextNode(before));
        frag.appendChild(span);
        if (after) frag.appendChild(document.createTextNode(after));
        parent.replaceChild(frag, textNode);
      }
    }

    return tmp.innerHTML;
  }

  function renderMarkdownBlock(block, knownTargets, linkOverrides, sidecarLinks) {
    let markdown = injectSidecarPlainLinks(block.markdown, sidecarLinks);
    const { text, blocks } = protectMath(markdown);
    let html = marked.parse(text, { gfm: true, breaks: true });
    html = restoreMath(html, blocks);
    html = renderHighlightSyntax(html);
    html = rewriteLocalImagePaths(html);
    html = postProcessMemoriaLinks(
      html,
      knownTargets,
      linkOverrides,
      block.startLine,
      markdown
    );
    html = attachLineAttrs(html, block);
    return html;
  }

  function countExpectedMathBlocks(body) {
    let n = 0;
    const lines = body.split("\n");
    let inBlock = false;
    for (const line of lines) {
      if (line.trim() === "$$") {
        if (!inBlock) inBlock = true;
        else {
          n += 1;
          inBlock = false;
        }
      }
    }
    const inline = body.match(/\$(?:\\.|[^\$\n\\])+\$/g);
    n += inline ? inline.length : 0;
    return n;
  }

  function diagnose(container, body) {
    const report = {
      ok: true,
      mathExpected: countExpectedMathBlocks(body || ""),
      mathRendered: container.querySelectorAll("mjx-container").length,
      mathInline: container.querySelectorAll('mjx-container:not([display="true"])').length,
      mathDisplay: container.querySelectorAll('mjx-container[display="true"]').length,
      mathErrors: [],
      rawDelimiters: [],
      messages: [],
    };

    container.querySelectorAll("mjx-merror").forEach((el) => {
      report.ok = false;
      report.mathErrors.push((el.textContent || "").trim().slice(0, 120) || "TeX 错误");
    });

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.parentElement?.closest("mjx-container, script, style, code, pre")) continue;
      const t = node.textContent || "";
      if (/\$\$/.test(t) || /\$[^$\n]+\$/.test(t)) {
        report.ok = false;
        report.rawDelimiters.push(t.trim().slice(0, 80));
      }
    }

    if (report.mathExpected > 0 && report.mathRendered === 0) {
      report.ok = false;
      report.messages.push("未检测到已渲染公式");
    }
    if (report.mathErrors.length) {
      report.messages.push(`${report.mathErrors.length} 处 TeX 错误`);
    }
    if (report.rawDelimiters.length) {
      report.messages.push(`${report.rawDelimiters.length} 处未处理定界符`);
    }

    return report;
  }

  function renderHtml(body, options) {
    if (!window.marked) {
      return `<pre class="m0-preview-error">marked 未加载</pre>`;
    }
    const knownTargets = options?.knownTargets || null;
    const linkOverrides = options?.linkOverrides || null;
    const sidecarLinks = options?.sidecarLinks || null;
    const normalized = normalizeBody(body);
    return splitSourceBlocks(normalized)
      .map((block) => {
        if (block.kind === "blank") {
          // 空行占位 block：生成可选中、可定位的空行元素
          const lineAttr = `data-m0-src-line="${block.startLine}" data-m0-src-line-end="${block.endLine}"`;
          return `<div class="m0-src-block m0-blank-block" ${lineAttr}><br></div>`;
        }
        if (block.kind === "display-math") {
          return renderDisplayMathBlock(block);
        }
        return renderMarkdownBlock(block, knownTargets, linkOverrides, sidecarLinks);
      })
      .filter(Boolean)
      .join("\n");
  }

  async function renderToElement(container, body, options) {
    container.innerHTML = renderHtml(body, options);
    // innerHTML 已同步设置完毕，执行回调（用于光标恢复等需要即时操作的场合）
    if (options?.afterSync) {
      try { options.afterSync(); } catch (_) {}
    }
    const report = {
      ok: false,
      mathExpected: countExpectedMathBlocks(body || ""),
      mathRendered: 0,
      mathErrors: [],
      rawDelimiters: [],
      messages: ["MathJax 未就绪"],
    };
    try {
      await initMathJax();
      if (window.MathJax?.typesetClear) {
        window.MathJax.typesetClear([container]);
      }
      if (window.MathJax?.typesetPromise) {
        await window.MathJax.typesetPromise([container]);
      }
      Object.assign(report, diagnose(container, body));
      if (
        report.mathErrors.length === 0 &&
        report.rawDelimiters.length === 0 &&
        (report.mathExpected === 0 || report.mathRendered > 0)
      ) {
        report.ok = true;
      }
    } catch (e) {
      report.ok = false;
      report.messages = [String(e.message || e)];
      console.warn("MathJax typeset:", e);
    }
    // Post-render: Mermaid diagrams
    await renderMermaidBlocks(container);
    // Post-render: Image lightbox
    attachImageLightbox(container);
    // Post-render: enable editing in preview
    enableEditing(container);
    container.dataset.previewOk = report.ok ? "1" : "0";
    return report;
  }

  // ── Preview cursor mapping (click → focus source editor) ──
  function enableEditing(container) {
    const preview = container.closest(".m0-preview") || container;
    if (!preview.classList.contains("m0-preview")) return;
    // 预览区域不设 contenteditable — 点击映射到源码编辑器
    // 光标由 CSS cursor: text 提供
  }

  return {
    renderHtml,
    renderToElement,
    initMathJax,
    normalizeBody,
    diagnose,
    countExpectedMathBlocks,
    renderMermaidBlocks,
    attachImageLightbox,
    renderHighlightSyntax,
    setKbRootForImages,
    setCurrentFileDir,
    rewriteLocalImagePaths,
    parseInlineTokens,
    annotateSegments,
  };
})();
