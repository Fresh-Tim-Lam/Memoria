"""task-149 A 提案：图谱可视化的渲染/性能实测（不改 src）。

实测项：
 P1 真实图数据规模：node/link/group 数（docs/example/AAA_Vocab 的临时副本，只读源）
 P2 2D 真实 draw() 成本：force/galaxy × nodeRadius 4/6/9/12，以及合成 canvas 基准
    （uniform r=6 vs varied r=6..14；分项：背景/边/节点/标签）
 P3 3D 真实成本：renderer.info（draw calls/triangles）、_render() 与 _syncPositions() 耗时
 P4 3D 合成基准：1000 节点场景 —— (a) 共享几何+共享材质 1000 mesh vs
    (b) 每节点独立材质 vs (c) InstancedMesh 1 draw；含 gl.finish() 口径
 P5 3D 标签 sprite 数量与 draw call 占比
输出：viz-bench.json
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
WORK = Path(os.environ.get("TEMP", ".")) / "memoria_viz"
CDP_PORT = 9621
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
TOOLS = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-93-responsive"
LAUNCH = TOOLS / "launch_ctl.py"
PROBE = REPO / "artifacts" / "agent" / "verify" / "todo" / "0.4.7-task-112-d4b" / "probe112.mjs"
SRC_KB = REPO / "docs" / "example" / "AAA_Vocab"


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2); return True
    except Exception:  # noqa: BLE001
        return False


def probe(cmds):
    (WORK / "probe-cmd.json").write_text(json.dumps({"cmds": cmds}), encoding="utf-8")
    p = subprocess.run(["node", str(PROBE), "--port", str(CDP_PORT), "--cmd", str(WORK / "probe-cmd.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
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


SYNTH2D = """(() => {
  const sizes = [300, 800, 1500, 3000];
  const out = {};
  function drawOnce(ctx, w, h, N, varied, withLabels) {
    const nodes = [];
    for (let i = 0; i < N; i++) {
      nodes.push({ x: (i * 37) % w, y: (i * 53) % h, id: 'n' + i, name: 'L' + i, range_ok: true });
    }
    // 每节点 1.6 条边，模拟典型图密度
    const links = [];
    for (let i = 0; i < N * 1.6; i++) links.push([i % N, (i * 7 + 3) % N]);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#161b22'; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#58a6ff'; ctx.fillStyle = '#58a6ff'; ctx.lineWidth = 1.2; ctx.globalAlpha = 0.45;
    for (const [a, b] of links) {
      const s = nodes[a], t = nodes[b];
      ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(t.x, t.y); ctx.lineTo(t.x - 4, t.y - 2); ctx.lineTo(t.x - 4, t.y + 2); ctx.closePath(); ctx.fill();
    }
    ctx.globalAlpha = 1;
    for (const n of nodes) {
      const r = varied ? 6 + ((n.id.charCodeAt(1) * 7) % 9) : 6;
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fillStyle = '#c9d1d9'; ctx.fill();
      if (withLabels) {
        ctx.font = '10px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        ctx.lineWidth = 3; ctx.strokeStyle = '#0d1117'; ctx.strokeText(n.name, n.x, n.y + r + 4);
        ctx.fillStyle = '#adbac7'; ctx.fillText(n.name, n.x, n.y + r + 4);
      }
    }
  }
  for (const N of sizes) {
    const canvas = document.createElement('canvas');
    canvas.width = 900; canvas.height = 700;
    const ctx = canvas.getContext('2d');
    for (const variant of [
      { key: 'uniform_nodes_only', varied: false, labels: false },
      { key: 'varied_nodes_only', varied: true, labels: false },
      { key: 'uniform_with_labels', varied: false, labels: true },
      { key: 'varied_with_labels', varied: true, labels: true },
    ]) {
      // 预热
      drawOnce(ctx, 900, 700, N, variant.varied, variant.labels);
      const t0 = performance.now();
      const REPS = 10;
      for (let k = 0; k < REPS; k++) drawOnce(ctx, 900, 700, N, variant.varied, variant.labels);
      const ms = (performance.now() - t0) / REPS;
      out['N=' + N + '/' + variant.key] = Math.round(ms * 100) / 100;
    }
  }
  return out;
})()"""

SYNTH3D = """(() => {
  const THREE = window.THREE;
  if (!THREE) return { error: 'no-THREE' };
  const size = { w: 900, h: 700 };
  const canvas = document.createElement('canvas');
  canvas.width = size.w; canvas.height = size.h;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false });
  renderer.setPixelRatio(1);
  renderer.setSize(size.w, size.h, false);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(50, size.w / size.h, 0.1, 5000);
  camera.position.set(0, 0, 900);
  const geom = new THREE.SphereGeometry(1, 16, 12); // 单位球：逐节点缩放即可，无需拆几何体
  function bench(name, build) {
    const sub = new THREE.Scene();
    const objs = build(sub);
    // 预热
    renderer.render(sub, camera);
    renderer.getContext().finish();
    const REPS = 20;
    const t0 = performance.now();
    for (let k = 0; k < REPS; k++) renderer.render(sub, camera);
    renderer.getContext().finish();
    const ms = (performance.now() - t0) / REPS;
    const info = renderer.info.render;
    return [name, { msPerFrame: Math.round(ms * 100) / 100, drawCalls: info.calls,
                    triangles: info.triangles, geometries: renderer.info.memory.geometries,
                    textures: renderer.info.memory.textures }];
  }
  const N = 1000;
  const out = {};
  const positions = [];
  for (let i = 0; i < N; i++) {
    const a = i * 2.399963; const r = Math.sqrt(i / N) * 260;
    positions.push([Math.cos(a) * r, Math.sin(a) * r, (i % 7) * 2 - 6]);
  }
  // (a) 共享几何 + 共享材质，1000 个 Mesh（现有实现是共享几何但每节点材质）
  out.sharedGeomSharedMat = bench('sharedGeomSharedMat', (s) => {
    const mat = new THREE.MeshStandardMaterial({ color: 0xc9d1d9 });
    for (const p of positions) {
      const m = new THREE.Mesh(geom, mat);
      m.position.set(p[0], p[1], p[2]);
      m.scale.setScalar(1 + (p[0] % 3) * 0.2);
      s.add(m);
    }
    return s;
  })[1];
  // (b) 共享几何 + 每节点独立材质（现有 3D 实现）
  out.sharedGeomPerNodeMat = bench('sharedGeomPerNodeMat', (s) => {
    for (const p of positions) {
      const mat = new THREE.MeshStandardMaterial({ color: 0xc9d1d9, roughness: 0.55, metalness: 0.08 });
      const m = new THREE.Mesh(geom, mat);
      m.position.set(p[0], p[1], p[2]);
      m.scale.setScalar(1 + ((p[0] + 3) % 3) * 0.2);
      s.add(m);
    }
    return s;
  })[1];
  // (c) InstancedMesh：1 draw call
  out.instancedMesh = bench('instancedMesh', (s) => {
    const mat = new THREE.MeshStandardMaterial({ color: 0xc9d1d9 });
    const inst = new THREE.InstancedMesh(geom, mat, N);
    const dummy = new THREE.Object3D();
    for (let i = 0; i < N; i++) {
      dummy.position.set(positions[i][0], positions[i][1], positions[i][2]);
      dummy.scale.setScalar(1 + ((positions[i][0] + 3) % 3) * 0.2);
      dummy.updateMatrix();
      inst.setMatrixAt(i, dummy.matrix);
    }
    inst.instanceMatrix.needsUpdate = true;
    s.add(inst);
    return s;
  })[1];
  // (d) 标签 sprite：1000 个 sprite 的 draw call 成本
  out.labelSprites1000 = bench('labelSprites1000', (s) => {
    const c = document.createElement('canvas'); c.width = 64; c.height = 16;
    const cx = c.getContext('2d'); cx.fillStyle = '#000'; cx.fillRect(0, 0, 64, 16);
    cx.fillStyle = '#fff'; cx.font = '10px sans-serif'; cx.fillText('label', 2, 12);
    const tex = new THREE.CanvasTexture(c);
    for (let i = 0; i < N; i++) {
      const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
      spr.position.set(positions[i][0], positions[i][1], positions[i][2]);
      s.add(spr);
    }
    return s;
  })[1];
  // (e) 边：1600 条"每边独立 Line"（现有实现）vs 合并 LineSegments 1 draw
  const edgeEnds = [];
  for (let i = 0; i < 1600; i++) edgeEnds.push([i % N, (i * 7 + 3) % N]);
  out.edges1600_individualLines = bench('edges1600_individualLines', (s) => {
    for (const [a, b] of edgeEnds) {
      const g = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(positions[a][0], positions[a][1], positions[a][2]),
        new THREE.Vector3(positions[b][0], positions[b][1], positions[b][2]),
      ]);
      s.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.55 })));
    }
    return s;
  })[1];
  out.edges1600_mergedLineSegments = bench('edges1600_mergedLineSegments', (s) => {
    const arr = new Float32Array(edgeEnds.length * 6);
    for (let i = 0; i < edgeEnds.length; i++) {
      const [a, b] = edgeEnds[i];
      arr[i * 6] = positions[a][0]; arr[i * 6 + 1] = positions[a][1]; arr[i * 6 + 2] = positions[a][2];
      arr[i * 6 + 3] = positions[b][0]; arr[i * 6 + 4] = positions[b][1]; arr[i * 6 + 5] = positions[b][2];
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3));
    s.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x58a6ff, transparent: true, opacity: 0.55 })));
    return s;
  })[1];
  // (f) 每帧更新 1600 条边坐标：独立 geometry vs 合并 buffer（typed array 一次上传）
  {
    const t0 = performance.now();
    const REPS = 200;
    // individual
    const indiv = [];
    for (let i = 0; i < 1600; i++) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
      indiv.push(g);
    }
    for (let k = 0; k < REPS; k++) {
      for (let i = 0; i < 1600; i++) {
        const p = indiv[i].attributes.position;
        p.setXYZ(0, i % 100, 0, 0); p.setXYZ(1, (i * 3) % 100, 1, 0);
        p.needsUpdate = true;
      }
    }
    const indivMs = (performance.now() - t0) / REPS;
    // merged
    const mergedArr = new Float32Array(1600 * 6);
    const mergedGeom = new THREE.BufferGeometry();
    mergedGeom.setAttribute('position', new THREE.BufferAttribute(mergedArr, 3));
    const t1 = performance.now();
    for (let k = 0; k < REPS; k++) {
      for (let i = 0; i < 1600; i++) {
        mergedArr[i * 6] = i % 100; mergedArr[i * 6 + 1] = 0; mergedArr[i * 6 + 2] = 0;
        mergedArr[i * 6 + 3] = (i * 3) % 100; mergedArr[i * 6 + 4] = 1; mergedArr[i * 6 + 5] = 0;
      }
      mergedGeom.attributes.position.needsUpdate = true;
    }
    const mergedMs = (performance.now() - t1) / REPS;
    out.edgeUpdatePerFrame1600 = { individualGeomsMs: Math.round(indivMs * 100) / 100,
                                   mergedBufferMs: Math.round(mergedMs * 100) / 100 };
  }
  renderer.dispose();
  return out;
})()"""

REAL = """(() => {
  const st = window.state || {};
  const e = st.graphEngine;
  const v2 = st.graphView2d;
  const out = { nodes: e ? e.nodes.length : null, links: e ? e.links.length : null,
                groups: e && e.groups ? (e.groups.groups ? e.groups.groups.length : null) : null,
                has2d: !!v2, has3d: !!st.graphView3d };
  if (v2) {
    // 先把面板显示/尺寸落定（否则 canvas 宽高可能是 0/1，draw() 量出来是 0ms 假数据）
    out.container2d = v2.container ? { w: v2.container.clientWidth, h: v2.container.clientHeight } : null;
    try { v2.container.style.width = '260px'; v2.container.style.height = '560px'; } catch (_) {}
    try { v2.onPanelShown(); } catch (_) {}
    try { v2.reflow(); } catch (_) {}
    function benchDraw(n) {
      v2.draw();
      const t0 = performance.now();
      for (let i = 0; i < n; i++) v2.draw();
      return Math.round(((performance.now() - t0) / n) * 100) / 100;
    }
    out.view2d = { w: v2.viewW, h: v2.viewH, active: v2.active,
                   forceRadius6: benchDraw(20) };
    // nodeRadius 变体
    out.nodeRadiusCost = {};
    for (const r of [4, 6, 9, 12]) {
      v2.opts.nodeRadius = r;
      out.nodeRadiusCost['r=' + r] = benchDraw(15);
    }
    v2.opts.nodeRadius = 6;
    // galaxy 风格
    const oldStyle = v2.opts.graphStyle;
    v2.opts.graphStyle = 'galaxy';
    out.nodeRadiusCost.galaxy_r6 = benchDraw(15);
    v2.opts.graphStyle = oldStyle;
  }
  if (st.graphView3d) {
    const v3 = st.graphView3d;
    // 让 3D 面板真正可见并完成首次布局/建图（否则 _nodeMeshes 为空，draw call 全 0）
    out.container3d = v3.container ? { w: v3.container.clientWidth, h: v3.container.clientHeight } : null;
    try { v3.container.style.width = '260px'; v3.container.style.height = '560px'; } catch (_) {}
    try { v3.onPanelShown(); } catch (_) {}
    try { v3.reflow(); } catch (_) {}
    try { v3.start(); } catch (_) {}
    const info = v3.renderer ? v3.renderer.info : null;
    function bench(fn, n) {
      fn();
      const t0 = performance.now();
      for (let i = 0; i < n; i++) fn();
      return Math.round(((performance.now() - t0) / n) * 100) / 100;
    }
    out.view3d = {
      active: v3.active,
      nodes: v3._nodeMeshes ? v3._nodeMeshes.size : null,
      labels: v3._labelSprites ? v3._labelSprites.size : null,
      halos: v3._haloSprites ? v3._haloSprites.size : null,
      edges: v3._edgeLines ? v3._edgeLines.length : null,
      render: info ? { calls: info.render.calls, triangles: info.render.triangles,
                       geometries: info.memory.geometries, textures: info.memory.textures } : null,
      renderMs: bench(() => v3._render(), 10),
      syncPositionsMs: bench(() => v3._syncPositions(), 10),
    };
    // Q4 深度线索实测：相机距离范围 ⇒ 同样 world 半径的"近大远小"倍率（透视混淆量化）
    try {
      const cam = v3.camera;
      const nodes = v3.layout.nodes || [];
      if (cam && nodes.length) {
        const cp = cam.position;
        const ds = nodes.map((n) => Math.sqrt((n.x - cp.x) ** 2 + (n.y - cp.y) ** 2 + (n.z - cp.z) ** 2));
        ds.sort((a, b) => a - b);
        const minD = ds[0], maxD = ds[ds.length - 1];
        out.view3d.depth = {
          fov: cam.fov, cameraPos: [cp.x, cp.y, cp.z],
          nodeDistanceMin: Math.round(minD * 100) / 100,
          nodeDistanceMax: Math.round(maxD * 100) / 100,
          nodeDistanceP50: Math.round(ds[Math.floor(ds.length / 2)] * 100) / 100,
          // 同一 world 半径下，最近节点在屏幕上的半径是"最远节点"的多少倍
          apparentRadiusRatioMax: Math.round((maxD / minD) * 100) / 100,
        };
      }
    } catch (_) {}
  }
  return out;
})()"""


def main() -> int:
    os.makedirs(WORK, exist_ok=True)
    kb = WORK / "AAA_Vocab"
    if kb.exists(): shutil.rmtree(kb)
    shutil.copytree(SRC_KB, kb)
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
    out = (WORK / "app.out.log").open("w", encoding="utf-8")
    err = (WORK / "app.err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, str(LAUNCH)], cwd=str(REPO), env=env, stdout=out, stderr=err)
    res = {}
    try:
        for _ in range(160):
            if up(f"http://127.0.0.1:{CDP_PORT}/json/version"): break
            time.sleep(0.5)
        time.sleep(7)
        ctl({"op": "foreground"})
        time.sleep(0.8)
        # 打开左栏 graph2d 页签（触发图谱加载/初始化）
        ev("(() => { const t = document.querySelector('[data-sidebar-tab=\"graph2d\"]'); if (t) t.click(); return !!t; })()")
        time.sleep(2.5)
        ready = ev("(() => !!(window.state && window.state.graphEngine && window.state.graphEngine.nodes && window.state.graphEngine.nodes.length))()")
        if not ready:
            # 有些路径需要先开一个文件
            ev("(() => { window.__OPEN='pending'; window.MemoriaApp.openFile('README.md').then(function(r){window.__OPEN=(r&&r.status)||'done';}); return true; })()")
            time.sleep(2)
            ev("(() => { const t = document.querySelector('[data-sidebar-tab=\"graph2d\"]'); if (t) t.click(); return !!t; })()")
            time.sleep(2.5)
        res["real"] = ev(REAL)
        res["synth2d"] = ev(SYNTH2D)
        # 3D：切 3D 页签后测
        ev("(() => { const t = document.querySelector('[data-sidebar-tab=\"graph3d\"]'); if (t) t.click(); return !!t; })()")
        time.sleep(3.5)
        ev("(() => { if (window.state && window.state.graphView3d) { try { window.state.graphView3d.start(); } catch(e) {} } return true; })()")
        time.sleep(1.5)
        res["real3d"] = ev(REAL)
        res["synth3d"] = ev(SYNTH3D)
        (HERE / "viz-bench.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"real": res["real"], "real3d": res.get("real3d"), "synth2d": res["synth2d"],
                          "synth3d": res.get("synth3d")}, ensure_ascii=False, indent=1))
        return 0
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        out.close(); err.close()


if __name__ == "__main__":
    raise SystemExit(main())
