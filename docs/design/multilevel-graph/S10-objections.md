# S10 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35（重点 U-12/13/14/19/21/22/25/27/32）；上游冻结 S0–S9 十份 v1 + `S3-ADDENDUM-1`/`S6-ADDENDUM-1`，不得违反；`S10-charter.md`。
> **对象**：`S10-kp-proposal-A.md`（主办研究，sha **`d0a0940477b5737019a50d9e6c2125e5a59092066f345f92ebe4da41d03dd884`**，20,268 B）与 `S10-kp-proposal-B.md`（本复核方，sha **`b323c82b67fea70d7966aa0da327319cfdbd628af1e91c39934485c6d20edde0`**，14,327 B）。
> **独立性**：B 于 08:20:39 落盘，A 于 08:21:31 才出现；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S9 冻结。

---

## 0. A/B 差异总表（S10-1..S10-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S10-1 边界 | 只写 KP 元数据/语义边/provenance；不写正文；propose_write/人工确认/0.5 不做 | 同核心；不写事实/唯一 propose_write/0.5 不做 | 一致；A 更细（写 op 白名单）。 |
| S10-2 KP 定义/粒度/字段 | KP schema 全（title/alias/summary/range/section/evidence/confidence/status）；单 section/不重叠；嵌套需 parent | 同核心；字段/粒度/id/来源标记 | 一致；A 更细（失败码/嵌套）。 |
| S10-3 抽取/生成 | 证据锚/低置信/幂等/去重 | 同 | 一致。 |
| S10-4 语义边 | **type 枚举仅 `reference`/`extend`**；label=semantic；方向固定；证据/置信/reason；结构/ref 不冒充 | type = S0 E_relation 允许（**含 contain(semantic)**）；label semantic；方向；证据/置信 | **关键差异（P1-1）**：A 排除 `contain(semantic)`，但 S0 E_relation_min/S1 relation_sources/S2 E_sem 包含 contain(semantic)；S10 不能写该语义类型 ⇒ E_sem 覆盖缺口。B 更完整。 |
| S10-5 双引用/curation | provenance source/target/assertion_source；curated_by/at；人工确认；undo | 同 | 一致；A 更细（decision/review_status）。 |
| S10-6 写路径 | propose/plan/approval/atomic/backup/undo/audit；ops 白名单；失败零写 | 同 | 一致；A 更细（WritePlan schema）；**D-3 写路径边界 P1-3**。 |
| S10-7 冲突/去重/合并 | 冲突类/人工/merge 历史/redirect | 同核心 | 一致。 |
| S10-8 版本/失效/回滚 | edition→S9 失效/S2 重算/旧数据保留/回滚 | 同 | 一致。 |
| S10-9 质量 | Q-KP-P/R/Q-EDGE-P/R/Q-EVIDENCE/Q-SEM-PURITY；golden/抽检/阈值；S8 消费 | 同核心；指标较简 | 一致；A 更细；均缺 golden/命令可执行细节（P2-2）。 |
| S10-10 S1/S2 | KP 目录独立/S1 只读/S2 重算/多归属 | 同 | 一致。 |
| S10-11 失败/隐私 | 失败矩阵 **`S10_*` 码**（NO_SOURCE/AMBIGUOUS/LOW_CONFIDENCE/CONFLICT/BUDGET/PRIVACY） | 失败/隐私；未见具体码表 | **关键差异（P1-2）**：A 用 `S10_*` 新命名空间，与 S6 `GRAPH_*` canonical 冲突（S6-9）；B 需补码表。 |
| S10-12 0.5 | 不在 0.5；未来人工确认；feature flag | 同 | 一致。 |

**总判断**：A 在 schema/写路径/质量/失败矩阵上更强；B 在语义边类型覆盖（含 contain(semantic)）上更完整。**P1 集中在 A 语义边类型缺口、A S10_* 错误码、A/B 写路径 D-3 边界**。

---

## 1. 异议（按严重度；P0=违反 S0–S9；P1=冻结前必须裁；P2=后续/SE）

### P1-1（A）`SemanticEdge.type` 仅 `reference`/`extend`，排除 `contain(semantic)`，导致 E_sem 类型覆盖缺口

- **议项**：S10-4（S0-3 E_relation_min；S1 relation_sources；S2 semantic-only）。
- **异议**：A 的 SemanticEdge `type` 枚举只有 `reference`/`extend`，并写“contain(structural) 不手标”；S0 `E_relation_min` 明确含 **contain(structural/semantic)**、reference、extend；S1 A `relation_sources` 覆盖 min；S2 的 E_sem 可包含 contain(semantic)。若 S10 只能写 reference/extend，则 **contain(semantic) 语义边永远无法由 agent 创建**，E_sem 覆盖不完整，S2 语义簇无法包含该类型；A §14.3 已自列“是否允许新增语义关系类型需 S1/S0 修订”，但当前 schema 直接把 contain(semantic) 排除，未证明它不需要。
- **反例**：KP 间“整体-部分/概念包含”语义关系应写 `contain(semantic)`；A 只能写 reference/extend，语义丢失；S2 簇只看 reference/extend，覆盖下降。
- **修复**：SemanticEdge `type` 允许 S0 E_relation_min **全部允许类型**：`contain(structural)`、`contain(semantic)`、`reference`、`extend`；仅当 `label=semantic`/`contain_kind=semantic` 时进入 E_sem；`contain(structural)` 只能作结构、不得标 semantic；结构/引用边零语义贡献。若 Lead 认为 S10 只写 reference/extend，必须在 S0/S1 修订中显式裁掉 contain(semantic) 的语义边来源，不能只在 S10  Schema 里静默排除。
- **严重度**：S0/S1/S2 语义边契约 ⇒ **P1（冻结前）**。

### P1-2（A）S10 失败码用 `S10_*` 新命名空间，与 S6 `GRAPH_*` canonical 冲突

- **议项**：S10-11（S6-9 `GRAPH_*` canonical + legacy；S6-ADDENDUM-1）。
- **异议**：A S10-11 定义 `S10_NO_SOURCE/S10_AMBIGUOUS/S10_LOW_CONFIDENCE/S10_CONFLICT/S10_BUDGET_EXCEEDED/S10_PRIVACY_REJECTED`，S10-2/S10-4 也用 `S10_KP_*`/`S10_EDGE_*` 失败码；S6-9 冻结 **`GRAPH_*` canonical**，新码须登记 S6-ADDENDUM（S7 即如此）；S10 另起 `S10_*` 命名空间会让 S7/S8/G6/客户端无法统一映射，legacy/i18n/severity 缺失。B 未给具体码表，也需补。
- **反例**：S10 返回 `S10_NO_SOURCE`，S6/ S7 错误表只有 `GRAPH_*`；客户端/G7 无法映射；S6-ADDENDUM 不覆盖。
- **修复**：S10 错误码统一 `GRAPH_*` canonical（可新增 `GRAPH_KP_*`/`GRAPH_EDGE_*`/`GRAPH_CURATION_*` 并经 S6-ADDENDUM 登记）；每码给 legacy/i18n/severity/audit_id；或映射到既有 `GRAPH_INPUT_INVALID/GRAPH_ANCHOR_STALE/GRAPH_TOOL_INPUT_INVALID/GRAPH_INTERNAL`；机检码表 ⊆ S6 注册表。
- **严重度**：错误命名空间/可机判 ⇒ **P1（冻结前）**。

### P1-3（A/B）S10 写路径与 S6 D-3 边界未精确：agent 写 curated overlay 是否等于写 sidecar/产品事实？

- **议项**：S10-1/S10-6（S6-1 单一真源；S6-8 D-3；S0 D-3）。
- **异议**：A 允许写“KP 元数据/语义边/curation provenance/curated overlay”，B 允许“curated overlay”；但 S6-1 事实 = `.md` + sidecar/manifest，S6-8/D-3 **禁止图服务写 sidecar/新段**；S10 curation 是产品 curation 写路径（人工/未来 agent），不是 graph service 直接写 sidecar。A/B 均未明确：**S10 agent 只产出 plan/proposal；apply 由产品 curation writer/人工确认执行，graph 服务不接触 sidecar**；A 的 `curation` op 与 `curated overlay` 可能被实现为 graph 直接写 sidecar，违反 D-3。`curated_by/at` 写到哪里（产品 curation 元数据/audit vs sidecar）也未定。
- **反例**：实现按 S10 写 `.memoria/sidecars` 的 KP/边；违反 D-3；或写 `.md` 正文改事实。
- **修复**：S10-1/S10-6 明确：agent 只 `propose_write`（plan/evidence，不写）；apply 由 **S10 外的产品 curation writer** 在人工确认后写既有 curation 允许路径（非 graph service 直写 sidecar）；写目标字段/文件白名单（curation overlay/KP history/audit）明确；graph 服务无 sidecar 写权限；机检写路径白名单 + 无 sidecar 写。
- **严重度**：单一真源/D-3 边界 ⇒ **P1（冻结前）**。

### P2 清单

| # | 项 | 修复 |
|---|---|---|
| P2-1 | A `S10-4` direction 固定 source→target | S0 边方向是否含 both/无向需确认；允许 `both` 时 schema/证据更新 |
| P2-2 | A/B `S10-9` 质量指标缺 golden schema/路径/命令/exit/sha | S10 质量评估可执行契约（golden/抽检/阈值/命令/JSON sha）；S8 消费 |
| P2-3 | A KP `kp_id` 全局唯一 vs B anchor+label | 统一 id 派生/去重键；跨文件同名；ID history |
| P2-4 | A KP 嵌套 range/parent 规则 | S10a/UX 决定；重叠需 parent+人工确认；机检 |
| P2-5 | A `curation` op 与 `curated_by/at` 存储位置 | 产品 curation 元数据 vs audit；不写 sidecar；见 P1-3 |
| P2-6 | 合并/redirect 历史 schema | KP_HISTORY/KP redirect 字段/sha；旧 id 可解析；undo |
| P2-7 | 语义边 type 是否新增（除 S0） | 不新增；若需新类型须 S0/S1 修订；不得 S10 自造 |
| P2-8 | 低置信阈值/抽检样本/golden 规模 | S10a 实测校准；人工抽检；S8 消费 |
| P2-9 | B 缺失败码表/写 op 白名单细节 | B 吸收 A 码表（GRAPH_*）与 WritePlan schema |
| P2-10 | S10 与 S7/S9 边界 | S10 不启用时 S7 只读；S10 写后 S9 失效；不夹带 |

---

## 2. 点名审查结论

1. **只写 KP/语义边/不写事实/不绕 propose_write/0.5**：A/B **PASS**（写 op 白名单；propose/plan/approval/apply；0.5 不做）；**D-3 写路径 P1-3**。
2. **KP 定义/粒度/字段/锚可机检/不编造/低置信/去重**：A/B **PASS**（schema/range/anchor/confidence/去重）；A 更细；P2-3/P2-4。
3. **语义边类型/方向/证据/置信/结构引用不冒充**：B **PASS**（含 contain(semantic)）；**A 缺 contain(semantic) P1-1**；结构/ref 零语义 PASS。
4. **双引用/curated_by/at/人工确认/undo**：A/B **PASS**（provenance/approval/undo）。
5. **写路径 atomic/零写入/审计**：A/B **PASS**（plan/approval/atomic/backup/undo/audit；失败零写）；D-3 P1-3。
6. **冲突/去重/合并/历史**：A/B **PASS**（冲突类/人工/历史/redirect）；历史 schema P2-6。
7. **edition/S9 重建/回滚**：A/B **PASS**（edition 失效/S2 重算/旧数据/回滚）。
8. **质量/golden/抽检/阈值**：A/B 有指标/抽检/阈值；**缺可执行 golden/命令 P2-2**。
9. **S1 registry/S2 clustering**：A/B **PASS**（S1 只读/只增；KP 目录独立；S2 重算/多归属；不写簇）。
10. **失败/隐私**：A/B 有失败/隐私/不自动；**A `S10_*` 码 P1-2**；B 码表 P2-9。
11. **0.5 边界**：A/B **PASS**（S10 不在 0.5；无写；人工确认；不影响 DoD）。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A）SemanticEdge 排除 `contain(semantic)`**：S0 E_relation_min/S1 relation_sources/S2 E_sem 含 contain(semantic)，A 只允许 reference/extend ⇒ S10 不能写该语义类型，E_sem 覆盖缺口。修复：允许 S0 全部类型（contain(structural/semantic)/reference/extend），仅 label=semantic/contain_kind=semantic 进入 E_sem，结构边不得标语义；若裁掉须 S0/S1 修订而非 S10 静默排除。
2. **P1-2（A）S10_* 错误码与 S6 `GRAPH_*` canonical 冲突**：S6-9 冻结 `GRAPH_*`，S7 已用 ADDENDUM；A 另起 `S10_*` 命名空间，G7/S8/客户端无法映射。修复：统一 `GRAPH_*`（新增 `GRAPH_KP_*`/`GRAPH_CURATION_*` 须 S6-ADDENDUM），每码 legacy/i18n/severity/audit_id；B 同码表。
3. **P1-3（A/B）写路径 vs S6 D-3 未精确**：S10 agent 只 propose（plan/evidence），apply 由产品 curation writer 在人工确认后执行；graph 服务不得写 sidecar；curated overlay/curated_by/at 存储位置白名单明确；机检无 sidecar 写。否则实现可能违反 D-3。

## 4. 结论

- **两版无 P0**；A 在 schema/写路径/质量/失败矩阵上更强；B 在语义边类型覆盖（含 contain(semantic)）上更完整。
- **P1-1/P1-2/P1-3 冻结前必修**；P2 包括 direction、质量 golden/命令、kp_id/嵌套、curation 存储、merge history、新类型禁止、阈值校准、B 码表。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S10 章程 S10-1..12；S0-3 E_relation_min；S1 relation_sources；S2 semantic-only；S6-1/S6-8 D-3；S6-9 `GRAPH_*`；A S10-4/S10-11；B S10-4/S10-11。
