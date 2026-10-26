# Memoria 待办清单（整理版）

> 整理日期：2026-08-20（由原 `to-dolist.md` 与 `dicussion.md` 合并去重后按功能域归类）。
> 维护规范：[conventions/ledger-maintenance.md](conventions/ledger-maintenance.md) —— K1 真开放 / K2 代码完成·验收未闭环 / K3 待评审 / K4 已收口；证据锚必填；规则 8：体积 ≤36 KB，已收口条目按批次出表入 §10。
> 状态标记：✅ 已收口 / 🔄 进行中 / ⏳ 待做 / 💡 方向性（需再规格化）/ 🔴 Bug / ⬇️ 最低优先级。
> 2026-09-16 按规则 8 压缩至预算内：开发流水账出表（i18n 迁移明细见 [conventions/i18n.md](conventions/i18n.md) 修订记录；拆分与文档登记见 [docs-management.md](conventions/docs-management.md)；版本级变更见 [version.md §7](conventions/version.md)）；旧文末两段用户粘贴的 bug 记录按规则 8.3 归位（E22 补复现记录、新增 E23）。
> 2026-09-19 按规则 8.2 再清理（表头逐日追述与 §10.4 流水账出表；新增 §13 AG12–AG16）。
> **索引化（2026-10-26，人批准）**：本文件是**索引**——只允许 标题 / 状态 / 一行摘要 / 详情链接；详细内容只在 `docs/todo/` 附件（活跃详情）或 `docs/design/` 归档（已收口）。**引用本文件必须用 §-锚点或任务 ID，禁止用行号**。
> **维护约定（2026-10-22，裁决 #9 固化）**：§10 归档区（§10.3 明细 / §10.4 作废存档 / **§10.5 索引表**）中的 ID **允许与正文重复**；做「编号唯一」自检时**必须排除 `## 10.` 段**（否则 §10.5 的 27 条 ✅ 索引会被误报为重复）。**活动区（§0–§9、§11–§13）内编号仍必须唯一**；**索引表不是证据** —— 证据锚与「未取证 / 下一步」一律以原条目行为准。

***

## 0. 当前进行中（焦点）

- 🔄 样式笔刷·预览模式涂抹后选区保持：纯预览模式应用样式后选区消失（分栏模式正常）；harness 多次复现未果，待用户确认环境/操作细节。K1（无修复证据）
- 🔄 样式笔刷·同行含公式涂抹混乱（旧 §10.1 内重复记作「样式笔刷同行公式涂抹」）：映射修复已在 `app.js:9217-9218,10640`。K2（验证未闭环，无通过证据）
- 🔄 M5 桌面壳收尾：窗口原生动画/顶栏拖拽/圆角/最大化已达成；剩余图标与安装体验、更新通道。K1
- 🔄 app.js 拆分瘦身：已抽 5 个子系统 js（file-tree / import-flow / toolbar-search / image-tools / kb-check），app.js ≈16.8k 行 @2026-10-22（实测 16,845 行；`js/**` 共 62 个模块 —— 当时记的「~10.9k 行 / 5 个子系统」已随迭代腐化，故改为带日期快照）；界面文案候选清零（i18n-inventory 空清单）。下一步：editor-styles 层抽取（`FT_MENU_ID` 浮层引用仍在 app.js）；真机回归待用户执行。K1
- 🔄 **P06 打包态在他人机器启动崩溃**（根因 = **Mark-of-the-Web**；修复 = 随包 `Memoria.exe.config`（`loadFromRemoteSources`）+ 失败可读弹窗 + 交付面说明；v0.3.4 已重新构建并替换资产）。K2（待在报错机器复验，见 §8 P06 详情）
- ✅ **task-140 跳转滚动定位三处不符** → 已修（`039e815f`）：删 `block:"start"` + 已可见不滚 + 二次校准只补偏移；真机三场景 + OLD-SIM 对照（`artifacts/agent/verify/todo/jump-scroll-fix.md`）。K4a
- ✅ **task-141 长文档预览跳开头** → 已修（`51e1c755`；证据矩阵 `d2c22695` 15/15 + 3 轮一致）：惰性物化空态把 scrollTop 夹到 0。K4a

***

## 1. 配置窗口（合并「知识点解析」+「审核」）— 核心大项

| ID | 任务 | 状态 |
| --- | --- | --- |
| C02 | 配置窗内左侧文件树 + 「当前文件」快速定位 | 🔄 K1（配置窗仅 kp/links/pending 三 Tab，无文件树/无「当前文件」；主界面文件树与点击切换已在） |
| C03 | 右侧三段式布局：顶栏 `id + description`；tag 分「已有（上）/候选灰色（下）」逐 chip 点击，支持手动创建、「系统建议」重新推荐 | 🔄 K1（上下分区/逐 chip/手动创建/系统建议已在 `app.js:4008-4091,4121`；多选批量上移/下移未实现） |
| C04 | UI 风格：右侧编辑框去掉外框包裹与框间隔，统一左栏文件树风格 | 🔄 K1（列表项已扁平化去外框 `app.css:1637-1646`；「统一左栏文件树风格」无专门证据） |
| C06 | 配置页右侧顺序：文件描述 → 知识点配置（下拉展开/再点收回）→ 链接管理 | ⏳ K1（现状与描述不符：实为 kp/links/pending 三 Tab，KP 配置走独立弹窗，`app.js:2272,3020-3030`） |
| C08 | 自动解析：识别库内/库外知识点 → 推荐创建 KP 并解析跳转锚点；识别可建边文本 → 推荐创建 | 🔄 K1（KP 推荐已实现：`heading_proposals.py`/`mention_proposals.py`/`definition_proposals.py`；「可建边文本→推荐创建」为 `disabled` 占位 `app.js:2180-2197`） |
| <br /> | <br /> | <br /> |
| C10 | 弹窗层级混乱：`.-modal` 的 z-index 1000 低于搜索面板 9000 / 右键菜单 10050 / 颜色选择器 20000 / flash 浮层 12000，弹窗可被浮层遮挡 | 🔴 K1（`app.css:4633`（modal z-index:1000）vs `2501`（搜索面板 9000）；来源 agent-guide/01） |

***

## 2. 链接系统

| ID | 任务 | 状态 |
| --- | --- | --- |
| L01 | 选中文本右键 → 创建链接窗口：智能推荐 + 加号手动添加（输入 id/tag 匹配）+ 多选定向 | 🔄 K1（创建窗/多选定向/手动 id-tag 搜索已实现 `app.js:5134,5189-5195,5238-5259`；智能推荐为 `disabled` 占位 `app.js:5197-5208`） |
| L03 | 公式也可以作为链接被点击 | ⏳ K1（未实现：解析器视 `[[…]]` 为纯文本、公式为独立原子节点，`parser.js:222-235` / `js/surface/render-core.js`（原 `renderer.js`，已改名）） |
| L04 | `[[**aaa**]]` 类链接预览错误（`**aaa` 无法选中创建链接） | 🔴 |
| L05 | http 链接点击行为完善 | ⏳ K1（未实现：预览仅拦截库内 `.md` 且显式排除 `https?`，`app.js:6271-6326`） |

***

## 3. 检索引擎

| ID | 任务 | 状态 |
| --- | --- | --- |
| S02 | R17 SearchKernel v2：双向生长汇合检索（查询侧语义扩张 + 库侧沿图/标签生长，按路径计分） | 💡 K1（未实现：`retrieval_fusion.py:149-161` 有 `graph_hits` 通道但检索未接线） |
| S03 | R16 检索反馈循环·库内模型（点击/有用无用学习，存 `.memoria/`，本地离线可删） | ⏳ K1（未实现：无 `search_feedback.py`，`ui.py` 无反馈 RPC） |
| S04 | R04 智能链接推荐 | 🔄 K1（Lexical 版已实现 `services/link_relevance.py` + `ui.py:626`；LLM 提议层未实现，`model_router.py:17-18` 为空槽） |
| S05 | R05 公式级语义检索 | 🔄 K1（公式归一化已并入语义检索 `services/text_normalize.py:11`；独立公式索引/AST 未做） |
| S06 | 搜索范围偏好跨库残留：上次停在「文件」时，新开库且未打开文件即搜索 → 报 `app.openFileFirst`，而范围按钮为 disabled 态 | 🔴 K1（`app.js:47`、`toolbar-search.js:143-146`；来源 agent-guide/07） |

***

## 4. 图谱

| ID | 任务 | 状态 |
| --- | --- | --- |
| G01 | R07 图谱推理·新边提议（建议边不自动写入，用户逐条采纳/忽略；需先定边属性专章）+ 梳理现实阅读/学习/复习场景中的知识点边类型 | 🔄 K1（边类型体系 `graph/edge_types.py:10-29` + 手动建边 `ui.py:775` 已实现；无 `suggest_edge`/提议 RPC，新边提议未实现） |
| G02 | Bug：边抑制之后点击构建/刷新，图谱仍然显示该边 | 🔴 |
| G05 | 图谱节点渲染算法优化，提升渲染性能，设置benchmark单独对图谱引擎性能测试 | 🔄 K1（**主体已达成，待补最后一步**；规划与逐项实测数据全部在 [design/graph-benchmark.md](design/graph-benchmark.md)。已落地：**D1 帧预算化**（目标档整帧 p95 大降）、**D2 Barnes-Hut 近似排斥**（`graph-bh-tree.js`，θ=0.9，`bh:false` 保留精确路径供同 build A/B）、**X3**（`distanceMin` 下限 + 位移上限取代 `Math.random()`）、**X4 装载卡死根治**（warmup 工作量上限 + worker 超时）。**未达标项**：单 tick ≤20ms 仅 partitioned 达标，small\_world/star 仍 33–35ms ⇒ 下一步 **D2b 树扁平化/免分配**（估 2–3×，目标 \~10ms）。用户已定：不设节点间距指标、不作质量门禁） |

***

## 5. 编辑器 / 富文本

| ID | 任务 | 状态 |
| --- | --- | --- |
| E01 | R15 富文本 Markdown 编辑 | 🔄 K1（加粗/斜体/高亮/荧光笔/字色/Undo-Redo 已实现 `index.html:154-184`、`app.js:7196-7198`、`lexer.js:326-335`；字号/上下标仅语法层支持，工具栏无入口） |
| E02 | 表格内部也可以编辑（同步编辑板块） | ⏳ K1（未实现：有「编辑表格/+行/+列」按钮但无事件绑定、内容不写回，`edit-handler.js:570`（NON_EDITABLE 含 table）与 `:1215`（editTable 入口未接事件）） |
| E03 | 编辑模式下修改链接的内容要自动处理 | ⏳ |
| E06 | 文本批处理按钮：`\(` `\)` → `$`、`\[` `\]` → `$$` | ⏳ |
| E07 | ~~Bug：无法复制~~（2026-10-22 已并入 E14，正文保留供追溯） | ⛔ 已并入 E14（2026-10-22） |
| E08 | Bug：分栏状态下文本编辑功能检验不通过 | 🔴 |
| E09 | U04 预览/源码切换定位到对应位置；分栏可配置是否自动定位 | 🔄 K1（切换定位已实现 `app.js:1578-1668`；分栏自动定位配置项缺） |
| E10 | U08 设置内部数值范围过小，需扩大 | ⏳ K1 ❓（无法定位 U08 所指控件：字号 12-28 / 缩放 0.8-1.5 / labelMaxLen 4-20 均无从对应，需澄清） |
| E11 | U09 右键创建知识点时自动剔除「3.3.4.2」类编号前缀 | ⏳ K1（未实现：`app.js:11196-11207` 取首行 trim 后直接截断，无编号剥离） |
| E13 | Bug：预览区域粘贴时换行符被忽略，导致代码格式错误 | 🔴 |
| E14 | 完善源码-预览-分栏区域的复制粘贴功能 | 🔄 K1（粘贴换行处理已实现 `app.js:7411-7511,7513-7538,9641-9673`；「复制」与格式保持未做，无 copy 监听、现仅写 text/plain；**含原 E07「无法复制」与 §11「复制粘贴 redo undo」——2026-10-22 合并裁决**） |
| E18 | 工具栏 tooltip 声称 `Ctrl+B` / `Ctrl+I`（及 `Ctrl+S`）实际未实现 | 🔴 K1（`index.html:153-154`、`i18n/zh-CN.js:593-594`；全库无按键处理器；来源 agent-guide/03） |
| E20 | 保存会吞掉 frontmatter 与正文之间的空行（`---` 后空行被移除）→ 用户库里产生纯空白差异、污染 git 历史 | 🔴 K1（harness 打开并保存 showcase `README.md` 后 `git diff` 显示 `---` 后空行消失） |
| E22 | 跨块选区删除被静默拒绝：`deleteSelectionMulti` 命中 `list` / `blockquote` / `NON_EDITABLE`（code\_block·math\_block·mermaid·table·frontmatter）任一即 `return false`，而 `beforeinput` 已 `preventDefault()` → 按 Backspace 毫无反应、无任何提示 | 🔴 K1（`app.js:9446-9452` + `edit-handler.js:596-624`；对照：普通段落→`<details>` 选区 `ret:true` 且删除范围与源码行完全正确 → 问题在「拒绝时无反馈」）。**用户原始复现（2026-09-14 粘贴记录）**：在预览区拖拽选中含 `<details><summary>flowchart</summary>` 的区块后删除，结果删掉了**前一行**而不是选中内容 —— 与上述「范围正确」的对照结论冲突，需在真机复测确认是同一根因还是独立缺陷 |
| E23 | 打包态偶发：Mermaid 渲染失败时（`Syntax error in text / mermaid version 11.16.0`）窗口整面上移、报错块占位挤占 UI，导致「最大化 / 还原 / 关闭」按钮点不到，只能从系统底栏关进程重开才恢复。**难复现**（用户报告，未定位） | 🔴 K1（用户报告 2026-09-14；与 E21「不再展示原生错误图」是否同根因待验 —— 若 E21 的 `suppressErrorRendering` 已消除该占位，本条可关闭） |

***

### 5.1 2026-10-22 批次（未闭环项：E24/E31/E33/E34 + DOC02/DOC03）

> 来源：用户 2026-10-22 直接反馈（原文见各条「现象」）。编号沿用本文件既有 E 系列（E23 之后），不新造体系；本条块只登记**用户可感知的产品缺陷/需求**，施工中的工程任务在团队任务板（Lead 立项），不在此复制。
> 分组：**A 编辑器输入（E24）· D 选区与快捷键（E31）· F 后续登记（E33/E34）· E 台账治理（DOC02/DOC03）**；**已闭环移出**：E25–E30、E32、DOC01 → §10.4.1。
> 优先级是本批**建议**（理由随条），与 §12 机器门禁台账无冲突（§12 不设优先级）；`K1` 沿用 [ledger-maintenance.md](conventions/ledger-maintenance.md) 的「真开放」。
> 探针产物：`artifacts/agent/verify/probe-parser-roundtrip-2026-10-22.js`（parser/source-gen 往返）、`artifacts/agent/verify/probe-anchor-check-2026-10-22.py`（证据锚可解析性）。
> **优先级总表（仅活动项）**：P2 = E24（受 E02 阻塞）/ E31（语义待确认）/ E33（拖拽未接管）/ E34（尾随空格观感）/ DOC03（版本漂移，需人修）；P3 = DOC02（AG35 残余）。**已闭环项（E25–E30 / E32 / DOC01）不在活动表**，见 §10.4.1。

| ID | 任务 | 状态 / 优先级 |
| --- | --- | --- |
| E24 | 格式编辑不完善：表格内无法应用字体颜色 / 加粗 / 斜体 | 🔴 K1 · P2（被 E02「表格编辑未实现」阻塞） |
| E31 | 引用块（`>`）内选中文字无法发到对话 + 选区缺快捷键（**原话存疑**） | 🔴 K1 · P2（原话断句有歧义，语义待用户确认） |
| E33 | 真实拖拽移动（`deleteByDrag` / `insertFromDrop`）可能只进 DOM 不进源码；E30 仅覆盖 Ctrl+X | 🔴 K1 · P2（单测覆盖 drag 分派，真实拖拽未验） |
| E34 | 尾随空格占宽后，基线库 **603 行**带行尾空白的块会多出可见空格（≈3.86px/空格） | 🔴 K1 · P2（观感影响；可加开关或仅光标所在块生效） |
| DOC02 | 历史格式化残留：`\|\|` 被旧对齐工具拆成 `\| <br /> \|`；真污染 2 处：**AG86 已修**（2026-10-22），**AG35 待复核**（未转义形式，需重建行结构） | 🟡 P3（AG35 残余 1 处，仅归档可读性；另 8 处为无害填充单元格，保留） |
| DOC03 | 版本文档漂移：`v0.4.6` 已发布（tag + `793a70be`）但 `version.md`/`__version__.py` 仍写 0.4.5；版本文件属「人只读」，需人修 | 🟡 P2（发布治理：建议 0.4.7 发布前先 bump，否则 tag 与产物不符） |

> **已闭环移出（2026-10-22）**：E25–E30（用户复报批次）、E32（转化丢 srcLine 修复）、DOC01（台账治理）已由 Lead 确认收口；按台账规范不硬删——**原文与证据已归档**于 [design/ledger-archive-2026.md §10.4.1](design/ledger-archive-2026.md)；**活动表只跟踪未闭环项**（E24/E31 为阻塞/待裁决，不是已完成）。

**详情已出表（2026-10-22 P3）**：E24 / E31 / E33 / E34 / DOC02 / DOC03 的逐条详情（现象·用户原话 / 影响面 / 验收判据 / 定位线索）已**逐字**迁入 [design/editor-input-defects-2026-10.md](design/editor-input-defects-2026-10.md)；本表只留索引与优先级，证据/原话以该存档为准。
***

## 6. 文件树管理

T01–T03 已按规则 8.4 出表（见 §10）。

| ID | 任务 | 状态 |
| --- | --- | --- |
| T04 | 文件夹无法折叠（含当前文件时点折叠即回弹）+ 文件树 emoji 换 dsh 图标 | ✅ 已收口 @2026-10-22（**依据 = 用户在该行行尾亲笔批注「已经验证了」**；非代码/测试验证，本轮未重跑真机；原状态 K2 待真机验收）（根因 `file-tree.js:451` 重渲时自动展开覆盖用户折叠；修复 = 用户折叠记忆 + 重渲守卫 + 真 reveal 清除（末尾块 539-557）；图标借 dsh `ui-primitives`（末尾块 521-716、`app.css` 5522-5583）；2026-09-20 无侧车「暗淡」态 0.45→0.55（`app.css` 5601-5613）；无验收落盘） |

<br />

***

## 7. 导入与媒体

| ID | 任务 | 状态 |
| --- | --- | --- |
| I03 | F01 接入 LLM API，结构化处理，交互中有意义的内容智能导入知识库 | 💡 K1（未实现：全仓无 LLM 客户端/API Key 读取；`model_router.py:17-18` 为空槽） |
| I04 | F02 一键应用推荐配置（KP 名称/id/标签/描述 + 智能加链；效果用 benchmark 衡量） | 💡 K1（未实现：仅有逐项候选引擎与逐条确认 UI，无「一键应用」RPC，无对应 benchmark） |
| I05 | R03 HTML 导入（A 直接渲染 / B 转 Markdown 未定） | ⬇️ |
| — | 给程序顶栏的「导入」添加一项为「提示词」：点击后弹出页面让用户复制提示词并说明使用方式（未编号·用户备注） | 💡 |
| I06 | 导入入口被双重绑定（`app.js:12109-12112` 与 `import-flow.js:518`）→ 一次点击连跑两遍导入向导 | 🔴 K1（来源 agent-guide/08） |
| I07 | 图片资产后台静默删除：每 5 分钟检查一次，删除「注册表外且 mtime 超 6 小时」的图片，前端 catch 后不提示用户 | 🔴 K1（`image-tools.js:575-597` + `document.py:1069-1078`；来源 agent-guide/07） |

***

## 8. 壳与发布

| ID | 任务 | 状态 |
| --- | --- | --- |
| P01 | M5 收尾：图标/安装体验、更新通道（非 Windows 壳后续再议） | 🔄 K1（图标已落地 `resources/icons/**`、`packaging/build.py:101-113`；安装器与更新通道未实现） |
| P02 | R10 新手引导（首开 KB / 空文件树 / 无 KP 引导流；示例库一键打开） | ⏳ |
| P03 | R13 UI 语言切换 | 🔄 K1（前端已完成 `js/i18n.js:14-15` + 设置→显示即时切换；壳端未做，原生对话框标题硬编码中文 `app/pywebview_host.py:152/171/194`；不自动翻译 md 正文） |
| P04 | Windows 右键文件夹「以 Memoria 打开」+ 打开前安全检查（2026-08-29 登记，详情见下） | ⏳ |
| P05 | `static_server` 的 `_kb_root` 是模块全局 → 一进程只能服务一个知识库（多库/多实例与外部宿主嵌入受阻） | ⏳ K1（`static_server.py`；与 D2 集成 X10 相关；来源 agent-guide/10） |
| P06 | 打包态在**他人机器**启动崩溃（pythonnet 初始化失败，2026-09-18 用户报于 v0.3.4-lite 分发） | 🔄 K2（**根因 = Mark-of-the-Web**；修复 = 随包 `Memoria.exe.config` + 失败可读弹窗 + 交付面补系统要求；v0.3.4 已重建并替换资产。证据 `artifacts/p06-motw-e2e.txt`。待在报错机器复验。详情见下） |
| P07 | UI 视觉收敛（滚动条 / 标签栏滚轮 / 圆角五档 / 描边 0.5px + **分隔线档** **`--border-sep`** / 阴影三档 / **横条统一 33px（`--bar-h`）** / 侧栏页签条去 13.2px 白留 / 发送按钮右对齐） | 🔄 K2（`app.css` 末尾块 + 原位改值；harness 8651–8659 实测数字见 agent-guide/01 §6–§7 与 design/ui-visual-language.md §4。**未取证**：0.5px 在 1x 仍上取整为 1px、真实 hover/滚轮、真机观感） |
| <br /> | <br /> | <br /> |

**P04 / P06 详情已出表（2026-10-22 P4）**：右键集成与打开前安全检查的 6 项校验、P06 的 MotW 根因/修复/证据/遗留，均已**逐字**迁入 [design/packaging-release.md](design/packaging-release.md)；本表只留状态与一行摘要。
***

## 9. 学习产品（V2+）

| ID | 任务 | 状态 |
| --- | --- | --- |
| V01 | R14 知识点沿路拼接·导出新文档 | ⏳ |
| V02 | R06 遗忘曲线·主动复习（进度存 `.memoria/`） | 🔄 K2 待真机验收（由 V06 的 FSRS 工具包实现，`.memoria/agent/review/`；代码与自测在案，无真机 results 落盘） |
| V03 | R12 全库静态离线 HTML 导出（只读子集） | 💡 |
| V04 | 导出 PDF | 💡 |
| V05 | Android 端 | 💡 |
| V06 | Trae 知识库智能体：`.memoria/agent/` 工具包（指令 + 编撰规范 + FSRS 调度）；应用内「文件 → 创建 Trae 智能体」一键生成并复制指令，规则可独立升级而无需重建智能体 | ✅ 已收口 @2026-10-22（**依据 = 原状态列声明「已经验收」**；非代码/测试验证，本轮未重跑验收） |
| — | 接入大语言模型 api 接口直接对话，增强检索框引擎联网场景能力，同时让用户直接在程序维护发展知识库（未编号·用户备注） | 💡 |

***

## 10. 已完成归档

> **格式**：本节是归档索引，按规则 8.4 从活动分区出表；一行一批次 = `| 日期 | ID 列表 | 一行汇总 | 证据锚 |`。**未收口条目不在本节**（原 §10.1 末尾的「样式笔刷·同行公式涂抹」属 K2 未收口项，已归位 §0）。

> **2026-08 ~ 2026-09-05 的 7 条早期归档索引已移出** → [design/ledger-archive-2026.md §10.7](design/ledger-archive-2026.md)（task-135 腾体积，**原文逐字**；其余批次仍见下表）。

> **2026-09-09/10 ~ 2026-09-14 的 5 条归档索引已移出** → [design/ledger-archive-2026.md §10.8](design/ledger-archive-2026.md)（2026-10-25 腾体积，**原文逐字**；其余仍见下表）。

| 日期 | ID 列表 | 一行汇总 | 证据锚 |
| --- | --- | --- | --- |
| 历史 | T01, T02, T03 | 文件树右键菜单：文件重命名/删除、空白区或文件夹右键新建文件/文件夹；重命名同步全库引用（正文 wikilink 改写、侧车 links/edges 与 pool 迁移，KP id 不随文件名变，新名冲突拒绝） | `file-tree.js`；`document.py:697-780` + `storage/path_cascade.py` |
| 历史 | E15, E16, E17 | 源码编辑器多行粘贴换行丢失修复；快照式撤销/重做（输入/Enter/合并删除/粘贴，Ctrl+Z/Y）；新建文件缺 `.md` 后缀自动补齐 | `git log -S E16` |
| 历史 | B01, B02, B03, B04, B05, B06, B07, B08, U01, U02, U03, U06, U07, U10, U11, U12 | Bug 批次全部修复；UI/UX 批次修复 | `git log -S U12` |
| 历史 | R02, R09, R18 | KB 根目录安全标记；Lexical 强化模糊搜索；SearchKernel v1.5（aux + 多模型 + 统一建议） | `services/search_kernel.py` |
| 历史 | — | 边模型升级（强/弱边 + 实线/虚线）、图谱面板拖拽宽度、3D 图谱（Three.js）、布局模式（Radial/Top-down/Free-force）、节点点击跳转 + anchor 定位 | `graph-engine.js` |
| 历史 | — | 检索量化基准：BEIR SciFact → Memoria KB（gold/minimal/skeleton 三档 profile）+ qrels；知识文件整理导入提示词 + 平面文件导入格式规范（已收编进 [import-spec.md](reference/import-spec.md) §4A/§12） | `scripts/benchmark/`；[import-spec.md](reference/import-spec.md) |
| 2026-09-15 | E19, E21, A8 | 修复批次：Mermaid 块替换后复制 `data--src-line`/`data--src-line-end`（预览范围带与源码定位恢复）；Mermaid 失败不再展示原生错误图（`suppressErrorRendering` + 空源码跳过 + 重入保护）；`locate_snippet` 终点锚 `forward_only` 漏洞（hint 未校验是否在起点之后） | `markdown-preview.js`；`vendor/mermaid.min.js`；`range/locator.py:45` |
| 2026-09-19 | G0–G5、附录指针 | §12「施工计划 · 阶段门禁」**整段收口出表**（G0 基线 / G1 验收收尾 / G2 一致性补强 / G3 调度内核 / G4 作业化 / G5 维护面收敛，结论与实测数字见证据锚）；同批删除文末「附录：已交付规范」三行指针（其事实早已在别处：A → `resources/agent-prompts/organize.zh-CN.md`、B → [import-spec.md](reference/import-spec.md) §4A、C → [import-plan.md](reference/import-plan.md) M5.3） | tag `maint-g3` / `maint-g4` / `maint-g5`；`results/g4-gate-summary-2026-09-09.json`、`results/g5-gate-summary-2026-09-10.json`；`git log -S maint-g4` |

### 10.3–10.5 明细已出表（2026-10-22 P2）

> **10.3 首轮台账对账明细** / **10.4 已废弃条目存档（AG97、AG75 原文 + 作废理由；10.4.2 = 窗口化家族 24 条，task-90）** / **10.5 §13 中 27 条 ✅ 批量出表索引** / **10.7 §10 早期归档索引（2026-08~09-05，task-135）**，均已**逐字**迁入 [design/ledger-archive-2026.md](design/ledger-archive-2026.md)；本区只保留上方批索引，原文可按标题 `grep -n` 反查。
> **10.4.1 已闭环归档（E25–E30 / E32 / DOC01，2026-10-22）**：用户复报批次 6 条（Ctrl+V 图片 / 换行滚动跟随 / 样式尾随空格 / `>` 后空格 / 英文词后空格 / Ctrl+X 重现）、E32（转化丢 `srcLine/srcLineEnd` 修复）、DOC01（台账治理）均已移出 §5.1 活动表，原文 + 证据见 [design/ledger-archive-2026.md §10.4.1](design/ledger-archive-2026.md)。**E24/E31（阻塞/待裁决）与 DOC02（残余）不在归档区。**
***

## 11. 备注 / 散记（待讨论）

- 编辑链接页面选择文本时主窗口正文跟随跳转，用户编辑完如何回到原位置 → 需描述交互方案
- 打开/配置慢：任务排队在后台进程继续工作，不阻塞前端（进度条/锁？）
- 检索负样本基准（召回率/精确率/错误率）是否完善；每个知识点除隐式 tag 外，是否智能写隐式描述
- 前进/后退功能与一些新设计没对应好，部分跳转无法返回
- 需要一套完整的规则提示词，让 agent 学会整理/修改 `.memoria` 与 Markdown 格式的知识文件
- ！！！需要知识库导出为html资源文件夹的形式把知识库静态化的功能，一方面便于知识库转发，另一方面绕开了程序markdown渲染的开销，用户可以以这种方式放弃编辑能力看知识库，同时支持html资源文件夹导入到知识库，所以要约束一个html文件夹的组织格式
- bug: mermaid 渲染出来的图很小；给mermaid添加拖拽和放大缩小
- ~~复制粘贴的redo undo没了？~~ → 已并入 E14（2026-10-22 合并裁决；见 §5 E14）
- agent向用户提问竟然有等待超时按照默认做的机制，这个不要，允许无限等待

***

## 12. 知识库与维护机制 · 施工总表（2026-09-09 建立）

> **索引（2026-10-26 索引化）**：本表只留索引；**详情（施工总表原文/节区注记）**→ [todo/12-build-table.md](todo/12-build-table.md)。状态事实源 = 本表；A/D/F 收口与 G 认领表归档 = [design/ledger-archive-2026.md](design/ledger-archive-2026.md) §10.6；验证方法论 = [design/maintenance-benchmark.md §9](design/maintenance-benchmark.md)。
> 统计：活跃行 **7**（B2/B3/B6/B7/B8/C4/E3）；A/D/F 已收口出表；G 已归档；H 待裁决建议条款（见附件 #h）；遗留两处（见附件 #residual）。

| # | 任务 | 状态 | 详情 |
| --- | --- | --- | --- |
| B2 | 文件夹重命名 `dir_rename`（整树移动 + 逐文件级联） | 🔄 K2 | [详](todo/12-build-table.md#b2) |
| B3 | F2 快捷键（文件/文件夹，捕获阶段 + 仅拦可见弹窗） | 🔄 K2 | [详](todo/12-build-table.md#b3) |
| B6 | md 相对路径链接在目录重命名时自动改写 | ❌ 已知边界 | [详](todo/12-build-table.md#b6) |
| B7 | 导出知识库包（bundle） | ⏳ K3 | [详](todo/12-build-table.md#b7) |
| B8 | 构建 `build_kb` 末尾 `openFile(同路径, {skipNav:true})` 跳过 `flushDurableBar… | 🔴 K1 | [详](todo/12-build-table.md#b8) |
| C4 | 图谱**增量更新**（增量在布局与数据层，非帧绘制；原「局部刷… | ⏳ K1 | [详](todo/12-build-table.md#c4) |
| E3 | design：export-plan / maintenance-jobs / durable-flush（草稿，2026-09-09 复核… | ⏳ K3 | [详](todo/12-build-table.md#e3) |

> 节区注记：引言/触发点约束 `#intro`｜A 一致性内核（已收口出表）`#a`｜D 渲染（已收口）`#d`｜F §2.5 开放发现 `#f`｜G 团队任务板（已归档）`#g`｜H 待裁决建议条款 `#h`｜验证机制分配 `#verify`｜§12 遗留 `#residual`

## 13. 应用内对话（Agent 面板）

> **索引（2026-10-26 索引化）**：本表只留索引（ID/主题/状态/详情）；**详情（AG 行原文 + 注记）**→ [todo/13-agent-panel.md](todo/13-agent-panel.md)。状态事实源 = 本表；历史批次叙述 = [design/agent-panel-batches.md](design/agent-panel-batches.md)。
> 统计：106 行 = 活跃索引 **52**（✅10 / 🔄·K2 30 / 🔄 3 / ⏳7 / 💡1 / ⚠️1）+ 已归档 ✅→§10.5 **27** + 已作废 ⛔ **27**。

| ID | 主题 | 状态 | 详情 |
| --- | --- | --- | --- |
| AG01 | 引用 agent 回复内容再追问（选中某条… | 💡 | [详](todo/13-agent-panel.md#ag01) |
| AG03 | dsh M2 session-refere… | 🔄·K2 | [详](todo/13-agent-panel.md#ag03) |
| AG04 | 工具与能力包路线图（写/联网/skill/… | ⏳ | [详](todo/13-agent-panel.md#ag04) |
| AG05 | 状态栏/状态 bar（点绿/红 + 模型/… | 🔄 | [详](todo/13-agent-panel.md#ag05) |
| AG06 | UI 视觉语言对照（借 dsh 观感）：A… | 🔄 | [详](todo/13-agent-panel.md#ag06) |
| AG07 | 引用/锚点合法性（空格路径/非 md/全角… | ⏳ | [详](todo/13-agent-panel.md#ag07) |
| AG08 | 面板看不到模型 thinking ＋其展开… | 🔄·K2 | [详](todo/13-agent-panel.md#ag08) |
| AG09 | 设置里的「字号」同时控制对话面板字号 | 🔄·K2 | [详](todo/13-agent-panel.md#ag09) |
| AG10 | dock 整理：会话选择迁到左栏「历史」页… | 🔄·K2 | [详](todo/13-agent-panel.md#ag10) |
| AG11 | 流式逐行渲染（面板侧中间缓冲；代码块/公式… | 🔄·K2 | [详](todo/13-agent-panel.md#ag11) |
| AG12 | 图片渲染支持：在流式管线里渲染模型输出的图… | ⏳ | [详](todo/13-agent-panel.md#ag12) |
| AG13 | 思考不落盘 ⇒ 重载旧会话/刷新看不到历史… | ⏳ | [详](todo/13-agent-panel.md#ag13) |
| AG14 | 会话重命名（title.py 补 user… | ⏳ | [详](todo/13-agent-panel.md#ag14) |
| AG15 | 每轮 token 用量行：最后一轮助手气泡… | 🔄·K2 | [详](todo/13-agent-panel.md#ag15) |
| AG16 | 状态 bar 刷新间隔可配：设置 → 对话… | 🔄·K2 | [详](todo/13-agent-panel.md#ag16) |
| AG17 | 「生成中…Ns」下沉末条助手气泡尾 + 状… | 🔄·K2 | [详](todo/13-agent-panel.md#ag17) |
| AG18 | 「读后写守卫」+ 审批审计事件 + nev… | 🔄·K2 | [详](todo/13-agent-panel.md#ag18) |
| AG19 | delete\_file op（写面 §7 … | 🔄·K2 | [详](todo/13-agent-panel.md#ag19) |
| AG20 | 修（真机反馈）：同批「先 create\_f… | 🔄·K2 | [详](todo/13-agent-panel.md#ag20) |
| AG21 | 技能（skill）规则面落地：吃上游 pa… | 🔄·K2 | [详](todo/13-agent-panel.md#ag21) |
| AG22 | 补 move\_file op（跨目录搬整篇… | 🔄·K2 | [详](todo/13-agent-panel.md#ag22) |
| AG23 | 斜杠命令最小面（上游 interactio… | 🔄·K2 | [详](todo/13-agent-panel.md#ag23) |
| AG24 | 能力插件「声明面」落地（S1 开篇）：se… | 🔄·K2 | [详](todo/13-agent-panel.md#ag24) |
| AG25 | tool/call 落盘位次对齐上游（"先… | 🔄·K2 | [详](todo/13-agent-panel.md#ag25) |
| AG26 | skill 的 /name 用户手势补齐（… | 🔄·K2 | [详](todo/13-agent-panel.md#ag26) |
| AG27 | sidecar 结构 op 三件套 | 🔄·K2 | [详](todo/13-agent-panel.md#ag27) |
| AG28 | 修「字样式命令被当成 wikilink」（… | 🔄·K2 | [详](todo/13-agent-panel.md#ag28) |
| AG29 | 库级 op rebuild\_manifes… | 🔄·K2 | [详](todo/13-agent-panel.md#ag29) |
| AG39 | 文件树连接线第三版：折角退役、仿 Trae… | 🔄 | [详](todo/13-agent-panel.md#ag39) |
| AG56 | 回话二级折叠（只剩最后一段摘要）+ 发送区… | ⏳ | [详](todo/13-agent-panel.md#ag56) |
| AG58 | 末轮用量行"又没了"的修复（重载/重启后仍在）+ 「思考过程」小… | 🔄·K2 | [详](todo/13-agent-panel.md#ag58) |
| AG61 | **N 线插件化·第二片：样板声明 + 工具级能力闸（= 库级启停）+ … | 🔄·K2 | [详](todo/13-agent-panel.md#ag61) |
| AG62 | **N 线技能包：skill 的「内置只读根」+ 首个随包技能** **`web-researc… | 🔄·K2 | [详](todo/13-agent-panel.md#ag62) |
| AG64 | **预览池的智能替换**（评分 + 老化 + 后台预渲染的入场闸）+ 设… | 🔄·K2 | [详](todo/13-agent-panel.md#ag64) |
| AG65 | **预览池门槛可配 + 现场读数**（真机反馈跟进，AG64 的修正） | 🔄·K2 | [详](todo/13-agent-panel.md#ag65) |
| AG66 | **板块：预览渲染管线**（刷新分档 / 缓存形态 / 增量渲染 / 预测… | ⏳ | [详](todo/13-agent-panel.md#ag66) |
| AG67 | **K1'a + K1'b 落地：双重预渲染的**第二层\*\*（基于知识点的智能预… | 🔄·K2 | [详](todo/13-agent-panel.md#ag67) |
| AG68 | **真机读数判定（"静态化能否提速"）+ 命中恢复分段计时** | 🔄·K2 | [详](todo/13-agent-panel.md#ag68) |
| AG69 | **第四次～第六次真机读数归因定形 +** **`static`** **两处修正 + K2… | 🔄·K2 | [详](todo/13-agent-panel.md#ag69) |
| AG70 | **第七次真机读数：④ 没打中靶子 + 读数头条口径修正 + 预渲染… | 🔄·K2 | [详](todo/13-agent-panel.md#ag70) |
| AG89 | **读数证明"33 s 不在渲染流水线里"**（全程仅 100 ms）⇒ 把 `renderPr… | 🔄·K2 | [详](todo/13-agent-panel.md#ag89) |
| AG100 | **修「行首退格合并后预览只剩前半段」（我 AG98 引入的 AST↔DOM … | ✅ | [详](todo/13-agent-panel.md#ag100) |
| AG105 | **切模式锚点回归修复 + 输入不再"先源码后预览"**（人：「从预… | ✅ | [详](todo/13-agent-panel.md#ag105) |
| AG103 | **原生优先：预览区打字不再"每键重渲那一块"**（人指出"南辕北… | ✅ | [详](todo/13-agent-panel.md#ag103) |
| AG104 | **跳转落点二次校准**（人：「知识点跳转定位位置又不准了」） | ✅ | [详](todo/13-agent-panel.md#ag104) |
| AG102 | **按键热路径再瘦身：跳过 O(文档) 重算 + 诊断埋点默认关**（人… | ✅ | [详](todo/13-agent-panel.md#ag102) |
| AG101 | **编辑热路径瘦身：源码面板/后处理都只动改动的那几行·那一块** | ✅ | [详](todo/13-agent-panel.md#ag101) |
| AG99 | **清掉窗口化残留 + MathJax 排队回旧口径**（收尾） | ✅ | [详](todo/13-agent-panel.md#ag99) |
| AG98 | **预览区编辑一律块级提交：结构性编辑不再整篇重渲**（人指出… | ✅ | [详](todo/13-agent-panel.md#ag98) |
| AG106 | 文档资源附件（拖 PDF/Word/TXT/MD 进对话栏） | ✅ | [详](todo/13-agent-panel.md#ag106) |
| AG107 | Release 标题/双语/造价段违反已文档化规范（v0.4.7/v0.4.8 两版 + 0.5.0… | ✅ | [详](todo/13-agent-panel.md#ag107) |
| AG108 | 资产命名漂移：`-lite.zip`（v0.4.7/v0.4.8；0.5.0 撤回前用的是 canonical… | ⚠️ 留档 | [详](todo/13-agent-panel.md#ag108) |
| — | 27 条已完成归档（§10.5） | ✅→§10.5 | [全部](todo/13-agent-panel.md#archived) |
| — | 27 条已作废/已并入（AG59/60/63/71–96 等） | ⛔ | [全部](todo/13-agent-panel.md#voided) |

> 注记（2026-10-25 task-94 K2 判定 / AG106/AG107/AG108 补录 / 2026-10-25 台账补录）→ [附件#notes](todo/13-agent-panel.md#notes)

## 14. 0.4.7 收摊计划（2026-10-25 刷新，todo-owner；交人审）

> **✅ 已发布 0.4.7（2026-10-25）**：tag `v0.4.7` → `d88e4cba`（2026-10-25T17:46:12+08:00）；Release 已发布；发版记录 `artifacts/agent/verify/todo/release-0.4.7-record.md`。**本 §14 原计划文本保留**（历史决策记录）；实际完成情况、计划外发现与偏离说明见 **§14.7**。

> **依据（L8）**：版本级规划必须由 todo-owner 从台账/代码/git 证据产出并写入本文件；Lead 不得凭记忆排期。
> **本版计划报告**：`artifacts/agent/verify/todo/0.4.7-plan-refresh-2026-10-25.md`（结论表 + 需人裁决 + 逐条证据 + 复跑命令）。
> **前序审计**：`artifacts/agent/verify/agent-0.4.7-collection-audit-2026-10-24.md`（§13 全量 103 条状态表）。
> **范围定义（人原话 2026-10-25）**：「现在你们可以做 0.4.7，先告诉我你要做什么给我检查一下」⇒ 本版 = **agent 半吊子工作收摊**；计划先交人审，批准后开工。
> **版本拆分裁决（todo-owner 2026-10-25）**：0.4.7 = **本 §14 收摊 6 项，先发**（低风险、用户可见修复/验证）；架构重构（粒度化→契约→MCP→扩展点→trace）**另立 0.5.0**，见 §16。理由：架构重构是 R1 级（改内部契约+新增 MCP 交付面+写安全边界），不应与收摊混发；混发会让用户可见修复被大改动拖住，且回滚粒度变粗。

### 14.1 范围与推荐顺序（6 项，任务板 task-90 ~ task-94 + task-112）

| 序 | 条目（台账 ID） | 任务板 | 类型 | 预估 | 依赖 | 完成（commit） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | §13 窗口化家族作废 + `✅·K2` 矛盾校准 | `task-90` | 台账校准（半吊子收摊） | 0.5–1 天 | 无（纯 docs，先做） | `65b408c8` |
| 2 | 上下文占用显示 + 压缩可观测（原 ①-b；AG15 相关） | `task-91` | 半吊子收摊（可观测性） | 1.5–2.5 天 | 需人裁决 D2；`agent-panel.js` 单写者 | `f2fe512d` + `7214932a` |
| 3 | skill/plugin 命名统一 + AG21 真机收口（原 ①-a） | `task-92` | 半吊子收摊（命名+验收） | 1–2 天 | 需人裁决 D1；与 2/4 串行 | `22b4391c` |
| 4 | 排版响应式（原 ②） | `task-93` | 原 0.4.7 范围（新做） | 2–3 天 | 需人裁决 D3；`app.js`/`agent-panel.js`/`app.css` | `efa7b806` + `5c6e93cc` |
| 5 | 0.4.6 已知问题收尾：矩阵补图片块 + 光标像素核验 +（待裁决）视图模式持久化 | `task-112` | 半吊子收摊（上一版披露债） | 1–1.5 天 | 需人裁决 D4；`app.js` 与 4 串行 | `26d2e110` |
| 6 | §13 剩余 K2 逐条收口/降级审计 | `task-94` | 半吊子收摊（批量） | 2–3 天（可分批） | 依赖 1–5 判定输入；与实现并行 | `5aaba784` |

**为什么这个顺序**：① 半吊子收摊优先新功能（人的意图）；② `app.js`/`agent-panel.js`/`i18n` **单写者** ⇒ 2/3/4/5 严格串行（本仓已因并行写 `app.js` 发生 2 次覆盖事故）；③ 能机器验证的优先（91 压缩事件 / 92 AG21 会话日志 / 112 选区矩阵）；④ 90 零代码先做，让看板可信。

### 14.2 逐条证据与可验证关闭条件

> 原文逐字归档 → [design/ledger-archive-2026.md §10.9](design/ledger-archive-2026.md)（发布后腾体积；本 §14 保留原计划结构，正文见归档）。

### 14.3 0.4.6 已带走（对照 release body + tag `09a5cbf2`）

> 原文逐字归档 → [design/ledger-archive-2026.md §10.9](design/ledger-archive-2026.md)。

### 14.4 人裁决结果（**2026-10-25 已裁决：全部按推荐项**）

> 原「需人裁决」5 项，人已逐项批准：**D1=A｜D2=A｜D3=A｜D4=B｜D5=A+C**。
> 保留原始选项与代价分析供追溯，**生效选择见每项「✅ 裁决」行**。

1. **D1 skill/plugin 术语**：A 三层区分（能力/技能/插件，**推荐**）｜B 统一「能力」｜C 现状+文档澄清。选错代价：30–60 条文案返工（R2）或问题不解决。
   **✅ 裁决 = A**：能力=capability（抽象）／技能=skill（规则面）／插件=plugin（分发载体）+ 出「旧→新」映射表。
2. **D2 上下文占用展示**：A 百分比+阈值提示（**推荐**）｜B 仅 token 数｜C 详细面板。选错代价：百分比映射错=误导；B 观测不到压缩=没解决原问题。
   **✅ 裁决 = A**：状态区显示「上下文 62% · 80% 时压缩」，压缩发生时插一条系统行（可回放）。需一个模型窗口上限来源。
3. **D3 响应式联动**：A 按原话自动联动+保守阈值 720px（**推荐**）｜B 仅 dock→折叠文件树｜C 手动紧凑开关。选错代价：布局抖动/覆盖用户手调（不可逆感）。
   **✅ 裁决 = A**：文档区 < 720px 触发；**不记忆**（每次按窗口状态算，避免覆盖用户手调）。
4. **D4 0.4.6 已知问题**：A 全纳入｜B 纳入图片块+光标核验、视图模式推 0.4.8（**推荐**）｜C 全推 0.4.8。选错代价：A 引入 pywebview 隐私方案风险；C 验证缺口继续挂着。
   **✅ 裁决 = B**：纳入 ① 图片块进选区矩阵、② 多行粘贴后光标像素核验；③ 视图模式持久化**推 0.4.8**（功能改动 + `private_mode` 隐私分支，不塞进收摊版）。
5. **D5 团队基础设施运维债**：A 不进 0.4.7（**推荐**，归 steward/task-110/宽限期）｜B 全进｜C 只做 0 成本项（写域收窄/路径修正，已做）。选错代价：B 让发布说明变内部治理清单且无产品验收标准。
   **✅ 裁决 = A + C**：不进 0.4.7；0 成本项（写域收窄、旧路径修正）已在计划刷新时顺手完成。

> **裁决索引**：提交内 `Decision:`/`Why:`。D5 不进版本 ⇒ 0.4.7 发布说明只讲产品，不讲内部治理。


### 14.5 本版本不做什么（防范围膨胀）

> 原文逐字归档 → [design/ledger-archive-2026.md §10.9](design/ledger-archive-2026.md)。

### 14.6 未测项（如实）

> 原文逐字归档 → [design/ledger-archive-2026.md §10.11](design/ledger-archive-2026.md)（发布后移出；含 0.4.7 发布时状态更新）。

### 14.7 实际完成情况与偏离记录（发布时补记，2026-10-25）

> 原文逐字归档 → [design/ledger-archive-2026.md §10.11](design/ledger-archive-2026.md)（六项完成/计划外 4+1/偏离说明/已知问题）。

***

## 15. 0.4.8 范围（2026-10-25，人已定）

> **依据（L8）**：版本级规划由 todo-owner 写入台账；本范围 = 人 2026-10-25 明确指定（2 件必做 + 1 件可选）。
> **上一版**：0.4.7 已发布（§14.7）；**下一版**：0.4.9（PATCH；当前 0.4.9 为开发中未发布）。

### 15.1 范围（2 件必做 + 1 件可选）

| 序 | 条目 | 任务板 | 类型 | 可验证关闭条件 | 预估 | 写域 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 知识图谱调研：知识点类型学 + 关系本体（含方向性）+ 点分布模式 | `task-86` | 纯调研+设计 | 《类型与关系本体 v0》+ 关系矩阵（类型×关系×方向×权重）+ 点分布评估（能否支持导航）+ 最小落地建议；**不改 `src/**`**；产物 design + kg-research-* | 3–5 天 | `docs/design`、`artifacts/agent/verify` |
| 2 | 修复 P1：预览区折叠光标多行粘贴只保留首行（task-137 定性=产品缺陷，真机 OS 注入 10/10 复现） | `task-138` | 产品缺陷修复 | 真机 OS 注入 10/10：3 行→3 行、光标落末行末字（与源码区一致）+ 矩阵加用例 + `pytest` 不降（基线 1474） | 1–2 天 | `src/memoria/ui/static/app/js/app.js`、`scripts/benchmark/surface/scenarios/selection-*` |
| 3（可选，视时间） | AG15/16/17/58 一批真机 DOM 收口 | 待建 | 半吊子收摊 | 一次真机 DOM 截图 + 重载一致性覆盖 4 条；§13 状态按证据更新（有证据才升 ✅） | 0.5–1 天 | `artifacts/agent/verify/todo`、`docs/todo.md` |

### 15.2 顺序与理由

- **1 与 2 可并行**：调研纯 docs（不写 `src/**`）；修复动 `app.js`（单写者，与可选收口不冲突）。
- **3 可选**：只有前两件按计划完成后才做；**不得为做 3 而压缩 1/2 的验收**。
- **0.4.8 已发布**；S1–S5 架构重构原定 0.5.0，**经人裁决后归入 0.4.7**（见 §16 横幅）。

### 15.3 本版不做什么

- **S1–S5 架构重构不在 0.4.8**；它随 0.4.7 发布，文档归档在 0.4.7（详见 §16）。
- KG 调研**不改 `src/**`**（只出类型学/本体/点分布设计）。
- task-85（图谱审计 3×）/ AG04 / AG56 / AG66 / AG67–70 等仍按 §14.5 推后清单处理，不因 0.4.8 重新膨胀。
- 视图模式持久化（`private_mode`）不在 0.4.8 范围（D4 裁决推后，需人另行拍板）。

## 16. 架构重构 S1–S5（原定 0.5.0，**已撤回** → 内容归入 0.4.7）

> **⚠️ 2026-10-25 人裁决**：MINOR 位只保留给「架构级/范式级」变更（0.3→0.4 = 引入 DSH）；
> S1–S5 是能力增量 ⇒ **0.5.0 撤回**（Release 与 tag 已删除，commit `8067cde6` 保留在历史），
> 内容归入 **0.4.7**（S1–S5 代码本就是 v0.4.7 的祖先，随该版安装包发布）。门槛见 `version.md §2`。

> **依据**：辩论冻结 `artifacts/agent/verify/debate/PROTOCOL.md`（commit `48ca704e`）+ 26 条协议裁决 + R-L1..L3 + R-R1..R7 + R-D1..D3。
> **计划报告**：`artifacts/agent/verify/todo/agent-arch-plan-2026-10-25.md`（阶段详表/证据/风险/复跑命令）。
> **版本关系**：本 §16 原定 0.5.0，经人裁决后**归入 0.4.7**（不是独立版本）；验收仍按 R1 级做（已由 `task-139` 完成）。
> **不做**（裁决结论 7）：不移植 Cordis 宿主运行时（scoped layers/服务注册/bundle+preset 分层）、不移植 DSH 17 个 `dsh-*` 自用技能内容、不追 `skill-office`/`tool-workspace-dependencies`。

> **✅ 已发布 0.5.0（2026-10-25，第二次）**：tag `v0.5.0` → **annotated tag 对象 `b43306e4`**，**commit `8067cde6`**（两者不同：annotated tag 有自己的对象 sha；核对时勿混用）。资产 2 件（win64 约 1.18 GB / lite 约 35 MB）。
> **⚠️ 命名注意**：本次用 `Memoria-v0.5.0-lite.zip`（**漂移**，见 `AG108`）；canonical 是 `-win64-lite.zip`。已发布资产不改名。
> **⚠️ 勿引用 `release-0.5.0-record.md`**：那是**被撤回**的首次发布记录（tag `c7c5fb39`，12:26），与本次无关；本记录见 `8067cde6` 提交信息与 `release-0.4.7-record.md` §一（发布顺序）。
> R1 重验收 `task-139`（HEAD `093dac0e`）：五份旧验收逐条复核 + 必红重证明 + 12 剧本 12/12 + pytest 1474 passed，报告 `artifacts/agent/verify/todo/0.5.0-acceptance-reverify.md`。
> **0.5.0 body 保留更正声明**：S1–S5 代码已随 0.4.7/0.4.8 发布但当时未提（见 `8067cde6` 提交标题）。§16.1–16.5 原计划详情 → [design/ledger-archive-2026.md §10.10](design/ledger-archive-2026.md)。

***

## 17. 团队插件完善项（team-plugin / Agent Teams；2026-10-25 登记，todo-owner）

> **依据（L8）**：计划正文在 [design/team-plugin-roadmap.md](design/team-plugin-roadmap.md)（P0–P4 逐条验收）+ [vision](design/team-plugin-vision.md)；本表只做**索引与状态**，不复制正文。
> **范围**：团队插件（DSH Agent Teams）自身能力完善，**不占产品版本**（0.4.8/0.4.9/0.5.0 节奏不变）。**状态**：P0 ⏳（前置=DSH 重建，需人时间窗）｜P1 ⏳（含 P1-8）｜P2 部分（P2-4 ✅ / P2-1 ❌）｜P3 ⏳｜P4 ⏳（digest 先行）。

| 阶段 | 条目（可 grep：team-plugin / 团队插件 / Agent Teams / P0–P4 / P1-8） | 状态 | 指针/验收 |
| --- | --- | --- | --- |
| P0 | 版本对齐与契约升级（v3→v4；「声明>插件」改拒绝，默认开关 off） | ⏳ 待做 | roadmap P0-1..P0-5；`contractNotice status=ahead` |
| P1 | 义务强制化：mode 必填拒绝 / complete 证据增强 / claim 写域冲突拒绝 / team_decide / 声明≠事实证据契约 / digest 骨架 / 用户文档校验 | ⏳ 待做 | roadmap P1-1..P1-7 |
| **P1-8** | **研讨会/辩论编排（`team_debate`）** | ⏳ 待做（本轮手工 fixture 已证重复、易漏） | 见下方「P1-8 实证」；fixture=本轮 KG 辩论四阶段产物 |
| P2 | 监督角色（P2-0..P2-6；**P2-1 ❌ 已验证不可行**；**P2-4 ✅ 已落地**） | 🔄 部分 | 见下方「P2 细节」；`scripts/agent/release_preflight.py` |
| P3 | 场景 profile（角色/触发/审查/写域/交付物/文档模板）+ 3 场景试点 | ⏳ 待做 | roadmap P3-1..P3-4 |
| P4 | 产品化：用户可读 digest 先行 → Memoria 学习/复习场景 → AOCI/Xerj → 独立 DSH 插件包 | ⏳ 待做 | roadmap P4-1..P4-5；**P4-5 纪律项单列**：对外分发前必须内部跑满 2 个版本；vision §9（digest 5 分钟三问） |

**P2 细节（不美化）**：P2-0 = Lead 代持定时唤醒（`schedule_create` → resume Lead → `send_message` 唤醒 supervisor）；**P2-1 ❌ 已验证不可行**（四工具挂载=是、调用=拒；`subagent_session`；换 preset/升级 v4 无效）；P2-2 模板 / P2-3 schema / P2-4 ✅ `release_preflight.py` / P2-5 wrapper 原型 / P2-6 S1–S6。

**P1-8 实证（本轮 KG 辩论，2026-10-25）**：Lead 手工编排 = 4 `spawn_teammate` + 8 `send_message` + 4 `wait_agent` + 2 份 Lead 文书 + 阶段状态手工维护；产出 **13 条裁决**、推翻 task-86 D1、四提案全部自推翻 ⇒ 重复/易漏/不可机检。
**L10 说明（证据→建议）**：本条不是凭感觉加项——fixture 完整（14 次工具调用 + 13 条裁决可复核）；建议做成插件工具（`team_debate`）而不是再写文档规范。
**P2-1 事实（不美化）**：teammate 工具表挂载 schedule 四件套=**是**，调用=**全部被拒**；`schedule_create`/`schedule_delete` 同样被拒；**会话类型级禁止，换 preset/升级 v4 均无效** ⇒ 监督角色只能走 P2-0（Lead 代持）+ B（契约门禁）。
**不做什么**：不把团队插件塞进 0.4.8/0.4.9/0.5.0；不因本项改产品发布节奏；不恢复「teammate 自触发」（已证不可行）。

***

## 18. 0.5.x 导出/导入板块（2026-10-26 人定方向；Q1/Q2/Q3 已裁决）

> 计划全文（P0 12 项 / 4 批 / 四组矩阵验收 / 人裁决）见 [design/export-import-0.5.md](design/export-import-0.5.md) §7–§12。**Q1 都要**：两皮肤（a Memoria 只读=默认 / b 纯文本）× 两形态（单 html / 文件夹）= **四组组合都做**，正交不设限；**Q2 省电=待测**（未测不得作卖点）；**Q3 v1 只导出**、导入延后。批次：B1 内核+文件夹+a → B2 单html+多选全选 → B3 纯文本皮肤 → B4 矩阵回归；v1.1 只延后高级体验，不延后组合。
