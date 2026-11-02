# S0 术语提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S0-RULINGS.md`（含 D-1..D-5）；最高原话 `multilevel-graph-vision.md`（U-1..U-35）。
> **输入**：B v1（sha `48e29f3d…`）、A v1（sha `0fddb4c6…`）、`S0-objections.md`；A-v2 写作时尚未落盘，本文件先独立完成（完成后才对照 A-v2，见 `S0-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码（file:line）；B=冻结数据/实测；C=契约/文档推断；PI=本项目假设（RULINGS 已裁决的项标注为 **R**）。
> **日期**：2026-11-02（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 RULINGS）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S0-1 | 字段判据（type/provenance/contain_kind） | 并集 A 的 **T1 可命名 / T2 可真假 / T4 非偶然** + B 字段闸门；**T3 降级**为消费者准入清单（R S0-1、P1-3） | 并集/降级 |
| 2 | S0-2 | Level 粒度轴；未要求 partition | **partition 限定「同一 (level, 视图族)」**；补**机检伪代码**（叶子 kind=kp、叶子 id⊆K、无 cluster 叶子、cluster 展开到底全 KP、同族互斥/跨族允许重叠、fail-closed）（R P1-1/D-1） | 新增 |
| 3 | S0-3 | relation_dimension 关系源（已含 U-10） | 明确 `edge_selector = E_relation(D)`；开放槽位模板 + **reserved 不得进渲染分支**；**v1 单维度激活**（R S0-3/D-5） | 强化 |
| 4 | S0-4 | cluster_id=stable_hash(members...) | 改 **D-2**：`cluster_run_id + local_seq` 为实例 id；`cluster_key = sha256(sorted(member_canonical_ids)+algorithm_id+version+params_hash)` 为可复算键；并集 A 的 **μ/β**；partition 限定视图族（R P1-4/D-2） | 修正/并集 |
| 5 | S0-5 | E_relation(D)（R1 已修）；无方向契约 | 补 **`dir(D)` 方向定义** + **跨维重置**；保持 E_relation(D) 覆盖 U-10（R S0-5） | 新增 |
| 6 | S0-6 | present(e,ctx) 布尔 + suppression | 并集 A 的**边状态枚举**；落 SE 的 **`presence ∈ {shown,suppressed,unknown}` + `ctx` + `rule_id`**；全展开也走 `present(e,ctx_full)`（R S0-6/P1-2） | 并集/强化 |
| 7 | S0-7 | membership 多对多；无单 parent | 保留多对多；**删除层内全局单归属**，改「同一视图族内单归属、跨视图族/维度多归属」；Role/provenance 并集 A；**D-3 不写产品 sidecar/新段**（R S0-7/D-3） | 修正 |
| 8 | S0-8 | 同 DataSource/Renderer；参数退化 | 补 **焦点保持/映射**（并集 A）；full_expand 走 `present(e,ctx_full)` 且**不得第二数据源**；模式是 Presentation toggle（R S0-8/P1-2） | 并集 |
| 9 | S0-9 | ViewModel kind{kp,cluster}；事件 5 种 | 补 **capabilities + 完整事件清单**（并集 A）；**D-4**：ViewModel 不含导航状态/模式开关；kind 固定 {kp,cluster}；bridge 仅 role/state（R S0-9/D-4/P0-2） | 并集/修正 |
| 10 | S0-10 | 三层边界 | 并集 A 的三角色表（KP 设计/语义 curation/取景）+ **确定性取景服务**；agent 不得直接改渲染状态（R S0-10） | 并集 |
| 11 | S0-11 | 12 条 | 并集 A 13 条 + B 的「不把 cluster/membership 写产品 sidecar」「不新增产品拓扑段」等约 15 条，每条绑执行点（R S0-11） | 并集 |
| 12 | S0-12 | 12 行映射 | 并集 A 的旧术语覆盖 + B 的 **DataSource→ViewModel→Renderer 三段**、present/semantic_edges 映射；冲突处迁移/回滚（R S0-12） | 并集 |

> 所有 RULINGS 判为「成立」的 P0-1/P0-2/P1-1..P1-4 均在 B-v2 对应章节落位；无静默合并——A-v2 对照差异与我的独立判断见 `S0-objections-v2.md`。

---

## 0.1 覆盖矩阵（U 编号 → B-v2 落点；S0 相关全部出现）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-1 | S0-1 语义定义 | U-19 | S0-5/S0-9（kind 仅 kp/cluster） |
| U-2 | S0-10 双层价值边界 | U-20 | S0-9 事件/KP→编辑器（S5 执行） |
| U-3 | S0-6/S0-8 默认视图 | U-21 | S0-2/S0-7 多归属 |
| U-4 | S0-2 层次 | U-22 | S0-5/S0-7 导航权衡（S5） |
| U-5 | S0-2/S0-8 默认非全展开 | U-23 | §0/覆盖矩阵/流程 |
| U-6 | S0-4/S0-9 簇节点 | U-24 | vision 文件（不转述） |
| U-7 | S0-4/S0-9（下钻在 S5） | U-25 | S0-3 开放槽位 |
| U-8 | S0-2/S0-3 层次维度 | U-26 | S0-8 默认替代+开关 |
| U-9 | S0-3 维度 | U-27 | S0-6 存无/类型 |
| U-10 | S0-3/S0-5 `E_relation(D)`（P0-1 修正） | U-28 | S0-2 最小粒度 |
| U-11 | S0-3/S0-5 跳数 | U-29 | S0-10（细谈 S10） |
| U-12 | S0-3 开放槽位 | U-30 | S0-3（细谈 S1/S4） |
| U-13 | S0-4 簇定义 | U-31 | S0-7 多归属上限 |
| U-14 | S0-4 语义小群 | U-32 | S0-6/S0-10（检索 S9） |
| U-15 | S0-5 一跳 | U-33 | S0-9 单一渲染接口 |
| U-16 | S0-6 选择性渲染 | U-34 | 本文件逐项结构 |
| U-17 | S0-5/S0-6 背后图边界 | U-35 | S0-9/S0-10 接口预留（S5a/S6a/S9a） |
| U-18 | S0-5 不闭包/预算 | | |

---

## S0-1 「语义」（并集 T1/T2/T4 + 字段闸门；T3 降级）

**定义**：图谱语境下，"语义"= **一条能被指认、可判真假、且非布局/投影偶然产生的关系断言**；边上的 `semantic / structural / navigation` 是**标签**，不是视觉现象。

**形式化**：
```
semantic_edge(e) ⇔ T1(e) ∧ T2(e) ∧ T4(e)
T1 可命名：存在谓词 P（来自受控词表：contain / extend / reference 的既有语义命名），e=(P,a,b)
T2 可真假：存在可读证据（assertion_source：file/line_start/line_end 非空且 quote_sha256 可复算）
T4 非偶然：e 不是布局/缩放/取景/投影偶然产生（来源字段可核，见下）
字段闸门（B 原判据，R S0-1）：
  semantic edge 必须满足其一：
   (a) 作者断言型：provenance_state=asserted ∧ assertion_source 可读；
   (b) semantic contain：contain_kind=semantic ∧ **derived_by=author** ∧ assertion_source ∧ curated_by/curated_at（v0.3；validator `edge_derivation.py:812-859` 硬要求 derived_by=author，agent curation 也必须以 author 身份落 overlay）
  structural = contain_kind=structural（仅结构包含，不是 semantic）
  navigation = reference（无断言跳转）
T3（消费者准入，R/P1-3）：仅用于评测/消费白名单，不作 semantic 的必要条件；登记在 G6/S8 的消费清单，不进入本定义。
```
**反例**：range 包含（structural）不是 semantic；reference 不是 semantic；布局靠近/同文件不是 semantic；无锚点的 asserted 不是 semantic（fail-closed）。
**边界用例**：asserted + 锚点可读但无消费者 → **仍是 semantic**（T3 已降级）；锚点 stale → 降级为候选（不删边）；reference 与 semantic 同对节点共存时分别标标签；contain semantic 缺 curated_by/at → 不满足字段闸门，退回 structural/候选。
**U 映射**：U-1、U-10、U-13/U-14、U-15、U-17、U-27。
**建议裁决**：冻结 `semantic_edge = T1∧T2∧T4 + 字段闸门`；T3 只作消费准入；三段标签 semantic/structural/navigation 为 S0 唯一语义分类。
**证据等级**：A（U-1/U-17；ontology v0.3 §2.1/§2.2/§2.3；canonical schema 字段）。

---

## S0-2 层次（level）与最小粒度（补机检伪代码 + partition 作用域）

**定义**：层次是同一知识库上按**展示粒度**的取景级别；**最深一层的最小节点粒度 = 知识点（KP）**；partition 只在**同一 (level, 视图族)** 内要求（D-1），跨视图族/维度允许重叠。

**形式化**：
```
K = 该 KB 的 KP 集（canonical KP id）
Level = ⟨level_id, granularity, display_node_kind⟩；display_node_kind ∈ {cluster,kp}
ViewFamily = 同一 (level, dimension) 下的视图族（R D-1）
对每个 view_family：partition Π_{level,family} = { blocks }，块 = cluster 或单 KP
跨 view_family / 跨 level：允许同一 KP 出现在多个块（对接 S0-7 多归属）
最深 level L_max：所有展示节点 kind=kp（无 cluster、无句/词/断言节点）
```
**机检伪代码（S0 冻结前必须可执行；对 ViewModel 断言）**：
```
def check_level_partition(view_model, K, view_family):
    nodes = view_model.nodes
    errors = []
    # 1) kind 仅两类
    if any(n.kind not in {"kp","cluster"} for n in nodes):
        errors.append("non-kp/cluster kind")
    # 2) 叶子只允许 kp；kp 的 id 必须 ⊆ K（未知 id fail-closed）
    for n in nodes:
        if n.kind == "kp":
            if n.id not in K: errors.append(f"unknown kp id {n.id}")
            if n.member_count not in (None, 1): errors.append("kp member_count != 1")
    # 3) 无 cluster 叶子：cluster 必须 expandable 且展开到底全为 KP
    for n in nodes:
        if n.kind == "cluster":
            if not n.expandable: errors.append(f"cluster {n.id} not expandable")
            members = expand_cluster_to_kp(n)       # 递归展开
            if not members: errors.append(f"empty cluster {n.id}")
            if not set(members) <= K: errors.append(f"cluster member outside K {n.id}")
    # 4) 同一 (level, view_family) 内 partition：每个 KP 恰属一个块
    owners = {}
    for n in nodes:
        ids = [n.id] if n.kind == "kp" else expand_cluster_to_kp(n)
        for k in ids:
            if k in owners: errors.append(f"kp {k} in multiple blocks of same family")
            owners[k] = n.id
    if set(owners) != K:
        errors.append("partition not cover K")
    return errors   # 非空 ⇒ FAIL（fail-closed；S0 冻结门禁用）
# 跨 view_family / 跨 level：不执行同一断言（允许重叠）
```
**反例**：句子/段落作为节点（违反 U-28）；一个 cluster 展开出现非 KP（违反最小粒度）；同一视图族同一 KP 属两个块（partition 破坏）；cluster 成员 id 不在 K（错误数据）；空 cluster。
**边界用例**：单成员 cluster 允许（但若同族内也可显示为 kp，需算法决定）；最深 L_max 无 cluster；`range_ok=false` 的 KP 仍是 KP（不能因不可定位变成其他 kind）；跨视图族同一 KP 多块允许（S0-7）；无法展开的 cluster ⇒ fail-closed，不得作为叶子渲染。
**U 映射**：U-4、U-5、U-8、U-26、U-28（+U-21 多归属）。
**建议裁决**：冻结上述定义/机检伪代码/partition 作用域（同 (level, view_family)）；L_max 由 S1 定，**不得细于 KP**；fail 语义 = 冻结门禁 FAIL，不得静默降级。
**证据等级**：A（U-4/U-5/U-8/U-28；collector 节点字段可支持 kind/id 断言）+ R（D-1/P1-1）。

---

## S0-3 维度（dimension）

**定义**：维度是同一层次下改变"取哪些节点/边、沿哪些关系、几跳"的取景规则；**不是粒度，不是视觉风格，不是 2D/3D**。

**形式化**：
```
Dimension = ⟨dimension_id, status, scope_fn, edge_selector, direction, hop_policy,
             termination, priority, version, owner, activation_criteria⟩
edge_selector = E_relation(D)   # U-10：contain(structural/semantic) / reference / semantic extend 等
semantic/structural 是边的标签；不是"能否进入 E_relation"的开关
status ∈ {active, reserved}
active v1：level_dimension、relation_dimension；**同一视图只允许一个 active 维度（D-5）**
reserved：只登记；不得进渲染分支/默认取景/产品代码；组合维度留 reserved（S1 再裁）
```
**反例**：把 graphStyle（force/galaxy）当维度；把 edge.type 当维度（类型是边标签）；把 2D/3D 当维度；未登记私加时间维度；v1 同时激活两个维度（违反 D-5）。
**边界用例**：reserved 维度切换不生效（fail-closed，提示未实现）；active 维度切换重置跳数（S0-5）；维度与层次组合顺序留 S1 开放槽位；E_relation(D) 对 structural contain 也返回边（但标签 structural）。
**U 映射**：U-8、U-9、U-10、U-11、U-12、U-25、U-30。
**建议裁决**：冻结维度定义 + E_relation(D) + reserved 登记 + **v1 单维度激活**；组合留开放槽位。
**证据等级**：A（U-8..U-12/U-25/U-30；graphStyle 排除可机检）+ R（P0-1/D-5）。

---

## S0-4 簇 / 代表连通子图（μ/β + D-2 身份）

**定义**：簇是 KP 集合上**语义内聚、与外部只有零星桥**的子集；代表节点是视图层 cluster_node，不是本体实体；非严格连通分量。

**形式化（并集 A 的 μ/β）**：
```
C ⊆ K；E_sem = semantic_edge 集；E(C,K\C) = 跨边
μ(C) = |E_sem 内部边| / 可能对数（或等价归一化内聚度） ≥ τ_coh
β(C) = |E(C,K\C)| / (|E_sem(C)| + |E(C,K\C)|) ≤ τ_bridge（或桥数 ≤ b）
簇 = μ(C)≥τ_coh ∧ β(C)≤τ_bridge
（阈值 τ_coh/τ_bridge/桥数 b 由 S2 定；S0 只冻结可采纳性判据）
```
**D-2 簇身份（RULINGS 唯一口径）**：
```
cluster_run_id  = 一次聚类运行的稳定 id（corpus_manifest_sha + level_id + view_family_id
                  + algorithm_id + algorithm_version + params_hash 的稳定编码）
cluster_local_seq = 该 run 内簇的稳定局部序号（按成员 canonical id 排序后编号）
簇实例 id = (cluster_run_id, cluster_local_seq)     # 审计/curation 引用用这个（成员变也不失效）
cluster_key = sha256( sorted(member_canonical_ids) + algorithm_id + algorithm_version + params_hash )
                                                    # 可复算/去重键，不是 curation 主引用
curation/审计引用必须同时记录 (cluster_run_id, cluster_key)
```
**partition 作用域**：同 (level, 视图族) 内簇族构成 partition；跨视图族/维度允许重叠（D-1；对接 S0-7）。
**反例**：严格连通分量冒充簇（U-13）；目录分组冒充簇（现有 `MemoriaGraphGroups` 是 UnionFind 闭包，A 级证据：`graph-groups.js:80-99`）；用 reference/structural 当内聚证据；把 cluster 写产品 sidecar（D-3）；用内容哈希当 curation 主 id（成员一变引用失效，D-2 禁止）。
**边界用例**：单成员簇；桥=0（同时是连通分量，但定义不要求）；同一 KP 跨视图族多簇（S0-7）；算法版本变化 ⇒ cluster_run_id/cluster_key 变化，但旧 curation 通过 run+key 可追溯；空簇/成员越界 ⇒ fail-closed。
**U 映射**：U-6、U-7、U-13、U-14、U-15、U-19、U-21/U-31。
**建议裁决**：冻结 μ/β 可采纳性 + D-2 身份（run+seq+key）+ 视图族 partition；簇结果只存研究/缓存层（D-3），不写产品 sidecar；算法/阈值 S2。
**证据等级**：A（U-13/U-14；`graph-groups.js` UnionFind 事实）+ R（D-1/D-2/D-3/P1-4）。

---

## S0-5 一跳挂接（E_relation(D) + dir(D) + 跨维重置）

**定义**：一跳 = 从当前可见节点出发，沿**当前维度 `E_relation(D)`** 的边、按 `dir(D)` 方向、**恰好走 1 条**边到达的节点；挂接集合 = 尚未可见的邻居（KP 或 cluster），不递归、不闭包、不带背后图（U-17）。

**形式化**：
```
dir(D) ∈ {out, in, both, hierarchy_down}；每维度显式声明；
  out = 只 source→target；in = 只 target→source；both = 双向；hierarchy_down = 父簇→子层（仅 H 维度）
缺省 v1 = both（无向，本项目假设，S1/S4 可改，但不得两义）；方向和 hierarchy 语义由 S1 冻结
hop1(ctx) = { n | ∃ e ∈ E_relation(D) ∩ E_selected :
              (e.source∈visible ∧ n=e.target ∧ direction_ok(e, dir(D)))
              ∨ (e.target∈visible ∧ n=e.source ∧ direction_ok(e, dir(D), reverse)) }
attach_set = hop1 \ visible          # canonical id 去重
每条挂接边带 label ∈ {semantic, structural, navigation}；label 不影响能否挂接（U-10）
跨维度：切换 active 维度 ⇒ 跳数计数重置为 0/1，重新从新维度基座开始；不得跨维度累加跳数
cluster_node：以桥边聚合一跳；簇内成员边不计一跳（S4 细化聚合）
```
**反例**：展示 2 跳/闭包（U-18）；只走 semantic 边、排除 reference/structural（违背 U-10，P0-1 修正）；跨维度累加跳数；把已在视图内节点重复挂接；不带 dir 导致同一实现两种方向都合规。
**边界用例**：同一对节点多条不同类型边仍算一跳，显示类型由维度/S0-6 决定；一跳节点属于别的簇/层 → 只显示该节点 + "进入其所在子图"入口（U-17/U-21）；reference/structural 邻居可挂接（标 navigation/structural）；semantic 候选无锚点不挂接（只提示待补证据）；`dir(D)=forward` 时反向边不挂接。
**U 映射**：U-10、U-11、U-15、U-17、U-18、U-19、U-20、U-21、U-22。
**建议裁决**：冻结「E_relation(D) + dir(D) + 恰好 1 条 + 去重 + 不递归 + 跨维重置 + 背后图不带入」；dir 缺省无向、按维度声明；具体预算 S4/S1。
**证据等级**：A（U-10/U-11/U-15/U-17/U-18；R P0-1）+ R（S0-5）。

---

## S0-6 选择性渲染 + 边「存无/类型」（presence 三值 + 边状态枚举）

**定义**：渲染集合由（level, dimension, 视图族, 焦点, 预算, 语义条件）计算；**边在视图中的「存在」是上下文函数**（U-27），不是 `edges[]` 里有就画；视图缺席 ≠ 数据缺席。

**形式化（并集 A 状态枚举 + B present 唯一判据 + SE ctx/presence）**：
```
ctx = ⟨level_id, dimension_id, view_family_id, focus_id, hop_budget, mode=default|full_expand⟩
presence(e, ctx) ∈ {shown, suppressed, unknown}
  shown:    endpoints∈V_selected ∧ e∈E_relation(D) ∧ type_allowed(D) ∧ hop(e,ctx)≤budget ∧ rule_id=OK
  suppressed: 被折叠/层级/维度/预算/显式过滤 ⇒ 必须给 rule_id（可枚举）
  unknown: 未计算/不可判定（不得当 absent）
边状态枚举（A 并集，映射到 presence+rule_id）：
  full / bridge_only → shown(rule_id=full/bridge)
  folded / hidden_by_level / hidden_by_dim / hidden_by_budget / hidden_by_filter → suppressed(rule_id=...)
  unknown → unknown
full_expand：ctx.mode=full_expand，仍调用同一 presence(e,ctx_full)；
             允许 shown 覆盖全部数据边，但每条边带 label(semantic/structural/navigation)，
             不得绕过 present、不得第二数据源、不得改变类型读法
类型映射 τ_view(e) = (base type, contain_kind, label)；structural contain ≠ semantic contain；reference 不得显示为 contain/extend
```
**机检**：`foreach e in ViewModel.edges: presence(e,ctx) != suppressed 或 rule_id ∈ 枚举`；`unknown` 必须有标记；full_expand 的 edges ⊆ all_data_edges 且 labels 完整；无 `data-has-edge ⇒ shown` 路径（断言 select 函数唯一入口）。
**反例**：旧行为 `graph-engine.js:88-110 expandLinks` 对每条 edge 的每个 target 无条件画（A 级旧行为证据）；视图缺席断言数据无关系；structural 显示为整体-部分；full_expand 走独立数据路径或改变类型；suppressed 无 reason（静默丢）。
**边界用例**：多类型边按维度优先级显示 + 其他类型徽标/计数；budget=0 无边；full_expand 下 reference 也 shown 但 label=navigation；unknown 在 UI 上必须与 absent 区分；折叠簇的边只计数/提示，不产生 edgeClick。
**U 映射**：U-3、U-16、U-17、U-26、U-27（+U-18 预算理由）。
**建议裁决**：冻结 presence 三值 + rule_id + 边状态枚举映射 + `present` 唯一入口；full_expand 也走 present；视图缺席不得推出数据缺席；类型标签与本体 type 不可改写。
**证据等级**：A（U-16/U-17/U-26/U-27；旧 expandLinks 行为）+ R（S0-6/P1-2）。

---

## S0-7 多归属（membership vs view appearance）

**定义**：「属于」= 成员关系（KP 与簇/层/视图族之间，可多对多）；「视图出现」= 某 ctx 下的可见性；二者互不蕴含（U-21）。

**形式化**：
```
membership ⊆ K × Container × Role × Provenance   # Container ∈ {cluster, level, view_family}
membership 多对多；无单值 parent；同一视图族内 partition（S0-2），跨视图族/维度允许重叠（D-1）
view_visible(kp, ctx) 由 Select 计算，含 reason ∈ {member, one_hop, bridge, focus}
M ⇏ A；A ⇏ M
Role/provenance：author / algorithm / agent；持久化/上限留 S2/S6（S0 不设上限，U-31）
D-3：membership/cluster 不写产品 sidecar、不新增产品段；研究/缓存层；semantic 边 curation overlay 仍走 v0.3
```
**反例**：用单值 parent/`nodeToGroup` 表达语义归属（现有 `graph-groups.js` 单值 nodeToGroup 是目录分组，不是 membership；A 级冲突）；把视图出现当成员写回；一跳节点登记为成员；把文件归属当语义归属；把 membership 写产品 sidecar（D-3）。
**边界用例**：同层不同视图族多簇允许；same family 内 partition（S0-2）；KP 属于簇但当前不可见；不同层次/维度多归属；membership 可持久/可复算但必须带 provenance；上限不设。
**U 映射**：U-21、U-22、U-31、U-19/U-20。
**建议裁决**：冻结"membership 多对多 vs 视图出现二分 + 同视图族 partition/跨族重叠 + Role/provenance + D-3 不写产品"；上限/存储 S2/S6。
**证据等级**：A（U-21/U-31；`graph-groups.js` nodeToGroup 单值可核）+ R（S0-7/D-1/D-3）。

---

## S0-8 默认视图 vs 全展开（焦点映射 + present 化）

**定义**：默认入口=新的多层次选择性渲染（彻底替代旧全展开，U-26）；全展开=同一数据源/同一 ViewModel 构建/同一渲染接口下，`ctx.mode=full_expand` 的兼容视图；不是第二主线/第二真相。

**形式化**：
```
DataSource = collect_graph_data(kb)             # 唯一事实源；不得第二数据源
buildViewModel(DataSource, ctx)                 # 唯一构建入口（默认/全展开同函数）
子集断言（在"数据边投影"上做，避免聚合边伪造包含关系）：
  expand_data_edges(VM) = ⋃ { e.data_edge_ids if e 是聚合边 else {e.id} }
  expand_data_edges(VM_default) ⊆ expand_data_edges(VM_full) ⊆ DataSource.edge_ids
  # 聚合/折叠边必须带 data_edge_ids（S0-9 ViewModel），否则视为非法（fail-closed）
默认 D0：ctx=⟨level0, active_dim, view_family, focus, budget=B0, mode=default⟩
全展开 F：ctx=⟨L_max, active_dim, view_family, focus, budget=∞ 或全量, mode=full_expand⟩，
          仍走 presence(e,ctx_full)，每条边带 label，不得 all_data_edges 直接注入
焦点保持/映射（并集 A）：
  切换 mode 时若 focus 节点在当前 ctx 可见 ⇒ 保持；
  若 focus 被折叠进 cluster ⇒ 映射到包含它的最近 cluster/根，并记录提示（S5 呈现）；
  若无法映射 ⇒ 回到当前 level 根，记录 reason（S5）
禁止：第二数据源/第二 ViewModel 构建器/第二渲染器；全展开改类型读法
```
**反例**：双入口/默认仍全展开；全展开直接 `all_data_edges` 绕过 present；全展开独立数据路径；切换静默丢焦点；默认视图仍渲染全部数据边。
**边界用例**：最小层默认与全展开在焦点范围收敛（允许；但边仍需 label，不得把 reference 当 semantic）；全展开规模问题归 S9/S8；模式切换是 Presentation 层 toggle（D-4：ViewModel 不含 mode）；无簇时默认退化为 KP 图但仍同一入口。
**U 映射**：U-3、U-5、U-26、U-27、U-32。
**建议裁决**：冻结"默认唯一入口 + 全展开同源同构建同 present + 焦点映射 + 禁第二数据源"；切换细节 S5。
**证据等级**：A（U-26/U-32；现有单数据路径事实）+ R（S0-8/P1-2/D-4）。

---

## S0-9 渲染接口边界（kind 约束 + capabilities/事件；D-4 纯度）

**定义**：渲染接口 = 纯数据 ViewModel + 2D/3D 同签名后端 + 渲染事件；**ViewModel 不含导航状态与模式开关**（D-4）；渲染器不取数、不做语义判断；`kind ∈ {kp, cluster}`，bridge 只是 role/state。

**形式化（并集 A 字段 + B kind 约束）**：
```
ViewModel（纯数据；无 mode/focus/breadcrumb/历史；**不含后端能力字段**）：
  { view_model_id, level_id, dimension_id, view_family_id,
    nodes: [{id, kind ∈ {kp,cluster}, label, member_count?, role? ∈ {member,one_hop,focus},
             state? ∈ {bridge,...}, expandable}],
    edges: [{id, source, target, base_type, contain_kind?, label ∈ {semantic,structural,navigation},
             presence ∈ {shown,suppressed,unknown}, rule_id?, display_type,
             data_edge_ids?: [edge_id]}   # 聚合/折叠边必须列出其代表的数据边 id 集合
  }
Renderer（2D/3D 同签名）：
  mount(root, viewModel) / update(viewModel, {transition?}) / destroy()
  getCapabilities() -> {labels, zoom_hint, ...}   # 后端能力，来自 Renderer，不属于 ViewModel
  on(event, handler)
事件（渲染器→上层；最小集；导航/模式事件归 S5/Presentation，不进本契约）：
  nodeClick {node_id, kind}          # kind∈{kp,cluster}；S5 决定跳编辑器/下钻
  edgeClick {edge_id}
  hover {node_id?|edge_id?}
  clusterExpand {node_id}            # 请求下钻（S5 决定状态迁移）
禁止：modeToggle/navigateBack/breadcrumbClick 进渲染器契约；渲染器调用 get_graph_data/读 sidecar；
      渲染器自己决定 semantic_edges/present；事件携带正文/用户输入/DOM 引用
2D/3D：同一 ViewModel、同一事件 id 集；差异只允许 Renderer.getCapabilities() 返回的后端能力
```
**反例**：`kind: kp|cluster|bridge`（A v1 的 P0-2，已修）；把 modeToggle/navigateBack 放渲染器事件；2D 有 edge_id、3D 无（A 级现存事实 `graph-view-2d.js:544-547` vs `graph-view-3d.js:1042-1044`）；渲染器直接取数；事件传整对象。
**边界用例**：3D 暂缺；3D 能力差异用 `Renderer.getCapabilities()` 声明，不改 ViewModel/事件 id；折叠边不产生 edgeClick；switch mode 由 Presentation/S5 调用 `update(viewModel)`，ViewModel 内无 mode；cluster 节点点击由 S5 决定下钻。
**U 映射**：U-6、U-7、U-19、U-20、U-26、U-33（+U-35 工程图）。
**建议裁决**：冻结 ViewModel 纯数据字段 + kind 约束 + 事件清单 + 2D/3D 同签名 + 禁取数/禁语义判断/禁导航事件；S3/S5/S6 细化视觉/状态/数据契约。
**证据等级**：A（U-19/U-33；现有 2D/3D 代码事实）+ R（S0-9/D-4/P0-2）。

---

## S0-10 agent 的角色边界

**定义**：agent 在 KP 设计层主导；语义层可写但必须带证据+审计；取景层可设计/调用**确定性取景服务**，不得进入渲染/视觉实现；三层之间不越权。

**形式化**：
```
L_kp   ：agent 主导 KP 设计（产生/边界/命名/粒度/去重/多归属）+ 人监督/审计（S10，U-29）
L_sem  ：agent 可 curate_contain(semantic)，必须 assertion_source + curated_by/curated_at（v0.3）；
         structural 由系统派生；agent 不得自动推断 semantic（v0.2 §2.3 规则 3）
L_view ：agent 可设计/调用检索与取景服务（S9/U-32），输出只能是 ctx/候选参数；
         最终 ViewModel 由确定性 buildViewModel(DataSource, ctx) 生成；agent 不得直接改渲染状态/DOM
人      ：KP 政策审批、semantic 抽查/撤销、产品决策
系统    ：structural 派生、类型归一化、schema/G6 机检
```
**反例**：agent 几何 contain 自动标 semantic；agent 直接改渲染集合/DOM/view state；把取景结果当语义证据；KP 拆分/合并无审计；agent 绕过 presence 直接渲染。
**边界用例**：agent 提 KP 修改先提案后落库（S10）；agent curation 带锚点与审计，人可撤销；agent 的取景参数被预算截断（S9）不得越权；agent 离线→确定性基线（S9 退化）。
**U 映射**：U-2、U-29、U-32、U-35。
**建议裁决**：冻结三层边界 + 确定性取景服务 + agent 不得直接改渲染状态；机制 S7/S9/S10。
**证据等级**：A（U-29/U-32；v0.3 §2.3；ontology §1）+ R（S0-10）。

---

## S0-11 不做什么（v1 并集清单，每条绑执行点）

**定义**：v1 不做=不实现、不进产品契约/默认视图；解除范围须新章程+人批（U-23）。

| # | v1 不做 | 依据 | 执行点（机检/评审点） |
|---|---|---|---|
| 1 | 词级/句级/概念级节点（低于 KP） | U-28 | S0-2 机检：叶子 kind=kp |
| 2 | 自动改写用户正文 | AGENTS.md 单一事实源/U-29 | propose_write 审计 |
| 3 | 自动推断 semantic contain | v0.2 §2.3 规则 3 | schema/collector fail-closed |
| 4 | 新增语义边类型（prerequisite 等） | ontology v0 §4 | 边类型枚举/准入三闸 |
| 5 | 跨库图（v1 单 KB） | 无原话/证据需求 | 数据模型 KB 边界 |
| 6 | 时间轴维度（留 reserved） | U-25 | S0-3 槽位登记 |
| 7 | 2D/3D 双设计线/双入口 | U-33 | S0-9 ViewModel/事件契约测试 |
| 8 | 全展开作为默认/第二主线 | U-26 | S0-8 单入口/同 present 断言 |
| 9 | 渲染器直接取数/读 KB | S0-9/D-4 | 接口审计（renderer 无 get_graph_data） |
| 10 | 把视图出现持久化为成员关系 | S0-7 | membership/view 断言 |
| 11 | 无审计批量 semantic curation | v0.3 | curated_by/at 必填 |
| 12 | 把 cluster/membership 写产品 sidecar 或新增产品段 | D-3 | sidecar schema 禁止键/无新段 |
| 13 | 复用现有 graph-groups（UnionFind 闭包）当语义簇 | S0-4 | cluster 定义/算法评审 |
| 14 | 在 S0 冻结簇/检索算法与性能阈值 | 章程 §2 | S2/S8/S9 |
| 15 | 将导航状态/模式开关放进 ViewModel | D-4 | S0-9 ViewModel 字段机检 |
| 16 | v1 同时激活多个维度 | D-5 | S0-3 active 维度数=1 断言 |

**反例/边界**：越界=重开章程；2D/3D 可只实现 2D 后端但不得拆线；"不做"≠永久禁止。
**U 映射**：U-23、U-25、U-26、U-28、U-33。
**建议裁决**：冻结 16 条；每条执行点进 S0 冻结门禁（无执行点的条目不得冻结）。
**证据等级**：A（ontology/AGENTS 约束）+ R（S0-11/D-3/D-4/D-5）。

---

## S0-12 术语映射（新 ↔ 现有；并集 A 覆盖 + B 三段）

**定义**：新术语到现有产品术语/字段/代码的显式函数，关系 ∈ {same, extends, conflicts, none}；冲突必须有兼容/迁移/回滚。

| 新术语 | 现有术语/实现 | 关系 | 冲突/迁移/回滚 |
|---|---|---|---|
| KP | `knowledge_points[]`/`node.id`/`kp_id` | same | 不变 |
| semantic edge | `edges[]` + `type/contain_kind/provenance_state/assertion_source/curated_*` | extends/筛选 | 旧 `edges[]` 含 reference/structural；消费者按 S0-1 过滤 |
| structural contain | `contain_kind=structural` | same | 不得显示成整体-部分 |
| semantic contain | `contain_kind=semantic` + v0.3 curation | same | 缺证据 fail-closed |
| level / dimension | 无；旧全展开=单层 KP 图 | none（新） | 默认入口替换；全展开=兼容开关 |
| cluster | `graph-groups.js` groups（UnionFind 闭包） | **conflicts** | 不得复用；新 `semantic_cluster`；D-3 不写产品 |
| 代表节点 | 无（现有全是 KP） | none | ViewModel kind=cluster；点击需 S5 映射 |
| 一跳挂接 | 旧 ego-only/0.5 范围 | extends | 新=预算/维度/防背后图 |
| 选择性渲染 | 旧 `loadPayload`+`expandLinks` 全量 | **conflicts** | 新=Select+present；旧行为只作 full_expand 兼容 |
| present / presence | 无 | none | 新研究/服务函数；S0-6 唯一判据 |
| ViewModel | `get_graph_data` payload | extends | 三段：DataSource→ViewModel→Renderer；payload 不是 ViewModel |
| renderer（2D/3D） | `graph-view-2d.js`/`graph-view-3d.js` | same/extends | 同接口后端；事件 id 统一 |
| membership | 无（sidecar 文件归属是存储） | none | 多对多；D-3 不写产品 |
| 多归属 | 现 KP 只在所属文件 | none | 跨层/维/视图族；存储 S6 |
| 全展开 | 旧默认 force 全量 | conflicts | 默认被替代；保留开关 |
| curation | `contain_kind`+`curated_by/at` | same | 仅 semantic；审计 |
| 视图出现 | 旧 payload 全渲染 | conflicts | 新=Select+reason；≠成员 |
| DataSource | `collect_graph_data(kb)` | same | 唯一事实源；禁止第二数据源 |

**标红冲突**：cluster vs graph-groups；选择性渲染 vs expandLinks；全展开 vs 默认；视图出现 vs 成员；renderer 取数 vs ViewModel 纯数据。**迁移/回滚**：数据层 v1 不改 sidecar；渲染层默认入口替换可回滚（关新入口/恢复旧 load 路径，无数据迁移）；术语冲突在 S6 落地前不得按旧口径实现。
**U 映射**：U-1、U-16、U-21、U-26、U-27、U-28、U-33。
**建议裁决**：冻结映射表 + 五条红线 + 三段架构；S6 给迁移/回滚实现。
**证据等级**：A（ontology/schema/代码 file:line）+ R（S0-12）。

---

## B-v2 自检（对 RULINGS 的逐条落位）

| RULINGS 要求 | B-v2 落位 |
|---|---|
| P0-1 `E_relation(D)` | S0-1/S0-3/S0-5（全文替换；U-10 关系源） |
| P0-2 kind 约束 + bridge role/state | S0-9（kind {kp,cluster}；role/state） |
| P1-1 机检伪代码 + partition 作用域 | S0-2（四断+expand+fail；同 (level,视图族)） |
| P1-2 full_expand 走 present | S0-6/S0-8（ctx_full + present；无 all_data_edges） |
| P1-3 T3 降级 | S0-1（消费准入，不作定义） |
| P1-4 / D-2 cluster 身份 | S0-4（run_id+seq+key；禁内容哈希主引用） |
| S0-6 ctx/presence/rule_id | S0-6（三值+枚举映射） |
| D-4 ViewModel 纯度 | S0-9（无 mode/focus/breadcrumb；导航事件归 S5） |
| D-5 单维度激活 | S0-3（v1 单 active 维度） |
| D-3 不写产品 sidecar/新段 | S0-4/S0-7/S0-11 #12 |
| μ/β、边状态枚举、术语映射、T1/T2/T4 | S0-4/S0-6/S0-12/S0-1 |
| dir(D)/跨维重置/焦点映射 | S0-5/S0-8 |

> 本文件为 B-v2 独立修订；A-v2 落盘后才对照，差异与我的判断见 `S0-objections-v2.md`。未写产品代码/契约，未 commit。
