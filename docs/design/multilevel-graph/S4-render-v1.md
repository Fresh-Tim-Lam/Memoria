# S4 选择性渲染 / 一跳 / 边「存无」 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`；`S4-charter.md`；`S4-RULINGS.md`。
> **上游冻结**：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`（节点 presence/rule_id 白名单扩展）——不得违反。
> **输入**：A-v2（`634cb9cf…`）、B-v2（`048b9909…`）、异议-v2（`a8f10629…`）。
> **状态**：冻结候选 v1，待 SE 工程校核（task-312）与 Lead 独立机检后冻结；冻结前不写产品代码。

---

## 0. 一句话口径

默认视图只显示 **focus 的一跳**（`F={focus}`，恰好一条语义关系边），**不闭包、不带背后图**；预算内先保**最小必选集**，其余候选逐条 `suppressed+rule_id`；每条候选边/节点都有 `presence+rule_id`；全展开与默认走同一 `present` 且**构造性保证** `shown(default) ⊆ shown(full)`。

## 1. 规范性条款（S4-1..S4-12）

### S4-1 定义与唯一裁剪者
- **规则**：S4 = Admission 层，是 `presence ∈ {shown, suppressed, unknown}` 的**唯一裁剪者**；只改取景，不改事实/type/label/contain_kind；Renderer 只校验/渲染已选 VM（S3 R-S3-2）；旧「有边就画」被替代。
- **机检**：只有 S4 产生 presence；Renderer 无裁剪逻辑；事实字段与 DataSource 一致。
- **来源**：A-v2 S4-1；B-v2 S4-1。

### S4-2 预算选点与排序
- **规则**：`max_nodes/max_edges`（S8 定值，S3 冻结字段）；排序键冻结 `(tier, hop, relation_class, label_rank, canonical_id)`，`relation_class = semantic < structural < navigation < reference`；同输入同结果；超预算非必选项 `suppressed + rule_id`。
- **机检**：排序可复算；两次运行 presence 相同；无静默截断。
- **来源**：A-v2 S4-2；B-v2 S4-2；R-S4-6。

### S4-3 一跳（focus-only）
- **规则**：默认 `one_hop` 基座集 **F={focus}**（cluster 焦点即该簇节点）；`one_hop(F) = {v | ∃e ∈ E_relation(D) 连接 F 与 v，v∉F}`；每端点最多一条边进入；不闭包、不带背后图。
- **机检**：`base(F)=={focus}`；默认 `max_hop(shown)==1`；端点 `kind∈{kp,cluster}`；无闭包边。
- **来源**：A-v2 S4-3；B-v2 S4-3；R-S4-1。

### S4-4 禁止隐式第二跳
- **规则**：tier2 只含基座（focus）+ H 结构同层节点，**不得含一跳端点的邻居**；所有 `shown` 候选 `hop ≤ hop_budget`（默认 1）；2 跳只能由 S5 `EXPLICIT_NEW_HOP`（`new_hop=true`）触发。
- **机检**：`max_hop(shown) ≤ hop_budget`；默认无 2 跳候选；`new_hop` 仅 S5。
- **来源**：A-v2 S4-2/S4-5；B-v2 S4-2/S4-3；R-S4-2。

### S4-5 最小必选集与预算降级
- **规则**：`MANDATORY` 公式冻结：A 维 `{focus}`；H 维 `{focus} ∪ first K children(focus)`；v1 `K = MANDATORY_CONTEXT_CAP = 2`（S8 可调，上界 1+K）；预算内先保 MANDATORY；其余 `suppressed+rule_id`；**仅 MANDATORY 超预算**才 `S4_BUDGET_INVALID` fail-visible；S8 必须保证 `max_nodes ≥ 1 + MANDATORY_CONTEXT_CAP`。
- **机检**：MANDATORY 可枚举、≤ cap；超预算先抑制非必选；仅必选超预算失败。
- **来源**：A-v2 S4-2；B-v2 S4-2；R-S4-3；S4 v2 P1-3 统一。

### S4-6 边「存无」三值
- **规则**：`presence ∈ {shown, suppressed, unknown}`；`rule_id` 11 类统一：`dimension.sources / dimension.direction / dimension.level.cross_layer / hop.budget / node.budget / edge.budget / cluster.folded / endpoint.unresolved / source.unavailable / admission.undecided / invalid.data`；`unknown` 仅由后 4 类触发（`endpoint.unresolved/source.unavailable/admission.undecided/invalid.data`）；**unknown ≠ 无关系**；类型独立判定。
- **机检**：枚举闭合；unknown 触发面；unknown/suppressed 语义分离。
- **来源**：A-v2 S4-4；B-v2 S4-4；R-S4-5。

### S4-7 维度接入
- **规则**：`frame_spec.dimension_id` 解析 S1；H=无 hop/contain 下钻；A=E_relation_min/hop 1-2；维度只改 presence；未知/保留维度 fail-closed（S1）。
- **机检**：未知维度无输出；presence 改变但事实不变。
- **来源**：A-v2 S4-6；B-v2 S4-6。

### S4-8 层次与 drill
- **规则**：drill = 新 frame（level+1、focus=簇、hop 重置）；S4 只读 S2 run、不重算簇；跨层非 H 边 `dimension.level.cross_layer` suppressed；多归属按当前 `view_family`。
- **机检**：drill 后 hop 重置；无重算簇；跨层边规则。
- **来源**：A-v2 S4-7；B-v2 S4-7。

### S4-9 全展开与 subset 构造保证
- **规则**：全展开与默认走**同一 Admission/present**；`relation_scope = candidate_scope`（不是 raw data edges 直出）；**构造性保证 subset** 需同时满足两个前提：① **`candidates(full) ⊇ candidates(default)`**（full 的 candidate_scope 必须覆盖 default 的全部候选；若数据源/查询不能保证该超集，⇒ `S4_BUDGET_INVALID` 或**显式回退 default**，不得静默补入）；② full 先把 `shown(default)` 作为 **reserved** 全部保留，再按同一排序填剩余预算；要求 `budget_full ≥ budget_default`；因此 `shown(default) ⊆ shown(full)` 由构造保证，而非事后断言；full 仍受 S8 硬上限，无第二数据源。
- **R-S4-7（冻结）**：subset 是构造性质，机检必须同时验证：`candidates(full) ⊇ candidates(default)`、`reserved(full) == shown(default)`、`budget_full ≥ budget_default`、无第二数据源。
- **R-S4-9（冻结）**：full 的候选超集前提不成立 ⇒ `S4_BUDGET_INVALID` 或显式回退 default（两种都必须可见，禁止静默）。
- **来源**：A-v2 S4-8；B-v2 S4-8；R-S4-7；S4 v2 P1-1。

### S4-10 VM 载体与 S3 兼容
- **规则**：AdmissionResult 携带**全部候选节点/边**的逐条 `presence+rule_id`；VM 按 S3 白名单投影；`S3-ADDENDUM-1` 将节点白名单扩展为含 `presence?/rule_id?`（view-status 字段，不改变 S3 核心规则）——因此 VM 节点/边都可带 presence+rule_id；Renderer 只渲染 `shown`；`data_edge_ids` 仍只审计、Renderer 禁读。
- **机检**：候选完整性；VM schema 含 node/edge presence/rule_id；Renderer 只读 shown。
- **来源**：A-v2 S4-9；B-v2 S4-9；R-S4-4；S3-ADDENDUM-1。

### S4-11 与 S5 边界
- **规则**：S4 是纯取景函数；focus/selection/navigation 不进 VM；事件→S5；`new_hop` 仅 S5；S4 无导航状态机。
- **机检**：VM 无导航字段；S4 无状态机。
- **来源**：A-v2 S4-10；B-v2 S4-10。

### S4-12 与 S1/S2 一致性 + 度量
- **规则**：presence 不改 type/label/contain_kind；A 不改变簇；run/簇不进 VM；多归属按 `view_family`；无簇不伪造/不注入结构边（S2-12）；G6 指标：candidate/mandatory/shown 计数、rule_id 直方图、`max_hop`、closure/behind 违规=0、deterministic sha、subset_ok、budget 状态、candidate_scope；数值门禁 S8。
- **机检**：事实不变；G6 可复跑；closure/behind 违规 0。
- **来源**：A-v2 S4-11/S4-12；B-v2 S4-11/S4-12。

## 2. 跨议题裁决（R-S4-1..R-S4-10）

- R-S4-1 F={focus}；R-S4-2 无隐式 2 跳；R-S4-3 最小必选集；R-S4-4 候选边/节点 presence 载体；R-S4-5 rule_id/unknown；R-S4-6 排序键；R-S4-7 全展开 candidate_scope；R-S4-8 并集。
- **R-S4-9（subset 构造）**：full reserved(shown(default)) + fill；`budget_full ≥ budget_default`；subset 由构造保证。
- **R-S4-10（MANDATORY 统一）**：A={focus}；H={focus}+first K children；v1 `K=2`；S8 保证 `max_nodes ≥ 1+K`；S8 可调 K。
- **S3-ADDENDUM-1**：S3 VM 节点白名单增加 `presence?/rule_id?`（仅 view-status；S3 核心规则不变；按 S3 变更控制以修订+决策记录）。

## 3. 冻结前机检（SE，M-S4-1..M-S4-12）

M-S4-1 唯一裁剪者；M-S4-2 排序/预算；M-S4-3 focus 一跳；M-S4-4 无隐式 2 跳；M-S4-5 最小必选集/降级；M-S4-6 presence/rule_id/unknown；M-S4-7 维度接入；M-S4-8 drill/跨层；M-S4-9 全展开 subset 构造；M-S4-10 VM 载体/S3 addendum；M-S4-11 S5 边界；M-S4-12 与 S1/S2 一致 + G6 + 工程图增量（mermaid 同版本）。

## 4. 覆盖矩阵（U → 条款）

| U# | 要点 | 落地 |
|---|---|---|
| U-5 | 默认非全展开、不是所有节点 | S4-2/S4-3/S4-5 |
| U-15 | 深入后经语义边挂接一跳 | S4-3/S4-4；S1/S5 |
| U-16 | 旧版两端都渲染 vs 选择性渲染 | S4-1/S4-9 |
| U-17 | 一跳背后图不自动带入 | S4-3/S4-4 |
| U-18 | 挂接一跳、避免多跳污染 | S4-4 |
| U-19 | 一跳节点可为 KP/簇 | S4-3 |
| U-21 | 多归属 | S4-8/S4-12 |
| U-22 | 新一跳 vs 跳更深 | S4-4（S5 显式） |
| U-27 | 边存无/类型不同 | S4-6 |
| U-28 | 2D/3D 同一接口 | S3-6；S4-10 |
| U-31 | 多归属/不设上限 | S2-6；S4-8 |

## 5. 冻结后进入的下一场

S5（导航状态机：click/drill/back/new-hop/focus 生命周期）；S5 必须复用 S4 的 `frame_spec`/presence 契约，不得改 S4 的一跳/预算规则。

## 6. 变更控制

- 加 rule_id/优先级/阈值：S4 修订 + 决策；删/改一跳/预算归属/subset/presence 语义：重开 S4；
- S3 节点白名单扩展按 `S3-ADDENDUM-1` 记录，不改 S3 核心规则。
