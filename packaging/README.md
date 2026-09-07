# Memoria 打包工具（开发者用）

此目录仅用于**从源码构建** Windows 发布包，**不要**随 `Package/` 一起分发给最终用户。

## 构建（唯一入口）

```powershell
.\packaging\build_release.cmd            # 完整构建（PyInstaller --clean）
.\packaging\build_release.cmd --no-clean # 增量构建（跳过 --clean，构建更快）
```

`.cmd` 不受 PowerShell ExecutionPolicy 限制，是唯一受支持的构建入口。

首次或换环境：

```powershell
pip install -e .
pip install pyinstaller
```

## 产物位置

构建完成后，可分发目录为仓库根目录的 **`Package/`**：

```
Package/
  Memoria.exe
  lib/
  resources/
  config/               # ui-settings.json（与 exe 同目录，便携）
  VERSION
  manifest.json
  README.txt
```

将整个 `Package/` 文件夹打包（zip/拷贝）给用户即可。

## 随包资源登记（防漏包）

发布包的 `resources/` 内容由 `packaging/build.py` 的 **`_stage_runtime_resources()` 登记表**统一收集，不是自动整目录拷贝：

| 登记项（源 → 包内） | 性质 | 运行态读取方 |
|---|---|---|
| `resources/icons` → `resources/icons` | 必带 | 图标 |
| `resources/agent-prompts` → `resources/agent-prompts` | **必带** | `get_agent_prompt`（程序内 Agent 整理提示词，单一事实源） |
| `docs/reference`（白名单） → `resources/docs` | **必带** | `get_reference_doc`（弹窗"查看格式说明"，单一事实源） |
| `docs/example/showcase` → `resources/examples` | **必带** | 官方展示样例库（机器学习导论，打开知识库试用；仅正文/侧车/图片随包，cache 等剔除） |

- **必带清单**：`_REQUIRED_RELEASE_RESOURCES`；构建结束前 `_verify_release_resources()` 自检，缺失即终止构建。
- **新增随包资源（目录/必带文件）的维护铁律**：① 在 `build.py` 登记表（或必带清单）登记 → ② 同步本表 → ③ 有需要时更新 `templates/README.release.txt` → ④ 构建后到 `Package/resources/` 自检。
- 构建后自检（无需完整重打包）：

```powershell
python -c "from pathlib import Path; p=Path('Package/resources'); print('agent-prompts:', (p/'agent-prompts'/'organize.zh-CN.md').is_file(), '| docs:', (p/'docs'/'preview-formats.md').is_file(), '| examples:', (p/'examples'/'README.md').is_file(), (p/'examples'/'overview.md').is_file(), '| icons:', (p/'icons'/'Memoria.ico').is_file())"
```

## 本地运行

```powershell
.\packaging\run_release.cmd   # 运行 Package\Memoria.exe（发布态，pywebview 壳）
.\scripts\run_dev.ps1         # 开发态（源码 + pywebview 壳 + DevTools）
```

## 本目录说明

```
packaging/
  build_release.cmd         # 构建入口（唯一）
  run_release.cmd           # 发布态运行入口
  build.py                  # 构建主逻辑（PyInstaller + 布局 Package/ + manifest）
  app_release.py            # PyInstaller 入口（默认 pywebview 发布壳）
  memoria.spec              # PyInstaller 配置（contents_directory=lib）
  pyi_rth_memoria.py        # runtime hook（任务栏分组/图标）
  config/                   # 环境变量示例（dev / release）
  templates/                # 发布包内 README 模板
  build/                    # 中间产物（gitignore）
  dist/                     # 中间产物（gitignore）
```

> **职责划分**：`packaging/` = 打包发布的一切（入口脚本 + 构建实现 + 配置 + 文档），与 `scripts/`（开发者工具与研究脚本：开发态入口 `run_dev.ps1`、`benchmark/` 等）互不交叉。
