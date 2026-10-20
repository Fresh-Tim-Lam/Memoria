# -*- coding: utf-8 -*-
"""大库基线读数（baseline runner）。

量四件事（都是**用户能感知的**，不是内部指标）：
  1) **首开**：应用启动后第一次打开文档 → 预览可见就绪的耗时；
  2) **切页签**：A→B→A，回到 A 可见的耗时（3 次取样，报中位数）；
  3) **打字**：编辑态逐键，「按键派发 → 预览 DOM 发生变化」的时延（5 键预热丢弃）；
  4) **内存**：JS 堆占用 + 预览块数/DOM 节点数（注明是 JS 堆，不是进程 RSS）。

为什么单独一个 runner：`run_probe.py` 的用例绑死 `tests/probe-kb` 的构造语料（scale/corpus），
而重构要对齐的是**真实大库**（人指定的 `数字通信原理` 副本）。两者用途不同，互不替代。

用法：
    python scripts/benchmark/surface/run_baseline.py \\
        --kb "artifacts/baseline-kb/数字通信原理" \\
        --file "教材/02_第2章_信号分析基础.md" \\
        --file-b "教材/04_第4章_信息论基础.md" \\
        --label legacy-baseline
"""
from __future__ import annotations

import argparse
import importlib.util
import json
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
IX_MJS = HERE / "interaction.mjs"


def _load_run_probe():
    spec = importlib.util.spec_from_file_location("memoria_run_probe", str(HERE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_short_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT)).decode().strip()
    except Exception:
        return "nogit"


def build_md(meta: dict, rec: dict) -> str:
    steps = rec.get("steps") or {}
    co = steps.get("coldOpen") or {}
    ts = steps.get("tabSwitch") or {}
    ty = steps.get("typing") or {}
    me = steps.get("memory") or {}
    L = []
    L.append("# 大库基线读数：%s" % meta["label"])
    L.append("")
    L.append("- 时间：%s" % meta["startedAt"])
    L.append("- commit：`%s`" % meta["sha"])
    L.append("- 语料：`%s`" % meta["kb"])
    L.append("- 文档 A：`%s`" % meta["fileA"])
    L.append("- 文档 B：`%s`" % meta["fileB"])
    L.append("- 浏览器：%s" % rec.get("browser", "?"))
    L.append("")
    L.append("| 指标 | 读数 | 说明 |")
    L.append("|---|---|---|")
    L.append("| **首开就绪** | **%s ms** | 启动后首次打开 A → 预览块可见且稳定（%s 块） |" % (
        co.get("readyMs", "—"), co.get("blocks", "—")))
    L.append("| **切页签回 A（中位）** | **%s ms** | A→B→A，3 次取样中位 |" % (ts.get("medianMs", "—")))
    L.append("| **打字（中位）** | **%s ms** | 按键→预览 DOM 变化，n=%s（预热 %s 丢弃） |" % (
        ty.get("medianMs", "—"), ty.get("n", "—"), ty.get("warmup", "—")))
    L.append("| 打字 p95 | %s ms | 同上样本 |" % (ty.get("p95Ms", "—")))
    L.append("| JS 堆 | %s MB / 总 %s MB | **JS 堆**，非进程 RSS |" % (
        me.get("usedJSHeapMB", "—"), me.get("totalJSHeapMB", "—")))
    L.append("| 预览块数 / DOM 节点 | %s / %s | 规模快照（读数必须绑定规模） |" % (
        me.get("blocks", "—"), me.get("domNodesInPreview", "—")))
    L.append("")
    if rec.get("samples"):
        L.append("## 原始样本")
        L.append("")
        for k, v in rec["samples"].items():
            L.append("- `%s`：%s" % (k, json.dumps(v, ensure_ascii=False)))
        L.append("")
    L.append("> 口径：所有读数在同一机器、同一语料副本、同一 commit 下取样；")
    L.append("> 首开/切页签用「块数连续 3 次稳定且无 loading 占位」判可见就绪；打字用 MutationObserver 记「按键→DOM 变化」。")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="大库基线读数")
    ap.add_argument("--kb", default="artifacts/baseline-kb/数字通信原理")
    ap.add_argument("--file", required=True, help="文档 A（相对 kb 根）")
    ap.add_argument("--file-b", default=None, help="文档 B（切页签用）")
    ap.add_argument("--label", default="legacy-baseline")
    ap.add_argument("--port", type=int, default=8646)
    ap.add_argument("--work-kb", default="artifacts/_baseline_kb")
    ap.add_argument("--keys", type=int, default=30)
    ap.add_argument("--warmup-keys", type=int, default=5)
    ap.add_argument("--min-blocks", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=1200)
    args = ap.parse_args()

    src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[bl] 语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2

    work_kb = (REPO_ROOT / args.work_kb).resolve()
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, work_kb)
    print("[bl] 语料副本: %s -> %s" % (src_kb, work_kb))

    rp = _load_run_probe()
    harness = rp.load_harness(work_kb, args.port)
    import bottle
    th = threading.Thread(target=bottle.run, kwargs=dict(app=harness.app, host="127.0.0.1", port=args.port, quiet=True), daemon=True)
    th.start()
    if not rp.wait_port(args.port):
        print("[bl] harness 未起来", file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % args.port
    import urllib.request
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                r.read(1024)
            break
        except Exception:
            time.sleep(0.5)
    print("[bl] harness 就绪（已预热）: %s" % url)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    sha = git_short_sha()
    stem = "baseline-%s_%s" % (args.label, sha)
    raw_path = RESULTS_DIR / ("raw-%s.json" % stem)
    md_path = RESULTS_DIR / ("%s.md" % stem)

    cmd = ["node", str(IX_MJS), "--bench", "--url", url, "--out", str(raw_path),
           "--file", args.file, "--file-b", args.file_b or "",
           "--keys", str(args.keys), "--warmup-keys", str(args.warmup_keys),
           "--min-blocks", str(args.min_blocks)]
    cmd = [c for c in cmd if c != ""]
    print("[bl] 起 node: %s" % " ".join(cmd))
    t0 = time.time()
    try:
        cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[bl] node 超时", file=sys.stderr)
        return 3
    took = time.time() - t0
    print("[bl] node rc=%s" % cp.returncode)
    print("[bl] --- stdout ---\n%s" % (cp.stdout or "")[-1500:])
    print("[bl] --- stderr ---\n%s" % (cp.stderr or "")[-4000:])
    if not raw_path.is_file():
        print("[bl] 未产出 raw json", file=sys.stderr)
        return 3

    rec = json.loads(raw_path.read_text(encoding="utf-8"))
    meta = {
        "label": args.label, "sha": sha, "startedAt": started,
        "kb": str(src_kb.relative_to(REPO_ROOT)) if str(src_kb).startswith(str(REPO_ROOT)) else str(src_kb),
        "fileA": args.file, "fileB": args.file_b or "—",
    }
    md_path.write_text(build_md(meta, rec), encoding="utf-8")
    print("\n[bl] 产物：\n  %s\n  raw: %s" % (md_path, raw_path))
    print("[bl] 用时 %.1fs" % took)
    return 0 if cp.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
