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

### 2.1 已确认 KP 的索引字段

| 字段 | 来源 | Lexical | Embedding | 相对权重 |
|------|------|---------|-----------|----------|
| kp id | sidecar | ✓ | 拼入向量 | 最高 |
| name | sidecar | ✓ | 拼入向量 | 高 |
| tags | sidecar | ✓ | 拼入向量 | 中高 |
| kp description | sidecar | ✓ | 拼入向量 | 中 |
| file description | sidecar 文件级 | ✓ | — | 低 |
| range 正文 | md + 已确认 range | token（低权） | 前 800 字 | 低 / 语义主力 |

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

### 3.3 Tag：系统 propose + 用户选择

- 系统 **propose** → 进入 **候选**；用户 **手动创建** 的 tag 也先进候选或直接已选（产品可配置）。
- UI 划分：**已选** vs **候选** 两区。
- **颜色区分**：系统 propose 候选 vs 用户自建候选（不同色）；已选统一样式。
- 算法（现有）：`suggest_tags` — jieba + 库内 tag 词表 + 正文共现；非 LLM。

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

## 7. 相关文件

| 区域 | 路径 |
|------|------|
| Lexical | `src/memoria/services/lexical_index.py` |
| Embedding | `src/memoria/services/embedding_provider.py` |
| 统一 search | `src/memoria/services/search_kernel.py` |
| 正文定位 | `src/memoria/services/body_locate.py` |
| 合并建议 | `search_kernel.suggest_kp_merge` |
| 检索设置 UI | `src/memoria/ui/static/m0/js/search-settings.js` |
| 合并夹具 | `tests/fixtures/m4_merge_kb/` |
