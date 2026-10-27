# PROPOSAL — 外部研究（Phase 1 + Phase 1.5 追加）

> 角色：外部研究专员。本文只提供**外部证据**（论文 / 开源实现 / 本机两个参照实现），不参与架构裁决。
> 独立性：Phase 1 期间未读 `PROPOSAL-agent-arch / arch-contract / corpus-analysis / metrics-baseline / todo-owner` 任何一份；仅按目录枚举看到文件名（PROTOCOL §4 F2' 允许）。
> 证据格式：`ev:file:<path>#L<n>` / `ev:doc:<url>` / `ev:data:<path>`。**外部仓库代码取自 `main` 分支 2026-10-27 抓取，行号可能随后续提交漂移**；引用时同时给 URL，可点开复核。
> 许可纪律：LlamaIndex=MIT、LightRAG=MIT、Aider=Apache-2.0、Graphiti=Apache-2.0（均逐字读到 LICENSE 头，见 E11–E14）；**未读到许可的文件一律不作代码结论**（RAGFlow/LangChain，见 §5）。

---

## 0. 结论摘要（≤12 行）

1. **值得搬（3 件）**：① LlamaIndex 的「小单元匹配 / 大单元阅读」节点关系模型（SentenceWindow + Hierarchical，E11/E12）——直接对应 R1/R5；② AOCI 的**逐对象内容哈希基线 + 语义变更计数门禁**（E15/E16）——直接对应 R3；③ XERJ/Graphiti 的**双时态边（valid_at/invalid_at + as_of 回放、软失效不删除）**（E13/E14）——R3 的第二个答案，代价与 AOCI 完全不同。
2. **值得搬（2 件，R5/工具预算）**：Aider repo map 的「**图排序 + 固定 token 预算 + 按会话种子个性化**」（E17）与 LightRAG 的「**description 合并时 map-reduce 摘要到上限**」（E18）；外加 XERJ 的「**预算封顶 + 放不下的给 locator-only + 记账 + 错误永不截断**」工具返回契约（E13，见 §R6.5）——这三者是"索引/工具结果自己也要有预算"的成熟工程解法。
3. **明确不搬**：GraphRAG 全局检索（单次查询 610K tokens，E02）、RAPTOR 递归摘要树（需可靠聚类且无公开建树成本，E04）、Self-RAG/Adaptive-RAG 训练式控制器（需训练管线，E05/E06）、语义切分（成本不抵收益，E09）。
4. **两个参照实现是两种答案**：AOCI = 模型策展 + 哈希基线 + 验证回环（质量强、**每次维护都要花模型 token + 机器时间**：ledger 实测 maintain 中位 48.3s / 批量写入 97.6s，34 次 maintain 里 32 次 `repair_required`，E16）；XERJ = 确定性机器索引（BM25+HNSW+确定性边检测器）+ 双时态边（**每次写入带时间戳，不需要重新策展**，E13）。Memoria 的 KP 描述属语义层 ⇒ 更接近 AOCI，但**不应复制 AOCI 的全套仪式**。
5. **最大外部空白**：没有主流开源实现为「节点/块」提供"可判性摘要"字段（LlamaIndex 的 `metadata` 是自由 dict，E11）；R2 的"写什么才能不读原文就判"**没有现成标准答案**，只有间接证据（索引级 catalog 的 sample_queries 设计，E13）。
6. **成本结论（R11）**：GraphRAG 实测 1M tokens 语料索引 281 分钟（gpt-4-turbo/16GB VM，E01）；Memoria 14 章 606,619 tokens 按同参数线性外推 ≈ 2.8 小时墙钟。**论文没给美元成本**；按 deepseek-flash 价与 LightRAG 的 `LLM 调用数 = 总 tokens / chunk 大小` 公式（E02）粗算一次性 ≈ 数元级，但这是**本文的推算，不是实测**。
7. **R10 结论**：开源界的 node parser 全是**边界决策器**，没有一个是"语义标注器"；标题层级不可靠时**没有任何开源 parser 会自动推断层级**——层级要靠显式结构（markdown/HTML/代码语法）或 LLM 抽取（贵）。Memoria 的编号文字层级需要**自己写确定性解析器**（类比 tree-sitter，E17）。
8. **R12 结论**：外部没有"抽样人审比例"的公开数据；能搬的质量保证是：证据身份绑定（AOCI 的 `source_sha256`+批次身份；XERJ 的 `evidence{quote,source,offset}`+`confidence`+每次运行计数器，E13/E16）、删除审批阈值（AOCI `approval_thresholds`，E15）、以及"机器只能定位/校验，不能生成语义"的边界（AOCI §8，E15）。

---

## 1. 证据清单（后文按编号引用）

| ID | 来源 | 关键内容 | 许可 |
|---|---|---|---|
| E01 | GraphRAG, arXiv:2404.16130 (2024, v2 2025) https://arxiv.org/abs/2404.16130 ｜ HTML https://arxiv.org/html/2404.16130v2 | 1M-token 语料=1669×600-token chunks(100 重叠)；索引 281 分钟/16GB VM/gpt-4-turbo(2M TPM,10k RPM)；全局检索 comprehensiveness 胜率 72–83%(p<.001)、diversity 75–82%/62–71%；root 级社区摘要在"token 成本的一小部分"下接近全局法；chunk 600 vs 2400 ⇒ GPT-4 抽取实体引用约 2 倍；抽取质量受 prompt 工程影响（引 Zhu et al. 2024），且他们用了 self-reflection | CC BY 4.0 |
| E02 | LightRAG, arXiv:2410.05779 https://arxiv.org/abs/2410.05779 | 索引成本公式：LLM 调用次数 = 总 tokens / chunk 大小，无额外开销；在 Legal 数据集（5,081,069 tokens/94 文档）GraphRAG 检索生成 1,399 社区、用其中 610 个 level-2、每报告约 1,000 tokens ⇒ **610,000 tokens/查询 + 数百次 API 调用**；LightRAG <100 tokens 关键词 + 1 次 API 调用；增量更新无需重建；数据集来自 UltraDomain（428 本大学教材/18 领域，600K–5M tokens，**与 Memoria 教材同域**）；最大数据集上基线 LLM-judge 胜率仅约 20% | MIT |
| E03 | HippoRAG, arXiv:2405.14831 https://arxiv.org/abs/2405.14831 | KG 上 Personalized PageRank；多跳 QA 上"高达 20%"提升；单步检索≈IRCoT 且 **10–30× 便宜、6–13× 快** | 未读到 LICENSE，仅引用结论 |
| E04 | RAPTOR, arXiv:2401.18059 https://arxiv.org/abs/2401.18059 | 递归 embed→cluster→summarize 建树；GPT-4 + RAPTOR 在 QuALITY 上绝对准确率 **+20%**；**摘要页未给建树成本** | 未读到 LICENSE，仅引用结论 |
| E05 | Self-RAG, arXiv:2310.11511 https://arxiv.org/abs/2310.11511 | 用 reflection token **训练**模型按需检索/自评；7B/13B 优于 ChatGPT 与 RAG-Llama2 | 未读到 LICENSE，仅引用结论 |
| E06 | Adaptive-RAG, arXiv:2403.14403 https://arxiv.org/abs/2403.14403 | **训练一个小分类器**预测 query 复杂度→选 no-retrieval/单步/迭代 | 未读到 LICENSE，仅引用结论 |
| E07 | Lost in the Middle, arXiv:2307.03172 https://arxiv.org/abs/2307.03172 | 相关信息在长上下文中段时性能显著下降（U 形），显式长上下文模型也一样 | 未读到 LICENSE，仅引用结论 |
| E08 | OP-RAG ("In Defense of RAG in the Era of Long-Context"), arXiv:2409.01666 https://arxiv.org/abs/2409.01666 | 检索 chunk 数增加时答案质量**先升后降（倒 U）**；存在甜点区：比整段长上下文**质量更高且 token 更少** | 未读到 LICENSE，仅引用结论 |
| E09 | "Is Semantic Chunking Worth the Computational Cost?", arXiv:2410.13070 https://arxiv.org/abs/2410.13070 | 语义切分在文档检索/证据检索/答案生成三任务上**成本不被稳定收益抵消** | 未读到 LICENSE，仅引用结论 |
| E10 | Late Chunking, arXiv:2409.04701 https://arxiv.org/abs/2409.04701 | 先长文嵌入再切块（切块在 transformer 之后、mean pooling 之前），保留跨块上下文；**无需训练即可用** | 未读到 LICENSE，仅引用结论 |
| E11 | LlamaIndex `schema.py` MIT（LICENSE 头逐字：`The MIT License Copyright (c) Jerry Liu`）https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/schema.py | `NodeRelationship` = SOURCE/PREVIOUS/NEXT/**PARENT/CHILD**（L207–225）；`BaseNode` 字段 `id_`(L275)、`embedding`(L278)、`metadata`(L289)、`excluded_embed_metadata_keys`(L294)、`excluded_llm_metadata_keys`(L298)、`relationships`(L302)、`metadata_template`(L309)、`metadata_separator`(L316)；`TextNode`（L765）字段 `text`(L778)、`start_char_idx`(L782)、`end_char_idx`(L785)；`TextNode.hash = sha256(text+metadata)`（L801–803） | MIT |
| E12 | LlamaIndex `node_parser/text/sentence_window.py` + 官方 node parser 文档（commit 8797f52b）https://github.com/run-llama/llama_index/blob/8797f52b/docs/src/content/docs/framework/module_guides/loading/node_parsers/modules.md | SentenceWindow：按句切、窗口存 `metadata`、**窗口 key 加入 excluded_embed/excluded_llm**（L117–136）；文档列出的 parser 全集：SimpleFile/HTML/JSON/Markdown；CodeSplitter/Langchain 包装/Chunker(本地 chonkie)/Sentence/SentenceWindow/Semantic/TokenText；关系型 Hierarchical（`chunk_sizes=[2048,512,128]` + AutoMergingRetriever）（文档 L5–213）；SemanticSplitter 的两条 caveat：**正则以英文为主、breakpoint 阈值需调**（L165–168） | MIT |
| E13 | XERJ 运行时数据（本机引擎 1.0.0-rc.97；路径 `C:\Users\Lam Tim\xerj-data\`）+ 本会话 MCP 工具契约（`xerj_map` / `xerj_brain_*` / `xerj_*_search`） | 每索引目录 = `schema.json`+`es_mapping.json`+`settings.json`+`snapshot.json`(segments/doc_count/min_seq_no/max_seq_no/generation)+`xerj_meta.json`+`analysis-binding.json`+`wal/`+`segments/*.{fst,meta,norms,post}`，向量索引另有 `hnsw/graph.bin`；记忆索引 `embedding_execution.json` = `{backend:"lexical", identity_sha256:"58a7576c…"}`；二脑边索引字段 = `edge_id/src/dst/type/weight/**valid_at/invalid_at/created_at/expired_at**/detector/confidence/schema_version/src_file/src_format/dst_format/evidence{quote,source,offset}/meta_version/brain/nodes_index`；`autoindex-catalog` 每索引一条记录含 `fields_json`/`sample_queries_json`/`time_field`/`time_min`/`time_max`/`semantic_field`/`record_count`/`junk`/`bytes`/`status`/`notes` + 跑批统计（`wall_seconds`/`docs_per_sec`/`workers`/`memory_safe_zone_mb`）+ 边质量计数（`edges_unresolved/ambiguous/capped/self_dropped/invalidated`）；`brain_overview("agents")` 实测：nodes_index=ax-docs、51 节点、17 活边、类型 pathcite/same_dir/sequence/mdlink、detector=pathcite@1/samedir@2/sequence@2/mdlink@2、embedder=`lexical-feature-hash` | 闭源二进制（本机无源码） |
| E14 | Graphiti `graphiti_core/edges.py`（Apache-2.0，LICENSE 头逐字 `Apache License Version 2.0`）https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py | `EntityEdge` = `name/fact/fact_embedding/**episodes**(溯源到 episode)/**expired_at/valid_at/invalid_at/reference_time**/attributes`（L263–290），`invalid_at` 注释："fact 停止为真的时间；软截止不算 invalid_at" | Apache-2.0 |
| E15 | AOCI 本机实现（服务版本 `0.1.0-rc20`，仓库根 `D:\AAA_Jupyter\Memoria`）`ev:file:.aoci/config.json`、`ev:file:.aoci/baseline.json`、`ev:file:aoci.meta.txt`、`ev:file:aoci.txt`、`ev:file:aoci.code.txt`、`ev:file:.aoci/ledger.jsonl` + 本会话 `aoci_rules`/`aoci_overview` 契约 | Entry 形如 `<path>[tag]: F:… | R:… | A:… | S:…`（`aoci.meta.txt:10` 示例；`aoci.code.txt:6` 实例）；tag 字典 A 层/B 模块/C 重要度/E 规模（`aoci.meta.txt:11–20`，C 9=最高）；`S-Admission: non-inferable-and-error-preventing`（`:5`）、S 配额按 C 级（`:6`）、`FRAS-v2-Limits-Authority: machine-contract`（`:4`）；卷定义 `aoci.txt:1–7`；基线 `baseline.json` = 每文件 `{role,sha256,**normalized_sha256**,size}`，583 文件（`version=1, updated_at=2026-10-13`）；配置 `cognition_refresh_threshold: 30`（`:42`）、`line_ending_tolerance: true`（`:41`）、`cognition_budget.whole_index` target 200K / warn 300K / max 400K（`:171–178`）、**按 C 级的 R/S 每 Entry token 预算**（C9: R 90/180、S 100/200，`:179–230`）、`managed_scope` 排除目录与 `approval_thresholds.entry_removal_count=25 / percent=25`（`:46–169`，阈值在 `:51–54`） | 本机 |
| E16 | AOCI `ev:file:.aoci/ledger.jsonl`（228 条事件，2026-10-10→2026-10-27）+ `aoci_overview(check_only)` 实测 | ledger 累计机器耗时 **10,049.9s**（约 2.8 h）；按 op：`maintain` n=34 中位 48.3s / `update_entries_batch` n=32 中位 97.6s / `auto_finalize` n=35 中位 109.9s / `cognition_check` n=8 中位 82.8s（max 318.6s）/ `overview` n=13 中位 72.5s；结果分布：`maintain` **32/34 = repair_required**、`update_entries_batch` 26 ok / 4 error / 2 rejected、`remove_entry` **91 次 ok**；checkpoint 实测：`semantic_change_count=1535`（阈值 30）、`semantic_stale=114`、`actionable_missing=1421`、`orphan=4`、`pending_curation=0`、`format_only=0`、`line_ending_only=0`、`whole_index_tokens=13947`、`scope_object_count=470`、`governance_aligned=false` | 本机 |
| E17 | Aider `aider/repomap.py`（Apache-2.0，LICENSE 头逐字 `Apache License Version 2.0`）https://github.com/Aider-AI/aider/blob/main/aider/repomap.py | repo map 默认预算 `map_tokens=1024`（L49）、无文件时倍数 `map_mul_no_files=8`（L56）、按上下文窗口设置上限（L111–132）；`get_ranked_tags` 用 **networkx PageRank**，`personalization` 由"会话中提到的文件名/标识符"生成（L365–529）；渲染时**二分逼近预算**：`middle = min(int(max_map_tokens // 25), num_tags)`，比较 `abs(num_tokens - max_map_tokens)`（L633–698） | Apache-2.0 |
| E18 | LightRAG `lightrag/operate.py`（MIT）https://github.com/HKUDS/LightRAG/blob/main/lightrag/operate.py | `_handle_entity_relation_summary`（L372–440+）：合并描述时按 `summary_context_size`/`summary_max_tokens`/`force_llm_summary_on_merge` 决定是否 **map-reduce 摘要**；`_merge_nodes_then_upsert`(L2429)/`_merge_edges_then_upsert`(L2782) 增量合并 upsert；`_apply_token_truncation`(L5501–5548) 用 `max_entity_tokens`/`max_relation_tokens` **分阶段截断并按列表位置分配 chunk 配额**；`_truncate_vdb_content`(L297) | MIT |
| E19 | Memoria 现状代码（本仓）`ev:file:src/memoria/services/agent/tools/kb.py#L248`、`#L337–377`；`ev:file:src/memoria/services/search_kernel.py#L38–105` | agent 的 `_search_kb` **硬编码 `modes="lexical"`**（kb.py:248）；`search_kernel.search` 支持 `lexical/semantic/both/full` 且 `both/full` 走 RRF（search_kernel.py:58–105）；`_read_kp` 按 sidecar 的 `start_line/end_line` 取行区间、可选带 `description/tags/aliases`，锚点 = `{file,line,kp_id,name,snippet}`（kb.py:337–377） | 本仓 |

---

## 2. 逐项对照表

| 做法 | 解决的问题 | 代价（实测/原文） | 在 Memoria 能否落地 | 证据 |
|---|---|---|---|---|
| 逐文件 `sha256`+`normalized_sha256` 基线，按"语义变更数"触发刷新（≤阈值就 defer） | R3 低成本陈旧检测；行尾/格式变化不误报 | 每次要对全部受管文件做哈希（583 文件基线 159KB）；AOCI 每次 checkpoint 实测中位 **82.8s**、最坏 318.6s | **能**，但 Memoria 应按"章"而非全库；块级哈希更省 | E15, E16 |
| 双时态边：`valid_at/invalid_at` + `created_at/expired_at`，`as_of` 回放，软失效永不删 | R3 索引过期；R7 图的时效语义 | 写入必须带时间戳（每个事实 2–4 个时间字段）；但**不需要重新策展**；查询要带 `as_of` 语义 | **能**（sidecar 加 4 个时间字段），且与 FSRS 无关，不冲突 | E13, E14 |
| 边上的 `evidence{quote,source,offset}` + `detector` + `confidence` | R3/R12 可复核、可追责 | 每条边多存一段引文；存储可忽略 | **能且应该**（KP 的 description 也照此绑定） | E13 |
| 每索引的 "catalog 记录"：字段图 + `sample_queries_json` + 时间范围 + 记录数/垃圾数 | R2/R5 **索引级的"可判性摘要"**（先判该不该查这个索引，再判读哪块） | 每索引一条 JSON；跑批统计顺带产生 | **能**——`kb_overview` 应先返回"章目录 + 每章样本问题 + KP 数/未覆盖数"，而不是 KP 全表 | E13 |
| 小单元 embedding + 大窗口进 LLM，窗口字段排除在 embedding/LLM 之外 | R1/R5 匹配粒度≠阅读粒度，天然省 token | 每节点多存一份窗口文本（存储 ×window） | **能**：KP 匹配用 description/关键词，`read_kp` 仍返回原文区间 | E11, E12 |
| 层次节点 + AutoMergingRetriever（子节点命中过半→自动上提父节点） | R5 分层展开、避免一次给整章 | 建索引时多一层切分；查询时多一次父节点判断 | **能**：章→节→KP 三级，默认给 KP，命中多 KP 同节时上提节 | E12 |
| 合并时对 description 做 map-reduce 摘要到 token 上限 | R2/R3 description 会随增量更新膨胀 | 只在"合并后超限"才调 LLM；有 `force_llm_summary_on_merge` 阈值 | **能**：KP 描述更新时按上限裁剪（AOCI 已有 per-C token 预算可复用） | E18, E15 |
| 检索结果分层截断：`max_entity_tokens`/`max_relation_tokens`/chunk 配额 | R5 + 工具结果预算（对应"工具结果放大 10.94×"） | 需 tokenizer + 配额策略；被截断内容需显式告知 | **能**：`read_kp`/`search_kb` 返回值加硬预算 + `truncated: true` | E18 |
| 图排序 + 固定预算 + 会话种子个性化（repo map） | R5 索引本身有预算；R6 与 query 相关而非固定全量 | 需要图 + PageRank + 二分拟合（纯本地计算，**零 LLM**） | **能**：KP 图（前置/相关边）做 personalized ranking，`kb_overview` 输出 1024 tok 级"地图" | E17 |
| GraphRAG 社区摘要 + 全局 map-reduce 检索 | 全局性/主题性问题（"这批教材的主要论点"） | **610K tokens/查询 + 数百次 API 调用**；建索引 281 min/1M tokens | **不默认搬**（Memoria 95%+ 提问是章内定位，不是全局综述）；可留"全局模式"按需 | E01, E02 |
| RAPTOR 递归摘要树 | 长文档多跳、跨层抽象 | 建树需 embed+聚类+逐层摘要；**未找到公开建树成本**；QuALITY +20% 是长文档多跳任务 | **不做默认**；可作为"单章深读"实验 | E04 |
| Self-RAG / Adaptive-RAG 控制器 | 决定"要不要检索/检索多少" | **需要训练**（reflection token 微调 / 复杂度分类器） | **不做**：本地优先、无训练管线；用提示词级启发式替代 | E05, E06 |
| 语义切分（embedding 断点） | 块边界更"语义" | 成本不被稳定收益抵消；caveat：英文正则、阈值要调 | **不做**：KP 边界应由产品/人定义，不由 embedding 决定 | E09, E12 |
| 迟切块（late chunking） | 块向量丢上下文 | 需要长上下文 embedding 模型；**无需训练** | 可选（若 embedding 层升级）；对"description 可判性"无直接帮助 | E10 |

---

## 3. 对 R1–R8 的直接回答

### R1 索引单元：KP 还是块？
**外部没有"KP"这个概念；开源界的单元由 parser 决定，而不是由学习单元决定。** LlamaIndex 提供 9 类 parser（E12），其中只有 `MarkdownNodeParser`/`HTMLNodeParser` 尊重**显式**层级，`HierarchicalNodeParser` 的层级是**按 token 大小**造出来的（`chunk_sizes=[2048,512,128]`，E12），`SentenceWindowNodeParser` 则是"句子匹配 + 窗口阅读"（E11/E12）。
⇒ **建议**：Memoria 的 KP 作为**产品/学习单元**保留（外部无对照物，这是 Memoria 的差异化），但索引要分两层：**KP 摘要节点（description+关键词）** 与 **KP 内块（可读区间）**；锚点用**字符偏移**（LlamaIndex `start_char_idx/end_char_idx`，E11）而不是行号。理由：本仓锚点是 `{file,line,kp_id,name,snippet}`（E19），行号会漂、snippet 会重名；字符偏移+内容哈希是外部通用解。

### R2 description 的"可判性"：写什么？
**诚实结论：没有外部标准答案。** 我查过的所有实现里：
- LlamaIndex 的 `metadata` 是自由 `dict`（E11），没有"可判性摘要"字段，也没有 schema 约束；
- LightRAG 的实体/关系"描述"是**抽取出的多段事实拼接**，靠合并时 map-reduce 摘要控长（E18），它优化的是"压缩"不是"可判";
- 唯一接近"不读原文就能判断"的**外部设计**是 **XERJ 的索引级 catalog**：每条索引记录带 `fields_json` + `sample_queries_json` + 时间范围 + 记录数/垃圾数（E13）——它是"这个索引值不值得查"的可判摘要，不是"这条内容该不该读"的可判摘要。**可以把它的思路下沉一层**：每个 KP 给 2–3 个"样本问题"（该 KP 能回答什么），比抽象描述更可判。
- 反例证据（外部）：GraphRAG 论文自认实体抽取质量受 prompt 工程影响很大，且不同 chunk 大小下抽取量差 2 倍（E01）⇒ **靠 LLM 写摘要的字段质量天然波动**，所以 description 必须**可机检**（非空/长度/与兄弟的重叠度），不能只靠"写得好"。

⇒ 建议：description 写三件事（**经验判断，外部无对照**）：① 该 KP 能回答的问题（1–2 个，形态同 XERJ `sample_queries`）；② 与**兄弟 KP 的边界**（"这里不讲 X，X 在下一节"）——这正对应本仓实测"45% 判不出缺的是兄弟边界"；③ 何时**不该**读它。

### R3 证据绑定与陈旧检测
外部有**三种**成熟答案，代价不同：
1. **内容哈希基线 + 语义变更计数**（AOCI）：`baseline.json` 逐文件 `sha256` + `normalized_sha256`（行尾容错），583 文件；`cognition_refresh_threshold=30`，`format_only`/`line_ending_only` **不计入**语义变更；达到阈值就 `refresh_required`，否则 `refresh_deferred_until_stable`（E15/E16）。**代价**：全量哈希（实测中位 82.8s/次）+ 触发后的模型策展（ledger：`maintain` 34 次中 **32 次 repair_required**，`update_entries_batch` 中位 97.6s、`auto_finalize` 109.9s，E16）。**这是"质量换钱"**。
2. **双时态边**（XERJ / Graphiti）：每条边有 `valid_at/invalid_at`（事实何时真/何时不再真）+ `created_at/expired_at`（系统何时学到/何时退休），`as_of` 可回放历史；失效是**软失效**（`unlink` 只是写 `invalid_at`，永不物理删），`edge_id` 对 `(src,type,dst,valid_at)` 确定性生成 ⇒ 重放幂等（E13/E14）。**代价**：写入时每个事实多 2–4 个时间字段、查询要处理时间语义；**不需要重新策展**。**这是"钱换质量"**（靠检测器的确定性，不靠模型重写）。
3. **增量 upsert + 合并摘要**（LightRAG）：新文档走同一抽取流程，按实体名合并、描述超限才摘要（E18/E02）。**代价**：每次新增仍要 LLM 抽取（`LLM 调用数=总 tokens/chunk 大小`），但**不重建全库**。

⇒ 建议（Memoria 选型，理由在 §5 的边界内）：**description 绑定 `source_sha256`（块级）+ `range(char)`**；陈旧检测用**块级哈希 diff**（不是全库哈希，省掉 AOCI 那种 83s 级检查）；stale 期间**降级为"读原文 + 标注 unverified"**（AOCI 的做法是"Dirty 仍交付但标不可靠"，XERJ 的做法是 `as_of` 回放，两者都支持"不假装新"）。**不要把 AOCI 的 `repair_required` 式重写回环搬进来**——34 次 maintain 32 次返工（E16）对本地产品太重。

### R4 锚点稳定性
外部通用做法是 **id + 内容哈希 + 字符偏移**三重，而不是行号：
- LlamaIndex `BaseNode.id_` + `TextNode.start_char_idx/end_char_idx` + `hash=sha256(text+metadata)`（E11）；
- XERJ 边 `edge_id` 由 `(src,type,dst,valid_at)` 确定性生成（E13）；
- AOCI 对象身份是 `code:<path>` + 每次候选的 `source_sha256`，写入走 CAS（E15）。
⇒ 建议：锚点 = `{kp_id, file, char_range, source_sha256}`，行号只作**显示**；漂移时用 `source_sha256`/snippet 做**就近重定位**（内容哈希命中即修复），失败则标 stale 而不是静默指向错行。产品"划高亮"改动正文会改变 char 偏移——因此**必须**把 `source_sha256` 作为唯一可信身份，偏移仅加速。

### R5 检索路径与预算
外部有四个可直接借的工程解法：
1. **索引本身要有硬预算**：AOCI `cognition_budget.whole_index` target/warn/max = 200K/300K/400K tokens，且**每个 Entry 有按 C 级的 R/S token 上限**（C9: R 90/180、S 100/200）（E15）；overview 分块交付 `chunk_tokens=7000`（E15 契约）。⇒ 索引不是"免费的元数据"，要像 prompt 一样预算。
2. **图排序 + 固定预算 + 会话个性化**（Aider）：`map_tokens=1024`，PageRank 的 personalization 来自"本次会话提到的文件/标识符"，渲染时二分逼近预算（E17）。⇒ `kb_overview` 应该是**按当前问题个性化、1024 token 级的地图**，不是全量 KP 列表。
3. **分阶段截断 + 配额**（LightRAG）：`max_entity_tokens`/`max_relation_tokens`，chunk 配额按列表位置分配，且显式记录 `truncation_tally`（E18）。⇒ 工具返回值必须带 `truncated` 标记与"被截断多少"。
4. **倒 U 曲线**（OP-RAG）：检索块数不是越多越好，存在质量甜点（E08）；Lost-in-the-Middle 说明长上下文中段会被忽略（E07）⇒ 不要把"多给原文"当安全策略。

### R6 与现有检索栈融合
- 本仓 `search_kernel.search` **已经有** `lexical/semantic/both/full`，`both/full` 走 RRF 融合（E19，`search_kernel.py:58–105`），但 agent 的 `_search_kb` 硬编码 `modes="lexical"`（E19，`kb.py:248`）。**这是接线问题，不是能力缺失。**
- 外部融合的共识就是 **RRF**：XERJ 的 hybrid 支持 `rrf|linear`（E13 工具契约）；LightRAG 用"低层关键词+高层关键词"双路再融合（E02）。⇒ **不需要新造检索层**。
- 索引该"替代哪一层"：**不替代** lexical/semantic/rerank 的任何一层；它应作为**候选过滤与阅读预算层**（metadata filter → 候选 KP → 分层展开），即 LlamaIndex 的 `metadata filters` + `AutoMergingRetriever` 的模式（E12）。
⇒ 建议：① 先把 `_search_kb` 的 `modes` 放开为 `both`（一行接线，零新组件，E19）；② KP 索引只做 **filter/rerank 特征**（kp_id、章、覆盖度）与**阅读展开**；③ 不要另开"图谱检索"第二套管线。

### R7 AOCI 与 XERJ 的 Entry/索引设计对比
| 维度 | AOCI | XERJ |
|---|---|---|
| 索引是什么 | 模型写的**认知条目**（每条一行 `F/R/A/S`，E15） | 机器建的**倒排+向量**（`segments/*.fst`、`hnsw/graph.bin`）+ 目录索引（E13） |
| 语义从哪来 | **只有模型能写语义**；路径/AST/正则「只能定位、校验，不能生成」（E15 `aoci_rules` §8） | **确定性检测器**（`mdlink/samedir/sequence/pathcite`）+ lexical 特征哈希 embedder（E13） |
| 防"索引烂" | 证据身份（`source_sha256`+批次身份+CAS）、Verify/Check/Guide 状态机、Challenge Attestation、Ledger、孤儿裁决、删除审批阈值（E15/E16） | `confidence`+`detector`+`evidence{quote,source,offset}`+每次跑批的 `edges_unresolved/ambiguous/capped/self_dropped/invalidated` 计数（E13） |
| 过期怎么办 | 哈希基线 → 语义变更计数 → 模型重新策展（**花 token，34 次 maintain 32 次返工**，E16） | bitemporal 边 + 软失效（**花写入字段，不花策展**，E13） |
| 适合什么 | 需要"可读、可审、可解释"的语义索引 | 需要"便宜、确定、可回放"的检索与事实时效 |
⇒ Memoria 的 KP description 是**语义**产物 ⇒ 骨架应学 AOCI（证据身份+机检+删除审批），**但把"每次变更都模型重写"换成"块级哈希定位 + 只重写变更块"**；图的时效学 XERJ/Graphiti（双时态软失效）。

### R6.5（lead 指定）工具结果预算 / 摘要回退：外部成熟做法
> 背景输入（Lead 实测，我未复测）：第 k 轮的工具结果在后续每轮重发，**放大系数 10.94×**。问题：外部有没有"工具结果预算/摘要回退"的做法？

有，且都是**产品级**做法（不是论文）：

| 做法 | 机制（关键设计） | 证据 |
|---|---|---|
| **预算封顶 + locator-only 回退 + 记账**（XERJ MCP 工具契约） | 响应带 `max_tokens` 预算；**绝不超预算**；放不下的命中不丢弃，而是列成 **LOCATORS ONLY**（file:line + id），并由 `_token_budget` 块记账 `kept/locator-only/deduped/dropped`；重叠片段先去重；错误信息**永不截断**（"a refusal you cannot read end-to-end is worse than a long response"） | E13（`xerj_search`/`xerj_code_search`/`xerj_hybrid_search` 工具契约） |
| **分阶段 token 截断 + 配额**（LightRAG） | `max_entity_tokens`/`max_relation_tokens` 分阶段截断；chunk 配额**按列表位置**分配；截断有 `truncation_tally` 记录；"选择器可重排/丢弃，但**不能发明**"（invent 的记录会被丢弃并告警） | E18 |
| **优先级填充到上限**（GraphRAG 社区摘要） | leaf 级社区：元素摘要按优先级排序后**迭代加入，直到 token 上限**；高层社区若全部元素能装进窗口就直接总结 | E01 |
| **检索小单元、上送大单元**（LlamaIndex） | SentenceWindow：embedding 只看句子（`excluded_embed_metadata_keys` 排除窗口），上送 LLM 前用 `MetadataReplacementNodePostProcessor` 把句子替换成窗口 → **同一份原文只送一次、且只送需要的那段窗口** | E11/E12 |
| **命中过半才展开父节点**（LlamaIndex AutoMergingRetriever） | 子节点命中超过阈值才自动上提父节点，避免"给整章" | E12 |
| **索引/索引交付本身有预算**（AOCI） | 全量索引 target 200K/warn 300K/max 400K tokens；overview 分块 `chunk_tokens=7000`；`aoci_maintain`/`update_entries_batch` 受 `max_entries` 与 transport 预算约束 | E15 |
| **零 LLM 的预算拟合**（Aider） | 预算 1024 tokens，二分逼近（`min(max_map_tokens // 25, num_tags)` 步长），按 PageRank 排序输出"地图"而非全文 | E17 |

⇒ **可直接搬的一条**：把工具返回改成"**预算封顶 + 未返回部分给 locator + 记账 + 错误不截断**"（XERJ 契约形态）。它是唯一同时满足"省 token、可继续操作、可审计"的设计：agent 看到 locator 后可以按需二次读取，而不是被动接受被砍一半的正文。LightRAG 的"截断必须记账"和 AOCI 的"索引本身有 token 预算"可作为配套。

### R8 如何证明"真正对 agent 有提升"
外部证据**不能直接借用**，因为它们的指标是"LLM-judge 胜率"而非"答对率"：GraphRAG 用 comprehensiveness/diversity 胜率 72–83%（E01），LightRAG 用 LLM-judge 四维胜率（E02）——**这类指标不能证明"答对率不降"**。
⇒ 按 PROTOCOL E4/E4.2/B4 设计：同 commit/同语料/同任务集/同轮数，≥3 次重复，报 `prompt/completion/total` 与加权成本（B4.a）、报分布而非单次（B4.b）、分离 `functional_pass` 与 `token_delta`（B4.e）。**falsifier 见 §6**。
补充外部支持：OP-RAG 的倒 U（E08）意味着"省 token"与"答对率"不是单调关系，A/B 必须至少扫 2–3 个预算档，否则可能测到曲线左侧（还没到甜点）就下结论。

---

## 4. 我【否决】的 3 个外部方案及具体冲突点

### 4.1 否决：GraphRAG 的全局检索（community summaries + map-reduce）
**冲突点（数字）**：LightRAG 在 Legal（5.08M tokens）实测 GraphRAG 检索消耗 **610,000 tokens/查询**（610 个 level-2 社区 × 1,000 tokens）并需数百次 API 调用（E02）；而 Memoria 的真账是**平均 225,553 tokens/轮、峰值 656,818**（1M 窗口 65.7%）。**一次 GraphRAG 全局查询就会吃掉 Memoria 一轮的全部预算**，且它解决的是"对整个语料的全局综述"，Memoria 实测提问以章内定位为主。
**最小替代**：保留"全局模式"作为**显式触发**的独立工具（用户问"这批教材的主线"时才用），默认路径不用。
（注意：GraphRAG 的**思路**——层次化 + 摘要——是对的，被否决的是**每次查询 map-reduce 全社区**这个代价。）

### 4.2 否决：RAPTOR 递归摘要树作为默认索引
**冲突点**：① 它需要**可靠聚类**（embed→cluster→summarize，E04），而 Memoria 的 KP 边界目前来自标题（93.3% KP 起点=标题行）——在边界本身不可靠的语料上做聚类，会把错误放大一层；② **建树成本无公开数据**（E04 摘要页只给效果，不给成本），无法做 R11 的成本决策；③ 它的收益场景是"长文档多跳"（QuALITY +20%），与 Memoria 的"选对 KP 再读"不同层。
**最小替代**：单章"深读模式"里用一次递归摘要（按需、单章、可缓存），不做全库预建树。

### 4.3 否决：Self-RAG / Adaptive-RAG 式的"模型自己决定检索多少"
**冲突点**：两者都**需要训练**——Self-RAG 用 reflection token 微调 LM（E05），Adaptive-RAG 训练一个复杂度分类器（E06）；Memoria 是本地优先产品，**没有训练管线**，且换模型即失效。
**最小替代**：把同样的决策做成**提示词级启发式**（"description 是否包含问题关键实体/是否与兄弟边界冲突 → 读原文/不读"）+ 工具返回值里带 `confidence`/`coverage` 字段，由 agent 的 system prompt 决策；不需要训练。**这也顺带回答了"description 够不够、要不要读原文"**：由**规则+字段**决定，而不是由训练出的控制器决定。

---

## 5. 我【不确定】/【查不到】的点（M3 登记）

1. **AOCI 的 `duration_ms` 语义未验证**：我读的是 `.aoci/ledger.jsonl` 的字段，**没有读到 AOCI 源码**（本机只有 MCP 服务与 `.aoci` 数据）。"中位 48–110s"是**机器侧时长**，**不含模型读写索引的 token 成本**（那部分 ledger 不记录）。⇒ E16 只能支持"验证回环很重"，**不能**支持"AOCI 总成本 = X 元"。
2. **XERJ 是闭源 Rust 二进制**（`C:\ProgramData\xerj\xerj.exe`、`C:\xerj\xerj-1.0.0-rc.96…`，数据版本 `1.0.0-rc.97`）。我读到的是**磁盘上的索引文件布局**与 **MCP 工具契约**，**没有读到引擎源码**；"detector 如何判定 `mdlink/samedir`"、"`lexical-feature-hash` 的召回质量"**均未验证**。
3. **GraphRAG 的美元成本未找到公开数据**：论文只给墙钟 281 分钟/1M tokens 与模型/端点（E01），**没有 $ 数字**。⇒ 对 R11 的决策含义：只能按 token 量线性外推，**不能**拿"$X/百万字"当事实引用。**RAPTOR 建树成本同样未找到公开数据**（E04）。
4. **LlamaIndex `SummaryIndex` 的"建索引成本≈0"是读代码得出的**（`_build_index_from_nodes` 只把 nodes 塞进 `IndexList`，无 LLM 调用，E12 来源文件 `indices/list/base.py:96–123`），但**查询期成本**（遍历全部节点 + refine）**未实测**。
5. **LangChain 与 RAGFlow 的代码未取到**（`raw.githubusercontent.com` 多次超时/404，RAGFlow 走 jsdelivr 也失败）。因此本文**不对** `MultiVectorRetriever`/`ParentDocumentRetriever`/RAGFlow 的 chunk `keywords/questions` 字段作任何代码结论——若后续需要，应补 `pip download` 或本地 clone。
6. **"抽样人审比例"未找到公开数据**：AOCI 有删除审批阈值（25 条/25%），但**没有**"随机抽 N% 复核"的公开约定；XERJ 有 per-run 质量计数但没有抽样协议。
7. **"description 真的能提升答对率"没有外部实验**：所有外部证据都在**检索层**（recall/nDCG/胜率），没有"给 agent 一句 description 就能少读原文且不降准确率"的直接实验。⇒ 这是 R8 必须自测的核心假设。

---

## 6. Falsifiers（什么实验会推翻本文推荐）

| # | 我的主张 | 推翻条件（可执行） |
|---|---|---|
| F1 | 块级哈希比全库哈希更划算 | 若"块级哈希 diff"在 14 章 606K tokens 上单次耗时 > 全库文件哈希（对照 AOCI 实测中位 82.8s），则 R3 推荐反了 |
| F2 | description+样本问题能让 agent 判断"不读" | A/B 中"只给 description/样本问题"组相对"直接读 KP"组，**答对率下降 >2 个百分点**，或"该读未读率"上升 ⇒ R2/R5 的省钱路径不成立 |
| F3 | KP 索引应只做 filter/展开，不另开检索层 | 若放开 `modes="both"`（E19）后 RRF 召回已覆盖 KP 索引的收益，则"KP 索引作为检索层"的增量价值 ≈0 ⇒ R6 结论加强；反之若 RRF 单独很差而 KP 索引显著更好，则"只做 filter"过于保守 |
| F4 | 双时态（软失效）优于模型重写 | 若软失效导致"过期 description 仍被 agent 使用"的比例 >5%（需埋点：读过 stale KP 且答案引用其错误内容），则须改为 AOCI 式硬刷新 |
| F5 | 全量建索引一次性成本可接受（数元级/14 章） | 实测建索引 token 成本若 > 该库**10 次会话**的账单（真账 1.64 元/16 轮 ⇒ >16 元），则"全量预建"不成立，应改"按需建章" |
| F6 | 结构化（标题/编号）切分优于语义切分 | 若确定性编号解析器在 14 章上产生的 KP 边界被人工判定"不可学"的比例 > 语义切分方案，则 R10 推荐反了（外部已有语义切分成本不划算的证据 E09，但不是"效果更差"） |

---

# Phase 1.5 追加：索引构建方法论（R10/R11/R12）

> 触发：人 2026-10-27 "索引确实尚未建立，但是也要研究**怎样科学进行索引**"。
> 本节的结论**只回答"怎么建"**；不修改上面的推荐。

## R10 建索引的信源与顺序

### R10.1 外部实现从什么生成索引？（读实现，不是读 README）

LlamaIndex 的 node parser 全集按"信源类型"分三类（E12，官方文档 commit 8797f52b）：
```
文件型（按格式解析）: SimpleFileNodeParser / HTMLNodeParser / JSONNodeParser / MarkdownNodeParser
文本切分型（按长度/句子/语义）: CodeSplitter / LangchainNodeParser / Chunker(chonkie) /
                              SentenceSplitter / SentenceWindowNodeParser /
                              SemanticSplitterNodeParser / TokenTextSplitter
关系型（造层级）: HierarchicalNodeParser(+AutoMergingRetriever)
```
关键观察（**这三类全都是"边界决策器"，没有一个是"语义标注器"**）：
- `MarkdownNodeParser` 只按 **markdown 标题层级**切（E12）⇒ 若层级不可靠，它输出的是扁平的 371 个 H2，不会推断层级；
- `HierarchicalNodeParser` 的层级是**按 `chunk_sizes=[2048,512,128]` 的 token 大小**造的（E12），**与语义无关**；
- `SemanticSplitterNodeParser` 用**句向量相似度选断点**，官方 caveat 明说"正则主要适用英文句、阈值需调"（E12），且外部已有系统评测认为它的成本不被稳定收益抵消（E09）；
- 只有 `SentenceWindowNodeParser` 是"匹配单元 ≠ 阅读单元"的设计（E11/E12）——**这是唯一直接服务"少读原文"的 parser**。

**GraphRAG / LightRAG 的信源**是"固定大小 chunk + LLM 抽取"：GraphRAG 用 1669×600-token chunks（100 重叠）（E01）；LightRAG 的索引成本公式就是 `LLM 调用数 = 总 tokens / chunk 大小`（E02）。**即：它们不在"结构"上做文章，而是把语义交给 LLM 抽取。**

### R10.2 标题层级不可靠时，外部怎么处理？

**直说：没有主流开源 parser 会从"编号文字"（如 `3.2.1`）推断层级。** 我查到的处理方式只有三条：
1. **用真正的结构**：markdown/HTML 的 DOM 层级、代码的语法树。Aider 的 repo map 就是**确定性语法解析**的最佳证据：tree-sitter 出符号+引用图，**零 LLM**（E17）。⇒ 说明"只要语料有可靠语法，层级可以确定性得到"。
2. **用布局模型**（PDF 场景）：RAGFlow 走 DeepDoc 版面分析——**本文未能取到其代码，不作结论**（§5.5）。
3. **用 LLM 抽取/摘要**：GraphRAG 的实体抽取、RAPTOR 的递归摘要。代价是每 chunk 一次 LLM 调用（E01/E02），且抽取质量受 prompt 影响（E01 自述）。

⇒ **对 Memoria 的直接含义**：本仓教材的层级编码在**编号文字**里（H1=1/H2=371/H5=1，层级靠编号）。这不是 markdown 结构，**没有任何现成 parser 能用**；正解是**自己写一个确定性的"编号层级解析器"**（类比 tree-sitter：先定义"编号 token 的语法"，再构建树），而不是把边界交给 LLM 或 embedding。这与 AOCI 的边界原则一致：**正则/路径/AST 只能用于定位与校验，不能用于生成语义**（E15 `aoci_rules` §8）——即：**边界可以由确定性规则决定（可复核），语义标签必须由模型写（可审）**。

### R10.3 建议的建索引顺序（每步都给校验点）

```
1 结构扫描（确定性，零 LLM）：目录/编号/token 长度 → 候选层级树
   校验：树深度、每层节点数、是否有孤儿段（无归属文本）
2 定边界（确定性 + 人审抽样）：KP = 学习单元，边界取"编号节点 + 语义完整性检查"
   校验：93.3% 起点=标题行 的现状说明现在只是"标题切分"；
        必须抽查"KP 是否含完整定义/例题"（否则 agent 读到的块不完整）
3 绑定证据身份（零 LLM）：{kp_id, file, char_range, block_sha256}
   校验：每个 KP 的 char_range 可反向切片且 sha256 匹配（这是 R3/R4 的地基）
4 写 description（唯一用 LLM 的步骤）：样本问题 1–2 条 + 兄弟边界 + 何时不该读
   校验：非空、长度上限（按重要度分级，参考 AOCI per-C 预算 E15）、
        与兄弟 KP 的 description 相似度不得高于阈值（防"都写抽样"）
5 机器复核（零 LLM）：覆盖度报告 = 已索引章/总章、未覆盖 token、KP 密度、锚点可切片率
   校验：这五项必须落盘（本仓现状：description 0/357 落盘 ⇒ 第 5 步缺失）
6 落盘 sidecar（单一事实源）+ 记录 build_run 统计（耗时、调用数、失败数）
   参照 XERJ 每索引 catalog 记录跑批统计（wall_seconds/docs_per_sec/失败计数，E13）
```
**顺序的要点**：**先边界、后语义**。若先让 LLM 写 description 再定边界，边界一变全部 description 作废（重写成本 = 全量）。这是 R11 里"增量建索引"能成立的前提。

## R11 时机与成本（★ 最重要）

### R11.1 GraphRAG 的 indexing 实测成本（原文数字）

| 量 | 数值 | 来源 |
|---|---|---|
| 语料 | ~1M tokens（1669 × 600-token chunks，100 重叠） | E01 |
| 索引墙钟 | **281 分钟**（虚拟机 16GB RAM / Xeon 8171M；gpt-4-turbo，2M TPM / 10k RPM） | E01 |
| 折算 | **≈10.1 秒/chunk**；≈ 4.7 小时/百万 token | 由 E01 两数相除（本文计算） |
| 美元成本 | **论文未给**（只有墙钟与端点） | E01 |

**对 Memoria 的外推（标注为推算，不是实测）**：14 章 = 606,619 tokens（任务书给出的本仓实测）⇒ 若同样 600-token chunk：`606,619/600 ≈ 1,011` 个 chunk；按 10.1s/chunk ⇒ **≈ 10,200s ≈ 2.8 小时**墙钟（假设同样的模型吞吐与并发）。**这是"按 GraphRAG 参数"的上界参考**，不是 Memoria 必付的价。

### R11.2 RAPTOR / SummaryIndex 的建树成本

- **RAPTOR**：摘要页只给效果（QuALITY +20%，E04），**没有建树成本数字**；其流程是 embed→cluster→summarize 逐层递归，成本 ≈ Σ(每层簇数 × 摘要调用)，**层数越多越贵**。⇒ **未找到公开数据**，决策含义：不能把 RAPTOR 作为"便宜方案"引用的依据。
- **LlamaIndex `SummaryIndex`**：**读代码确认建索引不调用 LLM**——`_build_index_from_nodes` 只是 `index_struct.add_node(n)` 把节点放进 `IndexList`（`indices/list/base.py:96–123`，E12 同仓）。⇒ **建索引成本 ≈ 切块成本**；**成本在查询期**（遍历全部节点 + refine 合成，`SummaryIndex` docstring L33–39 明说"query time … iterates through the nodes … synthesizes"）。⇒ 决策含义：**SummaryIndex 不是"预建摘要"，是"查询期全量读"**——正好是 Memoria 想避免的模式。

### R11.3 全量 vs 增量：外部有哪些"建一部分"的成熟做法

| 做法 | 机制 | 成本特征 | 证据 |
|---|---|---|---|
| **按内容哈希缓存、按需建** | repo map 每文件按内容缓存；只用"会话提到的标识符"做 personalization | **零 LLM**；重复会话 0 增量 | E17 |
| **增量插入，不重建** | LightRAG：新文档走同一抽取流程，按实体名 merge/upsert，描述超限才 map-reduce 摘要 | 每次新增 1 次/chunk 抽取调用；无全量重建 | E02/E18 |
| **按目录/子集建索引** | XERJ autoindex 以"文件夹→索引"为单位，每次跑批记录 `files_indexed/junk/wall_seconds` | 建一个子集只付该子集成本 | E13 |
| **分批策展**（模型写索引的场景） | AOCI `aoci_maintain` 按 transport 预算分批返回候选，`remaining≠0` 再继续；`max_entries` 只限单事务 | 每批一次模型创作 + 一次原子写入 | E15/E16 |
| **全量预建**（反面） | GraphRAG 社区摘要、RAPTOR 树 | 一次付全库（281 min/1M tokens） | E01/E04 |

### R11.4 "在这套价格下值不值"——给决策的算式（不是结论）

Memoria 的真账单口径（`artifacts/agent/verify/kg-agent-retrieval/ACCOUNT-2026-10-27.md`）：deepseek-flash 高峰价 = 输入未命中 2.00 元/M、输入命中 0.04 元/M、输出 8.00 元/M；真会话 16 轮 = **1.64 元**。

**一次性全量建索引（抽取式）的粗算**（本文推算，假设每 chunk 输入 ≈600 tok、输出 ≈800 tok 的实体/关系 JSON）：
```
1,011 chunk × (600×2.00 + 800×8.00)/1e6
= 1,011 × (0.0012 + 0.0064) 元
≈ 7.7 元            （全部按未命中输入计，最坏情况）
若 90% 输入命中缓存 ≈ 1,011 × (600×0.04/1e6×0.9 + 600×2.00/1e6×0.1 + 0.0064)
≈ 1,011 × (0.0000216 + 0.00012 + 0.0064) ≈ 6.6 元
```
⇒ **结论（推算，非实测）**：一次性全量抽取 ≠ 天价（**个位数元**，约等于 4–5 次真会话的账单），**真正的成本不是钱，是"质量"与"重写"**：
- 若边界先定错（标题切分），description 全废重写 ⇒ 成本 ×2；
- 若走 AOCI 式验证回环，机器复核与返工占比很高（`maintain` 32/34 返工，E16）；
- 若每次正文改动都全量重建 ⇒ 成本随编辑次数线性增长（这是必须避免的）。
⇒ **建议的时机策略（3 条）**：
1. **懒建**：按章建，`kb_overview` 显式暴露"已索引 4/14 章、未覆盖 61.8% token"（现状问题就是覆盖率不可见）；
2. **按内容哈希增量**：只对 `block_sha256` 变化的 KP 重写 description（这是把 AOCI 的"逐文件哈希"下沉到块级，且不需要 83s 级全库检查）；
3. **先做 1 章 pilot**：用 1 章真实数据量出"每 KP 的 description token 成本 + 人工抽查不合格率"，再决定是否全量——**这一步没有外部数据可替代**。

## R12 质量保证：外部怎么防"机器写的索引不可信"

| 机制 | 具体做法 | 代价 | 证据 |
|---|---|---|---|
| **证据身份绑定** | AOCI：每个候选绑定 `source_sha256` + `candidate_id` + 机器签发批次身份 + CAS；对象身份 `code:<path>`；写入失败可定位到候选 | 每对象一次哈希；机器可全自动校验 | E15 |
| **机器只能校验、不能生成语义** | AOCI `aoci_rules §8`：路径/文件名/扩展名/AST/符号列表/依赖扫描/正则/模板/规则引擎**只能辅助定位、传递、校验、审计、写入**，不能生成/预填 F/R/A/S | 约束了自动化上限（换来可审） | E15 |
| **写入边界与审批阈值** | AOCI `managed_scope.approval_thresholds`：删除 Entry ≥25 条或 ≥25% 需审批 | 阈值可调；防止"模型批量删索引" | E15 |
| **可复核的证据片段** | XERJ 边带 `evidence{quote,source,offset}` + `detector` + `confidence`；每跑批记 `edges_unresolved/ambiguous/capped/self_dropped/invalidated` | 存储可忽略；计数自动产生 | E13 |
| **溯源到原始事件** | Graphiti 每条边带 `episodes`（哪些 episode 产生了这条事实） | 每边多一个 id 列表 | E14 |
| **全量认知校验（防"读错索引"）** | AOCI 的 Challenge/Attestation：读全量索引后必须按 ordinal/对象身份/核心 F 作答，≥80% 正确才算"认知已验证" | **很贵**：`overview` 中位 72.5s + 模型重读全量（13,947 tokens） | E15/E16 |
| **抽样人审比例** | **未找到公开数据**（AOCI 只有删除阈值，XERJ 只有计数） | — | §5.6 |

⇒ 对 Memoria 的移植建议（按性价比排序）：
1. **必须**：每个 description 绑定 `{block_sha256, char_range}`，机器校验"可切片 + hash 匹配 + 非空 + 长度 ≤ 分级预算"（AOCI 的 per-C 预算可直接借用，E15）；
2. **必须**：每次 build/reindex 落盘 run 统计（候选数、失败数、未覆盖 token、平均 description 长度），像 XERJ catalog 那样"质量是被测量的，不是被声称的"（E13）；
3. **应该**：删除/批量重写 KP 描述设审批阈值（学 AOCI 25 条/25%，E15）；
4. **应该**：**不要**把"LLM 写的 description"当唯一事实——`read_kp` 始终返回原文区间，description 只是"索引层"（这与 LlamaIndex 的"metadata vs text"分层一致，E11）；
5. **可选**：2% 随机人审（本文建议值，**无外部数据支持**，用 pilot 阶段定）；
6. **不要**：AOCI 那种"全量 Attestation"（读全索引 + Challenge）用在 KP 索引上——对 470 条 Entry 都要 72.5s 中位，KP 数量级更大时不可行（E16）。

### Phase 1.5 的否决与不确定

- **否决**：用 LLM 决定 KP 边界（GraphRAG/RAPTOR 路线）。冲突点：① 边界错误会让所有下游 description 作废，重写成本=全量（R11.4）；② 外部自证 LLM 抽取质量随 prompt/块大小波动（GraphRAG 自述，600 vs 2400 token 抽取出 ~2 倍差异，E01）；③ AOCI 的边界原则明确"规则只能定位/校验，不能生成语义"（E15）——**边界是结构问题，不是语义问题**。
- **否决**：把 `SummaryIndex` 当"预建摘要索引"。读代码证明它建索引不调用 LLM、查询期遍历全部节点（E12）；它省不了 Memoria 的上下文。
- **不确定**：① "编号层级确定性解析器"的可行性**未在外部找到同类实现**（tree-sitter 有语法，markdown 编号没有语法）——这是**本文的工程建议，无外部对照**；② R11.4 的元级成本是**推算**，pilot 必须实测；③ "每 KP 样本问题"能否显著提升 agent 的"不读判断"**无外部实验**（§5.7）。
