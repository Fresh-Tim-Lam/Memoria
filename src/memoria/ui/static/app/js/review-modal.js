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
    date: "", auto: false, judged: null, choice: null,
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
    for (let i = 0; i < btns.length; i += 1) btns[i].disabled = !(!on && (S.flipped || !!S.judged));
  }

  // ── 视图切换 ────────────────────────────────────────────────────────────────

  async function showCard() {
    const body = $("#-review-body");
    if (!body) return;
    S.flipped = false; S.judged = null; S.choice = null;
    S.item = S.queue[S.pos] || null;
    S.card = S.item ? S.item.card : null;
    if (!S.card) {
      finish();
      return;
    }
    // 重试项（队尾重排的"暂时性失败"卡）：直接按**已选的分**再试一次，**不要求再翻面**
    // （评分幂等 ⇒ 安全；不做乐观更新，仍以返回为准）。
    const retryGrade = S.item.autoGrade; S.auto = retryGrade == null && isAutoCard(S.card); S.agentInput = retryGrade == null && isAgentInputCard(S.card);
    paintProgress();
    body.innerHTML =
      '<div class="-review-face" id="-review-face"></div>' + (S.auto || S.agentInput ? answerUIHtml() : "") +
      '<div class="-review-hint">' + esc(T(S.auto || S.agentInput ? "review.answerHint" : "review.flipHint")) + "</div>";
    renderGradeBar(retryGrade != null || !!S.judged);
    S.flipped = retryGrade != null;
    await paintFace($("#-review-face"), S.card, S.flipped); S.shownAt = Date.now();
    if (S.auto || S.agentInput) setupAnswerUI(); else focusBox();
    if (retryGrade != null) grade(retryGrade);
  }

  async function flip() {
    if (!S.card || S.busy || S.flipped) return;
    S.busy = true; const card = await revealForFlip(S.card); S.busy = false; if (!card || !S.open || !S.card || S.card.card_id !== card.card_id) return;
    S.flipped = true;
    const face = $("#-review-face");
    if (face) await paintFace(face, card, true);
    renderGradeBar(true); focusBox();
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
    if (inEditable()) return; if (S.auto && handleAutoKey(e)) return; // 输入框聚焦交还；R4.3 作答交互优先（作答前不翻面）
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
      if (S.flipped || S.judged) grade(Number(e.key));
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
    S.flipped = false; S.auto = false; S.judged = null; S.choice = null;
    S.retried = Object.create(null); revealCache = Object.create(null); // 截断本次会话的揭晓缓存（见模块尾 revealForFlip）
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
      renderGradeBar(!!S.flipped || !!S.judged);
      const hint = box.querySelector(".-review-hint");
      if (hint) hint.textContent = T(S.auto ? "review.answerHint" : "review.flipHint");
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

  // ── R4.3（2026-10-11）：作答交互（**只** auto 判分那三型）──────────────────────────
  // 设计见 `docs/design/preview-render-refactor.md` 附 R4（R4.3）。**范围收窄**：只有
  // `mcq` / `gapfill` / 带 `answer|accept` 的 `cloze`（即 `judge:auto`）有作答交互；`basic` /
  // `reverse` / `judge:self` 的 `cloze` / `short` / `produce` **维持现状**（题面 → 翻面 → 1..4 自评）。
  // **判分走后端** `review_submit_one`（只读；作答后才揭晓 `answer`/`explain`）；**写评分仍走**
  // `review_grade_one`。**不做乐观更新**：以返回 verdict 为准（失败 / unjudged / unreviewable 如实显示）。
  // 整块追加在模块尾 ⇒ 上方所有 `review-modal.js:<行号>` 锚点零漂移。

  /** 该卡是否走作答交互：`judge:auto`（后端已持久化该字段）；兜底 `mcq`+`options`。 */
  function isAutoCard(card) {
    if (!card) return false;
    if (String(card.judge || "") === "auto") return true;
    return String(card.type || "") === "mcq" && Array.isArray(card.options) && card.options.length >= 2;
  }

  /** 作答区 HTML（mcq 的选项按钮由 `setupAnswerUI` 用 DOM 建；输入型在此给 input + 提交按钮）。 */
  function answerUIHtml() {
    const t = String((S.card && S.card.type) || "");
    const inner = t === "mcq"
      ? '<div class="-review-answer -review-mcq" id="-review-answer" role="group"></div>'
      : '<div class="-review-answer -review-inputs">' + inputFieldHtml() +
        '<button type="button" class="-btn primary" id="-review-submit">' +
        esc(T("review.submit")) + "</button></div>";
    return inner + '<div class="-review-verdict" id="-review-verdict" aria-live="polite"></div>';
  }

  function optionKeyLabel(i) { return i < 9 ? String(i + 1) : String.fromCharCode(97 + i); }

  /** 绑定作答区事件并聚焦（gapfill/cloze 直接聚焦输入框）。 */
  function setupAnswerUI() {
    const t = String((S.card && S.card.type) || "");
    if (t === "mcq") {
      const box = $("#-review-answer");
      const opts = Array.isArray(S.card && S.card.options) ? S.card.options : [];
      if (box) {
        opts.forEach(function (opt, i) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "-review-option";
          btn.setAttribute("data-choice", String(opt));
          btn.setAttribute("data-idx", String(i));
          btn.innerHTML = '<span class="-review-opt-key">' + esc(optionKeyLabel(i)) + '</span>' +
            '<span class="-review-opt-text">' + esc(opt) + "</span>";
          btn.addEventListener("click", function () { submitAnswer(String(opt), null); });
          box.appendChild(btn);
        });
      }
      focusBox();
      return;
    }
    const inp = $("#-review-input");
    if (inp) {
      inp.addEventListener("keydown", function (e) {
        if (e.isComposing || e.keyCode === 229) return; // IME 组字中：一行都不碰
        if (e.key === "Escape") { e.preventDefault(); close(); return; }
        if (e.key === "Enter") { if (inp.tagName === "TEXTAREA" && !(e.ctrlKey || e.metaKey)) return; e.preventDefault(); submitAnswer(null, inp.value); }
      });
      setTimeout(function () {
        try { inp.focus({ preventScroll: true }); } catch (_e) { try { inp.focus(); } catch (_e2) { /* noop */ } }
      }, 30);
    }
    const submitBtn = $("#-review-submit");
    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        const el = $("#-review-input");
        submitAnswer(null, el ? el.value : "");
      });
    }
  }

  /** 作答控件的忙碌态（只碰作答区，不动评分条 / S.busy）。 */
  function setAnswerBusy(on) {
    const root = $("#-review-answer");
    if (!root) return;
    const els = root.querySelectorAll("button,input");
    for (let i = 0; i < els.length; i += 1) els[i].disabled = !!on;
  }

  /** 键盘（`auto` 卡）：作答前选/答；判分后 1..4 评分。返回 true 表示已处理（勿再走翻面分支）。 */
  function handleAutoKey(e) {
    if (!S.auto || !S.card || S.busy) return false;
    if (S.judged) {
      if (/^[1-4]$/.test(e.key)) { e.preventDefault(); grade(Number(e.key)); return true; }
      if (e.key === " " || e.key === "Enter") { e.preventDefault(); return true; } // 已判分：不翻面
      return false;
    }
    if (String(S.card.type || "") === "mcq") {
      const opts = Array.isArray(S.card.options) ? S.card.options : [];
      let idx = -1;
      if (/^[1-9]$/.test(e.key)) idx = Number(e.key) - 1;
      else if (/^[a-z]$/i.test(e.key)) idx = e.key.toLowerCase().charCodeAt(0) - 97;
      if (idx >= 0 && idx < opts.length) { e.preventDefault(); submitAnswer(String(opts[idx]), null); return true; }
      if (e.key === " ") { e.preventDefault(); return true; } // 作答前不翻面
      if (e.key === "Enter") {
        e.preventDefault();
        const ae = document.activeElement;
        if (ae && ae.classList && ae.classList.contains("-review-option")) submitAnswer(String(ae.getAttribute("data-choice") || ""), null);
        return true; // 消费：不翻面
      }
      return false;
    }
    // gapfill / cloze：作答在输入框里（输入框聚焦时不会走到这）；空格/回车留给自己，不翻面
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); return true; }
    return false;
  }

  /** 提交作答给后端只读判分入口（`choice` 与 `text` 按题型二选一）。 */
  async function submitAnswer(choice, text) {
    if (!S.card || S.busy || S.judged) return;
    const cid = S.card.card_id;
    S.busy = true;
    setAnswerBusy(true);
    let res;
    try {
      res = await call("review_submit_one", cid, choice, text, null, kbPath(), S.shownAt ? (Date.now() - S.shownAt) : null);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    S.busy = false;
    if (!S.open || !S.card || S.card.card_id !== cid) return; // 已切卡 / 已关闭
    if (!res || res.status !== "ok") {
      setAnswerBusy(false); // 允许重试
      showVerdictError((res && (res.message || res.code)) || "", (res && res.code) || "");
      return;
    }
    revealVerdict(res); // 判分完成 ⇒ 作答控件保持禁用
  }

  /** 判分后揭晓：verdict + `answer`（若回）+ `explain`（若回）；随后开放 1..4 评分。 */
  function revealVerdict(res) {
    S.judged = { verdict: String(res.verdict || ""), answer: res.answer, explain: res.explain };
    const box = $("#-review-verdict");
    if (!box) return;
    const v = String(res.verdict || "");
    const cls = v === "correct" ? "-review-verdict-ok" : (v === "wrong" ? "-review-verdict-bad" : "-review-verdict-wait");
    const label = v === "correct" ? T("review.verdictCorrect") : (v === "wrong" ? T("review.verdictWrong") : T(res.recorded ? "review.recordedPending" : "review.verdictUnjudged"));
    let html = '<div class="-review-verdict-label ' + cls + '">' + esc(label) + "</div>";
    if (typeof res.answer === "string" && res.answer) {
      html += '<div class="-review-verdict-line"><span class="-review-verdict-tag">' + esc(T("review.revealAnswer")) +
        "</span>" + esc(res.answer) + "</div>";
    }
    if (typeof res.explain === "string" && res.explain) {
      html += '<div class="-review-verdict-line"><span class="-review-verdict-tag">' + esc(T("review.explainLabel")) +
        "</span>" + esc(res.explain) + "</div>";
    }
    box.innerHTML = html;
    renderGradeBar(true); // 判分后开放 1..4（用户可覆盖）
    focusBox();
  }

  /** 提交失败 / 无法判分 / 记录落盘失败：如实显示，不假装判过（`code` 决定文案，`record_failed` 单独提示）。 */
  function showVerdictError(msg, code) {
    const box = $("#-review-verdict");
    if (!box) return;
    const label = (code === "record_failed") ? T("review.recordFailed", { msg: String(msg || "") }) : T("review.submitFailed", { msg: String(msg || "") });
    box.innerHTML = '<div class="-review-verdict-label -review-verdict-bad">' + esc(label) + "</div>";
    focusBox();
  }

  // ── R4.3 收尾（2026-10-11）：**按需揭晓**（修 `judge:self` cloze 翻面看不到答案）────────────────
  // 回归：`judge:self` 的 cloze **没有 `answer`/`accept`** ⇒ 答案只在 `front` 的 `{{cN::答案}}` 里；
  // R4.2 收尾把 `front` 挖空（`{{cN::}}`）⇒ 界面翻面靠**回填 token 文本** ⇒ 一片空白。修法（人已拍板
  // 方案 B）：**只对 cloze 卡 · 翻面时**调只读 UI RPC `review_reveal_one` 取**完整卡面**（回填挖空 token）。
  // 每卡在**本次复习会话内**缓存一次（`open()` 重置）⇒ **不翻面就不请求**、同卡不重复请求。
  // `auto` 卡仍走 `review_submit_one`（不改）；`basic`/`reverse`/`short`/`produce` 不调（`back` 本就到前端）。
  // 整块追加在模块尾 ⇒ 上方所有 `review-modal.js:<行号>` 锚点零漂移。

  /** 本次复习会话的揭晓缓存（`card_id -> 完整卡面`；`open()` 重置 ⇒ 不跨会话残留）。 */
  let revealCache = Object.create(null);

  /**
   * cloze 卡翻面时**按需**取完整卡面：调只读 RPC `review_reveal_one` 拿**未挖空**的 `front`（顺带 `back`）⇒
   * `faceSource`/`fillCloze` 才能在翻面时把 `{{cN::答案}}` 回填出答案。**其它类型 / auto 卡 / 无 id 原样返回**
   * （即不请求）。失败 ⇒ 如实提示（`review.revealFailed`）并返回原（挖空）卡 ⇒ **不假装有答案**（不做乐观更新）。
   */
  async function revealForFlip(card) {
    if (!card || String(card.type || "") !== "cloze" || isAutoCard(card)) return card;
    const id = String(card.card_id || "");
    if (!id) return card;
    if (revealCache[id]) return revealCache[id];
    let res;
    try {
      res = await call("review_reveal_one", id, null, kbPath());
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok" || typeof res.front !== "string") {
      toast(T("review.revealFailed", { card: id }), (res && (res.message || res.code)) || "");
      return card;
    }
    const full = Object.assign({}, card, { front: res.front });
    if (typeof res.back === "string") full.back = res.back;
    revealCache[id] = full;
    return full;
  }

  // ── R4 P1（2026-10-12）：`short`/`produce` 作答输入（`judge:agent` ⇒ 提交后 `unjudged` 待 agent 判）─────
  // 设计见 `docs/design/preview-render-refactor.md` 附 R4（P1）。R4.3 只给 `auto` 三型（mcq/gapfill/cloze）
  // 作答交互；本轮**解锁** `short`/`produce` 的输入框 —— 它们 `judge:agent`，「没有去处就不能收」的前提已由
  // **P1 的作答记录**（`review_submit_one` 落 `attempts.jsonl`）补上 ⇒ **有去处，可收**。提交沿用同一条 UI RPC
  // （不新增写路径）；`input:single` ⇒ 单行 input，`input:multi`（produce）⇒ 多行 textarea（Enter 换行、
  // Ctrl/Cmd+Enter 提交）。整块**追加在模块尾** ⇒ 上方所有 `review-modal.js:<行号>` 锚点零漂移。

  /** 该卡是否需要输入型作答区：`short`/`produce` 且非 `auto` 判分（即 `judge:agent`）。 */
  function isAgentInputCard(card) {
    if (!card || isAutoCard(card)) return false;
    const t = String(card.type || "");
    return t === "short" || t === "produce";
  }

  /** 输入型作答控件 HTML：`input:multi`（produce）⇒ 多行 textarea；否则单行 input。 */
  function inputFieldHtml() {
    const t = String((S.card && S.card.type) || "");
    const multi = String((S.card && S.card.input) || (t === "produce" ? "multi" : "single")) === "multi";
    const ph = esc(T("review.inputPlaceholder"));
    return multi
      ? '<textarea class="-review-input" id="-review-input" rows="3" spellcheck="false" placeholder="' + ph + '"></textarea>'
      : '<input type="text" class="-review-input" id="-review-input" autocomplete="off" spellcheck="false" placeholder="' + ph + '">';
  }

  global.MemoriaReviewModal = { open: open, close: close };
})(window);
