# S3 提案 A-v2：节点视觉与渲染接口（确定性 label / 预算单一归属 / 两类节点）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-308｜**日期**：2026-11-03（Asia/Shanghai）
> **唯一修订依据**：`docs/design/multilevel-graph/S3-RULINGS.md`（R-S3-1..R-S3-8；Lead 已复核 2 P1 + 1 裁）。
> **最高依据**：`multilevel-graph-vision.md`；上游冻结：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）。
> **本文件**：A 修订版；**不覆盖** `S3-visual-proposal-A.md`（v1 `7997a893…`），保留审计链。
> **纪律**：不写产品代码、不改 S0/S1/S2 冻结稿/契约、不 commit；独立写。

---

## 0. 修订摘要（R-S3 → 结构变化）

| 裁决 | v1 问题 | v2 落实 |
|---|---|---|
| **R-S3-1（P1）** 簇 label 确定性 | v1 label 由取景层生成、fallback 用 `local_seq` ⇒ 成员增删后显示名漂移 | 冻结 `label = label_of(min canonical member id)`；>1 成员加本地化「等 N 个」；`root_exempt`→「全库」；**禁止 local_seq 作显示名**；fallback=`cluster_key` 短前缀；机检跨 run 稳定 |
| **R-S3-2（P1）** 预算归属 | v1 Renderer 可拒绝或 S4 裁剪（两套行为） | **S4 负责选点/裁剪**（`presence=suppressed+rule_id`）；Renderer 只校验/渲染已选 VM，不裁剪/不静默丢；VM 超硬上限 ⇒ `RENDER_BUDGET_EXCEEDED` fail-visible；数值 S8 |
| **R-S3-3（P1）** bridge 视觉 | v1 node `role=bridge` + 虚线外环（可变成第三类节点） | v1 **禁止 node role=bridge 视觉**；桥只作 edge `state=bridge_only` + 簇成员统计；VM node `role∈{member,focus}` |
| **R-S3-4** 接口命名 | v1 接口带 `on`/opts 但未冻结命名；“可选 setSelection” | canonical：`render(container,vm)` / `update(vm,opts)` / `dispose()` / `on(event)` / `getCapabilities()`；**不用 mount**；v1 **无 setSelection** |
| **R-S3-5** 无簇 UX 边界 | v1 布局分组未强制 `semantic=false` | `layout_group` 必须在 VM 显式 `semantic=false` 且非 cluster kind；KP+仅布局分组+banner；agent 入口**仅用户动作** |
| **R-S3-6/7** 层标/KP 大小 | v1 用 metrics.degree 缩放 KP | VM 可带 `level_label`（渲染器只画**非交互**层标；面包屑/历史归 Presentation）；**KP 固定大小**；簇仍按 member_count 公式 |
| **R-S3-8** 并集 | v1 `metrics` 进 VM、节点字段松 | 吸收 B 的 label 确定性/VM 白名单/bridge 保守；**`metrics` 不进 VM**；`layout_group` 白名单且 `semantic=false`；3D 同 token；`data_edge_ids` 不进渲染器 |

**总口径不变**：`DataSource → ViewModel（纯）→ Renderer（2D/3D 同签名）`；视觉=字段→token 的确定性映射；只渲染 `presence=shown`；无簇合法且不得伪造语义簇。

---

## 1. S3-1 节点类型与视觉语义（只两类；role 仅 member/focus）

**定义/规则（一句话）**：节点只有 `kind∈{kp,cluster}`；v1 **不允许 node `role=bridge` 的视觉表达**（桥只作 edge `state=bridge_only` 与成员统计）；VM node `role∈{member,focus}`；hover/selected 是渲染器/Presentation 瞬态，不进 VM。

**形式化**：
```
VM.nodes[i].kind ∈ {kp, cluster}
VM.nodes[i].role ∈ {member, focus}          # v1 冻结；无 bridge
bridge 表达：
  edge.state=bridge_only（S3-5）
  簇成员统计（S2 CLUSTER/membership 数据；Presentation/检查器使用，不产生节点形状）
singleton：kind=kp（representative=false；无 cluster 外观）
cluster：kind=cluster、representative=true、member_count≥2
交互态：
  hover    渲染器本地瞬态（不写 VM）
  selected 渲染器内部瞬态 + Presentation 驱动（v1 无 setSelection；不进 VM）
  focus    VM.role=focus（导航焦点；S5 产生）
禁止：kind=bridge/group/document；role=bridge；第三形状/点击语义
```
**视觉区分（2D/3D 同数据变量）**：
| VM 字段 | 值 | 2D token | 3D token | a11y |
|---|---|---|---|---|
| `kind=kp` | 固定大小 | 圆，半径 8px（**不随 degree 变**） | 球，固定 scale | "知识点 X" |
| `kind=cluster` | 大小=member_count | 圆角方（12–28px） | 多面体（同公式） | "簇 N，含 M 个知识点" |
| `role=member` | 默认 | 无额外边 | 无额外边 | — |
| `role=focus` | 高亮 | 高亮描边 | 自发光 | "当前焦点" |
| `root_exempt=true` | 特殊 | 虚线双环+"全库" | 双壳 | "全库根块" |
| `singleton` | kp 普通 | 无簇徽标 | 无簇徽标 | 无簇文案 |

**反例**：node role=bridge 画虚线外环（P1）；新增 kind=bridge/group；把 hover 写进 VM；用节点形状编码边类型。
**边界**：bridge 端点仍是 kp/cluster（无特殊节点外观）；selected 可在 update 后丢失（瞬态）；cluster 无子仍可点击（S5 决定是否可展开）。
**机检条件**：
```
- node.kind 枚举 == {kp,cluster}；node.role 枚举 == {member,focus}（无 bridge）
- 无第三形状/点击语义；role=bridge 出现即 FAIL
- VM 无 hover/selected 字段；渲染器无 setSelection 方法
```
**U 映射**：U-6、U-19、U-27、U-33。
**建议裁决**：采纳两类 kind + role∈{member,focus}；bridge 只作 edge state/成员统计。
**证据等级**：A（S0-9 kind；S2 R-S2-7 `S2-clustering-v1.md:43,91`；U-6/U-19）；**本项目假设**（selected 内部瞬态实现）。

---

## 2. S3-2 簇节点视觉（确定性 label/大小/徽标/root_exempt）

**定义/规则（一句话）**：簇节点大小映射 `member_count`（对数、上下限同 v1）；显示名必须由成员**确定性**导出：最小 canonical 成员 id 的 KP label + 「等 N 个」；`root_exempt` 显示「全库」；**禁止 local_seq 作显示名**；label 缺失才用 `cluster_key` 短前缀 fallback。

**形式化（label 冻结，R-S3-1）**：
```
label(C):
  if C.root_exempt: return i18n("全库")                    # 本地化
  members = sorted(C.member_canonical_ids)                 # 以 kp_id 排序
  m = members[0]
  base = label_of(m)                                       # KP 的确定性显示名（不取 local_seq）
  if |C| > 1:
      return base + " " + i18n("等 {n} 个", n=|C|)         # 本地化后缀；n 为成员数
  return base
fallback（base 缺失）: "簇 " + cluster_key[:8]              # cluster_key 短前缀（确定性/可复算）
禁止：local_seq / run 序号 / 取景器临时序号作为显示名
跨 run 稳定：同成员集（canonical id 集相同）⇒ 同 label，即使 run_id/版本变化
```
**大小/徽标**：
```
r_cluster = clamp(8 + 2.2 * log2(member_count + 1), 12, 28)   # px @ zoom=1；2D/3D 同 token
member_count 为 cluster 节点显式字段（≥2）；缺失 ⇒ RENDER_VM_INVALID
badge = member_count；expand_hint = expandable===true ? chevron : none
root_exempt 特殊外观（虚线双环+"全库"）；不显示为普通语义簇
singleton（kind=kp）无 cluster 徽标/计数
```
**反例**：label 用 `local_seq`/run 序号（v1 P1）；用中心 KP 名但未定义"中心"（不可复算）；成员增删后显示名漂移；root_exempt 普通外观；label 缺省 fallback 用随机 id。
**边界**：|C|=2 后缀「等 2 个」；root_exempt 固定「全库」；成员集不变跨 run 同 label；成员变化 ⇒ label 可能变化（确定性规则决定）；本地化由取景区提供，渲染器不翻译；cluster_key fallback 短前缀 8 字符。
**机检条件**：
```
- assert label == deterministic_label(members, root_exempt, locale)
- 同成员集两次 run（不同 run_id）label 相同；label 中不含 local_seq/run 序号
- cluster node member_count≥2；radius 由公式计算
- root_exempt label == "全库"（本地化）；无 local_seq 文案
```
**U 映射**：U-6、U-7、U-21（成员变化感知）。
**建议裁决**：采纳 R-S3-1 确定性 label + 大小公式 + 徽标 + root_exempt 外观。
**证据等级**：A（R-S3-1 `S3-RULINGS.md:19-21`；S2-4 local_seq 定义 `S2-clustering-v1.md:31-35,47-51`；U-6）；**本项目假设**（后缀文案/8 字符前缀）。

---

## 3. S3-3 KP 节点视觉与编辑器跳转提示（U-20；固定大小 R-S3-7）

**定义/规则（一句话）**：KP 节点 v1 **固定大小**（不按 degree/权重缩放）；显示 VM `label`；`range_ok=false` 失效样式；hover/focus 提示"打开知识点"；点击只发 `nodeClick`，由 S5 映射到 `jumpToTarget`。

**形式化**：
```
KP 视觉：kind=kp；固定半径 8px（2D/3D 同 token；不随 degree/权重变）
label = VM.nodes[i].label（截断由 label 模块统一；不显示描述全文）
range_ok=false：去饱和/虚线 + aria "锚点失效"
hover/focus：cursor pointer + 高亮环 + 提示 "打开知识点"（Presentation 文案）
点击：Renderer 发 nodeClick{node_id,kind=kp}；S5 执行 jumpToTarget（U-20）
```
**反例**：按 degree 缩放 KP（v1 P1；结构度量误导）；渲染器点击后直接跳转；用节点颜色编码边类型；range 无效正常样式。
**边界**：单点块与普通 KP 同视觉；KP 无 cluster 徽标；极长 label 由 label 模块处理；3D 标签可隐藏（DOM overlay 提供 a11y）。
**机检条件**：
```
- KP 半径固定（同 VM 下不同 degree 不变；degree 不在 VM）
- 无 member_count 徽标；range_ok=false 有失效 token
- 渲染器无 jumpToTarget/导航调用；nodeClick payload 仅 node_id/kind
```
**U 映射**：U-20、U-19、U-3。
**建议裁决**：采纳固定大小 + 点击提示 + 渲染器不导航。
**证据等级**：A（R-S3-7 `S3-RULINGS.md:43-45`；U-20；`app.js:1661-1677`）；**本项目假设**（固定 8px/提示文案）。

---

## 4. S3-4 层次感知（level_label；面包屑归 Presentation）

**定义/规则（一句话）**：VM 可带 `level_label`（本地化字符串）；渲染器只画**非交互**层标；面包屑/层级条/历史/切换全归 Presentation/S5，不进 VM。

**形式化**：
```
VM 允许 level_id + level_label（本地化显示字符串；可选）
Renderer：可画非交互层标（如画布角落 "L2 · 第 2 层"），不可点击/不可切换
Presentation（S5）：breadcrumb/level-bar/history = f(GRAPH_NAV_FRAME, VIEW_FRAME)
跨层：公共 node id 位置/相机保持；过渡可配置（reduced motion=0）
禁止：VM 带 breadcrumb/history/level list；渲染器实现返回/层级切换
```
**反例**：VM 带面包屑/历史；渲染器"返回上一层"；KP/簇大小表示深度；level_label 被渲染器当逻辑判断。
**边界**：level_label 缺失 ⇒ 只画 level_id；root_exempt L0；叶层全 KP；跨 view_family 由 S5 处理。
**机检条件**：
```
- VM 无 breadcrumb/history/level list；level_label 为字符串或缺失
- Renderer 无导航 action；层标不可交互（无 click handler）
- 跨层 update：common node ids 位置/相机保持（可测）
```
**U 映射**：U-5、U-7、U-8、U-19。
**建议裁决**：采纳 level_label + 非交互层标；其余归 S5。
**证据等级**：A（R-S3-6 `S3-RULINGS.md:39-41`；S0-9/D-4；`ENGINEERING-PLAN.md:713-719`）；**本项目假设**（层标样式）。

---

## 5. S3-5 边视觉与「存无/类型」（U-27；bridge 只作 edge state）

**定义/规则（一句话）**：只有 `presence=shown` 的边可绘制；suppressed/unknown 不画线，只在统计/检查器/aria 说明；bridge 仅作 **edge `state=bridge_only`** 叠加，不改 type/不产生新 type；不得视觉暗示不存在的边。

**形式化（字段→token）**：
```
presence=shown ⇒ 绘制；suppressed/unknown ⇒ 不绘制（统计/检查器/aria 可解释 rule_id）
type/contain_kind（display_type 由 VM 给定）：
  contain(structural) ⇒ 实线 1.0px 中性灰，箭头
  contain(semantic)   ⇒ 实线 2.0px 强调蓝，箭头
  reference           ⇒ 虚线 [4,3] 1.0px 弱灰，箭头
  extend              ⇒ 实线 1.5px 暖黄，箭头
state=bridge_only ⇒ 在类型线型上叠加点线/透明度（不改变 type/颜色语义），aria "跨簇桥"
data_edge_ids：VM 可保留（R-3 审计），Renderer 输入白名单剔除；不逐条渲染
aggregate_count（如提供）显示为边徽标（数值由取景层给，不暴露内部 ids）
```
**反例**：suppressed 画半透明/虚线（暗示存在）；unknown 画虚线；bridge 变成新 type；同对多类型边合并；data_edge_ids 逐条画。
**边界**：同对多类型边分画；reference+extend 同对；bridge_only 的 contain 边；full_expand 仍只画 shown；unknown 不画。
**机检条件**：
```
- 绘制集合 == {edge | presence==shown}（注入 fixture 断言）
- presence!=shown 无图形/DOM；aria 可列 rule_id
- bridge 只改 state token，不改 type；无新 edge type
- Renderer 不读 data_edge_ids；aggregate_count 数字不来自内部 id 遍历
```
**U 映射**：U-15、U-16、U-17、U-27。
**建议裁决**：采纳 shown 唯一判据 + 类型 token + bridge 仅 state + 不画幽灵边。
**证据等级**：A（S0-6/S1-12/U-27；R-S3-3；`graph-engine.js:261`、`graph-view-2d.js:634-663`）；**本项目假设**（颜色/线宽）。

---

## 6. S3-6 渲染接口契约（canonical 命名；无 mount/setSelection）

**定义/规则（一句话）**：Renderer canonical 接口 = `getCapabilities()` + `render(container,vm)` + `update(vm,opts)` + `dispose()` + `on(event)`；2D/3D 同签名；纯 VM 输入、不取数/不做语义/不裁剪；v1 无 `mount`、无 `setSelection`。

**形式化（冻结接口）**：
```ts
interface Renderer {
  getCapabilities(): {
    backend: "2d" | "3d";
    supportsAnimation: boolean;
    supportsKeyboard: boolean;
    supportsAria: boolean;
    maxNodes: number;          // 硬上限（S8 定值）
    maxEdges: number;
  };
  render(container: HTMLElement, vm: ViewModel): void;   // 首次挂载（不是 mount）
  update(vm: ViewModel, opts?: { transition?: "none"|"fade"; preserveCamera?: boolean }): void;
  dispose(): void;                                       // 幂等
  on(event: "nodeClick"|"edgeClick"|"backgroundClick"|"hover"|"focus",
     handler: (p: object) => void): () => void;
}
// v1 不提供：mount()、setSelection()、getState()、navigate()
```
**规则**：
```
R1 2D/3D 方法名/参数/返回一致；同 VM 的 node/edge id 集一致（U-33）
R2 渲染器只吃 VM：不调用 get_graph_data/collect/sidecar/网络；不读 DataSource
R3 不重算 μ/β/cluster/level/admission；不裁剪节点/边（裁剪归 S4，R-S3-2）
R4 capabilities 独立方法，不进 VM
R5 无效 VM/超硬上限 ⇒ RENDER_VM_INVALID / RENDER_BUDGET_EXCEEDED（fail-visible，不部分渲染）
R6 update 同一 VM 幂等；dispose 后调用 no-op/明确错误；无 setSelection
```
**反例**：2D/3D 各自 loadPayload/render(scene) 签名（现状）；接口用 mount；提供 setSelection 写状态；渲染器 fetch/裁剪；VM 带 capabilities。
**边界**：仅 2D 可用（3D WebGL 失败）⇒ capabilities 指明；空 nodes；重复 render 同容器；update 期间 backend 切换由 S5 capture/restore。
**机检条件**：
```
- 2D/3D 原型方法名/arity 一致；无 mount/setSelection
- 渲染器 import 白名单无数据层/网络；无 get_graph_data/fetch
- VM schema 无 mode/nav/capabilities/metrics；capabilities 来自 getCapabilities
- 超预算/无效 VM 抛明确错误码，不部分渲染
```
**U 映射**：U-33、U-16、U-32。
**建议裁决**：采纳 canonical 五方法；2D/3D 同签名；无 mount/setSelection；不裁剪。
**证据等级**：A（R-S3-4 `S3-RULINGS.md:31-33`；S0-9/D-4；`ENGINEERING-PLAN.md:224-250,291`；现状 API 不一致 `graph-view-2d.js:167-181,211`、`graph-view-3d.js:249-262,347`）；**本项目假设**（on/opts 细节）。

---

## 7. S3-7 事件契约（最小集；导航不在渲染器）

**定义/规则（一句话）**：渲染器只发 `nodeClick{node_id,kind}` / `edgeClick{edge_id}` / `backgroundClick{}`（可选 `hover/focus`）；payload 只带 view 标识，不含导航/模式/历史；导航动作由 S5 消费事件后执行。

**形式化**：
```
必需：nodeClick{node_id,kind∈{kp,cluster}} / edgeClick{edge_id} / backgroundClick{}
可选：hover{node_id|null} / focus{node_id|null}
禁止字段：mode/dimension_id/level_id/history/breadcrumb/run_id/cluster_key/navigate*
S5 映射：nodeClick(kp)→jumpToTarget；nodeClick(cluster)→CLICK_CLUSTER；edgeClick→检查器（可选）
键盘 Enter/Space 等价 click；Escape 清除渲染器内部选中（不写 VM）
```
**反例**：事件带 mode/level 决定导航；渲染器实现返回/展开；payload 带 data_edge_ids/成员列表；3D 与 2D payload 不一致（现 3D 无 edge_id）。
**边界**：3D 与 2D 同 payload；重复点击去抖；空白点击；键盘等价；hover 可选不承诺。
**机检条件**：
```
- payload key 白名单；无导航字段
- 2D/3D 同 fixture 的 nodeClick/edgeClick payload 相等
- 渲染器无 jumpToTarget/navigate/mode 调用
```
**U 映射**：U-7、U-19、U-20、U-33。
**建议裁决**：采纳最小事件集 + 统一 payload + 导航归 S5。
**证据等级**：A（S0-9 事件集；R-S3-4；`ENGINEERING-PLAN.md:287,714,848`；2D/3D 差异 `graph-view-2d.js:544-547` vs `graph-view-3d.js:1043`）；**本项目假设**（键盘等价）。

---

## 8. S3-8 `no_semantic_edges` 默认视图 UX（semantic=false 布局分组）

**定义/规则（一句话）**：无簇状态显示 KP + **仅布局**结构分组（VM `layout_group.semantic=false`、非 cluster kind）+ banner + 显式 affordance；agent 仅在**用户动作**时被请求；不得注入结构边/伪造语义簇。

**形式化**：
```
触发：S2 run.status==no_semantic_edges 或 representative_clusters==0 && coverage==0
VM 要求：
  nodes 全 kind=kp（无 cluster）；singleton 以 kp 呈现
  layout_group: {group_id, label, semantic: false}（文档/章节布局提示；非 cluster、无徽标/展开语义）
  edges：只含 S4/H 允许的 shown；reference/structural 不得升级 semantic
UI（Presentation）：
  banner："尚无语义簇" + "未发现 semantic 边（0 个语义簇，coverage 0%）。这是合法空状态；
          不会用结构/引用边伪造语义簇。"
  affordance（仅用户点击）：[让 agent 建立语义关联]（用户确认后走 S10）/[结构布局]/[全展开]/[帮助]
  不得自动触发 agent；不得把布局分组称"簇"
```
**反例**：layout_group 用 cluster kind/徽标/展开；`semantic=true` 或缺失；banner 缺失；自动调用 agent；用 structural contain 造簇；coverage=0 显示簇数>0。
**边界**：E_sem=0 大图（KP 拥挤，S4/预算处理）；E_sem>0 无合格簇（"已发现 N 条 semantic 边但无合格簇"）；切全展开仍无簇；多语言文案走 i18n。
**机检条件**：
```
- empty 模式 VM nodes 无 kind=cluster；layout_group.semantic===false 且非 cluster
- banner/affordance 存在（DOM）；agent 请求只由用户点击触发（无自动调用）
- 文案不含"语义簇"用于 layout_group；coverage=0 时不显示簇数>0
- 结构边不进入 E_sem/簇判据
```
**U 映射**：U-1、U-3、U-6、U-13、U-14、U-27。
**建议裁决**：采纳 KP+仅布局分组+banner+用户动作 affordance；禁伪造簇/自动 agent。
**证据等级**：A（R-S3-5 `S3-RULINGS.md:35-37`；S2-12 `S2-clustering-v1.md:73-76`；S2 probe E_sem=0）；**本项目假设**（文案/按钮形式）。

---

## 9. S3-9 默认 vs 全展开的视觉（不得第二数据源）

**定义/规则（一句话）**：默认层次视图与全展开是同一 DataSource/同一 VM schema/同一 Renderer 的两个 Presentation 模式；视觉差异只在选点/边集与"全展开"标识；无第二数据源/第二语义模型。

**形式化**：
```
default = H 层次视图（cluster/KP；per-level VM），S4 选择性渲染
full    = 同一 DataSource→同一 VM 生成器（ctx_full）→同一 Renderer
差异：full 显示更全的 shown 边；reference/structural 按类型 token（不升级 semantic）；
      全展开徽标 "全展开（兼容模式，不改变语义）"
切换：Presentation 工具栏（S5/S3 UI）；S5 保持焦点/相机；动画 180ms/reduced 0ms
禁止：第二数据文件/渲染器/语义模型/第二 id 集
```
**反例**：全展开另开数据/渲染器；full 把 structural 当 semantic；两套缓存漂移；切换丢焦点无提示。
**边界**：默认叶层与 full 选点接近（同数据）；full 仍只画 shown；返回默认保持导航（S5）。
**机检条件**：
```
- 两模式 DataSource 身份相同；同一 VM schema/Renderer
- full 徽标存在；full 边仍 presence=shown 才画
- 无第二 builder/数据源；切换焦点/相机由 S5 保持/映射
```
**U 映射**：U-3、U-5、U-16、U-26、U-27。
**建议裁决**：采纳同源同接口 + 全展开徽标；不引入第二数据源。
**证据等级**：A（S0-8；S1-13；`ENGINEERING-PLAN.md:717`）；**本项目假设**（徽标/动画）。

---

## 10. S3-10 可访问性（无 setSelection；renderer 内部瞬态）

**定义/规则（一句话）**：对比度、键盘焦点、aria（节点/簇展开/空状态）、reduced motion 必须满足；canvas 配 DOM overlay；v1 无 `setSelection`（焦点/选中由渲染器内部瞬态 + Presentation 事件驱动，不进 VM）。

**形式化**：
```
对比度：文本≥4.5:1、图形≥3:1；颜色不作唯一通道（类型用线型+图例）
键盘：Tab 进入图；方向键在节点间移动；Enter/Space=nodeClick；Escape 清除内部选中；焦点环≥2px
aria（DOM overlay 由 VM 派生）：容器摘要；节点 role=button aria-label；cluster aria-expanded；
  边不逐条聚焦（检查器列表说明类型/状态/rule_id）；空状态/降级 aria-live
reduced motion：prefers-reduced-motion ⇒ 动画 0ms（无 pulse/淡入/相机飞行）
v1 无 setSelection：Presentation 不通过接口设选中；渲染器内部 transient selection
```
**反例**：只用颜色区分类型（色盲失败）；canvas 无 tabindex/aria（现状）；setSelection 写 VM/状态；动画不可关；焦点不可见。
**边界**：3D 用 2D 同构 DOM overlay；超大图摘要+列表；高对比主题 token；selected 可 update 后丢失。
**机检条件**：
```
- token 对比度测试（文本4.5/图形3）；类型有非颜色通道
- 容器 tabindex=0；节点可聚焦；Enter/Space 触发 nodeClick；focus 可见
- aria-label/aria-expanded/aria-live 存在；reduced motion 动画=0
- 接口无 setSelection；VM 无 selection 字段
```
**U 映射**：U-3、U-18、U-33。
**建议裁决**：采纳对比度/键盘/aria overlay/reduced motion；无 setSelection。
**证据等级**：A（R-S3-4；现状无 aria/tabindex：`graph-view-2d.js`/`graph-view-3d.js`/`graph-engine.js` 计数 0；`graph-engine.js:270-327` 视觉通道）；**本项目假设**（WCAG 细节/键位）。

---

## 11. S3-11 性能与稳定预算（S4 裁剪；Renderer 只校验）

**定义/规则（一句话）**：**S4 负责选点/裁剪**（超预算输出 `presence=suppressed+rule_id`）；Renderer 只校验并渲染**已选 VM**，不自行裁剪/不静默丢；VM 超过硬上限（`max_nodes/max_edges`）⇒ `RENDER_BUDGET_EXCEEDED` fail-visible；数值 S8。

**形式化**：
```
责任：
  S4：选择/裁剪 → VM 中 presence=suppressed + rule_id（hop.budget/node.budget/...）
  Renderer：只校验 VM（nodes/edges 数量 ≤ max_nodes/max_edges）+ 渲染 shown
         不裁剪、不丢弃、不合并；超硬上限 ⇒ RENDER_BUDGET_EXCEEDED（不部分渲染）
  max_nodes/max_edges：S8 定值；S3 只冻结字段/失败语义/capabilities 暴露
预算/稳定：
  target_fps=60（低端30）；animation=180ms（reduced 0ms）
  drill：common node ids 位置/相机保持（位置 delta ≤ 阈值；可 S8 定）
失败：WebGL 初始化失败 ⇒ capabilities 指明 3D 不可用，S5 回退 2D（显式）；VM invalid ⇒ RENDER_VM_INVALID
```
**反例**：Renderer 自行裁剪前 200（与 S4 两套行为，P1）；超预算静默丢节点；S4 不标 suppressed；drill 全局重排跳动；3D 失败静默黑屏。
**边界**：恰好上限；空 VM；低端 30fps；full 超预算由 S4 先裁；Renderer 拒绝时 UI 显示错误（不白屏）。
**机检条件**：
```
- Renderer 无裁剪/丢弃逻辑；绘制集合 == VM shown 集合
- VM 超 max_nodes/max_edges ⇒ RENDER_BUDGET_EXCEEDED（不部分渲染）
- 裁剪只发生在 S4：VM suppressed 有 rule_id；Renderer 不产生 suppressed
- capabilities.maxNodes/maxEdges 存在；动画/帧预算可测
```
**U 映射**：U-3、U-18、U-32。
**建议裁决**：采纳 S4 裁剪 + Renderer 仅校验/渲染 + 超硬上限 fail-visible；数值 S8。
**证据等级**：A（R-S3-2 `S3-RULINGS.md:23-25`；S3 章程 §3；U-32）；**本项目假设**（默认值/阈值）。

---

## 12. S3-12 与 S1/S2 的一致性（VM 白名单；metrics 不进 VM）

**定义/规则（一句话）**：VM 只含 `dimension_id + level/view_family + level_label + nodes/edges + layout_group` 的视图投影；**`metrics` 不进 VM**；簇/run/dendrogram/候选状态不进 VM；`data_edge_ids` 可审计但不进渲染器；视觉只从 VM 字段派生。

**形式化（VM 白名单，R-S3-8）**：
```
允许：
  view_model_id, level_id, level_label?, dimension_id, view_family_id,
  nodes[{node_id, kind, role∈{member,focus}, label, label_key?,
         expandable?, representative?, root_exempt?, member_count?, layout_group?}],
  edges[{edge_id, source, target, type, contain_kind?, label, display_type,
         presence, rule_id?, state?, hop?, underlying_hop_count?, aggregate_count?,
         data_edge_ids?（仅审计，不进 Renderer）}]
  layout_group = {group_id, label, semantic: false}（仅 no_semantic 布局）
禁止：metrics/degree/weight/cluster_run_id/cluster_key/dendrogram/run_status/candidate/
      params_hash/mode/nav/breadcrumb/capabilities/selection
Renderer 输入投影：剔除 data_edge_ids（以及任何审计字段）；不读 data_edge_ids
```
**反例**：VM 带 metrics/degree；VM 带 run/dendrogram；渲染器读 data_edge_ids 逐条画；VM 带 mode/nav；2D/3D id 集不同。
**边界**：cluster member_count 是显式字段（不是 metrics）；layout_group 仅 empty 布局；audit 字段在 VM 外/投影剔除；无簇 VM 无 cluster。
**机检条件**：
```
- VM schema 白名单：禁止字段出现即 fail；metrics 不存在
- Renderer 不读 data_edge_ids/cluster_run/*；2D/3D id 集一致
- layout_group.semantic===false；非 cluster kind
- level_label 字符串；VM 无 mode/nav/capabilities
```
**U 映射**：U-1、U-27、U-33。
**建议裁决**：采纳 VM 白名单（无 metrics）+ 渲染器不读内部 + 视觉派生；S6a 落 schema。
**证据等级**：A（R-S3-8 `S3-RULINGS.md:47-49`；S0-9/D-4；S1-13；S2-11 `S2-clustering-v1.md:69`）；**本项目假设**（字段名细节由 S6a 定）。

---

## 13. 覆盖矩阵

| U# | 要点 | S3 落点 |
|---|---|---|
| U-3 | 海量节点/错线 | S3-2/S3-11（预算/退化） |
| U-5 | 默认非全展开 | S3-9 |
| U-6 | 代表子图节点外观更大 | S3-2 |
| U-15 | 语义边挂接 | S3-5 |
| U-16 | 选择性渲染 | S3-5/S3-11 |
| U-18 | 跳数/显示预算 | S3-11 |
| U-19 | 点击节点 | S3-1/S3-7 |
| U-20 | KP→编辑器 | S3-3/S3-7 |
| U-26 | 默认替代+全展开 | S3-9 |
| U-27 | 边存无/类型 | S3-5/S3-9 |
| U-33 | 2D/3D 不分家 | S3-6/S3-7 |
| S0 | VM 纯度/kind/present/R-3 | S3-1/S3-5/S3-6/S3-12 |
| S1 | H/A 视觉、dimension_id 标签 | S3-5/S3-12 |
| S2 | 无簇合法、singleton/root_exempt/coverage | S3-1/S3-2/S3-8 |

---

## 14. A-v2 变更表（逐条旧→新，含 v1 行号）

> 旧文件：`S3-visual-proposal-A.md`（v1 `7997a893…`）；行号可 grep 复核。

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S3-1（L33）node role 含 bridge + 虚线外环 | role∈{member,focus}；桥只 edge state/成员统计；无第三形状 | R-S3-3 |
| 2 | S3-1 hover/selected 状态说明 | selected 改为渲染器内部瞬态；无 setSelection（§1/§6/§10） | R-S3-4 |
| 3 | S3-2（L73）label 由取景层生成、fallback local_seq | 确定性 label：min member label+「等 N 个」/「全库」/cluster_key 前缀；跨 run 稳定（§2） | R-S3-1 |
| 4 | S3-2 大小/徽标（member_count） | 保留公式；member_count 为显式字段；metrics 不进 VM（§2/§12） | R-S3-8 |
| 5 | S3-3（L111）KP 按 degree 连续半径 6–10px | KP 固定 8px（不按 degree/权重）；3D 同 token（§3） | R-S3-7 |
| 6 | S3-4（L137）层次指示归 Presentation | VM 允许 level_label；渲染器只画非交互层标；面包屑/历史归 S5（§4） | R-S3-6 |
| 7 | S3-5（L166）边视觉 | 保留；明确 data_edge_ids 不进 Renderer；bridge 仅 state（§5） | R-S3-3/8 |
| 8 | S3-6（L200）接口含 on/opts 但未冻结；可选 setSelection | canonical 五方法；不用 mount；无 setSelection；Renderer 不裁剪（§6） | R-S3-4 |
| 9 | S3-7（L248）事件集 | 保留；统一 2D/3D payload（§7） | R-S3-4 |
| 10 | S3-8（L278）布局分组未强制 semantic=false | layout_group 显式 semantic=false、非 cluster；agent 仅用户动作（§8） | R-S3-5 |
| 11 | S3-9（L323）默认/full 视觉 | 保留；同源同接口/徽标（§9） | 本轮 |
| 12 | S3-10（L353）可访问性 | 保留；无 setSelection；选中为内部瞬态（§10） | R-S3-4 |
| 13 | S3-11（L384）Renderer 可拒绝或 S4 裁剪 | S4 裁剪；Renderer 仅校验/渲染；超硬上限 RENDER_BUDGET_EXCEEDED（§11） | R-S3-2 |
| 14 | S3-12（L418）VM 允许 metrics | metrics 不进 VM；白名单收紧；data_edge_ids 不进 Renderer（§12） | R-S3-8 |
| 15 | 覆盖矩阵 §13 | 更新 U/S0/S1/S2 映射（§13） | 本轮 |
| 16 | 缺 level_label/布局 semantic 说明 | 新增 §4/§8/§12 | R-S3-6/5 |

---

## 15. 仍存争议 / 待 Lead·SE 裁决

1. **簇 label 后缀的本地化形式**：「等 N 个」在其他语言/标点/顺序下的最终字符串需 i18n 定义；fallback cluster_key 8 字符是否足够可读需 S3 修订。
2. **S4 的裁剪预算与 S8 硬上限关系**：S4 应保证 VM ≤ max_nodes/max_edges，否则 Renderer 拒绝；两者数值需同一 S8 配置（S3 只冻结失败语义）。
3. **KP 固定 8px 是否过小**：大屏/触控/3D 下可读性需 S3 视觉评审；可调但必须固定（不按 degree）。
4. **无簇 UX 的布局分组**：文档结构在 `layout_group` 里的粒度（文件/章节）由 S4/S6a 定；banner 文案/按钮强度需产品确认。
5. **3D 的 KP 固定大小**：3D 投影下固定 screen-space 还是 world-space 需 S3/SE 定；本提案要求同 token/固定（不按 degree）。

---

## 16. 证据锚

```text
裁决：S3-RULINGS.md:10-16（复核）、:17-49（R-S3-1..8）、:51-63（修订轮/门禁）
原话：vision.md:23-24（U-6/U-7）、:32-34（U-15/U-16/U-17）、:36-37（U-19/U-20）、:65-66（U-26/U-27）、:72（U-33）
S0：S0-terms-v1.md:21-26（语义）、:56-61（present/R-3）、:75-79（VM 纯度/kind）、:69-73（默认/full）
S1：S1-dimensions-v1.md:13-15（H/A）、:99-107（present/VM/事件）
S2：S2-clustering-v1.md:12（无簇）、:17（簇/单点/root）、:31-35,47-51（local_seq/身份）、:69-76（VM/无簇）
工程：ENGINEERING-PLAN.md:224-250（VM 字段）、:287（事件）、:291（capabilities）、:713-719（渲染/导航分离）
代码（现状/反例）：graph-view-2d.js:7-12,14-25,167-181,211,544-547,617,634-663,686-717；
  graph-view-3d.js:249-262,347,1043,1049；graph-engine.js:167-181,232-238,261,270-327；app.js:1661-1677
```
