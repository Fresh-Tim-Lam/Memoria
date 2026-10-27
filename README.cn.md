<img src="resources/icons/Memoria.png" alt="Memoria 图标" width="96"/>

# Memoria — 以**知识点**为原子的本地知识 IDE

> **把 Markdown 笔记变成一张可跳转、可复习、可让 AI Agent 与你共同维护的知识网络 —— 全部在你自己的磁盘上。**

> English readers: see [README.md](README.md)。

[![Version](https://img.shields.io/badge/Version-0.4.9-8A2BE2)](src/memoria/__version__.py)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11%20x64-blue)](https://github.com/)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-1600%2B%20passing-brightgreen)](https://github.com/)
[![English](https://img.shields.io/badge/README-English-green)](README.md)

**Memoria** 不是"又一个 Markdown 笔记软件"。它以**知识点（Knowledge Points）**而不是整篇文档为知识单位：
链接定位到**精确的片段范围**；**2D/3D 图谱按"索引"设计**（设计理念，见下）；**内置 FSRS 间隔复习**；
一个**应用内 AI Agent** 可以在**单一写路径**（写前备份、可审计、可撤销、按会话设审批档位）下读写知识库。

所有数据都是磁盘上的普通文件：Markdown 正文 + YAML 侧车。没有账号、没有云同步、没有上传遥测。

<img src="resources/screenshots/demo-workspace.png" alt="Memoria 工作区：2D 知识图谱、知识点列表与文档编辑区" width="820"/>

---

## 为什么用 Memoria？

| 传统笔记应用 | Memoria |
|---|---|
| 用文件夹组织一篇篇文档 | 以**知识点**为单位、按**精确片段范围**互相链接，支持前进 / 后退导航 |
| 图谱只是装饰 | 图谱**按"索引"设计** —— 经过本体辩论（13 条裁决）+ **冻结**的可视化设计（见[设计理念](#图谱是索引不是装饰)） |
| 复习只能重读 | **内置 FSRS** 调度：到期队列、1–4 评分、每卡状态（stability / difficulty / due）、追加式作答流水 |
| AI 在另一个应用/侧边栏里 | **应用内 Agent** 能读库、审计，并通过**单一写路径**写入 —— 写前备份、审计留痕、一步撤销，审批按会话分档（默认：常规写自动放行，删除/重命名问一次） |
| 性能靠形容词 | 用仓库自带基准**实测**并公开口径，连"没达标"的项也写出来 |

---

## 图谱是索引，不是装饰

这是 Memoria 区别于"好看的图"类笔记应用的设计理念。

- 我们先做了**知识图谱本体辩论**并冻结：**13 条裁决**，其中明确写下：**边当前服务于「人看的图」与「写质量诊断」，不服务于 agent 推理**
  （[kg-ontology-v0.md](docs/design/kg-ontology-v0.md) `L13` / `L20` / `L27` / `L28`）。
- 随后做了**可视化设计研讨会**并冻结：节点大小范围、不设档位（连续映射）、3D **不**用大小编码重要性、
  标签避让、布局稳定性承诺 —— 每条都有被否决的备选方案与可证伪条件，并包含**两轮人裁决**
  （[kg-visualization-v0.md](docs/design/kg-visualization-v0.md)）。
- **设计理念（design intent）**：图谱是 agent 框架所需要的那种稳定、带类型的**索引**。
  **Roadmap**：让图谱拓扑参与 **agent 检索** —— 但要先满足项目自己的裁决：
  **必须在实验里证明它能改变一个 agent 决策**
  （[kg-ontology-v0.md §6.2](docs/design/kg-ontology-v0.md)）。

> 换句话说：我们清楚自己走到哪一步。图谱按索引设计；它**目前尚不**参与 agent 检索。
> 这条边界是我们自己在写任何宣传之前就写下来的。

---

## 核心功能

### 知识点、snippet-range 链接、2D/3D 图谱

- `[[某个知识点]]` 把片段连成网络；点击跳到**精确的源码行区间**（不是整页），支持前进 / 后退。
- 2D 力导向图与 3D 空间图；点节点跳回原文；侧栏可重建图谱、按分组查看。
- 知识点元数据（名称、权重、标签）在 front-matter 或侧车中；知识点面板管理当前文件的点与链接。
- 全库完整性检查：悬空链接、缺失知识点、图谱建边问题 —— 并支持一键复制 Markdown 报告。

### 内置间隔复习（FSRS）

- 随包提供**确定性 FSRS 调度器**（`resources/agent-prompts/fsrs.py`）：`due` / `init` / `grade`，原子写、调度状态单一写者。
- 复习卡可绑定到**知识点与其来源文件**；复习面板显示到期队列并评分；答案在揭晓前对前端隐藏；作答追加到审计流水。
- Agent 可协助建卡、列到期、评分、写回反馈 —— **每个写工具都必须过审批**。

### AI 与笔记一体

- **读**：`read_document`（分页）、`kb_overview`、三级粒度读（`outline` / `section` / `snippet`）、`search_kb`、`validate_kb`。
- **写**：只有一条计划式写路径 —— 先算 dry-run diff，再按**会话审批档位**应用：
  `auto-approval`（**默认**：常规写自动放行，删除/重命名类问一次）、`manual-approval`（每次写都问）、
  `all-access`（不再询问）。**无论哪一档**，每次应用都先取写前快照、写审计事件、可一步撤销，越界/越限的写会被拒绝。
  不存在第二条写路径。
- **MCP**：内置最小 MCP 服务器，暴露 4 把工具（`outline` / `section` / `snippet` / `propose_write`，schema 544 tok），
  外部 MCP 客户端可读、可**提议**修改；MCP 写不沿用应用内档位，仍需审批。
- **MCP**：内置最小 MCP 服务器，暴露 4 把工具（`outline` / `section` / `snippet` / `propose_write`，schema 544 tok），
  外部 MCP 客户端可读、可**提议**修改；写仍需审批。
- **可扩展**：能力插件、用户技能与扩展点 —— 插件目录内不含可执行代码（声明式）。

### 富内容渲染（Markdown+）

- LaTeX 公式（MathJax：行内 `$...$`、块级 `$$...$$`）、Mermaid 图表、表格、代码块、引用。
- 可视化编辑：像 Word 一样涂抹荧光笔 / 字体颜色 / 加粗斜体，自动回写源码。
- 图片：本地相对路径 / 网络 URL / 一键复制入库（`.memoria/images`），支持 Lightbox、宽度与对齐。

### 界面双语、数据在手中

- 界面中 / 英双语，运行时可切换。
- 知识库就是一个普通文件夹：`.md` 正文 + `.memoria/`（侧车 YAML、manifest、缓存、图片）。放进 Git、NAS、网盘都能搬走。

---

## 30 秒上手

> 前置：桌面应用需 **Windows 10/11 x64**；开发需 Python ≥ 3.11。
> 桌面壳为 pywebview + WebView2（Windows 10 1803+ / Windows 11 已内置）。

```powershell
# 1) 安装（开发模式，含 pytest）
pip install -e ".[dev]"

# 2) 启动桌面应用
python app.py
# 或开发态（DevTools + 无边框窗口）
.\scripts\run_dev.ps1
```

打开后点「打开知识库」，选任意 Markdown 目录即可。想先体验，直接打开仓库内**官方展示样例库**
（机器学习导论；10 个内容页 / 36 个知识点，覆盖样式、图片、链接与搜索别名）：

```text
docs\example\showcase\
```

需要独立 exe？运行 `.\packaging\build_release.cmd`，产物在 `Package\Memoria.exe`（或使用已发布的
`Memoria-v*-win64.zip`）。请**整包解压**到可写目录，不要直接在 zip 里运行 `Memoria.exe`。若启动失败，
exe 同目录的 `crash.log` 有详细报错；若是 Windows 以「文件来自网络」为由拦截随包 .NET 运行时，
在解压目录执行 `Get-ChildItem -Recurse | Unblock-File` 后重试。

---

## 设计取舍（Memoria vs Obsidian）

两者都是本地优先的 Markdown 工具，只是优化目标不同。这里只讲取舍，不贬低对方 —— 方便你选对工具。

| | Memoria | Obsidian |
|---|---|---|
| 重心 | **知识点** + 内置学习闭环（复习调度） | **文件 + 庞大的插件生态**，功能靠社区插件生长 |
| 链接 | 知识点级、snippet-range；图谱设计经研讨会并冻结 | 块引用 + 图谱视图，可经插件扩展 |
| 间隔复习 | **内置**（FSRS、到期队列、评分） | 依赖社区插件 |
| AI | **内置 Agent**（单一写路径 + 写前备份/可撤销 + 按会话审批档位 + 最小 MCP 服务器） | 依赖社区插件 / 外部工具 |
| 平台（2026-10） | Windows 10/11 桌面 | Windows / macOS / Linux / 移动端 |

**适合用 Memoria**：你在 Windows 上、想要知识点级结构、内置复习闭环，以及一个能在**写前备份 + 可撤销 + 审计留痕**前提下维护同一批文件的 AI Agent。
**适合用 Obsidian**：你今天就需要移动端、庞大插件生态或跨平台同步。

### 不适合谁

- 今天就需要**移动端 / 平板**客户端；
- 需要**多用户 / 云同步服务**；
- 需要成百上千的第三方插件；
- 需要 macOS / Linux 桌面版（暂未发布）。

写这份"不适合"清单会让我们少一些下载；写假的清单会让你失去信任。

---

## 界面预览

工作区：左侧 2D 知识图谱与知识点列表，右侧文档编辑区。

<img src="resources/screenshots/demo-workspace.png" alt="Memoria 工作区：2D 知识图谱与文档编辑" width="820"/>

3D 知识图谱：滚轮缩放、拖拽旋转、点节点跳回原文。

<img src="resources/screenshots/demo-graph-3d.png" alt="Memoria 3D 知识图谱" width="820"/>

分栏模式：左侧源码、右侧实时渲染预览。

<img src="resources/screenshots/demo-split.png" alt="Memoria 分栏编辑：源码 + 实时预览" width="820"/>

渲染预览：表格、Wiki 链接、代码块混合排版。

<img src="resources/screenshots/demo-preview.png" alt="Memoria 富文本预览渲染" width="820"/>

数学公式：MathJax 渲染的 LaTeX 公式（行内 / 块级）。

<img src="resources/screenshots/demo-math.png" alt="Memoria LaTeX 数学公式渲染" width="820"/>

显示设置与完整性检查：字号 / 界面缩放可调；一键扫描知识库结构问题。

<img src="resources/screenshots/demo-settings.png" alt="Memoria 显示设置" width="820"/>

<img src="resources/screenshots/demo-check.png" alt="Memoria 知识库完整性检查" width="820"/>

知识库检查 + 可复制报告：面板汇总完整性、清单差异与图谱建边问题；点「复制报告」把 Markdown 报告写入剪贴板。

<img src="resources/screenshots/demo-check-report.png" alt="Memoria 知识库检查面板与「复制报告」提示" width="820"/>

---

## 实测性能（公开口径）

我们不用"丝滑/飞快"这类形容词；我们给数字，并给出产生数字的基准。

| 测量项 | 结果 | 测量版本 / 依据 |
|---|---|---|
| 5,000 节点 star 图，整帧 | **9108 ms → 41.5 ms**（约 212×，≈23 fps）；装载 **136 s → 0.35 s** | 实测于 **v0.3.4**；基线与结果见 [graph-benchmark.md](docs/design/graph-benchmark.md) 与原始产物 `scripts/benchmark/graph/results/` |
| 冷启动 | **15.4 s → 2.4 s（−84%）** | 实测于 **v0.4.6**；测量协议见 [benchmark-measurement-protocol.md](docs/design/benchmark-measurement-protocol.md) |

**如实说明**：以上是特定硬件上的**历史实测**，本次 README 改版**没有复跑**；基准文档里也记录了**未达标**的项。
如果你在意某个数字，请用仓库里的基准脚本复跑 —— 命令与原始产物都在仓库内。

---

## 数据、隐私与联网

- **没有账号、没有云同步、没有上传遥测。** 笔记就是文件，应用是本地桌面应用。
- **只有你启用或配置的功能才会联网**：你的 LLM 提供方、可选的联网搜索/抓取、可选的更新检查。
  设置里有**唯一一个出网开关** —— 关闭后应用**零请求**（代码里写明并有测试）。
- 更新检查只发标准 `GET` + `User-Agent`（外加 GitHub 要求的 `Accept`），**不携带任何本地数据**，自动检查可关闭。
- 发布包若带 `release-manifest.json`，只做**结构与完整性校验**（逐文件 sha256/bytes、zip 条目集合、路径穿越、尾随数据）。
  这是完整性检查，**不是数字签名** —— 我们不声称有签名。
- 本地交互计数（图谱风格 / 节点大小调整）只存于 `%LOCALAPPDATA%` 本地文件，绝不上传。

---

## 文档与 AI 协作

Memoria 的文档体系为人机协作设计：每个一级目录都有 README，契约性规范集中在 `docs/conventions/`。

- 接入指南（先读）：[AGENT.md](AGENT.md)
- 文档中心：[docs/README.md](docs/README.md)
- 架构说明：[docs/reference/architecture.md](docs/reference/architecture.md)、[docs/design/system-design.md](docs/design/system-design.md)
- 设计里程碑：[docs/design/designV0.md](docs/design/designV0.md)
- 版本号唯一事实源：[src/memoria/\_\_version\_\_.py](src/memoria/__version__.py)（当前 **0.4.9**）
- **本 README 的每条能力性断言都登记了证据**：[docs/marketing/claims.md](docs/marketing/claims.md)。
  如果你发现 README 里有一条没登记的断言，那是 bug —— 请提 issue。

---

## 技术架构

| 层 | 技术 | 说明 |
|---|---|---|
| 语言 | **Python ≥ 3.11** | `src` layout，`pyproject.toml` 管理 |
| 桌面壳 | **pywebview**（WebView2/Chromium），PyQt6 可选 | `MEMORIA_SHELL` 环境变量切换 |
| Web 服务 | **bottle** | 静态资源 + `/files/` 路由 + `/rpc` 桥 |
| 前端 | **原生 JS（零框架）** | `parser.js` → AST → 渲染器；编辑回写源码 |
| 渲染 | marked / **MathJax** / **mermaid** / **three.js** | Markdown、公式、图表、3D 图谱 |
| 存储 | 文件系统 + YAML | 侧车 `.memoria.yaml` + `.memoria/`（索引、图片、manifest） |
| 检索 | jieba 词法；可选 sentence-transformers / pypinyin | 语义检索为可选依赖 |
| 测试 | **pytest** —— `pytest -q tests` → **1,600+ passed**（此刻 1,624，2026-10-26） | 前端另跑 `node --check` 与 i18n 自检 |

---

## 路线图

- **图谱参与 agent 检索** —— 让 agent 的搜索/读取路径利用图谱拓扑；但按项目已冻结的裁决，
  **必须先在 A/B 中证明它能改变 agent 的决策**。
- **更强的语义检索** —— 更好的本地嵌入 / 重排，同时保持默认离线可用。
- **更多桌面平台** —— macOS / Linux 尚未发布。
- 以上都是计划而非承诺：已实现 / 设计理念 / Roadmap 的三分法见
  [claims.md §2](docs/marketing/claims.md)。

---

## License

[AGPL-3.0-only](LICENSE) © 2026 FreshTim

**本版本原始发布时为 MIT；许可已回填为 AGPL-3.0。v0.4.10 及更早版本的既有授权不受影响（MIT 不可撤回）。**
