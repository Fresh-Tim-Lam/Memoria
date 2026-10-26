"""task-177 真机验证：标签 LOD/避让（D-KGV-06）。

产出（同目录）：
  verify_label.json      T-label-1/2/3/5 机检读数（用画布真实 fillText 包围盒）
  shots/01_label_lod.png / 02_hover_hidden_label.png / 03_zoom_more_labels.png / 04_red_all_labels.png

运行：.venv\\Scripts\\python.exe artifacts/agent/verify/todo/kgviz-label-lod/verify_label.py
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
SHOTS = HERE / "shots"
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t177"
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
LAUNCH = REPO / "artifacts/agent/verify/todo/0.4.7-task-93-responsive/launch_ctl.py"
PROBE = REPO / "artifacts/agent/verify/todo/0.4.7-task-112-d4b/probe112.mjs"
KB = Path(os.environ.get("TEMP", ".")) / "memoria_p3_corpus"
PORT = 9701


def up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False


def probe(cmds):
    (WORK / "probe.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(PORT), "--cmd", str(WORK / "probe.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": (p.stderr or "")[-500:]}]


def ev(expr, await_promise=True):
    r = probe([{"action": "eval", "expr": expr, "awaitPromise": await_promise}])[0]
    if isinstance(r, dict) and r.get("exception"):
        return {"__exception": str(r.get("exception"))[:600]}
    return r.get("value") if isinstance(r, dict) else r


def shot(name, selector='[data-sidebar-view="graph2d"]'):
    probe([{"action": "shot", "path": str(SHOTS / name), "clipSelector": selector}])


def click(selector):
    pos = ev("(function(){var b=document.querySelector(%s); if(!b) return null; var r=b.getBoundingClientRect(); return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()" % json.dumps(selector))
    if isinstance(pos, list) and pos:
        probe([
            {"action": "mouse", "type": "mousePressed", "x": pos[0], "y": pos[1], "button": "left", "clickCount": 1},
            {"action": "mouse", "type": "mouseReleased", "x": pos[0], "y": pos[1], "button": "left", "clickCount": 1},
        ])


MEASURE_JS = r"""
(() => {
  const st = window.state;
  const view = st.graphView2d;
  const ctx = view.ctx;
  const proto = CanvasRenderingContext2D.prototype;
  const origFill = proto.fillText;
  const labels = [];
  proto.fillText = function (text, x, y) {
    labels.push({ text: String(text), x: Number(x), y: Number(y) });
    return origFill.call(this, text, x, y);
  };
  try {
    view.active = true;
    view.draw();
  } finally {
    proto.fillText = origFill;
  }
  // 用与渲染相同的字体测量真实文本宽度，构造屏幕包围盒（机检 T-label-1 的口径）
  const mc = document.createElement('canvas').getContext('2d');
  mc.font = '10px system-ui, sans-serif';
  const boxes = labels.map((l) => {
    const w = mc.measureText(l.text).width;
    return { text: l.text, x: l.x - w / 2, y: l.y - 6, w, h: 12 };
  });
  let overlapPairs = 0;
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (!(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y)) overlapPairs++;
    }
  }
  const engine = st.graphEngine;
  const topIds = engine.nodes.map((n) => ({ id: n.id, d: engine.degreeOf(n.id) }))
    .sort((a, b) => b.d - a.d || String(a.id).localeCompare(String(b.id)))
    .slice(0, 10).map((x) => x.id);
  const visible = view._visibleLabelIds ? [...view._visibleLabelIds] : [];
  return {
    drawnLabels: labels.length,
    boxesCount: boxes.length,
    overlapPairs,
    disjointRatio: boxes.length > 1 ? 1 - overlapPairs / (boxes.length * (boxes.length - 1) / 2) : 1,
    stats: view._labelLodStats || null,
    visibleCount: visible.length,
    topIds,
    topVisible: topIds.every((id) => visible.includes(id)),
    zoomK: +view.transform.k.toPrecision(6),
    labelsSample: labels.slice(0, 5),
  };
})()
"""


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    cfg = WORK / "cfg"
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
        probe([{"action": "ctl", "cmd": {"op": "foreground"}}]) if False else None
        # launch_ctl 的 cmd/ack 通道
        ack = WORK / "ack.json"
        (WORK / "cmd.json").write_text(json.dumps({"op": "foreground", "_seq": time.time_ns()}), encoding="utf-8")
        for _ in range(60):
            if ack.is_file():
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
        time.sleep(2.0)
        # 冻结布局（T-stable 已保证可复现），让标签测量只依赖屏幕几何
        ev("(function(){var s=window.state; if(s.graphLayout2d) s.graphLayout2d.stop(); if(s.graphView2d) s.graphView2d.active=true; return true;})()")
        time.sleep(0.2)

        result["default"] = ev(MEASURE_JS)
        shot("01_label_lod.png")

        # T-label-2：topN 必然可见
        result["top_n"] = {
            "ids": result["default"].get("topIds"),
            "visible": result["default"].get("topVisible"),
        }

        # hover 一个被隐藏标签 ⇒ 它必须出现（信息不丢失）
        hidden = ev("(function(){var s=window.state; var st=s.graphView2d._labelLodStats||{}; return (st.hiddenIds||[])[0]||null;})()")
        result["hover"] = {"hiddenId": hidden, "appeared": False}
        if hidden:
            pos = ev("""(function(){
              const s=window.state, v=s.graphView2d, n=s.graphLayout2d.getNode(%s);
              const k=v.transform.k, tx=v.transform.x, ty=v.transform.y;
              const c=v.canvas, r=c.getBoundingClientRect();
              return [r.left + n.x*k + tx, r.top + n.y*k + ty];
            })()""" % json.dumps(hidden))
            if isinstance(pos, list) and len(pos) == 2:
                probe([{"action": "mouse", "type": "mouseMoved", "x": pos[0], "y": pos[1]}])
                time.sleep(0.4)
                result["hover"]["after"] = ev(MEASURE_JS)
                result["hover"]["appeared"] = bool(
                    result["hover"]["after"]
                    and hidden in (ev("(function(){var v=window.state.graphView2d; return v._visibleLabelIds?[...v._visibleLabelIds]:[];})()") or [])
                )
                shot("02_hover_hidden_label.png")
                # 移开
                probe([{"action": "mouse", "type": "mouseMoved", "x": 30, "y": 30}])
                time.sleep(0.2)

        # T-label-5 / 必红 fixture（真机）：在当前默认（最密）缩放下关闭 LOD ⇒ 全部标签显示 ⇒ 包围盒重叠 > 0
        ev("(function(){var s=window.state.graphView2d; s.opts.labelLod=false; s.draw(); return true;})()")
        time.sleep(0.2)
        red = ev(MEASURE_JS)
        shot("04_red_all_labels.png")
        ev("(function(){var s=window.state.graphView2d; s.opts.labelLod=true; s.draw(); return true;})()")
        result["red_fixture"] = {
            "drawnLabels": red.get("drawnLabels"),
            "overlapPairs": red.get("overlapPairs"),
            "disjointRatio": red.get("disjointRatio"),
            "detectedAsOverlapping": (red.get("overlapPairs") or 0) > 0,
            "toggleOffReverts": (red.get("drawnLabels") or 0) >= 134,
            "zoomK": red.get("zoomK"),
        }

        # T-label-3：缩放变稀疏后，可见标签增加
        before_count = ev("(function(){var s=window.state.graphView2d; return s._labelLodStats? s._labelLodStats.visible : -1;})()")
        before_k = ev("(function(){var s=window.state.graphView2d; return +s.transform.k.toPrecision(6);})()")
        box = ev("(function(){var c=window.state.graphView2d.canvas; var r=c.getBoundingClientRect(); return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()")
        for _ in range(4):
            if isinstance(box, list) and box:
                probe([{"action": "mouse", "type": "mouseWheel", "deltaX": 0, "deltaY": -120, "x": box[0], "y": box[1]}])
            time.sleep(0.25)
        time.sleep(0.4)
        after_labels = ev(MEASURE_JS)
        result["zoom"] = {
            "beforeVisible": before_count,
            "afterVisible": after_labels.get("visibleCount"),
            "beforeK": before_k,
            "afterK": after_labels.get("zoomK"),
            "moreLabels": (after_labels.get("visibleCount") or 0) > (before_count or 0),
        }
        shot("03_zoom_more_labels.png")

        # ── 3D 标签 LOD（D-KGV-06 3D 版：默认按度数 topN 裁剪；拉近全显；hover 显示）──
        click('[data-sidebar-tab="graph3d"]')
        for _ in range(80):
            n = ev("(function(){var v=window.state&&window.state.graphView3d; return v&&v.layout&&v.layout.nodes?v.layout.nodes.length:0;})()")
            if isinstance(n, int) and n > 0:
                break
            time.sleep(0.25)
        time.sleep(1.5)
        base3d = ev("""(() => {
          const v = window.state.graphView3d;
          v._applyHighlight();
          const st = v._labelLodStats || null;
          const hidden = [...v._labelSprites.keys()].filter((id) => !(v._labelLodVisibleIds || new Set()).has(id));
          return { stats: st, hiddenSample: hidden[0] || null, meshes: v._labelSprites.size,
                   topNVisible: (() => {
                     const e = window.state.graphEngine;
                     const top = e.nodes.map((n) => ({ id: n.id, d: e.degreeOf(n.id) })).sort((a,b)=>b.d-a.d).slice(0,10).map(x=>x.id);
                     const vis = v._labelLodVisibleIds || new Set();
                     return top.every((id) => vis.has(id));
                   })() };
        })()""")
        result["three_d"] = {"base": base3d}
        # hover 一个被 3D LOD 隐藏的标签 → 必须出现
        hid = base3d.get("hiddenSample") if isinstance(base3d, dict) else None
        if hid:
            result["three_d"]["hover"] = ev("""(() => {
              const v = window.state.graphView3d;
              v.setRemoteHover(%s);
              v._applyHighlight();
              const label = v._labelSprites.get(%s);
              return { hovered: %s, labelVisible: !!(label && label.visible), stats: v._labelLodStats };
            })()""" % (json.dumps(hid), json.dumps(hid), json.dumps(hid)))
            ev("(function(){var v=window.state.graphView3d; v.setRemoteHover(null); v._applyHighlight(); return true;})()")
        # 相机拉近 → 全显（T-label-3 的 3D 对应）
        result["three_d"]["zoom_in"] = ev("""(() => {
          const v = window.state.graphView3d;
          const before = v._labelLodStats;
          v.camera.position.multiplyScalar(0.35);
          v._applyHighlight();
          return { before, after: v._labelLodStats };
        })()""")
        shot("05_graph3d_label_lod.png", '[data-sidebar-view="graph3d"]')
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close()
        err.close()
    (HERE / "verify_label.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1)[:7000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
