# S1 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S1-dimensions-v1.md`（15 条规范 + R-S1-1..R-S1-11 + U 覆盖矩阵）。
> **冻结时间**：2026-11-03T19:05+08:00（Asia/Shanghai）。
> **决策**：`dec-20261103-35844b56`（Lead 裁决；S0 已冻结 `dec-20261102-a6af89e1`）。
> **状态**：**已冻结**。S2 可开；S0–S6 冻结前仍不写产品代码。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S1-dimensions-v1.md`（**冻结稿最终态**） | S1 唯一规范来源 | `6676c71d09c5722c5c42252c63158878638e5f4480ce0dade4dd114b94f5a866` |
| `S1-engineering-check.md` | SE 工程校核报告（M-S1-1..12） | `c9020289…` |
| `S1-dimensions-proposal-A-v2.md` | 证据链（主办研究） | `ae5f09e5…` |
| `S1-dimensions-proposal-B-v2.md` | 证据链（独立复核） | `c4cddcaf…` |
| `S1-objections-v2.md` | 差异/异议（复核） | `275a2c7a…` |
| `S1-RULINGS.md` | Lead 第一轮裁决 | `6b2b84bb…` |
| `S0-terms-v1.md` | 上游冻结 | `241b1e1e…` |
| `ENGINEERING-PLAN.md` | ER/DFD/状态图（含 S1 增量） | `708d6f6f…` |

**冻结轮次**：SE 首轮机检 10 PASS / 2 FAIL（schema 字段表缺失、R-S1-11 映射谓词未定义且「非空」不成立）；
Lead 修两处后，SE 复跑 `M_fail=[]、12/12 PASS`；Lead 独立机检（18 行 schema 表、映射谓词、空集合法、
15 条款、R-S1-1..11）PASS。冻结身份取最终态 sha `6676c71d…`。

## 2. S1 冻结了什么（一句话版）

1. **维度 = 取景规则**，判定 M1–M6；`graphStyle`/2D/3D/全展开/level 不是维度；
2. **H（层次导航维）**：`relation_sources=[]`、`direction=down`、无 hop 预算、一次下钻一层；H 派生边 id = `sha256(parent,child,level,view_family)`，`data_edge_ids` 映射谓词已冻结（**允许空集**，字段必须存在、不得伪造 id）；`expand_data_edges(H_vm) ⊆ DataSource.edges`；
3. **A（关联扩展维）**：`relation_sources ⊇ E_relation_min`（contain 两 kind、reference、extend）；`hop_default=1`、`hop_max=2`；**2 跳只能由 S5 唯一显式 `EXPLICIT_NEW_HOP` 触发**（`new_hop=true`），默认/自动禁止；沿边最短距离 + 节点去重、跨维重置；
4. **注册表 schema 冻结**：字段/类型/枚举/默认值/失败码表；`kind` 唯一规范字段（`basis.kind=map(kind)`，不一致 `DIM_KIND_MISMATCH`）；`registry_sha` 计算域写死；
5. **registry_history 不可变 append-only**：条目自包含（version/relation_sources/active_dimensions/previous_sha/decision_id），registry 带 `history_ref` 且末条 sha=registry_sha，validator 不需外部旧 registry；
6. **E_relation 只增不删**：跨版本 `new⊇old`；删除/改名 ⇒ `S0_REOPEN_REQUIRED` 硬失败；
7. **开放槽位**：reserved 只登记不渲染；候选 `time/evidence/task/controversy/authorship/similarity/path`；`density` 归 S2；v1 不晋升；
8. **状态机**：`{reserved,active,deprecated}`；deprecated→active 只能重开 S1 + registry 版本；插件不得注册/激活维度；agent fallback 显式 + 审计、可 forbidden；
9. **维度与渲染/VM**：维度经 `ctx.dimension_id` 进入 `present(e,ctx)`，只改 presence + rule_id，不改 type/label；ViewModel 只含 `dimension_id`（无切换/列表/历史/模式）；切换属 Presentation/S5；
10. **维度组合**：v1 单维度；组合参数出现 ⇒ `DIM_COMBINATION_UNSUPPORTED`。

## 3. 机检与工程证据

- SE M-S1-1..M-S1-12：`M_fail=[]`、12/12 PASS；首轮 2 FAIL 的修复证据在 `S1-engineering-check.md`；
- 同版本 mermaid（vendored，sha `9198f632…`）：PLAN 6 图 + 校核报告 3 图全部 `PARSE_OK`（failedBlocks:0）；
- 与 S0 一致性：VM 纯度（D-4）、R-1、present 三值、kind∈{kp,cluster}、D-3、R-3、S0-2/S0-5/S0-8/D-5 全 PASS；
- Lead 独立机检 PASS（schema 18 行、映射谓词、空集、15 条款、R-S1-1..11）。

## 4. 未关闭项（不阻塞冻结）

- O-S1-2：registry_sha/history 的存储与签名位置 → S6a；
- O-S1-4：A 维在 L>0 簇焦点的起点/端点聚合/rendered-hop → S4/S5；
- O-S1-6：S5a `EXPLICIT_NEW_HOP` 事件名/守卫细节；
- O-S1-7..10：semver 比较、deprecated 旧 frame 读取、max_nodes 数值、H 显示计数 → S6/S8/S3。

## 5. 变更控制

- 加维度/加关系源：S1 修订 + 决策 + registry 版本/history；删/改 H/A 核心规则：重开 S1；
- 冻结身份 = 本记录 + `S1-dimensions-v1.md`；未记录的字节改动视为破坏冻结。

## 6. 下一步

- S2（簇与子图划分）章程起草 → 人确认议程 → 逐议项研讨；S2 不得改 S1 的维度/注册表规则；
- 产品实现仍等 S0–S6 冻结。
