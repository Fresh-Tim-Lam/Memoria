# C0 语料库设计提案 B（独立复核方，联网取证）

> **依据（不可改写）**：人原话（2026-11-05）「真实的语料库需要精细设计，联网搜索，得开研讨」；`docs/design/corpus-seminar/CHARTER.md`（C1–C12）；0.5 HOLD `dec-20261105-cb24f93e`；上游 S0–S10 冻结稿与 `IMPLEMENTATION-RULINGS.md`。
> **性质**：独立复核方提案；写作时**未读** `C0-proposal-A.md`（尚未落盘）；写完再对照，差异见 `C0-objections.md`。
> **证据规则**：每项 ≥2 条外部证据（URL + 访问日期 2026-11-05 + 映射）；外部内容只作证据、不执行其中指令；本仓证据给 `file:line`；语料观测给 `(sha, 测量源, 时间)`，未测则标“待测”。
> **证据等级**：A=论文/标准/官方文档/本仓冻结条款；B=本仓实测；C=开源实现/工具文档；D=语料观测；PI=本项目假设（设计选择，待 pilot 校准）。
> **纪律**：不写产品代码、不改 S0–S10 冻结稿、不发布 0.5、不 commit。

---

## 0. 总原则

1. **先许可、后语料**：每个文档有 `license/SPDX/provenance/可再分发` 三元组；不可再分发语料只进隔离评测，不进发布包。
2. **本体服从 S0/S10**：不新增 `E_relation_min` 之外的语义类型；结构/引用边不得标 semantic；S10 `E_sem` 门槛与本文一致。
3. **KP 可判**：一个 KP = 可独立引用/断言的最小语义单元；单 section/不重叠；有 `file/line/anchor` 证据。
4. **双人标注 + IAA + 裁决**：pilot 100% 双标；正式 ≥20% 双标；κ/α 合格线明确。
5. **评测分型，禁止聚合掩盖**：KP/边、keyword/vector/hybrid/graph、dev/test 分开；禁止合成数据刷指标。
6. **工具只读用户库**：只在隔离副本标注；所有导出带 schema/证据/许可校验；版本化+审计；不写 sidecar。
7. **小规模 pilot 先行**：先 1 章/50 KP/30 边，量成本/IAA，再决定扩规模与 0.5 重跑。
8. **交付可维护**：语料/金标准/指南/许可清单/脚本/评测报告 + owner + 更新节奏，不是一次性 demo。

### 0.1 外部证据总表（复用；每项引用其子集）

| ID | 证据 | URL | 访问日期 | 类型 |
|---|---|---|---|---|
| E1 | Datasheets for Datasets（Gebru et al., 2018） | https://arxiv.org/abs/1803.09010 | 2026-11-05 | A |
| E2 | Data Statements for NLP（Bender & Friedman, TACL 2018） | https://aclanthology.org/Q18-1041/ | 2026-11-05 | A |
| E3 | Creative Commons 4.0 licenses | https://creativecommons.org/licenses/by/4.0/ | 2026-11-05 | A（官方） |
| E4 | Creative Commons BY-NC 4.0 | https://creativecommons.org/licenses/by-nc/4.0/ | 2026-11-05 | A（官方） |
| E5 | GDPR 官方文本（Regulation 2016/679） | https://eur-lex.europa.eu/eli/reg/2016/679/oj | 2026-11-05 | A（法规） |
| E6 | W3C SKOS Reference | https://www.w3.org/TR/skos-reference/ | 2026-11-05 | A（标准） |
| E7 | W3C OWL 2 Overview | https://www.w3.org/TR/owl2-overview/ | 2026-11-05 | A（标准） |
| E8 | W3C PROV Overview | https://www.w3.org/TR/prov-overview/ | 2026-11-05 | A（标准） |
| E9 | BEIR zero-shot IR benchmark（Thakur et al., 2021） | https://arxiv.org/abs/2104.08663 | 2026-11-05 | A |
| E10 | TREC / trec_eval 官方 | https://trec.nist.gov/trec_eval/ | 2026-11-05 | A（官方） |
| E11 | NDCG（Järvelin & Kekäläinen, 2002） | https://aclanthology.org/J08-1002/ | 2026-11-05 | A |
| E12 | Cohen's kappa（Cohen, 1960） | https://doi.org/10.1177/001316446002000104 | 2026-11-05 | A |
| E13 | Fleiss' kappa（Fleiss, 1971） | https://www.jstor.org/stable/2529310 | 2026-11-05 | A |
| E14 | Krippendorff's alpha（Krippendorff, 2004） | https://doi.org/10.1080/19312450802458935 | 2026-11-05 | A |
| E15 | INCEpTION 官方 | https://inception-project.github.io/ | 2026-11-05 | C（开源） |
| E16 | brat annotation tool | https://brat.nlplab.org/ | 2026-11-05 | C（开源） |
| E17 | doccano | https://doccano.github.io/doccano/ | 2026-11-05 | C（开源） |
| E18 | DocRED（Yao et al., 2019） | https://arxiv.org/abs/1906.06127 | 2026-11-05 | A |
| E19 | SemEval-2010 Task 8（Hendrickx et al., 2009；W09-2415 已核验） | https://aclanthology.org/W09-2415/ | 2026-11-05 | A |
| E20 | Biber 1993, Representativeness in corpus design | https://doi.org/10.1093/llc/8.4.243 | 2026-11-05 | A |
| E21 | FAIR Guiding Principles（Wilkinson et al., 2016） | https://www.nature.com/articles/sdata201618 | 2026-11-05 | A |
| E22 | Croissant dataset metadata（2024） | https://arxiv.org/abs/2403.19546 | 2026-11-05 | A |
| E23 | Hugging Face datasets licensing 文档 | https://huggingface.co/docs/hub/datasets-licensing | 2026-11-05 | C（官方文档） |
| E24 | LDC 数据目录/许可 | https://www.ldc.upenn.edu/data | 2026-11-05 | A（机构） |
| E25 | CLARIN 研究基础设施 | https://www.clarin.eu/ | 2026-11-05 | A（机构） |
| E26 | ISO 24613 LMF（语言资源管理框架） | https://www.iso.org/standard/66777.html | 2026-11-05 | A（标准） |
| E27 | Microsoft Presidio（PII 检测/匿名化） | https://microsoft.github.io/presidio/ | 2026-11-05 | C（开源） |
| E28 | U.S. Copyright Fair Use Index | https://www.copyright.gov/fair-use/ | 2026-11-05 | A（官方） |

> 说明：E1/E2 是本方案“数据文档”主依据；E3–E5/E23/E28 是许可/隐私主依据；E6–E8 是本体/溯源；E9–E11 是检索评测；E12–E14 是 IAA；E15–E17 是标注工具；E20/E21/E22/E24/E25 是采样/交付/维护。

---

## C1 用户与用途

**定义/规则**：
- 主要用户：**个人学习者**（复习/问答）、**教材/课程作者**（建 KP/语义关系）、**agent 检索**（S7/S9 的 candidate 消费）。
- 先做 **一个域/一本教材**：`docs/example/AAA_Vocab` 的 1 章（约 30–60 KP）做 pilot；不铺全库。
- 成功标准（pilot）：≥50 KP、≥30 语义边、双人标注 IAA 达标、`GATE-RET` 分型可复跑、许可清单完整；0.5 只在 pilot 通过后重跑。
- 与 0.5 对齐：0.5 的目标是 graph 检索从 `NOT_APPLICABLE` 变为可评测，不是“语料规模大”。

**候选对比**：① 个人 KB 小规模（快、隐私风险低）；② 公开教材（可再分发、可评测）；③ 论文/标准（高质量但许可复杂）。建议 **①+② pilot，论文/标准后置**。

**外部证据（≥2）**：
- **E1 Datasheets**（https://arxiv.org/abs/1803.09010，2026-11-05）：数据文档应写动机/用途/受众/限制；映射：C1 的成功标准必须写用户与用途，不能只写“建语料”。
- **E2 Data Statements**（https://aclanthology.org/Q18-1041/，2026-11-05）：NLP 数据应声明语言/受众/用途/采集；映射：C1 指定语言/域/用户，并限制发布范围。
- **E9 BEIR**（https://arxiv.org/abs/2104.08663，2026-11-05）：IR 评测需异构任务/零样本；映射：C1 不以单库单任务成功冒充通用成功。

**反例**：先铺 10 本书再定用途；把用户真实库当标注田；用 0.5 指标倒推语料。
**边界**：多语言；用户 KB 不可发布；无域专家。
**风险/许可**：用户库 PII/版权；公开教材许可需逐本核。
**本仓证据**：`CHARTER.md:5` 记录 `AAA_Vocab` 0 semantic edge；`S8-metrics-v1.md:88` `GATE-RET`/S9 边界。语料观测 `(sha 待测, AAA_Vocab 0 E_sem, 2026-11-05)`。
**建议裁决**：C1 冻结“个人+教材+agent 检索；先 1 章 pilot；0.5 重跑以 pilot 通过为前提”。
**待验证**：pilot 章节选择、用户访谈、0.5 重跑门槛。
**证据等级**：A（E1/E2/E9）+ R（章程）+ PI（pilot 规模）。

---

## C2 来源与许可（含隐私/再分发）

**定义/规则**：
```
每文档：{source_id, origin, license(SPDX), redistribution∈{yes,no,internal}, attribution,
         pii_risk, consent_basis, evidence_url, checked_at}
Tier A 可发布：CC0/PD/CC BY/CC BY-SA/OER 明确许可；
Tier B 仅内部评测：CC BY-NC/ND、购买许可、用户授权但不可再分发；
Tier C 禁用：来源不明/盗版/无许可/许可冲突。
发布包只含 Tier A；Tier B 只放隔离环境 + 不导出原文；引用/署名/NOTICE。
PII：GDPR 合法基础；最小化/脱敏（Presidio）；用户库默认只读、隔离副本。
```
**候选对比**：① 只用 CC BY 公开教材（可发布但域窄）；② 用户库（贴合但不可发布）；③ 混合分层（推荐：发布包 A，内部评测 B）。
**外部证据（≥2）**：
- **E3 CC BY 4.0**（https://creativecommons.org/licenses/by/4.0/，2026-11-05）：允许再分发/改编需署名；映射：Tier A 发布必须带 attribution/NOTICE。
- **E4 CC BY-NC 4.0**（https://creativecommons.org/licenses/by-nc/4.0/，2026-11-05）：禁止商业使用；映射：Tier B 不可进商业发布包。
- **E5 GDPR**（https://eur-lex.europa.eu/eli/reg/2016/679/oj，2026-11-05）：个人数据处理需合法基础/最小化；映射：用户库 PII 脱敏、隔离、保留期限。
- **E23 HuggingFace licensing**（https://huggingface.co/docs/hub/datasets-licensing，2026-11-05）：数据集卡需 license/来源/限制；映射：每文档/每语料卡记录许可。
- **E27 Presidio**（https://microsoft.github.io/presidio/，2026-11-05）：PII 检测/匿名化工具；映射：C2 脱敏流程可执行。
**反例**：整本教材扫描进 repo；CC BY-NC 进 release；用户库原文当 golden 发布；无 NOTICE。
**边界**：多许可合集；引用片段 fair use；政府部门/标准文本；跨语言。
**风险/许可**：许可兼容性（CC BY-SA 传染）、数据库权利、引用长度；需法务复核。
**建议裁决**：Tier A/B/C + 发布包只 A + 用户库隔离 + PII 脱敏 + 许可清单/NOTICE。
**待验证**：法务对 fair use/数据库权利意见；每本教材许可核验；PII 扫描召回率。
**证据等级**：A（E3/E4/E5/E23）+ C（E27）+ PI（分层策略）。

---

## C3 本体与关系 schema（对齐 S0/S10）

**定义/规则**：
```
实体：KP（概念/定义/命题/步骤/例题），可选 concept_scheme（SKOS）但不替代 S0。
关系：只允许 S0 E_relation_min：
  contain（contain_kind∈{structural,semantic}）
  reference
  extend
E_sem = (contain ∧ semantic) ∪ ((reference|extend) ∧ label=semantic)
方向：source→target；both 物化为两条有向边；不新增第三种方向。
禁止：新增关系类型（须 S0/S1 修订）；结构/引用标 semantic；跨 KB 边。
每条边：evidence（双端/assertion span）、confidence、reason、provenance。
```
**候选对比**：① 完全 SKOS/OWL 本体（表达强但偏离 S0）；② 只用 S0 最小类型（推荐，先可评测）；③ 自定义扩展（须 S0/S1 修订，后置）。
**外部证据（≥2）**：
- **E6 SKOS**（https://www.w3.org/TR/skos-reference/，2026-11-05）：概念方案/标签/上下位/关联；映射：concept_scheme 仅作组织层，不替代 S0 边类型。
- **E7 OWL 2**（https://www.w3.org/TR/owl2-overview/，2026-11-05）：本体可表达类/属性/约束；映射：形式约束可用于校验，但 S10 边类型仍以 S0 为准。
- **E8 PROV**（https://www.w3.org/TR/prov-overview/，2026-11-05）：来源/实体/活动/代理；映射：C3 每条边必须有 provenance（谁/何时/依据）。
**反例**：把 `related_to` 等新类型直接写入；用 SKOS broader 替代 `contain(semantic)`；结构边标语义。
**边界**：多语言标签；一词多义；跨文档；负例。
**风险/许可**：本体复用许可（SKOS W3C 文档许可；概念方案来源）；不引入外部本体术语的许可负担。
**本仓证据**：`S10-kp-v1.md:29` 全类型/E_sem 门槛；`S0-terms-v1.md` E_relation_min（见 S10 引用）。建议：S0 全类型 + SKOS 仅组织。
**建议裁决**：C3 冻结 S0 全类型/E_sem 门槛/方向 both 物化/禁止新类型；SKOS/OWL 只作组织/校验。
**待验证**：多语言 concept scheme 映射；负例定义；跨文档边策略。
**证据等级**：A（E6/E7/E8）+ R（S0/S10）。

---

## C4 KP 定义与粒度

**定义/规则**：
```
KP = 可独立引用/断言的最小语义单元；类型 {definition, claim, procedure, example}。
粒度：最小一个命题/定义/步骤；最大单 section；不跨 section（跨节引用用 reference 边）；
range 单文件连续；默认不重叠；嵌套 future（v1 不做）；
字段：kp_id(global unique)/title/alias/summary/file/range/section_ref/tags/evidence/confidence/status；
公式/例题可作为 KP，但必须带上下文 range；section 不是 KP。
```
**候选对比**：① 句级（过细、边爆炸）；② 段/小节级（过粗、不可判）；③ **命题级+section 边界**（推荐）；章级只作容器。
**外部证据（≥2）**：
- **E26 ISO 24613 LMF**（https://www.iso.org/standard/66777.html，2026-11-05）：词法/语言资源的结构化模型；映射：KP 需稳定 id/range/层级，不能只有自由文本。
- **E1 Datasheets**（https://arxiv.org/abs/1803.09010，2026-11-05）：数据单元/收集/标注需文档化；映射：C4 粒度规则写入数据卡，供复核。
- **E15 INCEpTION**（https://inception-project.github.io/，2026-11-05）：支持 span/层级标注；映射：C4 的 range/嵌套/边界可在标注工具落地。
**反例**：整节一个 KP；一句话拆成 10 个 KP；跨文件 range；公式 KP 无上下文；重叠未标。
**边界**：标题/列表/表格/公式/代码；多语言；超长 section。
**风险/许可**：拆句涉及原文片段再分发（C2）；例题/图版权。
**本仓证据**：`S10-kp-v1.md:21` KP 字段/单 section/不重叠/嵌套 future；`S10-kp-v1.md:49` Q-KP 指标。
**建议裁决**：C4 冻结命题级 KP/单 section/不重叠/公式例题可 KP/section 容器；嵌套 future。
**待验证**：pilot 粒度一致性（IAA）；公式/表格边界例；跨节 reference 规则。
**证据等级**：A（E26/E1）+ C（E15）+ R（S10）。

---

## C5 标注协议与指南

**定义/规则**：
```
《KP/边标注手册 v1》必含：目的/范围/单位/上下文窗口/正例/负例/边界例/歧义裁决/
字段定义/证据锚格式/提交格式/质量控制。
流程：预标注（可选）→ 双人独立标注 → 比对/IAA → 裁决会 → 冻结版本；
标注单位：KP（range）+ 边（source,target,type,direction,evidence）；
培训：1 小时指南 + 10 条练习 + 合格测试（≥90% 与金标准一致才上岗）。
```
**候选对比**：① 无指南直接标（不可复现）；② 只给定义（边界争议大）；③ **手册+正负例+裁决+培训**（推荐）。
**外部证据（≥2）**：
- **E15 INCEpTION**（https://inception-project.github.io/，2026-11-05）：支持标注指南/层级/多人；映射：C5 工具落地和导出。
- **E16 brat**（https://brat.nlplab.org/，2026-11-05）：span/关系标注与 standoff 格式；映射：C5 证据 span/关系字段可机读。
- **E2 Data Statements**（https://aclanthology.org/Q18-1041/，2026-11-05）：标注者/语言/流程需声明；映射：C5 记录标注者背景/培训/语言。
**反例**：只有“按语义标”；边界例缺失；无培训；标注者不知道字段。
**边界**：多语言/多领域；歧义句；公式/图；跨文档。
**风险/许可**：标注者隐私/劳动；指南引用原文的版权；工具许可。
**建议裁决**：C5 冻结手册结构/流程/培训/合格测试/边界例；pilot 先修订 v1。
**待验证**：pilot 后指南修订；培训测试效度；多语言指南。
**证据等级**：A（E2/E16）+ C（E15）+ PI（培训阈值）。

---

## C6 语义边标注

**定义/规则**：
```
边字段：source_id/target_id/type∈{contain,reference,extend}/contain_kind?/label?/
direction∈{source_to_target,both}/evidence{file,line,anchor}/confidence/reason/provenance。
语义边门槛：contain(semantic) 或 (reference|extend)∧label=semantic；
结构/引用边不得标 semantic；无证据不建边；跨文档边必须双端证据；
负例：结构包含、纯引用、同义但无断言、跨 KB、自环。
```
**候选对比**：① 只标正例（无法测误报）；② 正+负例（推荐）；③ 只标结构边（不可评测语义）。
**外部证据（≥2）**：
- **E18 DocRED**（https://arxiv.org/abs/1906.06127，2026-11-05）：文档级关系抽取标注含实体/关系/证据；映射：C6 边必须带证据与方向。
- **E19 SemEval-2010 Task 8**（https://aclanthology.org/W09-2415/，2026-11-05，已核验 W09-2415）：9+1 关系类型/方向标注；映射：C6 关系类型/方向需固定枚举与负例。
- **E8 PROV**（https://www.w3.org/TR/prov-overview/，2026-11-05）：映射：边 provenance（谁/何时/依据）必须记录。
**反例**：把 reference 当 semantic；无 evidence；方向反；跨 KB；只标正例导致 precision 不可测。
**边界**：同义/反向/多证据/冲突；跨文档；多语言。
**风险/许可**：引用片段再分发；关系类型版权（用 S0 自有）。
**本仓证据**：`S10-kp-v1.md:29` E_sem 门槛/结构不冒充；`S10-kp-v1.md:67` R-S10-1。
**建议裁决**：C6 冻结 S0 边类型/E_sem 门槛/evidence span/方向 both 物化/负例集。
**待验证**：边 IAA；跨文档边比例；负例采样。
**证据等级**：A（E18/E19/E8）+ R（S10）。

---

## C7 规模/采样/金标准

**定义/规则**：
```
pilot：1 章、50 KP、30 语义边（含负例 30）；
阶段 1：500 KP、300 边、golden 100 KP/60 边；
采样：按 section/type/难度分层，随机种子固定；dev/test 隔离（test 不参与调参）；
edition 固定：语料 sha + 标注指南版本 + 日期；
成本：双人标注 pilot 估 2 人×2 天；正式按 1 KP≈1.5 min、1 边≈2 min 估，需实测。
```
**候选对比**：① 全库标注（成本不可控）；② 随机小样本（偏差）；③ **分层 pilot→阶段扩展**（推荐）。
**外部证据（≥2）**：
- **E20 Biber 1993**（https://doi.org/10.1093/llc/8.4.243，2026-11-05）：语料设计需代表性/分层/规模论证；映射：C7 分层采样与规模理由。
- **E1 Datasheets**（https://arxiv.org/abs/1803.09010，2026-11-05）：数据规模/采样/划分需文档化；映射：C7 记录采样框/种子/划分。
- **E10 TREC**（https://trec.nist.gov/trec_eval/，2026-11-05）：test collection/池化/评测复现；映射：C7 金标准隔离与复跑。
**反例**：随机抽 10 页当 golden；test 调参；规模无成本估算；合成数据补量。
**边界**：小语料；多语言；长尾 section；标注预算不足。
**风险/许可**：成本超支；样本偏差；test 泄漏。
**建议裁决**：C7 冻结 pilot 规模/分层/种子/dev-test 隔离/edition/成本实测后再扩。
**待验证**：pilot 实际成本/IAA；阶段规模；长尾覆盖。
**证据等级**：A（E20/E1/E10）+ PI（规模数字）。

---

## C8 质量与 IAA

**定义/规则**：
```
pilot 100% 双人独立标注；正式 ≥20% 双标 + 10% 专家裁决；
指标按标注对象分型，不能用一个 κ 覆盖所有对象：
  KP span：Krippendorff unitizing α（或 exact-boundary F1 + overlap F1；须先定义 unitizing 单位）；
  KP 类型/边类型/方向：Cohen κ（两标）/Fleiss κ（多标）；
  边 tuple（source,endpoint,type,direction）：tupleset F1 + 裁决一致率；
  置信/有序：加权 κ 或 Krippendorff α（有序/缺失）。
合格线：α/κ≥0.80 优秀；0.67–0.80 可接受需裁决；<0.67 重训/重标；边 tuple F1 单独门槛（pilot 实测后定）。
裁决：分歧记录→专家裁决→更新指南；错误分类：粒度/边界/类型/方向/证据/漏标/误标；
抽检：每批 10% 专家复核；发布前 100% schema/证据校验。
```
**候选对比**：① 单人标（无法估一致性）；② 双人但无裁决（分歧不收敛）；③ **双人+IAA+裁决+错误分类**（推荐）。
**外部证据（≥2）**：
- **E12 Cohen 1960**（https://doi.org/10.1177/001316446002000104，2026-11-05）：两标者名义一致性；映射：C8 双标 κ。
- **E13 Fleiss 1971**（https://www.jstor.org/stable/2529310，2026-11-05）：多标者一致性；映射：C8 多标者 κ。
- **E14 Krippendorff 2004**（https://doi.org/10.1080/19312450802458935，2026-11-05）：α 适用多标/缺失/有序；映射：C8 主指标 α + 缺失处理。
**反例**：只算百分比一致；分歧不裁决；IAA 低仍发布；只标容易样本。
**边界**：多语言/多标注者；类别不平衡；缺失标注。
**风险/许可**：标注者隐私/报酬；裁决成本。
**建议裁决**：C8 冻结双标比例/α/κ 合格线/裁决/错误分类/抽检。
**待验证**：pilot IAA 实际值；α vs κ 选择；专家裁决一致性。
**证据等级**：A（E12/E13/E14）+ PI（合格线）。

---

## C9 评测协议（分型/禁止聚合）

**定义/规则**：
```
三层：
  L1 KP/边抽取：P/R/F1（按类型/域/难度分型）；
  L2 图谱检索 GATE-RET：keyword/vector/hybrid/graph 四型分别 recall@k/NDCG/MRR/coverage；
  L3 端任务：问答/复习正确率/引用完整率（人判矩阵）。
消融：去语义边 vs 有边；去 cluster vs 有；分型报告，禁止只报总体平均；
test 固定 edition，不调参；2× 确定性；无合成数据；S8 只消费 S10/S9 指标。
```
**候选对比**：① 只报总体 P/R（掩盖分型失败）；② 分型+消融+人判（推荐）；③ 只跑检索不跑 KP/边（无法定位）。
**外部证据（≥2）**：
- **E9 BEIR**（https://arxiv.org/abs/2104.08663，2026-11-05）：异构零样本 IR 评测需多数据集/分型；映射：C9 GATE-RET 分型。
- **E10 TREC/trec_eval**（https://trec.nist.gov/trec_eval/，2026-11-05）：标准 IR 指标/复现；映射：C9 固定 qrels/命令/指标。
- **E11 NDCG**（https://aclanthology.org/J08-1002/，2026-11-05）：分级相关性指标；映射：C9 用 NDCG@k 而非仅命中率。
**反例**：只报平均 recall；test 调参；合成数据；不分 keyword/graph；无消融。
**边界**：无 semantic 库；小 test；多语言；人判成本。
**风险/许可**：评测集许可；人判隐私；指标误用。
**本仓证据**：`S8-metrics-v1.md:88` M-S8-10/GATE；`S10-kp-v1.md:49` Q-*；S9 `GATE-RET`。
**建议裁决**：C9 冻结三层/分型/消融/人判/test 隔离/禁止合成/禁止聚合掩盖。
**待验证**：pilot 指标基线；人判矩阵样本；GATE-RET 门槛。
**证据等级**：A（E9/E10/E11）+ R（S8/S10）。

---

## C10 工具与工作流

**定义/规则**：
```
标注工具：INCEpTION（层级/多人）或 doccano/brat（轻量）；导出 JSONL/standoff；
导入导出 schema 校验（KP/边/证据锚/许可）；
版本化：corpus_version/guideline_version/tool_version/sha；审计：谁/何时/改什么；
用户库只读：复制到隔离 workdir，绝不写 sidecar/正文；脱敏后标注；
提交前校验：schema/证据可解析/许可字段/PII 扫描。
```
**候选对比**：① 自建表格（快但无 schema/审计）；② INCEpTION（重但可审计）；③ **轻量工具+校验脚本**（推荐 pilot），正式迁 INCEpTION。
**外部证据（≥2）**：
- **E15 INCEpTION**（https://inception-project.github.io/，2026-11-05）：多用户/层级/指南；映射：C10 正式工具。
- **E17 doccano**（https://doccano.github.io/doccano/，2026-11-05）：文本分类/序列/关系标注；映射：C10 轻量 pilot。
- **E16 brat**（https://brat.nlplab.org/，2026-11-05）：standoff/关系标注；映射：C10 证据 span/导出格式。
- **E27 Presidio**（https://microsoft.github.io/presidio/，2026-11-05）：PII 扫描；映射：C10 提交前 PII 校验。
**反例**：直接改用户库；工具导出无证据锚；无版本；无审计；PII 未扫描。
**边界**：多语言工具支持；离线环境；大文件；多人并发。
**风险/许可**：工具许可（Apache/MIT 需核）；数据驻留；标注者账号。
**建议裁决**：C10 冻结只读隔离/工具选型/导出 schema/版本审计/PII 校验；不写 sidecar。
**待验证**：工具多语言/关系标注能力；离线部署；导出兼容。
**证据等级**：C（E15/E16/E17/E27）+ PI（工具选型）。

---

## C11 与 S10/0.5 衔接

**定义/规则**：
```
标注→金标准→S10 提案：agent 只 propose_write；人工确认；产品 curation writer apply；
curated_by/at + decision_id + audit；写后 edition 变化 ⇒ S9 失效/重建；
0.5 重跑 GATE-RET 进入条件：pilot 语料许可通过 + golden 冻结 + 标注 IAA 达标 +
  S10 KP/边提案通过人工确认 + GATE-RET 可复跑；否则继续 HOLD。
0.5 不做 S10 自动写；S10 未启用时 S7/S9 只读。
```
**候选对比**：① 直接让 agent 写库（违反 S10/0.5）；② **人工确认后 apply**（推荐）；③ 只做离线评测不接 S10（无法验证产品链路）。
**外部证据（≥2）**：
- **E2 Data Statements**（https://aclanthology.org/Q18-1041/，2026-11-05）：数据用途/限制需声明；映射：C11 0.5 重跑前声明用途/许可。
- **E8 PROV**（https://www.w3.org/TR/prov-overview/，2026-11-05）：写路径 provenance；映射：curated_by/at/decision/audit。
- **E1 Datasheets**（https://arxiv.org/abs/1803.09010，2026-11-05）：版本/维护/用途；映射：C11 交付与重跑条件。
**反例**：agent 自动 apply；0.5 未 pilot 就重跑；无人工确认；写后不失效 S9。
**边界**：S10 未启用；0.5 HOLD；批量写；回滚。
**本仓证据**：`S10-kp-v1.md:12/17/37` propose-only/人工确认；`S8-metrics-v1.md:88` GATE-RET；0.5 HOLD `dec-20261105-cb24f93e`。
**建议裁决**：C11 冻结人工确认/产品 writer/edition 失效/0.5 重跑四条件；不自动写。
**待验证**：0.5 重跑门槛具体值；人工确认 UI；回滚演练。
**证据等级**：A（E2/E8/E1）+ R（S10/S8/0.5 HOLD）。

---

## C12 交付与维护

**定义/规则**：
```
交付包：
  corpus/（Tier A 原文/片段 + 许可/NOTICE）
  golden/（edition/sha、dev/test、负例）
  guidelines/（标注手册/边界例/培训）
  licenses/（SPDX/来源/许可清单）
  scripts/（校验/评测/统计）
  reports/（IAA/指标/评测）
  DATASHEET.md（E1）+ DATA_STATEMENT.md（E2）
维护：owner、季度复核、许可到期、版本/edition、废弃策略、变更日志；
不把一次性 demo 当交付；FAIR/Croissant 元数据；LDC/CLARIN 可选托管。
```
**候选对比**：① 只交语料（不可维护）；② 语料+脚本（半可维护）；③ **语料+golden+指南+许可+脚本+数据卡+owner**（推荐）。
**外部证据（≥2）**：
- **E21 FAIR**（https://www.nature.com/articles/sdata201618，2026-11-05）：可发现/可访问/可互操作/可复用；映射：C12 元数据/许可/持久标识。
- **E22 Croissant**（https://arxiv.org/abs/2403.19546，2026-11-05）：ML 数据集元数据格式；映射：C12 数据集卡/资源描述可机读。
- **E1 Datasheets**（https://arxiv.org/abs/1803.09010，2026-11-05）：数据卡；映射：C12 DATASHEET。
- **E24 LDC**（https://www.ldc.upenn.edu/data，2026-11-05）/ **E25 CLARIN**（https://www.clarin.eu/，2026-11-05）：语料托管/许可/维护实践；映射：C12 托管/维护参考。
**反例**：只给 zip；无许可清单；无 owner；无版本；demo 后废弃。
**边界**：许可到期；多语言；大文件；托管成本。
**风险/许可**：再分发/托管条款；隐私保留期；成本。
**建议裁决**：C12 冻结交付包清单/DATASHEET+DATA_STATEMENT/owner/季度维护/版本废弃/FAIR/Croissant。
**待验证**：托管方案；维护成本；许可到期处理。
**证据等级**：A（E21/E22/E1/E24/E25）+ PI（维护节奏）。

---

## 附：C1–C12 覆盖与证据计数

| 项 | 外部证据 | 本仓/语料 | 主要裁决 |
|---|---|---|---|
| C1 | E1,E2,E9 | CHARTER:5 | pilot 1 章/用户/0.5 门槛 |
| C2 | E3,E4,E5,E23,E27 | — | Tier A/B/C/许可/NOTICE/PII |
| C3 | E6,E7,E8 | S10:29 | S0 全类型/E_sem/SKOS 仅组织 |
| C4 | E26,E1,E15 | S10:21 | 命题级/单 section/不重叠 |
| C5 | E15,E16,E2 | — | 手册/正负例/培训/裁决 |
| C6 | E18,E19,E8 | S10:29/67 | 边类型/证据/方向/负例 |
| C7 | E20,E1,E10 | — | pilot/分层/dev-test/成本 |
| C8 | E12,E13,E14 | — | 双标/α/κ/裁决/抽检 |
| C9 | E9,E10,E11 | S8:88;S10:49 | 三层/分型/消融/禁止聚合 |
| C10 | E15,E16,E17,E27 | — | 只读隔离/schema/审计/PII |
| C11 | E2,E8,E1 | S10:12/17/37;0.5 HOLD | propose-only/人工/0.5 四条件 |
| C12 | E21,E22,E1,E24,E25 | — | 交付包/数据卡/owner/维护 |

> 独立声明：本文件写作时未读 `C0-proposal-A.md`（尚未落盘）；差异与判断见 `C0-objections.md`，逐项列不合并。
