# C0 异议与 A/B 差异 v2（修订轮复核）

> **依据（唯一裁决依据）**：`docs/design/corpus-seminar/C0-RULINGS.md`（R-C0-1..R-C0-6）。
> **对象**：`C0-proposal-A-v2.md`（主办研究，sha **`fc9a927a068d4281c7b23b8153cfd99ab02b8d47ebe40636fd3c85895cfdfa34`**，27,837 B）与 `C0-proposal-B-v2.md`（本复核方，sha **`125429dcf7abe0033e7ba516b802e04eacaa83dc19944f63b87c99ddeffea3b4`**，25,712 B）。
> **性质**：B-v2 以 R-C0 为依据独立修订；完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=论文/标准/官方；B=本仓冻结/实测；C=开源/官方文档；D=语料观测；PI=假设。

---

## 0. R-C0 关闭矩阵

| 裁决 | A-v2 | B-v2 | 判定 |
|---|---|---|---|
| R-C0-1 IAA 分型 | C8 分型表：KP span unitizing α/边界 F1；类型/方向 κ；边 tuple F1+裁决；分指标合格线；100% 双标+10%抽检 | C8 同口径；补 `unitizing_alpha.py` 实现计划/输入输出；分指标合格线 | **关闭** |
| R-C0-2 URL HTTP+标题核验 | A-v2 声称全部 HTTP 200 + title（17 条表）；SemEval 改 W09-2415 | B 独立核验：核心证据每项 ≥2 条 200/标题（含 W09-2415、Artstein J08-4004、McHugh PMC3900052、SPDX、TREC、INCEpTION、brat、Croissant、Datasets、Data Statements、SKOS/OWL/PROV/BEIR）；**11 条补充 URL 标 pending**（CC/GDPR/DOI/ISO 等网络受限） | **对已发现错误关闭**；A 全量 200 声称需 Lead/SE 复验；B pending 不冒充 200（P2-1） |
| R-C0-3 许可 Tier A/B/C | A-v2 Tier A/B/C；字段/NOTICE/Presidio；Tier B 不进发布/golden | B-v2 同；补 SPDX/Fair Use；Tier B 隔离/不导出/仅聚合 | **关闭** |
| R-C0-4 并集 | A 吸收 B 的 C2/C8/C10/C12；A 保留 C1 GraphRAG/HITL、C5 例数、C9 三层、C12 DVC | B 吸收 A 的 C1/C5/C9/C12；保留 B 的 Tier+Presidio、span IAA、PII、FAIR/Croissant/Data Statement | **关闭**（差异见 §1） |
| R-C0-5 粒度/成本 | 默认概念+1–3 句；pilot 对比命题级；32 人时上限+实际记录 | 同 | **关闭** |
| R-C0-6 0.5 门槛 | 五条件：IAA/Q-EVIDENCE/Q-SEM-PURITY/graph 适用 recall@5≥0.80/无写/2× | 同；C9 加 GATE-RET 命令/指标 JSON sha/exit | **关闭** |

**结论**：R-C0-1/3/4/5/6 **关闭**；R-C0-2 **对 A 的 SemEval 错误与核心证据集关闭**，但 B 有 11 条补充 URL pending、A 全量 200 声称需独立复核，列为 **P2-1**（不构成 P0/P1，因为每个 C 项的 ≥2 核心证据均已 200/标题核验；pending 仅补充/替代来源）。**两版无 P0/P1**。

---

## 1. A-v2 / B-v2 逐项差异（C1–C12）

| 项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| C1 用户 | 开放教材单章；GraphRAG/HITL/BEIR；三层成功 | 同；Datasheets/Data Statements/BEIR + GraphRAG/HITL | 一致；B 吸收 A 的 GraphRAG/HITL。 |
| C2 许可 | Tier A/B/C；CC BY/GDPR；Presidio；逐文档字段/NOTICE | 同；+SPDX/Fair Use；Tier B 隔离/仅聚合；PII 工具 | 一致；B 多 SPDX/FAIR use；A 多 CC 直链。 |
| C3 本体 | S0 全类型 + SKOS/OWL/schema.org；E_sem | S0 全类型 + SKOS/OWL/PROV；E_sem | 一致；A 多 schema.org，B 多 PROV。 |
| C4 KP | 概念+1–3 句；单 section；pilot 命题级；嵌套 future | 同；ISO LMF/INCEpTION | 一致。 |
| C5 协议 | 30+正/30+负/20+边界；培训/裁决 | 同；Data Statements/HITL | 一致；A 例数已吸收。 |
| C6 语义边 | S0 全类型/E_sem/方向/证据/负例；SemEval W09-2415（已修） | 同；DocRED/SemEval/PROV | 一致；A 已修 URL。 |
| C7 规模/成本 | pilot 50/30/20；32 人时；按章隔离 | 同；32h+实际记录；Biber/Datasheets/TREC | 一致；B 明确成本记录。 |
| C8 IAA | 分型：span α/边界 F1、类型 κ、边 tuple F1；Artstein/McHugh | 同；+unitizing α 脚本/输入输出；E31/E32 | 一致；**B 多实现脚本，A 多 IAA 综述**；可合并。 |
| C9 评测 | 三层/四型/消融/人判；GATE-RET 逐型 | 同；+GATE-RET 命令/JSON sha/exit；graph recall@5≥0.80 | 一致；**B 多可执行命令/阈值**；A 需补（P2-2）。 |
| C10 工具 | INCEpTION/brat/CoNLL/Croissant；PII Presidio | INCEpTION/doccano/brat/Presidio/SPDX；PII；只读隔离 | 一致；B 多 doccano/SPDX；A 多 CoNLL/Croissant。 |
| C11 S10/0.5 | propose-only/人工/edition 失效；五条件 recall@5≥0.80 | 同；+GATE-RET 命令 | 一致；B 多命令。 |
| C12 交付 | Datasheet/Croissant/Data Statement/FAIR/DVC | 同；FAIR/Croissant/Data Statement/DVC；owner/维护 | 一致；B 多 owner/维护，A 多 DVC 说明。 |

**总判断**：A-v2 在 C8 的 IAA 综述（Artstein/McHugh）、C2 CC 直链、C10 CoNLL/Croissant 上更强；B-v2 在 C8 unitizing 脚本、C9 GATE-RET 命令/JSON sha、C10 SPDX/Presidio、C12 owner/维护上更可执行。**差异均为 P2 合并项，无 P0/P1**。

---

## 2. 仍未解决 3 点（P2）

### P2-1 URL 全量核验：A 全量 200 声称 vs B 11 条 pending
- **现状**：A-v2 证据表声称所有 URL HTTP 200+title（17 条）；B-v2 独立核验的核心证据（E1/E2/E6/E7/E8/E9/E10/E15/E16/E19/E22/E28/E31/E32/E33 等）为 200+title；但 CC/GDPR/DOI/ISO/HF/NDCG/DocRED/LDC/CLARIN/Biber/DVC 等 11 条补充 URL 在本环境超时/重定向/反爬，B 标 pending，**不冒充 200**。每个 C 项的 ≥2 核心证据已核验，但“全量 URL 核验”未在 B 侧完成。
- **影响**：A 的“全部 200”与 B 的 pending 不一致；若补充证据被用于正文映射，需人工复核。
- **建议**：Lead/SE 用可联网浏览器/curl 对 A/B 全部 URL 做一次 `HTTP 200 + <title>` 复核，产 `C0-URL-VERIFY.json`（url/title/status/verified_at/used_in）；B 的 pending 在核验后改 200 或删除；**不把 pending 写成已核验**。
- **证据**：R-C0-2；B-v2 §0.1；A-v2 证据表。

### P2-2 C9/C11 GATE-RET 可执行契约合并
- **现状**：A-v2 C9 有三层/分型/消融/人判，但无命令/指标 JSON sha/exit；C11 有 recall@5≥0.80 门槛。B-v2 C9 有 `gate_ret.py` 命令/`metrics.json+sha`/exit，但需 SE 确认脚本路径/参数/与 S9 `eval-retrieval` 关系。
- **影响**：GATE-RET 仍可能两套命令；S8 gate 无法引用唯一产物。
- **建议**：SE/S8a 冻结唯一 GATE-RET 命令/参数/exit/产物路径；A/B 合并；pilot 先跑基线；未校准前阈值 soft。
- **证据**：R-C0-6；A-v2 C9/C11；B-v2 C9。

### P2-3 C8 unitizing α 实现与工具合并
- **现状**：A-v2 C8 给出分型 IAA/Artstein/McHugh，但未给 unitizing α 脚本/输入输出；B-v2 给 `scripts/benchmark/corpus/unitizing_alpha.py`（offset spans、α/observed/expected/缺失），但脚本未实现/未验证；INCEpTION 内置 IAA 是否能直接算 unitizing α 未确认。
- **影响**：pilot IAA 可能仍手工/口径不一致；span 部分重叠/缺失处理需脚本。
- **建议**：SE/标注负责人实现 `unitizing_alpha.py`（或采用成熟 Krippendorff α 库）并用 10 条合成 span 做单测；INCEpTION 导出 offset 后跑脚本；pilot 报告 α/observed/expected/样本/缺失。
- **证据**：R-C0-1；A-v2 C8；B-v2 C8。

---

## 3. 点名审查结论（v2）

1. **来源/许可/隐私可发布/只挑容易语料**：A/B **PASS**（Tier A/B/C；Tier B 隔离/不导出/不进发布/golden；PII Presidio+人工；NOTICE/SPDX/Fair Use）；教材尚未实际锁定（P2，pilot 前）。
2. **本体/关系与 S0/S10 对齐；语义边证据/方向/负例**：A/B **PASS**（S0 全类型/E_sem/方向/双端证据/负例；A SemEval W09-2415 已核验）。
3. **KP 粒度/边界/嵌套可标注**：A/B **PASS**（概念+1–3 句/单 section/不重叠；pilot 对比命题级；嵌套 future）。
4. **标注协议/IAA/合格线可执行**：A/B **PASS**（分型 IAA；100% 双标；10% 抽检；span α≥0.67/类型 κ≥0.67/边 tuple F1≥0.70）；unitizing 脚本 P2-3。
5. **规模/采样/dev-test/成本现实**：A/B **PASS**（pilot 50/30/20；32 人时上限+实际记录；按章隔离；edition）。
6. **评测分型/禁止聚合**：A/B **PASS**（四型/消融/人判；GATE-RET 逐型；graph recall@5≥0.80；NOT_APPLICABLE 不算通过）；命令/阈值 P2-2。
7. **工具/只读用户库/版本/审计**：A/B **PASS**（隔离副本；不写 sidecar/正文；版本/审计；INCEpTION/brat/doccano/Presidio）。
8. **S10/0.5 衔接/交付维护**：A/B **PASS**（propose-only/人工/edition 失效；五条件重跑；交付包/数据卡/FAIR/Croissant/Data Statement/owner）。
9. **证据质量（博客/可复核/许可依据）**：A/B 以论文/标准/官方为主 **PASS**；A 全量 200 声称与 B pending 不一致（P2-1），不构成 P1，因为核心证据每 C 项 ≥2 已核验。
10. **A/B 差异未静默合并**：见 §1；B 已在 v2 主动披露初稿 SemEval 错误并修正。

---

## 4. 最严重 3 条 / 结论

1. **P2-1 URL 全量核验**：A 声称全部 200；B 核心证据 200/title 已核验，但 11 条补充 pending（CC/GDPR/DOI/ISO 等）。Lead/SE 用可联网环境出 `C0-URL-VERIFY.json`；pending 改 200 或删除，不冒充。
2. **P2-2 GATE-RET 可执行契约**：合并 A 的三层/分型与 B 的命令/JSON sha/exit；SE 冻结唯一命令/路径/产物；graph recall@5≥0.80；未校准前 soft。
3. **P2-3 unitizing α 实现/工具**：合并 A 的 IAA 综述与 B 的脚本计划；实现并单测 `unitizing_alpha.py`（或成熟库），INCEpTION 导出 offset 后跑；pilot 报告 α/observed/expected/缺失。

- **两版无 P0/P1**；R-C0-1/3/4/5/6 关闭，R-C0-2 对已发现错误/核心证据集关闭、全量核验列 P2-1。A-v2 与 B-v2 已收敛；剩余均为 S8a/SE/pilot 可执行细节。未写产品代码/未发布 0.5/未 commit；差异逐项列出未静默合并。

> 参考锚：R-C0 `C0-RULINGS.md:17-43`；A-v2 C8/C9/C10/C11；B-v2 C8/C9/C10/C11；`CHARTER.md` C1–C12/§6。
