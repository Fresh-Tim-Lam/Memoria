# S2 提案 A-v2：簇与子图划分（语义-only μ/β + 确定性 HAC + 稳定身份）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-303｜**日期**：2026-11-03（Asia/Shanghai）
> **唯一修订依据**：`docs/design/multilevel-graph/S2-RULINGS.md`（R-S2-1..R-S2-8；Lead 已复核 P0/P1）。
> **最高依据**：`multilevel-graph-vision.md`（U-1..U-35）；上游冻结：`S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）。
> **本文件**：A 的修订版；**不覆盖** `S2-clustering-proposal-A.md`（v1，`b14bb379…`），保留审计链。
> **纪律**：不写产品代码、不改 S0/S1 冻结稿/契约、不 commit；独立写。

---

## 0. 修订摘要（R-S2 → 结构变化）

| 裁决 | v1 问题 | v2 落实 |
|---|---|---|
| **R-S2-1（P0）** μ/β 语义污染 | v1 weight_policy 把 reference 0.2 / structural contain 0.5 / 非 semantic extend 0.3 计入 μ/β | **μ/β 只用 `E_sem`（label=semantic）**；reference/structural/非 semantic extend 权重 0，只作结构诊断（`diag_*` 字段，不参与簇成立）；机检「μ/β 输入边集 == E_sem」 |
| **R-S2-2** τ 标定 | v1 τ=0.04/0.15 来自含结构边的 probe | 语义-only probe 重跑（frozen + 演示库 + 合成语义夹具），产物 `artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/results.json`；**τ_coh=0.5 / τ_bridge=0.25**（S8 可复标定）；允许"几乎无簇"为合法状态 |
| **R-S2-3** 算法 | v1 seeded Louvain（第三方 networkx 未批） | v1 主算法 = **纯自实现确定性 average-linkage HAC**；冻结伪代码/tie-break（min canonical id）/canonical 序列化/golden 两次逐字节一致；失败显式 `degraded`，不静默回退连通分量 |
| **R-S2-4** run 粒度 | v1 每 view_family 一个 run 含所有层 | run 粒度 = **`(level, view_family)`**；`cluster_run_id=sha256(canonical(corpus_manifest_sha, view_family_id, level_id, algorithm_id, algorithm_version, params_hash))`；`parent_run_id` 连接父子层；`local_seq` 按最小 canonical id 排序 |
| **R-S2-5** agent | v1 允许请求重聚类/改参数 | v1 agent **只读** + 可请求"新建候选 run"（`requester/reason/params` 审计；`candidate` 不自动采用、不覆盖旧 run）；不得改 membership/缓存/manifest/渲染状态 |
| **R-S2-6** singleton/root/覆盖 | v1 singleton μ=1、coverage 恒 1 | singleton `μ=null`、`representative=false`；L0 全库一簇显式 `root_exempt=true`；**coverage = 覆盖 KP 数 / 全库 KP 数**（非 Σ|C|/|K|） |
| **R-S2-7** 命名/角色 | v1 Membership.role 含 bridge | `Membership.role` 不复用 S1 node `role=bridge`；桥只作**边状态**（`bridge_only`）与统计；node kind 仍 `{kp,cluster}`；A 不改变簇（补机检伪代码） |
| **R-S2-8** 并集 | — | 吸收 B 的 HAC/覆盖公式/只读 agent/语义纯净；保留本提案 frozen probe 方法、root_exempt、降级路径、G6 字段；**`weight_policy` 进 `params_hash`** |

**数据流**：`DataSource → (确定性服务 build_clusters) → ClusterRun(派生缓存) → ViewModel/H`；簇不写产品事实源（D-3）。

**证据等级**：A（原话/冻结契约/决策/可复跑代码）；B（本场语义-only probe）；C（单源推理）；**本项目假设**（τ 默认值、HAC tie-break 等显式约定）。

---

## 1. S2-1 簇定义与边界（≠ 严格连通分量；语义证据独占）

**定义/规则（一句话）**：簇是**同一 `(level, view_family)` 下、由 `E_sem` 语义边证据支撑的成员块**：语义内聚 μ 达标、语义桥 β 不超标；结构/引用边/非 semantic extend **不参与簇成立**；簇 ≠ 严格连通分量。

**形式化**：
```
E_sem = { e ∈ DataSource.edges | label(e)=semantic }        # S0-1；见 §2
E_struct_diag = DataSource.edges \ E_sem                     # 只作结构诊断/背景，权重 0
C ⊆ K_f（同 family/level）
μ(C) 基于 E_sem（§2）；β(C) 基于 E_sem（§3）
簇条件（|C|≥2）：μ(C)≥τ_coh ∧ β(C)≤τ_bridge
|C|=1：singleton 块（μ=null、representative=false；§6）
划分 Π_ℓ,f：块两两不交、非空、并=K_f；空簇禁止
严格连通分量（graph-groups 并查集）≠ 簇；只可作失败诊断，不得作为 v1 cluster 实现
```
**边界**：空簇禁止；singleton 允许但不作代表节点；L0 全库一簇 `root_exempt=true`（显式，非普通簇）；ℓ>0 不得"整库一簇"（降级/失败可见）；跨族可重叠（S2-6）；同族同层禁止重叠。
**机检条件**：
```
- 每个 |C|≥2 的块的 μ/β 只由 E_sem 计算：assert used_edges(C) ⊆ E_sem（§2 机检）
- 同族同层 partition（S0-2 V5）；空块不存在
- 代码/服务层无 graph-groups/并查集作为 cluster 实现
- root_exempt 仅 L0；singleton representative=false
```
**反例**：把 graph-groups 并查集分组当簇；用 reference/structural 边把"孤立对"凑成 μ>τ 的簇（v1 P0）；ℓ>0 整库一簇；同族同层重叠；空块。
**U 映射**：U-6、U-13、U-14、U-21、U-31。
**建议裁决**：采纳；簇只由 E_sem 支撑；结构/引用只作诊断；禁止并查集当簇。
**证据等级**：A（U-13/U-14；S0-1/S0-4 `S0-terms-v1.md:21-26,43-47`；`graph-groups.js:2,83`）；**本项目假设**（singleton/root 边界，沿用 v1）。

---

## 2. S2-2 语义内聚度 μ（E_sem-only；阈值/参数）

**定义/规则（一句话）**：`E_sem` 是唯一簇证据边集；μ 是**语义内部密度** `μ(C)=|E_sem(C)|/P(C)`（单位权 1.0），`P=|C|(|C|-1)/2`；τ_coh 参数化，v1 默认 **0.5**（由语义-only probe 标定）。

**形式化**：
```
E_sem 判定（S0-1，fail-closed）：
  reference                              → 永不算语义
  contain ∧ contain_kind=semantic        → 需 derived_by=author ∧ assertion_source
                                            ∧ curated_by ∧ curated_at（v0.3 校验器）
  extend                                 → 需作者断言/证据（derived_by=author ∧ assertion_source）
  其它/字段不全                          → 非语义（不得猜测）
weight_policy v1：semantic_uniform（E_sem 内每条边权 1.0；不含任何结构/引用边）
μ(C) = |E_sem(C)| / (|C|(|C|-1)/2)   （|C|≥2；单位权密度）
μ(C) = null                           （|C|=1，singleton 豁免）
τ_coh ∈ (0,1]，默认 0.5；参数非法/非有限 ⇒ fail-closed（S2_PARAM_INVALID）
```
**τ 标定（R-S2-2，probe 产物）**：
- 产物：`artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/results.json`（脚本 `probe.py`，纯研究代码）；
- frozen 语料（357 KP/62 边）与演示库 `docs/example/showcase`（35 KP/73 边）**E_sem 均为 0** ⇒ 合法状态"几乎无簇"（所有块 singleton，coverage=0），**不得用结构边凑簇**；
- 合成语义夹具（语义-only，显式 synthetic，不是语料结构边）用于标定：
  - `two_triangles_bridge`（两个三角以一条桥相连）：HAC 切 k=2 得 2 个簇，μ=0.667/1.0、β=0.2/0.25，均合格；
  - `pair/triangle/star4/path*` 用于检查边界（见 probe results）；
  - 取 **τ_coh=0.5、τ_bridge=0.25** 可区分"语义内聚块"与"链/星/孤立边"（细节见 §3/probe）。
- **限制**：真实语料无 E_sem，τ 不能称"live 标定"；S8 在有 semantic curation 的语料上必须复标定（S2 冻结公式+默认值+出处，不冻结永久数值）。

**机检条件**：
```
- 每个 |C|≥2：assert μ(C)=|E_sem(C)|/P；assert used_edges(C) ⊆ E_sem
- 若任何 reference/structural/非 semantic extend 出现在 μ 输入 ⇒ S2_SEMANTIC_PURITY_FAIL
- singleton μ=null；非 singleton μ 必须是 [0,1] 浮点
- τ_coh 进入 params_hash；非法参数 fail-closed
- E_sem=0 ⇒ 全部 singleton + status=ok/empty（合法），不得退化用结构边
```
**反例**：v1 的 structural 0.5/reference 0.2 权重（P0：一条 reference 边即可让 μ=0.2>τ）；用"名字相似"冒充语义边；字段不全的 semantic contain 当 E_sem（应 fail-closed 非语义）；τ 硬编码在代码。
**边界**：|C|=2 一条语义边 ⇒ μ=1；无内部 E_sem ⇒ μ=0（不合格）；E_sem=0 ⇒ 无簇合法；E_sem 稀疏 ⇒ 少簇合法（S4/S3 处理退化视图）。
**U 映射**：U-1、U-13、U-14。
**建议裁决**：采纳 E_sem-only 密度公式 + semantic_uniform + τ_coh=0.5；E_sem=0/少簇合法；S8 复标定。
**证据等级**：A（S0-1 `S0-terms-v1.md:21-26`；S0-4 `:43-47`）；B（本场 probe：frozen/showcase E_sem=0；synthetic two-triangles 标定）；**本项目假设**（τ_coh=0.5、单位权）。

---

## 3. S2-3 语义桥 β（E_sem-only；阈值）

**定义/规则（一句话）**：桥边 = 恰有一端在 C 内的 **E_sem** 边；`β(C)=|E_sem_bridge|/(|E_sem_internal|+|E_sem_bridge|)`；τ_bridge 默认 **0.25**；reference/structural 桥只作结构诊断，不计入 β。

**形式化**：
```
E_sem_bridge(C) = {e∈E_sem | |端点在 C|=1}
E_sem_internal(C) = {e∈E_sem | 两端均∈C}
β(C) = |E_sem_bridge| / (|E_sem_internal|+|E_sem_bridge|)   # 无 E_sem 关联时 β=0
τ_bridge ∈ [0,1)，默认 0.25
诊断（不参与判定）：
  diag_struct_bridge(C) = 非语义边（含 contain structural/reference）形成的桥计数/权重
  single_anchor_bridge(C) = 外部端点只与 C 有一条 E_sem 边的桥
簇条件：β(C) ≤ τ_bridge（|C|≥2）
```
**反例**：把 structural contain 的跨边计入 β 导致"结构桥"否决语义簇；把桥数绝对值当阈值（簇大小敏感）；β=1 判合格；对 singleton 计 β。
**边界**：β=0 ⇒ 也可同时是语义连通分量（允许，定义不要求）；β=1 ⇒ 无内部语义（不合格）；单锚点桥 ⇒ 警告（诊断），v1 不单独硬拒；结构桥（diagnostic）不影响簇成立。
**机检条件**：
```
- β 计算只用 E_sem：assert β_edges ⊆ E_sem（任意外部边出现 ⇒ FAIL）
- β(C)∈[0,1]；|C|≥2 的合格簇 β≤τ_bridge
- 诊断字段 diag_struct_bridge 只读、不得参与 valid 判定
- τ_bridge 进 params_hash；非法 fail-closed
```
**U 映射**：U-13、U-14、U-15。
**建议裁决**：采纳 E_sem-only β + τ_bridge=0.25；结构桥仅诊断；S8 复标定。
**证据等级**：A（U-13；S0-4）；B（probe：two_triangles_bridge β=0.2/0.25 合格）；**本项目假设**（τ_bridge=0.25、诊断字段）。

---

## 4. S2-4 划分算法：确定性 HAC（纯自实现；无第三方）

**定义/规则（一句话）**：v1 主算法 = **average-linkage 层次凝聚聚类（HAC）**，只用 `E_sem`、纯 Python 自实现、无第三方图库；冻结链接准则/tie-break/序列化，同输入两次运行**逐字节一致**；失败或超显式上限 ⇒ `degraded`，不得回退连通分量。

**候选与选型**：
| 候选 | v1 | 说明 |
|---|---|---|
| **average-linkage HAC（纯自实现）** | ✅ 主选 | 确定性、可复算；O(n²·merges) 最坏 O(n³)，规模上限归 S8 |
| 单链接/全链接 HAC | 备选（S2 修订） | 单链接易链式；全链接偏紧；v1 固定 average |
| Louvain/CNM/networkx | ❌ v1 | 第三方依赖未批；R-S2-3 明确不改主路径 |
| 连通分量（并查集） | ❌ 禁止当簇 | 仅诊断；不得静默回退 |

**冻结伪代码**：
```python
def hac_semantic(K_f, E_sem, target_k):        # 纯 Python；无第三方
    clusters = {frozenset([k]) for k in sorted(K_f)}     # 节点按 canonical id 排序
    merges = []
    while len(clusters) > target_k:
        best = None
        ordered = sorted(clusters, key=lambda c: (min(c), len(c)))
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                A, B = ordered[i], ordered[j]
                w = count_E_sem_between(A, B)          # 只数 E_sem 边
                if w == 0: continue
                linkage = w / (len(A) * len(B))        # average linkage（单位权）
                key = (linkage, min(A), min(B))        # tie-break: min canonical id
                if best is None or key > best[0]:
                    best = (key, A, B, w)
        if best is None: break                         # 语义图不连通：无法继续合并
        _, A, B, w = best
        clusters -= {A, B}; clusters.add(A | B)
        merges.append({"a_min": min(A), "b_min": min(B), "linkage": linkage, "size": len(A|B)})
    return canonical_partition(clusters), merges    # 按 (min id, size) 排序
```
**分层/级别**：
```
- 同一 (view_family, E_sem, params) 先构建一次 dendrogram（HAC 合并序列），记录 dendrogram_sha。
- 每层 ℓ 的 run = 对同一 dendrogram 按 target_k_ℓ 切分（target_k 进入该 run 的 params_hash）；
  - 同一 dendrogram 保证嵌套（Π_{ℓ+1} 是 Π_ℓ 的 refinement）；
  - parent_run_id = 上一层 run_id（同 family）。
- target_k 序列由 S8/S4 定（如按簇数/可视预算），S2 只冻结"每层一个 run + 同 dendrogram 切分"的规则。
```
**序列化/golden**：
```
canonical_partition = JSON 数组：每个簇成员按 canonical id 升序，簇按 (min id,size) 升序；无浮点；
golden = sha256(canonical_partition)；两次运行 golden 必须相同（machine check）。
merges 记录 linkage 以固定小数位（如 6）序列化；不参与 run identity 之外的比较。
```
**降级/失败语义**：
```
status ∈ {ok, empty, partial_disconnected, degraded}
  ok: 达到 target_k 或正常终止
  empty: E_sem=∅ ⇒ 全 singleton（合法，coverage=0；不是 degraded）
  partial_disconnected: 语义图不连通导致 len(clusters)>target_k；返回当前划分（合法，不伪造合并）
  degraded: 参数非法 / n>max_nodes(S8) / 算法异常；返回失败码 + 不输出"正常簇"
禁止：任何状态静默回退到连通分量（graph-groups）当簇。
```
**机检条件**：
```
- 不得 import networkx/igraph/lein/community 等未批依赖（import 白名单/S6 检查）
- 同 (K_f,E_sem,params_hash) 两次运行 canonical partition 逐字节一致（golden）
- 合并只沿 E_sem 正权边；tie-break = min canonical id（伪代码审计）
- status∈{ok,empty,partial_disconnected,degraded}；degraded 不产出正常簇
- 无 graph-groups/并查集调用作 cluster 实现
```
**反例**：用 Louvain/networkx（未批依赖）；随机 tie-break；扁平算法伪造嵌套；E_sem=0 时用结构边凑簇；失败时静默返回连通分量；浮点序列化不稳定导致 golden 不同。
**边界**：E_sem=0 ⇒ empty（全 singleton）；语义图不连通 ⇒ partial_disconnected（簇数>target_k 合法）；单层 target_k=1 且 E_sem 不连通 ⇒ partial；n 超大 ⇒ S8 上限 + degraded；只有 2 个 KP 有 1 条语义边 ⇒ k=1 得一个 2 簇（μ=1、β=0）合格。
**U 映射**：U-4、U-6、U-13、U-14、U-32。
**建议裁决**：采纳纯自实现 average-linkage HAC + canonical/tie-break/golden + 四态状态；禁止第三方与连通分量回退。
**证据等级**：A（R-S2-3 `S2-RULINGS.md:32-35`；U-13/U-14；`graph-groups.js:2,83` 反例）；B（probe：HAC 两次 golden_equal=true；纯 Python 无第三方）；**本项目假设**（average 链接、tie-break 细节、target_k 序列归 S8）。

---

## 5. S2-5 稳定性（不可变 run；per-level 触发/度量）

**定义/规则（一句话）**：每次 `(level, view_family)` 聚类是**不可变 run**；`E_sem`/语料/算法/参数变化 ⇒ 新建 run；稳定性用新旧 run 的成员 Jaccard、churn、split/merge、簇数差度量；v1 全量重算，不原地修改。

**形式化**：
```
run 输入 = ⟨corpus_manifest_sha, view_family_id, level_id, algorithm_id, algorithm_version, params_hash⟩
触发：E_sem 变化（semantic curation/边派生变化）∨ 语料 manifest 变化
      ∨ 算法/参数变化 ∨ 显式请求（人/agent 候选 run）；不按时间自动
稳定性度量（同 family/level 的新旧 run）：
  best_match(N) = argmax_{O in old} Jaccard(N,O)（tie 按 cluster_key）
  jaccard_weighted = Σ_N |N|·J(N,best_match(N)) / |K_covered∪...|（报告口径）
  churn = 1 - Σ_N |N∩best| / |K_f|
  split/merge = 新/旧簇数差与匹配拆分/合并计数
  cluster_count_delta
record: CLUSTER_STABILITY（run_id, previous_run_id, metric, value, threshold?, pass?）
```
**反例**：新 run 覆盖旧 run；按时间重聚类；只比簇数；用 cluster_key 当匹配键（成员变化即失配）；跨 level 比较（不同粒度）。
**边界**：首次 run ⇒ stability=initial（无 previous）；E_sem 很少时稳定性天然低（合法）；大改语料 ⇒ split/merge 多（报告，不阻断）；阈值/门禁归 S8，S2 只定义测量与记录。
**机检条件**：
```
- 每 run 有 corpus_manifest_sha/level/view_family/algorithm/version/params_hash；旧 run 只读
- metrics 可由 run 的 memberships 复算；同输入重复计算一致
- 跨 level 不做稳定性比较；previous_run_id 同 family
```
**U 映射**：U-21、U-22、U-31。
**建议裁决**：采纳不可变 per-level run + Jaccard/churn 度量 + 全量重算；门禁 S8。
**证据等级**：A（S0-7/D-2；`ENGINEERING-PLAN.md:401-412,439-447`）；**本项目假设**（匹配/tie 规则、触发清单）。

---

## 6. S2-6 多归属、singleton、root、覆盖率（R-S2-6）

**定义/规则（一句话）**：membership 多对多；同 `(level, view_family)` 单归属、跨族/层/维多归属；singleton `μ=null`、`representative=false`；L0 全库一簇 `root_exempt=true`；coverage = 覆盖 KP 数 / 全库 KP 数（非恒 1）。

**形式化**：
```
Membership = ⟨run_id, cluster_id, kp_id, role, weight?, source=derived_cluster, provenance⟩
  role ∈ {member}（v1；不复用 S1 node role=bridge；§S2-7）
  同 (level, view_family)：每个 kp 恰属一块（partition）
  跨 level（同 family）：嵌套包含（每层各一块）
  跨 view_family：多归属允许（S0-7）；v1 不设上限（max_memberships_per_kp=null，S6 可配）
  membership ⇏ appearance；appearance 由 S1 present/VM 决定
singleton：|C|=1 ⇒ μ=null、representative=false；不是"代表子图节点"
root_exempt：L0 的整库单块显式标记 true；不是普通簇
coverage = |∪_{C: representative=true} members(C)| / |K_total|
  （singleton 不计入覆盖；E_sem=0 ⇒ coverage=0 合法）
```
**反例**：nodeToGroup 单值当 membership（`graph-groups.js:123-126`）；coverage 用 Σ|C|/|K| 恒 1（掩盖无簇）；singleton μ=1/representative=true；L0 整库簇不标记 root_exempt；role=bridge 复用到 membership。
**边界**：单 KP 各层各一块；跨族多块；`max_memberships_per_kp=null`；coverage=0（E_sem=0）合法；root_exempt 只 L0。
**机检条件**：
```
- 同 (level,view_family) 每个 kp 恰好一块；空块禁止
- singleton: μ=null ∧ representative=false；root_exempt 仅 L0
- coverage = |union(representative clusters)| / |K_total|（分母全库 KP，不是 Σ）
- Membership.role 枚举不含 bridge；node kind 仍 kp/cluster
- v1 max_memberships_per_kp=null（或正配置）
```
**U 映射**：U-19、U-21、U-22、U-31。
**建议裁决**：采纳多归属多对多 + singleton/root/coverage 语义；v1 不设上限；role 不复用 bridge。
**证据等级**：A（U-21/U-31；S0-7；`ENGINEERING-PLAN.md:111-121,423-430`）；**本项目假设**（role 枚举/上限留 S6）。

---

## 7. S2-7 簇身份（per-level run_id + local_seq + cluster_key；D-2）

**定义/规则（一句话）**：run 粒度 = `(level, view_family)`；`cluster_run_id` 由 6 元组 sha256 稳定编码（含 `level_id`）；`local_seq` 按最小 canonical id 排序；`cluster_key` 按 D-2；父子层用 `parent_run_id` 关联；curation/审计引用同时记 run+key。

**形式化**：
```
cluster_run_id = sha256(canonical(
    corpus_manifest_sha, view_family_id, level_id,
    algorithm_id="hac-average", algorithm_version,
    params_hash))
params_hash = sha256(canonical({
    weight_policy: "semantic_uniform",     # R-S2-8：必须进 params_hash
    tau_coh, tau_bridge, target_k, min_cluster_size,
    linkage: "average", tie_break: "min_canonical_id", algorithm_version}))
parent_run_id = 上一 level（同 view_family）的 run_id（L0=null）
cluster_local_seq：同 run 内按 min(member_canonical_ids) 升序（tie 按 cluster_key）分配 1..N
cluster_instance_id = f"{cluster_run_id}:{cluster_local_seq}"
cluster_key = sha256(canonical(sorted(member_canonical_ids)) + "|" + algorithm_id
                     + "|" + algorithm_version + "|" + params_hash)   # D-2
curation/审计引用 = {cluster_run_id, local_seq, cluster_key}
```
**反例**：run_id 不含 level（与 per-level 冲突）；local_seq 随哈希排序乱序；cluster_key 用内容哈希当实例 id；curation 只记 key 不记 run；跨层复用 run。
**边界**：同一 level/family 同参数同语料 ⇒ 同 run_id；参数变 ⇒ 新 run；成员变 ⇒ key 变（旧 curation stale）；E_sem=0 ⇒ run 仍存在（全 singleton），但无 representative 簇。
**机检条件**：
```
- run_id 公式含 level_id/view_family/algorithm/version/params_hash；G6 可复算
- local_seq 在 run 内 1..N 唯一、排序可复算
- cluster_key 可复算；curation 引用三字段齐全；key 不匹配 ⇒ stale
- parent_run_id 只指向同 family 的上一层（L0=null）
```
**U 映射**：U-6、U-21、U-31。
**建议裁决**：采纳 per-level run_id/local_seq/cluster_key/parent_run_id；curation stale 规则。
**证据等级**：A（R-S2-4 `S2-RULINGS.md:37-40`；S0-4/D-2 `S0-terms-v1.md:45,104`；`ENGINEERING-PLAN.md:452-455`）；**本项目假设**（canonical 序列化细节/S6a 冻结）。

---

## 8. S2-8 嵌套与展开（per-level run + parent_run_id）

**定义/规则（一句话）**：同一 view_family 的相邻层 run 通过 `parent_run_id` 关联，且 Π_{ℓ+1} 必须精化 Π_ℓ（子簇成员 ⊆ 父簇成员）；展开簇=进入下一层 run（H 导航，S1-2 无 hop），最终到单 KP；空簇禁止；singleton 不作代表节点。

**形式化**：
```
同 family：run_0 (L0) ← parent_run_id ← run_1 (L1) ← ...（parent_run_id = 上一层）
refinement: ∀C'∈Π_{ℓ+1} ∃!C∈Π_ℓ: C'⊆C（由同一 dendrogram 切分保证）
展开：cluster(C,ℓ) → children C'（parent 关系）；到 Π_L=单 KP
H 派生边由 S1 R-S1-11 谓词生成；data_edge_ids 允许空集、字段必存在
singleton：代表节点=false；L0 root_exempt=true（若整库一块）
```
**反例**：不同 dendrogram/参数导致不嵌套；子簇超出父簇；展开到非 KP；空块；singleton 当代表节点；跨 family 建父子。
**边界**：父块只有一个子块 ⇒ `degenerate_refinement`（合法，标记）；L0 全库块；叶层全 singleton；子簇缺失 ⇒ fail-visible（unknown+rule_id）。
**机检条件**：
```
- child_run.parent_run_id == parent_run_id（同 family/上一层）
- refinement：∀C'∈child, ∃!C∈parent: C'⊆C（伪代码）
- 展开递归到 Π_L 全 singleton/KP；无空块
- root_exempt 仅 L0；degenerate_refinement 显式标记
```
**U 映射**：U-5、U-6、U-7、U-19、U-28。
**建议裁决**：采纳 per-level parent_run_id + refinement + 展开语义；空/单点边界。
**证据等级**：A（U-5/U-6/U-7/U-28；S0-2；S1 H 规则/R-S1-11）；**本项目假设**（degenerate_refinement 标记）。

---

## 9. S2-9 簇与边（E_sem internal/bridge；结构仅诊断）

**定义/规则（一句话）**：簇的 internal/bridge 边只由 `E_sem` 定义；结构/引用边只作为 `diag_*` 诊断与 H 层次背景，**不参与簇成立**；聚合/派生边带 `data_edge_ids`（R-3），H 派生边按 S1 R-S1-11（允许空集）。

**形式化**：
```
CLUSTER_EDGE:
  edge_kind ∈ {internal_sem, bridge_sem}   # 仅 E_sem
  data_edge_ids[] = canonical ids of E_sem 底层边
  diag_struct_internal/diag_struct_bridge   # 非语义边，仅诊断字段，不进 valid
H 派生边：由 S1 R-S1-11 生成（contain(structural) 谓词；data_edge_ids 可空集）
机检：expand_data_edges(cluster_vm/H_vm) ⊆ DataSource.edges；edge_kind 与 E_sem 成员一致；
      diag_* 不得参与 μ/β/valid
```
**反例**：把 structural contain 当 internal_sem（P0 同类）；bridge 用 reference 计 β；聚合边无 data_edge_ids；结构诊断字段影响簇判定。
**边界**：同一底层 E_sem 边在多归属性下可属不同 run；H 派生边空集合法；自环禁止；结构边只显示背景（S4）。
**机检条件**：
```
- CLUSTER_EDGE internal/bridge 的 data_edge_ids 均 ∈ E_sem
- diag_struct_* 字段只读、不参与 valid/μ/β
- expand_data_edges 子集（R-3）；H 派生边允许空集但字段存在
```
**U 映射**：U-13、U-15、U-16、U-17。
**建议裁决**：采纳 E_sem 的 internal/bridge + 结构仅诊断；data_edge_ids 强制；H 按 S1。
**证据等级**：A（S0 R-3；S1 R-S1-11；S0-1）；**本项目假设**（diag 字段命名）。

---

## 10. S2-10 簇与维度/层次（A 不改变簇，机检伪代码）

**定义/规则（一句话）**：H 在每层产生独立 but 嵌套的划分（per-level run）；**A 维度不产生/不改变簇**；簇只属于 H 的 view_family；簇服务输入不含 `dimension_id`。

**形式化 + 机检伪代码**：
```python
def assert_A_dimension_invariance(DataSource, params):
    # cluster 输入不含 dimension_id；view_family 固定 hierarchy
    run_h = build_clusters(DataSource, params)                  # 与维度无关
    frame_a = frame(DataSource, ctx={dimension_id:"association", ...})
    run_a = build_clusters(DataSource, params)                  # 同 DataSource/params
    assert run_h.run_id == run_a.run_id                         # A 切换不改 run
    assert canonical_partition(run_h) == canonical_partition(run_a)
    assert run_h.memberships == run_a.memberships
# A 只基于 H 基座扩展 appearance（S1-5），不写 membership
```
**反例**：A 维度下重新聚类；把 A 挂接节点写入 membership；H 每层不嵌套；跨维度复用 cluster_key 断言同簇。
**边界**：A 可见节点不属于簇成员（appearance，S0-7）；未来 relation 维度定义簇须重开 S2/S1；H 跨族不共享 parent。
**机检条件**：
```
- build_clusters 签名不含 dimension_id（代码/服务检查）
- 同 DataSource+params 下 H/A 切换 run_id/partition/membership 不变
- 每层 run 通过 parent_run_id 嵌套；跨层不重叠 criterion
```
**U 映射**：U-8、U-10、U-21、U-31。
**建议裁决**：采纳"H 产生簇、A 不产生/不改簇"；机检伪代码作为 freeze 检查。
**证据等级**：A（S0-7；S1-4/S1-5/S1-13；`ENGINEERING-PLAN.md:387,455`）；**本项目假设**（服务签名/伪代码）。

---

## 11. S2-11 持久化与缓存（per-level 派生缓存；D-3）

**定义/规则（一句话）**：每 `(level, view_family)` run 的簇/成员/边/稳定性全部是**派生缓存**（可重建、非事实源）；不写产品 sidecar/新段（D-3）；旧 run 只读保留。

**形式化**：
```
缓存 = ClusterRun{run_id, corpus_manifest_sha, view_family_id, level_id, algorithm_id/version,
                 params_hash, status, parent_run_id, clusters[], memberships[], cluster_edges[],
                 stability, dendrogram_sha, golden_sha}
路径：`.memoria/build/clusters/<view_family>/<level>/<run_id>.json`（S6 定精确路径；可再生）
不写：sidecar/knowledge_points/edges/md/manifest/新顶层段（D-3）
原子写 + 内容 sha；旧 run 只读；GC/配额 S6
回滚：删除缓存/忽略 run（事实源未改）；重建同输入同 run_id/golden
```
**反例**：写 sidecar/新段（D-3）；把 cluster_key 写进 KP 事实；缓存与 manifest 不一致当有效；删旧 run 破坏审计；缓存路径在事实源目录。
**边界**：缓存缺失 ⇒ 重算；损坏 ⇒ 重算+记录；schema 升级 ⇒ 丢弃旧缓存（不影响事实）；agent 不得写缓存（S2-13）。
**机检条件**：
```
- 缓存路径不在 sidecar/md/manifest/新顶层段（D-3 检查）
- 删除缓存后同输入重算：run_id/golden 相同
- 旧 run 只读；agent 无写缓存路径
```
**U 映射**：U-21、U-31、U-32。
**建议裁决**：采纳 per-level 派生缓存 + D-3；S6 需求（路径/schema/原子写/GC/stale）。
**证据等级**：A（S0 D-3 `S0-terms-v1.md:105`；`ENGINEERING-PLAN.md:458-459`）；**本项目假设**（路径/GC）。

---

## 12. S2-12 度量与验收（coverage 修正；G6）

**定义/规则（一句话）**：每 run 产出可复算指标（μ/β 分布、簇数/大小/singleton、coverage=覆盖 KP/全库 KP、稳定性、determinism golden）；G6 快照记录 run/params/key 清单；S2 冻结指标与降级语义，数值门禁归 S8。

**形式化（指标）**：
```
per cluster: |C|, μ, β, singleton, representative, diag_struct_bridge
per run: cluster_count, size_distribution, singleton_ratio,
         coverage = |∪_{representative} members| / |K_total|   # 修正：非 Σ|C|/|K|
         semantic_edges_used = |E_sem|, empty_state (E_sem=0 ⇒ coverage 0)
         modularity/其他可选（不上门禁）
per pair runs: jaccard_weighted, churn, split/merge, cluster_count_delta
G6 snapshot: corpus_manifest_sha, view_family_id, level_id, run_id, algorithm_id/version,
             params_hash, cluster_key list, μ/β summary, coverage, stability summary,
             E_sem count
```
**机检条件**：
```
- 同输入两次 run golden 相同（确定性）
- coverage = covered_KP / |K_total|，且 E_sem=0 ⇒ 0（不得恒 1）
- 所有块 partition/μ/β/singleton 规则可复算；指标可由 memberships 复算
- G6 字段齐全；G6 语义统计不得把结构 cluster 当 semantic（source=derived_cluster）
- degraded/empty/partial 状态显式，不输出"正常"指标
```
**反例**：coverage 用 Σ|C|/|K| 恒 1；只报簇数；把 structural cluster 计入 G6 语义；降级 run 当正常；随机/时间指标。
**边界**：首次 run（稳定性 initial）；E_sem=0 ⇒ coverage=0（合法）；全 singleton；partial_disconnected；数值门禁 S8。
**U 映射**：U-2、U-13、U-32。
**建议裁决**：采纳指标/G6/coverage 修正；数值门禁 S8。
**证据等级**：A（U-32；S0/S1 acceptance；`ENGINEERING-PLAN.md:439-447`）；**本项目假设**（指标清单/门禁归 S8）。

---

## 13. S2-13 与 agent（v1 只读 + 候选 run；审计）

**定义/规则（一句话）**：v1 agent **只读现有 run**；可请求**新建候选 run**（`requester/reason/params` 审计），候选 `candidate` 不自动采用、不覆盖旧 run；agent 不得改 membership/缓存/manifest/渲染状态、不得改参数生效。

**形式化**：
```
允许：
  ① 只读 ClusterRun（clusters/memberships/metrics）用于 S9 检索/取景
  ② 请求新建候选 run：{requester, reason, params, base_run_id} → ClusterRun(status=candidate)
  ③ 提议参数（作为请求的一部分，不直接生效）
禁止：
  写 membership/cluster 缓存/sidecar/manifest；覆盖旧 run；自动采用候选；改渲染/导航状态
采用：由人/S5 显式 adopt（candidate→adopted）；旧 run 保留
审计：{requester, reason, params_hash, corpus_manifest_sha, run_id, status, created_at}
```
**反例**：agent 写缓存；agent 自动 adopt 候选；agent 静默改 params；不审计；把候选当事实；跨 KB。
**边界**：缓存缺失 ⇒ 服务重算（非 agent 写入）；参数非法 ⇒ 错误码；候选 run 可多个、互不覆盖；v1 不自动采用。
**机检条件**：
```
- agent 无写 membership/缓存/manifest 接口（allowlist）
- 候选 run status=candidate 且不被 ViewModel 引用；adopt 需显式动作
- 审计字段齐全；同 params_hash 已有 run ⇒ 复用而不覆盖
- 跨 KB 拒绝
```
**U 映射**：U-2、U-29、U-32。
**建议裁决**：采纳只读+候选 run+审计+不自动采用；S9 用 run 接口。
**证据等级**：A（R-S2-5 `S2-RULINGS.md:42-45`；S0-10；S1-14；`ENGINEERING-PLAN.md:301-303`）；**本项目假设**（服务签名/audit 字段）。

---

## 14. 覆盖矩阵

### 14.1 U 覆盖

| U# | 要点 | S2 落点 |
|---|---|---|
| U-6 | 代表子图节点 | S2-1/S2-8（singleton 不作代表；cluster 节点≥2） |
| U-13 | 非严格连通子图/零星桥 | S2-1/S2-3（E_sem β） |
| U-14 | 按语义划分小群 | S2-2（E_sem-only μ） |
| U-15 | 语义边挂接一跳 | S2-9（semantic internal/bridge）+S1-5 |
| U-17 | 背后图不带入 | S2-8/S2-9（展开只子簇；桥呈现 S4） |
| U-21 | 多归属 | S2-6/S2-10 |
| U-22 | 新一跳 vs 更深 | S2-8（展开=导航）/S1-5 |
| U-31 | 多归属上限 | S2-6（v1 不设上限，S6 可配） |

### 14.2 S0/S1 一致性

| 条款 | S2 落实 | 检查 |
|---|---|---|
| S0-1 语义（E_sem） | S2-2/S2-1 | μ/β 输入 == E_sem（P0 关闭） |
| S0-2 partition/最小粒度 | S2-1/S2-8 | 同族同层 partition；叶 KP |
| S0-4 簇定义/身份 | S2-1/S2-7 | μ/β；run-scoped id + key |
| S0-7 多归属 | S2-6 | 成员≠出现；同族单归属/跨族多归属 |
| S0 D-2/D-3 | S2-7/S2-11 | per-level run+key；不写 sidecar |
| S0 R-3 | S2-9 | data_edge_ids/expand 子集 |
| S1 H/A 分工 | S2-4/S2-10 | H 每层 run；A 不改簇（伪代码） |
| S1 view_family/R-S1-11 | S2-7/S2-8 | per-level family；H 派生边映射 |

---

## 15. A-v2 变更表（逐条旧→新，含 v1 行号）

> 旧文件：`S2-clustering-proposal-A.md`（v1 `b14bb379…`），行号可 grep 复核。

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S2-1（L33）簇成立可用任意 E_relation 证据 | 簇只由 E_sem 支撑；结构/引用仅诊断（§1） | R-S2-1 |
| 2 | S2-2（L67）weight_policy structural 0.5/reference 0.2/extend 0.3；τ_coh=0.04 | E_sem-only 单位权；τ_coh=0.5；参数类型/范围/失败语义；probe 产物路径（§2） | R-S2-1/2 |
| 3 | S2-3（L105）β 含 reference/structural；τ_bridge=0.15 | β 只用 E_sem；τ_bridge=0.25；结构桥仅诊断（§3） | R-S2-1/2 |
| 4 | S2-4（L136）Louvain 主选 + CNM 降级 + networkx | 纯自实现 average-linkage HAC；tie-break/canonical/golden；四态降级；禁第三方/连通分量回退（§4） | R-S2-3 |
| 5 | S2-5（L175）run 粒度 per view_family 含所有层 | run 粒度 per `(level, view_family)`；parent_run_id/稳定性按层（§5） | R-S2-4 |
| 6 | S2-6（L200）singleton μ=1；coverage=Σ|C|/|K| | singleton μ=null/representative=false；coverage=覆盖 KP/全库 KP；role 不复用 bridge（§6） | R-S2-6/7 |
| 7 | S2-7（L229）run_id 不含 level；local_seq 规则未定 | run_id 公式含 level_id/view_family；parent_run_id；local_seq 按 min id；cluster_key D-2（§7） | R-S2-4 |
| 8 | S2-8（L258）嵌套未绑定 per-level run | parent_run_id 跨层 + refinement 机检（§8） | R-S2-4 |
| 9 | S2-9（L286）internal/bridge 含结构边证据 | internal/bridge 只 E_sem；结构仅 diag；data_edge_ids 强制（§9） | R-S2-1 |
| 10 | S2-10（L310）A 不改簇仅文字 | 补 `assert_A_dimension_invariance` 机检伪代码（§10） | R-S2-7/8 |
| 11 | S2-11（L328）缓存粒度 per view_family | per `(level, view_family)` 缓存路径/run 只读（§11） | R-S2-4 |
| 12 | S2-12（L356）coverage 可能恒 1 | coverage=覆盖 KP/全库 KP；E_sem=0 ⇒ 0；G6 字段含 E_sem 计数（§12） | R-S2-6/8 |
| 13 | S2-13（L385）agent 可请求重聚类/改参数 | v1 只读 + 候选 run（requester/reason/params 审计、不自动采用、不覆盖）（§13） | R-S2-5 |
| 14 | 覆盖矩阵 §14 | 增加 E_sem/coverage/HAC/per-level run 检查（§14） | 本轮 |
| 15 | 缺 probe 产物 | 新增语义-only probe 路径与结果（frozen/showcase E_sem=0；synthetic 标定 τ） | R-S2-2 |
| 16 | §15 争议 | 更新为 τ live 复标定/HAC 规模/候选 run adopt（§16） | 本轮 |

---

## 16. 仍存争议 / 待 Lead·SE 裁决

1. **τ 默认值的 live 标定**：frozen/showcase 均无 E_sem，τ=0.5/0.25 来自合成语义夹具；需要在有 semantic curation 的 live 语料复标定（S8）。是否允许 S2 冻结该默认值+出处、S8 可配置。
2. **HAC 规模上限**：纯 Python O(n²·merges) 对超大图的风险；max_nodes 数值归 S8，超出即 degraded；是否可加"分块近似"（不得回退连通分量）需 S9/S8 评估。
3. **target_k 序列/层数**：per-level run 的 `target_k_ℓ` 由 S4/S8 定；S2 只冻结"同 dendrogram 切分"；层数与默认序列待裁。
4. **singleton 的 UI 处理**：v1 允许 singleton 但不作代表节点；S3/S4 是否隐藏/合并需裁决。
5. **候选 run 的采用流程**：agent 建候选后由人/S5 adopt；adopt 的权限/审计/回滚细节归 S5/S6。

---

## 17. 证据锚

```text
裁决：S2-RULINGS.md:9-20（复核）、:21-62（R-S2-1..8）、:64-74（修订轮/门禁）
原话：vision.md:23-24（U-6/U-7）、:30-32（U-13/U-14/U-15）、:34（U-17）、:38（U-21）、:39（U-22）、:70（U-31）
S0：S0-terms-v1.md:21-26（S0-1 E_sem）、:30-33（S0-2）、:43-47（S0-4）、:56-61,102（S0-6/R-3）、:65-68（S0-7）、:104-105（D-2/D-3）
S1：S1-dimensions-v1.md:13-15（H/A）、:57-65（H/R-S1-11）、:137-155（覆盖矩阵）
工程：ENGINEERING-PLAN.md:101-121（CLUSTER/MEMBERSHIP）、:201-214（实体表）、:401-412（CLUSTER_RUN）、:423-447（MEMBERSHIP/CLUSTER_EDGE/STABILITY）、:452-459（身份/缓存）
代码（反例/现状）：graph-groups.js:2,83,123-126（并查集/单值）；graph-engine.js:167-181；app.js:1845；collector.py:46-99；edge_derivation.py:787-793
probe：artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/{probe.py,results.json}
```
