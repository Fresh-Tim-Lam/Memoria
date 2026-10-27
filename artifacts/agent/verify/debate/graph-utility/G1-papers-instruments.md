# G1-A 源核实：GUE 六条文献线 —— 哪些现成仪器能直接套

> 角色：论文取证员（A 源）。只做 G1，不碰 G2–G6，不 commit。
> 取证日：2026-10-27（Asia/Shanghai）。
> 方法：`web_search` / OpenAlex / 直接抓取一手 PDF 与规范页；PDF 用本机 pdftotext 抽文后逐条核对。
> 标注约定：**【实验数字】**＝原文给出数据/统计；**【仅论断】**＝原文只有主张/定性描述；**【规范】**＝标准/方法论文档；**【综述】**＝survey 对他人工作的归纳。查不到全文的，在文末「核对状态」里明说，不用二手数字冒充一手。

---

## 0. 结论先行：六条线逐条判定

| # | 文献线 | 代表仪器 | 评的对象 | 能否直接套到"节点链路" | 判定 |
|---|---|---|---|---|---|
| ① | KG 质量 | Zaveri 18 维/69 指标 | 数据/三元组（LOD 发布质量） | **部分**：可当数据级检查清单，不能评链路语义 | 裁剪后借用 |
| ②a | 本体评价·OntoClean | rigidity / identity / unity / dependence | **类/属性**的建模决策 | **不能**：需要类层与 subsumption，当前是实例边 | 不可用 |
| ②b | 本体评价·OntoQA | schema metrics + population metrics | 本体 schema + 实例库 | **不能**：62 条边无类型，schema 指标无定义 | 需先补类型 |
| ②c | 本体评价·CQ | competency questions（功能需求→验收） | 本体/模型**整体** | **可改造**：最接近"链路必须支撑哪个提问"，但链路级判据要自建 | 改造为骨架 |
| ③ | Cranfield/IR 评价 | topic set + pooling + 判定矩阵 + nDCG/MAP | **系统间比较** | **不能解决** n=13/20 的统计问题；只能做单用户工程 A/B | 不能当证明 |
| ④ | 元路径语义 | PathSim / metapath2vec | 同类型节点对的**相似度** / 节点表示 | **不能**：评的是相似度，不是路径语义有效性 | 明确错配 |
| ⑤ | KG refinement | Paulheim 评价方法分类 | 图/边的增删 | **部分**：gold standard / ex post 可借；**ablation 不是该领域标准** | 借用方法，不借"标准" |
| ⑥ | 人判一致性 | Cohen's κ / Krippendorff's α | 标注可靠性 | **可以直接用**（α 优先 + 报告 CI） | 可用 |

**总问题答案（先给）：六条线里没有任何一个现成仪器能直接评价「从图中取出若干节点组成的链路，是否具有语义 / 对下游任务有用」。**
最接近的三个零件是：②c CQ（把"链路必须支撑哪个提问"变成验收）、③ Cranfield 式 relevance judgment（判"这条链路对任务有没有用"）、⑤ gold standard / ex post（判边对错）。但它们的**分析单元**都不是"一条多节点链路"，把三者拼起来的那一层（链路构造 + 链路级判据 + 判定协议）**必须自建**。理由在 §7 展开。

---

## 1. ① KG 质量评估：Zaveri et al. 2016

### 身份
- **文献**：Zaveri, Rula, Maurino, Pietrobon, Lehmann, Auer. *Quality assessment for Linked Data: A Survey*. **Semantic Web 7(1): 63–93, 2016**（在线 2015）。
- **URL**：https://doi.org/10.3233/SW-150175 （摘要经 OpenAlex 核对：https://openalex.org/works/doi:10.3233/SW-150175 ；全文本次抓取失败，见 §9）
- **类型**：系统文献综述（survey + 概念框架）。

### 具体仪器/指标（原文摘要 + 可及转写）
- 摘要原文（经 OpenAlex 核对，非印象）：**"provide a comprehensive list of 18 quality dimensions and 69 metrics"**；并"qualitatively analyze the **30 core approaches and 12 tools**"。→ 这是**分类学 + 指标目录**，不是一个可执行的评分器。
- 维度分组（转写依据：OPAL 交付物 D3.1 附录 "Table Z.A–Z.R: Results from Zaveri et al. (2016)"，https://files.dice-research.org/projects/OPAL/Deliverables/OPAL_D3.1_Specification_of_quality_criteria.pdf ）：
  - **Accessibility**：availability、licensing、interlinking、security、performance
  - **Intrinsic**：accuracy、consistency、conciseness
  - **Trust**：reputation、believability、verifiability、objectivity
  - **Dynamicity**：currency、volatility、timeliness
  - **Contextual**：completeness、amount-of-data、relevancy
  - **Representational**：representational-conciseness、representational-consistency、understandability、interpretability、versatility
  - **重要的核对限制**：OPAL 转写把这些子维展开后合计 **23** 个，而原文摘要说 **18** 个。两者**可能**是"主维 vs 子维展开"的差异，也可能是 OPAL 参考了 Zaveri 的早期版本——**本次没有一手全文，无法裁决**。因此：18/69 是摘要核实数，可引；上述维度名是 OPAL 的二级转写，**不要当作"原文逐字清单"引用**。
- **哪些可机检、哪些需人判**（依据 OPAL 转写中每条指标的计算定义）：
  - 可机检（有明确分子/分母或检测规则）：completeness（schema/property/population/interlinking completeness，均为"已表示/总数"）、conciseness（unique/total）、interlinking degree（网络度量）、license 的机器可读指示、availability（HTTP/SPARQL 可达性）、timeliness（时间差公式）。
  - 需人判或外部参照：semantic accuracy / correctness（需 unbiased trusted third party 或 gold standard）、trust 类（reputation、believability、verifiability、objectivity）、relevance、understandability/interpretability。这些的"分母/真值"不在图内。
- 代价：69 个指标不是开箱即用的评分器；多数 completeness/accuracy 指标需要**参考本体或 gold standard**才能算；LOD 专属维度（licensing、interlinking、SPARQL availability）对内部教材图大多不适用。

### 能否当我们的检查清单？
- **能当"数据级 QA 清单"的子集**：完整性、一致性、简洁性、可达性这类可以在建图后自动跑。
- **不能当"链路语义/效用"判据**：它的分析单元是数据集/三元组，不是"一条由若干节点组成的链路"；没有"路径是否成立/是否有意义"的维度。
- 中文教材场景不适用处：licensing / interlinking / SPARQL endpoint / volatility 等 LOD 发布维度基本 N/A；semantic accuracy、relevancy 需要教材 gold standard，成本高。

### 反驳条件（何时不适用）
1. 若目标是评价"链路语义有效性"→ 该分类学没有这个维度，直接套会得到"数据很干净但链路无意义"的假阳性。
2. 若图不是 RDF/LOD（无 URI、无 dereferenceable endpoint）→ accessibility 组指标无定义。
3. 若没有参考本体/gold standard → accuracy/completeness 类指标无法计算，只剩可达性/结构计数。

### 证据强度
**中**：同行评审综述、18/69 的规模经摘要核对；但本次**未取到全文**（IOS Press 付费、镜像被 Cloudflare 拦），维度名依据 OPAL 转写；且它是分类学，不是实验。

---

## 2. ② 本体评价

### 2a. OntoClean（Guarino & Welty）

- **身份**：Guarino & Welty. *Evaluating Ontological Decisions with OntoClean*. **Communications of the ACM 45(2), 2002**。DOI https://doi.org/10.1145/503124.503150
  可及全文（本次核对用）：https://www.omgwiki.org/MBSE/lib/exe/fetch.php?media=mbse:ontoclean.pdf
- **类型**：方法论（【规范】/方法论文，无实验数字）。
- **具体仪器**：四个**元属性（metaproperties）**，用来判断类/属性之间的 subsumption 是否合法：
  - **rigidity**：属性是否对"所有实例"都本质（rigid / non-rigid / anti-rigid）。原文例：`car part` 是 anti-rigid（发动机可拆下装到别处），`engine` 是 rigid；**anti-rigid 类不能 subsumption rigid 类**。
  - **identity criteria**：判断"两个实例何时是同一个"的充分/必要条件（跨时间识别）。
  - **unity**：判断"若干部分何时构成一个整体"（如 ocean 是多个 water 量；bound volume 的 unity 条件）。
  - **dependence**：实体是否必须依赖另一实体存在。
  - 用法：逐个类标注元属性，检查 subsumption 是否与元属性冲突（如把 part-of 误写成 subclass-of）。
- **能否判断"一个节点概念是否清晰"**：
  - **只在类层可用**：如果"节点"是 class（有实例、有 subsumption 关系），可以用 identity + rigidity 检查它是否是一个可辩护的类。
  - **对实例/边不可直接用**：OntoClean 的操作对象是 classes/properties 的层级；一条由实例节点组成的链路不进入它的判定范围。
  - 对"知识点"：若知识点被建模为 class（且知识点之间有 is-a），可以做"这个概念有没有 identity criteria"的检查；若知识点只是无类型的节点标签，OntoClean 无从下手。
- **代价/局限**：纯人工、需要哲学式论证与领域承诺；不产出数值分数；不能自动化；对事件/过程类（identity 跨时间）尤其难。
- **反驳条件**：无 class 层 / 节点是实例 / 关系不是 subsumption → 不适用；需要可复现打分 → 不适用。

### 2b. OntoQA（Tartir et al.）

- **身份**：Tartir, Arpinar, Sheth. *OntoQA: Metric-Based Ontology Quality Analysis*. **2005 IEEE ICDM Workshop on Knowledge Acquisition from Distributed, Autonomous, Semantically Heterogeneous Data and Knowledge Sources**。
  URL（OpenAlex 书目页，含摘要）：https://openalex.org/W1534981661
  一手 PDF（Wright State 仓库）：https://corescholar.libraries.wright.edu/cgi/viewcontent.cgi?article=2036&context=knoesis ——**本次抓取被 Cloudflare 403**。
- **类型**：方法 + 案例应用（摘要有"evaluation of several ontologies using these metrics"；本次未取全文，**无实验数字可核**）。
- **摘要可核内容**：OntoQA "analyzes ontology **schemas** and their **populations** (i.e. knowledgebases) and describes them through a well defined set of metrics"；指标用于"highlight key characteristics of an ontology schema as well as its population"。
- **具体指标（lead 给的名称：schema richness / relationship richness / inheritance richness）**：这三个名称与 OntoQA 的"schema metrics"家族一致，但**本次未能从一手全文核对公式**（403）。可确定的结构性事实是：schema 类指标以 **class / property / inheritance** 的计数为输入；population 类指标以 **每个 class 的实例数**为输入。**在这两个输入缺失时，这些指标没有定义**——这是定义层面的结论，不依赖具体公式。
- **对 62 条边（无类型）是否可用**：**不可用**。62 条边如果没有 (a) class/property 类型、(b) subClassOf 继承、(c) 实例的 class membership，则：
  - relationship richness / inheritance richness 的分母（关系数、继承数）无法定义；
  - population 类指标无法按 class 分组；
  - 只能算"度/连通性/聚类系数"这类图指标——那已经不是 OntoQA。
- **代价**：必须先补类型层（schema）；补完后它评的是**schema 结构**，仍不评链路语义。
- **反驳条件**：若先把边类型化并建立 class 层级 → 指标可算，但那时它回答的是"schema 丰不丰富"，不是"链路对不对/有没有用"。

### 2c. Competency Questions（Grüninger & Fox）

- **身份（源头）**：Grüninger & Fox. *Methodology for the Design and Evaluation of Ontologies*. **1995 IJCAI Workshop on Basic Ontological Issues in Knowledge Sharing**。
  URL（OpenAlex 书目页，含摘要）：https://openalex.org/W1665997306
  **核对限制**：本次只取到摘要（无 DOI，全文未取到）。摘要明确该文是"methodology used ... for the design and evaluation of integrated ontologies"，以 motivating scenarios 为起点；**摘要本身没有出现 "competency question" 字样**——CQ 与该方法的绑定来自后续文献，本次未用一手全文核对，标为"出处待核"。
- **现代可核定义（用于说明 CQ 是什么）**：*An Experiment in Retrofitting Competency Questions for Existing Ontologies*（2024，DOI https://doi.org/10.1145/3605098.3636053 ）摘要：**"Competency Questions (CQs) are a form of ontology functional requirements expressed as natural language questions"**；CQs 用于 ontology reuse、**testing**、requirement specification、pattern definition。
- **具体仪器**：CQ = 该模型/本体**必须能回答**的问题清单；做法是把自然语言问题形式化为查询/公理，验收"模型是否蕴含正确答案"。这是**需求驱动验收**，不是质量打分。
- **能否改造成"这条链路必须支撑哪个提问"**：**可以，而且这是六条线里最合适的骨架**。改法：
  1. 为一条候选链路写 CQ："要回答 Q，是否必须/可以经过这条链路？"
  2. 给 Q 配 gold answer（或至少可判定的答案键）；
  3. 验收 = 用该链路作为证据时，答案是否正确/是否唯一可辩护。
  - **但**：CQ 方法评的是"整个模型/本体能否回答"，不是"某条链路本身是否语义成立"；把它降到链路级，需要额外定义"链路作为证据"的判据与反例（同一答案可能有多条链路 → CQ 通过 ≠ 该链路必要）。这层是**自建**。
- **代价**：写 CQ + gold answer 的人工成本；CQ 的覆盖度决定验收强度；n 小的时候同样有统计问题（见 ③）。
- **反驳条件**：问题有歧义 / 无 gold answer / 一题多解（链路不唯一）→ CQ 通过不能证明链路有效；只有模型整体验收、没有链路级反例时，会高估链路质量。

---

## 3. ③ 任务型检索评价（Cranfield 范式）

### 身份
- **源头**：Cranfield 测试（Cleverdon 1960s）；TREC 将其工程化。本次核对的、与"小样本"直接相关的两份：
  - Voorhees & Buckley. *The Effect of Topic Set Size on Retrieval Experiment Error*. **SIGIR 2002**。
    NIST 页（含摘要，本次核对）：https://www.nist.gov/publications/effect-topic-set-size-retrieval-experiment-error
  - Sakai. *Topic set size design*. **Information Retrieval Journal, 2016**（Springer；DOI 10.1007/s10791-015-9273-z）。
    摘要页：https://link.springer.com/article/10.1007/s10791-015-9273-z

### 具体仪器（流程）
- 固定 **topic set**（信息需求集）→ 多系统/多配置跑 **runs** → **pooling**（把各 run 的 top-k 结果合并成待判池）→ 人工/专家给 **relevance judgments**（判定矩阵）→ 算 MAP/nDCG/P@k 等 → 比较系统。
- 关键假设：topic 是**从目标用户总体中抽样**的；判定者可代表用户；pooling 覆盖了相关文档（未判文档按不相关处理）。

### 在"小规模、单用户、个人知识库"上是否成立
- **样本量要求**：Sakai 摘要明确：传统 pooling 测试集通常 **n = 50–100 topics**；topic set size 应通过 **paired t-test / one-way ANOVA / confidence interval** 的统计功效要求反推，而这需要**历史 topic-by-run 分数矩阵**来估计 within-system variance（没有历史矩阵就无法做设计）。
- **n=13/20 能不能被这套范式救**：**不能**。Voorhees & Buckley 摘要：他们**只对 ≤25 topics 直接计算 error rate**，再外推到更大集合；结论是"error rates found are **larger than anticipated**，topics 少时下'方法 A 更好'的结论要非常小心"。n=13/20 正落在这个"误差大、外推不可靠"的区间；而且单用户知识库没有"判定者总体"、没有多系统 pool（往往只有 1–2 个配置），Cranfield 的两个前提都不满足。
- **它能给你什么**：单用户的**工程 A/B 描述性比较**（同一 topic set 上比较两个索引配置，报告逐题差值 + 置信区间/ bootstrap），以及"不要用 13/20 题去认证阈值"的论证依据。
- **它不能给你什么**：可泛化的"合格线"、跨用户结论、统计显著的阈值认证。

### 代价/局限
- 判定成本 = topics × pool depth；pooling 有 pool bias（未被任何系统召回的文档永远不被判）；单判定者无法估计 judge 间一致性（需要 ⑥）。
- **反驳条件**：若只做单用户、单系统、描述性工程决策 → Cranfield 可作为流程模板；若要"证明某阈值/某方法更好" → n 必须按功效分析设计，13/20 不够。

---

## 4. ④ 元路径语义：PathSim / metapath2vec

### 4a. PathSim
- **身份**：Sun, Han, Yan, Yu, Wu. *PathSim: Meta Path-Based Top-K Similarity Search in Heterogeneous Information Networks*. **PVLDB 4(11), 2011**。
  DOI https://doi.org/10.14778/3402707/3402736 ；可及全文（本次核对）：https://www.vldb.org/pvldb/vol4/p992-sun.pdf
- **它到底评什么**：**同类型对象之间的相似度**。给定一条**对称元路径** P，PathSim 用"两对象间路径实例数"与"各自可见度"的比值定义相似度（原文 Definition 4；满足 symmetric、self-maximum）。它假设**元路径的语义已经由用户选定**——"different meta paths give different semantic meanings"，选哪条路径是**输入**，不是被评价的对象。
- **实验数字【实验数字】**：DBLP（710K 作者、1.2M 论文）；对 15 个 query 人工标注 top-15，nDCG：PathSim **0.7446** > RW 0.7061 > SimRank 0.6289 > P-PageRank 0.5552 > PRW 0.5284；4-area 聚类 weighted NMI：PathSim 0.6507 vs RW 0.6485 vs PRW 0.6371（差距很小）。原文还发现**元路径太长会降低质量**。
- **能否评价"这条链路是否有语义"**：**不能，这是明确的错配**。PathSim 回答"给定这条元路径，两个节点有多相似"；它不回答"这条具体链路是否成立/是否有意义/对任务是否有用"。一条高相似度路径仍可能是错的（如"同作者"路径把两个不同领域的作者拉近）。
- **反驳条件**：若目标是"找相似节点/聚类"→ 可用；若目标是"验证链路语义"→ 不可用（会把"相似"误当"有效"）。

### 4b. metapath2vec
- **身份**：Dong, Chawla, Swami. *metapath2vec: Scalable Representation Learning for Heterogeneous Networks*. **KDD 2017**。DOI https://doi.org/10.1145/3097983.3098036
- **摘要可核内容**：用 **meta-path-based random walks** 构造异构邻居，再用 heterogeneous skip-gram 学节点嵌入；metapath2vec++ 同时建模结构与语义相关性；实验任务是 **node classification / clustering / similarity search**（摘要）。
- **它评什么**：节点表示在下游挖掘任务上的效果；**没有"路径语义有效性"这个输出**。元路径同样是超参/输入。
- **结论**：与 PathSim 同类错配；可作为特征/表示工具，不能作为"链路语义"判据。
- **代价/边界**：需要类型化的异构网络 schema；62 条无类型边连元路径都定义不了。
- **反驳条件**：无类型图 → 元路径不存在；要"可解释的链路判定"→ 嵌入不可解释。

---

## 5. ⑤ KG refinement：Paulheim 2017 survey

- **身份**：Paulheim. *Knowledge graph refinement: A survey of approaches and evaluation methods*. **Semantic Web 8(3): 489–508, 2017**。
  DOI https://doi.org/10.3233/SW-160218 ；可及预印本全文（本次核对）：https://www.semantic-web-journal.org/system/files/swj1083.pdf
- **类型**：survey（【综述】）。
- **对"删除冗余/错误边"给了哪些可操作方法**：survey 把 refinement 分为 **completion**（补缺失）与 **error detection**（找错误），再分 internal / external。错误检测的手段包括：outlier detection、逻辑不一致/推理、link prediction / link validation、外部源交叉验证等；检测到错误 axiom 后可**移除并尝试修正**。它**没有给出一个统一的"删边算法"**，而是方法目录。
- **评价方法（这是关键）**：survey §4/§7.2 归纳的评估方法是：
  1. **partial gold standard**（人工标注子集；可分 public / 非 public）；
  2. **silver standard**（用 KG 自身做参照；含 **split validation / cross validation**——留出边再预测）；
  3. **ex post evaluation**（把输出交给人工判官逐条判对错，报 precision + 找到的总数）；
  4. 指标以 **precision / recall / F-measure** 为主，另有 accuracy、AUC、RMSE、total new statements。
  - **重要更正：ablation（消融）不是该 survey 列出的标准评价方法。** 全文没有把 "ablation / downstream task drop" 作为一类评估方法；survey 自己也说各方法评价方式"mixed"、"only a minority evaluated on a whole, large-scale KG"、"statements about computational performance are rarely included"、"no common benchmarks"。
- **能否用 ablation 判"删边是否损害下游任务"**：作为**工程上的补充证据**可以，但按 Paulheim 的分类它属于**自建的任务型评估**，不是该领域"标准做法"。若要用，必须自己声明并给 baseline/control。
- **代价**：gold standard 人工标注贵；silver standard 有"KG 自身错误被当真理"的风险；ex post 不可复用（survey 明确指出 partial gold standard 可复用、ex post 不可）。
- **反驳条件**：没有 gold standard 且不愿做人工 ex post → 只能做 silver/split，结论受 KG 自身质量污染；把 ablation 当"领域标准"会被审稿人质疑（survey 无此分类）。

---

## 6. ⑥ 人判一致性：Cohen's κ vs Krippendorff's α

### 身份
- Cohen. *A coefficient of agreement for nominal scales*. **Educational and Psychological Measurement 20(1), 1960**。DOI https://doi.org/10.1177/001316446002000104
- Artstein & Poesio. *Inter-Coder Agreement for Computational Linguistics*. **Computational Linguistics 34(4), 2008**。可及全文（本次核对）：https://aclanthology.org/J08-4004/ （PDF: https://aclanthology.org/J08-4004.pdf ）
- Krippendorff. *Computing Krippendorff's Alpha-Reliability*. **2011**（方法说明）。可及全文：https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff's%20Alpha-Reliability.pdf
- Landis & Koch. *The measurement of observer agreement for categorical data*. **Biometrics 33(1): 159–174, 1977**。DOI https://doi.org/10.2307/2529310 （付费；benchmark 数字经 ERIC 开放论文核对：https://files.eric.ed.gov/fulltext/EJ1238388.pdf ）
- Hayes & Krippendorff. *Answering the call for a standard reliability measure for coding data*. **Communication Methods and Measures 1(1), 2007**。DOI https://doi.org/10.1080/19312450709336664 （α 的 bootstrap 置信区间方法）。

### 2–3 名判定者、20–60 个判定项时，哪种更合适
- **2 名判定者、名义标签**：Cohen's κ 是标准选择；**Krippendorff's α 在名义二判定者时与 κ 数值接近**（Artstein & Poesio：α 是更一般的框架，名义距离下二者近似）。
- **3 名判定者**：Cohen's κ 不适用于 >2 人；用 **Fleiss 多 π**（Fleiss 1971）或 **Krippendorff's α**。Artstein & Poesio 明确：α "applies to multiple coders"、任意测量层级、可处理缺失数据，并用无偏估计修正小样本；在层级标签/集合值标签上**推荐 α**。
- **小样本（20–60 项）**：
  - κ 的正态近似只在**大样本**下成立（Artstein & Poesio 引 Cohen 1960：sample sizes large 时才近似正态）；α 的分布未知，**必须用 bootstrap 求置信区间**（Krippendorff 2004 §11.4.2，经 Artstein & Poesio 转述；工具见 Hayes & Krippendorff 2007）。
  - 因此正确做法不是"算一个 α/κ 然后对合格线"，而是**报告点估计 + bootstrap CI**；20 项的 CI 会很宽，可能横跨"不可接受"到"可接受"。
  - Krippendorff 2011 明确 α "applies to ... large and small sample sizes alike, not requiring a minimum"——但"能算"不等于"估得准"；CI 宽度是硬约束。
- **合格线（行业惯例，给具体数字）**：
  - **Landis & Koch 1977** 的 κ 基准：<0.00 poor；0.00–0.20 slight；0.21–0.40 fair；0.41–0.60 moderate；**0.61–0.80 substantial**；**0.81–1.00 almost perfect**（数字经 ERIC 论文原文核对）。
  - **Krippendorff** 的 α 惯例：**0.67 只支持"highly tentative and cautious conclusions"；0.80 才是"solid results"**；其后期明确 **α=0.800 是"a pretty low standard"**（Krippendorff 1980 p.147 / 2004 p.242，经 Artstein & Poesio 与 Hovy et al. 两处转述核对；Hovy 文：http://www.cs.cmu.edu/~hovy/papers/10JNLE-IL-annot.pdf ）。
  - **重要限定**：Artstein & Poesio 明确说 CL 界"doubt that a single cutoff point is appropriate for all purposes"；Landis/Krippendorff 的数字是**惯例**，不是统计定律。20–60 项 + 2–3 人时，**先看 CI 是否跨线**，再谈达标。
- **代价**：双人独立标注 + 分歧裁决；α 需要 bootstrap 工具；κ 对 prevalence 敏感（Artstein & Poesio 讨论 bias/prevalence 问题，α 用无偏估计缓解）。
- **反驳条件**：判定项非独立（同一人多条）/判定者非独立（讨论后标注）→ 系数失效；标签是序数/层级 → 用加权 α/κ；n=20 且 CI 很宽 → 不能声称"达到 0.8"。

---

## 7. 总问题：有没有现成仪器能评价"节点链路是否语义/对任务有用"？

### 答案：**没有现成仪器。**
逐条看它们的分析单元（unit of analysis）：

| 文献线 | 分析单元 | 输出 | 为什么不能回答链路问题 |
|---|---|---|---|
| ① Zaveri | 数据集/三元组 | 质量维度得分/检查项 | 数据质量 ≠ 链路语义；没有"路径"概念 |
| ②a OntoClean | 类/属性层级 | 建模决策是否合法 | 不评实例链路；需要 class 层 |
| ②b OntoQA | schema + 实例库 | 结构丰富度指标 | 不评单条链路；62 边无类型时无定义 |
| ②c CQ | 整个本体/模型 | 能否回答需求问题 | 最接近，但"链路作为证据"的判据要自建 |
| ③ Cranfield | 系统（跨 topics） | 系统间相对优劣 | 不评单条链路；n 小无法推断 |
| ④ PathSim / metapath2vec | 同类型节点对 / 节点 | 相似度 / 嵌入 | 相似度 ≠ 语义有效性；元路径语义是输入 |
| ⑤ Paulheim | 边/三元组 | 错误检测 P/R/F | 不评链路；ablation 非其标准方法 |
| ⑥ κ/α | 判定者×判定项 | 一致性系数 | 只保证"人判是否可重复"，不提供判据本身 |

### 最接近的"零件组合"（可借用，但不是现成仪器）
1. **②c CQ** 提供"需求→验收"的骨架：为链路写"它必须支撑哪个提问"。
2. **③ Cranfield** 提供"判定矩阵"的操作：topic × 链路 → 有用/无用/部分有用，配 nDCG/精度与 bootstrap CI（但 n 小只能描述，不能认证阈值）。
3. **⑤ Paulheim** 提供"边级对错"的 gold standard / ex post 评价法与 P/R/F。
4. **⑥** 提供"多人判定是否可信"的 α + CI。

### 必须自建的那一层（这就是 GUE 的自建部分）
- **链路构造（chain construct）**：什么算一条"链路"？节点顺序、边方向、是否允许重复、长度上限、是否要求最小语义单元（例如"概念—关系—概念"）。
- **链路级判据（criterion）**：什么叫"有语义"？建议拆成可判定的子问题（例如：每条边是否被文本证据支持；链路是否覆盖 CQ 的答案路径；去掉任一条边后 CQ 是否还可答）。这些子问题在六条线里**没有现成定义**。
- **判定协议（protocol）**：CQ/relevance/边级 gold 的混合；2–3 名判定者、20–60 项时报告 α + bootstrap CI；用 adjudication 解决分歧；记录"一题多解"。
- **基线与效度**：至少一个随机链路基线 + 一个人工构造的正确链路集；否则无法证明判据有区分度。
- **明确边界**：如果只做"单用户工程决策"，用 ③ 的描述性 A/B 即可；如果要"统计上证明某类链路更好"，13/20 项不够——这与 ③ 的结论一致。

> 结论一句话：**六条线能给我们"评价的零件"和"不能这么做的理由"，但没有一条能直接输出"这条链路有语义/有用"的判决。GUE 的自建层是链路级判据 + 判定协议，不是又一套质量维度。**

---

## 8. 给 Lead 的结论：哪几条能直接用 / 哪条必须自建 / 三个关键数字

### 能直接用（或稍改）
- **⑥ 人判一致性**：2 人名义用 κ（或 α），3 人用 α/Fleiss；20–60 项必须报 bootstrap CI；合格线引 Landis & Koch 0.61–0.80 substantial / 0.81–1 almost perfect，Krippendorff α .80（.67 仅 tentative）。
- **⑤ Paulheim 的评价方法分类**：边级对错用 partial gold standard / ex post + P/R/F；**注意 ablation 不是该 survey 的标准方法**，若用需自声明。
- **③ Cranfield 的流程**：可作单用户工程 A/B 的模板 + "n 小不能认证阈值"的论证；**不能**用它把 n=13/20 变成统计结论。
- **① Zaveri 的子集**：可作数据级 QA 清单（完整性/一致性/可达性），不能当链路语义判据。

### 必须自建
- **链路语义/效用判据**：六条线没有。可借 ②c CQ 的验收骨架 + ③ 的判定矩阵 + ⑤ 的边级 gold，但"链路作为证据是否成立/是否必要/是否唯一"要自己定义并验证。

### 不能直接用（明确错配/前置条件不满足）
- **OntoQA**：62 条无类型边 → schema 指标无定义；补类型后才可算，且只评 schema 结构。
- **OntoClean**：只在 class 层可用；实例链路不进入判定。
- **PathSim / metapath2vec**：评相似度/表示，不评语义有效性；元路径语义是输入不是输出；无类型图连元路径都定义不了。

### 最关键的三个数字
1. **≤25 topics**：Voorhees & Buckley 2002 只对 ≤25 topics 直接算 error rate，且误差"larger than anticipated"；Sakai 2016 说传统 pooling 集合通常 **50–100 topics**、需按统计功效反推 → **n=13/20 不足以做阈值认证**。
2. **0.80 / 0.67**：Krippendorff α 的 0.80（solid / 最低严肃标准）与 0.67（仅 tentative）；Landis & Koch 的 0.61–0.80 substantial、0.81–1.00 almost perfect → 人判门槛应引这两个来源，且 20–60 项要报 CI。
3. **18 / 69**：Zaveri 的 18 个质量维度和 69 个指标——**规模说明它是数据级清单，不是链路判据**；另可补一个数字：PathSim 在 15 个标注 query 上 nDCG 0.7446 vs RW 0.7061，说明它做的是"相似排序"而非"有效性判定"。

---

## 9. 核对状态（诚实边界）

| 文献 | 核对程度 | 说明 |
|---|---|---|
| Zaveri 2016 | **摘要一级核对**（OpenAlex 摘要：18 dims/69 metrics/30 approaches/12 tools）；维度名依据 OPAL 转写 | IOS Press 全文本次抓取失败、镜像被 Cloudflare 拦；**未用 23 这个数** |
| OntoClean 2002 | **全文核对**（OMG wiki PDF） | 元属性定义/例子均来自原文 |
| OntoQA 2005 | **仅摘要核对**（OpenAlex）；PDF 403 | "schema richness/relationship richness/inheritance richness" 三词**未在一手全文核对**；仅用其"schema+population"的可核事实下结论 |
| Grüninger & Fox 1995 | **仅摘要核对**（OpenAlex）；无 DOI/全文 | "competency question" 字样未在 1995 摘要中出现；CQ 定义用 2024 论文（DOI 可核）补 |
| Voorhees & Buckley 2002 | **摘要核对**（NIST 页；含 ≤25 topics / error larger than anticipated） | 无全文；未引具体 error 数值（摘要未给表） |
| Sakai 2016 | **摘要核对**（Springer；50–100 topics / 功效设计需历史矩阵） | 未引具体样本量表 |
| PathSim 2011 | **全文核对**（PVLDB PDF） | nDCG/NMI 数字来自 Table 5/6 |
| metapath2vec 2017 | **摘要核对**（OpenAlex）；PDF 403 | 任务类型来自摘要 |
| Paulheim 2017 | **全文核对**（预印本 PDF） | "ablation 未列为标准方法"为全文检索结论 |
| Artstein & Poesio 2008 | **全文核对**（ACL Anthology PDF） | κ/α/Fleiss、CI、阈值转述均来自原文 |
| Krippendorff 2011 | **全文核对**（UPenn PDF） | "any number of observers / small samples" 来自原文 |
| Landis & Koch 1977 | **benchmark 数字经 ERIC 开放论文原文核对** | 原始论文付费；未直接读原文 |
| Hayes & Krippendorff 2007 | **仅书目核对**（DOI） | 未取全文；α bootstrap CI 由 Artstein & Poesio 转述 |

*（本文档仅 G1 的 A 源核实，不写 G2–G6，不含设计提案；未修改代码，未 commit。）*
