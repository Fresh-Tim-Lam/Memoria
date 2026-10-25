"""task-144 ⑥(a) 二轮复现：验证 Lead 假设「恢复时响应式联动重跑 ⇒ dock 先塌再展」。

真机：先把窗口 resize 到窄（dock 可能 auto-hide），再最小化→恢复；
页面内 8ms 采样：innerWidth / visibility / resize 事件时间 / dock class+inline width+rect / dockMetrics 三态。
输出 repro-restore-<scenario>.json。
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t144rr"
CDP_PORT = 9617
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
u32 = ctypes.WinDLL("user32")
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
MAXIMIZE_FLAG = [False]  # 场景开关：max 模式先 Win32 最大化再最小化/恢复（真人常见用法）


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
    for _ in range(80):
        if ack.is_file():
            try: return json.loads(ack.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.1)
    return {"ok": False}


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


INSTALL = """(() => {
  window.__RR = { events: [], samples: [] };
  ['resize', 'visibilitychange', 'focus', 'blur'].forEach(function (name) {
    window.addEventListener(name, function () {
      window.__RR.events.push({ t: Date.now(), name: name, w: window.innerWidth, h: window.innerHeight,
                                hidden: document.hidden });
    }, true);
  });
  window.__RR.iv = setInterval(function () {
    const dock = document.getElementById('-agent-dock');
    const m = window.MemoriaAgentPanel && window.MemoriaAgentPanel.dockMetrics
      ? window.MemoriaAgentPanel.dockMetrics() : null;
    window.__RR.samples.push({
      t: Date.now(), w: window.innerWidth, h: window.innerHeight, hidden: document.hidden,
      dockClass: dock ? String(dock.className || '') : null,
      dockStyleW: dock ? (dock.style.width || '') : null,
      dockW: dock ? Math.round(dock.getBoundingClientRect().width) : null,
      m: m ? { visible: m.visible, collapsed: m.collapsed, autoHidden: m.autoHidden,
               responsiveHidden: m.responsiveHidden, effectivePx: m.effectiveWidthPx,
               availablePx: m.availablePx } : null,
      booting: document.documentElement.classList.contains('-booting'),
      noTrans: document.documentElement.classList.contains('-no-transition'),
    });
  }, 8);
  return true;
})()"""


def scenario(name: str, w: int, h: int) -> dict:
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
    out = (WORK / f"app-{name}.out.log").open("w", encoding="utf-8")
    err = (WORK / f"app-{name}.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    res = {"scenario": name, "target": [w, h]}
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
        # 真实 OS 窗口 resize 到目标尺寸
        ctl({"w": w, "h": h})
        time.sleep(1.2)
        res["beforeRestore"] = ev("""(() => {
          const dock = document.getElementById('-agent-dock');
          const m = window.MemoriaAgentPanel && window.MemoriaAgentPanel.dockMetrics();
          return { w: window.innerWidth, h: window.innerHeight, dockClass: dock ? dock.className : null,
                   dockW: dock ? Math.round(dock.getBoundingClientRect().width) : null,
                   metrics: m ? { visible: m.visible, collapsed: m.collapsed, autoHidden: m.autoHidden,
                                  responsiveHidden: m.responsiveHidden, availablePx: m.availablePx } : null };
        })()""")
        time.sleep(0.3)
        ev(INSTALL)
        hwnd = None
        for _ in range(40):
            hwnd = find_hwnd()
            if hwnd:
                break
            time.sleep(0.25)
        res["hwnd"] = hwnd
        if MAXIMIZE_FLAG[0]:
            ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            time.sleep(1.0)
        ctypes.windll.user32.ShowWindow(hwnd, 6)
        time.sleep(1.0)
        t0 = time.time()
        res["t0"] = t0
        ctl({"op": "foreground"})
        time.sleep(1.8)
        data = ev("(() => { clearInterval(window.__RR.iv); return window.__RR; })()")
        res["events"] = data.get("events")
        res["samples"] = data.get("samples")
        smp = data.get("samples") or []
        vis = [s for s in smp if s["t"] >= t0 * 1000]
        res["afterSummary"] = {
            "innerWidths": sorted({s["w"] for s in vis}),
            "dockClasses": sorted({s["dockClass"] for s in vis}),
            "dockWidths": sorted({s["dockW"] for s in vis if s["dockW"] is not None}),
            "metrics_visible": sorted({bool(s["m"] and s["m"]["visible"]) for s in vis if s["m"]}),
            "metrics_autoHidden": sorted({bool(s["m"] and s["m"]["autoHidden"]) for s in vis if s["m"]}),
            "metrics_responsiveHidden": sorted({bool(s["m"] and s["m"]["responsiveHidden"]) for s in vis if s["m"]}),
            "hidden": sorted({s["hidden"] for s in vis}),
            "eventNames": [e["name"] for e in (data.get("events") or [])],
        }
        (HERE / f"repro-restore-{name}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"scenario": name, "before": res["beforeRestore"], "after": res["afterSummary"]},
                         ensure_ascii=False, indent=1))
        return res
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "narrow"
    if mode == "max":
        MAXIMIZE_FLAG[0] = True
        scenario("max", 0, 0)
    elif mode == "narrow":
        scenario("narrow", 1000, 700)
    else:
        scenario("wide", 1360, 860)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
