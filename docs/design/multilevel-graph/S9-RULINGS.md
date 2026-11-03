# S9 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S9-charter.md`；
> 上游冻结 S0–S8（`241b1e1e…/6676c71d…/92bb0041…/0ca4ea0e…/2576f6c8…/7f4c4515…/40f12e5f…/70dd8748…/c6a135ff…`）。
> **输入**：提案 A（`fa2d2092…`）、提案 B（`a95545dd…`）、异议（`bb7728cd…`）。
> **状态**：S9 **未冻结**；两版无 P0，2 条 P1 + 1 条 P2 需冻结前修。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 budget 缺 max_tokens | 读 A S9-2/S9-7 与 S7/S8 | **成立**：S9 若不截 token，S7 二次截断/G7 A-TOKEN 无法归因 |
| P1-2 评估不可执行 | 读 A/B S9-10 | **成立**：只有指标名，无命令/exit/golden 路径/sha/阈值/回归 |
| P2-3 枚举未统一（query_type/filters/status） | 读 A/B S9-2 | **成立**：S7/S8 消费会分叉 |
| 其余点名 | 边界/索引/semantic-only/权限/失败/一致性/S10 | 方向 PASS；P2 合并 |

## 1. 跨议题裁决（R-S9-1..R-S9-5）

### R-S9-1 `budget.max_tokens`（P1-1）
- **裁决**：`RetrievalRequest.budget` 冻结为 `{max_candidates, max_tokens=4000, max_latency_ms=500, cursor?}`；超 token 返回 `truncated=true, reason="token_budget"`；与 S7 默认 4000 一致；G7 可归因；机检截断可见。

### R-S9-2 评估可执行（P1-2）
- **裁决**：S9-10 冻结 **eval 契约**：golden 路径 `docs/design/multilevel-graph/golden/S9-golden-set.json`（或 `.memoria/agent/audit/graph/golden/`，S9a 定稿唯一）、golden schema、`eval-retrieval` 命令/exit code、指标 JSON + sha、阈值/回归容差、2× 确定性复跑、无 semantic 数据集单列；S8 gate 引用该命令/产物。
- **机检**：golden 存在且 sha 可复算；eval exit=0；指标 JSON；2× 一致。

### R-S9-3 枚举/schema 统一（P2-3）
- **裁决**：
  - `query_type ∈ {keyword, vector, graph, hybrid}`（**不含 lookup**；`graph` = 单 seed semantic 1 跳）；
  - `filters` 固定字段 `{kb_id, level_id?, view_family_id?, dimension_id?, file?, section?, anchor?, kind?}`；`kind` 与 S7 candidate kind 对齐；
  - `candidate.kind ∈ {kp, cluster, edge, file, anchor}`；`candidate.status ∈ {ok, degraded, unknown}`；`data_state` 按 S6；
  - `tie-break = (score desc, hop asc, kind, canonical_id)`；
  - `ref_type` 弃用，统一 `kind`；
  - 延迟/超时字段统一 `max_latency_ms`（默认 500）。
- **机检**：枚举唯一；schema 白名单；S7/S8 可消费。

### R-S9-4 召回/权重/多 seed（P2）
- **裁决**：v1 graph 召回**单 seed + semantic 1 跳**；多 seed 需 S4/S5 对齐后另开修订；hybrid 权重 `0.4/0.4/0.2` 为**假设值**，需 golden 校准；结构/引用边语义贡献=0；embedding `model_id/dim/license` 记录；无 semantic 返回 KP-only + 可见降级。

### R-S9-5 错误码/索引/一致性（P2）
- **裁决**：错误码只用 S6 `GRAPH_*`；新码须 `S6-ADDENDUM`；索引只写 `.memoria/cache/graph/retrieval/`、可重建、edition 绑定、原子切换、不写 sidecar；增量/全量重建由 S9a 定稿；S10 写后 edition 失效触发重建。

## 2. 修订轮任务

**A-v2**：加 `max_tokens`/`max_latency_ms`；eval 可执行契约；enum/filter/status/tie-break 统一；单 seed+1 跳/权重假设；错误码/索引一致性。
**B-v2**：同口径 enum；eval 契约；max_tokens/延迟统一；补 A 的 schema/评估指标；无 lookup；更新差异清单。
**SE（task-338）**：等 v2 齐后校核 + 接口/索引/评估图 + `PARSE_OK` + golden set 草案。

## 3. S9 冻结门禁

1. A-v2/B-v2 关闭 R-S9-1..5（逐条证据）；
2. SE 工程校核 PASS（接口/schema/索引/评估/一致性，mermaid）；
3. Lead 独立机检（边界/schema/枚举/semantic-only/预算/评估/失败/一致性）；
4. 与 S0–S8 无冲突；
5. 冻结 `S9-retrieval-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0–S8 冻结稿；S9 冻结前不开工实现；修订保留旧版。
