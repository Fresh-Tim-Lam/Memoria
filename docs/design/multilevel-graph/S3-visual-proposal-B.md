# S3 节点视觉与渲染接口提案 B（独立复核方）

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`），不得违反；本场 `S3-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S3-visual-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S3-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0/S1/S2 冻结。

---

## 0. 总原则（S3 不得改 S0/S1/S2）

1. 节点 `kind ∈ {kp, cluster}` **只有两类**；bridge 只是 node role/edge state，不是第三类（S0-9/S1 R-S2-7）。
2. 单点簇 `representative=false`，**不得**当"代表子图节点"渲染；`root_exempt` 是带显式标志的 cluster，不是普通簇。
3. 视觉编码**从数据派生**：大小/计数/标签必须可追溯到 `member_count`/canonical name；不得伪造数据或视觉暗示不存在的边（U-27）。
4. **渲染接口单一**：ViewModel 纯数据（不含 mode/导航/capabilities/簇 run/dendrogram）；2D/3D 同签名后端；渲染器不取数、不做语义判断、不写状态。
5. 默认与全展开同源同 ViewModel；`no_semantic_edges` 状态如实显示 KP/结构布局，不伪造语义簇。
6. 每条视觉 token 映射可机检（字段→token→DOM/属性断言）；事件集最小；导航状态归 S5。

### 0.1 覆盖矩阵（U + S0/S1/S2 相关）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-3 | 海量节点/错线→S3-11 预算 | U-15/U-16 | 一跳/选择性渲染视觉=S3-5 |
| U-5/U-6 | 非全展开/簇节点=S3-1/S3-2 | U-17 | 背后图不带入=S3-5（只渲染端点边） |
| U-18 | 防多跳=S3-11 | U-19/U-20 | 点击/编辑器=S3-3/S3-7 |
| U-26 | 默认/全展开=S3-9 | U-27 | 存无/类型=S3-5 |
| U-33 | 2D/3D=S3-6 | U-34 | 逐议项=本文件 |
| S0-9/D-4 | VM 纯度/kind=S3-1/S3-6/S3-12 | S1 D-4/D-5 | 维度不进 VM/单维度=S3-6/S3-12 |
| S2-6/7 | singleton/root/role=S3-1/S3-2 | S2-12 | no_semantic_edges UX=S3-8 |
| S2-9/R-3 | data_edge_ids 审计=S3-12 | S0-11 | 不做什么=S3-8/S3-9 |

---

## S3-1 节点类型与视觉语义

**规则**：节点类型固定 `kind ∈ {kp, cluster}`；簇节点仅在 `cluster.representative=true`（|members|≥2）时渲染为 cluster；`singleton`/`representative=false` 一律渲染为 KP（即使 partition 中有 singleton 块）。节点状态（active/hover/selected/bridge-role）只改变视觉状态，不改变 `kind`；`bridge` 只能出现在 node `role`/edge `state`，**不得**成为 `kind`。

**形式化/机检**：
```python
assert all(n.kind in {"kp","cluster"} for n in vm.nodes)
assert all(n.kind=="cluster" for n in vm.nodes if n.representative)
assert all(n.kind=="kp" for n in vm.nodes if n.kind=="cluster" and n.member_count==1) is False  # singleton 不得 cluster
assert "bridge" not in {n.kind for n in vm.nodes}
assert node.role ∈ {member, one_hop, focus} （bridge 仅 edge.state）
```
**反例**：出现 `kind=bridge`/`kind=singleton`/`kind=group`（第三类）；singleton 被渲染成代表子图节点（U-6 误用）；`root_exempt` 被当普通簇；bridge 节点 kind=cluster/kp 但视觉桥接块（应 role/state）。
**边界**：单点；root_exempt（仍是 cluster，带特殊标志）；hover/selected 不改变 kind；A 维度一跳节点 role=one_hop 但 kind 仍是 kp/cluster。
**U 映射**：U-5、U-6、U-19、U-28。
**建议裁决**：冻结 `kind {kp,cluster}`、singleton 不作 cluster、bridge 仅 role/edge state；视觉状态不改 kind。
**证据等级**：A（S0-9/S1 R-S2-7/S2 R-S2-6；现有 `graph-engine.js` 节点无 kind，需扩展）+ R。

---

## S3-2 簇节点视觉编码（大小/计数/名称/root）

**规则**：簇节点**视觉大小 = 单调函数 f(member_count)**，有显式 min/max 与 cap；显示计数=真实 `member_count`（不得伪造/四舍五入到假精度）；显示名从**确定性代表规则**派生（成员中 canonical id 最小者的 KP 名称 + "等 N 个"）；`root_exempt` 有独立外观（外环/徽标），不占用普通计数语义。
**形式化**：
```
radius = clamp(f(member_count), r_min, r_max); f 单调非减、确定性、无随机
count_badge = member_count 精确整数；多语言 "N 个知识点"
label = name(argmin canonical id of members) + " 等 N 个"; 同一 run 内稳定
root_exempt: 额外标记（outline/badge="全库"），不得显示为普通簇计数
视觉 token 表（示例，数值 S3 冻结）:
  cluster: radius f(count), badge count, expand affordance (▸), no semantic color coding
  root_exempt: 外环/tone 区分 + "全库" badge
```
**机检**：
```python
assert all(c.member_count == len(c.members) for c in cluster_nodes)
assert all(c.label == deterministic_label(c.members) for c in cluster_nodes)
assert all(radius in [r_min,r_max] for c in cluster_nodes) and monotonic(f)
assert root_exempt flagged distinctly
assert no_fabricated_count (badge==len(members))
```
**反例**：radius 用权重/随机/degree 冒充 count（无数据）；显示计数比真实多/少；label 随机选成员；root_exempt 当普通簇；空簇渲染（S2 禁止）。
**边界**：member_count=2 最小代表簇；超大簇 cap；root_exempt；单点不渲染 cluster（S3-1）；count 极大时的显示格式（数字不伪造）。
**U 映射**：U-6、U-14、U-19。
**建议裁决**：冻结大小映射 f/cap/计数/名称/root 外观；数值 token S3 定，数据可追溯。
**证据等级**：A（S2 R-S2-6；现有 degree→radius `graph-engine.js:14-84` 是"度数"非成员数，需新映射）+ C（U-6）+ PI（f/数值）。

---

## S3-3 KP 节点视觉与状态

**规则**：KP 节点显示名称（canonical label/name）；可选 range_ok 标记；**不显示**未经 S0-1 判定的语义标签（不得把 structural/reference 显示成语义）；KP 点击视觉提示（hover/pointer/选中态）应暗示"跳编辑器"（U-20），但点击行为由 S5 决定；level/dimension 只影响取景不改变 KP 的身份视觉。
**形式化**：
```python
kp.label = canonical kp name; kp.id 唯一
range_ok=false ⇒ 可显示"定位不可用"标记（不影响节点类型）
不渲染 semantic badge 除非数据 label=semantic
click affordance (cursor/underline) 与 S5 行为一致；不得在节点上放导航动作
```
**机检**：KP 节点字段来自数据；无 semantic badge 当 label≠semantic；hover/selected 状态 token 可断言；点击事件只发 nodeClick（S3-7）。
**反例**：给所有 KP 标 semantic 色；把 structural contain 显示成"整体-部分"；KP 点击后渲染器自己跳转/改导航；用 node 大小表示"重要性"无数据。
**边界**：range_ok=false；长名称截断 tooltip；同名不同 id；同 KP 在 H/A 出现时身份不变。
**U 映射**：U-1、U-19、U-20、U-27。
**建议裁决**：冻结 KP 视觉/标签/点击 affordance；语义标签只由数据 label 决定；渲染器不执行导航。
**证据等级**：A（S0-1/S0-9；现有 `app.js` nodeClick 跳转在 shell）+ C。

---

## S3-4 层次感知

**规则**：层次指示（当前 level/depth、面包屑/层级条、缩略图）属于 **Presentation/S5 导航 chrome**，不属于渲染器 ViewModel；渲染器只接收当前 ViewModel 并绘制节点/边；层次切换/下钻是 S5 动作；跨层视觉连续性用稳定 token/布局提示，不携带历史栈。
**形式化**：
```
Presentation/S5 持有: current level/dimension/focus/history -> 生成 VM
VM 不含 breadcrumb/history/mode；可含 view 标识（level_id/dimension_id/view_family_id，S0/S1 允许）
Renderer 不渲染面包屑；若渲染器需显示 depth label，由 VM 的只读字段（如 level_id）派生，不写状态
```
**机检**：VM 无 history/breadcrumb/mode；Renderer 无 setLevel/navigate；事件无 breadcrumbClick；层次 chrome DOM 在 S5/Presentation 层。
**反例**：VM 带面包屑/历史；Renderer 处理下钻；breadcrumb 点击由渲染器发导航事件；跨层布局随机跳变（稳定性）。
**边界**：H 下钻一层（S1 无 hop）；A 切换不改 level；全展开仍显示层次 chrome 但无导航状态。
**U 映射**：U-4、U-7、U-8、U-34。
**建议裁决**：冻结层次 chrome 归 Presentation/S5；VM 无导航状态；渲染器只绘制 VM。
**证据等级**：A（S0-9/S1 D-4）+ C（S5 接口）。

---

## S3-5 边视觉与状态（present 三值/类型；不暗示不存在边）

**规则**：**只有 `presence=shown` 的边渲染为可见边**；suppressed/unknown **不画成普通边**（避免暗示数据中存在）；可用非边 UI（图例/节点角标/计数）表达存在 suppressed/unknown 数量；边类型视觉区分 `contain(structural)/contain(semantic)/reference/extend`；`bridge_only` 是边 state 视觉；类型差异不得暗示不存在的语义（U-27）。
**形式化**：
```
render_edges = {e | e.presence==shown}
edge_style: base_type/contain_kind/label + state ∈ {normal,bridge_only}
suppressed/unknown: 不进入 render_edges；提供 legend/aria/count（例如"2 条关系被隐藏/未判定"）
unknown 不得视觉呈现为"无关系"（需要在 UI 提示 unknown 存在，但不得画假边）
label=semantic 才可语义色；structural/reference 不得语义色
H 派生边按 S1；data_edge_ids 不直接画
```
**机检**：
```python
assert rendered_edges == {e for e in vm.edges if e.presence=="shown"}
assert no rendered edge with presence in {suppressed,unknown}
assert edge style mapping table covers base_type/contain_kind/state
assert unknown_count exposed in legend/aria (not as fake edge)
```
**反例**：把 suppressed 边画成淡色实线（暗示存在）；unknown 画虚线（暗示边存在/不存在）；reference 用 semantic 色；bridge 当普通边；未 shown 的边产生 edgeClick。
**边界**：同一对节点多类型边（分别样式）；bridge_only；unknown 大量时只计数；A 一跳只渲染端点边（U-17）；全展开仍按 present（S0-8）。
**U 映射**：U-15、U-16、U-17、U-27。
**建议裁决**：冻结"只画 shown + suppressed/unknown 非边视觉 + 类型/标签 token 表"；unknown 需可感知但不得画假边。
**证据等级**：A（S0-6/S0-8；现有 `graph-view-2d` edgeColor 按 type）+ C。

---

## S3-6 渲染接口契约（2D/3D 统一；VM 纯）

**规则**：单一渲染接口：`Renderer.getCapabilities()`、`mount(root, vm)`、`update(vm, opts?)`、`dispose()`、`on(event, handler)`；VM 纯数据（无 mode/nav/capabilities 字段；可含 view 标识 `level_id/dimension_id/view_family_id`）；2D/3D 同签名、同事件 id；渲染器不取数、不做 semantic/present/cluster 计算、不写任何状态。
**形式化**：
```
ViewModel = {schema_version, view_model_id, level_id?, dimension_id?, view_family_id?,
             nodes:[{id,kind∈{kp,cluster},label,member_count?,representative?,role?,state?,
                     range_ok?,x?/y?/layout_hint?}],
             edges:[{id,source,target,base_type,contain_kind?,label?,presence,rule_id?,
                     state?,display_type}]}
Renderer API (2D/3D identical):
  getCapabilities() -> {labels, zoom, animation, a11y}
  mount(root, vm) / update(vm, opts?) / dispose()
  on(event, handler) / off?
事件: nodeClick {node_id,kind}, edgeClick {edge_id}, backgroundClick {}, hover? {node_id|edge_id}
禁止: VM 含 mode/focus/history/capabilities；renderer 调 get_graph_data/读 sidecar/算 cluster/present；
      渲染器拥有导航/切换状态；2D/3D 两套 VM
```
**机检**：
```python
assert vm has no {mode,focus,history,breadcrumb,capabilities,cluster_run,dendrogram}
assert 2D/3D register same interface signature/event ids
assert no data access in renderer (grep imports/calls)
assert capabilities from Renderer.getCapabilities(), not VM
```
**反例**：VM 带 capabilities/mode/导航；2D/3D 各自 VM/事件；渲染器取数/做 semantic；渲染器持有 dimension 切换。
**边界**：3D 未实现（接口先冻结）；2D/3D 渲染差异只走 capabilities；render failure 不影响 VM。
**U 映射**：U-19、U-20、U-33、U-34。
**建议裁决**：冻结单一接口/VM 字段/2D/3D 同签名/禁取数禁语义判断；S3/S6 细化。
**证据等级**：A（S0-9/S1 D-4；现有 2D/3D 代码签名不同，A 级反例）+ R。

---

## S3-7 事件契约（最小；导航不进渲染器）

**规则**：事件最小集 `nodeClick(node_id,kind)`、`edgeClick(edge_id)`、`backgroundClick()`；hover/focus 可选且只读；**导航动作（下钻/返回/切换维度/全展开）不在渲染器事件**，由 S5/Presentation 处理；事件不得携带导航状态或正文/用户输入。
**形式化/机检**：
```python
EVENTS = {nodeClick, edgeClick, backgroundClick}; optional {hover, focus}
assert "navigate"/"drill"/"dimensionToggle"/"modeToggle" not in renderer events
assert payload keys ⊆ {node_id,edge_id,kind}
assert no text/body/user input in events
```
**反例**：渲染器发 breadcrumbClick/dimensionToggle；nodeClick 带 history；事件携带正文；edgeClick 触发导航/编辑。
**边界**：cluster nodeClick 由 S5 决定下钻；KP nodeClick 由 S5 跳编辑器；backgroundClick 关闭浮层；hover 仅视觉。
**U 映射**：U-7、U-19、U-20、U-22。
**建议裁决**：冻结最小事件集与 payload；导航事件/动作归 S5；S3 只定义事件语义。
**证据等级**：A（S0-9/S1 D-4）+ C。

---

## S3-8 `no_semantic_edges` 默认视图 UX（不伪造语义簇）

**规则**：S2 `no_semantic_edges`（E_sem 空或无可成立 representative 簇）时：默认视图显示 **KP 节点**（可带结构布局分组，仅布局，明确标注"结构布局"不是簇），显示非阻断提示"暂无已核语义关系（E_sem=0）；可建立语义关系后重算"；**不得**渲染假簇/假边/把结构分组标成 cluster；提供 affordance（查看为什么、如何建立语义）但不自动写数据；agent 可被提示，但 S3 不触发写。
**形式化**：
```
if run.status in {no_semantic_edges, uncalibrated}:
   nodes = KPs (kind=kp); layout = structural layout only
   banner/empty-state text; legend says "结构布局（非语义簇）"
   no representative cluster nodes; no semantic edge styling
   counts: cluster_count=0; do not show fake "N 簇"
else normal
```
**机检**：
```python
assert no_semantic_edges => no cluster node with representative=true
assert structural grouping not labeled "簇"/"语义"; data-testid/aria labels distinct
assert banner present and localized; no data writes
assert no fake cluster count
```
**反例**：无簇时把目录分组画成簇并显示"N 个簇"；把 structural 边画成语义；空状态只显示"加载中"；自动触发聚类/写数据。
**边界**：E_sem=0（frozen 当前状态）；E_sem 不足（coverage 低）；root_exempt 存在但不代表普通簇；A 维度仍可用一条跳（若有边）。
**U 映射**：U-3、U-5、U-27；S2-12。
**建议裁决**：冻结无簇 UX（KP + 结构布局标注 + 提示/affordance）；禁止伪造簇/语义；不触发写。
**证据等级**：A（S2-12 冻结；G5 frozen `asserted=0`）+ C（UX）。

---

## S3-9 默认 vs 全展开视觉

**规则**：默认层次视图（H）与全展开开关共用同一 DataSource/ViewModel/Renderer；全展开是 `ctx.mode=full_expand` 的**相同视图模型**（节点/边同一来源），视觉差异只限取景集/标签密度；切换反馈明确；状态保持由 S5 负责；**不得**第二数据源/第二渲染器/另一套语义。
**形式化**：
```
默认: H 当前层 VM；全展开: 同 DataSource/同一 buildViewModel(ctx_full)；
视觉：默认聚合/少节点；全展开更多节点；同一 kind/token；边仍 present shown
切换：Presentation 调用 S5；VM 只变 content，无 mode 字段；焦点映射 S5
```
**机检**：两模式 VM 来自同一 builder；full VM nodes/edges ⊆ 数据投影；无第二数据文件/渲染器；VM 无 mode；切换后 token/kind 不变。
**反例**：全展开独立数据源/渲染器；VM 带 mode；切换后节点类型/语义变化；默认仍画全部节点。
**边界**：最小层收敛；全展开性能差走预算；切换失败保留旧 VM。
**U 映射**：U-3、U-5、U-26、U-32。
**建议裁决**：冻结同源同 VM/同渲染器、视觉 token 一致；模式/切换归 S5；禁第二数据源。
**证据等级**：A（S0-8/S0-9 冻结）+ C。

---

## S3-10 可访问性

**规则**：对比度（WCAG AA：文本 4.5:1、大文本/图形 3:1）、键盘焦点可见、`aria` 语义（节点/边/簇展开/状态）、reduced motion 遵循 `prefers-reduced-motion`、读屏可理解层次/维度切换；不得仅靠颜色编码类型/状态。
**机检**：
```python
assert contrast(token.text, bg) >= 4.5 (or 3 for large)
assert keyboard focus ring token; tab order deterministic
assert aria-label for nodes (kind/label), edges (type/presence), cluster expand
assert prefers-reduced-motion => no animation / minimal
assert status not color-only (shape/text/legend)
```
**反例**：仅颜色区分 semantic/structural；无 aria-label；动画不可关；键盘不可达；对比度不足。
**边界**：2D canvas/3D canvas 的无障碍替代列表；reduced motion；屏幕阅读器层次切换公告。
**U 映射**：U-2、U-19、U-33。
**建议裁决**：冻结 a11y 最低要求与机检项；视觉 token 需附对比度值；3D 提供等价 2D/列表替代。
**证据等级**：A（现有 `graph-view-2d` 无 aria/reduced 证据）；C（WCAG）+ PI（token 数值）。

---

## S3-11 性能与稳定预算

**规则**：必须有**显示预算**：单屏节点/边上限、帧率目标、drill 后布局稳定性、动画时长；U-32 的"规模不是问题"指后端，前端仍需预算与退化；超限显式降级（减标签/聚合/提示），不得静默丢语义；预算参数化，S8 定数值。
**形式化**：
```
budget = {max_nodes, max_edges, target_fps, max_animation_ms, layout_stability_epsilon}
超限: 降级 levels (hide labels -> aggregate -> show notice)，保留 presence 语义
drill 后节点位置稳定性: 同一 focus 的局部坐标变化 ≤ ε（或保持）
```
**机检**：budget 字段存在/数值 S8；渲染节点/边 ≤ max；超限状态可枚举；动画时长上限；布局稳定性测试（drill 前后坐标）。
**反例**：无预算；超限静默丢节点/边；drill 后全图跳动；动画阻塞交互；用性能理由改语义。
**边界**：超大图；空图；3D 降级；reduced motion（动画 0）。
**U 映射**：U-3、U-18、U-32。
**建议裁决**：冻结预算字段/超限降级/布局稳定/动画上限；数值 S8；不得以预算改语义。
**证据等级**：A（U-32；现有 `graph-view-2d` 无预算字段）+ C + PI（数值）。

---

## S3-12 与 S1/S2 的一致性

**规则**：VM 只含 S1/S2 允许字段（`level_id/dimension_id/view_family_id` + 节点/边视图），**不含** cluster run/dendrogram/membership 状态、mode/导航/capabilities；视觉编码从 VM 数据派生，不在渲染器重算簇/μ/β；`data_edge_ids` 仅用于审计/计数，不直接暴露内部；`no_semantic_edges`/coverage 状态来自 S2 run，不由渲染器猜。
**形式化/机检**：
```python
assert vm has no {cluster_run_id,dendrogram,membership_state,mu,beta,params_hash,mode,nav}
assert renderer does not import cluster/collector; no compute mu/beta/present
assert cluster count/label from vm fields; data_edge_ids only count/audit
assert S1/S2 statuses (no_semantic_edges etc.) passed through VM/status, not re-inferred
```
**反例**：VM 带 run/membership/μ/β；渲染器计算簇/选择；display 计数从 data_edge_ids 内部算并暴露；S2 no-cluster 状态由渲染器猜。
**边界**：3D/2D 只读；A 维度切换只换 VM；S2 run 更新需新 VM。
**U 映射**：U-27、U-33；S0 D-4、S1 D-4、S2 R-S2-6/12。
**建议裁决**：冻结 VM 纯度/渲染器只读/状态透传；S6 契约细化。
**证据等级**：A（S0-9/S1 D-4/S2 R-S2-9/12 冻结）+ R。

---

## 附：本提案对 S3 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| 每视觉编码可机检（字段→token 映射） | S3-1/S3-2/S3-5/S3-10 有映射/断言 ✅ |
| 渲染接口 schema 可校验；2D/3D 同签名 | S3-6 | 
| 事件最小/导航不在渲染器 | S3-7 | 
| no_semantic_edges UX 不伪造语义簇 | S3-8 | 
| A/B 差异逐条 | 见 `S3-objections.md`（写完对照） |
| 覆盖 U-3/5/6/15/16/18/19/20/26/27/33 | §0.1 ✅ |
| 不写产品代码/契约/commit | 本文件只写设计 ✅ |

> 独立声明：本文件写作时未读 `S3-visual-proposal-A.md`（尚未落盘）；差异与判断见 `S3-objections.md`，逐项列不合并。
