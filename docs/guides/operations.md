# 开发与发布操作手册（Operations）

> **用途**：Memoria 本地开发、验证、构建、发布的**可执行操作指引**——从零环境到发布包的全流程命令与注意事项。
> **目标读者**：维护者 / AI Agent（执行开发或发布任务时按本手册操作）。
> **关联文档**：[collaboration.md](./collaboration.md)（协作规则）；[version.md](../conventions/version.md)（版本规范）；[logging.md](../conventions/logging.md)（日志规范）；[packaging/README.md](../../packaging/README.md)（打包详情）。

---

## 1. 环境准备

```powershell
# 要求：Windows 10/11、Python ≥ 3.11
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"       # 开发安装（含 pytest）
pip install pyinstaller        # 仅构建发布包需要
```

可选依赖（按需）：
```powershell
pip install -e ".[semantic]"   # sentence-transformers 语义检索
pip install -e ".[search]"     # pypinyin 拼音搜索
```

## 2. 开发态运行

```powershell
.\scripts\run_dev.ps1          # 推荐：源码 + pywebview 壳 + DevTools + 无边框（MEMORIA_MODE=dev）
python app.py                  # 直接源码运行（同上，但需自行设环境变量）
```

`run_dev.ps1` 内置环境：`MEMORIA_MODE=dev`、`MEMORIA_SHELL=pywebview`、`MEMORIA_FRAMELESS=1`、`MEMORIA_DEBUG=1`。

切壳（备选 pyqt6）：
```powershell
$env:MEMORIA_SHELL="pyqt6"; .\scripts\run_dev.ps1
```

## 3. 验证

```powershell
pytest                         # 单元测试（tests/）
```

### 3.1 浏览器复现 harness（前端交互验证）

交互性前端改动（图片、编辑、图谱、导入）用 harness 在真实浏览器复现：

```powershell
python docs\example\rich-content-test\_harness.py            # 富内容样例库（KB=rich-content-test）
python docs\example\import-test\_harness_import.py --fresh    # 导入模块（KB=docs/example/empty3，--fresh 复位空库）
```

- harness 机制：bottle 服务真实前端 + UIAPI over `/rpc` + 注入 pywebview 桥。
- **注意**：harness 注入的桥对裸字符串 RPC 响应解析失败，需 `r.text()` + 单次解析的容错代理；且 api 需**异步延迟挂载**（先空壳再派发 `pywebviewready`，约 1.2s），否则晚于 app.js 加载的模块 init 会被静默跳过。
- 导入 harness 附加「测试反馈机制」（供 browseragent/脚本回读执行证据）：
  | 端点 | 作用 |
  |---|---|
  | `POST /harness/pick` | 队列 canned「文件选择」结果（`{type:dir\|files, value}`），替代原生对话框 |
  | `POST /harness/mark` | 测试步骤/断言标记（step/kind/ok/note） |
  | `POST /harness/console` | 前端 console/onerror/unhandledrejection 上报 |
  | `GET /harness/state` | 实时状态 + RPC/console 环形缓冲 |
  | `GET /harness/report` | 汇总结构化报告（meta+marks+rpc+console+错误统计），落 `<KB>/.memoria/harness/` |
- 验证原则：每阶段独立可交互验证（见 [image-asset-dev-plan.md](../design/image-asset-dev-plan.md) 的分阶段方法），完成即记录验证结果。

### 3.2 前端调试日志

| 前缀 | 含义 |
|------|------|
| `[SYNC]` | 预览同步（视图切换/内容收集/渲染） |
| `[img-rewrite]` | 图片路径重写（原 URL → API URL） |
| `[img-debug]` / `[img-attrs]` | 图片加载诊断 / 属性解析 |
| `[STATIC]` | 静态服务（KB 根初始化/文件请求/路径逃逸） |

## 4. 版本升级

1. 只改 [`src/memoria/__version__.py`](../../src/memoria/__version__.py)（唯一事实源，pyproject dynamic 读取）。
2. 构建时 `packaging/build.py` 自动读取并写入 manifest/VERSION/README。

```powershell
# 验证三处跟随：
python -c "import importlib; m=importlib.util.spec_from_file_location('v','src/memoria/__version__.py'); mod=importlib.util.module_from_spec(m); m.loader.exec_module(mod); print(mod.__version__)"
```

## 5. 构建发布包

```powershell
.\packaging\build_release.cmd            # 完整构建（PyInstaller --clean）
.\packaging\build_release.cmd --no-clean # 增量构建（更快）
```

- 产物：仓库根 `Package/`（`Memoria.exe` + `lib/` + `resources/` + `config/` + `VERSION` + `manifest.json` + `README.txt`）。
- 整包 zip/拷贝分发即可。
- **铁律**：`Package/lib/` 与 `src/` 代码必须同版本——每次改前端/后端后发布前重新构建；发布态验证跑 `.\.\packaging\run_release.cmd`。
- **随包资源**：`Package/resources/` 由 `packaging/build.py` `_stage_runtime_resources()` 登记表收集（icons/agent-prompts/docs 白名单/examples 官方展示库），构建结束前自动自检必带文件（含 `resources/agent-prompts/organize.zh-CN.md`、`resources/docs/preview-formats.md`、`resources/examples/README.md`）。新增随包资源按 [packaging/README.md](../../packaging/README.md)「随包资源登记」四步维护；构建后自检：
  ```powershell
  python -c "from pathlib import Path; p=Path('Package/resources'); print((p/'agent-prompts'/'organize.zh-CN.md').is_file(), (p/'docs'/'preview-formats.md').is_file(), (p/'examples'/'README.md').is_file(), (p/'icons'/'Memoria.ico').is_file())"
  ```
- 构建中间产物 `packaging/build/`、`packaging/dist/` 已被 gitignore，勿提交。

### 5.1 发布资产命名（GitHub Release）

Release 的 Asset 命名固定为：

| 资产 | 命名格式 | 内容 |
|------|---------|------|
| 完整包 | `Memoria-v<版本>-win64.zip` | 内置模型（`Package/hf/`），离线可用 |
| 轻量包 | `Memoria-v<版本>-win64-lite.zip` | 不含内置模型；首次使用 embedding / rerank 需联网获取 |

规则：

- `<版本>` 与 git tag、`__version__.py` 完全一致，**带 `v` 前缀**（tag `v0.3.1` → `Memoria-v0.3.1-win64.zip`）。
- 平台标识固定 `win64`；将来新增平台时追加平台后缀（如 `-macos-arm64`）。
- **无后缀 = 完整包**；`-lite` = 不含内置模型。两种形态**每次同时上传**，供用户按网络条件 / 磁盘占用自行选择。
- 样板（v0.3.1）：`Memoria-v0.3.1-win64.zip`（1182.8 MB）、`Memoria-v0.3.1-win64-lite.zip`（35.1 MB）。

发布资产生成（轻量包仅选完整包内容、排除 `hf/` 模型目录）：

```powershell
# 完整包（含内置模型 hf/）
Compress-Archive -Path "Package\Memoria.exe","Package\Memoria.exe.config","Package\lib","Package\resources","Package\hf","Package\README.txt","Package\VERSION","Package\manifest.json" `
  -DestinationPath "artifacts\Memoria-v<版本>-win64.zip" -CompressionLevel Optimal

# 轻量包（不含 hf/）
Compress-Archive -Path "Package\Memoria.exe","Package\Memoria.exe.config","Package\lib","Package\resources","Package\README.txt","Package\VERSION","Package\manifest.json" `
  -DestinationPath "artifacts\Memoria-v<版本>-win64-lite.zip" -CompressionLevel Optimal
```

> **两份清单都不打 `Package\config\`**：`build.py` 的 `_RELEASE_PRESERVE_DIRS` 会跨构建保留**开发机自己**的
> `ui-settings.json`（含 `last_kb_path`、`recent_kbs` 等本机私人路径），整目录打包会把维护者的本机设置分发出去。
> `config/` 本就由首次运行按需创建（`storage/ui_settings.py::save_ui_settings` 会 `mkdir(parents=True)`），
> 无需随包。`Package/config/` 仅为本地 `run_release.cmd` 保留。
> 用显式清单而非 `Package\*`，同理是为了不把 `.gitkeep`、`crash.log`、`logs/` 等运行时残留带进包。
>
> **`Memoria.exe.config` 不可省**：它是 .NET 应用配置，缺了则 zip 解压出的文件带 Mark-of-the-Web 时
> pythonnet 起不来（P06）。`packaging/build.py` 的 `_verify_release_bundle()` 会在构建末尾校验其存在。

### 5.2 Release 说明（双语 + 上下排版）

Release 正文必须**中英双语**，且**上下排版**——中文段在前、英文段在后，之间用 `---` 分隔：

```markdown
## Memoria vX.Y.Z

<中文说明：本次变更要点，含两个 package 的选择说明>
<系统要求 + 整包解压 / Unblock-File 提示>

---

## Memoria vX.Y.Z

<English description: same highlights, incl. which package to choose>
<system requirements + unzip / Unblock-File note>
```

规则：

- 两段使用**同一版本标题**，便于读者按语言定位。
- 用 `---` 分隔，避免中英混排导致标题层级混乱。
- 变更要点与「完整包 / 轻量包怎么选」在两段中**都要出现**（各自语言）。
- 两段**都要**给出**系统要求**（Windows 10/11 x64、.NET Framework 4.7.2+、WebView2）与「**整包解压**到可写目录、勿在 zip 内直接运行」的提示；启动排障指向 exe 同目录的 `crash.log`，并附可选命令 `Get-ChildItem -Recurse | Unblock-File`。
  - 原因（P06）：zip 解压会给文件打上 Mark-of-the-Web，.NET 因此拒绝 `Assembly.LoadFrom` 加载随包运行时，报 `Failed to resolve Python.Runtime.Loader.Initialize`，首发表现即「双击闪退」。产品侧的解法是随包 `Memoria.exe.config`（`loadFromRemoteSources`，见 §5.1）；`Unblock-File` 仅作兜底提示。随包 `README.release.txt` 与两份 README 已有同款说明。
- 样板：v0.3.2 Release（本条规范落地后的首个双语说明）。

#### 截图（必要时补）

有**用户可见的新功能 / 界面变化**时（如检查面板新增按钮、交互反馈变化），Release 说明应配截图：

- **复用 README 的同一份截图资源**：存放 `resources/screenshots/`、命名 `demo-<场景>.png`、分辨率与现有图一致；收录与三处登记流程见 [readme-i18n.md §3](../conventions/readme-i18n.md)（不新建第二份截图目录）。
- **Release 正文必须用绝对 URL**（Release 页面不具备仓库相对路径上下文）：

  ```markdown
  ![检查面板「复制报告」](https://raw.githubusercontent.com/Fresh-Tim-Lam/Memoria/main/resources/screenshots/demo-check-report.png)
  ```

- 中英两段**各自附一次**（同一张图可复用；`alt` / 图注用各自语言）。
- 该功能尚无截图时：先按 [readme-i18n.md §3.1](../conventions/readme-i18n.md) 入库（放入 `resources/screenshots/` + 两份 README 各加一张 + 登记），再在 Release 引用。
- 纯内部重构 / 修复、无界面变化时可省略截图。

## 6. 发布态运行

```powershell
.\packaging\run_release.cmd   # 运行 Package\Memoria.exe（发布态，pywebview 壳）
```

## 7. 日志与临时产物

- 调试日志按 [logging.md](../conventions/logging.md) 归置（默认 `artifacts/`，已被 gitignore）。
- `docs/tmp/` 只放少量诊断记录；一次性的批量产物进 `artifacts/`。

## 8. 发布里程碑收尾

发布成功（`build_release.cmd` 跑通）后按 [docs-management.md](../conventions/docs-management.md) §4.3 做 docs 定期整理：归位散文档、登记新文档、清理临时产物。
