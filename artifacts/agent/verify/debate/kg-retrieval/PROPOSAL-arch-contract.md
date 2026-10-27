# KG/索引驱动 agent 检索 · Phase 1 提案（A 方：契约 / 数据结构 / 迁移）

> **作者**：arch-contract（A 方）。**Phase 1 独立性**：未读任何他人提案，未与他人讨论。
> **证据身份**：`ev:file:<path>#L<n>` / `ev:bench:<id>` / `ev:url:<URL>`。
> 无证据的判断显式标 **【经验判断】**。
> **写域**：仅本目录；未改 `src/**`、`docs/**`、`docs/example/**`；未 commit。

---

## 1. 结论摘要（先给答案）

1. **架构基线的前提「锚点 = KP id + source range」当前不成立**。
   真库实测：**37.0%（132/357）的 KP snippet 在文档内不唯一**；
   文档前插 50 行后，**18.8%（67/357）的 KP 被静默钉到错误行且 `ok=True`**
   （歧义 KP 中 50.8% 钉错）—— 用户看到的 ≠ agent 读到的，且**无任何告警**。
   ⇒ **若不先修锚点，双视图"共享锚点"是建立在一个 37% 有歧义的键上。**

2. **R4 解法：以「块级内容哈希锚」替代「行号 + 文本 snippet」**，
   并把 `line_hint` 降级为**性能提示**（不参与身份判定）。这是最小侵入的可行路径。

3. **R3 解法：stale 判据不能用文件级 sha256** ——
   实测：文档末尾加一行 ⇒ **357/357 KP 全被判 stale，实际受影响 0**（过度失效 ∞ 倍）。
   必须**块级 hash**；`manifest.yaml` 已有的 `md_sha256` 可复用为**粗筛第一层**。

4. **R1：索引单元 = 块（block），KP 是块的视图**，不是并列概念。
   现有 KP 直接映射为"由若干连续块构成的组"，避免再造一套单元。

5. **R6：检索栈已有 4 种模式（lexical/semantic/both/full + RRF），
   但 `search_kb` 硬编码 `modes="lexical"` ⇒ agent 只用 1/4 能力。**
   （`ev:file:src/memoria/services/search_kernel.py#L58-L94`、
   `ev:file:src/memoria/services/agent/tools/kb.py#L248`）
   ⇒ **最便宜的改进可能是改一行 `modes`，而不是新造索引层。** 不许重复造已有能力。

---

## 2. 逐 R 回答

### R1 索引单元粒度：**块（block）**，KP 是块的视图

**证据**：
- `ev:file:src/memoria/domain/range.py#L1-L10` —— 现有 `Range = {snippet: str, line_hint?: int}`，
  **没有块概念**，也没有 id。
- `ev:file:docs/design/kg-ontology-v0.md` —— KG 本体已裁 `contain` 是**派生专用**类型
  （我 task-154 落地：`DERIVE_ONLY_EDGE_TYPES`），即"文档结构层级"是派生的，不是手标。
- 实测（`ev:bench:r4-anchor-probe`）：`AAA_Vocab` 是 **134 文件 / 134 KP = 每文件 1 KP**；
  真库是 **9-12 文件 / 357 KP**。⇒ **现状两种库的 KP 密度差 40 倍**，
  任何"KP = 单元"的假设在不同库上行为完全不同。

**我的主张**：
```
索引单元 = 块（block）    ← 全文按 Markdown 结构切块（heading/段落/表格/代码块）
KP       = 一组连续块的 id 列表（视图，不是第二套单元）
```
**为什么不是"段落"或"chunk"**：
- 段落边界在 Markdown 里不稳定（列表项/引用块可跨行）——这正是 task-155/156 引用块内列表
  改了四处的原因（lexer/parser/mapper/render-core 联动）；
- "chunk" 是**检索概念**（固定 token 窗口），与**编辑单元**（用户改的是段落/小节）不是一回事。
  用 chunk 当锚点 ⇒ 用户编辑后 chunk 边界全变 ⇒ 锚点全失效。

**关键约束（契约）**：块必须来自**解析器**（`memoria/parser`），不能由检索侧自行切分，
否则"两套切分"必然漂移（这正是今晚"两个后端图路径 404 vs 454"的同类错误）。

---

### R2 description 的可判性 —— **转交 B 方，我只给契约约束**

**【经验判断 + 契约视角】**：`sufficient statistic` 的写法属知识组织判断（B 方专长）。
A 方只提一条**硬约束**：

> **description 必须能对应到块的【可计算特征】否则无法验证它是否过期。**
> 例如"何时该读"若写成自然语言，则源文变化后**无法机械判断该句是否还成立**。

⇒ 契约上要求：description 至少带 `derived_from: {block_ids, block_hashes}`，
使**"描述是否仍适用"可降级为"块是否变化"**（见 R3）。

---

### R3 证据绑定与失效 ★（A 方重点之一）

#### 3.1 绑定什么

```yaml
kp:
  id: kp-xxx
  anchor:
    block_ids: [b-7f3a, b-7f3b]        # R4 的块级锚
    block_hashes: [sha256:..., ...]     # 内容哈希（见 3.3 的口径）
  index:                                # 视图 B
    description: "..."
    derived_from_hash: sha256(block_hashes 的确定性拼接)
```

#### 3.2 为什么**不能**用文件级 sha256 判 stale（实测）

`manifest.yaml` 已有 `md_sha256`（`ev:file:docs/example/AAA_Vocab/.memoria/manifest.yaml#L5`）。

**实测代价**（`ev:bench:r3-stale-precision`，真库 357 KP / 9 文档）：

| 库 | 文档 | KP | 文件级判 stale | 实际受影响 | 过度失效 |
|---|---|---|---|---|---|
| AAA_Vocab | 134 | 134 | **134** | 0 | ∞ |
| **真库-数字通信原理** | 9 | **357** | **357** | **0** | **∞** |

⇒ 文档**末尾加一行**（不在任何 KP range 内）⇒ **357 个 KP 全部被判 stale，实际受影响 0**。

**后果不只是浪费**：若 agent 收到"全部 stale"就会**整库重读** ⇒ 直接推高 baseline
（真库单章 407KB ≈ 十万 token，见 `ev:bench:ACCOUNT-2026-10-27`）。**stale 判据太粗 = token 灾难**。

#### 3.3 块级 hash 的口径（**必须写死，否则跨平台不一致**）

我在 task-181 刚踩过同类坑（发布清单规范化字节）：
```python
block_hash = sha256(
    ("\n".join(line.rstrip() for line in block_lines) + "\n").encode("utf-8")
).hexdigest()
```
**三条硬规则**（每条都有真实前例）：
- **LF 归一化**（`\r\n → \n`）：Windows 工作区是 CRLF（`ev:file:docs/guides/agent-team-org.md` B3-b 记录了 autocrlf 导致的收据假红）；
- **行尾空白剥离**：编辑器自动去尾空格不应让块"变化"；
- **不剥离 BOM**：BOM 是内容的一部分（同 B3-d）。

#### 3.4 stale 期间 agent 该怎么做

**我的主张（分级，不搞一刀切）**：

| 情形 | 行为 |
|---|---|
| `block_hash` 相同 | 直接用 index（**不读原文**） |
| `block_hash` 变了但块仍在 | 标 `stale`，**降级到读原文该块**（不是拒绝） |
| 块**已被删除** | 标 `orphan`，**拒绝使用该 KP**，并在 `search_kb` 结果里显式告警 |
| 只有文件级 hash 变了、块级未变 | **不算 stale**（这正是 3.2 要避免的过度失效） |

#### 3.5 检测成本（要回答"低成本"）

| 层 | 成本 | 作用 |
|---|---|---|
| 文件级 `md_sha256`（已有） | O(文件数) stat + 读 | **第一层粗筛**：文件没变 ⇒ 该文件所有块必然没变（**零误报**） |
| 块级 hash | O(变更文件的字节数) | **第二层精判**：只对粗筛命中的文件算 |

⇒ **增量成本 = 只有真正被编辑过的文件**，正常编辑 1 篇时是 O(1 篇)。
**【经验判断】**：对 357 KP 的库，块级 hash 一次全量约几十 ms 量级；需实测确认（列 U-2）。

---

### R4 锚点稳定性 ★★（A 方核心）

#### 4.1 现有机制的真实实现（不是转述，我读了源码）

`ev:file:src/memoria/range/locator.py#L43-L49`：
```python
if line_hint is not None and 1 <= line_hint <= len(lines):
    h = line_hint - 1
    if needle in _norm(lines[h]) and (not forward_only or h >= start):
        scan(max(start, h - HINT_WINDOW), ...)
        return h, candidates or [h]      # ← 直接采信 hint，不校验唯一性
```
`ev:file:src/memoria/range/locator.py#L35` —— `if needle in _norm(lines[i])` 是**子串包含**，
不是行相等；`_truncate` 截到 `SNIPPET_MAX_LEN = 80`（`ev:file:src/memoria/range/constants.py#L1`）。

⇒ **机制本质**：`hint` 命中就信 hint；hint 不命中则在 ±`HINT_WINDOW(=40)` 行内找，
再退化为全文找；多个候选时**取离 hint 最近的那个**（`#L62`）。

#### 4.2 失效场景清单（含是否已实测）

| # | 场景 | 后果 | 状态 |
|---|---|---|---|
| **F1** | **snippet 在文档内重复**（标题/常见行重复出现） | hint 漂移后钉到**错误同名行**，`ok=True` 静默 | ✅ **实测 37.0% 歧义 / 18.8% 静默钉错** |
| **F2** | 行号漂移（前插/删除行） | hint 失效，退化到全文搜索，歧义时选错 | ✅ 实测（同上，前插 50 行） |
| **F3** | snippet **极短**（≤8 字符，实测 11.5% = 41/357） | 子串匹配命中大量行 | ✅ 实测计数 |
| **F4** | `end.snippet` 为空 ⟹ range 无法闭合 | 整条 KP 无法定位 | ✅ 代码强制：`ev:file:src/memoria/storage/sidecar_validate.py#L263-L270` 校验 `missing_snippet` |
| **F5** | snippet 被**编辑**（用户改了那一行） | `snippet_not_found`；`document.py` 有一套"重新锚定"补救 | ✅ 代码存在：`ev:file:src/memoria/services/document.py#L373-L473` |
| **F6** | 同文本出现在**多个文件** | 文件级已解决（per-file 索引），不构成歧义 | ✅ 排除 |
| **F7** | 两个 KP **range 重叠**且 snippet 相同 | 两 KP 钉到同一行 | ⚠️ 未单测（列 U-3） |

#### 4.3 F1 的实证样本（真库）

`ev:bench:r4-wrongpin`（真库 `ch02-2_信号与系统的时域分析.md`）：

```
snippet='## 2. 单位冲激信号'  文档内出现 8 次
  三个不同 KP（img-ch2-2-19-2 / -22-2 / -24-2）
  漂移后应指向 L458 / L522 / L569，实际分别钉到 L422 / L458 / L522
  ⇒ 全部错位，且全部 ok=True
```

⇒ **这不是理论风险**：同一文档里 8 个同名小节，现有机制**无法区分**它们。

#### 4.4 可行替代方案对比

| 方案 | 唯一性 | 编辑鲁棒 | 迁移代价 | 我的判断 |
|---|---|---|---|---|
| **A. 块级内容哈希锚**（推荐） | ✅ 块 hash 天然唯一 | ✅ 编辑只影响被改块 | **中**：需给块分配稳定 id + 回填 | ✅ **采纳** |
| B. 只加"出现序号"（snippet#3） | ✅ 可消歧 | ❌ 前面插入一个同名块 ⇒ 序号全偏 | 低 | ❌ 见 §3 否决 |
| C. 纯行号锚 | ❌ 行号必漂 | ❌ | 低 | ❌ 现状已证明不够 |
| D. 只要 snippet 不加 hint | ⚠️ 依赖文本唯一 | ✅ | 低 | ❌ 实测 37% 不唯一 |
| E. 人工 UUID per KP | ✅ | ✅ 但**不解决块漂移** | 低 | ⚠️ **必要但不充分**：KP id 稳定 ≠ range 稳定 |

**⇒ 主张：A + E 组合**。KP id 保持现状（已有），**新增块 id 作为 range 的锚**。

#### 4.5 迁移代价（实测口径）

| 步骤 | 工程量 | 风险 |
|---|---|---|
| 给解析器加块切分 + 块 id | 中（parser 已有 AST，见 task-155 改造） | 与 task-156（引用块二期）冲突 ⇒ **需排队** |
| 回填现有 sidecar（357 + 134 KP） | **可脚本化**：按现有 `line_hint` 定位 → 算出块 hash → 写入 | 中：现有 5 条 resolve 失败的 KP 需人工 |
| 保留 `line_hint` 作为**性能提示** | 零 | — |
| 兼容期双写 | 低 | — |

**关键**：因为**块可由现有 `line_hint` 反推**（`resolve_range` 已给出 start/end line），
所以回填是**一次性脚本 + 人工复核 5~10 条**，不是重标全库。这是 A 方案代价可接受的原因。

---

### R5 检索路径与预算 —— **转交 C 方，我只给契约边界**

A 方唯一主张（契约）：
> **索引条目必须支持"按需分级加载"**：`kb_overview` 只返回 `{kp_id, name, block_ids, stale}`（无 description），
> description 在**选中候选后**再取。否则索引本身变成负担（几千 token）**且无法降级**。

**【经验判断】**：这是"索引也要分页"的通用要求；具体预算数字归 C 方实测。

---

### R6 与现有检索栈融合（**不许重复造**）

#### 6.1 现状核查（代码事实，**U-1 已查清**）

**`search_kernel` 实际已有 4 种模式**（`ev:file:src/memoria/services/search_kernel.py#L58-L94`）：

| 模式 | 实现 | 是否含 RRF |
|---|---|---|
| `lexical` | `search_lexical`（jieba 倒排） | — |
| `semantic` | `embedding_provider.search_semantic` | — |
| `both` / `full` | lexical + semantic，`retrieval_fusion.fuse_search_result` 融合 | ✅ `use_rrf = mode in ("both","full")`（`#L61`） |

⇒ **embedding 与 RRF 融合都已经存在**（我之前担心的"重复造"前提不成立）。

**但 `search_kb` 把它锁死在 1 种**（`ev:file:src/memoria/services/agent/tools/kb.py#L248`）：
```python
payload = search(text, kb_path=kb_path, scope="kb", modes="lexical", limit=top_k)
```
⇒ **agent 只用了检索栈 1/4 的能力**，`semantic` 与 `RRF` 从未进入 agent 路径。

**而且命中后的位置信息继承了 R4 缺陷**：
`ev:file:src/memoria/services/agent/tools/kb.py#L272-L275` —— 行号来自
`_kp_map_for_file(...)["line"]` = `_line_hint(kp)`，正是 R4 §4.1 里那个会漂的 hint。

#### 6.2 我的主张（修正后）

```
lexical / semantic / RRF（都已有）        ← 【召回层，保留，不要重造】
        ↓
agent 索引（新增，薄薄一层）               ← 只做两件事：
   ① 用 KP 的 keywords/description 做 query 扩展（把同义术语映射进召回）
   ② 用块级 stale/orphan 信息【过滤】不可用 KP
        ↓
返回结果带【块级锚点】（R4）                ← 修掉 _line_hint 继承缺陷
```

**关键判断**：
- **不该新造 embedding 或 RRF** —— 已有（`search_kernel#L61-L94`）；
- 该做的是 **把 `search_kb` 的 `modes` 从硬编码 `lexical` 改成可选/自适应** ——
  这是**一行配置级**的改动，收益可能远大于新造索引层。**这是我这一方最"便宜"的建议**；
- **不另开一条独立召回路径**：另开一条 = 两套召回结果不一致，
  与今晚 404 vs 454 双后端图路径是同类缺陷。

**⚠️ 需要 C 方裁决的问题**（我不越界）：`semantic` 默认关闭是**成本考量**（embedding 调用）
还是**质量考量**？→ 决定第 2 条建议是否可行。

---

### R7 外部参考（契约部分）

| 参考 | 解决什么 | 契约层可搬的 | 不能搬的（**具体冲突**） |
|---|---|---|---|
| **AOCI**（本仓已接 `.mcp.json`） | 仓库级**认知索引**：每对象一条 Entry，带 F/R/A/S | **"一条对象一条 Entry + 稳定对象身份"** 的形态与本提案 §4 A 方案同构 | AOCI 的 Entry 身份是**文件路径**（`code:<path>`），Memoria 需要**块级**身份；且 AOCI 是"模型生成语义"，Memoria index 的 description 也要人可读 ⇒ 需双写口径 |
| **XERJ** | 检索引擎（BM25 + 可选向量 + rerank 代理） | **"检索层与数据层分离"** | XERJ 是**外挂服务**；Memoria 是**便携单机包**（`Package/` 自包含）⇒ 引外部服务破坏"离线可用"（与 `docs/design/kg-ontology-v0.md` 的便携定位冲突） |
| **GraphRAG** | 用图做"全局摘要"回答跨文档问题 | **实体→社区→摘要**的三级结构 | 需要**大量 LLM 调用建图**（成本）；Memoria 的图是 **hybrid reference 边、无实体解析**（KG 本体已裁类型无信息量）⇒ 建不出可靠实体图 |
| **HippoRAG** | 用"个性化 PageRank"做多跳检索 | **用图结构扩散召回**的想法 | 依赖**可靠的知识图谱边**；Memoria 边是 reference（无断言），**扩散会传播噪声** |
| **RAPTOR** | 递归**摘要树**（叶→簇→摘要） | "多粒度索引"思想 | 需要为每个簇**生成摘要**（LLM 成本 + 与源文偏离风险）；且簇是**语义聚类**，与"块结构"不是同一棵树 |
| **LlamaIndex** | index-retriever 抽象层 | **分层索引 + metadata filter** 的工程形态 | 引入大依赖，与"纯 stdlib/便携"取向冲突（我为 task-181 手写 Ed25519 就是因依赖不可保证） |

**总结**：**形态可参考（对象+Entry+稳定 id），实现不照搬（外部服务/LLM 建图/重依赖）**。

---

### R8 如何证明"真正对 agent 有提升" —— **转交 D 方，我给一条契约级要求**

**我从契约角度坚持的一条**：
> **A/B 必须同时报告"锚点正确率"** —— 否则无法区分"检索变好了"与"检索用错了行但答案碰巧对"。

实测显示现状锚点错误率 **18.8%（静默）**，
若 A/B 只测"答对率/token"，**这个错误会被平均掉**，看起来"提升 20%"而实际上
部分提升来自**读错了块却给对了答案**（教材章节标题重复、内容相似时会这样）。

⇒ 契约要求：`stale/orphan/anchor_mismatch` 三类计数**必须进 metrics**，
且**锚点正确率不得低于改动前**。

---

## 3. 我【否决】的方案（含我自己曾考虑的）

### 否决 1：只给 snippet 加"文档内出现序号"（`snippet#3`）

**我一度认为这是最便宜的修法**（不改结构，只在 range 里加一个 `occurrence_index`）。
**否决理由（推演 + 实测支撑）**：
- 序号是**位置序**，不是**身份**：在它前面插入一个同名块 ⇒ 该块序号 +1，
  所有后续同名块**全体偏移**；
- 实测真库存在"同名小节出现 8 次"（§4.3），一次编辑就会让同文档 3~8 个 KP 集体错位；
- 与现状 `line_hint` 是**同一类缺陷**（都是"位置"而非"内容"），等于把行号问题换成"序号问题"。

### 否决 2：全库重算 `llm` 生成 description 作为"最新事实"（不做 hash）

**否决理由**：源文变化后**无法判断**已生成的 description 是否还成立 ⇒
只能"定期全量重生成" ⇒ LLM 成本与 baseline token 都不可控，且**无法回答 agent 的"这条还准吗"**。

### 否决 3：让 `search_kb` 直接返回 KP 全文

**否决理由**：baseline 已实测单章 407KB ≈ 十万 token（`ev:bench:ACCOUNT-2026-10-27`）；
返回全文会让"检索"退化为"读文档"，**与本次要解决的问题相反**。

---

## 4. 我不确定的点（M3 登记，不装懂）

| # | 不确定 | 影响 | 怎么才能确定 |
|---|---|---|---|
| **U-1** | ✅ **已查清**（原列为未知，现已读代码确认）：`search_kernel` 已有 `lexical/semantic/both/full` 四模式 + RRF（`ev:file:src/memoria/services/search_kernel.py#L58-L94`），**但 `search_kb` 硬编码 `modes="lexical"`** ⇒ agent 只用 1/4 | 已转化为 §6.2 的具体建议 | — |
| **U-2** | 块级 hash 对 357 KP 全量计算的实际耗时 | 决定 stale 检测能否放在"每次 search"上 | 实测（本 Phase 未做，时间用于锚点） |
| **U-3** | KP range 重叠（F7）在真库有多少 | 决定是否需要"块 id 唯一归属"约束 | 待测 |
| **U-4** | 块切分是否会与 task-156（引用块内列表）冲突 | 影响迁移排期 | 需读 task-155/156 结论 |
| **U-5** | `document.py#L373-L473` 的"保存后重新锚定"与我的块锚是否重复劳动 | 若已解决大半，迁移可更轻 | 需读该段全部逻辑 |

---

## 5. Falsifiers（什么会推翻我）

| # | 我的主张 | 推翻条件 |
|---|---|---|
| **F-A** | 锚点当前不稳定（37% 歧义 / 18.8% 静默错） | 若能证明真库实际使用中 agent **从不读 KP range**（只读整篇），则该缺陷不影响 agent ⇒ 降级为"用户体验问题"而非"检索问题" |
| **F-B** | 块级内容哈希优于位置锚 | 若实测"编辑后块 hash 变化率"接近 100%（即任何编辑都让所有块变），则块锚退化为文件锚 ⇔ 我的方案无增益 |
| **F-C** | 文件级 sha256 不能作 per-KP stale | 若能证明"agent 收到全库 stale 时的实际代价可忽略"（例如它本来就整库重读），则该主张的**重要性**下降（方案本身仍成立） |
| **F-D** | 不应引外部服务（XERJ 等） | 若能证明"便携离线"不再是硬约束（人明确允许联网依赖），则外部检索方案值得重新评估 |
| **F-E** | agent 索引应接在 lexical 之上 | 若 C 方证明 lexical 召回率已饱和（top-k 内必含正确 KP），则索引层的价值只在**过滤 stale**，不需要做扩展 |

---

## 6. 交付物清单

| 文件 | 内容 |
|---|---|
| `PROPOSAL-arch-contract.md` | 本提案 |
| `r4_anchor_probe.py` / `r4-anchor-probe.json` | 锚点歧义/漂移实测 |
| `r4_wrongpin_probe.py` / `r4-wrongpin-probe.json` | **静默钉错**实测（核心证据） |
| `r3_stale_precision_probe.py` / `r3-stale-precision.json` | 文件级 hash 过度失效实测 |

**复现**：
```powershell
python artifacts/agent/verify/debate/kg-retrieval/r4_anchor_probe.py
python artifacts/agent/verify/debate/kg-retrieval/r4_wrongpin_probe.py
python artifacts/agent/verify/debate/kg-retrieval/r3_stale_precision_probe.py
```
