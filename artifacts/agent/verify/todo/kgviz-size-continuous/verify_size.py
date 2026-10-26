"""task-175 真机 + 机检：KG 节点大小连续变化（D-KGV-13）A/B/C 三项。

产出（与本文件同目录）：
  t-size-machine-check.json   纯函数机检（T-size-2/3/4 + 必红 fixture 证据）
  verify.json                 真机验证（2D 实际绘制半径分布 / 3D 等大 / tooltip 中英）
  shots/*.png                 2D 大小差异、tooltip、3D 等大

运行：.venv\Scripts\python.exe artifacts/agent/verify/todo/kgviz-size-continuous/verify_size.py
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
SHOTS = HERE / "shots"
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t175"
CDP = 9653
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
LAUNCH = REPO / "artifacts/agent/verify/todo/0.4.7-task-93-responsive/launch_ctl.py"
PROBE = REPO / "artifacts/agent/verify/todo/0.4.7-task-112-d4b/probe112.mjs"
ENGINE = REPO / "src/memoria/ui/static/app/js/graph-engine.js"
KB = Path(os.environ.get("TEMP", ".")) / "memoria_p3_corpus"

FIXTURE_DISTINCT = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24, 25]


def _node_json(script: str) -> dict:
    p = subprocess.run(["node", "-"], input=script, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, cwd=str(REPO))
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-3000:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def plane_check() -> dict:
    engine = str(ENGINE).replace("\\", "/")
    script = f"""
const fs = require("fs"), vm = require("vm");
const sandbox = {{}}; vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("{engine}", "utf8"), sandbox);
const S = sandbox.MemoriaGraphSizing;
const distinct = {json.dumps(FIXTURE_DISTINCT)};
const radii = distinct.map((d) => S.radiusForDegree(d, distinct, 6));
const t = distinct.map((d) => S.normalizedRankT(d, distinct));
const rng = S.sizingRangeForBase(6);
const span = rng.max - rng.min;
const bucketed = t.map((tv) => rng.min + span * (Math.min(2, Math.floor(tv * 3)) / 2));
const monotonic = radii.every((r, i) => i === 0 || r >= radii[i - 1]);
const plateau = (arr) => {{
  const ds = []; for (let i = 1; i < arr.length; i++) ds.push(Math.abs(arr[i] - arr[i - 1]));
  const flat = ds.filter((d) => d < 0.01).length;
  return {{ ratio: ds.length ? flat / ds.length : 0, flat, total: ds.length }};
}};
const greens = {{
  radii, t, monotonic,
  distinctDegrees: distinct.length,
  distinctRadii: new Set(radii.map((r) => r.toFixed(9))).size,
  plateau: plateau(radii),
  min: Math.min(...radii), max: Math.max(...radii),
  range6: S.sizingRangeForBase(6), range4: S.sizingRangeForBase(4), range12: S.sizingRangeForBase(12),
}};
const red = {{
  radii: bucketed,
  distinctDegrees: distinct.length,
  distinctRadii: new Set(bucketed.map((r) => r.toFixed(9))).size,
  plateau: plateau(bucketed),
  monotonic: bucketed.every((r, i) => i === 0 || r >= bucketed[i - 1]),
}};
red.pass_distinct = red.distinctRadii === red.distinctDegrees;
red.pass_plateau = red.plateau.ratio <= 0.05;
red.detected_as_bucketed = !(red.pass_distinct && red.pass_plateau);
greens.pass_distinct = greens.distinctRadii === greens.distinctDegrees;
greens.pass_plateau = greens.plateau.ratio <= 0.05;
console.log(JSON.stringify({{greens, red}}));
"""
    raw = _node_json(script)
    out = {
        "schema": "kgviz-t-size-machine-check/v1",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "fixtureDistinctDegrees": FIXTURE_DISTINCT,
        "T-size-2": {
            "name": "单调性（radius 随 degree 单调不减，无反转）",
            "pass": raw["greens"]["monotonic"],
            "detail": "25 个 distinct degree 逐对检查无反转",
        },
        "T-size-3": {
            "name": "连续性（distinct 半径数 == distinct degree 数；平台段占比 ≤5%）",
            "pass": bool(raw["greens"]["pass_distinct"] and raw["greens"]["pass_plateau"]),
            "distinctDegrees": raw["greens"]["distinctDegrees"],
            "distinctRadii": raw["greens"]["distinctRadii"],
            "plateau": raw["greens"]["plateau"],
            "redFixture": {
                "description": "把连续映射偷偷改成 3 档（t→0/0.5/1）",
                "distinctRadii": raw["red"]["distinctRadii"],
                "distinctDegrees": raw["red"]["distinctDegrees"],
                "plateau": raw["red"]["plateau"],
                "pass_distinct": raw["red"]["pass_distinct"],
                "pass_plateau": raw["red"]["pass_plateau"],
                "detectedAsBucketed": raw["red"]["detected_as_bucketed"],
                "proven": bool(raw["red"]["detected_as_bucketed"]),
            },
        },
        "T-size-4": {
            "name": "范围（基准 6 ⇒ [4.50,9.90]±0.5；随用户 nodeRadius 缩放）",
            "pass": abs(raw["greens"]["min"] - 4.5) <= 0.5 and abs(raw["greens"]["max"] - 9.9) <= 0.5,
            "min": raw["greens"]["min"],
            "max": raw["greens"]["max"],
            "base6": raw["greens"]["range6"],
            "base4": raw["greens"]["range4"],
            "base12": raw["greens"]["range12"],
        },
    }
    (HERE / "t-size-machine-check.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2); return True
    except Exception:
        return False


def probe(cmds):
    (WORK / "c.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP), "--cmd", str(WORK / "c.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": (p.stderr or "")[-300:]}]


def ev(expr):
    r = probe([{"action": "eval", "expr": expr, "awaitPromise": True}])[0]
    if isinstance(r, dict) and r.get("exception"):
        return {"__exception": str(r.get("exception"))[:500]}
    return r.get("value") if isinstance(r, dict) else r


def shot(name, selector=None):
    cmd = {"action": "shot", "path": str(SHOTS / name)}
    if selector:
        cmd["clipSelector"] = selector
    probe([cmd])


def ctl(payload):
    ack = WORK / "ack.json"
    try: ack.unlink()
    except OSError: pass
    payload["_seq"] = time.time_ns()
    (WORK / "cmd.json").write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(60):
        if ack.is_file():
            try: return json.loads(ack.read_text(encoding="utf-8"))
            except Exception: pass
        time.sleep(0.1)
    return {"ok": False}


def real_check() -> dict:
    os.makedirs(WORK, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    cfg = WORK / "cfg"
    if cfg.exists(): shutil.rmtree(cfg)
    os.makedirs(cfg, exist_ok=True)
    env = dict(os.environ)
    env.update({"T93_WORK": str(WORK), "T93_CDP_PORT": str(CDP), "MEMORIA_CONFIG_DIR": str(cfg),
                "MEMORIA_KB": str(KB), "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8"})
    out = (WORK / "o.log").open("w", encoding="utf-8"); err = (WORK / "e.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    res: dict = {}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP}/json/version"): break
            time.sleep(0.5)
        time.sleep(8)
        ctl({"op": "foreground"}); time.sleep(0.6)
        # 展开侧栏 + 2D 图谱 tab（真实鼠标）
        for sel in ("#btn-toggle-sidebar", '[data-sidebar-tab="graph2d"]'):
            r = ev("(function(){var b=document.querySelector(%s); if(!b) return null; var r=b.getBoundingClientRect(); return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()" % json.dumps(sel))
            if isinstance(r, list) and r:
                probe([{"action": "mouse", "type": "mousePressed", "x": r[0], "y": r[1], "button": "left", "clickCount": 1},
                       {"action": "mouse", "type": "mouseReleased", "x": r[0], "y": r[1], "button": "left", "clickCount": 1}])
                time.sleep(0.8)
        for _ in range(80):
            n = ev("(function(){var v=window.state.graphView2d; return v&&v.simNodes?v.simNodes.length:0;})()")
            if isinstance(n, int) and n > 0: break
            time.sleep(0.3)
        time.sleep(2.0)
        # 1) 拦截 ctx.arc：采集一次 draw 的真实世界坐标半径
        res["render"] = ev("""(() => {
          const v = window.state.graphView2d; if (!v) return null;
          const proto = CanvasRenderingContext2D.prototype;
          const orig = proto.arc;
          const radii = [];
          proto.arc = function (x, y, r, s, e, ccw) { if (r > 0) radii.push(r); return orig.call(this, x, y, r, s, e, ccw); };
          try { v.draw(); } finally { proto.arc = orig; }
          const uniq = [...new Set(radii.map(r => r.toFixed(6)))].map(Number).sort((a,b)=>a-b);
          const ds = []; for (let i=1;i<uniq.length;i++) ds.push(Math.abs(uniq[i]-uniq[i-1]));
          const flat = ds.filter(d => d < 0.01).length;
          const deg = window.state.graphEngine;
          const nodes = deg.nodes.map(n => n.id);
          const engineRadii = [...new Set(nodes.map(id => deg.radiusForNode(id, 6).toFixed(6)))].map(Number);
          return {
            nodes: deg.nodes.length, links: deg.links.length,
            drawRadiiCount: radii.length, distinctDrawn: uniq.length,
            minDrawn: uniq[0], maxDrawn: uniq[uniq.length-1],
            distinctDegrees: deg.degreeDistinct().length,
            distinctEngineRadii: engineRadii.length,
            plateauRatio: ds.length ? flat / ds.length : 0,
            sample: nodes.slice(0, 6).map(id => ({ id, degree: deg.degreeOf(id), radius: +deg.radiusForNode(id, 6).toFixed(4) })),
            expectedRange: deg.sizingRange(6),
          };
        })()""")
        res["render"]["drawnEqualsEngine"] = (
            res["render"].get("distinctDrawn") == res["render"].get("distinctEngineRadii")
            and abs(res["render"].get("minDrawn", 0) - 4.5) < 1e-6
            and abs(res["render"].get("maxDrawn", 0) - 9.9) < 1e-6
        )
        shot("01_graph2d_continuous_size.png", '[data-sidebar-view="graph2d"]')
        # 1b) 放大到能看清大小差异（fit 后 k×3.2，居中在高 degree 节点）
        res["zoomshot"] = ev("""(() => {
          const v = window.state.graphView2d; const e = window.state.graphEngine; if (!v || !e) return null;
          v.fitToView(24);
          const hi = e.nodes.map(n => ({ n, d: e.degreeOf(n.id) })).sort((a,b)=>b.d-a.d)[0];
          const k = Math.max(1.2, (v.transform.k || 1) * 3.2);
          const cw = v.viewW || 280, ch = v.viewH || 580;
          v.transform = { x: cw / 2 - hi.n.x * k, y: ch / 2 - hi.n.y * k, k };
          v._userView = true;
          v.draw();
          return { k: +k.toFixed(3), center: { id: hi.n.id, degree: hi.d }, cw, ch };
        })()""")
        time.sleep(0.3)
        shot("01b_graph2d_zoomed_size_visible.png", '[data-sidebar-view="graph2d"]')

        # 2) tooltip：走生产路径 engine.on("hover") → updateGraphNodeHint
        res["tooltip"] = ev("""(() => {
          const engine = window.state.graphEngine; if (!engine) return null;
          const byDeg = engine.nodes.map(n => ({ n, d: engine.degreeOf(n.id) })).sort((a,b) => b.d - a.d);
          const hi = byDeg[0], lo = byDeg[byDeg.length-1];
          const hint = document.querySelector('#graph-2d-hint');
          engine._emit('hover', { node: hi.n });
          const zhHtml = hint ? hint.innerHTML : '';
          const zhText = hint ? hint.innerText : '';
          return { high: { id: hi.n.id, degree: hi.d }, low: { id: lo.n.id, degree: lo.d },
                   zhHasDegree: /连接数\\s*\\d+/.test(zhText), zhText, zhHtmlSnippet: zhHtml.slice(0, 400),
                   degreeLineClass: !!document.querySelector('#graph-2d-hint .-graph-hint-degree') };
        })()""")
        # 双语：切 en → 再 hover
        res["tooltip"]["en"] = ev("""(() => {
          try { window.MemoriaI18n && window.MemoriaI18n.setLang && window.MemoriaI18n.setLang('en'); } catch (e) {}
          const engine = window.state.graphEngine; const hint = document.querySelector('#graph-2d-hint');
          if (!engine || !hint) return null;
          const hi = engine.nodes.map(n => ({ n, d: engine.degreeOf(n.id) })).sort((a,b) => b.d - a.d)[0];
          engine._emit('hover', { node: hi.n });
          const text = hint.innerText || '';
          return { hasDegree: /Connections:\\s*\\d+/.test(text), text };
        })()""")
        # 英文 tooltip 截图（关闭前）
        ev("(function(){ const e=window.state.graphEngine; const hi=e.nodes.map(n=>({n,d:e.degreeOf(n.id)})).sort((a,b)=>b.d-a.d)[0]; e._emit('hover',{node:hi.n}); return true; })()")
        time.sleep(0.3)
        shot("02b_tooltip_degree_en.png", '[data-sidebar-view="graph2d"]')
        ev("(function(){ try { window.MemoriaI18n && window.MemoriaI18n.setLang && window.MemoriaI18n.setLang('zh-CN'); } catch(e){} return true; })()")
        # 保持高亮 hover 再截图（tooltip 可见）
        ev("(function(){ const e=window.state.graphEngine; const hi=e.nodes.map(n=>({n,d:e.degreeOf(n.id)})).sort((a,b)=>b.d-a.d)[0]; e._emit('hover',{node:hi.n}); return true; })()")
        time.sleep(0.4)
        shot("02_tooltip_degree_zh.png", '[data-sidebar-view="graph2d"]')

        # 3) 3D 等大：打开 3D tab，检查所有节点 mesh scale === 1 且共享同一 geometry
        r = ev("(function(){var b=document.querySelector('[data-sidebar-tab=\\\"graph3d\\\"]'); if(!b) return null; var r=b.getBoundingClientRect(); return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()")
        if isinstance(r, list) and r:
            probe([{"action": "mouse", "type": "mousePressed", "x": r[0], "y": r[1], "button": "left", "clickCount": 1},
                   {"action": "mouse", "type": "mouseReleased", "x": r[0], "y": r[1], "button": "left", "clickCount": 1}])
        time.sleep(2.5)
        res["three_d"] = ev("""(() => {
          const v = window.state.graphView3d; if (!v) return { error: 'no-3d-view' };
          const meshes = [...(v._nodeMeshes ? v._nodeMeshes.values() : [])];
          const scales = meshes.map(m => [m.scale.x, m.scale.y, m.scale.z]);
          const geos = new Set(meshes.map(m => m.geometry && m.geometry.uuid));
          return { active: !!v.active, meshes: meshes.length, allScaleOne: scales.every(s => s.every(x => Math.abs(x - 1) < 1e-9)),
                   distinctGeometries: geos.size, nodeGeoUuid: v._nodeGeo ? v._nodeGeo.uuid : null,
                   camera: v.camera ? { fov: v.camera.fov, z: +v.camera.position.z.toFixed(1) } : null,
                   sampleScales: scales.slice(0, 5) };
        })()""")
        shot("03_graph3d_equal_size.png", '[data-sidebar-view="graph3d"]')

        # 3b) D-KGV-16：切 galaxy 风格（唯一有 halo 的风格），测「不同 degree 节点表观尺寸一致」
        res["three_d"]["galaxy"] = ev("""(() => {
          const v = window.state.graphView3d; if (!v) return { error: 'no-3d-view' };
          v.applyOptions({ graphStyle: 'galaxy' });
          return { switched: v.opts.graphStyle };
        })()""")
        time.sleep(1.5)
        res["three_d"]["galaxy"] = ev("""(() => {
          const v = window.state.graphView3d; if (!v || !v._nodeMeshes) return null;
          const engine = window.state.graphEngine;
          const meshes = [...v._nodeMeshes.values()];
          const halos = [...(v._haloSprites ? v._haloSprites.values() : [])];
          const cam = v.camera;
          const canvasH = v.renderer && v.renderer.domElement ? v.renderer.domElement.clientHeight : 0;
          const focal = canvasH / (2 * Math.tan((cam.fov * Math.PI / 180) / 2));
          const dist = (m) => Math.hypot(m.position.x - cam.position.x, m.position.y - cam.position.y, m.position.z - cam.position.z);
          const degOf = (id) => engine.degreeOf(id);
          const meshWorld = (m) => (v._nodeGeo && v._nodeGeo.parameters ? v._nodeGeo.parameters.radius : 0) * m.scale.x;
          const haloWorld = (id) => { const h = v._haloSprites.get(id); return h && h.userData ? h.userData.baseScale : null; };
          const haloWorlds = [...new Set(meshes.map(m => (haloWorld(m.userData.nodeId) || 0).toFixed(6)))].map(Number);
          const meshWorlds = [...new Set(meshes.map(m => meshWorld(m).toFixed(6)))].map(Number);
          const rows = meshes.map(m => { const d = dist(m); const hw = haloWorld(m.userData.nodeId);
            return { id: m.userData.nodeId, degree: degOf(m.userData.nodeId), distPx: +d.toFixed(1),
                     meshPx: +((meshWorld(m) / d) * focal).toFixed(3),
                     haloPx: +(((hw || 0) / d) * focal).toFixed(3), haloWorld: hw }; });
          // 选一对「深度几乎相同」的高/低 degree 节点（控制透视），比较表观 halo 直径
          rows.sort((a,b)=>a.distPx-b.distPx);
          const byDeg = [...rows].sort((a,b)=>b.degree-a.degree);
          const hi = byDeg[0], lo = byDeg[byDeg.length-1];
          let pair = null, best = Infinity;
          for (const h of byDeg.slice(0, 8)) for (const l of byDeg.slice(-8)) {
            if (h.degree <= l.degree) continue;
            const dd = Math.abs(h.distPx - l.distPx);
            if (dd < best) { best = dd; pair = { hi: h, lo: l, distDiffPx: +dd.toFixed(1) }; }
          }
          // 度数 vs 光晕世界尺寸的相关性（应=0：统一值）
          const xs = rows.map(r=>r.degree), ys = rows.map(r=>r.haloWorld);
          const mx = xs.reduce((a,b)=>a+b,0)/xs.length, my = ys.reduce((a,b)=>a+b,0)/ys.length;
          const cov = xs.reduce((s,x,i)=>s+(x-mx)*(ys[i]-my),0);
          const sx = Math.sqrt(xs.reduce((s,x)=>s+(x-mx)**2,0)), sy = Math.sqrt(ys.reduce((s,y)=>s+(y-my)**2,0));
          return {
            active: !!v.active, graphStyle: v.opts.graphStyle, meshes: meshes.length, halos: halos.length,
            distinctHaloWorldSizes: haloWorlds.length, haloWorldSize: haloWorlds[0] || null,
            distinctMeshWorldSizes: meshWorlds.length, meshWorldSize: meshWorlds[0] || null,
            haloScreenPxDependentOnDegree: { corrDegreeHaloWorld: sx && sy ? +(cov/(sx*sy)).toFixed(6) : null },
            sameDepthPair: pair, rows: rows.sort((a,b)=>b.degree-a.degree).slice(0,6),
          };
        })()""")
        shot("04_graph3d_galaxy_halo_equal.png", '[data-sidebar-view="graph3d"]')


        # 恢复 2D tab（避免影响用户/后续截图）
        ev("(function(){var b=document.querySelector('[data-sidebar-tab=\\\"graph2d\\\"]'); if(b) b.click(); return true;})()")
        time.sleep(0.5)
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()
    res["corpus"] = {"kb": str(KB), "nodesExpected": 134, "linksExpected": 404}
    (HERE / "verify.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def main() -> int:
    machine = plane_check()
    print("=== machine check ===")
    print(json.dumps(machine, ensure_ascii=False, indent=1)[:2500])
    real = real_check()
    print("=== real render ===")
    print(json.dumps(real.get("render"), ensure_ascii=False, indent=1)[:2000])
    print("=== tooltip ===")
    print(json.dumps(real.get("tooltip"), ensure_ascii=False, indent=1)[:800])
    print("=== 3d ===")
    print(json.dumps(real.get("three_d"), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
