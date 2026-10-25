"""task-144 ① 基线/对比：侧栏 & dock 展缩 transition 期间的帧时间（长文档 / 普通文档）。

口径：页面内 requestAnimationFrame 间隔（ms）+ PerformanceObserver longtask。
每次：真实鼠标点击顶栏按钮（#btn-toggle-sidebar / #btn-agent）→ 采样 700ms → 统计
  frames / mean / p95 / max / >33ms 掉帧数 / longtasks。
用法：python ui144_measure.py <label>   （结果写 frames-<label>.json）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t144"
CDP_PORT = 9611
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"


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


def click_center(selector: str):
    pt = ev(f"""(() => {{
      const el = document.querySelector({json.dumps(selector)});
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {{ x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }};
    }})()""")
    if not pt:
        return None
    probe([{"action": "mouse", "type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1},
           {"action": "mouse", "type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1}])
    return pt


SAMPLER = """(() => {
  window.__FR = { times: [], on: true, longtasks: [], t0: performance.now() };
  try {
    if (window.__LTO) { try { window.__LTO.disconnect(); } catch (_) {} }
    window.__LTO = new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (e) { window.__FR.longtasks.push(Math.round(e.duration * 10) / 10); });
    });
    window.__LTO.observe({ entryTypes: ['longtask'] });
  } catch (e) { window.__FR.longtaskErr = String(e); }
  (function loop(t) { window.__FR.times.push(t); if (window.__FR.on) requestAnimationFrame(loop); })(performance.now());
  return true;
})()"""

STOP = """(() => {
  window.__FR.on = false;
  try { if (window.__LTO) window.__LTO.disconnect(); } catch (_) {}
  const ts = window.__FR.times;
  const iv = [];
  for (let i = 1; i < ts.length; i++) iv.push(ts[i] - ts[i - 1]);
  function st(arr, p) {
    if (!arr.length) return null;
    const s = arr.slice().sort(function (a, b) { return a - b; });
    const idx = Math.min(s.length - 1, Math.max(0, Math.ceil(p * s.length) - 1));
    return Math.round(s[idx] * 100) / 100;
  }
  const mean = iv.length ? iv.reduce(function (a, b) { return a + b; }, 0) / iv.length : 0;
  return { frames: ts.length, intervals: iv.map(function (x) { return Math.round(x * 100) / 100; }),
           mean: Math.round(mean * 100) / 100, p50: st(iv, 0.5), p95: st(iv, 0.95),
           max: st(iv, 1), over33: iv.filter(function (x) { return x > 33.4; }).length,
           over25: iv.filter(function (x) { return x > 25; }).length,
           longtasks: window.__FR.longtasks, longtaskErr: window.__FR.longtaskErr || null };
})()"""


def open_doc(fname: str) -> dict:
    ev(f"(() => {{ window.__OPEN = 'pending'; window.MemoriaApp.openFile({json.dumps(fname)}).then(function (r) {{ window.__OPEN = (r && r.status) || 'done'; }}, function (e) {{ window.__OPEN = 'err:' + e; }}); return 'started'; }})()")
    for _ in range(200):
        if ev("window.__OPEN") not in ("pending", None):
            break
        time.sleep(0.2)
    # 等预览块数量稳定
    last = -1
    for _ in range(120):
        n = ev("document.querySelectorAll('#preview .-src-block').length")
        if isinstance(n, (int, float)) and n == last and n > 0:
            break
        last = n
        time.sleep(0.25)
    time.sleep(1.0)
    return ev("""(() => ({
      blocks: document.querySelectorAll('#preview .-src-block').length,
      bodyChars: ((window.state && window.state.doc && window.state.doc.body) || '').length,
      view: window.state && window.state.viewMode,
    }))()""")


def measure(kind: str, cycles: int) -> list:
    sel = "#btn-toggle-sidebar" if kind == "sidebar" else "#btn-agent"
    out = []
    for i in range(cycles):
        ev(SAMPLER)
        pt = click_center(sel)
        time.sleep(0.75)
        st = ev(STOP)
        st["click"] = pt
        out.append(st)
        time.sleep(0.45)
    return out


def summarize(name: str, runs: list) -> dict:
    ok = [r for r in runs if r and r.get("frames")]
    frames = sum(r["frames"] for r in ok)
    over33 = sum(r["over33"] for r in ok)
    over25 = sum(r["over25"] for r in ok)
    all_iv = [x for r in ok for x in (r.get("intervals") or [])]
    all_iv.sort()

    def pct(p):
        return all_iv[min(len(all_iv) - 1, max(0, int(len(all_iv) * p)))] if all_iv else None

    lat = [d for r in ok for d in (r.get("longtasks") or [])]
    return {"name": name, "cycles": len(ok), "frames": frames,
            "over33": over33, "over25": over25,
            "over33PerCycle": round(over33 / len(ok), 2) if ok else None,
            "meanInterval": round(sum(all_iv) / len(all_iv), 2) if all_iv else None,
            "p50": pct(0.5), "p95": pct(0.95), "max": all_iv[-1] if all_iv else None,
            "longtasks": lat[:20], "longtaskCount": len(lat),
            "runs": ok}


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "before"
    mode = sys.argv[2] if len(sys.argv) > 2 else "frames"
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "kb"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(REPO / "tests" / "probe-kb", kb)
    # 长文档 fixture：~1800 段落 + 若干块（约 4k 块）
    big = ["# Big doc", ""]
    for i in range(1800):
        big.append(f"P{i} word{i}a word{i}b word{i}c")
        big.append("")
    (kb / "big.md").write_text("\n".join(big), encoding="utf-8")
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
    res = {"label": label, "mode": mode, "long": {}, "normal": {}}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(6)
        ctl({"op": "foreground"})
        time.sleep(0.8)
        if mode == "frames":
            res["long"]["doc"] = open_doc("big.md")
            res["long"]["sidebar"] = summarize("long/sidebar", measure("sidebar", 5))
            res["long"]["dock"] = summarize("long/dock", measure("dock", 5))
            res["normal"]["doc"] = open_doc("README.md")
            res["normal"]["sidebar"] = summarize("normal/sidebar", measure("sidebar", 4))
            res["normal"]["dock"] = summarize("normal/dock", measure("dock", 4))
        elif mode == "normal":
            # 只测普通文档（fresh app，避免"先开大文档再开普通文档"的重载干扰）
            res["normal"]["doc"] = open_doc("README.md")
            res["normal"]["sidebar"] = summarize("normal/sidebar", measure("sidebar", 5))
            res["normal"]["dock"] = summarize("normal/dock", measure("dock", 5))
        (HERE / f"frames-{label}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        for scope in ("long", "normal"):
            for kind in ("sidebar", "dock"):
                s = res[scope].get(kind)
                if s:
                    print(f"[{scope}/{kind}] frames={s['frames']} over33/cycle={s['over33PerCycle']} "
                          f"mean={s['meanInterval']} p95={s['p95']} max={s['max']} longtasks={s['longtaskCount']}")
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
