# S4 选择性渲染 / 一跳 / 边存无提案 B（独立复核方）

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`），不得违反；本场 `S4-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S4-render-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S4-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0/S1/S2/S3 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. 总原则（S4 不得改 S0–S3）

1. **S4 是 presence/选点/裁剪的唯一决策者**；输出 ViewModel（含 `presence/rule_id`）。Renderer 只校验/渲染，不裁剪（S3 R-S3-2）。
2. 选择性只改 **presence/selection**，不改 DataSource、type、label、contain_kind、kind、簇成员（S0-6/S1/S2）。
3. 默认一跳 = **恰好一条 `E_relation(D)` 边**，不闭包、不带背后图；2 跳只能 S5 显式 `EXPLICIT_NEW_HOP`（S0-5/S1）。
4. presence 三值语义严格区分：`shown`（选择且可见）、`suppressed`（存在但被预算/方向/层过滤）、`unknown`（数据/维度不可判定）；三者都有可枚举 `rule_id`；unknown ≠ suppressed。
5. 全展开与默认同一 DataSource/同一 `present`；`shown(default) ⊆ shown(full)` 可机检；不得第二数据源。
6. VM 纯：无 focus/selection/navigation/history/mode/cluster run/dendrogram（S0 D-4/S1 D-4/S2/S3）。
7. 选点/tie-break/预算/输出确定性：同 `(VM input, ctx, budget)` ⇒ 唯一 presence 结果；超预算显式降级，不静默丢。

### 0.1 覆盖矩阵（U + S0–S3）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-5 | 默认非全展开=S4-1/S4-8 | U-15 | 一跳=S4-3 |
| U-16 | 选择性渲染=S4-1/S4-2 | U-17 | 背后图不带入=S4-5 |
| U-18 | 防多跳=S4-3/S4-5 | U-19 | 点击/事件=S4-10 |
| U-21 | 多归属=S4-11 | U-22 | 新一跳/更深=S4-5 |
| U-27 | 边存无/类型=S4-4 | U-28 | 最小粒度=S4-7 |
| U-31 | 多归属上限=S4-11 | U-32 | 规模/预算=S4-2/S4-12 |
| S0-5/S0-6 | 一跳/presence | S1 H/A | 维度接入=S4-6/S4-11 |
| S2 | 簇/run/多归属 | S3 | VM/presence/Renderer=S4-9 |

---

## S4-1 选择性渲染定义与边界

**规则**：选择性渲染 = 在给定 `(DataSource, level, view_family, frame_spec, budget)` 下，S4 对候选节点/边计算 `presence ∈ {shown,suppressed,unknown}`，只把 `shown` 节点/边写入 ViewModel；不是全量渲染，不是渲染器裁剪；只改投影，不改事实。
**形式化/机检**：
```
view = select(DataSource, ctx, budget) -> VM
VM.nodes/edges 只含 shown；suppressed/unknown 记录在 VM.suppressed_counts?/audit（不出现在渲染集合）
assert S4 is sole producer of presence/rule_id
assert Renderer does not compute/trim presence
assert presence ∈ {shown,suppressed,unknown}; rule_id required when != shown
assert same input => same presence
```
**反例**：Renderer 先收全量再裁剪；S4 只标 shown 不记录 suppressed；把全量数据塞 VM 让 Renderer 选；选择性改 type/label/DataSource。
**边界**：空图/单节点；预算=0；全展开（S4-8）；unknown 源不可用；簇节点与 KP 混合。
**U 映射**：U-5、U-16、U-27。
**建议裁决**：冻结 S4 唯一裁剪者、presence 三值、只改投影；Renderer 不裁剪。
**证据等级**：A（S3 R-S3-2 冻结；S0-6）+ R。

---

## S4-2 预算内选点规则（确定性/tie-break/降级）

**规则**：预算 `max_nodes/max_edges` 与 S3/S8 同源（S8 定值，S3 字段）；S4 用**确定性优先级**选点/选边，超预算显式 `suppressed + rule_id`；不静默丢、不按时间/随机。
**选点优先级（可复算）**：
```
focus 节点（若在当前层）优先：is_focus = 1
hop 距离：hop（focus=0，一跳=1；2 跳仅 S5 显式）
kind rank：cluster=0, kp=1（簇承载更多成员，默认视图优先保留）
semantic_degree（当前候选边集中 label=semantic 的连接数，降序；无 semantic 边则为 0）
canonical_id 升序（最终 tie-break）
sort key = (is_focus desc, hop asc, kind_rank asc, semantic_degree desc, canonical_id asc)
取前 max_nodes ⇒ shown；其余 suppressed(rule_id=node.budget)
```
**选边优先级**：
```
仅候选边（S4-3/4/5；见 S4-4 类型存在性）
endpoint 均 shown；优先 internal/base 边（两端均 shown 且属于当前层/簇），再 one-hop 边
sort key = (both_endpoints_shown desc, is_base_edge desc, hop asc, display_type rank, canonical_edge_id asc)
取前 max_edges ⇒ shown；其余 suppressed(rule_id=edge.budget)
任一端 suppressed ⇒ edge suppressed(rule_id=edge.endpoint)；不得显示悬空边
```
**降级**：预算不足 ⇒ 显式 `suppressed` + `rule_id`；`degraded=true`/统计字段；不得降低 presence 语义、不得改数据。
**机检**：
```python
assert sort key deterministic; tie-break canonical id
assert shown_nodes == first max_nodes; rest suppressed with rule_id
assert shown_edges == first max_edges of eligible; endpoint shown
assert same input => same output; no random/time
assert suppressed counts 可枚举；degraded 显式
```
**反例**：按渲染顺序/哈希/随机选；超预算静默丢；只记录 shown 不记录 suppressed；边端点被抑制仍画悬空边；优先级依赖未冻结的语义权重。
**边界**：max_nodes=0；focus 不在候选；同分 tie；边预算小于节点预算；全展开预算更大（S4-8）。
**U 映射**：U-16、U-18、U-32。
**建议裁决**：冻结优先级/tie-break/显示规则/显式降级；max 值 S8，S3/S4 同源。
**证据等级**：A（S3 R-S3-2/S3-11；S0-6）+ PI（优先级权重）。

---

## S4-3 一跳挂接（严格一条边）

**规则**：默认 `hop_budget=1`：从 focus 出发，沿 `E_relation(D)`（S1 维度定义）**恰好一条**边取邻居；节点 = focus + 邻居；边 = focus 关联的这条边 + 当前层的 base/H 派生边；**不闭包、不取邻居的邻居、不带邻居的背后边**；2 跳仅 S5 显式 `EXPLICIT_NEW_HOP`（U-22）。
**形式化**：
```
D = ctx.dimension_id；E(D)=E_relation(D)（H 时无关系边，使用 H base 边，见 S4-6）
candidates = {v | ∃e∈E(D), e 连接 focus↔v, dir 合法}
one_hop_edges = {e∈E(D) | focus∈endpoints(e), dir 合法}
shown_nodes = {focus} ∪ candidates（受预算）
shown_edges = one_hop_edges ∪ H base edges within current view（受预算）
禁止：distance(focus,v)>1 的节点/边；neighbor 之间的边；邻居的其余邻接（背后图）
2 跳：仅 ctx.new_hop==true 时 hop_budget=2；否则 hop>1 ⇒ fail-closed/自动降级到 1（显式记录，不静默）
```
**机检**：
```python
assert every added node has exactly one E(D) edge to focus (or H child edge)
assert no shown edge with both endpoints ∉ {focus} ∪ one-hop（除 base/H 边）
assert hop(v)<=1 unless ctx.new_hop
assert no transitive closure/back-of-neighbor edges
```
**反例**：BFS 到 2 跳/闭包；把邻居的全部边带入；A 维自动展开邻居邻域；H 下钻时把整棵子树带入（应由 S5 逐层）。
**边界**：focus=cluster；邻居是 cluster/kp；方向 out/in/both；A/H；无 E(D) 边；同一 neighbor 多边去重（节点去重，边按 id）；2 跳显式。
**U 映射**：U-15、U-17、U-18、U-22。
**建议裁决**：冻结"一跳=恰好一条 `E_relation(D)` 边、不闭包/不带背后图；2 跳仅 S5 显式"。
**证据等级**：A（S0-5/S1-5 冻结；U-17/U-18）+ R。

---

## S4-4 边「存无」与 presence 三值

**规则**：边的存在性由 **DataSource 的边类型/来源**决定（U-27）；S4 只判定其在当前 view 的 presence：
- `shown`：边存在、端点均 shown、在预算/方向/层内、类型允许；
- `suppressed`：边存在但被预算/端点/方向/层过滤（**存在但未显示**）；
- `unknown`：无法判定是否存在/来源不可用/维度未解析（**不是不存在**，也不是 suppressed）；
`rule_id` 必须可枚举；unknown 与 suppressed 不得混淆；不得用视觉/字段把 unknown 当"没有边"。
**形式化/rule_id**：
```
rule_id enum（v1 建议）:
  node.budget / edge.budget / edge.endpoint / direction.filter / level.filter /
  hop.budget / cluster.folded / source.unavailable / dim.unresolved / edge.unknown
existence:
  data edge exists => shown/suppressed 可判定
  provenance missing/derived unavailable => unknown(source.unavailable)
  dimension/unresolved => unknown(dim.unresolved)
  reference/structural/extend type 不改变存在性；只影响显示 token/是否参与选择
assert unknown != suppressed; unknown 不能归入 "不存在"
```
**机检**：
```python
assert presence ∈ {shown,suppressed,unknown}
assert presence != shown => rule_id in enum
assert suppressed implies edge exists in DataSource/derived scope
assert unknown implies not_decidable (source/dim unavailable), not just filtered
assert edge type/label not changed by presence
```
**反例**：把 source unavailable 标 suppressed（把未知当不存在）；把 reference 边当 semantic 显示；unknown 画成没有边；suppressed 边可 click；rule_id 空/自由文本。
**边界**：同 pair 多类型边；endpoint unknown；cluster folded edge；H 派生边；A 一跳；全展开仍受 type/present。
**U 映射**：U-16、U-17、U-27。
**建议裁决**：冻结 presence 三值/rule_id 枚举/unknown≠suppressed/类型决定存在性；不得改 type。
**证据等级**：A（S0-6/S3-5/U-27）+ R。

---

## S4-5 背后图不带入 / 2 跳仅 S5

**规则**：一跳端点作为新焦点时，**不自动**带入其背后图；只有 S5 显式新一跳（`EXPLICIT_NEW_HOP`）才用 2 跳；每次新 frame 重新计算 hop/预算；禁止 S4 内缓存闭包/自动扩展。
**形式化**：
```
on nodeClick(neighbor) -> S5 frame(focus=neighbor, hop_budget=1) (new frame)
if ctx.new_hop: hop_budget=2（仅显式动作）；否则 1
S4 无导航状态/无历史；不自动 BFS
多归属/跨层端点：只取当前 view_family/level 的一跳边；跨族不自动带入
```
**机检**：
```python
assert S4 has no navigation state/history
assert hop_budget==1 unless ctx.new_hop
assert no transitive closure persisted; no neighbor background
assert new focus frame resets hop/budget
```
**反例**：一键展开整个邻域；缓存上一步邻居继续扩；S4 自己处理新一跳；跨层边自动带入。
**边界**：2 跳显式；多归属节点；跨层边；drill 后新焦点。
**U 映射**：U-17、U-18、U-22。
**建议裁决**：冻结不自动背后图、2 跳仅 S5 显式、frame 重置。
**证据等级**：A（S0-5/S1-5；S5 边界）+ R。

---

## S4-6 维度接入（H/A 只改 presence）

**规则**：`ctx.dimension_id` 决定 `E_relation(D)`/H base 边与 selection；维度只改**取景/presence**，不改 DataSource/type/label/cluster 成员；H 用层次 base 边（S1 H 无 hop）；A 用关系扩展（E_relation_min + 一跳）；维度切换只重建 frame/VM，不写事实。
**形式化**：
```
H: focus block + children/base H edges；无关系 hop；drill 由 S5
A: H base view + E_relation(A) one-hop from focus; hop=1 default
dimension switch: new frame; S4 recalculates presence; no data mutation
assert dimension does not change type/label/cluster membership
```
**机检**：同一 DataSource 下切换维度只 presence 变化；type/label/簇成员不变；H/A 不混；`dimension_id` 只 ctx；A 不改变 S2 cluster run。
**反例**：维度切换改 edge type；A 下重算簇；H 用 hop 闭包；维度写入产品数据。
**边界**：H 叶层；A 无 E 边；维度 reserved/unknown fail-closed；跨族多归属。
**U 映射**：U-8、U-10、U-21、U-22、U-30。
**建议裁决**：冻结维度只改 presence、H/A 输入不同、切换只重建 frame；不改事实。
**证据等级**：A（S1 H/A/D-4；S2 A 不变簇）+ R。

---

## S4-7 层次与一跳交互（drill 重置）

**规则**：S5 drill 到 L_{k+1} 后，新 frame 重置 hop=1、预算按新层/配置；跨层边仅在当前 view_family/level 的 allowed 边中显示；与 S2 每层 `(level,view_family)` run 一致；不继承上一层的 selection/hop。
**形式化/机检**：
```python
drill -> new frame(level=k+1, focus=child, hop=1, budget=default)
assert hop/budget reset; focus within new level partition
assert cross-level edges only if current level allows; no stale layer edges
assert S2 run keyed by (level,view_family); run not in VM
```
**反例**：drill 后保留 2 跳/旧邻居；跨层边乱入；run 状态进 VM；focus 不在新层。
**边界**：叶层无子；跨族多归属；root_exempt L0；预算变化。
**U 映射**：U-5、U-7、U-18、U-28。
**建议裁决**：冻结 drill 重置 hop/预算、层/族边界、run 不进 VM。
**证据等级**：A（S1 无 hop/S2 per-level run/S3 level）+ R。

---

## S4-8 全展开模式（同源、子集）

**规则**：全展开是同一 DataSource/同一 `present` 的另一 ctx（更大候选/预算），不是第二数据源；`shown(default) ⊆ shown(full)` 必须机检；全展开仍只画 shown、仍带 suppressed/unknown/rule_id；预算超限显式降级。
**形式化**：
```
default = select(ds, ctx_default, budget_default)
full    = select(ds, ctx_full, budget_full)
ctx_full candidate set ⊇ ctx_default；budget_full ≥ budget_default
∀e: presence_default(e)==shown ⇒ presence_full(e)==shown   # 子集
same data source id/schema；no second builder
```
**机检**：
```python
assert same DataSource identity
assert candidate_default ⊆ candidate_full
assert budget_default <= budget_full
assert shown(default) ⊆ shown(full)
assert presence/rule_id 完整；full 仍 present
```
**反例**：全展开第二数据源/第二 builder；full 显示 default 没有的节点却反过来把 default 的边 suppress；full 无预算；全展开改语义类型。
**边界**：预算相等（子集=同集）；候选人全展开；unknown/suppressed 仍存在；性能预算。
**U 映射**：U-5、U-16、U-26、U-27。
**建议裁决**：冻结同源/子集/同 present/预算显式；禁止第二数据源。
**证据等级**：A（S0-8 冻结；S3-9）+ R。

---

## S4-9 与 S3 契约

**规则**：S4 输出 VM（S3 白名单字段）；设置 `presence/rule_id`、`aggregate_count?`/审计字段；Renderer 只渲染 shown、不裁剪；`RENDER_BUDGET_EXCEEDED` 只在 VM 超 S3 硬上限时由 Renderer fail-visible；S4 预算与 S8/S3 `max_nodes/max_edges` 同源；`data_edge_ids` 仅审计、Renderer 禁读。
**形式化/机检**：
```python
VM fields ⊆ S3 whitelist + presence/rule_id/aggregate_count? + data_edge_ids(audit)
assert S4 outputs presence for all nodes/edges; renderer no trim
assert VM nodes/edges <= max_nodes/max_edges (S4 responsibility); else renderer RENDER_BUDGET_EXCEEDED
assert S4/S8/S3 same max source
assert renderer no data_edge_ids
```
**反例**：S4 输出超预算 VM 让 Renderer 裁；Renderer 改 presence；S4 用另一套 max；data_edge_ids 暴露。
**边界**：空 VM；预算 0；S4 降级仍不超硬上限；S3 视觉 token 不改。
**U 映射**：U-16、U-32、U-33。
**建议裁决**：冻结 S4→VM/presence/rule_id/预算；Renderer 只校验；S3 token 不改；max 同源。
**证据等级**：A（S3 R-S3-2/S3-11/S3-12 冻结）+ R。

---

## S4-10 与 S5 导航边界

**规则**：focus/selection/navigation/history 不进 VM；S4 不实现导航状态机；S5 消费 `nodeClick/edgeClick/backgroundClick`，生成新 frame（focus/level/dimension/new_hop）；S4 只按 ctx 计算 presence；S5 与 S4 接口 = `frame(DataSource, ctx) -> VM`。
**形式化/机检**：
```python
assert VM no focus/selection/nav/history/mode
assert S4 no navigation state; no next/back
assert events from renderer -> S5; S5 calls frame(ctx)
assert new frame resets/uses ctx; no S4-owned state
```
**反例**：S4 保存 focus/历史；渲染器直接跳；VM 带 navigation；S4 处理返回/展开。
**边界**：cluster click；KP click；background；2 跳显式；drill。
**U 映射**：U-7、U-19、U-20、U-22。
**建议裁决**：冻结 focus/selection/nav 不进 VM；S5 触发 frame；S4 无导航状态。
**证据等级**：A（S0-9/S1 D-4/S3 事件）+ R。

---

## S4-11 与 S1/S2 一致性

**规则**：presence 不改 type/label/contain_kind/kind/簇成员；多归属保持；A 不改变簇；run/簇状态不进 VM；一跳端点按 S1 维度定义；S2 每层 partition 不被 S4 改写。
**形式化/机检**：
```python
assert presence only -> type/label/kind unchanged
assert clusters unchanged across dimension/selection
assert multi-belonging preserved
assert VM no cluster_run/dendrogram/membership
assert one-hop endpoints from E(D); S2 partition intact
```
**反例**：选择性删边改类型；A 下重算簇；VM 带 run；S4 改 membership；跨族丢弃多归属。
**边界**：多归属节点；簇/ KP 混合；run no_semantic_edges；A 一跳。
**U 映射**：U-21、U-31、U-27。
**建议裁决**：冻结只改 presence、A 不变簇、run 不进 VM、多归属不变。
**证据等级**：A（S1/S2 冻结）+ R。

---

## S4-12 度量与验收（G6 可复跑）

**规则**：每 frame 输出指标并进 G6：`shown_node_count/shown_edge_count`、`suppressed_node/edge`、`unknown count`、`suppression_ratio`、`one_hop_accuracy`（所有 shown 邻居与 focus 距离=1）、`determinism_hash`（同输入同 presence）、`budget`、`degraded`；可复跑脚本。
**形式化/机检**：
```python
metrics = {shown_nodes, shown_edges, suppressed_nodes, suppressed_edges,
           unknown_nodes, unknown_edges, suppression_ratio, one_hop_accuracy,
           determinism_hash, budget, degraded}
assert one_hop_accuracy==1 unless ctx.new_hop
assert determinism_hash same 2x run
assert G6 fields完整; values可复算
```
**反例**：只报 shown；unknown/suppressed 混淆；一跳准确率不测；G6 缺预算/规则 id；同输入不同 presence。
**边界**：空图；预算 0；unknown 多；全展开；2 跳显式。
**U 映射**：U-16、U-18、U-32。
**建议裁决**：冻结指标/G6 字段/确定性/一跳准确率；阈值 S8。
**证据等级**：A（S0-6/S3）+ PI（指标集合）。

---

## 附：S4 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| 选点/选边可机检/唯一 presence | S4-1/S4-2（sort key/pseudocode）✅ |
| 预算单一归属 S4/Renderer 不裁剪 | S4-1/S4-9 ✅ |
| presence 三值/rule_id/unknown≠suppressed | S4-4 ✅ |
| 一跳严格/2 跳 S5 显式 | S4-3/S4-5 ✅ |
| shown(default)⊆shown(full)/同源 | S4-8 ✅ |
| A/B 差异逐条 | 见 `S4-objections.md`（写完对照） |
| 覆盖 U-5/15/16/17/18/19/21/22/27/28/31 | §0.1 ✅ |
| 不写产品代码/契约/commit | 本文件只写设计 ✅ |

> 独立声明：本文件写作时未读 `S4-render-proposal-A.md`（尚未落盘）；差异与判断见 `S4-objections.md`，逐项列不合并。
