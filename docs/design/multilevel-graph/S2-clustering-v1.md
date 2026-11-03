# S2 簇与子图划分 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`（U-1..U-35）；`S2-charter.md`；`S2-RULINGS.md`。
> **上游冻结**：`S0-terms-v1.md`（sha `241b1e1e…`）、`S1-dimensions-v1.md`（sha `6676c71d…`）——不得违反。
> **输入**：A-v2（sha `154cf098…`）、B-v2（sha `5a1d299d…`）、异议-v2（sha `864a9cdd…`）、语义-only probe（`artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/`）。
> **状态**：冻结候选 v1，待 SE 工程校核（task-302）与 Lead 独立机检后冻结；冻结前不写产品代码。

---

## 0. 一句话口径

簇 = **仅由 semantic 边**构成的语义内聚小群（μ 达标、β 不超标），**不是**严格连通分量；无语义边的语料合法地产生"无簇"，不得拿结构/引用边伪造簇。默认视图在无簇状态下的 UX 归 S3/S4，本场只冻结"无簇是合法状态"与"不得伪造"。

## 1. 规范性条款（S2-1..S2-13）

### S2-1 簇定义与边界
- **规则**：簇 = 同一 `(level, view_family)` 内、由 `E_sem`（label=semantic）诱导的成员块，满足 μ≥τ_coh 且 β≤τ_bridge；≠ 严格连通分量；空簇禁止；单点块允许（`representative=false`）；L0 全库一簇用显式 `root_exempt=true`；禁止 UnionFind/并查集（graph-groups）当簇。
- **机检**：`used_edges(C) ⊆ E_sem`；单点 `representative=false`；root_exempt 显式；无空簇。
- **来源**：A-v2 S2-1/S2-9；B-v2 S2-1；R-S2-1。

### S2-2 内聚度 μ（语义-only）
- **规则**：`μ(C)=W_in / (|C|(|C|-1)/2)`，其中 `W_in` 只累计 **semantic 边**权重（v1 `weight_policy=semantic_uniform`，权重 1.0）；reference/structural/非 semantic extend **权重 0**，仅出现在 `diag_struct_*` 诊断字段，不参与 μ/β。
- **机检**：`used_edges(C) == E_sem ∩ internal(C)`；含非 semantic 边 ⇒ `S2_SEMANTIC_PURITY_FAIL`。
- **来源**：A-v2 S2-2；B-v2 S2-2/S2-9；R-S2-1（P0）。

### S2-3 桥 β（语义-only）
- **规则**：`β(C)=W_out/(W_in+W_out)`，同样只累计 semantic 边；另报 `bridge_per_member`、`single_anchor` 诊断（只作诊断，不作合格判据）。
- **机检**：β 输入边集 == E_sem；诊断字段不参与 `representative` 判定。
- **来源**：A-v2 S2-3；B-v2 S2-3；R-S2-1。

### S2-4 划分算法（确定性 HAC 契约）
- **规则**：v1 主算法 = **纯自实现 average-linkage HAC**，无第三方依赖；输入 `E_sem` 诱导的图；建完整 dendrogram；按 **`cut_policy`（target_k 或 min_cluster_size）** 切分；tie-break = `min canonical id`；canonical 序列化。
- **R-S2-9（冻结）**：canonical 契约 = 标准 average-linkage dendrogram + cut（`target_k`/`min_cluster_size`），**μ/β 只作后验质量校验，不作合并门控**；B 的"μ/β 门控约束合并"列为 reserved 替代（不进 v1）。算法四态：`ok / no_semantic_edges / partial_disconnected / size_exceeded / algorithm_failed`（不得用"degraded"含糊覆盖）。
- **机检**：两次运行 run 逐字节一致；golden 可复算；无第三方 import；失败状态可枚举；不得静默回退连通分量。
- **来源**：A-v2 S2-4；B-v2 S2-4；R-S2-3；R-S2-9（Lead）。

### S2-5 稳定性与重算触发
- **规则**：run 不可变；触发 = corpus/manifest、semantic 边集、算法 id/version、params_hash 任一变化，或显式请求；v1 全量重算；稳定性度量 = 成员加权 Jaccard / churn / split-merge / 簇数差。
- **机检**：同输入同 params ⇒ 同 run_id；任一触发字段变化 ⇒ 新 run；指标可复算。
- **来源**：A-v2 S2-5；B-v2 S2-5。

### S2-6 多归属
- **规则**：`Membership` 多对多；同一 `(level, view_family)` 内单归属、跨族/层/维多归属；`Membership.role ∈ {member}`（**不复用** S1 node `role=bridge`）；成员关系 ≠ 视图出现；v1 不设上限（S6 可配）。
- **机检**：同族同层成员唯一；role 枚举；视图出现与成员分开断言。
- **来源**：A-v2 S2-6；B-v2 S2-6；R-S2-7。

### S2-7 簇身份
- **规则**：run = `(level, view_family)`；`cluster_run_id = sha256(canonical(corpus_manifest_sha, view_family_id, level_id, algorithm_id, algorithm_version, params_hash))`；父子 `parent_run_id`；`local_seq` 按成员最小 canonical id 排序；`cluster_key` 按 D-2（成员集合 + 算法 + 版本 + 参数）。
- **R-S2-10（冻结）**：`params_hash` 规范字段集 = `{algorithm_id, algorithm_version, weight_policy="semantic_uniform", linkage="average", tie_break="min_canonical_id", cut_policy, target_k, min_cluster_size, n_max, tau_coh, tau_bridge}`；任一字段变化 ⇒ 新 run；curation/审计引用必须同时记 `run_id + cluster_key`。
- **机检**：run_id 可复算；字段集固定；缺字段 fail-closed。
- **来源**：A-v2 S2-7；B-v2 S2-7；R-S2-4；R-S2-10。

### S2-8 嵌套与展开
- **规则**：`Π_{ℓ+1}` 精化 `Π_ℓ`（parent_run_id 连接）；展开 = H 导航到 KP 叶子（无 hop）；空簇禁止；单点允许；退化细化（无子簇）显式标记。
- **机检**：父子 run 成员覆盖关系；展开到底全为 KP；无空簇。
- **来源**：A-v2 S2-8；B-v2 S2-8。

### S2-9 簇与边
- **规则**：internal/bridge 只由 semantic 边分类；`data_edge_ids` 必须映射回 `DataSource.edges`（R-3）；H 派生边按 S1 R-S1-11（允许空集）；`contain(structural)` 只作层次结构证据，**不参与 μ/β**；桥的渲染归 S4。
- **机检**：`expand_data_edges ⊆ DataSource.edges`；μ/β 输入集不含 structural/reference；桥边可映射。
- **来源**：A-v2 S2-9；B-v2 S2-9；R-S2-1。

### S2-10 簇与维度
- **规则**：H 每层独立但嵌套划分；**A 维度不产生/不改变簇**（同 DataSource + params 下切换 H/A，cluster run 不变）；`view_family` 为划分作用域。
- **机检**：`assert_A_dimension_invariance`（同数据同参数，A 切换前后 run_id 相同）。
- **来源**：A-v2 S2-10；B-v2 S2-10；R-S2-7。

### S2-11 持久化与缓存
- **规则**：簇/成员/边/稳定性全部为**派生缓存**（可重建）；**禁止写产品 sidecar/新段**（D-3）；旧 run 只读；路径/GC/schema 归 S6。
- **机检**：无产品 sidecar 写入；缓存可删除后重建得到同 run。
- **来源**：A-v2 S2-11；B-v2 S2-11；S0 D-3。

### S2-12 语义稀疏与无簇状态
- **规则**：`E_sem` 为空或不足时，合法结果为 **无 representative 簇**（`no_semantic_edges` / coverage=0），**不得**引入结构/引用边伪造簇；默认视图在该状态下的 UX 归 S3/S4（S2 只冻结状态与"不得伪造"）；真实语料缺语义边是**语料质量问题**（本仓库 frozen 语料与 showcase 均 E_sem=0，probe 已证），不是放松语义门槛的理由；修复路径 = agent 建立 semantic（S10）。
- **机检**：无簇状态可枚举；coverage=0 合法；任何结构边进入簇判据 ⇒ FAIL。
- **来源**：A-v2 S2-12；B-v2 S2-2b；Lead 裁决（人指出语料库质量差、要求继续思考）；R-S2-11。

### S2-13 与 agent
- **规则**：v1 agent **只读** run；可请求"新建候选 run"（`requester/reason/params/base_run_id` 审计；`status=candidate`，不自动采用、不覆盖旧 run）；不得写 membership/缓存/manifest/渲染状态；跨 KB 拒绝。
- **机检**：candidate/adopted 分离；审计字段必填；无写路径。
- **来源**：A-v2 S2-13；B-v2 S2-13；R-S2-5。

## 2. 跨议题裁决（R-S2-1..R-S2-13）

- R-S2-1：μ/β 只用 semantic 边（P0 关闭）。
- R-S2-2：τ 默认值须有 probe 出处；`no_semantic_edges` 合法。
- R-S2-3：确定性 HAC；失败显式状态。
- R-S2-4：run 粒度 `(level, view_family)`。
- R-S2-5：agent 只读 + candidate run。
- R-S2-6：singleton μ=null/representative=false；root_exempt；coverage 按覆盖 KP/全库 KP。
- R-S2-7：Membership.role 不复用 bridge；A 不改变簇。
- R-S2-8：A/B 并集。
- R-S2-9：canonical HAC 契约（average-linkage + cut；μ/β 后验；B 变体 reserved）。
- R-S2-10：params_hash/run_id 字段集冻结；curation 记 run_id+cluster_key。
- R-S2-11：τ 默认 `τ_coh=0.5`、`τ_bridge=0.25`（出处：合成语义夹具 probe `results.json`；真实语料 E_sem=0 故为合成标定，S8 在 live 语料复标定；默认值可配置但必须进 params_hash）。
- R-S2-12：无簇状态合法，禁止结构边伪造簇；默认视图 UX 交 S3/S4。
- R-S2-13：状态枚举统一（`ok/no_semantic_edges/partial_disconnected/size_exceeded/algorithm_failed`）；`Membership.role={member}`；`diag_struct_*` 仅诊断；agent 请求带 `base_run_id`。

## 3. 冻结前机检（SE，M-S2-1..M-S2-12）

M-S2-1 簇定义/边界；M-S2-2 μ semantic-only；M-S2-3 β semantic-only + 诊断分离；M-S2-4 HAC 确定性/golden/状态枚举；M-S2-5 run 粒度/身份/params_hash；M-S2-6 稳定性触发；M-S2-7 多归属/role/partition；M-S2-8 嵌套/展开；M-S2-9 簇边/data_edge_ids/R-3；M-S2-10 维度不变性（A 不改簇）；M-S2-11 持久化 D-3；M-S2-12 无簇状态 + 禁止结构伪造 + 覆盖矩阵 + 与 S0/S1 一致 + ER/DFD/状态图增量（同版本 mermaid）。

**另**：SE 需**独立复跑语义-only probe**（同方法；frozen + showcase + 合成夹具），核对 A 的 `τ=0.5/0.25` 出处与 B 的独立复算缺口（task-304 未完成项），产物路径与命令写入报告。

## 4. 覆盖矩阵（U → 条款）

| U# | 要点 | 落地 |
|---|---|---|
| U-6 | 簇节点代表连通子图 | S2-1/S2-4/S2-6；S3/S4 |
| U-13 | 非严格连通子图：内聚高+零星桥 | S2-1/S2-2/S2-3 |
| U-14 | 按语义关系划分小群 | S2-2（semantic-only） |
| U-15 | 深入后经语义边挂接一跳 | S1（一跳）+ S2-8 |
| U-17 | 一跳背后图不自动带入 | S1/S4；S2 只定内部/桥边 |
| U-21 | 多归属（不同子图/层次/维度） | S2-6 |
| U-22 | 新一跳 vs 跳更深 | S1-5（new_hop）；S2-8/S5 |
| U-31 | 多归属先定义/或不设上限 | S2-6（v1 不设上限） |
| U-32 | 规模不是问题、关键后端检索 | S2-5/S2-7（缓存/run）→ S9 |
| U-34 | 逐议项/质量优先 | 章程/变更控制 |

## 5. 冻结后进入的下一场

S3（节点视觉与渲染接口）；S3 必须处理 `no_semantic_edges` 状态的 UX，但**不得**把结构边当语义簇；S3 不得改 S2 的 μ/β/算法/身份。

## 6. 变更控制

- 加算法/cut_policy/参数：S2 修订 + 决策 + params_hash 版本；
- 删/改 μ/β 语义-only、身份公式、无簇状态规则：重开 S2；
- 本文件冻结以 SE 的 M-S2 全 PASS + 独立 probe 复跑 + Lead 独立机检为前置。
