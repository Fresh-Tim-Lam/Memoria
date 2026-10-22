# -*- coding: utf-8 -*-
"""task-78 密封 A/B 门禁 runner：不改仓库里的 app.js，而是把 `src/memoria/ui/static`
复制到临时目录，按 `--app-rev` / `--app-file` 替换 `app/js/app.js`，再把 harness 的
静态根指向该临时目录后跑官方 `lazy_gate.mjs`。

为什么需要它：2026-10-23 收口期间 app.js 被 task-72 与 task-78 同时写（见 2072a789），
A/B 必须只变「app.js 的某个版本」这一个因子，且不能覆盖别人正在改的工作区文件。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS = HERE / "results"
GATE_MJS = HERE / "lazy_gate.mjs"


def _load(name):
    spec = importlib.util.spec_from_file_location("t78g_" + name, str(HERE / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git_show(rev: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", "%s:%s" % (rev, path)], cwd=str(REPO_ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-rev", default="", help="从该 git rev 取 app.js（与 --app-file 二选一）")
    ap.add_argument("--app-file", default="", help="用该本地文件覆盖 app.js")
    ap.add_argument("--kb", default=str(REPO_ROOT / "artifacts" / "_kbwork_perf_edu"))
    ap.add_argument("--scenarios", default=str(HERE / "scenarios" / "lazy-gate-4001.json"))
    ap.add_argument("--label", default="t78sealed")
    ap.add_argument("--tail-mode", default="", choices=["", "legacy", "pred", "noSh"])
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    gate = _load("run_lazy_gate")
    gate._acquire_gate_lock()
    import atexit
    atexit.register(gate._release_gate_lock)

    spec = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    fixture_path = (REPO_ROOT / spec["fixture"]["path"]).resolve()

    # 1) 临时静态根（复制整棵 static，只替换 app.js）
    tmp_root = Path(tempfile.mkdtemp(prefix="t78_static_"))
    static_root = tmp_root / "static"
    shutil.copytree(REPO_ROOT / "src" / "memoria" / "ui" / "static", static_root)
    app_dst = static_root / "app" / "js" / "app.js"
    if args.app_file:
        shutil.copyfile(args.app_file, app_dst)
        app_src = args.app_file
    else:
        app_dst.write_bytes(_git_show(args.app_rev, "src/memoria/ui/static/app/js/app.js"))
        app_src = "rev:" + args.app_rev
    print("[t78g] app.js 来源: %s（%d bytes）" % (app_src, app_dst.stat().st_size))

    # 2) 把 harness 的静态根指向副本（必须在导入 _harness / static_server 之前/之后都改）
    import memoria.presentation.paths as paths
    paths.UI_STATIC_ROOT = static_root
    paths.UI_APP_INDEX = static_root / "app" / "index.html"
    import memoria.presentation.static_server as ss
    ss._STATIC_ROOT = str(static_root)

    # 3) 复制 KB（与官方门禁同口径）
    src_kb = Path(args.kb)
    work_kb = REPO_ROOT / "artifacts" / ("_t78g_kb_%s_%d" % (args.label, os.getpid()))
    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.copytree(src_kb, work_kb)
    cfg = REPO_ROOT / "artifacts" / ("_t78g_cfg_%s_%d" % (args.label, os.getpid()))
    shutil.rmtree(cfg, ignore_errors=True)
    cfg.mkdir(parents=True, exist_ok=True)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg)

    port = gate._free_port()
    rp = gate._load_run_probe()
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

    # 4) 直接复用官方 lazy_gate.mjs（不改门禁；只换被测静态文件）
    RESULTS.mkdir(parents=True, exist_ok=True)
    raw = RESULTS / ("raw-t78sealed-%s.json" % args.label)
    if raw.exists():
        raw.unlink()
    cmd = ["node", str(GATE_MJS), "--scenarios", args.scenarios, "--out", str(raw),
           "--url", url, "--label", args.label]
    if args.tail_mode:
        cmd += ["--tail-mode", args.tail_mode]
    print("[t78g] " + " ".join(cmd))
    t0 = time.time()
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=args.timeout)
    if cp.stdout:
        print(cp.stdout.strip()[-3000:])
    if cp.stderr:
        print(cp.stderr.strip()[-3000:], file=sys.stderr)
    if not raw.is_file():
        print("[t78g] 未产出 JSON", file=sys.stderr)
        return 3
    out = json.loads(raw.read_text(encoding="utf-8"))
    out["meta"] = {"label": args.label, "appSrc": app_src, "sha": gate.git_short_sha(),
                   "startedAt": datetime.now(timezone.utc).isoformat(),
                   "elapsedMs": int((time.time() - t0) * 1000), "sealed": True}
    raw.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    ls = out.get("longScroll") or {}
    print("[t78g] PASS=%s checks=%s maxMaterialized=%s domLimit=%s evictDelta=%s peakΔMB=%s retainedΔMB=%s" % (
        (out.get("summary") or {}).get("pass"), (out.get("summary") or {}).get("checks"),
        ls.get("maxMaterialized"), ls.get("domLimit"), ls.get("evictDeltaDuringLongScroll"),
        ls.get("peakDeltaMb"), ls.get("retainedDeltaMb")))
    for c in out.get("checks") or []:
        if c.get("status") != "PASS":
            print("[t78g] FAIL %s" % c.get("id"))
            for s in c.get("steps") or []:
                for a in s.get("assertions") or []:
                    if not a.get("ok"):
                        print("   ✗ %s / %s: expected %s actual %s" % (s.get("step"), a.get("name"), a.get("expected"), a.get("actual")))
    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.rmtree(cfg, ignore_errors=True)
    shutil.rmtree(tmp_root, ignore_errors=True)
    return 0 if (out.get("summary") or {}).get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
