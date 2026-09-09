# Docs 组织管理规范

> **用途**：定义 `docs/` 文件夹的组织规则（子目录职责、根目录准入、文档生命周期），建立**自维护机制**（目录登记表 + 索引同步 + 定期整理），使任何人（含 AI Agent）无需额外提醒即可正确归置文档，并允许目录体系随项目演进自行拓展完善。
> **目标读者**：项目负责人（用户）与 AI Agent。
> **关联文档**：[meta-rules.md](./meta-rules.md)（本规范遵循的元规则）；[collaboration.md](../guides/collaboration.md)（开发场景协作）；[context-key.md](./context-key.md)（CTX-KEY 防火墙）；[refs-system.md](./refs-system.md)（refs 系统）。

---

## 1. 核心原则

1. **唯一落位**：任何文档按 [§2 决策表] 必须能唯一确定归属目录，不允许"放哪都行"。
2. **根目录极简**：`docs/` 根只允许 `README.md`（总索引）与活跃工作清单 `to-dolist.md`。
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

> 历史沿革：`agents/`（旧）→ `sessions/`（2026-08-20）；`skills/`（空目录，供将来存放可执行技能说明或并入 `context/` 用途）；`standards/` + `context/` → 按性质拆分为 `conventions/`（契约）+ `guides/`（how-to）+ `reference/`（understand）（2026-08-30）。

### 4.2 规范修订记录

| 日期 | 规范 | 修订内容 |
|------|------|---------|
| 2026-08-20 | docs-management.md | 初版建立 |
| 2026-08-20 | logging.md | 新增：日志存放位置、命名、格式约定、生命周期 |
| 2026-08-26 | image-features.md | 新增：图片功能说明文档，登记索引；后续随阶段落地更新 |
| 2026-08-26 | image-asset-dev-plan.md | 新增：图片资产管理分阶段开发方案（design/），六阶段可交互验证；A/B/C/D 已落地并记录验证结果 |
| 2026-08-30 | docs-management.md | 目录体系重构：`standards/` → `conventions/` + `guides/`；`context/` → `guides/` + `reference/`；新增三目录 README 与 reference/architecture、glossary、hard-constraints；决策表/登记表/沿革同步更新 |
| 2026-09-01 | preview-formats.md | 新增：预览渲染格式与样式说明（reference/），登记 reference/README.md |
| 2026-09-03 | docs-management.md | 新增 `screenshots/` 目录登记（README/GitHub 演示截图），docs/README.md 导航同步；后经复核 `screenshots/` 属**非文档内容**（图片资源），随仓库截图约定迁出 docs（目录登记行删除） |
| 2026-09-03 | i18n.md / i18n-inventory.md | 新增：语言系统维护规范（conventions/）与 UI 界面文案登记清单（reference/，由 scripts/scan_ui_strings.py 刷新），登记两目录 README 索引 |
| 2026-09-03 | readme-i18n.md | 新增：README 与项目截图中英双语维护规范（conventions/）；同日 `docs/screenshots/` 迁出至 `resources/screenshots/`（docs 不存截图类二进制资源），登记 conventions/README.md |
| 2026-09-04 | i18n.md / i18n-inventory.md | 编辑块工具栏整文件接入 `edit.block.*`（edit-handler.js，32 候选清零，文件退出清单）；i18n.md 修订记录与 `edit.` 前缀登记、清单迁移记录同步 |
| 2026-09-04 | i18n.md / i18n-inventory.md | 图谱/检索设置页整文件接入（graph-settings.js + graph-label.js + search-settings.js，71 候选清零，三文件退出清单）；新增 `graph.settings.*`/`graph.sample.*`/`graph.labelModes.*`/`search.settings.*`，`SAMPLE_GRAPH` 改 `buildSampleGraph()` |
| 2026-09-04 | collaboration.md | 新增 §0「通用协作规则（存疑对齐，适用于所有场景）」：存疑即停先问后做、反问须具体带选项/推荐、先用尽自解手段再问、对齐后按结果执行、低风险事务不阻塞（guides/，登记 guides/README 指引清单现有条目内，无新文件） |
| 2026-09-04 | i18n.md / i18n-inventory.md / scan_ui_strings.py / js/* | i18n 收尾改为「app.js 拆分 + 随拆分同步 i18n」专项：扫描器剔除规则修订；导入流程抽为 `js/import-flow.js`（`window.MemoriaApp` 门面 + boot init）；其余拆分候选顺序依可行性修订（搜索→图片→KB 检查→文件树→取色器/画笔） |
| 2026-09-08 | export-plan.md | 新增：导出功能设计文档（design/，草稿待评审）。范围=知识库包（kb_bundle）导出（导入 §4C 逆过程）；R12/R14/PDF 明确非本期；含产物规格/RPC/UI/阶段与打开问题 |
| 2026-09-09 | maintenance-jobs.md | 新增：维护作业与静默同步设计（design/，草稿待评审）。以 OS 任务视角统一“保存后派生维护”：作业模型/调度内核/前后端执行边界/作业登记表/P0–P3 阶段与打开问题 |
| 2026-09-09 | to-dolist §12 + 代码复核 | 施工总表（A–E）建立并落盘 to-dolist §12；2026-09-09 代码复核修正：A7 原子写注明范围、B2 partial 上屏、恢复 export-plan.md（此前缺失致引用悬空）、E4 补本登记行 |
| 2026-09-09 | maintenance-benchmark.md | 新增：维护机制基准设计（design/，草稿待评审）。受控语料/指标采集/A–B 对照/门禁规则，回答“调度等机制改造前后改善多少”；当前无基准实现 |
| 2026-09-09 | collaboration.md | §0 通用协作规则新增规则 6「待评审问题须答复后才继续」：Agent 提出的待评审/打开问题未获答复前不得默认继续执行或给下一步方案 |
| 2026-09-09 | M1/A7 原子写 | 正文保存（document.py save_document）与 ui-settings（storage/ui_settings.py）改 tmp+os.replace 原子写并验证（M1） |

### 4.3 定期整理约定

- **触发点**：每次发布里程碑（`packaging\build_release.cmd` 成功）或每月底。
- **动作**：① 检查 `docs/` 根是否出现非允许文件 → 归位；② 检查新文档是否已登记索引；③ 检查临时产物是否都在 `artifacts/`。

## 5. 已执行的整理

### 5.1 2026-08-20

- `agents/` → `sessions/`（更名迁移，内容不变）
- 根目录散文档归位：`designV0.md`/`dicussion.md`/`system-design.md`/`preview-sync-refactor-plan.md` → `design/`；`markdown_form_std.md` → `standards/markdown-form-std.md`；`usage.md` → `standards/import-format.md`；`description_of_kb.md` → `example/`；`outs.md`/`127.0.0.1-*.log`（日志）→ `artifacts/`
- 删除 `_archive/`（早期草稿，git 历史可恢复）
- 根目录现存文件：`README.md` + `to-dolist.md`（活跃待办），符合 [§1 原则 2]

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
