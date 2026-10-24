# -*- coding: utf-8 -*-
"""跨块选区矩阵探针运行器（task-79）。

做什么：
  1) 用**内嵌模板**生成冻结语料 `artifacts/_selection_kb/selection-matrix.md`
     （覆盖 paragraph / list / heading / blockquote / table / code_block /
       math_block / mermaid 八种块类型，每块带**全局唯一 ASCII 词**，
       使得「删了哪些词 / 留下哪些词」可以用词集精确判定，不靠肉眼）；
  2) 复用 `run_probe.load_harness()` 起本地服务（bottle + UIAPI + 假 pywebview 桥），
     把语料副本交给应用；与 12 剧本门禁同一套 harness，不另造运行环境；
  3) 起 Node 子进程 `scenarios/selection-driver.mjs`，用 CDP 真实鼠标/键盘事件执行
     「块类型 × 跨块跨度 × 四种操作（复制/剪切/删除/粘贴替换）」矩阵，
     每条用例断言：源码正确 / 重渲不回魂 / 剪贴板正确 / 单次撤销回到操作前 / 无内容丢失；
  4) 产出：
       scripts/benchmark/surface/results/selection-<label>_<sha>.json   原始证据
       artifacts/agent/verify/selection-matrix-<label>.md               人读矩阵（PASS/FAIL）

为什么不用 `run_interaction.py --scenarios`：那套剧本 DSL 只有
open/view/drag/click/key/eval/snapshot，无法在一次用例内完成
「选区 → 操作 → 重渲 → 撤销」四段断言与剪贴板回读；本探针自带 driver，
但**复用 interaction.mjs 的 CDP/启动/交互原语**（同一套真实事件，不复制）。

用法：
  python scripts/benchmark/surface/run_selection.py --label baseline
  python scripts/benchmark/surface/run_selection.py --label after --only paragraph,blockquote
  python scripts/benchmark/surface/run_selection.py --label sm --only-ops delete --only mixed
  # 连已在运行的真机应用（WebView2 + --remote-debugging-port=96xx）：
  python scripts/benchmark/surface/run_selection.py --label real --cdp-port 9611

退出码：0 = 探针跑完（**不管 PASS/FAIL**，基线本来就要记录 FAIL）；
        `--strict` 时有 FAIL 用例返回 1；启动/环境失败返回 2/3。
"""
from __future__ import annotations

import argparse
import importlib.util
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

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS_DIR = HERE / "results"
DRIVER = HERE / "scenarios" / "selection-driver.mjs"
DEFAULT_MATRIX = HERE / "scenarios" / "selection-matrix.json"
FIXTURE_DIR = REPO_ROOT / "artifacts" / "_selection_kb"
VERIFY_DIR = REPO_ROOT / "artifacts" / "agent" / "verify"

# ─────────────────────────────────────────────────────────────────────────────
# 冻结语料：八种块类型 + 全局唯一 ASCII 词
#
# 设计约束（改语料必须同步同步矩阵 JSON 里的 marker/word）：
#   · 每个「词」在整篇**只出现一次** ⇒ 可以用词集做「删了啥 / 留了啥」的精确判定，
#     不依赖光标偏移、不依赖行号、也不依赖渲染文本与源码文本的换行差异。
#   · 相邻两个同类块之间必须有空行（否则表格/代码/公式会并块）；
#     列表刻意用「无序 + 有序」两种标记 ⇒ 两个独立 list 块（同一列表块内两项会被并成一个块）。
#   · 非编辑块的选区端点一律落在其**内部**（表格单元格 / 代码行 / 公式 / mermaid 标签），
#     这正是用户报的「选区要能选到表格/代码/公式」；端点能不能落到那里本身就是被测事实。
# ─────────────────────────────────────────────────────────────────────────────
FIXTURE_MD = """# H1 heading marker

## H2 mike november

P1 alpha bravo charlie delta

P2 echo foxtrot golf hotel

P3 india juliet kilo lima

> BQ1 quebec romeo sierra
>
> BQ1B tango uniform victor

> BQ2 whiskey xray yankee
>
> BQ2B zulu alfa beta

- L1 gamma2 delta2
- L1B epsilon2 zeta2

1. L2 eta2 theta2
2. L2B iota2 kappa2

PREC kilo3 lima3

```python
C1 lambda2 mu2
C1B nu2 xi2
```

MIDC mike3 november3

```python
C2 omicron2 pi2
C2B rho2 sigma2
```

POSTC papa3 quebec3

PRET romeo3 sierra3

| T1 tau2 | T1B upsilon2 |
| --- | --- |
| T1C phi2 | T1D chi2 |

MIDT tango3 uniform3

| T2 psi2 | T2B omega2 |
| --- | --- |
| T2C alpha3 | T2D bravo3 |

POSTT victor3 whiskey3

PREM xray3 yankee3

$$
M1 = 1
$$

MIDM zulu3 alfa3

$$
M2 = 2
$$

POSTM bravo4 charlie4

PREMM delta4 echo4

```mermaid
graph TD
  MM1 --> MM2
```

MIDMM foxtrot4 golf4

```mermaid
graph TD
  MM3 --> MM4
```

POSTMM hotel4 india4

P9 juliet4 kilo4
"""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _load_run_probe():
    spec = importlib.util.spec_from_file_location("memoria_run_probe", str(HERE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_fixture_kb() -> Path:
    """生成冻结语料目录（幂等：内容不同才重写，避免无谓 mtime 抖动）。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    doc = FIXTURE_DIR / "selection-matrix.md"
    data = FIXTURE_MD.replace("\r\n", "\n")
    if not doc.is_file() or doc.read_text(encoding="utf-8") != data:
        doc.write_text(data, encoding="utf-8", newline="\n")
    readme = FIXTURE_DIR / "README.md"
    if not readme.is_file():
        readme.write_text(
            "# 跨块选区矩阵语料（task-79）\n\n"
            "由 `scripts/benchmark/surface/run_selection.py` 生成，勿手改；"
            "矩阵定义见 `scripts/benchmark/surface/scenarios/selection-matrix.json`。\n",
            encoding="utf-8", newline="\n")
    return FIXTURE_DIR


def git_short_sha() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT))
        return out.decode("utf-8", "replace").strip()
    except Exception:
        return "nogit"


# ─────────────────────────────────────────────────────────────────────────────
# 报告
# ─────────────────────────────────────────────────────────────────────────────
OPS_ZH = {"copy": "复制", "cut": "剪切", "delete": "删除", "pasteReplace": "粘贴替换"}
CHECK_ZH = {
    "selReady": "选区建立",
    "changed": "源码变化",
    "deletedGone": "选中内容已删",
    "keptPresent": "未选内容保留",
    "noDuplicate": "无重复/残留词",
    "domNoGhost": "重渲不回魂",
    "renderStable": "重渲不改源码",
    "singleUndo": "单次撤销复原",
    "clipboard": "剪贴板正确",
    "copyNoop": "复制不改文档",
    "failureNotice": "失败有可见提示",
}


def build_md(raw: dict, label: str, sha: str) -> str:
    """人读矩阵报告：**摘要表 + 逐用例状态**。

    刻意不内联每条用例的源码前后文（那样单份报告 400KB+，没人读）——
    完整证据在同名 raw JSON 的 `cases[].preBody/postBody/logs/clipboard` 里。
    """
    cases = raw.get("cases") or []
    meta = raw.get("meta") or {}
    total = len(cases)
    passed = sum(1 for c in cases if c.get("pass"))

    # 聚合：类型 × 操作（用例 id 里的类型前缀只到组，另用 type 字段归一）
    def type_key(c):
        t = str(c.get("type") or "?")
        for k in ("paragraph", "heading", "blockquote", "list", "code", "table", "math", "mermaid"):
            if t.startswith(k):
                return k
        return t

    agg = {}
    for c in cases:
        k = (type_key(c), c.get("op"))
        d = agg.setdefault(k, {"pass": 0, "total": 0})
        d["total"] += 1
        if c.get("pass"):
            d["pass"] += 1

    L = []
    L.append("# 跨块选区矩阵探针：%s" % label)
    L.append("")
    L.append("- 时间：%s" % datetime.now(timezone.utc).isoformat())
    L.append("- commit：`%s`" % sha)
    L.append("- 语料：`artifacts/_selection_kb/selection-matrix.md`（8 类块 + 全局唯一词；不可编辑块用 PRE/MID/POST 布局）")
    L.append("- 矩阵定义：`scripts/benchmark/surface/scenarios/selection-matrix.json`")
    L.append("- 驱动：`scripts/benchmark/surface/scenarios/selection-driver.mjs`（CDP 真实键鼠；cut 走产品同源 beforeinput）")
    L.append("- 模式：%s；浏览器：%s" % (meta.get("mode", "?"), meta.get("browser", "?")))
    L.append("- 每用例断言：选区建立 / 源码变化 / 选中已删 / 未选保留 / 无重复残留 / **重渲不回魂** / "
             "重渲不改源码 / **单次 Ctrl+Z 复原** / 剪贴板含可见被选词（复制复制、剪切写、粘贴事件）/ 失败必有可见提示")
    L.append("- 完整证据（源码前后、产品日志、剪贴板文本）：同名 raw JSON 的 `cases[]`")
    L.append("")
    verdict = "✅ 全部 PASS" if passed == total else "❌ %d / %d FAIL" % (total - passed, total)
    L.append("## 结论：%s（%d/%d）" % (verdict, passed, total))
    L.append("")
    L.append("## 摘要：块类型 × 操作")
    L.append("")
    ops = [("copy", "复制"), ("cut", "剪切"), ("delete", "删除"), ("pasteReplace", "粘贴替换")]
    L.append("| 块类型 | " + " | ".join(z[1] for z in ops) + " |")
    L.append("|---|" + "---|" * len(ops))
    order = ["paragraph", "heading", "list", "blockquote", "code", "table", "math", "mermaid"]
    seen = set()
    for tk in order + sorted({k[0] for k in agg} - set(order)):
        seen.add(tk)
        cells = []
        for op, _zh in ops:
            d = agg.get((tk, op))
            cells.append("—" if not d else ("✅ %d/%d" % (d["pass"], d["total"]) if d["pass"] == d["total"]
                                            else ("❌ %d/%d" % (d["pass"], d["total"]))))
        L.append("| %s | %s |" % (tk, " | ".join(cells)))
    L.append("")
    L.append("## 逐用例")
    L.append("")
    L.append("| 用例 | 结果 | 失败项 | 备注 |")
    L.append("|---|---|---|---|")
    for c in cases:
        fails = c.get("failChecks") or []
        note = c.get("error") or ""
        if not note and c.get("notice"):
            note = "提示:" + str(c.get("notice"))[:40]
        L.append("| %s | %s | %s | %s |" % (
            c.get("id"), "✅" if c.get("pass") else "❌",
            ", ".join(CHECK_ZH.get(f, f) for f in fails) or "—",
            str(note).replace("|", "\\|")[:70]))
    L.append("")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="跨块选区矩阵探针（task-79）")
    ap.add_argument("--label", default="baseline", help="本次运行 label（产物文件名）")
    ap.add_argument("--matrix", default=str(DEFAULT_MATRIX), help="矩阵 json")
    ap.add_argument("--only", default="", help="只跑指定 group/mixed id 前缀（逗号分隔，支持子串）")
    ap.add_argument("--only-ops", default="", help="只跑指定操作（逗号分隔：copy/cut/delete/pasteReplace）")
    ap.add_argument("--cdp-port", type=int, default=0,
                    help="非 0 = attach 已在运行的真机应用（WebView2 remote-debugging-port）")
    ap.add_argument("--port", type=int, default=0, help="harness 端口（0=自动挑）")
    ap.add_argument("--timeout", type=int, default=1800, help="node 子进程超时秒")
    ap.add_argument("--strict", action="store_true", help="有 FAIL 用例时退出码 1")
    ap.add_argument("--serve-only", action="store_true",
                    help="DIAG：只起 harness，把 URL 写进 --serve-file 后阻塞（供手工跑 driver）")
    ap.add_argument("--serve-file", default="artifacts/_sel_harness_url.txt", help="DIAG：harness URL 落盘路径")
    ap.add_argument("--report-only", action="store_true", help="只把既有 raw json 重建成人读 md（不跑探针）")
    ap.add_argument("--raw", default="", help="配合 --report-only：raw json 路径（留空=取最新 selection-*.json）")
    args = ap.parse_args()

    if args.report_only:
        raws = [Path(args.raw)] if args.raw else sorted(RESULTS_DIR.glob("selection-*.json"))
        raws = [p for p in raws if p.is_file() and not p.name.endswith(".node.log")]
        if not raws:
            print("[sel] 找不到 raw json", file=sys.stderr)
            return 2
        VERIFY_DIR.mkdir(parents=True, exist_ok=True)
        report_label = args.label or "baseline"
        raw = json.loads(raws[-1].read_text(encoding="utf-8"))
        md_path = VERIFY_DIR / ("selection-matrix-%s.md" % report_label)
        md_path.write_text(build_md(raw, report_label, git_short_sha()), encoding="utf-8")
        print("[sel] 重建报告：%s（来源 %s）" % (md_path, raws[-1]))
        return 0

    matrix_path = Path(args.matrix)
    if not matrix_path.is_absolute():
        matrix_path = (REPO_ROOT / args.matrix).resolve()
    if not matrix_path.is_file():
        print("[sel] 矩阵不存在: %s" % matrix_path, file=sys.stderr)
        return 2
    if not DRIVER.is_file():
        print("[sel] driver 不存在: %s" % DRIVER, file=sys.stderr)
        return 2

    build_fixture_kb()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    sha = git_short_sha()
    stem = "selection-%s_%s" % (args.label, sha)
    raw_path = RESULTS_DIR / ("%s.json" % stem)
    md_path = VERIFY_DIR / ("selection-matrix-%s.md" % args.label)

    base_cmd = [
        "node", str(DRIVER),
        "--matrix", str(matrix_path),
        "--out", str(raw_path),
        "--label", args.label,
        "--file", "selection-matrix.md",
    ]
    if args.only:
        base_cmd += ["--only", args.only]
    if args.only_ops:
        base_cmd += ["--only-ops", args.only_ops]

    url = None
    proc_thread = None
    cfg_dir = None
    if args.cdp_port:
        # attach 真机：应用已自行加载 KB（MEMORIA_KB 指向语料目录的副本）
        print("[sel] attach 真机 CDP 端口: %d" % args.cdp_port)
        base_cmd += ["--cdp-port", str(args.cdp_port)]
        mode = "attach(真机 WebView2)"
    else:
        port = args.port or _free_port()
        if _port_busy(port):
            print("[sel] 端口 %d 已被占用" % port, file=sys.stderr)
            return 2
        # 工作副本（绝不在语料目录上跑；应用会写 .memoria）
        work_kb = REPO_ROOT / ("artifacts/_selection_work_%s_%d" % (args.label, os.getpid()))
        if work_kb.exists():
            shutil.rmtree(work_kb, ignore_errors=True)
        shutil.copytree(FIXTURE_DIR, work_kb)
        # 密封配置（不继承开发机 ui-settings.json）
        cfg_dir = work_kb.parent / ("_selection_config_%s_%d" % (args.label, os.getpid()))
        if cfg_dir.exists():
            shutil.rmtree(cfg_dir, ignore_errors=True)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)

        rp = _load_run_probe()
        harness = rp.load_harness(work_kb, port)
        import bottle
        proc_thread = threading.Thread(
            target=bottle.run,
            kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
            daemon=True,
        )
        proc_thread.start()
        if not rp.wait_port(port):
            print("[sel] harness 未在端口 %s 起来" % port, file=sys.stderr)
            return 2
        url = "http://127.0.0.1:%s/" % port
        import urllib.request
        for _ in range(3):
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    r.read(1024)
                break
            except Exception:
                time.sleep(0.4)
        print("[sel] harness 就绪: %s（语料副本 %s）" % (url, work_kb))
        base_cmd += ["--url", url]
        mode = "headless Edge + harness"
        if args.serve_only:
            sf = REPO_ROOT / args.serve_file
            sf.parent.mkdir(parents=True, exist_ok=True)
            sf.write_text(url + "\n", encoding="utf-8")
            print("[sel] DIAG serve-only：URL 已写入 %s；Ctrl+C 结束" % sf)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                return 0

    t0 = time.time()
    try:
        cp = subprocess.run(base_cmd, cwd=str(REPO_ROOT), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[sel] node 子进程超时", file=sys.stderr)
        return 3
    elapsed = time.time() - t0
    node_log = RESULTS_DIR / ("%s.node.log" % stem)
    try:
        node_log.write_text(
            "=== exit %s ===\n--- stdout ---\n%s\n--- stderr ---\n%s\n"
            % (cp.returncode, cp.stdout or "", cp.stderr or ""), encoding="utf-8")
    except Exception:
        pass
    if cp.stdout:
        print(cp.stdout.strip()[:4000])
    if cp.stderr:
        print("[sel] node stderr:\n%s" % cp.stderr.strip()[:6000], file=sys.stderr)
    if cp.returncode != 0:
        print("[sel] node 退出码 %s（完整日志 %s）" % (cp.returncode, node_log), file=sys.stderr)
    if not raw_path.is_file():
        print("[sel] 未产出 raw json: %s" % raw_path, file=sys.stderr)
        return 3

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw.setdefault("meta", {})["mode"] = mode
    cases = raw.get("cases") or []
    passed = sum(1 for c in cases if c.get("pass"))
    md_path.write_text(build_md(raw, args.label, sha), encoding="utf-8")
    print("\n[sel] 产物：\n  %s\n  raw: %s" % (md_path, raw_path))
    print("[sel] 用例 %d 个：PASS %d / FAIL %d，用时 %.1fs" % (
        len(cases), passed, len(cases) - passed, elapsed))
    if args.strict and passed != len(cases):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
