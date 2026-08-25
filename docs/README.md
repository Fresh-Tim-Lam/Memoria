# Memoria 文档中心

> **用途**：`docs/` 的入口索引——列出全部子目录职责与关键文档，供人机快速定位。
> **目标读者**：项目负责人（用户）与 AI Agent（进入 docs 前先读本页）。
> **关联文档**：[standards/docs-management.md](standards/docs-management.md)（docs 组织规则，含目录登记表）。

---

## 子目录导航

| 目录 | 职责 | 入口/关键文档 |
|------|------|--------------|
| `standards/` | 规范（人机都要遵守的规则） | [README.md](standards/README.md)（规范清单） |
| `context/` | AI 注入 / 交接说明（架构、术语、操作） | [README.md](context/README.md) |
| `design/` | 设计文档与决策记录 | system-design.md、dicussion.md、designV0.md 等 |
| `sessions/` | 历史对话记录（承接上下文，原 agents/） | 各会话文档 |
| `example/` | 示例知识库与测试环境 | example-boonie/、rich-content-test/、导入测试等 |
| `refs/` | 开发参考资料 | [README.md](refs/README.md) |
| `prompts/` | 提示词模板 | [README.md](prompts/README.md) |
| `tmp/` | 少量诊断/调试记录 | 调试会话记录 |

## 根目录规则

`docs/` 根只允许以下文件：
- `README.md`（本页，总索引）
- `to-dolist.md`（活跃工作清单/待办）

其余文档一律归入上表子目录；新增子目录须登记到 `standards/docs-management.md` 目录登记表。

## 快速导航（按任务）

| 我想… | 看这里 |
|-------|--------|
| 查当前版本 / 升级版本 | [standards/version.md](standards/version.md) |
| 决定文件放哪 | [standards/directory-organization.md](standards/directory-organization.md) |
| 新增 docs 子目录 | [standards/docs-management.md](standards/docs-management.md#5-自维护机制) |
| 了解系统架构 | [design/system-design.md](design/system-design.md) |
| 了解 `[[]]` 语法 | [standards/markdown-form-std.md](standards/markdown-form-std.md) |
| 让 Agent 生产/转换知识库 | [context/usage-agent-workflow.md](context/usage-agent-workflow.md) |
| 接入新 AI/交接 | `context/` 全部 + `standards/README.md` |
| 找历史对话 | `sessions/` |
