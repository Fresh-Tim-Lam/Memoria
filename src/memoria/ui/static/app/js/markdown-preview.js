/**
 * Markdown 预览：marked (GFM) + MathJax 3 full (TeX 最高兼容)
 * 行内 / 块级公式分离占位，避免行内公式被 marked 拆成独立段落。
 */
window.MemoriaMarkdownPreview = (function () {
  "use strict";

  const BLOCK_PH = "MEMORIA_MATH_BLOCK_";
  const INLINE_START = "\uE000";
  const INLINE_END = "\uE001";

  /** i18n 取词助手（无 MemoriaI18n 时回退键名）。 */
  const _t = (k, p) => (window.MemoriaI18n ? window.MemoriaI18n.t(k, p) : k);

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
          reject(new Error(_t("preview.math.timeout")));
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
    // 主题配置集中在 js/mermaid-theme.js（颜色读 :root 的 --mmd-*，浅色主题只改这些变量）；
    // 取不到时退回最小可用配置，保证 mermaid 仍能渲染。
    window.mermaid.initialize(
      window.MemoriaMermaidTheme
        ? window.MemoriaMermaidTheme.options()
        : {
            startOnLoad: false,
            theme: "default",
            securityLevel: "loose",
            fontFamily: "inherit",
            // mermaid 默认把 parse 失败画成一张 "Syntax error in text / mermaid version X" 的错误图；
            // 关掉它改为抛异常，由 renderMermaidBlocks 统一提示（用户不该看到 mermaid 的原始报错图）。
            suppressErrorRendering: true,
          }
    );
    mermaidInited = true;
  }

  async function renderMermaidBlocks(container) {
    initMermaid();
    if (!window.mermaid?.render) return;
    const els = container.querySelectorAll("code.language-mermaid");
    for (const el of els) {
      const pre = el.parentElement;
      if (!pre) continue;
      // 编辑中途会出现空/半成品源码；空源码交给 mermaid 必然得到一张错误图 → 直接跳过
      // 2026-09-28 还原：**不再剥任何指令行**（人：「双击之后不知咋的就渲染失败」——
      // 指令行是个未定型的东西，交给 mermaid 当普通注释即可；剥行属于"改渲染路径"，一律不做）。
      const src = (el.textContent || "").trim();
      if (!src) continue;
      // 重入/并发保护：同一 <pre> 只渲染一次；await 后若已被新一轮渲染替换则放弃写入
      if (pre.dataset.mermaidRendered === "1") continue;
      pre.dataset.mermaidRendered = "1";
      const id = "mermaid-" + Math.random().toString(36).slice(2, 10);
      try {
        const { svg } = await _mmdRenderWithFontSync(id, src);   // 2026-10-05 根因修法：渲染前等字体就绪（见文件尾 _mmdRenderWithFontSync 注释）
        if (!pre.isConnected) continue;
        const div = document.createElement("div");
        div.className = "-mermaid-container";
        // 保留 -src-block 与块属性：双击编辑靠 block-index，预览高亮/滚动定位靠 src-line(-end)
        if (pre.classList.contains("-src-block")) div.classList.add("-src-block");
        ["data--block-index", "data--src-line", "data--src-line-end"].forEach((k) => {
          const v = pre.getAttribute(k);
          if (v) div.setAttribute(k, v);
        });
        // 嵌套场景（引用/列表内的 mermaid）<pre> 无 -src-block，但行号属性同样要带过去
        // 2026-09-28：**去掉 pan 包装层**（人：「先把渲染做正常再说」）——
        // 原来这里无条件包一层 `.-mermaid-pan`（带 overflow:hidden），与交互开关无关，
        // 等于把渲染路径本身改了 ⇒ 图会被裁/走形。交互整层默认关时，DOM 必须与老路径完全一致。
        div.innerHTML = svg; div._mmdDirective = _parseMemoriaViewDirective(src).found;   // 只解析（不剥行）视图指令，供 _attachMermaidView 还原尺寸/位移；渲染路径零改动
        pre.replaceWith(div); _afterMermaidInsert(div);
      } catch (e) {
        if (!pre.isConnected) continue;
        const div = document.createElement("div");
        div.className = "-mermaid-error";
        if (pre.classList.contains("-src-block")) div.classList.add("-src-block");
        ["data--block-index", "data--src-line", "data--src-line-end"].forEach((k) => {
          const v = pre.getAttribute(k);
          if (v) div.setAttribute(k, v);
        });
        // 同上：渲染失败换成短红框后行号属性仍要保留，否则该块对行号系消费者整块消失
        div.textContent = _t("preview.mermaidFail", { msg: e.message || e });
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
    if (cmd === "b") return `<strong class="-fmt-b">${innerText}</strong>`;
    if (cmd === "i") return `<em class="-fmt-i">${innerText}</em>`;
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
   * Render \c:color → <span class="-fc-color"> or <span style="color:...">
   */
  function renderFontColor(params, innerText) {
    const color = params.color;
    if (!color) return innerText;
    if (FC_COLORS.includes(color)) {
      return `<span class="-fc-${escAttr(color)}">${innerText}</span>`;
    }
    return `<span style="color:${escAttr(color)}">${innerText}</span>`;
  }

  /** Lightbox 放大：滚轮以光标为中心缩放、左键拖拽平移；Esc / 右键 / 点击背景退出。 */
  function openLightbox(srcImg) {
    if (document.querySelector(".-lightbox-overlay")) return;
    const overlay = document.createElement("div");
    overlay.className = "-lightbox-overlay";
    const bigImg = _lightboxBigElement(srcImg);
    if (bigImg.tagName === "IMG") bigImg.src = srcImg.src;
    bigImg.alt = srcImg.alt || "";
    bigImg.setAttribute("class", "-lightbox-image");
    bigImg.draggable = false;
    overlay.appendChild(bigImg);
    const hintText = (window.MemoriaI18n && window.MemoriaI18n.t)
      ? window.MemoriaI18n.t("preview.lightboxHint")
      : "";
    if (hintText) {
      const hintEl = document.createElement("div");
      hintEl.className = "-lightbox-hint";
      hintEl.textContent = hintText;
      overlay.appendChild(hintEl);
    }
    document.body.appendChild(overlay);

    let scale = _lightboxInitialScale(bigImg), tx = 0, ty = 0;
    let dragging = false, moved = false, grabX = 0, grabY = 0;

    function apply() {
      bigImg.style.transform = "translate(" + tx + "px," + ty + "px) scale(" + scale + ")";
    }
    apply();

    function onWheel(ev) {
      ev.preventDefault();
      const rect = bigImg.getBoundingClientRect();
      const cx = ev.clientX - (rect.left + rect.width / 2);
      const cy = ev.clientY - (rect.top + rect.height / 2);
      const next = Math.min(12, Math.max(0.2, scale * (ev.deltaY < 0 ? 1.15 : 1 / 1.15)));
      const k = next / scale - 1;
      tx -= cx * k;
      ty -= cy * k;
      scale = next;
      moved = true;
      apply();
    }
    function onDown(ev) {
      if (ev.button !== 0) return;
      ev.preventDefault();
      dragging = true;
      moved = false;
      grabX = ev.clientX - tx;
      grabY = ev.clientY - ty;
      overlay.classList.add("-lightbox-dragging");
      if (bigImg.setPointerCapture) { try { bigImg.setPointerCapture(ev.pointerId); } catch (_) { /* 合成事件无活动指针 */ } }
    }
    function onMove(ev) {
      if (!dragging) return;
      tx = ev.clientX - grabX;
      ty = ev.clientY - grabY;
      moved = true;
      apply();
    }
    function onUp(ev) {
      if (!dragging) return;
      dragging = false;
      overlay.classList.remove("-lightbox-dragging");
      if (bigImg.releasePointerCapture) { try { bigImg.releasePointerCapture(ev.pointerId); } catch (_) { /* noop */ } }
    }
    function close() {
      window.removeEventListener("keydown", onKey, true);
      overlay.remove();
    }
    function onKey(ev) {
      if (ev.key === "Escape") { ev.preventDefault(); close(); }
    }

    overlay.addEventListener("wheel", onWheel, { passive: false });
    bigImg.addEventListener("pointerdown", onDown);
    bigImg.addEventListener("pointermove", onMove);
    bigImg.addEventListener("pointerup", onUp);
    bigImg.addEventListener("pointercancel", onUp);
    bigImg.addEventListener("dragstart", (ev) => ev.preventDefault());
    overlay.addEventListener("contextmenu", (ev) => { ev.preventDefault(); close(); });
    overlay.addEventListener("click", () => { if (!moved) close(); });
    window.addEventListener("keydown", onKey, true);
  }

  // ── Image Lightbox ──
  function attachImageLightbox(container) {
    container.querySelectorAll("img").forEach((img) => {
      if (img.closest(".-lightbox-overlay")) return;
      img.style.cursor = "zoom-in";
      // 2026-09-23 性能：原先这里有一条 `console.log`，内含 4 次 `getComputedStyle(img)`（每张图都会强制
      // 样式计算 + 布局）⇒ 实测 270 图的文档切一次文件刷出上千条日志、并明显拖慢渲染，已整体删除。
      // 同理删掉只做打印的 `error` / `load` 两条诊断监听；`dblclick` 放大逻辑保留（见下）。
      // 需要排查图片加载时用 DevTools 的 Network 面板，别再往热路径塞日志。
      // 双击放大（阶段 F 交互：单击进入图片编辑工具栏，双击 Lightbox 放大）
      img.addEventListener("dblclick", (e) => {
        // 双击放大时退出已进入的图片编辑模式（由 edit-handler 的 preview dblclick 处理，
        // 此处不 stopPropagation，让冒泡链继续）
        e.preventDefault();
        openLightbox(img);
      });
    });
  }

  // ── Local image path rewriting ──
  let _kbRootForImages = null;
  let _currentFileDir = ""; // relative dir of current file within KB (e.g. "subdir/" or "")
  function setKbRootForImages(root) { _kbRootForImages = root; }
  function setCurrentFileDir(dir) { _currentFileDir = dir; }
  function rewriteLocalImagePaths(html) {
    if (!_kbRootForImages) { return html; } // 2026-09-23 性能：原在此打一条 SKIP 日志；本函数**每张图调用一次** ⇒ 改成静默
    // 2026-09-23 性能：原在此打印 kbRoot/currentFileDir（每图一次），已删
    // Match any <img src="..."> and rewrite relative paths.
    return html.replace(
      /(<img\s[^>]*src=")([^"]+)"/g,
      (_, prefix, src) => {
        // Skip absolute URLs and data URIs
        if (/^(https?:|data:|\/)/i.test(src)) return prefix + src + '"';
        // Normalize: remove leading ./
        const clean = src.replace(/^\.\//, "");
        // `./` 开头 → 相对当前文件目录（旧语义，兼容 ./images/x.png）；
        // 其他相对路径（如 .memoria/images/x.png）→ 相对 KB 根（新约定）
        const relPath = src.startsWith("./") ? _currentFileDir + clean : clean;
        // Encode each path segment so / remains as separator.
        // marked 对 <...> 包裹的 URL 会先做一次编码（如 %E5%B1%8F），此处需先解码再
        // 编码，避免 % 被二次编码成 %25 导致静态服务器解码后仍找不到文件。
        const encodeSeg = (seg) => {
          let raw = seg;
          try {
            raw = decodeURIComponent(seg);
          } catch (e) {
            /* 孤立 % 等无法解码的情况：保留原段再编码 */
          }
          return encodeURIComponent(raw);
        };
        const encoded = relPath.replace(/\\/g, "/").split("/").map(encodeSeg).join("/");
        const apiBase = window.MemoriaBridge?.apiBase || "";
        const url = apiBase + "/files/" + encoded;
        // 2026-09-23 性能：原在此逐图 `console.log(src → url)`，已删（它是"每图一条"噪声的主要来源）
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
        return _t("preview.link.unresolved", { key, total });
      }
      if (routeTargets?.length) {
        if (resolvedList.length > 1) {
          return _t("preview.link.multi", { resolved: resolvedList.length, total });
        }
        if (resolvedList.length === 1) {
          return _t("preview.link.routed", { target: resolvedList[0] });
        }
      }
      if (resolved === true) {
        return _t("preview.link.jump", { key });
      }
      return _t("preview.link.title");
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
            ? `${safeId}<span class="-link-type">#${safeType}</span>`
            : safeId;
        const routeTargets = overrides?.[key];
        const resolved = isResolved(id);
        const routed = isRoutedTarget(key, routeTargets);
        let linkCls = "-link-pending";
        if (resolved === true) {
          linkCls = routed ? "-link-multi" : "-link-resolved";
        } else if (resolved === false) {
          linkCls = "-link-broken memoria-broken-link";
        }
        const title = linkTitle(key, routeTargets, resolved);
        const tabIndex = linkCls.includes("-link-broken") ? "-1" : "0";
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
      block.kind === "display-math" ? "-display-math -src-block" : "-src-block";
    const lineAttrs =
      `data--src-line="${block.startLine}" data--src-line-end="${block.endLine}"`;
    const singleRoot = /^<([a-zA-Z][a-zA-Z0-9]*)([^>]*)>[\s\S]*<\/\1>$/.test(html);
    const tagMatch = singleRoot ? html.match(/^<([a-zA-Z][a-zA-Z0-9]*)([^>]*)>/) : null;

    if (tagMatch) {
      const tag = tagMatch[1];
      let rest = tagMatch[2];
      if (/class=/.test(rest)) {
        rest = rest.replace(/class=(["'])([^"']*)\1/, (_, q, cls) =>
          cls.includes("-src-block") ? `class=${q}${cls}${q}` : `class=${q}${cls} ${extraClass}${q}`
        );
      } else {
        rest += ` class="${extraClass}"`;
      }
      if (!/data--src-line=/.test(rest)) {
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
   * Wraps each text segment in <span class="-seg" data-line="L" data-col="C">.
   *
   * Strategy: for each -src-block, align rendered DOM text nodes
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

    // For each -src-block element (or the root if single element)
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
      if (parent && parent.closest('mjx-container, pre, code, .-mermaid-container')) continue;
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
        span.className = "-seg";
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
        span.className = "-seg";
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
      report.mathErrors.push((el.textContent || "").trim().slice(0, 120) || _t("preview.math.texError"));
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
      report.messages.push(_t("preview.math.noRendered"));
    }
    if (report.mathErrors.length) {
      report.messages.push(_t("preview.math.texErrors", { n: report.mathErrors.length }));
    }
    if (report.rawDelimiters.length) {
      report.messages.push(_t("preview.math.rawDelims", { n: report.rawDelimiters.length }));
    }

    return report;
  }

  function renderHtml(body, options) {
    if (!window.marked) {
      return `<pre class="-preview-error">${_t("preview.markedMissing")}</pre>`;
    }
    const knownTargets = options?.knownTargets || null;
    const linkOverrides = options?.linkOverrides || null;
    const sidecarLinks = options?.sidecarLinks || null;
    const normalized = normalizeBody(body);
    return splitSourceBlocks(normalized)
      .map((block) => {
        if (block.kind === "blank") {
          // 空行占位 block：生成可选中、可定位的空行元素
          const lineAttr = `data--src-line="${block.startLine}" data--src-line-end="${block.endLine}"`;
          return `<div class="-src-block -blank-block" ${lineAttr}><br></div>`;
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
      messages: [_t("preview.math.notReady")],
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
    const preview = container.closest(".-preview") || container;
    if (!preview.classList.contains("-preview")) return;
    // 预览区域不设 contenteditable — 点击映射到源码编辑器
    // 光标由 CSS cursor: text 提供
  }

  // ── Mermaid 尺寸校正 + 放大交互（2026-10-03） ──
  // 根因：本机 Edge 对 <foreignObject> 的 getBBox() 会返回 2000×2000（真实内容仅约 82×303），
  // mermaid 用它算出的 viewBox 被夸大约 25 倍 ⇒ 图形被缩到 ~19%、13px 字缩成 ~2.5px 看不清。
  // 修法：块插入真实容器后，用 svg.getBBox()（此时贴合内容）重写 viewBox 与 max-width；
  // 插入时预览若不可见（getBBox 为 0），等容器首次拿到尺寸再补正一次。
  function _normalizeMermaidSvg(svg) {
    const pad = 2;
    const apply = () => {
      let b;
      try { b = svg.getBBox(); } catch (e) { return false; }
      if (!b || !(b.width > 0) || !(b.height > 0)) return false;
      svg.setAttribute("viewBox", (b.x - pad) + " " + (b.y - pad) + " " + (b.width + pad * 2) + " " + (b.height + pad * 2));
      svg.setAttribute("width", "100%");
      svg.style.maxWidth = Math.ceil(b.width + pad * 2) + "px";
      return true;
    };
    if (apply()) return;
    if (typeof ResizeObserver === "undefined") return;
    const host = svg.parentElement || svg;
    const ro = new ResizeObserver(() => { if (apply()) ro.disconnect(); });
    ro.observe(host);
  }

  // 双击 mermaid 图体内 → 复用图片 lightbox 放大（优先放大，不落入块编辑）
  // 2026-09-28：加**完整性检查** —— 图还没排好时不展示半成品（人：「当渲染不全的时候…你这样肯定不行」）。
  // mermaid 是拿到完整 svg 字符串后一次性插入的（不存在"节点只画一半"），
  // 这里挡的是两种真的会出现的半成品：① 插入时容器不可见/0 宽 ⇒ 尺寸为 0；② 子节点为空。
  // 命中就先等几帧（最多 ~10 帧 / 约 160ms）再取；仍不就绪则照常打开（没有更好的办法，且此时面板上它也看得见）。
  function _mermaidReady(svg) {
    try {
      if (!svg.querySelector("g")) return false;
      const r = svg.getBoundingClientRect();
      return r.width > 1 && r.height > 1;
    } catch (e) { return false; }
  }

  function _openWhenMermaidReady(svg, triesLeft) {
    if (_mermaidReady(svg) || !(triesLeft > 0)) { openLightbox(svg); return; }
    requestAnimationFrame(() => _openWhenMermaidReady(svg, triesLeft - 1));
  }

  function _attachMermaidZoom(svg) {
    const container = svg && svg.parentElement;
    if (!container || container.dataset.mermaidZoomBound === "1") return;
    container.dataset.mermaidZoomBound = "1";
    // 入口改成**图右上角的小按钮**（**绝不占用双击** —— 双击属于 edit-handler 的"进块编辑"）。
    // 点击 → 复用既有 lightbox（滚轮缩放 / 拖拽平移 / Esc / 点背景关闭）。
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "-mmd-zoom-btn";
    btn.setAttribute("contentEditable", "false");
    btn.setAttribute("title", _t("preview.mermaidZoom"));
    btn.setAttribute("aria-label", _t("preview.mermaidZoom"));
    btn.textContent = "\u2922";
    btn.addEventListener("pointerdown", (e) => e.stopPropagation());                       // 不触发图内平移
    btn.addEventListener("dblclick", (e) => { e.preventDefault(); e.stopPropagation(); }); // 双击按钮=两次单击，不进块编辑
    btn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); _openWhenMermaidReady(svg, 10); });
    container.appendChild(btn);
  }

  function _afterMermaidInsert(container) {
    const svg = container && container.querySelector("svg");
    if (!svg) return;
    // 2026-09-28 修正（人真机）：「**先把渲染做正常再说**，而且双击放大和双击进入 mermaid 的编辑模式
    // 是有**键位冲突**的，**先不管直接拖拽和放大，先渲染好**」
    // ⇒ **交互整层默认关**，本函数只负责渲染相关处理。
    //    关掉后：双击 mermaid 块 = 进块编辑改源码（**原有行为，不再被抢**）。
    //    要再评估时开启：控制台 localStorage["-mermaid-view-tools"]="1" 后刷新，或 URL 加 ?mmdview=1
    if (_mermaidNormalizeOn()) _normalizeMermaidSvg(svg);
    if (!_mermaidViewToolsOn()) return;
    _attachMermaidZoom(svg);
    _attachMermaidView(container, svg);
  }

  // 2026-09-28：交互层**默认关闭**（放大按钮 / 图内平移 / 把手）—— 主视图回 mermaid 原生；要开：
  //   localStorage["-mermaid-view-tools"]="1" 或 URL 加 ?mmdview=1。
  function _mermaidViewToolsOn() {
    try { if (localStorage.getItem("-mermaid-view-tools") === "0") return false; } catch (e) { /* 隐私模式 */ }
    try { if (/[?&]mmdview=0(?:&|$)/.test(location.search)) return false; } catch (e) { /* ignore */ }
    return true;   // 2026-10-05 默认开（类 Trae 预览：控制条 + Ctrl 滚轮缩放 + 拖拽平移；关：localStorage["-mermaid-view-tools"]="0" / URL ?mmdview=0）
  }

  function _mermaidNormalizeOn() {
    try { if (localStorage.getItem("-mermaid-normalize") === "0") return false; } catch (e) { /* 隐私模式 */ }
    try { if (/[?&]mmdnorm=0(?:&|$)/.test(location.search)) return false; } catch (e) { /* ignore */ } return true;   // 2026-10-05 语义改为**默认开**（安全网：只在 getBBox 明显超出 viewBox 时扩大、绝不缩小）；localStorage["-mermaid-normalize"]="0" 或 URL ?mmdnorm=0 可关
  }

  // lightbox：把「只吃 <img>」泛化为也能吃 <svg>（同一 overlay、同样的滚轮/拖拽/关闭手感）
  function _lightboxBigElement(srcEl) {
    const tag = (srcEl && srcEl.tagName || "").toLowerCase();
    if (tag !== "svg") {
      const img = document.createElement("img");
      img.src = srcEl.src;
      img.alt = srcEl.alt || "";
      img.className = "-lightbox-image";
      img.draggable = false;
      return img;
    }
    const clone = srcEl.cloneNode(true);
    clone.removeAttribute("style");
    const vb = (clone.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
    const r = srcEl.getBoundingClientRect();
    const w = (vb.length === 4 && vb[2] > 0) ? vb[2] : r.width;
    const h = (vb.length === 4 && vb[3] > 0) ? vb[3] : r.height;
    clone.setAttribute("width", String(w));
    clone.setAttribute("height", String(h));
    clone.setAttribute("preserveAspectRatio", "xMidYMid meet");
    clone.setAttribute("class", "-lightbox-image");
    return clone;
  }

  // svg 开箱时的初始缩放：放大到约占视口 90%（矢量，放大不糊）；img 维持既有 1:1
  function _lightboxInitialScale(el) {
    if (!el || (el.tagName || "").toLowerCase() !== "svg") return 1;
    const r = el.getBoundingClientRect();
    if (!(r.width > 0) || !(r.height > 0)) return 1;
    const fit = Math.min((window.innerWidth * 0.9) / r.width, (window.innerHeight * 0.9) / r.height);
    return Math.min(12, Math.max(0.2, fit));
  }

  // ── Mermaid 视图交互：图内平移(pan) + 右下把手**等比缩放**(zoom) + 把手双击复位（2026-10-04 语义修正）─
  // 视图模型：容器**永不裁切**（`-mmd-viewport` = overflow:auto 的可滚区，不是"画框"）
  //          └ `-mermaid-pan`（translate(panX,panY)）└ svg（无 zoom=自然尺寸；有 zoom=自然尺寸×zoom，等比）
  // 视图态落盘为围栏内首行指令 `%% memoria-view: zoom=<float> [pan=<x>,<y>]`（旧 `w=/h=` 兼容：忽略、不裁切）
  //（`renderMermaidBlocks` 交给 mermaid.render 之前用 `_parseMemoriaViewDirective` 剥掉该行；
  // 只在拖动结束且数值真变时经门面 `window.MemoriaApp.surface.setBlockSource` 写回 —— 可撤销、
  // 会重渲、跟文件走；把手双击 = 删指令行回到自然尺寸）。
  const _MV_RE = /^\s*%%\s*memoria-view:\s*(?:zoom=(?<z>\d*\.?\d+)(?:\s+pan=(?<npx>-?\d+)\s*,\s*(?<npy>-?\d+))?|w=(?<w>-?\d+)\s+h=(?<h>-?\d+)\s+pan=(?<opx>-?\d+)\s*,\s*(?<opy>-?\d+))\s*$/;   // 新 zoom(z|npx|npy) 与旧 w/h/pan(w|opx|opy) 都匹配

  /** 剥掉 `%% memoria-view` 指令行；返回 { code, found:{hasView,legacy,zoom,panX,panY}|null }（旧格式 ⇒ zoom:null）。 */
  function _parseMemoriaViewDirective(text) {
    const lines = String(text == null ? "" : text).split("\n");
    const out = [];
    let found = null;
    for (const ln of lines) {
      const m = _MV_RE.exec(ln);
      const g = (m && m.groups) ? m.groups : null;
      if (g && !found) { found = _mvFoundFromGroups(g); continue; }
      out.push(ln);
    }
    return { code: out.join("\n"), found };
  }

  function _formatMemoriaViewDirective(zoom, px, py) {
    return "%% memoria-view: zoom=" + (Math.round((Number(zoom) || 1) * 1000) / 1000) +
      (((px || py) ? (" pan=" + Math.round(px) + "," + Math.round(py)) : ""));
  }

  /** 在块源码围栏内首行插入/替换 `%% memoria-view` 指令行；dirLine=null ⇒ 删除该行。 */
  function _upsertMemoriaViewLine(text, dirLine) {
    const kept = String(text == null ? "" : text).split("\n").filter((ln) => !_MV_RE.test(ln));
    if (dirLine != null) kept.splice(1, 0, dirLine);
    return kept.join("\n");
  }

  function _mmdBlockIndex(el) {
    const bi = parseInt(el && el.getAttribute && el.getAttribute("data--block-index"), 10);
    return isFinite(bi) ? bi : null;
  }

  /**
   * 把视图态（尺寸/位移）落到 DOM。
   *  · 无视图态 ⇒ **完全恢复 mermaid 自然渲染**：svg 回到 `width="100%"` + mermaid 自己的
   *    `max-width`（= 该图自然宽）。这是"小图自然宽、不被拉伸 / 宽图贴合面板不越界"的关键：
   *    旧实现把 max-width 清成 "" ⇒ CSS `max-width:100%` 生效 ⇒ **小图被拉满面板**（实测 116→399px）。
   *  · 视图态 ⇒ 容器 = 画框（尺寸 w×h，CSS `max-width:100%` 保证不超出面板），
   *    svg 按**自然像素尺寸**绘制（viewBox 宽高）⇒ 超出画框由 overflow 裁掉，靠 pan 平移看。
   */
  function _applyMermaidView(container, svg, pan, st) {
    if (st.hasView) {
      container.classList.add("-mmd-viewport");
      container.style.width = Math.round(st.w) + "px";
      container.style.height = Math.round(st.h) + "px";
      svg.style.width = Math.round(st.fullW || st.w) + "px";
      svg.style.height = Math.round(st.fullH || st.h) + "px";
      svg.style.maxWidth = "none";
    } else {
      container.classList.remove("-mmd-viewport");
      container.style.width = "";
      container.style.height = "";
      svg.style.width = "";
      svg.style.height = "auto";
      svg.style.maxWidth = st.naturalMaxW || "";
    }
    pan.style.transform = (st.panX || st.panY)
      ? "translate(" + Math.round(st.panX) + "px," + Math.round(st.panY) + "px)" : "";
  }

  /**
   * 给一个已渲染的 mermaid 容器挂视图交互（幂等）：
   *  · 图体按住拖动（超过 4px 才算）⇒ 图内平移；
   *  · 右下把手拖动 ⇒ 改显示宽高；把手双击 ⇒ 复位自然尺寸（删指令行）；
   *  · 拖动结束后把尺寸/位移经门面写回文档（数值没变则不写）。
   * 只有该容器带 `data--block-index`（顶层块）才可写回；嵌套图只读。
   */
  function _attachMermaidView(container, svg) {
    if (!container || !svg || container.dataset.mermaidViewBound === "1") return;
    const bi = _mmdBlockIndex(container);
    const surface = (window.MemoriaApp && window.MemoriaApp.surface) || null;

    let pan = container.querySelector(".-mermaid-pan");
    if (!pan) { pan = document.createElement("div"); pan.className = "-mermaid-pan"; container.insertBefore(pan, svg); pan.appendChild(svg); }
    let handle = container.querySelector(".-mermaid-resize");
    if (!handle) {
      handle = document.createElement("div");
      handle.className = "-mermaid-resize";
      handle.setAttribute("contentEditable", "false");
      container.appendChild(handle);
    }
    container.dataset.mermaidViewBound = "1";

    const d = container._mmdDirective || null;
    const st = { fullW: 0, fullH: 0, naturalMaxW: "", w: d ? d.w : 0, h: d ? d.h : 0, panX: d ? d.panX : 0, panY: d ? d.panY : 0, hasView: !!d };
    container._mmdState = st;   // 调试/诊断用（探针读尺寸/位移）

    let inited = false;
    function init() {
      if (inited) return true;
      const r = svg.getBoundingClientRect();
      if (!(r.width > 1 && r.height > 1)) return false;   // 容器不可见/未排版 ⇒ 等下一拍
      const vb = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
      // 图的**自然像素尺寸**取自 viewBox（mermaid `useMaxWidth` 下 = 图自身的自然宽高）；
      // `naturalMaxW` = mermaid 写进 svg.style 的自然上限（无视图态恢复用，防小图被拉满）。
      st.fullW = (vb.length === 4 && vb[2] > 0) ? vb[2] : Math.round(r.width);
      st.fullH = (vb.length === 4 && vb[3] > 0) ? vb[3] : Math.round(r.height);
      st.naturalMaxW = svg.style.maxWidth || "";
      if (st.hasView) {
        if (!st.w) st.w = Math.round(Math.min(st.fullW, container.clientWidth || st.fullW));
        if (!st.h) st.h = Math.round(st.fullH);
      }
      _applyMermaidView(container, svg, pan, st);
      inited = true;
      return true;
    }
    if (!init() && typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(function () { if (init()) ro.disconnect(); });
      ro.observe(container);
    }

    function setFrozen(on) { if (on) container.dataset.mermaidInteracting = "1"; else delete container.dataset.mermaidInteracting; }
    function curW() { return st.hasView && st.w ? st.w : Math.round(Math.min(st.fullW || 0, container.clientWidth || st.fullW || 0)); }
    function curH() { return st.hasView && st.h ? st.h : Math.round(st.fullH || 0); }

    // ── 块级写回（只在数值真变时；经门面 → 撤销栈 + 重解析重渲）──
    function writeBack() {
      if (!surface || bi == null || !st.hasView) return;
      const cur = surface.getBlockSourceText(bi);
      if (cur == null) return;
      const line = _formatMemoriaViewDirective(curW(), curH(), st.panX, st.panY);
      const m = _MV_RE.exec(cur.split("\n")[1] || "");
      if (m && m[0].trim() === line) return;                  // 与指令行现值一致 ⇒ 不写
      const next = _upsertMemoriaViewLine(cur, line);
      if (next === cur) return;
      surface.setBlockSource(bi, next);
    }

    // ── 复位：删指令行 + 回到自然尺寸 ──
    function resetView() {
      st.hasView = false; st.panX = 0; st.panY = 0;
      _applyMermaidView(container, svg, pan, st);
      if (!surface || bi == null) return;
      const cur = surface.getBlockSourceText(bi);
      if (cur == null) return;
      const next = _upsertMemoriaViewLine(cur, null);
      if (next === cur) return;                               // 本来就没指令行 ⇒ 无需写盘
      surface.setBlockSource(bi, next);
    }

    // ── 图内平移（指针事件；>4px 才算拖动，否则当点击/双击）──
    // move/up 挂到 window（不靠 setPointerCapture：合成指针/跨元素拖动都能收到），结束时移除。
    const THRESHOLD = 4;
    let drag = null;
    function panMove(e) {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved) {
        if (dx * dx + dy * dy < THRESHOLD * THRESHOLD) return;   // 未过阈值 ⇒ 当点击/双击，不 pan
        drag.moved = true; setFrozen(true);
      }
      e.preventDefault();
      st.hasView = true;
      if (!st.w) st.w = curW();
      if (!st.h) st.h = curH();
      st.panX = drag.px0 + dx; st.panY = drag.py0 + dy;
      _applyMermaidView(container, svg, pan, st);
    }
    function panEnd(e) {
      if (!drag || e.pointerId !== drag.id) return;
      const moved = drag.moved; drag = null;
      window.removeEventListener("pointermove", panMove);
      window.removeEventListener("pointerup", panEnd);
      window.removeEventListener("pointercancel", panEnd);
      setFrozen(false);
      if (moved) { container._mmdDraggedAt = Date.now(); writeBack(); }   // 只有真拖过才写回
    }
    container.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      if (e.target && e.target.closest && e.target.closest(".-mermaid-resize")) return;   // 把手区不参与平移
      if (e.target && e.target.closest && e.target.closest(".-mmd-zoom-btn")) return;     // 放大按钮不参与平移
      if (!inited) init();
      // 图**没超出视口** ⇒ 拖动无效（不拦截点击/双击，让"进块编辑"等照常）。
      // "超出"按图的自然尺寸（viewBox）比视口内容盒判定。
      if (!(st.fullW > container.clientWidth + 1 || st.fullH > container.clientHeight + 1)) return;
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY, px0: st.panX, py0: st.panY, moved: false };
      window.addEventListener("pointermove", panMove);
      window.addEventListener("pointerup", panEnd);
      window.addEventListener("pointercancel", panEnd);
    });
    // 拖动后短暂窗口内屏蔽双击（避免"拖完立刻双击"被当作进 lightbox）
    container.addEventListener("dblclick", function (e) {
      if (container._mmdDraggedAt && (Date.now() - container._mmdDraggedAt) < 500) { e.preventDefault(); e.stopPropagation(); }
    }, true);

    // ── 右下把手：拖拽改宽高；双击复位 ──
    let rs = null;
    function rsMove(e) {
      if (!rs || e.pointerId !== rs.id) return;
      e.preventDefault();
      st.hasView = true;
      st.w = Math.max(40, Math.round(rs.w0 + (e.clientX - rs.x)));
      st.h = Math.max(40, Math.round(rs.h0 + (e.clientY - rs.y)));
      handle._mmdResized = true;
      _applyMermaidView(container, svg, pan, st);
    }
    function rsEnd(e) {
      if (!rs || e.pointerId !== rs.id) return;
      const changed = handle._mmdResized; rs = null;
      window.removeEventListener("pointermove", rsMove);
      window.removeEventListener("pointerup", rsEnd);
      window.removeEventListener("pointercancel", rsEnd);
      setFrozen(false);
      if (changed) { container._mmdDraggedAt = Date.now(); writeBack(); }
    }
    handle.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.stopPropagation();                                   // 不触发图体平移（也不进块编辑）
      if (!inited) init();
      rs = { id: e.pointerId, x: e.clientX, y: e.clientY, w0: curW(), h0: curH() };
      handle._mmdResized = false;
      setFrozen(true);
      window.addEventListener("pointermove", rsMove);
      window.addEventListener("pointerup", rsEnd);
      window.addEventListener("pointercancel", rsEnd);
    });
    handle.addEventListener("dblclick", function (e) { e.preventDefault(); e.stopPropagation(); resetView(); });
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

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-10-04 语义修正：mermaid「调整大小」= **等比整体缩放**，主视图**永不裁切**
  //   人（真机）：「你还是做成一个截图，导致越界的没有显示，我不要截图」
  //   ⇒ 旧"画框态"（`-mmd-viewport` 设 overflow:hidden + content-box + 固定 w×h）会把越界部分
  //     隐藏掉、只能靠拖拽找回来 —— 体验上等价"固定在框里的一张图"。本块把它改掉：
  //     · 容器**不再**设固定宽高、**不再** overflow:hidden（app.css 末尾覆盖 ⇒ overflow:auto）；
  //     · 无 zoom ⇒ mermaid 自然尺寸（小图自然宽居中、宽图 max-width:100% 适配面板，均不裁切）；
  //     · 有 zoom ⇒ svg 铺设 自然尺寸×zoom（等比）；宽/高超面板 ⇒ 容器滚动条保证**内容可达**；
  //     · 右下把手拖动改 **zoom**（等比，宽高比恒等于 viewBox 比），双击复位（删指令行）；
  //     · 旧指令 `%% memoria-view: w=… h=… pan=…` **兼容**：忽略 w/h（绝不裁切），仅取 pan。
  //   以下函数与文件上方旧实现**同名**（JS 函数声明后者覆盖前者）—— 刻意"文件尾追加"以满足
  //   「零行漂移」：既有 `markdown-preview.js:<行号>` 锚点一个不动。
  // ══════════════════════════════════════════════════════════════════════════════
  /** 由 `_MV_RE` 命名分组生成视图态：新格式取 zoom；旧格式 zoom=null（不裁切，仅取 pan）。 */
  function _mvFoundFromGroups(g) {
    return {
      hasView: true,
      legacy: g.w != null,
      zoom: (g.z != null) ? Number(g.z) : null,
      panX: (g.npx != null) ? Number(g.npx) : (g.opx != null ? Number(g.opx) : 0),
      panY: (g.npy != null) ? Number(g.npy) : (g.opy != null ? Number(g.opy) : 0),
    };
  }

  /** 等比缩放系数夹取：保证显示宽 ≥ 约 40px、上限 20×。 */
  function _mmdClampZoom(z, fullW) {
    const minZ = fullW > 0 ? Math.max(0.02, 40 / fullW) : 0.02;
    return Math.max(minZ, Math.min(20, Number(z) || 1));
  }

  /**
   * 把视图态落到 DOM（**永不裁切**）。
   *  · 无 zoom（含仅旧指令/仅 pan）⇒ 完全恢复 mermaid 自然渲染：svg width="100%" + 内联 `max-width`
   *    （= 该图自然宽）⇒ 小图自然宽居中、宽图贴合面板；容器不固定尺寸 ⇒ 不裁切。
   *  · 有 zoom ⇒ svg 显式 width=自然宽×zoom、height=自然高×zoom（等比）；`max-width:none` 允许超出面板，
   *    由容器 `overflow:auto` 出滚动条 ⇒ 越界内容**始终可达**。
   */
  function _applyMermaidView(container, svg, pan, st) {
    const zoomed = !!(st.hasView && st.zoom != null && st.zoom > 0);
    container.classList.toggle("-mmd-viewport", !!st.hasView);
    container.style.width = "";   // 不再固定"画框"尺寸（画框=裁切之源）
    container.style.height = "";
    if (zoomed) {
      svg.style.width = ((st.fullW || 0) * st.zoom) + "px";    // 用小数 px（不取整）⇒ 宽高比严格守恒
      svg.style.height = ((st.fullH || 0) * st.zoom) + "px";
      svg.style.maxWidth = "none";
    } else {
      svg.style.width = "";
      svg.style.height = "";
      svg.style.maxWidth = st.naturalMaxW || "";
    }
    pan.style.transform = (st.panX || st.panY)
      ? "translate(" + Math.round(st.panX) + "px," + Math.round(st.panY) + "px)" : "";
  }

  /**
   * 给一个已渲染的 mermaid 容器挂视图交互（幂等）：
   *  · 图体拖动（>4px，且**确实超出可视区**）⇒ 图内平移；否则不拦截（双击仍进块编辑）；
   *  · 右下把手拖动 ⇒ 改 **zoom**（等比例，指针到锚点距离比）；把手双击 ⇒ 复位自然尺寸（删指令行）；
   *  · 拖动结束且数值真变时经门面写回（可撤销、跟文件走）。仅 `data--block-index`（顶层块）可写回。
   */
  function _attachMermaidView(container, svg) {
    if (!container || !svg || container.dataset.mermaidViewBound === "1") return;
    const bi = _mmdBlockIndex(container);
    const surface = (window.MemoriaApp && window.MemoriaApp.surface) || null;

    let pan = container.querySelector(".-mermaid-pan");
    if (!pan) { pan = document.createElement("div"); pan.className = "-mermaid-pan"; container.insertBefore(pan, svg); pan.appendChild(svg); }
    let handle = container.querySelector(".-mermaid-resize");
    if (!handle) {
      handle = document.createElement("div");
      handle.className = "-mermaid-resize";
      handle.setAttribute("contentEditable", "false");
      container.appendChild(handle);
    }
    container.dataset.mermaidViewBound = "1";

    const d = container._mmdDirective || null;
    const st = {
      fullW: 0, fullH: 0, naturalMaxW: "",
      hasView: !!(d && d.hasView),
      zoom: (d && d.zoom != null) ? d.zoom : null,   // 旧格式(w/h) ⇒ null（不裁切，仅取 pan）
      panX: d ? (d.panX || 0) : 0,
      panY: d ? (d.panY || 0) : 0,
    };
    container._mmdState = st;   // 调试/诊断用（探针读尺寸/位移）

    let inited = false;
    function init() {
      if (inited) return true;
      const r = svg.getBoundingClientRect();
      if (!(r.width > 1 && r.height > 1)) return false;
      const vb = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
      st.fullW = (vb.length === 4 && vb[2] > 0) ? vb[2] : Math.round(r.width);
      st.fullH = (vb.length === 4 && vb[3] > 0) ? vb[3] : Math.round(r.height);
      st.naturalMaxW = svg.style.maxWidth || "";
      if (st.zoom != null) st.zoom = _mmdClampZoom(st.zoom, st.fullW);
      _applyMermaidView(container, svg, pan, st);
      inited = true;
      return true;
    }
    if (!init() && typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(function () { if (init()) ro.disconnect(); });
      ro.observe(container);
    }

    function setFrozen(on) { if (on) container.dataset.mermaidInteracting = "1"; else delete container.dataset.mermaidInteracting; }
    function dispW() { try { return svg.getBoundingClientRect().width; } catch (e) { return st.fullW; } }
    function dispH() { try { return svg.getBoundingClientRect().height; } catch (e) { return st.fullH; } }
    // 写回用 zoom：显式 zoom 优先；仅 pan/旧格式 ⇒ 用"当前显示宽 / 自然宽"固化成新格式
    function curZoom() { return (st.zoom != null) ? st.zoom : (st.fullW > 0 ? dispW() / st.fullW : 1); }

    function writeBack() {
      if (!surface || bi == null || !st.hasView) return;
      const cur = surface.getBlockSourceText(bi);
      if (cur == null) return;
      const line = _formatMemoriaViewDirective(curZoom(), st.panX, st.panY);
      const m = _MV_RE.exec(cur.split("\n")[1] || "");
      if (m && m[0].trim() === line) return;
      const next = _upsertMemoriaViewLine(cur, line);
      if (next === cur) return;
      surface.setBlockSource(bi, next);
    }

    function resetView() {
      st.hasView = false; st.zoom = null; st.panX = 0; st.panY = 0;
      _applyMermaidView(container, svg, pan, st);
      if (!surface || bi == null) return;
      const cur = surface.getBlockSourceText(bi);
      if (cur == null) return;
      const next = _upsertMemoriaViewLine(cur, null);
      if (next === cur) return;
      surface.setBlockSource(bi, next);
    }

    // ── 图内平移（仅在**确实超出可视区**时生效；>4px 才算拖动）──
    const THRESHOLD = 4;
    let drag = null;
    function panMove(e) {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved) {
        if (dx * dx + dy * dy < THRESHOLD * THRESHOLD) return;
        drag.moved = true; setFrozen(true);
      }
      e.preventDefault();
      st.hasView = true;
      st.panX = drag.px0 + dx; st.panY = drag.py0 + dy;
      _applyMermaidView(container, svg, pan, st);
    }
    function panEnd(e) {
      if (!drag || e.pointerId !== drag.id) return;
      const moved = drag.moved; drag = null;
      window.removeEventListener("pointermove", panMove);
      window.removeEventListener("pointerup", panEnd);
      window.removeEventListener("pointercancel", panEnd);
      setFrozen(false);
      if (moved) { container._mmdDraggedAt = Date.now(); writeBack(); }
    }
    container.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      if (e.target && e.target.closest && e.target.closest(".-mermaid-resize")) return;
      if (e.target && e.target.closest && e.target.closest(".-mmd-zoom-btn")) return;
      if (!inited) init();
      // 只有**当前显示尺寸确实超出可视区**才允许平移（缩放适配/自然尺寸下拖动无效 ⇒ 不拦截双击）
      if (!(dispW() > container.clientWidth + 1 || dispH() > container.clientHeight + 1)) return;
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY, px0: st.panX, py0: st.panY, moved: false };
      window.addEventListener("pointermove", panMove);
      window.addEventListener("pointerup", panEnd);
      window.addEventListener("pointercancel", panEnd);
    });
    container.addEventListener("dblclick", function (e) {
      if (container._mmdDraggedAt && (Date.now() - container._mmdDraggedAt) < 500) { e.preventDefault(); e.stopPropagation(); }
    }, true);

    // ── 右下把手：拖动 = **等比整体缩放**（指针到锚点距离比）；双击 = 复位回 mermaid 自然尺寸 ──
    let rs = null;
    function rsMove(e) {
      if (!rs || e.pointerId !== rs.id) return;
      e.preventDefault();
      const cur = Math.hypot(e.clientX - rs.ax, e.clientY - rs.ay);
      if (!(rs.dist0 > 0)) return;
      st.hasView = true;
      st.zoom = _mmdClampZoom(rs.z0 * (cur / rs.dist0), st.fullW);
      handle._mmdResized = true;
      _applyMermaidView(container, svg, pan, st);
    }
    function rsEnd(e) {
      if (!rs || e.pointerId !== rs.id) return;
      const changed = handle._mmdResized; rs = null;
      window.removeEventListener("pointermove", rsMove);
      window.removeEventListener("pointerup", rsEnd);
      window.removeEventListener("pointercancel", rsEnd);
      setFrozen(false);
      if (changed) { container._mmdDraggedAt = Date.now(); writeBack(); }
    }
    handle.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      e.stopPropagation();
      if (!inited) init();
      const pr = pan.getBoundingClientRect();
      rs = { id: e.pointerId, ax: pr.left, ay: pr.top, dist0: Math.hypot(e.clientX - pr.left, e.clientY - pr.top), z0: curZoom() };
      handle._mmdResized = false;
      setFrozen(true);
      window.addEventListener("pointermove", rsMove);
      window.addEventListener("pointerup", rsEnd);
      window.addEventListener("pointercancel", rsEnd);
    });
    handle.addEventListener("dblclick", function (e) { e.preventDefault(); e.stopPropagation(); resetView(); });
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-10-05 mermaid viewBox 裁切修复（真机确诊：viewBox 比实际内容小 ⇒ 溢出部分被裁）
  //   证据：同图 viewBox=595×667.5 而 getBBox=759×984（右溢约 220 / 下溢约 352）；
  //         容器 clientWidth==scrollWidth、面板/整页尺寸均正常 ⇒ 无撑破、无横滚 ⇒ 问题只在 viewBox 与内容不匹配。
  //   两条修法（都可单独关，便于对照）：
  //     ① 根因：`_mmdRenderWithFontSync` —— render 前等字体就绪（mermaid 用测量结果算 viewBox，
  //        字体未就绪时量到的是**回退字体**宽度 ⇒ viewBox 偏小 ⇒ 真字体渲染后文字变宽溢出）；
  //     ② 安全网：`_normalizeMermaidSvg`（覆盖文件上方同名旧实现）—— 排版稳定后，仅当 getBBox
  //        明显超出 viewBox 才**扩大**到恰好包住（+padding）；框内则不动（绝不缩小、绝不拉伸小图）。
  //   「文件尾追加」以满足「零行漂移」：既有 `markdown-preview.js:<行号>` 锚点一个不动。
  // ══════════════════════════════════════════════════════════════════════════════
  /** ① 根因修法：render 前 `await document.fonts.ready`（try/catch + 1.5s 超时，拿不到就继续渲染，绝不卡住）。
   *  理由：mermaid 用**测量结果**算 viewBox；若 render 当刻真实字体尚未应用/加载，量到的是**回退字体**的字号
   *  宽度 ⇒ viewBox 偏小 ⇒ 真字体渲染后文字变宽、内容溢出框外（实测 viewBox 595×667.5 vs getBBox 759×984，
   *  宽高比 1.276 与 1.475 不一致，符合"文字回流导致长宽**不同比例**增大"）。 */
  function _mmdRenderWithFontSync(id, src) {
    let on = true;   // 可单独关（对照用）：localStorage["-mermaid-font-sync"]="0" 或 URL ?mmdfont=0
    try { if (localStorage.getItem("-mermaid-font-sync") === "0") on = false; } catch (e) { /* 隐私模式 */ }
    try { if (/[?&]mmdfont=0(?:&|$)/.test(location.search)) on = false; } catch (e) { /* ignore */ }
    if (!on) return window.mermaid.render(id, src);   // 关掉时不加任何等待（零延迟）
    let ready = null;
    try { ready = (typeof document !== "undefined" && document.fonts && document.fonts.ready) ? document.fonts.ready : null; } catch (e) { ready = null; }
    const timeout = new Promise(function (r) { setTimeout(r, 1500); });
    const gate = ready ? Promise.race([ready, timeout]) : timeout;
    return gate.catch(function () { /* 字体就绪等待失败/超时 ⇒ 直接继续渲染，绝不卡住 */ }).then(function () { return window.mermaid.render(id, src); });
  }

  /** ② 安全网（覆盖文件上方同名旧实现）：**只扩大以容纳内容，绝不缩小**。
   *  旧实现在"插入当刻就量"且无条件重写 viewBox/max-width（会缩小、也会在未排版时误判）。
   *  新语义：
   *   · 排版稳定后再量（rAF×2；量到 b 为 0/NaN 说明未排版 ⇒ ResizeObserver/延时**有界重试**，几次后放弃）；
   *   · 仅当 getBBox() 明显超出 current viewBox（任一边溢出 > 1px）才把 viewBox **扩大**到包住 bbox（+2px padding）；
   *   · bbox 完全在 viewBox 内 ⇒ **什么都不做**（小图保持 mermaid 自然宽居中，绝不拉伸）；
   *   · 扩大时同步 `style.max-width` = 扩大后宽度（否则框变宽而显示宽度不变，仍会挤压）。
   *  开关：localStorage["-mermaid-normalize"]="0" 或 URL ?mmdnorm=0 可关（见 _mermaidNormalizeOn，默认开）。 */
  function _normalizeMermaidSvg(svg) {
    if (!svg || typeof svg.getBBox !== "function") return;
    const PAD = 2, MAX_TRIES = 8;
    let tries = 0;
    const attempt = function () {
      let b;
      try { b = svg.getBBox(); } catch (e) { return false; }
      if (!b || !(b.width > 0) || !(b.height > 0)) return false;   // 未排版/不可见 ⇒ 交还重试
      const vb = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
      if (vb.length !== 4 || !vb.every(function (n) { return isFinite(n); }) || !(vb[2] > 0) || !(vb[3] > 0)) return false;
      const right = vb[0] + vb[2], bottom = vb[1] + vb[3];
      const over = Math.max(vb[0] - b.x, vb[1] - b.y, (b.x + b.width) - right, (b.y + b.height) - bottom);
      if (!(over > 1)) return true;                                // 内容已在框内（含略小）⇒ 不动，绝不缩小
      const nx = Math.min(vb[0], b.x - PAD), ny = Math.min(vb[1], b.y - PAD);
      const nw = Math.max(right, b.x + b.width + PAD) - nx, nh = Math.max(bottom, b.y + b.height + PAD) - ny;
      svg.setAttribute("viewBox", nx + " " + ny + " " + nw + " " + nh);
      svg.style.maxWidth = Math.ceil(nw) + "px";                  // 同步显示上限 = 扩大后宽度
      return true;
    };
    const retry = function () {
      if (attempt()) return;
      if (++tries >= MAX_TRIES) return;                            // 有界：几次后放弃，绝不无限等
      if (typeof ResizeObserver !== "undefined") {
        const ro = new ResizeObserver(function () { if (attempt() || ++tries >= MAX_TRIES) ro.disconnect(); });
        ro.observe(svg.parentElement || svg);
        return;
      }
      setTimeout(function () { requestAnimationFrame(retry); }, 80);
    };
    requestAnimationFrame(function () { requestAnimationFrame(retry); });
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-10-05「类 Trae 预览」：mermaid 控制条（−/＋/百分比/适配/全屏）+ Ctrl 滚轮缩放 + 拖拽平移
  //   · **纯视图态**：不写文档、不产生指令行、刷新或重开文件即回默认；缩放/平移不触发任何重渲。
  //   · 缩放上下限 0.1×~8×、按钮与 Ctrl+滚轮步进 1.2×；到边界即止（不无限）。
  //   · 平移仅在**当前显示尺寸超出可视区**时启用（>4px 才算拖动）；未超出不拦截点击/双击。
  //   · 控制条 = 装饰层（`.-mmd-zoombar`，`contentEditable=false`），浮在图右上角、不进可编辑内容路径。
  //   · 覆盖文件上方同名 `_attachMermaidZoom` / `_attachMermaidView`（JS 函数声明后者覆盖前者）；
  //     文件尾追加 ⇒ 既有 `markdown-preview.js:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 旧实现（右上角单个放大按钮）已被下方控制条取代；保留同签名空实现以兼容 `_afterMermaidInsert` 调用点。 */
  function _attachMermaidZoom() { /* noop: 控制条并入下方 _attachMermaidView */ }

  /**
   * 给一个已渲染的 mermaid 容器挂「控制条 + 缩放 + 平移」（幂等）：控制条在容器右上角；
   * `−`/`＋` 与 Ctrl+滚轮改缩放（0.1×~8×）；仅显示尺寸超出可视区时按住拖动平移（>4px）；
   * `适配` 复位到初始态（mermaid 自然尺寸 / 适配面板宽）；`⤢` 复用 lightbox 全屏。
   * **不写文档**：全部为视图态，刷新/重开即回默认。
   */
  function _attachMermaidView(container, svg) {
    if (!container || !svg || container.dataset.mermaidViewBound === "1") return;
    container.dataset.mermaidViewBound = "1";

    let pan = container.querySelector(".-mermaid-pan");
    if (!pan) { pan = document.createElement("div"); pan.className = "-mermaid-pan"; container.insertBefore(pan, svg); pan.appendChild(svg); }

    // ── 控制条（装饰层）──
    let bar = container.querySelector(".-mmd-zoombar");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "-mmd-zoombar";
      bar.setAttribute("contentEditable", "false");
      bar.setAttribute("data--decoration", "mermaid-view");
      bar.addEventListener("pointerdown", (e) => e.stopPropagation());
      bar.addEventListener("dblclick", (e) => { e.preventDefault(); e.stopPropagation(); });
      container.appendChild(bar);
    }
    const mkBtn = (text, key) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "-mmd-zoom-btn";
      b.setAttribute("contentEditable", "false");
      b.setAttribute("title", _t(key));
      b.setAttribute("aria-label", _t(key));
      b.textContent = text;
      b.addEventListener("pointerdown", (e) => e.stopPropagation());
      b.addEventListener("dblclick", (e) => { e.preventDefault(); e.stopPropagation(); });
      return b;
    };
    let pct = bar.querySelector(".-mmd-zoom-pct");
    if (!pct) {
      const btnOut = mkBtn("\u2212", "preview.mermaidZoomOut");
      const btnIn = mkBtn("\uFF0B", "preview.mermaidZoomIn");
      pct = document.createElement("span");
      pct.className = "-mmd-zoom-pct";
      pct.setAttribute("contentEditable", "false");
      const btnFit = mkBtn(_t("preview.mermaidFit"), "preview.mermaidFit");
      const btnFull = mkBtn("\u2922", "preview.mermaidFullscreen");
      bar.append(btnOut, btnIn, pct, btnFit, btnFull);
      btnOut.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); zoomBy(1 / STEP); });
      btnIn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); zoomBy(STEP); });
      btnFit.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); fit(); });
      btnFull.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); _openWhenMermaidReady(svg, 10); });
    }

    const MINZ = 0.1, MAXZ = 8, STEP = 1.2, THRESHOLD = 4;
    const st = { fullW: 0, fullH: 0, naturalMaxW: "", zoom: null, panX: 0, panY: 0 };   // zoom=null ⇒ 初始态（自然尺寸 / 适配面板宽）
    container._mmdState = st;   // 调试/诊断用（探针读尺寸/位移/缩放）

    let inited = false;
    const fitScale = () => { const cw = container.clientWidth || 0; return (st.fullW > 0 && cw > 0) ? Math.min(1, cw / st.fullW) : 1; };
    const effZoom = () => (st.zoom != null ? st.zoom : fitScale());

    /** 重新读「自然尺寸/自然 max-width」。用于：init 及**首次进入缩放**前 —— 因为 `_normalizeMermaidSvg`
     *  可能在我们 init 之后（rAF×2）才把 viewBox/max-width 扩大；不刷新的话 `zoom=1` 会比初始态还小。 */
    function refreshNatural() {
      const vb = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
      if (vb.length === 4 && vb[2] > 0) st.fullW = vb[2];
      if (vb.length === 4 && vb[3] > 0) st.fullH = vb[3];
      st.naturalMaxW = svg.style.maxWidth || "";
    }

    function apply() {
      const z = effZoom();
      container.classList.add("-mmd-viewport");
      if (st.zoom != null) {
        svg.style.width = (st.fullW * z) + "px";
        svg.style.height = (st.fullH * z) + "px";
        svg.style.maxWidth = "none";
      } else {
        svg.style.width = "";   // 恢复 mermaid 自然渲染（宽 100% + 自然 max-width）⇒ 不裁、不拉伸
        svg.style.height = "";
        svg.style.maxWidth = st.naturalMaxW || "";
      }
      pan.style.transform = (st.panX || st.panY) ? "translate(" + Math.round(st.panX) + "px," + Math.round(st.panY) + "px)" : "";
      const p = Math.round(z * 100);
      if (pct) { pct.textContent = p + "%"; pct.setAttribute("aria-label", _t("preview.mermaidZoomLevel", { p: p })); }
    }

    function init() {
      if (inited) return true;
      const r = svg.getBoundingClientRect();
      if (!(r.width > 1 && r.height > 1)) return false;   // 容器不可见/未排版 ⇒ 等下一拍
      refreshNatural();
      if (!(st.fullW > 0)) st.fullW = Math.round(r.width);
      if (!(st.fullH > 0)) st.fullH = Math.round(r.height);
      apply();
      inited = true;
      return true;
    }
    if (!init() && typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(function () { if (init()) ro.disconnect(); });
      ro.observe(container);
    }

    function setFrozen(on) { if (on) container.dataset.mermaidInteracting = "1"; else delete container.dataset.mermaidInteracting; }
    function dispW() { try { return svg.getBoundingClientRect().width; } catch (e) { return st.fullW; } }
    function dispH() { try { return svg.getBoundingClientRect().height; } catch (e) { return st.fullH; } }
    const overflow = () => dispW() > container.clientWidth + 1 || dispH() > container.clientHeight + 1;

    /** 设定绝对缩放（夹到 0.1×~8×）；从初始态首次进入缩放时**先刷新**自然尺寸/max-width。 */
    function setZoom(z) {
      if (!init() || !(st.fullW > 0)) return;
      if (st.zoom == null) refreshNatural();
      st.zoom = Math.max(MINZ, Math.min(MAXZ, z));
      apply();
    }
    function zoomBy(k) { if (st.zoom == null) refreshNatural(); setZoom(effZoom() * k); }
    function fit() { st.zoom = null; st.panX = 0; st.panY = 0; apply(); }

    // ── Ctrl+滚轮：只处理 Ctrl（**普通滚轮不拦截** ⇒ 交还页面/容器滚动）──
    container.addEventListener("wheel", function (e) {
      if (!e.ctrlKey) return;
      if (!init() || !(st.fullW > 0)) return;
      if (st.zoom == null) refreshNatural();
      const z1 = effZoom();
      const z2 = Math.max(MINZ, Math.min(MAXZ, z1 * (e.deltaY < 0 ? STEP : 1 / STEP)));
      e.preventDefault();
      if (z2 === z1) return;   // 到边界 ⇒ 停住，不无限
      // 光标锚定：让光标下的内容点缩放前后不动（容器滚动坐标）
      const cr = container.getBoundingClientRect();
      const cx = container.scrollLeft + (e.clientX - cr.left), cy = container.scrollTop + (e.clientY - cr.top);
      const natX = (cx - (st.panX || 0)) / z1, natY = (cy - (st.panY || 0)) / z1;
      st.panX = cx - natX * z2; st.panY = cy - natY * z2;
      st.zoom = z2;
      apply();
    }, { passive: false });

    // ── 拖拽平移：仅当**显示尺寸确实超出可视区**时启用；>4px 才算拖动 ──
    let drag = null;
    function panMove(e) {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved) {
        if (dx * dx + dy * dy < THRESHOLD * THRESHOLD) return;   // 未过阈值 ⇒ 当点击/双击，不 pan
        drag.moved = true; setFrozen(true);
        try { if (container.setPointerCapture) container.setPointerCapture(e.pointerId); } catch (_) { /* 合成事件无活动指针 */ }
      }
      e.preventDefault();
      st.panX = drag.px0 + dx; st.panY = drag.py0 + dy;
      apply();
    }
    function panEnd(e) {
      if (!drag || e.pointerId !== drag.id) return;
      const moved = drag.moved; drag = null;
      try { if (container.releasePointerCapture) container.releasePointerCapture(e.pointerId); } catch (_) { /* noop */ }
      setFrozen(false);
      if (moved) container._mmdDraggedAt = Date.now();   // 拖动后短窗口内屏蔽双击（**不写文档**）
    }
    container.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      if (e.target && e.target.closest && e.target.closest(".-mmd-zoombar")) return;   // 控制条不参与平移
      if (!init()) return;
      if (!overflow()) return;   // 未超出 ⇒ 不 pan、不拦截点击/双击（**双击仍进块编辑**）
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY, px0: st.panX, py0: st.panY, moved: false };
    });
    container.addEventListener("pointermove", panMove);
    container.addEventListener("pointerup", panEnd);
    container.addEventListener("pointercancel", panEnd);
    // 拖动后短暂窗口内屏蔽双击（避免"拖完立刻双击"被当作进块编辑/放大）
    container.addEventListener("dblclick", function (e) {
      if (container._mmdDraggedAt && (Date.now() - container._mmdDraggedAt) < 500) { e.preventDefault(); e.stopPropagation(); }
    }, true);
  }
})();
