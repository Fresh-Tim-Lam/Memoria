# resources/ — 应用资源

> **用途**：存放随应用仓库分发的**非代码静态资源**（应用图标、演示截图等），供应用运行时、打包脚本与 GitHub 展示引用；截图同时承担仓库 README（中/英）的配图职责。
> **目标读者**：维护图标的开发者；维护/新增项目演示截图者（README 配图）；打包脚本维护者。
> **关联文档**：[docs/conventions/readme-i18n.md](../docs/conventions/readme-i18n.md)（README 与截图中英描述维护规范）；[docs/conventions/docs-management.md](../docs/conventions/docs-management.md)（docs 组织规则）；[docs/conventions/directory-organization.md](../docs/conventions/directory-organization.md)（顶层目录职责）。

## 内容

| 路径 | 用途 |
|------|------|
| `icons/` | 应用图标（`Memoria.ico` / `Memoria-big.ico` / `Memoria.png`），用于窗口、任务栏与打包产物 |
| `screenshots/` | 项目演示截图（`demo-*.png`），README（中/英）配图；由打包脚本**不纳入**发布包 |

## 目录变更约定

- `docs/` 下**不得**存放图片资源（docs 只放文档，截图等二进制资源一律落 `resources/screenshots/`）；发现 `docs/` 出现截图类二进制文件时应迁至本目录并同步引用。
- 新增/删除/重命名截图后，必须同步：README.md + README.cn.md 引用、本表说明、仓库文档登记（docs-management.md 修订记录）。
