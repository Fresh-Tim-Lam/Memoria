"""run_dock_width.py —— 起 harness + Edge，跑 dock 宽度探针（0.4.7 任务 3 验收）

复用 run_interaction.py 的 harness 启动方式（bottle + 独立配置目录 + 语料副本），
再用 interaction.mjs 同款 CDP 通道驱动 `dock_width_probe.mjs`。

用法：
    python scripts/benchmark/surface/run_dock_width.py [--label xxx]

退出码：0 = 全部断言通过；1 = 有断言失败；2 = 环境/启动失败。
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
PROBE = SURFACE / "dock_width_probe.mjs"


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
    ap = argparse.ArgumentParser(description="dock 宽度探针（0.4.7 任务 3）")
    ap.add_argument("--kb", default="artifacts/baseline-kb/数字通信原理", help="语料库目录")
    ap.add_argument("--label", default="dock-width")
    ap.add_argument("--timeout", type=int, default=180, help="node 探针超时（秒）")
    args = ap.parse_args()

    src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[dw] 语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2

    # 语料副本（不污染 baseline-kb）
    work_rel = "artifacts/_dock_kb_%s_%d" % (args.label, os.getpid())
    work_kb = (REPO_ROOT / work_rel).resolve()
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    shutil.copytree(src_kb, work_kb)
    print("[dw] 语料副本: %s -> %s" % (src_kb, work_kb))

    # 密封配置目录
    cfg_dir = work_kb.parent / ("_dock_config_%s_%d" % (args.label, os.getpid()))
    if cfg_dir.exists():
        shutil.rmtree(cfg_dir, ignore_errors=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)
    print("[dw] 密封配置目录: %s" % cfg_dir)

    rp = load_run_probe()
    port = free_port()
    harness = rp.load_harness(work_kb, port)
    import bottle  # harness 已导入

    th = threading.Thread(
        target=bottle.run,
        kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
        daemon=True,
    )
    th.start()
    if not rp.wait_port(port):
        print("[dw] harness 未在端口 %s 起来" % port, file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % port
    print("[dw] harness URL: %s" % url)

    # 用一个 node 子进程同时做三件事：起 Edge → 打开页面 → 跑探针 → 清理。
    # 这样不跨进程传递 CDP 连接（launchEdge 返回的 wsUrl 供同进程内用）。
    RESULTS.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    out_json = RESULTS / ("raw-%s.json" % args.label)
    runner = SURFACE / ("_dock_runner_%s.mjs" % os.getpid())  # 与 cdp.mjs 同目录 ⇒ 相对 import 有效
    # 用 withBrowser(url, fn)：它负责起 Edge + 连接 + 等 MemoriaApp 就绪（含重试），
    # 比手写 launchEdge/CDP 更可靠（launchEdge 返回的是 wsUrl 而非已连接对象）。
    # withBrowser(url, fn) 负责起 Edge + 连接 + 等 MemoriaApp 就绪，再把**同一个 cdp** 传给 fn。
    # 探针是模块（导出 probeDockWidth(cdp)），不再自建连接。
    runner.write_text(
        """
import { withBrowser } from "./interaction.mjs";
import { probeDockWidth, formatReport } from "./dock_width_probe.mjs";
const url = process.argv[2];
let result = null;
await withBrowser(url, async (cdp) => {
  result = await probeDockWidth(cdp);
});
if (!result) { process.stderr.write("探针未产出结果"); process.exit(2); }
process.stdout.write(JSON.stringify(result, null, 2));
process.exit(result.ok ? 0 : 1);
""", encoding="utf-8")
    cmd = ["node", str(runner), url]
    print("[dw] 跑探针: %s" % " ".join(cmd))
    t0 = time.time()
    try:
        cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[dw] 探针超时", file=sys.stderr)
        runner.unlink(missing_ok=True)
        return 3
    elapsed = time.time() - t0
    runner.unlink(missing_ok=True)
    out_json.write_text(cp.stdout or "", encoding="utf-8")
    print("[dw] 用时 %.1fs, exit=%d, 结果: %s" % (elapsed, cp.returncode, out_json.name))
    if cp.stderr:
        print("[dw] stderr: %s" % cp.stderr[:800], file=sys.stderr)

    try:
        data = json.loads(cp.stdout or "{}")
    except json.JSONDecodeError:
        print("[dw] 探针输出不是 JSON", file=sys.stderr)
        return 2

    md = RESULTS / ("%s.md" % args.label)
    lines = [
        "# agent 会话栏宽度探针（0.4.7 任务 3）",
        "",
        "- 开始：%s" % started,
        "- 用时：%.1fs" % elapsed,
        "- 结论：%s" % ("✅ PASS" if data.get("ok") else "❌ FAIL"),
        "",
        "| 检查 | 结果 | 详情 |",
        "|---|---|---|",
    ]
    for c in data.get("checks", []):
        detail = json.dumps(c.get("detail"), ensure_ascii=False).replace("|", "\\|")
        lines.append("| %s | %s | `%s` |" % (c.get("id"), "✅" if c.get("pass") else "❌", detail[:400]))
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("[dw] 报告: %s" % md.name)

    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
