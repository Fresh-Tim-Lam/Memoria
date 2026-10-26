"""task-187 真机验证：毛球态判定（D-KGV-09）+ T-double（D-KGV-15）。

产出（同目录）：
  verify_hairball_tdouble.json
  shots/01_graph2d_galaxy_tdouble.png

运行：.venv\\Scripts\\python.exe artifacts/agent/verify/todo/kgviz-hairball-tdouble/verify_hairball_tdouble.py
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t187"
SHOTS = HERE / "shots"
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
LAUNCH = REPO / "artifacts/agent/verify/todo/0.4.7-task-93-responsive/launch_ctl.py"
PROBE = REPO / "artifacts/agent/verify/todo/0.4.7-task-112-d4b/probe112.mjs"
KB = REPO / "docs" / "example" / "AAA_Vocab"
PORT = 9721


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
    result: dict = {"env": {"kb": str(KB), "port": PORT}}
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
        time.sleep(1.5)

        # 1) 真实语料毛球态（生产 engine 路径）
        result["hairball_real"] = ev("""(() => {
          const e = window.state.graphEngine;
          const r = e && e.hairballReport ? e.hairballReport() : null;
          return r ? {
            isHairball: r.isHairball,
            rule: r.rule,
            threshold: r.threshold,
            metrics: r.metrics,
            calibration: r.calibration,
            engineMethod: typeof e.hairballReport === 'function',
          } : null;
        })()""")

        # 2) 合成语料双向验证（同一生产 engine，构造 good / hairball 两个 payload）
        result["hairball_synthetic"] = ev("""(() => {
          const Engine = window.MemoriaGraphEngine;
          function ringLinks(n, start, links) {
            for (let i = 0; i < n; i++) links.push({ source_id: "n" + (start + i), targets: ["n" + (start + ((i + 1) % n))], type: "reference" });
          }
          function build(sizes) {
            const nodes = [], edges = []; let base = 0;
            for (const size of sizes) {
              for (let i = 0; i < size; i++) nodes.push({ id: "n" + (base + i), name: "n" + (base + i) });
              for (let i = 0; i < size; i++) edges.push({ source_id: "n" + (base + i), targets: ["n" + (base + ((i + 1) % size))], type: "reference" });
              base += size;
            }
            const e = new Engine();
            e.loadPayload({ nodes, edges }, {});
            return e.hairballReport();
          }
          const good = build(Array.from({ length: 12 }, () => 10));   // 120 节点 / 12 群（最大 8.33%）
          const hairball = build([60]);                               // 60 节点单群（100%）
          let holes = false;
          const e = new Engine();
          e.on("hairball", () => { holes = true; });
          e.loadPayload({ nodes: [{id: "a"}], edges: [] }, {});
          return {
            good: { is: good.isHairball, maxShare: good.metrics.maxGroupShare, threshold: good.threshold },
            hairball: { is: hairball.isHairball, maxShare: hairball.metrics.maxGroupShare },
            eventEmitted: holes,
          };
        })()""")

        # 3) T-double：声明检查 + 真机像素/半径相关性（2D galaxy 三通道）
        result["tdouble_static"] = ev("""(() => {
          const V = window.MemoriaGraphVisualChannels;
          if (!V) return null;
          const r = V.check(V.CHANNELS);
          return { pass: r.pass, conflicts: r.conflicts, encodedVariables: r.encodedVariables, channels: r.channels };
        })()""")
        result["tdouble_real"] = ev("""(() => {
          const st = window.state, v = st.graphView2d, e = st.graphEngine;
          v.opts.graphStyle = 'galaxy';
          try { v.active = true; v.resize(); } catch (_) {}
          v.draw();
          const ctx = v.ctx;
          const k = v.transform.k, tx = v.transform.x, ty = v.transform.y;
          const dpr = Math.min(window.devicePixelRatio || 1, 2);
          const rect = v.canvas.getBoundingClientRect();
          function corr(xs, ys) {
            const n = xs.length; if (n < 3) return null;
            const mx = xs.reduce((a,b)=>a+b,0)/n, my = ys.reduce((a,b)=>a+b,0)/n;
            let cov = 0, sx = 0, sy = 0;
            for (let i = 0; i < n; i++) { cov += (xs[i]-mx)*(ys[i]-my); sx += (xs[i]-mx)**2; sy += (ys[i]-my)**2; }
            if (!sx || !sy) return null;
            return +(cov / Math.sqrt(sx*sy)).toFixed(4);
          }
          // 生产函数相关性：degree ↔ radius（全部节点，不依赖画布）
          const all = e.nodes.map((n) => ({ d: e.degreeOf(n.id), r: e.radiusForNode(n.id, 6) }));
          const allDegs = all.map((x) => x.d);
          const rows = [];
          const nodes = e.nodes.map((n) => ({ n, d: e.degreeOf(n.id) })).sort((a, b) => a.d - b.d);
          const step = Math.max(1, Math.floor(nodes.length / 24));
          for (let i = 0; i < nodes.length; i += step) {
            const { n, d } = nodes[i];
            const sx = n.x * k + tx, sy = n.y * k + ty;
            if (!Number.isFinite(sx) || !Number.isFinite(sy)) continue;
            if (sx < 6 || sy < 6 || sx > rect.width - 6 || sy > rect.height - 6) continue;
            const devX = Math.floor(sx * dpr), devY = Math.floor(sy * dpr);
            let lum = 0, cnt = 0, lumErr = null;
            try {
              const cw = Math.floor(v.canvas.width), ch = Math.floor(v.canvas.height);
              const gx = Math.max(0, Math.min(cw - 7, Math.floor(devX) - 3));
              const gy = Math.max(0, Math.min(ch - 7, Math.floor(devY) - 3));
              const img = ctx.getImageData(gx, gy, 7, 7).data;
              for (let p = 0; p < img.length; p += 4) { lum += 0.2126 * img[p] + 0.7152 * img[p + 1] + 0.0722 * img[p + 2]; cnt++; }
              lum = cnt ? lum / cnt : 0;
            } catch (err) { lum = null; lumErr = String(err) + " cw=" + v.canvas.width; }
            rows.push({ id: n.id, degree: d, radius: +e.radiusForNode(n.id, 6).toFixed(4), luminance: lum == null ? null : +lum.toFixed(2), lumErr });
          }
          const degs = rows.map(r => r.degree);
          return {
            sampleSize: rows.length,
            corrDegreeRadius: corr(degs, rows.map(r => r.radius)),
            corrDegreeRadiusAll: corr(allDegs, all.map((x) => x.r)),
            corrDegreeLuminance: rows.some(r => r.luminance != null) ? corr(degs, rows.map(r => r.luminance ?? 0)) : null,
            view: { active: !!v.active, simNodes: (v.simNodes || []).length, rect: [Math.round(rect.width), Math.round(rect.height)], canvas: [v.canvas.width, v.canvas.height], k: +k.toFixed(4) },
            rows: rows.slice(0, 8),
            graphStyle: v.opts.graphStyle,
          };
        })()""")
        probe([{"action": "shot", "path": str(SHOTS / "01_graph2d_galaxy_tdouble.png"), "clipSelector": '[data-sidebar-view="graph2d"]'}])
        (HERE / "verify_hairball_tdouble.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=1)[:8000])
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
