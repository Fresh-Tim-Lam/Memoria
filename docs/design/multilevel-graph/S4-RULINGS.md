# S4 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S4-charter.md`；
> 上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）。
> **输入**：提案 A `S4-render-proposal-A.md`（`ba11c990…`）、提案 B `S4-render-proposal-B.md`（`4d3e0dd8…`）、`S4-objections.md`（`899c88f1…`）。
> **状态**：S4 **未冻结**；无 P0，3 条 P1（A）+ 1 条 P1（B）必修。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 A `one_hop(F)` 起点过宽 | 读 A S4-3/S4-2（F=基座集，tier2 从端点再走） | **成立**：若 F 是整层可见块，会从每个基座挂边，接近邻域展开，违反 S0-5/U-17；必须冻结 F={focus} |
| P1-2 A tier2 引入 2 跳 | 读 A S4-2（tier2=与 tier0/1 相邻） | **成立**：默认视图可能闭包；必须 `max_hop(shown) ≤ hop_budget` |
| P1-3 A tier0 必选 + 预算不足整屏失败 | 读 A S4-2/S4-9 与 S3 默认 200 | **成立**：层可见块>200 会整屏失败；必须最小必选集 + 其余 suppressed |
| P1-4 B VM 只含 shown 无 rule_id 载体 | 读 B S4-9 与 S3-12/S0-6 | **成立**：候选边需逐条 presence/rule_id；采用 A 候选边模型 |
| 其余点名 | 唯一裁剪者/Renderer 不裁剪/维度边界/S5 边界/S1-S2/G6 | 全 PASS；P2 合并进修订 |

## 1. 跨议题裁决（R-S4-1..R-S4-8）

### R-S4-1 一跳起点（P1-1）
- **裁决（冻结）**：默认视图 `one_hop` 的基座集 **F = {focus}**（单焦点；cluster 焦点即该簇节点）；不得用"整层可见块"作 F。`one_hop(F) = {v | ∃e∈E_relation(D): e 连接 F 与 v，且 v 不在 F}`，每端点最多一条边进入；不闭包、不带背后图。
- **机检**：`base(F) == {focus}`；`max_hop(shown) == 1`（默认）；端点仅 kp/cluster；无闭包边。
- **理由**：S0-5/U-17 冻结「一跳」语义；整层基座会变成邻域展开。

### R-S4-2 禁止隐式第二跳（P1-2）
- **裁决（冻结）**：tier2 只能包含**基座（focus）本身 + H 结构同层节点**，不得包含"一跳端点的邻居"；所有 `shown` 候选 `hop ≤ hop_budget`（默认 1）；2 跳只能由 S5 `EXPLICIT_NEW_HOP`（`new_hop=true`）触发，S4 默认路径不得产生。
- **机检**：`max_hop(shown) ≤ hop_budget`；默认 `hop_budget=1`；2 跳候选只有在 `new_hop=true` 时存在。
- **理由**：U-18/U-22；防止默认视图悄悄闭包。

### R-S4-3 最小必选集与预算降级（P1-3）
- **裁决（冻结）**：`MANDATORY = {focus} ∪ (focus 的必要显示上下文：当前层块/簇徽标所需的最小集合)`（公式显式、数量有上限）；预算内先保证 MANDATORY；其余按优先级 `suppressed + rule_id`；**只有 MANDATORY 本身超预算**才 `S4_BUDGET_INVALID` fail-visible；S8 必须保证 `max_nodes ≥ |MANDATORY|` 上界。
- **机检**：MANDATORY 可枚举；超预算时先抑制非必选；仅必选超预算才失败；无静默丢。
- **理由**：可用降级优先于整屏失败；同时不违反 S3 硬上限。

### R-S4-4 VM 候选边载体（P1-4）
- **裁决（冻结）**：VM 必须携带**全部候选节点/边**及其逐条 `presence ∈ {shown,suppressed,unknown}` + `rule_id`（A 模型）；Renderer 只渲染 `shown`；`suppressed/unknown` 保留供审计/度量；B 的"VM 只含 shown"作废。
- **机检**：候选集完整；每条有 presence+rule_id；Renderer 输入只使用 shown。
- **理由**：S3-12/S0-6 要求逐条 presence/rule_id；否则无法解释"为什么这条边没出现"。

### R-S4-5 rule_id 枚举与 unknown 触发
- **裁决**：统一 A 的 11 类 `rule_id`（`dimension.sources/direction/level/hop/budget/cluster.folded/endpoint.unresolved/source.unavailable/admission.undecided/invalid.data`）；`unknown` 仅在 `source.unavailable/endpoint.unresolved/admission.undecided/invalid.data` 出现，**不等于**"无关系"；`suppressed` 是已知但取景不显示。
- **机检**：枚举闭合；unknown/suppressed 语义分离。

### R-S4-6 选点排序（tie-break）
- **裁决**：排序键冻结 `(tier, hop, relation_class, label_rank, canonical_id)`；`relation_class` 顺序 = semantic < structural < navigation < reference（reference 最后，不参与内聚/桥）；`label_rank` 取确定性字符串序；同输入同结果。
- **机检**：排序键可复算；两次运行一致。

### R-S4-7 全展开
- **裁决**：全展开与默认走**同一 Admission/present**；`relation_scope=candidate_scope`（不是 raw data edges 直出，P2-1 措辞修正）；`shown(default) ⊆ shown(full)`；full 仍受 S8 硬上限，超限显式失败/降级；不得第二数据源。
- **机检**：subset；同源；full 预算路径。

### R-S4-8 P2 并集
- A 的候选边模型/rule_id 表/G6 指标/全展开 subset 为主干；B 的 focus 一跳/VM 严格性/无 tier0 失败并入；
- `aggregate_count` 不遍历 `data_edge_ids`；G6 字段统一；unknown 触发面按 R-S4-5；S1 F 定义同步（S4 只引用 S1）。

## 2. 修订轮任务

**A-v2**：落实 R-S4-1..R-S4-8；更新 `S4-render-proposal-A-v2.md` + 变更表。
**B-v2**：落实 R-S4-1..R-S4-8（focus 一跳/候选边模型/最小必选集/排序键/rule_id 统一）；产出 `S4-render-proposal-B-v2.md` + `S4-objections-v2.md`。
**SE 工程校核（task-312）**：等 v2 齐后执行。

## 3. S4 冻结门禁

1. A-v2/B-v2 关闭全部 R-S4 与 P1（逐条证据）；
2. SE 工程校核 PASS；
3. Lead 独立机检（focus 一跳、无隐式 2 跳、最小必选、候选边 presence/rule_id、排序键、全展开 subset、VM 纯度）；
4. 与 S0/S1/S2/S3 无冲突；
5. 冻结 `S4-render-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0–S3 冻结稿；S4 冻结前不开工实现；所有修订保留旧版。
