# AGENT.md — Memoria 项目接入指南

> 本文件是 AI Agent（及新维护者）进入本项目的第一站：快速建立角色认知、掌握技术栈、获取常用命令、理解架构、遵守规范、明确边界。
> 详细规则不在此重复，一律指向 `docs/` 对应文档（单一事实源）。

## 1. Role（角色）

**Memoria** 是一个本地知识图谱 IDE：离线检索内核 + snippet range 导航 + 双向链接（`[[]]`）知识库管理与富文本编辑器。全本地运行，无云端依赖。

Agent 在此项目的职责：按 [collaboration.md](docs/guides/collaboration.md) 与用户协作完成架构讨论、模块开发、测试、Debug、代码审查；任何改动遵守 `docs/conventions/` 下契约性规范。

## 2. TechStack（技术栈）

| 层 | 技术 | 说明 |
|----|------|------|
| 语言 | Python ≥ 3.11 | src layout，`pyproject.toml` 管理 |
| 桌面壳 | **pywebview**（默认）+ pyqt6（备选） | `MEMORIA_SHELL` 环境变量选择；pyqt6 用于自定义无边框窗口（window-chrome.js + window_win32.py） |
| Web 服务 | bottle | 静态资源 + `/files/` 知识库文件路由（防目录穿越）+ `/rpc` API 桥 |
| 前端 | 原生 JS 无框架 | app.js / parser.js / renderer.js / ast.js / edit-handler.js / markdown-preview.js / source-gen.js / graph-*.js；lib: marked / MathJax / mermaid / three.js |
| 存储 | 文件系统 + YAML | sidecar（`.memoria.yaml`）+ manifest.yaml + pending.yaml + `.memoria/` 隐藏元数据目录 |
| 依赖 | PyYAML / jieba / bottle / pywebview | 可选：sentence-transformers（语义检索）、pypinyin（搜索） |
| 打包 | PyInstaller | 唯一入口 `packaging\build_release.cmd` → `Package/` |

## 3. Commands（常用命令）

| 命令 | 用途 |
|------|------|
| `pip install -e ".[dev]"` | 开发安装（含 pytest） |
| `.\scripts\run_dev.ps1` | 开发态启动：源码 + pywebview 壳 + DevTools + 无边框（`MEMORIA_MODE=dev`） |
| `python app.py` | 直接源码运行 |
| `pytest` | 单元测试（`tests/`） |
| `.\packaging\build_release.cmd` | 构建发布包（`--no-clean` 增量） |
| `.\packaging\run_release.cmd` | 运行 `Package\Memoria.exe`（发布态） |
| `memoria` / `memoria-desktop` | 安装后的 console 入口（cli / desktop） |

**版本变更**：版本唯一事实源是 [src/memoria/\_\_version\_\_.py](src/memoria/__version__.py)，pyproject 通过 dynamic attr 读取，构建自动跟随。**禁止**手改 pyproject.toml 中的硬编码版本号。详见 [version.md](docs/conventions/version.md)。

## 4. Architecture（架构）

```
app.py → app/desktop.py（DPI/UTF-8 兜底）→ app/shell/（壳选择：pywebview | pyqt6）
        → presentation/static_server.py（bottle：静态资源 + /files/ + /rpc）
        → ui/static/app/（前端：编辑/预览/图谱/搜索）
```

**顶层目录导航**：每个一级目录顶部都有 `README.md` 说明职责——进入任何目录前先读其 README：

| 目录 | 职责 | README |
|------|------|--------|
| `src/` | 源码（Python 包 + 前端静态资源） | [src/README.md](src/README.md) |
| `tests/` | pytest 单元/集成测试 | [tests/README.md](tests/README.md) |
| `docs/` | 文档中心（规范/设计/指南/示例） | [docs/README.md](docs/README.md) |
| `scripts/` | 开发者工具（启动/基准） | [scripts/README.md](scripts/README.md) |
| `packaging/` | 打包发布（唯一入口 `build_release.cmd`） | [packaging/README.md](packaging/README.md) |
| `resources/` | 应用资源（图标） | [resources/README.md](resources/README.md) |
| `benchmarks/` | 检索评估数据与结果 | [benchmarks/README.md](benchmarks/README.md) |
| `config/` | 程序配置（`ui-settings.json`） | [config/README.md](config/README.md) |
| `artifacts/` | 临时产物区（已 gitignore） | [artifacts/README.md](artifacts/README.md) |
| `Package/` | 构建发布产物（gitignore，勿手改） | Package/README.txt |

| 模块 | 职责 |
|------|------|
| `domain/` + `range/` | 领域类型（Range、KP）与 snippet 定位算法 |
| `storage/` | 侧车 YAML、manifest、Markdown 解析、目录扫描、原子写入 |
| `services/` | 应用服务：文档加载、KP 解析/索引、检索内核（lexical/embedding/rerank 融合）、导入引擎 |
| `presentation/` | pywebview API 桥接（`api/`）、路径解析、静态服务器 |
| `app/` | 桌面启动入口、壳、运行时、构建 |
| `ui/static/app/` | 前端：AST 编译（parser→renderer）、编辑交互（edit-handler）、预览同步、图谱引擎（graph-*.js） |

**前端数据流**：`source → parser.js（AST）→ renderer.js（DOM）→ preview`；编辑经 `edit-handler.js` 回写源码并重编译；`bridge.js` 桥接后端 `/rpc`。

详见 [reference/architecture.md](docs/reference/architecture.md)、[design/system-design.md](docs/design/system-design.md)。

## 5. Conventions（规范）

所有契约性规范在 `docs/conventions/`，**改动代码/文档/版本/日志前先读对应规范**：

| 规范 | 何时必读 |
|------|---------|
| [version.md](docs/conventions/version.md) | 改版本号、打包 |
| [directory-organization.md](docs/conventions/directory-organization.md) | 创建/移动任何文件 |
| [docs-management.md](docs/conventions/docs-management.md) | 改 docs/、新增子目录/文档 |
| [markdown-form-std.md](docs/conventions/markdown-form-std.md) | 处理 `[[]]` 语法、图片节点属性 |
| [import-format.md](docs/conventions/import-format.md) | 知识库平面文件导入格式 |
| [logging.md](docs/conventions/logging.md) | 加日志、排查问题 |
| [context-key.md](docs/conventions/context-key.md) | CTX-KEY 上下文防火墙 |
| [refs-system.md](docs/conventions/refs-system.md) | 引用外部资料 |
| [meta-rules.md](docs/conventions/meta-rules.md) | 制定/修改任何规范 |

操作指引见 [guides/](docs/guides/README.md)（协作方式、知识库生产流水线、开发/发布操作）。

## 6. Boundaries（边界）

### Always（必须做）
- 文档新增/移动/删除后**同步索引**（父目录 README 或 docs-management 登记表）。
- 涉及版本变更先读 [version.md](docs/conventions/version.md)，只在 `__version__.py` 改。
- 新日志遵守 [logging.md](docs/conventions/logging.md) 的存放/命名/格式。
- 中文内容统一 UTF-8；前端改动保持原生 JS 无框架风格。
- 修改交互逻辑后跑通 [operations.md](docs/guides/operations.md) 中的验证方式（如 harness）。
- **生成物自动维护，不等用户提示**：`.gitignore` 忽略的目录（`*.egg-info/`、`build/`、`logs/`、`artifacts/`、`Package/*`、`__pycache__/`、`.cache/`、`.vendor-cache/` 等）均为**可再生物**，不是源码——发现过期（如 `src/memoria.egg-info/` 的 SOURCES.txt 未跟随源码、或 pyproject 依赖/入口变更后未刷新）时，主动执行 `pip install -e ".[dev]"` 重新生成；**不手动编辑、不提交任何生成物**。
- **任务收尾执行文件组织自检，不等用户提示**：本轮操作产生的文件是否落在正确目录（临时/调试→`artifacts/`，可复用工具→`scripts/`，打包→`packaging/`，文档→`docs/` 对应子目录，正式代码→`src/`）；根目录是否出现违规产物（`cdp-*.mjs`、`test-*.html`、`diag-*.json`、`shot-*.png`、`dbg/` 等兜底模式）→ 移入 `artifacts/`；目录/文档变更后父目录 README 与 docs-management 登记表是否同步；若发现 git 历史误跟踪的缓存/垃圾（如 `.cache/`、`cmake-build-debug/`、`Package.zip`）→ 主动向用户提出 `git rm` 解除跟踪（执行前仍须用户确认）。

### Ask First（先问用户）

> **区分"日常归位"与"结构性变更"**：临时文件归位、清理可再生缓存、同步文档索引、刷新生成物属 **Always**（主动做，不必问）；下述**结构性变更**必须先问：
- 结构性重构、删除/移动**正式文件**、改变目录组织。
- 打包/发布流程、新增第三方依赖、改动构建配置。
- 修改 `docs/example/` 下演示知识库或测试数据的内容。
- 改动会影响 `.memoria/` 元数据（sidecar/manifest/pending）一致性的逻辑。

### Never（禁止）
- **不直接编辑 `Package/` 发布产物**——任何产物改动都从源码经 `build_release.cmd` 构建。
- **不手改 pyproject.toml 版本号**——版本只出自 `__version__.py`。
- **不覆盖用户知识库原始文件**——保留 `.bak` 机制，破坏 `.memoria/` 元数据一致性。
- **不提交 secrets/凭据**。
- **不擅自 push/强推**，不经用户确认不执行破坏性 git 操作。

## 7. Common Pitfalls（常见陷阱）

- **Windows 编码**：frozen/windowed 下 stdout/stderr 为 cp1252，直接 print 中文会崩溃——desktop.py 已用 `_SafeStream` 兜底，勿绕过。
- **DPI**：任何窗口创建前必须抬升 DPI 感知（desktop.py 已处理），否则系统对话框在高缩放下满屏。
- **前端预览缓存**：修改渲染逻辑后若预览不更新，检查 `preview_body` 缓存清理。
- **事件派发**：前端全局事件用 `document` 派发（`window` 在壳内不可靠）。
- **图片/富文本编辑**：图片块单击编辑 / 双击放大，属性写回经 `memoria:image-attr`（document 派发）→ 源码合并 → 重进编辑；改前读 [image-features.md](docs/reference/image-features.md)。
- **git mv**：重命名文件用 `git mv` 保留历史（本次 docs 重构已用）。
- **`src/memoria.egg-info/` 过期不是故障**：它是 `pip install -e` 生成的元数据缓存（已被 gitignore，不入库），`SOURCES.txt` 不会自动跟随源码变化——新增/删除模块后显示旧内容属**正常现象**，不要手动编辑它，也不要据此误判源码丢失；需要刷新时重跑 `pip install -e ".[dev]"` 即可再生。

## 8. References（参考）

- [docs/README.md](docs/README.md) — 文档中心总索引（先读）
- [reference/architecture.md](docs/reference/architecture.md) — 系统架构总览
- [reference/glossary.md](docs/reference/glossary.md) — 术语表（KP/sidecar/manifest/contain 边/虚链）
- [reference/hard-constraints.md](docs/reference/hard-constraints.md) — 硬约束
- [reference/image-features.md](docs/reference/image-features.md) — 图片功能机制
- [design/system-design.md](docs/design/system-design.md) — 设计文档
- [guides/operations.md](docs/guides/operations.md) — 开发/发布/验证操作手册
- [docs/to-dolist.md](docs/to-dolist.md) — 活跃待办清单
