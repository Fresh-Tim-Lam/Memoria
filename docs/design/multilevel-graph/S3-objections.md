# S3 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`），不得违反；`S3-charter.md`。
> **对象**：`S3-visual-proposal-A.md`（主办研究，sha **`7997a893cb6921ce538ba01214dcfe818fda91faf1dc49ee1c2d32584d21c806`**，31,861 B）与 `S3-visual-proposal-B.md`（本复核方，sha **`0abc2f2b1cd7b6a5818e442ec15f5af518ae6d27ea18a8fd78e004cfe068ba95`**，21,011 B）。
> **独立性**：B 于 20:13:40 落盘，A 于 20:16:21 落盘；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0/S1/S2 冻结。

---

## 0. A/B 差异总表（S3-1..S3-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S3-1 节点类型 | kind {kp,cluster}；role 含 bridge/member/one_hop/focus；交互态不进 VM；提供 token 表 | 同 kind 约束；bridge 仅 role/state；交互状态不改 kind；无 token 表 | 核心一致；**A 更细**（role/交互/token 表）；A 的 `Renderer.setSelection` 在 S3-6 接口未定义（P2-1）。 |
| S3-2 簇视觉 | 对数大小 `8+2.2*log2(count+1)` clamp 12–28；badge=member_count；label 取 VM label，fallback "簇 N"(local_seq)；root_exempt 特殊 | 大小仅要求单调 f(count)+cap，未给公式；label 要求确定性规则（min canonical member name）；计数真实；root 特殊 | **A 更强（具体公式/token）**；B 更强调 label 确定性；**A 的 label/fallback 未定义确定性来源（P1-1）**。 |
| S3-3 KP 视觉 | label/range_ok/点击提示；**可选 metrics.degree → 半径 6–10px**（现有连续映射） | label/range/点击提示；未使用 degree 大小 | A 保留度数大小（现有），B 不引入；差异不影响核心；**度数作为 KP 大小需说明是结构度量非语义（P2-2）**。 |
| S3-4 层次感知 | 层次 chrome 归 Presentation/S5；渲染器可画 VM.level_id 轻标；跨层保持视口/相机 | 层次 chrome 全归 Presentation/S5；渲染器只绘制 VM，不画面包屑/层切换 | A 允许渲染器画层标（只读），B 更严格；**需裁“层标是否属于渲染器”**（P2-3）；两者都不含 VM 历史/导航。 |
| S3-5 边视觉 | 只画 presence=shown；suppressed/unknown 不画幽灵边；类型 token 表；bridge_only 仅 state | 同（只 shown；unknown 不画假边；类型 token；bridge state） | 一致；A 的 token 表更具体；B 更强调 unknown 需 aria/计数。 |
| S3-6 渲染接口 | `render(container,vm)/update/dispose/on`；getCapabilities 独立；R1–R6；VM 白名单 | `mount(root,vm)/update/dispose/on`；getCapabilities；VM 白名单；2D/3D 同签名 | 基本一致；**方法名不同（render vs mount）**、A 多 R1–R6 细节；需统一方法名/签名（P2-4）；A 的 `setSelection` 不一致（P2-1）。 |
| S3-7 事件 | nodeClick{node_id,kind}/edgeClick/backgroundClick + 可选 hover/focus；无导航字段 | 同；最小集；无导航字段 | 一致。 |
| S3-8 无簇 UX | KP+仅布局结构分组+空状态 banner+显式“让 agent 建立语义”入口；layout_group 字段 | KP+结构布局+提示/affordance；无明确 layout_group 字段；不自动写 | A 更细（文案/affordance/字段）；**layout_group 未在 S0/S1/S2 冻结字段中，需 S6a/VM 白名单确认（P2-5）**；A 的 agent 入口需明确仅用户动作/不自动（P2-6）。 |
| S3-9 默认/全展开 | 同 DataSource/VM/Renderer；full 徽标/兼容模式；不升级类型 | 同；无第二数据源；token 一致 | 一致；A 更细（徽标/动画）。 |
| S3-10 可访问性 | 对比度/键盘/aria overlay/reduced motion；3D 不豁免 | 同；更简 | 一致；A 更细（aria token/overlay）。 |
| S3-11 性能预算 | max_nodes=200/max_edges=400/60fps/180ms/布局稳定；超预算 Renderer 拒绝或 S4 先裁剪；3D 失败回退 2D | 预算字段/降级/布局稳定；数值 S8；不静默丢 | 一致；**A 的“Renderer 拒绝 vs S4 裁剪”所有权未定（P1-2）**；B 也未明确谁裁剪。 |
| S3-12 一致性 | VM 白名单（含 metrics/layout_group）；禁 run/dendrogram/data_edge_ids；渲染器只读 | VM 白名单；禁 run/mode/nav；渲染器只读 | 一致；A 字段更细，但 layout_group/metrics 需 S6a 确认；B 更保守。 |

**总判断**：A 在 token 表、公式、a11y、无簇 UX、接口细节上明显更强；B 在 label 确定性、VM 白名单保守、组件边界上更严谨。**A 可作为并集主干，但 P1-1/P1-2 需修**；B 需吸收 A 的 token/公式/UX 细节。

---

## 1. 异议（按严重度；P0=违反 S0/S1/S2；P1=冻结前必须裁；P2=可冻结但后续场次补）

### P1-1（A）簇节点 label/fallback 没有确定性契约，`local_seq` 不是稳定显示名

- **议项**：S3-2（+S3-12）。
- **异议**：A 规定 `display_label = VM.nodes[i].label`（"由取景层按 locale 生成"），缺省回退 `"簇 " + local_seq`；但 S2 冻结的 `local_seq` 是 **run 内按 min(member id) 排的实例序号**，不是语义名称：同一成员簇在其他簇增删时 local_seq 可变，fallback 显示名会漂移；且 A 未定义取景层生成 label 的**确定性规则**（成员统计/中心 KP/最短名等），两个实现可给同一簇不同名字。S3 预注册判据 1 要求视觉编码可机检；label 是视觉编码的一部分，当前只校验"非空/fallback"，不可机检。
- **反例**：run1 中簇 C（成员 a,b）local_seq=3，因新增簇 X 在 run2 变 local_seq=4 ⇒ 回退名"簇 3"→"簇 4"，同一语义簇视觉名漂移；两个实现分别取"最短成员名"与"min id 成员名"⇒ 同 VM 不同显示。
- **修复**：S3 冻结 cluster label 生成规则之一（推荐 **min canonical member id 的 KP label + "等 N 个"**，或 S2/S4 输出 `label_seed` 字段并在 S6a 固定）；fallback 用 `cluster_key` 短前缀/稳定 id，不用 local_seq；机检 `label == deterministic_label(members)` 且同成员跨 run 稳定；locale 只影响 UI 文案（"等 N 个"），不影响显示名来源。
- **严重度**：视觉可机检/稳定身份 ⇒ **P1（冻结前）**。

### P1-2（A/B）性能预算的裁剪归属未定：Renderer 拒绝 vs S4 先裁剪

- **议项**：S3-11（S4 接口）。
- **异议**：A 写"Renderer 拒绝渲染（RENDER_BUDGET_EXCEEDED）或 S4 先裁剪；S3 不允许静默画前 N"；B 只写显式降级，未定谁裁剪。渲染器与 S4 都可"处理"超预算会产生两种实现：S4 裁剪 vs S4 不裁、Renderer 拒绝；前者视图部分可显示，后者空白/错误；同时 S3 的 `max_nodes/max_edges` 与 S4 预算字段可能两套。S3 章程要求预算可机检；需要单一责任。
- **反例**：默认视图超 max_nodes：实现 X 由 S4 裁剪显示 200 节点；实现 Y 直接拒绝渲染报错；同 VM 两种用户体验；或两者都裁剪但阈值不同；S4 裁掉的节点 presence/rule_id 未记录（静默丢）。
- **修复**：S3 冻结"**S4 负责选点/预算裁剪（带 presence=suppressed+rule_id），S3/Renderer 只校验并渲染已选 VM；Renderer 不自行裁剪、不静默丢**"；超预算时 S4 输出显式降级/通知；S3 只保留"无效 VM fail-visible"。若保留 Renderer 拒绝，也必须只作为最后防线并显式错误，不得部分渲染。`max_nodes/max_edges` 字段与 S4 预算统一（S8 定值）。
- **严重度**：与 S4 接口/预算可机检 ⇒ **P1（冻结前）**。

### P1-3（A）`node.role=bridge` 与 S2 R-S2-7「桥只作边状态/成员统计」的边界需裁决

- **议项**：S3-1/S3-5（S0-9/S2 R-S2-7）。
- **异议**：A 的 S3-1 允许 `node.role ∈ {member, one_hop, bridge, focus}`，并用虚线外环/线框外壳渲染 bridge 节点；S2 R-S2-7 冻结"桥只作为**边状态**（bridge/bridge_only）与成员统计，不改变节点 kind"；S0-9 又允许 bridge 作 node role。两处冻结文字存在解释空间：允许但仅 role/state 视觉叠加，还是只允许 edge state？任务明确要求审"节点类型是否被扩成第三类"——A 未改 kind，但把 bridge 作为节点 role 广泛使用，可能与 S2 的"只作边状态/统计"冲突。
- **反例**：所有跨族一跳端点都标 role=bridge，视觉上形成"第三类节点外观"（虚线外环）；S2 的成员统计只记录桥边，未定义节点 role；S3 若把 bridge role 作为强语义分类，会与 S2 的"桥=边状态"边界不一致。
- **修复**：Lead/SE 裁：① 若允许 node role=bridge（S0-9），S3 在 S3-1 明确"role 不是 kind、不得产生第三种节点形状/点击语义"，且 bridge role 只由 S1/S2 输出；或 ② 禁 node role=bridge，仅边 state=bridge_only + 节点徽标/计数（更贴 S2 R-S2-7）。无论哪种，机检断言 role 与 kind 不混、点击语义仍按 kind。
- **严重度**：与 S2 冻结文字边界 ⇒ **P1（冻结前裁决）**。

### P2 清单

| # | 项 | 异议/证据 | 修复 |
|---|---|---|---|
| P2-1 | A 的 `Renderer.setSelection` 只出现在 S3-1，S3-6 接口无此方法 | 接口不一致；实现两套 | 删 setSelection 或加入接口并定义幂等/清除；selected 仍不进 VM |
| P2-2 | A 的 KP radius = `metrics.degree`（6–10px），簇 radius=member_count（12–28） | 两种不同变量；degree 随显示边集/维度切换变化，可能造成 KP 大小漂移；U-6 只需簇外观更大 | 标注 degree 是**结构连接度**（非语义重要性），只在同 kind 内比较；或固定 KP 半径，用 3D 形状区分 |
| P2-3 | A 允许渲染器画 VM.level_id 轻标；B 认为层次 chrome 全归 Presentation | 静态层标是否属渲染器需统一；不得变成导航状态 | Lead/SE 选：Renderer 只画 VM 提供标签（A）或全部 Presentation（B）；二者不得两套 |
| P2-4 | A 接口 `render(container,vm)` vs B `mount(root,vm)` | 方法名不同 | 统一为 `mount/update/dispose/on`（或 render），2D/3D 同签名；方法名冻结 |
| P2-5 | A 的 VM `layout_group`（仅布局结构分组）未在 S0/S1/S2 白名单 | 可能被实现为第二数据/类簇字段；S3-8 又要求"仅布局" | S6a 明确 layout_group 是 presentation-only 布局提示，不参与 kind/presence/簇；机检不得产生 cluster 视觉 token |
| P2-6 | A 的 "让 agent 建立语义关联" 入口 | 可能被读成 S3 触发 agent 写/自动动作；S0-10/S1-14 只允许请求确定性服务 | 明确：仅用户显式动作、路由到 S10，不自动调用/不写数据；按钮 disabled 当无权限 |
| P2-7 | A 的 cluster label fallback 用 local_seq | 同 P1-1；应改稳定种子 | 见 P1-1 |
| P2-8 | A 的 S3-8 结构分组可产生成员计数/展开 | 可能视觉像簇；A 已要求文案"仅布局"，但需 class/token 断言 | S3-8 机检增加：结构分组 DOM 无 cluster class/token、无 member_count/expand affordance |
| P2-9 | A 的 3D 视觉一致性要求（member_count 缩放）与现有 3D 等大视觉 | 现有 3D D-KGV-04 等大；S3 要求同变量编码 | S3 冻结同 VM 同变量；3D 视觉差异只走 capabilities（A 可接受） |
| P2-10 | A 的“层次指示渲染器轻标”与 S0 D-4 VM 白名单 | VM 允许 level_id；静态标签不属导航状态 | 明确 level_id 只读标签，不携带历史/切换 |

---

## 2. 点名审查项结论（S3 任务）

1. **节点类型是否偷偷扩成第三类/单点簇当作代表节点**：A **PASS**（kind 仅 {kp,cluster}；singleton representative=false→kp；bridge 仅 role/state；S3-1 机检）。B 同。**但 A 的 bridge node role 与 S2 边界需裁（P1-3）**。
2. **簇大小/计数映射是否可机检/伪造数据**：A 有公式 `clamp(8+2.2*log2(count+1),12,28)`、badge=member_count、label/fallback；**PASS**（可机检）；**label 确定性 P1-1**；KP degree 大小需说明（P2-2）。
3. **边视觉是否暗示不存在边/presence 三值区分**：A **PASS**（只画 shown；suppressed/unknown 不画幽灵边；aria/统计解释；类型 token 表）。
4. **渲染接口是否真纯/2D/3D 同签名**：A **PASS**（VM 白名单、getCapabilities 独立、R1–R6、2D/3D 同签名）；**方法名 render vs mount P2-4、setSelection P2-1**。
5. **事件集最小/导航是否混入**：A **PASS**（nodeClick/edgeClick/backgroundClick + 可选 hover/focus；禁 mode/nav/history；导航归 S5）。
6. **`no_semantic_edges` UX 是否伪造语义簇**：A **PASS**（KP+仅布局结构分组+空状态+显式 agent 入口；不自动写）；**layout_group/agent 入口需 P2-5/P2-6 明确**；不得用结构边凑簇。
7. **默认/全展开是否第二数据源**：A **PASS**（同 DataSource/VM/Renderer；full 徽标；不升级类型）。
8. **可访问性/性能预算是否可机检**：A **PASS**（对比度/键盘/aria/reduced motion；预算字段/降级/布局稳定）；**预算裁剪归属 P1-2**。
9. **与 S1/S2 的 VM 纯度/簇状态不进 VM**：A **PASS**（VM 无 run/dendrogram/mode/nav；data_edge_ids 不传渲染器；白名单）；**layout_group/metrics 需 S6a 确认（P2-5）**。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1 cluster label/fallback 无确定性契约**：A 的 label 由取景层生成、fallback 用 `local_seq`；local_seq 非语义稳定名，跨 run 会漂移；S3 预注册要求视觉可机检。须冻结确定性 label 规则（min member canonical id + "等 N 个"或 S2/S4 的 label_seed）与稳定 fallback，机检 `label==deterministic_label(members)`。
2. **P1-2 性能预算裁剪归属未定**：A 写"Renderer 拒绝或 S4 先裁剪"，B 未定；同 VM 可有两种行为（S4 裁剪 vs 渲染器拒绝），S3/S4 预算可能两套。须冻结"S4 负责选点/裁剪（presence=suppressed+rule_id），Renderer 只校验+渲染已选 VM，不自行裁剪/不静默丢"。
3. **P1-3 `node.role=bridge` 与 S2 R-S2-7「桥只作边状态/统计」边界**：A 广泛用 node role=bridge 视觉；S2 冻结桥只作边状态/成员统计。须 Lead/SE 裁：允许 role（S0-9）但非 kind/非第三形状，或仅 edge state；无论哪种，机检 role 与 kind 不混、点击语义按 kind。

> P2：setSelection 未定义、KP degree 大小、level 标归属、render/mount 命名、layout_group 白名单、agent 入口、结构分组 token、3D 视觉、VM 白名单——可后续/SE 统一。

---

## 4. 结论

- **A 无 P0**：节点类型、单点簇、边 presence、渲染接口纯度、事件集、无簇 UX、默认/全展开、VM 纯度**均通过点名审查**；A 的 token 表/公式/a11y/无簇 UX 明显强于 B。
- **A 冻结前需修 P1-1/P1-2 并裁 P1-3**；P2 可 SE/后续场次；B 需吸收 A 的 token/公式/UX 细节，保留 label 确定性/VM 白名单的严格性。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S0-9/D-4 `S0-terms-v1.md:75-79`；S1 D-4 `S1-dimensions-v1.md:99-107`；S2 R-S2-6/7/12 `S2-clustering-v1.md:17,69-76`；A S3-2/S3-6/S3-11；B S3-2/S3-6/S3-11；代码 `graph-view-2d.js:544-547,651-662`、`graph-view-3d.js:1043`、`graph-engine.js:261`。
