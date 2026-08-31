# Prompts（提示词模板）

> **用途**：存放可复用的提示词模板（知识整理、导入等），供用户直接复制使用。
> **目标读者**：用户（复制使用）；AI Agent（新增模板时遵守本目录规范）。
> **关联文档**：[docs-management.md](../conventions/docs-management.md)（docs 组织规则）。

## 模板清单

| 文件 | 用途 |
|------|------|
| [role-a-content-agent.md](role-a-content-agent.md) | 角色 A（内容生成 Agent）完整手册：任务提示词 + 平面文件格式规范 + 整理/分批规则 + 输出格式 + 自检清单与冲突处理。取代原 knowledge-organizer-prompt.md |

## 约定

- 新增模板：命名 kebab-case、头部含「用途 / 目标读者 / 关联文档」三要素、在本表登记一行
- 模板内容若有规范性约束（如导入格式），须先更新对应 `conventions/` 文档，再同步模板，避免双源漂移
