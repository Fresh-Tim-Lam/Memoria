# KGR 研讨会 Phase 1 提案 — B（知识组织 / 学习视角）

> 提案方：`todo-owner`（B）｜2026-10-27｜Phase 1（严格独立）
> **读入集**（只读，未读他人 Phase 1 提案、未讨论）：`PROTOCOL.md`、`ACCOUNT-2026-10-27.md`、`docs/design/kg-ontology-v0.md`、`src/memoria/services/agent/tools/kb.py`、`src/memoria/services/agent/section_index.py`、`src/memoria/services/search_kernel.py`、`src/memoria/storage/manifest.py`、`aoci.txt` / `aoci.code.txt`、`D:\AAA_Courses\数字通信原理` 真实 sidecar 与 md、`docs/example/AAA_Vocab` sidecar；外部论文/文档仅读摘要与索引说明页（URL 见 R7）。
> **证据身份（E1）**：`ev:file:<repo-rel>#L<n>`｜`ev:bench:kg-retrieval-b-1`（脚本 `b_measure*.py` + 产物 `b-measure.json` sha256 `973E6415…`、`b-measure-kp.json` sha256 `2A5676F6…`）｜`ev:web:<url>`。
> **测量脚本可复跑**：`python artifacts/agent/verify/debate/kg-retrieval/b_measure.py` / `b_measure2.py` / `b_measure3.py`（只读语料）。

---

## 1. 结论摘要（先给答案，≤10 行）

1. **KP 不是学习单元**：实测 354 个 KP 的正文切片 **p50=526 字、p90=2,918 字、max=18,198 字**；**20.3% <200 字（碎片）**、**9.3% >3,000 字（超单元）**、4.0% >8,000 字。同一库内 284KB 的第 8 章只有 **1 个 KP（398 字）**，而 PDF 转写页的 KP 平均 600–750 字、161 个/篇。⇒ 「KP = 一次能学会的最小完整单元」**不成立**，KP 是「标题切分 + 手标范围」的混合产物。
2. **但 KP 是对的"语义标签/锚点"，不是对的"检索返回单元"**。建议：**索引单元 = 带预算的学习切片（section/heading path + ≤~1,200 字窗口）**；KP id 保留为稳定语义锚（标签、关系、复习、跳转都用它），检索按切片返回。
3. **description 现状是空/混用**：数字通信原理 **0/357** 个 KP 有 description；AAA_Vocab **25/134（18.7%）**，且现有 25 条明显混着两类用途——「给 agent 判相关」的**判别性摘要**（话题/同义替换/语域限制）与「给人学」的**记忆笔记**（词源/音近陷阱）。一个字段服务两个受众必然稀释（见 §3 R2）。
4. **description 应拆两字段**：`scope`（机器可判：本切片回答什么问题、**何时不该读**、判别关键词，≤80 字）+ `note`（人用：词源/易错/记忆法，可选）。"sufficient statistic" 的标准不是"摘要像摘要"，而是**不读正文就能做读/不读的决策**。
5. **索引不是越全越好，是要分层**：把 357 个 KP 的名字全量注入 ≈4.8k 字（3.4–4.8k tok）；再加首行 preview ≈19k 字（13–19k tok）——相当于单次工具结果上限（20,000 字）的 65–95%，也占 225k 平均 prompt 的 6–8%。⇒ **L0 概览 → L1 文件 outline → L2 候选切片 description** 三层，绝不整库注入。
6. **现成能力比想象多**：`outline/section/snippet`（S1a 三级读粒度，预算 800/4,000/600 tok）+ `read_kp` + manifest 文件级 sha 已存在（`kb.py#L73-L90`、`section_index.py#L51-L53`、`manifest.py#L59-L61`）。**R6 的答案是"接上"而不是"重造"**：agent 的 `search_kb` 目前硬编码 `modes="lexical"`（`kb.py#L248`），而 `search_kernel` 已支持 semantic / both / RRF / cross-encoder 精排（`search_kernel.py#L58-L121`）——这是现成的第一优先级。
7. **图谱进 agent 检索（PPR/HippoRAG 式）不进 v0**：本体裁决已明确「agent 侧从不读边」「图谱↔agent 两套未打通」，且**任何为 agent 加边能力的设计必须先证明能改变一个 agent 决策**（`kg-ontology-v0.md#L13,L23,L28`）。在拿到该证明前，图谱在 B 视角只做**人看的导航**，不做检索扩散。
8. **可验收的"提升"**：不是"token 变少"，而是 **同答对率下 prompt 下降 + 峰值上下文下降 + 召回不降**。若答对率降 1 题（或召回降 >5%）即否决该改动（R8）。
9. **我的核心否决**：不做「全库 KP description 自动生成 + 全量注入」——它同时踩三坑：prompt 常驻 +15–21k tok、LLM 摘要不可复核/易陈旧、人失去维护动机（已实测内容空洞/混用）。
10. **边界诚实**：我没有人类学习实验数据；"学习单元 200–1,200 字"来自教学分段原则 + 本库实测分布，是**可证伪的设计假设**，不是定论（falsifier 见 §5）。

---

## 2. R1 索引单元：KP 是否符合"学习单元"？——不符合，但别扔掉 KP

### 2.1 实测（ev:bench:kg-retrieval-b-1）

| 指标（数字通信原理，357 KP / 12 sidecar / 354 可解析切片） | 值 |
| --- | --- |
| KP 正文切片字符数 | p50 **526**；p90 2,918；p99 12,605；max 18,198 |
| 切片行数 | p50 16；p90 76；p99 322；max 393 |
| <200 字（碎片，判"学到什么"都难） | **20.3%** |
| 200–1,200 字（一次精读可完成） | 55.6% |
| 1,200–3,000 字（偏大） | 14.7% |
| >3,000 字（超单元） | **9.3%** |
| >8,000 字（一次读都贵） | 4.0% |
| KP 名称"自足"（脱离正文能判断讲什么） | 285/354 = **80.5%**；其余是「目录」「1. 直流信号」「【例】…」等碎片 |
| KP 起点落在 heading 行上 | 混合：PDF 转写 81/81、161/161、38/42；教材章节 3/21、16/21、28/28、**0/1** |

**两个反例（极端）**：
- `教材/08_第8章_差错控制编码.md`：284,714 字 / 42 个标题，却只有 **1 个 KP**（span=1 行、切片 398 字，id=`test`/「跳转测试节点」——是**测试残留**，不是知识单元）。⇒ 该章在"KP 索引"里几乎不存在。
- AAA_Vocab：**134 个 KP / 135 篇文档**，每篇 1 个 KP，KP 切片 **p50=105 行**（≈整篇）。⇒ KP = 文档，不是学习单元。

### 2.2 为什么 KP 会变成这样（机制，不是猜测）
- KP 由人/agent 手标 range + `{snippet, line_hint}`（`kb.py#L194-L231` 的 `_snippet/_line_hint`、`kp_resolver.resolve_knowledge_points`），**没有长度约束**；
- PDF 转写页把每个标题当 KP（合理，因为原文就是标题切分）；教材章节点选少量重点（于是 1 章 1 KP 或 21 KP 混合）；
- 名称直接取标题文本（`img-ch2-2-25-3-单位斜坡信号`），**不是"可学习单元命名"**。

### 2.3 我的主张（可证伪）
- **索引单元 L2 = 学习切片**：`(file, heading_path, start_line, end_line)`，目标 **200–1,200 字**（约 1–3 分钟精读）；超预算按 `section` 的既有切片机制继续切（`section_index.py#L444-L458` 已实现按预算切 + `next_cursor`）。
- **KP 降级为语义锚**：保留 id/name/tags/description/range 作为**标签与跳转锚**；复习（FSRS）、图谱、link 解析继续用 KP id（不迁移 id，避免锚点崩塌）。
- **两者关系**：一个切片可含 0–N 个 KP；一个 KP 可跨切片（长 KP 切成多片，KP 元数据只在首片标注）。这样"人维护的是 KP（语义）"，"agent 检索的是切片（预算）"，**单一事实源仍是正文+sidecar**，不新增第二套知识。
- 依据：教学分段原则（segmenting principle：学习者自定步调的分段显著优于连续大段，`ev:web:https://www.cambridge.org/core/books/abs/cambridge-handbook-of-multimedia-learning/...`）；本库实测 55.6% 落在目标区。

**若"KP 必须保持为返回单元"的反方案**：则必须给 KP **长度上限 + 拆分规则**（超限自动降级到 section），否则 9.3% 的超单元 KP 会单次把上下文打回危险区（p99 12.6k 字 ≈ 9–12k tok，多个就爆）。

---

## 3. R2 description 写什么（既让 agent 判相关，又让人愿意维护）

### 3.1 现状证据
- 数字通信原理：**0/357** KP 有 description（实测于 sidecar）；文件级 description 也 **0/12**（`kb_overview` 因此只能显示文件名，`kb.py#L391-L392`）。
- AAA_Vocab：25/134，长度 p50 49、p90 187、max 267；**用途混杂**：
  - 机器向（判别性）：「`dilapidated`：破旧的；年久失修的（建筑与街区负面描写，与 renovation 正反成对）」；
  - 人向（记忆笔记）：「`flail`——含 flagellum 词源记忆、flailed/failed 与 flail/fail/frail/flair 两组音近陷阱、Best Situation 与 Register Gate」（267 字）；
  - 混合体：「`favourable`——含核心规则「修饰条件、时机、结果，不修饰人的心情」、BrE/AmE 拼写差异…」（185 字）。
- ⇒ **一个字段确实无法同时最优服务两个受众**；这不是理论，是本库现有 25 条的真实分布。

### 3.2 主张：拆成 `scope`（机器）+ `note`（人）
```
kp.description.scope  （≤80 字，agent 读；可机械校验）
  必含：① 本切片回答的 1–2 个问题（"什么是 X / 如何算 Y / X 与 Z 的区别"）
        ② 判别关键词（同义/别名/符号，供 lexical 命中）
        ③ **何时不该读**（所属章/前提/超出范围）——这一条最能提升"不读"的决策
  禁含：泛泛的"本章讲…"；不含步骤细则（那是正文）
kp.description.note   （可选，人读；自由文本）
  词源/记忆法/易错/语域/例证线索；不参与 agent 判相关（避免污染检索）
```

### 3.3 为什么这是"sufficient statistic"
IR 里的 sufficient statistic 不是"摘要得像摘要"，而是**给定它就能做决策而不损失**（query-relevant summarization，`ev:web:https://dl.acm.org/doi/10.3115/1075218.1075256`）。对"要不要读这一片"的决策，需要的统计量是：**它是什么 + 能不能回答我的问题 + 我读它要付多少预算 + 什么情况下它不该读**。`scope` 的四要素正好覆盖，且能机检（长度/禁用词/是否含"何时不该读"）。
**对人**：`note` 承载人真正愿意写的差异化信息（词源/陷阱），并且**在 UI 里可见**（图谱 tooltip、链接小窗候选卡片、复习卡片）——人写它不只是"喂 agent"，自己也受益；这正是维持动机的关键（否则 description 会像本库 0/357 一样空掉）。

### 3.4 落地方式（不新增第二事实源）
- 写入既有 sidecar：KP 已有 `description` 字段（`document.py#L1875` `update_kp(... description=...)`），扩展为 `description: {scope, note}` 需 schema 兼容（A 方契约）；旧字符串按 `scope` 读、`note` 空。
- **生成策略**：agent 起草 `scope`（基于切片正文，≤80 字）→ **人一键确认/修改**（可批量抽查）；`note` 只由人写（或从复习错题沉淀）。
- **不做**：agent 全库静默重写 description（理由见 §4 否决方案 A）。

---

## 4. R3/R4（证据绑定与锚点；虽非 B 重点，但与我方案耦合，必须给答案）

### R3 证据绑定与失效
- **已有**：manifest 每文件 `md_sha256` / `sidecar_sha256`（`manifest.py#L59-L61`；实测 `数字通信原理/.memoria/manifest.yaml` 12 条 sidecar 条目均带）⇒ 文件级陈旧检测是 O(文件数) 的便宜操作，不需要全库分词。
- **缺**：KP/切片级绑定。建议 `scope` 绑定四元组 `(kp_id, file, range[start,end], slice_sha256)`，其中 `slice_sha256 = sha256(去 frontmatter 后该 range 的正文)`。
- **检测分级**：① 先比 manifest 文件 sha（廉价，覆盖 99% 情况）；② 文件变了再只对**被引用的候选切片**算 slice hash（O(候选数)）；③ 不一致 ⇒ 标 `stale=true`。
- **stale 期间 agent 行为**：**降级读原文切片**（section/read_kp），并在结果里标注"索引陈旧，已回原文"；**禁止**把 stale 的 scope 当事实引用（与 M1 精神一致）。

### R4 锚点稳定性
- 现状：KP range = `{start:{snippet,line_hint}, end:{snippet,line_hint}}`（`数字通信原理/.memoria/sidecars/教材/08…yaml` 实录）；`line_hint` 会随插入/删除漂移，`snippet` 可能重名。
- 主张：锚点用 **内容锚 + 结构锚 + 行号提示**：`(file, heading_path, heading_ordinal, slice_sha256)` 为稳定身份，`line_hint` 仅作提示；漂移修复 = 先按 `heading_path` 重定位、再按 `slice_sha256` 精确校验；都失败 ⇒ 标 stale + 进人工复核队列（不自动猜）。
- 这与 R3 共用同一 `slice_sha256` 字段，**不引入额外事实源**。

---

## 5. R5 检索路径与预算：分层，不注入整库索引

### 5.1 实测预算事实
- 会话基线：平均 prompt **225,553 tok/轮**、峰值 656,818（1M 的 65.7%）；费用 66.2% 是输出（`ACCOUNT…md#L21-L34`）。
- 现有工具硬上限：`read_document` ≤20,000 字（`kb.py#L66`）；`outline` ≤800 tok、`section` ≤4,000 tok、`snippet` ≤600 tok（`section_index.py#L51-L53`）。
- 索引体积（357 KP，实测）：names-only 4,824 字（3.4–4.8k tok）；加每 KP 40 字 preview 18,984 字（13.3–19k tok）。

### 5.2 主张：三层索引 + 预算分配
```
L0 库概览（≤1.5k tok）：文件列表 + 每文件 KP 数 + 文件级 description（现在为空 → 先补 12 条）
L1 文件 outline（≤800 tok）：heading 树 + 行号区间（现成 outline）
L2 候选切片（≤4,000 tok/次）：按 query 选 1–3 个候选，返回切片正文 + scope
```
- **绝不**把 357 个 KP 的名字/preview 整库注入（13–19k tok 是"索引变负担"的本例）。
- 预算红线（可机检）：索引注入 ≤ **10%** 当前 prompt（225k 时 ≈22k tok；但目标是把平均 prompt 降下来，所以按比例约束而非绝对值）；单次工具结果 ≤20k 字（现状）；**回答预留**：结果注入后剩余 ≥30% 窗口。
- 顺序：先 `search_kb`（或 R6 的融合检索）→ 候选文件 → `outline` → `section`（切片）→ 必要时 `read_document`。**现有三把工具已足够表达这条路径，缺的是"路由规则与默认用法"**（提示词/工具描述层面，不是新引擎）。
- 上下文位置：重要证据放在注入块**末尾/边缘**（Lost-in-the-Middle / Found-in-the-Middle 的位置偏差，`ev:web:https://ar5iv.labs.arxiv.org/html/2406.16008`）。

---

## 6. R6 与现有检索栈融合：接上，不重造

实测现状：
- `search_kernel.search(modes=...)` 已支持 **lexical / semantic / both(RRF) / cross-encoder 精排**（`search_kernel.py#L58-L121`）；`both` 时 lexical 与 semantic 融合（L103-L121）。
- 但 agent 的 `search_kb` **写死** `modes="lexical"`（`kb.py#L248`）⇒ **现有语义检索能力对 agent 不可见**。
- 三级粒度读（outline/section/snippet）已注册进工具面（`kb.py#L73-L90`），且 `section_index` 已实现预算切分与 C1–C5 语义。

主张：
1. **不重造**：索引层 = 现有 sidecar/manifest 上加 `scope` 与切片锚；检索层 = 现有 `search_kernel`（lexical 默认、semantic/both 可配）；返回层 = 现有 `section`/`read_kp`。
2. **第一优先（低成本、可测）**：把 agent `search_kb` 的 `modes` 暴露为可配（默认仍是 lexical，灰度 `both`），用 ACCOUNT 同一会话做 A/B：命中率、召回、prompt 变化。
3. **新增的只有一样**：`scope` 索引的读取路径（L0/L1 工具已有，补 L2 的"候选切片 scope 卡"）；**不新增向量库、不新增图谱扩散**。
4. **图谱/PPR 不进 v0**：本体已裁 agent 不读边且未证明价值（`kg-ontology-v0.md#L13,L28`）；HippoRAG 式 PPR 需要"边对 agent 有决策价值"的前置证明，当前 0 证据。

---

## 7. R7 外部参考：各自解决什么、代价、能否搬

| 参考 | 解决的问题 / 机制 | 代价 | 能否搬到 Memoria |
| --- | --- | --- | --- |
| **AOCI**（本仓 `aoci.txt`/`aoci.code.txt`；Entry 按**文件/对象**一条，四字段 F/R/A/S，模型撰写+机器校验+CAS/baseline；代码卷 39.5KB） | 给模型一个**对象级充分统计量**（职责/关系/契约/非显然约束），先读索引再决定是否读源码；索引由模型维护、可增量 | 每对象一条的维护成本；**无向量检索**（靠模型读/工具查）；索引本身可能膨胀 | **高**：证明"对象级 + 短字段 + 机器校验"可行；方法迁移到"切片级 scope"（字段更少、更短）；不搬其全量生成开销 |
| **XERJ**（`xerj_map` 先出字段图；`search/semantic/hybrid(rrf)/vector`；memory；brain 图） | 查询前先**schema 发现**；多检索器融合；明确 token 预算；索引陈旧拒绝（30 天 stale 拒答） | embedding/LLM 成本、索引新鲜度维护、语义模型的领域漂移 | **中**：借用「先 map 再查」「RRF 融合」「stale 拒绝」三条；不搬 embedding-first（本仓无稳定语义索引预算） |
| **GraphRAG**（Microsoft, arXiv 2404.16130） | 语料级实体图 + **社区层级摘要**，local/global 两类查询解决"全局总结" | 全库 LLM 索引成本巨大；抽取错误传播；更新即重算 | **低（v0）**：Memoria 的图是确定性 sidecar 派生的、人维护的；LLM 全库摘要与"单一事实源/可复核"冲突。可借"社区层级"做**人可读的目录树**（已有 outline） |
| **HippoRAG**（arXiv 2405.14831） | KG + **Personalized PageRank** 扩散做多跳检索，单步多跳 | OpenIE/实体链接成本；图质量决定上限 | **低（v0）/中（v1）**：需先证明"边对 agent 决策有价值"（本体 L28）；若做，PPR 只走**人工确认的边**并做 A/B |
| **RAPTOR**（arXiv 2401.18059） | 递归聚类 + **摘要树**，自底向上支持长文/全局 | LLM 摘要成本、幻觉、更新重算 | **中（v1）**：可做"确定性摘要树"——节点摘要由人工确认的标题/KP 名与 scope 组成，不自由生成；先解决索引新鲜度 |
| **LlamaIndex**（Index guide） | 多索引类型（vector/summary/keyword/tree/KG）+ **retriever 组合/router** | 框架耦合、额外依赖 | **只借概念**：query→索引/工具的 **router**（"是什么/在哪/为什么/怎么算"分别路由到 outline/section/kp/search）不引入框架 |

**AOCI 的一个关键教训**：它的 Entry **不是自动 chunk**，而是"受管理对象"一条、短字段、可版本化校验——这正是"索引单元要有稳定身份 + 短充分统计量"的现成证明（`ev:file:aoci.code.txt#L7-L18` 示例 Entry）。

---

## 8. R8 如何证明"真正对 agent 有提升"：预注册指标 + 证伪条件

**装置**：从 ACCOUNT 同一真实库（数字通信原理）取 **16 个真实问题**（覆盖定义/计算/对比/定位四类），每个问题人工标注**最小充分切片集合**（ground truth：文件+行区间，1–3 个）。A/B 两组：现状（read_document/lexical）vs 方案（L0→L1→L2 路由 + 融合检索）。

**指标（全部预注册，不许事后改）**：
1. **检索召回**：候选集是否覆盖 ground-truth 切片（recall@5、MRR）。
2. **单轮 prompt tokens**：平均/峰值（目标：平均 −20% 以上、峰值 < 40% 窗口）。
3. **答对率**：同一模型、同一判分（人工 rubric + LLM 辅助，双盲抽检 1/3）；**不得下降**（降 1 题即否决该改动）。
4. **成本**：按 `pricing.py` 口径复算（含输出不变项）。
5. **缓存命中率**：不得因索引注入把前缀打乱而显著下降（ACCOUNT 已 94.21%，空间只有 5.8%）。

**证伪条件（任一 ⇒ 我的方案被推翻）**：
- 答对率下降或召回下降 >5%；
- 平均 prompt 降幅 <10%（收益不成立）；
- `scope` 描述在"该不该读"的盲评中 ≤ 名字 baseline（说明 description 无用）；
- 索引维护成本 > 节省（人时折算）——**人的维护时间必须计入**，否则"省 token 但费人"不是提升。

---

## 9. 我【否决】的方案（自己曾考虑过，给理由）

### 9.1 否决 A：全库 KP description 自动生成 + 全量注入 overview
- 曾考虑：357 KP × 60 字 scope ≈ 21,420 字 ≈ 15–21k tok/轮常驻；加上缓存前缀随更新变动，命中率受损。
- 三个硬伤：① **常驻成本**（每轮 +15–21k tok，相当于把"索引"变成第二份正文）；② **不可复核**（LLM 生成的描述无法像正文一样被人校验，与 AOCI/本仓"可复核"传统冲突）；③ **动机消失**（人不会维护自动生成的长文，最终 0/357 的现状会重演）。
- 替代：L0/L1/L2 分层 + 只对候选切片取 scope（§5）。

### 9.2 否决 B：把 KP 当返回单元、给 KP 加长度上限
- 曾考虑：简单——限制 KP ≤1,200 字，超限的拆 KP。
- 否决理由：**会破坏锚点/复习/链接**（KP id 是 FSRS、link、图谱、review 的锚；批量拆 KP = 大规模迁移风险），且需要人重标 9.3% 超限 KP；收益与"用 section 切片"相同但成本高一个量级。⇒ 保留 KP 身份，返回用切片（§2.3）。

### 9.3 否决 C：embedding 替换 lexical
- 现有 `search_kernel` 已支持 RRF/cross-encoder；agent 只是**没接**。引入新向量库 = 新依赖 + 索引维护 + 与"本地离线、无外部依赖"约束冲突。⇒ 先接现有能力（§6）。

---

## 10. 我【不确定】的点（M3，不装懂）

1. **学习单元的边界**："200–1,200 字"来自分段原则 + 本库分布，**没有人类学习实验**证明这个区间的学习收益；可能因学科/题型不同而变（数学推导 vs 英语表达）。
2. **description 的 ROI**：人写 `scope` 的时间 vs agent 节省的读取成本，我没有测量；若人工成本高，应改为"agent 起草 + 人抽查"（本提案默认后者），但仍需实测。
3. **《数字通信原理》是否代表其他库**：本库 PDF 转写 + 教材混排；Obsidian 类库（AAA_Vocab 式单文件单 KP）分布完全不同——跨库泛化未测。
4. **切片 hash 的稳定性**：正文编辑（尤其 agent 写入）后 slice hash 变更率未测，可能造成大量 stale 提示；需要量。
5. **R8 的判分可靠性**：LLM 判分可能偏向"回答更长/更像教材"的组；需人工双盲校准（本提案要求 1/3 抽检，但样本小）。

---

## 11. falsifiers（什么结果会推翻我的主张）

| 主张 | 反证条件 |
| --- | --- |
| KP ≠ 学习单元（§2） | 人类标注实验显示：教师/学习者把 ≥80% 的 KP 判为"一次可学会的完整单元" ⇒ 我的论断错，应按 KP 返回 |
| 学习切片 200–1,200 字（§2.3） | A/B 显示该窗口的答对率不优于整章读取 ⇒ 分段假设不成立 |
| description 拆 scope/note（§3） | 盲评：仅名字 vs 名字+scope 的"该不该读"判断无显著差异 ⇒ description 无用，删 |
| 三层索引预算（§5） | 平均 prompt 降幅 <10%，或 L0+L1 已足够、L2 无增益 ⇒ 简化 |
| 接现有 search_kernel（§6） | `both` 模式在真实问题上召回/答对率反而下降（小库 lexical 已够）⇒ 保持 lexical，仅做切片 |
| stale 分级（§4） | slice hash 变更率 >30%/周 ⇒ 维护成本过高，改用"文件级 stale + 读时校验" |

---

## 12. 复跑与产物

```
# 测量（只读语料；产物在 artifacts/agent/verify/debate/kg-retrieval/）
python artifacts/agent/verify/debate/kg-retrieval/b_measure.py    # sha256 01EE3E81…（KP/desc/索引体积）
python artifacts/agent/verify/debate/kg-retrieval/b_measure2.py   # sha256 58C6883A…（切片字符量/文件description/三级索引）
python artifacts/agent/verify/debate/kg-retrieval/b_measure3.py   # sha256 F95EFCDB…（名称自足性/单元尺寸分布）
# 产物：b-measure.json（973E6415…）、b-measure-kp.json（2A5676F6…）
```

**一句话**：B 的答案是——**别把 KP 当学习单元，也别扔掉 KP；把它当锚点，把"带预算的切片 + 双字段 description + 分层索引"当检索单元**。这是本场唯一一个既尊重"人维护的知识组织"、又能直接压低 agent prompt 的方案。
