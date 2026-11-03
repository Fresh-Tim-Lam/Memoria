# S6 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S6-contract-v1.md`（12 条规范 + R-S6-1..6 + S6a ER/DFD/状态图 + 0.5 接口清单 I-01..I-13）。
> **冻结时间**：2026-11-03T22:00+08:00（Asia/Shanghai）。
> **决策**：`dec-20261103-a991904b`（Lead；S0–S5 已冻结）。
> **状态**：**已冻结**。S0–S6 **全部冻结**；可进入 0.5 实现计划（S7–S10 仍按议程后续）。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S6-contract-v1.md`（**冻结稿最终态**） | S6 唯一规范来源 | `40f12e5fd5946c8cc4ebdb71800579d3e9098f74ef7381ad65a2e51f389db82b` |
| `S6-engineering-check.md` | SE 工程校核 + S6a 定稿（ER-07/DF-07/ST-07、I-01..I-13） | `b9125610…` |
| `S6-contract-proposal-A-v2.md` | 证据链（主办研究） | `9e71d540…` |
| `S6-contract-proposal-B-v2.md` | 证据链（独立复核） | `4e262068…` |
| `S6-objections-v2.md` | 差异/异议（含 role 撤回） | `a495564b…` |
| `S6-RULINGS.md` | Lead 裁决（R-S6-1..6） | `93d89efa…` |
| `ENGINEERING-PLAN.md`（S6a） | 21 图 ER/DFD/ST + 0.5 接口清单 | `3b3e0f68…` |

**冻结轮次**：A 无 P0；3 条 P1 中 **2 条成立**（nav_id→frame_id、FRAME_SPEC 超界）、**1 条不成立**（B 误读 S3 role；S3 原文 `role∈{member}`，focus 是 Presentation 瞬态，B 已撤回）；修订 A-v2/B-v2 后 R-S6-1..6 全关闭；SE M-S6-1..12 全 PASS、S6a 21 图 `PARSE_OK`；Lead 独立机检（12 条款、单一真源、S4_FRAME_SPEC、frame_id、role=member、签名、路径、GRAPH_*、G6、0.5 边界）PASS。冻结身份取 `40f12e5f…`。

## 2. S6 冻结了什么（一句话版）

1. **单一真源**：事实只来自 `.md` + `.memoria` sidecar/manifest（只读）；DataSource 只读；GraphView/run/VM 派生；Frame/Nav 是视图状态；**禁并行事实源、禁 D-3 写 sidecar**；
2. **DataSource/GraphView**：`(level,view_family)` partition、`E_relation_min`、`kind∈{kp,cluster}`、`data_state`；
3. **registry/history**：S1 全字段；history append-only、`content_sha` 链、可选 `signature?`（detached `<content_sha>.sig` 或 entry 字段；`content_sha` 不含签名）；只增不删；失败码 `GRAPH_HISTORY_SIGNATURE_INVALID`；
4. **run/membership**：run 六元组 `run_id` 可复算；membership 多归属；`cluster_id=run:local_seq` + `cluster_key`；五状态；curation 双引用；
5. **Visual/VM**：S3 白名单 + `S3-ADDENDUM-1` 节点 presence/rule_id；`role:"member"`（focus 非 VM role）；`data_edge_ids` 审计但 Renderer 禁读；
6. **Frame**：`S4_FRAME_SPEC` **严格 S4 字段**；`frame_id=sha256(canonical(S4_FRAME_SPEC))` 由 **S5 派生**；`edition` 本地；**不进 S4 输入**；
7. **Nav**：`frame_id` 统一（禁 `nav_id` schema）；9 主状态 + 正交 mode/data_state；T01–T30 唯一真源、S5a 148 边；持久化白名单；
8. **存储**：`.memoria/cache/graph/`（派生可删重建，GC 20 run/90 天）、`.memoria/config/graph/`（registry/history，永不 GC）、`.memoria/agent/audit/graph/`（append-only，不 GC）；旧 graph-groups/build 不迁移、只读 fallback 默认关闭；
9. **错误**：`GRAPH_*` canonical + `legacy_code` 映射；未知 `GRAPH_INTERNAL`；i18n 归 UI；
10. **G6**：快照字段/阈值冻结（determinism=100%、subset_ok=true、closure/behind=0、history_signed）；
11. **0.5 边界**：2D 先发；3D 只留同签名接口 + `capability=false`；不做 agent 写/自动 semantic/跨库/时间维/图编辑器/破坏性迁移；S7–S10 不在 0.5；
12. **S6a**：ER-07/DF-07/ST-07 定稿 + 0.5 接口清单 I-01..I-13。

## 3. 机检与证据

- SE M-S6-1..12 全 PASS（`M_fail=[]`）；S6a 同版本 mermaid 11.16.0（`9198f632…`）**21 图 `PARSE_OK`**；
- 与 S0–S5 一致性：S0 单一真源/D-3/D-4/R-1/R-3、S1 registry/history、S2 run/五状态/多归属、S3 VM 白名单+ADDENDUM-1/role=member/禁读、S4 frame_spec/presence/subset、S5 frame_id/T01–T30/事务化/持久化 — 全 PASS；
- Lead 独立机检 PASS。

## 4. 未关闭项（不阻塞冻结）

- O-S6-1..8：history key 管理、cache GC 并发/回退、legacy 映射表细节、G6 复跑脚本、URL/书签、focus 恢复细节、旧 build 清理、3D UI 降级。

## 5. 变更控制

- 加 schema 字段/失败码：S6 修订 + 决策；删/改单一真源/迁移/0.5 边界：重开 S6；S6a 工程定稿不改语义。

## 6. 下一步

- **S0–S6 全部冻结** → 进入 **0.5 图谱板块实现计划**（按 I-01..I-13 顺序；2D 先发）；
- S7（agent 使用）/S8（度量）/S9（后端检索）/S10（agent 设计知识点）仍按议程后续；
- 实现前先写 0.5 实现计划与任务拆分（Lead + todo-owner）。
