# 02 · 文件树与导航

> **用途**：把左侧栏「文件」页签的文件树、右键菜单、F2 重命名、标签页与前进/后退导航栈，写到可据以定位实现的粒度；含空态与已知"回不去"的边界。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[README.md](./README.md)（本套说明书的用法与维护约定）、[01-shell-and-layout.md](./01-shell-and-layout.md)（窗口外壳与布局、左侧栏三页签的定义）、[05-knowledge-points.md](./05-knowledge-points.md)（KP 列表与该篇的空态）、[../architecture.md](../architecture.md)（分层与数据流）、[../i18n-inventory.md](../i18n-inventory.md)（文案清单）。
> **状态**：生效中，2026-09-15。

---

**证据锚约定**：`文件:行号` 以**仓库根目录**为基准。文件树前端实现集中在 `src/memoria/ui/static/app/js/file-tree.js`（渲染 + 右键菜单 + F2 + 重命名链路），通用浮层与标签页/导航栈在 `src/memoria/ui/static/app/js/app.js`、`nav-stack.js`；样式在 `app/css/app.css` 与 `theme/memoria.css`。

## 1. 区域概览

```
#-sidebar                                        index.html:96
└── #sidebar-body-split                          index.html:108
    ├── #sidebar-nav-panel                       index.html:109
    │   └── #sidebar-view-files                  index.html:110   （data-sidebar-view="files"）
    │       └── #file-tree                        index.html:111   ← 本篇主体；可滚动（⚠️ 原写 app.css:308-312 是错的，该处为 #-agent-dock，待重取）
    ├── #sidebar-nav-kp-resizer                   index.html:122
    └── #sidebar-kp-block                        index.html:123   （知识点列表，归 05 篇）

#file-tree 内由 renderFileTree() 一次性 innerHTML 重建（file-tree.js:444-458）：
├── 递归目录节点
│   └── .-tree-dir[data-dir]
│       ├── .-tree-dir-head[data-dir-toggle]   三角图标（展开时 CSS 旋转 90°）+ 目录 open/close 图标 + 目录名
│       └── .-tree-dir-children[.collapsed]    （折叠时 display:none，app.css:3402）
│           └── 同名结构递归
├── .-tree-item[data-path][title=完整路径]      文件类型图标（借 dsh，见 §2.1「图标与侧车」）+ 文件名
└── .-tree-root-zone（固定 64px 留白，供右键"根目录新建"）        file-tree.js:454-456

#content                                          index.html:139
├── #tab-bar > #tabs[.tab / .tab.active / .tab-pending]   index.html:140-142
└── …文档区
```

导航栈（`MemoriaNavStack`）与文件树解耦，是纯内存结构：`{stack[], cursor, filePointer{}}`（nav-stack.js:7-9）。

## 2. 逐处细节

### 2.1 树渲染

| 项 | 证据 | 说明 |
|---|---|---|
| 数据来源 | app.js:630-640 | `call("list_files")` → `state.files`（每项含 `path` / `has_sidecar`）与 `state.dirs`（目录全量清单，含空目录） |
| 建树 | file-tree.js:130-156 | `buildFileTreeRoot(files, extraDirs)`：**先**按 `dirs` 建目录骨架（保证新建的空文件夹可见），**再**把文件挂到对应目录；路径反斜杠统一转 `/` |
| 目录行 | file-tree.js:164-177 | 结构见上图；`twisty` = dsh `IconTriangleRightFill14` 内联 SVG，**展开时由 CSS 旋转 90°**（file-tree.js:169；样式在 app.css 末尾块）；目录图标 = `IconFolderOpen16`/`IconFolderClose16` 随展开态切换（file-tree.js:170）；缩进 `padding-left = 4 + depth×14` px（file-tree.js:166）。**2026-09-19**：缩进区新增逐层连接线（dsh `IconTreeCorner8x10`，`treeGuides(depth)`，file-tree.js:168、700-706；样式 `.-tree-guide-*` 在 app.css 末尾块） |
| 文件行 | file-tree.js:179-189 | 缩进 `padding-left = 12 + depth×14` px；`title` 为完整相对路径；`data-path` 为归一化路径 |
| 图标与侧车 | file-tree.js:180-186；app.css:3421-3428 + **末尾追加块 5522-5583** | **2026-09-19 起不再用 emoji**：文件图标按扩展名/文件名分类（`classifyFileType`，file-tree.js:689-694）取 dsh `FileTypeIcon` 的类目 glyph（markdown/code/image/html/pdf/ppt/video/word/excel/other），类目→图标名映射见 `FT_CATEGORY_ICON`（file-tree.js:683-686）。原「有侧车 `📄` / 无侧车 `📝`」的**双字形差异已取消**——该信息本就由 `.no-sidecar` 类（图标透明度 **0.55**；**2026-09-20 由 0.45 复校** —— dsh 单色 glyph 的 mark 层是细笔画，0.45 叠加后浅色主题下合成对比仅约 2.5:1、偏"几乎看不见"，改 0.55 约 3.3:1，清晰态仍是 0.85 ⇒ 两态一眼可辨；覆盖块 app.css:5601-5613）独立承载，故保留为唯一区分；图标颜色一律 `currentColor`（随所在行的 `--text-secondary`/`--text-bright`，见末尾样式块） |
| 排序 | file-tree.js:123-128、187-198 | 目录与文件**各自**用 `localeCompare(zh-CN, sensitivity:"base", numeric:true)` 升序，目录整体排在文件之前 |
| 当前文件高亮 | file-tree.js:180；app.css:3416-3420、**5069-5076** | `f.path === state.currentPath` 时加 `.active`（字色 `--text-bright`）。**底色口径 2026-09-19 统一**：由 `--bg-active`（浅色主题下偏灰的 `#e2e7f0`）**并入 `--accent-soft`**（主题色淡底，与 `.-kp-item.active`、`.-link-pick-item.is-active` 同一口径），并补一条**不占布局**的左侧标记 `box-shadow: inset 2px 0 0 var(--theme-color)`（原规则在 app.css:3417-3420，覆盖块见 A 档视觉微调 5069-5076；hover 仍是 `--bg-hover`，见 3444）。⚠️ 本行原锚点 `app.css:3008-3011` 是**错的**（那里是 `.-ctx-item.danger:hover` / `.-link-edit-meta`），2026-09-19 一并修正 |
| 展开态 `treeExpanded` | app.js:34；file-tree.js:111-127 | `state.treeExpanded` 是 **`Set<string>`，仅存内存**（初值 `null`，首次使用惰性创建）；`ensureTreeExpandedForPath()` 会把当前文件的所有祖先目录加入集合；每次 `renderFileTree()` 前对 `state.currentPath` 自动展开（file-tree.js:451，**带重渲守卫**）。**2026-09-19 新增**同性质内存集合 `_userCollapsedDirs`（用户显式折叠记忆，file-tree.js:539-557）：重渲时跳过用户折叠过的目录，使含当前文件的文件夹能真正合上；任何**真实 reveal**（`expandToPath` / `revealDir` / 目录内新建）都会清除该记忆（见下行） |
| 折叠/展开 | file-tree.js:208-219 | 点击 `.-tree-dir-head`：命中则 `collapseDir()`（移出展开集 + 记入 `_userCollapsedDirs`），否则 `expandDir()`（清记忆 + 加入展开集），然后整树重渲染（`e.stopPropagation()`），并记录 `_lastSel = {type:"dir", path}`。**记忆清除点**：展开分支、`expandToPath`（file-tree.js:118-127，不带 `respectUserCollapsed` 时）、`revealDir`（:510）、目录内新建文件/文件夹（:423、:439） |
| 尾部留白区 | file-tree.js:424-427 | 高度 64px、`cursor:default`、空 title；保证滚到底仍有空白可右键出「根目录」菜单，也避免末项贴底难命中 |
| 空树占位 | file-tree.js:418-421；i18n/zh-CN.js:1074 | `state.files` 与 `state.dirs` **同时**为空时渲染 `<div class="empty">无 Markdown 文件</div>` |

### 2.2 点击切换文件

| 步骤 | 证据 | 行为 |
|---|---|---|
| 1 | file-tree.js:214-219 | 点击 `.-tree-item` → 记录 `_lastSel = {type:"file", path}` → `navigateToFile(path)`（**不改** `state.currentPath` 由本函数直接完成） |
| 2 | file-tree.js:302-308 | 先 `MemoriaNavStack.openFileFromTree(path)`（专门的入栈入口，见 §2.6）再 `updateNavButtons()` |
| 3 | app.js:1382-1459 | `openFile(path, {fromNav:true})`：提升调度 epoch → 换文件前 `flushDurableBarrier()` 与保存标签滚动位 → 清各类高亮 → `load_document` → 写入 `state.currentPath/state.doc` → `ensureOpenTab` → `showWelcome(false)` → 展开当前目录 + 重渲树（由此刷新 `.active`）→ `renderTabs()` → 重渲编辑器/预览/KP 列表 → `setViewMode` → 恢复滚动位 |
| 4 | app.js:1498-1514 | 成功后写状态栏（`{kp} KP · {lines} 行` 及 sidecar 校验）、刷新图谱审计提示与搜索范围按钮 |

### 2.3 右键菜单

菜单为**通用浮层**，由 `app.js` 的 `showTreeContextMenu(x, y, items)` 构建（app.js:648-703），文件树通过门面调用（file-tree.js:95-96）。

| 上下文 | 触发条件 | 菜单项（顺序） | 证据 |
|---|---|---|---|
| 文件 | `target.closest(".-tree-item")` | `重命名` → `renameTreeFile`；`删除`（`.danger` 红） → `deleteTreeFile` | file-tree.js:225-235 |
| 文件夹 | `target.closest(".-tree-dir-head")` | `重命名` → `renameTreeDir`；**分隔线**；`新建文件` → `createTreeFile(base)`；`新建文件夹` → `createTreeDir(base)` | file-tree.js:236-249 |
| 空白区（`#file-tree` 内非上述两者） | `target.closest("#file-tree")` | `新建文件` → `createTreeFile("")`；`新建文件夹` → `createTreeDir("")`；`图片管理` | file-tree.js:250-258 |

菜单行为与关闭规则：

| 项 | 证据 | 说明 |
|---|---|---|
| 结构 | app.js:655-680 | 每次右键先移除旧菜单（`id="-ft-context-menu"`，`.-context-menu` + `role="menu"`）；项为 `<button class="-ctx-item[.danger]" role="menuitem">`；`items[].divider` 渲染为 `.-ctx-divider` |
| 定位 | app.js:681-689 | `left/top = clientX/clientY`，然后按 `getBoundingClientRect()` 夹到视口内（右/下越界则回退到 `innerWidth - width - 4` / `innerHeight - height - 4`），再保底 `≥4px` |
| 样式 / 层级 | app.css:2949-2967 | `position:fixed`、`z-index:10050`、宽 12.5–20rem、`.danger` 红字 + hover 红底（原写 `app.css:2541-2600` 是**错的**，那里是 KP 创建字段与 `#-flash-host`） |
| 关闭 | app.js:691-702 | 一次性（`_ftMenuBound` 去重）绑定三个全局监听：任意 `click`、**外部** `contextmenu`（不在菜单内）、`Escape`。菜单项自身 `click` 先 `stopPropagation()` 再关闭并执行 action（app.js:673-677） |
| 右键不改变当前文件 | file-tree.js:225-249 | 只更新 `_lastSel`，不调用 `navigateToFile` |

### 2.4 F2 快捷键

| 项 | 证据 | 说明 |
|---|---|---|
| 注册点与去重 | file-tree.js:441-445 | `init()` 中 `document.addEventListener("keydown", handler, true)`——**捕获阶段**，注释说明预览/编辑器内部可能 `stopPropagation`，冒泡阶段收不到 |
| 只认 F2 | file-tree.js:448 | 其它键直接返回 |
| **不**劫持：纯文本控件 | file-tree.js:449-452 | `e.target` 的 `tagName` 为 `INPUT` / `TEXTAREA` / `SELECT` 时返回 |
| **不**劫持：有可见弹窗 | file-tree.js:453-457 | 遍历所有 `.-modal`，**只要有任一不带 `hidden`** 就返回（index.html 常驻多个 `.hidden` 的弹窗，不可见的不算） |
| **不**劫持：无选中项 | file-tree.js:458 | `_lastSel` 为 `null` 时返回 |
| 触发 | file-tree.js:459-462 | `preventDefault` + `stopPropagation` 后，按 `_lastSel.type` 分派到 `renameTreeDir` / `renameTreeFile` |
| 选中项来源 | file-tree.js:207、216、229、241 | 左键点目录头、左键点文件、右键点文件、右键点目录头都会写 `_lastSel`；**不会被清除**（无"失焦/点击空白即清空"的逻辑） |

### 2.5 标签页 `openTabs`

| 项 | 证据 | 说明 |
|---|---|---|
| 数据结构 | app.js:1242-1265 | `{ path, kpId, label, pending, sourceScroll, previewScroll, kpListScroll }`；同一 `path` 复用条目，已存在时只更新 `kpId`/`label`/`pending` |
| 渲染 | app.js:1345-1378 | `<div class="tab[ active| tab-pending]" data-tab-index title=path><span class="tab-label">…</span><span class="close-btn" data-tab-close="i">×</span></div>` |
| 样式 | theme/memoria.css:423-465 | 标签条可横向滚动（`#tab-bar` 的 `overflow-x:auto` 在 428 行）；`.tab.active` 底色 `--bg-primary` + 顶部主题色边框（445-449）；`.tab-pending` 斜体 + 顶部虚线边框（450-458）；标签名最大 8.75rem 省略（459-463）；关闭键 hover 变红（465）。**指针在标签条区域内的滚轮 = 横向滚动**（`app.js:12898-12922`，2026-09-19 新增；滚动条外观见 app.css 末尾块 5046-5104） |
| 打开 | app.js:1424-1435 | `openFile` 默认 `ensureOpenTab(..., {activate:true, pending:false})`；`skipTabUpsert` 时只就地清 `pending` |
| 点击切换 | app.js:1365-1371 → 1326-1343 | 命中 `.close-btn` 则忽略；否则 `activateTab(path, kpId)`：先存当前标签三处滚动位，再 `ensureOpenTab(activate)`，再 `openFile(..., {fromNav: !!skipNav, skipTabUpsert:true, restoreScroll:true})` |
| 关闭 | app.js:1372-1377 → 1291-1324 | 点 `×` → `closeTabAt(i)`。**关掉后仍有标签**：若关的是当前标签 → 激活 `openTabs[min(i, len-1)]`（即顶上的那个标签，或最后一个），且以 `skipNav:true` 激活（**不**产生导航历史）；否则只重绘标签条。**关掉最后一个标签**：清高亮/`currentPath`/`doc`/`activeKpId`，清空编辑器与预览与 `#file-meta`，`renderKpList(null)`（KP 面板显示"请选择文件"），同步搜索范围按钮，显示欢迎页 |
| 滚动位记忆 | app.js:1267-1289 | 每标签分别记忆源码窗格 / 预览窗格 / KP 列表的 `scrollTop`；切回时恢复（有 KP 跳转目标时不恢复 KP 列表） |

### 2.6 前进 / 后退 `nav-stack`

`nav-stack.js` 是一个极简 timeline：`stack[]` + `cursor` + `filePointer{file → cursor}`（nav-stack.js:7-9）。

| 操作 | 语义 | 证据 |
|---|---|---|
| `push(frame)` | 先丢弃 cursor 之后的"重做尾"（`stack.slice(0, cursor+1)`），再入栈并把 cursor 移到新顶；同时更新 `filePointer[file] = cursor` | nav-stack.js:23-36 |
| `openFileFromTree(file)` | **树专用入口**：若 `filePointer[file]` 命中且 `stack[ptr].file === file`，则 `cursor = ptr` 并把 `stack` 截断到该点（**回卷 + 丢尾**），返回该条目；否则等价于 `push({file, kpId:null, source:"tree"})` | nav-stack.js:38-46 |
| `navBack()` / `navForward()` | 仅移动 cursor 并返回新条目；越界返回 `null` | nav-stack.js:48-58 |
| `canBack()` | `cursor > 0` | nav-stack.js:60-62 |
| `canForward()` | `cursor >= 0 && cursor < stack.length - 1` | nav-stack.js:64-66 |
| `clear()` | 清空 stack / cursor / filePointer | nav-stack.js:11-17 |
| 按钮态 | `#btn-nav-back` / `#btn-nav-forward` 的 `disabled` 由 `updateNavButtons()` 按上述两函数刷新；HTML 初值 disabled | app.js:406-412；index.html:44-45 |
| 按钮/快捷键动作 | `navBack()` / `navForward()` 取 frame 后以 `openFile(frame.file, {fromNav:true, kpId:frame.kpId})` 打开（失败时 cursor 已移动，无回滚） | app.js:6201-6213 |
| 清空时机 | 打开知识库（`initKb`）与关闭知识库（`closeKb`）各清一次 | app.js:465、604；app.js:555 |

**入栈 / 不入栈总表**（按"最终是否产生新历史条目"判定）：

| 触发 | 是否入栈 | 证据 |
|---|---|---|
| 树内点击文件 | 入栈（但走 `openFileFromTree`，可能**回卷丢尾**） | file-tree.js:303-307 |
| 点击标签页 | 入栈（`activateTab` 未传 `skipNav`） | app.js:1326-1343、1365-1371 |
| 关闭标签后的自动激活 | **不入栈**（`skipNav:true` → `fromNav:true`） | app.js:1320 |
| 链接跳转 `jumpToTarget` | 自行 `push({source:"link"})` 后以 `fromNav:true` 打开 | app.js:4778-4790 |
| KP 列表点击 `onKpClick` | 自行 `push({source:"kp"})` | app.js:10923-10933 |
| 搜索命中跳转 | 入栈（`openFile` 未传 skipNav/fromNav） | toolbar-search.js:225、232 |
| 后退 / 前进按钮、Alt+←/→ | **不入栈**（`fromNav:true`） | app.js:6205、6212、12402-12409 |
| 刷新按钮 | **不入栈**（`skipNav:true`） | app.js:12196 |
| 构建后重载当前文件 | **不入栈**（`skipNav:true`） | app.js:1030 |
| 启动自动打开首选文件 | **不入栈**（`skipNav:true`） | app.js:480 |
| 重命名后重开（文件 / 目录） | **不入栈**（`fromNav:true`） | file-tree.js:329、358 |
| 新建文件后打开 | **不入栈**（`fromNav:true`） | file-tree.js:396 |
| 打开另一个知识库 / 关库 | 整体 `clear()`，历史归零 | app.js:465、604 |

### 2.7 右键 / 弹窗链路（新建、重命名、删除）

| 动作 | 调用 | 成功反馈 | 证据 |
|---|---|---|---|
| 输入弹窗 | 复用 `.-modal` 动态创建（宽 `min(360px,92vw)`），Enter=确定、Esc=取消、点遮罩=取消、30ms 后自动聚焦；空白输入按 `null` 处理（不执行） | — | file-tree.js:263-300 |
| 新建文件 | `file_create(rel)`，`rel = baseDir ? baseDir/输入 : 输入` | `已创建` + 路径；若指定目录则先展开该目录；随后刷新树并打开新文件 | file-tree.js:384-398 |
| 新建文件夹 | `dir_create(rel)` | `已创建文件夹`；先展开父目录；随后刷新树（**不**自动打开） | file-tree.js:400-413 |
| 重命名文件 | `file_rename(relPath, 新名)`；新名与旧名相同则直接返回 | `已重命名`；若后端 `synced` 再补一条 `已重命名并同步 {n} 处链接引用（{m} 个文件正文、{s} 个侧车）`；随后 `applyRenameUi` → 刷新树 → 重开重映射后的当前文件 | file-tree.js:310-332 |
| 重命名文件夹 | `dir_rename(relPath, 新名)`；后端可能返回 `partial`（部分文档级联失败）——代码**同样当失败**处理并提示，不误判为成功（注释明示） | `已重命名文件夹` + `并已同步 {files} 个文档、{sidecars} 个侧车、{pending} 条待确认` | file-tree.js:334-361 |
| 删除文件 | 先弹确认框（danger 按钮），确认后 `file_delete(relPath)` | `已删除`；若该文件在标签页中打开则 `closeTabAt` 对应下标；随后刷新树 | file-tree.js:363-382；app.js:706-728 |

**`applyRenameUi(oldPath, newPath)` 做了什么**（file-tree.js:51-73）：

1. `MemoriaScheduler.bumpEpoch()` —— 结构变更使基于旧路径/旧结构的排队作业陈旧可弃；
2. 重映射 `state.currentPath`（`remapPath`：等于旧路径则替换，旧路径前缀则替换前缀，否则返回 `null`）；
3. 逐个重映射 `state.treeExpanded` 集合中命中前缀的键；
4. 逐个重映射 `state.openTabs[].path` 并同步 `.label` 为新的 basename；
5. `renderTabs()`；返回重映射后的当前文件路径给调用方。

## 3. 交互流程

**3.1 单击文件 → 文档打开**
`click .-tree-item`（记录 `_lastSel`）→ `navigateToFile` → `NavStack.openFileFromTree` → `updateNavButtons` → `openFile(fromNav:true)` → 刷盘屏障 → `load_document` → 重渲树（`.active` 跟随）→ 重渲标签页/编辑器/预览/KP 列表 → 状态栏更新。

**3.2 右键 → 菜单 → 动作**
`contextmenu`（树内委托 handler，file-tree.js:222）→ 判定三上下文之一 → `preventDefault` + `stopPropagation` → `showTreeContextMenu(clientX, clientY, items)` → 菜单插入 `body` 并夹到视口内 → 点击某项：`stopPropagation` → 关菜单 → 执行 action（可能再弹输入框/确认框）→ 完成后 `refreshFiles()` 重渲整树。

**3.3 F2 重命名**
左键或右键选中文件/目录（写 `_lastSel`）→ 按 F2 → 捕获阶段判定（非输入控件、无可见弹窗、有 `_lastSel`）→ `preventDefault`/`stopPropagation` → 弹输入框 → 确定 →后端 rename → 状态栏反馈 → `applyRenameUi` → `refreshFiles` → 若当前文件被重映射则重新打开。

**3.4 标签页**
点击标签主体 → `activateTab`（存滚动位 → `ensureOpenTab` → `openFile`，入栈）；点击 `×` → `closeTabAt`（见 §2.5）。切换视图模式、编辑模式不影响标签集合。

**3.5 前进 / 后退**
点按钮或 Alt+←/→ → 判定 `canBack()/canForward()` → 移动 cursor → `updateNavButtons()` → `openFile(fromNav:true)`。返回的是**帧**（文件 + 可选 kpId），因此 KP 跳转也能被"后退"还原到同一文件的前一个 KP。

## 4. i18n key

键定义在 `app/i18n/zh-CN.js` 与 `en.js`。本区域涉及的键族：

| 键族 | 覆盖 | 代表键 |
|---|---|---|
| `tree.*` | 树内全部右键菜单项、输入/确认弹窗标题与按钮、状态提示 | `tree.empty`「无 Markdown 文件」、「tree.newFile / newFolder / rename / delete / createBtn」、`tree.renameTitle`、`tree.renameDirTitle`、`tree.renamePh`、`tree.renameDirPh`、`tree.newFilePh`、`tree.newFolderPh`、`tree.deleteTitle`、`tree.deleteBody`、`tree.renamed`、`tree.renamedSynced`、`tree.dirRenamed`、`tree.dirRenamedSynced`、`tree.deleted`、`tree.created`、`tree.createdFolder`、`tree.renameFail`、`tree.deleteFail`、`tree.createFail`（zh-CN.js:1073-1098） |
| `app.kpList*` | KP 面板三种空态（未选文件 / 无 KP / 仅提议） | `app.kpListSelectFile`、`app.kpListNoKp`、`app.kpListOnlyProposals`、`app.kpListOnlyProposalsHint`（zh-CN.js:491-494） |
| `app.*` | 打开文件前的提示与加载态 | `app.openFileFirst`、`app.openKbFirst`、`app.loading`、`app.loadFailed`、`app.listFailed`（zh-CN.js:479-483） |
| `common.*` | 输入/确认弹窗的取消、确定、关闭 | `common.cancel`、`common.ok`、`common.close` |
| `img.menuLabel` | 空白区右键的「图片管理」入口 | `img.menuLabel`（file-tree.js:256） |
| `toolbar.back.title` / `toolbar.forward.title` | 前进/后退按钮 title（含 Alt+←/→） | zh-CN.js:497-498 |
| `side.tab.files` / `side.tabs.aria` | 页签文案与 aria | zh-CN.js:562-563 |

完整清单见 [../i18n-inventory.md](../i18n-inventory.md)；语言包维护规范见 [../../conventions/i18n.md](../../conventions/i18n.md)。

## 5. 边界与已知坑

1. **展开态不持久化**：`state.treeExpanded` 是内存 `Set`（file-tree.js:105-110），代码中**没有任何 localStorage / 磁盘读写**（全仓检索仅 app.js:34 与 file-tree.js 内部出现）。重开应用或重开知识库后回到"只有当前文件路径上的祖先被展开"。这与"展开态持久化"的直觉不符。
2. **未开库时文件树可能完全空白**：`renderFileTree()` 只在 `refreshFiles` / `openFile` / `closeKb` / `closeTabAt` 之后被调用（app.js:614、639、1306、1438）。冷启动且没有知识库时这些路径都不会走，于是 `#file-tree` 保持空 div，**连「无 Markdown 文件」占位也不会出现**；只有在关库（`closeKb`，app.js:589+614）之后才会看到该占位文案。
3. **树内点击会"丢尾"**：`openFileFromTree`（nav-stack.js:38-46）一旦命中 `filePointer` 就把 stack 截断到该点，等于把之后的所有前进历史删除。这是"部分跳转无法返回"的主要来源：先 A→B→C，再从树上点回 A，则 B、C 的历史被丢弃，无法"前进"回去。
4. **`filePointer` 与 stack 不同步清理**：截断（nav-stack.js:42）与 `navBack/navForward`（48-58）都不会更新/失效 `filePointer`，只靠读取时的 `stack[ptr] && stack[ptr].file === file` 双条件兜底（nav-stack.js:39-41）。行为上安全，但如果后续要在此结构上加载更多语义，需注意该指针可能指向已失效的下标。
5. **重命名不重映射导航栈**：`applyRenameUi` 只处理 `currentPath` / `treeExpanded` / `openTabs`（file-tree.js:51-73），**不触碰** `MemoriaNavStack` 的 stack 与 filePointer。因此重命名前入栈的旧路径条目在后退/前进时会以旧路径调用 `openFile`，`load_document` 失败后仅写状态栏（app.js:1412-1415）而 cursor 已移动，表现为"点后退没反应/停在原地"。
6. **重命名后 `_lastSel` 仍指向旧路径**：`applyRenameUi` 未更新 `_lastSel`（file-tree.js:41、51-73）。若重命名后**不点击**而直接再按 F2，会对旧路径再次发起 rename 请求。
7. **导航失败不回滚 cursor**：`navBack/navForward` 先移动 cursor 再 `openFile`（app.js:6201-6213）；`jumpToTarget`/`onKpClick` 也是先 `push` 再打开（app.js:4778-4790、10923-10933）。打开失败时历史条目仍留在栈上，可能出现"原地反复后退"。
8. **F2 的"选中项"不会因失焦清除**：`_lastSel` 只在点击树节点时写入、从不置空（file-tree.js:41）。因此点过某个文件后，即使视觉上已在别处操作（未开弹窗、未聚焦输入框），F2 仍作用于那个文件。
9. **右键菜单不会切换当前文件**：右键只写 `_lastSel`（file-tree.js:225-249），"删除"的确认文案用的是被右键的文件名（file-tree.js:366）。删除的**不是**当前打开文件时，标签页不会受影响（`closeTabAt` 只在命中时调用，file-tree.js:375-378）。
10. **关闭最后一个标签 = 回欢迎页**：`closeTabAt` 会清空 `currentPath`/`doc` 并 `showWelcome(true)`（app.js:1296-1317），此时右侧内容区被欢迎页占满，但左侧树与 KP 面板仍在（KP 面板显示"请选择文件"，app.js:1307）。
11. **`pending` 标签态**：`.tab-pending` 由 `ensureOpenTab` 的 `pending` 选项驱动（app.js:1252、1257、1260、1263、1329），样式为斜体 + 顶部虚线（memoria.css:450-458，2026-09-19 实测重取；原写 421-429 偏早约 29 行）。本篇未逐处确认所有写入方，见 §7。
12. **空态文案复用**：关库后文件树与 KP 面板的占位分别是 `tree.empty`「无 Markdown 文件」与 `app.kpListSelectFile`「请选择文件」（file-tree.js:419、app.js:2107），二者语义不同，集成方勿混用。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 树容器 DOM | index.html:110-112 |
| 树模块总述与 API | file-tree.js:1-30、718-723 |
| `init()`（F2 注册） | file-tree.js:466-496 |
| 建树（含空目录） | file-tree.js:136-162 |
| 目录行 / 文件行渲染 | file-tree.js:164-189 |
| 排序规则 | file-tree.js:129-134、191-206 |
| 展开集合与祖先展开 | file-tree.js:111-127 |
| **用户折叠记忆 / 重渲守卫**（2026-09-19） | file-tree.js:539-557、451 |
| 交互绑定（点击 / 右键委托） | file-tree.js:208-289 |
| 空树占位 / 尾部留白 | file-tree.js:444-458 |
| 树样式 | app.css:3382-3429；**图标/连接线块末尾追加 5522-5583** |
| 图标清单 / 文件类型分类器 / 单测 | file-tree.js:521-716；scripts/benchmark/maintenance/file_tree_icons_test.js |
| 树滚动容器 | ⚠️ **锚点待重取**（原写 `app.css:304-312`，该处实为 `#-agent-dock`；2026-09-19 核对发现，未在本轮重取） |
| 通用右键浮层 | app.js:648-703 |
| 确认弹窗 | app.js:706-728 |
| 输入弹窗 | file-tree.js:292-329 |
| 点击切换文件 | file-tree.js:331-337；app.js:1382-1459 |
| 重命名链路（文件 / 目录） | file-tree.js:339-390 |
| 删除链路 | file-tree.js:392-411 |
| 新建链路 | file-tree.js:413-442 |
| `applyRenameUi` | file-tree.js:58-79 |
| 路径重映射函数 | file-tree.js:50-55 |
| 标签页数据结构 / 渲染 / 关闭 | app.js:1242-1265、1291-1324、1345-1378 |
| 标签页样式 | theme/memoria.css:423-465；app.css:3358-3369（`#tab-bar` / `#tabs`）；**滚动条外观统一收口在 app.css 末尾块 5046-5104**（2026-09-19 重取；原写 `memoria.css:396-436` 偏早约 20 行、`app.css` 部分此前标「锚点待重取」，本轮一并修正） |
| 标签滚动位记忆 | app.js:1267-1289 |
| 导航栈实现 | nav-stack.js:4-78 |
| 前进/后退动作 | app.js:6201-6213 |
| 按钮态刷新 | app.js:406-412 |
| Alt+←/→ | app.js:12402-12410 |
| 导航栈清空 | app.js:465、555、604 |
| 树内跳转入栈入口 | file-tree.js:332-336；nav-stack.js:38-46 |
| 链接跳转 / KP 跳转入栈 | app.js:4778-4790、10923-10933 |
| 搜索命中跳转 | toolbar-search.js:215-234 |
| KP 面板空态 | app.js:2103-2132 |
| 关库时的树/标签/KP 复位 | app.js:575-628 |
| 欢迎页显示切换 | app.js:380-383 |
| `tree.*` 文案 | i18n/zh-CN.js:1073-1098 |
| `app.kpList*` 文案 | i18n/zh-CN.js:491-494 |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未能取证）：标签页 `pending: true` 的全部写入方与语义（仅在 `ensureOpenTab` 的 `opts.pending` 与 `activateTab` 中读到相关赋值，未见其它业务侧调用 `pending: true` 的入口）。
- ⚠️ 待确认（未能取证）：`state.dirs` 中"空目录"的后端来源与 `list_files` 的完整字段集合（本篇只取证到 `state.files` 用到的 `path` / `has_sidecar` 两个字段，file-tree.js:173-183）。
- ⚠️ 待确认（未能取证）：后端 `file_rename` / `dir_rename` 返回的 `synced` / `md_replacements` / `md_files` / `sidecar_files` / `pending_updated` / `files` 各字段的精确含义与取值边界（前端仅做展示，file-tree.js:319-354）。
- ⚠️ 待确认（未能取证）：`dir_rename` 返回 `partial` 时的状态码全貌（注释说明按非 `ok` 处理，file-tree.js:339-343，但未找到后端返回样例）。
- ⚠️ 待确认（未能取证）：`openFileFromTree` 的"回卷丢尾"是否为设计意图（nav-stack.js:2 注释自称"designV0 §12 简化版"，未在本篇取证到该设计文档）。
- ⚠️ 待确认（未能取证）：树节点是否支持键盘导航（上下移动/回车打开）——检索到的键绑定只有 F2（file-tree.js:448）与 Ctrl+K（toolbar-search.js:282），但未穷尽 `edit-handler.js` 的全局 keydown 分支是否包含焦点在树上时的处理。
