# 01 · 窗口外壳与整体布局

> **用途**：把 Memoria 桌面窗口的「外壳 + 五大区域」（窗口 chrome / 顶栏 / 左侧栏 / 文档区 / 状态栏）连同闪烁提示（flash）、弹窗层级与缩放变量，写到可据以定位实现的粒度。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[README.md](./README.md)（本套说明书的用法与维护约定）、[02-file-tree-and-nav.md](./02-file-tree-and-nav.md)（左侧栏「文件」页签的细节）、[09-settings-i18n-and-shortcuts.md](./09-settings-i18n-and-shortcuts.md)（设置四页与快捷键总表）、[../preview-formats.md](../preview-formats.md)（渲染语法权威）、[../i18n-inventory.md](../i18n-inventory.md)（文案清单）。
> **状态**：生效中，2026-09-19。

---

**证据锚约定**：`文件:行号` 以**仓库根目录**为基准。前端在 `src/memoria/ui/static/app/**`；少量外壳样式在 `src/memoria/ui/static/theme/memoria.css`（下称 `theme/memoria.css`）；窗口 chrome 的原生部分属后端，涉及处标 `src/memoria/app/**`。

## 1. 区域概览

```
#app                          index.html:47    （memoria.css:81-85 纵向 flex，高 100vh）
├── #toolbar                  index.html:48    z-index 50（memoria.css:88-105）
│   顺序：.toolbar-left:49（**只剩品牌**:50-54）→ .toolbar-actions:56
│         （文件菜单按钮:60、菜单面板:61-75）→ spacer:85 → .toolbar-search-wrap:86
│         → spacer:96 → .toolbar-right:97（`#btn-toggle-sidebar`:98 + `#btn-agent`:99 + #window-controls:100-104）
├── #main                     index.html:109   （memoria.css:277 横向 flex，flex:1）
│   ├── #-sidebar             index.html:110    （app.css:123-135）
│   │   ├── #sidebar-resizer:111 · .-sidebar-tabs-wrap:112（文件/2D/3D）
│   │   ├── #sidebar-graph-group-bar:119       仅图谱页签 + 有节点时显示
│   │   └── #sidebar-body-split:122            导航面板:123 / 分栏柄:136 / 知识点块:137
│   │        └── 导航面板内三视图：files:124 / graph2d:127 / graph3d:131
│   ├── #content               index.html:151   （memoria.css:417-421）
│   │   ├── #tab-bar > #tabs   index.html:152-154
│   │   └── #viewer            index.html:155   （memoria.css:468-473）
│   │       ├── #welcome       index.html:156    欢迎页（空态）
│   │       └── #editor-wrap   index.html:161    默认 .hidden；header:162 / preview-status:210 / editor-split:211
│   ├── #-agent-dock           index.html:222   右侧「对话」停靠栏（app.css:304-317）；见 §2.4
│   │   ├── #agent-dock-resizer:223             左缘拖拽柄（app.css:345-357）
│   │   └── 内部：顶部操作条:224-233 / 设置区:234-255 / 历史行:256-260 / 消息区:261 / 输入区:262-270
│   └──（2026-09-18：原 `#agent-dock-collapse-btn` 浮动按钮已删除）
└── #status-bar                index.html:274    （memoria.css:591-600）
     #status-kb:275（**最左**，知识库路径）· #status-info:276 · #status-stats:277 · #status-agent:278（agent 用量格）
#-flash-host:284 · 9 个 .-modal:286-432   均在 #app 之外，fixed
```

> ⚠️ **行号漂移（2026-09-19 实测）**：本节 tree 已按当前 `index.html` 重取。差异来源：① **既有漂移**——本文最初记录的 `index.html` 锚点整段比实际**小 13 行**（`#app` 旧记 34、实际 47），`js/*.js` 锚点亦有小偏差（`showWelcome` 旧记 380-383、现 391-394）；② **2026-09-17 第一轮**——在侧栏插入第 4 页签与「对话」面板（共 +45 行），故 `#main` 内其后节点 = 旧锚 +58；③ **2026-09-17 第二轮**——对话面板由左栏第 4 页签**迁为右侧 `#-agent-dock`**（`index.html` 净 +4 行）；④ **2026-09-17 第三轮**（文档区最小宽度保护）**未改 `index.html`**，但 `app.css` 在 dock 段插入了 `.-agent-dock--auto-hidden`（+14 行）⇒ `app.css` 中 dock 段及其后行号整体位移；⑤ **2026-09-18（本轮 M1c）**——对话面板新增历史行 `.-agent-history`（`index.html` **+4 行**，259-262）⇒ **`index.html` 中 dock 之后各节点行号 +4**（`#-agent-dock` 225 不变、`</aside>` 269→273、折叠按钮 271→275、`#status-bar` 274→278、`#-flash-host` 282→286、`.-modal` 284-430→288-434）；`app.css` 仅新增 `.-agent-history` 5 条规则（494-526，其后各条行号下移 33 行，如 `.-agent-messages` 494→527）；⑥ **2026-09-18（本轮「agent 用量可视化」）**——`#status-bar` 内新增 agent 用量格 `<span id="status-agent">`（`index.html` **+1 行**）⇒ 其后各节点行号 +1（`#-flash-host` 286→288、`.-modal` 288-434→290-436）；`app.css` 新增 `#status-agent` 3 条规则（**+12 行**，其后各条行号 +12）；`js/agent-panel.js` **+131 行**（状态栏用量格的状态与渲染/累加，见 §2.7）⇒ §2.4 表中 `agent-panel.js` 锚点按 **+5**（原 1-555 段）/ **+111**（原 556+ 段）换算；⑦ **2026-09-18（本轮「外壳层重构」）**——顶栏：`.toolbar-left` 内新增 `#btn-toggle-sidebar`（+1 行）、`#file-menu` 内新增分隔线 + 「关闭知识库」/「退出程序」两项（+3 行）、`.toolbar-right` 内原 4 行 `#kb-indicator-wrap`（路径 + 退出按钮）替换为 1 行 `#btn-agent`（−3 行）、左栏浮动按钮 `#sidebar-collapse-btn` 与右栏浮动按钮 `#agent-dock-collapse-btn` 各删除 1 行 + 1 空行（−4 行）⇒ **`index.html` 净 −3 行**（顶栏区 +1；`#sidebar-collapse-btn` 及其空行 −2 ⇒ `#-agent-dock` 225→223；`#agent-dock-collapse-btn` 及其空行 −2 ⇒ `#status-bar` 279→275）；`theme/memoria.css` 新增顶栏弹性纪律（`#toolbar`/`.toolbar-left`/`.toolbar-actions`/`#btn-toggle-sidebar` 相关规则，**+37 行**，其后各条行号下移）并删除 `.kb-indicator-wrap`/`.kb-indicator`/`.-kb-exit`（**−38 行**）；`app.css` 删除两个浮动按钮的样式（`.-sidebar-collapse-btn` 26 行 + `.-agent-dock-collapse-btn` 26 行）、新增 `#status-kb` 与顶栏收缩规则。**本文 §2.1/§2.2 的锚点已在本轮一并重扫**（不再依赖偏移换算）；⑧ **2026-09-18（本轮「顶栏按钮合并 + 退出程序移除 + 底栏路径左移 + 文件树拖拽引用」）**——`index.html`：`#btn-toggle-sidebar` 由 `.toolbar-left` 首位**移到 `.toolbar-right` 首位**（净 0 行）、`#file-menu-quit` 删除（**−1 行**）⇒ 其后的 `.toolbar-right` 99→97、`#-agent-dock` 223→222、`#status-bar` 275→274、`#-flash-host` 285→284、`.-modal` 287-433→286-432；`#status-kb` 由 `#status-bar` 末位改为**首位**（净 0 行）；`theme/memoria.css` **本轮未改**；`app.css` 新增 `.-agent-mention` / `.-agent-mention--dir` / `.-agent-composer--drop .-agent-input` 三条规则块（`.-agent-mention` 546-574、drop 629-638 —— 同日后续把落点由 `.-agent-composer` 放宽为整个 `#-agent-dock`，故该 CSS 块由 4 行增为 7 行）⇒ **`app.css` 中 546 之后各条行号下移**（如 `#status-stats.-status-clickable` 2024-2050→2058-2067、`#status-agent` 2084-2091→2118-2125、`#status-kb` 2096-2105→2127-2141、`.-modal` 4542→4577）；`js/agent-panel.js` 新增 `/@路径/` 引用解析与拖拽插入（常量 121-125、`mentionChip`/`linkifyUser`/`mention*` 489-580、装配 1511-1550）；**同日又改 `@` 语法**（`MENTION_RE` 改为 `/(^|\s)(@"([^"]*)"?|@(\S+))/g`、新增 `formatMention`）⇒ 该文件净 **+19 行**（1617→1636），**121 之后各条行号下移**（§2.4/§6 中 agent-panel.js 锚点已按实测整体重取，见 §6 与 §2.4「`@相对路径` chip 渲染」）；`app.js` 删除 `#file-menu-quit` 的 click 绑定（**−4 行**，其后各条行号下移）；`i18n/{zh-CN,en}.js` 删除 `toolbar.quit`/`toolbar.quitTitle`、新增 `agent.mention.openTitle`/`revealTitle`。⑨ **2026-09-19（本轮：顶栏搜索框收窄）**——`app.css` 仅 `.toolbar-search-wrap` 块净 **+4 行**（`flex:1 1 auto`→`0 1 auto`、`width:min(380px,42vw)`→`min(240px,26vw)`，注释增补理由）⇒ **`app.css` 中 2398 之后各条行号 +4**；`index.html`/`theme/memoria.css` 本轮未改。⚠️ 本轮之前 §1/§2.3/§2.5/§2.9 中若干 `memoria.css`/`app.css` 锚点系**更早轮次遗留的漂移**（与代码本就不符）；⑨ 起已对本篇 §1/§2.1/§2.2/§2.3/§2.4/§2.5/§2.7/§2.8/§2.9/§2.10/§5/§6 的 `app.css`/`memoria.css` 锚点**逐条实测重取**（不依赖偏移换算，含此前遗留的漂移）；**§2.6（知识点面板）**锚点未重扫（本轮未改动知识点面板的代码）。

**关键互斥关系**（§5 展开）：`#welcome` 与 `#editor-wrap` 由 `showWelcome()` 互斥（app.js:391-394）；导航面板内**三**视图由 `.hidden` 互斥（app.js:1241-1246，见 §2.3）；`#editor-split` 三视图由类名互斥（app.js:1646）。

## 2. 逐处细节

### 2.1 窗口 chrome（无边框、三键、拖拽、边缘缩放）

| 项 | 实现位置 | 说明 |
|---|---|---|
| 是否无边框 | window-chrome.js:300-301 | 由后端 `get_window_chrome().frameless` 决定（ui.py:662-675）；非无边框时隐藏三键并给所有拖拽区设 `-webkit-app-region: no-drag`（window-chrome.js:330-337） |
| 三键容器与外观 | index.html:100-104；app.css:2203-2296 | `#window-controls` 默认 `hidden`，仅 frameless 时显示（window-chrome.js:339）；按钮宽 2.875rem、高 2.1875rem，`font-size:0`，图形由 `::before/::after` 画（最小化=横线、最大化=方块、关闭=叉）；关闭键 hover 变 `#e81123`。**`flex: 0 0 auto`（永不收缩，app.css:2207）** |
| 三键永不被挤出（弹性纪律，2026-09-18 立；2026-09-19 收窄搜索框） | theme/memoria.css:88-161；app.css:2207、2394-2417 | 顶栏是**单行**弹性条（`#toolbar{flex-wrap:nowrap}`，memoria.css:94）。**不可收缩**：`.toolbar-right`（`flex:0 0 auto`，memoria.css:235-243）与 `#window-controls`（app.css:2207）⇒ 三键恒定贴右缘可见。**可收缩**：`.toolbar-left`（`flex:0 1 auto; min-width:0; overflow:hidden`，memoria.css:109-118）、`.toolbar-actions`（同前两者 + 各按钮 `min-width:0; overflow:hidden`，memoria.css:119-131、159-162）、**主要收缩项** `.toolbar-search-wrap`（`flex:0 1 auto; flex-shrink:12; min-width:9.5rem; width:min(240px,26vw)`，app.css:2394-2417）。**2026-09-19：`flex-grow` 由 1 改 0**——搜索框宽度只由 `width` 决定、**不再吃掉顶栏中段空白**，剩余空白改由两处 `.-titlebar-drag-spacer`（`flex:1 1 0`，memoria.css:163-170）分走 = **可拖拽区**（这正是当年 `flex-grow:1` 把中段空白吃光、顶栏几乎无可拖空隙的修正）。`min-width:9.5rem`（= 内部范围开关 + 输入框 `min-width:4.5rem` + gap/padding 之和）**保持不变**，故真机窄窗口的收缩行为不变；取 0 会让子块外溢并抬高 `#toolbar.scrollWidth`，故只收窄首选宽度、不动下限。⚠️ `.toolbar-actions` **不得**加 `overflow:hidden`（盒内含 `#file-menu` 浮层，裁切会把下拉整个切掉）。实测定值见 §7 本轮（2026-09-19）记录 |
| 图标状态与行为 | window-chrome.js:25-30、382-395 | 最大化时切 `.is-restore`（app.css:2255-2264）并改 title/aria；三键分别经桥 `window_minimize` / `window_toggle_maximize` / `window_close`（关闭键走 `requestClose()`，见下行） |
| 关闭入口（`requestClose`；「文件 → 退出程序」菜单项已于 2026-09-18 移除） | window-chrome.js:293-298、393-395、400-404 | 导出 `MemoriaWindowChrome.requestClose()` = `api()?.window_close?.()`，**现在唯一的使用者是窗口关闭键 `#btn-win-close`**（原「文件 → 退出程序」菜单项经用户否决已删除，见 §7；其 JSDoc 注释仍提旧菜单项，属待清理的注释残留，**不影响行为**）。它**不依赖** `#window-controls` 是否可见（原生标题栏模式下三键被隐藏，RPC 仍可用） |
| 拖拽区与排除 | index.html:49、85、96、97；window-chrome.js:120-129 | 4 处挂 `pywebview-drag-region`（`.toolbar-left`:49、两个 spacer:85/96、`.toolbar-right`:97；**2026-09-18 起顶栏内已无 `#kb-indicator`**）；命中排除 `NO_DRAG_SELECTORS` = `#btn-toggle-sidebar, #btn-agent, .toolbar-search-wrap, .toolbar-actions, .-window-controls`（`closest()` 判定）。**本轮变化**：两个图标按钮 `#btn-toggle-sidebar` 与 `#btn-agent` **现同处 `.toolbar-right`**（该容器整体挂 drag-region、且不在 `NO_DRAG_SELECTORS` 里，故二者必须显式登记，否则 mousedown 会被拖拽吞掉点击）。harness（frameless 变体）实测：点这两个按钮**不**触发 `window_begin_drag`，点品牌区**会**触发 |
| pywebview 拖拽路径 | window-chrome.js:196-216、349-351 | `mousedown` → RPC `window_begin_drag` → 后端 `PostMessage` → WndProc 执行 `WM_NCLBUTTONDOWN + HTCAPTION`（原生拖动 + Aero Snap），不用 `-webkit-app-region` |
| pyqt6 拖拽路径 | window-chrome.js:166-194、131-164 | 走 `__memoriaQtBridge.startMove()`；另把 `.toolbar-right` 左沿 x 同步给 Qt 作拖拽排除带（ResizeObserver 观察 `#toolbar` 与 `.toolbar-right`——**2026-09-18**由已删除的 `#kb-indicator-wrap` 换成后者） |
| 最大化下拉还原 | window-chrome.js:230-291、8-9 | 阈值 `DRAG_THRESHOLD=4`、标题栏纵向偏移 `TITLEBAR_Y_OFFSET=17`；越阈值先 `window_restore_from_drag` 再 `window_move_to` |
| 双击标题栏 / 焦点回拉 | window-chrome.js:366-378、218-228 | 仅 pywebview 绑双击切换最大化；窗口重获焦点时用 `get_window_chrome()` 校正图标（覆盖 Aero Snap 等 JS 未知变化） |
| 边缘缩放层 | window-chrome.js:43-118；app.css:2298-2377 | `#window-resize-layer` 含 8 个手柄（n/s/e/w/nw/ne/sw/se），`z-index:10000`、容器 `pointer-events:none`（只有手柄 `auto`），拖拽经 `window_resize_to`（ui.py:677-684 再按 `WINDOW_MIN_*` 夹下限） |
| 原生 NCHITTEST 例外 | window-chrome.js:61-66 | `shell === "pyqt6"` 且 Windows 时不启用 JS 缩放层，交给系统 `WM_NCHITTEST` |
| DWM 圆角 | src/memoria/app/window_win32.py:166-180 | `DWMWA_WINDOW_CORNER_PREFERENCE(33)=DWMWCP_ROUND(2)`，保留 DWM 边框/阴影，标题栏区域由 `WM_NCCALCSIZE→0` 消除；pyqt6 hidden chrome 同常量（src/memoria/app/shell/pyqt6_hidden_chrome.py:886-891） |
| **最小尺寸（2026-09-18 起 1000×600）** | src/memoria/app/shell/host.py:7-15（**唯一事实源**）；pywebview.py:480；pyqt6.py:233；ui.py:662-684；window-chrome.js:16、315-316 | 常量 `WINDOW_MIN_WIDTH=1000` / `WINDOW_MIN_HEIGHT=600` 定义在宿主协议模块 `app/shell/host.py`，被三处引用：pywebview `create_window(min_size=…)`、PyQt6 `setMinimumSize(…)`、`get_window_chrome()` 的 `min_width/min_height`（前端 `window-chrome.js` 用它夹 JS 侧边缘缩放，兜底默认值同步为 1000×600）；`scripts/diag_webview.py:98` 亦改用常量。**1000 的理由**：三栏并排 = 左栏默认 17.5rem(280) + 右栏 dock 默认 22rem(352) + 文档区保底 `CONTENT_MIN_PX=360` ≈ **992** ⇒ 取整 1000，最小窗口下 dock 仍正常显示（不触发 `-agent-dock--auto-hidden`）；高度沿用 600 |
| 版本号 | window-chrome.js:317-325 | `version` 写入 `document.title`、`#welcome h1` 与 `#app-badge` |

> ⚠️ `.pywebview-drag-region` 在 `theme/memoria.css:171-179` 写着 `-webkit-app-region: drag`，但两条真实路径上都被 JS 显式改成 `no-drag`（window-chrome.js:333-335、349-351）——类名里的 "drag" 当前不生效。

### 2.2 顶栏

顶栏高 2.1875rem、左内边距 12px、右内边距 0（memoria.css:97-98），故窗口三键贴右缘。
**2026-09-18 布局**：顶栏**最左只剩品牌**；**最右** `.toolbar-right` 内依次是左栏伸缩 `#btn-toggle-sidebar`(◧) → 对话栏 `#btn-agent`(◨) → 窗口三键（两枚伸缩图标原分置左右，同日**合并到右侧**）。知识库路径与「关闭知识库」都已移出顶栏（见本表与 §2.7）。顶栏的弹性纪律（谁能被挤、谁不能被挤）见 §2.1「三键永不被挤出」。**2026-09-19**：中段 `.toolbar-search-wrap` 改 `flex:0 1 auto`、宽 `min(240px,26vw)`，**不再生长** ⇒ 顶栏中段剩余空白全部归两处 `.-titlebar-drag-spacer`（`flex:1 1 0`）= **可拖拽区**；成因与 A/B 实测见 §2.1 与 §7。

| 元素 | 位置 | id / 类 | 交互 | 禁用 / 隐藏条件 |
|---|---|---|---|---|
| **左栏伸缩（2026-09-18 起在顶栏右侧首位）** | `.toolbar-right` **首位**（`#btn-agent`、`#window-controls` 之前） | `#btn-toggle-sidebar`（index.html:98）；纯图标 **`◧`**（左半实心方块＝左栏）、无文字；视觉复用 `.toolbar-actions button` 规则（memoria.css:132-156，含 hover），图标按钮尺寸由 `#btn-toggle-sidebar, .toolbar-right #btn-agent` 共用规则给定（memoria.css:145-151） | 点击 = 左栏整体收起/展开（app.js:12191-12200 → `_applySidebarCollapsed()`，app.js:12177-12189）；`aria-pressed` = **是否展开**（与右栏 `#btn-agent` 同口径）；title/`aria-label` = `side.collapseTitle` / `side.expandTitle`（成对），语言切换由 `MemoriaI18n.addRefresh` 重刷（app.js:12198） | 无禁用；折叠态存 `localStorage["-sidebar-collapsed"]`（app.js:12165、12182）。**原浮动按钮 `#sidebar-collapse-btn` 已删除**（见 §2.3） |
| 品牌 + 版本徽标 | `.toolbar-left`（顶栏**最左**；2026-09-18 起该容器内**已无任何按钮**） | `#app-badge`（`.-badge`，app.css:3-15）；品牌 `logo-icon` + `.logo`（index.html:50-53） | 无（拖拽区；`.toolbar-left` 整体挂 `pywebview-drag-region`） | 徽标文本仅在后端返回 version 时填充（window-chrome.js:323-324） |
| 后退 | `.toolbar-actions` | `#btn-nav-back`（`.-nav-btn`，app.css:2664-2669） | 点击 → `navBack()`（app.js:6254-6259）；Alt+←（app.js:12566-12568） | `disabled = !canBack()`（app.js:417-423）；HTML 初值 disabled（index.html:57） |
| 前进 | 同上 | `#btn-nav-forward` | 点击 → `navForward()`（app.js:6261-6266）；Alt+→（app.js:12569-12572） | `disabled = !canForward()` |
| 「文件」菜单按钮 | 同上 | `#btn-file`（`.-tb-file`，app.css:4792-4797） | 点击切换 `#file-menu` 显隐并同步 `aria-expanded`（app.js:12253-12259） | 无禁用 |
| ─ 打开 / ─ 导入 | 菜单内（index.html:62-63） | `#file-menu-open` / `#file-menu-import` | 关闭菜单后分别调 `openKb()`（app.js:583-587）与 `MemoriaImportFlow.start()`（app.js:12270-12273） | 无 |
| ─ 导出（预留） | 菜单内（index.html:64） | `#file-menu-export` | 无 | 恒定禁用；title「导出知识库（预留，待后续版本）」（i18n/zh-CN.js:509-510） |
| ─ 创建 Trae 智能体 | 菜单内（index.html:67） | `#file-menu-kb-agent` | 绑定于 kb-agent.js:188；未开库时给应用内错误提示（底栏转红 + 浮层），**不**弹系统目录选择（kb-agent.js:43-50） | 无 |
| ─ 新窗口 | 菜单内（index.html:68） | `#file-menu-new-window` | 绑定 12338-12341 调 `spawnNewWindow("")`（实现 12276-12286）→ `call("open_new_window")` | 无 |
| ─ 打开最近 ▸ | 菜单内（index.html:68-72） | `#file-menu-open-recent` + `#file-menu-recent` | 点击展开二级面板并拉取列表（绑定 12342-12346，渲染 `renderRecentKbMenu` 12296-12336）；点条目：未开库→本窗口装载，已开别的库→另开窗口，同库→忽略 | 列表项可 disabled：`toolbar.recentLoadFailed` / `toolbar.recentEmpty` |
| **─ 关闭知识库（2026-09-18 新增）** | 菜单内**末尾段**（分隔线 index.html:73 之后，index.html:74） | `#file-menu-close-kb`（`role="menuitem"`） | 首句 `closeFileMenu()` 后调 `closeKb()`（app.js:12351）——**与原顶栏 `#btn-kb-close`（退出）按钮行为完全一致**（屏障刷盘 → 关库 → 清空全部前端状态 → 回欢迎页，app.js:589-643） | **未开库时 `disabled`**；可用态由 `showKbIndicator()` 统一同步（app.js:382-389），HTML 初值 `disabled` |
| ~~─ 退出程序~~（**已移除**，2026-09-18 用户否决，见 §7） | ~~菜单内最末（index.html:76）~~ | ~~`#file-menu-quit`~~——**节点、click 绑定与注释均已删除**；`#file-menu-close-kb` 之上仍有分隔线 | — | — |
| 刷新 | 同上 | `#btn-refresh` | 依次 `refreshFiles` → `loadLinkTargets` → `loadGraphData` → 以 `skipNav:true` 重开当前文件（app.js:12355-12360） | 无禁用、无前置检查 |
| 构建 | 同上 | `#btn-build` | `buildKb()`：同步链接配置并生成图谱（app.js:1033-1076） | 执行期间 `disabled`；未开库不置灰，给错误样式提示（底栏转红 + 浮层） |
| 检查（+角标） | 同上 | `#btn-check` + `#btn-check-badge`（`.-toolbar-badge`，app.css:2159-2190） | 打开检查弹窗（kb-check.js:642）；角标按 error/warn 计数着色 | 未开库不置灰，给错误样式提示（kb-check.js:622-626）；角标 `.hidden` 即隐藏 |
| 设置 | 同上 | `#btn-settings` | 打开设置弹窗（graph-settings.js:950） | 无 |
| 搜索范围开关 | `.toolbar-search-wrap` | `#toolbar-search-scope`（`role="switch"`） | 整块可点/可聚焦，点击或 Enter/Space 翻转「全库 ⇄ 文件」（toolbar-search.js:253-263）；子按钮 `pointer-events:none` | 内部「文件」子按钮在无 `currentPath` 时 `disabled`；强行切到 file 会发 `openFileFirst` 错误 |
| 搜索框 | 同上 | `#toolbar-search` | 输入防抖 220ms、Enter 搜索（Shift+Enter 仅当前文件）、Esc 关面板并失焦、Ctrl+K 聚焦 | 无禁用；未开库时提示 `openKbFirst`（错误样式） |
| 搜索结果面板 | 同上 | `#toolbar-search-panel` | 绝对定位于搜索框下方，`z-index:9000`；点外部或选中结果即隐藏 | 默认 `.hidden` |
| **对话（右栏 dock 开关）** | `.toolbar-right` 次位（`#btn-toggle-sidebar` 之后、`#window-controls` 之前） | `#btn-agent`（index.html:99）；纯图标 **`◨`**（右半实心方块＝右栏）、无文字；title 仍走 i18n `agent.btnTitle` | 点击切换右侧 `#-agent-dock` 的展开/收起（agent-panel.js:1587-1588 → `toggleDock()`:294-296，它在「手动折叠**或**空间不足自动隐藏」两种隐藏态下都解释为"请求展开"）；`aria-pressed` = 是否可见（agent-panel.js:253-259）；**原浮动 `#agent-dock-collapse-btn` 已删除**，故这是唯一入口；见 §2.4 | 无禁用；页面无 `#-agent-dock` 时整个面板不装配（agent-panel.js:1482） |
| **知识库路径（2026-09-18 移到底栏，同日改到最左）** | ~~`.toolbar-right`~~ → `#status-bar` **首位** | `#status-kb`（index.html:275；app.css:2137-2145） | 见 §2.7 | 空路径 ⇒ `:empty{display:none}` 隐藏不占位 |
| **退出（2026-09-18 移入「文件」菜单）** | ~~`.toolbar-right`~~ → `#file-menu-close-kb` | 见上「关闭知识库」行 | 同上 | 同上 |
| 窗口三键 | `.toolbar-right` 末位 | `#window-controls`（index.html:100-104） | 见 §2.1 | 默认 `hidden`（非 frameless 或 RPC 不可用时不 `remove("hidden")`） |

### 2.3 左侧栏

| 项 | 证据 | 说明 |
|---|---|---|
| 容器 / 收起态 | index.html:110；app.css:123-144 | `#-sidebar` 默认宽 17.5rem、`min-width` 11.25rem、含宽度过渡；加 `.-sidebar--collapsed` 后宽 0、去右边框、溢出自隐、隐藏拖拽柄 |
| 收起/展开按钮（**2026-09-18 改为顶栏图标**） | index.html:98（顶栏 `.toolbar-right` **首位**）；memoria.css:132-161、109-118；app.js:12162-12200 | **原 `#sidebar-collapse-btn` 浮动按钮已删除**——连同 `app.css:147-171` 样式、贴侧栏右缘的 `_positionSidebarCollapseBtn()`、跟随几何的 `ResizeObserver` 与 `window.resize` 重定位（`applySidebarWidth()` 里的定位调用，原 app.js:12124）一并移除；现唯一入口是顶栏**右侧首位**的 `#btn-toggle-sidebar`（图标 `◧`，见 §2.2），`aria-pressed` 反映展开态（`aria-expanded` 已弃用），点击走同一份 `_applySidebarCollapsed()`（app.js:12177-12189），状态存 `localStorage["-sidebar-collapsed"]` |
| 宽度拖拽 | index.html:111；app.js:12134-12154；夹取 app.js:12103-12106；手柄样式 theme/memoria.css:291-302 | 手柄在右缘外 3px、宽 0.375rem、hover 高亮主题色；把 `clientX` 夹到 **180–480px**（与 CSS 的 11.25rem 最小值/17.5rem 默认值为两套口径）；`mouseup` 落盘 `layout.sidebarWidth`（app.js:12113-12122，落盘点 12121） |
| **三页签** | index.html:112-116；app.js:1233-1258 | `[data-sidebar-tab]` = `files`(113) / `graph2d`(114) / `graph3d`(115)，复用 `.-config-tab`；切换逻辑是通用实现（按 `dataset` 遍历按钮与视图，无 tab 白名单，app.js:1239-1246）；当前页签写 `localStorage["-sidebar-tab"]`（app.js:1238），初值读同键、默认 `files`（app.js:33）。**2026-09-17：「对话」第 4 页签已删除**（面板迁为右侧 `#-agent-dock`，见 §2.4），同时 `setSidebarTab` 加了一行守卫——存量 `localStorage["-sidebar-tab"]="agent"` 命中不到任何 `[data-sidebar-view]` 时回退 `files`（app.js:1234-1236），否则三个视图会被一起隐藏 |
| 页签计数 | index.html:113-115；app.js:739-741 | `#sidebar-tab-count-files` = `state.files.length`；`#sidebar-tab-count-graph2d/-graph3d` = `state.graphData.nodes.length`（两者同值）；更新于 `refreshFiles`（app.js:639）与 `loadGraphData`（app.js:1072） |
| 页签内容 | index.html:124-134；app.js:1239-1246 | `files` → `#file-tree`（124-126）；`graph2d` → `#graph-2d-root` + 覆盖提示（127-130）；`graph3d` → `#graph-3d-root` + 覆盖提示（131-134）；切页签时 `.hidden` 互斥（app.js:1244-1246）并通知图谱视图 `stop()/start()`（app.js:1248 → `setGraphPanelActive`，1194-1210） |
| 图谱分组条 | index.html:119-121；app.js:757-768 | `#sidebar-graph-group-bar` 仅在图谱页签**且**节点数 > 0 时显示，同步 `aria-hidden` |
| 上下分栏 | index.html:122-134、136-137；graph-settings.js:343、361、915-965、967 | 上=导航面板、下=知识点块；柄高 6px、上方最小 100px（`SPLIT_MIN_TOP`，graph-settings.js:343）、下方最小 72px；比例按页签记忆（默认 files 0.55 / graph2d 0.82 / graph3d 0.72，graph-settings.js:43-47）；柄样式见 app.css:708-719 |

### 2.4 右侧「对话」停靠栏（`#-agent-dock`，2026-09-17 由左栏第 4 页签迁出）

只读问答面板：问一句 → 后端 `ask()` 跑「检索 → 远端模型 → 带 `文件:行号` 锚点的回答」，
答案里的锚点可点击跳转；**2026-09-18 起**还可把左侧文件树的文件/目录**拖到输入框**插入 `@相对路径` 引用（见下表三行）。DOM 骨架**静态写在 index.html**（index.html:222-270），
行为与渲染全部在独立模块 `js/agent-panel.js`（`window.MemoriaAgentPanel`，装配于 app.js:12849）。
结构**与左栏 `#-sidebar` 镜像**：同为 `#main` 的直系子节点（在 `#content` **之后**）、`flex-shrink:0`、
1px 分隔边框、宽度过渡；差别只在「贴右缘 / 边框在左 / 拖拽方向相反」。
**2026-09-18**：同级浮动折叠按钮 `#agent-dock-collapse-btn`（原 index.html:275）已删除，
展开/收起的唯一入口是顶栏右侧图标按钮 `#btn-agent`（见 §2.2）。

| 项 | 证据 | 说明 |
|---|---|---|
| 容器与宽度 | index.html:222；app.css:304-317 | `#-agent-dock` 默认 **22rem**、`min-width` **16rem**、`max-width` **34rem**；`background:var(--bg-secondary)`、`border-left:1px solid var(--border)`、`transition: width .18s ease`；**展开态不设 `overflow`**（与 `#-sidebar` 一致——设了会把它左缘外 3px 的拖拽柄裁掉一半，见「拖拽柄」行）。内容结构 = 顶部操作条 / 折叠设置区 / **历史行（M1c）** / 消息区（唯一滚动容器）/ 底部输入区，五段都是 `flex-shrink:0` 或 `flex:1` 的纵向 flex 子项 |
| 宽度单位是 rem | agent-panel.js:221-224、270-291 | JS 改宽写的是 `dock.style.width = <n>rem`（不是 px），故随显示设置的根 `font-size`（`uiScale`，见 §2.10）等比缩放，与 CSS 默认值同口径；拖动时用 `getComputedStyle(documentElement).fontSize`（`rootFontSize()`:221-224）做 px↔rem 换算 |
| 折叠（宽度归零） | app.css:320-328；agent-panel.js:253-259、270-291 | 加 `.-agent-dock--collapsed` ⇒ `width:0 !important`、`min-width:0`、去左边框、`overflow:hidden`、隐藏 `#agent-dock-resizer`。**只归零宽度、节点仍在 DOM**（不 `display:none`），故 `clientWidth===0` 可断言；状态可逆 |
| **折叠入口（2026-09-18 起唯一）** | index.html:99；agent-panel.js:294-296、1587-1588 | 顶栏 `#btn-agent`（见 §2.2）→ `toggleDock()`（294-296）—— 它把「隐藏态（手动折叠**或**空间不足自动隐藏）点击」统一解释为「请求展开」，故自动隐藏时点到的是展开分支（由 `setDockCollapsed` 拦下并提示，见下行「空间不足自动隐藏」）；按钮以 `aria-pressed` 反映是否可见（`applyDockCollapsed()`:253-259），title 恒为 i18n `agent.btnTitle`。**默认展开可见**（`dockCollapsed` 初值 false，agent-panel.js:217） |
| ~~展开/收起浮动按钮~~（2026-09-18 **已删除**） | ~~app.css:387-411；agent-panel.js:211-226~~ | 原 `fixed; top:45%; z-index:90; 20×40px` 的按钮及其定位函数 `positionDockCollapseBtn()`、跟随 `ResizeObserver`、`dockCollapseTitle`/`dockExpandTitle`/`dockNoSpaceTitle` 三键**全部移除**。改由顶栏 `#btn-agent` 承担；「空间不足」的说明改由 flash 文案 `agent.dockNoSpace` 承担（见下行） |
| 拖拽柄 | index.html:223；app.css:345-357；agent-panel.js:405-428 | 贴**左**缘外 3px、宽 0.375rem（`left:-3px` ⇒ 可抓区 3px 在 dock 内、3px 在外，故**展开态必须不裁剪**）、`cursor:col-resize`、hover 高亮主题色；**向左拖变宽**（期望宽度 = `innerWidth − clientX`，与左栏相反）；拖动中实时夹到 16–34rem（`clampDockRem`，agent-panel.js:226-229），**上界还受 `available` 约束**（`min(34rem, available)`，见下行「文档区最小宽度保护」）；拖动中实时生效、**`mouseup` 才落盘**（写的是期望宽度） |
| **文档区最小宽度保护**（期望 ≠ 生效） | agent-panel.js:209-244、270-291 | `CONTENT_MIN_PX = 360`（agent-panel.js:215）。`layout.agentDockWidth` 是**期望宽度**（rem，只在拖拽/显式操作时写盘）；每次布局变化按 `available = #main.clientWidth − 左栏生效宽度 − 360` 算**生效宽度**（`applyDockLayout()`:270-291）：手动折叠 → 0；`available ≥ 16rem` → `clamp(期望, 16rem, min(34rem, available))`；否则 → 0。左栏「生效宽度」= 未折叠时的实测宽度、折叠时按 0 计（`sidebarEffectivePx()`，agent-panel.js:232-237，直接量几何宽度即可覆盖两态）。生效宽度只写**内联 `width`**（rem），**不覆盖** CSS 的 min/max 规则；因此 `#content` 宽度 = `#main.clientWidth − 左栏 − dock ≥ 360`（推导：`#content` 是 `flex:1`+`overflow:hidden`，宽度即剩余空间；`*{box-sizing:border-box}`，memoria.css:2）。**前提**：仅当 `#main.clientWidth ≥ 左栏生效宽 + 360` 时该保底成立；再窄下去 dock 保持隐藏、`#content` 只剩更少的空间（左栏行为未改，不参与让位） |
| 空间不足自动隐藏（`.-agent-dock--auto-hidden`） | app.css:334-342；agent-panel.js:270-291、430-447 | `available < 16rem` 时加 `.-agent-dock--auto-hidden`（视觉同手动折叠：`width:0 !important` / 隐藏拖拽柄 / 去左边框），与 `.-agent-dock--collapsed` **互斥**。它是**派生态**：**不写盘、不改用户期望值**，窗口变宽即自动还原到期望宽度（无需用户再点）。**2026-09-18 起不再有"三态 title"**：顶栏按钮 title 恒为 `agent.btnTitle`，隐藏原因只在点击展开时才由 flash 说明。**此时点顶栏 `#btn-agent` 不会展开**：`setDockCollapsed(false, …)`（430-447）检测到自动隐藏即 `showFlashInfo(agent.dockNoSpace)` 后返回，**不挤压文档区**、也不写盘（`toggleDock()`:294-296 把"隐藏态点击"统一解释为"请求展开"，故自动隐藏时点到的是"请求展开"分支而非折叠分支）。harness 实测：自动隐藏态点顶栏按钮 → flash「空间不足：对话栏保持隐藏…」且 `clientWidth` 仍 0 |
| 生效宽度的重算时机 | agent-panel.js:1590-1599 | **ResizeObserver 为主**：`#main`（视口/`uiScale` 改根字号）+ `#-sidebar`（左栏宽度拖拽、折叠/展开）。另接 `window.resize`（`uiScale` 由 display-settings.js:97 显式派发）。折叠/展开与顶栏按钮走 `applyDockLayout()`（agent-panel.js:270-291）；dock 拖拽过程中逐帧 `applyDockLayout()`（:421）；语言切换由 `MemoriaI18n.addRefresh` 同步按钮 aria 与状态栏文案（:1602-1610）——**2026-09-18 移除**了跟随浮动按钮位置的第三个 `ResizeObserver`。**未**在 `app.js` 的左栏拖拽/折叠代码里挂钩子（左栏行为零改动） |
| 布局持久化 | agent-panel.js:304-315、450-460 | 键在 `config/ui-settings.json` 的 `layout` 段：`layout.agentDockWidth`（数字，**rem 数值**，如 `22`——**期望宽度**）与 `layout.agentDockCollapsed`（bool，**只记手动折叠**）。启动 `hydrateDockLayout()`（450-460）读回；拖动结束/手动切换折叠时 `saveDockLayout()`（304-315）落盘。⚠️ **自动收缩/自动隐藏一律不回写盘**（这是上一轮硬规则：窗口临时变窄不会污染用户期望值）。⚠️ **必须先读旧 `layout` 再整体写回**：后端 `save_ui_settings` 是**顶层浅合并**（`storage/ui_settings.py:58-75`），直接传 `{layout:{agentDockWidth}}` 会把整个 `layout` 换掉、**抹掉 `layout.sidebarWidth`**（左栏宽度）——`saveDockLayout()` 的 `get_ui_settings` → 合并 → `save_ui_settings` 就是为规避它（harness 已断言 `sidebarWidth` 保持不变；M1 收尾新增的顶层 `agent` 段偏好走同套路的读-改-写，但**两步写** `writeAgentPrefs()`:361-366——先 `agent:null` 迫使后端整体替换、再写目标对象，因为嵌套浅合并**无法删除键**，而面板要删旧全局键与陈旧库条目） |
| 层级关系 | 对比 app.css:4587（`.-modal`）、2396（搜索面板 z-index:6 的包裹层）；§2.9 表 | dock 在 `#main` 的**普通流**内、自身**无** `z-index`（它在文档区内，不可能盖住任何浮层）。**2026-09-18**：原浮动按钮（`z-index:90`）已删除，dock 段落里不再有任何 `position:fixed` 节点 ⇒ 顶栏（`#toolbar` z-index:50）与弹窗/搜索面板/右键菜单/`#-flash-host` 的层级关系不再涉及 dock。`#status-bar`（index.html:274）在 `#main` **之外**，与 dock 不重叠（harness 实测：`#status-bar` top 与 dock 底相接） |
| 顶部操作条 | index.html:224-233；app.css:359-394 | `#agent-model-label`（模型名 + 关网时的「出网已关」尾注，由 `applyConfigToForm()`:1121-1149 写入）+ `#agent-net-toggle`（checkbox，文案「出网」）+ `#agent-settings-toggle`（`.-config-btn`，带 `aria-expanded`/`aria-controls`） |
| 折叠设置区 | index.html:234-255；app.css:395-440；agent-panel.js:1484-1491 | 默认 `.hidden`；点「设置」按钮 `classList.toggle("hidden")` 并同步 `aria-expanded`（**就地折叠，不弹窗**）。字段：`#agent-base-url` / `#agent-model` / `#agent-api-key`(type=password) / `#agent-timeout` + `#agent-save-config`；底部 `#agent-config-path` 显示 `config/agent.json` 相对路径（`agent.settings.path`）。**2026-09-17 修复**：加 `max-height: min(24rem, 45vh)` + `overflow-y:auto`（app.css:402-403）——此前无上限，矮窗口展开后「保存」按钮被顶出可视区且无法滚动（harness 271px 高窗口下现已可滚到） |
| 密钥处理 | index.html:245；agent-panel.js:1121-1149、1180-1204 | 输入框**永不回显**密钥：保存后清空，已存密钥只作 placeholder（`agent.settings.apiKeySet` 带 `{masked}`，掩码由后端 `mask_secret` 生成）；留空即「不修改」（后端 `save_config` 同语义，`llm/config.py:309-313`）；保存请求仅在输入非空时带 `api_key` |
| **历史会话下拉**（M1c；M1 收尾加删除按钮与 `capped` 标记；**M2 起标签改用后端折叠标题**） | index.html:256-260；app.css:441-478；agent-panel.js:893-968 | 独立一行 `.-agent-history`（label「历史」+ `<select id="agent-history">` + **M1 收尾新增**的 `#agent-history-delete`，见下两行）。填充 `agent_sessions_list`（按修改时间倒序、最多 30 条）；首个选项恒为「（新会话）」(值 `""`)，其余为 `{标签}（{n} 轮）`；**标签自 M2 起取 `session.title \|\| session.preview`**（agent-panel.js:905-912）—— 后端 `title` 从 M1c 起就返回但前端此前只用了 `preview`，M2 接线后显示的是 `session/title` 折叠出的**会话标题**（模型标题或确定性兜底，口径见 [10 篇 §2.15](./10-data-layout-and-host-embedding.md)），没有标题事件的**老会话**仍回落「首条提问前 40 字」；后端 `capped:true` 的会话（turn 计数被 2 MiB 扫描上限截断）在该项后追加 `agent.history.capped`（「（已截断）」）。**选中某条 → `loadSession()` 调 `agent_session_load` 灌进消息区并把 `sessionId` 设为它（下一句即续聊）；选「（新会话）」= `clear()`**（重置 `sessionId`，旧会话仍在磁盘上、留在列表里）。空列表/未开库 ⇒ `disabled` + `agent.history.empty` 占位。刷新时机：`init` / 展开 dock / 每次提问结束 / 切换知识库 / 删除后 / 语言切换（就地重绘，不重新请求）。**列表与载入两个 RPC 只读、不写盘**（口径见 [10 篇 §2.15](./10-data-layout-and-host-embedding.md)） |
| 消息区 | index.html:261；app.css:480-545；agent-panel.js:470-653 | `#agent-messages`（`role="log"`、`aria-live="polite"`）：用户气泡 `.-agent-msg--user`（主题色底、`max-width:85%`、`align-self:flex-end` 靠右）/ 助手气泡（`--bg-secondary`、占满栏宽）；**用户气泡正文 2026-09-18 起改用 `linkifyUser()`:516-531**（先按 `@路径` 切分再逐段转义，渲染成 chip，见下行「`@相对路径` chip」）；助手正文把 `路径.md:行号`（含反引号包裹）渲染成 `.-agent-anchor` 可点节点（`linkify()`:470-486），末尾另附 `.-agent-source` 来源条（后端 `anchors` 数组，`sourcesEl()`:633-653）；历史会话载入的 assistant 气泡同样带锚点（后端按轮归属）。**M1 收尾新增**「（已停止）」标注：`messageEl()`:601-630 在 `rec.stopped` 时追加 `.-agent-msg-note.-agent-stopped`（次要色，app.css:533-534），与错误条（同基类、错误色）区分。字号按 dock 宽度定为 **0.8125rem**（= 正文基准，app.css:500），此前挤在左栏时是 0.75rem。**2026-09-19 起助手气泡渲染 Markdown**（此前只有「转义 + 锚点 + `<br>`」）：`messageEl()` 正文一律交 `renderBody()`（agent-panel.js:1645-1651）——用户气泡仍走 `linkifyUser()`，**助手气泡走 `renderAssistantBody()`（1709-1728）** = `window.marked`（`vendor/marked.min.js`，**与预览同一份** `{gfm:true, breaks:true}`）→ **白名单净化** `sanitizeHtmlInto()`（1666-1683：只留 `MD_KEEP_TAGS`、**全部属性一律丢弃**、`MD_DROP_TAGS`（`script`/`iframe`/`img`/表单/媒体/SVG…）连内容一起丢）→ 文本节点锚点化 `linkifyNodes()`（1686-1706，锚点节点由 `anchorEl()` 生成 ⇒ 与旧 `linkify()` **同一份 DOM 形状**，样式与点击委托都不用改）；**任一步抛错或 `marked` 未加载 ⇒ 退回 `linkify()` 纯文本**；**流式期间仍是纯文本**（`applyDelta` 用 `textContent`），**定稿才渲染一次**（避免每 250ms 轮询重排）。窄栏排版覆盖见 `app.css:4906-4950`（首要一条：气泡容器原本 `white-space:pre-wrap`，而 marked 产物块间带换行 ⇒ 必须回 `normal`，否则多出空行）。**2026-09-19 锚点匹配修复（同一轮）**：`ANCHOR_RE`（117，**行号未变**）原先的路径字符集只排除 **ASCII** 标点，于是中文里的「见：foo.md:7」会把「见：」吞进 `data-agent-file`（**点开错文件**）、「、foo.md:3」把顿号吞成路径开头、含**全角冒号**的 `foo.md：3` 整条不匹配、区间 `7-9` 只留 `7`（与原文不符）——用户报告的"定位不准"与"渲染不全"**同源**于此。现在：路径字符集**显式排除中日韩标点与全角符号**、分隔符接受 `[:：]`、第 2 组改为「**行号或区间原文**」（`7` / `7-9`；显示与 `data-agent-line` 同源，点击时 `parseInt("7-9")=7` 取**起始行**）——`linkify()`（470-486）与 `linkifyNodes()`（1686-1706）共用同一 `ANCHOR_RE`，两处取证见 §7 |
| 锚点跳转 | agent-panel.js:1464-1477 → app.js:1412-… | 点锚点调门面 `openFile(file, {navSource:"agent", lineHint})`；**`kpId` 优先于 `lineHint`**（app.js:1514-1521 与 1522-1527）——本面板只用 `lineHint`（锚点是行号而非 KP）；未打开的文件会经 `load_document` 正常打开并高亮该行。目录 chip 走 `revealDir` 分支（见下行） |
| **`@相对路径` chip 渲染（用户消息，2026-09-18 新增；同日随 `@` 语法对齐重取锚点）** | agent-panel.js:119-125、493-531；app.css:546-574 | 用户消息改由 `linkifyUser(text)`（516-531）渲染：先按 `MENTION_RE = /(^|\s)(@"([^"]*)"?|@(\S+))/g`（125）切分，**不先整体 `esc`**（避免路径里的 `&` 被二次转义成 `&amp;amp;`），非引用段换行转 `<br>`；**前导空白（分组 1）不进 chip**、原样留在文本里，故 chip 从 token 起点开始；带引号 / 裸路径分别取分组 3/4，匹配段交 `mentionChip(path, isDir)`（493-509）产出 `.-agent-mention`（目录再加 `.-agent-mention--dir`）。**刻意与答案里的 `.-agent-anchor`（纯文字 + 下划线）不同**：chip 是带边框底色的"标签块"（实线=文件 / 虚线+次要色=目录，app.css:546-574），一眼区分"这是我拖进来的文件"。title 走 i18n `agent.mention.openTitle` / `revealTitle`（zh-CN.js:627-630 / en.js:628-631）。**口径（2026-09-18 同日改）**：`@` 必须是**一个 token 的开头**（行首或前导空白）＋ 含空格的路径走 `@"..."`（收尾引号可缺）——故邮箱 `a@b.com`、行内 `x@y` **不会**被识别为引用；答案锚点的 `ANCHOR_RE`（117）仍是"不含空白"的**独立**口径，二者**不再同口径**（见 §5 坑 17） |
| **chip 点击行为（2026-09-18 新增）** | agent-panel.js:1464-1477、1570-1584；file-tree.js:502-519 | 委托挂在 `#agent-messages` 的 click/keydown（1570-1584）→ `onAnchorClick(target)`（1464-1477）：带 `data-agent-dir` 的**目录** chip → `window.MemoriaFileTree?.revealDir?.(file)`；**文件** chip 复用锚点那套 `data-agent-file` → `openFile`。`revealDir(dirPath)`（file-tree.js:502-519）展开目标目录**自身与全部祖先** → `renderFileTree()` → 对命中 `data-dir-toggle === p` 的 `.-tree-dir-head` 调 `scrollIntoView({block:"nearest"})`；导出对象为 `{init, render, expandToPath, revealDir}`（file-tree.js:521-526） |
| **文件树拖拽插入（2026-09-18 新增；同日随 `@` 语法对齐重取锚点）** | file-tree.js:41、168、185、229-248；agent-panel.js:127-129、536-599、1530-1568；app.css:629-638 | **发送端**（file-tree.js）：`.tree-dir-head`/`.tree-item` 均 `draggable="true"`（168、185），`bindFileTreeInteraction` 用**属性赋值** `el.ondragstart`（229；不用 `addEventListener`——该函数每次 render 都跑而 `el` 常驻）写载荷：自定义 MIME `DRAG_MIME = "application/x-memoria-path"`（41）＝ `{path, kind:"file"|"dir"}` 的 JSON，另写 `text/plain`（目录带尾斜杠）。**接收端**（agent-panel.js）：`init()` 在 `#agent-input` 上记录**上次光标位置** `inputCaret`（129；`keyup/click/select/input/blur` 时更新，1537-1544——失焦后 `selectionStart` 归 0），并在 **`#-agent-dock`（= 整个对话栏，回退 `#agent-input`）** 上绑 `dragover`/`dragleave`/`drop`（1545-1568）——落点**不限于那个小输入框**（精准落到 textarea 上手感太别扭），消息区 / 设置区 / 头部任意子块都算（`#-agent-dock` 自身无既有 `box-shadow`，见 app.css:304-317，故高亮用它）。**只认自定义 MIME**（`hasMentionPayload` 536-540）：普通文本/文件拖放不 `preventDefault`（保留浏览器默认）；dragover 时给对话栏加 `.-agent-dock--drop`（app.css:629-638：dock 内侧主题色描边 + 输入框同色描边，提示「会插到光标处」），`dragleave` 仅在 `relatedTarget` 落到 dock 之外时才清高亮（子元素之间移动也触发 `dragleave`，不判会闪）。`drop` → `readMentionPayload`（543-561）→ `insertMention(path, kind)`（578-599）：插到 `inputCaret` 处，**前面缺空白补一个空格、后面已紧跟空白则不再补尾空格**，插入后光标落在 `@路径` 之后；token 由 `formatMention`（569-572）生成——**只在该路径含空白时**用 `@"..."`（目录也**闭合**引号：`@"dir with space/"`，与上游对目录留开引号不同），否则 `@plain.md`、目录 `@sub/dir/`（带尾斜杠）。**后端呼应**：`services/agent/prompt.py` 的独立段落 `FILE_REFERENCE_SECTION`（194-218；**只在本次请求工具集含 `read_document` 时注入**，门控 262-263）明确"用户消息里以 `@` 开头的 token 是他明确圈定的库内路径（**目录以 `/` 结尾** → 用 `search_kb` 检索；其余 → 用 `read_document` 读取，**真正读过之前不得声称已经看过**；`@"..."` 表示含空格）"⇒ 该引用不是纯视觉装饰 |
| 输入区 | index.html:262-270；app.css:604-648；agent-panel.js:1530-1569 | `#agent-input` 多行 `textarea`（Enter 发送 / Shift+Enter 换行，`isComposing` 期间不发送以兼容中文输入法）；三按钮：`#agent-send`（primary）/ `#agent-stop`「停止」（生成中才显示，**真取消**，见下）/ `#agent-clear`（`margin-left:auto` 靠右，清空即开新会话）；`#agent-status` 状态行（`aria-live="polite"`）显示「生成中… Ns / 用量 / 会话 id / 错误 / 已停止」。**2026-09-18**：本区承担**光标记忆**（`inputCaret`）；拖拽**落点**已放宽到整个对话栏、不限于本区（见上「文件树拖拽插入」行）。**2026-09-19 新增：输入框上方的状态 bar** `#agent-statusbar`（`index.html:262` 同一行内、`agent-panel.js:1730-1789`、`app.css:4952-4984`）—— 结构 = **状态点** `#agent-statusbar-dot`（`data-state` ∈ `busy`/`off`/`error`/`idle`，优先级 **busy > off > error > idle**；「出网关」刻意排在「出错」之前，因为关出网会把 `#agent-status` 置红、但用户看到的事实是"不能发"而不是"出故障"）+ **事实串** `#agent-statusbar-facts`（`模型 <b>名</b> · 出网｜出网已关 · （新会话）｜会话 …尾8位 · 历史（N 轮）`）。分工：**事实与运行态**归 bar，**消息级长文案**（生成中 Ns / 错误原文 / 已停止）仍归下方 `#agent-status`，两者不重复同一句话。**首版刻意不新增 i18n 键**（全部复用 `agent.settings.model` / `agent.model.none` / `agent.net.label` / `agent.model.netOff` / `agent.status.session` / `agent.history.none` / `agent.history.option`）：往 `zh-CN.js` 的 `agent` 段插键会推位其后所有行、牵动 01/02/04/06/07/08/09 篇十余处 `zh-CN.js:<行号>` 锚点，等措辞定稿再一次性补专用键。**挂接方式**：在 IIFE 尾部**包装本模块自身的 `renderMessages()` / `setStatusText()` / `applyConfigToForm()`**（`agent-panel.js:1782-1789`）—— 这三个入口已覆盖全部状态流转（提交/轮询/定稿/出错/停止/清空/载入/换库/保存配置/换语言），且**不改动上方既有函数的任何一行** ⇒ 本篇其余 `agent-panel.js:<行号>` 与 `index.html` 行号锚点全部保持有效（bar 的标记也刻意压在 `.-agent-composer` 那一行内，净增 0 行）。**待完善**：事实项、措辞、点击行为等待用户指引（台账 `todo.md §13` **AG05**） |
| 伪流式与等待计时 | agent-panel.js:113-114、1243-1252、1254-1270、1272-1391 | `agent_ask_start` 提交后每 **250ms**（`POLL_INTERVAL_MS`，113-114）轮询 `agent_ask_poll(job_id, cursor)`，`delta` 追加进当前助手气泡（`applyDelta()`:1243-1252 流式期间用 `textContent` 追加、`finalizeMessage()`:1254-1270 定稿时再 linkify 重绘）；`done` 时以后端 `answer` 覆盖流式累积文本（loop 每轮以当轮文本覆盖 `answer`，故工具轮前言不在最终答案里）。**M1c 起状态行带计时**：`startWait()/tickWait()/stopWait()`（842-861）每秒把状态行刷成「生成中… Ns」（`agent.status.thinking` + `agent.status.elapsed`），结束/出错/停止/清空/超时/换库一律 `stopWait()`。**M1 收尾起增量是真流式**：`llm/providers/openai_compatible.py:296-311` 改用 `response.read1(_READ_SIZE)`（`HTTPResponse.read(n)` 在「无 Content-Length / Connection: close」的 SSE 上会阻塞到 EOF，实测一次 3.6s 的流只在结束时返回一整块 ⇒ 增量投递与"取消立即停止消费"都失效；`read1` 至多触发一次底层读，SSE 帧一到即返回）。**M1 收尾后**确定性连接失败（连接被拒 / DNS / 证书）在后端**立即失败**（面板路径约秒级，不再是最长 ~28s），重试与失败分类见 [10 篇 §2.16](./10-data-layout-and-host-embedding.md) |
| 「停止」（**真取消**，M1 收尾语义变更） | index.html:266；agent-panel.js:1402-1426；`services/agent/loop.py:73-101` | 旧「忽略本次」的"丢弃结果"语义已废除。点停止顺序：① `epoch += 1` + `job = null` ⇒ 立即停止轮询、作废在飞回调；② 把**已生成的部分文本**留在当前助手气泡上并标注「（已停止）」（`agent.stopped`，`.-agent-msg-note.-agent-stopped` 次要色，非错误色）；③ 调 `agent_ask_cancel(job_id)` ⇒ 后端置 `CancelToken`（`threading.Event`）：`AskJob.cancel()` **立即**把作业收敛为 `done` + `stop_reason="aborted"`（`answer` = 当时已投递片段）并**释放单飞 busy**，工作线程在下个检查点（每轮迭代前 / 流式逐事件 / 每次工具调用后，`loop.py:295-299、248-250、380-383`）观察到取消后 `break` 并 `stream.close()`（关闭底层 HTTP 响应、不再收完）；`loop/end` 以 `stop_reason="aborted"` 正常落盘，**不抛异常**；④ 取消 RPC 返回后才放开发送按钮 ⇒ **停止后立刻可再提问、不会撞 `busy`**（实测停止往返 0.06s，见 §7 验证段）。取消是**协作式**的：阻塞中的 socket 读不会被抢占，最长等一个分片的到达 |
| 「清空对话」（生成中亦可用，M1 收尾起**顺带取消**） | agent-panel.js:1437-1460 | 清空气泡 + `sessionId = null`（= 开新会话；旧会话已在磁盘上、留在历史列表）+ **删掉当前库在 `agent.lastSessionByKb` 里的条目**（`clearLastSessionId()`:388-403，只删本库、不动别的库）。**生成中点它也作废在飞结果**（同样 `epoch += 1` 并 `job = null`），并**顺带调 `agent_ask_cancel(job_id)`**（M1 收尾：此前只丢弃结果、后端仍烧 token）；等取消返回后才放开发送按钮，故清空后立刻再提问不会撞 `busy`。`#agent-clear` 生成中**不禁用** |
| 世代号（epoch）作废机制 | agent-panel.js:179、1296、1306、1316、1324、1328、1331、1350 | 模块级 `epoch` 每次提问递增（`const myEpoch = ++epoch`，1296，并记进 `job.epoch`:1316）；提交与轮询回调均先比对 `epoch === myEpoch`（1306、1324、1328、1331、1350），不等即 `return`（丢弃响应、不写回任何状态）。「清空对话」「停止」递增 `epoch` ⇒ 在飞结果一律作废；作废后新提问用新 epoch 正常写回 |
| 删除会话（M1 收尾，**产品首次允许写知识库**） | index.html:259；app.css:474-478；agent-panel.js:869-890、1083-1117 | 历史行末的 `#agent-history-delete`（`.-agent-history-delete`，未选中具体会话时 `disabled`）；删除的是**当前下拉选中**的那条（`syncDeleteButton()`:869-880 维护文案与禁用态）。**两次点击确认**：首点文案变「再点一次删除」（`agent.history.deleteConfirm`）并起 3s 定时器，3s 内未再点即复位为「删除」（`resetDeleteArmed()`:883-890）；再点才真删（**不弹窗**）。调 `agent_session_delete(session_id, kb_path)`（只允许删 `<kb>/.memoria/agent/sessions/<id>.jsonl`）；删的是当前会话 ⇒ 复用 `clear()` 回到「新会话」态（清空气泡 + 删本库偏好条目），随后刷新历史列表并 flash「会话已删除」 |
| 恢复上次会话（M1 收尾；**2026-09-18 起按库记**） | agent-panel.js:326-403、1028-1045、976-1015 | 磁盘偏好 `config/ui-settings.json` 的**顶层** `agent.lastSessionByKb`：`{ "<库标识>": "<会话 id>" }`，**每个库只存自己**的上次会话（提问成功 `setLastSessionId()`:372-385 / 载入 `loadSession()`:976-1015 / 自动恢复时写；清空时删本库条目）。库标识由 `kbKey()`:326-329 归一化（`/`→`\`、去尾分隔符、Windows 下 `toLowerCase`）。**面板打开**（`init` / dock 展开）或**切换知识库**（`app.js` 在 `initKb:454` / `openKbAt:564` / `closeKb:602` 三处调 `MemoriaAgentPanel.onKbChanged()`，共 3 行）时，取**当前库**的条目，若该会话文件**仍存在**即 `agent_session_load` 自动载入并设为当前会话（下一句即续聊）；不存在/非法 ⇒ **静默忽略**（不报错、不提示，`loadSession(id, silent=true)`）并**清掉该陈旧条目**（`clearLastSessionId()`:388-403）。同一（库, id）只尝试一次（`restoredKey` 幂等，`restoreLastSession()`:1028-1045）。**旧全局键 `lastSessionId` 兼容＝一次性迁移**：映射里无本库条目但存在旧键时，只有该会话在**当前库**下确实能载入才认领（写映射 + 删旧键），否则不迁移也不删（留给它所属的库）。写入走 `writeAgentPrefs()`:361-366 的**两步写**（先 `agent:null` 再写目标对象；后端嵌套浅合并**无法删键**），**绝不覆盖 `layout` 段** |
| 换库 / 关库（**无条件重置**，2026-09-18 修正） | agent-panel.js:1055-1080、1323-1363 | `onKbChanged()`:1055-1080 由 `app.js` 在 `initKb:454` / `openKbAt:564` / `closeKb:602` 显式调用。判据是**面板自持的 `renderedKb`**（:186，当前气泡/下拉属于哪个库；载入会话与提问成功时更新）——**只要 `renderedKb !== 当前库` 就无条件重置**（含 `renderedKb` 为空但屏上有气泡的情况）：清空 `messages`、`sessionId=null`、`sessionKb=""`、`streamingEl=null`、**状态栏用量格与本会话累计**（`resetStatusUsage()`:833-837）、状态行，并**重绘历史下拉**（`refreshHistory()`:949-968，只列当前库）。⚠️ **不得再用 `sessionKb` 作"是否重置"的判据**：它只在**会话真正建立**时才赋值，故「上一轮失败只留下气泡（未建立会话）」时它仍为 `""`，会让旧气泡残留（**原缺陷**）。**在飞作业属于别的库时**：先 `epoch += 1` 作废在飞回调 + `job=null` + 释放 `busy`，并并发调 `agent_ask_cancel(job_id)`（不阻塞 UI，语义同「清空对话」——该作业结果必然作废、不该继续烧 token）；随后对**当前库**尝试静默恢复上次会话。关库（`kb=""`）同样走无条件重置 ⇒ 面板空态，且**不动任何库的 `lastSessionByKb` 条目**。轮询期间换库另有一层兜底：`poll()` 发现 `state.kbPath` 变化即丢弃本次结果并提示 `agent.status.dropped`（:1323-1363） |
| 发送前置 | agent-panel.js:1272-1321 | 未开库 / 未输问题 / `enabled=false` 时**就地报错**（状态行转红 + flash 卡片），不静默失败；前端已 `busy` 时直接返回不重复提交（后端仍有单飞约束）；`enabled=false` 时发送按钮 `disabled` 且带 title（`renderComposer()`:1151-1159） |
| 错误呈现 | agent-panel.js:132-157、680-689、1180-1204 | 后端 8 个 agent RPC 的错误按**稳定 code** 映射文案（`ERR_KEYS`:132-157，M1c 新增 `unknown_session`/`session_failed`，M1 收尾新增 `cancel_failed`）。**具体 code**（`busy`/`no_base_url`/`net_disabled`/`unknown_job`/`unknown_session`…）只显示本地化文案；**兜底 code**（`ask_failed`/`config_error`，`GENERIC_CODES`:160）额外拼后端原文（`fullErrorText()`:702-708）——LLM 失败的真实原因（传输/认证/HTTP/确定性连接失败）只存在于 `error` 文本里；未登记 code 一律回显原文。flash 卡片同理（标题=本地化、详情=原文，app.js:344-358） |
| 语言切换 | agent-panel.js:1602-1610 | 静态节点由 `MemoriaI18n` 刷新；动态消息/状态行 + 历史选项（含禁用态占位）+ 删除按钮文案（含二次确认复位）+ **顶栏 `#btn-agent` 的 `aria-pressed`**（title 由静态节点 `agent.btnTitle` 刷）+ 状态栏用量格文案由 `MemoriaI18n.addRefresh` 重绘（与 kb-check.js 同套路）。**2026-09-18**：原浮动按钮的三态 title 随语言刷新已随按钮一并删除 |
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

> 推论（`uiScale=1`、左栏默认 17.5rem=280px 时）：应用最小窗口 **1000×600（2026-09-18 起，原 900×600；理由见 §2.1）** 下 `available = 1000−280−360 = 360 ≥ 16rem` ⇒ dock 仍可见（22rem 以内可全宽显示）；原 900×600 下 `available = 260` 恰在 16rem 下限之上（约 16.25rem），左栏一旦宽于 ≈283px 就会触发 dock 自动隐藏——这正是本轮把最小宽度提到 1000 的原因。见 §7 待拍板项。
>
> 上一轮（2026-09-17 第二轮）在 876×271 视口做出的「设置区可滚到保存按钮」断言，在本轮行为下**需在 ≥917px 宽窗口才可复现**（876 宽时 dock 已自动隐藏）——那是**行为变更的副作用，非缺陷**：设置区自身的 `max-height + overflow-y:auto`（app.css:402-403）未改。

后端 8 个对话 RPC（`agent_get_config` / `agent_save_config` / `agent_ask_start` / `agent_ask_poll` /
`agent_ask_cancel` / `agent_sessions_list` / `agent_session_load` / `agent_session_delete`；
中间两个为 M1c 新增的**只读**会话历史，2026-09-18；`agent_ask_cancel` 与 `agent_session_delete`
为 **M1 收尾（2026-09-18）新增**——前者是真取消，后者是**产品首次允许写知识库**（仅限会话目录））、
续聊语义（`agent_ask_start` 的**追加可选参数** `session_id` ⇒ 后端按会话回放历史）、
`agent_ask_poll` 新增 `cancelled` 字段与 `agent_sessions_list` 新增 `capped` 字段（**只增不改**）、
配置落点 `config/agent.json`、偏好落点 `config/ui-settings.json`（`layout` 段 + **新增顶层 `agent` 段**）
与会话事实源 `<kb>/.memoria/agent/sessions/*.jsonl`、以及 **M2（2026-09-19）的长会话压缩**
（会话事件面新增 `compaction` 记录；**不新增 RPC、不 bump 会话格式版本**，对面板唯一可见影响是
状态栏用量格不计压缩开销）
见 [10-data-layout-and-host-embedding.md](./10-data-layout-and-host-embedding.md) §2.15。


### 2.5 文档区

| 项 | 证据 | 说明 |
|---|---|---|
| 层级 | index.html:151-217；app.css:3490-3501 | `#content` > `#tab-bar`(152) + `#viewer`(155)；`#editor-wrap` 可见时 `#viewer` 变无内边距、`overflow:hidden` 的纵向 flex（`:has()`） |
| 欢迎页 | index.html:156-160；memoria.css:475-497 | 标题 `Memoria`（运行时追加版本号）、副标题 `welcome.tagline`、`#btn-welcome-open` 打开知识库 |
| 文件信息 / 预览状态条 | index.html:163、210；app.js:1542-1544；app.css:3513-3518、4122-4126、4545-4548 | `#file-meta` 只显示**侧车 description**（`doc.sidecar.description`）；`#preview-status` 初始 `hidden`，警告态加 `.warn` |
| 格式工具栏 | index.html:164-196；app.css:3544-3606 | `.-format-bar`（`role="toolbar"`）：B / I / 分隔 / H▾（6 色 + 无色 + 添加颜色）/ 色▾（7 色 + 无色 + 添加颜色）/ 分隔 / `#btn-insert-image`（初值 `disabled`，195）；颜色下拉为 `position:fixed` + `z-index:10050`，靠 `.-fmt-dropdown` 加 `.open` 显示 |
| 块编辑栏（与格式栏互斥） | index.html:197-200；app.css:4194-4224；edit-handler.js:1010-1013、1134-1137、1545-1550 | 二者共用 `#editor-header` 同一位置：进块编辑时格式栏 `hidden`、块编辑栏显示，退出时反向 |
| 视图模式 | index.html:201-205；app.css:3520-3541、3862-3868 | `.-view-btn` 三键（源码/预览/分栏）：实现为 `#editor-split` 上换 `view-source|view-preview|view-split` 类；当前模式写 `localStorage["-view"]`（app.js:1571-1573），初值读同键、默认 `source`（app.js:20） |
| 编辑模式开关 | index.html:206-208；app.css:2457-2459；edit-handler.js:59-98 | `#edit-mode-toggle`（`role="switch"`，复用 `-toolbar-search-scope` 样式）+ `#btn-edit-mode`；**默认开启**（edit-handler.js:60）；关闭时 `#preview` 的 `contentEditable=false`、源码行全部只读并加 `.-readonly`（edit-handler.js:80-118），并强制禁用图片插入按钮（edit-handler.js:89-92） |
| 双窗格 | index.html:212-217；app.css:3850-3894 | `#editor-pane > #editor`（等宽字体，字号 `--editor-font-size`）、`#preview-pane > #preview`（`markdown-body`，字号 `--preview-font-size`） |

### 2.6 知识点面板（仅定位）

`#sidebar-kp-block`（index.html:137-147）位于左侧栏 `#sidebar-body-split` 的**下半区**，与导航面板以 `#sidebar-nav-kp-resizer` 分隔（见 §2.3）。内部为 `.sidebar-toolbar.-kp-toolbar`（标题「知识点」+ `#kp-count` + `#btn-config`「配置」+ `#btn-kp-new`「新建」）与 `#kp-list`（`.-panel -kp-panel`）。行为细节（KP 列表、hover、弹窗三 Tab、范围编辑）归 [05-knowledge-points.md](./05-knowledge-points.md)。

### 2.7 状态栏

| 项 | 证据 | 说明 |
|---|---|---|
| 容器与**最左**路径格 | index.html:274-279；memoria.css:591-602 | 高 1.375rem、主题蓝底、白字、`flex-shrink:0`（memoria.css:591-600）；**2026-09-18 起 `#status-kb` 是 `#status-bar` 的第一个子元素（最左）**，其后依次 `#status-info`:276 / `#status-stats`:277 / `#status-agent`:278。`#status-info` 为 `flex:1` 单行省略（memoria.css:601），初值「就绪」（`app.status.ready`） |
| 右段统计块 | app.js:290-342；i18n/zh-CN.js:484-489 | 由 `renderStatusStats()` 以 ` · ` 连接：① 检查统计（有 error/warn 时，文案取自 kb-check.js 的 `statsChunk`，并打 `data-kb-check="1"`）；② 全库检查通过（`check.stat.pass`，且无文件级统计）；③ 图谱待办 warn 数；④ 当前文件统计 `app.stat.kpLines`「{kp} KP · {lines} 行」，若有 sidecar 问题再追加 `app.stat.errors/warnings` + `app.stat.sidecar`；⑤ 图谱审计问题（文件级优先，其次全库） |
| **Agent 用量格** `#status-agent` | index.html:278；app.css:2123-2128；agent-panel.js:202-203、754-830、1364、1522-1528、1448、1608 | **2026-09-18（上一轮）新增，为 `#status-stats` 之后的独立 span**（不与统计块共用节点，**`#status-stats` 的语义与点击行为完全不变**）。显示**最近一轮**的紧凑摘要：`↑8.7k ↓233 · 命中 62%`（`↑` = 输入 `prompt_tokens`、`↓` = 输出 `completion_tokens`；数字 ≥1000 用 k 缩写一位小数）。**命中率未知时省略该段**（绝不显示 0%）；`title`（悬停）给计费拆分多行文本：本轮输入/输出/合计、**命中/未命中/命中率**、是否估算、**本会话累计**（含命中的拆分）。点击 ⇒ `MemoriaAgentPanel.open()` 展开右侧对话面板（`open()` 内部按空间不足规则处理，**不新增弹窗**；绑定 1522-1528）。**无 agent 活动时该 span 为空**（`:empty { display:none }`，不占位）。数值来源：`agent_ask_poll` 的 `usage`（含 `cache_read_tokens`/`cache_miss_tokens`）；本会话累计由面板**自行累加**（`addSessionUsage()`:754-778 / `renderStatusUsage()`:781-830，不新增 RPC 轮询），「清空对话」/载入历史会话/切换知识库时复位（历史会话视图不含 usage，无法回算旧用量）。**压缩（M2）的摘要调用用量不进本格**：它记在会话 `compaction` 事件的 `usage` 里，而本格口径只认 `loop/end`（`agent_ask_poll.usage`）⇒ 压缩开销对用量格**不可见**（见 [10 篇 §2.15/§2.17](./10-data-layout-and-host-embedding.md)） |
| **知识库路径格** `#status-kb`（2026-09-18 新增；同日移到**最左**并去重） | index.html:275；app.css:2137-2145；app.js:379-389 | 底栏**最左**的独立 span（`#status-bar` 的第一个子元素，在 `#status-info` 之前）。由 `showKbIndicator(path)` 写 `textContent` 与 `title`（**title = 完整路径**，`textContent` 可被省略号截断）：`#status-kb { margin-right:.75rem; max-width:40%; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }`（**2026-09-18 由 `margin-left` 改为 `margin-right`**，其余不变），**空路径 ⇒ `:empty{display:none}` 完全隐藏、不占位**。**全底栏只此一处显示路径**：`initKb`/`openKbAt` 的 `setStatus(...)` 已**不再把路径当第二参数**（原 `setStatus(T("app.status.kbLoaded"), state.kbPath)` / `setStatus(T("app.status.kbOpened"), path)`，现为 app.js:484 与 app.js:576 的单参调用）⇒ `#status-stats` 里不再混入那份重复路径。**不是标题栏**：不带 `pywebview-drag-region`、不参与窗口拖动（原顶栏 `#kb-indicator` 的拖拽语义已随节点删除）。同一函数还同步「文件 → 关闭知识库」的 `disabled`（未开库即禁用）。调用点：`initKb` 恢复态（app.js:477）、无库态（app.js:496）、开库（app.js:568）、关库（app.js:621） |
| 样式与点击（统计块） | app.css:2063-2086、2092-2102；app.js:12382-12390 | `.-stat-error` 红（app.css:2074）、`.-stat-warn` 黄（app.css:2079）、`.-stat-ok` 次色（app.css:2084）；命中图谱审计时 `#status-stats` 加 `.-status-clickable`（黄 + 下划线 + 指针，app.css:2063-2068）；点击时 `data-kb-check` 优先 → 检查弹窗，否则 `data-graph-audit-goto` → 跳到首个图谱审计问题（**本条只描述 `#status-stats`；`#status-agent` 与 `#status-kb` 见上两行**） |

### 2.8 闪烁提示（flash，瞬时反馈）

| 项 | 说明 |
|---|---|
| 宿主 / 位置 / 层级 | `#-flash-host`（index.html:284）；fixed，`left:50%`、`bottom:2rem`，纵向列；`z-index:12000`（app.css:2571-2582）⇒ **高于弹窗**，弹窗内也能看见 |
| 时长 / 并发 | 默认 3800ms + 280ms 淡出（app.js:363-371）；可多条堆叠（host 为 flex 列，追加节点） |
| 变体 / 入口 | `.-flash-error` 红边 + 标题/详情两行（app.css:2584-2596）、`.-flash-info` 绿边（app.css:2602-2614）；`showFlashError(msg, detail)`（app.js:344）、`showFlashInfo(msg)`（app.js:360），两者均已挂在 `MemoriaApp` 门面上供子模块调用 |
| 与底栏的分工 | `setStatusError(msg, detail)` = `setStatus` + `showFlashError`（app.js:374-377）⇒ 底栏 + 卡片**双写**；`setStatus(msg, undefined, {error:true})` 只把底栏转红、不弹卡片；「导入」未开库是唯一**只弹卡片、不写底栏**的入口（import-flow.js:44） |

> **2026-09-16 收敛为单通道**：原先另有一个 `js/toast.js` 轻提示组件（`#-toast`，z-index 30000），其唯一调用点（检查弹窗「复制报告」）与 flash 卡片**同文案双通道**，底部会叠两个一模一样的框。该模块、`#-toast` 节点与其 CSS 已删除，瞬时反馈一律走 flash 卡片（成功绿边 / 失败红边）。

### 2.9 弹窗与层级

通用结构（index.html:286-432 共 9 个）：`.-modal[.hidden]` > `.-modal-backdrop` + `.-modal-box[变体类]` > `.-modal-header`（标题 + `.-icon-btn` ×）/ `.-modal-body` / `.-modal-footer.-btn-bar`。

现有变体类：`#kp-modal`、`#config-modal`（`-modal-tabbed`）、`#assist-modal`（`-modal-assist`）、`#check-modal`（`-modal-check`）、`#settings-modal`（`-modal-settings`）、`#link-modal`、`#import-conflict-modal` / `#import-result-modal`（`-modal-import-conflict|-result`）、`#kb-agent-modal`（复用 `-modal-import-conflict`）。另有**运行时动态创建**的 `.-modal`：文件树输入/确认框（file-tree.js:263-300；app.js:706-728）。

| 层级值 | 归属 | 证据 |
|---|---|---|
| 1 | 面板内装饰（角标、范围带、辅助线） | app.css:1420、1431、2175、3999 |
| 2–6 | 顶栏内部：`.toolbar-right`:2、`.-graph-hint--overlay`:3、`.toolbar-left`/`.toolbar-actions`:4、`.-window-controls`:5、`.toolbar-search-wrap`:6 | memoria.css:242、113、129；app.css:742、2210、2396 |
| 10 / 20 | `#sidebar-resizer` / `.-link-target-suggest` | memoria.css:291；app.css:3258 |
| 50 / 60 / 61 | `#toolbar` / `.-tb-file-menu` / `.-tb-file-submenu` | memoria.css:104；app.css:4802、4862 |
| **1000** | **`.-modal`（全部弹窗）** | app.css:4590 |
| 9000 / 10000 / 10050 | `.-toolbar-search-panel` / `.-win-resize-layer` / `.-context-menu`、`.-fmt-dropdown-menu` | app.css:2505、2301、2980、3593 |
| 12000 / 20000 / 99999 | `#-flash-host` / `.-color-picker-mask` / `.-lightbox-overlay` | app.css:2576、3688、4474 |

> **2026-09-18**：原 `z-index:90` 的两个浮动按钮（`.-sidebar-collapse-btn` / `.-agent-dock-collapse-btn`）已删除，故「90」这一档在顶栏/侧栏区域**不再存在**；顶栏内部层级（2–6）与 `#toolbar`(50) 不变。

**同时只允许一个弹窗的约束**：**没有**"关掉其它弹窗"的中央实现，各弹窗各自管理自己的 `hidden`（app.js:3062、4539、5451；kb-check.js:629）；唯一存在的"全局互斥"是 F2 的前置检查——只要存在任一非 `hidden` 的 `.-modal` 就不劫持 F2（file-tree.js:453-457）。

弹窗可拖动：按住 `.-modal-header` 拖动 `.-modal-box`，位移用 `transform: translate()` 累加，排除按钮/输入类元素（app.js:12723-12774）；关闭时由 `MutationObserver` 清零位移（app.js:12775-12787）。

### 2.10 缩放与字号

| 变量 / 设置 | 写入位置 | 作用范围与取值 |
|---|---|---|
| `--preview-font-size` / `--editor-font-size` | `#preview`、`#editor` 的 inline style（display-settings.js:80-85） | 预览正文与 h1–h3 标题（app.css:3888、3920-3922）、源码/分栏区（app.css:3873）；12–28px，默认 14（display-settings.js:12、16-17），两者同值 |
| `--lineno-ch` | `#editor` inline style（app.js:1561-1564） | 源码行号列宽，按总行数位数自适应 |
| `uiScale` | `document.documentElement.style.fontSize = 16×scale px`；等于 1.0 时清空恢复（display-settings.js:87-98） | **全界面**：样式表尺寸/字号绝大多数用 `rem`，故整体等比缩放；改完主动派发一次 `resize` 让监听方重算（display-settings.js:97）；0.8–1.5、步长 0.1（display-settings.js:18-20），默认 1.0 |
| 持久化 | `localStorage["-display-settings"]`（display-settings.js:9、40-46）+ 磁盘 `ui-settings.json` 的 `display` 段（display-settings.js:114-118） | 启动 `hydrateFromDisk` 时"本地优先、磁盘仅作种子"（display-settings.js:66-77、120-138） |
| 快捷键 | `Ctrl+=` / `Ctrl++` 放大、`Ctrl+-` 缩小、`Ctrl+0` 复位（app.js:12365-12379） | 步进 ±0.1 并被夹在区间内（display-settings.js:147-157）；**无按键目标过滤**（输入框内同样生效） |

> 注：`index.html:282-283` 注释称"浮层放 `#app` 外以免受 `#app` 的 zoom 影响"，但当前实现改的是**根元素 `font-size`**（display-settings.js:92-93），`rem` 会级联到 `body` 下所有浮层，故 flash 卡片的间距实际**会**随缩放变化——注释与实现已不一致。**同一原因适用于 `#-agent-dock` 的宽度**：它以 rem 计量（agent-panel.js:217-220、266-287），故 `Ctrl+=` 缩放时 dock 会跟着变宽/变窄（见 §2.4「宽度单位是 rem」）。

## 3. 交互流程

**3.1 启动 → 主界面**：`MemoriaBridge.onReady` 后统一 boot（导入流 → 工具条搜索 → 图片 → 检查 → KB 智能体 → 文件树 → **对话面板** → `initKb()` → `initWindowChrome()`，app.js:12843-12854）；`initWindowChrome` 先取 `get_window_chrome()`，失败则三键保持隐藏（window-chrome.js:304-307），成功则写标题/版本、判定 frameless 并把 `min_width/min_height`（**1000×600**）灌进 JS 侧夹取值（window-chrome.js:310-328）；`initKb()` 有路径时**在底栏 `#status-kb` 显示路径**、清空导航栈与标签页、刷新文件、加载链接目标与图谱、跑一次完整检查并打开首选文件（`navigation-demo.md` → `mdp.md` → 首个文件，app.js:489-493），无路径则显示欢迎页、清空底栏路径、状态栏写 `Memoria`（app.js:494-498）。**2026-09-18**：路径不再出现在顶栏，也不再随开/关库同步拖拽排除带（顶栏 `.toolbar-right` 的宽度已与知识库状态无关）；`initKb`/`openKbAt` 里 `setStatus(...)` 亦**不再传知识库路径**（底栏只保留 `#status-kb` 一处，见 §2.7）。

**3.2 顶栏「文件」菜单**：点 `#btn-file` 翻转 `#file-menu` 的 `hidden`、同步 `aria-expanded`、收起时一并隐藏二级面板（app.js:12253-12259）；点「打开最近」显示二级面板并异步拉列表（绑定 12342-12346，渲染 `renderRecentKbMenu` 12296-12336）；关闭有三条路径——点菜单外部（app.js:12260-12265）、按 Esc（app.js:12266-12268）、点任意菜单项（各项 handler 首句都先 `closeFileMenu()`）。**2026-09-18**：「关闭知识库」→ `closeKb()`（app.js:12351，未开库时该项 `disabled`，可用态由 `showKbIndicator()` 维护）；同日新增的「退出程序」**已经用户否决删除**（节点 + click 绑定 + 注释一并移除，见 §7），顶栏/菜单里不再有第二个退出入口。

**3.3 侧栏页签**：点 `[data-sidebar-tab]`（app.js:12584-12586）→ `setSidebarTab`（app.js:1233-1258）：无对应 `[data-sidebar-view]` 的悬空页签名（如存量的 `"agent"`）先回退 `files`（app.js:1234-1236），再写 localStorage、刷新按钮 `.active`/`aria-selected`、切换 `[data-sidebar-view]` 的 `.hidden`；随后清图谱 hover、启停对应图谱视图、按需重算上下分栏比例。**左栏整体收起/展开**由顶栏右侧的 `#btn-toggle-sidebar` 触发（app.js:12191-12200 → `_applySidebarCollapsed()` 12177-12189），不再有贴侧栏右缘的浮动按钮。

**3.3.1 右侧对话停靠栏**：顶栏 `#btn-agent`（**2026-09-18 起唯一入口**） → `toggleDock()`（agent-panel.js:294-296）→ `setDockCollapsed()`（agent-panel.js:430-447）：切 `.-agent-dock--collapsed` 类、同步 `aria-pressed`（agent-panel.js:253-259）、状态落盘在 `layout.agentDockCollapsed`（`localStorage` 无关）、**展开时**额外 `refreshConfig()` 拉一次端点配置（与旧版「切到对话页签即拉配置」同语义）；**空间不足自动隐藏态（`.-agent-dock--auto-hidden`）下点它不会展开**——只弹 `agent.dockNoSpace` 提示并保持隐藏（不写盘、不挤压文档区，见 §2.4）。拖拽 `#agent-dock-resizer` → 实时改宽（agent-panel.js:405-428，上界受 `available` 约束）、`mouseup` 才落盘；期望/生效宽度与自动隐藏规则见 §2.4。

**3.4 视图 / 编辑模式**：点 `.-view-btn` → `setViewMode(mode)`：先把源码编辑器内容同步回 `state.doc` 并重渲染两窗格，再换 `#editor-split` 类名与按钮 `.active`（app.js:1620-1682）；点 `#edit-mode-toggle` → `toggleEditMode()`（实现 edit-handler.js:70-98，绑定 app.js:12621）：切 `contentEditable`、刷按钮态、按需禁用图片插入（edit-handler.js:70-98）；预览区双击进入块编辑时格式栏与块编辑栏互换（edit-handler.js:1009-1013），退出恢复（edit-handler.js:1545-1550）。

**3.5 缩放**：`Ctrl+=` / `Ctrl+-` / `Ctrl+0` → `adjustUiScale(±0.1)` / `resetUiScale()` → 改根 `font-size` 并派发 `resize`（app.js:12365-12379；display-settings.js:87-98、147-157）。

## 4. i18n key

键定义在 `app/i18n/zh-CN.js` 与 `en.js`（成对），由 `i18n.js` 在启动/切语言时按 `[data-i18n]`（textContent）与 `[data-i18n-attr="attr:key;attr2:key2"]`（属性）刷新（i18n.js:91-115、154-169）。本区域涉及的前缀：

| 前缀 / 键 | 覆盖 | 代表键（zh-CN.js 行号） |
|---|---|---|
| `app.*` | 状态栏、窗口/范围 aria、空态 | `app.status.ready`、`app.status.kbEmpty`、`app.stat.kpLines`、`app.scope.aria`（468-494）。**2026-09-18**：`app.kbPath.title`（原顶栏路径的"可拖拽移动窗口"提示）**已删除**——路径改由 `#status-kb` 以完整路径写 `title`，不再有静态 i18n 文案 |
| `toolbar.*` | 顶栏全部按钮与文件菜单项、相关 title | `toolbar.file`、`open`、`import`、`export`、`kbAgent`、`newWindow`、`openRecent`、`recentEmpty`、`refresh`、`build`、`check`、`settings`、**`closeKb`（523）、`closeKbTitle`（524）**——供「文件 → 关闭知识库」、`back.title`（496）、`forward.title`（497）（整段 495-525）。原 `toolbar.exit`/`exitTitle` 已删除；同日新增的 `toolbar.quit` / `quitTitle` 已随「退出程序」菜单项一并**删除**（见 §7「已决」） |
| `win.*` | 窗口三键与控制区 aria | `win.controlsAria`、`minimize`、`maximize`、`restore`、`close`（421-427） |
| `side.*` | 侧栏页签、分栏、收起、知识点工具栏 | `side.tabs.aria`、`side.tab.files`、`collapseTitle`（564）、`expandTitle`（**2026-09-18 起由顶栏 `#btn-toggle-sidebar` 使用**，见 §2.2）、`split.title`、`side.kp.label|config|new`（560-573） |
| `view.*` / `edit.*` | 视图模式、编辑模式、格式栏、块编辑栏 | `view.toggleAria`、`view.source|preview|split`、`edit.mode.aria|title|browseTitle|btn`、`edit.fmt.aria|boldTitle|…`、`edit.block.aria`（648-679） |
| `search.*` | 搜索范围、占位符、状态与结果文案 | `search.scopeKb`、`scopeFile`、`ph`、`title`、`statusSearching`（527-536） |
| `agent.*` | 右侧「对话」停靠栏（**顶栏按钮 title `agent.btnTitle`** + dock aria/拖拽 title + 出网开关 + 端点设置 8 字段 + 输入占位 + 角色两态 + 来源 + **`@路径` chip 的悬停 title** + 状态与错误） + **状态栏用量格** | `agent.btnTitle`（顶栏 `#btn-agent` 的 title；按钮已是**纯图标 `◨`**，不再有文字键；zh-CN.js:575）、`agent.dockAria`、`agent.dockResizeTitle`、`agent.dockNoSpace`（点顶栏按钮请求展开但空间不足时的 flash 文案）、`agent.net.label`、`agent.settings.apiKeySet`、`agent.status.usage`、`agent.err.no_base_url`、**`agent.mention.openTitle` / `agent.mention.revealTitle`**（**2026-09-18 本轮新增 2 键**：文件 chip 悬停「打开 {path}」/ 目录 chip 悬停「在左侧文件树中定位 {path}」；zh-CN.js:627-630、en.js:628-631）、**`agent.statusBar.*`**（2026-09-18 上一轮新增 9 键：`span`/`spanCache`/`line`/`cache`/`cacheUnknown`/`estimated`/`session`/`sessionCache`/`hint`，供状态栏 `#status-agent` 的文本与多行 `title`；zh-CN.js:642-652）（整段 zh-CN.js:574-…）。**上一轮删除 4 键**：`agent.tab`（原按钮文字）、`agent.dockCollapseTitle`、`agent.dockExpandTitle`、`agent.dockNoSpaceTitle`（原浮动按钮的三态 title） |
| `dlg.*` / `check.*` / `kbAgent.*` / `import.*` | 各弹窗标题与按钮 | `dlg.kpTitle`、`dlg.configTitle`、`check.modalTitle` 等 |

完整清单与未迁移中文行的登记规则见 [../i18n-inventory.md](../i18n-inventory.md)；语言系统维护规范见 [../../conventions/i18n.md](../../conventions/i18n.md)。

## 5. 边界与已知坑

1. **弹窗层级低于多个浮层**：`.-modal` 为 `z-index:1000`（app.css:4590），低于搜索面板 9000、右键菜单 10050、flash 卡片 12000、颜色选择器遮罩 20000、图片灯箱 99999。flash 卡片刻意高于弹窗（弹窗会遮住底栏，反馈只能靠它，见 §2.8），代价是**任何 1000 以上的浮层都能盖住弹窗**。
2. **没有"只能开一个弹窗"的中央约束**：各弹窗独立管理 `hidden`，多个弹窗可同时可见；唯一的"统一判定"是 F2 的全局检查（file-tree.js:453-457）。
3. **禁用态并不统一**：后退/前进用 `disabled`；构建仅在执行中 `disabled`；检查/刷新/设置/对话 无禁用，改为点击后提示前置条件（`openKbFirst` / `openFileFirst`）。**这类提示分两档**：`setStatusError` = 底栏整行转红（`.-status-error`，app.css:2112-2118）+ 底部浮层卡片；`setStatus` = 底栏普通色。当前「硬前置」类（构建/检查/插入图片/搜索/创建智能体）都走**前者**；**导入**是唯一只弹悬浮卡片、**不**写底栏的入口（直调 `showFlashError`，见 08 篇 §2.1）。集成方判断"能否操作"需按 §2.2 表逐项判，不能只看是否灰化。
4. **侧栏宽度是两套口径**：CSS 默认 17.5rem / 最小 11.25rem（app.css:124-125），JS 拖拽夹在 180–480px（app.js:12104）；非 100% 缩放时 rem 与 px 不一致，会出现"能拖到比 CSS 最小值更窄/更宽"的观感。
5. **`Ctrl+= / Ctrl+- / Ctrl+0` 无目标过滤**：在搜索框、弹窗输入框内按同样触发整界面缩放（app.js:12365-12379 未检查 `e.target`）。
6. **顶栏拖拽靠"选择器黑名单"**：`NO_DRAG_SELECTORS`（window-chrome.js:120-129）= `#btn-toggle-sidebar, #btn-agent, .toolbar-search-wrap, .toolbar-actions, .-window-controls`。**2026-09-18 本轮**两个图标按钮 `#btn-toggle-sidebar` 与 `#btn-agent` **已同处 `.toolbar-right`**——该容器整体挂 `pywebview-drag-region` 且不在名单内，漏登记会被拖拽的 mousedown 吞掉点击（历史上左栏按钮曾在 `.toolbar-left`，同样不在名单内，故一直必须显式登记）。harness（frameless 变体，见 §7）已实测：点这两个按钮**不**触发 `window_begin_drag`，点品牌区**会**触发。新增顶栏控件时**必须**同步这份名单。
7. **块编辑栏与格式栏互斥**：二者共用 `#editor-header` 同一位置；若在块编辑中切换视图，恢复依赖 `_restoreToolbar()`（edit-handler.js:1545-1550），未被调用则格式栏会一直隐藏。
8. **`#preview-status` 的 `.warn` 态样式存在但需渲染层主动加类**（app.css:4545）；未打开文件时该节点保持 `hidden`（index.html:212）。
9. **`theme/memoria.css` 含大量与当前 DOM 不符的历史选择器**：`#sidebar`、`.toolbar-center`、`#group-tabs`、`.mode-switch`、`.file-grid`、`.file-card` 在 `index.html` 与 `js/**` 中均无对应节点（已检索确认）。不要把它里面的 `#sidebar { width: 23.75rem }`（memoria.css:280-281）当成左侧栏实际宽度——实际是 `#-sidebar { 17.5rem }`（app.css:123-135）。**2026-09-18**：原 `.kb-indicator-wrap` / `.kb-indicator` / `.-kb-exit` 三条规则已随顶栏路径块一并删除（不再是"历史选择器"）。
10. **`uiScale` 的注释已过时**：见 §2.10 末尾（index.html:282-283 vs display-settings.js:92-93）。
11. **右侧 dock 是"左栏/文档区/dock 三栏，dock 让位"**（2026-09-17 第二轮加入**文档区最小宽度保护**后）：`#-sidebar`(17.5rem) 与 `#-agent-dock`(22rem) 都是 `flex-shrink:0`，`#content` 名义上 `flex:1`、实际宽度就是剩余空间。现在 JS 每次布局变化都会算 `available = #main.clientWidth − 左栏 − 360`，把 dock 的**生效宽度**压到 `min(期望, min(34rem, available))`；`available < 16rem` 时整条 dock 临时自动隐藏（`.-agent-dock--auto-hidden`）。故 `#content ≥ 360` 在 `#main.clientWidth ≥ 左栏 + 360` 时成立；**再窄下去**（左栏本身已占满）`#content` 会 < 360，但 dock 不会把 `#main` 撑出溢出——`#main` 的 `overflow:hidden` 不再裁掉 dock。应用最小窗口 **1000×600**（§2.1）下 `available = 1000−280−360 = 360 ≥ 16rem`，**不会**触发自动隐藏。
12. **两种"隐藏"语义不同、类名不同**：手动折叠 `.-agent-dock--collapsed`（**落盘** `layout.agentDockCollapsed=true`，只有用户再点才展开）；空间不足自动隐藏 `.-agent-dock--auto-hidden`（**派生态、永不落盘**，窗口一变宽就自动还原到期望宽度）。两者都只归零宽度、不 `display:none`（仍是布局节点、`clientWidth=0`，消息滚动位置与未发送文本保留、内部仍参与事件与 a11y 树）。自动隐藏时点**顶栏 `#btn-agent`**（2026-09-18 起唯一入口）**不会展开**（会弹 `agent.dockNoSpace` 提示），因为强行展开必然挤压文档区。若集成方需要"完全不存在"，须自行 `hidden`/移除节点。
13. **「停止」现在是真取消（M1 收尾语义变更）**：`services/agent/loop.py` 三个检查点观察 `CancelToken`（`loop.py:295-299`、`248-250`、`380-383`），点「停止」后后端**停止消费模型流并关闭底层响应**（`stream.close()` → provider 的 `with closing(response)`），单飞 `busy` **立即释放**，故停止后**可以立刻再提问**；已生成的部分文本保留在助手气泡并标注「（已停止）」，`loop/end` 以 `stop_reason="aborted"` 落盘。**残留边界**：取消是**协作式**的——若工作线程正阻塞在一次 `read1()` 上，要等该分片到达才会返回；且被取消的一轮**不会**写入 `assistant/message`（会话文件里该轮只有 `user/message` + `loop/end(aborted)`），故刷新后该轮的部分文本不再显示（见 §7 待拍板项）。
14. **端点配置是全局的、不随库走**：`config/agent.json` 在程序目录（与 `ui-settings.json` 同级），一个进程一份；`enabled=false` 时发送按钮禁用（`disabled` + title），**不是**点击后报错。
15. **dock 的滚动边界**：只有 `#agent-messages` 滚动（`overflow-y:auto`、`flex:1`、`min-height:0`），头部、**历史行（M1c 加入）**与输入区是 `flex-shrink:0`，矮窗口下会挤压消息区（实测 876×271 + 设置展开：消息区只剩 20px 高）。展开态 dock 本身**不设** `overflow`（为保证左缘拖拽柄可抓，见 §2.4「拖拽柄」），折叠态才 `overflow:hidden`；设置区自身有 `max-height: min(24rem,45vh)` + `overflow-y:auto` 兜底（app.css:402-403，2026-09-17 修），但**头部、历史行与输入区仍无滚动兜底**——若未来往这几处加内容，需自行保证不撑破。
16. **「会话严格随库」——不存在跨库会话**（2026-09-18）：会话按库分（`<kb>/.memoria/agent/sessions/`），面板的「上次会话」也**按库记**（`config/ui-settings.json` 的 `agent.lastSessionByKb[<库标识>]`，见 §2.4「恢复上次会话」）。**换库必须无条件作废当前会话态**（判据是「当前气泡属于哪个库」`renderedKb`，**不是** `sessionKb`——后者只在会话真正建立时才有值，用它判会让"失败轮只留气泡"的旧气泡残留）；在飞作业若属于旧库则一并 `agent_ask_cancel`。⚠️ **键是知识库的绝对路径**（归一化后）：**换盘符 / 移动 / 重命名知识库会让该条目失效**（不报错，只是不再自动恢复）；此外**同一库只记 1 个**「上次会话」（不是"最近 N 个"）。两点是否需改进见 §7 待拍板项。
17. **用户消息里的 `@路径` 引用有三条语法约束**（2026-09-18 新增；同日对齐上游 `context/file-reference` 的 `activeAtToken` / `formatFileMention` 后重写）：`MENTION_RE = /(^|\s)(@"([^"]*)"?|@(\S+))/g`（agent-panel.js:125，`formatMention` 569-572）。① **`@` 必须是一个 token 的开头**（行首或前导空白）——故邮箱 `a@b.com`、行内 `x@y` 里的 `@` **不会**被识别为引用（旧实现 `/@([^\s@]+)/g` 会误判邮箱，本轮修掉）；② **含空格的路径必须写成 `@"..."`**（如 `@"docs/IELTS vocab.md"`），否则只识别到第一个空白前为止；③ **收尾引号可缺**（`@"dir/` 与 `@"dir/"` 等价）——`insertMention`/`formatMention` 对目录生成**闭合**引号（`@"dir with space/"`），上游对目录留开引号（`@"dir/sub`）属编辑器逐级下钻的交互，本地不需要。⚠️ 与答案锚点**不再同口径**：`ANCHOR_RE`（agent-panel.js:117）仍是"路径不含空白/引号/括号/冒号"的独立硬口径，本轮**未改**——把含空格的文件名当作**答案**里的 `文件:行号` 引用写出来仍然识别不了（两套正则各管一边：用户侧放宽、答案侧不变）。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 顶层骨架 / 区域顺序 | index.html:47-280；theme/memoria.css:81-85、277、417-421、468-473 |
| `#toolbar` 尺寸与层级 / 顶栏元素顺序 / 弹性纪律 | theme/memoria.css:88-161（`#toolbar` 88-105、`.toolbar-left` 109-118、`.toolbar-actions` 119-131、按钮 132-161）；index.html:48-106 |
| 拖拽区标记 / 排除选择器 | index.html:49、85、96、97；window-chrome.js:120-129 |
| 原生标题栏拖动 / 下拉还原 / 双击最大化 / 焦点回拉 | window-chrome.js:196-216、349-351、230-291、366-378、218-228 |
| 边缘缩放层 / 三键图形 / 最大最小尺寸 | window-chrome.js:43-118；app.css:2298-2377、2203-2296；window-chrome.js:16、315-316 |
| 窗口信息接口 / 最小尺寸常量 / DWM 圆角 | src/memoria/app/shell/host.py:7-15；src/memoria/presentation/api/ui.py:662-684；src/memoria/app/window_win32.py:166-180 |
| 关闭入口（`requestClose`；现仅窗口关闭键使用） | window-chrome.js:293-298、393-395、400-404（原「文件 → 退出程序」菜单项及其 app.js:12353-12356 绑定**已删除**） |
| 文件菜单开合 / 最近列表渲染 / 关闭知识库 | app.js:12248-12273、12296-12346、12351 |
| 后退前进动作与按钮态 / Alt+←→ | app.js:417-423、6254-6266、12565-12573 |
| 刷新 / 构建 | app.js:12355-12360、1033-1076 |
| **顶栏左栏伸缩开关** `#btn-toggle-sidebar`（`.toolbar-right` 首位） | index.html:98；memoria.css:132-161（图标共用规则 145-151）；app.js:12162-12200（`_syncSidebarToggleBtn` 12168-12175、`_applySidebarCollapsed` 12177-12189、`setupSidebarCollapse` 12191-12200、装配 12582） |
| **顶栏对话开关** `#btn-agent`（`.toolbar-right` 次位） | index.html:99；agent-panel.js:1587-1588、253-259、294-296 |
| 侧栏页签 / 悬空页签回退 / 计数 / 宽度拖拽 / 上下分栏 | app.js:1233-1258（回退守卫 1234-1236）、739-741、12103-12106、12119-12127；graph-settings.js:43-47、343、361、915-965、967 |
| **右侧「对话」停靠栏**（骨架 / 样式 / 模块 / 装配 / 持久化 / 最小宽度保护 / 历史会话 / 删除 / 恢复上次会话 / **按库会话偏好** / **换库无条件重置** / 停止与取消 / 等待计时 / 状态栏用量格 / **`@路径` 引用与拖拽插入**） | index.html:222-270（历史行 256-260，删除按钮 259）；app.css:304-648（折叠 320-328；自动隐藏 334-342；拖拽柄 345-357；历史行 441-478；消息区 480-545；**`.-agent-mention` 546-574**；拖拽落点 629-638）；js/agent-panel.js:1-1636（dock 常量与几何 209-460；**按库会话偏好 326-403**：`kbKey` 326-329 / `readAgentPrefs` 332-340 / `lastSessionIdFor` 343-349 / `writeAgentPrefs` 361-366 / `setLastSessionId` 372-385 / `clearLastSessionId` 388-403；渲染 462-…（**`@路径` 引用 119-129、493-599**）；**状态栏用量格** 754-830 / 1364 / 1522-1528 / 1448 / 1608；会话历史/删除 893-1117；`loadSession` 976-1015；**`restoreLastSession` 1028-1045**；**`onKbChanged` 1055-1080**；提问与取消 1272-1460；装配 1479-1619）；app.js:12849（另见 454/564/602 三处 `onKbChanged` 钩子） |
| **文件树拖拽 → 对话栏插入 `@相对路径`**（发送端 / 接收端 / 样式 / 后端提示） | file-tree.js:41、168、185、229-248、502-526；agent-panel.js:119-129、493-599、1530-1568；app.css:546-574、629-638；i18n/zh-CN.js:627-630、i18n/en.js:628-631；services/agent/prompt.py:194-218（门控 262-263） |
| 侧栏与树样式 | app.css:123-323；app.css:3409-3457 |
| 图谱分组条显隐 | app.js:763-772 |
| 视图模式切换 / 编辑模式开关 | app.js:1620-1682；app.css:3520-3541、3862-3868；edit-handler.js:59-122 |
| 格式栏与块编辑栏互斥 | index.html:162-199；edit-handler.js:1009-1013、1545-1550 |
| 欢迎页与文档区切换 / 关库复位 | app.js:391-394、589-643 |
| 状态栏统计拼装 / 点击跳转 / 样式 | app.js:290-342、12382-12390；app.css:2063-2086、2092-2102 |
| **状态栏知识库路径格** `#status-kb`（底栏**最左**；2026-09-18 新增，同日左移并去重） | index.html:275；app.css:2137-2145；app.js:379-389（写入点 477/496/568/621；`setStatus` 不再传路径：484/576） |
| **状态栏 Agent 用量格** `#status-agent` | index.html:278；app.css:2123-2128；agent-panel.js:202-203（状态）、754-830（渲染/累加/复位）、1364（轮询结束时写入）、1448（清空对话复位）、1522-1528（点击展开面板）、1608（语言切换重绘）；i18n/zh-CN.js:642-652（`agent.statusBar.*` 9 键，en.js 同段） |
| flash 卡片实现 | app.js:344-377；app.css:2571-2629 |
| 弹窗通用结构 / 拖动 / 动态弹窗 | app.css:4587-4639；app.js:12723-12788、706-728；file-tree.js:263-300 |
| 显示设置（字号 / 缩放）/ 缩放快捷键 | display-settings.js:11-20、79-98、140-157；app.js:12365-12379 |
| i18n 静态节点刷新 / boot 顺序 | i18n.js:91-115、154-169；app.js:12843-12854（`MemoriaFileTree.init` 12848、`MemoriaAgentPanel.init` 12849、`initWindowChrome` 12854） |

## 7. 未证实 / 待确认

- ⚠️ **本轮（2026-09-19：助手气泡锚点匹配修复）已断言 / 未取证**。已断言（harness 端口 8648 + 合成会话 `session-anchor-demo`，其助手回复是一段 **A1–A24 共 24 种锚点写法**的测试文本；两次浏览器实测同一 fixture，**修前/修后对照**）：

  | | 修前（旧 `ANCHOR_RE`） | 修后 |
  |---|---|---|
  | 锚点总数 | 25 | **26**（全角冒号的 `supervised.md：3` 由"不匹配"变为"匹配"） |
  | `data-agent-file` 含中文标点的 | **8 条**（`裸路径：neural-network.md`、`区间：…`、`、supervised.md`、`，supervised.md`、`「neural-network.md`、`【neural-network.md`、`（neural-network.md`、`上级路径：…`） | **0 条**（逐条核对全部为干净路径） |
  | 区间 `neural-network.md:7-9` | 渲染成 `neural-network.md:7`（`-9` 丢失，与原文不符） | 渲染 **`neural-network.md:7-9`**，`data-agent-line="7-9"` |
  | 点击传参 | 8 次传入的是**带中文前缀的错路径** | 全部为正确路径；区间锚点传 `lineHint=7`（`parseInt("7-9")`） |

  - **未取证 / 已知遗留**：① **含空格且未加引号的路径**仍会被腰斩（用例 `docs/IELTS vocab.md:12` ⇒ 只剩 `vocab.md`；加了反引号/引号则正常）；② 非 `.md`（如 `.memoria.yaml:3`）不匹配（按设计）；③ 路径中段含全角括号（`docs/ref/（旧）x.md:7`）会退化为 basename；④ **区间只跳起始行**（`openFile` 只接 `lineHint`，`app.js` 未接"到行"—— 改 `app.js` 会推动其行号锚点，故本轮不动）；⑤ `.md:L7` 这类写法不匹配。①②③⑤ 属"候选收敛"问题，正解是用**当前库的文件清单**去收敛候选路径（登记为 `todo.md §13` **AG07**）。仍属"未取证"的还有：真机 WebView2 下同一 fixture 的观感与点击跳转（harness 里跳转是桩函数）。
- ⚠️ **同轮（2026-09-19：对话面板新增「输入框上方的状态 bar」首版）已断言 / 未取证**。已断言（**harness `docs/example/rich-content-test/_harness.py`，端口 8647**，`MEMORIA_HARNESS_KB` 指向临时库、`MEMORIA_CONFIG_DIR` 隔离；浏览器实测）：
  - **位置**：`#agent-statusbar` 在 `.-agent-composer` 内、**紧邻且位于 `#agent-input` 之上**（实测 `barRect.bottom = 617 ≤ inputRect.top = 623`、`barHeight = 15`、`bar.nextElementSibling === input` 为 true）。
  - **首屏**：`dotState = idle`、`factsText = 模型 deepseek-chat · 出网 · （新会话） · 历史（0 轮）`、`factsHTML` 中模型名在 `<b>` 内。
  - **关 / 开出网**：点 `#agent-net-toggle` 关闭 ⇒ 文案变 `… · 出网已关 · …`、`dotState = off`；再点开 ⇒ 回到 `出网` / `idle`。**首轮实测曾返回 `error`** —— 根因是 `toggleNet()` 关闭时会把 `#agent-status` 置红（`setStatusText(..., !cfg.enabled)`），圆点被误判成"故障"；把「出网关」提到「出错」之前后第二次实测通过（这就是本轮那个 `error` 的来龙去脉，属实修掉）。
  - **未取证**：① 真机 pywebview/WebView2 观感（0.6875rem 字号在窄栏的换行、圆点与文字的垂直对齐）；② **生成中 / 真出错时**圆点的实际表现（只静态核对了 `statusBarDotState()` 的分支来源，未跑慢端点）；③ 载入带历史的会话后「会话 …尾8位」「历史（N 轮）」是否如预期刷新（本轮未造该类会话）；④ **bar 的事实项、措辞与点击行为尚未定稿** —— 等用户指引（台账 `todo.md §13` AG05）。
- ⚠️ **上一轮（2026-09-19：助手气泡渲染 Markdown）已断言 / 未取证**。已断言（**仓库自带 harness `docs/example/rich-content-test/_harness.py`，端口 8646**；`MEMORIA_HARNESS_KB` 指向临时库、`MEMORIA_CONFIG_DIR` 隔离；**不需要模型** —— 助手回复直接写进会话文件，再从 `#agent-history` 下拉载入）—— **20 项断言全通过、页面无 JS 异常**：
  - **Markdown 渲染**：`h2`=1（文本 `感知机`）、`strong`=1、`ul`=1 / `ol`=1 / `li`=4、`pre code`=1（内容含 `print("hi")`）、`table`=1 / `th`=2、`blockquote`=1；气泡 `textContent` 里**不再出现** `**` 或 `##`。
  - **锚点保留**：`.-agent-anchor` = **2**，`data-agent-file` 分别是 `neural-network.md:7` 与 `supervised.md:3`（后者是被反引号包裹的写法）⇒ 渲染后仍可点，且 `anchorEl()` 与旧 `linkify()` 是同一份 DOM 形状（样式与点击委托不变）。
  - **注入面（净化是硬前置）**：同一段回复夹带的 4 段载荷 —— `<img onerror>`、`<script>`、`<a href="javascript:…">`、`<span onmouseover>` ⇒ 气泡内 `script` / `img` / `a[href]` / `[onerror],[onmouseover],[onclick]` **全为 0**，`window.__xss1..4` **全为 undefined**（未执行）。
  - **未取证**：① **真机 pywebview/WebView2 观感**（harness 是 Chromium；字体、窄栏换行、表格横向滚动条的实际手感未看）；② **流式期间的观感** —— 现在**只有定稿才渲染**（流式期间是 `textContent` 纯文本，为的是不每 250ms 重排一次 Markdown），"打字时看到原文、定稿瞬间跳成排版好的样子"是否可接受**未与用户确认**；③ 亮色主题下的排版观感；④ 超长回答（几十屏）的渲染耗时未计时。
- ⚠️ **上一轮（2026-09-19：顶栏搜索框收窄——`.toolbar-search-wrap` 交还中段空白给拖拽区）已断言 / 未取证**。已断言（**仓库自带 harness `docs/example/rich-content-test/_harness.py`，端口 8642**；浏览器内实测，用「改父容器宽度」模拟窗口宽——故 CSS 里的 `vw` 仍按**真实视口**解析、绝对值不等于真机，但旧/新两栏在**同一视口**下做 A/B，趋势可靠）：
  - **A/B（搜索框宽 / 顶栏可拖拽空白合计；旧 → 新）**：1600 → **542 → 173** / **526 → 896**；1200 → **409 → 173** / **260 → 496**；1000 → **342 → 173** / **126 → 296**；900 → **309 → 173** / **60 → 196**（四档搜索框都稳定在 173px ≈ `min(240px, 26vw)` 的换算值；「可拖拽空白」= 两处 `.-titlebar-drag-spacer`（`flex:1 1 0`）分走的剩余空间）。
  - **不变量未破**：四档 `#toolbar.scrollWidth <= clientWidth` **全为 true**（无横向溢出）。
  - **成因**：`flex-grow` 由 1 改 0 ⇒ 搜索框宽度只由 `width:min(240px,26vw)` 决定、不再吃掉中段空白；`min-width:9.5rem`（内部范围开关 + 输入框 `min-width:4.5rem` + gap/padding 之和的下限）**保持不变** ⇒ 真机窄窗口的收缩行为不变（取 0 会让子块外溢并抬高 `#toolbar.scrollWidth`）。
  - **未取证**：① 真机 1600px 窗口下的**绝对像素**（harness 只改父容器宽，`vw` 仍按 665px 真实视口解析）；② **系统级原生拖拽手势**在各宽度下的实际手感（`window_begin_drag` 在 harness 里是 no-op，沿用旧条目）。
- ⚠️ **更前一轮（2026-09-19：M2 长会话压缩 `compaction`——纯后端）已取证 / 未取证**。已取证（静态 + 单测；**本轮无前端改动，故未跑 harness**）：`py_compile` 全过（新模块 `services/agent/compaction.py` + 4 个改动文件）；`pytest -q` **104 passed**（原 81 + 新增 **23** 例 `tests/test_agent_compaction.py`）——长会话超字符阈值时自动把最旧区间摘成 checkpoint、落一条 `compaction` 事件，续聊请求**不再逐字重发被覆盖的旧料**，**压缩失败照常答题**，短会话一次多余模型调用都不发，且会话 JSONL **仅追加**（既有记录逐条不变、seq 连续）。**与面板/状态栏的两处口径**：① 压缩是**纯追加记录类型、不 bump `SESSION_FORMAT_VERSION`** ⇒ 旧版本读新文件只降级为「没有压缩」（不误读也不崩）；② **摘要调用的 token 用量不进状态栏用量格 `#status-agent`**（本格与 `agent_ask_poll.usage` 只认 `loop/end`；压缩开销记在 `compaction.usage` 里、对面板不可见，见 §2.7 与 [10 篇 §2.15/§2.17](./10-data-layout-and-host-embedding.md)）。**未取证**：① 真实模型端点下的**摘要质量**与**压缩前后 A/B**（含「回答可回溯性」，需真人用真实库对照；用户 `config/agent.json` 是真密钥、**刻意不调用**）；② 前端/浏览器端到端（本轮无前端改动，未跑 harness）；③ 真实鼠标拖拽手势（沿用旧条目）。详见 [../../design/dsh-agent-port.md §6.8](../../design/dsh-agent-port.md)。
- ⚠️ **上一轮（2026-09-18：「`@` 引用语法对齐上游 `context/file-reference`」——前端 `MENTION_RE`/`formatMention` 重写 + 后端系统提示新增「用户引用（`@路径`）」段）已断言 / 未取证**。已断言（用仓库自带 harness `docs/example/rich-content-test/_harness.py`（端口 8642，`MEMORIA_CONFIG_DIR` 指向临时目录隔离；先用 RPC `agent_save_config` 置 `enabled=true, base_url=http://127.0.0.1:9/v1` 使「发送」能走到气泡渲染）在浏览器内实测，**全部通过**）：
  - **① 用户气泡 chip 渲染**：发送一条含多种情形的消息（`@a.md`、`@"docs/IELTS vocab.md"`、`@"dir with space/"`、`a@b.com`、裸 `@`、行首 `@line-start.md`）⇒ 用户气泡渲染出 **4 个 chip**：`data-agent-file = ["a.md","docs/IELTS vocab.md","dir with space","line-start.md"]`、`data-agent-dir = [null,null,"1",null]`；气泡文本里 `a@b.com` 与裸 `@` **保持原样、未被识别**（旧实现 `/@([^\s@]+)/g` 会把邮箱 `a@b.com` 误判成引用 —— 这正是本轮修掉的真缺陷）。
  - **② 插入侧（合成拖拽载荷）**：`docs/IELTS vocab.md`(file) → `@"docs/IELTS vocab.md" `；`dir with space`(dir) → `@"dir with space/" `（**闭合引号**）；`plain.md`(file) → `@plain.md `；`docs/example`(dir) → `@docs/example/ `。
  - **③ 静态面**：`py_compile` 通过、`node --check` 通过、`pytest -q` **81 passed**（新增 1 例：`tests/test_agent_loop.py:489-506::test_system_prompt_gates_file_reference_section_on_read_tool` —— 断言 `read_document` 在场时 prompt 含「用户引用（`@路径`）」段与 `@"..."`，不在场时该段不出现）。
  - **④ 后端段落**：`services/agent/prompt.py` 的 `FILE_REFERENCE_SECTION`（194-218）按上游门控**只在 `read_document` 在场时**追加（262-263），段落顺序变为「基础身份 → 运行环境 → 知识库指令文件 → 可用工具 → **用户引用（`@路径`）** → 回答要求」（模块头 12）；原先临时写在「基础身份」段里的那句 `@` 说明**已删除**。
  - **未取证**：① 真实鼠标拖拽手势（本轮仍为合成 `DragEvent`）；② 后端新段落在**真实模型端点**下的行为（只做静态与单测核对，未调真实模型）；③ 亮色主题下 chip 观感；④ 真机 pywebview 窗口。

- ⚠️ **本轮（2026-09-18：「顶栏两枚伸缩按钮合并到右侧 + 移除『文件 → 退出程序』+ 底栏知识库路径左移去重 + 文件树拖拽插入 `@相对路径` 引用」）已断言 / 未取证**。已断言（用仓库自带 harness `docs/example/rich-content-test/_harness.py`，`http://127.0.0.1:8642/`，`MEMORIA_CONFIG_DIR` 指向临时目录隔离；浏览器内实测，**全部通过**）：
  - **① 顶栏顺序**：`.toolbar-right` 子元素顺序 = `[btn-toggle-sidebar, btn-agent, window-controls]`；`.toolbar-left` **无任何 button**（只剩 `logo-icon` + `.logo` + `#app-badge`）。
  - **② 底栏顺序与去重**：`#status-bar` 子元素顺序 = `[status-kb, status-info, status-stats, status-agent]`；`#status-kb` 文本 = 知识库**绝对路径**；`#status-stats` 文本 = `检查 · 8 警告 · 0 KP · 66 行`（**不含**路径）⇒ 重复显示已消除。
  - **③ 文件菜单**：`#file-menu-quit` **不存在**、`#file-menu-close-kb` **存在**。
  - **④ 拖拽插入（落点 = 整个对话栏）**：从文件树条目（实测路径 `aaa/哈哈哈.md`）派发 `dragstart` ⇒ `dataTransfer.types = ["application/x-memoria-path","text/plain"]`。**把 `dragover`/`drop` 派发到 `#agent-messages`（消息区，不是输入框）** ⇒ `#-agent-dock` 拿到 `.-agent-dock--drop`、旧类 `.-agent-composer--drop` 已不存在、`drop` 后输入框 = `"PRE @aaa/哈哈哈.md "`（光标 16）；派发到 dock 内另一个子块（`.-agent-head`）同样成立；普通 `text/plain` 拖放**不**被劫持（`defaultPrevented=false`）且不高亮；`dragleave` 到 dock 之外能清高亮、结束时无残留。
  - **⑤ 中间光标插入**：输入框 `"AA ZZ"`、光标置 2 ⇒ `drop` 后 = `"AA @aaa/哈哈哈.md ZZ"`（不改动光标后的原文、无多余空格）。
  - **⑥ 目录载荷**：合成 `{path:"sub/dir",kind:"dir"}` ⇒ 插入 `@sub/dir/`（带尾斜杠）。
  - **⑦ chip 渲染与点击**：发送后用户气泡渲染 2 个 chip：`data-agent-file = ["aaa/哈哈哈.md","sub/dir"]`、`data-agent-dir = [null,"1"]`、类名分别为 `-agent-mention` / `-agent-mention -agent-mention--dir`；点**文件** chip → 触发 `MemoriaApp.openFile("aaa/哈哈哈.md")`；点**目录** chip → 触发 `MemoriaFileTree.revealDir("sub/dir")`。
  - **未取证**：① **真实鼠标拖拽手势**（本轮只有合成 `DragEvent`，未做原生 drag-and-drop 手势）；② **答案锚点 `ANCHOR_RE` 里的含空白 `文件:行号`**——`ANCHOR_RE`（agent-panel.js:117）仍是"路径不含空白/引号/括号/冒号"的硬口径，含空白即不识别、退化为纯文本，本轮**未造该用例**（**注意**：用户消息侧的 `@` 引用已不再受此限制 —— 见上一条本轮条目 ①，含空格路径走 `@"..."` 已实测通过）；③ `<b>` 类 HTML 注入的转义断言（当次脚本在发送前覆盖了输入框内容，该断言**未被真正压到**）；④ 亮色主题下 chip 的观感；⑤ 后端 `prompt.py` 新指令在**真实模型端点**下的行为（只做静态核对，未调真实模型）；⑥ 真机 pywebview 窗口。

- ⚠️ **本轮（2026-09-18：会话归属修复——「上次会话」按库记 + 换库无条件重置 + 在飞作业随换库取消）已断言 / 未取证**。已断言（**headless Edge（`--headless=new --remote-allow-origins=*`）+ CDP（`websocket-client` 直连，断言全在 Python 侧）+ harness 的 `/rpc` 与静态页 + 本地假 SSE 端点（可在同进程内切快/慢：快 3 帧×0.02s，慢 40 帧×0.3s，并记录每次请求的 `frames_sent`/`aborted`）；`MEMORIA_CONFIG_DIR` 指向临时目录，**两个临时知识库 A/B**；脚本与产物在仓库外临时目录**）——**25/25 PASS**、页面无 JS 异常：
  - **① 换库即复位**：A 内提问成功（会话 `session-…64d64253` 建立、状态栏用量格 `↑5 ↓5`）后切到 B ⇒ **气泡清空、`#agent-history` 选中值 `""`、`#status-agent` 用量格清零**；历史下拉只剩 B 自己的「（新会话）」（B 无会话 ⇒ 禁用）。
  - **② 失败分支回归（原缺陷直接断言）**：A 内制造一次「未配端点」失败轮（只留下用户气泡 + 错误助手气泡、**未建立会话**）⇒ 切到 B 后**旧气泡被清空**（修复前会残留）。
  - **③ 按库恢复 + 无跨库**：B 内提问成功（`session-…5463174c`）后切回 A ⇒ **A 的上次会话被自动恢复**（下拉值 == A 的 id），且 **B 的会话 id 不出现在 A 的下拉列表里**。
  - **④ 在飞作业随换库取消**：A 内以慢端点进入在飞作业（「生成中…」）后切到 B ⇒ 本地立刻不 busy、面板复位；**假端点侧 `frames_sent=2/43 aborted=true`**（确证后端中断、未收完）、被作废结果未写回 B；随后 B 内提问**不受 busy 阻塞**且正常完成。
  - **⑤ 盘上偏好**：临时 `ui-settings.json` 的 `agent.lastSessionByKb` **同时含 A、B 两个键且各自指向正确会话**；`layout` 段（`sidebarWidth:301` / `agentDockWidth:22`）**未被覆盖**；旧全局键 `lastSessionId` 被删除；**旧键一次性迁移**（映射里无本库条目、只有旧键时，能在当前库载入 ⇒ 认领进映射并删旧键）亦通过。
  - **⑥ 刷新**：`Page.reload` 后恢复到**当前库**（B）的上次会话，不是 A 的。
  - **⑦ 关库**：关库后面板空态（气泡清空 + 下拉禁用），且**不动任何库的条目**；重新打开 A ⇒ A 的上次会话仍能恢复。
  - **⑧ 配置隔离证据**：运行前后真实 `config/ui-settings.json`（SHA256 `4253363FF73599C7BC95067CF6C13F3B1D84436D90A70BCE581F757D290E17C4`）与 `config/agent.json`（`C9CFC8B72271A4FA382270F4210BC59063432CA8F417DED86CCB0FB54CD01D50`）**完全一致**；全部写入只发生在临时 `MEMORIA_CONFIG_DIR` 与两个临时知识库。
  - 静态：`node --check` `agent-panel.js` 通过；`i18n_selftest.js` **12/12 PASS**；`scan_ui_strings.py`（files=3 rows=5，**无新增候选**，本轮未新增任何文案键）。
  - **未取证**：① `app.js` 的 `openKbAt`/`closeKb` **未导出到 `MemoriaApp` 门面**，本轮换库/关库是在页面内以「`set_kb_path` RPC + 设 `state.kbPath` + 调 `MemoriaAgentPanel.onKbChanged()`」复现（**与 `openKbAt`/`closeKb` 中真实调用的那两行完全一致**；三处调用点由静态核对：`app.js:454/564/602`），非原生点按文件菜单/目录选择器；② 原生鼠标点击（仍用页面内 `.click()` 与直接调钩子）；③ 真机 pywebview 窗口；④ 真实模型端点。
- ⚠️ **待拍板（2026-09-18 本轮提出）**：① `lastSessionByKb` 的**键用知识库绝对路径**（归一化后）——换盘符 / 移动 / 重命名知识库会让该条目失效（不报错，只是不再自动恢复；不清理则随库数量缓慢增长）。备选：用某类稳定 id（如 manifest 里的库 UUID，当前无此字段）或每库在 `.memoria/` 里存一份。② 每个库**只记 1 个**「上次会话」——是否需要「每库最近 N 个」（面板历史下拉已列最近 30 条，二者语义不同）。

- ⚠️ **本轮（2026-09-18：外壳层重构——顶栏 VSCode 式图标按钮 / 知识库路径下底栏 / 退出入「文件」菜单 / 三键永不被挤出 + 最小尺寸 1000×600）已断言 / 未取证**。已断言（**headless Edge（`--headless=new --remote-allow-origins=*`）+ CDP（`websocket-client` 直连，断言全在 Python 侧）+ harness `/rpc` 两份变体**：① 仓库普通 harness（端口 8643，`UIAPI(host=None)`）；② **frameless 变体 harness**（端口 8644，把 `UIAPI` 的 host 换成"假无边框宿主"⇒ 前端走真机 frameless 分支，`#window-controls` 自然显示并绑定标题栏拖拽处理链）；`MEMORIA_CONFIG_DIR` 与 KB 均指向临时目录；脚本与产物在仓库外临时目录）——**39/39 + 15/15 PASS**：
  - **① 三键永不被挤出**：四个视口（1600×900 / 1200×800 / 1000×700 / 900×600）下 `#btn-win-close` **完整可见且可命中**（`right ≤ innerWidth`，`elementFromPoint` 命中 `#window-controls` 内），`#window-controls` 未裁剪（`scrollWidth == clientWidth == 138`）；右缘恒为视口宽（1600/1200/1000/900 → right 1600/1200/1000/900）。
  - **② `#toolbar` 无横向溢出**：同四档 `scrollWidth == clientWidth`，`flex-wrap:nowrap`。实测几何（w900）：`left 183.78 / actions 280.08 / search 224.44 / right 138`（w1600 为 190.3 / 290 / 561.34 / 138）⇒ 收缩主要由 `.toolbar-search-wrap` 吸收（378→224），左段仅被削 ~17px。
  - **③ 两枚图标按钮 + aria**：`#btn-toggle-sidebar` 在顶栏**最左**（图标 `◧`）、`#btn-agent` 在 `.toolbar-right`（图标 `◨`）——⚠️ 该轮之后**本轮**已把 `#btn-toggle-sidebar` 也移入 `.toolbar-right` 首位，故此处"最左"描述**已被本轮取代**（见 §2.2 与本轮记录 ①）；`aria-pressed` 随状态翻转（true⇄false 双向验证）；点左栏按钮 → `.-sidebar--collapsed` 出现/消失；点右栏按钮 → `#-agent-dock` 加/去 `.-agent-dock--collapsed`（`dockRect` 352→0→352，`aria-pressed` 同步）。
  - **④ 底栏路径格**：`#status-kb` 的 `textContent` 与 `title` 都等于知识库**完整路径**；计算样式 `overflow:hidden`、`text-overflow:ellipsis`、`max-width:40%`；900px 下**真截断**（`scrollWidth 608 > clientWidth 354`）；`#status-bar` 自身无溢出；点「关闭知识库」后文本为空且 `display:none`（不占位）。
  - **⑤ 文件菜单一项**：含「关闭知识库」（该轮曾同时加「退出程序」，**本轮已按用户否决删除**，见本轮记录 ③ 与下方「已决」）；已开库时该项可用（`disabled=false`），关库后 `disabled=true`。
  - **⑥ 旧节点已消失**：`#sidebar-collapse-btn`、`#agent-dock-collapse-btn`、`#kb-indicator`、`#btn-kb-close` 在四档视口下均不存在。
  - **⑦ 自动隐藏回归**：900px + 左栏 480（`available < 16rem`）→ dock 进入 `-agent-dock--auto-hidden`；点顶栏 `#btn-agent` → **仍弹「空间不足：对话栏保持隐藏，请先折叠左栏或把左栏调窄」**（`agent.dockNoSpace` 文案未变）且 `clientWidth` 保持 0、未展开。
  - **⑧ frameless 变体专项 15/15**：`#window-controls` **无需手动去 `hidden`** 即显示；四档三键完整可见 + 顶栏无溢出；**点 `#btn-toggle-sidebar` / `#btn-agent` 都不触发 `window_begin_drag`**（拖拽豁免生效），而**点品牌区（非豁免拖拽区）会触发**（豁免是选择性的）；点 `#btn-win-close` 触发 `window_close`。
  - **配置隔离证据**：运行前后真实 `config/agent.json`（SHA256 `C9CFC8B72271A4FA382270F4210BC59063432CA8F417DED86CCB0FB54CD01D50`）与 `config/ui-settings.json`（`DBAE36E137DF802C08DC071E5C3A61DCB37A2F9AB9854DC498E114E4E2E0A326`）**完全一致**；全部写入只发生在临时 `MEMORIA_CONFIG_DIR`（两份 `ui-settings.json`，307B / 355B）与临时知识库；仓库内 `docs/example/rich-content-test/` 无新增脏文件。
  - **未取证（harness 不可断言，须人工验证）**：① **真机最小尺寸**——`min_size=(1000,600)`（pywebview）与 `setMinimumSize(1000,600)`（Qt）由 OS 窗口管理器执行，CDP 的 `Emulation.setDeviceMetricsOverride` 只改渲染视口、不受应用最小尺寸约束（故 900px 档能跑通，但**不能**据此证明真机缩不到 900）。**人工步骤**：真机启动 → 用鼠标把窗口拖到尽可能小 → 目测宽度卡在 1000px（且三键始终可见、无横向裁剪）；再 `Ctrl+=` 把 `uiScale` 调到 1.5 复核。② **系统级原生拖拽**：真机上 `window_begin_drag` 走 PostMessage + `WM_NCLBUTTONDOWN(HTCAPTION)` 进入原生拖动循环，harness 里该 RPC 是 no-op，**只能**验证"是否调用了该 RPC"。**人工步骤**：真机按住品牌区拖动窗口（应能移动且不选中文字）、按住/点击两个图标按钮（应正常切换且不触发窗口拖动）。③ **pyqt6 的拖拽排除带同步**（`set_toolbar_drag_exclusion`）：本轮把被 `ResizeObserver` 观察的节点从已删除的 `#kb-indicator-wrap` 换成 `.toolbar-right`，真机 pyqt6 未跑。**人工步骤**：`MEMORIA_SHELL=pyqt6` 启动，点「文件/检查/设置/对话」与两个图标按钮，确认点击均生效（未被标题栏拖动吞掉）。④ `uiScale ≠ 1`（0.8–1.5）下顶栏各段收缩的分界点（本轮实测均在根字号 16px）。
- ⚠️ **上一轮（2026-09-18：状态栏 agent 用量格 `#status-agent`）已取证 / 未取证**。已取证（headless Edge + CDP + harness `/rpc` + 本地假 SSE 端点，`MEMORIA_CONFIG_DIR` 与 KB 均指向临时目录；**11/11 PASS**）：⑧ 用量格文本 **`↑8.7k ↓233 · 命中 62%`**；⑨ `title` 含 `缓存：命中 5402 / 未命中 3311 / 命中率 62%` + `本会话累计…`；⑩ 无活动时为空且 `display:none`（不占位）；⑪ 折叠 dock 后点该格使其重新可见（`clientWidth 0 → 351`）；⑫ 会话 `loop/end.usage` 带 `cache_read_tokens`/`cache_miss_tokens`。详见 [10 篇 §7](./10-data-layout-and-host-embedding.md) 与 §2.7。**未取证**：悬停 `title` 在真机不同主题 / `uiScale` 下的换行观感、真实模型端点下的命中率数值。同类「桥在 document-start 就绪时后续模块 init 落空」的装载顺序脆弱点见 10 篇 §7（非本轮引入、未改代码）。
- ✅ **已决（2026-09-18）：移除「文件 → 退出程序」菜单项**。用户质疑其意义（原顶栏「退出」= 关库返回欢迎页，已满足需求；「退出程序」只是按 File 菜单惯例额外加的）⇒ **已删除**：`#file-menu-quit` 节点（原 index.html:76）、`app.js` 的 click 绑定与注释（原 app.js:12353-12356）、i18n 两键（`toolbar.quit` / `toolbar.quitTitle`）全部移除；`#file-menu-close-kb`（关库）**保留**、其上仍有分隔线。窗口关闭键 `#btn-win-close` 仍走 `window_close`；`MemoriaWindowChrome.requestClose()` **保留**并只服务窗口三键（其 JSDoc 仍提旧菜单项，属待清理的注释残留）。harness 实测见本轮记录 ③。
- ✅ **已决（2026-09-18）：知识库路径由 `#status-bar` 最右改到最左，并去掉重复显示**。`#status-kb` 现为 `#status-bar` 的第一个子元素（在 `#status-info` 之前，index.html:275），CSS 由 `margin-left` 改为 `margin-right`（app.css:2137-2145）；`initKb`/`openKbAt` 的 `setStatus(...)` 不再把路径当第二参数（app.js:484 / app.js:576）⇒ 全底栏只此一处显示路径。harness 实测见本轮记录 ②。
- ⚠️ 待确认（未能取证）：`#preview-status` 的填充逻辑与出现时机（app.js:2029-2047 附近有读写点，但完整触发链跨渲染层，未穷尽；留 [04-preview-and-rendering.md](./04-preview-and-rendering.md)）。
- ⚠️ 待确认（设计口径，需用户拍板）：**被「停止」的那一轮，部分文本是否要写进会话文件**。当前实现只落 `user/message` + `loop/end(stop_reason="aborted")`（部分文本只保留在面板内存与该轮 `answer` 里），因此**刷新页面/恢复会话后该轮只剩用户气泡**。若要"停止后刷新仍能看到半截回答"，需在 `loop.py` 的取消分支补发一条 `assistant/message`（会改变"aborted 轮不提交助手消息"的既有语义）。
- ⚠️ 待确认（未能取证）：`.-graph-settings-preview`（设置页内的图谱预览窗，app.css:663-697）的归属与交互，需在 [06-links-and-graph.md](./06-links-and-graph.md) 或 09 篇确认。
- ⚠️ 待确认（未能取证）：`#-flash-host` 的 `aria-live="polite"` 在动态追加节点时是否被屏幕阅读器正确播报（前端无额外处理，未在真实环境验证）。
- ⚠️ 待确认（未能取证）：`body.-win-dragging` 类（app.css:2384-2387）的写入方未在 `window-chrome.js` 中找到（该文件只写 `.-win-resizing`，window-chrome.js:94、109），疑似遗留样式。
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
