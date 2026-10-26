"""子进程控制台状态探针（被 run_command 启动的控制台应用）。

报告：自身 console 句柄、附着到该 console 的进程列表、stdio 句柄类型、
stdout 的 console mode（是否为控制台）、输出代码页、isatty。
用于对比 legacy / fixed 两种启动方式下「子进程到底有没有控制台、和父进程是不是同一个」。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys

k32 = ctypes.windll.kernel32


def _console_hwnd() -> int:
    try:
        return int(k32.GetConsoleWindow())
    except Exception:  # noqa: BLE001
        return -1


def _console_pids() -> list[int]:
    try:
        arr = (ctypes.c_uint32 * 64)()
        n = int(k32.GetConsoleProcessList(arr, 64))
        return [int(arr[i]) for i in range(n)] if n else []
    except Exception:  # noqa: BLE001
        return []


def _stdio_report() -> dict:
    out = {}
    for name, which in (("stdin", -10), ("stdout", -11), ("stderr", -12)):
        try:
            h = int(k32.GetStdHandle(which))
            ftype = int(k32.GetFileType(h)) if h not in (0, -1) else -1
            mode = ctypes.c_uint32()
            mode_ok = bool(k32.GetConsoleMode(h, ctypes.byref(mode))) if h not in (0, -1) else False
            out[name] = {
                "handle": h,
                "file_type": ftype,  # 0=UNKNOWN 1=DISK 2=CHAR 3=PIPE
                "console_mode_ok": mode_ok,
                "console_mode": int(mode.value) if mode_ok else None,
            }
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": repr(exc)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep-ms", type=int, default=0)
    args = ap.parse_args()
    kps = _console_pids()
    report = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "python": sys.executable,
        "console_hwnd": _console_hwnd(),
        # 若返回 0/空 ⇒ 该进程没有 console；若含自己和父 pid ⇒ 与父共享同一 console
        "console_process_ids": kps,
        "console_output_cp": int(k32.GetConsoleOutputCP() or 0),
        "isatty": {"stdin": sys.stdin.isatty(), "stdout": sys.stdout.isatty()},
        "stdio": _stdio_report(),
        "cwd": os.getcwd(),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    if args.sleep_ms > 0:
        import time

        time.sleep(args.sleep_ms / 1000.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
