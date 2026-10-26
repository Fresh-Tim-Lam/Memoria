"""子进程启动辅助：Windows 下不新建可见控制台窗口。

## 为什么需要它（task-159，人反馈 2026-10-26）

> 「裸机上跑发行版本的 agent 每次运行指令，pwsh 都显式弹窗闪烁」

根因：发行版是 **GUI 进程（无控制台）**；Windows 上从无控制台的父进程启动控制台程序
（`pwsh.exe` / `powershell.exe` / `cmd.exe` / `python.exe`）时，若不带 `CREATE_NO_WINDOW`
（或等价的 STARTUPINFO 隐藏标志），系统会**为子进程新建一个控制台窗口** ⇒ 每跑一条命令闪一下。
开发/测试环境通常本身就在控制台里，子进程会**继承**父控制台，不会新建窗口 ⇒ 该现象在开发环境
不可见（这也是为什么它只在发行版里被用户看到）。

## 语义：`CREATE_NO_WINDOW` = 「有 console 但无窗口」（**不是"没有 console"**）

⚠️ 微软文档字面写 "console handle is not set"，**按字面理解会得到错误结论**。实测（Windows 11 +
Python 3.12，证据见 `artifacts/agent/verify/todo/console-flash-semantic-audit.md`）：

- 子进程 `GetConsoleWindow() == 0`（没有**窗口**），但 **console 本身存在**：
  `GetConsoleOutputCP()` / `GetConsoleProcessList()` 正常，`std` 句柄可用；
- **子进程的 std 句柄继承自父进程**：真实 console 父进程下，fixed 子进程 `stdout` 仍是
  父 console 的句柄（`file_type=CHAR`、`isatty()==true`）⇒ 唯一不重定向 stdio 的调用点
  （`runtime.spawn_window`）输出可见性**不变**；
- **孙进程继承这个"无窗口 console"** ⇒ 子进程再启动 `cmd` / `python` / `git` 等控制台程序时
  **不会**再新建可见窗口（实测：GUI 父 + fixed 下 `cmd /c timeout`、`python -c sleep` 均 0 新窗口；
  未修复时各 1 个）—— 即用户真实命令链也不闪，不只是 `pwsh` 本身。

**已知 dev-only 差异**（发版前不处理，已登记债务）：子进程 console 与父 console 分离 ⇒
dev 环境下终端 Ctrl+C 不再跨到 agent 子命令；`GetConsoleWindow()==0` 对少数依赖 console 窗口
句柄的 TUI 有影响。取消路径是 `taskkill /F /T`（不依赖 console 信号），产品态（GUI 无 console）无感。

## 口径（task-159 要求，写死）

- **只在 `sys.platform == "win32"` 时返回 flags**：`CREATE_NO_WINDOW` 在 POSIX 上不存在，
  无条件取会 `AttributeError`；
- 用 `getattr(subprocess, "CREATE_NO_WINDOW", 0)` 兜底（老/裁剪的 Python 运行时也能安全降级）；
- **只返回 kwargs，不封装调用**：调用方保持自己的 `stdin/stdout/stderr` 语义、`env`、
  `cwd`、`timeout`、进程树终止逻辑不变 —— 本任务只加 flags，不改命令语义；
- 只抑制**子进程 console 窗口**，不改变 stdout/stderr（管道照常可读）、不改变退出码。

## 未来组合 flags 的约束（维护者必读）

- 本函数目前只返回 `creationflags`；**调用点禁止再手写 `creationflags=`**
  —— 重复关键字会 `TypeError: got multiple values for keyword argument 'creationflags'`（loud fail，
  不会静默忽略，好事，但别依赖它）。要组合别的 flags 时，把本函数扩成
  `no_window_kwargs(extra_flags: int = 0)` 再按位或；
- 实测 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`（`0x08000200`）**可以叠加**，子进程正常；
- **禁止**与 `CREATE_NEW_CONSOLE` / `DETACHED_PROCESS` 组合：Windows 文档规定此时 `CREATE_NO_WINDOW`
  被忽略（前者会弹出可见 console，后者没有 console）；
- `GenerateConsoleCtrlEvent` 只能触达**共享同一 console** 的进程；本 flag 使子进程 console 隔离 ⇒
  **console 信号式取消不可用**（现行取消走 `taskkill /F /T`，不受影响）。
- 新增产品路径启动点必须使用本函数（`tests/test_console_no_window.py` 有静态扫描防回归）。

## 用法

```python
from memoria.util.proc import no_window_kwargs

subprocess.run([exe, *args], stdout=subprocess.PIPE, **no_window_kwargs())
subprocess.Popen(cmd, stdin=subprocess.DEVNULL, **no_window_kwargs())
```

维护者可见的规则入口：`docs/reference/hard-constraints.md` §1「运行与平台」。
"""

from __future__ import annotations

import subprocess
import sys

#: `CREATE_NO_WINDOW` 的文档值（`0x08000000`）；仅作测试与降级参照。
CREATE_NO_WINDOW = 0x08000000


def _is_windows() -> bool:
    """运行平台判定（独立函数便于单测 monkeypatch，避免全局改 `sys.platform`）。"""
    return sys.platform == "win32"


def no_window_kwargs() -> dict[str, int]:
    """返回 `subprocess.*` 的 kwargs：Windows 上加 `CREATE_NO_WINDOW`，其他平台返回 `{}`。

    结果可直接 `**` 展开进 `subprocess.run/Popen/call/check_output`。不改变任何其它语义；
    拿不到 flag（异常运行时）时安全降级为 `{}`。
    """
    if not _is_windows():
        return {}
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    if not flags:
        return {}
    return {"creationflags": flags}


__all__ = ["CREATE_NO_WINDOW", "no_window_kwargs"]
