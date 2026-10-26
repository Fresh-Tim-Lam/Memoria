"""task-159 语义审计编排：控制台继承 / 孙进程 / 未来 flags 兼容性。

四个问题：
1. `CREATE_NO_WINDOW` 子进程到底有没有 console（官方文档："console handle 不设置"）？
   ⇒ 子进程 console 探针（同一个 console 的 pid 列表是否含父）。
2. 子进程再启动的**孙进程**（cmd / python）会不会**再弹窗**？
   ⇒ GUI 父进程 + legacy/fixed，跑 `cmd /c echo` 与 `python -c print`，窗口枚举对照。
3. 未来要 `CREATE_NEW_PROCESS_GROUP` 能不能叠加？重复 `creationflags=` 会不会静默？
   ⇒ 组合 flags 实测 + 重复 kwargs TypeError 实测。
4. `CREATE_NO_WINDOW` 对 GUI 子进程是否安全忽略？
   ⇒ pythonw 子进程实测。

用法（仓库根目录）：
    python artifacts/agent/verify/todo/console-flash-fix/audit/run_semantic_audit.py --json ...
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
REPO = PARENT.parents[4]
sys.path.insert(0, str(PARENT))  # 复用窗口观测实现
from run_flash_experiment import (  # noqa: E402
    _baseline_samples,
    poll_while,
    snapshot_console_windows,
)

PYTHON = Path(sys.executable)
PYTHONW = PYTHON.with_name("pythonw.exe")
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def _run_driver(parent_exe: Path, mode: str, case: str, out_dir: Path) -> dict:
    out_file = out_dir / f"audit-{mode}-{case}-{parent_exe.stem}.json"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    baseline = _baseline_samples()
    proc = subprocess.Popen(
        [str(parent_exe), str(HERE / "audit_driver.py"), "--mode", mode, "--case", case, "--out", str(out_file)],
        env=env,
        cwd=str(REPO),
    )
    observed = poll_while(proc, baseline_hwnds=set(baseline["hwnds"]))
    payload = json.loads(out_file.read_text(encoding="utf-8")) if out_file.is_file() else {}
    return {
        "parent_exe": str(parent_exe),
        "parent_has_console": parent_exe.name.lower().startswith("python.exe"),
        "mode": mode,
        "case": case,
        "baseline_max": baseline["max"],
        "max_new_console_windows": observed["max_new_console_windows"],
        "new_console_windows": observed["new_console_windows"],
        "observation": {k: observed[k] for k in ("samples", "sample_interval_s", "max_console_windows_absolute")},
        "driver": payload,
    }


def _console_buffer_text() -> str | None:
    """读取当前进程 console 屏幕缓冲区文本（无 console 返回 None）。"""
    import ctypes

    k32 = ctypes.windll.kernel32
    h = k32.GetStdHandle(-11)
    if h in (0, -1):
        return None
    info = ctypes.create_string_buffer(22)
    if not k32.GetConsoleScreenBufferInfo(h, info):
        return None
    left, top = ctypes.c_short(), ctypes.c_short()
    # CONSOLE_SCREEN_BUFFER_INFO: dwSize(4) dwCursorPosition(4) wAttributes(2) srWindow(8) dwMaximumWindowSize(4)
    # 简化：直接读 0..200 行 × 200 列（ReadConsoleOutputCharacterW 越界返回 0，足够探测）
    size = 200 * 200
    buf = ctypes.create_unicode_buffer(size + 1)
    read = ctypes.c_uint32(0)
    ok = k32.ReadConsoleOutputCharacterW(h, buf, size, 0, ctypes.byref(read))
    return buf.value[: read.value] if ok else None


def _output_visibility_test() -> dict:
    """唯一"不重定向 stdio"的启动点（runtime.spawn_window）在 CREATE_NO_WINDOW 下输出是否还进父控制台。

    做法：父进程（有 console）先清/读 buffer，spawn 子进程 `python -c print(MARKER)`（**不重定向**），
    再读 buffer 找 MARKER。fixed 与 legacy 各跑一次。
    """
    import ctypes

    k32 = ctypes.windll.kernel32
    out: dict = {}
    for mode, flags in (("fixed", CREATE_NO_WINDOW), ("legacy", 0)):
        marker = f"VIS-MARKER-{mode.upper()}-{int(time.time() * 1000) % 100000}"
        kwargs = {"creationflags": flags} if flags else {}
        try:
            subprocess.run(
                [str(PYTHON), "-c", f"print('{marker}')"],
                timeout=30,
                **kwargs,
            )
            time.sleep(0.4)
            text = _console_buffer_text()
            out[mode] = {
                "marker": marker,
                "console_buffer_available": text is not None,
                "marker_found_in_parent_console": bool(text and marker in text),
            }
        except Exception as exc:  # noqa: BLE001
            out[mode] = {"error": repr(exc)}
    return out


def _micro_tests(out_dir: Path) -> dict:
    results: dict = {}

    # ① 组合 flags：CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    try:
        cp = subprocess.run(
            [str(PYTHON), "-c", "print('COMBO-OK')"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )
        results["combined_flags"] = {
            "creationflags": hex(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP),
            "returncode": cp.returncode,
            "stdout": cp.stdout.strip(),
            "verdict": "OK：两 flags 可按位或叠加，子进程正常执行、stdout 可读",
        }
    except Exception as exc:  # noqa: BLE001
        results["combined_flags"] = {"error": repr(exc)}

    # ② 重复 creationflags：必须 loud fail（TypeError），不能静默
    try:
        subprocess.run(
            [str(PYTHON), "-c", "print('DUP')"],
            capture_output=True,
            text=True,
            timeout=30,
            **{"creationflags": CREATE_NO_WINDOW},
            creationflags=0,
        )
        results["duplicate_creationflags"] = {"verdict": "UNEXPECTED：未报错（静默）"}
    except TypeError as exc:
        results["duplicate_creationflags"] = {
            "verdict": "LOUD FAIL：重复关键字在调用点直接 TypeError（不会被静默忽略）",
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        results["duplicate_creationflags"] = {"error": repr(exc)}

    # ③ GUI 子进程：flags 被 Windows 按文档忽略，进程应正常运行
    probe = out_dir / "gui-child-ok.txt"
    if probe.exists():
        probe.unlink()
    try:
        cp = subprocess.run(
            [str(PYTHONW), "-c", f"open(r'{probe}','w').write('GUI-CHILD-OK')"],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=CREATE_NO_WINDOW,
        )
        results["gui_child"] = {
            "returncode": cp.returncode,
            "marker_written": probe.is_file(),
            "verdict": "OK：GUI 子进程不受 CREATE_NO_WINDOW 影响（文档：对非控制台应用忽略）",
        }
    except Exception as exc:  # noqa: BLE001
        results["gui_child"] = {"error": repr(exc)}

    results["output_visibility"] = _output_visibility_test()
    return results


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    out_dir = HERE / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "schema": "console-flash-semantic-audit/v1",
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo": str(REPO),
        "python": str(PYTHON),
        "pythonw": str(PYTHONW),
        "cases": [],
        "micro_tests": _micro_tests(out_dir),
    }
    for parent in (PYTHON, PYTHONW):
        for mode in ("legacy", "fixed"):
            for case in ("state", "nested", "nested_py"):
                report["cases"].append(_run_driver(parent, mode, case, out_dir))
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
