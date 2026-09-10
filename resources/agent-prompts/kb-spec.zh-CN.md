# 知识库编撰与维护规范（KB Spec）

> 用途：**知识库内容的事实标准**——KP 与元数据、sidecar 结构、链接与边、文档与目录、图片路径、撰写与整理规则、收尾自检。
> 读者：在该知识库内工作的 Trae 智能体（由 `kb-agent.zh-CN.md` 指令要求**必读**）。
> 特性：**自包含**（知识库工作区读不到 Memoria 仓库，故本文件内联全部所需规则）；由 Memoria 产品随版本分发到 `.memoria/agent/kb-spec.zh-CN.md`，**更新本文件即可兼容新规则，无需重建 Trae 智能体**。
> 上游权威（Memoria 仓库，仅供维护者对照）：`docs/conventions/import-format.md`、`docs/conventions/markdown-form-std.md`、`src/memoria/storage/sidecar_validate.py`。
> **同目录的「支持格式说明」**：`.memoria/agent/preview-formats.md`。它回答"某种写法**渲染成什么**"（渲染写法**以它为准**，写不确定的格式前**按需读**）；本文件回答"**该怎么写/怎么改才合规**"。渲染行为变更时两者须同步。

---

## 1. 事实源与元数据权威

| 来源 | 内容 | 地位 |
|---|---|---|
| `*.md` 正文 | 知识内容 | 事实源 |
| `.memoria/sidecars/**/<同名>.memoria.yaml` | KP 元数据（`knowledge_points[]`） | **权威** |
| `.memoria/agent/review/cards.json` / `progress.json` | 复习卡与进度 | 事实源 |
| `.memoria/manifest.yaml` | 文件指纹快照 | **产品「构建」生成，禁止手写** |

- **KP 只认 sidecar**：解析逻辑只读 `sidecar.knowledge_points[]`；md 的 frontmatter 是导入期遗留，**不参与** KP 解析（可保留不动，但不要依赖它）。
- 因此：**维护 KP = 改 sidecar**；只改 md 不改 sidecar，产品里看不到 KP。
- 学习/复习状态只放 `.memoria/agent/review/**`，**不得**写进 sidecar（避免污染知识语义）。

## 2. KP 规范

| 字段 | 规则 |
|---|---|
| `id` | 英文 slug（小写 + 连字符），**全库唯一**（如 `bayes-rule`） |
| `name` | 中文名称，**必须与正文对应标题一致** |
| `range.start.snippet` | 起始行文本，通常是标题行（如 `## 贝叶斯公式`） |
| `range.end.snippet` | 该 KP 最后一行文本；**不能是空行**，需能在正文中**精确匹配** |
| `tags` | 领域/类型/关键词，便于检索 |
| `aliases` | 别名（如「强哥」→「光头强」） |
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
links: []      # 可由产品「构建」从正文 [[id]] 同步
edges: []      # 非 wikilink 派生的语义边
```

- `line_hint` 只是提示，**定位以 snippet 为准**。
- 一个文件一个 sidecar；一个 KP id 全库唯一。
- 写入 sidecar 后必须自检（§7），并提示用户在 Memoria 执行「构建」「检查」。

## 4. 链接与边

| 写法 | 含义 |
|---|---|
| `[[kp-id]]` | 引用目标 KP |
| `[[kp-id\|显示文本]]` | 引用但显示别的文本 |
| `[[kp-id#extend]]` | 声明 `extend` 边（A 是 B 的下游/特例） |

- 边类型：`reference`（引用/相关）、`extend`（扩展/下游）、`contain`（父子，**由标题层级自动生成，禁止手标**）。
- 同一处并列多个 `[[a]]`、`[[b]]` → 构建时合并为多目标。
- **悬空链接**（指向尚不存在的 id）：保留为"虚链"，**不要**创建空文件。

## 5. 文档与目录

- 文件名英文 kebab-case；正文标题中文；目录名英文、语义化。
- 按主题规划目录树，避免根目录散落；大库可建 1 个 hub 文件（`README.md`/`overview.md`）串起主要 KP。
- 一个 id 只映射一个文件。
- 正文使用 Memoria 支持的 Markdown（标题/列表/表格/代码块/公式/图片/链接）；**拿不准的写法一律保留原样**，不要自行改写。

## 6. 图片

- 库内图片统一放 `.memoria/images/`。
- 引用一律写**相对知识库根、无前缀**：`![alt](.memoria/images/文件名.png)`；**禁止 `..` 上跳**（会被判路径逃逸 → 404）。
- 路径含空格/中文用尖括号：`![alt](<.memoria/images/屏幕截图 2026.png>)`。
- 显示属性写 title 位：`![alt](url "width=300,align=center")`（仅 `width/enlarge/align` 等白名单属性）。

## 7. 撰写 / 整理 / 维护规则

### 7.1 撰写（新增用户想写入的知识）
1. **来源可溯**：内容须对应用户提供的要点/资料或库内既有 KP；你自行补充的一般性内容，必须在正文标注：
   `<!-- ⚠ 来源待核实：<说明> -->`
2. **先查重**：按 sidecar 索引查是否已有同概念 → 有则**扩写/合并**，不重复新建。
3. **必挂链**：新 KP 至少一条 `[[已有-kp-id]]`，并在相关已有 KP 处补反向链接。
4. **先清单后落笔**：按批次给出完整写入清单（路径 + 文件名 + KP id/name + 拟链接），确认后一次性写入。

### 7.2 整理（原始材料 → KP）
**保留原文、不改语义**：只做排版、KP 划分、链接与标签标注；不删减/改写/总结/扩写；不添加材料里没有的知识。
发现问题用注释标注（不改原文）：`<!-- ⚠ 待核实：… -->`、`<!-- ❓ 存疑：… -->`、`<!-- 🔄 歧义：… -->`。

### 7.3 维护（KP 与链接）
- 新增/更新 KP：按 §2 改 sidecar。
- 补链接与边：按 §4 写正文；`contain` 交给系统。
- 拆分/合并：合并时 concepts 累加、链接指向保留；拆分时各自成 KP 并补互链。
- 改 KP id / 重命名文件（全库级联）、删除文件/KP、跨目录移动、批量重组 → **先问用户**。

### 7.4 收尾自检（缺一不可）
1. 每个 KP 的 `name` 能在正文找到对应标题；
2. 每个 sidecar 的 `range` snippet 能在正文**精确匹配**，`end` 非空行；
3. 所有 `[[id]]` 的目标在 sidecar 中存在（或**有意**为虚链）；
4. 提示用户在 Memoria 执行「构建」「检查」，无错误后交付。

## 8. 常见坑

- 只改 md 不改 sidecar → 产品里看不到 KP（§1）。
- 手写 `manifest.yaml` → 与产品指纹不一致（应交给「构建」）。
- `range.end.snippet` 填了空行/不唯一文本 → 定位失败。
- 图片路径带 `../` 或 `./` 前缀 → 渲染 404。
- 把学习进度写进 sidecar → 污染知识语义。
- 把 `contain` 边手标进正文 → 与系统自动生成重复。
