# S6 增补 2（S6-ADDENDUM-2）：`GRAPH_*` 错误命名空间扩展（S10 KP/边/curation）

> **性质**：S6 变更控制允许的「加失败码」修订（`S6-contract-v1.md` §6），**不重开 S6、不改 S0–S9 语义**。
> **依据**：S6 §S6-9（`GRAPH_*` canonical）；S10 冻结候选 R-S10-2；S6/S7 两个既有 ADDENDUM。
> **状态**：随 S10 一并冻结；S6 身份仍为 `40f12e5f…` + ADDENDUM-1/2。

## 1. 新增 S10 错误码（append-only）

| code | 触发 | legacy 映射 | severity | i18n |
|---|---|---|---|---|
| `GRAPH_KP_INVALID` | KP 字段/范围/锚非法 | `GRAPH_INTERNAL` | error | `graph.kp.invalid` |
| `GRAPH_KP_DUPLICATE` | 同 id/同 name 重复 KP 未合并 | `GRAPH_INTERNAL` | warn | `graph.kp.duplicate` |
| `GRAPH_KP_EVIDENCE_MISSING` | KP 提案无 file/line/anchor | `GRAPH_INTERNAL` | error | `graph.kp.evidence_missing` |
| `GRAPH_KP_AMBIGUOUS` | 锚点歧义/多候选无法唯一 | `GRAPH_INTERNAL` | warn | `graph.kp.ambiguous` |
| `GRAPH_KP_LOW_CONFIDENCE` | 低于阈值，不 apply | `GRAPH_INTERNAL` | warn | `graph.kp.low_confidence` |
| `GRAPH_EDGE_INVALID` | 边 type/direction/字段非法 | `GRAPH_INTERNAL` | error | `graph.edge.invalid` |
| `GRAPH_EDGE_DUPLICATE` | 同 pair/同 type 重复 | `GRAPH_INTERNAL` | warn | `graph.edge.duplicate` |
| `GRAPH_EDGE_EVIDENCE_MISSING` | 边无 evidence/assertion_source | `GRAPH_INTERNAL` | error | `graph.edge.evidence_missing` |
| `GRAPH_EDGE_SEMANTIC_MISMATCH` | 结构/引用边标 semantic | `GRAPH_INTERNAL` | error | `graph.edge.semantic_mismatch` |
| `GRAPH_CURATION_CONFLICT` | 冲突未裁决 | `GRAPH_INTERNAL` | warn | `graph.curation.conflict` |
| `GRAPH_CURATION_APPROVAL_REQUIRED` | 无人确认即 apply | `GRAPH_INTERNAL` | error | `graph.curation.approval_required` |
| `GRAPH_CURATION_PRIVACY_REJECTED` | PII/正文边界违规 | `GRAPH_INTERNAL` | error | `graph.curation.privacy_rejected` |
| `GRAPH_CURATION_BUDGET_EXCEEDED` | 提案超预算 | `GRAPH_INTERNAL` | warn | `graph.curation.budget_exceeded` |
| `GRAPH_CURATION_ROLLBACK_FAILED` | 回滚失败，零写入校验失败 | `GRAPH_INTERNAL` | error | `graph.curation.rollback_failed` |

- 已有 S6/S7/S10 码不变；未知 `GRAPH_INTERNAL`；所有码带 `audit_id`；
- 禁止 `S10_*` 平行命名空间；新码只增不删。

## 2. 变更控制

- 本增补只扩错误码表；改语义/删码须重开 S6/S10；S6 身份 = 原 sha + ADDENDUM-1/2。
