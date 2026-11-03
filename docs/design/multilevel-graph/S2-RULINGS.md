# S2 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`（U-1..U-35）；`S2-charter.md`；
> 上游冻结 `S0-terms-v1.md`（sha `241b1e1e…`）、`S1-dimensions-v1.md`（sha `6676c71d…`）。
> **输入**：提案 A `S2-clustering-proposal-A.md`（sha `b14bb379…`）、提案 B `S2-clustering-proposal-B.md`（sha `5b40429f…`）、`S2-objections.md`。
> **状态**：S2 **未冻结**；A 有 1 条 P0（μ/β 语义污染），另有 4 条 P1 必须关闭。本文件是修订轮唯一依据。
> **日期**：2026-11-03（Asia/Shanghai）。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P0-1：A 的 μ/β 用 reference/structural 当证据 | 读 A 的 weight_policy（structural 0.5 / extend 0.3 / reference 0.2）与 S0-1/S0-4 | **成立**：S0-1 冻结「`reference` 永不算语义边」，S0-4 要求语义内聚；参照 A 的反例（仅一条 reference 边 → μ=0.2 > τ=0.04 被判为簇），属于语义污染，必须修 |
| P1-2：划分算法确定性/产品依赖 | 读 A（seeded Louvain + networkx 依赖未批）与 B（HAC 确定但 O(n²) 无 probe） | **成立**：需冻结算法实现契约或选确定性算法 |
| P1-3：cluster run 粒度与身份公式不一致 | 读 A（per view_family，含所有层）与 B（per (level,view_family)） | **成立**：影响 G6/缓存键/curation 引用，必须统一 |
| P1-1：τ 来自加权（含非语义）probe | 读 A 的 τ=0.04/0.15 标定来源 | **成立**：语义-only 后数值不可沿用，需重新标定 |
| P1-4：agent 可请求重聚类/改参数 | 读 A S2-13 与 S0-10/S1-14 | **成立**：v1 只能只读或"创建新 run + 审计、不自动采用" |
| 簇≠严格连通分量 | 两版都禁 UnionFind 当簇，且 A 有 frozen probe（连通分量 μ=0.0233 < τ） | PASS |

## 1. 跨议题裁决（R-S2-1..R-S2-8）

### R-S2-1（P0）μ/β 只允许语义边
- **裁决**：内聚度 μ、桥 β **只使用 `label=semantic` 的 `E_sem`**；`reference`、`contain(structural)`、非 semantic 的 extend **权重为 0**，不进入 μ/β 分子分母；它们只可用于「结构诊断/背景信息」，不得作为簇成立证据。
- **机检**：`μ/β` 的输入边集 == `E_sem`；任何 reference/structural 边出现在 μ/β 计算中 ⇒ FAIL。
- **理由**：S0-1/S0-4 冻结；解决 P0-1。

### R-S2-2 τ 的标定与冻结方式
- **裁决**：S2 冻结 **公式 + 参数类型/范围/失败语义**；默认值必须由**语义-only probe**（frozen 语料 + 演示库）标定后在修版中给出；若标定后语义簇过稀疏（例：frozen 语义边近 0），允许"几乎无簇"作为**合法状态**，不得用结构边凑簇（由 S4/S3 处理 default 视图退化）。
- **机检**：τ 参数化并进入 `params_hash`；默认值有出处（probe 产物路径）；非法参数 fail-closed。
- **理由**：解决 P1-1；不把"无语义簇"伪装成有簇。

### R-S2-3 划分算法确定性契约（v1 = 确定性 HAC）
- **裁决**：v1 主算法 = **确定性层次凝聚聚类（HAC）**，纯自实现、无网络库依赖；冻结精确伪代码、距离/链接准则、tie-break（min canonical id）、序列化与 golden（同输入两次运行逐字节一致）。Louvain/CNM 不作 v1 主路径；失败或规模超限 ⇒ 显式 `degraded`（不得静默回退到连通分量）。O(n²) 规模风险由 S9/S8 评估，S2 只要求显式上限与降级。
- **机检**：两次运行 run 字节一致；伪代码可复算；`degraded` 状态可枚举；不得 import 未批准第三方依赖。
- **理由**：解决 P1-2；同时满足 B 的确定性诉求与 A 的可复算诉求。

### R-S2-4 run 粒度与身份（统一）
- **裁决**：`cluster run` 粒度 = **`(level, view_family)`**；`cluster_run_id = sha256(canonical(corpus_manifest_sha, view_family_id, level_id, algorithm_id, algorithm_version, params_hash))`；父子层用 `parent_run_id` 关联；`local_seq` 按成员最小 canonical id 排序；`cluster_key` 按 D-2（成员集合 + 算法 + 版本 + 参数）计算。
- **机检**：run_id 不含/含 level 的公式唯一；G6 快照可复算；curation 引用同时记 run_id+cluster_key。
- **理由**：解决 P1-3；与 S1 `(level, view_family)` 一致。

### R-S2-5 agent 权限（v1 只读 + 受审计的"新建 run"）
- **裁决**：v1 agent **不得**改 membership/缓存/manifest/渲染状态，**不得自动采用**新 run；只允许：① 只读现有 run；② 请求"新建一个候选 run"（必须带 `requester/reason/params` 审计），候选 run **不自动替换**当前视图，采用与否由人/S5 决定。A 的"agent 提议参数"保留为"请求参数"，不直接生效。
- **机检**：agent 无写 membership/缓存路径；候选 run 状态 `candidate` 与 `adopted` 分离；审计字段必填。
- **理由**：解决 P1-4；与 S0-10/S1-14 一致。

### R-S2-6 单点簇/根/覆盖率语义
- **裁决**：单点块允许，**μ=null（未定义）**（不是 1），不作"代表子图节点"；L0 全库一簇用显式 `root_exempt=true`（不是普通簇）；覆盖率指标改为 `覆盖的 KP 数 / 全库 KP 数`（不能是 Σ|C|/|K| 恒 1）。
- **机检**：singleton `μ=null`、`representative=false`；root_exempt 标志显式；覆盖率公式正确。
- **理由**：解决 P2 差异。

### R-S2-7 与 S1 的命名/角色边界
- **裁决**：`Membership.role` 不得复用 S1 的 node `role=bridge` 语义；桥只作为**边状态**（`bridge`/`bridge_only`）与成员统计，不改变节点 kind；簇节点 `kind=cluster`、KP 节点 `kind=kp`；A 维度不产生/不改变簇（机检：同 DataSource+params 下 H/A 切换 cluster run 不变）。
- **机检**：membership 无与 S1 node role 冲突的枚举；A 切换不改变 run。
- **理由**：保持 S0-9/S1 边界。

### R-S2-8 并集项
- A 吸收 B：HAC 确定算法、语义-only μ/β、per (level,view_family) run、覆盖公式、只读 agent；
- B 吸收 A：frozen probe 方法、权重（语义边内部再分级需 S2 表决但不得含非语义）、`root_exempt`、降级路径、G6 度量字段；
- 双方统一：τ 标定产物、run_id 公式、singleton 语义、membership role 边界。

## 2. 修订轮任务

**A-v2**：落实 R-S2-1..R-S2-8；重跑**语义-only probe**（frozen + 演示库）给出 μ/β/τ 与簇数；产出 `S2-clustering-proposal-A-v2.md` + 变更表。
**B-v2**：落实 R-S2-1..R-S2-8（含 HAC 伪代码/tie-break/golden、per-level run、覆盖/singleton/role、只读 agent）；产出 `S2-clustering-proposal-B-v2.md` + `S2-objections-v2.md`。
**SE 工程校核（task-302）**：等 v2 齐后执行；检查簇/成员/身份/重聚类/算法契约/多归属/持久化的 ER/DFD/状态图增量与 S0/S1 一致。

## 3. S2 冻结门禁（同章程 §7）

1. A-v2/B-v2 关闭全部 R-S2 与 P0/P1（逐条证据）；
2. SE 工程校核 PASS；
3. Lead 独立机检（μ/β 只含语义边、HAC 确定性、run 身份、τ 标定、singleton/root、多归属、D-3、agent 只读）；
4. 与 S0/S1 无冲突；
5. 冻结 `S2-clustering-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0/S1 冻结稿；S2 冻结前不开工实现；所有修订保留旧版。
