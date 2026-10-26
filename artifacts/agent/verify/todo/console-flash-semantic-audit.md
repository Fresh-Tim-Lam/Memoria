# task-159 后续审计：`CREATE_NO_WINDOW` 的语义副作用与未来 flags 兼容性

- **任务来源**：Lead 在 `1da0b50b`（task-159 已提交）后要求的**纯审计**（不改代码）
- **日期**：2026-10-26
- **结论先行**：**未发现产品路径回归；发现 2 处 dev-only 语义变化 + 3 条未来使用约束，均不需要现在改代码。**
- **证据**：`artifacts/agent/verify/todo/console-flash-fix/audit/`（脚本 + JSON + 原始运行结果）

---

## 0. 官方语义 vs 实测语义（重要修正）

Microsoft `Process Creation Flags` 对 `CREATE_NO_WINDOW (0x08000000)` 的原文：

> "The process is a console application that is being run without a console window.
> Therefore, the console handle for the application is not set.
> This flag is ignored if the application is not a console application, or if it is used with
> either CREATE_NEW_CONSOLE or DETACHED_PROCESS."
> — https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags

**实测（本机 Windows 11 + Python 3.12.4，`audit/semantic_audit.json`）显示文档措辞会误导**：

| 场景 | 子进程 `GetConsoleWindow` | `GetConsoleOutputCP` | `GetConsoleProcessList` | stdout 句柄 |
|---|---|---|---|---|
| console 父 + legacy | 非 0（与父同一个 console） | 65001（父的 CP） | 含父/子等 5 个 | 继承父的 |
| console 父 + fixed | **0** | 437（子自己的 CP） | 2 个（子自己的 console） | 继承父的 |
| GUI 父 + legacy | 非 0（子自己的可见 console） | 437 | 2 个 | 继承/有效 |
| GUI 父 + fixed | **0** | 437 | 2 个 | 继承父（GUI 父无有效句柄则为空） |

⇒ **准确结论：`CREATE_NO_WINDOW` 不是"没有 console"，而是给子进程一个「无窗口的 console」**；
`GetConsoleWindow()==0` 只是"没有 console 窗口句柄"，console 本身仍存在（CP/进程列表/std 句柄都可用）。
**孙进程会继承这个无窗口 console ⇒ 不会再弹窗**（这是关键，见 §2）。

---

## 1. 唯一「会改变可观察行为」的位置：`runtime.spawn_window`

7 处启动点里 **6 处都显式重定向 stdio**（`DEVNULL`/`PIPE`），所以输出/输入语义与 flags 无关；
唯一不重定向的是 `runtime.spawn_window`（`Popen(cmd, env=..., cwd=...)` 无 stdio 参数）。

**实测（真实控制台父进程，`audit/console_parent_output.json`）**：

| 模式 | 子进程 console 窗口 | stdout 句柄 | stdout 类型 | `isatty()` | 输出是否仍进父终端 |
|---|---|---|---|---|---|
| legacy | **与父同一个**（hwnd 相同） | 12 | 2 = CHAR（console） | true | 是 |
| fixed | **0（自己的无窗口 console）** | **116 = 父的 console 句柄（继承）** | 2 = CHAR | **true** | **是**（继承句柄照常写父 console） |

⇒ **`spawn_window` 的 stdout/stderr 输出可见性没有回归**（dev 态 `python app.py` 的 print/traceback 仍写到启动它的终端）。
**变化只有「控制台归属」**：子进程不再与父共享 console，而是有自己的无窗口 console。

### dev-only 语义变化（建议记录，不建议改代码）
1. **Ctrl+C / 控制台控制事件不再跨进程传播**：dev 态在终端里按 Ctrl+C 只会作用于启动终端/父进程，**不会**再打到 agent 启动的命令子进程。
   - 产品态（GUI 无 console）本来就没有 Ctrl+C 通道；
   - 取消命令走 UI（`_terminate_tree` 的 `taskkill /F /T`）不受影响（task-159 已验证超时杀树）。
   - 若将来确实需要"从终端中断子命令"，可选简化：dev 态（`not is_frozen()`）`spawn_window` 不加 flags（dev 父进程有 console，本来就不闪）；**本次不改**。
2. **子进程 `GetConsoleWindow()==0`**：依赖 console 窗口句柄的程序（少数 TUI/取窗口位置的工具）在 agent 命令里行为可能不同；非交互 shell 命令不受影响（`stdout` 仍是有效 console 句柄，`isatty()` 仍为 true）。
3. **代码页**：子进程自己 console 的 CP=437，而父 console 是 65001；但子进程实际写的是**继承的父 console 句柄**（§1 表），所以输出编码路径与修复前一致。若将来有程序按"自己 console 的 CP"编码再写父句柄，非 ASCII 可能乱码（dev-only，低风险，记录待观察）。

---

## 2. 孙进程（nested）会不会"又弹窗"？—— 不会（实测 2 秒钉窗法）

担心点：文档说子进程 "console handle is not set"，那它再启动控制台程序（`cmd`/`python`/`git`）时
系统会不会给孙进程新建**可见** console？⇒ 用「让孙进程 sleep 2s 把窗口钉住」的方式实测（避免 50ms 采样漏掉）：

| 父进程 | 模式 | 孙进程 | 新控制台窗口数 |
|---|---|---|---|
| GUI（pythonw） | legacy | `cmd /c "timeout /t 2"` | **1**（powershell 自己的可见 console） |
| GUI（pythonw） | fixed | `cmd /c "timeout /t 2"` | **0** ✅ |
| GUI（pythonw） | legacy | `python -c "sleep 2"`（控制台程序） | **1**（powershell 的 console） |
| GUI（pythonw） | fixed | `python -c "sleep 2"` | **0** ✅ |
| 真实 console 父 | legacy/fixed | 上述两种 | 0 / 0（console 已存在，不新建窗口） |

⇒ **孙进程继承了「无窗口 console」→ 不再新建窗口**。用户跑 `git status`、`python script.py` 这类
**真实命令链也不会再闪**（不止 pwsh 本身）。这是本条修复能覆盖真实使用场景的关键证据。

---

## 3. 对未来 flags 的兼容性（Lead 点名的问题）

| 问题 | 实测/文档结论 | 建议 |
|---|---|---|
| `CREATE_NO_WINDOW` 与将来 `CREATE_NEW_PROCESS_GROUP`（0x200）能否共存？ | **可以按位或叠加**：实测 `0x08000200` 启动子进程 `returncode=0`、stdout 可读（`semantic_audit.json.micro_tests.combined_flags`） | 将来需要时把 helper 扩成 `no_window_kwargs(extra_flags=0)` 再 OR，**不要**在调用点手写 `creationflags=`（见下） |
| 调用点重复传 `creationflags=` 会怎样？ | **loud fail**：`subprocess.run() got multiple values for keyword argument 'creationflags'`（实测 TypeError，不会静默忽略） | 保持现状：重复即红；可在代码评审/防回归扫描里加一条"调用点不得出现 `creationflags=`"（目前 `tests/test_console_no_window.py` 已保证必须出现 `no_window_kwargs()`） |
| `CREATE_NO_WINDOW` + `CREATE_NEW_CONSOLE`/`DETACHED_PROCESS` | **文档规定 NO_WINDOW 被忽略**（前者会新建可见 console；后者无 console） | 禁止在 helper 里混入这两个；若将来需要 detached 行为，必须另写 helper 并说明 token 可见性 |
| `CREATE_NEW_PROCESS_GROUP` 的控制语义 | 文档：新进程组内 **CTRL+C 被禁用**；`GenerateConsoleCtrlEvent` **只能触达与调用方共享同一 console 的进程**（https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent ）；而 fixed 下子进程有**自己的无窗口 console** ⇒ 从父进程 `GenerateConsoleCtrlEvent` **无法**打到子进程 | 现有取消路径是 `taskkill /F /T`（不依赖 console 信号）⇒ **无影响**；将来若要做「温和中断」，不能用 console 信号，应走进程组 + 显式 IPC/信号约定 |
| GUI 子进程（`pythonw.exe`、`Memoria.exe`） | 文档：非控制台应用忽略该 flag；实测 GUI 子进程正常执行并写文件 | `runtime.spawn_window` 在 frozen 下启动 `sys.executable`（GUI）→ flag 被忽略、无害 |

---

## 4. 7 处逐点语义核对（"只加 flags 但改了语义"排查）

| # | 调用点 | stdio | flags 对语义的影响 | 结论 |
|---|---|---|---|---|
| 1 | `shell_exec._probe_version` | `DEVNULL`+`PIPE` | 无 console 输出/输入依赖；stdout 仍可读 | 无变化 |
| 2 | `shell_exec._terminate_tree`（taskkill） | 全 `DEVNULL` | 只少一个可见窗口；退出码/kill 行为不变 | 无变化（且 task-159 实测 taskkill 窗口消失） |
| 3 | `shell_exec.run_command` | `DEVNULL`+`PIPE` | 子进程 console 归属变化（隔离），stdout/stderr 管道不变、`isatty=false` 不变、退出码/超时/杀树不变 | 仅 console 隔离（见 §1 dev-only 说明；产品态无感） |
| 4 | `scratch.run_script` | `DEVNULL`+`PIPE` | 同上；脚本输出仍捕获、超时仍 `proc.kill()` | 无变化 |
| 5 | `kb._review_run_fsrs` | `PIPE`（capture） | 同上；`fsrs.py` 输出仍 JSON 解析 | 无变化 |
| 6 | `registry.make_subprocess_tool`（第三方 stdio 工具） | `PIPE`（input/text/capture） | 同上；stdin 仍 pipe 传入 JSON；第三方若依赖 console 窗口会受影响（见 §5） | 无产品变化；扩展工具契约需注明 |
| 7 | `runtime.spawn_window` | **无重定向** | console 归属变化 + Ctrl+C 隔离；**输出经继承句柄仍可见**（实测 §1） | 唯一 dev-only 变化 |

**其他机制核对**：`shell_exec` 的 `_EXEC_LOCK`（并发 1）、`_Budget` 输出预算、`_drain` 线程、`_child_env()` 白名单、
`timeout` 换算、`taskkill /F /T` 均未被 flags 触碰；`src/**` 无 `start_new_session` / `preexec_fn` / `close_fds` /
`os.system` / `asyncio.create_subprocess_*` / `os.spawn*`（task-159 已全仓扫过，本次复核仍为空）。

---

## 5. 残余风险与建议（不改代码，供后续决策）

| # | 风险 | 影响面 | 建议 |
|---|---|---|---|
| R1 | dev 态 Ctrl+C 不再跨到子命令 | 仅开发/测试（产品态 GUI 无 console） | 记录即可；若确有需要，dev 态 `spawn_window` 可跳过 flags（父 console 下本来不闪） |
| R2 | TUI/依赖 console 窗口句柄的程序在 agent shell 内行为可能不同 | 用户命令（非交互场景为主） | `shell_exec` 本就 `-NonInteractive` + 管道；可在工具说明里加一句"非交互、无 TTY"（已有类似口径） |
| R3 | 第三方扩展工具可能依赖真实 console（窗口） | `stdio` 扩展工具 | 在扩展工具契约里注明：Windows 发行版下子进程 console **无窗口**（`GetConsoleWindow()==0`），仅保证 stdin/stdout/stderr 管道 |
| R4 | 未来新启动点漏加 flags | 全部 | 已有 `tests/test_console_no_window.py::test_all_src_subprocess_launches_use_helper` 静态扫描（红即阻止） |
| R5 | 新模块 `memoria.util` 未进包 | 发行版启动即 ImportError | Lead 已计划打包后核对（PyInstaller 依赖分析应自动收录；本审计不涉及构建） |
| R6 | 打包 UI 完整回合未驱动 | 端到端最后一步 | 保留给 Lead 发版后人工验一次（task-159 已记录） |

---

## 6. 物证清单

| 文件 | 内容 |
|---|---|
| `audit/run_semantic_audit.py` | 四问题编排（console 归属 / 孙进程 / 组合 flags / GUI 子进程 / 输出可见性） |
| `audit/audit_driver.py` | 由 python.exe/pythonw.exe 承载、调用产品 `shell_exec.run_command` 的驱动 |
| `audit/child_console_report.py` | 子进程 console 状态探针 |
| `audit/console_parent_probe.py` + `child_stdio_probe.py` | 真实控制台下「无重定向 stdio」继承验证 |
| `audit/semantic_audit.json` | 12 组 parent×mode×case 运行结果 + micro tests |
| `audit/console_parent_output.json` | 真实 console 父进程的 stdio 继承证据 |

**审计结论**：`CREATE_NO_WINDOW` 的语义副作用被限制在「控制台归属/窗口」这一层；
**stdout/stderr、退出码、超时杀树、stdin 管道、GUI 子进程全部不受影响**；
孙进程继承无窗口 console 故不再闪；未来 `CREATE_NEW_PROCESS_GROUP` 可按位叠加但与"console 信号取消"不兼容
（现行 taskkill 路径已避开）。**无需修改代码，建议仅补文档/契约两处说明（R2/R3）。**

---

## 7. 契约落点（Lead 收口要求，2026-10-26 追加）

本轮审计的结论已写进**契约文档**（不只留在 artifacts）：

1. **实现侧**：`src/memoria/util/proc.py` 模块 docstring 增补
   「语义：`CREATE_NO_WINDOW` = 有 console 但无窗口（不是没有 console）」一节
   （std 句柄继承父 / 孙进程继承无窗口 console / dev-only 差异 / 未来组合 flags 约束）；
2. **维护者侧**：`docs/reference/hard-constraints.md` §1「运行与平台」新增
   「子进程控制台窗口（task-159）」硬约束条目（必须用 `no_window_kwargs()`、禁止手写
   `creationflags=`、孙进程结论、未来 flags 约束、证据与防回归测试位置）。

> 目的（对应 AGENTS L6）：让「下一个维护者读微软文档得出错误结论」这件事**在物理上不可通过**
> —— 规则出现在「硬约束」清单与实现模块 docstring 两处，而不只在本审计报告里。
> 门禁：`pytest -q tests/test_console_no_window.py tests/test_source_integrity.py` = **292 passed**。
