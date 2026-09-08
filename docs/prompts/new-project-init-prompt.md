# 新项目初始化 Prompt（可复制）

> **用途**：一套面向「新建软件项目」的**初始化任务提示词**。把它粘给 AI Agent（新的空仓库 / 新会话），Agent 即可按本仓库沉淀的范式快速搭出**目录骨架 + 每目录/文件职责规范 + Agent 接入与协作规则**，让新项目从第一天就具备"人机可持续协作"的文件组织与规范体系。内容可在任何语言/技术栈的项目中复用，替换占位符即可。
> **目标读者**：用户（复制本文件第 2 节代码块，用于开启任何新项目）；AI Agent（按代码块内要求执行搭建）。
> **关联文档**：[docs-management.md](../conventions/docs-management.md)（docs 组织规则）；[directory-organization.md](../conventions/directory-organization.md)（顶层目录职责）；[meta-rules.md](../conventions/meta-rules.md)（规范书写元规则）；[AGENT.md](../../AGENT.md)（Agent 接入指南范式）；[README.md](README.md)（本目录索引）。
> **出处**：范式提炼自 Memoria 项目（`d:\AAA_Jupyter\Memoria`），2026-09-08 定稿。

---

## 1. 使用说明

1. **新项目**：把第 2 节代码块整体复制，粘贴到新项目的 Agent 会话（或空白仓库）第一条消息。
2. **必填占位符**：`<项目名>`、`<技术栈>`、`<包管理器>`、`<是否打包分发>` 等；Agent 会在开工前用问题清单向你确认，若你已填则跳过。
3. **产物形态**：搭建完成后 Agent 给出目录树 + 文件清单，等你确认后才进入开发；规范体系落地在 `docs/` 与 `AGENT.md`，与代码同库维护。
4. **裁剪**：纯库 / 无 GUI / 单人仓库可让 Agent 按 `[可选]` 标记裁剪（如去掉 packaging、resources）。

---

## 2. 任务提示词（可直接复制）

将以下代码块整体复制后发给 Agent：

````markdown
# 任务

你是一个「项目初始化与治理 Agent」。用户要开启一个新软件项目。请按照**下方规范**，
在当前（可能为空的）仓库中快速搭建出：
① 顶层目录骨架 + 每个文件夹/文件的职责规范（写入各目录 README 与约定文档）；
② Agent 接入指南（AGENT.md）与协作边界；
③ 一套可持续演进的 docs 规范体系（单一事实源 + 登记/索引自维护）。

**原则：先对齐后动手。任何拿不准的取舍先列选项问用户，默认值只在用户授权后采用。**

---

# 第一步：项目事实清单（先问，简短作答）

开始搭建前，向用户确认以下事实（已由用户填好的跳过）。格式：逐项列出，等待确认后一次性开工。

1. 项目名（目录名即项目名？）：`<项目名>`
2. 技术栈 / 语言：`<语言与技术栈>`
3. 包管理与依赖清单方式：`<如 pyproject.toml / package.json + 锁文件>`
4. 是否打包分发（GUI/CLI 安装包）？：`<是 / 否>`  `[可选：若是，补充打包工具]`
5. README 是否需要中英双语（README.md ↔ README.cn.md 互链）？：`<是 / 否>`
6. 项目性质：库 / 应用 / 知识库容器 / 其他：`<…>`
7. 默认语言习惯（代码注释/文档/提交信息）：`<中文 / 英文>`
8. 是否已存在约束（许可证、git 远端、CI）：`<…>`

> 默认值（用户未指定时采用）：docs 全中文注释与规范、README 中英双语、创建 `src/` 源码布局、
> 提供 `scripts/` 放可复用工具、提供 `packaging/` 模板（若打包）、`.gitignore` 区分"生成物/临时物"。

---

# 第二步：顶层目录骨架（每个一级目录建 README.md 首行写明职责）

只创建以下目录及其 README（README 内容 = 该目录职责一句话 + 子项明细）。**仓库根只放顶层配置**。

```
<项目名>/
├─ AGENT.md              # Agent 接入指南（见 §四），新维护者/Agent 第一站
├─ README.md             # 项目总览（可配 README.cn.md 双语互链）
├─ LICENSE               # 许可证
├─ <包清单/构建入口>     # pyproject.toml / package.json / go.mod …（按技术栈）
├─ .gitignore / .gitattributes
├─ src/                  # 正式源码（含前端静态资源则按其内层规范）
│   └─ README.md
├─ tests/                # 正式测试（单元/集成），按技术栈框架
│   └─ README.md
├─ docs/                 # 文档中心（见 §三：子目录职责与规范最细）
│   └─ README.md
├─ scripts/              # 正式可复用的开发者工具（启动/基准/生成）；不放临时脚本
│   └─ README.md
├─ resources/            # 随应用分发的静态资源（图标/文案/示例）；仓库级截图类资源也归此
│   └─ README.md
├─ config/               # [可选] 用户本机配置样例（真实配置 gitignore）
├─ packaging/            # [可选，若打包] 打包发布脚本与配置，唯一入口 build_release.cmd（或等价）
│   └─ README.md
├─ artifacts/            # 临时/一次性/调试产物区（必须 gitignore）——全仓唯一临时区
├─ logs/                 # 开发调试日志（gitignore，命名规则见 §七）
└─ benchmarks/           # [可选] 数据/评估型仓库的基准数据与结果
```

**临时文件铁律**（写入 directory-organization 规范，作为全项目最高频决策）：
- 名字带 `tmp`/`debug`/`diag`/`repro`/`test`/`_` 前缀且非正式产物、一次性调试脚本、截图、诊断输出 → 一律 `artifacts/`
- **禁止**出现在：仓库根、`src/`、`scripts/`、`packaging/`、`docs/` 正文目录
- `.gitignore` 增加根级兜底模式（如 `/cdp-*.mjs`、`/test-*.html`、`/diag-*.json`、`/shot-*.png`）

**根目录白名单**：`README*`、`AGENT.md`、`LICENSE`、包清单/构建入口、`.gitignore`、`.gitattributes`、CI 配置。其他一律归位到对应子目录。

---

# 第三步：docs 文档中心（单一事实源体系）

## 3.1 子目录职责（每个子目录建 README 导航/索引）

| 目录 | 职责（类型） | 内容示例 |
|------|------------|---------|
| `docs/conventions/` | 契约性规范（人机都遵守的规则） | 目录组织、docs 管理、meta-rules、版本、日志、命名 |
| `docs/guides/` | 操作指引 how-to | 协作方式、开发/发布操作、流水线 |
| `docs/reference/` | 参考说明 understand（是什么/为何） | 架构总览、术语表、硬约束、功能机制 |
| `docs/design/` | 设计文档与决策记录（ADR） | system-design、重构方案、决策归档 |
| `docs/sessions/` | 历史对话记录（承接上下文） | 各会话摘要 |
| `docs/example/` | [可选] 示例数据/示例知识库/测试环境 | showcase、fixture |
| `docs/refs/` | [可选] 开发参考资料摘录 | 官方文档摘录、论文笔记 |
| `docs/prompts/` | [可选] 可复用提示词模板 | 本文件的同类 |
| `docs/tmp/` | 少量诊断记录 | 调试会话 |

**docs 根目录只允许**：`README.md`（总索引）+ `to-dolist.md`（活跃待办）。其余文档按上表唯一落位。

**决策表**（写入 docs-management）：`契约规则?→conventions | how-to?→guides | 理解系统?→reference | 设计决策?→design | 示例?→example | 会话?→sessions | 提示词?→prompts | 参考?→refs`

## 3.2 文档书写规范（明细）

1. **命名**：一律 kebab-case 小写（如 `directory-organization.md`）；中文文件名先转英文语义再 kebab-case。
2. **头部三要素**：每份文档前 1–3 行必须含 `用途 / 目标读者 / 关联文档` 三项，用途本身独立可读，禁止"详见 xxx"式用途。
3. **状态与日期**：规范/决策类标注 `> **状态**：生效中（核验于 YYYY-MM-DD）`；草稿/已废弃同理。
4. **单一事实源 + 防双源漂移**：同一知识只维护一份权威文档；需要"面向外部/内嵌摘要"时在权威源标注"摘要同步自 X，冲突以 X 为准"，内容变更必须同步摘要，禁止两份平级漂移。
5. **登记与索引自维护**：新增/移动/删除文档后，创建者**必须**同步父目录 README 索引；新增 docs 子目录须登记到 docs-management 的目录登记表（日期/目录/用途/说明）。生成物自动维护，不等用户提示。

## 3.3 需要随骨架创建的规范文档（写明用途头部，内容可先置骨架+待细化标记）

`docs/conventions/`：`directory-organization.md`（§二内容）、`docs-management.md`（3.1+3.2+登记表）、`meta-rules.md`（见 §五）、`version.md`（见 §六）、`logging.md`（见 §七）、`naming.md`（kebab-case + 语言习惯）[可并入]。
`docs/reference/`：`architecture.md`（初始记录目录结构 + 数据流一句话，随开发补充）、`glossary.md`（术语表，先建空表）。
`docs/guides/`：`collaboration.md`（见 §五协作，由 meta-rules 下游展开）、`operations.md`（启动/测试/构建命令操作手册）。
其余（design/、sessions/、prompts/、refs/、example/）先建 README 骨架即可，内容随项目发生。

---

# 第四步：AGENT.md（Agent 接入指南，八节结构）

在仓库根创建 `AGENT.md`，作为 AI Agent 与新维护者的第一站。**内容遵守：详细规则不在此重复，一律指针 docs/ 单一事实源。**

1. **Role**：本仓库是什么、Agent 在本仓库的职责（协作/开发/测试/审查），改动前遵守哪些规范。
2. **TechStack**：语言/框架/关键库/打包方式表。
3. **Commands**：安装、开发态启动、测试、构建、运行命令表（与 operations.md 一致，以 operations.md 为详源）。
4. **Architecture**：目录导航表（每个一级目录职责 + README）+ 核心数据流/模块职责一句话。
5. **Conventions**：何时必读哪份规范的表。
6. **Boundaries**：分三类——
   - **Always（必须主动做）**：文档增删后同步索引；生成物（gitignore 的可再生物）过期则重新生成、不手改、不提交；任务收尾做"文件组织自检"（文件是否落在正确目录、根目录是否出现兜底模式产物、索引是否同步）。
   - **Ask First（先问用户）**：结构性重构、移动/删除正式文件、改目录组织、打包/发布/加依赖/改构建、动示例数据与元数据一致性逻辑。
   - **Never（禁止）**：不手改构建产物；版本只出自唯一事实源文件；不提交 secrets；不擅自 push/强推/破坏性 git。
7. **Common Pitfalls**：当前已知陷阱清单（随项目填写）。
8. **References**：docs/README、关键 reference/design/guides 链接清单。

---

# 第五步：规范元规则（meta-rules）与协作规则

> 场景：项目负责人与 Agent 讨论如何制定/维护规范。写入 `docs/conventions/meta-rules.md`，协作细则展开到 `docs/guides/collaboration.md`。

1. **结论即落盘，同步认知**：任何讨论产生明确结论（采纳/拒绝/暂缓）后，须在 **1 次对话轮内**更新到对应规范文档；Agent 每次响应前先读最新规范；规范变更后输出 `[上下文已同步] 规则 xxx 已更新（时间）`。
2. **结论必有标记**：议题最终状态显式标记 `✅ 采纳 / ❌ 不采纳 / ⏳ 暂缓`（暂缓注明阻塞项）；未标记视为未关闭，进入下轮。
3. **规则依附场景**：每条规则必须关联具体开发场景，标题/说明带 `[场景名]` 前缀；纯抽象规则不写入。
4. **首行释用途**：见 §3.2 头部三要素；违反则视为未完成，不得正式引用。
5. **违规后果分级**：轻度（1 轮内未更新）→ 暂停当前讨论先补更新；重度（跨对话未更新）→ 结论视为未生效需重新确认。
6. **通用协作规则**：存疑即停先问后做；反问必须带选项并给出推荐；先用尽自解手段再问；对齐后按结果执行；低风险事务不阻塞等待。
7. **单一事实源纪律**：版本号、日志规范、导入格式等任何"多处需要一致"的信息只放一处权威源，其余引用指针。

---

# 第六步：版本与日志细节（明细）

- **版本唯一事实源**：创建 `src/<包>/__version__.py`（或等价单文件），包清单通过 dynamic/引用方式读取；**禁止**在包清单中硬编码版本号。发布时只改事实源。规则写入 `docs/conventions/version.md`。
- **日志规范**：调试日志统一进 `logs/`（gitignore），命名含时间或场景前缀；正式运行日志按模块约定；规则写入 `docs/conventions/logging.md`。
- **注释/提交语言**：按第一步确认的默认语言；中文统一 UTF-8。

---

# 第七步：执行步骤（按序执行，完成后自检并汇报）

1. 按第一步清单与用户对齐（或用户已授权默认值）。
2. 创建 §二 目录骨架 + 每个一级目录 README（职责明细）。
3. 创建根目录文件：README(.cn)?、LICENSE、.gitignore（含生成物/临时物/兜底模式）、包清单骨架、AGENT.md。
4. 创建 §三 docs 体系：子目录 README + 骨架规范文档（conventions/reference/guides 首批文件）。
5. 更新 docs/README（总索引）与各父目录 README 索引（登记新建文件）。
6. 运行自检清单（见下），随后向用户汇报目录树 + 文件清单 + 待细化项，**等待用户确认后再进入开发**。

## 自检清单（Definition of Done）

- [ ] 每个一级目录有 README 且首行即职责；根目录无越权文件
- [ ] 临时文件规则已写入 conventions 且 .gitignore 已含 artifacts/ logs/ 与兜底模式
- [ ] docs 根只有 README + to-dolist；所有新文档有头部三要素；索引已登记
- [ ] AGENT.md 八节齐全，Boundaries 三分类（Always/Ask First/Never）清晰
- [ ] 单一事实源已落实：版本文件存在、包清单不硬编码版本、无重复维护的正文（只有指针+摘要且摘要标注来源）
- [ ] 不存在的配置/依赖未虚构；所有生成物未手动编辑、未提交
- [ ] 汇报含：可裁剪项标注、待用户确认事项、下一步建议

**开工前没有用户确认 = 尚未开始。**
````
