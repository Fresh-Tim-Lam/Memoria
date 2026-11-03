# S3 节点视觉与渲染接口提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S3-RULINGS.md`（R-S3-1..R-S3-8）；最高原话 `multilevel-graph-vision.md`；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`），不得违反。
> **输入**：B v1（`0abc2f2b…`）、A v1（`7997a893…`）、`S3-objections.md`。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S3-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S3-RULINGS/S0/S1/S2 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S3）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S3-2 | label 要求 min canonical member name | **冻结 label 确定性规则：min canonical 成员 id 的 KP label + 本地化「等 N 个」；root_exempt=「全库」；禁 local_seq/run 序号；补跨 run 稳定机检**（R-S3-1） | 修正 |
| 2 | S3-11 | 预算归属未定 | **预算归属=S4 选点/裁剪（presence=suppressed+rule_id）；Renderer 只校验/渲染；超硬上限 `RENDER_BUDGET_EXCEEDED` fail-visible；max 值 S8**（R-S3-2） | 修正 |
| 3 | S3-1/S3-5 | bridge 可 role/state | **v1 无 node role=bridge 视觉**；桥只作 edge `state=bridge_only` + 成员统计；VM node role∈{member,focus}（R-S3-3） | 修正 |
| 4 | S3-6 | 接口 mount | **接口统一 `render(container,vm)/update(vm,opts)/dispose()/on(event)/getCapabilities()`**；不用 mount、无 setSelection（R-S3-4） | 修正 |
| 5 | S3-8 | 无簇 UX 含 layout_group | **layout_group 必须 `semantic=false`、非 cluster kind、无簇徽标/计数/展开；agent 入口仅用户动作**（R-S3-5） | 修正 |
| 6 | S3-4 | 层次 chrome 全归 Presentation | **VM 可带 level_label；渲染器可画非交互层标；面包屑/层级条/历史/切换归 Presentation/S5**（R-S3-6） | 并集 |
| 7 | S3-2/S3-3 | cluster 公式未给；KP 可用 degree | **吸收 A 的 cluster 公式 `clamp(8+2.2*log2(n+1),12,28)`；v1 KP 固定大小（不按 degree/权重）**；2D/3D 同 token（R-S3-7） | 并集 |
| 8 | S3-2/S3-5/S3-10/S3-11/S3-12 | token 表/a11y/预算字段较简 | **吸收 A 的 token 表/无簇 UX/a11y 要求/预算字段**；`metrics` 不进 VM；`layout_group` 进白名单但 semantic=false；`data_edge_ids` 不进渲染器；root_exempt 外观（R-S3-8） | 并集 |

---

## 0.1 覆盖矩阵（U + S0/S1/S2）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-3 | 海量/错线→S3-11 预算 | U-15/U-16 | 一跳/选择性渲染=S3-5 |
| U-5/U-6 | 非全展开/簇节点=S3-1/S3-2 | U-17 | 背后图不带入=S3-5 |
| U-18 | 防多跳=S3-11 | U-19/U-20 | 点击/编辑器=S3-3/S3-7 |
| U-26 | 默认/全展开=S3-9 | U-27 | 存无/类型=S3-5 |
| U-33 | 2D/3D=S3-6 | U-34 | 逐议项=本文件 |
| S0-9/D-4 | VM 纯度/kind=S3-1/S3-6/S3-12 | S1 D-4/D-5 | 维度不进 VM=S3-6/S3-12 |
| S2-6/7 | singleton/root/role=S3-1/S3-2 | S2-12 | no_semantic_edges UX=S3-8 |
| S2-9/R-3 | data_edge_ids 审计=S3-12 | S3 R-S3-3 | bridge 边界=S3-1/S3-5 |

---

## S3-1 节点类型与视觉语义

**规则**：节点 `kind ∈ {kp, cluster}` **只有两类**；singleton/`representative=false` 以 `kind=kp` 呈现；**v1 不允许 node `role=bridge` 视觉**（桥只作 edge `state=bridge_only` + 成员统计）；VM node `role ∈ {member, focus}`；hover/selected 是渲染器/Presentation 瞬态，不进 VM。
**形式化/机检**：
```python
assert all(n.kind in {"kp","cluster"} for n in vm.nodes)
assert all(n.kind=="kp" for n in vm.nodes if n.kind=="cluster" and n.member_count==1) is False
assert {n.role for n in vm.nodes} <= {"member","focus"}
assert "bridge" not in {n.role for n in vm.nodes}      # R-S3-3
assert "bridge" not in {n.kind for n in vm.nodes}
assert no third kind / no bridge node shape
```
**反例**：kind=bridge/group/singleton；singleton 画成 cluster；role=bridge 虚线外环（第三类外观）；把 hover 写进 VM；selected 通过未定义接口。
**边界**：cluster 节点 role=member/focus；root_exempt 仍是 cluster 带标志；A 一跳端点 role=member（非 bridge）；点击语义按 kind（S3-7）。
**U 映射**：U-6、U-19、U-33。
**建议裁决**：冻结 kind 两类、singleton→kp、v1 无 bridge node role、role∈{member,focus}；交互态不进 VM。
**证据等级**：A（S2 R-S2-7；S0-9；现有 `graph-engine.js` 无 kind）+ R（R-S3-3）。

---

## S3-2 簇节点视觉编码（大小/计数/label/root）

**规则**：簇视觉大小用成员数公式；badge=真实 `member_count`；**label 确定性**：取最小 canonical 成员 id 的 KP label，成员>1 加本地化「等 N 个」；`root_exempt` 显示「全库」特殊外观；禁止 local_seq/run 序号；禁止空簇/伪造计数。
**形式化**：
```
r_cluster = clamp(8 + 2.2*log2(member_count+1), 12, 28)  # px @ zoom=1; 2D/3D 同 token
member_count = VM.nodes[i].member_count（必填 ≥2；无/小于2 ⇒ RENDER_VM_INVALID）
label = label(min canonical member id) + (member_count>1 ? i18n("等 {N} 个") : "")
root_exempt=true ⇒ 虚线外环/徽标「全库」，不显示普通簇计数
```
**2D/3D token 表（吸收 A；2D/3D 同字段映射）**：
| VM 字段 | 值 | 2D token | 3D token |
|---|---|---|---|
| `kind` | `kp` | 圆，固定 8px | 球，固定 scale |
| `kind` | `cluster` | 圆角方，半径 `clamp(8+2.2*log2(n+1),12,28)`px | 多面体，同公式 |
| `root_exempt` | true | 虚线双环 + “全库” | 双壳 + “全库” |
| `role` | `focus` | 高亮描边 | 自发光 |
| 计数 | `member_count` | badge 数字 | badge 数字 |
**机检**：
```python
assert cluster.member_count == len(members) >= 2
assert cluster.label == deterministic_label(members)  # min canonical member label + suffix
assert cluster.label 不含 local_seq/run 序号（跨 run 同成员集一致）
assert radius == clamp(...); root_exempt flagged distinctly
assert no fabricated count
```
**反例**：label 用 local_seq（同成员簇其他簇增删后名漂移）；label 随机/取中心 KP 未定义；badge 与成员数不符；root_exempt 当普通簇；空簇渲染。
**边界**：count=2 ⇒ r clamp 12；大 count cap 28；root_exempt；成员标签缺失时用稳定 fallback（如 canonical id 短串，见 S3-12），不用 local_seq；跨 run/版本同成员集 label 稳定。
**U 映射**：U-6、U-14、U-19。
**建议裁决**：冻结 A 的公式、badge、确定性 label（min canonical member + 等 N 个）、root_exempt「全库」；禁 local_seq。
**证据等级**：A（A S3-2 公式/token；S2 R-S2-6）+ R（R-S3-1/R-S3-7）+ PI（后缀文案）。

---

## S3-3 KP 节点视觉与状态

**规则**：KP 显示名称（数据 label）；可选 range_ok 标记；**v1 KP 固定大小**（不按 degree/权重缩放）；不显示未判定 semantic 标签；点击 affordance 暗示可跳编辑器（U-20），行为由 S5；KP 身份不因 H/A/维度切换改变。
**形式化**：
```
kp.radius = FIXED 8px（v1 token；2D/3D 同 token；不随 degree/权重变）
kp.label = canonical data label; range_ok=false ⇒ 定位不可用标记
semantic badge 仅当数据 label=semantic；不得将 structural/reference 显示成语义
click affordance（cursor/underline）与 S5 行为一致；渲染器不执行跳转
```
**机检**：KP radius 常量/无 degree 输入；无 semantic badge 当 label≠semantic；hover/selected 状态 token；nodeClick 只发事件。
**反例**：KP 用 degree 6–10px 缩放（结构度暗示重要性）；所有 KP 标 semantic 色；点击渲染器自己跳转；长名称无 tooltip。
**边界**：range_ok=false；同名不同 id；H/A 同 KP 身份一致；固定大小在 2D/3D 同 token。
**U 映射**：U-1、U-19、U-20、U-27。
**建议裁决**：冻结 KP 固定大小/label/range 标记/点击提示；语义标签只由数据决定；渲染器不导航。
**证据等级**：A（S0-1/S0-9；现有 degree→radius 反例 `graph-engine.js:14-84`）+ R（R-S3-7）。

---

## S3-4 层次感知

**规则**：VM 可带 `level_label`（本地化字符串）；渲染器可画**非交互层标**；面包屑/层级条/历史/切换/缩略图归 Presentation/S5，不进 VM；跨层视觉连续性靠稳定 token/布局，不携带历史。
**形式化/机检**：
```python
VM.level_label? : string（只读标签；不含 level_id 历史/可点击动作）
Renderer 可画 level_label 的非交互文本；不得画面包屑/导航按钮
VM 无 history/breadcrumb/nav/mode；渲染器无 setLevel/navigate
```
**反例**：VM 带面包屑/历史/mode；渲染器处理下钻/切换；level_label 可点击发导航；跨层布局随机跳。
**边界**：H 下钻一层（S1 无 hop）；A 切换不改 level；全展开仍显示层标但无导航状态；3D 同样层标。
**U 映射**：U-4、U-7、U-8、U-34。
**建议裁决**：冻结 level_label 只读/渲染器非交互层标；导航 chrome 归 S5；VM 无导航状态。
**证据等级**：A（S0-9/S1 D-4）+ R（R-S3-6）。

---

## S3-5 边视觉与状态（present 三值/类型；不暗示不存在边）

**规则**：**只渲染 `presence=shown` 的边**；suppressed/unknown 不画成普通边（避免幽灵边）；用图例/aria/计数表达 suppressed/unknown 数量；边类型 `contain(structural)/contain(semantic)/reference/extend` 视觉区分；bridge 只作 edge `state=bridge_only` 视觉 + 统计；类型不得暗示不存在的语义（U-27）。
**形式化**：
```
render_edges = {e | e.presence=="shown"}
edge_style = base_type/contain_kind/label + state∈{normal,bridge_only}
suppressed/unknown: 不进入 render_edges；legend/aria 显示 hidden/unknown count
bridge_only: 边样式（虚线/半透明）与 legend；节点不因 bridge 改变形状/role
H 派生边按 S1；data_edge_ids 不直接画
```
**边 token 表（吸收 A；2D/3D 同 token）**：
| VM 字段 | 值 | token |
|---|---|---|
| `contain_kind=structural` | 结构包含 | 实线 1.0px 中性灰 + 箭头 |
| `contain_kind=semantic` | 语义包含 | 实线 2.0px 强调蓝 + 箭头 |
| `base_type=reference` | 引用 | 虚线 [4,3] 1.0px 弱灰 + 箭头 |
| `base_type=extend` | 扩展 | 实线 1.5px 暖黄 + 箭头 |
| `state=bridge_only` | 跨簇桥 | 类型线型上叠加点线/透明度 + aria「跨簇桥」；不改 type/节点形状 |
| `presence=suppressed/unknown` | 非 shown | 不绘制；仅 legend/aria/计数 |
**机检**：
```python
assert rendered_edges == {e for e in vm.edges if e.presence=="shown"}
assert no ghost edges for suppressed/unknown
assert node role not bridge; bridge only edge state
assert edge type token table covers all types; semantic color only label=semantic
```
**反例**：suppressed/unknown 画淡线/虚线（幽灵边）；reference 用 semantic 色；bridge 改节点外观；未 shown 边可 click。
**边界**：同 pair 多类型；bridge_only；unknown 仅计数；A 一跳只渲染端点边（U-17）；全展开仍按 present。
**U 映射**：U-15、U-16、U-17、U-27。
**建议裁决**：冻结只画 shown + suppressed/unknown 非边 + bridge 仅 edge state + 类型 token 表。
**证据等级**：A（S0-6/S0-8；现有 edgeColor 按 type）+ R（R-S3-3）。

---

## S3-6 渲染接口契约（2D/3D 同签名；VM 纯）

**规则**：canonical 接口：`render(container, vm)`、`update(vm, opts)`、`dispose()`、`on(event)`、`getCapabilities()`；**不用 `mount`**；v1 无 `setSelection`；VM 纯数据（无 mode/nav/history/capabilities/cluster run/dendrogram/metrics）；2D/3D 同签名/同事件 id；渲染器不取数、不算语义/簇、不写状态。
**形式化**：
```ts
interface Renderer {
  getCapabilities(): { renderer: "2d"|"3d"; supportsLabels; supportsKeyboard; supportsAria; supportsAnimation };
  render(container: HTMLElement, vm: ViewModel): void;
  update(vm: ViewModel, opts?: {transition?: "none"|"fade"; preserveCamera?: boolean}): void;
  dispose(): void;
  on(event: "nodeClick"|"edgeClick"|"backgroundClick"|"hover"|"focus", handler): () => void;
}
ViewModel = { schema_version, view_model_id, level_id?, level_label?, dimension_id?, view_family_id?,
             nodes[{id,kind∈{kp,cluster},label,member_count?,representative?,role∈{member,focus},state?,
                    range_ok?, layout_group?}],
             edges[{id,source,target,base_type,contain_kind?,label?,presence,rule_id?,state?}] }
禁止 VM: mode/focus/history/breadcrumb/capabilities/cluster_run/dendrogram/metrics/params
```
**机检**：2D/3D 原型方法名/arity 一致；同 fixture id 集相等；VM schema 拒绝禁用字段；渲染器无数据层 import；无 `mount`/`setSelection`；capabilities 独立。
**反例**：2D/3D 不同签名；VM 带 capabilities/mode/metrics；渲染器 fetch/get_graph_data；v1 用 mount/setSelection；渲染器写导航。
**边界**：3D WebGL 失败 → capabilities 说明，S5 回 2D；空 VM；重复 render；update 幂等。
**U 映射**：U-19、U-20、U-33、U-34。
**建议裁决**：冻结接口名/VM 白名单/2D/3D 同签名/渲染器只读；v1 无 mount/setSelection。
**证据等级**：A（S0-9/S1 D-4；现有 2D/3D 签名不同反例）+ R（R-S3-4）。

---

## S3-7 事件契约（最小；导航不进渲染器）

**规则**：必需 `nodeClick{node_id,kind}`、`edgeClick{edge_id}`、`backgroundClick{}`；可选 `hover/node_id|null`、`focus/node_id|null`；事件不得携带 mode/dimension/level/history/run/key/navigate；导航动作由 S5 消费事件执行；渲染器无导航 API。
**机检**：payload key 白名单；2D/3D 同结构；渲染器静态检查无 `jumpToTarget/navigate/mode`；键盘 Enter/Space 等价 click；重复点击去抖。
**反例**：事件带 mode/level/导航；渲染器内部返回/展开；cluster click 直接跳编辑器；事件带 data_edge_ids/成员列表。
**边界**：cluster nodeClick 由 S5 决定下钻；kp nodeClick 由 S5 跳编辑器；backgroundClick 关浮层；键盘等价。
**U 映射**：U-7、U-19、U-20、U-22。
**建议裁决**：冻结最小事件集/payload/导航归 S5；hover/focus 可选。
**证据等级**：A（S0-9/S1 D-4）+ C。

---

## S3-8 `no_semantic_edges` 默认视图 UX

**规则**：S2 `no_semantic_edges`/representative 簇=0/coverage=0 时：显示 KP（singleton 以 kp）；允许**仅布局**文档结构分组但必须 `layout_group.semantic=false`、非 cluster kind、无簇徽标/计数/展开；banner「尚无语义簇」+ coverage 0%；agent 入口**仅用户动作**、不自动调用/不写；不得注入结构边或伪造语义簇。
**形式化**：
```
if status in {no_semantic_edges, uncalibrated}:
  nodes = KPs; layout_group allowed {semantic:false, cluster_kind:false}
  no cluster node/badge/count; no fake semantic edges
  banner + i18n keys; affordance user-click only
  cluster_count displayed = 0; coverage = 0
```
**机检**：
```python
assert no_semantic_edges => no cluster nodes with representative=true
assert layout_group.semantic is False and no cluster token/badge/count
assert banner/affordance DOM exists; no auto agent call
assert coverage displayed==0; no fake cluster count
```
**反例**：结构分组画成簇并显示"N 个簇"；layout_group 有 cluster class/member_count；自动调 agent；空状态空白。
**边界**：E_sem=0（frozen 现状）；E_sem>0 但无合格簇；用户切全展开仍无簇；多语言。
**U 映射**：U-1、U-3、U-6、U-13、U-14、U-27。
**建议裁决**：冻结 KP+layout_group(semantic=false)+banner/affordance（仅用户动作）；不伪造语义。
**证据等级**：A（S2-12；G5 frozen asserted=0）+ R（R-S3-5）。

---

## S3-9 默认 vs 全展开视觉（同源）

**规则**：默认 H 与全展开共用同一 DataSource/VM/Renderer；全展开是同源 buildViewModel 的视图差异（节点/边更多），视觉 token 一致；切换反馈/状态归 S5；**不得第二数据源/第二渲染器/另一套语义。
**机检**：两模式 VM 同一 builder；full 节点/边 ⊆ 数据投影；无第二数据文件/渲染器；VM 无 mode；token/kind 一致。
**反例**：全展开独立数据源/渲染器；VM 带 mode；切换后类型/语义变化；默认仍画全部。
**边界**：最小层收敛；性能预算走 S4/S8；切换失败保留旧 VM。
**U 映射**：U-3、U-5、U-26、U-32。
**建议裁决**：冻结同源同 VM/同 token；模式/切换归 S5；禁第二数据源。
**证据等级**：A（S0-8/S0-9）+ C。

---

## S3-10 可访问性

**规则**：对比度 WCAG AA（文本≥4.5:1、大文本/图形≥3:1）；键盘焦点可见、tab 顺序确定；aria 标签（节点 kind/label、簇展开、边类型/presence）；reduced motion 遵循 `prefers-reduced-motion`；类型/状态不得仅靠颜色；3D 提供 2D/列表等价。
**机检**：
```python
assert contrast(token)>=4.5/3.0; assert focus ring token
assert aria-label for node/edge/cluster expand; assert keyboard reachable
assert prefers-reduced-motion => animation <= 0/短暂
assert status not color-only (shape/text/legend)
```
**反例**：仅颜色区分 semantic/structural；无 aria；动画不可关；键盘不可达；3D 无替代。
**边界**：2D/3D canvas 的 DOM 替代列表；屏幕阅读器层次/维度切换公告；reduced motion。
**U 映射**：U-2、U-19、U-33。
**建议裁决**：冻结 a11y 最低要求/对比度/token 断言；3D 提供等价替代。
**证据等级**：A（现状无 aria/reduced 证据）+ C（WCAG）+ PI（token 数值）。

---

## S3-11 性能与稳定预算

**规则**：显示预算字段：`max_nodes/max_edges/target_fps/max_animation_ms/layout_stability_epsilon`；**S4 负责选点/裁剪**（超预算输出 suppressed+rule_id）；Renderer 只校验/渲染已选 VM，**不得自行裁剪/静默丢**；VM 超硬上限 ⇒ `RENDER_BUDGET_EXCEEDED` fail-visible；数值 S8；drill 后布局稳定。
**形式化/机检**：
```python
budget = {max_nodes,max_edges,target_fps,max_animation_ms,layout_stability_epsilon} # 数值 S8
assert S4 selected/trimmed: over-budget => suppressed + rule_id
assert renderer no trimming/silent drop
assert vm.nodes > max_nodes or vm.edges > max_edges => RENDER_BUDGET_EXCEEDED (fail-visible)
assert drill layout delta <= epsilon; animation <= max_animation_ms
```
**反例**：Renderer 自行裁 200 节点；S4/Renderer 两套裁剪；超预算静默丢；drill 后全图跳动；用性能理由改语义。
**边界**：超大图 S4 裁剪；空图；3D 降级；reduced motion 动画 0；S4 未裁时 Renderer fail-visible。
**U 映射**：U-3、U-18、U-32。
**建议裁决**：冻结预算字段/归属（S4 裁/Renderer 校验）/失败语义/布局稳定；数值 S8。
**证据等级**：A（U-32；现有无预算字段）+ R（R-S3-2）+ PI（数值）。

---

## S3-12 与 S1/S2 的一致性

**规则**：VM 白名单只含 `schema_version/view_model_id/level_id/level_label?/dimension_id?/view_family_id?/nodes/edges/layout_group?`；不含 cluster run/dendrogram/membership/μ/β/metrics/mode/nav/capabilities；label 由 VM 给（确定性规则 S3-2）；视觉编码从 VM 派生；渲染器不重算簇/μ/β/present；`data_edge_ids` 不进渲染器；S2 状态（no_semantic_edges 等）透传。
**机检**：
```python
assert vm keys ⊆ {schema_version,view_model_id,level_id,level_label,dimension_id,view_family_id,nodes,edges,layout_group}
assert no {cluster_run_id,dendrogram,membership,mu,beta,metrics,params_hash,mode,nav,breadcrumb}
assert renderer no cluster/collector import; no compute mu/beta/present
assert node label deterministic; data_edge_ids absent renderer
```
**反例**：VM 带 run/membership/μ/β/metrics；渲染器算簇/选择；display 计数从 data_edge_ids 暴露；S2 状态由渲染器猜。
**边界**：3D/2D 只读；A 切换只换 VM；S2 新 run 需新 VM；layout_group 仅布局。
**U 映射**：U-27、U-33；S0 D-4/S1 D-4/S2 R-S2-6/12。
**建议裁决**：冻结 VM 白名单/渲染器只读/状态透传；`layout_group.semantic=false`；S6 契约细化。
**证据等级**：A（S0-9/S1 D-4/S2 R-S2-9/12 冻结）+ R（R-S3-8）。

---

## 附：R-S3 自检（8 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S3-1 label 确定性 | S3-2（min canonical member + 等 N 个；root_exempt「全库」；禁 local_seq；跨 run 机检） |
| R-S3-2 预算归属 | S3-11（S4 裁剪；Renderer 校验/渲染；超硬上限 fail-visible；max S8） |
| R-S3-3 bridge 边界 | S3-1/S3-5（无 node role=bridge；只 edge state；role∈{member,focus}） |
| R-S3-4 接口 | S3-6（render/update/dispose/on/getCapabilities；无 mount/setSelection） |
| R-S3-5 无簇 UX | S3-8（layout_group semantic=false/非 cluster；agent 入口仅用户动作） |
| R-S3-6 level_label | S3-4（VM 只读 level_label；非交互层标；导航归 S5） |
| R-S3-7 KP 大小/cluster 公式 | S3-3（KP 固定）/S3-2（A 公式；2D/3D 同 token） |
| R-S3-8 并集 | S3-2/S3-5/S3-8/S3-10/S3-11/S3-12（token 表/a11y/预算/VM 白名单/metrics 不进 VM） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S3-objections-v2.md`；未写产品代码/契约，未 commit。
