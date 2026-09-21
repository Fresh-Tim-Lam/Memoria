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
 * 只依赖应用门面（`window.MemoriaApp`）与写守卫（`window.MemoriaWriteGuard`），**不改 app.js**。
 */
(function (global) {
  const A = () => global.MemoriaApp || {};
  const WR = () => global.MemoriaWriteGuard || {};
  const T = (k, p) => (A().T ? A().T(k, p) : k);
  const esc = (s) => (A().esc ? A().esc(s) : String(s == null ? "" : s));

  //: 等待"当前编辑落盘"的上限与轮询间隔（人机保存是 1s 防抖，故 3s 足够；再脏就是真的在编辑）
  const IDLE_WAIT_MS = 3000;
  const IDLE_POLL_MS = 150;

  let overlay = null; // 当前卡片（同一时刻只允许一张）

  function close() {
    if (overlay) {
      overlay.remove();
      overlay = null;
    }
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
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

  function opRow(opId, entry) {
    const rows = Array.isArray(entry.diff) ? entry.diff : [];
    const body = rows.length
      ? rows
          .map(
            (r) =>
              `<div class="plan-diff"><span class="plan-diff-del">- ${esc(r.before)}</span>` +
              `<span class="plan-diff-add">+ ${esc(r.after)}</span></div>`
          )
          .join("")
      : `<div class="plan-diff-none">${esc(T("plan.noDiff"))}</div>`;
    return (
      `<label class="plan-op"><input type="checkbox" data-op-id="${esc(opId)}" checked>` +
      `<span class="plan-op-name">${esc(opLabel(entry))}</span>` +
      `<span class="plan-op-id">${esc(opId)}</span></label>` +
      `<div class="plan-op-body">${body}</div>`
    );
  }

  function fileBlocks(preview) {
    return (preview.files || [])
      .map((file) => {
        const ops = (file.ops || []).map((entry) => opRow(entry.op_id, entry)).join("");
        return `<div class="plan-file"><div class="plan-file-path">${esc(file.file)}</div>${ops}</div>`;
      })
      .join("");
  }

  function errLines(errors) {
    if (!errors || !errors.length) return "";
    const items = errors
      .map((e) => `<li>[${esc(e.op_id || "-")}] ${esc(e.message || e.code || "")}</li>`)
      .join("");
    return `<div class="plan-errors"><div class="plan-errors-title">${esc(T("plan.errorsTitle"))}</div><ul>${items}</ul></div>`;
  }

  function warnLines(warnings) {
    if (!warnings || !warnings.length) return "";
    const items = warnings
      .map((w) => `<li>[${esc(w.op_id || "-")}] ${esc(w.message || w.code || "")}</li>`)
      .join("");
    return `<div class="plan-warnings"><ul>${items}</ul></div>`;
  }

  function mount(html) {
    close();
    overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
    const box = overlay.querySelector(".-modal-box");
    const cancel = overlay.querySelector('[data-act="cancel"]');
    const backdrop = overlay.querySelector(".-modal-backdrop");
    if (cancel) cancel.addEventListener("click", close);
    if (backdrop) backdrop.addEventListener("click", close);
    return { box, overlay };
  }

  /** 预览失败 / 计划非法：只展示，**没有任何写**（后端在这一步之前不会建备份）。 */
  function showPreviewProblems(plan, preview) {
    const { box } = mount(
      `<div class="-modal-backdrop"></div><div class="-modal-box plan-box">
         <div class="-modal-header" style="cursor:default"><span>${esc(T("plan.title"))}</span></div>
         <div class="-modal-body">${errLines(preview.errors)}${warnLines(preview.warnings)}</div>
         <div class="-modal-footer -btn-bar"><span class="-modal-footer-spacer"></span>
           <button type="button" class="-btn" data-act="cancel">${esc(T("common.cancel"))}</button>
           <button type="button" class="-btn primary" data-act="repreview">${esc(T("plan.rePreview"))}</button>
         </div>
       </div>`
    );
    const again = box.querySelector('[data-act="repreview"]');
    if (again) again.addEventListener("click", () => open(plan));
  }

  function showResult(result, plan) {
    const res = result || { status: "error", code: "unknown" };
    const ok = res.status === "ok";
    const undone = ok && res.undone;
    const title = ok ? (undone ? T("plan.undoneTitle") : T("plan.doneTitle")) : T("plan.failedTitle");
    const head = ok
      ? undone
        ? T("plan.undone")
        : T("plan.done", { n: (res.applied || []).length, txid: res.txid || "" })
      : T("plan.failed") + "：" + (res.message || res.code || "");
    const rollback = res.rolled_back ? `<div class="plan-note">${esc(T("plan.rollback"))}</div>` : "";
    const { box } = mount(
      `<div class="-modal-backdrop"></div><div class="-modal-box plan-box">
         <div class="-modal-header" style="cursor:default"><span>${esc(title)}</span></div>
         <div class="-modal-body">
           <div class="plan-summary">${esc(head)}</div>${rollback}
           ${errLines(res.errors)}${warnLines(res.warnings)}
         </div>
         <div class="-modal-footer -btn-bar"><span class="-modal-footer-spacer"></span>
           ${ok && !undone ? `<button type="button" class="-btn danger" data-act="undo">${esc(T("plan.undo"))}</button>` : ""}
           <button type="button" class="-btn" data-act="cancel">${esc(T("plan.close"))}</button>
         </div>
       </div>`
    );
    const undo = box.querySelector('[data-act="undo"]');
    if (undo) {
      undo.addEventListener("click", async () => {
        undo.disabled = true;
        showResult(await doUndo(res, plan), plan);
      });
    }
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
    return Object.assign({ status: "error", code: "undo_failed" }, res || {}, { message: (res && res.message) || T("plan.undoFail") });
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
    const files = preview.files || [];
    const total = files.reduce((n, f) => n + ((f.ops || []).length), 0);
    if (!total) {
      showResult({ status: "error", code: "empty_plan", message: T("plan.empty") }, plan);
      return;
    }
    const { box } = mount(
      `<div class="-modal-backdrop"></div><div class="-modal-box plan-box">
         <div class="-modal-header" style="cursor:default"><span>${esc(T("plan.title"))} · ${esc(preview.intent || "")}</span></div>
         <div class="-modal-body">
           <div class="plan-summary">${esc(T("plan.summary", { ops: total, files: files.length }))}</div>
           ${errLines(preview.errors)}${warnLines(preview.warnings)}
           <div class="plan-files">${fileBlocks(preview)}</div>
         </div>
         <div class="-modal-footer -btn-bar"><span class="-modal-footer-spacer"></span>
           <button type="button" class="-btn" data-act="cancel">${esc(T("common.cancel"))}</button>
           <button type="button" class="-btn primary" data-act="apply"></button>
         </div>
       </div>`
    );
    const applyBtn = box.querySelector('[data-act="apply"]');
    const syncBtn = () => {
      const n = box.querySelectorAll('input[type="checkbox"][data-op-id]:checked').length;
      applyBtn.textContent = n ? T("plan.apply", { n }) : T("plan.needSelect");
      applyBtn.disabled = !n;
    };
    box.querySelectorAll('input[type="checkbox"][data-op-id]').forEach((cb) => cb.addEventListener("change", syncBtn));
    syncBtn();
    applyBtn.addEventListener("click", async () => {
      const checked = new Set(
        Array.from(box.querySelectorAll('input[type="checkbox"][data-op-id]:checked')).map((cb) => cb.dataset.opId)
      );
      applyBtn.disabled = true;
      applyBtn.textContent = T("plan.applying");
      const res = await doApply(plan, preview, checked);
      if (res && res.status === "ok") refreshOpenDoc(res.files);
      showResult(res || { status: "error" }, plan);
    });
  }

  /** 便捷入口：直接喂一段 plan JSON 文本（调试/手工验证用）。 */
  function openFromText(text, opts) {
    let plan = null;
    try {
      plan = JSON.parse(text);
    } catch (e) {
      showResult({ status: "error", code: "bad_json", message: String(e) }, null);
      return;
    }
    open(plan, opts);
  }

  global.MemoriaPlan = { open, openFromText, close, undo: doUndo };
})(typeof window !== "undefined" ? window : globalThis);
