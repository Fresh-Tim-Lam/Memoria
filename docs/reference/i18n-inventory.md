# UI 界面文案清单（i18n Inventory）

> **用途**：登记桌面应用**前端界面**全部含中文的用户可见文案与定位（文件+行号），作为 i18n 迁移（抽键→语言包）与后续新增 UI 自查的依据。
> **目标读者**：项目负责人 / AI Agent（迁移文案、新增 UI、审阅语言包前必查）。
> **关联文档**：[i18n.md](../conventions/i18n.md)（语言系统维护规范）；[docs-management.md](../conventions/docs-management.md)（docs 组织规则）。
> **范围/边界**：仅统计 `src/memoria/ui/static/app/` 下 index.html、app/js/*.js、app/css 的 `content:` 文案；**不含** lib/vendor/mathjax 第三方库、纯注释文件（lexer/parser/ast 等中文均为注释，不属界面文案）；后端 Python 返回给界面的消息（document.py/import_engine.py/ui.py 等）为另一分区，机制落地后另行登记。
> **剔除规则**：开发日志 `console.*`/`syncLog` 等（i18n.md §2 非界面文案）；HTML 中已挂 `data-i18n`/`data-i18n-attr` 的静态节点（行内含标记即视为已迁移，中文仅为默认值/占位）。
> **生成**：`python scripts/scan_ui_strings.py`（确定性输出，可重复执行覆盖本文）。状态口径：`☐ 未迁移` 表示仍硬编码中文；迁移为 `t('key')` 后人工将对应文件状态置 `✔ 已迁移`（脚本重跑会重置，可在本文末尾「迁移记录」人工维护）。
> 生成日期：2026-09-05

## 统计总览

| 文件 | 含中文候选行数 | 状态 |
|------|------|------|
| **合计** | **0** | — |

## 逐文件清单

## 迁移记录

| 日期 | 文件/区域 | 动作 | 结果 |
|------|------|------|------|
|（初始生成）| 全部 | 盘点登记 | — |

