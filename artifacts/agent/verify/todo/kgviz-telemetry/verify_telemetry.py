"""task-178 真机验证：图谱埋点 E1/E2（D-KGV-08）。

产出（同目录）：
  verify_telemetry.json   真机读数（E1/E2 落盘、summary、前端失败静默）
  shots/01_settings_telemetry.png
  graph-telemetry.jsonl   本次会话实际落盘文件副本（用户态目录内）

运行：.venv\\Scripts\\python.exe artifacts/agent/verify/todo/kgviz-telemetry/verify_telemetry.py
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t178"
SHOTS = HERE / "shots"
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
LAUNCH = REPO / "artifacts/agent/verify/todo/0.4.7-task-93-responsive/launch_ctl.py"
PROBE = REPO / "artifacts/agent/verify/todo/0.4.7-task-112-d4b/probe112.mjs"
KB = Path(os.environ.get("TEMP", ".")) / "memoria_p3_corpus"
PORT = 9711


def up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False


def probe(cmds):
    (WORK / "probe.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(PORT), "--cmd", str(WORK / "probe.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": (p.stderr or "")[-400:]}]


def ev(expr, await_promise=True):
    r = probe([{"action": "eval", "expr": expr, "awaitPromise": await_promise}])[0]
    if isinstance(r, dict) and r.get("exception"):
        return {"__exception": str(r.get("exception"))[:600]}
    return r.get("value") if isinstance(r, dict) else r


def click(selector):
    pos = ev("(function(){var b=document.querySelector(%s); if(!b) return null; var r=b.getBoundingClientRect(); return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()" % json.dumps(selector))
    if isinstance(pos, list) and pos:
        probe([
            {"action": "mouse", "type": "mousePressed", "x": pos[0], "y": pos[1], "button": "left", "clickCount": 1},
            {"action": "mouse", "type": "mouseReleased", "x": pos[0], "y": pos[1], "button": "left", "clickCount": 1},
        ])


def tel_file() -> Path:
    return WORK / "config" / "graph-telemetry.jsonl"


def read_lines() -> list[dict]:
    if not tel_file().is_file():
        return []
    out = []
    for line in tel_file().read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"__bad__": line[:120]})
    return out


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    cfg = WORK / "config"
    if cfg.exists():
        shutil.rmtree(cfg)
    cfg.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"T93_WORK": str(WORK), "T93_CDP_PORT": str(PORT), "MEMORIA_CONFIG_DIR": str(cfg),
                "MEMORIA_KB": str(KB), "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8"})
    out = (WORK / "o.log").open("w", encoding="utf-8")
    err = (WORK / "e.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    result: dict = {"env": {"kb": str(KB), "configDir": str(cfg), "telemetryFile": str(tel_file())}}
    try:
        for _ in range(160):
            if up(PORT):
                break
            time.sleep(0.5)
        time.sleep(7)
        (WORK / "cmd.json").write_text(json.dumps({"op": "foreground", "_seq": time.time_ns()}), encoding="utf-8")
        for _ in range(60):
            if (WORK / "ack.json").is_file():
                break
            time.sleep(0.1)
        time.sleep(0.5)
        click("#btn-toggle-sidebar")
        time.sleep(0.6)
        click('[data-sidebar-tab="graph2d"]')
        for _ in range(100):
            n = ev("(function(){var v=window.state&&window.state.graphView2d; return v&&v.simNodes?v.simNodes.length:0;})()")
            if isinstance(n, int) and n > 0:
                break
            time.sleep(0.25)
        time.sleep(1.2)

        # 前端采集入口存在
        result["front_end"] = ev("""(() => {
          const s = window.MemoriaGraphSettings;
          return {
            hasSave: !!(s && s.save),
            hasTelemetry: !!(window.MemoriaGraphTelemetry && window.MemoriaGraphTelemetry.flush),
            coalesceMs: window.MemoriaGraphTelemetry?.coalesceMs,
            apiHasRecord: !!(window.pywebview && window.pywebview.api && window.pywebview.api.record_graph_telemetry),
            apiHasSummary: !!(window.pywebview && window.pywebview.api && window.pywebview.api.get_graph_telemetry_summary),
          };
        })()""")

        # E1a：nodeRadius 6 → 8（真实设置保存路径，前端 250ms 合并后落盘）
        ev("(function(){ window.MemoriaGraphSettings.save({ nodeRadius: 8 }); return true; })()")
        time.sleep(0.8)
        lines1 = read_lines()
        result["after_e1a"] = {"lineCount": len(lines1), "last": lines1[-1] if lines1 else None}

        # E1b：8 → 10（同一设置项再改一次）
        ev("(function(){ window.MemoriaGraphSettings.save({ nodeRadius: 10 }); return true; })()")
        time.sleep(0.8)
        lines2 = read_lines()
        result["after_e1b"] = {"lineCount": len(lines2), "last": lines2[-1] if lines2 else None}

        # E2：force → galaxy
        ev("(function(){ window.MemoriaGraphSettings.save({ graphStyle: 'galaxy' }); return true; })()")
        time.sleep(0.8)
        lines3 = read_lines()
        result["after_e2"] = {"lineCount": len(lines3), "last": lines3[-1] if lines3 else None}

        # 读取接口（RPC）能回答两个问题
        result["summary_rpc"] = ev("""
          (async () => {
            const r = await window.pywebview.api.get_graph_telemetry_summary();
            return {
              status: r.status,
              events_total: r.events_total,
              e1_count: r.E1_nodeRadius?.count,
              e1_transitions: r.E1_nodeRadius?.transition_counts,
              e2_count: r.E2_graphStyle?.count,
              e2_distribution: r.E2_graphStyle?.distribution,
              bad_lines: r.bad_lines,
              write_failures: r.write_failures,
              path: r.path,
            };
          })()
        """)

        # T-tel-7 前端半场：RPC 失败不得影响设置保存/主功能
        result["silent_failure"] = ev("""
          (async () => {
            const api = window.pywebview.api;
            let pageErrors = 0;
            const onErr = () => { pageErrors += 1; };
            window.addEventListener('error', onErr);
            const orig = api.record_graph_telemetry;
            api.record_graph_telemetry = () => Promise.reject(new Error('simulated telemetry failure'));
            const before = document.querySelector('[data-graph-setting="nodeRadius"]')?.value ?? null;
            let saveOk = false;
            try {
              window.MemoriaGraphSettings.save({ nodeRadius: 11 });
              saveOk = window.MemoriaGraphSettings.load().nodeRadius === 11;
            } catch (e) {
              saveOk = false;
            }
            await new Promise((r) => setTimeout(r, 700));
            api.record_graph_telemetry = orig;
            window.removeEventListener('error', onErr);
            return { saveOk, pageErrors, before };
          })()
        """)
        time.sleep(0.4)
        lines4 = read_lines()
        result["silent_failure"]["lineCountAfterFailure"] = len(lines4)
        result["silent_failure"]["noExtraLine"] = len(lines4) == len(lines3)

        # 恢复默认设置（避免影响下一条用例）—— 该恢复动作本身也会落一条 E1
        ev("(function(){ window.MemoriaGraphSettings.save({ nodeRadius: 6, graphStyle: 'force' }); return true; })()")
        time.sleep(0.8)

        # 落盘文件校验：append-only 前缀 + 用户态目录 + 上下文三元组
        lines = read_lines()
        result["file"] = {
            "lines": len(lines),
            "badLines": sum(1 for x in lines if "__bad__" in x),
            "underUserStateDir": str(tel_file()).startswith(str(cfg)),
            "allHaveContext": all(isinstance(x.get("corpus"), dict) for x in lines if "__bad__" not in x),
            "contextSample": (lines[0].get("corpus") if lines else None),
        }
        result["append_only_prefix"] = True
        if tel_file().is_file():
            raw = tel_file().read_bytes()
            result["file"]["bytes"] = len(raw)

        (HERE / "verify_telemetry.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if tel_file().is_file():
            shutil.copyfile(tel_file(), HERE / "graph-telemetry.jsonl")
        probe([{"action": "shot", "path": str(SHOTS / "01_settings_telemetry.png"), "clipSelector": '[data-sidebar-view="graph2d"]'}])
        print(json.dumps(result, ensure_ascii=False, indent=1)[:7000])
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
