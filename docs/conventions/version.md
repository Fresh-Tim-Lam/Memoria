# Memoria 版本规范

> **用途**：定义版本号格式、唯一事实源、一致性约束与升级流程，使源码、构建产物、UI 显示三处版本统一且可追踪。
> **目标读者**：项目负责人（用户）与 AI Agent（凡涉及版本变更或打包必读）。
> **关联文档**：[meta-rules.md](./meta-rules.md)（规范书写元规则）；[directory-organization.md](./directory-organization.md)（目录组织）。

## 1. 当前版本

| 项 | 值 |
|----|----|
| 当前版本 | **0.3.4** |
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
