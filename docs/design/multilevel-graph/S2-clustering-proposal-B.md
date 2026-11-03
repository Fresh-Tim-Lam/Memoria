# S2 簇与子图划分提案 B（独立复核方）

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（sha `241b1e1e…`）、`S1-dimensions-v1.md`（sha `6676c71d…`），**不得违反**；本场章程 `S2-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S2-clustering-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S2-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0/S1 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. 总原则（S2 不得改 S0/S1）

1. 簇 = **语义内聚小群 + 零星桥**，**不是严格连通分量**（S0-4/U-13/U-14）；`graph-groups.js` 的 UnionFind 闭包是**反例**，不得作为簇定义（A：`graph-groups.js:9-24,80-99`）。
2. 簇是**视图/研究层派生对象**，不是产品事实；不写产品 sidecar/新段（S0 D-3/S0-11 #14）。
3. 簇身份按 S0 D-2：`cluster_run_id + local_seq` 为实例 id；`cluster_key = sha256(canonical(sorted(member_canonical_ids)) + algorithm_id + version + params_hash)` 为可复算/去重键；**内容哈希不得当 curation 主引用**。
4. 多归属遵循 S0-7 + S1 partition：**同一 `(level, view_family)` 内成员唯一（partition），跨 view_family/层次/维度允许重叠**；不设上限（S0-7；S2 可选收紧但须证据）。
5. 簇只属于 H 的层次划分；**A 不影响簇**（S1 H/A 分工）；簇派生边/聚合边带 `data_edge_ids`（S0 R-3/S1 R-S1-11）。
6. 所有 μ/β/划分/稳定性/身份必须可机检：同输入同参数 ⇒ 唯一结果（或确定性分布，若算法统计性则必须固定种子+分布报告）；参数非法 fail-closed。

### 0.1 覆盖矩阵（S2 相关 U 全部出现）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-6 | 代表连通子图节点=S2-1/S2-8 | U-13 | 非严格连通子图=S2-1/S2-3 |
| U-14 | 语义划分小群=S2-2/S2-4 | U-15 | 一跳挂接承接 S0-5（S2-9 边界） |
| U-17 | 背后图不带入=S2-9（簇边） | U-21 | 多归属=S2-6 |
| U-22 | 新一跳/更深=S2-10（A 不影响簇） | U-31 | 多归属上限=S2-6 |
| U-4/U-5 | 层次/默认=S2-8/S2-10 | U-28 | 最小粒度=S2-8 |
| U-1/U-2 | 语义/双价值=S2-2/S2-12 | U-32 | 规模/检索=S2-4/S2-12 |
| U-30 | 关联维度=S2-10 | U-33 | 2D/3D=S2-12（度量不含渲染） |
| U-34 | 逐议项=本文件 | U-35 | SE 图纸=S2-11/S2-12 |

---

## S2-1 簇定义与边界

**定义/规则**：簇 = KP 集合 C 上满足 **内聚度 μ(C) ≥ τ_coh** 且 **桥比例 β(C) ≤ τ_bridge** 的语义小群；簇不是严格连通分量、不是目录分组、不是 graph-groups 闭包。簇是视图层 cluster_node 的成员来源，不写产品事实。

**形式化**：
```
K = KP 集；E_sem = S0-1 语义边（label=semantic，含 asserted/semantic contain）
C ⊆ K，|C|≥1；E_in(C) = {e∈E_sem | endpoints⊆C}
E_bridge(C) = {e∈E_sem | 一端∈C，另一端∉C}
候选簇 ⇔ μ(C)≥τ_coh ∧ β(C)≤τ_bridge ∧ C 非空
单点簇：|C|=1 允许（退化），但默认视图不应全为单点簇（U-5）
空簇：禁止（不得渲染空 cluster_node）
全库一簇：允许数学上存在，但若没有"外部桥"（β 无定义/0）需标记 degenerate，不默认采用（见 S2-4 降级）
```
**机检条件**：
```python
assert all(c.members and set(c.members) <= K for c in clusters)
assert all(mu(c) >= tau_coh and beta(c) <= tau_bridge for c in clusters)
assert not any(len(c.members)==0 for c in clusters)
# 与严格连通分量区分：fixture 中至少一个簇 ≠ UnionFindComponent（不得以并查集定义簇）
assert not is_union_find_component_definition(algorithm)
```
**反例**：用 `graph-groups.js` UnionFind 闭包直接当簇（严格连通分量，U-13 禁止）；按目录分组当簇；空簇；全库一簇无外部桥却作为默认；单点簇占满默认视图（退化为全展开）。
**边界用例**：单成员簇；全库只有 1 个语义连通块（β=0）⇒ 标记 degenerate，默认 H 退化为 KP/结构提示，不伪造多簇；无 E_sem（μ/β 无定义）⇒ 降级路径（S2-4），不得用 UnionFind 冒充；簇成员全为 range_ok=false 的 KP 仍可为成员。
**U 映射**：U-6、U-13、U-14、U-21。
**建议裁决**：冻结"簇=μ/β 语义小群，非严格连通分量/非目录分组/非 graph-groups；空簇禁止、单点允许；全库一簇标 degenerate"。
**证据等级**：A（U-13/U-14；`graph-groups.js:9-24,80-99` UnionFind 反例）+ R（S0-4）。

---

## S2-2 语义内聚度 μ

**定义/规则**：μ 用**内部语义边的密度**（可复算）；v1 采用二值语义权重（label=semantic 的边权重 1；structural/navigation 权重 0，不计入 μ），不引入 embedding/人工评分等不可复算量。
**形式化**：
```
n = |C|；P = n(n-1)/2（无向 possible pairs）
E_in_sem(C) = {e∈E_sem | source,target∈C}（有向边按端点对去重？见下）
μ(C) = |distinct unordered endpoint pairs in E_in_sem(C)| / P        （n≥2）
     = 1（定义，n=1，单点簇退化；不提供语义证据）                    （n=1）
阈值：τ_coh ∈ (0,1]；默认 v1=0.3（可配置；S8 可调）；参数非法（≤0、>1、NaN）⇒ fail-closed
权重：v1 二值；未来若加权（confidence/证据等级）必须 S2 修订，不得静默换公式
```
**机检条件**：
```python
assert 0 < tau_coh <= 1
assert mu(c) == len(distinct_pairs(E_in_sem(c))) / (n*(n-1)/2)   # n>=2
assert mu(c) >= tau_coh
assert not weighted  # v1 二值
```
**反例**：用边数不作密度（大簇自动高 μ）；把 structural contain 计入 μ（偷换语义）；把 embedding 相似度当 μ 而不冻结公式；μ 公式随实现不同（未冻结）；n=1 用 μ=1 冒充语义证据。
**边界用例**：n=1；n=2 有 1 条语义边 μ=1；n=3 两条边 μ=2/3；同一对节点多类型边按**端点对**去重（不得重复加权）；有向边按 unordered pair 计（cluster 无向成员关系）。
**U 映射**：U-1、U-13、U-14。
**建议裁决**：冻结 μ=内部语义边端点对密度（二值、n=1 定义 1 仅退化），τ_coh 参数化+默认 0.3；参数非法 fail-closed。
**证据等级**：C（U-13/U-14；S0-1 语义边定义）+ PI（二值/默认阈值）。

---

## S2-3 桥判定 β

**定义/规则**：β 衡量簇与外部连接的"零星"程度：跨簇**语义边**数占（内部语义边 + 跨簇语义边）的比例；与 U-13"内聚高、外部零星桥"一致。
**形式化**：
```
E_out_sem(C) = {e∈E_sem | 一端∈C，另一端∉C}
β(C) = |distinct pairs E_out_sem(C)| / (|pairs E_in_sem(C)| + |pairs E_out_sem(C)|)
     若分母=0（无任何语义边）⇒ β 无定义（degraded，不得判为 0）
τ_bridge ∈ [0,1)；默认 v1=0.2（可配置）
边界：β=0 表示无外部语义桥（可能全库一簇/孤立），不是"最好"；单点桥计入 E_out
```
**机检条件**：
```python
assert 0 <= tau_bridge < 1
if denom == 0: mark_unknown(c, "beta_undefined")
else: assert beta(c) <= tau_bridge
assert pairs 去重；semantic only；不把 structural contain 当桥
```
**反例**：β 用全部边（含 structural/reference）→ 把目录/引用当桥；β 用节点数；无外部边时把 β 当 0 判优；单点桥被忽略。
**边界用例**：β=0（孤立/全库一簇）；β 接近 1（链式/稀疏）；n=1 的 β（可能全部外连）；多桥同对去重。
**U 映射**：U-13、U-14、U-17（桥不带背后图）。
**建议裁决**：冻结 β=跨簇语义边比例（去重、分母含内外；无定义标 unknown）；τ_bridge 默认 0.2；非法 fail-closed。
**证据等级**：C（U-13；S0-4）+ PI（默认阈值）。

---

## S2-4 划分算法候选与确定性/降级

**定义/规则**：v1 选**确定性图聚类**（不是并查集、不是随机社区发现）；候选：
1. **确定性层次凝聚聚类**（primary）：以语义边加权邻接 + 平均连接（average linkage，Jaccard/边密度距离）；固定输入顺序（canonical id 排序）+ 固定 tie-break；目标簇数由 τ_coh/τ_bridge 与最小簇规模决定；复杂度 O(n²) 可接受（S9 负责取景，S2 只算簇）。
2. **确定性标签传播（备选）**：固定更新顺序/canonical tie-break；异步/同步固定；结果必须可复跑。
3. **禁止**：非固定种子的 Louvain/Leiden、随机初始化 k-means、`graph-groups.js` UnionFind 闭包当簇定义。
**机器可复算/确定性**：
```
algorithm_id + algorithm_version + params_hash（含 seed=0/固定排序）→ 唯一 cluster set
同 (K,E_sem,params) 两次运行字节一致（cluster 集合/成员排序/cluster_key 一致）
```
**降级路径（fail-visible，不得静默）**：
```
D0 正常：μ/β 满足，返回 clusters
D1 无 E_sem / μ/β 无定义：返回 cluster_mode="none"（H 显示 KP 节点 + `rule_id=no_semantic_edges`），不得用 UnionFind 冒充
D2 算法不收敛/超预算：返回 partial? 不允许部分结果冒充完整；返回错误 DEGRADED，上层显式提示，H 退化为 KP 视图
D3 参数非法：fail-closed（不返回簇）
```
**机检条件**：
```python
assert algorithm_id in {"agglo_deterministic","label_prop_deterministic"}
assert seed fixed/ordering canonical; 2x run identical
assert graph_groups_union_find not used as cluster definition
assert degraded => explicit cluster_mode/rule_id, not fake clusters
```
**反例**：用 Louvain 默认 seed 当确定；用 UnionFind 当簇（严格连通分量）；无 E_sem 时返回目录分组冒充语义簇；超时返回部分簇并声称完整；参数漂移无版本。
**边界用例**：无 E_sem；单个全连通块；大图 O(n²) 超预算→降级；同分 tie 用 canonical id 定序；算法版本升级 → 新 run id。
**U 映射**：U-13、U-14、U-32（规模/检索 S9）。
**建议裁决**：冻结确定性算法候选 + 固定 tie-break + 降级显式 fail-visible；禁止 UnionFind 当定义；v1 选 primary 层次凝聚，备选标签传播仅研究。
**证据等级**：A（`graph-groups.js` 反例）+ C（U-13/U-14）+ PI（算法选择/复杂度）。

---

## S2-5 稳定性与重聚类触发

**定义/规则**：簇有版本/run；重聚类只在**明确触发条件**下发生；稳定性用成员 Jaccard 度量；不得每次视图刷新随机重算。
**触发条件（全部可机检）**：
```
T1 语料身份变化：corpus_manifest_sha 变化
T2 语义边集变化：E_sem 增/删/改（含 curation/assertion_source 变化）
T3 算法/参数/版本变化：algorithm_id/version/params_hash 变化
T4 层级/视图族变化：level/view_family 变化（新划分）
T5 显式用户/服务请求（S2-13；agent 默认不可）
禁止：定时随机重算；仅 UI 刷新/维度切换不触发（A 不影响簇，S2-10）
```
**稳定性度量**：
```
按 cluster_key 匹配旧/新簇；Jaccard(A,B)=|A∩B|/|A∪B|
stable ⇔ Jaccard ≥ τ_stable（默认 v1=0.8；S8 可调）
报告：matched/unmatched/new/removed；不稳定簇列表
```
**机检条件**：
```python
assert run_id deterministic from (manifest_sha, level, view_family, algorithm, params)
assert re_run_trigger in {T1..T5}
assert no periodic random trigger
assert jaccard computed for matched clusters; tau_stable ∈ (0,1]
assert same input without trigger => same run_id/clusters (cache hit)
```
**反例**：每次刷新重算导致漂移；无触发条件下 cluster 变化；以节点数变化为唯一触发；Jaccard 只在同索引比较（成员重排即误判）；重聚类覆盖旧 run 无历史。
**边界用例**：小改动（1 边）触发新 run，Jaccard 高；算法升级 Jaccard 低但合法；无旧 run（首次）；簇消失/新增。
**U 映射**：U-13、U-14、U-21（稳定身份）。
**建议裁决**：冻结触发 T1–T5 + Jaccard 稳定性 + 默认 τ_stable + 禁止随机/周期性重算；run 历史保留。
**证据等级**：C（U-13/U-14）+ PI（阈值/触发细节）。

---

## S2-6 多归属（与 S0-7/S1 partition 一致）

**定义/规则**：membership 多对多；**同一 `(level, view_family)` 内 partition（每个 KP 恰属一个簇）**，跨 `view_family`/层次/维度允许重叠；成员关系 ≠ 视图出现；不设上限（S0-7，S2 可决定是否收紧，但必须给证据且 fail-closed）。
**形式化**：
```
membership ⊆ K × cluster_instance
同 (level, view_family)：每个 KP 恰属一个簇（partition）
跨 family/level/dimension：一个 KP 可属多个簇
与维度无关：A 维度不改变 membership；H 每层独立划分（S2-10）
上限：v1 不设硬上限；若未来设上限，超限 fail-closed，不得静默丢弃
```
**机检条件**：
```python
for fam in view_families:
    owners = [c for c in clusters_in(fam) if kp in c.members]
    assert len(owners)==1                      # 同族 partition
cross_family_overlap_allowed = True
assert no_single_parent_field
assert cap is None or fail_closed_on_exceed
```
**反例**：用单值 `parent_cluster`；同族一个 KP 属两簇（partition 破坏）；把视图出现写回 membership；偷偷设上限（如最多 3 个簇）并静默截断；把 membership 写入产品 sidecar（D-3）。
**边界用例**：同一 KP 跨层属不同簇（允许）；同族单点簇；跨族重叠计数不设限；成员数为 0 的 cluster 禁止。
**U 映射**：U-21、U-31（+U-6/U-7）。
**建议裁决**：冻结"同族 partition、跨族/层/维多归属、不设上限、membership≠视图出现、不写产品"。
**证据等级**：A（S0-7/S1 R-2 冻结；`graph-groups.js` 单值 nodeToGroup 反例）+ R。

---

## S2-7 簇身份（D-2）

**定义/规则**：实例 id = `(cluster_run_id, local_seq)`；`cluster_key` 为内容键；curation/审计同时记录 run+key；内容哈希不得当实例 id（成员一变引用失效）。
**形式化**：
```
cluster_run_id = sha256(canonical(corpus_manifest_sha, level_id, view_family_id,
                                  algorithm_id, algorithm_version, params_hash))
local_seq = 该 run 内按 (cluster_key, 最小成员 canonical id) 排序后的序号（稳定）
cluster_instance_id = f"{cluster_run_id}:{local_seq}"
cluster_key = sha256(canonical(sorted(member_canonical_ids), algorithm_id,
                                algorithm_version, params_hash))
curation/audit 引用 = {run_id, local_seq, cluster_key}
成员变化 ⇒ 新 key、可能新 local_seq；旧 curation 必须按 (run,key) 追溯，不得用新 key 冒充旧
```
**机检条件**：
```python
assert run_id deterministic from identity tuple
assert local_seq unique/stable within run
assert cluster_key == sha256(canonical(...))
assert curation_ref contains run_id and cluster_key
assert cluster_key not used alone as instance id
```
**反例**：`cluster_id=sha256(members)` 当实例 id（D-2 禁止）；成员变化后旧 curation 自动"继承"新簇；local_seq 依赖哈希随机顺序；run id 不含 manifest/算法版本（不可比较）。
**边界用例**：成员不变但 key 算法版本变 ⇒ 新 run；同 members 不同参数 ⇒ key 不同；簇合并/拆分 ⇒ 旧引用保留可追溯；首次 run。
**U 映射**：U-21、U-31（+G6 快照）。
**建议裁决**：冻结 D-2 身份 + 审计引用规则；`cluster_key` 只作可复算键。
**证据等级**：A（S0 D-2 冻结）+ C（实现细节）+ PI（排序规则）。

---

## S2-8 嵌套、展开、空/单点簇

**定义/规则**：H 每层是独立 partition；跨层为嵌套细化（S0-2）；同一层禁止簇重叠（S2-6）；cluster 展开到 KP（S0 V6）；空簇禁止；单点簇允许；cluster_node 是视图节点非事实实体。
**形式化**：
```
同 (level, view_family)：分块互斥且并=K（S0-2）
跨层：Π_{ℓ+1} 细化 Π_ℓ（S0-2 嵌套）
expand(c) = 递归到 KP 的成员集合；必须非空、⊆K、无环
cluster 只在 H 的层级出现；A 不创建/改变簇（S2-10）
```
**机检条件**：
```python
assert same_family_partition_valid()
assert all(expand(c) is nonempty and <=K)
assert no_cycles(expand)
assert empty_cluster_count==0
assert single_point_allowed but default_not_all_singletons (or explicit degraded)
```
**反例**：同层簇重叠/漏 KP；空簇节点；展开出现非 KP；嵌套成环；A 维度改变簇；单点簇占满默认（退化为全展开）。
**边界用例**：单点簇；跨层嵌套；叶层全 KP；簇成员 range_ok=false；簇展开到 KP 后与 H 下一层一致。
**U 映射**：U-5、U-6、U-28（+S0-2）。
**建议裁决**：冻结同层 partition/跨层嵌套/展开语义/空禁单点允许；H 使用。
**证据等级**：A（S0-2/S0-7/R-2 冻结）+ C。

---

## S2-9 簇与边（内部/桥/data_edge_ids）

**定义/规则**：内部语义边用于 μ；桥语义边用于 β；structural contain 只作结构内部边，不进 μ/β（S0-4）；聚合/折叠边必须带 `data_edge_ids`（R-3）；簇边界边显示归 S4，S2 只定义集合。
**形式化**：
```
E_in_sem/E_out_sem 见 S2-2/S2-3（semantic only）
E_struct_in = contain(structural) inside C（结构，不计 μ）
bridge = semantic cross edge；structural cross edge 不计 β
cluster 视图边若聚合多数据边 ⇒ data_edge_ids 非空；expand_data_edges(VM) ⊆ DataSource.edges
```
**机检条件**：
```python
assert mu uses semantic only; beta uses semantic only
assert all(aggregated_edges have data_edge_ids)
assert expand_data_edges(VM) <= DataSource.edges
```
**反例**：用 reference/structural 当语义内聚/桥；聚合边无 data_edge_ids；把桥边当作簇内边；跨簇边丢失（无 presence/rule_id）。
**边界用例**：同 pair 多类型边；单条桥；结构包含嵌套；簇合并后内部边重算；空 data_edge_ids 字段（R-S1-11 允许空集但字段必须存在）。
**U 映射**：U-13、U-15、U-17。
**建议裁决**：冻结语义边/结构边分工 + 聚合边 data_edge_ids + 边界显示归 S4。
**证据等级**：A（S0-4/R-3/S1 R-S1-11）+ C。

---

## S2-10 簇与维度/层次

**定义/规则**：H 每层独立划分；A 不改变簇（只做关系扩展）；`clusters` 与 `dimension_id` 无关；`view_family`/level 决定 partition；跨维多归属由 S2-6。
**形式化**：
```
clusters(level, view_family) 独立计算；A 激活不改变 clusters
H: 每层 partition；A: 只扩节点/边，不重算簇
view_family = ⟨family_id,basis,dimension_id,level_chain⟩（S0 R-2）
同族单归属；跨族可重叠
```
**机检条件**：
```python
assert cluster_set(H_ctx) == cluster_set(A_ctx) for same level/family   # A 不影响簇
assert each level has its own partition
assert view_family identity used in run_id
```
**反例**：A 维度下按关系邻居重算簇（维度污染簇）；H 各层共享同一簇（不独立）；A 改变 membership；切换维度簇漂移。
**边界用例**：A 激活时 H 簇背景不变；跨族同 KP 多簇；level 变化生成新划分；维度切换不触发重聚类（S2-5 T4 只 level/family 变化，不因 A 切换）。
**U 映射**：U-8、U-10、U-21、U-22、U-30。
**建议裁决**：冻结"簇只属 H；A 不影响簇；每层独立划分；维度切换不触发重聚类"。
**证据等级**：A（S1 H/A 分工、S0-7/R-2）+ C。

---

## S2-11 持久化与缓存（D-3）

**定义/规则**：簇是**派生缓存/研究层**，不是产品事实；**禁止写产品 sidecar/新段**（S0 D-3）；允许写入可再生产物（cache/artifacts）但必须可重建、带 run/算法版本；S6 定义正式存储。
**形式化**：
```
cluster 持久化位置 ∈ {research artifacts, .memoria/cache（可再生）}
禁止：.memoria/sidecars/** 增加簇/成员段；产品 schema 变更；写用户 KB 正文
缓存 key = cluster_run_id；删除缓存可重建；审计记录 run/params/corpus
semantic 边 curation overlay 仍按 v0.3（不属于 S2 簇持久化）
```
**机检条件**：
```python
assert no_cluster_keys_in_sidecar_schema
assert cache_rebuildable_from (DataSource, registry, params)
assert cache includes algorithm_id/version/params_hash/manifest_sha
assert write_paths ⊆ {artifacts,cache}
```
**反例**：把簇写入 sidecar/新段（D-3 违反）；缓存无版本/不可重建；把簇当事实源供其他模块读；回滚删除不了/无法重建。
**边界用例**：缓存缺失⇒重算；算法升级⇒新 cache key；回滚到旧 cache；只读 frozen 语料。
**U 映射**：U-6、U-13、U-14（+S0 D-3/S0-11 #14）。
**建议裁决**：冻结"簇=派生缓存/研究层，禁写产品 sidecar/新段；缓存可重建+版本化；S6 定正式存储"。
**证据等级**：A（S0 D-3 冻结；`graph-groups.js` 仅视图层分组）+ R。

---

## S2-12 度量与验收（G6 可复跑）

**定义/规则**：S2 度量必须可复跑并进 G6 快照；数值阈值归 S8，S2 冻结指标定义。
**指标**：
```
cluster_count；size 分布；μ 分布；β 分布；bridge edge 数；
partition 违规数（必须 0）；stability Jaccard（匹配簇）；run 可复现（2x 字节一致）；
G6 快照字段：corpus_manifest_sha, algorithm_id, version, params_hash,
             cluster_run_id, sorted(cluster_key), membership digest,
             edge_set digest（E_sem）
```
**机检条件**：
```python
assert partition_violations == 0
assert run_reproducible(2x)
assert snapshot_fields_complete
assert metrics computed from frozen corpus identity
```
**反例**：只报簇数不报 μ/β；不固定算法版本/种子；G6 快照缺 manifest/algorithm；用 live KB 无 manifest 测；稳定性无可比 run。
**边界用例**：单点全库；无 E_sem；算法降级；不同参数比较；历史 run 回放。
**U 映射**：U-13、U-14、U-32、U-33（性能 S8/S9）。
**建议裁决**：冻结指标定义 + G6 快照字段 + 可复跑要求；阈值 S8。
**证据等级**：C（U-13/U-14/S8 接口）+ PI（指标集合）。

---

## S2-13 与 agent

**定义/规则**：v1 agent **只读**簇结果，不触发重聚类、不写簇状态；agent 可请求 S9 取景（S1-14），但簇重算必须由触发条件（S2-5）或显式用户/服务动作触发，并审计。agent 可提出 KP 修改（S10），但不得因此隐式重聚类/写 membership。
**形式化**：
```
agent 允许：读 clusters（run/key）、读 metrics、请求 frame（S1-14）
agent 禁止：触发重聚类（无 API）、写 cluster store/cache、改 membership、改 algorithm/params
重聚类触发：T1–T5（S2-5），其中 T5 显式用户/服务动作；agent 不能直接 T5
审计：任何 run 记录触发来源/actor/policy
```
**机检条件**：
```python
assert no_agent_api("recluster"/"write_cluster"/"write_membership")
assert run_audit.trigger in {T1..T5}; agent-initiated ⇒ denied unless explicit policy
assert agent read-only cluster results
```
**反例**：agent 触发重聚类并覆盖 run；agent 写 membership/缓存；agent 用 KP 修改隐式触发重算；无审计。
**边界用例**：agent 读旧 run 做检索；S9 取景使用旧 cluster；用户显式重算；策略允许 agent 提案但需人批。
**U 映射**：U-21、U-29、U-32（+S0-10/S1-14）。
**建议裁决**：冻结"agent 只读簇；重聚类由 T1–T5/用户动作触发；无 agent 写接口"；S7/S9 再议提案能力。
**证据等级**：A（S0-10/S1-14 冻结）+ C（S2 触发）。

---

## 附：本提案对 S2 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| μ/β/划分/稳定性可机检 | S2-2/S2-3/S2-4/S2-5（公式+pseudocode）✅ |
| 阈值/参数有类型/默认/失败语义 | S2-2/S2-3/S2-4（fail-closed）✅ |
| 簇 ≠ 严格连通分量，有反例/机检 | S2-1/S2-4（graph-groups 反例 + 禁用断言）✅ |
| 多归属与 S0-7/S1 partition 一致 | S2-6/S2-8/S2-10 ✅ |
| A/B 差异逐条列出 | 见 `S2-objections.md`（写完对照） |
| 覆盖 U-6/13/14/15/17/21/22/31 | §0.1 ✅ |
| 不改产品代码/契约/commit | 本文件只写设计 ✅ |

> 独立声明：本文件写作时未读 `S2-clustering-proposal-A.md`（尚未落盘）；差异与我的判断见 `S2-objections.md`，逐项列不合并。
