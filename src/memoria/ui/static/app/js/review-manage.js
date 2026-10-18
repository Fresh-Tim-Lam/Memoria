/**
 * 复习卡管理页（2026-10-12）：替代顶栏「复习」旧模态的主入口。
 * 看**所有**复习卡（含未到期、含答案，管理场景不做隔离）+ 增删改/禁用 + 批量复习入口。
 * 数据全走已有 UI RPC（review_cards_list / review_cards_upsert / review_card_delete / review_card_disable），
 * 不新增事实源。DOM 全由本模块自建 ⇒ index.html 只多一行 script。
 * 复用既有 `.-modal` 骨架（overlay=.-modal + .-modal-backdrop + .-modal-box + .-modal-header/body/footer）；
 * 开关 = append/remove DOM（同 review-modal.js）。零依赖：只用 window.MemoriaApp + window.MemoriaReviewModal。
 */
(function (global) {
  "use strict";

  const A = () => global.MemoriaApp || {};
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));
  function call(method, ...args) {
    const app = A();
    if (!app.call) return Promise.resolve({ status: "error", code: "no_bridge", message: "桥不可用" });
    return Promise.resolve(app.call(method, ...args));
  }
  function kbPath() {
    const st = A().state;
    return (st && st.kbPath) || "";
  }
  function flash(err) {
    const app = A();
    if (app.showFlashError) app.showFlashError(String(err || ""));
  }

  const TYPES = ["basic", "cloze", "reverse", "mcq", "gapfill", "short", "produce"];
  const TYPE_ZH = { basic: "基础", cloze: "挖空", reverse: "反向", mcq: "选择", gapfill: "填空", short: "简答", produce: "开放" };

  const S = { open: false, cards: [], q: "", type: "", editing: null };
  let mainEl = null;
  let formEl = null;
  const PAGE = 25; // 增量渲染：首屏 25 张，滚到底再补下一批

  function typeOptions() {
    return TYPES.map((t) => '<option value="' + t + '">' + (TYPE_ZH[t] || t) + "（" + t + "）</option>").join("");
  }

  // ── 主面板 ──────────────────────────────────────────────────────────────────
  function buildMain() {
    if (mainEl) return mainEl;
    const overlay = document.createElement("div");
    overlay.id = "-review-manage-modal";
    overlay.className = "-modal -review-manage-modal";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML =
      '<div class="-modal-backdrop"></div>' +
      '<div class="-modal-box -review-manage-box">' +
        '<div class="-modal-header">' +
          '<span class="-review-manage-title">复习卡管理</span>' +
          '<div class="-review-manage-headops">' +
            '<button type="button" class="-btn" id="-rm-review">批量复习</button>' +
            '<button type="button" class="-btn primary" id="-rm-new">新建卡</button>' +
            '<button type="button" class="-icon-btn" id="-rm-close" title="关闭" aria-label="关闭">×</button>' +
          "</div>" +
        "</div>" +
        '<div class="-review-manage-toolbar">' +
          '<input type="search" id="-rm-q" placeholder="搜索 card_id / 卡面…">' +
          '<select id="-rm-type"><option value="">全部类型</option>' + typeOptions() + "</select>" +
          '<span class="-rm-count" id="-rm-count"></span>' +
        "</div>" +
        '<div class="-modal-body -review-manage-list" id="-rm-list"></div>' +
      "</div>";
    mainEl = overlay;
    overlay.querySelector(".-modal-backdrop").addEventListener("click", close);
    overlay.querySelector("#-rm-close").addEventListener("click", close);
    overlay.querySelector("#-rm-new").addEventListener("click", () => openForm(null));
    overlay.querySelector("#-rm-review").addEventListener("click", reviewDue);
    overlay.querySelector("#-rm-q").addEventListener("input", (e) => { S.q = e.target.value.trim().toLowerCase(); renderList(); });
    overlay.querySelector("#-rm-type").addEventListener("change", (e) => { S.type = e.target.value; renderList(); });
    const listEl = overlay.querySelector("#-rm-list");
    bindListEvents(listEl);
    listEl.addEventListener("scroll", function () {
      if (listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - 40) appendPage(); // 滚近底部补下一页
    });
    return overlay;
  }

  async function load() {
    const kb = kbPath();
    if (!kb) { flash("请先打开知识库"); return; }
    const res = await call("review_cards_list", kb);
    if (res.status !== "ok") { flash(res.message || "加载失败"); return; }
    S.cards = Array.isArray(res.cards) ? res.cards : [];
    renderList();
  }

  let _filtered = [];   // 当前筛选后的卡片（增量渲染用）
  let _shown = 0;       // 已渲染到第几张

  function renderList() {
    const el = document.getElementById("-rm-list");
    const count = document.getElementById("-rm-count");
    if (!el) return;
    const list = S.cards.filter((c) => {
      if (S.type && c.type !== S.type) return false;
      if (S.q) {
        const hay = ((c.card_id || "") + " " + (c.front || "") + " " + (c.back || "")).toLowerCase();
        if (hay.indexOf(S.q) < 0) return false;
      }
      return true;
    });
    if (count) count.textContent = "共 " + S.cards.length + " 张" + (list.length !== S.cards.length ? "，筛选出 " + list.length : "");
    _filtered = list;
    _shown = 0;
    if (!list.length) {
      el.innerHTML = '<div class="-review-manage-empty">没有复习卡' + (S.cards.length ? "（筛选无结果）" : "，点右上「新建卡」创建") + "</div>";
      return;
    }
    el.innerHTML = "";
    appendPage(); // 只渲染第一页，剩余滚动懒加载
    // 首屏若没填满可视区（没有滚动条），继续补到滚动出现（避免"看起来没满但实际还有"，且仍远快于一次 95 张）
    while (_shown < _filtered.length && el.scrollHeight <= el.clientHeight + 4 && _shown < PAGE * 4) appendPage();
  }

  function appendPage() {
    const el = document.getElementById("-rm-list");
    if (!el) return;
    const next = _filtered.slice(_shown, _shown + PAGE);
    if (!next.length) return;
    _shown += next.length;
    const frag = document.createDocumentFragment();
    next.forEach((c) => { const row = document.createElement("div"); row.innerHTML = cardRow(c); frag.appendChild(row.firstChild); });
    el.appendChild(frag);
  }

  function bindListEvents(el) {
    if (!el._rmBound) {
      el._rmBound = true;
      el.addEventListener("click", (ev) => {
        const t = ev.target && ev.target.closest ? ev.target.closest("[data-rm-enter],[data-rm-edit],[data-rm-del],[data-rm-toggle]") : null;
        if (!t) return;
        if (t.hasAttribute("data-rm-enter")) enter(t.getAttribute("data-rm-enter"));
        else if (t.hasAttribute("data-rm-edit")) openForm(t.getAttribute("data-rm-edit"));
        else if (t.hasAttribute("data-rm-del")) del(t.getAttribute("data-rm-del"));
        else if (t.hasAttribute("data-rm-toggle")) toggle(t.getAttribute("data-rm-toggle"), t.getAttribute("data-rm-dis") === "1");
      });
    }
  }

  function cardRow(c) {
    const type = esc(c.type || "");
    const dis = !!c.disabled;
    const front = esc(String(c.front || "").slice(0, 120));
    return (
      '<div class="-review-manage-card' + (dis ? " -review-manage-card--disabled" : "") + '">' +
        '<div class="-rm-main">' +
          '<div class="-rm-top"><span class="-rm-cid" title="' + esc(c.card_id) + '">' + esc(c.card_id) + "</span>" +
          '<span class="-rm-type -rm-type--' + type + '">' + (TYPE_ZH[type] || type) + "</span>" +
          (dis ? '<span class="-rm-badge-dis">已禁用</span>' : "") +
          "</div>" +
          '<div class="-rm-front">' + front + "</div>" +
        "</div>" +
        '<div class="-rm-ops">' +
          '<button type="button" class="-btn" data-rm-enter="' + esc(c.card_id) + '">进入</button>' +
          '<button type="button" class="-btn" data-rm-edit="' + esc(c.card_id) + '">编辑</button>' +
          '<button type="button" class="-btn" data-rm-toggle="' + esc(c.card_id) + '" data-rm-dis="' + (dis ? "0" : "1") + '">' + (dis ? "启用" : "禁用") + "</button>" +
          '<button type="button" class="-btn -btn--danger" data-rm-del="' + esc(c.card_id) + '">删除</button>' +
        "</div>" +
      "</div>"
    );
  }

  // ── 增/改 表单 ──────────────────────────────────────────────────────────────
  function buildForm() {
    if (formEl) return formEl;
    const overlay = document.createElement("div");
    overlay.id = "-rm-form";
    overlay.className = "-modal -review-manage-form-modal";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML =
      '<div class="-modal-backdrop"></div>' +
      '<div class="-modal-box -review-manage-form">' +
        '<div class="-modal-header">' +
          '<span class="-review-manage-title" id="-rmf-title">新建卡</span>' +
          '<button type="button" class="-icon-btn" id="-rmf-close" title="关闭" aria-label="关闭">×</button>' +
        "</div>" +
        '<div class="-modal-body">' +
          '<label class="-rm-field">card_id<input type="text" id="-rmf-id" placeholder="唯一 id，如 vocab-001"></label>' +
          '<label class="-rm-field">类型<select id="-rmf-type">' + typeOptions() + "</select></label>" +
          '<label class="-rm-field">正面（front）<textarea id="-rmf-front" rows="3"></textarea></label>' +
          '<label class="-rm-field">背面（back）<textarea id="-rmf-back" rows="3"></textarea></label>' +
          '<label class="-rm-field">来源（source，可选）<input type="text" id="-rmf-source"></label>' +
          '<div class="-rm-form-hint">选择题/填空题的 options/answer 等扩展字段在编辑时原样保留；如需精调可用 agent 工具 review_cards_upsert。</div>' +
        "</div>" +
        '<div class="-modal-footer -btn-bar">' +
          '<button type="button" class="-btn primary" id="-rmf-save">保存</button>' +
          '<button type="button" class="-btn" id="-rmf-cancel">取消</button>' +
        "</div>" +
      "</div>";
    formEl = overlay;
    overlay.querySelector(".-modal-backdrop").addEventListener("click", closeForm);
    overlay.querySelector("#-rmf-close").addEventListener("click", closeForm);
    overlay.querySelector("#-rmf-cancel").addEventListener("click", closeForm);
    overlay.querySelector("#-rmf-save").addEventListener("click", saveForm);
    return overlay;
  }

  function openForm(cid) {
    const card = cid ? S.cards.find((c) => c.card_id === cid) : null;
    S.editing = cid || null;
    const f = buildForm();
    f.querySelector("#-rmf-title").textContent = card ? "编辑卡 " + cid : "新建卡";
    f.querySelector("#-rmf-id").value = card ? card.card_id : "";
    f.querySelector("#-rmf-id").disabled = !!card;
    f.querySelector("#-rmf-type").value = card ? (card.type || "basic") : "basic";
    f.querySelector("#-rmf-front").value = card ? (card.front || "") : "";
    f.querySelector("#-rmf-back").value = card ? (card.back || "") : "";
    f.querySelector("#-rmf-source").value = card ? (card.source || "") : "";
    document.body.appendChild(f);
    f.querySelector("#-rmf-id").focus();
  }

  function closeForm() {
    S.editing = null;
    if (formEl) { formEl.remove(); formEl = null; }
  }

  async function saveForm() {
    const f = buildForm();
    const isEdit = S.editing != null;
    const orig = isEdit ? S.cards.find((c) => c.card_id === S.editing) : null;
    const row = {
      card_id: f.querySelector("#-rmf-id").value.trim(),
      type: f.querySelector("#-rmf-type").value,
      front: f.querySelector("#-rmf-front").value,
      back: f.querySelector("#-rmf-back").value,
      source: f.querySelector("#-rmf-source").value.trim(),
    };
    if (!row.card_id) { flash("card_id 不能为空"); return; }
    if (!row.front) { flash("正面 front 不能为空"); return; }
    if (orig) {
      for (const k of ["options", "answer", "accept", "extra", "hint"]) {
        if (orig[k] !== undefined) row[k] = orig[k];
      }
    }
    const res = await call("review_cards_upsert", [row], kbPath());
    if (res.status !== "ok") { flash(res.message || "保存失败"); return; }
    closeForm();
    await load();
  }

  // ── 删 / 禁用 / 批量复习 ─────────────────────────────────────────────────────
  async function del(cid) {
    if (!global.confirm("删除卡片「" + cid + "」？卡定义会被移除（学习进度保留）。")) return;
    const res = await call("review_card_delete", cid, kbPath());
    if (res.status !== "ok") { flash(res.message || "删除失败"); return; }
    await load();
  }

  async function toggle(cid, dis) {
    const res = await call("review_card_disable", cid, dis, kbPath());
    if (res.status !== "ok") { flash(res.message || "操作失败"); return; }
    await load();
  }

  function reviewDue() {
    close();
    const rm = global.MemoriaReviewModal;
    if (rm && typeof rm.open === "function") rm.open();
  }

  // ── 开/关 ────────────────────────────────────────────────────────────────────
  function open() {
    if (S.open) return;
    S.open = true;
    document.body.appendChild(buildMain());
    document.body.classList.add("-review-manage-open");
    S.q = ""; S.type = "";
    const q = document.getElementById("-rm-q"); if (q) q.value = "";
    const t = document.getElementById("-rm-type"); if (t) t.value = "";
    load();
  }

  function close() {
    if (!S.open) return;
    S.open = false;
    document.body.classList.remove("-review-manage-open");
    if (mainEl) { mainEl.remove(); mainEl = null; }
    closeForm();
  }

  /** 「进入」：关管理页 + 呼出这张卡到悬浮卡复习。 */
  function enter(cid) {
    close();
    const s = global.MemoriaReviewSummon;
    if (s && typeof s.summon === "function") {
      try { s.summon(String(cid || "")); } catch (e) { /* 静默 */ }
    } else if (global.MemoriaReviewModal && typeof global.MemoriaReviewModal.open === "function") {
      // 兜底：无悬浮卡模块时退回模态面板（不传入具体卡，仅开面板）
      try { global.MemoriaReviewModal.open(); } catch (e) { /* 静默 */ }
    }
  }

  global.MemoriaReviewManage = { open, close };
})(window);
