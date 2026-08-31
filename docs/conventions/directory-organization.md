# 目录组织规范

> **用途**：定义仓库顶层目录职责与临时文件归置规则，使任何文件（含 AI 产物）无需询问即可唯一落位。
> **目标读者**：项目负责人（用户）与 AI Agent（创建/移动文件时必须遵守）。
> **关联文档**：[meta-rules.md](./meta-rules.md)（规范书写元规则）；[docs-management.md](./docs-management.md)（docs 组织规则）。

## 1. 顶层目录职责总表

| 路径 | 职责 | 可否放临时文件 |
|------|------|:---:|
| `src/` | 源码（Python + UI 静态资源） | ❌ |
| `tests/` | 单元/集成测试 | ❌ |
| `docs/` | 文档（规范/设计/交接/示例知识库） | ⚠️ 仅 `docs/tmp/` |
| `scripts/` | **正式可复用**的开发者工具（启动/基准/数据生成） | ❌ |
| `packaging/` | 打包发布脚本与配置（唯一入口 `build_release.cmd`） | ❌ |
| `artifacts/` | **临时产物/垃圾区**（已被 gitignore） | ✅ 唯一指定处 |
| `resources/` | 应用图标等资源 | ❌ |
| `benchmarks/` | 检索评估数据与结果 | ❌ |
| `_archive/` | 历史版本/废弃代码归档 | ❌ |
| `Package/` | 构建发布产物（`Memoria.exe` + `lib/`） | ❌（构建生成，gitignore） |
| `.venv/` | 虚拟环境 | ❌ |
| 仓库根目录 | 仅允许：`README.md`、`LICENSE`、`pyproject.toml`、`requirements.txt`、`app.py`、`.gitignore`、`.gitattributes` 等**顶层配置** | ❌ |

## 2. 临时文件规则（本规范最重要的一条）

**所有临时/一次性文件必须放入 `artifacts/`（已被 .gitignore 忽略）。**

判定标准——符合以下任一即视为临时文件，放 `artifacts/`：
- 名字带 `tmp`、`test`、`debug`、`diag`、`repro`、`_` 前缀，且不是正式测试/正式脚本
- 一次性调试脚本（如 CDP/浏览器诊断 `.mjs`）、截图、运行日志、诊断输出
- 还在探索期、可能丢弃的验证代码

**禁止出现的位置**：仓库根目录、`src/`、`scripts/`、`packaging/`、`docs/`（`docs/tmp/` 仅放少量诊断记录 md）。

### 兜底机制
`.gitignore` 已加入根级临时产物模式（`/cdp-*.mjs`、`/test-*.html`、`/diag-*.json`、`/shot-*.png` 等）。一旦根目录出现此类文件，`git status` 不会显示——但应主动移入 `artifacts/`，不要依赖忽略规则掩盖问题。

## 3. 目录职责细节

### docs/ 子目录
| 目录 | 职责 |
|------|------|
| `docs/conventions/` | 契约性规范（版本、语法、导入格式、目录组织、日志、docs 管理）——人机都要遵守 |
| `docs/guides/` | 操作指引（how-to：流水线、协作、开发/发布操作） |
| `docs/reference/` | 参考说明（架构、术语、硬约束、功能机制） |
| `docs/sessions/` | 历史对话记录（承接上下文，原 agents/ 迁移而来） |
| `docs/design/` | 设计文档与决策记录 |
| `docs/example/` | 示例知识库（含 rich-content-test 测试环境） |
| `docs/refs/` | 开发参考资料 |
| `docs/prompts/` | 提示词模板 |
| `docs/tmp/` | 少量诊断/调试记录 |

### scripts/ vs packaging/（此前已划分）
- `scripts/` = 开发者工具（`run_dev.ps1`、benchmark、示例数据生成）——**不放临时脚本**
- `packaging/` = 打包发布的一切（`build_release.cmd`、`build.py`、`memoria.spec` 等）

## 4. 创建文件时的决策流程

```
需要新建文件？
├─ 临时/一次性/调试 → artifacts/
├─ 正式源码         → src/
├─ 正式测试         → tests/
├─ 可复用工具脚本   → scripts/
├─ 打包相关         → packaging/
├─ 规范/设计/交接文档 → docs/（按子目录职责）
└─ 其他             → 先问：这个文件属于哪个目录的职责？
```

## 5. 已执行的清理（2026-08-20）

根目录历史污染已清理：`.edge-tmp/`（Edge profile）删除；CDP 调试脚本/诊断 JSON/截图/一次性测试文件移入 `artifacts/`（`cdp-diag/`、`dev-tests/`）；`debug-preview-canvas-lost.md` 移入 `docs/tmp/`。根目录现仅保留顶层配置文件。
