"""task-112 口径澄清：用**当前代码**真机重跑选区矩阵子集（copy/cut），与 0.4.5 的 79/146 对账。

真机：pywebview+WebView2 真实窗口；KB = artifacts/_selection_kb 的临时副本（冻结语料只读）；
隔离 MEMORIA_CONFIG_DIR；跑前把窗口切前台（task-136 harness 的 foreground 能力）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t112"
CDP_PORT = 9593
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
LAUNCH = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive" / "launch_ctl.py"


def http_up(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


def ctl(payload: dict) -> dict:
    ack = WORK / "ack.json"
    try:
        ack.unlink()
    except OSError:
        pass
    payload = dict(payload)
    payload["_seq"] = time.time_ns()
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(100):
        try:
            if ack.is_file():
                d = json.loads(ack.read_text(encoding="utf-8"))
                if d.get("req") == payload:
                    return d
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    return {"ok": False, "err": "ack timeout"}


def kill_ours() -> None:
    cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*0.4.7-task-93-responsive*launch_ctl.py*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for pid in re.findall(r"\d+", p.stdout or ""):
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    time.sleep(0.8)


def main() -> int:
    kill_ours()
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists():
        shutil.rmtree(kb)
    shutil.copytree(REPO / "artifacts" / "_selection_kb", kb)
    cfg = WORK / "cfg"
    if cfg.exists():
        shutil.rmtree(cfg)
    os.makedirs(cfg, exist_ok=True)
    for f in ("cmd.json", "ack.json"):
        try:
            (WORK / f).unlink()
        except OSError:
            pass
    env = dict(os.environ)
    env.update(
        {
            "T93_WORK": str(WORK),
            "T93_CDP_PORT": str(CDP_PORT),
            "MEMORIA_CONFIG_DIR": str(cfg),
            "MEMORIA_KB": str(kb),
            "MEMORIA_FRAMELESS": "0",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    print("app pid", proc.pid)
    try:
        for _ in range(160):
            if http_up(f"http://127.0.0.1:{CDP_PORT}/json/version"):
                break
            time.sleep(0.5)
        time.sleep(6)
        fg = ctl({"op": "foreground"})
        print("foreground:", json.dumps(fg, ensure_ascii=False)[:300])
        args = [
            PY,
            str(REPO / "scripts" / "benchmark" / "surface" / "run_selection.py"),
            "--label", sys.argv[1] if len(sys.argv) > 1 else "task112-real-fg",
            "--cdp-port", str(CDP_PORT),
            "--only", sys.argv[2] if len(sys.argv) > 2 else "paragraph,heading",
            "--only-ops", sys.argv[3] if len(sys.argv) > 3 else "copy,cut",
        ]
        p = subprocess.run(args, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        print((p.stdout or "")[-1500:])
        print("stderr:", (p.stderr or "")[-500:])
        print("exit:", p.returncode)
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
        kill_ours()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
