# S3 提案 A：节点视觉与渲染接口（2D/3D 统一契约 + 无语义簇默认视图）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-305｜**日期**：2026-11-03（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结（不得违反）**：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）。
> **本场章程**：`docs/design/multilevel-graph/S3-charter.md`（S3-1..S3-12）。
> **工程输入**：`ENGINEERING-PLAN.md`（ViewModel/Renderer/事件/状态图）、`S1-engineering-check.md`、`S2-engineering-check.md`。
> **独立性**：未阅读 S3 复核方草稿（S3-visual-proposal-B / S3-objections）；本提案独立撰写。
> **纪律**：只写设计；不改产品代码/契约/用户库；未 commit。

---

## 0. 总口径

```
单一数据源 DataSource → 确定性取景服务 → ViewModel（纯）→ Renderer（2D/3D 同一签名）
视觉 = 对 VM 字段的**确定性映射**（字段→token），不是渲染器里的语义/聚类/取数逻辑。
节点只有 kind∈{kp,cluster}；bridge 只能是 role/边状态；singleton 不作代表节点。
边只在 presence=shown 时可见；suppressed/unknown 不得画成"幽灵边"（U-27）。
无语义簇是合法状态：显示 KP + 结构布局 + 空状态说明，不伪造语义簇（S2-12）。
```

**冻结不变量（来自 S0/S1/S2）**：
- ViewModel 不含导航/模式/capabilities（D-4）；`dimension_id` 只作标签；只渲染 `presence=shown` 的边（S0-6/S1-12）。
- H 派生边由 S1 R-S1-11 生成；`data_edge_ids` 可审计但渲染器不得读取内部。
- 簇只由 semantic 边支撑；无簇状态合法（S2-1/S2-12）；单点 `representative=false`（S2-6）。
- 2D/3D 是同一渲染契约的两个后端（U-33）。

**证据等级**：A（原话/冻结契约/决策/可复跑代码）；B（单源实测产物）；C（单源推理）；**本项目假设**（token 数值/预算阈值/空状态文案等显式约定）。

---

## 1. S3-1 节点类型与视觉语义（只两类；状态表达）

**定义/规则（一句话）**：图上节点只有两种 `kind`：`kp` 与 `cluster`；**不得新增第三节点类型**；singleton 以 `kind=kp` 呈现（不是 cluster 节点）；`bridge` 只能作为 node `role` 或 edge `state`；hover/active/selected 是渲染器/Presentation 的瞬态状态，不进入 VM。

**形式化**：
```
VM.nodes[i].kind ∈ {kp, cluster}           # 唯一节点类型枚举
cluster 节点：representative=true（S2）；member_count≥2
单点块：kind=kp（representative 不适用/visual 不画 cluster 外观），不得出现 cluster 节点只有 1 成员
bridge：node.role=bridge（跨族/一跳端点）或 edge.state=bridge_only；绝不出现在 kind
node.role ∈ {member, one_hop, bridge, focus}（S0/S1；视觉可区分，数据语义）
交互态：
  hover    = 渲染器本地瞬态（不写 VM；不要求事件）
  focus    = VM.role=focus（导航焦点；S5 产生）
  selected = Presentation 本地选择态（可选通过 Renderer.setSelection 传入，不进 VM）
```
**视觉区分（2D/3D 同一变量）**：
| VM 字段 | 值 | 2D token | 3D token |
|---|---|---|---|
| `kind` | `kp` | 圆形；`--node-kp` | 球体；`--node-kp` |
| `kind` | `cluster` | 圆角方；`--node-cluster` | 多面体；`--node-cluster` |
| `role` | `bridge` | 虚线外环 | 线框外壳 |
| `role` | `focus` | 高亮描边 | 高亮自发光 |
| 单点 | `kind=kp` | 普通 KP（无 cluster 徽标） | 普通 KP |

**反例**：新增 `kind=bridge`/`kind=group`/`kind=document`；把单点簇画成 cluster 节点；把 hover 写进 VM；用 node 形状区分边类型（越层）。
**边界**：bridge 的 cluster 节点（kind=cluster + role=bridge）允许；selected 在 update 后丢失可接受（非持久）；cluster 节点无子（degenerate_refinement）仍可点击（S5 决定是否可展开）。
**机检条件**：
```
- node.kind 枚举 == {kp,cluster}；无第三值（schema/静态断言）
- singleton 块无 kind=cluster 节点（S2 representative=false）
- node.role 枚举不含 kind 值；bridge 不出现在 kind
- VM 无 hover/selected 字段（瞬态不在 VM）
```
**U 映射**：U-6、U-19（点击）、U-33。
**建议裁决**：采纳两类 kind + role/state 表达 bridge + 交互态不进 VM；禁止第三类型。
**证据等级**：A（S0-9 kind 约束；S2-6 singleton；U-6/U-19）；**本项目假设**（selected 的 Presentation 表达方式）。

---

## 2. S3-2 簇节点视觉编码（大小/徽标/名称/root_exempt）

**定义/规则（一句话）**：簇节点的大小映射 `member_count`（对数压缩、上下限）；徽标显示聚合计数与可展开提示；显示名取 VM `label`（由取景层生成，可本地化），缺省回退"簇 N"；`root_exempt` 用显式特殊外观且不宣称语义簇。

**形式化（大小映射，可复算）**：
```
r_cluster = clamp(8 + 2.2 * log2(member_count + 1), 12, 28)   # px @ zoom=1
member_count = VM.nodes[i].metrics.member_count（必填，≥2）
无 metrics 或 <2 ⇒ RENDER_VM_INVALID（fail-closed；渲染器不得猜）
```
**徽标/提示**：
```
badge_count = member_count（文字 "N" 或 "+N"，由 Presentation 决定显示格式；数字来自 VM）
expand_hint = VM.nodes[i].expandable === true ⇒ chevron/⊕ 图标
root_exempt = VM.nodes[i].root_exempt === true ⇒ 虚线外圈 + "全库" 标签（不显示为普通语义簇）
singleton: 无 cluster 徽标/计数（S3-1）
```
**显示名/多语言**：
```
display_label = VM.nodes[i].label（非空字符串；由取景层按 locale 生成）
fallback = "簇 " + local_seq / "Cluster " + local_seq（仅 label 缺失时；渲染器不做统计/中心 KP 选择）
i18n：VM 可带 label_key（可选）；locale 切换由 Presentation 重新取景/更新 VM，渲染器不自行翻译
```
**反例**：大小直接线性映射 10k 成员（巨大节点）；用中心 KP 名字当簇名（需要额外数据/语义判断）；渲染器自行统计成员名；root_exempt 画成普通簇；簇无 member_count 仍渲染。
**边界**：member_count=2 ⇒ r=11.5（clamp 到 12）；1000 ⇒ 28 上限；member_count 缺失 ⇒ fail-closed；root_exempt 只 L0（S2）；单点不算簇。
**机检条件**：
```
- 每个 cluster node 有 metrics.member_count≥2；radius 由公式计算（字段→token 断言）
- root_exempt 只出现在 L0 且有特殊 token（class/data-attr）
- label 非空或走 fallback；渲染器无成员统计代码（静态检查）
- 徽标数字 == member_count（DOM/aria 断言）
```
**U 映射**：U-6（外观更大）、U-3（避免海量小点）、U-7。
**建议裁决**：采纳对数大小 + 上下限 + 徽标/展开提示 + VM label/fallback + root_exempt 特殊外观。
**证据等级**：A（U-6；S2-1/S2-6）；**本项目假设**（2.2/12/28 的 token 数值、fallback 文案）。

---

## 3. S3-3 KP 节点视觉与编辑器跳转提示（U-20）

**定义/规则（一句话）**：KP 节点显示 VM `label`（短标签）+ 可选描述/标签徽标；`range_ok=false` 用失效样式；hover/focus 显示"可打开编辑器"提示；点击 KP 的事件由 S5 映射到 `jumpToTarget`（U-20），渲染器不直接跳转。

**形式化**：
```
KP 视觉：shape=circle/sphere；label=VM.nodes[i].label（截断规则由 label 模块统一，S3 只要求可预测）
可选：metrics.degree → 半径（现有连续分位映射，6–10px）；不再用 kind 之外变量
optional badges：label 徽标（semantic/structural/navigation 不在节点上重复；边类型在边上）
range_ok=false：虚线/去饱和 + aria "锚点失效"
可点击提示：hover/focus 时 cursor pointer + 高亮环 + 文案（"打开知识点"）；点击只发 nodeClick
```
**反例**：渲染器点击后直接 `jumpToTarget`（渲染器做导航）；用节点颜色编码边类型；用描述全文当标签；range 无效仍正常样式。
**边界**：单点块与普通 KP 视觉一致（无簇徽标）；KP 同时 role=bridge 时加桥环但仍是 kp；极短/极长 label 由 label 模块处理；3D 标签可隐藏（a11y 由 DOM 覆盖）。
**机检条件**：
```
- kp 节点无 member_count 徽标；range_ok=false 有失效 token
- 渲染器无 jumpToTarget/导航调用（静态检查）
- nodeClick payload 只有 node_id/kind（S3-7）
```
**U 映射**：U-20、U-19、U-3。
**建议裁决**：采纳 KP 视觉 + 点击提示 + 渲染器不导航；点击由 S5 处理。
**证据等级**：A（U-20；现有 `app.js:1661-1677` jumpToTarget；`graph-view-2d.js:544-547` nodeClick）；**本项目假设**（提示文案/标签截断留给标签模块）。

---

## 4. S3-4 层次感知（当前层/深度/跨层连续性）

**定义/规则（一句话）**：层次指示（当前层/深度/面包屑/层级条）属于 **Presentation（S5）**，不在 ViewModel；渲染器可读 VM `level_id` 画轻量层标；跨层连续性由 S5 保留导航栈与视口、S3 定义过渡动画与焦点保持。

**形式化**：
```
VM 含 level_id/view_family_id（渲染标签；不含层级列表/面包屑/历史）
Presentation（S5）：
  breadcrumb/level-bar = f(GRAPH_NAV_FRAME.history, VIEW_FRAME.level_id)（不在 VM）
  level indicator text = registry/level label + "Lℓ"
  cross-level：进入子簇→新 VM（新 level）；保留同一 view_family 的视口/相机（可配置 fit）
Renderer：
  只在画布角落绘制 level_id 轻标（可选，来自 VM）；不画面包屑、不处理返回/层级切换
  过渡：node id 保留者位置尽量保持；新节点淡入；reduced motion=无动画
```
**反例**：VM 携带 breadcrumb/history；渲染器实现"返回上一层"；跨层重新 fit 导致跳动且无记录；用节点颜色表示深度。
**边界**：L0 root_exempt 整库块；叶层全 KP；跨 view_family（多归属）时 S5 处理来源；布局种子固定（现有 D-KGV-07）保证可复现。
**机检条件**：
```
- VM 无 breadcrumb/history/level list；渲染器无导航动作
- level 指示来自 VM.level_id 或 Presentation；二者不同时存在两套真相
- 跨层 VM 更新：common node ids 的位置/相机保持（可测 position delta）
```
**U 映射**：U-5、U-7、U-8、U-19。
**建议裁决**：采纳层次指示归 Presentation、渲染器只读 level_id；跨层保持视口/焦点；S5 定导航细节。
**证据等级**：A（S0-9/D-4；S1-13；`ENGINEERING-PLAN.md:713-719` 状态图立场）；**本项目假设**（层标样式/过渡时长）。

---

## 5. S3-5 边视觉与「存无/类型」（U-27；不得幽灵边）

**定义/规则（一句话）**：边视觉由 VM 的 `type + contain_kind + label + display_type + presence + state` 决定；**只有 `presence=shown` 的边可绘制**；suppressed/unknown 不画线，只在统计/检查器/aria 中解释；bridge 用独立线型而非改类型。

**形式化（字段→token）**：
```
presence:
  shown     ⇒ 正常绘制（唯一可见条件）
  suppressed⇒ 不绘制；进入 "已隐藏 N 条（rule_id）" 统计/检查器
  unknown   ⇒ 不绘制；aria/检查器标 "未计算/数据未加载"；不得画虚线幽灵
type/contain_kind（display_type 由 VM 给定，渲染器不改写）:
  contain(structural) ⇒ 实线 1.0px 中性灰 --edge-structural，箭头→child
  contain(semantic)   ⇒ 实线 2.0px 强调蓝 --edge-semantic，箭头
  reference           ⇒ 虚线 [4,3] 1.0px 弱灰 --edge-reference，箭头
  extend              ⇒ 实线 1.5px 暖黄 --edge-extend，箭头
state=bridge_only ⇒ 在类型线型上叠加点线/透明度（不改变 type/颜色语义），并 aria "跨簇桥"
label: 边类型图例（semantic/structural/navigation）来自 VM.label；不逐边写文字
data_edge_ids: 不传给渲染器；聚合计数用 aggregate_count（VM 可选）显示为边徽标
```
**反例**：把 suppressed 边画成半透明（暗示存在）；unknown 画虚线；用颜色改写 type；bridge 边改成新类型；同一对节点多条边合并成一条复合边；`data_edge_ids` 逐条渲染。
**边界**：同对多类型边分别绘制（可重叠/偏移）；reference 与 extend 同对；bridge_only 的 contain 边；unknown 数据加载失败；full_expand 下仍只画 shown。
**机检条件**：
```
- 绘制集合 == {edge | presence==shown}（renderer 注入假 VM 的绘制计数断言）
- presence!=shown 的边没有图形/DOM 节点；aria 可列出 rule_id
- edge.type/contain_kind 映射到固定 token 表；渲染器无 label/type 推断
- bridge_only 使用 state token，不产生第三种 edge type
```
**U 映射**：U-15、U-16、U-17、U-27。
**建议裁决**：采纳唯一 shown 判据 + 类型/状态 token 表 + 不画幽灵边；bridge 仅 state；多类型边分画。
**证据等级**：A（S0-6/S1-12/U-27；现有 `graph-engine.js:261` edgeColor 按 type；`graph-view-2d.js:651-662` 全量 links 绘制）；**本项目假设**（颜色/线宽 token）。

---

## 6. S3-6 渲染接口契约（2D/3D 同一签名）

**定义/规则（一句话）**：Renderer = 纯 ViewModel 输入 + `getCapabilities()` + `render/update/dispose` + 事件回传；2D/3D 同签名；渲染器不取数、不做语义/聚类判断、不写导航/全局状态。

**形式化（契约）**：
```ts
interface Renderer {
  getCapabilities(): {
    backend: "2d" | "3d";
    supportsAnimation: boolean;
    supportsKeyboard: boolean;
    supportsAria: boolean;
    supportsSelection: boolean;
    maxNodes: number; maxEdges: number;      // 与 S3-11 预算一致
  };
  render(container: HTMLElement, vm: ViewModel): void;  // 首次挂载
  update(vm: ViewModel, opts?: { transition?: "none" | "fade"; preserveCamera?: boolean }): void;
  dispose(): void;                                       // 幂等释放资源/监听
  on(event: "nodeClick" | "edgeClick" | "backgroundClick" | "hover" | "focus",
     handler: (payload: object) => void): () => void;    // 返回取消订阅
}
// ViewModel 纯度：无 mode/nav/breadcrumb/capabilities/cluster run/dendrogram；
// 只含 view_model_id, level_id, dimension_id, view_family_id, nodes[], edges[]（+展示所需 metrics）。
```
**规则**：
```
R1 2D/3D 方法名/参数/返回一致；同 VM 的 node/edge id 集合一致（U-33）
R2 渲染器不得调用 get_graph_data/collect/sidecar/网络；只吃 VM
R3 渲染器不得重算 μ/β/cluster/level/admission；不修改 VM
R4 capabilities 独立方法，不塞进 VM（S0-9 C-6）
R5 无效 VM（schema/kind/presence 非法）⇒ fail-visible（抛错/降级，不部分渲染）
R6 update 同一 VM 幂等；dispose 后调用 = no-op 或明确错误
```
**反例**：2D 以 `loadPayload(engine)` 吃 engine、3D 在自身类内直接持有 engine/layout 并 `_render()`，两者无共同 `render(vm)` 签名（现状）；渲染器内部 fetch；把 `getCapabilities` 塞进 VM；渲染器写导航状态；2D/3D 节点 id 集不同。
**边界**：仅 2D 后端可用（3D WebGL 失败）⇒ capabilities 指明，S5 切换；VM 空 nodes；重复 render 同容器；update 期间切换 backend（由 S5 先 capture）。
**机检条件**：
```
- 2D/3D 原型方法名/arity 一致；同一 fixture VM 的 id 集相等
- 渲染器源码 import 白名单无数据层/网络；无 get_graph_data/fetch/sidecar
- VM schema 拒绝 nav/mode/capabilities 字段（S6a schema）
- getCapabilities 与预算字段存在且为有限数
```
**U 映射**：U-33、U-16、U-32、U-34。
**建议裁决**：采纳上述接口；2D/3D 同签名；渲染器纯渲染；capabilities 独立。
**证据等级**：A（S0-9/D-4/U-33；`ENGINEERING-PLAN.md:224-250,291`；现状 2D `destroy`/3D 各自 API、无 `getCapabilities`）；**本项目假设**（`on`/opts 的具体签名）。

---

## 7. S3-7 事件契约（最小集；导航不在渲染器）

**定义/规则（一句话）**：渲染器只发最小交互事件 `nodeClick/edgeClick/backgroundClick`（可选 `hover/focus`）；事件只携带 view 标识，不含导航/模式/历史；导航动作由 S5 消费事件后执行。

**形式化**：
```
必需事件：
  nodeClick   { node_id, kind }        # kind ∈ {kp,cluster}
  edgeClick   { edge_id }
  backgroundClick {}
可选：
  hover       { node_id|null }
  focus       { node_id|null }         # 键盘焦点；不是 selected/nav
禁止字段：mode/dimension_id/level_id/history/breadcrumb/run_id/cluster_key/navigate*
S5 映射（示例）：nodeClick(kp)→jumpToTarget（U-20）；nodeClick(cluster)→CLICK_CLUSTER（U-7）；edgeClick→可选检查器
```
**反例**：事件带 mode/level 让渲染器决定导航；渲染器内部实现返回/展开；事件携带 data_edge_ids/成员列表（泄露内部）；点击 cluster 直接 jumpToTarget（S0-9 旧 bug）。
**边界**：3D 必须与 2D 同 payload（现 3D nodeClick 无 edge_id 是历史差异，S3 统一）；重复点击去抖；点击空白发 backgroundClick；键盘 Enter/Space 等价 click。
**机检条件**：
```
- 事件 payload key 白名单；无导航字段
- 2D/3D 同一 fixture 的 nodeClick/edgeClick payload 结构相等
- 渲染器无 jumpToTarget/navigate/mode 调用（静态检查）
```
**U 映射**：U-7、U-19、U-20、U-33。
**建议裁决**：采纳最小事件集 + 统一 payload + 导航归 S5；`hover/focus` 可选，其余不扩。
**证据等级**：A（S0-9 事件集；`ENGINEERING-PLAN.md:287,714,848`；`graph-view-2d.js:544-547` vs `graph-view-3d.js:1043`）；**本项目假设**（键盘等价点击）。

---

## 8. S3-8 `no_semantic_edges` 默认视图 UX（S2-12 交办）

**定义/规则（一句话）**：当 S2 run 状态为 `no_semantic_edges`（或 representative 簇=0/coverage=0）时，默认视图必须**如实显示无簇**：显示 KP 节点 + **仅布局用**的结构分组 + 明确空状态说明 + 显式"让 agent 建立语义"入口；**不得伪造语义簇/不得用结构边凑簇**。

**状态判定（与 S2 对齐）**：
```
S2 run.status == "no_semantic_edges" 或 representative_clusters==0 && coverage==0
⇒ S3 进入 empty-semantic 视觉模式（Presentation 触发；渲染器只收"全 kp"VM）
```
**显示什么**：
```
1) 节点：显示当前层 KP 节点（不是空白）；kind=kp，无 cluster 节点/徽标/计数
2) 布局分组：可按文档/文件形成**仅布局**的分组容器/标题，文案必须为
   "文档结构（仅布局，不是语义簇）"；不得使用 cluster 视觉 token/成员计数/展开语义
   分组来源 = VM 可选字段 `layout_group`（取景层给文档/章节 id；仅布局，不是语义/簇字段；S6a 定 schema）
3) 边：只显示 S4/H 允许的 shown 边（如 H 结构边）；reference/structural 不得升级为 semantic；
   suppressed/unknown 不画（S3-5）
4) 空状态 banner（Presentation 层，非渲染器）：
   标题："尚无语义簇"
   正文："未发现 semantic 边（0 个语义簇，coverage 0%）。这是合法的空状态：
         不会用结构/引用边伪造语义簇。"
   （若 E_sem>0 但无合格簇："已发现 N 条 semantic 边，尚未形成满足 μ/β 的簇。" N 来自 S2 run/Presentation）
5) affordance（显式、非自动）：
   [让 agent 建立语义关联] → 调用 S10 流程（需用户确认；不自动写）
   [查看结构布局]（当前默认）
   [查看全展开]（S0-8 正交开关）
   [了解语义边]（帮助链接）
```
**S4 接口**：S4 的选择性渲染在 empty 模式下仍只作用在 VM 的 shown 边上；S4 **不得**注入结构/引用边来制造簇；S3 只负责展示空状态，不改变取景。
**反例**：把文档分组画成 cluster 节点/带成员计数徽标；用 structural contain 生成"簇"；空状态直接空白（用户以为坏了）；自动触发 agent 建立语义；把 reference 边标成语义边凑 coverage。
**边界**：E_sem=0 且 K 很大 ⇒ 显示 KP（可能拥挤，S4/预算处理），不伪造；E_sem>0 但 τ 未过 ⇒ 显示"有语义边但无合格簇"；用户切全展开 ⇒ 仍无簇，只是显示更多边；多语言文案由 i18n key 提供。
**机检条件**：
```
- empty 模式下 VM.nodes 无 kind=cluster；无 cluster 徽标/计数
- banner/affordance 存在（DOM 断言）；文案 key 存在（i18n）
- 结构分组容器无 cluster class/token；文案含"仅布局/不是语义簇"
- 不自动调用 agent（无自动请求）；affordance 需用户动作
- coverage=0 时不得显示"语义簇数>0"
```
**U 映射**：U-1、U-3、U-6、U-13、U-14、U-27。
**建议裁决**：采纳"KP + 仅布局结构分组 + 空状态说明 + 显式 agent 入口"；严禁伪造簇；S4 不注入结构边当簇。
**证据等级**：A（S2-12：无簇合法/不得伪造；S2-1/S2-6；U-13/U-14）；**本项目假设**（文案/affordance 形式）。

---

## 9. S3-9 默认 vs 全展开的视觉（不得第二数据源）

**定义/规则（一句话）**：默认层次视图与全展开是**同一 DataSource、同一 ViewModel schema、同一 Renderer** 的两个 Presentation 模式；视觉差异只体现在选点/边集与"全展开"标识，不引入第二数据源/第二语义模型。

**形式化**：
```
default  = H 层次视图（clusters/KP，per-level VM），按 S4 选择性渲染
full     = 同一 DataSource → 同一 ViewModel 生成器（ctx_full）→ 同一 Renderer
视觉差异：
  - 默认：层次节点（cluster/KP），边以 H 结构边 + S4 admitted 边为主
  - full：更全的 shown 边集；reference/structural 按类型 token 显示（不升级 semantic）
  - 顶部/角落徽标："全展开（兼容模式，不改变语义）"
切换：Presentation 工具栏（S5/S3 UI）；S5 保持 frame/焦点/相机（preserveCamera）
禁止：独立 full.json/独立渲染器/独立语义模型/第二套 id
```
**反例**：全展开另开渲染器/数据文件；全展开把 structural 当 semantic；默认和 full 各自缓存且漂移；切换丢失焦点且无提示。
**边界**：默认在叶层与 full 选点可接近（同一数据）；full 仍只画 shown；切换动画 180ms、reduced motion 0ms；返回默认保持导航（S5）。
**机检条件**：
```
- 两模式 DataSource 身份相同（kb_path/manifest/collect_version）
- 同一 VM schema；同一 Renderer 接口；无第二数据源/渲染器
- full 徽标存在；full 边仍 presence=shown 才画
- 切换前后 focus/level 由 S5 保持/映射（S5 测试）
```
**U 映射**：U-3、U-5、U-16、U-26、U-27。
**建议裁决**：采纳同源同接口 + 全展开徽标/兼容模式 + 类型不升级；不引入第二数据源。
**证据等级**：A（S0-8；S1-13；`ENGINEERING-PLAN.md:717`）；**本项目假设**（徽标/动画）。

---

## 10. S3-10 可访问性（对比度/键盘/aria/reduced motion）

**定义/规则（一句话）**：视觉编码必须可被无鼠标/低视力/读屏用户使用：文本对比度≥4.5:1、图形≥3:1；canvas 必须有可聚焦 DOM 覆盖层 + aria 语义；键盘可达节点/簇展开；`prefers-reduced-motion` 时禁用动画/脉冲。

**形式化**：
```
对比度：文本 token ≥4.5:1；边界/线 ≥3:1（对背景）；颜色不作唯一通道（类型用线型+图例）
键盘：Tab 进入图区域；方向键在节点间移动；Enter/Space=nodeClick；Escape=清除选择；
     焦点环 ≥2px、可见（不靠颜色）
aria（DOM overlay，来自 VM；不改变 VM/数据）：
  容器 role="application"/img + aria-label 摘要（层/维度/节点数/边数）
  节点 role="button" aria-label="知识点 X" / "簇 N，含 M 个知识点，可展开"；cluster aria-expanded
  边不逐条聚焦；检查器列表 aria 说明类型/状态/rule_id
  空状态/降级 aria-live 公告（如 "尚无语义簇"）
reduced motion：prefers-reduced-motion ⇒ 无 pulse/淡入/相机飞行动画（0ms）
```
**反例**：只用颜色区分 semantic/reference（色盲失败）；canvas 无 tabindex/aria（现状无）；动画不可关；焦点不可见；aria-label 只写 id。
**边界**：3D 无 DOM 节点 ⇒ 用 2D 同构 overlay 列表（不要求 3D 可视化可聚焦）；超大图只给摘要 + 列表（S3-11）；高对比主题 token。
**机检条件**：
```
- token 对比度计算通过（WCAG 公式，阈值文本4.5/图形3）
- 容器 tabindex=0；节点可聚焦；focus 可见；Enter/Space 触发 nodeClick（测试）
- aria-label/aria-expanded/aria-live 存在；reduced motion 下动画时长=0
- 类型编码有非颜色通道（线型/图例）断言
```
**U 映射**：U-3、U-18、U-33（+可访问性通用）。
**建议裁决**：采纳对比度/键盘/aria overlay/reduced motion；canvas 必须配 DOM overlay；3D 不豁免。
**证据等级**：A（现状无 aria/tabindex：`graph-view-2d.js`/`graph-view-3d.js` 无相关属性；`graph-engine.js:270-327` 视觉通道声明含颜色/大小）；**本项目假设**（具体对比度/键盘键位/阈值）。

---

## 11. S3-11 性能与稳定预算（显示预算/退化）

**定义/规则（一句话）**：渲染器有显式显示预算（节点/边上限、帧率目标、动画时长、drill 布局稳定）；超预算/失败必须显式降级（不静默截断/不取数），规模不是问题不等于无限渲染（U-32）。

**形式化**：
```
预算（默认值可 S8 配置；S3 冻结字段/语义）：
  max_nodes=200, max_edges=400（每 VM/每屏）
  target_fps=60（低端 30）；frame_budget_ms=16.7/33
  animation_ms=180（reduced motion=0）
  drill 布局稳定：common node ids 位置变化 ≤ 阈值（如 8% viewport）
超预算：
  Renderer 拒绝渲染（RENDER_BUDGET_EXCEEDED）或 S4 先裁剪；S3 不允许静默画前 N；
  UI 降级：显示"超过显示预算"banner + 可切换列表/全展开（列表来自 VM 只读）
失败：
  WebGL 初始化失败 ⇒ capabilities 指示 3D 不可用；S5 回退 2D（不静默）
  VM invalid ⇒ RENDER_VM_INVALID（不部分渲染）
  dispose 幂等；update 期间异常 → 保持上一帧并报错（不白屏）
```
**反例**：无限节点直接渲染（毛球）；超出后静默只画前 50；drill 后全局重新布局导致跳动；动画 1s 不可跳过；3D 失败静默黑屏。
**边界**：恰好预算；空 VM（空状态）；低端设备 30fps；drill 小图无布局变化；全展开超预算 ⇒ banner。
**机检条件**：
```
- capabilities.maxNodes/maxEdges 存在且与 S4 预算一致
- VM 超预算 ⇒ 显式状态（不画部分且不报告）
- 动画时长/帧预算可测；reduced motion=0
- drill fixture：common ids 位置 delta ≤ 阈值（或声明 fit 策略）
```
**U 映射**：U-3、U-18、U-32。
**建议裁决**：采纳显式预算/降级/布局稳定；数值 S8 可调；禁止静默截断与静默 3D 失败。
**证据等级**：A（U-32；`ENGINEERING-PLAN.md` 性能/状态图；现有布局种子 `graph-engine.js:241-250`）；**本项目假设**（具体数值/阈值）。

---

## 12. S3-12 与 S1/S2 的一致性（VM 纯度/数据派生）

**定义/规则（一句话）**：ViewModel 只含 `dimension_id + level/view_family + nodes/edges` 的视图投影；**簇/run/dendrogram/成员/候选状态不进 VM**；视觉只从 VM 字段派生；`data_edge_ids` 可审计但不暴露给渲染器（不得逐条渲染）。

**形式化**：
```
VM 允许字段（S0-9/S1 D-4 + S2-11）：
  view_model_id, level_id, dimension_id, view_family_id,
  nodes[{node_id,kind,role,label,label_key?,expandable,representative?,root_exempt?,
         layout_group?, metrics{member_count,degree},badges?}],
  edges[{edge_id,source,target,type,contain_kind,label,display_type,presence,rule_id,
         state?,hop,underlying_hop_count,aggregate_count?}]
禁止字段：cluster_run_id/cluster_key/dendrogram/run_status/candidate/params_hash/mode/nav/breadcrumb/capabilities
渲染器：
  只读 VM；不重算 μ/β/cluster/level/admission；不读 data_edge_ids（可审计侧保留，渲染器输入投影中剔除）
视觉派生：kind/role/metrics/presence/type → token；不新增语义
```
**反例**：VM 带 cluster_run_id/候选 run 状态（D-4 违反）；渲染器按 dendrogram 重画簇；渲染器读 data_edge_ids 逐条画边；VM 带 mode/nav；同一节点在不同后端 id 不同。
**边界**：VM 可带 `aggregate_count`（由取景层从 data_edge_ids 计数）；`data_edge_ids` 保留在审计副本但不给 Renderer；空状态 VM 无 cluster；多后端共享 VM。
**机检条件**：
```
- VM schema 白名单：禁止字段缺省/出现即 fail
- Renderer 无 cluster/dendrogram/run 字段读取；无 data_edge_ids 读取
- 同一 fixture VM 2D/3D node/edge id 集一致
- VM 无 mode/nav/capabilities（S0/S1）
```
**U 映射**：U-1、U-27、U-33。
**建议裁决**：采纳 VM 白名单 + 渲染器不读内部 + 视觉从字段派生；S6a 落 VM schema。
**证据等级**：A（S0-9/D-4；S1-13；S2-11；`ENGINEERING-PLAN.md:224-250`）；**本项目假设**（VM 新增 metrics 字段由 S6a 定）。

---

## 13. 覆盖矩阵

| U# | 要点 | S3 落点 |
|---|---|---|
| U-3 | 海量节点/错综连线 | S3-2/S3-11（显示预算/退化） |
| U-5 | 默认非全展开 | S3-9（默认视觉） |
| U-6 | 代表子图节点外观更大 | S3-2（member_count 大小/徽标） |
| U-15 | 深入后语义边挂接一跳 | S3-5（边类型/presence）/S1 |
| U-16 | 选择性渲染 | S3-5（只画 shown） |
| U-18 | 限制跳数理由 | S3-11（预算） |
| U-19 | 点击 KP/簇节点 | S3-1/S3-7 |
| U-20 | KP→编辑器 | S3-3/S3-7 |
| U-26 | 默认替代+全展开开关 | S3-9 |
| U-27 | 边存无/类型 | S3-5/S3-9 |
| U-33 | 2D/3D 不分家 | S3-6/S3-7 |
| S0 | VM 纯度/kind/present/R-3 | S3-1/S3-5/S3-6/S3-12 |
| S1 | H/A 视觉区分、dimension_id 标签 | S3-5/S3-12 |
| S2 | 无簇合法、singleton/root_exempt/coverage | S3-1/S3-2/S3-8 |

---

## 14. 仍存争议 / 待 Lead·SE 裁决

1. **簇大小的具体映射**：`8+2.2*log2(member_count+1)`、上下限 12–28 为建议值；SE/S8 可调（但必须保留公式+可机检）。
2. **空状态文案/affordance 强度**：是否默认展示"让 agent 建立语义"按钮（可能显得产品缺陷），还是放在"了解更多"里；本提案默认显式按钮。
3. **3D 的视觉一致性**：是否强制 3D 也按 member_count 缩放（现有 3D 等大 D-KGV-04）；本提案要求同变量编码，可能与现有 3D 视觉习惯冲突。
4. **可访问性实现位置**：canvas 的 DOM overlay 由 Renderer 提供还是 Presentation 提供；本提案说"Renderer 提供锚点/VM 派生 overlay"（capabilities.supportsAria），SE 可改。
5. **显示预算数值**：200/400/60fps 为默认，S8 可调；3D 失败回退 2D 的策略由 S5/S3 协调。

---

## 15. 证据锚（详见 `S3-evidence-A.md`）

```text
原话：vision.md:22-24（U-6/U-7）、:32（U-15）、:33（U-16）、:36-37（U-19/U-20）、:65-67（U-26/U-27）、:72（U-33）
S0：S0-terms-v1.md:21-26（语义）、:56-61（present/R-3）、:75-79（VM 纯度/kind）、:81-85（agent）
S1：S1-dimensions-v1.md:13-15（H/A）、:99-107（present/VM/事件）
S2：S2-clustering-v1.md:17（簇/单点/root）、:69-76（VM 纯度/无簇）
工程：ENGINEERING-PLAN.md:224-250（VM 字段）、:287（事件）、:291（capabilities C-6）、:713-719（渲染事件/导航分离）
代码（现状/反例）：graph-view-2d.js:7-12,617,651-662,544-547；graph-view-3d.js:249-262,1043；graph-engine.js:261,270-327；app.js:1661-1677；无 getCapabilities/aria/空状态
```
