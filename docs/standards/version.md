# Memoria 版本规范

> **用途**：定义版本号格式、唯一事实源、一致性约束与升级流程，使源码、构建产物、UI 显示三处版本统一且可追踪。
> **目标读者**：项目负责人（用户）与 AI Agent（凡涉及版本变更或打包必读）。
> **关联文档**：[AAA 讨论元规范](./AAA_讨论元规范.md)（规范书写元规则）；[directory-organization.md](./directory-organization.md)（目录组织）。

## 1. 当前版本

| 项 | 值 |
|----|----|
| 当前版本 | **0.2.0** |
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

## 7. 变更记录（CHANGELOG）

> 约定：每次升级在此追加一行。格式：`版本号（日期）｜ 变更要点`。

| 版本 | 日期 | 变更 |
|------|------|------|
| 0.2.0 | 2026-08-20 | 换壳 pywebview（WebView2）根治首帧冻结；窗口原生动画/顶栏原生拖拽/Aero Snap/Win11 圆角/最大化铺满工作区；打包机制整理（scripts↔packaging 职责划分、构建脚本修复）；m0→app 目录与命名重构；版本统一机制（单一事实源 + 构建校验）；样式笔刷公式映射修复与选区高亮 |
| 0.1.0 | 2026-08 之前 | 早期版本（前置功能基线：知识库浏览、检索、图谱、链接、导入等） |
