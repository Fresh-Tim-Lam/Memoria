# S7 agent 如何使用图谱 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`；`S7-charter.md`；`S7-RULINGS.md`。
> **上游冻结**：S0（`241b1e1e…`）、S1（`6676c71d…`）、S2（`92bb0041…`）、S3（`0ca4ea0e…`+ADDENDUM-1）、S4（`2576f6c8…`）、S5（`7f4c4515…`）、S6（`40f12e5f…`+`S6-ADDENDUM-1`）——不得违反。
> **输入**：A-v2（`605f0032…`）、B-v2（`8c1ada34…`）、异议-v2（`849cfecb…`）。
> **状态**：冻结候选 v1，待 SE 工程校核（task-328）与 Lead 独立机检后冻结；冻结前不写产品代码。

---

## 0. 一句话口径

v1 agent **只读**：5 个只读工具（focus/explain/expand/summary/resolve_ref），只走 AgentQuery → DataSource/索引，不读文件系统、不写 sidecar/registry；`edges[]` 只含 shown，被抑制边用 summary+rule_id 解释、逐条由 explain 受控返回；所有工具可带 `expected_edition`，响应带 `edition_sha` 与 `audit_id`。

## 1. 规范性条款（S7-1..S7-12）

### S7-1 定位与只读边界
- **规则**：v1 agent **只读**；唯一读路径 AgentQuery → DataSource（只读）/索引；不得绕过 DataSource 读文件系统、不得写 sidecar/registry/cache、不得把 VM/缓存当事实；写请求一律 `GRAPH_WRITE_FORBIDDEN`；curation 只能走 S10 工具（未来）。
- **机检**：无写工具/写路径；读路径唯一；审计。

### S7-2 agent 可见层与 ViewResponse
- **规则**：`ViewResponse{kb_id, view_model_id, frame_id?(仅审计), level_id, view_family_id, dimension_id, data_state, edition_sha, nodes[], edges[], clusters[], suppressed_count, unknown_count, suppressed_summary{rule_id:count}, rule_histogram, truncated, audit_id}`。
  - `edges[]` **只含 `presence=shown`**；`suppressed/unknown` 不列原始边，只给 counts + summary/直方图；逐条解释由 `graph_explain_edge` 受控返回。
  - `clusters[]`：`{cluster_id, run_id, cluster_key, label, member_count, coverage}`（摘要载体）。
  - 不直接看 raw 边、不把 VM/缓存当事实；字段白名单机检。
- **机检**：edges 全 shown；summary/直方图存在；字段白名单；clusters 载体。

### S7-3 查询工具集
- **规则**：5 个只读工具（snake_case）：`graph_focus`、`graph_explain_edge`、`graph_expand_cluster`、`graph_summary`、`graph_resolve_ref`。
  - `graph_focus{kb_id, focus, dimension?, expected_edition?}`：H 层 / A focus-only 一跳，复用 S4；
  - `graph_explain_edge{kb_id, edge_id, expected_edition?}`：受控解释（含 suppressed/unknown/rule_id/claim_type）；
  - `graph_expand_cluster{kb_id, cluster_id, expected_edition?}`：**只返回一次 drill 的只读 ViewResponse，不改 S5 nav 状态/stack**；
  - `graph_summary{kb_id, dimension?, expected_edition?}`：SummaryResponse；
  - `graph_resolve_ref{kb_id, kp_id?|file+line|anchor, expected_edition?}`：引用解析。
- **v1 无 `graph_path`**（不隐式多跳；未来需 `allow_two_hop` + S5 `EXPLICIT_NEW_HOP`，另开修订）。
- **机检**：工具名唯一；无 path；expand 不改 nav；focus 一跳。

### S7-4 预算与截断
- **规则**：`max_tokens=4000`、`max_nodes=200`（S8 可调）；超预算先降级 summary，再显式 `truncated + omitted{kind,count}`；presence/rule 直方图必须给；**禁止静默截断**；极小预算下 summary 能给出即成功，否则 `GRAPH_TOOL_BUDGET_EXCEEDED`。
- **机检**：默认值；truncated 可见；直方图；预算错误码。

### S7-5 工具 schema、edition、幂等与审计
- **规则**：所有工具参数含 `kb_id`、可选 **`expected_edition?`**；响应/审计回带 `edition_sha`、`audit_id`；未传 `expected_edition` 用当前 edition 并在 `meta` 明示；不匹配 ⇒ `GRAPH_EDITION_STALE`。
  - 幂等键 `(tool, args, edition, budget)`；同键同结果；每次调用写 append-only 审计（失败 `GRAPH_TOOL_AUDIT_FAILED`）。
  - **错误表**（逐码映射 S6 + `S6-ADDENDUM-1`）：`GRAPH_TOOL_INPUT_INVALID`、`GRAPH_TOOL_BUDGET_EXCEEDED`、`GRAPH_ANCHOR_STALE`、`GRAPH_EDITION_STALE`、`GRAPH_RETRIEVAL_UNAVAILABLE`、`GRAPH_WRITE_FORBIDDEN`、`GRAPH_TOOL_AUDIT_FAILED`、`GRAPH_INTERNAL`；S6 既有码保留；均带 legacy/severity/i18n/audit_id。
- **机检**：schema 含 kb_id/expected_edition；响应 edition_sha/audit_id；幂等；错误表覆盖。

### S7-6 写权限
- **规则**：v1 agent 不可写图；不提供写工具；写请求/curation ⇒ `GRAPH_WRITE_FORBIDDEN`；不得改 sidecar/registry/cache；S10 才有写工具（另场冻结）。
- **机检**：无写工具；写 forbidden；无写路径。

### S7-7 引用与证据契约
- **规则**：每条 claim 带 `claim_type ∈ {graph_relation, source_assertion}`：
  - `graph_relation`：`cluster_key/run_id`（图谱关系）；
  - `source_assertion`：`kp_id + file + line/anchor`，并由 `graph_resolve_ref` 返回 **有界 `source_excerpt`（≤500 字符，含 offset/anchor/stale，只读、不缓存正文、审计）**；
  - unknown/未解析显式（`resolved=false` + `GRAPH_ANCHOR_STALE` 按场景）；不得编造；G7 记 `source_verified`。
- **机检**：claim_type；resolve_ref 有 excerpt/上限；stale；不缓存。

### S7-8 与 S9 检索接口
- **规则**：S7 只定义消费；S9 提供 candidate/召回/排序；S9 错误/空结果原样传播/可见降级（`GRAPH_RETRIEVAL_UNAVAILABLE`）；无 semantic edges 时返回 KP-only、无簇；`candidate_ref` schema 归 S9。
- **机检**：错误传播；无 semantic 降级；不夹带 S9 schema。

### S7-9 与 S10 边界
- **规则**：S10 设计/写 KP/语义边；S7 只读；写后 edition 变化 ⇒ `GRAPH_EDITION_STALE` 要求刷新；不混用旧新 edition；刷新触发方由 S10 定义。
- **机检**：edition 失效；不夹带写语义。

### S7-10 多维度/多归属
- **规则**：默认 H；A 必须显式 `dimension_id`；响应带 `scope_note`；多归属返回 `memberships[]`（cluster_id/cluster_key/run_id）；不把一维/族当全局。
- **机检**：dimension 显式；memberships；scope_note。

### S7-11 失败与降级
- **规则**：`no_semantic_edges`/预算不足/数据缺失/unknown/retrieval 不可用均显式可见；不编造、不静默、unknown≠无关系；降级路径有 `rule_id`/`degraded_reason`。
- **机检**：降级可见；无编造。

### S7-12 可观测与 G7
- **规则**：`G7_EVENT`（tool/tokens/refs/unknown/truncated/write_attempts=0/error_histogram/edition）、`G7_SNAPSHOT{...g6_run_ids[], g6_frame_ids[], edition}`；只引用 G6，不复制事实；阈值/隐私保留期归 S8。
- **机检**：G7 字段；引用 G6；write_attempts=0。

## 2. 跨议题裁决（R-S7-1..R-S7-9）

- R-S7-1 加 `graph_resolve_ref`；R-S7-2 edges 只 shown + summary/explain；R-S7-3 工具名/错误码对齐 S6+ADDENDUM-1；R-S7-4 字段统一；R-S7-5 幂等/导航边界；R-S7-6 默认值/G7 归属。
- **R-S7-7**：所有工具加可选 `expected_edition`，响应 `edition_sha`；不匹配 `GRAPH_EDITION_STALE`；幂等键含 edition。
- **R-S7-8**：`graph_resolve_ref` 对 `source_assertion` 返回有界 `source_excerpt`（≤500 字符），不读文件系统、不缓存正文、审计；`graph_relation` 用 cluster_key/run_id。
- **R-S7-9**：`ViewResponse`/`SummaryResponse` 必须含 `kb_id`、`clusters[]`、`suppressed/unknown` counts+summary、truncated；SummaryResponse 冻结字段（clusters/counts/data_state/truncated/edition_sha/audit_id）；B 的缺字段补齐。

## 3. 冻结前机检（SE + Lead）

M-S7-1 只读边界；M-S7-2 ViewResponse 字段/edges 口径；M-S7-3 5 工具/无 path/expand 不改 nav；M-S7-4 预算/截断/直方图；M-S7-5 schema/edition/幂等/审计/错误表；M-S7-6 写权限；M-S7-7 引用/excerpt/stale；M-S7-8 S9 边界；M-S7-9 S10 边界；M-S7-10 多维度/多归属；M-S7-11 降级；M-S7-12 G7 + S0–S6 一致性 + 工程图 `PARSE_OK`。

## 4. 覆盖矩阵（U → 条款）

| U# | 落地 |
|---|---|
| U-2 图谱为主/非辅 | S7-3/S7-4 |
| U-3 默认局部视图 | S7-2/S7-4 |
| U-6 不展示全图 | S7-4 |
| U-10 关联维度 | S7-3/S7-10 |
| U-11 层/子树 | S7-3 |
| U-12/13/14 agent 读/写/记忆 | S7-1/S7-6/S7-9 |
| U-15 一跳挂接 | S7-3 |
| U-17 背后图不带入 | S7-3 |
| U-19 KP/簇 | S7-2/S7-3 |
| U-27 边存无/类型 | S7-2/S7-7 |
| U-32 agent 侧 | S7-12 |

## 5. 冻结后

- S8（度量/验收）、S9（后端检索）、S10（agent 设计知识点）按议程后续；
- 0.5 实现计划按 S6a I-01..I-13，S7 工具面为消费侧接口。

## 6. 变更控制

- 加工具/字段/错误码：S7 修订 + 决策（新码同时登记 S6-ADDENDUM）；删/改只读边界/引用/写权限：重开 S7。
