"""快速判定：本机 WebView2 是否渲染原生 title tooltip（用顶栏已有 title 的按钮做对照）。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t136_probe"
CDP_PORT = 9583
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = TOOLS / "probe.mjs"
BUNDLED_PY = Path(r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe")


def ctl(payload: dict) -> dict:
    ack = WORK / "ack.json"
    try:
        ack.unlink()
    except OSError:
        pass
    payload = dict(payload)
    payload["_seq"] = time.time_ns()
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(80):
        try:
            if ack.is_file():
                d = json.loads(ack.read_text(encoding="utf-8"))
                if d.get("req") == payload:
                    return d
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
    return {"ok": False}


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else []


def ev(expr):
    return probe([{"action": "eval", "expr": expr}])[0].get("value")


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    for pid in subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*0.4.7-task-93-responsive*launch_ctl.py*' }).ProcessId"], capture_output=True, text=True).stdout.split():
        if pid.strip().isdigit():
            subprocess.run(["taskkill", "/PID", pid.strip(), "/F"], capture_output=True)
    for d in ("kb", "cfg"):
        if (WORK / d).exists():
            shutil.rmtree(WORK / d)
    os.makedirs(WORK / "cfg", exist_ok=True)
    shutil.copytree(REPO / "tests" / "probe-kb", WORK / "kb")
    env = dict(os.environ)
    env.update({"T93_WORK": str(WORK), "T93_CDP_PORT": str(CDP_PORT), "MEMORIA_CONFIG_DIR": str(WORK / "cfg"), "MEMORIA_KB": str(WORK / "kb"), "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8"})
    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    try:
        for _ in range(120):
            try:
                import urllib.request

                urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        time.sleep(6)
        ctl({"op": "foreground"})
        origin = ctl({"op": "clientorigin"})
        # 找一个顶栏带 title 的元素
        info = ev("""(() => {
          const els = [...document.querySelectorAll('[title]')].filter(e => e.offsetParent);
          const e = els[0];
          if (!e) return null;
          const r = e.getBoundingClientRect();
          return { id: e.id, title: e.getAttribute('title'), rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) } };
        })()""")
        print("target:", json.dumps(info, ensure_ascii=False))
        if not info:
            return 2
        r = info["rect"]
        sx = origin["x"] + r["x"] + r["w"] // 2
        sy = origin["y"] + r["y"] + r["h"] // 2
        ctl({"op": "hover", "x": sx, "y": sy})
        time.sleep(2.0)
        print("tooltips:", json.dumps(ctl({"op": "tooltips", "needles": [info["title"] or "x"]}), ensure_ascii=False)[:500])
        win = ctl({"op": "foreground"})["rect"]
        img = WORK / "tooltip_probe.png"
        subprocess.run([str(BUNDLED_PY), str(HERE / "grab.py"), str(win["x"]), str(win["y"]), str(win["w"]), str(win["h"]), str(img)], capture_output=True)
        print("shot:", img, img.stat().st_size if img.exists() else None, "cursor", sx, sy)
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
