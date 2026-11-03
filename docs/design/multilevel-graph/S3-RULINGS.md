# S3 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S3-charter.md`；
> 上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）。
> **输入**：提案 A `S3-visual-proposal-A.md`（`7997a893…`）、提案 B `S3-visual-proposal-B.md`（`0abc2f2b…`）、`S3-objections.md`（`281c4537…`）。
> **状态**：S3 **未冻结**；无 P0，2 条 P1 必修 + 1 条 P1 需裁。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 簇 label 无确定性 | 读 A S3-2（label 由取景层生成、fallback 用 local_seq）与 S2-4（local_seq 为 run 内序号） | **成立**：同语义簇在成员增删后显示名漂移，两实现可不同；必须冻结确定性规则 |
| P1-2 预算裁剪归属 | 读 A（renderer 拒绝或 S4 裁剪）与 S4 契约未定 | **成立**：同 VM 可能两种行为；必须单一归属 |
| P1-3 node.role=bridge 与 S2 边界 | 读 A S3-1（role 含 bridge + 虚线外环）与 S2 R-S2-7 | **成立**：可被实现成第三类节点外观；需裁 |
| 其余点名审查 | 节点类型/边视觉/接口纯度/事件/无簇 UX/第二数据源/VM 纯度 | 全 PASS；P2 项合并进修订 |

## 1. 跨议题裁决（R-S3-1..R-S3-8）

### R-S3-1 簇显示名确定性（P1-1）
- **裁决（冻结）**：簇 `label` 必须由成员**确定性**导出：取**最小 canonical 成员 id 的 KP label**；成员数 >1 时加本地化后缀（如「等 N 个」）；`root_exempt` 用「全库」。禁止用 `local_seq`/run 序号作显示名。机检：`label == deterministic_label(members)`，同成员集跨 run/跨版本稳定。
- **理由**：显示名漂移会让用户以为簇变了；也保证 2D/3D/审计一致。

### R-S3-2 预算裁剪归属（P1-2）
- **裁决（冻结）**：**S4 负责选点/裁剪**（超预算时输出 `presence=suppressed + rule_id`）；**Renderer 只校验并渲染已选 VM**，不得自行裁剪、不得静默丢节点/边；若 VM 本身超过硬上限（`max_nodes/max_edges`）⇒ `RENDER_BUDGET_EXCEEDED` fail-visible。`max_nodes/max_edges` 数值 S8 定；S3 冻结字段与失败语义。
- **理由**：单一归属避免"S4 裁 200 个 vs Renderer 拒绝"两套行为。

### R-S3-3 bridge 视觉边界（P1-3）
- **裁决（冻结）**：v1 **不允许 node `role=bridge` 的视觉表达**；桥只作为 **edge `state=bridge_only`** 与簇成员统计；VM node `role ∈ {member, focus}`。需要 bridge 节点外观时必须重开 S3（并同步改 S2）。机检：node role 枚举不含 bridge；无第三形状/点击语义。
- **理由**：贴 S2 冻结「桥只作边状态/成员统计」，避免第三类节点。

### R-S3-4 渲染接口命名与字段（P2 收口）
- **裁决**：canonical 方法名 `render(container, vm)`、`update(vm, opts)`、`dispose()`、`on(event)`、`getCapabilities()`；v1 **不用 `mount`**；v1 不提供 `setSelection`（键盘焦点/选区视觉由渲染器内部瞬态 + Presentation 驱动，不进 VM）。
- **理由**：统一 A/B 命名差异，保持 VM 纯。

### R-S3-5 无簇 UX 的边界（S2-12 交办）
- **裁决**：`no_semantic_edges` 时：① 显示 KP 节点（singleton 以 kp 呈现）；② **仅布局**的文档结构分组允许，但必须在 VM 中显式 `semantic=false` 且**不是 cluster kind**、不产生簇徽标/展开语义；③ banner（"尚无语义簇"、coverage 0%）+ 显式 affordance（**仅在用户动作时**请求 agent 建立语义，不自动调用）；④ 不得注入结构边、不得伪造语义簇。
- **理由**：保留可用性又不污染语义。

### R-S3-6 层次标识归属
- **裁决**：VM 可带 `level_label`（本地化显示字符串）；渲染器可画**非交互**层标；面包屑/层级条/历史/切换全归 Presentation/S5，不进 VM。
- **理由**：视觉上要有层次感，同时不把导航塞进 VM/渲染器。

### R-S3-7 KP 节点大小
- **裁决**：v1 KP 节点**固定大小**（不按结构 degree/权重缩放；结构度量非语义，避免暗示错误信号）；簇节点用 A 的 `clamp(8+2.2·log2(member_count+1),12,28)`，2D/3D 同 token。
- **理由**：避免"看起来重要的节点"由结构度决定，误导用户。

### R-S3-8 P2 并集
- `layout_group` 进 VM 白名单但必须 `semantic=false`；`metrics` 不进 VM；3D 与 2D 同视觉 token（深度只影响投影）；agent 入口仅用户动作；`data_edge_ids` 不进渲染器；`root_exempt` 外观按 A。
- A 的 token 表/大小公式/无簇 UX/a11y/预算字段为主干；B 的 VM 白名单严格性/label 确定性要求/bridge 保守性并入。

## 2. 修订轮任务

**A-v2**：落实 R-S3-1..R-S3-8；更新 `S3-visual-proposal-A-v2.md` + 变更表。
**B-v2**：落实 R-S3-1..R-S3-8（吸收 A 的 token 表/公式/无簇 UX/a11y/预算字段；保持独立复核）；产出 `S3-visual-proposal-B-v2.md` + `S3-objections-v2.md`。
**SE 工程校核（task-307）**：等 v2 齐后执行；检查视觉映射/渲染接口/事件/无簇 UX/预算归属的 ER/DFD/状态图增量与 S0/S1/S2 一致。

## 3. S3 冻结门禁

1. A-v2/B-v2 关闭全部 R-S3 与 P1（逐条证据）；
2. SE 工程校核 PASS；
3. Lead 独立机检（label 确定性、预算单一归属、bridge 边界、render 接口、无簇 UX、VM 纯度、token 表可机检、覆盖矩阵）；
4. 与 S0/S1/S2 无冲突；
5. 冻结 `S3-visual-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0/S1/S2 冻结稿；S3 冻结前不开工实现；所有修订保留旧版。
