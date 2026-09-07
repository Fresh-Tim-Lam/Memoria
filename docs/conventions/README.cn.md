[English](README.md) | 中文

# Conventions（契约性规范）

> **用途**：`conventions/` 存放**契约性规范**——人机都必须遵守的规则（语法、格式、目录、版本、日志、文档管理、元规范）。命名 kebab-case 小写。
> **目标读者**：项目负责人（用户）与 AI Agent（创建/修改代码或文档前先查对应规范）。
> **关联文档**：[meta-rules.md](./meta-rules.md)（规范书写元规则）；[docs-management.md](./docs-management.md)（docs 组织规则）。

---

## 规范清单

| 规范 | 内容 | 谁要遵守 |
|------|------|---------|
| [meta-rules.md](./meta-rules.md) | 如何讨论/制定规范的元规则 | 所有规范制定者 |
| [docs-management.md](./docs-management.md) | docs/ 组织规则（子目录职责、登记、生命周期） | 任何人（含 AI Agent） |
| [directory-organization.md](./directory-organization.md) | 仓库顶层目录职责与临时文件归置 | 任何人（含 AI Agent） |
| [version.md](./version.md) | 版本号格式、唯一事实源、升级流程 | 涉及版本变更/打包者 |
| [markdown-form-std.md](./markdown-form-std.md) | 统一 `[[]]` 语法体系（含图片节点属性） | 知识库内容生产者 |
| [import-format.md](./import-format.md) | 知识库平面文件导入格式 | 内容生成 Agent（角色 A） |
| [context-key.md](./context-key.md) | CTX-KEY 上下文防火墙机制 | 项目负责人与 AI Agent |
| [logging.md](./logging.md) | 日志存放/命名/格式/生命周期 | 添加或排查日志者 |
| [refs-system.md](./refs-system.md) | 参考资料库（refs/）使用规范 | 引用技术资料者 |
| [i18n.md](./i18n.md) | 语言系统维护规范（文案抽键/语言包结构与回退/新 UI 接入/清单维护） | 新增或修改界面文案者 |
| [readme-i18n.md](./readme-i18n.md) | README 与项目截图的中英双语维护规范（README.md ↔ README.cn.md 同步、截图收录/存放、自查） | 维护 README 或新增/更换演示截图者 |

> **决策流程**：内容属于"人机都要遵守的规则" → 放本目录；属于操作指引（how-to）→ `guides/`；属于参考说明（understand）→ `reference/`。详见 [docs-management.md](./docs-management.md)。
