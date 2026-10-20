# -*- coding: utf-8 -*-
"""交互契约测试运行器（interaction runner）。

做什么：
  1) 复用 `run_probe.py` 的 `load_harness()`（bottle 静态服务 + `/rpc` → UIAPI +
     注入假 `window.pywebview.api` 桥），把**任意知识库**当语料起一个本地服务；
  2) 起 Node 子进程 `interaction.mjs --scenarios`，用 CDP `Input` 域发**受信任**的
     鼠标/键盘/IME 事件，跑剧本；
  3) 每个剧本抓「选区 + 块文本」快照 ⇒ 作为**新老实现对比的金标准**。

为什么复用 run_probe 而不是另写：服务与桥的逻辑已经在 `_harness.py` 里，重复实现只会漂移。

用法：
    # 先只跑旧实现，产出金标准
    python scripts/benchmark/surface/run_interaction.py \
        --kb artifacts/baseline-kb/数字通信原理 \
        --scenarios scripts/benchmark/surface/scenarios/interactions.json \
        --label legacy-golden

产物：`scripts/benchmark/surface/results/interaction-<label>_<sha>.{json,md}`
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
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS_DIR = HERE / "results"
CDP_MJS = HERE / "interaction.mjs"
DEFAULT_SCENARIOS = HERE / "scenarios" / "interactions.json"


def _load_run_probe():
    """把 run_probe.py 当模块加载（它有 __main__ 守卫，导入不会执行 main）。"""
    spec = importlib.util.spec_from_file_location("memoria_run_probe", str(HERE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_short_sha() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT))
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return "nogit"


def build_md(meta: dict, raw: dict) -> str:
    lines = []
    lines.append("# 交互契约测试：%s" % meta["label"])
    lines.append("")
    lines.append("- 时间：%s" % meta["startedAt"])
    lines.append("- commit：`%s`" % meta["sha"])
    lines.append("- 语料：`%s`" % meta["kb"])
    lines.append("- 剧本：`%s`（%d 个）" % (meta["scenarios"], meta["count"]))
    lines.append("- 浏览器：%s" % meta.get("browser", "?"))
    lines.append("")
    ok = meta["failed"] == 0
    lines.append("## 结论：%s" % ("✅ 全部剧本跑通" if ok else "❌ %d 个剧本报错" % meta["failed"]))
    lines.append("")
    lines.append("| 剧本 | 状态 | 快照数 | 选区摘要 |")
    lines.append("|---|---|---|---|")
    results = raw.get("results") or []
    for r in results:
        snaps = r.get("snapshots") or {}
        last = None
        for _, v in snaps.items():
            last = v
        sel = (last or {}).get("selection") or {}
        sel_desc = "—"
        if sel:
            a = sel.get("anchor") or {}
            f = sel.get("focus") or {}
            sel_desc = "`%s` | a=%s@%s f=%s@%s collapsed=%s" % (
                (sel.get("text") or "").replace("\n", " ")[:24],
                a.get("blockIndex"), a.get("offset"),
                f.get("blockIndex"), f.get("offset"),
                sel.get("collapsed"),
            )
        lines.append("| %s | %s | %d | %s |" % (
            r.get("id"), "❌ " + (r.get("error") or "") if r.get("error") else "✅", len(snaps), sel_desc))
    lines.append("")
    lines.append("> 快照明细见同名 `.json`。新实现落地后用同一剧本再跑一次，逐剧本 diff 快照即可判「交互是否一致」。")
    return "\n".join(lines) + "\n"


def _free_port() -> int:
    """要一个当前空闲的本地端口（避免并发跑时撞车）。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _port_busy(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="交互契约测试运行器")
    ap.add_argument("--kb", default="artifacts/baseline-kb/数字通信原理", help="语料库目录（相对 repo 根）")
    ap.add_argument("--scenarios", default=str(DEFAULT_SCENARIOS), help="剧本 json")
    ap.add_argument("--label", default="legacy-golden", help="本次运行 label")
    # 并发安全：默认自动选空闲端口；显式指定则要求该端口确实空闲（否则快速失败，不劫持别人的服务）
    ap.add_argument("--port", type=int, default=0, help="harness 端口（0=自动选空闲端口；显式指定时若被占用则失败）")
    ap.add_argument("--work-kb", default="", help="临时语料副本目录（留空=按 label+pid 自动唯一）")
    ap.add_argument("--timeout", type=int, default=900, help="node 子进程超时秒")
    args = ap.parse_args()

    src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[ix] 语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2
    scen_path = Path(args.scenarios)
    if not scen_path.is_absolute():
        scen_path = (REPO_ROOT / args.scenarios).resolve()
    if not scen_path.is_file():
        print("[ix] 剧本不存在: %s" % scen_path, file=sys.stderr)
        return 2

    # 端口：0=自动挑；显式端口被占用 ⇒ 快速失败并说明（以前是静默劫持/撞车，导致 11 剧本全红）
    if args.port == 0:
        port = _free_port()
        print("[ix] 自动选择空闲端口: %d" % port)
    else:
        if _port_busy(args.port):
            print("[ix] 端口 %d 已被占用（另一个 benchmark 正在跑？）——请换端口或让它结束；"
                  "也可不传 --port 让脚本自动选。" % args.port, file=sys.stderr)
            return 2
        port = args.port
    args.port = port

    # 工作副本：绝不在原库上跑（会写 .memoria / 改 md）；并发跑必须各自独立目录
    work_kb_rel = args.work_kb or ("artifacts/_interaction_kb_%s_%d" % (args.label, os.getpid()))
    work_kb = (REPO_ROOT / work_kb_rel).resolve()
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, work_kb)
    print("[ix] 语料副本: %s -> %s" % (src_kb, work_kb))

    rp = _load_run_probe()
    harness = rp.load_harness(work_kb, args.port)
    import bottle  # harness 已导入
    th = threading.Thread(
        target=bottle.run,
        kwargs=dict(app=harness.app, host="127.0.0.1", port=args.port, quiet=True),
        daemon=True,
    )
    th.start()
    if not rp.wait_port(args.port):
        print("[ix] harness 未在端口 %s 起来" % args.port, file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % args.port
    # 预热：确保 harness 的路由/桥接已完成首次初始化（否则首个 openFile 可能拿到「API 不可用」）
    import urllib.request
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read(1024)
            break
        except Exception:
            time.sleep(0.4)
    print("[ix] harness 就绪（已预热）: %s" % url)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    sha = git_short_sha()
    stem = "interaction-%s_%s" % (args.label, sha)
    raw_path = RESULTS_DIR / ("raw-%s.json" % stem)
    md_path = RESULTS_DIR / ("%s.md" % stem)

    cmd = [
        "node", str(CDP_MJS),
        "--scenarios", str(scen_path),
        "--out", str(raw_path),
        "--url", url,
        "--label", args.label,
    ]
    print("[ix] 起 node: %s" % " ".join(cmd))
    t0 = time.time()
    try:
        cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[ix] node 子进程超时", file=sys.stderr)
        return 3
    elapsed = time.time() - t0
    if cp.stdout:
        print(cp.stdout.strip()[:2000])
    if cp.returncode != 0 and cp.stderr:
        print("[ix] node stderr:\n%s" % cp.stderr.strip()[:4000], file=sys.stderr)

    if not raw_path.is_file():
        print("[ix] 未产出 raw json：%s" % raw_path, file=sys.stderr)
        return 3

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    results = raw.get("results") or []
    failed = sum(1 for r in results if r.get("error"))
    meta = {
        "label": args.label, "sha": sha, "startedAt": started,
        "kb": str(src_kb.relative_to(REPO_ROOT)) if str(src_kb).startswith(str(REPO_ROOT)) else str(src_kb),
        "scenarios": str(scen_path.name), "count": len(results),
        "browser": raw.get("browser"), "failed": failed, "elapsedMs": int(elapsed * 1000),
    }
    md_path.write_text(build_md(meta, raw), encoding="utf-8")
    print("\n[ix] 产物：\n  %s\n  raw: %s" % (md_path, raw_path))
    print("[ix] 剧本 %d 个，失败 %d 个，用时 %.1fs" % (len(results), failed, elapsed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
