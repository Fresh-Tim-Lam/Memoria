"""task-176 真机验证：布局确定性种子 + 会话内保位（D-KGV-07）。

产出（同目录）：
  verify_seed.json          机检摘要（T-stable-1/2/4/5 真机读数）
  shots/01_graph2d_seeded.png、shots/stable3_run{1,2,3}.png、shots/04_graph3d_seeded.png

运行：.venv\\Scripts\\python.exe artifacts/agent/verify/todo/kgviz-layout-seed/verify_seed.py
"""

from __future__ import annotations

import hashlib
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_t176"
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
LAUNCH = REPO / "artifacts/agent/verify/todo/0.4.7-task-93-responsive/launch_ctl.py"
KB = Path(os.environ.get("TEMP", ".")) / "memoria_p3_corpus"
DEFAULT_SEED = 0x9E3779B9
ALT_SEED = 0x12345678


def up(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False


class App:
    def __init__(self, tag: str, port: int):
        self.tag = tag
        self.port = port
        self.proc = None
        self.work = WORK / tag
        self.work.mkdir(parents=True, exist_ok=True)
        self.ack = self.work / "ack.json"
        self.cmd = self.work / "cmd.json"
        self.shots = SHOTS

    def start(self):
        cfg = self.work / "cfg"
        if cfg.exists():
            shutil.rmtree(cfg)
        cfg.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.update({
            "T93_WORK": str(self.work), "T93_CDP_PORT": str(self.port),
            "MEMORIA_CONFIG_DIR": str(cfg), "MEMORIA_KB": str(KB),
            "MEMORIA_FRAMELESS": "0", "PYTHONIOENCODING": "utf-8",
        })
        out = (self.work / "o.log").open("w", encoding="utf-8")
        err = (self.work / "e.log").open("w", encoding="utf-8")
        self.proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
        self._out, self._err = out, err
        for _ in range(160):
            if up(self.port):
                break
            time.sleep(0.5)
        time.sleep(7)
        self.ctl({"op": "foreground"})
        time.sleep(0.5)
        return self

    def stop(self):
        if self.proc:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/F"], capture_output=True)
        self._out.close()
        self._err.close()

    def ctl(self, payload):
        payload["_seq"] = time.time_ns()
        try:
            self.ack.unlink()
        except OSError:
            pass
        self.cmd.write_text(json.dumps(payload), encoding="utf-8")
        for _ in range(80):
            if self.ack.is_file():
                try:
                    return json.loads(self.ack.read_text(encoding="utf-8"))
                except Exception:
                    pass
            time.sleep(0.1)
        return {"ok": False}

    def js(self, expr: str):
        """通过 CDP 执行表达式（沿用 T93 的 launch_ctl 无 CDP 外部端口：这里走页面内 bridge）。"""
        # launch_ctl 暴露 /eval HTTP 端点（与 probe112 使用同一桥接）
        body = json.dumps({"expr": expr}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/__dsh_eval__", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("value") if isinstance(data, dict) else data
        except Exception as exc:
            return {"__error": str(exc)[:400]}


# 说明：本仓库 launch_ctl 目前没有 /__dsh_eval__ 桥；使用 probe112 的 cmd/ack 通道。
PROBE = REPO / "artifacts/agent/verify/todo/0.4.7-task-112-d4b/probe112.mjs"


def probe(port: int, cmds):
    (WORK / "probe.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(port), "--cmd", str(WORK / "probe.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    lines = (p.stdout or "").strip().splitlines()
    return json.loads(lines[-1])["results"] if lines else [{"error": (p.stderr or "")[-400:]}]


def ev(port: int, expr: str, await_promise: bool = True):
    r = probe(port, [{"action": "eval", "expr": expr, "awaitPromise": await_promise}])[0]
    if isinstance(r, dict) and r.get("exception"):
        return {"__exception": str(r.get("exception"))[:600]}
    return r.get("value") if isinstance(r, dict) else r


def shot(port: int, name: str, selector: str = '[data-sidebar-view="graph2d"]'):
    probe(port, [{"action": "shot", "path": str(SHOTS / name), "clipSelector": selector}])


def click(port: int, selector: str):
    pos = ev(port, "(function(){var b=document.querySelector(%s); if(!b) return null; var r=b.getBoundingClientRect(); return [Math.round(r.left+r.width/2),Math.round(r.top+r.height/2)];})()"
             % json.dumps(selector))
    if isinstance(pos, list) and pos:
        probe(port, [
            {"action": "mouse", "type": "mousePressed", "x": pos[0], "y": pos[1], "button": "left", "clickCount": 1},
            {"action": "mouse", "type": "mouseReleased", "x": pos[0], "y": pos[1], "button": "left", "clickCount": 1},
        ])


def open_graph(port: int):
    click(port, "#btn-toggle-sidebar")
    time.sleep(0.6)
    click(port, '[data-sidebar-tab="graph2d"]')
    for _ in range(100):
        n = ev(port, "(function(){var v=window.state&&window.state.graphView2d; return v&&v.simNodes?v.simNodes.length:0;})()")
        if isinstance(n, int) and n > 0:
            break
        time.sleep(0.25)
    time.sleep(1.5)


SNAP_JS = r"""
(() => {
  const st = window.state;
  const layout = st.graphLayout2d;
  const nodes = layout.nodes.map(n => [n.id, n.x.toPrecision(17), n.y.toPrecision(17)]);
  const payload = nodes.map(r => r.join('|')).join('\n');
  let h = 0;
  for (let i = 0; i < payload.length; i++) h = (Math.imul(h, 31) + payload.charCodeAt(i)) | 0;
  return { count: nodes.length, hash: h >>> 0, payload };
})()
"""

STABLE_JS = r"""
(async () => {
  const st = window.state;
  const view = st.graphView2d, layout = st.graphLayout2d;
  const waitReady = async () => {
    const t0 = Date.now();
    while (Date.now() - t0 < 12000) {
      if (!layout._workerWaitingReady) return true;
      await new Promise(r => setTimeout(r, 40));
    }
    return false;
  };
  const freeze = async () => {
    layout.stop();
    view.active = false;
    view.resetSimulation();
    await waitReady();
    await new Promise(r => setTimeout(r, 120));
    layout.stop();
    view.active = true;
    view._fitCanvas && view._fitCanvas();
    if (!view._userView) view.fitToView();
    view.draw();
    return true;
  };
  const snap = () => {
    const payload = layout.nodes.map(n => n.id + '|' + n.x.toPrecision(17) + '|' + n.y.toPrecision(17)).join('\n');
    let h = 0;
    for (let i = 0; i < payload.length; i++) h = (Math.imul(h, 31) + payload.charCodeAt(i)) | 0;
    return { count: layout.nodes.length, hash: h >>> 0, payload, seed: layout.getSeed() };
  };
  await freeze();
  const a = snap();
  await freeze();
  const b = snap();
  // T-stable-2：换种子后重新初始化
  layout.setSeed(SEED_ALT, { relayout: false });
  await freeze();
  const c = snap();
  layout.setSeed(SEED_DEFAULT, { relayout: false });
  await freeze();
  const d = snap();
  return {
    firstEqualsSecond: a.payload === b.payload,
    aHash: a.hash, bHash: b.hash,
    differentSeedChanged: a.payload !== c.payload,
    changedNodes: a.payload.split('\n').filter((row, i) => row !== c.payload.split('\n')[i]).length,
    restoreEqualsFirst: a.payload === d.payload,
    seedBefore: a.seed, seedAlt: c.seed, seedDefault: d.seed,
    count: a.count,
  };
})()
"""


def session_2d(port: int) -> dict:
    out = {"stable": ev(port, STABLE_JS.replace("SEED_ALT", str(ALT_SEED)).replace("SEED_DEFAULT", str(DEFAULT_SEED)))}
    # T-stable-4：冻结后 hover / zoom / 样式切换 不改变布局坐标
    out["no_reheat"] = ev(port, r"""
(() => {
  const st = window.state;
  const view = st.graphView2d, layout = st.graphLayout2d, engine = st.graphEngine;
  const snap = () => layout.nodes.map(n => n.x.toPrecision(17) + ',' + n.y.toPrecision(17)).join(';');
  const before = snap();
  engine._emit('hover', { node: engine.nodes[0] });
  const afterHover = snap();
  const c = view.canvas;
  const r = c.getBoundingClientRect();
  c.dispatchEvent(new WheelEvent('wheel', { deltaY: -120, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, bubbles: true, cancelable: true }));
  const afterZoom = snap();
  // 样式切换：force → galaxy → force（只影响绘制/编码，不应重置布局）
  view.applyOptions({ graphStyle: 'galaxy' }, { relayout: false });
  const afterStyle1 = snap();
  view.applyOptions({ graphStyle: 'force' }, { relayout: false });
  const afterStyle2 = snap();
  // 选中：真实 pointerdown/up 命中一个节点（走生产 click 路径，不应 reset 布局）
  const target = layout.nodes[Math.floor(layout.nodes.length / 2)];
  const k = view.transform.k, tx = view.transform.x, ty = view.transform.y;
  const cr = view.canvas.getBoundingClientRect();
  const px = cr.left + target.x * k + tx;
  const py = cr.top + target.y * k + ty;
  const pe = { clientX: px, clientY: py, pointerId: 7, bubbles: true, cancelable: true, button: 0, buttons: 1 };
  view.canvas.dispatchEvent(new PointerEvent('pointerdown', pe));
  view.canvas.dispatchEvent(new PointerEvent('pointerup', { ...pe, buttons: 0 }));
  const afterSelect = snap();
  return {
    hover: before === afterHover,
    zoom: before === afterZoom,
    styleSwitch: before === afterStyle1 && before === afterStyle2,
    select: before === afterSelect,
    allUnchanged: before === afterHover && before === afterZoom && before === afterStyle1 && before === afterStyle2 && before === afterSelect,
    zoomK: +view.transform.k.toPrecision(8),
    activeAlpha: layout.alpha,
  };
})()
""")
    shot(port, "01_graph2d_seeded.png")
    return out


def session_3d(port: int) -> dict:
    click(port, '[data-sidebar-tab="graph3d"]')
    for _ in range(80):
        n = ev(port, "(function(){var v=window.state&&window.state.graphView3d; return v&&v.layout&&v.layout.nodes?v.layout.nodes.length:0;})()")
        if isinstance(n, int) and n > 0:
            break
        time.sleep(0.25)
    time.sleep(1.0)
    return ev(port, r"""
(async () => {
  const st = window.state;
  const view = st.graphView3d, layout = st.graphLayout3d;
  const waitReady = async () => {
    const t0 = Date.now();
    while (Date.now() - t0 < 12000) {
      if (!layout._workerWaitingReady) return true;
      await new Promise(r => setTimeout(r, 40));
    }
    return false;
  };
  const freeze = async () => {
    layout.stop(); view.active = false;
    view.resetSimulation();
    await waitReady();
    await new Promise(r => setTimeout(r, 120));
    layout.stop();
    view.active = true;
    view.draw && view.draw();
    return true;
  };
  const snap = () => {
    const payload = layout.nodes.map(n => n.id + '|' + n.x.toPrecision(17) + '|' + n.y.toPrecision(17) + '|' + n.z.toPrecision(17)).join('\n');
    let h = 0;
    for (let i = 0; i < payload.length; i++) h = (Math.imul(h, 31) + payload.charCodeAt(i)) | 0;
    return { count: layout.nodes.length, hash: h >>> 0, payload, seed: layout.getSeed() };
  };
  await freeze(); const a = snap();
  await freeze(); const b = snap();
  layout.setSeed(SEED_ALT, { relayout: false });
  await freeze(); const c = snap();
  layout.setSeed(SEED_DEFAULT, { relayout: false });
  await freeze(); const d = snap();
  return {
    hasSeedApi: typeof layout.setSeed === 'function' && typeof layout.getSeed === 'function',
    firstEqualsSecond: a.payload === b.payload,
    differentSeedChanged: a.payload !== c.payload,
    changedNodes: a.payload.split('\n').filter((row, i) => row !== c.payload.split('\n')[i]).length,
    restoreEqualsFirst: a.payload === d.payload,
    count: a.count, seedDefault: d.seed,
  };
})()
""".replace("SEED_ALT", str(ALT_SEED)).replace("SEED_DEFAULT", str(DEFAULT_SEED)))


def launch_session(tag: str, port: int):
    app = App(tag, port)
    app.start()
    open_graph(port)
    return app


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    result: dict = {"env": {"kb": str(KB), "defaultSeed": DEFAULT_SEED, "altSeed": ALT_SEED}}

    # ── 会话 1：2D 确定性 / 换种子 / 无 reheat / 3D 种子 ──────────────────
    app = launch_session("s1", 9681)
    try:
        result["two_d"] = session_2d(9681)
        result["three_d"] = session_3d(9681)
        shot(9681, "04_graph3d_seeded.png", '[data-sidebar-view="graph3d"]')
    finally:
        app.stop()

    # ── 三次独立启动：同语料 + 同种子 ⇒ 冻结后的布局与截图一致 ────────────
    runs = []
    for i in range(1, 4):
        port = 9690 + i
        app = launch_session(f"s3run{i}", port)
        try:
            stable = ev(port, STABLE_JS.replace("SEED_ALT", str(ALT_SEED)).replace("SEED_DEFAULT", str(DEFAULT_SEED)))
            shot(port, f"stable3_run{i}.png")
            runs.append({"i": i, "stable": stable})
        finally:
            app.stop()
    result["three_opens"] = runs
    hashes = [r["stable"]["aHash"] for r in runs if isinstance(r.get("stable"), dict) and "aHash" in r["stable"]]
    result["three_opens_summary"] = {
        "positionHashes": hashes,
        "positionsIdentical": len(set(hashes)) == 1,
        "pngSha256": [
            hashlib.sha256((SHOTS / f"stable3_run{i}.png").read_bytes()).hexdigest()
            if (SHOTS / f"stable3_run{i}.png").is_file() else None
            for i in range(1, 4)
        ],
    }
    png = result["three_opens_summary"]["pngSha256"]
    result["three_opens_summary"]["pngIdentical"] = len(set(png)) == 1

    (HERE / "verify_seed.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
