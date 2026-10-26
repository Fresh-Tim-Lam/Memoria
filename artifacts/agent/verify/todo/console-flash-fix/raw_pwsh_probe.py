"""阳性对照：pythonw（无控制台父进程）直接 spawn **裸 PowerShell**，不带任何 flags。

用途：证明观测判据（EnumWindows 找 ConsoleWindowClass）**真的能看见**这个现象，
否则"改后 0 窗口"可能是假绿（判据本身看不见）。

注意：本机可能只装了 Windows PowerShell 5.1、没有 pwsh 7（`pwsh` 不在 PATH），
因此这里按 `pwsh` → `powershell` → `%COMSPEC%` 顺序取第一个可用解释器，
与产品 `resolve_interpreter()` 的回退顺序一致。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time


def main() -> int:
    exe = shutil.which("pwsh") or shutil.which("powershell") or os.environ.get("COMSPEC") or "cmd"
    args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
            "Write-Output 'RAW-OK'; Start-Sleep -Milliseconds 3000"]
    if exe.lower().endswith("cmd.exe"):
        args = ["/d", "/s", "/c", "echo RAW-OK & timeout /t 3 /nobreak >nul"]
    subprocess.run(
        [exe, *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
