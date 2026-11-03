# S1 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S1-RULINGS.md`（sha `6b2b84bb…`，R-S1-1..R-S1-8）。
> **对象**：`S1-dimensions-proposal-A-v2.md`（主办研究，sha **`ae5f09e5cd159b915be0fce64a14bf0eb95aa672986609bcb5bd2f5e3bd76d03`**，44,080 B）与 `S1-dimensions-proposal-B-v2.md`（本复核方，sha **`c4cddcafd5922fa13fee4542133db3567623856facd960e0f1644e3e16994053`**，32,623 B）。
> **独立性**：B-v2 于 18:55:22 落盘，A-v2 18:56:50 才出现；B-v2 写作时未读 A-v2；下方为落盘后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S1-RULINGS/S0 冻结。

---

## 0. R-S1 关闭矩阵（修订轮）

| 裁决 | A-v2 落位 | B-v2 落位 | 判定 |
|---|---|---|---|
| R-S1-1 H 不参与关系扩展；`H.relation_sources=[]`；R-1 只约束 relation_expansion | S1-1/S1-2/S1-4：kind 分类；H=[]；validator 只对 A 断言 min | S1-1/S1-2/S1-4：kind；H=[]；validator 只对 A 断言 min | **关闭** |
| R-S1-2 H 无 hop；S0-5 只约束 A | S1-2/S1-4/S1-7：H `hop_unit=n/a`、hop null；S0-5 仅 A | S1-2/S1-4/S1-7：H `n/a`、null；仅 A | **关闭** |
| R-S1-3 registry_history append-only + 跨版本只增 + `S0_REOPEN_REQUIRED` | S1-2/S1-6：history 链 + `source_union(new)⊇old` + 删除硬失败 | S1-6：history schema（含 relation_sources/active_dimensions）+ 跨版本断言 + 删除硬失败 | **关闭**（A/B 历史存储形态不同，见 §1/§2） |
| R-S1-4 H 派生边 `data_edge_ids` | S1-4/S1-12：强制 data_edge_ids + 映射 contain(structural) | S1-4/S1-12：同 | **关闭** |
| R-S1-5 A hop 1/2、方向、终止；H 无 hop | S1-5/S1-7/S1-8/S1-9：A 1/2、both、终止；H n/a | 同 | **关闭** |
| R-S1-6 三态/deprecated→active/插件禁入/fallback 审计 | S1-11/S1-14：三态、重开、fallback 显式+审计、插件禁写 | 同 | **关闭** |
| R-S1-7 候选 7 个；density→S2；similarity 走 S1-6 | S1-15：7 候选；density 排除；similarity derived | 同 | **关闭** |
| R-S1-8 B 吸收 A 的 hop_unit/registry_sha/active set/H/状态机 | A 自身已具备 | B-v2 已补 hop_unit/registry_sha/active set/kind/H/状态机 | **关闭**（B 仍缺 A 的 M1–M6 标签、history 内嵌，见 §3） |

**结论**：R-S1-1..8 两版均已关闭，**无 P0**。剩余是历史存储形态、显式「新一跳」入口、H 派生边显示等未决细节（§2）。

---

## 1. A-v2 / B-v2 逐项差异（S1-1..S1-15；差异 + 独立判断）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S1-1 | M1–M6 判定 + `kind ∈ {hierarchy_navigation, relation_expansion}` + basis 匹配 | 定义 + M1–M6 语义（未标 M1–M6 编号）+ 排除清单；B-v2 已补 kind | **A 更强**（编号判据+类别明确）；B 应补 M1–M6 编号/kind-basis 机检文案。 |
| S1-2 | schema v2，`history` **内嵌** registry；kind/basis/ hop_unit/registry_sha/active set；H hop=null | schema v2，`registry_sha`/kind/hop_unit/active set；`registry_history` 在 S1-6 **单独定义**；H hop=null | 两版等价；**A 内嵌 history 更一体**；**B 单独 history 更清晰**但 registry 未引用/校验 history（P2-1）。A 的 history 只存 version/sha/previous/decision_id，**不含每版 relation_sources**；跨版本校验需外部 `previous_registry`（P2-2）。 |
| S1-3 | reserved 格式含 kind/basis reserved/draft/why_not_v1；R1–R6 | reserved 格式含 draft/why_not_v1；四要件；v2 未含 kind 草案 | A 更细（kind/R6 similarity/density 明确）；B 可吸收 A 的 R6。 |
| S1-4 | H 不参与关系扩展；无 hop；派生边 data_edge_ids；**H 不渲染 reference/extend 邻居**；边界更全 | 同核心（H=[]/n/a/data_edge_ids）；H 无关系扩展；边界较少 | 两版等价；A 更明确"不显示 context 邻居"（解决 P1-1）；B 表述较简。 |
| S1-5 | A hop_default=1/hop_max=2；2 跳仅显式「新一跳」；最短+去重+跨维重置 | 同；B-v2 明确 new_hop 请求字段 | 等价；B 的 `new_hop` 请求参数更可机检；A 的 S5 入口待定（§2-2）。 |
| S1-6 | 历史链 `source_union(new)⊇old`；删除/改名 `S0_REOPEN_REQUIRED`；classification E1–E7 | history schema（entries 含 relation_sources/active_dimensions/decided_by）+ 跨版本断言 + 删除硬失败 | **B 的 history 条目自带 sources，历史可独立复算**；A 的 history 只存 content_sha，需外部旧 registry（P2-2）。A 的分类 E1–E7 更完整。**并集**：A 的分类 + B 的历史自包含。 |
| S1-7 | H 无 hop；A 1/2；终止规则详细 | 同核心；B-v2 已修正 H null | 等价；A 更细（H 下钻由 S5 连续 frame）。 |
| S1-8 | 5 枚举 `down/up/both/out/in`；H=down/A=both；up 保留 | 同 5 枚举；H/A 同 | 一致。 |
| S1-9 | A/H 终止；max_nodes 字段、数值 S8；rule_id | 同；B 的 termination 规则稍简 | 等价；A 更细（H leaf/cancel）。 |
| S1-10 | 单维度 + `DIM_COMBINATION_UNSUPPORTED` + 切换语义 | 同；B 的组合槽位字段稍简 | 等价；A 更细（错误码/切换）。 |
| S1-11 | 三态 + deprecated→active 需 S1 重开/version/history；插件禁写 | 同三态 + 重开 + 插件禁写；B 的 fallback/registry 描述较简 | 等价；A 更细（C-5 映射/旧 frame edition）。 |
| S1-12 | H 派生边 data_edge_ids；A 候选；presence/rule_id；类型不变 | 同；B 稍简 | 等价；A 更细（H 不产生 E_relation 邻居）。 |
| S1-13 | 切换 Presentation/S5；VM 只 dimension_id；H 下钻导航动作 | 同；B 稍简 | 等价；A 更细（S5 push_nav_frame）。 |
| S1-14 | frame 纯函数 + fallback 显式/审计 + registry fallback_policy 可禁 | 同；B 的 fallback 字段/审计同样明确 | 等价；A 稍细（错误码/审计字段）。 |
| S1-15 | 7 候选；density→S2；similarity 两步晋升 | 7 候选；同；B 的 why_not_v1 稍简 | 一致；A 更细（similarity/path 草案）。 |

**总判断**：两版在 R-S1 核心上已收敛；A-v2 在 M1–M6、历史/内嵌、分类 E1–E7、H 细节、状态机/agent 细节上更完整；B-v2 在 **history 条目自包含（可独立复算）**、`new_hop` 请求字段、H null 无 hop 上更可机检。建议并集：A 的 M1–M6/分类/E1–E7/H 细节 + B 的 history 条目字段/new_hop/registry 引用。

---

## 2. 仍未解决的 3 点（建议 Lead/SE 在冻结前裁）

### 2-1（P2→P1 边缘）`registry_history` 的存储位置/不可篡改性与跨版本可复算

- **现状**：R-S1-3 要求 history append-only 且跨版本只增。A-v2 把 history **内嵌** registry，条目只有 `version/content_sha256/previous_sha256/decision_id`，**不含该版 relation_sources**；validator 需要外部 `previous_registry` 才能比较（A-v2 S1-2 `validate_registry(reg, previous_registry=None)`）。B-v2 的 history 条目含 `relation_sources/active_dimensions`，但 history 作为 S1-6 的独立 schema，**registry 本身没有引用/校验它**，存储位置/是否随 registry 提交仍未定义。A-v2 §18.3 自己把"存储位置/签名"列为待裁。
- **风险**：若 history 内容可由任意人重写（无不可变存储/签名），"只增不删"仍不可审计；A 的 history 无每版源列表，若旧 registry 文件未保留（只有 sha），无法证明 `new⊇old`。
- **修复**：冻结 history 存储为**只追加文件/不可变对象**（内容 sha 作 id；旧版按 content_sha 可取）；每版条目至少含 `relation_sources/active_dimensions`（B 已写，A 补）；registry 引用 `history_ref` 且 `history[-1].content_sha == registry_sha`；validator 不需要外部传入旧 registry 即可复算；删除/改名 ⇒ `S0_REOPEN_REQUIRED`；记录 decision id。
- **证据**：R-S1-3（`S1-RULINGS.md:33-38`）；A-v2 §2/§18.3；B-v2 S1-6。

### 2-2（P1）A 的 `hop_max=2`「显式新一跳」缺少 S5 动作/机检入口

- **现状**：R-S1-5 规定 A `hop_default=1/hop_max=2`，2 跳仅在用户显式「新一跳」时使用（U-22）。A-v2 S1-5/S1-7 只在数据语义层写"显式新一跳"；S1-13 说"切换维度/下钻属 S5"，但 **S5 的「新一跳」动作/事件/状态未定义**（A-v2 §18.2 自列待裁）。B-v2 S1-14 有 `new_hop` 请求字段（agent 侧），但用户 UI 的显式动作仍未定义。
- **风险**：没有唯一入口时，实现可默认 2 跳（违反默认 1）或 UI 无入口（hop=2 永远不可达）；机检只能检查请求字段，不能检查"用户显式"。
- **修复**：S1 冻结"唯一触发路径"：S5 状态机增加 `explicitNewHop` 动作（事件/守卫/副作用），只有该动作把 `hop_budget=2`；`present`/frame 检查 `new_hop=true` 才允许 2；默认/自动路径禁止 2；S1 明确该动作由 S5 定义、S1 只冻结语义。
- **证据**：R-S1-5（`S1-RULINGS.md:43-47`）；A-v2 §18.2；B-v2 S1-14 `new_hop`；S0-5/U-22。

### 2-3（P2）H 派生边的 canonical id/显示映射与 `data_edge_ids` 的折叠语义

- **现状**：R-S1-4 要求 H 边带 `data_edge_ids` 映射 contain(structural)。A-v2/B-v2 都写"H 派生边 → data_edge_ids"，但 **H 派生边自身的 canonical id/去重键**、一个块→子块边对应**多条** contain 数据边时的 `data_edge_ids` 折叠/显示计数、以及 `expand_data_edges(H_vm) ⊆ DataSource.edges` 的机检签名均未冻结（A-v2 §18.1 把显示类型交 S3/S4；B 同样留）。
- **风险**：不同实现可能把同一块对拆成多条 H 边或合并成一条但 data_edge_ids 不同；S0-8 的 default⊆full 投影与 G6 快照需要稳定 H 边 id；R-3 机检需要明确 `data_edge_ids` 是"全部成员 contain 边"还是"代表边"。
- **修复**：S1 冻结 H 派生边 `id = hash(parent_cluster_id + child_cluster_id + level/view_family)` 或 `(parent,child)` 元组；`data_edge_ids = 所有成员 contain(structural) 数据边`（去重、排序、可枚举）；显示计数/类型由 S3 决定但不得改 id；`expand_data_edges` 按全集投影；机检给出签名。
- **证据**：R-S1-4；S0 R-3/S0-8；A-v2 §18.1；B-v2 S1-4/S1-12。

> 另：A-v2/B-v2 对 **deprecated 旧 frame 读取**（A §18.4：旧 registry edition 解释 vs 重建）、**similarity/path 两步晋升**（A §18.5）仍留 S6/S9；可列入"后续场次不阻塞"。

---

## 3. 其余 P1/P2（对 A/B 两版的独立判断）

| # | 项 | 判断/证据 | 修复 |
|---|---|---|---|
| P2-1 | B-v2 的 registry schema 未引用/校验 S1-6 的 history | B registry 有 `registry_sha`，但 schema 无 `history_ref`；跨版本校验依赖 S1-6 外部文件 | B 在 registry 加 `history_ref`/`history[-1]` 校验，或把 history 内嵌（A 做法） |
| P2-2 | A-v2 的 history 条目缺每版 `relation_sources` | A history 只有 `content_sha/previous/decision_id`；无法从 history 单独复算 append-only（需旧 registry 文件） | A 的历史条目补 `relation_sources/active_dimensions`（B 已有） |
| P2-3 | B-v2 S1-1 未标 A 的 M1–M6 编号 | B 有定义/机检但无 M1–M6 标签；与 A 并集时应统一条款编号 | B 吸收 A 的 M1–M6 编号与 kind-basis 匹配机检 |
| P2-4 | A-v2 `kind` 与 `basis.kind` 双字段冗余 | 两版都有；若二者不一致，校验器需同时断言（A 已做；B 已做） | SE 决定只留一个 canonical 类别字段，另一个派生校验 |
| P2-5 | A-v2/B-v2 的 `max_nodes=200` 示例 | R-S1-5 说数值归 S8；示例值可能被实现抄死 | 文档标注"示例非规范"；S8 定值（A/B 均已注 A 有注，B 需补） |
| P2-6 | A/B 的 `deprecated` 旧 frame 读取 | A-v2 §18.4 未裁；B S1-11 只说 deprecated 不可新取景 | Lead/SE 定：旧 frame 按旧 registry edition 解释（不重建），S6 落存储 |
| P2-7 | similarity/path 晋升路径 | A/B 都写"两步"（S1-6 派生源 → S1 维度修订）；未写评测门槛 | S7/S9 补评测；S1 冻结"两步"流程 |
| P2-8 | B-v2 的 `registry_sha`/history 语义版本比较 | B 使用 `semver_gt` 占位；未定义 semver 比较（2.10 vs 2.9） | S1/S6 冻结 semver/版本比较；实现用 tuple 解析 |
| P2-9 | A/B 的 `H` 派生边 label | A 固定 structural；B 同；S3/S4 显示类型未定义 | S1 冻结 label=structural；显示映射 S3/S4 |
| P2-10 | A/B 的 `DIM_COMBINATION_UNSUPPORTED` 与切换语义 | A 有错误码/切换；B 有切换但错误码描述少 | 统一错误码/切换事件（S5） |

---

## 4. 点名审查项结论（S1 任务要求）

1. **A 维覆盖 U-10（包含/引用/语义关联）**：A-v2 S1-5/B-v2 S1-5 均 `⊇ E_relation_min`（contain 两 kind/reference/extend），**PASS**；R-S1-1 只把 H 排除，A 未被窄化。
2. **`E_relation` 只增不删可机检**：A-v2 有 history 链 + `source_union(new)⊇old` + `S0_REOPEN_REQUIRED`；B-v2 有含 sources 的 history + 断言；**方向 PASS**，但历史存储/旧内容可复算需按 §2-1 补才完全可审计。
3. **H/A 注册表 fail-closed**：A/B 均有未知/保留/弃用错误码、active 集合固定、H/A 分工；**PASS**（B 需补 registry-history 引用）。
4. **跳数/方向/终止可机检**：A：H n/a 无 hop、A 1/2、方向 5 枚举、终止有穷；B 同；**PASS**；A hop=2 的 S5 显式入口未定（§2-2）。
5. **维度是否被塞进 ViewModel**：A/B 均 VM 只带 dimension_id，无 mode/nav/history/capabilities；**PASS**。
6. **v1 单维度/组合槽位双真相**：A/B 均单 active + 组合 reserved + `DIM_COMBINATION_UNSUPPORTED`；**PASS**。
7. **reserved 是否偷偷实现**：A/B 均 reserved 不进渲染/ctx，v1 不晋升；**PASS**（需 CI grep）。

---

## 5. 结论

- R-S1-1..8 两版均关闭，**无 P0**；A-v2 与 B-v2 在核心语义上收敛，可进入 SE 工程校核/Lead 机检。
- **冻结前建议补**：§2-1 history 存储/每版 sources 可复算；§2-2 A 的显式「新一跳」S5 入口；§2-3 H 派生边 canonical id/`data_edge_ids` 折叠语义。
- A-v2 仍缺 per-version `relation_sources`（P2-2）；B-v2 仍缺 registry-history 引用/M1–M6 编号（P2-1/P2-3）；其余 P2 可后续场次。
- 未写产品代码/契约，未 commit；差异逐项列出，未静默合并。

> 参考锚：R-S1 `S1-RULINGS.md:21-62`；S0 冻结 `S0-terms-v1.md:35-41,49-61,75-107`；U-10/U-11/U-22/U-25/U-30/U-32；`ENGINEERING-PLAN.md:149-173,217,229-247,290,301-345`。
