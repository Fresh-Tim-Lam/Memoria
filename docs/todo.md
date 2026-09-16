# Memoria 待办清单（整理版）

> 整理日期：2026-08-20。由原 to-dolist.md 与 dicussion.md 合并去重，按功能域归类；2026-08-22 追加文件树右键菜单（重命名/删除/新建）与粘贴换行条目；2026-08-29 追加 P04（右键文件夹「以 Memoria 打开」+ 打开前安全检查）；2026-08-30 docs 目录体系重构（standards/context → conventions/guides/reference + AGENT.md 现代分区）。
> 状态标记：✅ 已完成 / 🔄 进行中 / ⏳ 待做 / 💡 方向性（需再规格化）/ 🔴 Bug / ⬇️ 最低优先级
> **维护规范**：[conventions/ledger-maintenance.md](conventions/ledger-maintenance.md)（四类分区 K1 真开放 / K2 代码完成·验收未闭环 / K3 待评审 / K4 已收口、**证据锚必填**、收口判据、定期对账；2026-09-14 生效）。
> **台账现状**（2026-09-14 首轮对账）：11 条误开已收口、7 条描述与代码不符已修正、**5 条代码完成但真机验收未闭环**、1 条验证未闭环、2 条设计待评审 —— 明细见 §10.3 与 §12。
> **2026-09-15 新增 8 条取证登记**（来源：[agent-guide](reference/agent-guide/README.md) 首轮取证，逐条带 `文件:行号`）：C10 弹窗层级 / S06 搜索范围跨库残留 / E18 快捷键 tooltip 未实现 / E19 Mermaid 块丢行号锚点 / I06 导入入口双重绑定 / I07 图片后台静默删除 / P05 `_kb_root` 模块全局 / B8 构建可能覆盖未落盘编辑。

***

## 0. 当前进行中（焦点）

- 🔄 样式笔刷：预览模式涂抹后选区保持（用户反馈纯预览模式下应用样式后选区消失，分栏模式正常；harness 多次复现未果，待用户确认环境/操作细节后定位）；**K1 真开放·无修复证据**
- 🔄 样式笔刷：同行含公式涂抹混乱（**K2 验证未闭环**：映射修复已在 `app.js:9217-9218,10640`，无验证通过证据）
- 🔄 M5 桌面壳收尾：窗口原生动画/顶栏拖拽/圆角/最大化已达成；剩余图标与安装体验、更新通道
- ✅ 语言系统 i18n（中英语言包）【2026-09-14 对账：**候选清单已清零（K4）**；真机回归仍待用户执行】：①②完成（清单 + 规范）→ ③ 机制已落地（i18n.js + zh-CN/en 包 + 设置→显示即时切换 + 首批静态文案）→ ④ 整理语言包已收口：2026-09-03 已迁移「检查」功能链路（index.html 检查弹窗 / app.js 状态栏·角标·检查弹窗·图谱建边提示 / check-settings.js 设置→检查页）并落地后端检查消息 code+params 本地化（en `check.issue.<code>`，未知 code 回退中文；§5.1）；同日补齐相邻文案（图片管理/诊断/清理 `img.*`、图谱空态提示 `graph.hint.*`、共享「请先打开知识库」`app.openKbFirst`、检查相关 RPC 错误按 code 翻译）；link-context-menu.js 右键菜单已整文件接入 `menu.*`（含源码/预览「插入图片」对齐）；2026-09-04 edit-handler.js 编辑块工具栏已整文件接入 `edit.block.*`（块类型标签/语言/类型/符号/对齐/大小/名称工具、行内公式、图片名称开关、编辑模式切换提示，32 候选清零）；同日图谱/检索设置页整文件接入（graph-settings.js `graph.settings.*` + 示例图 `graph.sample.*`、graph-label.js `graph.labelModes.*`、search-settings.js `search.settings.*`，71 候选清零，设置示例图随语言重建）；2026-09-04 编辑块工具栏之取色器/画笔状态与自定义颜色管理已原位接入 `color.*`（8 键）+ `brush.*`（11 键），候选清零该区段；此后剩余 UI 文案迁移改走「app.js 拆分专项」（下条：随拆分同步 i18n，当前 app.js 候选 0 —— app.js 界面文案清零达成，i18n-inventory 为空清单）
- ✅ 演示截图迁出 docs → `resources/screenshots/`（2026-09-03，git mv 保历史；README 双语引用 14 处同步）；新增 conventions/readme-i18n.md（README.md↔README.cn.md 双语 + 截图收录/存放维护规范）；docs 不再存截图类二进制资源
- 🔄 app.js 拆分瘦身（先拆分、随拆分同步 i18n）：已抽 `js/import-flow.js`（导入）、`js/toolbar-search.js`（搜索）、`js/image-tools.js`（图片）、`js/kb-check.js`（KB 检查/徽标/静默检查）、`js/file-tree.js`（文件树：渲染/展开/右键新建·重命名·删除/切换，复用 app.js 通用右键浮层与确认弹窗，新增 tree.* 20 键）；app.js →10.9k 行、i18n 候选 496→0；`window.MemoriaApp` 门面承载 app 私有服务。2026-09-04 取色器/画笔/自定义颜色区段文案已原位 `t()` 化（color.*/brush.*），结构抽取仍待 editor-styles 层（画笔与编辑格式管线耦合、引用保留在 app.js 的 FT_MENU_ID 浮层）；同日图谱侧栏分组页签 + 构建/加载状态接入 `graph.*`（graph.group.*/graph.build.*/graph.loadFailed）；又同日应用启动/KB 开关/状态栏/文件打开与加载/标签关闭/文件状态统计接入 `app.*`（status.kbLoaded/kbOpened/kbEmpty/kbEmptyDetail/waitingBackend、loading/loadFailed/listFailed/apiUnavailable、stat.kpLines/errors/warnings/sidecar）；再同日预览加载/自检/链接一致性提示/KP 列表空态接入 `preview.*`（loadNotReady/rendering/renderFail/okDetail/failDetail/brief/incomplete/selfcheck/linkAuditHint，TeX 摘要复用 preview.math.texError）与 `app.kpList*`（SelectFile/NoKp/OnlyProposals/Hint）；配置文件弹窗「链接审计/匹配」区段接入 `cfg.*` 51 键 + `common.delete`，`cfg.` 前缀登记；同区「链接 Tab/待确认 Tab/概要·校验/KP 弹窗 Tab/忽略·刷新状态」追加 `cfg.*` 43 键（linktab/pending/config/panel.tabs/match.scanFail），7 函数接入；KP 弹窗「边」页接入 `cfg.edge.*` 34 键（4 函数）；KP 弹窗「范围编辑器+标题+标识/描述」接入 `cfg.range/cfg.kpModal/cfg.kpIdent` 19 键（保存按钮复用 common.ok）；KP 弹窗「Tag/别名/描述候选编辑器」接入 `cfg.kpTag/cfg.chip` 22 键（9 函数）；「aux/建议/合并 + 待确认直接确认·全部确认 + 跳转/确认跳转」接入 `cfg.aux/cfg.confirm/cfg.jump` 29 键（7 函数）；链接编辑器主体区接入 `cfg.linkEdge/cfg.linkSave/cfg.linkMeta` 36 键（7 函数）；链接保存/扫描/挂接/移除/删除/点击解析/预览链接 title/图谱提示流程接入 `cfg.linkSave(+15)/cfg.match(+16)/cfg.linkOps/cfg.linkClick` 51 键（14 函数）；样式错误消息+格式化状态+剪贴板/粘贴接入 `cfg.style/cfg.clip` 19 键（24 处替换）；扫描器规则扩展剔除自定义 `log("TAG",…)` 开发日志行；KP 定位辅助预览接入 `cfg.assist` 8 键（ellipsis 上/下模板、范围预览、预览模式 aria、源码/Markdown、rangeError、默认名）；KP id 迁移/保存/删除/range 校验流接入 `cfg.kpSave` 23 键（rename/delete confirm 含换行、迁移状态、各校验 detail）；收尾清零（errorLabel map→cfg.kpErr 4 键、匹配行定位→cfg.match located/substringBlocked/checkboxHint、「请先打开文件」复用 app.openFileFirst）—— **app.js 界面文案候选清零（0 行）达成，i18n-inventory 为空清单**；真机回归待用户执行（导入/搜索/图片/检查/文件树/语言切换/画笔取色/图谱构建/文件打开/预览异常与空态/配置弹窗链接·待确认 Tab/KP 弹窗各页/待确认确认流/跳转/链接编辑器全流程/样式·粘贴）
- ✅ 0.3.0 导入体系（M0–M7 全 ☑）：场景/契约见 [docs/reference/import-spec.md](reference/import-spec.md)，模块化计划见 [docs/reference/import-plan.md](reference/import-plan.md)。统一导入向导（三源卡→预览→冲突决策→复制反馈 JSON/MD→结果）+ Agent 整理提示词事实源已随 M7 落地；2026-09-05 GUI 真机回归用 browseragent × `docs/example/import-test/_harness_import.py`（KB=empty3，--fresh）跑通：三类源 × {新建/幂等/冲突(跳过·覆盖·重命名)} 全 ✓ + 磁盘结构核对（md/sidecar/图谱节点与边），记录与遗留观察见 import-plan M6.2 回归记录；导入工具栏并入「文件」下拉（打开/导入/导出预留）

***

## 1. 配置窗口（合并「知识点解析」+「审核」）— 核心大项

| ID  | 任务                                                                                  | 状态 |
| --- | ----------------------------------------------------------------------------------- | -- |
| C01 | 配置入口：点击「配置」呼出配置窗口                                                                   | ✅ K4（2026-09-14 对账：`index.html:129` 配置按钮 + `app.js:12207` openConfigModal） |
| C02 | 配置窗内左侧文件树 + 「当前文件」快速定位（**2026-09-14 对账：现状无** —— 配置窗仅 kp/links/pending 三 Tab）                                               | 🔄 K1（文件树与点击切换已在；配置窗内无文件树/无「当前文件」按钮） |
| C03 | 右侧三段式布局：顶栏 `id + description`；下方 tag 分「已有（上）/候选灰色（下）」，移动为**逐 chip 点击**（原「多选上移/下移」**未实现**），支持手动创建、「系统建议」重新推荐 | 🔄 K1（上下分区/逐 chip 切换/手动创建/系统建议已在，`app.js:4008-4091,4121`；多选批量未实现） |
| C04 | UI 风格：右侧编辑框去掉外框包裹与框间隔，统一左栏文件树风格                                                     | 🔄 K1（列表项已扁平化去外框，`app.css:1637-1646`；「统一左栏文件树风格」无专门证据） |
| C05 | 数据模型改造：知识点为最小单位（唯一 id + tags 上下栏管理），文件只是容器                                          | ✅ K4（2026-09-14 对账：`docs/reference/architecture.md:88` KP 模型 + `kp_rename.py:28-69`） |
| C06 | 配置页右侧顺序：文件描述 → 知识点配置（点击下拉展开/再点收回）→ 链接管理（**2026-09-14 对账：现状与描述不符** —— 实为 kp/links/pending 三 Tab，KP 配置走独立弹窗，见 `app.js:2272,3020-3030`）                | ⏳  |
| C07 | 修改 id 自动更新所有相关链接；修改 tag 不破坏链接                                                       | ✅ K4（2026-09-14 对账：`kp_rename.py:28-69` 正文链接改写 + sidecar edges；`ui.py:342`） |
| C08 | 自动解析：识别库内/库外知识点 → 推荐创建 KP 单元并解析跳转锚点（**已实现**：`heading_proposals.py`/`mention_proposals.py`/`definition_proposals.py`）；识别可建边文本 → 推荐创建（**2026-09-14 对账：`disabled` 占位，未实现**，见 `app.js:2180-2197`）                       | 🔄 K1（KP 推荐已实现；「可建边文本→推荐创建」为 `disabled` 占位） |
| C09 | 高级选项 → 设置内容完善（**2026-09-14 对账 ❓：设置页为 6 个具名 Tab，无「高级选项」区，原描述不足以定位**）                                                                       | ⏳  |
| C10 | 弹窗层级混乱：`.-modal`（z-index **1000**）低于搜索面板 9000 / 右键菜单 10050 / 颜色选择器 20000 / toast 30000，弹窗可被浮层遮挡 | 🔴 K1（2026-09-15 取证：`app.css:4125` vs `2096`；来源 [agent-guide/01](reference/agent-guide/01-shell-and-layout.md)） |

***

## 2. 链接系统

| ID  | 任务                                                               | 状态 |
| --- | ---------------------------------------------------------------- | -- |
| L01 | 选中文本右键 → 创建链接窗口：智能推荐（**2026-09-14 对账：该区块为 `disabled` 占位**，`app.js:5197-5208`）+ 加号手动添加（输入 id/tag 匹配）+ 多选定向                | 🔄 K1（创建窗/多选定向/手动 id-tag 搜索已实现，`app.js:5134,5189-5195,5238-5259`；智能推荐为占位） |
| L02 | 右键虚链接/链接 → 编辑链接窗口：修改 id/tag 重新匹配、未定向虚链接匹配定向（多选）、删除某链接；全部删除则该跳转消失 | ✅ K4（2026-09-14 对账：`link-context-menu.js:106-160` + `app.js:5512/5563/5238-5276` + `ui.py:479`） |
| L03 | 公式也可以作为链接被点击（**2026-09-14 对账：未实现** —— 解析器视 `[[…]]` 为纯文本、公式为独立原子节点，`parser.js:222-235` / `renderer.js:385-391,421-427`）                                                     | ⏳  |
| L04 | `[[**aaa**]]` 类链接预览错误（\*\*aaa 无法选中创建链接）                          | 🔴 |
| L05 | http 链接点击行为完善（**2026-09-14 对账：未实现** —— 预览仅拦截库内 `.md` 且显式排除 `https?`，`app.js:6271-6326`）                                                    | ⏳  |

***

## 3. 检索引擎

| ID  | 任务                                                      | 状态 |
| --- | ------------------------------------------------------- | -- |
| S01 | 搜索/匹配功能封装成统一内核（系统多处使用推荐匹配）                              | ✅ K4（2026-09-14 对账：`services/search_kernel.py:38-133` 统一 `search()`（lexical/semantic/RRF）+ `ui.py:241-258`） |
| S02 | R17 SearchKernel v2：双向生长汇合检索（查询侧语义扩张 + 库侧沿图/标签生长，按路径计分）（**2026-09-14 对账：未实现** —— `retrieval_fusion.py:149-161` 有 `graph_hits` 通道但检索未接线） | 💡 |
| S03 | R16 检索反馈循环·库内模型（点击/有用无用学习，存 `.memoria/`，本地离线可删）（**2026-09-14 对账：未实现** —— 无 `search_feedback.py`，`ui.py` 无反馈 RPC）         | ⏳  |
| S04 | R04 智能链接推荐（**2026-09-14 对账：Lexical 版已实现** —— `services/link_relevance.py` + `ui.py:626`；**LLM 提议层未实现** —— `model_router.py:17-18` 为空槽）               | 🔄 K1（Lexical 推荐已在；缺 LLM 提议层） |
| S05 | R05 公式级语义检索（**2026-09-14 对账：公式归一化已并入语义检索** —— `services/text_normalize.py:11`；**独立公式索引/AST 未做**）                      | 🔄 K1（公式归一化已并入语义检索；独立公式索引/AST 未做） |
| S06 | 搜索范围偏好跨库残留：上次停在「文件」时，新开库且未打开文件即搜索 → 直接报 `app.openFileFirst`，而范围按钮却是 disabled 态 | 🔴 K1（2026-09-15：`app.js:47`、`toolbar-search.js:143-146`；来源 [agent-guide/07](reference/agent-guide/07-search-and-images.md)） |

***

## 4. 图谱

| ID  | 任务                                                                                                        | 状态 |
| --- | --------------------------------------------------------------------------------------------------------- | -- |
| G01 | R07 图谱推理·新边提议（**2026-09-14 对账：未实现** —— 无 `suggest_edge`/提议 RPC；需先定边属性专章；建议边不自动写入，用户逐条采纳/忽略）；图谱边类型的完善，整理现实生活中，人们阅读、学习或者复习场景下，看到某个文字想要“跳转”有什么类型，或者说知识点之间的边类型 | 🔄 K1（边类型体系 `graph/edge_types.py:10-29` + 手动建边 `ui.py:775` 已实现；新边提议未实现） |
| G02 | Bug：边抑制之后点击构建/刷新，图谱仍然显示该边                                                                                 | 🔴 |
| G03 | F03 增加新的力场范式方便图谱观看（由 G04 银河样式实现）                                                                        | ✅ |
| G04 | 图谱样式切换：新增「银河 Galaxy」视觉样式（星空星点渲染：亮度随连接度、径向光晕、深空底色、交互时焦点星点闪烁；布局仍为力导向，2D/3D 通用）+ 设置内样式修改 UI（光晕强度） | ✅ |

<br />

***

## 5. 编辑器 / 富文本

| ID  | 任务                                                                  | 状态 |
| --- | ------------------------------------------------------------------- | -- |
| E01 | R15 富文本 Markdown 编辑（**2026-09-14 对账：加粗/斜体/高亮/荧光笔/字色/Undo-Redo 已实现** —— `index.html:154-184`、`app.js:7196-7198`、`lexer.js:326-335`；**字号/上下标仅有语法层支持**，工具栏无入口） | 🔄 |
| E02 | 表格内部也可以编辑（同步编辑板块）（**2026-09-14 对账：未实现** —— 有「编辑表格/+行/+列」按钮但**无事件绑定、内容不写回**，`edit-handler.js:953-958,1451-1452`）                                                   | ⏳  |
| E03 | 编辑模式下修改链接的内容要自动处理                                                   | ⏳  |
| E04 | 双击公式进入公式编辑区，工具栏切换到公式栏（行内公式 enterInlineMathEditMode + 块级 math_block 符号面板） | ✅ |
| E05 | 阅读区选中文本后通过工具栏应用/编辑样式                                                | ✅ K4（2026-09-14 对账：预览区选中经工具栏应用样式已实现，`app.js:9703-9723,10013-10045,10810-10824`） |
| E06 | 文本批处理按钮：`\(` `\)` → `$`、`\[` `\]` → `$$`                            | ⏳  |
| E07 | Bug：无法复制                                                            | 🔴 |
| E08 | Bug：分栏状态下文本编辑功能检验不通过                                                | 🔴 |
| E09 | U04 预览/源码切换定位到对应位置（**已实现** —— `app.js:1578-1668`）；分栏可配置是否自动定位（**2026-09-14 对账：无该配置项**）                               | 🔄 K1（切换定位已实现；分栏自动定位配置缺） |
| E10 | U08 设置内部数值范围过小，需扩大（**2026-09-14 对账 ❓：U08 未指明具体控件** —— 字号 12-28 / 缩放 0.8-1.5 / labelMaxLen 4-20 等均无从对应，需澄清所指）                                                  | ⏳  |
| E11 | U09 右键创建知识点时自动剔除「3.3.4.2」类编号前缀（**2026-09-14 对账：未实现** —— `app.js:11196-11207` 取首行 trim 后直接截断，无编号剥离）                                      | ⏳  |
| E12 | F04 IDE 缩放功能                                                        | ✅ K4（2026-09-14 对账：`display-settings.js:11-19` 整体缩放 + `app.js:12170-12186` 快捷键） |
| E13 | Bug：预览区域粘贴时换行符被忽略，导致代码格式错误                                          | 🔴 |
| E14 | 完善源码-预览-分栏区域的复制粘贴功能（**粘贴换行处理已实现** —— `app.js:7411-7511,7513-7538,9641-9673`；**「复制」与格式保持未做** —— 无 copy 监听，现仅写 text/plain） | 🔄  |
| E15 | 源码编辑器多行粘贴换行丢失                                                       | ✅  |
| E16 | 源码编辑器快照式撤销/重做（覆盖输入/Enter/合并删除/粘贴，Ctrl+Z/Y）                          | ✅  |
| E17 | 新建文件缺 .md 后缀自动补齐（与前端提示一致）                                           | ✅  |
| E18 | 工具栏 tooltip 声称 `Ctrl+B` / `Ctrl+I`（及 `Ctrl+S`）实际未实现 | 🔴 K1（2026-09-15：`index.html:153-154`、`i18n/zh-CN.js:593-594`；全库无按键处理器；来源 [agent-guide/03](reference/agent-guide/03-editor-and-formatting.md)） |
| E19 | Mermaid 块替换后未复制 `data--src-line` / `data--src-line-end` → 该块对预览范围带与「预览↔源码」定位不可见 | ✅ **K4 2026-09-15 修复**：`markdown-preview.js` 替换 `.-mermaid-container` / `.-mermaid-error` 时同步复制 `data--src-line`、`data--src-line-end`（原仅复制 `data--block-index`） |
| E21 | Mermaid 渲染失败时直接展示 mermaid 原生**错误图**（「Syntax error in text / mermaid version X」），用户看到的是库内部报错；且编辑中途的空/半成品源码也会被渲染成错误图（打包态"偶尔出现"） | ✅ **K4 2026-09-15 修复**：`initMermaid` 加 `suppressErrorRendering: true`（改为抛异常，由 catch 统一提示 `preview.mermaidFail`）；渲染前跳过空/纯空白源码；加同元素重入保护 + `await` 后 `isConnected` 校验（防并发重入写入过期 DOM）。证据：`vendor/mermaid.min.js` 含该配置项（4 处命中） |
| E20 | 保存会**吞掉 frontmatter 与正文之间的空行**（`---` 后空行被移除）→ 用户库里产生纯空白差异、污染 git 历史 | 🔴 K1（2026-09-15 观察：harness 打开并保存 showcase `README.md` 后，`git diff` 显示 `---` 后空行消失） |
| E22 | **跨块选区删除被静默拒绝**：`deleteSelectionMulti` 命中 `list` / `blockquote` / `NON_EDITABLE`（code_block·math_block·mermaid·table·frontmatter）任一即 `return false`；而 `beforeinput` 已 `preventDefault()` → 用户按 Backspace **毫无反应、无任何提示**（"删除不正常"的一大来源） | 🔴 K1（2026-09-15 实测：列表项→`<details>` 选区 `ret:false`，正文零变化；`app.js:9446-9452` + `edit-handler.js:596-624`）。**对照**：普通段落→`<details>` 选区 `ret:true` 且删除范围与源码行完全正确（段落/图片/2 空行被删、上一行 `"` 未被触碰）→ 说明入口正确时逻辑正确，问题在"拒绝时无反馈" |

***

## 6. 文件树管理

| ID  | 任务                                                                                                                                                                    | 状态 |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -- |
| T01 | 左侧文件树右键菜单：文件右键可重命名或删除文件                                                                                                                                               | ✅  |
| T02 | 文件树空白区域或文件夹右键：在该路径下新建文件或新建文件夹                                                                                                                                         | ✅  |
| T03 | 重命名文件同步全库引用：正文 `[[旧名]]`/`[[旧名#类型]]`/`[[旧名\|文本]]` 改写为 `[[新名\|原文]]`，侧车 links/edges 目标与 pool 迁移；若旧名恰为某 KP id（如 a.md 内含 id=a 的知识点）则不动引用（KP id 不随文件名变化）；新名 stem 与其他文件冲突时拒绝 | ✅  |

***

## 7. 导入与媒体

| ID     | 任务                                                              | 状态     |
| ------ | --------------------------------------------------------------- | ------ |
| I01    | R11 约定格式 KB 导入包（md + sidecar + manifest，应用内导入向导 + validate\_kb） | ✅ K4（2026-09-14 对账：三源导入向导 + RPC 全链路已落地 —— `import-flow.js:4,83-101`、`ui.py:967/999/1015`、`import_executor.py:130-160`；与 §0「M0–M7 全 ☑」一致） |
| I02    | R08 图片/图表渲染（①图片引用+预览 ②Mermaid/图表块渲染；③数据生图更远）                    | ✅      |
| I03    | F01 接入 LLM API，结构化处理，交互中有意义的内容智能导入知识库（**2026-09-14 对账：未实现** —— 全仓无 LLM 客户端/API Key 读取；`model_router.py:17-18` 为空槽）                           | 💡     |
| I04    | F02 一键应用推荐配置（KP 名称/id/标签/描述 + 智能加链；效果用 benchmark 衡量）（**2026-09-14 对账：未实现** —— 仅有逐项候选引擎与逐条确认 UI，无「一键应用」RPC，无对应 benchmark）            | 💡     |
| I05    | R03 HTML 导入（A 直接渲染 / B 转 Markdown 未定）                           | ⬇️     |
| <br /> | 给程序顶栏的”导入“添加一个项为提示词，点击后弹出一个页面让用户复制提示词并且说明提示词使用方式                | <br /> |
| I06 | 导入入口被**双重绑定**（`app.js:12109-12112` 与 `import-flow.js:518`）→ 一次点击连跑两遍导入向导 | 🔴 K1（2026-09-15 取证；来源 [agent-guide/08](reference/agent-guide/08-import-export-and-check.md)） |
| I07 | 图片资产**后台静默删除**：每 5 分钟检查一次，删除「注册表外且 mtime 超 6 小时」的图片，前端 catch 后不提示用户 | 🔴 K1（2026-09-15：`image-tools.js:575-597` + `document.py:1069-1078`；来源 [agent-guide/07](reference/agent-guide/07-search-and-images.md)） |

***

## 8. 壳与发布

| ID  | 任务                                        | 状态 |
| --- | ----------------------------------------- | -- |
| P01 | M5 收尾：图标/安装体验、更新通道（非 Windows 壳后续再议）（**2026-09-14 对账：图标已落地** —— `resources/icons/**`、`packaging/build.py:101-113`；**安装器与更新通道未实现** —— 无安装器脚本、无 updater/更新通道代码）       | 🔄 |
| P02 | R10 新手引导（首开 KB / 空文件树 / 无 KP 引导流；示例库一键打开） | ⏳  |
| P03 | R13 UI 语言切换（**前端已完成** —— `js/i18n.js:14-15` + 设置→显示即时切换；**壳端未做** —— 原生对话框标题硬编码中文，`app/pywebview_host.py:152/171/194`；不自动翻译 md 正文）      | 🔄 K1（前端 i18n 已完成；壳端原生对话框仍硬编码中文） |
| P04 | Windows 右键文件夹「以 Memoria 打开」+ 打开前安全检查（2026-08-29 登记） | ⏳  |

| P05 | `static_server` 的 `_kb_root` 是**模块全局** → 一进程只能服务一个知识库（多库/多实例与外部宿主嵌入受阻） | ⏳ K1（2026-09-15：`static_server.py`；与 D2 集成 X10 相关；来源 [agent-guide/10](reference/agent-guide/10-data-layout-and-host-embedding.md)） |

**P04 详情（2026-08-29 登记）：**
- **右键集成**：注册表 `HKCU\Software\Classes\Directory\shell\Memoria`（command → `Memoria.exe --open "%1"`）；提供安装/卸载入口（打包安装器或程序内「集成右键菜单」开关）。
- **exe 入口**：CLI 支持 `--open <dir>` 参数 → 启动即加载该文件夹为知识库（对齐现有 kb 加载链路）。
- **打开前安全检查**（任一不通过 → 明确提示，不强行打开）：
  1. 存在性：文件夹存在且为目录
  2. 权限：可读 + 可写（防止只读介质/无权限导致写 `.memoria` 失败）
  3. 范围：排除系统/关键目录（`C:\Windows`、`Program Files`、`ProgramData`、回收站、`C:\` 根等）——防止误操作
  4. 结构：已有知识库（含 `.memoria/`）→ 直接打开；空目录 → 提示可初始化；混合目录（有 md 但无 .memoria）→ 提示将创建 `.memoria`（写前确认）
  5. 路径：长度限制、非法/特殊字符、UNC/网络路径（网络路径写性能与锁语义不同，明确提示）
  6. 占用：目标目录已被另一 Memoria 实例打开 → 聚焦已有窗口而非重复打开
- **验收**：右键 → 打开指定文件夹成为当前知识库；安全项逐一构造反例验证提示正确；卸载后右键菜单消失。

***

## 9. 学习产品（V2+）

| ID     | 任务                                                  | 状态     |
| ------ | --------------------------------------------------- | ------ |
| V01    | R14 知识点沿路拼接·导出新文档                                   | ⏳      |
| V02    | R06 遗忘曲线·主动复习（进度存 `.memoria/`）                      | 🔄 由 V06 的 FSRS 工具包实现（`.memoria/agent/review/`）；**待真机验收（K2：代码与自测在案，无真机 results 落盘 —— 2026-09-14 对账）** |
| V03    | R12 全库静态离线 HTML 导出（只读子集）                            | 💡     |
| V04    | 导出 PDF                                              | 💡     |
| V05    | Android 端                                           | 💡     |
| V06    | Trae 知识库智能体：`.memoria/agent/` 工具包（指令 + 编撰规范 + FSRS 调度）；应用内「文件 → 创建 Trae 智能体」一键生成并复制指令，规则可独立升级而无需重建智能体 | 🔄 **待真机验收（K2：T1–T6 代码齐全，`kb-agent.md:239-247` 仅有自测记录，无真机 results 落盘 —— 2026-09-14 对账）** |
| <br /> | 接入大语言模型api接口，直接进行对话，增强检索框引擎联网场景能力，同时让用户直接在程序维护发展知识库 | <br /> |

***

## 10. 已完成归档

### 10.1 近期对话确认完成（2026-08）

- ✅ 换壳 pywebview（WebView2）：根治首帧冻结
- ✅ 窗口原生动画（最小化/还原渐变）+ 顶栏原生拖拽（Aero Snap）+ Win11 圆角 + 最大化铺满工作区（DWM + WndProc 方案）
- ✅ 打包机制整理：scripts/packaging 职责划分、build\_release.cmd 修复（.venv python）、run\_release 壳修正、test\_shell 修正
- ✅ m0 → app 目录/命名整理（含 egg-info 出库）
- ✅ 公式映射修复（domToAst 跳过 MathJax 内部文本）+ 公式选中高亮（.m0-sel-covered）
- ✅ E04 公式编辑：双击行内公式进入编辑（enterInlineMathEditMode）、双击块级公式进入 math_block 符号面板
- ✅ I02 图片与 Mermaid：图片引用+预览+入库+管理+属性编辑（阶段 A-G）+ Mermaid 渲染与编辑（._BLOCK_TOOLS.mermaid）
- ✅ 图片资产全链路（阶段 A-G，2026-08-28/29）：插入复制入库去重、管理视图（引用/未使用/清理）、宽度/对齐/名称字号属性、名称显示与单击直编辑、双击放大/单击进编辑工具栏（即改即存）
- ✅ 版本号单一入口（pyproject dynamic version，改 `src/memoria/__version__.py` 一处全生效）
- ✅ 源码编辑器右键粘贴（2026-08-29）：源码/分栏模式源码区无选区右键弹「粘贴」菜单，多行粘贴逐行拆分；有选区右键仍弹链接菜单（根因=全局屏蔽原生右键 + 无选区 return）
- ✅ docs 目录体系重构（2026-08-30）：`standards/`/`context/` 按性质拆分为 `conventions/`（契约规范）/`guides/`（操作指引）/`reference/`（参考说明）；中文文件名重命名 kebab-case（git mv 保留历史）；填实 architecture/glossary/hard-constraints/operations；AGENT.md 重写为现代全分区接入指南（Role/TechStack/Commands/Architecture/Conventions/Boundaries/Pitfalls/References）
- ✅ 图谱银河样式（2026-08-30）：设置「图谱样式」新增 Galaxy 视觉样式（视觉样式下拉 + 光晕强度），2D/3D 通用；节点呈现为星空星点（径向渐变光晕、亮度/大小随度数 Hub 亮星叶子暗星），深空底色，悬停/焦点时焦点星点脉冲闪烁，空闲静止；布局保持力导向不变；随 `ui-settings.json` 持久化
- 🔄 样式笔刷同行公式涂抹（**K2 验证未闭环**：映射修复后无验证通过证据；2026-09-14 对账）

### 10.2 文档标记完成（历史）

- ✅ 边模型升级（强/弱边 + 实线/虚线）、图谱面板拖拽宽度、3D 图谱（Three.js）、布局模式（Radial/Top-down/Free-force）、节点点击跳转 + anchor 定位
- ✅ Bug B01-B08 全部修复；UI/UX U01/U02/U03/U06/U07/U10/U11/U12 修复
- ✅ R02 KB 根目录安全标记、R09 Lexical 强化模糊搜索、R18 SearchKernel v1.5（aux + 多模型 + 统一建议）
- ✅ 检索量化基准：BEIR SciFact → Memoria KB（gold/minimal/skeleton 三档 profile）+ qrels（`scripts/benchmark/`）
- ✅ 知识文件整理导入提示词 + 平面文件导入格式规范（详见附录，可直接给 AI 使用）

### 10.3 2026-09-14 首轮台账对账（收口 11 项 + 修正 7 条 + 消解 3 处矛盾）

> 依据：[conventions/ledger-maintenance.md](conventions/ledger-maintenance.md) 规则 4/5/6；方式 = 三路只读核验（逐条对 `src/**` 与产物取证），**未改任何代码**。

**（1）误开 → 已收口（K4，11 项）**

| ID | 证据锚 |
|---|---|
| C01 | `index.html:129` + `app.js:12207` |
| C05 | `docs/reference/architecture.md:88` + `kp_rename.py:28-69` |
| C07 | `kp_rename.py:28-69` + `ui.py:342` |
| L02 | `link-context-menu.js:106-160` + `app.js:5512/5563/5238-5276` + `ui.py:479` |
| S01 | `services/search_kernel.py:38-133` + `ui.py:241-258` |
| E05 | `app.js:9703-9723,10013-10045,10810-10824` |
| E12 | `display-settings.js:11-19` + `app.js:12170-12186` |
| I01 | `import-flow.js:4` + `ui.py:967/999/1015` + `import_executor.py:130-160` |
| E9 | `results/g4-gate-summary-2026-09-09.json:14-17`（真机 PASS） |
| E3（部分） | `durable-flush.md:3,82-88` 已评审锁定（export-plan / maintenance-jobs 仍未评审） |
| i18n ④ | `docs/reference/i18n-inventory.md` 候选 0 行（2026-09-14 生成） |

**（2）描述与代码不符 → 已改描述（7 条）**：C02（配置窗无文件树）、C03（无多选批量）、C06（非单页顺序）、C08 + L01（"智能推荐"为 `disabled` 占位）、E02（表格编辑按钮无事件绑定）、E14（复制/格式保持未做）

**（3）代码完成·验收或验证未闭环（K2，5 项）**：V02（FSRS 复习）、V06（KB 智能体 T1–T6）、B2（目录重命名）、B3（F2 快捷键）、样式笔刷·同行含公式 —— 均缺真机/验证落盘

**（4）设计待评审（K3，2 项）**：B7（`export-plan.md`）、E3 中的 `maintenance-jobs.md`（`durable-flush` 已闭环）

**（5）同文件矛盾已消解（3 处）**：§7 I01 ↔ §0「M0–M7 全 ☑」；§12 E9 ↔ §12 G4 段（真机 PASS）；`maintenance-jobs.md` §4 ↔ §5（`preview_range_redraw` 等，已在原文件修正）

**（6）无法判定（❓，2 条，需补信息后重判）**：C09「高级选项 → 设置内容完善」、E10「U08 设置内部数值范围过小」—— 原描述不足以定位到具体控件

**（7）附带发现（待项目负责人处置）**：`artifacts/agent/` 仅有 `agents.json` + `prompts/*.md`；`events.jsonl`、`verify/**`、`register/**`、`drift-report.json` **均不存在** → [AGENTS.md §5](../../AGENTS.md) 的一致性校验当前**无可校验对象**

### 10.4 2026-09-14 「文件」菜单修复（3 项，用户报告）

| # | 问题 | 修法 | 证据 |
|---|---|---|---|
| 1 | 导入 / 导出不相邻且被分隔线隔开 | `index.html` 菜单顺序改为 `打开 / 导入 / 导出 ─── 创建 Trae 智能体 / 新窗口 / 打开最近`，并去掉末尾分隔线 | `index.html:49-59` |
| 2 | 当前窗口未开库时，「打开最近」仍呼出新窗口 | 最近项点击按状态分流：**无库 → 本窗口装载**；已开着别的库 → 仍开新窗口（不打断当前会话）；同一个库 → 忽略。`openKb()` 抽出 `openKbAt(path)` 复用；i18n `toolbar.openRecentTitle` 中英同步 | `app.js:12152-12161`、`app.js:534-566` |
| 3 | **隐性缺陷**：按已知路径装载时未同步后端库根 | `openKbAt()` 补 `set_kb_path` 调用（选目录路径由 `select_directory` 内部完成，直接按路径装载会漏）；失败时上屏 `app.loadFailed` | `app.js:534-548` |

**验证（harness 真实前端 + 读取 `/rpc` 调用序列，2026-09-14）**：

- 菜单 DOM 顺序实测 `[file-menu-open, file-menu-import, file-menu-export, SEP, file-menu-kb-agent, file-menu-new-window, file-menu-recent-wrap]`，分隔线 **1 条**、末尾无分隔线。
- 关库 → 文件 → 打开最近 → 点 `showcase`：RPC 序列 `get_recent_kbs → set_kb_path → list_files → get_link_targets → get_graph_data → suggest_group_labels → get_kb_pending → validate_kb → install_kb_agent`；`open_new_window` 调用 **0 次**；`state.files=10`、侧栏 `文件 10 / 2D 35 / 3D 35`、后端 `list_files` 返回 10 项（**修复前为 0 且报「未打开知识库」**）。
- 已开着 `showcase` 时再点同一项：RPC **0 次**（按设计忽略）。
- 静态/门禁：`node --check` OK；`i18n_selftest` 12 PASS；`scan_ui_strings` rows=0。
- **未覆盖**：当前窗口已开着**别的**库时点击最近项（会真启动新进程，harness 内未触发；分支逻辑经代码审查确认）。

***

## 11. 备注 / 散记（待讨论）

- 编辑链接页面选择文本时主窗口正文跟随跳转，用户编辑完如何回到原位置 → 需描述交互方案
- 打开/配置慢：任务排队在后台进程继续工作，不阻塞前端（进度条/锁？）
- 检索负样本基准（召回率/精确率/错误率）是否完善；每个知识点除隐式 tag 外，是否智能写隐式描述
- 前进/后退功能与一些新设计没对应好，部分跳转无法返回

***

## 12. 知识库与维护机制 · 施工总表（2026-09-09 建立）

> 目的：把「知识库数据一致性 + 维护作业」类机制/任务统一登记为施工总表，据此敲定施工计划。
> 状态标记沿用文件头约定。关联设计：[maintenance-jobs.md](design/maintenance-jobs.md)（维护作业/静默同步，草稿）、[export-plan.md](design/export-plan.md)（导出，草稿）。
>
> **设计取向（2026-09-09 用户确立）：有意借鉴操作系统手段来组织维护机制**，把维护当作「任务/作业」而非一次性函数：
> - 调度内核：优先级、去重（replace/merge）、idle 执行、epoch 陈旧丢弃、flush/旁路（见 G3、scheduler.js）；
> - 写盘分级：缓存/缓冲 + 原子替换 + 延迟批量 fsync 屏障（durable flush，类 write-back 缓存/回写屏障，见 G4 M6a 与 [durable-flush.md](design/durable-flush.md)）；
> - 后台化与合并：重活（词法索引）移出同步路径，daemon 线程 + 合并重建（G4 M3）；
> - 时机/一致性：切文件/关库/退出为屏障点，前台即时响应、后台收尾（M6a/M6b/M3 均按此取舍）；
> - **触发点约束（2026-09-10 用户确立）**：维护动作只允许两类触发点——**后台（自动、不阻塞交互）** 或 **用户显式（打开库/刷新/构建/点击）**；**交互热路径（切换文件、输入、点击）禁止任何同步重活**。反例：`load_document` 曾每次同步重建全库 KP 索引（见 G5.4 修正）。
> 后续任务立项与评审都以「是否符合该作业化/屏障语义」为考量；jobs.md 与阶段门禁沿此口径登记。

### A. 一致性 / 注册内核

| # | 机制 | 现状 |
|---|---|---|
| A1 | sidecar 镜像 + `file` 字段 + 校验 + 级联（path_cascade.apply_path_move） | ✅ |
| A2 | manifest 基线/差分/幂等移动/touch | ✅ |
| A3 | pending 项路径同步（重命名已接入） | ✅ |
| A4 | 图片注册表：doc 增量 / 全量 / 自动检查 / 清理 | ✅（渲染 bug 已修） |
| A5 | KP range 双端定位（locator）+ 保存重锚 heal | ✅ 2026-09-09 |
| A6 | 词法/embedding 索引：侧车写后同步重建 | ✅ 词法已后台化（G4 M3：锁 + 合并 daemon，写路径不阻塞，检索前 wait）；embedding 未纳入机制（maintenance-jobs §7 建议保持现状） |
| A7 | 原子写（tmp + os.replace） | ✅ M1 已补（2026-09-09）：md 正文保存（document.py）与 ui-settings（storage/ui_settings.py）；YAML/registry 原已原子 |
表现为| A8 | 终点锚点 `forward_only` 漏洞：`locate_snippet` 的"信任 line_hint"分支未校验 hint 是否在起点之后 → hint 漂移且文本在起点前有同名行时，终点被钉到起点之前，报 `end_before_start`（候选里其实已有正确终点） | ✅ 2026-09-15 修复：`range/locator.py:45` 加 `and (not forward_only or h >= start)`；对照证据：修复前 `ok=False, end_before_start, end_line=1`（`end_candidates:[3]`）→ 修复后 `ok=True, start_line=2, end_line=4` |

### B. 操作 / 作业

| # | 任务 | 现状 |
|---|---|---|
| B1 | 文件重命名（stem 引用改写 / KP-shadow / 冲突 / pending+registry 级联） | ✅ 已加固 |
| B2 | 文件夹重命名 dir_rename（整树移动 + 逐文件级联） | ✅ 新增（partial 级联失败已上屏，2026-09-09 复核修正）；**K2 待真机验收**（2026-09-14 对账：代码与 RPC 齐备，无验收落盘） |
| B3 | F2 快捷键（文件/文件夹，捕获阶段 + 仅拦可见弹窗） | ✅ 新增；**K2 待真机验收**（2026-09-14 对账：`file-tree.js:438-463` 齐备，无验收落盘） |
| B4 | 保存 autosave / flush / 脏标记 | ✅ |
| B5 | KP 创建/更新慢 RPC（原阻塞 UI） | ✅ 主因已修（2026-09-09）：pending 存储 YAML→JSON（自动迁移）+ confirm/delete 改单文件范围同步 + 弹窗关窗先于图谱刷新；真机 modal 链 2442.6→981.6→**485.7ms**，后端稳态 4s→285.7ms（详见 [results/kp-confirm-2026-09-09.json](../scripts/benchmark/maintenance/results/kp-confirm-2026-09-09.json)）；剩余词法索引全库重建作业化归 M3/G4（P1） |
| B6 | md 相对路径链接在目录重命名时自动改写 | ❌ 已知边界（待扩展）；**2026-09-14 对账：边界成立** —— `document.py:697-780` 仅物理移动 + `apply_path_move`，`storage/path_cascade.py` 全函数不触碰 md 正文 |
| B7 | 导出知识库包（bundle） | ⏳ **K3 待评审**：design 草稿在案（`docs/design/export-plan.md` §8 四个打开问题未拍板），无实现（无 `export_execute`；`index.html:60` 导出菜单仍 disabled） |

| B8 | 构建 `build_kb` 末尾 `openFile(同路径, {skipNav:true})` 跳过 `flushDurableBarrier` → 构建期间**未落盘编辑**（<1.5s autosave 窗口）可能被磁盘内容覆盖 | 🔴 K1 ⚠️ **待运行时确认**（2026-09-15 静态取证：`app.js` buildKb 末尾 openFile 的 flush 分支被 skipNav 跳过；来源 [agent-guide/06](reference/agent-guide/06-links-and-graph.md) §7） |

### C. 视图 / 静默刷新

| # | 任务 | 现状 |
|---|---|---|
| C1 | 文件树重映射 + 刷新（rename 后 applyRenameUi） | ✅ |
| C2 | KP 面板静默刷新（ranges_resynced 触发） | ✅ 首期 |
| C3 | 预览范围带静默重绘（无滚动/闪烁） | ✅ 2026-09-10：新增 `markRangeQuiet`（只标记范围，不滚动/不闪烁/不自动消失）并用于「修改范围 / 创建知识点」；跳转语义（点链接/列表项/检查面板打开）仍走 `highlightRange`（滚+闪）。**编辑场景本就静默**（M6b 实时映射 + `resolve_kp_ranges` 回写 hover/列表，不经过 `highlightRange`），无需另接 |
| C4 | 图谱**增量更新**（增量在布局与数据层，非帧绘制；原「局部刷新」表述已修正） | ⏳ K1：G4 拆分后续项，方案 S1–S4 见 results/g4-gate-summary-2026-09-09.json；**2026-09-14 对账：`applyDelta` 零命中**，`graph-engine.js:62` 仍整体替换 |
| C5 | maintenance-jobs 调度内核（合并/优先级/idle/epoch/flush） | ✅ G3 已落地（`scheduler.js`，VM 单测全 PASS）；后端执行器见 G5.3 |

### D. 渲染 / 显示

| # | 任务 | 现状 |
|---|---|---|
| D1 | 图片缩略图渲染修复（lazy 干预 + overflow:hidden 不绘制） | ✅ |
| D2 | 预览颜色 hover / 选区机制（历史修复） | ✅ |

### E. 测试 / 文档 / 规范

| # | 任务 | 现状 |
|---|---|---|
| E1 | rename-test 测试库 + 生成脚本 + example README 登记 | ✅ |
| E2 | 图片路径规范（preview-formats §4.4 / organize §7.3，含 `../` 禁例）同步 | ✅ |
| E3 | design：export-plan / maintenance-jobs / durable-flush（草稿，2026-09-09 复核恢复 export-plan；durable-flush 为 G4 M6a 设计） | ⏳ **K3 待评审**：**2026-09-14 对账** —— durable-flush 已评审锁定（`durable-flush.md:3,82-88`），export-plan / maintenance-jobs 仍未拍板 |
| E4 | docs-management / to-dolist 修订登记 | ✅（2026-09-09 复核补登记 to-dolist §12 行） |
| E5 | L2 KP 创建链路归因闭环：前端插桩 + 后端克隆计时工具 trace_kp_confirm.py + results 记录（归因 pending 同步，B5 修复对照） | ✅ 2026-09-09 |
| E6 | L1 保存路径回退归因：2 轮 ABBA（base 158.6 vs HEAD 180.5，+13.8%）→ diff 定位 M1 fsync；分项剖析 trace_save_document.py（manifest_touch ~50ms 为大头）→ 决策 fsync flush 屏障化 + manifest 批量（jobs.md 登记，G4 M6a） | ✅ 2026-09-09 |
| E7 | G4 M6a 施工：durable_flush（barrier 默认 + RPC + 前端屏障）+ manifest 模块 pending overlay；实测 save median inline 89.35 → barrier 24.62ms（-72.5%，results/durable-flush-2026-09-09.json）；**门禁通过（用户 2026-09-09 拍板）**：真机 idle 3s（flushed1/manifest1/14.99ms）+ 切文件屏障（1.91ms）+ 崩溃注入 15/15 PASS + 回归冒烟 PASS | ✅ 2026-09-09（门禁通过） |
| E8 | G4 M3 词法索引后台化（锁+合并 daemon，`_write_sidecar` 不再同步重建；search/切库/关库前 wait）；回归冒烟 PASS；**真机验证通过（2026-09-09：建后立即检索与连建后检索均命中，rpc 340.5→260~320ms）**，results/m3-lexical-background-2026-09-09.json；待 G4 出口对照汇总 | ✅ 2026-09-09（施工+真机验证通过） |
| E9 | G4 M6b 正文编辑 KP 区域行号范围实时同步（区域内 Enter 并入/区域外与后续顺延/行前插空行吸收/删行收缩；前端实时更新列表行号与 hover 高亮，保存后后端 resync 权威校正）；单测 15/15（m6b_adjust_test.js，从真实 app.js 抽取断言）；待真机 | ✅ **K4（2026-09-09 施工 + 真机通过）**：真机 PASS 见 `results/g4-gate-summary-2026-09-09.json:14-17` 与本文 §12 G4 段（**2026-09-14 对账更正**：原写"待真机"与 G4 段矛盾） |

### F. §2.5 开放发现 · 待评估补录（2026-09-09 代码复核，均确认存在）

| # | 机制/任务 | 触发点 | 现状 |
|---|---|---|---|
| F01 | KB 完整性检查/审计子系统（`validate_kb` + 静默检查 + 徽标，kb-check.js） | 打开/定时/显式 | ✅ 存在，未纳入调度登记 |
| F02 | 路径漂移检测/修复（`detect_path_moves` / `repair_path_cascade`，GUI+CLI 双入口） | 修复 RPC/检查 | ✅ 存在，未纳入施工范围评估 |
| F03 | 图片引用诊断/修复（`diagnose_image_refs` / `fix_unregistered_image_refs`，防误删已引用图片） | 图片管理/保存后 | ✅ 存在，未纳入施工范围评估 |

### 验证机制分配（2026-09-09）

> 通用基线（每项都过）：`py_compile` / `node --check` / IDE 诊断 0 错；改动前端 UI 后 i18n 扫描 `rows=0`（scripts/scan_ui_strings.py）。真机类标 `[真机]`，由用户按清单执行，Agent 负责提供步骤与判定标准。

| 计划项 | 验证机制（手段/工具） | 通过标准（可复核证据） |
|---|---|---|
| M1 原子写补全 | 静态核查：列出全部写盘点是否 tmp+replace（grep `open(.w.)`/`write_text`）；临时副本压力脚本：反复写/读回 + 半程中断后重启可读 | 报告列明：md 保存/ui-settings 已改原子；临时副本中断后无半包、可正常打开 |
| M2 保存链路基线（A5+C2） | rename-test 临时副本断言脚本（结尾行回车→save→`ranges_resynced=1`→KP 重解析 ok）；真机：保存后 KP 面板行号自动更新 | 脚本 PASS；`[真机]` 面板无需手动刷新即更新 |
| M3 索引作业化 | 性能对照：同一保存路径 改造前后 计时（或计数索引重建次数）；行为：内容可检索；复用 scheduler VM 自检断言合并计数 | 报告含前后耗时/次数对比；检索命中一致；同文件连续保存只触发 1 次重建 |
| M4 预览带静默重绘 | 代码审查：确认静默路径无 `scrollIntoView`/flash 分支；`[真机]` 编辑换行保存后带位置自动更新且滚动/光标不动 | 代码路径证据 + `[真机]` 通过 |
| M5 调度内核 | scheduler VM 单测（artifacts 临时）：merge/优先级/epoch 陈旧/flush 各 PASS（已建基线）；`[真机]` 触发保存看 `[job]` 日志与 queue 收敛为 0 | 单测全 PASS；真机日志 `执行 kp_panel` 后 `queued=0` |
| M6 KP 创建作业化 | 行为脚本/计时：连续 2+ 次创建不再同步等待（入队立即返回）；完成事件后 KP 可见（轮询断言） | 连续创建无阻塞（耗时上限）；完成后 KP 列表/跳转可用 |
| M7 F01–F03 评估 | KB validate CLI（`python -m memoria.cli.main validate <kb>`）；repair_path_cascade 干跑报告断言；diagnose_image_refs 结构化输出断言；UI 入口 `[真机]` | validate 0 issue；干跑 moves 与实际 rename 一致；diagnose 输出合法 |
| B2 文件夹重命名 | rename-test 临时副本断言脚本（文件/sidecar 镜像/manifest 三方核对，已用）；partial 注入验证（构造只读目标） | 脚本 PASS；partial 时前端提示首项错误（上屏） |
| B3 F2 | `[真机]` 清单：文件/文件夹各一次 + 弹窗已开不劫持 + 输入框不劫持 | `[真机]` 全通过 |
| B6 md 链接改写 | 临时副本断言：dir 重命名后 `](...)` 相对链接指向仍正确；跨层/含 `../` 用例 | 断言 PASS；边界（根/子目录/同层）用例通过 |
| D1 图片渲染 | 代码审查（无 lazy/overflow 注释/圆角补位）+ `[真机]` 打开图片管理目测 | 审查证据 + `[真机]` 缩略图全显示 |
| A6/A7 回归 | 见 M1/M3；完成后在 snapshot 前跑全量临时库冒烟 | 冒烟 PASS 后再提交 |

### 施工计划 · 阶段门禁（2026-09-09 定版）

> 推进纪律：**逐阶段施工，阶段出口过「门禁(Gate)」才进下一阶段**；门禁结论由用户复核拍板（Agent 出证据，用户签字）。
> 每阶段通用执行顺序：任务实现 → 逐项验证（按「验证机制分配」表）→ 回归冒烟（rename-test/showcase 临时副本）→ 更新 to-dolist 状态 → **独立 git commit 快照收口**（可回滚）。
> 打回规则：任一项失败/证据不足 → 打回该阶段修复 → 重跑本阶段门禁 → 通过后再前进。
> **基准规则**：凡"改善"类提交必须附 A/B 对照（按 [docs/design/maintenance-benchmark.md](design/maintenance-benchmark.md)，当前为设计待评审）；无对照或关键指标回退 → 打回。

**G0 · 基线快照** ✅ `ae66a012`（维护机制基线已提交，工作区干净，恢复点就绪）→ 进入 G1 的入口条件已满足。

**G1 · 验收收尾（档 1）**
- 范围：B2 文件夹重命名 / B3 F2 / A5+C2（KP range 重锚+面板静默）/ D1 图片渲染 / E1 rename-test
- 入口：G0 通过；rename-test 与 showcase 可打开
- 出口门禁：B2 三方核对脚本 PASS（含 partial 上屏）｜B3 `[真机]` 清单通过｜A5 heal 脚本 + `[真机]` 面板自动更新｜D1 代码审查 + `[真机]` 目测｜E1 生成器复跑 PASS｜`py_compile`/`node --check`/validate/i18n rows=0｜to-dolist 状态更新 → commit `G1`

**G2 · 一致性补强**
- 范围：M1 原子写 ✅（2026-09-09 已实现并验证）｜B6 md 相对路径链接改写（消已知边界）｜M4(C3) 预览带静默重绘
- 入口：G1 门禁通过
- 出口门禁：M1 写盘点盘点 + 中断恢复脚本 PASS｜B6 跨层/`../` 断言 PASS｜M4 代码路径（无 scroll/flash）+ `[真机]` 滚动光标不动｜回归冒烟 PASS → commit `G2`

**G3 · 调度内核完善（M5 继续）**
- 范围：`bumpEpoch` 接入文件切换/关闭/重命名（✅ 已接入 openFile/closeKb/applyRenameUi）；replace/merge 语义实现（✅）；首批消费 `kp_panel`（启用 dropStale）；**文件树/registry 刷新等其余作业化随 M3/M4/C4 采用时注册**
- 入口：G2 门禁通过
- 出口门禁：scheduler VM 单测（replace=true/false、merge、prio、epoch/flush）全 PASS（✅ 已通过，tool `scripts/benchmark/maintenance/scheduler_vm_test.js`）｜bumpEpoch `[真机]` 陈旧丢弃生效（✅ 证据：g3_probe dropped=1）｜`[job]` 日志 `queued=0` 收敛（✅ 证据：status queued=0）｜回归冒烟 PASS → **✅ G3 门禁通过（用户拍板 2026-09-09），快照见 tag `maint-g3`**

**G4 · 作业化落地**
- 范围：**M6a 持久化 flush 屏障**（正文写降级 tmp+replace，fsync 收拢为 `durable_flush`，**✅ 门禁通过 2026-09-09**）｜**manifest_touch 批量合并**（**✅ 已施工**：模块 pending overlay + 屏障落盘，~50ms/保存消除，barrier 24.6 vs inline 89.4ms）｜**M3 词法索引后台化**（**✅ 真机验证通过 2026-09-09**：锁+合并 daemon 重建，`_write_sidecar` 不再同步重建；检索一致、rpc 340.5→260~320ms，results/m3-lexical-background-2026-09-09.json）｜**M6b KP 区域行号范围实时同步**（**✅ 真机通过 2026-09-09**：源码 Enter 并入/删行收缩 + 预览块替换平移 + 即时权威解析 RPC `resolve_kp_ranges`（停手 420ms 回写）+ 保存后校正兜底；单测 15/15）｜C4 图谱增量更新（**已拆分后续项**，仅可行性讨论，见 results/g4-gate-summary-2026-09-09.json）
- 入口：G3 门禁通过（作业底座就绪）
- 出口门禁：M6a 屏障对照（✅ inline 89.35 → barrier 24.62ms，切文件/关库屏障后可读，崩溃注入 15/15）｜manifest 批量（✅ 连续保存单次落盘证据 idle/屏障）｜M3 前后耗时/重建次数对照 + 检索一致（✅ rpc 340.5→260~320ms，合并计数以 pending 清零收敛代替确定性断言）｜回归冒烟 PASS（✅）→ **G4 收口 2026-09-09：M6a/M3/M6b 全✅（用户验收），汇总 results/g4-gate-summary-2026-09-09.json，快照见 tag `maint-g4`；C4 图谱增量更新拆分后续项（可行性见 summary.deferred.C4_graph_partial_refresh），不计入本门禁**

**G5 · 维护面收敛（M7）**
- 范围（2026-09-09 评估盘点）：**F01** `validate_kb`（RPC full-KB 扫描：逐文件 validate_sidecar + 图链路审计 + manifest diff + 路径漂移检测；静默检查默认 120s/可关，跑在主 RPC 线程）｜**F02** `repair_path_cascade`/`detect_path_moves`（GUI+CLI `repair-paths` 已有，干跑/apply 一致）｜**F03** `diagnose_image_refs`/`fix_unregistered_image_refs`（GUI RPC 已有，**CLI 无 diagnose 子命令**；保存后 cleanedImages 已做部分自动清理）｜**M7b 重活线程池与定时队列**（当前仅 M3 单 daemon 合并线程）
- 子计划：**G5.1** F01 后台化/调度化（**✅ 2026-09-10 施工+自动验证**：静默 validate 纳入调度内核——priority3 / 按库 replace / dropStale、编辑忙时跳过、idle 执行；新增 L1 基准 `run_validate_l1.py`（200 文件语料 median 5.93s、errors=0）；真机 `[job]` 证据：`入队→执行→开始→完成`、编辑中 3 次`跳过（编辑/待保存未收敛）`、`queue=1` 收敛）｜**G5.2** CLI 补全与断言（**✅ 2026-09-10 施工+自动验证**：新增 `diagnose-images` 子命令（结构化 JSON + 退出码语义）；断言脚本 `cli_assert_g5_2.py` 全 PASS——validate 0-issue、diagnose 分类与字段合法、repair 干跑不写盘且 move 集合与 apply 一致、修复后 errors=0；扫描器补日志封装剔除规则 → i18n `rows=0`，i18n 自检全 PASS）｜**G5.3** M7b 后端执行器（**✅ 2026-09-10 施工+自动验证**：新增 `services/executor.py`——线程池 + 作业表（submit 即返回 / 同 kind+key 排队顶替合并 / 结果保留供轮询）；RPC 增 `validate_kb_async` + `job_status` + `jobs_snapshot`；静默检查改为「提交后台作业 + 轮询」，不占用前端调度队列；断言 `executor_assert_g5_3.py` 全 PASS——submit 1.0ms 返回（作业 1.2s）、`superseded` 合并、异步 validate 与同步 errors/files 一致）｜**G5.4** 读路径索引缓存（M7a，**✅ 2026-09-10 施工+自动验证**：`load_document` 原每次两次全库 `build_kp_index`（含与 id 无关的范围解析）→ 改为只读轻量快照（KP id / 文件 stem / (文件,KP id) 对，仅读 sidecar）+ 持久化 `.memoria/kp_targets.json` + 打开库秒读 + 写后失效与后台增量重建（逐 sidecar mtime+size 缓存）；实测 `load_document` 1822 → 7.6ms（-99.6%）；**写后仅失效、重建移读路径（惰性 + 合并）**——修复「每次保存触发后台全库扫描 → 知识点区域内换行卡顿」的回归；遗留：打开库仍有 ~1.06s `sync_kb_pending` 全库扫描，另记）
- 入口：G4 门禁通过
- 出口门禁：validate CLI 0 issue（✅ 基准语料 errors=0）｜repair_path_cascade 干跑与实操一致（✅ `cli_assert_g5_2.py`）｜diagnose 结构化输出合法（✅ CLI + GUI）｜F01 调度化后无编辑期运行且不阻塞 RPC（✅ 真机编辑中 3 次 `跳过`；后端异步作业 787.6ms 不占 RPC 线程）｜G5.4 交互热路径零构建（✅ 1822→7.6ms + 快照与全量索引一致 + 打开库不触发全库重活）｜登记表与 i18n rows=0（✅）｜回归冒烟 PASS（✅）→ **✅ G5 门禁通过（用户拍板 2026-09-10）：汇总 results/g5-gate-summary-2026-09-10.json，快照见 tag `maint-g5`**
- 遗留（另记，非本阶段引入）：打开库 `sync_kb_pending` 全库扫描 ~1.06s（见 G5.4 实测）；`kp_panel` 作业在文件切换瞬间有一次 `expected str, bytes or os.PathLike object, not NoneType` 失败（真机 2026-09-10 日志）—— 待排查触发条件

**旁线 · B7 导出 bundle（独立评审门，不阻塞主线）**：export-plan 评审 → 通过后按 M1–M5 阶段表独立推进。

***

## 附录：已交付规范（保留原文）

### A. 知识文件整理导入提示词

> 已迁移为**单一事实源**：`resources/agent-prompts/organize.zh-CN.md`（程序内「导入 → Agent 整理提示词」直接读取该文件，docs 不再维护副本）。
> 用途与用法见 [docs/reference/import-spec.md §12](reference/import-spec.md)（0.3.0 导入模块规格）。

### B. 平面导入文件格式规范

> 已收编为事实来源：[docs/reference/import-spec.md §4A 平面文件（AI 整理）](reference/import-spec.md)；导入实现/冲突/预览见同文件 §5–§8，模块计划见 [import-plan.md](reference/import-plan.md)。

### C. 样例库隐私与官方样例（用户备注）

> docs/example 下本地知识库运行产物（`.memoria/**`、`empty*/` 等）按 .gitignore 自动忽略；仅维护/上传「官方样例知识库」与 import-test 夹具，保护本地隐私（见 import-plan.md M5.3）。

----待讨论
需要完整的规则提示词让agent学会整理修改.Memoria以及markdown格式的知识文件

“
- 开发人员通过建立原型系统已经学到了许多东西，因此，在设计和编码阶段发生错误的可能性比较小，这自然减少了在后续阶段需要改正前面阶段所犯错误的可能性。

![图2-4 快速原型模型](.memoria/images/2b4a0e5bc9c191d9a7c754d1b8df841470e66a0958bc2ddb418a106cb17f0d6b.jpg)


<details>
<summary>flowchart</summary>

```mermaid
...

"以上文段在预览区域拖拽选择”<details>
<summary>flowchart</summary>“的时候进行删除，会删除前一行而不是删除选中的内容，请你debug


---
打包态交互操作的时候偶尔会出现这个
”Syntax error in text
mermaid version 11.16.0“
表现为，窗口整一面上移，下方出现这个报错并且挤占ui，没办法点击“最大化”“还原”“关闭”，我window底栏关闭程序后重新打开恢复正常，这个bug很难复现，