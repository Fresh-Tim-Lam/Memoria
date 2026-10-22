# -*- coding: utf-8 -*-
"""task-79 单次运行器：准备 app.js 变体（仅静态副本，不改 `src/**`）→ 启动真实 app →
CDP 探针 `_t79_evict_jitter.mjs` → 杀实例 → 落 JSON。

用法：
  python scripts/benchmark/surface/_t79_run.py --variant V4 --appjs-from head --label V4-r1
  python scripts/benchmark/surface/_t79_run.py --variant V3 --appjs-from head --threshold 3 --label V3-r1
  python scripts/benchmark/surface/_t79_run.py --variant Vpre --appjs-from git:9c940796 --label Vpre-r1
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS = HERE / "results"
LAUNCHER = HERE / "_t79_launch.py"
PROBE = HERE / "_t79_evict_jitter.mjs"
APPJS_REL = "src/memoria/ui/static/app/js/app.js"
STATIC_SRC = REPO_ROOT / "src/memoria/ui/static"
DOC = "教材/08_第8章_差错控制编码.md"
CONST = "var LAZY_EVICT_PRESSURE_SCREENS = 4;"


def _utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def log(msg: str) -> None:
    print("[t79] " + msg, flush=True)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def build_appjs(src: str, threshold: int | None) -> tuple[bytes, dict]:
    if src == "head":
        data = (REPO_ROOT / APPJS_REL).read_bytes()
        origin = "head:" + subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    elif src.startswith("git:"):
        rev = src[4:]
        data = subprocess.check_output(["git", "show", f"{rev}:{APPJS_REL}"], cwd=REPO_ROOT)
        origin = "git:" + rev
    else:
        data = Path(src).read_bytes()
        origin = "file:" + str(Path(src).resolve())
    meta = {"origin": origin, "source_sha256": sha256_bytes(data)}
    if threshold is not None:
        text = data.decode("utf-8")
        if text.count(CONST) != 1:
            raise SystemExit(f"[t79] 常量锚点不唯一：{CONST!r} count={text.count(CONST)}")
        text = text.replace(CONST, f"var LAZY_EVICT_PRESSURE_SCREENS = {threshold};")
        data = text.encode("utf-8")
    meta["appjs_sha256"] = sha256_bytes(data)
    meta["threshold_requested"] = threshold
    return data, meta


def prepare_static(variant_dir: Path, appjs: bytes) -> Path:
    root = variant_dir / "static"
    if not (root / "app" / "index.html").is_file():
        shutil.rmtree(root, ignore_errors=True)
        shutil.copytree(STATIC_SRC, root)
    target = root / "app" / "js" / "app.js"
    target.write_bytes(appjs)
    return root


def port_free(port: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def wait_port(port: int, timeout: float = 60.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not port_free(port):
            return True
        time.sleep(0.5)
    return False


def wait_page(port: int, timeout: float = 90.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as r:
                items = json.loads(r.read().decode("utf-8", "replace"))
            for it in items:
                if it.get("type") == "page" and "/devtools" not in (it.get("url") or "") and it.get("webSocketDebuggerUrl"):
                    return it
        except Exception:
            pass
        time.sleep(1.0)
    return None


def kill_tree(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
    except Exception:
        pass
    # 兜底：只杀命令行里明确带本 runner 启动器的 python，避免误杀其它 app。
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*_t79_launch.py*' } | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=20)
        for line in ps.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                subprocess.run(["taskkill", "/PID", line, "/T", "/F"], capture_output=True, timeout=20)
    except Exception:
        pass


def acquire_gate_lock():
    """与惰性门禁共用同一把串行锁：测量期间禁止其它门禁/真实 app 并发跑。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("t79_gate_lock", str(HERE / "run_lazy_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._acquire_gate_lock(timeout_s=1800)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, help="臂标签（V4/V3/V6/Voff/Vpre）")
    ap.add_argument("--label", default="", help="结果文件名标签（默认 variant）")
    ap.add_argument("--appjs-from", default="head", help="head | git:<rev> | <file>")
    ap.add_argument("--threshold", type=int, default=None, help="覆盖 LAZY_EVICT_PRESSURE_SCREENS")
    ap.add_argument("--port", type=int, default=9635)
    ap.add_argument("--kb", default=str(REPO_ROOT / "artifacts" / "_kbwork_perf_edu"))
    ap.add_argument("--work-root", default="", help="复用的工作根（KB/静态副本）；空=每次自建")
    ap.add_argument("--keep-app", action="store_true")
    ap.add_argument("--no-gate-lock", action="store_true", help="不取门禁锁（仅调试；正常测量必须取）")
    args = ap.parse_args()
    _utf8_stdio()

    if not args.no_gate_lock:
        gate = acquire_gate_lock()
        atexit.register(gate._release_gate_lock)
        log("gate lock acquired")

    label = args.label or args.variant
    RESULTS.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS / f"t79-{label}.json"

    appjs, meta = build_appjs(args.appjs_from, args.threshold)
    work_root = Path(args.work_root) if args.work_root else Path(os.environ.get("TEMP", ".")) / "memoria_t79"
    work_root.mkdir(parents=True, exist_ok=True)
    variant_dir = work_root / args.variant
    static_root = prepare_static(variant_dir, appjs)

    # KB：整个 campaign 共用同一份字节副本（顺序运行，避免跨臂内容差异）
    kb = work_root / "kb"
    if not (kb / ".memoria").exists() and not any(kb.glob("*.md")):
        if kb.exists():
            shutil.rmtree(kb, ignore_errors=True)
        log(f"copy kb {args.kb} -> {kb}")
        shutil.copytree(args.kb, kb)
    cfg = work_root / ("cfg_" + label)
    shutil.rmtree(cfg, ignore_errors=True)
    cfg.mkdir(parents=True, exist_ok=True)

    if not port_free(args.port):
        log(f"port {args.port} occupied — 拒绝并发测量")
        return 3

    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "MEMORIA_MODE": "dev",
        "MEMORIA_FRAMELESS": "0",
        "MEMORIA_KB": str(kb),
        "MEMORIA_CONFIG_DIR": str(cfg),
        "MEMORIA_DEBUG": "0",
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={args.port}",
    })
    stdout = work_root / f"app_{label}.out"
    stderr = work_root / f"app_{label}.err"
    log(f"launch variant={args.variant} threshold={args.threshold} appjs={meta['appjs_sha256'][:12]}")
    with open(stdout, "wb") as fo, open(stderr, "wb") as fe:
        proc = subprocess.Popen(
            [sys.executable, str(LAUNCHER), "--static-root", str(static_root)],
            cwd=str(REPO_ROOT), env=env, stdout=fo, stderr=fe,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    t_launch = time.time()
    try:
        if not wait_port(args.port, 90):
            log("CDP 端口未就绪；stderr 尾部：")
            try:
                log(Path(stderr).read_text("utf-8", "replace")[-3000:])
            except Exception:
                pass
            return 4
        page = wait_page(args.port, 60)
        if not page:
            log("没有可用 page")
            return 4
        log(f"app ready in {time.time()-t_launch:.1f}s: {page.get('title')} {page.get('url')}")

        cmd = ["node", str(PROBE), "--port", str(args.port), "--out", str(out_json),
               "--variant", args.variant, "--doc", DOC]
        log("measure: " + " ".join(cmd))
        cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=900)
        print(cp.stdout[-12000:])
        if cp.stderr:
            print(cp.stderr[-6000:], file=sys.stderr)
        if cp.returncode != 0:
            log(f"probe exit={cp.returncode}")
            return 5
        if not out_json.is_file():
            log("probe 未产出 JSON")
            return 5
        data = json.loads(out_json.read_text("utf-8"))
        data["variantMeta"] = meta
        data["label"] = label
        data["kb"] = str(kb)
        data["appjsServed"] = str(static_root / "app" / "js" / "app.js")
        out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        log("wrote " + str(out_json))
        return 0
    finally:
        if not args.keep_app:
            kill_tree(proc.pid)
            for _ in range(40):
                if port_free(args.port):
                    break
                time.sleep(0.5)
            log("app killed / port free=" + str(port_free(args.port)))


if __name__ == "__main__":
    raise SystemExit(main())
