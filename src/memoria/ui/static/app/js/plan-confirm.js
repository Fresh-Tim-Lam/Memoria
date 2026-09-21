/**
 * M3a ④：**计划确认卡** —— 写路径上**唯一**的人机界面（`window.MemoriaPlan`）。
 *
 * 契约（`docs/design/agent-plugin-design.md §9` / `docs/design/agent-capabilities.md §2.3.3`）：
 *
 * 1. **先看后写**：`agent_plan_preview` 是 dry-run（零落盘），卡片把"将改哪些文件、哪些行、
 *    before → after"摊开给人看；人**逐条勾选**后才 apply。未勾的 op 直接在 `plan.ops` 里去掉
 *    （勾选是**编译前**的选择，因此不引入"部分执行"，后端仍然 all-or-nothing）。
 * 2. **盘上版本 = 唯一权威**：preview 返回的 `base_versions`（人看过的那一版）原样回传；
 *    期间文件被改过 ⇒ 后端整批拒（`stale_write`，且**尚未建备份**）⇒ 卡片改为提示 + 「重新预览」。
 * 3. **人的当下操作最高**：apply 前若当前编辑还没落盘（`__memoriaHasPendingEdits`），先**等**
 *    （有界，≤3s），仍脏就**拒写**并说明 —— 绝不趁人正在编辑时抢写。
 * 4. **写期间让人机保存让路**：`MemoriaWriteGuard.setBusy(true)` 包住整个 apply（人机保存经
 *    `deferIfBusy` 重新入队），`finally` 里一定解除。
 * 5. **可撤销**：成功后卡片给出 txid 与「撤销这一批」→ `agent_plan_undo`（pre-image 逐字节写回；
 *    apply 之后被改过的文件会被后端 `external_change` 拦下，不静默覆盖）。
 *
 * **卡片放在对话栏里**（与问答/工具调用同一条流）：渲染进 `#agent-messages` 成为一条聊天项，
 * 而不是弹窗盖住界面 —— 计划是"智能体提出、人确认"的东西，它就属于那条对话。对话栏不可用时
 * （面板收起 / 没有对话栏）自动**回落成弹窗**，绝不出现"点了没反应"。入口按钮也装在对话栏的
 * 输入区（`. -agent-composer-actions` 里追加一个「计划」按钮），本模块**自带入口**（不改
 * `app.js` / `agent-panel.js` / `index.html` ⇒ 既有行号锚点零漂移）。
 *
 * **长文本一律"单行省略 + 悬浮看全"**：文件名 / 操作名 / 差异行都带 `title`（`cursor: help`），
 * 栏窄时截断但不丢信息。
 *
 * 依赖：应用门面 `window.MemoriaApp`（`call` / `T` / `esc` / `state` / `openFile`）与写守卫
 * `window.MemoriaWriteGuard`（§9 的忙位）；两者缺席时按"不可用"降级，不抛异常。
 */
(function (global) {
  const A = () => global.MemoriaApp || {};
  const WR = () => global.MemoriaWriteGuard || {};
  const T = (k, p) => (A().T ? A().T(k, p) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));

  //: 等待"当前编辑落盘"的上限与轮询间隔（人机保存是 1s 防抖，故 3s 足够；再脏就是真的在编辑）
  const IDLE_WAIT_MS = 3000;
  const IDLE_POLL_MS = 150;

  let card = null; // 当前卡片（对话栏里的一条聊天项，或回落时的弹窗）
  let lastState = null; // 当前卡片的重绘状态（切语言时原地重绘，不再打 RPC）

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  /** 对话栏的消息容器；面板收起 / 没有对话栏 ⇒ `null`（调用方回落成弹窗）。 */
  function chatBox() {
    const box = document.getElementById("agent-messages");
    if (!box || !box.isConnected) return null;
    if (!box.clientHeight && !box.offsetParent) return null;
    return box;
  }

  function close() {
    if (card) {
      card.remove();
      card = null;
    }
    lastState = null;
  }

  /** 切语言时原地重绘当前卡片（纯前端重排，**不再打 RPC**）；没有卡片则什么都不做。 */
  function redraw() {
    const s = lastState;
    if (!s || !card) return;
    if (s.kind === "preview") renderPreview(s.plan, s.preview);
    else if (s.kind === "problems") showPreviewProblems(s.plan, s.preview);
    else showResult(s.res, s.plan);
  }

  /** 有界等待"当前编辑/预览同步收敛"；返回 false 表示仍在编辑（此时**不写**）。 */
  async function waitForIdleEdits() {
    const pending = global.__memoriaHasPendingEdits;
    if (typeof pending !== "function") return true; // 无编辑态信号（如非编辑器页面）⇒ 不阻塞
    const deadline = Date.now() + IDLE_WAIT_MS;
    while (pending()) {
      if (Date.now() > deadline) return false;
      await sleep(IDLE_POLL_MS);
    }
    return true;
  }

  function opLabel(entry) {
    const key = "plan.op." + String(entry.op || "");
    const text = T(key);
    return text === key ? String(entry.op || "") : text;
  }

  /** 一行"被截断但有悬浮全文"的文本（栏窄时省略号，`title` 里给全）。 */
  function clipped(className, text, extra) {
    const full = String(text == null ? "" : text);
    return `<div class="${className}" title="${esc(full)}"${extra || ""}>${esc(full)}</div>`;
  }

  function opRow(entry) {
    const rows = Array.isArray(entry.diff) ? entry.diff : [];
    const body = rows.length
      ? rows
          .map(
            (r) =>
              clipped("plan-diff-line plan-diff-del", "- " + r.before) +
              clipped("plan-diff-line plan-diff-add", "+ " + r.after)
          )
          .join("")
      : `<div class="plan-diff-none">${esc(T("plan.noDiff"))}</div>`;
    const opId = String(entry.op_id || "");
    const label = opLabel(entry);
    return (
      `<label class="plan-op" title="${esc(label + " · " + opId)}">` +
      `<input type="checkbox" data-op-id="${esc(opId)}" checked>` +
      `<span class="plan-op-name">${esc(label)}</span>` +
      `<span class="plan-op-id">${esc(opId)}</span></label>` +
      `<div class="plan-op-body">${body}</div>`
    );
  }

  function fileBlocks(preview) {
    return (preview.files || [])
      .map((file) => {
        const ops = (file.ops || []).map(opRow).join("");
        return `<div class="plan-file">${clipped("plan-file-path", file.file)}${ops}</div>`;
      })
      .join("");
  }

  function listBlock(kind, title, rows) {
    if (!rows || !rows.length) return "";
    const items = rows
      .map((row) => `<li title="${esc(row.message || row.code || "")}">[${esc(row.op_id || "-")}] ${esc(row.message || row.code || "")}</li>`)
      .join("");
    return `<div class="${kind}"><div class="${kind}-title">${esc(title)}</div><ul>${items}</ul></div>`;
  }

  function buttons(items) {
    return (
      `<div class="plan-actions">` +
      items
        .map(
          (it) =>
            `<button type="button" class="-btn ${it.cls || "-btn--sm"}" data-act="${it.act}"` +
            `${it.title ? ` title="${esc(it.title)}"` : ""}>${esc(it.label)}</button>`
        )
        .join("") +
      `</div>`
    );
  }

  /**
   * 把一段卡片内容挂到**对话栏**（成一条聊天项）；对话栏不可用时回落成弹窗。
   * 返回可交互的根元素。
   */
  function mount(inner) {
    close();
    const box = chatBox();
    if (box) {
      const el = document.createElement("div");
      el.className = "-agent-msg -agent-msg--assistant -agent-plan-msg";
      el.innerHTML = `<span class="-agent-msg-role">${esc(T("plan.role"))}</span>${inner}`;
      const empty = box.querySelector(".-agent-empty");
      if (empty) empty.remove();
      box.appendChild(el);
      box.scrollTop = box.scrollHeight; // 与问答流同款：新内容滚进视野
      card = el;
      bind(el, null);
      return el;
    }
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML =
      `<div class="-modal-backdrop"></div><div class="-modal-box plan-box">` +
      `<div class="-modal-header" style="cursor:default"><span>${esc(T("plan.role"))}</span></div>` +
      `<div class="-modal-body">${inner}</div></div>`;
    document.body.appendChild(overlay);
    card = overlay;
    bind(overlay, overlay.querySelector(".-modal-backdrop"));
    return overlay;
  }

  /** 绑定卡片里的按钮（`data-act`）；重绘后的新卡片要重新调用。 */
  function bind(root, backdrop) {
    const on = (act, handler) => {
      const el = root.querySelector(`[data-act="${act}"]`);
      if (el) el.addEventListener("click", handler);
    };
    if (backdrop) backdrop.addEventListener("click", close);
    on("discard", () => close());
    on("repreview", () => root.__plan && open(root.__plan));
    on("undo", async () => {
      const btn = root.querySelector('[data-act="undo"]');
      if (btn) btn.disabled = true;
      showResult(await doUndo(root.__applyResult || {}, root.__plan || null));
    });
    on("apply", async () => {
      const plan = root.__plan;
      const preview = root.__preview;
      if (!plan || !preview) return;
      const checked = new Set(
        Array.from(root.querySelectorAll('input[type="checkbox"][data-op-id]:checked')).map((cb) => cb.dataset.opId)
      );
      const btn = root.querySelector('[data-act="apply"]');
      if (btn) {
        btn.disabled = true;
        btn.textContent = T("plan.applying");
      }
      const res = await doApply(plan, preview, checked);
      if (res && res.status === "ok") refreshOpenDoc(res.files);
      showResult(res);
    });
    const cbAll = Array.from(root.querySelectorAll('input[type="checkbox"][data-op-id]'));
    if (cbAll.length) {
      const applyBtn = root.querySelector('[data-act="apply"]');
      const sync = () => {
        const n = cbAll.filter((cb) => cb.checked).length;
        applyBtn.textContent = n ? T("plan.apply", { n }) : T("plan.needSelect");
        applyBtn.disabled = !n;
      };
      cbAll.forEach((cb) => cb.addEventListener("change", sync));
      sync();
    }
  }

  /** 预览失败 / 计划非法：只展示，**没有任何写**（后端在这一步之前不会建备份）。 */
  function showPreviewProblems(plan, preview) {
    const el = mount(
      `<div class="plan-summary">${esc(T("plan.rejected"))}</div>` +
        listBlock("plan-errors", T("plan.errorsTitle"), (preview && preview.errors) || []) +
        listBlock("plan-warnings", T("plan.warningsTitle"), (preview && preview.warnings) || []) +
        buttons([
          { act: "repreview", label: T("plan.rePreview"), title: T("plan.rePreviewTitle") },
          { act: "discard", label: T("plan.discard") },
        ])
    );
    el.__plan = plan;
    lastState = { kind: "problems", plan: plan, preview: preview };
  }

  function showResult(res, plan) {
    const r = res || { status: "error", code: "unknown" };
    const ok = r.status === "ok";
    const undone = ok && r.undone;
    const head = ok
      ? undone
        ? T("plan.undone")
        : T("plan.done", { n: (r.applied || []).length, txid: r.txid || "" })
      : T("plan.failed") + "：" + (r.message || r.code || "");
    const el = mount(
      `<div class="plan-summary" title="${esc(head)}">${esc(head)}</div>` +
        (r.rolled_back ? `<div class="plan-note">${esc(T("plan.rollback"))}</div>` : "") +
        listBlock("plan-errors", T("plan.errorsTitle"), r.errors) +
        listBlock("plan-warnings", T("plan.warningsTitle"), r.warnings) +
        buttons(
          (ok && !undone ? [{ act: "undo", label: T("plan.undo"), cls: "danger -btn--sm" }] : [])
            // 盘上变了（`stale_write`）⇒ 给一条明路：按**当前**磁盘内容重新 dry-run（§9 规则 ①）
            .concat(r.code === "stale_write" && plan ? [{ act: "repreview", label: T("plan.rePreview"), title: T("plan.rePreviewTitle") }] : [])
            .concat([{ act: "discard", label: T("plan.close") }])
        )
    );
    el.__plan = plan || null;
    el.__applyResult = r;
    lastState = { kind: "result", plan: plan || null, res: r };
  }

  function refreshOpenDoc(files) {
    const cur = A().state && A().state.currentPath;
    if (!cur) return;
    const norm = String(cur).replace(/\\/g, "/");
    if ((files || []).map(String).some((f) => f.replace(/\\/g, "/") === norm)) {
      A().openFile?.(cur, { skipNav: true });
    }
  }

  async function doUndo(applyResult, plan) {
    const res = await A()
      .call("agent_plan_undo", null, applyResult.session_id || "ui-plan", applyResult.txid || null)
      .catch((e) => ({ status: "error", code: "rpc_failed", message: String(e) }));
    if (res && res.status === "ok") {
      const files = (res.files || []).map((row) => (row && row.rel_path) || "");
      refreshOpenDoc(files);
      return {
        status: "ok",
        undone: true,
        txid: res.txid,
        applied: files.map((rel_path) => ({ rel_path })),
        verified: res.verified,
      };
    }
    return Object.assign({ status: "error", code: "undo_failed" }, res || {}, {
      message: (res && res.message) || T("plan.undoFail"),
    });
  }

  async function doApply(plan, preview, checked) {
    // 勾选 = **编译前**的选择：未勾的 op 从 plan.ops 去掉（后端仍然整批 all-or-nothing）
    const cropped = Object.assign({}, plan, { ops: (plan.ops || []).filter((op) => checked.has(String(op.op_id))) });
    // §9 规则 ②：人的当下操作最高 —— 编辑还没落盘就等一会儿，仍脏则**拒写**
    if (!(await waitForIdleEdits())) {
      return { status: "error", code: "editing", message: T("plan.dirty") };
    }
    WR().setBusy?.(true); // 写期间人机保存 deferIfBusy 重新入队（§9）
    try {
      return await A()
        .call("agent_plan_apply", cropped, null, null, preview.base_versions || null)
        .catch((e) => ({ status: "error", code: "rpc_failed", message: String(e) }));
    } finally {
      WR().setBusy?.(false);
    }
  }

  /**
   * 打开确认卡：先 dry-run 预览，再让人逐条勾选、确认后整批写入。
   * `opts.kbPath` 可显式指定库（省略 ⇒ 后端用当前已打开的库）。
   */
  async function open(plan, opts) {
    const o = opts || {};
    const preview = await A()
      .call("agent_plan_preview", plan, o.kbPath || null)
      .catch((e) => ({ status: "error", code: "rpc_failed", message: String(e) }));
    if (!preview || preview.status !== "ok" || !preview.previewed) {
      showPreviewProblems(plan, preview || {});
      return;
    }
    renderPreview(plan, preview);
  }

  /** 纯渲染（不打 RPC）：预览结果 → 卡片；也是切语言时那个"原地重绘"的目标。 */
  function renderPreview(plan, preview) {
    const files = preview.files || [];
    const total = files.reduce((n, f) => n + ((f.ops || []).length), 0);
    if (!total) {
      showResult({ status: "error", code: "empty_plan", message: T("plan.empty") }, plan);
      return;
    }
    const intent = String(preview.intent || "");
    const el = mount(
      `<div class="plan-summary" title="${esc(intent)}">${esc(T("plan.summary", { ops: total, files: files.length }))}</div>` +
        (intent ? clipped("plan-intent", intent) : "") +
        listBlock("plan-errors", T("plan.errorsTitle"), preview.errors) +
        listBlock("plan-warnings", T("plan.warningsTitle"), preview.warnings) +
        `<div class="plan-files">${fileBlocks(preview)}</div>` +
        buttons([
          { act: "apply", label: T("plan.apply", { n: total }), cls: "primary -btn--sm" },
          { act: "discard", label: T("plan.discard") },
        ])
    );
    el.__plan = plan;
    el.__preview = preview;
    lastState = { kind: "preview", plan: plan, preview: preview };
  }

  /** 便捷入口：直接喂一段 plan JSON 文本（临时入口与调试用）。 */
  function openFromText(text, opts) {
    let plan = null;
    try {
      plan = JSON.parse(text);
    } catch (e) {
      showResult({ status: "error", code: "bad_json", message: T("plan.badJson") + "：" + e.message });
      return;
    }
    open(plan, opts);
  }

  // ── 对话栏里的入口按钮（工具面接入前的临时入口：粘贴 plan JSON → 预览 → 卡片）──────

  function askForPlan() {
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML =
      `<div class="-modal-backdrop"></div><div class="-modal-box plan-box">` +
      `<div class="-modal-header" style="cursor:default"><span>${esc(T("plan.pasteTitle"))}</span></div>` +
      `<div class="-modal-body"><div class="plan-note">${esc(T("plan.pasteHint"))}</div>` +
      `<textarea class="plan-paste" spellcheck="false" rows="10" placeholder='{"v":1,"intent":"…","ops":[…]}'></textarea></div>` +
      `<div class="-modal-footer -btn-bar"><span class="-modal-footer-spacer"></span>` +
      `<button type="button" class="-btn" data-act="cancel">${esc(T("common.cancel"))}</button>` +
      `<button type="button" class="-btn primary" data-act="ok">${esc(T("plan.preview"))}</button>` +
      `</div></div>`;
    document.body.appendChild(overlay);
    const area = overlay.querySelector(".plan-paste");
    const done = (go) => {
      const text = area.value;
      overlay.remove();
      if (go) openFromText(text);
    };
    overlay.querySelector(".-modal-backdrop").addEventListener("click", () => done(false));
    overlay.querySelector('[data-act="cancel"]').addEventListener("click", () => done(false));
    overlay.querySelector('[data-act="ok"]').addEventListener("click", () => done(true));
    if (area) area.focus();
  }

  /** 在对话栏输入区装一个「计划」入口（幂等：已装过就复用）。 */
  function mountEntry() {
    const actions = document.querySelector(".-agent-composer-actions");
    if (!actions || actions.querySelector("#agent-plan-open")) return false;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "agent-plan-open";
    btn.className = "-btn secondary -btn--sm";
    btn.title = T("plan.entryTitle");
    btn.textContent = T("plan.entry");
    btn.addEventListener("click", askForPlan);
    actions.insertBefore(btn, actions.firstChild);
    return true;
  }

  global.MemoriaPlan = { open, openFromText, close, undo: doUndo, mountEntry, askForPlan, redraw };

  // 入口按钮要在**应用门面就绪之后**装（早装会拿不到 i18n ⇒ 按钮显示裸 key）；
  // 切语言时同步按钮文案并**原地重绘**已打开的卡片（不打 RPC）。
  global.MemoriaBridge?.onReady?.(() => {
    mountEntry();
    global.MemoriaI18n?.addRefresh?.(() => {
      const btn = document.getElementById("agent-plan-open");
      if (btn) {
        btn.textContent = T("plan.entry");
        btn.title = T("plan.entryTitle");
      }
      redraw();
    });
  });
})(typeof window !== "undefined" ? window : globalThis);
