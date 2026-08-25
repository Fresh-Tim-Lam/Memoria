# Standards（项目规范）

> **用途**：`docs/standards/` 的目录索引——列出全部规范文档及其职责，供人机快速定位"规则在哪"。
> **目标读者**：项目负责人（用户）与 AI Agent。
> **关联文档**：[docs-management.md](./docs-management.md)（docs 组织规则，含目录登记表）；[AAA 讨论元规范](./AAA_讨论元规范.md)（规范书写的元规则）。

---

## 规范清单

| 文件 | 内容 | 状态 |
|------|------|------|
| [AAA_讨论元规范.md](AAA_讨论元规范.md) | 元规则：如何讨论与制定规范（即时落盘/结论必标记/规则依附场景/首行释用途） | 生效 |
| [AI 编程协作规范.md](AI%20编程协作规范.md) | 五大开发场景协作规则（架构讨论/模块开发/测试/Bug 修复/重构） | 生效 v0.1 |
| [上下文规范.md](上下文规范.md) | CTX-KEY 防火墙机制（验证 Agent 上下文加载完整性） | 生效 v0.1 |
| [参考资料系统.md](参考资料系统.md) | 参考资料库（refs/）使用规范（引用标注、CTX-KEY 散布） | 生效 v0.1 |
| [version.md](version.md) | 版本规范与使用说明（单一事实源、一致性约束、升级流程、变更记录） | 生效 |
| [directory-organization.md](directory-organization.md) | 目录组织规范（各目录职责、临时文件必须放 artifacts/） | 生效 |
| [docs-management.md](docs-management.md) | docs 组织管理规范（子目录职责、自维护机制、目录登记表） | 生效 |
| [logging.md](logging.md) | 日志规范（存放位置、命名、格式约定、生命周期） | 生效 |
| [markdown-form-std.md](markdown-form-std.md) | Memoria 统一 `[[]]` 语法体系规范 | 生效 |
| [import-format.md](import-format.md) | 平面导入文件格式规范（导入引擎接受的 .txt 格式） | 生效 |

## 书写约定（遵循 AAA 元规范）

- 每份规范前 1-3 行必须含：**用途 / 目标读者 / 关联文档** 三要素
- 规范修订必须登记到 [docs-management.md 规范修订记录](./docs-management.md#42-规范修订记录)
- 新增规范文档后必须在本表登记一行
