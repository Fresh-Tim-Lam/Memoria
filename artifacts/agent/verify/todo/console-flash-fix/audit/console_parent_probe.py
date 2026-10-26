"""验证「console 父进程 + CREATE_NO_WINDOW」下子进程是否仍继承父 console 的 stdout 句柄
（唯一不重定向 stdio 的启动点 `runtime.spawn_window` 的输出可见性）。

做法：本脚本由 **真实控制台** 承载（通过 `cmd /c python <本脚本>` 且带 CREATE_NEW_CONSOLE 启动一次），
它再以「不重定向 stdio」方式 spawn 一个控制台子进程（fixed / legacy 各一次），子进程把自己
stdout 句柄的类型/是否为 console/句柄值 写到文件；父进程也记录自己的 console 状态。
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time

k32 = ctypes.windll.kernel32
HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable if "pythonw" not in sys.executable.lower() else sys.executable.replace("pythonw.exe", "python.exe")


def _state() -> dict:
    h = int(k32.GetStdHandle(-11))
    return {
        "pid": os.getpid(),
        "console_hwnd": int(k32.GetConsoleWindow()),
        "stdout_handle": h,
        "stdout_file_type": int(k32.GetFileType(h)) if h not in (0, -1) else -1,
    }


def main() -> int:
    out_path = sys.argv[1]
    probe = os.path.join(HERE, "child_stdio_probe.py")
    report: dict = {"parent": _state(), "children": {}}
    for mode, flags in (("fixed", 0x08000000), ("legacy", 0)):
        child_out = out_path + f".{mode}.json"
        kwargs = {"creationflags": flags} if flags else {}
        try:
            subprocess.run([PYTHON, probe, child_out], timeout=30, **kwargs)
            time.sleep(0.2)
            with open(child_out, encoding="utf-8") as f:
                report["children"][mode] = json.load(f)
        except Exception as exc:  # noqa: BLE001
            report["children"][mode] = {"error": repr(exc)}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
