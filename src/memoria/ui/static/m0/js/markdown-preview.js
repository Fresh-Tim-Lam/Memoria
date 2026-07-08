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
    return b?.tex ?? "";
  }

  function stashInline(allBlocks, tex) {
    allBlocks.push({ kind: "inline", tex });
    const idx = allBlocks.length - 1;
    return `${INLINE_START}MI${idx}${INLINE_END}`;
  }

  function protectMath(text) {
    const allBlocks = [];
    let out = protectDisplayBlocks(text, allBlocks);

    out = out.replace(/\\begin\{([a-zA-Z*]+)\*?\}[\s\S]+?\\end\{\1\*?\}/g, (m) =>
      stashBlock(allBlocks, m)
    );
    out = out.replace(/\\\[([\s\S]+?)\\\]/g, (m) => stashBlock(allBlocks, m));
    out = out.replace(/\\\(([\s\S]+?)\\\)/g, (m) => stashInline(allBlocks, m));
    out = out.replace(/\$(?:\\.|[^\$\n\\])+\$/g, (m) => stashInline(allBlocks, m));

    return { text: out, blocks: allBlocks };
  }

  function toInlineDelimiters(tex) {
    const t = tex.trim();
    if (t.startsWith("\\(") && t.endsWith("\\)")) return t;
    if (t.startsWith("$") && t.endsWith("$") && !t.startsWith("$$")) {
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
    return attachLineAttrs(block.markdown, block);
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

  function renderMarkdownBlock(block, knownTargets, linkOverrides, sidecarLinks) {
    let markdown = injectSidecarPlainLinks(block.markdown, sidecarLinks);
    const { text, blocks } = protectMath(markdown);
    let html = marked.parse(text, { gfm: true, breaks: true });
    html = restoreMath(html, blocks);
    html = postProcessMemoriaLinks(
      html,
      knownTargets,
      linkOverrides,
      block.startLine,
      markdown
    );
    return attachLineAttrs(html, block);
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
    container.dataset.previewOk = report.ok ? "1" : "0";
    return report;
  }

  return {
    renderHtml,
    renderToElement,
    initMathJax,
    normalizeBody,
    diagnose,
    countExpectedMathBlocks,
  };
})();
