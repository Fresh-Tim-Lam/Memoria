# S4 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S4-RULINGS.md`（sha `efa597aa…`，R-S4-1..R-S4-8）。
> **对象**：`S4-render-proposal-A-v2.md`（主办研究，sha **`634cb9cf064dc657e0f7eaa572f46bb5397b7dc18626be34f70c9fde688af2d2`**，28,942 B）与 `S4-render-proposal-B-v2.md`（本复核方，sha **`048b9909dd4cd25b6111af19c7b170eb1cd7775f6740d5988b9be80d333d3117`**，19,304 B）。
> **性质**：B-v2 以 S4-RULINGS 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S4-RULINGS/S0/S1/S2/S3。

---

## 0. R-S4 关闭矩阵

| 裁决 | A-v2 落位 | B-v2 落位 | 判定 |
|---|---|---|---|
| R-S4-1 F={focus} | S4-3：F={focus}；机检 base(F)=={focus} | S4-3：F={focus} | **关闭** |
| R-S4-2 无隐式 2 跳 | S4-2/S4-3：tier2 仅基座+H 同层；max_hop≤hop_budget；2 跳仅 S5 | 同 | **关闭** |
| R-S4-3 MANDATORY/降级 | S4-2：H `focus+first K children(cap=20)`；A `{focus}`；仅 MANDATORY 超预算失败；S8 保证 | S4-2：`focus+current-level cluster`（cap=2）；仅 MANDATORY 超预算失败；S8 保证 | **基本关闭**；两版 MANDATORY 公式/cap 不同（P1-3） |
| R-S4-4 VM 候选载体 | S4-1/S4-9：全部候选节点/边 + presence/rule_id；**明确 S3 节点白名单需 S6a 扩展**，给出 fallback | S4-1/S4-9：全部候选节点/边 + presence/rule_id；**未提 S3 节点白名单兼容问题** | **部分关闭**：R-S4-4 与 S3-v1 节点字段冲突（P1-2）；A 有兼容方案，B 需补 |
| R-S4-5 11 类 rule_id | S4-4：11 类表；unknown 仅 8–11；unknown≠无关系 | S4-4：同 11 类/unknown 四类 | **关闭** |
| R-S4-6 排序键 | S4-2：`(tier,hop,relation_class,label_rank,canonical_id)`；class 顺序；label_rank 字符串 | 同 | **关闭** |
| R-S4-7 全展开 | S4-8：同 Admission/present；candidate_scope；subset；硬上限；**但 subset 仅断言，无保证机制** | S4-8：同；subset 断言；无保证机制 | **部分关闭**：`shown(default)⊆shown(full)` 不保证（P1-1） |
| R-S4-8 并集 | aggregate_count 不遍历 data_edge_ids；G6 字段 | 同 | **关闭** |

**结论**：R-S4-1/2/3/5/6/8 已落实；**R-S4-4 的 S3 节点兼容与 R-S4-7 的 subset 保证机制仍未闭环**（P1）；MANDATORY 公式需统一（P1-3）。

---

## 1. A-v2 / B-v2 逐项差异（S4-1..S4-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S4-1 定义/裁剪 | AdmissionResult 全部候选节点/边 + presence/rule_id；Renderer 只 shown | 同；S4 唯一裁剪 | 一致；A 更细（Result→VM 投影）。 |
| S4-2 选点 | **MANDATORY：A={focus}；H={focus}+first K children，cap=20**；tier/排序键；S8 保证 max≥cap | **MANDATORY：{focus}+current-level cluster containing focus，cap=2**；tier/排序键；S8 保证 | 核心一致；**MANDATORY 公式/cap 不同（P1-3）**；A 的 H 上下文更足但 cap 20 是否"最小"需裁；B 更小但 H 可能缺上下文。 |
| S4-3 一跳 | F={focus}；one_hop 一条边；不闭包；2 跳仅 S5 | 同 | 一致。 |
| S4-4 rule_id | 11 类；unknown 8–11；类型独立 | 同 11 类/unknown 四类 | 一致；A 具体表更完整。 |
| S4-5 背后图 | 端点只显示；S5 新 frame；2 跳仅 S5 | 同 | 一致。 |
| S4-6 维度 | frame_spec；H/A 只 presence；fail-closed | 同 | 一致。 |
| S4-7 层次 | drill 新 frame/hop reset；跨层 H 结构边；run 只读 | 同 | 一致。 |
| S4-8 全展开 | 同 Admission/present；candidate_scope；subset；硬上限；**subset 仅断言** | 同；subset 断言 | 一致；**subset 保证机制 P1-1**。 |
| S4-9 S3 契约 | VM 候选载体；Renderer shown；阈值同源；**明确 S3 节点白名单缺 node presence/rule_id，需 S6a/S3 扩展；若不允许则 fallback（AdmissionResult 保留全节点，VM 只投影 shown 节点+全候选边）** | VM 全部候选节点/边；Renderer shown；未提 S3 节点字段兼容 | **关键差异（P1-2）**：A 识别并给出兼容路径；B 直接假设 VM 可放 node presence/rule_id，与 S3-v1 白名单冲突。 |
| S4-10 S5 边界 | S4 纯取景；nav/focus 不进 VM | 同 | 一致。 |
| S4-11 S1/S2 | presence 不改事实；A 不改簇；run 不进 VM | 同 | 一致。 |
| S4-12 度量/G6 | 候选/必选/显示计数、rule_id 直方图、max_hop、closure/behind、deterministic sha、subset_ok | 同核心；指标略简 | 一致；A 更细。 |

**总判断**：两版在 R-S4 核心上已收敛；A 在 S3 兼容说明/MANDATORY H 上下文/指标细节上更完整；B 在 MANDATORY 小集合/VM 严格性上更保守。**subset 保证与 node presence 扩展是最后两个 P1**。

---

## 2. 仍需解决的 3 点（建议 Lead/SE 冻结前裁）

### 2-1（P1）`shown(default) ⊆ shown(full)` 只有断言，没有选点保证机制

- **现状**：A-v2/B-v2 的 S4-8 都写"同一 Admission/present；candidate 超集；`shown(default) ⊆ shown(full)`；机检 subset"；但两版的选择算法是"按排序键取前 max_nodes"。**候选超集 + 同排序 + 同一预算不保证 subset**：full 若新增高优先级候选（焦点/一跳/关系类更靠前），会占据 full 的前 K 名额，把 default 的某个已选节点挤出；subset 断言会 FAIL，除非 full 预算更大且额外名额不改变前缀，或显式保留 default 选择集。
- **反例**：default 候选排序 A,B,C，max_nodes=2 ⇒ shown A,B；full candidate 增加 X（排序在 A 前）⇒ full shown X,A ⇒ B 不在 full；`shown(default)⊆shown(full)` FAIL。A/B 的机检无法自动通过，需改选择机制。
- **修复**（任选，推荐 a）：
  (a) full **保留 default 的 shown 集合为 reserved/mandatory**（`full.MANDATORY ⊇ shown(default)`），再按排序键填剩余名额；budget_full ≥ budget_default；subset 恒成立；
  (b) full 选择采用"default 前缀 + 新增候选只追加"的稳定排序（定义 default 元素优先级高于新增），并机检无挤出；
  (c) 只允许 full 与 default 预算相同且候选超集，并为 full 新候选分配独立追加名额。
  机检：`assert shown(default) <= shown(full)` 由构造保证，不只是断言；G6 记录 subset 构造方式。
- **证据**：R-S4-7；A-v2 S4-8；B-v2 S4-8。

### 2-2（P1）R-S4-4「VM 全部候选节点 + presence/rule_id」与 S3-v1 节点白名单冲突

- **现状**：R-S4-4 要求 VM 携带**全部候选节点/边**及逐条 presence/rule_id；S3-v1 S3-12 节点白名单为 `id/kind/label/role/member_count?/aggregate_count?/representative?/root_exempt?/...`，**未含 node presence/rule_id**；S3-5 的 presence/rule_id 是针对边。A-v2 已明确此冲突并提出两种路径：① S6a/S3 扩展节点字段；② 若严格不改 S3，AdmissionResult 保留全部节点决策，VM 只投影 shown 节点 + 全候选边（最小冲突）。**B-v2 直接假设 VM 放 node presence/rule_id，未处理 S3 兼容**。
- **反例**：按 R-S4-4 输出 node presence/rule_id 到 VM ⇒ S3 schema 校验 FAIL（未知字段）；按 S3 白名单去掉 ⇒ 无法解释节点为什么被抑制（unknown/suppressed 不可审计）。
- **修复**：Lead/SE 冻结兼容路径：推荐 **S4 输出 `AdmissionResult`（全候选节点+presence/rule_id）作为 S4→S6a 接口；VM 按 S3 白名单投影：节点只 shown，边全候选（含 presence/rule_id）；节点决策保存在 AdmissionResult/G6 审计**；或在 S6a 正式扩展 S3 节点字段（需 S3 修订/Lead 批）。无论哪种，S4 冻结稿必须写明，不可默认 VM 可放未冻结字段。
- **证据**：R-S4-4；S3-v1 S3-12 白名单；A-v2 S4-9；B-v2 S4-9。

### 2-3（P1）MANDATORY 公式/cap 两版不同：A H=focus+first 20 children，B=focus+current-level cluster（cap=2）

- **现状**：R-S4-3 要求 `MANDATORY = {focus} ∪ 必要显示上下文（公式显式、数量有上限）`，S8 保证 `max_nodes ≥ |MANDATORY|`。A-v2 的 H 取 focus+first K children，`cap=20`；B-v2 取 focus+current-level cluster containing focus，`cap=2`。两者都显式，但默认 H 视图的必选内容差异巨大：A 保证 20 个子块始终显示（可能挤掉其他内容/让 max_nodes 小配置失败）；B 只保证焦点+簇，H 下钻后 children 可能被预算抑制（不满足"层次下钻后应看到子块"的默认体验）。
- **反例**：H 焦点有 30 children：A 必选 21，max_nodes=20 ⇒ S4_BUDGET_INVALID（S8 若未按 A cap 保证）；B 必选 2，max_nodes=20 ⇒ 只显示 2 必选+其他优先，可能不显示 children，用户下钻后看不到子层。
- **修复**：冻结统一 MANDATORY 公式：推荐 **A 维度 `{focus}`；H 维度 `{focus} ∪ first K children`，K 取小常数（如 2/4，S8 可调）**；`MANDATORY_CONTEXT_CAP` 作为 S8 字段，`max_nodes ≥ 1+CAP` 上界；A/B 统一公式/常数，并在 S4-2 机检 MANDATORY 可枚举/≤cap。若 Lead 认为 20 过大，改小常数；若认为 H 需要更多上下文，改 A 公式并同步 S8。
- **证据**：R-S4-3；A-v2 S4-2（CAP=20）；B-v2 S4-2（cap=2）。

> 另：A-v2 的 `S4-9` 已自列 S3 节点字段扩展；B 需吸收。A/B 的 G6 字段（rule_id 直方图/closure/behind/subset）基本一致，可合并（P2-4）。A 的 MANDATORY H children cap 20 与 `max_nodes` 默认 200 兼容，但 S8 必须保证；B 的 cap=2 更"最小"但与 H 下钻体验需验证（P2-3）。

---

## 3. 点名审查结论（v2）

1. **S4 唯一裁剪者/Renderer 不裁剪**：A/B **PASS**（S4=Admission；Renderer 只渲染 shown；S3 R-S3-2）。
2. **选点/tie-break/显式降级**：A/B 都有 MANDATORY/排序键/suppressed；**MANDATORY 公式/cap 差异 P1-3**；subset 机制 P1-1。
3. **一跳严格一条边/不闭包/不带背后图**：A/B **PASS**（F={focus}；tier2 不含一跳邻居；max_hop≤hop_budget；2 跳仅 S5）。
4. **presence 三值/rule_id/unknown vs suppressed/类型存在性**：A/B **PASS**（11 类；unknown 四类；unknown≠无关系；类型独立）；**VM node presence 与 S3 字段冲突 P1-2**。
5. **维度只改 presence/不改事实/drill 重置**：A/B **PASS**（frame_spec；H/A 只 presence；drill 新 frame/hop reset；run 只读）。
6. **全展开同源/子集**：A/B **PASS**（同 Admission/present；candidate_scope；subset 断言）；**subset 保证机制 P1-1**。
7. **S5 边界（focus/selection/nav 不进 VM）**：A/B **PASS**（S4 纯取景；事件→S5；new_hop 仅 S5）。
8. **S1/S2（A 不改簇/多归属/run 不进 VM）**：A/B **PASS**。
9. **度量/G6 可复跑**：A/B **PASS**（deterministic sha、presence/rule_id 计数、hop/closure/behind/subset）；A 指标更细。

---

## 4. 结论

- **S4 两版均无 P0**；R-S4-1/2/3/5/6/8 已落实；**R-S4-4 与 R-S4-7 仍需兼容/保证机制**（P1-1/P1-2）；MANDATORY 公式需统一（P1-3）。
- **A-v2 在 S3 兼容说明/MANDATORY H 上下文/指标上更完整；B-v2 在 focus 一跳/VM 严格性/小 MANDATORY 上更保守。**
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S4 `S4-RULINGS.md:17-50`；S0-5/6 `S0-terms-v1.md:49-61`；S1 A `S1-dimensions-v1.md:63-67`；S3-12 `S3-visual-v1.md:71-75`；A-v2 S4-2/S4-8/S4-9；B-v2 S4-2/S4-8/S4-9。
