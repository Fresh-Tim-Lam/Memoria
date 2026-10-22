# -*- coding: utf-8 -*-
"""W4.1 惰性路径交互门禁运行器（一条命令复跑）。

做什么：
  1) 复用 `run_interaction.py` 的 harness 做法（bottle 静态服务 + `/rpc` → UIAPI +
     注入假 `window.pywebview.api` 桥），把**仓库内大文档 fixture**当语料起服务；
  2) 起 Node `lazy_gate.mjs`，用 CDP 受信任输入/滚动量**惰性路径**：
       L0 测量可信门（空转 rAF p50）→ L1 打开 → L2 四个位置 → L3 回顶 → L4 长滚 → L5 编辑保护；
  3) 落可机读 JSON（每步断言 + 读数 + PASS/FAIL）与人读 MD，失败能定位到具体步骤。

用法：
    python scripts/benchmark/surface/run_lazy_gate.py
    python scripts/benchmark/surface/run_lazy_gate.py --label lazy-gate
    # 负向验证（必须 FAIL）：
    python scripts/benchmark/surface/run_lazy_gate.py --sabotage noevict --label neg-noevict
    python scripts/benchmark/surface/run_lazy_gate.py --sabotage viewport-placeholder --label neg-placeholder
    # 顺带证明既有 12 剧本仍 12/12：
    python scripts/benchmark/surface/run_lazy_gate.py --with-existing-12

产物：`scripts/benchmark/surface/results/lazy-gate-<label>_<sha>.{json,md}`
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
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESULTS_DIR = HERE / "results"
GATE_MJS = HERE / "lazy_gate.mjs"
DEFAULT_SCENARIOS = HERE / "scenarios" / "lazy-gate.json"
DEFAULT_KB = HERE / "fixtures" / "lazy-gate-kb"
EXISTING_SCENARIOS = HERE / "scenarios" / "interactions.json"
EXISTING_KB = "artifacts/baseline-kb/数字通信原理"


def _load_run_probe():
    spec = importlib.util.spec_from_file_location("memoria_lazy_gate_probe", str(HERE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_short_sha() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT),
                                      stderr=subprocess.DEVNULL)
        return out.decode("utf-8", "replace").strip() or "nogit"
    except Exception:
        return "nogit"


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _port_busy(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def build_md(meta: dict, out: dict) -> str:
    checks = out.get("checks") or []
    summary = out.get("summary") or {}
    L = []
    L.append("# 惰性路径交互门禁（W4.1）：%s" % meta["label"])
    L.append("")
    L.append("- 时间：%s" % meta["startedAt"])
    L.append("- commit：`%s`" % meta["sha"])
    L.append("- 语料：`%s`（fixture 源行数 %s，标记 %s 个）" % (
        out.get("fixture", {}).get("path"), (out.get("fixture") or {}).get("totalLines"), (out.get("fixture") or {}).get("markers")))
    L.append("- 剧本：`%s`" % meta["scenarios"])
    L.append("- 负向注入：%s" % (out.get("sabotage") or "无"))
    L.append("- 浏览器：%s" % (out.get("browser") or "?"))
    L.append("- 测量可信门：rAF p50 = %s ms（阈值 ≤ %s ms）⇒ %s" % (
        ((out.get("measurement") or {}).get("raf") or {}).get("p50Ms"),
        (out.get("thresholds") or {}).get("p50MaxMs"),
        "可信" if (out.get("measurement") or {}).get("trusted") else "不可信"))
    L.append("")
    L.append("## 结论：%s" % ("✅ PASS" if summary.get("pass") else "❌ FAIL（%s）" % ", ".join(summary.get("failedIds") or [])))
    L.append("")
    if out.get("open"):
        o = out["open"]
        L.append("### 打开（惰性路径）")
        L.append("")
        L.append("- 首块可见：**%s ms**（预算 %s ms）" % (o.get("firstVisibleMs"), (out.get("thresholds") or {}).get("firstVisibleMaxMs")))
        L.append("- 首屏就绪（≥3 块且有文本）：%s ms；墙钟 %s ms" % (o.get("screenReadyMs"), o.get("wallMs")))
        st = o.get("stats") or {}
        L.append("- 块数：%s（占位 %s / 已物化 %s）；行高 %s px；度量来源 `%s`；每屏约 %s 块" % (
            st.get("totalBlocks"), st.get("placeholders"), st.get("materialized"), st.get("lhPx"), st.get("metricsSrc"), o.get("blocksPerScreen")))
        L.append("")
    L.append("| 检查 | 状态 | 关键读数 |")
    L.append("|---|---|---|")
    for c in checks:
        key = ""
        for s in c.get("steps") or []:
            r = s.get("readings") or {}
            for k in ("drift", "delta", "maxMaterialized", "evictTotal", "open", "whileFarAway"):
                if k in r:
                    key += "`%s`=%s " % (k, json.dumps(r[k], ensure_ascii=False)[:180])
        L.append("| %s | %s | %s |" % (c.get("id"), "✅ PASS" if c.get("status") == "PASS" else "❌ FAIL", key or "—"))
    L.append("")
    failed = [c for c in checks if c.get("status") != "PASS"]
    if failed:
        L.append("## 失败明细（定位到步骤/断言）")
        L.append("")
        for c in failed:
            L.append("### %s" % c.get("id"))
            L.append("")
            if c.get("error"):
                L.append("- 异常：`%s`" % c["error"])
            for s in c.get("steps") or []:
                for a in s.get("assertions") or []:
                    if not a.get("ok"):
                        L.append("- `%s` / `%s`：期望 `%s`，实际 `%s`%s" % (
                            s.get("step"), a.get("name"), a.get("expected"), a.get("actual"),
                            ("（%s）" % a["note"]) if a.get("note") else ""))
                        for k, v in (s.get("readings") or {}).items():
                            L.append("  - `%s`：%s" % (k, json.dumps(v, ensure_ascii=False)[:1200]))
            L.append("")
    L.append("## 口径与限制")
    L.append("")
    L.append("- 「首块可见」= `openFile()` 返回到首个已物化块进入视口（rAF 轮询），不含 MathJax 全量排版完成。")
    L.append("- 「相对漂移」= 同一锚点块在 settle 前后相对视口的屏幕位移 ÷ 实测行高；「绝对位置」= 回顶后首块相对视口顶偏移 ÷ 行高。")
    L.append("- 「DOM ≤ 视口×8」按**同时存在的块数**（含占位）计，视口块数 = `ceil(pane.clientHeight / 实测行高)`；另报告 `#preview` 节点数。")
    L.append("- 堆读数是 Chromium `performance.memory.usedJSHeapSize`（非进程 RSS）；采样前尽量 `gc()`，仍受引擎 GC 时机影响。")
    L.append("- 本门禁跑在**无头 Edge harness**（与 12 剧本同一条 CDP 路径），不是真机 pywebview；真机首开读数另测。")
    return "\n".join(L) + "\n"


def run_existing12(label: str, timeout: int) -> dict:
    """顺带跑既有 12 个交互剧本，证明没有被新门禁破坏（12/12）。"""
    cmd = [
        sys.executable, str(HERE / "run_interaction.py"),
        "--kb", EXISTING_KB,
        "--scenarios", str(EXISTING_SCENARIOS),
        "--label", label,
        "--timeout", str(timeout),
    ]
    print("\n[gate] 顺带跑既有 12 剧本：%s" % " ".join(cmd))
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=timeout + 120,
                        env=dict(os.environ))
    if cp.stdout:
        print(cp.stdout.strip()[-3000:])
    if cp.stderr:
        print(cp.stderr.strip()[-2000:], file=sys.stderr)
    return {"ok": cp.returncode == 0, "returncode": cp.returncode,
            "stdoutTail": (cp.stdout or "").strip()[-2000:]}


def main() -> int:
    ap = argparse.ArgumentParser(description="W4.1 惰性路径交互门禁")
    ap.add_argument("--kb", default=str(DEFAULT_KB), help="fixture 语料目录（相对 repo 根或绝对路径）")
    ap.add_argument("--scenarios", default=str(DEFAULT_SCENARIOS), help="门禁剧本 json")
    ap.add_argument("--label", default="lazy-gate", help="本次运行 label（也用于结果文件名）")
    ap.add_argument("--sabotage", default="", choices=["", "noevict", "viewport-placeholder"],
                    help="负向验证注入（正常验收不要传）")
    ap.add_argument("--port", type=int, default=0, help="harness 端口（0=自动空闲端口）")
    ap.add_argument("--timeout", type=int, default=600, help="node 子进程超时秒")
    ap.add_argument("--with-existing-12", action="store_true", help="顺带跑既有 12 个交互剧本（12/12 证据）")
    ap.add_argument("--keep-work", action="store_true", help="保留语料副本（默认保留，便于失败取证）")
    args = ap.parse_args()

    src_kb = Path(args.kb)
    if not src_kb.is_absolute():
        src_kb = (REPO_ROOT / args.kb).resolve()
    if not src_kb.is_dir():
        print("[gate] 语料目录不存在: %s" % src_kb, file=sys.stderr)
        return 2
    scen_path = Path(args.scenarios)
    if not scen_path.is_absolute():
        scen_path = (REPO_ROOT / args.scenarios).resolve()
    if not scen_path.is_file():
        print("[gate] 剧本不存在: %s" % scen_path, file=sys.stderr)
        return 2
    spec = json.loads(scen_path.read_text(encoding="utf-8"))
    fixture_rel = (spec.get("fixture") or {}).get("path")
    fixture_path = (REPO_ROOT / fixture_rel).resolve() if fixture_rel else None
    if fixture_path is None or not fixture_path.is_file():
        print("[gate] fixture 不存在（仓库内固定 fixture 是硬要求）: %s" % fixture_path, file=sys.stderr)
        return 2
    # fixture 规模前置检查（真正块数在浏览器里用 parser 实测；这里只挡明显错误）
    fixture_lines = len(fixture_path.read_text(encoding="utf-8").splitlines())
    print("[gate] fixture: %s（%d 源行）" % (fixture_path, fixture_lines))

    port = args.port
    if port == 0:
        port = _free_port()
    elif _port_busy(port):
        print("[gate] 端口 %d 被占用，请换端口或省略 --port" % port, file=sys.stderr)
        return 2
    print("[gate] harness 端口: %d" % port)

    # 工作副本（绝不在 fixture 上跑：编辑保护用例会写库）
    work_kb = REPO_ROOT / "artifacts" / ("_lazy_gate_kb_%s_%d" % (args.label, os.getpid()))
    if work_kb.exists():
        shutil.rmtree(work_kb, ignore_errors=True)
    work_kb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_kb, work_kb)
    cfg_dir = work_kb.parent / ("_lazy_gate_config_%s_%d" % (args.label, os.getpid()))
    if cfg_dir.exists():
        shutil.rmtree(cfg_dir, ignore_errors=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)
    print("[gate] 工作副本: %s" % work_kb)
    print("[gate] 密封配置目录: %s" % cfg_dir)

    rp = _load_run_probe()
    harness = rp.load_harness(work_kb, port)
    import bottle
    th = threading.Thread(target=bottle.run,
                          kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
                          daemon=True)
    th.start()
    if not rp.wait_port(port):
        print("[gate] harness 未在端口 %s 起来" % port, file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % port
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read(1024)
            break
        except Exception:
            time.sleep(0.4)
    print("[gate] harness 就绪: %s" % url)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    sha = git_short_sha()
    stem = "lazy-gate-%s_%s" % (args.label, sha)
    raw_path = RESULTS_DIR / ("raw-%s.json" % stem)
    md_path = RESULTS_DIR / ("%s.md" % stem)
    cmd = ["node", str(GATE_MJS), "--scenarios", str(scen_path), "--out", str(raw_path),
           "--url", url, "--label", args.label]
    if args.sabotage:
        cmd += ["--sabotage", args.sabotage]
    print("[gate] 起 node: %s" % " ".join(cmd))
    t0 = time.time()
    try:
        cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[gate] node 子进程超时", file=sys.stderr)
        return 3
    elapsed = time.time() - t0
    if cp.stdout:
        print(cp.stdout.strip()[-4000:])
    if cp.stderr:
        print("[gate] node stderr:\n%s" % cp.stderr.strip()[-4000:], file=sys.stderr)
    if not raw_path.is_file():
        print("[gate] 未产出 JSON：%s" % raw_path, file=sys.stderr)
        return 3
    out = json.loads(raw_path.read_text(encoding="utf-8"))
    meta = {"label": args.label, "sha": sha, "startedAt": started,
            "scenarios": scen_path.name, "elapsedMs": int(elapsed * 1000)}
    out["meta"] = meta
    # 既有 12 剧本证据（可选）
    if args.with_existing_12:
        out["existing12"] = run_existing12("lazy-gate-existing12", args.timeout)
    raw_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_md(meta, out), encoding="utf-8")

    checks = out.get("checks") or []
    print("\n[gate] 结果：")
    for c in checks:
        print("  %-6s %-22s %s" % (c.get("status"), c.get("id"), c.get("desc") or ""))
        for s in c.get("steps") or []:
            for a in s.get("assertions") or []:
                if not a.get("ok"):
                    print("         ✗ %s / %s：期望 %s，实际 %s" % (
                        s.get("step"), a.get("name"), a.get("expected"), a.get("actual")))
    ok = bool((out.get("summary") or {}).get("pass"))
    print("\n[gate] %s（%d 项检查，失败 %s；用时 %.1fs）" % (
        "PASS" if ok else "FAIL", len(checks),
        ", ".join((out.get("summary") or {}).get("failedIds") or []) or "0", elapsed))
    print("[gate] 产物：\n  %s\n  raw: %s" % (md_path, raw_path))
    if args.with_existing_12:
        e = out.get("existing12") or {}
        print("[gate] 既有 12 剧本：%s（returncode=%s）" % ("12/12 PASS" if e.get("ok") else "FAIL", e.get("returncode")))
    # 失败时保留副本方便取证；成功且未要求保留则清掉工作副本
    if ok and not args.keep_work:
        shutil.rmtree(work_kb, ignore_errors=True)
        shutil.rmtree(cfg_dir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
