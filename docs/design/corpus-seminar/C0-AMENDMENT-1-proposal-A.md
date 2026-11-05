# C0 修订 A（AMENDMENT-1）：evaluation-first 语料设计

> **性质**：对 `C0-proposal-A.md`（v1 `18b1674d…`）的**局部修订**；不改 C0 正文/冻结稿，只重开受影响项。
> **依据**：人 2026-11-05 裁定（C0 转 evaluation-first）+ `C0-RULINGS.md`；本提案独立写，未读 B。
> **影响范围**：**C4/C5/C8/C9/C11 重开**；C1/C2/C3/C6/C7/C10/C12 只说明影响（C6 评测口径受 C9 影响，C7 人时受 C8 影响）。
> **核心变化**：不再把 KP span 当 gold、不再做 50 KP 双人标注/IAA；改为**结构+模型生成候选 → 问题→证据相关性 → A/B 呈现 → 任务指标**；人类只做 **judge（≤2–4h）**。
> **纪律**：不写产品代码、不改冻结稿、不 commit；外部内容只作证据。

---

## 0. 一句话口径

```
KP = 导航/检索单元（candidate，不追求唯一真值）；边界由 retrieval/UX 指标调，不由人标 gold。
评测 = 20–30 个问题 × section/paragraph 级 evidence relevance（人只判"这段是否含答案"）
      + 新旧图谱 A/B（time-to-find/偏好/理解）+ 任务指标；人类 ≤2–4h，只做 judge。
语义边 = 候选假设；用"问题→证据链路是否提升任务"评估，不做 gold edge IAA。
0.5 解禁不再看 IAA 达线，改看任务指标/GATE-RET 分型。
```

---

## 1. C4 修订：KP 重新定义（导航/检索单元）

**改什么**：
- KP 从“有唯一真值的标注对象”改为 **candidate unit**：heading/paragraph/formula/example/table 的结构 span + agent 提议，允许一个 section 有多个候选、允许重叠/嵌套（不要求唯一切分）。
- 字段：`candidate_id, source_span{file,line_start,line_end,anchor_id,structure_type}, title, aliases[], summary?, parent_section, proposed_by, confidence, status∈{candidate,accepted,rejected}, edition`。
- 候选生成优先级：①文档结构（heading 层级、段落、公式、例题、表格）；②agent 基于问题/证据提议；③检索命中回填。结构候选不需要人工 gold。
- 边界调优：用 C9 的 retrieval recall/answer/时间指标 + C5 的问题相关性 judge 调整粒度/合并/拆分；不做 span IAA。
- 默认粒度：**概念+1–3 句/一个结构块**；pilot 同时试“命题级”（一句命题）变体，由任务指标选择，不由 IAA 选择。

**为什么**：126k 文本下人类切分无唯一真值；把候选当 gold 会制造伪真值并消耗人时（人裁定）。候选/接受分离让派生可重建。

**怎么验**：
- 候选覆盖：问题证据中能被至少一个 candidate 覆盖的比例（机器可算）。
- 粒度消融：概念级 vs 命题级，比较 recall@5/answer/time-to-find；差异不显著则选成本低者。
- 边界稳定性：同 edition 两次生成 candidate set Jaccard ≥0.9（机器确定性）；不要求人一致。

**外部证据**：
| 来源 | URL | 访问日期 | 映射 |
|---|---|---|---|
| GraphRAG | https://arxiv.org/abs/2404.16130 | 2026-11-05 | 图索引/实体候选由模型生成 + 评测驱动，不需人工 gold 图 |
| DocRED | https://arxiv.org/abs/1906.06127 | 2026-11-05 | 实体/关系候选与文档级证据；支持“候选+证据”而非唯一切分 |
| Datasheets | https://arxiv.org/abs/1803.09010 | 2026-11-05 | 候选/派生数据需文档化；支持 candidate/accepted 分离 |

**反例**：把候选当 gold；要求唯一 span；人标 50 KP；嵌套/重叠直接拒绝。
**边界**：公式/表格/代码块；heading 无段落；跨 section 候选；多语言。
**风险**：候选覆盖不足；结构切分与问题不对齐；候选爆炸。
**建议裁决**：采纳“导航/检索单元 + candidate/accepted + 指标调边界”；不做 span gold/IAA。
**待验证**：结构类型权重；命题级变体是否值得；候选覆盖阈值。
**证据等级**：A（论文/标准）。

---

## 2. C5 修订：从标注协议改为“问题→证据相关性 + 呈现 judge”

**改什么**：
- 删除“KP 手册 + 30 正例/30 负例 + 标注者培训”路线；改为 **Judge Protocol**：
  1. 选 20–30 个真实问题（用户/教材/agent 场景）；
  2. 每个问题给候选 section/paragraph 列表（5–10 个，含正/负/边界），人只回答“这段是否包含答案”：`contains_answer∈{yes,partial,no}`；
  3. 记录判断耗时；不要求读全文/不要求切分 KP；
  4. 对新旧图谱做 A/B：同一问题分别用旧/新呈现，测 time-to-find、点击、偏好、理解度。
- 抽样：问题按章/题型/难度分层；候选段落按 retrieval 排序分层（top1/top3/随机负例）；dev/test 按**问题**隔离，test 不参与阈值调参。
- 防泄漏：问题作者不看系统输出；候选段不含答案位置提示；test edition 固定。
- 人时：20–30 问题 × 5–8 段判断 ≈ 100–240 次判断；每次 20–30 秒，约 1–2h；A/B 2 个 sessions ≈ 1–2h；总 ≤4h。

**为什么**：人只需判断“是否含答案”，比切分 KP 稳定、便宜；直接对齐检索/呈现目标。

**怎么验**：
- judge 一致性：同一问题 10% 双判，报告 agreement（不是 span IAA）；不一致进裁决。
- 任务指标：recall@5、answer correctness、time-to-find、preference（见 C9）。
- 人时：记录实际 judge 分钟数；超 4h 则缩问题/候选数，不降判断质量。

**外部证据**：
| 来源 | URL | 访问日期 | 映射 |
|---|---|---|---|
| TREC | https://trec.nist.gov/ | 2026-11-05 | 主题/相关性判断/池化的 IR 评测传统；支持“问题→证据相关性” |
| BEIR | https://arxiv.org/abs/2104.08663 | 2026-11-05 | 检索相关性/异构评测；支持候选池与分型 |
| Chatbot Arena | https://arxiv.org/abs/2403.04132 | 2026-11-05 | 成对偏好/A/B 人类 judge；支持呈现评测 |

**反例**：让 judge 读全文找答案；给答案位置提示；问题作者看系统输出；test 调阈值。
**边界**：问题歧义；多段证据；无答案问题（应判 no）；跨语言。
**风险**：问题偏差；judge 疲劳；小样本。
**建议裁决**：采纳 Judge Protocol + 问题级 dev/test；人只判相关性/偏好，不标 KP。
**待验证**：20–30 问题统计功效；候选段数量；双判比例。
**证据等级**：A（IR/偏好论文）。

---

## 3. C8 修订：从 IAA 改为 judge 可靠性 + 最小人类锚点

**改什么**：
- **删除** KP span/边界 IAA、类型 κ、边 tuple F1 作为 0.5 解禁条件；保留为**诊断**（可选）。
- 人类锚点最小化：
  - 10% 问题双 judge（相关性 yes/partial/no）→ 报告 agreement（Cohen κ 可选，不设硬线）；
  - 10% A/B 偏好双判 → 报告一致率；
  - 争议进裁决，记录理由。
- 机器锚点：retrieval/answer/time 指标可复跑；candidate 生成确定性；引用完整性；无写。
- 合格线改为**任务指标**（C9），不是 IAA。

**为什么**：人裁定不要 IAA 门槛；judge 可靠性只需证明“判断不是随机/不矛盾”，不必把 span 当唯一真值。

**怎么验**：
- 双判 agreement 报告（κ/一致率），不设解禁硬线；
- 争议率/裁决耗时；超阈值（如争议>30%）则修问题/候选，不增标注量；
- 任务指标达标即可进入 0.5 重跑讨论。

**外部证据**：
| 来源 | URL | 访问日期 | 映射 |
|---|---|---|---|
| Artstein & Poesio | https://aclanthology.org/J08-4004/ | 2026-11-05 | 标注/判断一致性方法综述；支持“可靠性诊断而非唯一真值” |
| LLM-as-a-Judge | https://arxiv.org/abs/2306.05685 | 2026-11-05 | LLM judge 偏差/与人类一致性；支持 judge 校准与偏差控制 |
| Chatbot Arena | https://arxiv.org/abs/2403.04132 | 2026-11-05 | 人类偏好一致性/统计；支持双判/偏好评测 |

**反例**：恢复 50 KP 双标；IAA 不达标就禁 0.5；只做 LLM judge 不校准；不报争议率。
**边界**：judge 少；问题歧义；LLM judge 位置/长度偏差。
**风险**：小样本；judge 偏差；争议裁决成本。
**建议裁决**：降级 IAA 为诊断；人类只做 10% 双判+裁决；0.5 看任务指标。
**待验证**：双判比例/样本量；LLM judge 与人类一致性；争议阈值。
**证据等级**：A（论文）。

---

## 4. C9 修订：evaluation-first 指标与 GATE-RET

**改什么**：指标分 P0/soft；GATE-RET 保留并分型（keyword/vector/hybrid/graph），但**不再要求 gold KP/edge**；以问题→证据任务为准。

| 指标 | 定义 | 门槛 | 类型 |
|---|---|---|---|
| `R-RECALL@5` | 问题证据中 top-5 覆盖比例 | ≥0.80（pilot） | P0 |
| `R-NDCG@5` | 证据相关性折损增益 | 基线不降 | soft |
| `A-ANSWER` | 答案正确/可接受比例（人判/可机判） | ≥基线 | P0 |
| `A-REF` | 引用完整率（答案→证据 anchor） | 100% | P0 |
| `T-FIND` | 找到答案中位时间（A/B） | 不慢于旧图谱 | P0（非劣） |
| `A-ITER/TOK` | agent 迭代/ token | ≤预算 | soft |
| `P-PREF` | 新旧图谱偏好（A/B） | 新≥50% | soft |
| `U-ACCESS` | 可访问性检查（键盘/aria） | 100% | P0 |
| `S-SEM` | 语义边对任务增益（消融） | 去边后指标下降 | soft（方向） |
| `GATE-RET` | 分型 PASS/FAIL（keyword/vector/hybrid/graph） | graph 型非 NA 且 recall@5≥0.80 | P0 |

**规则**：
```
P0 全过才可讨论 0.5 重跑；soft 只记录趋势；
GATE-RET 分型单独报告，禁止平均掩盖；NOT_APPLICABLE 不算通过；
A/B 用同问题同 edition；答案正确性人判 rubric（0/1/2）；
LLM-as-judge 只作预筛，不替代人判 P0；偏差（位置/长度/自增强）需校准。
```

**为什么**：C0 原路线用 gold KP/IAA 作为解禁条件；人裁定最终面向人呈现与任务，故以问题→证据/答案/时间/偏好为准，IAA 仅诊断。

**怎么验**：固定问题集与 edition；机器算 recall/NDCG/answer（人判 rubric）；A/B 同问题；2× 确定性；GATE-RET 逐型 PASS/FAIL；报告样本量/置信区间。P0 失败或 graph=NA 不通过。

**外部证据**：
| 来源 | URL | 访问日期 | 映射 |
|---|---|---|---|
| BEIR | https://arxiv.org/abs/2104.08663 | 2026-11-05 | recall/nDCG 异构检索评测；支持分型 |
| MS MARCO | https://arxiv.org/abs/1611.09268 | 2026-11-05 | 真实问题/答案/排序任务；支持 answer/retrieval 指标 |
| Chatbot Arena | https://arxiv.org/abs/2403.04132 | 2026-11-05 | 成对偏好/统计；支持 P-PREF |
| LLM-as-a-Judge | https://arxiv.org/abs/2306.05685 | 2026-11-05 | judge 偏差/校准；支持 LLM 预筛+人判 P0 |

**反例**：只报平均分；graph=NA 算通过；只 LLM judge 定 P0；A/B 不同问题。
**边界**：无答案问题；多证据；小样本；judge 疲劳。
**风险**：问题偏差；答案 rubric 主观；LLM judge 偏差。
**建议裁决**：采纳 P0/soft 表 + GATE-RET 分型；P0 以人判/机器可复跑为准。
**待验证**：recall@5 0.80 的 query 数；answer rubric；A/B 样本量。
**证据等级**：A（论文/工程）。

---

## 5. C11 修订：0.5 解禁门槛（去 IAA）

**改什么**：0.5 rerun gate 改为：
```
① P0 任务指标全过：R-RECALL@5≥0.80、A-ANSWER≥基线、A-REF=100%、T-FIND 非劣、U-ACCESS=100%；
② graph 分型适用（非 NA）且 GATE-RET graph 型 PASS；
③ 无写事实/无 sidecar 写；2× 确定性（同 edition 同结果）；
④ 人时≤2–4h；judge 争议率/双判一致率报告；
⑤ 不要求 IAA 达线；IAA 仅诊断。
```
满足才允许 0.5 重跑并讨论发布；否则 HOLD。

**为什么**：IAA 只证明“标注一致”，不证明“图谱对任务有用”；人裁定 evaluation-first，故 gate 直接看任务指标与呈现效果。

**怎么验**：pilot 按 C9 跑 P0/soft；graph 分型逐型报告；A/B 同问题；2× 复跑同结果；人时计时；任一 P0 失败或 `NOT_APPLICABLE` ⇒ 不重跑。

**外部证据**：
| 来源 | URL | 访问日期 | 映射 |
|---|---|---|---|
| TREC | https://trec.nist.gov/ | 2026-11-05 | 任务/相关性评测流程；支持 P0 gate |
| GraphRAG | https://arxiv.org/abs/2404.16130 | 2026-11-05 | 图检索增益需真实任务评测；支持 gate 而非 IAA |
| Datasheets | https://arxiv.org/abs/1803.09010 | 2026-11-05 | 版本/用途/维护记录；支持 edition 与 gate |

**反例**：IAA 达标但任务无增益；graph NA 通过；不看人时；不复跑。
**边界**：小样本；问题集偏差；0.5 版本差异。
**风险**：P0 阈值过严/过松；评测泄漏。
**建议裁决**：采纳五项 gate；IAA 降为诊断。
**待验证**：P0 阈值统计功效；人时测量；0.5 重跑流程。
**证据等级**：A（论文/工程）。

---

---

## 5A. C6 语义边（受影响）：候选假设，不做 gold IAA

**改什么**：语义边从“需 gold edge + IAA”改为 **edge_candidate 假设**：由 agent/结构/检索提出 `{source,target,type,contain_kind?,label=semantic,evidence_refs,confidence}`；只保留 S0 三类型；用“问题→证据链路是否提升任务”评估，不要求人标 gold edge。

**为什么**：边本身可能不是唯一真值；其价值应体现在检索/答案/时间上，避免为边做大规模 IAA。

**怎么验**：消融（有边/无边）比较 C9 指标；边候选的 precision 只作诊断（少量抽检）；若消融无增益，砍边或只保留结构+检索。

**外部证据**：
| 来源 | URL | 访问日期 | 映射 |
|---|---|---|---|
| GraphRAG | https://arxiv.org/abs/2404.16130 | 2026-11-05 | 图关系用于检索增益评估；支持边价值由任务验证 |
| DocRED | https://arxiv.org/abs/1906.06127 | 2026-11-05 | 关系候选+证据；支持候选假设而非唯一 gold |

**反例**：为边做 50 条双标 IAA；结构/引用边冒充语义；无消融直接宣称边有用。
**边界**：跨文档边；多证据；低置信。
**建议裁决**：采纳 edge_candidate + 任务消融；不做 gold edge IAA。
**待验证**：消融显著性；边 precision 抽检比例。
**证据等级**：A（论文）。

---

## 6. 数据模型 / edition / provenance（C4/C5/C8/C9 受影响）

```
CANDIDATE{candidate_id, kind∈{kp,section,paragraph,formula,example,table,edge},
  source_span{file,line_start,line_end,anchor_id,structure_type},
  proposed_by∈{structure,agent,retrieval}, confidence, status∈{candidate,accepted,rejected},
  edition, evidence_refs[], created_at}
ACCEPTED{accepted_id, candidate_id, accepted_by, accepted_at, reason, edition}
EDGE_CANDIDATE{edge_candidate_id, source,target,type,contain_kind?,label?,evidence_refs[],
  confidence, status, edition}
PROVENANCE{source_id,target_id?,assertion_source,evidence_refs[],curated_by/at,decision_id}
```
- CANDIDATE 派生可重建；ACCEPTED 是人工确认后的稳定引用；二者分离。
- edition = sha256(源文件+候选集+已接受集+问题集+评测脚本)；口径不变。
- 许可/Tier 仍按 C0：Tier A 可发布/B 内部/C 禁用；Tier B 不进发布包/golden。
- 不写用户 `.memoria/sidecars`；candidate 写入隔离工作区。

**外部证据**：Datasheets（1803.09010）、Croissant（docs.mlcommons.org/croissant/...）、GraphRAG（2404.16130）——数据卡/元数据/派生图。
**建议裁决**：采纳 candidate/accepted 分离、edition、provenance；许可不变。
**证据等级**：A/C。

---

## 7. 对未重开项的影响

| 项 | 是否受影响 | 说明 |
|---|---|---|
| C1 用户/成功标准 | 间接 | 成功标准改为任务指标+呈现 A/B，不再 IAA |
| C2 来源/许可/隐私 | 否 | Tier A/B/C、PII、NOTICE 不变 |
| C3 本体/schema | 否 | S0 关系类型/字段不变；candidate schema 扩展在 AMENDMENT |
| C6 语义边 | 部分 | 不做 gold edge IAA；边作为候选假设，用任务增益评估 |
| C7 规模/采样 | 部分 | pilot 问题 20–30、人时≤2–4h；候选/问题按章隔离；不再 50 KP 双标 |
| C10 工具 | 部分 | 工具从标注转为 judge/AB 记录；不写用户库 |
| C12 交付 | 部分 | golden 改为 question/evidence relevance + judge 记录；Datasheet/FAIR 不变 |

---

## 8. 可执行 pilot 设计（≤2–4 人类小时）

```
Day 1（机器，0 人时）：
  - 选定 1 章；结构+agent 生成 100–200 KP candidates / 50 edge candidates；
  - 生成 25 个问题（从标题/例题/术语/用户 query 模板，作者不看系统输出）；
  - 检索 top-10 候选段；固定 dev/test 问题各半。
Day 2（人，2–3h）：
  - 25 问题 × 6 段 = 150 判断；20–30 秒/判断 ≈ 1–1.5h；
  - 10% 双判（15 判断）≈ 10min；争议裁决 20min；
  - A/B 2 sessions（旧/新呈现，各 8 问题）≈ 40–60min；SUS/偏好 10min。
Day 3（机器，0 人时）：
  - 算 recall@5/NDCG/answer/time/preference；2× 确定性；
  - 输出 metrics.json + sha + 判分记录。
总人时 ≈ 2.5–4h；超 4h 缩问题/候选数，不降判断质量。
```

**人只做**：相关性 yes/partial/no、A/B 偏好、争议裁决。**机器做**：候选生成、排序、指标、去重、确定性。

---

## 9. 风险 / 反例 / Falsifiers

| 风险 | 反例 | Falsifier（什么会推翻本设计） |
|---|---|---|
| 问题偏差 | 问题只覆盖易检索段 | 新图谱在分层问题上无增益/负增益 |
| 评测泄漏 | 问题作者看系统输出 | test 问题与 dev 同源、指标异常高 |
| LLM judge 偏差 | 位置/长度/自增强 | LLM 与人判一致率低（<70%） |
| 小样本 | 25 问题不稳 | 置信区间跨 0；换问题集结论翻转 |
| 呈现偏差 | A/B 顺序/学习效应 | 交换顺序后偏好反转 |
| 候选不足 | 结构切分漏证据 | recall@5 低且候选无法覆盖 |
| 成本失控 | 又变成标注 | 人时 >4h 或判断数 >300 |
| 不可复现 | 不同 edition/随机 | 2× 结果不一致；edition 变 |

**外部证据**：LLM-as-a-Judge（2306.05685）偏差；Chatbot Arena（2403.04132）偏好统计；TREC 评测流程；BEIR 分型。

**反例**：把 LLM judge 当 P0；问题集/阈值同源；A/B 只做一轮；无 falsifier。
**建议裁决**：采纳风险表+falsifiers，pilot 先验证；不通过则回退设计而非加人时。

---

## 10. 外部证据核验表（全部 HTTP 200，访问 2026-11-05）

| 来源 | URL | title | http_status | verified_at |
|---|---|---|---|---|
| TREC | https://trec.nist.gov/ | Text REtrieval Conference | 200 | 2026-11-05 |
| BEIR | https://arxiv.org/abs/2104.08663 | BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models | 200 | 2026-11-05 |
| MS MARCO | https://arxiv.org/abs/1611.09268 | MS MARCO: A Human Generated MAchine Reading COmprehension Dataset | 200 | 2026-11-05 |
| Chatbot Arena | https://arxiv.org/abs/2403.04132 | Chatbot Arena: An Open Platform for Evaluating LLMs by Human Preference | 200 | 2026-11-05 |
| LLM-as-a-Judge | https://arxiv.org/abs/2306.05685 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | 200 | 2026-11-05 |
| GraphRAG | https://arxiv.org/abs/2404.16130 | From Local to Global: A Graph RAG Approach to Query-Focused Summarization | 200 | 2026-11-05 |
| DocRED | https://arxiv.org/abs/1906.06127 | DocRED: A Large-Scale Document-Level Relation Extraction Dataset | 200 | 2026-11-05 |
| Artstein & Poesio | https://aclanthology.org/J08-4004/ | Survey Article: Inter-Coder Agreement for Computational Linguistics | 200 | 2026-11-05 |
| Datasheets | https://arxiv.org/abs/1803.09010 | Datasheets for Datasets | 200 | 2026-11-05 |
| Croissant | https://docs.mlcommons.org/croissant/docs/croissant-spec.html | Croissant Format Specification | 200 | 2026-11-05 |
| CC BY 4.0 | https://creativecommons.org/licenses/by/4.0/ | Attribution 4.0 International | 200 | 2026-11-05 |
| NIST Privacy Framework | https://www.nist.gov/privacy-framework | Privacy Framework | 200 | 2026-11-05 |

**本仓证据**：`CHARTER.md:5`（0 semantic/NOT_APPLICABLE）；`S0-terms-v1.md:35-41`（E_relation_min）；S10（candidate/write boundary）；S9（GATE-RET/edition）；C0 v1/A-v2（许可/Tier）。语料观测 sha `43d1449d…`（298 文件，2026-11-05）。

---

## 11. 待验证 / 最争议

**待验证**：① 20–30 问题统计功效；② 25 问题×6 段是否 ≤2h；③ LLM judge 与人判一致率；④ recall@5 0.80 是否可达；⑤ 命题级 vs 概念级；⑥ A/B 顺序/学习效应；⑦ 候选覆盖。

**最争议 3 点**：
1. **完全去 gold** 是否会让评测过软：需 P0 人判+机器锚点守住，不能只靠 LLM judge。
2. **问题集代表性**：25 问题能否代表 126k 文本；是否需按章/题型分层扩到 50。
3. **语义边是否仍需要**：若消融显示无增益，是否砍掉边/只保留结构+检索。

---

## 12. 对 C0 正文的变更声明

本 AMENDMENT 只覆盖 C4/C5/C8/C9/C11 及 C6/C7/C10/C12 的受影响口径；**C1/C2/C3 不变**；不修改 `C0-proposal-A.md` 正文，不覆盖 v1/v2；0.5 仍 HOLD，直到本 AMENDMENT 冻结 + pilot 执行 + gate 通过。
