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
 * 5. **可撤销**：成功后给出「撤销一步 / 重做一步」→ `agent_plan_undo_step` / `agent_plan_redo`
 *    （撤销用该批 pre-image、重做用写后镜像；覆盖前自动兜底，因此不会被"外部改动"拦下）。
 *
 * **卡片放在对话栏里**（与问答/工具调用同一条流）：渲染进 `#agent-messages` 成为一条聊天项，
 * 而不是弹窗盖住界面 —— 计划是"智能体提出、人确认"的东西，它就属于那条对话。
 * **一份计划一张卡，状态在原地推进**：预览 → （点「应用」）→「已写入 …· 撤销这一批」→（点撤销）→
 * 「已撤销」；确认之后**不再留一张还能点的旧卡**（否则会诱导重复应用）。新计划才追加新卡。
 * 对话栏不可用时（面板收起 / 没有对话栏）自动**回落成弹窗**，绝不出现"点了没反应"。
 *
 * **计划从哪来**（两条路，同一张卡）：
 * ① **智能体自己提**：模型调 `propose_write` 工具（只产 plan、不落盘）⇒ 后端排进进程内信箱 ⇒
 *    前端在每轮问答收尾（`agent_ask_poll` 报 done/error）顺手 `agent_plan_pending` 取一次；
 * ② 人工兜底：对话栏输入区的「计划」按钮（本模块自己装的入口，不改 `app.js` / `agent-panel.js` /
 *    `index.html` ⇒ 既有行号锚点零漂移），粘贴 plan JSON 预览。
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

  let cards = []; // 已挂出的卡片节点（对话栏里的聊天项，或回落弹窗），按追加顺序 = 对话流的自然顺序
  let states = []; // 与 `cards` 平行的重绘状态（切语言时原地重建，**不再打 RPC**）

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

  /** 关掉本模块挂出的**所有**卡片（`卡片的「放弃」按钮只移除自己`）。 */
  function close() {
    cards.forEach((el) => el.remove());
    cards = [];
    states = [];
  }

  function removeCard(el) {
    const index = cards.indexOf(el);
    if (index >= 0) {
      cards.splice(index, 1);
      states.splice(index, 1);
    }
    el.remove();
  }

  /** 切语言时原地重建已挂出的卡片（顺序不变；纯前端重排，不打 RPC）。 */
  function redraw() {
    if (!cards.length) return;
    const keep = states.slice();
    close();
    keep.forEach(renderState);
  }

  /** 角色标签：人工确认的卡是「计划确认」；agent **已经写完**的回执是「已写入」。 */
  function roleLabel(state) {
    return state && state.res ? T("plan.doneTitle") : T("plan.role");
  }

  /** 按状态重画一张卡（切语言用；不带 `into` ⇒ 追加成新的一条，顺序由 `keep` 保证）。 */
  function renderState(state) {
    if (state.kind === "preview") renderPreview(state.plan, state.preview);
    else if (state.kind === "problems") showPreviewProblems(state.plan, state.preview);
    else showResult(state.res, state.plan);
  }

  /**
   * 把某张卡**原地换内容**（一张卡一个计划：预览 → 已写入 → 已撤销）：位置留在对话里，
   * 但旧的"应用"按钮随之消失（避免同一批被重复点；`base_versions` 也会拦，但界面不该留坑）。
   */
  function renderInto(el, inner, state) {
    const index = cards.indexOf(el);
    if (index >= 0) states[index] = state;
    el.innerHTML = `<span class="-agent-msg-role">${esc(roleLabel(state))}</span>${inner}`;
    bind(el, null);
    el.__plan = state.plan || null;
    el.__preview = state.preview || null;
    el.__applyResult = state.res || null;
    const box = chatBox();
    if (box && el.parentElement === box) box.scrollTop = box.scrollHeight;
    return el;
  }

  /** 卡片内容的统一出口：`into` 给了就原地换，否则追加成新的一条。 */
  function place(inner, state, into) {
    if (into) return renderInto(into, inner, state);
    const el = mount(inner, state);
    el.__plan = state.plan || null;
    el.__preview = state.preview || null;
    el.__applyResult = state.res || null;
    return el;
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

  /** 一行 diff：`before` 有就是删除行、`after` 有就是新增行（改正文时只来一边，包裹时两边都有）。 */
  function diffRow(row) {
    const where = row && row.line != null ? "L" + row.line + " " : "";
    let out = "";
    if (row && row.before != null) out += clipped("plan-diff-line plan-diff-del", "- " + where + row.before);
    if (row && row.after != null) out += clipped("plan-diff-line plan-diff-add", "+ " + where + row.after);
    return out;
  }

  function opRow(entry) {
    const rows = Array.isArray(entry.diff) ? entry.diff : [];
    const body = rows.length
      ? rows.map(diffRow).join("")
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
   * 把一段卡片内容挂到**对话栏**（成一条聊天项，**追加**不替换 —— 卡片是对话流的一部分）；
   * 对话栏不可用时回落成弹窗。`state` 是它的重绘状态（切语言用）。返回可交互的根元素。
   */
  function mount(inner, state) {
    const box = chatBox();
    if (box) {
      const el = document.createElement("div");
      el.className = "-agent-msg -agent-msg--assistant -agent-plan-msg";
      el.innerHTML = `<span class="-agent-msg-role">${esc(roleLabel(state))}</span>${inner}`;
      const empty = box.querySelector(".-agent-empty");
      if (empty) empty.remove();
      box.appendChild(el);
      box.scrollTop = box.scrollHeight; // 与问答流同款：新内容滚进视野
      cards.push(el);
      states.push(state);
      bind(el, null);
      return el;
    }
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML =
      `<div class="-modal-backdrop"></div><div class="-modal-box plan-box">` +
      `<div class="-modal-header" style="cursor:default"><span>${esc(roleLabel(state))}</span></div>` +
      `<div class="-modal-body">${inner}</div></div>`;
    document.body.appendChild(overlay);
    cards.push(overlay);
    states.push(state);
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
    on("discard", () => removeCard(root));
    on("repreview", () => root.__plan && open(root.__plan, { into: root }));
    // 撤销：**撤销一步**（栈语义）。手动预览卡上留一个就在回执旁的快捷入口，**与顶部状态栏同一语义**；
    // 状态栏才是"常驻 + 显示栈位置 + 提供重做"的那个（见 `afterStep()` / `publishWriteState()`）。
    on("undo", async () => {
      const btn = root.querySelector('[data-act="undo"]');
      if (btn) btn.disabled = true;
      const done = await undoWrite(root.__session || null);
      if (!done && btn) btn.disabled = false;
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
      const res = await doApply(plan, preview, checked, root.__session || null);
      if (res && res.status === "ok") syncAfterWrite(res.files);
      showResult(res, plan, root); // 原地换成「已写入 …」：旧的应用按钮随之消失，不会重复点
      // 手动应用也要把回执交给**顶部状态栏**：否则这条路径既看不到栈位置、也**没有重做入口**
      // （人 2026-09-21：「撤销之后栈状态栏就没了，我无法重做」—— 同一条栈，两个路径都得接上）。
      publishWriteState({ preview: preview, result: res || {} }, root.__session || null);
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

  /** 结果内容：已写入 / 失败（手动预览卡用；对话栏那条走"写入状态条"，见 `publishWriteState()`）。
   *  `stale_write` 时给「重新预览」这条明路（§9 规则 ①）。 */
  function resultInner(res, plan) {
    const r = res || { status: "error", code: "unknown" };
    const ok = r.status === "ok";
    const head = ok
      ? T("plan.done", { n: (r.applied || []).length, txid: r.txid || "" })
      : T("plan.failed") + "：" + (r.message || r.code || "");
    return (
      `<div class="plan-summary" title="${esc(head)}">${esc(head)}</div>` +
      (r.rolled_back ? `<div class="plan-note">${esc(T("plan.rollback"))}</div>` : "") +
      listBlock("plan-errors", T("plan.errorsTitle"), r.errors) +
      listBlock("plan-warnings", T("plan.warningsTitle"), r.warnings) +
      buttons(
        (ok ? [{ act: "undo", label: T("plan.undo"), title: T("plan.undoTitle"), cls: "danger -btn--sm" }] : [])
          .concat(
            r.code === "stale_write" && plan
              ? [{ act: "repreview", label: T("plan.rePreview"), title: T("plan.rePreviewTitle") }]
              : []
          )
          .concat([{ act: "discard", label: T("plan.close") }])
      )
    );
  }

  /** 预览失败 / 计划非法：只展示，**没有任何写**（后端在这一步之前不会建备份）。 */
  function showPreviewProblems(plan, preview, into) {
    return place(
      `<div class="plan-summary">${esc(T("plan.rejected"))}</div>` +
        listBlock("plan-errors", T("plan.errorsTitle"), (preview && preview.errors) || []) +
        listBlock("plan-warnings", T("plan.warningsTitle"), (preview && preview.warnings) || []) +
        buttons([
          { act: "repreview", label: T("plan.rePreview"), title: T("plan.rePreviewTitle") },
          { act: "discard", label: T("plan.discard") },
        ]),
      { kind: "problems", plan: plan, preview: preview },
      into
    );
  }

  function showResult(res, plan, into) {
    return place(resultInner(res, plan), { kind: "result", plan: plan || null, res: res || {} }, into);
  }

  /** 写入/撤销之后的**界面同步**（人 2026-09-21："agent 对话之后自动刷新渲染"）：让各视图跟上盘面，
   *  不必手动重开文件或切页。四件事，逐条独立 try（任一项失败都不该影响其它项与卡片结果）：
   *  ① **文件树** —— 新建 / 改名 / 删除会改变它（`refreshFiles`）；
   *  ② **当前打开的文件**（只有它**被写**时才动）—— 重载 + 重绘编辑器 / 预览 / KP 列表
   *     （走 `openFile(skipNav)`，与人在树里点开同一条路 ⇒ 不会多插一条导航历史）；
   *  ③ **待确认摘要**（`pending.json` 变了）；
   *  ④ **图谱**（sidecar / links 变了 ⇒ 边也变了）。
   *  被写的**不是**当前文件时**不动编辑器** —— 不打断人正在看的东西。 */
  async function syncAfterWrite(files) {
    const app = A();
    const rels = (files || []).map((f) => String(f).replace(/\\/g, "/")).filter(Boolean);
    if (!rels.length) return;
    // 与 `agent-panel.refreshAfterTurn()` 的 **1.5s 去重窗口**共用（人 2026-09-21：「每次对话结束
    // memoria 没有刷新，程序上先挂一个刷新」—— 那个**无条件**收尾刷新在 agent-panel 侧）。同一回合里
    // 两者谁先跑到都不该把图谱连算两遍 ⇒ 视图可跳；但下面那条**精确**的"确知被写就重开当前文件"
    // 永远执行（自动写库后编辑器必须看到新内容）。
    const fresh = Date.now() - (Number(app.__kbRefreshAt) || 0) < 1500;
    if (!fresh) {
      try {
        await app.refreshFiles?.();
      } catch (e) {
        /* 同步失败不阻塞结果展示 */
      }
    }
    const cur = app.state && app.state.currentPath;
    if (cur && rels.includes(String(cur).replace(/\\/g, "/"))) {
      try {
        await app.openFile?.(cur, { skipNav: true });
      } catch (e) {
        /* 同上 */
      }
    }
    if (!fresh) {
      try {
        await app.refreshKbPendingSummary?.();
      } catch (e) {
        /* 同上 */
      }
      try {
        await app.loadGraphData?.();
      } catch (e) {
        /* 同上 */
      }
    }
    app.__kbRefreshAt = Date.now();
  }

  // 最近一次写入的文件明细（状态栏展开态用）。撤销 / 重做一步之后**仍显示它** ——
  // 后端栈里只有"每步改了几个文件"的计数，没有逐文件明细（明细只在 apply 回执里给一次）。
  let lastWriteFiles = [];

  /** 取**会话栈**现状（给状态栏显示"第几步 / 共几步"与按钮可用性）；失败回 `null`。 */
  async function refreshStack(sessionId) {
    const sid = String(sessionId || "").trim();
    if (!sid) return null;
    const res = await A()
      .call("agent_plan_stack", null, sid)
      .catch(() => null);
    return res && res.status === "ok" ? res : null;
  }

  /** 撤销 / 重做**一步**成功后的统一收尾：各视图跟上盘面 → 重取栈 → 重绘状态栏（按钮可用性随之更新）。
   *
   *  **绝不能**拿"指针到 −1"当"该收起来"（人 2026-09-21 报：「撤销之后栈状态栏就没了，我无法重做」）：
   *  撤到最底时步骤**全都还在栈里**（`total > 0`）且 `can_redo === true` —— 收起状态栏等于把重做入口
   *  一起收掉。⇒ **只要栈里还有步骤就照常显示**，撤销 / 重做的可用性交给 `can_undo` / `can_redo`；
   *  只有**栈里真的没有步骤**（`total === 0`）才清掉状态栏（没有状态可展示，也没有可撤可重做的东西）。 */
  async function afterStep(res, sessionId) {
    syncAfterWrite((res.files || []).map((row) => (row && row.rel_path) || ""));
    const stack = await refreshStack(sessionId);
    const panel = global.MemoriaAgentPanel;
    if (stack && !stack.total) {
      panel?.setWriteState?.(null); // 全会话没有写入步骤 ⇒ 无可展示（也不留「已撤销」这种假象）
      return true;
    }
    // 展开态的明细沿用**这次写入的清单**（`preview.files`，见 `publishWriteState()`）：`res.files` 是
    // 这一步真正写回的文件集（含 `manifest.yaml` / `pending.json` 等派生文件）⇒ 同一个动作的计数会
    // 从「1 个文件」跳成「4 个文件」（L4 实测到），对人没有意义。逐**步**的差异去展开态的栈轨迹看。
    panel?.setWriteState?.({
      files: lastWriteFiles,
      failed: false,
      txid: (res && res.txid) || "",
      stack: stack,
      onUndo: () => undoWrite(sessionId),
      onRedo: () => redoWrite(sessionId),
    });
    return true;
  }

  /** **撤销一步**（栈语义，人 2026-09-21 定稿）：指针 −1，用该批 **pre-image** 写回。
   *  覆盖前由后端**自动兜底**（把当前那版另存 `manual-force` 批次）⇒ 覆盖 ≠ 丢数据。
   *  返回 `true` = 已完成（调用方据此复位按钮）。 */
  async function undoWrite(sessionId) {
    const sid = String(sessionId || "ui-plan");
    const res = await A()
      .call("agent_plan_undo_step", null, sid)
      .catch((e) => ({ status: "error", code: "rpc_failed", message: String(e) }));
    if (res && res.status === "ok") {
      A().showFlashInfo?.(T("agent.undoDone"));
      return afterStep(res, sid);
    }
    A().showFlashError?.(T("agent.undoFail"), (res && res.message) || "");
    return false;
  }

  /** **重做一步**：指针 +1，用该批**写后镜像**写回；该步没有写后镜像时后端如实回 `no_after`。 */
  async function redoWrite(sessionId) {
    const sid = String(sessionId || "ui-plan");
    const res = await A()
      .call("agent_plan_redo", null, sid)
      .catch((e) => ({ status: "error", code: "rpc_failed", message: String(e) }));
    if (res && res.status === "ok") {
      A().showFlashInfo?.(T("agent.redoDone"));
      return afterStep(res, sid);
    }
    A().showFlashError?.(T("agent.redoFail"), (res && res.message) || "");
    return false;
  }

  /** 把"刚写完什么"交给 `agent-panel`，渲染成**顶部副标题行**的写入状态栏（含撤销一步 / 重做一步）。
   *  人定稿（2026-09-21）：状态栏在 `.-agent-subhead`；它是**常驻 + 显示栈位置 + 提供重做**的那个入口。
   *  会话 id 的解析顺序 = 调用方给的 → 记录里的 → **回执里的**（后端 apply 会带回它解析后的 id）→
   *  `ui-plan`（后端 `agent_plan_apply` 在省略 session_id 时的伪会话，见 `ui.py`）—— 少这一环就会
   *  "查不到栈 ⇒ 状态栏没有栈位置、也没有可用的重做按钮"。 */
  async function publishWriteState(rec, sessionId) {
    const preview = (rec && rec.preview) || null;
    const result = (rec && rec.result) || {};
    const sid = sessionId || (rec && rec.session_id) || result.session_id || "ui-plan";
    const panel = global.MemoriaAgentPanel;
    if (!panel || typeof panel.setWriteState !== "function") {
      // 面板模块没加载 / 接口没暴露 ⇒ 状态栏与撤销入口都不会出现：必须**可见**（曾经静默失过一次，
      // 表现是"agent 回话下面只有复制、没有撤销"，且控制台一片干净）
      console.warn("[plan] MemoriaAgentPanel.setWriteState 不可用：本次写入的回执无法展示");
      return;
    }
    lastWriteFiles = ((preview && preview.files) || []).map((row) => ({
      path: String((row && row.file) || ""),
      lines: (((row && row.lines_changed) || []).length),
    }));
    // 栈位置：写入成功才查（失败没有栈可谈）
    const stack = result.status === "ok" ? await refreshStack(sid) : null;
    panel.setWriteState({
      files: lastWriteFiles,
      failed: result.status !== "ok",
      txid: result.txid || "",
      stack: stack,
      onUndo: () => undoWrite(sid),
      onRedo: () => redoWrite(sid),
    });
  }

  async function doApply(plan, preview, checked, sessionId) {
    // 勾选 = **编译前**的选择：未勾的 op 从 plan.ops 去掉（后端仍然整批 all-or-nothing）
    const cropped = Object.assign({}, plan, { ops: (plan.ops || []).filter((op) => checked.has(String(op.op_id))) });
    // §9 规则 ②：人的当下操作最高 —— 编辑还没落盘就等一会儿，仍脏则**拒写**
    if (!(await waitForIdleEdits())) {
      return { status: "error", code: "editing", message: T("plan.dirty") };
    }
    WR().setBusy?.(true); // 写期间人机保存 deferIfBusy 重新入队（§9）
    try {
      return await A()
        .call("agent_plan_apply", cropped, null, sessionId || null, preview.base_versions || null)
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
      const bad = showPreviewProblems(plan, preview || {}, o.into);
      if (bad) bad.__session = o.sessionId || null;
      return;
    }
    const el = renderPreview(plan, preview, o.into);
    // 这批是谁提的 ⇒ 应用时把**同一个会话 id** 带上：写入审计落在**那次对话**里，
    // 而不是落到 `ui-plan` 伪会话（审计要能跟"谁提的、谁确认的"对上）。
    if (el) el.__session = o.sessionId || null;
  }

  /** 纯渲染（不打 RPC）：预览结果 → 卡片；也是切语言时那个"原地重绘"的目标。 */
  function renderPreview(plan, preview, into) {
    const files = preview.files || [];
    const total = files.reduce((n, f) => n + ((f.ops || []).length), 0);
    if (!total) {
      showResult({ status: "error", code: "empty_plan", message: T("plan.empty") }, plan, into);
      return;
    }
    const intent = String(preview.intent || "");
    return place(
      `<div class="plan-summary" title="${esc(intent)}">${esc(T("plan.summary", { ops: total, files: files.length }))}</div>` +
        (intent ? clipped("plan-intent", intent) : "") +
        listBlock("plan-errors", T("plan.errorsTitle"), preview.errors) +
        listBlock("plan-warnings", T("plan.warningsTitle"), preview.warnings) +
        `<div class="plan-files">${fileBlocks(preview)}</div>` +
        buttons([
          { act: "apply", label: T("plan.apply", { n: total }), cls: "primary -btn--sm" },
          { act: "discard", label: T("plan.discard") },
        ]),
      { kind: "preview", plan: plan, preview: preview },
      into
    );
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

  // ── 智能体写完之后：把"写了什么"交给对话栏的**写入状态条**（人定稿 2026-09-21）──────────
  //    不再单独插一张回执卡 —— 撤销按钮只在**最新一条回复下方**出现（由 `agent-panel.js` 渲染）。

  /** 一条写入回执 ⇒ 状态条（`MemoriaAgentPanel.setWriteState()`）。 */
  function publishRecord(rec, sessionId) {
    if (!rec || !rec.plan) return;
    publishWriteState(rec, sessionId || rec.session_id || null);
  }

  /** 取走后端排队的**写回执**并发布到对话栏（取走即清空；返回条数）。
   *  `sessionId` 由调用方（问答收尾那一次 poll）带进来 ⇒ 撤销时写入审计能落回**这次对话**。 */
  async function drainProposals(sessionId) {
    const res = await A()
      .call("agent_plan_pending", null)
      .catch(() => null);
    const records = (res && res.status === "ok" && res.records) || [];
    const sid = sessionId || null;
    records.forEach((rec) => publishRecord(rec, sid));
    return records.length;
  }

  /**
   * 包装门面 `call`：**只在**问答收尾那一次（`agent_ask_poll` 报 done/error）顺手取一次提议。
   *
   * 为什么包这里：工具面产 plan 之后没有别的"推送"通道，而前端本来就在轮询 `agent_ask_poll`
   * （轮次结束才停）—— 借它一次往返，既不用新增轮询循环，也不用改 `agent-panel.js`。
   * 包装门面 `call` 是本仓既有做法（`agent-panel.js` 同样包它以追加思考游标）。
   */
  function installProposalDrain() {
    const app = global.MemoriaApp;
    if (!app || app.__planDrain || typeof app.call !== "function") return false;
    const inner = app.call;
    app.call = function (fn) {
      const pending = inner.apply(this, arguments);
      if (fn !== "agent_ask_poll" || !pending || typeof pending.then !== "function") return pending;
      return pending.then((res) => {
        if (res && (res.status === "done" || res.status === "error")) {
          drainProposals(res.session_id); // 这批提议属于**这次对话** ⇒ 审计也落这里
        }
        return res;
      });
    };
    app.__planDrain = true;
    return true;
  }

  global.MemoriaPlan = {
    open,
    openFromText,
    close,
    undo: undoWrite,
    mountEntry,
    askForPlan,
    redraw,
    drainProposals,
  };

  // 入口按钮要在**应用门面就绪之后**装（早装会拿不到 i18n ⇒ 按钮显示裸 key）；
  // 切语言时同步按钮文案并**原地重建**已挂出的卡片（不打 RPC）。
  global.MemoriaBridge?.onReady?.(() => {
    mountEntry();
    installProposalDrain();
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
