# E1 取证结论与设计修正清单

> **用途**：`kg-agent-index-v0.md` 草案的证据分级与必改项。
> **来源**：研讨会重启后三源取证（A 论文 / B 本仓代码 / C 优秀开源）。
> **状态**：B 源已定；A 源已定；C 源在跑。
> **日期**：2026-10-27

---

## 0. 证据分级规则（人 2026-10-27 定）

| 级 | 来源 | 可否作设计依据 |
|---|---|---|
| **A** | 论文（URL/arXiv） | 可以，但须给适用边界与反驳条件 |
| **B** | 本仓代码（file:line） | 可以 |
| **C** | 优秀开源（repo+路径+许可） | 可以 |
| **D** | 语料观测（AAA_Courses） | **不可**。只能作「数据现实 / 迁移成本」，必须标 `【D】` |

**判据**：设计主张须 A/B/C 至少两源；仅 D 源 ⇒ 记「经验判断」，不得进决策包。

---

## 1. B 源已定案的三处对账（此前长期悬空）

### 1.1 KP 健康基线：**357 / 98.60% / 5 坏** 是唯一正确值
```
· 358 只出现在 live 探针 anchor_stats.json，冻结快照（14:09:46，11 sidecar sha256 全等）不可复现
· 98.9% = 354/358 只算 start 端 hint；代码 range_ok 要求 start+end 双端成功 ⇒ 352/357 = 98.60%
· 「8 坏」混三种口径：4 start-ambiguous + 2 end-ambiguous + 1 not_found + 1 degenerate
· 代码口径坏 = 5：4 missing end.snippet + 1 end_snippet_not_found
· 「1 条 range 反转」不实：inverted = 0；只有 1 条 start==end 的 span=0（KP id=test）
```

### 1.2 A1（只修 end）**单独不够**
```
· 4/5 坏 KP 的 end.snippet 是【空串】⇒ kp_resolver.py:17-20 根本不调 resolve_range（恒 missing_snippet）
· 第 5 条「数字通信的特点」的 end snippet 是 80 字符截断文本，正文已拆成 3 行并插入 [[\c:yellow|…]]，
  locator 只做单行子串 ⇒ hint 改 1/110/208 仍 end_snippet_not_found
⇒ A1 必须包含【重写 end.snippet】，否则 gate 上线后这 5 条依旧不可用
```

### 1.3 `slices[]` / `source_hash` / `char_range` / `anchor_verified` / `section_number`
```
grep 在 src/ 下【0 命中】⇒ 全部是【新增 schema】，不是"接出现有字段"
⇒ 设计 §3.2 的 slice schema 成本被低估；C 方案在原估算上要加 schema 设计与落地
等价哈希存在但粒度不同：manifest 每条 md 有 md_sha256 / sidecar_sha256（按文件，非按切片），
且 pending 延迟落盘需走 overlay
```

---

## 2. B 源的五条现状硬事实（file:line，可直接引用）

| # | 事实 | 出处 |
|---|---|---|
| B1 | 读取预算不对称：`read_document` 2000 行/20,000 字符 + offset/limit；`section` 4000 tok；`outline` 800；`snippet` 600；**`read_kp` 无任何预算、无 offset/limit**（实测 1 个 KP 13,409 字符 ≈ 4,870 tok） | `tools/kb.py:66,992,1083-1094`；`section_index.py:51-56` |
| B2 | `search_kb` 硬编码 `modes="lexical"`；RRF 仅 both/full 且 semantic 默认关；`retrieval_fusion` 的 graph 通道**全仓无调用方** ⇒ 结构/图谱检索未接线 | `tools/kb.py:248`；`search_kernel.py:58-61,103-123`；`retrieval_fusion.py:145-161`；`embedding_provider.py:50-51` |
| B3 | 词法索引**只从 `knowledge_points[]` 建**；结果字段仅 `{kp_id,id,label,name,file,score,lexical_score,sources}`，**无 line/char_range/snippet/evidence/source_hash**；行号靠 `search_kb` 二次解析 | `lexical_index.py:163-190,591-600`；`tools/kb.py:265-288` |
| B4 | **26 篇 md 仅 11 篇有 sidecar ⇒ 覆盖约 46.4% 字节**；无 sidecar 的文档 `search_kb` **完全不可见**（只能 grep） | 探针 §2 |
| B5 | **写入非同事务、无失败自检**：先原子写正文 → best-effort `_resync_kp_ranges_after_edit`（`except: pass`）→ sidecar 后写；失败只丢计数、不回滚、不校验 range_ok/反转/span=0 | `document.py:341-349,373-380,476-477`；`body_edit.py:322-358` |

**附：KP 尺寸真值（n=352）** `p50 = 16 行 / 527 字 / 186 tok`；`p90 = 75 行 / 2,919 字 / 982 tok`；`max = 469 行 / 18,199 字 / 6,006 tok`；`>1200 字占 23.9%`

---

## 3. A 源已定的证据边界（**不能引用成什么**）

| 常被误用的说法 | 实际 |
|---|---|
| 「语义切分成本不划算，已测算」 | Qu/Tu/Bao, NAACL 2025 Findings（arXiv:2410.13070）**只给定性断言，未量化成本** |
| 「RAPTOR 82.6%」 | 那是 RAPTOR+GPT-4 的混合 headline；同 reader 受控对照仅 **+1.6~1.7 点**；摘要 **4% 幻觉**（6/150 节点） |
| 「GraphRAG 证明图有增量价值」 | 原论文**未证明**：相对「无图的全局文本摘要」多数指标不显著；directness 输给向量 RAG；1M token 索引 281 分钟 |
| 「有研究支持知识点的稳定身份」 | RAG 场景**无公开实证**；相邻证据 = reference rot（1/5 STM 文章）+ Trusty URI「内容哈希=一改就换身份」张力 + W3C Annotation 三层锚定 |

### 可以引的（有数字、有边界）
```
· DenseX（EMNLP 2024, arXiv:2312.06648）：更细自包含单元在【等 token 预算】下
  Recall@20 +10.1（无监督）/ +2.7（有监督）；代价：索引约 6.3 倍、需 propositionizer、多跳任务失败
· late chunking（arXiv:2409.04701）：nDCG@10 +1.5~1.9；
  但【只改 embedding 上下文，不改 chunk 边界/身份】——解决不了锚点问题
```

### 证据盲区（恰是我们的主场景）
```
· 中文 / 公式密集 / 图文混排教材的切分：A 源几乎空白
· RAG 索引 ID 在编辑/移动/重命名后的解析成功率：未找到公开数据
· "知识点作为稳定身份"：无直接论文
⇒ 这三块只能靠 B 源实测 + C 源开源实践，不得声称"有研究支撑"
```

---

## 4. 设计草案必改项（B 源已定，可立即改）

| # | 草案位置 | 现状问题 | 改法 |
|---|---|---|---|
| M1 | §4.1 判据① | 草案要求 `range_ok=False → 拒绝返回`，但代码 `start_line or 1` **静默返回第 1 行**（`kb.py:349-351`）= C1 冲突 | 先修代码再上线 gate；或 gate 与代码修复同批 |
| M2 | §4.1 判据② | `AMBIGUOUS_ANCHOR` **无实现**；locator 多候选从不拒绝（`range/locator.py:33-64`） | 需新增判定与消歧；写进实现任务 |
| M3 | §4.1 判据③ | `anchor_verified` 字段**不存在**；`read_document`/`search_kb` 解析失败静默回退 `line_hint` | 新增字段 + 回退路径改造 |
| M4 | §4.3 同事务重算 | 现状 best-effort `except: pass`（`document.py:373-380`）= C4 冲突（**代码明确违反设计**） | 必须实现事务化 + 重算后自检 |
| M5 | §3.2 slice schema | `char_range/identity/kp_ids/description/anchor_verified/source_hash` 后端**全不存在** | 标为新增 schema，成本重估 |
| M6 | §5.2 结构检索 | graph 通道**全仓无调用方**；both/full 代码等价 | R3 结论不变（结构不走 RRF），但"已接线"的前提不成立 |
| M7 | §6.1 冷启动 | 46.4% 字节无 sidecar ⇒ `search_kb` **看不见**，只能 grep | 冷启动方案必须把"无 sidecar 文档"纳入设计（否则索引天然覆盖不全） |
| M8 | §7 description | sidecar 已有 `description` 字段（大库为 0）；另有 `aliases/tag_candidates/alias_candidates/description_candidates/weight` | 字段落盘路径要写清"写哪个字段、谁写、何时写" |
| M9 | §8 验收 | `kg-ontology-v0.md:156` 禁用「长度/行数/块数」作判据 | 验收不得用"单元多大"作通过/否决线；可用作预算/截断（代码正是这么用的） |

---

## 5. E1 当前结论（B 源支撑，无需等 C 源）

```text
✅ kp_id 作身份成立 —— 它是代码里【唯一】现状身份（FSRS/图谱/引用/会话 anchors 均锚在它）
❌ kp.range 作「可注入内容边界」目前【不成立】——
   无 gate / 无自检 / 无预算 / 歧义从不拒绝 / A1 单独不够 / 写入非同事务
⇒ 设计 §4 与 §7 必须先按 M1–M9 修正，再谈冻结
```

## 6. 待 C 源补齐
```
· C 源（优秀开源）在跑：LlamaIndex NodeParser/SentenceWindow/Hierarchical、LightRAG 字段与合并、
  GraphRAG 社区摘要、HippoRAG PPR、XERJ 双时态边、AOCI F/R/A/S
· 补齐后：EVIDENCE-E1.md 汇总三源，逐条标级，再修设计文档
```
