# S2 簇与子图划分提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S2-RULINGS.md`（R-S2-1..R-S2-8）；最高原话 `multilevel-graph-vision.md`；上游冻结 `S0-terms-v1.md`（sha `241b1e1e…`）、`S1-dimensions-v1.md`（sha `6676c71d…`），不得违反。
> **输入**：B v1（sha `5b40429f…`）、A v1（sha `b14bb379…`）、`S2-objections.md`。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S2-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S2-RULINGS/S0/S1 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S2）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S2-2/S2-3/S2-9 | 语义-only 公式 | **确认 μ/β 只使用 `label=semantic` 的 `E_sem`**；reference/structural/非 semantic extend 权重=0、不进分子分母；补机检与反例（R-S2-1） | 确认/强化 |
| 2 | S2-2/S2-3 | 默认 τ=0.3/0.2（未标定） | 补**语义-only probe 方案**（frozen + 演示库）+ τ 标定流程；τ 参数类型/范围/失败语义；无 E_sem ⇒ `no_semantic_edges`，不得凑簇（R-S2-2/R-S2-8） | 新增 |
| 3 | S2-4 | HAC 主选，无精确契约 | **HAC 精确定义**：average-linkage、tie-break、序列化、golden 2x 字节一致、O(n²) 上限与 degraded（R-S2-3） | 强化 |
| 4 | S2-7 | run 含 level；local_seq 按 key/min | **run 粒度统一 `(level, view_family)`**；run_id 公式含 level_id；`parent_run_id`；local_seq 按 min canonical id；cluster_key 按 D-2（R-S2-4） | 修正 |
| 5 | S2-13 | agent 只读 | **v1 agent 只读 + 可请求候选 run**（requester/reason/params 审计；candidate/adopted 分离；不自动采用；不写 membership/缓存/manifest/渲染）（R-S2-5） | 修正 |
| 6 | S2-2/S2-1/S2-12 | singleton μ=1；coverage 不明确 | singleton **μ=null、representative=false**；`root_exempt`；coverage=覆盖 KP 数/|K|；Jaccard+churn；G6 字段（R-S2-6） | 修正 |
| 7 | S2-6 | Membership.role 含 bridge? | **Membership.role 不复用 S1 bridge**；bridge 只作边状态/统计；A 不改变簇（机检伪代码）（R-S2-7） | 修正 |
| 8 | S2-1/S2-4/S2-11/S2-12 | 无 probe 方法/root/降级/G6 细节 | **吸收 A 的 frozen probe 方法、root_exempt、降级路径、G6 度量字段**（R-S2-8） | 并集 |

---

## 0.1 覆盖矩阵（S2 相关 U + S0/S1 条款）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-6 | 代表节点=S2-1/S2-8 | U-21 | 多归属=S2-6 |
| U-13 | 非严格连通子图=S2-1/S2-3 | U-31 | 上限=S2-6 |
| U-14 | 语义小群=S2-2/S2-4 | U-15/U-17 | 桥/背后图=S2-9 |
| U-22 | 新一跳/更深=S2-8/S2-10 | U-32 | 规模/检索=S2-4/S2-12 |
| U-4/U-5 | 层次/默认=S2-8/S2-10 | U-1/U-2 | 语义/双价值=S2-2/S2-12 |
| U-28 | 最小粒度=S2-8 | U-33 | 2D/3D=S2-12（度量不含渲染） |
| S0-1/S0-4 | 语义边/簇定义 | S1 H/A | H 产生簇；A 不影响=S2-10 |
| S0-7/R-2/R-3 | 多归属/partition/聚合边 | S0 D-2/D-3 | 身份/不写产品=S2-7/S2-11 |
| S1 R-S1-11 | H 派生边 data_edge_ids | S2 charter | S2-1..S2-13 全覆盖 |

---

## S2-1 簇定义与边界

**规则**：簇 = 同一 `(level, view_family)` 下，**语义内聚度 μ≥τ_coh、桥比例 β≤τ_bridge** 的成员块；不是严格连通分量、不是目录分组、不是 graph-groups UnionFind；簇是派生视图层对象，不写产品事实。单点块允许但 `μ=null`、`representative=false`；空簇禁止；L0 全库一簇用显式 `root_exempt=true`（不是普通簇）。

**形式化**：
```
E_sem = { e ∈ DataSource.edges | label(e)=="semantic" }       # R-S2-1
C ⊆ K，|C|≥1；E_in(C) = {e∈E_sem | 两端∈C}；E_out(C) = {e∈E_sem | 恰一端∈C}
|C|≥2: μ(C)≥τ_coh ∧ β(C)≤τ_bridge；|C|=1: singleton（μ=null，豁免）
空簇禁止；Π_{ℓ,f} 覆盖 K_f、块不交
root_exempt: L0 全库单块显式标记；默认 H 从 L1 起
```
**机检**：
```python
assert all(c.members and set(c.members)<=K for c in clusters)
assert all(mu(c)>=tau_coh and beta(c)<=tau_bridge for c in clusters if len(c.members)>=2)
assert all(c.mu is None and not c.representative for c in clusters if len(c.members)==1)
assert empty_cluster_count==0
assert root_exempt_only_at_L0
assert not is_union_find_definition(algorithm)       # graph-groups 反例
```
**反例**：UnionFind 闭包当簇；目录分组；空簇；单点簇被标 representative=true；L0 全库块未标 root_exempt；把 reference/structural 当语义证据（S2-2）。
**边界**：单点；L0 根；全库一簇 root_exempt；无 E_sem ⇒ `no_semantic_edges` 降级（S2-4），不得返回假簇；跨族重叠归 S2-6。
**U 映射**：U-6、U-13、U-14、U-21。
**建议裁决**：冻结上述定义；单点 μ=null/representative=false；root_exempt 仅 L0；禁止 UnionFind 当簇。
**证据等级**：A（U-13/U-14；S0-1/S0-4；`graph-groups.js:2,83`）+ R（R-S2-1/R-S2-6）。

---

## S2-2 语义内聚度 μ（语义-only；含 probe/τ）

**规则**：μ 只使用 `E_sem`（label=semantic）的**内部语义边密度**；v1 二值权重（每条 semantic 边 1）；reference/structural/非 semantic extend **权重 0，不进分子分母**；singleton μ=null；τ_coh 参数化、类型/范围/失败语义如下。

**形式化**：
```
E_in(C) = {e∈E_sem | endpoints⊆C}
pairs(C) = distinct unordered endpoint pairs of E_in(C)
μ(C) = |pairs(C)| / (|C|(|C|-1)/2)        # |C|≥2
μ(C) = null                                # |C|=1
τ_coh: float|null；非 null 时 ∈ (0,1]；**暂定默认 0.5**（出处：A-v2 语义-only probe 产物 `artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/results.json`；B 独立复算/SE 复核后确认；S8 在真实 semantic curation 语料上复标定）。τ=null 仅允许 `no_semantic_edges`/`uncalibrated` 状态，不得用任意默认凑簇（R-S2-2）
params_hash 覆盖 (weight_policy=semantic_only, tau_coh)
```
**机检**：
```python
assert input_edge_set(mu) == E_sem          # 关键：不得含 reference/structural
assert all(e.label=="semantic" for e in E_in)
assert 0 < tau_coh <= 1 or tau_coh is None
assert mu(c)==len(distinct_pairs)/P for |C|>=2; singleton mu is None
```
**反例**：两个仅 reference 边的 KP 在旧 A 权重下 μ=0.2 被判簇（P0-1 反例，B-v2 必须 FAIL）；structural-only 目录嵌套 μ=0.5（FAIL）；同 pair 多类型 semantic 边重复计数（应去重）；singleton μ=1 参与阈值（FAIL）。
**边界**：n=2 一条 semantic 边 μ=1；无内部 semantic 边 μ=0（不合格）；E_sem=∅ ⇒ `no_semantic_edges`（不计算 μ）；τ=null ⇒ `uncalibrated`，不得用任意默认凑簇。
**U 映射**：U-1、U-13、U-14。
**建议裁决**：冻结语义-only 二值 μ 公式 + τ 参数类型/范围/失败；默认 τ 待语义-only probe 标定，未标定则 `uncalibrated`。
**证据等级**：A（S0-1/S0-4 冻结；R-S2-1）+ R（R-S2-2）+ PI（二值权重）。

---

## S2-2b 语义-only probe 方案与 τ 标定（R-S2-2）

**目标**：用 frozen 语料 + 演示库产生 **semantic-only** 的 μ/β 分布与簇数，据此标定 τ_coh/τ_bridge；无语义边时如实报告"几乎无簇"为合法，不用结构边凑簇。

**输入身份**：
```
frozen 语料：artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理
  MANIFEST sha a4beaedc5f852816129ebc8399072a17b6b07e97bd22ea848246ae90a3b75466
演示库：docs/example/AAA_Vocab（live 工作区须记录 manifest sha；与 frozen 分开报告）
E_sem 提取规则：S0-1 label=semantic（asserted 作者边 + contain_kind=semantic 且 assertion_source/curated_* 齐全）；
  reference / structural contain / 非 semantic extend 权重 0
```
**已知 frozen 事实（B 级，来自 G5/G4 冻结产物）**：62 边 = 26 sidecar_edge（`provenance_state=missing`）+ 3 link（`inferred`）+ 33 contain（`system_range`/`structural`）；`asserted=0`（G5 `backfill-report.json`）⇒ **frozen E_sem = 0**，语义-only 下**没有可成立簇**（只能 singleton/no_semantic_edges）。这必须作为 probe 的正式结果之一，不能改权重制造簇。

**probe 输出（每次）**：
```json
{"corpus_identity":"...","e_sem_count":0,"mu_null":true,"beta_null":true,
 "cluster_count":0,"singleton_count":357,"status":"no_semantic_edges",
 "tau_coh":0.5,"tau_bridge":0.25,"note":"semantic-only; non-semantic edges excluded; tau provisional from A probe, B repro pending"}
```
**τ 标定流程**：
1. 若 E_sem 为空：`status=no_semantic_edges`、cluster_count=0；`tau_coh=0.5/tau_bridge=0.25` 仅作暂定参数（A-v2 probe 出处，B 独立复算 pending），不用于判定；S3/S4 处理默认视图退化。**不得**回退到 structural/reference 权重。
2. 若 E_sem 非空（人工 semantic curation 或演示库补充）：对候选块计算 μ/β 分布；列出候选 τ 区间（使非 singleton 块数>0 且 partition/μ/β 合法）；取**最小的 τ_coh / 最大的 τ_bridge** 使至少一个非平凡簇成立（保守）；同时报告簇数/覆盖率/单点比例；S8 live 复核后冻结默认。
3. 默认值出处：probe 产物路径 + corpus identity 必须写入 S2 冻结稿；`params_hash` 覆盖 τ；τ 非法（≤0、>1、NaN）⇒ fail-closed；τ=null 且非 `no_semantic_edges` ⇒ `uncalibrated` fail-closed（不返回簇）。
**机检**：probe 可复跑；E_sem 输入断言；τ 区间/默认值可从产物复算；无 E_sem 时必须 cluster_count=0。
**反例**：用加权 E_relation_min 产生"簇"（A P0-1）；用目录分组补簇；τ 未标定却用任意值；在 frozen 报告"有簇"。
**U 映射**：U-1、U-13、U-14。
**建议裁决**：冻结 probe 方法/输入身份/输出/标定流程；frozen 语义-only 结果如实为"无簇"；τ 默认由 probe/S8 定。
**证据等级**：B（G5/G4 frozen 产物；`edges-suggestions.jsonl`/`backfill-report.json` asserted=0）+ R（R-S2-1/R-S2-2）+ PI（标定流程）。

---

## S2-3 桥比例 β（语义-only）

**规则**：β 只使用 `E_sem` 的跨簇语义边；`E_out(C)={e∈E_sem | 恰一端∈C}`；`β(C)=|distinct pairs E_out|/(|pairs E_in|+|pairs E_out|)`；无任何语义边时 β 无定义（`null`/`no_semantic_edges`），不得当 0；τ_bridge ∈ [0,1)、**暂定默认 0.25**（A-v2 probe 出处同 S2-2；B 独立复算 pending；S8 复标定）；singleton 豁免。

**机检**：
```python
assert input_edge_set(beta) == E_sem        # 不得含 reference/structural
assert beta==null if denom==0 else 0<=beta<=1
assert tau_bridge is None or 0<=tau_bridge<1
assert singleton beta not used
```
**反例**：用 structural/reference 当桥（P0-1）；β 用节点数；无外部边把 β=0 当最优；单点桥遗漏；τ 未标定使用。
**边界**：β=0（孤立/全库根）；β=1（几乎无内部）；单锚点桥多（诊断）；同 pair 去重。
**U 映射**：U-13、U-14、U-17。
**建议裁决**：冻结语义-only β 公式 + τ_bridge 类型/范围/失败；无定义标 null；诊断量 bridge_per_member/single_anchor 只报告。
**证据等级**：A（S0-1/S0-4/R-S2-1）+ R（R-S2-2）+ PI（诊断）。

---

## S2-4 确定性 HAC 算法契约（R-S2-3）

**规则**：v1 主算法 = **纯自实现确定性 HAC（average-linkage）**，无第三方网络库依赖；冻结伪代码/距离/链接/tie-break/序列化/golden 2x；naive 约束合并最坏 **O(n³)**（每轮 O(n²) 对 + 每对 O(n) 计算），必须设 `n_max` 上限与 `degraded`；Louvain/CNM 不作 v1 主路径；失败/超限显式降级，不得回退连通分量。

**符号**：`K_f` = view_family 的 KP 集；`E_sem` 语义边；`n=|K_f|`；`params = {tau_coh, tau_bridge, linkage="average", n_max, seed="none"}`。

**伪代码（确定性）**：
```
def hac_semantic(K_f, E_sem, params):
    # 0) 参数/输入校验
    if E_sem is empty: return Degraded("no_semantic_edges", clusters=singletons(K_f))
    if tau_coh is None or tau_bridge is None: return Degraded("uncalibrated")
    if n > params.n_max: return Degraded("size_exceeded")
    clusters = [frozenset([k]) for k in sorted(K_f)]          # canonical order
    # 1) 初始 pair similarity（average-linkage on semantic adjacency）
    sim[A,B] = |E_sem_between(A,B)| / (|A|*|B|)              # 0..1；无向语义边端点对
    # 2) 每轮选 sim 最大且 merge 后合法的 pair；tie-break 严格字典序
    while True:
        cand = []
        for A,B in pairs(clusters, ordered by min member id):
            M = A|B
            if mu(M)>=tau_coh and beta(M)<=tau_bridge:
                cand.append((sim(A,B), A, B))
        if not cand: break
        best_sim = max(c[0] for c in cand)
        tied = [c for c in cand if c[0]==best_sim]
        choose (A,B) with lexicographically smallest (sorted(A|B)) # min canonical
        clusters = replace A,B by A|B; recompute sim with new cluster
    return Ok(clusters)     # 剩余 singleton 保留；partition
```
- 链接准则：**average-linkage**（簇间语义边数/可能对数）；无向语义边按 endpoint pair 去重；不引入权重。
- tie-break：`(sim 最大, 合并后成员集合字典序最小)`；成员按 canonical id 排序。
- 序列化：`canonical_json`（键排序、UTF-8、无空白、成员/边 id 排序）；`partition_sha=sha256(canonical_json(partition))`；golden 两次运行 `partition_sha` 及完整输出字节一致。
- 输出：clusters、memberships、μ/β、status；singlepoint 保留。
**O(n²) 上限/降级**：
```
n_max 参数（S8 定；示例 2000 非规范）；n>n_max ⇒ status=size_exceeded, clusters=singletons, warning
算法异常/超时 ⇒ status=algorithm_failed, clusters=singletons（不伪造簇）
语义图不连通导致无法继续合并 ⇒ status=partial_disconnected（返回当前划分，合法，不伪造合并）
无 E_sem ⇒ no_semantic_edges；τ null ⇒ uncalibrated
```
**机检**：
```python
run1,run2 = hac_semantic(...), hac_semantic(...)
assert canonical_bytes(run1)==canonical_bytes(run2)         # golden 2x
assert partition valid (cover/disjoint) and μ/β only E_sem
assert status in {ok,no_semantic_edges,uncalibrated,size_exceeded,algorithm_failed,partial_disconnected}
assert no ThirdPartyGraphLib imported; no UnionFind cluster definition
```
**反例**：随机 pair/字典顺序不稳定；平局用哈希/内存顺序；用 UnionFind 当 fallback；超限静默全库簇；weighted non-semantic；golden 只比簇数。
**边界**：n=0/1；E_sem 空；全 singleton；n>n_max；平局；簇合并后 β 变化；大图 O(n²) 预算 S9/S8。
**U 映射**：U-4、U-6、U-13、U-14、U-32。
**建议裁决**：冻结 HAC 契约/序列化/golden/degraded；v1 不引入第三方/不引入 Louvain；O(n²) 上限与降级显式。
**证据等级**：A（`graph-groups.js` 反例；U-13/U-14）+ R（R-S2-3）+ PI（n_max/参数示例）。

---

## S2-5 稳定性（Jaccard+churn；触发）

**规则**：run 不可变；触发=manifest/语义边集（E_sem）变化/算法/参数变化/显式请求；稳定性度量=成员 Jaccard + churn + split/merge + cluster_count_delta；v1 全量重算，不做增量覆盖；阈值/门禁 S8。

**形式化**：
```
match: 对每个 new N 找 old O 最大化 J=|N∩O|/|N∪O|（一对一贪心，tie by cluster_key）
jaccard_weighted = Σ_N |N|*J(N,best)/|K_f|
churn = 1 - Σ_N |N∩best|/|K_f|
split/merge = 新/旧簇数差与拆并计数
```
**机检**：同输入无触发 ⇒ 同 run/簇（cache hit）；触发后新 run；metrics 可复算；旧 run 只读；跨 view_family/level 不比较。
**反例**：刷新重算；覆盖旧 run；只用簇数；cluster_key 当唯一匹配（成员变化→失配）。
**边界**：首次 run（initial/null）；小改动 J 高；算法版本变化；语料重构大量 split/merge 报告但不阻断。
**U 映射**：U-21、U-22、U-31。
**建议裁决**：冻结触发清单 + Jaccard/churn/稳定性记录；v1 全量；阈值 S8。
**证据等级**：A（S0-7/D-2）+ C（U-22）+ PI（匹配规则）。

---

## S2-6 多归属（与 S0-7/S1 partition 一致）

**规则**：membership 多对多；**同一 `(level,view_family)` 内每个 KP 恰属一个块**；跨 view_family/层次/维度允许重叠；不设上限；成员关系 ≠ 视图出现；`Membership.role` **不得复用 S1 node role=bridge**（bridge 只作边状态/统计）；v1 不写产品。

**机检**：
```python
for fam in families:
    assert all(sum(kp in c.members for c in clusters_in(fam))==1 for kp in K_f)
assert cross_family_overlap_allowed
assert cap is None  # v1 no hard cap
assert "bridge" not in membership.role
```
**反例**：单值 parent；同族重叠；上限静默截断；role=bridge 混淆 S1；视图出现写回 membership。
**边界**：跨层各一块；跨族重叠；单点块；不设上限。
**U 映射**：U-21、U-31（+U-6）。
**建议裁决**：冻结"同族 partition/跨族多归属/不设上限/role 不含 bridge/不写产品"。
**证据等级**：A（S0-7/S1 R-2；`graph-groups.js:123-126` 单值反例）+ R（R-S2-7）。

---

## S2-7 簇身份（run=(level,view_family)+D-2）

**规则**：run 粒度 = **`(level, view_family)`**；`cluster_run_id = sha256(canonical(corpus_manifest_sha, view_family_id, level_id, algorithm_id, algorithm_version, params_hash))`；父子层用 `parent_run_id` 关联；`local_seq` 按成员最小 canonical id 排序；`cluster_key` 按 D-2；curation/审计引用同时记 run_id+cluster_key；成员变化 ⇒ key 变化/stale，不静默套用。

**形式化**：
```
run_id = sha256(canonical(corpus_manifest_sha, view_family_id, level_id, algo_id, algo_version, params_hash))
parent_run_id = run_id(level-1, same view_family) or null
local_seq = 1..N sorted by min(member_canonical_ids)（tie by cluster_key）
cluster_instance_id = f"{run_id}:{local_seq}"
cluster_key = sha256(canonical(sorted(member_canonical_ids), algo_id, algo_version, params_hash))
curation_ref = {run_id, local_seq, cluster_key}
```
**机检**：run_id 公式含 level；parent_run_id 同 family/上一层；local_seq 唯一可复算；cluster_key 可复算；curation 引用完整；key 不匹配 stale。
**反例**：run_id 不含 level（旧 A）；内容哈希当实例 id；local_seq 随机；curation 只记 key；旧 run 被覆盖。
**边界**：首次层；父子层；成员变化；算法版本；同层多 run 历史。
**U 映射**：U-6、U-21、U-31。
**建议裁决**：冻结 per-(level,family) run + run_id 公式 + parent_run_id + local_seq 排序 + D-2 key/curation。
**证据等级**：A（S0 D-2）+ R（R-S2-4）+ PI（排序细节）。

---

## S2-8 嵌套、展开、单点、root

**规则**：同 `(level,view_family)` 内 Π 为 partition；跨层 Π_{ℓ+1} 精化 Π_ℓ；展开到 KP；空簇禁止；单点允许但 `μ=null`、`representative=false`；L0 全库单块 `root_exempt=true`（非普通簇）；degenerate refinement 显式标记。
**机检**：
```python
assert refinement: every child subset unique parent
assert expand_to_kp(c) nonempty <=K
assert empty==0; singleton.mu is None and not representative
assert root_exempt only L0; degenerate_refinement explicit
assert H data_edge_ids exist per S1 R-S1-11 (may be empty)
```
**反例**：子簇越父；展开非 KP；空簇；singleton representative；L0 root 当普通簇；H 边缺 data_edge_ids。
**边界**：父仅 1 子（degenerate）；L0 root；叶层全单点；数据缺失 unknown。
**U 映射**：U-5、U-6、U-7、U-19、U-28。
**建议裁决**：冻结 refinement/展开/单点/root/degenerate；H 派生边按 S1。
**证据等级**：A（S0-2；S1 R-S1-11）+ R（R-S2-6）。

---

## S2-9 簇与边（internal/bridge/data_edge_ids）

**规则**：μ/β 只用 `E_sem`；internal/bridge 均指语义边；structural contain 只作结构诊断/背景，**不进 μ/β**；聚合/派生边带 `data_edge_ids`（R-3）；H 派生边按 S1 R-S1-11（可空集、字段必存在）；桥的呈现归 S4。
**机检**：
```python
assert mu_beta_input == E_sem
assert all(aggregated_cluster_edges.data_edge_ids nonempty and subset DataSource)
assert H edges have data_edge_ids field (may be empty)
assert internal endpoints same cluster; bridge exactly one endpoint
```
**反例**：structural/reference 进 μ/β；聚合边无 data_edge_ids；bridge 当 internal；H 边缺字段。
**边界**：同 pair 多类型 semantic 边；单桥；结构诊断；空 H 边字段。
**U 映射**：U-13、U-15、U-17。
**建议裁决**：冻结语义-only 边集 + data_edge_ids + 桥呈现 S4。
**证据等级**：A（S0 R-3；S1 R-S1-11）+ R（R-S2-1）。

---

## S2-10 簇与维度/层次（A 不改变簇；机检伪代码）

**规则**：簇只由 H 的 `(level,view_family)` 产生；A 维度不参与构建、不改变 cluster run/membership；维度切换不触发重聚类；`cluster_run_id` 输入固定 hierarchy view_family（不含 A 的 dimension 参数）。
**机检伪代码**：
```python
def assert_dimension_invariance(ds, params, family):
    run_h = build_clusters(ds, params, level, family, dimension_id="hierarchy")
    run_a = build_clusters(ds, params, level, family, dimension_id="association")
    # cluster 构建 API 不接受 dimension_id（或忽略），两者必须同 run_id/同 partitions
    assert run_h.run_id == run_a.run_id
    assert run_h.partitions == run_a.partitions
    assert run_h.memberships == run_a.memberships
    # A 只影响 frame/present，不影响 clusters
    assert frame_h.dimension_id != frame_a.dimension_id  # 仅视图不同
```
**反例**：A 下重新聚类；A 挂接节点写 membership；A 的 dimension_id 进 run_id；切换维度触发新 run。
**边界**：A 可见节点不属簇（appearance）；跨族多归属；H 每层独立。
**U 映射**：U-8、U-10、U-21、U-30。
**建议裁决**：冻结"A 不改变簇"及上述机检；run 输入固定 H family。
**证据等级**：A（S0-7；S1 H/A 分工）+ R（R-S2-7）。

---

## S2-11 持久化与缓存（D-3）

**规则**：簇/成员/边/run 是派生缓存（可重建、非事实源）；不写产品 sidecar/新拓扑段；缓存键=run_id；旧 run 只读；profile/GC S6；不写用户正文/manifest。
**机检**：写路径不在 sidecar/新段；缓存可从 DataSource+params 重建同 run_id/内容；旧 run 只读；agent 无写路径。
**反例**：写 sidecar；缓存不可重建；删旧 run；缓存当事实。
**边界**：缓存缺失/损坏 ⇒ 重算；跨版本 schema 丢弃；D-3。
**U 映射**：U-21、U-31、U-32。
**建议裁决**：冻结派生缓存/禁产品写/可重建/旧 run 保留；S6 定路径/GC。
**证据等级**：A（S0 D-3）+ R（R-S2-8）。

---

## S2-12 度量与验收（G6 可复跑）

**规则**：每 run 输出指标并进 G6 快照；S2 冻结指标定义/字段，数值门禁 S8。
**指标**：
```
per cluster: |C|, μ (null for singleton), β, bridge_per_member, representative, singleton flag
per run: status, cluster_count, size_distribution, singleton_count/ratio,
         coverage = |∪_{C: representative=true} members(C)| / |K_total|   # 只计代表簇；singleton 不计；E_sem=0 ⇒ 0
         determinism_hash = sha256(canonical partitions)
per pair runs: jaccard_weighted, churn, split/merge, cluster_count_delta
G6 fields: corpus_manifest_sha, run_id, level_id, view_family_id, parent_run_id,
           algorithm_id/version, params_hash, cluster_key list, membership digest,
           E_sem digest, μ/β summary, coverage, stability summary, status
```
**机检**：同输入 2x `determinism_hash` 相同；coverage 公式正确；G6 字段齐全；降级 status 显式；指标可从 run 复算。
**反例**：coverage=Σ|C|/|K| 恒 1（R-S2-6 修正）；只报簇数；降级当正常；G6 缺 manifest/level/params；稳定性无 previous。
**边界**：首次 run；E_sem 空（no_semantic_edges）；全 singleton；root_exempt；不同 level 不比较稳定性。
**U 映射**：U-2、U-13、U-32。
**建议裁决**：冻结指标/G6 字段/coverage 公式/可复跑；数值 S8。
**证据等级**：A（S0/S1 验收模式）+ R（R-S2-6/R-S2-8）+ PI（字段）。

---

## S2-13 与 agent（只读 + 候选 run）

**规则**：v1 agent **只读**现有 run；可请求**新建候选 run**（必须 `requester/reason/params` 审计），候选状态 `candidate`，**不自动采用**（人/S5 决定）；不得写 membership/缓存/manifest/渲染状态；不得自动改参数；跨 KB 拒绝。
**形式化**：
```
agent 允许：read run; request_candidate_run(params, reason, requester)
agent 禁止：write membership/cache/manifest/render state; adopt run; change params silently
状态：candidate（审计、可丢弃） vs adopted（人/S5 选择）；默认视图只读 adopted
审计：{requester, reason, params_hash, run_id, corpus_manifest_sha, created_at, status}
```
**机检**：agent 无写 API；请求必带审计；candidate 不自动 adopted；参数变更不静默生效；跨 KB 拒绝；runner 纯函数。
**反例**：agent 写缓存/覆盖 run；agent 自动 adopted；无审计请求；agent 改 params 后当事实。
**边界**：缓存缺失 agent 只读触发重算? 应由服务；candidate 被丢弃；离线/失败降级。
**U 映射**：U-2、U-29、U-32。
**建议裁决**：冻结只读+候选 run+审计+不自动采用；S9/S7 后续选采用策略。
**证据等级**：A（S0-10/S1-14）+ R（R-S2-5）。

---

## 附：R-S2 自检（8 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S2-1 μ/β 只 E_sem | S2-2/S2-3/S2-9（输入断言 + 反例） |
| R-S2-2 τ probe/类型/失败 | S2-2b（frozen 0 语义边/演示库/标定流程/τ null/非法） |
| R-S2-3 HAC 契约 | S2-4（伪代码/linkage/tie-break/序列化/golden/n_max/degraded） |
| R-S2-4 run 身份 | S2-7（per (level,family)/run_id 含 level/parent/local_seq/key） |
| R-S2-5 agent | S2-13（只读+candidate run+审计+不自动采用+禁写） |
| R-S2-6 singleton/root/coverage | S2-1/S2-2/S2-8/S2-12（μ=null/representative=false/root_exempt/coverage 公式） |
| R-S2-7 role/A 不变 | S2-6/S2-10（membership role 不用 bridge；A 不变机检） |
| R-S2-8 并集 A | S2-2b/S2-1/S2-4/S2-12（probe/root/降级/G6） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S2-objections-v2.md`；未写产品代码/契约，未 commit。
