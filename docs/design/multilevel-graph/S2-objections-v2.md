# S2 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S2-RULINGS.md`（sha `4a83c8a9…`，R-S2-1..R-S2-8）。
> **对象**：`S2-clustering-proposal-A-v2.md`（主办研究，sha **`154cf0981dbdc441fb18e378645f63d930271216273a6af0550f8ba21fd75104`**，37,934 B）与 `S2-clustering-proposal-B-v2.md`（本复核方，sha **`5a1d299d11293ed3d671a79a66866a23d6aca38b1468faf61c85672e3444ab8c`**，26,821 B）。
> **独立性**：B-v2 于 19:23:55 落盘，A-v2 19:25:59 才出现；B-v2 写作时未读 A-v2；下方为落盘后对照。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S2-RULINGS/S0/S1。

---

## 0. R-S2 关闭矩阵

| 裁决 | A-v2 落位 | B-v2 落位 | 判定 |
|---|---|---|---|
| R-S2-1 μ/β 只 E_sem | S2-1/S2-2/S2-3/S2-9：语义-only + 输入断言；reference/structural 仅 diag | S2-2/S2-3/S2-9：语义-only + 输入断言 + reference-only 反例 | **关闭** |
| R-S2-2 τ 标定 | 语义-only probe（frozen/showcase E_sem=0 + 合成夹具），τ_coh=0.5/τ_bridge=0.25；产物 `s2-semantic-probe/results.json` | probe 方案 + 标定流程；τ 暂定 0.5/0.25（出处 A-v2 probe，B 独立复算 pending）；无 E_sem 时 `no_semantic_edges` | **基本关闭**；B 的独立复算/probe 产物尚未落盘（P1-2） |
| R-S2-3 HAC 契约 | 纯自实现 average-linkage HAC；dendrogram + target_k 切分；tie-break/golden/序列化；不允许第三方 | 纯自实现 HAC；**约束合并（按 μ/β 门控）无 target_k**；tie-break/golden/序列化；O(n³) 上限+degraded | **各自有契约但两版算法不同**（P1-1） |
| R-S2-4 run 身份 | per `(level,view_family)`；run_id 含 level；parent_run_id；local_seq by min id；cluster_key D-2 | 同；run_id 公式含 level；parent_run_id；local_seq；cluster_key D-2 | **关闭**（params_hash 内容随算法差异，见 P1-3） |
| R-S2-5 agent | 只读 + candidate run（requester/reason/params 审计；不自动采用；不写） | 同；candidate/adopted 分离；禁写 membership/cache/manifest/render | **关闭** |
| R-S2-6 singleton/root/coverage | singleton μ=null/representative=false；root_exempt L0；coverage=representative 覆盖 KP/全库 | 同；coverage 已修正为 representative-only；root_exempt；μ=null | **关闭**（B 自修 coverage） |
| R-S2-7 role/A 不变 | Membership.role∈{member}（无 bridge）；A 不变簇伪代码 | role 不含 bridge；A 不变簇伪代码；bridge 只作边状态 | **关闭** |
| R-S2-8 并集 | 吸收 B 的 HAC/coverage/只读 agent/语义纯净；保留 probe/root/降级/G6 | 吸收 A 的 probe 方法/root_exempt/降级/G6；HAC/coverage/只读/语义纯净 | **关闭**（细节差异见 §1） |

**结论**：R-S2 两版均基本关闭，**无 P0**；剩 P1-1（HAC 两版算法契约不同）、P1-2（B 独立 probe 产物缺失）、P1-3（params_hash/run 身份字段随算法不同）需 Lead/SE 冻结前统一。

---

## 1. A-v2 / B-v2 逐项差异（S2-1..S2-13）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S2-1 定义/边界 | 语义-only；singleton μ=null/representative=false；L0 root_exempt；禁止 UnionFind | 同；全库一簇 degenerate；root_exempt；禁止 UnionFind | 核心一致；A root_exempt/B root_exempt；B 的 degenerate 表述更保守；**并集**。 |
| S2-2 μ | E_sem-only 密度；单位权；τ_coh=0.5（probe 标定）；singleton μ=null | 同公式；τ_coh 暂定 0.5（A probe 出处，B 独立 pending）；singleton μ=null | 公式一致；**τ 证据**：A 有 probe 产物，B 仅为方案+暂定值（P1-2）。 |
| S2-2b probe | 实际 probe（frozen/showcase E_sem=0 + synthetic two_triangles/pair/triangle/star4/path）；结果 `probe.py/results.json` | probe 方案（frozen+演示库+合成夹具流程/输出 schema）；引用 A probe 产物为暂定 τ 出处，独立复算 pending | A 证据更强（实际产物）；B 诚实但未独立复跑（P1-2）。 |
| S2-3 β | E_sem-only；τ_bridge=0.25；diag 结构桥 | E_sem-only；τ_bridge 暂定 0.25；诊断 | 公式一致；τ 证据同 P1-2。 |
| S2-4 算法 | **标准 average-linkage HAC 建完整 dendrogram，按 target_k_ℓ 切分**；纯自实现；tie-break min id；golden；target_k 序列 S8；`params_hash` 含 target_k/min_cluster_size | **约束合并 HAC：每轮选最大 sim 且合并后 μ/β 合法的 pair，无 target_k**；纯自实现；tie-break；golden；`n_max`/degraded | **核心差异（P1-1）**：A 的 dendrogram+target_k 与 B 的 μ/β-gated greedy 输出可能不同；`params_hash`/run_id 不同；复杂度 A O(n²·merges)/最坏 O(n³)，B O(n³)。必须选一个 canonical 算法契约；B 的"约束合并"并非标准 HAC（顺序/门控导致非标准 dendrogram），A 更标准但需 target_k 来源。 |
| S2-5 稳定性 | per-level 不可变 run；Jaccard/churn/split/merge；显式触发 | 同；Jaccard+churn；触发 T1–T5 | 一致；A 更细（churn/split/merge记录）。 |
| S2-6 多归属/单点/root/coverage | 同族 partition/跨族多归属；singleton μ=null/representative=false；root_exempt L0；coverage representative-only；role {member} | 同；coverage 已修 representative-only；role 不含 bridge；不设上限 | 一致；B role 枚举未写死 `{member}`（A 更明确）。 |
| S2-7 身份 | per-level run；run_id 含 level；parent；local_seq by min id；cluster_key D-2；params_hash 含 target_k/min_cluster_size | per-level；run_id 含 level；parent；local_seq；cluster_key D-2；params_hash 含 tau/n_max | 公式一致但 **params_hash 内容不同**（P1-3），导致同输入同算法不同 run_id；须先统一算法契约。 |
| S2-8 嵌套/展开 | per-level parent_run_id；refinement；展开 KP；空/单点 | 同 | 一致。 |
| S2-9 边 | E_sem internal/bridge；结构仅 diag；data_edge_ids；H 按 S1 | 同 | 一致。 |
| S2-10 维度 | A 不变簇；build_clusters 无 dimension_id；伪代码 | 同 | 一致。 |
| S2-11 持久化 | per-level 派生缓存 `.memoria/build/clusters/...`；D-3 | 派生缓存/研究产物；D-3；S6 定路径 | 一致；A 路径更具体。 |
| S2-12 度量 | coverage representative-only；G6 字段；μ/β/singleton/diag | coverage 已修 representative-only；G6 字段；状态枚举 | 一致；A 有 diag_struct_bridge 字段，B 未列（B 可吸收）。 |
| S2-13 agent | 只读+候选 run（base_run_id/审计/不自动采用/禁写） | 只读+候选 run（requester/reason/params 审计/不采用/禁写） | 一致；A 多 base_run_id。 |

**总判断**：两版在语义-only μ/β、per-level run、singleton/root/coverage、只读 agent、D-3 上已收敛；A 在 probe 产物/标准 HAC/target_k、B 在约束合并/明确状态枚举（`partial_disconnected`）上各有取舍。**HAC 算法契约与 params_hash 是最后的分歧核心**。

---

## 2. 仍未解决的 3 点（建议 Lead/SE 冻结前裁）

### 2-1（P1）HAC 两版算法契约不同（dendrogram+target_k vs μ/β-gated greedy）

- **现状**：A-v2 S2-4 = 标准 average-linkage HAC，先建完整 dendrogram，再按每层 `target_k_ℓ` 切分（target_k 序列归 S8）；B-v2 S2-4 = 约束合并：每轮选最大 similarity 且合并后 μ/β 合法的 pair，无 target_k，直到无合法合并。两者同输入 + 同参数会产出**不同 partition/run**；`params_hash` 分别含 `target_k/min_cluster_size`（A）与 `tau/n_max`（B）。R-S2-3 要求"冻结精确伪代码/链接/tie-break/golden"，当前两份契约都自洽但互不兼容。
- **风险**：S2 冻结稿若并集两版，会出现两套"合规"实现；G6 快照/curation 引用不可比；target_k 由 S8 定（A）还是无 target_k（B）未裁。
- **修复**：Lead/SE 选一个 canonical 契约：推荐 **A 的标准 dendrogram + target_k 切分**（标准 HAC、层次 refinement 明确、target_k 可由 S4/S8 定），B 的 μ/β 门控作为**后验校验**（切分后检查 μ/β，不参与合并顺序），避免非标准合并导致不可复算；或反之选 B 但须定义 target_k 替代参数/终止。`params_hash` 字段随之冻结（见 2-3）。
- **证据**：R-S2-3；A-v2 S2-4；B-v2 S2-4；S2-1/R-2。

### 2-2（P1）B 的语义-only probe 独立产物缺失；τ 默认值证据链不完整

- **现状**：A-v2 已产出 `artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/{probe.py,results.json}`（frozen/showcase E_sem=0 + 合成夹具；τ=0.5/0.25）。B-v2 只写 probe **方案**与暂定 τ（注明"出处 A-v2 probe，B 独立复算 pending"），**没有 B 自己的 probe 产物**。R-S2-2 要求默认值由 probe 标定并给出出处；B 的默认值目前依赖 A 的产物，独立复核证据链不足。
- **风险**：A 的 probe 若被质疑（synthetic fixture 设计/阈值选择），B 无独立复算；S2 冻结稿的 τ 默认值证据只有 A 单源。
- **修复**：B（或 SE）在冻结前跑**同方法但独立实现**的语义-only probe（frozen+showcase+合成夹具），产出 `s2-semantic-probe-b/results.json`，与 A 的 τ/簇数对账；或 Lead 指定 A 的 probe 为唯一证据并让 SE 复跑（记录命令/版本）。τ 默认值必须带 `probe_artifact_sha`/命令；E_sem=0 时明确 no_semantic_edges。
- **证据**：R-S2-2；A-v2 S2-2b/probe 产物；B-v2 S2-2b。

### 2-3（P1）`params_hash`/run_id 字段集未冻结（算法依赖）

- **现状**：A-v2 `params_hash` 含 `weight_policy, tau_coh, tau_bridge, target_k, min_cluster_size, linkage, tie_break, algorithm_version`；B-v2 含 `tau_coh, tau_bridge, linkage, n_max, seed`（无 target_k，n_max 为 B 规模参数）。由于 2-1 算法未统一，run_id/G6/curation 引用字段也不同；同输入下 A/B run_id 必不同。R-S2-4 只要求公式含 params_hash，未冻结其内容。
- **风险**：冻结后 G6 快照/curation 无法跨实现对齐；"同输入同 run"无法验证；算法参数变更是否该产生新 run 不明确。
- **修复**：与 2-1 一起冻结 `params_hash` 的**规范字段集**（至少 algorithm_id/version, weight_policy=semantic_uniform, tau_coh, tau_bridge, linkage=average, tie_break=min_canonical_id, target_k 或 n_max, min_cluster_size；具体由 canonical contract 决定）；`run_id` 公式固定；任何字段变化 ⇒ 新 run；禁止未列入字段影响结果。
- **证据**：R-S2-4；A-v2 S2-7；B-v2 S2-7。

> 另：A 的 synthetic probe 阈值 0.5/0.25 是否可作为 S2 默认（而非 live 标定）需 Lead 在 2-2 中一并裁；B 的 `partial_disconnected` 状态与 A 的 `empty/partial` 命名需统一（P2）。

---

## 3. 其余 P2（不阻塞，但冻结前对齐）

| # | 项 | 判断 |
|---|---|---|
| P2-1 | B-v2 coverage 公式已自修为 representative-only（相对 B v1）；A 也是 | 已对齐；保留 A 的 `diag_struct_bridge` 字段给 B。 |
| P2-2 | 状态枚举：A `{ok,empty,partial_disconnected,degraded}`；B `{ok,no_semantic_edges,uncalibrated,size_exceeded,algorithm_failed,partial_disconnected}` | 需统一命名/映射（`empty` vs `no_semantic_edges`；`degraded`  vs 具体码）；B 更细，A 更聚合。 |
| P2-3 | Membership.role：A `{member}`；B "不含 bridge" 但未写枚举 | B 明确 `role={member}`；bridge 只作边状态（S2-7）。 |
| P2-4 | A 的 `target_k` 序列归 S8；B 无 target_k | 与 2-1/2-3 一并裁；若选 A 需定义每层 target_k 来源与单调性。 |
| P2-5 | A 的 synthetic fixtures（two_triangles/pair/triangle/star4/path） | 应作为 probe 产物固定；B 可复用并独立实现。 |
| P2-6 | A 的 `diag_struct_bridge/single_anchor_bridge`；B 未列 | B 吸收诊断字段；不得参与 valid。 |
| P2-7 | B 的 `O(n³)` 已修正（相对 v1 的 O(n²) 表述） | A 同 O(n³) 最坏；统一规模上限 S8/S9。 |
| P2-8 | A 的 cache path `.memoria/build/clusters/<family>/<level>/<run_id>.json`；B 只写 S6 定 | 统一 S6 需求；D-3 两版一致。 |
| P2-9 | A 的 agent 请求带 `base_run_id`；B 无 | 吸收 A 的 base_run_id（候选 run 基于哪个 run）以审计。 |
| P2-10 | 覆盖矩阵：A/B 都覆盖 U-6/13/14/21/31 等 | 合并覆盖矩阵；S2-10 A 不变簇两版一致。 |

---

## 4. 点名审查结论

1. **μ/β 可复算、阈值可机检、不退化严格连通分量**：A/B 均 E_sem-only、公式/pseudocode、禁 UnionFind；**PASS**；τ 证据 B 依赖 A（2-2）。
2. **划分算法确定性/可复算/降级**：两版均纯自实现/HAC/golden/degraded；**但算法契约不同（2-1）**，需统一。
3. **稳定性/重聚类触发**：A/B per-level run + Jaccard/churn/触发；**PASS**。
4. **多归属与 S0-7/S1 partition**：A/B 同族 partition/跨族重叠/不设上限；**PASS**。
5. **簇身份 D-2/curation**：A/B per-level run_id/cluster_key/curation 三字段；**PASS**；params_hash 待统一（2-3）。
6. **嵌套/空/单点簇**：A/B refinement/空禁/单点 μ=null/representative=false/root_exempt；**PASS**。
7. **簇与边/维度**：A/B E_sem internal/bridge；结构 diag；H data_edge_ids；A 不变簇伪代码；**PASS**。
8. **持久化 D-3**：A/B 派生缓存/不写 sidecar/新段；**PASS**。
9. **度量/G6**：A/B coverage representative-only/G6 字段；**PASS**；状态命名需统一。
10. **agent**：A/B 只读+candidate run+审计/不自动采用/禁写；**PASS**。

---

## 5. 结论

- R-S2 两版基本关闭，无 P0；A-v2 在 probe 产物/标准 HAC/target_k、B-v2 在状态枚举/约束合并/明确规模降级上各有取舍。
- **冻结前必须统一**：① HAC 算法契约（dendrogram+target_k vs μ/β-gated greedy）；② B 的独立 probe 产物/τ 证据（或 Lead 指定 A probe 为唯一证据并 SE 复跑）；③ params_hash/run_id 字段集。否则会出现两套合规实现/G6 不可比（P1）。
- 其余 P2 可后续场次；两版均未写产品代码/契约，未 commit；差异逐项列出未静默合并。
