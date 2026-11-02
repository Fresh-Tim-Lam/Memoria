# S0 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S0-terms-v1.md`（12 条规范 + R-1..R-3 + D-1..D-5 + U-1..U-35 覆盖矩阵）。
> **冻结时间**：2026-11-02T17:25:46+08:00（Asia/Shanghai）。
> **决策**：`dec-20261102-a6af89e1`（Lead 裁决；人已两次给出原话与流程要求）。
> **状态**：**已冻结**。冻结前不进入 S1、不写产品代码的纪律由本记录确认转段：S0 已完成，S1 可开。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S0-terms-v1.md`（**冻结稿最终态**） | S0 唯一规范来源 | `241b1e1e8b0a2fe6c8e1291e03a06c122d16cf71273d9e5d0d879f64ebf9ea78` |
| `S0-freeze-check.md` | SE 机检报告（M-1..M-12） | 以磁盘为准 |
| `S0-terms-proposal-A-v2.md` | 证据链（主办研究） | `5b3562e2…` |
| `S0-terms-proposal-B-v2.md` | 证据链（独立复核） | `dd713707…` |
| `S0-objections-v2.md` | 差异/异议（复核） | `5d9828e7…` |
| `S0-RULINGS.md` | Lead 第一轮裁决 | `078363aa…` |
| `ENGINEERING-PLAN.md` / `S0-engineering-review.md` | ER/DFD/状态图 v0 + 工程校核 | 以磁盘为准 |

**sha 链说明（重要）**：
- SE 机检（task-294 复跑）通过的是 `ab7538f0…`；
- 其后 Lead 按 SE 的 O-9/O-10 只修正了**覆盖矩阵两条映射锚点**（U-34 → `S0-charter.md` §3/§5 + agenda §5；U-20 → S0-9 nodeClick + S5），**未改任何条款**；
- Lead 用**自写断言**对最终态复检 PASS（35 行覆盖矩阵、U 35/35、E_relation_min、kind、presence、cluster_key、R-1..R-3、VM 纯度、default⊆full、12 条款齐全），最终态 sha 为 `241b1e1e…`；
- 因此冻结身份取最终态 `241b1e1e…`；SE 报告保留 `ab7538f0…` 作为机检证据链。

## 2. 机检结论（SE，M-1..M-12）

- `M_fail = []`、`M_partial = []`、`special_fail = []`；
- **M-11 PASS**：覆盖矩阵 rows=35 / unique=35 / missing=[] / dupes=[]；
- R-1/R-2/R-3 全 PASS；M-1..M-10、M-12 PASS；
- 三张工程图（er / flowchart-v2 / stateDiagram）用**仓库 vendored mermaid 11.16.0**（sha `9198f632…`）解析：`failedBlocks:0`。

## 3. S0 冻结了什么（一句话版）

1. **语义** = T1/T2/T4 + 字段闸门；`reference` 永不算语义；T3 只是消费者准入清单；
2. **层次** = 同一 `(level, view_family)` 内的嵌套划分；**最小粒度 = 知识点**；更深层仅开放槽位；
3. **维度** = 取景规则；v1 可用 H/A、一次只激活一个；**E_relation_min 冻结** = `{contain(structural), contain(semantic), reference, extend}`，S1 只能加不能删；
4. **簇** = 语义内聚 + 零星桥（≠严格连通分量）；身份 = run-scoped id + `cluster_key`；
5. **一跳** = 恰好一条 `E_relation(D)` 边、不闭包、跨维重置、不带背后图；
6. **选择性渲染** = `present(e, ctx)` 唯一判据；`presence ∈ {shown, suppressed, unknown}` + `rule_id`；**视图缺席 ≠ 数据缺席**；全展开也走 present；聚合边须带 `data_edge_ids`；
7. **多归属** = 成员关系 ≠ 视图出现；同视图族单归属、跨族/维可重叠；不设上限；
8. **默认视图** = 层次视图彻底替代旧全展开；全展开是正交开关；同源同 present；
9. **渲染接口** = 单一 `DataSource → ViewModel（纯）→ Renderer`；2D/3D 是同一接口的两个后端；`kind ∈ {kp, cluster}`，bridge 只能是 role/state；
10. **agent** = 三层边界：KP 设计主导 / 语义可写但须证据+审计、不得自动推断 / 取景只能请求确定性服务，不得改渲染状态；
11. **v1 范围外** 15 条；
12. **术语映射** 与兼容/迁移/回滚；三段架构；旧 `graph-groups` ≠ 簇。

## 4. 未关闭项（不阻塞冻结，已登记后续场次）

- `underlying_hop_count` / `HopNetwork` 细节 → S4/S5；
- `expand_data_edges()` 签名 / canonical 序列化 / cluster_key 细则 → S2/S4/S6a；
- T3 消费者准入清单 C-1..C-4 的强度 → S7/S8 评测门槛；
- 维度组合（多维度叠加）→ S1 开放槽位。

## 5. 变更控制（冻结后）

- **加条款**：追加 §1.x + 覆盖矩阵行 + 决策记录，版本升 v1.x；
- **删/改 S0 条款**：必须**重开 S0**（记录原因/影响/回滚），不得在 S1+ 私改；
- 本冻结记录与 `S0-terms-v1.md` 一起构成冻结身份；任何未记录的字节改动都视为破坏冻结。

## 6. 下一步

- S1（维度体系）章程起草 → 人确认议程 → S1 逐议项研讨；S1 只能**增加** `E_relation`，不能删除 R-1 冻结项。
- S0 已完成，按 U-34 流程进入下一场；产品实现仍等 S0–S6 冻结（本记录不放行代码）。
