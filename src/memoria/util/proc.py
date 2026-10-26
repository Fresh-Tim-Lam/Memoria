"""子进程启动辅助：Windows 下不新建可见控制台窗口。

## 为什么需要它（task-159，人反馈 2026-10-26）

> 「裸机上跑发行版本的 agent 每次运行指令，pwsh 都显式弹窗闪烁」

根因：发行版是 **GUI 进程（无控制台）**；Windows 上从无控制台的父进程启动控制台程序
（`pwsh.exe` / `powershell.exe` / `cmd.exe` / `python.exe`）时，若不带 `CREATE_NO_WINDOW`
（或等价的 STARTUPINFO 隐藏标志），系统会**为子进程新建一个控制台窗口** ⇒ 每跑一条命令闪一下。
开发/测试环境通常本身就在控制台里，子进程会**继承**父控制台，不会新建窗口 ⇒ 该现象在开发环境
不可见（这也是为什么它只在发行版里被用户看到）。

## 口径（task-159 要求，写死）

- **只在 `sys.platform == "win32"` 时返回 flags**：`CREATE_NO_WINDOW` 在 POSIX 上不存在，
  无条件取会 `AttributeError`；
- 用 `getattr(subprocess, "CREATE_NO_WINDOW", 0)` 兜底（老/裁剪的 Python 运行时也能安全降级）；
- **只返回 kwargs，不封装调用**：调用方保持自己的 `stdin/stdout/stderr` 语义、`env`、
  `cwd`、`timeout`、进程树终止逻辑不变 —— 本任务只加 flags，不改命令语义；
- 只抑制**子进程 console 窗口**，不改变 stdout/stderr（管道照常可读）、不改变退出码。

## 用法

```python
from memoria.util.proc import no_window_kwargs

subprocess.run([exe, *args], stdout=subprocess.PIPE, **no_window_kwargs())
subprocess.Popen(cmd, stdin=subprocess.DEVNULL, **no_window_kwargs())
```

注意：同一调用**不要**再传 `creationflags=`（会重复关键字）；若将来需要组合别的 flags，
应合并到本函数返回值里，而不是在调用点另加。
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
