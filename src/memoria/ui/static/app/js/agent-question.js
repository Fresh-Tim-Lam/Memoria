/**
 * `ask_user_question` 的**待答卡**（模型中途提问 → 人在面板作答 → 答案当普通工具结果回给模型）。
 *
 * 契约（上游 `packages/interaction/user-questions` + `tool-ask-user`；本地面见
 * `services/agent/questions.py` 与 `approval_bridge.py` 末尾「待答信道」）：
 *
 * 1. **只消费两个面**：轮询载荷 `agent_ask_poll` 的追加键 `pending_questions`（只增不改），
 *    与回填 RPC `agent_question_answer(question_id, answers, kb_path)`。**不读文件、不拼库路径**。
 * 2. **一批一卡**：后端一次 `ask()` = 一条待答项（`id` + `created_at` + 整批问题）⇒ 卡片把整批
 *    问题一次收齐、一次提交（与上游 `provider.ask(request)` 的粒度一致，不做"逐题分次作答"）。
 * 3. **答案形状 = 上游 `AskUserQuestionAnswerItem[]`**：`[{id, selected: [...], custom?}]`；
 *    `selected` 里放**选项标签原文**（不是序号），`custom` 是"其他"里自己写的那句话。
 * 4. **单选与自写互斥、多选可以并存**：单选时点选项会清空自写、自写非空会清掉选项；多选按上游
 *    口径允许"既选若干项、又补一句话"。
 * 5. **单选与多选长相一致**：控件都是原生 `input`（单选 `radio` / 多选 `checkbox`），外观共用同一套
 *    圆点（`app.css` 末尾「勾选框 / 单选框统一改圆点」块）；"这是单选还是多选"**只由标题后的
 *    `.-agent-question-mode` 徽标写明**（「单选」/「多选」）—— 不靠控件长相区分。
 * 6. **不许交白卷**：每题必须"选了至少一项"或"自己写了一句话"，否则原地提示、不发请求。
 * 7. **一次作答、随后收起**：提交成功即禁用该卡并写下人的答案摘要（当过程痕迹）；后端把待答项
 *    收敛掉（超时/取消/作业结束）而人没答 ⇒ 卡片标「问题已收起」，绝不假装答过。
 *
 * **卡放在对话栏里**（与问答/工具调用同一条流），对话栏不可用时**回落成弹窗**，绝不"点了没反应"。
 * **零依赖**：只用应用门面 `window.MemoriaApp`（`call` / `T` / `esc` / `showFlashError` / `state`），
 * 不改 `app.js` / `agent-panel.js`；轮询钩子用与 `agent-panel.js` 同款的"包一层 `call`"手法。
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

  //: 已挂出的卡片：键 = `id@created_at`（与审批卡同款键法：同一条跨帧反复出现只建一张，新的一条必出新卡）。
  const cards = {};

  //: 题号 → 题干（2026-09-23：人要求「答完把卡收起来、只把问答记录在工具块里」⇒ 工具行要能配出"问→答"，
  //: 所以这里留一份题面给 `agent-panel.js` 的 `ask_user_question` 行取用；本题面关掉应用即失效，
  //: 取不到时工具行**回退到只显示答案序号**，绝不把内部 id 露给人看）。
  const questionTexts = {};

  //: 已作答过的批次（键同 `cards`）：答完卡会被移除，但**后端可能还没把这条从 `pending_questions` 收敛掉**
  //: ⇒ 下一帧若又见到同一条，必须**不再重建**卡（否则卡会"闪现回来"）。这份记录只增不删，
  //: 键里带 `created_at` ⇒ 新的批次必然是新键，不会被误挡。
  const answered = {};

  /** 题干（供工具行渲染"问→答"用；查不到返回空串）。 */
  function questionText(id) {
    return String(questionTexts[String(id == null ? "" : id)] || "");
  }

  function chatBox() {
    const box = document.getElementById("agent-messages");
    if (!box || !box.isConnected) return null;
    return box;
  }

  function cardKey(row) {
    const id = String((row && row.id) || "");
    const at = String((row && row.created_at) || "");
    return id + "@" + at;
  }

  /** 卡片随对话流被清空/重绘 ⇒ 丢掉已脱离文档的元素（否则会一直"待答"下去）。 */
  function prune() {
    Object.keys(cards).forEach((key) => {
      const el = cards[key];
      if (!el || !el.isConnected) delete cards[key];
    });
  }

  function setState(el, text) {
    const node = el && el.querySelector(".-agent-question-state");
    if (node) node.textContent = String(text || "");
  }

  /** 该卡到此为止：禁用全部输入并给出终态文案（**卡保留**当过程痕迹；已有终态不覆盖）。 */
  function markDone(key, label) {
    const el = cards[String(key == null ? "" : key)];
    if (!el) return;
    if (el.classList.contains("-agent-question--done")) return;
    el.classList.add("-agent-question--done");
    setState(el, label || T("agent.question.done"));
    Array.prototype.forEach.call(el.querySelectorAll("button"), (btn) => {
      btn.disabled = true;
    });
  }

  function optHtml(question, index, option) {
    const type = question.multiSelect ? "checkbox" : "radio";
    const name = question.multiSelect ? "" : ` name="-agent-q-${index}"`;
    return (
      '<label class="-agent-question-opt">' +
      `<input type="${type}"${name} data-q-index="${index}" data-opt value="${esc(option.label)}">` +
      `<span class="-agent-question-opt-label">${esc(option.label)}</span>` +
      (option.description
        ? `<span class="-agent-question-opt-desc -muted">${esc(option.description)}</span>`
        : "") +
      "</label>"
    );
  }

  function itemHtml(question, index) {
    const options = Array.isArray(question.options) ? question.options : [];
    const heading = [question.header, question.question]
      .map((part) => String(part == null ? "" : part).trim())
      .filter(Boolean)
      .join("：");
    return (
      `<div class="-agent-question-item" data-q-index="${index}" data-question-id="${esc(question.id)}">` +
      `<div class="-agent-question-title">${esc(heading)}` +
      `<span class="-agent-question-mode -muted">${
        question.multiSelect ? esc(T("agent.question.multi")) : esc(T("agent.question.single"))
      }</span>` +
      `</div>` +
      (options.length
        ? `<div class="-agent-question-opts">${options.map((opt) => optHtml(question, index, opt)).join("")}</div>`
        : "") +
      `<input type="text" class="-agent-question-custom" data-q-index="${index}" spellcheck="false" ` +
      `placeholder="${esc(T("agent.question.custom"))}">` +
      "</div>"
    );
  }

  function cardEl(row) {
    const el = document.createElement("div");
    el.className = "-agent-msg -agent-msg--assistant -agent-question-msg";
    el.setAttribute("data-question-id", String(row.id || ""));
    el.setAttribute("data-question-key", cardKey(row));
    const list = Array.isArray(row.questions) ? row.questions : [];
    // 记下题面（工具行渲染"问→答"要用；题干与工具的 `header：question` 拼法保持一致）。
    list.forEach((q) => {
      if (!q || !q.id) return;
      const heading = [q.header, q.question]
        .map((part) => String(part == null ? "" : part).trim())
        .filter(Boolean)
        .join("：");
      if (heading) questionTexts[String(q.id)] = heading;
    });
    el.innerHTML =
      '<span class="-agent-msg-role">' +
      esc(T("agent.question.role")) +
      "</span>" +
      '<div class="-agent-question">' +
      '<div class="-agent-question-head">' +
      esc(T("agent.question.title", { n: list.length })) +
      "</div>" +
      list.map(itemHtml).join("") +
      '<div class="plan-actions">' +
      '<button type="button" class="-btn primary -btn--sm" data-act="submit">' +
      esc(T("agent.question.submit")) +
      "</button>" +
      '<span class="-agent-question-state -muted"></span>' +
      "</div></div>";
    el.querySelectorAll("input").forEach((input) => {
      input.addEventListener("change", () => {
        syncExclusive(el, input);
      });
      if (input.type === "text") {
        input.addEventListener("input", () => {
          syncExclusive(el, input);
        });
      }
    });
    const submit = el.querySelector('[data-act="submit"]');
    if (submit)
      submit.addEventListener("click", () => {
        submitCard(el);
      });
    return el;
  }

  /**
   * 单选与"其他"互斥（多选不互斥，与上游 `custom` 可伴随 `selected` 的口径一致）：
   * 单选点了选项 ⇒ 清空该题的自写；自写有内容 ⇒ 清掉该题的单选。
   */
  function syncExclusive(el, input) {
    const item = input.closest(".-agent-question-item");
    if (!item) return;
    const radios = item.querySelectorAll('input[type="radio"]');
    if (!radios.length) return;
    if (input.type === "radio") {
      const custom = item.querySelector(".-agent-question-custom");
      if (custom && input.checked) custom.value = "";
      return;
    }
    if (String(input.value || "").trim()) {
      radios.forEach((radio) => {
        radio.checked = false;
      });
    }
  }

  /** 收集人的作答（上游 `AskUserQuestionAnswerItem[]`）；每题都答了才返回，否则返回 `null`。 */
  function collect(el) {
    const items = el.querySelectorAll(".-agent-question-item");
    const answers = [];
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      const id = String(item.getAttribute("data-question-id") || "");
      const selected = [];
      item.querySelectorAll("input[data-opt]").forEach((input) => {
        if (input.checked) selected.push(String(input.value || ""));
      });
      const customNode = item.querySelector(".-agent-question-custom");
      const custom = customNode ? String(customNode.value || "").trim() : "";
      if (!id || (!selected.length && !custom)) return null;
      const answer = { id: id, selected: selected };
      if (custom) answer.custom = custom;
      answers.push(answer);
    }
    return answers.length ? answers : null;
  }

  /** 人的答案摘要（给卡片写终态用；**就是**回给模型的那份内容，不是另写一套）。 */
  function summary(answers) {
    return answers
      .map((row) => {
        const parts = (row.selected || []).slice();
        if (row.custom) parts.push(row.custom);
        return String(row.id) + "：" + parts.join("、");
      })
      .join("｜");
  }

  function upsertCard(row) {
    const key = cardKey(row);
    if (!key || cards[key] || answered[key]) return; // 已作答过的批次不再重建（否则会"闪现回来"）
    const box = chatBox();
    if (!box) return;
    const empty = box.querySelector(".-agent-empty");
    if (empty) empty.remove();
    const el = cardEl(row);
    box.appendChild(el);
    cards[key] = el;
    box.scrollTop = box.scrollHeight; // 要人作答的卡必须进视野（与审批卡同款）
  }

  /** 一帧 `pending_questions`：新增的建卡；不再待答的（后端已收敛）标「已收起」。 */
  function applyPendingQuestions(rows) {
    const list = Array.isArray(rows) ? rows : [];
    prune();
    const live = {};
    list.forEach((row) => {
      if (row) live[cardKey(row)] = true;
    });
    Object.keys(cards).forEach((key) => {
      if (!live[key]) markDone(key, T("agent.question.done"));
    });
    list.forEach(upsertCard);
  }

  /** 提交一次作答（成功即写下摘要并收起；失败原地提示、卡片可再点 —— 绝不留"点了没反应"）。 */
  async function submitCard(el) {
    const key = String(el.getAttribute("data-question-key") || "");
    const questionId = String(el.getAttribute("data-question-id") || "");
    if (!key || !questionId) return;
    const answers = collect(el);
    if (!answers) {
      setState(el, T("agent.question.needAnswer"));
      const first = el.querySelector("input");
      if (first) first.focus();
      return;
    }
    setState(el, T("agent.question.sending"));
    let res;
    try {
      res = await call("agent_question_answer", questionId, answers, (A().state || {}).kbPath || null);
    } catch (err) {
      res = { status: "error", message: String((err && err.message) || err) };
    }
    if (!res || res.status !== "ok" || !res.answered) {
      flash(T("agent.question.failed"), (res && (res.message || res.code)) || "");
      setState(el, "");
      return;
    }
    // 2026-09-23（人）：「我回复完 agent 之后这个卡还显示，甚至对话结束还显示」⇒ 答完**把卡收起来**。
    // 记录不丢：问答由工具行（`ask_user_question`）以「问→答」文字承载，见 `agent-panel.js::toolDisplayDetail`。
    const node = cards[key];
    if (node) node.remove();
    delete cards[key];
    answered[key] = true; // 见 `answered` 注释：挡住"下一帧又冒出来"
  }

  /**
   * 轮询钩子：包一层 `MemoriaApp.call`，只认 `agent_ask_poll`（与 `agent-panel.js` 的审批卡同款手法，
   * 两层包装互不干扰：本模块后加载 ⇒ 包在它外面，先让内层处理 `pending_approvals`）。
   */
  (function bindPoll() {
    const facade = A();
    const base = facade && facade.call;
    if (typeof base !== "function") return;
    facade.call = function (fnName) {
      const pending = base.apply(this, arguments);
      if (fnName !== "agent_ask_poll") return pending;
      return Promise.resolve(pending).then((res) => {
        if (res && res.pending_questions) applyPendingQuestions(res.pending_questions);
        return res;
      });
    };
  })();

  global.MemoriaAgentQuestion = {
    applyPendingQuestions,
    cardEl,
    collect,
    summary,
    questionText,
  };
})(window);
