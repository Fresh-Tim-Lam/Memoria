# 03 · 编辑器与格式工具链

> **用途**：把「源码编辑区长什么样、格式工具栏与编辑块工具栏各按钮做什么、撤销/粘贴/选区如何工作」记到可据以工作的粒度，供集成方与后续 Agent 直接对照代码改前端。
> **目标读者**：在 Memoria 之上做集成/移植的 Agent 与人；给 Memoria 前端写改动的人。
> **关联文档**：[README.md](./README.md)（维护约定）、[preview-formats.md](../preview-formats.md)（**渲染语法权威**，本篇不重复语法清单）、[04-preview-and-rendering.md](./04-preview-and-rendering.md)（预览与渲染）、[i18n-inventory.md](../i18n-inventory.md)（文案键）、[glossary.md](../glossary.md)。
> **状态**：生效中，2026-09-15。

---

## 1. 区域概览

```
#editor-wrap                                   （index.html:149）
├─ #editor-header                              （index.html:150；app.css:3093）
│  ├─ #file-meta                               （index.html:151；显示 sidecar.description）
│  ├─ .-format-bar          [role=toolbar]      （index.html:152-184）
│  │  ├─ B / I / -fmt-sep
│  │  ├─ .-fmt-dropdown(H▾)  > .-fmt-dropdown-menu.-hl-colors
│  │  ├─ .-fmt-dropdown(色▾) > .-fmt-dropdown-menu.-fc-colors
│  │  └─ #btn-insert-image（默认 disabled）
│  ├─ #block-edit-bar.hidden [role=toolbar]     （index.html:185-188）
│  │  ├─ #block-edit-label
│  │  └─ #block-edit-tools（内容由 JS 注入）
│  ├─ .-view-toggle  > .-view-btn × 3           （index.html:189-193）
│  └─ #edit-mode-toggle > #btn-edit-mode        （index.html:194-196）
├─ #preview-status.hidden                      （index.html:198；渲染告警条，见 04 篇）
└─ #editor-split.view-source                   （index.html:199；app.css:3441）
   ├─ #editor-pane.-pane > #editor.-editor     （index.html:200-202）→ 源码编辑区
   └─ #preview-pane.-pane > #preview           （index.html:203-205）→ 预览区
```

`. -format-bar` 与 `#block-edit-bar` **互斥显示**：进入块编辑时给格式栏加 `.hidden`、去掉块编辑栏的 `.hidden`；退出时反向（`edit-handler.js:1546`-`1551`）。两者同在 `#editor-header` 这一 flex 行内（`app.css:3093`-`3103`），块编辑栏 `flex:1` 且工具区可横向滚动（`app.css:3757`-`3778`）。

## 2. 逐处细节

### 2.1 源码编辑区的结构

源码区**不是** textarea，而是「每行一个 div + 行号 span + contenteditable 内容 span」：

```html
<div class="-line" data-line="12" id="line-12">
  <span class="-lineno">12</span>
  <span class="-line-content" contenteditable="true" spellcheck="false" tabindex="-1">…</span>
</div>
```

| 元素 | 位置/尺寸 | 样式类 | 交互 | 状态与边界 |
|---|---|---|---|---|
| 行容器 | 全宽，`display:flex`，`min-height:1.25rem` | `.-line` | hover 有底色；KP 范围内加 `.in-range` | `app.css:3598`-`3602`、`app.css:3634` |
| 行号栏 | 固定列宽 `calc((--lineno-ch + 3)*1ch + 1px)`，右对齐，不可选中 | `.-lineno` | 无交互 | 列宽按总行数位数自适应，`--lineno-ch` 由渲染时写入（`app.js:1561`-`1564`、`app.js:6984`-`6988`） |
| 行内容 | `flex:1`，`white-space:pre-wrap`，可选中 | `.-line-content` | 独立 contenteditable（**每行一个可编辑单元**，浏览器无法跨行移动光标，跨行由 JS 接管） | `app.css:3616`-`3632`；跨行方向键/退格/回车见 `app.js:7246`-`7419` |
| 空行占位 | — | — | 无文字时内部补 `<br>` | `app.js:7045`-`7050`；CSS `:empty::after`（`app.css:3632`） |
| 滚动容器 | `overflow:auto` | `.-pane`（`#editor-pane`） | 分栏时滚动与预览联动 | `app.css:3447`-`3452`、`app.js:1519`-`1540` |

**没有独立的行号栏容器**：行号是每行的子元素，随行滚动（不是 sticky 定位的实现，`app.css:3603`-`3615` 中无 `position` 声明）。

### 2.2 编辑模式开关（编辑 / 只读）

| 项 | 说明 | 锚点 |
|---|---|---|
| 默认态 | `EH.editMode = true` | `edit-handler.js:60` |
| 开关节点 | `#edit-mode-toggle`（`role=switch`、`tabindex=0`）内含 `#btn-edit-mode` | `index.html:194`-`196` |
| 点击绑定 | 绑定在**外层 wrapper** 上；`#btn-edit-mode` 自身 `pointer-events:none`（`app.css:2036`） | `app.js:12452`-`12462` |
| 关闭的影响面 | ① `#preview.contentEditable="false"`；② 源码全部 `.-line-content` 变 `contenteditable=false` 并清空残留选区；③ `#btn-insert-image` 立即 `disabled`；④ `_caretInPreview=false` | `edit-handler.js:80`-`97`、`104`-`119` |
| 视觉 | 按钮 `.active` 切换；`#editor` 加/去 `.-readonly` | `edit-handler.js:74`、`110` |
| 键盘 | **无 Enter/Space 处理**：`tabindex=0` 但只有 click 监听 | `app.js:12452`-`12462` |
| 只读下的菜单 | 源码区/预览区右键菜单直接 return（不弹「粘贴/插入图片/创建链接」） | `app.js:9530`、`app.js:9550`、`app.js:9562`-`9563` |

### 2.3 格式工具栏（`.-format-bar`）

**顺序固定**（DOM 即顺序）：`B` → `I` → 分隔 → `H▾` → `色▾` → 分隔 → `图片`（`index.html:153`-`183`）。

| 控件 | 样式类 / 标识 | 左键 | 右键 | 禁用/边界 |
|---|---|---|---|---|
| 加粗 | `.-fmt-btn[data-fmt=bold]` | 有非折叠选区 → `applyFormat("bold")`（**toggle**：已全加粗则移除）；无选区 → 进入画笔（`armBrush`） | 若该槽位已被画笔选中 → 仅取消该槽位 | `app.js:10053`-`10064`；画笔语义 `app.js:10607`-`10642` |
| 斜体 | `.-fmt-btn[data-fmt=italic]` | 同上（`toggle`） | 同上 | `app.js:10053`-`10064` |
| 荧光笔 ▾ | `.-fmt-btn[data-fmt=highlight]` + `.-fmt-dropdown-menu.-hl-colors` | 仅**开合**下拉（不应用样式） | 同 B/I 的槽位取消规则 | 下拉开合 `app.js:10066`-`10077` |
| 荧光笔色块 | `.-hl-swatch[data-hl-color]`（黄/绿/红/蓝/橙）+ `[data-hl-none]` + `[data-hl-custom]` | 有选区 → 直接应用；无选区 → 进画笔。`无色` → `applyFormat("unhighlight")`；`添加颜色` → 打开取色器并**只加到色板** | 自定义色块保留自己的删除菜单 | `app.js:10079`-`10097`、`10119`-`10139` |
| 字体色 ▾ | `.-fmt-btn[data-fmt=fontcolor]` + `.-fc-colors` | 同荧光笔 | 同上 | `app.js:10099`-`10117` |
| 悬停预染 | — | `mouseenter` 只**临时**给选区文字包 span 染色，`mouseleave` 复原（不改源码/AST） | — | `app.js:10091`-`10096`、`9744`-`9844` |
| 图片 | `#btn-insert-image[data-insert-image]` | 打开图片选择/入库流程 | — | **仅当「编辑光标真实位于预览区」时可点**：`EH.editMode && EH._caretInPreview`（`image-tools.js:163`-`176`）；按钮 `mousedown` 被 `preventDefault` 以阻止焦点转移（`image-tools.js:528`-`530`） |

**选区捕获机制**（按钮点击会导致 contenteditable 失焦，故需缓存）：

1. 全局 `mousedown`（捕获阶段）：按在预览区**外** → `capturePreviewSelection()` 缓存实时选区；按在预览区**内** → 作废缓存（`app.js:10036`-`10051`）。
2. 取用时 `getPreviewSelectionRange()`：优先实时选区，其次缓存；两者都必须落在 `#preview` 内且非折叠（`app.js:9721`-`9742`）。
3. 工具栏 active 指示由 `selectionchange`（`requestAnimationFrame` 合并节流）刷新（`app.js:9969`-`9976`、`9932`-`9965`）。
4. `contentEditable=false` 的原子块（行内公式 `.-math`）浏览器不画选区高亮，另由 `._sel-covered` 补（`app.js:9978`-`10022`；样式 `app.css:3835`-`3839`）。

**应用样式后选区是否保持**：保持。单块走 `commitSelection` → `restoreSelection`（非折叠）；跨块走 `_commitMultiStyle` → `restoreSelectionMulti`（`app.js:8129`-`8138`、`9356`、`7751`、`7788`）。画笔连续涂抹时每次应用后**重取实时选区**继续（`app.js:10672`-`10674`）。

**源码区选区**：仅在「无预览区选区」时才作为兜底，且**只支持单行**，跨行会给状态栏 `cfg.style.singleLineOnly` 并放弃（`app.js:10785`-`10820`、`10850`-`10854`）。`无色` 两种格式只支持预览区 AST 管线，源码区不生效（`app.js:10844`-`10848`）。

### 2.4 编辑块工具栏（`_BLOCK_TOOLS`）

双击（或单击图片块）不可编辑块进入块编辑模式后，`#block-edit-tools` 由 `_BLOCK_TOOLS[blockType].tools()` 生成（`edit-handler.js:906`-`977`）。块类型 → 标签/工具：

| 块类型 | 标签键 | 工具（按 DOM 顺序） | 触发与写回 |
|---|---|---|---|
| `code_block` | `edit.block.editCodeBlock` | `<select #blk-lang-sel>`：空 / javascript / python / bash / json / html / css / sql / mermaid | 语言**只在退出时**统一写回（`pendingLang`）`edit-handler.js:1337`-`1345`、`1473`-`1479` |
| `mermaid` | `edit.block.editMermaid` | `<span hint>类型:</span> + <select #blk-mermaid-type>`：graph TD / sequenceDiagram / classDiagram / stateDiagram-v2 / erDiagram / gantt | 同上；注意 mermaid 由 `code_block + lang=mermaid` 归一得到（`edit-handler.js:1071`-`1072`） |
| `math_block` | `edit.block.editMathBlock` | `<span hint>符号:</span>` + 32 个 `.-math-sym-btn[data-sym]`（α…∃） | 点符号在**浏览器选区**处 `insertNode`（不改 AST）；退出时用 `blockEl.textContent` 重建 `$$ … $$`（`edit-handler.js:1346`-`1360`、`1480`-`1483`） |
| `table` | `edit.block.editTable` | `#blk-add-row`（+行）、`#blk-add-col`（+列） | ⚠️ **两个按钮无任何事件绑定**；退出时表格分支显式不处理内容（`edit-handler.js:1451`-`1452`） |
| `image` | `edit.block.editImage` | 对齐 `.-img-align-btn`（左/中/右）+ `#img-size-slider`(50–800 step10) + `#img-size-val` + `#img-name-size-slider`(10–32) + `#img-name-val` + `#img-name-toggle` + `#img-mgr-btn` | 全部经由事件写回源码行（见 §3.3） |
| `math_inline`（行内公式） | `edit.block.editInlineMath` | 同 `math_block` 的符号条 | 由双击 `.-math` / `mjx-container[data--inline-math]` 进入，非 `_BLOCK_TOOLS` 表项（`edit-handler.js:983`-`1059`） |

**颜色/画笔区段（`color.*` / `brush.*`）不在这里**：`H▾/色▾` 的色板与画笔属于 `.-format-bar`（§2.3），块编辑栏不提供颜色控件；自定义颜色增删文案键为 `color.added/deleted/inPalette/customTitle`（`i18n/zh-CN.js:437`-`457`）。

### 2.5 撤销 / 重做

**存在两套互不相通的栈**：

| | 源码编辑区 | 预览区（AST 编辑管线） |
|---|---|---|
| 实现 | `_srcUndoStack` / `_srcRedoStack` | `undoStack` / `redoStack` |
| 锚点 | `app.js:6890`-`6971` | `app.js:8152`-`8319` |
| 快照内容 | `{ body, caret:{line,col} }` | `{ body, cursorAST }` |
| 粒度 | 输入按「同行 + 间隔 <1200ms」合并为一个单元（`app.js:7051`-`7060`）；Enter / 行首退格 / 行末 Delete / 跨行选区删除 / 粘贴各自**强制入栈**（`app.js:7233`、`7294`、`7323`、`7338`、`7449`） | 单字符输入按 `kind + blockIndex + nodePath + offset` **连续同类合并**（`app.js:8225`-`8234`）；Enter / 样式 / 选区删除强制分组（`8427`、`8438`、`9271`、`9429`） |
| 原子分组 | 粘贴期间 `_srcPasting=true`，`input` 不再入栈 | `beginUndoGroup()/endUndoGroup()`：粘贴多行、跨块样式、替换图片整体算一步（`app.js:8252`-`8267`、`9679`-`9689`、`9339`-`9353`） |
| 栈上限 | **300**（超出 `shift()` 丢最旧） | **无上限** |
| 快捷键 | 焦点在源码行内时 Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z（`app.js:7212`-`7221`） | 焦点在预览区时 Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z（`edit-handler.js:627`-`645`） |
| 切换文件 | `srcResetUndo()` 清空并重建基线（`app.js:1441`、`6964`-`6971`） | `MemoriaEditSync.resetHistory()`（`app.js:1421`-`1422`） |

注意：预览区撤销/重做会 `renderEditor + renderPreview` 并清空 `preview_body` 缓存（`app.js:8281`-`8292`）；两套栈**不同步**，在源码区 Ctrl+Z 不会撤销预览区刚做的编辑。

### 2.6 粘贴与复制

| 场景 | 判定 | 行为 | 锚点 |
|---|---|---|---|
| 源码区原生粘贴（Ctrl+V） | `paste` 事件在 `.-line-content` 内 | `preventDefault` → `applyEditorPaste`：按 `\n` 拆行，首段用 `execCommand("insertText")`（失败则手动插文本节点），其余每段**新建一个 `.-line`**，整体一个撤销单元 | `app.js:7429`-`7439`、`7447`-`7529` |
| 源码区右键「粘贴」 | 无选中文本且在行内容上 | 读 `navigator.clipboard.readText()` 后复用 `applyEditorPaste`；光标不在源码行 → 状态栏 `cfg.clip.needCursor` | `app.js:7532`-`7556`、`7560`-`7574` |
| 预览区光标右键「粘贴」 | `#preview.contentEditable==="true"` 且 (i) 不在图片/链接上；(ii) `getSelectionInContainer` 返回空（即折叠光标） | `syncPreviewCursorForPaste()` 用当前选区刷新 `EH.cursorAST` → `pasteAtCursor()`：`beginUndoGroup` → `insertText(首行)` → 每行 `splitParagraph()+insertText` → `endUndoGroup` | `app.js:9544`-`9565`、`9639`-`9691` |
| 预览区有选中文本右键 | `getSelectionInContainer` 非空 | 弹**链接/知识点/样式**菜单（不是粘贴菜单）：复制、加粗、斜体、荧光笔▾、字体色▾、创建链接、设为知识点、复制 Markdown | `app.js:9566`-`9635`、`link-context-menu.js:162`-`229` |
| 预览区原生 Ctrl+V | `beforeinput` 只拦截 `insertText / deleteContent* / insertParagraph` | **不拦截 `insertFromPaste`** → 走浏览器原生 DOM 编辑（后续重渲染会以源码为准覆盖） | `edit-handler.js:581`-`625`（`else return` 在 `612`-`614`） |
| 复制 | 全仓**没有 `copy` 事件处理器**（grep `"copy"` 仅命中 kb-agent/kb-check 的 `execCommand("copy")` 报告导出） | 复制走浏览器原生（默认同时写 `text/html` 与 `text/plain`）；本应用侧的「复制」菜单项一律只写 `text/plain`：`navigator.clipboard.writeText()` | `link-context-menu.js:76`-`86` |

即：**「复制的格式保持 / 富文本粘贴」当前未实现**——右键菜单复制纯文本，粘贴只读 `text/plain`。

### 2.7 光标与选区恢复

| 辅助 | 作用 | 触发时机 | 已知失效场景 |
|---|---|---|---|
| `EH._caretInPreview` | 显式状态机：编辑光标是否真实在预览区（图片按钮可用性依赖它） | `focusin`（`image-tools.js:535`-`542`）、预览区 `mouseup` 成功定位（`edit-handler.js:756`）、编辑模式切换（`edit-handler.js:89`-`97`）、切文件（`app.js:1458`） | 无独立「失焦」收尾事件；靠 `focusin` 落到非预览元素时置 false |
| `restoreCursor` / `restoreSelection` / `restoreSelectionMulti` | 用 AST 坐标重建光标或非折叠选区 | 每次 `commit` / `commitSelection` / 撤销 / 样式应用 | 若 `astToDom` 返回 null → 退化为折叠光标到选区末尾（`app.js:7758`-`7763`、`7791`-`7795`） |
| `syncFromSelection(tag)` | DOM Selection → `EH.currentCursor` + `EH.cursorAST` + 源码假光标 | 预览区 `mouseup`、方向键、`beforeinput`、`compositionstart` | 行号取自 block 的 `data--src-line`；LIST 需再加 `listItemIndex`（`edit-handler.js:268`-`278`） |
| `showFakeCursor` / `hideFakeCursor` | 分栏模式下在源码行内插入 `.-sync-cursor` 假光标（供对位校验） | 仅 `state.viewMode === "split"`（`edit-handler.js:299`-`301`） | 非分栏不显示；源码区 `mousedown/focus` 即清除（`edit-handler.js:702`-`705`） |
| `showPreviewCursor` / `hidePreviewCursor` | 源码光标 → 预览块加 `.-preview-cursor`（源码→预览方向指示） | 仅分栏；`keyup/mouseup/focus` 同步（`edit-handler.js:192`-`206`） | 不可编辑块不显示光标（`edit-handler.js:165`-`167`） |
| `_pendingPreviewRange` | 格式按钮点击前的选区缓存 | 全局 `mousedown` 捕获（`app.js:10036`-`10051`） | 点进预览区即作废；只在拿到有效非折叠选区时写入（`app.js:9696`-`9707`） |

⚠️ 本仓**不存在**名为 `_restorePreviewSelection` 的函数（全库 grep 无命中）；对应职责由上表的 `restoreSelection*` 与 `_pendingPreviewRange` 分担。

## 3. 交互流程

### 3.1 给预览区文字加样式
`mouseup`（预览区，编辑模式下）→ `syncFromSelection("click")` 刷新锚点 → 点 `B` → 命中全局 `mousedown` 捕获 → `hasExistingSelection()` 为真 → `applyFormat("bold")` → `applyStyle` → 改写 AST inline 树 → `spliceBlockSource` + `renderEditor` + `reRenderBlock` → `restoreSelection` 保持选区 → 状态栏 `cfg.style.applied`（`edit-handler.js:711`-`758`、`app.js:10055`-`10063`、`9370`-`9391`、`8129`-`8138`）。

### 3.2 双击进入块编辑
`dblclick`（编辑模式 + 非源码视图）→ 先判行内公式命中的是 `.-math` 还是 `mjx-container[data--inline-math]` → `enterInlineMathEditMode`；否则找最近 `.-src-block` → `isNonEditableBlock` → 图片块走 Lightbox（不进编辑），其余 `enterBlockEditMode`（`edit-handler.js:1559`-`1613`）。退出方式：Escape、点击块外、点击 `#block-edit-bar` 外（`1650`-`1667`）。

### 3.3 图片块：单击进编辑 + 属性写回
单击图片块（非 img 本体）→ `enterBlockEditMode`（`edit-handler.js:1616`-`1647`）；单击名称文字 → 替换成原生 `<input.-caption-input>`，Enter/失焦提交（`1271`-`1323`）；对齐/滑条/名称开关 → `dispatchImageAttr` 派发 `memoria:image-attr`，名称提交派发 `memoria:image-caption`，由 `app.js` 改源码行后**重新进入编辑**（`1326`-`1332`、`1674`-`1684`、`image-tools.js:486`-`519`）。

### 3.4 画笔连续涂抹
无选区时点 `B`/色块 → `armBrush` → `body.-brush-active`（鼠标换成画笔光标，`app.css:3430`-`3433`）→ 在预览区拖选文字 → `mouseup` 捕获 → `_applyBrushToRange`（`forceApply=true`，固定顺序 加粗→斜体→高亮→字体色）→ 状态栏 `brush.applied`。Esc 或右键点已选样式取消（`app.js:10607`-`10751`）。

## 4. i18n key 前缀（代表键）

| 前缀 | 代表键 | 用途 |
|---|---|---|
| `edit.mode.*` | `edit.mode.btn`、`edit.mode.title`、`edit.mode.browseTitle`、`edit.mode.aria` | 编辑模式开关 |
| `edit.fmt.*` | `edit.fmt.boldTitle`、`edit.fmt.imageTitle` | 格式按钮 title |
| `edit.block.*` | `edit.block.editCodeBlock`、`edit.block.lang`、`edit.block.symbols`、`edit.block.editImage`、`edit.block.nameOn/nameOff` | 块编辑标签与工具 |
| `color.*` | `color.yellowShort`、`color.noneShort`、`color.addTitle` | 色板 |
| `brush.*` | `brush.ready`、`brush.applied`、`brush.cancelPart`、`brush.noStyle` | 画笔状态提示 |
| `cfg.style.*` / `cfg.clip.*` | `cfg.style.applied`、`cfg.style.singleLineOnly`、`cfg.style.needPreviewSel`、`cfg.clip.pasted`、`cfg.clip.needCursor` | 状态栏结果/失败 |
| `view.*` | `view.source`、`view.preview`、`view.split` | 视图切换（详见 04 篇） |

键值全文见 [i18n-inventory.md](../i18n-inventory.md)；本篇仅列前缀与代表键（`i18n/zh-CN.js:575`-`637`、`431`-`467`）。

## 5. 边界与已知坑

1. **工具栏 tip 里的 Ctrl+B / Ctrl+I 未实现**：`index.html:153`-`154` 与 `edit.i18n` 文案声称 `(Ctrl+B)`/`(Ctrl+I)`，但全库无 `b`/`i` 的键盘处理（`ctrlKey` 仅出现在源码撤销、缩放、预览撤销三处：`app.js:7214`、`12204`、`edit-handler.js:632`）。
2. **表格块是「假编辑」**：`+行/+列` 按钮无绑定；退出块编辑时表格分支不采集内容、不写回、不标脏（`edit-handler.js:956`-`957`、`1451`-`1452`、`1523`）。
3. **两个选区体系不通用**：源码区用 `getEditorSelectionInfo()`（单行 + 源码列号），预览区用 `domToAst/astToSrc`（AST 坐标）；跨行源码选区调样式直接失败（`app.js:10797`-`10800`）。
4. **编辑模式关闭后**：源码行、预览区均不可编辑，且两处右键编辑菜单都不弹；但已缓存的 `_pendingPreviewRange` 不受编辑模式影响。
5. **`.-readonly` 是空转 class**：`setSourceEditable` 加/去它，但 `app.css` 与 `theme/memoria.css` 中**没有该选择器**（全 CSS 目录 grep 无命中）。
6. **`#editor-header` 在图片编辑时隐藏 `#file-meta`**（`display:none`），退出时恢复（`edit-handler.js:1116`-`1118`、`1441`-`1442`）——若其他逻辑依赖 `#file-meta` 可见性需留意。
7. **块编辑中 `originalContent` 取自 `blockEl.textContent`**（`edit-handler.js:1130`），对已被 MathJax/Mermaid 替换过的块（公式块、mermaid 块）而言该文本是**渲染产物**而非源码；块级公式退出时以它重建 `$$…$$`（`1480`-`1483`）——见 04 篇「未证实/待确认」第 1 条。

## 6. 代码锚点表

| 主题 | 文件:行 |
|---|---|
| 编辑器 DOM 结构 | `index.html:149`-`207` |
| 格式栏 / 块编辑栏 / 视图切换 / 编辑模式开关 | `index.html:152`-`196` |
| `#editor-wrap`/`#editor-header` 布局 | `app.css:3081`-`3103` |
| 视图容器与三态显隐 | `app.css:3441`-`3459` |
| `.-editor` 字号变量 | `app.css:3461`-`3468`；`display-settings.js:79`-`85` |
| 行 / 行号 / 行内容样式 | `app.css:3598`-`3636` |
| 格式按钮 / 分隔 / 下拉 / 色块样式 | `app.css:3136`-`3234` |
| 画笔光标与 `brush-armed` | `app.css:3430`-`3439` |
| 块编辑栏与工具样式 | `app.css:3756`-`3821` |
| 编辑器渲染与 `--lineno-ch` | `app.js:1542`-`1565` |
| 行号重排 | `app.js:6974`-`6990` |
| 编辑模式切换 | `edit-handler.js:71`-`123`；`app.js:12452`-`12462` |
| 格式栏绑定 | `app.js:10032`-`10158` |
| 选区捕获 / 取用 | `app.js:9693`-`9742` |
| 工具栏 active 刷新 | `app.js:9932`-`9976` |
| 原子块选中高亮 | `app.js:9978`-`10022` |
| `applyFormat` / 源码兜底 | `app.js:10822`-`10907` |
| 画笔实现 | `app.js:10549`-`10751` |
| 下拉定位 | `app.js:10759`-`10783` |
| `_BLOCK_TOOLS` | `edit-handler.js:906`-`977` |
| 进入块编辑（图片 / 其他 / 行内公式） | `edit-handler.js:983`-`1165` |
| 图片工具栏与名称编辑 | `edit-handler.js:1187`-`1332` |
| 退出块编辑与写回 | `edit-handler.js:1366`-`1544` |
| 双击 / 单击 / 退出事件 | `edit-handler.js:1554`-`1668` |
| 块/行内编辑再入与光标落点 | `edit-handler.js:1674`-`1704` |
| 预览区 `beforeinput` 拦截 | `edit-handler.js:577`-`625` |
| IME 组合处理 | `edit-handler.js:653`-`694` |
| 预览区方向键 + 跳过不可编辑块 | `edit-handler.js:762`-`889` |
| 源码撤销栈 | `app.js:6890`-`6971`；`7212`-`7221` |
| 源码 input 与合并策略 | `app.js:7042`-`7065` |
| 源码跨行编辑（方向键/退格/Delete/Enter） | `app.js:7204`-`7419` |
| 源码粘贴 | `app.js:7422`-`7556` |
| 预览撤销栈 | `app.js:8152`-`8319` |
| 预览撤销快捷键 | `edit-handler.js:627`-`645` |
| 预览粘贴 / 折叠光标右键 | `app.js:9639`-`9691`；`9544`-`9574` |
| 右键菜单条目 | `link-context-menu.js:162`-`259` |
| 图片插入按钮可用性 | `image-tools.js:163`-`176`、`521`-`543` |
| 应用门面 `MemoriaApp` | `app.js:12631`-`12674` |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未能取证）：内置 Chromium/WebView2 下 `document.execCommand("insertText")` 在源码粘贴路径的失败率与回退分支（`app.js:7474`-`7487`）实际命中情况——需运行时验证。
- ⚠️ 待确认（未能取证）：`#btn-insert-image` 的 `title` 与 `edit.fmt.imageTitle` 文案声称「需先将文本光标置于预览区域」；实际判据是 `EH._caretInPreview` 状态机而非实时 selection（`image-tools.js:164`-`170`），在「光标在预览区但焦点被弹窗夺走」等场景的实际可用性未做运行时验证。
- ⚠️ 待确认（未能取证）：分栏模式下 `.-sync-cursor` 假光标与真实选区的关系只在源码 `keyup/mouseup/focus` 时刷新（`edit-handler.js:203`-`205`），切标签/程序化改内容后是否残留未验证。
- ⚠️ 未实现但界面有入口：表格 `+行/+列` 按钮（`edit-handler.js:956`-`957`）无绑定，本仓无表格编辑写回路径。
- ⚠️ 未实现但文案有声明：`Ctrl+B` / `Ctrl+I` 快捷键（`index.html:153`-`154`）。
- ⚠️ 未实现：复制的格式保持（无 `copy` 处理器）；粘贴只读 `text/plain`（`app.js:7435`、`9662`）。
