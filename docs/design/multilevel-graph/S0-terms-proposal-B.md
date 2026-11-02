# S0 术语提案 B（独立复核方）

> **依据（最高）**：`docs/design/multilevel-graph-vision.md`（U-1..U-24 + U-25..U-35，逐字原话；本提案不改写）。
> **章程**：`docs/design/multilevel-graph/S0-charter.md`（S0-1..S0-12、预注册判据、不在范围）。议程：`multilevel-graph-seminar-agenda.md` V0.2。
> **性质**：独立复核方提案；**不合并、不转述**提案 A；与 A 的差异另见 `S0-objections.md`（写完后才对照）。
> **日期**：2026-11-02（Asia/Shanghai）。
> **证据等级定义（本提案口径，固定）**：
> - **A（可执行/机检）**：仓库内可运行命令或 `file:line` 源码事实，可复算；`ev:code:<path>:<line>`。
> - **B（冻结数据/实测）**：冻结语料/已冻结测量产物上的统计，带语料身份；`ev:data:<artifact>#<sha8>`。
> - **C（契约/文档推断）**：由已冻结文档/契约可推出，但无独立机检；`ev:doc:<path>:<section>`。
> - **PI（本项目假设）**：无独立根，只能作设计假设/待验证；不得当裁决证据。
> 每项末给「建议裁决」（术语级，不替 S1–S10 做实现决策）与证据等级。

---

## 0. 覆盖矩阵（S0 相关 U 编号；全表在 S0 冻结稿合并时补）

| U# | 原话要点 | 本提案落点 | 证据等级 |
|---|---|---|---|
| U-1 | 图谱最重要的是语义 | S0-1 语义判据 | C |
| U-3 | 不要海量节点+错综连线 | S0-6 选择性渲染需求；S0-8 默认视图 | C |
| U-5 | 默认节点不再是「最小粒度 KP」 | S0-2 层次；S0-4 簇节点 | C |
| U-6 | 代表连通子图的节点、外观更大 | S0-4 簇/代表节点 | C |
| U-8 | 层次维度 | S0-2 | C |
| U-9/U-12 | 还有其他维度/更多维度 | S0-3 维度；开放槽位 | C |
| U-10 | 关联维度：显示一般不可见关联节点 | S0-3；S0-5 一跳 | C |
| U-11 | 关联维度跳数需设计 | S0-5 一跳计法（预算在 S4） | C |
| U-13/U-14 | 非严格连通子图：内聚高+零星桥；语义小群 | S0-4 簇定义 | C |
| U-15 | 深入后经有关联语义的边挂接一跳 | S0-5 | C |
| U-16 | 旧版连边两端都渲染；新设计选择性渲染 | S0-6；S0-8 | A（旧行为证据 `graph-engine.js:88-110`） |
| U-17 | 一跳背后图不一定与本图有语义关系 | S0-5 边界；S0-6 判据 | C |
| U-18 | 挂接一跳避免多跳污染 | S0-5 | C |
| U-19/U-20 | 一跳节点可为 KP/簇节点；KP 点击跳编辑器 | S0-5；S0-9 事件契约 | A（`app.js` nodeClick 旧行为） |
| U-21/U-31 | 多归属；先定义、可能不设上限 | S0-7 | C |
| U-25 | 其他维度先留开放槽位 | S0-3 开放槽位登记 | C |
| U-26 | 默认彻底替代旧全展开；保留开关 | S0-8 | C |
| U-27 | 边有「存无」「类型」不同 | S0-6 | C |
| U-28 | 最深层次待研讨；最小节点粒度=知识点 | S0-2 | C |
| U-29 | 关键：memoria agent 怎么设计知识点 | S0-10（细谈 S10） | C |
| U-30 | 关联维度需具体定义与设计 | S0-3（细谈 S1/S4） | C |
| U-31 | 多归属先定义再决定/不设上限 | S0-7 | C |
| U-32 | 规模不是问题；关键在后端检索 | S0-6（selection 算法在 S9）；S0-10 边界 | C |
| U-33 | 2D/3D 不分家，只是带接口的渲染板块 | S0-9 单一渲染接口 | C |
| U-34/U-35 | 逐议项/保质量；SE 专家 DFD/ER/状态图 | 本提案逐项结构；S0-9/S6/S9a 交接 | C |

---

## S0-1 「语义」

**定义（一句话）**：在图谱语境下，「语义」= **一条可被指认的关系断言（subject — relation type — object）及其可核出处**；不是视觉重要性，不是"图上有一条线"。

**形式化（建议术语）**：
```
semantic_edge(e) ⇔
  e.type ∈ {contain_semantic, extend}
  ∧ e 有可读 assertion_source（file/line_start/line_end 非空且 quote_sha256 可复算）
  ∧ (contain 时 e.contain_kind == "semantic" 且 e.curated_by/curated_at 存在)
  ∧ 该断言未过期（quote 可复算/未被标 stale）
```
- `reference`（无断言跳转）**不计入语义边**；`contain(structural)` **不计入**（仅结构包含候选，不得作语义链路——ontology v0.3 §2.3 规则 5）。
- 无 provenance 的 `extend` 是**候选**（`provenance_state=missing`），不是已核语义。
- 视觉大小/颜色/位置 ≠ 语义；「看起来有边」不构成语义判据。

**反例**：
1. `reference` 边在 `edges[]` 中存在（旧数据 100% reference）→ 只是无断言跳转，**不能**说"两 KP 有语义关系"。
2. 33 条 contain 全部由 KP range 几何包含生成（`derived_by=system_range`）→ 是 structural，**不能**当语义整体-部分。
3. 作者边 26 条当前无锚点（`provenance_state=missing`）→ 不能标 asserted、不能算已核语义。
4. UI 里两点有连线（旧 `expandLinks` 把每条 edge 的每个 target 都画线）→ 只是渲染，不是语义判据。

**边界用例**：
- `contain(semantic)` 有 `assertion_source` 但缺 `curated_by` → 不满足语义（fail-closed，退回 structural/候选）。
- `extend` 有 `assertion_source` 但 `quote_sha256` 与当前正文不一致 → 标 stale，不删除边，但不算当前有效语义。
- 同一对节点同时存在 `reference` 与 `extend` 两条边 → 只有 extend（有锚点）那条算语义；reference 只是跳转。
- 无边但有链接（link without edge）→ 无关系断言；不是"语义关系"。

**U 映射**：U-1、U-16、U-17、U-27（边存在/类型是语义的一部分，见 S0-6）。

**建议裁决**：S0 冻结「语义边」= 可核断言（asserted + 可读锚点；contain 仅 semantic）；`reference`/`structural` 明确排除；后续所有"语义"字段/视图必须调用同一判据，不得各自发明。

**证据等级**：A（`kg-ontology-v0.md` §2.1/§2.2/§2.3 与 `docs/design/kg-edge-provenance.schema.json` 可机检字段）+ B（G4/G5 冻结语料 62 边/26/3/33）。

---

## S0-2 层次（level）与最小粒度

**定义（一句话）**：**层次 = 同一知识范围内、以"展示粒度"为轴的取景级别**；越深越细，最深一层的最小节点粒度 = **知识点（KP）**；更深的内容（句/断言/概念）不在 v1 成为节点，只作为 KP 的内部内容。

**形式化**：
```
Level = ⟨level_id, granularity, display_node_kind⟩
granularity 有序（L0 最粗 → Ln 最细）；同一 KP 集在不同 level 用不同 display node kind 表示
display_node_kind ∈ {cluster_node, kp_node}          # v1 仅这两类
∀ level L: 每个 kp_node 恰好对应 1 个 canonical KP id（type|source|target 中的节点 id）
最深 level L_deepest: display_node_kind 只能 = kp_node；不存在句/词/断言节点
L_deepest 具体深度 = 待 S1/S10 研讨（U-28），本项只钉住"最深不能细于 KP"与"必须有 KP 层"
```
**机检（可执行）**：给定任一视图模型，断言：(a) 每个 node 的 `kind ∈ {cluster,kp}`；(b) `kp` node 的 id 必须存在于 collector 的 KP 集；(c) 任一 `cluster` node 的成员展开到最深后全部落到 KP。当前实现节点字段见 `collector.py`（id/name/file/start_line/end_line 等，A），可直接做该断言。

**反例**：
1. 把"句子/段落"作为节点渲染 → 违背 U-28（最小节点粒度=知识点）。
2. 把 `cluster node` 当成新的本体实体写进 sidecar（新增类型/事实源）→ 违背 ontology v0.3 §4 与 DM-P7。
3. 将"层次"实现为**同一个 KP 的 3 个缩放级别**（只改 radius）→ 不是层次，只是视觉缩放；层次必须有 display node kind/成员集变化。
4. 最深层次无限细分到句/词 → 违背 U-28。

**边界用例**：
- 单 KP 构成的 cluster（成员数=1）：允许；下钻后就是该 KP 节点。
- KP 的 range 无效（`range_ok=false`）：仍是 KP（最小粒度不变），但视觉/下钻可标注不可定位；不得因此把它变成"非 KP 节点"。
- 空 cluster：不允许（簇节点必须至少 1 个成员）。
- 层次深度上限：S0 不设；U-28 交给 S1/S10 决定"最深到哪一层"，但下界固定为 KP。

**U 映射**：U-4、U-5、U-8、U-28（+U-6 的代表节点外观属 S3）。

**建议裁决**：冻结"层次=展示粒度轴；v1 display node kind 仅 {cluster,kp}；最深节点粒度=KP；句/词/断言不作为 v1 节点"；深度上限待 S1/S10，S0 只写"不得细于 KP"。

**证据等级**：A（collector 节点字段/现有 KP 集可直接机检）+ C（U-5/U-28 语义）。

---

## S0-3 维度（dimension）

**定义（一句话）**：**维度 = 同一层次下，另一套"取景+关系选择"规则**（选择哪些节点/边、按什么关系挂接、默认几跳）；层次变"粒度"，维度变"取景视角"。

**形式化**：
```
Dimension = ⟨dimension_id, status, node_selector, edge_selector, hop_policy, activation⟩
status ∈ {active, reserved(开放槽位), deprecated}
active 维度 v1 至少两个：level_dimension（层次轴本身作为导航轴）、relation_dimension（关联维度，定义待 S1/S4/U-30；**其 edge_selector 必须覆盖 U-10 明示的「包含关系 / 引用 / 语义关联」三类关系源**，而不是只走 semantic 边）
reserved 槽位：有 id/owner/activation_criteria，但【无实现、无渲染分支、无默认数据路径】
dimension 组合规则（叠加/互斥/优先级）待 S1；S0 只要求：每个视图上下文必须能指出"当前 dimension id"与"selection 规则来源"
```
**与层次区别（机检）**：层次改变 `display_node_kind`（粒度），维度**不改变**粒度，只改变被选中的节点/边集合与挂接规则。若某配置只改节点大小/颜色，既不是层次也不是维度（是 S3 视觉）。

**开放槽位登记（U-25）**：
```json
{"dimension_id":"<id>","status":"reserved","owner":"<role>","activation_criteria":"<可判据>","impl":"none","render_branch":"none"}
```
机检：reserved 维度 id 不得出现在渲染配置/默认取景代码的 active 列表中；不得为它写默认 UI 分支。

**反例**：
1. 把"2D/3D"当维度 → 违背 U-33（渲染后端不是维度）。
2. 把"边类型"直接当维度（reference/extend/contain 各一个维度）→ 类型是边属性，不是取景维度；会把 S0-6 的"类型差异"和维度混为一谈。
3. 把"时间轴"当已定维度 → 未批准（U-12/U-25 先留槽位）。
4. 为 reserved 维度先写死 UI 开关/代码分支 → 违反"开放槽位不得被误实现"。

**边界用例**：
- 同一 level 下 relation_dimension 与 level_dimension 同时激活：组合规则待 S1；S0 要求"不得隐式相乘导致双真相"（组合后仍是同一视图模型，不是两套数据）。
- 维度可切换但不动当前 level（除显式规格）。
- 未来新增维度：只登记槽位，不改现有 active 维度定义；新增时须新章程。

**U 映射**：U-9、U-10、U-12、U-25、U-30。

**建议裁决**：冻结"层次=粒度轴，维度=取景轴"二分；v1 active 维度只登记为 `level_dimension` + `relation_dimension`（后者定义待 S1/S4）；其余全部 `reserved` 槽位且 **无实现/无渲染分支**；2D/3D 明确不是维度（U-33）。

**证据等级**：C（U-9/U-12/U-25/U-30）+ PI（"v1 仅两个 active 维度"是设计假设，需 S1 验证）。

---

## S0-4 簇 / 代表连通子图

**定义（一句话）**：**簇 = 一小组 KP，内部语义关联相对紧密、与外部只有零星桥**；「代表连通子图的节点」是**该簇的展示节点**（cluster_node），不是新的本体实体，也不是严格连通分量。

**形式化（S0 只钉契约，阈值交 S2）**：
```
Cluster = ⟨cluster_id, members ⊆ KP, internal_edges ⊆ semantic_edges, bridge_edges, algorithm_version, evidence⟩
cluster_id = stable_hash(sorted(member_canonical_ids) + algorithm_version)   # 可复算、可去重
bridge edge = 连接 members 与非 members 的语义边（不含 reference；structural contain 不计入语义桥）
"内聚高+零星桥" = S2 定义的可复算判据（如内部密度/桥数比/连通性）；S0 不写死阈值
cluster_node 是【展示层节点】：members 必须可展开到 KP；不得写入 sidecar/不得新增 edge type
```
**反例**：
1. 严格连通分量（弱连通/强连通）→ 与 U-13 不符（原话说"不算严格意义上的连通子图"）。
2. 按文件夹/目录分组（现有 `MemoriaGraphGroups` 的 group 是**目录/分组**）→ 不是语义簇；两者不得混用（S0-12 标红）。
3. 把 cluster_node 当 KP 写进 sidecar/edges → 新增本体类型，违反 ontology v0.3 §4、DM-P7。
4. 用 reference 边/structural contain 当"桥"来证明语义内聚 → 偷换语义（S0-1）。
5. 同一 KP 在不同层次被拆成多个"代表节点"但 cluster_id 不稳定/不可复算 → 无法做 G6 快照与复现。

**边界用例**：
- 成员数=1 的簇（允许，作为"代表节点"退化情形）。
- 一个簇内部无任何语义边（仅结构包含）→ 不是语义簇；只能作为"分组/目录"（S0-12 映射到 group，不是 cluster）。
- 桥边只有 1 条且指向另一簇 → 允许；一跳选择规则在 S0-5。
- 簇重叠/嵌套（一个 KP 属于多个簇）→ 见 S0-7 多归属；S0 只要求成员关系可多对多，cluster_id 稳定。
- 簇算法版本变化 → `algorithm_version` 变 ⇒ cluster_id 变；旧快照可复算（G6 要求）。

**U 映射**：U-6、U-13、U-14（+U-21 多归属、U-28 最小粒度）。

**建议裁决**：冻结"簇=语义内聚小群（非严格连通分量）；代表节点是展示层 cluster_node，不是本体实体；簇 id 稳定可复算、成员可展开到 KP；阈值/算法由 S2 定；严格连通分量/目录分组不得冒充簇"。

**证据等级**：C（U-13/U-14）+ A（`MemoriaGraphGroups` 现有 group 语义 = 目录分组，可机检区分）+ PI（阈值）。

---

## S0-5 一跳挂接

**定义（一句话）**：**一跳 = 从当前可见节点出发，沿当前维度允许的「关联关系边」恰好走 1 条边**；挂接集合 = 这些邻居中、尚未在当前视图可见的节点（KP 或簇节点），**不递归多跳**。
> **修订 R1（B 初稿把 U-10 读窄了；写异议时回读 U-10 原话后自更正，不是采用 A——“A 同样窄化了，见 `S0-objections.md` P0-1”）**：U-10 明说关联维度要显示「包含关系、引用、语义关联等等」的关联节点 ⇒ 关联维度的一跳**允许**沿 contain（structural 或 semantic）、reference、semantic extend 等关系边计数；**不允许**的是把非 semantic 关系**标成语义边**。语义强度与跳数是两件事：跳数按关系源计，semantic/navigation/structural 是边上的标签。

**形式化**：
```
hop1(ctx) = { n | ∃ e ∈ relation_edges(ctx) : (e.source ∈ visible(ctx) ∧ n = e.target) ∨ (e.target ∈ visible(ctx) ∧ n = e.source) }
                 # relation_edges = 当前维度 edge_selector 选中的关系源（U-10：contain/reference/语义关联）
attach_set(ctx) = hop1(ctx) \ visible(ctx)      # 去重（canonical id），排除已在视图中的节点
每条挂接边必须带 label ∈ {semantic, navigation, structural}；跳数计数与 label 无关
hop 计数轴 = 当前 dimension 的 edge_selector；跨维度只在显式切换后重新计 1 跳（不把别的维度边算进当前跳）
当 visible 节点是 cluster_node：以该簇 members 的桥边做聚合（桥边可含 contain/reference，但须标非 semantic 若证据弱）；一跳邻居指向外部簇/ KP；具体聚合规则待 S4，但 S0 要求"簇的成员边不得把簇内边当一跳"
```
**机检**：`attach_set` 可由视图模型 + 当前维度 `relation_edges(ctx)`（U-10 关系源）复算；不得包含 visible 集合成员；**非 semantic 关系必须标 navigation/structural，不得标 semantic**；semantic 关系要求可读锚点。

**反例**：
1. 把 reference/structural 关系挂接的节点**标成 semantic**（可以挂接——U-10；错在冒充语义，违背 U-15/U-17/U-27）。
2. 从一跳节点继续自动展开 2/3 跳 → 违背 U-18"避免多跳污染"。
3. 把"一跳背后图里的节点"全部带入 → 违背 U-17（背后图不一定与本图有语义关系）。
4. 对 cluster_node 一跳时把簇内成员当邻居 → 一跳集合混入非外部节点。
5. 同一节点通过多条边重复挂接 → 未按 canonical id 去重。

**边界用例**：
- 一跳节点是 cluster_node → 允许（U-19）；点击进入该簇（S5）。
- 一跳节点已被当前视图以另一种角色显示 → 不重复添加（去重）。
- 一跳邻居没有可读锚点：若它是 **reference/structural** 关系 → 允许挂接（标 navigation/structural，U-10）；若它是 **semantic 候选**（无锚点/未 asserted）→ 不进挂接集合（只作为"待补证据"提示）。
- 当前维度切换到 relation_dimension → 重新按该维度 edge_selector 计 1 跳（不是累加）。
- 跨维度边：不得跨维度自动加跳（S1 决定组合方式）。

**U 映射**：U-10、U-11、U-15、U-17、U-18、U-19、U-22。

**建议裁决**：冻结"一跳沿当前维度**关联关系源**（U-10：包含/引用/语义关联）、恰好 1 条、按 canonical id 去重、排除已可见节点、不递归；semantic/navigation/structural 是边标签、不是能否挂接的开关；cluster_node 用桥边聚合"；跳数预算/跨维度组合由 S4/S1 定。

**证据等级**：C（U-15/U-17/U-18）+ A（当前 `expandLinks` 旧行为 = 全展开可作反例证据 `graph-engine.js:88-110`）。

---

## S0-6 选择性渲染 + 边「存无/类型」

**定义（一句话）**：**选择性渲染 = 只渲染由（层次、维度、焦点、跳数预算、语义判据）共同选出的节点/边**；**边在视图中的"存在"是上下文函数，不是 `edges[]` 里有就画**（U-27）；同一对节点在不同层/维/上下文可以「有边/无边/类型不同」。

**形式化**：
```
RenderContext = ⟨level_id, dimension_id, focus_id, hop_budget, filters⟩
render(set) = ⟨V_nodes, V_edges⟩
V_edges = { e ∈ semantic_edges(dimension) | endpoints(e) ⊆ V_nodes ∧ present(e, ctx) }
present(e, ctx) ⇔ e ∈ semantic_edges(ctx)
                 ∧ type_allowed(e.type, dimension)
                 ∧ hop(e, ctx) ≤ hop_budget
                 ∧ ¬suppressed(e, ctx)      # 例：被层级聚合折叠、被显式排除
edge_display_type(e) = 本体 type + contain_kind（semantic/structural）+ provenance 状态（可选视觉区分）；
                      不得因渲染便利改写本体 type（旧实现 contain→reference 静默改写是反例）
```
**反例（旧行为）**：`graph-engine.js:88-110 expandLinks(edges)` 对 `edges[]` 每条边的每个 target 无条件生成 link；`loadPayload` 直接 `rawEdges = payload.edges`（`graph-engine.js:179-181`）→ **数据有边就渲染**，违背 U-27/U-16。
2. 对"同一对节点在不同层次边存无不同"用同一份静态 edge set 渲染 → 违背 U-27。
3. 把 reference 边渲染成与 extend 同样权重/颜色 → 类型差异丢失（现有 `edgeColor` 以 type 分色，但语义层未区分）。
4. 全展开开关绕过 `present()` 直接画 rawEdges → 双真相（见 S0-8）。

**边界用例**：
- 同一对节点存在多条不同类型边（dedupe key 含 type）：按类型分别判定 present；不得合并成一条"复合边"。
- `contain(structural)` 与 `contain(semantic)` 同对节点：类型显示与语义入集不同（structural 不进 semantic_edges）。
- 边存在但一端被聚合进 cluster：边改挂在 cluster_node 上（S4 规则），不得丢语义。
- hop_budget=0：只渲染 focus/可见节点，无边；hop_budget=1：一跳挂接（S0-5）。
- 全展开开关：仍是同一 `semantic_edges` + `present()` 的极端参数（无预算/无过滤），不是另一套数据。

**U 映射**：U-16、U-17、U-27（+U-3/U-18 体验理由）。

**建议裁决**：冻结"选择性渲染=RenderContext 的函数；`present(e, ctx)` 是唯一渲染判据；禁止 data-has-edge⇒render；边类型差异=本体 type+contain_kind+provenance 状态；静默改写 type 禁止"；具体选择算法/范围由 S4 定。

**证据等级**：A（旧实现 `graph-engine.js` 行号可机检；ontology v0.3 `contain_kind` 可机检）+ C（U-16/U-27 语义）。

---

## S0-7 多归属

**定义（一句话）**：**「属于」= 成员关系（membership），是 KP/簇与"簇/层次/维度"之间的稳定关系；「视图出现」= 某一 RenderContext 下的临时可见性**。二者必须分开：视图出现**不产生**归属，归属**不保证**在某个视图出现。

**形式化**：
```
membership: KP × Container → bool        # Container ∈ {cluster, level, dimension}
membership 多对多；允许同一 KP 同时 ∈ 多个 cluster/level/dimension
view_visible(kp, ctx) 由 RenderContext 计算，≠ membership
不得用单值 parent_id/owner_cluster 表达归属
membership 是研究/展示层数据（不写 sidecar、不新增 product 边类型）；cluster 上限/规则由 S2/S6 定（可能不设上限 U-31）
```
**反例**：
1. 用 `node.parent`/单值字段表示归属 → 一个 KP 只能有一个父，违背 U-21。
2. 把"本视图出现了某 KP"当成"它属于本簇/本层" → 混淆视图出现与成员关系（S0-1 语义污染）。
3. 为多归属在每个簇里复制 KP 实体/复制 sidecar 记录 → 多份真相/同步问题。
4. 把 membership 当产品边（写进 edges[]）→ 新增本体关系，违背 ontology v0.3 §4/DM-P7。

**边界用例**：
- 同一 KP 同时属于两个簇且两簇在同一视图 → 视图需去重显示（S5 导航规则），membership 仍为 2。
- KP 属于某簇但该簇当前不可见 → membership 仍存在；进入该簇后可见。
- 不同层次/维度子图同时包含同一 KP → 允许；"从哪来回哪去"由 S5 状态机决定。
- 上限：U-31 允许"不设上限"；S0 不设上限，只要求 membership 集合可枚举、可复算。

**U 映射**：U-21、U-31（+U-7/U-22 导航交互在 S5）。

**建议裁决**：冻结"多归属=membership 多对多关系；视图出现与成员关系分离；不设上限由 S0 默认，S2/S6 可收紧但须给证据；membership 不写产品 sidecar/不新增边类型"。

**证据等级**：C（U-21/U-31）+ A（现有节点/分组模型无可表达多归属的单值字段，可机检；`MemoriaGraphGroups` 是目录分组，非语义成员）。

---

## S0-8 默认视图 vs 全展开

**定义（一句话）**：**默认视图 = 新的多层次/多维度选择性渲染入口，彻底替代旧全展开成为默认**（U-26）；**全展开 = 保留的兼容开关**，用同一份图数据 + 同一渲染接口的极端参数（无预算/无过滤）显示旧行为；二者**不是两条设计线、不是两份真相**。

**形式化**：
```
DataSource: collector.get_graph_data() 的 nodes/edges（唯一事实源）  # 两条路径 404/454 问题见 ontology §5.2，不得引入第三份
ViewModel = select(DataSource, RenderContext{default|full_expand})
Renderer(viewModel) —— 2D/3D 同一接口（S0-9）
default 模式：默认入口，受 level/dimension/hop_budget/present() 约束
full_expand：同一 DataSource + 同一 Renderer，参数退化为"全部数据边可见"（含 reference/structural，**必须显式标注 navigation/structural，不得标 semantic**）；只是兼容视图，不是产品第二主线
```
**机检**：两种模式必须共用同一 `get_graph_data()` 数据源与同一渲染接口；禁止为 full_expand 新增独立数据文件/独立渲染器/独立语义模型；默认入口只能有一个。

**反例**：
1. 把全展开实现成"另一套数据源/另一套渲染器" → 双主线/双真相，违背 U-26。
2. 默认视图仍以旧全展开为入口，新视图只是"可选高级模式" → 违背"彻底替代"。
3. 全展开绕过 `present()` 直接画 rawEdges（旧 `expandLinks`）→ 全展开成为第二套语义（且与 U-27 冲突）。
4. 默认视图与全展开各维护一份选点/边集合缓存且可独立漂移 → 双真相。

**边界用例**：
- 用户从默认视图切到全展开：应能一键切换且返回后保持导航状态（S5）。
- 全展开下点击节点：仍按旧行为（KP 跳编辑器 U-20）；但语义徽标/类型仍按 S0-6 显示，不改写本体。
- 全展开性能退化：允许慢，但不得为它改默认视图语义（U-32：规模不是问题，关键后端检索）。
- 无任何簇（全库仅 KP）：默认视图退化为 KP 图；仍是同一入口。

**U 映射**：U-3、U-16、U-26、U-27、U-32。

**建议裁决**：冻结"默认=新多层次选择性渲染（唯一默认入口）；全展开=同数据源同接口的兼容开关；禁止双数据源/双渲染器/双语义模型；全展开不是第二主线"。

**证据等级**：C（U-26）+ A（现有 `expandLinks`/`rawEdges` 旧行为可作兼容视图基线；当前无第二数据源）。

---

## S0-9 渲染接口边界（2D/3D 统一）

**定义（一句话）**：**2D/3D 不是两条设计线，而是同一「视图模型→渲染」接口的两个实现后端**（U-33）；S0/S3 只定义接口与视图模型，不设计各自渲染算法。

**形式化（最小接口契约）**：
```
输入 ViewModel = {
  view_id, level_id, dimension_id, focus_id, hop_budget,
  nodes: [{id, kind(cluster|kp), label, member_count?, semantic_badges?}],
  edges: [{id/canonical, source, target, display_type, semantic(bool), provenance_state?}],
  layout_hints?（确定性种子/初始位置；2D/3D 可各自解释，不改变语义）,
  breadcrumb: [...]
}
输出 Renderer: mount(container, viewModel) / update(viewModel) / unmount()
事件回传 Event = {type: nodeClick|clusterDrill|edgeClick?|hover, node_id?, edge_id?, view_id}
                 # 最小集；2D/3D 必须都发同一事件语义
禁止：语义选择逻辑写进渲染器（渲染器不得自己决定 semantic_edges/present）；禁止 2D/3D 各自一套 ViewModel
```
**反例**：
1. 为 2D 设计"力导向图"、为 3D 设计"星系图"两套数据模型/两套选择规则 → 违背 U-33。
2. 在渲染器内部读 `rawEdges` 并按 type 过滤 → 语义逻辑泄漏进渲染后端。
3. 2D/3D 事件语义不同（一个发 nodeClick，另一个发 pick）→ 上层无法统一导航（S5）。
4. 把 2D/3D 当两个维度/两种层次 → 维度/层次混淆（S0-3）。

**边界用例**：
- 3D 后端暂缺：接口仍先冻结；2D 是唯一实现，事件契约不变。
- 同一 ViewModel 在 2D/3D 渲染结果不同（视觉）→ 允许；语义集合/事件必须相同。
- 性能不同的后端：不得因此改变 ViewModel 语义（只允许降级渲染，如 LOD）。
- 可访问性/键盘：事件契约需允许 2D DOM/3D canvas 各自实现同一语义。

**U 映射**：U-19（事件）、U-20（KP 点击跳编辑器）、U-33（核心）。

**建议裁决**：冻结"单一 ViewModel + 单一渲染接口 + 最小事件契约；2D/3D 是后端实现，禁止两条设计线/两套语义；语义选择在渲染器之外"。

**证据等级**：C（U-33）+ A（现有 `graph-engine.js` 可作为 ViewModel 雏形；`graph-view-2d.js` 是 2D 后端；未见 3D 后端）。

---

## S0-10 agent 的角色边界

**定义（一句话）**：agent 在三个不同层各有边界：**(a) 设计知识点（S10）**= 提议 KP 的产生/边界/命名/粒度，但须可审计、可回滚；**(b) 决定语义（S0-1/provenance）**= 只能以带可读锚点+审计身份的 curation 落库（ontology v0.3 允许 agent curate_contain），不得无锚点冒充；**(c) 决定取景（S9）**= 后端检索/取景算法可由 agent 设计/调用，但渲染集合由确定性服务计算，agent 不直接改视图状态/不写渲染器。

**形式化（职责表）**：
```
层            agent 可以                                    agent 不可以
KP 设计       提议 KP（从正文/选区/对话）、边界/命名/粒度   无审计地覆写用户正文/删除 KP（须 propose_write + 审计）
语义          curate_contain(semantic) 带 assertion_source  无锚点/无 curated_by 的 asserted；改 sidecar 绕过 curation
取景         设计/调用 S9 检索算法、给定 (level,dim,focus,budget) 直接改渲染器状态/DOM/布局；把 agent 偏好写进产品事实源
```
**机检**：agent 动作必须落在已存在 op（`propose_write`/`curate_contain` 等）与审计字段（`curated_by/curated_at`）；视图计算函数无 agent 直接写路径；KP 创建/修改有审计/回滚记录（S10 冻结）。

**反例**：
1. agent 直接往 sidecar 写 `asserted` 而无 `assertion_source` → 违背 ontology v0.3 §2.2/§2.3（fail-closed）。
2. agent 根据"想看什么"直接改渲染集合/写 DOM → 渲染层被污染、不可复算。
3. agent 自动生成大量 KP 但不审计/不回滚 → 违背 U-29 的"关键点=agent 怎么设计知识点"（须有机制，S10）。
4. 把 agent 的检索偏好写进产品事实源（sidecar/用户库）→ 产品事实与研究偏好混层（AGENTS.md §1）。

**边界用例**：
- agent 提议 KP，人被抽查/撤销 → 允许（S10 定流程）。
- agent curation 与已有作者断言冲突 → 拒绝/人工裁决（不得静默覆盖）。
- agent 取景请求超出 hop_budget（如要 3 跳）→ 服务按预算截断/拒绝；agent 不能绕过。
- agent 离线/失败 → 默认视图用确定性基线（S9 退化策略）。

**U 映射**：U-29（核心）、U-32（后端取景）、U-1/U-27（语义判据输入）。

**建议裁决**：冻结"agent 三层边界：KP 设计（S10、可审计）、语义 curation（带锚点+审计身份）、取景算法（S9、确定性服务计算）；agent 不得直接改渲染状态/绕过语义判据/写产品事实源"；具体流程由 S10/S9 冻结。

**证据等级**：C（U-29/U-32）+ A（ontology v0.3 已有 `curate_contain`/`curated_by/curated_at` 与 `propose_write` 机制，可机检）。

---

## S0-11 不做什么（v1 边界）

**定义（一句话）**：本板块 v1 明确**不做**下列事项；任何一项要做，须新开章程并给人批准（U-23 流程）。

| # | v1 不做 | 依据 | 证据等级 |
|---|---|---|---|
| 1 | 不自动改写用户正文（KP 只能经审计的 propose_write/curation） | AGENTS.md 单一事实源；U-29 | A |
| 2 | 不做跨库图（单 KB 内多层次） | 议程范围；U-19 上下文 | C |
| 3 | 不做时间轴维度（先留 reserved 槽位） | U-25；S0-3 | C |
| 4 | 不做词级/句级节点（最小节点粒度=知识点） | U-28；S0-2 | C |
| 5 | 不新增本体语义类型（edge type 仍 contain/reference/extend） | ontology v0.3 §4；U-27 的"类型"指现有类型+contain_kind，不是新类型 | A |
| 6 | 不把 cluster/membership 写进产品 sidecar/不新增产品段 | ontology v0.3 §4/DM-P7；AGENTS.md §1 | A |
| 7 | 不做"数据有边就渲染"（旧 expandLinks 行为） | U-16/U-27；S0-6 | A |
| 8 | 不把 2D/3D 拆成两条设计线/两套数据模型 | U-33；S0-9 | C |
| 9 | 不做全展开第二主线/第二数据源（只做开关） | U-26；S0-8 | C |
| 10 | 不做无锚点的 asserted、不让 agent 冒充作者断言 | ontology v0.3 §2.2；S0-1/S0-10 | A |
| 11 | 不在 S0–S6 冻结前写产品代码 | 议程 §5 纪律；章程 §7 | C |
| 12 | 不设多归属硬上限（v1 默认不设上限） | U-31；S0-7 | PI |

**反例（若违反）**：新 edge type 进 schema/bump schema_version；cluster 实体写 sidecar；全展开独立数据源；agent 无锚点 asserted；词级节点。均为"越界 = 重新开章程"。

**边界用例**：
- 未来若 S10 要"句级 KP"：属改变最小粒度，必须重开 S0（U-23），不是 S10 私改。
- 未来若要时间轴：从 reserved 激活 → 新章程，不许在 S4 私开。
- 全展开性能优化：可改渲染，不得改语义/数据源。

**U 映射**：U-4、U-23、U-25、U-28、U-33；ontology §4。

**建议裁决**：以上 12 条写进 S0 冻结稿"不做什么"；其中 1/5/6/7/10 有 A 级证据，可作硬门禁；2/3/4/8/9/11/12 为 v1 范围假设（C/PI），需 Lead 裁决。

**证据等级**：A（ontology/AGENTS 约束）+ C/PI（范围选择）。

---

## S0-12 术语映射（新 ↔ 现有）

**定义（一句话）**：把 S0 新术语一对一/一对多映射到现有产品术语；**冲突处必须标红并给兼容/迁移/回滚**（章程预注册判据 3）。

| 新术语 | 现有术语/实现 | 映射关系 | 冲突/风险 | 兼容/迁移/回滚 |
|---|---|---|---|---|
| KP（知识点） | `knowledge_points[]` / `node.id` / `kp_id` | 1:1 同义（最小粒度） | 无 | 不变 |
| edge（语义边） | `edges[]` 条目 + `type/relevance/derived/origin` | 部分：仅满足 S0-1 判据的边才叫语义边 | 现有 `edges[]` 含 reference/structural，不能全叫语义边 | 加 S0-1 判据；不删旧边；UI 文案区分（ontology §2.3） |
| link（链接） | `links[]` / `link.instances` | link ≠ edge（旧契约已解耦） | 旧代码把 link 投影成 edge；反之 reference 边无 link | 保留"有 link 无 edge / 有 edge 无 link"两种（ontology §2）；不得强制 1:1 |
| cluster / 代表子图节点 | **现有 `MemoriaGraphGroups` 的 group（目录分组）** | **不同**：group=目录/分组；cluster=语义内聚小群 | **标红**：若把 group 当 cluster，会把目录结构当语义 | 新增 cluster 为**研究/展示层**对象；不改 product group 语义；两者同名禁止（S0-12 需新名 `semantic_cluster`） |
| level（层次） | 现无；旧"全展开"是单层次 KP 图 | 新概念 | 旧默认视图将被替代（U-26） | 默认入口替换；旧行为=full_expand 开关（S0-8） |
| dimension（维度） | 现无；`edge.type` 不是维度 | 新概念 | 若拿 edge.type 当维度 → 类型/取景混淆 | 单独 dimension 注册表；reserved 槽位 |
| 选择性渲染 | `expandLinks`/`loadPayload` 现有"数据有边就画" | **反面**：旧行为=非选择性 | 旧实现违反 U-16/U-27 | 新视图模型 + `present()`；旧行为仅 full_expand 兼容（且不得称语义正确） |
| present(e,ctx)/semantic_edges | 现无 | 新概念 | 需 S0-1 语义判据支撑 | 研究/服务层函数；不写产品事实源 |
| view model | `get_graph_data()` payload（nodes/edges） | 同层概念：payload 是数据，ViewModel 是取景结果 | 两者若混用会把"原始数据"当"视图" | 明确 DataSource→ViewModel→Renderer 三段（S0-8/S0-9） |
| renderer（2D/3D） | `graph-view-2d.js`（2D）；3D 现无 | 2D/3D=同一接口后端 | 若给 3D 另设数据模型 → U-33 违背 | 单一接口；2D 先实现；3D 后接 |
| full_expand 全展开 | 现有默认视图行为 | 兼容开关 | 若成为第二主线 → 违背 U-26 | 同数据源同接口；默认入口唯一 |
| contain_kind | ontology v0.3 `structuralsemantic` | 1:1（仅 contain 边） | 旧数据按 structural fail-safe | 已有 v0.2/v0.3 补丁；不改 |
| provenance（asserted/inferred/missing） | ontology v0.1 §2.2 | 1:1（语义判据输入） | 旧数据 missing | 已有；S0-1 消费 |
| graph group（现有） | `MemoriaGraphGroups` 目录分组 | 与 cluster **不同** | 同名混淆风险 | 标红：命名区分 `scheme: folder_group` vs `semantic_cluster` |

**冲突处（标红）**：
1. **cluster vs 现有 group**：现有 `MemoriaGraphGroups` 按目录/分组；S0 的簇是语义内聚小群。**不得**复用同名字段/同一数据源；建议新名 `semantic_cluster`，S6 决定存储（研究层，不写产品）。
2. **edge vs link**：旧实现 link→edge 投影（`expandLinks`），新设计必须保持 edge/link 解耦（ontology §2），否则语义判据无法成立。
3. **全展开 vs 默认**：全展开不得成为第二数据源（S0-8）；旧 `expandLinks` 行为只能作为兼容视图的极端参数，不得作为语义真相。
4. **"有边就渲染" vs present**：旧实现必须被 S0-6 判据替代；full_expand 也不得宣称"数据边=语义边"。

**U 映射**：U-1、U-16、U-27、U-33（映射不改变原话效力）。

**建议裁决**：冻结本表；四条标红冲突必须有 S6 的兼容/迁移/回滚方案后才可进入实现；新术语不得复用现有 group/edge 字段名造成歧义（建议 `semantic_cluster` / `view_model` / `present()` 作为研究侧新名）。

**证据等级**：A（现有代码/契约为准：`graph-engine.js:88-110`、`MemoriaGraphGroups`、ontology §2/§2.3）+ C（术语解释）。

---

## 附：本提案对 S0 章程硬验收的自检

| 预注册判据 | 本提案 |
|---|---|
| 每术语：定义/≥1 反例/≥1 边界用例/U 映射 | S0-1..S0-12 每项均有 ✅ |
| 两提案差异逐条列出并裁决（不许静默合并） | 待写完对照后写入 `S0-objections.md`（承诺不合并） |
| 与现有契约冲突处写兼容/迁移/回滚 | S0-12 四条标红 + S0-11 边界；具体方案留 S6 |
| 每项裁决有证据等级 | A/B/C/PI 逐项标注 ✅ |
| S0 相关 U 编号全出现 | §0 覆盖矩阵（S0 相关全部；其余场次标注） ✅ |

> **独立声明**：本文件写作时未读取 `S0-terms-proposal-A.md`（当时尚未落盘）；后续差异对照见 `S0-objections.md` 的「A/B 差异」节，逐项列而不合并。
