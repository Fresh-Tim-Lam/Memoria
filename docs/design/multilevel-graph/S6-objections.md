# S6 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`、`S4-render-v1.md`（`2576f6c8…`）、`S5-nav-v1.md`（`7f4c4515…`），不得违反；`S6-charter.md`。
> **对象**：`S6-contract-proposal-A.md`（主办研究，sha **`af67ca9f2e2fb8a65a3271dd424468d2d40811cf1ce6880aec42d54332f79ebb`**，33,936 B）与 `S6-contract-proposal-B.md`（本复核方，sha **`f9eb5c13d2b4bbf3f3db9b99305ee353c8b529345e2bb0ac33fda3356780680e`**，19,422 B）。
> **独立性**：B 于 21:33:38 落盘，A 于 21:35:34 才出现；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S5 冻结。

---

## 0. A/B 差异总表（S6-1..S6-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S6-1 单一真源/ER | 实体分事实/配置/派生/视图/审计；FactSource 明确；D-3 | 同类实体但较简（无 DOCUMENT/KP_OCCURRENCE/EDGE_PROVENANCE 细分） | A 更细（ER 定稿输入）；B 需吸收 A 的事实实体粒度。 |
| S6-2 DataSource/GraphView | 字段表+失败码 `GRAPH_*`；EDGE canonical；C-* | 字段/只读/E_relation_min；失败码 `DS_*` | A 更细（失败码/GraphView/字段表）；B 的 `DS_*` 与 A 的统一 `GRAPH_*` 冲突（P2-2）。 |
| S6-3 registry/history | 字段/枚举/失败码；history content-addressed；**未给签名位置**（charter 要求） | history 自包含 + **可选 detached signature**；schema 较简 | A 字段更全；B 的签名可选方案补足 charter；两者需并集（P2-1）。 |
| S6-4 run/membership | `params_hash` 含 tau/cut/MANDATORY；CLUSTER 含 μ/β/label；五状态；curation | 公式/字段/五状态；CLUSTER 较简（无 μ/β/label） | A 更完整（μ/β/label/params）；B 需吸收。 |
| S6-5 VM/Visual | 字段表+`VISUAL_ENCODING_MAP`/`RendererCapabilities`；**VM_NODE role 只写 `"member"`** | VM 白名单+ADDENDUM；role∈{member,focus}；token map 较简 | A 的 token map 更强；**A role 字段与 S3 不符（P1-3）**；B role 对但 token map 弱。 |
| S6-6 Frame/presence | FRAME_SPEC **含 `frame_id`/`edition_sha`**；presence/MANDATORY/subset/失败码 | FRAME_SPEC 只 S4 输入字段；frame_id 派生；presence/rule_id/MANDATORY/失败码 | **关键差异**：A 把 `frame_id`/`edition_sha` 加进 S4 输入（P1-2），与 S4 冻结 frame_spec 不一致；B 更贴 S4/S5。 |
| S6-7 Nav | `GraphNavFrame` 用 **`nav_id`**；NAV_EVENT 21；T01–T30；持久化白名单 | 用 **`frame_id`**；T01–T29（B 表少 T30?） | **A 字段名与 S5 冻结 `frame_id` 不一致（P1-1）**；B 名称正确但表/事件需对齐 S5 30 组（B 需补）。 |
| S6-8 存储/审计/GC | `.memoria/config/graph`、`build/graph`、`audit/graph`；可重建 | `.memoria/cache/...`、audit/G6；可重建 | 核心一致；路径需 S6a 统一（P2-3）。 |
| S6-9 错误 | 单一 `GRAPH_*` 命名空间 + origin 表 | 多命名空间 `DS_/DIM_/S2_/S3_/S4_/S5_` | **A 更符合“统一命名空间”**；B 多命名空间可能违反 charter，应吸收 A（P2-2）。 |
| S6-10 兼容/迁移 | 旧 graph-groups 忽略、无破坏迁移、回滚删缓存 | 同 | 一致；A 更细（版本/EDITION）。 |
| S6-11 G6 | 字段/复跑/度量详细 | 字段/复跑较简 | A 更细；B 需补字段。 |
| S6-12 0.5 边界 | 做/不做/接口清单/验收 | 做/不做/依赖/验收 | 一致；A 更细（3D 预留/agent/迁移）。 |

**总判断**：A 在 ER 实体/字段表/token map/G6/0.5 边界上更强；B 在 frame_id/FRAME_SPEC 与 S4/S5 一致、role 枚举上更正确。**A 的 P1-1/P1-2/P1-3 是接口层硬冲突，必须修**；B 需吸收 A 的字段表/token map/G6/统一错误命名空间。

---

## 1. 异议（按严重度；P0=违反 S0–S5；P1=冻结前必须裁；P2=可冻结但后续补）

### P1-1（A）`GraphNavFrame` 用 `nav_id`，与 S5 冻结字段 `frame_id` 不一致

- **议项**：S6-7（S5-1/R-S5-9）。
- **异议**：A 的 `GraphNavFrame` schema 用 `nav_id`（失败码 `GRAPH_NAV_ID_INVALID`），但 S5-nav-v1 冻结字段/条款用 **`frame_id`**（S5-1 `GraphNavFrame{...frame_id...}`；R-S5-9 `frame_id=sha256(canonical(frame_spec))`）。S6 是收口契约，字段名必须是 S5 的 `frame_id`；否则 S5 与 S6 schema 不兼容、持久化/审计/curation 引用对不上。
- **反例**：按 S6 schema 实现的 frame 写 `nav_id`；S5 代码读 `frame_id` ⇒ undefined；G6/nav 审计引用断裂；S6a ER `NAV_FRAME.nav_id` 与 S5 冻结不一致。
- **修复**：S6-7 全部改为 `frame_id`（`NAV_ID` 失败码改 `GRAPH_FRAME_ID_INVALID`）；`NAV_STACK_ENTRY`/`NAV_EVENT` 同步；机检 schema 字段 == S5 冻结字段；如要保留 `nav_id` 必须是**别名**且在 schema 注释/迁移映射中显式，不得作为主字段。
- **严重度**：S5→S6 字段契约 ⇒ **P1（冻结前）**。

### P1-2（A）`FRAME_SPEC` 加入 `frame_id`/`edition_sha`，超出 S4 冻结输入

- **议项**：S6-6（S4-11/S5-9/R-S5-9）。
- **异议**：A 的 `FRAME_SPEC` 字段含 `frame_id`、`edition_sha`，并定义 `frame_id=sha256(canonical(frame_spec_without_frame_id))`；但 S4-render-v1 的 `frame_spec` 输入只有 `level_id/view_family_id/dimension_id/focus_id/hop_budget/new_hop/mode/budget`（无 frame_id/edition），S5 R-S5-9 规定 **frame_id 由 S5 派生、edition 由 S5 本地派生、不消费 S4 未冻结字段**。S6 把二者写进 FRAME_SPEC 会把 S4 输入变成未冻结契约，违反 S4/S5 边界；且 frame_id 作为输入再 hash 自身有循环歧义。
- **反例**：S5 按 S6 FRAME_SPEC 把 edition_sha 传给 S4；S4 schema 拒绝未知字段/忽略，S5/S4 行为不一致；frame_id 在 spec 内又被 hash，S5/S6 计算的 id 不同。
- **修复**：`FRAME_SPEC` 只保留 S4 冻结字段；`frame_id` 作为 S5 派生输出（`sha256(canonical(frame_spec))`），`edition_sha` 由 S5/S6a 本地校验但不进 S4 输入；S6-6 的 `frame_id/edition` 从 FRAME_SPEC 删除或标注为 S5 附加输出字段；机检 frame_spec 字段 == S4 冻结。
- **严重度**：S4/S5 契约边界 ⇒ **P1（冻结前）**。

### P1-3（A）`VM_NODE.role` 只允许 `"member"`，与 S3 冻结 `role∈{member,focus}` 冲突

- **议项**：S6-5（S3-1/S3-12）。
- **异议**：A 的 `VM_NODE` schema 写 `role:"member"`（固定），但 S3-visual-v1 S3-1/S3-12 冻结 `role∈{member,focus}`，`focus` 用于当前焦点节点（S5 产生）。若 S6 按 `member` only 校验，带 focus 的 VM 会被 `GRAPH_VM_NODE_INVALID` 拒绝，S5/S4 无法输出焦点角色；S3 视觉高亮也失效。
- **反例**：S4 生成 `role:"focus"` 的焦点节点 ⇒ S6 schema 拒绝；或 S3 Renderer 无法识别焦点；S5 Focused 状态不对应 VM 角色。
- **修复**：`VM_NODE.role ∈ {"member","focus"}`（默认 `member`；focus 至多 1 个/VM 或按 S3 约束）；机检枚举/数量；若 S3 另有限制（cluster/kp），同步。S6 不得把字段收窄到 S3 之外。
- **严重度**：S3→S6 schema 冲突 ⇒ **P1（冻结前）**。

### P2 清单

| # | 项 | 判断/修复 |
|---|---|---|
| P2-1 | A history 无签名位置（charter 要求签名位置） | 吸收 B 的 optional detached signature（`.sig` 与 content_sha 绑定）；或明确 v1 不启用签名并写原因/后续 S6 修订；机检字段 |
| P2-2 | A 用 `GRAPH_*` 统一命名空间，B 用 `DS_/DIM_/S2_...` | 统一采用 A 的 `GRAPH_*` + origin 表；B 需映射旧名；失败码唯一/映射；i18n key |
| P2-3 | 存储路径 A `.memoria/config/graph`/`build/graph`/`audit/graph` vs B `.memoria/cache` | S6a 冻结唯一路径；缓存可重建；D-3；审计 append-only；GC |
| P2-4 | A `CLUSTER` 含 μ/β/label/label_key；B 缺 | B 吸收；S2 schema 字段；run/membership 身份；stale/curation |
| P2-5 | A `S6-5` `VISUAL_ENCODING_MAP`/`RendererCapabilities`；B 缺 | B 吸收 token map/capabilities sha；2D/3D 同签名 |
| P2-6 | A `S6-7` T01–T30；B 表少 T30/事件 | B 补 `RESET` from Stale/T30；事件集/状态表与 S5 附录 A 完全一致；S5a 生成 |
| P2-7 | A/B G6 字段差异 | 合并 A 的 rule_id 直方图/subset/closure/behind + B 的 nav 指标；S8 阈值 |
| P2-8 | A/B 0.5 边界 | 合并：2D 先发、3D 仅接口、agent 只读、无迁移、S6a 门禁 |
| P2-9 | A `GraphView`/`CLUSTER_EDGE` 字段 vs B 简 | B 吸收 A；S6a ER |
| P2-10 | A `S6-1` 事实实体细（DOCUMENT/KP_OCCURRENCE/EDGE_PROVENANCE） | B 吸收；ER 定稿；与现有 `.memoria` 对齐 |

---

## 2. 点名审查结论

1. **并行事实源/双写**：A/B **PASS**（事实=`.md`+sidecar/manifest；DataSource 只读；派生缓存；D-3）。A ER 更细。
2. **每个 schema 字段/类型/枚举/默认/失败码**：A 更全（表/失败码）；B 较简；**A 的 VM role/GraphNavFrame/FRAME_SPEC 有字段冲突（P1-1/2/3）**；B 需吸收 A 字段表。
3. **registry_history 不可变/可复算/签名**：A 有 content-addressed/history 但无签名；B 有可选签名但 schema 简；**P2-1** 合并。
4. **run/membership 身份/stale/curation/五状态**：A/B **PASS**（run_id/params_hash/cluster_key/五状态/curation）；A 更完整（μ/β/label）。
5. **S3 白名单+ADDENDUM-1 / data_edge_ids 审计禁读**：A **PASS** 但 role 收窄（P1-3）；B **PASS**；均 Renderer 禁读。
6. **S4 候选/MANDATORY/budget/subset 失败码**：A/B **PASS**（presence/rule_id/MANDATORY/subset）；A 的 FRAME_SPEC 字段超 S4（P1-2）；B 更贴 S4。
7. **S5 T01–T30 表↔图/frame_id 派生/持久化白名单**：A 用 nav_id（P1-1）、FRAME_SPEC 超界（P1-2）；B 用 frame_id/派生正确但表需补 T30/事件（P2-6）；均需 S5a 生成。
8. **存储/审计/GC/版本/D-3**：A/B **PASS**；路径需 S6a 统一（P2-3）。
9. **失败码统一与 i18n**：A 统一 `GRAPH_*` 更强；B 多命名空间需映射（P2-2）；均需 i18n key/severity。
10. **兼容/迁移/回滚**：A/B **PASS**（旧 graph-groups 忽略、无破坏迁移、删缓存回滚）；A 更细版本。
11. **G6 可复跑**：A/B **PASS**；A 字段更细（rule_id 直方图/subset/closure/behind）。
12. **0.5 边界**：A/B **PASS**（2D 先发/3D 接口/agent 只读/无迁移）；A 更细接口清单。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A）`GraphNavFrame.nav_id` vs S5 冻结 `frame_id`**：S6 契约字段名必须与 S5-1/R-S5-9 一致；否则 S5/S6/持久化/G6 引用断裂。修复：S6-7 改 `frame_id`（失败码 `GRAPH_FRAME_ID_INVALID`），`nav_id` 仅可作别名；机检 schema==S5。
2. **P1-2（A）`FRAME_SPEC` 加入 `frame_id`/`edition_sha` 超出 S4 冻结输入**：S4 frame_spec 无这些字段，S5 R-S5-9 明确 frame_id 派生、edition 本地；S6 不能把二者塞进 S4 输入（还会产生 frame_id 自哈希）。修复：FRAME_SPEC 只保留 S4 冻结字段；frame_id/edition 作为 S5 派生/本地校验字段，不进 S4；机检字段==S4。
3. **P1-3（A）`VM_NODE.role` 只 `member`，与 S3 冻结 `{member,focus}` 冲突**：S4/S5 焦点节点会被 schema 拒绝/视觉失效。修复：`role∈{member,focus}`（默认 member；focus 数量按 S3 约束），机检枚举。

> P2：A history 签名位置缺失；B 多错误命名空间应统一 `GRAPH_*`；A/B 存储路径 S6a；B 补 T30/事件；B 吸收 A 的 CLUSTER μ/β/label、token map、G6、0.5 清单。

## 4. 结论

- **A 无 P0**，但 **P1-1/P1-2/P1-3 是 S5/S4/S3 接口字段冲突，冻结前必须修**；A 在 ER/字段表/token map/G6/0.5 边界上更强。
- B 在 frame_id/FRAME_SPEC 与 S4/S5 边界、role 枚举上更正确，但需吸收 A 的字段表/统一错误命名空间/token map/G6/0.5 清单。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S5 `S5-nav-v1.md:16-19`（frame_id/R-S5-9）、`:57-59`（FRAME_SPEC 边界）、`:117-155`（T01–T30）；S4 `S4-render-v1.md`（frame_spec 无 frame_id/edition）；S3-1/S3-12 role∈{member,focus}；A S6-5/S6-6/S6-7；B S6-5/S6-6/S6-7。
