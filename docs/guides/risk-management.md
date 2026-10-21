# 风险治理规则与协议

> **状态**：生效（2026-10-21）
> **地位**：**风险相关规则的单一事实源**。其他文档（charter §8、org.md §12、各施工计划）的风险条目**引用本文**，不各写一套。
> **适用**：所有 Agent（Lead 与 teammate）；人类维护者可据此复核。

---

## 0. 术语来源（不自造）

本文借用业界成熟概念，不新造词：

| 概念 | 来源 | 用途 |
|---|---|---|
| **单向门 / 双向门**（Type 1 / Type 2 decisions） | Bezos；见 [Inc: two-way-door](https://www.inc.com/jeff-haden/jeff-bezos-just-proved-even-moving-across-country-can-be-a-two-way-door-decision.html) | 决定**审批强度**与**回滚要求** |
| **风险 = 可能性 × 影响** | ISO 31000 风险管理办法（见 [UNHCR ERM policy](https://www.unhcr.org/sites/default/files/2024-10/UNHCR_HCP_2020_2_ERM_Complete%20Policy%20with%20Annexes.pdf)） | 决定**风险等级** |
| **Pre-mortem**（事前验尸） | Klein；见 [Premortem 论文](https://par.nsf.gov/servlets/purl/10435109) | 单向门操作前**主动找失败原因** |
| **可复现/密封性** | Bazel hermeticity；见 org.md §12 | 测量类风险的控制手段 |
| **Blameless postmortem** | SRE 实践 | 事故复盘**只查机制、不追人** |

---

## 1. 风险分级（可能性 × 影响）

### 可能性（Likelihood）

| 级 | 含义 |
|---|---|
| **L4** | 已发生过，或当前正在发生 |
| **L3** | 很可能（同类问题近期出现过） |
| **L2** | 可能（有理论路径、无先例） |
| **L1** | 罕见 |

### 影响（Impact）

| 级 | 含义 | 例子 |
|---|---|---|
| **I4** | **不可逆数据损坏 / 用户数据丢失** | 静默丢字、写错文件 |
| **I3** | 可逆但需人工介入 / 结论永久失真 | 基线被污染、A/B 能力丢失 |
| **I2** | 需返工 / 局部功能失效 | 渲染错、某操作变慢 |
| **I1** | 仅影响可读性 / 无功能影响 | 文档笔误 |

### 等级

| 等级 | 判定 | 要求 |
|---|---|---|
| **R0 阻断** | `I4`（无论可能性） | **必须停下上报人类**，不得由 Agent 自行处置 |
| **R1 高** | `L≥3 且 I3`，或 `L≥2 且 I3` | 需 pre-mortem + 回滚计划 + 人类确认 |
| **R2 中** | `I2`，或 `L≥3 且 I2` | 需回滚计划 + 分段提交 + 每段验收 |
| **R3 低** | `I1` | 记录即可 |

**关键**：**`I4` 一律 R0**，不看可能性。因为"数据损坏"哪怕概率 1%，也不该由自动化流程单方面决定。

---

## 2. 单向门 vs 双向门（决定审批强度）

**判定问题**：**如果这一步做错了，能否用一条命令 / 一次 git revert 回到原状？**

| | 双向门（Two-way） | **单向门（One-way）** |
|---|---|---|
| 判据 | 可回滚、成本低 | **不可逆，或逆转成本 >> 决策成本** |
| 例子 | 改一个函数、调参数、加断言、写文档 | **删除 legacy 实现**、污染冻结基线、销毁 A/B 对照能力、覆盖用户数据 |
| 审批 | Agent 自主，记录即可 | **人类确认 + pre-mortem + 回滚计划** |
| 节奏 | 快 | **慢、分段、每段验收** |
| 提交粒度 | 可合并 | **每段单独 commit** |

### 本项目已识别的单向门

| 操作 | 为何单向 | 附加要求 |
|---|---|---|
| **P6 删除 legacy 渲染管线** | 删除后**永久失去 A/B 对照能力**；后续无法再证明"没退化" | 必须在 task-47（L1/L3 补齐）完成后；四段独立提交；每段跑 13/13 + 11 剧本 |
| **修改/重建冻结基线**（`S_render_frozen` / `p5_perf_frozen`） | 旧基线一旦被覆盖，历史对照失效 | 必须先归档旧基线；改动需记录原因 |
| **修改用户知识库内容**（`.md` / `.memoria`） | 无法区分"程序改动"与"用户原文" | 写前备份；不得静默覆盖 |
| **推送 / 力推远端** | 他人可见 | 本仓库禁止 Agent push |
| **修改 `Package/**` / 版本号** | 打包产物、发布语义 | 仅人类可动 |

**双向门示例（不需要人类审批）**：新增断言、加注释、补测试、写报告、加测量脚本、改探测口径。

---

## 3. 风险登记册（Living Register）

**规则**：
- 这是**唯一**的风险清单；其他文档只引用 `R-<n>` 编号
- **每条必须有**：可能性、影响、等级、状态、缓解措施、关闭条件
- 状态变化时**必须更新本文**，不得只写在报告里
- 关闭时**保留记录**（标 `CLOSED` + 关闭依据），不删除

| ID | 风险 | L | I | 等级 | 状态 | 缓解 / 状态说明 |
|---|---|---|---|---|---|---|
| **R-01** | **编辑器 DOM 回读丢尾 `\n`**（`collectEditorBody` 逐行 `join` 无法表达"文件以 `\n` 结尾"） | L4（已发生） | I4（保存会写回缺尾换行的文件） | **R0→已降级** | **已修**（`80b4d79b` + `0fa99f1d`） | P4b 修 `collectEditorBody`；AST 加 `document.trailingNewline` 从数据结构层根治。**残余**：`_srcApplySnapshot` 的 Ctrl+Z 入口无公开入口，未单独真机回环 |
| **R-02** | **`ast != dom` 瞬时不一致**（拆分后块索引偏移） | L4（已复现） | I2（**判定 A：安全**，无丢字/无写错块） | **R2** | **待修**（legacy/new 共有） | 见 charter S14。**残余隐患**：`ast!=dom` 期间下游若假设"AST 块索引 == DOM 块索引"会取错位块。**未测**：`applyBlockPatches` 路径、有内容的幽灵块 |
| **R-03** | **测量不密封**（跑测量期间 `src/**` 被改；headless/realapp 混比；判定读不存在的 JSON 键） | L4（已发生多次） | I3（结论失真、归因错 3 次、耗费数小时） | **R1** | **已控制** | org.md §12 三要素 + null sequential build 自检；`run_p5_finalize.ps1` 三层 guard；L8 契约条目 |
| **R-04** | **P6 删除 legacy 后永久失去 A/B 对照** | L4（必然发生） | **I3**（不可逆：未来无法证明"没退化"） | **R1** | **待执行** | **前置已基本满足（2026-10-21）**：task-47/48 完成 —— A 类确定性计数器 13/13 逐字节一致、双侧 13/13 零额外工作量、wall-time 8 项 ≤1.15×。**执行中（2026-10-21）**：放行条件已满足（R-13/R-14 CLOSED）。**P6a 完成并入库 `d472e851`**（`renderPreview` 切 render-core，29 调用点不动；`R.render` 运行时 0 次；冻结签名 13/13 IDENTICAL；高亮退化经 R-15 修复后 435 块/2189 span 全对）。**下一步 P6b**（迁 3 个临时开窗）。四段独立提交；每段 13/13 + 12 剧本；删除文件在 git history 永久可恢复 |
| **R-05** | **首开真实成本集中在 MathJax typeset 758ms(73%) + mermaid 193ms(19%) = 92%** | L4 | I2（用户可感知的慢） | **R2** | **未修**（H5） | 需 typeset 分批 / 可见区优先 / mermaid 延后渲染。**优化前必须保留当前基线**（否则无法证明改善） |
| **R-06** | **`markdown-preview.js` 104KB / 2409 行仍承担高亮+mermaid+math**，P6d 若误删会打断这些能力 | L2 | I3（功能缺失且难察觉） | **R1** | **未发生** | P6d **禁止大改**该文件；删任何函数前必须 grep 全部消费者 |
| **R-07** | **`renderPreview` 29 个调用点**，P6a 若逐个改会漏 | L3 | I3（漏一处 = 静默走 legacy = 并行事实源复活） | **R1** | **已缓解** | **策略：换实现不换签名**（只改 `renderPreview` 内部）。勘察确认 27 处无 opts、仅 2 处 `{incremental}` 且该参数已被证明无害 |
| **R-08** | **`preview_body` 是派生缓存**，曾被误当输入源（P2c 尾块 bug 根因） | L3（已发生） | I2 | **R2** | **已修**（`705874cf`） | `setText` 以入参 `text` 为真源；`preview_body` 只由 `renderPreview` 内部后端预清洗产物填充 |
| **R-09** | **同一函数在 IIFE 内被重绑多次**（`addSelectionToChat` 3 处定义） | L4（已踩） | I2（误判"功能不存在" ⇒ 重复造功能） | **R2** | **已记录** | org.md §11.3：定义多处时**以最后一处为准**；判定"功能不存在"前必须排除"已存在但被重绑" |
| **R-10** | **冻结 KB / 语料被外部进程污染**（`scale-5k.md` 被变异测试塞入 800+ 个 `z`） | L3（已发生） | I3（基线被污染，所有对照失真） | **R1** | **已控制** | 冻结 KB 做 sha256 + 末尾字节 guard；`run_p5_finalize.ps1` 拒跑机制 |
| **R-11** | **`results/` 目录 134 已跟踪 + 243 未跟踪**，`git status` 噪音大，易误提交一次性数据 | L4 | I1（仅卫生问题） | **R3** | **未处理** | 建议：显式文件清单提交（当前做法）；后续可考虑统一忽略 |
| **R-12** | **非本项目的未提交改动**（`ask_stream.py`、`review-cards-handoff.md`、`AAA_Vocab/**`）长期混在工作区 | L4 | I2（可能被误提交或误删） | **R2** | **已知** | 每次提交**显式列文件**，不 `git add -A`；提交前用 `git status` 核对归属 |
| **R-13** | **测量脚本 `taskkill /T` + 凭端口反查 PID 杀进程 ⇒ 会误杀用户自己的应用**。已实际发生：任务期间用户 app 被波及重启（pid 21860 → 39868）。全仓 6 个脚本共 **18 处 `/T`**，其中 `taskkill /PID $c.OwningProcess /T /F` 在测量实例绑定端口失败时会反查到**用户正式应用**的 PID。 | L4（已发生） | I3（用户正在用的应用被杀，可能丢未保存内容） | **R1** | **CLOSED**（task-49，2026-10-21）：实际范围比初查更大——**15 脚本 26 处**（含 `artifacts/agent/verify/` 下 9 个历史探针）。新建 `scripts/benchmark/surface/safe-kill.psm1`（253 行）：只杀自己启动的 PID / 杀前校验命令行含本次调试端口 / 无 `/T` / 进程名+路径双重拦截 `Memoria.exe` / 端口被占只报告不杀。**Lead 独立复核**：`grep taskkill./T`=0、`OwningProcess`=0、dry-run 输出 `PROTECTED`。**Lead 另判断**：agent 侧曾提议在 `src/.../shell_exec.py` 加同类兜底，**已回滚** —— 该处 `proc.pid` 恒为本模块自己 `Popen` 的子进程（L360→L382 单一调用点），保护的是**安全路径**；而 agent 真危险路径是命令行里直接写 taskkill，那道守卫覆盖不到；且会阻断重启 Memoria 这类合法请求、每次终止多起一个 powershell。**结论：修在脚本层正确，修在 shell_exec 层是错层** |
| **R-14** | **`find`（搜索高亮）无任何交互回归覆盖**：`scenarios/interactions.json` 只有 S0–S10（开文档/选区/IME/画笔），搜索从未入回归集。而 `find` 是 `#preview` 的 DOM 消费者，新管线换实现后其行为无回归保护。 | L4（已确认缺失） | I2（搜索高亮失效不会被回归发现） | **R2** | **CLOSED**（task-49，2026-10-21）：补 `S11-find-highlight`。**实测查清 find 真实语义**：`#toolbar-search` 是**全局搜索建议面板**（输入 ~1s 出 35 条建议、点击跳行），**不是预览内查找**——`#preview` 的 `mark` 恒为 0、HTML 长度恒 440595（输入前后完全相同）。故 S11 断言「面板出现 + 无预览高亮」，**未伪造不存在的行为**。`kpHover` 已由 `KP1-hover-highlights-range` 覆盖。**Lead 独立复核：12 剧本 12/12 失败 0，exit 0** |
| **R-15** | **渲染签名只覆盖块级 `{tag, kindClass(首个), textNorm}`，覆盖不到块内嵌套标记**（语法高亮 `pre>code>span.tok-*`、对齐子类等）。已实际造成假绿：P6a 把 `renderPreview` 切到 render-core 后**代码块语法高亮整体消失**，而 `S_render_frozen` 仍报 13/13 `IDENTICAL`。旧路径 `renderer.js:105-106` 做高亮，新路径 `render-core.js:393` 明确"不做高亮 token"，`app.js` 后处理也未补。 | L4（已发生） | I2（用户可见的功能退化，且验收判绿） | **R1** | **CLOSED**（task-51，2026-10-21）：① `app.js` 新增 `_applyCodeHighlightToPreview()` 复用 `MemoriaCodeHighlight.render`，3 个接入点（`renderPreview`/`renderPreviewAST`/`_preloadOne`，后者防缓存搬回无高亮 DOM）；跳过 mermaid；未知语言降级转义。② 新增独立断言 `check_code_highlight.mjs` + 真机 runner（不污染 `signatureNorm`）。**Lead 独立复核**：`discrimination` 短路⇒135 blocks/0 span/**135 mismatch（RED）**，恢复⇒675 span/0 mismatch（GREEN）；全量 13 文档 / 5 含码 / **435 codeBlocks / 2189 tokenSpans / mismatch 0 / textMismatch 0**；mermaid 135 容器 / 0 残留 code / 0 高亮 span；冻结基线仍 13/13 IDENTICAL |
| **R-16** | **真机测量脚本继承开发机 ambient 配置（`config/ui-settings.json`）⇒ 测量不密封**。已实际发生：该文件 `search.embedding_enabled=true` / `search_modes="both"`，S11 搜索触发**同步构建 embedding 索引**（`search_semantic→ensure_embedding_index→sync_embedding_index→BERT encode`），而 harness 是**单线程 wsgiref** ⇒ 唯一工作线程被占满 >45s，连 `fetch('/')` 都超时，S11 稳定红。**一度被误判为 P6a 产品回归**（Lead 二分：P6a 前 12/12、P6a 后稳定红），实为测试非密封（R-03 同族）。 | L4（已发生） | I3（假红/假绿；**性能基线也可能被后台 warmup 污染**） | **R1** | **部分修复**：`run_interaction.py` 已改为每次 run 独立空 `MEMORIA_CONFIG_DIR`（+`--ambient-config` 仅诊断），S11 场景/断言/sleep 未改；密封后 12/12（49.7s，Lead 复核）。**仍待修**：其余 **8 个真机脚本全部继承 ambient**（`run_fidelity.py` / `run_perf_ops.py` / `run_probe.py` / `run_ready_selfcheck.ps1` / `run_realapp_coverage.ps1` / `run_domwrites.ps1` / `run_fidelity_real.ps1` / `check_code_highlight_run.ps1`），且**需复验 `p5_perf_frozen` / `S_render_frozen` 是否在 ambient 下测得** |---

## 4. 协议 A：单向门操作前置清单（Pre-flight）

**任何单向门操作（见 §2）在执行前必须逐项确认并留下记录**：

| # | 检查项 | 判据 |
|---|---|---|
| 1 | **回滚路径明确** | 能用 `git revert <sha>` 恢复；或已归档旧状态（如旧基线、旧文件副本） |
| 2 | **`src/**` 干净（或已知脏项归属）** | `git status --porcelain -- src/` 输出每一项都有归属说明 |
| 3 | **HEAD 已记录** | 计划/报告中写明起始 commit |
| 4 | **基线已冻结** | 「改之前」的验收基线存在且可复验（`S_render_frozen` / `p5_perf_frozen`） |
| 5 | **已做 pre-mortem** | §5：列出 ≥3 种失败方式及应对 |
| 6 | **分段与验收点已定义** | 每段有独立 commit + 独立验收，不攒到最后 |
| 7 | **人类已知情**（若为 R0/R1） | 有明确的人类确认记录 |

**未通过任一项 ⇒ 不得开始。**

**已实现自动化**：`scripts/benchmark/maintenance/risk_preflight.py`（检查 1–4 项，输出缺口清单）。

---

## 5. 协议 B：Pre-mortem（事前验尸）

**做法**（Klein）：假设**这个操作已经彻底失败**，倒推"为什么会失败"，列出来并逐条给应对。

**要求**：
- **至少 3 条失败方式**（少于 3 条通常说明想得不够）
- 每条必须有**可执行的应对**，不能只写"注意一下"
- 写进施工计划的「风险与缓解」节

**本项目示例（P6 的 pre-mortem）**：
1. *"P6a 改 `renderPreview` 内部后，某条 29 个调用点里的特殊 opts 被忽略 ⇒ 行为差异"* → 应对：先枚举全部 opts 用法（已完成：27 无 opts / 2 个 `incremental` 且无害）
2. *"P6c 删 legacy 后发现公式时序变了"* → 应对：P6c 前单独跑 scale-5k（270 公式 + 135 mermaid）
3. *"P6d 删 `markdown-preview.js` 里某函数，assist/复习卡静默失效"* → 应对：删前 grep 全部消费者；**该文件禁止大改**

---

## 6. 协议 C：回滚计划

**每个 R1/R2 操作必须写明**：

| 项 | 内容 |
|---|---|
| **回滚命令** | 具体到可复制执行（如 `git revert <sha>` / `git checkout <sha> -- <path>`） |
| **回滚判据** | 什么现象出现时必须回滚（不是"感觉不对"） |
| **回滚后验证** | 回滚后跑哪些断言证明已恢复（13/13 + 11 剧本 + 门禁） |
| **不可回滚部分** | 诚实标注：如"删除 legacy 后的 A/B 能力无法通过 revert 恢复（历史已发生）" |

---

## 7. 协议 D：风险上报与升级

**Agent 必须在以下情况立即停下上报（不得自行处置）**：

| 触发 | 动作 |
|---|---|
| 发现 **I4（数据损坏/丢失）** 证据 | **立即停止**，保留现场，上报 Lead |
| 发现**冻结基线被污染** | 立即停止测量，上报（不得"修一下继续"） |
| 单向门操作**前置清单未过** | 不得开始，上报缺口 |
| 同一问题**归因失败 ≥2 次** | 停止试错，上报改方法（今天典型：尾块问题归因错了 3 次） |
| 发现自己**此前的结论被推翻** | 主动上报并更正记录，**不得静默修改** |
| 测量**不密封**（自检不通过） | 结论作废，上报测量缺陷 |

**上报格式**（≤200 字）：`【风险上报】等级 R? | 现象 | 证据 | 我的判断 | 需要什么决定`

---

## 8. 协议 E：风险关闭

**关闭条件**（全部满足才能标 CLOSED）：

1. **根因已定位**（不是"现象消失"）
2. **修复有验证**（不是"改了就对"）—— 有可复验的断言/基线
3. **残余风险已如实记录**（如"S14 判 A 安全，但 ast!=dom 期间下游勿假设索引等价"）
4. **登记册已更新**（本文件，不是只写报告）

**关闭后保留记录**，标 `CLOSED` + 关闭 commit + 残余说明。**不得删除条目**——历史风险是理解系统脆弱点的资产。

---

## 9. 与其它文档的关系

| 文档 | 关系 |
|---|---|
| `display-refactor-charter.md` §8 | 缺陷清单（S13/S14/H4/H5）；**风险等级与协议以本文为准** |
| `org.md` §12 | 测量密封性协议（本文 R-03 的控制手段） |
| `org.md` §11.3 | IIFE 重绑读码陷阱（本文 R-09 的控制手段） |
| `p6-migration-plan.md` | P6 的 pre-mortem 与回滚计划（§5/§6 的具体应用） |
| `concurrent-edit-infrastructure.md` | 人机并发编辑的风险基础（lease/patch/合并的顺序依赖） |
| `render-fidelity-contract.md` | 冻结基线的契约（R-04/R-10 相关） |
