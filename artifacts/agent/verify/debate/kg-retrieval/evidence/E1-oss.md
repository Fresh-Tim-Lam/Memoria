# E1-C 源取证：优秀开源实现的索引单元 / 身份 / 同步 / 成本控制

> 角色：专职开源取证员（C 源）。**只做 E1，不写设计提案、不 commit。**
> 取证日：2026-10-27（Asia/Shanghai）。
> 方法：`curl`/`Invoke-WebRequest` 抓取 GitHub 源码快照 → 本地落盘 `evidence/_oss_src/` → 用精确行号逐条核对；本机 XERJ/AOCI 只读磁盘与 MCP 工具契约。
> 硬约束：每条给 **repo + 文件路径 + 行号或函数名 + 许可**；取不到就写"未取到"，**不凭印象描述实现**；行号来自 2026-10-27 的 main/master 快照，**会漂移**。
> 许可基线：LlamaIndex=MIT、LightRAG=MIT、LangChain=MIT、Aider=Apache-2.0。**本报告只摘签名/行为/字段，不复制实现体；AGPL/SSPL 未出现在本报告任何一条中。**

---

## 0. 先行结论（证据状态，不代替设计裁决）

| 子问题 | C 源证据状态 | 一句话 |
|---|---|---|
| ① schema 字段 / 可判性摘要 | **强**（4 个 OSS 仓 + 2 个本机参照） | 开源**没有**叫"可判性摘要"的字段；最接近的是两类：LlamaIndex 的 `metadata`（任意 KV + 可排除注入）与 LightRAG 的 `description`（LLM 抽取并合并，有摘要成本/截断风险）；本机 AOCI 的 `S` 字段是"非显然且防错"约束，不是描述 |
| ② 索引↔原文同步 | **强**（LlamaIndex docstore/index_store + LightRAG 状态机 + XERJ WAL/journal + AOCI baseline） | 主流做法是"**分层存储 + 内容哈希判变更 + 按文档级 ref_doc 级联删除**"；四家都没有单一事务，失败窗口靠状态机/日志补救，代码复杂度集中在这里 |
| ③ 身份 | **强**（代码可直接证明） | 共识是 **稳定 id 与内容哈希分离**：id 由调用方给，hash 只用于变更检测。反例是 LightRAG `doc_key = md5(全文)`（编辑即新文档）；LlamaIndex 默认 `id_ = uuid4()`（不传稳定 id 会重复入库） |
| ④ 体积/成本控制 | **强**（Aider 有硬 token 预算实现；LightRAG 有检索期预算；LlamaIndex 有按需回填父块） | 三种可组合手段：**硬 token 预算 + 排序 + 二分逼近**（Aider）、**分项 token 配额 + 截断**（LightRAG）、**检索到小单元后按比例回填父块**（LlamaIndex AutoMerging，不需要 LLM 摘要） |
| ⑤ 本机 XERJ / AOCI | **中**（能读磁盘布局与工具契约，读不到源码） | XERJ：**文件级 + 代码/段落级两层文档**、字段投影裁剪、segment+WAL+snapshot+journal 增量；AOCI：**路径为身份 + sha256 为漂移检测 + 机器签发批次 + 原子替换 receipts**。XERJ 的 `_id`/`ax_file` 算法、AOCI 的许可与源码均**未取到**，不许猜 |

---

## 1. 取证方法与快照（可复核）

### 1.1 抓取日与仓库 HEAD

| 仓库 | 许可 | 快照分支 | 抓取日 | 当日 HEAD commit / 时间 |
|---|---|---|---|---|
| run-llama/llama_index | MIT | `main` | 2026-10-27 | `619d74664e84` / 2026-10-14T15:29:28Z |
| HKUDS/LightRAG | MIT | `main` | 2026-10-27 | `aaebfe1bb8d5` / 2026-10-14T14:55:37Z |
| langchain-ai/langchain | MIT | `master` | 2026-10-27 | `575db57ab365` / 2026-10-26T23:00:03Z |
| Aider-AI/aider | Apache-2.0 | `main` | 2026-10-27 | `5dc9490bb35f` / 2026-05-22T14:02:20Z |

> HEAD 时间用 GitHub REST `commits?per_page=1` 取得（2026-10-27）。**行号只对上述快照成立**；`@main` 服务端缓存与 HEAD 可能有数小时差。

### 1.2 本地快照与完整性

- 源码副本：`artifacts/agent/verify/debate/kg-retrieval/evidence/_oss_src/`（`llamaindex/`、`lightrag/`、`langchain/`、`aider/`，含各自 LICENSE）。
- 每个文件落盘后做了"首字节 + 行数"人工校验（例如 `schema.py` 首字节 `"""Base schema for data structures."""`，`lightrag.py` 首行 `from __future__ import annotations`）。
- 抓取失败记录（**不隐瞒**）：
  - `raw.githubusercontent.com` 对 4 个文件多次超时/403（`auto_merging_retriever.py`、`ingestion/pipeline.py`、`langchain_core/documents/base.py`、部分 LICENSE）；改用 `cdn.jsdelivr.net` + GitHub Contents API（base64）补齐。
  - jsdelivr 对部分文件返回 `application/octet-stream`，PowerShell 写入方式一度把字节写成十进制文本；已丢弃并重新用 `curl.exe`/Contents API 落盘，校验首字节后重做。
- 未运行任何仓库代码、未装依赖、未执行 benchmark；**C 源所有"代价"都是读代码得出的结构性代价，不是实测性能数字。**

### 1.3 本机参照的只读边界

- XERJ：`C:\ProgramData\xerj\xerj.exe --insecure --data-dir "C:\Users\Lam Tim\xerj-data"`；MCP 进程 `C:/xerj/xerj-1.0.0-rc.96-x86_64-pc-windows-msvc/xerj.exe mcp`；索引内 `xerj_meta.json` 报 `1.0.0-rc.97`。**闭源 Rust 二进制，只能读数据目录 + MCP 工具契约。**
- AOCI：MCP 进程 `C:/aoci/bin/aoci.exe --repo D:/AAA_Jupyter/Memoria mcp`；可读 `aoci.txt` 根清单、`aoci.meta.txt`、`aoci.code.txt`、`.aoci/{config,baseline,ledger,governance,transactions}`。**无源码；许可文本未取到（不得推断为 MIT/Apache）。**

---

## 2. ① 索引单元 schema：有哪些字段？有没有"可判性摘要"？

### C1-1｜LlamaIndex `BaseNode` / `TextNode`：id、metadata、关系、模板、哈希分离

- **来源**：`llama-index-core/llama_index/core/schema.py`（MIT），`class BaseNode` L264-320、`class TextNode` L765-803、`class Document` L1097-1174；`node_parser/node_utils.py` L25-26。
- **字段（逐行核对）**：
  - `id_: str = Field(default_factory=lambda: str(uuid.uuid4()))`（L275-277）——**默认随机 UUID，不是内容哈希**；
  - `metadata: Dict[str, Any]`（L289-293，别名 `extra_info`，flat dict）；
  - `excluded_embed_metadata_keys` / `excluded_llm_metadata_keys`（L294-301）——同一份 metadata 可"给人看/给过滤"但**不进 embedding、不进 LLM prompt**；
  - `relationships`（L302-308，键为 `SOURCE/PREVIOUS/NEXT/PARENT/CHILD`，枚举 L207-224）；
  - `metadata_template` / `metadata_separator`（L309-320）——metadata 如何拼进文本可配置；
  - `TextNode.text` + `start_char_idx`/`end_char_idx` + `text_template`（L778-794）；
  - `hash` = `sha256(text + metadata)`（L800-803）；`node_id` 只是 `id_` 的别名（L382-388）。
- **有没有"可判性摘要"字段？没有专门字段。** 如果要放摘要，只能塞进 `metadata`（任意 KV），并用 `excluded_embed_metadata_keys` 控制它是否进入向量/提示。**代码本身不生成摘要。**
- **解决什么问题**：把"身份 / 内容 / 上下文元数据 / 图关系 / 哈希"拆成独立维度，使同一节点可以换 id、换 metadata 呈现方式而不动内容。
- **代价**：`metadata` 无 schema 约束（flat dict），字段治理靠调用方；`hash` 含 metadata，**改一个 metadata 键也会改变 hash**（L801-803），进而触发下游"内容变了"的判定。
- **Memoria 能否落地**：机制上完全可落地（纯 schema 设计）。约束：若 Memoria 的"知识点"要带摘要，需明确它是"人工/模型写入的 metadata"还是"计算生成字段"；LlamaIndex 不替你回答这一点。
- **许可**：MIT，可参考/可移植（保留版权与许可声明）；本报告未复制实现体。

### C1-2｜LlamaIndex `SentenceWindowNodeParser`：小单元 + 窗口上下文，但窗口**显式排除**出 embed/LLM

- **来源**：`llama-index-core/llama_index/core/node_parser/text/sentence_window.py`（MIT），L16-18、L40-52、L103-140。
- **做法**：每个 node = 一个句子（L110-115 `sentence_splitter` + `build_nodes_from_splits`）；把前后 `window_size=3` 句拼成 `metadata["window"]`（L118-127）；原文句子另存 `metadata["original_text"]`（L128）；随后把这两个 key **加入 `excluded_embed_metadata_keys` 与 `excluded_llm_metadata_keys`**（L130-136）。
- **解决什么问题**：检索仍按小句子做（精准），命中后由 retriever/postprocessor 用 `window` 回填上下文；因为窗口被排除，embedding 与 LLM 看到的仍是句子本身（不会因窗口文本污染向量）。
- **代价**：存储冗余（每个句子都存一份窗口文本）；**该 parser 只负责挂 metadata，回填逻辑不在本文件**（需要额外 retriever/postprocessor，本报告未追踪）。
- **Memoria 能否落地**：可落地，且比"摘要父块"便宜（零 LLM 调用）。约束：窗口文本会重复存储，索引体积随 `window_size` 线性涨。
- **许可**：MIT。

### C1-3｜LlamaIndex `HierarchicalNodeParser` + `AutoMergingRetriever`：多粒度切分 + 按命中比例回填父块

- **来源**：`node_parser/relational/hierarchical.py`（MIT）L76-110、L126-138、L160-205；`indices/vector_store/retrievers/auto_merging_retriever.py`（MIT）L26-47、L39、L56-125（比例合并）、L127-164（补洞）、L176-194（循环+排序）。
- **做法**：
  - 默认 `chunk_sizes=[2048, 512, 128]`（hierarchical.py L126-138），同文多粒度切分，返回**扁平 list**，靠 `PARENT/CHILD` 关系字段串起来（L14-22 建关系，L186-191 逐层添加）；父块与小句块**文本重叠**（L82-93 docstring 明说）。
  - 检索先用小节点；`AutoMergingRetriever` 取回父节点后算 `ratio = 命中子节点数 / 父节点子节点总数`（auto_merging L87），**ratio > `simple_ratio_thresh`（默认 0.5，L39/L90）就把子节点合并成父节点**；另外还会把检索结果之间"缺失的相邻节点"补进来（L127-164），并循环到不再变化（L186-190）。
- **解决什么问题**：不必为每个 chunk 生成 LLM 摘要（对比 RAPTOR 摘要树），就能在"小单元精准命中"与"父块完整上下文"之间折中；`while is_changed` 保证连续命中会被合并。
- **代价**：索引要存全部层级的文本（体积 ≈ Σ 各层）；父节点文本必须能从 docstore 取回（auto_merging L64-70 用 `storage_context.docstore.get_document`）；**该 retriever 没有 token 预算控制**，合并/补洞可能放大返回量，只在最后按相似度排序（L192-194）。
- **Memoria 能否落地**：可落地，但需先有 docstore 持久化父节点；若不存父块文本，就无法回填。
- **许可**：MIT。

### C1-4｜LightRAG `TextChunkSchema`：chunk 只存原文 + 定位，没有 description

- **来源**：`lightrag/base.py`（MIT）L79-84。字段仅 4 个：`tokens`、`content`、`full_doc_id`、`chunk_order_index`。
- **解决什么问题**：chunk 层保持"原文 + 可回溯定位（属于哪篇文档、第几块）"，语义全部放到实体/关系层，避免 chunk 级摘要再引入一遍噪声。
- **代价**：chunk 本身不可"按语义解释"，检索到 chunk 后仍需靠实体/关系描述解释。
- **Memoria 能否落地**：可落地（结构极简）。
- **许可**：MIT。

### C1-5｜LightRAG 实体/关系 schema：`description` 是 LLM 抽取并**合并摘要**的字段（最接近"摘要"）

- **来源**：`lightrag/prompt.py`（MIT）L56-110（抽取字段与行格式）；`lightrag/operate.py`（MIT）L372-530（`_handle_entity_relation_summary`）、L2429-2548（实体合并）、L2782+（关系合并，`src_id`/`tgt_id`/`keywords`/`description`/`source_id`/`file_path`）；`lightrag/lightrag.py` L2745-2789（chunk 行）。
- **字段**（从抽取 prompt + 合并代码核对）：
  - 实体：`entity_name`、`entity_type`、`entity_description`；存储侧还有 `source_id`（来自哪些 chunk）、`file_path`、`created_at`、`description`（prompt.py L60-65；operate.py L2451-2486、L2488-2532）。
  - 关系：`source_entity` → `target_entity`、`relationship_keywords`、`relationship_description`（prompt.py L67-74）；存储侧 `src_id`、`tgt_id`、`keywords`、`description`、`source_id`、`file_path`（operate.py L2783-2849），关系按**无向**处理（prompt.py L100）。
  - 抽取输出行数上限：`max_total_records` / `max_entity_records`（prompt.py L95-97）。
- **合并规则（关键）**：`_handle_entity_relation_summary` 用 **map-reduce** 合并多份 description：总 token < `summary_context_size` 且条数 < `force_llm_summary_on_merge` 时直接拼接（L436-448）；否则按 `summary_context_size` 分批 → 每批 LLM 摘要 → 递归（L466-530）。合并实体时 `source_id` 去重合并，并受 `max_source_ids_per_entity` 限制（L2511-2532），限制策略 `KEEP` 会把超出上限的 chunk 来源**丢掉**（L2534-2548）。
- **解决什么问题**：实体/关系是跨文档复用的"语义单元"，`description` 提供可读的语义摘要；`source_id` 提供回溯源 chunk 的引用。
- **代价（读代码可见）**：
  - 摘要需要 LLM 调用；**截断会直接变成持久 description**，代码为此专门做 `truncation_tally` + `truncation_write_ahead`（operate.py L550-561、lightrag.py L2745-2763）——说明作者把"截断摘要落库"当作数据风险来管理；
  - `source_id` 有上限，KEEP 策略下超出部分来源被丢弃（L2534-2548），**引用完整性是有损的**；
  - 关系按无向合并（prompt.py L100），方向语义丢失。
- **Memoria 能否落地**：结构可借鉴（`description` + `source_id` + `file_path` 三件套），但**若 Memoria 要"可判性"，不能直接照搬 LLM 摘要**：它需要 LLM、会被截断、合并后可追溯性下降。这是 C 源最强的"摘要字段"证据，也是最强反证。
- **许可**：MIT。

### C1-6｜本机 XERJ `ax-docs`：没有摘要字段，只有"多粒度原文投影"

- **来源**：`C:\Users\Lam Tim\xerj-data\ax-docs\schema.json`（schema version 23，updated 2026-10-21）、`es_mapping.json`、`settings.json`、`snapshot.json`；以及 MCP `xerj_map`/`xerj_search` 实测返回（2026-10-27）。
- **字段全集（schema.json 逐项）**：`body`、`code`、`defs`、`kind`、`language`、`line`、`end_line`、`impl`、`name`、`path`、`section`、`start_line`、`symbol_count`、`text`、`title`、`ax_path`、`ax_paths`、`ax_file`、`ax_locator`、`ax_dataset`、`ax_run`、`ax_format`，以及嵌套 `symbols{name, kind, line, end_line}`。
- **实测文档形态（51 docs，`_id` 32-hex）**：同一文件 `maintain.mjs` 同时存在
  - 文件级 doc：`title/ax_path/ax_file/ax_locator="file"/ax_format="code"`；
  - 代码级 doc：`language/defs/symbols[]/symbol_count/body/ax_locator="code"`；
  - JSON 文件还有 section 级 doc：`section=0/1`、`ax_locator="s0"/"s1"`、`ax_format="json"`。
- **有没有摘要？没有。** `impl/code/body/text` 都是原文（或原文片段），`defs` 是符号名列表，不是 description。
- **解决什么问题**：以"文件/代码/段落"三种粒度提供可检索的原文投影，并把 `ax_*` 作为引用与溯源元数据（dataset / run / format / file fingerprint）。
- **代价**：同一内容在多粒度重复存储（`xerj_map` 覆盖率显示 code 56.8%、body 18.9%、text 24.3%，说明字段是稀疏异构的，查询要区分 doc 种类）；`_id`/`ax_file` 生成算法未取到。
- **Memoria 能否落地**：只能借鉴"多粒度投影 + 溯源字段"思路；**不能复制机制**（闭源）。
- **许可**：未取到（闭源产品，不适用开源许可）。

### C1-7｜本机 AOCI：`F/R/A/S` 四段式，`S` 是"非显然且防错"约束（不是描述）

- **来源**：`aoci.meta.txt` L1-15、`aoci.code.txt`（470 条 entry）、`.aoci/baseline.json`。
- **Entry 形态**（meta L10 例子）：`file.go[EG7T]: F:运行示例应用 | R:code:config/load.go | A:main | S:配置文件缺失时直接非零退出，不回退到内置默认值`
  - `F`：文件职责（压缩后的"这是干什么的"）；
  - `R`：关系（指向其他 `code:path`）；
  - `A`：入口锚点（如 `main`）；
  - `S`：**"non-inferable-and-error-preventing"** 的非显然约束（meta L5 明确写出准入规则）。
- **规模与配额**：`aoci.code.txt` 588 行 / **470 条 entry**；平均 61 字节、max 323；**S 非空仅 17/470（3.6%）**；带 `R:code:` 引用的 32 条。meta L6 明确条目预算：`C9-8≤600 C7-4≤200 C3-1≤50`（按 tag 的 C 重要度与 E 规模给大小配额）。
- **有没有"可判性摘要"？有最接近的东西：`F`（职责摘要）+ `S`（防错约束），但两者都是"模型/人创作的语义"**，不是从文件自动计算出来的字段；且单位是**整文件一条 entry**，不是 chunk。
- **代价**：每条 entry 要人/模型读文件后写；文件改动后 entry 语义可能失效，需要维护流程复核（见 §4 C2-5 的 `maintain repair_required` 记录）。
- **Memoria 能否落地**：`F` + `S` 的分工可直接借鉴（"摘要"与"防错约束"分开，后者宁缺毋滥，AOCI 自己只有 3.6% 条目写 S）。
- **许可**：**未取到**（AOCI 无源码；不能假定开源）。

### ① 小结

1. **没有一个 OSS 仓把"可判性摘要"做成索引单元的必填字段**。存在的是三种替代：
   - `metadata` 任意 KV（LlamaIndex，可排除注入）；
   - LLM 生成的 `description`（LightRAG，成本/截断/可追溯性有损）；
   - 人工/模型创作的 `F`+`S`（AOCI，质量高但不可自动规模化）。
2. **"摘要"与"原文"在代码里是分开的层**：LlamaIndex 的 node text 是原文、metadata 是附注；LightRAG 的 chunk 是原文、实体 description 才是摘要；XERJ 全是原文投影。**把摘要塞进 chunk 正文的开源实现，本报告未取到。**
3. 可判性相关的真正设计点是 `excluded_embed_metadata_keys` 这类**"同一字段对不同消费者可见性不同"**的机制（LlamaIndex schema L294-301）——它允许"给检索/给 LLM/给人"看到不同内容，而不必复制文本。

---

## 3. ② 索引与原文档如何保持同步？

### C2-1｜LlamaIndex 三层存储：docstore / index_store / vector store 各管一段

- **来源**：`storage/index_store/keyval_index_store.py`（MIT）L38-89；`storage/docstore/keyval_docstore.py`（MIT）L93-125、L143-205、L207-245、L352-368、L401-421、L557-598、L599-660；`indices/vector_store/base.py`（MIT）L219-258、L423-431。
- **做法**：
  - `KVIndexStore.add_index_struct` 以 `index_struct.index_id` 为 key 存索引结构（keyval_index_store L38-48）；`get_index_struct` 反序列化（L60-78）。
  - docstore 按 node 存三份：node 本体（含 text）、`{doc_hash, ref_doc_id}` 元数据、`ref_doc_id → {node_ids, metadata}` 引用文档记录（keyval_docstore L93-125、L143-205）。
  - vector index 写入：先 `vector_store.add`（L232）；若 vector store 不存文本，再 `index_struct.add_node` + `docstore.add_documents`（L234-245）。
  - 删除：`delete_ref_doc(ref_doc_id)` 先删 vector store，再按 ref_doc_info 的 node_ids 删 index struct、可选删 docstore（vector_store/base L423-431、L410-421）。
- **解决什么问题**：把"向量索引（可重建）/ 文档存储（事实源）/ 索引结构（路由）"解耦；删除以**文档级 ref_doc_id** 为单位级联。
- **代价**：**不是单一事务**：vector store、index struct、docstore 三次写入分步进行（L423-431），中途失败会留下半状态；代码没有回滚事务，只靠"每次写完再 `index_store.add_index_struct`"把索引结构当提交点。
- **Memoria 能否落地**：可落地（LlamaIndex 全 MIT）；但要接受"分步写 + 以索引结构为提交点"的弱一致模型。
- **许可**：MIT。

### C2-2｜LlamaIndex ingestion pipeline：hash 驱动的增量重算（最可直接对照的实现）

- **来源**：`ingestion/pipeline.py`（MIT）L242-259（策略枚举）、L451-467（`_handle_duplicates`）、L469-507（`_handle_upserts`）、L518-536（`_update_docstore`）。
- **做法**：
  - 默认策略 `DocstoreStrategy.UPSERTS`（L340-341）。
  - `_handle_upserts`：对每个 node 取 `ref_doc_id = node.ref_doc_id or node.id_`，查 docstore 里存的 hash（L479-481）；
    - 无记录 → 新增（L482-484）；
    - **hash 不同 → `docstore.delete_ref_doc(...)` + `vector_store.delete(ref_doc_id)`，再重新加入**（L485-491）；
    - hash 相同 → **跳过、不重算**（L492-493）；
    - `UPSERTS_AND_DELETE` 额外把"本次没有出现"的旧文档删掉（L495-506）。
  - `_handle_duplicates`：只看 hash，不看 id（L451-467）。
  - 成功后 `set_document_hashes` + `add_documents`（L527-532）。
- **解决什么问题**：只有内容变化才重算 embedding/索引；被删除的文档能级联清掉向量与 docstore。
- **代价（读代码可见的具体风险）**：
  - 变更判定是 `docstore` 里 `ref_doc_id → hash` 的映射，**前提是重投时 `ref_doc_id` 稳定**；LlamaIndex 的 `Document.id_` 默认 uuid4（schema L275-277、node_utils L25-26），**调用方不显式给稳定 doc id 的话，同一文件重投会得到新 id → 永远走"新增"分支**。这是"稳定身份"与"内容哈希"分离的直接代价。
  - hash 含 metadata（schema L801-803），改 metadata 也会触发重算；
  - 删除不是事务，且先删 docstore 再删 vector store（L486-489），中间失败会有悬挂向量。
- **Memoria 能否落地**：可落地；**必须同时设计"稳定 doc id 的来源"**（路径？显式 id？id_func？），否则该机制不生效。这一点是 E1 ③ 的关键约束。
- **许可**：MIT。

### C2-3｜LightRAG 存储分层 + 文档状态机（内容哈希 + 分阶段处理）

- **来源**：`lightrag/lightrag.py`（MIT）L1825-1901（存储初始化）、L2442-2465（doc/chunk 身份）、L2745-2789（chunk 行）；`lightrag/base.py`（MIT）L1317-1372（状态机与 DocProcessingStatus）。
- **分层**（lightrag.py L1825-1901）：
  - KV：`llm_response_cache`、`text_chunks`、`full_docs`、`full_entities`、`full_relations`、`entity_chunks`、`relation_chunks`；
  - 图：`chunk_entity_relation_graph`；
  - 向量库三个，各带 `meta_fields`：entities `{entity_name, source_id, content, file_path}`、relationships `{src_id, tgt_id, source_id, content, file_path}`、chunks `{full_doc_id, content, file_path}`（L1876-1893）；
  - 状态：`doc_status`（L1896-1901）。
- **状态机**：`PENDING → PARSING → ANALYZING(可选) → PROCESSING → PROCESSED | FAILED`（base.py L1317-1330）。`DocProcessingStatus` 字段：`content_summary`（前 100 字符预览）、`content_length`、`file_path`（**basename，明确说明不是唯一键**）、`status`、`created_at/updated_at`、`chunks_list`（用于删除）、`content_hash`（**MD5 of underlying document content，用于与 file_path basename 一起去重**）（base.py L1332-1372）。
- **增量**：代码里有按状态分页扫描（`get_docs_by_statuses_page`，lightrag.py L3400 附近）、按状态取候选（L3418），说明处理是"扫 doc_status 找待处理文档"而不是每次全量重算。
- **解决什么问题**：文档生命周期可观测、可重试、可删除（chunks_list 支持按文档删）；内容哈希 + basename 用于重复检测。
- **代价**：为维护状态与数据一致，`lightrag.py` 里出现大量"失败阶段/删除修复/缓存引用/claims"逻辑（如 L3832-3842、L4286-4326、L6674-6679 的注释与专门方法），**复杂度是这套状态机的真实成本**；本报告未逐条读完 8k 行，只取证结构与状态机。
- **Memoria 能否落地**：可借鉴"文档状态机 + 按状态扫描"；不建议照搬其一致性修复代码（体量与风险都大）。若 Memoria 只需要"内容变才重算"，LlamaIndex 的 hash 对比更小。
- **许可**：MIT。

### C2-4｜本机 XERJ：segment + WAL + snapshot + journal 的增量替换

- **来源**：`C:\Users\Lam Tim\xerj-data\ax-docs\` 与 `autoindex-catalog\` 磁盘；`C:\Users\Lam Tim\.xerj\autoindex\*\journal.ndjson`。
- **盘上结构**（每个索引目录）：`schema.json`、`es_mapping.json`、`settings.json`、`snapshot.json`、`analysis-binding.json`、`created_at.json`、`xerj_meta.json`、`segments/`、`wal/`。
  - `snapshot.json`（ax-docs）：`{segments:[{doc_count:51,size_bytes:28973,min_seq_no:1,max_seq_no:51,has_tombstones:false}], generation:16, max_seq_no:51}`——**generation + seq_no + tombstone 标志**，是 LSM 式增量索引的提交点。
  - `segments/` 每段是列存：每个字段一组 `.fst/.meta/.norms/.post`，另有 `.seg`、`.sidx`、`.ids`、`.dv`（Lucene 风格）。
  - `wal/0000000000000001.wal` 当前 16 字节（空 WAL）。
- **autoindex（代码仓索引）**：`autoindex-catalog` 的 `es_mapping` 存**数据集级元数据**（`doc_kind/slug/index_name/record_count/bytes/file_count/formats/time_field/semantic_field/fields_json/sample_queries_json/...`），与内容索引分离。
- **journal.ndjson**（一次 run，704 行）：`kind` 分布 = `file_replace_start` 350、`file_done` 350、`run` 1、`plan` 1、`finish` 1、`embedding_identity` 1；run 记录含 `root/url/prefix/run_id/started`。另有 `plan` 与 `finish`，以及曾观察到 `.autoindex-stage-*` 暂存文件——**按文件"替换 + 完成标记"的增量重跑，带运行日志**。
- **解决什么问题**：增量化（按文件替换）+ 可审计（journal）+ 可恢复（WAL/segment/snapshot）；字段级列存让"只取需要的字段"变便宜。
- **代价**：闭源，**崩溃恢复语义、WAL 提交协议、`_id` 生成规则都读不到**；只能把"磁盘布局 + journal 事件种类"当事实。
- **Memoria 能否落地**：只能做"参考设计"（文件级增量 + journal + 显式提交快照），不能复制实现。
- **许可**：未取到（闭源）。

### C2-5｜本机 AOCI：baseline sha256 + 机器签发批次 + 原子替换 receipts

- **来源**：`.aoci/baseline.json`、`.aoci/ledger.jsonl`、`.aoci/governance/*.json`、`.aoci/config.json`、`aoci.txt`、`aoci.meta.txt`；MCP 工具契约 `aoci_maintain` / `aoci_update_entry`（本会话注入的工具描述）。
- **baseline.json**：`{version, created_at, updated_at, files:{<repo-relative path>:{role, sha256, size, normalized_sha256}}, managed_scope}`；**583 个文件**（role=`index` 508、`observe` 75）。→ 身份是**路径**，sha256（含 `normalized_sha256`）用于**漂移检测**。
- **ledger.jsonl**：228 条事件，`op` 分布：`remove_entry` 91、`auto_finalize` 35、`maintain` 34、`update_entries_batch` 32、`overview` 13、`rules` 8、`cognition_check` 8、`update_entries_batch_recover` 3、`header_show` 2、`scan` 1、`managed_scope_change_apply` 1；`maintain` 事件多次 `result="repair_required"`（如 2026-10-11 三次，paths_count 23–28，duration 42–46s）。→ 增量维护是真实的，且**经常需要修**，不是全自动。
- **governance receipts**（26 个）：`{receipt_id, kind:"entries", transaction_id, pre_index_sha256, post_index_sha256, paths:["aoci.code.txt"], completed_at}`。→ **写入是整卷 CAS/原子替换**（pre/post 摘要 + transaction_id）；部分失败/恢复有独立 op（`update_entries_batch_recover`）。
- **MCP 契约**（工具描述，非源码）：`aoci_maintain` 返回机器签发批次，每候选绑定 `source_sha256`/`candidate_id`；`aoci_update_entry` 必须提交**完整批次**，禁止字段 Patch。→ 语义更新与源字节摘要绑定；**禁止增量字段改写**，只能整条替换。
- **解决什么问题**：内容漂移可检测（sha256）、语义更新可审计（ledger + receipts）、写入失败可恢复（transaction + recover op）。
- **代价**：漂移检测只回答"变了"，**不回答"语义哪里变"**；每次变更需要模型/人重写 entry（`repair_required` 记录印证）；全卷 CAS 意味着条目多时写放大。
- **Memoria 能否落地**：baseline+receipts 模式可借鉴；但 AOCI 的 `maintain` 仍是"模型参与重写"，**不能当成全自动同步方案**。
- **许可**：未取到（无源码）。

### ② 小结

1. **四家都没有"单一事务"**：LlamaIndex 以 index struct 为提交点；LightRAG 用 doc_status 状态机；XERJ 用 WAL/segment/snapshot+journal；AOCI 用整卷 CAS + receipts。**"同步"在代码里 = "生命周期状态 + 内容哈希 + 可恢复提交点"三件事。**
2. **内容哈希判变更**是共同点：LlamaIndex `sha256(text+metadata)`、LightRAG MD5、AOCI sha256+normalized_sha256；**但哈希不承担身份**（见 ③）。
3. **删除必须以文档/文件为单位级联**（LlamaIndex `ref_doc_id`、LightRAG `chunks_list`）；只删 chunk 不删文档引用会留下悬挂。
4. **代价都落在"弱一致窗口"**：分步写、失败恢复、缓存引用、状态修复——LightRAG 的 8k 行与 AOCI 的 26 个 receipt 都在为这件事付账。

---

## 4. ③ 身份：节点 id 是内容哈希还是稳定 id？编辑后如何不丢引用？

### C3-1｜LlamaIndex：`id_` 默认随机 UUID，`hash` 才是内容哈希（两者分离）

- **来源**：`schema.py` L207-224（关系枚举）、L275-277（`id_` 默认 uuid4）、L289-320（metadata/关系）、L382-456（`node_id`/`source_node`/`prev/next/parent/child`/`ref_doc_id`）、L765-803（TextNode/hash）、L1097-1174（Document 的 `doc_id` 只是 `id_` 别名）；`node_parser/node_utils.py` L25-26（`default_id_func` 返回 `str(uuid.uuid4())`）；`keyval_docstore.py` L93-125、L599-660。
- **可以直接证明的事实**：
  - `node_id` 不是内容哈希：默认 `uuid4`（schema L275-277 + node_utils L25-26）；`hash` 单独存在且 = `sha256(text+metadata)`（L800-803）。
  - `Document.doc_id` 只是 `id_` 的别名（L1104-1118、L1167-1174）；`id_` 仍是 uuid4 默认。
  - `ref_doc_id` 来自 `relationships[SOURCE].node_id`（L390-404、L450-456）——是**文档级引用**，不是 chunk 自身 id。
  - docstore 存 `{doc_hash, ref_doc_id}`（L93-125），并以 `ref_doc_id` 删除整个文档的 node 列表（L557-598）。
- **解决什么问题**：id 可以稳定（由调用方指定：路径哈希、业务主键、显式 UUID），hash 只用于"内容是否变了"；引用用 `SOURCE` 关系指向文档，编辑文档可用同一 `doc_id` 做 upsert。
- **代价（关键）**：**默认不提供稳定 id**。不传稳定 doc id / 不自定义 `id_func` 时，每次解析都是新 uuid4 → 重投会被当新文档（配合 C2-2 的 `_handle_upserts` 直接重复入库）。这不是 bug，是"库把选择权留给调用方"；但对"编辑后引用不丢"来说，**这是必须自己补的一层**。
- **Memoria 能否落地**：机制可落地；**必须显式定义 Memoria 的 doc id 规则**（否则引用稳定性无从谈起）。
- **许可**：MIT。

### C3-2｜LangChain `Document.id`：提供槽位，但不强制策略

- **来源**：`langchain-core/langchain_core/documents/base.py`（MIT）L34-56（`BaseMedia.id` + 注释）、L288（`class Document`）、L306（`page_content`）。
- **代码原文（L45-53）**：`id: str | None = Field(default=None, coerce_numbers_to_str=True)`；注释写"**The ID field is optional at the moment. It will likely become required in a future major release**"；docstring 写"ideally unique across the document collection and formatted as a UUID, but this will not be enforced"。
- **解决什么问题**：给 Document 一个显式身份槽位；把"身份"和 `metadata` 分开。
- **代价**：**不强制、不生成、不校验唯一性**；是否稳定、要不要用，完全交给 loader/vectorstore。本报告**未取证**各 VectorStore 实现如何使用该 id（不能声称"生态都按 id upsert"）。
- **Memoria 能否落地**：可落地（字段语义清晰）；但 LangChain 自身不提供"编辑后引用不丢"的机制。
- **许可**：MIT。

### C3-3｜LightRAG：`doc_key = md5(全文)`，chunk id 是"文档域内"的内容哈希（反例）

- **来源**：`lightrag.py` L2442-2465（doc_key 与 chunk id）、L2454-2471（chunk_entries / operation_id）、L2777-2789（chunk 行字段）、L2289/L2345（`ainsert` 文档说明 "if not provided, MD5 hash IDs will be generated"）；`base.py` L1367-1372（`content_hash` MD5）。
- **做法**：
  - `if doc_id is None: doc_key = compute_mdhash_id(full_text, prefix="doc-") else: doc_key = doc_id`（L2442-2445）——**默认内容寻址**；调用方可传 `ids` 覆盖（ainsert docstring L2345）。
  - chunk id = `make_custom_chunk_id(doc_key, chunk_text)`，注释明确"**deterministic, document-scoped identity: chunk ids hash (doc_key, content)**... so identical text in two documents never shares a chunk row"（L2447-2460）。
  - chunk 行：`content/full_doc_id/tokens/chunk_order_index/file_path`（L2777-2789）。
- **解决什么问题**：默认情况下"同一字节 = 同一文档"，天然去重；chunk id 文档域内哈希，避免两份文档的相同段落共享一行导致 `full_doc_id` 被覆盖（L2447-2452 注释直接说明这个动机）。
- **代价**：**编辑一个字 → doc_key 变 → 整篇文档的 chunk id 全变**；旧文档要靠 doc_status/删除逻辑清理；跨版本引用（chunk id）无法保持。要稳定身份必须由调用方传 `ids`（ainsert L2345）。
- **Memoria 能否落地**：**不建议把"内容哈希 = 文档身份"直接搬**到会持续编辑的知识点；若借用，必须同时提供"显式 id 通道"（LightRAG 确实留了 `ids`）。
- **许可**：MIT。

### C3-4｜本机 XERJ：`_id` 与 `ax_file` 双标识，但算法未取到

- **来源**：`ax-docs` 索引实测（`xerj_search` 返回 `_source`）与磁盘 `schema.json`。
- **观察到的事实**：
  - 每个 doc 有 `_id`（32-hex，如 `215ea62954dba76e86b896dd635bb4c2`）；
  - 每个 doc 有 `ax_file`（形如 `axf2-57b5a5b0c100261b8323c4c7aeb2c565-24e8`，不同 doc 不同）；
  - 同一文件 `maintain.mjs` 的"文件级 doc"与"代码级 doc"是**两个不同 `_id`**（证明身份是"文档单元级"，不是"文件级唯一"）；
  - `ax_path/ax_paths/ax_locator/ax_run/ax_dataset/ax_format` 是引用与溯源字段。
- **未取到**：`_id` 与 `ax_file` 的生成规则（是否内容哈希、是否含路径/时间），WAL 提交协议，崩溃恢复语义。**不猜。**
- **解决什么问题（可从字段命名推断，但仅此而已）**：`ax_file` 像"文件指纹"用于去重/引用，`ax_path`+line/section 用于定位；`ax_run` 记录来自哪次建索引。
- **代价**：身份不透明，外部无法验证"同一文件两次索引是否同 id"（本报告只有一次快照）。
- **Memoria 能否落地**：只能借鉴"指纹字段 + 定位字段并存"这一形态。
- **许可**：未取到。

### C3-5｜本机 AOCI：路径即身份，sha256 只做漂移检测

- **来源**：`aoci.meta.txt` L9（`Code canonical identity example: code:path/to/file.go`）、L10（Entry 例子）；`.aoci/baseline.json`（583 个 path→role/sha256/size/normalized_sha256）；`.aoci/ledger.jsonl`（`remove_entry` 91 次）。
- **事实**：Entry 的规范身份是 `code:<仓库相对路径>`；baseline 以路径为 key 存 sha256；文件删除/重命名表现为 `remove_entry` + 新路径 entry（ledger 里有 91 次 remove_entry）；R 字段的引用写 `code:path`（aoci.code.txt 里 32 条带 `R:code:`）。
- **解决什么问题**：路径稳定且人类可读；hash 变化只触发"这条 entry 需要复核"，不改变身份；引用按路径可跨版本。
- **代价**：重命名 = 删除+新增（引用需同步更新，否则悬空）；路径冲突/移动无法表达"同一逻辑对象改名"；hash 变→仍需模型/人重写 entry（C2-5 的 repair_required）。
- **Memoria 能否落地**：**这是与本仓现状最接近的参照**（路径 + 内容摘要 + 语义条目），落地成本低；但它解决不了"知识点跨文件移动"的身份连续性问题。
- **许可**：未取到（无源码）。

### ③ 小结（能支持到什么程度）

1. **"稳定 id 与内容哈希分离"是 4 个 OSS 仓里 3 个（LlamaIndex/LangChain/AOCI）的共同结构**：id 管引用，hash 管变更。LightRAG 是**明确的反例**（默认内容寻址，编辑即换 id），但自己也留了 `ids` 显式通道。
2. **"编辑后不丢引用"没有免费实现**：
   - LlamaIndex：要调用方提供稳定 doc id（否则 uuid4）；
   - LightRAG：要调用方传 `ids`；
   - LangChain：只给槽位；
   - AOCI：靠路径 + 人工/模型维护引用；
   - XERJ：算法不可见。
3. **chunk 级身份比文档级身份更难稳定**：LightRAG 用 `(doc_id, content)` 域内哈希；LlamaIndex 用独立 uuid + `SOURCE` 关系指文档。**本报告未取到任何"chunk id 在编辑后仍稳定"的开源实现。**
4. 结论只能到"证据约束"：若 Memoria 的索引单元会持续编辑，把内容哈希当身份会直接违背引用稳定性（LightRAG 的 `md5(全文)` 是最好的反例代码）；若要求引用可追溯，必须有请求方/维护方提供的稳定 id 通道（LlamaIndex `id_`、LangChain `Document.id`、LightRAG `ids` 三者都留了这个口子）。

---

## 5. ④ 体积/成本控制：分层展开、按需加载、预算截断

### C4-1｜Aider repo map：硬 token 预算 + PageRank 排序 + 二分逼近（最完整的预算实现）

- **来源**：`aider/repomap.py`（Apache-2.0）L42-72（默认值）、L103-167（`get_repo_map` 预算逻辑）、L365-445（personalization）、L490-514（边权启发式）、L524-545（PageRank）、L629-706（二分搜索）、L708-782（`render_tree`/`to_tree` 只出签名行）、L43/L217-262（mtime+sqlite 缓存）。
- **做法（逐段核对）**：
  - 默认 `map_tokens=1024`（L49），`max_map_tokens`（L70）；无文件在 chat 时 `target = min(max_map_tokens * map_mul_no_files(=8), max_context_window - 4096)`（L122-132）；
  - `get_ranked_tags`：以 chat 文件/提及文件为 personalization（L424-445），按"被引用次数 + 标识符形态"加权（`num_refs = math.sqrt(num_refs)` 防止高频词主导，L511-514；mention ×10、长标识符 ×10、下划线开头 ×0.1、被 >5 处定义 ×0.1，L492-499），跑 PageRank（L524-525），再把 rank 分摊到定义（L533-545）；
  - `get_ranked_tags_map_uncached`：对"取前 middle 个 tag 渲染后的 token 数"做**二分搜索**，接受 `pct_err < 0.15` 的近似（L676-706）——**不是精确填满，而是 ±15% 容差**；
  - 输出只含**签名/行号范围**：`render_tree` 用 TreeContext 只保留 lines-of-interest 上下文（L710-746），`to_tree` 每行截断 100 字符（L781-782）；不输出函数体。
  - 缓存：`TAGS_CACHE_DIR = ".aider.tags.cache.v{CACHE_VERSION}"`（L43），按 mtime 失效（L217-262）。
- **解决什么问题**：在**固定 token 预算**下给 agent 最大信息量的仓库全貌；排序用图中心性而不是文件顺序。
- **代价**：只给签名，命令/实现细节要再读文件；二分搜索每次要多次渲染+token 计数（有 tree_cache 缓解，L708/L745）；repo 大时首次扫描慢（L391-395 自己提示）；依赖 tree-sitter 解析质量（本报告未读 parser）。
- **Memoria 能否落地**：**预算机制可搬**（硬上限 + 排序 + 二分/贪心 + 容差），但 **PageRank 的部分不可直接搬**——它依赖"代码定义-引用图"，中文教材/讲义没有这种图；能借的是"按重要性排序 + 预算内截断"。
- **许可**：Apache-2.0；若复制代码需保留 LICENSE/NOTICE 并声明修改；**本报告只取思路，未复制代码**。

### C4-2｜LightRAG：检索期分项 token 配额 + 抽取/摘要期上限 + 来源数上限

- **来源**：`lightrag/base.py`（MIT）L89-135（QueryParam）；`lightrag/constants.py`（MIT）L59-61（默认值）、L76-81（source ids limit）；`lightrag/operate.py`（MIT）L5501-5610（`_apply_token_truncation`）、L412-416（summary 限额）、L2524-2532（source ids 限额）；`lightrag/prompt.py`（MIT）L95-97（输出行数上限）。
- **数值（constants.py L59-61）**：`DEFAULT_MAX_ENTITY_TOKENS=6000`、`DEFAULT_MAX_RELATION_TOKENS=8000`、`DEFAULT_MAX_TOTAL_TOKENS=30000`；三个配额可在 `QueryParam` 覆盖（base.py L122-135）。
- **做法**：
  - 查询期：`_apply_token_truncation` 把实体/关系按检索顺序组装成 `entities_context/relations_context`，按 `max_entity_tokens`/`max_relation_tokens` 截断，同时维护 `filtered_*` 与原始记录映射（L5501-5610）；注释强调"selector 可以重排和丢弃，但**不能发明**"（L5520-5523）——截断是有明确语义约束的。
  - 抽取期：prompt 限制每次输出 `max_total_records` / `max_entity_records` 行（prompt.py L95-97）。
  - 合并期：`summary_context_size` / `summary_max_tokens` / `force_llm_summary_on_merge`（operate.py L412-416）控制是否摘要、何时摘要。
  - 来源数：`max_source_ids_per_entity` + `KEEP`/`FIFO` 策略（operate.py L2524-2532；constants.py L76-79）限制每个实体保留多少 chunk 来源。
- **解决什么问题**：把"检索上下文预算"拆成 entity / relation / total 三层，避免某一类挤占全部；抽取/摘要也都有上限，防止单次 LLM 输出爆炸。
- **代价**：截断有损（实体/关系描述被切、来源被丢）；代码为"被截断的摘要变成持久 description"专门做 tally + write-ahead（operate.py L550-561、lightrag.py L2745-2763）——**说明截断会污染索引，必须额外记账**；配额是启发式默认值，未见调参依据。
- **Memoria 能否落地**：分项配额 + 显式截断记录可搬；默认数值不可直接搬（与 Memoria 的上下文长度/模型相关）。
- **许可**：MIT。

### C4-3｜LlamaIndex AutoMerging：按需回填父块（无需 LLM 摘要的"分层展开"）

- **来源**：`auto_merging_retriever.py`（MIT）L26-47、L56-125、L127-164、L176-194。
- **做法**：检索小节点 → 若某父节点命中的子节点比例 > 0.5（L39/L87-90）→ 用父节点替换这些子节点（L90-124）；同时把结果之间缺失的相邻节点补进来（L127-164）；循环直到稳定（L186-190）。**不做摘要、不做 LLM 调用。**
- **解决什么问题**：用"命中比例"作为"是否展开"的判断，只有确实命中了父块的大部分内容才返回父块，避免无差别返回大块。
- **代价**：需要 docstore 持久化父节点文本；`while is_changed` + 补洞可能让结果集膨胀；**无 token 预算**（与 Aider/LightRAG 相比是缺口）；需要正确的 PARENT/CHILD 关系（HierarchicalNodeParser 建立）。
- **Memoria 能否落地**：可落地，且与 C4-1 的预算机制组合（先 AutoMerging 决定展开哪些，再用预算截断）是自然组合。
- **许可**：MIT。

### C4-4｜本机 XERJ：多粒度文档 + 字段投影裁剪（观测到的"按需加载"）

- **来源**：MCP `xerj_map` / `xerj_search` 实测返回；`ax-docs/schema.json`。
- **做法（工具契约层面）**：
  - 同一内容有 file / code / section 三种粒度 doc（见 C1-6），检索可只取需要的粒度；
  - 响应自带 `_savings` 与 hint：实测一次 `match_all` 返回 3 条 `_source` 共 **11,790 bytes**，提示改用 `_source:["ax_path","title"]` + `fields:["_passage"]` 只返回匹配函数而不是整文件；按 hint 收窄后用 `_source` 只回 8 个字段，响应显著变小（实测 `_savings.bytes=4854`，采样口径）。
- **解决什么问题**：把"返回整文件"改成"返回匹配单元 + 最小字段集"，降低给 agent 的 token。
- **代价**：闭源，无法验证内部预算/缓存；字段裁剪靠调用方传 `_source`，默认仍可能很大。
- **Memoria 能否落地**：只能借鉴"分层粒度 + 投影裁剪"的接口设计。
- **许可**：未取到。

### C4-5｜本机 AOCI：条目级预算（不是检索上下文预算）

- **来源**：`aoci.meta.txt` L6（`S配额: C9-8≤600 C7-4≤200 C3-1≤50`）、`aoci.code.txt` 统计（470 条，平均 61 字节、max 323）。
- **做法**：按 tag 的重要度（C）与规模（E）给不同字符预算；条目保持极短（均值 61 字节），S 只在真正必要时写（17/470）。
- **解决什么问题**：把"索引体积"控制在条目级，让完整索引可以整卷注入模型上下文（AOCI 的 cognition/overview 机制依赖这一点）。
- **代价**：表达力受限（61 字节写不下细节）；需要人工/模型判断"什么值得写"；对检索期预算没有帮助。
- **Memoria 能否落地**：可作为"索引条目长度纪律"参考。
- **许可**：未取到。

### ④ 小结

1. **Aider 是唯一把"硬 token 预算"写进核心路径的实现**：默认 1024、无文件时 ×8、二分 ±15%、只出签名、mtime 缓存。**它证明"预算 + 排序 + 近似填充"是工程上可行的**，但也证明代价是"只能给签名"。
2. **LightRAG 把预算拆成 entity/relation/total 三份**，并且在抽取、摘要、来源数上都设上限；代价是截断有损且需要额外记账。
3. **LlamaIndex 的 AutoMerging 提供"无需 LLM 的分层展开"**：按命中比例展开父块，适合"小单元检索 + 大上下文回填"，但自身没有预算控制。
4. 四家都没有"按查询动态调整索引单元大小"的实现；**单元大小是建索引时定的，运行时只做选择/截断**。

---

## 6. ⑤ 本机两个参照：XERJ 与 AOCI 能读到什么

### 6.1 XERJ（闭源 Rust 二进制）

**能读到（事实）**
1. 运行时路径：`C:/xerj/xerj-1.0.0-rc.96-x86_64-pc-windows-msvc/xerj.exe mcp`、`C:\ProgramData\xerj\xerj.exe --data-dir "C:\Users\Lam Tim\xerj-data"`；索引内 `xerj_meta.json` 报 `1.0.0-rc.97`。
2. 索引目录契约：`schema.json`（字段定义 v23）、`es_mapping.json`、`settings.json`（`analysis.analyzer.default: stemmer`、`index.query.strict_unknown_fields: true`、`xerj_ingest_shards: 1`）、`snapshot.json`（generation/segments/seq_no/tombstones）、`segments/`（列存 `.fst/.meta/.norms/.post` + `.seg/.sidx/.ids/.dv`）、`wal/`、`analysis-binding.json`、`created_at.json`。
3. 索引内容实测：`ax-docs` 51 docs，三种粒度（file/code/section），字段见 C1-6；`xerj_map` 返回字段基数/覆盖率/样例；`xerj_search` 返回 `_id`（32-hex）与 `_source`。
4. autoindex 机制：`autoindex-catalog`（数据集级元数据索引，字段含 `fields_json`/`record_count`/`sample_queries_json`）+ `.xerj/autoindex/*/journal.ndjson`（704 行，350 次 `file_replace_start` + 350 次 `file_done` + run/plan/finish/embedding_identity）；存在 `.autoindex-stage-*` 暂存。
5. 记忆层：`.xerj-memory-<ns>/` 索引 schema = `text`(text) + `stored_at`(long) + `text_vector`(**384 维 cosine**) + `metadata{date, role, task, doc, files, verification}`；另有 `-edges` 目录（图边）。
6. MCP 工具契约：`xerj_map`（字段地图）、`xerj_search`（DSL/字符串）、`xerj_memory_store(dedup)`/`xerj_memory_recall(recency_weight/graph)`、`xerj_brain_*`（bi-temporal 图边）。

**读不到（明确写"未取到"）**
- `_id` / `ax_file` 生成算法；segment 二进制格式；WAL 提交与崩溃恢复语义；segment 合并/压缩策略；任何内部 token 预算实现；源码与许可文本。
- 不能从一次快照验证"同一文件重复索引是否同 `_id`"。

### 6.2 AOCI（无源码，只有数据与 MCP 工具）

**能读到（事实）**
1. 根清单 `aoci.txt`：`cognition-volumes/v1`，两个卷 `meta`（`aoci.meta.txt`）与 `code`（`aoci.code.txt`）。
2. Meta：`FRAS-Discipline: 2`、`S-Admission: non-inferable-and-error-preventing`、S 配额、tag 字典（A 层/B 模块/C 重要度/E 规模）、身份示例 `code:path/to/file.go`。
3. Code 卷：588 行 / 470 条 entry；`filename[tags]: F:… | R:… | A:… | S:…`；平均 61 字节；S 非空 17 条；`R:code:` 引用 32 条。
4. 维护数据：baseline 583 文件（path→sha256/size/normalized_sha256/role）；ledger 228 事件（op 分布见 C2-5）；governance receipts 26 个（pre/post `index_sha256` + `transaction_id`）；transactions/history 下有 3.6KB–48KB 的快照文件；`verify_history` 为空。
5. MCP 工具契约：`aoci_maintain` 机器签发批次（每候选绑定 `source_sha256`/`candidate_id`）；`aoci_update_entry` 必须提交完整批次、禁止字段 Patch；`aoci_remove_entry` 仅用于治理返回的 orphan；`aoci_report` 用于证据不足。

**读不到 / 不可用**
- 源码（`aoci.exe` 为二进制）；许可文本**未取到**（不能假定开源）；`maintain` 的候选生成算法、条目的语义质量评估方式不可见。
- `verify_history` 为空，无法据此证明"验证阶梯被执行过"。
- `.aoci/transactions/history` 内文件只列到大小，未逐条解析。

---

## 7. ⑥ 汇总表：做法 / 解决什么 / 代价 / 在 Memoria 能否落地 / 许可

| # | 做法（repo + 位置） | 解决什么 | 代价 | Memoria 落地性 | 许可 |
|---|---|---|---|---|---|
| 1 | LlamaIndex `BaseNode` 字段拆分：id/metadata/关系/模板/hash（schema.py L275-320, L800-803） | 身份与内容解耦；同一 metadata 可按消费者排除注入 | metadata 无 schema；hash 含 metadata | 高（纯 schema） | MIT |
| 2 | LlamaIndex `SentenceWindow`：小句 + 窗口 metadata 且排除出 embed/LLM（sentence_window.py L16-18, L118-136） | 小单元精准 + 大上下文回填，零 LLM | 存储冗余；回填逻辑另需 retriever | 高 | MIT |
| 3 | LlamaIndex `HierarchicalNodeParser` + `AutoMergingRetriever`：多粒度 + 命中比例 ≥0.5 回填父块（hierarchical.py L95-138；auto_merging L39, L87-90, L186-194） | 分层展开，不用摘要树 | 存全层级文本；无 token 预算；循环可能膨胀 | 中—高（需 docstore 存父块） | MIT |
| 4 | LlamaIndex docstore/index_store 分层 + `ref_doc_id` 级联删除（keyval_docstore L93-125, L557-598；keyval_index_store L38-89；base.py L423-431） | 文档级删除/引用完整 | 分步写、非事务 | 高 | MIT |
| 5 | LlamaIndex `DocstoreStrategy`：hash 判变更，UPsert/删除缺失（ingestion/pipeline.py L242-259, L451-536） | 只重算变化内容 | 依赖稳定 doc id；hash 含 metadata；删除有失败窗口 | 高（但须先定 doc id 规则） | MIT |
| 6 | LangChain `Document.id` 显式身份槽位（documents/base.py L45-53, L288, L306） | 身份与 metadata 分离 | 不强制/不生成/不校验 | 高（只借字段语义） | MIT |
| 7 | LightRAG `TextChunkSchema` 极简 4 字段（base.py L79-84） | chunk 只存原文+定位 | 无语义解释能力 | 高 | MIT |
| 8 | LightRAG 实体/关系 `description` + `source_id` + map-reduce 合并摘要（prompt.py L56-110；operate.py L372-530, L2429-2548, L2782+） | 语义单元可读、可回溯 | LLM 成本；截断/来源上限有损；合并改写 | 中（结构可借，摘要不宜直接搬） | MIT |
| 9 | LightRAG 存储分层 + doc_status 状态机（lightrag.py L1825-1901, L2442-2465；base.py L1317-1372） | 生命周期可观测、可重试、可删 | 一致性修复代码量大 | 中（借状态机，别照搬 8k 行） | MIT |
| 10 | LightRAG 分项 token 配额 6000/8000/30000 + 抽取/摘要上限 + source ids 上限（constants.py L59-61, L76-81；operate.py L5501-5610；prompt.py L95-97） | 上下文可控、防输出爆炸 | 截断有损且需记账 | 高（数值不照搬） | MIT |
| 11 | Aider repo map 硬预算 + PageRank + 二分 ±15% + 只出签名（repomap.py L49-70, L103-167, L365-545, L629-782） | 固定 token 下最大仓库可见性 | 只给签名；依赖代码图 | 中（借预算机制，不搬 PageRank） | Apache-2.0 |
| 12 | XERJ 多粒度 doc（file/code/section）+ 字段投影裁剪 + segment/WAL/journal（磁盘契约 + 工具契约） | 按需加载、增量重跑可审计 | 闭源；机制不可复制 | 低（仅设计参照） | 未取到 |
| 13 | AOCI 路径身份 + baseline sha256 + 机器签发批次 + 整卷 CAS receipts（baseline/ledger/governance + MCP 契约） | 漂移可检测、写入可审计可恢复 | 语义仍需模型/人重写；写放大 | 高（与本仓现状最接近） | 未取到 |

---

## 8. 给 Lead：最值得搬的 5 条 + 明确不搬 + 未取到

### 最值得搬（按"证据强度 × 落地成本"排序）

1. **"稳定 id 与内容哈希分离"作为硬结构**（LlamaIndex `id_` vs `hash`，schema.py L275-277/L800-803；LangChain `Document.id` L45-53）。
   - 理由：三家独立实现同构；代价最低；直接回答 E1 ③"该不该用内容哈希当身份"——**不该**（LightRAG `md5(全文)` 是反例：编辑即换 id，L2442-2445）。
   - 落地前提：Memoria 必须先定义"doc/知识点 id 由谁生成、编辑后是否保持"；否则任何 hash-vs-id 设计都落不了地。
2. **文档级 ref_doc + 级联删除**（LlamaIndex docstore `ref_doc_info{node_ids}` + `delete_ref_doc`，keyval_docstore L93-125/L557-598；vector_store/base L423-431）。
   - 理由：删除/重建必须有文档级单位，否则悬挂向量与孤儿节点无法清理；代码量小、机制清晰（MIT）。
3. **hash 驱动的增量重算策略**（LlamaIndex `DocstoreStrategy`，pipeline L451-536）。
   - 理由：直接给出"只重算变化内容"的可对照实现；但**必须同时解决 doc id 稳定性**（见第 1 条），否则默认 uuid4 会让它失效（这是读代码能直接证明的坑）。
4. **AutoMerging 式"按命中比例回填父块"**（LlamaIndex auto_merging L87-90/L186-194）。
   - 理由：不需要 LLM 摘要就能获得"小单元检索 + 大上下文"；比 RAPTOR 式摘要树便宜且无 4% 幻觉问题（A 源 A2-1 已证摘要成本/幻觉）。建议与 token 预算组合，补上它缺失的预算控制。
5. **硬 token 预算 + 排序 + 近似填充**（Aider repomap L49-70/L629-706）。
   - 理由：唯一把预算写进核心路径的实现；机制可移植（二分/容差/只出签名）。**但排序信号要换**：Aider 的 PageRank 依赖代码定义-引用图，教材/讲义没有这种图，只能借"预算内按重要性截断"的骨架。

### 明确不搬

- **内容哈希当文档/知识点唯一身份**（LightRAG `doc_key=md5(全文)`，L2442-2445）：编辑即新文档、引用全变；若要用，必须同时提供显式 `ids` 通道（LightRAG 自己留了，L2345）。
- **LlamaIndex 默认 `uuid4` node id 直接拿来用**（schema L275-277、node_utils L26）：不补稳定 id 就会重复入库；只能作为"默认值不可用于生产"的反面教材。
- **LLM 摘要树 / description 合并当索引主线**（LightRAG operate L372-530；A 源 RAPTOR/GraphRAG 已给出成本与幻觉代价）：C 源进一步证明摘要会因 token 上限被截断并持久化（lightrag.py L2745-2763 专门记账），不适合作为"可判性"来源。
- **LightRAG 8k 行级的一致性修复/状态机全量移植**：复杂度与其非事务存储强相关，Memoria 若没有同等多后端需求，搬进来是负债。
- **Aider PageRank repo map 直接用于中文教材**：信号不匹配；只借预算骨架。
- **XERJ 内部索引机制**：闭源，不可复制；只作磁盘布局/工具契约参照。
- **AOCI 的具体实现**：无源码且许可未取到，只能作行为参照，**不得复制/移植**。

### 未取到（必须在后续保持"未知"）

1. XERJ `_id` / `ax_file` 生成算法、segment 格式、WAL 提交/崩溃恢复语义、任何内部预算。
2. AOCI 源码、许可文本、`maintain` 候选生成算法；`verify_history` 为空，无法证明验证执行。
3. LightRAG 各存储后端（KV/图/向量）的真实 schema 与 upsert 语义：本报告只读到 Python 侧字段使用点，未读后端实现。
4. LangChain 各 VectorStore 对 `Document.id` 的实际使用（只取证 Document 定义，未读实现）。
5. LlamaIndex 各 reader 是否默认设置稳定 `doc_id`（未读 loader 层）。
6. 所有 OSS 的实测性能/成本数字：**C 源未运行代码**，本报告"代价"均为结构性代价；若需要数字，须 B 源实测或另开 benchmark。
7. "chunk id 在编辑后仍稳定"的开源实现：**未找到**（本报告范围内）。

---

## 9. 检索与核对记录（可复核）

- 抓取日：2026-10-27。抓取方式：`curl.exe` / `Invoke-WebRequest` + `cdn.jsdelivr.net/gh/<repo>@<branch>`、`raw.githubusercontent.com`、GitHub Contents API（`/repos/<repo>/contents/<path>?ref=<branch>`，base64）。
- 快照落盘：`artifacts/agent/verify/debate/kg-retrieval/evidence/_oss_src/`（20 个文件，含 4 份 LICENSE）；配套 HEAD commit 时间见 §1.1。
- 核对规则：
  - 行号必须与落盘文件逐行对齐（`Select-String` / `read` 双查）；跨文件引用给函数名 + 行号双锚。
  - 字段清单只从代码/磁盘 schema 抄录，不从 README/博客推断。
  - 任何"推断"单独标注（如 XERJ `ax_file` 的用途、LlamaIndex 默认 uuid4 导致重复入库的后果），不写成"实现如此"。
  - 未取到的项集中在 §8 末尾，不散落成模糊表述。
- 失败与重试：`raw.githubusercontent.com` 超时/403 → 换 jsdelivr/Contents API；jsdelivr 返回 octet-stream 导致一次落盘乱码 → 丢弃重抓并做首字节校验。**这些失败不改变任何结论，只影响抓取路径。**

*（本文档仅为 C 源取证，不含设计提案；未修改任何产品代码，未 commit。）*
