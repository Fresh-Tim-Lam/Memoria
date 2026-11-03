# S6 增补 1（S6-ADDENDUM-1）：`GRAPH_*` 错误命名空间扩展（S7 工具错误码）

> **性质**：S6 变更控制允许的「加失败码」修订（`S6-contract-v1.md` §6），**不重开 S6、不改 S0–S5 语义**。
> **依据**：S6 §S6-9（`GRAPH_*` canonical + legacy 映射）；S7 冻结候选 R-S7-3；S6 freeze `dec-20261103-a991904b`。
> **状态**：随 S7 一并冻结；S6 身份仍为 `40f12e5f…` + 本增补。

## 1. 新增 S7 工具错误码（append-only）

| code | 触发 | legacy 映射 | severity | i18n |
|---|---|---|---|---|
| `GRAPH_TOOL_INPUT_INVALID` | 工具参数缺失/非法/越界 | `GRAPH_INTERNAL`（旧无对应） | error | `graph.tool.input_invalid` |
| `GRAPH_TOOL_BUDGET_EXCEEDED` | `max_tokens/max_nodes` 连 summary 都无法满足 | `GRAPH_BUDGET_INVALID` | warn | `graph.tool.budget_exceeded` |
| `GRAPH_ANCHOR_STALE` | 引用 anchor 对应版本已失效 | `GRAPH_EDITION_STALE` | warn | `graph.tool.anchor_stale` |
| `GRAPH_RETRIEVAL_UNAVAILABLE` | S9 检索不可用/超时 | `GRAPH_INTERNAL` | error | `graph.tool.retrieval_unavailable` |
| `GRAPH_WRITE_FORBIDDEN` | agent 尝试写图/curation（v1 只读） | `GRAPH_INTERNAL` | error | `graph.tool.write_forbidden` |
| `GRAPH_TOOL_AUDIT_FAILED` | 工具调用审计落盘失败 | `GRAPH_INTERNAL` | error | `graph.tool.audit_failed` |

- 已有 S6 码（`GRAPH_FRAME_ID_INVALID`、`GRAPH_PRESENCE_INVALID`、`GRAPH_SUBSET_VIOLATION`、`GRAPH_BUDGET_INVALID` 等）**不变**；
- 未知错误仍 `GRAPH_INTERNAL`；所有码必须带 `audit_id`；
- 机检：S7 错误表逐码可解析；新增码只增不删；i18n key 存在。

## 2. 变更控制

- 本增补只扩错误码表；改语义/删码须重开 S6；S6 身份 = 原 sha + 本增补。
