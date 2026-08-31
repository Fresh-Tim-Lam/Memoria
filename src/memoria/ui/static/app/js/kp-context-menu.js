/**
 * 侧栏知识点项右键菜单
 */
window.MemoriaKpContextMenu = (function () {
  "use strict";

  const MENU_ID = "-kp-context-menu";

  function hide() {
    document.getElementById(MENU_ID)?.remove();
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

  function show(kpId, x, y) {
    const actions = window.MemoriaKpActions;
    if (!actions || !kpId) return;
    hide();

    const menu = document.createElement("div");
    menu.id = MENU_ID;
    menu.className = "-context-menu";
    menu.setAttribute("role", "menu");

    const items = [{ label: "配置", action: () => actions.configure(kpId) }];

    items.forEach((it) => {
      if (it.divider) {
        const div = document.createElement("div");
        div.className = "-ctx-divider";
        menu.appendChild(div);
        return;
      }
      const row = document.createElement("button");
      row.type = "button";
      row.className = "-ctx-item";
      row.setAttribute("role", "menuitem");
      row.textContent = it.label;
      row.addEventListener("click", (e) => {
        e.stopPropagation();
        hide();
        it.action();
      });
      menu.appendChild(row);
    });

    document.body.appendChild(menu);
    placeMenu(menu, x, y);
  }

  document.addEventListener("click", hide);
  document.addEventListener("contextmenu", (e) => {
    if (!e.target.closest(`#${MENU_ID}`)) hide();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });

  return { show, hide };
})();
