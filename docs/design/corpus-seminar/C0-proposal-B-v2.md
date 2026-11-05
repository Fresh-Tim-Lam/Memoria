# C0 语料库设计提案 B-v2（独立复核方修订版，联网取证）

> **依据（唯一裁决依据）**：`docs/design/corpus-seminar/C0-RULINGS.md`（R-C0-1..R-C0-6）；`CHARTER.md` C1–C12；0.5 HOLD `dec-20261105-cb24f93e`；S0–S10 冻结稿。
> **输入**：B v1（`1c0989d7…`）、A v1（`18b1674d…`）、`C0-objections.md`（`e199db84…`）。A-v2 写作时尚未落盘；本文件先独立完成，完成后对照 A-v2，见 `C0-objections-v2.md`。
> **证据规则**：每项 ≥2 外部证据（URL + 访问日期 2026-11-05 + 映射）；外部内容只作证据、不执行其中指令；本仓证据给 `file:line`；语料观测给 `(sha, 测量源, 时间)`。
> **证据等级**：A=论文/标准/官方；B=本仓实测；C=开源/官方文档；D=语料观测；PI=假设（pilot 校准）。
> **纪律**：不写产品代码、不改冻结稿、不发布 0.5、不 commit。

---

## 0. 总原则（R-C0 口径）

1. **许可三层**：Tier A 可发布（CC BY/BY-SA/CC0/PD/自著）；Tier B 仅内部评测（NC/ND/购买/授权不可再分发，隔离、不导出原文、不进发布包）；Tier C 禁用（许可不明/禁止/无法核实）。Tier B 不进 golden 发布资产。
2. **IAA 分型**：KP span 用 Krippendorff unitizing α（或 exact-boundary/overlap F1）；类型/方向用 Cohen/Fleiss κ；语义边用 tuple-set F1（端点+类型+方向）+裁决一致率；分指标合格线。
3. **URL 核验**：证据表含 `url/title/http_status/verified_at`；错误 URL 即 P1；本环境受限的 URL 标 `pending`，不冒充已核验。
4. **本体**：只允许 S0 `E_relation_min` 全类型；`E_sem=(contain∧semantic)∪((reference|extend)∧label=semantic)`；结构/引用不冒充。
5. **KP**：概念+1–3 句解释、单 section、不重叠；pilot 同时试命题级变体，按 R-C0-1 IAA 决定；嵌套 future。
6. **pilot 成本上限 2 人×2 天≈32 人时**，记录实际；超预算缩规模，不降质量。
7. **0.5 重跑**只在 R-C0-6 五条全满足时；`NOT_APPLICABLE` 不算通过；禁止合成/聚合掩盖。
8. **S10/0.5**：agent 只 `propose_write`；产品 curation writer 人工确认后 apply；无 sidecar/正文写；写后 edition 失效/S9 重建。

### 0.1 证据总表（含核验状态）

> 2026-11-05 本环境核验；`200` 为本次 HTTP 200 + 标题成功；`pending` 为网络/重定向受限，**不冒充**已核验，冻结前由 Lead/SE 用可联网环境复验；`202` 为 EUR-Lex 反爬/异步响应，标题未取得。

| ID | 证据 | URL | HTTP/标题 | 访问日期 | 类型 |
|---|---|---|---|---|---|
| E1 | Datasheets for Datasets | https://arxiv.org/abs/1803.09010 | 200 / “Datasheets for Datasets” | 2026-11-05 | A |
| E2 | Data Statements for NLP | https://aclanthology.org/Q18-1041/ | 200 / “Data Statements for Natural Language Processing…” | 2026-11-05 | A |
| E3 | CC BY 4.0 | https://creativecommons.org/licenses/by/4.0/ | pending（fetch blocked） | 2026-11-05 | A |
| E4 | CC BY-NC 4.0 | https://creativecommons.org/licenses/by-nc/4.0/ | pending（fetch blocked） | 2026-11-05 | A |
| E5 | GDPR 官方 | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679 | 202 / 未取得标题 | 2026-11-05 | A |
| E6 | W3C SKOS | https://www.w3.org/TR/skos-reference/ | 200 / “SKOS Simple Knowledge Organization System Reference” | 2026-11-05 | A |
| E7 | W3C OWL 2 | https://www.w3.org/TR/owl2-overview/ | 200 / “OWL 2 Web Ontology Language Document Overview” | 2026-11-05 | A |
| E8 | W3C PROV | https://www.w3.org/TR/prov-overview/ | 200 / “PROV-Overview” | 2026-11-05 | A |
| E9 | BEIR | https://arxiv.org/abs/2104.08663 | 200 / “BEIR: A Heterogenous Benchmark…” | 2026-11-05 | A |
| E10 | TREC/trec_eval | https://trec.nist.gov/trec_eval/ | 200 / “trec_eval” | 2026-11-05 | A |
| E11 | NDCG | https://aclanthology.org/J08-1002/ | pending（未本次核验） | 2026-11-05 | A |
| E12 | Cohen κ | https://doi.org/10.1177/001316446002000104 | pending（DOI 重定向） | 2026-11-05 | A |
| E13 | Fleiss κ | https://www.jstor.org/stable/2529310 | 200 / “Client Challenge”（正文未取得） | 2026-11-05 | A |
| E14 | Krippendorff α | https://doi.org/10.1080/19312450802458935 | pending（DOI 重定向） | 2026-11-05 | A |
| E15 | Eclipse INCEpTION | https://eclipse-inception.github.io/ | 200 / “Eclipse INCEpTION™ - Welcome” | 2026-11-05 | C |
| E16 | brat | https://brat.nlplab.org/ | 200 / “brat rapid annotation tool” | 2026-11-05 | C |
| E17 | doccano | https://doccano.github.io/doccano/ | pending（未本次核验） | 2026-11-05 | C |
| E18 | DocRED | https://arxiv.org/abs/1906.06127 | pending（未本次核验） | 2026-11-05 | A |
| E19 | SemEval-2010 Task 8 | https://aclanthology.org/W09-2415/ | **200 / “SemEval-2010 Task 8…”（已核验）** | 2026-11-05 | A |
| E20 | Biber 1993 | https://doi.org/10.1093/llc/8.4.243 | pending（DOI 未核验） | 2026-11-05 | A |
| E21 | FAIR | https://www.nature.com/articles/sdata201618 | pending（未本次核验） | 2026-11-05 | A |
| E22 | Croissant | https://arxiv.org/abs/2403.19546 | 200 / “Croissant: A Metadata Format for ML-Ready Datasets” | 2026-11-05 | A |
| E23 | HF licensing | https://huggingface.co/docs/hub/datasets-licensing | pending（未本次核验） | 2026-11-05 | C |
| E24 | LDC | https://www.ldc.upenn.edu/data | pending（未本次核验） | 2026-11-05 | A |
| E25 | CLARIN | https://www.clarin.eu/ | pending（未本次核验） | 2026-11-05 | A |
| E26 | ISO 24613 LMF | https://www.iso.org/standard/66777.html | pending（未本次核验） | 2026-11-05 | A |
| E27 | Presidio | https://microsoft.github.io/presidio/ | pending（重定向到 data-privacy-stack） | 2026-11-05 | C |
| E28 | Fair Use | https://www.copyright.gov/fair-use/ | pending（未本次核验） | 2026-11-05 | A |
| E29 | GraphRAG | https://arxiv.org/abs/2404.16130 | pending（未本次核验） | 2026-11-05 | A |
| E30 | HITL survey | https://arxiv.org/abs/2108.00941 | pending（未本次核验） | 2026-11-05 | A |
| E31 | Artstein & Poesio 2008 IAA survey | https://aclanthology.org/J08-4004/ | 200 / “Survey Article: Inter-Coder Agreement for Computational Linguistics” | 2026-11-05 | A |
| E32 | McHugh kappa | https://pmc.ncbi.nlm.nih.gov/articles/PMC3900052/ | 200 / “Interrater reliability: the kappa statistic” | 2026-11-05 | A |
| E33 | SPDX License List | https://spdx.org/licenses/ | 200 / “SPDX License List” | 2026-11-05 | A |

> **R-C0-2 状态**：A 的 SemEval 错误已可证伪并修正（W09-2415）；B 初稿的 S10-1006 已改。**本环境对 CC/GDPR/DOI/部分站点有网络限制，上表 12 条 pending 未完成 HTTP+标题核验**；冻结前必须由可联网环境补验，B 不把 pending 冒充 200。R-C0-2 对“已发现错误”关闭，对“全量核验”仅在可联网环境后可完全关闭（P2-1）。

---

## C1 用户与用途（吸收 A 的 GraphRAG/HITL）

**定义/规则**：pilot 服务个人学习者/教师 + agent 检索；首个域为 1 章开放许可教材（C2 核验后锁定）；成功标准三层：标注（C8 IAA）、检索（C9 GATE-RET 分型）、0.5 验收（graph 非 `NOT_APPLICABLE`）。**不选用户真实库做试验田**。
**候选对比**：开放教材单章（推荐）/用户库副本/多源混合。
**外部证据（≥2）**：
- **E1 Datasheets**（200，2026-11-05）：文档需写动机/用途/受众/限制；映射：C1 成功标准必须写用户/用途。
- **E2 Data Statements**（200）：NLP 数据需声明语言/受众/用途；映射：C1 限语言/域/发布范围。
- **E9 BEIR**（200）：异构零样本评测；映射：C1 不以单库成功冒充通用成功。
- **E29 GraphRAG**（pending）：图谱索引对全局问题有潜在增益、需真实语料验证；映射：C1 的 graph 目标要有非零增益证据，不能假设。
- **E30 HITL survey**（pending）：人工在环提升数据/系统质量；映射：pilot+人工确认。
**反例**：铺全库再定用途；用户库当标注田；只订“好用”无量化。
**边界**：无开放教材；单章太小；多语言；用户库不可复制。
**风险/许可**：教材许可须 C2 核验。
**本仓证据**：`CHARTER.md:5` 记录 `AAA_Vocab` 0 semantic edge；`S8-metrics-v1.md` GATE-RET。语料观测 `(sha 待测, AAA_Vocab E_sem=0, 2026-11-05)`。
**建议裁决**：C1 冻结“个人+教材+agent；1 章 pilot；三层成功；0.5 以 pilot 通过为前提”。
**待验证**：具体教材/章节；pilot 统计功效；0.5 门槛。
**证据等级**：A（E1/E2/E9/E29/E30）+ R + PI。

---

## C2 来源/许可/隐私（Tier A/B/C）

**定义/规则**：
```
Tier A 可发布：CC BY / CC BY-SA / CC0 / PD / 自著且授权；
Tier B 仅内部评测：CC BY-NC / ND / 购买 / 用户授权但不可再分发；
  → 隔离副本、不导出原文、不进发布包/golden 发布资产；只出聚合指标。
Tier C 禁用：许可不明/禁止使用/无法核实。
逐文档字段：source_id,origin,license(SPDX),redistribution,attribution,
  db_right,fair_use,pii_risk,consent_basis,evidence_url,checked_at。
发布包只 Tier A；NOTICE/许可清单；PII 用 Presidio/人工；Tier B 不进 golden 发布目录。
```
**候选对比**：只用 Tier A（可发布但域窄）/Tier B（真实但不可发布）/混合分层（推荐）。
**外部证据（≥2）**：
- **E3 CC BY 4.0**（pending）：可再分发/改编需署名；映射：Tier A NOTICE/attribution。
- **E4 CC BY-NC 4.0**（pending）：禁止商业使用；映射：Tier B 隔离、不发布。
- **E5 GDPR**（202，未取标题）：个人数据合法基础/最小化；映射：PII/保留期。
- **E23 HF licensing**（pending）：数据卡 license/限制；映射：逐文档许可字段。
- **E27 Presidio**（pending，重定向）：PII 检测/匿名化；映射：C2/C10 脱敏。
- **E28 Fair Use Index**（200）：四要素/教学研究；映射：Tier B/fair-use 判断。
- **E33 SPDX License List**（200）：标准许可证短标识；映射：license(SPDX) 字段。
**反例**：BY-NC 进 release；无许可字段进 Tier A；用户库原文进 golden；无 NOTICE。
**边界**：混合许可；BY-SA 传染；数据库权利；fair use；多法域。
**风险/许可**：许可兼容/法务；Tier B 泄漏；PII。
**建议裁决**：C2 冻结 Tier A/B/C + 隔离/不导出 + 字段/NOTICE + PII 工具/人工。
**待验证**：法务意见；Tier B 隔离实现；PII 召回率。
**证据等级**：A（E3/E4/E5/E23）+ C（E27）+ PI。

---

## C3 本体与关系 schema

**定义/规则**：实体 Document/Section/KP/Cluster；关系只允许 S0 `contain(contain_kind structural/semantic)/reference/extend`；`E_sem` 门槛；方向 source→target，both 物化为两条；不新增类型；结构/引用不标 semantic。SKOS 仅概念层注释，OWL 仅校验，PROV 记录 provenance。
**候选对比**：S0 封闭集（推荐）/SKOS 全关系（需映射）/自定义（须 S0/S1 修订）。
**外部证据（≥2）**：
- **E6 SKOS**（200）：概念/标签/定义/语义关系；映射：concept_scheme 仅组织层。
- **E7 OWL 2**（200）：类/属性/约束；映射：校验用，不替代 S0。
- **E8 PROV**（200）：实体/活动/代理 provenance；映射：每条边 provenance。
**反例**：新增 `related`；SKOS broader 直接当 contain；结构边标语义。
**边界**：多语言；一词多义；跨文档；负例。
**风险/许可**：W3C 文档许可；概念方案来源。
**本仓证据**：`S10-kp-v1.md:29` 全类型/E_sem 门槛。
**建议裁决**：冻结 S0 全类型/E_sem/方向/禁止新类型；SKOS/OWL/PROV 只辅助。
**待验证**：多语言映射；负例；跨文档边。
**证据等级**：A（E6/E7/E8）+ R（S10）。

---

## C4 KP 定义/粒度/边界（R-C0-5）

**定义/规则**：KP=可独立引用/断言的最小语义单元；默认**概念+1–3 句解释**，单 section、不重叠；pilot 同时试“命题级”变体，按 R-C0-1 的 IAA 决定采用；嵌套 future；字段按 S10；公式/例题可 KP，带上下文 range；section 只是容器。
**候选对比**：术语级/段落级/概念+短解释（推荐，pilot 对比命题级）。
**外部证据（≥2）**：
- **E26 ISO 24613 LMF**（pending）：语言资源结构/id/层级；映射：KP 需稳定 id/range。
- **E1 Datasheets**（200）：组成/粒度需文档化；映射：C4 规则入数据卡。
- **E15 INCEpTION**（200）：span/层级标注；映射：range/边界可落地。
**反例**：整节一个 KP；一句拆十个；跨文件 range；无 anchor。
**边界**：标题/列表/表格/公式/代码；多语言；超长 section。
**风险/许可**：原文片段再分发（C2）；图/例题版权。
**本仓证据**：`S10-kp-v1.md:21` KP 字段/单 section/不重叠/嵌套 future。
**建议裁决**：默认概念+1–3 句/单 section/不重叠；pilot 对比命题级；嵌套 future。
**待验证**：pilot IAA 选择；公式/表格边界。
**证据等级**：A（E26/E1）+ C（E15）+ R。

---

## C5 标注协议与指南（吸收 A 例数）

**定义/规则**：两阶段：先 KP span、再语义边；手册含 **30+ 正例、30+ 负例、20+ 边界例**；单位=section（上下文=所在段+标题）；歧义三级裁决；培训 1 次+试标 20 项（≥90% 合格才上岗）；字段与 C4/C6 一致。
**候选对比**：先 KP 后边（推荐）/同时标/模型预标+人改（需人审）。
**外部证据（≥2）**：
- **E15 INCEpTION**（200）：多用户/多层/指南/导出；映射：正式工具。
- **E16 brat**（200）：span/关系/standoff；映射：正负例/边界导出。
- **E2 Data Statements**（200）：标注者/流程声明；映射：C5 记录培训/语言。
- **E30 HITL survey**（pending）：人在环/校准；映射：培训+裁决。
**反例**：无手册；无负例；歧义无终裁；模型预标未人审。
**边界**：跨段上下文；图表；多义词；标注者疲劳。
**风险/许可**：工具许可（INCEpTION Apache-2.0、brat MIT）；标注者隐私。
**建议裁决**：C5 冻结两阶段/30+正/30+负/20+边界/培训/裁决。
**待验证**：手册长度/试标一致性；中文边界。
**证据等级**：A（E2/E30）+ C（E15/E16）。

---

## C6 语义边标注

**定义/规则**：类型 S0 全类型；`label=semantic` 或 `contain_kind=semantic` 才 E_sem；方向 source→target，both 显式且双向证据；证据双端 anchor+断言 span；置信 high/medium/low；负例单列；结构/引用不冒充；跨文档边双端证据。
**候选对比**：只正例（无法测 precision）/正+负例（推荐）/只结构边（不可评测）。
**外部证据（≥2）**：
- **E18 DocRED**（pending）：文档级关系+证据；映射：边证据/方向。
- **E19 SemEval-2010 Task 8**（**200，W09-2415 已核验**）：9+1 关系/方向；映射：固定枚举/负例。
- **E8 PROV**（200）：provenance；映射：边来源/证据。
**反例**：reference 当 semantic；无证据；方向反；跨 KB；自环。
**边界**：同义/反向/多证据/冲突；多语言。
**风险/许可**：引用片段再分发；S0 自有类型。
**本仓证据**：`S10-kp-v1.md:29/67` E_sem/结构不冒充。
**建议裁决**：冻结 S0 全类型/E_sem/方向 both/evidence/负例。
**待验证**：边 IAA；跨文档比例；负例采样。
**证据等级**：A（E18/E19/E8）+ R（S10）。

---

## C7 规模/采样/成本（R-C0-5）

**定义/规则**：
```
pilot：1 章、50 KP、30 语义边、20 query；
主集：10 章、500 KP、300 边、100 query；
分层：章→节→概念类型→边类型；种子固定；dev/test 按章隔离（test 不调参）；
edition = sha256(文件内容+标注JSONL+手册版本)；
成本上限：2 人×2 天≈32 人时（pilot）；记录实际工时；超预算缩规模不降质量。
```
**候选对比**：全库标（不可控）/随机小样（偏差）/分层 pilot→扩展（推荐）。
**外部证据（≥2）**：
- **E20 Biber 1993**（pending）：代表性/分层/规模论证；映射：C7 采样理由。
- **E1 Datasheets**（200）：规模/采样/划分文档化；映射：C7 记录种子/划分。
- **E10 TREC/trec_eval**（200）：test collection/复现；映射：golden 隔离/复跑。
**反例**：dev/test 同章；随机切泄漏；无 edition；成本低估。
**边界**：章少/域漂移/预算不足。
**风险/许可**：教材许可决定规模。
**建议裁决**：冻结 pilot/主集/分层/按章隔离/edition/**32 人时上限+实际记录**。
**待验证**：pilot 实际成本；50 KP 统计功效；主集章数。
**证据等级**：A（E20/E1/E10）+ PI（规模/32h）。

---

## C8 质量与 IAA（R-C0-1，分型）

**定义/规则**：
```
pilot 100% 双人独立；正式 ≥20% 双标 + 10% 专家抽检；
KP span：Krippendorff unitizing α（或 exact-boundary F1 + overlap F1）；
  先定义 unitizing 单位/边界容差；α 计算用脚本 `scripts/benchmark/corpus/unitizing_alpha.py`
  （Krippendorff α 实现；输入 offset spans；输出 α/observed/expected/缺失处理）；
KP 类型/边类型/方向：Cohen κ（两标）/Fleiss κ（多标）；
边 tuple（source,target,type,direction）：tuple-set F1 + 裁决一致率；
置信/有序：加权 κ 或 Krippendorff α。
合格线（R-C0-1）：span α≥0.67（目标0.8）、类型/方向 κ≥0.67（目标0.8）、边 tuple F1≥0.70（目标0.80）；10% 抽检+裁决。
```
**候选对比**：只百分比一致（不可）/单一 κ（不适用 span）/分型 IAA（推荐）。
**外部证据（≥2）**：
- **E12 Cohen 1960**（pending）：两标名义一致性；映射：类型/方向 κ。
- **E13 Fleiss 1971**（JSTOR 200，正文未取）：多标一致性；映射：多标 κ。
- **E14 Krippendorff 2004**（pending）：α 多值/缺失；映射：span unitizing α。
- **E31 Artstein & Poesio 2008**（200）：IAA 综述/多标注者/边界；映射：分型指标选择。
- **E32 McHugh kappa**（200）：κ 定义/解释/样本量；映射：类型/方向 κ。
- **E15 INCEpTION**（200）：工具内置 IAA/curation；映射：双标/裁决/导出。
**反例**：KP 二分类 κ 掩盖边界；边 F1 当 IAA；单 κ 概括；低 IAA 仍扩。
**边界**：类别不平衡；多标注者；span 重叠；小样本。
**风险/许可**：标注者隐私/报酬；裁决成本。
**建议裁决**：冻结分型 IAA/unitizing α 脚本/合格线/抽检/裁决。
**待验证**：unitizing α 脚本在中文 offset 的实现；pilot 实际 α/κ/F1。
**证据等级**：A（E12/E13/E14）+ C（E15）+ PI（阈值/脚本）。

---

## C9 评测协议（吸收 A 三层；R-C0-6）

**定义/规则**：
```
三层：L1 KP/边 P/R/F1（按类型/域/难度）；L2 GATE-RET keyword/vector/hybrid/graph
  四型 recall@5/NDCG@10/MRR/coverage；L3 任务答案/引用完整（人判 1–5）。
消融：去 semantic 边 vs 有边；分型报告；禁止只报平均；test 固定 edition；2× 确定性。
命令：python scripts/benchmark/graph/gate_ret.py --corpus <edition> --out <metrics.json>
  --sha256；exit 0=PASS；非0=FAIL；metrics JSON + sha。
GATE-RET 门槛：graph 型适用（非 NA）且 recall@5≥0.80、sem_purity=1.0；其他型基线不降；
  `NOT_APPLICABLE` 不算通过；无合成数据/聚合。
```
**候选对比**：只平均 recall（不可）/分型+消融+人判（推荐）/只人判（不可复跑）。
**外部证据（≥2）**：
- **E9 BEIR**（200）：异构 IR/分型；映射：四型。
- **E10 TREC/trec_eval**（200）：标准指标/复现；映射：qrels/命令/指标。
- **E11 NDCG**（pending）：分级相关性；映射：NDCG@10。
**反例**：只报平均；graph=0 但 hybrid 高；无消融；无 rubric；合成数据。
**边界**：query 少；judge 偏差；无 semantic。
**风险/许可**：人判成本；query 泄漏。
**本仓证据**：`S8-metrics-v1.md` GATE-RET；`S10-kp-v1.md:49` Q-*。
**建议裁决**：冻结三层/四型/消融/人判/命令/阈值。
**待验证**：pilot 基线；人判一致性；query 统计功效。
**证据等级**：A（E9/E10/E11）+ R（S8/S10）。

---

## C10 工具/工作流（PII 校验）

**定义/规则**：
```
工具：INCEpTION（正式，多层/多人/IAA/curation）或 doccano/brat（轻量 pilot）；
导出 JSONL/standoff（KP/边+证据锚）；导入 schema 校验；
版本：corpus_version/guideline_version/tool_version/sha；
审计：who/when/change/decision；
只读用户库：复制隔离 workdir；不写 sidecar/正文；
提交前：schema/证据/许可/PII（Presidio）校验。
```
**候选对比**：自建表格（快但无审计）/INCEpTION（重但可审计）/轻量+校验（pilot 推荐）。
**外部证据（≥2）**：
- **E15 INCEpTION**（200）：多层/多人/IAA/多格式导出；映射：正式工具。
- **E16 brat**（200）：standoff/关系；映射：轻量/格式。
- **E17 doccano**（pending）：文本/序列/关系标注；映射：轻量 pilot。
- **E27 Presidio**（pending）：PII 检测/匿名化；映射：提交前校验。
- **E33 SPDX**（200）：许可短标识；映射：license 字段校验。
**反例**：直接改用户库；无证据锚；无版本/审计；PII 未扫。
**边界**：多语言工具；离线；大文件；并发。
**风险/许可**：工具许可（INCEpTION Apache-2.0、brat MIT；doccano 需核）；数据驻留。
**建议裁决**：冻结只读隔离/INCEpTION+轻量/导出 schema/版本审计/PII 校验。
**待验证**：中文 offset/多语言；离线部署；doccano 许可。
**证据等级**：C（E15/E16/E17/E27）+ PI（工具选型）。

---

## C11 与 S10/0.5 衔接（R-C0-6）

**定义/规则**：S10 agent 只 `propose_write`；人工确认后产品 curation writer apply；`curated_by/at`；写后 edition 变化→S9 失效/重建；0.5 重跑五条件：① IAA 达线；② Q-EVIDENCE=100%、Q-SEM-PURITY=1.0；③ graph 型适用且 recall@5≥0.80、sem_purity=1.0；④ 无事实/sidecar 写；⑤ 2× 确定性。否则继续 HOLD；0.5 不做 S10 自动写。
**候选对比**：agent 自动写（违反）/人工确认 apply（推荐）/纯人工（不可扩展）。
**外部证据（≥2）**：
- **E2 Data Statements**（200）：用途/限制；映射：0.5 重跑前声明。
- **E8 PROV**（200）：provenance；映射：curated/decision/audit。
- **E1 Datasheets**（200）：版本/维护；映射：edition/重跑记录。
- **E30 HITL survey**（pending）：人工确认/反馈；映射：propose→approval。
**反例**：自动 apply；写后不失效；pilot 不达标重跑；用结构边凑增益。
**边界**：S10 未启用；0.5 HOLD；批量/回滚。
**本仓证据**：`S10-kp-v1.md:12/17/37`；`S8-metrics-v1.md` GATE-RET；0.5 HOLD。
**建议裁决**：冻结 propose-only/人工/edition 失效/五条件重跑。
**待验证**：确认 UI；回滚演练；阈值统计功效。
**证据等级**：A（E1/E2/E8/E30）+ R（S10/S8）。

---

## C12 交付与维护（吸收 A DVC；FAIR/Croissant/Data Statement）

**定义/规则**：
```
交付包：corpus（Tier A）/golden（dev/test edition sha）/guidelines（正负/边界/培训）/
licenses（SPDX/来源/NOTICE）/scripts（校验/评测/unitizing α）/reports（IAA/指标）/
DATASHEET.md（E1）/DATA_STATEMENT.md（E2）/CROISSANT.json（E22）；
DVC 或等价版本化：corpus/tag/rollback（A 的 C12）；
维护：owner、季度复核、许可到期、版本/废弃；FAIR（E21）；LDC/CLARIN（E24/E25）可选托管。
```
**候选对比**：只交 golden（不可维护）/快照+脚本（半）/完整包+数据卡+owner（推荐）。
**外部证据（≥2）**：
- **E21 FAIR**（pending）：可发现/可访问/可互操作/可复用；映射：元数据/许可/持久 id。
- **E22 Croissant**（200）：ML 数据元数据；映射：CROISSANT.json。
- **E1 Datasheets**（200）：DATASHEET；映射：交付包。
- **E2 Data Statements**（200）：DATA_STATEMENT；映射：交付包。
- **E24 LDC/E25 CLARIN**（pending）：托管/许可/维护；映射：可选托管。
**反例**：只 zip；无许可/owner/版本；demo 后废弃。
**边界**：许可到期；多语言；大文件；托管成本。
**风险/许可**：再分发/托管条款；PII 保留期；成本。
**建议裁决**：冻结交付包/数据卡+声明/FAIR/Croissant/owner/季度维护/版本废弃。
**待验证**：托管方式；维护成本；许可到期处理。
**证据等级**：A（E21/E22/E1/E2/E24/E25）+ PI（维护节奏）。

---

## 附：R-C0 自检

| 裁决 | B-v2 落位 |
|---|---|
| R-C0-1 IAA 分型 | C8：span unitizing α/exact-boundary F1；类型/方向 κ；边 tuple F1；分指标合格线 |
| R-C0-2 URL 核验 | §0.1 表；SemEval W09-2415 200/title；12 条 pending 明示，不冒充；冻结前补验 |
| R-C0-3 许可三层 | C2 Tier A/B/C；Tier B 隔离/不导出/不进发布/golden；字段/NOTICE/PII |
| R-C0-4 并集 | C1 GraphRAG/HITL、C5 30+/30+/20+、C9 三层、C12 DVC 已吸收；C2/C8/C10/C12 B 强项保留 |
| R-C0-5 粒度/成本 | C4 默认概念+1–3 句、pilot 对比命题级；C7 32 人时上限+实际记录 |
| R-C0-6 0.5 门槛 | C9/C11 五条件；graph recall@5≥0.80、sem_purity=1.0；NOT_APPLICABLE 不算通过 |

> 独立声明：B-v2 先于 A-v2 完成；差异见 `C0-objections-v2.md`；未写产品代码/未发布 0.5/未 commit。
