# 09 · 设置、i18n 与快捷键

> **用途**：把 Memoria「设置」窗口的**具名页签**逐项列全（名称 / i18n key / 控件类型 / 取值范围与默认值 / 是否即时生效 / 是否落盘），并给出 i18n 机制（`data-i18n`、`data-i18n-attr`、`T()`、回退、参数填充、语言包结构）与**全库快捷键总表**（含只在特定区域生效与已知缺失项）。
> **目标读者**：在 Memoria 之上做集成 / 移植 / 对齐的 Agent 与人；给 Memoria 写前端改动的人。
> **关联文档**：[README.md](./README.md)（本套用法与维护约定）、[01-shell-and-layout.md](./01-shell-and-layout.md)（缩放变量、弹窗层级与通用弹窗结构）、[../i18n-inventory.md](../i18n-inventory.md)（界面文案清单）、[../../conventions/i18n.md](../../conventions/i18n.md)（语言系统维护规范）、[10-data-layout-and-host-embedding.md](./10-data-layout-and-host-embedding.md)（`ui-settings.json` 的真实落点、无桥时的表现）。
> **状态**：生效中，2026-09-15。

---

**证据锚约定**：`文件:行号` 以仓库根为基准；前端路径前缀 `src/memoria/ui/static/app/`（下称 `index.html`、`js/*.js`、`i18n/*.js`、`css/app.css`）；壳端原生对话框在后端 `src/memoria/app/shell/**`。

## 1. 区域概览

```
#btn-settings（顶栏「设置」按钮）        index.html:83         → openModal()  graph-settings.js:875
#settings-modal .-modal.hidden          index.html:319-363   宽 min(820px,96vw) / 高 min(680px,88vh)（app.css:749-757）
├── .-modal-header                      index.html:322-325   标题 modal.settings + ×（#settings-close）
├── #settings-tabs .-settings-tabs-wrap index.html:326       运行时注入页签按钮（graph-settings.js:789-799）
├── #settings-body .-modal-body.-settings-body index.html:327 运行时注入当前页签内容（graph-settings.js:801-843）
│   ├── .-settings-layout              app.css:888-895       grid：表单列 minmax(220px,1fr) + 预览列 minmax(260px,1.1fr)
│   │   ├── .-settings-form            app.css:901-906       表单列（纵向滚动，overscroll 隔离）
│   │   └── .-settings-preview-col     app.css:952-… / graph-settings.js:607-620  仅 2D/3D 页：示例图画布 + 竖直分栏柄
│   └── .-settings-layout--solo        app.css:897-899       单列（节点群 / 检索 / 检查 / 显示页）
├── #settings-body-agent               index.html:328-355   **静态体**（2026-09-19 新增）：「Agent」页签的字段常驻此处，
│                                                         与上行动态体 `hidden` **互斥**（见 graph-settings.js:807-812）；
│                                                         2026-09-23 起页内再分**两个可折叠子版块**（`#agent-sections` 装配在 JS 里）
└── #settings-config-path               index.html:356       底部一行：settings.configPath「设置保存在程序目录：{path}」（graph-settings.js:883-906）
└── .-modal-footer                      index.html:357-362   「恢复默认」#settings-reset + 「关闭」#settings-dismiss
```

页签集合是 **7 个具名页签**：`2D 图谱` / `3D 图谱` / `节点群` / `检索` / `检查` / `显示` / **`Agent`**（graph-settings.js:789-799；文案 `settings.tab.*`，`settings.tab.agent` 追加在 zh-CN.js:1254-1256 / en.js:1339-1341）。**顺序即上表顺序**——「显示」在第 6 位、「Agent」在最后（第 7 位），「检索」在「检查」之前。**「Agent」是唯一的静态体页签**：内容（`#settings-body-agent`，端点/模型/密钥/超时/出网）常驻 index.html，由 `setSettingsTab()` 显隐，与其它页签的动态体 `#settings-body` **互斥**。**2026-09-23 两处变化**：① 页签名由「对话」改为 **`Agent`**（人：「页签 chat 改名为 Agent」）；② 原「能力」页签**并入本页**，页内分成**两个可折叠子版块** ——「对话」（默认展开，装着原 `#agent-settings`）与「能力插件」（默认折叠，装着能力面板）⇒ 页签总数由 8 回到 **7**。**页签条可横向滚动**：`#settings-tabs` `overflow-x: auto` + 滚条整条隐藏（`scrollbar-width: none` + `::-webkit-scrollbar` 归零），滚轮绑定见 `graph-settings.js` 末尾 `bindSettingsTabWheelScroll()`（写法同 `#tabs`）。

> ⚠️ 常见的四种归纳（显示 / 图谱 / 检索 / 检查）与实际不符：图谱被拆成 3 个独立页签（2D、3D、节点群）。另设置窗口内**没有**「高级选项」这一层：只有具名页签 +（2026-09-23 起）**「Agent」页内的两个可折叠子版块**（「对话」/「能力插件」；全前端检索「高级 / advanced」仍只命中链接编辑器的 `.-link-advanced`，app.css:2782-2792）。

**2026-09-23：设置区的「折叠子版块」已成为统一组件**（人：「设置其他地方也可也效仿 Agent 页签的子版块设计可展缩」）。六个**动态体**页签（`2D 图谱` / `3D 图谱` / `节点群` / `检索` / `检查` / `显示`）里的每一个 `.-settings-section` 都被折成 **`<details class="-settings-section" open>` + `<summary class="-settings-section-head">` + `<div class="-settings-section-body">`**：折叠由 `graph-settings.js::foldSettingsSections()` 在 `setSettingsTab()` 写完 `bodyEl.innerHTML` 之后**就地移动节点**完成 —— 各页 renderer **一行未改**（字段 id 与各 settings 模块 / `agent-panel.js` 的事件绑定原样保留），`section` 标签守卫 ⇒ 对 Agent 页已有的两个 `<details>` 与重复调用**幂等**；**默认全部展开**（提供的是"可收起"，不是"默认藏起来"）。三角标记复用 `agent-panel.js` 注入的**全局** `details > summary::before`（不另画），标题排版对齐既有 `.-settings-heading` 那一档（`app.css` 末尾追加块）。实测（harness 8663 + `AAA_Vocab` 临时副本）：六页 `details` 数 = **3 / 3 / 1 / 1 / 1 / 4**、残留 `<section>` **0**、全部 `open=true`、summary 文本 = 原 `<h3>` 文本；**真实点击 `<summary>`** ⇒ `open` true→false、该块高 **124 → 33**、后续小节整体上移 91px、`elementFromPoint` 同点由 `SELECT` 变下一节 `SUMMARY`；`.-settings-form` 仍可滚（`scrollHeight 891 > clientHeight 519`），折叠后 `#display-theme → light` 仍写盘。规范口径与未取证项见 [ui-visual-language.md §4「实施记录 C」](../../design/ui-visual-language.md)。

## 2. 逐处细节

### 2.1 入口、骨架与生命周期

| 项 | 证据 | 说明 |
|---|---|---|
| 唯一入口 / 打开 | graph-settings.js:950、851-857 | `#btn-settings` click → `openModal()`：移除 `.hidden` → 重绘**当前页签**（模块变量 `settingsTab`，初值 `"graph2d"`，graph-settings.js:111）→ 异步拉设置文件路径并显示。无菜单项、无快捷键 |
| 关闭 / 无 Esc | graph-settings.js:884-889、957-961 | 三条路径：× 按钮、`#settings-dismiss`、点遮罩；关闭时先 `flushPendingDiskSave()`（检索页）→ 落盘 → 拆预览。**不响应 Esc**（未检索到 settings 相关 keydown） |
| 可拖动 | app.js:12560-12609、12611-12624 | 按住 `.-modal-header` 拖动 `.-modal-box`（排除按钮/输入/select/a/contenteditable）；关闭时 `MutationObserver` 清零位移 |
| 页签状态不落盘 | graph-settings.js:111、777-785 | `settingsTab` 只在内存；应用重启后回到「2D 图谱」 |
| 页签换页副作用 | graph-settings.js:786-818 | 每次切页先 `teardownPreview()`（销毁示例图引擎/视图）；离开 2D/3D 时额外 `stopPreview()` |
| 「恢复默认」范围 | graph-settings.js:230-241、953-956 | 重置 **图谱设置 + 侧栏上下分栏比例 + 检查设置**，然后重绘当前页签。**不含**显示设置、检索设置、界面语言 |

### 2.2 「显示」页（`settings.tab.view`）

渲染：`MemoriaDisplaySettings.renderSettingsBody()`（display-settings.js:250-301）；绑定：display-settings.js:303-360。四个 section：主题 / 语言 / 文字 / 界面整体缩放 —— **2026-09-23 起四者（以及其它五个页签的每个 section）都被折成可折叠的 `<details open>`**（见 §1 末尾的折叠说明，默认展开、可点标题收起）。**2026-09-19 修（滚不动）**：显示页原先是**唯一**没有 `-settings-layout--solo > -settings-form` 包裹的页签（检索 / 检查 / 节点群 都有），而弹窗体 `#settings-body` 是 `overflow: hidden` ⇒ 内容一旦高于弹窗体就**整块裁掉、滚轮无效、下半截看不到**（用户报："这个页签下的配置项没有办法滚轮滚动，底下的看不到"）。现按同款结构包一层（`return` 模板的首尾**原位各加一层**，**行号零漂移**）⇒ 滚动交给 `.-settings-form`（实测 `#settings-body` 448=448 不再溢出、`.-settings-form` 428→550 可滚、`scrollTop` 可写到底且末节可见）。

| 项（i18n key） | 控件 / 选择器 | 取值与默认值 | 即时生效 | 落盘 |
|---|---|---|---|---|
| 界面语言 `settings.display.langLabel` | `<select id="display-language">`（display-settings.js:255-260）；选项文案 `langs.*` | `zh-CN` / `en`（i18n.js:15、zh-CN.js:420）；默认 `zh-CN`（i18n.js:14） | 是：`setLang()` → 刷新静态节点 + 派发刷新回调（i18n.js:117-135）；**切完调 `applyAll()`** 重算正文字体栈的语言优先级（display-settings.js:354） | 本地 `localStorage["-i18n"]`（i18n.js:13、119）+ 磁盘 `i18n.lang`（i18n.js:142-151） |
| 字号 `settings.display.fontSize` | `input[type=range][data-display-setting="previewFontSize"]`（display-settings.js:284） | **12–28，步长 1，默认 14**（display-settings.js:27-28、12） | 是：`save()` → `applyAll()`（display-settings.js:217-222） | `localStorage["-display-settings"]` + 磁盘 `display.previewFontSize`（display-settings.js:191-195） |
| 缩放比例 `settings.display.uiScale` | `input[type=range][data-display-setting="uiScale"]`（display-settings.js:296） | **0.8–1.5，步长 0.1，默认 1.0**（display-settings.js:29-31） | 是（同上） | 同上，键 `display.uiScale` |
| 复位为 100% `settings.display.resetScale` | `<button id="display-ui-scale-reset">`（display-settings.js:298） | — | 是：`resetUiScale()`（display-settings.js:232-234、333-342） | 同上 |
| **按语言的正文字体** `settings.display.fontLangNote`（**2026-09-23 新增**） | 每种界面语言一个**下拉** `select[data-display-font-lang="<lang>"]`（生成器 `fontSelect()` display-settings.js:374-381、逐行装配 `fontRows()` display-settings.js:383-395，语言表 = `MemoriaI18n.SUPPORTED`） | 选项 = 首项**空值**（文案 `settings.display.fontSlotDefault`「默认字体」）+ `FONT_CHOICES` 15 个常见字体名（display-settings.js:21-25）；**存档值不在表里会补成选项并选中**（否则回显成空白）；选「默认字体」= 该语言跟随默认 | 是：`change` → `save({fonts})` → `applyAll()` → `applyFonts()` 写 `--font-content`（display-settings.js:166-174、323-332） | `localStorage["-display-settings"]` + 磁盘 `display.fonts`（**按语言全覆盖**写、空档写空串 —— 后端浅合并删不掉键，见 display-settings.js:85-92） |
| **顶栏字标字体** `settings.display.fontBrandLabel`（**2026-09-23 新增**） | 同一个下拉形状：`select[data-display-setting="fontBrand"]`（display-settings.js:289），走既有 `[data-display-setting]` 绑定通道 | 选项 = 首项空值（文案 `settings.display.fontBrandDefault`「跟随正文字体」）+ 同一张候选表；选空值 = **跟随正文字体** | 是（同上，另写 `--font-brand`；落点见 display-settings.js:166-174） | 同上，键 `display.fontBrand` |

**作用范围**：字号（display-settings.js:137-144）只写 `#preview` 的 `--preview-font-size` 与 `#editor` 的 `--editor-font-size` 两处内联变量，**两者同值**（源码区与分栏区一起变）；缩放（display-settings.js:146-157）设 `document.documentElement.style.fontSize = 16 × scale + "px"`（等于 1.0 时清空回默认），因样式表尺寸绝大多数是 `rem`，等价于整体等比缩放，改完**主动派发一次 `resize`**（display-settings.js:156）让侧栏按钮对齐、图谱容器等重算——**不是** `#app` 的 `zoom`。**字体**（display-settings.js:166-174）写 `<html>` 上的两个变量，落点在 `app.css` 末尾：`--font-content` → `.markdown-body`（**Markdown 预览**与**对话栏里渲染的正文**共用这一个类，故一处设置两处生效）、`--font-brand` → `.toolbar-left .logo`（`var(--font-brand, var(--font-content, var(--font-sans)))` 三级兜底）；**两个字体档都选「默认/跟随」** ⇒ 变量被**移除**（不是写空串）、回到默认字体（详见 [01-shell-and-layout.md §2.10](01-shell-and-layout.md)）。**控件形状（人 2026-09-23 复审指定）**：字体档一律是 `.-settings-field` 里的原生 `<select>`（与「主题 / 语言」两个下拉同一套 `.-settings-field select` 规则，实测 9 项计算样式逐项相等），**不用**自造的文本框 / `datalist`。

### 2.3 「2D 图谱」/「3D 图谱」页

渲染：`renderSettingsBody2d()` / `renderSettingsBody3d()`（graph-settings.js:629-647），组成 = 节点标签 section + 图谱样式 section + 布局 section（2D 含箭头与 2D 缩放；3D 含 3D 缩放）。控件全部 `data-graph-setting`，值读写走 `MemoriaGraphSettings.load()`；持久化 `localStorage["-graph-settings"]` + 磁盘 `graph` 段（280ms 去抖，graph-settings.js:148-176、220-228）。

**节点标签**（graph-settings.js:504-524）

| 项（key） | 控件 | 取值与默认值 |
|---|---|---|
| 显示策略 `graph.settings.nodeLabel.display` | `<select data-graph-setting="labelMode">`，选项来自 `MemoriaGraphLabels.LABEL_MODES` | `name_short`（默认）/ `id` / `name`；`smart` **disabled**（graph-label.js:7-12） |
| 缩短字数 `graph.settings.nodeLabel.maxLen` | range | 4–20，步长 1，默认 **8**（graph-settings.js:11-12、521） |

**图谱样式**（graph-settings.js:560-577）

| 项（key） | 控件 | 取值与默认值 |
|---|---|---|
| 视觉样式 `graph.settings.style.label` | `<select data-graph-setting="graphStyle">` | `force`（标准，默认）/ `galaxy`（银河）（graph-settings.js:37、568-571） |
| 辉光 `graph.settings.style.glow` | range，**仅 `graphStyle=galaxy` 时显示**（`syncStyleVisibility`，graph-settings.js:292-300、846-848） | 0–1，步长 0.05，默认 0.6（`galaxyGlow2d` / `galaxyGlow3d`，graph-settings.js:38-39、574） |

**布局参数**（graph-settings.js:526-558、660-668；`DEFAULTS` 见 graph-settings.js:11-40）

| 键 | 范围 / 步长 | 默认 | 备注 |
|---|---|---|---|
| `linkDistance` 边长 / `repulsion` 斥力 | 60–200 / 4；2000–9000 / 200 | 108；5200 | |
| `linkStrength` 边拉力 / `centerStrength` 向心力 | 0.08–0.6 / 0.02；0–0.05 / 0.002 | 0.28；0.006 | 显示 2 位小数 |
| `spreadFactor` 初始散布 / `nodeRadius` 节点半径 | 0.2–0.55 / 0.02；4–12 / 1 | 0.42；6 | |
| `arrowSize` 箭头大小 | 4–12 / 1 | 7 | **仅 2D**（graph-settings.js:528-529） |
| `alphaMin` / `alphaDecay` / `alphaTarget` | 0.002–0.05 / 0.001；0.01–0.12 / 0.005；0.05–0.5 / 0.01 | 0.012；0.045；0.12 | 前两者显示 **3** 位小数（graph-settings.js:551-552） |
| `dragReheat` / `dragReleaseReheat` | 0.1–0.6 / 0.02；0.05–0.5 / 0.02 | 0.28；0.2 | |
| 2D：`zoomSensitivity2d` / `zoomMin2d` / `zoomMax2d` | 0.3–2.5 / 0.1；0.02–0.5 / 0.01；2–16 / 0.5 | 1.0；0.05；8 | 仅 2D |
| 3D：`zoomSensitivity3d` / `zoomMinDistance3d` / `zoomMaxDistance3d` | 0.3–2.5 / 0.1；2–50 / 1；500–8000 / 100 | 1.0；5；3000 | 仅 3D，单位为相机距离 |

**预览列**（graph-settings.js:607-620、670-732）：右列画一张**固定示例图**（`buildSampleGraph()`，文案键 `graph.sample.*`，graph-settings.js:50-109）；hover 节点时提示区改为节点信息卡（graph-settings.js:670-683）；竖直分栏柄可调预览高度 140–520px（`bindPreviewResize`，graph-settings.js:479-491），高度存 `localStorage["-settings-preview-h"]` + 磁盘 `settingsPreviewH`。

### 2.4 「节点群」页

渲染 `renderSettingsBodyGroups()`（graph-settings.js:592-629、649-654），单列、**无预览列**。

| 项（key） | 控件 | 取值与默认值 | 生效 |
|---|---|---|---|
| 分布模式 `graph.settings.groups.distLabel` | select `distMode` | `grid`（群组网格，默认）/ `scatter`（散落）（graph-settings.js:26、600-604）。`grid`＝群按 cols×rows 网格占位、跨群不排斥（群多时易叠成一团）；`scatter`＝群心随机撒在圆/球内、**不写 `groupOx/Oy/Oz` 锚点**，改由「向原点中心力 + 跨群排斥」自然铺开，无连边的孤立节点散落到外围 | 即时（`distMode` 在 app.js `_RELAYOUT_KEYS` 内 → 2D/3D 都重布局） |
| 「全部」群间距 `…spacing` | range 160–420 / 20 | 260（graph-settings.js:25）；**仅 `distMode=grid` 生效**，散落模式下整块隐藏（graph-settings.js:606-608、`syncDistVisibility`） | 即时 |
| 页签命名 `graph.settings.groups.label` | select `groupLabelMode` | `hub_name`（默认）/ `hub_id`；`smart` **disabled**（graph-settings.js:611-615） | 即时（触发群重算，app.js:969-977） |
| 页签最大字数 `…maxLen` | range 6–20 / 1 | 12（graph-settings.js:24） | 即时 |
| 群页签排序 `…sort` | select **disabled**（占位） | 仅「按规模（默认）」（graph-settings.js:618-623） | — |
| 隐藏单节点群页签 `…hideSingle` | checkbox **disabled**（占位，`.-settings-field--placeholder`） | 未实现（graph-settings.js:624-627） | — |

> 分布模式的实现落在布局层：`initialPositionsScattered`（`graph-layout-2d.js:85`-`127` 圆盘 / `graph-layout-3d.js:97`-`144` 球），跨群排斥开关见 `graph-layout-sim-core.js` 的 `skipPairRepulsion`（`scatter` 不跳过）。

### 2.5 「检索」页

渲染 `MemoriaSearchSettings.renderSettingsBody()`（search-settings.js:249-289）；单列。

| 项（key） | 控件 | 默认 | 生效时机 | 落盘 |
|---|---|---|---|---|
| 启用语义（向量）检索 `search.settings.enableEmbedding` | checkbox `data-search-setting="embeddingEnabled"` | `false`（search-settings.js:19-27） | **下次检索时读取**，不是即时：检索入口每次现读 `getSearchModes()`（toolbar-search.js:151） | `localStorage["-search-settings"]` + 磁盘 `search.embedding_enabled`（search-settings.js:153-175） |
| 正文定位 `search.settings.bodyLocate` | checkbox `bodyLocateEnabled` | `false` | 同上（`isBodyLocateEnabled()`，toolbar-search.js:177） | 磁盘 `search.body_locate_enabled` |

搜索模式 `searchModes` **没有独立控件**，由开关派生：`embeddingEnabled ? "both" : "lexical"`（search-settings.js:105、121）；磁盘键 `search.search_modes`（search-settings.js:167）。关闭弹窗时 `flushPendingDiskSave()` 兜底落盘（graph-settings.js:885；search-settings.js:179-183）。

### 2.6 「检查」页

渲染 `MemoriaCheckSettings.renderSettingsBody()`（check-settings.js:160-183）；单列。

| 项（key） | 控件 | 取值与默认值 | 生效 | 落盘 |
|---|---|---|---|---|
| 检查间隔 `check.settings.interval` | select `silentCheckIntervalSec`，选项文案 `check.settings.off/seconds/minutes` | 选项集 **0 / 30 / 60 / 120 / 300 / 600 秒**（check-settings.js:8）；默认 **120**（check-settings.js:10-13） | 即时：`restartSilentCheck()`（check-settings.js:117-121、144-146；订阅方 kb-check.js:650-654） | `localStorage["-check-settings"]` + 磁盘 `check` 段（check-settings.js:59-71） |
| 启用静默检查 `check.settings.enabled` | checkbox `silentCheckEnabled` | 默认 `true`；**间隔=0 时 disabled 且强制 false**（check-settings.js:52-56、175-178、90-94） | 即时 | 同上 |

注：非选项集的间隔值会被 `normalizeInterval()` 归一到默认 120（check-settings.js:44-48）。

### 2.7 语言切换：变什么 / 不变什么

| | 内容 | 证据 |
|---|---|---|
| **会变**（静态节点） | 全部挂 `data-i18n` / `data-i18n-attr` 的节点（顶栏、侧栏页签、视图切换、格式栏、各弹窗标题与按钮、欢迎页…） | i18n.js:91-115、117-135 |
| **会变**（注册了刷新回调的动态区域） | ① 设置弹窗当前页签重绘（graph-settings.js:976-981；app.js:12440-12444）；② 检查角标/状态栏检查统计/打开的检查弹窗（kb-check.js:656-665）；③ Trae 智能体弹窗（kb-agent.js:198） | 同左 |
| **不会变**（在旧语言里留到下次重绘） | 已渲染但未注册刷新回调的动态区域：KP 列表（app.js 渲染）、状态栏常规统计、标签页标题、图谱分组条、搜索结果面板等 | 全库仅 3 处 `addRefresh`（app.js:12440、kb-check.js:657、kb-agent.js:198）——file-tree.js、app.js 的 KP 列表、toolbar-search.js 均无。注：**按需生成的浮层**（文件树右键菜单、重命名弹窗）在下次打开时才调 `T()`，因此会直接用新语言 |
| **不会变**（本就不翻译） | ① Markdown 正文（用户文档内容不属界面文案，conventions/i18n.md:22）；② 壳端**原生文件对话框标题**——硬编码中文：`选择知识库文件夹` / `选择要导入的文件` / `选择图片文件`（pywebview_host.py:152、171、194），`选择知识库目录` / `选择导入文件` / `选择图片`（pyqt6_host.py:55、65、74）；③ 后端返回的 `message`（除 `check.issue.<code>` 机制外原样显示，app.js:258-268） | 同左 |
| 持久化 | `localStorage["-i18n"]`（立即）+ 磁盘 `ui-settings.json` 的 `i18n.lang`（280ms 去抖） | i18n.js:13、38-44、142-151 |

### 2.8 i18n 机制

| 机制 | 位置 | 规则 |
|---|---|---|
| `data-i18n="key"` | index.html 全篇（如 index.html:47、100、146） | 刷新时写 `el.textContent`（i18n.js:100-103）→ **会清空子元素**，只适合纯文本节点 |
| `data-i18n-attr="attr:key;attr2:key2"` | 如 index.html:44、77、87-90 | 以 `;` 分隔多对；每对用**第一个 `:`** 切分（`idx <= 0` 跳过），故属性名不可含 `:`、键可含 `.`；写入用 `setAttribute`（i18n.js:104-113） |
| JS 侧 `T(key, params)` | 各模块取 `MemoriaI18n.t`（graph-settings.js:9、display-settings.js:252、check-settings.js:148-152） | 动态渲染内容**不走** `data-i18n`，两套机制互不覆盖 |
| 查找与回退 | i18n.js:55-78 | 顺序：**当前语言 → `zh-CN` → 键名本身**；点路径逐段下钻；值必须是 `string`，否则视为缺失 |
| 参数填充 | i18n.js:66-71 | 正则 `\{(\w+)\}`；参数缺失时**保留原字面量**（不置空） |
| CSS 文案 / 语言自述名 | i18n.js:96-98、86-89 | 伪元素无法挂 `data-i18n`：整页刷新时同步 `--memoria-i18n-range`（取自 `assist.rangeTag`）；语言名取 `langs.<code>`（zh-CN.js:420），取不到回显语言代码 |
| 语言包结构 | i18n/zh-CN.js:1-3、en.js 同构；`window.MEMORIA_LOCALES[code]` | 树状对象，键为点路径；`SUPPORTED = ["zh-CN","en"]`（i18n.js:15） |
| 启动注入 / 清单维护 | i18n.js:154-169；app.js:12437-12438 | `hydrate()`：有桥则读磁盘 `i18n.lang` 作**种子**（本地优先，本地有值不覆盖）→ `applyStatic()`。清单：`python scripts/scan_ui_strings.py` → 覆盖 [../i18n-inventory.md](../i18n-inventory.md)；自测 `node scripts/i18n_selftest.js`；规范见 [../../conventions/i18n.md](../../conventions/i18n.md) §3/§5/§6 |

### 2.9 快捷键总表（全库 `keydown`/`keyup` 穷举）

| 键位 | 上下文 / 前置条件 | 行为 | 触发位置 |
|---|---|---|---|
| `Ctrl+=` / `Ctrl++` | **全局，无目标过滤** | 界面缩放 +0.1（夹在 0.8–1.5） | app.js:12204-12209 |
| `Ctrl+-` | 全局，无目标过滤 | 界面缩放 −0.1 | app.js:12204-12211 |
| `Ctrl+0` | 全局，无目标过滤 | 缩放复位 100% | app.js:12204-12215 |
| `Ctrl+K` | 全局（`preventDefault` 不判焦点） | 聚焦顶栏搜索框 | toolbar-search.js:281-286 |
| `Alt+←` / `Alt+→` | 全局 | 后退 / 前进 | app.js:12402-12410 |
| `F2` | **捕获阶段**；排除 `INPUT/TEXTAREA/SELECT`；当前无任何可见 `.-modal`；文件树已有选中项 | 打开重命名（文件或目录） | file-tree.js:445-465 |
| `Esc` | 全局 | 关闭「文件」菜单 | app.js:12105-12107 |
| `Esc` | 全局 | 隐藏文件树右键菜单 | app.js:698-700 |
| `Esc` | 全局 | 隐藏色块右键菜单 | app.js:10480-10482 |
| `Esc` | 画笔（刷子）激活时 | 取消画笔 | app.js:10749-10751 |
| `Esc` | 取色面板可见时 | 取消取色 | app.js:10323-10327 |
| `Esc` | 块编辑模式中 | 退出块编辑 | edit-handler.js:1650-1655 |
| `Esc` | KP 右键菜单 / 链接右键菜单可见 | 隐藏菜单 | kp-context-menu.js:66-68；link-context-menu.js:263-265 |
| `Esc` | 焦点在搜索框内 | 关结果面板并失焦 | toolbar-search.js:269-272 |
| `Esc` | 文件树重命名/新建输入框内 | 取消 | file-tree.js:295-297 |
| `Esc` | 链接「添加目标」输入框内 | 隐藏目标建议 | app.js:5303-5305 |
| `Enter` / `Space` | 焦点在搜索范围开关（`role="switch"`） | 翻转「全库 ⇄ 文件」 | toolbar-search.js:258-263 |
| `Enter` | 搜索框内 | 搜索 | toolbar-search.js:265-268 |
| `Shift+Enter` | 搜索框内 | **仅当前文件**搜索 | toolbar-search.js:268 |
| `Enter` | 取色面板 hex 输入框内 | 等同「确定」 | app.js:10309-10311 |
| `Enter` | KP 新建标签输入框内 | 等同「添加」 | app.js:4262-4267 |
| `Enter` | 链接「添加目标」输入框内 | 添加目标 | app.js:5298-5302 |
| `Enter` | 文件树新建/重命名输入框内 | 提交 | file-tree.js:291-298 |
| `Enter` | 图片名称编辑 input 内 | 提交 alt | edit-handler.js:1291-1296 |
| `↑` / `↓` | **仅当**：无修饰键；`#preview` 非 contentEditable；焦点不在 contenteditable / `INPUT`/`TEXTAREA`/`SELECT` / `#file-tree` / `.-modal`；视图模式为源码·预览·分栏之一 | 滚动对应面板 96px | app.js:7011-7037 |
| `↑↓←→` | 焦点在源码编辑器 `.-line-content` 内 | 跨行/跨行首末光标移动（每行是独立 contenteditable，浏览器无法跨行） | app.js:7205-7288 |
| `Ctrl+Z` / `Ctrl+Y` / `Ctrl+Shift+Z` | 源码编辑器行内 | 快照式撤销 / 重做 | app.js:7213-7222 |
| `Ctrl+Z` / `Ctrl+Y` / `Ctrl+Shift+Z` | 预览区，且编辑模式开、视图非源码 | AST 管线撤销 / 重做 | edit-handler.js:628-645 |
| `Backspace`@行首 / `Delete`@行末 | 源码编辑器行内 | 行合并（并入上一行 / 下一行） | app.js:7290-7336 |
| `Enter` | 源码编辑器行内 | 拆行；光标在标题前缀末尾时改为行前插空行 | app.js:7337-7378 |
| `↑↓←→` | 预览区，编辑模式开、非 IME 组合、非图片名编辑 | AST 光标同步（跳过不可编辑块） | edit-handler.js:762-800+ |

**已知缺失 / 不生效**：

1. **`Ctrl+B` / `Ctrl+I` 没有实现**：只在格式栏 tooltip 里声称（index.html:153-154；zh-CN.js:593-594）。全库 `ctrlKey/metaKey` 分支仅上表 5 类，无 `b`/`i` 判定。
2. **`Ctrl+S`（保存）未实现**：无任何处理器（保存走编辑后的自动写回链路）。
3. `#edit-mode-toggle`（`role="switch"`）只绑 `click`（app.js:12453-12462），**无 keydown**——对 `<div>` 浏览器不会因 Enter/Space 合成 click，故键盘不可切换该开关。
4. `↑/↓` 的滚动劫持**会抢掉原生行为**：只要满足前置条件即 `preventDefault()`（app.js:7035），即便面板已到边界也不再滚动父容器。

## 3. 交互流程

**3.1 打开 → 改一项 → 关闭**：`#btn-settings` click → `openModal()`（graph-settings.js:851-857）→ 注入页签与当前页内容 → 用户拖 range：`input` + `change` 双事件都触发同一个 handler（graph-settings.js:842-843；display-settings.js:319-320）→ `save({key:val})` → ① 写 `localStorage` ② 去抖 280ms 排一次磁盘写 ③ `notifyChange()`：同步表单 + 刷新示例图预览 + 通知订阅方（graph-settings.js:220-228、286-290）→ 关闭时再无条件 `persistToDisk()`（graph-settings.js:884-888）。

**3.2 切页签**：点 `[data-settings-tab]` → `setSettingsTab(tab)`（graph-settings.js:777-785）：**整页重建**（`tabsEl.innerHTML` + `bodyEl.innerHTML`）→ 按页签重新绑定表单 → 2D/3D 额外 `bindPreviewResize()` + 建预览引擎。

**3.3 切语言**：`#display-language` change（display-settings.js:350-358）→ `MemoriaI18n.setLang(code)` → ① 写本地 ② 排磁盘写 ③ `applyStatic()` 全文档刷新 ④ `dispatchEvent("memoria:langchange")` ⑤ 逐个执行 `_refreshFns` ⑥ `applyAll()` 重算字体栈优先级 ⑦ 最后设置弹窗自身调 `rerenderCurrentTab()` 重绘（display-settings.js:352-356）——故设置窗内文案立即变。

**3.4 恢复默认**：`#settings-reset` click（graph-settings.js:953-956）→ `reset()`（清理图谱键、侧栏分栏键，重置检查设置并排盘）→ `setSettingsTab(settingsTab)` 重绘当前页。若当前页是「显示」或「检索」，**看起来点了没反应**（它们不在重置范围内）。

## 4. i18n key 前缀

键在 `i18n/zh-CN.js` 与 `i18n/en.js` 成对维护；本轮涉及的前缀：

| 前缀 | 覆盖 | 代表键（zh-CN.js 行号） |
|---|---|---|
| `settings.` | 设置弹窗骨架与页签 | `settings.tab.{graph2d,graph3d,groups,search,check,view}`（642-649）、`settings.reset`（650）、`settings.configPath`（651） |
| `settings.display.*` | 「显示」页各项与说明 | `langGroup/langLabel/langNote`（653-655）、`text/fontNote/fontSize/fontDefault`（656-659）、`uiScaleGroup/uiScaleNote/uiScale/uiScaleHint/resetScale`（660-664）、**2026-09-23 追加 5 键** `fontLangNote/fontSlotDefault/fontBrandLabel/fontBrandDefault/fontBrandNote`（**文末 `Object.assign` 块** ⇒ 上方行号零漂移：zh-CN.js:1630-1634、en.js:1731-1735） |
| `graph.settings.*` | 2D/3D/节点群三页 + 预览列 | `nodeLabel.*`（941-946）、`layout.*`（947-964）、`style.*`、`groups.*`、`preview.*` |
| `graph.labelModes.*` / `graph.sample.*` | 标签模式选项 / 示例图节点文案 | graph-label.js:8-11；zh-CN.js:928-932 |
| `search.settings.*` / `check.settings.*` | 「检索」页 / 「检查」页 | `search.settings.{heading,noteMain,enableEmbedding,noteEmbedding,bodyLocate,noteBodyLocate}`；`check.settings.{heading,noteMain,interval,enabled,noteOff,off,seconds,minutes}`（746-755） |
| `langs.*` / `modal.settings` / `common.close` / `dialog.closeTitle` | 语言自述名、弹窗标题与按钮 | `langs."zh-CN"` / `langs.en`（420）；640；index.html:290、296-298 |

完整清单与未迁移行登记规则见 [../i18n-inventory.md](../i18n-inventory.md)；语言系统契约见 [../../conventions/i18n.md](../../conventions/i18n.md)。

## 5. 边界与已知坑

1. **「四页」是错的**：设置是 **7 个具名页签**（2D / 3D / 节点群 / 检索 / 检查 / 显示 / **对话**），且「显示」在第 6 位、「对话」在最后（graph-settings.js:789-799）。**不存在「高级选项」区**。
2. **页签不落盘**：`settingsTab` 是模块内变量（graph-settings.js:111），重开应用回到 2D 图谱——集成方不要假设"上次打开的页"。
3. **「恢复默认」范围小于直觉**：只覆盖图谱、侧栏分栏、检查（graph-settings.js:230-241）。显示与检索**不重置**；`MemoriaSearchSettings.reset()` 虽有实现但**无任何调用点**（search-settings.js:139-149）。
4. **设置弹窗不响应 Esc**，也没有"同时只开一个弹窗"的中央约束（弹窗各自管 `hidden`）。
5. **语言切换不是全量重绘**：只有 `data-i18n*` 静态节点 + 3 个注册了 `addRefresh` 的区域会更新（app.js:12440-12444、kb-check.js:657、kb-agent.js:198）。已渲染的 KP 列表、状态栏常规统计、标签页等会**停留在旧语言**，直到各自下次重绘（按需生成的浮层如右键菜单则在下次打开时即用新语言）。
6. **`memoria:langchange` 是死事件**：i18n.js:123 派发它，但全库无监听者（实际刷新靠 `addRefresh` 回调列表）。外部宿主若要联动，只能监听它或自行轮询 `currentLang()`。
7. **缩放与 `Ctrl+K` 快捷键都无目标过滤**：`Ctrl+=/-/0` 在输入框内同样生效（app.js:12203-12216 未判 `e.target`），会连带改变弹窗尺寸；`Ctrl+K` 同样无条件 `preventDefault` 并抢焦点到顶栏搜索框（toolbar-search.js:281-286）。
8. **`Ctrl+B` / `Ctrl+I` 只存在于文案**（tooltip）中，无按键实现；`Ctrl+S` 亦无。
9. **`F2` 有全局互斥但只检查弹窗**：存在任一可见 `.-modal` 即不劫持（file-tree.js:453-457）；但**不检查**取色面板、色块菜单等非 `.-modal` 浮层。
10. **语言切换不改 md 正文，也不改壳端原生对话框标题**（pywebview_host.py:152/171/194；pyqt6_host.py:55/65/74 硬编码中文），也不改窗口标题 `Memoria v{版本}`（window-chrome.js:305，与 i18n 无关）。
11. **两处"看起来没生效"的正常现象**：检索页开关要到**下次检索**才反映（toolbar-search.js:151）；检查页改间隔后仅在下次定时点或重启定时器时体现（check-settings.js:134-146）。
12. **滑块拖动的落盘节奏**：拖动期间 `input` 事件高频触发 `save()`，本地写即时、磁盘写去抖 280ms（display-settings.js:183-189；graph-settings.js:148-154），关闭弹窗时再兜底一次全量写（graph-settings.js:887）。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 设置弹窗结构 / 尺寸 / 布局 grid | index.html:285-301；app.css:439-447、526-578 |
| 入口 / 打开 / 关闭 / 恢复默认 / 拖动 / 路径提示 | graph-settings.js:950、851-857、884-889、953-961、859-882；app.js:12560-12624 |
| 页签清单与整页重建 | graph-settings.js:765-785、786-818、111 |
| 显示页渲染 / 绑定 / 默认值与范围 / 持久化 | display-settings.js:250-360、11-18、27-31、183-222 |
| 字号、缩放与字体的应用范围 | display-settings.js:137-181 |
| 缩放快捷键 | app.js:12201-12217 |
| 图谱设置默认值 / 载入 / 存盘 / 侧栏分栏比例 | graph-settings.js:11-46、143-176、220-228、338-359、891-947 |
| 2D/3D/节点群页渲染与范围 | graph-settings.js:504-605、629-654 |
| 示例图 / 预览列 / 预览高度 | graph-settings.js:50-109、607-620、670-763、479-491 |
| 节点标签模式可用性 | graph-label.js:7-12、26-40 |
| 检索设置（默认值 / 派生 searchModes / 落盘） | search-settings.js:19-27、99-135、153-183、249-311 |
| 检查设置（选项集 / 归一 / 定时器） | check-settings.js:8-13、44-57、59-71、111-146、160-223 |
| i18n 引擎（t / 回退 / 填充 / applyStatic / setLang / hydrate） | i18n.js:55-78、66-71、91-115、117-135、154-169 |
| `data-i18n` / `data-i18n-attr` 用例与语言包 | index.html:44、47、77、87-90、100-102、146；i18n/zh-CN.js:420、633-659；i18n.js:15 |
| 语言切换的刷新订阅点 / 后端 check 消息本地化 | app.js:12437-12445、258-268；kb-check.js:656-665、59-62；kb-agent.js:198 |
| 快捷键：源码编辑器 / 方向键滚面板 / 预览区 / 树输入框 | app.js:7205-7380、7011-7037；edit-handler.js:628-645、762-800、1650-1655、1291-1296；file-tree.js:437-467、291-299 |
| 快捷键：Alt+←/→、Ctrl+K、各 Esc 关闭浮层 | app.js:12402-12410、698-700、10323-10327、10480-10482、10749-10751、12105-12107；toolbar-search.js:258-286；kp-context-menu.js:66-68；link-context-menu.js:263-265 |
| 壳端原生对话框标题（硬编码中文） | app/shell/pywebview_host.py:152、171、194；app/shell/pyqt6_host.py:55、65、74 |

## 7. 未证实 / 待确认

- ⚠️ 待确认（未能取证）：`uiScale` 对**非 rem 尺寸**绘制物（Three.js 画布、MathJax CHTML、图片灯箱）的实际观感影响未在真实窗口验证；代码只保证根字号与 `resize` 事件。
- ⚠️ 待确认（未能取证）：`i18n/en.js` 与 `zh-CN.js` 的键是否**逐键对齐**（本次只抽样比对，未做机械 diff）。
- ⚠️ 待确认（未能取证）：设置页签按钮只有 `role="tab"`，未见 `aria-selected`/`aria-controls`/`tabpanel` 关联（graph-settings.js:789-799），屏幕阅读器表现未验证。
- ⚠️ 待确认（未能取证）：`#edit-mode-toggle` 键盘不可达为**代码推断**（无 keydown 绑定），未在真实窗口中按 Enter/Space 复验。
- ⚠️ 待确认（未能取证）：`F2` 在「取色面板打开」等非 `.-modal` 浮层下的行为（前置检查只看 `.-modal`），未真机验证。

## 2.22 设置 →「Agent」→「联网域名名单」（2026-09-24；设计见 [design/agent-capabilities.md §3.3](../../design/agent-capabilities.md)）

- **两行输入**（DOM 由 `js/net-settings.js` **自建后追加**进 `#agent-settings` ⇒ `index.html` 一行未改）：**允许抓取的域**（留空 = 不限）与**禁止抓取的域**（优先于允许）。`change`（失焦 / 回车）即保存，走既有 `agent_save_config` 浅合并（`fetch_allow_domains` / `fetch_deny_domains` 两个键），不碰同页其它设置。
- **归一化回显**：输入下方那行小字直接告诉你**最终生效的规则**（`允许：example.com、sub.example.org · 禁止：ads.example.com`）；写不出来的项会被忽略并**计数**（`已忽略 N 处无法识别的写法`，此时该行转成警示色）—— 不让"看起来配了其实没配"这种情况静默发生。可选写法：`example.com`（含全部子域）、`*.example.com`、`https://example.com/x`、`example.com:8443`、逗号 / 分号 / 空白分隔。
- **执行面**：`services/agent/web.py::WebClient._assert_domain()` 在**每一跳**（含重定向）**先于 DNS** 校验；被拒 ⇒ 工具结果带 **`WEB_BLOCKED_DOMAIN`**（与"地址类别"的 `WEB_BLOCKED_URL` 分开）。`web_search` 的结果里也会给"抓不了"的来源标一行提示（省掉"试抓→被拒→再试"的 token）。
- **读现状的 RPC**：`agent_net_domains`（`{allow, deny, allow_rules[], deny_rules[], ignored:{allow,deny}, code}`）—— 设置页与将来的「能力插件」面板共用同一份判据。
- **已接线的部分**（2026-09-24，AG61）：两句随包声明 `resources/agent-capabilities/web-search.json` / `web-fetch.json` + **工具级能力闸**（`tools/kb.py::_outbound_guard()`）⇒ `web_search` / `fetch_url` 可**逐库启停**；库级名单（本库 `allow` / `deny`）在**「能力插件」面板的 web-fetch 行「本库参数」**里就地编辑 —— **库级只能收紧**（`deny` 取并集 / `allow` 取交集，见 `agent-capabilities.md §3.3`）。N 线工作法（何时该查 / 抓完怎么落工作区 / 何时该停下问用户）已随包成一份**内置技能** `web-research`（`resources/agent-skills/**`，2026-09-24 AG62）。
- **仍未做**：`web_search` **本身不受名单内容约束** —— 检索在模型端点执行，我们只能在结果里标注"这条抓不了"。

## 2.23 设置 →「Agent」→「脚本工作区」（2026-09-24 AG63；设计见 [design/agent-capabilities.md §3.4](../../design/agent-capabilities.md)）

- **三行 + 一行回显**（DOM 由 `js/scratch-settings.js` **自建后追加**进 `#agent-settings`，与上面那两行同法 ⇒ `index.html` 只多一行 `<script>`）：**解释器路径**（留空 = 自动）、**允许使用发布包内置的解释器**（勾选框）、**单次执行超时（秒）**；`change`（失焦 / 回车）即保存，走既有 `agent_save_config` 浅合并（`script_interpreter` / `script_use_bundled` / `script_timeout_s` 三个键）。
- **回显"当前会用哪个"**：一行小字给出**解析结果 + 来源档**（`设置里指定` / `发布包内置` / `系统` / `未找到`），并顺带提示内置目录在不在、超时的允许区间（5–300 秒）。填了不存在的路径 ⇒ **照原样报错、不静默回落**（后端口径），该行转警示色 —— 免得"改了半天其实没生效"。
- **超时的边界**：前端只把**正数但越界**的值**夹到 5–300 秒**并提示"已夹到 N 秒"；**非数字 / ≤0 照原样报错并回滚显示**（写侧 `llm/config.py::_coerce_timeout` 只收正数、拒写时整份不落盘）—— 真正的 5–300 夹取发生在**执行时**（`scratch._clamp_timeout()`）：所以填 999 会被**存下**，跑的时候按 300 秒用（写 2 则按 5 秒）。
- **执行权不在这里**：脚本**不会自己跑** —— 只有人在对话栏的「工作区」面板点「运行」才会执行，且以当前用户身份运行（**不是沙箱**，面板常显那条警告）。设置页只决定"用哪个解释器 + 一次最长跑多久"。
- **读现状的 RPC**：`agent_script_settings`（`{interpreter, use_bundled, timeout_s, default_timeout_s, resolved:{path,source}, bundled_dir, bundled_name, error, code, limits}`）—— **不收 `kb_path`**：解释器是**机器级**设置，没开库也要能改；也**不并进** `agent_get_config`（那会推位 `ui.py` 中段锚点）。
- **仍未做**：`resources/python/` 的**随包内置解释器**本身尚未分发（`bundled_dir()` 今天恒为空 ⇒ 一律回落到系统解释器）；勾选框现在等价于"允许将来用内置的那一份"。
- **L4 取证（2026-09-24，真实进程 + 真配置读写层；配置文件用产品自己的 `MEMORIA_AGENT_CONFIG` 重定向到临时目录 ⇒ **不碰**用户的 `config/agent.json`）**：① 初始读回 `{timeout_s: 60, use_bundled: true, resolved: {path: D:\Python\python.EXE, source: system}, bundled_dir: ""}`；② 写三个键 ⇒ 磁盘**只有这三个键**且读回一致；③ **只写一个键** ⇒ 另一个键（30.0）保持 ⇒ 浅合并成立；④ 超时写 `999` ⇒ **原样存下**（写侧只校验正数）、执行期 `_clamp_timeout(999) = 300`（`2` 则夹到 `5`）⇒ 证实"5–300 的夹取在执行时"；⑤ 超时写 `0` ⇒ 写侧 `ConfigError` 拒写、**磁盘值未变** ⇒ fail-closed；⑥ 显式路径填不存在的目录 ⇒ `error` 有值 + `resolved.source="none"`（**不静默回落**），用户填的路径原样留在盘上；⑦ 清空路径 ⇒ 回 `system`。**未取证**：整套只在**进程内**跑，**没有浏览器/真机 UI 一轮**（DOM 装配与 `change` 保存未经人眼/真点击确认）。

## 2.24 设置 →「显示」→「性能」：预览池的智能替换（2026-09-24 AG64）

> **来源** = 人：「后台预加载的加载池需要有一个智能替换机制，我们给资源计算优先级……优先级最低的优先被替换，新入池的资源优先级都重新初始化……权重参数应该在设置内「性能」板块调整，显示计算公式，支持恢复默认」。
> **先说清是哪个池**：`app.js` 末尾那个**预览 DOM 缓存**（`Map<relPath, {frag, map, ast, version, fp, scrollTop, bytes, prerendered}>`）——「后台预加载」预渲染出来的条目就往它里面填。**不是**后端 `load_document` 的文档缓存（`document.py`，按 `(路径, mtime, size)` 键、仍是 FIFO 24 条，本轮**未动**）。

**版块内容**（都在同一个「性能」`<details>` 里）：

| 键 | 含义 | 默认 | 区间 |
|---|---|---|---|
| `previewCacheMax` | 池容量（最多缓存几个页签） | `8` | 1–32 |
| `previewCacheMaxLines` | **缓存行数上限**（超过就不建缓存条目） | `8000` | 200–200000 |
| `preloadMaxLines` | **预渲染行数上限**（超过就不预渲染） | `4000` | 200–200000 |
| `preloadMaxTabs` | **预渲染次数上限**（每次会话） | `8` | 1–64 |
| `perfTimeWeight` | 加载耗时权重 `w_t` | `1.0` | 0–5 |
| `perfFreqWeight` | 打开次数权重 `w_f` | `0.5` | 0–5 |
| `perfRecencyWeight` | 新鲜度权重 `w_r` | `0.6` | 0–5 |
| `perfSizeWeight` | 占用惩罚权重 `w_s` | `0.4` | 0–5 |
| `perfAgingWeight` | 老化权重 `w_a` | `0.05` | 0–5 |
| `perfHalfLifeH` | 新鲜度半衰期 `τ`（小时） | `12` | 0.5–168 |
| `perfAdmission` | 后台预加载要过「入场闸」 | 开 | — |

> **后三个键是 2026-09-24 从 `app.js` 的硬编码搬过来的**（AG65，来源 = 人真机反馈「切 AAA_Course 教材第 8 章预览很慢」）。原来的值是 **1200 行 / 4000 行 / 4 次**，代价如下（教材 `数字通信原理` 14 个 md 里 **8 个**永远进不了预渲染射程，恰好是最大的那 8 个）：
>
> | 文件 | 行数 | 原预渲染闸（1200） | 原缓存闸（4000） |
> |---|---|---|---|
> | 06 第6章 | 4694 | ✗ 从不预渲染 | ✗ **永不建缓存** |
> | **08 第8章** | **3983** | ✗ **从不预渲染** | ✓ 但只剩 17 行余量 |
> | 04 / 03 / 02 / 05 / 07 / 09 | 1325–2731 | ✗ 从不预渲染 | ✓ |
>
> 第 8 章还很重：**1134 个 `$$`（≈567 个块级公式）**、394 行表格、19 个 mermaid、13 张图、407 KB ⇒ 冷渲染是**数秒级**。**改动门槛后 `_preloadTried` 会一并清空并立即重排**（它是"试过就不再试"的清单，不清的话放宽门槛后什么都看不到）。

**公式**（面板上按**当前权重**显示，数字全部取自代码常量 ⇒ 显示的就是真正在算的那条）：

```
S(r) = w_t·T̂ + w_f·lg(1+打开次数) + w_r·2^(−闲置小时/τ) − w_s·占用比 − w_a·老化
T̂    = ln(1 + 毫秒/8000) / ln2    （0–1；8000 ms = AG51 实测的冷切 5–10 s，满量程）
占用比 = min(1, 估算字节 / 4 MiB)  （估算口径 = `app.js::_estimatePreviewBytes`）
老化   = min(距上次打开池内发生过的淘汰次数, 20)
```

**三条行为**：

- **淘汰**：取 `S` **最小**者（"优先级最低的优先被替换"）。**画像**（打开次数 / 最后打开时间 / 加载耗时 / 老化戳）按**路径**存活 —— 切走再切回本来就
  是一次"出池 → 入池"，若跟着清零，打开次数恒为 0、频次项就废了；**首次见到某路径**才叫"新入池"，那时按 `次数 0 / 闲置 0 / 老化 0 / 加载 = 本次实测` **重新初始化**。
- **入场闸**：人**正在看**的页签**永远直接入池**（它正被付代价）；只有**后台预渲染**那条投机路径要过闸 —— 与"当前分最低的那条"比分，赢了才换入，不够格就**就地丢掉**（不挤别人）。这是防"扫一遍目录把热页签全冲掉"（scan attack）的那道闸。
- **加载耗时**：冷加载（未命中）那一轮实测的切页签耗时，按 **EWMA(α=0.3)** 挂到画像上（一次异常快/慢不钉死）。后台预渲染的条目**没有**冷加载计时点 ⇒ 首轮取中性值，等它被真正打开一次就有了实测样本。

**模型来处**（都是既有研究，本仓不发明）：**GDSF** 的"老化/膨胀"（`− w_a·老化`，离散事件版）、**TinyLFU / W-TinyLFU** 的**入场闸**、**Hyperbolic caching** 的按**占用**折算（`− w_s·占用比`）。三者合起来治的正是 LRU 的两个病：**scan attack** 与**历史热点永生**。

**接口（只两个口）**：`window.MemoriaPreviewPolicy`（**纯函数**、无 DOM 依赖 ⇒ 可 `node` 单独跑分；文件头写了每个因子的出处）、`MemoriaApp.setPreviewCachePolicy(policy)`（设置 → app.js 的**唯一**门面，`applyAll()` 每次设置变更通告一次）；另有 `MemoriaApp.previewCacheScores()` 给**现场读数**用（同步函数，不走 RPC）：`{lastSwitchMs, lastSwitchHit, entries, enabled, evicts, limit, limits:{cacheLines, preloadLines, preloadTabs, preloadDone}, policy, rows:[{path, bytes, hits, idleH, loadMs, t, score}]}` —— `rows` 按分升序，**第一行就是下一个被替换的**。
**现场读数**（同版块内，等宽小字 + 「刷新读数」按钮）：最近一次切页签的**耗时**与**是否走了缓存搬回**、三个生效门槛、池内逐条（路径 / 分 / 次数 / 闲置小时 / 加载项）；另有**五行诊断**：**切页签阶段**（**全程**，各段增量 ms —— `stash` 切走时入池（含整树字节估算）/ `load` `load_document` 的 IPC + 后端解析 AST + sha256 / `editor` 页签 + **源码编辑器整篇填充** + 撤销栈 + 知识点列表 / **`rpEnd`** 到 `renderPreview` 返回为止（打在 `setViewMode` 内部）/ `render` `setViewMode` 完成 / `settle` 等同步渲染那一轮落定（**不等 MathJax**）/ `tail` 状态栏 + 图审计 + 搜索同步；读数侧两两相减 ⇒ `rpEnd` 就是用来把 `render` 那一段从中间切开的）、**切页签分段**（命中那次，各段增量 ms —— `attach` 搬运 / `static` 静态收尾（现在只做"**只在真变时才写 `contentEditable`**"）/ `wikilinks` · `bind` 两轮全量扫描 / `mermaid` 同步渲染 / `math` 排队 / `scroll` 写 `scrollTop` 的强制布局；**只在命中时显示**）、**切页签异步**（相对点击起点 ms —— `mathjax` 排版 promise 落定 / **`frame1`** 双 rAF 的第一个 = 渲染时机到了（它本身就晚 ⇒ **主线程被别的东西占着**）/ `paint` 双 rAF 的第二个 ≈ 含布局绘制的这一帧画完（`paint - frame1` = **帧自己的样式/布局/绘制**）；**它远大于同步分段是正常的**：真机读数里 `settle` 恒为 0 而 `paint` 晚于总耗时 ⇒ 那 ~1 s 在**浏览器侧的样式/布局/绘制**，不在我们的 JS 里）、**池占用（实测节点数）**（`N 条 / M 节点 / 文本 K 字符 ⇒ 估值 … · 活 DOM 区间 … · 若改存序列化 HTML 约 …；另含常驻 AST … 块` —— 节点数是遍历缓存子树**数出来的真数**，两档区间按每节点 100–200 B 与 20–40 B 折算），以及 **已清掉的过期投机预渲染：N 条**（见 §2.25 的两条使用规则）。刷新只换读数容器的 `innerHTML`（按钮在容器外 ⇒ 不会连带丢监听器）。
**读数的两个坑**：① 它只读**内存里的计数器**，**不会重新加载 JS** —— 改完前端代码必须**重启应用**再读，否则读到的是旧版本的行为；② 「预渲染配额 `N/8`」的 `N` 在**改门槛时被有意清零**（AG65：清 `_preloadTried` 让放宽后的章节重新有机会）⇒ `0/8` 不等于"从没跑过"，**「预渲染命中率 0%（a 中 / b 未中）」才是真信号**。
**另注（2026-09-24，窗口化渲染）**：**只读预览**现在只把「看得到的那一窗」放进 DOM（`app.js` 末尾 `memoriaPreviewWindow`；设计与三条入口见 `design/preview-render-pipeline.md §3.7 / §4 K4a`）—— 窗口外的块被摘走、原位留一个 `div.-pv-spacer` 占位块（高度由 JS 写死）⇒ 帧不再对整篇 30 万节点计价。**为什么不是 `content-visibility`**：那版当日落地也被读数否掉（`paint` 1833 → **1788 ms**，它只让浏览器"跳过"、节点仍全在 DOM 里）⇒ 已删。**已知限制（如实）**：① 原生 `Ctrl+F` 只能搜到**已渲染窗口**内的内容（K4c 补自带查找，人会说自己不用 `Ctrl+F`）；② 编辑模式**不窗口化**（光标与选区风险，见设计 §3.2 / R3）；③ 离屏块高度按估值 ⇒ 滚动条长度与"跳到很远的行"的落点可能偏（量过的块会记住真高，越用越准）；④ 拖滚条**松手才渲**（`scrollend`；普通滚动即时补）。
**策略模块缺席**（老发布包 / 脚本没加载）⇒ 四个门槛回落 `app.js` 里的兜底常量（8 / 4000 / 1200 / 4）、淘汰回落"按插入序逐出最旧"，**不会更差**。**落盘**：`display` 段这一组共 **13 个键**（原地 11 个 + §2.25 的 `navPredictor` / `navHalfLifeDays`），与字号/字体同一条 `save_ui_settings` 通道；「恢复默认」**只重置这一组**，不动字号 / 缩放 / 字体 / 语言 / 后台预加载开关。

**未取证（如实）**：① **无浏览器/真机一轮** —— 版块 DOM 装配、数值框失焦保存的手感、公式块与读数块在中英两种语序下的换行观感都未经真点击/人眼确认（本批算法侧有 `node` 真跑数值断言兜底）；② **命中率提升未测**：没有真实负载回放，"这样调权重到底快多少"没有数据，只有"该留哪些"的语义钉子；③ 后台预渲染条目的加载耗时首轮是中性值（见上），其"值不值得留"要等它被打开过一次才准；④ **放宽门槛后的实际切页签耗时未复测**（教材第 8 章那台机器上的读数要用户下次开应用看「刷新读数」）；⑤ 池占用那一行给的是**区间估算**（节点数是真数，但每节点字节数用的是经验区间）—— 真值要看 DevTools 堆快照，属 K3 未做部分。

## 2.25 设置 →「显示」→「性能」：**导航预测器**（2026-09-24 AG67；设计见 [design/preview-render-pipeline.md §3.5 / §3.6](../../design/preview-render-pipeline.md)）

**一句话**：这是「双重预渲染」的**第二层** —— 第一层是 §2.24 那个**页签级缓存池**（文件从页签栏关掉就立刻出池），第二层决定**接下来该把哪一份提前渲染好**。

- **两个新旋钮**：`navPredictor`（**关** / **马尔可夫链**，默认开）、`navHalfLifeDays`（跳转习惯半衰期，默认 14 天，0.5–365）；另有「**清空导航模型**」按钮（模型是可再生缓存，清了只损失一点预测质量）。
- **它怎么猜**：从**你主动的跳转**里学一张转移图（节点 = `文件` 或 `文件 + 知识点`），用**带重启的随机游走**（截断 PPR `q_{k+1} = α·e_c + (1−α)·q_k·P`，α=0.35、看 3 跳）算出"接下来最可能打开谁"，再**乘"打开它要花多久"**（`T̂`）⇒ 慢文件更值得提前做、快文件不值得抢 CPU。**投影回文件**时同一文件下的多个知识点**相加**（渲染的最小单位仍是文件）。
- **反污染**：只记**用户发起**的跳转。`#btn-refresh` 四连、写面同步这些**自动重开**（`skipNav:true`）、以及**预渲染自身**都不记 ⇒ 否则模型学的是自己的尾巴。同文件内的锚点跳转不算跨文件边。
- **冷启动**：样本不足 50 次 ⇒ 自动退化为「目录相邻优先」（同一章的上下节 > 隔一节 > 同目录）+ 最近打开过，同样乘 `T̂`；**一条都排不出**时保持原来的页签顺序（行为与没有预测器时一致）。
- **模型落在库内** `.memoria/cache/nav/transitions.jsonl`（一行一次跳转；`.memoria/cache/**` = **可再生缓存**，不进 manifest/sidecar、不被 `validate_kb` 审计）；写入走 `nav_model_write`（路径**写死**，前端不接触任意路径）、读取 `nav_model_read`；单次 ≤ 2 MiB、追加后 > 8 MiB 时前端自动**紧凑化重写**。
- **两条使用规则**（2026-09-24 人追加、同日落地）：① **预渲染只在「文件打开之后」做** —— 预览 / 源码 / 分栏**任一都算打开**，打开过程中不抢 CPU（`_preloadDocumentOpen()` 拦在调度与执行两个入口）；② **切换当前文件后按「新候选集」比对清理投机的预渲染产物**（避免滞留）—— 保留集 = 打开着的页签 ∪ 仍被预测的文件，**人真正打开过的一律不碰**，清掉的条数在读数里（`已清掉的过期投机预渲染：N 条`）。
- **它会把"你还没打开的那一章"也提前渲染**（这正是第二层的意义）：候选池 = 打开着的页签 ∪ 预测里**收益最高**的 2 个文件（`PRELOAD_PREDICT_MAX`）—— 这也是②要清的那种滞留的来源，所以两条规则是配套的。
- **读数行**（点「刷新读数」）：`导航模型：N 个节点 / M 条边 / 样本 K（≥50 才启用预测）· 预渲染命中率 P%（h 中 / m 未中）` —— 命中率就是"我们提前渲染的那些页签，后来你真的打开了几个"。
- **未取证**：① 真机上的命中率要积累一段时间才有意义；② 设计文档里"离线回放对比 页签顺序 / 目录相邻 / 一阶马尔可夫"那条验收**还没跑**；③ **KP 层的结构边**（侧车/图谱里的 `[[链接]]` 先验）与复习队列先验**尚未接入** —— 骨架已就位（节点键与文件投影已经在用）。
