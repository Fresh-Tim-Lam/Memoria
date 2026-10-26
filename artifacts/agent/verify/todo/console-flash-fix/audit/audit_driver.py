"""语义审计驱动：由 python.exe（有控制台）或 pythonw.exe（无控制台）承载，
调用产品同一路径 `shell_exec.run_command()` 执行一条探测命令。

case：
  state     -> 启动一个控制台子进程（python child_console_report.py）并回传它的 console 状态
  nested    -> `cmd /c echo ...`：**孙进程**也是控制台应用 ⇒ 验证 nested 会不会再弹窗
  nested_py -> `python -c ...`：同上，孙进程是 python.exe
mode：
  fixed  = 真实代码（CREATE_NO_WINDOW）
  legacy = monkeypatch 让 no_window_kwargs() 返回 {}（修复前行为）
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tempfile

k32 = ctypes.windll.kernel32


def _console_state() -> dict:
    try:
        hwnd = int(k32.GetConsoleWindow())
    except Exception:  # noqa: BLE001
        hwnd = -1
    pids: list[int] = []
    try:
        arr = (ctypes.c_uint32 * 64)()
        n = int(k32.GetConsoleProcessList(arr, 64))
        pids = [int(arr[i]) for i in range(n)] if n else []
    except Exception:  # noqa: BLE001
        pass
    return {"pid": os.getpid(), "console_hwnd": hwnd, "console_process_ids": pids}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("fixed", "legacy"), required=True)
    ap.add_argument("--case", choices=("state", "nested", "nested_py"), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(os.environ.get("PYTHONPATH", "")))
    from memoria.util import proc as proc_mod

    if args.mode == "legacy":
        proc_mod._is_windows = lambda: False

    from memoria.services.agent import shell_exec

    kb = tempfile.mkdtemp(prefix="memoria-audit-kb-")
    child_json = os.path.join(os.path.dirname(args.out), f"child-{args.mode}-{args.case}-{os.getpid()}.json")
    child_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "child_console_report.py")
    quoted_py = sys.executable
    if quoted_py.lower().endswith("pythonw.exe"):
        # 驱动本身跑在 pythonw 下；探针子进程必须是**控制台程序** python.exe，
        # 否则它是 GUI 子系统、本来就没有控制台，测不到"孙进程会不会新建控制台"。
        quoted_py = quoted_py[: -len("pythonw.exe")] + "python.exe"
    if args.case == "state":
        # PowerShell 里用 `&` 调用带引号的 exe；否则首个引号串会被当表达式
        # sleep 1500ms：若孙进程被分配了新控制台窗口，则窗口会被"钉住"整个 1.5s，采样必然看到
        command = f'& "{quoted_py}" "{child_py}" --out "{child_json}" --sleep-ms 1500'
    elif args.case == "nested":
        # cmd 是控制台应用，且自身 sleep 2s ⇒ 若它被分配新控制台，窗口存活 2s（不会被采样漏掉）
        command = 'cmd /c "timeout /t 2 /nobreak >nul & echo NESTED-CMD-OK"'
    else:
        command = (
            f'& "{quoted_py}" -c "import time; time.sleep(2); print(\'NESTED-PY-OK\')"'
        )

    res = shell_exec.run_command(kb, shell="pwsh", command=command, timeout_ms=20000)
    out = {
        "mode": args.mode,
        "case": args.case,
        "parent_console": _console_state(),
        "no_window_kwargs": proc_mod.no_window_kwargs(),
        "result": {
            "exitCode": res.get("exitCode"),
            "stdout": res.get("stdout"),
            "stderr": res.get("stderr"),
            "timedOut": res.get("timedOut"),
            "interpreterKind": res.get("interpreterKind"),
        },
        "child_report_path": child_json if os.path.isfile(child_json) else None,
    }
    if os.path.isfile(child_json):
        with open(child_json, encoding="utf-8") as f:
            out["child_report"] = json.load(f)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
