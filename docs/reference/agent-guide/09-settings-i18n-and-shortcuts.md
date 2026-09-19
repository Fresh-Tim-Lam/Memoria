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
#settings-modal .-modal.hidden          index.html:319-363   宽 min(820px,96vw) / 高 min(680px,88vh)（app.css:777-785）
├── .-modal-header                      index.html:322-325   标题 modal.settings + ×（#settings-close）
├── #settings-tabs .-settings-tabs-wrap index.html:326       运行时注入页签按钮（graph-settings.js:789-799）
├── #settings-body .-modal-body.-settings-body index.html:327 运行时注入当前页签内容（graph-settings.js:801-843）
│   ├── .-settings-layout              app.css:916-923       grid：表单列 minmax(220px,1fr) + 预览列 minmax(260px,1.1fr)
│   │   ├── .-settings-form            app.css:929-934       表单列（纵向滚动，overscroll 隔离）
│   │   └── .-settings-preview-col     app.css:980-… / graph-settings.js:607-620  仅 2D/3D 页：示例图画布 + 竖直分栏柄
│   └── .-settings-layout--solo        app.css:925-927       单列（节点群 / 检索 / 检查 / 显示页）
├── #settings-body-agent               index.html:328-355   **静态体**（2026-09-19 新增）：「对话」页签的字段常驻此处，
│                                                         与上行动态体 `hidden` **互斥**（见 graph-settings.js:807-812）
└── #settings-config-path               index.html:356       底部一行：settings.configPath「设置保存在程序目录：{path}」（graph-settings.js:883-906）
└── .-modal-footer                      index.html:357-362   「恢复默认」#settings-reset + 「关闭」#settings-dismiss
```

页签集合是 **7 个具名页签**：`2D 图谱` / `3D 图谱` / `节点群` / `检索` / `检查` / `显示` / **`对话`**（graph-settings.js:789-799；文案 `settings.tab.*`，`settings.tab.agent` 追加在 zh-CN.js:1263-1265 / en.js:1347-1349）。**顺序即上表顺序**——「显示」在第 6 位、「对话」在最后（第 7 位），「检索」在「检查」之前。**「对话」是唯一的静态体页签**：内容（`#settings-body-agent`，端点/模型/密钥/超时/出网）常驻 index.html，由 `setSettingsTab()` 显隐，与其它页签的动态体 `#settings-body` **互斥**。

> ⚠️ 常见的四种归纳（显示 / 图谱 / 检索 / 检查）与实际不符：图谱被拆成 3 个独立页签（2D、3D、节点群）。另**当前不存在任何「高级选项」折叠区**：设置页只有具名页签，全前端检索「高级 / advanced」只命中链接编辑器的 `.-link-advanced`（app.css:2810-2820），不在设置窗口内。

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

渲染：`MemoriaDisplaySettings.renderSettingsBody()`（display-settings.js:167-199）；绑定：display-settings.js:201-239。三个 section：语言 / 文字 / 界面整体缩放。

| 项（i18n key） | 控件 / 选择器 | 取值与默认值 | 即时生效 | 落盘 |
|---|---|---|---|---|
| 界面语言 `settings.display.langLabel` | `<select id="display-language">`（display-settings.js:180-183）；选项文案 `langs.*` | `zh-CN` / `en`（i18n.js:15、zh-CN.js:420）；默认 `zh-CN`（i18n.js:14） | 是：`setLang()` → 刷新静态节点 + 派发刷新回调（i18n.js:117-135） | 本地 `localStorage["-i18n"]`（i18n.js:13、119）+ 磁盘 `i18n.lang`（i18n.js:142-151） |
| 字号 `settings.display.fontSize` | `input[type=range][data-display-setting="previewFontSize"]`（display-settings.js:189） | **12–28，步长 1，默认 14**（display-settings.js:16-17、11-12） | 是：`save()` → `applyAll()`（display-settings.js:140-145） | `localStorage["-display-settings"]` + 磁盘 `display.previewFontSize`（display-settings.js:114-118） |
| 缩放比例 `settings.display.uiScale` | `input[type=range][data-display-setting="uiScale"]`（display-settings.js:194） | **0.8–1.5，步长 0.1，默认 1.0**（display-settings.js:18-20） | 是（同上） | 同上，键 `display.uiScale` |
| 复位为 100% `settings.display.resetScale` | `<button id="display-ui-scale-reset">`（display-settings.js:196） | — | 是：`resetUiScale()`（display-settings.js:155-157、220-229） | 同上 |

**作用范围**：字号（display-settings.js:79-85）只写 `#preview` 的 `--preview-font-size` 与 `#editor` 的 `--editor-font-size` 两处内联变量，**两者同值**（源码区与分栏区一起变）；缩放（display-settings.js:87-98）设 `document.documentElement.style.fontSize = 16 × scale + "px"`（等于 1.0 时清空回默认），因样式表尺寸绝大多数是 `rem`，等价于整体等比缩放，改完**主动派发一次 `resize`**（display-settings.js:97）让侧栏按钮对齐、图谱容器等重算——**不是** `#app` 的 `zoom`。

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
| JS 侧 `T(key, params)` | 各模块取 `MemoriaI18n.t`（graph-settings.js:9、display-settings.js:169、check-settings.js:148-152） | 动态渲染内容**不走** `data-i18n`，两套机制互不覆盖 |
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

**3.1 打开 → 改一项 → 关闭**：`#btn-settings` click → `openModal()`（graph-settings.js:851-857）→ 注入页签与当前页内容 → 用户拖 range：`input` + `change` 双事件都触发同一个 handler（graph-settings.js:842-843；display-settings.js:217-218）→ `save({key:val})` → ① 写 `localStorage` ② 去抖 280ms 排一次磁盘写 ③ `notifyChange()`：同步表单 + 刷新示例图预览 + 通知订阅方（graph-settings.js:220-228、286-290）→ 关闭时再无条件 `persistToDisk()`（graph-settings.js:884-888）。

**3.2 切页签**：点 `[data-settings-tab]` → `setSettingsTab(tab)`（graph-settings.js:777-785）：**整页重建**（`tabsEl.innerHTML` + `bodyEl.innerHTML`）→ 按页签重新绑定表单 → 2D/3D 额外 `bindPreviewResize()` + 建预览引擎。

**3.3 切语言**：`#display-language` change（display-settings.js:230-238）→ `MemoriaI18n.setLang(code)` → ① 写本地 ② 排磁盘写 ③ `applyStatic()` 全文档刷新 ④ `dispatchEvent("memoria:langchange")` ⑤ 逐个执行 `_refreshFns` → 最后设置弹窗自身调 `rerenderCurrentTab()` 重绘（display-settings.js:234-236）——故设置窗内文案立即变。

**3.4 恢复默认**：`#settings-reset` click（graph-settings.js:953-956）→ `reset()`（清理图谱键、侧栏分栏键，重置检查设置并排盘）→ `setSettingsTab(settingsTab)` 重绘当前页。若当前页是「显示」或「检索」，**看起来点了没反应**（它们不在重置范围内）。

## 4. i18n key 前缀

键在 `i18n/zh-CN.js` 与 `i18n/en.js` 成对维护；本轮涉及的前缀：

| 前缀 | 覆盖 | 代表键（zh-CN.js 行号） |
|---|---|---|
| `settings.` | 设置弹窗骨架与页签 | `settings.tab.{graph2d,graph3d,groups,search,check,view}`（642-649）、`settings.reset`（650）、`settings.configPath`（651） |
| `settings.display.*` | 「显示」页各项与说明 | `langGroup/langLabel/langNote`（653-655）、`text/fontNote/fontSize/fontDefault`（656-659）、`uiScaleGroup/uiScaleNote/uiScale/uiScaleHint/resetScale`（660-664） |
| `graph.settings.*` | 2D/3D/节点群三页 + 预览列 | `nodeLabel.*`（941-946）、`layout.*`（947-964）、`style.*`、`groups.*`、`preview.*` |
| `graph.labelModes.*` / `graph.sample.*` | 标签模式选项 / 示例图节点文案 | graph-label.js:8-11；zh-CN.js:935-939 |
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
12. **滑块拖动的落盘节奏**：拖动期间 `input` 事件高频触发 `save()`，本地写即时、磁盘写去抖 280ms（display-settings.js:106-112；graph-settings.js:148-154），关闭弹窗时再兜底一次全量写（graph-settings.js:887）。

## 6. 代码锚点表

| 要点 | 锚点 |
|---|---|
| 设置弹窗结构 / 尺寸 / 布局 grid | index.html:285-301；app.css:445-453、551-603 |
| 入口 / 打开 / 关闭 / 恢复默认 / 拖动 / 路径提示 | graph-settings.js:950、851-857、884-889、953-961、859-882；app.js:12560-12624 |
| 页签清单与整页重建 | graph-settings.js:765-785、786-818、111 |
| 显示页渲染 / 绑定 / 默认值与范围 / 持久化 | display-settings.js:167-239、11-20、106-138 |
| 字号与缩放的应用范围 | display-settings.js:79-104 |
| 缩放快捷键 | app.js:12201-12217 |
| 图谱设置默认值 / 载入 / 存盘 / 侧栏分栏比例 | graph-settings.js:11-46、143-176、220-228、338-359、891-947 |
| 2D/3D/节点群页渲染与范围 | graph-settings.js:504-605、629-654 |
| 示例图 / 预览列 / 预览高度 | graph-settings.js:50-109、607-620、670-763、479-491 |
| 节点标签模式可用性 | graph-label.js:7-12、26-40 |
| 检索设置（默认值 / 派生 searchModes / 落盘） | search-settings.js:19-27、99-135、153-183、249-311 |
| 检查设置（选项集 / 归一 / 定时器） | check-settings.js:8-13、44-57、59-71、111-146、160-223 |
| i18n 引擎（t / 回退 / 填充 / applyStatic / setLang / hydrate） | i18n.js:55-78、66-71、91-115、117-135、154-169 |
| `data-i18n` / `data-i18n-attr` 用例与语言包 | index.html:44、47、77、87-90、100-102、146；i18n/zh-CN.js:420、640-666；i18n.js:15 |
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
