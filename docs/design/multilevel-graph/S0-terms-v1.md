# S0 术语与边界 · 冻结稿 v1（候选）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35，两轮原话）；`S0-charter.md`；
> `S0-RULINGS.md`（Lead 第一轮裁决）；`S0-terms-proposal-A-v2.md`；`S0-terms-proposal-B-v2.md`；
> `S0-objections-v2.md`；`S0-engineering-review.md`；`ENGINEERING-PLAN.md`。
> **状态**：**冻结候选 v1**。待 SE 按 M-1..M-12 机检（task-294）与 Lead 终审后，本文件即 S0 冻结稿；
> 冻结前不得进入 S1，不得写产品代码。
> **版本规则**：冻结后只允许「加条款」（新增 U 覆盖或澄清），删除/改写 S0 规则必须**重开 S0**。
> **证据链**：每条款的**反例 / 边界用例 / U 映射细节**见 `S0-terms-proposal-A-v2.md` 与 `S0-terms-proposal-B-v2.md` 对应章节；本文件只写规范性条款。

---

## 0. 一句话口径

图谱 = **语义**的多层次、多维度视图：默认入口用「代表语义内聚小群的簇节点」逐层深入，**选择性渲染**当前层/维/跳数内该显示的东西；**边的「存无」与类型本身是语义**，不是"数据里有边就画"；2D/3D 只是同一渲染接口的两个实现后端。

## 1. 规范性条款（S0-1..S0-12）

> 每条：**规则**（冻结）/ **机检**（能自动化的写条件）/ **来源**。冲突时以本条 + §2 裁决为准。

### S0-1 语义（semantic）

- **规则**：语义边 = 满足 T1（可命名）+ T2（可真假）+ T4（非偶然）**且**通过字段闸门 `G_sem` 的断言。
  `G_sem`：`reference` 不算语义；`contain_kind=semantic` 需 `assertion_source` + `curated_by/curated_at`（复用 v0.3 `validate_contain_curation_overlay`）；`extend` 按作者断言/证据判定。标签三类：`semantic / structural / navigation`，**标签不是取景开关**。T3「决策绑定」不是语义定义条件，只作**消费者准入清单 C-1..C-4**（S7/S8 评测门槛）。
- **机检**：`semantic_edge(e) ⇒ T1∧T2∧T4∧G_sem(e)`；`reference ⇒ ¬semantic_edge`；标签与 `E_relation` 解耦（见 S0-3）。
- **来源**：A-v2 §1；B-v2 S0-1；RULINGS P1-3。

### S0-2 层次与最小粒度（level）

- **规则**：层次 = 同一视图族内的**嵌套划分** Π_ℓ（L0 全库簇 → … → L_L 单 KP）。**最小节点粒度 = 知识点**（U-28）。更深层（句/断言/概念）只登记**开放槽位**，不是 v1 层次。partition 约束只在**同一 `(level, view_family)`**；跨视图族/维度允许重叠（对接 S0-7）。
- **机检**（`validate_level_view`，V1–V6，fail-closed）：
  - V1 每个非叶节点 `kind=cluster`；V2 每个叶节点 `kind=kp` 且 `id ∈ K`（collector KP 集）；V3 cluster 成员非空；V4 无 `cluster` 叶节点；V5 同一 `(level, view_family)` 内成员集合互不相交且并集=该层全集；V6 `expand_cluster_to_kp` 递归展开到底全为 KP。
- **来源**：A-v2 §2；B-v2 S0-2；RULINGS P1-1；SE M-2。

### S0-3 维度（dimension）与 E_relation

- **规则**：维度 = 同一层次上的**取景规则**（决定取哪些关系源、方向、扩展步数），不是粒度、不是视觉风格。v1 可用维度：`H`（层次维）与 `A`（关联维），**同一视图一次只激活一个维度**（D-5）；其余**开放槽位**（reserved：只登记、不得进渲染分支，切换必须 fail-closed）。**关联维度挂接/计跳边 = `E_relation(D)`，与语义标签无关**（U-10）。
- **R-1（冻结）**：`E_relation_min = {contain(structural), contain(semantic), reference, extend}`。**S1 只能加不能删**；任何删除必须重开 S0。`semantic/structural` 仅标签，不是 `E_relation` 过滤条件。
- **R-2（冻结）**：`view_family = ⟨family_id, basis, dimension_id, level_chain⟩`；partition 断言的对象是 `(level, view_family)`，不是 `(level, dimension)`。
- **机检**：`reserved` 维度出现渲染分支 ⇒ FAIL；`E_relation(D) ⊇ E_relation_min`；未知 dimension_id fail-closed；v1 同时只激活一个维度。
- **来源**：A-v2 §3；B-v2 S0-3；RULINGS P0-1/D-5；B-v2 未决 1/2（Lead 冻结为 R-1/R-2）。

### S0-4 簇（cluster）

- **规则**：簇 = 语义内聚度高（μ≥τ_coh）且与外部只有零星桥（β≤τ_bridge）的成员集合；**不是**严格连通分量（U-13/U-14）。簇是**视图节点**，不回写 KP。身份按 D-2：`cluster_instance_id = (cluster_run_id, cluster_local_seq)`（run-scoped）；`cluster_key = sha256(canonical(sorted(member_canonical_ids)) + algorithm_id + version + params_hash)`（可复算/去重）。curation/审计引用必须同时记录 run 与 key。
- **机检**：`cluster_key` 可复算；`cluster_instance_id` 唯一；`cluster.members ⊆ K`；同一簇的 `μ/β` 可按 S2 参数复算。
- **来源**：A-v2 §4；B-v2 S0-4；D-2；RULINGS P1-4。

### S0-5 一跳（one hop）

- **规则**：当前视图只挂接**恰好一条** `E_relation(D)` 边的邻居；**不闭包**、不递归；跨维度时跳数重置。**方向 `dir(D)`**：H 维度 = `down`（外层→内层）；A 维度 = `both`（可配置，S1 细化，但不得默认闭包）。只渲染「端点 + 这条边」，**不带端点背后的子图**（U-17）；挂接节点只能是 `kind∈{kp,cluster}`；`bridge` 只能是 node `role`/edge `state`。
- **机检**：视图边数 ≤ |F| × hop_budget；`hop=1` 时不存在二跳边；`dir` 枚举合法；bridge 不出现在 `kind`。
- **后续项（非阻塞）**：`underlying_hop_count` 与 `HopNetwork` 状态细节由 S4/S5 定义（O-7/O-8）。
- **来源**：A-v2 §5；B-v2 S0-5；RULINGS P0-2；D-5。

### S0-6 选择性渲染与「边存无/类型」（presence）

- **规则**：渲染集合 = `{e | present(e, ctx) == shown}`，**唯一判据**。`ctx` 至少含 `(level, view_family, dimension_id, focus, hop_budget, mode)`。`presence ∈ {shown, suppressed, unknown}`；`suppressed/unknown` 必须带 `rule_id`（可枚举）。**视图缺席 ≠ 数据缺席**（U-27）。默认视图与全展开**同源同 present**：`ctx_full` 也走 `present`，不得 `all_data_edges` 直出。
- **R-3（冻结）**：聚合/折叠边必须携带 `data_edge_ids`（映射回 DataSource 边）；机检 `expand_data_edges(VM) ⊆ DataSource.edges`，且 `shown(default) ⊆ shown(full)`。
- **机检**：渲染集合恒等式；`suppressed/unknown` 必有 `rule_id`；`expand_data_edges` 子集；`ctx_full` 不绕过 present。
- **来源**：A-v2 §6/§8；B-v2 S0-6/S0-8；SE S0-6；RULINGS P1-2；B-v2 未决 3（R-3）。

### S0-7 多归属（membership）

- **规则**：成员关系 ≠ 视图出现。`membership` 多对多；**同一视图族内单归属**（partition），跨视图族/层次/维度**允许重叠**（U-21）；S0 **不设上限**（S2/S6 定）。Membership 记 `role/source/provenance`（A-v2），但**不得**写入产品 sidecar/新段（D-3）。
- **机检**：同 `(level, view_family)` 内成员唯一；跨族重叠允许；`view_presence` 与 `membership` 分开断言。
- **来源**：A-v2 §7；B-v2 S0-7；RULINGS P1-1/D-1/D-3。

### S0-8 默认视图 vs 全展开

- **规则**：默认入口 = 层次视图，**彻底替代**旧全展开（U-26）；全展开是 Presentation 层正交开关，**同 DataSource、同 Renderer、同 present**，仅 `ctx` 不同；焦点与历史在切换时映射保持（A-v2）。禁止第二数据源/双主线。
- **机检**：`source(default) == source(full)`；`shown(default) ⊆ shown(full)`；切换前后焦点映射表非空；无第二 builder。
- **来源**：A-v2 §8；B-v2 S0-8；RULINGS P1-2。

### S0-9 渲染接口（单一契约，2D/3D 后端）

- **规则**：`DataSource → ViewModel → Renderer` 三段；**ViewModel 纯**：`nodes/edges/level/dimension/view_family/presence 等`，**不含导航状态、模式开关、capabilities**（`capabilities` 由 `Renderer.getCapabilities()` 提供，D-4）。节点 `kind ∈ {kp, cluster}`；桥只能 `role/state`。渲染器**不取数、不做语义判断、不写状态**；事件最小集：`nodeClick(node_id, kind)`、`edgeClick(edge_id)`、`backgroundClick()`（hover/clusterExpand 等为可选，S3/S5 定）。2D/3D 实现同一接口（U-33），**不是两条设计线**。
- **机检**：VM 无 `mode/nav/capabilities` 字段；`kind` 枚举；renderer 不 import DataSource/DB；2D/3D 接口签名一致。
- **来源**：A-v2 §9；B-v2 S0-9；D-4；RULINGS P0-2；B-v2 P2（capabilities 移出 VM，Lead 采纳）。

### S0-10 agent 边界

- **规则**：三层职责——`L_kp`：agent **主导**设计知识点（S10 细化）；`L_sem`：agent 可写语义，但**必须带证据锚 + 审计**（`curated_by/curated_at`），**不得自动推断 semantic**；`L_view`：agent 只能请求取景服务，**不得直接改渲染状态**。取景由**确定性服务**生成（同输入同输出），agent 不拼装视图数据。
- **机检**：semantic 写入必带证据/审计（v0.3 validator）；取景服务纯函数（无会话态）；renderer 状态只能由 UI 事件/导航服务改。
- **来源**：A-v2 §10；B-v2 S0-10；U-29/U-32。

### S0-11 v1 不做什么（范围外）

1) 词/句级作为节点/层次；2) 跨库图谱；3) 时间维作为 v1 激活维度；4) 自动改写用户正文；5) 自动推断 semantic；6) 新增语义边类型（v1 只用现有三类）；7) 2D/3D 双设计线；8) 全展开作为默认；9) 渲染器直接读库/取数；10) 把「视图出现」当成员关系；11) 无审计的批量 semantic 写入；12) 在 S0 决定簇算法/检索算法/性能参数（这些分别由 S2/S9/S8 决定）；13) 复用 `graph-groups`（并查集严格连通分量）当簇；14) 把簇/成员关系写入产品 sidecar 或新增产品段（D-3）；15) 导航状态塞进 ViewModel。
> 每条的**执行点/机检**见 A-v2 §11 与 B-v2 S0-11；S1–S10 负责细化，不得扩大 v1 范围。

### S0-12 术语映射

- **规则**：新术语 ↔ 现有产品术语一一映射（KP、edge、link、contain_kind、provenance、graph view、graph-groups、graphStyle、2D/3D）；冲突项必须写**兼容/迁移/回滚**。三段：`DataSource（collect_graph_data + curation overlay）→ ViewModel（纯）→ Renderer（2D/3D 实现）`。**旧 `graph-groups` ≠ 簇**；**`reference` ≠ 语义**；**视图缺席 ≠ 数据缺席**；**2D/3D 是后端**。
- **映射表**：见 A-v2 §12（16 组）与 B-v2 §12（三段）并集；关键红线：`graph-groups ≠ 簇`、`reference ≠ 语义`、`视图缺席 ≠ 数据缺席`、`2D/3D = 同一接口的两个后端`、`graphStyle ≠ 维度`。
- **机检**：映射表无空项；冲突项有迁移/回滚；术语在 S1–S10 引用同一 id。

## 2. 跨议题裁决（R-1..R-3 + D-1..D-5）

- **R-1**：`E_relation_min` 冻结（S0 不得删；S1 只能加）。
- **R-2**：`view_family` 唯一定义（S0-3）；partition 断言对象 `(level, view_family)`。
- **R-3**：聚合/折叠边必须 `data_edge_ids`；`expand_data_edges(VM) ⊆ DataSource.edges`；`shown(default) ⊆ shown(full)`。
- **D-1**：partition 作用域 = 视图族内；跨族/维度多归属允许。
- **D-2**：簇身份 = run-scoped id + `cluster_key`（内容哈希不作实例 id）。
- **D-3**：S0 不写簇/成员到产品 sidecar/新段；semantic overlay 走 v0.3。
- **D-4**：ViewModel 纯；导航/模式/capabilities 不进 VM。
- **D-5**：v1 单维度激活；组合留开放槽位。

## 3. 冻结前机检（SE M-1..M-12，逐项必须 PASS）

M-1 术语三要素；M-2 层次划分机检；M-3 维度/E_relation_min；M-4 簇 μ/β + 身份；M-5 一跳/方向/跨维重置；M-6 present 三值 + ctx + rule_id；M-7 多归属/partition；M-8 同源与 default⊆full；M-9 ViewModel 纯度与 kind 枚举；M-10 agent 边界（证据/审计/取数）；M-11 U-1..U-35 覆盖 0 缺失；M-12 三张工程图（ER/DFD/状态图）与 S0 条款一致（mermaid 同版本复验）。


## 4. 覆盖矩阵（U-1..U-35 → 条款 / 场次；本表冻结）

> 本表为 vision §2 要求的覆盖矩阵。来源：A-v2 §13 + B-v2 §0.1 并集。
> 反例 / 边界用例 / 详细 U 映射见 A-v2 / B-v2 对应章节；本表只做**覆盖登记**，不重复内容。

| U# | 要点 | 落地条款 / 场次 |
|---|---|---|
| U-1 | 图谱最重要的是语义 | S0-1；贯穿 S1–S10 |
| U-2 | 前端让人真想用 + 后端给 agent 增效 | S0-10；S7/S8 |
| U-3 | 不要海量节点+错综连线 | S0-6/S0-8；S3/S4 |
| U-4 | 要考虑多层次 | S0-2；S1/S2/S3 |
| U-5 | 非全展开默认；节点不再是最小粒度 KP | S0-2/S0-8；S3/S4 |
| U-6 | 簇节点代表连通子图、外观更大 | S0-4；S3 |
| U-7 | 点击 → 图谱区域切换子图 = 深入一层 | S5（S0 已定粒度/簇） |
| U-8 | 层次可以很多层 = 层次维度 | S0-2/S0-3；S1 |
| U-9 | 其他维度也要设计 | S0-3（开放槽位）；S1 |
| U-10 | 关联维度：包含/引用/语义关联 | S0-3/S0-5（E_relation_min，R-1）；S1/S4 |
| U-11 | 关联维度跳数 | S0-5；S4 |
| U-12 | 更多维度 | S0-3（开放槽位）；S1 |
| U-13 | 不是严格连通子图：内聚高+零星桥 | S0-4；S2 |
| U-14 | 按语义关系划分小群 | S0-4；S2 |
| U-15 | 深入后经语义边挂接一跳 | S0-5；S4/S5 |
| U-16 | 旧版两端都渲染；新设计选择性渲染 | S0-6；S4 |
| U-17 | 一跳背后图不一定与本图有语义关系 | S0-5/S0-6；S4/S5 |
| U-18 | 挂接一跳避免多跳污染 | S0-5；S4 |
| U-19 | 一跳节点可为 KP/簇节点 | S0-9（kind∈{kp,cluster}）；S5 |
| U-20 | KP 点击仍跳编辑器 | S0-9（nodeClick 事件）+ S5（跳编辑器执行） |
| U-21 | 多归属（不同子图/层次/维度） | S0-7（多对多）；S2/S6 |
| U-22 | 进入关联网"新一跳" vs 跳更深 | S5（S0 已定跳数/方向契约） |
| U-23 | 覆盖不足重开研讨会 | §6 变更控制；本矩阵 |
| U-24 | 原话存档「供起来」 | `multilevel-graph-vision.md`（文件整体） |
| U-25 | 其他维度先留开放槽位 | S0-3；S1 |
| U-26 | 默认彻底替代；保留开关全展开 | S0-8；S3/S4 |
| U-27 | 边有「存无」「类型」不同 | S0-6（presence 三值 + ctx + rule_id） |
| U-28 | 最深层次待研讨；最小粒度=知识点 | S0-2（已定最小粒度）；S1/S10 定更深层 |
| U-29 | 关键：agent 怎么设计知识点 | S0-10；S10 |
| U-30 | 关联维度具体定义与设计 | S0-3/S0-5；S1/S4 |
| U-31 | 多归属先定义；或不上限 | S0-7（不设上限）；S2/S6 |
| U-32 | 规模不是问题；关键后端检索算法 | S0-10；S9 |
| U-33 | 2D/3D 不分家，是带接口的渲染板块 | S0-9（单一接口 + 双后端） |
| U-34 | 逐议项、团队/时间不设上限 | `S0-charter.md` §3/§5 + agenda §5；§6 只作变更控制 |
| U-35 | 招聘 SE 专家做 DFD/ER/状态图 | 已聘（graph-se-architect）；S5a/S6a/S9a |

## 5. 冻结后进入的下一场（不在本文件裁决）

S1 维度体系（含 E_relation 扩展、维度组合、开放槽位登记）；S2 簇算法/稳定性；S9 后端检索；S10 agent 设计 KP。S0 冻结前，S1 不得开。

## 6. 变更控制

- 冻结后新增条款：追加 §1.x + 覆盖矩阵 + 决策记录；
- 删除/改写 S0 条款：重开 S0（记录原因/影响/回滚），不得在 S1+ 私改；
- 本文件冻结时以 `S0-freeze-check.md` 全 PASS 为前置。
