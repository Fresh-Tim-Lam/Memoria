# S3 章程：节点视觉与渲染接口（含无语义簇时的默认视图）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结**：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`），**不得违反**；议程 V0.2；逐议项（U-34）。
> **状态**：S3 章程 V1（Lead 起草）。本场冻结前不写产品代码。
> **日期**：2026-11-03（Asia/Shanghai）。

## 1. 目的

把 S0/S1/S2 的视图模型落成**可机检的视觉与渲染接口契约**：节点类型与视觉编码（簇 vs KP）、层次感知、
边状态视觉、**单一渲染接口（ViewModel→Renderer，2D/3D 为实现后端，U-33）**、事件契约、可访问性、性能预算，
并处理 S2 交办的 **`no_semantic_edges` 默认视图降级 UX**（不得把结构边当语义簇）。

## 2. 不在范围

- 选择性渲染算法 / 一跳 / 边存无判定（S4）；
- 导航状态机（S5，S3 只定义事件与展示接口）；
- 数据契约细节（S6）；
- 2D/3D 引擎实现（只定义共同接口，U-33）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：定义/规则、机检条件、反例、边界用例、U 映射、建议裁决、证据等级。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S3-1 | 节点类型与视觉语义 | `kind∈{kp,cluster}` 的视觉区分；单点簇不作代表节点（S2）；节点状态（active/hover/selected/bridge-role）如何表达；不得新增第三节点类型 |
| S3-2 | 簇节点视觉编码 | 大小/徽标/聚合计数/展开提示；大小映射什么（member_count？weight？）以及下限/上限；簇显示名从哪来（成员统计？中心 KP？）及多语言；`root_exempt` 的特殊外观 |
| S3-3 | KP 节点视觉与状态 | KP 节点如何在图中表示（名称/描述/标签）；是否显示语义/结构标签；与文本编辑器跳转的视觉提示（U-20） |
| S3-4 | 层次感知 | 当前层次/深度指示；面包屑/层级条/缩略图；跨层次视觉连续性；与 S5 导航接口 |
| S3-5 | 边视觉与状态 | 边类型（contain structural/semantic、reference、extend）与「存无」状态（shown/suppressed/unknown）的视觉编码；bridge 边状态；不得以视觉编码暗示数据中不存在的边 |
| S3-6 | 渲染接口契约（2D/3D 统一） | `ViewModel` 输入（纯、无导航/模式/capabilities）；`Renderer.getCapabilities()`；`render(vm)`/`update(vm)`/`dispose()`；事件回传；2D/3D 同签名（U-33）；渲染器不取数、不做语义判断、不写状态 |
| S3-7 | 事件契约 | `nodeClick(node_id, kind)`、`edgeClick(edge_id)`、`backgroundClick()` 的最小集；hover/focus 可选；**导航动作不在渲染器内**（S5）；事件不得携带导航状态 |
| S3-8 | `no_semantic_edges` 默认视图 UX | 语义簇为 0 时默认视图显示什么（不得伪造语义簇）；是否显示 KP 节点/提示 agent 建立语义/结构布局分组（仅布局，不称簇）；空状态文案与 affordance；与 S4 选择性渲染的接口 |
| S3-9 | 默认 vs 全展开的视觉 | 默认层次视图与全展开开关的视觉差异、切换反馈、状态保持；不得引入第二数据源（S0-8） |
| S3-10 | 可访问性 | 对比度、键盘焦点、`aria` 语义（节点/边/簇展开）、reduced motion；读屏可理解层次/维度切换 |
| S3-11 | 性能与稳定预算 | 单屏节点/边上限、帧率目标、布局稳定性（drill 后不跳动）、动画时长；规模不是问题（U-32）但必须有显示预算与退化策略 |
| S3-12 | 与 S1/S2 的一致性 | ViewModel 只带 `dimension_id` + 节点/边视图（S1 D-4、S2 D-4）；簇/run/dendrogram 状态不进 VM；视觉编码从数据派生，不在渲染器里重新算簇；`data_edge_ids` 可用于审计/计数但不暴露内部 |

## 4. 预注册判据（会前写死）

1. 每个视觉编码可机检（字段→token 映射表；DOM/样式可断言）；
2. 渲染接口 schema 可校验；2D/3D 同签名；`getCapabilities()` 显式；
3. 事件集最小且不含导航状态；导航动作只在 S5；
4. `no_semantic_edges` 状态有明确 UX，且**不伪造语义簇**；
5. 两份独立提案（A/B）差异逐条列出并裁决；
6. 覆盖矩阵（U-3/5/6/15/16/18/19/20/26/27/33 + S0/S1/S2 相关）无缺失；
7. SE 工程校核确认视觉/渲染接口可落到 ER/DFD/状态图，且不违反 VM 纯度/D-3；
8. 不写产品代码、不改契约、不 commit。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游冻结：`S0-terms-v1.md`、`S1-dimensions-v1.md`、`S2-clustering-v1.md`、三份 FREEZE-RECORD；
- 工程：`ENGINEERING-PLAN.md`（ER/DFD/状态图 + S1/S2 增量）、`S1-engineering-check.md`、`S2-engineering-check.md`；
- 只读代码锚：`graph-engine.js`、`graph-view-2d.js`、`graph-view-3d.js`、`graph-settings.js`、`app.js` 的图谱渲染/点击入口（现状证据，非设计结论）。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S3-visual-proposal-A.md` + 证据 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S3-visual-proposal-B.md` + `S3-objections.md` |
| 软件工程专家 | `graph-se-architect` | `S3-engineering-check.md`（视觉/接口→ER/DFD/状态图增量 + 可工程性） |
| 并集与裁决 | Lead | `S3-RULINGS.md` → `S3-visual-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS（渲染接口/视觉编码/事件/性能预算/无簇 UX 的 ER/DFD/状态图增量，与 S0/S1/S2 一致）；
3. Lead 独立机检（视觉映射表、渲染接口 schema、2D/3D 同签名、事件集、无簇 UX、VM 纯度）；
4. 与 S0/S1/S2 无冲突；
5. 满足后冻结 `S3-visual-v1.md` 并写决策；否则回修订轮。

## 8. 变更控制

- 冻结后加视觉编码/事件：S3 修订 + 决策；删/改渲染接口/事件集/无簇规则必须重开 S3；
- 本场无产品代码；S0–S6 全冻结前不开工实现。
