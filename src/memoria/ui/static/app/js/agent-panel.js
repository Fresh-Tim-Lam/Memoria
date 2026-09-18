/**
 * 应用内对话面板（**右侧独立停靠栏** `#-agent-dock`，M1 首版曾挂在左栏第 4 页签）。
 *
 * 自包含：DOM/事件绑定全部由本模块 init() 完成，不依赖 app.js 的 bindEvents：
 *   - 顶栏 `#btn-agent` / 浮动 `#agent-dock-collapse-btn` → 停靠栏展开·收起
 *   - `#agent-dock-resizer` 向左拖拽调宽（rem）→ 落盘 `layout.agentDockWidth`
 *   - `#agent-settings-toggle` 折叠设置区；`#agent-save-config` 保存端点配置
 *   - `#agent-net-toggle`「出网」开关（写 `config/agent.json` 的 enabled）
 *   - `#agent-input` Enter 发送 / Shift+Enter 换行；`#agent-send` 发送
 *   - `#agent-stop`「停止」（**真取消**：调 `agent_ask_cancel`，保留已生成的部分文本）
 *   - `#agent-clear` 清空对话（= 开新会话，并顺带取消在飞作业）
 *   - `#agent-history` 下拉恢复历史会话；`#agent-history-delete` 删除选中会话（两次点击确认）
 *   - `#agent-messages` 内锚点点击 → 跳转文件:行号
 *   - MemoriaI18n.addRefresh → 语言切换后重绘消息/状态/历史选项/折叠按钮（静态节点由 i18n 引擎刷）
 *
 * **多轮续聊（M1c）**：本模块自持 `sessionId`（首次提问为 null）。`agent_ask_poll`
 * 返回的 `session_id` 存下来，之后的提问都带上它 ⇒ 后端按会话文件回放历史，形成多轮；
 * 「清空对话」= 把 `sessionId` 重置为 null（开新会话，旧会话已在磁盘上、进历史列表）。
 * `sessionKb` 记录该会话所属知识库，换库即作废（避免把 A 库的会话 id 带到 B 库）。
 *
 * **停止 = 真取消（M1 收尾）**：`stop()` 递增 `epoch` 作废在飞回调 → 调
 * `agent_ask_cancel(job_id)`（后端置取消令牌，停止消费模型流并**立即**释放单飞 busy）
 * → 保留已生成的部分文本为助手气泡并标注「（已停止）」、状态行写「已停止」、
 * 停止轮询。**不再丢弃结果**（旧版「忽略本次」的语义已废除）。停止后立刻可再提问。
 *
 * **世代号（epoch）作废（M1 收尾）**：每次提问递增模块级 `epoch`，在飞作业记住自己的
 * epoch；提交/轮询回调只有「epoch 仍是最新」时才允许写回任何面板状态（`sessionId`、
 * 气泡、状态行、锚点）。「清空对话」递增 `epoch` ⇒ 在飞结果一律作废（停止轮询、
 * 不写回会话 id）——修掉"生成中点清空后，已作废会话的 `session_id` 又被
 * 写回、下一句续到上一轮"的缺陷。作废后用户立刻再提问不受影响（新 epoch 正常写回）。
 * 生成中**不**禁用「清空」：允许清空，同时**顺带取消**后端作业（避免白烧 token）。
 *
 * **会话历史（M1c）**：`#agent-history` 由 `agent_sessions_list` 填充（按修改时间倒序，
 * 最多 30 条），选中某条 → `agent_session_load` 把消息灌进气泡区并把 `sessionId`
 * 设为该会话（下一句即续聊）。列表/载入是**只读**；`agent_session_delete` 是
 * **本产品首次允许写知识库**（仅限会话目录 `.memoria/agent/sessions/<id>.jsonl`，
 * 见 10 篇 §2.15）。删除用**两次点击确认**（`#agent-history-delete`），不弹窗。
 *
 * **恢复上次会话（M1 收尾）**：磁盘偏好 `config/ui-settings.json` 的**顶层** `agent`
 * 段存 `lastSessionId`（提问成功/载入/恢复时写、清空时置空）。面板打开或**切换知识库**
 * 时若该会话文件仍存在即自动载入（下一句即续聊）；不存在则**静默忽略**（不报错、
 * 不提示）。落盘见 saveAgentPrefs()——与 saveDockLayout() 同理，**必须先读旧值再合并
 * 写回**（后端 `save_ui_settings` 是顶层浅合并，不能覆盖 `layout` 段）。
 *
 * 布局持久化（`config/ui-settings.json` 的 `layout` 段：`agentDockWidth` /
 * `agentDockCollapsed`）见 saveDockLayout()——**必须先读旧 layout 再整体写回**，
 * 否则会抹掉 `layout.sidebarWidth`（后端是顶层浅合并）。
 *
 * 宽度分「**期望宽度**」与「**生效宽度**」（见 applyDockLayout()）：
 * `agentDockWidth` 是期望宽度（只在拖拽/显式操作时写盘）；生效宽度按可用空间实时算出
 * ——文档区（`#content`）保底 `CONTENT_MIN_PX=360`，不够就让 dock 先缩到 16rem、
 * 再整体**临时自动隐藏**（加 `-agent-dock--auto-hidden`，不写盘、窗口变宽自动还原）。
 *
 * 与后端的分工（见 `presentation/api/ui.py` 的 9 个 RPC）：
 *   `agent_get_config` / `agent_save_config` / `agent_ask_start` / `agent_ask_poll` /
 *   `agent_ask_cancel` / `agent_sessions_list` / `agent_session_load` /
 *   `agent_session_delete` / （`get_ui_settings` / `save_ui_settings` 为通用偏好 RPC）。
 * 伪流式：`agent_ask_start` 提交即返回 job_id，本模块每 250ms 轮询
 * `agent_ask_poll(job_id, cursor)` 取 `delta`（后端 worker 线程跑同步 `ask()`，
 * 增量来自 `ask(on_text=...)`），从而得到打字机效果；轮询期间状态行带「生成中… Ns」
 * 计时（每秒刷新），缓解长等待的"像卡死"观感。
 *
 * 依赖 window.MemoriaApp（app.js 门面）：state / call / T / esc /
 * showFlashError / showFlashInfo / openFile。
 * 依赖 window.MemoriaI18n（语言包刷新钩子，可选）。
 */
window.MemoriaAgentPanel = (function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const A = () => window.MemoriaApp || {};

  // app.js 导出 state 为同一对象引用（永不整体替换），捕获一次后属性读写均实时可见
  const state = A().state || {};

  function T(key, params) {
    const a = A();
    return a.T ? a.T(key, params) : key;
  }
  function esc(s) {
    const a = A();
    return a.esc ? a.esc(s) : String(s == null ? "" : s);
  }
  const call = (...args) => {
    const a = A();
    return a.call ? a.call(...args) : undefined;
  };
  const showFlashError = (...args) => {
    A().showFlashError?.(...args);
  };
  const showFlashInfo = (...args) => {
    A().showFlashInfo?.(...args);
  };
  const openFile = (relPath, opts) => A().openFile?.(relPath, opts);

  // ── 轮询参数（与 kb-check.js 的静默作业同套路）────────────────────────
  const POLL_INTERVAL_MS = 250;
  const POLL_TIMEOUT_MS = 300000; // 5 分钟兜底；模型长回答不会被误判超时

  // 答案里的 `文件:行号`（允许被反引号包裹；路径不允许空白/引号/括号/冒号）
  const ANCHOR_RE = /`?([^\s`"'<>()[\]:]+\.md):(\d+)`?/g;

  // 后端稳定 code → 文案键；未登记的 code 回退后端 message（i18n.md §5.1 口径）
  const ERR_KEYS = {
    no_kb: "agent.err.no_kb",
    empty_question: "agent.err.empty_question",
    net_disabled: "agent.err.net_disabled",
    no_base_url: "agent.err.no_base_url",
    busy: "agent.err.busy",
    unknown_job: "agent.err.unknown_job",
    unknown_session: "agent.err.unknown_session",
    session_failed: "agent.err.sessionFailed",
    cancel_failed: "agent.err.cancelFailed",
    config_error: "agent.err.config",
    ask_failed: "agent.err.askFailed",
    CONFIG: "agent.err.config",
    AUTH: "agent.err.auth",
    MISSING_CREDENTIAL: "agent.err.credential",
    INVALID_CREDENTIAL: "agent.err.credential",
    RATE_LIMIT: "agent.err.rateLimit",
    QUOTA: "agent.err.quota",
    TIMEOUT: "agent.err.timeout",
    CONTEXT_WINDOW_EXCEEDED: "agent.err.context",
    TRANSPORT: "agent.err.transport",
    SERVER: "agent.err.server",
    EMPTY_RESPONSE: "agent.err.emptyResponse",
    PROTOCOL: "agent.err.protocol",
    INVALID_REQUEST: "agent.err.invalidRequest",
  };

  // 本地化文案只说"失败"、需要附后端原文的兜底 code（见 fullErrorText）
  const GENERIC_CODES = { ask_failed: true, config_error: true, unknown: true };

  // 端点配置的对外视图（与 agent_get_config 的返回结构一致）
  let cfg = {
    enabled: true,
    base_url: "",
    model: "",
    timeout_s: 0,
    has_key: false,
    key_masked: "",
    config_rel: "",
  };

  // 会话消息（渲染的唯一来源；清空 = 置空数组）
  const messages = []; // { role: "user"|"assistant", text, anchors, error, stopped }
  let job = null; // { id, cursor, epoch }：在飞作业（null = 无）
  let busy = false; // 生成/轮询中（禁用发送）
  let streamingEl = null; // 正在流式写入的消息体元素
  // 世代号：每次提问递增；「清空对话」/「停止」也递增 ⇒ 在飞回调据此作废
  let epoch = 0;

  // 多轮续聊：当前会话 id（null = 全新会话）与其所属知识库（换库即作废）
  let sessionId = null;
  let sessionKb = "";

  // 历史会话下拉的缓存（供语言切换后就地重绘，无需重新请求）
  let historyRows = [];
  let historyDisabled = true;

  // 删除的二次确认状态（3s 内未再点即复位；不弹窗）
  const DELETE_CONFIRM_MS = 3000;
  let deleteArmed = false;
  let deleteTimer = null;

  // 「恢复上次会话」的幂等键（同一库+同一 id 只自动恢复一次，避免重复请求/覆盖）
  let restoredKey = "";

  // 底部状态栏用量格（`#status-agent`）：最近一轮 usage + **本会话累计**
  // （面板自持累加；**不**为此新增任何 RPC 轮询）。`null` = 尚无（该格为空、不占位）。
  let lastUsage = null;
  let sessionUsage = null;

  // 等待计时：轮询期间状态行显示「生成中… Ns」（每秒刷新，结束/出错即停）
  let waitStartedAt = 0;
  let waitTimer = null;

  // ── 右侧停靠栏宽度 / 折叠（持久化到 config/ui-settings.json 的 layout 段）──
  const DOCK_MIN_REM = 16; // 与 app.css 的 #-agent-dock min-width 一致
  const DOCK_MAX_REM = 34; // 与 max-width 一致
  const DOCK_DEFAULT_REM = 22; // 与 width 一致
  // 文档区（#content）最小宽度保护：三栏（左栏 + #content + dock）都是固定/自动宽，
  // 空间不足时**只让 dock 让位**（先缩到 16rem，再整体临时隐藏），#content 永不小于它。
  const CONTENT_MIN_PX = 360;
  let dockWidthRem = DOCK_DEFAULT_REM; // **期望宽度**（rem）：只在拖拽/显式操作时改写
  let dockCollapsed = false; // 手动折叠（用户意图，落盘）
  let dockAutoHidden = false; // 空间不足自动隐藏（派生态，**永不落盘**）

  /** 根字号（rem→px 换算基准；受显示设置 uiScale 影响）。 */
  function rootFontSize() {
    const px = parseFloat(getComputedStyle(document.documentElement).fontSize);
    return px > 0 ? px : 16;
  }

  function clampDockRem(rem) {
    const rounded = Math.round(rem * 100) / 100;
    return Math.min(DOCK_MAX_REM, Math.max(DOCK_MIN_REM, rounded));
  }

  /** 左栏**生效**宽度（px）：未折叠 = 当前宽度，折叠 = 0（CSS 已把宽度归零）。 */
  function sidebarEffectivePx() {
    const sb = $("#-sidebar");
    if (!sb) return 0;
    const w = sb.getBoundingClientRect().width;
    return w > 0 ? w : 0;
  }

  /** 容许 dock 占用的宽度（px）= `#main` 内宽 − 左栏生效宽 − 文档区最小宽 360。 */
  function availableDockPx() {
    const main = $("#main");
    const mainW = main ? main.clientWidth : window.innerWidth;
    return mainW - sidebarEffectivePx() - CONTENT_MIN_PX;
  }

  /** 浮动按钮贴对话栏左缘（右栏在最右侧，故用 right 定位；隐藏时贴窗口右缘）。 */
  function positionDockCollapseBtn() {
    const dock = $("#-agent-dock");
    const btn = $("#agent-dock-collapse-btn");
    if (!dock || !btn) return;
    btn.style.right = (
      dockCollapsed || dockAutoHidden
        ? 0
        : Math.max(0, window.innerWidth - dock.getBoundingClientRect().left - 1)
    ) + "px";
  }

  /**
   * 把三态（手动折叠 / 空间不足自动隐藏 / 展开）落到 DOM：类名 + 按钮字形·文案·aria。
   * 三态的**浮动按钮文案不同**——自动隐藏用 `agent.dockNoSpaceTitle`（说明"先折叠左栏"），
   * 从而与用户主动折叠可区分；顶栏 `#btn-agent` 的 title 仍由 i18n 静态节点
   * `agent.btnTitle` 驱动（不在此改写，避免与语言包刷新抢写）。
   */
  function applyDockCollapsed() {
    const dock = $("#-agent-dock");
    const btn = $("#agent-dock-collapse-btn");
    const toolbarBtn = $("#btn-agent");
    if (dock) dock.classList.toggle("-agent-dock--collapsed", dockCollapsed);
    const hidden = dockCollapsed || dockAutoHidden;
    if (btn) {
      btn.textContent = hidden ? "‹" : "›";
      btn.title = T(
        dockAutoHidden
          ? "agent.dockNoSpaceTitle"
          : dockCollapsed
            ? "agent.dockExpandTitle"
            : "agent.dockCollapseTitle"
      );
      btn.setAttribute("aria-label", btn.title);
      btn.setAttribute("aria-expanded", String(!hidden));
    }
    if (toolbarBtn) toolbarBtn.setAttribute("aria-pressed", String(!hidden));
    positionDockCollapseBtn();
  }

  /**
   * 重算**生效宽度**并落到 DOM。期望宽度 ≠ 生效宽度：
   *   available = `#main` 内宽 − 左栏生效宽 − CONTENT_MIN_PX(360)
   *   手动折叠                    → 0
   *   available ≥ dockMin(16rem)  → clamp(期望, 16rem, min(34rem, available))
   *   否则                        → 0（空间不足：临时自动隐藏）
   * **自动收缩/自动隐藏都不回写盘**：dockWidthRem 始终是用户期望值，窗口变宽即自动还原。
   * CSS 的 min-width/max-width 仍作兜底——本函数只写内联 `width`，不覆盖它们。
   */
  function applyDockLayout() {
    const dock = $("#-agent-dock");
    if (!dock) return;
    const unit = rootFontSize();
    let effectiveRem = 0;
    dockAutoHidden = false;
    if (!dockCollapsed) {
      const cappedPx = Math.min(DOCK_MAX_REM * unit, availableDockPx());
      if (cappedPx >= DOCK_MIN_REM * unit) {
        effectiveRem = Math.min(dockWidthRem, cappedPx / unit);
      } else {
        dockAutoHidden = true;
      }
    }
    dock.classList.toggle("-agent-dock--auto-hidden", dockAutoHidden);
    // 折叠/自动隐藏都交由 CSS（两者都是 width:0 !important）；隐藏期间保留内联值不清，
    // 展开时再由本函数按新的 available 重算覆盖。
    if (!dockCollapsed && !dockAutoHidden) {
      dock.style.width = Math.round(effectiveRem * 100) / 100 + "rem";
    }
    applyDockCollapsed();
  }

  /** 手动切换（两个入口共用）：隐藏态（手动折叠**或**空间不足）点击 = 请求展开。 */
  function toggleDock() {
    setDockCollapsed(!(dockCollapsed || dockAutoHidden), true);
  }

  /**
   * 写 layout 段。
   * ⚠️ 后端 `save_ui_settings` 是**顶层浅合并**（`storage/ui_settings.py:58-75`）：
   * 直接传 `{layout:{agentDockWidth}}` 会把整个 `layout` 换成只含本键的对象、
   * 抹掉 `layout.sidebarWidth`。故必须先读现有 layout 再整体写回。
   */
  async function saveDockLayout(patch) {
    let layout = {};
    try {
      const res = await call("get_ui_settings");
      const cur = res && res.status === "ok" && res.settings && res.settings.layout;
      if (cur && typeof cur === "object") layout = Object.assign({}, cur);
    } catch (_e) { /* 非桌面环境：保持内存态 */ }
    Object.assign(layout, patch);
    try {
      await call("save_ui_settings", { layout: layout });
    } catch (_e) { /* 同上 */ }
  }

  /**
   * 写 `config/ui-settings.json` 的**顶层 `agent` 段**（当前只有 `lastSessionId`）。
   * 与 saveDockLayout() 同理：后端 `save_ui_settings` 是**顶层浅合并**，先读旧
   * `agent` 段再合并写回，避免抹掉同段其它键（也绝不触碰 `layout` 段）。
   */
  async function saveAgentPrefs(patch) {
    let agent = {};
    try {
      const res = await call("get_ui_settings");
      const cur = res && res.status === "ok" && res.settings && res.settings.agent;
      if (cur && typeof cur === "object") agent = Object.assign({}, cur);
    } catch (_e) { /* 非桌面环境：保持内存态 */ }
    Object.assign(agent, patch);
    try {
      await call("save_ui_settings", { agent: agent });
    } catch (_e) { /* 同上 */ }
  }

  /** 读磁盘偏好里的「上次会话 id」（顶层 `agent.lastSessionId`，空即 null）。 */
  async function readLastSessionId() {
    try {
      const res = await call("get_ui_settings");
      const seg = res && res.status === "ok" && res.settings && res.settings.agent;
      const raw = seg && seg.lastSessionId;
      const id = typeof raw === "string" ? raw.trim() : "";
      return id || null;
    } catch (_e) {
      return null;
    }
  }

  function setupDockResize() {
    const resizer = $("#agent-dock-resizer");
    if (!resizer) return;
    let dragging = false;
    resizer.addEventListener("mousedown", (e) => {
      dragging = true;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      // 右栏与左栏相反：向左拖变宽 ⇒ 期望宽度 = 窗口右缘 − 指针 x
      // 上界同时受「文档区留 360px」约束（min(34rem, available)）：拖到极限也不会破 360
      const unit = rootFontSize();
      const upperRem = Math.min(DOCK_MAX_REM, availableDockPx() / unit);
      const wantRem = (window.innerWidth - e.clientX) / unit;
      dockWidthRem = Math.min(Math.max(DOCK_MIN_REM, wantRem), Math.max(DOCK_MIN_REM, upperRem));
      applyDockLayout(); // 拖拽过程中实时生效
    });
    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      saveDockLayout({ agentDockWidth: dockWidthRem }); // 只有松手才写盘（照左栏做法）
    });
  }

  function setDockCollapsed(collapsed, persist) {
    const want = !!collapsed;
    // 空间不足自动隐藏时的「展开」请求：**不允许挤压文档区** ⇒ 保持隐藏并提示先折叠左栏。
    // 不写盘、也不改 dockCollapsed，故窗口变宽后仍会自动回到期望宽度，无需用户再点。
    if (!want && dockAutoHidden) {
      showFlashInfo(T("agent.dockNoSpace"));
      return;
    }
    const wasCollapsed = dockCollapsed;
    dockCollapsed = want;
    applyDockLayout();
    if (persist) saveDockLayout({ agentDockCollapsed: dockCollapsed });
    // 展开时刷新端点配置与历史列表（可能被外部改动），并尝试恢复上次会话
    if (wasCollapsed && !dockCollapsed) {
      refreshConfig();
      refreshHistory().then(() => restoreLastSession());
    }
  }

  /** 启动时同步停靠栏宽度/折叠态（磁盘优先；无磁盘值则用 CSS 默认 22rem / 展开）。 */
  async function hydrateDockLayout() {
    try {
      const res = await call("get_ui_settings");
      const lay = res && res.status === "ok" && res.settings && res.settings.layout;
      if (!lay) return;
      const w = parseFloat(lay.agentDockWidth);
      if (Number.isFinite(w)) dockWidthRem = clampDockRem(w); // 磁盘上是**期望宽度**
      if (typeof lay.agentDockCollapsed === "boolean") dockCollapsed = lay.agentDockCollapsed;
      applyDockLayout();
    } catch (_e) { /* 非桌面环境忽略 */ }
  }

  // ── 渲染 ────────────────────────────────────────────────────────────

  function scrollToBottom() {
    const box = $("#agent-messages");
    if (box) box.scrollTop = box.scrollHeight;
  }

  /** 把纯文本里的 `文件:行号` 变成可点击锚点（先转义再匹配，避免注入）。 */
  function linkify(text) {
    return esc(text)
      .replace(ANCHOR_RE, function (_m, file, line) {
        return (
          '<span class="-agent-anchor" role="link" tabindex="0" data-agent-file="' +
          esc(file) +
          '" data-agent-line="' +
          esc(line) +
          '">' +
          esc(file) +
          ":" +
          esc(line) +
          "</span>"
        );
      })
      .replace(/\n/g, "<br>");
  }

  function messageEl(rec) {
    const wrap = document.createElement("div");
    wrap.className = "-agent-msg " + (rec.role === "user" ? "-agent-msg--user" : "-agent-msg--assistant");
    if (rec.error) wrap.classList.add("-agent-msg--error");
    const role = document.createElement("span");
    role.className = "-agent-msg-role";
    role.textContent = T(rec.role === "user" ? "agent.role.user" : "agent.role.assistant");
    const body = document.createElement("div");
    body.className = "-agent-msg-body";
    body.innerHTML = rec.role === "user" ? esc(rec.text).replace(/\n/g, "<br>") : linkify(rec.text);
    wrap.appendChild(role);
    wrap.appendChild(body);
    if (rec.anchors && rec.anchors.length) {
      wrap.appendChild(sourcesEl(rec.anchors));
    }
    if (rec.error) {
      const note = document.createElement("div");
      note.className = "-agent-msg-note";
      note.textContent = rec.error;
      wrap.appendChild(note);
    }
    if (rec.stopped) {
      // 真取消：保留已生成的部分文本，其后标注「（已停止）」（次要色，非错误）
      const note = document.createElement("div");
      note.className = "-agent-msg-note -agent-stopped";
      note.textContent = T("agent.stopped");
      wrap.appendChild(note);
    }
    return wrap;
  }

  /** 助手消息末尾的来源条（后端 anchors：file/line/kp_id/name）。 */
  function sourcesEl(anchors) {
    const box = document.createElement("div");
    box.className = "-agent-sources";
    const label = document.createElement("span");
    label.className = "-agent-sources-label -muted";
    label.textContent = T("agent.sources", { n: anchors.length });
    box.appendChild(label);
    anchors.forEach(function (anchor) {
      const file = String((anchor && anchor.file) || "");
      if (!file) return;
      const line = anchor && anchor.line;
      const chip = document.createElement("span");
      chip.className = "-agent-source";
      chip.setAttribute("data-agent-file", file);
      if (line) chip.setAttribute("data-agent-line", String(line));
      const name = String((anchor && anchor.name) || anchor.kp_id || "");
      chip.textContent = name ? name + " · " + file + (line ? ":" + line : "") : file + (line ? ":" + line : "");
      box.appendChild(chip);
    });
    return box;
  }

  function renderMessages() {
    const box = $("#agent-messages");
    if (!box) return;
    box.innerHTML = "";
    streamingEl = null;
    if (!messages.length) {
      const empty = document.createElement("div");
      empty.className = "-agent-empty -muted";
      empty.textContent = T("agent.empty");
      box.appendChild(empty);
      return;
    }
    messages.forEach(function (rec) {
      box.appendChild(messageEl(rec));
    });
    scrollToBottom();
  }

  function currentAssistant() {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant") return messages[i];
    }
    return null;
  }

  function errorText(res) {
    const code = res && res.code;
    if (code && ERR_KEYS[code]) {
      const key = ERR_KEYS[code];
      const text = T(key);
      if (text !== key) return text;
    }
    const message = (res && (res.message || res.error)) || "";
    return message || T("agent.err.unknown");
  }

  /** 后端原始错误文本（轮询在 `error`、提交在 `message`）；可能为空。 */
  function errorDetail(res) {
    return String((res && (res.error || res.message)) || "").trim();
  }

  /**
   * 展示用错误文本：本地化文案 + 后端原始文本（两者不同才拼接）。
   * 只在**兜底 code** 上拼接：`ask_failed` / `config_error` 的本地化文案只说"失败"，
   * 真正原因（传输/认证/HTTP 状态等）只在后端原文里；而 `busy` / `no_base_url` 这类
   * 具体 code 的本地化文案已足够，再叠一句后端中文只是噪声。
   */
  function fullErrorText(res) {
    const mapped = errorText(res);
    const raw = errorDetail(res);
    if (!raw || raw === mapped) return mapped;
    if (ERR_KEYS[(res && res.code) || ""] && !GENERIC_CODES[(res && res.code) || ""]) return mapped;
    return mapped + " · " + raw;
  }

  /** 状态行：`msg` 为文案；`error=true` 时转红。 */
  function setStatusText(msg, error) {
    const el = $("#agent-status");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("-agent-error", !!error);
  }

  function usageText(usage) {
    if (!usage || !usage.total_tokens) return "";
    return T("agent.status.usage", {
      prompt: usage.prompt_tokens || 0,
      completion: usage.completion_tokens || 0,
      total: usage.total_tokens || 0,
      estimated: usage.estimated ? T("agent.status.usageEstimated") : "",
    });
  }

  function statusLine(parts) {
    return parts.filter(Boolean).join(" · ");
  }

  // ── 底部状态栏用量格（`#status-agent`）────────────────────────────────
  // 显示**最近一轮**的紧凑摘要（如 `↑8.7k ↓233 · 命中 62%`）；悬停给计费拆分
  // （本轮 + 本会话累计）；点击展开右侧对话面板。无 agent 活动 ⇒ 空（`:empty` 不占位）。

  function usageInt(value) {
    return typeof value === "number" && isFinite(value) ? value : null;
  }

  /** token 数的紧凑写法：≥1000 用 k（一位小数，去掉多余的 .0），否则原样。 */
  function fmtTokens(n) {
    const v = Number(n) || 0;
    if (v < 1000) return String(v);
    return (v / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  }

  /** 命中率文本；**命中量未知时返回 null**（调用方据此省略该段，绝不瞎报 0%）。 */
  function hitRateText(hit, prompt) {
    if (hit === null || !prompt) return null;
    return ((hit / prompt) * 100).toFixed(1).replace(/\.0$/, "") + "%";
  }

  /** 把一轮 usage 累加进本会话累计（只累加，不发请求）。 */
  function addSessionUsage(usage) {
    if (!sessionUsage) {
      sessionUsage = {
        turns: 0, prompt: 0, completion: 0, total: 0,
        cache_hit: 0, cache_miss: 0, hit_denom: 0, hit_known: 0, miss_known: 0,
      };
    }
    const prompt = usage.prompt_tokens || 0;
    const completion = usage.completion_tokens || 0;
    const hit = usageInt(usage.cache_read_tokens);
    const miss = usageInt(usage.cache_miss_tokens);
    sessionUsage.turns += 1;
    sessionUsage.prompt += prompt;
    sessionUsage.completion += completion;
    sessionUsage.total += usage.total_tokens || prompt + completion;
    if (hit !== null) {
      sessionUsage.hit_known += 1;
      sessionUsage.cache_hit += hit;
      sessionUsage.hit_denom += prompt;
    }
    if (miss !== null) {
      sessionUsage.miss_known += 1;
      sessionUsage.cache_miss += miss;
    }
  }

  /** 重绘用量格；`lastUsage` 为空即清空文本与 title（`:empty` 使其不占位）。 */
  function renderStatusUsage() {
    const el = $("#status-agent");
    if (!el) return;
    const u = lastUsage;
    if (!u || !u.total_tokens) {
      el.textContent = "";
      el.title = "";
      return;
    }
    const prompt = u.prompt_tokens || 0;
    const completion = u.completion_tokens || 0;
    const total = u.total_tokens || prompt + completion;
    const hit = usageInt(u.cache_read_tokens);
    const miss = usageInt(u.cache_miss_tokens);
    const rate = hitRateText(hit, prompt);

    el.textContent =
      T("agent.statusBar.span", { prompt: fmtTokens(prompt), completion: fmtTokens(completion) }) +
      (rate ? T("agent.statusBar.spanCache", { rate: rate }) : "");

    const lines = [T("agent.statusBar.line", { prompt: prompt, completion: completion, total: total })];
    lines.push(
      hit === null
        ? T("agent.statusBar.cacheUnknown")
        : T("agent.statusBar.cache", { hit: hit, miss: miss === null ? "—" : miss, rate: rate || "—" })
    );
    if (u.estimated) lines.push(T("agent.statusBar.estimated"));
    if (sessionUsage && sessionUsage.turns > 0) {
      lines.push(
        T("agent.statusBar.session", {
          turns: sessionUsage.turns,
          prompt: sessionUsage.prompt,
          completion: sessionUsage.completion,
          total: sessionUsage.total,
        })
      );
      // 累计缓存只在"至少一轮上报过命中量"时给（与后端 report 口径一致）
      if (sessionUsage.hit_known > 0) {
        lines.push(
          T("agent.statusBar.sessionCache", {
            hit: sessionUsage.cache_hit,
            miss: sessionUsage.miss_known > 0 ? sessionUsage.cache_miss : "—",
            rate: hitRateText(sessionUsage.cache_hit, sessionUsage.hit_denom) || "—",
          })
        );
      }
    }
    lines.push(T("agent.statusBar.hint"));
    el.title = lines.join("\n");
  }

  /** 复位用量格（清空对话 / 载入历史会话 / 换库；历史会话无法回算旧用量）。 */
  function resetStatusUsage() {
    lastUsage = null;
    sessionUsage = null;
    renderStatusUsage();
  }

  // ── 等待计时（轮询期间状态行「生成中… Ns」）────────────────────────────

  /** 每秒刷新一次状态行；只在 `startWait()` 之后生效。 */
  function tickWait() {
    if (!waitStartedAt) return;
    const secs = Math.max(0, Math.floor((Date.now() - waitStartedAt) / 1000));
    setStatusText(statusLine([T("agent.status.thinking"), T("agent.status.elapsed", { n: secs })]));
  }

  function startWait() {
    waitStartedAt = Date.now();
    if (waitTimer) clearInterval(waitTimer);
    waitTimer = setInterval(tickWait, 1000);
    tickWait();
  }

  function stopWait() {
    if (waitTimer) {
      clearInterval(waitTimer);
      waitTimer = null;
    }
    waitStartedAt = 0;
  }

  // ── 会话历史（列/载 只读；删除为 M1 收尾新增的唯一写知识库入口）─────────

  /**
   * 删除按钮的文案与禁用态：未选中具体会话（「（新会话）」/列表空）时禁用；
   * 二次确认中显示 `agent.history.deleteConfirm`。
   */
  function syncDeleteButton() {
    const btn = $("#agent-history-delete");
    if (!btn) return;
    const sel = $("#agent-history");
    const hasTarget = !!(sel && sel.value && historyRows.length && !historyDisabled);
    btn.disabled = !hasTarget;
    const label = deleteArmed && hasTarget ? T("agent.history.deleteConfirm") : T("agent.history.delete");
    const span = btn.querySelector("span");
    if (span) span.textContent = label;
    else btn.textContent = label;
    btn.title = T("agent.history.deleteTitle");
  }

  /** 复位删除的二次确认态（选择变化 / 超时 / 删除完成后调用）。 */
  function resetDeleteArmed() {
    if (deleteTimer) {
      clearTimeout(deleteTimer);
      deleteTimer = null;
    }
    deleteArmed = false;
    syncDeleteButton();
  }

  /** 把会话列表渲染进 `#agent-history`；空/不可用时给禁用态与提示文案。 */
  function renderHistory(sel, sessions, disabled) {
    historyRows = Array.isArray(sessions) ? sessions : [];
    historyDisabled = !!disabled;
    sel.innerHTML = "";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = T("agent.history.none");
    sel.appendChild(none);
    historyRows.forEach(function (row) {
      const session = row || {};
      const id = String(session.session_id || "");
      if (!id) return;
      const opt = document.createElement("option");
      opt.value = id;
      // 超限会话（后端 `capped:true`：turn 计数被扫描上限截断）补一个后缀标记
      opt.textContent =
        T("agent.history.option", {
          preview: String(session.preview || id),
          n: session.turn_count || 0,
        }) + (session.capped ? T("agent.history.capped") : "");
      sel.appendChild(opt);
    });
    sel.disabled = historyDisabled || !historyRows.length;
    if (!historyRows.length) none.textContent = T("agent.history.empty");
    sel.title = sel.disabled ? none.textContent : "";
    syncHistorySelection();
    resetDeleteArmed(); // 列表重绘后先复位，再按当前选中态刷新按钮
  }

  /** 让下拉选中当前 `sessionId`（不在列表中则落回「（新会话）」）。 */
  function syncHistorySelection() {
    const sel = $("#agent-history");
    if (!sel) return;
    const want = sessionId || "";
    for (let i = 0; i < sel.options.length; i += 1) {
      if (sel.options[i].value === want) {
        sel.selectedIndex = i;
        syncDeleteButton();
        return;
      }
    }
    if (sel.options.length) sel.selectedIndex = 0;
    syncDeleteButton();
  }

  /** 语言切换后就地重绘历史选项（文案来自语言包，无需重新请求）。 */
  function refreshHistoryLabels() {
    const sel = $("#agent-history");
    if (!sel) return;
    renderHistory(sel, historyRows, historyDisabled);
  }

  /**
   * 刷新历史列表（打开面板 / 每次提问结束后 / 展开停靠栏 / 切换知识库时）。
   * 顺带作废跨库会话：`sessionKb` 与当前库不一致 ⇒ `sessionId` 置空（开新会话）。
   */
  async function refreshHistory() {
    const sel = $("#agent-history");
    if (!sel) return;
    const kb = state.kbPath || "";
    if (sessionKb && sessionKb !== kb) {
      sessionId = null;
      sessionKb = "";
    }
    if (!kb) {
      renderHistory(sel, [], true);
      return;
    }
    let res;
    try {
      res = await call("agent_sessions_list", kb);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok" || !Array.isArray(res.sessions)) {
      renderHistory(sel, [], true);
      return;
    }
    renderHistory(sel, res.sessions, false);
  }

  /**
   * 载入一个历史会话：灌进气泡区并把 `sessionId` 设为它（下一句即续聊）。
   * `silent=true`（恢复上次会话用）⇒ 失败**不报错、不提示**，只是不载入。
   */
  async function loadSession(id, silent) {
    if (busy) return false;
    const kb = state.kbPath || "";
    let res;
    try {
      res = await call("agent_session_load", id, kb || null);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok") {
      if (!silent) {
        const msg = fullErrorText(res);
        setStatusText(msg, true);
        showFlashError(msg);
        syncHistorySelection(); // 失败即把下拉回滚到当前会话
      }
      return false;
    }
    messages.length = 0;
    (res.messages || []).forEach(function (item) {
      const rec = item || {};
      messages.push({
        role: rec.role === "user" ? "user" : "assistant",
        text: String(rec.text || ""),
        anchors: Array.isArray(rec.anchors) ? rec.anchors : [],
        error: "",
        stopped: false,
      });
    });
    streamingEl = null;
    sessionId = String(res.session_id || id);
    sessionKb = kb;
    resetStatusUsage(); // 历史会话的旧用量无法回算（会话视图不含 usage）⇒ 本会话累计从 0 起
    renderMessages();
    setStatusText(T("agent.status.session", { id: sessionId }));
    syncHistorySelection();
    saveAgentPrefs({ lastSessionId: sessionId }); // 记住当前会话，供下次自动恢复
    return true;
  }

  /**
   * 恢复上次会话（面板打开 / 切换知识库后）：磁盘偏好里的 `lastSessionId` 若指向
   * **仍存在**的会话文件即自动载入并设为当前会话；不存在/非法 ⇒ **静默忽略**
   * （不报错、不提示）。同一（库, id）只尝试一次（`restoredKey` 幂等）。
   */
  async function restoreLastSession() {
    if (busy || job || messages.length || sessionId) return;
    const kb = state.kbPath || "";
    if (!kb) return;
    const id = await readLastSessionId();
    if (!id) return;
    const key = kb + "|" + id;
    if (restoredKey === key) return;
    restoredKey = key;
    await loadSession(id, true);
  }

  /** 知识库切换钩子（app.js 在开库/关库时调用）：换库即作废会话并重试恢复。 */
  function onKbChanged() {
    const kb = state.kbPath || "";
    resetDeleteArmed();
    if (sessionKb && sessionKb !== kb) {
      sessionId = null;
      sessionKb = "";
      messages.length = 0;
      streamingEl = null;
      resetStatusUsage(); // 换库即作废本会话累计与状态栏用量格
      renderMessages();
      setStatusText("");
    }
    restoredKey = "";
    refreshHistory();
    restoreLastSession();
  }

  /** 「删除」按钮：两次点击确认（首点变「再点一次删除」，3s 未再点即复位）。 */
  async function deleteSelected() {
    const sel = $("#agent-history");
    const id = (sel && sel.value) || "";
    if (!id || !historyRows.length) return;
    if (!deleteArmed) {
      deleteArmed = true;
      syncDeleteButton();
      if (deleteTimer) clearTimeout(deleteTimer);
      deleteTimer = setTimeout(function () {
        deleteTimer = null;
        deleteArmed = false;
        syncDeleteButton();
      }, DELETE_CONFIRM_MS);
      return;
    }
    resetDeleteArmed();
    const kb = state.kbPath || "";
    let res;
    try {
      res = await call("agent_session_delete", id, kb || null);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok") {
      showFlashError(fullErrorText(res));
      return;
    }
    // 删的是当前会话 ⇒ 回到「新会话」态（清空气泡与偏好），否则仅刷新列表
    if (sessionId === id) {
      await clear();
      restoredKey = ""; // 该会话已不存在：清掉幂等键，避免下次误判
    }
    await refreshHistory();
    showFlashInfo(T("agent.history.deleted"));
  }

  // ── 表单 / 按钮态 ───────────────────────────────────────────────────

  function applyConfigToForm() {
    const baseUrl = $("#agent-base-url");
    const model = $("#agent-model");
    const key = $("#agent-api-key");
    const timeout = $("#agent-timeout");
    const net = $("#agent-net-toggle");
    const label = $("#agent-model-label");
    if (baseUrl) baseUrl.value = cfg.base_url || "";
    if (model) model.value = cfg.model || "";
    if (timeout) timeout.value = cfg.timeout_s ? String(cfg.timeout_s) : "";
    if (key) {
      // 密钥永不回显：输入框留空，掩码只作 placeholder
      key.value = "";
      key.placeholder = cfg.has_key ? T("agent.settings.apiKeySet", { masked: cfg.key_masked }) : T("agent.settings.apiKeyPh");
    }
    if (net) net.checked = !!cfg.enabled;
    if (label) {
      label.textContent = statusLine([
        cfg.model || T("agent.model.none"),
        cfg.enabled ? "" : T("agent.model.netOff"),
      ]);
    }
    const pathEl = $("#agent-config-path");
    if (pathEl) {
      pathEl.textContent = cfg.config_rel ? T("agent.settings.path", { path: cfg.config_rel }) : "";
      pathEl.title = cfg.config_rel || "";
    }
    renderComposer();
  }

  function renderComposer() {
    const send = $("#agent-send");
    const stopBtn = $("#agent-stop");
    if (send) {
      send.disabled = busy || !cfg.enabled;
      send.title = !cfg.enabled ? T("agent.err.net_disabled") : "";
    }
    if (stopBtn) stopBtn.classList.toggle("hidden", !busy);
  }

  // ── 配置读写 ────────────────────────────────────────────────────────

  async function refreshConfig() {
    let res;
    try {
      res = await call("agent_get_config");
    } catch (e) {
      setStatusText(String((e && e.message) || e), true);
      return;
    }
    if (!res || res.status !== "ok") {
      setStatusText(fullErrorText(res), true);
      return;
    }
    cfg = res;
    applyConfigToForm();
    if (!cfg.enabled && !busy) setStatusText(T("agent.err.net_disabled"), true);
  }

  async function saveConfig() {
    const patch = {
      base_url: ($("#agent-base-url") || {}).value || "",
      model: ($("#agent-model") || {}).value || "",
    };
    const timeout = (($("#agent-timeout") || {}).value || "").trim();
    if (timeout) patch.timeout_s = timeout; // 空 = 不修改（后端同语义）
    const secret = (($("#agent-api-key") || {}).value || "").trim();
    if (secret) patch.api_key = secret; // 掩码占位：仅在输入新值时提交
    let res;
    try {
      res = await call("agent_save_config", patch);
    } catch (e) {
      showFlashError(T("agent.settings.saveFailed"), String((e && e.message) || e));
      return;
    }
    if (!res || res.status !== "ok") {
      showFlashError(T("agent.settings.saveFailed"), errorDetail(res) || errorText(res));
      return;
    }
    cfg = res;
    applyConfigToForm();
    showFlashInfo(T("agent.settings.saved"));
    setStatusText(cfg.enabled ? "" : T("agent.err.net_disabled"), !cfg.enabled);
  }

  async function toggleNet(on) {
    let res;
    try {
      res = await call("agent_save_config", { enabled: !!on });
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok") {
      const net = $("#agent-net-toggle");
      if (net) net.checked = !on; // 写失败即回滚开关外观
      showFlashError(T("agent.settings.saveFailed"), errorDetail(res) || errorText(res));
      return;
    }
    cfg = res;
    applyConfigToForm();
    setStatusText(cfg.enabled ? "" : T("agent.err.net_disabled"), !cfg.enabled);
  }

  // ── 提问（伪流式：提交 + 轮询）────────────────────────────────────────

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function pushMessage(role, text) {
    const rec = { role: role, text: text || "", anchors: [], error: "", stopped: false };
    messages.push(rec);
    const box = $("#agent-messages");
    if (box) {
      const empty = box.querySelector(".-agent-empty");
      if (empty) empty.remove();
      const el = messageEl(rec);
      box.appendChild(el);
      streamingEl = el.querySelector(".-agent-msg-body");
      scrollToBottom();
    }
    return rec;
  }

  function applyDelta(delta) {
    const rec = currentAssistant();
    if (!rec) return;
    rec.text += delta;
    if (streamingEl) {
      // 流式期间用 textContent 追加（不重排 HTML）；定稿时再 linkify
      streamingEl.textContent = rec.text;
      scrollToBottom();
    }
  }

  function finalizeMessage(result) {
    const rec = currentAssistant();
    if (!rec) return;
    // 后端 `answer` 是权威最终答案（loop 每轮以当轮文本覆盖 answer），
    // 流式累积可能含工具轮的前言，故非空时以 answer 为准
    if (result.answer) rec.text = result.answer;
    rec.anchors = Array.isArray(result.anchors) ? result.anchors : [];
    rec.error = result.status === "error" ? fullErrorText(result) : "";
    const box = $("#agent-messages");
    if (box && streamingEl) {
      const wrap = streamingEl.parentElement;
      const rebuilt = messageEl(rec);
      if (wrap) box.replaceChild(rebuilt, wrap);
    }
    streamingEl = null;
    scrollToBottom();
  }

  async function ask() {
    const input = $("#agent-input");
    const text = ((input && input.value) || "").trim();
    if (busy) return;
    if (!text) {
      setStatusText(T("agent.err.empty_question"), true);
      return;
    }
    if (!state.kbPath) {
      showFlashError(T("agent.err.no_kb"));
      setStatusText(T("agent.err.no_kb"), true);
      return;
    }
    if (!cfg.enabled) {
      showFlashError(T("agent.err.net_disabled"));
      setStatusText(T("agent.err.net_disabled"), true);
      return;
    }
    // 换库后旧会话 id 失效：作废即开新会话（避免把 A 库的会话续到 B 库）
    const kb = state.kbPath || "";
    if (sessionKb && sessionKb !== kb) {
      sessionId = null;
      sessionKb = "";
    }
    // 本问的世代号：清空/忽略会递增 epoch，使本次提交与轮询结果一律作废
    const myEpoch = ++epoch;

    pushMessage("user", text);
    if (input) input.value = "";
    let res;
    try {
      res = await call("agent_ask_start", text, kb || null, sessionId || null);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (epoch !== myEpoch) return; // 提交期间被「清空对话」作废 ⇒ 丢弃，不写回面板
    if (!res || res.status !== "ok" || !res.job_id) {
      const msg = fullErrorText(res);
      const rec = pushMessage("assistant", "");
      rec.error = msg;
      renderMessages();
      setStatusText(msg, true);
      showFlashError(msg);
      return;
    }
    job = { id: res.job_id, cursor: 0, epoch: myEpoch };
    busy = true;
    pushMessage("assistant", "");
    renderComposer();
    await poll();
  }

  async function poll() {
    const myEpoch = epoch; // 本次轮询所属世代：epoch 一旦被递增，本次结果一律作废
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    const kbAtStart = state.kbPath || "";
    startWait();
    while (job && epoch === myEpoch && Date.now() < deadline) {
      await sleep(POLL_INTERVAL_MS);
      // 已被「清空对话」/「停止」作废（job 置空、epoch 递增）⇒ 停止轮询、不写回
      if (!job || epoch !== myEpoch) return;
      if ((state.kbPath || "") !== kbAtStart) {
        // 轮询期间换库/关库：结果与当前库无关，丢弃（不谎称已取消）
        job = null;
        busy = false;
        stopWait();
        sessionId = null;
        sessionKb = "";
        renderComposer();
        setStatusText(T("agent.status.dropped"), true);
        refreshHistory();
        return;
      }
      let st;
      try {
        st = await call("agent_ask_poll", job.id, job.cursor);
      } catch (e) {
        st = { status: "error", message: String((e && e.message) || e) };
      }
      if (!job || epoch !== myEpoch) return; // 轮询请求期间被作废 ⇒ 丢弃响应
      if (!st) st = { status: "error", message: T("agent.err.unknown") };
      if (st.delta) applyDelta(st.delta);
      if (typeof st.cursor === "number") job.cursor = st.cursor;
      if (st.status === "running") {
        tickWait();
        continue;
      }
      stopWait();
      finalizeMessage(st);
      // 状态栏用量格：只认"确实有总量"的 usage（取消/未知作业的 usage 为空 ⇒ 保留上一轮）
      if (st.usage && st.usage.total_tokens) {
        lastUsage = st.usage;
        addSessionUsage(st.usage);
        renderStatusUsage();
      }
      if (st.session_id) {
        // 后端把本次会话 id 回传：存下来，后续提问即续聊；并落盘供下次自动恢复
        sessionId = String(st.session_id);
        sessionKb = kbAtStart;
        saveAgentPrefs({ lastSessionId: sessionId });
      }
      const parts = [usageText(st.usage), st.session_id ? T("agent.status.session", { id: st.session_id }) : ""];
      const ok = st.status === "done";
      const detail = ok ? "" : fullErrorText(st);
      setStatusText(ok ? statusLine(parts) : detail, !ok);
      if (!ok) showFlashError(errorText(st), errorDetail(st));
      job = null;
      busy = false;
      renderComposer();
      await refreshHistory(); // 新增/更新的会话进入历史列表，并选中当前会话
      return;
    }
    if (job) {
      job = null;
      busy = false;
      stopWait();
      renderComposer();
      setStatusText(T("agent.status.timeout"), true);
    }
  }

  /**
   * 「停止」= **真取消**（M1 收尾语义变更：不再是"忽略本次"）。
   *
   * 顺序：① 递增 `epoch` 作废在飞回调（含 `poll` 的下一帧）并把 `job` 置空 ⇒ 立即
   * 停止轮询；② 把**已生成的部分文本**留在当前助手气泡上并标注「（已停止）」；
   * ③ 调 `agent_ask_cancel(job_id)`（后端置取消令牌、停止消费模型流并**立即**释放
   * 单飞 busy）；④ 取消 RPC 返回后再放开发送按钮 ⇒ 立刻可再次提问，不会撞 `busy`。
   * 取消 RPC 失败（如作业已结束/已清理）**不影响本地已停止**的结果。
   */
  async function stop() {
    if (!job) return;
    const jid = job.id;
    epoch += 1; // 作废在飞结果：后续轮询回调一律不再写回（含 sessionId）
    job = null;
    streamingEl = null;
    stopWait();
    // 保留已生成的部分文本（不回填后端 answer —— 尚未定型），并在其后标注「（已停止）」
    const rec = currentAssistant();
    if (rec && !rec.error) rec.stopped = true;
    renderMessages();
    setStatusText(T("agent.status.stopped"));
    let res = null;
    try {
      res = await call("agent_ask_cancel", jid);
    } catch (_e) {
      res = null;
    }
    busy = false;
    renderComposer();
    if (res && res.status !== "ok" && res.code !== "unknown_job") {
      showFlashError(errorText(res), errorDetail(res));
    }
    refreshHistory();
  }

  /**
   * 清空对话 = 开新会话（`sessionId` 置空）；旧会话已在磁盘上、进历史列表。
   *
   * 生成中点「清空」同样**作废在飞结果**（递增 epoch ⇒ 轮询停止、session id 不写回），
   * 并**顺带调 `agent_ask_cancel` 取消后端在飞作业**（M1 收尾：避免丢弃结果却继续烧
   * token）。等取消返回后才放开发送按钮，故清空后立刻再提问不会撞 `busy`。
   * 同时把偏好里的 `lastSessionId` 置空（新建会话不该恢复旧会话）。
   */
  async function clear() {
    const jid = job ? job.id : "";
    epoch += 1; // 作废在飞作业（若有）
    job = null;
    messages.length = 0;
    streamingEl = null;
    sessionId = null;
    sessionKb = "";
    stopWait();
    resetStatusUsage(); // 开新会话：状态栏用量格与本会话累计一并清零
    renderMessages();
    setStatusText("");
    if (jid) {
      try {
        await call("agent_ask_cancel", jid);
      } catch (_e) { /* 本地已清空；后端取消失败不影响面板 */ }
    }
    busy = false;
    renderComposer();
    saveAgentPrefs({ lastSessionId: "" });
    refreshHistory();
  }

  // ── 锚点跳转 ────────────────────────────────────────────────────────

  function onAnchorClick(target) {
    const file = target.getAttribute("data-agent-file");
    if (!file) return;
    const line = parseInt(target.getAttribute("data-agent-line") || "", 10);
    // openFile(relPath, {kpId, lineHint})：kpId 优先于 lineHint（app.js:1505-1517）
    const opts = { navSource: "agent" };
    if (Number.isFinite(line) && line > 0) opts.lineHint = line;
    openFile(file, opts);
  }

  // ── 装配 ────────────────────────────────────────────────────────────

  function init() {
    if (!$("#-agent-dock")) return; // 页面未登记右侧停靠栏（旧版 index.html）

    const settingsToggle = $("#agent-settings-toggle");
    const settings = $("#agent-settings");
    if (settingsToggle && settings) {
      settingsToggle.addEventListener("click", () => {
        const open = settings.classList.toggle("hidden");
        settingsToggle.setAttribute("aria-expanded", open ? "false" : "true");
      });
    }
    const save = $("#agent-save-config");
    if (save) save.addEventListener("click", () => saveConfig());
    const net = $("#agent-net-toggle");
    if (net) net.addEventListener("change", () => toggleNet(net.checked));
    const send = $("#agent-send");
    if (send) send.addEventListener("click", () => ask());
    const stopBtn = $("#agent-stop");
    if (stopBtn) stopBtn.addEventListener("click", () => stop());
    const clearBtn = $("#agent-clear");
    if (clearBtn) clearBtn.addEventListener("click", () => clear());
    const historySel = $("#agent-history");
    if (historySel) {
      historySel.addEventListener("change", () => {
        resetDeleteArmed(); // 选中项变了 ⇒ 复位二次确认
        const value = historySel.value || "";
        if (busy) {
          syncHistorySelection(); // 生成中不接受切换（loadSession 也会拒绝）
          return;
        }
        if (!value) {
          clear(); // 选「（新会话）」= 开新会话
          return;
        }
        loadSession(value);
      });
    }
    const deleteBtn = $("#agent-history-delete");
    if (deleteBtn) deleteBtn.addEventListener("click", () => deleteSelected());

    // 状态栏用量格：点击展开右侧对话面板（不新增弹窗；面板在此前已由本模块定义）
    const statusAgent = $("#status-agent");
    if (statusAgent) {
      statusAgent.addEventListener("click", () => {
        const panel = window.MemoriaAgentPanel;
        if (panel && panel.open) panel.open();
      });
    }

    const input = $("#agent-input");
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
        e.preventDefault();
        ask();
      });
    }
    const box = $("#agent-messages");
    if (box) {
      box.addEventListener("click", (e) => {
        const target = e.target && e.target.closest ? e.target.closest("[data-agent-file]") : null;
        if (target) onAnchorClick(target);
      });
      box.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        const target = e.target && e.target.closest ? e.target.closest("[data-agent-file]") : null;
        if (target) {
          e.preventDefault();
          onAnchorClick(target);
        }
      });
    }

    // 停靠栏显隐/调宽：顶栏按钮 + 浮动按钮 + 左缘拖拽柄（两个按钮同一状态、同一 handler）
    const toolbarBtn = $("#btn-agent");
    if (toolbarBtn) toolbarBtn.addEventListener("click", () => toggleDock());
    const collapseBtn = $("#agent-dock-collapse-btn");
    if (collapseBtn) {
      collapseBtn.addEventListener("click", () => toggleDock());
    }
    setupDockResize();
    // 重算生效宽度的触发时机全部收敛到「几何变化」：视口（含 uiScale 改根字号后的
    // 显式 resize 事件）+ 左栏宽度拖拽/折叠展开（#-sidebar 宽变）+ dock 自身。
    // 用 ResizeObserver 盯 #main / #-sidebar 比到 app.js 各处挂钩子侵入更小；
    // 宽度过渡（.18s）期间 resize 事件不触发，RO 仍能逐帧跟上（与浮动按钮定位同套路）。
    window.addEventListener("resize", () => applyDockLayout());
    const dockEl = $("#-agent-dock");
    if (dockEl && typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => applyDockLayout()).observe($("#main"));
      new ResizeObserver(() => applyDockLayout()).observe($("#-sidebar"));
      new ResizeObserver(() => positionDockCollapseBtn()).observe(dockEl);
    }
    applyDockLayout(); // 首帧：按当前几何 + 默认期望宽度落一次（含三态文案）
    hydrateDockLayout(); // 磁盘值（若有）随后覆盖

    if (window.MemoriaI18n && window.MemoriaI18n.addRefresh) {
      window.MemoriaI18n.addRefresh(() => {
        applyConfigToForm();
        renderMessages();
        resetDeleteArmed(); // 语言切换后删除按钮文案随语言包（含复位二次确认）
        refreshHistoryLabels(); // 历史选项文案（含禁用态占位）随语言切换
        applyDockCollapsed(); // 语言切换后重绘按钮文案（含三态 title）
        renderStatusUsage(); // 状态栏用量格文案（中英）随语言切换
      });
    }

    renderMessages();
    setStatusText("");
    syncDeleteButton();
    refreshConfig();
    // 打开面板即刷新历史；若磁盘偏好里有「上次会话」且仍存在，则自动载入（静默）
    refreshHistory().then(() => restoreLastSession());
  }

  return {
    init: init,
    // 展开并刷新配置（旧版是「点开左栏对话页签」）；
    // 空间不足时不强行展开（setDockCollapsed 会保持隐藏并提示），保持"不挤压文档区"
    open: () => {
      if (dockCollapsed || dockAutoHidden) setDockCollapsed(false, true);
      else {
        refreshConfig();
        refreshHistory().then(() => restoreLastSession());
      }
    },
    // 知识库切换钩子（app.js 在 openKbAt/closeKb 处调用）：作废跨库会话并重试恢复
    onKbChanged: onKbChanged,
    clear: clear,
  };
})();
