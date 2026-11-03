# S2 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（sha `241b1e1e…`）、`S1-dimensions-v1.md`（sha `6676c71d…`），**不得违反**；`S2-charter.md`。
> **对象**：`S2-clustering-proposal-A.md`（主办研究，sha **`b14bb379f4b97f68327bf6c768400742f57d98b02f20d11999ba450865df6556`**，33,763 B）与 `S2-clustering-proposal-B.md`（本复核方，sha **`5b40429fcb6c5693d7e62af27b4b85701cf9b2d61e4861db67c8464ce62ba87f`**，24,361 B）。
> **独立性**：B 于 19:16:54 落盘，A 于 19:19:22 落盘；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0/S1 冻结。

---

## 0. A/B 差异总表（S2-1..S2-13）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S2-1 簇定义 | 簇=μ/β 块；非严格连通分量；singleton μ 豁免；L0 全库单块 root_exempt；ℓ>0 整库一簇=降级 | 同核心；空禁/单点允许；全库一簇标 degenerate；不 root_exempt | 核心一致；A 多 root_exempt（L0）与 singleton μ=null；B 更严格（全库一簇 degenerate），避免 L0 伪造 cluster；**A 的 root_exempt 需 Lead 裁**（P2）。 |
| S2-2 μ | **加权密度**：semantic=1.0 / contain(structural)=0.5 / extend(非semantic)=0.3 / reference=0.2；`μ=W_in/P`；τ_coh=**0.04**；singleton μ=null | **二值语义密度**：only label=semantic 权重 1，structural/navigation=0；`μ=内部语义边端点对/P`；τ_coh=**0.3**；n=1 定义 1（退化） | **根本差异（P0）**：A 把 reference/structural 当内聚证据，违反 S0-1（reference 不算语义）与 S0-4（语义内聚）；B 只用语义边。A 的 τ=0.04 与权重绑定，不能直接移植到语义-only。 |
| S2-3 β | **加权**跨簇 `W_out/(W_in+W_out)`；τ_bridge=**0.15**；bridge_per_member/single_anchor 诊断 | **语义边**跨簇比例（去重）；τ_bridge=0.2；无定义标 unknown | 同根问题：A 的 β 把 structural/reference 当桥（非语义）；B 语义-only；A 的 0.15 与权重绑定。 |
| S2-4 算法 | **deterministic seeded Louvain（weighted）主选**；CNM 降级；HAC 备选；连通分量禁止；E_rel=∅→全 singleton degraded | **确定性层次凝聚 HAC 主选**；标签传播备选；固定 tie-break；E_sem=∅→cluster_mode=none；禁止 UnionFind | A 的 Louvain 依赖 networkx/实现版本，跨版本确定性需钉死；B 的 HAC 更可控但 O(n²)。两者都禁止并查集；**算法选型需 Lead/SE 决定**（P1-2）。 |
| S2-5 稳定性 | 不可变 run；触发=manifest/关系证据/算法参数/显式请求；Jaccard/churn/split/merge；v1 全量重算 | 触发 T1–T5；Jaccard + τ_stable 默认 0.8；run_id 确定性；不随机 | 等价；A 更细（churn/split/merge），B 有默认阈值。并集。 |
| S2-6 多归属 | 多对多；同 `(level,view_family)` partition；跨族/层/维重叠；`max_memberships_per_kp` 可配置（v1 null）；role member/bridge | 多对多；同族 partition；跨族/层/维重叠；不设上限；membership≠视图出现 | 等价；A 的 role=bridge 可能混淆（bridge 是 S1 node role），B 更干净。 |
| S2-7 身份 | run_id=hash(manifest, view_family, algo, version, params)（**不含 level**）；local_seq 按 min(member id) 升序；cluster_key 公式；curation 记 run+seq+key，key 变 stale | run_id=hash(manifest, **level**, view_family, algo, version, params)；local_seq 按 (key,min id)；同 cluster_key；curation 记 run+key | **run 粒度不同**：A 每 view_family 一个 run（含所有层），B 每 (level,view_family) 一个 run；影响 G6/stability/curation；需 Lead 裁（P1-3）。 |
| S2-8 嵌套展开 | Π_{ℓ+1} refinement；展开到 KP；空禁；singleton 不作代表；root L0 全库单块 root_exempt；degenerate_refinement | 同 refinement；空禁/单点允许；无 root_exempt；全库一簇 degenerate | 核心一致；A 的 root_exempt 与 B 的 degenerate 取舍需裁。 |
| S2-9 簇与边 | internal/bridge 基于 E_rel（含 structural/reference 加权）；`contain(structural)` **参与 μ/β**；data_edge_ids 聚合非空；H 边按 S1 | internal/bridge 基于 **E_sem**；structural 只作结构内部边，不进 μ/β；data_edge_ids 聚合/H 按 R-3 | **P0 同源**：A 让 structural 参与 μ/β，与 S0-4/ S0-1 冲突；B 只语义边。 |
| S2-10 簇与维度 | H 每层独立嵌套划分；A 不产生/不改簇；cluster_run 输入固定 hierarchy | 同；A 不影响簇；维度切换不触发重聚类 | 一致。 |
| S2-11 持久化 | 派生缓存 `.memoria/build/clusters/<run_id>.json`；不写 sidecar/新段；旧 run 只读；可重建 | 派生缓存/研究产物；不写 sidecar/新段；缓存可重建；S6 定路径 | 一致；A 路径更具体（S6 定）；B 更保守。 |
| S2-12 度量 | per-cluster μ/β/桥/singleton；per-run cluster_count/size/singleton/coverage/modularity/determinism；G6 字段；数值 S8 | 指标集合类似；G6 字段；可复跑 | 等价；A 更细（modularity）；B 更简洁。 |
| S2-13 agent | agent **可请求重聚类**（读 run/触发重算）+ 提议参数/审计；不得写缓存/membership | agent **只读簇**，v1 不触发重聚类；重聚类由 T1–T5/用户动作；无写接口 | **策略差异**：A 允许请求触发（审计），B 更严格只读；S0-10/S1-14 只允许请求确定性服务；需明确 v1 是否允许 agent 触发（P1-4）。 |

**总判断**：A 在权重策略细节/阈值 probe、Louvain 选型、per-view_family run、root_exempt、agent 请求重聚类上更"功能化"；B 在语义纯净（μ/β only semantic）、算法可控（HAC）、run 粒度明确（level）、agent 最小权限上更保守。**A 的加权 μ/β 与 S0 冻结语义定义冲突，是最大问题**；B 需补语义-only 的阈值标定/算法论证。

---

## 1. 异议（按严重度；P0=违反 S0/S1 冻结；P1=冻结前必须裁决；P2=可冻结但补）

### P0-1（A）μ/β 把 reference/structural 当内聚/桥证据，违反 S0-1/S0-4/U-14

- **议项**：S2-2 / S2-3 / S2-9（U-1、U-13、U-14；S0-1/S0-4）。
- **异议**：A 的 `weight_policy` 给 `contain(structural)=0.5`、非 semantic 的 `extend=0.3`、`reference=0.2` 权重，并令 `E_rel = E_relation_min`（含 reference/structural）；S2-9 明确"contain(structural) 作为层次内部证据参与 μ/β"。但 S0-1 冻结：**`reference` 永不算语义边**；S0-4 冻结：簇=**语义内聚**度高（μ≥τ_coh），不是结构/引用密度。用非语义边算 μ/β，等于把"目录/引用/结构包含"当语义簇，直接违反 S0 冻结。
- **反例（最小）**：两个 KP 仅有一条 `reference` 边：按 A 权重 `μ=0.2/1=0.2 > τ_coh=0.04`，`β=0` ⇒ **被接受为簇**；按 S0-1/S0-4 该边不是语义，μ 应为 0，不能成簇。同理，同目录下一条 `contain(structural)` 权重 0.5 ⇒ 结构嵌套被当语义簇（U-14 失败）。再如全库 25 成员严格连通分量 μ=0.0233<0.04 被 A 判"不达标"——这个 0.0233 含 reference/structural 权重，不能证明语义内聚。
- **可行动修复**：`E_rel` 必须 = **semantic edges**（label=semantic：asserted 作者边 + semantic contain；`reference`/`structural` 权重 0）；μ/β 只算语义边；structural/reference 只能作为"结构诊断/视图背景"（S4）或单独 `structural_cohesion` 指标，**不得进入簇合格判据**。若 Lead 要让结构参与"分组"，它不能叫语义簇，必须另立 `structural_group` 词（S0 不含此概念），且不能违反 U-14。
- **严重度**：直接违反 S0-1/S0-4 冻结 ⇒ **P0，A 不得冻结**。

### P1-1（A）τ_coh=0.04 / τ_bridge=0.15 的默认值与"语义-only"不兼容

- **议项**：S2-2 / S2-3（阈值/默认值）。
- **异议**：A 的 τ_coh=0.04 是从**加权**（含 reference/structural）probe 得到的；一旦按 P0-1 改成语义-only，frozen 62 边中语义边极少，0.04 会导致几乎所有块不合格/只剩 singleton；A 自己也承认"该值来自稀疏冻结语料，S8 须 live 复标定"。B 的语义-only 默认 0.3 同样未经 frozen probe 标定（B 自认 PI）。
- **反例**：语义-only 下 2 KP 1 条 semantic 边 μ=1（合格），但 3 KP 2 条边 μ=2/3；一个 13 成员语义块可能几乎无边（μ≈0）——0.04 仍可能过松/过紧；没有 frozen 语义-only 分布就冻结阈值不可复算。
- **修复**：S2 冻结公式+参数**类型/范围/失败语义**，数值默认值由 S8 live 标定；在 S2 冻结稿中写"默认仅示例，非规范"；或冻结前用 frozen 语义-only 复算一份分布（B 级 probe）作为默认依据。
- **严重度**：不修则阈值无证据、可能大面积退化 ⇒ **P1（冻结前）**。

### P1-2（A/B）划分算法的确定性与产品依赖未钉死

- **议项**：S2-4。
- **异议**：A 主选 **deterministic seeded Louvain（weighted）**，依赖 networkx/Louvain 实现版本；"固定 seed/节点顺序"不能保证跨 networkx/平台版本逐位一致（Louvain 的随机顺序/社区合并 tie 可能变），A 自己在 §15.4 把"产品依赖需 S6/S9 决定"列为待裁。B 主选 HAC（O(n²)）虽确定但无 frozen 规模 probe/复杂度论证。章程预注册判据 1 要求"唯一结果或确定性分布"；没有固定算法版本/序列化/tie-break 的 Louvain 不满足。
- **反例**：同 seed/params 在 networkx 2.x 与 3.x 得到不同社区（节点合并顺序变化）；换 OS/浮点排序不同；产品不能引入 networkx（S6/S9 未批）；B 的 O(n²) 在 live 大图超 S8 预算但未标降级。
- **修复**：S2 冻结**算法实现契约**：algorithm_id+version+精确伪代码/tie-break/序列化（或自实现确定性算法，不依赖第三方版本）；跨环境 golden fixture 2x 逐字节一致；不可确定则必须给"确定性分布"（固定种子集合/分布报告）而非假装唯一；算法失败显式 degraded（A/B 均有 fallback，保留）。
- **严重度**：确定性/可复算是 S2 硬判据 ⇒ **P1（冻结前）**。

### P1-3（A/B）cluster run 粒度不一致（per view_family vs per level）

- **议项**：S2-7 / S2-5 / S2-12（D-2/G6）。
- **异议**：A 的 `cluster_run_id` 公式**不含 level**（per view_family，含所有层）；B 的公式**含 level**（per (level,view_family)）。S2-1 写"同一 (level, view_family) 的块族"，S0-2 partition 作用域也是 (level, view_family)；A 的 per-family run 与 S2-1 字面不一致（一个 run 多 level），影响 G6 快照、稳定性比较、curation 引用、缓存键。
- **反例**：同一 view_family 的 L1/L2 用两个不同 run（B）与一个 run（A）会得到不同 run_id、不同 stability 对比、不同缓存键；A 的 local_seq 跨层全局排序 vs B 每层排序，curation 引用不同；G6 快照字段 `run_id` 覆盖范围不同。
- **修复**：Lead/SE 裁"run 粒度"；推荐**每 (level, view_family) 一个 run**（与 S0-2/S2-1 partition 作用域一致，G6/curation 引用更精确），父子关系用 `parent_run_id`/`level` 字段；或每 family 一个 run 但明确 `level_chain` 与每层 local_seq 命名空间。不得两版并存。
- **严重度**：身份/G6 契约 ⇒ **P1（冻结前）**。

### P1-4（A）agent 请求重聚类是否越权未定

- **议项**：S2-13（S0-10/S1-14）。
- **异议**：A 允许 agent **请求重聚类**（读 run/触发重算）并"提议参数"；B 只读。S0-10/S1-14 只允许 agent **请求确定性取景服务**，不得直接改渲染状态；重聚类会生成新缓存/run（不改产品事实），但可能造成 cluster 漂移、影响 S9 检索结果；A 没有定义"agent 请求"的权限/审计/人类批准，也没有说参数变更是否即时生效。任务明确要求审"agent 是否越权（触发重聚类/写状态）"。
- **反例**：agent 用不同 params 请求重聚类得到另一套簇并当搜索前提（G6 双真相）；agent 请求触发覆盖当前 run 缓存；无审计；跨 KB。
- **修复**：v1 推荐 **agent 只读**（B）；若允许请求，必须：只创建**新 run**（不覆盖旧）、显式 `requester/trigger/reason` 审计、默认不自动采用（S9 需显式选择 run）、参数变更走 S1/S2 修订、不得写 membership/缓存；跨 KB 拒绝。Lead 裁 v1 策略。
- **严重度**：越权/双真相风险 ⇒ **P1（冻结前裁决）**。

### P2 清单

| # | 项 | 异议/证据 | 修复 |
|---|---|---|---|
| P2-1 | A 的 singleton μ=null / B 的 μ=1 | 两版对单点簇的语义证据定义不同；A 更安全（不参与阈值），B 的 1 可能误导 | 统一 μ=null/singleton exempt（A 做法） |
| P2-2 | A 的 `root_exempt` L0 全库单块 | S2-1 允许 L0 根块；但 H 默认从 L1 起，需明确 L0 是否可渲染；B 用 degenerate | Lead 裁 root_exempt；避免把全库当"簇"显示 |
| P2-3 | B μ/β 语义-only 阈值 0.3/0.2 未标定 | B 自认 PI；A 的 probe 不可直接用于语义-only | S8/frozen probe 标定；S2 冻结公式+参数类型 |
| P2-4 | B 的 HAC O(n²) 无规模 probe | live 大图性能未测；S8 预算 | S2 标"复杂度待 S8"；或加 fallback |
| P2-5 | A 的 `Membership.role ∈ {member,bridge?}` | bridge 是 S1 node role/edge state，不是 membership role；易混淆 | 删除 membership bridge role；bridge 留在边/节点 state |
| P2-6 | A 的 coverage=Σ|C|/|K|=1 恒成立 | 指标无信息量（A 已注）；需 non_singleton_coverage | 冻结指标定义时用覆盖率/单点比例分开 |
| P2-7 | A/B 的 G6 快照字段 | 两版字段略异；需统一 run_id 粒度（P1-3） | 统一字段（corpus/level/family/algo/version/params/run/key 列表/metrics digest） |
| P2-8 | A 的 weight_policy 可配置 | 若允许配置，必须 params_hash 覆盖并禁止隐含默认；否则 mu 不可复算 | 权重策略进 params_hash，非法 fail-closed |
| P2-9 | A 的 Louvain/CNM 降级 | 降级为扁平分块后"再构造层次"如何保证 refinement 未定义 | 明确 fallback 层次构造和 verification；失败显式 degraded |
| P2-10 | S2-10 A 不影响簇 | 两版一致，但机检要"同 DataSource+params 下 H/A cluster run 相同"；A 未给断言伪代码 | 补机检伪代码（B 有） |

---

## 2. 点名审查项结论

1. **μ/β 可复算、阈值可机检、是否退化成严格连通分量**：公式可复算；A 的 μ/β 因含 reference/structural **不是语义内聚**（P0-1）；B 语义-only 可复算。两版都明确簇 ≠ 严格连通分量（A/B 都禁用 graph-groups UnionFind 当定义），**区分 PASS**，但 A 的权重污染使"语义"失效。
2. **划分算法确定性/可复算/降级**：A Louvain seeded（跨版本依赖未钉死，P1-2）；B HAC 确定性但 O(n²)/无 probe；两版都有 degraded 路径（A singleton/degraded；B none/degraded）；**需算法契约**。
3. **稳定性/重聚类触发**：A/B 都定义触发+Jaccard；A 触发含"关系证据版本/显式请求"，B T1–T5；可机检；A 的"显式请求"与 agent 权限需 P1-4；**方向 PASS**。
4. **多归属与 S0-7/S1 partition 一致/偷偷设上限**：A/B 都同族 partition/跨族重叠；A `max_memberships_per_kp` 可配 null；B 不设上限；**PASS**；A role=bridge 小问题 P2。
5. **簇身份/D-2/curation**：A/B 都 D-2 run+local_seq+key，curation 记 run+key；**PASS**，但 run 粒度不一致（P1-3）与 local_seq 排序规则需统一。
6. **嵌套/空/单点簇**：A/B 都 refinement/空禁/单点允许；A root_exempt vs B degenerate（P2-2）；**PASS（有取舍）**。
7. **簇与边/维度**：A structural 参与 μ/β（P0-1）；B 语义-only；A/B 都要求 H data_edge_ids/R-3；A 不影响簇两版一致；**A 需修 P0**。
8. **持久化 D-3**：A/B 都派生缓存、不写 sidecar/新段；**PASS**。
9. **度量/G6 可复跑**：A/B 都定义指标/G6 字段/确定性；A coverage 恒 1（P2）；B 缺 probe（P2）；**方向 PASS**。
10. **agent 越权**：A 允许请求重聚类（P1-4），B 只读；S0-10/S1-14 只允许请求取景服务；**v1 倾向 B，需 Lead 裁**。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P0-1（A）μ/β 使用 reference/structural 权重，违反 S0-1/S0-4**：两个仅 reference 边的 KP 在 A 下 μ=0.2>0.04 即成"簇"；structural contain 权重 0.5 使目录嵌套成语义簇。必须改为 `E_sem`（label=semantic）only；structural/reference 只能作结构诊断，不得进 μ/β；否则 A 不得冻结。
2. **P1-2（A/B）算法确定性/产品依赖未钉死**：A 的 seeded Louvain 跨 networkx/平台版本不保证逐位一致，且产品依赖未批；B 的 HAC O(n²) 无规模 probe。须冻结算法实现契约（精确伪代码/tie-break/序列化/golden 2x 一致），或自实现确定性算法；失败显式 degraded。
3. **P1-3（A/B）cluster run 粒度与身份公式不一致**：A per view_family（不含 level），B per (level,view_family)；直接影响 G6 快照/稳定性/curation 引用/缓存键。须 Lead/SE 裁 run 粒度并统一 run_id/local_seq 公式。

> P1-1（阈值语义-only 不兼容）、P1-4（agent 是否可请求重聚类）建议同轮裁；P2 清单随后续场次。

## 4. 结论

- **A 有 P0（μ/β 语义污染）⇒ A 不得直接冻结**；B 无 P0，但需补语义-only 阈值标定、算法规模/依赖、run 粒度与 agent 策略。
- 两版在簇定义/身份/多归属/持久化/降级/B 的语义纯净上大体一致；A 在权重 probe/算法选型/root_exempt/agent 请求上更功能化，B 在语义纯净/算法可控/最小权限上更保守。
- 差异逐项列出，未静默合并；未写产品代码/契约，未 commit。

> 参考锚：S0-1/S0-4 `S0-terms-v1.md:21-26,43-47`；S1 H/A `S1-dimensions-v1.md:57-66`；`graph-groups.js:2,83,123-126`（UnionFind 反例）；A S2-2/S2-3/S2-9（权重）；B S2-2/S2-3/S2-9（语义-only）。
