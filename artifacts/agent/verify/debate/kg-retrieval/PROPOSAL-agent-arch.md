# C 方提案：agent 检索路径、索引预算与"省轮次"论证

> **角色**：C 方（agent 检索 / 推理 / token 经济）｜**任务**：`task-195`（Phase 1 独立提案）
> **日期**：2026-10-27
> **独立性**：Phase 1 窗口内**未读** `PROPOSAL-arch-contract.md` / `PROPOSAL-todo-owner.md` / `PROPOSAL-metrics-baseline.md`（`unread_declared`，仅见过目录名）；未与任何一方讨论。`read_set` 见 §8。
> **证据身份**：全部按 `ev:file:<path>#L<n>` / `ev:paper:<url>` / `ev:bench:<id>`（bench 原始产物路径见 §8）。

---

## 1. 结论摘要（先给答案）

1. **read_kp 用得少（6 vs 37）不是模型不会用，而是 ID 不可见 + 粒度不匹配**：read_document / search_kb 的正文只给 `文件:行号 名称`，**从不给 kp_id**；`anchors` 里的 `kp_id` 不进入模型消息。**改一处即可**：在这两处输出里露出 `kp_id`（0 schema 变更），并把 read_kp 描述改成"id 来自 read_document/search_kb 输出"。
2. **轮次/迭代确实比 prompt token 更值钱**（实测计价）：输出占 **66.75%** 费用；省 1 个 iteration/轮 ≈ **−20.5%** 总费用，而把 prompt 砍半只 **−16.63%**；prompt 全部归零的上限也只有 **33.25%**。
3. 因此索引产品的验收主指标应是 **iterations/answer 与答对率**，prompt token 是"防爆/防 Lost-in-Middle"的次指标；只报"省 token"的 A/B 会低估或错估收益。
4. 索引**不是**新检索器：应作为现有 RRF 融合的第 3 条通道（`retrieval_fusion` 已有 Graph 占位通道），并承担 **L0/L1 方向感（routing）**；lexical 保留（精确公式/行级问题仍靠它）。
5. 索引预算必须**工具侧硬约束 + 游标分页**：全库 357 KP × description 绝不能整包注入（≈2 万 token，且被放大 ~10×）；L0 ≤300 tok、L1 单文件 ≤800 tok（复用 `OUTLINE_MAX_TOKENS` 口径）、单次读取 ≤1.5k tok（`snippet` 600 / `section` 4000 已有上限）。
6. `description` 0/357 是**最大风险**：它决定"可判性"；写不好，索引只是又一层噪声。给出可判模板与判据（§3 R2）。
7. 索引的**真实收益路径**：减少"猜文件 → grep → 读大段 → 再读"的探索轮（本会话 37 次 read_document 中 36 次同一章），而不是让每条工具结果更短。
8. 两条 dev-only/未知项已登记（§5/§6），并有 falsifier 可推翻本提案（§7）。

---

## 2. 必答问题 1：read_kp 用了 6 次 vs read_document 37 次 —— 原因与"改一处"

### 2.1 先摆事实（本会话）

| 工具 | 次数 | 结果 token | 平均/次 | 备注 |
|---|---:|---:|---:|---|
| read_document | **37** | 33,458 | 904 | 36/37 次是同一章（`教材/03_第3章_模拟信号的数字编码.md`） |
| grep | 28 | 24,018 | 858 | **单次最大 34,249 字符 ≈ 9.8K tok**（compaction/prune 记录 chars_before=34,249） |
| snippet | 11 | 1,427 | 130 | 行级窗口，便宜 |
| search_kb | 7 | 2,025 | 289 | 1/7 未命中；6/7 命中 |
| **read_kp** | **6** | 8,589 | 1,431 | **全部发生在 turn 7–9（写笔记/建 KP 阶段）**；回答问题的 16 轮里 **0 次** |
| outline | 3 | 945 | 315 | 方向感工具，便宜 |
| kb_overview | 2 | 534 | 267 | 只有文件清单 + 每文件 KP 数 |

来源：`ev:bench:kg-retrieval-session-analysis`（`scripts/session-analysis.json`，解析同一真实会话 `session-20261027T011706Z-0cb419b6.jsonl`）；会话基础账单见 `ev:file:artifacts/agent/verify/kg-agent-retrieval/ACCOUNT-2026-10-27.md`。

### 2.2 原因 A（主因）：**kp_id 对模型不可见**

- `read_document` 的知识点清单只输出 `- 文件:行号 名称`：`ev:file:src/memoria/services/agent/tools/kb.py#L318`；
- `search_kb` 的命中行只输出 `序号. 文件:行号 名称（score）`：`ev:file:src/memoria/services/agent/tools/kb.py#L276-L278`；
- `kb_overview` 只回文件清单 + 每文件 KP 数，**无 id、无名称**：`ev:file:src/memoria/services/agent/tools/kb.py#L625-L635`；
- `read_kp` 的 schema **只接受 id**（无 name/path 入口），且描述没说 id 从哪来：`ev:file:src/memoria/services/agent/tools/kb.py#L614-L622`；
- 工具结果里的 `anchors`（含 `kp_id`）**不会发给模型**：loop 只把 `result.content` 追加为 tool 消息，anchors 仅用于引用汇总（`ev:file:src/memoria/services/agent/loop.py#L367-L370`，anchors 读取在 `#L290`、写入事件在 `#L385`）。
- **实证**：本会话首次 read_kp 在 seq 236，而 id 第一次出现在模型可读文本里是 seq 212 的 **grep** 结果（pattern 直接猜 sidecar 格式 `- id: (...)`；grep 允许 `.memoria/**`，`ev:file:src/memoria/services/agent/tools/kb.py#L995`）。即采用路径是：**先知道内部 sidecar 格式 → 猜模式 → grep 出 id → 才敢调 read_kp**。见 `ev:bench:kg-retrieval-kp-id-trace`（`scripts/trace_kp_id_visibility.py` 输出：5 个 id 首次可读出现均在 seq 212/222 的 grep 结果）。

> 这解释了一个反直觉现象：**6 次 read_kp 全部在"写笔记"轮**——那几轮 agent 自己刚 propose_write 过 sidecar，知道 id 命名；而**回答问题的 16 轮一次也没用**，因为它没有合法的 id 获取路径。

### 2.3 原因 B：**粒度不匹配（read_kp 太粗）**

- `read_kp` 返回**整个 KP 正文**（start_line–end_line）：`ev:file:src/memoria/services/agent/tools/kb.py#L344-L369`；
- 真实 KP 粒度（357 条，本库实测）：p50 **523 字符 ≈ 149 tok**，p90 **2,887 字符 ≈ 825 tok**，p99 **12,119 字符 ≈ 3,463 tok**，max **18,198 字符 ≈ 5,199 tok**（`ev:bench:kg-retrieval-kb-granularity`，`scripts/kb-granularity.json`）；
- 而本会话 read_kp 平均结果 **1,431 tok/次**（6 次 8,589 tok）——因为被读的正是大 KP（`uniform-quantization` 439–604 行、`bandpass-sampling` 202–293 行等）；
- 用户问题里有 **2/19 是行级定位**（`@教材/03...#L499`、`#L675C1-L675C85`），需要的是 **±20 行窗口**而不是整节 1.3k–3.7k tok；`read_document` 的 `offset/limit`（`ev:file:...kb.py#L586-L611`）与 `snippet` 的 ±ctx（`ev:file:...kb.py#L951-L969`）天然更合适。

⇒ **两个原因叠加**：回答问题时要么不知道 id（A），要么知道了也太贵/太粗（B），于是默认退回到 `read_document + grep`。

### 2.4 "改一处就能提升采用率"的具体点

**最小改动（推荐，0 schema）**：在 `read_document` 的知识点清单行与 `search_kb` 命中行里露出 `[kp_id]`，并把 `read_kp` 描述补齐来源：

```diff
- kp_rows.append(f"- {location}  {name}")                       # kb.py#L318
+ kp_rows.append(f"- {location}  [{kp_id}]  {name}")

- rows.append(f"{index}. {location}  {name}（score={hit.get('score')}）")   # kb.py#L276
+ rows.append(f"{index}. {location}  [{kp_id}]  {name}（score={hit.get('score')}）")

- description="按知识点 id 读取该知识点的正文片段与元数据（带 `文件:行号`）。"   # kb.py#L615
+ description=("按知识点 id 读取该知识点正文与元数据（带 `文件:行号`）。"
+              "id 可直接用 read_document 知识点清单 / search_kb 命中行里 `[id]` 的值。")
```

这一改动的收益可**独立测量**（见 §7 falsifier F3）：read_kp 采用率、read_document 次数、单问题迭代数。

**第二改动（若采用率仍低，则说明是粒度问题）**：`read_kp` 增加 `offset_lines/limit_lines`（或 `near_line`），默认返回整 KP 但允许取窗口——复用 `section` 的切片逻辑（`ev:file:src/memoria/services/agent/section_index.py#L51-L56` 有预算常量与切片机制）。

---

## 3. 必答问题 2：轮次数是不是比 prompt tokens 更值钱？——**是（在本会话价格结构下）**

### 3.1 实测计价（同一会话，高峰价，deepseek-flash 价目见 ACCOUNT）

| 项 | tokens | 费用（元） | 占比 |
|---|---:|---:|---:|
| 输出 | 166,403 | **1.331** | **66.75%** |
| 输入·未命中 | 250,606 | 0.501 | 25.13% |
| 输入·命中 | 4,048,640 | 0.162 | 8.12% |
| **合计** | prompt 4,299,246 / completion 166,403 | **1.994** | 100% |

- 19 轮 / 93 iterations（**4.89 iteration/轮**）/ 105 tool calls（5.53/轮）；
- **每轮 0.105 元、每 iteration 0.0214 元、每 iteration 输出 1,789 tok**；
- 单轮成本分布：写笔记的 3 轮 0.389 元（19.5%）、回答的 16 轮 1.605 元（80.5%）；最贵单轮 0.217 元（turn 7，13 iterations）。
- 口径说明：ACCOUNT 记录的是 **16 轮 / 1.64 元**（会话当时）；本文件读到的会话已追加到 **19 轮 / 1.99 元**。两套数都保留，**不做跨口径相减**（PROTOCOL E4.3）。

### 3.2 敏感性（按各轮实际档位单价，B4 齐报）

| 场景 | 费用（元） | 相对 |
|---|---:|---:|
| 现状 | 1.994 | — |
| prompt × 0.5（每轮减半） | 1.663 | **−16.63%** |
| prompt × 0.25 | 1.497 | −24.94% |
| 轮数 × 0.75（−25%） | 1.496 | **−25.0%** |
| 轮数 × 0.5 | 0.997 | −50.0% |
| prompt×0.5 + 轮数×0.75 | 1.247 | −37.47% |

（脚本 `scripts/analyze_session.py --json session-analysis.json` 的 `scenarios` 字段；`ev:bench:kg-retrieval-session-analysis`。）

### 3.3 等价换算（回答"哪个更值钱"）

- **省 1 个 iteration/轮 = 19 iterations ≈ 0.41 元 ≈ −20.5%**；
- **prompt 砍半 = −16.63%**；prompt **全部归零**也才 −33.25%（输入份额上限）；
- ⇒ **少 1 个 iteration/轮 ≈ prompt 砍半的 1.23 倍**；少 2 个 iteration/轮 ≈ −41%，超过"prompt 全免"。
- 机制解释：输出单价是未命中输入的 **4 倍**、命中输入的 **200 倍**（ACCOUNT §1：output 4/8 vs miss 1/2 vs hit 0.02/0.04 元/M）；每多一轮必多一份输出+一份增量输入。prompt 削减只作用于输入份额（33%），而**轮数削减同时作用于输出（67%）与输入（33%）**。

### 3.4 由此得到的投资判断

1. **索引的 KPI 必须是"减少探索轮"**：本会话 37 次 read_document 里 36 次读同一章、且集中在 8–13 iterations 的探索轮（turn 4/6/7/8）；这正是索引/L1 方向感可以压缩的对象。
2. **prompt 削减仍有独立价值，但价值不是钱**：656,818 峰值（1M 的 65.7%）+ 8 次 compaction + Lost-in-Middle（§4-R8），属于**质量/稳定性**收益，应在 R8 单列。
3. **不要做"只缩结果、不缩轮"的优化**（例如把 10K 结果截成 2K）：它最多拿到输入份额的一小部分，且可能因信息缺失让 agent 多读一次 → 净亏（本会话 grep 34K 字符结果就是反例：一次 grep 塞 9.8K tok，随后仍要 read_document）。

---

## 4. R1–R8 回答（C 视角；不重复 A/B 方已覆盖的契约与学习单元论证，只给 agent/token 证据）

### R1 索引单元

- **索引条目 = KP（现有 id/name/range）**，因为：真实 KP 已≈`##` 节（本章 28 KP vs 32 个 h2，`scripts/kb-granularity.json` `chapter3`），p50 523 字符，和"用户问题落到某个概念/公式"基本可比；
- 但**仅 KP 不够**：行级问题需要 KP 内部锚点。建议条目携带 `anchors[] = {kind: 定义|公式|定理|结论, line, snippet_hash}`，因为：37% KP snippet 不唯一、14.1% 读取路径已踩在会漂的锚点上（**给定输入**，task-195 基线 ⑥；`ev:baseline:task-195-inputs`）、本会话有 2 次用户直接给 `#L` 行号。对 agent 而言，"KP + 行号锚点"才是可行动单元。
- 反对把索引单元降到 chunk（固定 512 字）：本库 20.3% KP <200 字（碎片）、9.3% >3000 字（巨型），固定 chunk 会在公式中间切断（教材公式密度高，公式/表格块需要整体性）；**结构化切分（KP + 公式块）优于定长切分**。这是经验判断，需 corpus 侧数据复核（§6 M3-c）。

### R2 description 的"可判性"（agent 决策视角）

从本会话 19 个真实问题归纳，模型要在**不读正文**时判断三件事：① 这节和问题有关吗？② 大概在哪（公式/结论/推导）？③ 读完能回答什么？⇒ description 必须含 **"结论 + 关键量/公式符号 + 适用/区分"**，而不是"本节讨论 X"的同义反复。

建议模板（≤60 汉字，约 45–70 tok）：

```
<一句结论/定义>｜关键量：<符号/公式名>｜区分于：<相邻概念>｜定位：<公式号/定理号>
```

以本库真实 KP 为例（草案，非最终文案）：
- `uniform-quantization`：均匀量化=量化间隔恒定 Δ；SQNR 随位数 6.02N+…；与"非均匀量化（小信号优先）"区分；式 3.3.16 起。
- `bandpass-sampling`：带通抽样可行域由 f_H/B 决定、f_S 落在 2B~4B 区间；注意与低通 2f_H 的区别；图 3.2.4/式 3.2.19。
- `pcm`：PCM=量化值↔二进制码组的一一映射；区别于"广义 PCM（含波形编码）"；3.4 节。

**判据（可机检）**：description 必须能被这三个问题各回答 ≥1 个具体名词（量/公式号/对比概念）；否则判"不可判"退回重写。
**反例**：只写"本章讲抽样"——对"带通抽样上界为什么比低通小"这类问题零信息（本会话 turn 340/349 就是这类追问）。

### R3 证据绑定与失效（agent 消费视角）

- 每条 description 至少绑定 `{kp_id, file, start_line, end_line, source_sha}`；agent 侧只信任 `kp_id` 与 `文件:行号` 契约，stale 必须**显式降级**：索引读取结果里带 `stale:true` + `"以 read_document 原文为准"`，不允许静默使用；
- 检测成本：优先**文件级 sha + 行号区间 re-resolve**（现有 `resolve_knowledge_points`），不做全库逐块 hash；只有命中 stale 的文件才做块级 diff；
- agent 行为约定：stale 条目 → 直接 `read_document(range)` 并**不把 stale description 当证据**（引用只写 `文件:行号`）。

### R4 锚点稳定性（对 agent 的直接要求）

- 现有 `{snippet, line_hint}` 锚点会漂（37% 不唯一、前插 50 行后 18.8% 静默钉错，给定输入）；agent 侧因此**不能把 line_hint 当权威**；
- 建议锚点三层：`kp_id`（稳定主键）→ `heading path`（可重算）→ `line`（读取时由 `resolve_knowledge_points` 重解析）；description 里保存 `snippet_hash` 仅用于校验，不用于定位；
- 漂移时 agent 可见行为：`read_kp` 返回 `range_repaired:true` + 新行号，引用仍写新行号（保持"看到的=读到的"）。

### R5 检索路径与预算（本提案重点之一）

**分层与硬上限（全部复用现有常量口径，不新造预算系统）**：

| 层 | 内容 | 预算 | 控制者 |
|---|---|---|---|
| L0 | `kb_overview`（文件清单 + KP 数，现状 934 字符 ≈ 267 tok） | ≤300 tok | 工具硬上限 + 现状 |
| L1 | 单文件 KP 索引（每行 `行号 [id] 名称`，28 KP ≈ 900 tok） | ≤800 tok，超限分页 `cursor` | 工具（复用 `OUTLINE_MAX_TOKENS=800`，`ev:file:src/memoria/services/agent/section_index.py#L51`） |
| L2 | 读正文：`snippet`（600 tok）/ `section`（4000 tok）/ `read_document`（2000 行） | 单次 ≤1.5k tok 为推荐用法 | 工具硬上限（`#L52-L53`、`kb.py#L992`）+ 模型选择 |
| L3 | 全库 KP 摘要 | **禁止整包**；需要时按文件/主题分页 | 不提供该工具 |

- **谁控制预算**：**工具硬约束负责"不可能超"**（现有模式：outline/section/snippet 都带 `max_tokens`），**模型负责"选择调用哪层"**；不要在 loop 里偷偷截断（会制造"看不见的缺失"，且无法归因）。
- 数学依据：357 KP × 60 tok description ≈ **21,420 tok** 全量注入 ≈ 会话均值的 9.5%，且被放大 ~10.94×（Lead 基线②；我按逐次调用放大得 892,855 token-rounds，`session-analysis.json.amplification`）⇒ **全量注入本身就是新的上下文债务**。
- 预算放哪：**不进 system prompt**（否则每轮都占）；作为工具返回值，按需调用、用完即弃。

### R6 与现有检索栈融合（本提案重点之二）

现状（`ev:file:src/memoria/services/search_kernel.py#L38-L125`）：`search(modes=)` 支持 `lexical / semantic / both / full`；`both/full` 时走 `retrieval_fusion.fuse_search_results`（RRF），可选 cross-encoder rerank，`body_locate` 另挂。而 **agent 路径硬编码 `modes="lexical"`**（`ev:file:src/memoria/services/agent/tools/kb.py#L248`）⇒ agent 只用了 1/4 能力。

**方案：索引作为"第 3 条通道"接入现有 RRF，而不是新开检索器、也不替代 lexical**：
1. `retrieval_fusion` 已有 **Graph 占位通道**（`ev:file:src/memoria/services/retrieval_fusion.py#L145-L152`；`DEFAULT_CHANNEL_WEIGHTS` `#L47`；`RRF_K=60` `#L7`）→ 新增 `index` 通道权重建议 **0.6–0.8**（低于 lexical/semantic，因为它只用于"选 KP"，不提供原文证据）；
2. **索引通道只召回 KP id + 行号**，正文仍由 `section/snippet/read_document` 取 ⇒ 证据永远来自原文（引用契约不变）；
3. **保留 lexical**：本会话 7 次 search_kb 有 1 次零命中，剩余 6 次有命中的查询**都**出现了 `img/*.md` 包装文件行（见会话检索结果样例），那是**语料卫生/filter 问题**，不是替换 lexical 的理由；而 `grep/snippet` 的精确子串能力（公式、符号）是 embedding 不擅长的；
4. 不建议把 `modes` 直接改成 `both` 作为第一步：本机 embedding 默认关闭（`is_embedding_enabled` 读 UI 设置，`ev:file:src/memoria/services/embedding_provider.py#L50-L51`），切通道是配置+质量风险，应先做 §2.4 的"id 可见"和 L1 索引，再按 A/B 决定是否启用 semantic 通道；
5. 与图的关系：本会话 graph/edge/KP 命中 0（Lead 基线①）⇒ 图不该是 agent 第一入口；索引与图共享 `kp_id` 锚点，图可作为**后续扩展**（例如"相关 KP"提示），不进 Phase 1 主路径。

### R7 外部参考（只作思路对照，不据以裁决，M2/B5）

- **AOCI**（本仓 `.mcp.json` 已接入）：Entry = 对象 + F/R/A/S + 证据绑定 + 刷新门禁 ⇒ 与"KP description + 源 hash + stale"同构，可作为 **R3 的直接参照**（尤其"机器签发候选 + 模型创作语义"的维护流程）。
- **XERJ brain**：边带 `valid_at/invalid_at` 的 bitemporal ⇒ 可作为 **R3/R4 stale 语义**参照（描述存"何时有效"而非只看当前字节）。
- 明确**不搬**：GraphRAG 社区摘要（索引成本高，且本库 58 篇/中文学科教材的"全局问题"占比低——本会话 19 问中 0 问需要全局摘要，`ev:bench:kg-retrieval-session-analysis.per_turn.user`）；RAPTOR 递归摘要（教材标题层级已足够，重造树会与 KP/标题双事实源冲突）。
- 论文依据（仅 1 条，用于 R8）：Lost in the Middle（Liu et al., TACL 2023, `ev:paper:https://arxiv.org/abs/2307.03172`）：相关信息在长上下文**中段**时性能显著下降，即使模型支持长上下文 ⇒ 225K/656K prompt 本身是答对率风险，不只是费用问题。

### R8 "真正对 agent 有提升"的 A/B 与证伪条件（含"答对率不能降"）

按 PROTOCOL B4/E4.2 口径设计（同 commit/语料/任务集/脚本/轮数；≥5 次或完整分布；原始产物落盘带 sha）：

**任务集**：用本会话 19 个真实问题 + 同库 held-out 20 问（同分布五类：定义/概念、对比、公式推导、行级定位（`#L`，用 435/475 两例补足）、纠错追问；分类为人工归类，边界可复核）。
**两组**：A=现状；B=索引（read_kp id 可发现 + L1 索引 + 可选 index RRF 通道）。
**指标（全部齐报，B4.a/b）**：
| 指标 | 定义 | 判据 |
|---|---|---|
| **答对率** | 固定 rubric 盲评（以教材原文为参考答案；≥2 评委；0–2 分/题） | **不得低于 A 超过 2 个百分点**（硬门槛） |
| **iterations/answer** | 每问 LLM 迭代数（median + min–max） | 期望 −20% 以上 |
| **tool calls/answer** | 每问工具调用数 | 期望 −15% |
| prompt tokens | 总/峰值/每轮 | 峰值 ≤400K（安全区） |
| completion tokens | 总 | 随 iterations 下降 |
| 总成本 | 按 pricing.py 逐轮计价 | 期望 −15% 以上 |
| compaction/prune 次数 | 事件数 | 不得增加 |
| 重复读同文件次数 | 计数 | 期望下降（本会话 36） |

**证伪条件（见 §7）**；**A/B 之外的辅助实验（便宜、先做）**：只做 §2.4 的 `[kp_id]` 露出，量 read_kp 采用率与 read_document 次数变化——若采用率不升，则问题在粒度（2.3）而不是可见性，直接改 `read_kp offset/limit`。

---

## 5. 我否决的方案（含自己考虑过的）

### 否决 1：`kb_overview` 直接返回全库 357 个 KP 的摘要（我曾想"一次给全，省得来回"）
- 数学：357 × 60 tok ≈ **21.4K tok/次**；本会话平均 prompt 226K/轮 ⇒ 单次注入 ≈ +9.5%，且被放大 ~10.94× ≈ 234K token-rounds ≈ 0.23 元/会话（按未命中折算），**收益为零**（L1 分页只需 800 tok）；
- 质量：Lost-in-the-middle（`ev:paper:arxiv:2307.03172`）⇒ 中段 21K 索引反而降低命中段落的可见性；
- 替代：L0（文件清单，267 tok）+ 按需 L1（单文件 ≤800 tok）。

### 否决 2：让 `read_kp` 取代 `read_document` 作为默认读取（"KP 更结构化"）
- 本会话 read_kp 平均 **1,431 tok/次**（大 KP），而 read_document 平均 **904 tok/次**；行级问题（3/19）需要 20–60 行窗口，KP p99 3.5K tok 太粗；
- 替代：read_kp 露出 id + 加 `offset/limit`；`read_document` 保留。

### 否决 3：把 agent 检索切到 `both/full`（semantic+RRF）替代 lexical（"利用现有 4 模式"）
- 本机 embedding 默认关闭（`ev:file:...embedding_provider.py#L50-L51`），切通道是配置+质量+成本三重变量；
- 本会话 lexical 只有 7 次调用，不是瓶颈；真正的检索质量问题是 `img/*.md` 污染（7/7 查询命中 img 行）；
- 替代：先做 `[kp_id]` + L1；索引作为 index 通道接入 RRF；semantic 按 A/B 决定（§R6）。

---

## 6. 我不确定的点（M3 登记；含 `if_true_then`）

| # | 未知 | if_true_then |
|---|---|---|
| M3-a | description 由谁写、成本多少（0/357 现状）；LLM 生成的"可判性"是否达标 | 若人工 ≥5 min/KP 不可维护 ⇒ 降级为"机器可提取字段（标题/公式号/首句）"，不做自由摘要 |
| M3-b | "露 id"是否真的提升 read_kp 采用率（未测） | 若不升 ⇒ 主因是粒度，直接做 read_kp offset/limit；索引设计不受影响 |
| M3-c | 结构化切分（KP+公式块）是否优于定长 chunk | 若 corpus 分析证明公式跨 KP 严重 ⇒ 索引单元改为"KP+公式块"，R1 调整 |
| M3-d | index 通道能减少多少 iterations（未测） | 若 A/B 显示 iterations 不降 ⇒ 本提案的"轮数优先"收益不成立，只保留 R1–R6 的数据结构部分，砍掉 RRF 通道 |
| M3-e | Lost-in-middle 在中文教材/225K-656K 尺度效应强度（论文为英文 QA） | 若效应弱 ⇒ prompt 削减的"质量"理由下调，但仍保留"峰值安全"理由 |
| M3-f | `img/*.md` 污染对答对率的实际影响 | 若影响大 ⇒ 检索卫生（过滤包装文件）应排在索引之前，属独立 P0 |

---

## 7. Falsifiers（什么结果会推翻我的主张）

1. **"轮数比 prompt 更值钱"**：若某次 A/B 中"prompt 砍半但不减 iterations"的总成本降幅 **>** "减 1 iteration/轮但不缩 prompt" 的降幅 ⇒ §3 结论撤回（当前实测分别为 −16.63% vs −20.5%，需新实证）。
2. **"索引能减轮"**：若 A/B 中 B 组 iterations/answer 与 A 组差 <5%，且正确率无变化 ⇒ 索引对 agent 的"探索轮"无价值，本提案 R6/R8 的收益主张撤回。
3. **"露 id 提升采用率"**：若只改 `[kp_id]` 后 read_kp 采用率不升（<2×）且 read_document 次数不降 ⇒ 原因判定为粒度，§2.4 的最小改动结论修正为"必须先做 offset/limit"。
4. **"答对率不降"**：若 B 组正确率低于 A **>2pp** ⇒ 整个索引方案否决（这是人给的硬条件）。
5. **"峰值安全"**：若 B 组峰值仍 >500K 且 compaction ≥A ⇒ 上下文安全收益不成立，prompt 削减目标需重设。
6. **成本**：若 B 组总成本高于 A（含索引维护/生成开销）⇒ 否决。

---

## 8. 独立性与 read_set / 原始产物

**unread_declared**：未打开任何 `PROPOSAL-*.md`（含 arch-contract / todo-owner / metrics-baseline 三份），只见过 Lead 转述的任务口径；未与四方讨论。

**read_set（path + sha256 前 16 位，LF 归一化口径）**：

| path | sha256[:16] |
|---|---|
| `src/memoria/services/agent/tools/kb.py` | `d7d60c21274fe01f` |
| `src/memoria/services/agent/loop.py` | `11fdf53da3bc774e` |
| `src/memoria/services/agent/prompt.py` | `faacbbf650ffdf44` |
| `src/memoria/services/search_kernel.py` | `71bbd931cf415c1f` |
| `src/memoria/services/retrieval_fusion.py` | `c127f7d62be0e198` |
| `src/memoria/services/agent/section_index.py` | `85b0f6617026b291` |
| `artifacts/agent/verify/kg-agent-retrieval/ACCOUNT-2026-10-27.md` | `073163bab5a905d5` |
| session `session-20261027T011706Z-0cb419b6.jsonl`（只读） | `ecd2fd2b43f16309` |
| sidecar `03_第3章_模拟信号的数字编码.memoria.yaml`（只读） | `7d38f9819fda14f0` |
| `artifacts/agent/verify/debate/kg-retrieval/scripts/session-analysis.json` | `c67cdcf7d815b87c` |
| `artifacts/agent/verify/debate/kg-retrieval/scripts/kb-granularity.json` | `b0559e72cfe968c6` |

**可复跑脚本（均在 `artifacts/agent/verify/debate/kg-retrieval/scripts/`）**：
- `analyze_session.py` → `session-analysis.json`（工具分布/逐轮成本/放大系数/场景表）
- `kb_granularity.py` → `kb-granularity.json`（357 KP 粒度/标题层级/大 KP 榜）
- `trace_kp_id_visibility.py`（id 首次可读出现位置）
- `summarize_for_proposal.py`（iterations/read_kp 轮次/命中率）

**给定输入（不重测，直接引用）**：task-195 基线 ①–⑥（4 模式/RRF、真会话分布、放大系数 10.94×、357 KP 碎片比例、94.17% 命中率、锚点漂移 14.1%）— `ev:baseline:task-195-inputs`。

---

## 9. 一句话

**先别造索引系统：把 `kp_id` 放进 read_document/search_kb 的输出（改两行），就能把"已存在但不可发现"的 read_kp 变成真实入口；而索引产品的验收要以"少几个 iteration/轮"为主指标——本会话实测输出占 66.75%，省 1 iteration/轮（−20.5%）比 prompt 砍半（−16.63%）更值钱，prompt 削减的正确价值是"防爆 + 防 Lost-in-Middle"，不是省钱。**
