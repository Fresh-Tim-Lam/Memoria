# S4 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`），不得违反；`S4-charter.md`。
> **对象**：`S4-render-proposal-A.md`（主办研究，sha **`ba11c990736a9ea982fb24c89b553fd3e48610c7f4d2dc9f9ab432f54213e74d`**，27,735 B）与 `S4-render-proposal-B.md`（本复核方，sha **`4d3e0dd8b8a5355abdf73ae05ff9fd921e650df61bd2d271ee104bb1d72c6226`**，19,218 B）。
> **独立性**：B 于 20:46:25 落盘，A 于 20:47:52 才出现；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0/S1/S2/S3 冻结。

---

## 0. A/B 差异总表（S4-1..S4-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S4-1 定义/唯一裁剪 | S4=Admission；VM.nodes=选中节点，**VM.edges=候选边每条 presence/rule_id**；Renderer 只画 shown | S4 唯一裁剪；**VM.nodes/edges 只含 shown**；suppressed/unknown 计数/audit | **关键差异**：S3-12 的 VM 边字段含 presence/rule_id，A 保留候选边更符合 S3 契约/审计；B 只 shown 会丢失 suppressed/unknown 的 rule_id 载体（P1-B）。 |
| S4-2 预算选点 | tier0 焦点+当前可见块**必选**；tier1 一跳/子块；tier2 相邻；tie-break canonical；超预算 `S4_BUDGET_INVALID`（tier0 不可满足时 fail） | 确定性 sort key `(is_focus,hop,kind_rank,semantic_degree,canonical_id)` 取前 N；超预算 suppressed；无必选/tier0 | **差异**：A 有必选集/失败语义；B 简洁但可能预算小/同分时把 focus/基座挤掉（P2-B）；A 的 tier0 失败在 max_nodes<可见块时会整屏失败（P1-A 预算语义）。 |
| S4-3 一跳 | `one_hop(F, A)` 从 **基座节点集 F** 出发，取恰好一条 `E_relation(D)` 边；不闭包/不带背后图 | 从 **focus** 出发，恰好一条边；节点=focus∪邻居；不闭包 | **关键差异（P1-A）**：A 的 F 若=当前层全部可见块，会从**每个基座节点**挂邻居，超出"以 focus 为一跳起点"的直觉，可能把邻域/背后图拉宽；S0-5 "当前视图"与 S1 A 的 focus 语义需裁。B 更严格。 |
| S4-4 存无三值 | 详尽 rule_id 表（dimension.sources/direction/level/hop/node.budget/edge.budget/cluster.folded/endpoint.unresolved/source.unavailable/admission.undecided/invalid.data）；unknown≠suppressed；类型独立 | 三值 + rule_id 枚举（node/edge budget、direction、level、hop、cluster、source、dim、unknown）；unknown 不渲染 | 核心一致；**A 的 rule_id 更完整**（invalid.data/endpoint.unresolved/dimension.sources）；B 可用于收敛。 |
| S4-5 背后图/2 跳 | 端点只作可见节点；新焦点由 S5；2 跳仅 `EXPLICIT_NEW_HOP`；跨层非 H 边 level.cross_layer | 同；S4 无导航状态；frame 重置 | 一致。 |
| S4-6 维度接入 | frame_spec（level/view_family/dimension/focus/hop/new_hop/mode/budget）；H/A 只改 presence；未知维度 fail-closed | 同；H/A 只改取景；维度切换重建 frame | 一致；A 更细（错误码/输入）。 |
| S4-7 层次交互 | drill 新 frame（level+1/focus/hop reset）；跨层只有 H 父子结构边；S2 run 只读不重算 | 同；drill reset；run 不进 VM | 一致。 |
| S4-8 全展开 | 同 Admission/present；`ctx_full` 放宽 relation_scope/hop/budget；`shown(default)⊆shown(full)`；full 仍预算/降级 | 同源同 present；候选/预算更大；子集机检 | 一致；A 明确 `relation_scope=all_data_edges`（易被误读为 S0-6 "不得 all_data_edges 直出"，需措辞确认，P2）。 |
| S4-9 S3 契约 | S4 输出 VM/presence/rule_id/aggregate_count；Renderer 只校验；阈值同源；超硬上限 Renderer fail | 同；S4 输出 VM；Renderer 不裁剪；max 同源 | 一致；A 的 aggregate_count/data_edge_ids 审计更细。 |
| S4-10 S5 边界 | S4 纯取景；focus/selection/nav 不进 VM；事件→S5；new_hop 仅 S5 | 同 | 一致。 |
| S4-11 S1/S2 | presence 不改 type/label/簇；A 不改簇；run 不进 VM；多归属 | 同 | 一致。 |
| S4-12 度量/G6 | 节点/边数、presence/rule_id 直方图、抑制率、hop 违规=0、closure/behind=0、deterministic sha、subset_ok；G6 ctx/budget/edition | 指标集合类似；one_hop_accuracy/determinism/G6 | 一致；A 更细（rule_id 直方图/behind_graph_leak）。 |

**总判断**：A 在 rule_id/指标/接口细节/全展开/必选语义上更完整；B 在 one-hop 严格以 focus 出发、VM 白名单更严、无 tier0 失败路径上更保守。**A 的两处结构问题（one-hop F 的范围、tier2 与一跳矛盾）和 B 的 VM 只 shown 问题需修**。

---

## 1. 异议（按严重度；P0=违反 S0–S3；P1=冻结前必须裁；P2=可冻结但后续补）

### P1-1（A）一跳起点是"基座节点集 F"而非 focus，可能把邻域/背后图拉宽

- **议项**：S4-3（U-15/U-17；S0-5/S1-5）。
- **异议**：A 定义 `one_hop(F,A)`，F 为基座/当前可见节点集；若 F 含当前层全部可见块（A 的 S4-2 tier0 正是"当前 level/view_family 的可见块节点"），则 S4 会从**每个基座节点**各挂一条 `E_relation(A)` 边，新增节点数可达 |F|×|E|，远超"以 focus 为中心的一跳"；这会把每个可见块的邻域都拉进来，接近"背后图/邻域展开"，与 S0-5"当前视图只挂接恰好一条边的邻居"（通常以 focus 为中心）和 U-17 不一致。B 以 focus 为唯一起点，更严格。
- **反例**：当前层有 50 个 KP 作为基座，每个有 5 条 reference；A 可能新增 250 个一跳端点（受预算截断），用户以为只看 focus 一跳；S0-5 机检 `视图边数 ≤ |F|×hop_budget` 可过，但 U-17 语义已变。
- **修复**：把 `F` 明确为 **focus**（或 `F={focus}`）；若需要基座内节点的一跳，必须另立规则并证明不违反 U-17/预算（例如仅允许 focus 所在簇的成员作为基座，且仍只挂 focus 直接边）。S1 A 的"当前视图节点"若指 focus，则文档应写死；若指基座，需 Lead/SE 裁决并同步 S1/S4 机检。
- **严重度**：一跳/背后图语义是 S4 核心 ⇒ **P1（冻结前）**。

### P1-2（A）S4-2 的 tier2 可产生 2 跳节点，与 S4-3「无 hop>1」自相矛盾

- **议项**：S4-2 / S4-3（U-18）。
- **异议**：A 的 S4-2 节点优先级写 tier2 = "与 tier0/1 通过 candidate 边相邻的节点"，并按 `(hop,label_rank,canonical)` 选；若 tier1 是一跳端点，tier2 与其相邻即**二跳**（focus→tier1→tier2），而 S4-3 机检要求"每个新增节点距离≤1（除非 new_hop）"、`no closure`。同一提案给出两个不同候选集，tier2 会把 2 跳引入默认视图（除非 tier2 仅指基座/同层节点，但文字未限定）。
- **反例**：默认 hop=1，tier1 有邻居 v，tier2 取 v 的邻居 w ⇒ w 距离 2 被 shown，S4-3 机检 FAIL；或实现者按 tier2 扩展导致闭包。
- **修复**：删除 tier2 的跨跳邻接，或明确 tier2 仅包含 **基座/H 同层节点**（hop=0/1 且非 focus 邻居）；所有候选必须满足 `hop≤hop_budget`；2 跳仅 S5 显式。机检统一 `max_hop(shown)≤hop_budget` 并覆盖 tier2。
- **严重度**：一跳/闭包硬规则 ⇒ **P1（冻结前）**。

### P1-3（A）tier0 必选 + 预算不足 `S4_BUDGET_INVALID` 可能让默认视图整屏失败

- **议项**：S4-2（U-5/U-16；S3 预算）。
- **异议**：A 把"focus + 当前 level/view_family 的可见块节点"设为必选 tier0；若 `|tier0| > max_nodes` 则 `S4_BUDGET_INVALID`（整屏失败）。S3 默认 `max_nodes=200`，而一个层级的可见 KP/块可能 >200（例如全展开前某层 KP 多），会出现"默认视图直接报错/空白"，而不是显式降级显示。S4 章程要求"超预算显式降级而非静默丢"；fail-visible 是显式，但不是可用降级；S8 也未必能保证 tier0 ≤ 200。
- **反例**：L1 有 300 个可见块，max_nodes=200 ⇒ A 返回 S4_BUDGET_INVALID，用户看不到任何图；B 的 sort 至少显示 focus+前 200（但 B 未保证 focus/基座必选）。
- **修复**：定义**最小必选集**（推荐：focus + 其祖先路径/当前层必要上下文，大小≤常数）为硬必选；其余可见块按优先级选，超预算 `suppressed+rule_id`；仅当"最小必选集 > max_nodes"（如 focus 不可显示）才 `S4_BUDGET_INVALID`。这样既显式降级又避免整屏失败；S8 保证 `max_nodes≥|最小必选集|`。
- **严重度**：默认视图可用性/预算语义 ⇒ **P1（冻结前）**。

### P1-4（B）B 的 VM 只含 shown 会丢失 suppressed/unknown 的 rule_id 载体

- **议项**：B 的 S4-1/S4-4（对照 S3-12/S0-6）。
- **异议**：B 写"VM.nodes/edges 只含 shown；suppressed/unknown 记录在 VM.suppressed_counts?/audit"，但 S3-12 冻结的 VM `edges[]` 字段含 `presence/rule_id`，S0-6 要求 `suppressed/unknown` 必须带 `rule_id` 且可枚举；若 VM 只含 shown，则 suppressed/unknown 的逐边 rule_id 无法进 VM，只能靠旁路 audit/count，与"每条候选边都有 presence"（S4-4 自身）不一致。A 保留候选边各有 presence 更符合 S3 契约。
- **反例**：某边因 `node.budget` 被抑制，VM 不包含该边 ⇒ 检查器/aria 无法给出 rule_id；只能显示总数，无法审计"为什么这条边没显示"。
- **修复**：VM 包含**候选边**（或至少 suppressed/unknown 的摘要记录）并逐条带 `presence/rule_id`；`nodes` 可只含 shown，但 `edges` 的 presence 需覆盖候选；若为性能只传 shown，则必须另立 `suppressed_edges` 数组带 rule_id，并纳入 S3 schema（S3 冻结后需 S4 修订/SE 确认）。推荐采用 A 的"候选边 + presence"。
- **严重度**：S3 契约/审计 ⇒ **P1（B 冻结前修）**。

### P2 清单

| # | 项 | 异议/证据 | 修复 |
|---|---|---|---|
| P2-1 | A 的 `relation_scope=all_data_edges` 措辞 | S0-6 明确"全展开不得 all_data_edges 直出"；A 是经 Admission 的候选 scope，但字面易被误解为直出 | 改为 `candidate_scope=all_data_edges` 且明确仍经 present/Admission；机检无 raw edge 直出 |
| P2-2 | A/B rule_id 枚举差异 | A 有 `invalid.data`（suppressed fail-visible）、`endpoint.unresolved`；B 无 | 统一枚举（A 为主）+ 每值 presence 类型；不得自由文本 |
| P2-3 | A 的 tier2/`label_rank` 与 B 的 `semantic_degree` 排序不同 | 两版都确定，但默认可见集不同；tie-break 需冻结 | 统一 sort key（推荐 A 的 tier + canonical；B 的 semantic_degree 可作 tier2 子键） |
| P2-4 | A 的 `S4_BUDGET_INVALID` vs B 的 `suppressed` 降级 | 与 P1-3 同源；需统一"最小必选集+部分显示" | 见 P1-3 |
| P2-5 | A 的 full 预算 `FULL_MAX`/full budget 是否可大于 S8 硬上限 | A §14.3 自列；S3 max 硬上限 | S8 冻结 full≤硬上限；full 只放宽候选/relation_scope，不越硬预算 |
| P2-6 | A 的 `unknown` 触发面 | A §14.4 自列；B 也有限 | 统一 unknown 枚举（source/endpoint/cache/dim）与不渲染/可重试语义 |
| P2-7 | A 的 `one_hop(F)` 与 S1 的 `focus`/F 定义 | P1-1；S0-5 机检用 F | 统一 F=focus 或明确 base 集合，并同步 S1/S0 机检 |
| P2-8 | A/B 的 G6 字段 | A 有 rule_id 直方图/behind_graph_leak/closure_violations；B 有 one_hop_accuracy/determinism | 合并 G6 字段；数值 S8 |
| P2-9 | A 的 `aggregate_count` 显式 | S3 R-S3-9 要求不遍历 data_edge_ids | 两版一致；A 明确取景层给 |
| P2-10 | A 的 `cluster.folded` suppressed 计数 | S2 folded 边 data_edge_ids；S4 只 presence | 保持 S2 生成/审计，S4 不遍历内部 |

---

## 2. 点名审查项结论

1. **S4 是否唯一裁剪者/Renderer 是否被允许裁剪**：A/B 都 **PASS**（S4=Admission；Renderer 只校验/渲染；S3 R-S3-2）；A 的 `S4_BUDGET_INVALID` 与 S3 `RENDER_BUDGET_EXCEEDED` 分工清楚。
2. **选点/tie-break 可复算/显式降级**：A 有 tier/排序/失败；B 有 sort key/suppressed；**P1-2/P1-3** 需修；A/B 均为确定性。
3. **一跳严格一条边/是否闭包/带背后图**：B **PASS**（focus 一跳）；A 的 `one_hop(F)` F 范围过宽（P1-1），需收窄到 focus/明确定义；2 跳均只 S5。
4. **presence 三值/rule_id/unknown vs suppressed/类型存在性**：A **PASS**（rule_id 表完整、unknown≠suppressed、类型独立）；B 方向 PASS但 VM 载体不足（P1-4）；A 更优。
5. **维度只改 presence/是否改事实/drill 重置**：A/B **PASS**（frame_spec；H/A 只 presence；drill 新 frame/hop reset；run 不进 VM）。
6. **全展开同源/子集**：A/B **PASS**（同一 Admission/present；`shown(default)⊆shown(full)`；A 有 subset 机检）；P2-1 措辞。
7. **S5 边界（focus/selection/nav 不进 VM）**：A/B **PASS**（S4 纯取景；事件→S5；VM 无 nav）。
8. **S1/S2（A 不改簇/多归属/run 不进 VM）**：A/B **PASS**（S4 只 presence；A 不重算簇；VM 无 run；多归属按 view_family）。
9. **度量/G6 可复跑**：A/B **PASS**（deterministic sha、presence/rule_id 计数、G6 字段）；A 指标更细（rule_id 直方图/behind/closure）。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A）一跳起点 `one_hop(F)` 的 F 范围过宽**：若 F=当前层全部可见块，会从每个基座节点挂邻居，接近邻域/背后图展开，与 S0-5/U-17 的 focus 一跳语义冲突。修复：F 冻结为 `{focus}`（或明确 base 集合并证明不违反 U-17/预算），同步 S1/S4 机检；B 的 focus 一跳可作基准。
2. **P1-2（A）S4-2 tier2 与 S4-3「无 hop>1」矛盾**：tier2 从 tier1 相邻节点取会引入 2 跳，默认视图可能闭包。修复：tier2 仅基座/H 同层节点，所有候选 `hop≤hop_budget`；2 跳仅 S5 显式；统一机检 `max_hop(shown)≤hop_budget`。
3. **P1-3（A）tier0 必选 + 预算不足 `S4_BUDGET_INVALID` 可能整屏失败**：默认 max_nodes=200 下可见块 >200 时无图可显示。修复：最小必选集（focus+必要上下文）为硬必选，其余按优先级 suppressed+rule_id；仅最小必选集超预算才 fail-visible；S8 保证 max≥最小必选集。

> P1-4（B）VM 只 shown 导致 suppressed/unknown 无逐边 rule_id 载体，B 需改为候选边带 presence（或另立 suppressed_edges 数组），与 S3-12/S0-6 对齐。

---

## 4. 结论

- **A 无 P0**；A 在 rule_id/指标/接口细节/全展开/必选语义上更强；B 在 focus 一跳/VM 白名单/无 tier0 失败路径上更保守。
- **A 冻结前需修 P1-1/P1-2/P1-3；B 需修 P1-4**；P2 可后续场次/SE 统一。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S0-5 `S0-terms-v1.md:49-54`；S0-6 `:56-61`；S1 A `S1-dimensions-v1.md:63-67`；S3 R-S3-2 `S3-visual-v1.md:66-69`；A S4-2/S4-3/S4-4/S4-9；B S4-1/S4-3/S4-4。
