# S4 提案 A：选择性渲染、一跳挂接与边「存无」

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-310｜**日期**：2026-11-03（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结（不得违反）**：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）。
> **本场章程**：`docs/design/multilevel-graph/S4-charter.md`（S4-1..S4-12）。
> **工程输入**：`ENGINEERING-PLAN.md`（P4/P5/P6、DFD、ST 状态图）。
> **独立性**：未阅读 S4 复核方草稿（S4-render-proposal-B / S4-objections）；本提案独立撰写。
> **纪律**：只写设计；不改产品代码/契约/用户库；未 commit。

---

## 0. 总口径与管线位置

```
DataSource（唯一事实源：collect_graph_data）
  → P4 取景检索（候选节点/边；S9）
  → P5 Admission（**S4**：唯一裁剪者，逐候选判 presence/rule_id）
  → P6 ViewModel 构建（S6/S3 schema）
  → P7 Renderer（2D/3D；只校验/渲染已选 VM，不裁剪）
```

**S4 只做三件事**：① 在预算内选节点/边；② 给每条候选边判 `presence∈{shown,suppressed,unknown}`+`rule_id`；③ 把选择结果交给 VM 构建。**S4 不改事实/类型/标签/簇**；Renderer 不做裁剪（S3 R-S3-2）。

**证据等级**：A（原话/冻结契约/决策/可复跑代码）；B（单源实测产物）；C（单源推理）；**本项目假设**（预算默认值/tie-break 细则等显式约定）。

---

## 1. S4-1 选择性渲染定义与边界（唯一裁剪者）

**定义/规则（一句话）**：选择性渲染 = 由 S4 的 Admission 函数在给定 `ctx + 预算` 下，决定哪些候选节点/边进入 ViewModel、哪些边以 `suppressed/unknown` 记录；**只有 S4 做这个决定**，且只改 `presence/选择`，不改 DataSource/边类型/标签/簇。

**形式化**：
```
Admission: (CandidateSet, ctx, budget) → ViewModel 选择结果
CandidateSet 来源：DataSource 边 + S2 簇（当前 level/view_family）+ S1 维度规则 + focus
ctx = {level_id, view_family_id, dimension_id, focus_id, hop_budget, new_hop, mode, budget}
budget = {max_nodes, max_edges}（S8 定值；与 Renderer.getCapabilities 同源）
输出：
  VM.nodes = 被选节点（≤max_nodes）
  VM.edges = 候选边（每条带 presence/rule_id；Renderer 只画 shown）
约束：
  S4 不改 DataSource；不改 type/contain_kind/label；不重算簇/μ/β；
  Renderer 不得二次裁剪/丢弃（S3 R-S3-2）；S4 输出超硬上限 ⇒ 自身错误（S4_BUDGET_INVALID）
旧行为对比：graph-engine.expandLinks 对 payload.edges 全量生成 link（graph-engine.js:179-180），
           无 presence/预算/规则；本设计以 Admission 替代"数据有边就画"（U-16）
```
**反例**：Renderer 里按节点数截断；S4 改 edge.type 让边"看起来合理"；S4 直接写 DataSource；同一 VM 由前端/后端各自裁剪（双行为）。
**边界**：候选为空（空 VM/空状态）；预算恰好；S4 与 S9 分工（S9 生成候选集，**不是 presence 裁剪**；S4 对候选集做唯一 presence/选择裁决；候选集生成须可审计/可解释）；S4 不做导航/历史。
**机检条件**：
```
- 输出 VM 的 nodes/edges 均来自 CandidateSet 子集；无新造 id
- 边 type/contain_kind/label 与 DataSource 一致（无改写）
- Renderer 输入 VM 后不再减少 shown 集合（S3 契约测试）
- 唯一裁剪者：代码/接口中只有 Admission 产生 suppressed/rule_id；Renderer 无裁剪逻辑
```
**U 映射**：U-3、U-16、U-27。
**建议裁决**：采纳 S4 唯一裁剪者 + 只改 presence/选择 + Renderer 不裁剪。
**证据等级**：A（S0-6/S3-11；U-16；`graph-engine.js:179-180` 旧全量渲染）；**本项目假设**（Admission 输入/输出细节）。

---

## 2. S4-2 预算内选点规则（确定性、可复算、显式降级）

**定义/规则（一句话）**：在 `max_nodes/max_edges` 内按**分层优先级 + 确定性 tie-break** 选节点/边；超预算的候选必须显式标记 `suppressed + rule_id`，不得静默丢弃；预算值由 S8 定、S4 与 Renderer capabilities 同源。

**形式化（节点优先级）**：
```
必选（tier 0）：focus 节点 + 当前 level/view_family 的可见块节点（H 的 Π_ℓ,f；A 的基座）
tier 1：A 一跳端点（距离=1，方向符合） / H 的直接子块
tier 2：与 tier0/1 通过 candidate 边相邻的节点，按 (label_rank, hop, canonical_id)
  label_rank: semantic=0 < structural=1 < navigation=2（只作排序，不重算语义）
tie-break（冻结）：(hop asc, label_rank asc, canonical node_id lexicographic asc)
选择：按 tier→key 排序取前 max_nodes；超出的候选节点 ⇒ suppressed（node.budget）
预算不足：若 |tier0| > max_nodes ⇒ S4_BUDGET_INVALID（fail-visible；S8 必须保证 max_nodes ≥ 最小必选集）
```
**形式化（边优先级）**：
```
候选边：两端至少一端在已选节点 + 符合维度/层次/方向/跳数
优先级：edge_tier = 0 H 派生父→子边 / 1 A 一跳边 / 2 语义 label / 3 structural / 4 reference
        tie-break: (edge_tier, hop asc, canonical edge_id asc)
取前 max_edges；超出 ⇒ presence=suppressed + rule_id=budget.edge
端点未选 ⇒ presence=suppressed + rule_id=node.budget（不画悬空边）
```
**显式降级**：
```
- 节点/边被预算排除 ⇒ suppressed+rule_id（可枚举、可统计）
- 预算不可满足（tier0>max_nodes / max_edges<必选边）⇒ S4_BUDGET_INVALID，由 UI 显示降级提示（不静默）
- 数值 max_nodes/max_edges 由 S8 配置；S4/Renderer 读取同一配置（不允许两套阈值）
```
**反例**：按遍历顺序/对象插入序选点（不确定）；超预算直接丢且不标 suppressed；S4 裁 200 而 Renderer 再裁 200（双裁剪）；预算与 Renderer 不同源。
**边界**：焦点邻域=0；候选恰好=预算；tier0 恰好填满；集群节点占预算但成员不计；重复 id 去重。
**机检条件**：
```
- 同 (CandidateSet, ctx, budget) 两次运行结果逐字节相同（确定性）
- nodes 数 ≤max_nodes；edges 数 ≤max_edges
- 所有未选候选有 presence=suppressed+rule_id（budget.*）；无静默丢弃
- tier0 必选；预算不足时 S4_BUDGET_INVALID（不部分输出）
- tie-break 按 canonical id（伪代码审计）
```
**U 映射**：U-3、U-5、U-16、U-18。
**建议裁决**：采纳分层优先级 + 确定性 tie-break + 显式 suppressed/BUDGET_INVALID；数值 S8。
**证据等级**：A（S3-11 预算归属/默认 200/400；U-16/U-18）；**本项目假设**（tier/label_rank/tie-break 细则）。

---

## 3. S4-3 一跳挂接（恰好一条 E_relation(D) 边；不闭包）

**定义/规则（一句话）**：A 维度的一跳 = 从基座节点出发，沿**恰好一条** `E_relation(D)` 边（方向 `dir(D)`）到达的邻居；只取端点+这条边，不递归/不闭包/不带背后图；H 维度是层次下钻，不是关系跳。

**形式化**：
```
E_relation(A) = S1 注册的 relation_sources（v1 ⊇ E_relation_min）
one_hop(F, A) = {(u,v,e) | u∈F, e∈E_relation(A), e 按 dir(A) 连接 u→v,
                 v∉F, hop(v)=1}
节点：F ∪ {v | 存在上述边}（去重，取最小 hop）
边：上述 e（每条 canonical id 唯一；同对多类型边分别保留）
禁止：hop>1 的自动扩展；v 的背后邻居/簇成员；A 不改变 H 基座
H：一次下钻=下一层块（S1-4），无 hop 预算
```
**端点 kind/方向**：
```
端点 kind ∈ {kp,cluster}（S0/S1）；cluster 端点只显示该节点，不展开成员
dir(A) ∈ {both,out,in}（S1-8）；H=down；非法/不匹配 fail-closed
hop_budget 默认 1；=2 仅当 frame_spec.new_hop=true 且由 S5 显式 EXPLICIT_NEW_HOP 设置
```
**反例**：自动 2 跳/闭包（U-18）；展开一跳端点背后图（U-17）；忽略方向；把 H 下钻当 A 跳；展示端点成员；同对多边合并。
**边界**：多条边到同一节点（节点去重、边保留）；cluster 端点；无邻居；hop=2 显式；方向 both 双向。
**机检条件**：
```
- 每个新增节点距离==1（除非 new_hop=true 且 hop=2）
- 不存在距离>hop_budget 的 shown 节点
- 一跳节点不展开成员（无其 membership 子节点）
- 端点 kind ∈ {kp,cluster}；dir 枚举合法
- no closure：无"邻居的邻居"自动 shown
```
**U 映射**：U-10、U-15、U-17、U-18、U-19、U-22。
**建议裁决**：采纳恰好一跳/不闭包/端点 kind/方向/2 跳仅 S5 显式；不带背后图。
**证据等级**：A（U-15/U-17/U-18；S0-5；S1-5 `S1-dimensions-v1.md:63-67`）；**本项目假设**（new_hop 的 frame 校验细节）。

---

## 4. S4-4 边「存无」三值（shown/suppressed/unknown；U-27）

**定义/规则（一句话）**：每条候选边在 `ctx` 下由 S4 判 `presence`：`shown`=准入渲染；`suppressed`=候选存在但被明确规则排除（带 rule_id）；`unknown`=候选无法判定/数据未加载（带 rule_id，禁止当"不存在"）；**类型不同则独立判定**（U-27）。

**形式化**：
```
presence(e,ctx) ∈ {shown, suppressed, unknown}
shown     ⇔ e∈CandidateSet ∧ 端点均被选中 ∧ 通过维度/层次/方向/跳数/预算规则
suppressed⇔ e∈CandidateSet ∧ 被规则排除：必须带 rule_id（枚举见下）
unknown   ⇔ e 是候选但输入不完整/未计算：必须带 rule_id；不渲染；不得解读为"无关系"
edge type 独立：同 (source,target) 多种 type 各自 canonical id，各自 presence
```
**rule_id 枚举（v1，穷举）**：
| rule_id | 语义 | presence |
|---|---|---|
| `dimension.sources` | 边 type 不在当前维度 relation_sources | suppressed |
| `dimension.direction` | 方向过滤（dir 不通过） | suppressed |
| `level.cross_layer` | 跨层边在当前层不可见 | suppressed |
| `hop.budget` | A 跳数超过 hop_budget | suppressed |
| `node.budget` | 端点节点被预算排除 | suppressed |
| `edge.budget` | 边预算耗尽 | suppressed |
| `cluster.folded` | 端点/边被折叠进簇，原边不直接显示 | suppressed |
| `endpoint.unresolved` | 端点数据不完整/找不到 | unknown |
| `source.unavailable` | 关系源未加载/不可用 | unknown |
| `admission.undecided` | 规则输入未计算（缓存/stale） | unknown |
| `invalid.data` | 边数据非法（自环/缺端点等） | suppressed（fail-visible） |
（`budget.*`/`node.*` 是 S4 唯一产生；Renderer 不得产生这些）
**unknown 语义**：不渲染；UI 检查器/aria 标"未计算/数据未加载"；不得显示为"无关系"；可触发重试（S5/S9）。
**反例**：数据里有边就画；视图中无边 ⇒ 断言无关系（应 unknown/suppressed 解释）；unknown 画虚线幽灵；同对多类型合并一条；维度过滤改写 type 为 reference。
**边界**：同对多类型（一条 shown 一条 suppressed）；cluster 折叠；unknown 源恢复后新 frame；full 模式仅预算规则变化。
**机检条件**：
```
- 每条候选边都有 presence；presence!=shown ⇒ rule_id ∈ 枚举
- shown 边端点均在 VM.nodes；无悬空边
- 同对多类型边独立 presence（不合并）
- unknown 不渲染；suppressed 不渲染；Renderer 只画 shown
- 无"数据不存在"被写成 unknown（unknown 仅候选输入不完整）
```
**U 映射**：U-16、U-17、U-27。
**建议裁决**：采纳三值 + rule_id 枚举 + 类型独立 + unknown 不渲染/不表示无关系。
**证据等级**：A（S0-6 `S0-terms-v1.md:56-61`；S1-12；U-27；SE S0-6 三值）；**本项目假设**（rule_id 枚举细节由 S4 冻结）。

---

## 5. S4-5 背后图不带入（一跳端点作新焦点；2 跳只 S5）

**定义/规则（一句话）**：一跳端点只是当前帧的可见节点；它成为新焦点必须由 S5 发起新 frame；S4 不自动展开其背后图；2 跳只能由 S5 的**唯一显式** `EXPLICIT_NEW_HOP` 触发（`new_hop=true`）。

**形式化**：
```
一跳端点 v：只显示 v + 边 e；不显示 v 的邻域/成员/其他边（U-17）
若用户点击 v：S5 决定 = 新 frame（新 focus=v）或跳编辑器（kp）
  新 frame 时 S4 重新 Admission；hop 重置/按维度 default（S1-5）
2 跳：仅 frame_spec.new_hop==true ∧ hop_budget==2（S5 唯一显式动作）
     S4 校验：hop=2 且 new_hop!=true ⇒ S4_HOP_GATE_FAIL（fail-closed）
跨层边：仅 H 的父→子结构边在当前层显示；其它跨层边 rule_id=level.cross_layer（suppressed）
多归属：cluster 端点只按当前 view_family 显示；不展开其其它族成员；membership 不进 VM
```
**反例**：点击一跳节点自动展开其邻域（闭包）；2 跳默认/自动；跨层边混入；多归属簇展开全部成员；把一跳端点作为 focus 但不重置预算。
**边界**：端点 cluster 点击进入其子图（S5）；端点 KP 点击编辑器；new_hop 显式且 hop=2；无邻居；跨族重叠。
**机检条件**：
```
- 无 distance>hop_budget 的 shown；无"邻居的邻居"自动加入
- hop_budget==2 ⇒ new_hop==true（帧校验）
- 一跳端点无其成员/邻域节点
- 跨层非结构边 presence=suppressed+level.cross_layer
```
**U 映射**：U-7、U-17、U-19、U-21、U-22。
**建议裁决**：采纳端点只作可见节点/新焦点由 S5；2 跳仅 EXPLICIT_NEW_HOP；不带背后图。
**证据等级**：A（U-17/U-21/U-22；S1-5 `:65`；`ENGINEERING-PLAN.md:912-914` ST-12/13/14）；**本项目假设**（new_hop 校验错误码）。

---

## 6. S4-6 维度接入（frame_spec；H/A 只改 presence）

**定义/规则（一句话）**：S4 通过 `frame_spec.dimension_id` 解析 S1 维度，按维度的 relation_sources/direction/hop/descent 决定候选与 presence；维度只改取景，不改 type/label/事实；H/A 都进入同一 Admission。

**形式化**：
```
frame_spec = {
  level_id, view_family_id, dimension_id, focus_id,
  hop_budget, new_hop, mode∈{default,full}, budget{max_nodes,max_edges}
}
H: relation_sources=[]；只沿 contain(structural) 下钻；无 hop；候选=当前层块+子块
A: relation_sources ⊇ E_relation_min；hop 1/2；方向 dir(A)；候选=基座+一跳端点
presence 由维度规则决定；type/contain_kind/label 不改
未知/保留/弃用 dimension_id ⇒ DIM_UNKNOWN/DIM_NOT_ACTIVE（fail-closed）
```
**反例**：维度切换改边类型/标签；用维度过滤伪造"无边"；H 走关系邻居；A 改 level；维度逻辑进 Renderer。
**边界**：H/A 切换；hop 重置；reserved 维度拒绝；维度与全展开正交（full 模式不改变 dimension_id 语义）。
**机检条件**：
```
- 同一 DataSource 不同 dimension：type/label/contain_kind 相同，仅 presence/选择不同
- frame_spec 含单 dimension_id（S1 D-5）；未知/保留 fail-closed
- H 无 hop；A hop≤2/new_hop 校验
- Renderer 不读 dimension 规则（只看 VM）
```
**U 映射**：U-8、U-9、U-10、U-11、U-12、U-30。
**建议裁决**：采纳 frame_spec 维度接入；维度只改 presence；失败关闭。
**证据等级**：A（S1-5/S1-12/S1-13；D-5；U-10）；**本项目假设**（frame_spec 字段命名）。

---

## 7. S4-7 层次与一跳交互（drill 重置；跨层边）

**定义/规则（一句话）**：drill（H）进入下一层会创建新 frame：focus=被展开簇、level+1、A hop 重置、预算按新 frame 重算；跨层边只有 H 父子结构边显示；簇/run 由 S2 按 `(level,view_family)` 提供，不重算。

**形式化**：
```
drill: S5 CLICK_CLUSTER → new frame{level=ℓ+1, focus=cluster, hop_budget=default, new_hop=false}
S4 读取 S2 run(level=ℓ+1, view_family) 的划分；不重算 HAC/μ/β
跨层边：
  H 派生父→子结构边（S1 R-S1-11）显示；
  其它 endpoint 跨层边 ⇒ suppressed + level.cross_layer
A 在当前 level 基座上扩展；不因 drill 保留旧一跳节点
多归属：当前 view_family 的 membership 优先；跨族重叠不合并
```
**反例**：drill 后沿用旧 hop/旧一跳；跨层 reference 混入；S4 重算簇；旧节点残留；多归属合并两族。
**边界**：叶层（KP）；无子簇 degenerate；跨层 H 结构边空集（S1 允许）；focus 簇无子。
**机检条件**：
```
- 新 frame level 与 S2 run level/view_family 一致；run 不重算
- drill 后 hop==default；旧一跳节点不残留
- 跨层非 H 边 suppressed+level.cross_layer；H 边 data_edge_ids 可审计
```
**U 映射**：U-5、U-7、U-8、U-21、U-28。
**建议裁决**：采纳 drill 新 frame+hop 重置+跨层规则；S4 不重算簇。
**证据等级**：A（S1-4/S1-5；S2-7/S2-10；`ENGINEERING-PLAN.md:905-910` ST-05/07）；**本项目假设**（旧节点清理细节）。

---

## 8. S4-8 全展开模式（同一 present；子集约束）

**定义/规则（一句话）**：全展开是 Presentation 正交模式，仍走同一 Admission/present；只放宽 relation/hop/预算参数，**`shown(default) ⊆ shown(full)`**；不得 raw edges 直出/第二数据源；预算超限仍显式降级。

**形式化**：
```
ctx_full = ctx with mode=full, relation_scope=all_data_edges,
           hop_budget=FULL_MAX（S8）, budget=full budget（S8；可大于 default）
present_full(e) = Admission(e, ctx_full)（同一函数/同一规则表）
约束：shown(default) ⊆ shown(full) ⊆ CandidateSet(DataSource)
差异：full 可显示 reference/structural 等默认被维度/层次排除的边；仍只 shown 绘制
预算：full 仍 max_nodes/max_edges 硬上限；超限 ⇒ S4_BUDGET_INVALID（不静默截断）
```
**反例**：full 直读 DataSource.edges 全画（绕过 present）；full 另一数据源/渲染器；full 显示 default 没有的边却 default 不 subset；full 静默截断。
**边界**：默认在叶层与 full 选点接近；full 仍需 budget；unknown 仍 unknown；无第二 builder。
**机检条件**：
```
- 同一 Admission 函数/同一 rule_id 表（代码/接口检查）
- shown(default) ⊆ shown(full)（同 DataSource/edition）
- full 只画 shown；无 raw edges 路径；无第二数据源
- full 超预算 ⇒ S4_BUDGET_INVALID（不部分）
```
**U 映射**：U-5、U-16、U-26、U-27。
**建议裁决**：采纳同 present + 放宽参数 + 子集约束 + 预算降级。
**证据等级**：A（S0-8；S3-9；`ENGINEERING-PLAN.md:944-945` ST-15/16）；**本项目假设**（FULL_MAX/full budget 归 S8）。

---

## 9. S4-9 与 S3 契约（VM/presence/aggregate_count；Renderer 不裁剪）

**定义/规则（一句话）**：S4 输出 VM 的 `nodes/edges`（每条边带 presence/rule_id/hop/aggregate_count；聚合边 data_edge_ids 审计），Renderer 只校验/渲染；S4 与 Renderer 的 max 阈值同源；VM 超硬上限由 Renderer `RENDER_BUDGET_EXCEEDED`，但正常路径 S4 保证不超。

**形式化**：
```
S4→VM：
  nodes[] 被选节点（kind∈{kp,cluster}；role∈{member/focus}；S3 字段）
  edges[] 候选边（presence/rule_id/hop/underlying_hop_count/aggregate_count/data_edge_ids?）
  VM 白名单遵守 S3（无 metrics/nav/mode/capabilities；data_edge_ids 仅审计）
Renderer：
  只画 presence=shown；不裁剪/不静默丢；VM 超 max_nodes/max_edges ⇒ RENDER_BUDGET_EXCEEDED
阈值同源：S4 budget.max_nodes/max_edges == Renderer.getCapabilities().maxNodes/maxEdges
```
**反例**：S4 输出超上限让 Renderer 丢；Renderer 自己裁剪；S4 遍历 data_edge_ids 算 aggregate_count（应显式给）；S4 输出 mode/nav。
**边界**：恰好上限；空 VM；Renderer 拒收超限；聚合边 data_edge_ids 可空（H 边 S1 例外）。
**机检条件**：
```
- S4 输出 nodes≤max_nodes、edges≤max_edges（正常路径）
- Renderer 只画 shown；无裁剪代码
- S4/Renderer 阈值同源（同一配置 sha）
- VM 白名单；aggregate_count 显式（不遍历 data_edge_ids）
```
**U 映射**：U-3、U-16、U-27、U-33。
**建议裁决**：采纳 S4 输出 VM/Renderer 只校验渲染/阈值同源；超限 fail-visible。
**证据等级**：A（S3-11/R-S3-2；S3-12/R-S3-9；U-33）；**本项目假设**（聚合计数由取景层给）。

---

## 10. S4-10 与 S5 导航边界（focus/selection/nav 不进 VM）

**定义/规则（一句话）**：S4 是**纯取景函数**：输入 `frame_spec`（含 focus/hop/new_hop），输出 VM；不保存导航/历史/选中；事件由 Renderer→S5，S5 产生新 frame；S4 内不得有导航状态机。

**形式化**：
```
S4 输入 frame_spec（S5/Presentation 提供）；输出 VM（无 nav/focus/selection 字段）
事件流：Renderer nodeClick/edgeClick/backgroundClick → S5
S5：更新 GRAPH_NAV_FRAME/history/焦点；生成新 frame_spec → S4
S4 禁止：push/pop history、维护 selected/focus、处理返回/层级切换
new_hop：仅 S5 EXPLICIT_NEW_HOP 动作设置 frame_spec.new_hop=true
```
**反例**：VM 带 focus/selection/history；S4 处理点击导航；S4 保存上次 focus；Renderer 发导航动作。
**边界**：点击 KP 跳编辑器（S5）；点击簇下钻（S5）；返回（S5）；多归属返回 origin（S5）。
**机检条件**：
```
- VM 无 nav/focus/selection/history 字段
- S4 无状态（纯函数）；同 frame_spec 输出相同
- 事件 payload 无导航字段（S3-7）；new_hop 只由 S5 设置
```
**U 映射**：U-7、U-19、U-21、U-22。
**建议裁决**：采纳 S4 纯取景/S5 导航；focus 只作输入；2 跳仅 S5。
**证据等级**：A（S0-9/D-4；S3-7；`ENGINEERING-PLAN.md:713-719`）；**本项目假设**（frame_spec 生成细节）。

---

## 11. S4-11 与 S1/S2 一致性（presence 不改事实；簇/run 不进 VM）

**定义/规则（一句话）**：Admission 只改 `presence/选择`；不改 `type/contain_kind/label/簇成员/run`；A 不改变簇；多归属按当前 view_family；簇/run/dendrogram 不进 VM。

**形式化**：
```
presence 不变式：对同一 DataSource/edge，S4 输出后 type/contain_kind/label 字段不变
A 不改变簇：S4 不做聚类；S2 run 只读；A 只扩展可见节点
多归属：VM 节点按当前 (level,view_family) 的 membership；跨族重叠不合并
VM 不含 cluster_run_id/cluster_key/dendrogram/run_status/candidate/params_hash
无簇状态：S4 可输出 KP+布局分组，不伪造簇；不注入结构边造簇
```
**反例**：S4 改 label/type 让边"更语义"；A 重新聚类；多归属合并成员；VM 带 run 状态；无簇时用结构边造簇。
**边界**：多类型边；多归属节点；无簇；A/H 切换；跨族。
**机检条件**：
```
- 字段不变式：S4 前后 type/contain_kind/label 相同
- VM 无 run/dendrogram/cluster_key/params_hash
- 同一 DataSource+params 下 A 切换不改变 S2 run（S2-10）
- 无簇时不产生 kind=cluster 假节点/不注入结构边
```
**U 映射**：U-1、U-10、U-21、U-27、U-31。
**建议裁决**：采纳 presence 不改事实/只读 run/多归属按 view_family/VM 纯度。
**证据等级**：A（S1-12；S2-10/S2-11；S0-6/D-4）；**本项目假设**（多归属选择细节）。

---

## 12. S4-12 度量与验收（G6 快照/复跑）

**定义/规则（一句话）**：每次 Admission 产出可复算指标：每屏节点/边数、presence 分布（shown/suppressed/unknown 按 rule_id）、抑制比例、一跳距离违规=0、确定性 hash、default⊆full、预算命中/超限；G6 快照记录 ctx/budget/edition/rule_id 直方图；数值门禁 S8。

**形式化（指标）**：
```
per frame:
  node_count, edge_count, shown/suppressed/unknown counts, suppression_ratio
  rule_id_histogram（枚举内）
  hop_max_shown, closure_violations(=0), behind_graph_leak(=0)
  deterministic_sha256 = sha256(canonical(shown node ids/edge ids/rule_ids))
  budget{max_nodes,max_edges}, budget_hit(bool), budget_error
per pair default/full:
  subset_ok = shown(default) ⊆ shown(full)
G6 snapshot:
  edition/corpus_manifest, level_id/dimension_id/focus/hop/new_hop/mode,
  budget, node/edge counts, presence histogram, rule_id histogram,
  deterministic sha, subset_ok, run_id? (S2 run 只作输入标识，不进 VM)
```
**机检条件**：
```
- 同输入两次 deterministic_sha 相同
- suppression 全部有 rule_id；unknown/suppressed 比例可复算
- closure_violations=0；behind_graph_leak=0
- shown(default)⊆shown(full)（同 edition）
- budget_* 与 S8 配置一致；超限有错误/降级标记
```
**反例**：只统计节点数；抑制无边规则统计；一跳违规不测；default/full 用不同数据源；指标含随机/时间。
**边界**：空帧（0/0）；全抑制；full 超预算；多归属帧；无簇帧。
**U 映射**：U-3、U-16、U-18、U-32、U-34。
**建议裁决**：采纳指标清单/G6 快照/确定性；数值阈值 S8。
**证据等级**：A（U-32；S3-11/S3-12；`ENGINEERING-PLAN.md:660` P5）；**本项目假设**（指标字段/门禁）。

---

## 13. 覆盖矩阵

| U# | 要点 | S4 落点 |
|---|---|---|
| U-5 | 默认非全展开/可见节点非最小粒度 | S4-1/S4-2/S4-8 |
| U-15 | 深入后语义边挂接一跳 | S4-3/S4-6 |
| U-16 | 旧版全量→选择性渲染 | S4-1/S4-2/S4-4 |
| U-17 | 一跳背后图不带入 | S4-3/S4-5 |
| U-18 | 限制跳数避免污染 | S4-3/S4-5/S4-12 |
| U-19 | 一跳节点可为 KP/簇 | S4-3/S4-5 |
| U-21 | 多归属/返回 | S4-5/S4-11 |
| U-22 | 新一跳 vs 更深 | S4-3/S4-5/S4-10 |
| U-27 | 边存无/类型 | S4-4 |
| U-28 | 最小粒度 KP | S4-7（叶层） |
| U-31 | 多归属不设上限 | S4-11 |
| S0 | S0-6 present/R-3、S0-8 full、D-4 | S4-4/S4-8/S4-9/S4-10 |
| S1 | H/A、hop/new_hop、present 只改 presence | S4-3/S4-6 |
| S2 | 簇/run、无簇、A 不改簇 | S4-7/S4-11 |
| S3 | presence 字段、Renderer 不裁剪、预算同源 | S4-9/S4-10 |

---

## 14. 仍存争议 / 待 Lead·SE 裁决

1. **tier/label_rank/tie-break 具体值**：本提案用 semantic<structural<navigation 排序；是否把 reference 排最后、是否加入 hop 优先需 S4 修订/SE 校核。
2. **预算不足语义**：`S4_BUDGET_INVALID`（fail-visible）vs 降级只显示 focus；本提案 fail-visible，避免静默；S8 需保证 max ≥ 最小必选集。
3. **full 模式的 `FULL_MAX`/full budget**：全展开是否允许比 default 更大预算、是否仍受 max_nodes/max_edges 约束；本提案要求仍受硬上限（S8 定值）。
4. **unknown 的触发面**：哪些输入缺失算 unknown（source/端点/缓存），是否允许"未计算"的边集整体 unknown；本提案只对候选边判 unknown，不伪造无边。
5. **多归属端点**：cluster 端点跨族时显示哪一个 view_family 的簇（本提案当前 frame family 优先），S5/S6 可细化。

---

## 15. 证据锚（详见 `S4-evidence-A.md`）

```text
原话：vision.md:22（U-5）、:32-36（U-15..U-19）、:38-39（U-21/U-22）、:66-67（U-27/U-28）、:70（U-31）
S0：S0-terms-v1.md:49-54（S0-5 一跳）、:56-61（S0-6 presence/R-3）、:69-73（S0-8 full）、:75-79（S0-9 VM）
S1：S1-dimensions-v1.md:57-67（H/A 一跳/new_hop）、:99-107（present/VM）
S2：S2-clustering-v1.md:17（簇/单点）、:64-71（S2-10/S2-11）、:73-76（无簇）
S3：S3-visual-v1.md:36-39（presence）、:66-69（预算归属）、:71-75（VM 白名单/data_edge_ids）
工程：ENGINEERING-PLAN.md:583,660（P5 Admission）、:912-916（ST-12..16）、:224-250（VM）
代码（反例/现状）：graph-engine.js:179-180（rawEdges 全量）；graph-view-2d.js:634-663（simLinks 全画）；app.js:1845（单入口）
```
