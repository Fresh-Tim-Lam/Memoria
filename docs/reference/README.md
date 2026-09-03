# Reference（参考说明）

> **用途**：`reference/` 存放**参考说明（understand）**——系统架构、术语、硬约束、功能机制的说明，供理解与调试时查阅。命名 kebab-case 小写。
> **目标读者**：维护者 / AI Agent（理解系统、排查问题前先查对应参考）。
> **关联文档**：[docs-management.md](../conventions/docs-management.md)（docs 组织规则）；[logging.md](../conventions/logging.md)（日志规范）。

---

## 参考清单

| 文档 | 内容 |
|------|------|
| [architecture.md](./architecture.md) | 系统架构总览（双壳/静态服务器/前端模块/数据流） |
| [glossary.md](./glossary.md) | 术语表（KP/sidecar/manifest/contain 边/虚链等） |
| [hard-constraints.md](./hard-constraints.md) | 硬约束（不可违反的既定事实） |
| [image-features.md](./image-features.md) | 图片功能说明与内部机制（渲染链路/路径解析/交互/静态服务） |
| [preview-formats.md](./preview-formats.md) | 预览渲染说明：支持的格式与样式（块级/行内/扩展语法/样式/交互/边界） |
