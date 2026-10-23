"""run_block_count.py —— 验证 `-src-block` 数量 == AST 块数（0.4.7 任务 4 修补验证）

复用 run_dock_width.py 的套路（harness + withBrowser）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SURFACE = Path(__file__).resolve().parent
RESULTS = SURFACE / "results"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def load_run_probe():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_probe", str(SURFACE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="-src-block 计数探针")
    ap.add_argument("--kb", default="artifacts/baseline-kb/数字通信原理")
    ap.add_argument("--fixture", default="nested-list-fixture.md")
    ap.add_argument("--label", default="block-count")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[bc] 语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2

    work_kb = (REPO_ROOT / ("artifacts/_bc_kb_%s_%d" % (args.label, os.getpid()))).resolve()
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    shutil.copytree(src_kb, work_kb)
    cfg_dir = work_kb.parent / ("_bc_config_%s_%d" % (args.label, os.getpid()))
    if cfg_dir.exists():
        shutil.rmtree(cfg_dir, ignore_errors=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)

    rp = load_run_probe()
    port = free_port()
    harness = rp.load_harness(work_kb, port)
    import bottle

    threading.Thread(
        target=bottle.run,
        kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
        daemon=True,
    ).start()
    if not rp.wait_port(port):
        print("[bc] harness 未起来", file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % port
    print("[bc] harness: %s" % url)

    RESULTS.mkdir(parents=True, exist_ok=True)
    runner = SURFACE / ("_bc_runner_%s.mjs" % os.getpid())
    runner.write_text(
        """
import { withBrowser } from "./interaction.mjs";
import { probeBlockCount } from "./block_count_probe.mjs";
const url = process.argv[2];
const fixture = process.argv[3];
let result = null;
await withBrowser(url, async (cdp) => { result = await probeBlockCount(cdp, fixture); });
if (!result) { process.stderr.write("探针未产出结果"); process.exit(2); }
process.stdout.write(JSON.stringify(result, null, 2));
process.exit(result.ok ? 0 : 1);
""",
        encoding="utf-8",
    )

    started = datetime.now(timezone.utc).isoformat()
    out_json = RESULTS / ("raw-%s.json" % args.label)
    cmd = ["node", str(runner), url, args.fixture]
    print("[bc] 跑探针: %s" % " ".join(cmd))
    t0 = time.time()
    try:
        cp = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        runner.unlink(missing_ok=True)
        print("[bc] 探针超时", file=sys.stderr)
        return 3
    elapsed = time.time() - t0
    runner.unlink(missing_ok=True)
    out_json.write_text(cp.stdout or "", encoding="utf-8")
    print("[bc] 用时 %.1fs exit=%d" % (elapsed, cp.returncode))
    if cp.stderr:
        print("[bc] stderr: %s" % cp.stderr[:800], file=sys.stderr)

    try:
        data = json.loads(cp.stdout or "{}")
    except json.JSONDecodeError:
        print("[bc] 输出不是 JSON", file=sys.stderr)
        return 2

    md = RESULTS / ("%s.md" % args.label)
    lines = [
        "# `-src-block` 计数探针（0.4.7 任务 4 修补验证）",
        "",
        "- 开始：%s" % started,
        "- 用时：%.1fs" % elapsed,
        "- 结论：%s" % ("✅ PASS" if data.get("ok") else "❌ FAIL"),
        "",
        "| 检查 | 结果 | 详情 |",
        "|---|---|---|",
    ]
    for c in data.get("checks", []):
        det = json.dumps(c.get("detail"), ensure_ascii=False).replace("|", "\\|")
        lines.append("| %s | %s | `%s` |" % (c.get("id"), "✅" if c.get("pass") else "❌", det[:380]))
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("[bc] 报告: %s" % md.name)

    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
