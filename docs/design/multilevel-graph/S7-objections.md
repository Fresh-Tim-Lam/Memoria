# S7 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`、`S4-render-v1.md`（`2576f6c8…`）、`S5-nav-v1.md`（`7f4c4515…`）、`S6-contract-v1.md`（`40f12e5f…`），不得违反；`S7-charter.md`。
> **对象**：`S7-agent-proposal-A.md`（主办研究，sha **`2508e8bc1532167627496e48e87dc48636b7b8cc39c7fa1c437f1b9e8d981daa`**，22,150 B）与 `S7-agent-proposal-B.md`（本复核方，sha **`2293ddd34e5c71c4efef655457fac7bd6e796ea84068d17e00961392cfa6ade3`**，15,917 B）。
> **独立性**：B 于 22:15:47 落盘，A 于 22:16:22 才出现；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S6 冻结。

---

## 0. A/B 差异总表（S7-1..S7-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S7-1 定位/只读 | v1 只读；只能经 AgentQuery 看 View；**不直接读 DataSource raw edges**；S10 写 | v1 只读；可读 DataSource 只读投影 + GraphView/VM；不写 | A 更严格（不直接 DataSource）；B 的“可读 DataSource”与 S7-2 引用/锚点需统一；均无写路径。 |
| S7-2 可见层 | ViewResponse 含 `frame_id/edition_sha`、node/edge、presence/rule_id；`data_edge_ids` 不可见 | AgentView 含 view_model/frame、presence/rule；不暴露 data_edge_ids | 一致；**字段命名不同**（A `underlying_edge_count` vs B/S6 `aggregate_count`；A `frame_id` vs B `view_model_id`）见 P2-1/P2-2。 |
| S7-3 查询 | 4 工具：`graph_focus/graph_explain_edge/graph_expand_cluster/graph_summary`；**v1 不提供 path**；无隐式 2 跳 | `graph.focus/expand/explain/path?/query?`；path 显式有界 | 核心一致；**A 不提供 path/B 可选 path**（charter `path?` 允许）；工具名/集合需冻结（P2-3）。 |
| S7-4 token/截断 | summary 优先、显式 truncated/omitted、presence/rule 直方图；**suppressed 不列原始边** | token budget、summary、显式截断、suppressed/unknown 解释 | 一致；**A S7-2 edges 含 suppressed/unknown 与 S7-4“不列被抑制原始边”矛盾（P1-2）**；B 需明确摘要/边列表。 |
| S7-5 工具/错误 | 4 工具 schema；`GRAPH_*` 错误表；只读/幂等/审计；无写工具 | 工具 schema/错误/audit；无写 | A 更细；**A 新增 `GRAPH_TOOL_*`/`GRAPH_ANCHOR_STALE` 等未在 S6 canonical 注册（P1-3）**；B 工具名/错误表需对齐。 |
| S7-6 写边界 | 无写；curation S10+审计/人工；禁 sidecar/registry | 同 | 一致。 |
| S7-7 引用 | `claim_type` graph_relation/source_assertion；kp/file/line/anchor、cluster_key/run_id；unknown 显式 | REF kp/file/line、cluster_key/run_id；unknown；关系 vs 断言 | 一致；**A/B 都缺“引用解析/原文读取”工具（P1-1）**。 |
| S7-8 S9 接口 | S7 只消费；S9 候选/召回；错误传播；无 semantic 降级 | 同 | 一致；A 更细（候选 ref 字段）。 |
| S7-9 S10 边界 | S10 写；S7 只读；edition stale/刷新 | 同 | 一致。 |
| S7-10 多维度/多归属 | 默认 H；A 显式；memberships[]；不合并 | 同 | 一致。 |
| S7-11 失败/降级 | no_semantic/预算/数据缺失/unknown/stale 显式 | 同 | 一致；A 更细（错误码/状态）。 |
| S7-12 G7 | G7_EVENT/G7_SNAPSHOT/指标 | G7_SNAPSHOT/指标 | 一致；A 更细（call_id/audit）。 |

**总判断**：A 在工具/错误码/引用/G7 细节上更强；B 在 path 可选/工具面更少、字段命名更贴 S6 上较保守。两版核心一致；**P1 集中在“引用解析工具缺失”“suppressed 边可见性矛盾”“S7 新错误码未进 S6 canonical”**。

---

## 1. 异议（按严重度；P0=违反 S0–S6；P1=冻结前必须裁；P2=后续/SE）

### P1-1（A/B）缺“引用/锚点解析”工具，S7-7 的“引用可解析”无契约入口

- **议项**：S7-5/S7-7（S7 章程判据 4；S6 DataSource KP/file/line）。
- **异议**：A/B 都要求回答带 `kp_id+file+line`/anchor 且“引用可解析”，但工具集只有 `focus/explain/expand/summary`（A）或 `focus/expand/explain/path?/query?`（B），**没有 `resolve_ref`/`get_source_assertion`/`resolve_anchor` 只读工具**。agent 拿到 KP/行号后无法通过契约验证 anchor/读取原文断言；要么直接读文件/DataSource（违反 S7-1“不绕过 DataSource/不直接 raw”），要么只能信任 ViewResponse 的 anchor（S7-7 要求“可解析”但无解析入口）。B 的 `query?` 也不明确包含 anchor 解析。
- **反例**：agent 引用 `kp_id+file+line`，但无法确认 file/line 存在/是否 stale；S7-7 机检“引用可解析”无法通过统一工具完成；agent 只能 `cat` 文件（越界）。
- **修复**：增加只读工具 **`graph_resolve_ref(ref)`**（或 `graph_get_source(kp_id)`）：输入 `{kp_id?|edge_id?|cluster_ref?, file?, line?, anchor?}`，返回 `{resolved:boolean, kp_id/file/line/anchor/occurrence, source_assertion_excerpt?（受版权/长度限制）, stale:boolean, error?}`；只读、幂等、审计；agent 只能通过它/ViewResponse anchor 访问原文，禁止直接文件/DataSource raw。或明确 S7-7 的“可解析”只依赖 ViewResponse 返回的 already-validated anchor（则不需要额外工具），但需在 S7-5 写明并机检。
- **严重度**：引用契约是 S7 核心验收 ⇒ **P1（冻结前）**。

### P1-2（A）S7-2 的边列表含 suppressed/unknown，与 S7-4“不列出被抑制原始边”自相矛盾

- **议项**：S7-2/S7-4（S4 presence/rule_id；S6 VM）。
- **异议**：A S7-2 的 `ViewResponse.edges[]` 字段含 `presence, rule_id?`，按 S4/S6 语义会包含 suppressed/unknown 边；但 A S7-4 又写“**suppressed 解释：按 rule_id 聚合；不列出被抑制的原始边**”。同一响应若含 suppressed 边则违反 S7-4；若不含则 S7-2 的 `presence/rule_id` 只对 shown 边，无法解释“为什么这条边没显示”（S4 R-S4-4/S6-5 的候选载体要求）。B 的 AgentView 也有类似未定的 suppressed 可见性。
- **反例**：agent 询问某边为何未显示：ViewResponse edges 无该边 ⇒ 无 rule_id 可解释；或含该边 ⇒ 违反“不列被抑制原始边”；不同实现两种行为。
- **修复**：二选一并机检：① `edges[]` 只含 shown；另给 `suppressed_edges_summary{rule_id:count}` + `graph_explain_edge(edge_id)` 返回 suppressed 边的 rule_id（受控、不批量列 raw）；② `edges[]` 含全部候选，但 suppressed/unknown 标记 `explain_only=true`、agent 不得当 shown/事实；S7-4 改成“按 rule_id 聚合摘要，不默认展开 suppressed 的端点/背后图”。S7-2/S7-4 同步，机检“suppressed 逐边不可见/可解释”一致。
- **严重度**：presence 解释核心 ⇒ **P1（冻结前）**。

### P1-3（A）S7 新增 `GRAPH_TOOL_*`/`GRAPH_ANCHOR_STALE` 等错误码未进 S6 canonical 注册

- **议项**：S7-5（S6-9 `GRAPH_*` canonical + legacy 映射）。
- **异议**：A S7-5 定义 `GRAPH_TOOL_INPUT_INVALID, GRAPH_KB_NOT_FOUND, GRAPH_EDITION_STALE, GRAPH_DIM_UNKNOWN/GRAPH_DIM_NOT_ACTIVE, GRAPH_FRAME_ID_INVALID, GRAPH_FOCUS_REQUIRED, GRAPH_TOOL_BUDGET_EXCEEDED, GRAPH_ANCHOR_STALE, GRAPH_RETRIEVAL_UNAVAILABLE, GRAPH_WRITE_FORBIDDEN, GRAPH_INTERNAL`；其中 `GRAPH_TOOL_INPUT_INVALID/GRAPH_TOOL_BUDGET_EXCEEDED/GRAPH_ANCHOR_STALE/GRAPH_RETRIEVAL_UNAVAILABLE/GRAPH_WRITE_FORBIDDEN` 等**不在 S6-contract-v1 的 canonical 错误表/映射中**（S6 只列 `GRAPH_FRAME_ID_INVALID/GRAPH_PRESENCE_INVALID/GRAPH_SUBSET_VIOLATION/GRAPH_BUDGET_INVALID` 等）。S6 冻结后新增 `GRAPH_*` 码必须走 S6/S7 契约注册（canonical + legacy + i18n）；否则 S7 工具返回码与 S6 不一致、G7/客户端无法映射。B 亦未给码表（只写 `GRAPH_*`）。
- **反例**：S4 返回 `GRAPH_BUDGET_INVALID`，S7 工具预算返回 `GRAPH_TOOL_BUDGET_EXCEEDED`，调用方需猜两套；S6 G6/错误统计无法归一。
- **修复**：S7 冻结**工具错误码表**，每码映射 S6 canonical（优先复用 `GRAPH_BUDGET_INVALID/GRAPH_FRAME_ID_INVALID/GRAPH_PRESENCE_INVALID/...`），仅 S7 特有码新增并登记 legacy/i18n/severity；机检 S7 码 ⊆ S6 `GRAPH_*` 注册表或已登记 S7 扩展；B 同步码表。
- **严重度**：S6/S7 错误契约 ⇒ **P1（冻结前）**。

### P2 清单

| # | 项 | 判断/修复 |
|---|---|---|
| P2-1 | A `underlying_edge_count` vs S6/S4 `aggregate_count` | AgentView 应复用 S6/S4 字段名（`aggregate_count`/`hop`），不另造；机检字段映射 |
| P2-2 | A `frame_id`/B `view_model_id` 在 AgentView 中的身份字段 | 统一：agent 查询用 `view_model_id`（S6 VM）+ `frame_id` 仅当 S5 frame 关联；避免把 S5 导航状态当 agent 事实 |
| P2-3 | 工具集/名称：A 4 工具 underscore、无 path；B dot、含 path?/query? | S7 冻结唯一工具名/集合；path 是否 v1 按 A §14 裁；`query?` 泛化工具若保留需定义不引入新语义；去掉未定工具 |
| P2-4 | A 幂等“同参数（除 budget）同结果” | 预算变化本会改变结果；幂等应定义为同参数（含 budget/edition）同结果，否则不可判 |
| P2-5 | A `graph_expand_cluster` 复用 S5 CLICK_CLUSTER 但 agent 不应持有导航状态 | 明确 S7 调用 S5 转移语义的纯函数/只读子集，不写 S5 stack；机检无 nav 状态变更 |
| P2-6 | B `graph.query?`/`path?` 可能夹带未冻结语义 | 删除或限定为显式只读组合查询；path 需 `max_hops`/显式，不产生 presence；SE 审 |
| P2-7 | S9 candidate_ref schema 归属 | S7 只定义消费字段（id/score?/edition），S9 定实现；不把 score 当事实 |
| P2-8 | S10 写后刷新/人工确认 | S7 只报 stale；刷新编排归 S9/S10；不自动混用旧 edition |
| P2-9 | token 默认 4000/200、G7 阈值/隐私 | S8 定；G7 不含正文；保留期/上报 S8 |
| P2-10 | A S7-12 G7 与 S6 G6 字段关系 | G7 引用 G6 `data_source_sha/run_ids/registry_sha/vm_sha/frame_sha`，不重复/冲突；字段统一 |

---

## 2. 点名审查结论

1. **agent 只读/是否绕 DataSource/写 sidecar**：A **PASS**（只读；不写 sidecar/registry；S10 写）；B **PASS** 但“可读 DataSource 只读投影”需与 S7-2 统一（P2-2/P1-1）。
2. **可见层是否把 VM/缓存当事实**：A/B **PASS**（View 派生；事实回 DataSource anchor；data_edge_ids 不可见）；A `underlying_edge_count` 字段命名 P2-1。
3. **查询是否复用 S4 focus-only/S5 nav/无隐式 2 跳**：A/B **PASS**（focus 一跳；expand 一层；无隐式 2 跳；path 显式/可选）；A 无 path、B 可选 path；需冻结（P2-3/P2-6）。
4. **explain/expand/path 语义**：A **PASS**（explain edge 受控；expand 一层；v1 无 path）；B 方向 PASS（path 显式有界；`query?` 需限定）；A 的 explain 无 path 选项为明确取舍。
5. **token 预算/静默截断/unknown/suppressed**：A/B **PASS**（显式 truncated/omitted、直方图、unknown≠无）；**A suppressed 边可见性矛盾 P1-2**。
6. **工具 schema/`GRAPH_*`/幂等/审计**：A/B **PASS**（只读/审计/幂等）；**A 新码未进 S6 canonical P1-3**；工具名集合需冻结（P2-3）。
7. **引用契约可机检**：A/B 有 REF/claim_type；**缺解析工具 P1-1**；field/file/line/cluster_key/run_id 要求 PASS。
8. **与 S9/S10 边界（不夹带）**：A/B **PASS**（S9 召回、S10 写；S7 只读消费；edition stale）；A 更细；S9 candidate_ref schema P2-7。
9. **多维度/多归属**：A/B **PASS**（显式 dim/family；memberships；不合并；默认 H 标注）。
10. **失败降级**：A/B **PASS**（no_semantic/预算/数据缺失/unknown/stale 可见；不编造）；A 错误码更细；P1-3 注册。
11. **指标/G7**：A/B **PASS**（G7 events/snapshot/metrics；阈值 S8）；A 更细；字段与 G6 关系 P2-10。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A/B）缺引用/锚点解析只读工具**：S7-7 要求引用可解析，但工具集无 `resolve_ref`/`get_source`；agent 只能绕过 DataSource 读文件或盲信 anchor。修复：增加 `graph_resolve_ref`（只读/幂等/审计，返回 resolved/file/line/anchor/stale/source_assertion），或明确 ViewResponse anchor 已校验且无需解析；机检引用可解析。
2. **P1-2（A）S7-2 edges 含 suppressed/unknown 与 S7-4“不列被抑制原始边”矛盾**：同一响应要么含 suppressed 边（违反 S7-4）要么不含（无法解释 rule_id）。修复：`edges[]` 只 shown + `suppressed_summary/rule_histogram` + `explain_edge` 受控解释；或全候选但 suppressed `explain_only=true`，S7-4 改口径；S7-2/S7-4 同步机检。
3. **P1-3（A/B）S7 新错误码/工具名未与 S6 canonical 对齐**：A 的 `GRAPH_TOOL_*`/`GRAPH_ANCHOR_STALE`/`GRAPH_RETRIEVAL_UNAVAILABLE` 等不在 S6 注册表，B 无码表；工具名 A `graph_focus` vs B `graph.focus`。修复：S7 冻结工具名 + 错误码表，逐码映射 S6 `GRAPH_*`/legacy/i18n/severity；新增码登记 S6/S7 扩展；机检。

## 4. 结论

- **两版均无 P0**；核心只读边界/可见层/查询/预算/引用/边界已收敛。A 在工具/错误码/G7/引用细节上更强；B 更少工具、更贴 S6 字段。
- **P1-1/P1-2/P1-3 冻结前必须修**；P2 包括字段命名（aggregate_count）、工具集/ path、幂等定义、S9 candidate schema、S10 刷新、G7/G6 关系、token 默认值。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S7 章程 S7-1..12；S4 R-S4-1/2/4；S5 导航；S6-1/5/9；A S7-2/S7-4/S7-5/S7-7；B S7-2/S7-4/S7-5/S7-7。
