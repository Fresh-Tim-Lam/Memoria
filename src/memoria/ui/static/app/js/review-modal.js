/**
 * R3a：复习界面（模态弹窗）。设计见 `docs/design/preview-render-refactor.md` 附 R3a / R3a-2。
 *
 * **它做什么**：点顶栏「复习」按钮（或 `Ctrl/Cmd+Shift+R`）弹出模态，一次 `review_due_start` 取今日
 * 全量到期 → 本地成队列逐张翻面评分；每评分调一次 `review_grade_one`（**人驱动 · 免审批**）。
 *
 * **关键纪律**（逐条对应 R3a 附节）：
 *  - **不做乐观更新**：只有 RPC 返回 `status:"ok"` 才把该卡计为「已评」并前移进度；未成功即显示「未评」。
 *  - **失败分类**（R3a-2.2）：`unreviewable`（卡不存在/被禁）⇒ 跳过记下**不重试**；`temporary`（写不进/
 *    解释器不可用/结果不明）⇒ **队尾重试一次**（评分幂等）；最终仍未评 ⇒ 退出时**汇总列出**并提示
 *    「未评的明天照样到期」。`unavailable`/`load_failed` ⇒ 明确提示，绝不静默失败。
 *  - **只经 UI RPC 写评分**：绝不直写 `cards.json` / `progress.json`。
 *  - **冲突规避照抄全仓范式**：输入控件聚焦 / IME 组字中一律不碰；`Esc` 走**捕获阶段**；模态打开即挂
 *    全局监听、关闭即卸。
 *
 * **零依赖、零侵入**：只用应用门面 `window.MemoriaApp`（`call` / `T` / `esc` / `state` /
 * `showFlashError`），正文复用 `window.MemoriaMarkdownPreview`（含公式）；模态骨架复用既有 `.-modal`
 * 一族。DOM 全由本模块自建 ⇒ `index.html` 只多一行 script（`#btn-review` 为**同行追加**，不新增行）。
 */
(function (global) {
  "use strict";

  const A = () => global.MemoriaApp || {};
  const T = (k, p) => (A().T ? A().T(k, p) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));

  const MODAL_ID = "-review-modal";
  const CLOZE_RE = /\{\{c(\d+)::([\s\S]*?)\}\}/g; // 与后端 `_review_cloze_re` 同源口径

  //: 本地复习态（每次 open 重置）。
  const S = {
    open: false,
    busy: false,
    card: null,
    item: null,
    queue: [],
    pos: 0,
    total: 0,
    done: 0,
    unreviewed: [],
    flipped: false,
    retried: null,
    date: "",
  };

  function call(method, ...args) {
    const app = A();
    if (!app.call) return Promise.resolve({ status: "error", code: "apiUnavailable", message: "桥不可用" });
    return Promise.resolve(app.call(method, ...args));
  }

  function kbPath() {
    const st = A().state;
    return (st && st.kbPath) || "";
  }

  const $ = (sel) => document.querySelector(sel);

  // ── 卡面渲染 ────────────────────────────────────────────────────────────────

  // cloze 挖空占位：**不往 markdown 里塞 HTML**（`class="…"` 里的 `=`/`-` 会被
  // `MemoriaMathNormalize.isLegacyFormulaLine` 判成"旧式公式"而包成 $$ 数学块）；
  // 改用**私有区哨兵**占位，渲染完成后再在 DOM 里换成真元素（见 `expandClozeTokens`）。
  const TK_OPEN = "\uE010";
  const TK_CLOSE = "\uE011";
  const TK_RE = new RegExp(TK_OPEN + "(\\d+)" + TK_CLOSE, "g");

  /** 把 `{{cN::…}}` 换成哨兵；`items[i] = {reveal, text}` 供渲染后展开。 */
  function fillCloze(text, reveal, items) {
    return String(text == null ? "" : text).replace(CLOZE_RE, function (_m, _n, ans) {
      const idx = items.push({ reveal: !!reveal, text: ans }) - 1;
      return TK_OPEN + idx + TK_CLOSE;
    });
  }

  /** 渲染后把哨兵文本节点切成真元素（挖空占位框 / 填回答案）。 */
  function expandClozeTokens(root, items) {
    if (!items.length) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function (node) {
      const text = node.nodeValue || "";
      TK_RE.lastIndex = 0;
      if (!TK_RE.test(text)) return;
      TK_RE.lastIndex = 0;
      const frag = document.createDocumentFragment();
      let last = 0;
      let m;
      while ((m = TK_RE.exec(text))) {
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        const it = items[Number(m[1])];
        const el = document.createElement("span");
        if (it && it.reveal) {
          el.className = "-review-cloze-ans";
          el.textContent = it.text;
        } else {
          el.className = "-review-blank";
          el.setAttribute("aria-label", T("review.blankAria"));
        }
        frag.appendChild(el);
        last = m.index + m[0].length;
      }
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  /** 渲染失败时的纯文本回退：哨兵换成"____"/答案。 */
  function stripTokens(text, items) {
    return String(text).replace(TK_RE, function (_m, i) {
      const it = items[Number(i)];
      return it && it.reveal ? it.text : "____";
    });
  }

  /** 当前面/背面的 markdown 源（不处理挖空；`cloze=true` 时由 `paintFace` 走哨兵管线）。 */
  function faceSource(card, reveal) {
    const type = String((card && card.type) || "basic");
    const front = String((card && card.front) || "");
    const back = String((card && card.back) || "");
    if (type === "cloze") {
      const hasMark = /\{\{c\d+::/.test(front);
      return { cloze: hasMark, text: hasMark ? front : (reveal ? back : front) };
    }
    if (type === "reverse") return { cloze: false, text: reveal ? front : back };
    return { cloze: false, text: reveal ? back : front };
  }

  /** 把 markdown 渲染进元素（复用既有管线：公式 / 高亮 / 链接 / 代码）。缺件时退回纯文本。 */
  async function paintFace(el, card, reveal) {
    const s = faceSource(card, reveal);
    const items = [];
    const src = s.cloze ? fillCloze(s.text, reveal, items) : s.text;
    const pv = global.MemoriaMarkdownPreview;
    if (pv && typeof pv.renderToElement === "function") {
      try {
        await pv.renderToElement(el, src, { legacyMath: false });
        if (s.cloze) expandClozeTokens(el, items);
        return;
      } catch (_e) {
        /* 退回纯文本 */
      }
    }
    el.textContent = s.cloze ? stripTokens(src, items) : src;
  }

  // ── 模态 DOM ────────────────────────────────────────────────────────────────

  function buildModal() {
    const overlay = document.createElement("div");
    overlay.id = MODAL_ID;
    overlay.className = "-modal -review-modal";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML =
      '<div class="-modal-backdrop"></div>' +
      '<div class="-modal-box -review-box" tabindex="-1">' +
      '<div class="-modal-header">' +
      '<span class="-review-head-title" data-i18n="review.title"></span>' +
      '<span class="-review-progress" id="-review-progress"></span>' +
      '<button type="button" class="-icon-btn" id="-review-close" title="关闭" data-i18n-attr="title:dialog.closeTitle">×</button>' +
      "</div>" +
      '<div class="-modal-body -review-body" id="-review-body"></div>' +
      '<div class="-modal-footer -review-footer -btn-bar" id="-review-footer"></div>' +
      "</div>";
    document.body.appendChild(overlay);
    overlay.querySelector(".-modal-backdrop").addEventListener("click", close);
    $("#-review-close").addEventListener("click", close);
    if (global.MemoriaI18n && global.MemoriaI18n.applyStatic) global.MemoriaI18n.applyStatic(overlay);
  }

  function focusBox() {
    const box = document.querySelector("#" + MODAL_ID + " .-modal-box");
    if (!box) return;
    setTimeout(function () {
      try {
        box.focus({ preventScroll: true });
      } catch (_e) {
        try { box.focus(); } catch (_e2) { /* noop */ }
      }
    }, 30);
  }

  function paintProgress() {
    const el = $("#-review-progress");
    if (!el) return;
    if (!S.total) {
      el.textContent = "";
      return;
    }
    el.textContent = T("review.progress", { total: S.total, done: S.done });
  }

  function renderGradeBar(enabled) {
    const f = $("#-review-footer");
    if (!f) return;
    const rows = [
      [1, "review.grade.again"],
      [2, "review.grade.hard"],
      [3, "review.grade.good"],
      [4, "review.grade.easy"],
    ];
    f.innerHTML = "";
    const bar = document.createElement("div");
    bar.className = "-review-grade-bar";
    rows.forEach(function (row) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "-review-grade-btn";
      btn.setAttribute("data-grade", String(row[0]));
      btn.innerHTML = '<span class="-review-kbd">' + row[0] + "</span><span>" + esc(T(row[1])) + "</span>";
      btn.disabled = !enabled;
      btn.addEventListener("click", function () {
        grade(row[0]);
      });
      bar.appendChild(btn);
    });
    f.appendChild(bar);
  }

  function renderCloseFooter() {
    const f = $("#-review-footer");
    if (!f) return;
    f.innerHTML =
      '<span class="-modal-footer-spacer"></span>' +
      '<button type="button" class="-btn primary" id="-review-done">' + esc(T("common.close")) + "</button>";
    const btn = $("#-review-done");
    if (btn) btn.addEventListener("click", close);
  }

  function setBusy(on) {
    S.busy = !!on;
    const f = $("#-review-footer");
    if (!f) return;
    const btns = f.querySelectorAll(".-review-grade-btn");
    for (let i = 0; i < btns.length; i += 1) btns[i].disabled = !(!on && S.flipped);
  }

  // ── 视图切换 ────────────────────────────────────────────────────────────────

  async function showCard() {
    const body = $("#-review-body");
    if (!body) return;
    S.flipped = false;
    S.item = S.queue[S.pos] || null;
    S.card = S.item ? S.item.card : null;
    if (!S.card) {
      finish();
      return;
    }
    // 重试项（队尾重排的"暂时性失败"卡）：直接按**已选的分**再试一次，**不要求再翻面**
    // （评分幂等 ⇒ 安全；不做乐观更新，仍以返回为准）。
    const retryGrade = S.item.autoGrade;
    paintProgress();
    body.innerHTML =
      '<div class="-review-face" id="-review-face"></div>' +
      '<div class="-review-hint">' + esc(T("review.flipHint")) + "</div>";
    renderGradeBar(retryGrade != null);
    S.flipped = retryGrade != null;
    await paintFace($("#-review-face"), S.card, S.flipped);
    focusBox();
    if (retryGrade != null) grade(retryGrade);
  }

  async function flip() {
    if (!S.card || S.busy || S.flipped) return;
    S.flipped = true;
    const face = $("#-review-face");
    if (face) await paintFace(face, S.card, true);
    renderGradeBar(true);
    focusBox();
  }

  function dedupe(list) {
    const seen = Object.create(null);
    const out = [];
    list.forEach(function (id) {
      if (!seen[id]) {
        seen[id] = true;
        out.push(id);
      }
    });
    return out;
  }

  function finish() {
    paintProgress();
    const body = $("#-review-body");
    if (!body) return;
    const left = Math.max(0, S.total - S.done);
    const msg = left <= 0 ? T("review.doneAll") : T("review.donePartial", { done: S.done, left: left });
    let html = '<div class="-review-summary">' + esc(msg) + "</div>";
    const list = dedupe(S.unreviewed);
    if (list.length) {
      html += '<div class="-review-unreviewed-title">' + esc(T("review.unreviewedTitle", { n: list.length })) + "</div>";
      html +=
        '<ul class="-review-list">' +
        list.map(function (id) { return "<li>" + esc(id) + "</li>"; }).join("") +
        "</ul>";
    }
    body.innerHTML = html;
    renderCloseFooter();
    focusBox();
  }

  function showEmpty() {
    paintProgress();
    const body = $("#-review-body");
    if (!body) return;
    body.innerHTML = '<div class="-review-empty">' + esc(T("review.empty")) + "</div>";
    renderCloseFooter();
    focusBox();
  }

  function showError(res) {
    paintProgress();
    const body = $("#-review-body");
    if (!body) return;
    let msg;
    if (res && res.code === "apiUnavailable") {
      msg = T("review.unavailable");
    } else {
      msg = T("review.loadFailed", { msg: (res && (res.message || res.code)) || "" });
    }
    body.innerHTML = '<div class="-review-error">' + esc(msg) + "</div>";
    renderCloseFooter();
    focusBox();
  }

  function toast(message, detail) {
    const app = A();
    if (app.showFlashError) app.showFlashError(message, detail || "");
  }

  // ── 评分 ────────────────────────────────────────────────────────────────────

  async function grade(g) {
    if (!S.card || S.busy) return;
    const card = S.card;
    S.busy = true;
    setBusy(true);
    let res;
    try {
      res = await call("review_grade_one", card.card_id, g, null, kbPath());
    } catch (e) {
      res = { status: "error", category: "unavailable", message: String((e && e.message) || e) };
    }
    S.busy = false;
    setBusy(false);
    if (res && res.status === "ok") {
      // **不做乐观更新**：以返回为准，成功才 +1 并前移进度。
      S.done += 1;
      advance();
      return;
    }
    const cat = (res && res.category) || "temporary";
    if (cat === "unavailable") {
      showError(res);
      return;
    }
    if (cat === "unreviewable") {
      // 卡不存在 / 被禁：跳过、记下、不重试。
      S.unreviewed.push(card.card_id);
      toast(T("review.gradeFailed", { card: card.card_id }), (res && res.message) || "");
      advance();
      return;
    }
    // temporary / 未知：队尾重试一次（评分幂等，安全）。重排时带上**本次选的分**，
    // 到达队尾时自动再试一次（不再要求翻面）。
    if (!S.retried[card.card_id]) {
      S.retried[card.card_id] = true;
      S.queue.push({ card: card, autoGrade: g }); // 队尾
      toast(T("review.retry", { card: card.card_id }), (res && res.message) || "");
      advance();
      return;
    }
    S.unreviewed.push(card.card_id);
    toast(T("review.gradeFailed", { card: card.card_id }), (res && res.message) || "");
    advance();
  }

  function advance() {
    S.pos += 1;
    if (S.pos >= S.queue.length) {
      finish();
      return;
    }
    showCard();
  }

  // ── 键盘（冲突规避照抄全仓范式）──────────────────────────────────────────────

  function inEditable() {
    const ae = document.activeElement;
    if (!ae) return false;
    if (ae.isContentEditable) return true;
    return /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName || "");
  }

  function onKeyDown(e) {
    if (!S.open) return;
    if (e.isComposing || e.keyCode === 229) return; // IME 组字中：一行都不碰
    if (inEditable()) return; // 输入控件聚焦：交还各自处理
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
      return;
    }
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      flip();
      return;
    }
    if (e.key === "1" || e.key === "2" || e.key === "3" || e.key === "4") {
      e.preventDefault();
      if (S.flipped) grade(Number(e.key));
    }
  }

  function onShortcut(e) {
    if (S.open) return;
    if (!(e.ctrlKey || e.metaKey) || !e.shiftKey) return;
    if (e.isComposing || e.keyCode === 229) return;
    if (String(e.key || "").toLowerCase() !== "r") return;
    if (inEditable()) return;
    e.preventDefault();
    open();
  }

  // ── 打开 / 关闭 ──────────────────────────────────────────────────────────────

  async function open() {
    if (S.open) return;
    S.open = true;
    S.busy = true;
    S.card = null;
    S.item = null;
    S.queue = [];
    S.pos = 0;
    S.total = 0;
    S.done = 0;
    S.unreviewed = [];
    S.flipped = false;
    S.retried = Object.create(null);
    buildModal();
    document.body.classList.add("-review-modal-open");
    window.addEventListener("keydown", onKeyDown, true); // 捕获阶段（Esc 同范式）
    focusBox();

    let res;
    try {
      res = await call("review_due_start", null, kbPath());
    } catch (e) {
      res = { status: "error", code: "apiUnavailable", message: String((e && e.message) || e) };
    }
    S.busy = false;
    if (!S.open) return; // 加载期间用户已关闭
    if (!res || res.status !== "ok") {
      showError(res);
      return;
    }
    const cards = Array.isArray(res.cards) ? res.cards : [];
    S.date = String(res.date || "");
    S.total = Number(res.count != null ? res.count : cards.length) || 0;
    cards.forEach(function (c) {
      if (!c || !c.card_id) return;
      if (c.missing_in_cards || !(c.type || c.front)) {
        S.unreviewed.push(String(c.card_id)); // 无卡面可渲染：记下、不重试
        return;
      }
      S.queue.push({ card: c, autoGrade: null });
    });
    if (S.total <= 0) {
      showEmpty();
      return;
    }
    if (!S.queue.length) {
      finish();
      return;
    }
    showCard();
  }

  function close() {
    if (!S.open) return;
    S.open = false;
    S.busy = false;
    window.removeEventListener("keydown", onKeyDown, true);
    document.body.classList.remove("-review-modal-open");
    const m = document.getElementById(MODAL_ID);
    if (m) m.remove();
  }

  /** 语言切换时重绘当前文案（模态常显节点 + 进度 + 按钮）。 */
  function repaintTexts() {
    const box = document.getElementById(MODAL_ID);
    if (!box) return;
    if (global.MemoriaI18n && global.MemoriaI18n.applyStatic) global.MemoriaI18n.applyStatic(box);
    paintProgress();
    if (S.card) {
      renderGradeBar(!!S.flipped);
      const hint = box.querySelector(".-review-hint");
      if (hint) hint.textContent = T("review.flipHint");
    }
  }

  let bound = false;
  function boot() {
    if (!global.document) return;
    const btn = document.getElementById("btn-review");
    if (btn && !btn.__reviewBound) {
      btn.__reviewBound = true;
      btn.addEventListener("click", open);
    }
    if (!bound) {
      bound = true;
      document.addEventListener("keydown", onShortcut);
      if (global.MemoriaI18n && global.MemoriaI18n.addRefresh) global.MemoriaI18n.addRefresh(repaintTexts);
    }
  }

  if (global.document) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
    else boot();
    global.addEventListener("pywebviewready", boot);
  }

  global.MemoriaReviewModal = { open: open, close: close };
})(window);
