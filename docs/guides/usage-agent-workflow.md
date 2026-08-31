# 知识库生产流水线：Agent 协作使用指南

> **用途**：描述 Memoria 知识库从「原始知识文本」到「文件组织的知识库文件夹」的完整生产流程——**内容生成 Agent** 按规范产出知识库平面文件 → 用户转贴为单文件 → **知识库转换 Agent（项目管辖）** 把平面文件转换为有文件组织的知识库。本文档同时定义两个角色的职责与必须遵守的规则、知识库质量标准，以及文档自维护机制。
> **目标读者**：用户（编排流水线）；内容生成 Agent（角色 A）；知识库转换 Agent（角色 B）。
> **关联文档**：[conventions/import-format.md](../conventions/import-format.md)（平面文件格式规范）；[prompts/role-a-content-agent.md](../prompts/role-a-content-agent.md)（角色 A 完整手册）；[conventions/markdown-form-std.md](../conventions/markdown-form-std.md)（`[[]]` 语法体系）；[conventions/docs-management.md](../conventions/docs-management.md)（docs 自维护规则）。

---

## 1. 流水线总览

```
┌────────────┐   ┌───────────────────┐   ┌─────────────┐   ┌───────────────────┐
│ 原始知识文本 │ → │ 角色A：内容生成 Agent │ → │ 用户中转（转贴） │ → │ 角色B：知识库转换 Agent │ → 知识库文件夹
└────────────┘   └───────────────────┘   └─────────────┘   └───────────────────┘
                        ↓                        ↓                    ↓
                  平面文件（.txt）            分批内容拼为单文件        校验 + 构建 + 验证
```

| 步骤 | 执行者 | 输入 | 输出 |
|------|--------|------|------|
| 1 | 角色 A（内容生成 Agent） | 原始知识文本 + [角色 A 手册](../prompts/role-a-content-agent.md) | 知识库**平面文件**（`.txt`，`---` 分隔多段） |
| 2 | 用户 | 角色 A 分批输出的内容 | 单个平面文件（拼接所有批次） |
| 3 | 角色 B（知识库转换 Agent / 项目管辖） | 平面文件 | **知识库文件夹**（`.md` 文件 + `.memoria/sidecars/`） |
| 4 | 用户 | 知识库文件夹 | 用 Memoria「打开」该目录，点「构建」「检查」验收 |

> **两条等价路径**：步骤 3 也可以由 Memoria 自带的「导入」按钮完成（导入引擎自动执行段→文件 + sidecar 生成）。角色 B 手动转换遵循的规则与导入引擎一致，便于 agent 在不打开程序时也能生成合规知识库。

---

## 2. 角色 A：内容生成 Agent（知识整理）

> 角色 A 的**唯一完整手册**：[prompts/role-a-content-agent.md](../prompts/role-a-content-agent.md)（含任务提示词、平面格式规范、整理/分批规则、输出格式、自检清单、冲突处理）。本节为流水线层面的摘要。

### 2.1 职责

把用户提供的原始知识文本整理为 **Memoria 平面导入格式**，严格遵守 [conventions/import-format.md](../conventions/import-format.md)。

### 2.2 使用方式

- 直接使用 [prompts/role-a-content-agent.md](../prompts/role-a-content-agent.md)（内含可复制任务提示词，已内嵌完整格式规范与整理规则）
- 若提示词与 import-format.md 冲突，**以 import-format.md 为准**（手册第 9 节已声明此规则）

### 2.3 分批输出规则（内容过多时）

1. **分批原则**：内容过长时按主题自然切分为多批，每批输出一个完整的平面文件片段（含各自独立的 `---` 段）
2. **批次衔接**：每批仍必须以 `---` 开头的完整 frontmatter 段开始，保证用户拼接后文件结构合法
3. **跨批链接**：后批引用前批知识点时，直接写 `[[kp-id]]`（id 全局唯一，拼接后自然连通）
4. **总览先行**：分批前先输出「知识点总览表 + 链接关系表」，供用户确认划分合理后再逐批输出正文

### 2.4 输出质量底线

- 每个 KP id 全局唯一、英文 slug（小写 + 连字符）
- `name` 与正文 `##`/`###` 标题完全一致（转换阶段依赖该匹配定位 range）
- 正文原文保留、只标注不修改；用 `[[kp-id]]` 标注知识关联

---

## 3. 用户中转：分批内容 → 知识库平面文件

1. 接收角色 A 的分批输出，**按序拼接**到同一个 `.txt` 文件（各批之间保留 `---` 分隔段，不要增删空行）
2. 该文件即「知识库平面文件」——它是流水线的事实源，可长期归档
3. 交给角色 B（或直接用 Memoria「导入」按钮）

> 拼接是纯文本操作，用户只需保证：文件开头是 `---`、段与段之间由独立成行的 `---` 分隔、无被截断的段。

---

## 4. 角色 B：知识库转换 Agent（项目管辖）

### 4.1 职责

读取「知识库平面文件」，按本节省规则转换为**文件组织的知识库文件夹**，并验证其可被 Memoria 正常加载、构建、检查。

### 4.2 目标产物结构

```
knowledge-base/                     ← KB 根目录（用户用 Memoria「打开」它）
├── topic-a.md                      ← 一个知识点文件（可含多个 KP）
├── topic-b.md
├── subtopic/
│   └── topic-c.md                  ← 子目录按主题组织（可选）
└── .memoria/
    ├── sidecars/
    │   ├── topic-a.memoria.yaml    ← 与 md 一一对应的侧车
    │   ├── topic-b.memoria.yaml
    │   └── subtopic/topic-c.memoria.yaml   ← 侧车镜像 md 的目录结构
    └── manifest.yaml               ← 由 Memoria「构建」生成，agent 不手写
```

### 4.3 段 → 文件映射

| 平面文件段 | 转换产物 | 规则 |
|-----------|---------|------|
| 1 段 | 1 个 `.md` 文件 | 默认**一段一文件**，文件名 = 段内第一个 KP 的 `id` + `.md` |
| 多段同主题 | 1 个 `.md` 文件（合并） | 仅当这些段讲同一主题且合并后语义连贯；合并后 concepts 累加 |
| 1 段多 KP | 1 个 `.md` 含多 KP | 每个 `##` 标题对应一个 KP（`###` 为子 KP） |

文件名必须与 `concepts[0].id` 一致（如 `bayes-rule.md`）；**一个 id 全局只映射一个文件**。

### 4.4 `.md` 文件格式

```markdown
---
description: 一句话说明本文件主题
concepts:
  - id: kp-id-1
    name: 知识点名称1
    weight: 1.0
    tags: [标签1, 标签2]
  - id: kp-id-2
    name: 知识点名称2
    weight: 0.8
    tags: [标签a]
---

## 知识点名称1

（正文，原文保留）这里用 [[kp-id-2]] 标注关联。

## 知识点名称2

（正文）
```

字段规则与 import-format.md 一致；正文标题用 `##`/`###`，链接用 `[[id]]`、`[[id|文本]]`、`[[id#type]]`（语法见 [markdown-form-std.md](../conventions/markdown-form-std.md)）。

### 4.5 sidecar 生成（必须，构建依赖它）

> 关键：Memoria 的「构建」只把正文 wikilink **同步**进 sidecar `links[]`，而 **KP 节点完全来自 sidecar 的 `knowledge_points[]`**（见 `resolve_knowledge_points`）。sidecar 缺失或 KP 为空 → 图谱无节点。因此角色 B 必须为每个 `.md` 生成 sidecar。

```yaml
schema_version: 1
file: topic-a.md
knowledge_points:
  - id: kp-id-1
    name: 知识点名称1
    range:
      start: { snippet: "## 知识点名称1" }
      end:   { snippet: "该 KP 范围最后一行的正文片段" }
  - id: kp-id-2
    name: 知识点名称2
    range:
      start: { snippet: "## 知识点名称2" }
      end:   { snippet: "（最后一个 KP 的 end 可为文件末行）" }
links: []          # 可由 agent 预填，也可留空交给「构建」同步
edges: []
```

规则：
- `range.start.snippet` 必须能在正文中精确匹配（通常就是标题行）；`range.end.snippet` 是该 KP 末尾一行（下一个标题前的最后一行，不能为空行）
- 一个文件一个 sidecar，路径镜像 `.md` 目录（`subdir/topic-c.md` → `.memoria/sidecars/subdir/topic-c.memoria.yaml`）
- `links[]`/`edges[]` 可留空：用户打开 Memoria 点「构建」会自动同步正文 wikilink

### 4.6 链接与边

| 边类型 | 含义 | 是否手动标注 |
|--------|------|-------------|
| `reference` | 引用/参考（A 提到 B） | 正文 `[[id]]` 标注 |
| `extend` | 扩展/下游（A 是 B 的特例/实现） | 正文 `[[id#extend]]` 标注 |
| `contain` | 包含/父子（`##` ⊃ `###`） | **系统自动生成，禁止手动标注**；如需抑制用 `no_build: true` 标记 |

- 跨文件/跨段关联：在正文相应位置写 `[[目标kp-id]]`，转换时保留原文显示文本则用 `[[id|原文文本]]`
- 同一锚点可指向多目标：`[[id-a]]`、`[[id-b]]` 并列出现时，构建合并为 `targets: [id-a, id-b]`

### 4.7 目录组织与命名

- **命名**：文件英文 slug（kebab-case），目录英文；正文标题用中文
- **多级文件夹组织（重点）**：知识库文件夹支持任意层级目录结构，角色 B 应为主题规划目录树：
  - 按领域/章节建子目录，可多级嵌套（如 `MachineLearning/ReinforcementLearning/DDPG/`、`英语/词汇/外交`）
  - 导入时由 frontmatter `path` 字段直接指定（如 `path: MachineLearning/Basics`），目录自动创建，sidecar 同步镜像；未指定 `path` 的段落根目录
  - 组织原则：同主题文件进同一目录；目录名语义化；避免根目录散落文件；hub/README 文件可置于根目录
- **Hub 页**：知识库较大时创建 1 个概览文件（如 `README.md` 或 `overview.md`），用链接串起主要 KP 作为阅读入口（示例：`example/example-boonie/dog-xiong-ridge.md`）

> **完整落地示例**：`example/example-english-kb/` 是「角色 A 平面文件（docs/sessions/AgentAnswer.md，两批会话记录）→ 导入 → 知识库文件夹」的成品——9 个 md + 9 个 sidecar，图谱 40 节点 23 边。每段单一主题、相关 KP 互链，导入引擎自动剥离批次围栏与对话噪音。可直接用 Memoria「打开」该目录查看。

### 4.8 交付前验证

1. 每个 `.md` 的 `name` 都能在正文中找到对应 `##` 标题
2. 每个 sidecar 的 range snippet 都能在正文中精确匹配，end 非空行
3. 所有 `[[id]]` 的目标 id 都存在于全部 frontmatter 的 concepts 中；悬空链接保留原样（系统支持虚链，**不要**创建空文件）
4. 用户用 Memoria「打开」→「构建」→「检查」无错误后交付

---

## 5. 知识库质量标准（well-organized + 清晰链接）

> 一个全面的知识库至少满足以下两条，角色 A/B 在各自环节都要自查。

### 5.1 知识点组织（well-organized）

- **原子性**：知识点是最小语义单位，一个 KP 聚焦单一概念，不合并不同主题
- **唯一性**：id 全局唯一；同一概念只在一个 KP 中定义，其余处用链接指回
- **完整性**：每个 KP range 覆盖完整语义段，不截断在空行
- **层级清晰**：`##` 一级、`###` 二级，父子关系即 contain 边
- **检索友好**：`name` 用自然中文，`tags` 覆盖领域/类型/别名（如「强哥」→ 光头强）

### 5.2 链接与跳转（清晰）

- **有出链**：每个 KP 至少指出与它相关的上游/下游知识点（reference/extend）
- **有入链**：被多处提及的概念（Hub、高频概念）应被多个文件链接，保证可从任意入口跳达
- **双向可达**：A→B 存在时，B 侧应有反向语境（不一定对称，但整库无孤立节点）
- **多跳路径**：存在 Hub → 主题 → 细节的阅读路径（可用 Alt+← 返回）
- **虚链策略**：确有计划但尚未建立的跳转保留 `[[id]]` 悬空，不创建空文件

---

## 6. 自维护机制（Agent 主动更新，无需用户提醒）

> 随 Memoria 在 AI Agent 操作下迭代，本流水线涉及的所有文档应由**正在执行相关任务的 Agent** 主动更新，不等用户提醒。

### 6.1 触发时机

- 你（Agent）发现平面格式、sidecar 结构、链接语法、构建行为等任一环节与文档描述不符
- 你完成一次知识库转换/整理后，发现文档缺失某条实际遇到的规则
- Memoria 代码演进导致行为变化（如导入引擎、图谱构建改动）

### 6.2 更新顺序（防双源漂移）

1. **先改规范**：平面格式 → `conventions/import-format.md`；`[[]]` 语法 → `conventions/markdown-form-std.md`
2. **再同步角色 A 手册**：`prompts/role-a-content-agent.md`（其第 9 节已声明以规范为准，但内容应同步避免误导）
3. **再同步本文档**：本流水线规则、质量标准随之修订
4. **登记**：在 `conventions/docs-management.md` §4.2 规范修订记录登记一行（日期/文档/修订内容）

### 6.3 每次知识库任务的收尾动作

- 检查本文件 §2/§4/§5 是否覆盖你本次实际遇到的全部规则，缺则补
- 若你为某规则新增了示例，把示例落到 `docs/example/`（如 example-boonie、example-english-kb），并在文中引用

---

## 7. 常见问题

| 问题 | 处理 |
|------|------|
| 角色 A 分批输出太多，拼接后导入报错？ | 检查拼接文件：每段 `---` 独立成行、frontmatter 完整、无截断段；报错详情复制给角色 A 修正 |
| 转换后打开 Memoria 图谱没有节点？ | 检查 sidecar `knowledge_points[]` 是否为空（§4.5）——构建只同步 links，不生成 KP |
| `[[id]]` 指向不存在的知识点？ | 保留悬空（系统支持虚链）；确认 id 拼写与 frontmatter 一致后重新构建 |
| 想让某个 `##` 不成为 contain 父节点？ | 在 sidecar 对应 KP 加 `no_build: true`，构建时跳过该 contain 边 |
| 与已有知识库重名 id？ | 要么改新 id，要么覆盖；Memoria「导入」会给出冲突报告逐条处理 |
