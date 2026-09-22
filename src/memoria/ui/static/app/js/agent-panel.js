/**
 * 应用内对话面板（**右侧独立停靠栏** `#-agent-dock`，M1 首版曾挂在左栏第 4 页签）。
 *
 * 自包含：DOM/事件绑定全部由本模块 init() 完成，不依赖 app.js 的 bindEvents：
 *   - 顶栏（右侧）`#btn-agent` → 停靠栏展开·收起（2026-09-18 起唯一入口：边缘浮动按钮
 *     `#agent-dock-collapse-btn` 已删除，改为 VSCode 式顶栏图标按钮）
 *   - `#agent-dock-resizer` 向左拖拽调宽（rem）→ 落盘 `layout.agentDockWidth`
 *   - `#agent-settings`（端点/模型/密钥/超时/出网）**2026-09-19 搬进设置弹窗「对话」页签**（`#settings-body-agent`）；`#agent-save-config` 保存端点配置
 *   - `#agent-net-toggle`「网络」开关（写 `config/agent.json` 的 enabled；2026-09-19 前文案是「出网」）
 *   - `#agent-input` Enter 发送 / Shift+Enter 换行（浏览器默认）/ Ctrl（Cmd）+Enter **自己插**换行（2026-09-22：真机实测 Windows Chromium 对 Ctrl+Enter 没有默认动作）/ 空框时 ↑↓ 翻"发过的内容"；`#agent-send` 发送
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
 * `sessionId` 设为该会话（下一句即续聊）。列表/载入是**只读**；写只发生在会话目录这一个产品
 * 自管的运行时产物上（`.memoria/agent/sessions/<id>.jsonl`：删除 / 改名，见 10 篇 §2.15）；
 * **2026-09-20 起**行动作改由**右键菜单**进入（重命名 / 删除，删除走确认弹窗），行内按钮退役。
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
 * 与后端的分工（见 `presentation/api/ui.py` 的 10 个 RPC）：
 *   `agent_get_config` / `agent_save_config` / `agent_ask_start` / `agent_ask_poll` /
 *   `agent_ask_cancel` / `agent_sessions_list` / `agent_session_load` / `agent_session_delete` /
 *   `agent_session_rename`（2026-09-20 新增，改名）；`get_ui_settings` / `save_ui_settings` 为通用偏好 RPC。
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
  let showFlashError = (...args) => {
    A().showFlashError?.(...args);
  };
  const showFlashInfo = (...args) => {
    A().showFlashInfo?.(...args);
  };
  const openFile = (relPath, opts) => A().openFile?.(relPath, opts);

  // ── 轮询参数（与 kb-check.js 的静默作业同套路）────────────────────────
  const POLL_INTERVAL_MS = 250;
  const POLL_TIMEOUT_MS = 1800000; // 30 分钟兜底：轮次不再有上限（对齐上游）后，长任务可能是几十轮工具调用；失控由「停止」按钮兜底

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
  let sessionUsage = null, lastStatusText = "", lastStatusError = false; // 后两项 = 状态行撤除后（2026-09-21）只留状态：判重 / 判红

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

  function scrollToBottom(force) {
    const box = $("#agent-messages");
    if (box) messageBoxScrollTo(box, force === true);
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
    scrollToBottom(true);
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
        stopped: false, process: msgProcess(rec), reasoning: msgReasoning(rec),
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
      scrollToBottom(true);
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
    // 后端 `answer` 是权威最终答案（loop 以当轮文本覆盖 answer）；本轮**没有最终答复**时补一句说明，
    // 否则气泡是空的、看着像"卡在思考没有后文"（真机：AAA_Vocab 连续两次 `max-iterations`）。
    if (result.answer) rec.text = result.answer;
    if (!rec.text && result.status !== "error") rec.text = stopNote(result);
    rec.anchors = Array.isArray(result.anchors) ? result.anchors : []; rec.tools = Array.isArray(result.tool_calls) ? result.tool_calls : [];
    rec.error = result.status === "error" ? fullErrorText(result) : "";
    const box = $("#agent-messages");
    if (box && streamingEl) {
      const wrap = streamingEl.parentElement;
      const rebuilt = messageEl(rec);
      if (wrap && wrap.parentNode) wrap.parentNode.replaceChild(rebuilt, wrap);
    }
    streamingEl = null;
    scrollToBottom();
  }

  async function ask() {
    const input = $("#agent-input");
    const text = expandSessionAliases(((input && input.value) || "").trim()); // 短别名 → 完整 dsh-session URI（发给后端与落盘的始终是可解析形式）
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
      const parts = []; // 2026-09-19：不再把会话 id 拼进状态行；2026-09-20：本轮用量也不再进状态行（改挂末条气泡尾 `.-agent-usage`）
      const ok = st.status === "done";
      const detail = ok ? "" : fullErrorText(st);
      setStatusText(ok ? statusLine(parts) : detail, !ok);
      if (!ok) showFlashError(errorText(st), errorDetail(st));
      job = null;
      busy = false;
      renderComposer();
      await refreshHistory(); await tagLiveBubblesWithSeqs(); // 会话进历史列表；并把事件 seq 标到刚生成的气泡上（拖拽引用靠它）
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
        if (composerEnterKey(e, input)) return; // Ctrl/Cmd+Enter = 自己插换行；Shift/Alt+Enter 放行给浏览器
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

  //: 整棵丢弃的标签（脚本 / 内嵌文档 / 表单 / 媒体 —— 图片除外：**库内图片**要渲染，见 `appendLocalImage()`）。
  const MD_DROP_TAGS = new Set([
    "SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "LINK", "META", "BASE", "TEMPLATE",
    "FORM", "INPUT", "BUTTON", "SELECT", "OPTION", "TEXTAREA", "NOSCRIPT",
    "PICTURE", "VIDEO", "AUDIO", "SOURCE", "TRACK", "CANVAS", "SVG", "MATH",
  ]);
  //: 允许保留的标签。其余一律「拆外壳、留文字」；**属性一律丢弃**（顺带消灭 `on*`、`href`、`src`
  //: —— 应用里没有外链跳转通道，留 `href` 只会让 webview 被导航走）；唯一例外是库内 `<img src>`。
  const MD_KEEP_TAGS = new Set([
    "P", "BR", "HR", "H1", "H2", "H3", "H4", "H5", "H6",
    "UL", "OL", "LI", "BLOCKQUOTE", "PRE", "CODE", "STRONG", "EM", "DEL", "S",
    "TABLE", "THEAD", "TBODY", "TFOOT", "TR", "TH", "TD", "SPAN", "DIV",
  ]);

  /** 一条消息正文的渲染入口：用户气泡走 `@引用` chip，助手气泡走 Markdown（含兜底）。 */
  function renderBody(el, role, text) {
    if (role === "user") el.innerHTML = linkifyUser(text);
    else renderAssistantBody(el, text);                    // 助手气泡：Markdown（含兜底）；用户气泡：`@引用` chip + 纯文本
    // ★ 可寻址：给每段可见文本标出它在**消息原文**里的字符区间（拖拽引用靠它定位，见文件尾 `annotateMessageOffsets`）
    annotateMessageOffsets(el, text);
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
        if (tag === "IMG") appendLocalImage(target, node); else sanitizeHtmlInto(target, node); // 图片只放行库内；其余拆壳留字
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
      tpl.innerHTML = agentRichHtml(src); // 公式先归一化 + 库内图片路径改写（都与预览同源）
      el.innerHTML = "";
      el.classList.add("markdown-body"); // 排版沿用预览的 .markdown-body（窄栏覆盖见 app.css）
      sanitizeHtmlInto(el, tpl.content);
      linkifyNodes(el);
      attachAgentImages(el); typesetAgentMath(el); // 净化**之后**：先挂图片灯箱、再排版公式（产物都不进净化器）
    } catch (e) {
      el.classList.remove("markdown-body");
      el.innerHTML = linkify(src);
      console.warn("agent-md:", e);
    }
  }

  // ── 输入框上方的状态 bar（首版）────────────────────────────────────────
  // 结构 = 状态点（idle / busy / error / off）+ 一条「事实」串（模型 · 出网 · 会话 · 轮次）。
  // 分工：**事实与运行态**在这里常显；消息级长文案（「生成中… Ns」）归气泡尾，错误归顶部浮层
  // （`#agent-status` 已于 2026-09-21 撤除 —— 见文件末尾「状态行撤除」块），不重复同一句话。
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
   * 事实是「出网已关、不能发」，不是"出错了"。错误态改读 `lastStatusError`（见文件末「状态行撤除」块）。
   */
  function statusBarDotState() {
    if (busy) return "busy";
    if (!cfg.enabled) return "off";
    // 状态行 `#agent-status` 已从 index.html 撤掉 ⇒ 改读内部状态（原先读它的 `-agent-error` 类）。
    if (lastStatusError) return "error";
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
    // 网络：开时显示「网络」并**上绿**，关时显示既有的「断网」并**上红**（颜色由 CSS 的 `data-on` 决定）
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
    return "@[" + text.replace(/[\\\]]/g, function (m) { return "\\" + m; }) + "](" + sessionAliasUri(id) + ")";
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
  //    流式期间**始终默认折叠**（创建即折叠），摘要跟**末行**并随增量实时更新（`textContent`，
  //    与流式正文同一条插入路径，不新造渲染器）；定稿后摘要取**首行**、常驻 DOM，用户可随时展开。
  // ③ **无思考则整块不存在**（首个非空增量才创建，`rec.reasoning` 为空时不插入 ⇒ 无空块、无跳变）。
  // ④ 思考**随 `assistant/message` 落会话文件**（2026-09-22 起）：回放（`agent_session_load` 的
  //    `process` 行）能重建同样的思考行；旧的会话文件没有 `reasoning` ⇒ 照旧不显示过往思考（不报错）。
  //    形状的单一来源见 services/agent/turn_process.py 与 session/history.py::conversation_messages。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  //: 已投递的思考字符数（**与文本游标完全独立**）；每轮提问由 `ask()` 包装重置。
  let reasoningCursor = 0;

  /** 思考行的**骨架**（2026-09-22 改版，人：「思考和三角符号应该不在圆角气泡内，而点击思考之后
   *  才展开在下方出现圆角气泡显示思考或者正在思考的内容，而且这个圆角气泡可以进一步展开直接显示全部」）：
   *
   *  ```
   *  <details class="-agent-think">             ← **无底色/无边框**：只有那一行摘要，不算气泡
   *    <summary class="-agent-think-summary">   ← 「思考」+ 三角（CSS 画）；**旁边不放任何摘要文字**
   *    <div class="-agent-think-bubble">        ← **圆角气泡**：点开后才出现（默认 `max-height` 截断）
   *      <div class="-agent-think-body">…思考原文…</div>
   *      <button class="-agent-think-more">展开 / 收起</button>
   *  ```
   *  `live` = 还在生成（正文为空时显示「正在思考…」占位）；`text` = 已有思考正文（一律**渲染**，非裸文本）。 */
  function thinkEl(text, live) {
    const box = document.createElement("details");
    box.className = "-agent-think";
    const summary = document.createElement("summary");
    summary.className = "-agent-think-summary";
    const label = document.createElement("span"); label.className = "-agent-think-label"; label.textContent = T("agent.think");
    // 2026-09-22：摘要 tip 撤除（人：「思考过程旁边不用展示文字」）⇒ 等量占位，保下方锚点不推位。
    summary.appendChild(label);
    box.appendChild(summary);

    const bubble = document.createElement("div"); bubble.className = "-agent-think-bubble";
    const body = document.createElement("div"); body.className = "-agent-think-body";
    // 有正文 ⇒ 走与助手正文**同一条 markdown 管线**（公式 / 代码 / 列表都渲染，2026-09-21 的口径：
    // 「思考可以渲染吧，不然公式这些用户都看不懂」）；**流式同样走渲染**（见 `updateThinkRowEl()`）。
    if (String(text || "").trim()) { renderAssistantBody(body, text); body.__thinkText = String(text); }
    else if (live) { body.__thinkText = T("agent.thinkLive"); body.textContent = body.__thinkText; }
    bubble.appendChild(body);
    const more = document.createElement("button");
    more.type = "button";
    more.className = "-agent-think-more";
    more.addEventListener("click", function (ev) {
      ev.preventDefault(); // 别把 <details> 一起开合
      const full = bubble.classList.toggle("-agent-think-bubble--full");
      more.textContent = full ? T("agent.thinkLess") : T("agent.thinkMore");
    });
    bubble.appendChild(more);
    box.appendChild(bubble);
    refreshThinkMore(bubble, body, more);
    return box;
  }

  /** 「展开」按钮只在正文真的放不下时出现（截断阈值见样式块的 `max-height`：8rem ⇒ 展开 20rem）。
   *  不量 DOM 尺寸（渲染时可能还没进文档）：按**行数 / 字符数**判定 ⇒ 纯函数、可单测。 */
  function thinkNeedsMore(text) {
    const s = String(text == null ? "" : text);
    return s.split(/\r?\n/).length > 5 || s.length > 240;
  }

  function refreshThinkMore(bubble, body, more) {
    const needed = thinkNeedsMore(body ? body.textContent : "");
    more.hidden = !needed;
    if (needed) {
      // **两个分支都要写文案**：只写 `!needed` 分支会让长正文（= 真需要按钮的那些）露出**空白按钮**
      // —— 真机 L4 实测到的缺陷（101 个按钮文案为空、高度 3px，点了才出现「收起」）。
      // 已展开（`--full`）时保留「收起」，别被后续增量改回「展开」。
      if (!bubble.classList.contains("-agent-think-bubble--full")) more.textContent = T("agent.thinkMore");
      return;
    }
    bubble.classList.remove("-agent-think-bubble--full");
    more.textContent = T("agent.thinkMore");
  }

  /** 流式期间：找到**当前这一步**还没收尾的思考行（`state:"live"`），没有就**新开一段**——
   *  行落在 `rec.process` 末尾（⇒ 排在本步工具行之前），并**立即建好 DOM 节点**（新的一段思考）。
   *  收尾由 `applyProcessDelta()` 在收到本步 `step` 行时做 ⇒ **多段思考**、段与段之间有工具行。 */
  function openThinkRow() {
    const rec = currentAssistant();
    if (!rec || rec.role !== "assistant") return null;
    if (!Array.isArray(rec.process)) rec.process = [];
    const last = rec.process[rec.process.length - 1];
    if (last && last.kind === "think" && last.state === "live") return last;
    const row = { kind: "think", text: "", state: "live", iteration: 0 };
    rec.process.push(row);
    const wrap = streamingEl && streamingEl.parentElement;
    if (wrap) processBox(wrap).appendChild(thinkEl("", true));
    return row;
  }

  /** 把一片思考增量追加到**当前这一步**的思考行（纯文本、无 HTML 注入；DOM 就地更新，不重建）。 */
  function applyReasoningDelta(delta) {
    const rec = currentAssistant();
    if (!rec) return;
    rec.reasoning = (rec.reasoning || "") + delta;
    const row = openThinkRow();
    if (!row) return;
    row.text = String(row.text || "") + delta;
    const wrap = streamingEl && streamingEl.parentElement;
    if (wrap) {
      const nodes = wrap.querySelectorAll(".-agent-process .-agent-think");
      const el = nodes[nodes.length - 1];
      if (el) updateThinkRowEl(el, row);
    }
    scrollToBottom();
  }

  /** 过程容器里**最后一条**思考行的节点（流式更新用；没有 ⇒ `null`）。 */
  function lastThinkRowEl(wrap) {
    if (!wrap) return null;
    const nodes = wrap.querySelectorAll(".-agent-process .-agent-think");
    return nodes.length ? nodes[nodes.length - 1] : null;
  }

  /** 就地更新一条思考行（流式中每次增量）：正文、摘要、按钮可见性；收尾（`done`）时改走 markdown 管线。 */
  function updateThinkRowEl(el, row) {
    if (!el || !row) return;
    el.setAttribute("data-state", String(row.state || "done"));
    const body = el.querySelector(".-agent-think-body");
    const text = String(row.text || "");
    if (body) {
      // 2026-09-22：**流式也走渲染**（人：「思考过程里面要渲染，不是裸文本」）—— 与助手正文的流式同口径：每次都重渲染（见 `renderAssistantBody(streamingEl, parts.safe)`），`__thinkText` 去重免掉无谓重渲染。
      const shown = text || T("agent.thinkLive");
      if (body.__thinkText !== shown) {
        renderAssistantBody(body, shown);
        body.__thinkText = shown;
      }
    }
    // 2026-09-22：摘要 tip 撤除（见 `thinkEl()`）⇒ 不再同步那个已删掉的预览节点。本行等量占位，保下方锚点。
    const bubble = el.querySelector(".-agent-think-bubble");
    const more = el.querySelector(".-agent-think-more");
    if (bubble && more) refreshThinkMore(bubble, body, more);
  }

  // 定稿/重绘都经 `messageEl`；**2026-09-22 起不再往正文前插"整轮一条"的思考块** ——
  // 思考改成**按步**的过程行（`kind: "think"`，见 `openThinkRow()` 与过程渲染那条路径），
  // 由过程容器按事件顺序渲染 ⇒ 多段思考与工具行天然交错。这里只保留 `rec.reasoning`（兼容字段）。
  const baseMessageEl = messageEl;
  messageEl = function (rec) {
    return baseMessageEl.apply(null, arguments);
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
      args.push(reasoningCursor); args.push(processCursor); // 第 3/4 个位置参数 = 思考游标 / 过程游标（后端追加的可选参数）
      const pending = baseFacadeCall.apply(this, args);
      return Promise.resolve(pending).then(function (res) {
        if (res && typeof res.reasoning_cursor === "number") reasoningCursor = res.reasoning_cursor;
        if (res && typeof res.process_cursor === "number") processCursor = res.process_cursor;
        if (res && typeof res.reasoning_delta === "string" && res.reasoning_delta) applyReasoningDelta(res.reasoning_delta);
        if (res && Array.isArray(res.process_delta) && res.process_delta.length) applyProcessDelta(res.process_delta);
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

  /** 本轮用量行文案（**含命中率**）；无总量（无本轮 usage）返回 ""（调用方据此不挂节点）。
   *  命中率口径 = `hit / prompt`（与底部 `#status-agent` 同源）；`hit` 未知时**不写这一句**（不瞎报 0%）。 */
  function usageLineText(u) {
    if (!u || !u.total_tokens) return "";
    const hit = usageInt(u.cache_read_tokens);
    const miss = usageInt(u.cache_miss_tokens);
    const total = hit !== null && miss !== null ? hit + miss : usageInt(u.total_tokens);
    const line = T("agent.usage.line", { hit: usageNumText(hit), miss: usageNumText(miss), total: usageNumText(total) });
    const rate = hitRateText(hit, u.prompt_tokens || 0);
    return rate ? line + " · " + T("agent.usage.rate", { rate: rate }) : line;
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

  /** 取 `rec` 对应的消息元素（按 `data-msg-index` 稳定定位）；未渲染 / 不在 `messages` 里 ⇒ `null`。
   *
   *  刻意**不用**"assistant 序位 + `querySelectorAll(".-agent-msg--assistant")`"：计划/写入回执卡也带
   *  这个类却**不在** `messages` 里（`plan-confirm.js`）⇒ 一旦出现过写入卡，序位整体错位，本轮用量行
   *  与「生成中… Ns」尾标都会挂到那张卡上（真机症状：最后那条回话下方看不到用量与命中率）。 */
  function assistantWrapFor(rec) {
    const idx = messages.indexOf(rec), box = $("#agent-messages");
    if (idx < 0 || !box) return null;
    return box.querySelector('.-agent-msg[data-msg-index="' + idx + '"]');
  }

  /** 重绘用量行：只挂在**拥有该 usage 的那条助手气泡**末尾（全面板最多一份）；无则只清不挂。 */
  function renderTurnUsage() {
    clearUsageLines();
    const text = usageLineText(lastUsage);
    if (!text || !usageOwner) return;
    // 定位一律走 `assistantWrapFor()`（`data-msg-index`）：**不能**用"assistant 序位 +
    // `querySelectorAll(".-agent-msg--assistant")`"——计划 / 写入回执卡也带这个类却不在 `messages`
    // 里（`plan-confirm.js`），一旦出现过写入卡，序位整体错位（真机症状：用量行挂到了那张回执卡上，
    // 而最后那条回话下方**什么都没有** —— 人 2026-09-21 报的正是这个）。
    const wrap = assistantWrapFor(usageOwner);
    if (!wrap) {
      usageOwner = null; // 那条消息已被清空 / 换会话 / 尚未渲染 ⇒ 不再有归属
      return;
    }
    const line = usageRowEl(wrap); // **操作行**里那一格（与「复制」同一行 —— 人 2026-09-22：「对话底部除了显示用量信息还需要复制按钮」）
    line.className = "-agent-usage -muted";
    line.textContent = text;
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

  // ══════════════════════════════════════════════════════════════════════════════
  // 全库「三角形」统一（2026-09-20；用户："agent 思考过程展开的『三角形』字符也要换掉，
  // 全仓库『三角形』都要换"）
  //   ① **唯一 path 字面量**仍在 `file-tree.js` 的 `ICON_BODIES.triangleRight`（dsh `ui-primitives`
  //      的 `IconTriangleRightFill14`，MIT，pin 0d1f5000；文件树 twisty 用它渲染，file-tree.js:169/629）。
  //      本块**不改 file-tree.js 一行**，而是从 `window.MemoriaTreeIcons.icon("triangleRight")` 取回
  //      同一份 SVG、抽出其 `d` 拼成 data-URI mask ⇒ 全库只有一份 path 数据（两个消费方共用）。
  //   ② 消费方 = 所有**原生 `<details>/<summary>` 的 UA 三角标记**（AG08 思考块 `.-agent-think`、
  //      Markdown 预览里的用户 `<details>`、公式诊断 `<details>`、链接「高级」与系统建议块），
  //      加上格式栏两个下拉按钮文案里那个「小实心下三角」字符（U+25BE）——`index.html:168/180`
  //      已把该字符删掉，改由 `::after` 用**同一枚**三角旋转 90° 指下 ⇒ 与"点开色板"的下拉语义一致。
  //   ③ 规则**整条注入**（含 `content`/尺寸/mask）而不进 app.css 静态块：静态块只能给到
  //      `mask-image`，一旦 JS 未运行（`--memoria-tri` 缺失）伪元素就会以 `currentColor` 画成
  //      **实心方块**；整条注入则"JS 缺席 ⇒ 一条规则都没有 ⇒ 原生标记照旧"，是干净的优雅降级。
  //   ④ 颜色一律 `currentColor`（深浅主题随所在行既有 token 走）；尺寸 0.5625rem 与文件树 twisty
  //      同档（`.-tree-twisty > svg`）；展开语义不变（右向 → `[open]` 旋转 90° 指下）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  //: 格式栏两个「点开色板」按钮（原文案「H + 小下三角」/「色 + 小下三角」，U+25BE）：caret 由 `::after` 画。
  const FMT_CARET_BUTTONS =
    '.-fmt-btn[data-fmt="highlight"]::after, .-fmt-btn[data-fmt="fontcolor"]::after';

  /** 从文件树那枚三角 SVG 抽出 `d`，拼成 CSS `mask-image` 用的 data-URI；取不到返回 ""。 */
  function triangleMaskUrl() {
    const tree = window.MemoriaTreeIcons;
    if (!tree || typeof tree.icon !== "function") return "";
    const svg = tree.icon("triangleRight");
    if (!svg) return "";
    const d = /d="([^"]+)"/.exec(svg);
    if (!d) return "";
    const box = /viewBox="([^"]+)"/.exec(svg);
    const src =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' +
      (box ? box[1] : "0 0 14 14") +
      '"><path fill="#000" d="' +
      d[1] +
      '"/></svg>';
    return 'url("data:image/svg+xml,' + encodeURIComponent(src).replace(/'/g, "%27") + '")';
  }

  /** 注入一次全局三角规则（幂等；同一份 mask 同时服务 `<details>` 标记与格式栏 caret）。 */
  function installTriangleStyles() {
    if (document.getElementById("-memoria-triangle")) return;
    const mask = triangleMaskUrl();
    if (!mask) return; // 图标模块缺席 ⇒ 不注入（原生标记照旧，绝不画方块）
    const base =
      "content: ''; display: inline-block; width: 0.5625rem; height: 0.5625rem;" +
      " background-color: currentColor; -webkit-mask: " +
      mask +
      " center/contain no-repeat; mask: " +
      mask +
      " center/contain no-repeat; transition: transform 0.12s ease;";
    const css =
      "details > summary { list-style: none; }\n" +
      "details > summary::-webkit-details-marker { display: none; }\n" +
      "details > summary::before { " +
      base +
      " margin-right: 0.3125rem; vertical-align: -0.0625rem; }\n" +
      "details[open] > summary::before { transform: rotate(90deg); }\n" +
      FMT_CARET_BUTTONS +
      " { " +
      base +
      " margin-left: 0.1875rem; vertical-align: -0.0625rem; transform: rotate(90deg); }\n";
    const style = document.createElement("style");
    style.id = "-memoria-triangle";
    style.textContent = css;
    document.head.appendChild(style);
  }

  installTriangleStyles();

  // ══════════════════════════════════════════════════════════════════════════════
  // 「生成中… Ns」下沉到**末条助手气泡末尾**（2026-09-20；用户："对话框下面这个不用保留，
  // 生成过程中这个位置会显示『生成中』，把『生成中』放在 agent 最后一次对话进行时的末尾"）
  //   ① `#agent-status` **不再承载 token 用量文本**：原 `poll()` 定稿时写的
  //      `usageText(st.usage)`（=「用量 18582+14=18596 tokens」）与上一轮新增的 `.-agent-usage`
  //      逐字重复，故就地改为空数组（函数 `usageText` 与键 `agent.status.usage` 保留，只是不再有
  //      调用方写进状态行）。**2026-09-21 起该状态行整行撤除**（人：「对话框下面这个能不能去掉」）：
  //      错误 / 提示改走顶部浮层、状态点改读 `lastStatusError`，`setStatusText()` 只剩"记状态"职责
  //      —— 接管代码见文件末尾「状态行撤除」块（本段保留原貌以存史，勿按它判断现状）。
  //   ② 生成期间**只剩气泡尾这一处**写「生成中…」：原状态行的基词 `agent.status.thinking` 随该行
  //      一起撤除；秒数只在 `.-agent-generating`（`agent.generating` =「生成中… {n}s」）。
  //   ③ 挂载点 = **当前助手气泡（`.-agent-msg--assistant`）的最后一个子节点**。同气泡内最终顺序：
  //      角色 → AG08 思考块（正文**之前**）→ 正文 → AG11 等待区（`.-agent-stream-wait`，插在正文之后）
  //      →「生成中… Ns」→（定稿后才有）来源条/错误条。生成期间它与等待区**各占一行**、互不覆盖。
  //   ④ 生命周期：只**包装** `tickWait`（每秒）与 `stopWait`（定稿/超时/停止/清空/换库等所有终止
  //      路径都会调它）⇒ 本轮一结束指示器必被摘掉；`renderMessages()` 整串重绘也会把它一起换掉，
  //      定时器若仍在跑，下一秒自会按新气泡重建（自愈，不留陈旧节点）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 当前（或末条）助手气泡容器：优先取流式正文元素之父，回落按**稳定索引**定位。 */
  function generatingHost() {
    if (streamingEl && streamingEl.parentElement) return streamingEl.parentElement;
    const rec = currentAssistant();
    if (!rec) return null;
    // 回落定位同样走 `assistantWrapFor()`（`data-msg-index`）而不是"assistant 序位 +
    // `querySelectorAll`"：写入回执卡也带 `-agent-msg--assistant` 却不在 `messages` 里 ⇒ 序位法会把
    // 「生成中… Ns」挂到那张卡尾部（与用量行同一个坑）。该消息尚未渲染 ⇒ `null`，本帧不画尾标，
    // 下一帧（`tickWait` 每秒一次）自会重建。
    const wrap = assistantWrapFor(rec);
    return wrap;
  }

  /** 清掉消息区里所有「生成中… Ns」指示器（幂等）。 */
  function clearGeneratingTail() {
    const box = $("#agent-messages");
    if (!box) return;
    const nodes = box.querySelectorAll(".-agent-generating");
    for (let i = 0; i < nodes.length; i += 1) {
      if (nodes[i].parentNode) nodes[i].parentNode.removeChild(nodes[i]);
    }
  }

  /** 一帧：确保末条助手气泡尾部有唯一指示器并刷新秒数（节点复用 ⇒ 不闪烁、不重排）。 */
  function renderGeneratingTail(secs) {
    const host = generatingHost();
    if (!host) return;
    let el = host.querySelector(".-agent-generating");
    if (!el) {
      el = document.createElement("div");
      el.className = "-agent-generating -muted";
      host.appendChild(el); // 气泡**末尾**
    }
    el.textContent = T("agent.generating", { n: secs });
  }

  // 每秒一帧：状态行只留基词「生成中…」，秒数交给气泡尾（原函数体不再被调用 ⇒ 不写状态行秒数）。
  tickWait = function () {
    if (!waitStartedAt) return;
    const secs = Math.max(0, Math.floor((Date.now() - waitStartedAt) / 1000));
    setStatusText(T("agent.status.thinking"));
    renderGeneratingTail(secs);
  };

  // 终止路径（定稿/超时/停止/清空/换库）都经 `stopWait` ⇒ 在此摘掉指示器。
  const baseStopWaitForGenerating = stopWait;
  stopWait = function () {
    const out = baseStopWaitForGenerating.apply(null, arguments);
    clearGeneratingTail();
    return out;
  };

  // ══════════════════════════════════════════════════════════════════════════════
  // 选区悬浮「加入对话」（2026-09-20；用户报障："我在文件内（不论源码或者预览区）拖拽选取之后，
  // 没有在选区附近悬浮显示『添加到对话 chat』"）。此前**不存在**该入口（全前端无此 affordance）。
  // 契约：① 只在**非空**选区、且选区落在 `#preview`（预览区）或 `#editor`（源码区）内、并且有
  //   当前打开的文件时出现（选区为空 / 选区在别处 / 没开文件 ⇒ 一律不出现或立刻消失）；
  // ② 点它 = 把**当前打开文件**的 `@相对路径` token 插到输入框的「上次光标位置」——直接复用
  //   文件树拖拽那条 `insertMention()`（同一 `inputCaret` 语义，不自造第二套插入逻辑）；
  // ③ 点别处（含面板内）/ Esc / 换文件（选区自然消失）/ 窗口尺寸变化 ⇒ 隐藏；**滚动 ⇒ 重算位置**（2026-09-20 修正：旧版"任意滚动即隐藏"会让跨行拖拽的自滚动把入口永久摘掉）；
  // ④ 不碰文件树拖拽、不碰既有选区渲染（`sel-source.js`），本块只**读**选区 + 维护一个浮动按钮。
  // v1 产生的 token **只有** `@相对路径`（路径含空格时为 `@"路径"`，与 `formatMention` 同口径）：
  //   选中的**文本本身不进请求、也不生成区间 token** —— 片段级引用（区间/摘录）属设计 §6.13 A 项，
  //   规格未定前不发明语法（模型拿到 `@路径` 后自行 `read_document` 取内容）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  //: 浮动按钮的固定 id/类名（CSS 在 `app.css` 文件末尾同名块）。
  const SEL_ADD_ID = "-agent-sel-add";
  //: 允许出按钮的两个宿主：预览区与源码区（两处都是**真实** DOM 选区 ⇒ 一套逻辑通用）。
  const SEL_ADD_HOSTS = ["#preview", "#editor"];

  /** 当前选区是否落在允许宿主内且有内容；命中回 `{rect}`（`rect` = 选区包围盒，用于定位）。 */
  function selAddHit() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
    if (!String(sel.toString() || "").trim()) return null; // 只有空白字符不算"选了东西"
    if (!state.currentPath) return null; // 没开文件 ⇒ 无 `@路径` 可引用
    const range = sel.getRangeAt(0);
    for (let i = 0; i < SEL_ADD_HOSTS.length; i += 1) {
      const host = $(SEL_ADD_HOSTS[i]);
      if (host && host.contains(range.commonAncestorContainer)) {
        const rect = range.getBoundingClientRect();
        if (rect && (rect.width || rect.height)) return { rect: rect };
        return null;
      }
    }
    return null;
  }

  /** 浮动按钮（惰性建、只建一个；`mousedown` 拦一下，别把用户刚拖出来的选区点没了）。 */
  function selAddButton() {
    let btn = document.getElementById(SEL_ADD_ID);
    if (btn) return btn;
    btn = document.createElement("button");
    btn.type = "button";
    btn.id = SEL_ADD_ID;
    btn.className = "-agent-sel-add";
    btn.addEventListener("mousedown", function (ev) {
      ev.preventDefault();
    });
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      addSelectionToChat();
    });
    document.body.appendChild(btn);
    return btn;
  }

  function hideSelAdd() {
    const btn = document.getElementById(SEL_ADD_ID);
    if (btn) btn.classList.remove("-on");
  }

  /** 把当前文件作为 `@路径` 引用加进输入框（插在**上次光标位置**），随后收掉按钮。 */
  function addSelectionToChat() {
    const path = state.currentPath || "";
    hideSelAdd();
    if (!path) return;
    insertMention(path, "file"); // 与文件树拖拽同一落点逻辑（含 `inputCaret` 记账与焦点回填）
  }

  /** 选区变化后同步按钮：命中则贴到选区**上方**（挤不下时落下方），否则隐藏。 */
  function syncSelAdd() {
    const hit = selAddHit();
    if (!hit || hit.rect.bottom < 0 || hit.rect.top > window.innerHeight) { // 选区整体滚出视口 ⇒ 不显示
      hideSelAdd();
      return;
    }
    const btn = selAddButton();
    btn.textContent = T("agent.selAddAction");
    btn.title = T("agent.selAddTitle");
    btn.classList.add("-on"); // 先显示再量尺寸（`display:none` 时 offsetWidth 为 0）
    const w = btn.offsetWidth || 72;
    const h = btn.offsetHeight || 20;
    const rect = hit.rect;
    let top = rect.top - h - 6;
    if (top < 4) top = Math.min(rect.bottom + 6, Math.max(4, window.innerHeight - h - 4)); // 贴顶改落下方；仍越界（选区高过视口）则钉进视口
    const maxLeft = Math.max(4, window.innerWidth - w - 4);
    const left = Math.max(4, Math.min(rect.left + rect.width / 2 - w / 2, maxLeft));
    btn.style.left = Math.round(left) + "px";
    btn.style.top = Math.round(top) + "px";
  }

  // 事件全部挂在 document/window 上（与面板初始化时机无关，也不动上方任何监听）：
  // 选区变化 / 拖拽结束（mouseup）/ 点别处（capture，mousedown 早于新选区成立）/ 滚动 / Esc / 缩放。
  document.addEventListener("selectionchange", syncSelAdd);
  document.addEventListener("mouseup", syncSelAdd);
  document.addEventListener(
    "mousedown",
    function (ev) {
      const t = ev.target;
      if (t && t.id === SEL_ADD_ID) return; // 点按钮本身：交给它的 click
      hideSelAdd();
    },
    true
  );
  document.addEventListener(
    "scroll",
    syncSelAdd, // 重算位置而非隐藏：跨行拖拽/跨界选择常伴随自动滚动，隐藏会让入口再也回不来
    true // capture：预览区/源码区/任意内层滚动容器都能收到
  );
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") hideSelAdd();
  });
  window.addEventListener("resize", hideSelAdd);

  // ══════════════════════════════════════════════════════════════════════════════
  // 选区引用的「位置」＋ 消息气泡入口 ＋ 打字框 chip（2026-09-20；用户报障三连："实际写入对话的仍然
  // 只是 `@文件名`，根本没有标出对应内容的源码位置…对话栏仍然不能悬浮显示加入对话…引用仍是 `@` +
  // 纯文本而不是在打字框里面把引用渲染一下"）。整块追加在 IIFE 末尾（`return {}` 之前）：
  //   ① 选区「加入对话」写出**带位置**的 token：源码区用真实行号（`.-line[data-line]`），
  //      预览区用**块级源码行映射**（`[data--src-line][data--src-line-end]`，见 `prevPreviewBlockEnd`）；
  //   ② 触发宿主扩到**消息气泡**（`#agent-messages`）：产出会话片段引用 token（`…#seq:<n>`）；
  //   ③ `#agent-input` 背后加一层**镜像层**（追加在 `.-agent-composer` 末尾，靠 `z-index` 压到 textarea
  //      之下），把 token 包成 chip —— textarea 自身文字透明、光标与选区仍归 textarea；无 token 时镜像
  //      `display:none` 且 textarea 样式不变 ⇒ 零视觉差异。
  // 纪律：**不改**既有 `syncSelAdd` / `insertMention` / `insertSessionToken` / `messageEl` / `loadSession`
  // 的任何一行，只**包一层**或换个绑定（`selAddHit` / `addSelectionToChat` 是"按名调用"的，重绑可见；
  // `syncSelAdd` 已作为监听器绑死 ⇒ 不改它，改用**后注册**的监听做文案修正）。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 源码区：选区端点 → 该行**真实**行号（`.-line[data-line]`，1 起）；取不到回 0（不猜）。 */
  function sourceLineAt(node) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    const lineEl = el && el.closest ? el.closest("[data-line]") : null;
    const n = lineEl ? Number(lineEl.getAttribute("data-line")) : 0;
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  /** 选区**终点**：若它恰好停在某行的**第一个文本节点**的 0 偏移，收回到上一行（别多算一行）。 */
  function endLineAt(node, offset) {
    const line = sourceLineAt(node);
    if (!line || offset !== 0 || node.nodeType !== 3 || !document.createTreeWalker) return line;
    const lineEl = node.parentElement && node.parentElement.closest ? node.parentElement.closest("[data-line]") : null;
    if (!lineEl) return line;
    const first = document.createTreeWalker(lineEl, NodeFilter.SHOW_TEXT).nextNode();
    return first === node && line > 1 ? line - 1 : line;
  }

  /** 预览区：选区端点所属源码块 → `[起, 止]` 源码行区间（`data--src-line[-end]`）；取不到回 null。 */
  function previewBlockRange(node) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    const block = el && el.closest ? el.closest("[data--src-line]") : null;
    if (!block) return null;
    const start = Number(block.getAttribute("data--src-line")) || 0;
    const end = Number(block.getAttribute("data--src-line-end")) || start;
    return start > 0 ? [start, Math.max(start, end)] : null;
  }

  /** 预览区：选区终点恰在**下一个块的首字符**时，回"上一块的末行"（避免把整块多算进来）。 */
  function prevPreviewBlockEnd(node) {
    const preview = $("#preview");
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    const block = el && el.closest ? el.closest("[data--src-line]") : null;
    if (!preview || !block) return null;
    const blocks = preview.querySelectorAll("[data--src-line]");
    let prev = null;
    for (let i = 0; i < blocks.length; i += 1) {
      if (blocks[i] === block) break;
      prev = blocks[i];
    }
    if (!prev) return null;
    return Number(prev.getAttribute("data--src-line-end")) || Number(prev.getAttribute("data--src-line")) || null;
  }

  /** 消息气泡 → 事件 seq（`data-agent-seq`，由 `conversation_messages()` 的 `seq` 键标上）；无回 null。 */
  function bubbleSeq(node) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    const bubble = el && el.closest ? el.closest("[data-agent-seq]") : null;
    const n = bubble ? Number(bubble.getAttribute("data-agent-seq")) : NaN;
    return Number.isInteger(n) && n >= 0 ? n : null;
  }

  /** 选区所属**宿主与位置**：`{host:"editor"|"preview", startLine, endLine}` 或 `{host:"messages", seqFrom, seqTo}`。 */
  function selectionLocation(range) {
    const anchor = range.commonAncestorContainer;
    const editor = $("#editor");
    if (editor && editor.contains(anchor)) {
      return {
        host: "editor",
        startLine: sourceLineAt(range.startContainer),
        endLine: endLineAt(range.endContainer, range.endOffset),
      };
    }
    const preview = $("#preview");
    if (preview && preview.contains(anchor)) {
      const a = previewBlockRange(range.startContainer);
      let b = previewBlockRange(range.endContainer) || a;
      if (a && b && b[0] > a[1] && range.endOffset === 0) {
        const prev = prevPreviewBlockEnd(range.endContainer);
        if (prev && prev >= a[0]) b = [prev, prev]; // 终点在下一块块首 ⇒ 上一块末行才是真正选中的末尾
      }
      if (!a || !b) return null;
      return { host: "preview", ...previewRangeEndpoints(range, a, b) }; // 反标命中 ⇒ 精确行:列；否则退回块级近似
    }
    const box = $("#agent-messages");
    if (box && box.contains(anchor)) {
      const from = bubbleSeq(range.startContainer);
      const to = from === null ? null : bubbleSeq(range.endContainer); // 气泡无事件 seq（本 run 刚生成的当轮）也不再"不出入口"，落点由 addSelectionToChat 决定
      // ↑ 仍返回 messages 宿主：入口照常出现；拿不到 seq 时写入**整会话**引用（不静默、不假装精确）
      return { host: "messages", seqFrom: from, seqTo: to === null ? from : to, offFrom: messageOffsetAt(range.startContainer, range.startOffset), offTo: messageOffsetAt(range.endContainer, range.endOffset) };
    }
    return null;
  }

  // ① 宿主判定：在既有「预览区 / 源码区」之外**追加**消息气泡（其余判断逐条照旧）。
  selAddHit = function () {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
    if (!String(sel.toString() || "").trim()) return null;
    const range = sel.getRangeAt(0);
    const loc = selectionLocation(range);
    if (!loc) return null;
    const rect = range.getBoundingClientRect();
    if (!rect || (!rect.width && !rect.height)) return null;
    return { rect: rect, loc: loc };
  };

  /** `@路径#L12-L30`（单行 `#L12`；含空白路径写 `@"…"#L12-L30`）；无行号 ⇒ 退回既有 `formatMention`。 */
  function formatRangeMention(path, start, end) {
    const p = String(path || "").replace(/\\/g, "/");
    if (!p) return "";
    if (!(start > 0)) return formatMention(p, "file");
    const head = /\s/.test(p) ? '@"' + p + '"' : "@" + p;
    return end > start ? head + "#L" + start + "-L" + end : head + "#L" + start;
  }

  /** 会话片段引用 token：`@[label](dsh-session:<base64url>#seq:<n>)`（跨气泡用 `#seq:<起>-<止>`）。 */
  function sessionFragmentToken(from, to, offFrom, offTo) {
    const id = sessionId ? String(sessionId) : "";
    if (!id || !Number.isInteger(from)) return "";
    const end = Number.isInteger(to) ? to : from;
    const frag = fragmentSuffix(from, offFrom, end, offTo); // 纯函数（可单测）：序号区间 + 两端**消息内字符位**
    const row = histDataRow(id);
    const label = (row && histTitle(row)) || id;
    const head = formatSessionMentionToken(id, label); // 别名 URI（单一事实源）
    return head.replace("(" + sessionAliasUri(id) + ")", "(" + sessionAliasUri(id) + frag + ")");
  }

  // ② 落点：源码/预览 ⇒ 带行区间的文件 token；气泡 ⇒ 会话片段 token。落点仍走既有 `inputCaret` 语义。
  addSelectionToChat = function () {
    const hit = selAddHit();
    hideSelAdd();
    if (!hit || !hit.loc) return;
    const loc = hit.loc;
    if (loc.host === "messages") {
      const token = sessionFragmentToken(loc.seqFrom, loc.seqTo, loc.offFrom, loc.offTo); // 带**消息内字符区间**（对话栏里拖拽选取的起止）
      if (token) insertSessionToken(token); else if (sessionId) quoteSession(String(sessionId)); // 无事件 seq（本 run 刚生成的当轮）⇒ 退回**整会话**引用，与历史行「引用」同一落法
      return;
    }
    const path = state.currentPath || "";
    if (!path) return;
    insertSessionToken(formatRangeMention(path, loc.startLine, loc.endLine));
  };

  /** 气泡选区的按钮文案（基座 `syncSelAdd` 已绑死为监听器 ⇒ 不能改它，改用**后注册**的监听补文案）。 */
  function relabelSelAdd() {
    const btn = document.getElementById(SEL_ADD_ID);
    if (!btn || !btn.classList.contains("-on")) return;
    const sel = window.getSelection();
    const loc = sel && !sel.isCollapsed && sel.rangeCount ? selectionLocation(sel.getRangeAt(0)) : null;
    const seq = !!(loc && loc.host === "messages");
    if (seq === (btn.getAttribute("data-sel-ctx") === "seq")) return; // 已是该上下文的文案
    if (seq) {
      btn.textContent = T("agent.selAddActionSeq");
      btn.title = T("agent.selAddTitleSeq");
      btn.setAttribute("data-sel-ctx", "seq");
    } else {
      btn.textContent = T("agent.selAddAction");
      btn.title = T("agent.selAddTitle");
      btn.removeAttribute("data-sel-ctx");
    }
  }

  // ③ 打字框引用 chip：镜像层（同字体/内距/换行 + 同步滚动与尺寸），textarea 文字透明、光标归它自己。
  const COMPOSER_TOKEN_RE = /(@\[(?:\\.|[^\\\]])*\]\(dsh-session:[^\s)]*\))|(^|\s)(@"[^"]*"?|@\S+)/g;

  /** 单个 token → chip HTML（**逐字保留 token 原文** ⇒ 与 textarea 里那串字符同宽，镜像才不会错位）。 */
  function composerTokenHtml(token) {
    const session = /^@\[(?:\\.|[^\\\]])*\]\(dsh-session:([^\s)]*)\)$/.exec(token);
    if (session) {
      if (!sessionAliasOrUriOk(session[1].split("#seq:")[0])) return esc(token);
      return '<span class="-agent-composer-chip -agent-composer-chip--session">' + esc(token) + "</span>";
    }
    const file = /^@(?:"([^"]*)"?|([^\s"]+?))(#L\d+(?:-L\d+)?)?$/.exec(token);
    if (!file) return esc(token);
    const body = (file[1] !== undefined ? file[1] : file[2]) || "";
    if (!body) return esc(token);
    const range = file[3] || "";
    const head = range ? token.slice(0, token.length - range.length) : token;
    return (
      '<span class="-agent-composer-chip' + (range ? " -agent-composer-chip--range" : "") + '">' +
      esc(head) +
      (range ? '<span class="-agent-composer-chip-range">' + esc(range) + "</span>" : "") +
      "</span>"
    );
  }

  /** 全文 → chip HTML（逐段转义，**不先整体 esc**，与 `linkifyUser` 同一手法）。 */
  function composerChipsHtml(text) {
    const raw = String(text == null ? "" : text);
    let out = "";
    let last = 0;
    COMPOSER_TOKEN_RE.lastIndex = 0;
    for (const m of raw.matchAll(COMPOSER_TOKEN_RE)) {
      if (m[1] !== undefined) {
        out += esc(raw.slice(last, m.index)) + composerTokenHtml(m[1]);
        last = m.index + m[1].length;
        continue;
      }
      const token = m[3] || "";
      const start = m.index + (m[2] || "").length;
      out += esc(raw.slice(last, start));
      out += token ? composerTokenHtml(token) : "";
      last = start + token.length;
    }
    return out + esc(raw.slice(last));
  }

  let composerMirror = null;

  /** 惰性建镜像层；**追加在 `.-agent-composer` 末尾**（不插进 `#agent-statusbar` ↔ `#agent-input` 之间
   *  —— 那一对紧邻关系是 01 篇已实测的 DOM 事实，`bar.nextElementSibling === input` 必须继续成立）。
   *  绘制次序由 `z-index` 决定（镜像 0 / textarea 1），与 DOM 次序无关 ⇒ 视觉上镜像仍在 textarea 之下。 */
  function composerMirrorEl(input) {
    if (composerMirror && composerMirror.parentElement === input.parentElement) return composerMirror;
    const el = document.createElement("div");
    el.id = "-agent-composer-mirror";
    el.className = "-agent-composer-mirror";
    el.setAttribute("aria-hidden", "true");
    input.parentElement.appendChild(el);
    composerMirror = el;
    return el;
  }

  /** 重算镜像内容与几何（输入 / 粘贴 / 滚动 / 换行 / resize / 字号变化 / 程序化插入后都调它）。 */
  function syncComposerChips() {
    const input = $("#agent-input");
    if (!input || !input.parentElement) return;
    const mirror = composerMirrorEl(input);
    const raw = String(input.value || "");
    COMPOSER_TOKEN_RE.lastIndex = 0;
    const hasToken = COMPOSER_TOKEN_RE.test(raw);
    if (!hasToken || !input.offsetWidth) {
      // 无 token（或面板收起、量为 0）⇒ 覆盖层关掉、textarea 恢复原样式：**零视觉差异**
      mirror.classList.remove("-on");
      input.classList.remove("-agent-chips-on");
      return;
    }
    mirror.innerHTML = composerChipsHtml(raw);
    mirror.classList.add("-on");
    input.classList.add("-agent-chips-on");
    mirror.style.left = input.offsetLeft + "px";
    mirror.style.top = input.offsetTop + "px";
    mirror.style.width = composerMirrorWidth(input) + "px";
    mirror.style.height = composerMirrorHeight(input) + "px";
    mirror.scrollTop = input.scrollTop;
    mirror.scrollLeft = input.scrollLeft;
  }

  (function bindComposerChips() {
    const input = $("#agent-input");
    if (!input) return;
    ["input", "keyup", "change", "paste", "cut", "drop"].forEach(function (ev) {
      input.addEventListener(ev, function () {
        setTimeout(syncComposerChips, 0); // 让浏览器先把新值/新尺寸落定
      });
    });
    input.addEventListener("scroll", syncComposerChips);
    window.addEventListener("resize", syncComposerChips);
    // 字号：`display-settings.js::applyFontSize` 把 `--agent-font-size` 打在 `#-agent-dock` 的行内 style 上
    const dock = $("#-agent-dock");
    if (dock && window.MutationObserver) {
      new MutationObserver(syncComposerChips).observe(dock, { attributes: true, attributeFilter: ["style"] });
    }
    // 程序化插入（`insertMention` / `insertSessionToken`）与发送清空（`ask`）不触发 `input` 事件 ⇒ 包一层
    const baseInsertMentionForChips = insertMention;
    insertMention = function () {
      const out = baseInsertMentionForChips.apply(null, arguments);
      syncComposerChips();
      return out;
    };
    const baseInsertSessionTokenForChips = insertSessionToken;
    insertSessionToken = function () {
      const out = baseInsertSessionTokenForChips.apply(null, arguments);
      syncComposerChips();
      return out;
    };
    const baseAskForChips = ask;
    ask = function () {
      const out = baseAskForChips.apply(null, arguments);
      syncComposerChips();
      return out;
    };
    syncComposerChips();
  })();

  // ④ 气泡 → seq：`agent_session_load` 回来的 `seq` 标到气泡 DOM 上（顺序与 `messages` 一一对应）。
  const baseLoadSessionForSeq = loadSession;
  loadSession = function () {
    const pending = baseLoadSessionForSeq.apply(null, arguments);
    return Promise.resolve(pending).then(function (res) {
      if (res && res.status === "ok") {
        const box = $("#agent-messages");
        const list = res.messages;
        if (box && Array.isArray(list)) {
          const bubbles = box.querySelectorAll(".-agent-msg");
          for (let i = 0; i < bubbles.length && i < list.length; i += 1) {
            const seq = list[i] && list[i].seq;
            if (Number.isInteger(seq) && seq >= 0) bubbles[i].setAttribute("data-agent-seq", String(seq));
          }
        }
      }
      return res;
    });
  };

  // 后注册的监听（基座先跑、本行后跑 ⇒ 能读到基座刚摆好的按钮）只做气泡文案修正。
  document.addEventListener("selectionchange", relabelSelAdd);
  ["mouseup", "scroll"].forEach(function (ev) { document.addEventListener(ev, relabelSelAdd); }); // scroll 同源：按钮由 syncSelAdd 重算，文案也得跟着重算

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-20 追加（三项；用户："显示区域引用定位得有开始行号字符号和结束行号字符号，而且在对话框
  // 渲染是把引用视作一个块整体删除或者光标整体跳过，而且对话内的引用没有渲染，也没有开始结束的标记"）：
  //   ① 选区 token 带**列号**：`@路径#L3C2-L5C7`（列可只写一端 ⇒ 另一端按行首 / 行末）；
  //   ② 输入框里引用是**原子块**（Backspace / Delete 整体删、← / → 整体跳过、整块选中即高亮）；
  //   ③ 对话气泡（user + assistant）把区间 / 会话片段引用渲染成 chip 并显示**起止**。
  // 纪律：整块**追加在本 IIFE 末尾**（`return` 之前）⇒ 上方所有 `agent-panel.js:<行号>` 锚点零漂移；
  // 需要改既有行为时**按名重绑**（本文件既有手法：`selAddHit` / `linkifyUser` / `renderMessages` 都这么改）。
  // ══════════════════════════════════════════════════════════════════════════════

  // ── ① 列号：源码区端点 → 行内字符位置 ────────────────────────────────────────

  /** 行内**字符偏移**：只数 `.-line-content` 内的文本节点（**不数行号列** `.-lineno`）。
   *  `node` 是元素容器时按「子节点序号前已累计的文本」折算。取不到（端点不在本行内容里）回 `null`。 */
  function lineContentOffset(node, offset) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    const content = el && el.closest ? el.closest(".-line-content") : null;
    if (!content || !document.createTreeWalker) return null;
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, null);
    let total = 0;
    let cur = walker.nextNode();
    if (node && node.nodeType === 3) {
      while (cur) {
        if (cur === node) return total + (offset || 0);
        total += (cur.nodeValue || "").length;
        cur = walker.nextNode();
      }
      return null;
    }
    if (node && node.nodeType === 1 && content.contains(node)) {
      let before = 0;
      let t = walker.nextNode();
      while (t && !node.contains(t)) {
        before += (t.nodeValue || "").length;
        t = walker.nextNode();
      }
      let inner = 0;
      let child = node.firstChild;
      let idx = 0;
      while (child && idx < offset) {
        inner += child.textContent ? child.textContent.length : 0;
        child = child.nextSibling;
        idx += 1;
      }
      return before + inner;
    }
    return null;
  }

  /** 源码区端点 → `{line, col, lineStart}`；`col` = **1 起字符位置**（caret 语义：行首 1 / 行末 caret = 行长+1）。
   *  行号取不到回 `null`；列取不到（端点落在行内容的强元素边界）回 `col: null`（⇒ token 里省略列，不猜）。 */
  function editorPoint(node, offset) {
    const line = sourceLineAt(node);
    if (!line) return null;
    const off = lineContentOffset(node, offset);
    if (off === null) return { line: line, col: null, lineStart: false };
    return { line: line, col: off + 1, lineStart: off === 0 };
  }

  /** 选区token 拼写的**纯函数**（不碰 DOM；列缺省就不写 `C<列>`，后端按行首 / 行末解）。
   *  ⚠️ 与 `docs/design/dsh-agent-port.md §6.21` 的语法表逐字对应；测试 `tests/test_agent_panel_token.py`
   *  从本文件抽出此函数体用 `node` 实跑（不是复制一份实现）。 */
  function rangeTokenText(path, sLine, sCol, eLine, eCol) {
    const p = String(path || "").replace(/\\/g, "/");
    if (!p) return "";
    const head = /\s/.test(p) ? '@"' + p + '"' : "@" + p;
    if (!(sLine > 0)) return head;
    const at = function (line, col) { return "L" + line + (col > 0 ? "C" + col : ""); };
    const multi = eLine > sLine;
    const sameLineRange = eLine === sLine && eCol > 0 && sCol > 0 && eCol > sCol;
    if (multi || sameLineRange) return head + "#" + at(sLine, sCol) + "-" + at(eLine, eCol);
    return head + "#" + at(sLine, sCol);
  }

  /** 选区位置（重绑 §6.20 版）：源码区**加列号**；预览区仍是**块级**近似（只给行，不给列 —— 诚实）。
   *  终点恰停在**下一行行首**（源码区）⇒ 收回到上一行且列缺省（= 上一行行末），不多算一行。 */
  selectionLocation = function (range) {
    const anchor = range.commonAncestorContainer;
    const editor = $("#editor");
    if (editor && editor.contains(anchor)) {
      const s = editorPoint(range.startContainer, range.startOffset);
      if (!s) return null;
      let e = editorPoint(range.endContainer, range.endOffset);
      if (e && e.lineStart && e.line > 1) e = { line: e.line - 1, col: null };
      if (!e || e.line < s.line) e = { line: s.line, col: null };
      return { host: "editor", startLine: s.line, startCol: s.col, endLine: e.line, endCol: e.col };
    }
    const preview = $("#preview");
    if (preview && preview.contains(anchor)) {
      const a = previewBlockRange(range.startContainer);
      let b = previewBlockRange(range.endContainer) || a;
      if (a && b && b[0] > a[1] && range.endOffset === 0) {
        const prev = prevPreviewBlockEnd(range.endContainer);
        if (prev && prev >= a[0]) b = [prev, prev];
      }
      if (!a || !b) return null;
      return {
        host: "preview",
        ...previewRangeEndpoints(range, a, b), // 反标命中 ⇒ 精确行:列；否则退回块级近似
        // 说明（占位保持行号零漂移）：本分支原为 startLine/startCol/endLine/endCol 四个显式字段，
        // 现统一由 previewRangeEndpoints() 产出 —— 单一事实源，避免两处预览分支各自演化；
        // 未反标时 col 为 null（行为与改前逐字一致）。
      };
    }
    const box = $("#agent-messages");
    if (box && box.contains(anchor)) {
      const from = bubbleSeq(range.startContainer);
      const to = from === null ? null : bubbleSeq(range.endContainer); // 气泡无事件 seq（本 run 刚生成的当轮）也不再"不出入口"，落点由 addSelectionToChat 决定
      // ↑ 仍返回 messages 宿主：入口照常出现；拿不到 seq 时写入**整会话**引用（不静默、不假装精确）
      return { host: "messages", seqFrom: from, seqTo: to === null ? from : to, offFrom: messageOffsetAt(range.startContainer, range.startOffset), offTo: messageOffsetAt(range.endContainer, range.endOffset) };
    }
    return null;
  };

  /** 选区 → 输入框 token（重绑 §6.20 版，多带列号；`insertSessionToken` 落点规则一行未改）。 */
  formatRangeMention = function (path, sLine, sCol, eLine, eCol) {
    return rangeTokenText(path, sLine, sCol, eLine, eCol);
  };

  addSelectionToChat = function () {
    const hit = selAddHit();
    hideSelAdd();
    if (!hit || !hit.loc) return;
    const loc = hit.loc;
    if (loc.host === "messages") {
      const token = sessionFragmentToken(loc.seqFrom, loc.seqTo, loc.offFrom, loc.offTo); // 带**消息内字符区间**（对话栏里拖拽选取的起止）
      if (token) insertSessionToken(token); else if (sessionId) quoteSession(String(sessionId)); // 无事件 seq（本 run 刚生成的当轮）⇒ 退回**整会话**引用，与历史行「引用」同一落法
      return;
    }
    const path = state.currentPath || "";
    if (!path) return;
    insertSessionToken(formatRangeMention(path, loc.startLine, loc.startCol, loc.endLine, loc.endCol));
  };

  // ── ② 输入框引用 = 原子块 ───────────────────────────────────────────────────

  /** 当前输入框文本的 token 区间（与镜像层**同一解析器** `COMPOSER_TOKEN_RE`，含前导空白折算）。 */
  function composerTokenSpans(text) {
    const raw = String(text == null ? "" : text);
    const spans = [];
    COMPOSER_TOKEN_RE.lastIndex = 0;
    for (const m of raw.matchAll(COMPOSER_TOKEN_RE)) {
      const token = m[1] !== undefined ? m[1] : m[3] || "";
      if (!token) continue;
      const start = m[1] !== undefined ? m.index : m.index + (m[2] || "").length;
      spans.push({ start: start, end: start + token.length, token: token });
    }
    return spans;
  }

  /** 落点 → token 下标：`"end"`/`"start"` = caret 恰好贴尾 / 贴首；`"left"`/`"right"` = caret 落在 token 内部。
   *  找不到回 `-1`（绝不猜）。 */
  function tokenAtCaret(spans, pos, mode) {
    for (let i = 0; i < spans.length; i += 1) {
      const s = spans[i];
      if (mode === "end" && pos === s.end) return i;
      if (mode === "start" && pos === s.start) return i;
      if (mode === "left" && pos > s.start && pos <= s.end) return i;
      if (mode === "right" && pos >= s.start && pos < s.end) return i;
    }
    return -1;
  }

  /** 一次编辑替换 `[start,end)`：优先 `execCommand("insertText")`（**浏览器原生撤销栈**里算一次编辑），
   *  不支持时退回 `setRangeText`（内容正确，但能否单步撤销由浏览器定 —— 见报告"仍做不到的"）。 */
  function replaceInputRange(input, start, end, text) {
    let done = false;
    try {
      input.setSelectionRange(start, end);
      done = !!(document.execCommand && document.execCommand("insertText", false, text));
    } catch (_err) {
      done = false;
    }
    if (!done) input.setRangeText(text, start, end, "end");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function afterComposerEdit(input, pos) {
    inputCaret = pos;
    syncComposerChips();
  }

  (function bindComposerAtomicTokens() {
    const input = $("#agent-input");
    if (!input) return;
    input.addEventListener(
      "keydown",
      function (e) {
        if (e.isComposing || e.keyCode === 229) return; // 输入法组字中：一行都不碰
        if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return; // 带修饰键（含 Shift 选择）不碰
        const key = e.key;
        if (key !== "Backspace" && key !== "Delete" && key !== "ArrowLeft" && key !== "ArrowRight") return;
        const spans = composerTokenSpans(input.value);
        if (!spans.length) return;
        const from = input.selectionStart;
        const to = input.selectionEnd;
        if (!Number.isInteger(from) || from !== to) return; // 有选区时交给浏览器默认行为（整体覆盖删除本就一次编辑）
        if (key === "Backspace" || key === "Delete") {
          const i = tokenAtCaret(spans, from, key === "Backspace" ? "left" : "right"); // 贴边**或落在块内**都整体删（杜绝块内编辑）
          if (i < 0) return;
          e.preventDefault();
          replaceInputRange(input, spans[i].start, spans[i].end, "");
          afterComposerEdit(input, spans[i].start);
          return;
        }
        const j = tokenAtCaret(spans, from, key === "ArrowLeft" ? "left" : "right");
        if (j < 0) return;
        e.preventDefault();
        const pos = key === "ArrowLeft" ? spans[j].start : spans[j].end;
        input.setSelectionRange(pos, pos);
        afterComposerEdit(input, pos);
      },
      true
    );
    ["select", "mouseup"].forEach(function (ev) {
      input.addEventListener(ev, function () {
        setTimeout(syncComposerChips, 0);
      });
    });
  })();

  /** 单个 token → chip HTML（**逐字保留原文** ⇒ 镜像与 textarea 同宽不错位；`active` = 整块被选中）。 */
  function composerChipHtml(token, active) {
    const cls = "-agent-composer-chip" + (active ? " -agent-composer-chip--active" : "");
    const session = /^@\[(?:\\.|[^\\\]])*\]\(dsh-session:([^\s)]*)\)$/.exec(token);
    if (session) {
      if (!sessionAliasOrUriOk(session[1].split("#seq:")[0])) return esc(token);
      return '<span class="' + cls + ' -agent-composer-chip--session">' + esc(token) + "</span>";
    }
    const file = /^@(?:"([^"]*)"?|([^\s"]+?))(#L\d+(?:C\d+)?(?:-L\d+(?:C\d+)?)?)?$/.exec(token);
    if (!file) return esc(token);
    const body = (file[1] !== undefined ? file[1] : file[2]) || "";
    if (!body) return esc(token);
    const range = file[3] || "";
    const head = range ? token.slice(0, token.length - range.length) : token;
    return (
      '<span class="' + cls + (range ? " -agent-composer-chip--range" : "") + '">' +
      esc(head) +
      (range ? '<span class="-agent-composer-chip-range">' + esc(range) + "</span>" : "") +
      "</span>"
    );
  }

  /** 全文 → chip HTML（逐段转义；`activeIndex` 那一个加 `--active`）。 */
  function composerChipsHtmlWithActive(raw, spans, activeIndex) {
    let out = "";
    let last = 0;
    for (let i = 0; i < spans.length; i += 1) {
      const sp = spans[i];
      if (sp.start < last) continue;
      out += esc(raw.slice(last, sp.start)) + composerChipHtml(sp.token, i === activeIndex);
      last = sp.end;
    }
    return out + esc(raw.slice(last));
  }

  /** 重算镜像（重绑 §6.20 版：多算一个「当前块」高亮；几何 / 零视觉差异口径一行未改）。 */
  syncComposerChips = function () {
    const input = $("#agent-input");
    if (!input || !input.parentElement) return;
    const mirror = composerMirrorEl(input);
    const raw = String(input.value || "");
    const spans = composerTokenSpans(raw);
    if (!spans.length || !input.offsetWidth) {
      mirror.classList.remove("-on");
      input.classList.remove("-agent-chips-on");
      return;
    }
    let active = -1;
    const from = input.selectionStart;
    const to = input.selectionEnd;
    if (Number.isInteger(from)) {
      for (let i = 0; i < spans.length; i += 1) {
        const s = spans[i];
        if (from === to && (from === s.start || from === s.end)) { active = i; break; } // caret 贴边
        if (from === s.start && to === s.end) { active = i; break; } // 整块选中
      }
    }
    mirror.innerHTML = composerChipsHtmlWithActive(raw, spans, active);
    mirror.classList.add("-on");
    input.classList.add("-agent-chips-on");
    mirror.style.left = input.offsetLeft + "px";
    mirror.style.top = input.offsetTop + "px";
    mirror.style.width = composerMirrorWidth(input) + "px";
    mirror.style.height = composerMirrorHeight(input) + "px";
    mirror.scrollTop = input.scrollTop;
    mirror.scrollLeft = input.scrollLeft;
  };

  // ── ③ 对话内引用渲染（起止可见） ─────────────────────────────────────────────

  /** `@路径#L3C2-L5C7` / `@路径#L3-L5` / `@路径#L3` → `{path, sLine, sCol, eLine, eCol}`；不匹配回 `null`。 */
  function rangeMentionParts(token) {
    const m = /^@(?:"([^"]*)"?|([^\s"]+?))#L(\d+)(?:C(\d+))?(?:-L(\d+)(?:C(\d+))?)?$/.exec(String(token || ""));
    if (!m) return null;
    const path = (m[1] !== undefined ? m[1] : m[2]) || "";
    if (!path) return null;
    const num = function (v) { return v === undefined ? null : Number(v); };
    return { path: path, sLine: Number(m[3]), sCol: num(m[4]), eLine: num(m[5]), eCol: num(m[6]) };
  }

  /** 起止的**可见**串：`12:5–14:20`（单行 `12:5`；缺列只写行）。 */
  function rangeSpanText(parts) {
    const one = function (line, col) { return String(line) + (col ? ":" + col : ""); };
    const from = one(parts.sLine, parts.sCol);
    const single = parts.eLine === null || parts.eLine === parts.sLine;
    if (single) {
      if (parts.eLine === null || !parts.eCol || parts.eCol === parts.sCol) return from;
      return from + "–" + one(parts.eLine, parts.eCol);
    }
    return from + "–" + one(parts.eLine, parts.eCol);
  }

  /** 区间引用 chip（`-agent-mention--range`）：正文 = `路径 起–止`，title 里把「起 / 止」写全；
   *  点击复用既有锚点委托（`data-agent-file` / `data-agent-line`）⇒ 打开文件并高亮起始行。 */
  function rangeChipEl(parts) {
    const from = String(parts.sLine) + (parts.sCol ? ":" + parts.sCol : "");
    const to = parts.eLine === null ? from : String(parts.eLine) + (parts.eCol ? ":" + parts.eCol : "");
    const el = document.createElement("span");
    el.className = "-agent-mention -agent-mention--range";
    el.setAttribute("role", "link");
    el.setAttribute("tabindex", "0");
    el.setAttribute("title", T("agent.rangeChipTitle", { path: parts.path, from: from, to: to }));
    el.setAttribute("data-agent-file", parts.path);
    el.setAttribute("data-agent-line", String(parts.sLine));
    el.textContent = parts.path + " " + rangeSpanText(parts);
    return el;
  }

  function rangeChipHtml(parts) {
    return rangeChipEl(parts).outerHTML;
  }

  /** 会话**片段**引用 chip（`-agent-mention--session`）：正文 `@label` + 片段序号（起止可见），
   *  title 写全会话 id 与 `#seq:` 区间；点击复用既有 `data-agent-session` 委托（切历史并高亮）。 */
  function sessionFragmentChipEl(id, label, uri) {
    const frag = /#seq:(\d+)(?:c(\d+))?(?:-(\d+)(?:c(\d+))?)?/.exec(String(uri || ""));
    const seq = frag ? frag[0].slice("#seq:".length) : "";
    const el = document.createElement("span");
    el.className = "-agent-mention -agent-mention--session";
    el.setAttribute("role", "link");
    el.setAttribute("tabindex", "0");
    el.setAttribute("title", seq ? T("agent.sessionChipTitleSeq", { id: id, seq: seq }) : T("agent.mention.sessionTitle", { id: id }));
    el.setAttribute("data-agent-session", id);
    el.textContent = "@" + label;
    if (seq) {
      const tail = document.createElement("span");
      tail.className = "-agent-mention-seq";
      tail.textContent = fragmentSpanText(frag[1], frag[2], frag[3], frag[4]); // 起–止（含消息内字符位，如 `3:12–3:48`）
      el.appendChild(tail);
    }
    return el;
  }

  /** 气泡引用扫描器：**只认** ① 会话片段 `@[label](dsh-session:…#seq:n)` ② 文件区间 `@path#L…`。
   *  普通 `@路径` / 无片段会话仍交给既有 `linkifyUser`（不抢它的活）。 */
  const REF_MENTION_RE = new RegExp(
    "@\\[((?:\\\\.|[^\\\\\\]])*)\\]\\((dsh-session:[^\\s)]*#seq:\\d+(?:-\\d+)?)\\)" +
      "|(^|\\s)(@(?:\"([^\"]*)\"?|(\\S+?))#L\\d+(?:C\\d+)?(?:-L\\d+(?:C\\d+)?)?)",
    "g"
  );

  /** user 气泡：在既有（会话 aware 的）包装层**之外**再包一层，先切出片段 / 区间 token。 */
  const baseLinkifyUserForRefs = linkifyUser;
  linkifyUser = function (text) {
    const raw = String(text == null ? "" : text);
    let out = "";
    let last = 0; REF_MENTION_RE.lastIndex = 0; // 全局正则：`matchAll` 继承当前 lastIndex ⇒ 先归零
    for (const m of raw.matchAll(REF_MENTION_RE)) {
      let html = "";
      let start = m.index;
      let end = m.index + m[0].length;
      if (m[2] !== undefined) {
        const id = decodeSessionUri(String(m[2]).split("#seq:")[0]);
        if (id === null) continue; // 非规范 URI：退回既有渲染（绝不猜）
        const label = m[1] === undefined ? id : String(m[1]).replace(/\\(.)/g, "$1");
        html = sessionFragmentChipEl(id, label, m[2]).outerHTML;
      } else {
        const parts = rangeMentionParts(m[4]);
        if (!parts) continue;
        start = m.index + (m[3] || "").length;
        html = rangeChipHtml(parts);
      }
      if (start < last) continue;
      out += baseLinkifyUserForRefs(raw.slice(last, start));
      out += html;
      last = end;
    }
    out += baseLinkifyUserForRefs(raw.slice(last));
    return out;
  };

  /** assistant 气泡：在**已净化**的 DOM 里把区间引用换成 chip（只动文本节点）。
   *  **绝不碰** 代码块 / 行内代码（`code` / `pre` / `kbd` / `samp`）、脚本 / 样式、公式（katex / math 类）、
   *  已完成锚点化的 `-agent-anchor`；raw HTML 在 `sanitizeHtmlInto` 阶段已按白名单拆壳，这里无需另判。 */
  const REF_CHIP_SKIP_TAGS = { CODE: 1, PRE: 1, KBD: 1, SAMP: 1, SCRIPT: 1, STYLE: 1, TEXTAREA: 1 };
  function chipRangeRefsInDom(root) {
    if (!root || root.nodeType !== 1 || !document.createTreeWalker) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      const text = node.nodeValue || "";
      REF_MENTION_RE.lastIndex = 0;
      if (!REF_MENTION_RE.test(text)) return;
      for (let el = node.parentElement; el && el !== root.parentElement; el = el.parentElement) {
        if (REF_CHIP_SKIP_TAGS[el.tagName]) return;
        if (el.classList && el.classList.contains("-agent-anchor")) return;
        if (/katex|math/i.test(String(el.className || ""))) return;
      }
      REF_MENTION_RE.lastIndex = 0;
      const frag = document.createDocumentFragment();
      let last = 0;
      let m;
      while ((m = REF_MENTION_RE.exec(text)) !== null) {
        let chip = null;
        let start = m.index;
        let end = m.index + m[0].length;
        if (m[2] !== undefined) {
          const id = decodeSessionUri(String(m[2]).split("#seq:")[0]);
          if (id === null) continue;
          const label = m[1] === undefined ? id : String(m[1]).replace(/\\(.)/g, "$1");
          chip = sessionFragmentChipEl(id, label, m[2]);
        } else {
          const parts = rangeMentionParts(m[4]);
          if (!parts) continue;
          start = m.index + (m[3] || "").length;
          chip = rangeChipEl(parts);
        }
        if (start < last) continue;
        if (start > last) frag.appendChild(document.createTextNode(text.slice(last, start)));
        frag.appendChild(chip);
        last = end;
      }
      if (!frag.childNodes.length || !node.parentNode) return;
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  const baseRenderAssistantBodyForRefs = renderAssistantBody;
  renderAssistantBody = function (el, text) {
    baseRenderAssistantBodyForRefs(el, text);
    chipRangeRefsInDom(el);
  };

  /* ══ 气泡「可寻址」：消息原文 ↔ 可见文本的字符区间（2026-09-20；用户选 C「渲染也做可寻址结构」）══
     目的：在对话栏里**拖拽选取某次回复（或某条提问）里的一段话**时给出精确「起–止」——与文件引用
     `@路径#L3C2-L5C7` 同一套口径；落到会话片段 token 上就是 `#seq:<条>c<a>-<条>c<b>`。
     为什么不换渲染管线（不把气泡改走 Memoria 的 lexer/parser/renderer）：助手气泡的 `sanitizeHtmlInto()`
     是硬前置，它**丢弃全部属性**（只留白名单标签）⇒ 渲染时打的行号标记活不下来；助手输出又属不可信文本，
     换掉净化链是安全回退。改用**渲染后反标**：可见文本一定是消息原文的有序子序列（Markdown 标记被消费掉），
     逐文本节点在原文里从游标处向后找自己即可 —— 与渲染管线**解耦**（marked / 纯文本 + chip 都走这一条）。
     找不到（MathJax 排版产物、表格补齐的空格等）⇒ 标 `data-md-drop="1"` 并**冻结游标**（不猜、不硬凑）。
     本块追加在 IIFE 末尾（`return {…}` 之前）⇒ 仅门面行号变化，上方 anchor 零漂移。 */

  /** 给气泡正文的每个可见文本节点套一层 `[data-md-from][data-md-to]`（0 基、半开区间；值为**消息原文**偏移）。 */
  function annotateMessageOffsets(el, text) {
    const raw = String(text == null ? "" : text);
    if (!el || !raw || !document.createTreeWalker) return;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let node;
    while ((node = walker.nextNode())) nodes.push(node);
    let cursor = 0;
    for (const tn of nodes) {
      const piece = tn.nodeValue || "";
      if (!piece.trim() || !tn.parentNode) continue; // 纯空白不动（表头补齐、缩进都属排版产物）
      const at = raw.indexOf(piece, cursor);
      const span = document.createElement("span");
      span.className = "-md-off";
      if (at < 0) {
        span.setAttribute("data-md-drop", "1"); // 反标不到 ⇒ 明说"这段不可寻址"，调用方退回整条口径
      } else {
        span.setAttribute("data-md-from", String(at));
        span.setAttribute("data-md-to", String(at + piece.length));
        cursor = at + piece.length;
      }
      span.textContent = piece;
      tn.parentNode.replaceChild(span, tn);
    }
  }

  /** 气泡内某点 → **消息原文**里的 0 基字符偏移；落在未标注区域 ⇒ `null`（不猜）。 */
  function messageOffsetAt(node, offset) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    const seg = el && el.closest ? el.closest("[data-md-from]") : null;
    if (!seg) return null;
    const from = Number(seg.getAttribute("data-md-from"));
    if (!Number.isFinite(from)) return null;
    const length = (seg.textContent || "").length;
    return from + Math.max(0, Math.min(Number(offset) || 0, length));
  }

  /** 片段后缀（纯函数，可单测）：`#seq:<条>[c<位>][-<条>[c<位>]]`。
   *  字符位只在**两端都拿得到**时才写（缺一端 ⇒ 退回整条 / 整段口径，绝不半猜）；写就两端都写。 */
  function fragmentSuffix(seqFrom, offFrom, seqTo, offTo) {
    const start = Number(seqFrom);
    if (!Number.isInteger(start) || start < 0) return ""; // 事件 seq 是 **0 起**（`conversation_messages()` 的 seq）
    const end = typeof seqTo === "number" && Number.isInteger(seqTo) && seqTo >= start ? seqTo : start;
    const cFrom = typeof offFrom === "number" && Number.isInteger(offFrom) && offFrom >= 0 ? offFrom + 1 : 0;
    const cTo = typeof offTo === "number" && Number.isInteger(offTo) && offTo >= 1 ? offTo : 0;
    if (!cFrom || !cTo || cTo < cFrom) return end > start ? "#seq:" + start + "-" + end : "#seq:" + start;
    return "#seq:" + start + "c" + cFrom + "-" + end + "c" + cTo;
  }

  /** 片段 chip 可见串（纯函数）：`3` / `3–7` / `3:12–3:48` / `3:12–7:48`（与文件 chip 的 `12:5–14:20` 同风格）。 */
  function fragmentSpanText(seqFrom, cFrom, seqTo, cTo) {
    const one = function (seq, chr) { return String(seq) + (chr ? ":" + chr : ""); };
    const last = seqTo ? String(seqTo) : String(seqFrom);
    const tail = last === String(seqFrom) && !cTo ? "" : "–" + one(last, cTo);
    return one(seqFrom, cFrom) + tail;
  }

  /* ══ 会话引用「短别名」token（2026-09-20）══════════════════════════════════════════════
     用户口径：「会话引用不需要渲染会话id，太占地方，**实际要传入**」。
     做法：输入框里只写**别名** —— `@[标题](dsh-session:s1#seq:3-7)`（`s1`/`s2`… 每个真实会话 id
     一个），真实 id 留在下面这张内存表里；**发送前**由 `ask()` 调 `expandSessionAliases()`
     换成完整 `dsh-session:<base64url>` URI ⇒ 发给后端、写进会话历史、被气泡渲染/审计工具看到的
     **一律是可解析的完整形式**（别名只活在当前输入框里，发送即不再出现）。
     为什么不是"显示层替换"：镜像层 chip 必须与 textarea **逐字同宽**，只改 chip 的可见文字会让
     chip 之后的光标/选区与可见文字错位（在 chip 后面打字最明显）——所以让**两边都变短**。
     落点纪律：本块追加在 IIFE 末尾（`return {…}` 门面之前）⇒ 仅门面行号变化，上方 anchor 零漂移。 */
  const sessionAliasById = new Map(); // 真实 id → 别名
  let sessionAliasSeq = 0;

  /** 真实 id → 稳定别名（同一 id 反复引用只占一个别名）。 */
  function sessionAliasFor(id) {
    const key = String(id == null ? "" : id);
    if (!key) return "";
    if (!sessionAliasById.has(key)) {
      sessionAliasSeq += 1;
      sessionAliasById.set(key, "s" + sessionAliasSeq);
    }
    return sessionAliasById.get(key);
  }

  /** 别名形态的规范 URI（拼不出来时退回完整 URI，宁可长也不丢引用）。 */
  function sessionAliasUri(id) {
    const alias = sessionAliasFor(id);
    return alias ? SESSION_URI_PREFIX + alias : sessionUri(id);
  }

  /** payload 合法性：**已登记别名**或**可解码的完整 base64url** 都算（镜像 chip 与解析器共用这一判据）。 */
  function sessionAliasOrUriOk(payload) {
    const p = String(payload == null ? "" : payload);
    if (!p) return false;
    for (const alias of sessionAliasById.values()) {
      if (alias === p) return true;
    }
    return decodeSessionUri(SESSION_URI_PREFIX + p) !== null;
  }

  /** 发送前展开：`dsh-session:s1…` → `dsh-session:<真实 base64url>…`；未登记的别名原样保留（不猜）。 */
  function expandSessionAliases(text) {
    const raw = String(text == null ? "" : text);
    if (!raw || !sessionAliasSeq) return raw;
    return raw.replace(/dsh-session:(s\d+)/g, function (full, alias) {
      for (const entry of sessionAliasById.entries()) {
        if (entry[1] === alias) return sessionUri(entry[0]);
      }
      return full;
    });
  }

  /* ══ 预览区「源坐标」**按需现算**（2026-09-20 二次实现：一个字节的 DOM 都不写）══════════════════
     目的：预览区拖拽选取也产出**精确的 `行:列`**（`@路径#L3C2-L5C7`）。思路与气泡反标同一套：渲染后的
     可见文本一定是**源文本的有序子序列**（Markdown 标记被消费掉）⇒ 逐文本节点在源码里从游标处向后找自己。
     **为什么从"预打标"改成"按需现算"**（首版给每个文本节点套 `span.-src-seg[data-src-line]`）：
     ① 预览**编辑态**走 `mapper` 的 DOM↔AST 光标映射，插入包裹节点会破坏它 ⇒ 首版只好加"编辑态直接返回"
        的守卫，而真机默认常常就是编辑态 ⇒ 功能**整体失效**（用户报障："预览现在不能映射回去精确的字符号"）；
     ② 预打标会替换文本节点 ⇒ 触发打标的那次选区端点失效，要额外维护替换表，且编辑态 DOM 变化会让缓存失真。
     按需现算**不写 DOM、无缓存、无失效**，编辑态与只读态**同一套**逻辑。
     块的**源行范围**取自 `data--src-line(-end)`（单一事实源）；只在该块的行区间内找，绝不跨块乱窜。 */

  /** 取元素端点内部的首 / 末文本节点（`offset` 为 0 ⇒ 首，其余 ⇒ 末）；里面没有文本节点回 `null`。 */
  function edgeTextNode(el, offset) {
    if (!el || el.nodeType !== 1) return null;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let first = null;
    let last = null;
    let n;
    while ((n = walker.nextNode())) {
      if (!first) first = n;
      last = n;
    }
    if (!first) return null;
    return offset ? last : first;
  }

  /** 预览区某点 → `{line, col}`（1 起源码行列）；该点的可见文本在源码里找不到 ⇒ `null`（不猜、不硬凑）。 */
  function previewSourcePoint(node, offset) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    const block = el && el.closest ? el.closest("[data--src-line]") : null;
    if (!block) return null;
    const A = window.MemoriaApp;
    const body = A && A.state && A.state.doc ? String(A.state.doc.body || "") : "";
    const start = Number(block.getAttribute("data--src-line")) || 0;
    if (!start || !body) return null;
    const end = Number(block.getAttribute("data--src-line-end")) || start;
    const lines = body.split("\n");
    const target = node && node.nodeType === 3 ? node : edgeTextNode(node, offset);
    if (!target) return null;
    let line = start - 1; // 0 基行下标
    let col = 0;          // 该行内已消费到的字符下标（0 基）
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let tn;
    while ((tn = walker.nextNode())) {
      const piece = tn.nodeValue || "";
      let at = -1;
      let hit = -1;
      if (piece.trim()) { // 纯空白是排版产物（表格补齐、缩进）：不参与匹配，也不推进游标
        while (line < Math.min(end, lines.length)) {
          const idx = lines[line].indexOf(piece, col);
          if (idx >= 0) { at = idx; hit = line; break; }
          line += 1;
          col = 0;
        }
      }
      if (tn === target) {
        if (at < 0) return null; // 反标不到（MathJax 产物 / 图片 alt 等）⇒ 明说不可寻址，退回块级近似
        const inner = Math.max(0, Math.min(Number(offset) || 0, piece.length));
        return { line: hit + 1, col: at + inner + 1 };
      }
      if (at >= 0) { line = hit; col = at + piece.length; }
    }
    return { line: start, col: 1 }; // 端点落在块内非文本节点（如 <br>）⇒ 退化为块首（比 null 有用）
  }

  /** 预览区选区 → `{startLine,startCol,endLine,endCol}`：反标命中 ⇒ 精确；否则退回块级近似（列给 null）。 */
  function previewRangeEndpoints(range, a, b) {
    const ps = previewSourcePoint(range.startContainer, range.startOffset);
    const pe = previewSourcePoint(range.endContainer, range.endOffset);
    return {
      startLine: ps ? ps.line : Math.min(a[0], b[0]),
      startCol: ps ? ps.col : null,
      endLine: pe ? pe.line : Math.max(a[1], b[1]),
      endCol: pe ? pe.col : null,
    };
  }

  /** 把**事件 seq** 标到"本 run 刚生成"的实时气泡上（拖拽引用要它；载入历史会话时由 `loadSession` 回填）。
   *  对齐方式：`messages[]` 与气泡 1:1（`renderMessages()` 逐条渲染）⇒ 数量一致就按序号对齐；不一致
   *  （存在"已停止/报错"等不落盘的气泡）⇒ 退回**按角色 + 文本**匹配，仍对不上的气泡跳过（不猜）。
   *  每轮结束静默跑一次（一次本地 RPC）；失败或换库就保持现状 —— 入口照常出现，只是退回整会话引用。 */
  async function tagLiveBubblesWithSeqs() {
    const id = sessionId ? String(sessionId) : "";
    if (!id) return;
    const bubbles = Array.from(document.querySelectorAll("#agent-messages .-agent-msg"));
    if (!bubbles.length) return;
    let res = null;
    try {
      res = await call("agent_session_load", id, state.kbPath || null);
    } catch (_err) {
      return;
    }
    const list = res && res.status === "ok" && Array.isArray(res.messages) ? res.messages : null;
    if (!list || !list.length) return;
    const tag = function (bubble, item) {
      const seq = item && item.seq;
      if (bubble && Number.isInteger(seq) && seq >= 0) bubble.setAttribute("data-agent-seq", String(seq));
    };
    if (list.length === messages.length && bubbles.length === messages.length) {
      for (let i = 0; i < list.length; i += 1) tag(bubbles[i], list[i]);
      return;
    }
    const used = new Set();
    for (let i = 0; i < messages.length && i < bubbles.length; i += 1) {
      const rec = messages[i];
      if (!rec) continue;
      const idx = list.findIndex(function (item, j) {
        return !used.has(j) && item && item.role === rec.role && String(item.text || "") === String(rec.text || "");
      });
      if (idx < 0) continue;
      used.add(idx);
      tag(bubbles[i], list[idx]);
    }
  }

  /** 拖拽载荷契约的**唯一生产者入口**：文件树 / 顶栏文件页签都走它 ⇒ MIME 与 JSON 形状只有一处定义。
   *  接收端就是本模块的 `readMentionPayload()`（同一 MIME）；`text/plain` 副本供其它输入框或外部程序使用。 */
  window.MemoriaMentionDrag = {
    set: function (e, path, kind) {
      const text = String(path == null ? "" : path).replace(/\\/g, "/");
      const dt = e && e.dataTransfer;
      if (!dt || !text) return false;
      const isDir = kind === "dir";
      dt.effectAllowed = "copy";
      try {
        dt.setData(DRAG_MIME, JSON.stringify({ path: text, kind: isDir ? "dir" : "file" }));
      } catch (_err) {
        // 个别宿主不接受自定义 MIME：此时对话栏接不到这次拖拽（text/plain 仍写，供其它消费方）
      }
      dt.setData("text/plain", isDir ? text.replace(/\/+$/, "") + "/" : text);
      return true;
    },
  };

  // ══════════════════════════════════════════════════════════════════════════════
  // 历史行「右键菜单」（2026-09-20；用户："历史对话栏的每一行的「删除」做到右键下拉菜单，
  // 这个菜单还要添加「重命名」，然后鼠标悬浮在这些对话栏上悬浮提示右键更多操作"）
  // ① **行内 `-hist-del` 按钮退役**：行动作（重命名 / 删除）统一收进右键菜单；菜单与确认弹窗
  //    复用 app.js 的**通用** `.-context-menu` / `.-modal`（门面 `showTreeContextMenu` /
  //    `confirmTreeAction`；file-tree.js 与 image-tools.js 亦共用同一对浮层）。
  // ② **删除**改走应用内确认弹窗（菜单点一下即弹框，不再有"行内点两次"）。
  // ③ **重命名**：后端 `agent_session_rename` **追加**一条 `session/title`（"最新者胜"）⇒
  //    列表 / 回放 / 模型输入零改动（依据见 `services/agent/title.py` 政策一节）。
  // ④ **零行漂移**：整块追加在 IIFE 末尾 ⇒ 上方所有 `agent-panel.js:<行号>` 锚点保持有效。
  //    代价：旧的行内两段式确认（`histDelete()` 与 `histDeleteArmed` / `histDeleteTimer` /
  //    `DELETE_CONFIRM_MS`）及其点击分支**原样保留但已不可达**（行内按钮在下面被即时摘除）——
  //    这是"锚点优先"纪律下的刻意取舍，待允许行号漂移的批次再清理。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 悬浮提示 = 菜单的发现入口（菜单只能右键唤出 ⇒ 提示必须常显在行上）。 */
  function histRowHint() {
    return T("agent.historyList.rightClickMore");
  }

  /** 摘掉退役的行内「删除」按钮 + 给整行（含标题）挂「右键更多操作」悬浮提示。
   *  在既有 `renderHistoryList` **之后**跑（包装调用）⇒ 既有渲染函数一个字符都没动。 */
  function decorateHistoryRowMenu() {
    const list = document.getElementById("hist-list");
    if (!list) return;
    const hint = histRowHint();
    const rows = list.querySelectorAll("[data-hist-id]");
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      const del = row.querySelector("[data-hist-del]");
      if (del) del.remove(); // 行内「删除」退役（见块头 ①）
      row.title = hint;
      // 标题自带 `title`（长标题截断时可看全称）⇒ 把提示**并进**它，否则悬停在标题上看不到提示
      const ttl = row.querySelector(".-hist-title");
      if (ttl) {
        const full = String(ttl.getAttribute("title") || ttl.textContent || "");
        ttl.setAttribute("title", full ? full + "\n" + hint : hint);
      }
    }
  }

  const baseRenderHistoryListForMenu = renderHistoryList;
  renderHistoryList = function () {
    const pending = baseRenderHistoryListForMenu.apply(null, arguments);
    decorateHistoryRowMenu();
    return pending;
  };

  /** 生成中不给改当前会话：那个文件正被本轮作业的 `SessionStore` 追加写，
   *  另开一个 store 去写会撞 `seq`（`store.py` 的 `_seq` 是构造时点数得出的）。 */
  function histRowLocked(id) {
    if (busy && String(id) === String(sessionId || "")) {
      showFlashError(T("agent.history.busyLock"));
      return true;
    }
    return false;
  }

  /** 右键某一行 ⇒ 打开行菜单（重命名 / 删除）。 */
  function openHistRowMenu(x, y, id) {
    if (!id) return;
    A().showTreeContextMenu?.(x, y, [
      {
        label: T("agent.history.rename"),
        action: function () {
          histRename(id);
        },
      },
      {
        label: T("agent.history.delete"),
        danger: true,
        action: function () {
          histDeleteWithConfirm(id);
        },
      },
    ]);
  }

  /** 菜单「删除」：先弹应用内确认框（会话文件删掉不可恢复），确认后才真删并刷新列表。 */
  function histDeleteWithConfirm(id) {
    if (!id || histRowLocked(id)) return;
    const row = histDataRow(id);
    A().confirmTreeAction?.(
      T("agent.history.deleteTitle"),
      T("agent.history.deleteBody", { name: histTitle(row) || id }),
      T("agent.history.delete"),
      async function () {
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
    );
  }

  /** 菜单「重命名」：输入新标题 ⇒ `agent_session_rename` 追加一条 `session/title`；随后刷新列表
   *  （`fold_title()` 取最后一条非空 ⇒ 新标题即刻生效，回放与模型输入不受影响）。 */
  function histRename(id) {
    if (!id || histRowLocked(id)) return;
    const row = histDataRow(id);
    promptHistInput(
      T("agent.history.renameTitle"),
      T("agent.history.renamePh"),
      histTitle(row),
      T("agent.history.rename"),
      async function (val) {
        if (!val) return;
        const kb = state.kbPath || "";
        let res;
        try {
          res = await call("agent_session_rename", id, val, kb || null);
        } catch (e) {
          res = { status: "error", message: String((e && e.message) || e) };
        }
        if (!res || res.status !== "ok") {
          showFlashError(fullErrorText(res) || T("agent.history.renameFail"));
          return;
        }
        await refreshHistory(); // 列表标题与 dock「当前会话」随之更新
      }
    );
  }

  /** 轻量输入弹窗（`.-modal` 样式；pywebview 里 `prompt()` 是系统对话框，故自建。
   *  与 file-tree.js 的 `promptTreeInput` 同形但**各持一份**（frontend-modules.md R5：不跨文件借私有符号）。 */
  function promptHistInput(title, placeholder, initial, okLabel, cb) {
    const overlay = document.createElement("div");
    overlay.className = "-modal";
    overlay.innerHTML =
      '<div class="-modal-backdrop"></div>' +
      '<div class="-modal-box" style="width:min(360px,92vw)">' +
      '<div class="-modal-header" style="cursor:default"><span>' +
      esc(title) +
      "</span></div>" +
      '<div class="-modal-body">' +
      '<input data-role="hist-title" type="text" style="width:100%;box-sizing:border-box;padding:6px 8px;' +
      "border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);" +
      'border-radius:4px;font-size:12px;outline:none" placeholder="' +
      esc(placeholder || "") +
      '" value="' +
      esc(initial || "") +
      '" /></div>' +
      '<div class="-modal-footer -btn-bar">' +
      '<span class="-modal-footer-spacer"></span>' +
      '<button type="button" class="-btn" data-act="cancel">' +
      T("common.cancel") +
      "</button>" +
      '<button type="button" class="-btn primary" data-act="ok">' +
      esc(okLabel || T("common.ok")) +
      "</button>" +
      "</div></div>";
    document.body.appendChild(overlay);
    const input = overlay.querySelector('[data-role="hist-title"]');
    const close = function (val) {
      overlay.remove();
      cb(val);
    };
    overlay.querySelector(".-modal-backdrop").addEventListener("click", function () {
      close(null);
    });
    overlay.querySelector('[data-act="cancel"]').addEventListener("click", function () {
      close(null);
    });
    overlay.querySelector('[data-act="ok"]').addEventListener("click", function () {
      close(input.value.trim() || null);
    });
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        close(input.value.trim() || null);
      } else if (ev.key === "Escape") {
        close(null);
      }
    });
    setTimeout(function () {
      input.focus();
      input.select();
    }, 30);
  }

  // 右键委托挂在**页签视图**上（不是 document）：`stopPropagation()` 才能拦住 app.js 那条
  // 全局 contextmenu（它会关掉刚打开的菜单 —— 菜单不在它的目标里）。视图节点常驻 DOM
  //（`ensureHistoryView()` 只换 innerHTML），故绑一次即可。
  (function bindHistRowMenu() {
    const view = historyViewEl();
    if (!view || view.dataset.histCtxBound === "1") return;
    view.dataset.histCtxBound = "1";
    view.addEventListener("contextmenu", function (ev) {
      const t = ev.target && ev.target.closest ? ev.target.closest("[data-hist-id]") : null;
      if (!t) return;
      ev.preventDefault();
      ev.stopPropagation();
      openHistRowMenu(ev.clientX, ev.clientY, t.getAttribute("data-hist-id") || "");
    });
  })();

  renderHistoryList(); // 用包装后的版本重绘一次（把新提示与按钮摘除应用到当前列表）

  /* ══ 消息下方的操作行 + 写入状态条（2026-09-21 第二版，人定稿）══════════════════════════
     人：「撤销按钮和复制按钮都放在每个对话气泡的下方，不是气泡内，或者说 agent 回复甚至不需要气泡框住」
        「用户只能在最后一次对话下方撤销，而且只能撤销不能 redo」
        「文件修改状态可以效仿 trae 的做法，给一个状态栏可以展开」

     结构（`#agent-messages` 的直接子元素由 `.-agent-msg` 变成 `.-agent-turn`）：
       .-agent-turn[--assistant|--user]
         ├ .-agent-msg           ← 内容（助手不再有边框/底色；用户保留浅底，见 `app.css` 末尾那块）
         ├ .-agent-msg-actions   ← **气泡外面**的操作行：[复制]（每条助手消息）
         └ .-agent-write         ← **只挂在最新一条助手消息下**：可展开的写入状态条 + [撤销]

     为什么用"重新赋值包装"而不是改函数内部：`pushMessage` / `renderMessages` / `finalizeMessage`
     都是同作用域的函数声明、按**名字**调用 ⇒ 一次赋值三处生效，`agent-panel.js` 上方所有
     `<行号>` 锚点**零漂移**。 */

  /** 复制一条消息的**原文**（Markdown）：clipboard API 优先，被拒（失焦 / 无权限）时回退
   *  `execCommand`（与 `kb-check.js` 同款两段式）；按钮上给一次「已复制 / 复制失败」反馈。 */
  async function copyMessageText(rec, btn) {
    const text = String((rec && rec.text) || "");
    if (!text) return;
    let ok = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        ok = true;
      }
    } catch (e) {
      ok = false;
    }
    if (!ok) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try {
        ok = document.execCommand("copy");
      } catch (e2) {
        ok = false;
      }
      ta.remove();
    }
    if (!btn) return;
    // 图标按钮：不改文字，改用**悬停提示 + 变色**给一次成败反馈
    const restoreTitle = T("agent.copy");
    btn.title = ok ? T("agent.copyDone") : T("agent.copyFail");
    btn.classList.toggle("-agent-act--done", !!ok);
    setTimeout(function () {
      btn.title = restoreTitle;
      btn.classList.remove("-agent-act--done");
    }, 1200);
  }

  /** 「复制」的图标（内联 SVG，不依赖任何图标集）：人要求「改成复制的图标，鼠标悬浮显示复制」。 */
  const COPY_ICON_SVG =
    '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">' +
    '<rect x="5.75" y="5.75" width="8.25" height="8.25" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.3"/>' +
    '<path d="M3.4 10.25V3.6A1.6 1.6 0 0 1 5 2h6.4" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>' +
    "</svg>";

  /** 一条消息下方的操作行（**在气泡外面**）：目前是「复制」，只给助手消息。
   *
   *  注意"有正文才建按钮"这条守卫只在**建行那一刻**成立；助手消息是**空文本**建的
   *  （`pushMessage("assistant", "")`）⇒ 实时那一轮建行时它必然返回空行，终答后要靠
   *  `syncTurnActions()` 补上（2026-09-22 L4 抓到的真 bug，见该函数注释）。 */
  function actionsEl(rec) {
    const box = document.createElement("div");
    box.className = "-agent-msg-actions";
    if (!rec || rec.role === "user" || !String(rec.text || "").trim()) return box;
    box.appendChild(copyButtonEl(rec));
    return box;
  }

  /** 把一条消息的 DOM 包进 `.-agent-turn`（内容 + 操作行）；已经包过就复用原容器。 */
  function wrapTurn(rec, msgEl) {
    const box = $("#agent-messages");
    if (!box) return null;
    const msg = msgEl || box.lastElementChild;
    if (!msg || !msg.classList || !msg.classList.contains("-agent-msg")) return null;
    const parent = msg.parentElement;
    if (parent && parent.classList && parent.classList.contains("-agent-turn")) return parent;
    const turn = document.createElement("div");
    turn.className =
      "-agent-turn " + (rec && rec.role === "user" ? "-agent-turn--user" : "-agent-turn--assistant");
    box.replaceChild(turn, msg);
    turn.appendChild(msg);
    turn.appendChild(actionsEl(rec));
    return turn;
  }

  const pushMessageBase = pushMessage;
  pushMessage = function (role, text) {
    const rec = pushMessageBase(role, text);
    wrapTurn(rec);
    renderWriteState(); // 「撤销只在最后一次对话下方」⇒ 每次追加消息后重挂
    return rec;
  };

  const renderMessagesBase = renderMessages;
  renderMessages = function () {
    renderMessagesBase();
    const box = $("#agent-messages");
    if (!box) return;
    // 按文档序取"消息"（排除计划卡片 `.-agent-plan-msg` 与空态），与 `messages` 一一对应
    const msgs = Array.prototype.slice.call(box.querySelectorAll(".-agent-msg:not(.-agent-plan-msg)"));
    msgs.forEach(function (msg, index) {
      wrapTurn(messages[index] || null, msg);
    });
    renderWriteState();
  };

  const finalizeMessageBase = finalizeMessage;
  finalizeMessage = function (result) {
    finalizeMessageBase(result);
    renderWriteState(); // 正文变了 ⇒ 重挂状态条（消息仍是最新那一条）
    refreshAfterTurn(result); // 回合收尾**无条件刷工作区**（人 2026-09-21：结束时不刷新）
  };

  /** 回合结束后的**工作区刷新**（人 2026-09-21：「每次对话结束 memoria 没有刷新，程序上先挂一个刷新」）。
   *
   *  为什么需要它：原来只有"写入回执"那条路会刷（`plan-confirm.syncAfterWrite()`），而 agent 现在是
   *  **调用内直接落盘**、回执链路任何一环没走到（本回合只是读+答、提议没被 drain…）时，文件树 /
   *  待确认 / 图谱 / 当前文档就停在本回合之前的样子。⇒ 在**每回合收尾**（`finalizeMessage()`，`done`
   *  与 `error` 都走）无条件刷一次。
   *
   *  口径：① 三个 KB 视图（树 / 待确认 / 图谱）**无条件**刷；② 当前文件**只在"本回合确实写过库"
   *  且没有未保存编辑时**重开（`.-agent-turn` 里人的脏编辑绝不覆盖）；③ 与 `syncAfterWrite()` 用
   *  `A().__kbRefreshAt` 做 **1.5s 去重** —— 两者谁先跑到都不会把图谱连算两遍（`syncAfterWrite`
   *  的去重只跳"三个视图"，它那条**精确**的"确知被写就重开"永远执行）。 */
  function shouldSkipKbRefresh(now, lastAt) {
    return now - (Number(lastAt) || 0) < 1500;
  }

  /** 本回合是否**写过库**：`propose_write` 成功过一次就算（它是唯一的写工具，调用内即落盘）。 */
  function turnWroteSomething(result) {
    const rows = result && Array.isArray(result.tool_calls) ? result.tool_calls : [];
    return rows.some(function (row) {
      return !!row && row.name === "propose_write" && !row.is_error;
    });
  }

  async function refreshAfterTurn(result) {
    const app = A();
    if (shouldSkipKbRefresh(Date.now(), app.__kbRefreshAt)) return;
    app.__kbRefreshAt = Date.now();
    try {
      await app.refreshFiles?.();
    } catch (e) {
      /* 刷不动不影响对话本身 */
    }
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
    if (!turnWroteSomething(result)) return; // 没写过库 ⇒ 不动编辑器（不打断人正在看的东西）
    try {
      if (window.__memoriaHasPendingEdits && window.__memoriaHasPendingEdits()) return; // 有脏编辑 ⇒ 不覆盖
      const cur = (state && state.currentPath) || "";
      if (cur) await app.openFile?.(cur, { skipNav: true });
    } catch (e) {
      /* 同上 */
    }
  }

  /* ── 顶部**副标题行**里的写入状态栏（人 2026-09-21 定稿）──────────────────────────────────
     位置：`.-agent-subhead`（就是原来的 `.-agent-history` 那一行；会话名与「历史」按钮已搬到
     `.-agent-head`，见 `restructureHeader()`）。**撤销 / 重做只在这里出现一次**，不再挂在每条消息下方。
     两态：**纯 bar**（一行摘要 + 撤销一步 / 重做一步）/ **点击展开**（栈轨迹 + 本步文件明细）。
     文案两态：**已修改 N 个文件 /（无 state 时不渲染）**—— 原先还有个「已撤销」短显态，2026-09-21
     已**删除**：它会在"撤到最底"时把整条状态栏收掉，连**重做入口一起收掉**（人报：「撤销之后栈状态栏
     就没了，我无法重做」）。栈里只要有步骤就该显示，可用性交给 `can_undo` / `can_redo`。
     `state` 形状：`{files: [{path, lines}], failed, txid, stack, onUndo, onRedo}`；`null` = 无改动。 */
  let writeState = null;

  /** 副标题行（状态栏宿主）；首次访问时补上新名 `-agent-subhead`。 */
  function subheadEl() {
    const dock = document.getElementById("-agent-dock");
    if (!dock) return null;
    const hist = dock.querySelector(".-agent-history");
    if (hist && !hist.classList.contains("-agent-subhead")) hist.classList.add("-agent-subhead");
    return hist;
  }

  /** 顶栏重排（人：「当前会话的名称改成在 head 显示（纯会话名）…历史按钮放这里，不用显示模型行名，
   *  history 这栏显示状态，而且改名不叫 history 叫 subhead」）。**只搬 DOM、不动 `index.html`** ⇒ 零行漂移。 */
  function restructureHeader() {
    const dock = document.getElementById("-agent-dock");
    if (!dock) return;
    const head = dock.querySelector(".-agent-head");
    const sub = subheadEl();
    if (!head || !sub || head.dataset.restructured === "1") return;
    const model = head.querySelector("#agent-model-label");
    if (model) model.hidden = true; // 不显示模型名（DOM 保留，切模型的逻辑照旧）
    const label = sub.querySelector(".-agent-history-label");
    if (label) label.hidden = true; // 不显示"当前会话"这几个字
    const current = sub.querySelector("#agent-history-current");
    const openBtn = sub.querySelector("#agent-history-open");
    if (current) head.appendChild(current); // 会话名 → head
    if (openBtn) head.appendChild(openBtn); // 「历史」按钮 → head
    head.dataset.restructured = "1";
  }

  /** 「撤销一步」/「重做一步」按钮（栈语义：一步一退 / 一步一进）。可用性由栈指针决定。 */
  function stepButton(direction, st, stack) {
    const isRedo = direction === "redo";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "-agent-act " + (isRedo ? "-agent-write-redo" : "-agent-write-undo");
    btn.title = T(isRedo ? "agent.redoTitle" : "agent.undoTitle");
    btn.textContent = T(isRedo ? "agent.redo" : "agent.undo");
    const can =
      !!st && !st.failed && stack
        ? isRedo
          ? !!stack.can_redo
          : !!stack.can_undo
        : false;
    btn.disabled = !can;
    btn.addEventListener("click", async function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      btn.disabled = true;
      btn.textContent = T(isRedo ? "agent.redoing" : "agent.undoing");
      const handler = isRedo ? st && st.onRedo : st && st.onUndo;
      const done = await (handler ? handler() : Promise.resolve(false));
      if (!done) {
        // 失败或没有回调 ⇒ 复位（成功的路径由调用方重新取栈后整体重绘）
        btn.textContent = T(isRedo ? "agent.redo" : "agent.undo");
        btn.disabled = false;
      }
    });
    return btn;
  }

  /** 状态栏元素（两态：纯 bar / 点击展开；含「撤销一步 / 重做一步」与栈轨迹）。 */
  function writeBarEl() {
    const st = writeState;
    const stack = (st && st.stack) || null;
    const wrap = document.createElement("div");
    wrap.className = "-agent-write-bar";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "-agent-act -agent-write-toggle";
    toggle.setAttribute("aria-expanded", "false");
    const summary = st && st.failed
      ? T("agent.writeFailed")
      : st
        ? T("agent.writeSummary", { n: (st.files || []).length })
        : T("agent.writeIdle");
    // 栈位置（人：「采用 stack 设计」）⇒ bar 态就能看到"第几步 / 共几步"
    toggle.textContent =
      stack && stack.total ? summary + "  " + T("agent.stackPos", { p: stack.position, t: stack.total }) : summary;
    wrap.appendChild(toggle);
    wrap.appendChild(stepButton("undo", st, stack));
    wrap.appendChild(stepButton("redo", st, stack));
    if (st && !st.failed) {
      const body = document.createElement("div");
      body.className = "-agent-write-body";
      body.hidden = true;
      // ① 栈轨迹（每步一行；当前指针高亮）——这是"展开态"的主要信息
      const steps = (stack && stack.steps) || [];
      if (steps.length) {
        const trace = document.createElement("div");
        trace.className = "-agent-write-trace";
        steps.forEach(function (step, index) {
          const row = document.createElement("div");
          row.className =
            "-agent-write-step" + (step.current ? " is-current" : "") + (step.applied ? " is-applied" : "");
          row.textContent =
            T("agent.stackStep", { i: index + 1, n: step.files || 0 }) + (step.current ? "  ← " + T("agent.stackHere") : "");
          trace.appendChild(row);
        });
        body.appendChild(trace);
      }
      // ② 本步（最近一次写入）的文件明细
      (st.files || []).forEach(function (row) {
        const line = document.createElement("div");
        line.className = "-agent-write-file";
        line.title = String(row.path || "");
        line.textContent =
          String(row.path || "") + (row.lines ? "  " + T("agent.writeLines", { n: row.lines }) : "");
        body.appendChild(line);
      });
      toggle.addEventListener("click", function () {
        body.hidden = !body.hidden;
        toggle.setAttribute("aria-expanded", body.hidden ? "false" : "true");
        wrap.classList.toggle("-agent-write--open", !body.hidden);
        // 宿主（`.-agent-subhead`）被 `--bar-h-b` 钉成一行高 ⇒ 展开时改由内容撑开，否则会溢出盖住
        // `.-agent-head` 与消息区顶部（L4 实测过）。
        if (wrap.parentElement) {
          wrap.parentElement.classList.toggle("-agent-write-host--open", !body.hidden);
        }
      });
      wrap.appendChild(body);
    }
    return wrap;
  }

  /** 把状态栏渲染进**副标题行**（无改动且不在"已撤销"提示期 ⇒ 该行留空）。 */
  function renderWriteState() {
    restructureHeader();
    const sub = subheadEl();
    if (!sub) return;
    Array.prototype.slice.call(sub.querySelectorAll(".-agent-write-bar")).forEach(function (el) {
      el.remove();
    });
    sub.classList.remove("-agent-write-host--open"); // 每次重绘都回到"一行高"（折叠态为常态）
    if (!writeState) return;
    sub.appendChild(writeBarEl());
  }

  /** 告知"这次对话写了什么"（`null` = 无改动）。撤销按钮由本模块渲染，点击回调交回调用方。
   *
   *  ⚠️ **必须经由下面的 `return {...}` 暴露**，不能在 IIFE 内部 `Object.assign` 到那个全局名：
   *  本文件是 `window.MemoriaAgentPanel = (function () { … })()` 形式，IIFE 内部执行时那个全局名**还没被赋值**
   *  ⇒ `Object.assign` 只会创建一个**临时对象**，随后被 `return` 的对象覆盖 ⇒ 方法丢失（实测踩过：
   *  状态条/撤销按钮完全不出现，且无任何报错）。 */
  function setWriteState(next) {
    writeState = next || null;
    renderWriteState();
  }

  // 页面一加载就把顶栏按人定稿重排（会话名 / 「历史」→ `.-agent-head`；`.-agent-history` 兼作
  // `-agent-subhead`，用来放写入状态栏）。放在 IIFE 末尾 ⇒ `index.html` 零改动、锚点零漂移。
  restructureHeader();

  // ══════════════════════════════════════════════════════════════════════════════
  // 状态行撤除 + 用量行定位修正 + 「没有最终答复」如实说明（2026-09-21，人报三件事）
  //   ① 「对话框下面这个（`#agent-status`）能不能去掉」⇒ `index.html` 那行**改成注释**（保留行数 ⇒
  //      不动 index.html 既有行号锚点），元素就此消失。原 `setStatusText()` 因为取不到元素而自动变成
  //      空操作，故这里**接管**它：只记状态（`statusBarDotState()` 判红点用），并把原本**只**显示在
  //      那行的提示（未输问题 / 换库丢弃 / 超时 / 配置读取失败）改走顶部浮层，不让它们**彻底消失**。
  //      「断网」**不弹**：它是**状态**（状态 bar 有红字槽、发送键已禁用 + 悬停说明），不是一次出错。
  //   ② 「agent 最后一次回话下方没有显示 token 使用情况以及命中率」⇒ 根因是**序位错位**：计划 / 写入
  //      回执卡也带 `-agent-msg--assistant`（`plan-confirm.js`）却不在 `messages` 里 ⇒ 按 assistant
  //      序位取 DOM 会整体偏一格。这里给每个消息元素打 `data-msg-index`，与上面两处 `assistantWrapFor()`
  //      配对使用；用量行同时补上命中率（键 `agent.usage.rate`）。
  //   ③ 「agent 有时候思考就卡在思考了，然后没有后文」⇒ 真机取证（AAA_Vocab 会话
  //      `session-20260921T111525Z-ab1ac72c`）：`loop/end {stop_reason:"max-iterations", iterations:8}`，
  //      而最后一轮 `assistant/message` 的 `content` 是**空串**（只调工具）⇒ 后端 `answer=""`，前端过去
  //      完全不看 `stop_reason` ⇒ 气泡全空，看着就像"卡住了"。`stopNote()` 把这种"没有最终答复"如实
  //      写成一句可行动的话（`agent.stop.*`），不再让人对着空气猜。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 同一次失败只弹一次浮层：`setStatusText(..., true)` 与显式 `showFlashError()` 常成对出现（两种
   *  先后顺序都有）⇒ 300ms 内只放行第一个，否则一次失败会弹两个 toast。 */
  let flashGuardAt = 0;
  function flashOnce(fn, args) {
    if (Date.now() - flashGuardAt < 300) return undefined;
    flashGuardAt = Date.now();
    return fn.apply(null, args);
  }

  /** 顶部浮层入口（包装）：只加"去重闸门"，其余与原行为逐字一致。 */
  const baseShowFlashErrorBeforeStatus = showFlashError;
  showFlashError = function () {
    return flashOnce(baseShowFlashErrorBeforeStatus, arguments);
  };

  /** 接管状态行写入：可见状态行已撤 ⇒ 只记状态；"会消失的"错误改走顶部浮层（见本块顶注 ①）。 */
  const baseSetStatusTextBeforeStatus = setStatusText;
  setStatusText = function (msg, error) {
    const text = String(msg == null ? "" : msg);
    const isNew = text !== lastStatusText; // 配置刷新 / 整串重绘会重复设同一句 ⇒ 不再弹一次
    lastStatusText = text;
    lastStatusError = !!error;
    if (error && isNew && text && text !== T("agent.err.net_disabled")) {
      flashOnce(baseShowFlashErrorBeforeStatus, [text]);
    }
    return baseSetStatusTextBeforeStatus.apply(null, arguments);
  };

  /** 本轮**没有最终答复**时的说明（工具轮达上限 / 输出被长度截断 / 内容策略 / 只出思考没正文）。 */
  function stopNote(result) {
    const reason = String((result && result.stop_reason) || "");
    if (reason === "max-iterations") return T("agent.stop.maxIterations", { n: (result && result.iterations) || 0 });
    if (reason === "max-tokens") return T("agent.stop.maxTokens");
    if (reason === "content-filter") return T("agent.stop.filtered");
    // 正常收尾却**没有正文**（例如只流了思考块、正文为空）：同样要说一句，否则气泡空白、
    // 人看到的仍是"卡在思考没有后文"（`test_agent_thinking_stream.py` 明确允许 `answer==""`）。
    return T("agent.stop.emptyAnswer");
  }

  /** 给每个消息元素打**稳定索引**（`assistantWrapFor()` 的定位依据），并渲染本回合的**过程内容**
   *  （思考行 + 过程行；compact 档在构成最终答复时折叠）。只包装 `messageEl()`、不改它本体
   *  ⇒ 上方锚点零漂移。旧的 `toolsStrip()`（气泡末尾的工具摘要条）已由本块取代（见文件末尾块）。 */
  const baseMessageElForIndex = messageEl;
  messageEl = function (rec) {
    const el = baseMessageElForIndex.apply(null, arguments);
    const idx = messages.indexOf(rec);
    if (el && idx >= 0) el.dataset.msgIndex = String(idx);
    renderProcessInto(el, rec);
    return el;
  };

  // ══════════════════════════════════════════════════════════════════════════════
  // 一次回合的「过程内容」（2026-09-22；对齐上游 dsh 的 Turn Process Folding）+ 对话显示档
  //   ① 思考行：**始终默认折叠**（AG08 的 `thinkEl()` 创建即折叠），摘要流式跟**末行**、定稿取**首行**；
  //   ② 工具行：`process_delta` 边到边追加 / 同 `id` 的结果行**就地**更新（不重建整块 ⇒ 不闪烁、不打断
  //      滚动），一行 = 状态点 + `工具名 · 参数摘要`；`running`→「运行中…」、`error`→「失败（code）」红字、
  //      `ok` 不加字（避免噪声，状态点由 CSS 按 `data-state` 着色）；
  //   ③ 回合结束（`finalizeMessage`）：**compact 档**且末步构成最终答复 ⇒ 把过程收进折叠容器、气泡
  //      **顶部**给一行计数摘要按钮（`N 次工具调用 · N 条过程消息 · N 次失败`，全 0 回落「思考了一会儿」）；
  //      不是最终答复（只调工具 / 出错）⇒ 整轮过程**全部保留可见**；`normal` 档**永不折叠**、也不渲染
  //      摘要行；展开态按轮记忆（`rec.processOpen`）、新回合默认折叠。正文 / 锚点条 / 错误条 /
  //      「（已停止）」标记都**留在折叠容器之外**（它们是独立节点，永远不折）。
  //   ④ 设置项 `#agent-transcript`（`normal` / `compact`，落 `config/agent.json: transcript_mode`）
  //      在设置弹窗「对话」页签（`#agent-refresh` 旁），改动即保存并**立即重绘**（折叠态随之改变）；
  //   ⑤ 回放：`agent_session_load` 的记录带 `process` 时按**同一套**渲染（`loadSession` 把行与思考灌进
  //      `rec`；旧的会话没有该键 ⇒ 保持现状、不报错、不留空壳）；
  //   ⑥ 旧的 `toolsStrip()`（气泡末尾的工具摘要条）已删除并被本块取代 —— **失败可见性不退化**：
  //      折叠态有摘要里的「N 次失败」，展开后有红字「失败（code）」+ 输出；没有实时过程通道时（例如
  //      `result.tool_calls` 有、`rec.process` 为空）用 `result.tool_calls[]` 合成过程行。
  //   落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  //: 已投递的过程行**条数**（与文本游标、思考游标**完全独立**）；每轮提问由 `ask()` 包装重置。
  let processCursor = 0;

  /** 回放记录里的过程行（`agent_session_load` 的 `process` 键）；没有该键 ⇒ `null`（旧会话不动形状）。 */
  function msgProcess(rec) {
    return rec && Array.isArray(rec.process) ? rec.process : null;
  }

  /** 回放记录里的思考文本：把各 `step` 行的 `reasoning` 按顺序拼起来（无 ⇒ 空串；**仅兼容字段**，
   *  渲染已改为按步的 `kind:"think"` 行，见 `withThinkRows()`）。 */
  function msgReasoning(rec) {
    const parts = [];
    // **最终答复那一步**的思考（回放记录上的 `reasoning` 字段，见 `history._flush_turn()`）：它不在
    // `process` 里（过程列表有意跳过最终答复，免得正文重复）⇒ 少了这一行，单步回合的思考会整块丢。
    if (rec && typeof rec.reasoning === "string" && rec.reasoning.trim()) parts.push(rec.reasoning);
    (rec && Array.isArray(rec.process) ? rec.process : []).forEach(function (row) {
      if (row && row.kind === "step" && typeof row.reasoning === "string" && row.reasoning.trim()) parts.push(row.reasoning);
    });
    return parts.join("\n");
  }

  /** **按步**把思考插进过程行（2026-09-22 改版）：每个带 `reasoning` 的 `step` 行**前面**插一条
   *  `kind:"think"`；**最终答复那一步**的思考（`rec.reasoning`）**排在最后**（它就是"最终答复之前
   *  的那次思考"，天然在末尾）。
   *
   *  为什么这么摆（人：「agent 回话都是上面一个思考，然后产出总结并结束，但 dsh 里思考是**多次开展
   *  多次结束**的」）：思考本来就是**随步**产生的（`turn_process.step_row()` 把 `reasoning` 挂在
   *  `step` 上、`session/history` 按步存），拼成一条会丢掉"第几步在想什么"以及它与工具行的交替关系。
   *  纯函数（不改入参、可单测）。 */
  function withThinkRows(rows, rec) {
    const out = [];
    (Array.isArray(rows) ? rows : []).forEach(function (row) {
      if (row && row.kind === "step" && typeof row.reasoning === "string" && row.reasoning.trim()) {
        out.push({ kind: "think", text: row.reasoning, state: "done", iteration: row.iteration || 0 });
      }
      out.push(row);
    });
    if (rec && typeof rec.reasoning === "string" && rec.reasoning.trim()) {
      out.push({ kind: "think", text: rec.reasoning, state: "done", iteration: 0 });
    }
    return out;
  }

  /** 回合内的过程行缓冲（实时 `process_delta` 与回放记录**共用同一形状**，见 turn_process.py）。 */
  function procRows(rec) {
    return rec && Array.isArray(rec.process) ? rec.process : [];
  }

  /** 末条 `step` 行是否构成**最终答复**（正文非空白且无工具调用）；尾部的工具行不参与判定。 */
  function finalAnswerFromRows(rows) {
    const list = Array.isArray(rows) ? rows : [];
    for (let i = list.length - 1; i >= 0; i -= 1) {
      const row = list[i];
      if (!row || row.kind !== "step") continue;
      return !!String(row.text || "").trim() && !Number(row.tool_calls || 0);
    }
    return false;
  }

  /** 该回合在 compact 档下是否**可折叠**：实时侧由 `finalizeMessage` 判定后写进 `rec.processFinal`；
   *  回放记录没有实时帧 ⇒ 按行形状推 —— 末行是**已收尾的工具行**说明「最终答复那条 `step`」已被后端
   *  `turn_process.process_items()` 从 `process` 里跳过；末行是 `step` 或**未收尾**的工具行 ⇒ 不可折。 */
  function processFoldable(rec, rows) {
    if (rec && rec.processFinal === true) return true;
    if (rec && rec.processFinal === false) return false;
    const last = rows && rows.length ? rows[rows.length - 1] : null;
    return !!(last && last.kind === "tool" && String(last.state || "") !== "running");
  }

  /** 对话显示档（`transcript_mode`）：只认 `normal` / `compact`，其余（含缺省）一律 `compact`。 */
  function transcriptMode() {
    return cfg && cfg.transcript_mode === "normal" ? "normal" : "compact";
  }

  /** 工具行状态文案：`running` → 「运行中…」、`error` → 「失败（code）」、`ok` → 空串（不加噪声）。 */
  function toolStateText(row) {
    const state = String((row && row.state) || "");
    if (state === "running") return T("agent.tool.running");
    if (state === "error") {
      const code = String((row && row.code) || "");
      return T("agent.tool.failed") + (code ? "（" + code + "）" : "");
    }
    return "";
  }

  /** 工具行的**原生悬停提示** = 工具名 + 参数摘要 + 输出全文。 */
  function toolRowTitle(row) {
    return [
      String((row && row.name) || ""),
      String((row && row.summary) || ""),
      String((row && row.detail) || ""),
    ].filter(function (bit) { return !!bit; }).join(" · ");
  }

  /** 就地刷新一条工具行（同 `id` 的结果行到达时用；**不重建节点** ⇒ 不闪烁、不打断滚动）。 */
  function updateToolRowEl(line, row) {
    if (!line) return;
    const detail = String((row && row.detail) || "");
    const state = String((row && row.state) || "");
    line.setAttribute("data-state", state);
    const st = line.querySelector(".-agent-tool-state");
    if (st) {
      st.textContent = toolStateText(row);
      st.classList.toggle("-agent-tool-state--error", state === "error");
    }
    let out = line.querySelector(".-agent-tool-output");
    if (!detail) {
      if (out) out.remove();
      line.classList.remove("-agent-tool--expandable"); // 没有输出 ⇒ 不给展开入口（cursor: default）
    } else {
      if (!out) {
        out = document.createElement("div");
        out.className = "-agent-tool-output";
        const label = document.createElement("div");
        label.className = "-agent-tool-output-label";
        label.textContent = T("agent.tool.output");
        const pre = document.createElement("pre");
        pre.className = "-agent-tool-output-body";
        out.appendChild(label);
        out.appendChild(pre);
        out.hidden = true;
        line.appendChild(out);
        // 点这一行开合输出（行的 `title` 已给全文；展开区是等宽小字 + `pre-wrap`）
        line.addEventListener("click", function () {
          if (!line.classList.contains("-agent-tool--expandable")) return;
          out.hidden = !out.hidden;
          line.classList.toggle("-agent-tool--open", !out.hidden);
        });
      }
      line.classList.add("-agent-tool--expandable");
      const pre = out.querySelector(".-agent-tool-output-body");
      if (pre) pre.textContent = detail;
    }
    line.title = toolRowTitle(row);
  }

  /** 工具行 DOM（**一行**）：状态点 + `工具名 · 参数摘要` + 状态文案；有输出时可点开。 */
  function toolRowEl(row) {
    const line = document.createElement("div");
    line.className = "-agent-tool";
    line.setAttribute("data-tool-id", String((row && row.id) || ""));
    const dot = document.createElement("span");
    dot.className = "-agent-tool-dot";
    dot.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = "-agent-tool-name";
    name.textContent = String((row && row.name) || "");
    const summary = document.createElement("span");
    summary.className = "-agent-tool-summary";
    summary.textContent = String((row && row.summary) || "");
    const state = document.createElement("span");
    state.className = "-agent-tool-state";
    line.appendChild(dot);
    line.appendChild(name);
    if (summary.textContent) {
      const sep = document.createElement("span");
      sep.className = "-agent-tool-sep";
      sep.textContent = "·";
      line.appendChild(sep);
      line.appendChild(summary);
    }
    line.appendChild(state);
    updateToolRowEl(line, row);
    return line;
  }

  /** 同一工具调用的两行（`tool/call` / `tool/result`，**同 `id`**）合并成一行（L4 实测的必要步骤：
   *  结果行的 `summary` 是空串 —— 结果事件没有参数 ⇒ 摘要必须取**先到**那行，状态 / code / detail
   *  取**后到**那行；不合并会让一次调用在回放里显示成两行、其中一行没有参数摘要）。 */
  function mergeToolRows(rows) {
    const out = [];
    const seen = {};
    (Array.isArray(rows) ? rows : []).forEach(function (row) {
      if (!row) return;
      if (row.kind !== "tool") { out.push(row); return; }
      const id = String(row.id || "");
      const prev = id ? seen[id] : null;
      if (!prev) {
        const copy = Object.assign({}, row);
        if (id) seen[id] = copy;
        out.push(copy);
        return;
      }
      if (!String(prev.summary || "").trim()) prev.summary = String(row.summary || "");
      prev.state = row.state;
      if (row.code) prev.code = row.code;
      if (String(row.detail || "")) prev.detail = row.detail;
      if (row.name) prev.name = row.name;
    });
    return out;
  }

  /** 过程行节点序列（**按步的思考行** + `step` 的「更早的助手正文」+ 工具行，按事件 / 到达顺序）。 */
  function processRowsEl(rows) {
    const box = document.createElement("div");
    box.className = "-agent-process";
    (Array.isArray(rows) ? rows : []).forEach(function (row) {
      if (!row) return;
      if (row.kind === "think") {
        if (String(row.text || "").trim()) box.appendChild(thinkEl(row.text, row.state === "live"));
        return;
      }
      if (row.kind === "tool") {
        box.appendChild(toolRowEl(row));
        return;
      }
      if (row.kind !== "step") return;
      const text = String(row.text || "").trim();
      if (!text) return;
      const step = document.createElement("div");
      step.className = "-agent-step";
      renderAssistantBody(step, text); // 与助手正文同一条管线（公式 / 代码 / 列表都渲染）
      box.appendChild(step);
    });
    return box;
  }

  /** 折叠摘要文案：`N 次工具调用 · N 条过程消息`（为 0 的段省略）+（有失败时）` · N 次失败`；
   *  三段全 0 ⇒ 「思考了一会儿」。工具数按 `id` 去重（同一次调用有 `call` / `result` 两行）。 */
  function processSummaryText(rows) {
    const seen = {};
    const seenFailed = {};
    let tools = 0;
    let failed = 0;
    let messages = 0;
    (Array.isArray(rows) ? rows : []).forEach(function (row) {
      if (!row) return;
      if (row.kind === "tool") {
        const id = String(row.id || "");
        if (!seen[id]) { seen[id] = 1; tools += 1; }
        if (String(row.state || "") === "error" && !seenFailed[id]) { seenFailed[id] = 1; failed += 1; }
        return;
      }
      if (row.kind === "step" && String(row.text || "").trim()) messages += 1;
    });
    const parts = [];
    if (tools) parts.push(T("agent.process.tools", { n: tools }));
    if (messages) parts.push(T("agent.process.messages", { n: messages }));
    if (failed) parts.push(T("agent.process.failed", { n: failed }));
    return parts.length ? parts.join(" · ") : T("agent.process.thought");
  }

  /** 没有实时过程通道时的兜底过程行（`result.tool_calls[]` → 行）：**工具失败不可能隐形**。
   *  字段 `{id,name,is_error,code,message}` 已在载荷里 ⇒ `message` 当 `detail`、`is_error` 定 `state`。 */
  function synthesizeRows(rec) {
    const calls = rec && Array.isArray(rec.tools) ? rec.tools : [];
    return calls.map(function (call, index) {
      const isError = !!(call && call.is_error);
      return {
        kind: "tool",
        id: String((call && call.id) || "call-" + index),
        name: String((call && call.name) || ""),
        summary: String((call && call.summary) || ""),
        state: isError ? "error" : "ok",
        code: (call && call.code) || null,
        detail: String((call && call.message) || ""),
        iteration: 0,
      };
    });
  }

  /** 过程容器（`.-agent-process`）：正文**之前**（流式期间思考行 / 工具行的落点）。
   *  **2026-09-22 起思考行在容器内部**（按步、与工具行交错）⇒ 不再需要"把外层思考块拽到容器之前"。
   *  `wrap.querySelector(".-agent-process")` 可能命中**上一次渲染的折叠容器内的**那个：只有它还在
   *  `wrap` 的直接子级里才复用，否则新造一个（避免把新行塞进折叠体里）。 */
  function processBox(wrap) {
    const body = wrap.querySelector(".-agent-msg-body");
    let box = null;
    for (let i = 0; i < wrap.children.length; i += 1) {
      if (wrap.children[i].classList && wrap.children[i].classList.contains("-agent-process")) {
        box = wrap.children[i];
        break;
      }
    }
    if (!box) {
      box = document.createElement("div");
      box.className = "-agent-process";
      if (body) wrap.insertBefore(box, body); else wrap.appendChild(box);
    }
    return box;
  }

  /** 把一帧 `process_delta` 交给当前助手记录与 DOM：新增行 append；同 `id` 的结果行**就地**更新。
   *  **本步思考的收尾点**（2026-09-22）：`step` 行到达即把当前那段"实时思考"冻结成 `done`，并用后端
   *  给的**权威全文**覆盖增量拼接的结果（同一份文本，避免边界处少一片/多一片）⇒ 下一片增量会**另开
   *  一段**（`openThinkRow()`）⇒ 一段思考后面跟它那一步的工具行。 */
  function applyProcessDelta(rows) {
    const rec = currentAssistant();
    if (!rec || !Array.isArray(rows) || !rows.length) return;
    if (!Array.isArray(rec.process)) rec.process = [];
    const wrap = streamingEl && streamingEl.parentElement;
    let box = null;
    rows.forEach(function (row) {
      if (!row || typeof row !== "object") return;
      if (row.kind === "step" && typeof row.reasoning === "string" && row.reasoning.trim()) {
        const prev = rec.process[rec.process.length - 1];
        if (prev && prev.kind === "think" && prev.state === "live") {
          prev.text = row.reasoning;
          prev.state = "done";
          if (wrap) updateThinkRowEl(lastThinkRowEl(wrap), prev);
        } else {
          // 该步没有实时增量（例如回放灌进来的过程行）⇒ 补一段，别丢这一步的思考
          const think = { kind: "think", text: row.reasoning, state: "done", iteration: row.iteration || 0 };
          rec.process.push(think);
          if (wrap) processBox(wrap).appendChild(thinkEl(row.reasoning, false));
        }
      }
      rec.process.push(row);
      // `step` 行不单独出节点：生成期间正文本身就在流式渲染（回合结束后才折进过程区）
      if (!wrap || row.kind !== "tool") return;
      box = box || processBox(wrap);
      const id = String(row.id || "");
      let line = null;
      if (id) {
        const nodes = box.querySelectorAll(".-agent-tool");
        for (let i = 0; i < nodes.length; i += 1) {
          if (nodes[i].getAttribute("data-tool-id") === id) { line = nodes[i]; break; }
        }
      }
      if (line) updateToolRowEl(line, row);
      else box.appendChild(toolRowEl(row));
    });
    scrollToBottom();
  }

  /** 渲染一个回合的过程内容（重绘**幂等**）：**按步的思考行 + 过程行**；compact 档在**构成最终
   *  答复**时整块收进折叠容器、气泡顶部给计数摘要按钮（真实 `<button>` + `aria-expanded`，按轮记忆展开态）。 */
  function renderProcessInto(wrap, rec) {
    if (!wrap || !rec || rec.role !== "assistant") return;
    const body = wrap.querySelector(".-agent-msg-body");
    Array.prototype.slice.call(wrap.querySelectorAll(".-agent-process, .-agent-process-fold")).forEach(function (node) {
      node.remove();
    });
    let rows = procRows(rec);
    if (!rows.length) rows = synthesizeRows(rec);
    rows = mergeToolRows(rows); // 同 id 的调用 / 结果两行合成一行（摘要取调用那行、状态取结果那行）
    rows = withThinkRows(rows, rec); // **按步**插思考行（最终答复那一步的思考排最后）
    if (!rows.length) return;
    const nodes = [processRowsEl(rows)];
    if (transcriptMode() !== "compact" || !processFoldable(rec, rows)) {
      // normal 档 / 不是最终答复：过程**全部可见**（不渲染摘要行）
      const frag = document.createDocumentFragment();
      nodes.forEach(function (node) { frag.appendChild(node); });
      if (body) wrap.insertBefore(frag, body); else wrap.appendChild(frag);
      return;
    }
    const box = document.createElement("div");
    box.className = "-agent-process-fold";
    const open = rec.processOpen === true;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "-agent-act -agent-process-toggle";
    btn.title = T("agent.process.toggleTitle");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.textContent = processSummaryText(rows);
    const inner = document.createElement("div");
    inner.className = "-agent-process-fold-body";
    inner.hidden = !open;
    nodes.forEach(function (node) { inner.appendChild(node); });
    btn.addEventListener("click", function () {
      const next = inner.hidden; // 当前收起 ⇒ 这次点击的意图是展开
      inner.hidden = !next;
      rec.processOpen = next;
      btn.setAttribute("aria-expanded", next ? "true" : "false");
      box.classList.toggle("-agent-process-fold--open", next);
    });
    box.classList.toggle("-agent-process-fold--open", open);
    box.appendChild(btn);
    box.appendChild(inner);
    if (body) wrap.insertBefore(box, body); else wrap.appendChild(box);
  }

  /** 定稿：判定「末步是否构成最终答复」（compact 档据此折叠），并**摘掉**末条最终答复 `step` 行
   *  （= 它已作为气泡正文渲染；摘掉后 `rec.process` 与后端回放记录的形状一致）。 */
  const baseFinalizeForProcess = finalizeMessage;
  finalizeMessage = function (result) {
    const rec = currentAssistant();
    if (rec) {
      const rows = procRows(rec);
      rec.processFinal = rows.length
        ? finalAnswerFromRows(rows)
        : !!String((result && result.answer) || "").trim() && !(result && result.status === "error");
      if (Array.isArray(rec.process)) {
        const last = rec.process[rec.process.length - 1];
        if (last && last.kind === "step" && finalAnswerFromRows([last])) rec.process = rec.process.slice(0, -1);
      }
    }
    return baseFinalizeForProcess.apply(null, arguments);
  };

  // 每轮提问重置过程游标（基座 `ask()` 的 job 游标是每轮新建，过程游标同口径；不重置会漏行/重放）。
  const baseAskForProcess = ask;
  ask = function () {
    processCursor = 0;
    return baseAskForProcess.apply(null, arguments);
  };

  // ── 设置项：对话显示 Normal / Compact（`transcript_mode`）────────────────────────

  //: 白名单（与后端 `llm/config.py` 的 `transcript_mode` 一致；发别的值后端报 `ConfigError`）。
  const TRANSCRIPT_CHOICES = ["normal", "compact"];
  const TRANSCRIPT_KEYS = { normal: "agent.settings.transcriptNormal", compact: "agent.settings.transcriptCompact" };

  /** 重填 `<select id="agent-transcript">` 的选项（含语言切换后的文案）并对齐当前值。 */
  function syncTranscriptSelect() {
    const sel = $("#agent-transcript");
    if (!sel) return;
    sel.innerHTML = "";
    TRANSCRIPT_CHOICES.forEach(function (value) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = T(TRANSCRIPT_KEYS[value]);
      sel.appendChild(opt);
    });
    sel.value = transcriptMode();
  }

  /** 选中即保存（与 `#agent-refresh` 同套路）：写 `transcript_mode` 并**立即重绘**（折叠态随之改变）。 */
  async function saveTranscriptMode(value) {
    const mode = String(value || "");
    if (TRANSCRIPT_CHOICES.indexOf(mode) === -1) {
      syncTranscriptSelect(); // 非法取值：回滚显示
      return;
    }
    let res;
    try {
      res = await call("agent_save_config", { transcript_mode: mode });
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok") {
      showFlashError(T("agent.settings.saveFailed"), errorDetail(res) || errorText(res));
      syncTranscriptSelect();
      return;
    }
    cfg = res;
    applyConfigToForm(); // 内含 syncTranscriptSelect
    renderMessages(); // 立即生效：按新档重绘（折叠 / 展开随之改变）
  }

  // 表单回填 / 配置落定后同步选择框（`refreshConfig` / `saveConfig` / 语言切换都经此）。
  const baseApplyConfigToFormForTranscript = applyConfigToForm;
  applyConfigToForm = function () {
    const out = baseApplyConfigToFormForTranscript.apply(null, arguments);
    syncTranscriptSelect();
    return out;
  };

  // 装配：绑选择框 + 首帧对齐（与基座同判据：页面未登记停靠栏则整体不介入）。
  const baseInitForTranscript = init;
  init = function () {
    const out = baseInitForTranscript.apply(null, arguments);
    if (!$("#-agent-dock")) return out;
    const sel = $("#agent-transcript");
    if (sel) sel.addEventListener("change", () => saveTranscriptMode(sel.value));
    syncTranscriptSelect();
    return out;
  };

  // ── 助手气泡里的**公式**（人 2026-09-21：「agent 回复的内容公式没有被渲染，它的渲染不是采用和
  //    memoria 一样的吗」）────────────────────────────────────────────────────────────────
  // 现状与缺口：气泡只走 `marked.parse()`（`renderAssistantBody()`），**没有**预览那条"公式"管线 ⇒
  //   `$…$` / `$$…$$` 原样留在文本里。而 MathJax 的**全局配置本来就认这两个定界符**
  //   （`index.html:24-33` 的 `inlineMath` / `displayMath`），**且 `skipHtmlTags` 已排除 `pre`/`code`**
  //   ⇒ 缺的只是"归一化 + 排版"两步。这里两步都**复用预览那一份实现**（不复制第二套规则）：
  //   ① 归一化 = `MemoriaMathNormalize.normalize()`（`markdown-preview.js::normalizeBody()` 用的同一个；
  //      顺带把"没写定界符的旧式公式"按同一标准收进 `$$…$$`）；
  //   ② 排版 = `MemoriaMarkdownPreview.initMathJax()`（同一个 MathJax 实例 / 同一份配置）。
  // 为什么**防抖 300ms**：流式期间每帧都会重渲染正文（250ms 轮询）—— 每帧都排版会把 MathJax 拖死；
  //   防抖 + `isConnected` 守卫 ⇒ 只在"这一帧停下来之后"排一次，节点已被重建则直接跳过。
  // 为什么在**净化之后**排：`sanitizeHtmlInto()` 会剥掉所有未知标签与属性（模型输出不受信），
  //   而 MathJax 生成的 `<mjx-container>` 是它自己的产物 ⇒ 必须排在净化之后（否则会被剥掉）。
  // 落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  // ─────────────────────────────────────────────────────────────────────────────────────────

  const AGENT_MATH_DEBOUNCE_MS = 300;
  const agentMathTimers = new WeakMap();

  /** 交给 `marked` 之前先把公式归一化（取不到归一化模块 / 抛错 ⇒ 原样返回，绝不吞正文）。 */
  function agentMathSource(text) {
    const src = String(text == null ? "" : text);
    const norm = typeof window !== "undefined" ? window.MemoriaMathNormalize : null;
    if (!norm || typeof norm.normalize !== "function") return src;
    try {
      return norm.normalize(src);
    } catch (e) {
      console.warn("agent-math-normalize:", e);
      return src;
    }
  }

  /** 给一个**已净化**的气泡正文排一次公式（防抖、fail-open：拿不到 MathJax 就保持源码文本）。 */
  function typesetAgentMath(el) {
    if (!el) return;
    const preview = typeof window !== "undefined" ? window.MemoriaMarkdownPreview : null;
    if (!preview || typeof preview.initMathJax !== "function") return;
    const timer = agentMathTimers.get(el);
    if (timer) clearTimeout(timer);
    agentMathTimers.set(
      el,
      setTimeout(function () {
        agentMathTimers.delete(el);
        if (!el.isConnected) return; // 已被整串重绘换掉 ⇒ 别再排版一个游离节点
        Promise.resolve(preview.initMathJax())
          .then(function () {
            if (window.MathJax?.typesetClear) window.MathJax.typesetClear([el]);
            if (window.MathJax?.typesetPromise) return window.MathJax.typesetPromise([el]);
            return null;
          })
          .catch(function (e) {
            console.warn("agent-math:", e);
          });
      }, AGENT_MATH_DEBOUNCE_MS)
    );
  }

  /** 交给 `marked` 的完整管线（与预览同源的**前两步**）：① 公式归一化；② 库内图片路径改写。
   *  `rewriteLocalImagePaths()` 是 `markdown-preview.js` 的导出（同一份实现、同一个「库根」）——
   *  它把 `.memoria/images/x.png` 这类**库内相对路径**改写成 `/files/...`，远程 / `data:` 一律不动
   *  （随后被 `appendLocalImage()` 丢掉）。人 2026-09-21：「img 怎么会被丢，都是交给 memoria 渲染管线
   *  渲染的，只要有本地图片文件就会渲染出来」—— 对：库内图片本来就该走同一通路。 */
  function agentRichHtml(src) {
    const html = window.marked.parse(agentMathSource(src), { gfm: true, breaks: true });
    const preview = window.MemoriaMarkdownPreview;
    try {
      if (preview && typeof preview.rewriteLocalImagePaths === "function") {
        return preview.rewriteLocalImagePaths(html);
      }
    } catch (e) {
      console.warn("agent-img-rewrite:", e);
    }
    return html;
  }

  /** 是不是**库内**图片（改写后的 `/files/...`）；其它（`http(s)` / `data:` / `javascript:` / 空）一律拒。
   *  纯函数 ⇒ 可被单测直接跑（安全边界就写在它一处）。 */
  function isLocalImageSrc(src) {
    return /^\/files\//.test(String(src == null ? "" : src));
  }

  /** 净化期放行**库内**图片：只搬运 `src`（必须本地）+ `alt`/`title`，其它属性（`on*` 等）一律不抄。 */
  function appendLocalImage(target, node) {
    const src = String((node && node.getAttribute && node.getAttribute("src")) || "");
    if (!isLocalImageSrc(src)) return; // 远程 / data: / javascript: ⇒ 丢（不静默放行）
    const img = document.createElement("img");
    img.setAttribute("src", src);
    const alt = node.getAttribute("alt");
    if (alt) img.setAttribute("alt", alt);
    const title = node.getAttribute("title");
    if (title) img.setAttribute("title", title);
    img.setAttribute("loading", "lazy");
    target.appendChild(img);
  }

  /** 给气泡里的库内图片挂上预览那套**灯箱**（双击放大）；同一个实现，不另写一套。 */
  function attachAgentImages(el) {
    const preview = window.MemoriaMarkdownPreview;
    if (!preview || typeof preview.attachImageLightbox !== "function") return;
    try {
      preview.attachImageLightbox(el);
    } catch (e) {
      console.warn("agent-img-lightbox:", e);
    }
  }

  // ── 输入框：空框时 ↑/↓ 翻「发过的内容」（人 2026-09-21：「输入框空的时候按上下键要可以切换“发过的内容”」）
  //   口径：① **只有空输入框**才翻历史（有草稿就交给浏览器默认的上下移动，绝不吞掉人的编辑）；
  //   ② ↑ 往旧、↓ 往新；已到最旧停在最旧，越过最新 ⇒ 回到空框并退出历史模式；③ 落点光标在**末尾**；
  //   ④ 手动敲字或 `ask()` 之后游标复位（否则刚发完再按 ↑ 会从"倒数第二条"开始，与直觉不符）。
  //   落点纪律：整块追加在 IIFE 末尾 ⇒ 上方所有 `<文件>:<行号>` 锚点零漂移。
  let composerHistCursor = null; // null = 不在历史模式；数字 = 在 `sentTexts()` 里的下标

  /** 本会话（含载入的历史会话）里"人发过的内容"，按发送先后。 */
  function sentTexts() {
    return messages
      .filter(function (rec) {
        return rec && rec.role === "user";
      })
      .map(function (rec) {
        return String(rec.text == null ? "" : rec.text);
      })
      .filter(function (t) {
        return t.trim() !== "";
      });
  }

  /** 纯函数：算翻一步之后的历史下标（`null` = 退出历史模式回到空框）。`dir` = -1 旧 / +1 新。 */
  function composerHistNext(cursor, dir, n) {
    if (!n) return null;
    if (cursor === null || cursor < 0 || cursor >= n) return dir < 0 ? n - 1 : null; // 首次 ↑ = 最新那条
    const next = cursor + dir;
    if (next < 0) return 0; // 已到最旧：停在最旧（不退出，免得"再按一下框就空了"）
    if (next >= n) return null; // 越过最新：退出历史 ⇒ 空框
    return next;
  }

  /** 空框时翻历史；返回 true 表示"这次按键我处理了"（调用方 preventDefault）。 */
  function composerHistStep(dir) {
    const input = $("#agent-input");
    if (!input) return false;
    // 有**人打的**草稿 ⇒ 一概不动（交给浏览器默认的上下移动）。注意判据**不是"框空不空"**：
    // 历史填充进去的文本也非空，若只判空则第一次 ↑ 之后后续 ↑↓ 全被挡掉（真机 L4 实测到的一次性 bug）。
    if (String(input.value || "") !== "" && composerHistCursor === null) return false;
    const texts = sentTexts();
    const next = composerHistNext(composerHistCursor, dir, texts.length);
    if (next === null && texts.length === 0) return false;
    composerHistCursor = next;
    const text = next === null ? "" : texts[next];
    input.value = text;
    const end = text.length;
    try {
      input.setSelectionRange(end, end); // 光标落在末尾，方便接着改
    } catch (e) {
      /* 老 webview 没有 setSelectionRange：不上报、不影响取值 */
    }
    afterComposerEdit(input, end); // chip / 提及块与被替换的文本同步
    return true;
  }

  (function bindComposerHistory() {
    const input = $("#agent-input");
    if (!input) return;
    input.addEventListener("keydown", function (e) {
      if (e.isComposing || e.keyCode === 229) return; // 输入法组字中不碰（与原子块处理同一口径）
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      if (!composerHistStep(e.key === "ArrowUp" ? -1 : 1)) return;
      e.preventDefault();
    });
    input.addEventListener("input", function () {
      composerHistCursor = null; // 手动敲字 ⇒ 离开历史模式
    });
    const askBase = ask;
    ask = function () {
      composerHistCursor = null; // 发出去之后重新从最新那条开始
      return askBase.apply(this, arguments);
    };
  })();

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-22 追加：审批档位（上游 `dsh-permission-presets`）+ 逐条确认（上游 `user-approval`）
  //
  // 人：「继续移植上游」。三档的**机器键**是稳定英文（进会话事件 ⇒ 可回放、可审计），显示名走
  // i18n（后端中文名只作回退事实源）。本块**整段追加在 `return {` 之前** ⇒ 既有行号锚点零漂移。
  //
  // 四个落点：
  //   ① 输入区档位选择器 `#agent-permission`（挂到 `.-agent-composer-actions`，与 `plan-confirm.js`
  //      的计划入口同一扩容点，无 HTML 改动）——切**当前会话**的档（落 `permission/preset` 事件）；
  //   ② 设置面板「新会话审批档」`#agent-permission-default`（HTML 已就位）——写
  //      `config/agent.json: permission.<agent>`，只影响**以后新建**的会话；
  //   ③ 轮询载荷 `pending_approvals` ⇒ 逐条确认卡（允许一次 / 拒绝），回填走 `agent_approval_answer`；
  //   ④ 会话改变（首轮结束 / 换库 / 清空 / 整串重绘）时重读或重填档位面。
  //
  // 兜底口径：**卡只在"待批"期间可点**；不在待批帧里的卡一律标「已处理」并禁用按钮（面板与后端
  // 各自收敛，绝不出现"点了没反应"）。派生态 `custom` 只展示、不可选（对齐上游）。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 档位机器键 → i18n 键后缀（`agent.permission.<后缀>.name` / `.desc`）。 */
  const PERMISSION_KEYS = {
    "manual-approval": "manual",
    "auto-approval": "auto",
    "all-access": "all",
    custom: "custom",
  };
  //: 派生态（当前旋钮不匹配任何档）：**可展示、不可作切换目标**。
  const PERMISSION_CUSTOM = "custom";
  //: 逐条确认卡的两个按钮 → 后端封闭词汇（`unavailable` 不是人能点的裁决）。
  const APPROVAL_ACT = { allow: "allowed-once", deny: "rejected" };

  let permOptions = []; // 后端 `options[]`（含派生态），每次读档位面时整体替换
  let permCurrent = "";
  let permDefault = "";
  let permAgent = "main"; // 档位归属的 agent（当前只有主 agent；见 permission_presets.MAIN_AGENT）
  //: 待批卡：**键 = call id + created_at**（不是 call id 一个键，理由见 `approvalCardKey()`）。
  const approvalCards = {};

  function permKey(value) {
    return PERMISSION_KEYS[String(value == null ? "" : value)] || "";
  }

  /** 档位文案：优先本地语言；缺键时回退后端给的中文名/描述。 */
  function permText(value, field, fallback) {
    const key = permKey(value);
    if (!key) return String(fallback == null ? (value == null ? "" : value) : fallback);
    const full = "agent.permission." + key + "." + field;
    const text = T(full);
    if (text && text !== full) return text;
    return String(fallback == null ? "" : fallback);
  }

  /** 重填一个档位选择器；派生态作为**禁用项**保留（否则"当前值"会显示成别的档 ⇒ 说谎）。 */
  function fillPermissionSelect(sel, current) {
    if (!sel) return;
    sel.innerHTML = "";
    permOptions.forEach(function (opt) {
      if (!opt || !opt.value) return;
      const value = String(opt.value);
      const el = document.createElement("option");
      el.value = value;
      el.textContent = permText(value, "name", opt.name);
      const tip = permText(value, "desc", opt.description);
      if (tip) el.title = tip;
      if (value === PERMISSION_CUSTOM) el.disabled = true;
      sel.appendChild(el);
    });
    const wanted = String(current == null ? "" : current);
    if (wanted && sel.querySelector('option[value="' + wanted.replace(/"/g, '\\"') + '"]')) sel.value = wanted;
    else if (!sel.value && sel.options.length) sel.selectedIndex = 0;
  }

  /** 后端档位面 → 两个选择器 + 缓存（一次 RPC 同时喂"当前会话"与"新会话默认"）。 */
  function paintPermission(st) {
    if (!st || st.status !== "ok") return false;
    permOptions = Array.isArray(st.options) ? st.options : [];
    permCurrent = String(st.current || "");
    permDefault = String(st.default || permCurrent);
    permAgent = String(st.agent || permAgent);
    fillPermissionSelect($("#agent-permission"), permCurrent);
    fillPermissionSelect($("#agent-permission-default"), permDefault);
    return true;
  }

  /** 读档位面（库/会话都可有可无：没有会话时 `current` = 该 agent 的默认档）。 */
  async function refreshPermission() {
    let res;
    try {
      res = await call("agent_permission_get", state.kbPath || null, sessionId || null);
    } catch (e) {
      return; // 档位面读失败保持上一次显示：它不该打断对话
    }
    paintPermission(res);
  }

  /** 把选择器挂进输入区（幂等；与计划入口共用 `.-agent-composer-actions`）。 */
  function mountPermissionSelect() {
    const actions = document.querySelector(".-agent-composer-actions");
    if (!actions) return false;
    if (actions.querySelector("#agent-permission")) return true;
    const sel = document.createElement("select");
    sel.id = "agent-permission";
    sel.className = "-agent-permission";
    sel.title = T("agent.permission.sessionTitle");
    sel.addEventListener("change", function () {
      const value = String(sel.value || "");
      if (!value || value === PERMISSION_CUSTOM) return;
      saveSessionPermission(value);
    });
    actions.insertBefore(sel, actions.firstChild);
    return true;
  }

  /** 设置面板那一个（`#agent-permission-default`）只绑一次 change。 */
  function bindPermissionDefault() {
    const sel = $("#agent-permission-default");
    if (!sel || sel.__permBound) return;
    sel.__permBound = true;
    sel.addEventListener("change", function () {
      saveDefaultPermission(String(sel.value || ""));
    });
  }

  /** 切**当前会话**的档（落 `permission/preset` + 变化的 `approval/policy` 事件）。 */
  async function saveSessionPermission(value) {
    if (!sessionId) {
      showFlashError(T("agent.permission.needSession"), "");
      refreshPermission(); // 回滚显示
      return;
    }
    let res;
    try {
      res = await call("agent_permission_set_session", value, state.kbPath || null, sessionId);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok") {
      showFlashError(T("agent.permission.failed"), errorDetail(res) || errorText(res));
      refreshPermission();
      return;
    }
    paintPermission(res);
    showFlashInfo(T("agent.permission.switched", { name: permText(value, "name", value) }));
  }

  /** 改该 agent 的**默认档**（新会话用；当前会话不受影响）。 */
  async function saveDefaultPermission(value) {
    let res;
    try {
      res = await call("agent_permission_set_default", value, permAgent);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok") {
      showFlashError(T("agent.permission.failed"), errorDetail(res) || errorText(res));
      refreshPermission();
      return;
    }
    paintPermission(res);
    showFlashInfo(T("agent.permission.defaultSaved", { name: permText(value, "name", value) }));
  }

  // —— 逐条确认卡（`pending_approvals` → 允许一次 / 拒绝）——

  function approvalBox() {
    const box = $("#agent-messages");
    return box && box.isConnected ? box : null;
  }

  /** 卡片随对话流一起被重绘/清空 ⇒ 丢掉已脱离文档的元素（否则会一直"待批"下去）。 */
  function pruneApprovalCards() {
    Object.keys(approvalCards).forEach(function (key) {
      const el = approvalCards[key];
      if (!el || !el.isConnected) delete approvalCards[key];
    });
  }

  /** 一张待批卡的键：**call id + created_at**。
   *
   *  为什么不用 call id 单键（L4 实测到的事故）：call id 只保证**一轮内**唯一，网关/上游会跨轮
   *  复用同一个 id（脚本化 provider 就每轮发 `call-l4-1`）。若同 id 的**新**待批项因"表里已有"
   *  而被跳过，面板就不会出卡 ⇒ 没人应答 ⇒ 挂起 120s 后被判 `unavailable` 拒绝：**写入静默死掉**。
   *  `created_at` 由后端按待批项生成（每条唯一）⇒ 同一条跨帧反复出现只建一张卡，新的待批项必出新卡。 */
  function approvalCardKey(row) {
    const id = String(row && row.id ? row.id : "");
    const at = String(row && row.created_at ? row.created_at : "");
    return id + "@" + at;
  }

  function setApprovalState(el, text) {
    const state = el && el.querySelector(".-agent-approve-state");
    if (state) state.textContent = String(text || "");
  }

  /** 该卡到此为止：禁用两个按钮并给出终态文案（**卡保留**当过程痕迹）。
   *
   *  已有终态就**不覆盖**：`applyPendingApprovals()` 每帧都会对"不再待批"的卡补一次通用
   *  「已处理」，若不过滤就会把点按钮时写下的「已允许一次 / 已拒绝」盖掉（L4 实测）。 */
  function markApprovalCardDone(key, label) {
    const el = approvalCards[String(key == null ? "" : key)];
    if (!el) return;
    if (el.classList.contains("-agent-approve--done")) return;
    el.classList.add("-agent-approve--done");
    setApprovalState(el, label || T("agent.approve.done"));
    Array.prototype.forEach.call(el.querySelectorAll("button"), function (btn) {
      btn.disabled = true;
    });
  }

  function approvalIntent(row) {
    const args = row && row.arguments && typeof row.arguments === "object" ? row.arguments : {};
    const intent = String(args.intent == null ? "" : args.intent).trim();
    return intent || T("agent.approve.noIntent");
  }

  function approvalOpCount(row) {
    const args = row && row.arguments && typeof row.arguments === "object" ? row.arguments : {};
    return Array.isArray(args.ops) ? args.ops.length : 0;
  }

  function approvalCardEl(row) {
    const el = document.createElement("div");
    const key = approvalCardKey(row);
    el.className = "-agent-msg -agent-msg--assistant -agent-approve-msg";
    el.setAttribute("data-approval-id", String(row.id || ""));
    el.setAttribute("data-approval-key", key);
    const ops = approvalOpCount(row);
    el.innerHTML =
      '<span class="-agent-msg-role">' +
      esc(T("agent.role.assistant")) +
      "</span>" +
      '<div class="-agent-approve">' +
      '<div class="-agent-approve-title">' +
      esc(T("agent.approve.title", { tool: String(row.tool || "") })) +
      "</div>" +
      '<div class="-agent-approve-intent">' +
      esc(approvalIntent(row)) +
      "</div>" +
      (ops ? '<div class="-agent-approve-meta -muted">' + esc(T("agent.approve.ops", { n: ops })) + "</div>" : "") +
      '<div class="plan-actions">' +
      '<button type="button" class="-btn primary -btn--sm" data-act="allow">' +
      esc(T("agent.approve.allow")) +
      "</button>" +
      '<button type="button" class="-btn -btn--sm" data-act="deny">' +
      esc(T("agent.approve.deny")) +
      "</button>" +
      '<span class="-agent-approve-state -muted"></span>' +
      "</div></div>";
    const allow = el.querySelector('[data-act="allow"]');
    const deny = el.querySelector('[data-act="deny"]');
    if (allow)
      allow.addEventListener("click", function () {
        answerApproval(key, "allow");
      });
    if (deny)
      deny.addEventListener("click", function () {
        answerApproval(key, "deny");
      });
    return el;
  }

  function upsertApprovalCard(row) {
    const key = approvalCardKey(row);
    if (!key || approvalCards[key]) return; // 同一条待批项跨帧反复出现 ⇒ 只建一张
    const box = approvalBox();
    if (!box) return;
    const empty = box.querySelector(".-agent-empty");
    if (empty) empty.remove();
    const el = approvalCardEl(row);
    box.appendChild(el);
    approvalCards[key] = el;
    scrollToBottom(true); // 要人点确认的卡必须进视野（唯一"强制滚底"的新增场合）
  }

  /** 一帧 `pending_approvals`：新增的建卡；不再待批的标「已处理」（后端已收敛，这里只同步显示）。 */
  function applyPendingApprovals(rows) {
    const list = Array.isArray(rows) ? rows : [];
    pruneApprovalCards();
    const live = {};
    list.forEach(function (row) {
      if (row) live[approvalCardKey(row)] = true;
    });
    Object.keys(approvalCards).forEach(function (key) {
      if (!live[key]) markApprovalCardDone(key, T("agent.approve.done"));
    });
    list.forEach(upsertApprovalCard);
  }

  /** 回填一次裁决（成功即禁用该卡；失败恢复可点，绝不留"点了没反应"）。 */
  async function answerApproval(key, act) {
    const outcome = APPROVAL_ACT[String(act || "")] || "";
    if (!outcome) return;
    const el = approvalCards[String(key == null ? "" : key)];
    const callId = String((el && el.getAttribute("data-approval-id")) || "");
    if (!callId) return; // 卡片已随对话流被清掉：没有可回填的对象
    setApprovalState(el, T("agent.approve.sending"));
    let res;
    try {
      res = await call("agent_approval_answer", callId, outcome, state.kbPath || null);
    } catch (e) {
      res = { status: "error", message: String((e && e.message) || e) };
    }
    if (!res || res.status !== "ok" || !res.answered) {
      showFlashError(T("agent.approve.failed"), errorDetail(res) || errorText(res));
      setApprovalState(el, "");
      return;
    }
    markApprovalCardDone(key, act === "allow" ? T("agent.approve.allowed") : T("agent.approve.denied"));
  }

  (function bindPermissionFacade() {
    const facade = A();
    const base = facade && facade.call;
    if (typeof base !== "function") return;
    facade.call = function (fnName) {
      const pending = base.apply(this, arguments);
      if (fnName !== "agent_ask_poll") return pending;
      return Promise.resolve(pending).then(function (res) {
        if (res && res.pending_approvals) applyPendingApprovals(res.pending_approvals);
        return res;
      });
    };
  })();

  (function bindPermissionHooks() {
    const initBase = init;
    init = function () {
      const out = initBase.apply(this, arguments);
      mountPermissionSelect();
      bindPermissionDefault();
      refreshPermission();
      return out;
    };
    const renderBase = renderMessages; // 语言切换 / 整串重绘后按缓存重填两个选择器（纯 DOM，无 RPC）
    renderMessages = function () {
      const out = renderBase.apply(this, arguments);
      if (permOptions.length) {
        fillPermissionSelect($("#agent-permission"), permCurrent);
        fillPermissionSelect($("#agent-permission-default"), permDefault);
      }
      return out;
    };
    const pollBase = poll; // 回合收尾：会话 id（可能刚新建）已写回 ⇒ 重读档位面
    poll = function () {
      return Promise.resolve(pollBase.apply(this, arguments)).then(function (out) {
        refreshPermission();
        return out;
      });
    };
    const clearBase = clear;
    clear = function () {
      const out = clearBase.apply(this, arguments);
      refreshPermission();
      return out;
    };
    const kbBase = onKbChanged;
    onKbChanged = function () {
      const out = kbBase.apply(this, arguments);
      refreshPermission();
      return out;
    };
  })();

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-22 追加（人报障三条）：Ctrl+Enter 不换行 / 输入框文字与光标错位几格 / 生成中无法上翻
  //
  // ① **Ctrl+Enter 真机不换行**：Windows Chromium 的 textarea 对 Ctrl+Enter **没有**默认动作
  //    ⇒ 过去那条"不 preventDefault、交给浏览器默认"的注释是错的，实际什么都不会发生。
  //    改为**自己插**：`composerInsertLineBreak()` 在光标处插入 `\n`、把光标移到其后，并派发
  //    `input`（镜像层同步、历史游标复位、chip 高亮都挂在既有 `input` 监听上，一并跑）。
  // ② **输入框内文字与光标错位几格**：镜像层原先用 `offsetWidth/offsetHeight` 定尺寸，而 textarea
  //    一旦出现**滚动条**（内容超过 `max-height: 10rem`），可用文本宽度就窄了一个滚动条（≈17px）
  //    ⇒ 镜像的换行点与 textarea 不一致，光标落在可见文字右侧几格。改用 `clientWidth/clientHeight`
  //    （已排除滚动条）**加上两侧边框宽** ⇒ 与 textarea 的**内容盒**逐像素一致。
  // ③ **生成中无法向上滚动**：每个文本分片 / 过程行都无条件 `scrollTop = scrollHeight`，把用户往回
  //    翻的动作每一帧又拽回底部。改为**粘底**语义：`stickToBottom` 只由**位置上移**（= 用户上翻）关掉、
  //    由"回到近底"打开（见 `stickAfterScroll()`），非强制调用只在粘底时跟随；`scrollToBottom(true)`
  //    只留给"必须看到"的场合（用户发问、整串重绘、确认卡进场），且会**重挂**粘底。
  //    为什么不用"离底 < N px"直接判"用户上翻了"：滚动事件是**异步**派发的，事件到达时内容可能又长
  //    了一截 —— L4 实测：发问后"生成中"尾行 ≈50px 落地，距离 51 > 48 ⇒ 把"一直在底部"的人误判成
  //    "上翻了" ⇒ 整轮回答都不再跟随（含用户根本没碰滚轮的情况）。
  //
  // 整块**追加在 `return {` 之前** ⇒ 既有行号锚点零漂移（①②③ 动到的既有行全部是**等量改写**）。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 「离底」容差（px）：滚动后离底小于它就算"用户还在看底部" ⇒ 恢复自动跟随。 */
  const STICK_SLOP_PX = 48;

  //: 粘底开关：true = 新内容自动跟随到底；false = 用户正在往上翻，**别抢**。
  let stickToBottom = true;
  //: 上一次观察到的滚动位置（`stickAfterScroll()` 用它判"位置上移"）。
  let lastBoxScrollTop = 0;

  /** 纯函数版粘底判据（只吃三个数，便于 node 实跑）。 */
  function boxAtBottom(scrollHeight, scrollTop, clientHeight) {
    return Number(scrollHeight) - Number(scrollTop) - Number(clientHeight) <= STICK_SLOP_PX;
  }

  function messageBoxAtBottom(box) {
    return boxAtBottom(box.scrollHeight, box.scrollTop, box.clientHeight);
  }

  /** 一次滚动事件 → 新的粘底状态（纯函数，`[新状态, 新 lastTop]`，便于 node 实跑）。
   *
   *  判据刻意**不**是"离底距离"：滚动事件是**异步派发**的，事件到达时内容可能又长了一截
   *  （L4 实测：发问后"生成中"尾行 ≈50px 落地 ⇒ 距离 51 > 48 ⇒ 把"一直在底部"的人误判成
   *  "上翻了" ⇒ 整轮不再跟随）。只有**位置上移**才算"用户要读历史"：
   *  - `top` 明显小于上次 ⇒ 用户上翻 ⇒ 停止跟随；
   *  - 否则若已在近底 ⇒ 恢复跟随（含程序化滚底、用户拖回底部）；
   *  - 其余（位置下移但还没到底、内容变长引起的同一位置）⇒ **保持原状态**。
   */
  function stickAfterScroll(wasStick, lastTop, top, atBottom) {
    if (top < Number(lastTop) - 1) return [false, top];
    if (atBottom) return [true, top];
    return [wasStick, top];
  }

  /** 粘底语义的**唯一**落点：`force` = 必须看到的场合（重挂粘底并滚到底），否则只在粘底时跟随。 */
  function messageBoxScrollTo(box, force) {
    if (force) stickToBottom = true;
    if (force || stickToBottom) box.scrollTop = box.scrollHeight;
  }

  (function bindStickyScroll() {
    const box = $("#agent-messages");
    if (!box) return;
    lastBoxScrollTop = box.scrollTop;
    box.addEventListener("scroll", function () {
      const top = box.scrollTop;
      const next = stickAfterScroll(stickToBottom, lastBoxScrollTop, top, messageBoxAtBottom(box));
      stickToBottom = next[0];
      lastBoxScrollTop = next[1];
    });
  })();

  /** 输入框 → 光标处插入换行（Ctrl/Cmd+Enter；不依赖浏览器默认动作）。 */
  function composerInsertLineBreak(input) {
    if (!input) return false;
    const value = String(input.value || "");
    const from = Number.isInteger(input.selectionStart) ? input.selectionStart : value.length;
    const to = Number.isInteger(input.selectionEnd) ? input.selectionEnd : from;
    input.value = value.slice(0, from) + "\n" + value.slice(to);
    try {
      input.setSelectionRange(from + 1, from + 1);
    } catch (e) { /* 非文本控件忽略 */ }
    try {
      input.dispatchEvent(new Event("input", { bubbles: true })); // 镜像同步 / 历史游标复位随既有监听
    } catch (e) { /* 无 Event 构造器的环境忽略 */ }
    return true;
  }

  /** 输入框 Enter 语义：返回 true = 本次事件已处理（或该放行给浏览器），false = 该发送。 */
  function composerEnterKey(e, input) {
    if (e.key !== "Enter" || e.isComposing) return true; // 输入法组字中不碰（与原子块处理同一口径）
    if (e.ctrlKey || e.metaKey) {
      if (e.altKey || e.shiftKey) return true;
      e.preventDefault(); // 我们自己插，别让浏览器再动一次
      composerInsertLineBreak(input);
      return true;
    }
    if (e.shiftKey || e.altKey) return true; // Shift+Enter：交给浏览器默认（原生插换行）
    return false; // 裸 Enter = 发送
  }

  /** 镜像层尺寸：对齐 textarea 的**内容盒**（`clientWidth/Height` 已排除滚动条；再加两侧边框）。 */
  function composerMirrorWidth(input) {
    const cs = window.getComputedStyle ? window.getComputedStyle(input) : null;
    const border = cs ? (parseFloat(cs.borderLeftWidth) || 0) + (parseFloat(cs.borderRightWidth) || 0) : 1;
    return input.clientWidth + border;
  }

  function composerMirrorHeight(input) {
    const cs = window.getComputedStyle ? window.getComputedStyle(input) : null;
    const border = cs ? (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0) : 1;
    return input.clientHeight + border;
  }

  // ══════════════════════════════════════════════════════════════════════════════
  // 2026-09-22 追加：回复末尾那一行 =「用量 + 复制」同一行
  //   人：「对话底部除了显示用量信息还需要复制按钮」。原先用量文本挂在**气泡内**（`.-agent-msg` 末尾），
  //   而复制是气泡外那一行（`.-agent-msg-actions`）里的**纯图标**（`opacity .55`、文案只在悬停时给）
  //   ⇒ 人根本没把它当按钮看。现在两件事合并到**同一行**：用量在前、复制（图标 + 「复制」二字）在后，
  //   且按钮常显。整块追加在 `return {` 之前 ⇒ 既有行号锚点零漂移（`renderTurnUsage()` 只做**等量改写**）。
  // ══════════════════════════════════════════════════════════════════════════════

  /** 一个助手回合的**底部行**宿主：气泡外面那一行 `.-agent-msg-actions`（放「复制」）。
   *  取不到（异常 DOM / 尚未包进 `.-agent-turn`）时退化为消息元素本身 —— **绝不丢用量信息**。 */
  function usageRowHost(wrap) {
    const turn = wrap && wrap.closest ? wrap.closest(".-agent-turn") : null;
    const actions = turn ? turn.querySelector(".-agent-msg-actions") : null;
    return actions || wrap;
  }

  /** 底部行里的用量格（幂等）：没有就建一个并插在该行**最前**（复制按钮留在其后）。 */
  function usageRowEl(wrap) {
    const host = usageRowHost(wrap);
    let el = host.querySelector(".-agent-usage");
    if (!el) {
      el = document.createElement("span");
      el.className = "-agent-usage -muted";
      host.insertBefore(el, host.firstChild);
    }
    return el;
  }

  /** 「复制」按钮（图标 + 「复制」二字）；`actionsEl()` 与 `syncTurnActions()` 共用同一构造。 */
  function copyButtonEl(rec) {
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "-agent-act -agent-act--icon -agent-act--copy";
    copy.title = T("agent.copy"); // 悬停提示就一个字：复制（人：「鼠标悬浮显示复制」）
    copy.setAttribute("aria-label", T("agent.copy"));
    copy.innerHTML = COPY_ICON_SVG + '<span class="-agent-act-label">' + esc(T("agent.copy")) + "</span>";
    copy.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      copyMessageText(rec, copy); // 取 `rec.text` 的**当前值**（流式期间会变）⇒ 按钮可以早建
    });
    return copy;
  }

  /** 让某个回合的底部操作行**反映消息的当前状态**：有正文就该有「复制」，没正文就摘掉。
   *
   *  **为什么必须有它（2026-09-22 L4 抓到的真 bug）**：助手消息是 `pushMessage("assistant", "")`
   *  **空文本**建的，`actionsEl()` 那一刻按"没正文不建按钮"返回空行；终答后 `finalizeMessage()`
   *  只换气泡正文、`wrapTurn()` 又复用既有 `.-agent-turn` ⇒ **实时那一轮永远长不出复制按钮**
   *  （只有刷新页面走 `renderMessages()` 才有）。人看到的正是"底部只有用量、没有复制"。
   */
  function syncTurnActions(rec) {
    const wrap = assistantWrapFor(rec);
    if (!wrap) return;
    const host = usageRowHost(wrap);
    if (host === wrap) return; // 没有独立操作行（异常 DOM）：不往气泡里塞按钮
    const btn = host.querySelector("button.-agent-act--copy");
    const want = !!String((rec && rec.text) || "").trim();
    if (want && !btn) host.appendChild(copyButtonEl(rec));
    else if (!want && btn) btn.remove();
  }

  // 终答落定（正文已写进 `rec.text`）⇒ 补齐底部操作行。包装成链式（既有包装先跑）⇒ 不动其函数体。
  const finalizeTurnActionsBase = finalizeMessage;
  finalizeMessage = function (result) {
    const out = finalizeTurnActionsBase.apply(this, arguments);
    try {
      syncTurnActions(currentAssistant());
    } catch (e) {
      console.warn("agent-actions:", e);
    }
    return out;
  };

  // ══════════════════════════════════════════════════════════════════════════════
  // 斜杠命令（2026-09-22；上游 `interaction/commands` 的最小面，见 `services/agent/commands.py`）
  //   后端契约：整行 `/name` 且**名字已注册** ⇒ 宿主侧执行、**不进模型** ⇒ 那一轮回
  //   `stop_reason:"command"`、`answer` = 命令回文、`usage` 是空表；**未注册的名字照旧走模型**
  //   （所以 `/usr/bin`、`5/8` 这类不会被吃掉）。前端只做两件事：① 那一轮**看起来不是模型说的话**
  //   （气泡加 `-agent-msg--command`，且**没有用量、没有可复制的"回答"** —— 命令零 token、也没回答）；
  //   ② 输入 `/` 时给一行**可用命令提示**（发现面，数据来自 `agent_command_list`）。
  //   **不做** `/` 补全弹层与键盘选择（上游把它留给"capable clients"）—— 未移植，见 design §6.23 偏差表。
  //   落点纪律：整块追加在 IIFE 末尾（`return {}` 之前）、只**包装**既有函数 ⇒ 上方锚点零漂移。
  // ══════════════════════════════════════════════════════════════════════════════

  function isCommandTurn(result) {
    return !!result && String(result.stop_reason || "") === "command";
  }

  // ① 气泡标记：标记落在**消息记录**上（刷新重绘走 `messageEl()` 也保留）⇒ 不是只改一次 DOM。
  const baseMessageElForCommand = messageEl;
  messageEl = function (rec) {
    const el = baseMessageElForCommand.apply(null, arguments);
    if (el && rec && rec.command) el.classList.add("-agent-msg--command");
    return el;
  };

  // ② 终答落定：标 `command` ⇒ 摘掉用量行与复制按钮。
  //    **本块在文件末** ⇒ 这个包装是**最外层**（跑在「用量 + 复制」那两处包装**之后**）⇒ 摘除生效。
  const finalizeForCommandBase = finalizeMessage;
  finalizeMessage = function (result) {
    const out = finalizeForCommandBase.apply(this, arguments);
    if (isCommandTurn(result)) {
      try {
        const rec = currentAssistant();
        if (rec) {
          rec.command = true;
          const wrap = assistantWrapFor(rec);
          if (wrap) {
            const copy = wrap.querySelector("button.-agent-act--copy");
            if (copy) copy.remove();
            const usage = wrap.querySelector(".-agent-usage");
            if (usage) usage.remove();
          }
        }
      } catch (e) {
        console.warn("agent-command:", e);
      }
    }
    return out;
  };

  // ③ 输入 `/` 时的可用命令提示（发现面）：只列名字 + 输入提示 + 一句描述（**不可点**，纯提示）。
  let commandCatalog = null; // null = 还没拉过；[] = 拉过但为空
  function commandHintEl() {
    const composer = document.querySelector(".-agent-composer");
    if (!composer) return null;
    let el = composer.querySelector(".-agent-cmd-hint");
    if (!el) {
      el = document.createElement("div");
      el.className = "-agent-cmd-hint -muted";
      composer.appendChild(el);
    }
    return el;
  }
  async function refreshCommandHint() {
    const input = $("#agent-input");
    const el = commandHintEl();
    if (!input || !el) return;
    const value = String(input.value || "");
    if (!value.trimStart().startsWith("/")) {
      el.textContent = "";
      el.hidden = true;
      return;
    }
    if (commandCatalog === null) {
      try {
        const res = await call("agent_command_list");
        commandCatalog = res && Array.isArray(res.commands) ? res.commands : [];
      } catch (e) {
        commandCatalog = [];
      }
    }
    const typed = value.trimStart().slice(1).split(/\s/)[0].toLowerCase();
    const rows = commandCatalog
      .filter((row) => !typed || String(row.name || "").startsWith(typed))
      .map((row) => {
        const hint = row.input && row.input.hint ? " " + row.input.hint : "";
        return "/" + String(row.name || "") + hint + " — " + String(row.description || "");
      });
    if (!rows.length) {
      el.textContent = commandCatalog.length ? T("agent.command.none") : "";
      el.hidden = !commandCatalog.length;
      return;
    }
    el.textContent = rows.join("\n");
    el.hidden = false;
  }
  (function wireCommandHint() {
    const input = $("#agent-input");
    if (!input || input.dataset.cmdHintWired === "1") return;
    input.dataset.cmdHintWired = "1";
    input.addEventListener("input", function () {
      void refreshCommandHint();
    });
  })();

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
    // 写入状态栏入口（`plan-confirm.js` 调用）：告知"这次对话写了什么"，本模块渲染在顶部
    // **副标题行**（`.-agent-subhead`）——「已修改 N 个文件（可展开）+ 撤销一步 / 重做一步」。
    setWriteState: setWriteState,
  };
})();
