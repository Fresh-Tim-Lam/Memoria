# 06 · 链接与图谱

> **用途**：记录「正文选区怎么变成链接、链接编辑器每块控件做什么、断链/虚链接长什么样、边类型的语义与默认权重、2D/3D 图谱怎么渲染与交互、分组页签与样式如何持久化、顶栏「构建」做什么」到可据以工作的粒度；供集成方与后续 Agent 对照代码改前端。
> **目标读者**：在 Memoria 之上做集成/移植的 Agent 与人；给 Memoria 前端写改动的人。
> **关联文档**：[README.md](./README.md)（维护约定）、[preview-formats.md](../preview-formats.md)（**渲染语法权威**，`[[…]]` 写法以它为准）、[04-preview-and-rendering.md](./04-preview-and-rendering.md)（wiki 链接渲染与后处理）、[05-knowledge-points.md](./05-knowledge-points.md)（KP 与边页）、[architecture.md](../architecture.md)、[i18n-inventory.md](../i18n-inventory.md)。
> **状态**：生效中，2026-09-15。

---

## 1. 区域概览

```
#-sidebar                                              （index.html:109）
├─ #sidebar-resizer                                   （index.html:110）
├─ .-sidebar-tabs-wrap                                （index.html:111；`padding: 0 8px`）
│  └─ .-config-tabs.-sidebar-nav-tabs                 （index.html:112-117）
│     └─ [data-sidebar-tab=files|graph2d|graph3d|**history**] + #sidebar-tab-count-*  （index.html:113-115；**history 按钮与 graph3d 压在同一行**，2026-09-19 加，行号零漂移）
├─ #sidebar-graph-group-bar.-graph-group-bar           （index.html:118-120，仅图谱页且有节点时显示）
│  └─ #sidebar-graph-group-tabs.-graph-group-tabs      （横向可滚动页签）
└─ #sidebar-body-split                                 （index.html:121）
   ├─ #sidebar-nav-panel.-panel.-sidebar-nav-panel
   │  ├─ #sidebar-view-files  > #file-tree
   │  ├─ #sidebar-view-graph2d > #graph-2d-root.-graph-root
   │  │                        + #graph-2d-hint.-graph-hint--overlay     （index.html:128）
   │  ├─ #sidebar-view-graph3d > #graph-3d-root.-graph-root
   │  │                        + #graph-3d-hint.-graph-hint--overlay    （index.html:132）
   │  └─ #sidebar-view-history  （**空容器**，2026-09-19 加；紧贴上行闭合 div 之后 ⇒ 行号零漂移；
   │                              内容（`.-hist-head` / `#hist-new` / `#hist-filter` / `#hist-list`）
   │                              由 agent-panel.js 末尾块在加载时建，见 01 篇 §6 与 §7）
   └─ #sidebar-kp-resizer.-graph-panel-resizer          （上下占比拖拽）
      └─ #sidebar-kp-block                              （知识点，见 05 篇）

#link-modal                                            （index.html:303-320）
└─ #link-title / #link-body /（页脚） #link-hint │ #link-config-view │
   #link-cancel │ #link-save │ #link-save-jump │ #link-confirm
```

`.-graph-root` 内由各视图自建画布/渲染器：2D 插入 `<canvas class="-graph-canvas">`（`graph-view-2d.js:137`-`141`；`app.css:368`-`375`），3D 插入 `WebGLRenderer.domElement`（`graph-view-3d.js:246`-`256`）。

## 2. 逐处细节

### 2.1 创建链接

| 入口 | 传递参数 | 锚点 |
|---|---|---|
| 预览/源码选区右键 →「创建链接…」 | `openLinkEditorFromSelection(text,{preselectLines})` → `openLinkEditor({mode:"create", anchorText:t, displayText:t, createSelection:t})` | `link-context-menu.js:211`-`213`；`app.js:9537`-`9539`、`9580`-`9582`、`5591`-`5605` |
| 配置弹窗 `links` 页「新建链接」 | 先 `closeConfigModal()`，再 `openLinkEditor({mode:"create", anchorText:"", displayText:"", returnTo:"config"})` | `app.js:2879`-`2888` |

窗口标题按模式取 `cfg.linkSave.titleCreate` / `titleCreateNamed`（`app.js:5560`-`5568`）；正文由 `renderLinkTargetList` 一次渲染（`app.js:5146`-`5308`），结构自上而下：

| 区块 | 内容 | 交互 | 锚点 |
|---|---|---|---|
| 匹配文本 | `#link-edit-anchor` 输入框 + 建议下拉 `#link-anchor-suggest` | 输入即防抖重扫匹配（§2.2） | `app.js:5131`-`5144`、`2600`-`2627` |
| 搜索选项 | `[data-search-opt]`：`fuzzy_whitespace`（忽略空格）、`fuzzy_suggest`（模糊推荐）、`case_insensitive`（**`disabled`**） | 勾选写入本次匹配请求 | `app.js:2338`-`2370`；`i18n/zh-CN.js:56`-`63` |
| 匹配面板 | `#link-editor-match-slot` / `#link-editor-match-panel` | 勾选正文挂接位置 | `app.js:2517`-`2563` |
| 图例 | `-link-pick-legend`：编辑模式＝已选/未选，跳转模式＝队首/已选入队/未选 | — | `app.js:5164`-`5175`；`app.css:2323`-`2350` |
| 目标列表 | 每个候选一行 `.-link-pick-item[data-pick-row]`：`.-pick-dot` 圆点 + 名称 + 文件；编辑模式另带 `×`（`data-remove-target`） | 点行或点圆点＝切换；点 `×`＝**从候选表删除**（同时修正 `selectedOrder`） | `app.js:5181`-`5204`、`5272`-`5294`；`app.css:2266`-`2306`、`2897`-`2914` |
| 添加目标 | `#link-add-target` + `#link-add-target-btn` + 建议下拉 `#link-add-target-suggest` | 见下 | `app.js:5207`-`5213`、`5411`-`5446` |
| 图谱边面板 | `#link-edge-editor-panel`：为**每个已选目标**单独设边型与权重 | 见 §2.4 | `app.js:4991`-`5019` |
| 智能匹配（M4） | `<details class="-suggest-block -link-tag-suggest">`，内含**禁用**的「选用」按钮占位 | **当前为纯占位**（详见 §5.3） | `app.js:5215`-`5226`；`i18n/zh-CN.js:331`-`333` |

**顺序语义（`selectedOrder`，元素为候选下标）**：编辑模式点选＝`push`，再点＝`splice` 移除（**顺序即后续 `targets` 顺序**）；跳转模式（`mode:"jump"`）点未选项＝追加，点**队首**＝取消，点其它已选项＝`unshift` 提升为队首（`app.js:5256`-`5270`）。多目标跳转时队首用于跳转，其余 `ensureOpenTab({pending:true})` 加入标签页（`app.js:5618`-`5630`）。

**手动输入 id / tag 搜索**：输入框 placeholder 明示 `id 或 tag:rl policy …`（`i18n/zh-CN.js:329`）。`refreshLinkTargetSuggest` 在输入 180ms 防抖后调 `search(q,"kb",8)`，无命中则回退到本地 `state.linkTargetList` 前缀过滤（上限 8 条）（`app.js:5310`-`5409`）。按 Enter 或点「添加」→ `addLinkEditorTarget()` → `resolve_link(tid)`；解析失败仍会以 `{unresolved:true}` 候选入列并默认选中（`app.js:5411`-`5446`）。`state.linkTargetList` 来自 `get_link_targets`（`app.js:5570`-`5575`）。

**确认**：编辑模式「保存」/「保存并跳转」；两者都先 `readLinkEditorFields()`，无选中目标或匹配文本为空即拒绝并给状态栏文案（`app.js:5632`-`5646`）。跳转模式只有「确认跳转」，未选时 `disabled`（`app.js:5236`-`5248`）。

### 2.2 编辑链接与链接右键菜单

预览区链接的 `contextmenu` 由 `bindLinkContextMenu` 交给 `MemoriaLinkContextMenu.showForLink`（`app.js:6234`-`6248`）。菜单项顺序固定（`link-context-menu.js:94`-`160`）：

| 项 | 行为 | 文案键 |
|---|---|---|
| 头部：显示文字（disabled） | — | — |
| 状态行（disabled） | `未绑定目标` / `多目标链接` / `已解析` + ` · <目标 id>` | `menu.linkUnbound/linkMulti/linkResolved` |
| 编辑链接… | `openLinkEditorFromElement` → `openLinkEditor({mode:"edit", anchorText:targetId, displayText, oldDisplay})` | `menu.linkEdit` |
| 复制目标键 | `navigator.clipboard.writeText(targetId)` | `menu.copyTargetKey` |
| 复制显示文字 | **仅当显示文字 ≠ 目标 id 时出现** | `menu.copyDisplayText` |
| 从跳转入口移除此处 | `detach_link_instance(path, targetId, line)`（仅解本处标记，保留配置） | `menu.linkDetach`（title=`menu.linkDetachHint`） |
| 移除 `[[]]` 并删除路由 | `remove_link(path, targetId, displayText, linkType)`（弹 `cfg.linkOps.unwrapConfirm`） | `menu.linkRemoveRoute` |

**改锚文本重匹配**：改 `#link-edit-anchor` → 350ms 防抖 `scheduleLinkEditorMatchRescan` → `loadLinkEditorMatch` → `scan_link_text_matches(path, anchor, {…searchOptions, route_anchor: 旧锚文本||当前})`；每处命中渲染为一行可勾选（默认按 `createSelectionLines` → 审计 `suggested_lines` → `instance_lines` 顺序预选）（`app.js:2629`-`2707`、`5049`-`5076`）。保存时用 `resolveSaveAnchorFromSelection(match, selectedLines, searchQuery)` 取 canonical 文本；`oldAnchor !== saveAnchor` 即视为改名（`app.js:5640`-`5655`）。

**虚链接（未定向）的多选定向**：点击多目标链接 → `resolve_links(ids)`；命中 1 个直接跳，多个则 `showLinkPicker(title, candidates)`（`mode:"jump"`，候选 1 个时预置 `selectedOrder=[0]`，否则为空需用户勾选）（`app.js:6140`-`6165`、`5607`-`5616`）。

**删除最后一个目标后的表现**：

1. 编辑器内：点 `×` 删掉候选行或取消勾选，若 `selectedOrder` 变空 → 「保存 / 保存并跳转」变 `disabled`，提示行写 `cfg.linkSave.hintNoTarget`「请添加至少一个跳转目标」；即使强点，`saveLinkEditor` 也直接 `setStatus(cfg.linkSave.fail, cfg.linkSave.needTarget)` 返回（`app.js:5035`-`5059`、`5636`-`5639`）。
2. 文档级：配置 `links` 页「删除」→ `delete_link_route`（删配置并解除正文全部 `[[锚文本]]` 包裹，保留可见文字）（`app.js:6065`-`6094`、`i18n/zh-CN.js:345`）；右键「移除 `[[]]` 并删除路由」→ `remove_link`（`app.js:6096`-`6128`）。路由消失后，正文里若仍残留 `[[…]]`，将由后处理降级为**虚链接**（§2.3）。

### 2.3 断链 / 虚链接

`postProcessWikilinks` 给每个 `.-wikilink` 补 `memoria-link` + `data-link-target/-type/-line` + `role=link`，再按三种状态择一（`app.js:6250`-`6286`）：

| 状态 | 判定 | 类与属性 | 样式 |
|---|---|---|---|
| 实跳转 | 锚文本在 `state.linkTargetSet` 内，**或** `link_overrides[锚文本]` 中至少一个目标可解析 | `-link-resolved` + `tabindex=0` + `title=preview.link.jump` | 主题色实线下划线，hover 底色 |
| 断链（虚链接） | 有 lookup 但不满足上述条件（含「路由指向不存在的目标」） | `-link-broken memoria-broken-link` + `tabindex=-1` + `title=cfg.linkClick.unboundTitle` | 灰、点状下划线、`opacity:.72` |
| 目标集未知 | `state.linkTargetSet` 不是 `Set` | `-link-pending` | 主题色点状下划线 |

锚点与样式：`app.js:6271`-`6285`；`app.css:1665`-`1721`。多目标链接另有 `-link-multi`（虚线，`app.css:1688`-`1698`）。

**点击行为**（`onMemoriaLinkClick`，`app.js:6130`-`6199`）：画笔模式下不跳转；`-link-broken` → **打开链接编辑器**（不是报错）；有 `data-link-targets` → `resolve_links` 后单选直跳 / 多选 `showLinkPicker`；否则 `link_overrides[target]` 只有 1 个目标就直接跳，再退 `resolve_link`：`ambiguous` → picker，`not_found` → 状态栏 `cfg.linkClick.notFound` + `cfg.linkClick.unbound`。

### 2.4 边类型与默认权重

语义边类型的**唯一权威**是 sidecar（`src/memoria/graph/edge_types.py:1`-`6`）：

| 类型 | 常量 | 默认权重 | 说明 | 锚点 |
|---|---|---|---|---|
| `contain` | `EDGE_CONTAIN` | **0.9** | 结构包含（由 KP 范围嵌套推导）；只能抑制/恢复 | `edge_types.py:10`、`26`-`30` |
| `reference` | `EDGE_REFERENCE` | **0.7** | 引用（`links[].edge_type` 的默认值） | 同上；`edge_types.py:61`-`66` |
| `extend` | `EDGE_EXTEND` | **0.6** | 扩展 | 同上 |

`links[].edge_type` **只接受 `reference` / `extend`**（`normalize_link_edge_type` 把其它值一律折回 `reference`）；每个跳转目标可用 `links[].target_edges[tid]` 单独覆盖边型与权重（`app.js:4863`-`4887`；`edge_types.py:93`-`135`）。前端默认值同口径：`defaultRelevanceForEdgeType`（extend 0.6 / reference 0.7）（`app.js:4842`-`4844`）。

**颜色与视觉**：边颜色按类型取自 `MemoriaGraphEdgeColors`：`contain #3fb950 / reference #58a6ff / extend #d29922`（`graph-engine.js:7`-`11`；3D 侧复用同一表，`graph-view-3d.js:13`-`17`）。线宽/透明度表达「相关 vs 无关」而非「强边实线 / 弱边虚线」：

| 视图 | 非聚焦 | 聚焦（hover / 外部焦点） | 锚点 |
|---|---|---|---|
| 2D | `alpha 0.45`、`lineWidth 1.2`（聚焦时其它边降到 `0.14`） | `alpha 0.95`、`lineWidth 2.2`，端点留白再 +2 | `graph-view-2d.js:546`-`572` |
| 3D | `opacity 0.5`（聚焦时其它降到 `0.12`） | `opacity 0.95`，`linewidth` 恒为 1（WebGL 不支持线宽） | `graph-view-3d.js:446`-`464`、`865`-`874` |

2D 边为**有向**（线段 + 三角箭头，箭头大小 `arrowSize` 默认 7，端点留出 `nodeRadius+3` 间距）（`graph-view-2d.js:27`-`73`）。

**抑制与恢复**（仅 `contain`）：写 sidecar `edges[]` 中 `no_build:true` 的条目；调用 `set_contain_no_build(path, 父, 子, true|false)`，成功后重载文档整页重渲（`app.js:3733`-`3764`、`3495`-`3504`）。

### 2.5 2D 图谱（`#graph-2d-root`）

| 项 | 现状 | 锚点 |
|---|---|---|
| 画布 | 视图自建 `<canvas class="-graph-canvas">`，`position:absolute; inset:0`；`devicePixelRatio` 上限 2 | `graph-view-2d.js:137`-`141`、`216`-`225`；`app.css:368`-`375` |
| 缩放 | `wheel` 围绕鼠标点缩放，基数 0.9/1.1，乘 `zoomSensitivity2d`；夹在 `zoomMin2d 0.05` ~ `zoomMax2d 8` | `graph-view-2d.js:402`-`423` |
| 平移 / 拖节点 | 空白处拖＝平移（`_markUserView`，此后不再自动 fit）；节点上拖（位移 >4px 才激活）＝拖节点 | `graph-view-2d.js:425`-`459`、`331`-`342` |
| 点击节点 | `pointerup` 且未位移 → `engine._emit("nodeClick")` | `graph-view-2d.js:471`-`496` |
| 节点半径 | `nodeRadius`（默认 6）+ hover/源 +3、目标 +2；galaxy 下再 ×`(1+ratio*0.5)` | `graph-view-2d.js:594`-`595` |
| 节点颜色 | hover/源 `#f0f6fc`、目标 `#79c0ff`、有焦点时的无关节点 `#3d4350`、`range_ok===false` `#3a4152`、galaxy 按度数插值、其余 `#c9d1d9` | `graph-view-2d.js:596`-`603`、`93`-`101` |
| 焦点描边 | 2px 圆环：外部焦点 `#a371f7`，hover `#58a6ff` | `graph-view-2d.js:618`-`622` |
| 标签 | 短标签 `resolveNodeDisplayLabel`（`labelMode`+`labelMaxLen`）；10px、水平居中、位于节点下方 `r+4`；先描深色描边再填色（hover `#f0f6fc`、目标 `#79c0ff`、范围失效 `#6e7681`、其余 `#adbac7`） | `graph-view-2d.js:75`-`90`；`graph-label.js:26`-`40` |
| 悬停 | 命中变化才 `emit("hover")`；光标 `pointer`/`grab`；远端 hover（列表/KP hover）优先 | `graph-view-2d.js:358`-`377`、`460`-`469` |
| 自适应 | `fitToView(padding=36)`，缩放上限 2.5、下限 `zoomMin2d`；面板不可见时置 `_pendingRelayout`，显示时再 `resetSimulation` | `graph-view-2d.js:227`-`243`、`245`-`252` |
| 银河样式 | 背景 `#0a0d13`；节点为「径向渐变光晕 + 实心核心」；光晕强度 `galaxyGlow2d`（默认 0.6）；交互期间 `_pulse` 递增做呼吸 | `graph-view-2d.js:522`-`534`、`114`-`129`、`574`-`617` |

### 2.6 3D 图谱（`#graph-3d-root`）

| 项 | 现状 | 锚点 |
|---|---|---|
| 渲染器 | `THREE.WebGLRenderer({antialias:true})`，`pixelRatio ≤ 2`；`PerspectiveCamera` FOV 50，`near .1 / far 5000` | `graph-view-3d.js:242`-`256` |
| 灯光 | `AmbientLight(0.75)` + `DirectionalLight(0.45)`（位置 120/180/100） | `graph-view-3d.js:258`-`261` |
| 相机控制 | `THREE.OrbitControls`（`enableDamping`、`dampingFactor 0.08`）；按键映射用库默认：**左键 = ROTATE、中键 = DOLLY、右键 = PAN**，滚轮 = 缩放 | `graph-view-3d.js:263`-`268`；`lib/OrbitControls.js:81`-`85`；`index.html:119` |
| 分组容器 | `-edgeGroup / -nodeGroup / -pickGroup / -labelGroup / -haloGroup` | `graph-view-3d.js:270`-`279` |
| 节点网格 | 视觉半径 = `nodeRadius × 0.85`，`SphereGeometry(r,16,12)` + `MeshStandardMaterial`（roughness .55 / metalness .08；galaxy 时带 `emissive`）；拾取球半径 = `max(r×2.2, 10)`，`MeshBasicMaterial({visible:false, depthWrite:false})` | `graph-view-3d.js:370`-`406` |
| 拾取 | `Raycaster`（指针归一化坐标）+ 体素八叉树加速；八叉树仅在节点数 ≥ `MIN_NODES`（`MIN_OCTREE_NODES=40`）时构建，否则回退遍历全部拾取球 | `graph-view-3d.js:468`-`501`；`graph-octree.js:7`、`175` |
| 点击节点 | `pointerdown` 左键命中才 `preventDefault` 并准备拖拽；`pointerup` 未位移 → `nodeClick` | `graph-view-3d.js:925`-`957` |
| 悬停 | 每帧 `_updateHover()` 射线检测；光标 `pointer`/`grab` | `graph-view-3d.js:877`-`895` |
| 主循环 | `start()` 起 `requestAnimationFrame` 循环：同步坐标 → `controls.update()` → hover → 脉冲 → render | `graph-view-3d.js:648`-`665` |
| 缩放范围 | `zoomMinDistance3d 5` ~ `zoomMaxDistance3d 3000`，灵敏度 `zoomSensitivity3d` | `graph-settings.js:34`-`36`；`graph-view-3d.js:619`-`622` |
| 自适应 | `_fitCamera()`：包围盒跨度 ×1.35 作为相机距离，`controls.target` 对齐中心 | `graph-view-3d.js:537`-`548` |
| 银河样式 | 背景 `0x0a0d13`；节点亮度按度数插值 + `emissive`；光晕为 Sprite（共享径向渐变纹理）；交互期间 `_tickPulse` 调整 `emissiveIntensity` 与光晕透明度/缩放 | `graph-view-3d.js:282`-`288`、`47`-`55`、`57`-`112`、`667`-`702` |

**节点点击 → 跳转与 anchor 定位**：`initGraphPanel` 注册 `nodeClick` → `jumpToTarget({file, kp_id, name}, {source:"graph"})`（`app.js:889`-`899`）→ `openFile(file,{kpId})`；目标文档载入后若 `range_resolved.ok` 则 `highlightRange(start,end)` 并把左侧 KP 列表滚到该项（`app.js:1484`-`1491`）。**悬停效果**：`hover` → 侧栏底部覆盖条显示节点名/ID/文件/描述（`resolveNodeHoverHtml`），移出后恢复空闲或审计提示文案（`app.js:900`-`903`、`6441`-`6449`；`graph-label.js:42`-`55`）。

### 2.7 分组（`graph-groups.js`）

| 项 | 现状 | 锚点 |
|---|---|---|
| 算法 | 并查集：每条边 `union(source,target)`；无连边的孤立节点自成一群（**即「出边闭包分量」而非聚类**） | `graph-groups.js:83`-`101` |
| 群标签 | 取群内**度数最大**的 hub，用其 `name`（`hub_name`）或 `id`（`hub_id`），再按 `groupLabelMaxLen`（默认 12）截断 | `graph-groups.js:65`-`77`、`103`-`107` |
| 群排序 | 先按群规模降序，规模相同按标签 `localeCompare("zh")` | `graph-groups.js:121` |
| 智能命名 | `suggestGroupLabel` 是**占位**，直接返回 `suggested:null` + `reason:"search_kernel_not_available"` | `graph-groups.js:136`-`150` |
| 服务端标签 | `refreshGraphGroupLabels` 调 `suggest_group_labels`，返回项覆盖本地 hub 标签 | `app.js:987`-`1010` |
| 页签 UI | 首项恒为「全部」（`graph.group.allLabel`，count=群数）；群页签 count 仅当 size>1 时显示 | `app.js:793`-`818`；`i18n/zh-CN.js:912`-`916` |
| 显隐 | 仅在 `sidebarTab ∈ {graph2d,graph3d}` **且**图谱有节点时显示 | `app.js:748`-`757` |
| 选择 | `selectGraphGroup` → 存 `localStorage["-graph-group"]` → 重渲页签 → `resetSimulation()` 重布局 | `app.js:828`-`842` |
| 过滤 | 选中某群时只装载该群的节点与**两端都在群内**的边 | `graph-groups.js:152`-`164`；`graph-layout-2d.js:147`-`175` |
| 群分布 | 「全部」视图按群散布，两种模式由设置 `distMode` 决定：`grid`（默认）群按 cols×rows 网格占位、间距 `groupSpacing`（默认 260）、跨群**不**排斥；`scatter` 群心随机撒在圆/球内、**不写群锚点**、跨群排斥开启（孤立节点因此散落到外围） | `graph-groups.js:166`-`175`；`graph-layout-2d.js:52`-`83`、`90`-`127`；`graph-layout-sim-core.js` `skipPairRepulsion` |
| 页签轮滑 | 页签条监听 `wheel`（δy 为主时）横向滚动 | `app.js:769`-`782` |

### 2.8 图谱样式与持久化

**设置弹窗页签**（`renderTabsHtml`）：`graph2d` / `graph3d` / `graphGroups` / `search` / `check` / `view`（`graph-settings.js:765`-`773`；文案键 `settings.tab.*`）。2D/3D 页结构＝节点标签段 + 图谱样式段 + 布局段，右侧带**示例图预览列**（`graph-settings.js:629`-`647`）。

| 项 | 现状 | 锚点 |
|---|---|---|
| 视觉样式 | `graphStyle` 只有 `force`（标准）/ `galaxy`（银河 Galaxy）两项，**无第三项** | `graph-settings.js:566`-`572`；`i18n/zh-CN.js:972`-`978` |
| 光晕强度 | `galaxyGlow2d` / `galaxyGlow3d`（0–1，步长 0.05，默认 0.6），仅 galaxy 时显示该字段组 | `graph-settings.js:573`-`575`、`292`-`300` |
| 标签模式 | `labelMode`：名称（缩短）/ 知识点 ID / 名称（完整）/ **智能摘要（`smart`，`disabled` 占位）**；`labelMaxLen` 4–20 | `graph-label.js:7`-`17`、`graph-settings.js:504`-`523` |
| 力导向参数 | 边长/斥力/边拉力/向心力/初始散布/节点半径/箭头（仅 2D）/alpha 三件套/拖拽加热与松手加热/缩放参数 | `graph-settings.js:526`-`557` |
| 示例图 | `buildSampleGraph()` 硬编码 5 节点 4 条边（`reference`/`extend` 混用），文案键 `graph.sample.*`（随语言重绘） | `graph-settings.js:51`-`109`；`i18n/zh-CN.js:934`-`939` |
| 预览高度 | 拖拽 `#graph-settings-preview-resizer` 调高（140–520px），存 `localStorage["-settings-preview-h"]` 并写 ui-settings | `graph-settings.js:415`-`430`、`479`-`490` |
| 持久化 | ① `localStorage["-graph-settings"]`；② `config/ui-settings.json` 经 `save_ui_settings`（280ms 防抖）与 `get_ui_settings`（Hydrate 时磁盘优先） | `graph-settings.js:7`、`124`-`228` |
| 恢复默认 | `reset()` 清 localStorage 键并置默认值，同时级联 `MemoriaCheckSettings.reset()` | `graph-settings.js:230`-`241` |
| 参数生效 | 改值 → `applyGraphViewSettings` 重算群 + 广播给 2D/3D 布局与视图；命中重布局键的维度才 `resetSimulation` | `app.js:909`-`985` |

**侧栏几何（两处拖拽，含义不同）**：

| 拖拽条 | 作用 | 范围 / 持久化 | 锚点 |
|---|---|---|---|
| `#sidebar-resizer` | 侧栏**宽度** | 180–480px；**不持久化** | `app.js:11967`-`11984` |
| `#sidebar-nav-kp-resizer` | 上半（文件树/图谱）与下半（KP 列表）**高度比** | 上限比例 0.35–0.92，且上半 ≥100px、下半 ≥72px；按页签分别存 `localStorage["-sidebar-split-<tab>"]` + ui-settings；默认 files 0.55 / graph2d 0.82 / graph3d 0.72 | `graph-settings.js:42`-`46`、`330`-`359`、`381`-`399`；`app.js:1231`-`1233` |

### 2.9 构建与加载

| 项 | 现状 | 锚点 |
|---|---|---|
| 顶栏「构建」 | `#btn-build`（title「构建：同步链接配置并生成图谱」） | `index.html:63` |
| 执行中 | 按钮立即 `disabled=true`，状态栏 `graph.build.building` + `graph.build.buildingDetail`，`finally` 恢复可点 | `app.js:1012`-`1048` |
| 成功 | `build_kb` → 刷新文件树/链接目标/图谱 → 重开当前文件 → 状态栏 `graph.build.done`；有告警时追加 `graph.build.doneDetail`（`{n} 处待人工配置`）与 `graph.build.doneKinds` | 同上 |
| 失败 | `res.status==="error"` → `setStatus(res.message \|\| graph.build.failed)`；抛异常 → `graph.build.failed` + 异常串 | 同上 |
| 数据加载 | `loadGraphData()` → `get_graph_data`；非 ok → `graph.loadFailed`「图谱加载失败」+ 服务端消息 | `app.js:1051`-`1075` |
| 加载后 | 刷新 2D/3D 页签计数（=节点数）→ 首次才 `initGraphPanel()` → `loadPayload` → 服务端群标签 → 群页签 → `resetSimulation` → 更新提示条 | `app.js:730`-`738`、`1059`-`1071` |
| 提示条（覆盖层） | `.-graph-hint--overlay` 绝对定位在画布底部、`pointer-events:none`（仅按钮可点）；DOM 初始文案为 `graph.overlay2d/3d`（`index.html:128`、`132`），首次刷新后改由 `updateGraphAuditHint()` 写 `graph.hint.idle2d/idle3d`；有图边审计告警时换成告警 + 「打开文件」按钮（点击 `gotoGraphAuditIssue`） | `app.css:406`-`427`；`app.js:1136`-`1167`、`12228`-`12237` |
| 页签切换 | `setSidebarTab`：同步按钮 `active`、切 `.-sidebar-view` 显隐、启停下层布局、清 KP hover、刷群页签与提示条、`reflow()` 两块视图 | `app.js:1239`-`1250`、`1173`-`1210` |
| **页签条几何（2026-09-19 修）** | `. -sidebar-tabs-wrap` 高 = 页签条高（**2026-09-19 起为 34px**：由末尾 `--bar-h-b` 统一钉住，见 01 篇 §6「统一栏高」），其下缘与 `#sidebar-body-split` 顶边**严丝合缝（间隙 0）**；页签条 `border-bottom: 0.5px`（计算 1px）、页签 `border-bottom: 2px` + `margin-bottom: -1px` 正好压在容器下边框上（实测 active 页签 `bottom` 与容器 `bottom` 差 **0.00**）。**起因**：`. -sidebar-nav-tabs { margin-bottom: 0 }` 与 `.-config-tabs { margin-bottom: 0.75rem }` 同特异度、而后者在本文件更靠后 ⇒ 那条 0 一直被盖掉，页签条下白留 **13.2px**（用户反馈"外框太宽、与页签间还有缝隙"）；修法 = 选择器改双类 `.-config-tabs.-sidebar-nav-tabs`（`app.css:236-238`） | `app.css:231`-`244`、`1534`-`1560`、`5170`-`5204`；实测 harness 8655（13.2px→0）与 8656（高 30.19→34） |

## 3. 交互流程

**创建链接（选区）**：预览/源码拖选 → 右键 → 「创建链接…」→ 链接编辑器（`create`）→ 自动扫正文匹配并预勾选 → 勾选目标（可手输 `id` 或 `tag:`）→ 可选逐个设边型/权重 → 「保存」→ `wrap_text_as_link` → 重渲 → 状态栏 `cfg.linkSave.saved` + `savedDetail`（`app.js:5666` 起）。

**点实链接**：`click` → `onMemoriaLinkClick` → `resolve_link` → 单目标 `jumpToTarget`（入导航栈 + `openFile({kpId})` → `highlightRange`）；多目标走 `showLinkPicker`（§2.2）。

**悬停正文链接联动图谱**：`mouseenter` → `highlightGraphFromLink` → `is-graph-link-focus` 类 + `setExternalFocus({sourceIds,targetIds})`（源＝该行所属最小 KP，目标＝路由目标），并把提示条换成「链接 源 → 目标」；`mouseleave` 清除（`app.js:6511`-`6538`；源码区另有逐行 `mouseover` 版本 `app.js:6547`-`6570`）。

**构建**：顶栏「构建」→ `build_kb` → 全库重建链接配置与图谱 → 就地刷新侧栏与当前文件。

## 4. i18n key 前缀（代表键）

| 前缀 | 代表键 | 用途 |
|---|---|---|
| `menu.*` | `menu.createLink`、`menu.linkEdit`、`menu.linkDetach`、`menu.linkRemoveRoute`、`menu.copyTargetKey` | 选区/链接右键菜单 |
| `link.*` | `link.selectTarget`、`link.viewAll`、`link.saveJump`、`link.confirmJump` | 链接弹窗标题与页脚 |
| `cfg.linkSave.*` | `cfg.linkSave.titleCreate/titleEdit/titleMulti`、`cfg.linkSave.hintNoTarget`、`cfg.linkSave.savedDetail` | 保存状态与提示 |
| `cfg.linkMeta.*` | `cfg.linkMeta.anchorLabel`、`cfg.linkMeta.legendPrimary`、`cfg.linkMeta.addPlaceholder`、`cfg.linkMeta.m4Summary`（占位） | 编辑器控件文案 |
| `cfg.linkEdge.*` | `cfg.linkEdge.sectionTitle`、`cfg.linkEdge.relevanceLabel`…`cfg.linkEdge.suggestBtn`、`cfg.linkEdge.notIntegrated` | 图谱边面板 |
| `cfg.linkOps.*` | `cfg.linkOps.detachConfirm`、`cfg.linkOps.deleteConfirm`、`cfg.linkOps.unwrapConfirm` | 移除/删除确认 |
| `cfg.linkClick.*` | `cfg.linkClick.notFound`、`cfg.linkClick.unboundTitle`、`cfg.linkClick.graphLinkWord` | 点击失败与悬停提示 |
| `graph.*` | `graph.group.*`、`graph.hint.*`、`graph.overlay2d/3d`、`graph.build.*`、`graph.loadFailed`、`graph.sample.*`、`graph.settings.*` | 图谱面板与设置 |
| `settings.tab.*` | `settings.tab.graph2d/graph3d/groups/search/check/view` | 设置弹窗页签 |

键值全文见 [i18n-inventory.md](../i18n-inventory.md)（`i18n/zh-CN.js:281`-`360`、`757`-`790`、`905`-`1003`）。

## 5. 边界与已知坑

1. **没有 Radial / Top-down / Free-force 之类的「布局模式」开关**：全仓 grep `radial|topdown|layoutMode` 在应用代码中零命中（只命中 `createRadialGradient`）。2D/3D **都是力导向**（`graph-layout-2d.js` / `graph-layout-3d.js` / `graph-layout-sim-core.js`），差异只在维度与初始位置分群（`initialPositionsForGroups`，`graph-layout-2d.js:51`-`82`）。
2. **边没有「强边实线 / 弱边虚线」映射**：边的线型恒为实线，强弱只由颜色（类型）与透明度/线宽（是否聚焦）表达；虚线只出现在 `-link-pending` / `-link-broken` / `-link-multi` 的**文字下划线**上（`app.css:1665`-`1721`）。3D 的 `linewidth` 被硬编码为 1，改它不会有效果（WebGL 限制，`graph-view-3d.js:873`）。
3. **「智能推荐」占位 vs 真实「推荐」按钮**：链接编辑器里的 `<details>`「智能匹配（M4 · tag / Lexical）」是**纯静态占位**——按钮写死 `disabled`，内容是硬编码示例（`q-learning` / `94%`），无任何数据绑定（`app.js:5215`-`5226`）；配置弹窗「待确认」页底部同样有两块静态占位（`m4SuggestBlockHtml`，`app.js:2195`-`2225`、`2778`-`2780`、`2864`）。而图谱边面板里每个目标的「推荐」按钮是**真实接线**（`suggest_link_relevance`，`app.js:4921`-`4958`）：后端未给建议（`res.suggested == null`）时提示 `cfg.linkEdge.notIntegrated`「智能推荐尚未接入」+ `cfg.linkEdge.defaultDetail`。
4. **边类型颜色有两套且不一致**：图谱用 `contain #3fb950 / reference #58a6ff / extend #d29922`（`graph-engine.js:7`-`11`），KP 边页徽标用 `contain #5cb85c / reference #5bc0de / extend #f0ad4e`（`app.js:3621`-`3631`）。
5. **断链的鼠标样式与行为不一致**：`-link-broken` 声明 `cursor: not-allowed`（`app.css:1708`）且 `tabindex=-1`，但点击实际会**打开链接编辑器**（`app.js:6135`-`6137`），并非「不可点」。
6. **侧栏宽度不持久化**：`#sidebar-resizer` 只改内联宽度，无 `localStorage`/ui-settings 写入（`app.js:11967`-`11984`）；持久化的只有折叠状态 `-sidebar-collapsed`。
7. **「构建」后重载当前文件不带 flush**：`buildKb` 末尾调 `openFile(currentPath,{skipNav:true})`（`app.js:1029`-`1031`），而 `openFile` 只在**目标路径与当前不同**时才 `flushDurableBarrier()`（`app.js:1400`-`1404`）；同一路径重载会直接用 `load_document` 的结果覆盖 `state.doc` 并把 `_dirty` 置 false（`app.js:1411`-`1419`）。因此「构建」瞬间未落盘的编辑（<1.5s 自动保存窗口）有被磁盘内容覆盖的风险（静态代码路径推断，未做运行时验证 → 见 §7）。
8. **3D 初始化可能直接抛错**：`GraphView3D` 构造器在 `global.THREE` 缺失时 `throw new Error(T("graph.view3d.notLoaded"))`（`graph-view-3d.js:175`-`177`），而 `initGraphPanel` 对该构造**未包 try/catch**（`app.js:880`-`888`）——Three 脚本缺失时可能中断后续 `nodeClick/hover` 绑定；WebGL 创建失败则走内部 `_webglFailed` 静默路径（`graph-view-3d.js:245`-`252`）。
9. **图谱页签计数=节点数**：`#sidebar-tab-count-graph2d/graph3d` 都写 `graphData.nodes.length`（`app.js:733`-`737`），不区分群。
10. **群命名「智能」是占位**：`suggestGroupLabel` 恒返回 `null`（`graph-groups.js:136`-`150`），设置页对应选项 `disabled`（`graph-settings.js:614`）。
11. **`groupSpacing` 只在「全部」视图的 `grid` 分布下有摆位意义**：选中具体群时只保留该群节点，`groupSpacing` 不再起作用（`graph-groups.js:152`-`164`）；`scatter` 分布不写群锚点，`groupSpacing` 只用于估算初始散布半径（`graph-layout-2d.js:101`-`106`）。
12. **`data--src-line` 缺失影响图谱联动**：链接的 `data-link-line` 取自最近 `[data--src-line]` 块（`app.js:6266`-`6268`），因此 Mermaid 等替换块内的链接拿不到行号 → 图谱高亮的「源」会为空（与 04 篇「未证实/待确认」第 2 条同源）。

## 6. 代码锚点表

| 主题 | 文件:行 |
|---|---|
| 侧栏页签 / 群页签条 / 图谱容器 DOM | `index.html:99`-`134` |
| 链接弹窗 DOM 与页脚 | `index.html:303`-`320` |
| 图谱容器与提示条样式 | `app.css:273`-`294`、`324`-`375`、`377`-`444` |
| 链接编辑器控件样式 | `app.css:2266`-`2350`、`2533`-`2570`、`2630`-`2640`、`2723`-`2770`、`2796`-`2920`、`2922`-`2975` |
| 断链 / 虚链接 / 多目标样式 | `app.css:1665`-`1721`、`3540`-`3557` |
| 链接右键菜单构建 | `link-context-menu.js:38`-`160` |
| 选区右键菜单（创建链接 / 设为知识点 / 样式） | `link-context-menu.js:162`-`229`；`app.js:9524`-`9637` |
| 链接编辑器候选构建 / 目标列表 / 图例 | `app.js:5461`-`5528`、`5146`-`5308` |
| 编辑器状态与保存按钮同步 | `app.js:5035`-`5060` |
| 锚文本重匹配扫描 | `app.js:2517`-`2563`、`2629`-`2707`、`5062`-`5076` |
| 目标搜索建议 / 手动添加 | `app.js:5310`-`5446` |
| 边属性面板（每目标边型/权重/推荐） | `app.js:4837`-`4958`、`4991`-`5021`、`5078`-`5121` |
| 保存链接（create/edit/跳转） | `app.js:5632`-`5700`、`5618`-`5630` |
| wiki 链接后处理与状态类 | `app.js:6250`-`6286` |
| 链接点击行为 | `app.js:6130`-`6199` |
| 链接操作：detach / remove / delete route | `app.js:6024`-`6128`、`6065`-`6094` |
| 图谱悬停联动（预览 / 源码） | `app.js:6494`-`6570` |
| 图谱数据加载与构建 | `app.js:1012`-`1075`、`730`-`738` |
| 图谱面板初始化与节点点击 | `app.js:858`-`906`；`1484`-`1491` |
| 参数下发与重布局判定 | `app.js:909`-`985` |
| 群页签渲染与选择 | `app.js:748`-`842` |
| 侧栏页签切换 / 面板激活 | `app.js:1173`-`1234` |
| 提示条（空闲 / 节点详情 / 链接焦点 / 审计） | `app.js:1130`-`1167`、`6441`-`6508` |
| 侧栏宽度拖拽 / 折叠 | `app.js:11967`-`12015` |
| 边类型权威定义与默认权重 | `src/memoria/graph/edge_types.py:10`-`30`、`61`-`135` |
| 图谱引擎（数据层 / 边色） | `graph-engine.js:7`-`11`、`62`-`105` |
| 节点标签与悬停详情 | `graph-label.js:7`-`55` |
| 分组算法与过滤 | `graph-groups.js:83`-`174` |
| 2D 布局 / 3D 布局 | `graph-layout-2d.js:51`-`82`、`119`-`175`、`337`-`357`；`graph-layout-3d.js:60`-`96`、`131`-`183`、`386` |
| 2D 视图（绘制/交互/银河） | `graph-view-2d.js:27`-`129`、`227`-`243`、`402`-`505`、`522`-`627` |
| 3D 视图（场景/拾取/循环/高亮） | `graph-view-3d.js:173`-`288`、`375`-`501`、`648`-`702`、`787`-`895`、`897`-`963` |
| 图谱设置（默认值/持久化/表单） | `graph-settings.js:7`-`46`、`124`-`241`、`504`-`605`、`765`-`773`、`821`-`849` |
| 侧栏上下占比与预览高度 | `graph-settings.js:330`-`490`、`891`-`950` |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未运行时验证）：「构建」时同路径重载是否真会丢未落盘编辑——静态路径为 `buildKb` → `openFile(同路径,{skipNav:true})` → 跳过 `flushDurableBarrier`（`app.js:1400`-`1404`）→ `load_document` 覆盖 `state.doc` + `_dirty=false`（`app.js:1411`-`1419`）；若 `build_kb` 期间用户有编辑，防抖写盘计时器（`SAVE_DEBOUNCE_MS=1500`）此后写回的是被覆盖后的内容。需运行时复现才能定论。
- ⚠️ 待确认（未运行时验证）：`initGraphPanel` 里 `new MemoriaGraphView3D(...)` 在 `THREE` 缺失时的抛错会影响同一函数内后续的 `engine.on("nodeClick"/"hover")` 绑定（`app.js:880`-`905`、`graph-view-3d.js:175`-`177`）——静态代码路径如此，实际表现未验证。
- ⚠️ 待确认（未取证）：`-link-multi` 类的赋值点不在 `postProcessWikilinks`（那里只写 `-link-resolved` / `-link-broken` / `-link-pending`，`app.js:6271`-`6285`）；菜单判定却依赖它（`link-context-menu.js:101`-`104`），实际赋值时机未逐处取证。
- ⚠️ 待确认（未取证）：`suggest_link_relevance` 返回 `suggested == null` 时走 `cfg.linkEdge.notIntegrated` 分支（`app.js:4946`-`4953`）；后端何时返回空建议、是否等同「推荐未接入」未逐处取证。
- ⚠️ 待确认（未取证）：2D 侧 `-link-pick-item` 有两条规则块（`app.css:2266`-`2277` 与 `2897`-`2914`），后者是否覆盖前者在既有主题下未做视觉核对。
- ⚠️ 待确认（未取证）：`graph-octree.js` 的体素参数与命中率未做基准核对（仅在节点数 ≥40 时启用，`graph-view-3d.js:468`-`485`）。
- ⚠️ 待确认（未取证）：链接编辑器匹配面板在超大文件下的渲染开销（`renderLinkEditorMatchPanelHtml` 逐条渲染命中，`app.js:2517`-`2563`）未做性能核对。
