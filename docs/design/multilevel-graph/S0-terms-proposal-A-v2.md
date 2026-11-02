# S0 提案 A-v2：多层次 / 多维度图谱的术语、边界与不做什么（修订版）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-292｜**日期**：2026-11-02（Asia/Shanghai）
> **唯一裁决依据**：`docs/design/multilevel-graph/S0-RULINGS.md`（Lead 逐条复核后的 P0/P1 与 D-1..D-5）。
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35 两轮原话逐字存档）。
> **上游**：`S0-charter.md`、`multilevel-graph-seminar-agenda.md` V0.2、`kg-ontology-v0.md`（v0.3）、`kg-edge-provenance.schema.json`。
> **关系**：本文件是 **A 的修订版**；**不覆盖** `S0-terms-proposal-A.md`（v1，sha `0fddb4c6…`），保留审计链。
> **状态**：待复评。本文件逐条关闭 P0-1/P0-2/P1-1..P1-4 + SE S0-6 + D-1..D-5 + B 并集项。
> **纪律**：只写设计文本；不改产品代码/契约/schema/用户库；未 commit。

---

## 0. 修订摘要

### 0.1 与 v1 的 6 个结构性变化（详见 §16 变更表）

1. **关系 ≠ 标签**：v1 用"语义边集 `E_sem(D)`"作为关联维度挂接/计跳的开关；v2 改为 **`E_relation(D)`**（U-10：包含、引用、语义关联等），semantic/structural/navigation 只作**标签**。
2. **节点类型收敛为两类**：`kind ∈ {kp, cluster}`；`bridge` 降为 **node `role=bridge` / edge state `bridge_only`**。
3. **层次划分限定作用域**：partition 只在 **同一 `(level, view_family)`** 内要求互斥完备；跨视图族/维度允许重叠（对接多归属）。
4. **全展开也走 `present(e, ctx_full)`**：禁止 `all_data_edges` 直出；同一数据不得两种语义读法。
5. **语义判据去 T3**：T3"决策绑定"降级为**消费者准入清单**，不作语义定义必要条件；语义性由 T1/T2/T4 + 现有字段闸门决定。
6. **身份与存在性工程化**：簇采用 `cluster_run_id + 局部序号` + `cluster_key`；边"存无"写成 `ctx + presence(三值) + rule_id`；ViewModel 去掉导航/模式状态。

### 0.2 数据流三段（采纳 B 的架构用语，并作为全文默认语境）

```
DataSource ──(确定性取景服务)──> ViewModel ──(单一渲染契约)──> Renderer(2D/3D)
  ↑ 唯一事实源                     ↑ 视图投影（不持久化）           ↑ 只吃 ViewModel，不取数
collect_graph_data()                present(e,ctx) 决定 shown/       nodeClick/edgeClick/
(nodes/edges/warnings)              suppressed/unknown + rule_id     backgroundClick
```

**证据**：B 并集项（`S0-terms-proposal-B.md:304-308`、`:238-244`）；现实现单数据入口 `src/memoria/services/document.py:2124`、`src/memoria/graph/collector.py:46-99`（A 级）。

### 0.3 证据等级

| 级 | 定义 |
|---|---|
| **A** | 原话/冻结契约/决策/现有可复跑代码事实（file:line 可核） |
| **B** | 单源实测产物（artifacts 研究证据，可复跑但仅一源） |
| **C** | 单源推理/待验证假设 |
| **本项目假设** | 无独立证据、显式写下的设计约定（评审可推翻） |

---

## 1. S0-1「语义」（并集：A 的 T1/T2/T4 + B 的字段闸门；T3 降级）

**定义（一句话）**：图谱语境下，"语义"指一条关系**承载可判定的断言**（谓词可命名、可真假判定、非偶然），并通过**现有可核字段闸门**；`semantic / structural / navigation` 是**标签**，不是"能否被关联维度挂接"的开关。

**形式化**：
```
对边 e=(type, source_id, target_ids, provenance…):
谓词判据：
  T1 可命名   ：存在可写出的谓词 P（contain/extend/…）
  T2 可真假判定：P(a,b) 有真值条件、可构造反例（不靠布局/渲染偶然）
  T4 非偶然   ：不因缩放/取景/投影偶然产生
字段闸门 G_sem（现有可核字段）：
  (a) 作者断言型：provenance_state == "asserted" ∧ assertion_source 完整可核
  (b) semantic contain：contain_kind == "semantic" ∧ derived_by == "author"
      ∧ assertion_source 完整 ∧ curated_by ∧ curated_at
      （由产品校验器 validate_contain_curation_overlay 判定，edge_derivation.py:812-859）
标签：
  label(e) = semantic    ⇔ T1 ∧ T2 ∧ T4 ∧ G_sem
           = structural  ⇔ e 为系统几何/结构派生（如 contain_kind=structural）
           = navigation  ⇔ 无断言跳转/派生相似（如 reference）
  label 不是渲染开关：关联维度可挂接 E_relation(D) 中任意 label 的边（见 S0-3/S0-5）
```
**T3 的新位置（消费者准入清单，不是语义定义）**：
```
消费者准入（C-1..C-4；只约束"谁可以把 semantic 当断言语义使用"，不改变 label 计算）：
C-1 只消费 label=semantic 的边作语义前提（agent/G6/评测）
C-2 必须能追溯 G_sem 字段（provenance/assertion_source/contain_kind/curated_by·at）
C-3 必须做证据等级/来源核验（不得把 structural/navigation 升级为 semantic）
C-4 若字段缺失或过期（stale）⇒ fail-closed：降级为 structural/navigation，不得猜
```

**反例**：
- ✗ 把 `contain_kind=structural` 当整体-部分语义（v0.2 §2.3 禁止）。
- ✗ 把 `reference`（无断言跳转）当语义边（ontology §2.1：不进语义边集）。
- ✗ 用"这条边对某任务很重要"（T3）来定义语义——**T3 已降级**，不能作定义条件。
- ✗ semantic contain 缺 `curated_by/curated_at`：v0.3 校验器会拒绝合并/拒收（fail-closed），不得视为 semantic。

**边界用例**：
- `extend` 边带作者断言证据（asserted）：可满足 T1/T2/T4+G_sem ⇒ label=semantic；无证据则 navigation/投影（具体 S1/S4 定扩展语义）。
- 同一对节点同时有 structural contain 与 semantic contain：**同一关系两种断言状态**；View 按类型映射显示，不得同时当两条语义边。
- semantic 的 audit 字段过期/锚点 stale：label 降级（fail-closed），并保留 `rule_id` 解释（对接 S0-6）。

**U 映射**：U-1、U-2、U-10、U-13/U-14、U-15、U-17、U-27。

**建议裁决（v2）**：采纳 T1/T2/T4 + G_sem 作为语义标签定义；T3 移入消费者准入清单 C-1..C-4；**标签不参与取景/挂接开关**（见 S0-3/S0-5）。

**证据等级**：A（U-1/U-17 原话；ontology §2.1 `:51-59`、v0.2 §2.3 `:113-130`、v0.3 `:126`；schema `:136-149,202-230`；`edge_derivation.py:812-859` 校验器）+ **本项目假设**（C-1..C-4 的准入边界细节）。

---

## 2. S0-2 层次（level）与最小粒度（partition 作用域 + 机检伪代码）

**定义（一句话）**：层次是**同一视图族内 KP 集合的嵌套划分**；第 ℓ 层显示节点是划分块，最深层块=单知识点；跨视图族/维度可以是不同划分（允许重叠）。

**形式化（D-1 限定作用域）**：
```
视图族 view_family = ⟨family_id, basis, level_chain⟩
  （例：family=whole_kb_hierarchy，basis=全库 KP 集；不同维度/不同取景可属于不同族）
同族内：
  层 ℓ ∈ {0..L}；Π_{ℓ,f} 是 K_f 的划分（不交、非空、并=K_f）
  细化：Π_{ℓ+1,f} ⪯ Π_{ℓ,f}
  最小粒度层：Π_{L,f} = {{k} | k∈K_f}（叶=单 KP）
跨族：Π_{ℓ,f1} 与 Π_{ℓ',f2} 允许不同/重叠（多归属，S0-7）
```
**机检伪代码（P1-1，可执行断言）**：
```python
def validate_level_view(view, K, family, is_deepest=False):
    # V1 节点类型只有两类
    assert all(n.kind in {"kp", "cluster"} for n in view.nodes)
    # V2 kp 节点 id 必须属于 KP 集
    kp_nodes = [n for n in view.nodes if n.kind == "kp"]
    assert all(n.id in K for n in kp_nodes)
    # V3 cluster 必须非空、成员 ⊆ K，不得是"非 KP 实体"
    for c in (n for n in view.nodes if n.kind == "cluster"):
        assert c.members and set(c.members) <= K
    # V4 更深层不得有 cluster 叶子：最深层所有节点 kind=kp
    if is_deepest:
        assert all(n.kind == "kp" for n in view.nodes)
    # V5 同一 (level, family) 内：块两两不交，且并 == K_f（若族覆盖全库）
    blocks = [set(n.members) if n.kind == "cluster" else {n.id} for n in view.nodes]
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            assert blocks[i].isdisjoint(blocks[j]), "同族同层划分重叠 → FAIL"
    assert set().union(*blocks) == set(K), "同族同层未覆盖 K → FAIL"
    # V6 展开闭包：cluster 逐层展开到底，成员必须全为 KP 且 ⊆K（递归；检测环）
    assert expand_to_leaves(view) <= K and all(leaf.kind == "kp" for leaf in expand_to_leaves(view))
    return PASS
# fail 语义（fail-closed）：
#   任一断言失败 ⇒ 拒绝该 ViewModel（不渲染/返回错误），不得静默修正；
#   成员关系未知 ⇒ presence=unknown + rule_id（S0-6），不得当作"无成员"
```
**反例**：
- ✗ 一个"节点"不对应 K 子集（如搜索命中集合）⇒ 不是层节点（是维度/取景产物）。
- ✗ 句子/段落/概念作为 KP 之下的层（U-28；v1 只留开放槽位）。
- ✗ 同一 (level, family) 内块重叠或漏 KP ⇒ 划分不成立。
- ✗ 把跨视图族的重叠误判为"非法划分"（D-1：允许）。
- ✗ 最深层的 cluster 叶子（应全部展开为 kp）。

**边界用例**：
- 单 KP 簇：允许；展开后就是该 KP 节点。
- `range_ok=false` 的 KP：仍是 KP（不改变最小粒度），视觉可标注不可定位。
- 空簇：不允许（成员至少 1）。
- 跨族重叠：允许（多归属）；同族同层重叠：非法（机检 V5）。
- 族只覆盖子库（basis⊂K）：V5 的覆盖断言按 K_f 判定，不要求全库。

**U 映射**：U-4、U-5、U-6、U-8、U-21（跨族重叠）、U-26、U-28、U-29。

**建议裁决（v2）**：采纳 partition 形式化并限定到 `(level, view_family)`；机检 V1–V6 作为冻结前 M-2 依据；最深叶强制 kp；fail-closed。

**证据等级**：A（U-4/U-5/U-8/U-28 原话；KP 字段 `collector.py:46-72`）+ **本项目假设**（view_family 作为划分作用域的工程定义；机检伪代码为本提案起草，SE 可改写成测试）。

---

## 3. S0-3 维度（dimension）与 `E_relation(D)`（P0-1 修正）

**定义（一句话）**：维度是在同一层次上决定"取哪些关系源、沿什么方向、扩展几步"的**取景规则**；关联维度按 U-10 使用 **`E_relation(D)`**（包含/引用/语义关联等），语义/结构标签不参与挂接开关。

**形式化**：
```
维度注册项 D = ⟨dimension_id, status, relation_sources, direction, default_hops, termination, priority, version, owner⟩
status ∈ {reserved, specified, frozen, deprecated}   # reserved 不得进入渲染分支
未知 dimension_id ⇒ fail-closed（报错/不渲染），不得回退到默认维度
显式排除：graphStyle（视觉风格）、2D/3D（渲染后端）不是维度（U-33 / SE M-3）
已指定：
  H = hierarchy  ：level partition 的块节点 + 结构包含关系（contain structural）
  A = association：E_relation(A) 按 U-10 关系源挂接/计跳：
       contain(structural|semantic) / reference（link 投影）/ semantic extend 等
       （完整边源清单由 S1 冻结；label 只用于显示/消费准入，不决定能否挂接）
v1 同一视图只激活一个维度（D-5）；维度组合留开放槽位
E_relation(D) = { e ∈ DataSource.edges | type(e) ∈ relation_sources(D) }   # 与 label 无关
```
**开放槽位登记格式（U-25）**：
```
| slot_id | 草案定义 | relation_sources | direction | 默认跳数 | 终止条件 | status=reserved | owner | U-ref |
reserved ⇒ 只登记、不实现、不进 ViewModel；转 specified 须 S1 章程 + Lead 裁决（涉契约需人批）
```

**反例**：
- ✗ 关联维度只走语义边（v1 的做法）⇒ 漏掉 U-10 的"包含关系、引用"等；P0-1。
- ✗ 用 `label=semantic` 当挂接开关（应看 `E_relation(D)`）。
- ✗ 把 `graphStyle` 或 2D/3D 当维度。
- ✗ 未知 dimension_id 静默回退默认（应 fail-closed）。
- ✗ v1 同时激活两个关联维度（D-5 禁止）。

**边界用例**：
- 关联维度在最小层（KP 层）：允许；一跳挂接按 E_relation(A)。
- 结构 contain 在关联维度：允许显示/挂接（label=structural），但消费者不得当语义前提。
- 维度切换：显式动作；跳数计数重置（S0-5）。
- 组合维度：v1 不实现（开放槽位），不得偷偷叠加预算。

**U 映射**：U-8、U-9、U-10、U-11、U-12、U-25、U-30、U-33（排除）。

**建议裁决（v2）**：采纳 `E_relation(D)` 替代 `E_sem(D)`；label 仅标签；维度注册表 status/fail-closed；v1 单维度激活；开放槽位登记格式如上。

**证据等级**：A（U-8..U-12/U-25/U-30 原话；`graph-settings.js` graphStyle 为视觉风格）+ **本项目假设**（注册表字段/组合顺序，S1 可细化）。

---

## 4. S0-4 簇与代表节点（稳定身份 D-2；划分改视图族内）

**定义（一句话）**：簇是**同一视图族内**语义内聚、外部只有零星桥的 KP 子集，用作粗层代表节点；它**不是严格连通分量**，也不能用"内容哈希"当唯一 id（成员一变 curation/审计会失效）。

**形式化**：
```
ClusterInstance = ⟨cluster_run_id, cluster_local_id, cluster_instance_id,
                   cluster_key, members⊆K, internal_edges, bridge_edges,
                   algorithm_id, algorithm_version, params_hash, corpus_manifest_sha256, evidence⟩
cluster_instance_id = f"{cluster_run_id}:{cluster_local_id}"     # run-scoped、可追溯
cluster_key = sha256( "|".join(sorted(member_canonical_ids)) + "|" + algorithm_id
                      + "|" + algorithm_version + "|" + params_hash )   # 可复算/去重键
member_canonical_ids = sorted(kp_id)（UTF-8）  # 用 kp_id，不用 name
内聚/桥：μ(C)≥τ_coh ∧ β(C)≤τ_bridge（阈值 S2 冻结；桥只算语义关系边，参照 S0-1 label 判据）
视图族：簇族只在同一 (level, view_family) 内要求构成划分；跨族/维度允许重叠（S0-7）
审计/curation 引用 = {cluster_run_id, cluster_local_id, cluster_key}（run+key 同时记录）
```
**反例**：
- ✗ `cluster_id = 内容哈希`（D-2 明确不采纳：成员一变 curation/审计引用失效）。
- ✗ 要求"全库跨族互斥"（D-1：只限定同族同层）。
- ✗ 把严格连通分量/现有 `graph-groups`（并查集闭包）当簇（`graph-groups.js:2,83` 现状）。
- ✗ 把簇/成员关系写入产品 sidecar/新增拓扑段（D-3 禁止）。
- ✗ 用 8 条退化 contain 当内聚证据（B 级已知坏数据）。

**边界用例**：
- 单成员簇：允许；展开即 KP。
- 成员变化 ⇒ `cluster_key` 变、`cluster_run_id` 变；旧 curation 引用需按 run+key 迁移/重确认（不得静默套用到新簇）。
- 桥=0 时同时是连通分量：允许，但定义不要求。
- 同族同层簇族=划分；跨族重叠=多归属（S0-7）。

**U 映射**：U-6、U-7、U-13、U-14、U-15、U-19、U-21、U-31。

**建议裁决（v2）**：采纳 μ/β 判据 + D-2 身份；删除"每层簇族必须互斥完备"的全局措辞，改为"同一 (level, view_family) 内构成划分"；簇是展示层对象，不写产品事实源（D-3）。

**证据等级**：A（U-6/U-7/U-13/U-14 原话；`graph-groups.js:2,83`；D-2 在 `S0-RULINGS.md:46`）+ B（8 退化边：`contain-evidence.json`）+ **本项目假设**（`cluster_key` 的拼接/规范化细则由 S2/S6 冻结）。

---

## 5. S0-5 一跳挂接（P0-1：E_relation(D) + dir(D) + rendered-hop）

**定义（一句话）**："一跳"= 从当前视图节点出发，沿**当前维度 `E_relation(D)` 的关系边**按 `dir(D)` 经过**恰好一条渲染图边**到达的节点/边；不闭包、跨维度不计跳、不带端点背后的子图。

**形式化**：
```
当前视图 V、焦点 F、维度 D、方向 dir(D) ∈ {out,in,both,hierarchy_down}
attach₁(V,F,D) = {(u,v,e) | e∈E_relation(D), e 按 dir(D) 连接 u→v, u∈F, v∉V}
计跳：hop 在**渲染图**上计（聚合折叠的簇视为一个节点）；
      folded cluster 内部穿越的底层跳数 = underlying_hop_count（只报告，不展开）
跨维度：不计跳；切换维度显式重置 hop 计数
禁止闭包：不得把 (v,w)∈E_relation(D) 自动加入同一视图（那是第 2 跳）
背后边界：只渲染 v 与 e；v 所在其他子图/簇内部成员不渲染（U-17）
```
**反例**：
- ✗ 关联维度只走 `E_sem`（P0-1；U-10 漏掉包含/引用）。
- ✗ 展示 2 跳邻居（U-18）。
- ✗ 一跳时展开 v 的背后子图（U-17）。
- ✗ 把折叠簇内部穿越算作 1 跳而不给 underlying_hop_count（会误导"一跳"）。
- ✗ 跨维度自动续跳（应重置）。

**边界用例**：
- 同对节点多条关系边：仍算一跳；显示类型按 S0-6 映射，可分条。
- 端点 v 是 cluster 节点：点击进入其所在子图（U-7/U-19）；v 是 KP：点击跳编辑器（U-20，保留）。
- 端点 v 属其他视图族：只作 bridge role 节点显示，不显示其成员（S0-7/S0-9）。
- hop_budget=0：无挂接；=1：一跳。

**U 映射**：U-10、U-11、U-15、U-17、U-18、U-19、U-20、U-21、U-22。

**建议裁决（v2）**：采纳米关系集 `E_relation(D)` + `dir(D)` + rendered-hop + `underlying_hop_count`；跨维不计跳/重置；禁止闭包与背后展开。

**证据等级**：A（U-10/U-11/U-15/U-17/U-18 原话；B 的 dir/present 并集项 `S0-terms-proposal-B.md:238-244`）+ **本项目假设**（dir 枚举与 underlying_hop_count 字段的工程定义）。

---

## 6. S0-6 选择性渲染 + 边「存无/类型」（SE：ctx + presence 三值 + rule_id；P1-2 full_expand present 化）

**定义（一句话）**：渲染 = 从 DataSource 经确定性取景得到的 ViewModel；每条候选边在 `ctx` 下的"存无"由 **`presence ∈ {shown, suppressed, unknown}` + `rule_id`** 表达；**视图缺席 ≠ 数据缺席**。

**形式化（单一判据 present）**：
```
DataSource = collect_graph_data() 的 nodes/edges（唯一事实源）
ctx = ⟨view_id?, level_id, dimension_id, focus_id, hop_budget, filters, mode⟩
      # mode 属于 Presentation 层参数；不写进 ViewModel（D-4）
候选集 C(ctx) = { e ∈ DataSource.edges | type(e) ∈ relation_sources(ctx.dimension) }
presence(e, ctx) ∈ {shown, suppressed, unknown}
  shown     ⇔ e∈C(ctx) ∧ e 按 ctx 被准入（类型/跳数/过滤/端点可见）
  suppressed⇔ e∈C(ctx) 但被规则有意不显示，**必须**带 rule_id
              （如 hop_budget / cross_cluster_policy / level_fold / full_expand_override）
  unknown   ⇔ 候选未计算/数据未加载/无法判定；不渲染，且禁止被解读为"没有关系"
effective_type(e,ctx) = base type + contain_kind + label（显示层），不得回写事实层 type
渲染集合恒等式：render_set = { e | presence(e,ctx)==shown }
（不存在"既不在候选集、也没有 unknown 原因"的边 ⇒ 否则是静默丢边，FAIL）
```
**full_expand（P1-2）**：
```
ctx_full = ⟨level=leaf, dimension=A_all, focus=root, hop_budget=∞, filters=[], mode=full_expand⟩
full 的显示集也必须 = { e | present(e,ctx_full)==shown }；
禁止 "edges=all_data_edges" 直出；全展开与默认共用同一 present + 同一类型映射。
（ctx_full 可让绝大多数候选 shown，但仍经 present 计算并记录 rule_id；unknown/抑制仍可存在）
```

**反例**：
- ✗ 旧行为"数据有边就画"（`graph-engine.js:179-180` `rawEdges=payload.edges`）。
- ✗ 视图中没有边 ⇒ 断言"A 与 B 无关系"（应 unknown/suppressed 解释）。
- ✗ 全展开绕过 present 直接画 rawEdges（P1-2）。
- ✗ suppressed 不带 rule_id；静默丢边。
- ✗ 同一数据在 full_expand 使用另一套语义/类型口径（U-27）。

**边界用例**：
- 同对节点多类型边：逐条独立 present；不得合并成复合边。
- structural contain vs semantic contain：presence 均可 shown，但 effective_type/label 不同。
- 边端点被折叠进 cluster：边改挂到 cluster 节点（S4 规则），presence 保持可解释。
- hop_budget=0：无边；hop_budget=1：一跳挂接（S0-5）。
- full_expand：仍走 present；candidate universe 与默认同源（S0-8）。

**U 映射**：U-3、U-16、U-17、U-18（预算）、U-26、U-27。

**建议裁决（v2）**：采纳 `present(e,ctx)` 唯一判据 + presence 三值 + rule_id + ctx；full_expand 必须 present 化；渲染集合恒等式作为冻结机检（SE M-6）。

**证据等级**：A（U-16/U-17/U-26/U-27；SE review `:151-172`；旧实现 `graph-engine.js:179-180`）+ **本项目假设**（rule_id 枚举由 S4 冻结）。

---

## 7. S0-7 多归属（D-1：同族单归属、跨族多对多；无单值 parent）

**定义（一句话）**："属于"是 **membership 关系实体（多对多）**，与"视图出现"不同；同一视图族内同层恰属一个块，跨视图族/维度可同时属多个簇/层（S0 不设上限）。

**形式化**：
```
Membership = ⟨kp_id, cluster_instance_id, level_id?, dimension_id?, role, weight?, source, provenance⟩
  多对多；无单值 parent；source/provenance 必填（author/algorithm/agent）
视图出现 A(view) ⊆ K，reason ∈ {member, one_hop, bridge, focus}
M ⇏ A；A ⇏ M
同 (level, view_family) 内：membership 是函数（每个 KP 恰属一个块）——划分要求
跨视图族/维度：多归属允许，无上限（上限留 S2/S6，U-31）
cluster_instance_id 采用 D-2 的 run-scoped id；curation/审计引用同时记 run+key
```

**反例**：
- ✗ 用 `nodeToGroup` 单值当 membership（现有实现单值；SE M-7 要求列为冲突并迁移）。
- ✗ 把"当前渲染出现"写回 membership（循环）。
- ✗ 认为 KP 只属于 sidecar 文件（存储归属≠语义成员）。
- ✗ 在全库范围要求"一个 KP 只能属于一个簇"（D-1：只同族同层单归属）。

**边界用例**：
- 同一 KP 在粗层属簇 C、细层属单 KP 块：不同层，不冲突。
- 同一 KP 同时属两个关联簇：允许（跨维度多归属）；导航需记录入口（U-22）。
- membership 可计算不持久化；若持久化须 provenance（S6 定，且 D-3 禁止写产品 sidecar/新段）。
- 从 `nodeToGroup` 迁移：属视图层改造，不得改产品事实源。

**U 映射**：U-21、U-22、U-31、（U-7/U-19 导航）。

**建议裁决（v2）**：采纳 Membership 实体多对多；删除"层内单归属"的全局硬约束，改为"同一 (level, view_family) 内单归属；跨族/维度多归属"；S0 不设上限。

**证据等级**：A（U-21/U-31 原话；SE M-7 `S0-engineering-review.md:294`；现状 `graph-groups.js:123-126`）+ **本项目假设**（Membership 字段集）。

---

## 8. S0-8 默认视图 vs 全展开（三段同源；full 也 present）

**定义（一句话）**：默认入口是层次/关联视图（非全展开）；全展开是同一 DataSource、同一 ViewModel 生成器、同一 Renderer 下，用 `ctx_full` 的**兼容模式**；二者不是两条主线、不是两份数据。

**形式化**：
```
DataSource 身份 = ⟨kb_path, corpus_manifest_sha256, collect_version⟩（同一 manifest）
ViewModel_default = frame(DataSource, ctx_default)      # 层次默认
ViewModel_full    = frame(DataSource, ctx_full)         # 兼容开关（Presentation 参数）
Renderer 同一接口（S0-9）
子集关系：shown(ViewModel_default) ⊆ shown(ViewModel_full) ⊆ DataSource.edges（候选全集）
full_expand 不是第二主线：默认入口唯一，用户显式切换才进入 full
```
**机检（M-8）**：
```
- 两个模式引用同一 DataSource 标识（kb_path + manifest_sha + collect_version）
- shown(default) ⊆ shown(full) ⊆ candidates(DataSource)
- full 的候选全集 = DataSource.edges（经 present；不得旁路）
- 禁止第二数据文件/第二渲染器/第二语义模型
```

**反例**：
- ✗ 双入口/双数据源/双渲染器（U-26）。
- ✗ 默认仍全展开，新视图只是高级模式（违背"彻底替代"）。
- ✗ full 绕过 present 画 rawEdges（P1-2/U-27）。
- ✗ 两个模式各自缓存且可独立漂移（双真相）。

**边界用例**：
- 从默认切全展开：Presentation 层切换 ctx；导航状态由 S5 保存/恢复（D-4）。
- 默认已在叶层（KP 层）：该焦点范围内两模式可收敛（不是双主线）。
- manifest 不同：拒绝（fail-closed），不得混用两份数据。

**U 映射**：U-5、U-26、U-32、U-33、（U-3）。

**建议裁决（v2）**：采纳三段同源 + 子集关系 + full 也 present；模式归 Presentation 正交开关；禁止第二数据源/渲染器。

**证据等级**：A（U-26/U-32 原话；现状 `app.js:1842-1861` 单一 payload；SE M-8 `:295`）+ **本项目假设**（DataSource 身份三元组的具体字段）。

---

## 9. S0-9 渲染接口边界（P0-2：kind 两类；D-4：ViewModel 不含导航/模式）

**定义（一句话）**：渲染接口 = **ViewModel（纯数据投影，不含导航状态/模式）+ Renderer（2D/3D 同签名后端）+ 最小交互事件**；`kind ∈ {kp, cluster}`，`bridge` 只能是 `role`/边状态；渲染器不取数、不做语义判断。

**形式化（ViewModel 最小字段）**：
```
ViewModel = {
  schema_version,
  context: {level_id, dimension_id},              # 渲染所需标签；不含 mode/导航
  nodes: [{ id, kind: "kp"|"cluster", label, role?: "member"|"bridge"|"focus",
            member_count?, expandable? }],
  edges: [{ id, source, target, type, contain_kind?, display_type,
            presence: "shown"|"suppressed"|"unknown", rule_id?, state?: "bridge_only" }],
  capabilities: { can_expand, supports_2d?, supports_3d? }
}
# 约束：nodes.kind 只有两类；bridge 不作 kind；显示类型不改变事实 type；
#       edges 覆盖候选集（render set = presence==shown），渲染器只读。
Renderer（2D/3D 同签名）：
  mount(root, viewModel) / update(viewModel, {transition?}) / destroy() / on(event, handler)
事件（最小集，只报交互，不改状态）：
  nodeClick {node_id, kind}
  edgeClick {edge_id}
  backgroundClick {}
# 不包含：modeToggle / navigateBack / breadcrumbClick / 任何导航状态（D-4；归 S5 导航服务）
```
**反例**：
- ✗ `kind: kp|cluster|bridge` 三节点类型（P0-2；U-19 只允许两类）。
- ✗ ViewModel 携带 mode/面包屑/历史栈（D-4）。
- ✗ 2D/3D 事件结构不一致（实测 2D 带 edge_id、3D 不带：`graph-view-2d.js:544-547` vs `graph-view-3d.js:1043`）。
- ✗ 渲染器直接 `get_graph_data`/读 sidecar/做语义判断。
- ✗ cluster 节点点击复用 `jumpToTarget({file,kp_id})`（需导航服务按 kind 分支）。

**边界用例**：
- bridge 节点：`kind=kp`、`role=bridge`；跨族一跳端点显示为 bridge，不渲染其成员。
- cluster 节点：`kind=cluster`、`expandable`；点击由导航服务决定进入子图（U-7）。
- 2D/3D 输入同一 ViewModel → 同 id 集合（M-9）；能力差异用 capabilities。
- hidden/suppressed 边不产生 edgeClick；explainable rule_id 保留。

**U 映射**：U-6、U-7、U-19、U-26、U-33（+U-35）。

**建议裁决（v2）**：采纳 ViewModel 最小字段 + `kind∈{kp,cluster}` + `role=bridge`/`state=bridge_only` + 2D/3D 同签名 + 事件最小集；导航/模式移出渲染契约（D-4）。

**证据等级**：A（U-19/U-33 原话；现有 2D/3D 代码 `graph-view-2d.js:544-547`、`graph-view-3d.js:1043`；SE M-9 `:296`）+ **本项目假设**（字段命名与 capabilities 细节）。

---

## 10. S0-10 agent 的角色边界（三层 + 确定性取景服务 + 能力 allowlist）

**定义（一句话）**：agent 在 **KP 设计**层主导、在 **语义断言**层可写但须证据+审计、在 **取景**层设计/执行**确定性取景服务**，但不得直接改渲染状态、不得自动推断 semantic。

**形式化**：
```
L_kp   ：agent 主导 KP 产生/边界/命名/粒度/去重/多归属（S10 细化；人监督审计）
L_sem  ：agent 可经 curate_contain 写入 semantic（v0.3），必须 assertion_source +
         curated_by/curated_at（validate_contain_curation_overlay fail-closed）；不得自动推断 semantic
L_view ：确定性取景服务 frame(DataSource, ctx) -> ViewModel（纯函数、可复算、版本化）；
         agent 可设计/调用/提议 ctx，但不得绕过 present/type 映射，不得写 ViewModel/presence
人     ：KP 政策审批、semantic 抽查/撤销、产品决策
系统   ：structural 派生、类型归一化、schema/G6 机检
```
**agent 能力 allowlist（v1，供 SE M-10）**：
```
允许：读 DataSource；提议/执行 KP 变更（S10 审计）；写 semantic curation（v0.3 op，附证据）；
      调用确定性取景服务；提议 ctx 参数；读 ViewModel（只读）
禁止：写 ViewModel/presence/edge_states；写渲染状态/布局；写 cluster/membership 到产品事实源；
      自动推断 semantic；绕过 present 直出边集；把"取景结果"当语义证据（循环）
```

**反例**：
- ✗ agent 自动把几何 contain 标 semantic（v0.2/v0.3 禁止）。
- ✗ agent 直接改渲染/布局/DOM（越层）。
- ✗ agent 自己维护一套取景缓存与产品不一致（非确定性）。
- ✗ agent 用 appearance 反推 membership。

**边界用例**：
- agent 提议 KP 修改：先提案后落库（S10 定义人监督/回滚）。
- agent 提议 semantic curation：带锚点+审计；人可抽查/撤销（v0.3）。
- agent 调用取景服务：同输入必须同输出；失败/降级走确定性回退（S9）。

**U 映射**：U-2、U-29、U-32、U-35。

**建议裁决（v2）**：采纳三层边界 + 确定性取景服务 + allowlist/denylist；写死"agent 不得直接改渲染状态"；S9/S10 细化机制。

**证据等级**：A（U-29/U-32；ontology v0.3 `:1-4,126`；`document.py:3134` curate_contain；`edge_derivation.py:812-859` 校验器；SE M-10 `:297`）+ **本项目假设**（allowlist 边界细节）。

---

## 11. S0-11 v1 不做什么（并集 A+B；每条绑定执行点）

**定义（一句话）**：v1 不做 = v1 交付范围外**不实现、不进产品契约、不进默认视图**的能力集合；每条必须绑定执行点（代码/契约/机检），没有执行点的条目不得进冻结。

**形式化**：设候选能力集 `F`；v1 交付 `F₁⊂F`；`∀f∈F\F₁`：① 不进 ViewModel/契约；② 不进默认视图；③ 仅在议程槽位/后续场次登记；④ 重启须 U-23 新章程（新提案+异议+人批），并记录解除范围的决策 id。

**U 映射**：U-23、U-25、U-26、U-28、U-33（+各条对应 U）。

**建议裁决**：采纳下表（A 的 13 条 + B 的 2 条），**每条有执行点**。

| # | v1 不做 | 执行点（机检/契约） | 依据 |
|---|---|---|---|
| 1 | 词级/句级/概念级节点 | S0-2 机检 V4（最深叶全 kp）；S10 KP 定义 | U-28 |
| 2 | 跨库图 | DataSource 单 kb_path（S0-8 身份三元组） | 本项目假设（范围） |
| 3 | 时间轴/时态维度 | S0-3 注册表 status=reserved；`valid_from/valid_to` 只存不用 | U-25、ontology §2.2 |
| 4 | 自动改写用户正文 | agent allowlist（S0-10）；apply 侧无该能力 | AGENTS.md 边界 |
| 5 | 自动推断 semantic | `validate_contain_curation_overlay` fail-closed；collector 只合并合法 overlay | v0.2 §2.3 规则 3；v0.3 |
| 6 | 新增语义边类型 | ontology v0 §4 不做清单；type 枚举冻结 | ontology v0 §4 |
| 7 | 2D/3D 双设计线/双入口 | S0-9 单一接口；Renderer 同签名 | U-33 |
| 8 | 全展开作默认/第二主线 | S0-8 默认入口唯一；M-8 同源断言 | U-26 |
| 9 | 渲染器直接取数/读 sidecar | S0-9 接口约束；可 grep 渲染器内无 get_graph_data | S0-9 |
| 10 | 把"视图出现"持久化为成员 | S0-7 二分；D-3 禁止写产品事实源 | U-21/U-31、D-3 |
| 11 | 无审计批量 semantic curation | v0.3 校验器要求 curated_by/at；无批量 API | v0.3 §2.3 规则 1 |
| 12 | S0 冻结簇/检索算法/性能阈值 | 章程 §2 不在范围；S2/S8/S9 | 章程 §2 |
| 13 | 复用 graph-groups 当新簇 | S0-4/S0-12 红线（group≠cluster） | `graph-groups.js:2,83` |
| 14 | 把 cluster/membership 写入产品 sidecar/新增产品拓扑段 | D-3；sidecar schema/validator 不新增段；S6 才定 | D-3 |
| 15 | 把 full_expand 实现成第二数据源/第二语义模型 | S0-8 M-8 机检（同源/子集） | U-26/U-27 |

**反例**：把"句子节点"塞进层次；把 full 当默认；启发式批量标 semantic；复用 graph-groups 当簇并写入 sidecar。
**边界用例**：v1 可只实现 2D 后端（3D 留接口）但不拆设计线；"不做"≠永久禁止（须新章程）。
**证据等级**：A（原话/契约/决策）+ **本项目假设**（执行点选择，SE 可改写成检查）。

---

## 12. S0-12 术语映射（三段架构 + present/semantic_edges + 稳定身份）

**定义（一句话）**：术语映射是**新术语到现有产品术语/字段/代码行为的显式函数**，必须标 `same/extends/conflicts/none`；`conflicts` 必须给兼容/迁移/回滚。

**形式化**：`τ: NewTerms → ExistingTerms ∪ {∅}`，`rel ∈ {same, extends, conflicts, none}`；三段的术语映射固定为：
```
DataSource（事实源）  ↔ collect_graph_data() 输出（nodes/edges/warnings）
ViewModel（视图投影） ↔ frame(DataSource, ctx) 输出（不持久化）
Renderer（渲染后端）  ↔ graph-view-2d.js / graph-view-3d.js（同一接口）
present(e,ctx)        ↔ 视图层唯一准入函数（新）
semantic_edges        ↔ 满足 S0-1 label=semantic 的边子集（标签集，不是渲染开关）
E_relation(D)         ↔ 维度注册表 relation_sources 选出的关系集（新；含 U-10 各源）
cluster_run_id/key    ↔ 无现有；簇实例身份（run-scoped + 可复算键）
```

**映射表**（🔴=与现实现直接冲突；🟡=相近不可混用；✅=兼容）：

| 新术语 | 现有产品术语/字段/代码 | 关系 | 冲突/注意 | 兼容/迁移/回滚 |
|---|---|---|---|---|
| 语义标签（semantic） | `edges[]` type/provenance/contain_kind/curated_by·at | extends | 旧 `edges[]` 含 reference/structural，不能全叫语义 | 加 S0-1 标签；不删旧边；UI 文案区分 |
| structural | `contain_kind=structural` | same | 不得显示为整体-部分 | v0.2 已有 |
| navigation | `reference`、派生相似 | extends | reference 不进语义标签 | 过滤规则显式 |
| 层次 level | 无（旧全展开是单层 KP 图） | none | 🔴 旧默认无层 | 默认入口替换；旧行为=full_expand |
| 维度 dimension | 无；`graphStyle` 不是维度 | none | 🔴 视觉风格≠维度 | 注册表 + fail-closed |
| 关系集 E_relation(D) | `edges[]` + 维度注册表 | none | 🔴 旧"语义边"窄化 | 按 U-10 关系源（S1 冻结清单） |
| 簇 cluster | `graph-groups`（并查集闭包） | conflicts | 🔴 group≈连通分量，不是内聚+零星桥 | 新 `semantic_cluster`；group 降级为输入候选；不写产品 |
| 簇身份 | 无 | none | 🔴 内容哈希不可用于审计 | D-2：run+local id + `cluster_key` |
| 代表节点 | 无；节点全是 KP | none | 🔴 旧点击假设 kp_id | `kind=cluster`；导航按 kind 分支 |
| bridge | 无（externalFocus 仅高亮） | extends | 🟡 不能作第三 kind | node `role=bridge` / edge `state=bridge_only` |
| 一跳 | ego-only（0.5 范围） | extends | 🟡 旧 ego 非维度 | `E_relation(D)`+dir+hop；保留 externalFocus 作编辑器聚焦 |
| 选择性渲染 | `expandLinks`/`loadPayload` 全量 | conflicts | 🔴 旧"有边就画" | 新 present；旧行为仅 full_expand 且不得标语义 |
| present(e,ctx) | 无 | none | 🔴 旧无缺席原因 | 视图层函数；不写事实源；presence+rule_id |
| edge 存无/类型 | `edges[].type/contain_kind/provenance` | extends | 🔴 事实≠视图 | 事实字段不变；视图 effective_type/presence 不回写 |
| 多归属/membership | `nodeToGroup` 单值 + node.file 单值 | conflicts | 🔴 单值 parent | Membership 多对多；旧单值废弃/迁移（视图层） |
| ViewModel | `get_graph_data` payload | extends | 🟡 payload=数据，VM=投影 | 三段分离；旧 loadPayload 仅 full 兼容 |
| Renderer 2D/3D | `graph-view-2d.js`/`graph-view-3d.js` | same | 事件已不一致 | 单一接口；2D 先实现；3D 同签名 |
| full_expand | 现默认行为 | extends | 若变第二主线⇒违反 U-26 | Presentation 开关；present(ctx_full) |
| cluster_key 审计引用 | 无 | none | 需同时记 run+key | curation/审计记录 {run_id, local_id, key} |

**冲突红线**：① graphStyle≠维度；② graph-groups≠簇；③ reference≠语义；④ 视图缺席≠数据缺席；⑤ structural≠整体-部分；⑥ cluster/membership 不写产品事实源（D-3）；⑦ 导航/模式不进 ViewModel（D-4）。

**反例/边界用例**：
- ✗ 把 payload 直接当 ViewModel（旧 `loadPayload` 路径）。
- ✗ cluster 节点调用 `jumpToTarget` 的 KP 分支。
- 边界：旧数据无 contain_kind/curated_by ⇒ structural/navigation fail-safe；旧数据无 membership ⇒ 视图不显示簇（可用内存聚类，不写产品）。

**U 映射**：U-1/U-10、U-16/U-27、U-20、U-21、U-26、U-28、U-33。

**建议裁决**：采纳映射表 + 三段架构 + 7 条红线；`conflicts` 项在 S1–S6 落地方案前不得按旧口径实现。

**证据等级**：A（ontology/schema/现有代码 file:line；SE 映射草案 `:307-324`）+ **本项目假设**（术语最终命名若与 B/SE 冲突，按并集裁决）。

---

## 13. 覆盖矩阵 U-1..U-35（v2 更新）

| U# | 要点 | 本提案位置 | 后续 |
|---|---|---|---|
| U-1 | 语义最重要 | S0-1 | S4/S7 |
| U-2 | 前端想用+后端增效 | S0-1/S0-10 | S7/S8 |
| U-3 | 海量节点/错线 | S0-6/S0-8 | S3/S4 |
| U-4 | 多层次 | S0-2 | S1/S2 |
| U-5 | 非全展开默认 | S0-2/S0-8 | S3 |
| U-6 | 代表子图节点 | S0-4/S0-9 | S3 |
| U-7 | 点击深入 | S0-4/S0-9 | S5 |
| U-8 | 层次维度 | S0-2/S0-3 | S1 |
| U-9 | 其他维度 | S0-3 | S1 |
| U-10 | 关联维度（包含/引用/语义关联） | **S0-1/S0-3/S0-5**（E_relation） | S1/S4 |
| U-11 | 跳数 | S0-3/S0-5 | S1/S4 |
| U-12 | 更多维度 | S0-3 | S1 |
| U-13 | 非严格连通子图 | S0-4 | S2 |
| U-14 | 语义划分小群 | S0-1/S0-4 | S2 |
| U-15 | 语义边挂接一跳 | S0-5 | S4 |
| U-16 | 选择性渲染 | S0-6 | S4 |
| U-17 | 背后图不带入 | S0-5/S0-6 | S4/S5 |
| U-18 | 限制跳数理由 | S0-5/S0-6 | S4 |
| U-19 | 点击 KP/簇节点 | S0-5/S0-9（kind 两类） | S3/S5 |
| U-20 | KP→编辑器 | S0-5/S0-9/S0-12 | S5 |
| U-21 | 多归属 | S0-2/S0-7 | S2/S5/S6 |
| U-22 | 新一跳 vs 更深 | S0-5/S0-7 | S5 |
| U-23 | 覆盖不足重开 | §0/§13（全 35 覆盖） | 流程 |
| U-24 | 原话供起来 | vision 文件（不转述） | — |
| U-25 | 开放槽位 | S0-3 | S1 |
| U-26 | 默认替代+全展开开关 | S0-8 | S3/S4/S5 |
| U-27 | 边存无/类型 | S0-6 | S4/S6 |
| U-28 | 最小粒度=KP | S0-2 | S1/S10 |
| U-29 | agent 设计 KP | S0-10 | S10 |
| U-30 | 关联维度定义 | S0-3/S0-5 | S1/S4 |
| U-31 | 多归属上限 | S0-7 | S2/S6 |
| U-32 | 规模/后端检索 | S0-8/S0-10 | S9 |
| U-33 | 2D/3D 不分家 | S0-9 | S3/S4 |
| U-34 | 逐议项/不设上限 | 本文件逐项结构 | 流程 |
| U-35 | SE 专家 DFD/ER/状态图 | S0-9/S0-10 接口预留 | S5a/S6a/S9a |

---

## 14. 跨议题 D-1..D-5 落实表

| 裁决 | 落实位置 | 说明 |
|---|---|---|
| D-1 划分作用域 | S0-2/S0-4/S0-7 | partition 仅 `(level, view_family)`；跨族/维度重叠 = 多归属 |
| D-2 cluster 身份 | S0-4 | run-scoped instance id + `cluster_key`；审计引用同时记 run+key |
| D-3 membership 持久化禁令 | S0-7/S0-11 #14/S0-12 红线⑥ | S0 不写产品 sidecar/新拓扑段；semantic overlay 仍按 v0.3 |
| D-4 ViewModel 纯度 | S0-8/S0-9/S0-12 | ViewModel 无 mode/导航/面包屑；导航归 S5；全展开是 Presentation 参数 |
| D-5 维度组合 | S0-3 | v1 同视图只激活一个维度；组合留槽位 |

---

## 15. 仍存争议 / 待 Lead 裁决（v2 未擅自消解）

1. **`E_relation(A)` 的冻结边源清单**：U-10 已含 contain(两 kind)/reference/semantic extend 等，但"semantic extend"的判定边界（T2 真实性）需 S1 冻结；S0 只定关系源类别。
2. **`cluster_key` 规范化细节**：分隔符/`member_canonical_ids` 的编码、params_hash 的算法（S2/S6）；成员变化后旧 curation 引用是"迁移"还是"失效重确认"，需决策。
3. **full_expand 的 present 语义**：ctx_full 下是否允许 suppressed（如 invalid/unknown 仍存在）、candidate universe 是否严格=`DataSource.edges`；U-27 一致性与兼容成本的平衡留 S4。
4. **T3 降级后的消费者准入清单**：C-1..C-4 的检查点/证据要求是否够严（防止低价值 semantic 进入 agent 前提），S7/S8 可加评测门槛。
5. **View role/桥的边界**：bridge 节点 role 与导航服务（S5）的交互、跨族一跳的返回路径，细则留 S5。

---

## 16. A-v2 变更表（逐条旧→新，含 v1 行号）

> 旧文件：`S0-terms-proposal-A.md`（v1 sha `0fddb4c6…`）；行号为该文件行号（可 grep 复核）。

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S0-1 定义含 T3「决策绑定」为语义必要条件（v1 L41/L65） | T3 移入**消费者准入清单 C-1..C-4**；语义= T1/T2/T4 + G_sem 字段闸门（§1） | P1-3 |
| 2 | S0-1 语义=单一"语义边"概念 | 增加字段闸门 `G_sem`（asserted / semantic contain + curated_by·at，复用产品校验器）与三标签（§1） | 并集 B |
| 3 | S0-3/S0-5 用 `E_sem(D)`（v1 L170/172/174） | 全部改 **`E_relation(D)`**；U-10 关系源（contain 两 kind / reference / semantic extend 等）；label 仅标签（§3/§5） | P0-1 |
| 4 | S0-3 未写注册表 status/fail-closed | 维度注册表 status 枚举 + 未知 id fail-closed + graphStyle/2D/3D 显式排除（§3） | SE M-3 |
| 5 | S0-2 partition 全局"每层簇族构成划分"（v1 L160/162） | 限定 `(level, view_family)`；跨族/维度重叠允许（§2） | P1-1/D-1 |
| 6 | S0-2 无机检伪代码 | 增加 `validate_level_view` V1–V6 伪代码 + fail-closed 语义（§2） | P1-1/SE M-2 |
| 7 | S0-4 无 stable 身份 | 增加 D-2：`cluster_run_id + local_id` + `cluster_key=sha256(sorted(members)+algorithm+version+params_hash)`（§4） | P1-4/D-2 |
| 8 | S0-4/S0-7 全局"层内互斥/单归属"（v1 L160/L244/L260） | 删除全局措辞；改为同族单归属、跨族/维度多对多（§4/§7） | D-1/并集 B |
| 9 | S0-5 无 dir/underlying_hop_count | 增加 `dir(D)`、rendered-hop、`underlying_hop_count`、跨维不计跳（§5） | 并集 B/SE M-5 |
| 10 | S0-6 8 值边状态枚举、无 ctx（v1 S0-6 定义段） | 改为 `ctx + presence∈{shown,suppressed,unknown} + rule_id`；渲染集合恒等式（§6） | SE/并集 |
| 11 | S0-6/S0-8 全展开 `edges=all_data_edges`（v1 L274） | full_expand 也走 `present(e,ctx_full)`；禁止直出（§6/§8） | P1-2 |
| 12 | S0-7 无 Membership 实体、层内单归属硬约束（v1 L244/260） | 增加 Membership 多对多实体、无单值 parent、`nodeToGroup` 冲突迁移（§7） | D-1/SE M-7 |
| 13 | S0-8 默认/全展开仅"同数据源" | 增加三段 DataSource→ViewModel→Renderer、DataSource 身份三元组、子集关系、M-8 机检（§8） | 并集 B/SE M-8 |
| 14 | S0-9 `kind: kp|cluster|bridge`（v1 L306） | `kind∈{kp,cluster}`；bridge → node `role`/edge `state=bridge_only`（§9） | P0-2 |
| 15 | S0-9 ViewModel 含 mode/breadcrumb；事件含 modeToggle/navigateBack（v1 L304-320） | 移除导航/模式；事件最小集 nodeClick/edgeClick/backgroundClick；导航归 S5（§9） | D-4/并集 B |
| 16 | S0-10 三层角色表 | 增加确定性取景服务 frame() + agent 能力 allowlist/denylist（§10） | 并集 B/SE M-10 |
| 17 | S0-11 13 条，无执行点 | 15 条（A+B）每条绑定执行点；新增"cluster/membership 不写产品 sidecar/新段"（§11） | 并集 B/SE M-11 |
| 18 | S0-12 16 组映射，无三段/present | 增加三段架构映射、`present/semantic_edges/E_relation/cluster_key` 映射、7 条红线（§12） | 并集 B/SE M-12 |
| 19 | 覆盖矩阵 | 更新 U-1..U-35（S0-10/U-10 等改指 E_relation）（§13） | 章程验收 |
| 20 | 全文总立场 | 新增 §0 数据流三段与修订摘要；旧结论未变者保留原文引用 | 本轮 |

---

## 17. 证据锚索引（v2 新增/关键）

| 主张 | 锚 | 等级 |
|---|---|---|
| P0/P1 裁决与 D-1..D-5 | `docs/design/multilevel-graph/S0-RULINGS.md:14-22,30-49,54-61` | A |
| 语义字段闸门复用产品校验器 | `src/memoria/graph/edge_derivation.py:812-859`（validate_contain_curation_overlay）；`:862-903`（merge） | A |
| collector 数据源与 overlay 合并 | `src/memoria/graph/collector.py:46-99`（overlays 收集 `:76-83`；merge `:92-98`） | A |
| 边身份/canonical id | `edge_derivation.py:787-793`；dedupe `:630-669` | A |
| contain 两 kind / structural 派生 | `edge_derivation.py:319-371`；ontology `:113-130`；schema `:136-149,202-230` | A |
| 2D/3D 事件不一致 | `graph-view-2d.js:544-547` vs `graph-view-3d.js:1043` | A（实测） |
| 旧全量渲染 | `graph-engine.js:88-110,167-181`；`app.js:1842-1861` | A |
| graph-groups 并查集 | `graph-groups.js:2,83` | A |
| ViewModel/Renderer 三段（B 并集） | `S0-terms-proposal-B.md:238-244,304-308` | B |
| SE S0-6 三值/rule_id/M 系列 | `S0-engineering-review.md:151-172,286-299` | A（计划级） |
| present/full 同源（B/SE） | `S0-terms-proposal-B.md:304-316`；SE M-8 `:295` | B/A |
| 8 退化边/33 contain（B 级事实） | `artifacts/agent/verify/debate/graph-utility/contain-evidence.json` | B |

**复跑（关键机检）**：
```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) 12 议项 + U-1..U-35 齐全
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S0-terms-proposal-A-v2.md').read_text(encoding='utf-8'); print('S0 missing:',[f'S0-{i}' for i in range(1,13) if f'S0-{i}' not in t]); print('U missing:',[f'U-{i}' for i in range(1,36) if f'U-{i}' not in t])"
# 2) 关键代码锚
python -c "from pathlib import Path; checks=[('src/memoria/graph/edge_derivation.py',812,'def validate_contain_curation_overlay'),('src/memoria/graph/edge_derivation.py',862,'def merge_contain_curation_overlays'),('src/memoria/graph/collector.py',92,'merge_contain_curation_overlays'),('src/memoria/ui/static/app/js/graph-engine.js',179,'rawEdges = payload'),('src/memoria/ui/static/app/js/graph-view-2d.js',544,'nodeClick'),('src/memoria/ui/static/app/js/graph-view-3d.js',1043,'nodeClick')]; [print('OK' if n in Path(f).read_text(encoding='utf-8').splitlines()[l-1] else 'MISMATCH', f, l) for f,l,n in checks]"
```
（本文件主张均有上表/§1–§12 锚或显式"本项目假设"；未列锚的措辞若属解释性，按本项目假设处理。）
