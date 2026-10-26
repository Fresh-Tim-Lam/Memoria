[English](README.md) | 中文

# Memoria 文档中心

> **用途**：`docs/` 的入口索引——列出全部子目录职责与关键文档，供人机快速定位。
> **目标读者**：项目负责人（用户）与 AI Agent（进入 docs 前先读本页）。
> **关联文档**：[conventions/docs-management.md](conventions/docs-management.md)（docs 组织规则，含目录登记表）。

---

## 子目录导航

| 目录 | 职责 | 入口/关键文档 |
|------|------|--------------|
| `conventions/` | 契约性规范（人机都必须遵守的规则） | [README.md](conventions/README.md)（规范清单） |
| `guides/` | 操作指引（how-to：怎么做某事） | [README.md](guides/README.md) |
| `reference/` | 参考说明（understand：架构、术语、硬约束、功能机制） | [README.md](reference/README.md) |
| `design/` | 设计文档与决策记录 | system-design.md、dicussion.md、designV0.md 等；**知识图谱本体**：[kg-ontology-v0.md](design/kg-ontology-v0.md)（13 条裁决，FROZEN 2026-10-25）、[kg-visualization-v0.md](design/kg-visualization-v0.md)（可视化 v0 冻结设计，FROZEN 2026-10-26）；**发布包格式契约**：[release-format.md](design/release-format.md) |
| `marketing/` | 对外表述与发版 SOP（README / Release / 仓库页的事实来源） | [claims.md](marketing/claims.md)（**断言—证据表**：每条能力声明必须先登记并指向可核验证据）、[repo-metadata.md](marketing/repo-metadata.md)（GitHub「About」/ topics / 社交预览 / 截图素材文案）、[tag-release-spec.md](marketing/tag-release-spec.md)（打 tag 与建 Release 的可勾选 SOP） |
| `todo/` | 台账附件（活跃详情；由 `todo.md` 索引化拆出） | [README.md](todo/README.md)（每节一份 `<NN>-<slug>.md`） |
| `sessions/` | 历史对话记录（承接上下文，原 agents/） | 各会话文档 |
| `example/` | 示例知识库容器：showcase/（官方展示，入库）与 import-test/（夹具，入库）；其余本地样例与个人库仅存本地 |
| `refs/` | 开发参考资料 | [README.md](refs/README.md) |
| `prompts/` | 提示词模板 | [README.md](prompts/README.md) |
| `tmp/` | 少量诊断/调试记录 | 调试会话记录 |

## 三类主目录怎么选

| 内容类型 | 归属 | 典型例子 |
|---------|------|---------|
| 契约 / 规则（人机都要遵守） | `conventions/` | 版本、语法、导入格式、日志、目录组织、docs 管理 |
| 操作指引（how-to：怎么做） | `guides/` | 知识库生产流水线、AI 编程协作方式 |
| 参考说明（understand：是什么/为何） | `reference/` | 系统架构、术语表、硬约束、图片功能机制 |

详细决策流程见 [conventions/docs-management.md](conventions/docs-management.md#2-子目录职责与决策表)。

## 根目录规则

`docs/` 根只允许以下文件：
- `README.md`（本页，总索引）
- `todo.md`（活跃工作清单/待办）

其余文档一律归入上表子目录；新增子目录须登记到 [conventions/docs-management.md](conventions/docs-management.md#4-自维护机制) 目录登记表。

## 快速导航（按任务）

| 我想… | 看这里 |
|-------|--------|
| 查当前版本 / 升级版本 | [conventions/version.md](conventions/version.md) |
| 决定文件放哪 | [conventions/directory-organization.md](conventions/directory-organization.md) |
| 新增 docs 子目录 | [conventions/docs-management.md](conventions/docs-management.md#4-自维护机制) |
| 了解系统架构 | [reference/architecture.md](reference/architecture.md)、[design/system-design.md](design/system-design.md) |
| 了解 `[[]]` 语法 | [conventions/markdown-form-std.md](conventions/markdown-form-std.md) |
| 让 Agent 生产/转换知识库 | [guides/usage-agent-workflow.md](guides/usage-agent-workflow.md) |
| 接入新 AI/交接 | `reference/` 全部 + [guides/README.md](guides/README.md) + [conventions/README.md](conventions/README.md) |
| 找历史对话 | `sessions/` |
