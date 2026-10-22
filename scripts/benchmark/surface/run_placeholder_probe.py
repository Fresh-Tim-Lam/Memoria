# -*- coding: utf-8 -*-
"""W3.4 占位高度估值准确性 —— 可复跑对比探针运行器。

做三件事：
  1) 复制语料到工作副本（绝不写用户 KB），起 `_harness.py` 同款静态服务 + /rpc 桥；
  2) 起 Node `placeholder_probe.mjs`：同页先 `__MEMORIA_LAZY=false` 全量渲染量
     `scrollHeight` 真值，再 `__MEMORIA_LAZY=true` 惰性渲染量估值，输出逐类型误差表；
  3) 落可机读 JSON + 人读 TXT，并打印「偏差 / 滚动极差」。

用法：
    python scripts/benchmark/surface/run_placeholder_probe.py --label ph-baseline
    python scripts/benchmark/surface/run_placeholder_probe.py --label ph-after --with-lazy-gate
    # 可选：--file 教材/08_第8章_差错控制编码.md --kb <kb 目录> --scroll-steps 24
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
RESULTS_DIR = HERE / "results"
PROBE_MJS = HERE / "placeholder_probe.mjs"
DEFAULT_KB = Path(r"D:\AAA_Jupyter\Memoria\artifacts\_kbwork_perf_edu")
DEFAULT_FILE = "教材/08_第8章_差错控制编码.md"

_GATE_LOCK = os.path.join(tempfile.gettempdir(), "memoria_lazy_gate.lock")


def _load_run_probe():
    spec = importlib.util.spec_from_file_location("memoria_ph_probe", str(HERE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _acquire_lock(timeout_s=1800):
    start = time.time()
    while True:
        try:
            fd = os.open(_GATE_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, ("%d %f" % (os.getpid(), time.time())).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(_GATE_LOCK) > 3600:
                    os.unlink(_GATE_LOCK)
                    continue
            except OSError:
                pass
            if time.time() - start > timeout_s:
                raise SystemExit("[ph] 另一个测量实例在跑（锁 %s），拒绝并发测量。" % _GATE_LOCK)
            time.sleep(2.0)


def _release_lock():
    try:
        os.unlink(_GATE_LOCK)
    except OSError:
        pass


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT),
                                       stderr=subprocess.DEVNULL).decode().strip() or "nogit"
    except Exception:
        return "nogit"


def main() -> int:
    _acquire_lock()
    import atexit
    atexit.register(_release_lock)
    ap = argparse.ArgumentParser(description="W3.4 占位高度估值对比探针")
    ap.add_argument("--kb", default=str(DEFAULT_KB))
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--label", default="ph-probe")
    ap.add_argument("--scroll-steps", type=int, default=24)
    ap.add_argument("--scroll-pause-ms", type=int, default=220)
    ap.add_argument("--settle-ms", type=int, default=1500)
    ap.add_argument("--settle-timeout-ms", type=int, default=120000)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--with-lazy-gate", action="store_true",
                    help="顺带串行跑 run_lazy_gate.py（6/6 证据）")
    ap.add_argument("--dump-blocks", action="store_true", help="额外落逐块明细（.blocks.json，供离线分析）")
    ap.add_argument("--viewport", default="", help="覆盖视口尺寸，如 1000x700（默认沿用 headless 窗口）")
    args = ap.parse_args()

    src_kb = Path(args.kb)
    if not src_kb.is_dir():
        print("[ph] KB 不存在: %s" % src_kb, file=sys.stderr)
        return 2
    if not (src_kb / args.file).is_file():
        print("[ph] 文档不存在: %s" % (src_kb / args.file), file=sys.stderr)
        return 2

    port = _free_port()
    work_kb = REPO_ROOT / "artifacts" / ("_ph_probe_kb_%s_%d" % (args.label, os.getpid()))
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, work_kb)
    cfg_dir = work_kb.parent / ("_ph_probe_config_%s_%d" % (args.label, os.getpid()))
    if cfg_dir.exists():
        shutil.rmtree(cfg_dir, ignore_errors=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)
    print("[ph] 工作副本: %s" % work_kb)
    print("[ph] 密封配置目录: %s" % cfg_dir)

    rp = _load_run_probe()
    harness = rp.load_harness(work_kb, port)
    import bottle
    threading.Thread(target=bottle.run,
                     kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
                     daemon=True).start()
    if not rp.wait_port(port):
        print("[ph] harness 未就绪", file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % port
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read(1024)
            break
        except Exception:
            time.sleep(0.4)
    print("[ph] harness 就绪: %s" % url)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sha = _git_sha()
    stem = "placeholder-%s_%s" % (args.label, sha)
    out_path = RESULTS_DIR / ("%s.json" % stem)
    if out_path.exists():
        out_path.unlink()
    cmd = ["node", str(PROBE_MJS),
           "--out", str(out_path), "--url", url, "--file", args.file,
           "--scroll-steps", str(args.scroll_steps),
           "--scroll-pause-ms", str(args.scroll_pause_ms),
           "--settle-ms", str(args.settle_ms),
           "--settle-timeout-ms", str(args.settle_timeout_ms)]
    if args.dump_blocks:
        cmd.append("--dump-blocks")
    if args.viewport:
        cmd += ["--viewport", args.viewport]
    print("[ph] 起 node: %s" % " ".join(cmd))
    t0 = time.time()
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=args.timeout)
    elapsed = time.time() - t0
    if cp.stdout:
        print(cp.stdout.strip()[-4000:])
    if cp.stderr:
        print("[ph] node stderr:\n%s" % cp.stderr.strip()[-4000:], file=sys.stderr)
    if not out_path.is_file():
        print("[ph] 未产出 JSON（node returncode=%s）" % cp.returncode, file=sys.stderr)
        return 3
    out = json.loads(out_path.read_text(encoding="utf-8"))
    # 不采信不可信测量
    if not (out.get("measurement") or {}).get("trusted"):
        print("[ph] 测量可信门未过（rAF p50 > 20ms）⇒ 本次读数不可采信", file=sys.stderr)
        return 4
    out["meta"] = {"label": args.label, "sha": sha,
                   "startedAt": datetime.now(timezone.utc).isoformat(),
                   "elapsedMs": int(elapsed * 1000)}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[ph] 结论：全量 %s px vs 惰性 %s px ⇒ 偏差 %s%%（目标 |Δ|≤2%%）"
          % (out["full"]["scrollHeight"], out["lazy"]["scrollHeight"], out["deltaPct"]))
    print("[ph] 滚动期 scrollHeight 极差：%s px = %s%%"
          % (out["scrollTrace"]["spreadPx"], out["scrollTrace"]["spreadPct"]))
    print("[ph] 逐类型：")
    for r in out["perType"]:
        print("    %-16s n=%-5s real=%-8s est=%-8s pct=%s"
              % (r["type"], r["count"], r["meanRealH"], r["meanEstH"],
                 ("%+.2f%%" % r["pct"]) if r["pct"] is not None else "—"))
    print("[ph] 产物：\n  %s\n  %s" % (out_path, out_path.with_suffix(".txt")))

    rc = 0 if out.get("checks", {}).get("within2pct") else 1
    if args.with_lazy_gate:
        print("\n[ph] 串行跑惰性交互门禁（--with-lazy-gate）...")
        g = subprocess.run([sys.executable, str(HERE / "run_lazy_gate.py"), "--label", "ph-" + args.label],
                           cwd=str(REPO_ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=dict(os.environ))
        print((g.stdout or "").strip()[-3000:])
        if g.stderr:
            print((g.stderr or "").strip()[-1500:], file=sys.stderr)
        out["lazyGate"] = {"ok": g.returncode == 0, "returncode": g.returncode}
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        if g.returncode != 0:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
