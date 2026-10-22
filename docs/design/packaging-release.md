# 壳与发布：P04 / P06 详情（2026-10-22 自 `docs/todo.md §8` 迁入）

> **用途**：承接 `docs/todo.md §8` 中 P04（Windows 右键集成 + 打开前安全检查）与 P06（打包态启动崩溃 = Mark-of-the-Web，根因/修复/证据）的**详情原文**，按台账维护规范 [规则 8](../conventions/ledger-maintenance.md) 与 Lead 裁决 P4 于 2026-10-22 逐字迁出。
> **目标读者**：发布/打包维护者、verifier、后续 TODO Owner。
> **关联**：[docs/todo.md](../../docs/todo.md) §8（**状态事实源**，P04/P06 编号与状态仍在表内）、[maintenance-jobs.md](./maintenance-jobs.md) §5、[operations.md](../guides/operations.md)（Release 规则）、证据 `artifacts/p06-motw-e2e.txt`。
> **状态**：生效中（2026-10-22）；本文件是详情存档，不改状态。

**P04 详情（2026-08-29 登记）：**

- **右键集成**：注册表 `HKCU\Software\Classes\Directory\shell\Memoria`（command → `Memoria.exe --open "%1"`）；提供安装/卸载入口（打包安装器或程序内「集成右键菜单」开关）。
- **exe 入口**：CLI 支持 `--open <dir>` → 启动即加载该文件夹为知识库（对齐现有 kb 加载链路）。
- **打开前安全检查**（任一不通过 → 明确提示，不强行打开）：① 存在性（存在且为目录）② 权限（可读+可写，防只读介质写 `.memoria` 失败）③ 范围（排除 `C:\Windows`、`Program Files`、`ProgramData`、回收站、`C:\` 根等）④ 结构（含 `.memoria/` 直接打开；空目录提示可初始化；有 md 无 `.memoria` 提示将创建并写前确认）⑤ 路径（长度限制、非法/特殊字符、UNC/网络路径）⑥ 占用（已被另一实例打开 → 聚焦已有窗口）。
- **验收**：右键 → 打开指定文件夹成为当前知识库；安全项逐一构造反例验证提示正确；卸载后右键菜单消失。

**P06 详情（2026-09-18 登记；同日定位根因、修复并重新发布）：**

- **现象**：他人机器解压 `Memoria-v0.3.4-win64-lite.zip` 后启动即崩 —— `pythonnet/__init__.py:143 load()` → `clr_loader/netfx.py:47` → `RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize from <解压目录>\lib\pythonnet\runtime\Python.Runtime.dll`。
- **根因 = Mark-of-the-Web（实测）**：zip 解压出的文件被 Windows 写入 `Zone.Identifier`（ZoneId=3）；.NET 的 `Assembly.LoadFrom` 拒绝加载来源为「Internet 区域」的程序集（HRESULT `0x80131515`），而 clr\_loader 的原生入口把该异常吞成 NULL，故 Python 侧只剩上面那句无细节报错。对照实验（同一 445,952 B 的 dll）：干净 → OK；打 ZoneId=3 → 失败；`Unblock-File` → OK（可逆、确定性）；给真实 `.venv` 的 dll 打标记后 `import clr` 复现出**逐字一致**的 traceback。已排除打包缺件（完整版/lite 版 105 条条目逐一相同）与目标机 .NET 版本（报错机 `Release=0x82405` ≈ 4.8，足够）。
- **修复**：**随包** **`Memoria.exe.config`**（`<loadFromRemoteSources enabled="true"/>`，.NET 为「加载 Internet 区域程序集」提供的官方开关）—— 新增模板 `packaging/templates/Memoria.exe.config`，`build.py::_stage_release` 拷入、`_verify_release_bundle()` 构建末尾校验，两份 zip 清单（`operations.md §5.1`）同步加入。配套 `app_release.py::_show_fatal_dialog()`（发布态启动失败弹可读弹窗）、两份 README / 随包 `README.release.txt` / `site/**` 补系统要求与整包解压说明，并写死进 `operations.md §5.2` 的 Release 规则。
- **否决的初版做法**：启动时删 `lib/pythonnet/**` 的 `Zone.Identifier`（`runtime.py::unblock_bundled_runtime()` + 4 例单测）**已全部移除** —— 该删流操作在本机 D: 盘静默失效（`os.remove` 不抛异常、`DeleteFileW` 返回 TRUE 而流仍在，`Unblock-File` 亦无效），且属修改文件元数据；改用配置后不需要它。
- **顺带修复**：两份 zip 不再打 `Package\config\`——`_RELEASE_PRESERVE_DIRS` 会跨构建保留开发机自己的 `ui-settings.json`（含本机私人路径），整目录打包会把它发出去。
- **证据**：`artifacts/p06-motw-e2e.txt`。发布态 A/B（同一产物，只差 `Memoria.exe.config`）：无配置 → `crash.log` 内容即该 RuntimeError；有配置 → dll 仍带 MotW 也正常启动。全套 `pytest -q` 80 passed。
- **遗留**：发布包不含 PyQt6（`spec:12` 的 `_HEAVY_EXCLUDES`），「回退 Qt 壳」不可行，由可读弹窗兜底。**v0.3.0～v0.3.4 共 5 个 Release、9 个 zip 已全部重新构建并替换**（旧版由各自 tag 的 `git worktree` 构建 + 注入 `Memoria.exe.config`）；报错机器按新包复验待用户执行。同批清理了随包示例库的运行/调试产物残留（见 [docs-management.md](conventions/docs-management.md) §4.2 同日条目）。
