# C0-AMENDMENT-1 提案 B（独立复核：evaluation-first，去 gold KP/IAA）

> **依据**：人裁定 C0 转 **evaluation-first**（去 gold KP/IAA）；`CHARTER.md` C1–C12；`C0-corpus-v1.md`/`C0-RULINGS.md`（评估优先修订）；0.5 HOLD `dec-20261105-cb24f93e`；S0–S10 冻结。
> **性质**：独立复核/提案 B；写作时**未读** `C0-AMENDMENT-1-proposal-A.md`（尚未落盘）；完成后对照，见 `C0-AMENDMENT-1-objections.md`。
> **证据等级**：A=论文/标准/官方；B=本仓冻结/实测；C=工具文档；D=语料观测；PI=假设（pilot 校准）。
> **纪律**：不改 C0/冻结稿；不写产品代码；不 commit；外部内容只作证据。

---

## 0. 总原则：evaluation-first 不是“去掉质量门”

1. **去掉 gold KP/IAA** 只意味着：不再把“KP span/gold 标注”作为发布前置；不意味着“模型说好就是好”。
2. **最小人类锚点（MHA）必须保留**：人类回答/判断的 **answer-level** 锚点，而非 span-level gold；MHA 是唯一能防“模型自洽=质量”的硬证据。
3. **section/paragraph 级相关性**替代 KP 级 gold：可判、稳定、与检索单位一致；但必须处理“粗粒度假阳性”。
4. **三层评测**：L1 人类锚点（P0）；L2 检索/消融（P0/soft）；L3 A/B 偏好/时间（soft，需去混杂）。
5. **A/B 可复现**：同 corpus/edition/任务/UI，随机/平衡顺序，盲评，样本量/统计；不许“新鲜感/布局/数据量”冒充图谱收益。
6. **语义边价值**：必须用 **edge-only ablation**（同节点、去语义边）+ structural/random 对照；只看“去边任务变差”不够。
7. **≤2–4h**：只够 1 个章节、20–25 题、1 名独立出题 + 2 名人类锚点/或 1 名人类+1 名复核；必须记录实际工时；超时缩题不降锚点质量。
8. **许可/edition/provenance 不变**：Tier A/B/C、NOTICE、edition sha、无 sidecar 写仍适用；问题集也受许可约束。
9. **falsifiers 先写**：结果若不能推翻“图谱有效”，就不是评测。

### 0.1 外部证据总表（关键点复用）

| ID | 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|---|
| E1 | Ragas: reference-free RAG evaluation（Es et al., 2023） | https://arxiv.org/abs/2309.15217 | 2026-11-05 | 无 gold 也可评，但需人工锚点防自洽 |
| E2 | ARES（Saad-Falcon et al., NAACL 2024） | https://arxiv.org/abs/2311.09476 | 2026-11-05 | 少量人工标注 + PPI 校准自动 judge |
| E3 | MT-Bench / LLM-as-judge（Zheng et al., 2023） | https://arxiv.org/abs/2306.05685 | 2026-11-05 | LLM judge 可用但有位置/长度/自我偏好 |
| E4 | LLMs are not Fair Evaluators（Wang et al., 2023） | https://arxiv.org/abs/2305.17926 | 2026-11-05 | 顺序可被操纵；需平衡位置/人审 |
| E5 | BEIR（Thakur et al., 2021） | https://arxiv.org/abs/2104.08663 | 2026-11-05 | 异构 IR/分型评测；section/passage 相关 |
| E6 | TREC/trec_eval | https://trec.nist.gov/trec_eval/ | 2026-11-05 | qrels/池化/复跑 |
| E7 | NDCG（Järvelin & Kekäläinen, 2002） | https://aclanthology.org/J08-1002/ | 2026-11-05 | 分级相关性；section 级 graded relevance |
| E8 | MS MARCO（Nguyen et al., 2016） | https://arxiv.org/abs/1611.09268 | 2026-11-05 | passage 级检索/大规模 dev-test |
| E9 | Lost in the Middle（Liu et al., 2023） | https://arxiv.org/abs/2307.03172 | 2026-11-05 | 上下文位置影响答案；section 级相关不保证可用 |
| E10 | Kohavi et al., Online Controlled Experiments（KDD 2013） | https://doi.org/10.1145/2487575.2488217 | 2026-11-05 | A/B 随机化/样本量/混杂控制 |
| E11 | Trustworthy Online Controlled Experiments（Kohavi et al.） | https://experimentguide.com/ | 2026-11-05 | A/B 设计/护栏/学习效应 |
| E12 | Cohen, Statistical Power Analysis（1988） | https://doi.org/10.4324/9780203771587 | 2026-11-05 | 样本量/效应量/统计功效 |
| E13 | OSF Preregistration | https://www.cos.io/initiatives/prereg | 2026-11-05 | 预注册问题/指标/falsifiers |
| E14 | RAG evaluation survey（Gao et al., 2024） | https://arxiv.org/abs/2405.07437 | 2026-11-05 | RAG 多维指标/评测分层 |
| E15 | SUS（Brooke, 1996） | https://doi.org/10.1201/9781498710411-35 | 2026-11-05 | 可用性/学习效应问卷（soft） |

> 说明：E1–E6/E9–E14 为论文/标准/官方；E3/E4 直接支持“LLM judge 偏差”；E1/E2 支持“无 gold 可评但需少量人工锚点”；E5/E8/E9 支持 section/passage 级相关性；E10–E12 支持 A/B/样本量；E13 支持预注册/falsifiers。

---

## C4（evaluation-first）评测单元：Section/Passage，而非 gold KP

**规则**：
```
评测单元 = SectionUnit（section 或 1–3 段窗口），不是 gold KP。
SectionUnit{section_id, file, heading, range{line_start,line_end}, edition_sha,
            text_hash, parent_section?}
KP 仅作为检索内部单位/诊断，不作为发布 gold；不要求 KP 标注/IAA。
section 边界按 heading 层级；跨节答案用“主节 + 支撑节”多引用，不强行合并。
paragraph 级仅作为可选下钻；图/表/公式以所在 section 为单元。
```
**为什么更可靠**：section 是作者自然分块、读者可定位、与检索返回单位一致；比“模型自定 KP 边界”更少主观性。但**粗粒度会假阳性**：section 含关键词但无答案、答案跨节、多节重复；需 graded relevance + answer rubric。
**反例**：section 命中关键词就判 relevant；答案在下一节；图表信息未纳入；同一问题多节都相关却只标一个。
**边界**：跨节答案；超长节；无 heading；多语言；图表。
**外部证据（≥2）**：
- **E5 BEIR**（2026-11-05）：passage/document 异构检索；映射：SectionUnit 作为检索/相关性单元。
- **E8 MS MARCO**（2026-11-05）：passage 级大规模检索；映射：section/passage 是成熟评测单位。
- **E7 NDCG**（2026-11-05）：分级相关性；映射：section relevance 用 0–3 级而非二值。
**本仓证据**：`S10-kp-v1.md` KP 仅内部提案；`C0-corpus-v1.md` 的 KP gold 门改为评测锚点（本 amendment 不改 C0）。
**建议裁决**：冻结 SectionUnit 为评测单元；KP 仅内部诊断；section 相关性 graded；跨节多引用。
**待验证**：section 长度/边界；跨节比例；图表 section 规则。
**证据等级**：A（E5/E7/E8）+ PI。

---

## C5（evaluation-first）最小人类锚点协议（MHA）

**规则**：
```
MHA = 20–25 个问题/章（pilot），由“非实现者”从教材出题；预注册。
每题：
  question_id, question, type∈{fact,definition,procedure,comparison,multi-hop,no-answer},
  required_facts[]（答案必须包含的要点）, acceptable_sections[]（1–3 个 section，graded 0–3）,
  reference_answer（1–3 句，来自源文/可复核）, citation_required=true,
  no_answer?（源文无答案时必须拒答）, held_out∈{dev,test}。
锚点：
  2 名人类独立回答/判定（非实现者）；分歧→第 3 人裁决；
  记录 answer_correct、citation_supported、abstained、time；
  不标 gold KP span、不算 span IAA。
防泄漏：出题人≠实现者；test 题不参与调参/提示词；题目不出现在训练/索引导航；
  同一问题不直接复用源文句子（避免字面匹配）。
```
**最小锚点为什么必要**：
- 没有人类锚点，模型/LLM judge 的“自洽/流畅”无法证明答案正确；RAGAS/ARES 也需少量人工标注校准（E1/E2）。
- 人类锚点是 **answer-level**，不是 span-level；成本远低于 gold KP/IAA，但仍能防“模型自洽”。
**反例**：实现者出题+实现者答题；test 题泄漏进 prompt；只让 LLM judge；只判“引用存在”不判“引用支持答案”；no-answer 题缺失。
**边界**：open-ended；多答案；跨节；无答案；多语言；题量 20 是否够。
**外部证据（≥2）**：
- **E1 Ragas**（2026-11-05）：reference-free 可评但维度多；映射：无 gold 仍需人类锚点校准。
- **E2 ARES**（2026-11-05）：少量人类标注 + PPI 校准 judge；映射：MHA 20–25 题用于校准/验收。
- **E13 Preregistration**（2026-11-05）：预注册问题/指标/falsifiers；映射：出题/切分先写死。
**建议裁决**：冻结 MHA 20–25 题/2 人类锚点/第3裁决/出题人独立/dev-test 隔离/预注册。
**待验证**：20 题统计功效；2 人成本；跨节题比例；open-ended rubric。
**证据等级**：A（E1/E2/E13）+ PI（题量）。

---

## C8（evaluation-first）质量：人类锚点一致性，不是 gold KP IAA

**规则**：
```
不再要求 gold KP span/IAA；质量门改为：
  MHA answer correctness：2 人独立判 correct/partial/incorrect；报告 agreement（Cohen κ/α，类别）；
  citation support：2 人判引用是否支持答案（支持/部分/不支持）；100% 支持为 P0；
  no-answer：拒答正确率；
  section relevance：2 人对 acceptable_sections 的 graded 相关性一致性（加权 κ/α）；
  adjudication：分歧记录+第3人；不达线不扩 test。
合格线（pilot）：answer κ≥0.67（目标0.8）；citation support agreement≥0.8；
  section relevance weighted κ≥0.67；no-answer 100% 正确（pilot 少题）。
```
- 这里 κ 是 **人类锚点之间** 的一致性，不是 gold KP span IAA；样本是 20–25 题，不是 50 KP。
**反例**：用模型自评代替人类锚点；只算 answer 准确率不报一致性；citation 只判“有链接”；section 相关性二值化掩盖粗粒度。
**边界**：类别不平衡（correct 多）；小样本；多答案；open-ended。
**外部证据（≥2）**：
- **E1/E2**（2026-11-05）：RAG 评估需 faithfulness/answer relevance + 人工校准；映射：answer/citation 双锚点。
- **E13 Preregistration**（2026-11-05）：分析计划先写；映射：κ/样本/裁决预注册。
- **E14 RAG survey**（2026-11-05）：多维指标；映射：answer/citation/retrieval 分开报。
**建议裁决**：冻结 MHA 一致性指标/合格线/裁决；不再要求 gold KP IAA；不达线不扩 test。
**待验证**：20 题 κ 置信区间；citation 判定细则；多语言。
**证据等级**：A（E1/E2/E13/E14）+ PI（阈值）。

---

## C9（evaluation-first）评测协议：锚点 + 检索 + 消融 + A/B

**规则**：
```
L1 人类锚点（P0）：answer correctness、citation support、no-answer、section relevance；
L2 检索（P0/soft）：SectionUnit recall@5、NDCG@10、MRR；按 keyword/vector/hybrid/graph 分型；
L3 消融（P0 方向性）：full graph vs no-semantic-edge（同节点/同 lexical index）vs
   structural/random-edge control vs keyword-only；同 20–25 题、同 edition；
L4 A/B（soft）：盲评 preference/iterations/time；随机/平衡顺序；同 UI/corpus；
禁止：只报总体平均；模型 judge 单独作 P0；合成数据；test 调参；NOT_APPLICABLE 算通过。
```
**指标可操纵性与对策**：
| 指标 | 可操纵 | 对策 |
|---|---|---|
| retrieval recall | qrels 偏、题泄漏、池化不全 | 预注册题、独立出题、section qrels、pooling |
| answer accuracy | judge 偏、verbosity、prompt 泄漏 | 人类锚点、LLM judge 仅辅助、盲评、citation |
| citation support | 只判“有链接” | 人类判“span 是否支持 claim” |
| iterations/time | UI 引导、学习效应 | 同 UI、练习、顺序平衡、时间仅 soft |
| preference | 位置/长度/新鲜感 | 平衡位置、盲、同数据量、A/B 随机 |
**外部证据（≥2）**：
- **E3/E4**（2026-11-05）：LLM judge 位置/长度/自我偏好；顺序可操纵；映射：不让 judge 单独 P0，平衡位置。
- **E10/E11**（2026-11-05）：A/B 随机化/护栏/学习效应；映射：L4 设计。
- **E5/E6/E7**（2026-11-05）：IR 分型/qrels/NDCG；映射：L2。
**反例**：只报 hybrid 平均；用模型 judge 当 P0；A/B 不同数据量；无消融；test 调参。
**边界**：20 题统计功效；多轮；无 semantic；用户学习。
**建议裁决**：冻结 L1/L2/L3/L4；P0=人类锚点+citation+no-answer+graph 消融方向；soft=iterations/time/preference/judge。
**待验证**：20 题功效；消融差异阈值；A/B 样本量。
**证据等级**：A（E3/E4/E5/E6/E7/E10/E11）。

---

## C11（evaluation-first）与 S10/0.5：解禁门槛（去 gold 后）

**规则**：
```
0.5 重跑/解禁必须同时满足：
  ① MHA：answer correctness≥0.80、citation support=1.0、no-answer 100%；
  ② section relevance：weighted κ≥0.67 且 recall@5≥0.80（有 semantic 边后 graph 适用）；
  ③ 消融：full graph > no-semantic-edge（同题/同 edition）且差异达 pilot 预设效应量；
     structural/random 对照不优于 full；
  ④ 无事实/ sidecar 写；S10 只 propose_write/人工确认；
  ⑤ 2× 确定性；edition/许可/URL 记录完整；
  ⑥ A/B（若做）盲评/随机/同 UI，soft 报告，不用作唯一解禁依据。
NOT_APPLICABLE 不算通过；模型 judge 不单独作 P0；合成数据不算。
```
**为什么不是“去 gold=降门槛”**：gold KP 去掉了，但 **人类答案锚点 + 消融** 更直接约束“图谱是否真的帮助回答”；否则容易把“模型流畅/自洽”当成功。
**外部证据（≥2）**：
- **E1/E2**（2026-11-05）：RAG 评估需 answer/faithfulness + 人工锚点；映射：C11 ①。
- **E5/E6**（2026-11-05）：IR 检索分型/qrels；映射：C11 ②。
- **E10/E13**（2026-11-05）：A/B/预注册；映射：C11 ⑥。
**反例**：MHA 只 5 题；无消融；模型 judge 通过就解禁；Tier B 进发布；写 sidecar。
**边界**：20 题功效；无 semantic；S10 未启用。
**建议裁决**：冻结六条件；MHA 人类锚点为 P0；消融方向为 P0；A/B 仅 soft。
**待验证**：20 题/效应量；citation 判定；0.5 重跑成本。
**证据等级**：A（E1/E2/E5/E6/E10/E13）+ R（S10/0.5）。

---

## 关键点逐项审查（任务 1–9）

### 1. 模型自洽 ≠ 质量：哪些最小人类锚点仍必要
- 必须保留：**answer correctness**（人类）、**citation support**（人类判 span 是否支持 claim）、**no-answer/abstention**（人类）、**section relevance**（人类 graded）；LLM judge 仅辅助。
- 不保留：gold KP span、KP IAA、全量双标；这些成本高且与“答案是否正确”不直接。
- 机检：MHA 题/答案/引用/裁决/κ；模型 judge 与人类一致率仅 soft。

### 2. 问题集偏差/泄漏
- 出题人≠实现者；预注册；test 不参与调参；同一问题不直接用源文句；open-ended 用 rubric；多答案列 acceptable；no-answer 题。
- dev/test 按 **section** 隔离（不是按问题随机，避免同节泄漏）；test 只在最后跑一次。
- 反例：实现者出题、test 题进 prompt、题目答案在标题/摘要、池化只覆盖 top-k。

### 3. section/paragraph 级相关性是否更可靠
- 更可靠：边界由作者 heading 决定，读者可定位；但粗粒度会假阳性。需要 graded relevance、多 acceptable section、跨节答案、no-answer；paragraph 仅 optional 下钻。
- 反例：section 含关键词但无答案；答案跨两节；图表；同一问题多个 section 都相关。
- 结论：section 级 **比 KP 更稳定**，但 **不能单独**判 answer 正确；必须配 MHA。

### 4. A/B 混淆因素
- 布局/数据量/新鲜感/学习效应/顺序：同 UI、同 corpus/edition、同任务、随机/平衡顺序、盲评、练习/洗脱、样本量/功效、预注册指标；报告效应量/CI，不只看 p。
- 反例：graph 版多给 2 倍数据；先测 baseline 再测 graph；同一用户重复；只看 preference 不看 answer。
- 结论：A/B 只作 soft；P0 用 MHA+消融。

### 5. 语义边价值/消融是否足够
- 仅“去边任务变差”不够（可能节点/索引变化）；必须 **同节点/同 lexical index** 的去 semantic-edge 消融 + structural/random 对照 + keyword-only；同题/edition；报告 retrieval/answer/citation；edge-only 贡献。
- 反例：去边同时去掉簇/索引；结构边当语义；随机边也提升（说明不是语义）。
- 结论：消融方向性 P0；绝对阈值 pilot 后定。

### 6. 指标可操纵性/P0/soft/0.5
- P0：MHA answer/citation/no-answer、section recall@5、graph 消融方向、无写/edition；
- soft：LLM judge、iterations、time、preference、SUS；
- 0.5 六条件（C11）；禁止聚合/NOT_APPLICABLE/合成。
- 反例：judge 偏、题泄漏、时间 UI、preference 位置。

### 7. ≤2–4h 是否现实
- 现实范围：1 章、20–25 题、1 名独立出题（1–1.5h）、2 名人类锚点（各 1–1.5h）、第3裁决（0.5–1h）、消融/分析（1h）≈ **4–6 人时**；若严格 ≤4h，只能 **20 题/1 名人类+1 名复核** 或复用已有题。
- 膨胀步骤：出题/预注册、双人锚点、裁决、消融、A/B、许可/清洗；必须记录实际工时/题量，审计“没有偷偷扩大标注”。
- 结论：**≤2–4h 只够最小 pilot**；不能覆盖 gold KP/IAA/A/B 全做；C11 解禁需另排。

### 8. 许可/Tier/provenance/edition
- 不变：Tier A/B/C；问题/答案/引用也受许可；Tier B 不进发布；NOTICE/SPDX；edition sha；无 sidecar 写；问题集不复制长原文。
- 影响：evaluation-first 不含 gold KP，但 MHA/答案/引用仍需 provenance（file/section/anchor）。

### 9. Falsifiers（什么结果推翻 evaluation-first）
1. MHA 通过但 **no-semantic-edge 消融不差**（图谱无贡献）⇒ 推翻“图谱有效”。
2. 人类锚点与 LLM judge 一致率低（<0.6）且人类间 κ 低 ⇒ 评测不可靠。
3. section 级 baseline（keyword-only）已达 recall@5≥0.80，graph 无增量 ⇒ section 相关性不足以证明图谱。
4. 问题集被证明泄漏/实现者出题/test 调参 ⇒ 结果无效。
5. A/B 差异可由数据量/布局/学习效应解释 ⇒ 不是图谱收益。
6. ≤4h 实际只能做 10 题/1 人 ⇒ 统计功效不足，不能解禁 0.5。
7. 许可/Tier 不允许发布 MHA 源文/答案 ⇒ 评测不可交付。
8. 语义边只提升“引用存在”不提升 answer/citation support ⇒ 边是装饰。

---

## 附：evaluation-first 最小交付物（pilot）

```
MHA-20.json（题/答案要点/acceptable sections/no-answer/dev-test/预注册）
MHA-answers.csv（2 人类 correct/partial/citation/abstain/time/裁决）
section-qrels.json（graded 0–3）
ablation.json（full/no-sem-edge/structural/random/keyword；同题/edition）
metrics.json（answer/citation/no-answer/section recall/NDCG/MRR/消融差/CI）
falsifiers.md（预注册）
license/NOTICE + edition sha + 实际工时
```
> 独立声明：本文件先于 A 完成；差异见 `C0-AMENDMENT-1-objections.md`；未改 C0/冻结稿、未写产品代码、未 commit。
