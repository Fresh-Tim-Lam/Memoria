# C0-AMENDMENT-1 独立异议与 A/B 差异（evaluation-first）

> **依据**：人裁定 C0 转 **evaluation-first**（去 gold KP/IAA）；`CHARTER.md` C1–C12；`C0-corpus-v1.md`/`C0-RULINGS.md`；0.5 HOLD `dec-20261105-cb24f93e`；S0–S10 冻结。
> **对象**：`C0-AMENDMENT-1-proposal-A.md`（主办研究，sha **`7e5c9069e3c63f3ea3f03a8cfd0f3c764eb21fe14d9fba0483b863d0da2f92cb`**，21,085 B）与 `C0-AMENDMENT-1-proposal-B.md`（本复核方，sha **`7ab055e9b4ed7b0932fe1bbb9f5c64abe019e59f71b9ec0c2b058ed9efb83471`**，19,007 B）。
> **性质**：B 写作时未读 A；完成后对照；逐项列差异、不合并。
> **证据等级**：A=论文/标准/官方；B=本仓冻结/实测；C=工具文档；PI=假设。

---

## 0. A/B 差异总表（evaluation-first 关键项）

| 项 | A（A-v1） | B（B-v1） | 差异与判断 |
|---|---|---|---|
| C4 评测单元 | KP→candidate unit（结构 span + agent 提议，可重叠/嵌套），不做 gold；粒度用任务指标调 | SectionUnit（section/1–3 段）为评测单元；KP 仅内部诊断 | A 更贴近“候选导航”；B 更稳定、可判；**A 的 candidate 无唯一性，评测依赖候选生成**。 |
| C5 人类锚点 | Judge Protocol：20–30 题 × 5–10 候选段判 `contains_answer`；A/B 2 sessions；≤4h | MHA：20–25 题、2 名人类独立 answer/citation/no-answer + 第3裁决；≤4–6h | **A 只判“段含答案”，未要求人类独立答题/引用支持**；B 有 answer-level 锚点（P0-2）。 |
| C8 可靠性 | 10% 双 judge、`Cohen κ 可选、不设硬线`；争议>30% 修题；IAA 仅诊断 | 2 人类 answer/citation、κ/一致率分指标；citation 100%；不达线不扩 | **A 的 10%/无硬线不能防自洽**；B 更硬（P0-2）。 |
| C9 指标 | P0：recall@5、answer（人判/可机判）、A-REF、T-FIND 非劣、U-ACCESS、GATE-RET；S-SEM **soft 方向** | P0：MHA answer/citation/no-answer、section recall@5、**graph 消融方向**；soft：NDCG/judge/time/preference | **A 的语义边价值是 soft，0.5 可在无边增益下通过**（P0-1）；B 把消融设 P0。 |
| A/B | 同问题/edition；A/B 2 sessions；T-FIND P0 非劣；preference soft | 盲评/随机/平衡顺序、同 UI/corpus；A/B 仅 soft；MHA+消融 P0 | **A 的 A/B 未给随机化/学习效应/样本量；T-FIND 小样本非劣作 P0 风险**（P0-3）。 |
| 消融 | 有边/无边比较 C9；S-SEM soft 方向 | full vs no-sem-edge（同节点/同 lexical）+ structural/random/keyword-only；P0 方向 | A 消融不完整（未控节点/索引/结构边）；B 更可证伪（P0-1）。 |
| 预算 | 20–30 题×5–10 段 + A/B 2 sessions，≤4h；不含出题/裁决/分析 | 20–25 题、2 人类锚点+裁决+消融/分析，≤4–6h；超时缩题 | **A ≤4h 估算偏乐观**（P1-1）；B 更现实。 |
| 许可/edition | Tier/edition 不变 | 同 | 一致。 |
| Falsifiers | 有风险表（LLM judge 一致率<70% 等） | 8 条 falsifiers，含消融/问题泄漏/A/B 混杂/预算 | A 较少；B 更完整。 |

**总判断**：A 更“轻”（只判相关性/偏好），但 **去 gold 后的人类锚点太薄、语义边价值仅 soft、A/B/池化有假阳性风险**；B 更“硬”（answer/citation 人类锚点 + 消融 P0），但成本更高（4–6h）。**P0 集中在 A 的 3 个假阳性缺口**。

---

## 1. 异议（P0/P1/P2）

### P0-1（A）语义边价值仅为 soft（S-SEM），0.5 可在“无边增益”下通过

- **议项**：C9/C11/C6（evaluation-first 的 falsifier）。
- **异议**：A C9 把 `S-SEM` 定为 **soft（方向）**，C11 的 0.5 五条件不含语义边消融；只要 recall/answer/T-FIND 达标，即使 **去掉语义边完全不差**，A 仍可解禁 0.5。这样“图谱/语义边”可能只是装饰；evaluation-first 失去“验证 graph 价值”的目的。A 的消融只写“有边/无边比较 C9”，未控制同节点/同 lexical/结构边/随机边。
- **反例**：keyword-only 已 recall@5≥0.80；full graph 与 no-sem-edge 无差异；S-SEM soft 仍 PASS ⇒ 0.5 解禁，但语义边无贡献。
- **修复**：把 **edge ablation 方向性设为 P0**：同 corpus/edition/题，full graph vs no-sem-edge（同节点/同 lexical index）vs structural/random 对照；要求 full > no-sem-edge 且差异达预注册效应量，structural/random 不优于 full；否则 0.5 不解禁（或明确“只上检索、不上 graph”）。
- **严重度**：**P0（会放过假阳性/装饰边）**。

### P0-2（A）人类锚点太薄：只判“段含答案”，10% 双判无硬线，answer/citation 可由模型/实现者自洽

- **议项**：C5/C8/C9（最小人类锚点）。
- **异议**：A C5 人只判候选段 `contains_answer∈{yes,partial,no}`，不要求人类独立答题/判引用支持；C8 只 **10% 双 judge**，`Cohen κ 可选、不设硬线`，争议>30% 才修题；C9 `A-ANSWER` 写“人判/可机判”、`A-REF` 只要求引用完整率。去掉 gold KP 后，**没有独立 answer key / citation 支持的人类锚点**，模型可以“答案流畅 + 引用存在 + 自洽”通过；10% 双判也无法证明 90% 单判可靠。
- **反例**：实现者/同一人判 answer；引用链接存在但 span 不支持 claim；A-ANSWER 由 LLM judge 预筛后人只看少量；双判只覆盖容易题。
- **修复**：MHA 至少 20 题 **100% 人类 answer correctness**（correct/partial/incorrect）+ **citation support**（span 是否支持 claim，支持/部分/不支持）+ **no-answer 拒答**；2 名独立人类（非实现者）或 1 人+独立复核；报告 answer/citation 一致率（κ/一致率），不达线不扩 test；LLM judge 只作预筛/诊断，不作 P0。
- **严重度**：**P0（模型自洽=质量）**。

### P0-3（A）问题候选池/判定偏差 + A/B 混杂：recall 与 T-FIND 可被系统性抬高

- **议项**：C5/C9（问题集/候选池/A/B）。
- **异议**：A C5 每问题只给 **5–10 个候选 section/paragraph（含 top1/top3/随机负例）** 让人判；候选来自系统检索，**未判的 section 不进 qrels**，recall@5 只在系统候选池内计算 ⇒ **池化偏差**，召回被抬高；且候选排序可能暗示答案。A/B 只写“同问题/edition、2 sessions”，未给随机化/顺序平衡/学习效应/洗脱/样本量；`T-FIND` 用 A/B 小样本非劣作 P0，噪声/学习效应可能反转。
- **反例**：系统漏掉的相关 section 从未被 judge；recall@5=1.0 实际只覆盖系统池；A/B 先旧后新，学习效应使新更快；样本 8 题 T-FIND 非劣。
- **修复**：① section 相关性用 **独立分层池**（系统 top-k + 独立随机/标题/邻接采样；未判=unknown 不计 TP；报告 pooling 覆盖）；② judge 候选 **随机顺序/隐藏来源**；③ A/B **随机/平衡顺序、同 UI/corpus/数据量、练习/洗脱、盲评、样本量/功效**；`T-FIND` 降为 soft 或按功效设计；④ 问题集预注册/独立出题/test 隔离。
- **严重度**：**P0（评测可被池化/顺序抬高）**。

### P1-1（A）≤2–4h 预算偏乐观：未含出题/裁决/分析/消融，20–30 题×5–10 段 + A/B 2 sessions 很难 ≤4h
- **异议**：A C5 算 100–240 次判断×20–30s=1–2h，A/B 2 sessions=1–2h，合计 2–4h；但未含 **问题设计与预注册、候选池构造、双判裁决、答案 rubric、消融/分析、许可/清洗**；实际 4–6h。若硬压 4h，会压缩人类锚点/裁决，反而增加假阳性。
- **修复**：A 明确 4h 不含出题/分析；pilot 记录实际工时；20 题/1 人+1 复核的 4h 版本与 2 人 6h 版本二选一；超时缩题不降锚点质量（B 的 4–6h 更现实）。
- **严重度**：P1（预算现实性/审计）。

### P1-2（A）20–30 题无统计功效/效应量；P0 阈值 0.80/非劣无置信区间
- **异议**：A recall@5≥0.80、T-FIND 非劣、answer≥基线均无样本量/CI/效应量；20 题下 0.80 的 CI 很宽；A/B preference 新≥50% 几乎无信息。
- **修复**：预注册效应量/最小可检测差异；报告 bootstrap CI；A/B 按 paired 设计/功效计算；20 题只作 pilot，不作 0.5 唯一依据；B 同需补。
- **严重度**：P1（统计可判）。

### P2 清单
| # | 项 | 修复 |
|---|---|---|
| P2-1 | A judge `contains_answer` 无答案 rubric/引用支持 | 加 answer rubric + citation support；B 已有 |
| P2-2 | A 10% 双判/争议 30% 任意 | 预注册比例/阈值；报告样本/缺失；不达标缩题 |
| P2-3 | A T-FIND P0 非劣 | 降 soft 或按功效设计；A/B 随机/平衡 |
| P2-4 | A S-SEM soft | 按 P0-1 升 P0 方向；否则 0.5 不解禁 graph |
| P2-5 | A 候选重叠/嵌套无 gold | 允许 candidate 但评测用 section；候选生成确定性 |
| P2-6 | 许可/edition | MHA/答案/引用也受 Tier/edition；Tier B 不发布 |
| P2-7 | 外部证据 | A 缺 RAGAS/ARES/统计功效；B 已补；A 可补 |
| P2-8 | falsifiers | A 需加“消融无差/池化/顺序反转/预算超”四条 |

---

## 2. 点名审查结论

1. **去 gold 后防模型自洽**：A **P0-2**（人类锚点太薄）；B 有 answer/citation 人类锚点 PASS。
2. **问题集偏差/泄漏**：A 有问题作者不看输出/问题级 dev-test，但候选池偏差 P0-3；B 独立出题/预注册/按 section 隔离 PASS。
3. **section/paragraph 相关性可靠性**：A/B 均用 section；A 只判候选/含答案，B 用 graded + 多 acceptable；A 粗粒度假阳性 P0-3；B 更稳。
4. **A/B 混淆**：A 未给随机化/学习效应/功效 P0-3；B 随机/平衡/盲/soft PASS。
5. **语义边消融**：A **P0-1**（soft/不完整）；B 同节点/同 lexical/structural/random P0 方向 PASS。
6. **指标可操纵性/P0-soft**：A P0 含 T-FIND 非劣、S-SEM soft，可操纵；B P0 人类锚点+消融，soft 时间/偏好，更稳；A P1-1/P1-2。
7. **≤2–4h 现实性**：A 偏乐观 P1-1；B 4–6h 更现实；均需实际工时/审计。
8. **许可/Tier/provenance/edition**：A/B 均称不变 PASS；需把 MHA 问题/答案/引用纳入 Tier/edition（P2-6）。
9. **falsifiers**：A 有风险表但少；B 8 条 PASS；A 需补 P2-8。
10. **外部证据**：A 有 TREC/BEIR/Chatbot Arena/LLM judge；B 有 RAGAS/ARES/LLM judge/A/B/power；A 缺统计功效/RAG 人工锚点证据（P2-7）。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P0-1（A）语义边价值仅 soft**：0.5 可在去边不差时通过 ⇒ graph 可能是装饰。修复：edge ablation 方向性 P0（同节点/同 lexical；structural/random 对照；预注册效应量）；否则不解禁 graph/0.5。
2. **P0-2（A）人类锚点太薄**：只判“段含答案”+10% 双判无硬线，无独立 answer/citation 人类锚点 ⇒ 模型自洽可过。修复：20 题 100% 人类 answer/citation/no-answer；2 人独立或 1+复核；κ/一致率；LLM judge 仅预筛。
3. **P0-3（A）候选池/顺序偏差**：只判系统返回的 5–10 段 ⇒ recall 池化偏差；A/B 无随机/学习效应/功效，T-FIND 非劣作 P0 风险。修复：独立分层池+未判 unknown；随机顺序；A/B 随机/平衡/盲/功效；T-FIND soft。

## 4. 结论

- 两版均接受 evaluation-first；**A 更轻但 3 个 P0 假阳性缺口**；B 更硬但成本 4–6h。若人坚持 ≤4h，必须明确“4h 版只做 20 题 1 人+复核”，并把 C11 解禁拆成两阶段（4h pilot 不等于 0.5 解禁）。
- **P0 必须先修**；P1 预算/统计；P2 见清单。
- 未改 C0/冻结稿、未写产品代码、未 commit；差异逐项列出未静默合并。

> 参考锚：A C5/C8/C9/C11；B C5/C8/C9/C11；E1 RAGAS 2309.15217；E2 ARES 2311.09476；E3 2306.05685；E4 2305.17926；E10/E11 A/B；E12 功效。
