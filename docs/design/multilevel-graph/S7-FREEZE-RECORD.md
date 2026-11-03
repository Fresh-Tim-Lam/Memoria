# S7 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S7-agent-v1.md`（12 条规范 + R-S7-1..9 + 5 只读工具 + S7a + G7 草案）。
> **冻结时间**：2026-11-03T22:23+08:00（Asia/Shanghai）。
> **决策**：`dec-20261103-f87421c1`（Lead；S0–S6 已冻结）。
> **状态**：**已冻结**。0.5/agent 能力实现可引用；S8（度量/验收）可开。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S7-agent-v1.md`（**冻结稿最终态**） | S7 唯一规范来源 | `70dd8748053d7631cf941f1ff743ed5b9b5e165d39492d98018f0dc0cff0c2d3` |
| `S7-engineering-check.md` | SE 工程校核 + S7a + G7 | `00b2bb85…` |
| `S7-agent-proposal-A-v2.md` | 证据链（主办研究） | `605f0032…` |
| `S7-agent-proposal-B-v2.md` | 证据链（独立复核） | `8c1ada34…` |
| `S7-objections-v2.md` | 差异/异议 | `849cfecb…` |
| `S7-RULINGS.md` | Lead 裁决（R-S7-1..6 + 剩余 P1 收口） | `4067b810…` |
| `S6-ADDENDUM-1.md` | 错误码扩展（S7 工具码） | `f9918dfd…` |
| `ENGINEERING-PLAN.md`（S7a） | 24 图 + G7 接口清单 | `a6c628b5…` |

**冻结轮次**：两版无 P0；第一轮 3 条 P1 裁决（resolve_ref、edges 口径、工具/错误码对齐）；修订 v2 后剩 2 条 P1，Lead 在冻结候选以 **R-S7-7/8/9** 收口（expected_edition、source_excerpt≤500、ViewResponse/SummaryResponse 字段）；SE M-S7-1..12 全 PASS、24 图 `PARSE_OK`；Lead 独立机检（12 条款、R-S7-1..9、5 工具、无 path、edges 口径、edition、excerpt、错误表、G7）PASS。

## 2. S7 冻结了什么（一句话版）

1. **v1 agent 只读**：唯一读路径 AgentQuery → DataSource/索引；不读文件系统、不写 sidecar/registry/cache；写 `GRAPH_WRITE_FORBIDDEN`；
2. **5 个只读工具**（snake_case）：`graph_focus`、`graph_explain_edge`、`graph_expand_cluster`、`graph_summary`、`graph_resolve_ref`；**v1 无 `graph_path`**、无隐式多跳；
3. **ViewResponse**：`edges[]` 只含 shown；suppressed/unknown 只给 counts + `suppressed_summary/rule_histogram`，逐条由 `graph_explain_edge` 受控解释；含 `kb_id`、`view_model_id`、`frame_id`（仅审计）、`clusters[]`、`data_state`、`truncated`、`edition_sha`、`audit_id`；
4. **预算**：`max_tokens=4000/max_nodes=200`（S8 可调）；超预算先 summary 再显式 truncated/omitted；禁止静默截断；
5. **edition/幂等**：工具可选 `expected_edition`，响应/审计回带 `edition_sha`；不匹配 `GRAPH_EDITION_STALE`；幂等键 `(tool,args,edition,budget)`；每次调用 append-only 审计（失败 `GRAPH_TOOL_AUDIT_FAILED`）；
6. **错误表**：S6 `GRAPH_*` + `S6-ADDENDUM-1` 六新码；legacy/i18n/severity/audit_id；未知 `GRAPH_INTERNAL`；
7. **引用**：`claim_type ∈ {graph_relation, source_assertion}`；graph_relation 用 cluster_key/run_id；source_assertion 用 kp/file/line/anchor + `source_excerpt≤500`（只读、不缓存正文、审计）；stale/unknown 显式；
8. **写权限**：v1 不可写；S10 才有写工具；禁 sidecar/registry；
9. **与 S9**：S7 只消费；S9 给 candidate/召回；错误/空结果可见降级；无 semantic 时 KP-only、无簇；`candidate_ref` 归 S9；
10. **与 S10**：S10 设计/写 KP/语义边；写后 edition 失效 `GRAPH_EDITION_STALE`；刷新触发方由 S10 定；
11. **多维度/多归属**：默认 H；A 显式 `dimension_id`；`scope_note`；`memberships[]`，不把一维当全局；
12. **降级/G7**：no_semantic/预算/数据缺失/unknown/retrieval 不可用均显式、不编造；`G7_EVENT/SNAPSHOT` 引用 G6 `run_ids/frame_ids`，不复制事实；阈值/隐私归 S8。

## 3. 机检与证据

- SE M-S7-1..12 全 PASS（`M_fail=[]`）；S7a：ER-08/DF-08/ST-08 + G7；mermaid 11.16.0（`9198f632…`）**24 图 `PARSE_OK`**；
- 与 S0–S6 一致性：单一真源/D-3/D-4、S4 focus-only、S5 frame_id/事务化、S6 错误/路径、S3 VM 纯度、S6-ADDENDUM-1 — 全 PASS；
- Lead 独立机检 PASS。

## 4. 未关闭项（不阻塞冻结）

- O-S7-1..8：token 默认值 S8 校准、`allow_two_hop` 未来修订、excerpt 截断规范、stale 语义细节、S9 candidate schema、S10 写后 edition 失效、G7 隐私、审计失败回退。

## 5. 变更控制

- 加工具/字段/错误码：S7 修订 + 决策（新码同时登记 S6-ADDENDUM）；删/改只读边界/引用/写权限：重开 S7。

## 6. 下一步

- **S8（度量/验收）**：G6/G7 阈值、性能/正确性/可解释性验收、快照复跑；
- 之后 S9（后端检索）、S10（agent 设计知识点）；
- 0.5 实现计划（S6a I-01..I-13）可继续。
