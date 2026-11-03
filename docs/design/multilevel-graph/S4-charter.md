# S4 章程：选择性渲染、一跳挂接与边「存无」

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结**：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`），**不得违反**；议程 V0.2；逐议项（U-34）。
> **状态**：S4 章程 V1（Lead 起草）。本场冻结前不写产品代码。
> **日期**：2026-11-03（Asia/Shanghai）。

## 1. 目的

把「默认视图不再展开所有节点/边」落成**可机检的取景规则**：谁决定 `presence ∈ {shown, suppressed, unknown}`、
按什么优先级在预算内选点/选边、一跳挂接如何取、什么时候边"存在/不存在/未知"、背后图何时不带入、
全展开如何走同一 `present`、以及 S4 与 S3 Renderer / S5 导航 / S1 维度 / S2 簇的接口。

## 2. 不在范围

- 导航状态机（S5，S4 只定义取景与事件边界）；
- 数据契约细节（S6；S4 给需求）；
- 渲染视觉 token（S3 已冻结）；
- 后端检索算法（S9；S4 给输入/输出契约需求）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：定义/规则、机检条件、反例、边界用例、U 映射、建议裁决、证据等级。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S4-1 | 选择性渲染定义与边界 | 与 S3 `presence`、S0-6/S0-9、旧版全量渲染的区别；「选择性」只改 presence 不改事实；S4 是唯一裁剪者（S3 R-S3-2） |
| S4-2 | 预算内选点规则 | `max_nodes/max_edges`；优先级排序（焦点邻域/语义权重/最近/确定性 tie-break），如何可复算；超预算显式降级而非静默丢 |
| S4-3 | 一跳挂接 | 一跳 = 恰好一条 `E_relation(D)` 边；关系类型集合、方向、端点 kind∈{kp,cluster}；不闭包、不带背后图 |
| S4-4 | 边「存无」判定 | 三值（shown/suppressed/unknown）何时产生；类型不同导致边存在/不存在（U-27）；`rule_id` 可枚举；unknown 的显示语义 |
| S4-5 | 背后图不带入 | 一跳端点作为新焦点时的规则（S5 新一跳才有 2 跳）；禁止自动展开闭包；多归属/跨层边如何取 |
| S4-6 | 维度接入 | `ctx.dimension_id` 如何改变 presence（H 层次 / A 关联扩展）；`frame_spec` 输入；维度只改取景不改事实（S1） |
| S4-7 | 层次与一跳交互 | drill 到 L_{k+1} 后焦点/预算/一跳如何重置；跨层边是否显示；与 S2 run 的 `(level,view_family)` 一致 |
| S4-8 | 全展开模式 | 全展开（兼容模式）如何走同一 `present`；`presence(shown)` 子集约束 `shown(default) ⊆ shown(full)`；预算与降级 |
| S4-9 | 与 S3 契约 | S4 输出 VM；presence/rule_id/aggregate_count 字段；Renderer 不裁剪；`RENDER_BUDGET_EXCEEDED` 只在 VM 超硬上限时；S4 与 S8 阈值同源 |
| S4-10 | 与 S5 导航边界 | focus/selection/navigation 不进 VM；事件到 S5；S5 触发新 frame 的接口；禁止 S4 内做导航状态机 |
| S4-11 | 与 S1/S2 一致性 | presence 不改 type/label/contain_kind；簇成员多归属；run/簇状态不进 VM；A 不改变簇；一跳端点用 S1 维度定义 |
| S4-12 | 度量与验收 | 每屏节点/边数、被抑制比例、一跳准确率、确定性（同输入同 presence）、性能预算；G6 快照口径；可复跑脚本 |

## 4. 预注册判据（会前写死）

1. 选点/选边规则可机检（给定 VM+ctx+预算 → 唯一 presence 结果）；
2. 预算单一归属（S4），Renderer 不做裁剪决策；
3. presence 三值 + `rule_id` 可枚举；unknown 与 suppressed 语义不同；
4. 一跳严格不闭包、不带背后图；2 跳只能由 S5 显式 `EXPLICIT_NEW_HOP`；
5. `shown(default) ⊆ shown(full)`；全展开同源同 `present`；
6. 两份独立提案（A/B）差异逐条列出并裁决；
7. 覆盖矩阵（U-5/15/16/17/18/19/21/22/27/28/31 + S0/S1/S2/S3 相关）无缺失；
8. SE 工程校核确认取景/预算/presence 可落到 ER/DFD/状态图，且不违反 VM 纯度/D-3；
9. 不写产品代码、不改契约、不 commit。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游冻结：S0/S1/S2/S3 四份 v1 + FREEZE-RECORD；
- 工程：`ENGINEERING-PLAN.md`（ER/DFD/状态图 + S1/S2/S3 增量）、三份 engineering-check；
- 只读代码锚：`graph-engine.js`、`graph-view-2d.js`、`graph-view-3d.js`、`app.js` 的图谱取数/渲染入口（现状证据，非设计结论）。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S4-render-proposal-A.md` + 证据 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S4-render-proposal-B.md` + `S4-objections.md` |
| 软件工程专家 | `graph-se-architect` | `S4-engineering-check.md`（取景/预算/presence → ER/DFD/状态图增量） |
| 并集与裁决 | Lead | `S4-RULINGS.md` → `S4-render-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS；
3. Lead 独立机检（选点规则、presence、rule_id、一跳、全展开子集、预算单一归属、VM 纯度）；
4. 与 S0/S1/S2/S3 无冲突；
5. 满足后冻结 `S4-render-v1.md` 并写决策；否则回修订轮。

## 8. 变更控制

- 冻结后加规则/阈值：S4 修订 + 决策；删/改 presence 语义/一跳/预算归属必须重开 S4；
- 本场无产品代码；S0–S6 全冻结前不开工实现。
