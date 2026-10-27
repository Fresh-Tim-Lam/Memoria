# E1 扩项 C 源取证：agent 记忆插件 / 记忆实现 / 相关论文

> 角色：C 源扩项取证（agent memory）。**只做 E1-memory，不写设计提案、不 commit。**
> 取证日：2026-10-27（Asia/Shanghai）。
> 方法：先扫本机 DSH（源码 + 安装 profile + 文档），再抓 GitHub 实现源码（本地落盘 `evidence/_mem_src/`，逐行核对），最后抓 arXiv abs 页面核对年份/venue/摘要数字。**未运行任何仓库代码**；所有"代价"是读代码/读摘要得出的结构性代价，不是 benchmark。
> 许可纪律：Mem0/Graphiti/Letta/LangMem 等有明确许可；**Basic Memory 为 AGPL-3.0，只作思路参考，不复制任何代码**；Letta 服务端源码在 `main` 已不可得（只剩文档/政策），只取到 SDK 生成类型。
> 与 E1-oss.md 的关系：本文件是补轴，不重复 E1-oss 的索引单元取证；交叉处在 §9 标注。

---

## 0. 先行结论（对应 lead 的 A–E）

| 问题 | C 源证据状态 | 一句话 |
|---|---|---|
| **A 稳定身份 vs 内容漂移** | **强**（Graphiti 双时态 + Mem0 历史 + DSH 版本化记忆） | 成熟做法不是"用一个哈希当身份"，而是 **稳定 id + 时间/版本身份 + 显式失效（soft-invalidate/历史表）**：Graphiti 的边有 `valid_at/invalid_at/expired_at`；Mem0 每次 ADD/UPDATE/DELETE 都写 history（old/new/event）；DSH 长记忆用 `sourceVersion` 过滤过期工具事实 |
| **B 可判性摘要字段** | **中—强**（有"摘要字段"，但都不是"可判性"） | 存在 `EntityNode.summary`（Graphiti）、`memory` 文本（Mem0）、`context/keywords/tags`（A-MEM）、`description`（Letta block/ LlamaIndex block）。**没有一家把"可判性"做成字段/校验**；最接近的是 DSH 长记忆的 **kind + source + sourceVersion**（约束必须用户来源、事实必须工具来源+版本）+ 注入时明说"summary 未经语义核验" |
| **C 遗忘/合并** | **强**（三种范式齐全） | ① **软失效保留历史**：Graphiti invalidate + mcp-memory supersede（旧记忆退出默认检索但可查）；② **归档/压缩后删**：mcp-memory ControlledForgettingEngine（archive/compress/delete/skip）；③ **截断**：LlamaIndex memory block 按 priority 截断、DSH 卡片 8KiB 截断。另有 Memary 纯年龄淘汰、MemoryBank Ebbinghaus 遗忘曲线、A-MEM 记忆演化（旧记忆属性会被新记忆改写） |
| **D 分层记忆 ↔ L0/L1/L2** | **强（结构可比），但需谨慎映射** | LlamaIndex `Memory` 就是"FIFO 短期 + blocks 长期 + token_limit×ratio"；Letta 是"core blocks（常驻系统提示）+ archival passages（检索）"；MemGPT 论文是 OS 式虚拟上下文。**但它们是"按持久性分层"，我们的 L0/L1/L2 是"按注入预算分层"**（L0≤300 tok / L1≤800 tok / L2 单次≤1.5k tok，见 PROPOSAL-agent-arch L169-171）——只能做"功能映射"，不能说"同一种分层" |
| **E 实测数字** | **有，但只在论文摘要，且不覆盖本仓场景** | Mem0：+26% LLM-as-Judge vs OpenAI、p95 延迟 −91%、token 成本 −90%+；Zep：DMR 94.8% vs MemGPT 93.4%、LongMemEval 最高 +18.5%、延迟 −90%；HippoRAG：多跳最高 +20%、比 IRCoT 便宜 10–30×、快 6–13×。**MemGPT / Generative Agents / A-MEM / MemoryBank / CoALA 摘要里没有可直接引用的数字**；没有任何"中文教材/个人知识库"场景数字 |

---

## 1. ① 本机 DSH 已有的 agent 记忆机制（先说结论：DSH 没有"记忆插件"，只有 3 个 opt-in MCP overlay + 两套内建记忆）

### M1｜DSH 官方定位：**不做**记忆供应商，只提供通用 MCP 桥

- **来源**：`D:\deepseek-harness\.agents\notes\archived\feature\2026-07-31-third-party-memory-mcp-examples.md`（DSH 仓库 MIT，L14-18、L22-31、L35-43、L57-63）；`D:\deepseek-harness\docs\user\guide\mcp-memory.md`（L9-13、L17-21、L37-55、L74-82）。
- **事实**：
  - DSH 只发布 3 个**默认关闭**的 Cordis overlay（路径 `apps/cli/config/examples/mcp-memory/`）：
    - `memorix.cordis.yml`：`memorix@1.3.0`（npm，commit `500792c`），stdio，存储 `~/.memorix/data`；无 LLM/embedding 也能跑本地启发式（guide L37-44）。
    - `mcp-reference-memory.cordis.yml`：`@modelcontextprotocol/server-memory@2026.7.4`（commit `6dd0a68`），stdio，JSONL 默认落 `$HOME/.dsh-mcp-reference-memory.jsonl`（yaml L1-13）。
    - `engram.cordis.yml`：Engram `v1.20.0`（commit `ba9e46c`），`engram mcp`，存储 `~/.engram`，项目身份默认取 Git 工作目录（guide L57-64）。
  - 每个 overlay **只插入一行** `@deepseek-ai/dsh-mcp-client`；工具暴露为 `mcp__<serverName>__<tool>`（note L16、guide L9-13）。
  - DSH 明确**不**做：下载/安装 provider、初始化数据库、管理模型/embedding、迁移数据、健康检查、重连控制器（note L18、L22-31；guide L9-13）。"no memory preset registry, vendor-specific DSH plugin, universal memory service"（note L18）。
  - 参考记忆服务器的语义边界（guide L55）："**Search is case-insensitive substring matching... not semantic retrieval. The server does not add embeddings, automatic summarization, conflict resolution, or a forgetting policy.**"——这是官方文档对"最简单记忆插件"的自我描述，直接回答 B/C：没有摘要、没有冲突、没有遗忘。
  - 验收契约（note L57-63）：session A 写入 → **fresh** session B recall（不复制 A 的对话）→ B 使用召回值；"fresh session"= 同一 Host 新会话，不需重启。
- **对 A–E**：A：身份归 provider（Memorix/Engram 用 Git 项目 + provider 自有 id；reference 用实体名/关系名）；B：无摘要字段；C：无遗忘策略；D：MCP 工具是"按需调用"，不是分预算注入；E：无公开数字。
- **落地**：Memoria 若要做"可插拔记忆"，照抄"一个通用 MCP 桥 + 多份默认关闭 overlay"的边界比"内置记忆插件"便宜；但 DSH 的经验也说明：**桥不解决语义，语义在 provider**。
- **许可**：DSH MIT；三个上游各自许可（Memorix Apache-2.0、MCP servers repo `NOASSERTION` 需单独核对包许可、Engram MIT）。

### M2｜DSH 内建 `dsh-super-code` 长记忆：小型、主题化、版本感知（最贴近"可判性"）

- **来源**：`D:\deepseek-harness\.dsh\profiles\desktop\node_modules\dsh-super-code\lib\long-memory.js`（DSH MIT，L1-166）；配 `memory-usage-projection.js`（L1-110）。
- **Schema（L8-28）**：entry = `{id, kind∈{constraint,fact,experience}, summary(≤30 字符), detail(1..1000 字符), source, sourceVersion?}`；`source` 是判别联合：
  - `user`：`{sessionId, eventSeq, quote≤4000}`；
  - `tool`：`{sessionId, eventSeq, callSeq}`；
  - `manual`：`{sessionId}`。
  - 校验规则（L17-28）：**`constraint` 必须来自 user；`fact/experience` 必须有 tool source 且带 `sourceVersion`；manual 不允许带版本**。
- **主题/容量（L29-37、L81-100）**：topic = `{workspace(sha256(realpath cwd)), topic, revision, entries≤20}`；每 workspace ≤200 topics；**一 topic 一条原子记录**；写入用 `expectedRevision` CAS（L89-90 抛 `Stale topic`）；写入队列串行化（L76-80）。
- **身份（L52-58）**：记录 key = `sha256(workspace\0topic)`；`memoryEntryToken = sha256(JSON.stringify(entry))` **只作并发校验，不存历史**（L55-57 注释 "never stores a prior entry or a version history"）。**编辑时 id 不能改**（L107-108）。
- **遗忘/失效**：显式 `forget()` 删除单条（L131-145）；读上下文时按 `sourceVersion` 过滤工具事实（L148-153），并统计 `staleFacts`（L155-158）。
- **注入（L148-165）**：`longMemoryContext(topic, maxBytes=2048)`——**2 KiB 上限**，只取最近 **4** 条，超出逐条 shift 直到装下；输出带 `basis`：
  > "historical; manual entries are user-maintained; tool source pairs checked at write time, **summaries not semantically verified; verify mutable facts**; no permission granted"
- **对 A–E**：A：entry id + `sourceVersion` + revision CAS，是"身份/版本/并发"三件套（但**不保留历史**）；B：`summary≤30` + `detail` 是摘要字段，`kind + source` 是"来源可判"约束，`basis` 明确"摘要未经语义核验"——**这是本机最接近"可判性摘要"的设计**；C：显式 forget + 版本过滤（无自动衰减/合并）；D：**2 KiB 上下文预算 + 最近 4 条**，是标准 L1 级注入；E：无公开数字。
- **落地性**：高（MIT，代码短，schema 清晰）；但注意它面向"项目级偏好/约束"，容量上限 200 topics×20 entries，不适合当知识库检索层。

### M3｜DSH Team memory cards（本 agent 团队正在用的机制）

- **来源（代码）**：`D:\deepseek-harness\packages\experimental\agent-team\src\memory.ts`（DSH MIT，L1-240 起）；**来源（文档）**：`docs/persistence-changes/2026-10-24-team-memory-cards.md`（L12、L38-43）。
- **Schema/边界（memory.ts）**：
  - `MAX_MEMORY_CARD_BYTES = 8_192`（L14）；`MAX_INJECTED_MEMORY_BYTES = 51_200`（L17）；继承摘要只取**最后 3 条** assistant 结论（L19-20），每条 ≤200 字符（L27）。
  - 卡片固定四节（L39-44）：`我确认的事实（带证据：file:line / commit / 命令输出）`、`我试过但失败的路`、`我留下的坑`、`我推翻过的假设`；+ 强制 `### Lead 裁决`（L47）。
  - 每节带 **authority 标签**：`machine / self / lead / human`（L36）；machine 节由运行时抽取，Lead/human 可写（`team_memory_write`），**self 半可信**。
  - 卡片头有 `team-memory-card/v1 · bounded to 8 KiB · omitted …` 标记（L76）；超限追加 `truncated: true`（L79）；失败工具调用最多 5 条、每条 ≤320 bytes（L30-33）。
  - 读取时按 8 KiB 截断（L214-233）；文档 L43 记录验证："8 KiB bound with a truncation marker, **49 KiB inheritance pass versus 51 KiB explicit rejection**, append accumulation, completion-triggered extraction, retirement fail-closed ..."。
- **对 A–E**：A：卡片 id = member name / card path（L176-190），**不是内容哈希**；内容漂移靠"重写整卡"而非版本链；B：既有摘要（事实/坑/假设）也有证据锚点（`file:line / commit`），并显式区分 authority——**"可判性"体现在"证据 + 权威标签"而非字段级布尔**；C：无自动遗忘，靠 8 KiB 截断 + 退役时 fail-closed（缺卡/缺裁决拒绝退役）；D：**8 KiB/卡 + 50 KiB 注入** ≈ 我们的 L0/L1 级预算，但比 PROPOSAL 的 L0≤300 tok 大一个量级；E：无公开数字（文档只给测试通过数，非效果）。
- **落地性**：高（同仓同许可）；但这是"团队协作记忆"，不是"知识库检索记忆"。

### M4｜本机 XERJ 记忆层（闭源，只能读布局）

- **来源**：`C:\Users\Lam Tim\xerj-data\.xerj-memory-<ns>/`（索引盘 + `schema.json`）、`.xerj-memory-<ns>-edges/`、MCP 工具契约 `xerj_memory_store/recall`（含 `dedup`）。
- **事实**（详细见 E1-oss.md §6.1）：记忆 doc schema = `text`(text, 带 384 维 cosine `text_vector`)、`stored_at`(long)、`metadata{date, role, task, doc, files, verification}`；独立 `-edges` 目录存图边；`xerj_memory_store` 支持 `dedup`；`recall` 支持 `recency_weight`/`graph` 耦合、`as_of` 双时态。
- **对 A–E**：A：`as_of` 双时态 + 图边"believed-since/retired"是**软失效**思路（工具契约可见）；B：无摘要字段，只有 text+metadata；C：工具契约有 `dedup`（合并近似记忆）但**遗忘策略未取到**；D：memory 索引按 namespace 隔离，无预算参数暴露；E：无公开数字。

---

## 2. ② GitHub 成熟 agent memory 实现

> 所有 repo HEAD commit 与许可均于 2026-10-27 用 GitHub API 核对；源码落盘 `evidence/_mem_src/`。行号对 2026-10-27 快照有效。

### M5｜Mem0（Apache-2.0；HEAD `26cdefb46600` 2026-10-26）

- **记忆单元 schema**（`mem0/memory/main.py` L1975-2001、L2052-2100、L2114+）：
  - `memory_id = str(uuid4())`（L1981；异步路径 L2709/3678）；**id 与内容哈希分离**；
  - payload：`data`(记忆文本)、`hash = md5(data)`（L1984、L2077）、`created_at`、`updated_at`、`text_lemmatized`（BM25 用）、以及 `user_id/agent_id/run_id` 过滤键（L2107）与任意 metadata；
  - 更新时保留原 `created_at`（L2079），刷新 `updated_at`/`hash`。
- **写入/冲突决议**（`mem0/configs/prompts.py` L176-185、L189-320）：LLM 被要求对每条候选事实输出四种事件之一：`ADD / UPDATE / DELETE / NONE`；prompt 明确"新事实已存在→NONE；补充/细化→UPDATE；矛盾→DELETE"。→ **冲突由 LLM 语义判断，不是结构规则**。
- **历史与可追溯**（main.py L1078-1098、L1960-1972）：history 记录 `{memory_id, old_memory, new_memory, event, created_at}`；`history(memory_id)` 可查。→ **删除/更新不是不可逆的**（保留变更历史），但**没有双时态检索**。
- **检索**（L1393 `search`）：向量检索 + 过滤 + 可选 rerank（本报告未逐行读 rerank 实现）。
- **对 A–E**：A：uuid + md5(内容) 并存，md5 只用于去重/BM25，不承担身份；B：`memory` 文本就是 LLM 抽取的"可读事实"，无"可判性"字段；C：DELETE/UPDATE + history（**硬失效但留历史**）；D：长期记忆存储 + 检索注入，无 token 分层；E：论文数字见 §3。
- **许可**：Apache-2.0（可参考/可移植需声明）。

### M6｜Graphiti / Zep（Apache-2.0；HEAD `2b5db9e139b2` 2026-10-26）——**本轴最重要的实现**

- **节点 schema**（`graphiti_core/nodes.py`）：
  - `Node`（L93-98）：`uuid=uuid4()`、`name`、`group_id`（图分区）、`labels`、`created_at`；
  - `EpisodicNode`（L318-325）：`source`(EpisodeType)、`content`(原始 episode)、`valid_at`、`entity_edges`；
  - `EntityNode`（L499-502）：**`summary`（"regional summary of surrounding edges"）** + `attributes: dict`；
  - `CommunityNode`（L727-729）：`summary`（"region summary of member nodes"）——**层次摘要**。
- **边 schema**（`graphiti_core/edges.py` L49-54、L263-285）：`EntityEdge` 有 `fact`、`episodes[]`、**`valid_at` / `invalid_at` / `expired_at`**、`reference_time`。→ **双时态（事实有效时间 + 系统记录时间）**，这是 E1 ③"稳定身份 vs 内容漂移"的直接答案：**不删除旧事实，只标 invalid_at/expired_at**。
- **合并/冲突决议**（`utils/maintenance/edge_operations.py` L309-371、L424-450、L616+）：抽取边时解析 `valid_at/invalid_at`（失败则 warning 跳过）；`resolve_extracted_edges` 返回 `(resolved_edges, invalidated_edges, new_edges)`——**新信息可 invalidate 旧边**，并记录 `invalidated_by` 映射。
- **实体去重**（`utils/maintenance/node_operations.py` L67-68、L991-1135、L1260；`dedup_helpers.py` L31、L34、L151-204、L259-293、L321-372）：
  - `NODE_DEDUP_CANDIDATE_LIMIT = 15`、`NODE_DEDUP_COSINE_MIN_SCORE = 0.6`（node_operations L67-68）；
  - 名称熵阈值 `1.5`、模糊 Jaccard `0.9`、MinHash/LSH 分带（dedup_helpers L31/L34/L104-132）；
  - 支持**显式 identity properties**（如 email/uuid）优先匹配（L259-293）；
  - 合并时 `_merge_non_empty_attributes`：**空值不覆盖已有值**（L192-204）；
  - 摘要维护：`should_summarize_node` 工作线程（L991+）；如果 `summary + edge facts` 不超过 `MAX_SUMMARY_CHARS*2` 就**直接拼接、不调 LLM**（L1121-1135）；超长才 LLM 摘要并 `truncate_at_sentence(..., MAX_SUMMARY_CHARS)`（L1260）。
- **对 A–E**：A：**双时态软失效 + identity properties + uuid**，是最完整的"身份/漂移"答案；B：`EntityNode.summary` 是真正的"摘要字段"，且**优先拼接、必要时 LLM、按字符上限截断**——但摘要的对象是"实体周围边事实"，不是"知识点可判性"；C：invalidate/expired + 去重合并 + 摘要重写（**保留历史）**；D：episodes（原文）+ entity nodes（摘要）+ communities（层级摘要）三层，可按需检索；E：Zep 论文数字见 §3。
- **许可**：Apache-2.0。

### M7｜Letta / MemGPT（服务端已不可得；SDK Apache-2.0）

- **重要事实（必须写"未取到"）**：`letta-ai/letta` 的 `main` 分支 **只剩文档/政策/`LICENSE` 等 12 个 blob**（2026-10-27 用 GitHub tree 核对：`.github/*`、`AGENTS.md`、`AI_POLICY.md`、`CITATION.cff`、`CONTRIBUTING.md`、`LICENSE`、`PRIVACY.md`、`README.md`、`SECURITY.md`、`TERMS.md`），**服务端 Python 源码不在开源仓里**。因此只能取 SDK 生成类型（`letta-ai/letta-python`，Apache-2.0，HEAD `3731731b18af`）。
- **SDK schema**（`src/letta_client/types/block_response.py` L10-66；`passage.py` L12-58）：
  - Core memory block：`id`、`value`、`label`（"e.g. 'human', 'persona' in context window"）、`description`、`limit`（**character limit**）、`read_only`(deprecated)、`metadata`、`tags`、`is_template`、`created_by_id`、`last_updated_by_id`。
  - Archival passage：`text`、`embedding`、`embedding_config`、`id`（"human-friendly ID"）、`archive_id`、`file_id/file_name`、`created_at/updated_at`、**`is_deleted`（软删除）**、`metadata`、`tags`。
- **MemGPT 论文**（arXiv 2310.08560，2023；v2 2024-02）：OS 式虚拟上下文管理，**快/慢记忆分层 + 数据在层间移动 + interrupts**；文档分析与多轮对话两个域。→ "core block 常驻 + archival passage 检索"就是论文分层的工程化。
- **对 A–E**：A：block id + label（逻辑槽位）+ passage id + `is_deleted` 软删；B：block 的 `description` 是"这个块是什么"的说明，不是内容摘要；C：`is_deleted` 软删 + summarizer 压缩（服务端实现未取到）；D：**core blocks（常驻）vs archival（检索）** 是标准短/长期分层；E：论文摘要无数字。
- **许可**：SDK Apache-2.0；服务端源码**未取到**。

### M8｜LlamaIndex Memory（MIT；HEAD `619d74664e84`）

- **Block schema**（`llama-index-core/llama_index/core/memory/memory.py` L103-185）：`name`、`description`、`priority`（`0 = never truncate`）、`accept_short_term_memory`；抽象 `_aget/_aput`，可选 `atruncate`（默认直接返回 `None` = 丢弃整块，L167-185）。
- **Memory 分层**（同文件 L188-217、L624-670、L672-809）：
  - 配置：`token_limit`、`token_flush_size`、`chat_history_token_ratio`（默认 **0.7**，L213-216）、`memory_blocks` 列表、`insert_method`（system/user，L88-90、L604-620）；
  - 写入：`aput` 先入 SQL chat store，再 `_manage_queue`（L811-829）；队列超 `token_limit*ratio` 时按"最旧优先 + 完整对话轮"flush（L695-729），被 flush 的消息 **archive + 推给每个 block**（L781-797）；
  - 读取：`aget` 取 chat history + 各 block 内容（L624-650），按 token 预算 `_truncate_memory_blocks` 截断（L647-650），再按 `insert_method` 注入 system/最新 user 消息（L595-620）。
- **其他记忆后端**：`ChatMemoryBuffer`（token_limit + `_token_count_for_messages`，`chat_memory_buffer.py` L19-26、L114、L163）；`VectorMemory`（vector store + embed model，`vector_memory.py` L48-98）。
- **对 A–E**：A：消息/块没有稳定业务 id（chat store 内部 id；`generate_chat_store_key` uuid4，L93-95）；B：block 有 `description`（用途说明），内容可以是摘要块（需另配 block 实现，本报告未取到具体摘要 block 代码）；C：**FIFO 淘汰 + block 截断（按 priority）**——是"上下文窗口管理"而非"长期遗忘"；D：**这是与我们 L0/L1 最同构的实现**：FIFO（近期）→ blocks（常驻摘要）→ 注入；E：无公开数字。
- **许可**：MIT。

### M9｜LangMem / LangGraph（MIT；HEAD `48e3c11f5bb5`）

- **记忆 schema**（`src/langmem/knowledge/extraction.py` L73-93）：默认 `Memory` = `{content: str}`，描述为"**a well-written, standalone episode/fact/note/preference**"；`SummarizeThread` = `{title, summary}`；也支持自定义 schema（如 `PreferenceMemory{category, preference, context}`，`graphs/semantic.py` L26-31）。
- **写入/冲突**（extraction.py L217-339）：`MemoryManager` 用 **tool-calling** 让 LLM 选择 `insert / update / delete`；`json_doc_id` 决定是新 id 还是更新已有（L283-289）；去重/删除用 `RemoveDoc`（L285、L304-307）；**外部传入的 memory id 会被保留**（`external_ids`，L250-251、L291-293、L336-339）；`max_steps` 控制多轮抽取（L243-245）。→ **id 由调用方/LangGraph store 给，不是内容哈希**。
- **短期摘要**（`short_term/summarization.py` L53-77、L105-147）：`RunningSummary{summary, summarized_message_ids}`；预算参数 `max_tokens`、`max_tokens_before_summary`、`max_summary_tokens`，且强制 `max_summary_tokens < max_tokens`；`max_remaining_tokens = max_tokens - max_summary_tokens`（L119-121）——**摘要本身也占预算**。
- **存储**：LangGraph `InMemoryStore(index={dims:1536, embed:...})`；`namespace=("memories", "{langgraph_user_id}")`（semantic.py L7-16）；自定义 schema 示例 `PreferenceMemory{category, preference, context}`（L19-24）——**namespace 路径即分区身份**。
- **对 A–E**：A：memory id（json_doc_id / external id）+ namespace 路径；B：schema 自定义 + `content` 摘要文本；C：显式 insert/update/delete，**无自动遗忘**；D：短期 RunningSummary + 长期 store（按 namespace 检索）；E：无公开数字。
- **许可**：MIT。

### M10｜mcp-memory-service（Apache-2.0；HEAD `2c0fda3fb883` 2026-10-26）——**遗忘/冲突实现最完整**

- **记忆 schema**（`src/mcp_memory_service/models/memory.py` L37-54）：`content`、**`content_hash`**、`tags`、`memory_type`、`metadata`、`embedding`、`created_at(_iso)`、`updated_at(_iso)`、`timestamp`；另有 `access_count`、`last_accessed_at`（L251-258）、`record_access()` 记录最近 10 次 query（L364-381）。
- **衰减**（`consolidation/decay.py` L108-158）：指数衰减 `decay_factor = exp(-age_days / retention_period)`；总分 = `base_importance * decay_factor * connection_boost * access_boost * quality_multiplier`；低相关阈值 0.1、高相关阈值 1.0（L261-275）。
- **受控遗忘**（`consolidation/forgetting.py` L48-153）：`ControlledForgettingEngine` 的动作是 `archived / compressed / deleted / skipped`；归档到 `~/.mcp_memory_archive/{daily,compressed,metadata}`（L58-72）；规则示例："低质量（<0.5）在 30–90 天不活跃后归档（按质量缩放）"（L118-123）；低于 `relevance_threshold` 进候选（L151-153）。
- **冲突决议**（`consolidation/contradictions.py` L1-8、L24-28、L155-167）：用 embedding 相似度带 `[0.4, 0.75]` + KNN 10 找"语义相近但不完全相同"的邻居；判定新记忆 supersede 旧记忆，写 `contradicts` 图边并 `mark_superseded_batch`，**被 supersede 的行退出默认检索**（但保留）。
- **对 A–E**：A：**`content_hash` 被当作主键式身份**（supersede 以 hash 配对）——这是"内容哈希当身份"的少数派，代价是内容变→新记忆（与 LightRAG 同病）；B：无摘要字段（content 即原文/事实）；C：**衰减 + 选择遗忘 + 冲突取代**，三件套齐全，且"archive 而非 delete"；D：无分层（单层记忆库 + 检索/访问信号）；E：无公开数字。
- **许可**：Apache-2.0。

### M11｜Memary（MIT；HEAD `b2331a2c0844` **2024-10-18，近两年未更新**）

- **schema**（`src/memary/memory/types.py` L5-9、L22-26）：`MemoryItem{entity: str, date: datetime}`；`KnowledgeMemoryItem{entity, count, date}`——**只存实体名+时间/计数，不存原文**。
- **写入**（`src/memary/agent/chat_agent.py` L38-56）：一轮对话把 entities 写入 memory stream + entity knowledge store（L50-53），然后替换 LLM message 里的 `memory_stream`/`knowledge_entity_store`（即"把记忆列表塞回 prompt"，L75-84）。
- **遗忘**（`src/memary/memory/base_memory.py` L46-52）：`remove_old_memory(days)` ——按日期阈值**直接丢弃**（无归档）；`clear_memory` 清空（L61-73，agent L61-73 调它）。
- **对 A–E**：A：无 id（实体名+日期）；B：无摘要；C：纯年龄淘汰（最原始）；D：memory stream（短期列表）+ entity KG（长期计数）两层；E：无数字。
- **许可**：MIT。**结论：Memary 只能作"记忆流 + 实体图"概念参考，不建议搬实现。**

### M12｜Basic Memory（**AGPL-3.0，只作思路参考，不复制**；HEAD `438d49776b86`）

- **schema**（`src/basic_memory/models/knowledge.py`）：`Entity{id, title, permalink, file_path, created_at, updated_at}`（L32-110）；`NoteContent{file_path, updated_at}`（L186-230）；`NoteSection`（L303+）；`Observation{id, ...}`（L430+）；**`MemoryTimeIndex`**（L490+，内存时间索引）；`Relation{from_id, to_id, relation_type}`（L596-627）。
- **Markdown 即事实源**（`markdown/schemas.py`）：`Observation{category, content, tags, context, temporal: List[TemporalAssertion], temporal_error}`（L12-27）；`Relation{type, target, context}`（L41-46）；`EntityFrontmatter{...metadata}`（L56-64）；`EntityMarkdown{frontmatter, content, observations, relations, sections, created, modified}`（L111-127）。→ **记忆单元 = Markdown 文件/条目，带 frontmatter + wikilink 关系**，DB 只是索引。
- **时间限定符**（`markdown/temporal_qualifier.py` L1-8、L42-63、L115-125）：观察内容可带 `@asserted:2026-06-10`、`@valid_during:[...]` 等限定符；解析为 `TemporalAssertion`；**"读起来像时间但不是已知 kind"会被拒绝（refuse）而不是静默保留**；"refused or unread qualifier is never peeled... only derived temporal projection is withheld"（L61-63）。
- **对 A–E**：A：`file_path` + `permalink` 是稳定身份；时间限定符把"事实何时有效"写进内容/元数据——非常接近双时态；B：Observation 的 `category/context` 是描述性字段，无"可判性"校验；C：**无自动遗忘**（markdown 不删），靠时间投影过滤；D：文件/章节/观察三层；E：仓库含 **benchmark 代码**（`benchmarks/src/.../datasets/{locomo,longmemeval,beam}.py`）但**未运行、未取到结果数字**。
- **许可**：AGPL-3.0——**只读思路，禁止抄代码**。

### M13｜A-MEM（MIT；HEAD `f303dfc71e07` 2025-11-06；论文 NeurIPS 2025）

- **记忆单元 schema**（`agentic_memory/memory_system.py` L24-81）：`MemoryNote{content, id(uuid4), keywords, links, retrieval_count, timestamp, last_accessed, context, evolution_history, category, tags}`。
- **写入**（L237-290）：若 keywords/context/tags 为空，先用 LLM `analyze_content` 生成；然后 `process_memory(note)` 做**记忆演化**（建立链接、可能更新旧记忆属性），写入 ChromaDB metadata（L271-284），每 **100** 次演化触发一次 `consolidate_memories`（L97、L286-290）。
- **召回**（L314-374）：向量检索 top-k，再把命中记忆的 `links` 邻居一并拼进上下文（`find_related_memories_raw` L345-374）——**图扩展 + 向量检索的混合**。
- **对 A–E**：A：uuid + `evolution_history`（演化轨迹）+ `timestamp/last_accessed`；B：`context/keywords/tags` 是 LLM 生成的"可读摘要属性"，无校验；C：**演化/合并**（旧记忆会被新记忆改写）但**无删除/衰减**；D：单层 note + links 图；E：论文摘要无数值。
- **许可**：MIT。

---

## 3. ③ 相关论文（arXiv + 年份 + 摘要级证据）

| # | 论文 | arXiv / 年份 / venue | 摘要里能直接引用的结论/数字 | 与 A–E 的关系 |
|---|---|---|---|---|
| P1 | **MemGPT: Towards LLMs as Operating Systems** | [2310.08560](https://arxiv.org/abs/2310.08560)，2023（v2 2024-02） | 提出"virtual context management"：模仿 OS 分层内存，在快/慢记忆间移动数据、用 interrupts 控制流；文档分析 + 多会话聊天两域。**摘要无量化数字** | D；A（隐含：记忆有 tier/驻留位置） |
| P2 | **Generative Agents: Interactive Simulacra of Human Behavior** | [2304.03442](https://arxiv.org/abs/2304.03442)，2023（v2 2023-08） | memory stream：用自然语言存完整经历、**reflect 成更高层记忆、动态检索**；消融显示 observation/planning/reflection 各自关键。**摘要无数字**（无 retrieval score 权重公式，公式在正文，本报告未抓正文） | C（reflection/consolidation）、D |
| P3 | **HippoRAG: Neurobiologically Inspired Long-Term Memory for LLMs** | [2405.14831](https://arxiv.org/abs/2405.14831)，2024；**NeurIPS 2024** | 多跳 QA 比 SOTA **最高 +20%**；单步检索 vs IRCoT **便宜 10–30×、快 6–13×**；可接 IRCoT 进一步提升 | 检索/图记忆；E 有数字 |
| P4 | **A-MEM: Agentic Memory for LLM Agents** | [2502.12110](https://arxiv.org/abs/2502.12110)，2025；**NeurIPS 2025** | Zettelkasten 式：新记忆生成 `context/keywords/tags` 等结构化属性→分析历史记忆建链接→**记忆演化**（新记忆可更新旧记忆属性）；六个基础模型上优于 SOTA。**摘要无具体数字** | B（结构化属性）、C（演化/合并）、A（id） |
| P5 | **Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory** | [2504.19413](https://arxiv.org/abs/2504.19413)，2025（v1，未见会议标注） | LOCOMO 上：LLM-as-Judge 比 OpenAI **+26% 相对**；graph 版比 base **+~2%**；p95 延迟 **−91%**、token 成本 **−90%+**（相对 full-context） | A/C/E；与 M5 代码对应 |
| P6 | **Zep: A Temporal Knowledge Graph Architecture for Agent Memory** | [2501.13956](https://arxiv.org/abs/2501.13956)，2025（v1，未见会议标注；**CC BY-NC-SA 4.0**） | DMR **94.8% vs MemGPT 93.4%**；LongMemEval 准确率 **最高 +18.5%**、响应延迟 **−90%** | A（双时态）、E；与 M6 Graphiti 对应 |
| P7 | **MemoryBank: Enhancing LLMs with Long-Term Memory** | [2305.10250](https://arxiv.org/abs/2305.10250)，2023（v3） | 受 **Ebbinghaus 遗忘曲线**启发：按时间 + 记忆相对重要性"遗忘/强化"；有 SiliconFriend 案例。**摘要无量化数字** | C（遗忘曲线）、D |
| P8 | **Cognitive Architectures for Language Agents (CoALA)** | [2309.02427](https://arxiv.org/abs/2309.02427)，2023（v3 2024-03，TMLR camera-ready） | 框架：模块化记忆 + 结构化动作空间 + 决策过程；把记忆按 **working / episodic / semantic / procedural** 分类（正文；本报告只取摘要） | D（分层词汇）、B（semantic vs episodic） |

**论文小结**
1. **"记忆分层"在论文里是共识**（MemGPT/CoALA/Generative Agents），但**没有一篇给出"L0/L1/L2 预算分层"的工程参数**；我们的预算分层是产品约束，不是文献术语。
2. **可量化收益只在 Mem0/Zep/HippoRAG**，且都是英文对话/多跳 QA benchmark；**没有中文教材/个人知识库数字**。
3. **"可判性摘要"没有任何论文直接研究**；A-MEM 的 structured attributes、Graphiti 的 summary、DSH 的 kind/source 是三个最接近的工程近似。
4. **遗忘**：MemoryBank 用 Ebbinghaus 曲线（时间+重要性），mcp-memory 用指数衰减 + 归档，Graphiti 用双时态失效——**共同点是"不真删，保留可恢复/可审计"**。

---

## 4. 回答 A：它们怎么解决"稳定身份 vs 内容漂移"？

> 我们 E1-1 的结论是：开源索引实现里"稳定 id 与内容哈希分离是主流，但没有 chunk 级稳定身份"。记忆插件这一轴给出了**更完整的答案**：不是"一个 id"，而是 **id + 时间/版本身份 + 显式失效/历史**。

| 实现 | 身份 | 漂移处理 | 代价/边界 |
|---|---|---|---|
| Graphiti（M6） | `uuid` + `group_id` + identity properties（email/uuid 等显式键） | **双时态**：`valid_at/invalid_at/expired_at` + `reference_time`；新边可 invalidate 旧边（edge_operations L424-450）；旧事实保留可查 | 需要为每类实体定义 identity properties；时间解析失败会 warning 跳过（L325-339）；图/LLM 成本 |
| Mem0（M5） | `uuid4()` + md5(内容) 并存 | LLM 判 ADD/UPDATE/DELETE/NONE；history 记录 old/new/event（可追溯） | 冲突判断依赖 LLM；无时间有效性语义；删除后只能查 history 文本 |
| mcp-memory（M10） | **`content_hash` 当主键**（supersede 以 hash 配对） | 相似度带 [0.4,0.75] 判矛盾 → 新 supersede 旧，旧退出默认检索但保留 + contradicts 边 | **内容变即新身份**（与 LightRAG 同病）；阈值启发式 |
| DSH long-memory（M2） | entry `id`（调用方给）+ `sourceVersion` + topic revision CAS | 工具来源事实按 `sourceVersion` 过滤（过期不注入），并统计 `staleFacts`；编辑不允许改 id | **不保留历史**（注释明说 no version history）；上限 200 topics×20 entries |
| DSH team cards（M3） | member name / card path | 整卡重写；无版本链 | 8 KiB 截断；靠人/模型保证引用准确 |
| A-MEM（M13） | uuid + `evolution_history` | 新记忆可更新旧记忆属性（演化） | 无删除；演化历史只是列表，不能按时间点回放 |
| Basic Memory（M12） | `file_path` + `permalink` | 时间限定符（`@valid_during` 等）把"事实何时有效"写进内容；拒绝无法解析的时间 | AGPL；markdown 手写维护；无版本链 |
| Letta（M7） | block id + label；passage id | `is_deleted` 软删；summarizer 压缩（服务端未取到） | 服务端源码不可得 |

**结论（证据能支持的）**：
1. **没有一家用"内容哈希"当稳定逻辑身份**；唯一接近的是 mcp-memory 用 hash 做 supersede 配对，且它明确接受"内容变=新记忆"。
2. **成熟答案是三层**：稳定 id（uuid/路径/调用方 id）+ 时间/版本身份（valid_at / sourceVersion / history）+ 失效语义（invalidate / soft delete / supersede / stale 过滤）。
3. **"编辑后引用不丢"仍然没有免费实现**：Graphiti 靠"旧边保留 + invalid_at"，Mem0 靠 history，DSH 靠 sourceVersion 过滤；**都不是"同一个 chunk id 在编辑后继续有效"**。这与 E1-oss 的结论一致，但记忆轴补上了"时间维度"这个缺失件。

---

## 5. 回答 B：它们有没有"可判性摘要"类似字段？

先给判定口径：**"可判性摘要" = 一个能被程序判断真假/是否过期的摘要字段（带来源、版本、置信、权威）**，而不是"一段人读的总结"。

| 实现 | 最接近的字段 | 是否"可判" |
|---|---|---|
| Graphiti（M6） | `EntityNode.summary` + `attributes`；摘要由"边事实拼接/LLM 生成/按字符截断"（node_operations L991-1260） | **否**：摘要无来源/版本/置信；只有"可追溯到 episodes"的隐式关系 |
| Mem0（M5） | `memory` 文本（LLM 抽取的事实） | **否**：无来源/置信；history 只记录变更，不判断真假 |
| mcp-memory（M10） | `content` + `content_hash` + `access_count/quality` | **部分**：有 hash/访问/质量信号，可做"过期/低质"判断；**但没有语义真值** |
| A-MEM（M13） | `context/keywords/tags`（LLM 生成）+ `evolution_history` | **否**：属性是描述性的；演化历史可审计但不可判真 |
| LlamaIndex memory（M8） | `BaseMemoryBlock.description` + `priority` | **否**：description 是"块用途说明"，priority 是预算优先级 |
| Letta（M7） | block `description` + `limit` | **否**：description 是块用途；limit 是字符上限 |
| Basic Memory（M12） | `Observation{category, context, temporal}` + `temporal_error` | **部分**：`temporal_error` 表示"时间限定符解析失败"，是**可被程序判断的失败信号**；但内容真值仍靠人 |
| **DSH long-memory（M2）** | `kind∈{constraint,fact,experience}` + `source` + `sourceVersion` + 注入 `basis` | **最接近**：约束必须 user 来源、事实必须 tool 来源+版本；注入时明说"summaries not semantically verified; verify mutable facts"——**用"来源/版本/权威 + 免责声明"替代"真假字段"** |
| DSH team cards（M3） | 四节 + `authority: machine/self/lead/human` + 证据锚点 | **部分**：authority 是"谁说的"，证据锚点是 `file:line/commit`；仍无自动真值判断 |

**结论**：
1. **"可判性摘要"字段在开源/本机记忆系统里不存在**（与 E1-4 结论一致）。存在的是 **"来源可判"**（DSH kind+source+sourceVersion、Basic Memory temporal_error）与 **"权威可判"**（DSH authority）。
2. 若 Memoria 要做"可判性"，**最小可行近似是 DSH 的三件套**：`kind`（约束/事实/经验）+ `source`（谁说的/哪条工具调用/版本）+ 注入时的"未语义核验"声明；再加 Graphiti 的 `valid_at/invalid_at` 处理"事实会过期"。
3. **LLM 摘要不宜当"可判"来源**：Mem0/Graphiti/A-MEM 都允许摘要被后续记忆改写（Graphiti 的 summary 会 append/re-summarize；A-MEM 的演化会更新旧属性），且 LightRAG（E1-oss）已证明摘要会被 token 上限截断并持久化。

---

## 6. 回答 C：遗忘/合并策略是什么？

| 策略族 | 代表 | 具体做法 | 是否保留可恢复/可审计 |
|---|---|---|---|
| **双时态软失效** | Graphiti（M6） | 旧边 `invalid_at/expired_at`，不删；`resolve_extracted_edges` 返回 invalidated 列表 | **是**（可按时间回放） |
| **supersede + 图边** | mcp-memory（M10） | 相似度带 [0.4,0.75] 判矛盾 → `mark_superseded_batch` + `contradicts` 边；旧行退出默认检索 | **是**（仍可查） |
| **历史表 + 硬删除** | Mem0（M5） | LLM 决定 DELETE/UPDATE；history 存 old/new/event | 部分（history 文本可查） |
| **归档/压缩/删除** | mcp-memory（M10） | `ControlledForgettingEngine`：archive→`~/.mcp_memory_archive/{daily,compressed,metadata}`；低质 30–90 天不活跃后归档；动作 `archived/compressed/deleted/skipped` | **是**（归档可恢复） |
| **指数衰减 + 阈值** | mcp-memory（M10） | `exp(-age_days/retention_period)` × 重要度 × 连接 × 访问 × 质量；低相关阈值 0.1 | 衰减只排序/候选，不直接删 |
| **Ebbinghaus 曲线** | MemoryBank（P7） | 按时间 + 相对重要性"遗忘/强化" | 论文摘要未说是否保留原文 |
| **年龄淘汰** | Memary（M11） | `remove_old_memory(days)` 直接丢弃；`clear_memory` 清空 | **否** |
| **FIFO + 块截断** | LlamaIndex（M8） | 队列超 token limit 就 archive 最旧消息→推给 blocks；block `atruncate` 默认丢弃整块 | 部分（archive 到 SQL store） |
| **有界卡片截断** | DSH（M2/M3） | 2 KiB context 只取最近 4 条；8 KiB 卡片截断 + `truncated` 标记 | 部分（文件仍保留旧内容？截断即丢） |
| **记忆演化/合并** | A-MEM（M13） | 新记忆可更新旧记忆属性；每 100 次演化 consolidate 重建索引 | `evolution_history` 可审计 |
| **不遗忘** | Basic Memory（M12） | markdown 不删；靠时间投影过滤 | 是（文件即事实源） |

**结论**：
1. **主流是"软失效/归档"而不是"真删"**；只有 Memary 是纯年龄硬删（且它近两年未更新）。
2. **合并（merge）与遗忘（forget）是两件事**：Graphiti 合并的是实体/边（去重 + 摘要），失效的是边的时间；mcp-memory 合并的是相似记忆（supersede）；A-MEM 合并的是"属性/链接"。
3. **对 Memoria 的直接含义**：索引会随内容更新而失效时，**优先做"失效标记 + 可恢复"**（Graphiti/mcp-memory 模式），而不是删除重建；"删除"只用于明确不再需要的对象（且要有审计）。

---

## 7. 回答 D：分层记忆能否对应 L0/L1/L2 预算分层？

先对齐本仓定义（来自 `PROPOSAL-agent-arch.md` L169-171）：
- **L0**：`kb_overview`（文件清单 + KP 数），≤300 tok；
- **L1**：单文件 KP 索引（行号 + id + 名称），≤800 tok，超限分页；
- **L2**：读正文（snippet 600 / section 4000 / read_document 2000 行），单次推荐 ≤1.5k tok。

记忆系统的分层 vs 我们的预算分层：

| 记忆系统分层 | 实际含义 | 最接近我们的哪一层 |
|---|---|---|
| Letta core memory blocks（常驻系统提示，`limit` 字符） | 每轮都在上下文里 | **L0**（但字节量级 8 KiB vs 300 tok） |
| Letta archival passages（embedding 检索） | 按需召回 | **L2**（读原文片段） |
| LlamaIndex FIFO chat queue + blocks | 近期对话 + 压缩块 | FIFO≈L0/L1，blocks≈L1 |
| LangMem RunningSummary + store | 摘要常驻 + 长期检索 | summary≈L1，store≈L2 |
| Mem0 / Graphiti / A-MEM / mcp-memory | 长期记忆库，检索 top-k 注入 | **L1**（摘要/事实级）或 **L2**（episode 原文） |
| DSH long-memory 2 KiB + 最近 4 条 | 每轮注入的偏好/约束 | **L1**（但更小） |
| DSH team card 8 KiB / 注入 50 KiB | 每个 teammate 启动时注入 | L0/L1（一次性，非每轮） |

**关键判断**：
1. **结构可比，语义不同**：它们的"短期/长期"是**按持久性**分层（内存 vs 磁盘 vs 检索库）；我们的 L0/L1/L2 是**按注入预算**分层（给模型多少 token 去"看见"）。`L0/L1/L2` 不能直接叫"短期/长期记忆"。
2. **可借的功能映射**：
   - L0（路由/总览）↔ Letta core block / DSH team card / `kb_overview` —— 都是"固定小预算、每轮/每会话都注入"。
   - L1（方向感索引）↔ LlamaIndex memory blocks / LangMem summary / Mem0 的 facts —— "压缩后的可检索摘要"。
   - L2（正文）↔ Letta archival passage / Graphiti episode / Basic Memory note —— "按需拉原文"。
3. **不可直接搬的**：它们的预算是"记忆系统自定"（如 2 KiB/8 KiB/50 KiB），不是"按查询意图动态分配"；我们的 L0/L1/L2 是工具侧硬约束（PROPOSAL 已明确"工具侧硬约束 + 游标分页"），这一点比它们更严格。

---

## 8. 回答 E：有没有实测数字？

| 系统 | 数字 | 条件/边界 |
|---|---|---|
| Mem0（P5） | +26% relative LLM-as-Judge vs OpenAI memory；graph memory +~2% overall；p95 latency −91%；token cost −90%+ | LOCOMO benchmark；英文多会话对话；对比 full-context/OpenAI/RAG 等六类 baseline |
| Zep（P6） | DMR 94.8% vs MemGPT 93.4%；LongMemEval accuracy 最高 +18.5%；latency −90% | DMR + LongMemEval；企业场景；**论文许可 CC BY-NC-SA 4.0** |
| HippoRAG（P3） | 多跳 QA 最高 +20%；比 IRCoT 便宜 10–30×、快 6–13× | 多跳 QA；NeurIPS 2024 |
| MemGPT（P1） | **摘要无数字** | 文档分析 + 多会话聊天（正文可能有表，本报告未抓正文） |
| Generative Agents（P2） | **摘要无数字**（消融为定性） | 25 agents 沙盒 |
| A-MEM（P4） | **摘要无数字**（"six foundation models 上优于 SOTA"） | NeurIPS 2025 |
| MemoryBank（P7） | **摘要无数字** | 定性 + 模拟对话 |
| CoALA（P8） | **无数字**（框架论文） | TMLR |
| 本机 DSH | **无 agent-memory 效果数字**；`2026-10-07-memory-limited-benchmarks.md` 是 **RAM 上限**（4/8 GiB cgroup），**不是 agent 记忆效果**，本轴明确排除 | — |
| Basic Memory（M12） | 仓库有 benchmark 代码（locomo/longmemeval/beam 转换器）但**未运行、未取到结果** | AGPL |

**结论**：E 轴只有 Mem0/Zep/HippoRAG 三个可引数字，且都是英文对话/多跳 QA；**没有中文教材/个人知识库/长对话 agent 工具场景的数字**。

---

## 9. 与 E1-oss / E1-1 / E1-4 的关系（对 lead 的直接增量）

1. **E1-1（稳定身份 vs 漂移）缺失的"时间维度"在这里补上了**：Graphiti 的 `valid_at/invalid_at/expired_at` + Mem0 history + DSH `sourceVersion` 说明成熟做法是"**id 稳定 + 时间/版本可判 + 软失效**"，不是"换一个哈希"。
2. **E1-4（开源无"可判性摘要"）被进一步确认**：记忆插件也只有"摘要文本"（Mem0 memory、Graphiti summary、A-MEM context）与"来源可判"（DSH kind/source/version、Basic Memory temporal_error），**没有真假可判字段**。
3. **新增可搬件**：Graphiti 的"**summary 优先拼接、超限才 LLM、再按字符截断**"（node_operations L1121-1260）是"摘要成本控制"的具体实现；mcp-memory 的"**衰减 + 归档 + supersede**"是"索引失效"的具体实现；DSH 的"**kind/source/sourceVersion + 注入免责声明**"是"可判性"的最小近似。
4. **新增反例**：mcp-memory 用 `content_hash` 当身份做 supersede，说明"内容哈希当身份"在记忆域也有人用，但代价同样是"内容变=新记忆"。

---

## 10. 给 lead：3–5 条最值得搬 + 明确不搬 + 证据盲区

### 最值得搬（按"证据强度 × 落地成本"）

1. **Graphiti 的双时态软失效模式**（Apache-2.0；nodes.py L263-285、edge_operations L424-450）
   - 做法：给"事实/条目"加 `valid_at/invalid_at/expired_at`，新信息到来时**标记旧的失效而不是删除**；
   - 解决我们"索引随内容更新而失效"的问题，且保留可审计历史；
   - Memoria 落地：不需要图数据库也能做——在现有 manifest/sidecar 里加 `valid_from/valid_to/superseded_by` 三个字段即可；**代价**是每次检索要按时间过滤（可接受）。
2. **DSH 长记忆的"kind + source + sourceVersion"三件套 + 注入免责声明**（MIT；long-memory.js L8-28、L148-165）
   - 做法：记忆条目区分 `constraint/fact/experience`；约束必须 user 来源，事实必须 tool 来源 + 版本；每轮注入时明确"摘要未经语义核验"；
   - 这是"可判性"的**最小可行近似**，比 LLM 摘要可靠；**代价**是写入更麻烦（要带来源/版本）。
3. **LlamaIndex `Memory` 的"FIFO + blocks + token_limit×ratio"结构**（MIT；memory.py L188-217、L672-809）
   - 做法：短期队列按 token 预算淘汰→推给长期 blocks；读取时按 block priority 截断再注入；
   - 可映射我们的 L0/L1/L2；**代价**是它没有"每次查询动态预算"（我们已有工具侧硬约束，正好补它的缺口）。
4. **mcp-memory 的"衰减 + 归档 + supersede"组合**（Apache-2.0；decay L108-158、forgetting L48-153、contradictions L1-8/L24-28）
   - 做法：指数衰减只用于排序/候选；遗忘动作是 archive/compress/delete/skip（**默认归档而非删除**）；矛盾用相似度带判 supersede；
   - 适合"索引条目会过期"的场景；**代价**是阈值（0.4/0.75/0.1/30–90 天）需要按本仓数据校准，不能照搬。
5. **A-MEM 的"属性 + 链接 + 演化历史"**（MIT；memory_system.py L24-81、L237-290）
   - 做法：每条记忆带 `context/keywords/tags/links/evolution_history`，新记忆可更新旧记忆属性；
   - 适合"知识点之间有关联、会演化"的场景；**代价**是 LLM 生成属性 + 无删除策略（需配 4 的遗忘）。

### 明确不搬

- **Mem0 的"LLM 判 ADD/UPDATE/DELETE/NONE"当唯一冲突机制**：好实现但把正确性全押在 LLM 判断上，且无可判字段（本报告 M5 + P5）。
- **mcp-memory 用 `content_hash` 当身份主键**：与 E1-oss 的 LightRAG 反例同病（内容变=新记忆）。
- **Memary 纯年龄淘汰**（2024 年后未更新，且直接丢弃无归档）：不可恢复，违反审计需求。
- **Basic Memory 的代码**：AGPL-3.0，只能读思路；且 markdown 手写维护不适合本仓自动索引。
- **Letta/MemGPT 服务端实现**：源码已不在开源仓，**无法复制**；只能参考论文分层概念 + SDK 字段（block/passage）。
- **把"长期/短期"直接等同于 L0/L1/L2**：概念错位（见 §7）。
- **把 LLM 摘要当可判性来源**：Mem0/Graphiti/A-MEM 都允许摘要被后续更新，且 LightRAG（E1-oss）证明截断摘要会持久化。

### 证据盲区（未取到 / 不能声称）

1. **Letta/MemGPT 服务端源码**：`letta-ai/letta` main 只剩文档/政策（12 blob），**未取到** summarizer、memory tier 实现；只能用 SDK 生成类型 + 论文。
2. **A-MEM 的 `process_memory` 演化细节**：本报告只读了 `memory_system.py` 的入口与字段，未读 LLM controller/prompt（`llm_controller.py` 未抓）。
3. **Graphiti 的 `MAX_SUMMARY_CHARS` 具体值**：在 `dedup_helpers.py`/prompts 中，本报告只看到 `import` 与使用点，未抓到定义文件的常量值（**未取到**）。
4. **论文正文数字**：只抓了 arXiv abs 摘要；MemGPT/Generative Agents/A-MEM/MemoryBank 的正文表格数字**未取到**（摘要无数字）。
5. **任何中文/教材/个人知识库场景的实测**：全部没有；所有数字都是英文对话/多跳 QA。
6. **Basic Memory benchmark 结果**：仓库有 locomo/longmemeval/beam 转换代码，**未运行、未取到结果**；且 AGPL。
7. **DSH 三个 MCP provider 的实际记忆质量**：只有官方验收契约（write→fresh recall→use），**无召回率/成本数字**。

---

## 11. 检索与核对记录

- 本机：`D:\deepseek-harness\{.agents, docs, apps, packages, .dsh/profiles}`；`C:\Users\Lam Tim\\.agents\skills`（无 memory skill）；`C:\Users\Lam Tim\xerj-data\.xerj-memory-*`（XERJ 记忆索引）。
- GitHub 抓取（2026-10-27，HEAD 见 §2 各条）：mem0ai/mem0、getzep/graphiti、letta-ai/letta、letta-ai/letta-python、run-llama/llama_index、kingjulio8238/Memary、langchain-ai/langmem、basicmachines-co/basic-memory、doobidoo/mcp-memory-service、WujiangXu/A-mem-sys。
- 论文抓取：arXiv abs 页面 8 篇（2310.08560、2304.03442、2405.14831、2502.12110、2504.19413、2501.13956、2305.10250、2309.02427）。
- 失败与重试：`raw.githubusercontent.com` 多次超时/连接重置（A-MEM 首次失败→jsdelivr 成功；mcp-memory decay.py 首次半包→重抓）；GitHub API 查 Letta tree 确认 main 仅 12 blob；jsdelivr octet-stream 问题沿用 E1-oss 的校验流程（首字节+行数）。
- 校验规则：schema 字段只从代码/磁盘/文档抄录；"推断"单独标注（如 Graphiti 的 identity property 用途、mcp-memory 阈值需校准）；未取到项集中列 §10。

*（本文档仅为 C 源扩项取证，不含设计提案；未复制任何代码；未 commit。）*
