/**
 * 应用内对话面板（**右侧独立停靠栏** `#-agent-dock`，M1 首版曾挂在左栏第 4 页签）。
 *
 * 自包含：DOM/事件绑定全部由本模块 init() 完成，不依赖 app.js 的 bindEvents：
 *   - 顶栏（右侧）`#btn-agent` → 停靠栏展开·收起（2026-09-18 起唯一入口：边缘浮动按钮
 *     `#agent-dock-collapse-btn` 已删除，改为 VSCode 式顶栏图标按钮）
 *   - `#agent-dock-resizer` 向左拖拽调宽（rem）→ 落盘 `layout.agentDockWidth`
 *   - `#agent-settings`（端点/模型/密钥/超时/出网）**2026-09-19 搬进设置弹窗「对话」页签**（`#settings-body-agent`）；`#agent-save-config` 保存端点配置
 *   - `#agent-net-toggle`「网络」开关（写 `config/agent.json` 的 enabled；2026-09-19 前文案是「出网」）
 *   - `#agent-input` Enter 发送 / Shift+Enter 换行；`#agent-send` 发送
 *   - `#agent-stop`「停止」（**真取消**：调 `agent_ask_cancel`，保留已生成的部分文本）
 *   - 开新会话：**无独立按钮**（原「清空对话」按钮已退役；左栏「历史」页签的「＋ 新会话」= 下方 `clear()`）
 *   - 会话列表在左栏「历史」页签（`#sidebar-view-history`）；dock 头部只留「当前会话 + 历史按钮」
 *   - `#agent-messages` 内锚点点击 → 跳转文件:行号
 *   - MemoriaI18n.addRefresh → 语言切换后重绘消息/状态/历史选项（静态节点由 i18n 引擎刷）
 *
 * **多轮续聊（M1c）**：本模块自持 `sessionId`（首次提问为 null）。`agent_ask_poll`
 * 返回的 `session_id` 存下来，之后的提问都带上它 ⇒ 后端按会话文件回放历史，形成多轮；
 * 「清空对话」= 把 `sessionId` 重置为 null（开新会话，旧会话已在磁盘上、进历史列表）。
 * `sessionKb` 记录该会话所属知识库，**只作 `ask()` 的兜底断言**（绝不给后端发别的库的
 * 会话 id），**不再是「是否重置面板」的判据**——后者由 `renderedKb`（当前气泡属于哪个
 * 库）承担，见「换库无条件重置」。
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
 * **会话历史（M1c；2026-09-19 起列表在左栏「历史」页签）**：由 `agent_sessions_list` 填充
 * （按修改时间倒序，最多 30 条），点某条 → `agent_session_load` 把消息灌进气泡区并把
 * `sessionId` 设为该会话（下一句即续聊）。列表/载入是**只读**；`agent_session_delete` 是
 * **本产品首次允许写知识库**（仅限会话目录 `.memoria/agent/sessions/<id>.jsonl`，
 * 见 10 篇 §2.15）。删除用**两次点击确认**（列表行内按钮），不弹窗。
 *
 * **恢复上次会话（M1 收尾；2026-09-18 起按库记）**：磁盘偏好
 * `config/ui-settings.json` 的**顶层 `agent` 段**里的 `lastSessionByKb`
 * （`{ "<库标识>": "<会话 id>" }`，库标识由 `kbKey()` 归一化）**只存当前库自己的**
 * 上次会话（提问成功/载入/恢复时写、清空时删条目）。面板打开或**切换知识库**时若该
 * 会话文件仍存在即自动载入（下一句即续聊）；不存在则**静默忽略**（不报错、不提示）
 * 并**清掉该陈旧条目**（避免每次打开都重试）。旧版全局单键 `agent.lastSessionId`
 * 由 `restoreLastSession()` **一次性迁移**：只有当该会话在当前库下确实能载入时才认领
 * （写入 map + 删除旧键），否则不动（留给它所属的库认领）。
 * 落盘见 `writeAgentPrefs()`——后端 `save_ui_settings` 对嵌套对象是**浅合并**
 * （`{**old, **new}`），**无法删除键**（旧 `lastSessionId` / 陈旧 map 条目），故必须
 * 「先置 `null` 迫使后端整体替换、再写目标对象」两步，**绝不覆盖 `layout` 段**。
 *
 * **换库无条件重置（2026-09-18）**：`onKbChanged()` 只要 `renderedKb !==` 当前库就
 * 重置面板（清空气泡、`sessionId=null`、`sessionKb=""`、`streamingEl=null`、用量格归零、
 * 重绘消息、清状态行）。**不再依赖 `sessionKb`**——它只在会话真正建立时才赋值，故
 * 「上一轮提问失败（未配置端点，只留用户气泡）后换库」的旧气泡会被漏掉（原缺陷）。
 * 换库时若有**属于别的库的在飞 `job`** ⇒ 递增 `epoch` 作废旧回调 + 并发调
 * `agent_ask_cancel(job_id)`（不阻塞 UI），语义与「清空对话」一致。
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

  // 答案里的 `文件:行号`（允许全角冒号 `：`、支持 `7-9` 区间；路径须排除中日韩标点 —— 原因与实测见 agent-guide/01 §7）
  const ANCHOR_RE = /`?"?'?([^\s`"'<>()[\]:：，、。；！？「」『』【】（）《》〈〉〔〕…·—～]+\.(?:md|markdown))[:：](\d+(?:[-–—~]\d+)?)`?"?'?/g;

  // 用户消息里的 `@路径` 引用（由文件树拖拽插入，也可手打）。
  // 语法语义移植自上游 `context/file-reference` 的 activeAtToken / formatFileMention：
  //   - `@` 必须是**一个 token 的开头**（行首或前面是空白）—— 邮箱 `a@b.com` 里的 `@` 不是引用；
  //   - `@"..."` 表示含空格的路径（收尾引号可缺，见 formatMention 的说明）；
  //   - 结尾带 `/` 表示目录。
  // 分组：1 = 前导（行首 / 空白，原样保留）2 = 完整 token 3 = 带引号的路径 4 = 裸路径
  const MENTION_RE = /(^|\s)(@"([^"]*)"?|@(\S+))/g;
  // 文件树拖拽载荷 MIME（发送端在 js/file-tree.js，同一字面量；改一处必须同步改另一处）
  const DRAG_MIME = "application/x-memoria-path";
  // 输入框「上次光标位置」：失焦后 selectionStart 会归 0，故拖拽落点按这份自己记的值插入
  let inputCaret = null;

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
  let job = null; // { id, cursor, epoch, kb }：在飞作业（null = 无）；kb = 提问时的库
  let busy = false; // 生成/轮询中（禁用发送）
  let streamingEl = null; // 正在流式写入的消息体元素
  // 世代号：每次提问递增；「清空对话」/「停止」/换库作废也递增 ⇒ 在飞回调据此作废
  let epoch = 0;

  // 多轮续聊：当前会话 id（null = 全新会话）与其所属知识库。
  // `sessionKb` 现仅作 `ask()` 的兜底断言（绝不把别的库的 id 发给后端）。
  let sessionId = null;
  let sessionKb = "";
  // 当前气泡区（`messages`）属于哪个库——换库判据；提问开始 / 载入会话成功时更新。
  let renderedKb = "";

  // 历史会话列表的缓存（供语言切换后就地重绘，无需重新请求）
  let historyRows = [];
  let historyDisabled = true;

  // 删除的二次确认超时（3s 内未再点即复位；不弹窗；左栏历史页签的行内删除用）
  const DELETE_CONFIRM_MS = 3000;

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

  /**
   * 把三态（手动折叠 / 空间不足自动隐藏 / 展开）落到 DOM：类名 + 顶栏按钮的 aria-pressed。
   * 2026-09-18：浮动收起按钮 `#agent-dock-collapse-btn` 已删除，展开入口只剩顶栏
   * `#btn-agent`（其 title 仍由 i18n 静态节点 `agent.btnTitle` 驱动，不在此改写，避免与
   * 语言包刷新抢写）；"空间不足"的提示改由 setDockCollapsed() 的 flash 承担
   * （`agent.dockNoSpace`，文案不变）。
   */
  function applyDockCollapsed() {
    const dock = $("#-agent-dock");
    const toolbarBtn = $("#btn-agent");
    if (dock) dock.classList.toggle("-agent-dock--collapsed", dockCollapsed);
    const hidden = dockCollapsed || dockAutoHidden;
    if (toolbarBtn) toolbarBtn.setAttribute("aria-pressed", String(!hidden));
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
   * 知识库标识归一化（`agent.lastSessionByKb` 的键）。
   * 同一库的不同写法必须落到**同一个键**，否则会分裂成多条：
   *   - 分隔符统一为 `\`（Windows 盘符/UNC 场景）；
   *   - 去掉尾部分隔符（`D:\A\` ≡ `D:\A`）；
   *   - **Windows 上再做大小写统一**（`toLowerCase`）——NTFS 大小写不敏感。
   * 读 / 写 / 迁移 / 清理**全部**经此函数，禁止在别处各自实现。
   */
  const IS_WINDOWS = /Windows/i.test((typeof navigator !== "undefined" && navigator.userAgent) || "");
  function kbKey(path) {
    const key = String(path == null ? "" : path).trim().replace(/\//g, "\\").replace(/\\+$/, "");
    return IS_WINDOWS ? key.toLowerCase() : key;
  }

  /** 读 `config/ui-settings.json` 顶层 `agent` 段（缺省返回 `{}`；失败返回 `{}`）。 */
  async function readAgentPrefs() {
    try {
      const res = await call("get_ui_settings");
      const seg = res && res.status === "ok" && res.settings && res.settings.agent;
      return seg && typeof seg === "object" ? Object.assign({}, seg) : {};
    } catch (_e) {
      return {};
    }
  }

  /** 取 `agent.lastSessionByKb` 里当前库记的会话 id（无 / 空 ⇒ null）。 */
  function lastSessionIdFor(agent, kb) {
    const map = agent && agent.lastSessionByKb;
    if (!map || typeof map !== "object") return null;
    const raw = map[kbKey(kb)];
    const id = typeof raw === "string" ? raw.trim() : "";
    return id || null;
  }

  /**
   * 写回 `config/ui-settings.json` 顶层 `agent` 段（`next` 为**目标完整对象**）。
   *
   * ⚠️ 必须**两步**「先置 `null` 再写目标」：后端 `save_ui_settings`
   * （`storage/ui_settings.py:58-75`）对嵌套对象走**浅合并**（`{**old, **new}`），
   * **无法删除键**——而本模块需要移除旧全局键 `lastSessionId` 与陈旧的 map 条目。
   * 先写 `{agent: null}`（非 dict ⇒ 后端走"整体替换"分支）再写目标对象，
   * 即可得到"现存键 = 目标键"的精确结果；两写之间的瞬时 `null` 会被立刻覆盖。
   * 绝不触碰 `layout` 段（后端顶层浅合并）。
   */
  async function writeAgentPrefs(next) {
    try {
      await call("save_ui_settings", { agent: null });
      await call("save_ui_settings", { agent: next });
    } catch (_e) { /* 非桌面环境：保持内存态 */ }
  }

  /**
   * 记住（`id` 非空）或清除（`id` 空）**当前库自己**的「上次会话 id」。
   * 同时**删除旧全局键 `lastSessionId`**（迁移收尾；此后不再读写它）。
   */
  async function setLastSessionId(kb, id) {
    if (!kb) return;
    const agent = await readAgentPrefs();
    const map =
      agent.lastSessionByKb && typeof agent.lastSessionByKb === "object"
        ? Object.assign({}, agent.lastSessionByKb)
        : {};
    const key = kbKey(kb);
    if (id) map[key] = String(id);
    else delete map[key];
    agent.lastSessionByKb = map;
    delete agent.lastSessionId;
    await writeAgentPrefs(agent);
  }

  /** 清掉某库的「上次会话」条目（陈旧条目清理 / 清空对话；条目不存在则不发写请求）。 */
  async function clearLastSessionId(kb) {
    if (!kb) return;
    const agent = await readAgentPrefs();
    const map =
      agent.lastSessionByKb && typeof agent.lastSessionByKb === "object"
        ? Object.assign({}, agent.lastSessionByKb)
        : {};
    const key = kbKey(kb);
    if (!(key in map)) {
      if (!("lastSessionId" in agent)) return; // 无条目也无旧键：无事可做
    }
    delete map[key];
    agent.lastSessionByKb = map;
    delete agent.lastSessionId;
    await writeAgentPrefs(agent);
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

  /**
   * 用户消息里的 `@相对路径` → 可点击跳转 chip（与答案里的 `-agent-anchor` 视觉区分：
   * 本类是 `-agent-mention`，目录再加 `--dir`）。目录 chip 点击 = 左栏树里定位，
   * 文件 chip 点击 = 打开该文件（复用锚点那套 `data-agent-file` 委托）。
   */
  function mentionChip(path, isDir) {
    const shown = isDir ? path.replace(/\/+$/, "") + "/" : path;
    const title = T(isDir ? "agent.mention.revealTitle" : "agent.mention.openTitle", { path: shown });
    return (
      '<span class="-agent-mention' +
      (isDir ? " -agent-mention--dir" : "") +
      '" role="link" tabindex="0" title="' +
      esc(title) +
      '" data-agent-file="' +
      esc(path.replace(/\/+$/, "")) +
      '"' +
      (isDir ? ' data-agent-dir="1"' : "") +
      ">" +
      esc(shown) +
      "</span>"
    );
  }

  /**
   * 用户消息渲染：先按 `@路径` 语法切分再逐段转义（**不先整体 esc**，避免路径里的
   * `&` 被二次转义成 `&amp;amp;`），非引用部分换行转 `<br>`。
   * 前导空白（分组 1）不进 chip、原样留在文本里，故 chip 从 token 起点开始。
   */
  function linkifyUser(text) {
    const raw = String(text == null ? "" : text);
    let out = "";
    let last = 0;
    for (const m of raw.matchAll(MENTION_RE)) {
      const token = m[2];
      const body = (m[3] !== undefined ? m[3] : m[4]) || "";
      const start = m.index + m[1].length;
      out += esc(raw.slice(last, start)).replace(/\n/g, "<br>");
      const path = body.replace(/\/+$/, "");
      out += path ? mentionChip(path, /\/$/.test(body)) : esc(token);
      last = start + token.length;
    }
    out += esc(raw.slice(last)).replace(/\n/g, "<br>");
    return out;
  }

  // ── 文件树 → 输入框拖拽 ─────────────────────────────────────────────

  /** dragover / drop 是否携带文件树拖拽载荷（只认自定义 MIME，不劫持普通文本拖放）。 */
  function hasMentionPayload(e) {
    const dt = e.dataTransfer;
    if (!dt) return false;
    return dt.types ? Array.from(dt.types).indexOf(DRAG_MIME) >= 0 : false;
  }

  /** 解析拖拽载荷 → `{path, kind:"file"|"dir"}`；无效返回 null。 */
  function readMentionPayload(e) {
    const dt = e.dataTransfer;
    if (!dt) return null;
    let raw = "";
    try {
      raw = dt.getData(DRAG_MIME) || "";
    } catch (_err) {
      return null;
    }
    if (!raw) return null;
    try {
      const obj = JSON.parse(raw);
      const path = String((obj && obj.path) || "").replace(/\\/g, "/");
      if (!path) return null;
      return { path, kind: obj.kind === "dir" ? "dir" : "file" };
    } catch (_err) {
      return null;
    }
  }

  /**
   * 把路径格式化为引用 token；**含空白时用上游的 `@"..."` 形式**
   * （语义移植自 `context/file-reference` 的 formatFileMention）。
   * 与上游的一处偏差：目录也**闭合引号** —— 上游留开引号是为了让编辑器继续逐级下钻
   * （`@"dir/sub`），而我们这里是"选中即完成"，闭合后消息文本才良构。
   */
  function formatMention(path, kind) {
    const p = kind === "dir" ? path.replace(/\/+$/, "") + "/" : path;
    return /\s/.test(p) ? '@"' + p + '"' : "@" + p;
  }

  /**
   * 把 `@相对路径` 插到输入框的**上次光标位置**（失焦后 `selectionStart` 归 0，故用自记的
   * `inputCaret`）；目录带尾斜杠。前面缺空白时补空格、末尾恒补一个空格，便于接着打字。
   */
  function insertMention(path, kind) {
    const input = $("#agent-input");
    if (!input) return;
    const p = String(path || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
    if (!p) return;
    const token = formatMention(p, kind);
    const len = input.value.length;
    const pos = Number.isInteger(inputCaret) ? Math.max(0, Math.min(inputCaret, len)) : len;
    const before = input.value.slice(0, pos);
    const after = input.value.slice(pos);
    // 前面缺空白则补一个；后面已紧跟空白就不再加尾空格（避免双空格）
    const ins = (before && !/\s$/.test(before) ? " " : "") + token + (after && /^\s/.test(after) ? "" : " ");
    input.value = before + ins + after;
    const caret = pos + ins.length;
    input.focus();
    try {
      input.setSelectionRange(caret, caret);
    } catch (_err) {
      // 非文本控件/不支持选区的宿主：忽略，至少内容已插入
    }
    inputCaret = caret;
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
    renderBody(body, rec.role, rec.text);
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
  // 列表渲染与删除见 IIFE 末尾的「左栏第 4 页签『历史』」块（`renderHistoryList` / `histDelete`）。
  // 下面两个绑定早年由 dock 的原生 `<select>` 行使用，2026-09-19 会话选择迁到左栏后，
  // 其实现已由该末尾块整体接管（此处的 `let` 声明供更早定义的函数调用，赋值在末尾块）。

  /** 刷新历史列表（打开面板 / 每次提问结束后 / 展开停靠栏 / 切换知识库时）；实现在 IIFE 末尾。 */
  let refreshHistory;

  /** 语言切换后就地重绘历史选项；实现在 IIFE 末尾。 */
  let refreshHistoryLabels;

  /**
   * 载入一个历史会话：灌进气泡区并把 `sessionId` 设为它（下一句即续聊）。
   * `silent=true`（恢复上次会话用）⇒ 失败**不报错、不提示**，只是不载入。
   * 返回后端响应对象（`{status:"ok",…}` 或 `{status:"error", code, …}`），供调用方判别
   * `unknown_session`（陈旧条目清理）。
   */
  async function loadSession(id, silent) {
    if (busy) return { status: "error", code: "busy" };
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
      }
      return res || { status: "error" };
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
    renderedKb = kb; // 气泡区现在属于本库
    resetStatusUsage(); // 历史会话的旧用量无法回算（会话视图不含 usage）⇒ 本会话累计从 0 起
    renderMessages();
    setStatusText(""); // 2026-09-19：状态行不再显示会话 id（用户不需要；会话身份在左栏「历史」列表里）
    setLastSessionId(kb, sessionId); // 记住**本库**的会话，供下次自动恢复（并清掉旧全局键）
    return res;
  }

  /**
   * 恢复上次会话（面板打开 / 切换知识库后）。
   *
   * 目标 id 取自 `agent.lastSessionByKb[<当前库>]`；若该条目不存在但存在**旧全局键**
   * `agent.lastSessionId`，则把它当候选（**一次性迁移**）：只有当它在**当前库**下确实
   * 能载入时才认领（`loadSession` 成功即写入 map 并删除旧键）；载入失败 ⇒ 不迁移、
   * 也不删（该会话可能属于别的库，留给它所属的库认领）。
   * map 条目存在但载入失败且后端报 `unknown_session` ⇒ 会话文件已不存在（**陈旧条目**）
   * ⇒ 静默空态并**删除该条目**（避免每次打开都重试）。
   * 同一（库, id）只尝试一次（`restoredKey` 幂等）。
   */
  async function restoreLastSession() {
    if (busy || job || messages.length || sessionId) return;
    const kb = state.kbPath || "";
    if (!kb) return;
    const agent = await readAgentPrefs();
    const mapped = lastSessionIdFor(agent, kb);
    const legacy = typeof agent.lastSessionId === "string" ? agent.lastSessionId.trim() : "";
    const fromLegacy = !mapped && !!legacy;
    const id = mapped || legacy;
    if (!id) return;
    const key = kbKey(kb) + "|" + id;
    if (restoredKey === key) return;
    restoredKey = key;
    const res = await loadSession(id, true);
    if (res && res.status === "ok") return; // 迁移/写入已由 loadSession → setLastSessionId 完成
    if (fromLegacy) return; // 旧键指向别的库（或已消失）：不迁移、不删
    if (res && res.code === "unknown_session") await clearLastSessionId(kb); // 陈旧条目：静默清理
  }

  /**
   * 知识库切换钩子（app.js 在开库/关库时调用）。
   *
   * **无条件重置**：只要当前气泡所属库（`renderedKb`）≠ 新库就清空面板——不依赖
   * `sessionKb`（后者只在会话真正建立时才有值，"上一轮提问失败只留用户气泡"时它仍为空，
   * 会让旧气泡残留 = 原缺陷）。换库时若在飞作业属于**别的库** ⇒ 递增 `epoch` 作废在飞
   * 回调 + 并发 `agent_ask_cancel`（不阻塞 UI），语义与「清空对话」一致。
   */
  function onKbChanged() {
    const kb = state.kbPath || "";
    if (renderedKb !== kb) {
      if (job && job.kb !== kb) {
        const jid = job.id;
        epoch += 1; // 作废在飞回调（含 poll 的下一帧）
        job = null;
        stopWait();
        busy = false;
        renderComposer();
        call("agent_ask_cancel", jid).catch(() => {}); // 并发取消后端作业，不阻塞 UI
      }
      sessionId = null;
      sessionKb = "";
      messages.length = 0;
      streamingEl = null;
      resetStatusUsage(); // 换库即作废本会话累计与状态栏用量格
      renderMessages();
      setStatusText("");
      renderedKb = kb;
    }
    restoredKey = "";
    refreshHistory();
    restoreLastSession();
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
      // 兜底路径（未加载缓冲模块时）；正常路径由末尾块包装本函数、按 safe 逐段渲染（AG11）
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
    // 兜底断言：绝不把**别的库**的会话 id 发给后端（正常路径由 onKbChanged 无条件重置保证；
    // 这里再判一次是纵深防御，不改变 sessionId/sessionKb 本身）。
    const kb = state.kbPath || "";
    const sessionForKb = sessionKb && sessionKb !== kb ? null : sessionId || null;
    renderedKb = kb; // 本问的用户气泡从此属于本库（换库判据）
    // 本问的世代号：清空/忽略/换库会递增 epoch，使本次提交与轮询结果一律作废
    const myEpoch = ++epoch;

    pushMessage("user", text);
    if (input) input.value = "";
    let res;
    try {
      res = await call("agent_ask_start", text, kb || null, sessionForKb);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (epoch !== myEpoch) return; // 提交期间被「清空对话」/换库作废 ⇒ 丢弃，不写回面板
    if (!res || res.status !== "ok" || !res.job_id) {
      const msg = fullErrorText(res);
      const rec = pushMessage("assistant", "");
      rec.error = msg;
      renderMessages();
      setStatusText(msg, true);
      showFlashError(msg);
      return;
    }
    job = { id: res.job_id, cursor: 0, epoch: myEpoch, kb: kb };
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
        // 后端把本次会话 id 回传：存下来，后续提问即续聊；并按库落盘供下次自动恢复
        sessionId = String(st.session_id);
        sessionKb = kbAtStart;
        renderedKb = kbAtStart;
        setLastSessionId(kbAtStart, sessionId);
      }
      const parts = [usageText(st.usage)]; // 2026-09-19：不再把会话 id 拼进状态行（用户不需要）
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
   * 同时**删掉当前库在 `lastSessionByKb` 里的条目**（新建会话不该恢复旧会话；
   * 只删本库条目，不动别的库）。
   */
  async function clear() {
    const jid = job ? job.id : "";
    const kb = state.kbPath || "";
    epoch += 1; // 作废在飞作业（若有）
    job = null;
    messages.length = 0;
    streamingEl = null;
    sessionId = null;
    sessionKb = "";
    renderedKb = kb; // 清空后空面板仍属于当前库
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
    clearLastSessionId(kb);
    refreshHistory();
  }

  // ── 锚点跳转 ────────────────────────────────────────────────────────

  function onAnchorClick(target) {
    const file = target.getAttribute("data-agent-file");
    if (!file) return;
    // 目录引用（`@docs/example/`）没有「打开」语义：在左栏文件树里展开并定位
    if (target.getAttribute("data-agent-dir")) {
      window.MemoriaFileTree?.revealDir?.(file);
      return;
    }
    const line = parseInt(target.getAttribute("data-agent-line") || "", 10);
    // openFile(relPath, {kpId, lineHint})：kpId 优先于 lineHint（app.js:1505-1517）
    const opts = { navSource: "agent" };
    if (Number.isFinite(line) && line > 0) opts.lineHint = line;
    openFile(file, opts);
  }

  // ── 装配 ────────────────────────────────────────────────────────────

  function init() {
    if (!$("#-agent-dock")) return; // 页面未登记右侧停靠栏（旧版 index.html）

    const save = $("#agent-save-config");
    if (save) save.addEventListener("click", () => saveConfig());
    const net = $("#agent-net-toggle");
    if (net) net.addEventListener("change", () => toggleNet(net.checked));
    const send = $("#agent-send");
    if (send) send.addEventListener("click", () => ask());
    const stopBtn = $("#agent-stop");
    if (stopBtn) stopBtn.addEventListener("click", () => stop());

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
      // 记录「上次光标位置」：失焦后 selectionStart 会归 0，而拖拽落点要用它
      const rememberCaret = () => {
        const p = input.selectionStart;
        if (Number.isInteger(p)) inputCaret = p;
      };
      ["keyup", "click", "select", "input", "blur"].forEach((ev) =>
        input.addEventListener(ev, rememberCaret)
      );
      // 文件树拖入（js/file-tree.js 发同名自定义 MIME）→ 插入 `@相对路径` 到上次光标位置。
      // 落点是**整个对话栏**（`#-agent-dock`，含消息区/历史和输入框；设置区已搬到设置弹窗），不是只有那个小输入框
      // —— 要求精准落到 textarea 上手感太别扭。只认自定义 MIME：普通文本/文件拖放
      // 不 preventDefault，保留浏览器默认行为。
      const dock = document.querySelector("#-agent-dock");
      const dropZone = dock || input;
      dropZone.addEventListener("dragover", (e) => {
        if (!hasMentionPayload(e)) return;
        e.preventDefault(); // 不 preventDefault 就不会触发 drop
        if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
        if (dock) dock.classList.add("-agent-dock--drop");
      });
      dropZone.addEventListener("dragleave", (e) => {
        // 子元素之间移动也会触发 dragleave，故只在真正离开对话栏时清高亮
        if (dock && !dock.contains(e.relatedTarget)) dock.classList.remove("-agent-dock--drop");
      });
      dropZone.addEventListener("drop", (e) => {
        if (dock) dock.classList.remove("-agent-dock--drop");
        if (!hasMentionPayload(e)) return;
        const payload = readMentionPayload(e);
        if (!payload) return;
        e.preventDefault();
        insertMention(payload.path, payload.kind);
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

    // 停靠栏显隐/调宽：顶栏 `#btn-agent` + 左缘拖拽柄（2026-09-18 起浮动按钮已删除）
    const toolbarBtn = $("#btn-agent");
    if (toolbarBtn) toolbarBtn.addEventListener("click", () => toggleDock());
    setupDockResize();
    // 重算生效宽度的触发时机全部收敛到「几何变化」：视口（含 uiScale 改根字号后的
    // 显式 resize 事件）+ 左栏宽度拖拽/折叠展开（#-sidebar 宽变）+ dock 自身。
    // 用 ResizeObserver 盯 #main / #-sidebar 比到 app.js 各处挂钩子侵入更小；
    // 宽度过渡（.18s）期间 resize 事件不触发，RO 仍能逐帧跟上。
    window.addEventListener("resize", () => applyDockLayout());
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => applyDockLayout()).observe($("#main"));
      new ResizeObserver(() => applyDockLayout()).observe($("#-sidebar"));
    }
    applyDockLayout(); // 首帧：按当前几何 + 默认期望宽度落一次（含顶栏按钮 aria-pressed）
    hydrateDockLayout(); // 磁盘值（若有）随后覆盖

    if (window.MemoriaI18n && window.MemoriaI18n.addRefresh) {
      window.MemoriaI18n.addRefresh(() => {
        applyConfigToForm();
        renderMessages();
        refreshHistoryLabels(); // 左栏「历史」列表文案（骨架按钮 / 过滤框占位 / 行内动作）随语言切换
        applyDockCollapsed(); // 语言切换后同步顶栏按钮 aria-pressed（title 由 i18n 静态节点刷）
        renderStatusUsage(); // 状态栏用量格文案（中英）随语言切换
      });
    }

    renderMessages();
    setStatusText("");
    refreshConfig();
    // 打开面板即刷新历史；若磁盘偏好里有「上次会话」且仍存在，则自动载入（静默）
    refreshHistory().then(() => restoreLastSession());
  }

  // ── 助手回复的 Markdown 渲染 ────────────────────────────────────────────
  // 面板原先只做「转义 + `文件:行号` 锚点 + `<br>`」，模型按 Markdown 写的标题/列表/表格
  // 全是原样文本。这里改成：`marked`（`vendor/marked.min.js`，GFM，与预览同一份配置）
  // → **净化** → 文本节点锚点化。模型输出**不是**授信内容（可能引用库内文本、也可能被提示
  // 注入），故净化是硬前置：只留白名单标签、**丢弃全部属性**。任一步失败或 `marked` 未加载
  // ⇒ 退回 `linkify()`（M1c 原路径），"渲染坏了也不至于看不了答案"。
  // 注：**2026-09-19（AG11）起生成期间也走本函数**——末尾块把 `applyDelta` 包成"按 `MemoriaStreamBuffer`
  // 的 `safe` 前缀渲染、未成型尾部进等待区"（逐行渲染）；上面这段是兜底（无缓冲模块时仍为纯文本）。

  //: 整棵丢弃的标签（脚本 / 内嵌文档 / 表单 / 媒体 / **远程图片**——后者还会顺带出网）。
  const MD_DROP_TAGS = new Set([
    "SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "LINK", "META", "BASE", "TEMPLATE",
    "FORM", "INPUT", "BUTTON", "SELECT", "OPTION", "TEXTAREA", "NOSCRIPT",
    "IMG", "PICTURE", "VIDEO", "AUDIO", "SOURCE", "TRACK", "CANVAS", "SVG", "MATH",
  ]);
  //: 允许保留的标签。其余一律「拆外壳、留文字」；**所有属性一律丢弃**（顺带消灭 `on*`、
  //: `href`、`src` —— 应用里没有任何外链跳转通道，留 `href` 只会让 webview 被导航走）。
  const MD_KEEP_TAGS = new Set([
    "P", "BR", "HR", "H1", "H2", "H3", "H4", "H5", "H6",
    "UL", "OL", "LI", "BLOCKQUOTE", "PRE", "CODE", "STRONG", "EM", "DEL", "S",
    "TABLE", "THEAD", "TBODY", "TFOOT", "TR", "TH", "TD", "SPAN", "DIV",
  ]);

  /** 一条消息正文的渲染入口：用户气泡走 `@引用` chip，助手气泡走 Markdown（含兜底）。 */
  function renderBody(el, role, text) {
    if (role === "user") {
      el.innerHTML = linkifyUser(text);
      return;
    }
    renderAssistantBody(el, text);
  }

  /** `文件:行号` 的可点锚点节点（与 `linkify()` 产出**同一份 DOM 形状**，样式与点击委托共用）。 */
  function anchorEl(file, line) {
    const span = document.createElement("span");
    span.className = "-agent-anchor";
    span.setAttribute("role", "link");
    span.setAttribute("tabindex", "0");
    span.setAttribute("data-agent-file", file);
    span.setAttribute("data-agent-line", line);
    span.textContent = file + ":" + line;
    return span;
  }

  /** 净化 `marked` 产物：只留 `MD_KEEP_TAGS` 且不带任何属性；`MD_DROP_TAGS` 连内容一起丢。 */
  function sanitizeHtmlInto(target, source) {
    Array.prototype.slice.call(source.childNodes || []).forEach(function (node) {
      if (node.nodeType === 3) {
        target.appendChild(document.createTextNode(node.nodeValue || ""));
        return;
      }
      if (node.nodeType !== 1) return; // 注释 / CDATA 等非元素非文本节点一律丢
      const tag = node.tagName;
      if (MD_DROP_TAGS.has(tag)) return;
      if (!MD_KEEP_TAGS.has(tag)) {
        sanitizeHtmlInto(target, node); // 未知或降级标签：拆外壳、保住里面的文字
        return;
      }
      const el = document.createElement(tag);
      sanitizeHtmlInto(el, node);
      target.appendChild(el);
    });
  }

  /** 在**已净化**的 DOM 里把 `文件:行号`（可被反引号包裹）换成可点锚点（只动文本节点）。 */
  function linkifyNodes(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const texts = [];
    while (walker.nextNode()) texts.push(walker.currentNode);
    texts.forEach(function (node) {
      const text = node.nodeValue || "";
      ANCHOR_RE.lastIndex = 0;
      if (!ANCHOR_RE.test(text)) return;
      ANCHOR_RE.lastIndex = 0;
      const frag = document.createDocumentFragment();
      let last = 0;
      let m;
      while ((m = ANCHOR_RE.exec(text)) !== null) {
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        frag.appendChild(anchorEl(m[1], m[2]));
        last = m.index + m[0].length;
      }
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      if (node.parentNode) node.parentNode.replaceChild(frag, node);
    });
  }

  /** 助手气泡正文渲染（失败/无 `marked` 时退回纯文本 + `<br>`）。 */
  function renderAssistantBody(el, text) {
    const src = String(text == null ? "" : text);
    const md = window.marked;
    if (!md || typeof md.parse !== "function") {
      el.innerHTML = linkify(src);
      return;
    }
    try {
      const tpl = document.createElement("template"); // template 内容惰性：脚本/图片不会先跑起来
      tpl.innerHTML = md.parse(src, { gfm: true, breaks: true });
      el.innerHTML = "";
      el.classList.add("markdown-body"); // 排版沿用预览的 .markdown-body（窄栏覆盖见 app.css）
      sanitizeHtmlInto(el, tpl.content);
      linkifyNodes(el);
    } catch (e) {
      el.classList.remove("markdown-body");
      el.innerHTML = linkify(src);
      console.warn("agent-md:", e);
    }
  }

  // ── 输入框上方的状态 bar（首版）────────────────────────────────────────
  // 结构 = 状态点（idle / busy / error / off）+ 一条「事实」串（模型 · 出网 · 会话 · 轮次）。
  // 分工：**事实与运行态**在这里常显；消息级长文案（「生成中… Ns」/ 错误原文 / 已停止）仍归
  // 下方 `#agent-status`，两者不重复同一句话。
  //
  // 挂接方式（刻意）：在模块尾部**包装本模块自己的 `renderMessages()` / `setStatusText()` /
  // `applyConfigToForm()`** —— 这三个入口已覆盖面板的全部状态流转（提交 / 轮询 / 定稿 / 出错 /
  // 停止 / 清空 / 载入会话 / 换库 / 保存配置 / 换语言），且**不改动上方既有函数里的任何一行**
  // ⇒ `agent-guide/01` 里那些 `agent-panel.js:<行号>` 锚点保持有效。
  // 若将来 bar 要接更细的来源（工具调用、token 预算、skill…），应把这些调用点**内联**进对应
  // 函数并**重取 01 篇的锚点**（那时是本注释让位于可读性的时候）。

  /** 状态点：生成中 > **出网关** > 出错 > 空闲。
   *
   * 「出网关」刻意排在「出错」之前：关闭出网时 `toggleNet()` 会把状态行置红（`agent.err.net_disabled`，
   * 见 `setStatusText(..., !cfg.enabled)`），若按"红字=出错"判，圆点会显示成故障 —— 但用户此刻看到的
   * 事实是「出网已关、不能发」，不是"出错了"。错误态直接读 `#agent-status` 的类，不新起状态变量。
   */
  function statusBarDotState() {
    if (busy) return "busy";
    if (!cfg.enabled) return "off";
    const st = $("#agent-status");
    if (st && st.classList.contains("-agent-error")) return "error";
    return "idle";
  }

  /** 重绘状态 bar（幂等、纯读当前状态；元素缺失时静默返回）。
   *
   * 文案**全部复用既有 i18n 键**（`agent.settings.model` / `agent.model.none` / `agent.net.label` /
   * `agent.model.netOff` / `agent.status.session` / `agent.history.none`）——
   * 首版刻意不新增键：往 `zh-CN.js` 的 `agent` 段插键会把它**之后**的所有行推位，牵动 01/02/04/06/07/08/09
   * 篇里十余处 `zh-CN.js:<行号>` 锚点。等 bar 的事实与措辞定下来再一次性补专用键（届时同步重取锚点）。
   */
  function renderStatusBar() {
    const dot = $("#agent-statusbar-dot");
    const facts = $("#agent-statusbar-facts");
    if (!dot || !facts) return;
    dot.setAttribute("data-state", statusBarDotState());
    const model = String(cfg.model || "") || T("agent.model.none");
    // 网络：开时显示「网络」并**上绿**，关时显示既有的「网络已关」并**上红**（颜色由 CSS 的 `data-on` 决定）
    const net = cfg.enabled ? T("agent.net.label") : T("agent.model.netOff");
    // 第四槽（2026-09-19 由「历史（N 轮）」改为**本会话缓存命中率**）：数字来自只读 RPC
    // `agent_usage_stats(session_id)` 的 `summary.hit_rate`（口径同底部 `#status-agent`；未知即 `—`）
    const rate = hitRatePercent();
    const tone = balanceTone(); // 余额的**对数连续色**（"" ⇒ 不染色：未知余额/取不到主题色）
    facts.innerHTML = [
      T("agent.settings.model") + " <b>" + esc(model) + "</b>",
      '<span class="-agent-statusbar-net" data-on="' + (cfg.enabled ? "1" : "0") + '">' + esc(net) + "</span>",
      // 余额槽（2026-09-19 取代原「会话 id」槽）：串由后端产出（`¥110.00`／`—`）⇒ 无需新增 i18n 键；悬停浮层**不再用原生 `title`**（该槽每次重绘都被换掉、悬停总被打断 ⇒ 原生提示弹不出来），改为**常驻的自绘浮层**（`#agent-costtip`，见文件末的成本块），此处只用 `aria-describedby` 指过去。金额文字另有**对数连续色**（越少越红、越多越绿，¥10 = 红端；算法见文件末 `balanceTone()`）。
      ('<span class="-agent-statusbar-balance"' + (tone ? ' style="color:' + tone + '"' : "") + ' aria-describedby="agent-costtip">' + esc(balanceText || "—") + "</span>"),
      esc(T("agent.statusBar.hitRate", { rate: rate || "—" })),
    ].join(" · ");
  }

  // 余额槽：**60s TTL** + 出网关闭时不发请求（后端 `fetch_balance` 还会再挡一次）。
  // 首次抓取**延后 1.5s**：RPC 是同步的，放在启动路径上会在最坏情况下（6s 超时）卡住首屏。
  let balanceText = "—", balanceAmount = null; // amount 供「对数连续色」用（`balanceTone()`，见文件末）
  let balanceFetchedAt = 0;

  function refreshBalance(force) {
    const now = Date.now();
    if (!force && now - balanceFetchedAt < 60000) return;
    balanceFetchedAt = now;
    if (!cfg.enabled) {
      balanceText = "—"; balanceAmount = null;
      renderStatusBar();
      return;
    }
    call("agent_balance")
      .then(function (res) {
        balanceText = (res && res.text) || "—"; // 数值由后端给（`total`），**不从前端解析 `text`**
        balanceAmount = res && typeof res.total === "number" ? res.total : null;
        renderStatusBar();
      })
      .catch(function () {
        balanceText = "—"; balanceAmount = null;
        renderStatusBar();
      });
  }

  setTimeout(function () {
    refreshBalance(true);
  }, 1500);

  // 包装（先留原函数引用再赋值；三处包装只多一次 bar 重绘，无副作用）
  const baseRenderMessages = renderMessages;
  renderMessages = function () {
    baseRenderMessages.apply(null, arguments);
    renderStatusBar();
  };
  const baseSetStatusText = setStatusText;
  setStatusText = function () {
    baseSetStatusText.apply(null, arguments);
    renderStatusBar();
  };
  const baseApplyConfigToForm = applyConfigToForm;
  applyConfigToForm = function () {
    baseApplyConfigToForm.apply(null, arguments);
    renderStatusBar();
    refreshBalance(true); // 换端点/换密钥后余额必须重查（force：不受 60s TTL 限制）
    refreshCost(true); // 换模型后价目表也变了（force 同上）
  };

  // ── 成本浮层（余额槽悬停，2026-09-19）───────────────────────────────────
  // 金额一律由后端 `agent_usage_cost` 给出（`services/agent/llm/pricing.py`：**官方价目表**、
  // **逐轮**按事件时间定高峰/空闲价后求和），前端只做本地化拼装与千分位/金额美化。
  // 刷新时机 = 每轮结束（包装 addSessionUsage）+ 载入历史会话（包装 loadSession）+ 换模型；
  // 30s TTL 兜底。**会话 id 未知时不请求**（不带 session_id 会扫全库，对悬停来说太重）。
  let costInfo = null;
  let costFetchedAt = 0;

  /** 金额文本（**不含货币符号** —— 单位由 i18n 模板带出：中文「元」/ 英文「CNY」）。
   *  小额多加两位：会话成本常在 1e-4 量级，4 位会把 `¥0.0000` 抹成 0。 */
  function moneyText(value) {
    const n = Number(value);
    if (!isFinite(n)) return "—";
    return n.toFixed(n > 0 && n < 0.0001 ? 6 : 4);
  }

  /** 悬停浮层文案（**数组，一行一条**）：首行按用户指定格式「命中:…tokens(…元)，未命中:…tokens(…元)」，
   *  次行注明口径与价格表日期；无可计价数据时只给一条「为什么没有」。 */
  function costTipLines() {
    const model = String(cfg.model || "") || T("agent.model.none");
    const c = costInfo;
    const date = (c && c.price_table) || "—";
    if (!c || !c.priced) return [T("agent.statusBar.costEmpty", { model: model, date: date })];
    return [
      T("agent.statusBar.costLine", {
        hitTokens: fmtTokens(c.hit_tokens),
        hitCost: moneyText(c.hit_cost),
        missTokens: fmtTokens(c.miss_tokens),
        missCost: moneyText(c.miss_cost),
      }),
      T("agent.statusBar.costNote", { model: model, date: date }),
    ];
  }

  /** **常驻**的成本浮层节点（懒建一次，挂在**稳定的** `#agent-statusbar` 上）。
   *
   *  ⚠️ 为什么不用原生 `title`、也不把浮层塞进余额槽（两版都栽在同一点上，2026-09-19 实测）：
   *  `renderStatusBar()` 会把 `#agent-statusbar-facts` 的 innerHTML **整串替换**（生成期间轮询
   *  每 250ms 一次），于是 —— ㈠ 原生提示要求指针在同一节点停留 0.5–1s，节点一换就被打断，
   *  提示永远弹不出来（用户报的"悬停没有显示详情"）；㈡ 把浮层放进 facts 串里，则每次重绘都会
   *  造出一个**新的、没带 `is-open`** 的浮层 ⇒ 悬停中被"关掉"（实测：重绘后 `is-open` 丢失）。
   *  故：节点**只建一次**、挂在 facts 之外（`#agent-statusbar` 是静态节点，永不重绘），
   *  文本由 `refreshCostTip()` 随重绘更新，展开状态因此在重绘中**保持**。 */
  let costTipNode = null;

  function ensureCostTip() {
    if (costTipNode && costTipNode.isConnected) return costTipNode;
    const host = document.getElementById("agent-statusbar");
    if (!host) return null;
    costTipNode = document.createElement("span");
    costTipNode.className = "-agent-costtip";
    costTipNode.id = "agent-costtip";
    costTipNode.setAttribute("role", "tooltip");
    host.appendChild(costTipNode);
    return costTipNode;
  }

  /** 浮层定位：右缘对齐金额槽、上弹到状态 bar 之上，再夹进视口（贴边不裁字）。
   *  `position: fixed` ⇒ 不受 `.-agent-statusbar-facts` 的 `overflow: hidden`（省略号截断）裁剪。 */
  function placeCostTip(tip) {
    const host = document.querySelector(".-agent-statusbar-balance");
    if (!host) return;
    const r = host.getBoundingClientRect();
    const box = tip.getBoundingClientRect();
    const left = Math.max(6, Math.min(r.right - box.width, window.innerWidth - box.width - 6));
    tip.style.left = Math.round(left) + "px";
    tip.style.top = Math.round(Math.max(6, r.top - box.height - 6)) + "px";
  }

  /** 重绘后刷新浮层文本（并保持它已展开状态与位置）。 */
  function refreshCostTip() {
    const tip = ensureCostTip();
    if (!tip) return;
    const html = costTipLines()
      .map(function (line) {
        return "<span>" + esc(line) + "</span>";
      })
      .join("");
    if (tip.innerHTML !== html) tip.innerHTML = html;
    if (tip.classList.contains("is-open")) placeCostTip(tip);
  }

  /** 指针在文档上移动：落在余额槽上就展开（并现算位置），否则收起。 */
  function syncCostTip(event) {
    const tip = ensureCostTip();
    if (!tip) return;
    const host =
      event.target && event.target.closest
        ? event.target.closest(".-agent-statusbar-balance")
        : null;
    if (!host || !tip.firstChild) {
      tip.classList.remove("is-open");
      return;
    }
    tip.classList.add("is-open");
    placeCostTip(tip);
  }

  // `renderStatusBar` 每次重绘后刷新浮层文本（**包装而非改行** ⇒ 上方行号锚点零漂移）。
  const baseRenderStatusBar = renderStatusBar;
  renderStatusBar = function () {
    baseRenderStatusBar.apply(null, arguments);
    refreshCostTip();
  };

  // 挂**文档级**监听（捕获阶段）而不是挂在余额槽上：余额槽每次重绘都被换掉，挂在它身上会随节点消失。
  // 指针一动就判一次"是否落在余额槽上"——不是就收起；`scroll`/`resize`/窗口失焦同样收起（避免浮层留在旧位置）。
  ["mousemove", "scroll", "resize"].forEach(function (type) {
    document.addEventListener(type, syncCostTip, true);
  });
  window.addEventListener("blur", function () {
    const tip = ensureCostTip();
    if (tip) tip.classList.remove("is-open");
  });

  // ══════════════════════════════════════════════════════════════════════════════
  // 状态 bar 的「事实着色」与第四槽（2026-09-19；用户："Network 有网就绿、没网就红；模型可用的
  // 那个点就绿、否则红；余额用对数连续色，越少越红越多越绿，¥10 就是本项目那个红；别再显示
  // History，改显示缓存命中率"）。
  //   ① 出网字样与状态点的颜色**全在 CSS**（`.-agent-statusbar-net[data-on]`，点按 `data-state`，
  //      见 app.css 末尾块）—— 那里只有两个静态色，不需要 JS；
  //   ② 余额色随金额**连续**变化 ⇒ CSS 做不了对数映射，由 `balanceTone()` 现算并写成内联 `color`；
  //   ③ 命中率取只读 RPC `agent_usage_stats(session_id)` 的 `summary.hit_rate`（**未知即 `—`，
  //      绝不瞎报 0%**），与成本同一节拍刷新（每轮结束 / 载入会话 / 换模型 / 清空）。
  // ──────────────────────────────────────────────────────────────────────────────

  /** 本会话缓存命中率（0..1 或 null；null = 无会话 / 端点未上报 cache）。 */
  let hitRateValue = null;

  /** 命中率百分比串（`62%`）；未知返回 `""`（调用方写 `—`）。 */
  function hitRatePercent() {
    if (typeof hitRateValue !== "number" || !isFinite(hitRateValue)) return "";
    return (hitRateValue * 100).toFixed(1).replace(/\.0$/, "") + "%";
  }

  /** `r,g,b`（0..255）→ `{h,s,l}`（h 为度、s/l 为 0..1）。 */
  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
    if (max === min) return { h: 0, s: 0, l: l };
    const d = max - min, s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return { h: h * 60, s: s, l: l };
  }

  /** 读一个主题色令牌（`--error` / `--success`）并转 HSL；**随主题解析**（深/浅各一份），
   *  取不到（非 6 位 hex / 空值）返回 `null` ⇒ 调用方退回不染色。 */
  function cssColorHsl(name) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const m = /^#([0-9a-f]{6})$/i.exec(raw);
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return rgbToHsl((n >> 16) & 255, (n >> 8) & 255, n & 255);
  }

  /** 余额的**对数连续色**：≤¥10 = `--error`（红端，用户指定的"本项目那个红"），≥¥1000 =
   *  `--success`（绿端），中间按 `log10` 线性取值并在**色相**上从红经黄/青插到绿（只插
   *  hue/sat/light ⇒ 中点不会糊成灰）。两个锚点是一条**可调**口径（用户只钉了红端 ¥10，
   *  绿端选了 ¥1000 = 两个数量级）；金额未知返回 `""`（不染色，保持继承色）。 */
  const BALANCE_RED_AT = 10;
  const BALANCE_GREEN_AT = 1000;

  function balanceTone() {
    if (typeof balanceAmount !== "number" || !isFinite(balanceAmount)) return "";
    const lo = Math.log10(BALANCE_RED_AT), hi = Math.log10(BALANCE_GREEN_AT);
    const x = Math.log10(Math.max(balanceAmount, 0.01)); // 0/负数先夹进 log 定义域（仍是红端）
    const t = Math.min(1, Math.max(0, (x - lo) / (hi - lo)));
    // 两端**直接用令牌**（而不是取整后的 hsl）⇒ 端点与 `--error` / `--success` 逐字节一致、且随主题变
    if (t <= 0) return "var(--error)";
    if (t >= 1) return "var(--success)";
    const a = cssColorHsl("--error"), b = cssColorHsl("--success");
    if (!a || !b) return "";
    const h = a.h + (b.h - a.h) * t, s = a.s + (b.s - a.s) * t, l = a.l + (b.l - a.l) * t;
    return "hsl(" + h.toFixed(0) + " " + (s * 100).toFixed(0) + "% " + (l * 100).toFixed(0) + "%)";
  }

  /** 命中率与成本**同一节拍**刷新（两者都只依赖会话文件）；`sid` 为空即清空为「未知」。 */
  function refreshHitRate(sid) {
    if (!sid) {
      hitRateValue = null;
      renderStatusBar();
      return;
    }
    call("agent_usage_stats", null, sid)
      .then(function (res) {
        const sum = res && res.status === "ok" ? res.summary : null;
        hitRateValue = sum && typeof sum.hit_rate === "number" ? sum.hit_rate : null;
        renderStatusBar();
      })
      .catch(function () {
        hitRateValue = null; // 取不到就当未知，绝不瞎报 0%
        renderStatusBar();
      });
  }

  function refreshCost(force) {
    const sid = sessionId ? String(sessionId) : "";
    if (!sid) {
      costInfo = null;
      refreshHitRate(""); // 无会话 ⇒ 命中率也随之回到「未知」
      renderStatusBar();
      return;
    }
    const now = Date.now();
    if (!force && now - costFetchedAt < 30000) return;
    costFetchedAt = now;
    refreshHitRate(sid); // 命中率与成本**同节拍**（两个独立 RPC、各自 fail-open）
    call("agent_usage_cost", sid)
      .then(function (res) {
        costInfo = res && res.status === "ok" ? res.cost : null;
        renderStatusBar();
      })
      .catch(function () {
        costInfo = null; // 取不到成本就只显示「暂无/未收录」口径，绝不影响其余状态
        renderStatusBar();
      });
  }

  const baseAddSessionUsage = addSessionUsage;
  addSessionUsage = function () {
    baseAddSessionUsage.apply(null, arguments);
    refreshCost(true); // 一轮结束 = 成本变了（不设 TTL，保证刚问完就能看到本次开销）
  };
  const baseLoadSession = loadSession;
  loadSession = function () {
    const pending = baseLoadSession.apply(null, arguments);
    // loadSession 是 async：等它把 sessionId 落定后再取成本
    Promise.resolve(pending).then(function () {
      refreshCost(true);
    });
    return pending;
  };
  const baseResetStatusUsage = resetStatusUsage;
  resetStatusUsage = function () {
    baseResetStatusUsage.apply(null, arguments);
    costInfo = null;
    renderStatusBar();
  };

  // ══════════════════════════════════════════════════════════════════════════════
  // 左栏第 4 页签「历史」= **会话选择**（2026-09-19；用户："关于会话选择的设计可以优化" →
  // "移到这里（左栏页签栏）做页签"）。原先是 dock 里一行：原生 `<select>` + 独立删除按钮，
  // 受限于原生控件（一条 option 塞不下"标题 + 轮数 + 时间"两行、不能挂行内动作、不可过滤）。
  // 迁到左栏页签后：两行式条目（标题 / 轮数 · 相对时间 · 截断标记）+ 顶部「＋ 新会话」与过滤框
  // + 行内删除（点两次确认）+ 点条目即载入并展开右侧对话栏。dock 那一行改为
  // 「当前会话：<标题> ＋ 历史按钮」⇒ 它仍是"我正看的是哪段对话"的指示器，
  // 两行高度与编辑区对齐（`--bar-h-b`）也不破。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // 说明：本块**整体接管** `refreshHistory()` / `refreshHistoryLabels()` 的实现（早年为 dock 的
  // 原生 `<select>` 而写；会话选择迁走后其旧实现已随本次清理删除），数据仍落在同一个模块级
  // `historyRows`。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 过滤串（纯客户端过滤标题/预览，不请求后端）。 */
  let histFilter = "";
  /** 进入"二次确认删除"的会话 id（超时/列表重绘即复位）。 */
  let histDeleteArmed = "";
  let histDeleteTimer = null;
  let histBound = false;

  function historyViewEl() {
    return document.getElementById("sidebar-view-history");
  }

  /** 相对时间（`刚刚` / `N 分钟前` …；超过 7 天给本地化日期）。`ms` = epoch 毫秒。 */
  function histAgo(ms) {
    const t = Number(ms);
    if (!isFinite(t) || t <= 0) return "";
    const diff = Date.now() - t;
    if (diff < 60000) return T("agent.historyList.justNow");
    if (diff < 3600000) return T("agent.historyList.minutesAgo", { n: Math.floor(diff / 60000) });
    if (diff < 86400000) return T("agent.historyList.hoursAgo", { n: Math.floor(diff / 3600000) });
    if (diff < 604800000) return T("agent.historyList.daysAgo", { n: Math.floor(diff / 86400000) });
    try {
      return new Date(t).toLocaleDateString();
    } catch (e) {
      return "";
    }
  }

  /** 条目标题：优先后端折叠出的标题，回落首问预览，再回落会话 id。 */
  function histTitle(row) {
    const s = row || {};
    return String(s.title || s.preview || s.session_id || "");
  }

  /** 建出页签视图骨架（只建一次；列表内容随 `renderHistoryList()` 重绘）。 */
  function ensureHistoryView() {
    const view = historyViewEl();
    if (!view || view.dataset.histReady === "1") return view;
    view.dataset.histReady = "1";
    view.innerHTML =
      '<div class="-hist-head">' +
      '<button type="button" class="-btn secondary -btn--sm" id="hist-new" title="' +
      esc(T("agent.historyList.newChatTitle")) +
      '">' +
      esc(T("agent.historyList.newChat")) +
      "</button>" +
      '<input type="search" id="hist-filter" class="-hist-filter" autocomplete="off" spellcheck="false" placeholder="' +
      esc(T("agent.historyList.filterPh")) +
      '" value="' +
      esc(histFilter) +
      '" />' +
      "</div>" +
      '<div class="-hist-list" id="hist-list" role="list"></div>';
    return view;
  }

  /** dock 那一行的「当前会话」文案（标题 / 会话 id 缩略 /（新会话））。 */
  function syncHistoryCurrentLabel() {
    const el = document.getElementById("agent-history-current");
    if (!el) return;
    const id = sessionId ? String(sessionId) : "";
    let row = null;
    for (let i = 0; i < historyRows.length; i += 1) {
      if (String((historyRows[i] || {}).session_id || "") === id) {
        row = historyRows[i];
        break;
      }
    }
    const text = id ? (row ? histTitle(row) : id.slice(0, 12) + "…") : T("agent.history.none");
    el.textContent = text;
    el.title = text;
  }

  /** 重绘列表（含过滤 / 当前项高亮 / 空态）＋ 同步页签计数与 dock 的「当前会话」。 */
  function renderHistoryList() {
    const view = ensureHistoryView();
    if (!view) return;
    const list = document.getElementById("hist-list");
    if (!list) return;
    const q = histFilter.trim().toLowerCase();
    const rows = historyRows.filter(function (row) {
      if (!q) return true;
      const hay = (histTitle(row) + " " + String((row && row.preview) || "")).toLowerCase();
      return hay.indexOf(q) >= 0;
    });
    if (!rows.length) {
      list.innerHTML =
        '<div class="-hist-empty -muted">' +
        esc(
          historyRows.length
            ? T("agent.historyList.filtered", { q: histFilter.trim() })
            : T("agent.historyList.empty")
        ) +
        "</div>";
    } else {
      list.innerHTML = rows
        .map(function (row) {
          const id = String((row && row.session_id) || "");
          const on = !!id && id === String(sessionId || "");
          const meta = [
            T("agent.historyList.turns", { n: (row && row.turn_count) || 0 }),
            histAgo(row && row.modified_at),
            row && row.capped ? T("agent.history.capped") : "",
          ]
            .filter(Boolean)
            .join(" · ");
          const title = histTitle(row);
          return (
            '<div class="-hist-row' +
            (on ? " -hist-row--current" : "") +
            '" data-hist-id="' +
            esc(id) +
            '" role="listitem" tabindex="0">' +
            '<div class="-hist-main">' +
            // 标题与徽章**分开**：徽章若嵌在 `.-hist-title` 里，会被那行的 `overflow:hidden` + 省略号一起吃掉
            // （长标题时「当前」标记就看不见了 —— 实测抓到）。
            '<div class="-hist-title-row">' +
            '<div class="-hist-title" title="' +
            esc(title) +
            '">' +
            esc(title) +
            "</div>" +
            (on ? '<span class="-hist-badge">' + esc(T("agent.historyList.current")) + "</span>" : "") +
            "</div>" +
            '<div class="-hist-meta -muted">' +
            esc(meta) +
            "</div>" +
            "</div>" +
            '<button type="button" class="-hist-del" data-hist-del="' +
            esc(id) +
            '" title="' +
            esc(T("agent.historyList.deleteTitle")) +
            '">' +
            esc(histDeleteArmed === id ? T("agent.historyList.deleteArm") : T("agent.history.delete")) +
            "</button>" +
            "</div>"
          );
        })
        .join("");
    }
    const count = document.getElementById("sidebar-tab-count-history");
    if (count) count.textContent = String(historyRows.length);
    syncHistoryCurrentLabel();
  }

  /** 点条目 = 载入该会话，并在必要时展开右侧对话栏（生成中不切换，与旧下拉同口径）。 */
  async function histOpen(id) {
    if (!id || busy) return;
    await loadSession(id);
    if (dockCollapsed || dockAutoHidden) setDockCollapsed(false, true);
  }

  /** 行内删除：第一次点进入确认态（超时复位），第二次才真删（复用既有 RPC 与善后逻辑）。 */
  async function histDelete(id) {
    if (!id) return;
    if (histDeleteArmed !== id) {
      histDeleteArmed = id;
      renderHistoryList();
      if (histDeleteTimer) clearTimeout(histDeleteTimer);
      histDeleteTimer = setTimeout(function () {
        histDeleteTimer = null;
        histDeleteArmed = "";
        renderHistoryList();
      }, DELETE_CONFIRM_MS);
      return;
    }
    histDeleteArmed = "";
    if (histDeleteTimer) {
      clearTimeout(histDeleteTimer);
      histDeleteTimer = null;
    }
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
    if (sessionId === id) {
      await clear(); // 删的是当前会话 ⇒ 回到「新会话」态
      restoredKey = ""; // 该会话已不存在：清掉幂等键，避免下次误判
    }
    await refreshHistory();
  }

  /** 把 dock 的「历史」按钮变成"左栏 → 历史页签"的入口（左栏收起时先展开）。 */
  function showHistoryTab() {
    const side = document.getElementById("-sidebar");
    const toggle = document.getElementById("btn-toggle-sidebar");
    if (side && side.classList.contains("-sidebar--collapsed") && toggle) toggle.click();
    const tab = document.querySelector('[data-sidebar-tab="history"]');
    if (tab) tab.click(); // 复用 app.js 的 setSidebarTab（含持久化与图谱启停）
    renderHistoryList();
  }

  /** 事件绑定（委托在视图容器上；只绑一次）。 */
  function bindHistoryView() {
    const view = historyViewEl();
    if (!view || histBound) return;
    histBound = true;
    view.addEventListener("click", function (ev) {
      const t = ev.target;
      if (!t || !t.closest) return;
      const del = t.closest("[data-hist-del]");
      if (del) {
        histDelete(del.getAttribute("data-hist-del"));
        return;
      }
      if (t.closest("#hist-new")) {
        clear(); // 与旧下拉的「（新会话）」同义
        return;
      }
      const row = t.closest("[data-hist-id]");
      if (row) histOpen(row.getAttribute("data-hist-id"));
    });
    view.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const row = ev.target && ev.target.closest ? ev.target.closest("[data-hist-id]") : null;
      if (!row) return;
      ev.preventDefault();
      histOpen(row.getAttribute("data-hist-id"));
    });
    view.addEventListener("input", function (ev) {
      if (!ev.target || ev.target.id !== "hist-filter") return;
      histFilter = String(ev.target.value || "");
      renderHistoryList(); // 只重绘列表 ⇒ 过滤框保持焦点与光标
    });
  }

  // 接管列表数据流：把实现落到左栏「历史」页签的列表上（`renderHistoryList()`）。
  refreshHistory = async function () {
    const kb = state.kbPath || "";
    if (!kb) {
      historyRows = [];
      historyDisabled = true;
      renderHistoryList();
      return;
    }
    let res;
    try {
      res = await call("agent_sessions_list", kb);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    const ok = !!res && res.status === "ok" && Array.isArray(res.sessions);
    historyRows = ok ? res.sessions : [];
    historyDisabled = !ok;
    renderHistoryList();
  };

  // 语言切换：骨架里的按钮文案与过滤框占位符也要换 ⇒ 清掉"已建"标记重建骨架（过滤串在 `histFilter` 里，不丢）。
  refreshHistoryLabels = function () {
    const view = historyViewEl();
    if (view) view.dataset.histReady = "";
    renderHistoryList();
  };

  // 载入会话 / 开新会话后同步列表高亮与 dock 的「当前会话」（包装 ⇒ 不改上方任何一行）。
  const baseLoadSessionForList = loadSession;
  loadSession = function () {
    const pending = baseLoadSessionForList.apply(null, arguments);
    Promise.resolve(pending).then(function () {
      renderHistoryList();
    });
    return pending;
  };
  const baseClearForList = clear;
  clear = function () {
    const pending = baseClearForList.apply(null, arguments);
    Promise.resolve(pending).then(function () {
      renderHistoryList();
    });
    return pending;
  };

  bindHistoryView();
  ensureHistoryView();
  renderHistoryList();
  const histDockBtn = document.getElementById("agent-history-open");
  if (histDockBtn) histDockBtn.addEventListener("click", showHistoryTab);

  // ══════════════════════════════════════════════════════════════════════════════
  // 跨会话引用（M2 收尾；语义移植自 dsh `packages/context/session-reference` 的 `uri.ts`）
  // ① 左栏「历史」每行加「引用」动作：把 `@[标题](dsh-session:<id>) ` 插到输入框（**不切会话**）；
  // ② 用户气泡里该 token 渲染成会话 chip（`data-agent-session`）：点它 = 切到「历史」页签并高亮
  //    那一行（**不载入**该会话 —— 载入仍由点条目本身负责）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // `linkifyUser` / `renderHistoryList` 都是「包一层」，不改其内部实现或行数。
  // ══════════════════════════════════════════════════════════════════════════════

  const SESSION_URI_PREFIX = "dsh-session:";
  // 与后端 `reference.py::_MENTION_RE`（及上游 `uri.ts:71`）同一形状：
  // 组 1 = Markdown label、组 2 = Markdown URI、组 3 = 裸 URI。
  const SESSION_MENTION_RE = /@\[((?:\\.|[^\\\]])*)\]\((dsh-session:[^\s)]*)\)|(dsh-session:[A-Za-z0-9_-]+)/g;
  // 被点中的会话行 id（重绘时保留高亮；空 = 无）。
  let histFlashId = "";

  /** 会话 id → 规范 URI（`base64url(JSON.stringify(id))`，无填充），与后端 `encode_session_uri` 逐字节一致。 */
  function sessionUri(id) {
    const bytes = new TextEncoder().encode(JSON.stringify(String(id == null ? "" : id)));
    let bin = "";
    for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
    return SESSION_URI_PREFIX + btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  /** 规范 URI → 会话 id；非规范/解不出字符串返回 null（渲染期**绝不抛错**，退回纯文本）。 */
  function decodeSessionUri(uri) {
    const raw = String(uri || "");
    if (raw.indexOf(SESSION_URI_PREFIX) !== 0) return null;
    const payload = raw.slice(SESSION_URI_PREFIX.length);
    if (!/^[A-Za-z0-9_-]+$/.test(payload)) return null;
    try {
      let b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
      while (b64.length % 4) b64 += "=";
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
      const parsed = JSON.parse(new TextDecoder().decode(bytes));
      return typeof parsed === "string" ? parsed : null;
    } catch (_err) {
      return null;
    }
  }

  /** `@[标题](uri)` token；label 里的 `\` 与 `]` 按上游口径转义（与后端 `format_session_mention` 同口径）。 */
  function formatSessionMentionToken(id, label) {
    const text = String(label == null || label === "" ? id : label);
    return "@[" + text.replace(/[\\\]]/g, function (m) { return "\\" + m; }) + "](" + sessionUri(id) + ")";
  }

  /** 会话 chip（与文件 `-agent-mention` 同族，叠 `--session` 区分；点击委托见下方 document 监听）。 */
  function sessionChip(id, label) {
    return (
      '<span class="-agent-mention -agent-mention--session" role="link" tabindex="0" title="' +
      esc(T("agent.mention.sessionTitle", { id: id })) +
      '" data-agent-session="' +
      esc(id) +
      '">@' +
      esc(label) +
      "</span>"
    );
  }

  /** 会话 mention 先于文件 `@路径` 解析：命中段直接出 chip，其余段交给原 `linkifyUser`。 */
  const baseLinkifyUser = linkifyUser;
  linkifyUser = function (text) {
    const raw = String(text == null ? "" : text);
    let out = "";
    let last = 0;
    for (const m of raw.matchAll(SESSION_MENTION_RE)) {
      const uri = m[2] !== undefined ? m[2] : m[3];
      const id = decodeSessionUri(uri);
      if (id === null) continue; // 非规范 URI：当普通文本，交给原 linkifyUser 处理
      const label = m[1] === undefined ? id : m[1].replace(/\\(.)/g, "$1");
      out += baseLinkifyUser(raw.slice(last, m.index));
      out += sessionChip(id, label);
      last = m.index + m[0].length;
    }
    out += baseLinkifyUser(raw.slice(last));
    return out;
  };

  /** 历史数据行（按 id 找 `historyRows` 里那条，供「引用」按钮取标题）。 */
  function histDataRow(id) {
    for (let i = 0; i < historyRows.length; i += 1) {
      if (String((historyRows[i] || {}).session_id || "") === id) return historyRows[i];
    }
    return null;
  }

  /** 把一段 token 插到输入框的上次光标位置（与上方 `insertMention` 同一套规则）。
   *  ⚠️ 这里**刻意重复**那 10 行而不是把 `insertMention` 抽出一个共用函数：本轮新增代码一律落在
   *  本追加块内，才能保住上方所有 `<文件>:<行号>` 锚点零漂移（那是本篇与 01/10 篇的取证底座）。 */
  function insertSessionToken(token) {
    const input = $("#agent-input");
    if (!input || !token) return;
    const len = input.value.length;
    const pos = Number.isInteger(inputCaret) ? Math.max(0, Math.min(inputCaret, len)) : len;
    const before = input.value.slice(0, pos);
    const after = input.value.slice(pos);
    const ins = (before && !/\s$/.test(before) ? " " : "") + token + (after && /^\s/.test(after) ? "" : " ");
    input.value = before + ins + after;
    const caret = pos + ins.length;
    input.focus();
    try {
      input.setSelectionRange(caret, caret);
    } catch (_err) {
      // 非文本控件/不支持选区的宿主：忽略，至少内容已插入
    }
    inputCaret = caret;
  }

  /** 把会话 mention 插到输入框（**不切换当前会话**）。 */
  function quoteSession(id) {
    if (!id) return;
    const row = histDataRow(id);
    insertSessionToken(formatSessionMentionToken(id, row ? histTitle(row) : id));
  }

  /** 历史行装「引用」按钮 + 命中高亮（追加在既有行 DOM 上，不改 `renderHistoryList` 内部）。 */
  function decorateHistoryRows() {
    const list = document.getElementById("hist-list");
    if (!list) return;
    const rows = list.querySelectorAll("[data-hist-id]");
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      const id = row.getAttribute("data-hist-id") || "";
      if (histFlashId && id === histFlashId) row.classList.add("-hist-row--referenced");
      if (!id || row.querySelector("[data-hist-quote]")) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "-hist-quote";
      btn.setAttribute("data-hist-quote", id);
      btn.title = T("agent.historyList.quoteTitle");
      btn.textContent = T("agent.historyList.quote");
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation(); // 别让行点击把这条会话载入
        quoteSession(id);
      });
      btn.addEventListener("keydown", function (ev) {
        if (ev.key !== "Enter" && ev.key !== " ") return;
        ev.preventDefault();
        ev.stopPropagation();
        quoteSession(id);
      });
      const del = row.querySelector("[data-hist-del]");
      if (del) row.insertBefore(btn, del);
      else row.appendChild(btn);
    }
  }

  const baseRenderHistoryList = renderHistoryList;
  renderHistoryList = function () {
    const pending = baseRenderHistoryList.apply(null, arguments);
    decorateHistoryRows();
    return pending;
  };

  /** 点会话 chip：切到左栏「历史」页签并高亮那一行（**不载入**该会话）。 */
  function highlightSessionInHistory(id) {
    if (!id) return;
    histFlashId = id;
    showHistoryTab(); // 内部已 renderHistoryList ⇒ 高亮随之生效
  }

  // 会话 chip 的点击/键盘委托：挂在 `document` 上 ⇒ 与面板初始化时机无关，也不动既有气泡监听。
  document.addEventListener("click", function (ev) {
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-agent-session]") : null;
    if (t) highlightSessionInHistory(t.getAttribute("data-agent-session"));
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-agent-session]") : null;
    if (!t) return;
    ev.preventDefault();
    highlightSessionInHistory(t.getAttribute("data-agent-session"));
  });

  renderHistoryList(); // 用包装后的版本重绘一次（列表为空时是空操作）

  // ══════════════════════════════════════════════════════════════════════════════
  // 模型思考流（AG08；思考增量此前只被后端解析、从未送到面板）
  // ① 后端 `agent_ask_poll` 新增独立游标 `reasoning_cursor` 与增量 `reasoning_delta`；
  //    基座 `poll()` 只认文本的 `delta`/`cursor`（一行未改），故在**门面 `call`** 上包一层：
  //    发 `agent_ask_poll` 时补上第三个位置参数（思考游标），收到响应先落思考增量再交还原逻辑。
  // ② 思考渲染成助手气泡里的**折叠块**（`<details class="-agent-think">`），排在答案正文之前：
  //    流式期间展开、跟随增量实时更新（`textContent`，与流式正文同一条插入路径，不新造渲染器）；
  //    定稿后**默认折叠但常驻 DOM**，用户可随时展开（`messageEl` 包装负责重建）。
  // ③ **无思考则整块不存在**（首个非空增量才创建，`rec.reasoning` 为空时不插入 ⇒ 无空块、无跳变）。
  // ④ 思考**不落会话文件**：会话文件同时是读取路径的事实源（列表 2 MiB 扫描、`agent_session_load`
  //    直接回放成渲染视图）⇒ 重载页面或载入旧会话都**不显示过往思考**（有意偏差，上游 dsh 会持久化；
  //    口径见 services/agent/ask_stream.py 模块 docstring）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  //: 已投递的思考字符数（**与文本游标完全独立**）；每轮提问由 `ask()` 包装重置。
  let reasoningCursor = 0;

  /** 思考折叠块骨架；`open` = 流式期间展开、定稿后折叠；`text` = 定稿重绘时回填的已有思考。 */
  function thinkEl(open, text) {
    const box = document.createElement("details");
    box.className = "-agent-think";
    if (open) box.open = true;
    const summary = document.createElement("summary");
    summary.className = "-agent-think-summary";
    summary.textContent = T("agent.think");
    box.appendChild(summary);
    const body = document.createElement("div");
    body.className = "-agent-think-body";
    body.textContent = text || "";
    box.appendChild(body);
    return box;
  }

  /** 流式期间确保当前助手气泡里有思考块（首个非空增量才创建 ⇒ 无思考则完全无此节点）。 */
  function ensureThinkBlock() {
    if (!streamingEl) return null;
    const wrap = streamingEl.parentElement;
    if (!wrap) return null;
    let box = wrap.querySelector(".-agent-think");
    if (!box) {
      box = thinkEl(true); // 生成中：展开跟随
      wrap.insertBefore(box, streamingEl); // 排在答案正文**之前**
      scrollToBottom();
    }
    return box;
  }

  /** 把一片思考增量追加到当前助手气泡（复用流式正文的 `textContent` 路径，纯文本、无 HTML 注入）。 */
  function applyReasoningDelta(delta) {
    const rec = currentAssistant();
    if (!rec) return;
    rec.reasoning = (rec.reasoning || "") + delta;
    const box = ensureThinkBlock();
    if (!box) return;
    const body = box.querySelector(".-agent-think-body");
    if (body) body.textContent = rec.reasoning;
    scrollToBottom();
  }

  // 定稿/重绘都经 `messageEl`：思考非空才在正文前插入**折叠**常驻块（`rec.reasoning` 由增量累积）。
  const baseMessageEl = messageEl;
  messageEl = function (rec) {
    const wrap = baseMessageEl.apply(null, arguments);
    if (rec && rec.role === "assistant" && rec.reasoning) {
      const body = wrap.querySelector(".-agent-msg-body");
      if (body) wrap.insertBefore(thinkEl(false, rec.reasoning), body);
    }
    return wrap;
  };

  // 每轮提问重置思考游标（基座 `ask()` 的 job 游标是每轮新建，思考游标同口径）。
  const baseAsk = ask;
  ask = function () {
    reasoningCursor = 0;
    return baseAsk.apply(null, arguments);
  };

  // 门面 `call` 包装：只干预 `agent_ask_poll`（其余方法原样透传，不改任何调用方语义）。
  const facade = A();
  const baseFacadeCall = facade && facade.call;
  if (typeof baseFacadeCall === "function") {
    facade.call = function (fnName) {
      if (fnName !== "agent_ask_poll") return baseFacadeCall.apply(this, arguments);
      const args = Array.prototype.slice.call(arguments);
      args.push(reasoningCursor); // 第 3 个位置参数 = 思考游标（后端 AG08 追加的可选参数）
      const pending = baseFacadeCall.apply(this, args);
      return Promise.resolve(pending).then(function (res) {
        if (res && typeof res.reasoning_cursor === "number") reasoningCursor = res.reasoning_cursor;
        if (res && typeof res.reasoning_delta === "string" && res.reasoning_delta) {
          applyReasoningDelta(res.reasoning_delta);
        }
        return res;
      });
    };
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // 流式中间缓冲（AG11；用户："memoria 做一层中间缓冲，既起到缓冲作用，又可以让输出的
  // 内容逐行渲染…而不是输出完才渲染"）
  // ① 分割器是**纯函数**独立文件 `app/js/agent-stream-buffer.js`（`window.MemoriaStreamBuffer.split`，
  //    VM 单测见 `scripts/benchmark/maintenance/agent_stream_buffer_test.js`）：`safe` = 可安全渲染的
  //    最长前缀（恒以换行收尾），`pending` = 未成型尾部，`openBlock` = 扣住尾部的构造。
  // ② 生成期间：`safe` 交**既有** `renderAssistantBody()`（marked → 净化 → 锚点化，不新造渲染器）
  //    渲染；`pending` 落到正文下方的**等待区** `.-agent-stream-wait`：代码块 / `$$` 公式块 /
  //    文首 frontmatter 给纯 CSS 转圈进度条 + 提示（i18n `agent.stream.*`）+ 原文，普通半行只给原文。
  //    这样表格"给完一行就渲染一行"，代码块/公式则等闭合（期间转圈），不会渲染出半截结构。
  // ③ 定稿（`done`）仍走既有 `finalizeMessage()`（后端 `answer` 为准、整段重绘）并清掉等待区 ⇒
  //    "flush，绝不丢字"；工具轮无文本增量时 safe/pending 皆空 ⇒ 不渲染任何额外节点。
  // ④ **只包装、不改既有函数体**：`applyDelta`（流式渲染入口）、`finalizeMessage`、`stopWait`
  //    （所有终止路径——定稿/超时/停止/清空/换库——都会调它）在末尾块被包一层 ⇒ 上方所有
  //    `<文件>:<行号>` 锚点零漂移；未加载缓冲模块或无流式元素时原样回落到旧路径（纯文本）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 缓冲模块是否就绪（未加载 ⇒ 全程走旧路径，面板不因缺件而坏）。 */
  function streamBufferReady() {
    const buf = window.MemoriaStreamBuffer;
    return !!(buf && typeof buf.split === "function");
  }

  //: `openBlock` → 等待区提示键（`line` 无提示、无进度条）。
  const STREAM_BLOCK_HINTS = {
    fence: "agent.stream.fence",
    math: "agent.stream.math",
    frontmatter: "agent.stream.frontmatter",
  };

  /** 清掉消息区里所有等待区节点（幂等；定稿重建整条气泡时通常已被一起换掉）。 */
  function clearStreamWait() {
    const box = $("#agent-messages");
    if (!box) return;
    const nodes = box.querySelectorAll(".-agent-stream-wait");
    for (let i = 0; i < nodes.length; i += 1) {
      if (nodes[i].parentNode) nodes[i].parentNode.removeChild(nodes[i]);
    }
  }

  /** 等待区骨架（**幂等复用**：每 250ms 一帧只改文本/属性，不重建节点 ⇒ 无闪烁）。 */
  function ensureStreamWait(wrap) {
    let box = wrap.querySelector(".-agent-stream-wait");
    if (!box) {
      box = document.createElement("div");
      box.className = "-agent-stream-wait";
      const spin = document.createElement("span");
      spin.className = "-agent-stream-wait-spin";
      spin.setAttribute("aria-hidden", "true");
      const hint = document.createElement("span");
      hint.className = "-agent-stream-wait-hint";
      const raw = document.createElement("pre");
      raw.className = "-agent-stream-wait-raw";
      box.appendChild(spin);
      box.appendChild(hint);
      box.appendChild(raw);
      // 排在正文之后、来源条/错误条之前（生成期间后者尚不存在）
      if (streamingEl.nextSibling) wrap.insertBefore(box, streamingEl.nextSibling);
      else wrap.appendChild(box);
    }
    return box;
  }

  /** 生成中一帧：`safe` 走既有 markdown 路径，`pending` 落等待区（两段拼接=全文，无重叠）。 */
  function renderStreamFrame(rec) {
    const wrap = streamingEl.parentElement;
    if (!wrap) return;
    const parts = window.MemoriaStreamBuffer.split(rec.text);
    if (parts.safe) {
      renderAssistantBody(streamingEl, parts.safe);
    } else {
      streamingEl.innerHTML = "";
      streamingEl.classList.remove("markdown-body");
    }
    if (parts.pending) {
      const box = ensureStreamWait(wrap);
      box.setAttribute("data-block", parts.openBlock);
      const key = STREAM_BLOCK_HINTS[parts.openBlock] || "";
      const hint = box.querySelector(".-agent-stream-wait-hint");
      const spin = box.querySelector(".-agent-stream-wait-spin");
      if (hint) {
        hint.hidden = !key;
        hint.textContent = key ? T(key) : "";
      }
      if (spin) spin.hidden = !key; // 普通半行（line）不给进度条：这就是正常打字
      const raw = box.querySelector(".-agent-stream-wait-raw");
      if (raw) raw.textContent = parts.pending;
    } else {
      clearStreamWait();
    }
    scrollToBottom();
  }

  // 流式渲染入口：有缓冲模块且正文元素在场时走"分割渲染"，否则原样回落旧路径。
  const baseApplyDelta = applyDelta;
  applyDelta = function (delta) {
    const rec = currentAssistant();
    if (!delta || !rec || !streamingEl || !streamBufferReady()) {
      return baseApplyDelta.apply(null, arguments);
    }
    rec.text += delta;
    try {
      renderStreamFrame(rec);
    } catch (e) {
      // 分割/渲染异常（含缓冲模块被替换）：退回纯文本，**不再追加 delta**（避免重复）
      console.warn("agent-stream:", e);
      streamingEl.textContent = rec.text;
      clearStreamWait();
    }
  };

  // 定稿：先清等待区，再交既有逻辑（后端 answer 为准、整段重绘）——flush，绝不丢字。
  const baseFinalizeMessage = finalizeMessage;
  finalizeMessage = function () {
    clearStreamWait();
    return baseFinalizeMessage.apply(null, arguments);
  };

  // 所有终止路径（定稿/超时/停止/清空/换库）都会调 stopWait ⇒ 在此兜底清等待区（含超时无重绘那一支）。
  const baseStopWait = stopWait;
  stopWait = function () {
    clearStreamWait();
    return baseStopWait.apply(null, arguments);
  };

  // ══════════════════════════════════════════════════════════════════════════════
  // 每轮 token 用量行（2026-09-19；用户："对话框下方的 tokens 花费计算做到 agent 最后一次回复的
  // 对话框下方，并且格式应该为『用量 xx(命中)+xx(未命中)=xx tokens』"）
  //   ① 数据来源 = 每轮 `agent_ask_poll` 的 `usage`（后端 `AskJob.usage` ← `LoopResult.usage`）——
  //      这是**本轮**口径：一次提问内的若干 LLM 轮次（含工具调用轮）已由 `Usage.plus()` 逐轮
  //      求和（`services/agent/loop.py:289,314`）；缓存两字段由
  //      `services/agent/llm/providers/openai_compatible.py::_usage_from_wire()` 按端点形态择一
  //      读取（DeepSeek 顶层 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`；OpenAI 形态
  //      `prompt_tokens_details.cached_tokens`，未命中量按 `prompt - cached` 推得）；两者皆缺时
  //      `cache_*=None`。
  //   ② `{total}` = `hit + miss`（与用户给的式子一致）；端点未上报缓存字段时不臆造 0 ——
  //      命中/未命中显示 `—`，`{total}` 回落为端点上报的 `total_tokens`。
  //   ③ 只挂在**最后一条助手气泡**上：每次重绘先清掉全部 `.-agent-usage` 再挂一次 ⇒ 新一轮
  //      结束时上一条的副本被移除，不留过期副本。
  //   ④ 挂载时机复用既有路径（`poll()` 拿到本轮 usage 后调 `renderStatusUsage()`，见 `1358-1365`
  //      的既有代码；整串重绘走 `renderMessages()`），只**包装**这两个函数、不改其函数体。
  //   ⑤ 正文仍走既有 markdown 渲染（AG11 流式路径不受影响）：本行是定稿后**追加**的纯文本节点
  //      （`textContent`），不参与流式重绘，也不影响 AG08 思考块（它在正文之前）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  /** token 数文本：英文用千分位（`1,234`）、中文原样（`1234`）；未知（null）返回 `—`。 */
  function usageNumText(value) {
    const n = usageInt(value);
    if (n === null) return "—";
    const i18n = window.MemoriaI18n;
    const lang = i18n && i18n.currentLang ? i18n.currentLang() : "zh-CN";
    return lang === "en" ? n.toLocaleString("en-US") : String(n);
  }

  /** 本轮用量行文案；无总量（无本轮 usage）返回 ""（调用方据此不挂节点）。 */
  function usageLineText(u) {
    if (!u || !u.total_tokens) return "";
    const hit = usageInt(u.cache_read_tokens);
    const miss = usageInt(u.cache_miss_tokens);
    const total = hit !== null && miss !== null ? hit + miss : usageInt(u.total_tokens);
    return T("agent.usage.line", {
      hit: usageNumText(hit),
      miss: usageNumText(miss),
      total: usageNumText(total),
    });
  }

  // 哪条助手消息"拥有"当前 `lastUsage`。**按消息对象记录**（而不是"DOM 里最后一条助手气泡"）：
  // 生成中「停止」会 `renderMessages()` 整串重绘，若按 DOM 末条定位，上一轮的用量行会被错挂到
  // 本次（被停止的）气泡上；按归属重定位则始终回到产出该 usage 的那条气泡。
  let usageOwner = null;
  // 上次见到的 usage 对象（身份比较）：`poll()` 每轮**新建** usage 对象 ⇒ 身份变化即"新一轮落定"；
  // 语言切换 / 整串重绘时对象不变 ⇒ 归属不被改写。
  let usageSeen = null;

  /** 清掉消息区里所有用量行（幂等；整串重绘时通常已被一起换掉）。 */
  function clearUsageLines() {
    const box = $("#agent-messages");
    if (!box) return;
    const nodes = box.querySelectorAll(".-agent-usage");
    for (let i = 0; i < nodes.length; i += 1) {
      if (nodes[i].parentNode) nodes[i].parentNode.removeChild(nodes[i]);
    }
  }

  /** `rec` 在「助手消息」里的序位（0 起）；不在 `messages` 里返回 -1。 */
  function assistantOrdinal(rec) {
    let ordinal = -1;
    for (let i = 0; i < messages.length; i += 1) {
      if (messages[i].role !== "assistant") continue;
      ordinal += 1;
      if (messages[i] === rec) return ordinal;
    }
    return -1;
  }

  /** 重绘用量行：只挂在**拥有该 usage 的那条助手气泡**末尾（全面板最多一份）；无则只清不挂。 */
  function renderTurnUsage() {
    clearUsageLines();
    const text = usageLineText(lastUsage);
    if (!text || !usageOwner) return;
    const ordinal = assistantOrdinal(usageOwner);
    if (ordinal < 0) {
      usageOwner = null; // 那条消息已被清空/换会话 ⇒ 不再有归属
      return;
    }
    const box = $("#agent-messages");
    if (!box) return;
    const wraps = box.querySelectorAll(".-agent-msg--assistant");
    const wrap = ordinal < wraps.length ? wraps[ordinal] : null;
    if (!wrap) return;
    const line = document.createElement("div");
    line.className = "-agent-usage -muted";
    line.textContent = text;
    wrap.appendChild(line);
  }

  // 本轮 usage 落定（`poll()` 更新 `lastUsage` 后调 `renderStatusUsage()`）⇒ 记归属并同步刷新用量行；
  // `resetStatusUsage()`（清空/载入历史/换库）也走这里 ⇒ `lastUsage=null` 时自动清行与归属。
  const baseRenderStatusUsageForTurn = renderStatusUsage;
  renderStatusUsage = function () {
    baseRenderStatusUsageForTurn.apply(null, arguments);
    if (lastUsage !== usageSeen) {
      usageSeen = lastUsage;
      usageOwner = lastUsage && lastUsage.total_tokens ? currentAssistant() : null;
    }
    renderTurnUsage();
  };
  // 整串重绘（清空/停止/载入会话/语言切换）会丢掉该行 ⇒ 之后按同一 `lastUsage` 重新挂上。
  const baseRenderMessagesForTurn = renderMessages;
  renderMessages = function () {
    const out = baseRenderMessagesForTurn.apply(null, arguments);
    renderTurnUsage();
    return out;
  };

  // ══════════════════════════════════════════════════════════════════════════════
  // 状态 bar 刷新间隔（2026-09-19；用户："对话框上 bar 栏状态设置更新间隔，在设置面板配置，
  // 有 5s 15s 30s 1min 5min 10min 1h"）
  //   ① 持久化 = `config/agent.json` 的 `status_refresh_ms`（毫秒整数，白名单键），与端点/模型
  //      同一条 `agent_get_config` / `agent_save_config` RPC（`services/agent/llm/config.py`）。
  //      设置面板「对话」页签里的 `<select id="agent-refresh">`（index.html 静态体），改选即写盘
  //      （同「网络」开关的即时保存口径）。
  //   ② 默认 **60000 ms（1min）** —— 与今天唯一的固定节拍一致：余额槽的 60s TTL
  //      （`refreshBalance()` 的 `now - balanceFetchedAt < 60000`）＋成本/命中率的 30s TTL。
  //   ③ 计时器**只驱动既有**的 `refreshBalance()` / `refreshCost()`（状态 bar 的余额与成本/命中率），
  //      不新增任何槽位与 UI；改设置时先 `clearInterval` 再按新间隔重挂 ⇒ 无需重启。
  //   ④ 1h 是真选项：`setInterval(3600000)` 每小时才碰一次余额 RPC（该 RPC 会出网）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方行号锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  const DEFAULT_STATUS_REFRESH_MS = 60000;
  //: 7 档（用户指定）——值即毫秒。
  const STATUS_REFRESH_CHOICES = [5000, 15000, 30000, 60000, 300000, 600000, 3600000];
  //: 7 档 → i18n 文案键（中英一一对应）。
  const STATUS_REFRESH_KEYS = {
    5000: "agent.settings.refresh5s",
    15000: "agent.settings.refresh15s",
    30000: "agent.settings.refresh30s",
    60000: "agent.settings.refresh1m",
    300000: "agent.settings.refresh5m",
    600000: "agent.settings.refresh10m",
    3600000: "agent.settings.refresh1h",
  };
  let statusRefreshTimer = null;

  /** 生效间隔（ms）：只认 7 档之一；未配置/越界 ⇒ 默认 1min（即今天的节拍）。
   *  `Number(...)` 只为容错（后端回的是毫秒整数；手改 agent.json 成了字符串也不至于回落到默认）。 */
  function statusRefreshMs() {
    const v = usageInt(Number(cfg.status_refresh_ms));
    return v !== null && STATUS_REFRESH_CHOICES.indexOf(v) !== -1 ? v : DEFAULT_STATUS_REFRESH_MS;
  }

  /** 重填 `<select id="agent-refresh">` 的选项（含语言切换后的文案）并对齐当前值。 */
  function syncRefreshSelect() {
    const sel = $("#agent-refresh");
    if (!sel) return;
    sel.innerHTML = "";
    STATUS_REFRESH_CHOICES.forEach(function (ms) {
      const opt = document.createElement("option");
      opt.value = String(ms);
      opt.textContent = T(STATUS_REFRESH_KEYS[ms]);
      sel.appendChild(opt);
    });
    sel.value = String(statusRefreshMs());
  }

  /** 按当前设置重挂计时器（幂等；改设置即生效，无需重启）。 */
  function armStatusRefresh() {
    if (statusRefreshTimer) clearInterval(statusRefreshTimer);
    statusRefreshTimer = setInterval(function () {
      refreshBalance(true); // 出网关时前端/后端都会挡（`refreshBalance` 内已判 `cfg.enabled`）
      refreshCost(true); // 成本与命中率同节拍（既有口径）
    }, statusRefreshMs());
  }

  /** 选中即保存（与「网络」开关同套路：走 `agent_save_config`；失败回滚显示，不改计时器）。 */
  async function saveStatusRefresh(value) {
    const ms = usageInt(Number(value));
    if (ms === null || STATUS_REFRESH_CHOICES.indexOf(ms) === -1) {
      syncRefreshSelect(); // 非法取值：回滚显示
      return;
    }
    let res;
    try {
      res = await call("agent_save_config", { status_refresh_ms: ms });
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok") {
      showFlashError(T("agent.settings.saveFailed"), errorDetail(res) || errorText(res));
      syncRefreshSelect();
      return;
    }
    cfg = res;
    applyConfigToForm(); // 内含 syncRefreshSelect + armStatusRefresh（重挂计时器）
  }

  // 表单回填 / 配置落定后同步选择框并重挂计时器（`refreshConfig`/`saveConfig`/语言切换都经此）。
  const baseApplyConfigToFormForRefresh = applyConfigToForm;
  applyConfigToForm = function () {
    const out = baseApplyConfigToFormForRefresh.apply(null, arguments);
    syncRefreshSelect();
    armStatusRefresh();
    return out;
  };

  // 装配：绑选择框 + 首帧挂计时器（与基座同判据：页面未登记停靠栏则整体不介入）。
  const baseInitForRefresh = init;
  init = function () {
    const out = baseInitForRefresh.apply(null, arguments);
    if (!$("#-agent-dock")) return out;
    const sel = $("#agent-refresh");
    if (sel) sel.addEventListener("change", () => saveStatusRefresh(sel.value));
    syncRefreshSelect();
    armStatusRefresh();
    return out;
  };

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
