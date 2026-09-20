# Memoria 待办清单（整理版）

> 整理日期：2026-08-20（由原 `to-dolist.md` 与 `dicussion.md` 合并去重后按功能域归类）。
> 维护规范：[conventions/ledger-maintenance.md](conventions/ledger-maintenance.md) —— K1 真开放 / K2 代码完成·验收未闭环 / K3 待评审 / K4 已收口；证据锚必填；规则 8：体积 ≤36 KB，已收口条目按批次出表入 §10。
> 状态标记：✅ 已收口 / 🔄 进行中 / ⏳ 待做 / 💡 方向性（需再规格化）/ 🔴 Bug / ⬇️ 最低优先级。
> 2026-09-16 按规则 8 压缩至预算内：开发流水账出表（i18n 迁移明细见 [conventions/i18n.md](conventions/i18n.md) 修订记录；拆分与文档登记见 [docs-management.md](conventions/docs-management.md)；版本级变更见 [version.md §7](conventions/version.md)）；旧文末两段用户粘贴的 bug 记录按规则 8.3 归位（E22 补复现记录、新增 E23）。
> 2026-09-19 按规则 8.2 再清理（表头逐日追述与 §10.4 流水账出表；新增 §13 AG12–AG16）。

***

## 0. 当前进行中（焦点）

- 🔄 样式笔刷·预览模式涂抹后选区保持：纯预览模式应用样式后选区消失（分栏模式正常）；harness 多次复现未果，待用户确认环境/操作细节。K1（无修复证据）
- 🔄 样式笔刷·同行含公式涂抹混乱（旧 §10.1 内重复记作「样式笔刷同行公式涂抹」）：映射修复已在 `app.js:9217-9218,10640`。K2（验证未闭环，无通过证据）
- 🔄 M5 桌面壳收尾：窗口原生动画/顶栏拖拽/圆角/最大化已达成；剩余图标与安装体验、更新通道。K1
- 🔄 app.js 拆分瘦身：已抽 5 个子系统 js（file-tree / import-flow / toolbar-search / image-tools / kb-check），app.js ~10.9k 行；界面文案候选清零（i18n-inventory 空清单）。下一步：editor-styles 层抽取（`FT_MENU_ID` 浮层引用仍在 app.js）；真机回归待用户执行。K1
- 🔄 **P06 打包态在他人机器启动崩溃**（根因 = **Mark-of-the-Web**；修复 = 随包 `Memoria.exe.config`（`loadFromRemoteSources`）+ 失败可读弹窗 + 交付面说明；v0.3.4 已重新构建并替换资产）。K2（待在报错机器复验，见 §8 P06 详情）

***

## 1. 配置窗口（合并「知识点解析」+「审核」）— 核心大项

| ID | 任务 | 状态 |
| --- | --- | --- |
| C02 | 配置窗内左侧文件树 + 「当前文件」快速定位 | 🔄 K1（配置窗仅 kp/links/pending 三 Tab，无文件树/无「当前文件」；主界面文件树与点击切换已在） |
| C03 | 右侧三段式布局：顶栏 `id + description`；tag 分「已有（上）/候选灰色（下）」逐 chip 点击，支持手动创建、「系统建议」重新推荐 | 🔄 K1（上下分区/逐 chip/手动创建/系统建议已在 `app.js:4008-4091,4121`；多选批量上移/下移未实现） |
| C04 | UI 风格：右侧编辑框去掉外框包裹与框间隔，统一左栏文件树风格 | 🔄 K1（列表项已扁平化去外框 `app.css:1637-1646`；「统一左栏文件树风格」无专门证据） |
| C06 | 配置页右侧顺序：文件描述 → 知识点配置（下拉展开/再点收回）→ 链接管理 | ⏳ K1（现状与描述不符：实为 kp/links/pending 三 Tab，KP 配置走独立弹窗，`app.js:2272,3020-3030`） |
| C08 | 自动解析：识别库内/库外知识点 → 推荐创建 KP 并解析跳转锚点；识别可建边文本 → 推荐创建 | 🔄 K1（KP 推荐已实现：`heading_proposals.py`/`mention_proposals.py`/`definition_proposals.py`；「可建边文本→推荐创建」为 `disabled` 占位 `app.js:2180-2197`） |
| C09 | 高级选项 → 设置内容完善 | ⏳ K1 ❓（无法定位：设置页为 6 个具名 Tab，无「高级选项」区，原描述不足，需澄清） |
| C10 | 弹窗层级混乱：`.-modal` 的 z-index 1000 低于搜索面板 9000 / 右键菜单 10050 / 颜色选择器 20000 / flash 浮层 12000，弹窗可被浮层遮挡 | 🔴 K1（`app.css:4218` vs `2096`；来源 agent-guide/01） |

***

## 2. 链接系统

| ID | 任务 | 状态 |
| --- | --- | --- |
| L01 | 选中文本右键 → 创建链接窗口：智能推荐 + 加号手动添加（输入 id/tag 匹配）+ 多选定向 | 🔄 K1（创建窗/多选定向/手动 id-tag 搜索已实现 `app.js:5134,5189-5195,5238-5259`；智能推荐为 `disabled` 占位 `app.js:5197-5208`） |
| L03 | 公式也可以作为链接被点击 | ⏳ K1（未实现：解析器视 `[[…]]` 为纯文本、公式为独立原子节点，`parser.js:222-235` / `renderer.js:385-391,421-427`） |
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
| G05 | 图谱节点渲染算法优化，提升渲染性能，设置benchmark单独对图谱引擎性能测试 | 🔄 K1（**主体已达成，待补最后一步**；规划与逐项实测数据全部在 [design/graph-benchmark.md](design/graph-benchmark.md)。已落地：**D1 帧预算化**（目标档整帧 p95 大降）、**D2 Barnes-Hut 近似排斥**（`graph-bh-tree.js`，θ=0.9，`bh:false` 保留精确路径供同 build A/B）、**X3**（`distanceMin` 下限 + 位移上限取代 `Math.random()`）、**X4 装载卡死根治**（warmup 工作量上限 + worker 超时）。**未达标项**：单 tick ≤20ms 仅 partitioned 达标，small_world/star 仍 33–35ms ⇒ 下一步 **D2b 树扁平化/免分配**（估 2–3×，目标 ~10ms）。用户已定：不设节点间距指标、不作质量门禁） |

***

## 5. 编辑器 / 富文本

| ID | 任务 | 状态 |
| --- | --- | --- |
| E01 | R15 富文本 Markdown 编辑 | 🔄 K1（加粗/斜体/高亮/荧光笔/字色/Undo-Redo 已实现 `index.html:154-184`、`app.js:7196-7198`、`lexer.js:326-335`；字号/上下标仅语法层支持，工具栏无入口） |
| E02 | 表格内部也可以编辑（同步编辑板块） | ⏳ K1（未实现：有「编辑表格/+行/+列」按钮但无事件绑定、内容不写回，`edit-handler.js:953-958,1451-1452`） |
| E03 | 编辑模式下修改链接的内容要自动处理 | ⏳ |
| E06 | 文本批处理按钮：`\(` `\)` → `$`、`\[` `\]` → `$$` | ⏳ |
| E07 | Bug：无法复制 | 🔴 |
| E08 | Bug：分栏状态下文本编辑功能检验不通过 | 🔴 |
| E09 | U04 预览/源码切换定位到对应位置；分栏可配置是否自动定位 | 🔄 K1（切换定位已实现 `app.js:1578-1668`；分栏自动定位配置项缺） |
| E10 | U08 设置内部数值范围过小，需扩大 | ⏳ K1 ❓（无法定位 U08 所指控件：字号 12-28 / 缩放 0.8-1.5 / labelMaxLen 4-20 均无从对应，需澄清） |
| E11 | U09 右键创建知识点时自动剔除「3.3.4.2」类编号前缀 | ⏳ K1（未实现：`app.js:11196-11207` 取首行 trim 后直接截断，无编号剥离） |
| E13 | Bug：预览区域粘贴时换行符被忽略，导致代码格式错误 | 🔴 |
| E14 | 完善源码-预览-分栏区域的复制粘贴功能 | 🔄 K1（粘贴换行处理已实现 `app.js:7411-7511,7513-7538,9641-9673`；「复制」与格式保持未做，无 copy 监听、现仅写 text/plain） |
| E18 | 工具栏 tooltip 声称 `Ctrl+B` / `Ctrl+I`（及 `Ctrl+S`）实际未实现 | 🔴 K1（`index.html:153-154`、`i18n/zh-CN.js:593-594`；全库无按键处理器；来源 agent-guide/03） |
| E20 | 保存会吞掉 frontmatter 与正文之间的空行（`---` 后空行被移除）→ 用户库里产生纯空白差异、污染 git 历史 | 🔴 K1（harness 打开并保存 showcase `README.md` 后 `git diff` 显示 `---` 后空行消失） |
| E22 | 跨块选区删除被静默拒绝：`deleteSelectionMulti` 命中 `list` / `blockquote` / `NON_EDITABLE`（code_block·math_block·mermaid·table·frontmatter）任一即 `return false`，而 `beforeinput` 已 `preventDefault()` → 按 Backspace 毫无反应、无任何提示 | 🔴 K1（`app.js:9446-9452` + `edit-handler.js:596-624`；对照：普通段落→`<details>` 选区 `ret:true` 且删除范围与源码行完全正确 → 问题在「拒绝时无反馈」）。**用户原始复现（2026-09-14 粘贴记录）**：在预览区拖拽选中含 `<details><summary>flowchart</summary>` 的区块后删除，结果删掉了**前一行**而不是选中内容 —— 与上述「范围正确」的对照结论冲突，需在真机复测确认是同一根因还是独立缺陷 |
| E23 | 打包态偶发：Mermaid 渲染失败时（`Syntax error in text / mermaid version 11.16.0`）窗口整面上移、报错块占位挤占 UI，导致「最大化 / 还原 / 关闭」按钮点不到，只能从系统底栏关进程重开才恢复。**难复现**（用户报告，未定位） | 🔴 K1（用户报告 2026-09-14；与 E21「不再展示原生错误图」是否同根因待验 —— 若 E21 的 `suppressErrorRendering` 已消除该占位，本条可关闭） |

***

## 6. 文件树管理

T01–T03 已按规则 8.4 出表（见 §10）。

| ID | 任务 | 状态 |
| --- | --- | --- |
| T04 | 文件夹无法折叠（含当前文件时点折叠即回弹）+ 文件树 emoji 换 dsh 图标 | 🔄 K2 待真机验收（根因 `file-tree.js:451` 重渲时自动展开覆盖用户折叠；修复 = 用户折叠记忆 + 重渲守卫 + 真 reveal 清除（末尾块 539-557）；图标借 dsh `ui-primitives`（末尾块 521-716、`app.css` 5522-5583）；2026-09-20 无侧车「暗淡」态 0.45→0.55（`app.css` 5601-5613）；无验收落盘） |

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
| P07 | UI 视觉收敛（滚动条 / 标签栏滚轮 / 圆角五档 / 描边 0.5px + **分隔线档 `--border-sep`** / 阴影三档 / **横条统一 33px（`--bar-h`）** / 侧栏页签条去 13.2px 白留 / 发送按钮右对齐） | 🔄 K2（`app.css` 末尾块 + 原位改值；harness 8651–8659 实测数字见 agent-guide/01 §6–§7 与 design/ui-visual-language.md §4。**未取证**：0.5px 在 1x 仍上取整为 1px、真实 hover/滚轮、真机观感） |

**P04 详情（2026-08-29 登记）：**

- **右键集成**：注册表 `HKCU\Software\Classes\Directory\shell\Memoria`（command → `Memoria.exe --open "%1"`）；提供安装/卸载入口（打包安装器或程序内「集成右键菜单」开关）。
- **exe 入口**：CLI 支持 `--open <dir>` → 启动即加载该文件夹为知识库（对齐现有 kb 加载链路）。
- **打开前安全检查**（任一不通过 → 明确提示，不强行打开）：① 存在性（存在且为目录）② 权限（可读+可写，防只读介质写 `.memoria` 失败）③ 范围（排除 `C:\Windows`、`Program Files`、`ProgramData`、回收站、`C:\` 根等）④ 结构（含 `.memoria/` 直接打开；空目录提示可初始化；有 md 无 `.memoria` 提示将创建并写前确认）⑤ 路径（长度限制、非法/特殊字符、UNC/网络路径）⑥ 占用（已被另一实例打开 → 聚焦已有窗口）。
- **验收**：右键 → 打开指定文件夹成为当前知识库；安全项逐一构造反例验证提示正确；卸载后右键菜单消失。

**P06 详情（2026-09-18 登记；同日定位根因、修复并重新发布）：**

- **现象**：他人机器解压 `Memoria-v0.3.4-win64-lite.zip` 后启动即崩 —— `pythonnet/__init__.py:143 load()` → `clr_loader/netfx.py:47` → `RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize from <解压目录>\lib\pythonnet\runtime\Python.Runtime.dll`。
- **根因 = Mark-of-the-Web（实测）**：zip 解压出的文件被 Windows 写入 `Zone.Identifier`（ZoneId=3）；.NET 的 `Assembly.LoadFrom` 拒绝加载来源为「Internet 区域」的程序集（HRESULT `0x80131515`），而 clr_loader 的原生入口把该异常吞成 NULL，故 Python 侧只剩上面那句无细节报错。对照实验（同一 445,952 B 的 dll）：干净 → OK；打 ZoneId=3 → 失败；`Unblock-File` → OK（可逆、确定性）；给真实 `.venv` 的 dll 打标记后 `import clr` 复现出**逐字一致**的 traceback。已排除打包缺件（完整版/lite 版 105 条条目逐一相同）与目标机 .NET 版本（报错机 `Release=0x82405` ≈ 4.8，足够）。
- **修复**：**随包 `Memoria.exe.config`**（`<loadFromRemoteSources enabled="true"/>`，.NET 为「加载 Internet 区域程序集」提供的官方开关）—— 新增模板 `packaging/templates/Memoria.exe.config`，`build.py::_stage_release` 拷入、`_verify_release_bundle()` 构建末尾校验，两份 zip 清单（`operations.md §5.1`）同步加入。配套 `app_release.py::_show_fatal_dialog()`（发布态启动失败弹可读弹窗）、两份 README / 随包 `README.release.txt` / `site/**` 补系统要求与整包解压说明，并写死进 `operations.md §5.2` 的 Release 规则。
- **否决的初版做法**：启动时删 `lib/pythonnet/**` 的 `Zone.Identifier`（`runtime.py::unblock_bundled_runtime()` + 4 例单测）**已全部移除** —— 该删流操作在本机 D: 盘静默失效（`os.remove` 不抛异常、`DeleteFileW` 返回 TRUE 而流仍在，`Unblock-File` 亦无效），且属修改文件元数据；改用配置后不需要它。
- **顺带修复**：两份 zip 不再打 `Package\config\`——`_RELEASE_PRESERVE_DIRS` 会跨构建保留开发机自己的 `ui-settings.json`（含本机私人路径），整目录打包会把它发出去。
- **证据**：`artifacts/p06-motw-e2e.txt`。发布态 A/B（同一产物，只差 `Memoria.exe.config`）：无配置 → `crash.log` 内容即该 RuntimeError；有配置 → dll 仍带 MotW 也正常启动。全套 `pytest -q` 80 passed。
- **遗留**：发布包不含 PyQt6（`spec:12` 的 `_HEAVY_EXCLUDES`），「回退 Qt 壳」不可行，由可读弹窗兜底。**v0.3.0～v0.3.4 共 5 个 Release、9 个 zip 已全部重新构建并替换**（旧版由各自 tag 的 `git worktree` 构建 + 注入 `Memoria.exe.config`）；报错机器按新包复验待用户执行。同批清理了随包示例库的运行/调试产物残留（见 [docs-management.md](conventions/docs-management.md) §4.2 同日条目）。

***

## 9. 学习产品（V2+）

| ID | 任务 | 状态 |
| --- | --- | --- |
| V01 | R14 知识点沿路拼接·导出新文档 | ⏳ |
| V02 | R06 遗忘曲线·主动复习（进度存 `.memoria/`） | 🔄 K2 待真机验收（由 V06 的 FSRS 工具包实现，`.memoria/agent/review/`；代码与自测在案，无真机 results 落盘） |
| V03 | R12 全库静态离线 HTML 导出（只读子集） | 💡 |
| V04 | 导出 PDF | 💡 |
| V05 | Android 端 | 💡 |
| V06 | Trae 知识库智能体：`.memoria/agent/` 工具包（指令 + 编撰规范 + FSRS 调度）；应用内「文件 → 创建 Trae 智能体」一键生成并复制指令，规则可独立升级而无需重建智能体 | 🔄 K2 待真机验收（T1–T6 代码齐全，`kb-agent.md:239-247` 仅有自测记录，无真机 results 落盘） |
| — | 接入大语言模型 api 接口直接对话，增强检索框引擎联网场景能力，同时让用户直接在程序维护发展知识库（未编号·用户备注） | 💡 |

***

## 10. 已完成归档

> **格式**：本节是归档索引，按规则 8.4 从活动分区出表；一行一批次 = `| 日期 | ID 列表 | 一行汇总 | 证据锚 |`。**未收口条目不在本节**（原 §10.1 末尾的「样式笔刷·同行公式涂抹」属 K2 未收口项，已归位 §0）。

| 日期 | ID 列表 | 一行汇总 | 证据锚 |
| --- | --- | --- | --- |
| 2026-08 | — | 换壳 pywebview（WebView2）根治首帧冻结；窗口原生动画 + 顶栏原生拖拽（Aero Snap）+ Win11 圆角 + 最大化铺满（DWM + WndProc）；打包机制整理（scripts↔packaging 职责、构建脚本修正）；m0 → app 目录与命名整理（含 egg-info 出库）；样式笔刷公式映射修复（domToAst 跳过 MathJax 内部文本）+ 公式选中高亮 `.m0-sel-covered` | CHANGELOG 0.2.0（[version.md §7](conventions/version.md)） |
| 2026-08 | E04, I02 | 公式编辑：双击行内公式进入编辑、双击块级公式进入 `math_block` 符号面板；图片与 Mermaid：引用+预览+入库+管理+属性编辑（阶段 A–G）+ Mermaid 渲染与编辑；图片资产全链路（入库去重、管理视图/清理、宽度·对齐·名称字号、双击放大即改即存） | `edit-handler.js:1244,1844`；`git log -S I02` |
| 2026-08-29 | — | 版本号单一入口（pyproject dynamic version，改 `src/memoria/__version__.py` 一处全生效）；源码编辑器右键粘贴（无选区右键弹「粘贴」、多行逐行拆分；有选区仍弹链接菜单） | [version.md](conventions/version.md) |
| 2026-08-30 | G03, G04 | docs 目录体系重构（`standards/`/`context/` → `conventions/`/`guides/`/`reference/`，中文名 kebab-case 重命名 + AGENT.md 重写）；图谱银河 Galaxy 视觉样式（星点光晕、亮度随连接度、深空底色、焦点脉冲、设置内光晕强度，随 `ui-settings.json` 持久化） | [docs-management.md](conventions/docs-management.md)；`graph-settings.js:574-587` |
| 2026-09-03 | — | 演示截图迁出 docs → `resources/screenshots/`（git mv 保历史，README 双语引用 14 处同步）；新增 `conventions/readme-i18n.md`（README 双语 + 截图收录维护规范） | `conventions/readme-i18n.md` |
| 2026-09-03/04 | i18n ④ | 语言系统 i18n（中英语言包）：`i18n.js` + zh-CN/en 包 + 设置→显示即时切换；「检查」链路与全量界面文案迁移（`menu.*`/`edit.block.*`/`cfg.*`/`app.*`/`preview.*` 等键族），app.js 候选清零；后端检查消息 code+params 本地化 | [conventions/i18n.md](conventions/i18n.md) 修订记录；`i18n-inventory.md` 候选 0 行 |
| 2026-09-05 | — | 0.3.0 导入体系（M0–M7 全 ☑）：统一导入向导（三源卡→预览→冲突决策→复制反馈 JSON/MD→结果）+ Agent 整理提示词事实源；GUI 真机回归（三类源 × 新建/幂等/冲突全 ✓）；导入工具栏并入「文件」下拉 | [import-plan.md](reference/import-plan.md)；[import-spec.md](reference/import-spec.md) |
| 历史 | T01, T02, T03 | 文件树右键菜单：文件重命名/删除、空白区或文件夹右键新建文件/文件夹；重命名同步全库引用（正文 wikilink 改写、侧车 links/edges 与 pool 迁移，KP id 不随文件名变，新名冲突拒绝） | `file-tree.js`；`document.py:697-780` + `storage/path_cascade.py` |
| 历史 | E15, E16, E17 | 源码编辑器多行粘贴换行丢失修复；快照式撤销/重做（输入/Enter/合并删除/粘贴，Ctrl+Z/Y）；新建文件缺 `.md` 后缀自动补齐 | `git log -S E16` |
| 历史 | B01, B02, B03, B04, B05, B06, B07, B08, U01, U02, U03, U06, U07, U10, U11, U12 | Bug 批次全部修复；UI/UX 批次修复 | `git log -S U12` |
| 历史 | R02, R09, R18 | KB 根目录安全标记；Lexical 强化模糊搜索；SearchKernel v1.5（aux + 多模型 + 统一建议） | `services/search_kernel.py` |
| 历史 | — | 边模型升级（强/弱边 + 实线/虚线）、图谱面板拖拽宽度、3D 图谱（Three.js）、布局模式（Radial/Top-down/Free-force）、节点点击跳转 + anchor 定位 | `graph-engine.js` |
| 历史 | — | 检索量化基准：BEIR SciFact → Memoria KB（gold/minimal/skeleton 三档 profile）+ qrels；知识文件整理导入提示词 + 平面文件导入格式规范（已收编进 [import-spec.md](reference/import-spec.md) §4A/§12） | `scripts/benchmark/`；[import-spec.md](reference/import-spec.md) |
| 2026-09-09/10 | A1, A2, A3, A4, A5, A6, A7, A8, B1, B4, B5 | §12.A 一致性/注册内核整段收口：sidecar 镜像 + `file` 字段 + 校验 + 级联、manifest 基线/差分/幂等移动、pending 路径同步、图片注册表、KP range 双端定位 heal、词法索引后台化、原子写、终点锚 `forward_only` 漏洞修复；§12.B 文件重命名加固、autosave/flush/脏标记、KP 创建/更新提速（pending 改 JSON + 单文件同步） | `results/kp-confirm-2026-09-09.json`；`range/locator.py:45`；CHANGELOG 0.3.1 |
| 2026-09-09/10 | C1, C2, C3, C5, D1, D2 | §12.C 视图/静默刷新：文件树重映射刷新、KP 面板静默刷新、预览范围带静默重绘（`markRangeQuiet`）、调度内核 G3 落地（`scheduler.js`）；§12.D 渲染：图片缩略图渲染修复、预览颜色 hover/选区 | `scheduler_vm_test.js`；CHANGELOG 0.3.1 |
| 2026-09-09/10 | E1, E2, E4, E5, E6, E7, E8, E9, F01, F02, F03 | §12.E 测试/文档/规范：rename-test 库与生成脚本、图片路径规范同步、docs 修订登记、KP 创建链路 L2 归因、保存路径回退归因、G4 M6a/M3/M6b 施工与真机门禁；§12.F 开放发现 F01–F03 存在性确认，后续由 G5.1–G5.3 后台化/CLI 补全承接 | `results/durable-flush-2026-09-09.json`；`results/g4-gate-summary-2026-09-09.json` |
| 2026-09-14 | C01, C05, C07, L02, S01, E05, E12, I01, E9, E3（部分）, i18n ④ | 首轮台账对账：11 条「已收口但仍开放」条目收口（代码与产物早已闭环），明细见 §10.3 | 见 §10.3 证据清单 |
| 2026-09-14 | — | 「文件」菜单 3 项修复：菜单顺序改为 `打开/导入/导出 ─── 创建 Trae 智能体/新窗口/打开最近` 并去掉末尾分隔线；「打开最近」按状态分流；按已知路径装载漏 `set_kb_path` 的隐性缺陷。**未覆盖边界**：已开着别的库时点「打开最近」（会起新进程，该分支仅经代码审查） | `index.html:49-59`、`app.js:534-566,12152-12161`；`git log -S openKbAt` |
| 2026-09-15 | E19, E21, A8 | 修复批次：Mermaid 块替换后复制 `data--src-line`/`data--src-line-end`（预览范围带与源码定位恢复）；Mermaid 失败不再展示原生错误图（`suppressErrorRendering` + 空源码跳过 + 重入保护）；`locate_snippet` 终点锚 `forward_only` 漏洞（hint 未校验是否在起点之后） | `markdown-preview.js`；`vendor/mermaid.min.js`；`range/locator.py:45` |
| 2026-09-19 | G0–G5、附录指针 | §12「施工计划 · 阶段门禁」**整段收口出表**（G0 基线 / G1 验收收尾 / G2 一致性补强 / G3 调度内核 / G4 作业化 / G5 维护面收敛，结论与实测数字见证据锚）；同批删除文末「附录：已交付规范」三行指针（其事实早已在别处：A → `resources/agent-prompts/organize.zh-CN.md`、B → [import-spec.md](reference/import-spec.md) §4A、C → [import-plan.md](reference/import-plan.md) M5.3） | tag `maint-g3` / `maint-g4` / `maint-g5`；`results/g4-gate-summary-2026-09-09.json`、`results/g5-gate-summary-2026-09-10.json`；`git log -S maint-g4` |

### 10.3 2026-09-14 首轮台账对账（收口 11 项 + 修正 7 条 + 消解 3 处矛盾）

> 依据：[ledger-maintenance.md](conventions/ledger-maintenance.md) 规则 4/5/6；方式 = 三路只读核验（逐条对 `src/**` 与产物取证），**未改任何代码**。
> 收口 11 项证据锚：C01 `index.html:129` + `app.js:12207`；C05 `architecture.md:88` + `kp_rename.py:28-69`；C07 `kp_rename.py:28-69` + `ui.py:342`；L02 `link-context-menu.js:106-160` + `app.js:5512/5563/5238-5276` + `ui.py:479`；S01 `search_kernel.py:38-133` + `ui.py:241-258`；E05 `app.js:9703-9723,10013-10045,10810-10824`；E12 `display-settings.js:11-19` + `app.js:12170-12186`；I01 `import-flow.js:4` + `ui.py:967/999/1015` + `import_executor.py:130-160`；E9 `results/g4-gate-summary-2026-09-09.json:14-17`（真机 PASS）；E3（部分）`durable-flush.md:3,82-88` 已评审锁定；i18n ④ `i18n-inventory.md` 候选 0 行。
> 同批处置：描述与代码不符已改描述 7 条（C02/C03/C06/C08/L01/E02/E14）；矛盾消解 3 处（§7↔§0 导入状态、§12 E9↔G4 段、`maintenance-jobs.md` §4↔§5）；K2 5 项（V02/V06/B2/B3/样式笔刷·同行公式）与 K3 2 项（B7、E3 中的 `maintenance-jobs.md`）**保留在活动分区未收口**；❓ 2 条（C09/E10）描述不足以定位控件，待补信息。

***

## 11. 备注 / 散记（待讨论）

- 编辑链接页面选择文本时主窗口正文跟随跳转，用户编辑完如何回到原位置 → 需描述交互方案
- 打开/配置慢：任务排队在后台进程继续工作，不阻塞前端（进度条/锁？）
- 检索负样本基准（召回率/精确率/错误率）是否完善；每个知识点除隐式 tag 外，是否智能写隐式描述
- 前进/后退功能与一些新设计没对应好，部分跳转无法返回
- 需要一套完整的规则提示词，让 agent 学会整理/修改 `.memoria` 与 Markdown 格式的知识文件

***

## 12. 知识库与维护机制 · 施工总表（2026-09-09 建立）

> 目的：把「知识库数据一致性 + 维护作业」类机制/任务统一登记为施工总表。设计取向（2026-09-09 用户确立）：**借鉴操作系统手段把维护当「任务/作业」组织** —— 调度内核（优先级/去重/idle/epoch 陈旧丢弃/flush）、写盘分级（缓存+原子替换+延迟批量 fsync 屏障）、后台化与合并、切文件/关库/退出为屏障点。
> **触发点约束（2026-09-10 用户确立）**：维护动作只允许两类触发点 —— **后台（自动、不阻塞交互）** 或 **用户显式**（打开库/刷新/构建/点击）；**交互热路径禁止任何同步重活**。任务立项与评审均以此作业化/屏障语义为考量。详见 [maintenance-jobs.md](design/maintenance-jobs.md)。

### A. 一致性 / 注册内核

A1–A8 整段收口（sidecar 镜像/校验/级联、manifest 基线差分、pending 路径同步、图片注册表、KP range 双端定位 heal、词法索引后台化、原子写、`forward_only` 终点锚修复），已按规则 8.4 出表，见 §10。

### B. 操作 / 作业

| # | 任务 | 现状 |
| --- | --- | --- |
| B2 | 文件夹重命名 `dir_rename`（整树移动 + 逐文件级联） | 🔄 K2 待真机验收（代码与 RPC 齐备，partial 级联失败已上屏；无验收落盘） |
| B3 | F2 快捷键（文件/文件夹，捕获阶段 + 仅拦可见弹窗） | 🔄 K2 待真机验收（`file-tree.js:438-463` 齐备，无验收落盘） |
| B6 | md 相对路径链接在目录重命名时自动改写 | ❌ 已知边界（待扩展）：`document.py:697-780` 仅物理移动 + `apply_path_move`，`storage/path_cascade.py` 全函数不触碰 md 正文 |
| B7 | 导出知识库包（bundle） | ⏳ K3 待评审：design 草稿在案（[export-plan.md](design/export-plan.md) §8 四个打开问题未拍板）；无实现（无 `export_execute`；`index.html:60` 导出菜单仍 disabled） |
| B8 | 构建 `build_kb` 末尾 `openFile(同路径, {skipNav:true})` 跳过 `flushDurableBarrier` → 构建期间**未落盘编辑**（<1.5s autosave 窗口）可能被磁盘内容覆盖 | 🔴 K1 ⚠️ 待运行时确认（静态取证：`app.js` buildKb 末尾 openFile 的 flush 分支被 skipNav 跳过；来源 agent-guide/06 §7） |

### C. 视图 / 静默刷新

| # | 任务 | 现状 |
| --- | --- | --- |
| C4 | 图谱**增量更新**（增量在布局与数据层，非帧绘制；原「局部刷新」表述已修正） | ⏳ K1：G4 拆分后续项，方案 S1–S4 见 `results/g4-gate-summary-2026-09-09.json`；`applyDelta` 零命中，`graph-engine.js:62` 仍整体替换 |

### D. 渲染 / 显示

D1、D2 已收口，见 §10。

### E. 测试 / 文档 / 规范

| # | 任务 | 现状 |
| --- | --- | --- |
| E3 | design：export-plan / maintenance-jobs / durable-flush（草稿，2026-09-09 复核恢复 export-plan；durable-flush 为 G4 M6a 设计） | ⏳ K3 待评审：durable-flush 已评审锁定（`durable-flush.md:3,82-88`）；export-plan 与 maintenance-jobs 仍未拍板 |

### F. §2.5 开放发现 · 待评估补录（2026-09-09 代码复核，均确认存在）

F01（KB 完整性检查/审计 `validate_kb` + 静默检查 + 徽标）、F02（路径漂移检测/修复 `detect_path_moves`/`repair_path_cascade`）、F03（图片引用诊断/修复 `diagnose_image_refs`/`fix_unregistered_image_refs`）均已确认存在并出表（见 §10）；三者后续由 G5.1–G5.3 的后台化/调度化/CLI 补全承接。

### 验证机制分配（2026-09-09）

> 该表属**施工期验证方法论**（"每项用什么手段验、通过标准是什么"），按规则 8.3 已移到 [design/maintenance-benchmark.md §9](design/maintenance-benchmark.md)（原地不再维护副本）；通用基线（`py_compile` / `node --check` / i18n `rows=0` 等）以 [AGENTS.md §2.2](../../AGENTS.md) 的验证阶梯为准。

**§12 遗留（非门禁项）**：打开库 `sync_kb_pending` 全库扫描 ~1.06s（G5.4 实测）；`kp_panel` 作业在文件切换瞬间偶发 `expected str, bytes or os.PathLike object, not NoneType` 失败（真机 2026-09-10 日志），待排查触发条件。

***

## 13. 应用内对话（Agent 面板）

> 只记**状态**；设计与逐块施工见 [design/dsh-agent-port.md](design/dsh-agent-port.md)（规则 1.2：不在本文重复）。

| # | 任务 | 现状 |
| --- | --- | --- |
| AG01 | 引用 agent 回复内容再追问（选中某条回复当下一轮显式上下文）+ **文件内选区引用** | 💡 K1 待规格化（设计草见 dsh-agent-port §6.13） |
| AG02 | 助手气泡渲染 Markdown + `文件:行号` 锚点 | ✅ 代码完成（harness 二十项断言，见 §4.2）；真机观感待验 |
| AG03 | dsh M2 `session-reference`（跨会话引用） | ✅ K2（§4.2；harness 8660 端到端） |
| AG04 | 工具与能力包路线图（写/联网/skill/宿主+token 预算+基准集） | ⏳ K3 待评审（agent-capabilities.md §2 含计划API，P1–P12） |
| AG05 | 状态栏/状态 bar（点绿/红 + 模型/网络绿红/**余额对数连续色**/**缓存命中率**；已去会话 id 与轮次） | 🔄 K1（实现与实测见 agent-guide/01 §7） |
| AG06 | UI 视觉语言对照（借 dsh 观感）：A/B 档全收口（B-8 不做）+ **U4 分隔线专用档 `--border-sep`** | 🔄 K1（design/ui-visual-language.md §4/§7）；**U5 待选** |
| AG07 | **引用/锚点合法性**（空格路径/非 md/全角括号中段/区间只跳起始行/`.md:L7`） | ⏳ K2 路线已定：P 收窄语法 + V 用库内清单分级收敛 + L 改读时投影（文献与"不要做"见 §6.5） |
| AG08 | 面板看不到模型 **thinking** ＋其**展开三角**换 dsh 三角（2026-09-20，全库 details 同批） | ✅ K2：`ReasoningDelta` → `on_reasoning` → 折叠块 `.-agent-think*`（§7；真机未验） |
| AG09 | 设置里的「字号」同时控制对话面板字号 | 🔄 K2（`display-settings.js` 打 `--agent-font-size`；harness 实测 15→20px 联动；真机未验） |
| AG10 | dock 整理：会话选择**迁到左栏「历史」页签**；头部「出网」「设置」与「清空对话」**退役**，agent 设置**搬进设置弹窗「对话」页签** | 🔄 K2（harness 通过；真机未验；**退役残留已清**，见 01 §7、docs-management §4.2） |
| AG11 | 流式**逐行渲染**（面板侧中间缓冲；代码块/公式未闭合时转圈） | ✅ K2：`agent-stream-buffer.js` + `.-agent-stream-wait*`（§7 取证；真机未验；图片渲染另立 AG12） |
| AG12 | 图片渲染支持：在流式管线里渲染模型输出的图片（行内 `![]()` / 图片资产） | ⏳ K1（由 AG11 行内注记独立成条；无实现证据） |
| AG13 | 思考不落盘 ⇒ 重载旧会话/刷新看不到历史思考（AG08 偏差 1）：改落盘 = JSONL 事件 + 回放 + 渲染三点，需另立规格 | ⏳ K1 待规格化（`ask_stream.py:29-34`；落盘牵动读路径成本） |
| AG14 | 会话重命名（`title.py` 补 `user` 来源 + RPC + 左栏历史行入口） | ⏳ K1（`title.py:40` 未移植；无 rename RPC） |
| AG15 | 每轮 token 用量行：最后一轮助手气泡下显示「用量 {hit}(命中)+{miss}(未命中)={total} tokens」，旧副本随新一轮移除 | 🔄 K2 验收未闭环（实现 = `agent-panel.js` 末尾块 `.-agent-usage`；待真机 DOM 验收） |
| AG16 | 状态 bar 刷新间隔可配：设置 → 对话，5s/15s/30s/1min/5min/10min/1h（默认 1min），改设置即重挂计时器 | 🔄 K2 验收未闭环（`agent.json` 的 `status_refresh_ms`；待真机 DOM 验收） |
| AG17 | 「生成中…Ns」下沉末条助手气泡尾 + 状态行不再写用量文本（错/警告/已停止仍归它）+ 全库三角统一 dsh 三角 | 🔄 K2 验收未闭环（`agent-panel.js` 2820-2962、`app.css` 5585-5613；真机未验，见 01 §7） |
