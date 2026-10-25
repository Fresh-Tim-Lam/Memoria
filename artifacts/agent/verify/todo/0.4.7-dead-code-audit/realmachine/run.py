"""task-134 真机验证编排器：种子 → 桩端点 → 真实应用（CDP）→ 拖入 .txt 资源链路 → 判定。

用法：
  python run.py before   # 修复前：记录用户可见故障（"只支持图片"、无 chip、后端无文件）
  python run.py after    # 修复后：验证 ①–⑥ 全链路

隔离：独立 MEMORIA_CONFIG_DIR / KB（tests/probe-kb 副本），不碰用户配置、用户 app、docs/example。
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]
T133 = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-91-realmachine"
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t134"
CDP_PORT = int(os.environ.get("T134_CDP_PORT", "9587"))
STUB_PORT = int(os.environ.get("T134_STUB_PORT", "9599"))
PY = str(REPO / ".venv" / "Scripts" / "python.exe")


def log(msg: str) -> None:
    print("[t134] " + msg, flush=True)


def wait_cdp(timeout_s: float = 120.0) -> dict:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=3) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"CDP 未就绪：{last}")


def ps(cmd: str) -> str:
    p = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def find_our_app() -> list[int]:
    out = ps("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*0.4.7-task-91-realmachine*launch_app.py*' } | Select-Object -ExpandProperty ProcessId")
    return [int(x) for x in re.findall(r"\d+", out)]


def kill_our_app() -> list[str]:
    killed = []
    for pid in find_our_app():
        cmd = ps(f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine")
        if "0.4.7-task-91-realmachine" not in cmd or "launch_app.py" not in cmd:
            killed.append(f"skip {pid}")
            continue
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        killed.append(f"killed {pid}")
    time.sleep(1.5)
    out = ps(
        "Get-CimInstance Win32_Process -Filter \"Name='msedgewebview2.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*--remote-debugging-port={CDP_PORT}*' }} | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.ExecutablePath)|$($_.CommandLine)\" }"
    )
    for line in [x for x in out.splitlines() if x.strip()]:
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        pid_s, exe, cmd = parts
        if "Package\\Memoria.exe" in cmd or (exe and exe.lower().endswith("package\\memoria.exe")):
            continue
        subprocess.run(["taskkill", "/PID", pid_s.strip(), "/F"], capture_output=True)
        killed.append(f"webview {pid_s.strip()}")
    return killed


def main() -> int:
    phase = (sys.argv[1] if len(sys.argv) > 1 else "before").strip()
    assert phase in ("before", "after"), "phase must be before|after"
    for stale in find_our_app():
        log(f"清理遗留实例 {stale}")
    kill_our_app()

    env = dict(os.environ)
    env.update(
        {
            "T134_WORK": str(WORK),
            "T134_STUB_PORT": str(STUB_PORT),
            "T134_CDP_PORT": str(CDP_PORT),
            "T133_CDP_PORT": str(CDP_PORT),  # 复用 task-133 的 launch_app.py
            "MEMORIA_CONFIG_DIR": str(WORK / "cfg"),
            "MEMORIA_KB": str(WORK / "kb"),
            "MEMORIA_FRAMELESS": "0",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)

    seed = subprocess.run([PY, str(HERE / "seed.py")], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log("seed: " + (seed.stdout or "").strip())
    if seed.returncode != 0:
        log("seed failed: " + (seed.stderr or "")[-1200:])
        return 1

    os.environ.update(env)
    sys.path.insert(0, str(HERE))
    from stub_llm import serve_forever  # noqa: E402

    server = serve_forever(STUB_PORT)
    log(f"stub on 127.0.0.1:{STUB_PORT}; phase={phase}")

    out_log = (WORK / "app.out.log").open("w", encoding="utf-8")
    err_log = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(T133 / "launch_app.py")], cwd=str(REPO), env=env, stdout=out_log, stderr=err_log)
    log(f"app pid={proc.pid}")
    result: dict = {"phase": phase, "app_pid": proc.pid}
    try:
        ver = wait_cdp(150)
        result["cdp"] = ver.get("Browser")
        drive = subprocess.run(
            ["node", str(HERE / "drive.mjs"), "--port", str(CDP_PORT), "--out", str(HERE), "--phase", phase],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=420,
        )
        result["driver"] = {"rc": drive.returncode, "stdout": (drive.stdout or "").strip()[-1500:], "stderr": (drive.stderr or "").strip()[-2500:]}
        log("driver rc=" + str(drive.returncode))
        if drive.returncode != 0:
            log(drive.stderr[-1500:])
    finally:
        result["cleanup"] = kill_our_app()
        out_log.close()
        err_log.close()
        server.shutdown()

    # ── 证据收集 ────────────────────────────────────────────────
    read = lambda p: json.loads((HERE / p).read_text(encoding="utf-8")) if (HERE / p).is_file() else None  # noqa: E731
    seed_info = json.loads((WORK / "seed.json").read_text(encoding="utf-8"))
    drop = read(f"dom-drop-{phase}.json")
    removed = read(f"dom-removed-{phase}.json")
    sent = read(f"dom-sent-{phase}.json")
    stub_rows = []
    stub_file = WORK / "stub-requests.jsonl"
    if stub_file.is_file():
        stub_rows = [json.loads(x) for x in stub_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    res_dir = Path(seed_info["kb"]) / ".memoria" / "agent" / "attachments" / "resources"
    res_files = sorted(res_dir.glob("*")) if res_dir.is_dir() else []
    screenshots = sorted(p.name for p in HERE.glob(f"*-{phase}.png"))

    bad_type = "只支持" in (drop or {}).get("flashText", "") + (drop or {}).get("statusText", "") or "图片" in (drop or {}).get("flashText", "")
    checks = {
        "screenshots": len(screenshots) >= 2,
        "before_error_shown": (not bad_type) if phase == "after" else bad_type,
        "before_no_resource_chip": ((drop or {}).get("resChips", 0) == 0) if phase == "before" else True,
        "before_no_backend_file": (len(res_files) == 0) if phase == "before" else True,
        "after_chip_shown": ((drop or {}).get("resChips", 0) >= 1) if phase == "after" else True,
        "after_backend_file": (len(res_files) >= 1) if phase == "after" else True,
        "after_remove_works": ((removed or {}).get("resChips", 0) == 0) if phase == "after" else True,
        "after_note_injected": (any(r.get("has_resource_note") for r in stub_rows)) if phase == "after" else True,
        "after_chip_cleared_after_send": ((sent or {}).get("resChips", 0) == 0) if phase == "after" else True,
        "gpu_webgl": bool(((read(f"driver-{phase}.json") or {}).get("gpu") or {}).get("webgl")),
    }
    result.update(
        {
            "seed": seed_info,
            "drop_dom": drop,
            "removed_dom": removed,
            "sent_dom": sent,
            "stub_requests": stub_rows,
            "backend_resource_files": [p.name for p in res_files],
            "screenshots": screenshots,
            "checks": checks,
            "pass": all(checks.values()),
        }
    )
    (HERE / f"result-{phase}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print("phase:", phase, "| backend files:", result["backend_resource_files"])
    print("drop dom:", json.dumps({k: (drop or {}).get(k) for k in ("resChips", "chips", "statusText", "flashText", "stripHidden")}, ensure_ascii=False))
    print("stub has_resource_note:", [r.get("has_resource_note") for r in stub_rows])
    print("checks:", json.dumps(checks, ensure_ascii=False))
    print("PASS" if result["pass"] else "FAIL")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
