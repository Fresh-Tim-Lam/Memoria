# task-159 报告：修控制台弹窗闪烁（7 处子进程启动缺 `CREATE_NO_WINDOW`）

- **任务**：`task-159`（owner：agent-arch）
- **人反馈**：「裸机上跑发行版本的 agent 每次运行指令，pwsh 都显式弹窗闪烁」
- **日期**：2026-10-26
- **状态**：代码 + 单测 + **真机窗口 A/B** + 全部门禁 完成；**未 commit**（Lead 提交）

---

## 1. 根因（一句话）

发行版是 **GUI 子系统进程（无控制台）**；Windows 上从无控制台父进程启动控制台程序
（`pwsh.exe` / `powershell.exe` / `cmd.exe` / `python.exe`）时，**不带 `CREATE_NO_WINDOW` 就会新建可见控制台窗口** ⇒ 每条命令闪一下。
开发/测试环境本身在控制台里，子进程**继承**父控制台、不会新建窗口 ⇒ 所以只有发行版用户看得到。

**全部 7 处启动点确认（grep 全仓：修复前 `CREATE_NO_WINDOW` 0 处）**：

| # | 位置（修复后行号） | 用途 | 修复 |
|---|---|---|---|
| 1 | `src/memoria/services/agent/shell_exec.py#L165` | 探测解释器版本（`subprocess.run`） | `**no_window_kwargs()` |
| 2 | `src/memoria/services/agent/shell_exec.py#L281` | `taskkill /F /T` 终止进程树（`subprocess.run`） | 同上 |
| 3 | `src/memoria/services/agent/shell_exec.py#L334` | ★ **pwsh/cmd 执行内核**（`subprocess.Popen`，每次跑命令闪的就是它） | 同上 |
| 4 | `src/memoria/services/agent/scratch.py#L390` | scratch 面板执行脚本（`Popen`） | 同上 |
| 5 | `src/memoria/services/agent/tools/kb.py#L4797` | `fsrs.py` 调度脚本（`run`） | 同上 |
| 6 | `src/memoria/services/agent/tools/registry.py#L393` | 声明式扩展工具（stdio 子进程，`run`） | 同上 |
| 7 | `src/memoria/app/runtime.py#L131` | 派生新窗口（`Popen`，dev 态 `python app.py` 为控制台程序） | 同上 |

## 2. 统一封装（不各写一遍）

新增 `src/memoria/util/proc.py`（+ `src/memoria/util/__init__.py`）：

```python
def no_window_kwargs() -> dict[str, int]:
    if not _is_windows():          # 仅 sys.platform == "win32"
        return {}
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)  # getattr 兜底
    return {"creationflags": flags} if flags else {}
```

- **只返回 kwargs**：调用点的 `stdin/stdout/stderr`、`env`、`cwd`、`timeout`、`_terminate_tree` 逻辑**一律未动**；
- `_is_windows()` 独立函数便于单测 monkeypatch，**不全局改 `sys.platform`**；
- 拿不到 flag（异常运行时）安全降级 `{}`，不抛。

## 3. 单测（11 条，`tests/test_console_no_window.py`）

| 类别 | 断言 |
|---|---|
| 封装分支（3） | win32 → `{"creationflags": 0x08000000}`；非 win32 → `{}`；win32 但属性缺失 → `{}` 不抛 |
| **7 处接线**（7） | monkeypatch 捕获 `subprocess.run/Popen` 的 kwargs，逐个断言 7 个调用点真的拿到 `CREATIONFLAGS`；并复核 `stdin/stdout` 语义未变 |
| **防回归扫描**（1） | 扫 `src/memoria/**`：任何 `subprocess.Popen(`/`run(` 调用点若 16 行内无 `no_window_kwargs()` ⇒ 测试失败（防止将来新增启动点又闪） |

## 4. ★ 真机窗口验证（本任务核心验收）

### 4.1 等价性证据链（Lead 要求补的桥梁）

用 PE 头 `OptionalHeader.Subsystem` 证明「发行版 = GUI 无控制台」：

```
ev:file:artifacts/agent/verify/todo/console-flash-fix/pe_subsystem.py（输出）
Package/Memoria.exe      subsystem = 2 = IMAGE_SUBSYSTEM_WINDOWS_GUI   （无控制台）
D:\Python\pythonw.exe    subsystem = 2 = IMAGE_SUBSYSTEM_WINDOWS_GUI   （无控制台）
D:\Python\python.exe     subsystem = 3 = IMAGE_SUBSYSTEM_WINDOWS_CUI   （有控制台）
```

⇒ **发行版（GUI，无控制台）≡ `pythonw.exe`（GUI，无控制台）**；决定窗口是否新建的变量就是
"父进程有没有控制台"，因此 `pythonw` 是**打包等价环境**。本轮实验用 `pythonw.exe` 承载父进程，
**直接调用产品同一代码路径** `memoria.services.agent.shell_exec.run_command()`（不是合成 Popen）。

### 4.2 观测判据（防"假绿"）

`ev:file:artifacts/agent/verify/todo/console-flash-fix/run_flash_experiment.py`：

- Win32 `EnumWindows` 枚举**可见**窗口，取 `class ∈ {ConsoleWindowClass, CASCADIA_HOSTING_WINDOW_CLASS,
  PseudoConsoleWindow}` 或 owner exe ∈ {conhost, openconsole, windowsterminal, wt}；
- **基线 hwnd 差分**：用户本来就可能开着终端窗口（本机基线 6 个），判据只算「基线里没有的 hwnd」，
  否则固定基线会造成假绿；
- **时序**：子进程存活期间**每 50ms 轮询**（`proc.poll() is None` 循环），不是跑完数一次；
  每次 run 采样 **106–112 次**；
- **阳性对照**：用同一观测器看「`pythonw` + 裸 PowerShell、不带 flags」——必须能看到窗口，
  否则判据本身失明。

### 4.3 结果（`ev:measure:console-flash-experiment` = `runs/experiment.json`）

| 场景 | 新控制台窗口（基线差分） | 结论 |
|---|---|---|
| **阳性对照**（pythonw + 裸 PowerShell，无 flags） | **1 个**（`ConsoleWindowClass` / `powershell.exe`，首次出现 261ms） | 判据有判别力 ✅ |
| **改前等价**（legacy：monkeypatch 使 `no_window_kwargs()` 返回 `{}`） | **3/3 runs 均 4 个**：probe powershell ~0.43–0.52s、主命令 powershell ~0.65–0.86s、超时命令 ~4.25–4.35s、**taskkill ~5.2–5.4s**（并发峰值 2） | 复现"每条命令闪一下"✅（连 taskkill 也闪） |
| **改后**（真实代码，`CREATE_NO_WINDOW`） | **3/3 runs 均 0 个**（106–109 次采样全 0） | 修复生效 ✅ |

> 一个 run 内实际发生 5 次控制台程序启动（probe / 正常命令 / cmd 命令 / 超时命令 / taskkill），
> legacy 每次 4 个新窗口、fixed 每次 0 个 ⇒ 覆盖了 7 处中的 5 类调用（其余 2 处由单测 kwargs 断言覆盖）。

### 4.4 回归（同一次真机 run 内验证）

| 项 | 结果 |
|---|---|
| `pwsh` stdout | `PROBE-OK` 3/3 捕获成功 |
| `cmd` stdout | `CMD-OK` 3/3 捕获成功 |
| 退出码 | 正常 0；超时 `timedOut=true` 且 `exitCode=1`（3/3，语义与修复前一致） |
| 超时杀进程树 | 超时命令 `Start-Sleep 8` + `timeout_ms=800` → 1.7–1.8s 返回，taskkill 路径执行；**fixed 下 5.2s 处无 taskkill 窗口**（legacy 有） |

### 4.5 诚实边界（没做什么）

- **没有驱动 `Package/Memoria.exe` 的完整 UI agent 回合**（需要 CDP+LLM，成本 >30 分钟；Lead 已同意跳过）。
  本轮证据 = **PE Subsystem 等价性链** + **产品同一代码路径的真机 A/B**，不是"跑过发行版 UI"。
- 50ms 采样可能漏掉 **<50ms** 的极短闪现；但 legacy 侧能看见 taskkill（其窗口更短）⇒ 判据分辨率
  足以覆盖本现象；fixed 侧 15 次控制台启动全 0 窗口。
- `legacy` 是**等价模拟**（monkeypatch 让封装返回 `{}`，即修复前行为），不是跑旧二进制；
  这是为了同一脚本、同一判据做单变量 A/B。

## 5. 顺带核查：全仓进程启动点（Lead ③）

```
src/** 里 subprocess 相关 import 仅 6 个文件：
  shell_exec.py / scratch.py / tools/kb.py / tools/registry.py / app/runtime.py / util/proc.py
其他启动 API（全仓 src 0 命中）：
  asyncio.create_subprocess_exec / os.system / os.spawn* / os.startfile
  ShellExecute / _winapi.CreateProcess / Start-Process（产品 PowerShell 命令里也没有）
scripts/**：
  · 有 100+ 处 subprocess/child_process（benchmark/surface、maintenance、agent 工具等）
  · 但 `src/**` 从不 import scripts（grep 0 命中）⇒ **scripts 不是产品路径**，无需 flags（说明完成）
  · 例外：packaging/build.py 的 `subprocess.check_call` 是**构建机工具**，不随发行包运行
```

⇒ **产品路径启动点 = 上表 7 处，已全覆盖**；新增防回归测试会持续扫描。

## 6. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q tests` | **1516 passed / 0 failed**（基线 1485；+新增 11 条测试 + 其它成员新增） |
| `node --check`（all app js） | 62/62 files OK，0 fail |
| `i18n_selftest.js` | PASS（exit 0） |
| `team_audit.py` | **FAIL=0**（exit 0；WARN 52 为既有写域提示） |
| `prompt_drift_check.py` | **exit 0 / FAIL=0**（见 §7 指纹重签） |

## 7. 写域披露（超出 task-159 原始写域的部分）

1. **`src/memoria/app/runtime.py` 并发冲突**：task-160（arch-contract）也改此文件。
   我第一次改完后被对方版本覆盖；按 Lead 裁决「最后改 + rebase」在**其当前版本**上重新接线
   （`:L9` import + `:L131` kwargs），并在最终 diff 中确认存在。若 task-160 之后再次覆盖，需同样 rebase。
2. **`resources/agent-prompts/kb-agent-readme.md`**：`prompt_drift_check` 记录了该提示词对
   `scratch.py` 的依赖指纹；我改 `scratch.py` 导致 `version_stamp FAIL`。
   按工具规定流程 `--recheck-deps` 复核（仅新增 no window flags，未改执行权限/人工触发/输出上限/落盘语义），
   再 `--resign` 重签，日志追加到 `artifacts/agent/verify/todo/prompt-drift-recheck-log.jsonl`。
   **只改指纹元数据，未改提示词语义**。
3. 新增 `src/memoria/util/**`、`tests/test_console_no_window.py`、`artifacts/agent/verify/todo/console-flash-fix/**`。
4. **未动** `Package/**`、`docs/example/**`；**未 commit**。

## 8. 产物

| 产物 | 说明 |
|---|---|
| `src/memoria/util/proc.py` | 统一封装 `no_window_kwargs()` |
| 7 个调用点 diff | 见 §1 表 |
| `tests/test_console_no_window.py` | 11 条单测（含防回归扫描） |
| `artifacts/agent/verify/todo/console-flash-fix/pe_subsystem.py` | PE Subsystem 证据 |
| `artifacts/agent/verify/todo/console-flash-fix/run_flash_experiment.py` | 真机 A/B 编排 + 窗口枚举 |
| `artifacts/agent/verify/todo/console-flash-fix/spawn_driver.py` / `raw_pwsh_probe.py` | 被观察父进程 / 阳性对照 |
| `artifacts/agent/verify/todo/console-flash-fix/experiment.json` + `runs/driver-*.json` | 原始采样与驱动结果 |
| `artifacts/agent/verify/todo/console-flash-fix/pytest.txt` | 全量 pytest 输出 |

## 9. 一句话

**7 处启动点全部经同一封装加上 Windows `CREATE_NO_WINDOW`；`Package/Memoria.exe` 的 PE Subsystem=2（GUI 无控制台）
与 `pythonw` 等价，真机 A/B 显示：改前 3/3 次运行各出现 4 个控制台窗口（含 taskkill），改后 3/3 次运行 **0 个**，
同时 stdout/退出码/超时杀进程树全部不回归。**
