# Docs 组织管理规范

> **用途**：定义 `docs/` 文件夹的组织规则（子目录职责、根目录准入、文档生命周期），建立**自维护机制**（目录登记表 + 索引同步 + 定期整理），使任何人（含 AI Agent）无需额外提醒即可正确归置文档，并允许目录体系随项目演进自行拓展完善。
> **目标读者**：项目负责人（用户）与 AI Agent。
> **关联文档**：[meta-rules.md](./meta-rules.md)（本规范遵循的元规则）；[collaboration.md](../guides/collaboration.md)（开发场景协作）；[context-key.md](./context-key.md)（CTX-KEY 防火墙）；[refs-system.md](./refs-system.md)（refs 系统）。

---

## 1. 核心原则

1. **唯一落位**：任何文档按 [§2 决策表] 必须能唯一确定归属目录，不允许"放哪都行"。
2. **根目录极简**：`docs/` 根只允许 `README.md`（总索引）与活跃工作清单 `todo.md`；`todo.md` 的**详情附件**统一放 `docs/todo/` 子目录（索引化规则见 §4.2）。
3. **新文档必登记**：新建文档后必须同步父目录索引（README 或本规范相关表格）。
4. **新目录必登记**：新增子目录必须登记到 [§4.1 目录登记表]，否则视为无效。

## 2. 子目录职责与决策表

| 内容类型 | 归属目录 | 示例 |
|---------|---------|------|
| 契约性规范（人机都要遵守的规则） | `conventions/` | 版本、语法、导入格式、目录组织、日志、docs 管理、元规范 |
| 操作指引（how-to：怎么做） | `guides/` | 知识库生产流水线、AI 编程协作方式、开发/发布操作 |
| 参考说明（understand：架构/术语/机制） | `reference/` | 系统架构总览、术语表、硬约束、图片功能机制 |
| 设计文档 / 决策记录（ADR） | `design/` | system-design、refactor 方案、discussion 归档 |
| 历史对话记录（承接上下文） | `sessions/` | 与原 agents/ 相同，仅改名 |
| 示例知识库 / 测试环境 | `example/` | 示例 KB、rich-content-test、导入测试 |
| 开发参考资料 | `refs/` | 官方文档摘录、论文笔记（遵循参考资料系统规范） |
| 提示词模板 | `prompts/` | 知识整理导入提示词等 |
| 少量诊断 / 调试记录 | `tmp/` | 调试会话记录 md |
| 临时产物 / 日志 | `artifacts/`（仓库根，非 docs） | 日志、截图、一次性脚本（已被 gitignore） |

**决策流程**：`契约性规则（人机都要遵守）? → conventions | 操作指引（how-to）? → guides | 参考说明（理解系统）? → reference | 设计决策? → design | 示例数据? → example | 历史对话? → sessions | 提示词? → prompts | 参考资料? → refs`

## 3. 文档规范（符合 AAA 元规范规则 4）

1. **命名**：kebab-case 小写（如 `markdown-form-std.md`）。
2. **头部三要素**：每份文档前 1-3 行必须包含 `用途 / 目标读者 / 关联文档`（格式见各 conventions 文档）。
3. **状态标记**：规范/决策类文档标注状态（`生效中` / `草稿` / `已废弃`）与日期。
4. **索引同步**：文档新增/移动/删除后，创建者必须同步更新父目录 README 或本规范。

## 4. 自维护机制

> 使 docs 体系在不依赖用户逐条指示的情况下自我演进。

### 4.1 目录登记表（新增子目录时在此登记）

| 日期 | 目录 | 用途 | 说明 |
|------|------|------|------|
| 2026-08-20 | `sessions/` | 历史对话记录 | 由 `agents/` 更名迁移，语义更准 |
| 2026-08-20 | `standards/` | 规范体系 | 纳入版本/目录组织/docs 管理/语法/导入格式等 |
| 2026-08-20 | `context/` | AI 注入与交接说明 | 供 skill 注入与新手 agent 上手 |
| 2026-08-30 | `conventions/` | 契约性规范 | 由 `standards/` 拆分重组，中文文件名重命名 kebab-case |
| 2026-08-30 | `guides/` | 操作指引 how-to | 由 `standards/`（AI 协作）+ `context/`（usage-agent-workflow）迁移 |
| 2026-08-30 | `reference/` | 参考说明 | 由 `context/`（image-features）迁移，新增 architecture/glossary/hard-constraints |
| 2026-10-26 | `docs/todo/`（文档内相对 `todo/`） | 台账附件（活跃详情） | `todo.md` 索引化拆出：每节一份 `<NN>-<slug>.md`，只放 todo 索引指向的详情；历史归档仍进 `design/` |
| 2026-09-15 | `reference/agent-guide/` | 面向 Agent 的**功能·排版·交互说明书**（10 篇 + 索引） | 供外部集成方（把 Memoria 嵌进 dsh 的插件等）与后续 Agent 建立准确心智模型；每处描述带 `文件:行号` 证据锚，末节登记"未证实/待确认" |

> 历史沿革：`agents/`（旧）→ `sessions/`（2026-08-20）；`skills/`（空目录，供将来存放可执行技能说明或并入 `context/` 用途）；`standards/` + `context/` → 按性质拆分为 `conventions/`（契约）+ `guides/`（how-to）+ `reference/`（understand）（2026-08-30）。

### 4.2 规范修订记录

> **修订流水已拆出**（2026-10-19）：「规范修订记录」的逐条流水已迁至 [documentation-changelog.md](../design/documentation-changelog.md)（docs 内、规范体系的一部分）。本节只保留指针；**新变更追加进 changelog 文件**。
> **勘误（对既有提交信息的更正，非新工作）**：`37739bc6`（收录 AAA_Vocab 库内产物）那次提交信息里曾说"该库 `.memoria/**` 私人数据不在本次范围"，**实际 `docs/example/**/.memoria/sidecars/**` 被一并提交了**（sidecar 在本仓是被追踪内容）；真正被 `.gitignore` 排除的是 `review/**`、`sessions/**`、`backups/**`。

- **动作**：① 检查 `docs/` 根是否出现非允许文件 → 归位；② 检查新文档是否已登记索引；③ 检查临时产物是否都在 `artifacts/`；④ 检查台账体积是否在预算内（`docs/todo.md` **≤ 64 KB**（2026-10-22 调整，见下方说明）、`docs/design/maintenance-jobs.md §5` ≤ 8 KB；守卫 = `python scripts/check_todo_size.py` / `python scripts/check_jobs_size.py`），超限即按 [ledger-maintenance.md 规则 8](./ledger-maintenance.md) 清理（已收口条目出表入归档、开发流水账移除、压缩前事实须先转移到对应文档）。
- **台账硬规则（2026-10-22 随预算调整生效，守卫脚本 = `python scripts/check_todo_size.py`）**：
  1. **单元格 ≤200 B**（新增/修改条目；存量超限单元格以守卫脚本内的**基线清单**冻结，只允许变小，不允许变大或新增）；
  2. **禁止叙述体**：长文（做法 / 证据 / 未取证全文）进 `docs/design/**`，`todo.md` 只留一行索引 + 指针（先例：`agent-panel-batches.md` / `ledger-archive-2026.md` / `editor-input-defects-2026-10.md` / `packaging-release.md`）；
  3. **禁止等宽填充对齐**：表格用紧凑格式（`| a | b |`），不得用连续空格把列撑齐；
  4. **超限后的正规动作**：把**已收口条目**按 P1 先例归档到 `docs/design/**`（原文逐字、可 `git log -S` 追溯），台账只留索引行；**不得**靠调高预算或删条目/删证据锚达标；预算调整须人批准并注明日期与理由。
  5. **索引化（2026-10-26 人批准）**：`todo.md` 是**索引**——只允许 标题 / 状态 / 一行摘要 / 详情链接；详细内容只在 `docs/todo/<NN>-<slug>.md`（活跃详情）或 `docs/design/**`（已收口归档）。**禁止双事实源**（同一详情不得两处各写一版）。
  6. **链接与引用（2026-10-26 人批准）**：索引行详情链接必须指向真实存在的文件/锚点（**死链 = FAIL**）；`docs/todo/*.md` 必须被 `todo.md` 引用（**孤儿 = WARN**）；引用 `todo.md` **必须用 §-锚点或任务 ID，禁止用行号**（行号随插入失效）。
- **预算调整记录（2026-10-22）**：`docs/todo.md` 预算 **36 KB → 64 KB**。
- **索引化与预算（2026-10-26，人批准）**：`todo.md` 改为索引（详情进 `docs/todo/`）。Batch A（§13，106 行）后 **实测 65,445 → 54,382 B（−11,063 B）**；Batch B（§12，7 行）后 **54,557 → 50,066 B（−4,491 B）**；**A+B 合计 −15,379 B（−23.5%）**；**预算已按实测 64 KB → 56 KB 生效（2026-10-26，人批准）**；全量 C 批后按**实测**再定（40 KB 仅为预估，暂不批）。守卫脚本同步升级：死链 FAIL / 孤儿 WARN / 未索引化 WARN / `--selftest`。理由：① 旧预算在 ACTIVE 条目 170+、批次叙述持续增长后长期失真（曾达 797,845 B / 超 21.6 倍）；② 2026-10-22 完成 P1–P5 台账拆分与去填充后实测 **47,093 B**，64 KB 可留 ≈17 KB（约 3–5 批新缺陷）增长余量；③ 拆分为"活动 + 归档"两份文件会制造第二事实源（漂移风险高于可读性收益），故选择调预算 + 硬规则 + 守卫脚本，而非拆文件。
- **作业登记表治理（2026-10-23，W4.2）**：`maintenance-jobs.md §5` 的逐项明细（实现状态 / 证据锚 / 2026-09-14 对账修正原文）逐字迁入 [maintenance-jobs-archive-2026-10.md](../design/maintenance-jobs-archive-2026-10.md)，§5 只保留 `kind / 触发点 / 优先级 / 去重键 / 归属` 索引列，**§5 3,584 B → 2,523 B**。新增守卫 `python scripts/check_jobs_size.py`：断言 §5 ≤8 KB、每行 5 列且单元格 ≤200 B、无 ≥20 连续空格，并校验 **§5 索引与归档原表的作业 kind 集合 / 条数 / 优先级 / 去重键等价**；`--verify-verbatim <rev>` 另证归档逐字保留。新增作业须**同时**在 §5 登记索引行、在归档补明细行（否则守卫失败）。
  - **预算不变（仍 8 KB）**：核对发现长期计划 W4.2 写的「12,580 B vs 8 KB」实际是 `322be881` 时**整份文档**的字节数（该版本 §5 仅 2,942 B；W3.3 后整份 25,513 B、§5 3,584 B）。§5 从未突破 8 KB，本次归档针对的是 §5 内的叙述体与证据长文（单格最大 334 B），不是超预算处置；故不复制 `todo.md` 的「调预算」先例。

## 5. 已执行的整理

### 5.1 2026-08-20

- `agents/` → `sessions/`（更名迁移，内容不变）
- 根目录散文档归位：`designV0.md`/`dicussion.md`/`system-design.md`/`preview-sync-refactor-plan.md` → `design/`；`markdown_form_std.md` → `standards/markdown-form-std.md`；`usage.md` → `standards/import-format.md`；`description_of_kb.md` → `example/`；`outs.md`/`127.0.0.1-*.log`（日志）→ `artifacts/`
- 删除 `_archive/`（早期草稿，git 历史可恢复）
- 根目录现存文件：`README.md` + `todo.md`（活跃待办），符合 [§1 原则 2]

### 5.2 2026-08-30（目录体系重构）

- `standards/` 按性质拆分：契约性规范 → `conventions/`；AI 编程协作 → `guides/collaboration.md`
- `context/` 按性质拆分：usage-agent-workflow → `guides/`；image-features → `reference/`
- 中文文件名重命名为 kebab-case：`上下文规范.md` → `conventions/context-key.md`、`参考资料系统.md` → `conventions/refs-system.md`、`AAA_讨论元规范.md` → `conventions/meta-rules.md`、`AI 编程协作规范.md` → `guides/collaboration.md`
- 删除 `standards/README.md` 与 `context/README.md`，由 `conventions/`/`guides/`/`reference/` 三目录 README 取代
- 全部交叉引用同步（docs 内互链 + prompts/ + design/ 关联文档）

### 5.3 2026-09-03（演示截图迁出 docs）

- `docs/screenshots/`（`demo-*.png` × 7）→ `resources/screenshots/`（`git mv` 保留历史）——截图属**应用仓库静态资源**而非 docs 文档内容，且 README 仓库级展示配图应与 GitHub 展示约定一致。
- 引用同步：`README.md`、`README.cn.md` 全部 `<img src="docs/screenshots/…">` → `resources/screenshots/…`（14 处）。
- 目录登记同步：docs-management.md §4.1 删除 `screenshots/` 行（docs 不存二进制截图）；docs/README.md 子目录导航删除该行；resources/README.md 内容表补充 `screenshots/`。
- 新增规范 [conventions/readme-i18n.md](./readme-i18n.md)：README 双语（`README.md`↔`README.cn.md`）与截图收录/存放的维护规则（含自查清单）。

> **勘误（2026-10-11 补记，不改写上方任何历史行）**：① 上方 2026-10-10 的 R2 行所写 `type ∈ {basic,cloze,reverse}` 系**当时**裁决 —— 该枚举已于 2026-10-11 的 R4（`da433b3b`）放开为七种（`basic`/`cloze`/`reverse`/`mcq`/`gapfill`/`short`/`produce`，见 `src/memoria/services/agent/tools/kb.py` 的 `REVIEW_CARD_TYPES`）。② 上方 2026-09-25 的 AG92 行两处 `_restorePlainPosition()` 系**笔误**——仓内无此函数，真实实现为 `_saveCurrentViewScroll()` / `_restoreCurrentViewScroll()`（`src/memoria/ui/static/app/js/app.js`；同款更正另见 2026-10-09「导航位置恢复」行的备注）。
