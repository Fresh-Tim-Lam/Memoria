"""run_nested_diag.py —— 只读诊断入口：打印 domToAst 对每个 <li> 的返回值（task-80）

复用 run_nested_tab.py 的 harness 套路，但**不做任何点击/Tab**，只调 `MemoriaMapper.domToAst()`。
退出码：0 成功 / 1 失败 / 2 环境失败
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
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
    spec = importlib.util.spec_from_file_location("run_probe", str(SURFACE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "diag"
    kb = (REPO_ROOT / "artifacts" / "baseline-kb" / "数字通信原理").resolve()
    if not kb.is_dir():
        print("[diag] 语料目录不存在: %s" % kb, file=sys.stderr)
        return 2

    work_kb = (REPO_ROOT / ("artifacts/_diag_kb_%s_%d" % (label, os.getpid()))).resolve()
    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.copytree(kb, work_kb)
    cfg_dir = work_kb.parent / ("_diag_config_%s_%d" % (label, os.getpid()))
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
        print("[diag] harness 未起来", file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % port

    RESULTS.mkdir(parents=True, exist_ok=True)
    runner = SURFACE / ("_diag_runner_%s.mjs" % os.getpid())
    runner.write_text(
        """
import { withBrowser } from "./interaction.mjs";
import { diagDomToAst } from "./nested_diag_domtoast.mjs";
const url = process.argv[2];
let result = null;
await withBrowser(url, async (cdp) => { result = await diagDomToAst(cdp); });
if (!result) { process.stderr.write("no result"); process.exit(2); }
process.stdout.write(JSON.stringify(result, null, 2));
process.exit(0);
""",
        encoding="utf-8",
    )
    cmd = ["node", str(runner), url]
    try:
        cp = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        runner.unlink(missing_ok=True)
        print("[diag] 超时", file=sys.stderr)
        return 2
    runner.unlink(missing_ok=True)
    if cp.stderr:
        print("[diag] stderr: %s" % cp.stderr[:1200], file=sys.stderr)

    out_json = RESULTS / ("diag-domtoast-%s.json" % label)
    out_json.write_text(cp.stdout or "", encoding="utf-8")
    try:
        data = json.loads(cp.stdout or "{}")
    except json.JSONDecodeError:
        print("[diag] 输出不是 JSON", file=sys.stderr)
        return 1

    shutil.rmtree(work_kb, ignore_errors=True)
    shutil.rmtree(cfg_dir, ignore_errors=True)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
