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

> **索引（2026-10-26）**：本表 7 项（详情 → [todo/00-focus.md](todo/00-focus.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| F1 | — | [详](todo/00-focus.md#f1) |
| F2 | — | [详](todo/00-focus.md#f2) |
| F3 | — | [详](todo/00-focus.md#f3) |
| F4 | — | [详](todo/00-focus.md#f4) |
| F5 | — | [详](todo/00-focus.md#f5) |
| F6 | — | [详](todo/00-focus.md#f6) |
| F7 | — | [详](todo/00-focus.md#f7) |

## 1. 配置窗口（合并「知识点解析」+「审核」）— 核心大项

> **索引（2026-10-26）**：本表 6 项（详情 → [todo/01-config-window.md](todo/01-config-window.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| C02 | 🔄 K1 | [详](todo/01-config-window.md#c02) |
| C03 | 🔄 K1 | [详](todo/01-config-window.md#c03) |
| C04 | 🔄 K1 | [详](todo/01-config-window.md#c04) |
| C06 | ⏳ K1 | [详](todo/01-config-window.md#c06) |
| C08 | 🔄 K1 | [详](todo/01-config-window.md#c08) |
| C10 | 🔴 K1 | [详](todo/01-config-window.md#c10) |

## 2. 链接系统

> **索引（2026-10-26）**：本表 4 项（详情 → [todo/02-links.md](todo/02-links.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| L01 | 🔄 K1 | [详](todo/02-links.md#l01) |
| L03 | ⏳ K1 | [详](todo/02-links.md#l03) |
| L04 | 🔴 | [详](todo/02-links.md#l04) |
| L05 | ⏳ K1 | [详](todo/02-links.md#l05) |

## 3. 检索引擎

> **索引（2026-10-26）**：本表 5 项（详情 → [todo/03-search.md](todo/03-search.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| S02 | 💡 K1 | [详](todo/03-search.md#s02) |
| S03 | ⏳ K1 | [详](todo/03-search.md#s03) |
| S04 | 🔄 K1 | [详](todo/03-search.md#s04) |
| S05 | 🔄 K1 | [详](todo/03-search.md#s05) |
| S06 | 🔴 K1 | [详](todo/03-search.md#s06) |

## 4. 图谱

> **索引（2026-10-26）**：本表 3 项（详情 → [todo/04-graph.md](todo/04-graph.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| G01 | 🔄 K1 | [详](todo/04-graph.md#g01) |
| G02 | 🔴 | [详](todo/04-graph.md#g02) |
| G05 | 🔄 K1 | [详](todo/04-graph.md#g05) |

## 5. 编辑器 / 富文本

> **索引（2026-10-26）**：本表 21 项（详情 → [todo/05-editor.md](todo/05-editor.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| E01 | 🔄 K1 | [详](todo/05-editor.md#e01) |
| E02 | ⏳ K1 | [详](todo/05-editor.md#e02) |
| E03 | ⏳ | [详](todo/05-editor.md#e03) |
| E06 | ⏳ | [详](todo/05-editor.md#e06) |
| E07 | ⛔ | [详](todo/05-editor.md#e07) |
| E08 | 🔴 | [详](todo/05-editor.md#e08) |
| E09 | 🔄 K1 | [详](todo/05-editor.md#e09) |
| E10 | ⏳ K1 | [详](todo/05-editor.md#e10) |
| E11 | ⏳ K1 | [详](todo/05-editor.md#e11) |
| E13 | 🔴 | [详](todo/05-editor.md#e13) |
| E14 | 🔄 K1 | [详](todo/05-editor.md#e14) |
| E18 | 🔴 K1 | [详](todo/05-editor.md#e18) |
| E20 | 🔴 K1 | [详](todo/05-editor.md#e20) |
| E22 | 🔴 K1 | [详](todo/05-editor.md#e22) |
| E23 | 🔴 K1 | [详](todo/05-editor.md#e23) |
| E24 | 🔴 K1 | [详](todo/05-editor.md#e24) |
| E31 | 🔴 K1 | [详](todo/05-editor.md#e31) |
| E33 | 🔴 K1 | [详](todo/05-editor.md#e33) |
| E34 | 🔴 K1 | [详](todo/05-editor.md#e34) |
| DOC02 | — | [详](todo/05-editor.md#doc02) |
| DOC03 | — | [详](todo/05-editor.md#doc03) |

## 6. 文件树管理

> **索引（2026-10-26）**：本表 1 项（详情 → [todo/06-file-tree.md](todo/06-file-tree.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| T04 | ✅ 已收口 | [详](todo/06-file-tree.md#t04) |

## 7. 导入与媒体

> **索引（2026-10-26）**：本表 5 项（详情 → [todo/07-import-media.md](todo/07-import-media.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| I03 | 💡 K1 | [详](todo/07-import-media.md#i03) |
| I04 | 💡 K1 | [详](todo/07-import-media.md#i04) |
| I05 | ⬇️ | [详](todo/07-import-media.md#i05) |
| I06 | 🔴 K1 | [详](todo/07-import-media.md#i06) |
| I07 | 🔴 K1 | [详](todo/07-import-media.md#i07) |

## 8. 壳与发布

> **索引（2026-10-26）**：本表 7 项（详情 → [todo/08-shell-release.md](todo/08-shell-release.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| P01 | 🔄 K1 | [详](todo/08-shell-release.md#p01) |
| P02 | ⏳ | [详](todo/08-shell-release.md#p02) |
| P03 | 🔄 K1 | [详](todo/08-shell-release.md#p03) |
| P04 | ⏳ | [详](todo/08-shell-release.md#p04) |
| P05 | ⏳ K1 | [详](todo/08-shell-release.md#p05) |
| P06 | 🔄 K2 | [详](todo/08-shell-release.md#p06) |
| P07 | 🔄 K2 | [详](todo/08-shell-release.md#p07) |

## 9. 学习产品（V2+）

> **索引（2026-10-26）**：本表 6 项（详情 → [todo/09-learning-products.md](todo/09-learning-products.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| V01 | ⏳ | [详](todo/09-learning-products.md#v01) |
| V02 | 🔄 K2 | [详](todo/09-learning-products.md#v02) |
| V03 | 💡 | [详](todo/09-learning-products.md#v03) |
| V04 | 💡 | [详](todo/09-learning-products.md#v04) |
| V05 | 💡 | [详](todo/09-learning-products.md#v05) |
| V06 | ✅ 已收口 | [详](todo/09-learning-products.md#v06) |

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

> **索引（2026-10-26）**：本表 9 项（详情 → [todo/11-notes.md](todo/11-notes.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| F1 | — | [详](todo/11-notes.md#f1) |
| F2 | — | [详](todo/11-notes.md#f2) |
| F3 | — | [详](todo/11-notes.md#f3) |
| F4 | — | [详](todo/11-notes.md#f4) |
| F5 | — | [详](todo/11-notes.md#f5) |
| F6 | — | [详](todo/11-notes.md#f6) |
| F7 | — | [详](todo/11-notes.md#f7) |
| F8 | — | [详](todo/11-notes.md#f8) |
| F9 | — | [详](todo/11-notes.md#f9) |

## 12. 知识库与维护机制 · 施工总表（2026-09-09 建立）

> **索引（2026-10-26 索引化）**：本表只留索引；**详情（施工总表原文/节区注记）**→ [todo/12-build-table.md](todo/12-build-table.md)。状态事实源 = 本表；A/D/F 收口与 G 认领表归档 = [design/ledger-archive-2026.md](design/ledger-archive-2026.md) §10.6；验证方法论 = [design/maintenance-benchmark.md §9](design/maintenance-benchmark.md)。
> 统计：活跃行 **7**（B2/B3/B6/B7/B8/C4/E3）+ 门禁 **1**（GATE-1）；A/D/F 已收口出表；G 已归档；H 待裁决建议条款（见附件 #h）；遗留两处（见附件 #residual）。

| # | 任务 | 状态 | 详情 |
| --- | --- | --- | --- |
| B2 | 文件夹重命名 `dir_rename`（整树移动 + 逐文件级联） | 🔄 K2 | [详](todo/12-build-table.md#b2) |
| B3 | F2 快捷键（文件/文件夹，捕获阶段 + 仅拦可见弹窗） | 🔄 K2 | [详](todo/12-build-table.md#b3) |
| B6 | md 相对路径链接在目录重命名时自动改写 | ❌ 已知边界 | [详](todo/12-build-table.md#b6) |
| B7 | 导出知识库包（bundle） | ⏳ K3 | [详](todo/12-build-table.md#b7) |
| B8 | 构建 `build_kb` 末尾 `openFile(同路径, {skipNav:true})` 跳过 `flushDurableBar… | 🔴 K1 | [详](todo/12-build-table.md#b8) |
| GATE-1 | UI 契约门禁 `scripts/check_ui_contract.py`（新增违规红，基线 210F/60W） | ✅ 已落地 | [详](todo/12-build-table.md#ui-gate) |
| C4 | 图谱**增量更新**（增量在布局与数据层，非帧绘制；原「局部刷… | ⏳ K1 | [详](todo/12-build-table.md#c4) |
| E3 | design：export-plan / maintenance-jobs / durable-flush（草稿，2026-09-09 复核… | ⏳ K3 | [详](todo/12-build-table.md#e3) |

> 节区注记：引言/触发点约束 `#intro`｜A 一致性内核（已收口出表）`#a`｜D 渲染（已收口）`#d`｜F §2.5 开放发现 `#f`｜G 团队任务板（已归档）`#g`｜H 待裁决建议条款 `#h`｜验证机制分配 `#verify`｜§12 遗留 `#residual`

## 13. 应用内对话（Agent 面板）

> **索引（2026-10-26 索引化）**：本表只留索引（ID/主题/状态/详情）；**详情（AG 行原文 + 注记）**→ [todo/13-agent-panel.md](todo/13-agent-panel.md)。状态事实源 = 本表；历史批次叙述 = [design/agent-panel-batches.md](design/agent-panel-batches.md)。
> 统计：107 行 = 活跃索引 **53**（✅10 / 🔄·K2 30 / 🔄 3 / ⏳7 / 💡1 / ⚠️1 / 🔴1）+ 已归档 ✅→§10.5 **27** + 已作废 ⛔ **27**。

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
| AG109 | JS/CSS 常量双源：contentMinPx.def（display-settings.js:25 vs agent-panel.js:224） | 🔴 K1 | [详](todo/13-agent-panel.md#ag109) |
| — | 27 条已完成归档（§10.5） | ✅→§10.5 | [全部](todo/13-agent-panel.md#archived) |
| — | 27 条已作废/已并入（AG59/60/63/71–96 等） | ⛔ | [全部](todo/13-agent-panel.md#voided) |

> 注记（2026-10-25 task-94 K2 判定 / AG106/AG107/AG108 补录 / 2026-10-25 台账补录）→ [附件#notes](todo/13-agent-panel.md#notes)

## 14. 0.4.7 收摊计划（2026-10-25 刷新，todo-owner；交人审）

> **索引（2026-10-26）**：本表 6 项（详情 → [todo/14-plan-047.md](todo/14-plan-047.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| 1 | — | [详](todo/14-plan-047.md#1) |
| 2 | — | [详](todo/14-plan-047.md#2) |
| 3 | — | [详](todo/14-plan-047.md#3) |
| 4 | — | [详](todo/14-plan-047.md#4) |
| 5 | — | [详](todo/14-plan-047.md#5) |
| 6 | — | [详](todo/14-plan-047.md#6) |

## 15. 0.4.8 范围（2026-10-25，人已定）

> **索引（2026-10-26）**：本表 9 项（详情 → [todo/15-plan-048.md](todo/15-plan-048.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| 1 | — | [详](todo/15-plan-048.md#1) |
| 2 | — | [详](todo/15-plan-048.md#2) |
| F3 | — | [详](todo/15-plan-048.md#f3) |
| F4 | — | [详](todo/15-plan-048.md#f4) |
| F5 | — | [详](todo/15-plan-048.md#f5) |
| F6 | — | [详](todo/15-plan-048.md#f6) |
| F7 | — | [详](todo/15-plan-048.md#f7) |
| F8 | — | [详](todo/15-plan-048.md#f8) |
| F9 | — | [详](todo/15-plan-048.md#f9) |

## 16. 架构重构 S1–S5（原定 0.5.0，**已撤回** → 内容归入 0.4.7）

> **索引（2026-10-26）**：详情 → [todo/16-arch-refactor.md](todo/16-arch-refactor.md)（原文逐字）；状态事实源 = 本表。

## 17. 团队插件完善项（team-plugin / Agent Teams；2026-10-25 登记，todo-owner）

> **索引（2026-10-26）**：本表 5 项（详情 → [todo/17-team-plugin.md](todo/17-team-plugin.md)）；状态事实源 = 本表。

| 项 | 状态 | 详情 |
| --- | --- | --- |
| P0 | ⏳ 待做 | [详](todo/17-team-plugin.md#p0) |
| P1 | ⏳ 待做 | [详](todo/17-team-plugin.md#p1) |
| P2 | 🔄 | [详](todo/17-team-plugin.md#p2) |
| P3 | ⏳ 待做 | [详](todo/17-team-plugin.md#p3) |
| P4 | ⏳ 待做 | [详](todo/17-team-plugin.md#p4) |

## 18. 0.5.x 导出/导入板块（2026-10-26 人定方向；Q1/Q2/Q3 已裁决）

> 计划全文（P0 12 项 / 4 批 / 四组矩阵验收 / 人裁决）见 [design/export-import-0.5.md](design/export-import-0.5.md) §7–§12。**Q1 都要**：两皮肤（a Memoria 只读=默认 / b 纯文本）× 两形态（单 html / 文件夹）= **四组组合都做**，正交不设限；**Q2 省电=待测**（未测不得作卖点）；**Q3 v1 只导出**、导入延后。批次：B1 内核+文件夹+a → B2 单html+多选全选 → B3 纯文本皮肤 → B4 矩阵回归；v1.1 只延后高级体验，不延后组合。

***

## 19. 人提出的想法/需求台账（2026-10-27 建档）

> 人 2026-10-26 明确要求「不要停留在记忆，要交给 todo agent 记下来」⇒ 本会话 28 条需求/想法 + 1 条补充裁决已落盘 → [todo/ideas.md](todo/ideas.md)。状态严格取值（已落地/已派发/待排期/已否决或已缩范围/待澄清），commit sha 经 `git log` 核对；新需求由 todo-owner 24h 内追加。
