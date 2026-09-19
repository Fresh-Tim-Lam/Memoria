# 07 · 检索与图片

> **用途**：把顶栏检索（搜索框 / 范围切换 / 结果面板 / 跳转）与图片子系统（插入入库 / 图片管理视图 / 行内属性与名称编辑 / Lightbox / 引用诊断修复 / 静态路径解析）写到可据以定位实现的粒度。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[README.md](./README.md)（本套用法与维护约定）、[01-shell-and-layout.md](./01-shell-and-layout.md)（顶栏与弹窗层级）、[03-editor-and-formatting.md](./03-editor-and-formatting.md)（格式栏 / 块编辑栏）、[04-preview-and-rendering.md](./04-preview-and-rendering.md)（渲染后 DOM）、[../preview-formats.md](../preview-formats.md)（**图片属性写法权威**）、[../image-features.md](../image-features.md)（图片链路背景）、[../i18n-inventory.md](../i18n-inventory.md)（文案清单）。
> **状态**：生效中，2026-09-15。

---

**证据锚约定**：`文件:行号` 以仓库根目录为基准。前端在 `src/memoria/ui/static/app/**`（下称 `index.html` / `app.css` / `js/*.js`）；后端在 `src/memoria/services/**` 与 `src/memoria/presentation/**`。图片属性（`width` / `align` / `name-size` / `name`）的**语法权威**是 [../preview-formats.md](../preview-formats.md)，本篇只写界面与交互。

## 1. 区域概览

```
#toolbar                                    index.html:35
└── .toolbar-search-wrap                    index.html:71   app.css:1967-1981（宽 min(380px,42vw)）
    ├── #toolbar-search-scope               index.html:72   role="switch"，整块可点
    │   ├── #toolbar-search-scope-kb        index.html:73   「全库」（HTML 初值 .active）
    │   └── #toolbar-search-scope-file      index.html:74   「文件」
    └── .-toolbar-search-field              index.html:76
        ├── #toolbar-search                 index.html:77   input[type=search]
        └── #toolbar-search-panel           index.html:78   结果面板，z-index 9000（app.css:2068）

图片（运行时创建，无静态 HTML 节点）
├── #-image-manager .-modal                 image-tools.js:240-259（z-index 1000，app.css:4097）
│   ├── #imgr-stat                          image-tools.js:251
│   ├── [data-act=refresh|diagnose|cleanup] image-tools.js:252-254
│   └── #imgr-grid .-image-mgr-grid         image-tools.js:256（app.css:3851-3859）
├── #-img-diagnose .-modal                  image-tools.js:286-318（诊断子弹窗）
└── .-lightbox-overlay                      markdown-preview.js:507（z-index 99999，app.css:4004-4005）
```

## 2. 逐处细节

### 2.1 搜索框与范围切换

| 元素 | 位置 / 尺寸 | 样式类 | 交互 | 状态与边界 |
|---|---|---|---|---|
| 搜索范围开关 | `.toolbar-search-wrap` 左端 | `.-toolbar-search-scope`（app.css:1990-1999） | 整块可点 / 可聚焦；click 或 Enter/Space 翻转「全库 ⇄ 文件」（toolbar-search.js:253-263）；子按钮 `pointer-events:none`（app.css:2008） | 内部「文件」按钮无 `currentPath` 时 `disabled`（toolbar-search.js:60）、title 改为 `app.openFileFirst`；`aria-checked` 同步（toolbar-search.js:67） |
| 全库 / 文件 子按钮 | 同上 | `.-toolbar-search-scope-btn[.active]`（app.css:2001-2019） | 不单独响应点击（父级统一处理） | 当前态加 `.active`（蓝底白字） |
| 搜索框 | 高 1.5rem，虚线边框，聚焦转实线（app.css:2029-2052） | `.-toolbar-search` | 输入防抖 **220ms**（toolbar-search.js:245-252）；Enter = 搜索、Shift+Enter = 仅当前文件、Esc = 关面板并失焦、聚焦时有内容立即重搜（toolbar-search.js:265-277）；Ctrl+K 聚焦并全选（toolbar-search.js:33-38、281-286） | 未开库时状态栏报 `app.openKbFirst`（toolbar-search.js:132-135） |
| 占位文案 | — | — | — | i18n `search.ph`「搜索知识点、标签…」（zh-CN.js:532）；title `search.title`（含 Ctrl+K 提示） |

**范围持久化**：`state.toolbarSearchScope` 初值读 `localStorage["-search-scope"]`，缺省 `"kb"`（app.js:47）；每次切换写回同键（toolbar-search.js:90-92）。`openFile` 结束时调 `syncScope()` 刷新按钮态（app.js:1514）。

### 2.2 结果面板（`#toolbar-search-panel`）

| 项 | 证据 | 说明 |
|---|---|---|
| 定位 / 层级 | app.css:2054-2069 | 绝对定位于搜索框正下方（`top:calc(100%+2px)`），`max-height:min(240px,40vh)`、`overflow-y:auto`，**`z-index:9000`** |
| 无障碍 | index.html:78 | `aria-live="polite"` |
| 显隐 | toolbar-search.js:40-49 | 仅切换 `.hidden`；点面板外（非 `.toolbar-search-wrap` 内）即隐藏（toolbar-search.js:278-280） |
| 加载态 | toolbar-search.js:147-149 | 不渲染 loading 占位，只在状态栏写 `search.statusSearching`（`"搜索…"` + `q + scopeHint`） |
| 空结果 / 无正文命中 | toolbar-search.js:163-180 | 单个 `.-search-placeholder`，文案 `search.noMatch`「无匹配 · {q}」；若请求了语义模式而语义不可用，追加 `search.semReason*`（按 `reason` 映射 `embedding_not_enabled` / `not_installed` / `index_empty`，其余 reason 原样输出，toolbar-search.js:170-175）；正文定位关闭时追加 `search.bodyLocateTip`（toolbar-search.js:177-179） |
| 检索失败 | toolbar-search.js:153-157、238-241 | `status==="error"` 或抛异常 → **隐藏面板**，状态栏 `search.statusSearchFailed` + 后端 message（面板内无错误提示） |
| KP 命中条目 | toolbar-search.js:183-196 | `<button.-suggest-item.-toolbar-search-hit data-search-kind="kp" data-search-idx=i>`；左列 `.-suggest-score`（分数，title = `sources.join(", ")`），右列 `.-toolbar-search-main` 内两行：`.-suggest-label`（`label‖name‖id`）+ `.-toolbar-search-file`（**basename(file)**） |
| 正文命中条目 | toolbar-search.js:197-213 | 先插 `.-search-section-label`「正文定位」（仅在有 KP 结果时，toolbar-search.js:198-200）；条目 `data-search-kind="body"`，左列 `.-suggest-score--muted` 显示 `L{line}`（title `search.bodyLineTitle`），右列 label = `label‖snippet` + basename(file) |
| 分数格式化 | toolbar-search.js:102-127 | 按 `res.modes` 分支：`semantic` → `语义 {n}%`；`both|full` → `字 {n}` + `语义 {n}%` + 档位（>0 才拼）；`lexical` 且有 `tier` → `字 {n} · {档位}`；否则纯数字 |
| 档位文案 | toolbar-search.js:98-100；zh-CN.js:551 | `search.tier.high|medium|low` = 高 / 中 / 低 |
| 完成态 | toolbar-search.js:236-237 | 状态栏 `search.statusDone` + `search.resultCount`「{total} 条 · {q}{suffix}」，`total = 结果数 + 正文命中数` |
| 结果上限 | toolbar-search.js:152 | 固定 `limit=20`（`call("search", q, scope, 20, modes, relPath)`）；正文定位由后端再夹到 ≤15（search_kernel.py:33） |
| 无键盘导航 | toolbar-search.js:265-273 | 无 ↑/↓ 选择、无 Enter 打开首条；结果只能鼠标点击 |

**点击跳转**（toolbar-search.js:215-234）：

- KP 命中 → `openFile(hit.file, { kpId: hit.kp_id || null })`；`openFile` 内 `kpId` 分支查 `range_resolved` 命中则 `highlightRange(start,end)`，并把左侧 KP 列表滚动到该 KP（app.js:1484-1491）。
- 正文命中 → `openFile(hit.file, { lineHint: hit.line })`；`openFile` 内 `lineHint` 分支 `highlightRange(line,line)`（app.js:1492-1497）。
- 两级都无 `file` 时直接 `return`（不跳转、面板已隐藏，toolbar-search.js:223、230）。

### 2.3 命中策略的界面可见表现

| 策略 | 界面表现 | 证据 |
|---|---|---|
| 别名命中 | 无独立标记；体现在分数与 `sources` title（如 `alias-explicit-exact`、`alias-explicit-fuzzy`） | lexical_index.py:274-281；toolbar-search.js:188 |
| 拼音命中 | 同上（`name-pinyin` / `id-pinyin` 走倒排 postings） | lexical_index.py:99-104、275 附近；lexical_tokenizer.py:59-75 |
| 模糊 / 包含命中 | 同上（`name-fuzzy` = 名称包含、`id-fuzzy` = id 包含） | lexical_index.py:258-263 |
| 分档（高/中/低） | 直接显示在分数列尾部（lexical 模式） | retrieval_fusion.py:97-129；toolbar-search.js:122-124 |
| 语义不可用 | 空结果时给出 3 类原因提示（见 §2.2）；非空结果时不提示 | search_kernel.py:60-88；toolbar-search.js:166-176 |
| 检索失败重试 | 无重试按钮；改输入或重新聚焦即重搜（toolbar-search.js:274-277），错误留在状态栏 | toolbar-search.js:153-157 |
| 默认模式 | `lexical`（纯字面）；语义需在设置页开启 | search-settings.js:19-27、105 |

### 2.4 检索设置页（设置 → 检索）

页面由 `renderSettingsBody()` 生成（search-settings.js:249-289），宿主为设置弹窗的 `search` 页签（graph-settings.js:771、808-812）。

| 项 | 作用 | 默认值 | 证据 |
|---|---|---|---|
| `embeddingEnabled`「启用语义搜索（Embedding）」 | 决定请求模式：开 → `searchModes="both"`（Lexical + 语义 RRF 融合）、关 → `"lexical"` | **false** | search-settings.js:19-27、105、119-121 |
| `searchModes`（**派生，无 UI**） | 由 `embeddingEnabled` 单向推导，不能手工选值 | `"lexical"` | search-settings.js:89、105、121、233-237 |
| `bodyLocateEnabled`「搜索正文定位内容」 | 是否在 KP 结果之外追加 md 正文行内 substring 命中 | **false** | search-settings.js:25、107、241-245；后端开关 search_kernel.py:25-27 |

持久化：`localStorage["-search-settings"]` + 磁盘 `ui-settings.json` 的 `search` 段（`embedding_enabled` / `search_modes` / `body_locate_enabled`）（search-settings.js:13、153-175、187-221）；启动时磁盘仅作种子、本地优先（search-settings.js:101、211）。设置弹窗的「恢复默认」按钮**不会**重置本页（graph-settings.js:230-241 只重置 graph 与 check）。

### 2.5 图片插入（工具栏 / 编辑块 → 入库 → 写源码）

| 项 | 证据 | 说明 |
|---|---|---|
| 入口 | index.html:183 | 格式栏 `#btn-insert-image`「图片」（`.-fmt-btn`，初始 `disabled`） |
| 可用性状态机 | image-tools.js:163-176、521-543 | 仅当**文本光标真实位于预览区**（`MemoriaEditHandler._caretInPreview`，由 `focusin` 置位、切文件时清空 app.js:1458）时按钮可点；`selectionchange` 亦刷新。`mousedown` 阻止默认以免焦点离开预览区导致按钮当场失效（image-tools.js:528-530） |
| 选文件 → 入库 | image-tools.js:76-82 | `select_image_file`（ui.py:840）→ `import_image(local)`（ui.py:846 → document.py:833-882） |
| 入库语义 | document.py:833-882 | 白名单扩展名；**MD5 内容去重**（命中则复用已有副本并返回 `deduped=true`）；同名不同内容自动 `x-1.png` / `x-2.png`；返回相对路径 `.memoria/images/<名>` |
| 写入正文 | image-tools.js:83-90 | alt = 文件名去扩展名；写入 `![alt](<relPath>)`（**尖括号包裹**，防文件名含空格/中文时被从空格处截断）；未写 `width` 属性；成功状态栏 `img.insert.stored` |
| 写入位置 | image-tools.js:108-161 | `insertSourceLine()` 按「源码选区行 → 传入行号 → 预览光标所在块源码行 → 末行」择锚点，插入独占一行并入撤销栈 |
| 失败态 | image-tools.js:68-75、79-88 | 未开库 `app.openKbFirst`；未开文档 `img.insert.openDocFirst`；入库失败 `img.insert.importFailed`；无编辑器 `img.insert.failed` + `img.insert.noEditor` |
| 预览区右键 | image-tools.js:192-226、599-615 | 右键 `img.-preview-image` → 菜单「替换图片」/「删除图片（仅删引用）」；删除**只删正文行**，磁盘文件保留（`img.del.refsDone`）；替换保留原 alt 与 title 属性串（image-tools.js:208-217） |
| 图片管理视图内的插入 | image-tools.js:397-408 | 卡片「插入」→ 写 `![alt](<rel> "width=300")`（**带默认宽度 300**） |

### 2.6 图片管理视图

入口：编辑块工具栏「图片管理」按钮（`#img-mgr-btn`，edit-handler.js:974、1231-1236）派发 `memoria:open-image-manager`，由 image-tools.js:657 打开。**不是**独立菜单项。

| 元素 | 证据 | 说明 |
|---|---|---|
| 弹窗骨架 | image-tools.js:240-259 | 运行时创建 `#-image-manager`（类 `.-modal`），box 类 `.-image-mgr-box`（宽 `min(760px,94vw)`、高 ≤82vh，app.css:3825-3830） |
| 标题栏 / 关闭 | image-tools.js:246-249、260-261 | ✕ 与 backdrop 点击均关闭（直接 `remove()`，非 `.hidden`） |
| 统计行 | image-tools.js:251、344-345 | `img.statSummary`「共 {total} 张图片 · 已引用 {used} · 未使用 {unused}」 |
| 工具按钮 | image-tools.js:252-254 | 「刷新」`img.refresh`、「检查异常引用」`img.diagnose`、「清理未使用图片」`img.cleanup`（危险色） |
| 列表 | image-tools.js:337-384 | **单一扁平网格**（`grid-template-columns: repeat(auto-fill, minmax(210px,1fr))`，app.css:3855-3856），无「引用中 / 未使用 / 可清理」三个分区；分区语义只由卡片名称行内紧跟的 `.-img-tag` 徽标表达：`.-img-tag-used`「已引用 {n}」/ `.-img-tag-unused`「未使用」（image-tools.js:354-356；样式 app.css:3922-3932）；卡片含缩略图、名、格式化体积、引用文案（`img.refsUsed` / `img.refsUnused`）与「插入」「删除」 |
| 缩略图创建方式 | image-tools.js:371-383 | 模板**刻意不含 `<img>`**；改用 `new Image()` 逐个创建并 `insertBefore`，src = `/files/ + relPath`。注释说明 WebView2 下经整串 `innerHTML` 解析出的 `<img>` 可能「已加载但不绘制」 |
| 空态 | image-tools.js:341、346-348 | 加载中 `img.loading`；无资产 `img.emptyKb` |
| 卡片「删除」（已引用） | image-tools.js:410-436 | 当前文档有引用（按行包含 `rel` 或 `/files/rel` 计数）→ 确认后**只删当前文档的引用行**；若当前文档 0 引用但别处引用 → `img.del.blockedTitle/Body`（不可删，建议去引用方或走清理） |
| 卡片「删除」（未引用） | image-tools.js:437-452 | 确认后 `cleanup_unused_images([rel])` 真删磁盘文件（不可恢复） |
| 「清理未使用图片」 | image-tools.js:455-483 | 先 `unused_images()` 取列表；为空只报 `img.cleanup.none`；否则确认框列出前 5 个名 + 「等 N 张」→ `cleanup_unused_images()` 全量清理 |

### 2.7 图片属性编辑与名称编辑

单击图片块 → 进入块编辑（`enterBlockEditMode`，edit-handler.js:1082-1127），格式栏隐藏、块编辑栏显示（edit-handler.js:1109-1113），标题「编辑图片」（i18n `edit.block.editImage`），并把 `#file-meta` 隐藏（edit-handler.js:1117-1118）。

| 控件 | 证据 | 行为 |
|---|---|---|
| 对齐 left/center/right | edit-handler.js:963-966、1193-1206 | 三按钮 `.-img-align-btn[data-align]`；当前值加 `.active`（app.css:3940-3943）；点击 → `memoria:image-attr{align}` |
| 宽度滑条 `#img-size-slider` | edit-handler.js:967-969、1209-1228 | min 50 / max 800 / step 10，初值取源码 `width`，缺失时取当前渲染宽度；`input` 实时改内联 `width` + `maxWidth:100%`；`change` → `memoria:image-attr{width}` |
| 名称字号滑条 `#img-name-size-slider` | edit-handler.js:970-972、1239-1256 | min 10 / max 32 / step 1，初值取 `name-size`，缺失时取 caption 计算字号；`input` 实时改 caption `font-size`；`change` → `memoria:image-attr{name-size}` |
| 名称显示开关 `#img-name-toggle` | edit-handler.js:973、1260-1268 | 文本 `edit.block.nameOn|nameOff`；`active`（高亮）= 名称显示中；点击在 `hide` / `show` 间切换并写 `name` 属性 |
| 图片管理入口 | edit-handler.js:974、1231-1236 | 同 §2.6 |
| 名称文字编辑 | edit-handler.js:1271-1323、1620-1637 | **单击图片下方名称文字**（`[data--image-caption]`）→ 替换为原生 `<input.-caption-input>`（字号继承、内容预选）；Enter 或失焦提交 → `memoria:image-caption{caption}` → 写回 `![alt]` → 光标落到相邻可编辑块（`placeCaretAfterNameEdit`） |

**属性写回**：`updateImageAttrsLine()` 解析行尾 `"k=v,…"` 串做**键级合并**（保序、保留未知键、缺失即追加），再整行替换（image-tools.js:486-512）；名称写回只改 `![…]` 内的 alt，保留 url 与 title（image-tools.js:515-519）。写回后整体重渲染两窗格并入撤销栈（image-tools.js:179-190）；属性路径随后**重进图片编辑**（`reenterImageEdit`，edit-handler.js:1674-1684），名称路径不重进（edit-handler.js:1691-1704）。

**单击 / 双击差异**：

| 操作 | 结果 | 证据 |
|---|---|---|
| 单击图片块（含图片本体、名称外的空白） | 进入/保持图片编辑工具栏 | edit-handler.js:1615-1647 |
| 单击图片块内空白（非 img） | 光标停靠图片前/后（按点击在图片中线左右判定），并置 `_caretInPreview` | edit-handler.js:736-749 |
| 单击名称文字 | 进入名称编辑（若尚未在图片编辑模式，先进入） | edit-handler.js:1620-1637 |
| **双击图片** | 打开 **Lightbox** 放大；若已在图片编辑模式则先退出编辑模式 | edit-handler.js:1604-1609；markdown-preview.js:504-517 |
| Esc / 点击块外 | 退出块编辑 | edit-handler.js:1650-1667 |

### 2.8 渲染、Lightbox 与路径解析

| 项 | 证据 | 说明 |
|---|---|---|
| 块渲染 | renderer.js:116-160 | `p.-src-block.-image-block[data--block-index]` > `img.-preview-image` + `span.-image-caption[data--image-caption]`；`width/height` → img 内联样式（并置 `maxWidth:100%` 解除默认钳制）；`align` → 容器类 `.-image-align-{left|center|right}`；`name-size` → caption `font-size`；`name=hide` → caption `display:none`；未知 key 只 `console.warn` 并忽略 |
| 默认尺寸钳制 | app.css:3813-3817 | 未显式给尺寸时 `.-preview img { max-width:35% }` |
| 图片块编辑外观 | app.css:3935-3939 | 编辑中图片加蓝色虚线 outline + `cursor:pointer` |
| caption 样式 | app.css:3960-3987 | 默认灰色 0.875rem；编辑中加 `.-caption-editing`（虚线框 + 淡蓝底）；input 透明无边框、继承字体 |
| Lightbox | markdown-preview.js:496-519；app.css:4003-4020 | 对容器内每个 `img` 绑 `dblclick`：**运行时新建** `.` `-lightbox-overlay`（fixed、`inset:0`、`z-index:99999`、黑 85%）+ `img.-lightbox-image`（`max-width/height:95vw/vh`）；点击遮罩即 `remove()`；图片光标改为 `zoom-in` |
| Lightbox 挂载点 | markdown-preview.js:513 | `document.body`（不在 `#preview` 内） |
| 路径重写（源码 → AST） | app.js:1996-2026 | `rewriteMdImagePaths()` 在解析前把 `![…](<…>)` 与 `![…](.相对)` 重写为 `/files/` 编码路径（交由 `markdown-preview.rewriteLocalImagePaths`） |
| 路径重写（HTML） | markdown-preview.js:526-559 | 跳过 `http(s):` / `data:` / 绝对路径；`./` 开头按**当前文件目录**解析，其他相对路径按**KB 根**；逐段编解码（先 decode 再 encode，避免 `%` 二次编码）；前缀 `apiBase + "/files/"` |
| 静态服务 | static_server.py:56-91、132 | `/files/` 拦截 → 逐段 URL 解码 → `normpath(join(kb_root, 解码后路径))` → 必须落在 KB 根内（含 `kb+os.sep` 前缀边界校验，防兄弟目录绕过；Windows 下大小写归一比较）→ 存在才以图片 MIME 返回，否则 404 路径不命中；`_kb_root` 由 `set_kb_root()` 在开库时写入 |
| 懒加载 | — | ⚠️ 前端与后端均未发现 `loading="lazy"` / `IntersectionObserver`（见 §7） |
| 修复过的 WebView2 缺陷 | image-tools.js:371-374；app.css:3870-3872 | ① 缩略图不用 innerHTML 解析而是 `new Image()` 再插；② 卡片**不得**加 `overflow:hidden`（flex + overflow:hidden 会导致已加载图片不绘制） |
| 加载失败提示 | image-tools.js:545-564 | 捕获 `#preview` 内 `img` 的 `error`：加红虚线 outline + `opacity .55`、title/alt 追加 `img.missing`、`console.warn` |

### 2.9 图片引用诊断与后台自动清理

| 项 | 证据 | 说明 |
|---|---|---|
| 诊断入口 | image-tools.js:263、277-335 | 管理视图「检查异常引用」→ `diagnose_image_refs`（ui.py:881 → document.py:1168-1210） |
| 诊断结果 | image-tools.js:289-318 | 两类分区：① `unregistered`「已引用但未注册（N）」，逐条 `<code>src</code>` + `img.atLine`（doc + 行号）+ 缺失标记；② `missing`「引用格式正常但文件缺失（N）」 |
| 未注册含义 | document.py:1146-1159 | 指向 `.memoria/images/` 但**格式不可注册**（典型：文件名含空格/中文的裸 URL 未用 `<>` 包裹，会被判为「未引用」从而在自动清理时误删） |
| 一键修复 | image-tools.js:322-334 | 仅在第一类出现时给「一键修复为尖括号格式」→ `fix_unregistered_image_refs`（ui.py:888）；成功报 `img.status.fixDone` + `img.status.rewritten{n}`，随后移除弹窗并刷新列表 |
| 全清空态 | image-tools.js:296-298 | 两类皆空 → `img.diag.clean`「未发现异常引用」 |
| 管理视图即注册表重建点 | document.py:896-906 | `list_images()` 会 `rebuild_image_registry()` 并落盘 `registry.json`；`referenced` / `referencedBy` 取自注册表 |
| 未使用判定另走全量扫描 | document.py:1082-1102、1104-1144 | `unused_images` / `cleanup_unused_images` 用 `_scan_image_refs()`（实时扫全部 md，主正则 + `.memoria/images/` 提及兜底，document.py:927-954），**与 `list_images` 的注册表口径不一定一致** |
| 后台自动检查 | image-tools.js:566-597 | 开库/切库立即一次，其后每 30s tick、距上次 ≥5 分钟再跑；调 `image_registry_auto_check`（ui.py:874） |
| 自动清理语义 | document.py:1047-1080 | 按注册表删除「注册表内无引用」的图片，但有 **6 小时宽限期**（`_AUTO_CLEAN_GRACE_SEC = 6*3600`，document.py:980），避免刚入库/编辑中的图片被误删；用户显式清理不受宽限期限制 |

## 3. 交互流程

**3.1 搜索**：Ctrl+K（或点搜索框）→ 输入 → 220ms 防抖后 `runSearch()` → 取 `searchModes`/正文定位开关 → `call("search", q, scope, 20, modes, relPath)` → 渲染面板 → 点结果 → 关面板 → `openFile(file, {kpId|lineHint})` → 预览滚动并高亮（KP 走 `highlightRange(范围)`，正文走 `highlightRange(行,行)`）。Esc 关面板并失焦；点面板外关面板。

**3.2 插入图片**：把光标放进预览区（`_caretInPreview=true`，按钮解禁）→ 点「图片」→ `select_image_file` → `import_image`（去重/重名编号）→ 在源码光标所在行的**下一行**插入 `![alt](<rel>)` → 重渲染 + 标脏；成功后状态栏「图片已入库」。

**3.3 管理与清理**：编辑块工具栏「图片管理」→ 运行时建弹窗 → `list_images()`（重建注册表）→ 扁平网格（`new Image()` 补缩略图）→ 需要时「检查异常引用」→ 修复 / 「清理未使用图片」→ 确认 → `cleanup_unused_images`。

**3.4 属性与名称**：单击图片 → 块编辑栏（对齐 / 宽度 / 名称字号 / 名称开关 / 管理入口）；任一处改动 → `memoria:image-attr` → 改源码行 → 全量重渲染 → 重进图片编辑；单击名称文字走 `memoria:image-caption` → 改 alt → 光标移到相邻文本；双击图片 → Lightbox。

## 4. i18n key 前缀

| 前缀 | 覆盖 | 代表键（zh-CN.js 行号） |
|---|---|---|
| `search.*` | 范围按钮、占位符、状态、结果、分数与档位、检索设置段 | `search.scopeKb/scopeFile/ph/title/statusSearching/statusSearchFailed/statusDone/scopeFileSuffix/noMatch/bodySection/bodyLineTitle/resultCount/scoreLex/scoreSem/tier.*`（527-560） |
| `img.*` | 图片管理、插入、删除、清理、诊断、状态 | `img.title/openTitle/loading/refresh/diagnose/cleanup/statSummary/emptyKb/tagUsed/tagUnused/refsUsed/refsUnused/insert/delete/atLine/missing/edit.*/diag.*/status.*/insert.*/del.*/cleanup.*`（1004-1079） |
| `edit.block.*` | 图片块编辑工具栏标签与按钮 | `edit.block.editImage/align/alignLeft|Center|Right/imgWidth/size/name/nameSize/nameToggle/nameOn/nameOff`（edit-handler.js:960-975） |
| `app.openKbFirst` / `app.openFileFirst` | 未开库 / 未开文档的提示 | zh-CN.js 内 `app` 段（toolbar-search.js:133、image-tools.js:69） |

## 5. 边界与已知坑

1. **搜索面板层级高于所有弹窗**：面板 `z-index:9000`（app.css:2068）> `.-modal` 的 `1000`（app.css:4097）。弹窗不锁焦点，弹窗打开时 Ctrl+K 仍可聚焦顶栏搜索框（快捷键无弹窗判断，toolbar-search.js:281-286），此时结果面板会盖在弹窗之上。
2. **范围偏好在关库后不清除**：`state.toolbarSearchScope` 只在启动时读 localStorage（app.js:47）、切换时写（toolbar-search.js:90-92），`closeKb()` 不重置。若上次停在「文件」范围，**新开一个知识库且尚未打开任何文件**时直接搜索，会走 `scope==="file" && !currentPath` 分支报 `app.openFileFirst`（toolbar-search.js:143-146），而按钮上「文件」已处于 disabled 状态——用户看到的是「按钮灰着但范围仍是文件」。
3. **结果只显示 basename**（toolbar-search.js:28-31、191）：不同目录同名文件在面板中无法区分。
4. **检索失败无面板内反馈**：失败即 `hidePanel()`，只有状态栏一行红字（toolbar-search.js:153-157、238-241）。
5. **无键盘选择结果**：↑/↓ 与 Enter 都不用于选中结果（Enter 只触发搜索）。
6. **图片管理没有三分区**：现有实现是扁平网格 + 每卡 tag + 顶部一句统计（image-tools.js:337-384）；不存在「引用中 / 未使用 / 可清理」三块列表。引用计数口径也与「未使用」判定不同源（见 §2.9）。
7. **去重是静默的**：`import_image` 命中 MD5 去重时返回 `deduped:true`，但前端不区分，一律提示「图片已入库」（image-tools.js:78-90），用户无法得知复用旧文件。
8. **插入按钮默认不可点**：必须先把文本光标落到预览区（image-tools.js:163-176）；只读（编辑模式关闭）时永远 `disabled`（`previewHasCaret` 首行判断 `EH.editMode`，image-tools.js:164-170）。
9. **两条插入路径产物不同**：工具栏插入写 `![alt](<rel>)`（无宽度）；管理视图「插入」写 `![alt](<rel> "width=300")`（image-tools.js:86 vs 403）。
10. **双击图片不进入编辑**：双击固定是 Lightbox（edit-handler.js:1604-1609），与「双击进入编辑」的一般直觉相反；进入编辑用**单击**。
11. **caption 单击会拦截光标停靠**：正在编辑名称时，点击名称文字不再触发图片前后停靠（edit-handler.js:729-735），这是有意设计，但会让「点名称左侧空白」与「点名称文字」行为不同。
12. **后台自动清理会真删文件**：`image_registry_auto_check` 每 5 分钟（前端 tick 30s 判定）删除注册表外且 mtime 超 6 小时的图片（image-tools.js:575-597；document.py:1069-1078）。图片刚入库 6 小时内安全，但格式不可注册的引用（§2.9 第一类）一旦过宽限期即可能被删——这正是「检查异常引用 + 一键修复」存在的原因。
13. **`align` 只认三值**：`center|left|right` 之外的取值不生成容器类（renderer.js:135-139）；`width`/`height` 非数值时被 `_normalizeImageSize` 丢弃但仍会 `maxWidth:100%`。
14. **静态服务路径逃逸防护**：`/files/` 只服务 KB 根之内的文件（含 `kb+os.sep` 边界与 Windows 大小写归一），KB 之外一律 404（static_server.py:65-84）。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 搜索框 / 范围开关 / 面板 HTML | index.html:71-80 |
| 搜索框与面板 CSS（含 z-index 9000） | app.css:1967-2082 |
| 结果条目 CSS（分数 / 分节标签 / 两行主列） | app.css:1236-1323 |
| 范围切换与持久化 / Ctrl+K / 防抖 / Enter·Esc | toolbar-search.js:33-96、244-287；app.js:47、1514 |
| 检索执行与状态文案 | toolbar-search.js:129-242 |
| 分数格式化与档位 | toolbar-search.js:98-127 |
| 结果点击跳转（kpId / lineHint） | toolbar-search.js:215-234；app.js:1484-1497 |
| 检索 RPC 与内核 | ui.py:241-258；search_kernel.py:38-133 |
| 融合分档 / 来源集合 | retrieval_fusion.py:9-45、97-129 |
| 打分权重 / 拼音与别名倒排 | lexical_index.py:18-35、99-126、240-282；lexical_tokenizer.py:59-111 |
| 检索设置页（项 / 默认值 / 持久化） | search-settings.js:19-27、83-175、187-311；graph-settings.js:771、808-812 |
| 图片插入按钮与状态机 | index.html:183；image-tools.js:67-91、163-176、521-543 |
| 源码行插入 / 属性写回 / alt 写回 | image-tools.js:108-161、486-519 |
| 预览区图片右键（替换 / 删引用） | image-tools.js:192-226、599-615 |
| 图片管理弹窗（骨架 / 列表 / 卡片动作 / 清理） | image-tools.js:238-274、337-483 |
| 诊断与一键修复 | image-tools.js:277-335；document.py:1168-1210、1236 起 |
| 块编辑与图片工具栏 | edit-handler.js:960-975、1082-1127、1171-1185、1188-1269 |
| 名称编辑 / 单击 / 双击 / 重进编辑 | edit-handler.js:1271-1323、1604-1667、1674-1704 |
| 图片块渲染与属性 | renderer.js:116-160 |
| Lightbox / 路径重写 | markdown-preview.js:496-519、526-559、1413-1414；app.js:1996-2026 |
| 图片相关 CSS（尺寸 / 对齐 / 管理 / 编辑 / caption / Lightbox） | app.css:3812-4020 |
| 静态服务 `/files/` 解析 | static_server.py:56-91、132 |
| 后端图片资产 API 与实现 | ui.py:840-891；document.py:833-882、896-922、1047-1080、1082-1144 |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未能取证）：**图片懒加载**。全前端未检索到 `loading="lazy"` 或 `IntersectionObserver` 用于图片；是否由 WebView2 的 `loading` 默认行为间接生效未验证。
- ⚠️ 待确认（未能取证）：`search.semReason*` 只覆盖 3 个 `reason` 值（toolbar-search.js:170-175），其余 `reason` 原样显示英文键；后端实际会产出哪些 reason 未穷尽。
- ⚠️ 待确认（未能取证）：`res.results[i].sources` 的完整取值集合（前端只把它放进 title），未逐条与 `lexical_index.py` 的 `sources.append(...)` 全表比对。
- ⚠️ 待确认（未能取证）：搜索面板「盖住弹窗」的实际观感未在真机验证（由 z-index 数值推断）。
- ⚠️ 待确认（未能取证）：`#-image-manager` 是运行时创建的动态弹窗（类 `.-modal`，image-tools.js:241），未纳入 `#check-modal` 式的静态互斥体系，多个动态弹窗（图片管理 / 诊断）是否可能与静态弹窗叠加未实测。
- ⚠️ 待确认（未能取证）：`img.cleanup.doneList`（zh-CN.js:1069）在前端未见调用点，疑似遗留键；`img.menuLabel`（zh-CN.js:1000）同样未在 `js/**` 中检出。
- ⚠️ 待确认（未能取证）：`image_registry_auto_check` 的删除是静默的（前端 `catch` 后不打扰用户，image-tools.js:571-573），用户侧是否会收到任何提示未验证。
