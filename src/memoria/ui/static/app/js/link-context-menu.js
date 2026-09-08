/**
 * 预览区链接 / 选中文本右键菜单（瘦菜单 → 统一链接编辑器）
 */
window.MemoriaLinkContextMenu = (function () {
  "use strict";

  const MENU_ID = "-link-context-menu";

  function hide() {
    document.getElementById(MENU_ID)?.remove();
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function L(key, params) {
    return window.MemoriaI18n && window.MemoriaI18n.t
      ? window.MemoriaI18n.t(key, params)
      : key;
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
    menu.className = "-context-menu";
    menu.setAttribute("role", "menu");

    items.forEach((it) => {
      if (it.divider) {
        const div = document.createElement("div");
        div.className = "-ctx-divider";
        menu.appendChild(div);
        return;
      }
      const row = document.createElement("button");
      row.type = "button";
      row.className =
        "-ctx-item" +
        (it.disabled ? " disabled" : "") +
        (it.danger ? " danger" : "");
      row.setAttribute("role", "menuitem");
      if (it.hint) row.title = it.hint;
      row.innerHTML = it.label;
      if (!it.disabled) {
        row.addEventListener("click", (e) => {
          e.stopPropagation();
          // keepMenu 项（如"展开颜色下拉"）不关闭当前菜单，方便用户反悔点其它项
          if (!it.keepMenu) hide();
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
      const snippet = t.slice(0, 48) + (t.length > 48 ? "…" : "");
      onStatus?.(L("menu.copyDone", { text: snippet }));
    } catch (_) {
      onStatus?.(L("menu.copyFailed"));
    }
  }

  function linkStatusLabel(isBroken, isMulti) {
    if (isBroken) return L("menu.linkUnbound");
    if (isMulti) return L("menu.linkMulti");
    return L("menu.linkResolved");
  }

  function showForLink(e, linkEl, ctx) {
    e.preventDefault();
    e.stopPropagation();

    const targetId = ctx.targetId || linkEl.dataset.linkTarget || "";
    const displayText = ctx.displayText || linkEl.textContent?.trim() || targetId;
    const isBroken = ctx.isBroken ?? linkEl.classList.contains("-link-broken");
    const isMulti =
      ctx.isMulti ??
      (linkEl.classList.contains("-link-multi") ||
        (linkEl.dataset.linkTargets && linkEl.dataset.linkTargets.length > 2));

    const items = [
      {
        label: `<span class="-ctx-head">${esc(displayText)}</span>`,
        disabled: true,
        action: () => {},
      },
      {
        label: `<span class="-ctx-meta">${esc(linkStatusLabel(isBroken, isMulti))} · ${esc(targetId)}</span>`,
        disabled: true,
        action: () => {},
      },
      { divider: true },
      {
        label: L("menu.linkEdit"),
        action: () => ctx.onEditLink?.({ linkEl, targetId, displayText }),
      },
      {
        label: L("menu.copyTargetKey"),
        action: () => copyText(targetId, ctx.onStatus),
      },
    ];

    if (displayText && displayText !== targetId) {
      items.push({
        label: L("menu.copyDisplayText"),
        action: () => copyText(displayText, ctx.onStatus),
      });
    }

    items.push({ divider: true });
    items.push({
      label: L("menu.linkDetach"),
      danger: true,
      hint: L("menu.linkDetachHint"),
      action: () =>
        ctx.onDetachLink?.({
          targetId,
          displayText,
          linkType: ctx.linkType || linkEl.dataset.linkType || "",
          line: ctx.linkLine || Number(linkEl.dataset.linkLine) || 0,
        }),
    });
    items.push({
      label: L("menu.linkRemoveRoute"),
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
        label: `<span class="-ctx-head">${esc(sel.slice(0, 40))}${sel.length > 40 ? "…" : ""}</span>`,
        disabled: true,
        action: () => {},
      },
      { divider: true },
      {
        label: L("menu.copy"),
        hint: L("menu.copyHint"),
        action: () => copyText(sel, ctx.onStatus),
      },
    ];

    if (ctx.onApplyStyle) {
      const mx = e.clientX;
      const my = e.clientY;
      items.push(
        { divider: true },
        { label: L("menu.bold"), action: () => ctx.onApplyStyle("bold") },
        { label: L("menu.italic"), action: () => ctx.onApplyStyle("italic") },
        {
          label: L("menu.highlight"),
          keepMenu: true,
          action: () =>
            ctx.onPickStyle
              ? ctx.onPickStyle("highlight", mx, my)
              : ctx.onApplyStyle("highlight", "yellow"),
        },
        {
          label: L("menu.fontColor"),
          keepMenu: true,
          action: () =>
            ctx.onPickStyle
              ? ctx.onPickStyle("fontcolor", mx, my)
              : ctx.onApplyStyle("fontcolor", "red"),
        },
      );
    }

    items.push(
      { divider: true },
      {
        label: L("menu.createLink"),
        action: () => ctx.onCreateLink?.({ text: sel }),
      },
      {
        label: L("menu.makeKp"),
        action: () => ctx.onCreateKp?.({ text: sel, lines: ctx.lines }),
      },
    );

    if (ctx.markdown) {
      items.push({
        label: L("menu.copyMarkdown"),
        hint: L("menu.copyMarkdownHint"),
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
        label: `<span class="-ctx-head">${esc(L("menu.cursorPos"))}</span>`,
        disabled: true,
        action: () => {},
      },
      { divider: true },
      {
        label: L("menu.paste"),
        hint: L("menu.pasteHint"),
        action: () => ctx.onPaste?.(),
      },
    ];

    if (ctx.onInsertImage) {
      items.push({ divider: true });
      items.push({
        label: L("menu.insertImage"),
        hint: L("menu.insertImageHint"),
        action: () => ctx.onInsertImage(),
      });
    }

    buildMenu(items, e.clientX, e.clientY);
  }

  document.addEventListener("click", hide);
  document.addEventListener("scroll", hide, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });

  return { showForLink, showForSelection, showForCursor, hide };
})();
