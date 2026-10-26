"""控制台窗口观测器（Win32 EnumWindows）+ 启动实验编排。

判据（task-159）：
  · 改前（legacy：模拟修复前，`no_window_kwargs()` 强制返回 {}）⇒ 子进程存活期间应枚举到 ≥1 个控制台窗口
  · 改后（fixed：真实代码）⇒ 应为 0
  · **时序**：窗口可能瞬间创建又销毁 ⇒ 在子进程运行期间每 50ms 轮询采样，而不是跑完数一次
  · 观察器自身必须有判别力：先做一次**阳性对照**（pythonw 父进程直接 spawn 一个裸 pwsh，不带 flags）

用法（仓库根目录，普通控制台里跑；被观察的父进程由 pythonw.exe 承载）：
    python artifacts/agent/verify/todo/console-flash-fix/run_flash_experiment.py --runs 3 --json out.json
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
PYTHONW = Path(sys.executable).with_name("pythonw.exe")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# 控制台/终端窗口类名（经典 conhost / Windows Terminal / ConPTY）
CONSOLE_CLASSES = {
    "ConsoleWindowClass",
    "CASCADIA_HOSTING_WINDOW_CLASS",
    "PseudoConsoleWindow",
    "Windows.UI.Core.CoreWindow",
}
CONSOLE_EXES = {"conhost.exe", "openconsole.exe", "windowsterminal.exe", "wt.exe"}


def _process_image(pid: int) -> str:
    """PID → 可执行文件路径（失败返回空串，绝不抛）。"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def snapshot_console_windows() -> dict:
    """枚举当前**可见**的控制台类窗口（含 owner exe，非控制台类只记总数）。"""
    rows: list[dict] = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 2)
        user32.GetWindowTextW(hwnd, title_buf, length + 2)
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, 256)
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        cls = class_buf.value
        exe = os.path.basename(_process_image(pid.value)).lower() if pid.value else ""
        if cls in CONSOLE_CLASSES or exe in CONSOLE_EXES:
            rows.append(
                {
                    "hwnd": hex(hwnd),
                    "class": cls,
                    "title": title_buf.value,
                    "pid": int(pid.value),
                    "exe": exe,
                }
            )
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    return {"count": len(rows), "windows": rows}


def poll_while(proc: subprocess.Popen, *, interval_s: float = 0.05, baseline_hwnds: set[str] | None = None) -> dict:
    """在 `proc` 存活期间持续采样（核心：不能只跑完数一次）。

    **判别力**：只把「基线里没有的 hwnd」算作新窗口 —— 用户可能本来就有已打开的终端窗口，
    绝对数量不是判据；`new_hwnds` 才是。
    """
    base = set(baseline_hwnds or ())
    samples: list[dict] = []
    max_absolute = 0
    max_new = 0
    new_union: dict[str, dict] = {}
    started = time.perf_counter()
    while proc.poll() is None:
        snap = snapshot_console_windows()
        rows = {row["hwnd"]: row for row in snap["windows"]}
        fresh = [row for hwnd, row in rows.items() if hwnd not in base]
        for row in fresh:
            new_union.setdefault(row["hwnd"], {**row, "first_seen_ms": round((time.perf_counter() - started) * 1000, 1)})
        samples.append(
            {
                "t_ms": round((time.perf_counter() - started) * 1000, 1),
                "count": snap["count"],
                "new_count": len(fresh),
            }
        )
        max_absolute = max(max_absolute, snap["count"])
        max_new = max(max_new, len(fresh))
        time.sleep(interval_s)
    proc.wait()
    return {
        "samples": len(samples),
        "sample_interval_s": interval_s,
        "max_console_windows_absolute": max_absolute,
        "max_new_console_windows": max_new,
        "new_console_windows": list(new_union.values()),
        "sample_tail": samples[-5:],
        "exit_code": proc.returncode,
    }


def _baseline_samples(n: int = 10, interval_s: float = 0.03) -> dict:
    counts = []
    hwnds: set[str] = set()
    rows: list[dict] = []
    for _ in range(n):
        snap = snapshot_console_windows()
        counts.append(snap["count"])
        hwnds.update(row["hwnd"] for row in snap["windows"])
        rows = snap["windows"]
        time.sleep(interval_s)
    return {
        "samples": counts,
        "max": max(counts) if counts else 0,
        "min": min(counts) if counts else 0,
        "hwnds": sorted(hwnds),
        "rows": rows,
    }


def run_driver(mode: str, *, out_dir: Path, run_id: str) -> dict:
    """启动 pythonw 父进程（无控制台）→ 内部调用 shell_exec.run_command。"""
    driver = HERE / "spawn_driver.py"
    result_file = out_dir / f"driver-{run_id}.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    env["MEMORIA_CONFIG_DIR"] = str(out_dir / "cfg")
    cmd = [str(PYTHONW), str(driver), "--mode", mode, "--out", str(result_file)]
    baseline = _baseline_samples()
    started = time.perf_counter()
    proc = subprocess.Popen(cmd, env=env, cwd=str(REPO))
    observed = poll_while(proc, baseline_hwnds=set(baseline["hwnds"]))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    driver_out = json.loads(result_file.read_text(encoding="utf-8")) if result_file.is_file() else {}
    return {
        "mode": mode,
        "run_id": run_id,
        "elapsed_ms": elapsed_ms,
        "baseline_console_windows": baseline,
        "observation": observed,
        "driver_result": driver_out,
        "parent_has_console": False,  # pythonw：GUI 子系统，无控制台
        "verdict_new_console_window_seen": observed["max_new_console_windows"] > 0,
    }


def positive_control(out_dir: Path) -> dict:
    """阳性对照：pythonw 父进程直接 spawn **裸 powershell**（不带任何 flags）⇒ 判据必须能看见新窗口。"""
    probe = HERE / "raw_pwsh_probe.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    baseline = _baseline_samples()
    proc = subprocess.Popen([str(PYTHONW), str(probe)], env=env, cwd=str(REPO))
    observed = poll_while(proc, baseline_hwnds=set(baseline["hwnds"]))
    return {
        "kind": "positive_control_raw_powershell_no_flags",
        "baseline_console_windows": baseline,
        "observation": observed,
        "verdict_new_console_window_seen": observed["max_new_console_windows"] > 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    out_dir = HERE / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "schema": "console-flash-experiment/v1",
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo": str(REPO),
        "python": sys.executable,
        "pythonw": str(PYTHONW),
        "positive_control": positive_control(out_dir),
        "runs": [],
    }
    for i in range(1, args.runs + 1):
        # 交替执行，避免"总是先跑某模式"的系统偏差
        for mode in ("legacy", "fixed"):
            report["runs"].append(run_driver(mode, out_dir=out_dir, run_id=f"{mode}-{i}"))
    for mode in ("legacy", "fixed"):
        rows = [r for r in report["runs"] if r["mode"] == mode]
        report[f"summary_{mode}"] = {
            "runs": len(rows),
            "max_new_console_windows_each_run": [r["observation"]["max_new_console_windows"] for r in rows],
            "any_new_window_seen": any(r["verdict_new_console_window_seen"] for r in rows),
            "exit_codes": [r["driver_result"].get("results", {}).get("normal", {}).get("exitCode") for r in rows],
            "stdout_ok": [
                "PROBE-OK" in str(r["driver_result"].get("results", {}).get("normal", {}).get("stdout") or "")
                for r in rows
            ],
            "timeout_timedOut": [r["driver_result"].get("results", {}).get("timeout", {}).get("timedOut") for r in rows],
            "cmd_stdout_ok": [
                "CMD-OK" in str(r["driver_result"].get("results", {}).get("cmd", {}).get("stdout") or "")
                for r in rows
            ],
        }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
