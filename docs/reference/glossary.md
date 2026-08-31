# 术语表（Glossary）

> **用途**：Memoria 核心术语的权威解释——数据模型、存储、前端、图谱、检索。维护者与 AI Agent 遇到不认识的词先查本表。
> **目标读者**：维护者 / AI Agent / 新加入项目者。
> **关联文档**：[architecture.md](./architecture.md)（架构）；[hard-constraints.md](./hard-constraints.md)（硬约束）；[designV0.md](../design/designV0.md)（设计沿革）。

---

## 数据模型

| 术语 | 全称/英文 | 定义 |
|------|-----------|------|
| **KP** | Knowledge Point（知识点） | 知识的最小单元，以概念/知识点为单位组织；文件只是容器，可含多个 KP |
| **KB** | Knowledge Base（知识库） | 一个文档树根目录，含 `.memoria/` 元数据；应用打开的最小工作单元 |
| **Range** | — | KP 的正文定位区间：`start/end` 各含 `snippet`（锚文本）+ 可选 `line_hint`（行号提示），双端定位 |
| **Snippet** | — | Range 定位锚：唯一文本片段，用于在文档中定位行号 |
| **Line hint** | — | 定位的行号辅助提示（定位失败时的候选排序依据） |
| **Frontmatter** | — | md 文件顶部 `---` 元数据区；多目标链接路由表存于此，与正文 `[[]]` 语法分离 |
| **Edge** | 边 | KP 间语义关系（含链接派生与纯边两种来源） |
| **Contain 边** | EDGE_CONTAIN | 父子包含关系，由**同一文件内**的标题层级生成（`no_build: true` 可抑制） |
| **Reference 边** | EDGE_REFERENCE | 引用关系（含遗留 `#prerequisite` 等别名迁移） |
| **Extend 边** | EDGE_EXTEND | 扩展/延伸关系 |
| **虚链** | Virtual link | `[[unknown-id]]` 指向不存在的 KP——保持悬空，**不**自动创建空文件 |

## 存储

| 术语 | 定义 |
|------|------|
| **Sidecar** | 与正文同级的元数据文件 `<name>.memoria.yaml`（`schema_version: 1`），定义该文件的 knowledge_points（id/name/range/links/edges） |
| **Manifest** | `.memoria/manifest.yaml`，KB 级清单（KP 注册表） |
| **Pending** | `.memoria/pending.yaml`，待建/待处理项队列 |
| **`.memoria/`** | 隐藏元数据目录：sidecars/、manifest、pending、images/、cache/；文件树与文档扫描均不可见 |
| **原子写入** | `atomic_yaml.py`：先写 `.bak` 再替换，崩溃不损坏元数据 |
| **SKIP_DIR_NAMES** | 扫描跳过的目录名：`.memoria/.git/.build/__pycache__/node_modules` |

## 语法与编辑

| 术语 | 定义 |
|------|------|
| **`[[]]` 语法** | Memoria 统一语法体系：`[[kp-id]]` 链接、`[[id|text]]` 自定义显示文本、`[[id#type]]` 边类型、`\` 前缀系统命令 |
| **不可编辑块** | 公式/代码/表格/图片/Mermaid/SVG 等原子块（`contenteditable=false`），光标移动整体跳过 |
| **图片属性** | `![alt](url "width=300,align=center,name=show,name-size=16")`——title 内 `key=value` 逗号分段，白名单应用 |
| **Harness** | 浏览器复现测试台：`docs/example/rich-content-test/_harness.py`（bottle 服务真实前端 + M0API over /rpc + 注入 pywebview 桥） |
| **M0API** | 前后端 RPC 契约（`presentation/api/ui.py`），前端经 `/rpc` 调用 |

## 前端与图谱

| 术语 | 定义 |
|------|------|
| **AST** | `parser.js` 把源码编译为 AST（ast.js 定义节点），`renderer.js` 渲染为 DOM |
| **光标映射** | `mapper.js`：源码 ↔ 预览双向定位（块级 `data-m0-src-line` 行号锚） |
| **Lightbox** | 图片双击放大的全屏 overlay |
| **CTX-KEY** | 上下文关键句防火墙：项目文件内嵌隐式标记，Agent 回答开头自证已读取（见 conventions/context-key.md） |
| **Bridge** | 前端桥：`bridge.js` 封装 `/rpc`；pyqt6 用 qwebchannel，pywebview 用 js_api |

## 构建与运行态

| 术语 | 定义 |
|------|------|
| **MEMORIA_SHELL** | 壳选择环境变量：`pywebview`（默认）/`pyqt6` |
| **MEMORIA_MODE** | 运行模式：`dev`（开发态，DevTools 开）/ `release` |
| **Package/** | 可分发发布目录：`Memoria.exe` + lib/ + VERSION + manifest.json，由 `packaging/build_release.cmd` 构建 |
| **双壳** | pywebview（默认）+ pyqt6（备选）两套桌面壳实现 |
