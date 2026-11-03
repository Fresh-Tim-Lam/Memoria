# S3 节点视觉与渲染接口 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`；`S3-charter.md`；`S3-RULINGS.md`。
> **上游冻结**：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）——不得违反。
> **输入**：A-v2（`b8311e10…`）、B-v2（`b3a6fdd8…`）、异议-v2（`4783a113…`）。
> **状态**：冻结候选 v1，待 SE 工程校核（task-307）与 Lead 独立机检后冻结；冻结前不写产品代码。

---

## 0. 一句话口径

默认视图由**单一渲染接口**（纯 ViewModel 输入，2D/3D 为同签名后端）绘制：簇节点用确定性名字/大小/徽标；KP 节点固定大小；只画 `presence=shown` 的边；`no_semantic_edges` 时显示 KP + **仅布局**分组（显式非语义），绝不伪造语义簇。

## 1. 规范性条款（S3-1..S3-12）

### S3-1 节点类型与状态
- **规则**：`kind ∈ {kp, cluster}`，禁止第三节点类型；singleton 以 `kp` 呈现（`representative=false`）；VM node `role ∈ {member, focus}`，**v1 无 `role=bridge` 视觉**（桥只作 edge state + 成员统计）；hover/selected 是渲染器内部瞬态，不进 VM。点击语义只由 `kind` 决定（kp→S5 跳编辑器；cluster→S5 下钻）。
- **机检**：kind 枚举；role 枚举；无第三形状/第三点击语义。
- **来源**：A-v2 S3-1；B-v2 S3-1；R-S3-3。

### S3-2 簇节点视觉编码与确定性 label
- **规则**：半径 `clamp(8+2.2·log2(member_count+1),12,28)`（2D/3D 同 token）；徽标 = `member_count`；`expandable` 用 chevron；`root_exempt` 虚线双环 + 「全库」。
- **R-S3-1（冻结）**：`label = label_of(min canonical member id)`；成员数>1 时加本地化后缀 `cluster.more_members`（「等 N 个」）；`root_exempt` 用 `cluster.root_label`（「全库」）；**禁止 local_seq/run 序号作显示名**；fallback = `cluster_key[:8]`；机检 `label == deterministic_label(members, locale)` 且同成员集跨 run 稳定。
- **来源**：A-v2 S3-2；B-v2 S3-2；R-S3-1。

### S3-3 KP 节点视觉
- **规则**：KP 固定大小 **8px**（screen-space；不按 degree/权重缩放）；VM `label` 显示名称；`range_ok=false` 用失效样式；hover/focus 提示「打开知识点」；点击只发事件，由 S5 执行跳转（U-20）。
- **机检**：KP 大小固定；无 degree 字段参与；range 失效样式存在。
- **来源**：A-v2 S3-3；B-v2 S3-3；R-S3-7。

### S3-4 层次感知
- **规则**：VM 可带 `level_label`（本地化显示字符串）；渲染器只画**非交互**层标；面包屑/层级条/历史/切换全归 Presentation/S5，不进 VM。
- **机检**：VM 无导航字段；层标不可交互。
- **来源**：A-v2 S3-4；B-v2 S3-4；R-S3-6。

### S3-5 边视觉与 presence
- **规则**：只画 `presence=shown` 的边；`suppressed/unknown` **不画**（禁止幽灵边，U-27）；边类型（contain structural/semantic、reference、extend）各有固定 token；bridge 仅叠加 `state=bridge_only`，不改 type；多类型边分画。
- **机检**：渲染边集 == `{e | presence=shown}`；suppressed/unknown 无视觉；token 表完整。
- **来源**：A-v2 S3-5；B-v2 S3-5。

### S3-6 渲染接口契约（2D/3D 统一）
- **规则**：`Renderer{getCapabilities(), render(container, vm), update(vm, opts), dispose(), on(event)}`；`getCapabilities()` 含 `maxNodes/maxEdges/backends`；2D/3D **同签名**（U-33）；纯 VM 输入（无 mode/nav/capabilities）；渲染器不取数、不做语义判断、不重算簇；无效 VM fail-visible。
- **机检**：五方法齐全；2D/3D 签名一致；VM 白名单；无数据访问。
- **来源**：A-v2 S3-6；B-v2 S3-6；R-S3-4。

### S3-7 事件契约
- **规则**：最小集 `nodeClick{node_id, kind}`、`edgeClick{edge_id}`、`backgroundClick{}`；可选 `hover/focus`；payload 白名单无导航字段；**导航动作只在 S5**；2D/3D payload 一致（现 3D 缺 edge_id 为已知修复项）。
- **机检**：事件集；无导航字段；2D/3D 一致。
- **来源**：A-v2 S3-7；B-v2 S3-7。

### S3-8 `no_semantic_edges` 默认视图
- **规则**：显示 KP 节点；允许 `layout_group`（`semantic=false`、非 cluster kind、无徽标/计数/展开语义）；banner（「尚无语义簇」、coverage 0%）；affordance **仅用户动作**时请求 agent 建立语义（不自动、不写）；不注入结构边、不伪造簇。
- **机检**：layout_group `semantic=false`；非 cluster kind；无簇徽标；agent 入口仅用户动作。
- **来源**：A-v2 S3-8；B-v2 S3-8；S2-12；R-S3-5。

### S3-9 默认 vs 全展开
- **规则**：同 DataSource/同 VM schema/同 Renderer；full 仅 `ctx` 不同，且有「全展开（兼容模式）」徽标；切换属 Presentation，S5 保持焦点/相机；禁止第二数据源/第二渲染器。
- **机检**：同源；full 徽标；无第二 builder。
- **来源**：A-v2 S3-9；B-v2 S3-9。

### S3-10 可访问性
- **规则**：文本对比度 ≥4.5:1、图形 ≥3:1；canvas 配可聚焦 DOM overlay（`aria-label`/`aria-expanded`/`aria-live`）；键盘 Tab/方向键/Enter/Space/Escape；`prefers-reduced-motion` 时动画 0ms；3D 不豁免。
- **机检**：对比度 token；overlay 属性；键盘路径；reduced-motion。
- **来源**：A-v2 S3-10；B-v2 S3-10。

### S3-11 性能与稳定预算
- **规则**：默认 `max_nodes=200`、`max_edges=400`、60fps、动画 ≤180ms（数值 S8 可调）；**S4 负责选点/裁剪**（`presence=suppressed+rule_id`）；Renderer 只校验/渲染已选 VM，不裁剪/不静默丢；VM 超硬上限 ⇒ `RENDER_BUDGET_EXCEEDED` fail-visible；drill 保持公共节点位置；WebGL 失败显式回退 2D。
- **机检**：预算字段；超限 fail-visible；无静默裁剪；降级路径。
- **来源**：A-v2 S3-11；B-v2 S3-11；R-S3-2。

### S3-12 与 S1/S2 的一致性 + VM 白名单
- **规则**：VM 字段白名单：`view_model_id/level_id/level_label/dimension_id/view_family_id/nodes/edges`；节点：`id/kind/label/role/member_count?/representative?/root_exempt?/range_ok?`；边：`id/type/state/presence?/data_edge_ids?`；簇/run/dendrogram/候选状态**不进 VM**；`metrics` 不进 VM（用显式 `member_count`）；**`data_edge_ids` 仅审计/`expand_data_edges` 用，Renderer 不得读取**（S0 R-3/S1 R-S1-11 需要它在 VM 中可审计）；3D 与 2D 同 VM id 集。
- **R-S3-9（冻结）**：`data_edge_ids` 允许出现在 VM 的派生/聚合边上（审计与 `expand_data_edges`），但 Renderer schema 必须拒绝读取；`aggregate_count` 由取景层显式给出，不遍历 `data_edge_ids`。
- **机检**：VM 白名单；Renderer 无 `data_edge_ids` 读取；2D/3D id 集一致。
- **来源**：A-v2 S3-12；B-v2 S3-12；R-S3-9。

## 2. 跨议题裁决（R-S3-1..R-S3-11）

- R-S3-1 簇 label 确定性；R-S3-2 预算归属 S4；R-S3-3 无 bridge 节点视觉；R-S3-4 五方法接口；R-S3-5 无簇 UX；R-S3-6 层标/VM；R-S3-7 KP 固定大小；R-S3-8 并集。
- **R-S3-9**：`data_edge_ids` 仅审计/expand 用，Renderer 禁读；`aggregate_count` 显式。
- **R-S3-10（冻结）**：label i18n：后缀 key `cluster.more_members`、根 key `cluster.root_label`；fallback = `cluster_key[:8]`；确定性与 locale 绑定，跨 run 稳定。
- **R-S3-11（冻结）**：3D 固定大小 = **screen-space**（与 2D 同屏幕直径 token；距离只影响深度/遮挡/顺序）；2D/3D 同 VM 下屏幕直径一致（允许 DPI 缩放）。
- `getCapabilities()` 必须含 `maxNodes/maxEdges/backends`。

## 3. 冻结前机检（SE，M-S3-1..M-S3-12）

M-S3-1 节点类型/role；M-S3-2 label 确定性/i18n；M-S3-3 簇公式/徽标/root；M-S3-4 KP 固定大小；M-S3-5 层次/层标；M-S3-6 边 token/presence；M-S3-7 渲染接口/2D-3D 同签名；M-S3-8 事件最小/导航边界；M-S3-9 无簇 UX/layout_group；M-S3-10 默认/全展开同源；M-S3-11 a11y/预算/降级；M-S3-12 VM 白名单/data_edge_ids 禁读/覆盖矩阵/与 S0-S2 一致/工程图增量（mermaid 同版本）。

## 4. 覆盖矩阵（U → 条款）

| U# | 要点 | 落地 |
|---|---|---|
| U-3 | 不要海量节点+错综连线 | S3-8/S3-11；S4 |
| U-5 | 非全展开默认、节点不再是最小粒度 | S3-1/S3-2/S3-8 |
| U-6 | 簇节点代表子图、外观更大 | S3-2 |
| U-15 | 深入后经语义边挂接一跳 | S1/S4；S3 只负责画 |
| U-16 | 旧版两端都渲染；新设计选择性渲染 | S3-5（只画 shown）；S4 |
| U-18 | 挂接一跳避免多跳污染 | S1/S4 |
| U-19 | 一跳节点可为 KP/簇节点 | S3-1 |
| U-20 | KP 点击仍跳编辑器 | S3-3（事件）+ S5 |
| U-26 | 默认彻底替代+全展开开关 | S3-9 |
| U-27 | 边存无/类型不同 | S3-5（只画 shown） |
| U-33 | 2D/3D 是带接口渲染板块 | S3-6/S3-11 |

## 5. 冻结后进入的下一场

S4（选择性渲染、一跳、边存无、背后图不带入）；S4 必须复用 S3 的 VM/presence/Renderer 契约，不得改 S3 的视觉 token/接口。

## 6. 变更控制

- 加视觉 token/事件/预算字段：S3 修订 + 决策；删/改渲染接口/事件集/label 规则/无簇规则：重开 S3；
- 冻结身份 = 本记录 + 本文件；未记录的字节改动视为破坏冻结。
