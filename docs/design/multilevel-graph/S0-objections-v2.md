# S0 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S0-RULINGS.md`（sha `078363aa…`）。
> **对象**：`S0-terms-proposal-A-v2.md`（主办研究，sha **`5b3562e2aa5fc609b211637d165b10dd6ac039ea0a9c5fd4180325f893ac0746`**，47,430 B）；`S0-terms-proposal-B-v2.md`（本复核方，sha **`dd713707aa5e4b07d317e97eb2e492f9de4700e39e15e8cc586d1f4bf137832a`**，33,979 B）。
> **独立性**：B-v2 于 17:11 落盘，A-v2 17:12:52 才出现；B-v2 写作时未读 A-v2；下方差异为落盘后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=契约/文档推断；PI=本项目假设；R=RULINGS 已裁。

---

## 0. RULINGS 关闭矩阵（P0/P1/D/SE 项）

| RULINGS 项 | A-v2 落位 | B-v2 落位 | 判定 |
|---|---|---|---|
| P0-1 关联维度 `E_sem`→`E_relation`（U-10） | §3/§5（L159-276 区）；关系源含 contain 两 kind/reference/semantic extend，label 仅标签 | S0-3/S0-5：`E_relation(D)`；关系源同；label 仅标签 | **关闭** |
| P0-2 `kind` 两类；bridge=role/state | §9（L401-446）：kind∈{kp,cluster}；bridge→role/edge state | S0-9：kind∈{kp,cluster}；role/state bridge | **关闭** |
| P1-1 S0-2 partition 作用域 + 机检伪代码 | §2（L96-158）：`(level,view_family)` + V1–V6 + fail-closed | S0-2：同作用域 + 四断+递归 expand+fail | **关闭**（两版伪代码细节差异见 §1） |
| P1-2 full_expand 也走 present | §6/§8：ctx_full+present；禁 all_data_edges | S0-6/S0-8：ctx_full+present；无 all_data_edges | **关闭** |
| P1-3 T3 降级 | §1：T3→C-1..C-4 消费者准入 | S0-1：T3 消费准入，不作定义 | **关闭** |
| P1-4/D-2 cluster 身份 | §4：run_id+local_id+cluster_key；禁内容哈希主引用 | S0-4：run_id+local_seq+cluster_key；同禁令 | **关闭** |
| D-1 partition 作用域 | §2/§4/§7：同族内划分、跨族多归属 | S0-2/S0-4/S0-7：同 | **关闭** |
| D-2 cluster 身份 | §4 + §15.2（规范化细节待裁） | S0-4 + S2/S6（细节待裁） | **关闭（细节见 §2）** |
| D-3 不写产品 sidecar/新段 | §7/§11 #14/§12 红线⑥ | S0-4/S0-7/S0-11 #12 | **关闭** |
| D-4 ViewModel 纯度 | §9：移出 mode/面包屑/导航；但 `capabilities` 仍在 ViewModel（见 §3 P2-1） | S0-9：移出 mode/focus；**capabilities 已移到 Renderer.getCapabilities()**（B 自修） | **关闭，A 有残余（P2）** |
| D-5 v1 单维度激活 | §3：同视图一 active 维度 | S0-3：同 | **关闭** |
| SE S0-6：ctx+presence 三值+rule_id | §6：presence 三值+rule_id+渲染集合恒等式 | S0-6：presence 三值+rule_id+状态枚举映射 | **关闭** |

**结论**：RULINGS 的 P0-1/P0-2/P1-1..P1-4、D-1..D-5、SE S0-6 两版均已关闭；**无 P0**。剩 P1/P2 为冻结前需再裁/SE 机检的细节（§2/§3）。

---

## 1. A-v2 与 B-v2 逐项差异（A/B 编号、证据强弱、可工程化判断）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S0-1 语义 | T1/T2/T4 + `G_sem`（asserted / semantic contain 需 derived_by=author+assertion_source+curated_by·at）；T3→C-1..C-4 | 同集合；B 自修补 derived_by=author；T3 消费准入更简 | **A 更强**（C-1..C-4 更细）；B 已对齐字段；建议 B 吸收 C-1..C-4 文案。证据：A-v2 §1（L46-95）；B S0-1；`edge_derivation.py:812-859`（A）。 |
| S0-2 层次 | 划分 Π_{ℓ,f}；V1–V6 伪代码；`view_family=⟨family_id,basis,level_chain⟩` | 同 partition 作用域；四断+递归 expand+fail；`ViewFamily = 同一 (level,dimension)` | **作用域定义不同**（A 的 family 含 level_chain；B 把 (level,dimension) 当 family）；伪代码 B 的递归展开更强、A 的 V5 直接 `cluster.members` 可能漏嵌套。建议统一定义（见 §2-2）；合并 A 的 K_f 覆盖语义 + B 的递归/fail。证据：A-v2 §2（L96-158）；B S0-2。 |
| S0-3 维度 | status {reserved,specified,frozen,deprecated}；未知 id fail-closed；graphStyle/2D/3D 显式排除；槽位模板 | status {active,reserved}；reserved 不得进渲染分支；E_relation(D) | A 的状态机/排除更完整；B 更简洁。建议 B 吸收 A 的 status/unknown fail-closed。证据：A-v2 §3；B S0-3。 |
| S0-4 簇 | μ/β + D-2（run+local_id+key）；partition 视图族内；附录身份 | μ/β + D-2（run+local_seq+key）；`cluster_key` 同公式；成员可展开 | 基本一致；A 多了 μ/β 的边界说明；B 的 `cluster_key` 编码表述略简。**并集**；cluster_key 规范化细节两版都留（见 §2/§3）。证据：A-v2 §4；B S0-4。 |
| S0-5 一跳 | `E_relation(D)` + `dir(D) ∈ {out,in,both,hierarchy_down}` + rendered-hop + `underlying_hop_count` + 跨维不计跳 | 同 E_relation；B 已补 `dir(D)` 同枚举（并集 A）；缺 `underlying_hop_count` | A 更完整（underlying_hop_count）；B 应补；方向枚举已对齐。证据：A-v2 §5；B S0-5。 |
| S0-6 存无/类型 | ctx+presence 三值+rule_id；候选集 C(ctx)=type∈relation_sources；全展开 present；effective_type | 同；另定义边状态到 presence/rule 的映射；聚合边 `data_edge_ids` | **B 在聚合边身份上更强**；A 在 rule_id 示例/候选集定义更明确；合并 A 的 rule 枚举 + B 的 data_edge_ids。证据：A-v2 §6；B S0-6/S0-8/S0-9。 |
| S0-7 多归属 | Membership 实体 ⟨kp,cluster_instance,level?,dimension?,role,weight,source,provenance⟩；同族单归属/跨族多；无单 parent | membership 多对多 + role/provenance + no single parent + D-3 | A 字段更细（weight/source）；B 的 D-3 表述更硬。并集；A 的 Membership 实体可作为 S6 输入。证据：A-v2 §7；B S0-7。 |
| S0-8 默认/全展开 | 三段同源；DataSource 身份三元组；子集 `shown(default)⊆shown(full)⊆DataSource.edges`；焦点保持/映射 | 同三段；B 补 `expand_data_edges` 投影（聚合边 `data_edge_ids`）；焦点映射 | **B 的子集断言更可工程**（解决聚合边伪造子集）；A 缺聚合映射（见 §2-3）。A 的 DataSource 三元组更具体；合并。证据：A-v2 §8；B S0-8。 |
| S0-9 渲染接口 | ViewModel context{level,dimension}+nodes roles+edges presence+`capabilities{can_expand,supports_2d?,supports_3d?}`；事件 nodeClick/edgeClick/backgroundClick | ViewModel 纯数据+kind 约束+`data_edge_ids`；**capabilities 移到 Renderer.getCapabilities()**；事件 nodeClick/edgeClick/hover/clusterExpand | **B 的 D-4 纯度更强**（A 的 capabilities 仍在 VM，P2）；**A 的事件集有 backgroundClick，B 有 hover/clusterExpand——两版各缺**，合并全集。证据：A-v2 §9；B S0-9。 |
| S0-10 agent | 三层角色 + 确定性 frame() + 能力 allowlist/denylist | 三层 + 确定性服务 + 不得直接改渲染状态；B 的 allowlist 较简 | **A 更强**（allowlist/denylist 可机检）；B 的吸收 A 的显式清单。证据：A-v2 §10；B S0-10。 |
| S0-11 不做 | 15 条 + 执行点 | 16 条 + 执行点（含 v1 单维度、D-3/D-4） | 并集约 17 条：A 的 15 条 + B 的 #16（v1 单维度）；确认无冲突。证据：A-v2 §11；B S0-11。 |
| S0-12 映射 | 16 组 + 7 红线 + 迁移/回滚 | 19 行 + 5 红线 + 三段/present/semantic_edges | **A 的旧术语覆盖更广；B 的三段/present 映射更细**；合并为一份映射，冲突红线取并集。证据：A-v2 §12；B S0-12。 |

**总判断**：A-v2 在状态机/槽位/成员实体/agent allowlist/术语覆盖上更完整；B-v2 在（a）聚合边身份与子集投影、（b）ViewModel 纯度（capabilities 外置）、（c）递归 partition 机检、（d）`E_relation` 最小集表述上更可工程化。**不建议整份择优**；按上表并集，重点修 A 的 §2-3 与 §3 P2-1，B 吸收 A 的 §5/§9/§10 细节。

---

## 2. 我认为仍未解决的 3 点（按重要性；建议 Lead 在冻结前裁）

### 2-1（P1）`E_relation(D)` 的**最小冻结边源集**仍被推给 S1，P0-1 可能复发

- **现状**：A-v2 §15.1 明确"`E_relation(A)` 的冻结边源清单……'semantic extend'的判定边界需 S1 冻结；S0 只定关系源类别"；B-v2 S0-3 也把 `E_relation(D)` 写成 U-10 类别（contain/reference/semantic extend 等），未写"最小 inclusive 集不可删"。
- **风险**：P0-1 的根因是 U-10 覆盖；若 S1 再把 `reference`/`structural contain` 从 relation_sources 裁掉（以"语义只有 semantic"为名），P0-1 在下一场复发。S0 冻结稿应冻结**最小 inclusive 集**：`{contain(structural|semantic), reference, extend}` 全部进入 `E_relation(D)`（标签 semantic/navigation/structural 另定）；S1 只能**新增/细化**，不能删除该最小集，除非 Lead 重裁。
- **修复**：在 `S0-terms-v1` 的 S0-3/S0-5 写"minimal relation source set = …；删除项需重开 S0"；B-v2 建议加一行 `E_relation_min` 字段。
- **证据**：U-10（vision L27/L47）；RULINGS P0-1（L14）；A-v2 §15.1（L632-634）；B-v2 S0-3。

### 2-2（P1）`view_family` 定义不一致 → partition 作用域两义

- **现状**：A-v2 `view_family=⟨family_id,basis,level_chain⟩`（S0-2），partition 是"同一 (level, view_family)"；B-v2 把 `ViewFamily = 同一 (level,dimension) 下的视图族`（S0-2/S0-3）。同一句 "同一 (level, view_family)" 在两版指向不同对象：A 的 family 本身含 level_chain，B 的 family 是 level 内的取景族。
- **风险**：S0 冻结后 S2 聚类/S6 存储会按字面实现；两义会导致"同族单归属"边界漂移（一类实现允许同层跨维度多归属，另一类不允许）。
- **修复**：冻结 `view_family = ⟨family_id, basis, dimension_id, level_chain⟩`（A 的字段 + B 的维度绑定），并明确 partition 的断言对象是 `(level, family_id)` 的**块集合**；S0-7 的"同族单归属、跨族多归属"随之唯一化。
- **证据**：A-v2 §2（L100-108）、§7；B-v2 S0-2/S0-7；RULINGS D-1（L45）。

### 2-3（P1，A-v2 需修）聚合/折叠边的身份与 `default ⊆ full` 子集断言

- **现状**：A-v2 S0-8 写 `shown(default) ⊆ shown(full) ⊆ DataSource.edges`；但默认视图的簇/折叠边可能是**聚合边**（不是 DataSource 的原始 edge id），A-v2 的 ViewModel edges 没有 `data_edge_ids` 映射。这样"子集"断言在工程上不可执行（聚合边 id 不在 DataSource.edges），甚至可能把聚合边当"数据边"伪造语义。
- **修复（B-v2 已实现）**：ViewModel 聚合边必须带 `data_edge_ids[]`；子集断言改为在 `expand_data_edges(VM)` 上做（B-v2 S0-8/S0-9）；A-v2 S0-8/S0-9 照此补，否则 M-8 机检无法写。
- **证据**：A-v2 §8（L361-400）无 data_edge_ids；B-v2 S0-8 子集投影 + S0-9 edges 字段；SE M-8（`S0-engineering-review.md:295`）。

> 另两个次重要未决：**cluster_key canonical 序列化 + 成员变后 curation 迁移策略**（A §15.2/B S2；D-2 只给公式骨架）；**full_expand 的 suppressed/unknown 允许性与候选全集**（A §15.3/B S4）。建议一并写入 S0 冻结稿的"待 S2/S4 但不阻塞冻结"清单。

---

## 3. 其余 P1/P2（不阻塞，但应在冻结前落位）

| # | 项 | 异议/证据 | 可行动修复 |
|---|---|---|---|
| P2-1 | A-v2 ViewModel `capabilities{can_expand,supports_2d?,supports_3d?}` 仍在 ViewModel（§9） | D-4 要求 ViewModel 纯数据；supports_2d/3d 是后端能力，can_expand 是节点属性/导航能力 | 移出到 `Renderer.getCapabilities()`；节点用 `expandable`（B-v2 已这样） |
| P2-2 | A-v2 `dir(D)` 的 `hierarchy_down` 未给语义（§5） | 方向枚举无定义会导致两实现（父→子/子→父）都合规 | 在 S0-5 写每枚举定义；S1 冻结每维度取值（B-v2 已补 out/in/both/hierarchy_down 定义） |
| P2-3 | A-v2 S0-2 V5 用 `cluster.members` 直接拼块，未定义嵌套 cluster/expandable 的递归语义（§2） | 若 ViewModel 允许 cluster 成员含 cluster，V5 会把同族同层判错/漏判 | 采用 B-v2 的 `expand_cluster_to_kp` 递归 + `expandable`/fail（或明确 ViewModel 只允许单层块） |
| P2-4 | 事件清单差异：A-v2 `{nodeClick,edgeClick,backgroundClick}`；B-v2 `{nodeClick,edgeClick,hover,clusterExpand}` | 两版各缺对方事件；2D/3D 同 id 集验收需要全集 | 合并为 `{nodeClick,edgeClick,hover,clusterExpand,backgroundClick}`（navigation 事件仍归 S5） |
| P2-5 | B-v2 缺 A-v2 的 `underlying_hop_count`/rendered-hop（§5） | 折叠簇的一跳需要区分 rendered hop 与 underlying hop（SE M-5） | B-v2 补 `underlying_hop_count` 字段/说明；或 S4 明确 |
| P2-6 | cluster_key 规范化（分隔符/编码/params_hash 算法）与 curation 迁移（A §15.2） | D-2 只给公式骨架；成员变化后旧 curation 引用迁移/失效未定 | S0 冻结稿写"canonical JSON(sorted ids)+algorithm_id+version+params_hash"与迁移/重确认规则；S2/S6 实现 |
| P2-7 | full_expand 的 suppressed/unknown 允许性与候选全集（A §15.3） | full 是否允许 unknown/suppressed、候选是否严格=DataSource.edges，影响 U-27 一致性 | S0 写 `C(ctx_full)=DataSource.edges`、允许 suppressed/unknown 但 must rule_id，full 不等于 semantic |
| P2-8 | A-v2 cluster_key 公式用字符串拼接（`sorted(members)+algorithm+version+params_hash`），B-v2 同 | 分隔符/Unicode/排序规范化未定义，可能不同实现不同 key | 冻结 canonical serialization（JSON + UTF-8 + 排序）；S2/S6 |

---

## 4. 结论

- **RULINGS 关闭项**：P0-1/P0-2/P1-1..P1-4、D-1..D-5、SE S0-6 **两版均已关闭，无 P0**；B-v2 可作为 S0 冻结候选的独立复核主干之一。
- **A-v2 剩余必修**：2-3（聚合边 `data_edge_ids`/子集断言）、P2-1（capabilities 外置）；建议接受 B-v2 的这两个修法。
- **S0 冻结前需 Lead 裁决的 3 个未决**：2-1（E_relation 最小集不可删）、2-2（view_family 唯一定义）、2-3（聚合边身份）。
- B-v2 与 A-v2 的差异已逐项列出，未静默合并；B-v2 已吸收 A 的 μ/β、边状态枚举、术语映射、T1/T2/T4 与 dir 枚举，但保留独立判断（B 更强的 D-4 纯度、聚合边身份、递归机检、E_relation 最小集表述）。

> 未写产品代码/契约；未 commit；只写 B-v2/objections-v2 两份交付物。
