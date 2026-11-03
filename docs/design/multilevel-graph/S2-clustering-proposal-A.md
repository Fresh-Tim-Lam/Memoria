# S2 提案 A：簇与子图划分（语义内聚 + 零星桥 + 多归属 + 稳定身份）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-300｜**日期**：2026-11-03（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35 原话逐字存档）。
> **上游冻结（不得违反）**：`S0-terms-v1.md`（sha `241b1e1e…`）+ `S0-FREEZE-RECORD.md`；`S1-dimensions-v1.md`（sha `6676c71d…`）+ `S1-FREEZE-RECORD.md`。
> **本场章程**：`docs/design/multilevel-graph/S2-charter.md`（S2-1..S2-13）。
> **工程输入**：`ENGINEERING-PLAN.md`（ER-03 S2 增量草案）、`S1-engineering-check.md`、`S0-engineering-review.md`。
> **独立性**：未阅读 S2 独立复核方草稿（S2-clustering-proposal-B / S2-objections）；本提案独立撰写。
> **纪律**：只写设计；不改产品代码/契约/schema/用户库；未 commit。

---

## 0. 总口径（与 S0/S1 的关系）

```
簇（cluster）= 同一 (level, view_family) 下的一个成员块：关系内聚高、与外部只有零星桥；
               ≠ 严格连通分量（graph-groups 并查集），≠ KP 本体，≠ 事实源。
划分（partition）= 同一 (level, view_family) 内的块族（不交、非空、覆盖该层全集）；跨族/维可重叠（多归属）。
簇身份 = run-scoped instance id（cluster_run_id + local_seq）+ cluster_key（可复算内容键）。
簇是派生缓存（D-3：不写产品 sidecar/新段）；curation/审计引用必须同时记 run 与 key。
```

**本场不变量**：
- H 的每层划分必须满足 S0-2 `(level, view_family)` partition；跨族/维重叠 = S0-7 多归属。
- 簇的块→子块派生边由 S1 H 规则生成并带 `data_edge_ids`（R-S1-11）；S2 负责提供成员/父子/边投影。
- **A 维度不产生簇**；A 只基于 H 基座扩展可见节点（S1-5），机检见 S2-10。
- 簇/成员**不写产品 sidecar/新拓扑段**（S0 D-3）；簇仅派生缓存。

**证据等级**：A（原话/冻结契约/决策/可复跑代码事实）；B（单源实测产物，含本场 probe）；C（单源推理）；**本项目假设**（参数/默认值/阈值等显式约定）。

---

## 1. S2-1 簇定义与边界（≠ 严格连通分量）

**定义/规则（一句话）**：簇是**同一 `(level, view_family)` 下、关系内聚度 μ 达标且外部桥比例 β 不超标**的 KP 成员块；严格连通分量（内部连通且无跨边）只是它的一种特例，不能作为簇的定义或默认实现。

**形式化**：
```
给定视图族 family（S0 R-2）与层 ℓ，候选成员 C ⊆ K_f：
  G_rel = (K_f, E_rel)，E_rel = DataSource 中 E_relation_min 的边（关系证据图，带权 w，见 S2-2）
  W_in(C)  = Σ_{e∈E_rel, 两端∈C} w(e)
  W_out(C) = Σ_{e∈E_rel, 恰一端∈C} w(e)
  簇条件：|C|≥2 时 μ(C)≥τ_coh ∧ β(C)≤τ_bridge；|C|=1 为 singleton 块（μ 豁免，见边界）
  严格连通分量 CCC：C 内部连通 ∧ W_out(C)=0（强条件；簇不要求，U-13）
整个视图族的划分 Π_ℓ,f = {C_1,…,C_m}：块两两不交、并=K_f、每块满足簇条件或为 singleton
```
**边界**：
- **空簇**：禁止（`|C|=0` 非法；partition 非空块）。
- **单点簇**：允许为 partition 的 singleton 块（KP 直接显示；μ 豁免、不宣称"语义内聚"），但**不是**"代表子图节点"；U-6 的 cluster 节点至少 2 成员（见 S2-8）。
- **全库一簇**：只允许作为根层 L0 的 container block（`root_exempt=true`），且 H 默认视图从 L1 开始；ℓ>0 若退化为"整库一簇" ⇒ 视为算法失败/降级，不得静默当正常簇（记 warning/status=degraded）。
- **跨族重叠**：允许（多归属，S2-6）；同族同层重叠：禁止（partition）。
- **与 graph-groups**：现有 `graph-groups.js:2`（并查集闭包）/`:83`（`computeGraphGroups`）产生的是连通分量式分组；**不得**复用为簇（反例，A 级）。

**机检条件**：
```
- Π_ℓ,f 覆盖 K_f、块非空、同族同层不交（复用 S0-2 V5）
- 每个 |C|≥2 的块 μ(C)≥τ_coh ∧ β(C)≤τ_bridge
- 不存在 graph-groups/并查集函数作为 cluster 实现的调用（代码/服务层 grep）
- root block 仅在 L0 且 root_exempt；ℓ>0 无"整库单簇"
```
**反例**：把 `graph-groups` 并查集分组当簇（严格分量）；全库一个毛球簇（U-3）；同族同层块重叠；空块；ℓ>0 整库一簇。**U 映射**：U-6、U-13、U-14、U-21、U-31。
**建议裁决**：采纳定义与边界；簇≠严格连通分量；单点块允许但 μ 豁免；全库一簇仅 L0 root；禁止并查集当簇实现。
**证据等级**：A（U-13/U-14 原话；S0-4 `S0-terms-v1.md:43-47`；`graph-groups.js:2,83` 并查集事实）；**本项目假设**（singleton μ 豁免、root_exempt 规则）。

---

## 2. S2-2 语义内聚度 μ（度量/阈值/默认值）

**定义/规则（一句话）**：μ 用**加权内部密度**度量块内关系证据的紧密程度：`μ(C)=W_in(C)/P(C)`，其中 `P(C)=|C|(|C|-1)/2` 为可能对数，权重 `w(e)` 由关系证据强度策略给出；τ_coh 可参数化，v1 默认 **0.04**。

**形式化**：
```
权重策略 weight_policy v1（可参数化；默认值）：
  semantic 断言边（label=semantic）      w=1.0
  contain(structural)                     w=0.5
  extend（非 semantic）                   w=0.3
  reference（无断言跳转）                 w=0.2
  其它/未定                               w=0.0（不入 E_rel）
μ(C) = W_in(C) / (|C|·(|C|-1)/2)       # |C|≥2
μ(C) = null（singleton，豁免；不参与 τ 判定）
τ_coh 默认 0.04（参数化；S8 可调；参数非法 fail-closed）
```
**默认值的证据**（B 级本机 probe，frozen 62 边/357 KP）：
- Louvain 分块（含权重）中，13 成员块 μ≈0.046、12≈0.047、9≈0.086、8≈0.125、7≈0.143、3≈0.333、2≈0.5；
- 严格连通分量的 25 成员块 μ≈0.0233 < 0.04 ⇒ 被 μ 淘汰（需继续细分，见 S2-4）；
- 因此 v1 默认 τ_coh=0.04 可接受拆分后的内聚块，同时拒绝"大而松"的连通分量。**注意**：该值来自稀疏冻结语料，S8 必须在 live 语料复标定；S2 只冻结"可复算公式 + 默认值"。

**机检条件**：
```
- 每个 |C|≥2 的块给出 μ(C)=W_in/P（P>0），且 weight_policy/τ_coh 由 params_hash 覆盖
- singleton 块 μ=null 且不参与 τ 判定；无 μ=0 的"伪合格"块
- E_rel 为空 ⇒ status=degraded（不得返回 μ 指标冒充正常）
- 同一 (E_rel, weight_policy) 两次计算 μ 完全一致（可复算）
```
**反例**：用未加权边数密度（type/权重不区分，语义边被稀释）；用"成员名字相似度"代替关系证据（不是关系）；阈值随语料硬编码在代码里（应参数化）；把 singleton 的 μ 当 1.0 参与阈值（会误纳）。

**边界**：|C|=2 且一条权重 1.0 边 ⇒ μ=1.0；无内部边（仅桥）⇒ μ=0（不达标）；singleton μ=null 豁免；权重全 0 ⇒ E_rel 为空，μ 无定义 ⇒ 降级（S2-4 失败路径），不得用 0 冒充。

**U 映射**：U-1、U-13、U-14。
**建议裁决**：采纳加权密度公式 + weight_policy v1 + τ_coh=0.04（参数化、S8 复标定）；singleton 豁免。
**证据等级**：A（U-1/U-13/U-14；S0-4）；B（本场 frozen probe 分布）；**本项目假设**（权重取值/τ 默认值）。

---

## 3. S2-3 桥判定 β（跨簇边比例/语义强度/单点桥）

**定义/规则（一句话）**：桥是"恰有一端在 C 内"的关系边；β(C)=W_out/(W_in+W_out) 度量外溢比例，v1 默认 **τ_bridge=0.15**，另报"每成员桥数"与"单锚点桥"两个诊断量。

**形式化**：
```
E_bridge(C) = {e∈E_rel | |{端点在 C}|=1}
W_out(C) = Σ_{e∈E_bridge(C)} w(e)
β(C) = W_out / (W_in + W_out)          # 无关联边时 β=0
bridge_per_member(C) = |E_bridge(C)| / |C|      # 诊断/阈值候选
single_anchor_bridge(C) = {e∈E_bridge(C) | 外部端点只与 C 有一条关系边}  # 诊断（易造成假外溢）
τ_bridge 默认 0.15；τ_bridge_per_member 默认不设硬阈值（仅报告）
簇条件：β(C) ≤ τ_bridge（|C|≥2）
```
**机检条件**：
```
- 每个 |C|≥2 的块 β(C) 可计算且 ≤ τ_bridge（参数化）
- β=0 与"无外部边"一致；β=1 不得判为合格簇
- bridge_per_member/single_anchor_bridge 按定义可复算；singleton 豁免
- 权重与 μ 使用同一 weight_policy（避免两套口径）
```
**反例**：把"跨簇边存在"直接判为非簇（U-13 允许零星桥）；把所有边都当内部边（β=0 但没有"外部"概念）；用桥数绝对值不归一（簇越大越容易超标，尺度不可比）；对 singleton 计 β（无意义，豁免）。

**边界**：β=0 ⇒ 同时是连通分量（允许，但定义不要求）；β=1 ⇒ 几乎无内部（非簇）；单锚点桥多 ⇒ 提示"借一个节点外溢"，作为警告但 v1 不硬拒（除非 β 超限）；桥的方向/类型不改变 β（按权重计）。

**U 映射**：U-13、U-14、U-15（桥的呈现归 S4）。
**建议裁决**：采纳 β 公式 + τ_bridge=0.15（参数化、S8 复标定）；bridge_per_member/single_anchor 作为诊断指标，不单独作 v1 硬门槛。
**证据等级**：A（U-13 原话；S0-4）；B（probe：13 块 β≈0.077、12≈0.088、9/8/7 β=0；25 分量 β=0）；**本项目假设**（τ/诊断口径）。

---

## 4. S2-4 划分算法候选与 v1 选型

**定义/规则（一句话）**：v1 用**确定性带种子的 Louvain 层次社区发现（加权）**产生嵌套划分，**确定性贪心模块度（CNM）**作为降级；严格连通分量（graph-groups）**不作为簇算法**（仅允许作为失败诊断/降级标记）。

**候选对比**：
| 候选 | 确定性 | 可复算 | 复杂度 | 层次/嵌套 | v1 |
|---|---|---|---|---|---|
| 带种子 Louvain（weighted，node order=sorted kp_id，seed=0） | 高（固定 seed/顺序） | 同输入同划分 | 近 O(E) 每层 | ✅ 自产层次 partitions | **主选** |
| 贪心模块度（CNM，weighted，固定 tie-break） | 高（无随机） | 高 | O(E log N) | ❌ 扁平（需再构造层次） | **降级** |
| 层次凝聚（average-linkage/HAC） | 高（固定 tie） | 高 | O(N² log N) | ✅ dendrogram | 备选（小图） |
| 连通分量（并查集，`graph-groups`） | 高 | 高 | O(E α) | ❌ | **禁止当簇**（仅诊断/降级标记） |
| embedding kNN + 社区 | 取决于 embedding | 需模型版本 | 高 | 可 | 不在 v1（S9/未来） |

**v1 选型/降级路径**：
```
primary: deterministic_louvain_hierarchy(G_rel, weight, seed=0, resolution=1.0,
                                          node_order=sorted(kp_id), tie_break=min(kp_id))
  → 产出 L0..Lk 嵌套 partitions（验证 refinement）
fallback1: greedy_modularity → 扁平分块；再用确定性 agglomerative merge 构造层次（按簇间权重最大合并，tie=最小 kp_id）
fallback2: 若 E_rel=∅ 或算法失败/超时 ⇒ 全部 singleton partitions + status=degraded + warning
           （禁止用并查集"伪装"成簇；若显示必须是显式 degraded，不是正常簇）
validators: 每层 partition 过 S0-2 V5 + μ/β 条件；失败则降级上一级，不得静默
```
**关键机检**：
```
- 同一 (corpus_manifest_sha, params_hash, algorithm_id+version, seed) ⇒ 同 partition（两次运行 canonical 序列化相等）
- partitions 嵌套：Π_{ℓ+1} 是 Π_ℓ 的 refinement（每子块 ⊆ 唯一父块）
- 不使用 graph-groups/并查集结果作为 cluster 成员（grep/接口隔离）
- 算法失败走显式 degraded（warning/status），不输出"看起来正常"的分区
- 复杂度在 S8 规模内可接受（S2 不冻结数值；记录 N/E/levels）
```
**反例**：把并查集分量当簇（L2 现有实现）；Louvain 用随机 seed/未固定节点顺序（不可复算）；扁平分块直接伪造嵌套；失败时静默返回全库一簇；为"看起来有簇"把 singleton 合并成假块。
**边界**：E_rel 稀疏/孤立节点多（frozen probe：296 分量，278 singleton）⇒ 允许大量 singleton，不伪造聚合；单层只有 1 个非平凡簇 ⇒ 可继续降级到更细层；图太大 ⇒ S8/S9 预算，S2 不设规模上限（U-32）。
**U 映射**：U-4、U-6、U-13、U-14、U-32。
**建议裁决**：采纳 Louvain 主选 + CNM 降级 + 显式 degraded；禁止并查集当簇；确定性参数写死。
**证据等级**：A（U-13/U-14；`graph-groups.js:2,83` 反例）；B（probe：Louvain/CNM 在 frozen 62 边上结果一致：297 块/278 singleton/最大 13，且连通分量 25 块 μ=0.0233 不达标而 Louvain 拆为 13+12 达标）；**本项目假设**（seed/tie-break/分辨率/singleton 策略）。

---

## 5. S2-5 稳定性（漂移/触发/版本/度量）

**定义/规则（一句话）**：每次聚类是**不可变 run**；输入（语料/关系证据/算法/参数）变化即产生新 run；稳定性用新旧 run 的成员 Jaccard、churn、split/merge、簇数差度量，v1 全量重算、不做增量修改。

**形式化**：
```
run 输入键 = ⟨corpus_manifest_sha, view_family_id, algorithm_id, algorithm_version, params_hash⟩
触发：manifest_sha 变化 ∨ 关系边/证据版本变化 ∨ algorithm/params 变化 ∨ 显式请求
      （不按时间自动重聚类；旧 run 只读保留）
稳定性度量（新旧 run 同 view_family）：
  match: 对每个 new cluster N，找 old cluster O 最大化 J(N,O)=|N∩O|/|N∪O|（一对一贪心，tie 按 cluster_key）
  jaccard_weighted = Σ_{N} |N|·J(N,best O) / |K_f|
  churn = 1 - Σ_{N} |N∩best O| / |K_f|
  split/merge = 新簇数-旧簇数 / 被拆分/合并的簇计数（按最佳匹配）
  cluster_count_delta
机检：两 run 的 metrics 可用 canonical JSON 复算；同输入重复计算 metrics 一致
```
**反例**：新 run 原地覆盖旧 run（破坏审计）；按时间自动重聚类（不可复现）；只比簇数不看成员（掩盖漂移）；用 cluster_key 直接当匹配键（成员变化即失配，需成员 Jaccard）。
**边界**：首次 run（无 previous）⇒ stability 记录 `null/initial`；小编辑后部分簇完全不变 ⇒ J=1；语料重构 ⇒ 大量 split/merge（报告为不稳定性，不阻断，S8 定门禁）；跨 view_family 不做稳定性比较（不同划分作用域）。
**U 映射**：U-21、U-22（返回/更深）、U-31。
**建议裁决**：采纳不可变 run + 触发条件 + 成员 Jaccard/churn 度量；v1 全量重算；阈值/门禁归 S8（S2 只定义测量与记录）。
**证据等级**：A（S0-7/D-2；`ENGINEERING-PLAN.md:209-211,439-458` CLUSTER_RUN/STABILITY）；**本项目假设**（匹配贪心/tie 规则、触发清单）。

---

## 6. S2-6 多归属（成员 ≠ 视图出现；上限）

**定义/规则（一句话）**：membership 是**多对多派生关系**；同一 `(level, view_family)` 内一个 KP 恰属一个块，跨层/跨视图族/跨维可重叠；**成员关系 ≠ 视图出现**；v1 不设硬上限（记录计数，S6 可配置 `max_memberships_per_kp`，null=不设限）。

**形式化**：
```
Membership = ⟨run_id, cluster_id, kp_id, role ∈ {member, bridge?}, weight?, source=derived_cluster, provenance⟩
约束：
  同 (level, view_family)：函数 π(k)→唯一块（partition）
  跨层（同族）：嵌套包含关系（每层各一个块，不冲突）
  跨 view_family/dimension：允许同一 KP 属多个块（多归属），S0-7 允许；v1 不设上限
  membership ⇏ appearance；appearance 由 S1 present/ViewModel 决定
  成员关系不写产品 sidecar（D-3）；source 只允许 derived_cluster（v1 无 curation）
```
**机检条件**：
```
- 同 (level, view_family) 内每个 kp 恰好一个块（partition 校验）
- 跨族同一 kp 可多块；membership_count 可复算；max_memberships_per_kp=null 时不拒绝
- membership 字段无 nodeToGroup 单值依赖；无 appearance→membership 回写
- source 只能是 derived_cluster（v1 无 curation）
```
**反例**：用 `nodeToGroup` 单值当 membership（现有实现 `graph-groups.js:123-126`，必须废弃）；把"当前渲染出现"写成 membership；全库范围要求 KP 只属一个簇；同族同层重叠。
**边界**：单 KP 在 H 各层各属一块（正常）；跨族重叠（若未来多族）；`max_memberships_per_kp` 仍 null（v1）；appearance 为 one_hop/bridge 时不改变 membership。
**U 映射**：U-19、U-21、U-22、U-31。
**建议裁决**：采纳多对多 Membership + 同族单归属/跨族多归属；v1 不设上限，S6 可配置；禁止单值 `nodeToGroup` 作产品模型。
**证据等级**：A（U-21/U-31；S0-7；`ENGINEERING-PLAN.md:111-121,423-430` MEMBERSHIP 多对多）；**本项目假设**（上限留 S6）。

---

## 7. S2-7 簇身份（run-scoped id + cluster_key，D-2）

**定义/规则（一句话）**：簇实例 id 用 **run-scoped** `cluster_run_id + cluster_local_seq`（不可变、可追溯）；`cluster_key` 是成员+算法+版本+参数的**内容哈希**（可复算/去重）；curation/审计引用必须同时记 run 与 key，成员变化即 key 变化、旧引用标记 stale，不得静默套用。

**形式化**：
```
cluster_run_id = sha256(canonical(corpus_manifest_sha, view_family_id,
                                 algorithm_id, algorithm_version, params_hash))
cluster_local_seq：同一 run 内按 min(member_canonical_ids) 升序（tie→cluster_key）分配 1..N
cluster_instance_id = f"{cluster_run_id}:{cluster_local_seq}"
cluster_key = sha256(canonical(sorted(member_canonical_ids)) + "|" + algorithm_id + "|"
                     + algorithm_version + "|" + params_hash)
（member_canonical_ids = kp_id 列表；canonical 序列化 UTF-8、无歧义分隔）
```
**机检条件**：
```
- run_id 可复算：sha256(canonical(corpus_manifest_sha, view_family_id, algorithm_id, version, params_hash))
- cluster_local_seq 在 run 内 1..N 唯一、按 min(member_canonical_ids) 排序可复算
- cluster_key 可复算；同成员同参数 ⇒ 同 key；成员变 ⇒ key 变
- curation/审计引用同时含 run_id+local_seq+cluster_key；key 不匹配 ⇒ stale，不静默套用
```
**反例**：用内容哈希当唯一 id（D-2 已否：成员一变 curation 引用失效）；local_seq 随哈希排序导致大规模乱序（应按 min member canonical id 稳定排序）；curation 只记 cluster_key 不记 run（无法定位实例）；删除/复用旧 run id。
**边界**：成员不变、算法/参数变 ⇒ key 变、run 变（不可复用旧 curation）；成员变、算法同 ⇒ key 变；旧 run 保留审计；curation 引用若 key 不匹配 ⇒ stale 状态（S6 定义读写），绝不静默应用到新簇。
**U 映射**：U-6、U-21、U-31。
**建议裁决**：采纳 D-2 公式与排序规则；local_seq 按 min member id 排序；curation/审计引用 = {cluster_run_id, local_seq, cluster_key}；成员变化标记 stale。
**证据等级**：A（S0-4/D-2；`ENGINEERING-PLAN.md:209-211,452-455`）；**本项目假设**（cluster_key 拼接细节/local_seq 排序规则——S6a 冻结）。

---

## 8. S2-8 嵌套与展开（子簇/KP 叶子/空/单点）

**定义/规则（一句话）**：同 view_family 内 Π_{ℓ+1} 必须精化 Π_ℓ（子簇成员 ⊆ 父簇成员）；展开簇到下一层是 S5 的 H 导航动作（S1-2 无 hop），最终到达单 KP；空簇禁止；单点块允许但不得作为"代表子图节点"。

**形式化**：
```
refinement: ∀C'∈Π_{ℓ+1}, ∃!C∈Π_ℓ: C'⊆C
parent_cluster_id(C') = C
展开：cluster(C at ℓ) → {C'∈Π_{ℓ+1} | parent(C')=C}；到 Π_L = 单 KP
H 派生边（S1 R-S1-11）：parent block → child block；data_edge_ids = contain(structural) 谓词映射
单点：允许为 Π_ℓ 的 singleton；不产生"代表子图节点"语义；UI 可显示 KP
空簇：禁止；根 L0 允许全库单块（root_exempt），默认视图从 L1 开始
```
**机检条件**：
```
- Π_{ℓ+1} 是 Π_ℓ 的 refinement（∀子块 ⊆ 唯一父块）
- 展开递归到 Π_L 全为 singleton/KP；不存在空块
- root 全库单块仅 L0；degenerate_refinement 显式标记
- H 派生边 data_edge_ids 按 S1 R-S1-11 谓词可映射（允许空集、字段必存在）
```
**反例**：子簇成员超出父簇（破坏嵌套）；展开到"非 KP 叶子"；空块；把 singleton 当"代表子图节点"并显示成员计数 0/1；跨 view_family 建立父子。
**边界**：父簇只有 1 个子簇（partition 未实质细化）⇒ 允许但标记 `degenerate_refinement`（H 视图无变化）；L0 全库单块；叶层全是 singleton；展开失败（子簇缺失）⇒ fail-visible（unknown + rule_id），不伪造。
**U 映射**：U-5、U-6、U-7、U-19、U-28。
**建议裁决**：采纳 refinement 约束 + 展开语义 + 空/单点边界；H 派生边由 S1 规则生成；degenerate_refinement 显式标记。
**证据等级**：A（U-5/U-6/U-7/U-28；S0-2；S1 H 规则/R-S1-11）；**本项目假设**（degenerate_refinement 标记、root_exempt 细节）。

---

## 9. S2-9 簇与边（内部/桥/data_edge_ids/R-3）

**定义/规则（一句话）**：簇相关边分 `internal`（两端同簇）与 `bridge`（恰一端）；聚合/派生边必须带 `data_edge_ids` 映射回 DataSource 原始边（R-3）；contain(structural) 作为层次内部证据参与 μ/β，桥的呈现归 S4。

**形式化**：
```
CLUSTER_EDGE = {edge_kind: internal|bridge, source_cluster_id, target_cluster_id?, data_edge_ids[]}
  internal(C)：e∈E_rel 且两端∈C
  bridge(C)：e∈E_rel 且恰一端∈C；对端为另一簇（或外部 singleton）
  data_edge_ids(e_cluster) = [canonical_edge_id(e) for e∈对应底层边]
H 派生边（S1 R-S1-11）另带自己的 data_edge_ids（contain(structural) 谓词）
机检：
  expand_data_edges(cluster_vm/H_vm) ⊆ DataSource.edges
  每条 CLUSTER_EDGE.data_edge_ids 非空且 canonical id 可在 DataSource 找到（R-3；允许空集仅 H 派生边按 S1 例外？——不，H 边允许空集，见 S1-R-S1-11；CLUSTER_EDGE 聚合非空）
  edge_kind 与成员关系一致（internal 两端同簇；bridge 恰一端）
```
**反例**：聚合边无 data_edge_ids（违反 R-3）；把 bridge 当作 internal 计入 μ（自欺）；把 reference 强行算 internal 证据却不标 label（消费者误读）；用顶点权重重排边身份。
**边界**：同一底层边同时是 A 簇 internal 与 B 簇 bridge（多归属/不同族）⇒ 按各自 run 分别记录；H 派生边可空集（S1 冻结例外，但字段必须存在）；自环（source=target）不入簇边（DataSource 无自环；若出现 ⇒ invalid）。
**U 映射**：U-13、U-15、U-16、U-17。
**建议裁决**：采纳 internal/bridge 分类 + data_edge_ids 强制（H 例外按 S1）；contain(structural) 作为层次内证据；呈现归 S4。
**证据等级**：A（S0 R-3；S1 R-S1-11；`ENGINEERING-PLAN.md:431-438,457`）；**本项目假设**（CLUSTER_EDGE 字段细节）。

---

## 10. S2-10 簇与维度/层次（H 每层独立划分；A 不影响簇）

**定义/规则（一句话）**：H 在每层产生**独立但嵌套**的划分（同 view_family 的 Π_ℓ）；A 不参与簇构建、不改变簇（机检：同一 DataSource+params 下，H/A 切换前后 cluster run 与成员完全一致）；簇只属于 H 的 view_family。

**形式化**：
```
cluster_run 输入不含 dimension_id（或固定 hierarchy）；view_family_id 含 dimension_id=hierarchy（S1 R-2）
A 取景 = 在 H 当前层基座上扩展关系邻居（S1-5），不新建/修改 membership
同一曲线：同一 (DataSource, params) 两次 frame（H vs A）→ cluster_run_id/partitions/membership 相同
```
**反例**：A 维度下重新聚类（改变簇）；把 A 的挂接节点写入 membership；跨维度使用同一 cluster_key 断言同簇；H 每层不嵌套。
**边界**：A 可见节点不属于任何簇成员（只是 appearance，S0-7）；未来 relation 维度若定义簇，须重开 S2/S1；H 跨族不能共享 parent。
**U 映射**：U-8、U-10、U-21、U-31。
**建议裁决**：采纳"H 产生簇、A 不产生/不改簇"；机检 A 切换不改 cluster run；跨维度多归属留未来。
**证据等级**：A（S0-7；S1-4/S1-5/S1-13；`ENGINEERING-PLAN.md:387,455`）；**本项目假设**（"维度不输入 cluster"的机检实现）。

---

## 11. S2-11 持久化与缓存（派生缓存；D-3）

**定义/规则（一句话）**：簇/成员/边/稳定性全部是**派生缓存**（可重建、非事实源），不写产品 sidecar/新拓扑段；旧 run 不可变、保留审计；缓存键=run_id；删除/重建不影响知识库事实。

**形式化**：
```
缓存内容 = ClusterRun{run_id, corpus_manifest_sha, view_family_id, algorithm_id/version, params_hash, status,
                     previous_run_id, clusters[], memberships[], cluster_edges[], stability}
存放：`.memoria/build/clusters/<run_id>.json`（S6 定精确路径；可再生、非事实源）
不写：sidecar `edges[]`/`knowledge_points[]`、md、manifest、新顶层段（D-3）
原子写 + 内容 sha；旧 run 只读；GC/配额 S6 定
回滚：删除缓存/忽略 run（事实源未改）；重建 = 同输入同 run_id/内容
```
**机检条件**：
```
- 缓存写路径不在 sidecar/md/manifest/新顶层段（D-3 grep/契约检查）
- 缓存可重建：删除后同输入重算得到同 run_id/同内容 sha
- 旧 run 只读；缓存损坏/缺失 ⇒ 重算，不影响事实
- agent 无写缓存路径（allowlist）
```
**反例**：把簇/成员写入 sidecar 或新段（D-3 违反）；把 cluster_key 当事实键写进 KP；缓存与 manifest 不一致仍当有效（应 fail-closed/重算）；删旧 run 破坏审计。
**边界**：缓存缺失 ⇒ 重算（不代表数据变化）；缓存损坏 ⇒ 重算并记录；跨版本 schema 不兼容 ⇒ 丢弃旧缓存（不影响事实）；agent 不得写缓存（S2-13）。
**U 映射**：U-21、U-31、U-32。
**建议裁决**：采纳派生缓存 + D-3 禁令 + 不可变 run；S6 需求：路径/schema/原子写/GC/审计引用/stale 判定。
**证据等级**：A（S0 D-3；`ENGINEERING-PLAN.md:458-459`；`.memoria/build` 可再生缓存 ontology §5.2）；**本项目假设**（精确路径/GC 由 S6）。

---

## 12. S2-12 度量与验收（可复算指标/G6 快照）

**定义/规则（一句话）**：每 run 必须产出可复算指标：内聚/桥分布、簇数/大小/singleton 比例、稳定性、确定性证据；G6 快照记录 cluster run id + params + cluster_key 清单；S2 定义指标与记录，数值门禁由 S8 定。

**形式化（指标清单）**：
```
per cluster: |C|, μ, β, bridge_per_member, single_anchor_bridge, singleton flag
per run: cluster_count, size_distribution, singleton_ratio, coverage=Σ|C|/|K_f|,
         modularity Q（可选）, determinism_hash（canonical partitions sha）
per pair runs: jaccard_weighted, churn, split/merge, cluster_count_delta
G6 snapshot 字段：corpus_manifest_sha, run_id, algorithm_id/version, params_hash,
                  cluster_key 列表, μ/β 摘要, stability 摘要
```
**机检验收（S2 冻结的，不含数值门禁）**：
```
- 同输入重复 run：partitions canonical sha 相同（确定性）
- 所有块满足 partition + μ/β（或 singleton）；指标可从 cluster 数据复算
- G6 快照字段齐全；G6 的"语义统计"不得把 structural cluster 当 semantic（机器标记 source=derived_cluster）
- 失败/降级：status=degraded + warning，不得输出"正常"指标
```
**数值门禁（建议交 S8）**：τ_coh/τ_bridge、Jaccard≥0.8、singleton_ratio 上限、cluster_count 范围、性能预算；S2 不冻结数值（避免用未测阈值固化契约）。
**反例**：只报簇数不报 μ/β（无法判断质量）；用随机/时间相关指标；把降级 run 当正常指标；G6 语义分子含 structural cluster。
**边界**：首次 run（无稳定性）；空图/全 singleton（coverage<1 因为 singleton? coverage should include singleton members =1; define coverage=Σ|C|/|K_f|=1 always; use non_singleton_coverage separately）；指标对空数据 fail-visible。
**U 映射**：U-2、U-32、U-13。
**建议裁决**：采纳指标清单/复算/G6 快照；数值门禁 S8；S2 要求确定性/分区/μ/β/稳定性可复算。
**证据等级**：A（U-32；S0/S1 acceptance patterns；`ENGINEERING-PLAN.md:439-458`）；**本项目假设**（指标字段/候选阈值）。

---

## 13. S2-13 与 agent（重聚类/只读/提议/审计）

**定义/规则（一句话）**：agent 可以**请求确定性聚类服务**（读 run/触发重算）并读取结果用于检索/取景，但**不得写 membership/簇缓存/manifest**、不得改参数后不审计地生效；提议参数/重聚类需审计，确定性服务同输入同输出。

**形式化**：
```
服务：build_clusters(DataSource, params) → ClusterRun | FailClosed
agent 允许：读 ClusterRun；请求重算（若 cache miss/stale）；提议 params/阈值（提案，不直接生效）；
           读取 run/key 用于 S9 检索/取景
agent 禁止：写 cluster/membership/sidecar；改写缓存文件；静默改 params；改渲染状态
审计：{run_id, params_hash, corpus_manifest_sha, trigger, requester, status}
失败：stale cache ⇒ 重算或 fail-closed；参数非法 ⇒ 错误码；不得返回"猜测簇"
```
**机检条件**：
```
- build_clusters 为纯函数：同 (DataSource, params, algorithm version) 输出同 run/内容
- agent 触发重算产生审计事件；params 变更不静默生效
- agent 无写 membership/缓存/manifest 接口；跨 KB 拒绝
- stale 缓存 ⇒ 重算或 fail-closed，不返回猜测簇
```
**反例**：agent 直接写 `.memoria/build/clusters`；agent 用不同参数得到另一套簇并当事实；不审计触发重算；把簇当 semantic 前提（G6）。
**边界**：agent 触发重算=同确定性服务，不改变事实；离线/失败降级见 S9；跨 KB 拒绝；agent 只能读自己 KB。
**U 映射**：U-2、U-29、U-32。
**建议裁决**：采纳"只读+请求确定性服务+提议参数+审计"；agent 不写簇缓存/事实；S9 用 run 接口。
**证据等级**：A（S0-10；S1-14 确定性服务；`ENGINEERING-PLAN.md:301-303`）；**本项目假设**（服务签名/审计字段）。

---

## 14. 覆盖矩阵

### 14.1 U 覆盖

| U# | 要点 | S2 落点 |
|---|---|---|
| U-6 | 代表子图节点、外观更大 | S2-1/S2-8（cluster 节点 ≥2 成员；singleton 不作代表节点） |
| U-13 | 非严格连通子图/零星桥 | S2-1/S2-3（β） |
| U-14 | 按语义划分小群 | S2-2（μ/权重） |
| U-15 | 语义边挂接一跳 | S2-9（桥/内部边）+S1-5 |
| U-17 | 背后图不带入 | S2-9/S2-8（展开只子簇；桥呈现 S4） |
| U-21 | 多归属 | S2-6/S2-10 |
| U-22 | 新一跳 vs 更深 | S2-8（展开=导航）/S1-5 |
| U-31 | 多归属上限 | S2-6（v1 不设上限，S6 可配置） |

### 14.2 S0/S1 条款一致性

| 条款 | S2 落实 | 检查 |
|---|---|---|
| S0-2 层次 partition/最小粒度 | S2-1/S2-8 | 同族同层 partition；叶 KP |
| S0-4 簇定义/身份 | S2-1/S2-7 | μ/β；run-scoped id + key |
| S0-7 多归属 | S2-6 | 成员≠出现；同族单归属/跨族多归属 |
| S0 D-2/D-3 | S2-7/S2-11 | 身份；不写 sidecar |
| S0 R-3 | S2-9 | data_edge_ids/expand 子集 |
| S1 H/A 分工 | S2-10 | H 产生簇；A 不影响簇 |
| S1 view_family | S2-1/S2-10 | 簇属于 H view_family |
| S1 R-S1-11 | S2-8/S2-9 | H 派生边映射 |

---

## 15. 仍存争议 / 待 Lead·SE 裁决

1. **τ_coh=0.04 / τ_bridge=0.15 的默认值**：来自 frozen 稀疏语料 probe；live 语料需 S8 复标定。是否在 S2 冻结默认值，还是只冻结公式+参数（本提案建议冻结默认值但允许 S8 改配置）。
2. **权重策略**（semantic=1.0 / structural=0.5 / extend=0.3 / reference=0.2）：是否把 structural contain 作为 0.5 证据；反对意见会认为"簇必须只用 semantic 标签"，则 frozen 语料将几乎无簇（需 S2/Lead 裁决 U-14 的"语义关系"范围）。
3. **单点块**：本提案允许 singleton 在 partition 中但不作代表节点；反方可能要求 singleton 必须合并/不显示。
4. **算法依赖**：Louvain 主选需实现/依赖（networkx 已具备，但产品依赖需 S6/S9 决定）；若产品不允许第三方图算法库，需自实现 Dijkstra/Louvain 伪代码。
5. **run 粒度**（每 view_family 一个 run 含所有层 vs 每层一个 run）：本提案建议每 view_family 一个 run（嵌套父子同 run）；与 ER-03 草案 `CLUSTER_RUN.level_id` 字段需 S6a 对齐（改 `level_chain_id`/nullable）。

---

## 16. 证据锚（详见 `S2-evidence-A.md`）

```text
原话：vision.md:23-24（U-6/U-7）、:30-32（U-13/U-14/U-15）、:34（U-17）、:38（U-21）、:39（U-22）、:70（U-31）
S0：S0-terms-v1.md:30-33（S0-2）、:43-47（S0-4）、:56-61（S0-6/R-3）、:65-68（S0-7）、:98-107（D-2/D-3）
S1：S1-dimensions-v1.md:13-15（H/A）、:57-66（H 派生边/映射谓词）、:137-155（覆盖矩阵）
工程：ENGINEERING-PLAN.md:101-121（CLUSTER/MEMBERSHIP 实体）、:201-214（实体表）、:252-262（D-ER）、:385-462（ER-03 S2 增量）
代码（反例/现状）：graph-groups.js:2,83,123-126（并查集单值）；graph-engine.js:167-181；app.js:1845；collector.py:46-99；edge_derivation.py:787-793
```
