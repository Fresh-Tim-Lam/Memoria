# C0 独立异议与 A/B 差异（联网取证）

> **依据（不可改写）**：`docs/design/corpus-seminar/CHARTER.md` C1–C12；0.5 HOLD `dec-20261105-cb24f93e`；S0–S10 冻结稿 + `IMPLEMENTATION-RULINGS.md`。
> **对象**：`C0-proposal-A.md`（主办研究，sha **`18b1674d734da6411606ee3bcda09c27905e03b41049b00c2bb275dc63ef9f43`**，24,042 B）与 `C0-proposal-B.md`（本复核方，sha **`1c0989d7f19d036ad3d45664e8aa90a064ec5857949376e98acffbe6830e74cf`**，29,047 B）。
> **独立性**：B 写作时未读 A；完成后对照。B 初稿的 SemEval-2010 Task 8 URL 也有误（S10-1006），已在落盘后核验并改为 `W09-2415`；此处主动披露，不借此偏袒 B。
> **证据等级**：A=论文/标准/官方；B=本仓冻结/实测；C=开源/官方文档；D=语料观测；PI=假设。

---

## 0. A/B 差异总表（C1–C12）

| 项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| C1 用户/用途 | 开放教材单章 pilot；三层成功标准；证据 GraphRAG/BEIR/HITL | 个人+教材+agent；pilot；证据 Datasheets/Data Statements/BEIR | 一致（pilot/三层）；A 引 GraphRAG/HITL，B 引数据文档；无冲突。 |
| C2 来源/许可 | **只允许 CC BY/BY-SA/CC0/PD/自著**；用户库私有；每文档许可；PII 排除 | **Tier A 可发布/B 仅内部评测/C 禁用**；CC BY/BY-SA/CC0/PD；BY-NC/ND 内部；GDPR/Presidio；许可清单/NOTICE | **A 缺“内部评测”层与 BY-NC/ND/数据库权利/fair use/PII 工具**；B 更可执行（P1-3）。 |
| C3 本体 | S0 全类型 + SKOS 概念注释；schema.org 元数据；不新增 | S0 全类型 + E_sem 门槛 + SKOS/OWL/PROV；不新增 | 一致；A 多 schema.org，B 多 PROV。 |
| C4 KP 粒度 | 概念/术语/公式/步骤+1–3 句；单 section；不嵌套；JSONL/CoNLL 锚 | 命题级/单 section/不重叠；ISO LMF + INCEpTION | 一致；A 1–3 句 vs B 命题级；需 pilot 校准（P2-1）。 |
| C5 协议 | 两阶段；30+正/30+负/20+边界；三级裁决；培训 | 手册/正负/边界/培训/合格测试；INCEpTION/brat/Data Statements | 一致；A 例数更具体，B 培训测试更可执行。 |
| C6 语义边 | S0 全类型/E_sem/方向/证据；证据 **SemEval URL `S10-1002`（错误）** | S0 全类型/E_sem/方向 both/证据/负例；SemEval **已改 `W09-2415`** | **A 证据链接错误（P1-2）**；B 自纠。 |
| C7 规模/采样 | pilot 50 KP/30 边/20 query；主集 500 KP/300 边/100 query；按章 dev/test；成本 40–60 人时 | pilot 同；阶段 500/300；分层/种子/edition；成本 2 人×2 天（≈32 h） | 一致；成本口径不同（P2-2）。 |
| C8 IAA | **KP 用 Cohen κ（二分类）**/Fleiss；边用 agreement+F1；κ≥0.67/0.8 | KP span 用 Krippendorff unitizing α/边界 F1；类型/边 tuple 用 κ/F1；α/κ≥0.67/0.8 | **A 的 KP κ 二分类不适配 span/重叠，边 F1 不是 IAA（P1-1）**；B 更可执行。 |
| C9 评测 | 三层/分型/消融/人判；GATE-RET 逐型 | 三层/分型/消融/人判；NDCG/TREC/证据 | 一致；A 无具体阈值/命令（P2-3），B 同样需 pilot 定阈值。 |
| C10 工具 | INCEpTION/brat/CoNLL/Croissant；只读隔离；审计 | INCEpTION/doccano/brat/Presidio；只读隔离；schema/许可/PII 校验 | 一致；A 缺 PII 工具（C2/P1-3），B 有。 |
| C11 S10/0.5 | propose-only/人工确认/edition 失效；0.5 门槛 IAA+Q-EVIDENCE+SEM-PURITY+GATE-RET | 同；四条件；Data Statements/PROV/Datasheets | 一致；A 门槛“非零增益”无数值（P2-3）。 |
| C12 交付 | Datasheet/Croissant/DVC；维护/废弃 | 语料+golden+指南+许可+脚本+报告+DATASHEET/DATA_STATEMENT；FAIR/Croissant/LDC/CLARIN | 一致；B 更全（FAIR/数据声明），A 有 DVC。 |

**总判断**：A 在 C1/C5 例数、C9 三层、C12 DVC 上更强；B 在 C2 分层许可/PII、C8 span IAA、C12 FAIR/数据声明上更强。**P1 集中在 A 的 IAA 协议、A 的错误证据 URL、A 的许可分层缺失**。

---

## 1. 异议（按严重度）

### P1-1（A）C8 用 Cohen κ 的“KP 二分类”不适配 KP span，边 F1 不是 inter-annotator agreement

- **议项**：C8（章程判据 5；C4/C6）。
- **异议**：A C8 写“KP 用 Cohen κ（二分类）/Fleiss κ（多人）；边用边类型+方向 agreement 与 F1；合格线 κ≥0.67、边 F1≥0.7”。KP 是 **span/range 标注**（有边界、可重叠、可嵌套），Cohen κ 假设 **预定义单元 + 名义类别**，不能处理 **unitizing（单位化）**、边界偏移、重叠 span；把 KP 简化为二分类会掩盖边界分歧。边 F1 若指“与金标准比”不是 IAA；若指“两标注者边集合 F1”，则需明确 tuple 匹配（source/target/type/direction/evidence）与裁决口径，否则不可复算。A 的 Fleiss/Krippendorff 证据链接也未给出 unitizing 方法。
- **反例**：两标注者对同一句 KP 边界差 2 字，二分类都记“有 KP” ⇒ κ=1.0，但 span 完全不同；边端点/方向不同但 F1 按“存在”算 ⇒ 高 F1 假一致。
- **修复**：C8 按对象分型：① KP span 用 **Krippendorff unitizing α** 或 **exact-boundary F1 + overlap F1**（先定义 unitizing 单位）；② KP 类型/边类型/方向用 Cohen/Fleiss κ；③ 边 tuple 用 **tupleset F1 + 裁决一致率**；④ 置信/有序用加权 κ/α；合格线分指标写；pilot 100% 双标 + 裁决。B 已按此修，A 需补。
- **严重度**：IAA 是章程硬门禁 ⇒ **P1（冻结前）**。

### P1-2（A）C6 的 SemEval-2010 Task 8 证据 URL 错误（`S10-1002` 不是 Task 8）

- **议项**：C6（章程 §6 外部证据可复核；C6 关系类型/方向/负例）。
- **异议**：A C6 与证据清单把 SemEval-2010 Task 8 指向 `https://aclanthology.org/S10-1002/`；经核验，Task 8 的正确 ACL Anthology 条目是 **`https://aclanthology.org/W09-2415/`**（Hendrickx et al., SEW-2009，2009；页面标题即 “SemEval-2010 Task 8...”）。`S10-1002` 不是该文，映射“关系分类方向/负例”无法复核。B 初稿也误用 `S10-1006`，已改为 `W09-2415`；A 仍为错误链接。
- **反例**：评审点开 S10-1002 发现不是 Task 8；C6 的“方向/负例”依据不可验证；证据表可信度下降。
- **修复**：A C6 与证据清单改 `https://aclanthology.org/W09-2415/`（访问 2026-11-05）；所有外部 URL 做一次 HTTP/标题核验；B 已改。
- **严重度**：外部证据可复核是章程硬要求 ⇒ **P1（冻结前）**。

### P1-3（A）C2 许可只列“可发布”，缺少“内部评测/不可再分发”层与 NC/ND/数据库权利/fair use/PII 工具

- **议项**：C2（章程判据 1；C2 隐私/再分发）。
- **异议**：A C2 只允许 `CC BY/CC BY-SA/CC0/PD/自著` 作为可发布语料；用户库“私有副本、不纳入发布包”。但未定义 **Tier B：可内部评测但不可再分发**（CC BY-NC/ND、购买许可、用户授权但不可发布），也未处理 **数据库权利/引用长度/fair use**；PII 只写“先脱敏/排除”，无工具/流程（B 用 Presidio 并给法律基础/保留期）。结果是：真实教材/论文中大量只能内部评测的语料无法进入任何流程，或实现者把 BY-NC/ND 当可发布；许可矩阵不可执行。
- **反例**：CC BY-NC 教材被当 Tier A 进 release；用户授权“可内部使用”的库无法标注；引用超长/数据库权利未核；PII 无工具导致漏检。
- **修复**：采用 **Tier A 可发布 / Tier B 仅内部评测（隔离、不导出原文）/ Tier C 禁用**；Tier B 不进发布包，只出聚合指标；逐文档 `license/SPDX/redistribution/attribution/DB-right/fair-use/PII` 字段；PII 用 Presidio 或等价工具 + 人工复核；NOTICE/许可兼容（BY-SA 传染、NC/ND 限制）；法务复核。
- **严重度**：来源/许可/隐私是发布前置 ⇒ **P1（冻结前）**。

### P2 清单

| # | 项 | 修复 |
|---|---|---|
| P2-1 | A C4 “1–3 句” vs B “命题级” | pilot 之前用边界例校准；把粒度判定写进手册；IAA 按 span 口径 |
| P2-2 | A C7 成本 40–60 人时 vs B 2 人×2 天 | 统一“人时”口径；pilot 实测后写回；含裁决/培训/返工 |
| P2-3 | A C9/C11 GATE-RET“非零增益”无阈值/命令 | pilot 后定阈值（如 graph/hybrid 相对 baseline +x%）；命令/exit 进 S8 GATE-RET；禁止聚合 |
| P2-4 | A C8 Fleiss DOI `10.1037/h0031619` 未核验 | 改用可核验的 Biometrics/JSTOR 记录；所有 DOI 做解析检查 |
| P2-5 | A C10 缺 PII 工具/许可字段校验 | 补 Presidio/等价；导出校验 schema/证据/许可/PII；只读隔离 |
| P2-6 | A C12 缺 FAIR/数据声明 | 补 FAIR/Croissant/DATA_STATEMENT；B 已有 |
| P2-7 | A C1/C2 教材未实际选定/许可未核验 | pilot 前锁定 1 本 + 许可页 + 版本；不能只写“候选 OpenStax” |
| P2-8 | B C8 unitizing α 仍需具体实现 | 定义 unitizing 单位/边界容差/α 计算脚本；pilot 校验 |
| P2-9 | B C1 缺 GraphRAG/HITL 证据 | 可补，但非必需；保持 ≥2 外部证据 |
| P2-10 | 双方 C9 人判 rubric/规模未定 | pilot 20 query + 2 judge；报告一致性；不合成 |

---

## 2. 点名审查结论

1. **来源/许可/隐私可发布/是否只挑容易语料**：A 只允许开放许可、用户库私有 **方向 PASS**，但缺 Tier B/NC/ND/DB/fair use/PII 工具 **P1-3**；B Tier A/B/C + Presidio PASS。双方都尚未实际锁定教材/许可（P2-7）。
2. **本体/关系与 S0/S10 对齐；语义边证据/方向/负例**：A/B **PASS**（S0 全类型/E_sem/方向/证据/负例）；A SemEval 链接错误 P1-2，不影响 S0 对齐。
3. **KP 粒度/边界/嵌套可标注**：A/B **PASS**（单 section/不重叠/边界例）；A 1–3 句 vs B 命题级需 pilot（P2-1）；嵌套 future。
4. **标注协议/IAA/合格线可执行**：A 手册/例数强，但 **IAA 用 KP 二分类 κ 不可执行 P1-1**；B 分型 α/κ/F1 更可执行（仍需 unitizing 实现 P2-8）。
5. **规模/采样/dev-test 隔离/成本现实**：A/B **PASS**（pilot/主集/按章隔离/edition）；成本口径 P2-2。
6. **评测分型/禁止聚合掩盖**：A/B **PASS**（keyword/vector/hybrid/graph；消融；人判）；A 阈值/命令 P2-3。
7. **工具/只读用户库/版本/审计**：A/B **PASS**（隔离副本；不写 sidecar；版本/审计）；A PII 工具 P2-5。
8. **S10/0.5 衔接/交付维护**：A/B **PASS**（propose-only/人工/edition 失效/0.5 门槛；交付包/维护）；A FAIR/数据声明 P2-6。
9. **证据质量（博客/可复核/许可依据）**：A/B 以论文/标准/官方为主 **PASS**；A SemEval URL 错误 P1-2；B 已自纠；DOI 核验 P2-4。
10. **A/B 差异未静默合并**：见 §0/§1；B 自纠记录见文首。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A）C8 IAA 协议不可执行**：KP 是 span/unitizing，不是二分类；Cohen κ/Fleiss κ 不能处理边界/重叠；边 F1 不是 IAA。修复：KP span 用 Krippendorff unitizing α 或 exact-boundary/overlap F1；类型/方向用 κ；边 tuple 用 tupleset F1+裁决；分指标合格线；pilot 100% 双标。
2. **P1-2（A）C6 SemEval URL 错误**：Task 8 正确条目为 `https://aclanthology.org/W09-2415/`（2009），A 用 `S10-1002`（B 初稿 `S10-1006` 已自纠）。修复：A 改 URL；所有证据做标题/HTTP 核验；B 已改。
3. **P1-3（A）C2 许可分层缺失**：只列可发布，缺 Tier B 内部评测（BY-NC/ND/购买/用户授权）、DB 权利/fair use/PII 工具；实现者可能把 NC/ND 发布或无法纳入真实教材。修复：Tier A/B/C + 隔离/不导出 + 许可字段 + Presidio/人工复核 + 法务；B 已有。

## 4. 结论

- **两版无 P0**；A 在 C1/C5 例数、C9 三层、C12 DVC 上更强；B 在 C2 分层许可/PII、C8 span IAA、C12 FAIR/数据声明上更强；B 已主动修正 SemEval 错误。
- **P1-1/P1-2/P1-3 冻结前必修**；P2 包括粒度/成本/阈值/DOI/PII/FAIR/教材锁定/unitizing 实现。
- 未写产品代码/契约、未发布 0.5、未 commit；差异逐项列出未静默合并。

> 参考锚：`CHARTER.md` C1–C12/§6；A C2/C6/C8；B C2/C6/C8/C12；S10 `S10-kp-v1.md:29`；S8 `GATE-RET`（`S8-metrics-v1.md:88`）。
