# KG 驱动的 agent 检索：v0 设计（0.5.x）

> **状态**：草案 v2（按 `kg-agent-index-EVIDENCE-E1.md` 三源取证改写）
> **证据规则**：每条技术条款标注证据等级 —— **A** 论文 / **B** 本仓代码(file:line) / **C** 优秀开源(repo+路径+许可) / **D** 语料观测（**不作设计依据**）
> **改版依据**：E1 三源取证（`evidence/E1-papers.md` / `E1-repo.md` / `E1-oss.md`）+ 两次独立复核（`Q1-verify.md` / `Q1-verify-v2.md`）
> **日期**：2026-10-27

---

## 0. 一句话（已按 E1-12 改写）

**索引的价值不是给 agent 一张目录，而是让它少走几个来回。**

这不是修辞，是实测结论：`section` 骨架（373 条 / 2,227 tok）hit@1 55% / hit@3 70%，
而无索引直接 `grep` 是 55% / 70% —— **骨架索引在冷启动不比 grep 更好** `[B+D]`。
所以本案一切围绕「减少往返（iterations）+ 消除错切片」，**而不是「提供索引」**。

> ⚠️ 这条改写很重要：v1 草案的价值主张是"给 agent 目录"，已被 E1 证伪。

---

## 1. 问题定义

### 1.1 现状（B 源，file:line）
```
B1 预算不对称：read_document 2000 行/20,000 字符 + offset/limit；
   section 4000 tok；outline 800；snippet 600；
   ★ read_kp 无任何预算、无 offset/limit（实测 1 个 KP 13,409 字符 ≈ 4,870 tok）
B2 search_kb 硬编码 modes="lexical"（kb.py:248）；RRF 仅 both/full 且 semantic 默认关；
   retrieval_fusion 的 graph 通道【全仓无调用方】⇒ 结构/图谱检索未接线
B3 词法索引只从 knowledge_points[] 建；结果无 line/char_range/snippet/evidence/source_hash
B4 26 篇 md 仅 11 篇有 sidecar ⇒ 覆盖约 46.4% 字节；
   无 sidecar 的文档 search_kb【完全不可见】（只能 grep）
B5 写入非同事务、无失败自检：先原子写正文 → best-effort resync（except: pass）→ sidecar 后写；
   失败只丢计数、不回滚、不校验 range_ok/反转/span=0
```

### 1.2 会话成本（D 源，仅作规模参照）
```
21 轮 / 116 iterations / 135 tool calls
prompt 合计 5,724,271；均值 272,584/轮；峰值 845,926 = 1M 的 84.6%
缓存命中率 94.17%；compaction 8 次（每次压缩后命中率掉到 61–84%）
费用 2.4453 元 = 输出 66.4% + 未命中 24.7% + 命中 8.9%
```

### 1.3 锚点健康（B 源定案，冻结快照 14:09:46）
```
357 KP / range_ok 352 = 98.60% / 坏 5 条（4 missing end.snippet + 1 end_snippet_not_found）
inverted = 0（仅有 1 条 start==end 的 span=0，KP id=test）
★ A1 只改 line_hint 仍 False —— 4/5 坏的 end.snippet 是空串，resolver 根本不调用；
  第 5 条 end snippet 跨行且含 [[\c:yellow|…]] 标记，单行子串永不匹配
```

---

## 2. 设计原则（每条注证据）

```
P1 单一身份：kp_id 是唯一语义身份，不新建第二套 id        【B+C】
   B：FSRS/图谱/引用/会话 anchors 四类消费者全部锚在 kp_id
   C：LlamaIndex id_(uuid4) 与 hash(sha256) 分离是主流；
      LightRAG doc_key=md5(全文) 是"编辑即换身份"的反例
P2 视图分离：切片是 kp_id 的视图（kp_ids[]），slice_id 只做视图键   【B+C】
   C：LlamaIndex ref_doc_info{node_ids} 是同构做法
P3 锚点自证：只有 anchor_verified 的切片才允许进 agent 上下文        【B】
P4 结构不做相关度：结构负责范围/顺序/邻接，相关度交给 lexical/semantic 【C】
   C：HippoRAG(PPR)/GraphRAG(社区摘要)/LightRAG(轮转配额)/XERJ(独立 API)
      无一家用 RRF；RRF 是 rank-only，表达不了邻接与顺序
P5 预算硬约束：任何注入上下文的东西都有 token 上限（Aider 式）       【C】
P6 失效可降级：不确定时退回"读原文 + 标 unverified"，绝不静默使用    【B+C】
P7 价值可证伪：每项收益必须有 A/B（尤其"少往返"）
```

---

## 3. 数据模型（**全部为新增 schema**，B 源确认现网不存在）

```yaml
slice:                        # 全新层，src/ 下 grep slices/char_range/anchor_verified/source_hash 均 0 命中
  slice_id: string            # 视图键，仅缓存/定位，禁止承载语义
  file: string
  section_number: string      # 从标题编号解析
  char_range: [int, int]      # location，每次 build 重算（不是身份）
  identity: sha256            # 块内容身份，只做 stale/dedup/cache
  kp_ids: [string]            # 必须非空（映射孤儿率门禁）
  description: string         # 见 §7，本项目假设，无开源先例
  anchor_verified: bool
  source_hash: sha256
```

**三层定义（B 源实测支撑）**
```
identity  = sha256(file + normalize(text))     ← 14,395 块中 unique 13,260 ⇒ 重复 7.9%，必须 composite
location  = (file, char_start, char_end)       ← 每次 build 重算
anchor    = (section_number, ordinal_in_section, identity)
```

**等价哈希已有但粒度不同**：manifest 每条 md 有 `md_sha256`/`sidecar_sha256`（按文件，非按切片），
且 pending 延迟落盘需走 overlay `[B]`。

---

## 4. 锚点 gate（P0；九处必改见 §12）

### 4.1 三个判据
```
① range_ok == False            → ANCHOR_UNRESOLVED（拒绝返回，不得返回第 1 行）
② 同名 snippet 多候选且无法消歧 → AMBIGUOUS_ANCHOR
③ end 非唯一 / 超预算 / 解析失败 → 夹到下一同级标题；不得留 span=0 或反转
```

### 4.2 消歧手段（按优先级）
```
A heading 结构消歧（同一 section 内）
B 出现序号 + 前文 context_hash
C 仍无法消歧 ⇒ 标 AMBIGUOUS_ANCHOR，不进 agent 上下文
```

### 4.3 写入路径（**高于主流的要求，成本要认**）
```
正文写入 ⇒ 同一事务内重算受影响 range ⇒ 重算后立即自检（range_ok / 反转 / span=0）
```
`[B+C]` C 源显示四家开源同步机制都是"生命周期状态 + 内容哈希 + 可恢复提交点"，**没有一家用单一事务**；
现状代码是 best-effort（`except: pass`）`[B]`。**本要求高于业界常规，实现成本不得按"常规"估。**

### 4.4 A1 修复规格（B 源实测，已可上线）
```
对 end 坏的 KP：夹到下一同级标题 → 取【边界前最后一个非空行】重建 end.snippet + line_hint
实测：5/5 坏 KP 变 ok=True（"数字通信的特点" 110→176 行）
⚠️ 直接用边界空行会【仍失败】—— 必须取"最后一个非空行"  【B】
```

---

## 5. 检索路径

### 5.1 分层预算（硬约束）
```
L0  库概览      ≤300 tok（现状 267）—— 文件清单 + KP 数
L1  单文件索引  ≤800 tok（复用 OUTLINE_MAX_TOKENS）+ cursor
L2  候选切片    ≤4,000 tok
禁止：全库 358 KP 摘要整包（≈21.4k tok）
```
`[C]` 机制参考 Aider：硬预算 + 排序 + ±15% 二分逼近（`repomap.py` L49-70 / L629-706）。
**但 Aider 的 PageRank 依赖代码定义-引用图，中文教材不能照搬排序信号。**

### 5.2 结构的作用位置（不走 RRF）
```
检索前：确定性过滤（章节范围 / section_number 序）
检索后：有界跳数扩展（hops ≤2，超界标 not_shown）
排序：  确定性结构序（章序 / section_number）
融合：  若必须与 lexical/semantic 合并 → 分数加权线性 + 单列 A/B
```
`[C]` 四家实际接法：HippoRAG=PPR 传播；GraphRAG=社区摘要 map-reduce；
LightRAG=按 id 轮转合并+配额截断；XERJ=跳数邻域独立 API。**无一家用 RRF。**

### 5.3 工具结果预算（P1，理由="防峰值"）
```
单次工具结果有 token 上限；超限给 locator-only + 记账
优先收紧 grep（单次最大 34,249 字符，GREP_MAX_MATCHES=250 无 token 预算）  【D】
错误信息永不截断
```

---

## 6. 建索引方法

### 6.1 冷启动 C0–C4（价值主张已按 §0 修正）
```
C0 导入只建 section 骨架（373 条 ≈ 2,227 tok）
   ⚠️ 骨架 hit@3 70% ≈ grep 70% ⇒ 【不指望骨架救命】，它只是免费的结构底图  【B+D】
C1 首问先 grep / read 定位
C2 命中 → lazy 深化该章（建切片 + 写 description）
C3 失败（实测 30–50%）→ 读 top-3 候选章 / 让用户点章 / @file 指路
C4 禁止冷启动按书序建深
```

### 6.2 深化顺序（有信号时）
```
score = 3×复习卡 + 2×会话读 + 1×批注 → argmax
证据：复习卡 cards.json 的 file 字段与实际使用 top 章 2/2 一致  【D，仅作信号有效性参考】
全 0 → 回退书序（仅兜底）
```

### 6.3 切分规则
```
① section_number 给语义边界（标题比块稳定：编辑后 section 数不变）  【B】
② 块 identity 给精确边界与缓存键（改一行只改 1 块；但 7.9% 块 hash 重复 ⇒ composite）  【B】
③ 单元 >3,000 tok 先按下级编号拆、再按块边界拆（保留 1 块重叠）
④ 不切公式块/表格块（3,557 纯公式块 / 984 图片块只作附件）  【D】
⑤ 无编号文件退化为 page 模式
```

### 6.4 增量与失效（可搬机制）
```
hash 驱动增量：hash 变才 delete+重加，未变跳过  【C】LlamaIndex ingestion/pipeline.py L242-259, L451-536
文档级 ref_doc + 级联删除（防悬挂切片）        【C】keyval_docstore.py L93-125, L557-598
⚠️ 依赖稳定 doc id；删除分步、非事务
```

### 6.5 本方案不采用的两个主流做法
```
❌ 层次摘要树（RAPTOR 式）
   【A】受控对照仅 +1.6~1.7 点；headline 82.6% 混了 GPT-4；摘要 4% 幻觉
   【C】LightRAG 摘要会因 token 上限被截断并持久化（专门记账）⇒ 摘要不是可靠"可判性"来源
❌ 语义切分
   【A】NAACL 2025 Findings（arXiv:2410.13070）：真实文档上固定切分不差
   ⚠️ 该文【未量化成本】，只给定性断言 —— 不得引用成"已测算成本收益"
✅ 可选替代：AutoMerging 按命中比例回填父块（ratio>0.5，无 LLM 摘要，无幻觉）
   【C】auto_merging_retriever.py L39, L87-90, L186-194；缺点：自身无 token 预算，需配 §5.1
```

---

## 7. description 规范（**本项目假设，无开源先例**）

```
必填 description（机器读）：
  · 问句型，≤80 汉字
  · 含：回答什么问题 / 判别关键词 / 【何时不该读】
  · 写成【可比较】的（"与 X 的区别是…"），不是流水摘要
  · 禁止：截正文前 N 字
实测（D 源，仅作本项目初步证据）：截原文 hit@3 53.8%→38.5%；改写问句型 → 76.9%
```
`[C]` **开源无"可判性摘要"字段**：最近替身是 metadata 任意 KV（可排除注入）/ LightRAG description（LLM 摘要，截断）/ AOCI F+S（S 仅 3.6% 填写）。
⇒ 本条款只能标**本项目假设**，须 A/B 自测，**不得声称业界做法**。

可选 `note`（人读）：可空、不阻塞落盘、不参与机器判据；落盘率与 description 分开计。

---

## 8. 验收

### 8.1 门禁（确定性、全量、可复跑）
```
M4 锚点健康      fresh ≥99%；inverted = 0；anchor_verified 覆盖率（基线 98.60% / 5 坏）
M5 陈旧          增量 = 0；静默坏 = 0
M2 有害误路由    = 0（同名碰撞必须消歧；风险基线 77.6% / 32 组 102 条  【D】）
M12（新增）      索引上线后 Δhit ≥ −5pp（不得破坏前缀缓存）
```
**待裁口径（不钉死则门禁不可执行）**
```
口径① 孤儿率分母：切片→KP 还是 KP→切片？scope = KP 覆盖的 section / 整文件 / 全库
       （三种 scope 下结果差异巨大，见 D 源观测）
口径② anchor 覆盖率时点与消歧定义：当前值 98.60% 还是 A1 修复后？
       "可消歧" = section 内 还是 全文唯一？
```

### 8.2 观测（不作通过门槛）
```
P0 观测  峰值 prompt（基线 845,926 = 1M 的 84.6%）
P1 观测  iters/answer（116/21 = 5.524）、tool calls（135）、compaction（8）、单次工具结果 max（34,249 字符）
```

### 8.3 已废弃的门禁（不得复活）
```
M1 hit@3 ≥70%     n=13 时 Wilson95=[49.7,91.8] ⇒ 不可证（需 n≥158）→ 降 smoke
M3 可判性 ≥85%    n=20 时 C=0 上界 16.1% ⇒ 不可证（需 n≥230）→ 降 smoke
iterations 作主 KPI  证据为算术外推，非测量 → 候选，需三臂实验
```

### 8.4 判决性 A/B（必须有 Arm-1 对照）
```
Arm-0 现状（grep + read_document）
Arm-1 只注入索引 token 但不改行为 ← 分离"token 成本"与"行为收益"
Arm-2 索引驱动（L0→L2 + anchor gate + description）
判据：Arm-2 vs Arm-0 —— iters 降 且 答对率不降；Arm-1 用于归因
```

---

## 9. 不做（明确边界，均有证据）

```
· GraphRAG 全局检索        机制不匹配（97.5% 读同一章）      【D+外部】
· RAPTOR 递归摘要树        受控增益 +1.6~1.7、4% 幻觉        【A+C】
· Self-RAG / Adaptive-RAG  需训练管线                        【A】
· 语义切分                 成本未被证明值得                    【A，且原文未量化】
· 新建第二套语义 id        稳定 id 与 hash 分离是主流          【B+C】
· 以"提高缓存命中率"为目标  已 94.17%；改 Δhit ≥ −5pp 否决条件  【D】
· 搬 AOCI 完整重写回环     可搬：证据身份/哈希基线/软失效        【C】
· 把 M1/M3 小样本阈值当门禁 统计上不可证                       【A/D】
· LLM 摘要作 description 主干 不适用（无先例 + 截断不可靠）     【C】
```

---

## 10. 待用户确认（R7）

| # | 事项 | 影响 |
|---|---|---|
| 7.1 | KP 边界会被重算（教材 69% KP >1200 字需切开）`[D，仅作规模参考]` | 用户可见的知识点边界变化（id 不变） |
| 7.2 | sidecar 增加 description / note 字段（已有 description 字段，大库为 0） | 用户数据文件结构变化 |
| 7.3 | **价值主张改为「省往返」**（已按 E1-12 在 §0 改写） | 版本目标与验收口径 |
| 7.4 | 索引构建时机（C0–C4） | 首次使用体验与 token 花费 |
| 7.5 | 新增 `step/usage` 埋点 | 把 iteration 成本从算术变实测 |

---

## 11. 未决 unknowns

```
U1 anchor_verified 覆盖率（当前 98.60%；A1 修复后待测；若 <50% 需先建重建管线）
U2 KP→切片 映射孤儿率（阈值 20%，但口径①未裁）
U3 Arm-2 vs Arm-0 的 iters A/B（价值主张的判决实验）
U4 description 落盘率能否 ≥70%（大库 0/357；机制在 Vocab 可用 25/134）
U5 同名碰撞消歧方案（77.6% 风险，32 组 102 条）
U6 note 填写率与作者负担
U7 Δhit 实测（索引更新对前缀缓存影响；外部无公开研究）
U8 冷启动 C0–C4 的首次提问质量
```

---

## 12. 十二处必改（相对 v1 草案，B 源定案）

| # | v1 草案 | v2 修正 |
|---|---|---|
| M1 | §4.1 判据① 要求 range_ok=False 拒返 | 代码 `start_line or 1` **静默返回第 1 行** `kb.py:349-351` ⇒ 先修代码或同批上线 |
| M2 | 判据② AMBIGUOUS_ANCHOR | **无实现**；locator 多候选从不拒绝 `range/locator.py:33-64` |
| M3 | 判据③ anchor_verified | 字段**不存在**；解析失败静默回退 line_hint |
| M4 | §4.3 同事务重算 | 现状 best-effort `except: pass` `document.py:373-380` ⇒ **代码明确违反设计** |
| M5 | §3.2 slice schema | 六个字段**后端全不存在** ⇒ 标新增 schema、成本重估 |
| M6 | §5.2 结构检索 | graph 通道**全仓无调用方**；both/full 代码等价 |
| M7 | §6.1 冷启动 | 46.4% 字节无 sidecar ⇒ search_kb **看不见**；须把"无 sidecar 文档"纳入设计 |
| M8 | §7 description | sidecar 已有 description（大库 0）；另有 aliases/tag_candidates/alias_candidates/description_candidates/weight |
| M9 | §8 验收 | `kg-ontology-v0.md:156` 禁用长度/行数/块数作判据 ⇒ 不得用"单元多大"作通过线 |
| M10 | §0 价值主张 | 骨架 ≈ grep ⇒ 改为「省往返」（已改） |
| M11 | §6 切分理由 | 改为「可逆 + 不破坏身份 + hash 增量」，**不是**"更小更好"（已改） |
| M12 | §4.4 A1 规格 | 新增：取"边界前最后一个非空行"重建 end.snippet（实测 5/5 ok） |

---

## 13. 证伪条件（设计失败长什么样）

```
F1 Arm-2 的 iters 不比 Arm-0 低 ⇒ 放弃索引路线，退回"工具结果预算 + 检索栈能力暴露"
F2 答对率下降 ⇒ 立即回滚
F3 anchor_verified 覆盖率 <50% ⇒ 锚点重建成为独立大工程，索引延后
F4 description 落盘率长期 <70% ⇒ 索引退化为纯结构骨架（价值大幅缩水）
F5 Δhit 跌破 −5pp ⇒ 索引不得进前缀，只能经工具结果
F6 description 的 hit@3 提升无法复现（D 源仅一次小样本）⇒ §7 条款作废
```
