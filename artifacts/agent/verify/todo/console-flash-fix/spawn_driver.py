"""被观察的父进程：必须由 **pythonw.exe** 启动（GUI 子系统、无控制台）。

它直接调用产品同一代码路径 `memoria.services.agent.shell_exec.run_command()`
（agent 执行 pwsh 命令的内核），所以测的是真实产品行为，不是合成 Popen。

模式：
  fixed  —— 真实代码（含 task-159 修复：no_window_kwargs() 带 CREATE_NO_WINDOW）
  legacy —— 模拟修复前：monkeypatch `memoria.util.proc._is_windows -> False`，
            使 `no_window_kwargs()` 返回 {}（等价于旧代码没有 flags 的启动）

结果写 JSON 到 `--out`，父进程控制台状态用 `GetConsoleWindow()` 记录（应为 0）。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tempfile
import time


def _has_console() -> bool:
    try:
        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("fixed", "legacy"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep-ms", type=int, default=3000)
    args = ap.parse_args()

    sys.path.insert(0, str(os.environ.get("PYTHONPATH", "")))
    from memoria.util import proc as proc_mod

    if args.mode == "legacy":
        proc_mod._is_windows = lambda: False  # 等价于修复前：不给任何 creationflags

    from memoria.services.agent import shell_exec

    out: dict = {
        "mode": args.mode,
        "python": sys.executable,
        "frozen": bool(getattr(sys, "frozen", False)),
        "parent_has_console": _has_console(),
        "no_window_kwargs": proc_mod.no_window_kwargs(),
        "results": {},
    }
    kb = tempfile.mkdtemp(prefix="memoria-flash-kb-")
    try:
        command = f"Write-Output 'PROBE-OK'; Start-Sleep -Milliseconds {args.sleep_ms}"
        started = time.perf_counter()
        res = shell_exec.run_command(kb, shell="pwsh", command=command, timeout_ms=20000)
        out["results"]["normal"] = {
            "exitCode": res.get("exitCode"),
            "stdout": res.get("stdout"),
            "stderr": res.get("stderr"),
            "timedOut": res.get("timedOut"),
            "durationMs": round((time.perf_counter() - started) * 1000, 1),
            "interpreterKind": res.get("interpreterKind"),
        }
        # 超时分支：验证「超时仍终止进程树（taskkill 也 no-window）」+ 退出码语义
        started = time.perf_counter()
        killed = shell_exec.run_command(
            kb, shell="pwsh", command="Start-Sleep -Seconds 8", timeout_ms=800
        )
        out["results"]["timeout"] = {
            "exitCode": killed.get("exitCode"),
            "timedOut": killed.get("timedOut"),
            "durationMs": round((time.perf_counter() - started) * 1000, 1),
        }
        # cmd 分支：确认 cmd.exe 也走同一函数、stdout 仍可读
        cmd_res = shell_exec.run_command(kb, shell="cmd", command="echo CMD-OK", timeout_ms=20000)
        out["results"]["cmd"] = {
            "exitCode": cmd_res.get("exitCode"),
            "stdout": cmd_res.get("stdout"),
            "timedOut": cmd_res.get("timedOut"),
        }
    finally:
        out["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
