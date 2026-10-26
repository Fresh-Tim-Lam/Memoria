"""子进程自报 stdio 句柄状态（被 console_parent_probe 以"不重定向 stdio"方式启动）。"""

from __future__ import annotations

import ctypes
import json
import os
import sys

k32 = ctypes.windll.kernel32


def main() -> int:
    out = sys.argv[1]
    h = int(k32.GetStdHandle(-11))
    mode = ctypes.c_uint32()
    mode_ok = bool(k32.GetConsoleMode(h, ctypes.byref(mode))) if h not in (0, -1) else False
    report = {
        "pid": os.getpid(),
        "console_hwnd": int(k32.GetConsoleWindow()),
        "stdout_handle": h,
        # 2=CHAR(控制台/字符设备) 3=PIPE 1=DISK 0=UNKNOWN/invalid
        "stdout_file_type": int(k32.GetFileType(h)) if h not in (0, -1) else -1,
        "stdout_console_mode_ok": mode_ok,
        "stdout_isatty": sys.stdout.isatty(),
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
