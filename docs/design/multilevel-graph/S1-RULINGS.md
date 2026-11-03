# S1 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`（U-1..U-35）；`S1-charter.md`；上游冻结 `S0-terms-v1.md`（sha `241b1e1e…`）。
> **输入**：提案 A `S1-dimensions-proposal-A.md`（sha `58d6d4f6…`）、提案 B `S1-dimensions-proposal-B.md`（sha `9947dd7a…`）、
> 异议 `S1-objections.md`（sha `327f3984…`）。
> **状态**：S1 **未冻结**；无 P0，但有 3 条 P1 + 1 条 P1 数据边问题必须关闭。本文件是修订轮唯一依据。
> **日期**：2026-11-03（Asia/Shanghai）。

## 0. Lead 复核（不是转述）

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 H 的 relation_sources 自相矛盾 | 读 A S1-2/S1-4/S1-12（L661-662 等）与 R-1 | **成立**：同一 reference 上下文边出现三种结论（⊇min / 仅上下文 / 仅 contain），视图不唯一 |
| P1-2 E_relation「只增不删」不可机检 | 读 A validator 只断言当前 ⊇min | **成立**：删掉历史新增源仍 PASS，R-1 可被静默绕过 |
| P1-3 H 的 hop 与 S0-5 冲突 | 读 S0-5 原文（恰好一条 `E_relation(D)` 边）与 A/B 的 `hop_unit=level` | **成立**：H 的块→子块边不是 DataSource 的 E_relation 边，按 S0-5 机检会 FAIL |
| P1-4 H 派生边缺 `data_edge_ids` | 读 A S1-4 与 S0 R-3 | **成立**：违反 R-3 聚合/折叠边身份要求 |
| A 关联维覆盖 U-10 | 读 A S1-5 关系源表 | **PASS**（未窄化） |
| 维度不进 ViewModel | 读 A/B S1-13 | **PASS** |
| reserved 未偷实现 | 读 A/B S1-3/S1-15 | **PASS** |

## 1. 跨议题裁决（R-S1-1..R-S1-8，修订轮必须落实）

### R-S1-1 H（层次维）不参与关系扩展
- **裁决**：`H.relation_sources = []`。H 的「块→子块」边是**层次派生边**，不是 `E_relation`；H **不挂接关系邻居**。
- **R-1 的适用范围**：`E_relation_min` 只约束**关系扩展维度**（v1 = A）；H 不做关系扩展，故不要求 `H.relation_sources ⊇ E_relation_min`（A 的 S1-2 该断言改为「active 的 relation_expansion 维度 ⊇ min」）。
- **H 派生边身份**：H 的块→子块边必须携带 `data_edge_ids`（R-3 扩展到 H），可映射回 DataSource 的 contain(structural) 数据边。
- **理由**：解决 P1-1/P1-4，同时保持 R-1 原意（不约束层次导航）。

### R-S1-2 S0-5 的「一跳」只约束关系扩展维度
- **裁决**：S0-5 的「恰好一条 `E_relation(D)` 边、不闭包」适用于**关系扩展维度（v1 = A）**；H 的「下钻一层」是**层次导航**，不是关系跳，H **不设 hop 预算**（`hop_unit=n/a`，一次下钻 = 一层）。
- **理由**：解决 P1-3；S0-5 条款不改，本裁决明确其作用域（如未来 H 也要关系扩展，必须重开 S0/S1）。

### R-S1-3 E_relation「只增不删」必须跨版本机检
- **裁决**：冻结 `registry_history`（append-only，每条含 `version/content_sha/previous_sha`）；validator 断言：
  1. `set(active.relation_sources) ⊇ E_relation_min`；
  2. **`set(new.relation_sources) ⊇ set(old.relation_sources)`（跨版本）**；
  3. 删除/改名任何已冻结源 ⇒ `S0_REOPEN_REQUIRED`（硬失败，不得静默通过）。
- **理由**：解决 P1-2；R-1 从「文本约定」变成「可机检历史」。

### R-S1-4 H 派生边必须带 `data_edge_ids`
- 见 R-S1-1；机检 `expand_data_edges(H_vm) ⊆ DataSource.edges`，且每条 H 边可映射到 contain(structural) 数据边。

### R-S1-5 跳数/方向/终止（v1 口径）
- **A**：`hop_unit=edge`，`hop_default=1`，`hop_max=2`（v1 允许配 1..2；默认 1；2 仅在用户显式「新一跳」时使用，U-22）；沿边最短距离 + 节点去重；跨维重置为 default。
- **H**：`hop_unit=n/a`（无关系跳），一次下钻一层；终止 = KP 叶子 / 无子块 / 用户取消。
- **共同**：终止必须有穷（不得 null/∞）、确定性、截断带 `rule_id`；`max_nodes` 数值归 S8，S1 只要求字段存在与截断语义。
- **方向**：`direction ∈ {down, up, both, out, in}`；H=down；A=both（可配 out/in）；方向只影响取景，不改事实/类型。

### R-S1-6 状态机与 fallback
- 状态 `{reserved, active, deprecated}`；**deprecated→active 只允许经 S1 重开 + registry 版本升级**，不得静默复活。
- agent fallback：允许**显式** fallback 到默认 H（带审计字段 `fallback_reason`），不得静默；registry 可配置禁止 fallback（fail-closed）。
- 插件不得注册/激活/改写维度（registry 是产品配置，不是插件能力面）。

### R-S1-7 候选维度与归属
- 候选维度只登记 reserved：`time/evidence/task/controversy/authorship/similarity/path`（一句话定义 + 草案 + why_not_v1）；
- `density` 属 S2 簇算法参数，**不是维度**；`similarity` 若作为派生关系源，必须先走 S1-6 分类（derived 不得进 active）；
- v1 不晋升任何 reserved。

### R-S1-8 并集项（B 吸收 A / A 吸收 B）
- B 必须吸收 A 的：`hop_unit`、`registry_sha`、v1 active 集合固定、H 定义细节、状态机三态映射；
- A 必须吸收 B 的：`registry_history` 历史只增断言、H 的 `data_edge_ids`（R-S1-4）、候选维度覆盖；
- 双方统一：deprecated 规则、agent fallback、`DIM_COMBINATION_UNSUPPORTED` 与切换语义。

## 2. 修订轮任务（A/B 各自独立改，不覆盖旧版）

**A 修订（A-v2）**：落实 R-S1-1（H relation_sources=[]、R-1 只约束 A）、R-S1-2（H 无 hop）、R-S1-3（历史机检）、R-S1-4（H data_edge_ids）、R-S1-5（hop 口径）、R-S1-6（状态机/fallback）、R-S1-8（吸收 B）；产出 `S1-dimensions-proposal-A-v2.md` + 变更表。

**B 修订（B-v2）**：落实 R-S1-3/4/5/6/7/8 + 吸收 A 的注册表字段与状态机；产出 `S1-dimensions-proposal-B-v2.md` + `S1-objections-v2.md`。

**SE 工程校核（task-297）**：等 A-v2/B-v2 齐后执行；检查维度注册表/状态机/DFD 增量、R-S1 规则可工程化、与 S0 一致；产 `S1-engineering-check.md`。

## 3. S1 冻结门禁（同章程 §7）

1. A-v2/B-v2 关闭全部 R-S1 与 P1（逐条证据）；2. SE 工程校核 PASS；3. Lead 独立机检（注册表字段、跨版本只增、H/A 分工、hop/方向/终止、VM 纯度、覆盖矩阵）；4. 与 S0 无冲突；5. 冻结 `S1-dimensions-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0 冻结稿；S1 冻结前不开工实现；所有修订保留旧版（版本化）。
