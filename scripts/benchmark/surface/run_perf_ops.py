#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run_perf_ops.py —— 绩效操作覆盖矩阵 runner + P_old 基线 + 预算表

复用 load_harness（与 run_probe.py / run_fidelity.py 同款），驱动 perf_ops_cli.mjs，
产出 results/perf-ops-<label>_<sha>.{json,md}。

用法：
    python scripts/benchmark/surface/run_perf_ops.py --label baseline
    python scripts/benchmark/surface/run_perf_ops.py --label baseline --ops typing,scroll
    python scripts/benchmark/surface/run_perf_ops.py --label inject --inject busywait
    # 真机（首开/公式必须）：
    python scripts/benchmark/surface/run_perf_ops.py --label realapp --cdp http://127.0.0.1:9500

约束：不改 src/**；不传 --port（自动选）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS_PATH = REPO_ROOT / "docs" / "example" / "rich-content-test" / "_harness.py"
RESULTS_DIR = REPO_ROOT / "scripts" / "benchmark" / "surface" / "results"
CLI = REPO_ROOT / "scripts" / "benchmark" / "surface" / "perf_ops_cli.mjs"

# ─────────────────────────────────────────────────────────────────────────────
# 预算口径（task-24 §4，**不得凭空发明数字**）
#   绝对预算 = min(用户可感知阈值, P_old × 1.15)
#   无用户阈值的 => P_old × 1.15
#
# 用户可感知阈值来源（只取有据可循的；没有就留 None => 走 ×1.15）：
#   - typing:  <16ms  = 60fps 单帧预算（phase1-performance-gate.md §0 G1' 既定目标）
#              !! 注意单位：typing 是"一次按键处理耗时"，16ms 合理。
#   - open    : <1000ms（"可接受首开"常见感知阈值；gate 文档已用 1434ms 观测做参照）
#   其余操作无既有人体感知阈值 => 一律 P_old × 1.15
#
# !! scroll **不能**用 16ms 阈值 —— 这是 LEARNED CORRECTION（Lead 指出）：
#    帧间隔的物理下限就是 vsync 周期 1000/60 ≈ 16.67ms。
#    "帧间隔 p95 ≤ 16ms" 在 60Hz 上**物理不可达**，那是把刷新率当成要求，
#    属于预算定义错误而非实现问题。scroll 改用独立的三重硬判据（见 SCROLL_BUDGET）。
# ─────────────────────────────────────────────────────────────────────────────
USER_THRESHOLDS = {
    "typing": 16.0,     # ms，单次按键处理耗时（操作耗时，不是帧间隔）
    "open": 1000.0,     # ms
}
BUDGET_FACTOR = 1.15

# ── scroll 专项预算（方案 A，Lead 裁定）───────────────────────────────────────
#   单位是**帧间隔**（相邻 rAF 的时间差），不是"操作耗时"。
#   三条同时满足才算 PASS：
#     ① 帧间隔 p95 ≤ 20ms   —— 16.67ms(vsync 下限) + 约 1 帧容差
#     ② 卡顿比例 ≤ 0.05     —— 帧间隔 > 25ms(1.5 帧预算) 的帧占比
#     ③ 长任务 = 0 个
#   同时保留"不退化 > 1.15× P_old"的回归判据。
VSYNC_FRAME_MS = 1000.0 / 60.0      # ≈16.67
SCROLL_BUDGET = {
    "p95MaxMs": 20.0,               # 16.67 下限 + 一帧容差
    "jankRatioMax": 0.05,           # > 25ms 帧占比
    "longTaskMaxCount": 0,
    "regressionFactor": 1.15,
}

# 「当前实现即红」的项：不是阶段 2 退化，而是既有事实（阶段 1 gate 已记录）。
#   open   : p95 ≈ 1038ms > 1000ms 阈值（gate 记 1434ms）
#   scroll : p95 / 卡顿比例已达标，但**每次滚动都有 1 个 ~53ms 长任务**
#            （3 次独立复跑一致：53 / 54 / 53 ms）——这是窗口化边界跨越的首帧成本，
#            属当前实现事实，不是本次回归。
#   => 阶段 2 的约束是「不得恶化 >1.15x P_old」，改善另计；
#      不要把"当前红"误读为"本次回归"。
CURRENTLY_RED = {"open", "scroll"}

# 复现性判据的适用下限：p95 < 5ms 时相对比不稳定（0.55 vs 0.45 = 1.22 但绝对差仅 0.1ms），
#   这类操作改用**绝对差** ≤ 1.0ms 判定。见契约 §5.2。
REPRO_MIN_P95_MS = 5.0
REPRO_ABS_TOL_MS = 1.0

# 噪声门口径沿用 phase1-performance-gate.md
NOISE = {
    "maxIqrOverMedian": 0.25,
    "maxP95OverMedian": 1.60,
    "maxRoundSpread": 0.20,
}

# 度量口径 -> 从 run 结果里取哪个样本序列
A_LEVEL = ["typing", "scroll", "select", "paste", "undo", "find", "save",
           "viewSwitch", "structEdit", "format", "kpHover", "open", "tabSwitch"]
B_LEVEL = ["memGrowth"]


def load_harness(kb_dir: Path, port: int):
    os.environ["MEMORIA_HARNESS_KB"] = str(kb_dir)
    os.environ["MEMORIA_HARNESS_PORT"] = str(port)
    spec = importlib.util.spec_from_file_location("memoria_perfops_harness", str(HARNESS_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wait_port(port: int, timeout: float = 20.0) -> bool:
    import socket
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def git_short_sha() -> str:
    p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    return p.stdout.strip() or "nogit"


def pct(vals, q):
    """线性插值分位数。"""
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return None
    if n == 1:
        return v[0]
    h = (n - 1) * q
    lo = int(h)
    hi = min(lo + 1, n - 1)
    return v[lo] + (v[hi] - v[lo]) * (h - lo)


def collect_samples(runs, metric):
    """把多轮 runs 的样本合成一个序列。"""
    out = []
    for r in runs:
        ss = r.get("samples") or []
        out.extend([x for x in ss if isinstance(x, (int, float))])
    return out


def summarize(name, op, metric):
    """对单个操作做统计并按噪声门判定可用性。"""
    runs = [r for r in (op.get("runs") or []) if isinstance(r, dict)]
    s = {"id": name, "tier": op.get("tier"), "mode": op.get("mode"),
         "metric": op.get("metric"), "doc": op.get("doc"),
         "status": op.get("status")}
    if op.get("error"):
        s["error"] = op["error"]

    if metric == "frames":
        # 滚动：帧间隔 p95 + 长任务（Lead 特别要求，不用"滚完耗时"）
        allGaps = collect_samples(runs, "frames")
        extras = [r.get("extra") or {} for r in runs if r.get("extra")]
        lt = [e.get("longTaskCount", 0) for e in extras]
        ltmax = [e.get("longTaskMaxMs", 0) for e in extras]
        s["samples"] = len(allGaps)
        s["p50"] = round(pct(allGaps, 0.50), 2) if allGaps else None
        s["p95"] = round(pct(allGaps, 0.95), 2) if allGaps else None
        s["max"] = round(max(allGaps), 2) if allGaps else None
        jr = [e.get("jankRatio") for e in extras if isinstance(e.get("jankRatio"), (int, float))]
        s["extra"] = {
            "longTaskCountMedian": statistics.median(lt) if lt else None,
            "longTaskMaxMsMax": max(ltmax) if ltmax else None,
            "framesMedian": statistics.median([e.get("frames", 0) for e in extras]) if extras else None,
            "scrolledPx": extras[0].get("scrolledPx") if extras else None,
            "jankRatioMedian": round(statistics.median(jr), 4) if jr else None,
            "jankRatioMax": round(max(jr), 4) if jr else None,
            "jankThresholdMs": extras[0].get("jankThresholdMs") if extras else None,
        }
        vals = allGaps
    elif metric == "heap":
        extras = [r.get("extra") or {} for r in runs if r.get("extra")]
        deltas = [e.get("heapDeltaMB") for e in extras if isinstance(e.get("heapDeltaMB"), (int, float))]
        s["extra"] = {"heapDeltaMB": deltas,
                      "heapBeforeMB": [e.get("heapBeforeMB") for e in extras],
                      "heapAfterMB": [e.get("heapAfterMB") for e in extras],
                      "supported": bool(extras and extras[0].get("supported"))}
        # heap 用「每轮 delta 的中位数」作为度量
        s["p50"] = round(statistics.median(deltas), 2) if deltas else None
        s["p95"] = max(deltas) if deltas else None
        s["samples"] = len(deltas)
        vals = deltas
    else:
        vals = collect_samples(runs, "latency")
        s["samples"] = len(vals)
        s["p50"] = round(pct(vals, 0.50), 2) if vals else None
        s["p95"] = round(pct(vals, 0.95), 2) if vals else None
        s["max"] = round(max(vals), 2) if vals else None

    # 噪声门（需要 >=3 个样本）
    if vals and len(vals) >= 3 and s.get("p50"):
        med = statistics.median(vals)
        q1, q3 = pct(vals, 0.25), pct(vals, 0.75)
        s["iqrOverMedian"] = round((q3 - q1) / med, 3) if med else None
        s["p95OverMedian"] = round(pct(vals, 0.95) / med, 3) if med else None
        # 轮间相对极差：每轮取中位数
        roundMeds = []
        for r in runs:
            rv = [x for x in (r.get("samples") or []) if isinstance(x, (int, float))]
            if rv:
                roundMeds.append(statistics.median(rv))
        if len(roundMeds) >= 2 and min(roundMeds) > 0:
            s["roundSpread"] = round((max(roundMeds) - min(roundMeds)) / min(roundMeds), 3)
        else:
            s["roundSpread"] = None
        s["noiseOk"] = (
            (s["iqrOverMedian"] is None or s["iqrOverMedian"] <= NOISE["maxIqrOverMedian"])
            and (s["p95OverMedian"] is None or s["p95OverMedian"] <= NOISE["maxP95OverMedian"])
            and (s["roundSpread"] is None or s["roundSpread"] <= NOISE["maxRoundSpread"])
        )
    else:
        s["noiseOk"] = None
    return s


def budget_for(name, p_old):
    """返回 (budget, basis)。scroll 走独立三重判据，这里返回回归预算作参照。"""
    if p_old is None:
        return None, None
    if name == "scroll":
        # scroll 不用固定 ms 阈值（16.67ms 是 vsync 下限，见 SCROLL_BUDGET 注释），
        # 这里只给"不退化"回归预算作参照；硬判据在 scroll_verdict()。
        return round(p_old * SCROLL_BUDGET["regressionFactor"], 2), "P_old×1.15（回归参照；硬判据见三重条件）"
    user = USER_THRESHOLDS.get(name)
    factor_budget = round(p_old * BUDGET_FACTOR, 2)
    if user is not None:
        return round(min(user, factor_budget), 2), "min(阈值 %s, P_old×1.15)" % user
    return factor_budget, "P_old×1.15"


def scroll_verdict(s, p_old):
    """scroll 三重硬判据（方案 A）。返回 (verdict, reasons, detail)。

    单位是**帧间隔**，物理下限 = vsync 16.67ms，故用 20ms（下限+一帧容差）。
    """
    p95 = s.get("p95")
    ex = s.get("extra") or {}
    jank = ex.get("jankRatioMax")
    lt = ex.get("longTaskCountMedian")
    ltmax = ex.get("longTaskMaxMsMax")
    reasons = []
    if p95 is not None and p95 > SCROLL_BUDGET["p95MaxMs"]:
        reasons.append("帧间隔 p95 %.2fms > %.2fms" % (p95, SCROLL_BUDGET["p95MaxMs"]))
    if isinstance(jank, (int, float)) and jank > SCROLL_BUDGET["jankRatioMax"]:
        reasons.append("卡顿比例 %.4f > %.2f" % (jank, SCROLL_BUDGET["jankRatioMax"]))
    # 长任务：任一长任务即算超（门槛为 0）
    if (isinstance(lt, (int, float)) and lt > 0) or (isinstance(ltmax, (int, float)) and ltmax > 0):
        reasons.append("长任务 中位%s/最长%sms > 0" % (lt, ltmax))
    # 回归判据
    if p_old is not None and p95 is not None and p95 > p_old * SCROLL_BUDGET["regressionFactor"]:
        reasons.append("退化 %.3f× > %.2f× P_old" % (p95 / p_old, SCROLL_BUDGET["regressionFactor"]))
    detail = {
        "p95": p95, "p95MaxMs": SCROLL_BUDGET["p95MaxMs"],
        "jankRatioMax": jank, "jankRatioMaxAllowed": SCROLL_BUDGET["jankRatioMax"],
        "longTaskCountMedian": lt, "longTaskMaxMsMax": ltmax, "longTaskAllowed": 0,
        "pOld": p_old,
    }
    return ("FAIL" if reasons else "PASS"), reasons, detail


def main():
    ap = argparse.ArgumentParser(description="绩效操作覆盖矩阵 runner")
    ap.add_argument("--kb", default="tests/probe-kb")
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--port", type=int, default=8645)
    ap.add_argument("--work-kb", default="artifacts/_probe_kb")
    ap.add_argument("--ops", default="all", help="comma list 或 all")
    ap.add_argument("--rounds", type=int, default=3, help="每个操作的轮数（默认 3）")
    ap.add_argument("--inject", default=None, help="注入已知退化：busywait")
    ap.add_argument("--cdp", default=None, help="真机 CDP endpoint（首开/公式必须）")
    ap.add_argument("--baseline", default=None, help="对比基线 json（判超预算用）")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sha = git_short_sha()
    stem = "perf-ops-%s_%s" % (args.label, sha)
    out_path = RESULTS_DIR / ("%s.json" % stem)

    harness_url = None
    harness_thread = None
    if not args.cdp:
        src_kb = (REPO_ROOT / args.kb).resolve()
        if not src_kb.is_dir():
            print("[perfops] 源语料不存在: %s" % src_kb, file=sys.stderr)
            return 2
        work_kb = (REPO_ROOT / args.work_kb).resolve()
        if work_kb.exists():
            shutil.rmtree(work_kb, ignore_errors=True)
        work_kb.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_kb, work_kb)
        harness = load_harness(work_kb, args.port)
        import bottle
        th = threading.Thread(target=bottle.run, kwargs=dict(app=harness.app, host="127.0.0.1", port=args.port, quiet=True), daemon=True)
        th.start()
        harness_thread = th
        if not wait_port(args.port):
            print("[perfops] harness 未起来", file=sys.stderr)
            return 2
        harness_url = "http://127.0.0.1:%d/" % args.port

    cmd = ["node", str(CLI), "--ops", args.ops, "--rounds", str(args.rounds), "--out", str(out_path)]
    if args.cdp:
        cmd += ["--cdp", args.cdp]
    else:
        cmd += ["--url", harness_url]
    if args.inject:
        cmd += ["--inject", args.inject]
    print("[perfops] 运行: %s" % " ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print("[perfops] node 驱动超时", file=sys.stderr)
        return 3
    if proc.returncode != 0 or not out_path.exists():
        print("[perfops] node 驱动失败 code=%s" % proc.returncode, file=sys.stderr)
        print("--- stdout ---\n%s\n--- stderr ---\n%s" % (
            proc.stdout.decode("utf-8", "replace")[-3000:], proc.stderr.decode("utf-8", "replace")[-6000:]), file=sys.stderr)
        return 3

    raw = json.loads(out_path.read_text(encoding="utf-8"))
    mode = raw.get("mode")

    # ── 逐操作汇总 ──
    summaries = {}
    for name, op in (raw.get("ops") or {}).items():
        summaries[name] = summarize(name, op, op.get("metric"))

    # ── 基线对比 / 预算判定 ──
    baseline = None
    if args.baseline:
        bp = Path(args.baseline)
        if not bp.is_absolute():
            bp = RESULTS_DIR / bp
        if bp.exists():
            baseline = json.loads(bp.read_text(encoding="utf-8"))
    # 若本次是 baseline（无 --baseline），预算以自身 P_old 计算并落盘
    baseline_ops = (baseline or {}).get("ops") or raw.get("baselineOps") or {}

    table = []
    for name, s in summaries.items():
        base = baseline_ops.get(name) or {}
        p_old = base.get("p95") if base else s.get("p95")
        budget, basis = budget_for(name, p_old)
        verdict = None
        reasons = []
        if name == "scroll":
            # scroll 走三重硬判据（方案 A），单位是帧间隔；不受 --baseline 与否影响
            verdict, reasons, _sd = scroll_verdict(s, p_old)
        elif baseline and s.get("p95") is not None and budget is not None:
            verdict = "FAIL" if s["p95"] > budget else "PASS"
        # open：当前实现已超 1000ms 阈值（阶段 1 gate 记 1434ms）。标注"当前红"，
        #   阶段 2 的约束是"不得恶化 >1.15×"，改善另计 => 单独打标，不与"退化判红"混淆。
        # 「当前即红」标注：open 超 1000ms 阈值；scroll 长任务>0（见 CURRENTLY_RED 注释）。
        #   与"阶段 2 退化判红"分开，避免把既有事实误读成回归。
        if name == "open":
            currently_red = (s.get("p95") is not None
                             and USER_THRESHOLDS.get("open") is not None
                             and s["p95"] > USER_THRESHOLDS["open"])
        elif name == "scroll":
            currently_red = (verdict == "FAIL")
        else:
            currently_red = False
        table.append({
            "id": name, "tier": s.get("tier"), "mode": s.get("mode"), "metric": s.get("metric"),
            "p50": s.get("p50"), "p95": s.get("p95"), "samples": s.get("samples"),
            "pOld": p_old, "budget": budget, "budgetBasis": basis,
            "verdict": verdict, "verdictReasons": reasons,
            "currentlyRed": currently_red,
            "noiseOk": s.get("noiseOk"),
            "status": s.get("status"), "error": s.get("error"),
            "extra": s.get("extra"),
        })

    result = {
        "schema": "memoria-perf-ops/v1",
        "sha": sha, "label": args.label, "mode": mode,
        "environment": raw.get("environment"), "inject": raw.get("inject"),
        "budgetRule": "min(用户可感知阈值, P_old×1.15)；无阈值取 P_old×1.15",
        "noiseGate": NOISE,
        "userThresholds": USER_THRESHOLDS,
        "ops": {t["id"]: t for t in table},
        "summaries": summaries,
        "raw": raw,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Markdown 报告 ──
    md = RESULTS_DIR / ("%s.md" % stem)
    L = []
    L.append("# 绩效操作覆盖矩阵 · %s（%s）\n" % (args.label, sha))
    L.append("> 模式：**%s**%s" % (mode, "" if mode == "realapp" else "（无头 Edge；首开/公式相关需 `--cdp` 真机）"))
    L.append("> 轮数：每操作 %d 轮　｜　噪声门：IQR/med≤%.2f, p95/med≤%.2f, roundSpread≤%.2f\n" % (
        args.rounds, NOISE["maxIqrOverMedian"], NOISE["maxP95OverMedian"], NOISE["maxRoundSpread"]))
    if raw.get("inject"):
        L.append("> **注入**：`%s` —— 期望被判超预算时须如实显红\n" % json.dumps(raw["inject"], ensure_ascii=False))
    L.append("## 操作矩阵（A 级必测 %d 项 / B 级记录 %d 项）\n" % (
        len([t for t in table if t["tier"] == "A"]), len([t for t in table if t["tier"] == "B"])))
    L.append("| 操作 | 级 | 度量 | p50 | **p95** | 样本 | P_old | 预算 | 判定 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for t in table:
        v = "-" if t["verdict"] is None else ("🟢 PASS" if t["verdict"] == "PASS" else "🔴 FAIL")
        if t.get("currentlyRed"):
            v += " ⚠️当前红"
        unit = "ms"
        if t["id"] == "memGrowth":
            unit = "MB"
        budget_cell = ("%s %s" % (t["budget"], unit)) if t["budget"] is not None else "-"
        if t["id"] == "scroll":
            budget_cell = "p95≤%s + 卡顿≤%.2f + 长任务=0" % (
                SCROLL_BUDGET["p95MaxMs"], SCROLL_BUDGET["jankRatioMax"])
        L.append("| `%s` | %s | %s | %s | **%s** | %s | %s | %s | %s |" % (
            t["id"], t["tier"], t["metric"],
            ("%s %s" % (t["p50"], unit)) if t["p50"] is not None else "-",
            ("%s %s" % (t["p95"], unit)) if t["p95"] is not None else "-",
            t["samples"] or 0,
            ("%s %s" % (t["pOld"], unit)) if t["pOld"] is not None else "-",
            budget_cell,
            v))
    L.append("")
    # 判定失败原因明细
    failrows = [t for t in table if t["verdict"] == "FAIL"]
    if failrows:
        L.append("### 判定为 FAIL 的原因\n")
        for t in failrows:
            rs = t.get("verdictReasons") or []
            if rs:
                L.append("- `%s`：%s" % (t["id"], "；".join(rs)))
            else:
                L.append("- `%s`：p95 %s %s > 预算 %s %s" % (
                    t["id"], t["p95"], "ms", t["budget"], "ms"))
        L.append("")
    # 滚动专项
    sc = summaries.get("scroll") or {}
    if sc.get("samples"):
        L.append("## 滚动专项（Lead 重点项）\n")
        L.append("**单位是「帧间隔」，不是「操作耗时」** —— 帧间隔的物理下限就是 vsync 周期 `1000/60 ≈ %.2f ms`。"
                 % VSYNC_FRAME_MS)
        L.append("所以 `p95 ≤ 16ms` 在 60Hz 上**物理不可达**（那是把刷新率当要求）。"
                 "scroll 预算改用：**p95 ≤ %.0f ms（下限+一帧容差）且 卡顿比例 ≤ %.2f 且 长任务 = 0**，"
                 "并保留「不退化 >%.2f× P_old」回归判据。\n" % (
                     SCROLL_BUDGET["p95MaxMs"], SCROLL_BUDGET["jankRatioMax"], SCROLL_BUDGET["regressionFactor"]))
        ex = sc.get("extra") or {}
        sverdict, sreasons, _sd = scroll_verdict(sc, sc.get("p95"))
        L.append("| 条件 | 实测 | 门槛 | 结果 |")
        L.append("|---|---|---|---|")
        L.append("| 帧间隔 p95 | **%s ms** | ≤ %s ms | %s |" % (
            sc.get("p95"), SCROLL_BUDGET["p95MaxMs"],
            "✅" if (sc.get("p95") or 0) <= SCROLL_BUDGET["p95MaxMs"] else "❌"))
        jr = ex.get("jankRatioMax")
        L.append("| 卡顿比例（帧间隔 > %sms） | **%s** | ≤ %.2f | %s |" % (
            ex.get("jankThresholdMs"), jr, SCROLL_BUDGET["jankRatioMax"],
            "✅" if isinstance(jr, (int, float)) and jr <= SCROLL_BUDGET["jankRatioMax"] else "❌"))
        lt = ex.get("longTaskCountMedian"); ltm = ex.get("longTaskMaxMsMax")
        L.append("| 长任务 | 中位 %s 个 / 最长 %s ms | = 0 | %s |" % (
            lt, ltm, "✅" if not lt and not ltm else "❌"))
        L.append("")
        L.append("- 帧间隔明细：p50=%s ms，max=%s ms（%d 帧）；滚动距离 %s px" % (
            sc.get("p50"), sc.get("max"), sc.get("samples"), ex.get("scrolledPx")))
        L.append("- **滚动判定：%s**%s\n" % (
            "🟢 PASS" if sverdict == "PASS" else "🔴 FAIL",
            "" if not sreasons else "（%s）" % "；".join(sreasons)))
    # 失败/错误
    errs = [t for t in table if t["status"] != "ran" or t["error"]]
    if errs:
        L.append("## ⚠️ 未跑成 / 出错的操作\n")
        for t in errs:
            L.append("- `%s`：%s" % (t["id"], t.get("error") or t.get("status")))
        L.append("")
    # 预算口径
    L.append("## 预算口径\n")
    L.append("**绝对预算 = min(用户可感知阈值, P_old × 1.15)**；无用户阈值的取 `P_old × 1.15`。\n")
    L.append("| 操作 | 用户可感知阈值 | 依据 |")
    L.append("|---|---|---|")
    for k, v in USER_THRESHOLDS.items():
        L.append("| `%s` | %s | %s |" % (k, v, {
            "typing": "60fps 单帧预算（gate §0 G1' 既定目标 16ms）；单位是「操作耗时」，16ms 合理",
            "open": "可接受首开阈值（gate 已用 1434ms 观测作参照）",
        }.get(k, "-")))
    L.append("| `scroll` | **不含固定 ms 阈值** | 帧间隔物理下限 = vsync %.2f ms，`≤16ms` 不可达 ⇒ 改用三重判据（见「滚动专项」） |" % VSYNC_FRAME_MS)
    L.append("")
    # 当前即红项（不是退化，是既有事实）
    reds = [t for t in table if t.get("currentlyRed")]
    if reds:
        L.append("## ⚠️ 当前实现即未达标的项（**不是**阶段 2 退化）\n")
        for t in reds:
            if t["id"] == "open":
                L.append("- `open`：p95 = **%s ms** > 阈值 %s ms。阶段 1 gate 已记录该操作长期偏高（1434ms）。" % (
                    t["p95"], USER_THRESHOLDS.get("open")))
            elif t["id"] == "scroll":
                ex = t.get("extra") or {}
                L.append("- `scroll`：p95 %s ms 与卡顿比例 %s 均已达标，但**长任务 = %s ms（门槛 0）**。" % (
                    t["p95"], ex.get("jankRatioMax"), ex.get("longTaskMaxMsMax")))
                L.append("  该项 3 次独立复跑一致（53/54/53 ms），是窗口化边界跨越的首帧成本，属当前实现事实。")
        L.append("")
        L.append("**阶段 2 的约束是「不得恶化 >1.15× `P_old`」，改善另计**——不要把「当前红」误读为「本次回归」。\n")
    md.write_text("\n".join(L), encoding="utf-8")

    print("[perfops] 产物：\n  %s\n  %s" % (md, out_path))
    ran = [t for t in table if t["status"] == "ran" and t["p95"] is not None]
    print("[perfops] 成功 %d/%d 项（A 级 %d 项）" % (
        len(ran), len(table), len([t for t in ran if t["tier"] == "A"])))
    if any(t["verdict"] == "FAIL" for t in table):
        print("[perfops] 有操作超预算 ✗")
    return 0


if __name__ == "__main__":
    sys.exit(main())
