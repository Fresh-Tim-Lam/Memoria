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
- **随包资源**：`Package/resources/` 由 `packaging/build.py` `_stage_runtime_resources()` 登记表收集（icons / agent-prompts / agent-capabilities 能力插件声明 / agent-skills 内置技能 / docs 白名单 / examples 官方展示库），构建结束前自动自检必带文件（含 `resources/agent-prompts/organize.zh-CN.md`、`resources/agent-capabilities/kb-write.json`、`resources/agent-skills/web-research/SKILL.md`、`resources/docs/preview-formats.md`、`resources/examples/README.md`）。新增随包资源按 [packaging/README.md](../../packaging/README.md)「随包资源登记」四步维护；构建后自检：
  ```powershell
  python -c "from pathlib import Path; p=Path('Package/resources'); print((p/'agent-prompts'/'organize.zh-CN.md').is_file(), (p/'agent-capabilities'/'kb-write.json').is_file(), (p/'agent-skills'/'web-research'/'SKILL.md').is_file(), (p/'docs'/'preview-formats.md').is_file(), (p/'examples'/'README.md').is_file(), (p/'icons'/'Memoria.ico').is_file())"
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

> **历史漂移（2026-10-25 核实，勿再复制）**：`v0.4.7` / `v0.4.8` / `v0.5.0` 三个 Release 的实际资产名是
> `Memoria-vX.Y.Z-lite.zip`（缺 `win64-` 平台段），**根因是 v0.4.7 只看最近自己的命名习惯照抄，没人回头对照本表**。
> `v0.3.x`–`v0.4.6` 均为规范的 `-win64-lite.zip`。
> **已发布资产不改名**（可能有外部链接/用户已存路径）；**新发布一律用 `Memoria-vX.Y.Z-win64-lite.zip`**。
> 机检 `release_preflight.py --verify-published` 的 `ASSETS-COUNT` 两种都接受，`-lite.zip` 只 WARN 提示漂移。

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
> 无需随包。`Package/config/` 仅为本地 `run_release.cmd` 保留。
> 用显式清单而非 `Package\*`，同理是为了不把 `.gitkeep`、`crash.log`、`logs/` 等运行时残留带进包。
>
> **⚠️ 用户态已移出安装目录（task-160 / 0.4.10 起，必读）**
>
> 上面的 "`config/` 由首次运行按需创建" 只对**安装目录内的旧位置**成立。
> **0.4.10 起，用户态（`ui-settings.json` / `agent.json`）默认落在**
> `%LOCALAPPDATA%\Memoria\config\`（解析函数 `memoria.util.user_state.user_config_dir()`）：
>
> | 位置 | 谁用 | 换包（解压覆盖/换目录）时 |
> |---|---|---|
> | `%LOCALAPPDATA%\Memoria\config\` | **最终用户**（默认落点） | **完全不动** ⇒ 配置、API key、最近库列表都保留 |
> | `<install_root>\config\`（旧位置） | 仅**兼容读取**（一次性迁移源） | 会被覆盖；迁移**只复制不删**，残留副本可作备份但**不再被读取** |
> | `Package\config\`（构建机） | `run_release.cmd` 本地运行 | 不随包分发（见上） |
>
> - 优先级：`MEMORIA_CONFIG_DIR` / `MEMORIA_AGENT_CONFIG` > `%LOCALAPPDATA%\Memoria\config`。
> - **取 `%LOCALAPPDATA%` 而非 `%APPDATA%`**：`ui-settings` 存的是**绝对路径 + 窗口位置**（漫游到别的机器全失效），
>   `agent.json` 含 **API key**（漫游会把凭据复制到多台机器，扩大泄露面）。两者都是"机器本地状态"。
> - **迁移三条不变量**：旧有新无 ⇒ 迁移；两边都有 ⇒ **以新位置为准，绝不覆盖**；
>   迁移失败 ⇒ 用默认值 + 记 warn（**不回落到旧目录读**，否则用户的修改会被旧值静默覆盖）。
> - 真机验证：`artifacts/agent/verify/todo/user-state-relocation-swap-sim.py`（伪安装目录 → 删掉 → 再启动，配置仍在）。
>
> **`Memoria.exe.config` 不可省**：它是 .NET 应用配置，缺了则 zip 解压出的文件带 Mark-of-the-Web 时
> pythonnet 起不来（P06）。`packaging/build.py` 的 `_verify_release_bundle()` 会在构建末尾校验其存在。

### 5.2 Release 说明（双语 + 英语在前，机检）

> **规则单一事实源**：[version.md「GitHub Release 规范」](../conventions/version.md)（三条硬规则 +
> §6 第 0 步门禁）。本节只给排版骨架；冲突时以 version.md 为准，且以
> `scripts/agent/release_preflight.py` 的机器判定为准（`exit 1` 不得发布）。
> **注意：英文段在【前】、中文段在【后】**（2026-10-25 更正；旧版本本节曾写反，是违规来源之一）。

```markdown
# Memoria vX.Y.Z

## English

<English highlights: what changed, which package to choose>
<system requirements + unzip / Unblock-File note>

## Cost (Agent compute)

- **Magnitude**: roughly **CNY XXX-XXX** (estimate; not itemised).
- **Accounting basis**: <single version or merged block>.
- **Cost structure (one line)**: <where the spend went>.

---

## 中文

<中文要点：改了什么、完整包 / 轻量包怎么选>
<系统要求 + 整包解压 / Unblock-File 提示>

## 造价（Agent 算力）

- **量级**：约 **XXX–XXX 元人民币**（估算，非逐项计量）。
- **统计口径**：<单版或合并统计；为什么不能诚实切分>。
- **成本结构（一句话）**：<钱主要花在哪>。
```

规则：

- 标题/正文硬规则（标题严格等于 `Memoria vX.Y.Z`、English 在前、两段 >200 字符、中英双造价段）
  见 version.md；**不要再在 Release 标题上加副标题或「## Memoria vX.Y.Z」式段落标题**。
- 用 `---` 分隔两种语言，避免中英混排导致标题层级混乱。
- 变更要点与「完整包 / 轻量包怎么选」在两段中**都要出现**（各自语言），且**两段都要完整**（不是一段摘要）。
- 代码、文件名、`file:line`、commit sha 在两种语言里**保持原样**。
- 两段**都要**给出**系统要求**（Windows 10/11 x64、.NET Framework 4.7.2+、WebView2）与「**整包解压**到可写目录、勿在 zip 内直接运行」的提示；启动排障指向 exe 同目录的 `crash.log`，并附可选命令 `Get-ChildItem -Recurse | Unblock-File`。
  - 原因（P06）：zip 解压会给文件打上 Mark-of-the-Web，.NET 因此拒绝 `Assembly.LoadFrom` 加载随包运行时，报 `Failed to resolve Python.Runtime.Loader.Initialize`，首发表现即「双击闪退」。产品侧的解法是随包 `Memoria.exe.config`（`loadFromRemoteSources`，见 §5.1）；`Unblock-File` 仅作兜底提示。随包 `README.release.txt` 与两份 README 已有同款说明。
- 样板：v0.5.0 Release（双语 + 造价段 + 机检通过后的首个样板）。

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

### 5.3 网络与代理（连不上时先试代理）

推 tag / 调 GitHub API / 下载依赖 / 上传发布资产时报 `Connection reset` 或 TCP 443 超时，**先改走本机代理重试**（已实测可用，均返回 200）：

- HTTP 代理 `http://127.0.0.1:10809`；SOCKS5 代理 `socks5://127.0.0.1:10808`。
- git（命令级临时生效）：`git -c http.proxy=http://127.0.0.1:10809 push origin <tag>`；或先设 `$env:HTTPS_PROXY="http://127.0.0.1:10809"` / `$env:ALL_PROXY="socks5://127.0.0.1:10808"` 再执行原命令。
- curl / `Invoke-RestMethod`：`curl.exe --socks5-hostname 127.0.0.1:10808 https://api.github.com/rate_limit`（`--socks5-hostname` 让 DNS 也走代理）。
- **不得修改 git config**，只做命令级临时生效；直接重试常能恢复（v0.4.0 发版 tag push 曾连续 `Connection reset`，重试 + 代理后成功）。

## 6. 发布态运行

```powershell
.\packaging\run_release.cmd   # 运行 Package\Memoria.exe（发布态，pywebview 壳）
```

## 7. 日志与临时产物

- 调试日志按 [logging.md](../conventions/logging.md) 归置（默认 `artifacts/`，已被 gitignore）。
- `docs/tmp/` 只放少量诊断记录；一次性的批量产物进 `artifacts/`。

## 8. 发布里程碑收尾

发布成功（`build_release.cmd` 跑通）后按 [docs-management.md](../conventions/docs-management.md) §4.3 做 docs 定期整理：归位散文档、登记新文档、清理临时产物。
