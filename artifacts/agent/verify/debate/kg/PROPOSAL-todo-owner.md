# KG 设计辩论 Phase 1 — B 知识组织 / 产品提案

> 提案方：`todo-owner`（B 知识组织/产品）｜日期：2026-10-25
> **独立性声明**：未读取 `PROPOSAL-{arch-contract,agent-arch,metrics-baseline}.md`；结论从「真实库 + 学习场景」自下而上推导，最后才与 D1–D6 对照。
> **证据口径**：E1 格式 `ev:file:<repo-relative-path>#L<n>`；不可行号化的 JSON 用路径 + 实测计数。真实库 = `docs/example/AAA_Vocab`（121 节点 / 408 边的真实 IELTS 备考库）。

---

## 1. 立场摘要（≤10 行）

1. **只有一份数据**：知识原子（KP/节点）+ **有语义断言的关系（edge）** + **无断言的引用（link）**。场景不新增数据结构，只切换**投影/视图**（filter + layout + 焦点关系 + 可用动作）。
2. **语义边 v0 只保留 5 类**：`contains`（整体-部分）/ `prerequisite`（先学）/ `sequence`（步骤-时间）/ `contrast`（对比组）/ `exemplify`（抽象→例证）。`reference` **不是边**，是 link。
3. **D1 的 4 类不足以覆盖 Q1**：它从"代码已有 3 类"反推，漏了 **contrast 与 sequence**（真实库里有直接证据），且把 `reference` 当边（会把"文字出现"误当成"语义关系"）。
4. **Q2 判据**：一条边存在 ⇔ 它能改变 Q5 里的某个决策；只提供"点一下跳过去"的不叫边。当前真实库里 **408 条边全是 `reference`（origin=link 406 条）** ⇒ 现状图是**链接图**，不是关系图。
5. **Q5 四个主决策**（先学什么 / 为什么和我有关 / 这条跳转要不要点 / 这块掌握了吗）分别需要 `prerequisite` / 路径（contains+prereq+exemplify）/ link 元数据 / 卡片掌握度字段；这四类**不是同一张图能同时最优回答的**，必须靠视图。
6. **同一份知识在不同场景需要不同图吗？** 需要不同**视图**，不需要不同**数据结构**。切换方案 = 6 个视图预设（见 §2）。
7. **3D 只用于总览/探索**，有向边的决策类任务一律 2D；3D 里箭头必须屏幕空间恒显 + 关系着色 + legend，否则不展示有向边。
8. **D4/D5/D6 需改**：0.5 的 ego network 必须补"prerequisite 链"最小视图；force 默认必须过滤语义层；"不补外部对标"在**设计阶段**不成立（关系本体需要先验，至少 2–3 个学习科学框架 + falsifier）。
9. **风险**：把 tags 当关系。真实库 tags 有「对比/转折/写作/口语」（`ev:file:docs/example/AAA_Vocab/.memoria/sidecars/expressions/patterns/contrast-linkers.memoria.yaml#L14-L20`）——这些是**属性/适用场景**，不是边；应做 node 字段或 scene 权重。

---

## 2. Q1 学习场景 × 知识组织（主战场）

> 每个场景回答：用户动作 / 需要什么结构 / 需要什么关系 / 证据 / 该场景的视图。
> 关键结论：**6 个场景 = 6 个视图投影，数据同一份**。

| 场景 | 用户实际动作 | 需要看到的结构 | 需要的关系类型 | 证据（真实库） | 视图预设 |
| --- | --- | --- | --- | --- | --- |
| **背诵** | 看卡片正面→回忆→翻面→自评；跟读易混音；反复到 due 消失 | **卡片队列**（不是图）；单词页的"定义/音标/易混" | `reference`(卡片↔KP 的承载) + `contrast`（易混对，如 blend vs bland/blind） | `cards.json` 80 张、`card_id/kp_id/front/back`（`.memoria/agent/review/cards.json`）；易混对 `ev:file:docs/example/AAA_Vocab/vocab/blend.md#L6` | 卡片队列（due 排序）；单词页 |
| **理解** | 读定义、看用法、区分近义/易混、看例子 | **层级 + 例证**：词→用法→搭配→例句；对比槽位表 | `contains`（词→用法/搭配）、`exemplify`（抽象→例句）、`contrast`（易混/对比词） | 定义/例句 `blend.md#L9-L22`；词族/搭配 `#L24-L45`；对比槽位 `contrast-linkers.md#L23-L33` | 层级树 + 例证卡；对比槽位表 |
| **应用** | 写句/口语输出；查"这个搭配能不能用在我的题里" | **例证对 + 搭配矩阵 + 场景适用**（写作/口语） | `exemplify`（用法→例句）、`contrast`（该用/别用槽位） | Speaking/Writing example `blend.md#L13-L21`；槽位"该填/别填"`contrast-linkers.md#L25-L31`；plan 的"口语接口：写作喂养口语"`ev:file:docs/example/AAA_Vocab/plan/exam-2026-11-07.md#L21` | 任务视图（题目→可用句块/词块） |
| **迁移** | 把写作论点不看稿讲 60 秒；把 A 场景规则用到 B 场景 | **跨技能/跨域映射**：同一原则在别的场景的实例 | `exemplify`（同一原则→另一场景实例）、`prerequisite`（先有论点再讲） | plan「口语接口…写作喂养口语」`plan/exam-2026-11-07.md#L21`；写作→口语的"论点"是同一对象 | 跨域路径视图（写作↔口语） |
| **复习** | `fsrs.py due` 取今日到期卡→评分→错题回看 | **due 队列 + 掌握度状态**（不是图）；错题→KP 归因 | `reference`（card↔kp）+ `prerequisite`（先修卡） | `progress.json` 字段 `state/due/stability/difficulty/reps/lapses/last_review`（`.memoria/agent/review/progress.json`）；`attempts.jsonl` `verdict/elapsed_ms/source`；`cards.json` 的 `kp_id` | 复习面板（due + 掌握度） |
| **写作输出** | 读题→列提纲→按段写→自查（overview/数字/例证） | **模板序列 + 论点-例证**：4 段/3 理由/例证 | `sequence`（Step1→2→3；段序）、`exemplify`（论点→例证）、`contrast`（对比论证） | L14 三步 `ev:file:docs/example/AAA_Vocab/writing/SimonClass/L14-Planning.md#L3,L10,L16`；L12 "three reasons, one paragraph each, in this order" `#L10`；"Idea, Explain, Example" `#L24`；例证缺失→TR≤6 `plan/exam-2026-11-07.md#L19` | 模板/提纲视图（题→段→句块） |

**为什么不是"每个场景一套数据结构"**：6 个场景需要的都是同一组原子（KP/卡片/例句/槽位）+ 同 5 类关系 + 不同字段/过滤。若按场景建 6 套结构，会出现：同一"对比"在写作/理解里各存一份、复习卡与图脱钩、迁移无法表达。
**切换方案（具体）**：图数据只存 `nodes[]` + `edges[]`（type/direction/evidence）；视图预设声明：`focusTypes` / `layout(force|tree|list|matrix|queue)` / `nodeFilter(scene tag)` / `edgeFilter(type)` / `actions(点击=跳转 or 关系卡 or 出题)`。6 个预设见上表最后一列。

---

## 3. Q3 关系类型：真正独立的有哪些（论证独立性）

> 独立性判据：① 能否由其它类型派生/组合得到（能派生则不合一独立）；② 是否有方向；③ 是否可自动推断（结构/顺序可推 = 自动，语义判断需作者/模型 = 人工）；④ 服务 §2 哪个场景的哪个动作。
> **候选清单不照抄 Lead 列表**：按"用户决策"反推后，v0 保留 5 类语义边 + 1 类 link；其余归入"派生/字段/不做"。

| 类型 | 独立性论证 | 方向性 | 可推断性 | 服务场景（动作） |
| --- | --- | --- | --- | --- |
| **contains**（整体-部分） | 不能由 sequence/prereq/contrast 派生（部分≠先后≠对比）；层级是理解的最小骨架 | 整体→部分（可反向查"属于哪"） | **自动**：标题层级/文档结构/KP range 可推 | 理解（看范围/结构）、复习（这一章有哪些点）、图总览 |
| **prerequisite**（先学） | 不能由 contains 派生（同属一章不等价于先学）；不能由 plan 顺序自动等同（计划顺序含时间约束） | 强方向：A→B（B 依赖 A） | **半自动**：可从难度/依赖声明/计划顺序**建议**，必须可人工改 | **先学什么**（Q5①）、复习（前置未掌握先补） |
| **sequence**（步骤/时间） | 不能由 prerequisite 派生：写作 4 段顺序是"产出流程"，不是"学习依赖"；两者方向一致时也只是巧合 | 强方向：step1→step2 | **自动**：列表/编号/时间词/计划表可推（L14 Step1–3、L12 "in this order"） | 写作输出（模板步骤）、应用（流程类任务） |
| **contrast**（对比组） | 不能由 contains/sequence 派生（A 与 B 是"可比的不同对象"）；也不能由同义/近义派生（近义=可替换，对比=不可替换且需区分维度） | **对称但带维度**：A↔B 在同 dimension 上比较；建议存 `dimension` 字段 | **人工**（语义判断；可从"易混/对比"标签提示候选，但不自动建边） | 理解（区分易混）、迁移（对比两个场景）、写作（对比论证） |
| **exemplify**（抽象→例证/实例） | 不能由 contains 派生（例证不是部分，是实例）；不能由 sequence 派生 | 方向：抽象/规则→例证 | **半自动**：例句块在定义块之后可建议；是否"支撑该论点"需人工/模型判断 | 理解（看例子）、应用（套用例句）、写作（例证支撑论点：TR 判据）、迁移（同原则另一场景实例） |
| **reference / link**（引用入口） | **不是边**：它只断言"这段文字提到了某目标"，不断言任何语义关系；方向只是"出现位置→目标" | 出现位置→目标（点击方向） | **自动**：wikilink 扫描（现状 408 条，origin=link 406） | "这条跳转要不要点"（Q5③）；不参与推理 |
| ~~同义/近义~~ | **不独立**：同义=可合并节点 + alias 字段；作为边会制造"同义网"噪声 | — | 自动（词典/别名） | 归入 node 字段 `aliases[]` |
| ~~派生（词族）~~ | **不独立**：真实库就是"Word Family"表格字段（`blend.md#L37`），不是跨节点关系；跨节点派生可归 `contains` 的"词族"子类 | — | 半自动 | 归 node 字段 `family[]` 或 contains 子类 |
| ~~抽象-具体~~ | **不独立**：与 contains 的"层级"重复（category→instance 可用 contains+节点 level 表达）；独立会与 contains 语义重叠 | — | 自动 | 归 contains 子类（`contains:taxonomy`） |
| ~~理论-实践~~ | **不独立**：是 exemplify 的"跨域实例"特例（抽象规则→实践案例） | — | 半自动 | 归 exemplify（跨域） |
| ~~因果~~ | **v0 不建**：真实库没有可用因果标注；自动推断不可靠；建了必然低质。若 v1 建：需 `mechanism/evidence/strength` 三字段，且服务"为什么"类问题 | 方向 | 人工 | 暂不服务（not_doing，见 §7） |
| ~~前提-结论~~ | **v0 不建**：论证结构（claim→reason→evidence）在写作场景重要，但可先由 exemplify（例证）+ sequence（论证步骤）组合表达；独立类型需"逻辑蕴含"证据 | 方向 | 人工 | v1 候选（写作/论证） |

**结论**：真正独立 = **contains / prerequisite / sequence / contrast / exemplify** 五类；`reference` 是 link；其余归字段/派生/v1。

---

## 4. Q5 决策 → 边 → 字段（主战场）

> 判据：**没有对应决策的边不该存在**（Q2 的反向约束）。

| 用户决策 | 需要的边/数据 | 边需要什么字段 | 当前是否有数据 |
| --- | --- | --- | --- |
| **① 我该先学什么** | `prerequisite`（A→B）+ 节点掌握度 + 计划顺序（sequence 参考） | `from,to,type=prerequisite,reason(为何依赖),strength(0-1),source(author|plan|infer),evidence` | ❌ 无 prerequisite 边（真实库 408 边全 reference） |
| **② 为什么和我有关** | 从当前焦点到目标的路径（contains/prereq/exemplify/contrast 组合）+ 相关度 | `path_types,hops,relevance(0-1),why(一句话)` | ⚠️ 只有 reference relevance（graph.json 的 `relevance:0.7`，派生自链接） — 不是语义相关 |
| **③ 这条跳转要不要点** | `reference` link：目标类型/摘要/是否在 KP 范围内/目标是否有内容 | `anchor_text,occurrence,targets[],file,line,target_kind(KP|非KP),target_summary` | ✅ 有 wikilink 数据；且已有"不在 KP range 内不建边"的审计规则（`graph_audit.json` issue `instance_outside_kp`） |
| **④ 这块内容掌握了吗** | 不是边：卡片状态 + 作答记录 + 错题归因 | `card_id,kp_id,state,due,stability,difficulty,reps,lapses,last_review` + `attempt verdict` | ✅ 有（`progress.json`/`attempts.jsonl`/`cards.json` 的 `kp_id`） |
| ⑤（附加）这段该怎么写 | `sequence`（模板步骤）+ `exemplify`（论点→例证）+ `contrast`（对比论证槽位） | `step_index,slot,function,template/example` | ⚠️ 模板/槽位在文档里（L14/L12/contrast-linkers），**未结构化**为边/字段 |

**说明**：③/④ 已经可用；①②⑤ 需要新增语义边或结构化字段。若 0.5 只做 D4 的"域概览+ego"，则 ①（先学什么）**完全没有数据可答**——这是对 D4 的主要修正点。

---

## 5. Q2 / Q4 / Q6 / Q7

### Q2 边的存在性（用户需不需要看见这条边）
- **判据**：边的存在必须服务 §4 的某个决策；若只是"文字里出现、可以点过去"，那是 **link**，不画成边（或作为可开关的"引用层"，视觉上与语义边区分：细虚线/灰色，不参与推理与布局权重）。
- **现状实测**：真实库 121 节点 / **408 边全部 type=reference**，其中 406 `origin=link`、2 `origin=sidecar_edge`；**没有一条语义边**（`ev:file:docs/example/AAA_Vocab/.memoria/build/graph.json`）。⇒ 当前"图谱"回答不了"先学什么/为什么相关"，只能回答"有哪些引用"。
- **边界案例**：链接落在 KP range 外 ⇒ 审计明确"图谱不建边"（`graph_audit.json` `instance_outside_kp`，`expressions/patterns/feedback-hedging.md#L133-L135`）——这已经是一条现成的"边存在性"规则，应保留并升级为字段 `in_kp`。

### Q4 link 类型 vs edge 类型（用户点一下想要什么）
| | link（引用入口） | edge（语义关系） |
| --- | --- | --- |
| 用户点一下想得到 | "跳到出处/定义/目标页，并看到锚点上下文" | "告诉我为什么连着：关系是什么、方向、证据、路径" |
| 数据字段 | `anchor_text/occurrence/targets/file/line` | `type/from/to/direction/reason/evidence/strength/derived` |
| 视觉 | 文内链接；图里**默认不显示**（可开"引用层"，灰细线） | 图里显示：颜色=类型、箭头=方向、粗细=强度 |
| 现状 | 已有（408 条） | **0 条** |

**结论**：D1 的 `reference` 应降级为 link 而不是"兜底边"；否则"参考关系"会污染语义图布局，用户看不出哪条能回答 Q5。

### Q6 2D/3D 差异（用户读图角度）
- **3D 会误导方向性**：旋转/遮挡/深度让"箭头从谁指向谁"不可读；同一张图在不同视角下可读性不同 ⇒ 有向边（prereq/sequence/exemplify）**不应只用 3D 表达**。
- **建议**：3D 只做**总览/探索**（无向或弱有向、点云/星系）；任何决策类任务（先学什么/为什么相关）切 2D（树/ego/矩阵/链）。若 3D 必须显示有向边：箭头屏幕空间恒显 + 类型 legend + hover 显示 reason，且 3D 下不提供"先学什么"结论。
- **可证伪**：若用户研究显示 3D 在"找先修/找路径"任务上不慢于 2D 且正确率不低，则本条不成立。

### Q7 与 task-86 已裁 D1–D6 的兼容（judge，不遵守）
| 裁决 | 判定 | 理由（证据） |
| --- | --- | --- |
| D1 本体 4 类（contain/reference/prerequisite/exemplify） | **部分推翻** | contain/prereq/exemplify 保留；`reference` 降为 link；**漏 contrast 与 sequence**（真实库有对比槽位表与步骤模板证据） |
| D2 跨域边允许但默认过滤；域代理=路径首段 | **保留但改默认** | 跨域 exemplify/contrast 正是"迁移"场景的核心；默认过滤应按**场景视图**决定，不是全局一刀切 |
| D3 回落 + 可机读留痕 | **保留** | `graph_audit.json` 的 `instance_outside_kp` 已是现成留痕；应扩展为统一 `why_no_edge` 字段 |
| D4 0.5 只做域概览 + ego network | **部分推翻** | ego 能答"为什么相关"，**答不了"先学什么"**；0.5 至少要有 prerequisite 链（或显式声明"先学什么"推迟到 v1 且 UI 不承诺） |
| D5 默认 force + 毛球态提示 | **保留但加约束** | 真实库 408 条 reference 边的 force 图 = 毛球；默认必须过滤到"语义层"，引用层默认关 |
| D6 不补外部对标 | **设计阶段不成立** | 关系本体需要先验：至少引用 2–3 个学习科学/概念图/论证结构框架并给 falsifier；"不追产品对标"可保留 |

---

## 6. 可证伪断言（每条写"若观察到 X 则本条不成立"）

1. **F1 一份数据多视图**：若某场景无法用 5 类关系 + 过滤/布局表达（例如出现必须新增"场景专属关系"才能回答的决策），则 F1 不成立。
2. **F2 五类独立**：若能证明 `contrast` 或 `sequence` 可由 contains/prereq 组合自动生成且用户认可，则相应类型不必独立。
3. **F3 reference 不是边**：若 A/B 实验显示把 reference 边显示在图里能显著提升任一 Q5 决策的正确率/速度，则 F3 不成立（可保留为可选层）。
4. **F4 先学什么必须 prereq**：若在没有 prerequisite 边、仅靠 contains+掌握度的情况下用户仍能答对"先学什么"（≥80% 一致），则 F4 不成立。
5. **F5 3D 不用于决策**：若 3D 在"找先修/找路径"任务上不劣于 2D（时间、正确率、主观可读性），则 F5 不成立。
6. **F6 视图切换足够**：若 6 个视图预设中出现超过 2 个需要"额外节点类型/字段语义冲突"，则"不新增数据结构"不成立。
7. **F7 D4 需补 prereq 链**：若 0.5 的 ego-only 版本在真实用户试用中"先学什么"类问题发生率 <10%，则可推迟 prereq 链。

---

## 7. unknowns / not_doing

### unknowns（登记，不自欺）
- **U1**：5 类边的**人工标注成本**未知（真实库 121 节点 408 link；若每条语义边都需人工确认，成本可能不可接受）⇒ 需测"每 10 节点需人工确认几条"。
- **U2**：`contrast` 与 `exemplify` 的半自动候选（从标签/位置/结构提示）准确率未知。
- **U3**：跨域边（D2）在真实使用中的价值未知（迁移场景是否真的需要图，还是"写作喂养口语"这种清单就够）。
- **U4**：3D 可读性无用户证据（本提案只有推理 + 机制推理，没有读数）。
- **U5**："掌握了吗"与图的关系未知：是否需要在图上叠加掌握度着色（可能造成"颜色噪声"）。
- **U6**：外部先验框架未调研（D6 争议点；本提案未引文献，只从真实库反推）。

### not_doing（本 Phase 不做）
- 不做数据库 schema / UI 实现 / 具体布局算法（设计辩论阶段）。
- 不建 `causal` / `前提-结论` 边（v1 候选，需证据与字段定义）。
- 不做"每个场景一套图结构"（与 F1/F6 冲突）。
- 不把 tags 当边（tags 是属性/场景权重）。
- 不承诺 3D 能回答决策问题。

---

## 8. 证据清单（可复核）

```
ev:file:docs/example/AAA_Vocab/.memoria/build/graph.json            # 121 nodes / 408 edges，全 type=reference；origin=link 406 / sidecar_edge 2
ev:file:docs/example/AAA_Vocab/.memoria/build/graph_audit.json       # instance_outside_kp：「不在任何 KP range 内，图谱不建边」
ev:file:docs/example/AAA_Vocab/.memoria/sidecars/expressions/patterns/contrast-linkers.memoria.yaml#L3-L22   # KP 字段：id/range/tags(对比/转折/写作/口语)/links
ev:file:docs/example/AAA_Vocab/expressions/patterns/contrast-linkers.md#L3-L5,L23-L33   # 「跟谁比、往哪转」；对比槽位表
ev:file:docs/example/AAA_Vocab/expressions/patterns/enumeration-linkers.md#L3-L5         # 五槽位（第一点/追加/末项/结论）
ev:file:docs/example/AAA_Vocab/vocab/blend.md#L6,L9-L22,L24-L45                          # 易混对比、定义+例句、词族/搭配
ev:file:docs/example/AAA_Vocab/plan/exam-2026-11-07.md#L11-L21,L25,L41                    # 五段切分/复习卡/写作喂养口语/六图型/五题型
ev:file:docs/example/AAA_Vocab/writing/SimonClass/L14-Planning.md#L3,L10,L16             # 写作三步序列
ev:file:docs/example/AAA_Vocab/writing/SimonClass/L12-Part2MainBody.md#L10,L24           # 三理由顺序；Idea-Explain-Example
ev:file:docs/example/AAA_Vocab/.memoria/agent/review/cards.json                         # 80 卡，card_id/kp_id/front/back
ev:file:docs/example/AAA_Vocab/.memoria/agent/review/progress.json                      # state/due/stability/difficulty/reps/lapses/last_review
ev:file:docs/example/AAA_Vocab/.memoria/agent/review/attempts.jsonl                     # verdict/elapsed_ms/source
ev:file:docs/example/AAA_Vocab/.memoria/agent/fsrs.py#L1-L20                            # FSRS-5 due/grade 调度
```
