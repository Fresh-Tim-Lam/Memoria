/**
 * 预览区链接 / 选中文本右键菜单（瘦菜单 → 统一链接编辑器）
 */
window.MemoriaLinkContextMenu = (function () {
  "use strict";

  const MENU_ID = "m0-link-context-menu";

  function hide() {
    document.getElementById(MENU_ID)?.remove();
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function placeMenu(menu, x, y) {
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    const rect = menu.getBoundingClientRect();
    let nx = x;
    let ny = y;
    if (nx + rect.width > window.innerWidth) nx = window.innerWidth - rect.width - 4;
    if (ny + rect.height > window.innerHeight) ny = window.innerHeight - rect.height - 4;
    menu.style.left = `${Math.max(4, nx)}px`;
    menu.style.top = `${Math.max(4, ny)}px`;
  }

  function buildMenu(items, x, y) {
    hide();
    const menu = document.createElement("div");
    menu.id = MENU_ID;
    menu.className = "m0-context-menu";
    menu.setAttribute("role", "menu");

    items.forEach((it) => {
      if (it.divider) {
        const div = document.createElement("div");
        div.className = "m0-ctx-divider";
        menu.appendChild(div);
        return;
      }
      const row = document.createElement("button");
      row.type = "button";
      row.className =
        "m0-ctx-item" +
        (it.disabled ? " disabled" : "") +
        (it.danger ? " danger" : "");
      row.setAttribute("role", "menuitem");
      if (it.hint) row.title = it.hint;
      row.innerHTML = it.label;
      if (!it.disabled) {
        row.addEventListener("click", (e) => {
          e.stopPropagation();
          hide();
          it.action();
        });
      }
      menu.appendChild(row);
    });

    document.body.appendChild(menu);
    placeMenu(menu, x, y);
  }

  async function copyText(text, onStatus) {
    const t = (text || "").trim();
    if (!t) return;
    try {
      await navigator.clipboard.writeText(t);
      onStatus?.(`已复制：${t.slice(0, 48)}${t.length > 48 ? "…" : ""}`);
    } catch (_) {
      onStatus?.("复制失败");
    }
  }

  function linkStatusLabel(isBroken, isMulti) {
    if (isBroken) return "未绑定目标";
    if (isMulti) return "多目标链接";
    return "已解析";
  }

  function showForLink(e, linkEl, ctx) {
    e.preventDefault();
    e.stopPropagation();

    const targetId = ctx.targetId || linkEl.dataset.linkTarget || "";
    const displayText = ctx.displayText || linkEl.textContent?.trim() || targetId;
    const isBroken = ctx.isBroken ?? linkEl.classList.contains("m0-link-broken");
    const isMulti =
      ctx.isMulti ??
      (linkEl.classList.contains("m0-link-multi") ||
        (linkEl.dataset.linkTargets && linkEl.dataset.linkTargets.length > 2));

    const items = [
      {
        label: `<span class="m0-ctx-head">${esc(displayText)}</span>`,
        disabled: true,
        action: () => {},
      },
      {
        label: `<span class="m0-ctx-meta">${esc(linkStatusLabel(isBroken, isMulti))} · ${esc(targetId)}</span>`,
        disabled: true,
        action: () => {},
      },
      { divider: true },
      {
        label: "编辑链接…",
        action: () => ctx.onEditLink?.({ linkEl, targetId, displayText }),
      },
      {
        label: "复制目标键",
        action: () => copyText(targetId, ctx.onStatus),
      },
    ];

    if (displayText && displayText !== targetId) {
      items.push({
        label: "复制显示文字",
        action: () => copyText(displayText, ctx.onStatus),
      });
    }

    items.push({ divider: true });
    items.push({
      label: "从跳转入口移除此处",
      danger: true,
      hint: "仅解除本处 [[…]]，保留链接配置",
      action: () =>
        ctx.onDetachLink?.({
          targetId,
          displayText,
          linkType: ctx.linkType || linkEl.dataset.linkType || "",
          line: ctx.linkLine || Number(linkEl.dataset.linkLine) || 0,
        }),
    });
    items.push({
      label: "移除 [[]] 并删除路由",
      danger: true,
      action: () =>
        ctx.onRemoveLink?.({
          targetId,
          displayText,
          linkType: ctx.linkType || linkEl.dataset.linkType || "",
        }),
    });

    buildMenu(items, e.clientX, e.clientY);
  }

  function showForSelection(e, text, ctx) {
    e.preventDefault();
    e.stopPropagation();
    const sel = (text || "").trim();
    if (!sel) return;

    const items = [
      {
        label: `<span class="m0-ctx-head">${esc(sel.slice(0, 40))}${sel.length > 40 ? "…" : ""}</span>`,
        disabled: true,
        action: () => {},
      },
      { divider: true },
      {
        label: "复制",
        hint: "复制选中文本",
        action: () => copyText(sel, ctx.onStatus),
      },
    ];

    if (ctx.onApplyStyle) {
      items.push(
        { divider: true },
        { label: "加粗", action: () => ctx.onApplyStyle("bold") },
        { label: "斜体", action: () => ctx.onApplyStyle("italic") },
        { label: "高亮", action: () => ctx.onApplyStyle("highlight", "yellow") },
        { label: "字体颜色", action: () => ctx.onApplyStyle("fontcolor", "red") },
      );
    }

    items.push(
      { divider: true },
      {
        label: "创建链接…",
        action: () => ctx.onCreateLink?.({ text: sel }),
      },
      {
        label: "设为知识点…",
        action: () => ctx.onCreateKp?.({ text: sel, lines: ctx.lines }),
      },
    );

    if (ctx.markdown) {
      items.push({
        label: "复制 Markdown",
        hint: "复制选中片段对应的源码",
        action: () => copyText(ctx.markdown, ctx.onStatus),
      });
    }

    buildMenu(items, e.clientX, e.clientY);
  }

  function showForCursor(e, ctx) {
    e.preventDefault();
    e.stopPropagation();

    const items = [
      {
        label: `<span class="m0-ctx-head">光标位置</span>`,
        disabled: true,
        action: () => {},
      },
      { divider: true },
      {
        label: "粘贴",
        hint: "将剪贴板内容插入到光标位置",
        action: () => ctx.onPaste?.(),
      },
    ];

    buildMenu(items, e.clientX, e.clientY);
  }

  document.addEventListener("click", hide);
  document.addEventListener("scroll", hide, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });

  return { showForLink, showForSelection, showForCursor, hide };
})();
