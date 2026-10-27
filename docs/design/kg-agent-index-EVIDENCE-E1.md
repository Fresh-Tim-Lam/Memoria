# EVIDENCE-E1 —— 三源取证合并（索引单元与身份）

> **用途**：判定每个设计主张的证据等级，只让「A/B/C 至少两源」者进设计条款。
> **三源**：A=论文 / B=本仓代码(file:line) / C=优秀开源(repo+路径+许可) / D=语料观测（**不可作设计依据**）
> **取证产物**：`evidence/E1-papers.md`（296 行）/ `evidence/E1-repo.md`（243 行）/ `evidence/E1-oss.md`（385 行）
> **日期**：2026-10-27 · **Lead 汇总**

---

## 1. 结论速览

| # | 设计主张 | 证据 | 判定 |
|---|---|---|---|
| E1-1 | **身份用稳定 id，内容哈希只做 stale/dedup** | B + C（+A 相邻类比） | ✅ **可写进设计**（三源级） |
| E1-2 | 切片作**派生视图**、可删可重建、不承载语义 | B + C（LlamaIndex `ref_doc_info{node_ids}` 同构） | ✅ 可写进设计 |
| E1-3 | **切得更小更好** | 无（E08 变量错配 / E09 未测 heading / SentenceWindow 方向相反） | ❌ **只能标经验判断**，且必须删掉"更小"这个理由 |
| E1-4 | description 作「可判性摘要」字段 | 无开源先例（最近=metadata KV / LightRAG desc / AOCI F+S） | ⚠️ 仅 D + 经验判断；**不得声称业界做法** |
| E1-5 | 同步 = 生命周期状态 + 内容哈希 + 可恢复提交点 | B + C（四家一致，**无单一事务**） | ✅ 可写进设计；但"同事务"是**高于主流**的要求，成本按此重估 |
| E1-6 | token 硬预算 + 排序 + 二分逼近 | C（Aider `repomap.py` L49-70/L629-706） | ✅ 机制可搬；排序信号不可照搬 |
| E1-7 | 锚点 = id + 内容哈希 + 字符偏移（行号只作显示） | B + C（LlamaIndex `start_char_idx/end_char_idx`） | ✅ 可写进设计 |
| E1-8 | 结构/图谱检索不该走 RRF | C（HippoRAG PPR / GraphRAG 社区摘要 / LightRAG 轮转配额 / XERJ 独立 API —— 无一家用 RRF） | ✅ 可写进设计 |
| E1-9 | 层次摘要（RAPTOR 式）作索引主线 | A（受控增益仅 +1.6~1.7，摘要 4% 幻觉）+ C（LightRAG 摘要被 token 上限截断） | ✅ **否决有据** |
| E1-10 | 语义切分更优 | A（NAACL 2025 Findings：真实文档上固定切分不差；**原文未量化成本**） | ✅ 否决有据；但**不得引用成"已测算成本"** |
| E1-11 | A1（只修 end）后 gate 可上线 | B（产品 `resolve_range` 实测 5/5 坏 KP 变 ok=True） | ✅ 可写；**必须写明取"边界前最后一个非空行"** |
| E1-12 | 冷启动靠骨架索引定位章节 | B + D（section 骨架 hit@3 70% ≈ grep 70%） | ❌ 骨架不比 grep 好 ⇒ **价值主张须改写为"省往返"** |

---

## 2. 三条「不能声称」的边界（A/B/C 源共同划出）

```text
① 不能声称「更小的索引单元被研究证明更好」
   E08 arXiv:2409.01666 的倒 U，自变量是【检索返回的 chunk 数 k】而非单元大小
   E09 arXiv:2410.13070 只对比 semantic vs fixed-size，未测 heading 结构
   LlamaIndex SentenceWindow = 「匹配小 / 阅读大」，与「读更小切片」方向相反

② 不能声称「业界都有可判性摘要字段」
   四家开源（LlamaIndex/LightRAG/LangChain/Aider）均无此字段
   最近替身：metadata 任意 KV（可排除注入）/ LightRAG description（LLM 摘要，截断且不可靠）/ AOCI F+S（S 仅 3.6% 填写）

③ 不能声称「我们的锚点方案是主流成熟做法」
   未找到任何开源实现做到「chunk id 在编辑后仍稳定」
   ⇒ 我们比主流更进一步，既是优势也是风险（无现成实现可抄）
```

---

## 3. 可直接落地的机制（C 源，带出处）

| 机制 | 出处 | 我们的用法 |
|---|---|---|
| 稳定 id 与内容哈希**分两个字段** | LlamaIndex `schema.py` L275-277（`id_`=uuid4）vs L800-803（`hash`=sha256） | `kp_id`（稳定）+ `identity`（sha256，仅 stale/dedup） |
| 文档级 `ref_doc_info{node_ids}` + 级联删除 | `keyval_docstore.py` L93-125, L557-598；`vector_store/base.py` L423-431 | 重建/删除以「文档」为单位，防悬挂切片 |
| hash 驱动增量（变才 delete+重加） | `ingestion/pipeline.py` L242-259, L451-536 | 块级 hash 增量重算 |
| **AutoMerging 按命中比例回填父块（无 LLM）** | `auto_merging_retriever.py` L39, L87-90, L186-194（ratio>0.5） | 替代 RAPTOR：便宜、无幻觉；需自配 token 预算 |
| 硬 token 预算 + 二分逼近（±15%） | Aider `repomap.py` L49-70, L629-706 | L2 候选切片的预算控制 |
| 分项配额截断 | LightRAG（6000/8000/30000） | 分通道预算 |

**明确不搬**：内容哈希当唯一身份（LightRAG `lightrag.py` L2442-2445 反例）/ LlamaIndex 默认 uuid4 直接用（不补稳定 doc id 会重复入库）/ LLM 摘要树当索引主线 / XERJ 内部机制（闭源）/ AOCI 实现（无源码无许可）。

---

## 4. B 源定案的三处对账（不再有争议）

```text
① KP 健康基线 = 357 / 98.60% / 5 坏（冻结快照 14:09:46，11 sidecar sha256 全等）
   358 只在 live 探针出现；98.9%=只算 start 端；「8 坏」混三种口径；inverted=0（1 条 span=0 是 test）
② A1 只改 line_hint 仍 False —— 4/5 坏的 end.snippet 是空串（resolver 不调用），
   1 条 end snippet 跨行+含高亮标记，单行子串永不匹配
③ slices[]/source_hash/char_range/anchor_verified/section_number 在 src/ 下 0 命中 ⇒ 全新 schema
   等价哈希在 manifest（md_sha256/sidecar_sha256），按文件非按切片
```

---

## 5. B 源五条现状硬事实（file:line）

```
B1 预算不对称：read_document 2000 行/20k 字符+offset/limit；section 4000tok；outline 800；snippet 600；
   read_kp 无任何预算（实测 1 个 KP 13,409 字符 ≈ 4,870 tok）
B2 search_kb 硬编码 modes="lexical"（kb.py:248）；RRF 仅 both/full 且 semantic 默认关；
   retrieval_fusion 的 graph 通道【全仓无调用方】⇒ 结构检索未接线
B3 词法索引只从 knowledge_points[] 建；结果无 line/char_range/snippet/evidence/source_hash
B4 26 篇 md 仅 11 篇有 sidecar ⇒ 覆盖约 46.4% 字节；无 sidecar 的文档 search_kb【不可见】
B5 写入非同事务、无失败自检：先写正文 → best-effort resync（except: pass）→ sidecar 后写
```

---

## 6. 必须改写的两条设计依据

```text
① 切片方案的理由（E1-3）
   改成：选切片是因为【可逆 + 不破坏身份 + 能做 hash 增量】，
        不是因为「更小单元被证明更好」
   影响：kg-agent-index-v0.md §6 / 设计论证节

② 索引的价值主张（E1-12）
   section 骨架 hit@3 70% ≈ grep 70% ⇒ 骨架索引在冷启动不比 grep 好
   改成：价值 = 【让 agent 少走几个来回】，判决指标 = iterations + 错切片率
   影响：kg-agent-index-v0.md §0 / §5
```

---

## 7. 证据盲区（保持未知，不许填补）

```
· 中文 / 公式密集 / 图文混排教材的切分证据：A 源几乎空白
· RAG 索引 id 在编辑/移动/重命名后的解析成功率：未找到公开数据（含开源实现）
· 本仓规模（个人教材库）上 fixed vs semantic vs structure-aware 的成本收益：A 源无同规模数据
· XERJ 内部算法/segment 格式/WAL 恢复；AOCI 源码/许可/maintain 候选生成：均未取到
· 所有 OSS 的实测性能/成本：C 源未跑代码，报告里"代价"是结构性代价，非 benchmark
```

---

## 8. 结论

```text
✅ E1 可关闭：身份问题（E1-1）拿到 B+C 两源，是本轮最重要的升级
✅ 否决项（E1-9 摘要树 / E1-10 语义切分）有 A+C 两源支撑，可写进"不做什么"
❌ 两条必须改写（E1-3 切片理由 / E1-12 价值主张），否则会被当成已证事实
⚠️ description 字段（E1-4）无开源先例 —— 只能作为本项目假设，须 A/B 自测
⚠️ 「同事务重算」高于主流 —— 成本要认，不能按"业界常规"估算
```
