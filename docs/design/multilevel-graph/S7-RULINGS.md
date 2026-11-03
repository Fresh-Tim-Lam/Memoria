# S7 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S7-charter.md`；
> 上游冻结 S0/S1/S2/S3(+ADDENDUM-1)/S4/S5/S6（`241b1e1e…/6676c71d…/92bb0041…/0ca4ea0e…/2576f6c8…/7f4c4515…/40f12e5f…`）。
> **输入**：提案 A（`2508e8bc…`）、提案 B（`2293ddd3…`）、异议（`65f65bf8…`）。
> **状态**：S7 **未冻结**；两版无 P0，3 条 P1 需冻结前修。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 缺引用解析工具 | 读 A/B 工具集与 S7-7 引用契约 | **成立**：有引用字段但无 `resolve_ref` 入口；agent 只能绕过 DataSource 读文件或盲信 anchor |
| P1-2 A ViewResponse edges 含 suppressed 与 S7-4 矛盾 | 读 A S7-2/S7-4 | **成立**：若 edges 含 suppressed 就无法「不列原始边」；必须统一口径 |
| P1-3 错误码/工具名未对齐 S6 | 读 A S7-5 与 S6 §S6-9 | **成立**：S7 新码/工具名未登记；S6 是 canonical 命名空间 |
| 其余点名 | 只读/可见层/查询/预算/引用/S9-S10/多维度/降级/G7 | 全 PASS 或方向 PASS；P2 合并 |

## 1. 跨议题裁决（R-S7-1..R-S7-6）

### R-S7-1 增加只读引用解析工具（P1-1）
- **裁决**：工具集冻结为 **5 个只读工具**：`graph_focus`、`graph_explain_edge`、`graph_expand_cluster`、`graph_summary`、**`graph_resolve_ref`**；`graph_resolve_ref` 输入 `{kp_id?|file+line|anchor}`，返回 `{resolved, kp_id, file, line, anchor, stale, claim_type}`；只读、幂等、审计；不得读文件系统绕 DataSource（解析走 DataSource/索引）。
- **机检**：引用可解析；工具无写；审计记录；`stale` 显式。

### R-S7-2 ViewResponse 的边可见性（P1-2）
- **裁决**：`ViewResponse.edges[]` **只含 `presence=shown`**；`suppressed/unknown` **不列原始边**，只给 `suppressed_summary{rule_id:count}` + `rule_histogram`；需要逐条解释时由 **`graph_explain_edge(edge_id)`** 受控返回 `{presence, rule_id, claim_type, evidence}`（可解释被抑制边，但不批量列出）；`S7-4` 与 `S7-2` 同步此口径。
- **机检**：edges 全 shown；summary 有 rule_id 计数；explain 可解释 suppressed；无原始隐藏边批量泄漏。

### R-S7-3 工具名与错误码 canonical（P1-3）
- **裁决**：工具名统一 **snake_case**：`graph_focus/graph_explain_edge/graph_expand_cluster/graph_summary/graph_resolve_ref`；工具集 v1 **不含 `graph_path`**（不做隐式多跳；未来需显式 `allow_two_hop` + S5 `EXPLICIT_NEW_HOP`，另开修订）。
- **错误码**：S7 错误表必须逐码映射 S6 `GRAPH_*`/legacy/i18n/severity；新增 S7 码登记到 **S6 错误命名空间扩展（S6-ADDENDUM-1）**：`GRAPH_TOOL_INPUT_INVALID`、`GRAPH_TOOL_BUDGET_EXCEEDED`、`GRAPH_ANCHOR_STALE`、`GRAPH_RETRIEVAL_UNAVAILABLE`、`GRAPH_WRITE_FORBIDDEN`、`GRAPH_TOOL_AUDIT_FAILED`；保留 S6 既有码；未知 `GRAPH_INTERNAL`。
- **机检**：工具名唯一；错误表覆盖；新码在 S6 扩展登记；i18n/severity。

### R-S7-4 字段命名统一（P2）
- **裁决**：`ViewResponse` 用 `view_model_id`（S6 VM）、`frame_id`（若由导航帧触发，仅审计）、`aggregate_count`（替代 `underlying_edge_count`）；簇字段 `member_count`；不新增同义字段；机检字段白名单。

### R-S7-5 幂等与导航边界（P2）
- **裁决**：幂等键 = `(tool, args, edition, budget)`；同键同结果；`graph_expand_cluster` **不得修改 S5 导航状态/stack**（只返回一次 drill 的只读结果）；写请求一律 `GRAPH_WRITE_FORBIDDEN`。
- **机检**：幂等；无 nav 状态变更；写 forbidden。

### R-S7-6 默认值与指标归属（P2）
- **裁决**：token 默认 `max_tokens=4000`、`max_nodes=200`（S8 可调）；G7 与 G6 字段关系：G7 为 agent 侧事件/快照，引用 G6 `run_ids/frame_ids`，不复制事实；G7 阈值/隐私保留归 S8；S9 `candidate_ref` schema 归 S9，S7 只消费。
- **机检**：默认值可配置；G7 引用 G6；不夹带 S9/S10。

## 2. 修订轮任务

**A-v2**：加 `graph_resolve_ref`；统一 edges=shown+suppressed_summary+explain；工具名/错误表对齐 S6 + S6-ADDENDUM-1；字段统一；幂等/导航边界；默认值/G7 归属。
**B-v2**：吸收 A 的 5 工具/错误表/引用解析；明确 AgentQuery 读路径；修正 path 取舍（v1 无）；字段/幂等/降级对齐。
**SE（task-328）**：等 v2 齐后出工具接口/G7 草案 + DFD/状态图 + `PARSE_OK`。

## 3. S7 冻结门禁

1. A-v2/B-v2 关闭 R-S7-1..6（逐条证据）；
2. SE 工程校核 PASS；
3. Lead 独立机检（只读边界、查询语义、引用可解析、edges 口径、错误表、幂等、G7）；
4. 与 S0–S6 无冲突（S6-ADDENDUM-1 只扩错误码）；
5. 冻结 `S7-agent-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0–S6 冻结稿（仅 S6-ADDENDUM-1 扩错误码）；S7 冻结前不开工实现；修订保留旧版。
