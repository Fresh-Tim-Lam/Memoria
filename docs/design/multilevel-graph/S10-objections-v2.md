# S10 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S10-RULINGS.md`（sha `9818d0fd…`，R-S10-1..R-S10-5）+ `S6-ADDENDUM-2.md`。
> **对象**：`S10-kp-proposal-A-v2.md`（主办研究，sha **`db71ccd4558ea7fddf97f3efd280fc4c2efbe663c523a7f8c7892f80d7b8458a`**，25,262 B）与 `S10-kp-proposal-B-v2.md`（本复核方，sha **`48d8760d6907bf0b8aa536257756d210958332036c0af23b0c9196df5ed05274`**，17,127 B）。
> **性质**：B-v2 以 R-S10 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S10-RULINGS/S0–S9。

---

## 0. R-S10 关闭矩阵

| 裁决 | A-v2 | B-v2 | 判定 |
|---|---|---|---|
| R-S10-1 全类型/E_sem 门槛 | SemanticEdge type 允许 contain/reference/extend；contain_kind structural/semantic；E_sem=label=semantic ∪ contain_kind=semantic；结构/ref 不标语义；新类型须 S0/S1 | 同 | **关闭** |
| R-S10-2 GRAPH_*/ADDENDUM-2 码表 | 删除 S10_*；GRAPH_KP_*/EDGE_*/CURATION_* + legacy/i18n/severity/audit_id；未知 GRAPH_INTERNAL | 同（码表完整） | **关闭** |
| R-S10-3 propose_write only/D-3 | agent 只 propose_write 不写文件；apply 产品 curation writer 人工确认；无 sidecar/正文；失败零写 | 同 | **关闭** |
| R-S10-4 质量 eval 可执行 | golden 路径/schema/sha、eval-kp 命令/exit、metrics JSON+sha、人工抽检/阈值、S8 消费 | 同（路径/命令名不同，P2-1） | **关闭** |
| R-S10-5 身份/方向/合并/失效 | kp_id 全局唯一；单 section/不重叠；嵌套 future；merge canonical+alias+history；direction both；S10 未启用只读；写后 S9 失效 | 同 | **关闭** |

**结论**：R-S10-1..5 两版**全部关闭**；无 P0/P1；剩余 P2 为 golden 路径/命令、阈值校准、curation 元数据/KP 目录细节（S10a/SE）。

---

## 1. A-v2 / B-v2 逐项差异（S10-1..S10-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S10-1 边界 | agent 只 propose_write；apply 产品 curation writer；无文件写；0.5 不做 | 同 | 一致。 |
| S10-2 KP | KP schema 全；kp_id 全局唯一；单 section/不重叠；嵌套 future | 同 | 一致；A 失败码映射更细。 |
| S10-3 抽取 | 证据锚/低置信/幂等/去重 | 同 | 一致。 |
| S10-4 语义边 | S0 全类型；contain_kind/label；E_sem 门槛；direction both；结构/ref 不冒充；新类型须 S0/S1 | 同 | 一致；A 表更细。 |
| S10-5 双引用/curation | provenance/curated/approval/undo | 同 | 一致。 |
| S10-6 写路径 | propose_write/plan/approval/atomic/backup/undo/audit；产品 curation writer；失败零写；WritePlan schema | 同；WritePlan 细节 | 一致；A 更细。 |
| S10-7 冲突/合并 | 冲突类/去重/merge canonical+alias+history/redirect | 同 | 一致。 |
| S10-8 版本/失效 | edition/CAS/S9 失效/S2 重算/旧数据/回滚/disabled 只读 | 同 | 一致。 |
| S10-9 质量 | golden `.memoria/agent/audit/graph/golden/S10-golden-set.json`；`scripts/verify/eval-kp.py`；Q-KP/EDGE/EVIDENCE/SEM-PURITY；抽检/阈值/S8 | golden `docs/.../golden/S10-kp-golden-set.json`；`scripts/benchmark/graph/eval_kp.py`；同指标 | **路径/命令名不同（P2-1）**；指标一致。 |
| S10-10 S1/S2 | S1 只读；KP 目录独立；S2 重建/多归属；不写簇 | 同 | 一致。 |
| S10-11 失败/隐私 | GRAPH_* 码表完整/legacy/i18n/severity/audit；不 apply/零写/隐私 | 同 | 一致。 |
| S10-12 0.5 | 不在 0.5；无写工具；人工确认 | 同 | 一致。 |

**总判断**：两版在 R-S10 核心上已收敛；A-v2 schema/失败码/merge 历史更细；B-v2 eval 指标/枚举更紧凑。**无新增 P0/P1**；剩余 P2 为 S10a/SE 冻结细节。

---

## 2. 仍未解决 3 点（P2；S10a/SE 冻结）

### P2-1 golden 路径与 eval 命令名 A/B 不一致
- **现状**：A golden `.memoria/agent/audit/graph/golden/S10-golden-set.json` + `scripts/verify/eval-kp.py`；B `docs/design/multilevel-graph/golden/S10-kp-golden-set.json` + `scripts/benchmark/graph/eval_kp.py`；S10a 未定唯一路径/命令。R-S10-4 只要求可执行，未冻结路径。
- **影响**：S8 gate/CI/人工抽检两套路径/命令；golden sha 双源；本地/CI 不一致。
- **建议**：S10a/SE 冻结唯一 golden 路径（推荐 docs 评审可读 + edition-pinned；artifacts 只放 eval 产物）与唯一命令/参数/exit/产物；A/B 统一；机检路径/sha/命令。
- **证据**：R-S10-4；A S10-9；B S10-9。

### P2-2 质量阈值/置信阈值/golden 规模未校准
- **现状**：两版 Q-KP-P/R、Q-EDGE-P/R 阈值 0.8/0.9、低置信 0.6、人工抽检样本数、golden 规模均为建议/假设；R-S10-4 明确未校准前 soft。
- **影响**：质量验收只能趋势/soft，不能固定阻断；阈值不当会误放低质 KP/边或误杀；golden 小易过拟合。
- **建议**：S10a 建 edition-pinned golden（含无 semantic/多语言子集），跑精度/召回基线，冻结阈值/抽检样本/容差；未校准前 soft；S8 消费；阈值变更走 S10 修订。
- **证据**：R-S10-4；A S10-9/§14.4；B S10-9。

### P2-3 curation 元数据/KP 目录落盘位置未冻结
- **现状**：A 说 KP 目录“现有 sidecar/index；非 S1 维度 registry”，B 说 curated overlay；R-S10-3/R-S10-5 要求 `curated_by/at`/curation 元数据只写 **S6 允许的 metadata/audit 白名单**，但 S6 未定义 curation 元数据具体字段/路径（sidecar? audit? config?）；KP 目录/历史（KP_HISTORY）位置也未冻结。
- **影响**：实现可能把 curation 元数据写 sidecar（违反 D-3）或写正文；KP 目录与 S1 registry 混淆；history 不可追溯。
- **建议**：S10a/SE 冻结 curation 元数据 schema/字段与落盘位置（推荐 `.memoria/agent/audit/graph/curation/` 或 S6 config 白名单，不写 sidecar/正文）；KP 目录/KP_HISTORY 路径/sha；graph/agent 无 sidecar 写；机检路径白名单。
- **证据**：R-S10-3/R-S10-5；S6-8/S6-9；A S10-5/S10-10；B S10-5/S10-10。

---

## 3. 点名审查结论（v2）

1. **只写 KP/语义边/不写事实/不绕 propose_write/0.5**：A/B **PASS**（propose_write only；产品 curation writer apply；无 sidecar/正文；0.5 不做）。
2. **KP 定义/粒度/字段/锚/不编造/低置信/去重**：A/B **PASS**（kp_id 全局/单 section/不重叠/嵌套 future/anchor/confidence/去重）。
3. **语义边类型/方向/证据/置信/结构引用不冒充**：A/B **PASS**（S0 全类型；E_sem 门槛 label/contain_kind；结构/ref 不标语义；direction both）。
4. **双引用/curated_by/at/人工确认/undo**：A/B **PASS**（provenance/approval/undo）。
5. **写路径 atomic/零写入/审计**：A/B **PASS**（propose-only；产品 writer plan/approval/atomic/backup/undo/audit；失败零写；无 sidecar/正文）。
6. **冲突/去重/合并/历史**：A/B **PASS**（冲突类/去重/merge canonical+alias+history/redirect）。
7. **edition/S9 重建/回滚**：A/B **PASS**（CAS/失效/重建/旧数据/回滚/disabled 只读）。
8. **质量/golden/抽检/阈值**：A/B **PASS**（golden/命令/exit/JSON sha/抽检/阈值；P2-1/P2-2）。
9. **S1 registry/S2 clustering**：A/B **PASS**（S1 只读；KP 目录独立；S2 重建/多归属；不写簇）。
10. **失败/隐私**：A/B **PASS**（GRAPH_* 码表/ADDENDUM-2；legacy/i18n/severity/audit；不 apply/零写/隐私）。
11. **0.5 边界**：A/B **PASS**（S10 不在 0.5；无写工具；人工确认；不影响 DoD）。

---

## 4. 最严重 3 条 / 结论

1. **P2-1 golden 路径/命令名不统一**：A `.memoria/agent/audit/graph/golden/` + `scripts/verify/eval-kp.py`；B `docs/.../golden/` + `scripts/benchmark/graph/eval_kp.py`；S10a/SE 冻结唯一路径/命令/exit/产物，A/B 统一，机检 sha。
2. **P2-2 质量/置信阈值与 golden 规模未校准**：0.6/0.8/0.9、抽检样本、golden 规模为建议；S10a 用 edition-pinned golden 校准并冻结，未校准前 soft，S8 消费。
3. **P2-3 curation 元数据/KP 目录位置未冻结**：curated_by/at、KP_HISTORY、KP 目录需 S6 metadata/audit 白名单（不写 sidecar/正文）；S10a/SE 冻结字段/路径/sha；graph/agent 无 sidecar 写。

- **两版无 P0/P1**；R-S10-1..5 全部关闭；A-v2 schema/失败码/merge 历史更细，B-v2 eval 指标/枚举更紧凑。未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S10 `S10-RULINGS.md:19-37`；A-v2 S10-1/S10-4/S10-6/S10-9/S10-11；B-v2 同项。
