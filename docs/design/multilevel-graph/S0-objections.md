# S0 独立异议与 A/B 差异（复核方）

> **对象**：`S0-terms-proposal-A.md`（主办研究）sha256 **`0fddb4c6a9179ce4c02a273f55cf8e3457d0647bba967f6017ec444afd7927aa`**（40,149 B）；`S0-terms-proposal-B.md`（本复核方）sha256 **`48e29f3dae7fe860b839928d1837d5094f22fff92a3010299c3d1563a8f0febe`**（37,692 B）。
> **依据（最高）**：`docs/design/multilevel-graph-vision.md` U-1..U-35；`S0-charter.md`（12 议项、预注册判据）；`multilevel-graph-seminar-agenda.md` V0.2；现有契约 `kg-ontology-v0.md`（v0.3）/`kg-edge-provenance.schema.json`。
> **独立性**：B 于 2026-11-02 17:01 落盘（A 17:04 才出现）；B 写作时未读 A。写完 B 后才对照 A，下列差异**逐项列、不合并**。
> **证据等级（本文件）**：A=可执行/机检源码（file:line）；B=冻结数据/实测；C=契约/文档推断；PI=本项目假设。SE 校核 `S0-engineering-review.md` 仅作旁证，不替代本复核。

---

## 0. A/B 差异总表（S0-1..S0-12；逐项可对照，不静默合并）

| 议项 | A 的立场（条目） | B 的立场（条目） | 差异要点 | 证据强弱 | 工程化判断 |
|---|---|---|---|---|---|
| S0-1 语义 | T1 可命名/T2 真假判定/T3 决策绑定/T4 非偶然；分 semantic/structural/navigation（A §1，L38-65） | `semantic_edge(e)` 判据=现有可核字段（type+provenance+assertion_source/contain_kind+curated_by/at）；reference/structural 排除（B S0-1） | A 多了"谓词可命名/决策绑定"两条强判据；B 更直接复用 v0.3 可机检字段 | A：原话+契约（A 级）+ T3 自标本项目假设；B：契约字段可机检（A 级） | A 概念更严，T3 不可机检；B 可机检但**可能过宽/过窄**（只按字段）；建议 A 的 T1/T2/T4 + B 的字段闸门合并，T3 降为 reviewer checklist |
| S0-2 层次/粒度 | 嵌套划分 Π_ℓ（细化）、Π_L={{k}}（A §2，L73-96） | Level 粒度轴 + display kind {cluster,kp}，最深只能 kp；不要求划分（B S0-2） | **核心差异**：A 要求层=划分（互斥完备），B 不要求；A 形式化更强，B 更灵活 | A：形式化可推（C），无实现/机检产物；B：同样 C | A 更可机检（partition 断言），但**与 U-21 可能冲突**（见 P1-1）；B 较弱；建议 A 的 partition + 明确"层内单归属/多归属在维度/视图族" |
| S0-3 维度 | H=hierarchy（结构边）、A=association（语义边），槽位登记 6 要素（A §3，L104-131） | active=level_dimension+relation_dimension（U-10 关系源），reserved 三要素、无渲染分支（B S0-3） | 相似；A 的槽位模板更细（方向/终止/优先级），B 更强调 reserved 不得进渲染；**A 的 A 维度只走语义边**（与 U-10 冲突，见 P0-1） | A：原话+graphStyle 排除（A）；B：原话（C） | A 槽位更完整；两侧都需补"association 关系源含 contain/reference" |
| S0-4 簇 | μ/β 形式化 + 每层簇族必须构成划分；代表节点=视图 kind（A §4，L139-160） | 簇=成员+内边+桥；cluster_id=stable_hash(members+algo version)；不要求划分（B S0-4） | A 有内聚/桥公式（阈值交 S2），B 有稳定 id 与成员可展开；A 要求 partition，B 允许重叠 | A：U-13/14+代码（A）；B：U-13/14（C）+稳定 id（PI） | A 的 μ/β 更可复算；B 的 stable id 是 A 缺失；建议合并（A 公式+B id），并把 partition 降为"同一 (level,dimension) 的视图族"以免与多归属冲突 |
| S0-5 一跳 | 恰好 1 条、方向 dir(D)、不闭包、跨维重置；**关联维度默认只走语义边**（A §5，L170-190） | 恰好 1 条、按关系源（U-10 含 contain/reference/语义关联）、dedupe、不递归；B 已自更正 R1（B S0-5） | **P0 差异**：A 把 U-10 关联维度窄化为 semantic-only；B 已自更正为 U-10 关系源；A 有方向 dir，B 暂未定方向 | A：原话（A）+方向 PI；B：原话（A，已修） | A 方向契约更完整；B 的 U-10 覆盖更正确；需 A 接受 B 的 U-10 修正 + B 接受 A 的 direction 定义 |
| S0-6 选择性渲染/存无 | 边状态枚举 full/bridge_only/folded/hidden_by_*/unknown；类型映射 τ；**全展开"显示全部数据边"**（A §6，L202-229） | `present(e,ctx)` 布尔唯一判据 + suppression 原因；semantic_edges 入集；full_expand 显式参数（B S0-6/S0-8） | A 状态枚举更细、可工程；B 判据更硬（present 唯一）；A 的全展开用"全部数据边"是旧假设残留（P1-2） | A：旧代码+原话（A）；B：原话+旧代码（A） | A 状态枚举可工程化更强；B present 更防双真相；建议 A 枚举 + B"present 唯一/全展开也走 present + 非语义标签" |
| S0-7 多归属 | M⊆K×Cluster×Role；层内 π_l 函数（单归属）+ 跨层嵌套 + 跨维多归属（A §7，L240-258） | membership 多对多；无单值 parent；视图出现≠成员；不设上限（B S0-7） | A 有 Role/provenance 与层内单归属；B 明确多对多/无单 parent；**A 的层内单归属与 U-21 需裁决**（P1-1） | A：U-21/U-31（A）+ PI；B：U-21/U-31（A） | A 角色/provenance 更强；B 无单 parent 更贴 U-21；建议 A 的 Role + B 的多对多（按视图族限制） |
| S0-8 默认 vs 全展开 | 模式枚举 default/full_expand；同 ViewModel；焦点保持/映射（A §8，L270-291） | 同 DataSource+同 Renderer+参数退化；默认唯一入口；禁止第二数据源（B S0-8） | 相似；A 更细切换行为，B 更强调同源/无双主线；A 的 full 仍写"全部数据边"，需 present 化 | A：原话（A）+PI；B：原话（A） | 合并：A 的焦点映射 + B 的"同一 builder/present"机检 |
| S0-9 渲染接口 | ViewModel 字段含 `kind: kp\|cluster\|bridge`、capabilities、事件 6 种（A §9，L299-337） | ViewModel 含 `kind{kp,cluster}` + semantic flag；2D/3D 同签名；事件 5 种（B S0-9） | A 更细（capabilities/事件），但 **bridge 作为第三 node kind**（P1-4）；B 的 kind 更贴 U-19/U-28 | A：3D/2D 代码事实（A）+PI；B：原话（A） | A 的接口字段更完整（补 B 的 capabilities）；B 的 kind 约束更安全；建议 A 字段 + B kind 限制（bridge 改 state/role） |
| S0-10 agent 边界 | 三层 L_kp/L_sem/L_view；人/系统角色；agent 可设计/执行检索取景（A §10，L345-371） | 三层（KP/语义/取景）；agent 可设计/调用取景但"确定性服务生成视图"（B S0-10） | 相似；A 多"人/系统"角色与 S10/S9 交接；B 更强调服务确定性 | A：U-29/U-32+v0.3（A）；B：同（A） | 合并；A 的角色表更完整，B 的"不得直接改渲染状态"应保留 |
| S0-11 不做什么 | 13 条（含渲染器直接读 KB、无审计批量 curation；A §11，L379-415） | 12 条（含不把 cluster/membership 写产品 sidecar、词级/句级；B S0-11） | A 多"渲染器直连数据/无审计批量"；B 多"不写产品 sidecar/不新增产品段"；互为补充 | A：契约（A）+代码（A）；B：契约（A） | 取并集（约 15 条），每条绑定执行点（SE 建议同） |
| S0-12 术语映射 | 16 行映射；冲突 5 红线；兼容/迁移/回滚（A §12，L419-470） | 12 行映射；DataSource→ViewModel→Renderer 三段；cluster vs graph-groups 标红（B S0-12） | A 现有术语覆盖更广、兼容/回滚更细；B 明确 present/semantic_edges/三段与 `view model` 冲突；A 缺 present 映射 | A：代码/契约（A）；B：代码（A） | A 表更全；B 的三段/新名前缀应合并；A 需补 present/semantic_edges 映射 |

**总体**：A 在形式化（层次划分、μ/β、边状态枚举、术语映射、证据文件）上更强；B 在"U-10 关系源覆盖（已修）、stable cluster id、present 唯一判据、kind 约束、DataSource→ViewModel→Renderer 三段"上更强。**建议 Lead 按议项并集，不做整份择优**；下列异议对 A 为主，B 自身弱点一并标注。

---

## 1. 异议（按严重度排序；P0=与 U 原话直接冲突/不得冻结；P1=冻结前必须裁决；P2=可冻结但后续场次必须补）

### P0-1（A；B 已自更正）「关联维度」被窄化为"只走语义边"，直接违背 U-10

- **议项**：S0-3 / S0-5 / S0-1（U-10）。
- **异议**：A 的 S0-3 把 association 定义为"按语义边挂接"（A L111），S0-5 明确"关联维度默认只走语义边（semantic 或作者断言型），结构边仅作层次维度/导航背景"（A L168、L190；形式化 `E_sem(D)` 见 L174-176）。但 U-10 原话是：关联维度要显示"**本来节点之间没有边，可能因为一些包含关系、引用、语义关联等等会显示出来**"——**包含关系（contain，含 structural）与引用（reference）本身就是关联维度要显示的关联类型**，不是"仅 semantic 边"。
- **反例/证据**：两个 KP 只有一条作者 `reference` 边（无断言跳转）或只有 `contain(structural)` 边：按 U-10 关联维度应可显示其关联节点并计跳；按 A 的 S0-5 "只走语义边"则该节点不出现/不计跳 ⇒ U-10 未覆盖（vision §2：未覆盖 U 的设计不得评审通过）。
- **可行动修复**：把 S0-5 的 `E_sem(D)` 改为 `E_relation(D)`（U-10 关系源集合：contain(structural/semantic)、reference、semantic extend 等），并把 **semantic/navigation/structural 作为边的标签**而不是"能否挂接"的开关；跳数按关系源计，语义强度按标签判。B 已在 S0-5 R1 自更正（本异议亦针对 B 初稿，已修）。
- **严重度理由**：直接漏原话 U-10，章程预注册判据 5（U 覆盖不全不得冻结）⇒ **P0，A 必须修后才可冻结**。

### P0-2（A）`kind=bridge` 作为第三种视图节点类型，与 U-19/U-28 冲突

- **议项**：S0-9（+S0-2/S0-5）。
- **异议**：A 的 ViewModel nodes `kind: kp|cluster|bridge`（A L306）。U-19 明说一跳节点"**可以是知识点可以是代表连通子图的节点**"——即视图节点类型只有 KP 与簇（代表）两类；bridge 是**一跳挂接的角色/状态**，不是第三种本体/视图类型。若冻结 `kind=bridge`，会与 S0-2 的"最深叶子必须 kp"、S0-9 的点击语义（KP→编辑器）冲突，并给 S6 引入第三种节点实体。
- **反例/证据**：一个一跳 KP 若被标 `kind=bridge`，S0-2 的"叶子 kind=kp"机检失败，`app.js:1661-1677` 的 `node.kp_id/jumpToTarget` 逻辑无法判定它是不是 KP；G6 的 canonical node id 也会多一类。
- **可行动修复**：`kind ∈ {kp, cluster}` 固定；增加 `role/state ∈ {member, one_hop_bridge, focus}`（或 edge state `bridge_only`），bridge 只是展示角色；事件仍按 kind 决定点击行为（kp→编辑器、cluster→下钻）。
- **严重度理由**：与 U-19 原话冲突 + 污染本体/机检 ⇒ **P0，A 必须修**（B 的 kind 约束可直接采用）。

### P1-1（A；B 也需补）「最小粒度=知识点」仍不可机检；且"层内划分"与 U-21 多归属可能冲突

- **议项**：S0-2（+S0-4/S0-7；U-21/U-28）。
- **异议（不可机检）**：A 给了漂亮的数学形式（Π_ℓ 划分、Π_L={{k}}，A L73-96），但**S0 层没有任何可执行断言/产物**规定在哪个对象上检查（ViewModel？聚类输出？）、失败怎么办；B 同样只给定义（B S0-2）——这是两份提案的共同缺口。章程要求每场产出"可机检或有人工协议复现"，当前只是纸面形式化。
- **异议（划分 vs 多归属）**：A 同时要求（a）每层簇族必须构成该层划分、层内 π_ℓ 是函数（A L160、L244），（b）U-21 允许 KP 属于不同知识子图谱/层次/维度。若"不同知识子图谱"包含**同一层**的多个语义簇，则 A 的划分直接禁止同层多归属；A 只把多归属放到"跨层/跨维度"解决（A L244-246），这是**对 U-21 的收窄解释**，需 Lead 明确裁决。
- **反例**：KP k 同时满足簇 C1、C2 的 μ/β（S0-4）且同层；A 的 π_ℓ(k) 只能取一个 ⇒ 同层多归属不可能；U-21 未限制"不同子图谱"必须跨层/跨维。
- **可行动修复**：① S0-2 增加机检伪代码：`assert all(leaf.kind==kp); assert leaf_ids==K; assert no cluster leaf; assert member_sets 在 (level,dimension) 视图族内互斥/在跨视图族可重叠`；② Lead 明确"层内划分"的粒度：是 `(level, dimension)` 的视图族划分，还是全局 K 的划分；若是前者，S0-2/S0-4 的 `K→Π_l` 改成 `K→Π_{l,D}` 并允许同层跨维重叠；③ B 同样补机检（自认）。
- **严重度**：不解决则 S0 冻结后 S2 必返工，且 U-21 可能未覆盖 ⇒ **P1（冻结阻断）**。

### P1-2（A）「全展开=显示全部数据边」把 U-26 兼容开关写成 U-27 旧假设的豁免区

- **议项**：S0-6 / S0-8（U-26/U-27）。
- **异议**：A 的 S0-8 full_expand 写 `edges=all_data_edges`（A L274），S0-6 边界又写"全展开模式：显示全部数据边"（A L223）。这与 U-27「同一对节点在不同层次/维度/上下文，边可能存/无/类型不同，**不能沿用数据有边就渲染的旧假设**」在**默认视图**内被 A 正确否定了，但在 full_expand 被重新合法化为"全部数据边"。若 full_expand 不经过 `present(e,ctx)` 而直接按数据画，就形成"同一份数据两种语义读法"（A 自己也把"全展开用另一套类型/语义规则"列为反例，但没给机检）。
- **反例**：full_expand 下一条 `reference`/`structural` 边被渲染但无任何"非语义/导航"标注 ⇒ 用户/agent 可能把它当语义关系；默认视图与全展开对同一对节点的"边存在"给出相反结论，形成双真相。
- **可行动修复**：把 full_expand 定义为 `present(e, ctx_full)` 的参数（如 `mode=full_expand` → `present` 允许所有数据边），**但每条边必须带 semantic/navigation/structural 标签**；机检：`full_expand ViewModel = Select(DataSource, ctx_full)` 且 `edges ⊆ all_data_edges`、`labels` 完整；禁止 full_expand 走独立数据路径。B 已按此写（B S0-6/S0-8），A 可直接采用。
- **严重度**：不修则默认/全展开双真相风险（U-26 解读约束）⇒ **P1（冻结前）**。

### P1-3（A）S0-1 的 T3「决策绑定」不可操作/不可证伪，且被当作语义门槛

- **议项**：S0-1（U-1）。
- **异议**：A 的 T3 要求"存在消费者决策 Δ，使 e 的加入可改变结论"（A L41），但未定义 Δ 的登记方式/消费者清单/判定命令；A 自己在证据等级中把它标为"本项目假设"（A L65），却仍作为"semantic"的四要件之一。结果是：一条有作者断言+可读锚点的边，若找不到已登记的 Δ，按 A 不是 semantic；反之，T3 无法被任何机检证伪（"没有消费者"可被无限解释）。
- **反例**：作者对 `extend(A,B)` 写了 `asserted + assertion_source`（可核），但当前没有 agent/人消费该边做决策 → A 的 T3 判它非 semantic；这与 U-1"图谱最重要的是语义"以及"可核断言即语义"不一致，也会把大量已有作者边排除。
- **可行动修复**：把 S0-1 拆成两层：**语义性（intrinsic）**=`T1 可命名 ∧ T2 可核（assertion_source+quote） ∧ T4 非偶然`，机检复用 G5 provenance 闸门；**T3 决策绑定**降为"消费白名单/评测计划"（G6/S8）的准入建议，不用于 S0 语义分类。或在 A 中给出 T3 的可执行登记表（consumer/decision/predicate）与反例命令。
- **严重度**：语义判据不可机检且可能误杀 ⇒ **P1（冻结前裁决）**。

### P1-4（A）cluster 身份/可复算契约缺失（B 有 stable id，A 无）

- **议项**：S0-4（+G6 快照/复现约束）。
- **异议**：A 给了 μ/β 公式但**没有定义 cluster_id 的稳定公式**（成员排序+算法版本+corpus id），S0-4 只要求"阈值/算法由 S2 定、可复算"（A L160）。G6 的边组消融/快照需要"同一 frozen KB 上逐边可排序、可 diff、可复原"；没有稳定 cluster_id，簇节点/成员无法跨次复现，A/B 对比与 G6 无法做。
- **反例**：两次同参数聚类得到相同成员集但 cluster_id 顺序/哈希不同 ⇒ 快照 diff 全变；或成员集微变导致 id 全变，无法做"删簇可复原"。
- **可行动修复**：S0-4 冻结 `cluster_id = stable_hash(sorted(member_canonical_ids)+algorithm_id+algorithm_version+corpus_manifest_sha)`（B S0-4 已写），并要求 algorithm_id/params_hash/corpus id 进簇记录；A 式 μ/β 保留，B 的 id 并入。
- **严重度**：G6 依赖项 ⇒ **P1（S0 冻结前补条款；实现可 S2）**。

### P2 清单（可冻结但后续场次必须补/澄清）

1. **P2-1（A/B）一跳方向 `dir(D)`**：A 定义了 `dir(D)` 但未给出现有 edge（contain/reference/extend）的方向语义与默认值；B 的形式化暂按无向（source∨target）。需 S1/S4 明确 directed/undirected 及 contain 是否双向；S0 建议先写"默认无向、方向由维度声明"，避免两种实现都合规。
2. **P2-2（A）更深层（句/概念）的登记位置**：A 说"更深层作为开放槽位"（A L90），但 U-25 的槽位是**维度**槽位；层次槽位需单独登记表/字段，否则"预留"会变成不实现。
3. **P2-3（A）S0-9 事件集把 `modeToggle`/`navigateBack`/`breadcrumbClick` 放进渲染后端契约**：这些是导航状态机（S5）事件，不应由渲染器拥有；建议 ViewModel/事件只保留渲染相关（nodeClick/clusterExpand/edgeClick/hover），导航事件由 S5 定义、渲染器转发。
4. **P2-4（A）S0-11 #9 的证据表述**："渲染器直接读 KB/取数（`app.js` 直连 `get_graph_data`）"——`app.js` 是 UI shell，不是渲染后端；`graph-engine.js`/`graph-view-2d.js` 并不调用 get_graph_data（A 级代码事实）。应改为"UI shell 直接取数、渲染器吃 payload"或明确"未来 ViewModel 构建层负责取数"；避免把架构层次说错。
5. **P2-5（A）S0-10 "agent 可设计/执行检索与取景"**：需明确取景结果是**确定性服务**生成，agent 只能提供参数/算法，不得直接改 view state/渲染器（B 已写）；否则与 S0-9 "渲染器不取数"和审计冲突。
6. **P2-6（A）S0-12 映射缺 `present`/`semantic_edges`/`view model` 三段**：A 的映射对现有术语覆盖更广，但没有把"数据 payload→ViewModel→Renderer"的边界映射到 `get_graph_data`/`graph-engine`/`graph-view-2d`；B 有该三段，建议合并。
7. **P2-7（A）S0-6 的 `unknown` 状态**：A 的边状态枚举含 `unknown`（A L211），需定义何时 unknown（未计算/不可判定）与 UI 如何区分 absent；否则 `unknown` 会被消费者当 absent（SE 校核 E-4 同指）。
8. **P2-8（B 自身）**：B 的 S0-1 判据未覆盖"谓词可命名"（T1），S0-4 未给 μ/β 具体阈值（留 S2），S0-9 事件集少于 A（缺 capabilities/edgeClick 细节）；B 应吸收 A 的 T1、capabilities 与 edgeClick。
9. **P2-9（A/B）开放槽位无数据载体**：需要 S1 定义 `dimension_registry` 的存储/校验（A 的槽位模板好，但无载体则"预留=不实现"）；SE 校核 E-10 同指。
10. **P2-10（A）S0-1 的"8 条退化 contain"**：A 引用 G4 8 退化边作 B 级证据；建议在 S0 冻结稿中写明其证据身份（G4 v3 sha/产物路径），否则跨轮不可复算。

---

## 2. 五个点名审查项的明确回答

1. **「最小粒度=知识点」是否被写成可机检约束？**
   A：**形式化有，机检无**（Π_L={{k}} 是数学定义，S0 未给断言对象/命令/失败语义）；B 同样只给定义。→ **P1-1**；建议补 S0-2 机检伪代码（叶子 kind=kp、叶子 id 集合=K、无 cluster 叶子；聚类输出成员并集=K 且同视图族互斥），并可先在 ViewModel 上做断言（现有 collector 节点字段可支持 A 级检查）。
2. **「边存无/类型」是否被误写成"数据有边就渲染"？**
   A 的默认视图**没有**误写（S0-6 明确视图相对、状态枚举），但 **full_expand 豁免区**（A L223/L274 "显示全部数据边"）重新引入该旧假设；且无 `present(e,ctx_full)` 机检。→ **P1-2**；B 已用 present+标签约束。
3. **2D/3D 是否被拆成两条设计线？**
   A **没有**（S0-9 明确单一 ViewModel、2D/3D 后端、事件统一；并给出现有 2D/3D 事件字段不一致的 A 级证据——我核对 `graph-view-2d.js:544-547` 有 edge_id、`graph-view-3d.js:1042-1044` 无 edge_id，属实）。**判定：A 在方向上 PASS**；但缺"2D/3D 同 ViewModel 同 id 集"的验收机检（P2-3/P2-4），建议加契约测试。
4. **多归属是否区分「成员关系 vs 视图出现」？**
   A：**区分得最好**（M⊆K×Cluster×Role、M⇏A/A⇏M、reason 集；A L240-258）；B 也有同二分（B S0-7）。但 A 的"层内 π_l 单归属"可能收窄 U-21 的同层多子图归属，且 membership 实体/持久化未定义（留 S6）。→ **P1-1（与 S0-2 合并处理）**。
5. **「默认替代 + 全展开开关」是否形成双主线/双真相？**
   A 的 S0-8 明确同数据源/同 ViewModel/模式枚举，**方向 PASS**；但 full_expand 用"全部数据边"绕过 `present()`、且无"同一 builder/同源"的机检 ⇒ 仍有**双真相风险**（P1-2）。B 的"同 DataSource+同 Renderer + present 参数"更强；建议 A 采用。

---

## 3. 最严重 3 条（给 Lead 的裁决顺序）

1. **P0-1 U-10 关联维度被窄化**：A 的 S0-5 "关联维度只走语义边" 与 U-10 原话（包含关系、引用、语义关联都显示）冲突；A 必须改成 `E_relation(D)`（contain/reference/semantic 均计跳，语义标签分离）。**不修不得冻结**。
2. **P0-2 `kind=bridge` 第三节点类型**：A 的 ViewModel kind 与 U-19（一跳节点只能是 KP/簇节点）冲突；改为 `kind{kp,cluster}` + `role=bridge`（或 edge state `bridge_only`）。
3. **P1-1 最小粒度不可机检 + 层内划分 vs U-21 多归属**：需 Lead 裁决"层内划分"的粒度（(level,dimension) 视图族 vs 全局 K）并补 S0-2 机检伪代码；否则 S2/G6 必返工。

> 另：P1-2（full_expand 数据边豁免）、P1-3（T3 不可操作）、P1-4（cluster id）建议同轮一并裁；P2 清单可入后续场次。

---

## 4. 差异证据强弱与"更可工程化"结论（给 Lead 并集）

| 维度 | A 更强 | B 更强 | 建议 |
|---|---|---|---|
| 概念严密 | S0-1 T1–T4、S0-2 划分、S0-6 状态枚举、S0-12 映射/回滚 | S0-1 字段判据、S0-4 stable id、S0-5 U-10 关系源（已修）、S0-9 kind 约束、DataSource→ViewModel→Renderer 三段 | 按上表逐项取强者，**不整份择优** |
| 证据 | A 有 `S0-evidence-A.md` + 2D/3D/app.js file:line；我抽查 `graph-groups.js` 确为 UnionFind 闭包、2D/3D 事件不一致属实 | B 代码证据较窄但均复核；U-10 修正来自原话 | A 证据覆盖更广，但 P2-4 的"渲染器读 KB"表述需改 |
| 可工程化 | S0-2 划分（若修多归属）、S0-6 状态枚举、S0-9 capabilities/事件 | S0-5 的 U-10 关系源、S0-7 no-single-parent、S0-9 kind 约束、S0-12 三段 | 合并后需 SE 校核（`S0-engineering-review.md`）逐条核 |

**独立复核结论**：**A 当前不能直接冻结**（P0-1/P0-2 + P1-1 阻断），B 亦需按 R1/自认弱点补强；建议 Lead 在并集裁决前先裁上述 3 条最严重项，并把 P0/P1 修复写入冻结候选 `S0-terms.md` 的对应条款。A/B 差异已逐项列出，未静默合并。

---

> 本文件未 commit；未改产品代码/契约/用户库；只读复核 + 写本目录交付物。
