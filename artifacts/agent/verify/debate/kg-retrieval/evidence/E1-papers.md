# E1-A 源取证：索引单元 / 层次索引 / 身份稳定性

> 角色：论文取证员（A 源）。只做 E1，不写设计提案、不 commit。
> 取证日：2026-10-27（Asia/Shanghai）。
> 方法：`web_search` 定位 → 直接抓取一手页面（arXiv HTML、ACL Anthology、PLOS、W3C、Berkeley EECS、dblp），本地抽文本后逐条核对数字。未使用二手博客/宣传文作为数字来源。
> 硬约束：每条给 URL + 年份 + 解决什么问题 + 实验条件 + 代价 + 适用边界 + **反驳条件**；查不到的写"未找到公开数据"。所有数字均来自抓取到的一手页面，未做外推。

---

## 0. 先行结论（只陈述证据状态，不代替设计裁决）

| 子问题 | A 源证据状态 | 一句话 |
|---|---|---|
| ① fixed vs semantic 切分 | **中—强**：1 篇同行评审系统评测（Findings of NAACL 2025）+ 1 篇工业预印本（late chunking） | 现有最好证据**不支持**"语义切分带来稳定收益"；但该评测本身有明确边界，且**没有量化成本**，不能当作"成本收益已算清"的证据 |
| ① 结构感知切分 | **弱**：1 篇单领域预印本（FinanceBench）+ 1 篇 2026 单作者 arXiv（可信度低，不计入判断） | 只有"金融报告 + 自带版面模型"这一窄条件下的正结果，**不足以推广到通用知识库** |
| ① 更细检索单元（proposition） | **中**：1 篇 EMNLP 2024 主会 | 在**同一 token 预算**下，更细且自包含的单元能提高召回与 QA；代价是索引膨胀约 6.3 倍 + 需要 propositionizer |
| ② 层次索引 | **RAPTOR 中（ICLR 2024）/ GraphRAG 中（预印本）** | 两者都有正结果，但**代价与适用面都被原论文自己限死**：RAPTOR 只针对长文档 QA；GraphRAG 只针对"全局综述型问题"，且对局部事实问答反而更差 |
| ③ 稳定 ID 与内容漂移 | **直接研究：未找到公开数据**；相邻领域（数字图书馆/引用持久化）证据**强** | 有成熟研究证明"链接失效 + 内容漂移"是常态；也有两类互斥的 ID 方案（注册型 DOI vs 内容哈希型 Trusty URI），但**没有** RAG/知识点索引的场景内评测 |

---

## 1. ① chunk 粒度

### A1-1｜语义切分 vs 固定切分：成本收益的系统评测

- **来源**：[Is Semantic Chunking Worth the Computational Cost?](https://aclanthology.org/2025.findings-naacl.114/)（ACL Anthology，Findings of NAACL 2025，pp. 2155–2177，DOI 10.18653/v1/2025.findings-naacl.114；预印本 [arXiv:2410.13070](https://arxiv.org/abs/2410.13070)，2024-10-16）
- **年份**：2024（arXiv）/ 2025（NAACL Findings）
- **解决什么问题**：业界普遍假设"语义切分优于固定切分"，但缺少系统证据。论文用三个代理任务检验该假设。
- **实验条件**（逐项核对原文）：
  - 三种 chunker：Fixed-size（按句数切、带重叠）、Breakpoint-based Semantic（相邻句语义距离超阈值即断，4 个相对阈值 + 2 个绝对阈值）、Clustering-based Semantic（句向量聚类，作者自提位置+语义混合距离）。
  - 文档检索：10 个数据集；其中 6 个 BEIR 子集因原文太短被**人工拼接**成"长文档"（平均约 100 句，主题多样性被人为拉高）；每个数据集随机抽 100 query，取 top-k chunk，映射回源文档，指标 **F1@5**。
  - 证据检索：RAGBench 的 5 个数据集（ExpertQA / DelucionQA / TechQA / ConditionalQA / Qasper），统计 top-k chunk 覆盖的 ground-truth 证据句。
  - 答案生成：gpt-4o-mini；top-5 chunk 作上下文；BERTScore。
  - 统一使用 `dunzhang/stella_en_1.5B_v5` 作为 embedder；所有文档先经 spaCy 分句；每个 chunker 取各自最优超参后比较。
- **结果（数字）**：
  - 文档检索（Table 1，F1@5）：**非拼接的真实文档上固定切分更好**——HotpotQA 90.59 vs 87.37（Breakpoint）/84.79（Clustering）；MSMARCO 93.58 vs 92.23/93.18；ConditionalQA 68.11 vs 64.44/65.94；Qasper 90.99 vs 89.27/90.77。**拼接数据集上 Breakpoint 语义切分明显更好**——Miracl* 81.89 vs 69.45；NQ* 63.93 vs 43.79。
  - 证据检索（Table 2）：Fixed 在 5 个数据集中 3 个最好，但差距很小（如 ExpertQA 47.11 vs 47.08/46.87；DelucionQA 43.05 vs 43.24/43.36；ConditionalQA 18.23 vs 19.83/19.14）。
  - 答案生成（Table 3，BERTScore）：差异 ≤0.01（ConditionalQA 0.42 vs 0.43/0.43；Qasper 0.49 vs 0.49/0.50）。
  - 作者归因：top-k 检索到的证据句在不同 chunker 下高度重合；**embedding 模型质量的影响大于 chunk 策略**。
- **代价**：
  - 语义切分需要"逐句 embedding + 聚类/阈值扫描"，固定切分只需对最终 chunk 做 embedding；但**论文没有给出任何量化的成本数字**（无 token 数、无延迟、无 $；全文对 cost 的表述均是定性断言）。
  - 论文本身承认：无法直接测 chunk 级质量（缺 chunk 级 ground truth），只能用文档级/证据句级代理指标。
- **适用边界**：
  - 只测了**句子级**切分；作者明确说 embedding 本身仍是 context-free 的，"需要先探索 contextual embedding 才能对语义切分下定论"。
  - 拼接数据集是合成的、主题多样性被人为放大，正结果主要出现在这类数据上；真实文档上固定切分不差。
  - 英文、开放域 QA/检索任务；未覆盖中文教材/讲义、公式/图表密集文档、代码文档。
- **反驳条件（何时该结论不适用）**：
  1. 文档内部主题高度混杂（接近论文的 stitched 条件）时，Breakpoint 语义切分在文档检索上可大幅领先（+12.4 F1）。
  2. 使用 contextual embedding / late chunking 后，固定切分的"上下文丢失"劣势可能缩小，结论可能翻转（作者本人列为未完成项）。
  3. 任务指标换成端到端答案正确率、且生成模型对噪声敏感时，代理指标（F1@5/BERTScore）可能低估 chunk 边界的影响。
  4. 成本结构不同（例如 embedding 免费/本地、聚类成本可忽略）时，"成本不抵收益"的前提不成立。
- **证据强度**：**中—强**（同行评审、10+5 数据集、多种子/超参搜索；但仅句子级、成本未量化、真实文档结论与合成文档结论相反）。

### A1-2｜Late chunking：先编码全文、后切分池化

- **来源**：[Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models](https://arxiv.org/abs/2409.04701)（arXiv:2409.04701v3，2024-09 首发 / 2025-07 修订；Jina AI + Weaviate；**未见同行评审记录**）
- **年份**：2024
- **解决什么问题**：先切 chunk 再各自 embedding，会丢失跨 chunk 上下文。Late chunking 先用长上下文 embedding 模型编码全文 token，再对 chunk 对应 token 段做 mean pooling，使 chunk 向量携带全文上下文。
- **实验条件**：
  - 4 个 BEIR 数据集：SciFact / NFCorpus / FiQA / TRECCOVID；指标 nDCG@10。
  - 3 个 embedding 模型：jina-embeddings-v2-small、jina-embeddings-v3、nomic-embed-text-v1。
  - 3 种边界：固定 256 token、5 句、语义句边界；naive（先切后编码）vs late（先编码后切）。
  - 另有 LongEmbed 长文档实验（>8192 token 用 macro-chunk + overlap 的 long late chunking；chunk size 128/512；截断 8192）。
- **结果（数字）**：
  - 跨 3 模型 × 4 数据集平均：句边界 naive→late **+3.63% 相对（+1.9% 绝对）**；固定 256-token 边界 **+3.46% 相对（+1.8% 绝对）**；语义句边界 **+2.70% 相对（+1.5% 绝对）**。
  - 平均 nDCG@10：固定边界 52.2 → 54.0（jina-v2-small 的 NFCorpus 23.5→30.0 是最大单项提升）。
  - 长文档：chunk size 越小，late chunking 相对收益越大；chunking（512 token）相对不切分平均 +24.47% 相对。
- **代价**：
  - 需要**长上下文 embedding 模型**（jina-v2 支持 8192 token）；一次编码全文，显存/内存随 token 数增长（作者明说"memory required for encoding increases exponentially"，故需 macro-chunk + overlap）。
  - 不改变切分边界本身：仍需外部分句/边界线索，只是把"上下文"注入 embedding；因此**不解决 chunk 粒度选择，也不解决 chunk 身份问题**。
  - 基础方法无需训练；但作者另提了 span-pooling 微调（需 FEVER/TriviaQA 约 470k 对）。
- **适用边界**：
  - 文档需能被长上下文模型覆盖（或截断 + macro-chunk）；短文档无收益空间。
  - 只对 dense 向量检索有效；对 BM25/稀疏检索无直接作用。
  - 四个 BEIR 数据集偏"短文档/句级证据"场景；作者自述因算力限制只选了小数据集。
- **反驳条件**：
  1. 若索引/检索管线不是 dense embedding（纯 BM25、纯图检索），该方法不适用。
  2. 若文档长度远超模型上下文且截断严重，收益可能被截断损失抵消（论文中截断 8192 的实验即为此边界）。
  3. 若已采用"chunk 前拼接标题/上下文"等更便宜的方案（A1-5 的 title-chain / contextual retrieval），late chunking 的边际收益未与该方案对比。
- **证据强度**：**中**（多数据集 × 多模型、数字完整、可复现代码；但工业预印本、未同行评审、数据集偏小）。

### A1-3｜更细的检索单元（proposition）在等 token 预算下更好

- **来源**：[Dense X Retrieval: What Retrieval Granularity Should We Use?](https://arxiv.org/abs/2312.06648)（arXiv:2312.06648v3，2023-12 首发 / 2024-10 修订；**EMNLP 2024 Main Conference**）
- **年份**：2023 / 2024
- **解决什么问题**：索引单元（document / passage / sentence / proposition）的选择对检索与下游 QA 的影响被长期忽视。论文定义 proposition = 原子、自包含的事实陈述，并构建 FactoidWiki 做对照。
- **实验条件**：
  - 语料：英文 Wikipedia 600 万页 → 4,100 万 passage（100 词）、1.14 亿句、2.57 亿 proposition（**约 passage 的 6.3 倍**）。
  - proposition 由 GPT-4 种子（4.2 万 passage）+ 微调的 Propositionizer 生成（F1 0.822）。
  - 5 个 QA 数据集（NQ / TriviaQA / WebQ / SQuAD / EntityQuestions）；4 个 dense retriever（SimCSE、Contriever、DPR、GTR）；指标 Passage Recall@5/20，以及等 token 预算下的 EM@100/EM@500（FiD/LLaMA-2-7B）。
- **结果（数字）**：
  - 跨 5 数据集平均 Recall@20：无监督 retriever 上 proposition 比 passage **+10.1 点**（SimCSE 49.1→61.7；Contriever 62.8→70.5）；有监督 retriever **+2.7 点**（DPR 69.5→72.2；GTR 76.6→79.2）。
  - 等 token 预算的 EM@500：proposition 比 passage 提升 +4.1（SimCSE）、+3.2（Contriever）、+2.7（DPR）、+2.8（GTR）。
  - 优势主要来自长尾实体问题（EntityQuestions 上 DPR 的 Recall@5 相对 +25%）。
- **代价**：
  - 索引规模 **6.3 倍**（2.57 亿 vs 4,100 万向量），需要 sub-linear 索引才可实用（作者论证可行但未给本仓规模的成本）。
  - 需要先跑 propositionizer（微调模型；GPT-4 种子数据）；proposition 质量有损：不忠实 0.7–1.3%、不可再分 2.0–2.9%、非自包含 3.1–4.9%（人评 50 passage）。
  - **多跳问题失败**：没有单条 proposition 同时包含多跳所需的两个事实（作者给的反例）。
- **适用边界**：
  - 仅 Wikipedia；仅开放域事实型 QA；英文。
  - 评测的是"检索单元类型"，不是 token 长度意义上的 chunk size；不等价于"chunk 越小越好"。
- **反驳条件**：
  1. 若问题需要跨段/多跳整合，proposition 粒度会拆散证据链（作者自证）。
  2. 若无法承担 proposition 生成与 6.3 倍索引成本，收益不可得。
  3. 若业务问题以"整段理解/综述"为主（而非事实定位），passage 级上下文可能更合适。
- **证据强度**：**中**（同行评审、5 数据集 × 4 retriever、等预算对照严谨；但单语料、单语言、依赖生成式 propositionizer）。

### A1-4｜长单元（4K token）与长上下文 reader 的配对

- **来源**：[LongRAG: Enhancing Retrieval-Augmented Generation with Long-context LLMs](https://arxiv.org/abs/2406.15319)（arXiv:2406.15319v3，2024-06 首发 / 2024-09 修订；Technical Report，**未见同行评审记录**）
- **年份**：2024
- **解决什么问题**：传统 RAG 的检索单元很短（约 100 词 passage），retriever 负担重、reader 用不上长上下文。论文把 Wikipedia 按相关文档分组为 4K-token 单元，减少单元总数。
- **实验条件**：
  - NQ / HotpotQA（Wikipedia，4K-token 单元，top<8 单元）；Qasper / MultiFieldQA-en（整篇文档作为单元）。
  - 无训练；长上下文 reader；指标 EM / F1。
- **结果（数字）**：NQ EM 62.7%、HotpotQA EM 64.3%（"与全训练 SoTA 相当"）；Qasper F1 25.9%、MultiFieldQA-en F1 57.5%。
- **代价**：需要长上下文 LLM 作为 reader；单元变大后每个单元噪声更多，依赖 reader 的定位能力；retriever 的 top-k 很小（<8），检索容错降低。
- **适用边界**：Wikipedia 事实型 QA；有强长上下文 reader；语料可预先按主题分组。
- **反驳条件**：reader 上下文窗口小/贵；语料无法做相关文档分组；问题需要精确引用短证据（长单元会稀释）。
- **证据强度**：**弱—中**（技术报告、非同行评审；但数字完整、设置清楚）。**本条目只用于说明"单元大小与 reader 能力是耦合的"，不单独作为 chunk 策略依据。**

### A1-5｜结构感知切分：金融报告 + 版面模型（领域预印本）

- **来源**：[Financial Report Chunking for Effective Retrieval Augmented Generation](https://arxiv.org/abs/2402.05131)（arXiv:2402.05131v3，2024-02/03；Unstructured Technologies；**未见同行评审记录**）
- **年份**：2024
- **解决什么问题**：按段落/固定 token 切分忽略了文档结构（标题、表格）。论文按文档理解模型标注的 element 类型切分（标题起新 chunk、表格整表保留、短元素合并），并比较多种 baseline。
- **实验条件**：
  - FinanceBench：150 题（作者只找回 80 份文档 → 141 题）；84 份 unique 报告；平均文档 102,444 token。
  - baseline：Base 128 / 256 / 512 token；结构法：Chipper（版面模型）element 切分 + 3 种元数据增强（GPT-4 关键词 / 摘要 / 前缀+表格描述）；以及 aggregation。
  - top-10 chunk，GPT-4 生成；指标：page-level accuracy、ROUGE/BLEU、GPT-4 评判 + 人工 Q&A 准确率。
- **结果（数字）**：
  - 人工 Q&A 准确率：Base 512 48.23%、Base 256 36.88%、Base 128 35.46%；Chipper（Prefix & Table Description）53.19%、Keywords 53.19%、Summary 51.77%。
  - Page accuracy：Base 512 68.09%、Base 256 73.05%、Base 128 72.34%；Chipper Aggregation 84.40%。
  - 效率：Chipper Aggregation 62,529 chunks，Base Aggregation 112,155 chunks（约一半）。
- **代价**：
  - 依赖自带的文档理解模型（Chipper）做版面/元素识别；元数据增强还要额外 GPT-4 调用（关键词/摘要/前缀）。
  - 单领域（金融 10-K/年报）、单数据集（141 题）；指标混合了 page-level 与人工判断；"element 单独使用"在 Keywords 配置下 page accuracy 仅 46.10%，说明**正结果主要来自"结构切分 + 元数据增强"的组合，而非结构本身**。
- **适用边界**：有可靠版面解析的 PDF/报告类文档；领域结构稳定（标题/表格语义明确）。
- **反驳条件**：
  1. 无版面模型或文档是纯 Markdown/纯文本时，"结构"退化为标题层级，收益未验证。
  2. 通用知识库/教材场景未测；不能把金融报告结论直接外推。
  3. 若不能承担额外 LLM 元数据调用，结构法只剩 element 切分，收益显著缩水（见 Keywords 配置的 page accuracy）。
- **证据强度**：**弱**（单领域、单数据集、工业预印本、未同行评审、正结果依赖组合管线）。

### A1-6｜结构感知的另一条证据：**可信度不足，仅登记不计入判断**

- **来源**：[Structure-Aware Semantic Chunking with Title-Chain Prefixes: A 1600-Query Evaluation and the Measurement Trap in Text-Transform Ablations](https://arxiv.org/abs/2608.00824)（arXiv:2608.00824v1，2026-08-01，单作者）
- **它声称什么**：在单一私有 Markdown 知识库、1600 query 上，header-split + semantic merge + title-chain prefix 使 MRR@5 从 0.374 → 0.463（+23.8%），可回答子集 0.828 → 0.925（+11.7%）；并报告"去前缀后双标注者 kappa 从 0.45 崩到 0.04"。
- **为什么不把它当证据**：
  1. 单作者、8 页、arXiv only、无同行评审；全文仅约 1 万字符；
  2. 标注者是两个 LLM（DeepSeek-Pro / DeepSeek-Flash），不是人；
  3. 论文自曝上一版数字**无法从运行产物复现**并撤回；同一节里 MRR 只作为"trend"报告；
  4. 单知识库、单 embedding 模型（text-embedding-v4），作者自认不能跨模型/跨域推广。
- **可保留的方法论提示（不作为事实）**：文本变换类消融（加/去前缀、换 chunk 方案）如果用 LLM 绝对打分做标注，标注一致性可能随文本变换而崩塌——这会污染所有"结构 vs 非结构"的对比实验。该提示本身也只是一篇弱预印本的自我报告，**不能当作已证实结论**。

### ① 小结（证据强度分层）

1. **"固定切分是稳健默认值"**：有 1 篇同行评审系统评测支持（A1-1），但只覆盖句子级 chunk、英文问答/检索，且成本未量化。**可用作"不要默认上语义切分"的依据，不可用作"语义切分永远无用"的依据。**
2. **"上下文可以在不切边界的情况下注入"（late chunking）**：有中等强度证据（A1-2），但它解决的是 embedding 上下文，不是粒度或身份。
3. **"更细且自包含的单元在等 token 预算下更好"（proposition）**：有同行评审证据（A1-3），代价是索引膨胀 6.3 倍与生成式预处理；且多跳任务会输。
4. **"结构感知切分更好"**：证据最弱（A1-5 单领域预印本 + A1-6 低可信度预印本）。**在拿到本仓/多领域复现前，不应把结构感知写成已证实结论。**
5. **"有没有万能 chunk size"**：A 源没有任何一篇给出跨任务稳定的最优值；A1-1 的结论是"策略影响被 embedding 质量盖过"，A1-4 的结论是"单元大小与 reader 能力耦合"。

---

## 2. ② 层次索引

### A2-1｜RAPTOR：递归聚类 + 摘要树

- **来源**：[RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval](https://arxiv.org/abs/2401.18059)（arXiv:2401.18059v1，2024-01-31；据 dblp 记录为 **ICLR 2024**，dblp 页面被反爬拦截未直接复核，仅搜索摘要可见 `conf/iclr/SarthiATKGM24`）
- **年份**：2024
- **解决什么问题**：只检索短连续 chunk 无法回答需要跨全文整合的问题（书/长文/论文）。RAPTOR 递归地对 chunk 做 embedding→GMM 软聚类→LLM 摘要，自底向上建树；查询时用"collapsed tree"在多层节点上按余弦相似度取到 token 预算。
- **实验条件**：
  - 数据集：NarrativeQA（1,572 本书/剧本）、QASPER（5,049 题 / 1,585 篇 NLP 论文）、QuALITY（约 5,000 token 的选择题，含 HARD 子集）。
  - 语言模型：UnifiedQA、GPT-3、GPT-4；摘要用 gpt-3.5-turbo；叶子 chunk 约 100 token；检索 collapsed tree 上限 2,000 token（≈top-20 节点）。
  - 对照：SBERT / BM25 / DPR，有/无 RAPTOR；指标：QuALITY accuracy、QASPER F1、NarrativeQA ROUGE/BLEU/METEOR。
- **结果（数字）**：
  - QuALITY：RAPTOR+GPT-4 **82.6%**（test）、76.2%（HARD）；论文称此前最好 62.3%。
  - 但**受控对照**（同一 reader UnifiedQA）增益小得多：SBERT 54.9→56.6、DPR 53.1→54.7（约 +1.6~1.7 点）。
  - QASPER F1：RAPTOR+GPT-4 55.7 vs CoLT5 XL 53.9；受控对照中 RAPTOR 53.1/55.7/36.6（GPT-3/GPT-4/UnifiedQA）。
  - NarrativeQA：SBERT+ROUGE 29.26→30.87、METEOR 18.15→19.20。
- **代价**：
  - 建树成本随文档长度**线性**增长（token 与时间都线性）；测试范围 12,500–78,000 token 文档，在 Apple M1 16GB 上跑；**论文正文没有给出绝对 $/token 数字**（只有图）。
  - 摘要压缩率 72%（平均摘要 131 token / 平均子节点 85.6 token）；摘要用 gpt-3.5-turbo。
  - 摘要幻觉：抽 150 个节点，**4%（6 个）含幻觉**（添加训练知识/错误外推）；论文认为"不是主要担忧"，但该结论来自小样本人工标注。
- **适用边界**：长文档、需要主题级/跨段整合的问题；有预算对每个文档做多次 LLM 摘要；摘要模型质量可控。
- **反驳条件**：
  1. 查询是局部事实/精确字符串匹配时，层级摘要帮助有限，甚至引入摘要噪声（4% 幻觉率会污染父节点）。
  2. 语料是大量短文档时，建树开销换不到跨文档整合收益。
  3. 若 headline 数字（82.6%）被误读为"RAPTOR 单独贡献 +20 点"——错：该数字混合了 GPT-4 reader；受控对照只有约 +1.6 点。
  4. 若摘要模型换成弱模型或成本受限，树的质量与收益未验证。
- **证据强度**：**中**（ICLR 2024、多数据集、受控对照完整；但 build 成本只有相对线性结论、幻觉率样本小、headline 易误读）。

### A2-2｜GraphRAG：实体图 + 社区摘要 + map-reduce

- **来源**：[From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130)（arXiv:2404.16130v2，2024-04 首发 / 2025-02 修订；Microsoft Research；**未见同行评审记录**）
- **年份**：2024
- **解决什么问题**：向量 RAG 回答不了"整个语料的主旨/趋势"这类全局综述问题（QFS）。GraphRAG 用 LLM 抽实体/关系/claims 建图 → Leiden 层次社区检测 → 预生成社区摘要 → 查询时 map-reduce 汇总。
- **实验条件**：
  - 2 个约百万 token 级语料：Podcast transcripts（1,669 个 600-token chunk，约 1M token，100 token overlap）；News articles（MultiHop-RAG，3,197 chunk，约 1.7M token）。
  - 6 个条件：GraphRAG 四个社区层级 C0–C3、纯文本 map-reduce 摘要 TS、向量 RAG SS。
  - 125 个 LLM 生成的全局问题/数据集；LLM 成对评判 4 个指标（comprehensiveness / diversity / empowerment / directness）；每对重复 5 次；另用 claim-based 指标复核。
- **结果（数字）**：
  - 索引：Podcast 建图 **281 分钟**（16GB RAM、Xeon 8171M、gpt-4-turbo 公网端点 2M TPM/10k RPM）；图规模 8,564 节点 / 20,691 边（Podcast），15,754 节点 / 19,520 边（News）。
  - 相对向量 RAG：comprehensiveness 胜率 72–83%（Podcast）/72–80%（News），diversity 75–82%/62–71%（p<.001 或 p<.01）。
  - **directness：向量 RAG 全面更好**；empowerment 混合/多数不占优（C0 明显更差）。
  - **GraphRAG vs TS（纯文本全局摘要）**：comprehensiveness/diversity 多数成对比较**无统计显著差异**；只有中间层社区摘要有小胜（Podcast C1 57%，News C3 64% comprehensiveness）。
  - 查询 token：C0 根层社区摘要 26,657 token vs TS 1,014,611 token（**少 97%+；论文称根层比其它全局方法少 9x–43x**）。
- **代价**：
  - 索引成本高：281 分钟 / 1M token（且这是 Podcast；News 未给时间）；需要 GPT-4 级模型做实体/关系/claims 抽取；建图 + 社区摘要都是 LLM 调用。
  - 检索不是"局部事实查找"：GraphRAG 牺牲 directness；对具体实体/引用的精确定位不如向量 RAG。
- **适用边界**：全局综述/主题发现类问题；语料在百万 token 级；可接受一次性高索引成本、多次全局查询摊薄；有 GPT-4 级抽取预算。
- **反驳条件**：
  1. 问题是局部事实/实体查询 → 向量 RAG 更直接，GraphRAG 的 directness 劣势会伤害体验。
  2. 语料小、全局查询少 → 281 分钟级索引成本摊不薄。
  3. 若只需要"全局摘要"，TS（纯 map-reduce 文本摘要）在统计上与 GraphRAG 多数无差异——**图的增量价值未被证明**（这是原论文自己的数据）。
  4. LLM-judge 指标 + 2 个语料，外推到其它领域未验证（论文 Limitations 自认）。
- **证据强度**：**中**（方法清楚、成本数字硬、claim-based 复核；但预印本、仅 2 语料、LLM 评判、图相对纯摘要的增益不显著）。

### ② 小结

- **RAPTOR**：对"长文档 + 跨段整合"有正结果，但受控增益约 1.6 点，headline 20 点不能归因于索引；成本线性但需对每文档多次 LLM 摘要，4% 摘要幻觉。
- **GraphRAG**：对"全局综述"有正结果且查询 token 极省，但**索引一次 281 分钟/1M token**，对局部问答 directness 更差，且**相对"无图的全局文本摘要"多数无显著优势**。
- 共同边界：两者都假设"查询需要跨段/全局整合"；对"知识点级精确定位"没有证据支持。
- **A 源没有给出"层次索引 vs 平铺索引"在中小型个人知识库上的成本收益数据**；本仓规模的适用性需 B/C 源实测。

---

## 3. ③ 身份问题：稳定 ID 与内容漂移

> 直接问"RAG/知识点索引里稳定 ID 与内容漂移"：**未找到公开的实证研究**（检索了 arXiv/ACL/W3C/数字图书馆方向；见 §5 检索记录）。以下是相邻领域可用的硬证据，全部标注"类比适用"。

### A3-1｜引用持久化：链接失效与内容漂移的规模

- **来源**：[Scholarly Context Not Found: One in Five Articles Suffers from Reference Rot](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0115253)（PLOS ONE，2014-12-26，DOI 10.1371/journal.pone.0115253；Klein, Van de Sompel, Sanderson, Shankar, Balakireva, Zhou, Tobin）
- **年份**：2014
- **解决什么问题**：量化学术论文中"引用 web 资源"的 link rot（链接失效）与 content drift（内容漂移）——即"当年引用的东西，后来还能不能找回原样"。
- **实验条件**：3 个语料（arXiv / Elsevier / PMC），1997–2012 年发表；>350 万篇文章中抽取 >100 万条 web 资源引用；对每条 URI 做实时 HTTP 检查 + 检查 web archive 是否存在"时间上代表引用时刻"的快照（Memento）。
- **结果（数字）**：
  - **1/5 的 STM 文章**受 reference rot 影响（无法重访其引用的 web 上下文）；在"含 web 引用的文章"中升至 **7/10**。
  - 链接失效比例随文章年龄上升；不同语料差异明显（arXiv 最低）。
  - 大量文章同时缺"可用链接"和"时间代表性快照"；有快照但快照时间不对，也算 reference rot。
- **代价/含义**：DOI 解决了"期刊文章"的持久寻址，但**不解决 web-at-large 资源的 content drift**；Memento/存档是补丁，覆盖不全。
- **适用边界**：学术论文的外部 web 引用；2014 年数据；不直接等于"知识库内部 chunk 的 ID 漂移"。
- **反驳条件**：内部知识库若有版本控制 + 快照（git、内容寻址存储），漂移可被工程手段消除，本条的规模数字不能直接搬用；但"引用会指向已变内容"这一机制仍然成立。
- **证据强度**：**强**（同行评审、百万级样本、定义清晰；但领域是学术引用，非 RAG）。

### A3-2｜Robust hyperlinks：用"词签名"重新定位，而非用位置/内容哈希

- **来源**：[Robust Hyperlinks Cost Just Five Words Each](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2000/5442.html)（UC Berkeley EECS Technical Report UCB/CSD-00-1091，2000；Phelps & Wilensky）
- **年份**：2000
- **解决什么问题**：URL 失效（broken link）后如何找回同一文档。方案：URL 附带从文档内容计算出的极小"签名"（约 5 个词），失效时把签名提交搜索引擎重新定位。
- **实验条件/结果**：技术报告；论证极小签名足以在数百万网页中定位单个文档；签名可自动计算、成本极低、无需服务器/基础设施改造、可自动 retrofit 旧链接。
- **代价**：依赖搜索引擎仍索引该文档；签名是"内容特征"，文档大改后签名失效；不提供版本语义（无法区分"同一文档的新版本"与"不同文档"）。
- **适用边界**：文档仍可被搜索引擎检索；引用方接受"尽力找回"而非"强一致"。
- **反驳条件**：目标文档不再被索引/已删除 → 失效；文档频繁改写 → 签名漂移；需要"引用到确定版本"的审计场景 → 不满足。
- **证据强度**：**中**（经典技术报告、思路被后续引用；但 2000 年、无当代大规模复现）。

### A3-3｜Trusty URIs：内容哈希型 ID —— 可验证，但"一改就换身份"

- **来源**：[Trusty URIs: Verifiable, Immutable, and Permanent Digital Artifacts for Linked Data](https://arxiv.org/abs/1401.5775)（arXiv:1401.5775v3；ESWC 2014，Springer，DOI 10.1007/978-3-319-07443-6_27；Kuhn & Dumontier）
- **年份**：2014
- **解决什么问题**：让 web 上的数字对象可验证、不可变、永久。做法：把内容的密码学哈希值嵌入 URI；可在字节层或更抽象的 RDF 图层做规范化后哈希，使同一 RDF 图换格式仍保持同一 URI。
- **实验条件/结果**：参考实现评测：平均 <0.8 秒/文件，batch 模式 0.03 秒/文件；Java batch 模式 1 ms/文件（作者勘误注明）；对很大文件仍实用。
- **代价/关键张力**：
  - **内容一变，哈希就变 → URI 就变**。它保证"这个 URI 永远指向这份字节/RDF"，但**不能充当"跨版本稳定的逻辑身份"**。
  - 需要对内容做规范化（canonicalization）才能跨格式稳定；规范化本身有工程复杂度。
- **适用边界**：需要"可验证的不可变引用"（nanopublication、数据集快照、审计）；不适合"内容持续演化但逻辑身份不变"的对象（如持续修订的知识点）。
- **反驳条件**：对象需要跨编辑保持同一 ID → 内容哈希方案直接不适用；只需"版本内可验证" → 适用。
- **证据强度**：**强**（同行评审、规范+实现+性能数字；但领域是 Linked Data，非 RAG）。

### A3-4｜Web Annotation Data Model：锚点持久化的标准做法

- **来源**：[Web Annotation Data Model](https://www.w3.org/TR/annotation-model/)（W3C Recommendation，2017-02-23）
- **年份**：2017
- **解决什么问题**：在会变化的文档上做标注，如何描述"我标的是哪一段"。规范给出多种 Selector：
  - `TextQuoteSelector`：exact（引用文本）+ prefix + suffix（前后文），用于区分重复文本；若仍多处匹配，规范要求**视为匹配全部**。
  - `TextPositionSelector`：字符起止位置（文档一改就失效）。
  - `FragmentSelector`（如 PDF 页/媒体片段）、`RangeSelector`、`refinedBy` 链式细化。
  - `TimeState` / `HttpRequestState`：结合 Memento 取"当时版本"。
- **代价/边界**：这是**规范**，不是实证研究；规范本身没有给出"重锚定成功率"数据。引用文本被改写、前后文被编辑、重复文本歧义时，锚点会失配或过匹配。实现质量差异大。
- **反驳条件**：目标文本被大改/重排 → quote 锚点失效；需要"精确到版本" → 必须配合 TimeState/Memento；`TextPositionSelector` 单独使用在编辑后不可靠。
- **证据强度**：**仅标准参考**（W3C Rec；不是效果证据）。价值在于：它把"稳定 ID"问题拆成"资源 ID（IRI）+ 选区（selector）+ 时间状态（Memento）"三层——**单一 ID 无法同时承担这三种语义**。

### ③ 小结（证据能支持到什么程度）

1. **"内容会漂移、链接会失效"是已被大规模证实的现象**（A3-1：1/5 文章、含 web 引用者 7/10）。
2. **ID 方案存在结构性张力**：
   - 注册型/位置型 ID（DOI、URL、字符位置）：稳定但可指向已漂移内容（A3-1、A3-4 的 TextPositionSelector）；
   - 内容哈希型 ID（Trusty URI、robust hyperlink 的签名）：可验证/可重定位，但**内容一变身份就变**（A3-3、A3-2）。
   - 标准界的折中是"资源 ID + 引用文本锚 + 时间快照"三层（A3-4）。
3. **对"知识点是否应作为稳定身份"**：A 源**没有**直接研究。能从相邻证据推出的只有约束条件：若知识点内容会持续编辑，则"内容哈希 = 知识点 ID"会违背身份稳定性；若要求引用可审计，则必须有版本/时间维度。**这属于证据约束，不是设计结论。**
4. **未找到公开数据**：
   - RAG 索引中 chunk ID 在文档编辑/移动/重命名后的解析成功率；
   - "知识点 ID"与内容漂移的实证评测；
   - 任何把"稳定 ID + 内容漂移"作为主变量的检索/Agent 论文。

---

## 4. 跨条目综合：A 源能回答与不能回答的

**能回答（有数字、可点开）**
- 语义切分 vs 固定切分：真实文档上固定切分不差；合成高主题多样性文档上语义切分更好；无量化成本（A1-1）。
- late chunking：+1.5~1.9 绝对 nDCG@10，需长上下文 embedder（A1-2）。
- 更细检索单元：等 token 预算下 proposition 更好，但索引 6.3 倍、多跳失败（A1-3）。
- RAPTOR：长文档 QA 正结果；受控增益约 1.6 点；4% 摘要幻觉；建树线性（A2-1）。
- GraphRAG：全局综述正结果；索引 281 分钟/1M token；directness 更差；相对无图全局摘要多数不显著（A2-2）。
- 引用持久化：1/5 文章 reference rot；内容哈希 ID 与稳定逻辑 ID 不可兼得（A3-1/3/4）。

**不能回答（取证缺口，需 B/C 源或新实验）**
1. 本仓这种规模（个人教材/讲义知识库）上，fixed vs semantic vs structure-aware 的**成本收益**：A 源没有同规模数据。
2. "知识点"作为索引身份的任何实证：没有论文把"知识点"当检索单元/ID 做对照实验。
3. chunk 稳定 ID 在编辑/移动后的**解析成功率**：无公开数据。
4. 中文、公式密集、图文混排文档的切分证据：A 源几乎全是英文 Wikipedia/学术/金融语料。
5. GraphRAG/RAPTOR 在"非全局、非长文档"场景的负结果：论文只报适合其方法的任务。

---

## 5. 检索与核对记录（可复核）

- 检索日：2026-10-27。
- 检索入口：`web_search`（关键词组合见下）+ 直接抓取。
- 直接抓取的一手页面：arXiv abs/HTML（2307.03172v3、2410.13070v1、2409.04701v3、2401.18059v1、2404.16130v2、2312.06648v3、2406.15319v3、2402.05131v3、2608.00824v1）、ACL Anthology（2025.findings-naacl.114）、PLOS ONE（10.1371/journal.pone.0115253）、W3C（annotation-model）、Berkeley EECS（UCB/CSD-00-1091）。
- 关键检索词：`semantic chunking computational cost`、`late chunking long context embedding`、`RAPTOR recursive abstractive tree retrieval`、`GraphRAG query-focused summarization`、`retrieval granularity propositions`、`reference rot scholarly context not found`、`robust hyperlinks lexical signature`、`trusty URIs content hash`、`web annotation TextQuoteSelector`、`structure-aware chunking evaluation`、`RAG chunk stable id content drift`（最后一项未找到直接研究）。
- 核对规则：
  - 所有数字从一手页面正文/表格抄录；表格若被 HTML 数学标记替换为 `[MATH]` 且无法确认数值，则该数字不引用（例如 A1-1 的成本、A1-2 的部分表值）。
  - 论文的"显著提升"必须落到指标 + 数据集 + 对照；未给对照的 headline 数字单独标注（如 RAPTOR 82.6% vs 受控 1.6 点）。
  - 预印本/会议状态逐篇标注；未能直接打开 dblp 的（RAPTOR）已注明。

---

## 6. 给 Lead 的 3–5 条最硬证据 + 不确定处

**最硬 5 条**
1. **语义切分不划算**有同行评审出处的原始论文：[Qu, Tu & Bao, Findings of NAACL 2025](https://aclanthology.org/2025.findings-naacl.114/)（= arXiv:2410.13070）。但它**只测句子级 chunk、没量化成本**，且真实文档 vs 合成拼接文档结论相反（HotpotQA 90.59 vs 87.37；Miracl* 69.45 vs 81.89）。
2. **更细单元在等 token 预算下更好**：[DenseX, EMNLP 2024](https://arxiv.org/abs/2312.06648)，Recall@20 +10.1（无监督），但索引 **6.3 倍**、多跳失败、需 propositionizer。
3. **late chunking**：[arXiv:2409.04701](https://arxiv.org/abs/2409.04701)，nDCG@10 +1.5~1.9 绝对，需 8192-token embedder；不改变边界，只改 embedding。
4. **RAPTOR 的 headline 会误导**：82.6%（RAPTOR+GPT-4）vs 受控对照只 +1.6 点；建树线性但无绝对成本；摘要 **4% 幻觉**。
5. **GraphRAG 的代价与边界是硬的**：1M token 索引 **281 分钟**；directness 输给向量 RAG；**相对无图全局摘要多数指标不显著**；只适合全局综述。
6. **身份问题**：没有 RAG 内研究；相邻领域强证据是 reference rot **1/5 文章（含 web 引用者 7/10）** + Trusty URI 的"内容哈希=一改就换 ID"张力。

**不确定处（必须在 B/C 源补齐前保持"未定"）**
- Qu et al. 的"cost not justified"是定性判断，**没有 token/延迟/$ 数字**；不能引用成"已测算成本"。
- RAPTOR 82.6% 不能拆出"层次索引"的净贡献；受控实验只有约 +1.6 点。
- GraphRAG vs TS 的多数比较**不显著**，图的增量价值未被原论文证明。
- A1-5/A1-6 结构感知证据弱；A1-6 不计入判断。
- 所有 ③ 的结论都是**类比**：数字来自学术引用/数字图书馆，不是 RAG 索引；本仓的 chunk 编辑/移动频率与引用解析率**没有数据**。

*（本文档仅为 A 源取证，不含设计提案；未修改任何代码，未 commit。）*
