# 检索与知识库维护：产品决策记录

> 记录 2026-07-06～07 两次讨论结论，作为 M4+ 检索 UX 与「引导维护」板块的单一参考。
> 与 `designV0.md` §3.8、§11 互补；实现以本文 + 代码为准迭代。

---

## 1. 两条主线

| 主线 | 用户目标 | 系统输出 | UI 归属 |
|------|----------|----------|---------|
| **检索** | 找概念、定位阅读 | **kp_id** 列表 + 命中来源 + 分数；可选正文定位 | 工具栏搜索（**用户交互**，非维护） |
| **维护** | 建 KP、补 metadata、绑 link | 侧车 **提议 → 用户确认 → 写入** | 配置窗 / 待确认；未来 **「引导维护」** 独立板块 |

**铁律**：检索结果单元永远是 **KP（kp_id）**；`id` / `name` / `tag` / `description` / 正文是 **命中信号**，不是并列结果类型。

---

## 2. 检索：命中什么

### 2.1 已确认 KP 的索引字段 → v1.5 扩展隐式字段

**显式（sidecar，用户确认）**：

| 字段 | 来源 | Lexical | Embedding | 相对权重 |
|------|------|---------|-----------|----------|
| kp id | sidecar | ✓ | 拼入向量 | 最高 |
| name | sidecar | ✓ | 拼入向量 | 高 |
| tags | sidecar | ✓ | 拼入向量 | 中高 |
| kp description | sidecar | ✓ | 拼入向量 | 中 |
| file description | sidecar 文件级 | ✓ | — | 低 |
| range 正文 | md + 已确认 range | token（低权） | 前 800 字 | 低 / 语义主力 |

**隐式（search_aux，持久化 cache，用户可经 proposals 采纳）**：

| 字段 | Lexical | Embedding | 相对权重 |
|------|---------|-----------|----------|
| auto_tags | ✓ | ✓ | 略低于 user tag |
| aliases | ✓ | ✓ | 接近 name |
| key_phrases / summary_1l | ✓ | ✓ | 类似 description |
| query_hits | ✓ | — | 个性化 |
| bridge（MT 中间语言） | 可选 | ✓ 主用 | 跨语言 |

完整 schema 与权重见 [`search-kernel-v1.5.md`](search-kernel-v1.5.md) §2、§6.2。

**默认不进入 KP 索引**：pending 提议、虚链 anchor 文字、无 KP 的 plain 正文。

### 2.2 用户验证场景（俚语 ↔ 书面语）

- 已确认 KP，range 正文含「吃大便」→ 搜「吃屎」可命中（语义层，视模型与上下文）。
- 未建 KP、仅正文出现该词 → **KP 检索不命中**（符合「可搜性绑定 KP 单元」）。

### 2.3 检索 API 目标形态

```yaml
results:          # 主结果：KP
  - kp_id: ...
    score: ...
    lexical_score: ...
    semantic_score: ...
    sources: [id-exact | name-fuzzy | tag-fuzzy | kp-description | body-fuzzy | semantic]
    snippet: ...   # 待完善

body_locate:      # 可选降级层（见 §3.1）
  - kind: body-locate
    file: ...
    line: ...
    snippet: ...
```

---

## 3. 产品决策（2026-07-07 用户确认）

### 3.1 无 KP 命中时的降级 — **选 B**

- **A（未选）**：仅搜已确认 KP。
- **B（已选）**：KP 无/少结果时，**分级展示** pending / 正文提及等；不算正式 KP 命中。
- **实现（首版）**：设置 → 检索 → **「搜索正文定位内容」**（`body_locate_enabled`）。开启后在 KP 结果下方追加 **正文定位** 行（文件 + 行号 + 片段），点击打开文件；样式与 KP 结果区分。

后续扩展：待确认提议、虚链未绑定分组（仍非 KP 结果）。

### 3.2 「搜索链接」是什么交互场景？

**不是维护场景**，而是 **导航绑定场景**：

| 触发 | 行为 |
|------|------|
| 点击 **虚链**（`targets: []`） | 打开搜索 / 定向面板，预填 anchor 文本，用户选 target KP |
| 配置里为 link **添加 target** | 输入 id 时的 suggest 列表（Lexical / 未来语义） |
| 工具栏 **全局搜索** | 找 KP 去阅读；**不**直接写 sidecar |

链接推荐的产出是 `links[].targets`，与「是否已有 edge」**无必然关系**（见 §4.3）。

### 3.3 Tag：系统 propose + 用户选择 → **扩展为统一建议机制（v1.5）**

- 系统 **propose** → 进入 **候选**；用户 **手动创建** 的 tag 也先进候选或直接已选（产品可配置）。
- UI 划分：**已选** vs **候选** vs **已忽略** 三态。
- **颜色区分**：系统 propose 候选 vs 用户自建候选（不同色）；已选统一样式。
- 算法（现有）：`suggest_tags` — jieba + 库内 tag 词表 + 正文共现；非 LLM。

**v1.5 扩展（2026-07-10）**：同一交互模型覆盖 **alias、summary、key_phrase、description** 等隐式 aux — 非独立 AI 面板，而是：

| 触达位置 | 管理内容 |
|----------|----------|
| KP 配置窗 | tag / description / alias / summary 候选 |
| link 编辑 | link_target 候选 |
| 图谱节点 | edge / merge 候选 |
| 引导维护队列 | 全 kind 待办，按检索增益排序 |

详见 [`search-kernel-v1.5.md`](search-kernel-v1.5.md) §3。

### 3.4 Links、KP、Edges 的关系 — **用户澄清**

| 概念 | 谁产生 | 用户编辑 |
|------|--------|----------|
| **KP** | 用户确认 range / 手动创建 | id、name、tags、description、range |
| **links** | 用户 wrap + 绑 target；系统可 **推荐 targets** | anchor、targets、pool、relevance 等 **link 属性** |
| **edges** | **系统程序解析**（含 links 等信号）；不是用户手动「加边」 | 用户 **最多改 links 属性**；不单独维护 edges 表单 |

**links 是 edges 的信息子集/导航子集**（用户可见、可改的是 links 层；edges 为图谱/程序推导结构）。

链接创建推荐 **不依赖**「先建 edge」或「先合并 KP」；与 KP 合并建议独立。

### 3.5 搜索 vs 维护 — UI 分区

- **工具栏搜索**：纯 **用户交互**（找、跳转、读）。
- **维护**（建 KP、tag、绑 link）：配置窗 + 待确认 + 未来 **「引导维护」** 独立布局（开疆拓土，不挤在搜索里）。
- 搜索可无结果时 **指向** 引导维护（链接/按钮），但不替代维护 UI。

---

## 4. 知识库维护：推荐什么、配置是什么

### 4.1 推荐建立知识点（KP + range）

| 策略 | 输入 | 提议内容 |
|------|------|----------|
| S1 标题 | `##`+ | name + range |
| S2 mention | fm.concepts | 首次出现段落 range |
| S5 定义句 | 「X 是…」 | name + range |
| S3/S4 | — | 未实现 |

确认前 → `pending.yaml`；确认后 → `knowledge_points[]`。

### 4.2 推荐 KP 元数据

| 能力 | 提议写入 |
|------|----------|
| tags | `tags[]` 候选 |
| description | `description` 文本 |
| merge | 合并目标 kp_id（近重复） |

### 4.3 推荐 links（与 edges 解耦）

- **虚链定向**：search → 用户选 `targets[]`。
- **wrap 建议**：正文术语 → 建议 link + target。
- **不**在 link 推荐流程里创建 edge；edges 由程序后续解析。

### 4.4 写入契约

```yaml
kind: kp_range | kp_metadata | link_target
reason: heading | mention | definition | virtual_link | merge | ...
proposed: { ... sidecar 片段 ... }
confidence: 0–1
actions: [confirm, edit, dismiss]
```

禁止 silent 写入。

---

## 5. 相似知识点合并 — 测试夹具

见 `tests/fixtures/m4_merge_kb/` 与 `tests/unit/services/test_kp_merge_scenarios.py`。

| 场景 ID | 说明 | 当前 Lexical merge 预期 |
|---------|------|---------------------------|
| `same-name-cross-file` | 跨文件同名 | 应互相 suggest |
| `name-typo-pair` | 名称高相似（编辑距离） | 应 suggest |
| `name-variant-suffix` | 「策略梯度」vs「策略梯度法」 | 视包含/分词 |
| `tag-bridge-only` | 仅 tag 相同、name 不同 | **当前不应** merge（未来 semantic） |
| `en-zh-pair` | Attention vs 注意力机制 | **当前不应**；embedding 后续 |
| `id-prefix-only` | id 前缀相关、name 不同 | 通常不应 |
| `unrelated-control` | 无关 KP | 不应出现在 suggest 中 |

---

## 5.1 模糊匹配分层（非手工别名表）

| 场景 | 智能方案 | 不用 |
|------|----------|------|
| 同音错字（嘛而科夫→马尔可夫） | Lexical **拼音**（`pypinyin` 算法） | 手工同义词表 |
| 符号 / 跨语言（epsilon↔ε、Attention↔注意力） | **Embedding 语义** + 索引/查询前 **LaTeX 归一化**（`\varepsilon`→token） | 希腊字母硬编码映射 |
| 俚语↔书面语（吃屎↔吃大便） | Embedding（需开启语义搜索） | — |

**结论**：字面层只做分词 + 拼音；跨写法/跨语言交给本地向量模型，不维护 epsilon 等别名表。

---

| 项 | 状态 |
|----|------|
| Lexical 多字段 KP 搜索 | ✅ |
| Embedding 语义（可选） | ✅ |
| 增量 embedding 索引 | ✅ |
| `body_locate_enabled` 设置 + 正文定位 | ✅ 首版 |
| 检索结果 snippet / 分档置信度 | ⏳ |
| Tag 候选/已选分色 UI | ⏳ 设计已定 |
| 引导维护独立板块 | ⏳ 设计已定 |
| 虚链 ↔ 搜索绑定 UI | ⏳ |
| merge 语义增强 | ⏳ |

---

## 8. 当前检索全流程（SearchKernel v1 · 2026-07-10）

与 `dicussion.md` §17.1 一致；实现见 `search_kernel.py`、`lexical_index.py`、`embedding_provider.py`、`body_locate.py`。

### 8.1 索引构建（KB 打开 / 侧车变更）

1. 扫描库内 `.md` + 侧车，**仅已确认 KP** 进入索引。
2. 每条 KP → 扁平记录：`kp_id`、`name`、`tags[]`、`kp_description`、文件级 `description`、`body_excerpt`（range 摘录）。
3. 分字段分词（jieba + 标识符切分 + **拼音紧凑串**）→ 倒排表 `token → [(record_idx, field)]`。
4. 缓存：`.memoria/cache/lexical/index.json`。
5. （可选）Embedding：name+tags+description+正文 → 本地句向量 → `.memoria/cache/embedding/`。

### 8.2 一次工具栏搜索

```
用户输入 q + 范围(全库|当前文件)
  → 查询分词 + lower + 查询拼音
  → 倒排召回候选 KP（无命中则全表打分）
  → 字段加权：id 精确 > name > tag > description > body
  → Top-N 排序
  → [semantic/both] 向量相似度合并 (~0.65 Lexical + 0.35 Semantic)
  → [body_locate_enabled] 线性扫描 md 行（正文定位，非 KP 结果）
  → 返回 kp_id[] + sources + 可选 snippet/定位
```

### 8.3 当前局限（用户反馈：不够智能）

| 缺失能力 | 说明 |
|----------|------|
| 图谱遍历 | `edges[]` 不参与召回与打分 |
| 查询扩张 | 无同义/纠错/语义 query 树（R09 部分补齐 Lexical 层） |
| 多跳路径分 | 无「从 query 到 KP 经过哪些边/tag」的证据链 |
| 双向汇合 | 无「查询侧 + KB 侧同时生长再相遇」机制 |

---

## 9. 目标：双向生长汇合检索（SearchKernel v2 · R17）

用户设想（2026-07-10）：知识库与搜索栏各有一棵 **生长树**，向中间汇合；汇合节点（高度匹配的 KP、tag、中间概念）按 **路径证据** 计分。

```
[查询侧 front]                         [KB 侧 front]
      q                                    全库 KP 子图
      │                                         │
 拼音纠正、同义、tag 别名              沿 edges(reference/extend)、
 LLM/规则 query 扩张                   tag 共现、description 相似…
      │                                         │
      ▼                                         ▼
 查询概念树                               分析/激活树
      │                                         │
      └────────────► 汇合层 ◄───────────────────┘
              路径加权 → 排序 kp_id
```

| 阶段 | 内容 |
|------|------|
| **R09（过渡）** | Lexical 拼音/ typo、query 推荐、分档置信度 |
| **v2 首版** | tag 共现 + edge 1-hop 激活；简单路径分 |
| **v2 完整** | 双向 BFS 深度扩展 + 汇合层打分 |
| **R16** | 点击/有用无用反馈 → 调路径权重或库内小模型 |
| **R07 绑定** | 边属性专章定稿后，边类型参与生长规则与推理提议 |

详细对照表见 `dicussion.md` §17.2。

---

## 10. 用户决策补充（2026-07-10）

| 主题 | 决策 |
|------|------|
| R07 图谱推理 | 边属性系统需专章；建议边 **不自动写**，用户逐条确认 |
| R16 检索反馈 | 库内持久化方案 **可行** `[✅]` |
| R15 编辑 | 富文本 **Markdown**（含公式、荧光笔、undo/redo），非隐藏 md 的 WYSIWYG |
| R03 HTML | **全局最低优先级**；直接渲染 vs 转 md **待定** |
| 检索智能 | 认同 v2 **双向生长** 方向；v1 为静态倒排基线 |
| **SearchKernel v1.5** | 隐式 aux **全系统建议机制**（同 tag 候选）；**多模型分工** + MT 桥接；见 search-kernel-v1.5.md |

---

## 11. SearchKernel v1.5 摘要（2026-07-10）

> 完整规格：[`search-kernel-v1.5.md`](search-kernel-v1.5.md)

| 主题 | 决策 |
|------|------|
| 隐式内容可见性 | **嵌入全系统 proposals**；KP 配置 / link / 图谱 / 引导维护；用户 **采纳·拒绝·编辑**（同 tag） |
| 隐式持久化 | `.memoria/cache/search_aux/kp/{id}.json`；可重建；采纳 → sidecar + `promoted` |
| 多模型 | ModelRouter：**Embed-Recall / Embed-Rerank / MT-Bridge / LLM-aux / LTR** 分阶段；单模型不够 |
| 跨语言 | 高精度 **MT → 中间语言（默认 en）** + 多语 embed 并联 |
| 检索 | 显式+隐式 **四通道 RRF** → 精排 Top-20 → 反馈权重 → 置信分档 |
| 速度 | 查询 &lt;100ms（5k KP，无 rerank）；LLM/全库 MT **不进热路径** |
| 闭环 | aux 同时供 **search + suggest_tags/merge/link/query**；R16 显式+隐式反馈 |
| Q1–Q4 | 混合 proposals 存储；桥接语言 en 默认可改；bge-reranker-v2-m3；query_hits 须确认才晋升 alias |

---

## 7. 相关文件

| 区域 | 路径 |
|------|------|
| Lexical | `src/memoria/services/lexical_index.py` |
| Embedding | `src/memoria/services/embedding_provider.py` |
| 统一 search | `src/memoria/services/search_kernel.py` |
| 正文定位 | `src/memoria/services/body_locate.py` |
| 合并建议 | `search_kernel.suggest_kp_merge` |
| **v1.5 规格** | `docs/design/search-kernel-v1.5.md` |
| Benchmark | `scripts/benchmark/` |
