# S9 章程：后端检索（候选召回、排序、过滤、预算、评估与一致性）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结**：S0–S8 九份 v1（+ S3-ADDENDUM-1、S6-ADDENDUM-1），**不得违反**；逐议项（U-34）。
> **状态**：S9 章程 V1（Lead 起草）。本场冻结前不写产品代码。
> **日期**：2026-11-04（Asia/Shanghai）。

## 1. 目的

冻结**后端检索层**：给 S7 的 agent 查询提供候选/召回/排序，不改变图谱语义；定义检索接口、索引/存储、召回与排序策略、过滤/权限、预算/延迟、与图谱（S4/S5/S6）的交互、失败降级、更新一致性、评估与回归。
S9 只产出 **candidate/ranking**，最终取景/presence 仍由 S4；agent 工具契约仍由 S7。

## 2. 不在范围

- agent 工具面/引用契约（S7 已冻结）；
- 图谱取景/presence（S4）、导航（S5）、数据契约（S6）；
- agent 设计知识点/语义边（S10）；
- UI（S3–S5）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：定义/规则、机检条件、反例、边界用例、U 映射、建议裁决、证据等级。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S9-1 | 定位与边界 | 检索只给 candidate/ranking；不写图谱/不改事实；与 S7 `candidate_ref`、S4 取景、S10 写入的边界；单一真源（S6） |
| S9-2 | 检索接口 | 输入/输出 schema：query/query_type、kb_id、dimension/filters、budget、`expected_edition`；输出 `candidate_ref`（kp/cluster/edge/file/anchor/score/reason）；分页/游标 |
| S9-3 | 索引/存储 | 索引类型（FTS/embedding/graph adjacency）、存放路径（S6 cache/config 域）、可重建、edition 绑定；不得写 sidecar |
| S9-4 | 召回策略 | keyword/vector/graph expand/hybrid；图谱关系如何参与召回；无 semantic edges 时的行为；不得伪造语义 |
| S9-5 | 排序/打分 | 分数来源/归一化、确定性、tie-break、score 可解释；不得把结构/引用边当语义分数；校准 |
| S9-6 | 过滤/权限/范围 | kb/level/view_family/dimension/file/section/anchor 过滤；越权/不存在的可见失败；不泄漏隐藏内容 |
| S9-7 | 预算/延迟/分页 | token/候选数/延迟预算；超预算显式截断/降级；分页游标稳定；冷/热 |
| S9-8 | 与图谱交互 | candidate 与 S4/S5/S6 的 id 对齐（kp/cluster/run/edge/frame）；expand 时如何取候选；不绕过 S4 取景 |
| S9-9 | 失败/降级 | 索引缺失/stale/edition 不匹配/无 semantic/不可用；`GRAPH_RETRIEVAL_UNAVAILABLE`/可见降级；不编造 |
| S9-10 | 评估/回归 | retrieval quality 指标（recall@k/NDCG/MRR/coverage）golden set；确定性；S8 只消费；阈值/回归 |
| S9-11 | 缓存/更新/一致性 | 增量更新/失效、edition、重建、并发；不写事实源；audit |
| S9-12 | 与 S10 边界 | S10 写语义边/KP 后如何触发重建/失效；S9 不设计 KP；刷新由 S10 触发、S9 消费 |

## 4. 预注册判据（会前写死）

1. 检索只产出 candidate/ranking，不写图谱/不改事实；与 S7/S4/S6 边界明确；
2. 接口 schema 含 `candidate_ref/score/reason/edition`，可机检；分页稳定；
3. 索引可重建、路径在 S6 派生域、edition 绑定；不写 sidecar；
4. 召回/排序确定性、tie-break 明确；**semantic-only**：结构/引用边不得当语义分数/召回；
5. 过滤/权限可见失败；不泄漏隐藏内容；
6. 预算/延迟/分页显式；超预算降级可见；
7. 失败/降级覆盖索引缺失/stale/edition/无 semantic/不可用；
8. 评估 metrics/golden set/阈值明确（S9 定义，S8 消费）；确定性；
9. 缓存/更新/并发/审计明确；与 S10 边界；
10. 两份独立提案差异逐条裁决；SE 校核 PASS；
11. 不写产品代码、不改契约、不 commit。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游冻结：S0–S8 九份 v1 + 两 ADDENDUM；
- 工程：`ENGINEERING-PLAN.md`（27 图 + I-01..I-13）；S8 G6/G7 规范；
- 现有检索面：`src/memoria/services/**` 检索/索引实现（只读证据）。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S9-retrieval-proposal-A.md` + 证据 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S9-retrieval-proposal-B.md` + `S9-objections.md` |
| 软件工程专家 | `graph-se-architect` | `S9-engineering-check.md` + 检索/索引/评估图 + `PARSE_OK` |
| 并集与裁决 | Lead | `S9-RULINGS.md` → `S9-retrieval-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS（接口/索引/评估/一致性，与 S0–S8 一致）；
3. Lead 独立机检（边界/schema/确定性/semantic-only/失败/评估/一致性）；
4. 与 S0–S8 无冲突；
5. 满足后冻结 `S9-retrieval-v1.md` 并写决策。

## 8. 变更控制

- 加接口/指标/阈值：S9 修订 + 决策；删/改检索边界/分数语义/索引域：重开 S9；
- 本场无产品代码；0.5 实现按 S6a + S8 DoD，检索实现按 S9 冻结。
