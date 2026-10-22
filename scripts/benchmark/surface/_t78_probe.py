# -*- coding: utf-8 -*-
"""task-78 诊断 runner：复用 lazy 门禁的串行化锁 + harness，跑连续的『滚动条拖动』探针。

用法：
  python scripts/benchmark/surface/_t78_probe.py --mode pred --label t78-drag-pred
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS = HERE / "results"


def _load(name):
    spec = importlib.util.spec_from_file_location("t78_" + name, str(HERE / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="pred", choices=["pred", "legacy", "noSh"])
    ap.add_argument("--label", default="t78-drag")
    ap.add_argument("--duration", type=int, default=4000)
    ap.add_argument("--step-px", type=int, default=900)
    ap.add_argument("--jump-to", type=int, default=None)
    ap.add_argument("--load-ms", type=int, default=0, help="每 16ms 忙等 N ms（模拟并发 CPU 争用，仅用于故障注入）")
    ap.add_argument("--p2-load-ms", type=int, default=0, help="每 60ms 注入一个 P2 忙等作业（模拟 typeset 积压，仅用于故障注入）")
    ap.add_argument("--kb", default=str(REPO_ROOT / "artifacts" / "_kbwork_perf_edu"))
    ap.add_argument("--file", default="教材/08_第8章_差错控制编码.md")
    ap.add_argument("--app-rev", default="", help="密封 A/B：从该 git rev 取 app.js（临时静态副本，不改工作区）")
    args = ap.parse_args()

    gate = _load("run_lazy_gate")
    rp = _load("run_probe")
    gate._acquire_gate_lock()
    import atexit
    atexit.register(gate._release_gate_lock)

    tmp_root = None
    if args.app_rev:
        import tempfile
        tmp_root = Path(tempfile.mkdtemp(prefix="t78p_static_"))
        static_root = tmp_root / "static"
        shutil.copytree(REPO_ROOT / "src" / "memoria" / "ui" / "static", static_root)
        blob = subprocess.check_output(["git", "show", "%s:src/memoria/ui/static/app/js/app.js" % args.app_rev], cwd=str(REPO_ROOT))
        (static_root / "app" / "js" / "app.js").write_bytes(blob)
        import memoria.presentation.paths as paths
        paths.UI_STATIC_ROOT = static_root
        paths.UI_APP_INDEX = static_root / "app" / "index.html"
        import memoria.presentation.static_server as ss
        ss._STATIC_ROOT = str(static_root)
        print("[t78] app.js 来源: rev:%s" % args.app_rev)

    src_kb = Path(args.kb)
    work_kb = REPO_ROOT / "artifacts" / ("_t78_kb_%s_%d" % (args.label, os.getpid()))
    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.copytree(src_kb, work_kb)
    cfg = REPO_ROOT / "artifacts" / ("_t78_cfg_%s_%d" % (args.label, os.getpid()))
    shutil.rmtree(cfg, ignore_errors=True)
    cfg.mkdir(parents=True, exist_ok=True)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg)

    port = gate._free_port()
    harness = rp.load_harness(work_kb, port)
    import bottle
    threading.Thread(target=bottle.run, kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True), daemon=True).start()
    if not rp.wait_port(port):
        raise SystemExit("harness not ready")
    url = "http://127.0.0.1:%s/" % port
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read(1024)
            break
        except Exception:
            time.sleep(0.4)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / ("t78-drag-%s-%s.json" % (args.mode, args.label))
    cmd = ["node", str(HERE / "_t78_probe.mjs"), "--url", url, "--file", args.file,
           "--mode", args.mode, "--out", str(out), "--duration", str(args.duration), "--stepPx", str(args.step_px)]
    if args.jump_to is not None:
        cmd += ["--jumpTo", str(args.jump_to)]
    if args.load_ms:
        cmd += ["--loadMs", str(args.load_ms)]
    if args.p2_load_ms:
        cmd += ["--p2LoadMs", str(args.p2_load_ms)]
    print("[t78] " + " ".join(cmd))
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    print(cp.stdout[-4000:])
    if cp.stderr:
        print(cp.stderr[-3000:], file=sys.stderr)
    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.rmtree(cfg, ignore_errors=True)
    if tmp_root is not None:
        shutil.rmtree(tmp_root, ignore_errors=True)
    return 0 if cp.returncode == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
