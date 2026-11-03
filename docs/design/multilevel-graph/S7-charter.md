# S7 章程：agent 如何使用图谱（读写边界、查询接口、token 经济、证据契约）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结**：S0（`241b1e1e…`）、S1（`6676c71d…`）、S2（`92bb0041…`）、S3（`0ca4ea0e…`+ADDENDUM-1）、S4（`2576f6c8…`）、S5（`7f4c4515…`）、S6（`40f12e5f…`），**不得违反**；逐议项（U-34）。
> **状态**：S7 章程 V1（Lead 起草）。本场冻结前不写产品代码。
> **日期**：2026-11-03（Asia/Shanghai）。

## 1. 目的

冻结 **agent 侧如何使用已冻结的图谱**：读什么层、怎么查询/展开、token 预算、证据/引用契约、写权限边界、与 S9（后端检索）/S10（agent 设计知识点）的接口。
S7 不设计新图谱语义，只定义 **agent 消费图谱的契约**。

## 2. 不在范围

- 后端检索实现（S9）；
- agent 设计知识点（S10）；
- 度量与验收阈值（S8 给指标；S7 只给 agent 侧可观测项）；
- 图谱 UI（S3/S4/S5 已冻结）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：定义/规则、机检条件、反例、边界用例、U 映射、建议裁决、证据等级。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S7-1 | 定位与边界 | agent 只读还是可写？v1 只读（curation 由人工/后续 agent 写，S10）；不得绕过 DataSource 事实；不得写 sidecar；与 S0/S6 单一真源一致 |
| S7-2 | agent 可见层 | agent 能看 DataSource/GraphView/VM/Frame 哪些层？默认看「View + presence/rule_id 解释」，不直接看 raw 边；不得把 VM 当事实 |
| S7-3 | 查询接口 | 最小查询集：`focus/one-hop`、`explain(edge)`、`expand(cluster)`、`path?`（如需要）；必须复用 S4 focus-only 与 S5 导航语义；多跳仅显式 |
| S7-4 | 展开与预算 | token 预算（上下文/单次调用）；层级摘要（cluster label/member_count）；`suppressed/unknown` 如何解释；禁止静默截断 |
| S7-5 | 工具面（MCP/内部） | 工具名/参数/返回 schema；只读工具 vs 写工具；错误码 `GRAPH_*`；幂等；审计（每次调用可追溯） |
| S7-6 | 写权限边界 | v1 agent **不可写图**；若允许 curation，只能走 S10 定义的工具 + 审计/人工确认；禁止直接改 sidecar/registry |
| S7-7 | 证据/引用契约 | 回答必须带 `kp_id + file + line`（或 anchor）与 `cluster_key/run_id`；区分「图谱关系」vs「原文断言」；不确定/unknown 必须显式 |
| S7-8 | 与 S9 检索接口 | S7 只定义 agent 消费契约；S9 提供候选/召回；接口边界、错误传播、无 semantic edges 时的降级 |
| S7-9 | 与 S10 边界 | S10 设计/写入知识点与语义边；S7 只读消费；写后版本/edition 失效与刷新 |
| S7-10 | 多维度/多归属 | agent 如何选 dimension/view_family；多归属簇如何解释；不得把某一维当全局 |
| S7-11 | 失败/降级 | `no_semantic_edges`、预算不足、数据缺失、unknown 关系：agent 必须可见地降级，不得编造 |
| S7-12 | 可观测/验收 | agent 侧指标：工具调用数、token、命中率、引用完整率、unknown 比例；S8 统一阈值；G7 快照草案 |

## 4. 预注册判据（会前写死）

1. v1 agent **只读**；写路径不存在或受 S10 工具+审计约束；
2. agent 只看 View/解释层，不把 VM/缓存当事实；不绕过 DataSource；
3. 查询复用 S4/S5 语义（focus 一跳、无隐式 2 跳、presence/rule_id 可解释）；
4. 引用契约可机检（kp_id/file/line 或 anchor；cluster_key/run_id）；
5. token 预算与截断可见；unknown/降级显式，不编造；
6. 工具 schema/错误码与 S6 `GRAPH_*` 一致；调用可审计；
7. 与 S9/S10 接口边界明确；不夹带 S9/S10 设计；
8. 两份独立提案（A/B）差异逐条列出并裁决；
9. 覆盖矩阵（U-2/3/6/10/11/12/13/14/15/17/19/27/32 等）无缺失；
10. SE 工程校核 PASS（工具/状态/DFD，不含产品实现）；
11. 不写产品代码、不改契约、不 commit。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游冻结：S0–S6 七份 v1 + FREEZE-RECORD + S3-ADDENDUM-1；
- 工程：`ENGINEERING-PLAN.md`（21 图 + I-01..I-13）；
- 现有 agent 面：`resources/agent-prompts/**`、`agent-capabilities/*.json`、MCP/工具实现（只读证据）。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S7-agent-proposal-A.md` + 证据 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S7-agent-proposal-B.md` + `S7-objections.md` |
| 软件工程专家 | `graph-se-architect` | `S7-engineering-check.md` + 工具/DFD/状态图增量 |
| 并集与裁决 | Lead | `S7-RULINGS.md` → `S7-agent-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS（工具 schema/DFD/状态/与 S0–S6 一致）；
3. Lead 独立机检（只读边界、查询语义、引用契约、token/降级、错误码、审计）；
4. 与 S0–S6 无冲突；
5. 满足后冻结 `S7-agent-v1.md` 并写决策。

## 8. 变更控制

- 加工具/查询/指标：S7 修订 + 决策；删/改写权限/引用契约/只读边界：重开 S7；
- 本场无产品代码；实现按 0.5/后续计划。
