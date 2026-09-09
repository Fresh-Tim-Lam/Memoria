# Memoria 待办清单（整理版）

> 整理日期：2026-08-20。由原 to-dolist.md 与 dicussion.md 合并去重，按功能域归类；2026-08-22 追加文件树右键菜单（重命名/删除/新建）与粘贴换行条目；2026-08-29 追加 P04（右键文件夹「以 Memoria 打开」+ 打开前安全检查）；2026-08-30 docs 目录体系重构（standards/context → conventions/guides/reference + AGENT.md 现代分区）。
> 状态标记：✅ 已完成 / 🔄 进行中 / ⏳ 待做 / 💡 方向性（需再规格化）/ 🔴 Bug / ⬇️ 最低优先级

***

## 0. 当前进行中（焦点）

- 🔄 样式笔刷：预览模式涂抹后选区保持（用户反馈纯预览模式下应用样式后选区消失，分栏模式正常；harness 多次复现未果，待用户确认环境/操作细节后定位）
- 🔄 样式笔刷：同行含公式涂抹混乱（映射修复已上，验证中）
- 🔄 M5 桌面壳收尾：窗口原生动画/顶栏拖拽/圆角/最大化已达成；剩余图标与安装体验、更新通道
- 🔄 语言系统 i18n（中英语言包）：①②完成（清单 + 规范）→ ③ 机制已落地（i18n.js + zh-CN/en 包 + 设置→显示即时切换 + 首批静态文案）→ ④ 整理语言包进行中：2026-09-03 已迁移「检查」功能链路（index.html 检查弹窗 / app.js 状态栏·角标·检查弹窗·图谱建边提示 / check-settings.js 设置→检查页）并落地后端检查消息 code+params 本地化（en `check.issue.<code>`，未知 code 回退中文；§5.1）；同日补齐相邻文案（图片管理/诊断/清理 `img.*`、图谱空态提示 `graph.hint.*`、共享「请先打开知识库」`app.openKbFirst`、检查相关 RPC 错误按 code 翻译）；link-context-menu.js 右键菜单已整文件接入 `menu.*`（含源码/预览「插入图片」对齐）；2026-09-04 edit-handler.js 编辑块工具栏已整文件接入 `edit.block.*`（块类型标签/语言/类型/符号/对齐/大小/名称工具、行内公式、图片名称开关、编辑模式切换提示，32 候选清零）；同日图谱/检索设置页整文件接入（graph-settings.js `graph.settings.*` + 示例图 `graph.sample.*`、graph-label.js `graph.labelModes.*`、search-settings.js `search.settings.*`，71 候选清零，设置示例图随语言重建）；2026-09-04 编辑块工具栏之取色器/画笔状态与自定义颜色管理已原位接入 `color.*`（8 键）+ `brush.*`（11 键），候选清零该区段；此后剩余 UI 文案迁移改走「app.js 拆分专项」（下条：随拆分同步 i18n，当前 app.js 候选 0 —— app.js 界面文案清零达成，i18n-inventory 为空清单）
- ✅ 演示截图迁出 docs → `resources/screenshots/`（2026-09-03，git mv 保历史；README 双语引用 14 处同步）；新增 conventions/readme-i18n.md（README.md↔README.cn.md 双语 + 截图收录/存放维护规范）；docs 不再存截图类二进制资源
- 🔄 app.js 拆分瘦身（先拆分、随拆分同步 i18n）：已抽 `js/import-flow.js`（导入）、`js/toolbar-search.js`（搜索）、`js/image-tools.js`（图片）、`js/kb-check.js`（KB 检查/徽标/静默检查）、`js/file-tree.js`（文件树：渲染/展开/右键新建·重命名·删除/切换，复用 app.js 通用右键浮层与确认弹窗，新增 tree.* 20 键）；app.js →10.9k 行、i18n 候选 496→0；`window.MemoriaApp` 门面承载 app 私有服务。2026-09-04 取色器/画笔/自定义颜色区段文案已原位 `t()` 化（color.*/brush.*），结构抽取仍待 editor-styles 层（画笔与编辑格式管线耦合、引用保留在 app.js 的 FT_MENU_ID 浮层）；同日图谱侧栏分组页签 + 构建/加载状态接入 `graph.*`（graph.group.*/graph.build.*/graph.loadFailed）；又同日应用启动/KB 开关/状态栏/文件打开与加载/标签关闭/文件状态统计接入 `app.*`（status.kbLoaded/kbOpened/kbEmpty/kbEmptyDetail/waitingBackend、loading/loadFailed/listFailed/apiUnavailable、stat.kpLines/errors/warnings/sidecar）；再同日预览加载/自检/链接一致性提示/KP 列表空态接入 `preview.*`（loadNotReady/rendering/renderFail/okDetail/failDetail/brief/incomplete/selfcheck/linkAuditHint，TeX 摘要复用 preview.math.texError）与 `app.kpList*`（SelectFile/NoKp/OnlyProposals/Hint）；配置文件弹窗「链接审计/匹配」区段接入 `cfg.*` 51 键 + `common.delete`，`cfg.` 前缀登记；同区「链接 Tab/待确认 Tab/概要·校验/KP 弹窗 Tab/忽略·刷新状态」追加 `cfg.*` 43 键（linktab/pending/config/panel.tabs/match.scanFail），7 函数接入；KP 弹窗「边」页接入 `cfg.edge.*` 34 键（4 函数）；KP 弹窗「范围编辑器+标题+标识/描述」接入 `cfg.range/cfg.kpModal/cfg.kpIdent` 19 键（保存按钮复用 common.ok）；KP 弹窗「Tag/别名/描述候选编辑器」接入 `cfg.kpTag/cfg.chip` 22 键（9 函数）；「aux/建议/合并 + 待确认直接确认·全部确认 + 跳转/确认跳转」接入 `cfg.aux/cfg.confirm/cfg.jump` 29 键（7 函数）；链接编辑器主体区接入 `cfg.linkEdge/cfg.linkSave/cfg.linkMeta` 36 键（7 函数）；链接保存/扫描/挂接/移除/删除/点击解析/预览链接 title/图谱提示流程接入 `cfg.linkSave(+15)/cfg.match(+16)/cfg.linkOps/cfg.linkClick` 51 键（14 函数）；样式错误消息+格式化状态+剪贴板/粘贴接入 `cfg.style/cfg.clip` 19 键（24 处替换）；扫描器规则扩展剔除自定义 `log("TAG",…)` 开发日志行；KP 定位辅助预览接入 `cfg.assist` 8 键（ellipsis 上/下模板、范围预览、预览模式 aria、源码/Markdown、rangeError、默认名）；KP id 迁移/保存/删除/range 校验流接入 `cfg.kpSave` 23 键（rename/delete confirm 含换行、迁移状态、各校验 detail）；收尾清零（errorLabel map→cfg.kpErr 4 键、匹配行定位→cfg.match located/substringBlocked/checkboxHint、「请先打开文件」复用 app.openFileFirst）—— **app.js 界面文案候选清零（0 行）达成，i18n-inventory 为空清单**；真机回归待用户执行（导入/搜索/图片/检查/文件树/语言切换/画笔取色/图谱构建/文件打开/预览异常与空态/配置弹窗链接·待确认 Tab/KP 弹窗各页/待确认确认流/跳转/链接编辑器全流程/样式·粘贴）
- ✅ 0.3.0 导入体系（M0–M7 全 ☑）：场景/契约见 [docs/reference/import-spec.md](reference/import-spec.md)，模块化计划见 [docs/reference/import-plan.md](reference/import-plan.md)。统一导入向导（三源卡→预览→冲突决策→复制反馈 JSON/MD→结果）+ Agent 整理提示词事实源已随 M7 落地；2026-09-05 GUI 真机回归用 browseragent × `docs/example/import-test/_harness_import.py`（KB=empty3，--fresh）跑通：三类源 × {新建/幂等/冲突(跳过·覆盖·重命名)} 全 ✓ + 磁盘结构核对（md/sidecar/图谱节点与边），记录与遗留观察见 import-plan M6.2 回归记录；导入工具栏并入「文件」下拉（打开/导入/导出预留）

***

## 1. 配置窗口（合并「知识点解析」+「审核」）— 核心大项

| ID  | 任务                                                                                  | 状态 |
| --- | ----------------------------------------------------------------------------------- | -- |
| C01 | 配置入口：点击「配置」呼出配置窗口                                                                   | ⏳  |
| C02 | 左侧文件树（文件夹展开子目录）；点击文件配置 / 「当前文件」按钮快速定位                                               | ⏳  |
| C03 | 右侧三段式布局：顶栏 `id + description`；下方 tag 分「已有（上）/候选灰色（下）」，多选「上移」应用、「下移」撤回、手动创建、「解析」重新推荐 | ⏳  |
| C04 | UI 风格：右侧编辑框去掉外框包裹与框间隔，统一左栏文件树风格                                                     | ⏳  |
| C05 | 数据模型改造：知识点为最小单位（唯一 id + tags 上下栏管理），文件只是容器                                          | ⏳  |
| C06 | 配置页右侧顺序：文件描述 → 知识点配置（点击下拉展开/再点收回）→ 链接管理（`[[]]` 文本即链接；知识点 id 自带锚点不用管）                | ⏳  |
| C07 | 修改 id 自动更新所有相关链接；修改 tag 不破坏链接                                                       | ⏳  |
| C08 | 自动解析：识别库内/库外知识点 → 推荐创建 KP 单元并解析跳转锚点；识别可建边文本 → 推荐创建（触发时机：用户点击）                       | ⏳  |
| C09 | 高级选项 → 设置内容完善                                                                       | ⏳  |

***

## 2. 链接系统

| ID  | 任务                                                               | 状态 |
| --- | ---------------------------------------------------------------- | -- |
| L01 | 选中文本右键 → 创建链接窗口：智能推荐 + 加号手动添加（输入 id/tag 匹配）+ 多选定向                | ⏳  |
| L02 | 右键虚链接/链接 → 编辑链接窗口：修改 id/tag 重新匹配、未定向虚链接匹配定向（多选）、删除某链接；全部删除则该跳转消失 | ⏳  |
| L03 | 公式也可以作为链接被点击                                                     | ⏳  |
| L04 | `[[**aaa**]]` 类链接预览错误（\*\*aaa 无法选中创建链接）                          | 🔴 |
| L05 | http 链接点击行为完善                                                    | ⏳  |

***

## 3. 检索引擎

| ID  | 任务                                                      | 状态 |
| --- | ------------------------------------------------------- | -- |
| S01 | 搜索/匹配功能封装成统一内核（系统多处使用推荐匹配）                              | ⏳  |
| S02 | R17 SearchKernel v2：双向生长汇合检索（查询侧语义扩张 + 库侧沿图/标签生长，按路径计分） | 💡 |
| S03 | R16 检索反馈循环·库内模型（点击/有用无用学习，存 `.memoria/`，本地离线可删）         | ⏳  |
| S04 | R04 智能链接推荐（本地小 LLM 提议层，输出须用户确认才写 sidecar）               | 💡 |
| S05 | R05 公式级语义检索（LaTeX → AST/规范化串 单独索引）                      | 💡 |

***

## 4. 图谱

| ID  | 任务                                                                                                        | 状态 |
| --- | --------------------------------------------------------------------------------------------------------- | -- |
| G01 | R07 图谱推理·新边提议（需先定边属性专章；建议边不自动写入，用户逐条采纳/忽略）；图谱边类型的完善，整理现实生活中，人们阅读、学习或者复习场景下，看到某个文字想要“跳转”有什么类型，或者说知识点之间的边类型 | ⏳  |
| G02 | Bug：边抑制之后点击构建/刷新，图谱仍然显示该边                                                                                 | 🔴 |
| G03 | F03 增加新的力场范式方便图谱观看（由 G04 银河样式实现）                                                                        | ✅ |
| G04 | 图谱样式切换：新增「银河 Galaxy」视觉样式（星空星点渲染：亮度随连接度、径向光晕、深空底色、交互时焦点星点闪烁；布局仍为力导向，2D/3D 通用）+ 设置内样式修改 UI（光晕强度） | ✅ |

<br />

***

## 5. 编辑器 / 富文本

| ID  | 任务                                                                  | 状态 |
| --- | ------------------------------------------------------------------- | -- |
| E01 | R15 富文本 Markdown 编辑（加粗/斜体/高亮/字号/上下标/荧光笔/Undo-Redo；公式与 MathJax 预览一致） | 🔄 |
| E02 | 表格内部也可以编辑（同步编辑板块）                                                   | ⏳  |
| E03 | 编辑模式下修改链接的内容要自动处理                                                   | ⏳  |
| E04 | 双击公式进入公式编辑区，工具栏切换到公式栏（行内公式 enterInlineMathEditMode + 块级 math_block 符号面板） | ✅ |
| E05 | 阅读区选中文本后通过工具栏应用/编辑样式                                                | ⏳  |
| E06 | 文本批处理按钮：`\(` `\)` → `$`、`\[` `\]` → `$$`                            | ⏳  |
| E07 | Bug：无法复制                                                            | 🔴 |
| E08 | Bug：分栏状态下文本编辑功能检验不通过                                                | 🔴 |
| E09 | U04 预览/源码切换定位到对应位置（非首个位置）；分栏可配置是否自动定位                               | ⏳  |
| E10 | U08 设置内部数值范围过小，需扩大                                                  | ⏳  |
| E11 | U09 右键创建知识点时自动剔除「3.3.4.2」类编号前缀                                      | ⏳  |
| E12 | F04 IDE 缩放功能                                                        | 💡 |
| E13 | Bug：预览区域粘贴时换行符被忽略，导致代码格式错误                                          | 🔴 |
| E14 | 完善源码-预览-分栏区域的复制粘贴功能（换行处理、格式保持等；2026-08-29 源码区右键粘贴已修复） | 🔄  |
| E15 | 源码编辑器多行粘贴换行丢失                                                       | ✅  |
| E16 | 源码编辑器快照式撤销/重做（覆盖输入/Enter/合并删除/粘贴，Ctrl+Z/Y）                          | ✅  |
| E17 | 新建文件缺 .md 后缀自动补齐（与前端提示一致）                                           | ✅  |

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
| I01    | R11 约定格式 KB 导入包（md + sidecar + manifest，应用内导入向导 + validate\_kb） | ⏳      |
| I02    | R08 图片/图表渲染（①图片引用+预览 ②Mermaid/图表块渲染；③数据生图更远）                    | ✅      |
| I03    | F01 接入 LLM API，结构化处理，交互中有意义的内容智能导入知识库                           | 💡     |
| I04    | F02 一键应用推荐配置（KP 名称/id/标签/描述 + 智能加链；效果用 benchmark 衡量）            | 💡     |
| I05    | R03 HTML 导入（A 直接渲染 / B 转 Markdown 未定）                           | ⬇️     |
| <br /> | 给程序顶栏的”导入“添加一个项为提示词，点击后弹出一个页面让用户复制提示词并且说明提示词使用方式                | <br /> |

***

## 8. 壳与发布

| ID  | 任务                                        | 状态 |
| --- | ----------------------------------------- | -- |
| P01 | M5 收尾：图标/安装体验、更新通道（非 Windows 壳后续再议）       | 🔄 |
| P02 | R10 新手引导（首开 KB / 空文件树 / 无 KP 引导流；示例库一键打开） | ⏳  |
| P03 | R13 UI 语言切换（壳 + 前端 i18n，不自动翻译 md 正文）      | ⏳  |
| P04 | Windows 右键文件夹「以 Memoria 打开」+ 打开前安全检查（2026-08-29 登记） | ⏳  |

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
| V02    | R06 遗忘曲线·主动复习（进度存 `.memoria/`）                      | 💡     |
| V03    | R12 全库静态离线 HTML 导出（只读子集）                            | 💡     |
| V04    | 导出 PDF                                              | 💡     |
| V05    | Android 端                                           | 💡     |
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
- 🔄 样式笔刷同行公式涂抹（映射修复后验证中）

### 10.2 文档标记完成（历史）

- ✅ 边模型升级（强/弱边 + 实线/虚线）、图谱面板拖拽宽度、3D 图谱（Three.js）、布局模式（Radial/Top-down/Free-force）、节点点击跳转 + anchor 定位
- ✅ Bug B01-B08 全部修复；UI/UX U01/U02/U03/U06/U07/U10/U11/U12 修复
- ✅ R02 KB 根目录安全标记、R09 Lexical 强化模糊搜索、R18 SearchKernel v1.5（aux + 多模型 + 统一建议）
- ✅ 检索量化基准：BEIR SciFact → Memoria KB（gold/minimal/skeleton 三档 profile）+ qrels（`scripts/benchmark/`）
- ✅ 知识文件整理导入提示词 + 平面导入文件格式规范（详见附录，可直接给 AI 使用）

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

### A. 一致性 / 注册内核

| # | 机制 | 现状 |
|---|---|---|
| A1 | sidecar 镜像 + `file` 字段 + 校验 + 级联（path_cascade.apply_path_move） | ✅ |
| A2 | manifest 基线/差分/幂等移动/touch | ✅ |
| A3 | pending 项路径同步（重命名已接入） | ✅ |
| A4 | 图片注册表：doc 增量 / 全量 / 自动检查 / 清理 | ✅（渲染 bug 已修） |
| A5 | KP range 双端定位（locator）+ 保存重锚 heal | ✅ 2026-09-09 |
| A6 | 词法/embedding 索引：侧车写后同步重建 | ⚠️ 待作业化（重，P3） |
| A7 | 原子写（tmp + os.replace） | ✅ M1 已补（2026-09-09）：md 正文保存（document.py）与 ui-settings（storage/ui_settings.py）；YAML/registry 原已原子 |

### B. 操作 / 作业

| # | 任务 | 现状 |
|---|---|---|
| B1 | 文件重命名（stem 引用改写 / KP-shadow / 冲突 / pending+registry 级联） | ✅ 已加固 |
| B2 | 文件夹重命名 dir_rename（整树移动 + 逐文件级联） | ✅ 新增（partial 级联失败已上屏，2026-09-09 复核修正），**待真机验收** |
| B3 | F2 快捷键（文件/文件夹，捕获阶段 + 仅拦可见弹窗） | ✅ 新增，**待验收** |
| B4 | 保存 autosave / flush / 脏标记 | ✅ |
| B5 | KP 创建/更新慢 RPC（原阻塞 UI） | ✅ 主因已修（2026-09-09）：pending 存储 YAML→JSON（自动迁移）+ confirm/delete 改单文件范围同步 + 弹窗关窗先于图谱刷新；真机 modal 链 2442.6→981.6→**485.7ms**，后端稳态 4s→285.7ms（详见 [results/kp-confirm-2026-09-09.json](../scripts/benchmark/maintenance/results/kp-confirm-2026-09-09.json)）；剩余词法索引全库重建作业化归 M3/G4（P1） |
| B6 | md 相对路径链接在目录重命名时自动改写 | ❌ 已知边界（待扩展） |
| B7 | 导出知识库包（bundle） | ⏳ design 草稿待评审 |

### C. 视图 / 静默刷新

| # | 任务 | 现状 |
|---|---|---|
| C1 | 文件树重映射 + 刷新（rename 后 applyRenameUi） | ✅ |
| C2 | KP 面板静默刷新（ranges_resynced 触发） | ✅ 首期 |
| C3 | 预览范围带静默重绘（无滚动/闪烁） | ⏳ P2 |
| C4 | 图谱节点/标签局部刷新 | ⏳ P2 |
| C5 | maintenance-jobs 调度内核（合并/优先级/idle/epoch/flush） | ⏳ 设计稿 |

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
| E3 | design：export-plan / maintenance-jobs（草稿，2026-09-09 复核恢复 export-plan） | ⏳ 待评审 |
| E4 | docs-management / to-dolist 修订登记 | ✅（2026-09-09 复核补登记 to-dolist §12 行） |

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
- 出口门禁：scheduler VM 单测（replace=true/false、merge、prio、epoch/flush）全 PASS（✅ 已通过）｜bumpEpoch `[真机]` 验证陈旧丢弃生效｜`[job]` 日志 `queued=0` 收敛｜回归冒烟 PASS → commit `G3`

**G4 · 作业化落地**
- 范围：M6 KP 创建/更新作业化（入队即放行）｜M3 词法索引移出同步保存路径（合并+后台）｜C4 图谱局部刷新
- 入口：G3 门禁通过（作业底座就绪）
- 出口门禁：M6 连续 2+ 次创建无阻塞计时上限 + 完成后 KP 可见｜M3 前后耗时/重建次数对照 + 检索一致 + 合并计数断言｜C4 局部刷新不整图重绘（代码+`[真机]`）｜回归冒烟 PASS → commit `G4`

**G5 · 维护面收敛（M7）**
- 范围：F01 检查/审计、F02 路径漂移修复、F03 图片引用诊断修复 → 评估后登记/纳入调度；重活线程池与定时队列
- 入口：G4 门禁通过
- 出口门禁：validate CLI 0 issue｜repair_path_cascade 干跑与实操一致｜diagnose 结构化输出合法｜纳入登记表与 i18n 核对｜回归冒烟 PASS → commit `G5`

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
