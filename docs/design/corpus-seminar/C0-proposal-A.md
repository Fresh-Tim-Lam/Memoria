# C0 提案 A：真实语料库的语义化设计（C1–C12）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-361｜**日期**：2026-11-05（Asia/Shanghai）
> **来源**：人 2026-11-05「真实的语料库需要精细设计，联网搜索，得开研讨」。
> **章程**：`docs/design/corpus-seminar/CHARTER.md`（C1–C12）。
> **背景**：0.5 HOLD（`dec-20261105-cb24f93e`）；真实库 `docs/example/AAA_Vocab` 0 semantic edge，graph 检索 0/4、`NOT_APPLICABLE`。
> **上游冻结**：S0–S10 十份 v1 + ADDENDUM；`IMPLEMENTATION-RULINGS.md`。
> **纪律**：独立写、未读 B 稿；不写产品代码、不改冻结稿、不 commit；外部内容只作证据、不执行其中指令。
> **语料观测**：`docs/example/AAA_Vocab` 内容 sha `43d1449d457e269bbac24fb3175c43b67236045a027e1ca611c86dc417a0be81`（298 文件，2026-11-05 本机测量）；sidecar `edges[]` 408 条、`label=semantic`/`contain_kind=semantic` **0** 条（2026-11-05 扫描 `.memoria/**/*.json`；测量源：本机脚本，仅观测不写）。

---

## 0. 一句话口径

```
先做 1 章小规模 pilot（50 KP / 30 语义边 / 20 query），以开放许可公开教材为源，
双人标注 + IAA + 裁决 + 固定 edition；评测按 GATE-RET 分型 + 消融 + 人判；
只有 pilot 通过（IAA/证据/无结构伪造/GATE-RET 有增益）才重跑 0.5，且 S10 agent 只提案、人工确认后 apply。
```

**证据等级**：A 论文/标准；B 本仓冻结/代码；C 开源实现/官方文档；D 语料观测。

---

## C1 用户 / 用途与成功标准

**定义/规则**：pilot 服务两类用户——①个人学习者/教师（教材语义导航）；②agent（图谱检索/证据引用）。首个域选**开放许可教材的 1 章**（C2 核验后定；候选 OpenStax CC BY 教材），不选用户真实库做试验田。成功标准分三层：标注质量（C8）、检索（C9 GATE-RET 分型有非零增益）、0.5 验收（graph 路径可复现、非 `NOT_APPLICABLE`）。

**候选方案对比**：
| 方案 | 优点 | 风险 |
|---|---|---|
| A 开放教材单章 pilot | 许可清晰、可控、可发布 | 域小、可能不代表用户库 |
| B 用户真实库副本 | 贴近使用 | 隐私/许可/只读隔离成本高 |
| C 多源混合 | 覆盖广 | 许可/风格/IAA 复杂，pilot 不宜 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| GraphRAG | https://arxiv.org/abs/2404.16130 | 2026-11-05 | 图谱索引对全局问题有增益；需真实语料验证，不能假设 |
| BEIR | https://arxiv.org/abs/2104.08663 | 2026-11-05 | 检索需异构基准/分型，不可单指标；支持先小基准 |
| HITL survey | https://arxiv.org/abs/2108.00941 | 2026-11-05 | 人工在环提升数据/系统质量；支持 pilot+人工确认 |

**反例**：直接拿用户真实库标注；只订“好用”无量化；把 graph 检索当默认成功。
**边界**：无开放教材；单章太小；多语言；用户库不可复制。
**风险/许可**：教材许可须 C2 核验；用户库只读隔离。
**建议裁决**：采纳 A（开放教材单章 pilot）+ 三层成功标准；pilot 通过前不发布 0.5。
**待验证**：具体教材/章节；pilot 样本量是否足够统计；用户代表。
**证据等级**：A（论文）+ D（本仓 0 semantic 观测）。

---

## C2 来源 / 许可 / 引用 / 隐私

**定义/规则**：只允许 **CC BY 4.0 / CC BY-SA / CC0 / 公有领域 / 自著** 作为可发布语料；每文档记录 `source_url/license_spdx/accessed/attribution/modified`；用户库仅私有副本、不纳入发布包；PII 先脱敏/排除；引用到句/段，不整章复制。

**候选方案对比**：
| 方案 | 优点 | 风险 |
|---|---|---|
| 开放许可教材 | 可再分发、可引用 | 需逐文档核验 |
| 用户库（私有） | 真实 | 不可发布/隐私 |
| 网页抓取 | 量大 | 许可/版权/稳定性差 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| CC BY 4.0 | https://creativecommons.org/licenses/by/4.0/ | 2026-11-05 | 允许共享/改编，须署名+标注修改；作为首选许可 |
| GDPR | https://eur-lex.europa.eu/eli/reg/2016/679/oj | 2026-11-05 | PII/个人数据处理边界；用户库需最小化/隔离 |
| Datasheets | https://arxiv.org/abs/1803.09010 | 2026-11-05 | 数据集记录动机/组成/许可/用途；交付包必需 |

**反例**：用来路不明 PDF；把 CC BY-SA 当 CC BY；用户库文件进发布包；PII 写进 KP/证据。
**边界**：混合许可；翻译/改编；引用超长；多法域。
**风险/许可**：CC BY-SA 传染性；教材版本更新；引用长度。
**建议裁决**：发布包只收开放许可/自著；用户库只读私有；逐文档许可清单+NOTICE；PII 排除。
**待验证**：教材许可核验；引用长度政策；GDPR 适用性。
**证据等级**：A（CC/GDPR/论文）。

---

## C3 本体与关系 schema（对齐 S0/S10）

**定义/规则**：实体 `Document / Section / KP / Cluster`；关系只用 S0 `E_relation_min`：`contain`（`contain_kind∈{structural,semantic}`）、`reference`、`extend`；S10 `SemanticEdge` 字段（type/contain_kind/label/source/target/direction/evidence/confidence）。v1 **不新增关系类型**；SKOS 仅借 `prefLabel/altLabel/definition/broader/narrower/related` 作概念层注释，不直接作为图关系类型。`contain(structural)` 自动派生，不手标 semantic。

**候选方案对比**：
| 方案 | 优点 | 风险 |
|---|---|---|
| S0 封闭关系集 | 与冻结契约一致 | 表达力有限 |
| SKOS 全关系 | 标准成熟 | 与 S0 类型不对齐，需映射 |
| 自定义本体 | 贴合域 | 不可互操作、违反冻结 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| W3C SKOS | https://www.w3.org/TR/skos-reference/ | 2026-11-05 | 概念/标签/定义/语义关系的标准模型；用于概念层注释 |
| W3C OWL 2 | https://www.w3.org/TR/owl2-overview/ | 2026-11-05 | 本体/类/属性形式化；仅作上层，不替代 S0 |
| schema.org | https://schema.org/ | 2026-11-05 | 通用实体/属性词汇；用于文档/数据集元数据，不作图关系 |

**反例**：新增 `related` 边绕过 S0；把 SKOS broader 直接当 S0 contain；结构边标 semantic。
**边界**：跨文档/跨语言；多归属；版本演进。
**风险/许可**：SKOS/OWL 开放标准；schema.org 词汇开放。
**建议裁决**：采纳 S0 封闭关系集 + SKOS 概念注释；新增类型须 S0/S1 修订。
**待验证**：概念层映射表；SKOS 到 S0 的显示映射是否会引起歧义。
**证据等级**：A（W3C 标准）。

---

## C4 KP 定义 / 粒度 / 边界 / 嵌套

**定义/规则**：KP=可标注的语义单元，锚定单文件连续 span；粒度默认 **1 个概念/术语/公式/步骤 + 1–3 句解释**，上限 1 段；必须落在单 section；默认不重叠、不嵌套（嵌套 future）；字段按 S10：kp_id/title/alias/summary/file/range/section_ref/evidence/confidence/status；title≤120、summary≤500 字符。

**候选方案对比**：
| 方案 | 粒度 | 优点 | 风险 |
|---|---|---|---|
| A 术语级 | 词/短语 | 一致性好 | 语境不足 |
| B 段落级 | 1 段 | 语境足 | 粒度过粗、边少 |
| C 概念+短解释（建议） | 1–3 句 | 平衡 | 边界需例 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| W3C SKOS | https://www.w3.org/TR/skos-reference/ | 2026-11-05 | 概念用 label/definition/scopeNote 表达；支持标签/定义分离 |
| CoNLL-U | https://universaldependencies.org/format.html | 2026-11-05 | 标注 span/边界/元数据需显式格式；支持可复核锚点 |
| Datasheets | https://arxiv.org/abs/1803.09010 | 2026-11-05 | 数据组成/粒度需记录；支持 KP 定义文档化 |

**反例**：整章一个 KP；跨 section 切；无 anchor；summary 当正文；重叠不标 parent。
**边界**：标题/公式/代码块；无 section；多语言；同义 KP。
**风险/许可**：概念定义可能与教材原文冲突，需 scopeNote。
**建议裁决**：采纳 C（概念+短解释），单 section/不重叠；嵌套 future；边界例入手册。
**待验证**：中文教材下 1–3 句是否稳定；公式/代码 KP 规则。
**证据等级**：A（标准）+ C（格式）。

---

## C5 标注协议 / 手册 / 正负例 / 裁决

**定义/规则**：两阶段标注——先 KP span，再语义边；标注单位=section（上下文=所在段+标题）；手册含 30+ 正例、30+ 负例、20+ 边界例；歧义三级（A/B/C）由裁决人终裁；标注前培训 1 次 + 试标 20 项校准；所有字段与 C4/C6 schema 一致。

**候选方案对比**：
| 方案 | 优点 | 风险 |
|---|---|---|
| A 先 KP 后边（建议） | 边界清晰、可复核 | 两遍成本 |
| B 同时标 | 快 | 边依赖 KP 不稳定 |
| C 纯模型预标+人改 | 省力 | 引入模型偏差 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| INCEpTION | https://inception-project.github.io/ | 2026-11-05 | 多层标注/知识库链接/建议；适合 KP+边协议 |
| brat | https://brat.nlplab.org/ | 2026-11-05 | 文本 span/关系标注、standoff 输出；适合正负例与边界 |
| HITL survey | https://arxiv.org/abs/2108.00941 | 2026-11-05 | 人在环标注/校准；支持培训+裁决 |

**反例**：无手册直接标；正例无负例；歧义无终裁；模型预标未人审。
**边界**：跨段上下文；图表；多义词；标注者疲劳。
**风险/许可**：工具开源许可（INCEpTION Apache-2.0/brat MIT）；标注者隐私。
**建议裁决**：采纳两阶段 + 手册/正负/边界 + 培训/试标；裁决人固定。
**待验证**：手册长度/试标一致性；中文标点/术语边界。
**证据等级**：A（HITL）+ C（工具）。

---

## C6 语义边类型 / 方向 / 证据 span / 置信 / 负例

**定义/规则**：类型只用 S0 `contain/reference/extend`；`label=semantic`（或 contain_kind=semantic）才算 E_sem；方向默认 source→target，`both` 必须显式且有双向证据；证据需 **两端 anchor + 断言 span**（至少一端+断言源）；置信三档 high/medium/low；负例（不应建边）单列；结构/引用边不得标 semantic。
**候选方案对比**：
| 方案 | 优点 | 风险 |
|---|---|---|
| A 只用 S0 三类型（建议） | 与冻结契约一致、可机检 | 表达力有限 |
| B 引入 SKOS related 作为边 | 表达自然 | 与 S0 类型不对齐，需映射 |
| C 自定义关系 | 贴合域 | 不可互操作、违反冻结 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| TACRED | https://arxiv.org/abs/1709.10114 | 2026-11-05 | 关系标注需类型/方向/证据；支持边 schema |
| DocRED | https://arxiv.org/abs/1906.06127 | 2026-11-05 | 文档级关系+证据 span；支持跨句/双端证据 |
| SemEval-2010 Task 8 | https://aclanthology.org/S10-1002/ | 2026-11-05 | 关系分类方向/负例；支持方向与负例设计 |

**反例**：contain 手标 semantic；方向反；无证据；把共现当边；跨文档无边。
**边界**：多证据；反向边；跨语言；同义边。
**风险/许可**：论文方法仅借用，不引入其数据许可。
**建议裁决**：采纳三类型+label 门槛+direction both 显式+证据 span+置信+负例。
**待验证**：跨文档边证据充分性；both 是否产生重复边。
**证据等级**：A（论文）。

---

## C7 规模 / 采样 / dev-test 隔离 / edition / 成本

**定义/规则**：pilot = 1 章、50 KP、30 语义边、20 query；主集 = 10 章、500 KP、300 边、100 query。分层采样：章→节→概念类型→边类型；dev/test 按 **章** 隔离（test 不参与手册/阈值调参）；edition=`sha256(文件内容+标注JSONL+手册版本)`；成本 pilot 40–60 人时，主集 300–500 人时。
**候选方案对比**：
| 方案 | 规模 | 优点 | 风险 |
|---|---|---|---|
| A 1 章 pilot（建议） | 50 KP/30 边 | 成本低、可校准 | 统计功效有限 |
| B 直接主集 | 500 KP/300 边 | 一次到位 | 成本/返工高 |
| C 多域混合 | 跨教材 | 泛化 | 许可/风格/IAA 复杂 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| BEIR | https://arxiv.org/abs/2104.08663 | 2026-11-05 | 异构基准/多数据集；支持分层采样与分型评测 |
| MS MARCO | https://arxiv.org/abs/1611.09268 | 2026-11-05 | 大规模检索数据+dev/test；支持隔离与规模估计 |
| Datasheets | https://arxiv.org/abs/1803.09010 | 2026-11-05 | 数据组成/采样/用途记录；支持 edition/成本文档 |

**反例**：dev/test 同章；按 KP 随机切导致泄漏；无 edition；成本低估。
**边界**：章太少；域漂移；标注者流动；预算不足。
**风险/许可**：教材许可决定可发布规模。
**建议裁决**：采纳 pilot→主集规模、按章隔离、edition 固化；先 pilot 再扩。
**待验证**：pilot 实际成本；50 KP 是否够统计；主集章数。
**证据等级**：A（论文/标准）。

---

## C8 双人标注 / IAA / 裁决 / 抽检 / 合格线

**定义/规则**：pilot 100% 双人独立；KP 用 Cohen κ（二分类）/Fleiss κ（多人）；边用边类型+方向 agreement 与 F1；裁决人处理分歧并记录理由；10% 抽检；合格线 pilot κ≥0.67、边 F1≥0.7；目标 κ≥0.8、F1≥0.8；错误类型：无源/错锚/粒度/类型/方向/重复。
**候选方案对比**：
| 方案 | IAA | 优点 | 风险 |
|---|---|---|---|
| A 双人 100% pilot（建议） | Cohen/Fleiss | 可校准、可解释 | 成本 |
| B 单人+10%抽检 | 仅抽检 | 快 | 偏差不可估 |
| C 模型预标+人审 | 抽样 | 省力 | 模型偏差 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| Cohen κ | https://doi.org/10.1177/001316446002000104 | 2026-11-05 | 两标注者一致性；KP 二分类 |
| Fleiss κ | https://doi.org/10.1037/h0031619 | 2026-11-05 | 多标注者一致性；多人标注 |
| Krippendorff α | https://doi.org/10.1111/j.1468-2958.2004.tb00738.x | 2026-11-05 | 多值/缺失标注可靠性；边界情况 |

**反例**：只算百分比一致；不做裁决；抽检 0；低 κ 强行发布。
**边界**：类别不平衡；多标注者；边对匹配；小样本。
**风险/许可**：标注者隐私/劳动；裁决人负担。
**建议裁决**：采纳双人+IAA+裁决+10%抽检+合格线；pilot 不达标不扩。
**待验证**：κ 阈值是否适合中文教材；边 F1 计算口径。
**证据等级**：A（统计论文）。

---

## C9 评测协议（GATE-RET 分型/消融/人判）

**定义/规则**：三层——检索（recall@10/nDCG@10/MRR，按 keyword/vector/hybrid/graph 分型）、链路（focus→expand→path 正确率）、任务（答案正确/引用完整，人判 1–5）。消融：去掉 semantic 边后同 query 指标必须下降，否则边无贡献；人判矩阵（正确性×引用）；GATE-RET 每型单独 PASS/FAIL，禁止聚合掩盖。
**候选方案对比**：
| 方案 | 层级 | 优点 | 风险 |
|---|---|---|---|
| A 三层+分型+消融（建议） | 检索/链路/任务 | 可定位失败 | 评测成本 |
| B 只测检索 recall | 检索 | 快 | 掩盖链路/任务失败 |
| C 只人判 | 任务 | 贴近使用 | 不可复跑 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| BEIR | https://arxiv.org/abs/2104.08663 | 2026-11-05 | recall/nDCG 异构评测；支持分型 |
| MS MARCO | https://arxiv.org/abs/1611.09268 | 2026-11-05 | 大规模检索任务/指标；支持任务层 |
| TREC | https://trec.nist.gov/ | 2026-11-05 | 检索评测流程/池化/人判；支持人判协议 |

**反例**：只报平均分；graph 型 0 但 hybrid 平均高；无消融；人判无 rubric。
**边界**：query 少；judge 偏差；图路径错误但答案对；无 semantic。
**风险/许可**：人判成本；评测 query 泄漏。
**建议裁决**：采纳三层+分型+消融+人判矩阵；GATE-RET 逐型 gate。
**待验证**：query 数量/统计功效；人判一致性。
**证据等级**：A（论文/标准）。

---

## C10 工具 / 导入导出 / 校验 / 版本 / 审计（只读用户库）

**定义/规则**：标注在**隔离副本**进行，工具只读用户库；格式优先 JSONL（KP/边）+ 原文字符偏移 anchor；导出校验 schema/证据锚/许可/重复；版本=edition+git tag；审计记录标注者/时间/变更/裁决；不写用户 `.memoria/sidecars`。
**候选方案对比**：
| 方案 | 工具 | 优点 | 风险 |
|---|---|---|---|
| A INCEpTION（建议候选） | 多层/知识库/导出 | 成熟、支持多人 | 部署成本 |
| B brat | span/关系/standoff | 轻量、格式清晰 | 大项目支持弱 |
| C 自建表格+脚本 | 自定义 | 灵活 | 校验/协作成本 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| INCEpTION | https://inception-project.github.io/ | 2026-11-05 | 多层标注/导入导出/项目管理；候选工具 |
| brat | https://brat.nlplab.org/ | 2026-11-05 | span/关系 standoff；导入导出格式 |
| CoNLL-U | https://universaldependencies.org/format.html | 2026-11-05 | 文本+锚点+元数据格式；校验参考 |
| Croissant | https://docs.mlcommons.org/croissant/docs/croissant-spec.html | 2026-11-05 | 数据集元数据/版本/校验和；交付包格式 |

**反例**：直接写用户库；无 anchor；导出无 schema；无审计；手工改 golden。
**边界**：大文件；中文偏移；多人并发；工具锁定。
**风险/许可**：工具许可（INCEpTION Apache-2.0、brat MIT）；用户数据隔离。
**建议裁决**：采纳隔离副本+JSONL/standoff+校验+审计；不写用户 sidecar。
**待验证**：中文 UTF-8 offset 一致性；工具选择。
**证据等级**：C（官方文档/开源）+ A（标准）。

---

## C11 与 S10 / 0.5 衔接

**定义/规则**：S10 agent 只产 `propose_write`（KP/边/curation+evidence），**人工确认**后由产品 curation writer apply；`curated_by/curated_at`；写后 edition 变化→S9 失效/重建；0.5 重跑门槛：pilot IAA 达标 + Q-EVIDENCE=100% + Q-SEM-PURITY=1.0 + GATE-RET graph/hybrid 非零增益 + 无 sidecar/正文写 + 复跑确定性。
**候选方案对比**：
| 方案 | 写路径 | 优点 | 风险 |
|---|---|---|---|
| A agent 提案+人工确认后产品 writer apply（建议） | propose→approval→apply | 与 S10/D-3 一致 | 人工成本 |
| B agent 直接写 | 自动 | 快 | 违反只读/D-3 |
| C 纯人工标注 | 人工 | 可控 | 不可扩展 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| HITL survey | https://arxiv.org/abs/2108.00941 | 2026-11-05 | 人工确认/反馈回路；支持 agent 提案+人审 |
| GraphRAG | https://arxiv.org/abs/2404.16130 | 2026-11-05 | 图谱构建/检索增益需评测；支持 0.5 重跑门槛 |
| Datasheets | https://arxiv.org/abs/1803.09010 | 2026-11-05 | 版本/用途/维护记录；支持 edition 与交付 |

**反例**：agent 自动 apply；写后不失效；pilot 不达标重跑 0.5；用结构边凑增益。
**边界**：部分写；回滚；多 KB；edition 冲突。
**风险/许可**：人工确认成本；工具误写。
**建议裁决**：采纳 propose-only/人工确认/edition 失效/重跑门槛。
**待验证**：pilot 增益阈值；确认 UI 流程；S10 写路径接口。
**证据等级**：A（论文）+ B（S10）。

---

## C12 交付包 / 维护 / 更新 / 废弃

**定义/规则**：交付包=语料快照（sha）+ golden（dev/test）+ 标注手册 + 许可清单/NOTICE + 数据卡（Datasheet/Croissant）+ 评测脚本/命令 + 变更日志；维护责任人/节奏（每学期或每 edition）；更新=新 edition、旧版保留；废弃=标 deprecated、保留只读、不删历史；避免一次性 demo。
**候选方案对比**：
| 方案 | 交付 | 优点 | 风险 |
|---|---|---|---|
| A 数据卡+快照+脚本+手册（建议） | Datasheet/Croissant | 可交接/可复跑 | 维护成本 |
| B 只交 golden | 最小 | 快 | 不可复现/不可维护 |
| C 一次性 demo | 演示 | 短期 | 不可持续 |

**外部证据**：
| 证据 | URL | 访问日期 | 映射 |
|---|---|---|---|
| Datasheets | https://arxiv.org/abs/1803.09010 | 2026-11-05 | 数据卡/维护/用途；交付包核心 |
| Croissant | https://docs.mlcommons.org/croissant/docs/croissant-spec.html | 2026-11-05 | 数据集元数据/版本/sha；交付格式 |
| DVC | https://dvc.org/doc | 2026-11-05 | 数据版本/可复现流水线；维护/回滚参考 |

**反例**：只交 golden 不交许可/手册；无版本；删旧版；无维护人。
**边界**：教材更新；标注者离开；多版本并存；存储成本。
**风险/许可**：再分发许可；长期存储。
**建议裁决**：采纳交付包清单+数据卡+edition/维护/废弃策略。
**待验证**：维护责任人；存储/成本；废弃通知机制。
**证据等级**：A（论文/标准）+ C（工具）。

---

## 总建议与待验证

1. **先 pilot 后扩**：1 章/50 KP/30 边/20 query，IAA 与 GATE-RET 通过再进主集；0.5 不提前发布。
2. **许可先审**：只发布开放许可/自著；用户库私有只读；PII 排除。
3. **本体封闭**：只用 S0 关系类型；SKOS 仅概念注释；新增类型走冻结修订。
4. **评测分型**：GATE-RET 逐型 PASS/FAIL + 消融 + 人判；禁止聚合掩盖。
5. **S10 只提案**：人工确认后 apply；写后 S9 失效/重建；0.5 重跑门槛明确。

**最可能争议**：①pilot 域/教材选择（开放教材 vs 用户库）；②KP 粒度（术语级 vs 概念+短解释）；③语义边是否允许 `both`/跨文档；④IAA 阈值 κ=0.67/0.8；⑤0.5 重跑门槛的增益阈值；⑥是否引入 SKOS 作为第二本体。

---

## 外部证据来源清单（全部访问日期 2026-11-05）

1. BEIR — https://arxiv.org/abs/2104.08663
2. Datasheets for Datasets — https://arxiv.org/abs/1803.09010
3. W3C SKOS — https://www.w3.org/TR/skos-reference/
4. CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
5. GDPR — https://eur-lex.europa.eu/eli/reg/2016/679/oj
6. GraphRAG — https://arxiv.org/abs/2404.16130
7. HITL survey — https://arxiv.org/abs/2108.00941
8. INCEpTION — https://inception-project.github.io/
9. brat — https://brat.nlplab.org/
10. CoNLL-U — https://universaldependencies.org/format.html
11. Croissant — https://docs.mlcommons.org/croissant/docs/croissant-spec.html
12. MS MARCO — https://arxiv.org/abs/1611.09268
13. DocRED — https://arxiv.org/abs/1906.06127
14. TACRED — https://arxiv.org/abs/1709.10114
15. SemEval-2010 Task 8 — https://aclanthology.org/S10-1002/
16. Cohen κ — https://doi.org/10.1177/001316446002000104
17. Fleiss κ — https://doi.org/10.1037/h0031619
18. Krippendorff α — https://doi.org/10.1111/j.1468-2958.2004.tb00738.x
19. DVC — https://dvc.org/doc
20. W3C OWL 2 — https://www.w3.org/TR/owl2-overview/
21. schema.org — https://schema.org/
22. TREC — https://trec.nist.gov/

> 本仓证据：`CHARTER.md:5`（真实库 0 semantic 背景）；`docs/design/multilevel-graph/S0-terms-v1.md:35-41`（E_relation_min）；`S10-kp-proposal-A-v2`（KP/边 schema）；`S9-retrieval-proposal-A-v2`（GATE-RET/检索）；`S8-metrics-v1.md`（G0/G7/阈值）；语料观测 sha `43d1449d…`（298 文件，2026-11-05）。
