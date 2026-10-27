# G1 — 评价框架是否成立（Graph Utility Evaluation / 图谱可用性评价）

> **议题**：G1 学科定名与评价框架是否成立。**只做 G1**；不进入 G2–G6，不 commit、不改产品代码、不写 docs/design。
> **输入**：人 2026-10-27 原话（详见 task-203）；Lead 的四层框架（L1 节点 / L2 边 / L3 链路 / L4 图谱）与 GUE 定名。
> **基线快照**：`artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理`，26 md / 11 sidecar，
> MANIFEST sha256 `a4beaedc5f852816…`，taken_at `2026-10-27T14:09:46`；HEAD `1b3f6787a47a670e…`（dirty worktree，不涉本语料）。
> **本文件产物**：`G1-baseline.json` + `scripts/G1-baseline.py`（复跑见 §11）。
> **证据分级**：`A` 论文/标准｜`B` 本仓代码/运行数据｜`C` 优秀开源｜`D` 语料观测（**D 不作设计依据**）。
> **硬规则（来自人/Lead）**：任何"该边/该链路应当存在"的主张，必须给 **消融实验** 或 **人判矩阵 + 一致性系数**，二者至少其一。

---

## 0. 结论摘要（先给人看）

1. **对象覆盖：四层框架覆盖了人的四类问题，没有漏掉"评价对象"**（映射见 §2）。但**维度是一维的**：
   框架把"语义正确 / 必要性 / 效用 / 成本 / 溯源 / 时间"混进了层级，导致"这条边对用户有多大帮助、该不该存在"这种**属性问题**无处安放（现被塞进 L4）。
2. **建议保留 L1–L4 作为"评价单元"，把 GUE 升级成 `单元 × 属性` 矩阵**（§4）：
   `S 语义正确性 / U 必要性-效用 / G 溯源 / T 时间有效 / C 成本`，每一层都要各测一遍。
   另拆 **L4 = L4a 模型充分性（CQ） + L4b agent 任务效用（Cranfield/A-B） + L4c 人本效用（用户研究）**，
   并新增 **M 元评价层**（评价方法自身靠什么证明可信）。
3. **学科名**：它不是一门新学科，是 **5 个成熟领域的交叉 + 2 个借用方法**（人类评价/元评价；§2.4，均给 A 源）。
   `GUE` 作为板块名可用，但**不要宣称"新学科"**；对人的回答应是"这是图谱质量/本体评价/IR 评价/元路径/人因的交叉"。
4. **L3 三个候选测法：必要，但不充分**（§5.3 对照表）。缺 6 件：方向与组合语义、溯源支撑、非冗余/信息量、
   任务效用、负例构造规范、一致性协议。且**当前图做不了代表性 L3 测量**：62 边 / 357 节点里只有 **79 个节点(22.1%)被边覆盖**、
   **278 个孤立点**、**296 个连通块**、最大块 **25 节点**（§3）。
5. **现在能立刻测的**：L1 静态指标；**L2 人判矩阵（62 条边可穷举，3 人×62×5 项 ≈ 1–2 人日）**；L4a 的 CQ 清单与覆盖矩阵（纸面+脚本）。
   **完全没有测法的**：L2 边效用的统计级消融、L3 路径语义真值、L4b/L4c、以及跨层的成本/时间轴（§7）。

---

## 1. 任务边界与判定规则

```
本文件只回答四问：
  ① 四层框架是否覆盖人的四类问题？有漏吗？
  ② 每层可操作测法是什么（尤其 L2 边、L3 链路；L3 三候选够不够）？
  ③ 证据从哪来（A 论文 / B 本仓 / C 开源 / D 语料）？
  ④ 哪些层现在完全没测法、哪些能立刻测？
不做：G2 基线全量、G3/G4 实测、G5 数据模型定稿、G6 A/B 实验。它们只给依赖与顺序（§8）。
```

**统一判定规则（本文件所有"该不该存在"类结论都受它约束）**

| 规则 | 内容 | 依据 |
|---|---|---|
| R1 | 主张"某边/某链路应存在/应删除"⇒ 必须给 **消融实验** 或 **人判矩阵+一致性系数**（至少其一） | 人/Lead 硬约束 |
| R2 | 人判必须 **多人独立 + 一致性系数**（Krippendorff α 或 Fleiss κ）+ 分歧裁决；单人人判不算证据 | A 方法（Krippendorff 2004；Fleiss 1971） |
| R3 | 任何数量必须带 **语料三元组 (HEAD, manifest_sha256, 时刻) + 测量源 + build 状态**；跨语料/跨 build 不可比 | B：`kg-ontology-v0.md:87-101`（D-KG-01）、`kg-visualization-v0.md:244-278` |
| R4 | **D 源（语料观测）不作设计依据**；只作基线/测试集/最坏输入 | 人前提（2026-10-27） |
| R5 | 禁用 **长度/行数/块数** 作质量判据；只可作成本/影响面指标 | B：`kg-ontology-v0.md:156`（D-KG-07） |
| R6 | "全部一致/全部为 0" 类结论先构造"必须失败"的用例；构造不出 ⇒ 无判别力 | 团队治理规则（假通过） |

---

## 2. 人的四类问题 → 四层映射与覆盖判定

### 2.1 映射表

| # | 人原话/Lead 归纳 | 评价对象 | 框架层 | 覆盖？ |
|---|---|---|---|---|
| Q1 | 「网内几个节点提取出来他们组成的这条链路，是否具有语义」 | 路径（节点序列+边序列） | **L3** | ✅ 对象覆盖 |
| Q2 | 「一些图谱中的边，是否具有语义，**对用户对人有多大帮助**，而**应当存在与否**」 | 单条边 | **L2** | ⚠️ 对象覆盖；但"帮助/必要性"是**属性**，框架未给层内位置 |
| Q3 | 「节点/边/图谱的数据模型定义，是否能够很好 ①支撑 agent 记忆 ②辅助 agent 检索」 | 数据模型/schema | **L4** | ⚠️ 对象覆盖；但 L4 混了"模型可表达"与"任务有效"两件事 |
| Q4 | 「反正我感觉这是一门我不知道叫什么名字的学科」 | 学科定名 | GUE 命名 | ✅ 见 §2.4 |
| — | （人未直接问，但为 Q1/Q2 前置）节点本身是否可判 | 节点 | **L1** | ✅ 合理补充（否则边/链路测不了） |

### 2.2 覆盖判定的三个缺口（"有漏吗"的回答）

**缺口 1：把"属性"当成了"层"。**
人问的是"边**有没有语义**、**有没有帮助**、**该不该存在**"——这是三个属性（S/U/必要性），不是三个对象。
现框架只在 L4 提"辅助检索"，于是"边有没有用"在 L1–L3 无落点。⇒ **必须矩阵化**（§4）：U（效用/必要性）要能在 L1/L2/L3/L4 每一层各测。

**缺口 2：L4 三合一。**
"数据模型能支撑"至少三种不同测量：① 模型能否**表达**（CQ/本体评价，纸面可测）；② 用上图谱后**任务是否变好**（Cranfield/A-B）；③ **人**是否受益（用户研究）。
三者证据类型、成本、失败模式完全不同，不能合成一个 L4。⇒ 拆 L4a/L4b/L4c（§4.2、§5.4–5.6）。

**缺口 3：缺 3 条跨层轴 —— 溯源(G)、时间(T)、成本(C)。**
- **G 溯源**：边/链路若不能回溯到原文区间，语义真值就无法核（当前 graph edge **没有** `instances/fact/出处`，§3）。这是 L2/L3 可测性的前提，不是附属项。
- **T 时间**：agent 记忆的核心是"事实何时有效/何时被取代"（`E1-memory.md:15`：Graphiti `valid_at/invalid_at/expired_at`、Mem0 history）；当前图谱无任何时间字段（§3）。没有 T，"支撑 agent 记忆"无法评价。
- **C 成本**：人的"对用户有多大帮助"= 收益 − 成本（token/延迟/认知负担）；Cranfield 只测有效性不测成本；agent 检索的"减少往返"本质是成本轴。

### 2.3 一个 repo 特有、框架必须显式处理的问题：**link ≠ edge**
本仓把两种东西分开了（B：`kg-ontology-v0.md:31-56`）：
```
Link  正文锚点：为什么这段文字能跳过去；带 instances 行号；【不承诺语义关系】
Edge  语义关系：两个知识点是什么关系；纯边无行号；由 link 投影时才带锚点
类型  reference（无断言跳转）/ extend（延伸）/ contain（整体-部分，派生）
```
⇒ GUE 的 L2 **必须**：
- 把 `reference` 从"语义边集"里**排除或单列为负类**——它按定义不承诺任何关系（B：`kg-ontology-v0.md:48-56`）；
- 把 `contain` 标为**结构派生边**（由标题层级/行区间推导，B：`edge_types.py:35-38`）——它的"语义正确性"是"包含是否成立"，不是"新语义信息"；
- 对 `extend` 先做**语义定义**（当前代码只有枚举名，没有谓词定义/域值/方向约束，B：`edge_types.py:29-54`）。
否则 L2 的"边语义合格率"会被 `reference`（无断言）与 `contain`（派生结构）稀释成无意义数字。

### 2.4 学科定名：它是什么、不是什么

**结论：不是一门新学科，是 5 个成熟领域的交叉 + 2 个借用方法（人本效用/元评价）。**（Lead 的 GUE 定义方向正确，这里给每个分量的 A 源锚点）

| GUE 分量 | 对应成熟领域 | A 源锚点 | 这个领域能借什么 |
|---|---|---|---|
| 知识图谱质量评估 | KG / Linked Data quality | Zaveri et al. 2016, *Quality Assessment for Linked Data: A Survey*, Semantic Web 7(1):63–93, DOI `10.3233/SW-150175` | 质量维度分类（accuracy/completeness/consistency/timeliness/provenance…）→ 直接映射 S/G/T 轴 |
| 图谱精化 | KG Refinement | Paulheim 2017, *Knowledge Graph Refinement: A Survey of Approaches and Evaluation Methods*, Semantic Web 8(3):489–508, DOI `10.3233/SW-160218` | 边/节点的纠错与补全、silver standard 评估法 → L2 真值与必要性 |
| 本体评价 | Ontology Evaluation / CQ | Grüninger & Fox 1995, *Methodology for the Design and Evaluation of Ontologies*（IJCAI-95 Workshop）；Gómez-Pérez 2004, *Ontology Evaluation*, Handbook on Ontologies, Springer | **Competency Questions**：用"该模型必须能回答的问题集"评价模型 → L4a |
| 任务型检索评价 | IR evaluation（Cranfield 范式） | Cleverdon 1967, *The Cranfield Tests on Index Language Devices*, Aslib Proceedings 19(6):173–194；Järvelin & Kekäläinen 2002, *Cumulated Gain-based Evaluation of IR Techniques*, ACM TOIS 20(4), DOI `10.1145/564376.564421` | 固定任务集 + 相关判定（qrels）+ nDCG/MAP/Recall → L4b |
| 元路径语义 | Meta-path / 异质网络 | Sun et al. 2011, *PathSim: Meta Path-Based Top-K Similarity Search in Heterogeneous Information Networks*, PVLDB 4(11):992–1003；*Are Meta-Paths Necessary? Revisiting Heterogeneous Graph Embeddings*, CIKM 2018, DOI `10.1145/3269206.3271777` | **只借"类型化路径"的表示**；注意它测的是**相似度/邻近性，不是命题真值**（L3 不能直接套） |
| 人本效用 | Human-centered IR / HCI 评价 | （无单一权威；见 Cranfield + 用户研究方法，§5.6 自定义） | 用户任务时间/成功率/理解度/主观信任 |
| 元评价（新增） | 测量学/评估方法学 | Krippendorff 2004, *Content Analysis*（α）；Fleiss 1971, *Measuring Nominal Scale Agreement Among Many Raters*, Psychological Bulletin 76(5):378–382 | 一致性、信度、判别力、已知好坏夹具 → M 层 |

> **对人的诚实回答**：没有"图谱可用性评价"这个现成学科名；但**不需要发明新学科**——
> 它就是把上述 5 个领域的评价方法**组合**到"节点/边/链路/图谱"四种对象上，再加"agent 记忆/检索"这个任务域。
> `GUE` 可作板块名；若人想改名，可考虑 *Graph Quality & Utility Evaluation*（更贴近"质量+效用"）。

---

## 3. 基线事实（B 源，绑定 §R3；数字来自 `G1-baseline.json`）

```text
测量源     collect_graph_data() 于 frozen 副本（临时目录复制，无 .memoria/build ⇒ pre_build 状态）
语料身份   数字通信原理 · 26 md / 11 sidecar · MANIFEST a4beaedc… · HEAD 1b3f6787…
产物       G1-baseline.json（stats 段可逐字节复跑；仅 generated_at 变）
```

| 指标 | 值 | 说明 |
|---|---|---|
| 节点 / 边 | **357 / 62** | 边/节点比 **0.174**（对照：docs/example 语料为 3.02，B：`kg-visualization-v0.md:236`，**不可跨语料比**） |
| 边类型 | contain **33** / extend **21** / reference **8** | 3 值枚举；`reference` = 无断言 |
| 边来源 | range(派生) **33** / sidecar_edge **26** / link(投影) **3** | 派生边 36 条、作者边 26 条 |
| 作者边 | **extend 21 + reference 5**（全在 `教材/03`） | 21 条 extend 基本按节顺序连成一条链（见 §5.2 隐患） |
| relevance | 0.9×33 / 0.7×8 / 0.6×21 | **100% = 类型默认值**（`edge_types.py:50-54`），无逐边判断 |
| 边字段 | `type, source_id, targets[1], relevance, derived, origin, file` | **无** `fact / valid_at / invalid_at / confidence / provenance / instances`（各 0/62） |
| 节点字段 | `id, kp_id, name, label, description, file, start_line, end_line, range_ok` | 无 `kind / source / source_version / tags` |
| 节点 description 非空 | **0 / 357（0%）** | L1 "可判性"字段完全没落数据 |
| 节点 range_ok | **352/357 = 98.6%** | 5 条坏（与 Q1 frozen 口径一致；`G1-baseline.json.counts.range_ok_nodes`） |
| 连通性 | 被边覆盖 **79/357 = 22.1%**；孤立点 **278**；连通块 **296**；最大块 **25 节点** | 平均度 0.347 ⇒ **图极稀疏**，L3 材料极少 |
| 度分布 | deg1:56, deg2:13, deg3:4, deg4:3, deg5:1, deg6:1, deg7:1 | 无 hub；最长链近似"一条章内链 + 若干父子对" |
| 使用记录 | **无** | `nodeClick` 有前端事件但零统计消费、`edge_id` 从未记录（B：`kg-ontology-v0.md:65,68-73`）；可视化埋点 v0 只采 nodeRadius/graphStyle（B：`kg-visualization-v0.md:204-221`） |
| agent 读边 | **否** | `get_graph_data()` 无 agent 调用者（B：`kg-ontology-v0.md:20`；我复核：consumer 仅 `document.py:2127`/`ui.py:374`/`kb_build.py`） |

**四个必须写进 G2 的"基线陷阱"**

1. **两套语料不能混**：`kg-ontology-v0.md:21` 说"全部快照 100% `reference`、relevance 100% 默认 0.7"——那是 docs/example（AAA_Vocab）语料；
   本库（数字通信原理）实测 **21 条 extend / 26 条作者边**、relevance 0.6/0.7 都有。⇒ 该结论**不可移植**，GUE 基线必须按本库重测（这正是 G2 要做的事）。
2. **build 会改边数**：`kb_build` 会回写源 md/sidecar，实测同一副本 build 前 404 边 → build 后 454 边（B：`kg-visualization-v0.md:273-278`）。
   GUE 任何边/度测量必须记录 **pre/post_build + build sha**；本次基线 = pre_build。
3. **collector 文档与代码不一致**：`collector.py:44-49` docstring 写"不读侧车 edges[]"，但实现经 `derive_sidecar_edges` **读取** `sidecar.edges[]`
   （`edge_derivation.py:643-676`）。G2 写基线说明时以代码为准，并登记该文档缺陷。
4. **现有质量检查只到"结构"**：`validate_kb`（`document.py:2154-2205`）调用 `link_audit`，检查的是 missing_sidecar_link / missing_instances / instance_outside_kp /
   unresolved_target / virtual_link（`link_audit.py:24-30`）——**没有一条是语义/效用**。GUE 不重复造这些，直接把它们当 L2 的"结构前置闸"。

---

## 4. 框架修正：GUE = 单元 × 属性 矩阵（建议采纳；人可改）

### 4.1 两个维度

```
评价单元（对象）  L1 节点 | L2 边 | L3 链路 | L4a 模型 | L4b 图谱任务效用 | L4c 人本效用
评价属性（每条单元都要过） S 语义正确性 | U 必要性/效用 | G 溯源支撑 | T 时间有效性 | C 成本
元层 M：评价方法自身（信度/判别力/复现性）
```

**为什么这样改**：人的原话里"链路是否有语义"= L3×S；"边是否有帮助/该不该存在"= L2×U（+L2×S）；
"模型能否支撑记忆/检索"= L4a×{S,G,T} ∪ L4b×U；"对人有多大帮助"= L4c×U 且 C 参与。
矩阵化后每个格子都能单独定义"怎么测/合格线/放弃条件"，且**不会出现"边有没有用被塞进 L4"**。

### 4.2 格子优先级（G1 只排序，不执行）

| 优先级 | 格子 | 理由 |
|---|---|---|
| P0 | **L2×S**（边语义真值/类型可表述） + **L2×U**（必要性/消融） | 人点名；且是人判矩阵可穷举的唯一层（62 条边） |
| P0 | **L3×S**（链路语义） + **L3×G**（溯源） | 人最关心；但需先定路径来源（§5.3） |
| P1 | **L4a×S/G/T**（CQ + 模型字段充分性） | 纸面可先做；决定"数据模型能否支撑记忆" |
| P1 | **L1×S**（节点可判） | Q1/Q2 前置；字段现状 0% description |
| P2 | **L4b×U/C**（agent 任务 A/B） | 需任务 harness，属 G6 |
| P2 | **L4c×U**（人本） | 需用户研究协议 |
| P3 | 全层 ×T / ×C | 数据模型先补字段；成本轴依赖 harness |

### 4.3 与 Lead 五分量定义的对应

| Lead 的 GUE 分量 | 在矩阵里的落点 |
|---|---|
| KG Quality Assessment | 全层 ×{S,G,T} 的**维度字典**（Zaveri 的质量维度） |
| Ontology Evaluation (CQ) | **L4a×S/G/T** + L2 的"类型定义是否可表述" |
| Cranfield 任务型检索评价 | **L4b×U/C**（以及 L2/L3 的消融任务集） |
| Meta-path semantics | **L3×S** 的"类型化路径"表示（**只借表示，不借真值**） |
| 人本效用 | **L4c×U** + L2 人判矩阵里的"对用户帮助"项 |

---

## 5. 每层可操作测法（定义 / 怎么测 / 合格线 / 放弃条件 / 现在能否测）

> 所有门槛都是**初值（经验判断，待 G2 校准）**；校准前只能作"研究用"，不能当产品门禁。
> 人判类门槛统一要求：≥3 名独立标注者、盲化（不显示类型/来源）、先写标注手册、算 α/κ、分歧裁决。

### 5.1 L1 — 节点级（可判性 / 边界 / 身份）

**可操作定义**：节点可判 ⇔ ① 身份稳定（`id` 唯一、range 可解析）；② 边界明确（start/end 在原文可定位且不反转）；
③ 有可判摘要（不看原文能判断"该不该读"）；④ 可溯源（能回到原文区间）。

**测法（4 条，前 2 条现在就能跑）**

| 测法 | 操作 | 指标 | 现在能否测 |
|---|---|---|---|
| L1-1 结构静态 | 扫全库：`range_ok`、`id` 重复、start=heading 比例、嵌套/重叠、`description` 非空率 | range_ok（本库 352/357=98.6%）、描述非空率（本库 **0%**）、名称碰撞率 | ✅ 立刻（已有 `kp_index`/`validate_kb`） |
| L1-2 人判矩阵 | 分层抽样 40–60 节点（教材/幻灯片/笔记 × 描述有无）；每节点 3 项：含义清楚(1–5)、边界明确(1–5)、能否只凭名字决定"该不该读"(是/否/不确定) | 均值、α、% 可判 | ✅ 立刻（需 3 人 × ~1.5h） |
| L1-3 摘要有效性 A/B | 同一批节点：只给 `name` vs 给 `description`，让 agent/人判断"该不该读"（二分类） | 准确率提升、判断时间 | ⚠️ 需 harness（G6 可复用） |
| L1-4 检索选择效用 | 给定 20 个真实问题，只允许用节点摘要选择 top-k KP | recall@k vs 无摘要基线 | ⚠️ 需问题集+模型固定（G6） |

**合格线（初值）**：range_ok ≥98%（本库已过）；`description` 非空率 ≥90%；人判"可判"比例 ≥80% 且 α≥0.67；名称碰撞 <5%。
**放弃条件**：α<0.5（判定标准不可信）；或"可判"比例与随机无差异（说明题目/标注无效）；或必须重写节点 schema 才能测（转 G5 先改模型）。
**诚实**：L1 与"agent-index 的 R2 可判性"重叠——GUE 只测**图节点**（357 KP），R2 测切片；两者共享 `kind/source/source_version` 字段，**不要造两份基线**（B：`kg-agent-index-v0.md:230-241`）。

### 5.2 L2 — 边级（"这条边是否具有语义 / 该不该存在"）

**先把概念分清（repo 特有，见 §2.3）**

| 边类 | 语义地位 | 怎么评价 |
|---|---|---|
| `contain`（33，派生） | 结构包含，由标题层级/range 推导 | 测"包含是否正确/一致"（结构正确性），**不测"新语义信息"** |
| `reference`（8，其中 3 条 link 投影） | **无断言跳转**，按定义不承诺关系 | 从语义边集**排除**，单列为"跳转可用性"（L2×U 的另一类） |
| `extend`（21，作者） | 枚举名，**当前无谓词定义/域值/方向约束** | 先定义谓词，再测 S/U |

**可操作定义**：边 e=(s,type,t) 语义有效 ⇔
① `type` 有**谓词定义**（可用一句"s 与 t 是<谓词>关系"表述，且有正/反例）；
② 该命题在原文/证据上**为真**（可溯源到区间）；
③ 方向正确；
④ 非冗余（不是仅由层级/顺序推导出的重复信息）；
⑤ 有证据记录（provenance）。
**"该不该存在"（必要性）** = 语义有效 ∧ （移除后任务变差 **或** 人判"必须保留"）。

**测法（5 条；L2-0/L2-1/L2-2 现在就能做，L2-3 需 G6）**

| 测法 | 操作 | 指标 | 现在能否测 |
|---|---|---|---|
| **L2-0 结构前置闸** | 复用 `link_audit`：目标是否存在、instances 是否缺、实例是否落在 KP 内、是否 virtual | 0 error | ✅ 立刻（`validate_kb`） |
| **L2-1 类型可表述性** | 对 3 种类型先写"谓词定义 + 2 正例 + 2 反例"；再对每条作者边让人判断"这句话是否可表述且可判真假" | 类型定义覆盖 3/3；作者边可表述率；`reference` 占比单列 | ✅ 立刻（定义工作 0.5 人日 + 人判） |
| **L2-2 人判矩阵（核心）** | **穷举 62 条边**（作者边 26 + reference 8 + contain 抽 20 ≈ 54–62 条；全做约 930 项）。盲化呈现（只给 s/t 文本+range，不给类型）。每人每边 5 项：①能否说清关系 ②命题是否真 ③方向是否正确 ④是否冗余 ⑤保留/删除/不确定 | 每项分布；**Krippendorff α（序数）**/Fleiss κ（分类）；保留率；按边类型分组 | ✅ 立刻（3 人 × 62 × 5 项 ≈ 930 判断 ≈ 2–3h/人） |
| **L2-3 消融实验（必要性）** | 任务集 T（见 L4b）分三组：全图 / **去掉候选边组** / **随机去同等数量边（控制）**；先按类型组消融（extend/contain/reference），再对候选边单条消融；指标=答对率、路径支撑率、iters、tokens；统计=配对 bootstrap/置换检验 | Δ_targeted − Δ_random（必要性效应）、显著性、效应量 | ⚠️ 需任务 harness（G6）；当前 62 边**统计功效极低**，只能做"类型组级"消融 |
| **L2-4 约束/规则一致性** | domain/range、基数、对称/传递性约束；规则挖掘（AMIE+ 类）在留出集上的精度 | 违规率、规则精度 | ❌ 当前 62 边、无类型定义 ⇒ 不可做（登记为 G5 后） |

**合格线（初值，G2 校准）**：L2-0 = 100%；类型定义 3/3 且 `extend` 有谓词；
作者边"语义为真且不冗余"≥80%、α≥0.67；`reference` 不计入分子；
必要性：至少 1 个任务族上 **targeted 移除 > 随机移除**（p<0.05，效应量报告）。
**放弃条件**：α<0.5；或类型定义写不出（无法表述 ⇒ L2 不成立，转 G5 改类型空间）；或消融显示随机=targeted（边无判别力）。
**与既有裁决的关系**：`kg-ontology-v0.md:161-169` 的"新语义类型准入三闸"（区分度≥10 条或≥5% / relevance 异质度 std>0 / 决策绑定 + ≥10 人工确认）可作为 L2 的**产品准入闸**复用；GUE 不重新发明，只在它前面加"先测现有 3 类是否可表述"。

### 5.3 L3 — 链路级（"这条链路是否具有语义"）**← 人最关心**

**可操作定义**：路径 p = v0 —e1→ v1 —…— ek→ vk（k≥2）"有语义" ⇔
① 每一跳在 L2×S 上有效；
② **组合后有真值**：按边类型的**组合表**（如 contain∘contain = contain 传递；extend∘extend 未定义 ⇒ 不能自动传递）得到命题；
③ 方向一致；
④ **可溯源**（每个节点/边能回到原文区间）；
⑤ **非冗余/有信息量**（不是单纯沿标题层级的祖先链）；
⑥ 对某任务/问题有支撑（U）。

**对 Lead 三个候选的逐个评估**

| 候选 | 操作化 | 能证明什么 | 缺什么 / 风险 | 判定 |
|---|---|---|---|---|
| ① NL 复述成一句有意义的陈述 | 盲化给路径（节点名+类型序列，不给原文）→ 标注者写一句话 → 第二人判"真/假/无支撑" | 路径在**人可读层面**是否有可表述语义；可发现"拼得出来但不真" | 会**编造看似合理的句子**（必须加"原文支撑"核验）；不覆盖长路径/检索用途；把"边错"与"组合错"混在一起 | **必要**（S 的可操作近似） |
| ② 支撑一个真实提问的推理步骤 | 先建 CQ/问题集 + **独立于图**标注 gold 推理链（节点/关系），再测路径对 gold 链的 precision/recall | 路径的**任务效用**（最贴近人的"有用"） | 成本最高；**循环风险**：若 gold 链从图里抽，就是自证；需问题集+独立标注（G2/G6 前置） | **必要且最该做**，但现在做不了（无 gold 链） |
| ③ 与随机/乱序链路区分度 | 构造负例：随机节点对、打乱边序、反向、类型替换、语义空链；测分类/人判的 balanced accuracy/AUROC | 路径表示**是否携带可区分语义**（判别力） | **负例太容易**（随机对常不连通、乱序语法不通）⇒ 区分度虚高；需校准难度 + 人类上限；且"有意义"的正例标签仍来自①② | **必要但不充分**（效度检验，不是主测法） |

**结论：三个候选必要但不充分，缺 6 件 ——**

1. **方向与组合语义**：需先定义边类型的"组合表"（哪两种类型可组合、组合后是什么、是否传递）。
   A 源可借：OWL 2 属性链（property chains）https://www.w3.org/TR/owl2-syntax/#Property_Chains ；
   SPARQL 1.1 property paths https://www.w3.org/TR/sparql11-query/#propertypaths 。
   **Meta-path 文献不能替代**：PathSim 一类只定义"类型化路径用于相似度"，不定义命题真值（A：Sun et al. 2011）。
2. **溯源支撑（G）**：每跳必须能回原文区间，否则"复述"无法证伪。当前 graph edge **没有** `instances`（§3），这是 L3 的**硬前置**。
3. **非冗余/信息量**：仅沿 `contain` 的祖先链永远"真"但零信息量；需定义"相对问题的新信息"，并统计冗余链占比。
4. **任务效用（U）**：候选②的完整形态；没有它，"有语义"≠"有用"。
5. **负例构造规范 + 难度校准**：定义负例族（随机/乱序/反向/类型替换/同章干扰）与难度分层；报告人类上限与 trivial-separation 检查。
6. **一致性协议**：多人、盲化、α/κ、裁决；路径级判断比边级更主观，α 门槛应预注册。

**合格线（初值）**：路径复述"真且可溯源"≥70%；α≥0.67；与负例的 balanced accuracy ≥0.80，
**同时报告人类上限与 trivial-separation 检查**（若负例能被"是否连通/语法通顺"这类简单规则区分，则负例过易，需重造，不得当作判别力）。
gold-chain 上的 precision ≥0.7、recall ≥0.5（先小样本）。
**放弃条件**：组合表写不出；或 gold 链无法独立于图构造（循环）；或复述真值率与随机无差异；或冗余链占比 >50%（当前图很可能如此，见下）。
**现在能否测：几乎不能。**
- 当前 62 边、**79/357 节点被覆盖、296 连通块、最大块 25 节点** ⇒ 可枚举路径极少且高度局部；
- 且 **作者边 21 条 extend 基本是"按节顺序"的链**（§3 表；教材/03 的 edges 就是 intro→sampling→ideal→aliasing→bandpass…）——
  这种链的"语义"很可能只是"章节顺序"，会得到"复述成立但零信息量"的结果；
- 因此 **L3 必须先定义"路径候选来源"**（三选一，需 Lead/人裁）：
  (a) 只用现有图路径（诚实但样本≈0，只能做案例研究）；
  (b) 从正文/结构**独立生成**候选路径（研究用，不声称是"图的语义"）；
  (c) 等图扩充后再测（依赖 G5/G6）。
  **不先钉这个口径，L3 结果不可比。**

### 5.4 L4a — 图谱级：模型充分性（CQ / 可表达性）

**可操作定义**：数据模型"能支撑 agent 记忆/检索" ⇔ 对一组 **Competency Questions（CQ）**，
模型（含 schema 字段）能**表达**所需信息，且能从图中**取得**答案（不需要外部隐含知识）。

**测法**
1. **CQ 清单**：从 agent 记忆+检索需求写 25–40 条（示例）：
   记忆类："上次讨论到哪个 KP？""这条结论的来源区间？""该事实何时被取代/是否已失效？""谁写的/哪个会话？"；
   检索类："与 X 相关的 KP 有哪些？为什么相关？""从 A 到 B 的推理链是什么？""这个 KP 属于哪一章/哪一节？"
2. **覆盖矩阵**：每 CQ × 所需字段（身份/时间/类型/方向/来源/版本/置信/删除）→ 可表达/不可表达；
   再用当前图**实测可答率**（脚本 + 人工）。
3. **可表达性编码测试**：给 10 个记忆场景（新增/更新/矛盾/遗忘/跨文档），尝试只用现有 schema 编码，记录"编不出来"的点。
4. **CQ 质量检查**：单答案、无歧义、可判；请第二人复核（α/κ 或 100% 复核）。

**合格线（初值）**：产品关键 CQ 覆盖率 ≥80%；E1 必填字段（身份/时间/类型+方向/来源/版本/可验 char_range）全部可表达；
**放弃条件**：<50% 覆盖或需破坏性改 schema（转 G5 重设计，G1 只登记）。
**现在能否测**：✅ CQ 清单+覆盖矩阵可立刻做（纸面+脚本）；实测可答率需 G2 标注。

### 5.5 L4b — 图谱级：agent 任务效用（Cranfield / A-B）

**可操作定义**：在同一任务集上，**用图谱**（记忆召回/检索扩展/推理链）相对**不用图谱**的 baseline，
在"答对率不降"的前提下，**成本（iters/tokens/延迟）下降**；否则图谱无净效用。

**测法（Cranfield 范式 + 记忆专项）**
```
任务集 T：从真实会话/问题集构造（D 源可作测试集，不作设计依据），固定 topics + gold answers；
条件    ：B0 无图谱（现状） / B1 图谱只读（人看图） / B2 图谱进 agent（召回/扩展/链） / B3 去掉候选边组（消融）
指标    ：答对率、nDCG@k/Recall@k、iters、tool calls、tokens、延迟；配对检验 + 效应量
控制    ：同模型/同 prompt/同温度/固定 seed、N≥3 次、同语料三元组、同 build 状态
预注册  ：指标、停试规则、样本量、非劣界（如答对率下降 ≤2pp）
```
**合格线（初值）**：B2 vs B0：iters ↓≥20% 且 答对率不降（非劣界 2pp）；token 成本不升；
B3 消融：targeted 移除 > 随机移除（p<0.05）。
**放弃条件**：任务集无法构造 gold（循环）；或 B2 只降成本不升质量且用户不感知（价值主张不成立）；或效应只在单题上（不可泛化）。
**现在能否测**：❌ 无 harness。需 G6；但 **G2 可先产出"任务集候选 + gold answers 草案"**。

### 5.6 L4c — 人本效用（用户研究）

**可操作定义**：图谱（尤其"看图/看边/看链路"）是否帮助**人**完成任务、理解结构、建立信任；收益是否大于认知成本。

**测法**：被试内/间设计；任务：找相关概念、理解章节结构、判断某边是否合理、用图学习；
指标：任务完成时间、成功率、理解测验、SUS/信任、访谈；样本量按效应量估算（预注册）。
**合格线（初值）**：任务时间 ↓≥15% 或理解分 ↑≥10%，且主观负担不升。
**放弃条件**：无显著差异或负体验；样本不足（<12 人）只作定性。
**现在能否测**：❌ 需协议+被试；且"人"要先定义（终端用户 vs 开发者）——见 §9 开放问题。

### 5.7 M — 元评价（评价方法自身，GUE 的"系统评价方法"必须包含）

```
M1 标注信度：多人 α/κ + 分歧裁决记录
M2 判别力：已知好/坏夹具（known-good/known-bad）——例如人工构造 3 条明显错的边、3 条明显对的边，
          方法必须把它们分开；分不开 ⇒ 方法无判别力（R6）
M3 判官校准：若用 LLM-as-judge，必须与人类 gold 子集比一致性并报告（不得直接当真值）
M4 不确定度：比例给 CI（Wilson/bootstrap）；人判抽样给抽样误差（可借 Gao et al. 2019 的采样估计，arXiv:1907.09657，见 §6 A8）
M5 复现性：语料三元组 + build 状态 + 脚本 + 同 commit 双跑一致
```

---

## 6. 证据来源清单（A / B / C / D）

### 6.1 A 源（论文/标准；本轮只核对标题/ID，未逐篇读全文）

| # | 出处 | 用途 | 状态 |
|---|---|---|---|
| A1 | Zaveri et al. 2016, *Quality Assessment for Linked Data: A Survey*, Semantic Web 7(1):63–93, DOI `10.3233/SW-150175` | 质量维度字典（S/G/T 轴） | 标题/卷期已核；全文未读（引用维度名，不引数字） |
| A2 | Paulheim 2017, *Knowledge Graph Refinement: A Survey of Approaches and Evaluation Methods*, Semantic Web 8(3):489–508, DOI `10.3233/SW-160218` | 边/节点纠错、silver standard 评估 | 标题/卷期已核 |
| A3 | Grüninger & Fox 1995, *Methodology for the Design and Evaluation of Ontologies*（IJCAI-95 Workshop）；Gómez-Pérez 2004, *Ontology Evaluation*, Handbook on Ontologies | CQ（L4a） | 经典文献；Gómez-Pérez 章节页码未核（只引概念） |
| A4 | Cleverdon 1967, *The Cranfield Tests on Index Language Devices*, Aslib Proceedings 19(6):173–194 | 任务型 IR 评价范式（L4b） | 已核 |
| A5 | Järvelin & Kekäläinen 2002, *Cumulated Gain-based Evaluation of IR Techniques*, ACM TOIS 20(4), DOI `10.1145/564376.564421` | nDCG | 已核（DOI） |
| A6 | Sun et al. 2011, *PathSim: Meta Path-Based Top-K Similarity Search in Heterogeneous Information Networks*, PVLDB 4(11):992–1003 | meta-path 表示（L3 只借表示） | 已核 |
| A7 | *Are Meta-Paths Necessary? Revisiting Heterogeneous Graph Embeddings*, CIKM 2018, DOI `10.1145/3269206.3271777` | meta-path 不是语义真值（反例警示） | 已核（DOI） |
| A8 | Gao et al. 2019, *Efficient Knowledge Graph Accuracy Evaluation*, PVLDB 12:1679 起（2019）；arXiv:1907.09657 | **采样+置信区间**估计 KG 准确率（L2 人判抽样） | arXiv/PDF 已核（PVLDB 卷/起始页） |
| A9 | W3C OWL 2 Syntax — Property Chains https://www.w3.org/TR/owl2-syntax/#Property_Chains ；SPARQL 1.1 Property Paths https://www.w3.org/TR/sparql11-query/#propertypaths | 路径组合语义（L3 组合表） | 标准，URL 稳定 |
| A10 | Krippendorff 2004, *Content Analysis: An Introduction to Its Methodology*（2nd ed., Sage）；Fleiss 1971, *Measuring Nominal Scale Agreement Among Many Raters*, Psychological Bulletin 76(5):378–382 | 一致性系数（R2/M1） | 经典方法 |
| A11 | Mem0 arXiv:2504.19413；Zep arXiv:2501.13956；A-MEM arXiv:2502.12110；MemGPT arXiv:2310.08560 | agent 记忆任务与指标（L4b 任务集参考） | 来自本仓 `E1-memory.md:178-187`（前一研究者已核 arXiv abs） |

### 6.2 B 源（本仓代码/运行数据；file:line 为 2026-10-27 工作区）

| # | 位置 | 事实 |
|---|---|---|
| B1 | `src/memoria/graph/collector.py:44-86` | 节点/边构造；node 9 字段；边来自 range 派生 + link 投影 + sidecar edges |
| B2 | `src/memoria/graph/edge_derivation.py:53-65,296-344,480-592,643-676` | contain 由 range 严格包含派生；link 边按实例行归属；sidecar edges 读取 + relevance 默认 |
| B3 | `src/memoria/graph/edge_types.py:29-54` | 3 类型 + 默认 relevance 0.9/0.7/0.6；`contain` 只能派生 |
| B4 | `src/memoria/graph/link_audit.py:24-30` | 现有自查只有结构问题（缺 sidecar/缺实例/实例越界/目标未解析/virtual） |
| B5 | `src/memoria/services/document.py:2154-2205` | `validate_kb` 汇总上述结构检查；**无语义/效用检查** |
| B6 | `docs/design/kg-ontology-v0.md:16-56,87-101,137-157,161-177,190-198` | 概念模型 link/edge；语料三元组规则；节点字段现状；新类型准入三闸；未知 U-1/U-2 |
| B7 | `docs/design/kg-visualization-v0.md:204-221,244-278,283-298` | 埋点只采 nodeRadius/graphStyle；build 副作用（404→454）；验收可测项 |
| B8 | 本文 §3 表（`G1-baseline.json`） | 357/62、类型分布、字段缺失、连通性、description 0% |

### 6.3 C 源（优秀开源；许可与路径来自本仓 `E1-memory.md`，HEAD 2026-10-27）

| # | 项目 | 与本议题相关的字段/机制 | 许可 | 本文件用途 |
|---|---|---|---|---|
| C1 | **Graphiti / Zep** `getzep/graphiti` | `EntityEdge`：`fact`（自然语言事实）、`episodes[]`（溯源）、`valid_at/invalid_at/expired_at`（双时态）；`EntityNode.summary` | **Apache-2.0** | 边=一句可判事实 + 溯源 + 时间：**L2×S/G/T 的直接参照**；也提示 L3 的"复述"可对照 `fact` |
| C2 | **A-MEM** `WujiangXu/A-mem-sys` | `MemoryNote{content,id,keywords,links,retrieval_count,context,evolution_history,category,tags}`；召回时把 `links` 邻居拼入上下文 | **MIT** | "links 图扩展用于检索"= L3×U 的现成弱模式；但没有边类型/真值 |
| C3 | **Mem0** `mem0ai/mem0` | 记忆 `data + hash(md5)`；LLM 输出 ADD/UPDATE/DELETE/NONE；history 保留 old/new/event | **Apache-2.0** | 时间/失效语义（T）与"冲突判定靠 LLM"（GUE 不做 LLM 真值） |
| C4 | **mcp-memory-service** `doobidoo/mcp-memory-service` | `contradicts` 图边 + `mark_superseded_batch`；衰减/归档 | **Apache-2.0** | "边类型=矛盾"的工程先例（L2 的 T/U 组合） |
| C5 | **Basic Memory** `basicmachines-co/basic-memory` | `Relation{type,target,context}`；`Observation` 时间限定符（`@valid_during`） | **AGPL-3.0（只读思路，不复制）** | `context` = 边可判性的最小字段先例 |
| C6 | **LlamaIndex** `run-llama/llama_index` | `NodeRelationship`（PARENT/CHILD/NEXT/PREV）；`start_char_idx/end_char_idx`；metadata 自由 dict | **MIT** | 结构关系与字符偏移溯源（G）的参照；**无"可判性"字段**（E1-memory 结论 B） |

### 6.4 D 源（语料观测；**不作设计依据**）

| # | 来源 | 本文件用途 |
|---|---|---|
| D1 | 数字通信原理 frozen 快照（26 md / 11 sidecar） | 基线数字（§3）；只作"数据现实/迁移成本/测试集"，不用于证明"该如何设计" |
| D2 | `kg-retrieval/data/sessions.json`（2 个会话文件 / 20 个问题）、`real-usage.json`（5 库） | L4b 任务集/问题集的**候选来源**（D：测试用，不作设计依据；且需重放验证） |
| D3 | 语料本身是"未维护的教材库"（人已定调） | 只作最坏输入样本 |

---

## 7. 诚实清单：哪些层现在完全没测法、哪些能立刻测

### 7.1 完全没测法（现在做不了，别假装能做）

| # | 项 | 为什么做不了 | 前置 |
|---|---|---|---|
| 1 | **L2 边效用的统计级消融** | 无任务集/gold；62 边统计功效极低（单边效应不可检） | G6 harness + G2 任务集 |
| 2 | **L3 路径语义真值（代表性）** | 无路径来源口径、无组合表、无 gold 链；当前 79/357 覆盖、最大块 25 节点 | G4 + G5（provenance）+ CQ 集 |
| 3 | **L3 溯源** | graph edge 无 `instances/fact/出处`（§3）；无法把路径跳回原文 | G5 数据模型补 `provenance/instances` |
| 4 | **L4b agent 任务效用** | 无固定任务集/qrels/AB harness | G6 |
| 5 | **L4c 人本效用** | 无用户研究协议/被试；"人"未定义 | 人确认 + 协议 |
| 6 | **全层 ×T（时间）** | 数据模型无 `valid_from/valid_to/superseded_by`；记忆时间语义无数据 | G5 |
| 7 | **全层 ×C（成本）** | 无 harness、无预算基准；成本只有口径（token/延迟/认知）没有基线 | G6 |
| 8 | **L2-4 约束/规则** | 62 边、3 类型且无谓词定义 ⇒ 规则挖掘无统计基础 | G5 + 更多数据 |

### 7.2 能立刻测（G1 之后即可开，成本已估）

| # | 项 | 产物 | 成本（经验估计） |
|---|---|---|---|
| 1 | L1-1 结构静态 | 指标表（可脚本） | 0.5 人日 |
| 2 | L2-0 结构前置闸 | `validate_kb` 报告 | 0.2 人日 |
| 3 | L2-1 类型可表述性 | 3 个类型定义 + 正反例 | 0.5 人日 + 评审 |
| 4 | **L2-2 人判矩阵（62 边）** | 标注表 + α/κ + 保留率 | **3 人 × 2–3h**（≈1 人日/人） |
| 5 | L4a CQ 清单 + 覆盖矩阵 | CQ 表 + 字段×CQ 矩阵 | 1–2 人日 |
| 6 | L1-2 节点人判（抽样 40–60） | 标注表 + α | 3 人 × 1.5h |
| 7 | M1/M2 夹具 | known-good/known-bad 集（10 条边+5 条链路） | 0.5 人日 |

### 7.3 能"半测"（有数据但不足以作结论）

- **L3 案例研究**：在最大连通块（25 节点）里枚举长度 2–3 的路径，做 10–15 条人判——**只能当 pilot/夹具**，不能当"链路语义合格率"。
- **L2 派生边正确性**：contain 33 条可机检"父子关系是否与标题层级一致"（结构正确性），但这不是"语义有用性"。

---

## 8. 后续议题依赖（G1 只排序，不执行）

```
G2 基线（图结构 + 语义标注 + 任务性能）
   ├─ 必须先定：语料三元组 + build 状态（§3 陷阱 1/2）
   ├─ 语义标注基线 = 边的类型定义/谓词/方向/来源 + provenance（不是再数一遍边）
   └─ 任务性能基线 = 问题集 + gold answers 草案（可借 D2，但需重放验证）

G3 边级（L2×S/U）  ← 依赖 G2 的标注基线 + 人判矩阵
G4 链路级（L3×S/G） ← 依赖 G3（边有效）+ G5（provenance）+ 路径来源口径
G5 数据模型（L4a） ← 可与 G3/G4 并行；输出 E1 字段落地（时间/类型/来源/版本/可验）
G6 图谱任务 A/B（L4b×U/C） ← 依赖 G2 任务集 + G5 数据模型；这是唯一能回答"辅助检索是否有效"的
```

**给 Lead 的建议顺序**：G2 里先把 **L2 人判矩阵 + 类型定义** 做掉（这是唯一能立刻给人"边到底有没有语义"答案的动作），
同时并行 G4a（路径来源口径裁定）与 G5（provenance/时间字段）；**不要在 G2 之前承诺 L3 结论**。

---

## 9. 风险与测量纪律（GUE 自身的"不翻车"条件）

1. **语料身份**：每次测量带 `(HEAD, manifest_sha256, 时刻) + 测量源 + build 状态`（B：`kg-ontology-v0.md:87-101`）。
   本文件基线 = 数字通信原理 frozen / collect_graph_data / pre_build。
2. **不跨语料比**：docs/example（134/404）与数字通信原理（357/62）是两套世界；"100% reference"等结论不可移植（§3 陷阱 1）。
3. **不跨 build 比**：build 前 404 → 后 454 边（B：`kg-visualization-v0.md:273-278`）。
4. **同 commit 双跑**：同一脚本同参数连跑 2 次，除时间戳外逐字节一致（本文件 `G1-baseline.py` 已验证 deterministic=True）。
5. **假通过防御**：所有"全部为 0/全部一致"先构造必须失败用例（R6）；例如"0% description"要验证脚本确实读了字段。
6. **不拿长度当质量**（R5）；不拿覆盖率当设计依据（R4）。
7. **人判伦理**：标注者知情同意、盲化、可撤回；用户研究需另走协议。
8. **LLM 判官不得直接当真值**：必须与人类 gold 子集校准（M3）。

---

## 10. 开放问题（给 Lead/人裁；G1 只登记，不拍板）

| # | 问题 | 建议/选项 |
|---|---|---|
| U1 | `GUE` 名称与范围是否接受？（"不是新学科"的表述是否可对人这么讲） | 建议接受"交叉领域"表述；名称可保留 GUE |
| U2 | **L4 拆成 L4a/L4b/L4c 是否接受**？ | 建议接受（否则"模型能否支撑"无法落到可测） |
| U3 | **L3 路径候选来源**：(a) 现有图路径（少而局部）/ (b) 正文独立生成（研究）/ (c) 等图扩充 | 建议 (a)+(b) 双轨，报告分开；不要混成一个"链路语义率" |
| U4 | **"人"指谁**：终端用户 / 开发者 / agent 使用者？ | 建议先定"agent 任务效用"（L4b）为主，"人"（L4c）后置 |
| U5 | **人判预算**：L2 62 边 × 3 人 ≈ 1 人日/人，是否安排？ | 这是最快能回答"边有没有语义"的动作 |
| U6 | 62 边时代是否接受"GUE 只做案例研究+框架，不发布比率型结论"？ | 建议接受；比率需扩大语料后再发布 |
| U7 | 时间/溯源字段（G5）是否先于 L3 结论？ | 建议是；否则 L3 不可核 |

---

## 11. 证据身份与复跑

```text
本文件基线产物   artifacts/agent/verify/debate/graph-utility/G1-baseline.json
                 内容哈希（去掉 generated_at 后）sha256 = bfdd85ab64d9fd20142002c33c995e06c75f5bc48d4999060325575fd4cdab3e
复跑脚本         artifacts/agent/verify/debate/graph-utility/scripts/G1-baseline.py
运行（cwd = graph-utility 目录）  python scripts/G1-baseline.py   （系统 Python 3.12，需 PyYAML；只读 frozen 副本）
确定性           同命令连跑 2 次，除 generated_at 外逐字节一致（已验 deterministic=True）
输入              round2/frozen/数字通信原理（MANIFEST sha256 a4beaedc…，37 文件）
测量源            memoria.graph.collector.collect_graph_data() 于临时副本（无 .memoria/build）
关键输出          357 nodes / 62 edges；contain 33 / extend 21 / reference 8；
                  covered 79（22.1%）/ isolated 278 / components 296 / largest 25；avg_degree 0.347；
                  range_ok 352/357（98.6%）；description 非空 0；
                  边无 fact/valid_at/confidence/provenance/instances
本文件            未 commit；未改产品代码；未写 docs/design；未触碰活动库
```

> **一句话给 Lead**：框架**对象层覆盖成立**，但必须矩阵化（层级只是"单元"，语义/效用/溯源/时间/成本是"属性"）；
> L3 三候选必要不充分，且**当前 62 边做不了代表性 L3**；能立刻给人答案的是 **L2 62 条边的人判矩阵 + 类型定义**。
