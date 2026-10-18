/**
 * R4-3 v1：**悬浮复习卡**（可被 agent 呼出 / 可撤回 / 就地作答）。
 *
 * 设计见 `docs/design/review-cards-handoff.md` 与 `docs/design/preview-render-refactor.md` 附 R4-3。
 *
 * **边界（v1，人已拍板）**：① 只支持「作业进行中」呼出（复用 `agent_ask_poll` 的 250ms 轮询，呼出/撤回信号
 * 随载荷 `pending_summons` 带回）；② 呼出范围 = 任意已存在的卡（agent 工具缺省从今日到期挑）；③ 免审批
 * （`review_summon`/`review_revoke` 是 `read_only=True` 工具）；④ 呼出/撤回**不落盘**（内存态，非事实源）。
 *
 * **复用而非重写**：卡面渲染复用 `window.MemoriaReviewModal` 导出的**纯渲染原语**（`faceSource` / `paintFace` /
 * `isAutoCard` / `isAgentInputCard` / `revealForFlip`）⇒ markdown + 公式 + cloze 只有一套；作答/评分走**同一套
 * UI RPC**（`review_summon_card` 取隔离卡面、`review_submit_one` 判分、`review_grade_one` 评分、`review_reveal_one`
 * cloze 翻面）。**答案隔离仍在后端**（`_review_ui_attach_feedback` → `_review_ui_hide_answers`），本模块绝不直读
 * `cards.json`。
 *
 * **全局开关 + snooze（前端内存态）**：开关存 `localStorage["review-summon-enabled"]`（默认开）；「收起/忽略」后
 * 同卡 30 分钟内不再呼出（snooze 由本模块自行挡，后端不感知）。
 * **零依赖**：只经应用门面 `window.MemoriaApp`（`call` / `T` / `esc` / `showFlashError` / `state`）；不改
 * `app.js` / `agent-panel.js`（轮询钩子用「包一层 `call`」同款手法，与 `agent-question.js` / `plan-confirm.js` 并列）。
 */
(function (global) {
  "use strict";

  const A = () => global.MemoriaApp || {};
  const T = (k, p) => (A().T ? A().T(k, p) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));

  function call(method, ...args) {
    const app = A();
    if (!app.call) return Promise.resolve({ status: "error", code: "no_bridge", message: "桥不可用" });
    return Promise.resolve(app.call(method, ...args));
  }
  function flash(message, detail) {
    const app = A();
    if (app.showFlashError) app.showFlashError(message, detail || "");
  }

  const SWITCH_KEY = "review-summon-enabled";
  const SNOOZE_MS = 30 * 60 * 1000; // 「收起/忽略」后同卡 30 分钟内不再呼出

  const S = {
    queue: [], // 待显示的 card_id 队列（R4-3 后续：一次呼出多张、逐张作答）
    card: null, // 隔离卡面（review_summon_card 返回）
    full: null, // cloze 翻面后带答案的完整卡（revealForFlip 返回）
    flipped: false,
    judged: false,
    busy: false,
    showing: false, // showNext 重入保护（避免并发 pop 掏空队列）
    snoozed: {}, // card_id -> epoch(ms) 到 snooze 到期
  };

  function enabled() {
    try { return localStorage.getItem(SWITCH_KEY) !== "0"; } catch (e) { return true; }
  }
  function setEnabled(on) {
    try { localStorage.setItem(SWITCH_KEY, on ? "1" : "0"); } catch (e) { /* ignore */ }
  }
  function kbPath() {
    const st = A().state;
    return (st && st.kbPath) || "";
  }
  const RM = () => global.MemoriaReviewModal || {};
  const $ = (sel) => document.querySelector(sel);

  function isAuto(card) {
    const rm = RM();
    return rm.isAutoCard ? rm.isAutoCard(card) : false;
  }
  function isAgentInput(card) {
    const rm = RM();
    return rm.isAgentInputCard ? rm.isAgentInputCard(card) : false;
  }

  // ── 悬浮卡 DOM ────────────────────────────────────────────────────────────────

  function ensureRoot() {
    let el = document.getElementById("-review-summon");
    if (el && el.isConnected) return el;
    el = document.createElement("div");
    el.id = "-review-summon";
    el.className = "-review-summon";
    el.style.display = "none";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", T("review.summonAria"));
    el.innerHTML =
      '<div class="-review-summon-head" id="-review-summon-head">' +
      '<span class="-review-summon-title">' + esc(T("review.summonTitle")) + "</span>" +
      '<span class="-review-summon-count" id="-review-summon-count"></span>' +
      '<button type="button" class="-btn -btn--sm -review-summon-open" id="-review-summon-open" title="打开来源" aria-label="打开来源">' + esc(T("review.openSource")) + "</button>" +
      '<button type="button" class="-btn -btn--sm -review-summon-next" id="-review-summon-next">' + esc(T("review.next")) + "</button>" +
      '<button type="button" class="-icon-btn -review-summon-ignore" id="-review-summon-ignore" ' +
      'title="' + esc(T("review.summonIgnore")) + '">\u00d7</button>' +
      "</div>" +
      '<div class="-review-summon-face markdown-body" id="-review-summon-face"></div>' +
      '<div class="-review-summon-answer" id="-review-summon-answer"></div>' +
      '<div class="-review-summon-verdict" id="-review-summon-verdict" aria-live="polite"></div>' +
      '<div class="-review-summon-grade" id="-review-summon-grade"></div>';
    document.body.appendChild(el);
    bindDrag(el);
    const ignore = el.querySelector("#-review-summon-ignore");
    if (ignore) ignore.addEventListener("click", revoke);
    const openBtn = el.querySelector("#-review-summon-open");
    if (openBtn) openBtn.addEventListener("click", function () { openSource(); });
    const nextBtn = el.querySelector("#-review-summon-next");
    if (nextBtn) nextBtn.addEventListener("click", function () { advance(); });
    return el;
  }

  function bindDrag(el) {
    const head = el.querySelector("#-review-summon-head");
    if (!head) return;
    let sx = 0; let sy = 0; let ox = 0; let oy = 0; let dragging = false;
    head.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      dragging = true;
      sx = e.clientX; sy = e.clientY;
      const r = el.getBoundingClientRect();
      ox = r.left; oy = r.top;
      e.preventDefault();
    });
    document.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      el.style.right = "auto";
      el.style.bottom = "auto";
      el.style.left = (ox + e.clientX - sx) + "px";
      el.style.top = (oy + e.clientY - sy) + "px";
    });
    document.addEventListener("mouseup", () => { dragging = false; });
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────────────

  async function paintFace() {
    const el = $("#-review-summon-face");
    if (!el) return;
    const rm = RM();
    const card = S.flipped ? (S.full || S.card) : S.card;
    if (rm.paintFace && rm.faceSource) {
      await rm.paintFace(el, card, S.flipped);
    } else {
      el.textContent = String((card && (S.flipped ? card.back : card.front)) || "");
    }
  }

  function renderGrade(enabled) {
    const f = $("#-review-summon-grade");
    if (!f) return;
    const card = S.card;
    if (!card || isAuto(card) || isAgentInput(card)) {
      f.innerHTML = ""; // auto/agent 型不显示 1-4（判分由后端/agent，不由用户评熟悉度）
      return;
    }
    const rows = [[1, "review.grade.again"], [2, "review.grade.hard"], [3, "review.grade.good"], [4, "review.grade.easy"]];
    f.innerHTML = "";
    rows.forEach((row) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "-btn -btn--sm -review-summon-grade-btn";
      btn.setAttribute("data-grade", String(row[0]));
      btn.innerHTML = '<span class="-review-kbd">' + row[0] + "</span><span>" + esc(T(row[1])) + "</span>";
      btn.disabled = !enabled;
      btn.addEventListener("click", () => grade(Number(row[0])));
      f.appendChild(btn);
    });
  }

  function renderAnswer() {
    const box = $("#-review-summon-answer");
    if (!box) return;
    const card = S.card;
    const verdict = $("#-review-summon-verdict");
    if (verdict) verdict.innerHTML = "";
    if (!card) { box.innerHTML = ""; return; }
    if (S.flipped) { box.innerHTML = ""; return; }
    if (isAuto(card) || isAgentInput(card)) {
      const t = String(card.type || "");
      const opts = Array.isArray(card.options) ? card.options : [];
      if (t === "mcq" && opts.length) {
        box.innerHTML = '<div class="-review-summon-opts" role="group"></div>';
        const host = box.querySelector(".-review-summon-opts");
        opts.forEach((opt, i) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "-btn -review-summon-opt";
          btn.setAttribute("data-choice", String(opt));
          btn.innerHTML = '<span class="-review-opt-key">' + esc(i < 9 ? String(i + 1) : String.fromCharCode(97 + i)) + "</span>" +
            '<span class="-review-opt-text">' + esc(opt) + "</span>";
          btn.addEventListener("click", () => submitAnswer(String(opt), null));
          host.appendChild(btn);
        });
      } else {
        const multi = String(card.input || "") === "multi" || t === "produce";
        box.innerHTML =
          (multi ? '<textarea class="-review-summon-input" id="-review-summon-input" rows="3" spellcheck="false" ' : '<input type="text" class="-review-summon-input" id="-review-summon-input" autocomplete="off" spellcheck="false" ') +
          'placeholder="' + esc(T("review.inputPlaceholder")) + '">' + (multi ? "</textarea>" : "") +
          '<button type="button" class="-btn primary -btn--sm" id="-review-summon-submit">' + esc(T("review.submit")) + "</button>";
        const input = box.querySelector("#-review-summon-input");
        const submit = box.querySelector("#-review-summon-submit");
        const doSubmit = () => submitAnswer(null, input ? String(input.value || "") : "");
        if (submit) submit.addEventListener("click", doSubmit);
        if (input) {
          input.addEventListener("keydown", (e) => {
            if (e.isComposing || e.keyCode === 229) return;
            if (e.key === "Enter" && !multi) { e.preventDefault(); doSubmit(); }
            if (e.key === "Enter" && multi && (e.ctrlKey || e.metaKey)) { e.preventDefault(); doSubmit(); }
          });
          setTimeout(() => { try { input.focus({ preventScroll: true }); } catch (e2) { try { input.focus(); } catch (e3) { /* noop */ } } }, 30);
        }
      }
    } else {
      box.innerHTML =
        '<button type="button" class="-btn primary -btn--sm" id="-review-summon-flip">' + esc(T("review.summonFlip")) + "</button>";
      const flipBtn = box.querySelector("#-review-summon-flip");
      if (flipBtn) flipBtn.addEventListener("click", flip);
    }
  }

  function setBusy(on) {
    S.busy = !!on;
    const el = $("#-review-summon");
    if (!el) return;
    const nodes = el.querySelectorAll("button");
    for (let i = 0; i < nodes.length; i += 1) {
      if (nodes[i].classList.contains("-review-summon-ignore")) continue;
      nodes[i].disabled = !!on;
    }
  }

  function setVerdict(html) {
    const box = $("#-review-summon-verdict");
    if (box) box.innerHTML = html || "";
  }

  // ── 交互 ──────────────────────────────────────────────────────────────────────

  async function flip() {
    if (!S.card || S.busy || S.flipped) return;
    const rm = RM();
    let card = S.card;
    if (rm.revealForFlip && String(card.type || "") === "cloze" && !isAuto(card)) {
      card = await rm.revealForFlip(card);
    }
    S.full = card;
    S.flipped = true;
    await paintFace();
    renderAnswer(); // 翻面后清掉翻面按钮区
    renderGrade(true);
  }

  async function submitAnswer(choice, text) {
    if (!S.card || S.busy || S.judged) return;
    const cid = String(S.card.card_id || "");
    S.busy = true;
    setBusy(true);
    let res;
    try {
      res = await call("review_submit_one", cid, choice, text, null, kbPath());
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    S.busy = false;
    if (!S.card || String(S.card.card_id || "") !== cid) return;
    if (!res || res.status !== "ok") {
      setBusy(false);
      setVerdict('<div class="-review-summon-verdict-bad">' + esc(T("review.submitFailed", { msg: String((res && (res.message || res.code)) || "") })) + "</div>");
      return;
    }
    S.judged = true;
    S.lastAnswer = String(text || ""); revealVerdict(res);
  }

  function revealVerdict(res) {
    const v = String(res.verdict || "");
    const cls = v === "correct" ? "-review-summon-verdict-ok" : (v === "wrong" ? "-review-summon-verdict-bad" : "-review-summon-verdict-wait");
    const label = v === "correct" ? T("review.verdictCorrect") : (v === "wrong" ? T("review.verdictWrong") : T("review.verdictUnjudged"));
    let html = '<div class="' + cls + '">' + esc(label) + "</div>";
    if (typeof res.answer === "string" && res.answer) {
      html += '<div class="-review-summon-verdict-line"><span class="-review-summon-verdict-tag">' + esc(T("review.revealAnswer")) + "</span>" + esc(res.answer) + "</div>";
    }
    if (typeof res.explain === "string" && res.explain) {
      html += '<div class="-review-summon-verdict-line"><span class="-review-summon-verdict-tag">' + esc(T("review.explainLabel")) + "</span>" + esc(res.explain) + "</div>";
    }
    setVerdict(html);
    setBusy(false);
    const ans = $("#-review-summon-answer");
    if (ans && isAuto(S.card)) ans.innerHTML = ""; // auto 卡清选项；agent 卡保留输入显示用户作答
    if (typeof res.rating === "number") {
      grade(res.rating, true); // auto 卡：后端已自适应折算 1-4，自动落调度、不再显示 1-4；卡留显示 verdict 供用户关闭
      return;
    }
    if (v === "unjudged") { triggerJudge(S.card); setVerdict('<div class="-review-summon-verdict-wait"><span class="-review-spinner"></span>判分中…</div>'); } renderGrade(false); // 自动触发判分（内部 pollJudgeJob 驱动）+spinner；agent 卡不显示 1-4
  }

  async function grade(g, keep) {
    if (!S.card || S.busy) return;
    const cid = String(S.card.card_id || "");
    S.busy = true;
    setBusy(true);
    let res;
    try {
      res = await call("review_grade_one", cid, g, null, kbPath());
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    S.busy = false;
    if (res && res.status === "ok") {
      if (!keep) advance(); // self 卡：评分后自动下一张（队列空则隐藏）
      return;
    }
    setBusy(false);
    flash(T("review.gradeFailed", { card: cid }), (res && (res.message || res.code)) || "");
  }

  function dismiss() {
    if (S.card && !S.judged) {
      const cid = String(S.card.card_id || "");
      if (cid) S.snoozed[cid] = Date.now() + SNOOZE_MS;
    }
    advance(); // 「忽略」= snooze 当前卡 + 跳到下一张
  }

  function hide() {
    const el = $("#-review-summon");
    if (el) el.style.display = "none";
    S.card = null;
    S.full = null;
    S.flipped = false;
    S.judged = false;
    S.busy = false;
    updateCounter();
  }

  // ── 呼出 / 撤回（R4-3 后续：队列化，一次呼出多张、逐张作答）───────────────────

  function snoozedUntil(cid) {
    return S.snoozed[String(cid || "")] || 0;
  }

  function enqueue(cid) {
    if (!cid) return;
    const c = String(cid);
    if (S.queue.indexOf(c) < 0 && Date.now() >= snoozedUntil(c)) S.queue.push(c);
  }

  function updateCounter() {
    const el = $("#-review-summon-count");
    if (!el) return;
    const n = S.queue.length;
    el.textContent = n > 0 ? "还有 " + n + " 张" : "";
  }

  async function showNext() {
    if (S.showing || S.busy) return;
    S.showing = true;
    try {
      while (S.queue.length) {
        const cid = S.queue.shift();
        if (Date.now() < snoozedUntil(cid)) continue; // snooze 期内跳过
        let res;
        try {
          res = await call("review_summon_card", cid, kbPath());
        } catch (e) {
          res = { status: "error", message: String((e && e.message) || e) };
        }
        if (!res || res.status !== "ok" || !res.card) continue; // 取不到隔离卡面就静默跳下一张
        const el = ensureRoot();
        S.card = res.card;
        S.full = res.card;
        S.flipped = false;
        S.judged = false;
        el.style.display = "block";
        updateCounter();
        await paintFace();
        renderAnswer();
        renderGrade(false);
        return;
      }
      hide(); // 队列空
    } finally {
      S.showing = false;
    }
  }

  function advance() {
    S.card = null;
    S.full = null;
    S.flipped = false;
    S.judged = false;
    S.busy = false;
    if (S.queue.length) showNext(); else hide();
  }

  async function summon(cid) {
    enqueue(cid);
    if (!S.card && S.queue.length) await showNext();
  }

  function revoke() {
    S.queue = [];
    hide();
  }

  function applyPending(rows) {
    const list = Array.isArray(rows) ? rows : [];
    let revoked = false;
    list.forEach((row) => {
      if (!row) return;
      if (row.revoke) { revoked = true; return; }
      if (row.card_id && enabled()) enqueue(String(row.card_id));
    });
    if (revoked) { revoke(); return; }
    if (!S.card && S.queue.length) showNext();
  }

  // ── 轮询钩子（包一层 `call`，只认 `agent_ask_poll`）───────────────────────────

  (function bindPoll() {
    const facade = A();
    const base = facade && facade.call;
    if (typeof base !== "function") return;
    facade.call = function (fnName) {
      const pending = base.apply(this, arguments);
      if (fnName !== "agent_ask_poll") return pending;
      return Promise.resolve(pending).then((res) => {
        if (res && res.pending_summons) applyPending(res.pending_summons);
        return res;
      });
    };
  })();

  global.MemoriaReviewSummon = {
    summon,
    revoke,
    hide,
    setEnabled,
    enabled,
    applyPending,
  };

  // ── R4-3 后续（2026-10-13）：开放题提交后**自动触发 agent 判分 + 轮询回显** ─────────
  // 与 review-modal.js 同款逻辑（共享 `review_feedback_latest` / `agent_ask_start` / `review_feedback_add` 链路）。

  let judgeRequested = Object.create(null);

  function triggerJudge(card) {
    const cid = String((card && card.card_id) || "");
    const kb = kbPath();
    if (!cid || !kb) return;
    if (judgeRequested[cid]) return;
    judgeRequested[cid] = true;
    const front = String((card && card.front) || "").slice(0, 2000);
    const answer = String((S.lastAnswer) || "").slice(0, 4000);
    const prompt =
      "请判分复习卡 `" + cid + "`（开放题，judge:agent）。\n【题目】\n" + front + "\n\n【用户作答】\n" + (answer || "（无）") + "\n\n" +
      "请分析作答质量、给出判分，然后用 `review_feedback_add` 写入 feedback（你的分析文字）、verdict（correct/partial/wrong）、score（1-4）。若需参考该卡答案/知识点，可用 `review_due_list` 读取完整数据。";
    call("agent_ask_start", prompt, kb, null).then(function (res) {
      if (res && res.status === "ok" && res.job_id) {
        pollJudgeJob(cid, res.job_id);
      } else if (res && res.status !== "ok") {
        setVerdict('<div class="-review-summon-verdict-bad">判分触发失败：' + esc((res && (res.message || res.code)) || "未知") + "</div>");
      }
    }).catch(function (e) {
      setVerdict('<div class="-review-summon-verdict-bad">判分触发失败：' + esc(String((e && e.message) || e)) + "</div>");
    });
  }

  /** 轮询判分任务 job_id 直到 done/error，再读回反馈。 */
  function pollJudgeJob(cid, jobId) {
    const kb = kbPath();
    if (!kb) return;
    let cursor = 0;
    let tries = 0;
    const timer = setInterval(function () {
      if (!S.card || String(S.card.card_id || "") !== cid) { clearInterval(timer); return; }
      tries += 1;
      call("agent_ask_poll", jobId, cursor).then(function (r) {
        cursor = (r && r.cursor) || cursor;
        if (r && (r.status === "done" || r.status === "error")) {
          clearInterval(timer);
          pollJudgeFeedback(cid, 6, 2000);
        }
      }).catch(function (e) { /* 静默 */ });
      if (tries >= 40) {
        clearInterval(timer);
        if (S.card && String(S.card.card_id || "") === cid) setVerdict('<div class="-review-summon-verdict-bad">判分超时：agent 未返回分析，请到会话查看</div>');
      }
    }, 3000);
  }

  function pollJudgeFeedback(cid, maxTries, intervalMs) {
    const kb = kbPath();
    if (!kb) return;
    const cap = maxTries || 12; const iv = intervalMs || 5000;
    let tries = 0;
    const timer = setInterval(function () {
      if (!S.card || String(S.card.card_id || "") !== cid) { clearInterval(timer); return; }
      tries += 1;
      call("review_feedback_latest", cid, kb).then(function (res) {
        if (res && res.status === "ok" && res.feedback && typeof res.feedback.feedback === "string" && res.feedback.feedback) {
          clearInterval(timer);
          renderJudgeFeedback(cid, res.feedback);
        }
      }).catch(function (e) { /* 静默 */ });
      if (tries >= cap) {
        clearInterval(timer);
        if (S.card && String(S.card.card_id || "") === cid) setVerdict('<div class="-review-summon-verdict-bad">判分超时：agent 未返回分析，请到会话查看</div>');
      }
    }, iv);
  }

  function renderJudgeFeedback(cid, fb) {
    if (!S.card || String(S.card.card_id || "") !== cid) return;
    S.judged = true;
    const v = String(fb.verdict || "");
    const cls = v === "correct" ? "-review-summon-verdict-ok" : (v === "wrong" ? "-review-summon-verdict-bad" : "-review-summon-verdict-wait");
    const label = v === "correct" ? T("review.verdictCorrect") : (v === "wrong" ? T("review.verdictWrong") : T("review.feedbackLabel"));
    let html = '<div class="' + cls + '">' + esc(label) + "</div>";
    if (typeof fb.feedback === "string" && fb.feedback) {
      html += '<div class="-review-summon-verdict-line">' + esc(fb.feedback) + "</div>";
    }
    html += replyFieldHtml();
    setVerdict(html);
    const send = $("#-review-feedback-reply-send");
    if (send) send.addEventListener("click", function () {
      const ta = $("#-review-feedback-reply");
      submitReply(cid, ta ? ta.value : "");
    });
  }

  function replyFieldHtml() {
    return '<div class="-review-feedback-reply">' +
      '<textarea class="-review-input" id="-review-feedback-reply" rows="2" placeholder="进一步反馈…"></textarea>' +
      '<button type="button" class="-btn primary" id="-review-feedback-reply-send">发送</button>' +
      "</div>";
  }

  function triggerJudgeReply(cid, reply) {
    const kb = kbPath();
    if (!kb) return;
    const prompt =
      "用户对复习卡 `" + cid + "` 的判分给出了进一步反馈：\n" + reply +
      "\n请用 `review_attempts_list` 读取该卡完整记录，回应这条反馈（可修正判分），并用 `review_feedback_add` 写入新的 feedback（你的回应/修正分析）、verdict 和 score。";
    try { call("agent_ask_start", prompt, kb, null).catch(function () { /* 静默 */ }); } catch (e) { /* 静默 */ }
  }

  async function submitReply(cid, reply) {
    const text = String(reply || "").trim();
    if (!text) return;
    const kb = kbPath();
    if (!kb) return;
    let res;
    try { res = await call("review_feedback_reply", cid, text, kb); } catch (e) { res = { status: "error" }; }
    if (!res || res.status !== "ok") {
      setVerdict('<div class="-review-summon-verdict-bad">反馈记录失败</div>');
      return;
    }
    setVerdict('<div class="-review-summon-verdict-wait"><span class="-review-spinner"></span>判分中…</div>');
    triggerJudgeReply(cid, text);
    pollJudgeFeedback(cid);
  }

  /** 打开当前卡所属来源文件（定位到 `kp_id` 知识点）。卡面带 `file` 才可跳；无 `file`（如纯错题卡）静默。 */
  function openSource() {
    const card = S.card;
    if (!card) return;
    const file = String(card.file || "").trim();
    if (!file) return; // 无源文件（如错题卡 kp_id 空）⇒ 不跳
    const app = A();
    if (app && typeof app.openFile === "function") {
      try {
        app.openFile(file, { kpId: (card.kp_id && String(card.kp_id).trim()) || null });
      } catch (e) { /* 静默 */ }
    }
  }
})(window);
