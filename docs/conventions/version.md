# Memoria 版本规范

> **用途**：定义版本号格式、唯一事实源、一致性约束与升级流程，使源码、构建产物、UI 显示三处版本统一且可追踪。
> **目标读者**：项目负责人（用户）与 AI Agent（凡涉及版本变更或打包必读）。
> **关联文档**：[meta-rules.md](./meta-rules.md)（规范书写元规则）；[directory-organization.md](./directory-organization.md)（目录组织）。

## 1. 当前版本

| 项 | 值 |
|----|----|
| 当前版本 | **0.4.2** |
| 版本阶段 | 0.x（未稳定，接口可变更） |
| 版本类型 | SemVer：`MAJOR.MINOR.PATCH` |

## 2. 版本号格式与递增规则

格式：`MAJOR.MINOR.PATCH`（必要时 `-prerelease`）。

| 位 | 何时递增 | 示例 |
|----|---------|------|
| MAJOR | 破坏性重构（不兼容） | 1.0.0 → 2.0.0 |
| MINOR | 新增功能（兼容） | 0.2.0 → 0.3.0 |
| PATCH | Bug 修复（兼容） | 0.2.0 → 0.2.1 |

0.x 阶段约定：MINOR 可用于较大的功能里程碑（如本次 0.1.0 → 0.2.0 伴随窗口壳重构与整理）。

## 3. 唯一事实源（Single Source of Truth）

版本号**只定义在一处**：

```
src/memoria/__version__.py
    __version__ = "0.2.0"
```

升级版本 = 只改这一个文件。

## 4. 版本一致性约束

| 文件 | 要求 | 强制方式 |
|------|------|---------|
| `src/memoria/__version__.py` | 唯一事实源 | — |
| `pyproject.toml` `[project].dynamic = ["version"]` | 通过 `[tool.setuptools.dynamic] version = {attr = "memoria.__version__.__version__"}` 从 `__version__.py` **动态读取**，无需人工同步 | setuptools 打包时自动解析 |

> 早期版本曾硬编码 `pyproject.toml [project].version` 并由 `packaging/build.py` 校验一致性（不一致拒绝构建）。2026-08-29 起改为 dynamic version，**升级版本只需改 `__version__.py` 一处**。

手动校验（读取当前版本）：

```powershell
python -c "import sys; sys.path.insert(0,'packaging'); import build; print(build._read_version())"
```

## 5. 版本消费链路

### 运行时（UI 显示）

```
__version__.py
  ├─ UIAPI.get_window_chrome() → {version}
  │    └─ 前端 window-chrome.js：document.title / 欢迎页 h1 / 顶栏 badge（v0.2.0）
  └─ 壳窗口标题：pywebview.py / pyqt6.py（"Memoria v0.2.0"）
```

### 构建产物

```
__version__.py
  └─ packaging/build.py _read_version()
       ├─ Package/VERSION
       ├─ Package/manifest.json → "version"
       └─ Package/config/README.txt（{version} 模板替换）
```

### 安装元数据

```
__version__.py
  └─ pyproject.toml [project].dynamic + [tool.setuptools.dynamic] attr 读取
       └─ pip 安装 / 打包元数据（同一来源，天然一致）
```

## 6. 升级版本步骤

1. 修改 `src/memoria/__version__.py` 为 `"x.y.z"`（唯一一处）
2. 更新本文件「当前版本」与「变更记录」表
3. 构建发布：`packaging\build_release.cmd --no-clean`
4. 验证：
   - `Package\VERSION` 内容 = `x.y.z`
   - 启动发布包后顶栏 badge / 欢迎页 / 窗口标题显示 `vx.y.z`
5. 打 tag 与发布：tag 用 `vx.y.z`；GitHub Release 资产按 [operations.md §5.1](../guides/operations.md) 命名（`Memoria-vx.y.z-win64.zip` 完整包 + `Memoria-vx.y.z-win64-lite.zip` 轻量包，**两者同时上传**）

## 7. 变更记录（CHANGELOG）

> 约定：每次升级在此追加一行。格式：`版本号（日期）｜ 变更要点`。

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.4.2 | 2026-09-22 | **知识库 Agent「写面」打通（dsh 移植 M3）+ 权限 / 守卫 / 插件 + 交互与视觉收口**：① **写模块主链** —— `propose_write` 提议（工具面第一次能写）→ 计划确认卡（一份计划一张卡、状态原地推进、长文本悬浮看全）→ apply（编译器 + 原语白名单 + **整批回滚**）；配套**写前备份 / 撤销一步 / 重做一步**、**审计事件层**、**写冲突保护**（版本令牌 + 「以我为准」先备份再覆盖）。落盘一律走既有原语，不新造写实现。② **写能力覆盖** —— 文件级 `create_file` / `rename_file` / `move_file` / `delete_file`；正文级 `replace_lines` / `insert_lines` / `delete_lines`（**移出**风险表：判据是"不可逆"，而它有逐字 `expect` + 备份 + 整批撤销）、块级重建 `upsert_block`（代码块 / mermaid / 公式）、图片引用 `insert_image_ref`；sidecar 结构三件套 `upsert_edge` / `delete_kp` / `rename_kp`（全库级联）；库级 `rebuild_manifest`（等价界面「构建」，「清单陈旧」那类账 agent 自己就能收）。③ **两道闸** —— **读后写守卫**（语义移植上游 `fs/fs-observation-policy`：未读即写 `FS_NOT_OBSERVED`、读到过但当时不存在 `FS_NOT_FOUND`、版本变了 `FS_STALE_VERSION`；`create_file` 免读、写后刷新观察版本）与**审批档位**（手动 / 自动 / 完全访问 + **逐条确认卡** + `approval/asked`·`approval/decided` 审计事件；上游 `never` 改名 `allow-all` —— 同名反义易误判）。④ **能力插件声明面**（`services/agent/plugins.py`，守「插件目录内不含可执行代码」铁律；`kb.*` ↔ 落盘原语的**命名桥**单列一处）+ 技能面（`/name` 用户手势、只扫用户原文）。⑤ **读面**：`read_document` 可读**非 markdown 文本**（`.txt` / `.csv` / 源码；UTF-8 BOM 吃掉 + GB18030 回退；含 NUL 的二进制明确拒并指路 `read_image`），写面仍只认 `.md`。⑥ **交互 / 视觉** —— 思考改**按步多段**（与工具行天然交错；摘要行移出圆角气泡；气泡内可滚轮翻看；「展开」只**变高一点** 20rem）、**回合过程折叠**（对齐上游 compact 档 + 可按轮展开）、生成中**可上翻**（粘底语义，不再被每帧拽回底部）、回复底部「**用量 + 复制**」同一行、文件树图标两态**颜色轴**（已配置着主题色 / 未配置灰且浅）+ 缩进**折角紧贴图标**、空输入框 ↑/↓ 翻「发过的内容」、Ctrl+Enter 框内换行（修镜像层与光标错位）、每轮结束自动刷新工作区。⑦ **上游对齐**：移除「连续调用工具 8 轮上限」（上游明写**没有内置轮次预算**）。⑧ **修复** —— 写路径 `WinError 5` 全仓收口（写路径统一 `replace_with_retry`）、`move_file` 的 `to_dir` 口径（`""` / `.` / `./` = 库根；计划期与落地期收口到同一个 `normalize_target_dir()`）、`propose_write` 三条"读不出怎么改"的错误信息改成可照做、**字样式命令** `[[\h\|…]]` 不再被当 wikilink、`mapping-debug.log` / `undo-debug.log` 不再写进知识库根（改落 `.memoria/cache/**`）、设置「显示」页签滚不动、写路径全废（`body_edit.py` 缩进）与「分批写入断在半路」。`pytest -q` **1103 passed** |
| 0.4.1 | 2026-09-20 | **知识库 Agent 面板（dsh 移植 M1–M2 收尾 + 引用板块 + 跳转高亮修复）**：① **上游读面** —— `read_document` 分页续读（`offset`/`limit`，默认且上限 2000 行）+ 新增只读 `glob` / `grep` / `read_image`（校验层；缺多媒体「眼睛」插件即明确报 `UNSUPPORTED_IMAGE_INPUT`，不伪造成功），工具面由「知识库根」改为**工作区允许根列表**（`.memoria/**` 默认可见，为将来越出根目录留位）；② **会话查询五工具补全** —— `session_event_search` / `session_trace` / `session_event_trace` / `session_event_read`（只读、限本库、`session_id` 必填）；③ **引用板块** —— 只读 `resolve_reference` / `audit_references`（五类引用逐条回「指向什么 / 歧义候选 / 建议下一步」，不猜）。④ **引用机制** —— 选区引用带**源码位置**（`@路径#L3C2-L5C7`，预览区已到字符级）、会话片段引用（`@[标题](dsh-session:s1#seq:3c12-3c48)`，输入框用短别名、发送前展开成完整 URI）、对话内引用渲染成 chip 并标出「起 / 止」、打字框镜像层把 token 渲染成引用块（可拖文件树 / 拖顶栏页签入对话栏）。⑤ **跳转高亮** —— 块↔源码行映射收敛到 parser **单一事实源**（修「预览高亮位置错、行号偏小」：274 份 md 中 223 份存在错位的根因）、高亮带跟随 Mermaid/MathJax 布局、预览「源坐标」改**按需现算**（不写 DOM，编辑态与只读态同一路径）。⑥ **历史行右键菜单**（重命名 / 删除 + 悬浮提示），删除改应用内确认弹窗；新增 RPC `agent_session_rename`（**追加**一条 `session/title`，最新者胜，回放零改动）。⑦ 上游引用类收尾：时间上下文（`context/time-context`）与模型切换告知（`core/agent` `model-selection`）。⑧ **文档** —— 新增多 Agent 协作契约 [`AGENTS.md`](../../AGENTS.md)、能力插件与写模块总设计 [`agent-plugin-design.md`](../design/agent-plugin-design.md)（活文档）、发布与「连不上先试本地代理」运维规范。`pytest -q` **356 passed** |
| 0.4.0 | 2026-09-20 | **知识库 Agent 面板（dsh 移植 M1–M2）**：① **M1** —— 代码级移植 LLM 能力（纯标准库）+ Agent 主体只读竖切打通、多轮续聊与会话历史、真取消 / 恢复上次会话 / 删除会话；② **M2** —— `@路径` 上下文引用、跨会话引用（`context/session-reference`）、长会话自动压缩成 checkpoint、历史会话检索工具 `search_sessions`、会话标题（`session/title`）与免模型旧工具结果裁剪；③ **用量可视化** —— 状态栏余额槽 + 成本浮层（官方价目表 / 逐轮峰谷价）、每轮 token 用量行、状态栏刷新间隔可配。**UI 视觉收敛**：A/B 档 token 落地（圆角 4/6/8/12/999、描边 0.5px、三档阴影）、统一 `--bar-h` 栏高与 `--border-sep` 分隔线、滚动条变细并按需显形、状态 bar 四槽语义色、设置弹窗新增「对话」页签。**文件树 / 图标 / 流式渲染**：目录可折叠（记忆 + 重渲守卫）、借用 dsh 自有图标替换 emoji、文件树拖拽引用入对话栏、助手气泡渲染 Markdown（净化 + 锚点保留）+ 流式中间缓冲逐行渲染（AG11）。**打包分发修复**：P06 双击闪退根因 = Mark-of-the-Web（pythonnet / `Assembly.LoadFrom`），随包 `Memoria.exe.config`（`loadFromRemoteSources`）修复并重建 Release 资产（已在 0.3.4 行同名重构建登记）。**示例**：公开 IELTS 词汇库 `docs/example/AAA_Vocab/` 与上手 / 部署指引（`site/`） |
| 0.3.4 | 2026-09-16 | **图谱性能（G05 主体，目标档 5000 节点）**：① **D1 帧预算化** —— `sim-core.runTicksWithBudget`（2D/3D/worker 共用，默认 8ms、至少 1 tick），帧时间从此有上界（目标档整帧 p95 9252→710ms）；② **D2 Barnes-Hut 近似排斥**（新 `graph-bh-tree.js`，2D 四叉树 / 3D 八叉树，θ=0.9，分组语义与 `skipPairRepulsion` 严格对齐；`bh:false` 保留精确 O(N²) 路径供同 build A/B）；③ **X3 数值稳健**（`distanceMin` 距离下限取代 `Math.random()` 抖动 + 每 tick 位移上限 ⇒ 消掉边长 2.13e9 的数值爆炸，布局确定性可复现）；④ **X4 装载卡死根治**（warmup 工作量上限 + worker 就绪超时 3s→15s）。合计：5000 节点整帧 **9108ms → 41.5ms（212×，≈23fps）**、装载 **136s → 0.35s**。新增图谱性能基准 L1 采集器 `scripts/benchmark/graph/`（结构 / 分项剖面 / θ / 同 build A/B / 对照判定）与设计稿 [docs/design/graph-benchmark.md](../design/graph-benchmark.md) |
| 0.3.4 | 2026-09-16 | 图谱「分布模式」新增**「散落」**：孤立节点不再被固定在群组网格上，而是随机散落在圆盘/球内、只受"向原点中心力 + 节点间排斥"支配（连通群仍靠连边抱团、互相推开），避免节点多时聚成一个球；分布模式可持久化 |
| 0.3.4 | 2026-09-16 | 修复「构建」按钮**连点导致重复构建**（多条构建指令排队，表现为"构建完又构建"）：改为幂等 —— 在飞标志独立于按钮 `disabled`，重复请求直接忽略 |
| 0.3.4 | 2026-09-18 | **同名重新构建并替换 Release 资产（未改版本号）**：修复部分机器上「解压后双击即崩」。根因 = Mark-of-the-Web —— zip 解压出的文件被 Windows 写入 `Zone.Identifier`（ZoneId=3），.NET Framework 的 `Assembly.LoadFrom` 拒绝加载来源为「Internet 区域」的程序集（HRESULT `0x80131515`），pywebview 的 WinForms 后端正是这样加载随包 pythonnet 的 `Python.Runtime.dll`，失败后只报 `Failed to resolve Python.Runtime.Loader.Initialize`。**修法**：随包 `Memoria.exe.config`（`<loadFromRemoteSources enabled="true"/>`，.NET 官方开关；`packaging/templates/` 新增模板、`build.py` 拷贝并校验、两份 zip 清单同步加入），另在启动失败时弹可读提示（`packaging/app_release.py::_show_fatal_dialog()`）。**顺带**：两份 zip 不再打 `Package\config\`（避免把维护者本机的 `ui-settings.json` 发出去）。无数据格式变更，直接覆盖升级即可（详见 `docs/todo.md` §8 P06） |
| 0.3.3 | 2026-09-16 | **浅色主题**（深色/浅色/跟随系统，含知识图谱 2D/3D、代码块高亮、Mermaid 全套颜色 token）+ 顶栏灰底/底栏告警配色；**图标系统**：`scripts/icons/` 流水线（源图 → 多尺寸 ico + 运行时同步，命名约定与忽略规则见 docs/reference/icon-system.md）+ 手绘稿清理/配色对调工具 `recolor_icon.py`；代码块语法高亮（python/cpp/c/js/ts/json/bash，零依赖）；Mermaid 主题化（连线/节点/子图，走 themeVariables）+ 分栏模式滚动反弹修复；键盘选区与跨块删除修正（预览/源码双区 Shift 逐字符、Ctrl+Shift 按词、撤销后重锚、终点可落空行；跨块删除改用真实源码行表 `__blockLineMap`）；围栏代码块内 `=` 不再被误判为公式；侧栏宽度持久化（WebView2 私有模式不保留 localStorage，改落盘 `ui-settings.json`）；打包仅同步应用图标本体（草稿/备份/候选图不再进入发布包） |
| 0.3.2 | 2026-09-10 | 检查面板新增「复制报告」（结构化 Markdown 文本，便于粘贴给他人 / Agent 排查）；新增通用轻提示组件 `js/toast.js`（复制类反馈在弹窗内可见，落地 i18n 规范中已登记的 `toast.` 规划）；顶栏右侧拖拽区修正（知识库路径框底部空白不再触发文本选择 / 拖拽复制）；补发布资产命名规范（operations.md §5.1：完整包 `Memoria-v<版本>-win64.zip` + 轻量包 `-win64-lite.zip` 双形态） |
| 0.3.1 | 2026-09-10 | 维护机制迭代（G3–G5）：前端作业调度内核、持久化 flush 屏障、词法索引后台化、KP 行号范围实时同步、F01–F03 维护面收敛（含 CLI `diagnose-images`）。**知识库 Agent**：`.memoria/agent/` 工具包（智能体指令 + 编撰/维护规范 + 支持格式说明 + FSRS 确定性调度脚本），应用内「文件 → 创建 Trae 智能体」一键生成、打开知识库自动补写/刷新、规则可独立升级无需重建智能体。新增多 Agent 协作契约 `AGENTS.md`（builder/verifier/registrar + 可插拔扩展） |
| 0.3.0 | 2026-09-04 | 导入模块：由 0.2.x 单一「平面文件导入」扩展为面向三类场景的完整导入体系（三种导入源、统一内容模型、增量与冲突策略），新增导入前清单预览与面向 Agent harness 的结构化反馈接口（字段名冻结）；版本 0.3.0 同步 `__version__.py` + README 徽标 |
| 0.2.0 | 2026-08-20 | 换壳 pywebview（WebView2）根治首帧冻结；窗口原生动画/顶栏原生拖拽/Aero Snap/Win11 圆角/最大化铺满工作区；打包机制整理（scripts↔packaging 职责划分、构建脚本修复）；m0→app 目录与命名重构；版本统一机制（单一事实源 + 构建校验）；样式笔刷公式映射修复与选区高亮 |
| 0.1.0 | 2026-08 之前 | 早期版本（前置功能基线：知识库浏览、检索、图谱、链接、导入等） |
