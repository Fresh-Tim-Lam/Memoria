# SearchKernel v1.5：显式/隐式描述、统一建议机制与多模型检索

> **状态**：`[⏳]` 设计规格（2026-07-10）  
> **前置**：M4 Lexical v1（`search_kernel.py`）、[`search-and-maintenance-decisions.md`](search-and-maintenance-decisions.md)  
> **关联**：R09（Lexical 强化）、R16（反馈）、R17（双向生长 v2）、[`search-retrieval-benchmark.md`](search-retrieval-benchmark.md)  
> **解决痛点**：① 用户 KP 刻画不完善 → Recall 低；② 无关 KP 进 Top-k → 精度/噪声差

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **显式优先** | 用户 sidecar 字段（id/name/tags/description）权重始终 **高于** 引擎隐式字段 |
| **隐式可管** | 隐式内容 **不是黑盒 cache**；走与 **候选 tag 同一套** 建议机制，全系统可见、可采纳/可拒绝/可编辑 |
| **提议不静默写** | 任何智能产出先进 **提议层**；用户确认才进 sidecar；隐式持久化在 `.memoria/cache/search_aux/` |
| **多模型分工** | 检索各阶段使用 **专用本地模型**；禁止「一个 Embedding 包打天下」 |
| **重索引、轻查询** | LLM/翻译/精排重活离线或 Top-K；单次搜索目标 **&lt;100ms**（~5k KP） |
| **闭环** | 同一隐式描述同时服务 **检索 + 各类 recommend/suggest**；反馈回写权重与 aux 优先级 |

---

## 2. 双层描述模型

### 2.1 显式层（Explicit · 用户真相）

来源：`.memoria/sidecars/*.memoria.yaml` 中 **用户确认** 字段。

| 字段 | 层级 | 检索角色 |
|------|------|----------|
| `id` | KP | 精确锚点、跳转 |
| `name` | KP | 主展示 + Lexical 高权 |
| `tags[]` | KP | 过滤、共现、推荐 |
| `description` | KP / 文件 | 语义摘要、悬停 |
| `range` 正文 | KP | 低权 token / 语义主体 |

### 2.2 隐式层（Implicit · 引擎 aux · 持久化）

来源：索引/维护管线 **离线生成**，持久化于：

```
.memoria/cache/search_aux/
  manifest.json                 # schema_version, model_set_id, built_at
  kp/{kp_id}.json               # 单 KP aux（见 §4）
```

| aux 字段 | 含义 | 生成器（见 §6） |
|----------|------|-----------------|
| `auto_tags[]` | 系统推断主题词 | 规则 + 召回编码器近邻 + 可选 LLM |
| `aliases[]` | 别名/缩写/历史点击 query | 规则 + 反馈 |
| `key_phrases[]` | 关键短语 | 规则 / 关键词抽取 |
| `summary_1l` | 一句摘要 | 规则首句 / LLM |
| `query_hits[]` | 曾成功检索的 query 片段 | **隐式反馈** 聚合 |
| `bridge_en` | 英文桥接文本（跨语言） | **翻译模型**（§6.4） |
| `embed_text` | 拼接后的向量输入 | 显式+已采纳隐式 |
| `promoted` | 已晋升 sidecar 的 aux 项 | 用户采纳后标记 |

**与 sidecar 关系**：隐式 **不替代** sidecar；用户采纳某 `auto_tag` → 写入 `tags[]` 或 `tag_candidates` 已选 → aux 标记 `promoted`。

---

## 3. 统一建议机制（Proposal System）

> **2026-07-10 拍板**：隐式内容的可见性 **嵌入全系统配置与维护 UI**，不是独立「AI 面板」独占。

### 3.1 与现有 tag 候选模型对齐

sidecar 已有模式（实现中）：

```yaml
tags: [RL, 数学]                    # 用户已选
tag_candidates:
  - tag: 强化学习
    source: system                  # system | user | implicit
    status: candidate               # candidate | selected | dismissed
```

**v1.5 扩展为通用提议注册表**（逻辑模型；物理存储见 §3.3）：

```yaml
proposals:
  - id: prop-uuid
    kind: tag | description | alias | key_phrase | summary | link_target | edge | merge
    target: { kp_id, file?, field? }
    value: "强化学习"
    source: system                  # system | user | feedback | model:tagger
    status: candidate | selected | dismissed | expired
    reason: lexical_cooccur | embedding_neighbor | llm | query_hit
    confidence: 0.72
    created_at: ISO8601
    aux_ref: search_aux/kp/xxx.json#auto_tags[0]   # 可追溯
```

### 3.2 全系统触达点（非单面板）

| 场景 | UI 位置 | 提议 kinds |
|------|---------|------------|
| KP 配置窗 | 与 **tag 候选/已选** 同区 | tag, description, alias, summary |
| 文件级配置 | 文件 description 区 | summary, key_phrase |
| 虚链 / link 编辑 | target 搜索 + 候选列表 | link_target |
| 图谱节点详情 | 边/合并区 | edge, merge |
| 工具栏搜索 | 结果行「有用/无用」+ query 推荐 | （反馈，非 proposal） |
| 引导维护队列 | 待办列表 | 全部 kind；按「检索增益」排序 |
| 设置 → 检索 | 清除 aux / 清除反馈 / 重建索引 | — |

**交互铁律**（与 tag 一致）：

- **候选** / **已选** / **已忽略** 三态；系统 propose vs 用户自建 **分色**
- 采纳 → 写 sidecar + 标记 aux `promoted` + 重建索引条目
- 拒绝 → `dismissed`；同 reason 短期内不重复 propose
- 用户 **可手动编辑** 候选值后再采纳（与 tag 相同）

### 3.3 物理存储（拍板 Q1）

**混合存储** — 按提议范围分流，而非二选一：

| 提议范围 | 存储位置 | 理由 |
|----------|----------|------|
| **KP 级** metadata：`tag`、`description`、`alias`、`summary`、`key_phrase` | **sidecar 内联**（延续 `tag_candidates` 模式） | KP 配置窗已加载 sidecar；用户决策可进 git；与「像管 tag 一样管」一致 |
| **跨 KP / 文件 / 链接 / 边 / 合并** | **`.memoria/proposals/`** | 不污染每个 sidecar；引导维护队列统一索引 |

**sidecar KP 块（目标形态）**：

```yaml
knowledge_points:
  - id: mdp
    name: 马尔可夫决策过程
    tags: [RL]
    tag_candidates:
      - { tag: 强化学习, source: system, status: candidate }
    description_candidates:
      - { text: "…", source: system, status: candidate }
    alias_candidates:
      - { alias: MDP, source: system, status: candidate }
    # description 采纳后写入 description 字段；候选 status → selected | dismissed
```

**`.memoria/proposals/`**：

```
.memoria/proposals/
  index.json              # 全局待办索引（kind, target, status, updated_at）
  link/{proposal_id}.yaml
  edge/{proposal_id}.yaml
  merge/{proposal_id}.yaml
```

- `search_aux/` 仍只存 **引擎生成的隐式 cache**（可重建）；**用户 dismiss/采纳状态** 不在 aux 里，在 sidecar 候选或 `proposals/`。
- 迁移：现有 `tag_candidates` **不改动语义**；新增字段与之平行。

---

### 3.4 存储总览

| 存储 | 内容 | git |
|------|------|-----|
| `sidecar` | 显式字段 + KP 级 `*_candidates` | 是 |
| `.memoria/pending.yaml` | 未确认 KP range | 可选 |
| `.memoria/proposals/` | link / edge / merge 等跨 KP 提议 | 可 gitignore |
| `.memoria/cache/search_aux/` | 隐式 aux（可重建） | gitignore |
| `.memoria/search_feedback/` | 反馈 + weights | gitignore |

`search_aux/`（引擎 cache）与 sidecar/`proposals/`（用户决策）**严格分离**。

---

## 4. search_aux 单 KP Schema

```json
{
  "schema_version": 1,
  "kp_id": "mdp",
  "source_fingerprint": "sha256(sidecar+body)",
  "model_set_id": "memoria-v1.5-default",
  "auto_tags": ["RL", "decision-process"],
  "aliases": ["马尔可夫决策", "MDP"],
  "key_phrases": ["状态空间", "策略", "奖励函数"],
  "summary_1l": "在随机环境中基于策略与奖励的形式化决策框架。",
  "query_hits": ["mdp 公式", "马尔可夫 决策"],
  "bridge": {
    "lang": "en",
    "text": "Markov decision process formalizes sequential decision making…"
  },
  "embed_text": "…拼接块…",
  "generated_by": [
    { "field": "auto_tags", "pipeline": "rule+embed_neighbor" },
    { "field": "summary_1l", "pipeline": "llm:summary-small" },
    { "field": "bridge.en", "pipeline": "mt:bridge-translator" }
  ],
  "promoted": {
    "auto_tags": ["RL"],
    "aliases": []
  }
}
```

**重建规则**：`source_fingerprint` 变化 → 仅重算受影响字段；`promoted` 项不重复 propose。

---

## 5. 多模型架构（Model Registry）

> **2026-07-10 拍板**：**一个模型不够**；各阶段 **专用模型**；跨语言可用 **高精度翻译模型** 桥接中间语言（默认英语）。

### 5.1 ModelRouter

```
.memoria/cache/models/manifest.json     # 用户设置 + 已下载模型路径
src/memoria/services/model_router.py   # 统一调度（lazy load）
```

```yaml
# 设置 → 检索 → 模型集
model_set:
  lexical: rule+jieba+pypinyin          # 无神经网络
  embed_recall: paraphrase-multilingual-MiniLM-L12-v2
  embed_rerank: bge-reranker-base        # cross-encoder，可选
  mt_bridge: opus-mt-zh-en + opus-mt-en-zh   # 或 NLLB-200-distilled-600M
  llm_tag: qwen2.5-0.5b-instruct         # 可选，异步
  llm_summary: qwen2.5-0.5b-instruct
  ltr_feedback: linear-v1                # 非 NN，weights.json
```

每项可 **独立开关**；未安装时降级到规则/Lexical-only。

### 5.2 阶段 ↔ 模型映射

| 阶段 | 任务 | 模型角色 | 运行时机 | 降级 |
|------|------|----------|----------|------|
| **P0** | 分词/拼音/倒排 | 规则 + jieba | 索引+查询 | — |
| **P1** | 召回向量 | **Embed-Recall**（双塔 bi-encoder） | 索引+查询 | 仅 Lexical |
| **P2** | 跨语言桥接 | **MT-Bridge**（zh↔en 高精度翻译） | 索引（写 bridge）+ 查询（q→en） | 仅多语 embed |
| **P3** | Top-K 精排 | **Embed-Rerank**（cross-encoder） | 查询 Top-20 | RRF 顺序 |

**Embed-Rerank 默认型号（拍板 Q3）**：

| 档位 | 模型 | 约体积 | 适用 |
|------|------|--------|------|
| **默认** | `BAAI/bge-reranker-v2-m3` | ~400MB | 中英混合库；精排主选 |
| **轻量** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | ~90MB | 英文为主 / 磁盘紧 |

**包体积上限**：

- 单个 optional 模型包 **≤500MB**（下载器提示）。
- 检索模型集（Recall + Rerank + MT-Bridge）建议总量 **≤1.5GB**；**组件化下载**（可只开 Recall 不开 Rerank/MT）。
- 与现有 Embed-Recall（`paraphrase-multilingual-MiniLM-L12-v2`）**并存**，由 ModelRouter 分角色加载。

| **P4** | aux 摘要/标签 | **LLM-Summary / LLM-Tag**（小参） | 离线/async | 规则首句 |
| **P5** | 反馈排序 | **LTR-Linear**（weights.json） | 查询 | 无反馈权重 |
| **P6** | v2 图扩张 query | **LLM-QueryExpand**（可选） | 查询弱命中时 | 拼音+alias |

### 5.3 跨语言桥接策略（拍板 Q2）

**默认桥接语言：English（`en`）**；用户可在 **设置 → 检索 → 桥接语言** 覆盖。

| 设置值 | 行为 |
|--------|------|
| **`en`（默认）** | 非英文 KP/query 片段 → MT-Bridge → `bridge.en`；与原文 embed **并联** |
| **`zh`** | 以中文为桥（适合全中文库 + 英文 query 场景） |
| **`off`** | 不跑 MT；仅 Embed-Recall 多语模型 + Lexical 拼音 |

- 桥接语言 **按 KB 持久化**在 UI 设置 / `.memoria/cache/models/manifest.json`；不写入用户 md。
- 单 KP 可在配置窗 **关闭 bridge**（`bridge_enabled: false`），override 全局。
- 热路径：查询侧仅对 **当前 query** 做 MT（≤1 次短句）；索引侧 **离线批量** 写 aux。

**问题**：默认 en 是否改为仅用户设置？  
**结论**：**默认 en + 可改**；中文用户可设 `zh` 或 `off`，不必在首次安装强制选择。

### 5.4 模型生命周期

| 事件 | 行为 |
|------|------|
| 首次启用 semantic | 下载 Embed-Recall；后台 warmup |
| 开启跨语言桥接 | 下载 MT-Bridge；KP 增量写 bridge |
| 开启精排 | 下载 Embed-Rerank；仅查询加载 |
| 侧车变更 | 不重跑 LLM，除非 fingerprint 变且队列到 |
| 用户清除 aux | 删 search_aux；保留 proposals 状态 |

---

## 6. 检索管线（SearchKernel v1.5）

### 6.1 总览

```
Query
  │
  ▼
QueryPlan（分词、拼音、alias 扩展、可选 MT→en）
  │
  ├─► Ch-A  Lexical 显式（id/name/tag/desc/body）
  ├─► Ch-B  Lexical 隐式（auto_tag/alias/phrase/summary/query_hit）
  ├─► Ch-C  Semantic Embed-Recall（embed_text，含 bridge）
  └─► Ch-D  Graph 1-hop（可选，metadata 稀疏时加权）
  │
  ▼
RRF 融合 → Top-50
  │
  ▼
Embed-Rerank（Top-20，可选）
  │
  ▼
LTR 反馈权重（weights.json）
  │
  ▼
置信分档（高/中/低）→ Top-N kp_id + sources + evidence
```

### 6.2 字段权重（Lexical）

在 v1 `WEIGHTS` 基础上扩展（隐式 **始终低于** 同级显式）：

| 字段 | 相对显式 tag | 说明 |
|------|--------------|------|
| `tag`（用户） | 1.0 | 基准 |
| `auto_tag`（aux） | 0.85 | 候选未采纳也可检索 |
| `alias` | 0.90 | 接近 name |
| `summary_1l` | 0.75 | 类似 kp_description |
| `key_phrase` | 0.70 | |
| `query_hit` | 0.80 | 个性化 |
| `body` | 0.40 | 降噪声 |

**稀疏 KP 自适应**：无 user tag + 无 description 时，Ch-B/Ch-C 权重 ×1.2；有完整显式时 Ch-A ×1.15。

### 6.3 速度与预算

| 步骤 | 5k KP 预算 |
|------|------------|
| QueryPlan + Ch-A/B 倒排 | &lt;30ms |
| Ch-C 向量 cosine（flat） | &lt;40ms |
| RRF | &lt;5ms |
| Embed-Rerank ×20 pairs | &lt;80ms（可选） |
| **合计** | **&lt;100ms**（无 rerank）；**&lt;180ms**（开 rerank） |

LLM / 全库 MT **禁止**出现在热路径。

---

## 7. 反馈机制（R16）

### 7.1 显式反馈

| action | 触发 | 效应 |
|--------|------|------|
| `useful` | 结果行按钮 | ↑ kp×query 权重；写入 query_hits 候选 |
| `useless` | 结果行按钮 | ↓ 权重；负样本 |
| `promote_proposal` | 采纳 aux/tag/desc | 显式化 + promoted |
| `dismiss_proposal` | 拒绝候选 | 不再 propose 同 value |
| `clear_learning` | 设置 | 删 weights.json |

### 7.2 隐式反馈

| action | 推断 | 效应 |
|--------|------|------|
| `click_result` | rank=k | 点击学习；k 越小权重越大 |
| `query_rewrite` | Δt&lt;30s 新 query | 前次 Top-k 负样本 |
| `search_abandon` | 无点击关搜索 | 弱负样本 |
| `manual_navigate` | 搜索后手开文件 | 排序失败信号 |

**query_hits → alias（拍板 Q4）** `[✅]`：

- 隐式反馈写入 aux 的 `query_hits[]` 后，**不自动**进入检索 alias 字段。
- 系统生成 **`alias_candidates`**（`source: feedback`，进 sidecar 候选区）；**用户确认后**才：
  1. 写入 sidecar 显式 alias / tags（若适用）；
  2. 标记 aux `promoted`；
  3. 参与 Lexical 隐式通道时与显式 alias 同权档。
- **理由**：避免误点击 query 污染 KP 名称空间；与 tag 候选铁律一致。

存储：`.memoria/search_feedback/events.jsonl` + 聚合 `weights.json`。

**显式步长 &gt; 隐式**；均 **本地、可删、可重建**。

---

## 8. 闭环：检索 ↔ aux ↔ 建议 ↔ 用户

```
        ┌─────────────── 用户采纳/拒绝 ───────────────┐
        ▼                                              │
  sidecar 显式 ◄────────────────────────── proposals UI │
        │                                              │
        ▼                                              │
  search_aux 隐式 ◄── 离线生成器（多模型）              │
        │                                              │
        ├────────► lexical / embedding 索引             │
        │                                              │
        ▼                                              │
  SearchKernel ──► 结果 + 反馈 ─────────────────────────┘
        │
        └────────► suggest_tags / merge / link / query_rec
                   （与检索共用 aux 与 embed）
```

**引导维护排序**：检索失败次数 × aux 缺失度 → 优先展示「补 tag / 采纳 alias / 写 description」提议。

---

## 9. API 形态（目标）

```yaml
# 检索（扩展）
search(query, modes=lexical|semantic|both|full, limit):
  results: [{ kp_id, score, tier, sources[], evidence[] }]
  query_plan: { expanded[], bridge_lang? }

# 提议（扩展）
list_proposals(kp_id?, kind?, status=candidate):
  proposals: [...]

adopt_proposal(proposal_id):   # → sidecar + promoted + reindex
dismiss_proposal(proposal_id):

# aux（只读 + 触发重建）
get_search_aux(kp_id):
rebuild_search_aux(kp_id | kb):

# 反馈
record_feedback(event):
clear_search_feedback():
```

---

## 10. 与 Benchmark 对齐

| Profile | 验证重点 |
|---------|----------|
| gold | 精度上限、Noise@5 基线 |
| minimal | aux + 隐式通道 Recall 增益 |
| skeleton | 提议机制 + bridge + 反馈能否逼近 gold |

脚本：`scripts/benchmark/run_search_benchmark.py`；CI：`tests/fixtures/benchmark_retrieval_tiny/`。

---

## 11. 实施阶段

| 阶段 | 交付 | 依赖 |
|------|------|------|
| **1.5a** | search_aux 持久化 + 规则生成 + Ch-B 倒排 | lexical_index | `[🔄]` 已实现：`search_aux.py`、lexical v4、sidecar 候选校验 |
| **1.5b** | proposals 模型 + KP 配置 UI 扩展（alias/summary 候选） | tag_candidates 模式 | `[✅]` 已实现：`proposals.py`、`update_kp` 扩展、标签 Tab UI |
| **1.5c** | RRF + 置信分档 + ModelRouter 骨架 | embedding_provider | `[✅]` 已实现：`retrieval_fusion.py`、`model_router.py`、`search()` RRF |
| **1.5d** | MT-Bridge + embed 双路查询 | 可选模型包 | `[🔄]` 元数据 `desc_vector` 双路语义已实现；MT-Bridge 待做 |
| **1.5e** | Embed-Rerank + search_feedback | semantic 可选依赖 |
| **1.5f** | 引导维护队列 + 全系统 propose 触达 | M3 配置窗 |
| **2.0** | R17 双向汇合 + Graph 1-hop | R07 边属性 |

---

## 12. 开放问题（2026-07-10 拍板）

| # | 问题 | 决策 | 状态 |
|---|------|------|------|
| **Q1** | proposals 存 sidecar 内联 vs `.memoria/proposals/` | **混合**：KP 级 metadata → **sidecar 内联**（`tag_candidates` 扩展 + `alias_candidates` / `description_candidates`）；link/edge/merge → **`.memoria/proposals/`** | `[✅]` |
| **Q2** | MT-Bridge 默认 en vs 用户设置 | **默认 `en`**；设置 → 检索 → **桥接语言** 可选 `en` \| `zh` \| `off`；单 KP 可 `bridge_enabled: false` | `[✅]` |
| **Q3** | cross-encoder 默认型号与体积上限 | 默认 **`BAAI/bge-reranker-v2-m3`**；轻量 **`ms-marco-MiniLM-L-6-v2`**；单包 **≤500MB**，全套 optional **≤1.5GB**，分组件下载 | `[✅]` |
| **Q4** | query_hits 晋升 alias 是否需确认 | **必须用户确认** → `alias_candidates`（source: feedback）；不自动写 alias / sidecar | `[✅]` |

---

## 13. 相关文件（规划）

| 区域 | 路径 |
|------|------|
| 检索入口 | `src/memoria/services/search_kernel.py` |
| Lexical | `src/memoria/services/lexical_index.py` |
| Embedding | `src/memoria/services/embedding_provider.py` |
| 模型路由 | `src/memoria/services/model_router.py` |
| RRF 融合 | `src/memoria/services/retrieval_fusion.py` |
| aux 生成 | `src/memoria/services/search_aux.py` |
| 提议 | `src/memoria/services/proposals.py` |
| 反馈 | `src/memoria/services/search_feedback.py`（待建） |
| Benchmark | `scripts/benchmark/` |
