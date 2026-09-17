# 01 · 窗口外壳与整体布局

> **用途**：把 Memoria 桌面窗口的「外壳 + 五大区域」（窗口 chrome / 顶栏 / 左侧栏 / 文档区 / 状态栏）连同闪烁提示（flash）、弹窗层级与缩放变量，写到可据以定位实现的粒度。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[README.md](./README.md)（本套说明书的用法与维护约定）、[02-file-tree-and-nav.md](./02-file-tree-and-nav.md)（左侧栏「文件」页签的细节）、[09-settings-i18n-and-shortcuts.md](./09-settings-i18n-and-shortcuts.md)（设置四页与快捷键总表）、[../preview-formats.md](../preview-formats.md)（渲染语法权威）、[../i18n-inventory.md](../i18n-inventory.md)（文案清单）。
> **状态**：生效中，2026-09-17。

---

**证据锚约定**：`文件:行号` 以**仓库根目录**为基准。前端在 `src/memoria/ui/static/app/**`；少量外壳样式在 `src/memoria/ui/static/theme/memoria.css`（下称 `theme/memoria.css`）；窗口 chrome 的原生部分属后端，涉及处标 `src/memoria/app/**`。

## 1. 区域概览

```
#app                          index.html:47    （memoria.css:39-43 纵向 flex，高 100vh）
├── #toolbar                  index.html:48    z-index 50（memoria.css:46-60）
│   顺序：.toolbar-left:49 → .toolbar-actions:56 → spacer:83 → .toolbar-search-wrap:84
│         → spacer:94 → .toolbar-right:95
├── #main                     index.html:108   （memoria.css:248 横向 flex，flex:1）
│   ├── #-sidebar             index.html:109    （app.css:123-133）
│   │   ├── #sidebar-resizer:110 · .-sidebar-tabs-wrap:111（文件/2D/3D/对话）
│   │   ├── #sidebar-graph-group-bar:119       仅图谱页签 + 有节点时显示
│   │   └── #sidebar-body-split:122            导航面板:123 / 分栏柄:180 / 知识点块:181
│   │        └── 导航面板内四视图：files:124 / graph2d:127 / graph3d:132 / agent:135-178
│   ├── #sidebar-collapse-btn  index.html:195   fixed 收起/展开
│   └── #content               index.html:197   （memoria.css:388-393）
│       ├── #tab-bar > #tabs   index.html:198-200
│       └── #viewer            index.html:201   （memoria.css:439-443）
│           ├── #welcome       index.html:202    欢迎页（空态）
│           └── #editor-wrap   index.html:207    默认 .hidden；header:208 / preview-status:256 / editor-split:257
└── #status-bar                index.html:270    （memoria.css:561-573）
#-flash-host:278 · 9 个 .-modal:280-412   均在 #app 之外，fixed
```

> ⚠️ **行号漂移（2026-09-17 实测）**：本节 tree 的行号已按当前 `index.html` 重取。差异有两个来源：① **既有漂移**——本文此前记录的 `index.html` 锚点整段比实际**小 13 行**（`#app` 旧记 34、实际 47），`js/*.js` 锚点亦有小偏差（`showWelcome` 旧记 380-383、实际 388-391）；② **本次新增**——2026-09-17 在侧栏插入第 4 页签与「对话」面板（index.html:116 + 135-178，共 **+45 行**），故 `#main` 内其后节点 = 旧锚 +58（`#content` 139→197、`#status-bar` 212→270），`#app` 之外的浮层/弹窗 = 旧锚 +45（`#-flash-host` 233→278、`.-modal` 235-381→280-412）。**本文 §2.1/§2.2 与 §6 内的旧锚点尚未逐条重扫**，按上述偏移换算；本节 §2.3 新增段与 §2.3.1 用的是 2026-09-17 实测值。

**关键互斥关系**（§5 展开）：`#welcome` 与 `#editor-wrap` 由 `showWelcome()` 互斥（app.js:388-391）；导航面板内**四**视图由 `.hidden` 互斥（app.js:1241-1243，见 §2.3）；`#editor-split` 三视图由类名互斥（app.js:1646）。

## 2. 逐处细节

### 2.1 窗口 chrome（无边框、三键、拖拽、边缘缩放）

| 项 | 实现位置 | 说明 |
|---|---|---|
| 是否无边框 | window-chrome.js:296-297 | 由后端 `get_window_chrome().frameless` 决定（ui.py:662-672）；非无边框时隐藏三键并给所有拖拽区设 `-webkit-app-region: no-drag`（window-chrome.js:315-322） |
| 三键容器与外观 | index.html:87-91；app.css:1826-1896 | `#window-controls` 默认 `hidden`，仅 frameless 时显示（window-chrome.js:324）；按钮宽 2.875rem、高 2.1875rem，`font-size:0`，图形由 `::before/::after` 画（最小化=横线、最大化=方块、关闭=叉）；关闭键 hover 变 `#e81123` |
| 图标状态与行为 | window-chrome.js:23-28、367-380 | 最大化时切 `.is-restore`（app.css:1862-1870）并改 title/aria；三键分别经桥 `window_minimize` / `window_toggle_maximize` / `window_close` |
| 拖拽区与排除 | index.html:36,70,81,82,84；window-chrome.js:118-123 | 5 处挂 `pywebview-drag-region`（`.toolbar-left`、两个 spacer、`.toolbar-right`、`#kb-indicator`）；命中排除 `NO_DRAG_SELECTORS` = `#btn-kb-close, .-kb-exit, .toolbar-search-wrap, .toolbar-actions, .-window-controls`（`closest()` 判定） |
| pywebview 拖拽路径 | window-chrome.js:188-208、339-344 | `mousedown` → RPC `window_begin_drag` → 后端 `PostMessage` → WndProc 执行 `WM_NCLBUTTONDOWN + HTCAPTION`（原生拖动 + Aero Snap），不用 `-webkit-app-region` |
| pyqt6 拖拽路径 | window-chrome.js:158-179、125-156 | 走 `__memoriaQtBridge.startMove()`；另把 `.toolbar-right` 左沿 x 同步给 Qt 作拖拽排除带 |
| 最大化下拉还原 | window-chrome.js:222-283、8-9 | 阈值 `DRAG_THRESHOLD=4`、标题栏纵向偏移 `TITLEBAR_Y_OFFSET=17`；越阈值先 `window_restore_from_drag` 再 `window_move_to` |
| 双击标题栏 / 焦点回拉 | window-chrome.js:353-365、210-220 | 仅 pywebview 绑双击切换最大化；窗口重获焦点时用 `get_window_chrome()` 校正图标（覆盖 Aero Snap 等 JS 未知变化） |
| 边缘缩放层 | window-chrome.js:36-116；app.css:1898-1977 | `#window-resize-layer` 含 8 个手柄（n/s/e/w/nw/ne/sw/se），`z-index:10000`，拖拽经 `window_resize_to`（ui.py:674-681 再夹 900×600 下限） |
| 原生 NCHITTEST 例外 | window-chrome.js:57-64 | `shell === "pyqt6"` 且 Windows 时不启用 JS 缩放层，交给系统 `WM_NCHITTEST` |
| DWM 圆角 | src/memoria/app/window_win32.py:166-180 | `DWMWA_WINDOW_CORNER_PREFERENCE(33)=DWMWCP_ROUND(2)`，保留 DWM 边框/阴影，标题栏区域由 `WM_NCCALCSIZE→0` 消除；pyqt6 hidden chrome 同常量（src/memoria/app/shell/pyqt6_hidden_chrome.py:886-891） |
| 最小尺寸 / 版本号 | window-chrome.js:14、300-301、302-310 | 默认 `{w:900,h:600}` 可被后端覆盖；`version` 写入 `document.title`、`#welcome h1` 与 `#app-badge` |

> ⚠️ `.pywebview-drag-region` 在 `theme/memoria.css:101-105` 写着 `-webkit-app-region: drag`，但两条真实路径上都被 JS 显式改成 `no-drag`（window-chrome.js:318-320、334-337）——类名里的 "drag" 当前不生效。

### 2.2 顶栏

顶栏高 2.1875rem、左内边距 12px、右内边距 0（memoria.css:52-53），故窗口三键贴右缘。

| 元素 | 位置 | id / 类 | 交互 | 禁用 / 隐藏条件 |
|---|---|---|---|---|
| 品牌 + 版本徽标 | `.toolbar-left` | `#app-badge`（`.-badge`，app.css:3-15） | 无（拖拽区） | 徽标文本仅在后端返回 version 时填充（window-chrome.js:308-309） |
| 后退 | `.toolbar-actions` | `#btn-nav-back`（`.-nav-btn`） | 点击 → `navBack()`（app.js:12190）；Alt+←（app.js:12402-12405） | `disabled = !canBack()`（app.js:410）；HTML 初值 disabled（index.html:44） |
| 前进 | 同上 | `#btn-nav-forward` | 点击 → `navForward()`（app.js:12191）；Alt+→（app.js:12406-12409） | `disabled = !canForward()`（app.js:411） |
| 「文件」菜单按钮 | 同上 | `#btn-file`（`.-tb-file`，app.css:4326-4331） | 点击切换 `#file-menu` 显隐并同步 `aria-expanded`（app.js:12092-12098） | 无禁用 |
| ─ 打开 / ─ 导入 | 菜单内 | `#file-menu-open` / `#file-menu-import` | 关闭菜单后分别调 `openKb()`（app.js:12108；app.js:569-573）与 `MemoriaImportFlow.start()`（app.js:12109-12112） | 无 |
| ─ 导出（预留） | 菜单内 | `#file-menu-export` | 无 | 恒定禁用（index.html:51）；title "导出知识库（预留，待后续版本）"（i18n/zh-CN.js:510-511） |
| ─ 创建 Trae 智能体 | 菜单内 | `#file-menu-kb-agent` | 绑定于 kb-agent.js:188；未开库时给应用内错误提示（底栏转红 + 浮层），**不**弹系统目录选择（kb-agent.js:43-50） | 无 |
| ─ 新窗口 | 菜单内 | `#file-menu-new-window` | `spawnNewWindow("")` → `call("open_new_window")`（app.js:12115-12125、12177-12180） | 无 |
| ─ 打开最近 ▸（菜单项与分隔线顺序见 index.html:52-59） | 菜单内 | `#file-menu-open-recent` + `#file-menu-recent` | 点击展开二级面板并拉取列表（app.js:12181-12185）；点条目：未开库→本窗口装载，已开别的库→另开窗口，同库→忽略（app.js:12164-12173） | 列表项可 disabled：「读取最近打开列表失败」/「暂无最近打开的知识库」（app.js:12154-12161） |
| 刷新 | 同上 | `#btn-refresh` | 依次 `refreshFiles` → `loadLinkTargets` → `loadGraphData` → 以 `skipNav:true` 重开当前文件（app.js:12192-12197） | 无禁用、无前置检查 |
| 构建 | 同上 | `#btn-build` | `buildKb()`：同步链接配置并生成图谱（app.js:1027-1070） | 执行期间 `disabled`（app.js:1038、1068）；未开库不置灰，给错误样式提示（底栏转红 + 浮层，app.js:1032-1035） |
| 检查（+角标） | 同上 | `#btn-check` + `#btn-check-badge`（`.-toolbar-badge`，app.css:1800-1818） | 打开检查弹窗（kb-check.js:642）；角标按 error/warn 计数着色（kb-check.js:113-121） | 未开库不置灰，给错误样式提示（底栏转红 + 浮层，kb-check.js:622-626）；角标 `.hidden` 即隐藏（app.css:1820-1822） |
| 设置 | 同上 | `#btn-settings` | 打开设置弹窗（graph-settings.js:950） | 无 |
| 搜索范围开关 | `.toolbar-search-wrap` | `#toolbar-search-scope`（`role="switch"`） | 整块可点/可聚焦，点击或 Enter/Space 翻转「全库 ⇄ 文件」（toolbar-search.js:253-263）；子按钮 `pointer-events:none`（app.css:2035） | 内部「文件」子按钮在无 `currentPath` 时 `disabled`（toolbar-search.js:60）；强行切到 file 会发 `openFileFirst` 错误（toolbar-search.js:85-88） |
| 搜索框 | 同上 | `#toolbar-search` | 输入防抖 220ms、Enter 搜索（Shift+Enter 仅当前文件）、Esc 关面板并失焦、聚焦时有内容即重搜（toolbar-search.js:245-277）；Ctrl+K 聚焦（281-286） | 无禁用；未开库时提示 `openKbFirst`（错误样式，toolbar-search.js:132-135） |
| 搜索结果面板 | 同上 | `#toolbar-search-panel` | 绝对定位于搜索框下方，`z-index:9000`、最大高 `min(240px,40vh)`（app.css:2081-2096）；点外部或选中结果即隐藏（toolbar-search.js:278-280） | 默认 `.hidden`（index.html:78） |
| 知识库路径指示 | `.toolbar-right` | `#kb-indicator`（memoria.css:218-230） | 纯展示，title 为完整路径；CSS 标为拖拽区 | 外层 `#kb-indicator-wrap` 无路径时 `.hidden`（app.js:370-377） |
| 退出 | 同上 | `#btn-kb-close`（`-btn primary -btn--sm -kb-exit`） | `closeKb()`：屏障刷盘 → 关库 → 清空全部前端状态 → 回欢迎页（app.js:575-628、12188） | 与 `#kb-indicator-wrap` 同步隐藏 |
| 窗口三键 | 同上 | `#window-controls` | 见 §2.1 | 默认 `hidden`（index.html:87） |

### 2.3 左侧栏

| 项 | 证据 | 说明 |
|---|---|---|
| 容器 / 收起态 | index.html:109；app.css:123-144 | `#-sidebar` 默认宽 17.5rem、`min-width` 11.25rem、含宽度过渡；加 `.-sidebar--collapsed` 后宽 0、去右边框、溢出自隐、隐藏拖拽柄 |
| 收起/展开按钮 | index.html:195；app.css:147-171；app.js:11990-12039 | `fixed`、`top:45%`、`z-index:90`、20×40px 半圆角；展开时贴侧栏右缘（`left = right-1`）、收起时贴左缘；字形 `‹`/`›`；状态存 `localStorage["-sidebar-collapsed"]`（app.js:11988、12007）；几何变化不触发 `resize`，另用 `ResizeObserver` 跟踪（app.js:12027-12037） |
| 宽度拖拽 | index.html:110；app.js:11967-11984；memoria.css:262-274 | 手柄在右缘外 3px、宽 0.375rem、hover 高亮主题色；把 `clientX` 夹到 **180–480px**（与 CSS 的 11.25rem 最小值/17.5rem 默认值为两套口径） |
| **四页签** | index.html:112-117；app.js:1233-1255 | `[data-sidebar-tab]` = `files`(113) / `graph2d`(114) / `graph3d`(115) / **`agent`(116，2026-09-17 新增)**，复用 `.-config-tab` 样式（app.css:1210-1234）；切换逻辑**已是通用实现**（按 `dataset` 遍历按钮与视图，无 tab 白名单），故加页签无需改 app.js；当前页签写 `localStorage["-sidebar-tab"]`（app.js:1234-1235），初值读同键、默认 `files`（app.js:33） |
| 页签计数 | index.html:113-115；app.js:730-738 | `#sidebar-tab-count-files` = `state.files.length`；`#sidebar-tab-count-graph2d/-graph3d` = `state.graphData.nodes.length`（两者同值）；更新于 `refreshFiles`（app.js:638）与 `loadGraphData`（app.js:1061）；**「对话」页签不计数**（无 `-tab-count` 节点） |
| 页签内容 | index.html:124-178；app.js:1233-1255 | `files` → `#file-tree`（124-126）；`graph2d` → `#graph-2d-root` + 覆盖提示（127-130）；`graph3d` → `#graph-3d-root` + 覆盖提示（132-134）；**`agent` → 对话面板骨架（135-178，见 §2.3.1）**；切页签时 `.hidden` 互斥（app.js:1241-1243）并通知图谱视图 `stop()/start()`（app.js:1194-1210） |
| 图谱分组条 | index.html:119-121；app.js:757-766 | `#sidebar-graph-group-bar` 仅在图谱页签**且**节点数 > 0 时显示，同步 `aria-hidden`（非图谱页签一律隐藏 ⇒ 对话页签不显示） |
| 上下分栏 | index.html:122-147、180-181；graph-settings.js:330-332、394-412、967-971 | 上=导航面板、下=知识点块；柄高 6px、上方最小 100px、下方最小 72px；比例按页签记忆（默认 files 0.55 / graph2d 0.82 / graph3d 0.72，graph-settings.js:42-46）；**对话页签沿用兜底比例 0.6**（`SPLIT_DEFAULTS["agent"]` 未定义 ⇒ `?? 0.6`，graph-settings.js:361），并独立记忆在 `localStorage["-sidebar-split-agent"]`；柄样式见 app.css:377-389 |

#### 2.3.1 「对话」面板（第 4 个页签，2026-09-17 落地）

只读问答面板：问一句 → 后端 `ask()` 跑「检索 → 远端模型 → 带 `文件:行号` 锚点的回答」，
答案里的锚点可点击跳转。DOM 骨架**静态写在 index.html**（与 files/2D/3D 三视图同风格），
行为与渲染全部在独立模块 `js/agent-panel.js`（`window.MemoriaAgentPanel`，装配于 app.js:12853）。

| 项 | 证据 | 说明 |
|---|---|---|
| 容器与滚动 | index.html:135；app.css:327-329（`#sidebar-view-agent`） | 复用 `.-sidebar-view`（app.css:296-302）并覆盖 `overflow:hidden`：**消息区是唯一滚动容器**，头/设置区/输入区不随滚动移出视野 |
| 头部 | index.html:136-145；app.css:330-365 | `#agent-model-label`（模型名 + 关网时的「出网已关」尾注，由 `applyConfigToForm()`:256-284 写入）+ `#agent-net-toggle`（checkbox，文案「出网」）+ `#agent-settings-toggle`（`.-config-btn`，带 `aria-expanded`/`aria-controls`） |
| 折叠设置区 | index.html:146-167；app.css:366-405；agent-panel.js:531-538 | 默认 `.hidden`；点「设置」按钮 `classList.toggle("hidden")` 并同步 `aria-expanded`（**就地折叠，不弹窗**，故不影响 §2.8 的弹窗层级）。字段：`#agent-base-url` / `#agent-model` / `#agent-api-key`(type=password) / `#agent-timeout` + `#agent-save-config`；底部 `#agent-config-path` 显示 `config/agent.json` 相对路径（`agent.settings.path`） |
| 密钥处理 | index.html:157；agent-panel.js:266-270、315-328 | 输入框**永不回显**密钥：保存后清空，已存密钥只作 placeholder（`agent.settings.apiKeySet` 带 `{masked}`，掩码由后端 `mask_secret` 生成）；留空即「不修改」（后端 `save_config` 同语义，`llm/config.py:309-313`）；保存请求仅在输入非空时带 `api_key` |
| 消息区 | index.html:168；app.css:407-473；agent-panel.js:130-193 | `#agent-messages`（`role="log"`、`aria-live="polite"`）：用户气泡 `.-agent-msg--user`（主题色底）/ 助手气泡（`--bg-secondary`）；助手正文把 `路径.md:行号`（含反引号包裹）渲染成 `.-agent-anchor` 可点节点（`linkify()`:112-128），末尾另附 `.-agent-source` 来源条（后端 `anchors` 数组，`sourcesEl()`:155-175） |
| 锚点跳转 | agent-panel.js:516-526 → app.js:1403-1520 | 点锚点调门面 `openFile(file, {navSource:"agent", lineHint})`；**`kpId` 优先于 `lineHint`**（app.js:1505-1517）——本面板只用 `lineHint`（锚点是行号而非 KP）；未打开的文件会经 `load_document` 正常打开并高亮该行 |
| 输入区 | index.html:169-177；app.css:493-532；agent-panel.js:550-557 | `#agent-input` 多行 `textarea`（Enter 发送 / Shift+Enter 换行，`isComposing` 期间不发送以兼容中文输入法）；三按钮：`#agent-send`（primary）/ `#agent-abandon`（生成中才显示）/ `#agent-clear`（`margin-left:auto` 靠右）；`#agent-status` 状态行（`aria-live="polite"`）显示「生成中 / 用量 / 会话 id / 错误」 |
| 伪流式 | agent-panel.js:53-54、378-387、407-495 | `agent_ask_start` 提交后每 **250ms** 轮询 `agent_ask_poll(job_id, cursor)`，`delta` 追加进当前助手气泡（`applyDelta()` 流式期间用 `textContent` 追加、`finalizeMessage()`:389-405 定稿时再 linkify 重绘）；`done` 时以后端 `answer` 覆盖流式累积文本（loop 每轮以当轮文本覆盖 `answer`，故工具轮前言不在最终答案里） |
| 「忽略本次」 | agent-panel.js:498-505 | **不是取消**：仅 `job = null`（丢弃后续结果 + 停止轮询）并立即恢复发送按钮；后端 ask 仍在跑，此时再提问会收到 `busy` 结构化错误（文案如实说明「M1 无真取消」）。UI 措辞用「忽略本次」而非「停止」 |
| 换库 / 关库 | agent-panel.js:453-464 | 轮询期间 `state.kbPath` 变化 ⇒ 丢弃本次结果并提示（`agent.status.dropped`），不把 A 库的答案留在 B 库的面板里 |
| 发送前置 | agent-panel.js:407-419 | 未开库 / 未输问题 / `enabled=false` 时**就地报错**（状态行转红 + flash 卡片），不静默失败；前端已 `busy` 时直接返回不重复提交（后端仍有单飞约束）；`enabled=false` 时发送按钮 `disabled` 且带 title（`renderComposer()`:286-294） |
| 错误呈现 | agent-panel.js:60-85、202-231、332-350、478-483 | 后端 4 个 RPC 的错误按**稳定 code** 映射文案（`ERR_KEYS`:60-82）。**具体 code**（`busy`/`no_base_url`/`net_disabled`/`unknown_job`…）只显示本地化文案；**兜底 code**（`ask_failed`/`config_error`，`GENERIC_CODES`:85）额外拼后端原文——LLM 失败的真实原因（传输/认证/HTTP）只存在于 `error` 文本里；未登记 code 一律回显原文。flash 卡片同理（标题=本地化、详情=原文，app.js:344-358） |
| 语言切换 | agent-panel.js:578-582 | 静态节点由 `MemoriaI18n` 刷新；动态消息/状态行由 `MemoriaI18n.addRefresh` 重绘（与 kb-check.js 同套路） |
| 默认宽度下的观感 | 实测（harness，2026-09-17） | 侧栏宽度实测 **280px**（=17.5rem，与 app.css:124 一致）；`#sidebar-nav-panel` 的高度由「上下分栏」决定（默认兜底 0.6，graph-settings.js:361），**另一半留给知识点列表**。故消息区实际可用高度 ≈ `0.6 × 侧栏可用高 − 头部 − 输入区`；窗口矮时先触到 `SPLIT_MIN_TOP=100px` 下限，输入区会把消息区压到近乎为零（harness 376×271 窗口下实测：面板 100px、消息区 clientHeight 16px、输入区 87px 溢出被裁）。正常窗口（应用最小 900×600）下消息区约 300px 量级（**未逐档实测，为按比例的推算**） |

后端 4 个 RPC（`agent_get_config` / `agent_save_config` / `agent_ask_start` / `agent_ask_poll`）、
配置落点 `config/agent.json` 与会话事实源 `<kb>/.memoria/agent/sessions/*.jsonl`
见 [10-data-layout-and-host-embedding.md](./10-data-layout-and-host-embedding.md) §2.15。


### 2.4 文档区

| 项 | 证据 | 说明 |
|---|---|---|
| 层级 | index.html:139-208；app.css:3081-3092 | `#content` > `#tab-bar` + `#viewer`；`#editor-wrap` 可见时 `#viewer` 变无内边距、`overflow:hidden` 的纵向 flex（`:has()`） |
| 欢迎页 | index.html:144-148；memoria.css:445-466 | 标题 `Memoria`（运行时追加版本号）、副标题 `welcome.tagline`、`#btn-welcome-open` 打开知识库 |
| 文件信息 / 预览状态条 | index.html:151、198；app.js:1542-1544；app.css:3702-3706、4076-4085 | `#file-meta` 只显示**侧车 description**（`doc.sidecar.description`）；`#preview-status` 初始 `hidden`，警告态加 `.warn` |
| 格式工具栏 | index.html:152-184；app.css:3136-3197 | `.-format-bar`（`role="toolbar"`）：B / I / 分隔 / H▾（6 色 + 无色 + 添加颜色）/ 色▾（7 色 + 无色 + 添加颜色）/ 分隔 / `#btn-insert-image`（初始 `disabled`）；颜色下拉为 `position:fixed` + `z-index:10050`，靠 `.-fmt-dropdown` 加 `.open` 显示 |
| 块编辑栏（与格式栏互斥） | index.html:185-188；app.css:3756-3768；edit-handler.js:1010-1013、1134-1137、1545-1550 | 二者共用 `#editor-header` 同一位置：进块编辑时格式栏 `hidden`、块编辑栏显示，退出时反向 |
| 视图模式 | index.html:189-193；app.css:3111-3133、3453-3459 | `.-view-btn` 三键（源码/预览/分栏）：实现为 `#editor-split` 上换 `view-source|view-preview|view-split` 类；当前模式写 `localStorage["-view"]`（app.js:1571-1573），初值读同键、默认 `source`（app.js:20） |
| 编辑模式开关 | index.html:194-196；app.css:2048-2050；edit-handler.js:59-98 | `#edit-mode-toggle`（`role="switch"`，复用 `-toolbar-search-scope` 样式）+ `#btn-edit-mode`；**默认开启**（edit-handler.js:60）；关闭时 `#preview` 的 `contentEditable=false`、源码行全部只读并加 `.-readonly`（edit-handler.js:80-118），并强制禁用图片插入按钮（edit-handler.js:89-92） |
| 双窗格 | index.html:199-206；app.css:3441-3485 | `#editor-pane > #editor`（等宽字体，字号 `--editor-font-size`）、`#preview-pane > #preview`（`markdown-body`，字号 `--preview-font-size`） |

### 2.5 知识点面板（仅定位）

`#sidebar-kp-block`（index.html:123-133）位于左侧栏 `#sidebar-body-split` 的**下半区**，与导航面板以 `#sidebar-nav-kp-resizer` 分隔（见 §2.3）。内部为 `.sidebar-toolbar.-kp-toolbar`（标题「知识点」+ `#kp-count` + `#btn-config`「配置」+ `#btn-kp-new`「新建」）与 `#kp-list`（`.-panel -kp-panel`）。行为细节（KP 列表、hover、弹窗三 Tab、范围编辑）归 [05-knowledge-points.md](./05-knowledge-points.md)。

### 2.6 状态栏

| 项 | 证据 | 说明 |
|---|---|---|
| 容器与左段 | index.html:212-215；memoria.css:561-573 | 高 1.375rem、主题蓝底、白字、`flex-shrink:0`；`#status-info` 为 `flex:1` 单行省略（memoria.css:572），初值「就绪」（`app.status.ready`） |
| 右段统计块 | app.js:281-333；i18n/zh-CN.js:485-490 | 由 `renderStatusStats()` 以 ` · ` 连接：① 检查统计（有 error/warn 时，文案取自 kb-check.js 的 `statsChunk`，并打 `data-kb-check="1"`）；② 全库检查通过（`check.stat.pass`，且无文件级统计）；③ 图谱待办 warn 数；④ 当前文件统计 `app.stat.kpLines`「{kp} KP · {lines} 行」，若有 sidecar 问题再追加 `app.stat.errors/warnings` + `app.stat.sidecar`；⑤ 图谱审计问题（文件级优先，其次全库） |
| 样式与点击 | app.css:1732-1755；app.js:12219-12227 | `.-stat-error` 红、`.-stat-warn` 黄、`.-stat-ok` 次色；命中图谱审计时 `#status-stats` 加 `.-status-clickable`（黄 + 下划线 + 指针）；点击时 `data-kb-check` 优先 → 检查弹窗，否则 `data-graph-audit-goto` → 跳到首个图谱审计问题 |

### 2.7 闪烁提示（flash，瞬时反馈）

| 项 | 说明 |
|---|---|
| 宿主 / 位置 / 层级 | `#-flash-host`（index.html:233）；fixed，`left:50%`、`bottom:2rem`，纵向列；`z-index:12000`（app.css:2202-2213）⇒ **高于弹窗**，弹窗内也能看见 |
| 时长 / 并发 | 默认 3800ms + 280ms 淡出（app.js:347、354-356）；可多条堆叠（host 为 flex 列，追加节点） |
| 变体 / 入口 | `.-flash-error` 红边 + 标题/详情两行（app.css:2215-2227）、`.-flash-info` 绿边（app.css:2233-2245）；`showFlashError(msg, detail)`（app.js:344）、`showFlashInfo(msg)`（app.js:360），两者均已挂在 `MemoriaApp` 门面上供子模块调用 |
| 与底栏的分工 | `setStatusError(msg, detail)` = `setStatus` + `showFlashError`（app.js:374-377）⇒ 底栏 + 卡片**双写**；`setStatus(msg, undefined, {error:true})` 只把底栏转红、不弹卡片；「导入」未开库是唯一**只弹卡片、不写底栏**的入口（import-flow.js:44） |

> **2026-09-16 收敛为单通道**：原先另有一个 `js/toast.js` 轻提示组件（`#-toast`，z-index 30000），其唯一调用点（检查弹窗「复制报告」）与 flash 卡片**同文案双通道**，底部会叠两个一模一样的框。该模块、`#-toast` 节点与其 CSS 已删除，瞬时反馈一律走 flash 卡片（成功绿边 / 失败红边）。

### 2.8 弹窗与层级

通用结构（index.html:235-381 共 9 个）：`.-modal[.hidden]` > `.-modal-backdrop` + `.-modal-box[变体类]` > `.-modal-header`（标题 + `.-icon-btn` ×）/ `.-modal-body` / `.-modal-footer.-btn-bar`。

现有变体类：`#kp-modal`、`#config-modal`（`-modal-tabbed`）、`#assist-modal`（`-modal-assist`）、`#check-modal`（`-modal-check`）、`#settings-modal`（`-modal-settings`）、`#link-modal`、`#import-conflict-modal` / `#import-result-modal`（`-modal-import-conflict|-result`）、`#kb-agent-modal`（复用 `-modal-import-conflict`）。另有**运行时动态创建**的 `.-modal`：文件树输入/确认框（file-tree.js:263-300；app.js:706-728）。

| 层级值 | 归属 | 证据 |
|---|---|---|
| 1 | 面板内装饰（角标、范围带、辅助线） | app.css:1089、1100、1784、3579 |
| 2–6 | 顶栏内部：`.toolbar-right`:2、`.-graph-hint--overlay`:3、`.toolbar-left/actions`:4、`.-window-controls`:5、`.toolbar-search-wrap`:6 | memoria.css:172、63、74；app.css:411、1817、1996 |
| 10 / 20 | `#sidebar-resizer` / `.-link-target-suggest` | memoria.css:269；app.css:2854 |
| 50 / 60 / 61 / 90 | `#toolbar` / `.-tb-file-menu` / `.-tb-file-submenu` / `.-sidebar-collapse-btn` | memoria.css:59；app.css:4337、4397、151 |
| **1000** | **`.-modal`（全部弹窗）** | app.css:4122-4129 |
| 9000 / 10000 / 10050 | `.-toolbar-search-panel` / `.-win-resize-layer` / `.-context-menu`、`.-fmt-dropdown-menu` | app.css:2095、1901、2571、3184 |
| 12000 / 20000 / 99999 | `#-flash-host` / `.-color-picker-mask` / `.-lightbox-overlay` | app.css:2202、3279、4036 |

**同时只允许一个弹窗的约束**：**没有**"关掉其它弹窗"的中央实现，各弹窗各自管理自己的 `hidden`（app.js:3062、4539、5451；kb-check.js:629）；唯一存在的"全局互斥"是 F2 的前置检查——只要存在任一非 `hidden` 的 `.-modal` 就不劫持 F2（file-tree.js:453-457）。

弹窗可拖动：按住 `.-modal-header` 拖动 `.-modal-box`，位移用 `transform: translate()` 累加，排除按钮/输入类元素（app.js:12560-12609）；关闭时由 `MutationObserver` 清零位移（app.js:12611-12624）。

### 2.9 缩放与字号

| 变量 / 设置 | 写入位置 | 作用范围与取值 |
|---|---|---|
| `--preview-font-size` / `--editor-font-size` | `#preview`、`#editor` 的 inline style（display-settings.js:80-85） | 预览正文与 h1–h3 标题（app.css:3479、3511-3513）、源码/分栏区（app.css:3464）；12–28px，默认 14（display-settings.js:12、16-17），两者同值 |
| `--lineno-ch` | `#editor` inline style（app.js:1561-1564） | 源码行号列宽，按总行数位数自适应 |
| `uiScale` | `document.documentElement.style.fontSize = 16×scale px`；等于 1.0 时清空恢复（display-settings.js:87-98） | **全界面**：样式表尺寸/字号绝大多数用 `rem`，故整体等比缩放；改完主动派发一次 `resize` 让监听方重算（display-settings.js:97）；0.8–1.5、步长 0.1（display-settings.js:18-20），默认 1.0 |
| 持久化 | `localStorage["-display-settings"]`（display-settings.js:9、40-46）+ 磁盘 `ui-settings.json` 的 `display` 段（display-settings.js:114-118） | 启动 `hydrateFromDisk` 时"本地优先、磁盘仅作种子"（display-settings.js:66-77、120-138） |
| 快捷键 | `Ctrl+=` / `Ctrl++` 放大、`Ctrl+-` 缩小、`Ctrl+0` 复位（app.js:12201-12217） | 步进 ±0.1 并被夹在区间内（display-settings.js:147-157）；**无按键目标过滤**（输入框内同样生效） |

> 注：`index.html:231-232` 注释称"浮层放 `#app` 外以免受 `#app` 的 zoom 影响"，但当前实现改的是**根元素 `font-size`**（display-settings.js:92-93），`rem` 会级联到 `body` 下所有浮层，故 flash 卡片的间距实际**会**随缩放变化——注释与实现已不一致。

## 3. 交互流程

**3.1 启动 → 主界面**：`MemoriaBridge.onReady` 后统一 boot（导入流 → 工具条搜索 → 图片 → 检查 → KB 智能体 → 文件树 → **对话面板** → `initKb()` → `initWindowChrome()`，app.js:12845-12858）；`initWindowChrome` 先取 `get_window_chrome()`，失败则三键保持隐藏（window-chrome.js:289-293），成功则写标题/版本并判定 frameless（window-chrome.js:295-313）；`initKb()` 有路径时显示路径指示、清空导航栈与标签页、刷新文件、加载链接目标与图谱、跑一次完整检查并打开首选文件（`navigation-demo.md` → `mdp.md` → 首个文件，app.js:476-480），无路径则显示欢迎页、隐藏路径指示、状态栏写 `Memoria`（app.js:481-485）。

**3.2 顶栏「文件」菜单**：点 `#btn-file` 翻转 `#file-menu` 的 `hidden`、同步 `aria-expanded`、收起时一并隐藏二级面板（app.js:12092-12098）；点「打开最近」显示二级面板并异步拉列表（app.js:12181-12185）；关闭有三条路径——点菜单外部（app.js:12099-12104）、按 Esc（app.js:12105-12107）、点任意菜单项（各项 handler 首句都先 `closeFileMenu()`）。

**3.3 侧栏页签**：点 `[data-sidebar-tab]`（app.js:12588-12590）→ `setSidebarTab`（app.js:1233-1255）：写 localStorage、刷新按钮 `.active`/`aria-selected`、切换 `[data-sidebar-view]` 的 `.hidden`；随后清图谱 hover、启停对应图谱视图、按需重算上下分栏比例。「对话」页签额外在自己的 `click` 监听里拉一次端点配置（agent-panel.js:552-553；见 §2.3.1）。

**3.4 视图 / 编辑模式**：点 `.-view-btn` → `setViewMode(mode)`：先把源码编辑器内容同步回 `state.doc` 并重渲染两窗格，再换 `#editor-split` 类名与按钮 `.active`（app.js:1567-1611）；点 `#edit-mode-toggle` → `toggleEditMode()`（app.js:12453-12462）：切 `contentEditable`、刷按钮态、按需禁用图片插入（edit-handler.js:70-98）；预览区双击进入块编辑时格式栏与块编辑栏互换（edit-handler.js:1009-1013），退出恢复（edit-handler.js:1545-1550）。

**3.5 缩放**：`Ctrl+=` / `Ctrl+-` / `Ctrl+0` → `adjustUiScale(±0.1)` / `resetUiScale()` → 改根 `font-size` 并派发 `resize`（app.js:12201-12217；display-settings.js:87-98、147-157）。

## 4. i18n key

键定义在 `app/i18n/zh-CN.js` 与 `en.js`（成对），由 `i18n.js` 在启动/切语言时按 `[data-i18n]`（textContent）与 `[data-i18n-attr="attr:key;attr2:key2"]`（属性）刷新（i18n.js:91-115、154-169）。本区域涉及的前缀：

| 前缀 / 键 | 覆盖 | 代表键（zh-CN.js 行号） |
|---|---|---|
| `app.*` | 状态栏、窗口/范围 aria、空态 | `app.status.ready`、`app.status.kbEmpty`、`app.stat.kpLines`、`app.scope.aria`、`app.kbPath.title`（468-495） |
| `toolbar.*` | 顶栏全部按钮与文件菜单项、相关 title | `toolbar.file`、`open`、`import`、`export`、`kbAgent`、`newWindow`、`openRecent`、`recentEmpty`、`refresh`、`build`、`check`、`settings`、`exit`、`back.title`、`forward.title`（496-526） |
| `win.*` | 窗口三键与控制区 aria | `win.controlsAria`、`minimize`、`maximize`、`restore`、`close`（421-427） |
| `side.*` | 侧栏页签、分栏、收起、知识点工具栏 | `side.tabs.aria`、`side.tab.files`、`collapseTitle`、`expandTitle`、`split.title`、`side.kp.label|config|new`（561-574） |
| `view.*` / `edit.*` | 视图模式、编辑模式、格式栏、块编辑栏 | `view.toggleAria`、`view.source|preview|split`、`edit.mode.aria|title|browseTitle|btn`、`edit.fmt.aria|boldTitle|…`、`edit.block.aria`（643-674，2026-09-17 因插入 `agent.*` 整体 +68） |
| `search.*` | 搜索范围、占位符、状态与结果文案 | `search.scopeKb`、`scopeFile`、`ph`、`title`、`statusSearching`（527-536） |
| `agent.*` | 侧栏「对话」面板（页签名/出网开关/端点设置 8 字段/输入占位/角色两态/来源/状态与错误） | `agent.tab`、`agent.net.label`、`agent.settings.apiKeySet`、`agent.status.usage`、`agent.err.no_base_url`（zh-CN.js:575-642） |
| `dlg.*` / `check.*` / `kbAgent.*` / `import.*` | 各弹窗标题与按钮 | `dlg.kpTitle`、`dlg.configTitle`、`check.modalTitle` 等 |

完整清单与未迁移中文行的登记规则见 [../i18n-inventory.md](../i18n-inventory.md)；语言系统维护规范见 [../../conventions/i18n.md](../../conventions/i18n.md)。

## 5. 边界与已知坑

1. **弹窗层级低于多个浮层**：`.-modal` 为 `z-index:1000`（app.css:4218），低于搜索面板 9000、右键菜单 10050、flash 卡片 12000、颜色选择器遮罩 20000、图片灯箱 99999。flash 卡片刻意高于弹窗（弹窗会遮住底栏，反馈只能靠它，见 §2.7），代价是**任何 1000 以上的浮层都能盖住弹窗**。
2. **没有"只能开一个弹窗"的中央约束**：各弹窗独立管理 `hidden`，多个弹窗可同时可见；唯一的"统一判定"是 F2 的全局检查（file-tree.js:453-457）。
3. **禁用态并不统一**：后退/前进用 `disabled`；构建仅在执行中 `disabled`；检查/刷新/设置无禁用，改为点击后提示前置条件（`openKbFirst` / `openFileFirst`）。**这类提示分两档**：`setStatusError` = 底栏整行转红（`.-status-error`，app.css:1777-1787）+ 底部浮层卡片；`setStatus` = 底栏普通色。当前「硬前置」类（构建/检查/插入图片/搜索/创建智能体）都走**前者**；**导入**是唯一只弹悬浮卡片、**不**写底栏的入口（直调 `showFlashError`，见 08 篇 §2.1）。集成方判断"能否操作"需按 §2.2 表逐项判，不能只看是否灰化。
4. **侧栏宽度是两套口径**：CSS 默认 17.5rem / 最小 11.25rem（app.css:124-125），JS 拖拽夹在 180–480px（app.js:11977）；非 100% 缩放时 rem 与 px 不一致，会出现"能拖到比 CSS 最小值更窄/更宽"的观感。
5. **`Ctrl+= / Ctrl+- / Ctrl+0` 无目标过滤**：在搜索框、弹窗输入框内按同样触发整界面缩放（app.js:12203-12216 未检查 `e.target`）。
6. **顶栏拖拽靠"选择器黑名单"**：`NO_DRAG_SELECTORS`（window-chrome.js:118-119）未包含 `.toolbar-left` 内部元素，故品牌区整体可拖；新增顶栏控件若不在黑名单内，会被拖拽的 mousedown 吞掉点击。
7. **块编辑栏与格式栏互斥**：二者共用 `#editor-header` 同一位置；若在块编辑中切换视图，恢复依赖 `_restoreToolbar()`（edit-handler.js:1545-1550），未被调用则格式栏会一直隐藏。
8. **`#preview-status` 的 `.warn` 态样式存在但需渲染层主动加类**（app.css:4080）；未打开文件时该节点保持 `hidden`（index.html:198）。
9. **`theme/memoria.css` 含大量与当前 DOM 不符的历史选择器**：`#sidebar`、`.toolbar-center`、`#group-tabs`、`.mode-switch`、`.file-grid`、`.file-card` 在 `index.html` 与 `js/**` 中均无对应节点（已检索确认）。不要把它里面的 `#sidebar { width: 23.75rem }`（memoria.css:251-253）当成左侧栏实际宽度——实际是 `#-sidebar { 17.5rem }`（app.css:124）。
10. **`uiScale` 的注释已过时**：见 §2.9 末尾（index.html:218-219 vs display-settings.js:92-93）。
11. **「对话」面板在默认宽度下偏窄，且高度被「上下分栏」分掉一半**（2026-09-17 harness 实测）：侧栏宽 280px（=17.5rem），面板只占 `#sidebar-nav-panel` 上半（默认兜底 0.6），下半是知识点列表。事实层面：问答内容比文件树/图谱更耗横向与纵向空间，而本面板目前**只能挤在左栏第 4 个页签**——**是否改为右栏 / 抽屉 / 加宽侧栏默认值 / 给本页签单独的分栏比例（`SPLIT_DEFAULTS["agent"]`），属布局取舍，本轮未决定**（本轮只把面板做出来，未动既有布局约定）。
12. **设置区展开后在矮窗口会被裁**：`#sidebar-view-agent` 为 `overflow:hidden`，头/设置区/输入区都是 `flex-shrink:0`，只有消息区可伸缩。因此窗口高度不足时，展开的「设置」表单（含 保存 按钮）会落到面板可视区之外且无法滚动——harness 376×271 窗口下已复现（原生点击无法触达 保存）。正常窗口（应用最小 900×600）是否也有此问题**未逐档实测**；若要让设置区任何高度都可操作，需要给面板加一个滚动兜底（例如 `#agent-settings` 自身 `overflow-y:auto` + `max-height`），本轮未做。
13. **面板的「忽略本次」不是取消**：M1 后端 ask 无取消点（`services/agent/loop.py` 循环内无中断检查），故点「忽略本次」后若立刻再提问，会收到 `busy` 结构化错误提示（`agent.err.busy`）。这是如实措辞而非缺陷，见 §2.3.1。
14. **端点配置是全局的、不随库走**：`config/agent.json` 在程序目录（与 `ui-settings.json` 同级），一个进程一份；`enabled=false` 时发送按钮禁用（`disabled` + title），**不是**点击后报错。
15. **对话面板的滚动边界**：`#sidebar-view-agent` 设 `overflow:hidden`（app.css:327-329），只有 `#agent-messages` 滚动；若未来往头部/设置区加内容，需自行保证它们不撑破（否则会挤压消息区最小高度）。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 顶层骨架 / 区域顺序 | index.html:34-216；theme/memoria.css:39-43、248、388-393、439-443 |
| `#toolbar` 尺寸与层级 / 顶栏元素顺序 | theme/memoria.css:46-60；index.html:35-93 |
| 拖拽区标记 / 排除选择器 | index.html:36、70、81、82、84；window-chrome.js:118-123 |
| 原生标题栏拖动 / 下拉还原 / 双击最大化 / 焦点回拉 | window-chrome.js:188-208、339-344、222-283、353-365、210-220 |
| 边缘缩放层 / 三键图形 / 最大最小尺寸 | window-chrome.js:36-116；app.css:1898-1977、1826-1896；window-chrome.js:14、300-301 |
| 窗口信息接口 / DWM 圆角 | src/memoria/presentation/api/ui.py:662-672；src/memoria/app/window_win32.py:166-180 |
| 文件菜单开合 / 最近列表渲染 | app.js:12085-12185、12134-12175 |
| 后退前进动作与按钮态 / Alt+←→ | app.js:406-412、6201-6213、12402-12410 |
| 刷新 / 构建 | app.js:12192-12197、1012-1049 |
| 侧栏页签 / 计数 / 宽度拖拽 / 收起展开 / 上下分栏 | app.js:1233-1255、730-738、11967-11984、11986-12039；graph-settings.js:330-332、394-412、967-971 |
| **「对话」面板**（骨架 / 样式 / 模块 / 装配） | index.html:116、135-178；app.css:324-532；js/agent-panel.js:1-595；app.js:12853 |
| 侧栏与树样式 | app.css:123-323；app.css:3000-3048 |
| 图谱分组条显隐 | app.js:748-757 |
| 视图模式切换 / 编辑模式开关 | app.js:1567-1629；app.css:3453-3459；edit-handler.js:59-122 |
| 格式栏与块编辑栏互斥 | index.html:152-188；edit-handler.js:1009-1013、1545-1550 |
| 欢迎页与文档区切换 / 关库复位 | app.js:380-383、575-628 |
| 状态栏统计拼装 / 点击跳转 / 样式 | app.js:281-333、12219-12227；app.css:1732-1755 |
| flash 卡片实现 | app.js:344-372；app.css:2202-2245 |
| 弹窗通用结构 / 拖动 / 动态弹窗 | app.css:4122-4186；app.js:12560-12625、706-728；file-tree.js:263-300 |
| 显示设置（字号 / 缩放）/ 缩放快捷键 | display-settings.js:11-20、79-98、140-157；app.js:12201-12217 |
| i18n 静态节点刷新 / boot 顺序 | i18n.js:91-115、154-169；app.js:12845-12858（`MemoriaAgentPanel.init` 在 12853） |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未能取证）：`#preview-status` 的填充逻辑与出现时机（app.js:2029-2047 附近有读写点，但完整触发链跨渲染层，未穷尽；留 [04-preview-and-rendering.md](./04-preview-and-rendering.md)）。
- ⚠️ 待确认（未能取证）：`.-graph-settings-preview`（设置页内的图谱预览窗，app.css:332-367）的归属与交互，需在 [06-links-and-graph.md](./06-links-and-graph.md) 或 09 篇确认。
- ⚠️ 待确认（未能取证）：`#-flash-host` 的 `aria-live="polite"` 在动态追加节点时是否被屏幕阅读器正确播报（前端无额外处理，未在真实环境验证）。
- ⚠️ 待确认（未能取证）：`body.-win-dragging` 类（app.css:1984-1987）的写入方未在 `window-chrome.js` 中找到（该文件只写 `.-win-resizing`，window-chrome.js:94、109），疑似遗留样式。
- ⚠️ 待确认（未能取证）：`document.title` 与 `#welcome h1` 的版本号只在 `initWindowChrome` 成功返回时写入；无桥（纯浏览器）环境下的表现未验证。
- ⚠️ **本轮已断言 / 未取证（对话面板）**：已在 harness（端口 8642）断言 8 项——四页签与视图互斥、面板 DOM 齐全、空输入报错、未配置端点报错（状态行 + flash + 气泡）、出网开关读写与发送禁用、配置回填与**密钥掩码进 DOM 而明文不进 DOM**、真实作业（指向必拒连的 `http://127.0.0.1:9/v1`）从「生成中…」到 `askFailed+后端原文` 的全链路、忽略本次与 `busy` 文案；见 [docs-management.md §4.2](../../conventions/docs-management.md) 该行。**未取证**：① **真实模型的端到端效果**（打字机节奏、`answer` 覆盖流式文本的观感、`anchors` 条数）——需真实 `base_url` + 密钥，本轮**刻意未调用**真实端点（配置里那个 `config/agent.json` 是用户自己的真密钥，harness 用临时 `MEMORIA_CONFIG_DIR` 隔离）；② 设置区「保存」按钮的**原生点击**路径（harness 窗口仅 376×271，展开设置后按钮被裁，见 §5 第 12 条；该 RPC 已在 `/rpc` 层断言）；③ 侧栏 480px 上限与正常窗口高度下的排版（**推算非实测**）；④ 深色/浅色两套主题下的实际取色（`.-agent-*` 只用既有变量，10 个变量中 9 个在两个主题文件里都有定义；`--theme-color` 仅由 `theme/memoria.css` 定义、浅色主题不覆盖——这是**既有全局行为**，非本次引入）。
