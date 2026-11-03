# S3 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S3-visual-v1.md`（12 条规范 + R-S3-1..R-S3-11 + U 覆盖矩阵）。
> **冻结时间**：2026-11-03T20:27+08:00（Asia/Shanghai）。
> **决策**：`dec-20261103-def8efcf`（Lead；S0 `dec-20261102-a6af89e1`、S1 `dec-20261103-35844b56`、S2 `dec-20261103-ec432887` 已冻结）。
> **状态**：**已冻结**。S4 可开；S0–S6 冻结前仍不写产品代码。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S3-visual-v1.md`（**冻结稿最终态**） | S3 唯一规范来源 | `0ca4ea0e890aa7408a361ae97dbb4d8a8f06df60b1e191cbcb7d46ca5322cd6b` |
| `S3-engineering-check.md` | SE 工程校核（M-S3-1..12） | `321b0ef7…` |
| `S3-visual-proposal-A-v2.md` | 证据链（主办研究） | `b8311e10…` |
| `S3-visual-proposal-B-v2.md` | 证据链（独立复核） | `b3a6fdd8…` |
| `S3-objections-v2.md` | 差异/异议 | `4783a113…` |
| `S3-RULINGS.md` | Lead 裁决（R-S3-1..8） | `1d62fb48…` |
| `ENGINEERING-PLAN.md`（S3 增量） | ER-04/DF-04/ST-04 | `977332e7…` |

**冻结轮次**：SE 首轮 10 PASS / 2 FAIL（VM `role=focus` 把 S5 导航态塞进 VM；VM 白名单缺 `layout_group/aggregate_count`）；Lead 修两处后 SE 复跑 **12/12 PASS、M_fail=[]**；Lead 独立机检（12 条款、R-S3-1..11、role、白名单、label、五方法、2D/3D 同签名、presence、预算、3D screen-space）PASS。冻结身份取最终态 sha `0ca4ea0e…`。

## 2. S3 冻结了什么（一句话版）

1. **单一渲染接口**：`Renderer{getCapabilities, render(container,vm), update(vm,opts), dispose(), on(event)}`；纯 ViewModel 输入；2D/3D **同签名**（U-33）；渲染器不取数/不做语义/不重算簇/不裁剪；
2. **节点**：`kind∈{kp,cluster}`；singleton 以 kp 呈现；VM node `role∈{member}`；**无 bridge 节点视觉**（桥只作 edge state + 统计）；hover/selected/focus 全为渲染器/Presentation 瞬态，**不进 VM**；
3. **节点视觉**：KP 固定 8px screen-space（不按 degree）；簇半径 `clamp(8+2.2·log2(member_count+1),12,28)`；徽标=member_count；`root_exempt` 虚线双环+「全库」；
4. **簇 label 确定性**：`label_of(min canonical member id)` + 本地化「等 N 个」；root 用 `cluster.root_label`；**禁 local_seq**；fallback=`cluster_key[:8]`；跨 run 稳定；
5. **边视觉**：只画 `presence=shown`；suppressed/unknown 不画（无幽灵边）；四类边固定 token；bridge 仅叠加 `state=bridge_only`；
6. **层次**：VM 带 `level_label`，渲染器只画非交互层标；面包屑/历史/切换归 Presentation/S5；
7. **事件**：`nodeClick{node_id,kind}`/`edgeClick{edge_id}`/`backgroundClick{}`；无导航 payload；导航动作只在 S5；
8. **无簇 UX**：`no_semantic_edges` 显示 KP + `layout_group{semantic:false}`（非 cluster kind、无徽标/计数）+ banner + 仅用户动作请求 agent；**不伪造语义簇**；
9. **默认 vs 全展开**：同 DataSource/VM schema/Renderer；full 有兼容模式徽标；无第二数据源；
10. **预算**：`max_nodes=200/max_edges=400/60fps/≤180ms`（S8 可调）；**S4 负责裁剪**（suppressed+rule_id）；Renderer 只校验/渲染、超硬上限 `RENDER_BUDGET_EXCEEDED` fail-visible；WebGL 失败显式回退 2D；
11. **可访问性**：对比度阈值、canvas DOM overlay（aria）、键盘全路径、reduced motion 0ms；3D 不豁免；
12. **VM 白名单**：`view_model_id/level_id/level_label/dimension_id/view_family_id/nodes/edges`；节点含 `aggregate_count?/layout_group?{semantic:false}`；`data_edge_ids` 可审计/expand 但 **Renderer 禁读**；簇/run/dendrogram/metrics 不进 VM。

## 3. 机检与证据

- SE M-S3-1..12：`M_fail=[]`、12/12 PASS；两处 FAIL 修复证据在 `S3-engineering-check.md`；
- 同版本 mermaid（vendored，sha `9198f632…`）：PLAN 12 图 + 报告 3 图全部 `PARSE_OK`（failedBlocks:0）；
- 与 S0/S1/S2 一致性：kind 两类、无 bridge 节点、2D/3D 同一接口、presence 三值、S2 D-4、S2-12 无簇不伪造、S0-8 无第二数据源、D-3 无 sidecar 全 PASS；
- Lead 独立机检 PASS（见 §1）。

## 4. 未关闭项（不阻塞冻结）

- O-S3-3..10：`no_semantic_edges` 状态透传（S4/S6a）；预算数值 S8；`layout_group`/`data_edge_ids` schema（S6a）；3D DPI；label i18n 测试；`aggregate_count` 来源；VM schema 单源。

## 5. 变更控制

- 加视觉 token/事件/预算字段：S3 修订 + 决策；删/改渲染接口/事件集/label 规则/无簇规则：重开 S3；
- 冻结身份 = 本记录 + `S3-visual-v1.md`；未记录的字节改动视为破坏冻结。

## 6. 下一步

- S4（选择性渲染、一跳、边存无、背后图不带入）：必须复用 S3 的 VM/presence/Renderer 契约；首批产出 S4 章程与逐议项议程；
- 产品实现仍等 S0–S6 冻结。
