# S6 章程：数据契约收尾（ER/DFD 定稿、schema、存储/审计/GC、0.5 交付边界）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结**：S0（`241b1e1e…`）、S1（`6676c71d…`）、S2（`92bb0041…`）、S3（`0ca4ea0e…`+ADDENDUM-1）、S4（`2576f6c8…`）、S5（`7f4c4515…`），**不得违反**；逐议项（U-34）。
> **状态**：S6 章程 V1（Lead 起草）。本场冻结前不写产品代码。
> **日期**：2026-11-03（Asia/Shanghai）。S6 是 S0–S6 的收尾场；冻结后进入 0.5 图谱板块实现。

## 1. 目的

把 S0–S5 冻结语义收口成**可实现的数据契约**：ER/DFD/状态图定稿、DataSource/VM/frame/presence/registry/run/visual/nav 的 schema、
存储/审计/GC/版本策略、错误与失败码统一、G6 快照与复跑、以及 **0.5 交付边界**（哪些 v1 做、哪些明确不做）。

## 2. 不在范围

- 产品实现（S0–S6 全冻结后另立 0.5 实现计划）；
- S7–S10（agent 使用/度量/后端检索/知识点设计）仍按议程后续；
- 视觉细节（S3 已冻结）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：定义/规则、机检条件、反例、边界用例、U 映射、建议裁决、证据等级；S6a 另出 ER/DFD/状态图定稿。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S6-1 | 契约范围与单一真源 | ER/DFD 覆盖哪些实体；DataSource/VM/frame 的单一真源；禁止并行事实源；与现有 `.memoria` sidecar/manifest 的关系 |
| S6-2 | DataSource / GraphView / C-* 契约 | S0-2 的 `(level,view_family)`、`E_relation_min`、`kind∈{kp,cluster}`、D-2/D-3；DataSource 只读接口 |
| S6-3 | 维度注册表与 history schema | S1 全字段/枚举/失败码；`registry_history` 不可变存储位置/签名/取回；跨版本只增不删校验；S0_REOPEN 触发 |
| S6-4 | 簇 run / membership / 身份 schema | S2 run_id 公式、params_hash 字段集、membership 多归属、cluster_key、stale/curation 引用；失败五状态 |
| S6-5 | Visual / VM schema | S3 白名单 + `S3-ADDENDUM-1` 节点 presence/rule_id；token/encoding map；`data_edge_ids` 审计但 Renderer 禁读；2D/3D capabilities |
| S6-6 | Frame / presence / rule_id schema | S4 候选节点/边、presence 三值、11 类 rule_id、MANDATORY、budget、subset reserved、失败码 |
| S6-7 | Nav schema | S5 `GraphNavFrame`/`NAV_STACK_ENTRY`/`NAV_EVENT`、T01–T30 表↔图生成、frame_id 派生、持久化白名单 |
| S6-8 | 存储/审计/GC/版本 | 派生缓存位置/可重建；审计日志（决策/curation/agent 请求）；GC/清理；edition/stale；D-3 禁写产品 sidecar |
| S6-9 | 错误/失败语义统一 | S2/S3/S4/S5 失败码统一命名空间；fail-closed vs 降级 vs 回退；用户可见文案归属 i18n |
| S6-10 | 兼容/迁移 | 旧 graph-groups/旧图谱数据是否迁移/忽略；edition 兼容；无破坏性迁移；回滚 |
| S6-11 | G6 快照/复跑/度量 | 快照内容（DataSource/run/registry/visual/nav/frame）、sha、复跑命令、验收阈值 |
| S6-12 | 0.5 交付边界 | v1 实现范围（视图/导航/选择渲染/agent 接口优先级）、明确不做项、验收门禁；S6a ER/DFD 定稿 + 与实现的接口清单 |

## 4. 预注册判据（会前写死）

1. ER/DFD/状态图定稿且与 S0–S5 逐条一致；同版本 mermaid `PARSE_OK`；
2. 每个 schema 有字段/类型/枚举/默认/失败码；单一真源；无并行事实源；
3. 存储派生缓存可删除后重建；D-3 不写产品 sidecar；审计可追溯；
4. 失败码统一命名空间并映射到 S2–S5；
5. G6 快照可复跑、sha 稳定；验收阈值明确；
6. 0.5 交付边界明确（做/不做/依赖），不夹带未冻结语义；
7. 两份独立提案（A/B）差异逐条列出并裁决；
8. 覆盖矩阵（S0–S5 全部 U 相关 + U-32/34 等）无缺失；
9. SE 工程校核 PASS（含 S6a 定稿）；
10. 不写产品代码、不改契约、不 commit。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游冻结：S0–S5 六份 v1 + FREEZE-RECORD + S3-ADDENDUM-1；
- 工程：`ENGINEERING-PLAN.md`（18 图 + ER/DFD/ST 增量）、五份 engineering-check；
- 现有实现：`.memoria/sidecars`/`manifest`、`collector.py`、`edge_derivation.py`、`graph-groups.js`（只读证据）。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S6-contract-proposal-A.md` + 证据 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S6-contract-proposal-B.md` + `S6-objections.md` |
| 软件工程专家（S6a） | `graph-se-architect` | `S6-engineering-check.md` + `ENGINEERING-PLAN.md` ER/DFD/状态图定稿 |
| 并集与裁决 | Lead | `S6-RULINGS.md` → `S6-contract-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS（含 S6a 定稿、mermaid `PARSE_OK`、与 S0–S5 一致）；
3. Lead 独立机检（schema 字段/失败码/单一真源/缓存可重建/G6/0.5 边界）；
4. 与 S0–S5 无冲突；
5. 满足后冻结 `S6-contract-v1.md` 并写决策；**S0–S6 全部冻结 → 进入 0.5 实现计划**。

## 8. 变更控制

- 冻结后加 schema 字段/失败码：S6 修订 + 决策；删/改单一真源/迁移/0.5 边界：重开 S6；
- 本场无产品代码；S0–S6 全冻结前不开工实现。
