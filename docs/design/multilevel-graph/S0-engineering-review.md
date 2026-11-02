# S0 术语的可工程化校核（SE 专家，v0）

> **性质**：S0 议项（S0-1..S0-12）的**工程可行性校核**，不是 S0 冻结稿，不改写 S0 章程与提案 A/B。
> **依据（只读）**：`docs/design/multilevel-graph-vision.md`（U-1..U-35，最高效力）；
> `docs/design/multilevel-graph-seminar-agenda.md` V0.2；`docs/design/multilevel-graph/S0-charter.md`；
> 现有契约 `docs/design/kg-ontology-v0.md`（v0.3）、`docs/design/kg-edge-provenance.schema.json`；
> 现有实现（只读）`src/memoria/graph/**`、`src/memoria/ui/static/app/js/graph-*.js`、`app.js`、`nav-stack.js`。
> **作者 / 角色**：`graph-se-architect`（domain=se，group=multilevel-graph）；U-35 指派的软件工程专家首份交付。
> **日期**：2026-11-02（Asia/Shanghai）。
> **写域声明**：本文件与 `ENGINEERING-PLAN.md` 为本人唯二写入；**未**修改 S0 提案 A/B、未改契约、未写产品代码、未 commit。
> **证据分级**：A = 契约/代码 file:line 或已冻结文档；B = 本仓可复跑；C = 单源研究结论；H = 本项目假设（无来源，需裁决）。
> **版本注记（2026-11-02T17:1x，S0-RULINGS 后）**：本文为 **S0 裁决前**的校核 v0，保留原始判定与证据链；裁决后的冻结前机检见 `S0-freeze-check.md`。术语已按 `S0-RULINGS.md` 对齐：`presence ∈ {shown, suppressed, unknown}`（本文早期草稿曾写 `present`，以 `shown` 为准）；`ctx` 增加 `view_family`；D-1..D-5 的处置见 `ENGINEERING-PLAN.md §1.6/§1.7`。

---

## 0. 校核方法（可复现）

对每个 S0 议项问四个工程问题（任一答不上 ⇒ 该项不能进入 S5a/S6a/S9a 施工）：

1. **落点**：能否落到「实体 / 关系 / 状态 / 数据流」四类制品之一？落不到就只能是口号。
2. **键**：这个概念的**身份键**是什么（主键 / 复合键 / 派生键）？没有键就无法去重、无法缓存、无法回滚。
3. **判据**：能否写成**可机检谓词**（输入 → 布尔/枚举 + 证据指针）？只能人判的要标注人工协议。
4. **出处**：数据从哪来、写到哪去、谁是事实源、谁是可再生缓存？（仓库硬规则：禁止并行事实源，`AGENTS.md` §1）

**术语约定**（本文件新增，供 S0 采纳/否决）：
- **视图上下文键** `ctx = (level, dimension, focus, hop_budget, edition)`：所有「同一对节点在不同层/维/上下文边存无不同」（U-27）必须用这个键表达。
- **三值存在性** `presence ∈ {shown, suppressed, unknown}`（S0-RULINGS 定名；本文草稿曾用 `present`，以 `shown` 为准）：`suppressed` = 有意不显示（有规则 id）；`unknown` = 未计算/数据未加载。**二者都不得写成「不存在」**。
- **语义承载度** `semantic_bearing ∈ {none, structural, asserted}`：显式对应现有 `contain_kind`/`provenance_state`（`kg-ontology-v0.md` §2.2/§2.3），避免新造一套语义词。

---

## 1. 结论先行

### 1.1 判定统计

| 判定 | 议项 | 含义 |
|---|---|---|
| **可工程化** | S0-4、S0-7、S0-8、S0-9、S0-11、S0-12（有条件） | 可直接映射为实体/状态/机检项；照本文修复建议写入术语表即可 |
| **需澄清** | S0-1、S0-2、S0-3、S0-5、S0-10 | 概念方向正确，但**键/判据/边界**缺失，现在写进术语表会导致两种都「合规」的实现 |
| **不可接受** | **S0-6**（以当前措辞） | 「边存在/不存在本身是语义」在现有数据模型里**没有承载字段**，且缺判据；照现在的话写，实现必然退化成「数据里有边就画 / 没有就不画」，正好是 U-16/U-17 要禁的旧行为 |

> **口径说明（2026-11-02 补，见 §9）**：本条「不可接受」针对 **S0 章程的原始措辞**；提案 A/B 已分别提出 `RenderContext`/视图边状态枚举的修补（A §6、B §6）。因此该判定对冻结稿的实际要求是：**必须写死 ①视图上下文键；②三值存在性（含 unknown）；③缺席原因字段**，否则仍不可接受。

### 1.2 五个阻塞项（必须在 S0 冻结前裁决，否则 S4/S6 会返工）

1. **S0-6 的「存无」需要一个视图上下文键 `ctx` 与三值 `presence`**（证据：`collector.py:46-99` 输出的边条目无 level/dimension/context 字段；前端 `graph-view-2d.js:634-663` 对 `engine.links` **无条件全画**）。
2. **KP 身份必须拆成「概念 KP」与「出现位置 KP occurrence」两层**（证据：`kp_index.py:37-73` 按 `by_id` 聚出**一对多**；`collector.py:57-72` 只保留一个 `preferred` 节点并把 `file` 写成单值 ⇒ U-21「一个知识点可能在多个子图」在多文件/多锚点时**必然丢信息**）。
3. **「簇」不能沿用现有 group**：现有 `computeGraphGroups` 是**严格连通分量的单值分区**（`graph-groups.js:83-134`，`nodeToGroup` 单值），与 U-13「不是严格连通子图」和 U-21/U-31「多归属」直接冲突。
4. **边存在性只能作为「事实 × 视图上下文」的**投影函数**，不得落成第二事实源；因此 S6 的 ER 必须区分「语义边候选（事实）」与「本次渲染的边（视图产物）」（证据：`edge_derivation.py:630-669` 的 dedupe 键 `(type, source, target, no_build)` 不含 ctx；`kg-ontology-v0.md` §5.1 明确禁止把缓存当事实源）。
5. **「语义」必须给可机检判据**，否则 S0-1 无法验收；本仓已有可复用的机检先例：`assertion_source` + `quote_sha256` 与正文切片比对（`edge_derivation.py:812-859`，schema `kg-edge-provenance.schema.json:202-241`）。

---

## 2. 逐项校核（S0-1 .. S0-12）

> 格式：**判定** → 落点 → 歧义/实现风险 → 修复建议（可直接抄进术语表/判据）→ 证据。
> 「修复建议」写成**判据或契约条款**；标注 `[机检]` 的条目可由脚本判定，`[人工协议]` 的必须写抽检流程。

### S0-1 「语义」——**需澄清**

- **上游**：U-1「图谱最重要的是语义」；S0-1 要求「用什么判据说这条边有语义/没有」。
- **落点**：可落到「关系 + 属性」，但必须先定义**谓词**，不能停留在「有意义」。
  - 图语境的「语义」实际是两层：① **边的语义承载**（这条边是否断言了某种关系）；② **边/链路的可用性**（这条边对用户/agent 是否有帮助）。二者不可混为一谈：①是**本体/证据问题**，②是**评价问题**（GUE 板块 task-203 的 L2/L3）。本 S0 只能钉①，「有没有帮助」应显式移交评价板块，否则 S0 永远无法冻结。
- **歧义 / 风险**：
  - 若「语义」= 人的主观判断 ⇒ 不可机检，且不同实现者会对同一语料给出不同选边结果；
  - 若「语义」= 有类型字段 ⇒ 现有类型空间 100% 退化为 `reference`（`kg-ontology-v0.md:23-26`），等于「全都有语义」，判据失效。
- **修复建议**（可抄）：
  ```
  定义 语义承载度（semantic bearing）为三值枚举，由证据推导而非由类型名推导：
    none        ：无证据表明作者/agent 断言过关系（structural 派生、无锚点纯边、missing）
    structural  ：仅结构事实（B 的区间在 A 的区间内）；不承诺整体-部分语义
    asserted    ：存在可核验断言证据（assertion_source.file/line_start/line_end
                  且 quote_sha256 与正文切片一致）
  判据 [机检]：asserted(e) ⇔ e.provenance_state=="asserted" ∧ validate(assertion_source) 通过
              （复用 edge_derivation.validate_contain_curation_overlay 的同一算法）
  判据 [人工协议]：链路级「有意义」判定移交 GUE（消融实验或多人独立判定 + 一致性系数），
                  S0 只声明接口（链路 → 证据指针），不在此定义阈值。
  ```
- **证据**：`kg-ontology-v0.md:23-26`（agent 不读边、类型无信息量）；`kg-ontology-v0.md:61-131`（provenance/contain_kind 语义三态）；`kg-edge-provenance.schema.json:202-241`（semantic 强制 assertion_source/curated_by/curated_at）；`src/memoria/graph/edge_derivation.py:812-859`（quote_sha256 机检实现）。

### S0-2 层次与最小粒度——**需澄清**（最小粒度部分可工程化）

- **上游**：U-5（节点不再是最小粒度）、U-8（层次维度）、U-28（最小节点粒度=知识点毋庸置疑）。
- **落点**：层次 = **视图坐标（状态）** + 层次-成员映射（关系）；「最小粒度」= **聚合树叶子约束**（实体约束）。
- **歧义 / 风险**：
  - 「层次」若被理解为**数据层级**（文档/章节/段落）与**聚合层级**（簇→子簇→KP）二义，会产出两套互相打架的层级字段；
  - 「更深层（句/概念）」不定，但若不在 S0 钉死「层次是否只增不减、是否允许 KP 之上再聚合」，S6 的 ER 无法定主键。
- **修复建议**（可抄）：
  ```
  定义：level 是【视图粒度坐标】，有序（整数 depth，0=最粗，越大越细），不是文档结构也不是 KP 包含关系。
  聚合：node(kind ∈ {cluster, kp})；cluster 的成员只能是 kp 或更低 depth 的 cluster。
  最小粒度约束 [机检]：max depth 层的节点集合必须满足
      ① 全部 kind == "kp"；② 节点 id 集合 == 该 KB 的 KP id 全集；③ 不存在 kind=="cluster" 的叶子。
  深层问题（句/断言/概念）[待 S1/S10 裁决]：若引入，必须新增 level 而不是把 kp 节点替换成更小粒度，
      且 kp 层仍须满足上述三条（U-28）。
  ```
- **证据**：`collector.py:57-72`（当前节点=KP，无 cluster）；`graph-groups.js:83-134`（当前「分组」只是筛选，不是层次）。

### S0-3 维度——**需澄清**

- **上游**：U-9/U-10/U-12/U-25（维度 + 开放槽位）、U-30（关联维度要具体定义）。
- **落点**：维度 = **注册表实体 + 视图坐标**；「开放槽位」= 注册表里的 `status` 枚举（必须是数据，不能只是文档里一句话）。
- **歧义 / 风险**：
  - **「层次维度」与「维度」并列的措辞自相矛盾**：如果 level 也是 dimension，那 `ctx=(level,dimension)` 就重复；如果不是，则 S0 必须写清「level 是主轴，dimension 是可选副轴，组合方式 = (level, dimension)」。
  - 最大实现歧义：现状 `graphStyle`（`force` / `galaxy`）是**视觉风格**，不是维度。若 S0 不显式排除，后续极可能把「银河/力导向」当成维度实现（U-33 警告的同类错误）。
  - 「开放槽位」若只写「预留」，实现会静默忽略未知维度 ⇒ 持久化的 `dimension_id` 失效后 UI 无提示（U-25 的「不会被误实现」）。
- **修复建议**（可抄）：
  ```
  定义：dimension 是【在同一 level 下改变取景规则的可选坐标】，每个已注册维度必须声明五元组：
        {dimension_id, status: active|slot|deprecated, edge_sources[], hop_policy, admission_rules[], version}
  层次：level 是必选主轴，dimension 是可选副轴；视图上下文键 = (level, dimension)。
  开放槽位 [机检]：任何被持久化/引用的 dimension_id 必须在注册表中存在；
        不存在 ⇒ 启动时回退默认维度并在 UI 显示可见提示（禁止静默忽略）。
  排除项（写死）[机检]：graphStyle/force/galaxy、2D/3D、主题色 不是 dimension（U-33）。
  ```
- **证据**：`graph-view-2d.js:617`（`graphStyle === "galaxy"` 是视觉分支）；`app.js:141`（持久化的是 group 选择，无维度概念）。

### S0-4 簇 / 代表连通子图——**可工程化**

- **上游**：U-6、U-13、U-14；S2 负责算法。
- **落点**：`Cluster`（集合）+ `ClusterNode`（渲染表现，1:1 于某 revision 的 cluster）+ `Membership`（多对多）。
- **歧义 / 风险**：定义里「内聚高 + 零星桥」是**质量判据**，不是身份键；若不强制「算法 + 参数 + 版本 + 语料身份」四要素，簇结果不可复算，缓存永远无法判定 stale。
- **修复建议**（可抄）：
  ```
  Cluster = (cluster_id, algorithm_id, algorithm_version, params_hash, corpus_manifest_sha,
             cohesion_metric, bridge_metric, generated_at, state: candidate|curated|stale)
  内聚/桥判据的【阈值】归 S2；S0 只要求「阈值必须作为参数被记录并可复算」。
  ClusterNode 不是实体数据，而是 Cluster 在当前 drawing 下的表现（见 S6a ER）。
  [机检] 同一 corpus_manifest_sha + algorithm_id + version + params_hash ⇒ cluster 结果必须字节级可复现。
  ```
- **证据**：`graph-groups.js:83-134`（现有 group 可复算但无版本/语料键）；`kg-ontology-v0.md:162-177`（语料身份三元组强制格式，可直接复用）。

### S0-5 一跳挂接——**需澄清**

- **上游**：U-15、U-11、U-18；S4 负责跳数策略。
- **落点**：状态机里的**取景参数** + 边集合的**派生规则**（不是存储）。
- **歧义 / 风险**（三种都会产出不同实现）：
  1. 沿**哪些边**算一跳（全部候选边？仅 admitted 边？跨维度边？聚合前还是聚合后？）；
  2. 聚合节点是否「折叠」掉中间跳（A→KP→B 在簇视图里可能只显示为 1 跳）；
  3. 一跳节点是否允许继续展开（U-22 权衡）——这属于导航状态，不属于跳数定义。
- **修复建议**（可抄）：
  ```
  一跳 = 渲染图上的一次相邻关系（rendered-graph hop），定义域是本次 admitted 边集；
  hop_budget ∈ {0,1,2,...}；挂接集合 H1(focus) = {n | dist_rendered(n, focus) == 1} \ base_set。
  聚合折叠：若 n 是 cluster，其内部路径不计跳；同时记录 underlying_hop_count 供审计（U-17 防污染）。
  跨维度：默认不算一跳（跨维度 = 显式切换 dimension，产生新 ctx）；若 S1 允许，必须作为独立事件
        并带 cross_dimension=true，不得与同维度一跳混算。
  终止条件：hop_budget 用尽 或 下一跳节点全部属于 base_set 或 无 admitted 边。
  ```
- **证据**：`app.js:8383-8410`（现有 `externalFocus` 只高亮已存在边，不是挂接图外节点）；`graph-view-2d.js:634-663`（渲染域=全边，无 hop 概念）。

### S0-6 选择性渲染 + 边「存无/类型」——**不可接受（以当前措辞）**

- **上游**：U-16（旧版两端都渲染；新设计选择性渲染）、U-17（一跳背后图**不一定**语义上与本图有关系）、U-27（边有「存无」「类型」不同）、U-26（默认彻底替代 + 保留全展开开关）。
- **落点**：必须是 **派生投影**（数据流 + 派生函数），不能是实体；但投影需要**键**和**值域**，当前契约两者都没有。
- **为什么不可接受**：
  1. 现有契约的边条目身份键是 `(type, source_id, target[, no_build])`（`edge_derivation.py:630-669`；`canonical_edge_id = type|source|target`，`:787-793`），**没有 level/dimension/context**；因此「同一对节点在不同情况下边存无不同」在数据上无法表达。
  2. 前端唯一规则是「`engine.links` 有就画」（`graph-view-2d.js:634-663`），取消边就等于「无声断言不存在」——而「不存在」有三种完全不同的原因（规则抑制 / 没有事实 / 未计算），当前没有任何字段区分。
  3. 若把「存无」落成 sidecar 里的一个布尔字段，等于把**视图产物**写进**事实源** ⇒ 违反单一事实源（`AGENTS.md` §1）且无法随视图上下文变化。
- **修复建议**（可抄，S6/S4 必须采纳其一）：
  ```
  事实层（可持久化）：EdgeCandidate = {edge_id, type, source_id, target_id, provenance, contain_kind, ...}
  视图层（不持久化为事实）：Admission(ctx, EdgeCandidate) -> 
      {presence: present | suppressed | unknown, rule_id, effective_type, hop, reason}
  三值语义写死：
      present    = 本次 admitted，必须渲染
      suppressed = 候选存在但被规则有意不显示（必须带 rule_id，例如 hop_budget、cross_cluster_policy）
      unknown    = 候选未计算/数据未加载（禁止渲染、禁止在 UI 上下文中被解读为「没有关系」）
  [机检] 渲染集合恒等于 {e | presence(e)==present}；被 suppressed 的候选必须能列出 rule_id；
         不允许出现「不在候选集合中也没有 unknown 原因」的边（否则就是静默丢边）。
  effective_type：类型差异也随 ctx 变化 ⇒ 必须落在视图层，不得回写事实层 edge.type。
  ```
- **证据**：`collector.py:46-99`（边条目无 ctx 字段）；`edge_derivation.py:630-669,787-793`（边身份键）；`graph-view-2d.js:634-663`（全量渲染）；`app.js:1842-1866`（前端只消费 `get_graph_data` 一个 payload）。

### S0-7 多归属——**可工程化**（但要求先定义 membership 实体）

- **上游**：U-21、U-31；S2/S6 决定上限与规则。
- **落点**：`Membership(kp_id, cluster_id, level, dimension?, role, weight, source)` —— 关系实体，**多对多**。
- **歧义 / 风险**：把「属于」混同于「本次视图出现」（appearance）。多归属是**事实/派生关系**；出现是**视图投影**。若混同，返回导航、去重、缓存失效都会错。
- **修复建议**（可抄）：
  ```
  「属于」= membership 关系，可多值（不设上限，U-31）；「出现」= 视图投影，由 ctx 决定。
  Membership 必须带 source ∈ {derived_cluster, curated_overlay, agent_proposal} 与 audit 字段。
  [机检] 禁止对 (kp_id, cluster_id, level?) 施加唯一约束；同一 kp 在同一 level 允许属于多个 cluster。
  现有冲突必须显式列出：nodeToGroup 是 Map<id, groupId> 单值（graph-groups.js:123-126）⇒ S6 迁移必须废弃。
  ```
- **证据**：`graph-groups.js:123-126`（单值归属）；`collector.py:61-72`（节点 `file` 单值 = 只保留 preferred occurrence）。

### S0-8 默认视图 vs 全展开——**可工程化**

- **上游**：U-26；S3/S4/S5。
- **落点**：两条**同源**渲染路径 + 一个持久化开关；不是两套数据源。
- **歧义 / 风险**：若全展开走 `build_kb` 的 454 边路径而默认走 `collect_graph_data` 的 404 边路径，两视图会「看不同世界」——本仓已有该架构缺陷记录（`kg-ontology-v0.md:179-202`）。
- **修复建议**（可抄）：
  ```
  默认视图与全展开共用同一个 EdgeCandidate 事实集（同一 KB 快照、同一 collector 路径）；
  全展开 = 关闭 aggregation + 令 Admission 对所有候选返回 present（type 保真）。
  [机检] 设全展开集合 E_full、默认集合 E_def：必须满足
        E_def ⊆ E_full；且 E_full == 候选全集（按 ctx 中 level=leaf, dimension=all 计算）；
        并断言两者来自同一 corpus_manifest_sha。
  迁移：现有持久化 `-graph-group`（app.js:141）在新默认视图下语义失效 ⇒ S5 决策「重置为 all + 提示」。
  ```
- **证据**：`graph-view-2d.js:634-663`（当前默认即全展开）；`kg-ontology-v0.md:179-202`（两条后端路径 404/454 缺陷）。

### S0-9 渲染接口边界——**可工程化**

- **上游**：U-33（2D/3D 只是带接口的渲染板块）、U-4（单一契约）。
- **落点**：`ViewModel`（输入 schema）+ `RenderBackend`（实现接口）+ `ViewEvent`（回传）。
- **歧义 / 风险**：若接口把「取景/选边」放进渲染后端，2D 与 3D 会各自实现一遍语义 ⇒ U-33 说的「严重误解」重演。必须写死：**渲染后端不懂语义，只懂 ViewModel**。
- **修复建议**（可抄）：
  ```
  分层：Retrieval/Framing(S9) → Admission(S4) → ViewModel(S6/S3) → RenderBackend(2D|3D)
  渲染后端能力声明（precedent）：复用 docs/design/view-surface-contract.md §4 双插头协议
        register/current/switchTo + capabilities + onDegraded + 失败回滚；禁止后端各自读 engine。
  ViewModel 最小字段（S6a 冻结）：
        view {level, dimension, focus, breadcrumb[], hop_budget, edition_sha}
        nodes [{node_id, kind: kp|cluster, label, metrics, badges, member_count?}]
        edges [{edge_id, presence, type, rule_id, hop, style_class}]
        omitted [{edge_id, presence: suppressed|unknown, reason}]
  [机检] 同一 ViewModel 输入给 2D/3D ⇒ 两者渲染的节点/边 id 集合必须一致（U-33 验收）。
  ```
- **证据**：`docs/design/view-surface-contract.md:173-214`（本仓已有双插头 + capabilities + 回滚先例）；`app.js:1643-1660`（当前 2D/3D 各自持 engine/layout，无统一 ViewModel）。

### S0-10 agent 的角色边界——**需澄清**

- **上游**：U-29（agent 怎么设计知识点）、U-10/U-30（关联维度）、U-2（后端给 agent 增效）。
- **落点**：权限/接口层（可写成 allowlist），不是名词定义。
- **歧义 / 风险**：agent 现在**不读边**（`kg-ontology-v0.md:23-26`），但**可写 semantic curation**（`kg-ontology-v0.md:126` 规则 1）。若不把「设计 KP」「决定语义」「决定取景」三类能力分接口，agent 可能被实现成「写视图缓存」⇒ 形成第二事实源，且无法回滚。
- **修复建议**（可抄）：
  ```
  三类能力分开授权 [机检：接口 allowlist]：
    ① 设计 KP（写）：只能经 propose_write / curate 类接口写 sidecar，必须带 curated_by/curated_at（schema 先例）；
    ② 决定语义（写）：只能写 EdgeCandidate 的 provenance/contain_kind，必须带 assertion_source；
    ③ 决定取景（读）：agent 只能【读】framing API，不得写视图状态/缓存；缓存由系统按版本键重建。
  [机检] agent 接口集合中不存在「写 view state / 写 cluster revision」的接口。
  细谈移交 S9/S10；S0 只需钉死上述三分法。
  ```
- **证据**：`kg-ontology-v0.md:23-26`（agent 零读取边）；`kg-ontology-v0.md:126`（agent 可落库 semantic contain，`curated_by=agent:<session>`）；`kg-edge-provenance.schema.json:144-151`（审计身份字段）。

### S0-11 不做什么——**可工程化**（前提：改写成机检 denylist）

- **上游**：章程 S0-11；U-23/U-28。
- **问题**：当前表述「自动改写用户正文？跨库图？时间轴？词级节点？」是**疑问句/示例**，不是可执行边界；S8 前没有东西能拦住「顺手做了半个」。
- **修复建议**（可抄）：
  ```
  v1 明确不做（每条必须绑定执行点，才可机检）：
  ① 不自动改写用户正文  → 执行点：新增代码不得调用正文写回（本仓已有反例：kb_build 的
     strip_known_wikilink_edge_hints 会写回正文，见 kg-ontology-v0.md:195-202；本板块不得扩大该行为）
  ② 不跨库图            → 执行点：ER 不含 kb_id 外键；DFD 只有一个 KB 根
  ③ 不做时间轴/双时态    → 执行点：schema 不加 valid_from/valid_to 消费者（现有字段只存不用）
  ④ 不做词级/句级节点    → 执行点：S0-2 的叶子约束机检（所有叶子 kind==kp）
  ⑤ 不把 2D/3D 拆成两条设计线（U-33） → 执行点：S0-9 的 ViewModel 一致性机检
  [人工协议] 每条在 S0 冻结时写「若日后要做，需重开哪一场（Sx）+ 谁批」。
  ```
- **证据**：`kg-ontology-v0.md:150-158`（v0 不做清单的写法先例）；`kg-ontology-v0.md:195-202`（build 写回正文的既有残差）。

### S0-12 术语映射——**可工程化（有条件）**

- **上游**：章程 S0-12；vision §2 要求覆盖矩阵。
- **风险**：映射表若只写「新词 ↔ 旧词」而不写**兼容/迁移/回滚**（章程 §4 判据 3），冲突会拖到 S6 才爆。
- **修复建议**：见 §5 的工程草案；必须对 4 处硬冲突（簇/多归属/边存在/层次）写明迁移与回滚，且冲突处**不得静默合并**（章程 §4 判据 2）。
- **判定**：可工程化，但**当前映射未写 ⇒ 按章程 §4 判据 3 不得通过**。

---

## 3. 横向工程发现（E-1..E-10，跨议项，建议 Lead 逐条分派）

| # | 发现 | 证据（A 级） | 后果 | 建议归属 |
|---|---|---|---|---|
| **E-1** | 数据模型无视图上下文键；边身份 = `(type,source,target[,no_build])`，与 level/dimension/context 无关 | `edge_derivation.py:630-669`；`edge_derivation.py:787-793`；`collector.py:46-99` | U-27/U-16/U-15 无法表达；任何「存无」实现都会退化成全局布尔 | S0-6 + S6 |
| **E-2** | KP 概念与 KP 出现位置被合并：索引按 kp_id 一对多，节点只取 preferred 且 `file` 单值 | `kp_index.py:37-73`；`collector.py:57-72` | 多锚点/多文件 KP 的成员关系与跳转目标会丢；U-21 多归属首当其冲 | S0-2/S0-7 + S6a |
| **E-3** | 现有 group = 严格连通分量 + 单值分区 + 仅作筛选（非聚合节点） | `graph-groups.js:83-134`；`graph-groups.js:152-164`；`graph-layout-2d.js:219-257` | 与 U-13「非严格子图」、U-6「聚合节点」、U-21「多归属」三重冲突 | S2 + S6a |
| **E-4** | 边存在性是「事实」不是「视图函数」；缺失原因不可区分 | `graph-view-2d.js:634-663` | U-17「背后图不一定有关系」不可强制执行；UI 会把 unknown 当 absent | S0-6 + S4 + S6a |
| **E-5** | 导航有两套互不兼容的栈：文件导航栈（file/kpId/source）与图谱无栈；图点击直接跳编辑器 | `nav-stack.js:23-36`；`app.js:5928-5945`；`app.js:1661-1677` | U-7/U-21/U-22 的下钻/返回/「从哪来回哪去」无承载；需要独立 graph focus stack | S5a |
| **E-6** | 渲染后端无统一契约：2D/3D 各自持 engine/layout 并各自读数据 | `app.js:1643-1660`；`view-surface-contract.md:173-214`（已有双插头先例） | U-33 要求「同一接口两个实现」；应复用先例，不要新造 | S0-9 + S5a/S6a |
| **E-7** | 「语义」有可机检先例（assertion_source + quote_sha256 切片比对），但当前只用于 contain semantic overlay | `edge_derivation.py:812-859`；`kg-edge-provenance.schema.json:202-241` | S0-1 可不发明新判据，直接复用该证据闸门 | S0-1 + S6 |
| **E-8** | 事实源纪律：sidecar 是事实源；`.memoria/build/graph.json` 是缓存；cluster/level/dimension 结果只能是派生缓存或带审计的 overlay | `kg-ontology-v0.md:162-177`；`AGENTS.md` §1 | 否则新板块会造第二事实源，违反仓库硬规则 | S6 + S9a |
| **E-9** | 聚类的可复算三要素（算法/版本/参数）缺失；现有 group 无 corpus 键 | `graph-groups.js:83-134`；`kg-ontology-v0.md:162-177` | 缓存永远无法判定 stale；「簇漂移」无法审计 | S2 + S6a |
| **E-10** | 开放槽位无数据载体；未知 dimension 会被静默忽略 | `app.js:141`（持久化只有 group）；`graph-settings.js:127-138,193-212`（设置持久化无维度） | U-25 的「先留开放槽位」变成「预留 = 不实现」 | S0-3 + S1 |

---

## 4. S0 验收机检清单（建议写入 S0 预注册判据 §4）

> 原则：每条都能指向「一个文件/一个进程输出 + 布尔判定」，不依赖评审人记忆。

| # | 覆盖 | 判据 | 证据形态 |
|---|---|---|---|
| M-1 | S0-1 | 存在「语义承载度」三值定义，且 `asserted` 判据与 `validate_contain_curation_overlay` 同一算法 | 术语表条款 + 代码引用 |
| M-2 | S0-2 | 叶子约束三条（全 kp / id 全集 / 无 cluster 叶子）写成可执行断言 | 伪代码或测试用例集 |
| M-3 | S0-3 | 维度注册表含 status 枚举；未知 dimension_id 有 fail-closed 路径；graphStyle/2D/3D 被显式排除 | 注册表 schema + 一条反例 |
| M-4 | S0-4 | 簇定义包含 algorithm_id/version/params_hash/corpus_manifest_sha | 字段清单 |
| M-5 | S0-5 | 一跳 = rendered-graph hop，且聚合折叠有 underlying_hop_count；跨维度默认不计跳 | 定义 + 边界用例 ≥2 |
| M-6 | S0-6 | 三值 presence + rule_id 字段；渲染集合恒等式；`suppressed` 必须可枚举原因 | 契约条款 + 反例 |
| M-7 | S0-7 | membership 多对多；现有 nodeToGroup 单值被列为冲突并给迁移 | 冲突清单 + 迁移段 |
| M-8 | S0-8 | 默认/全展开同源断言（同 manifest、子集关系、全展开=候选全集） | 机检伪代码 |
| M-9 | S0-9 | ViewModel 最小字段集 + 2D/3D 同输入同 id 集合断言 | schema + 验收 |
| M-10 | S0-10 | agent 三类能力 allowlist；不存在写 view state 的 agent 接口 | 接口清单 |
| M-11 | S0-11 | 每条「不做」绑定执行点/文件/检查；无执行点的条目不得进入冻结 | denylist 表 |
| M-12 | S0-12 | 映射表冲突处 🔴 + 兼容/迁移/回滚三选一写明；覆盖矩阵 U 编号齐全 | 表 + 覆盖矩阵 |

**附加建议（对章程 §4 的补充）**：每个术语除「定义/反例/边界用例/U 映射」外，再加两项——
**(a) 存储位置**（事实源 / 派生缓存 / 仅视图状态，三选一；选派生须给版本键）；
**(b) 机检 id**（M-x）。这两项缺失的术语，S5a/S6a 无法施工。

---

## 5. 术语映射工程草案（S0-12 的输入，不是裁决）

> 冲突标记：🔴 = 与现有契约/实现直接冲突，必须写迁移；🟡 = 语义相近但不可混用；✅ = 可直接兼容。

| 新术语 | 现有产品术语 | 证据 | 冲突 | 兼容/迁移/回滚建议 |
|---|---|---|---|---|
| 层次 level | **无对应**（现有 group 页签不是层次） | `graph-groups.js:83-134`；`app.js:1560-1607` | 🔴 | 新增视图坐标字段，不动现有 group；全展开路径 level=leaf |
| 维度 dimension | **无对应**；`graphStyle` 是视觉风格不是维度 | `graph-view-2d.js:617` | 🟡 | 新增注册表；显式排除 graphStyle/2D/3D（U-33） |
| 簇 cluster | group（连通分量） | `graph-groups.js:83-134` | 🔴 | group 降级为「连通分量候选」输入；cluster 另建 revisioned 实体；旧 group 页签在默认视图下由 cluster 取代，保留开关 |
| 簇节点 / 代表子图节点 | **无对应**（group 只做筛选） | `graph-layout-2d.js:219-257` | 🔴 | 新增 node kind=cluster；渲染层按 kind 分支；旧 group 筛选保留为全展开开关下行为 |
| 一跳挂接 | `externalFocus`（仅高亮既有边） | `app.js:8383-8410` | 🟡 | 新字段 hop/rule_id；externalFocus 保留为「编辑器→图谱聚焦」另一功能 |
| 选择性渲染 | **无对应**（全量渲染） | `graph-view-2d.js:634-663` | 🔴 | 引入 admission 投影；默认视图启用，全展开关闭 |
| 边「存无/类型」差异 | `edges[].type` / `contain_kind` / `provenance_state` | `kg-ontology-v0.md:61-131`；schema `:20-151` | 🔴 | 事实层字段不变；新增视图层 `presence/effective_type/rule_id`；禁止把视图值回写 sidecar |
| 多归属 | `nodeToGroup` 单值 + node.file 单值 | `graph-groups.js:123-126`；`collector.py:61-72` | 🔴 | membership 多对多 + occurrence 两层身份（见 E-2）；旧单值字段废弃并给迁移 |
| KP | `knowledge_points[]` / kp_id / `KpIndexEntry` | `kp_index.py:18-73`；`collector.py:20-35` | ✅ | 定义不变；新增 occurrence 层，不动 kp_id 身份 |
| 边 edge / 链接 link | edge / link（已解耦契约） | `kg-ontology-v0.md:34-49` | ✅ | 沿用；只加视图层，不改概念 |
| 渲染接口 / 视图模型 | `GraphEngine.loadPayload` + `GraphView2D/3D` | `graph-engine.js:167-216`；`app.js:1643-1660` | 🟡 | 新 ViewModel 契约；旧 loadPayload 在全展开兼容路径下保留 |
| 默认视图 / 全展开开关 | 当前无开关（默认即全展开） | `graph-view-2d.js:634-663` | 🔴 | 新开关持久化（沿用 graph-settings 的 localStorage+disk 模式，`graph-settings.js:127-138,193-212`）；首次运行迁移为「默认视图」 |
| 审计 audit | `graph_audit`（链路审计）+ 交互计数器 | `document.py:2124-2132`；`app.js:26-101` | 🟡 | 新审计事件（簇/取景/存无决策）与现有 graph_audit 分表；不得混入同一报告口径 |
| agent 设计 KP | 现 KP 由正文/选区解析 + sidecar；agent 可写 curation | `kp_index.py:37-73`；`kg-ontology-v0.md:126` | 🟡 | S10 定义生成流程与审计；本板块只依赖「KP 存在生产方 + 审计字段」接口 |

---

## 6. 覆盖矩阵（U 编号 → 本文/图纸）

| U# | 本文覆盖 | 后续图纸 |
|---|---|---|
| U-1/U-2 | §2 S0-1；§3 E-7 | DFD（agent/用户双价值外部实体） |
| U-4/U-5/U-6/U-7/U-8 | §2 S0-2/S0-4 | ER（Cluster/ClusterNode/Level）、ST（下钻） |
| U-9/U-10/U-11/U-12 | §2 S0-3/S0-5 | ER（Dimension）、DFD（边源/跳数） |
| U-13/U-14 | §2 S0-4；§3 E-3 | ER（Cluster revision/cohesion/bridge） |
| U-15/U-16/U-17/U-18 | §2 S0-5/S0-6；§3 E-4 | DFD（Admission）、ST（挂接/不扩展） |
| U-19/U-20/U-21/U-22 | §2 S0-7；§3 E-2/E-5 | ER（Membership）、ST（从哪来回哪去） |
| U-25/U-26/U-27 | §2 S0-3/S0-6/S0-8 | ER（Dimension slot）、DFD（两条同源渲染路径） |
| U-28/U-29/U-30 | §2 S0-2/S0-10 | ER（leaf 约束）、DFD（agent API） |
| U-31/U-32/U-33 | §2 S0-7/S0-9；§3 E-6 | ER（多对多）、DFD（S9 取景）、ST（后端切换） |
| U-34/U-35 | §0/§4/§7 | 本文件 + ENGINEERING-PLAN.md 的冻结规则 |

**结论**：S0 相关 U 编号在本文件均有落点；**没有未覆盖项**，但 S0-6 与 S0-1 的判据若不定，§6 的「DFD（Admission）」无输入。

---

## 7. 待裁决与假设登记

| # | 待裁决 | 建议决策者/场次 | 不裁决的后果 |
|---|---|---|---|
| Q-1 | level 是否只增不减、是否允许 KP 之上多级聚合 | S1 | S6a ER 主键无法定稿 |
| Q-2 | dimension 与 level 的关系（主轴/副轴 vs 并列） | S0（Lead 裁决） | `ctx` 键重复或缺失 |
| Q-3 | 簇是「分区」还是「覆盖」（是否允许重叠） | S2 | ER 的 Membership 基数无法定 |
| Q-4 | 一跳是否按 rendered-graph 计、跨维度是否计跳 | S4 | ST/DFD 的 hop 字段无定义 |
| Q-5 | suppressed / unknown 是否要进 UI 提示 | S3/S4 | 用户会把「未计算」当「不存在」 |
| Q-6 | 全展开开关的持久化迁移（旧 `-graph-group`） | S5 | 老用户打开图谱后看到空图/错图 |
| Q-7 | 聚类结果落缓存还是事实源（含 curation overlay） | S6 | 违反单一事实源或无法审计 |
| Q-8 | agent 是否可读 framing API（读权限范围） | S7/S9 | agent 侧价值无法验证（U-2） |

**本项目假设（H，无来源，需裁决）**：
- H-1：S6a 会采纳「EdgeCandidate + Admissibility 投影」两层模型（本文 E-1/E-4 结论）；若否，S0-6 需重开。
- H-2：S2 的簇算法会提供版本化参数；若否，S0-4 的机检无法成立。
- H-3：S5 会引入独立 graph focus stack（不沿用 `MemoriaNavStack` 单栈）；若否，U-21/U-22 无法满足。

---

## 8. 证据索引（A 级，file:line）

```
docs/design/multilevel-graph-vision.md:16-41,60-84         U 编号与解读约束
docs/design/multilevel-graph-seminar-agenda.md:92-120      S5a/S6a/S9a 工程图归口
docs/design/multilevel-graph/S0-charter.md:24-37           S0-1..S0-12
docs/design/kg-ontology-v0.md:23-26,34-49,61-131,126       agent 不读边 / link-edge / provenance / agent 可写 curation
docs/design/kg-ontology-v0.md:150-202                      v0 不做清单 / 语料身份 / 404-vs-454 / build 写回正文残差
docs/design/kg-edge-provenance.schema.json:20-151,202-241  边字段 / 三态 / semantic 强制证据
docs/design/view-surface-contract.md:173-214               双插头协议（渲染后端契约先例）
src/memoria/services/kp_index.py:18-73                     KP 索引一对多
src/memoria/graph/collector.py:20-99                       KP 元数据 / 节点 / 边收集 / 无 ctx 字段
src/memoria/graph/edge_derivation.py:630-669,675-717       dedupe 键 / sidecar 边
src/memoria/graph/edge_derivation.py:787-793,812-859       canonical id / assertion_source 机检
src/memoria/services/document.py:2124-2132                 get_graph_data + graph_audit
src/memoria/ui/static/app/js/graph-engine.js:88-104,167-216  links 展开 / loadPayload
src/memoria/ui/static/app/js/graph-groups.js:83-134,152-164  连通分量 / 单值归属 / 群筛选
src/memoria/ui/static/app/js/graph-layout-2d.js:219-257     loadFromEngine（含 group 筛选）
src/memoria/ui/static/app/js/graph-view-2d.js:518-592,634-663  nodeClick 埋点 / 全量渲染
src/memoria/ui/static/app/js/app.js:141,1111-1118           graphGroupId 持久化 / hydrate
src/memoria/ui/static/app/js/app.js:1643-1677               engine/view 初始化 / 节点点击跳编辑器
src/memoria/ui/static/app/js/app.js:1767-1790               suggest_group_labels 调用
src/memoria/ui/static/app/js/app.js:1842-1866               loadGraphData
src/memoria/ui/static/app/js/app.js:5928-5945               jumpToTarget + nav push
src/memoria/ui/static/app/js/app.js:8383-8410               externalFocus
src/memoria/ui/static/app/js/nav-stack.js:23-36,48-58       文件导航栈
src/memoria/ui/static/app/js/graph-settings.js:127-138,193-212 设置 localStorage + 磁盘持久化
docs/design/multilevel-graph/S0-terms-proposal-A.md（只读交叉核对 §9：A:75-80,123-129,135-162,196-262,297-339）
docs/design/multilevel-graph/S0-terms-proposal-B.md（只读交叉核对 §9：B:84-188,227-291,329-363）
docs/design/multilevel-graph/S0-evidence-A.md（A 的证据清单，本文未采信其结论，仅交叉核对）
```

## 9. 对 S0 提案 A/B 的工程交叉核对（只读，2026-11-02 快照）

> 对象：`S0-terms-proposal-A.md`（主办研究，下称 A）、`S0-terms-proposal-B.md`（独立复核，下称 B）、`S0-evidence-A.md`。
> **只读核对，不抄写、不合并**；差异按 S0 章程 §4 判据 2「差异必须逐条列出、不许静默合并」列在此处，交 Lead 裁决。
> 本节不影响 §2 的逐项判定（那是对 S0 章程措辞的校核），只标注「冻结时必须消解」的施工级差异。

### 9.1 收敛项（A、B 与本文一致，可直接作为 S6a/S4 输入）

| 议题 | A | B | 本文对应 | 结论 |
|---|---|---|---|---|
| S0-6 需视图上下文 + 缺席原因 + 禁止「数据有边就画」 | A:196-231（`View=Select(Π,D,f,B)`，视图边状态 8 值枚举，`unknown` 单列） | B:227-259（`RenderContext`，`present(e,ctx)` 唯一判据） | §2 S0-6；E-1/E-4 | **三方收敛**；冻结稿应写成「presence 三值（机检谓词）+ reason 枚举（人读解释）」双层：A 的 `full/bridge_only → present`，`folded/hidden_by_* → suppressed + rule_id`，`unknown → unknown` |
| S0-7 成员关系 ≠ 视图出现 | A:237-260 | B:265-291 | §2 S0-7；E-2 | 三方收敛；支持 ER 独立 `MEMBERSHIP` 实体 |
| S0-9 单一 ViewModel + 2D/3D 后端 + 渲染器不碰数据 | A:299-339 | B:331-363 | §2 S0-9；E-6 | 三方收敛；可直接作为 S6a `VIEW_MODEL`/`RENDER_BACKEND` 的输入 |
| S0-4 簇 ≠ 严格连通分量、代表节点是展示层节点 | A:135-162 | B:158-188 | §2 S0-4；E-3 | 三方收敛；现有 group 必须降级为「连通分量候选」 |

### 9.2 差异项（必须在 S0 冻结或 S6a 前裁决；工程影响已标）

| # | 差异 | A 的立场 | B 的立场 | 工程影响（ER/DFD/ST） | 建议 |
|---|---|---|---|---|---|
| **D-1** | 层次形式化与「层内归属」 | 嵌套划分 `Π_{ℓ+1} ⪯ Π_ℓ`，每层是 K 的划分；「同一层 π_ℓ 是函数 K→Π_ℓ（层内单归属）」，跨维度才多归属（A:75-80,156,160,244-246） | 层次 = 展示粒度轴（`display_node_kind`），不强制每层划分；membership 多对多且允许同层多簇（B:90-95,270-273） | `MEMBERSHIP` 是否对 `(level, kp)` 加函数约束；若按 A，ER 需新增「层级分区」约束并可机检「每层覆盖 K 完整」；若按 B，则无约束、需另有「每层覆盖」检查 | **拆分两类成员关系**：`LEVEL_PARTITION`（层级分区，函数/覆盖完整）+ `ASSOCIATION_MEMBERSHIP`（关联簇，多对多）。若 S0 只允许一种，则必须裁决 A/B（影响 D-ER-02） |
| **D-2** | 簇身份 | 未给身份公式（S2 定） | `cluster_id = stable_hash(members + algorithm_version)`（B:165） | 内容哈希 id 在**成员变化即变**：curation overlay / 审计 / 跨重建引用全部失效；且无法表达「同一簇演化」 | run-scoped 稳定 `cluster_id`（本文 ER）+ 可选 `cluster_key` 内容哈希用于去重/快照；**curation 必须引用 run+cluster，不得引用内容哈希**（S6a 裁） |
| **D-3** | membership 是否可持久化 | 可计算不持久化；若持久化须标 provenance（A:256） | 明说「不写 sidecar、不新增 product 边类型」（B:273） | 决定「人/agent 能否纠正聚类并跨重建保留」：按 B，纠正只能改算法输入，重建即丢；按 A，需要 curation overlay（本文 D-ER-03） | S6 裁：若要求「人可抽查/纠错且可回滚」（U-29/S10、仓库审计纪律），则需要 curation overlay 作为事实（带 `curated_by/at`）；否则在 S2 明确「簇不可人工固定」 |
| **D-4** | ViewModel 纯度 | ViewModel 内含 `mode`、`breadcrumb`、`capabilities`、`navigateBack/modeToggle` 事件（A:303-320） | ViewModel 只放数据 + 最小事件（B:335-345） | 若 mode/导航进 ViewModel，`VIEW_MODEL` 与 `VIEW_FRAME`/`GRAPH_NAV_FRAME` 职责重叠，缓存键与状态机边界会混 | 采用 B 的数据纯度 + A 的导航事件集：ViewModel 只作渲染输入；导航/模式归 `VIEW_FRAME`/`GRAPH_NAV_FRAME`，事件经状态机路由 |
| **D-5** | 维度组合 | v1 只允许**一个**关联维度生效（A:125）；层次先定基座、关联只增量挂接（A:123） | 组合规则待 S1；v1 登记两个 active 维度，组合后仍是同一视图模型（B:127-129,146,152） | 决定 `VIEW_FRAME.dimension_id` 是**单值**还是**有序组合**；若组合，ER 需 `dimension_list + order`，DFD 取景输入随之变 | S1 裁；ER 先按单值设计，保留 `dimension_list` 扩展位（S6a 裁） |

### 9.3 给 Lead 的裁决顺序建议

1. 先裁 **D-1 / D-5**（决定 ER 的键与 ER/DFD 的字段形态）；
2. 再裁 **D-2 / D-3**（决定簇/成员缓存的版本键与审计能力，影响 S6a 冻结）；
3. **D-4** 可并入 S6a 图冻结时裁（不阻塞 S0 术语冻结）。

---

### 9.4 与独立复核异议的对接（`S0-objections.md`，只读；仅列 3 条最严重项的工程结论）

| 异议 | 工程结论 | 对本文图的影响 |
|---|---|---|
| P0-1「U-10 关联维度被窄化为只走语义边」（objections:114） | **可工程化，且必须按 U-10 放宽**：维度注册表的 `edge_sources[]` 必须允许 `contain / reference / 关联(语义) ` 三类边源；「是不是语义边」由 `provenance/contain_kind` 标签表达，**不由跳数边源表达**。DFD P2 已产出三类候选（`collector.py:46-99`），无需改图；ER `EDGE_CANDIDATE.type` 已是三值枚举 | 无需改 v0 图；S1 维度注册表须含 `edge_sources[]` 三值 |
| P0-2「A 的 `kind=bridge` 与 U-19 冲突」（objections:115） | **可工程化**：渲染节点 `kind` 只允许 `{kp, cluster}`；`bridge` 只能是**边状态**（A 的 `bridge_only`）或**节点 role**，不得成为第三节点类型（U-19 原话：一跳节点只能是知识点或代表子图的节点） | ER `VIEW_MODEL` 已按 `{kp,cluster}`；建议在 §1.4 ViewModel 的 nodes 增加 `role ∈ {member, hop, bridge}`（已补） |
| P1-1「最小粒度不可机检 + 层内划分 vs U-21」（objections:116） | 前者由本文 §4 **M-2** 给机检；后者即 §9.2 **D-1**（需 Lead 裁决，本文 ER 按保守形态不预设） | 同 D-1 |
| P1-4「cluster id」（objections:118） | 即 §9.2 **D-2**（run-scoped id vs 内容哈希），本文已给工程建议 | 同 D-2 |

---

## 10. 下一步（本角色的后续交付）

1. `ENGINEERING-PLAN.md`：ER / DFD / 状态图 v0 草案 + 图纸计划 + 冻结规则（与本文件同日交付）；
2. S5a/S6a/S9a：按本文件 §4 的 M-x 机检清单，把 v0 草案细化到「可冻结」；**不领先于 S5/S6/S9 正文设计**；
3. 若 S0 提案 A/B 出现与本文件冲突的术语定义，按章程 §4 判据 2「差异逐条列出、不静默合并」处理，冲突上升 Lead。
