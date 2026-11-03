# S4 选择性渲染 / 一跳 / 边存无提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S4-RULINGS.md`（R-S4-1..R-S4-8）；最高原话 `multilevel-graph-vision.md`；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`），不得违反。
> **输入**：B v1（`4d3e0dd8…`）、A v1（`ba11c990…`）、`S4-objections.md`。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S4-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S4-RULINGS/S0/S1/S2/S3 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S4）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S4-1/S4-4/S4-9 | VM 只含 shown；suppressed/unknown 仅计数 | **吸收 A 候选边模型**：VM 带全部候选节点/边 + 逐条 `presence/rule_id`；Renderer 只渲染 shown；suppressed/unknown 保留供审计（R-S4-4） | 修正 |
| 2 | S4-3/S4-5 | focus 一跳（B 已较严） | **冻结 F={focus}**；`one_hop(F)` 只从 focus 出发；不带背后图；不闭包（R-S4-1） | 确认/强化 |
| 3 | S4-2 | sort key 无 tier/relation_class | **排序键 `(tier,hop,relation_class,label_rank,canonical_id)`**；`relation_class` 顺序 semantic<structural<navigation<reference；label_rank 确定性字符串；tier2 不含一跳端点邻居（R-S4-2/R-S4-6） | 修正 |
| 4 | S4-2 | 无最小必选集；预算不足可能抑制 focus | **MANDATORY 最小必选集**（focus+必要上下文，有上限）；其余 suppressed；仅 MANDATORY 超预算才 `S4_BUDGET_INVALID`；S8 保证 `max_nodes≥|MANDATORY|` 上界（R-S4-3） | 修正 |
| 5 | S4-4 | rule_id 枚举不全 | **统一 A 的 11 类 rule_id**；unknown 只在 `endpoint.unresolved/source.unavailable/admission.undecided/invalid.data`；unknown≠无关系（R-S4-5） | 并集 |
| 6 | S4-8 | candidate_scope 未明确 | 全展开同一 Admission/present；`candidate_scope`（不是 raw data edges 直出）；subset；full 仍受 S8 硬上限（R-S4-7） | 修正 |
| 7 | S4-9/S4-12 | aggregate_count/G6 字段较简 | **aggregate_count 不遍历 data_edge_ids**；统一 G6 字段（rule_id 直方图/hop/closure/behind/subset/deterministic sha）（R-S4-8） | 并集 |

---

## 0.1 覆盖矩阵（U + S0–S3）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-5 | 默认非全展开=S4-1/S4-8 | U-15 | 一跳=S4-3 |
| U-16 | 选择性渲染=S4-1/S4-2 | U-17 | 背后图不带入=S4-3/S4-5 |
| U-18 | 防多跳=S4-2/S4-3 | U-19 | 点击/事件=S4-10 |
| U-21 | 多归属=S4-11 | U-22 | 新一跳/更深=S4-5 |
| U-27 | 边存无/类型=S4-4 | U-28 | 最小粒度=S4-7 |
| U-31 | 多归属上限=S4-11 | U-32 | 规模/预算=S4-2/S4-12 |
| S0-5/S0-6 | 一跳/presence | S1 H/A | 维度接入=S4-6/S4-11 |
| S2 | 簇/run/多归属 | S3 | VM/presence/Renderer=S4-9 |

---

## S4-1 选择性渲染定义与边界（唯一裁剪者）

**规则**：S4 Admission 在 `(CandidateSet, ctx, budget)` 上为**全部候选节点/边**判定 `presence ∈ {shown,suppressed,unknown}` + `rule_id`，输出 VM；VM **携带全部候选**（不是只 shown），Renderer 只渲染 `presence=shown`，不裁剪/不丢弃。选择性只改 presence/选择，不改事实/type/label/簇。
**形式化/机检**：
```
VM.nodes = all candidate nodes（含 shown/suppressed/unknown；带 presence/rule_id）
VM.edges = all candidate edges（逐条 presence/rule_id）
Renderer renders {e|presence=shown}
S4 sole producer of presence/suppressed/rule_id；Renderer 无裁剪
```
**反例**：VM 只含 shown（B v1，作废）；Renderer 二次裁剪；S4 改 type/label/DataSource；全量数据直出绕过 present。
**边界**：候选为空；预算 0；全展开；unknown 多；簇/KP 混合。
**U 映射**：U-5、U-16、U-27。
**建议裁决**：冻结候选边模型/逐条 presence/rule_id/S4 唯一裁剪/Renderer 只画 shown。
**证据等级**：A（S3-12/S3-5/S0-6；R-S4-4）+ R。

---

## S4-2 预算内选点规则（MANDATORY/排序/tie-break/降级）

**MANDATORY 最小必选集（R-S4-3）**：
```
MANDATORY = {focus} ∪ {current-level cluster containing focus（若当前层以 cluster 呈现且存在）}
|MANDATORY| ≤ M_max（M_max 为小常数，S8 配置；建议 2）
MANDATORY 必选；S8 保证 max_nodes ≥ |MANDATORY| 上界（max_nodes≥M_max）
其余候选按排序键填充剩余预算；未选 ⇒ suppressed + rule_id
仅当 |MANDATORY| > max_nodes ⇒ S4_BUDGET_INVALID（fail-visible，不部分渲染）
```
**排序键（R-S4-6 冻结）**：
```
node sort key = (tier asc, hop asc, relation_class asc, label_rank asc, canonical_id asc)
  tier: 0=MANDATORY, 1=focus 一跳端点, 2=H 同层结构节点/基座上下文（不含一跳端点的邻居）
  hop: 0=focus,1=一跳；tier2 H 节点 hop=0/层内
  relation_class: semantic(0) < structural(1) < navigation(2) < reference(3)
  label_rank: 确定性字符串（label 的 Unicode/canonical 序；缺失用 canonical id）
  canonical_id: 最终 tie-break
edge sort key = (tier asc, hop asc, relation_class asc, label_rank asc, canonical_edge_id asc)
  edge tier: 0=MANDATORY 关联/base 边, 1=一跳边, 2=其他候选
```
**选边**：
```
候选边 = CandidateSet 中符合维度/方向/层/跳的边（包含端点未选中的候选）
先选端点均 shown 且 tier/键靠前的边；取 max_edges；其余 suppressed(edge.budget)
任一端未 shown ⇒ suppressed(node.budget)（候选仍保留在 VM）
```
**显式降级**：`suppressed` 全部带 rule_id；`degraded=true` 统计；不静默丢；`S4_BUDGET_INVALID` 仅 MANDATORY 超预算。
**机检**：
```python
assert MANDATORY enumerable, |MANDATORY|<=M_max
assert max_nodes>=M_max (S8 guarantee)
assert shown_nodes = MANDATORY ∪ top(rest,key) within budget
assert all non-shown candidates presence=suppressed/unknown + rule_id
assert sort key deterministic; two runs byte same
assert shown_edges have shown endpoints; candidates retained in VM
```
**反例**：tier2 包含一跳端点邻居（2 跳）；按插入序选；MANDATORY 被预算挤掉；超预算静默丢；边端点未选仍画 shown。
**边界**：MANDATORY 恰好满；预算 0（MANDATORY>0 ⇒ fail）；同分 tie；边预算 0；全展开预算更大。
**U 映射**：U-5、U-16、U-18、U-32。
**建议裁决**：冻结 MANDATORY/排序键/tie-break/显式 suppressed/仅 MANDATORY 失败；S8 保证 max≥M_max。
**证据等级**：A（S3-11 预算；S0-6；R-S4-3/R-S4-6）+ PI（M_max/排序细则）。

---

## S4-3 一跳挂接（F={focus}；不闭包/不带背后图）

**规则**：默认 `hop_budget=1`；`F={focus}`；`one_hop(F) = {v | ∃e∈E_relation(D), e 连接 F↔v（dir 合法）, v∉F}`；每个端点最多一条边进入（同 endpoint 多类型边分别保留）；只取端点 + 这条边，不递归/不闭包/不带端点背后图；H 的 drill 是 S5 导航，不是 A 一跳。
**形式化/机检**：
```
F = {focus}
one_hop(F) 只从 focus 出发；v 距离==1
shown 候选 hop <= hop_budget；默认 1；2 跳仅 S5 new_hop
端点 kind∈{kp,cluster}；cluster 不展开成员
H：无关系 hop；H 直接子块由 H base 结构边（S1），不是 A one_hop
```
**机检**：
```python
assert F == {focus}
assert all(hop(v)<=hop_budget for shown)
assert all(hop(v)==1 for one_hop additions unless new_hop)
assert no edge to neighbor-of-neighbor (tier2 doesn't include)
assert no cluster.members expansion
```
**反例**：F=整层可见块（A v1 P1-1）；BFS 2 跳；把邻居全部边带入；A 自动扩展邻域；H 下钻当 A 跳。
**边界**：focus=cluster；端点 cluster/kp；方向；无邻居；同 endpoint 多边；2 跳显式。
**U 映射**：U-15、U-17、U-18、U-22。
**建议裁决**：冻结 F={focus}、一跳恰好一条 `E_relation(D)` 边、不闭包/不带背后图；2 跳仅 S5。
**证据等级**：A（S0-5/S1-5；U-17；R-S4-1/R-S4-2）+ R。

---

## S4-4 边「存无」与 presence 三值（11 类 rule_id）

**规则**：候选边逐条判 presence；存在性由数据/类型决定（U-27）；presence 三值 + rule_id；unknown≠无关系；类型独立。
**rule_id 11 类（R-S4-5 统一 A）**：
| rule_id | 语义 | presence |
|---|---|---|
| `dimension.sources` | 边类型不在本维度 relation_sources | suppressed |
| `dimension.direction` | 方向过滤 | suppressed |
| `level.cross_layer` | 跨层边当前层不可见 | suppressed |
| `hop.budget` | 跳数超 hop_budget | suppressed |
| `node.budget` | 端点节点被预算排除 | suppressed |
| `edge.budget` | 边预算耗尽 | suppressed |
| `cluster.folded` | 端点/边折叠进簇 | suppressed |
| `endpoint.unresolved` | 端点数据不完整/找不到 | unknown |
| `source.unavailable` | 关系源未加载/不可用 | unknown |
| `admission.undecided` | 规则输入未计算（缓存/stale） | unknown |
| `invalid.data` | 边数据非法（自环/缺端点） | unknown（fail-visible） |
**unknown 触发面**：仅 `endpoint.unresolved/source.unavailable/admission.undecided/invalid.data`；unknown 不渲染、不表示"无关系"；可重试/显示检查器。
**机检**：
```python
assert presence∈{shown,suppressed,unknown}; !=shown ⇒ rule_id in 11
assert suppressed ⇒ edge exists in CandidateSet/data
assert unknown ⇒ rule_id in unknown set; not interpreted as no-edge
assert same pair multi-type edges independent; no type/label mutation
```
**反例**：unknown 当无关系；suppressed 与 unknown 混淆；同对多类型合并；invalid.data 当 suppressed；自由文本 rule_id。
**边界**：同对多类型；端点 unknown；cluster folded；H/A；全展开仍 present。
**U 映射**：U-16、U-17、U-27。
**建议裁决**：冻结 11 类/三值/unknown 触发面/unknown≠无关系/类型独立。
**证据等级**：A（S0-6/S3-5；R-S4-5）+ R。

---

## S4-5 背后图不带入 / 2 跳仅 S5

**规则**：一跳端点只是当前帧可见节点；成为新焦点必须 S5 新 frame；S4 不自动展开其背后图；2 跳仅 `new_hop=true`（S5 EXPLICIT_NEW_HOP）；每次 frame 重置 hop/预算；跨层非 H 边 suppressed，不自动带入。
**形式化/机检**：
```
click(neighbor) -> S5 new frame（focus=neighbor, hop=1 default）
S4 no nav state/cache/closure
assert hop_budget==1 unless ctx.new_hop
assert no neighbor background; no closure
assert new frame resets
```
**反例**：点击自动展开邻域；2 跳默认；缓存上一步继续扩；跨层边混入；多归属展开全部族。
**边界**：2 跳显式；多归属；跨层；drill 后新焦点。
**U 映射**：U-7、U-17、U-19、U-21、U-22。
**建议裁决**：冻结端点只作可见节点/新焦点由 S5；2 跳仅 S5；frame 重置。
**证据等级**：A（S0-5/S1-5；S5 边界；R-S4-2）+ R。

---

## S4-6 维度接入（只改 presence）

**规则**：`ctx.dimension_id`（S1 注册表 active）决定候选/方向/hop/base 结构；维度只改 presence，不改 type/label/contain_kind/簇成员；H 无关系 hop；A 1/2 跳；未知/保留/弃用维度 fail-closed；切换维度新建 frame。
**形式化/机检**：
```
H: focus block + H base 结构边；无 A one_hop
A: focus + E_relation(A) 一跳；hop default 1；2 only new_hop
dimension switch -> new frame; no data mutation; no cluster recompute
assert type/label/kind unchanged across dimension
```
**反例**：维度改 edge type；A 下重算簇；H 用关系闭包；维度写事实；reserved 维度可用。
**边界**：H 叶层；A 无边；维度与 full 正交；跨族多归属。
**U 映射**：U-8、U-9、U-10、U-11、U-12、U-30。
**建议裁决**：冻结维度只改 presence/H-A 输入/fail-closed；不改事实。
**证据等级**：A（S1 H/A/D-4；S2 A 不变簇）+ R。

---

## S4-7 层次与一跳交互（drill 重置）

**规则**：S5 drill 到下一层生成新 frame：level+1/focus=被展开簇/hop=1/new_hop=false/预算按新 frame；S4 只读 S2 `(level,view_family)` run，不重算簇；跨层只有 H 父子结构边显示；其他跨层边 suppressed(level.cross_layer)。
**形式化/机检**：
```python
drill -> new frame; assert hop reset; assert focus in new level partition
assert S2 run keyed by (level,view_family); no recompute
assert cross-layer non-H edge suppressed; H edges data_edge_ids audit
assert run state not in VM
```
**反例**：drill 后旧 hop/邻居残留；跨层 reference 混入；S4 重算簇；run 进 VM；重点不在新层。
**边界**：叶层；无子簇 degenerate；H 跨层边空集；多归属。
**U 映射**：U-5、U-7、U-18、U-28。
**建议裁决**：冻结 drill 新 frame/hop 重置/跨层规则/run 只读不进 VM。
**证据等级**：A（S1/S2；S3 level）+ R。

---

## S4-8 全展开模式（同一 Admission/present；candidate_scope）

**规则**：全展开与默认同一 DataSource/同一 Admission/present；`ctx_full.candidate_scope = all_data_edges`（**候选范围**，不是 raw data edges 直出）；`shown(default) ⊆ shown(full)`；full 仍受 S8 硬上限，超限显式失败/降级；不得第二数据源/第二 builder。
**形式化/机检**：
```
ctx_full = ctx with mode=full, candidate_scope=all_data_edges,
           hop_budget=FULL_MAX（S8）, budget_full
same Admission/present/rule_id enum
assert CandidateSet(default) ⊆ CandidateSet(full)
assert budget_full.max_nodes >= budget_default.max_nodes (hard cap S8)
assert shown(default) ⊆ shown(full)
assert no raw edge path/second source
```
**反例**：full 直接画 DataSource.edges；第二数据源；full budget 更小导致 default 边消失；full 绕过 present；full 无硬上限。
**边界**：默认=full；full 仍 suppressed/unknown；budget 硬上限；candidate_scope 仅候选范围。
**U 映射**：U-5、U-16、U-26、U-27。
**建议裁决**：冻结同 Admission/present、candidate_scope、subset、硬上限；禁止 raw 直出/第二源。
**证据等级**：A（S0-6/S0-8；S3-9；R-S4-7）+ R。

---

## S4-9 与 S3 契约

**规则**：S4 输出 VM（S3 白名单）带全部候选节点/边 + presence/rule_id；Renderer 只渲染 shown、只校验；`RENDER_BUDGET_EXCEEDED` 仅 VM 超 S3 硬上限时；S4 与 S3/S8 预算同源；`aggregate_count` 由取景层显式给，不遍历 `data_edge_ids`；`data_edge_ids` 仅审计、Renderer 禁读。
**形式化/机检**：
```python
VM.nodes/edges = all candidates + presence/rule_id
Renderer renders shown only; no trim
S4 max == Renderer.getCapabilities().maxNodes/maxEdges (same config sha)
aggregate_count explicitly supplied; no traversal data_edge_ids
VM <= hard max (S4 normal path); else Renderer fail
```
**反例**：S4 输出超预算让 Renderer 裁；Renderer 改 presence；aggregate_count 遍历内部 id；data_edge_ids 进 Renderer；两套 max。
**边界**：空 VM；预算 0；decayed；聚合边 data_edge_ids 审计；H 空集。
**U 映射**：U-3、U-16、U-27、U-33。
**建议裁决**：冻结候选 VM/presence/rule_id/预算同源/Renderer 只校验/aggregate_count 显式。
**证据等级**：A（S3-11/S3-12；R-S4-4/R-S4-8）+ R。

---

## S4-10 与 S5 导航边界

**规则**：S4 纯取景函数：输入 frame_spec（focus/hop/new_hop 等），输出 VM；不保存 focus/selection/nav/history；事件 Renderer→S5；S5 生成新 frame；S4 无导航状态机。
**形式化/机检**：
```python
assert VM no focus/selection/nav/history/mode
assert S4 no state; same frame_spec => same VM
events -> S5; new_hop only S5
```
**反例**：S4 保存 focus/历史；VM 带 nav；Renderer 直接导航；S4 处理返回/切换。
**边界**：KP click/簇 click/background；2 跳；drill。
**U 映射**：U-7、U-19、U-21、U-22。
**建议裁决**：冻结 S4 纯取景/S5 导航/focus 只输入。
**证据等级**：A（S0-9/S3-7）+ R。

---

## S4-11 与 S1/S2 一致性

**规则**：presence 不改 type/label/contain_kind/kind/簇成员；A 不改簇；多归属按当前 view_family；run/簇状态不进 VM；一跳按 S1 维度；S2 partition 不被改写。
**形式化/机检**：
```python
assert fields unchanged; clusters unchanged; multi-belonging preserved
assert VM no run/dendrogram/membership
assert one-hop uses E(D); S2 partition intact
```
**反例**：presence 改类型；A 重算簇；VM 带 run；S4 改 membership；丢多归属。
**边界**：多类型边；多归属节点；无簇；A/H 切换。
**U 映射**：U-1、U-10、U-21、U-27、U-31。
**建议裁决**：冻结只改 presence/A 不变簇/run 不进 VM/多归属不变。
**证据等级**：A（S1/S2 冻结）+ R。

---

## S4-12 度量与验收（G6 统一）

**规则**：每帧指标 + G6：shown/suppressed/unknown 节点/边计数、rule_id 直方图、抑制率、hop_max、`closure_violations=0`、`behind_graph_leak=0`、`deterministic_sha256`、`budget`、`subset_ok`（default/full）、`candidate_scope`、`degraded`；可复跑。
**形式化/机检**：
```python
metrics = {shown/suppressed/unknown counts, rule_id_histogram,
           suppression_ratio, hop_max, closure_violations, behind_graph_leak,
           deterministic_sha256, budget, subset_ok, candidate_scope, degraded}
G6 fields: edition/corpus_manifest, level/view_family/dimension/focus/hop/new_hop/mode,
           candidate_scope, budget, counts, rule_id hist, deterministic_sha,
           subset_ok, s2_run_id?（仅输入标识，不进 VM）
assert closure/behind ==0; deterministic 2x; rule histogram enumerable
```
**反例**：只报 shown；rule_id 直方图缺失；不测 hop/closure；default/full 不同源；G6 缺预算/scope。
**边界**：空帧；全抑制；unknown 多；full 超预算。
**U 映射**：U-3、U-16、U-18、U-32、U-34。
**建议裁决**：冻结指标/G6 字段/确定性/closure/behind/subset；数值门禁 S8。
**证据等级**：A（S3-12；U-32）+ PI（字段）。

---

## 附：R-S4 自检（8 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S4-1 focus 一跳 F={focus} | S4-3（F={focus}；只 focus 边；无背后图） |
| R-S4-2 无隐式 2 跳 | S4-2/S4-3（tier2 不含一跳邻居；max_hop≤hop_budget；2 跳仅 S5） |
| R-S4-3 MANDATORY/预算降级 | S4-2（MANDATORY；其余 suppressed；仅 MANDATORY 超预算失败；S8 保证） |
| R-S4-4 VM 候选边模型 | S4-1/S4-9（全部候选 + presence/rule_id；Renderer 只 shown） |
| R-S4-5 11 类 rule_id/unknown | S4-4（11 类表；unknown 四类触发；unknown≠无关系） |
| R-S4-6 排序键 | S4-2（tier/hop/relation_class/label_rank/canonical_id；relation_class 顺序） |
| R-S4-7 全展开 | S4-8（同 Admission/present；candidate_scope；subset；硬上限） |
| R-S4-8 并集 | S4-9/S4-12（aggregate_count 不遍历 data_edge_ids；G6 统一） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S4-objections-v2.md`；未写产品代码/契约，未 commit。
