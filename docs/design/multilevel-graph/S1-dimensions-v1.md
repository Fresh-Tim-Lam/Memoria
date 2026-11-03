# S1 维度体系 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`（U-1..U-35）；`S1-charter.md`；`S1-RULINGS.md`；
> **上游冻结**：`S0-terms-v1.md`（sha `241b1e1e…`，不得违反）；`S0-FREEZE-RECORD.md`。
> **输入**：A-v2（sha `ae5f09e5…`）、B-v2（sha `c4cddcaf…`）、异议-v2（sha `275a2c7a…`）。
> **状态**：**冻结候选 v1**，待 SE 工程校核（task-297）与 Lead 独立机检后冻结；冻结前不写产品代码。
> **版本规则**：冻结后只允许「加维度/加关系源」（走 S1 修订 + 决策 + registry 版本）；删/改 H/A 核心规则必须重开 S1。

---

## 0. 一句话口径

维度 = 同一层次上的**取景规则**。v1 有两类：**H（层次导航维度）**沿层次划分逐层下钻，不参与关系扩展；**A（关联扩展维度）**沿 `E_relation` 关系边挂接邻居。2D/3D 与全展开都不是维度；维度切换属于 Presentation，不进 ViewModel。

## 1. 规范性条款（S1-1..S1-15）

### S1-1 维度定义与边界
- **规则**：维度是取景规则，判定 M1–M6：可计算、非粒度、非视觉风格、非展示模式、有注册项、不改事实。`graphStyle`/2D/3D/全展开/level 明确排除。
- **机检**：任何维度必须有 registry entry 且通过 M1–M6；无 registry entry 的取景请求 fail-closed。
- **来源**：A-v2 S1-1；B-v2 S1-1。

### S1-2 维度注册表 schema
- **规则**：entry 字段：`id/name/kind/basis/relation_sources/direction/hop_unit/hop_default/hop_max/termination/status/priority/version`；`kind ∈ {hierarchy_navigation, relation_expansion}` 且与 `basis.kind` 一致（**只保留 `kind` 一个规范字段**，`basis.kind` 为派生展示，不是第二个事实源）；`registry_sha` = 规范化 registry 的 sha256。
- **R-S1-9（冻结）**：`registry_history` 为**不可变 append-only 存储**：以 `content_sha` 为 id；每版条目**自包含** `version/relation_sources/active_dimensions/previous_sha/decision_id`；registry 带 `history_ref` 且末条 `content_sha == registry_sha`；validator **不需要外部旧 registry** 即可证明跨版本 `new⊇old`。
- **机检**：字段齐全/类型/枚举/默认值；未知 id、reserved、缺 min、H 方向非法、hop 非法、priority 重复、registry 坏、history 断链 ⇒ fail-closed。
- **来源**：A-v2 S1-2；B-v2 S1-2；R-S1-3；R-S1-9（Lead）。

### S1-3 开放槽位（U-25）
- **规则**：reserved 只登记（定义/草案/why_not_v1），**不得进渲染分支**；晋升需定义齐全 + 机检 + 需求 + 审批 + registry 版本升级；v1 不晋升。
- **机检**：reserved 维度出现在 frame/present 的 active 集合 ⇒ FAIL。
- **来源**：A-v2 S1-3；B-v2 S1-3。

### S1-4 H（层次导航维度）精确定义
- **规则**：`basis.kind=level_partition`、`relation_sources=[]`、`direction=down`、`hop_unit=n/a`、hop 无预算；一次下钻 = 一层；只沿层次划分下降；终止 = KP 叶子 / 无子块 / 用户取消。H 派生边必须带 `data_edge_ids`（R-S1-4）。
- **R-S1-11（冻结）**：H 派生边身份：`edge_id = sha256(canonical(parent_id, child_id, level, view_family))`；`data_edge_ids` = 该 (parent,child) 对应的**全部** `contain(structural)` 数据边 id（去重、排序、可枚举）；`expand_data_edges(H_vm)` = 所有 H 边 `data_edge_ids` 的并集，必须 ⊆ `DataSource.edges`；显示计数规则留 S3（S1 只要求集合语义）。
- **机检**：H entry `relation_sources=[]`；hop 字段为 null/n/a；每条 H 边有非空 `data_edge_ids` 且可映射；`expand_data_edges` 子集。
- **来源**：A-v2 S1-4；B-v2 S1-4；R-S1-1/2/4；R-S1-11（Lead）。

### S1-5 A（关联扩展维度）精确定义（U-10/U-30）
- **规则**：`basis.kind=relation_neighborhood`；`relation_sources ⊇ E_relation_min`（contain(structural/semantic)、reference、extend）；每条边 = 1 跳、不分类型；只挂接恰好一跳邻居；不闭包、不带背后图；label 仅标签。
- **R-S1-10（冻结）**：请求字段 `new_hop`（默认 false）；`hop_budget=2` **仅当** `new_hop=true` 且由 S5 的**唯一显式动作**设置；默认/自动路径禁止 2；`present/frame` 必须检查 `new_hop` 才允许 2 跳，否则 fail-closed。
- **机检**：A `relation_sources` 覆盖 min；`hop_default ≤ hop_max ≤ 2`；hop=2 时 `new_hop=true`；一跳端点集合只含 `kind∈{kp,cluster}`。
- **来源**：A-v2 S1-5；B-v2 S1-5；R-S1-5/10。

### S1-6 E_relation 扩展规则（只增不删）
- **规则**：只增不删（删/改名 ⇒ 重开 S0）；新增分 `edge_type/projection/derived` 三类 + 准入 E1–E7；v1 不新增；derived 不得进 active。
- **机检**：跨版本 `source_union(new) ⊇ old`（history 自包含）；删除/改名 ⇒ `S0_REOPEN_REQUIRED` 硬失败。
- **来源**：A-v2 S1-6；B-v2 S1-6；R-S1-3/9。

### S1-7 跳数
- **规则**：A 沿边计（`hop_unit=edge`，默认 1、最大 2）；最短距离 + 节点去重；跨维度切换重置为 default；超预算 → `presence=suppressed + rule_id(hop.budget/node.budget)`；H 无 hop。
- **机检**：见 S1-4/S1-5；截断必有 rule_id；同输入同输出（确定性）。
- **来源**：A-v2 S1-7；B-v2 S1-7；R-S1-5。

### S1-8 方向 `dir(D)`
- **规则**：`direction ∈ {down, up, both, out, in}`；H=down；A=both（可配 out/in）；方向只影响取景，不改事实/类型；非法 fail-closed。
- **机检**：枚举合法；H 非 down ⇒ FAIL；A 方向非法 ⇒ FAIL。
- **来源**：A-v2 S1-8；B-v2 S1-8。

### S1-9 终止条件
- **规则**：终止 = 层叶 ∨ hop_max ∨ max_nodes ∨ frontier 空 ∨ 用户取消；必须有穷（不得 null/∞）、确定性、截断可解释；`max_nodes` 数值归 S8（S1 只要求字段存在，示例值不具规范性）。
- **机检**：终止条件可枚举；不存在无限循环；截断带 rule_id。
- **来源**：A-v2 S1-9；B-v2 S1-9。

### S1-10 维度组合（D-5）
- **规则**：v1 单维度激活；组合只登记 reserved 槽位（`dimension_ids/order/composition_rule`）；`ctx` 出现组合参数 ⇒ `DIM_COMBINATION_UNSUPPORTED` fail-closed；切换语义见 S1-13。
- **机检**：v1 frame 的 `dimension_id` 单值；组合参数出现 ⇒ FAIL。
- **来源**：A-v2 S1-10；B-v2 S1-10；D-5。

### S1-11 状态机与能力闸
- **规则**：状态 `{reserved, active, deprecated}`；deprecated→active 只能经 S1 重开 + registry 版本 + history；registry 是版本化配置，不是事实源；插件不得注册/激活/改写维度。
- **机检**：状态转换表全覆盖；未知/保留/废弃维度 fail-closed；插件写入路径不存在。
- **来源**：A-v2 S1-11；B-v2 S1-11；R-S1-6。

### S1-12 维度与选择性渲染 / 边存无
- **规则**：维度经 `ctx.dimension_id` 进入 `present(e,ctx)`；只改 `presence`（shown/suppressed/unknown + rule_id），**不改 type/contain_kind/label**；视图缺席 ≠ 数据缺席；A 的关系边 presence 由 S1-5 规则决定；H 只渲染层次边。
- **机检**：presence 三值；type/label 不变；同数据不同维度不得改事实。
- **来源**：A-v2 S1-12；B-v2 S1-12；S0-6/S0-9。

### S1-13 维度与 UI/导航契约
- **规则**：切换属 Presentation/S5（新增 `VIEW_FRAME`、切换重置 hop）；ViewModel 只含 `dimension_id`，**不含**切换控件/列表/历史/模式（D-4）；渲染器只吃 VM；全展开是正交 Presentation 开关。
- **机检**：VM 字段无 mode/nav/dimension list；切换事件只在 Presentation 层。
- **来源**：A-v2 S1-13；B-v2 S1-13；D-4。

### S1-14 维度与 agent
- **规则**：agent 只能请求确定性取景服务 `frame(DataSource, frame_spec)`；`active` 白名单 + fail-closed（`DIM_UNKNOWN`/`DIM_NOT_ACTIVE`）+ 审计；不得改渲染状态/拼装 VM/写 registry；fallback 显式 + `fallback_reason`，registry `fallback_policy` 可 forbidden。
- **机检**：请求带审计；非法维度 fail-closed；agent 无写 registry/渲染状态路径。
- **来源**：A-v2 S1-14；B-v2 S1-14；R-S1-6。

### S1-15 其他维度候选（U-25）
- **规则**：reserved 候选：`time/evidence/task/controversy/authorship/similarity/path`（一句话定义 + 草案 + why_not_v1）；`density` 属 S2 簇算法参数，**不是维度**；`similarity` 若作派生关系源必须先走 S1-6 分类；v1 不晋升。
- **机检**：候选只在 reserved 表；density 不出现在维度注册表。
- **来源**：A-v2 S1-15；B-v2 S1-15；R-S1-7。

## 2. 跨议题裁决（R-S1-1..R-S1-11）

- **R-S1-1**：H 不参与关系扩展（`relation_sources=[]`）；R-1 只约束 relation_expansion 维度。
- **R-S1-2**：S0-5 的 one-hop 只约束 A；H 下钻不是关系跳，无 hop 预算。
- **R-S1-3**：E_relation 只增不删必须跨版本机检；删除/改名 ⇒ `S0_REOPEN_REQUIRED`。
- **R-S1-4**：H 派生边必须带 `data_edge_ids`。
- **R-S1-5**：A hop 默认 1/最大 2（2 仅显式「新一跳」）、沿边最短距离+去重、跨维重置、方向/终止可机检。
- **R-S1-6**：三态状态机；deprecated→active 只能重开 S1；agent fallback 显式+审计、可 forbidden；插件不得注册维度。
- **R-S1-7**：候选只登记 reserved；density 归 S2；similarity 派生源走 S1-6。
- **R-S1-8**：并集 A/B（A 的 M1–M6/E1–E7/H 细节 + B 的 history 自包含/new_hop/registry_sha）。
- **R-S1-9**：`registry_history` 不可变 append-only、条目自包含、registry 引用 history 尾、validator 不需外部旧 registry。
- **R-S1-10**：`new_hop` 请求字段；hop=2 仅由 S5 唯一显式动作设置；默认/自动禁止。
- **R-S1-11**：H 派生边 id/data_edge_ids/expand_data_edges 语义冻结（见 S1-4）。

## 3. 冻结前机检（SE，M-S1-1..M-S1-12）

M-S1-1 注册表 schema 与 fail-closed；M-S1-2 registry_history 链与自包含；M-S1-3 H kind/relation_sources/hop null；M-S1-4 A 覆盖 E_relation_min；M-S1-5 hop/new_hop/去重/重置；M-S1-6 方向枚举；M-S1-7 终止有穷+rule_id；M-S1-8 开放槽位不渲染；M-S1-9 三态/插件边界；M-S1-10 present 只改 presence；M-S1-11 VM 纯度；M-S1-12 U 覆盖矩阵 + 与 S0 无冲突 + 三图一致性（ER/DFD/状态图增量，同版本 mermaid 复验）。

## 4. 覆盖矩阵（U → 条款/场次）

| U# | 要点 | 落地 |
|---|---|---|
| U-8 | 层次可多层 = 层次维度 | S1-4；S5 |
| U-9/U-12 | 其他维度要设计 | S1-3/S1-15（reserved） |
| U-10 | 关联维度含包含/引用/语义关联 | S1-5（E_relation_min）；S1-6 |
| U-11 | 关联维度跳数 | S1-5/S1-7（默认1/最大2，new_hop） |
| U-25 | 其他维度先留开放槽位 | S1-3/S1-15 |
| U-26 | 默认替代+全展开开关 | S1-13（Presentation 正交） |
| U-30 | 关联维度具体定义 | S1-5 |
| U-32 | 规模不是问题、关键后端检索 | S1-9（预算字段）；S9 |
| U-33 | 2D/3D 是带接口渲染板块 | S1-13（不进维度/不进 VM） |
| U-34 | 逐议项/团队时间不设上限 | 章程 §5 / §6 变更控制 |
| U-35 | SE 专家 DFD/ER/状态图 | SE task-297；S5a/S6a/S9a |

## 5. 冻结后进入的下一场

S2（簇与子图划分：语义内聚、桥、多归属、稳定簇身份）；S2 不得改 S1 的维度/注册表规则。

## 6. 变更控制

- 冻结后加维度/加关系源：S1 修订 + 决策 + registry 版本/历史；
- 删/改 H/A 核心规则：重开 S1；
- 本文件冻结以 SE 的 M-S1-1..M-S1-12 全 PASS + Lead 独立机检为前置。
