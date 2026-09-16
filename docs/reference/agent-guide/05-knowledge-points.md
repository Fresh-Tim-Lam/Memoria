# 05 · 知识点（KP）

> **用途**：记录知识点子系统「侧栏列表长什么样、hover 怎么高亮、KP 弹窗四页各有什么控件、保存/删除/重命名如何落盘、配置弹窗三 Tab 与待确认流怎么走、范围高亮的两种语义」到可据以工作的粒度；供集成方与后续 Agent 对照代码改前端。
> **目标读者**：在 Memoria 之上做集成/移植的 Agent 与人；给 Memoria 前端写改动的人。
> **关联文档**：[README.md](./README.md)（维护约定）、[preview-formats.md](../preview-formats.md)（**渲染语法权威**，本篇不重复）、[04-preview-and-rendering.md](./04-preview-and-rendering.md)（`highlightRange`/`markRangeQuiet` 的预览侧浮层实现）、[03-editor-and-formatting.md](./03-editor-and-formatting.md)（源码行结构）、[i18n-inventory.md](../i18n-inventory.md)。
> **状态**：生效中，2026-09-15。

---

## 1. 区域概览

```
#-sidebar                                        （index.html:96）
└─ #sidebar-body-split                           （index.html:108）
   ├─ #sidebar-nav-panel                         （文件树 / 2D / 3D，见 06 篇）
   ├─ #sidebar-nav-kp-resizer                    （上下占比拖拽条，app.css:377）
   └─ #sidebar-kp-block                          （app.css:234）
      ├─ .sidebar-toolbar.-kp-toolbar            （index.html:124）
      │  ├─ 「知识点」 .-kp-toolbar-label
      │  ├─ #kp-count  .-muted                   （仅计数，无文案）
      │  └─ .-kp-toolbar-actions
      │     ├─ #btn-config  「配置」             （index.html:128）
      │     └─ #btn-kp-new  「新建」             （index.html:129）
      └─ #kp-list.-panel.-kp-panel               （index.html:132）

#kp-modal                                        （index.html:222-237，浮层在 #app 外）
└─ #kp-modal-box.-modal-box.-modal-tabbed       （app.css:752；resize:both，app.css:976）
   ├─ #kp-title「知识点配置」+ #kp-close
   ├─ #kp-body.-modal-body                       （Tab 由 renderKpModalTabs 注入）
   └─ .-modal-footer： #kp-delete / #kp-cancel / #kp-save

#config-modal                                    （index.html:239-251）
└─ #config-body → .-config-tabs[data-config-tab=kp|links|pending] + .-config-tab-panel
```

KP 弹窗的四个页签（`range` / `identity` / `tags` / `edges`）由 `renderKpModalTabs` 生成（`app.js:3117`-`3132`），文案键为 `cfg.panel.tabs.*`（`i18n/zh-CN.js:151`-`158`）。

## 2. 逐处细节

### 2.1 KP 列表（`#kp-list`）

渲染入口 `renderKpList(doc)`（`app.js:2103`-`2176`）。条目结构与状态：

```html
<div class="-kp-item active|error|warn" data-kp="<id>">
  <div class="-kp-name">名称（缺省回落 id）</div>
  <div class="-kp-meta"><span>L12–20 | 未配置 | 错误文案</span><span class="-tag">tag</span>…</div>
</div>
```

| 项 | 现状 | 锚点 |
|---|---|---|
| 排序 | 按 `range_resolved.start_line`，其次 `range.start.line_hint`，再退化 0 升序 | `app.js:2113`-`2117` |
| 计数 | `#kp-count` = 正式 KP 数；为 0 时清空文本 | `app.js:2118` |
| 行号/错误文案 | `rr.ok` → `L{start}–{end}`；`rr.error` → `errorLabel()` 并加 `error`（含 `not_found`）或 `warn` 类 | `app.js:2136`-`2145`、`2178`-`2183`；`errorLabel` `app.js:10913`-`10921` |
| 标签 | `.-tag` 逐个渲染（不折叠、不省略） | `app.js:2146`-`2148`；`app.css:3073`-`3078` |
| 当前选中 | `kp.id === state.activeKpId` → `active` 类（`background: var(--accent-soft)`） | `app.js:2138`；`app.css:3058` |
| 空态 A（未选文件） | `<div class="empty">请选择文件</div>`，`app.kpListSelectFile` | `app.js:2106`-`2109`、`i18n/zh-CN.js:491` |
| 空态 B（无 KP 且无提议） | `app.kpListNoKp`「无知识点 · 右键条目或点「配置」」 | `app.js:2120`-`2123`、`i18n/zh-CN.js:492` |
| 空态 C（**仅有待确认**） | `app.kpListOnlyProposals`（`{n}`＝**仅标题提议数**，因为这里 `proposals` 只取 `doc.heading_proposals`）+ 换行 + `app.kpListOnlyProposalsHint` | `app.js:2112`、`2124`-`2132`、`i18n/zh-CN.js:493`-`494` |
| 样式 | `.-kp-item:hover`/`.active`；`.-kp-item.warn .-kp-name`（warning 色）、`.-kp-item.error .-kp-name`（error 色） | `app.css:3051`-`3072` |

事件绑定（仅正式 KP 条目）：`click` → `onKpClick`；`mouseenter` → `highlightKpHover` + `highlightGraphFromKp`；`mouseleave` → `clearKpHoverHighlight` + `clearGraphKpHover`；`contextmenu` → `MemoriaKpContextMenu.show`（**菜单只有一项「配置」**，`kp-context-menu.js:37`）。

### 2.2 列表行号随编辑实时更新（两条并行路径 + 一条兜底）

| 路径 | 触发 | 做什么 | 锚点 |
|---|---|---|---|
| 本地结构平移 | 源码区 Enter / 行首退格 / 行末 Delete / 块替换 | `adjustKpRangesAfterInsert` / `adjustKpRangesAfterRemove` / `adjustKpRangesAfterSpanReplace` 直接改 `range_resolved` 与 `range.*.line_hint`，随后 `refreshKpRangeUi()` **就地改写** `.-kp-meta span` 文本（不整表重渲） | `app.js:7100`-`7124`、`7181`-`7202`、`7307`、`7364`、`7405`、`7708`-`7711` |
| 后端权威解析 | 任意 `markDirty()`（停手 420ms 合并） | `collectEditorBody()` → `resolve_kp_ranges(path, body)` → **只回写已知 id** 的 KP → `renderKpList` → 若正在 hover 则重跑 `highlightKpHover` | `app.js:160`、`168`-`192` |
| 保存后兜底 | `syncToDisk()` 成功 | 经调度内核入队 `kp_panel` 作业（优先级 P2、`dropStale`），用 `load_document` 权威结果重渲列表 | `app.js:139`-`141`、`232`-`249` |

即：**编辑期不调用 `highlightRange`**（无滚动、无闪烁），行号靠上述就近更新。

### 2.3 hover 高亮

| 项 | 现状 | 锚点 |
|---|---|---|
| 源码行 | 给 `start_line`…`end_line` 每个 `#line-n` 加 `in-range kp-hover`（先清掉上一组） | `app.js:11002`-`11008` |
| 预览浮层 | 仅当 `viewMode !== "source"` 且 `state.kpHighlightClearTimer == null`（无跳转清除计时器）时，`highlightPreviewRange(..., {scroll:false})` | `app.js:11009`-`11011` |
| 滚动 | **不滚动** | 同上（`scroll:false`） |
| 图谱联动 | 列表 hover 同步调用 `highlightGraphFromKp`（远端 hover，图谱节点加亮） | `app.js:2161`、`6451`-`6465` |
| 抑制条件 | `shouldSuppressHoverHighlight(e)`＝`e.buttons` 非 0（按住鼠标拖拽时不触发） | `app.js:8`-`10`、`2159`、`2164` |
| 清除 | `mouseleave` → 清 `in-range kp-hover`；只有闪烁与清除计时器**都为空**时才清预览浮层 | `app.js:2163`-`2167`、`10983`-`10991` |
| CSS | 源码行 `.-line.in-range .-line-content{background:rgba(0,122,204,.08)}` | `app.css:3634`-`3636` |

### 2.4 KP 弹窗 · 打开方式与框架

| 入口 | 行为 | 锚点 |
|---|---|---|
| 列表条目（范围未解析） | `onKpClick` 中 `rr.ok` 为假 → `openKpModal(kpId, {tab:"range"})` | `app.js:10937`-`10943` |
| 列表条目右键「配置」 | `MemoriaKpActions.configure` → `activeKpId` + `openKpModal(kpId)`（默认 `range` 页） | `app.js:12248`-`12254`、`4521`-`4540` |
| 侧栏「新建」/ `#btn-kp-new` | `openKpModalForCreate()`（`mode:"create"`） | `app.js:12239`-`12245`、`4542`-`4560` |
| 配置弹窗「新建知识点」/ 待确认「配置并确认」 | `openKpModalForCreate({returnTo:"config"})` / `openKpModalFromProposal`（先 `closeConfigModal`） | `app.js:2890`-`2893`、`4562`-`4575` |
| 选区右键「设为知识点…」 | `openAssistFromSelection` → **同 `#kp-modal`**（不是 `#assist-modal`），id 用 `slugify(首行文本)` | `app.js:11214`-`11225`、`9539`、`9582` |

框架行为：标题按模式取 `cfg.kpModal.createTitlePlain/createTitleNamed/editTitle`（`app.js:3372`-`3376`）；切页签前先 `syncKpPanelFromForm()` 收表单（`app.js:4512`-`4518`）；`syncKpModalLayout` 只在 `range` 页给 body 加 `-modal-body-kp-range`、在 `edges` 页加 `-modal-body-kp-edges`（`app.js:3266`-`3270`）；`syncKpModalFooter`：`edges` 页**隐藏「确定」**，`create` 模式**隐藏「删除知识点」**（`app.js:3272`-`3285`）。窗口尺寸由 `setupKpModalResize` 写入 `localStorage["-kp-modal-size"]`（200ms 合并，`app.js:11601`-`11626`）。

### 2.5 KP 弹窗 · 范围页（`range`）

`-kp-range-panel`（`app.css:824`-`856`）。结构：错误条 → 起止行号输入 → 候选单选 → 预览区 → 说明。

| 元素 | 现状 | 锚点 |
|---|---|---|
| 错误条 | `a.error` 存在时渲染 `.-config-range-warn` + `errorLabel(error)` | `app.js:3194`-`3196` |
| 起止输入 | `input[type=number][data-range-start]` / `[data-range-end]`，`min=1`、`max=正文总行数` | `app.js:3198`-`3202` |
| 滚轮微调 | `wheel` 上 `preventDefault` 后行号 ±1 并即时重渲预览（提示文案 `cfg.range.wheelNote`） | `app.js:3244`-`3256`、`i18n/zh-CN.js:162` |
| `focus` 切换锚点 | 决定预览区对齐起点还是终点（`state.assistScrollFocus`） | `app.js:3238`-`3243`、`11283`-`11285` |
| 候选列表 | 仅当 `start_candidates` / `end_candidates` 长度 >1 时出现；`radio[name=range-{start\|end}-kp]`，选中即写回对应输入 | `app.js:3203`-`3210`、`3216`-`3229`、`11628`-`11641` |
| 预览区 | `[data-range-preview].-assist-preview-wrap`，顶部「范围预览 + 源码/Markdown」小切换（`cfg.assist.viewSource/viewMarkdown`） | `app.js:3211`、`11262`-`11281` |
| 预览失效态 | 起止非法（`start > end` 或总行数为 0）→ `.-assist-preview-error`，文案 **`cfg.assist.rangeError`＝「行号无效：终点不能早于起点」**（键不在 `cfg.kpSave.*` 下） | `app.js:11538`-`11546`、`i18n/zh-CN.js:391` |
| 预览窗口 | 上下各留 3 行上下文，窗口至少 120 行（`ASSIST_CONTEXT_LINES=3`、`ASSIST_PREVIEW_TAIL_LINES=120`） | `app.js:11236`-`11247` |
| 说明 | `cfg.range.updateNote`「调整行号即更新高亮；预览区可切换源码 / Markdown」 | `app.js:3212`、`i18n/zh-CN.js:166` |

### 2.6 KP 弹窗 · 标识页（`identity`）

`#kp-field-id`（label 为**字面量 `id`**，非 i18n 键）+ `#kp-field-name`（`cfg.kpIdent.nameLabel`）+ 模式提示 `cfg.kpIdent.createHint/editHint`（`app.js:3407`-`3412`）。编辑模式下额外插入 `#kp-merge-suggest`，由 `loadKpMergeSuggestions` 调 `suggest_kp_merge` 填充近似 KP 命中项，点击即 `closeKpModal()` + `openFile(file,{kpId})`（`app.js:3445`-`3446`、`4474`-`4508`）。进入范围页/标签页/边页前都会 `clearKpRangeAssist()` 释放范围辅助状态（`app.js:3404`、`3414`、`3417`）。

### 2.7 KP 弹窗 · 标签页（`tags`）

一页内并列三块编辑器，都是「已选区 / 候选区 + 逐 chip 移动」：

| 编辑器 | 已选区 id | 候选区 id | 候选来源 | 锚点 |
|---|---|---|---|---|
| tag | `#kp-tags-selected` | `#kp-tags-candidates` | sidecar `tag_candidates` + 「系统建议」→ `suggest_tags` + 手输「加入候选」 | `app.js:4117`-`4148`、`4448`-`4472`、`4221`-`4270` |
| 别名 | `#kp-alias-selected` | `#kp-alias-candidates` | sidecar `alias_candidates` + 「同步检索 aux」+ 手输「加入候选」（**本编辑器没有「系统建议」按钮**） | `app.js:4026`-`4054`、`4298`-`4341`、`4379`-`4428` |
| 描述候选 | —（`#kp-desc-candidates`） | 同左 | 「同步检索 aux」+ 「建议描述」→ `suggest_description` | `app.js:4056`-`4067`、`4430`-`4446` |
| 描述正文 | — | `#kp-desc-input`（`textarea`，占位 `cfg.kpIdent.descPlaceholder`） | 点描述候选 chip 填入 | `app.js:3427`-`3429`、`4364`-`4372` |

chip 视觉与语义（`renderKpTagChip`/`renderKpAliasChip`）：`selected` 实线主题色描边；候选按 `source` 分 `cand-user`（虚线、主题色描边）/ `cand-system`（虚线、灰）；系统 tag chip 右上角显示 `score`。**点 chip 主体**＝切换已选/候选（`toggleKpTagZone` → `promote/demote`），**点 × 号**＝彻底移除（`dismissKpTag/dismissKpAlias`）（`app.js:4097`-`4115`、`4002`-`4015`、`4174`-`4219`、`4272`-`4296`、`app.js:4230`-`4251`；`app.css:1430`-`1468`）。描述候选进候选区的条件是文本 ≠ 当前描述（`app.js:3997`）。

### 2.8 KP 弹窗 · 边页（`edges`）

`deriveKpEdgesForCurrentFile(kp)` **在前端现算**，合并四类来源（`app.js:3466`-`3619`）：

1. `contain`：由同文件 KP 范围**嵌套**推导（外→内，`relevance:0.9`），外层或内层有一方是当前 KP 才收录；
2. `link`：由 `sidecar.links[]` 的实例行号定位所属最小 KP 作为源，逐目标取 `target_edges[tid]` 的边型/权重；
3. `sidecar_edge`：`sidecar.edges[]` 中 `no_build` 为假的条目（`origin:"sidecar_edge"`）；
4. 被抑制的 `contain`（`edges[].no_build` 为真，作为展示项，带 `no_build:true`）。

渲染：出边区（`cfg.edge.outTitle`，含操作按钮）与入边区（`cfg.edge.inTitle`，**只读、仅本文件内**），末尾「新建边」表单（`app.js:3640`-`3718`）。

| 操作 | 可见条件 | 落盘调用 | 锚点 |
|---|---|---|---|
| 抑制 contain | `type==="contain" && !no_build` | `set_contain_no_build(path, parent, child, true)` | `app.js:3665`-`3666`、`3733`-`3747` |
| 恢复 contain | `type==="contain" && no_build` | `set_contain_no_build(..., false)` | `app.js:3663`-`3664`、`3750`-`3764` |
| 删除边 | `origin==="sidecar_edge"`（`window.confirm` 后） | `delete_edge(path, src, tgt, type)` | `app.js:3668`-`3670`、`3767`-`3783` |
| 配置链接 | `origin==="link"` 且有 `anchor_text` | 转 `openLinkEditor({mode:"edit", returnTo:"kp"})` | `app.js:3671`-`3673`、`3786`-`3799` |
| 新建边 | 始终 | `create_edge(path, kp.id, targetId, edgeType, relevance)` | `app.js:3802`-`3866` |

「新建边」表单细节：目标输入框用**自绘 datalist**（`.-edge-target-datalist`，最多 10 项，取自本文件 KP id ∪ `state.linkTargetList`，`blur` 后 200ms 移除）；边型下拉**只有 `reference` / `extend`**（没有 `contain`）；权重滑条 `min=0 max=1 step=0.05`，初值 **0.70**，旁显两位小数（`app.js:3709`-`3711`、`3805`-`3809`、`3811`-`3845`；`app.css:956`-`975`）。每次操作成功后都 `reloadDocAndRefreshEdges(kp.id)`：重新 `load_document` 后整页重渲（`app.js:3720`-`3726`）。

### 2.9 保存 / 删除 / 重命名

| 动作 | 分支 | 校验与调用 | 锚点 |
|---|---|---|---|
| 点「确定」 | `saveKpModal()`：先 `syncKpPanelFromForm()`；`create` → 只走 `saveKpRange()`；编辑按当前页分流；**`edges` 页直接关窗**（该页操作即时落盘） | — | `app.js:11749`-`11768` |
| 保存范围 | `saveKpRange()`：`start<=end` → `end<=total` → 起止行**非空行**（`lineHasRangeSnippet`）→ `create` 额外要求 id/name 且 `check_kp_id` 可用 → `confirm_kp_range` | 失败时对 `host==="kp"` 重建范围辅助 | `app.js:11825`-`11920` |
| 保存标识 | `saveKpIdentity()`：名称必填；**id 变化**先 `window.confirm(cfg.kpSave.renameConfirm)` → `rename_kp_id` → 刷新文件树/链接目标/图谱 → `update_kp` | — | `app.js:11670`-`11715` |
| 保存标签 | `saveKpTags()`：`update_kp(path, kpId, null, tags, description, tagCandidates, aliasCandidates, aliases, descriptionCandidates)` | 全部为选后草稿（未点确定不落盘） | `app.js:11717`-`11747` |
| 保存后刷新 | `reloadDocAfterKpChange`：重渲编辑器/列表/文件树 → `setViewMode` → `renderPreview` → `onKpClick(kpId,{skipRangeModal:true})` | — | `app.js:11654`-`11668` |
| 删除 | `deleteKp()`：`window.confirm(cfg.kpSave.deleteConfirm)` → `delete_kp`（**只删配置，不改正文**）；`closeModal` 用于弹窗内删除 | — | `app.js:11770`-`11806` |
| 关闭 | `closeKpModal()`：`returnTo==="config"` 时重开配置弹窗（来自提议 → `pending` 页，否则回 `state.configTab`） | — | `app.js:4761`-`4776` |

### 2.10 配置弹窗（`#config-modal`）三 Tab

打开入口是**侧栏 KP 工具栏的「配置」按钮**（`#btn-config`，`app.js:12238`），不是顶栏。`configTabCounts(doc)` 出三个计数（`app.js:2227`-`2249`）：

| Tab | 计数 | 内容 | 锚点 |
|---|---|---|---|
| `kp`（知识点） | `knowledge_points.length` | 每项：名称 + 范围（`kpRangeMeta`，异常走 `-config-range-warn`）+ tag；操作「配置」（`openKpModal`，`returnTo:"config"`）与「删除」（`deleteKp(...,{refreshConfig:true})`） | `app.js:2267`-`2298`、`2935`-`2946` |
| `links`（链接） | `sidecar.links` 中**对象**条目数 | 审计横幅 + 每项「匹配 / 编辑 / 删除」；点击行主体 = 打开匹配面板 | `app.js:2717`-`2776`、`2899`-`2933` |
| `pending`（待确认） | 三类提议过滤掉「已被正式 KP 覆盖」后的总数 | 见 §2.11 | `app.js:2782`-`2866` |

弹窗顶部另有摘要与校验提示：`cfg.config.summary`、`validation.errors/warnings`、`links` 页额外 `cfg.config.linkWarn`（`app.js:3016`-`3036`）。打开时先 `refreshKbPendingSummary()` 再渲染（`app.js:3054`-`3064`）。

### 2.11 待确认（pending）流

**候选来源**（后端产出，前端只读三个数组）：

| 组 | 数组 | 标签键 | 操作按钮 |
|---|---|---|---|
| 标题提议 | `doc.heading_proposals` | `cfg.pending.tagHeading` | 直接确认 / 配置并确认 / 忽略 |
| 段落提议（mention） | `doc.mention_proposals` | `cfg.pending.tagMention` | 直接确认 / 配置并确认 / 忽略 |
| 定义句提议 | `doc.definition_proposals` | `cfg.pending.tagDefinition` | 直接确认 / 配置并确认（**无「忽略」按钮**） |

锚点：`app.js:2796`-`2863`。三组统一过滤条件 `isKpCoveredByConfirmed`（按 name 或 concept_id 与已确认 KP 比对，命中即不算待确认，`app.js:2185`-`2193`）。工具栏：`全部确认`（`confirmAllPending`）、`刷新待确认`（`syncPendingFromConfig` → `sync_pending`）、可选「全库 {n} 项」（`state.kbPending.total`，`app.js:2786`-`2790`）。

| 动作 | 行为 | 锚点 |
|---|---|---|
| 直接确认 | `confirmKpFromProposal`：用提议默认 id/name/范围，校验 `end<=total`、id 非空、name 非空、`check_kp_id` → `confirm_kp_range` → 重渲 → `markRangeQuiet(start,end)` → 异步 `loadGraphData` + `applyGraphGroupLayout({relayout:true})` → 若配置弹窗仍开则重开 `pending` 页 | `app.js:4619`-`4684` |
| 配置并确认 | `openKpModalFromProposal`：先关配置弹窗，进 `#kp-modal` 的 `range` 页（`returnTo:"config"`） | `app.js:4562`-`4575` |
| 全部确认 | `confirmAllPending`：`window.confirm` 后**按顺序逐个**确认，跳过的项汇总；有跳过则 `setStatusError` + `window.alert` 列出；结束后重渲、刷图谱、重开 `pending` 页 | `app.js:4687`-`4759` |
| 忽略 | `dismissPendingItem(pending_id)` → `dismiss_pending` → 重载文档 + 列表 + 全库摘要 → 重渲配置弹窗 | `app.js:3066`-`3087` |

**「关窗先于图谱刷新」**（如实记录该优化）：`saveKpRange` 在 `host==="kp"`（即从 KP 弹窗保存/创建）时**不 await** 图谱刷新，而是 `loadGraphData().then(() => applyGraphGroupLayout({relayout:true}))` 后立即 `return true`，让 `saveKpModal → closeKpModal` 先把窗口关掉，避免窗口关闭被图谱 relayout 拖住；其它 host 才 await（`app.js:11946`-`11960`）。

### 2.12 范围的两种语义（跳转 vs 静默）

| | `highlightRange`（跳转语义） | `markRangeQuiet`（静默标记） |
|---|---|---|
| 源码行类 | `in-range` + `kp-highlight-flash`（并清 `fade-out`） | 仅 `in-range` |
| 滚动 | `viewMode!=="preview"` 时对首个源码行 `scrollIntoView({block:"start",behavior:"smooth"})` | 不滚动 |
| 预览浮层 | `highlightPreviewRange(...,{scroll:true,flash:true})` | `{scroll:false,flash:false}` |
| 自动消失 | 800ms 加 `fade-out`（1.5s 过渡），2500ms 整体清除 | 不自动消失 |
| 触发方 | KP 列表点击（`app.js:10939`）、`openFile({kpId})` 跳转（`app.js:1488`，含图谱节点点击）、搜索结果/审计定位、KP 保存后回跳（`reloadDocAfterKpChange` → `onKpClick(...,{skipRangeModal:true})`，`app.js:11665`） | KP 保存/创建之后（`app.js:11932`）、直接确认待确认提议（`app.js:4667`） |
| 锚点 | `app.js:11050`-`11083` | `app.js:11039`-`11048` |

第三态为错误高亮 `highlightRangeWithError`（`kp-error-flash`，不自动淡出，另给列表项加 `.error-highlight`，用于检查面板「打开」跳转，`app.js:11086`-`11118`、`app.css:3670`-`3700`）。**编辑期实时同步不在此列**——它走 §2.2 的 M6b 即时映射 + `resolve_kp_ranges` 回写。

## 3. 交互流程

**创建（弹窗路径）**：`#btn-kp-new` → `openKpModalForCreate` → 范围页调行号（滚轮/候选/预览）→ 切「标识」页填 id/name → 「确定」→ `saveKpRange`（校验 + `check_kp_id` + `confirm_kp_range`）→ 重渲全 UI → `markRangeQuiet` → 异步图谱刷新 → `closeKpModal`（`app.js:11749`-`11768`、`11825`-`11953`）。

**改范围**：列表项点击（`rr.ok` 为真时只做跳转高亮）；要改则右键「配置」或点列表项（范围未解析）→ 范围页改行号 → 「确定」→ `confirm_kp_range` → `markRangeQuiet`。

**重命名 id**：标识页改 `#kp-field-id` → 「确定」→ `window.confirm` → `rename_kp_id`（全库联动）→ `update_kp`（`app.js:11680`-`11714`）。

**待确认批量**：配置弹窗 `pending` 页 → 「全部确认」→ 逐项 `confirm_kp_range` → 汇总结果 → 刷新图谱 → 回到 `pending` 页。

## 4. i18n key 前缀（代表键）

| 前缀 | 代表键 | 用途 |
|---|---|---|
| `side.kp.*` | `side.kp.label`、`side.kp.config`、`side.kp.configTitle`、`side.kp.newTitle` | 侧栏工具栏与右键菜单 |
| `app.kpList*` | `app.kpListSelectFile`、`app.kpListNoKp`、`app.kpListOnlyProposals`、`app.kpListOnlyProposalsHint` | 列表三种空态 |
| `cfg.panel.tabs.*` | `cfg.panel.tabs.range/identity/tags/edges` | KP 弹窗页签 |
| `cfg.kpModal.*` / `cfg.kpIdent.*` | `cfg.kpModal.editTitle`、`cfg.kpIdent.nameLabel`、`cfg.kpIdent.syncAux`、`cfg.kpIdent.suggestDesc` | 弹窗标题与标识/描述页 |
| `cfg.range.*` / `cfg.assist.*` | `cfg.range.start/end/wheelNote/startCand/endCand`、`cfg.assist.rangeError`、`cfg.assist.viewSource/viewMarkdown` | 范围页与预览 |
| `cfg.kpTag.*` / `cfg.chip.*` | `cfg.kpTag.zoneTagsSel`、`cfg.kpTag.sysSuggestBtn`、`cfg.kpTag.addCandBtn`、`cfg.chip.moveToCand`、`cfg.chip.remove` | 标签/别名候选编辑器 |
| `cfg.edge.*` | `cfg.edge.typeContain/typeReference/typeExtend`、`cfg.edge.outTitle/inTitle`、`cfg.edge.suppressBtn/restoreBtn`、`cfg.edge.createTitle/relevanceLabel` | 边页 |
| `cfg.kpSave.*` / `cfg.confirm.*` / `cfg.kpErr.*` | `cfg.kpSave.renameConfirm`、`cfg.kpSave.deleteConfirm`、`cfg.confirm.doneDetail`、`cfg.kpErr.startSnippet` | 保存/删除/确认与范围错误标签 |
| `cfg.tab.*` / `cfg.kpTab.*` / `cfg.pending.*` / `dlg.kpTitle` / `dlg.kpDelete` | `cfg.tab.pending`、`cfg.pending.confirmAll`、`cfg.pending.dismiss` | 配置弹窗三 Tab 与待确认 |

键值全文见 [i18n-inventory.md](../i18n-inventory.md)（`i18n/zh-CN.js:17`-`418`、`431`-`435`、`561`-`573`）。

## 5. 边界与已知坑

1. **`#assist-modal` 是死弹窗**：`index.html:253`-`266` 定义了「定位辅助」窗，但全库无任何 JS 引用（无绑定、无打开路径）；`getAssistHostEl()` 只在 `state.assist.host === "kp"` 时返回 `#kp-body`，否则返回 `#assist-body`，而当前代码只把 `host` 设为 `"kp"`（`app.js:3134`-`3136`、`3383`-`3394`）。所以「设为知识点」实际进的是 `#kp-modal`。
2. **「配置」入口在侧栏**，不是顶栏：`#btn-config` 位于 `.-kp-toolbar-actions`（`index.html:128`）。
3. **边页无法手工建 `contain`**：`#kp-edge-type` 下拉只有 `reference`/`extend`（`app.js:3710`）；`contain` 只由范围嵌套推导，且后端 `normalize_link_edge_type` 同样只接受 `reference`/`extend`（`src/memoria/graph/edge_types.py:61`-`66`）。
4. **入边只显示本文件内**：`cfg.edge.inScopeNote` 明确「入边需全库扫描，当前仅显示本文件内入边」（`i18n/zh-CN.js:224`）。
5. **边页的 `data-edge-*` 属性**（type/source/target/origin/anchor）只写不读，当前无消费方（`app.js:3654`、`3689`）。
6. **`edges` 页没有「确定」**：`syncKpModalFooter` 对该页 `add("hidden")`，页内操作即时落盘；「删除」按钮在 `create` 模式也被隐藏（`app.js:3272`-`3285`）。
7. **定义句提议没有「忽略」**：只有标题/段落两条分支渲染 `data-dismiss-pending`（`app.js:2812`、`2835` vs `2856`-`2857`）。
8. **`#kp-count` 不含待确认**：只写正式 KP 数（`app.js:2118`）；待确认量只在配置弹窗 Tab 计数与「全库 {n} 项」上。
9. **hover 高亮与拖动互斥**：按住鼠标拖动期间不触发/不清除悬停高亮（`app.js:8`-`10`）。
10. **删除只动配置**：`delete_kp` 不改正文；文案 `cfg.kpSave.deleteConfirm` 明说「正文不会被改写」；`cfg.kpTab.deleteTitle` 也写作「从配置中删除该知识点」（`i18n/zh-CN.js:406`、`29`）。
11. **id 输入框的 label 是硬编码 `id`**（`app.js:3408`），未走 i18n。
12. **范围错误高亮不自动消失**：`kp-error-flash` 只能由后续 `dismissKpRangeHighlight()` 清除（`app.js:11086`-`11105`）。
13. **切页签会丢「新建边」表单输入**：切 Tab 走 `syncKpPanelFromForm()`（只收 id/name/tags/描述与范围行号）后整块重渲（`app.js:4512`-`4518`、`3345`-`3457`），因此边页已输入的目标 id 与已拖动的权重滑条会回到空值 / 0.70。
14. **边权重输入静默夹取**：`normalizeLinkRelevance` 把非数值或越界值静默夹到 0–1 或回落到类型默认值（`app.js:4846`-`4852`、`4918`），界面不给任何提示。

## 6. 代码锚点表

| 主题 | 文件:行 |
|---|---|
| 侧栏 KP 区块 DOM（工具栏 / 列表 / 拖拽条） | `index.html:105`-`134` |
| KP 弹窗 DOM / 配置弹窗 DOM | `index.html:222`-`237`、`239`-`251` |
| 侧栏 KP 区块与列表样式 | `app.css:220`-`248`、`708`-`731`、`3051`-`3078` |
| KP 弹窗尺寸/分页布局 | `app.css:752`-`773`、`976`-`978`、`799`-`856` |
| 边页样式 / 候选 datalist | `app.css:858`-`975` |
| 标签 chip 样式 | `app.css:1366`-`1530` |
| 列表渲染与事件 | `app.js:2103`-`2176` |
| 计数与待确认过滤 | `app.js:2185`-`2193`、`2227`-`2249` |
| 配置弹窗渲染与三 Tab | `app.js:2251`-`2298`、`2717`-`2776`、`2782`-`2866`、`3007`-`3064` |
| 配置弹窗事件绑定 | `app.js:2868`-`3005` |
| 待确认：直接确认 / 全部确认 / 忽略 / 刷新 | `app.js:4619`-`4684`、`4687`-`4759`、`3066`-`3087`、`3089`-`3110` |
| KP 弹窗框架（标题/分页/页脚/body） | `app.js:3117`-`3132`、`3266`-`3285`、`3345`-`3457` |
| 范围页构建与绑定 | `app.js:3192`-`3264`、`11249`-`11260`、`11533`-`11546` |
| 范围预览工具栏与窗口 | `app.js:11236`-`11288` |
| 标签/别名/描述候选编辑器 | `app.js:4002`-`4373`、`4448`-`4472`、`4474`-`4508` |
| 边页推导与渲染 | `app.js:3466`-`3619`、`3640`-`3718` |
| 边页事件（抑制/恢复/删除/新建/配置链接） | `app.js:3728`-`3867` |
| 弹窗打开/关闭/尺寸持久化 | `app.js:4521`-`4575`、`4761`-`4776`、`11587`-`11626` |
| 保存/删除/重命名 | `app.js:11654`-`11768`、`11770`-`11806`、`11825`-`11960` |
| 图谱刷新与关窗解耦 | `app.js:11946`-`11960` |
| KP 列表点击 / 右键菜单动作 | `app.js:10923`-`10944`、`12246`-`12255`、`kp-context-menu.js:27`-`61` |
| 范围语义（静默 / 跳转 / 错误） | `app.js:11039`-`11118` |
| hover 高亮与抑制 | `app.js:8`-`10`、`10983`-`11012`、`2156`-`2167` |
| 预览浮层条实现 | `app.js:11136`-`11208`；`app.css:3574`-`3591`、`3634`-`3700` |
| M6b 实时行号映射与列表就地更新 | `app.js:160`-`192`、`7067`-`7202`、`7708`-`7711` |
| 保存后静默刷新（调度作业） | `app.js:139`-`141`、`232`-`249` |
| 选区右键「设为知识点」 | `app.js:9533`-`9540`、`9575`-`9582`、`11214`-`11225` |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未运行时验证）：编辑期同时存在「本地结构平移」与「420ms 后 `resolve_kp_ranges` 权威回写」两条路径（`app.js:7100`-`7124` vs `168`-`192`）；后者只回写已知 id，若用户在此期间增删了 KP 或改动超出后端判定阈值，列表行号是否会短暂跳变未做运行时观察。
- ⚠️ 待确认（未取证）：别名编辑器缺少与 tag 编辑器对应的「系统建议」入口（`app.js:4045`-`4050` vs `4138`-`4144`）；别名候选除 sidecar `alias_candidates` 与「同步检索 aux」外是否还有其它 UI 添加路径，未逐处取证。
- ⚠️ 待确认（未取证）：`#kp-merge-suggest` 的命中项点击后走 `closeKpModal()` + `openFile`，未见合并本身（M4 只给建议，`app.js:4474`-`4508`、`i18n/zh-CN.js:252`）；合并动作是否在别处实现未取证。
- ⚠️ 待确认（未运行时验证）：`setupKpModalResize` 只在 `localStorage["-kp-modal-size"]` 存尺寸，未进 `ui-settings.json`（`app.js:11601`-`11626`），因此「设置 → 恢复默认」与 `persistToDisk` 都不覆盖它。
- ⚠️ 待确认（未取证）：`.-modal-body-kp-edges` 类在 CSS 中没有对应选择器（只作 JS 开关标记，`app.js:3269`）。
- ⚠️ 待确认（未取证）：配置弹窗 `links` 页的匹配勾选状态（`state.configLinkMatch`，`app.js:2709`-`2715`）与链接编辑器的匹配勾选（`state.linkPicker.match`，`app.js:2657`-`2705`）是两套独立结构，二者在「选中集合 → 保存」上的行为差异未逐处比对。
