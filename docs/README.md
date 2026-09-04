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
| `design/` | 设计文档与决策记录 | system-design.md、dicussion.md、designV0.md 等 |
| `sessions/` | 历史对话记录（承接上下文，原 agents/） | 各会话文档 |
| `example/` | 示例知识库与测试环境 | example-boonie/、rich-content-test/、导入测试等 |
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
- `to-dolist.md`（活跃工作清单/待办）

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
