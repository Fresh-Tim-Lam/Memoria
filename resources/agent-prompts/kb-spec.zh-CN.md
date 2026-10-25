<!-- spec-version: 1.1.0 -->
<!-- spec-deps: src/memoria/graph/edge_types.py@6229550973e9, src/memoria/graph/kb_build.py@993495fcf892, src/memoria/services/link_md.py@82b6d65f44fd, src/memoria/storage/sidecar_validate.py@1649dcff8f71, src/memoria/services/kp_resolver.py@298e86263376, src/memoria/services/agent/file_ops.py@1f812209d12d, src/memoria/ui/static/app/js/surface/render-core.js@79484c296b72, src/memoria/services/kb_agent.py@0d816956b4d0, resources/agent-prompts/fsrs.py@07271eac4613, docs/reference/preview-formats.md@0b066f6b4310 -->
<!-- reviewed-on: 2026-10-25 -->
# 知识库编撰与维护规范（KB Spec）

> 用途：**知识库内容的事实标准**——KP 与元数据、sidecar 结构、链接与边、文档与目录、图片路径、撰写与整理规则、复习调度、收尾自检。
> 读者：在该知识库内工作的 Trae 智能体（由 `kb-agent.zh-CN.md` 指令要求**必读**）。
> 特性：**自包含**（知识库工作区读不到 Memoria 仓库，故本文件内联全部所需规则）；由 Memoria 产品随版本分发到 `.memoria/agent/kb-spec.zh-CN.md`，**更新本文件即可兼容新规则，无需重建 Trae 智能体**。
> 上游权威（Memoria 仓库，仅供维护者对照）：`docs/conventions/import-format.md`、`docs/conventions/markdown-form-std.md`、`src/memoria/storage/sidecar_validate.py`。
> **同目录的「支持格式说明」**：`.memoria/agent/preview-formats.md`。它回答"某种写法**渲染成什么**"（渲染写法**以它为准**，写不确定的格式前**按需读**）；本文件回答"**该怎么写/怎么改才合规**"。渲染行为变更时两者须同步。
> **写入边界（2026-10-25 补）**：本规范面向**直接读写文件**的智能体；这类写入**不经过** Memoria 应用的写安全闸（入口唯一/读后写/写前备份/审批四道闸只保护应用内 Agent 与 MCP 写入）。批量或高风险改动前，请自行备份受影响文件。

---

## 1. 事实源与元数据权威

| 来源 | 内容 | 地位 |
|---|---|---|
| `*.md` 正文 | 知识内容 | 事实源 |
| `.memoria/sidecars/**/<同名>.memoria.yaml` | KP 元数据（`knowledge_points[]`）与语义边 | **权威** |
| `.memoria/agent/review/cards.json` / `progress.json` | 复习卡与进度 | 事实源 |
| `.memoria/manifest.yaml` | 文件指纹快照 | **产品「构建」生成，禁止手写** |

- **KP 只认 sidecar**：解析逻辑只读 `sidecar.knowledge_points[]`；md 的 frontmatter 是导入期遗留，**不参与** KP 解析（可保留不动，但不要依赖它）。
- 因此：**维护 KP = 改 sidecar**；只改 md 不改 sidecar，产品里看不到 KP。
- 学习/复习状态只放 `.memoria/agent/review/**`，**不得**写进 sidecar（避免污染知识语义）。

## 2. KP 规范

| 字段 | 规则 |
|---|---|
| `id` | 英文 slug（小写 + 连字符），**全库唯一**（如 `bayes-rule`） |
| `name` | 中文名称，**必须与正文对应标题一致**（缺失只会告警，但请补齐） |
| `range.start.snippet` | 起始行文本，通常是标题行（如 `## 贝叶斯公式`） |
| `range.end.snippet` | 该 KP 最后一行文本；**不能是空行**，需能在正文中**精确匹配**（缺失即校验错误） |
| `tags` | 字符串列表，领域/类型/关键词，便于检索 |
| `aliases` | 字符串列表，别名（如「强哥」→「光头强」） |
| `description` | 该 KP 的一句话说明 |

划分原则：一个 KP 聚焦**单一概念**；覆盖**完整语义段**；`##` 常对应一个 KP，`###` 为子 KP；内容过短（<3 行）可与相邻合并。

## 3. sidecar 结构

路径镜像 md：`subdir/topic-c.md` → `.memoria/sidecars/subdir/topic-c.memoria.yaml`

```yaml
schema_version: 1
file: subdir/topic-c.md
knowledge_points:
  - id: bayes-rule
    name: 贝叶斯公式
    tags: [概率, 公式]
    aliases: [贝叶斯]
    description: 条件概率的换算公式
    range:
      start: { snippet: "## 贝叶斯公式", line_hint: 12 }
      end:   { snippet: "（该 KP 最后一行原文）", line_hint: 24 }
links: []      # 由「构建」从正文 [[id]] 同步维护；不要手写（见 §4）
edges:         # 语义边：边类型的唯一权威来源；需要标类型时写这里
  - source_id: bayes-rule
    targets: [conditional-probability]
    type: extend          # reference | extend（contain 由标题层级自动推导，禁手标）
    relevance: 0.8        # 可选，0～1
```

- `line_hint` 只是提示，**定位以 snippet 为准**。
- 一个文件一个 sidecar；一个 KP id 全库唯一。
- `edges[]` 的 `source_id` 必须是**本文件里的 KP id**；`targets` 必须是**库内已存在的 KP id**（不存在的目标不要写进 edges，用正文 `[[id]]` 表达虚链）。
- `links[]` 是构建产物（含 `anchor_text` / `targets` / `instances`）；**手写容易与正文行号错位并被检查报错，请不要手写**。
- 写入 sidecar 后必须自检（§7），并提示用户在 Memoria 执行「构建」「检查」。

## 4. 链接与边

| 写法 | 含义 |
|---|---|
| `[[kp-id]]` | 引用目标 KP（默认 `reference` 边） |
| `[[kp-id\|显示文本]]` | 引用但显示别的文本（同上） |

- 正文 `[[…]]` **只写目标 id（可带显示文本），不写边类型**；边类型只存 sidecar（`edges[]`，见 §3）。
- 边类型：`reference`（引用/相关）、`extend`（扩展/下游）、`contain`（父子，**由标题层级自动生成，禁止手标**）。
- 同一行可并列多个 `[[a]]`、`[[b]]`：构建会各自成为独立链接条目与边（**不会**合并成一个"多目标条目"）。
- **遗留写法** `[[kp-id#extend]]`：**不要用**。构建会把该片段读成 `links[].edge_type`（只有 extend / reference 生效），随后把 `#extend` 从正文**剥离并回写文件**；预览期它还会把 `#extend` 当成目标名而显示为断链；若该链接不在任何 KP `range` 内，这条边会直接丢失。要标 extend 请写 sidecar `edges[]`。
- **悬空链接**（指向尚不存在的 id）：保留为"虚链"，**不要**创建空文件。

## 5. 文档与目录

- 文件名英文 kebab-case；正文标题中文；目录名英文、语义化。
- 按主题规划目录树，避免根目录散落；大库可建 1 个 hub 文件（`README.md`/`overview.md`）串起主要 KP。
- 一个 id 只映射一个文件。
- 正文使用 Memoria 支持的 Markdown（标题/列表/表格/代码块/公式/图片/链接）；**拿不准的写法一律保留原样**，不要自行改写（渲染写法见 `.memoria/agent/preview-formats.md`）。

## 6. 图片

- 库内图片统一放 `.memoria/images/`。
- 引用一律写**相对知识库根、无前缀**：`![alt](.memoria/images/文件名.png)`；**禁止 `..` 上跳**（会被判路径逃逸 → 404）。
- `./` 前缀是旧语义（相对当前文件所在目录），**不推荐**：文件一移动引用就断；统一用无前缀写法。
- 路径含空格/中文用尖括号：`![alt](<.memoria/images/屏幕截图 2026.png>)`。
- 显示属性写 title 位：`![alt](url "width=300,align=center")`；**白名单只有** `width` / `height` / `align` / `name-size` / `name`（未知 key 会被忽略并告警）。

## 7. 撰写 / 整理 / 维护规则

### 7.1 撰写（新增用户想写入的知识）
1. **来源可溯**：内容须对应用户提供的要点/资料或库内既有 KP；你自行补充的一般性内容，必须在正文标注：
   `<!-- ⚠ 来源待核实：<说明> -->`
2. **先查重**：按 sidecar 索引查是否已有同概念 → 有则**扩写/合并**，不重复新建。
3. **必挂链**：新 KP 至少一条 `[[已有-kp-id]]`，并在相关已有 KP 处补反向链接；需要区分关系类型（extend）时在**目标文件的 sidecar `edges[]`** 里声明（§3）。
4. **先清单后落笔**：按批次给出完整写入清单（路径 + 文件名 + KP id/name + 拟链接），确认后一次性写入。

### 7.2 整理（原始材料 → KP）
**保留原文、不改语义**：只做排版、KP 划分、链接与标签标注；不删减/改写/总结/扩写；不添加材料里没有的知识。
发现问题用注释标注（不改原文）：`<!-- ⚠ 待核实：… -->`、`<!-- ❓ 存疑：… -->`、`<!-- 🔄 歧义：… -->`。

### 7.3 维护（KP 与链接）
- 新增/更新 KP：按 §2 改 sidecar。
- 补链接：按 §4 写正文 `[[id]]`；**边类型写 sidecar `edges[]`**；`contain` 交给系统。
- 拆分/合并：合并时 concepts 累加、链接指向保留；拆分时各自成 KP 并补互链。
- 改 KP id / 重命名文件（全库级联）、删除文件/KP、跨目录移动、批量重组 → **先问用户**。

### 7.4 收尾自检（缺一不可）
1. 每个 KP 的 `name` 能在正文找到对应标题；
2. 每个 sidecar 的 `range` snippet 能在正文**精确匹配**，`end` 非空行；
3. 所有 `[[id]]` 的目标在 sidecar 中存在（或**有意**为虚链）；**正文里没有 `#类型` 片段**（有则删掉、把类型写进 sidecar）；
4. 新增/修改的边写在 sidecar `edges[]`，且 `source_id`/`targets` 指向真实存在的 KP；
5. 提示用户在 Memoria 执行「构建」「检查」，无错误后交付。

## 8. 常见坑

- 只改 md 不改 sidecar → 产品里看不到 KP（§1）。
- 手写 `manifest.yaml` → 与产品指纹不一致（应交给「构建」）。
- `range.end.snippet` 填了空行/不唯一文本 → 定位失败。
- 图片路径带 `../` → 渲染 404（`./` 虽兼容但移动文件会断链，别用）。
- 把学习进度写进 sidecar → 污染知识语义。
- 把 `contain` 边手标进正文或 sidecar → 与系统自动生成重复。
- 把 `[[id#extend]]` 当推荐写法 → 构建会重写你的正文（剥离该片段）；类型应写 sidecar `edges[]`。
- 手写 sidecar `links[]` → `instances` 行号易与正文错位，构建/检查会报错。

## 9. 复习调度（FSRS，`fsrs.py`）

命令（在知识库根目录执行；`--kb` 缺省当前目录，`--date` 缺省系统当天，输出一行 JSON）：

```bash
python .memoria/agent/fsrs.py due   [--date YYYY-MM-DD]
python .memoria/agent/fsrs.py init  --card <card_id> [--date YYYY-MM-DD]
python .memoria/agent/fsrs.py grade --card <card_id> --grade 1..4 [--date YYYY-MM-DD]
python .memoria/agent/fsrs.py --selftest
```

- `review/cards.json`：卡片定义，`card_id` 全库唯一；一 KP 可多卡（`kp_id`、`kp_id#2`…）。`type` 约定 `basic` / `cloze` / `reverse`（调度本身不校验 type）。
- `review/progress.json`：只由脚本读写；不要手改（`log` 只追加）。
- **先落卡再调度**：`grade` 会拒绝 `cards.json` 中不存在的 `card_id`（不会静默建幻影卡）⇒ 新卡先写进 `cards.json`，再 `init` / `grade`。
- **fail-closed**：`cards.json` 缺失或结构非法（如某条目缺 `card_id`）⇒ `due` / `grade` **直接报错退出**（非 0），不要把它当成"今天没有到期卡"。
- 幂等：同一 `(card, date, grade)` 重复执行以 `log` 已有记录为准，不叠加。
- **降级**：若 `fsrs.py` 不存在，只把评分追加到 `log`、**不更新** `due`，并提示用户到 Memoria 执行「为知识库创建 Trae 智能体」。
