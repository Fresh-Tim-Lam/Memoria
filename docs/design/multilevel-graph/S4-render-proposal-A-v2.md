# S4 提案 A-v2：选择性渲染、一跳挂接与边「存无」（focus 一跳 / 最小必选 / 候选载体）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-313｜**日期**：2026-11-03（Asia/Shanghai）
> **唯一修订依据**：`docs/design/multilevel-graph/S4-RULINGS.md`（R-S4-1..R-S4-8）。
> **最高依据**：`vision.md`；上游冻结：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）。
> **本文件**：A 修订版；**不覆盖** `S4-render-proposal-A.md`（v1 `ba11c990…`），保留审计链。
> **纪律**：不写产品代码、不改 S0–S3 冻结稿/契约、不 commit；独立写。

---

## 0. 修订摘要（R-S4 → 结构变化）

| 裁决 | v1 问题 | v2 落实 |
|---|---|---|
| **R-S4-1（P1）** 一跳起点 | v1 `one_hop` 基座 F = 整层可见块（会变成邻域展开） | **F={focus}**（单焦点；cluster 焦点即该簇节点）；`one_hop(F)={v \| ∃e∈E_relation(D) 连接 F 与 v, v∉F}`；不闭包/不带背后图；机检 `base(F)=={focus}`、`max_hop(shown)==1`（默认） |
| **R-S4-2（P1）** 隐式 2 跳 | v1 tier2=与 tier0/1 相邻（可能闭包） | tier2 **只含基座 + H 结构同层节点**，不含一跳端点的邻居；所有 shown `hop≤hop_budget`；默认 1；2 跳仅 S5 `EXPLICIT_NEW_HOP` |
| **R-S4-3（P1）** 最小必选/降级 | v1 tier0 超预算整屏失败 | `MANDATORY` 显式公式/上限；先保 MANDATORY，其余 `suppressed+rule_id`；**仅 MANDATORY 超预算** ⇒ `S4_BUDGET_INVALID`；S8 保证 `max_nodes ≥ |MANDATORY|` 上界 |
| **R-S4-4（P1）** 候选载体 | v1 VM 主体仍是"选择后"（B 只含 shown） | VM/AdmissionResult **携带全部候选节点/边**的逐条 `presence+rule_id`；Renderer 只渲染 shown；suppressed/unknown 保留审计 |
| **R-S4-5** rule_id/unknown | v1 11 类但 unknown 面模糊 | 统一 **11 类**；unknown 仅 `source.unavailable/endpoint.unresolved/admission.undecided/invalid.data` 四类；unknown≠无关系 |
| **R-S4-6** 排序键 | v1 tier/tie-break 未含 relation_class 冻结 | 冻结 `(tier, hop, relation_class, label_rank, canonical_id)`；`relation_class=semantic<structural<navigation<reference` |
| **R-S4-7** 全展开 | v1 "放宽 relation/hop"可能被读成 raw data | `relation_scope=candidate_scope`（不是 raw data edges 直出）；同 Admission/present；subset；S8 硬上限 |
| **R-S4-8** 并集 | — | 吸收 B 的 focus 一跳/VM 严格性/无 tier0 失败；`aggregate_count` 不遍历 `data_edge_ids`；G6 字段统一 |

**管线不变**：`DataSource → P4 候选 → P5 Admission（S4 唯一裁剪者）→ P6 VM → P7 Renderer（只渲染 shown，不裁剪）`。

---

## 1. S4-1 选择性渲染定义与边界（唯一裁剪者）

**定义/规则（一句话）**：S4=Admission，是唯一决定候选节点/边 `presence` 与选择的人；只改 `presence/选择`，不改 DataSource/type/label/簇；P4 只生成候选集，Renderer 只校验/渲染。

**形式化**：
```
Admission: (CandidateSet, frame_spec, budget) → AdmissionResult
  AdmissionResult.nodes[] = 全部候选节点 + {presence∈{shown,suppressed,unknown}, rule_id}
  AdmissionResult.edges[] = 全部候选边 + {presence, rule_id, hop, aggregate_count?}
  VM 由 AdmissionResult 投影（候选载体见 S4-9）
约束：
  - 只有 S4 产生 suppressed/unknown 与 rule_id；P4 候选生成不是 presence 裁剪
  - type/contain_kind/label 不改；DataSource 不改；不重算簇/μ/β
  - Renderer 不裁剪/不静默丢（S3 R-S3-2）
旧行为对比：graph-engine.expandLinks/rawEdges 全量映射（graph-engine.js:179-180）→ 本设计以 Admission 替代
```
**反例**：P4 直接丢弃候选且无记录；Renderer 二次裁剪；S4 改 type/label；同一 VM 两套裁剪行为。
**边界**：候选为空；focus 不存在（`S4_FOCUS_UNRESOLVED`）；预算恰好；S9 候选 scope 变化不改 presence 语义。
**机检条件**：
```
- 唯一裁剪者：只有 AdmissionResult 产生 suppressed/unknown/rule_id；Renderer 无裁剪逻辑
- 字段不变式：type/contain_kind/label 前后一致
- 全部候选节点/边都有 presence+rule_id（R-S4-4）
- Renderer 输入后 shown 集合不再减少
```
**U 映射**：U-3、U-16、U-27。
**建议裁决**：采纳唯一裁剪者 + 候选载体 + 不改事实。
**证据等级**：A（S0-6/S3-11；U-16；`graph-engine.js:179-180`）；**本项目假设**（AdmissionResult 字段）。

---

## 2. S4-2 预算内选点（MANDATORY + tier + 排序键）

**定义/规则（一句话）**：先保证显式 `MANDATORY` 必选集，再按冻结排序键 `(tier, hop, relation_class, label_rank, canonical_id)` 在 `max_nodes/max_edges` 内选其余；超预算候选 `suppressed+rule_id`；**仅 MANDATORY 本身超预算**才 `S4_BUDGET_INVALID`。

**形式化（MANDATORY 显式公式）**：
```
A 维度：MANDATORY = {focus}
H 维度：MANDATORY = {focus} ∪ first K children(focus)（按 canonical_id 升序）
        K = min(|children(focus)|, MANDATORY_CONTEXT_CAP)
        MANDATORY_CONTEXT_CAP 默认 20（S8 可调；S4 冻结字段/公式）
        若 focus 是 KP（叶）：MANDATORY={focus}
|MANDATORY| ≤ 1 + MANDATORY_CONTEXT_CAP（默认 21）
S8 必须保证 max_nodes ≥ 1 + MANDATORY_CONTEXT_CAP；仅当 max_nodes < |MANDATORY| ⇒ S4_BUDGET_INVALID
```
**形式化（tier）**：
```
tier 0：MANDATORY
tier 1：A 的一跳端点（hop=1，按排序键）；H 无 tier1（下钻层级不产生关系跳）
tier 2：只允许 基座(focus) + H 结构同层节点（如 include_level_context=true；默认空）
       不得包含"一跳端点的邻居"（R-S4-2）
其余候选：suppressed（A 距离>1 ⇒ hop.budget；H 非上下文 ⇒ node.budget）
排序键（冻结）：(tier, hop, relation_class, label_rank, canonical_id)
  relation_class = semantic=0 < structural=1 < navigation=2 < reference=3
  label_rank = VM edge.label 的确定性字符串序（semantic/structural/navigation）
  canonical_id = 节点/边 canonical id 升序
```
**边选择**：
```
候选边：符合维度/方向/层次/端点选择
优先级：edge_tier 0 H 父子结构边 / 1 A 一跳边 / 2 语义上下文 / 3 结构上下文 / 4 reference
键：(edge_tier, hop, relation_class, label_rank, canonical_id)
取前 max_edges；超出 ⇒ suppressed + rule_id=edge.budget；端点未 shown ⇒ node.budget
```
**显式降级**：
```
- MANDATORY 以内保留；non-mandatory 超出 ⇒ suppressed+rule_id（可统计）
- MANDATORY 超预算 ⇒ S4_BUDGET_INVALID（fail-visible；不部分渲染）
- focus 不在候选 ⇒ S4_FOCUS_UNRESOLVED（fail-visible；不是预算问题）
- 无 tier0 不会发生（focus 必存在；否则 focus 错误）
```
**反例**：MANDATORY 用整层块导致必选爆炸；非必选超预算整屏失败（P1）；tier2 从一跳端点继续扩展（隐式 2 跳）；排序键不确定；MANDATORY 超预算静默丢。
**边界**：children > CAP ⇒ 其余 suppressed node.budget；max_nodes 恰好 |MANDATORY|；max_edges 0；focus 单独。
**机检条件**：
```
- MANDATORY 可枚举且 |MANDATORY|≤1+CONTEXT_CAP
- 预算不足只抑制非 MANDATORY；仅 |MANDATORY|>max_nodes ⇒ S4_BUDGET_INVALID
- shown nodes/edges 数 ≤ max；无静默丢弃
- 排序键可复算；两次运行同结果
```
**U 映射**：U-3、U-5、U-16、U-18。
**建议裁决**：采纳 MANDATORY 公式/上限 + tier + 冻结排序键；仅 MANDATORY 超预算失败。
**证据等级**：A（R-S4-3/R-S4-6 `S4-RULINGS.md:30-47`；S3-11；U-16/U-18）；**本项目假设**（CAP=20、tier 细节）。

---

## 3. S4-3 一跳挂接（F={focus}；恰好一条 E_relation(D) 边）

**定义/规则（一句话）**：默认 one-hop 的基座 **F={focus}**；`one_hop(F)={v | ∃e∈E_relation(D) 连接 F 与 v, v∉F}`；每条关系边=1 跳；不闭包/不带背后图。

**形式化**：
```
F = {focus}                                   # 单焦点（cluster 焦点=该簇节点）；R-S4-1
one_hop(F) = {v | ∃e∈E_relation(A), e 按 dir(A) 连接 u∈F 与 v, v∉F}
节点：F ∪ 一跳端点（节点 id 去重；端点可有多条边）
边：每条 e（canonical id 独立；同对多类型分别保留）
hop(v)=1（默认）；max_hop(shown)=1
禁止：F=整层可见块；hop>1 自动；v 的邻域/成员/背后图；A 闭包
H：一次下钻=下一层（S1-4），不是 one_hop；H 无 hop
```
**端点/方向**：
```
端点 kind∈{kp,cluster}；cluster 端点只显示节点，不展开成员
dir(A)∈{both,out,in}（S1-8）；非法 fail-closed
hop_budget 默认 1；=2 仅 S5 EXPLICIT_NEW_HOP（new_hop=true）
```
**反例**：用整层可见块当 F（P1）；从每个基座挂边接近邻域展开；2 跳自动；展开端点背后图；同对多边合并；H 当关系跳。
**边界**：focus 无邻居（只有 MANDATORY）；多条边到同一节点；cluster 端点；new_hop=true；方向 both。
**机检条件**：
```
- base(F)=={focus}（只有一个基座）
- 默认 max_hop(shown)==1；new_hop=false 时不存在 hop>1
- 端点 kind∈{kp,cluster}；无端点成员节点
- 无闭包：无"邻居的邻居"自动 shown
```
**U 映射**：U-10、U-15、U-17、U-18、U-19、U-22。
**建议裁决**：采纳 F={focus}、恰好一跳、不闭包/不带背后图、2 跳仅 S5。
**证据等级**：A（R-S4-1 `S4-RULINGS.md:20-23`；S0-5；S1-5 `S1-dimensions-v1.md:63-67`）；**本项目假设**（new_hop 校验细节）。

---

## 4. S4-4 边「存无」三值与 rule_id（11 类；unknown 4 类）

**定义/规则（一句话）**：对**全部候选边**逐条判 `presence`：shown=准入渲染；suppressed=候选存在但被已知规则排除；unknown=候选输入不完整/未计算（不等于"无关系"）；每条带 `rule_id`。

**形式化**：
```
presence(e) ∈ {shown, suppressed, unknown}
shown     ⇔ e∈CandidateSet ∧ 端点在 MANDATORY/tier 内 ∧ 维度/层次/方向/跳数/预算通过
suppressed⇔ e∈CandidateSet ∧ 被已知规则排除（7 类 rule_id）
unknown   ⇔ e∈CandidateSet ∧ 输入不完整/未计算（4 类 rule_id）；不渲染；不表示"无关系"
类型独立：同 (source,target) 多 type 各自 canonical id/各自 presence（U-27）
```
**rule_id 统一 11 类**：
| # | rule_id | presence | 含义 |
|---|---|---|---|
| 1 | `dimension.sources` | suppressed | type 不在当前维度 relation_sources |
| 2 | `dimension.direction` | suppressed | 方向过滤不通过 |
| 3 | `level.cross_layer` | suppressed | 跨层边在当前层不可见 |
| 4 | `hop.budget` | suppressed | A 跳数超过 hop_budget（非 new_hop） |
| 5 | `node.budget` | suppressed | 端点节点非 MANDATORY/超预算 |
| 6 | `edge.budget` | suppressed | 边预算耗尽 |
| 7 | `cluster.folded` | suppressed | 端点/边折叠进簇，原边不直显 |
| 8 | `endpoint.unresolved` | **unknown** | 端点数据不完整/找不到 |
| 9 | `source.unavailable` | **unknown** | 关系源未加载/不可用 |
| 10 | `admission.undecided` | **unknown** | 规则输入未计算（缓存/stale） |
| 11 | `invalid.data` | **unknown** | 边数据非法（自环/缺端点等），无法判定 |
（unknown 仅 8–11；suppressed 1–7；unknown ≠ 无关系；`invalid.data` 不得当作 suppressed 静默）
**反例**：数据有边就画；视图中无边⇒断言无关系；unknown 画幽灵；同对多类型合并；用 invalid.data 静默抑制；rule_id 不在枚举。
**边界**：同对多类型一条 shown 一条 suppressed；cluster folded；unknown 恢复后新 frame；full 下仍按规则。
**机检条件**：
```
- 每条候选边都有 presence；presence!=shown ⇒ rule_id∈11 类
- unknown 只出现 8–11；suppressed 只出现 1–7
- shown 边端点在 VM nodes；无悬空边
- 同对多类型独立 presence；Renderer 只画 shown
```
**U 映射**：U-16、U-17、U-27。
**建议裁决**：采纳 11 类 rule_id + unknown 四类 + 类型独立 + unknown≠无关系。
**证据等级**：A（R-S4-5 `S4-RULINGS.md:40-42`；S0-6；S3-5）；**本项目假设**（第 11 类 invalid.data 归 unknown 的处置）。

---

## 5. S4-5 背后图不带入（一跳端点作新焦点；2 跳仅 S5）

**定义/规则（一句话）**：一跳端点只显示自身+边；它作新焦点必须 S5 新 frame；S4 不展开其邻域；默认不产生 2 跳，2 跳只由 S5 显式 `EXPLICIT_NEW_HOP`。

**形式化**：
```
一跳端点 v：只显示 v + 边；不显示 v 的邻域/成员/其它边（U-17）
点击 v：S5 决定（新 frame 或编辑器跳转）；S4 不自动扩展
2 跳：仅 frame_spec.new_hop==true ∧ hop_budget==2（S5 唯一显式动作）
     S4 校验：hop=2 且 new_hop!=true ⇒ S4_HOP_GATE_FAIL
     max_hop(shown) ≤ hop_budget；默认 =1
跨层：只有 H 父子结构边显示；其它 ⇒ suppressed level.cross_layer
多归属：cluster 端点按当前 view_family 显示；不展开其它族成员
```
**反例**：点击一跳节点自动展开邻域；默认 2 跳；跨层边混入；多归属簇展开全部成员；tier2 引入端点邻居（P1）。
**边界**：端点 cluster→S5 进入子图；端点 KP→编辑器；new_hop=true；无邻居；多归属。
**机检条件**：
```
- 默认 max_hop(shown)==1；hop≤hop_budget（所有 shown）
- hop=2 ⇒ new_hop=true
- 一跳端点无成员/邻域节点
- 跨层非 H 边 suppressed+level.cross_layer
```
**U 映射**：U-7、U-17、U-19、U-21、U-22。
**建议裁决**：采纳端点只显示；2 跳仅 S5；不带背后图。
**证据等级**：A（R-S4-1/2；U-17/U-22；`ENGINEERING-PLAN.md:912-914`）；**本项目假设**（S4_HOP_GATE_FAIL）。

---

## 6. S4-6 维度接入（frame_spec；只改 presence）

**定义/规则（一句话）**：S4 从 `frame_spec.dimension_id` 解析 S1 维度，按维度 relation_sources/direction/hop/descent 判候选与 presence；维度只改取景，不改事实；H/A 同一 Admission。

**形式化**：
```
frame_spec = {level_id, view_family_id, dimension_id, focus_id,
              hop_budget, new_hop, mode∈{default,full}, include_level_context,
              budget{max_nodes,max_edges}}
H: relation_sources=[]；沿 contain(structural) 下钻；无 hop；MANDATORY=focus+children(cap)
A: relation_sources ⊇ E_relation_min；F={focus}；hop 1/2；dir(A)
presence 由维度规则决定；type/contain_kind/label 不改；未知/保留/弃用 fail-closed
```
**反例**：维度切换改 type/label；用维度过滤伪造"无关系"；H 走关系邻居；A 改 level；维度逻辑进 Renderer。
**边界**：H/A 切换；hop 重置；reserved 拒绝；full 与 dimension 正交。
**机检条件**：
```
- 同 DataSource 不同 dimension：type/label/contain_kind 相同，仅 presence/选择不同
- frame_spec 单 dimension_id；未知/保留 fail-closed
- H 无 hop；A hop≤2/new_hop 校验
- Renderer 不读维度规则
```
**U 映射**：U-8、U-9、U-10、U-11、U-12、U-30。
**建议裁决**：采纳 frame_spec/维度接入；只改 presence。
**证据等级**：A（S1-5/S1-12/S1-13；D-5；U-10）；**本项目假设**（frame_spec 字段）。

---

## 7. S4-7 层次与一跳交互（drill 重置；跨层边）

**定义/规则（一句话）**：drill 新 frame：level+1、focus=被展开簇、hop 重置、MANDATORY 重新计算；S4 只读 S2 run；跨层只显示 H 父子结构边；A 不跨越层次。

**形式化**：
```
drill: S5 CLICK_CLUSTER → new frame{level=ℓ+1, focus=cluster, hop_budget=default, new_hop=false}
S4 读 S2 run(level=ℓ+1, view_family)，不重算 HAC
MANDATORY 按新 level/focus 重算（children cap）
跨层：H 父→子结构边显示；其它跨层 ⇒ suppressed level.cross_layer
旧一跳节点不残留；A 不跨层扩展
多归属：当前 view_family 优先；不合并跨族
```
**反例**：drill 沿用旧 hop/旧一跳；跨层 reference 混入；S4 重算簇；旧节点残留；多归属合并。
**边界**：叶层 KP；无子簇；跨层 H 边空集；focus 缺失。
**机检条件**：
```
- 新 frame level 与 S2 run 一致；run 不重算
- drill 后 hop=default；旧节点不残留
- 跨层非 H 边 suppressed+level.cross_layer
- MANDATORY 重算且 ≤ 上限
```
**U 映射**：U-5、U-7、U-8、U-21、U-28。
**建议裁决**：采纳 drill 新 frame/hop 重置/跨层规则。
**证据等级**：A（S1-4；S2-7/S2-10；`ENGINEERING-PLAN.md:905-910`）；**本项目假设**（旧节点清理）。

---

## 8. S4-8 全展开（同 Admission；candidate_scope）

**定义/规则（一句话）**：全展开与默认走**同一 Admission/present**；`relation_scope=candidate_scope`（P4 候选 scope，不是 raw data edges 直出）；`shown(default) ⊆ shown(full)`；full 仍受 S8 硬上限。

**形式化**：
```
ctx_full = ctx with mode=full, relation_scope=candidate_scope,
           hop_budget=FULL_HOP（S8）, budget=full budget（S8）
present_full = Admission(e, ctx_full)（同一函数/规则表）
约束：shown(default) ⊆ shown(full) ⊆ CandidateSet
full 可显示默认被维度/层次排除的候选，但仍需通过 Admission 规则；
     不得直接读取 DataSource.edges 绕过 Admission；不得第二数据源/第二 builder
超限：full 仍 max_nodes/max_edges 硬上限；仅 MANDATORY 超预算 ⇒ S4_BUDGET_INVALID（full 的 MANDATORY 同公式）
```
**反例**：full 直读 DataSource.edges；full 另一数据源/渲染器；default 不 subset；full 绕过 rule_id。
**边界**：默认叶层与 full 接近；full 仍有预算；unknown 仍 unknown。
**机检条件**：
```
- 同一 Admission 函数/规则表；同一 DataSource
- shown(default) ⊆ shown(full)
- full 不读取 raw DataSource.edges（只吃 CandidateSet）
- full 预算/超限路径存在
```
**U 映射**：U-5、U-16、U-26、U-27。
**建议裁决**：采纳同 Admission + candidate_scope + subset + 硬上限。
**证据等级**：A（R-S4-7 `S4-RULINGS.md:48-50`；S0-8；S3-9）；**本项目假设**（FULL_HOP/full budget 归 S8）。

---

## 9. S4-9 与 S3 契约（VM 候选载体；Renderer 只渲染 shown）

**定义/规则（一句话）**：S4 输出 AdmissionResult（全部候选节点/边 + presence/rule_id），VM 携带候选载体；Renderer 只渲染 shown、不裁剪；S4/Renderer 预算同源；聚合计数不遍历 `data_edge_ids`。

**形式化**：
```
AdmissionResult = {
  nodes[]: 全部候选节点 + {presence∈{shown,suppressed,unknown}, rule_id}
  edges[]: 全部候选边 + {presence, rule_id, hop, aggregate_count?, data_edge_ids?}
  mandatory_ids[], budget{max_nodes,max_edges}, stats
}
VM 候选载体（S3 扩展）：
  - 全部候选边（presence/rule_id）
  - 全部候选节点 + presence/rule_id（R-S4-4；S3-v1 节点白名单需 S6a 增 presence/rule_id）
Renderer：
  只画 nodes.presence==shown ∧ edges.presence==shown；不裁剪
  VM 超硬上限 ⇒ RENDER_BUDGET_EXCEEDED（正常路径 S4 保证不超）
阈值同源：S4 budget.max_nodes/max_edges == Renderer.getCapabilities().maxNodes/maxEdges
aggregate_count：取景层显式给（不遍历 data_edge_ids）
```
**S3 兼容性**：S3-v1 节点白名单（`S3-visual-v1.md:72`）未含 node presence/rule_id；本提案按 R-S4-4 要求提出**S4→S6a/S3 扩展**（节点 presence/rule_id）；若 Lead 要求严格不改 S3，则 S4 AdmissionResult 保留全部节点决策，VM 仅投影 shown 节点 + 全候选边（最小冲突方案），并在 S6a 前作为已知差异登记。
**反例**：VM 只含 shown（无法解释缺席）；Renderer 裁剪；S4 超上限让 Renderer 丢；aggregate_count 遍历 data_edge_ids；VM 带 nav/mode。
**边界**：候选全部 suppressed（只有 MANDATORY? focus 必 shown）；空候选；超限拒绝；节点 presence 扩展未批。
**机检条件**：
```
- AdmissionResult 覆盖全部候选节点/边；每条有 presence/rule_id
- VM 候选边完整；节点载体按扩展方案
- Renderer 只画 shown；无裁剪；阈值同源
- aggregate_count 不遍历 data_edge_ids（静态检查）
```
**U 映射**：U-3、U-16、U-27、U-33。
**建议裁决**：采纳候选载体/Renderer 只渲染/阈值同源；节点 presence 扩展交 S6a/S3 修订。
**证据等级**：A（R-S4-4 `S4-RULINGS.md:35-38`；S3-12/R-S3-9；S3-11）；**本项目假设**（VM 节点 presence 扩展字段名）。

---

## 10. S4-10 与 S5 导航边界（focus/selection/nav 不进 VM）

**定义/规则（一句话）**：S4 是纯取景函数：输入 frame_spec（focus/hop/new_hop），输出 AdmissionResult/VM；不保存导航/历史/选中；事件由 Renderer→S5，S5 产生新 frame。

**形式化**：
```
S4 输入 frame_spec（S5/Presentation）；输出 VM（无 nav/focus/selection/history 字段）
事件：Renderer→S5；S5 更新 GRAPH_NAV_FRAME，生成新 frame_spec→S4
S4 禁止：push/pop、维护 selected/focus、处理返回/层级切换
new_hop 仅 S5 EXPLICIT_NEW_HOP
```
**反例**：VM 带 focus/selection/history；S4 处理点击导航；S4 保存上次 focus；Renderer 发导航动作。
**边界**：KP 跳编辑器；簇下钻；返回；多归属 origin。
**机检条件**：
```
- VM 无 nav/focus/selection/history
- S4 纯函数（同 frame_spec 同输出）
- 事件 payload 无导航字段；new_hop 只由 S5 设置
```
**U 映射**：U-7、U-19、U-21、U-22。
**建议裁决**：采纳 S4 纯取景/S5 导航。
**证据等级**：A（S0-9/D-4；S3-7；`ENGINEERING-PLAN.md:713-719`）；**本项目假设**（frame_spec 生成）。

---

## 11. S4-11 与 S1/S2 一致性（presence 不改事实；簇/run 不进 VM）

**定义/规则（一句话）**：Admission 只改 presence/选择；不改 type/contain_kind/label/簇/run；A 不改变簇；多归属按当前 view_family；簇/run/dendrogram 不进 VM。

**形式化**：
```
presence 不变式：同一 DataSource/edge 输出后 type/contain_kind/label 不变
A 不改变簇：S4 不聚类；S2 run 只读；A 只扩可见节点
多归属：VM 节点按当前 (level,view_family) membership；跨族不合并
VM 无 cluster_run_id/cluster_key/dendrogram/run_status/candidate/params_hash
无簇：S4 输出 KP+布局分组（semantic=false），不伪造语义簇/不注入结构边
```
**反例**：改 label/type；A 重新聚类；多归属合并；VM 带 run；无簇造假簇。
**边界**：多类型边；多归属；无簇；A/H 切换。
**机检条件**：
```
- type/contain_kind/label 前后一致
- VM 无 run/dendrogram/cluster_key/params_hash
- A 切换不改变 S2 run（S2-10）
- 无簇不产生 kind=cluster 假节点
```
**U 映射**：U-1、U-10、U-21、U-27、U-31。
**建议裁决**：采纳 presence 不改事实/只读 run/多归属/VM 纯度。
**证据等级**：A（S1-12；S2-10/S2-11；S0-6/D-4）；**本项目假设**（多归属选择）。

---

## 12. S4-12 度量与验收（G6 快照/复跑）

**定义/规则（一句话）**：每帧可复算指标：候选/必选/显示数量、presence/rule_id 直方图、抑制比例、max_hop、default⊆full、确定性 sha、预算命中/超限；G6 快照记录 ctx/budget/edition/规则直方图。

**形式化**：
```
per frame:
  candidate_nodes/edges, mandatory_count, shown/suppressed/unknown counts,
  rule_id_histogram（11 类）, suppression_ratio,
  max_hop_shown, closure_violations(=0), behind_graph_leak(=0),
  deterministic_sha256 = sha256(canonical(shown ids + presence/rule_id 全量)),
  budget{max_nodes,max_edges}, budget_hit, budget_error
per pair default/full:
  subset_ok = shown(default) ⊆ shown(full)
G6 snapshot:
  edition/corpus_manifest, level_id/dimension_id/focus/hop/new_hop/mode,
  budget, candidate/mandatory/shown counts, presence histogram, rule_id histogram,
  deterministic sha, subset_ok, S2 run_id（只作输入标识，不进 VM）
```
**机检条件**：
```
- 同输入两次 deterministic_sha 相同
- 候选全覆盖；presence/rule_id 可统计；unknown/suppressed 分离
- max_hop_shown≤hop_budget；closure/behind=0
- shown(default)⊆shown(full)；budget_* 与 S8 一致
```
**反例**：只统计节点数；抑制无规则统计；一跳违规不测；default/full 不同源；随机指标。
**边界**：空帧；全抑制（除 MANDATORY）；full 超预算；多归属；无簇。
**U 映射**：U-3、U-16、U-18、U-32、U-34。
**建议裁决**：采纳指标/G6/确定性；数值 S8。
**证据等级**：A（U-32；S3-11/S3-12；`ENGINEERING-PLAN.md:660` P5）；**本项目假设**（指标字段/门禁）。

---

## 13. 覆盖矩阵

| U# | 要点 | S4 落点 |
|---|---|---|
| U-5 | 默认非全展开/可见非最小粒度 | S4-1/S4-2/S4-8 |
| U-15 | 深入后语义边挂接一跳 | S4-3/S4-6 |
| U-16 | 全量→选择性渲染 | S4-1/S4-2/S4-4 |
| U-17 | 背后图不带入 | S4-3/S4-5 |
| U-18 | 限制跳数 | S4-2/S4-3/S4-5/S4-12 |
| U-19 | 一跳节点 KP/簇 | S4-3/S4-5 |
| U-21 | 多归属/返回 | S4-5/S4-11 |
| U-22 | 新一跳 vs 更深 | S4-3/S4-5/S4-10 |
| U-27 | 边存无/类型 | S4-4 |
| U-28 | 最小粒度 KP | S4-7 |
| U-31 | 多归属不设上限 | S4-11 |
| S0 | S0-5/S0-6/S0-8/S0-9 | S4-3/S4-4/S4-8/S4-10 |
| S1 | H/A/new_hop/present | S4-3/S4-6 |
| S2 | 簇/run/无簇/A 不改簇 | S4-7/S4-11 |
| S3 | presence/预算归属/VM | S4-9/S4-10 |

---

## 14. A-v2 变更表（逐条旧→新，含 v1 行号）

> 旧文件：`S4-render-proposal-A.md`（v1 `ba11c990…`）；行号可 grep 复核。

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S4-2（L63）tier0=focus+整层可见块；预算不足整屏失败 | MANDATORY={focus}/H focus+children(cap)；仅 MANDATORY 超预算才失败（§2） | R-S4-3 |
| 2 | S4-3（L107）F=基座集（可能整层） | F={focus}；one_hop 定义/不闭包/机检 base(F)=={focus}（§3） | R-S4-1 |
| 3 | S4-2 tier2=与 tier0/1 相邻（可 2 跳） | tier2 只含基座+H 同层节点；max_hop(shown)≤hop_budget（§2/§5） | R-S4-2 |
| 4 | S4-4（L143）rule_id 枚举/unknown 面模糊 | 11 类统一；unknown 仅 4 类；unknown≠无关系（§4） | R-S4-5 |
| 5 | S4-9（L302）VM 主要"选择后"（B 只 shown） | VM/AdmissionResult 携带全部候选节点/边 presence+rule_id；Renderer only shown（§9） | R-S4-4 |
| 6 | S4-2 排序键未含 relation_class | 冻结 `(tier,hop,relation_class,label_rank,canonical_id)`；class 顺序（§2） | R-S4-6 |
| 7 | S4-8（L274）full 放宽 relation/hop 可能被读成 raw | `relation_scope=candidate_scope`；同 Admission；subset/硬上限（§8） | R-S4-7 |
| 8 | S4-5（L187）无 focus 一跳约束 | 一跳端点只显示；2 跳仅 S5；不带背后图（§5） | R-S4-1/2 |
| 9 | S4-10（L331）S5 边界 | 保留；补 focus-only 输入/纯函数（§10） | R-S4-1/8 |
| 10 | S4-11（L357）S1/S2 一致 | 保留；补无簇不伪造/多归属（§11） | R-S4-8 |
| 11 | S4-12（L384）指标 | 补 candidate/mandatory/presence/rule_id 直方图、max_hop、subset（§12） | R-S4-8 |
| 12 | 覆盖矩阵 §13 | 更新（§13） | 本轮 |

---

## 15. 仍存争议 / 待 Lead·SE 裁决

1. **节点 presence 的 VM 载体 vs S3 白名单**：R-S4-4 要求 VM 携带全部候选**节点/边** presence+rule_id；S3-v1 节点白名单未含 presence/rule_id。本提案要求 S6a/S3 增字段；若严格不改 S3，则 VM 仅全候选边 + shown 节点，节点决策留在 AdmissionResult（需 Lead 裁）。
2. **MANDATORY_CONTEXT_CAP=20 的具体值**：影响 |MANDATORY| 上限与 S8 max_nodes 下限；需 S8/Lead 定。
3. **tier2 是否默认启用**：本提案默认 `include_level_context=false`（tier2 空）；若启用 H 同层上下文，需定义其边/排序。
4. **`invalid.data` 归 unknown**：R-S4-5 明确列入 unknown；但非法数据也可能应 fail-visible（整帧错误）；本提案按 unknown 并记录，需 SE 确认。
5. **full 的 candidate_scope 由 P4/S9 生成**：如何保证 full 候选 ⊇ default 候选需 S9 接口保证；S4 只做子集断言。

---

## 16. 证据锚

```text
裁决：S4-RULINGS.md:10-16（复核）、:17-54（R-S4-1..8）、:56-68（修订轮/门禁）
原话：vision.md:22（U-5）、:32-36（U-15..U-19）、:38-39（U-21/U-22）、:66-67（U-27/U-28）、:70（U-31）
S0：S0-terms-v1.md:49-54（S0-5）、:56-61（S0-6/R-3）、:69-73（S0-8）、:75-79（S0-9）
S1：S1-dimensions-v1.md:57-67（H/A/new_hop）、:99-107（present/VM）
S2：S2-clustering-v1.md:17（簇）、:64-71（S2-10/11）、:73-76（无簇）
S3：S3-visual-v1.md:36-39（presence）、:66-69（预算）、:71-75（VM 白名单）
工程：ENGINEERING-PLAN.md:583,660（P5）、:912-916（ST-12..16）、:224-250（VM）
代码（反例/现状）：graph-engine.js:179-180；graph-view-2d.js:634-663；app.js:1845
```
