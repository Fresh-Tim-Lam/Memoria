# 01 · 窗口外壳与整体布局

> **用途**：把 Memoria 桌面窗口的「外壳 + 五大区域」（窗口 chrome / 顶栏 / 左侧栏 / 文档区 / 状态栏）连同闪烁提示（flash）、弹窗层级与缩放变量，写到可据以定位实现的粒度。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[README.md](./README.md)（本套说明书的用法与维护约定）、[02-file-tree-and-nav.md](./02-file-tree-and-nav.md)（左侧栏「文件」页签的细节）、[09-settings-i18n-and-shortcuts.md](./09-settings-i18n-and-shortcuts.md)（设置四页与快捷键总表）、[../preview-formats.md](../preview-formats.md)（渲染语法权威）、[../i18n-inventory.md](../i18n-inventory.md)（文案清单）。
> **状态**：生效中，2026-09-18。

---

**证据锚约定**：`文件:行号` 以**仓库根目录**为基准。前端在 `src/memoria/ui/static/app/**`；少量外壳样式在 `src/memoria/ui/static/theme/memoria.css`（下称 `theme/memoria.css`）；窗口 chrome 的原生部分属后端，涉及处标 `src/memoria/app/**`。

## 1. 区域概览

```
#app                          index.html:47    （memoria.css:39-43 纵向 flex，高 100vh）
├── #toolbar                  index.html:48    z-index 50（memoria.css:46-60）
│   顺序：.toolbar-left:49 → .toolbar-actions:56（末位 `#btn-agent`:82）→ spacer:84
│         → .toolbar-search-wrap:85 → spacer:95 → .toolbar-right:96
├── #main                     index.html:109   （memoria.css:248 横向 flex，flex:1）
│   ├── #-sidebar             index.html:110    （app.css:123-133）
│   │   ├── #sidebar-resizer:111 · .-sidebar-tabs-wrap:112（文件/2D/3D）
│   │   ├── #sidebar-graph-group-bar:119       仅图谱页签 + 有节点时显示
│   │   └── #sidebar-body-split:122            导航面板:123 / 分栏柄:136 / 知识点块:137
│   │        └── 导航面板内三视图：files:124 / graph2d:127 / graph3d:131
│   ├── #sidebar-collapse-btn  index.html:151   fixed 收起/展开（左栏，z-index 90）
│   ├── #content               index.html:153   （memoria.css:388-393）
│   │   ├── #tab-bar > #tabs   index.html:154-156
│   │   └── #viewer            index.html:157   （memoria.css:439-443）
│   │       ├── #welcome       index.html:158    欢迎页（空态）
│   │       └── #editor-wrap   index.html:163    默认 .hidden；header:164 / preview-status:212 / editor-split:213
│   ├── #-agent-dock           index.html:225   右侧「对话」停靠栏（app.css:331-344）；见 §2.4
│   │   ├── #agent-dock-resizer:226             左缘拖拽柄（app.css:371-384）
│   │   └── 内部：顶部操作条:227-236 / 设置区:237-258 / 历史行:259-262 / 消息区:263 / 输入区:264-272
│   └── #agent-dock-collapse-btn index.html:275 fixed 收起/展开（右栏，z-index 90）
└── #status-bar                index.html:279    （memoria.css:604-615）
     #status-info:280 · #status-stats:281 · #status-agent:282（agent 用量格）
#-flash-host:288 · 9 个 .-modal:290-436   均在 #app 之外，fixed
```

> ⚠️ **行号漂移（2026-09-18 实测）**：本节 tree 已按当前 `index.html` 重取。差异来源：① **既有漂移**——本文最初记录的 `index.html` 锚点整段比实际**小 13 行**（`#app` 旧记 34、实际 47），`js/*.js` 锚点亦有小偏差（`showWelcome` 旧记 380-383、实际 388-391）；② **2026-09-17 第一轮**——在侧栏插入第 4 页签与「对话」面板（共 +45 行），故 `#main` 内其后节点 = 旧锚 +58；③ **2026-09-17 第二轮**——对话面板由左栏第 4 页签**迁为右侧 `#-agent-dock`**（`index.html` 净 +4 行）；④ **2026-09-17 第三轮**（文档区最小宽度保护）**未改 `index.html`**，但 `app.css` 在 dock 段插入了 `.-agent-dock--auto-hidden`（+14 行）⇒ `app.css` 中 dock 段及其后行号整体位移；⑤ **2026-09-18（本轮 M1c）**——对话面板新增历史行 `.-agent-history`（`index.html` **+4 行**，259-262）⇒ **`index.html` 中 dock 之后各节点行号 +4**（`#-agent-dock` 225 不变、`</aside>` 269→273、折叠按钮 271→275、`#status-bar` 274→278、`#-flash-host` 282→286、`.-modal` 284-430→288-434）；`app.css` 仅新增 `.-agent-history` 5 条规则（494-526，其后各条行号下移 33 行，如 `.-agent-messages` 494→527）；⑥ **2026-09-18（本轮「agent 用量可视化」）**——`#status-bar` 内新增 agent 用量格 `<span id="status-agent">`（`index.html` **+1 行**）⇒ 其后各节点行号 +1（`#-flash-host` 286→288、`.-modal` 288-434→290-436）；`app.css` 新增 `#status-agent` 3 条规则（**+12 行**，其后各条行号 +12）；`js/agent-panel.js` **+131 行**（状态栏用量格的状态与渲染/累加，见 §2.7）⇒ §2.4 表中 `agent-panel.js` 锚点按 **+5**（原 1-555 段）/ **+111**（原 556+ 段）换算。**本文 §2.1/§2.2 内的旧锚点仍未逐条重扫**，按上述偏移换算；§2.3 与 §2.4 用的是 2026-09-18 实测值。

**关键互斥关系**（§5 展开）：`#welcome` 与 `#editor-wrap` 由 `showWelcome()` 互斥（app.js:388-391）；导航面板内**三**视图由 `.hidden` 互斥（app.js:1241-1246，见 §2.3）；`#editor-split` 三视图由类名互斥（app.js:1646）。

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
| 对话（右侧 dock 开关） | 同上 | `#btn-agent`（`data-i18n="agent.tab"`，index.html:82） | 点击切换右侧 `#-agent-dock` 的展开/收起（agent-panel.js:259-261 → `toggleDock()`，它在「手动折叠**或**空间不足自动隐藏」两种隐藏态下都解释为"请求展开"）；与浮动 `#agent-dock-collapse-btn` 共用同一状态机（agent-panel.js:231-234、272-286）；`aria-pressed` 反映展开态（agent-panel.js:196）；见 §2.4 | 无禁用；页面无 `#-agent-dock` 时整个面板不装配（agent-panel.js:735） |
| 搜索范围开关 | `.toolbar-search-wrap` | `#toolbar-search-scope`（`role="switch"`） | 整块可点/可聚焦，点击或 Enter/Space 翻转「全库 ⇄ 文件」（toolbar-search.js:253-263）；子按钮 `pointer-events:none`（app.css:2035） | 内部「文件」子按钮在无 `currentPath` 时 `disabled`（toolbar-search.js:60）；强行切到 file 会发 `openFileFirst` 错误（toolbar-search.js:85-88） |
| 搜索框 | 同上 | `#toolbar-search` | 输入防抖 220ms、Enter 搜索（Shift+Enter 仅当前文件）、Esc 关面板并失焦、聚焦时有内容即重搜（toolbar-search.js:245-277）；Ctrl+K 聚焦（281-286） | 无禁用；未开库时提示 `openKbFirst`（错误样式，toolbar-search.js:132-135） |
| 搜索结果面板 | 同上 | `#toolbar-search-panel` | 绝对定位于搜索框下方，`z-index:9000`、最大高 `min(240px,40vh)`（app.css:2081-2096）；点外部或选中结果即隐藏（toolbar-search.js:278-280） | 默认 `.hidden`（index.html:78） |
| 知识库路径指示 | `.toolbar-right` | `#kb-indicator`（memoria.css:218-230） | 纯展示，title 为完整路径；CSS 标为拖拽区 | 外层 `#kb-indicator-wrap` 无路径时 `.hidden`（app.js:370-377） |
| 退出 | 同上 | `#btn-kb-close`（`-btn primary -btn--sm -kb-exit`） | `closeKb()`：屏障刷盘 → 关库 → 清空全部前端状态 → 回欢迎页（app.js:575-628、12188） | 与 `#kb-indicator-wrap` 同步隐藏 |
| 窗口三键 | 同上 | `#window-controls` | 见 §2.1 | 默认 `hidden`（index.html:87） |

### 2.3 左侧栏

| 项 | 证据 | 说明 |
|---|---|---|
| 容器 / 收起态 | index.html:110；app.css:123-144 | `#-sidebar` 默认宽 17.5rem、`min-width` 11.25rem、含宽度过渡；加 `.-sidebar--collapsed` 后宽 0、去右边框、溢出自隐、隐藏拖拽柄 |
| 收起/展开按钮 | index.html:151；app.css:147-171；app.js:12158-12206 | `fixed`、`top:45%`、`z-index:90`、20×40px 半圆角；展开时贴侧栏右缘（`left = right-1`）、收起时贴左缘；字形 `‹`/`›`；状态存 `localStorage["-sidebar-collapsed"]`（app.js:12158、12177）；几何变化不触发 `resize`，另用 `ResizeObserver` 跟踪（app.js:12187-12206） |
| 宽度拖拽 | index.html:111；app.js:12134-12154；夹取 app.js:12103-12106；手柄样式 theme/memoria.css:304-316 | 手柄在右缘外 3px、宽 0.375rem、hover 高亮主题色；把 `clientX` 夹到 **180–480px**（与 CSS 的 11.25rem 最小值/17.5rem 默认值为两套口径）；`mouseup` 落盘 `layout.sidebarWidth`（app.js:12113-12122，落盘点 12121） |
| **三页签** | index.html:112-116；app.js:1233-1258 | `[data-sidebar-tab]` = `files`(113) / `graph2d`(114) / `graph3d`(115)，复用 `.-config-tab`；切换逻辑是通用实现（按 `dataset` 遍历按钮与视图，无 tab 白名单，app.js:1239-1246）；当前页签写 `localStorage["-sidebar-tab"]`（app.js:1238），初值读同键、默认 `files`（app.js:33）。**2026-09-17：「对话」第 4 页签已删除**（面板迁为右侧 `#-agent-dock`，见 §2.4），同时 `setSidebarTab` 加了一行守卫——存量 `localStorage["-sidebar-tab"]="agent"` 命中不到任何 `[data-sidebar-view]` 时回退 `files`（app.js:1234-1236），否则三个视图会被一起隐藏 |
| 页签计数 | index.html:113-115；app.js:739-741 | `#sidebar-tab-count-files` = `state.files.length`；`#sidebar-tab-count-graph2d/-graph3d` = `state.graphData.nodes.length`（两者同值）；更新于 `refreshFiles`（app.js:639）与 `loadGraphData`（app.js:1072） |
| 页签内容 | index.html:124-134；app.js:1239-1246 | `files` → `#file-tree`（124-126）；`graph2d` → `#graph-2d-root` + 覆盖提示（127-130）；`graph3d` → `#graph-3d-root` + 覆盖提示（131-134）；切页签时 `.hidden` 互斥（app.js:1244-1246）并通知图谱视图 `stop()/start()`（app.js:1248 → `setGraphPanelActive`，1194-1210） |
| 图谱分组条 | index.html:119-121；app.js:757-768 | `#sidebar-graph-group-bar` 仅在图谱页签**且**节点数 > 0 时显示，同步 `aria-hidden` |
| 上下分栏 | index.html:122-134、136-137；graph-settings.js:343、361、915-965、967 | 上=导航面板、下=知识点块；柄高 6px、上方最小 100px（`SPLIT_MIN_TOP`，graph-settings.js:343）、下方最小 72px；比例按页签记忆（默认 files 0.55 / graph2d 0.82 / graph3d 0.72，graph-settings.js:43-47）；柄样式见 app.css:587-599 |

### 2.4 右侧「对话」停靠栏（`#-agent-dock`，2026-09-17 由左栏第 4 页签迁出）

只读问答面板：问一句 → 后端 `ask()` 跑「检索 → 远端模型 → 带 `文件:行号` 锚点的回答」，
答案里的锚点可点击跳转。DOM 骨架**静态写在 index.html**（index.html:225-269；`index.html:271` 是同级的浮动折叠按钮），
行为与渲染全部在独立模块 `js/agent-panel.js`（`window.MemoriaAgentPanel`，装配于 app.js:12856）。
结构**与左栏 `#-sidebar` 镜像**：同为 `#main` 的直系子节点（在 `#content` **之后**）、`flex-shrink:0`、
1px 分隔边框、宽度过渡；差别只在「贴右缘 / 边框在左 / 拖拽方向相反」。

| 项 | 证据 | 说明 |
|---|---|---|
| 容器与宽度 | index.html:225；app.css:331-344 | `#-agent-dock` 默认 **22rem**、`min-width` **16rem**、`max-width` **34rem**；`background:var(--bg-secondary)`、`border-left:1px solid var(--border)`、`transition: width .18s ease`；**展开态不设 `overflow`**（与 `#-sidebar` 一致——设了会把它左缘外 3px 的拖拽柄裁掉一半，见「拖拽柄」行）。内容结构 = 顶部操作条 / 折叠设置区 / **历史行（M1c）** / 消息区（唯一滚动容器）/ 底部输入区，五段都是 `flex-shrink:0` 或 `flex:1` 的纵向 flex 子项 |
| 宽度单位是 rem | agent-panel.js:185-193、259-281 | JS 改宽写的是 `dock.style.width = <n>rem`（不是 px），故随显示设置的根 `font-size`（`uiScale`，见 §2.10）等比缩放，与 CSS 默认值同口径；拖动时用 `getComputedStyle(documentElement).fontSize` 做 px↔rem 换算 |
| 折叠（宽度归零） | app.css:347-356；agent-panel.js:228-257、362-380 | 加 `.-agent-dock--collapsed` ⇒ `width:0 !important`、`min-width:0`、去左边框、`overflow:hidden`、隐藏 `#agent-dock-resizer`。**只归零宽度、节点仍在 DOM**（不 `display:none`），故 `clientWidth===0` 可断言；状态可逆 |
| 两个折叠入口（同一状态） | index.html:82、276；agent-panel.js:283-285、1209-1214 | 顶栏 `#btn-agent`（见 §2.2）与浮动 `#agent-dock-collapse-btn` 都调 `toggleDock()`——它把「隐藏态（手动折叠**或**空间不足自动隐藏）点击」统一解释为「请求展开」，故自动隐藏时点到的是展开分支（由 `setDockCollapsed` 拦下并提示，见下行「空间不足自动隐藏」）；前者以 `aria-pressed`、后者以 `aria-expanded` + 字形反映状态。**默认展开可见**（`dockCollapsed` 初值 false，agent-panel.js:179） |
| 展开/收起浮动按钮 | app.css:387-411；agent-panel.js:211-226 | `fixed`、`top:45%`、`z-index:90`、20×40px、圆角在左（`6px 0 0 6px`，去右边框）；**贴对话栏左缘**（`right = innerWidth − dock.left − 1`），折叠/自动隐藏时 `right:0` 贴窗口右缘；字形展开态 `›`（可收起）、隐藏态 `‹`（可展开）；宽度过渡期间靠 `ResizeObserver` 持续跟随（agent-panel.js:1223-1225） |
| 拖拽柄 | index.html:226；app.css:357-370；agent-panel.js:337-360 | 贴**左**缘外 3px、宽 0.375rem（`left:-3px` ⇒ 可抓区 3px 在 dock 内、3px 在外，故**展开态必须不裁剪**）、`cursor:col-resize`、hover 高亮主题色；**向左拖变宽**（期望宽度 = `innerWidth − clientX`，与左栏相反）；拖动中实时夹到 16–34rem（`clampDockRem`，agent-panel.js:190-193），**上界还受 `available` 约束**（`min(34rem, available)`，见下行「文档区最小宽度保护」）；拖动中实时生效、**`mouseup` 才落盘**（写的是期望宽度） |
| **文档区最小宽度保护**（期望 ≠ 生效） | agent-panel.js:172-183、196-209、259-281 | 新增 `CONTENT_MIN_PX = 360`（agent-panel.js:179）。`layout.agentDockWidth` 是**期望宽度**（rem，只在拖拽/显式操作时写盘）；每次布局变化按 `available = #main.clientWidth − 左栏生效宽度 − 360` 算**生效宽度**（agent-panel.js:259-281）：手动折叠 → 0；`available ≥ 16rem` → `clamp(期望, 16rem, min(34rem, available))`；否则 → 0。左栏「生效宽度」= 未折叠时的实测宽度、折叠时按 0 计（`sidebarEffectivePx()`，agent-panel.js:196-202，直接量几何宽度即可覆盖两态）。生效宽度只写**内联 `width`**（rem），**不覆盖** CSS 的 min/max 规则；因此 `#content` 宽度 = `#main.clientWidth − 左栏 − dock ≥ 360`（推导：`#content` 是 `flex:1`+`overflow:hidden`，宽度即剩余空间；`*{box-sizing:border-box}`，memoria.css:2）。**前提**：仅当 `#main.clientWidth ≥ 左栏生效宽 + 360` 时该保底成立；再窄下去 dock 保持隐藏、`#content` 只剩更少的空间（左栏行为未改，不参与让位） |
| 空间不足自动隐藏（`.-agent-dock--auto-hidden`） | app.css:361-373；agent-panel.js:259-281、362-380 | `available < 16rem` 时加 `.-agent-dock--auto-hidden`（视觉同手动折叠：`width:0 !important` / 隐藏拖拽柄 / 去左边框），与 `.-agent-dock--collapsed` **互斥**。它是**派生态**：**不写盘、不改用户期望值**，窗口变宽即自动还原到期望宽度（无需用户再点）。浮动按钮的 title 改为 `agent.dockNoSpaceTitle`（「空间不足：先折叠左栏…」）以区别于手动折叠的 `agent.dockExpandTitle`（agent-panel.js:228-257）。**此时点浮动按钮/顶栏按钮不会展开**：`setDockCollapsed(false, …)` 检测到自动隐藏即 `showFlashInfo(agent.dockNoSpace)` 后返回，**不挤压文档区**、也不写盘（agent-panel.js:362-380；`toggleDock()`:283-285 把"隐藏态点击"统一解释为"请求展开"，故自动隐藏时点到的是"请求展开"分支而非折叠分支） |
| 生效宽度的重算时机 | agent-panel.js:1216-1228 | **ResizeObserver 为主**：`#main`（视口/`uiScale` 改根字号）+ `#-sidebar`（左栏宽度拖拽、折叠/展开）+ dock 自身（浮动按钮跟随）。另接 `window.resize`（`uiScale` 由 display-settings.js:97 显式派发）。折叠/展开与顶栏按钮走 `applyDockLayout()`（agent-panel.js:375）；dock 拖拽过程中逐帧 `applyDockLayout()`（:355）；语言切换由 `MemoriaI18n.addRefresh` 重绘按钮 title（:1233-1240）。**未**在 `app.js` 的左栏拖拽/折叠代码里挂钩子（左栏行为零改动） |
| 布局持久化 | agent-panel.js:293-304、382-393 | 键在 `config/ui-settings.json` 的 `layout` 段：`layout.agentDockWidth`（数字，**rem 数值**，如 `22`——**期望宽度**）与 `layout.agentDockCollapsed`（bool，**只记手动折叠**）。启动 `hydrateDockLayout()` 读回；拖动结束/手动切换折叠时 `saveDockLayout()` 落盘。⚠️ **自动收缩/自动隐藏一律不回写盘**（这是本轮硬规则：窗口临时变窄不会污染用户期望值）。⚠️ **必须先读旧 `layout` 再整体写回**：后端 `save_ui_settings` 是**顶层浅合并**（`storage/ui_settings.py:58-75`），直接传 `{layout:{agentDockWidth}}` 会把整个 `layout` 换掉、**抹掉 `layout.sidebarWidth`**（左栏宽度）——agent-panel.js:293-304 的 `get_ui_settings` → 合并 → `save_ui_settings` 就是为规避它（harness 已断言 `sidebarWidth` 保持不变；M1 收尾新增的顶层 `agent` 段偏好走同套路的 `saveAgentPrefs()`:311-322） |
| 层级关系 | app.css:387-392；对比 app.css:4533、2448、2519 | dock 在 `#main` 的**普通流**内、自身**无** `z-index`（它在文档区内，不可能盖住任何浮层）；折叠按钮虽然 `position:fixed`，但只给 `z-index:90`（app.css:391），**低于** `.-modal` 的 1000（app.css:4533）⇒ 弹窗、搜索面板(9000，app.css:2448)、右键菜单/格式下拉(10050)、`#-flash-host`(12000，app.css:2519) 都会盖住它。`#status-bar`（index.html:279）在 `#main` **之外**，与 dock 不重叠（harness 实测 876×271 视口：`#status-bar` top=249、dock 底=249，相接） |
| 顶部操作条 | index.html:227-236；app.css:413-448 | `#agent-model-label`（模型名 + 关网时的「出网已关」尾注，由 `applyConfigToForm()`:802-830 写入）+ `#agent-net-toggle`（checkbox，文案「出网」）+ `#agent-settings-toggle`（`.-config-btn`，带 `aria-expanded`/`aria-controls`） |
| 折叠设置区 | index.html:237-258；app.css:449-493；agent-panel.js:1150-1157 | 默认 `.hidden`；点「设置」按钮 `classList.toggle("hidden")` 并同步 `aria-expanded`（**就地折叠，不弹窗**）。字段：`#agent-base-url` / `#agent-model` / `#agent-api-key`(type=password) / `#agent-timeout` + `#agent-save-config`；底部 `#agent-config-path` 显示 `config/agent.json` 相对路径（`agent.settings.path`）。**2026-09-17 修复**：加 `max-height: min(24rem, 45vh)` + `overflow-y:auto`（app.css:456-457）——此前无上限，矮窗口展开后「保存」按钮被顶出可视区且无法滚动（harness 271px 高窗口下现已可滚到） |
| 密钥处理 | index.html:248；agent-panel.js:815-822、861-885 | 输入框**永不回显**密钥：保存后清空，已存密钥只作 placeholder（`agent.settings.apiKeySet` 带 `{masked}`，掩码由后端 `mask_secret` 生成）；留空即「不修改」（后端 `save_config` 同语义，`llm/config.py:309-313`）；保存请求仅在输入非空时带 `api_key` |
| **历史会话下拉**（M1c；M1 收尾加删除按钮与 `capped` 标记） | index.html:259-263；app.css:495-533；agent-panel.js:575-683 | 独立一行 `.-agent-history`（label「历史」+ `<select id="agent-history">` + **M1 收尾新增**的 `#agent-history-delete`，见下两行）。填充 `agent_sessions_list`（按修改时间倒序、最多 30 条）；首个选项恒为「（新会话）」(值 `""`)，其余为 `{preview}（{n} 轮）`；后端 `capped:true` 的会话（turn 计数被 2 MiB 扫描上限截断）在该项后追加 `agent.history.capped`（「（已截断）」）。**选中某条 → `loadSession()` 调 `agent_session_load` 灌进消息区并把 `sessionId` 设为它（下一句即续聊）；选「（新会话）」= `clear()`**（重置 `sessionId`，旧会话仍在磁盘上、留在列表里）。空列表/未开库 ⇒ `disabled` + `agent.history.empty` 占位。刷新时机：`init` / 展开 dock / 每次提问结束 / 切换知识库 / 删除后 / 语言切换（就地重绘，不重新请求）。**列表与载入两个 RPC 只读、不写盘**（口径见 [10 篇 §2.15](./10-data-layout-and-host-embedding.md)） |
| 消息区 | index.html:264；app.css:534-628；agent-panel.js:402-472 | `#agent-messages`（`role="log"`、`aria-live="polite"`）：用户气泡 `.-agent-msg--user`（主题色底、`max-width:85%`、`align-self:flex-end` 靠右）/ 助手气泡（`--bg-secondary`、占满栏宽）；助手正文把 `路径.md:行号`（含反引号包裹）渲染成 `.-agent-anchor` 可点节点（`linkify()`:402-418），末尾另附 `.-agent-source` 来源条（后端 `anchors` 数组，`sourcesEl()`:452-472）；历史会话载入的 assistant 气泡同样带锚点（后端按轮归属）。**M1 收尾新增**「（已停止）」标注：`messageEl()`:420-450 在 `rec.stopped` 时追加 `.-agent-msg-note.-agent-stopped`（次要色，app.css:587-589），与错误条（同基类、错误色）区分。字号按 dock 宽度定为 **0.8125rem**（= 正文基准，app.css:558），此前挤在左栏时是 0.75rem |
| 锚点跳转 | agent-panel.js:1135-1143 → app.js:1403-1520 | 点锚点调门面 `openFile(file, {navSource:"agent", lineHint})`；**`kpId` 优先于 `lineHint`**（app.js:1505-1517）——本面板只用 `lineHint`（锚点是行号而非 KP）；未打开的文件会经 `load_document` 正常打开并高亮该行 |
| 输入区 | index.html:265-274；app.css:629-668；agent-panel.js:1187-1201 | `#agent-input` 多行 `textarea`（Enter 发送 / Shift+Enter 换行，`isComposing` 期间不发送以兼容中文输入法）；三按钮：`#agent-send`（primary）/ `#agent-stop`「停止」（生成中才显示，**真取消**，见下）/ `#agent-clear`（`margin-left:auto` 靠右，清空即开新会话）；`#agent-status` 状态行（`aria-live="polite"`）显示「生成中… Ns / 用量 / 会话 id / 错误 / 已停止」 |
| 伪流式与等待计时 | agent-panel.js:96-98、924-933、935-951、953-1131 | `agent_ask_start` 提交后每 **250ms** 轮询 `agent_ask_poll(job_id, cursor)`，`delta` 追加进当前助手气泡（`applyDelta()`:924-933 流式期间用 `textContent` 追加、`finalizeMessage()`:935-951 定稿时再 linkify 重绘）；`done` 时以后端 `answer` 覆盖流式累积文本（loop 每轮以当轮文本覆盖 `answer`，故工具轮前言不在最终答案里）。**M1c 起状态行带计时**：`startWait()/tickWait()/stopWait()`（554-573）每秒把状态行刷成「生成中… Ns」（`agent.status.thinking` + `agent.status.elapsed`），结束/出错/停止/清空/超时/换库一律 `stopWait()`。**M1 收尾起增量是真流式**：`llm/providers/openai_compatible.py:296-311` 改用 `response.read1(_READ_SIZE)`（`HTTPResponse.read(n)` 在「无 Content-Length / Connection: close」的 SSE 上会阻塞到 EOF，实测一次 3.6s 的流只在结束时返回一整块 ⇒ 增量投递与"取消立即停止消费"都失效；`read1` 至多触发一次底层读，SSE 帧一到即返回）。**M1 收尾后**确定性连接失败（连接被拒 / DNS / 证书）在后端**立即失败**（面板路径约秒级，不再是最长 ~28s），重试与失败分类见 [10 篇 §2.16](./10-data-layout-and-host-embedding.md) |
| 「停止」（**真取消**，M1 收尾语义变更） | index.html:269；agent-panel.js:1068-1101；`services/agent/loop.py:72-100` | 旧「忽略本次」的"丢弃结果"语义已废除。点停止顺序：① `epoch += 1` + `job = null` ⇒ 立即停止轮询、作废在飞回调；② 把**已生成的部分文本**留在当前助手气泡上并标注「（已停止）」（`agent.stopped`，`.-agent-msg-note.-agent-stopped` 次要色，非错误色）；③ 调 `agent_ask_cancel(job_id)` ⇒ 后端置 `CancelToken`（`threading.Event`）：`AskJob.cancel()` **立即**把作业收敛为 `done` + `stop_reason="aborted"`（`answer` = 当时已投递片段）并**释放单飞 busy**，工作线程在下个检查点（每轮迭代前 / 流式逐事件 / 每次工具调用后，`loop.py:287-291、240-241、371-374`）观察到取消后 `break` 并 `stream.close()`（关闭底层 HTTP 响应、不再收完）；`loop/end` 以 `stop_reason="aborted"` 正常落盘，**不抛异常**；④ 取消 RPC 返回后才放开发送按钮 ⇒ **停止后立刻可再提问、不会撞 `busy`**（实测停止往返 0.06s，见 §7 验证段）。取消是**协作式**的：阻塞中的 socket 读不会被抢占，最长等一个分片的到达 |
| 「清空对话」（生成中亦可用，M1 收尾起**顺带取消**） | agent-panel.js:1103-1131 | 清空气泡 + `sessionId = null`（= 开新会话；旧会话已在磁盘上、留在历史列表）+ 把偏好 `agent.lastSessionId` **置空**。**生成中点它也作废在飞结果**（同样 `epoch += 1` 并 `job = null`），并**顺带调 `agent_ask_cancel(job_id)`**（M1 收尾：此前只丢弃结果、后端仍烧 token）；等取消返回后才放开发送按钮，故清空后立刻再提问不会撞 `busy`。`#agent-clear` 生成中**不禁用** |
| 世代号（epoch）作废机制 | agent-panel.js:150、978、988、1006、1013、1032、1080、1113 | 模块级 `epoch` 每次提问递增（`const myEpoch = ++epoch`，并记进 `job.epoch`）；提交与轮询回调均先比对 `epoch === myEpoch`，不等即 `return`（丢弃响应、不写回任何状态）。「清空对话」「停止」递增 `epoch` ⇒ 在飞结果一律作废；作废后新提问用新 epoch 正常写回 |
| 删除会话（M1 收尾，**产品首次允许写知识库**） | index.html:262；app.css:528-533；agent-panel.js:581-602、764-797 | 历史行末的 `#agent-history-delete`（`.-agent-history-delete`，未选中具体会话时 `disabled`）；删除的是**当前下拉选中**的那条（`syncDeleteButton()`:581-592 维护文案与禁用态）。**两次点击确认**：首点文案变「再点一次删除」（`agent.history.deleteConfirm`）并起 3s 定时器，3s 内未再点即复位为「删除」（`resetDeleteArmed()`:595-602）；再点才真删（**不弹窗**）。调 `agent_session_delete(session_id, kb_path)`（只允许删 `<kb>/.memoria/agent/sessions/<id>.jsonl`）；删的是当前会话 ⇒ 复用 `clear()` 回到「新会话」态（清空气泡 + 偏好置空），随后刷新历史列表并 flash「会话已删除」 |
| 恢复上次会话（M1 收尾） | agent-panel.js:311-335、734-760、1243-1249 | 磁盘偏好 `config/ui-settings.json` 的**顶层** `agent.lastSessionId`（提问成功 / 载入 / 恢复时写，清空时置空）。**面板打开**（`init` / dock 展开）或**切换知识库**（`app.js` 在 `initKb:452` / `openKbAt:560` / `closeKb:598` 三处调 `MemoriaAgentPanel.onKbChanged()`，共 3 行）时，若该会话文件**仍存在**即 `agent_session_load` 自动载入并设为当前会话（下一句即续聊）；不存在/非法 ⇒ **静默忽略**（不报错、不提示，`loadSession(id, silent=true)`）。同一（库, id）只尝试一次（`restoredKey` 幂等，`restoreLastSession()`:734-743）。写入走 `saveAgentPrefs()`:311-322——**先读旧 `agent` 段再合并写回**（后端 `save_ui_settings` 顶层浅合并，绝不覆盖 `layout`） |
| 换库 / 关库 | agent-panel.js:1014-1024、661-683、747-760 | 轮询期间 `state.kbPath` 变化 ⇒ 丢弃本次结果并提示（`agent.status.dropped`），不把 A 库的答案留在 B 库的面板里；同时作废 `sessionId` 并刷新历史列表（`sessionKb` 与当前库不一致时也在 `refreshHistory()` 里作废，避免把 A 库的会话续到 B 库）；M1 收尾新增 `onKbChanged()`:747-760 由 `app.js` 在开库/关库处显式调用（清会话态 + 重试恢复上次会话） |
| 发送前置 | agent-panel.js:953-1003 | 未开库 / 未输问题 / `enabled=false` 时**就地报错**（状态行转红 + flash 卡片），不静默失败；前端已 `busy` 时直接返回不重复提交（后端仍有单飞约束）；`enabled=false` 时发送按钮 `disabled` 且带 title（`renderComposer()`:832-840） |
| 错误呈现 | agent-panel.js:104-130、499-529、861-903、1048-1052 | 后端 8 个 agent RPC 的错误按**稳定 code** 映射文案（`ERR_KEYS`:104-130，M1c 新增 `unknown_session`/`session_failed`，M1 收尾新增 `cancel_failed`）。**具体 code**（`busy`/`no_base_url`/`net_disabled`/`unknown_job`/`unknown_session`…）只显示本地化文案；**兜底 code**（`ask_failed`/`config_error`，`GENERIC_CODES`:132）额外拼后端原文——LLM 失败的真实原因（传输/认证/HTTP/确定性连接失败）只存在于 `error` 文本里；未登记 code 一律回显原文。flash 卡片同理（标题=本地化、详情=原文，app.js:344-358） |
| 语言切换 | agent-panel.js:1233-1240 | 静态节点由 `MemoriaI18n` 刷新；动态消息/状态行 + 历史选项（含禁用态占位）+ 删除按钮文案（含二次确认复位）+ 折叠按钮的 title/aria（含三态文案）由 `MemoriaI18n.addRefresh` 重绘（与 kb-check.js 同套路） |
| 默认宽度与三栏挤压（实测） | 实测（harness，2026-09-17） | 见下方「dock 实测尺寸」段与「文档区最小宽度保护」行 |

**dock 实测尺寸（headless Edge + harness，2026-09-17 第三轮复测；左栏宽度由 `layout.sidebarWidth=301` 预置，期望宽度 22rem）**

| 视口 | `#-sidebar` | `#-agent-dock`（生效） | `#content` | 说明 |
|---|---|---|---|---|
| 1576×668 | 301 | **352**（= 期望 22rem） | 923 | `available = 1576−301−360 = 915 ≥ 352` ⇒ 按期望；`#main` 无溢出 |
| 1300 / 1100 / 1020 | 301 | 352 | 647 / 447 / **367** | `available ≥ 352` 时 dock 保持期望宽度，让位的先是文档区的**余量** |
| 1000 | 301 | **339.03** | **360** | `available = 339` ⇒ 开始让位，文档区恰好触底 360 |
| 980 / 950 / 930 / 920 | 301 | 319.03 / 288.95 / 268.95 / 259.03 | 360 | 逐级让位（增量 = 视口收窄量） |
| 917 | 301 | **256**（= 16rem 下限） | 360 | `available = 256`，到此为止（不再更窄） |
| 916 | 301 | **0（自动隐藏）** | 615 | `available = 255 < 16rem` ⇒ 整条 dock 临时隐藏；content 回弹 |
| 876×271 / 492×179 | 301 | 0（自动隐藏） | 575 / 191 | **旧行为（`#content`=0 + dock 被 `#main` 的 `overflow:hidden` 裁掉）已消除**；492 宽时 `#content` 191 < 360 属"前提不成立"（左栏 301+360 > 492），dock 仍不参与挤压 |
| 720×600（**启动即窄**） | 301 | 0（自动隐藏，首帧即生效） | 419 | hydrate 读回期望 22rem 后立刻按 `available` 收成隐藏；`#agent-dock` 内联 `width` 为空、由 CSS 类归零 |
| 1200×668，左栏**拖到最宽 480** | 480 | 352 | 368 | `available = 360 ≥ 352` ⇒ 文档区余量先让，dock 仍 22rem |
| 1100×668，左栏 480 | 480 | **260** | 360 | `available = 260` ⇒ dock 让位到 260 |
| 1050 / 1000 / 900 / 840，左栏 480 | 480 | 0（自动隐藏） | 570 / 520 / 420 / **360** | `available ≤ 210` ⇒ 隐藏 |
| 820 / 800，左栏 480 | 480 | 0（自动隐藏） | 340 / 320 | **前提不成立**（左栏 480+360 > 视口）⇒ 文档区必然 < 360；dock 仍不参与挤压（`#main.scrollWidth == clientWidth`） |
| 1200×668，左栏 301，**手动把 dock 拖到极限** | 301 | **539.03** | 360 | 上界 = `available`（539）< 34rem（544）⇒ 拖不破 360；拖拽中实时生效、**松开鼠标才落盘** |

> 推论（`uiScale=1`、左栏默认 17.5rem=280px 时）：应用最小窗口 900×600 下 `available = 900−280−360 = 260 ≥ 16rem` ⇒ dock 仍可见（约 16.25rem）；但左栏一旦宽于 ≈283px，900px 宽窗口就会触发 dock 自动隐藏。见 §7 待拍板项。
>
> 上一轮（2026-09-17 第二轮）在 876×271 视口做出的「设置区可滚到保存按钮」断言，在本轮行为下**需在 ≥917px 宽窗口才可复现**（876 宽时 dock 已自动隐藏）——那是**行为变更的副作用，非缺陷**：设置区自身的 `max-height + overflow-y:auto`（app.css:456-457）未改。

后端 8 个对话 RPC（`agent_get_config` / `agent_save_config` / `agent_ask_start` / `agent_ask_poll` /
`agent_ask_cancel` / `agent_sessions_list` / `agent_session_load` / `agent_session_delete`；
中间两个为 M1c 新增的**只读**会话历史，2026-09-18；`agent_ask_cancel` 与 `agent_session_delete`
为 **M1 收尾（2026-09-18）新增**——前者是真取消，后者是**产品首次允许写知识库**（仅限会话目录））、
续聊语义（`agent_ask_start` 的**追加可选参数** `session_id` ⇒ 后端按会话回放历史）、
`agent_ask_poll` 新增 `cancelled` 字段与 `agent_sessions_list` 新增 `capped` 字段（**只增不改**）、
配置落点 `config/agent.json`、偏好落点 `config/ui-settings.json`（`layout` 段 + **新增顶层 `agent` 段**）
与会话事实源 `<kb>/.memoria/agent/sessions/*.jsonl`
见 [10-data-layout-and-host-embedding.md](./10-data-layout-and-host-embedding.md) §2.15。


### 2.5 文档区

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

### 2.6 知识点面板（仅定位）

`#sidebar-kp-block`（index.html:137-147）位于左侧栏 `#sidebar-body-split` 的**下半区**，与导航面板以 `#sidebar-nav-kp-resizer` 分隔（见 §2.3）。内部为 `.sidebar-toolbar.-kp-toolbar`（标题「知识点」+ `#kp-count` + `#btn-config`「配置」+ `#btn-kp-new`「新建」）与 `#kp-list`（`.-panel -kp-panel`）。行为细节（KP 列表、hover、弹窗三 Tab、范围编辑）归 [05-knowledge-points.md](./05-knowledge-points.md)。

### 2.7 状态栏

| 项 | 证据 | 说明 |
|---|---|---|
| 容器与左段 | index.html:279-283；memoria.css:604-615 | 高 1.375rem、主题蓝底、白字、`flex-shrink:0`；`#status-info` 为 `flex:1` 单行省略（memoria.css:614），初值「就绪」（`app.status.ready`） |
| 右段统计块 | app.js:281-333；i18n/zh-CN.js:485-490 | 由 `renderStatusStats()` 以 ` · ` 连接：① 检查统计（有 error/warn 时，文案取自 kb-check.js 的 `statsChunk`，并打 `data-kb-check="1"`）；② 全库检查通过（`check.stat.pass`，且无文件级统计）；③ 图谱待办 warn 数；④ 当前文件统计 `app.stat.kpLines`「{kp} KP · {lines} 行」，若有 sidecar 问题再追加 `app.stat.errors/warnings` + `app.stat.sidecar`；⑤ 图谱审计问题（文件级优先，其次全库） |
| **Agent 用量格** `#status-agent` | index.html:282；app.css:2138-2145；agent-panel.js:169-172、560-661、1156-1161、1308-1315 | **本轮（2026-09-18）新增，为 `#status-stats` 之后的独立 span**（不与统计块共用节点，**`#status-stats` 的语义与点击行为完全不变**）。显示**最近一轮**的紧凑摘要：`↑8.7k ↓233 · 命中 62%`（`↑` = 输入 `prompt_tokens`、`↓` = 输出 `completion_tokens`；数字 ≥1000 用 k 缩写一位小数）。**命中率未知时省略该段**（绝不显示 0%）；`title`（悬停）给计费拆分多行文本：本轮输入/输出/合计、**命中/未命中/命中率**、是否估算、**本会话累计**（含命中的拆分）。点击 ⇒ `MemoriaAgentPanel.open()` 展开右侧对话面板（`open()` 内部按空间不足规则处理，**不新增弹窗**）。**无 agent 活动时该 span 为空**（`:empty { display:none }`，不占位）。数值来源：`agent_ask_poll` 的 `usage`（含 `cache_read_tokens`/`cache_miss_tokens`）；本会话累计由面板**自行累加**（不新增 RPC 轮询），「清空对话」/载入历史会话/切换知识库时复位（历史会话视图不含 usage，无法回算旧用量） |
| 样式与点击（统计块） | app.css:1732-1755；app.js:12219-12227 | `.-stat-error` 红、`.-stat-warn` 黄、`.-stat-ok` 次色；命中图谱审计时 `#status-stats` 加 `.-status-clickable`（黄 + 下划线 + 指针）；点击时 `data-kb-check` 优先 → 检查弹窗，否则 `data-graph-audit-goto` → 跳到首个图谱审计问题（**本条只描述 `#status-stats`；`#status-agent` 见上一行**） |

### 2.8 闪烁提示（flash，瞬时反馈）

| 项 | 说明 |
|---|---|
| 宿主 / 位置 / 层级 | `#-flash-host`（index.html:288）；fixed，`left:50%`、`bottom:2rem`，纵向列；`z-index:12000`（app.css:2202-2213）⇒ **高于弹窗**，弹窗内也能看见 |
| 时长 / 并发 | 默认 3800ms + 280ms 淡出（app.js:347、354-356）；可多条堆叠（host 为 flex 列，追加节点） |
| 变体 / 入口 | `.-flash-error` 红边 + 标题/详情两行（app.css:2215-2227）、`.-flash-info` 绿边（app.css:2233-2245）；`showFlashError(msg, detail)`（app.js:344）、`showFlashInfo(msg)`（app.js:360），两者均已挂在 `MemoriaApp` 门面上供子模块调用 |
| 与底栏的分工 | `setStatusError(msg, detail)` = `setStatus` + `showFlashError`（app.js:374-377）⇒ 底栏 + 卡片**双写**；`setStatus(msg, undefined, {error:true})` 只把底栏转红、不弹卡片；「导入」未开库是唯一**只弹卡片、不写底栏**的入口（import-flow.js:44） |

> **2026-09-16 收敛为单通道**：原先另有一个 `js/toast.js` 轻提示组件（`#-toast`，z-index 30000），其唯一调用点（检查弹窗「复制报告」）与 flash 卡片**同文案双通道**，底部会叠两个一模一样的框。该模块、`#-toast` 节点与其 CSS 已删除，瞬时反馈一律走 flash 卡片（成功绿边 / 失败红边）。

### 2.9 弹窗与层级

通用结构（index.html:290-436 共 9 个）：`.-modal[.hidden]` > `.-modal-backdrop` + `.-modal-box[变体类]` > `.-modal-header`（标题 + `.-icon-btn` ×）/ `.-modal-body` / `.-modal-footer.-btn-bar`。

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

### 2.10 缩放与字号

| 变量 / 设置 | 写入位置 | 作用范围与取值 |
|---|---|---|
| `--preview-font-size` / `--editor-font-size` | `#preview`、`#editor` 的 inline style（display-settings.js:80-85） | 预览正文与 h1–h3 标题（app.css:3479、3511-3513）、源码/分栏区（app.css:3464）；12–28px，默认 14（display-settings.js:12、16-17），两者同值 |
| `--lineno-ch` | `#editor` inline style（app.js:1561-1564） | 源码行号列宽，按总行数位数自适应 |
| `uiScale` | `document.documentElement.style.fontSize = 16×scale px`；等于 1.0 时清空恢复（display-settings.js:87-98） | **全界面**：样式表尺寸/字号绝大多数用 `rem`，故整体等比缩放；改完主动派发一次 `resize` 让监听方重算（display-settings.js:97）；0.8–1.5、步长 0.1（display-settings.js:18-20），默认 1.0 |
| 持久化 | `localStorage["-display-settings"]`（display-settings.js:9、40-46）+ 磁盘 `ui-settings.json` 的 `display` 段（display-settings.js:114-118） | 启动 `hydrateFromDisk` 时"本地优先、磁盘仅作种子"（display-settings.js:66-77、120-138） |
| 快捷键 | `Ctrl+=` / `Ctrl++` 放大、`Ctrl+-` 缩小、`Ctrl+0` 复位（app.js:12201-12217） | 步进 ±0.1 并被夹在区间内（display-settings.js:147-157）；**无按键目标过滤**（输入框内同样生效） |

> 注：`index.html:279-280` 注释称"浮层放 `#app` 外以免受 `#app` 的 zoom 影响"，但当前实现改的是**根元素 `font-size`**（display-settings.js:92-93），`rem` 会级联到 `body` 下所有浮层，故 flash 卡片的间距实际**会**随缩放变化——注释与实现已不一致。**同一原因适用于 `#-agent-dock` 的宽度**：它以 rem 计量（agent-panel.js:140），故 `Ctrl+=` 缩放时 dock 会跟着变宽/变窄（见 §2.4「宽度单位是 rem」）。

## 3. 交互流程

**3.1 启动 → 主界面**：`MemoriaBridge.onReady` 后统一 boot（导入流 → 工具条搜索 → 图片 → 检查 → KB 智能体 → 文件树 → **对话面板** → `initKb()` → `initWindowChrome()`，app.js:12848-12862）；`initWindowChrome` 先取 `get_window_chrome()`，失败则三键保持隐藏（window-chrome.js:289-293），成功则写标题/版本并判定 frameless（window-chrome.js:295-313）；`initKb()` 有路径时显示路径指示、清空导航栈与标签页、刷新文件、加载链接目标与图谱、跑一次完整检查并打开首选文件（`navigation-demo.md` → `mdp.md` → 首个文件，app.js:476-480），无路径则显示欢迎页、隐藏路径指示、状态栏写 `Memoria`（app.js:481-485）。

**3.2 顶栏「文件」菜单**：点 `#btn-file` 翻转 `#file-menu` 的 `hidden`、同步 `aria-expanded`、收起时一并隐藏二级面板（app.js:12092-12098）；点「打开最近」显示二级面板并异步拉列表（app.js:12181-12185）；关闭有三条路径——点菜单外部（app.js:12099-12104）、按 Esc（app.js:12105-12107）、点任意菜单项（各项 handler 首句都先 `closeFileMenu()`）。

**3.3 侧栏页签**：点 `[data-sidebar-tab]`（app.js:12591-12593）→ `setSidebarTab`（app.js:1233-1258）：无对应 `[data-sidebar-view]` 的悬空页签名（如存量的 `"agent"`）先回退 `files`（app.js:1234-1236），再写 localStorage、刷新按钮 `.active`/`aria-selected`、切换 `[data-sidebar-view]` 的 `.hidden`；随后清图谱 hover、启停对应图谱视图、按需重算上下分栏比例。

**3.3.1 右侧对话停靠栏**：顶栏 `#btn-agent` 或浮动 `#agent-dock-collapse-btn` → `toggleDock()`（agent-panel.js:259-261）→ `setDockCollapsed()`（agent-panel.js:307-325）：切 `.-agent-dock--collapsed` 类、同步 `aria-pressed`/`aria-expanded`/字形、状态落盘在 `layout.agentDockCollapsed`（`localStorage` 无关）、**展开时**额外 `refreshConfig()` 拉一次端点配置（与旧版「切到对话页签即拉配置」同语义）；**空间不足自动隐藏态（`.-agent-dock--auto-hidden`）下点这两个入口不会展开**——只弹 `agent.dockNoSpace` 提示并保持隐藏（不写盘、不挤压文档区，见 §2.4）。拖拽 `#agent-dock-resizer` → 实时改宽（agent-panel.js:282-306，上界受 `available` 约束）、`mouseup` 才落盘；期望/生效宽度与自动隐藏规则见 §2.4。

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
| `view.*` / `edit.*` | 视图模式、编辑模式、格式栏、块编辑栏 | `view.toggleAria`、`view.source|preview|split`、`edit.mode.aria|title|browseTitle|btn`、`edit.fmt.aria|boldTitle|…`、`edit.block.aria`（648-679） |
| `search.*` | 搜索范围、占位符、状态与结果文案 | `search.scopeKb`、`scopeFile`、`ph`、`title`、`statusSearching`（527-536） |
| `agent.*` | 右侧「对话」停靠栏（**顶栏按钮文案复用 `agent.tab`** + dock aria/折叠/拖拽 title + 出网开关 + 端点设置 8 字段 + 输入占位 + 角色两态 + 来源 + 状态与错误） + **状态栏用量格** | `agent.tab`（= 顶栏 `#btn-agent` 文案）、`agent.btnTitle`、`agent.dockAria`、`agent.dockCollapseTitle`、`agent.dockExpandTitle`、`agent.dockResizeTitle`（2026-09-17 新增 5 键）、`agent.dockNoSpaceTitle` / `agent.dockNoSpace`（同日第二轮新增 2 键：空间不足自动隐藏的三态文案）、`agent.net.label`、`agent.settings.apiKeySet`、`agent.status.usage`、`agent.err.no_base_url`、**`agent.statusBar.*`**（2026-09-18 本轮新增 9 键：`span`/`spanCache`/`line`/`cache`/`cacheUnknown`/`estimated`/`session`/`sessionCache`/`hint`，供状态栏 `#status-agent` 的文本与多行 `title`）（zh-CN.js:575-663） |
| `dlg.*` / `check.*` / `kbAgent.*` / `import.*` | 各弹窗标题与按钮 | `dlg.kpTitle`、`dlg.configTitle`、`check.modalTitle` 等 |

完整清单与未迁移中文行的登记规则见 [../i18n-inventory.md](../i18n-inventory.md)；语言系统维护规范见 [../../conventions/i18n.md](../../conventions/i18n.md)。

## 5. 边界与已知坑

1. **弹窗层级低于多个浮层**：`.-modal` 为 `z-index:1000`（app.css:4506），低于搜索面板 9000、右键菜单 10050、flash 卡片 12000、颜色选择器遮罩 20000、图片灯箱 99999。flash 卡片刻意高于弹窗（弹窗会遮住底栏，反馈只能靠它，见 §2.8），代价是**任何 1000 以上的浮层都能盖住弹窗**。
2. **没有"只能开一个弹窗"的中央约束**：各弹窗独立管理 `hidden`，多个弹窗可同时可见；唯一的"统一判定"是 F2 的全局检查（file-tree.js:453-457）。
3. **禁用态并不统一**：后退/前进用 `disabled`；构建仅在执行中 `disabled`；检查/刷新/设置/对话 无禁用，改为点击后提示前置条件（`openKbFirst` / `openFileFirst`）。**这类提示分两档**：`setStatusError` = 底栏整行转红（`.-status-error`，app.css:1777-1787）+ 底部浮层卡片；`setStatus` = 底栏普通色。当前「硬前置」类（构建/检查/插入图片/搜索/创建智能体）都走**前者**；**导入**是唯一只弹悬浮卡片、**不**写底栏的入口（直调 `showFlashError`，见 08 篇 §2.1）。集成方判断"能否操作"需按 §2.2 表逐项判，不能只看是否灰化。
4. **侧栏宽度是两套口径**：CSS 默认 17.5rem / 最小 11.25rem（app.css:124-125），JS 拖拽夹在 180–480px（app.js:12104）；非 100% 缩放时 rem 与 px 不一致，会出现"能拖到比 CSS 最小值更窄/更宽"的观感。
5. **`Ctrl+= / Ctrl+- / Ctrl+0` 无目标过滤**：在搜索框、弹窗输入框内按同样触发整界面缩放（app.js:12203-12216 未检查 `e.target`）。
6. **顶栏拖拽靠"选择器黑名单"**：`NO_DRAG_SELECTORS`（window-chrome.js:118-119）含 `.toolbar-actions`，故 `#btn-agent` 的点击不会被拖拽 mousedown 吞掉（harness 实测点击生效）；但**未**包含 `.toolbar-left` 内部元素，故品牌区整体可拖。新增顶栏控件若不在黑名单内，会被拖拽的 mousedown 吞掉点击。
7. **块编辑栏与格式栏互斥**：二者共用 `#editor-header` 同一位置；若在块编辑中切换视图，恢复依赖 `_restoreToolbar()`（edit-handler.js:1545-1550），未被调用则格式栏会一直隐藏。
8. **`#preview-status` 的 `.warn` 态样式存在但需渲染层主动加类**（app.css:4080）；未打开文件时该节点保持 `hidden`（index.html:212）。
9. **`theme/memoria.css` 含大量与当前 DOM 不符的历史选择器**：`#sidebar`、`.toolbar-center`、`#group-tabs`、`.mode-switch`、`.file-grid`、`.file-card` 在 `index.html` 与 `js/**` 中均无对应节点（已检索确认）。不要把它里面的 `#sidebar { width: 23.75rem }`（memoria.css:251-253）当成左侧栏实际宽度——实际是 `#-sidebar { 17.5rem }`（app.css:124）。
10. **`uiScale` 的注释已过时**：见 §2.10 末尾（index.html:279-280 vs display-settings.js:92-93）。
11. **右侧 dock 是"左栏/文档区/dock 三栏，dock 让位"**（2026-09-17 第二轮加入**文档区最小宽度保护**后）：`#-sidebar`(17.5rem) 与 `#-agent-dock`(22rem) 都是 `flex-shrink:0`，`#content` 名义上 `flex:1`、实际宽度就是剩余空间。现在 JS 每次布局变化都会算 `available = #main.clientWidth − 左栏 − 360`，把 dock 的**生效宽度**压到 `min(期望, min(34rem, available))`；`available < 16rem` 时整条 dock 临时自动隐藏（`.-agent-dock--auto-hidden`）。故 `#content ≥ 360` 在 `#main.clientWidth ≥ 左栏 + 360` 时成立；**再窄下去**（左栏本身已占满）`#content` 会 < 360，但 dock 不会把 `#main` 撑出溢出——`#main` 的 `overflow:hidden` 不再裁掉 dock。应用最小窗口 900×600（§2.1）下不会触发自动隐藏。
12. **两种"隐藏"语义不同、类名不同**：手动折叠 `.-agent-dock--collapsed`（**落盘** `layout.agentDockCollapsed=true`，只有用户再点才展开）；空间不足自动隐藏 `.-agent-dock--auto-hidden`（**派生态、永不落盘**，窗口一变宽就自动还原到期望宽度）。两者都只归零宽度、不 `display:none`（仍是布局节点、`clientWidth=0`，消息滚动位置与未发送文本保留、内部仍参与事件与 a11y 树）。自动隐藏时点浮动/顶栏按钮**不会展开**（会弹 `agent.dockNoSpace` 提示），因为强行展开必然挤压文档区。若集成方需要"完全不存在"，须自行 `hidden`/移除节点。
13. **「停止」现在是真取消（M1 收尾语义变更）**：`services/agent/loop.py` 三个检查点观察 `CancelToken`（`loop.py:287-291`、`240-241`、`371-374`），点「停止」后后端**停止消费模型流并关闭底层响应**（`stream.close()` → provider 的 `with closing(response)`），单飞 `busy` **立即释放**，故停止后**可以立刻再提问**；已生成的部分文本保留在助手气泡并标注「（已停止）」，`loop/end` 以 `stop_reason="aborted"` 落盘。**残留边界**：取消是**协作式**的——若工作线程正阻塞在一次 `read1()` 上，要等该分片到达才会返回；且被取消的一轮**不会**写入 `assistant/message`（会话文件里该轮只有 `user/message` + `loop/end(aborted)`），故刷新后该轮的部分文本不再显示（见 §7 待拍板项）。
14. **端点配置是全局的、不随库走**：`config/agent.json` 在程序目录（与 `ui-settings.json` 同级），一个进程一份；`enabled=false` 时发送按钮禁用（`disabled` + title），**不是**点击后报错。
15. **dock 的滚动边界**：只有 `#agent-messages` 滚动（`overflow-y:auto`、`flex:1`、`min-height:0`），头部、**历史行（M1c 加入）**与输入区是 `flex-shrink:0`，矮窗口下会挤压消息区（实测 876×271 + 设置展开：消息区只剩 20px 高）。展开态 dock 本身**不设** `overflow`（为保证左缘拖拽柄可抓，见 §2.4「拖拽柄」），折叠态才 `overflow:hidden`；设置区自身有 `max-height: min(24rem,45vh)` + `overflow-y:auto` 兜底（app.css:456-457，2026-09-17 修），但**头部、历史行与输入区仍无滚动兜底**——若未来往这几处加内容，需自行保证不撑破。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 顶层骨架 / 区域顺序 | index.html:47-283；theme/memoria.css:39-43、248、388-393、439-443 |
| `#toolbar` 尺寸与层级 / 顶栏元素顺序 | theme/memoria.css:46-60；index.html:48-107 |
| 拖拽区标记 / 排除选择器 | index.html:49、84、95、96、97；window-chrome.js:118-123 |
| 原生标题栏拖动 / 下拉还原 / 双击最大化 / 焦点回拉 | window-chrome.js:188-208、339-344、222-283、353-365、210-220 |
| 边缘缩放层 / 三键图形 / 最大最小尺寸 | window-chrome.js:36-116；app.css:1898-1977、1826-1896；window-chrome.js:14、300-301 |
| 窗口信息接口 / DWM 圆角 | src/memoria/presentation/api/ui.py:662-672；src/memoria/app/window_win32.py:166-180 |
| 文件菜单开合 / 最近列表渲染 | app.js:12085-12185、12134-12175 |
| 后退前进动作与按钮态 / Alt+←→ | app.js:406-412、6201-6213、12402-12410 |
| 刷新 / 构建 | app.js:12192-12197、1012-1049 |
| **顶栏对话开关** `#btn-agent` | index.html:82；agent-panel.js:1209-1214、228-257、283-285 |
| 侧栏页签 / 悬空页签回退 / 计数 / 宽度拖拽 / 收起展开 / 上下分栏 | app.js:1233-1258（回退守卫 1234-1236）、739-741、12103-12106、12134-12154、12158-12206；graph-settings.js:43-47、343、361、915-965、967 |
| **右侧「对话」停靠栏**（骨架 / 样式 / 模块 / 装配 / 持久化 / 最小宽度保护 / 历史会话 / 删除 / 恢复上次会话 / 停止与取消 / 等待计时 / 状态栏用量格） | index.html:225-274、276（历史行 259-263，删除按钮 262）；app.css:331-680（自动隐藏 361-373；历史行 495-533、删除按钮 528-533；消息区 534-628；「（已停止）」587-589；输入区 629-668）；js/agent-panel.js:1-1397（dock 控制 190-407、渲染 425-554、**状态栏用量格 169-172 / 556-660 / 1156-1161 / 1308-1315 / 1370**、会话历史/删除/恢复 693-915、提问与取消 1023-1249、装配 1268-1380）；app.js:12856（另见 452/560/598 三处 `onKbChanged` 钩子） |
| 侧栏与树样式 | app.css:123-323；app.css:3000-3048 |
| 图谱分组条显隐 | app.js:757-768 |
| 视图模式切换 / 编辑模式开关 | app.js:1567-1629；app.css:3453-3459；edit-handler.js:59-122 |
| 格式栏与块编辑栏互斥 | index.html:164-201；edit-handler.js:1009-1013、1545-1550 |
| 欢迎页与文档区切换 / 关库复位 | app.js:380-383、575-628 |
| 状态栏统计拼装 / 点击跳转 / 样式 | app.js:281-333、12219-12227；app.css:1732-1755 |
| **状态栏 Agent 用量格** `#status-agent`（本轮新增） | index.html:282；app.css:2138-2145；agent-panel.js:169-172（状态）、556-660（渲染/累加/复位）、1156-1161（轮询结束时写入）、1240（清空对话复位）、1308-1315（点击展开面板）、1370（语言切换重绘）；i18n/zh-CN.js:642-652（`agent.statusBar.*` 9 键，en.js 同段） |
| flash 卡片实现 | app.js:344-372；app.css:2202-2245 |
| 弹窗通用结构 / 拖动 / 动态弹窗 | app.css:4503-4567；app.js:12560-12625、706-728；file-tree.js:263-300 |
| 显示设置（字号 / 缩放）/ 缩放快捷键 | display-settings.js:11-20、79-98、140-157；app.js:12201-12217 |
| i18n 静态节点刷新 / boot 顺序 | i18n.js:91-115、154-169；app.js:12852-12866（`MemoriaAgentPanel.init` 在 12860） |

## 7. 未证实 / 待确认

- ⚠️ **本轮（2026-09-18：状态栏 agent 用量格 `#status-agent`）已取证 / 未取证**。已取证（headless Edge + CDP + harness `/rpc` + 本地假 SSE 端点，`MEMORIA_CONFIG_DIR` 与 KB 均指向临时目录；**11/11 PASS**）：⑧ 用量格文本 **`↑8.7k ↓233 · 命中 62%`**；⑨ `title` 含 `缓存：命中 5402 / 未命中 3311 / 命中率 62%` + `本会话累计…`；⑩ 无活动时为空且 `display:none`（不占位）；⑪ 折叠 dock 后点该格使其重新可见（`clientWidth 0 → 351`）；⑫ 会话 `loop/end.usage` 带 `cache_read_tokens`/`cache_miss_tokens`。详见 [10 篇 §7](./10-data-layout-and-host-embedding.md) 与 §2.7。**未取证**：悬停 `title` 在真机不同主题 / `uiScale` 下的换行观感、真实模型端点下的命中率数值。同类「桥在 document-start 就绪时后续模块 init 落空」的装载顺序脆弱点见 10 篇 §7（非本轮引入、未改代码）。
- ⚠️ 待确认（未能取证）：`#preview-status` 的填充逻辑与出现时机（app.js:2029-2047 附近有读写点，但完整触发链跨渲染层，未穷尽；留 [04-preview-and-rendering.md](./04-preview-and-rendering.md)）。
- ⚠️ 待确认（设计口径，需用户拍板）：**被「停止」的那一轮，部分文本是否要写进会话文件**。当前实现只落 `user/message` + `loop/end(stop_reason="aborted")`（部分文本只保留在面板内存与该轮 `answer` 里），因此**刷新页面/恢复会话后该轮只剩用户气泡**。若要"停止后刷新仍能看到半截回答"，需在 `loop.py` 的取消分支补发一条 `assistant/message`（会改变"aborted 轮不提交助手消息"的既有语义）。
- ⚠️ 待确认（未能取证）：`.-graph-settings-preview`（设置页内的图谱预览窗，app.css:332-367）的归属与交互，需在 [06-links-and-graph.md](./06-links-and-graph.md) 或 09 篇确认。
- ⚠️ 待确认（未能取证）：`#-flash-host` 的 `aria-live="polite"` 在动态追加节点时是否被屏幕阅读器正确播报（前端无额外处理，未在真实环境验证）。
- ⚠️ 待确认（未能取证）：`body.-win-dragging` 类（app.css:1984-1987）的写入方未在 `window-chrome.js` 中找到（该文件只写 `.-win-resizing`，window-chrome.js:94、109），疑似遗留样式。
- ⚠️ 待确认（未能取证）：`document.title` 与 `#welcome h1` 的版本号只在 `initWindowChrome` 成功返回时写入；无桥（纯浏览器）环境下的表现未验证。
- ⚠️ **本轮（2026-09-18：M1 收尾打磨四件事——真取消 / 会话列表去读放大 / 恢复上次会话 / 删除会话）已断言 / 未取证**。已断言（**headless Edge（`--headless=new --remote-allow-origins=*`）+ CDP（`websocket-client` 直连，断言全在 Python 侧）+ harness 的 `/rpc` 与静态页 + 本地慢速假 SSE 端点（12 个内容帧 × 0.3s ≈ 3.6s 一轮，端点每帧后探测客户端是否已断开）；`MEMORIA_CONFIG_DIR` 指向临时目录；脚本与产物在仓库外临时目录**）——**31/31 PASS**：
  - **⑨ 停止 = 真取消**：生成中点 `#agent-stop` ⇒ 助手气泡保留已生成片段（`第1次回答分片00|`）并追加「（已停止）」、状态行 =「已停止（已生成的部分文本已保留，可立刻再提问）」、停止按钮隐藏且发送可用；**停止往返 0.060s**（完整流需 3.6s）；停止后**立刻**再提问即正常完成（无 `busy`）；该轮会话文件里 `loop/end` 的 `stop_reason="aborted"`；**假端点侧 `frames_sent=2/15` 且 `aborted=true`** ⇒ 后端确实中断并关闭了模型流（未收完）。
  - **⑩ 清空顺带取消**：生成中点 `#agent-clear` ⇒ 气泡清空、状态行清空、下拉回「（新会话）」、发送可用；假端点侧 `frames_sent=3/15 aborted=true` 且**累计请求数未增**（无后续请求）；随后立刻提问正常完成。
  - **⑪ 恢复上次会话**：提问成功后 `ui-settings.json` 顶层 `agent.lastSessionId` 落盘，且 `layout.sidebarWidth` 保留；`Page.reload` 后**自动恢复**（气泡与下拉 sessionId 与恢复前一致、无 flash）；把该会话文件删掉再 reload ⇒ **静默空态**（无气泡、无错误、无 flash、状态行为空）。
  - **⑫ 删除会话**：`#agent-history-delete` 首点变「再点一次删除」且**文件仍在**；等 3.3s 未再点 ⇒ 文案复位且仍未删除；3s 内连点两次 ⇒ 文件真的消失、面板回到「新会话」态（气泡清空 + 下拉回空）、历史列表刷新后不再含该会话、**其余会话文件保留**。
  - **配置隔离证据**：运行前后真实 `config/ui-settings.json`（SHA256 `3BC0ACC487865714FBDD2993B4C9EE6D1D55CBF7AFA46482DAA48B3D5228D894`）与 `config/agent.json`（`C9CFC8B72271A4FA382270F4210BC59063432CA8F417DED86CCB0FB54CD01D50`）**完全一致**；全部写入只发生在临时 `MEMORIA_CONFIG_DIR` 与临时知识库。
  - **顺带修复（本轮必须，否则 ⑨⑩ 无法成立）**：`llm/providers/openai_compatible.py` 的响应体读法由 `response.read(_READ_SIZE)` 改为 `response.read1(_READ_SIZE)`。实测 `HTTPResponse.read(n)` 在「无 Content-Length / `Connection: close`」的 SSE 上会**阻塞到 EOF 或读满 n 字节**（3.6s 的流只在结束时返回一整块 1094B），使增量投递与"取消立即停止消费"同时失效；`read1` 则逐帧返回（实测 0.02/0.32/0.62…s 各 90B）。**行为变更**：面板的「生成中…」现在是**真增量**（此前整段在结束时一次性上屏）。
  - **未取证**：① 真实模型端点下的取消/恢复观感（用户 `config/agent.json` 是真密钥，**刻意不调用**）；② 被取消那一轮的**部分文本不会写进会话文件**（只落 `user/message` + `loop/end(aborted)`），故刷新/恢复后该轮只剩用户气泡——见下方"待确认"；③ 原生鼠标点击（仍用页面内 `.click()`）；④ 多知识库之间来回切换时的恢复行为（本轮只验证了「刷新页面」这一条恢复路径）。
- ⚠️ **前一轮（2026-09-18 前半：「清空对话 / 忽略本次」的世代号作废 + 确定性连接失败立即失败）已断言 / 未取证**。已断言（**本地慢速假 SSE 端点（延迟 6s 才回帧）+ harness `/rpc` + headless Edge（`--headless=new --remote-allow-origins=*`）经 CDP 驱动，1400×900；`MEMORIA_CONFIG_DIR` 指向临时目录，脚本与产物在仓库外临时目录**）——**12/12 PASS**：① 提问后进入「生成中… Ns」（2 条气泡、发送禁用、忽略按钮可见）；② **生成中点 `#agent-clear`** ⇒ 气泡清空（仅剩 `-agent-empty`）、`#agent-history` 选中值 `""`、状态行清空、发送按钮恢复；③ 被作废作业在后端跑完后：`sessionId` **仍为 `""`**、状态行未被改写、仍无气泡（**修复前此处会把旧会话 id 写回**）；④ 随后新提问写回**新的** `session_id`（≠ 被作废会话），`agent_sessions_list` 由 1 份增至 **2 份**且旧会话保留，且新提问请求体的非 system 消息**只有当前问题**（确证未续到已作废会话）；⑤ 生成中点「忽略本次」⇒ `sessionId` 不变、状态行说明已忽略；⑥ 被忽略作业结束后状态行与气泡均未被改写；⑦ 页面无 JS 异常。**未取证**：原生鼠标点击（仍用页面内 `.click()`）、真机 pywebview 窗口、真实模型端点；另：本次后端「确定性连接失败立即失败」的 A/B 数值见 [10 篇 §2.16](./10-data-layout-and-host-embedding.md)。
- ⚠️ **前一轮（2026-09-18 更早：M1c 多轮续聊 + 会话历史，前端历史下拉与等待计时）已断言 / 未取证**。已断言（**harness 的 `/rpc` + 本地假 SSE 端点（照 `scripts/agent_llm_smoke.py --mock` 的帧格式），`MEMORIA_CONFIG_DIR` 指向临时目录，假端点记录每次请求体；脚本与产物在仓库外临时目录**；两轮提问经 `agent_ask_start`/`agent_ask_poll` 走完整链路）——**27/27 通过**：
  - **续聊**：第一轮请求体只含 1 条 user（无历史）；第二轮请求体（假端点侧记录）含第一轮的 `user(第一问)` 与 `assistant(第1次回答…)`，末尾是 `user(第二问)`，非 system/tool 的 `messages` 角色序列为 `[user, assistant, user]`（② 通过）。
  - **会话 id 贯穿**：两次 `agent_ask_poll` 的最终结果返回同一个 `session_id`（③ 通过），对应同一份 `session_<UTC 时间戳>-<hex>.jsonl`。
  - **列表**：`agent_sessions_list` 返回该会话，`turn_count=2`、`preview=第一问`、`modified_at` 为毫秒时间戳（④ 通过）。
  - **载入**：`agent_session_load` 返回 4 条（`user/assistant × 2`）且文本与两轮一致；未知会话 ⇒ `{status:"error", code:"unknown_session"}`（⑤ 通过）。
  - **零写入**：两次提问只**新增** `.memoria/agent/sessions/<id>.jsonl`、未改动任何既有文件；`agent_sessions_list` 与 `agent_session_load` 调用前后 KB 文件快照（相对路径 → SHA256）**完全一致**。
  - **配置隔离证据**：运行前后 `config/agent.json`（SHA256 `c9cfc8b72271a4fa382270f4210bc59063432ca8f417ded86ccb0fb54cd01d50`）与 `config/ui-settings.json`（`88f65cd17d7341b564d2c04281df470f4a56b1303e701b910c148477cfd85b12`）**完全一致**；全部写入只发生在临时 `MEMORIA_CONFIG_DIR` 与临时知识库。
  - **未取证**：① 真实模型端点下的续聊效果（同前几轮口径，用户 `config/agent.json` 里是真密钥，**刻意不调用**）；② 前端 `#agent-history` 下拉的**原生交互**（本轮端到端走 `/rpc`，未在浏览器里点选下拉/看禁用态；下拉文案与禁用态由 i18n 键覆盖，`scan_ui_strings.py` 无新增候选）；③ 长会话（> 40 条消息 / > 32000 字符）真实截断后的模型表现（截断收敛逻辑有单测断言"从最新往旧保留 + 不留孤儿 tool 消息"，浏览器侧未造大数据）；④ 等待计时器在**真机**上的观感（每秒刷新，本轮只做了静态代码核对与 `node --check`）。
- ⚠️ **上一轮（2026-09-17 第三轮：文档区最小宽度保护 `CONTENT_MIN_PX=360`）已断言 / 未取证**。已断言（**headless Edge（`--headless=new`）+ harness，端口 8643，`MEMORIA_CONFIG_DIR` 指向临时目录；视口用 CDP `Emulation.setDeviceMetricsOverride` 逐步收窄/恢复；断言在 Python 侧（`websocket-client` 直连 CDP）判定，脚本与产物在仓库外临时目录**）——**29/29 通过**：
  - **主表 24/24**：① 1576×668 下 dock 生效宽度 = 期望 22rem（352px）、`#content` 923 ≥ 360、`#main` 无溢出；② 视口 1576→1300→1100→1020→1000→980→950→930→920→917 逐步收窄：**每档 `#content` 均 ≥ 360**，dock 从 352 单调降到 **256（= 16rem 下限）**，且每档 `dock 生效宽度 == min(期望, available)`（误差 ≤ 2px，`available = #main.clientWidth − 左栏 − 360`）；③ 再收到 916（`available=255 < 16rem`）⇒ 加 `-agent-dock--auto-hidden`、`clientWidth/dockRect = 0`、拖拽柄 `display:none`、`#content` 回弹到 615，浮动按钮 title =「空间不足：先折叠左栏（或把它调窄），对话栏才能展开」（与手动折叠的 `agent.dockExpandTitle` 可区分）；④ 此时点**浮动按钮**与**顶栏 `#btn-agent`** 各一次：**仍保持隐藏**（`autoHidden=true`、`dockRect=0`、`#content` 不变），且 `#-flash-host` 出现「空间不足：对话栏保持隐藏…」（不挤压文档区、不写盘）；⑤ 视口恢复到 1576 ⇒ **无需任何点击**即自动回到 352（22rem）；⑥ 左栏先拖到最宽 480 再收窄（1200→1100→…→800）：`available ≥ 0` 的各档 `#content` 均 ≥ 360 且 dock 逐级让位（1200→352/368、1100→260/360、1050 以下隐藏），`available < 0` 的两档（820/800）dock 仍为 0 且 `#content == mainClient − 480`（340/320，属**前提不成立**：左栏 + 360 > 视口）；⑦ 1200×668（左栏 301，`available=539 < 34rem=544`）手动拖 dock 到极限：**拖拽中**即生效为 539.03（= `available`，未破 360），且此刻盘上 `agentDockWidth` 仍为 22（**松开才写盘**），松开后同样 539.03；⑧ 手动折叠 → `clientWidth 0` + `-agent-dock--collapsed`（无 auto-hidden）+ 盘上 `agentDockCollapsed:true`；再展开 → 回 352 + 盘上 `false`，且**盘上 `agentDockWidth` 全程保持 22、`sidebarWidth` 保持 301**（自动收缩/自动隐藏**从未回写盘**——在②③⑤整轮收窄-隐藏-恢复之后回读临时 `ui-settings.json` 断言）；⑨ 页面无 JS 异常（含 `ResizeObserver loop` 类，`window.onerror` 收集为空）。
  - **补充 5/5**：启动即窄视口（720×600，磁盘期望 22rem）⇒ **首帧**就落到自动隐藏（`dockClient=0`、`content=419=720−301`），浮动按钮 rect `[700,250,20×40]` 完全在视口内、`display:flex`/`visibility:visible`/`opacity:1`/未禁用 ⇒ **"浮动还原按钮出现"成立**；语言切到 `en` 再切回，其 title 随之变为 `Not enough space…` / 回到「空间不足…」（三态文案跟随语言刷新，未被静态节点覆盖）。极窄补测（876×271、492×179）：均为自动隐藏、`#main.scrollWidth == clientWidth`（**不再出现 dock 被 `overflow:hidden` 裁掉**）。
  - **配置隔离证据**：运行前后 `config/ui-settings.json`（SHA256 `292D35BC…011B09C8`）与 `config/agent.json`（`0105B261…04A8BC09`）**完全一致**；全部写入只发生在临时 `MEMORIA_CONFIG_DIR`。
  - **未取证**：① `uiScale ≠ 1`（0.8–1.5）下的实际换算——本轮所有实测都在根字号 16px 下（实现按 rem 等比，仍属**推算**）；② 左栏**折叠**（`-sidebar--collapsed`）时 `sidebarEffectivePx()` 取 0 的实际链路（代码按几何宽度取 0，本轮只测了「展开但很宽」；RE 观察器已挂在 `#-sidebar`，但未做折叠-展开的端到端断言）；③ 拖拽的**原生鼠标事件**（本轮仍是页面内合成 `MouseEvent`，与上一轮同一限制）；④ 真机 pywebview 窗口（`window.resize` 与 CDP metrics override 的差异：CDP 会改 `innerWidth` 并触发 resize，真机还应同时触发窗口 chrome 逻辑）；⑤ 用户实际"手感"（0.18s 过渡期间逐帧收窄的观感）。
- ⚠️ **上一轮（2026-09-17 第二轮：左栏第 4 页签 → 右侧 `#-agent-dock`）已断言 / 未取证**。已断言（**headless Edge + harness，端口 8642，`MEMORIA_CONFIG_DIR` 指向临时目录**；断言脚本注入页面、结果 POST 回 `/assert_result` 落盘，脚本与产物在仓库外的临时目录）：
  - **A 组（视口 1576×668）12/12 通过**：① `[data-sidebar-tab]` 数量 = 3（`files`/`graph2d`/`graph3d`）且三页签逐个点击后 `.hidden` 与 `.active` 正确互斥；② `#-agent-dock` 存在、默认可见（无 `-agent-dock--collapsed`、`offsetParent` 非空、`border-left` 1px、`flex-shrink:0`），`computed width = 352px`（= 22rem @ 根字号 16px）；③ 点 `#btn-agent` → `clientWidth` 0 + 类名 `-agent-dock--collapsed` + 拖拽柄 `display:none` + 浮动按钮字形 `‹`，再点 → 恢复 351px；④ 拖拽 `#agent-dock-resizer` 到两侧极限 → 夹取到 34rem（543px）与 16rem（255px），回拖到 22rem 恢复；⑤ 落盘后 `get_ui_settings` 返回 `layout = {sidebarWidth: 301, agentDockCollapsed: false, agentDockWidth: 22}`——**预置的 `sidebarWidth` 未被抹掉**（顶层浅合并坑已规避），且临时目录里的 `ui-settings.json` 磁盘内容一致。
  - **B 组（视口 876×271，高 271px 复现原矮窗口场景）7/7 通过**：① ② ③ 同上；⑥ 展开 `#agent-settings` 后 `clientHeight 121 / scrollHeight 267` ⇒ 可滚，`scrollTop` 到底后 `#agent-save-config` 的 rect 落在设置区可见范围内（[164,185] ⊂ [72,194]）——**上一版的「保存按钮被裁出可视区」已修复**。B′ 组（视口 492×179）同样 7/7 通过（`clientHeight 80 / scrollHeight 267`）。
  - **配置隔离证据**：运行前后 `config/ui-settings.json`（SHA256 `292D35BC…011B09C8`、mtime 2026/09/17 21:21:04）与 `config/agent.json`（SHA256 `0105B261…04A8BC09`、mtime 2026/09/17 20:05:07）**完全一致**；写入只发生在临时 `MEMORIA_CONFIG_DIR`。
  - **未取证**：① **真实模型的端到端对话效果**（打字机节奏、`answer` 覆盖流式文本的观感、`anchors` 条数）——需真实 `base_url` + 密钥，本轮**刻意未调用**真实端点（用户 `config/agent.json` 里是真密钥）；② 上一轮已断言的 4 个 RPC 行为（空输入/未配置端点/出网开关/密钥掩码/忽略本次/busy）本轮**未重跑**（本轮未改后端与这些代码路径，`git diff` 可核）；③ `#agent-dock-collapse-btn` 的**原生鼠标点击**路径（harness 用页面内 `.click()`；两个入口都绑在同一个 handler 上，`#btn-agent` 走的是同一条代码路径）；④ 深/浅两套主题下的实际取色（`.-agent-*` 只用既有变量：`--bg-secondary/--bg-tertiary/--bg-hover/--border/--text-primary/--text-secondary/--text-bright/--accent-hover/--accent-soft/--error` 在 `theme/light.css:17-30` 均有定义；`--theme-color` 仅由 `theme/memoria.css` 定义、浅色主题不覆盖——**既有全局行为**，非本次引入）；⑤ `uiScale` 缩放（0.8–1.5）下 dock 宽度的实际 rem 换算（按实现是等比，**推算非实测**）；⑥ 视口宽度介于 652px 与 900px 之间时三栏挤压的具体断点（只测了 876/492 两档与 1576 一档）。
- ⚠️ **上一轮（2026-09-17 首轮，左栏第 4 页签）已断言 8 项**：四页签与视图互斥、面板 DOM 齐全、空输入报错、未配置端点报错（状态行 + flash + 气泡）、出网开关读写与发送禁用、配置回填与**密钥掩码进 DOM 而明文不进 DOM**、真实作业（指向必拒连的 `http://127.0.0.1:9/v1`）从「生成中…」到 `askFailed+后端原文` 的全链路、忽略本次与 `busy` 文案。该版已随第 4 页签删除而**不再是当前形态**（回退参照：提交 `8f2e88f6`）。
