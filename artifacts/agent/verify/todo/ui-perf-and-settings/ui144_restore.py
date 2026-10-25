"""task-144 ⑥ 真机时间线：最小化 → 恢复（OS 帧 + 页面内 10ms 采样）。

输出：restore-<label>.json，含
  · os: 恢复后第一帧非黑（窗口背景色出现）耗时 / 首帧"非背景像素"（内容/logo 出现）耗时
  · page: visibility 变可见时间 / 首个文档就绪 / booting 动画结束 / dock 宽度是否在恢复时被动画
用法：python ui144_restore.py <label>
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t144r"
CDP_PORT = 9613
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
PIL_PY = r"D:\deepseek-harness\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
SERIES = HERE / "os_series.py"

u32 = ctypes.WinDLL("user32")
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]


def find_hwnd():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, buf, 256)
        if "Memoria" in buf.value and u32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2); return True
    except Exception:  # noqa: BLE001
        return False


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": p.stderr[-400:]}]


def ev(expr):
    r = probe([{"action": "eval", "expr": expr}])[0]
    return r.get("value") if isinstance(r, dict) else None


def ctl(payload):
    ack = WORK / "ack.json"
    try: ack.unlink()
    except OSError: pass
    payload = dict(payload); payload["_seq"] = time.time_ns()
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(60):
        if ack.is_file():
            try: return json.loads(ack.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.1)
    return {"ok": False}


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "after"
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    cfg = WORK / "cfg"
    if cfg.exists(): shutil.rmtree(cfg)
    os.makedirs(cfg, exist_ok=True)
    for f in ("cmd.json", "ack.json", "probe-cmd.json"):
        try: (WORK / f).unlink()
        except OSError: pass
    env = dict(os.environ)
    env.update({"T93_WORK": str(WORK), "T93_CDP_PORT": str(CDP_PORT), "MEMORIA_CONFIG_DIR": str(cfg),
                "MEMORIA_KB": str(kb), "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8"})
    env.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    out = (WORK / f"app-{label}.out.log").open("w", encoding="utf-8")
    err = (WORK / f"app-{label}.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    shoot_dir = WORK / f"series-{label}"
    if shoot_dir.exists(): shutil.rmtree(shoot_dir)
    res = {"label": label}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(6)
        ctl({"op": "foreground"})
        time.sleep(0.8)
        ev("(() => { window.__OPEN = 'pending'; window.MemoriaApp.openFile('README.md').then(function (r) { window.__OPEN = (r && r.status) || 'done'; }, function (e) { window.__OPEN = 'err:' + e; }); return 'started'; })()")
        for _ in range(150):
            if ev("window.__OPEN") not in ("pending", None): break
            time.sleep(0.2)
        time.sleep(1.5)
        # 页面内 10ms 采样器（wall clock：Date.now()）
        ev("""(() => {
          window.__REST = { samples: [], vis: [] };
          document.addEventListener('visibilitychange', function () {
            window.__REST.vis.push({ t: Date.now(), hidden: document.hidden });
          }, true);
          window.__REST.iv = setInterval(function () {
            const dock = document.getElementById('-agent-dock');
            const root = document.documentElement;
            window.__REST.samples.push({
              t: Date.now(), hidden: document.hidden,
              dockW: dock ? Math.round(dock.getBoundingClientRect().width) : null,
              noTrans: root.classList.contains('-no-transition'),
              booting: root.classList.contains('-booting'),
              path: !!(window.state && window.state.currentPath),
              blocks: document.querySelectorAll('#preview .-src-block').length,
            });
          }, 10);
          return true;
        })()""")
        hwnd = None
        for _ in range(40):
            hwnd = find_hwnd()
            if hwnd:
                break
            time.sleep(0.25)
        res["hwnd"] = hwnd
        # 启动 OS 连续截图（独立进程，4s）
        shoot = subprocess.Popen([PIL_PY, str(SERIES), str(shoot_dir), "4200", "40"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.7)
        # 最小化 → 等 900ms → 恢复（记录恢复瞬间 wall clock）
        ctypes.windll.user32.ShowWindow(hwnd, 6)   # SW_MINIMIZE
        time.sleep(0.9)
        t0 = time.time()
        res["t0"] = t0
        ctl({"op": "foreground"})    # 既有 foregound 能力：恢复 + 置前
        time.sleep(1.8)
        # 读页面采样
        page = ev("(() => { clearInterval(window.__REST.iv); return window.__REST; })()")
        res["page"] = page
        try:
            so, se = shoot.communicate(timeout=30)
            res["osSeries"] = json.loads((shoot_dir / "series.json").read_text(encoding="utf-8"))
            res["osSeriesDir"] = str(shoot_dir)
        except Exception as e:  # noqa: BLE001
            res["osSeriesError"] = str(e)
        # 分析
        frames = res.get("osSeries") or []
        after = [f for f in frames if f.get("t", 0) >= (res["t0"] - 0.02)]
        res["osTimeline"] = {
            "first_non_black_ms": next((round((f["t"] - res["t0"]) * 1000) for f in after if f.get("near_black", 1) < 0.5), None),
            "first_bg_colored_ms": next((round((f["t"] - res["t0"]) * 1000) for f in after
                                        if f.get("bg") and f["bg"] != [0, 0, 0] and f.get("near_black", 1) < 0.9), None),
            "first_non_bg_pixels_ms": next((round((f["t"] - res["t0"]) * 1000) for f in after if f.get("non_bg", 0) > 0.02), None),
            "frames_after": len(after),
        }
        smp = page.get("samples") or []
        vis_t = next((s["t"] for s in smp if not s["hidden"] and s["t"] >= res["t0"] * 1000 - 20), None)
        res["pageTimeline"] = {
            "visible_after_ms": (round(vis_t - res["t0"] * 1000) if vis_t else None),
            "content_ready_ms": next((round(s["t"] - res["t0"] * 1000) for s in smp if s.get("path") and s["t"] >= res["t0"] * 1000), None),
            "booting_gone_ms": next((round(s["t"] - res["t0"] * 1000) for s in smp if not s.get("booting") and s["t"] >= res["t0"] * 1000), None),
            "dock_widths_after_visible": sorted({s["dockW"] for s in smp if s["t"] >= res["t0"] * 1000 and s["dockW"] is not None}),
            "no_transition_seen": any(s.get("noTrans") for s in smp if s["t"] >= res["t0"] * 1000),
        }
        (HERE / f"restore-{label}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"os": res["osTimeline"], "page": res["pageTimeline"]}, ensure_ascii=False, indent=1))
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
