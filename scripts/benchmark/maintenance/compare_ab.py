"""维护基准 · A/B 交错多轮对比（消除机器漂移）。

用法（仓库根）：
  python scripts/benchmark/maintenance/compare_ab.py
    [--base ae66a012] [--head <HEAD|sha>] [--rounds 3]
    [--sample 20] [--runs 3]
每轮内按 base/head 交替顺序调用 run_l1 --worker，轮间再颠倒顺序（ABBA 抗漂移）。
输出 results/compare_<base8>_<head8>.md 与结论：改善 / 持平 / 回退需查。
"""
import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(".")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
RUN_L1 = os.path.join(ROOT, "scripts", "benchmark", "maintenance", "run_l1.py")
RES = os.path.join(ROOT, "scripts", "benchmark", "maintenance", "results")


def head_sha():
    return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def measure_worker(sha, sample, runs):
    out = subprocess.run(
        [PY, RUN_L1, "--worker", "--sha", sha, "--sample", str(sample), "--runs", str(runs)],
        capture_output=True, text=True, timeout=900,
    )
    if out.returncode != 0:
        raise SystemExit("worker FAIL sha=%s\n%s" % (sha, out.stderr[-800:]))
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    return json.loads(lines[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="ae66a012")
    ap.add_argument("--head", default=None)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    base = a.base.strip()
    head = (a.head or head_sha()).strip()
    print("compare base=%s head=%s rounds=%d" % (base, head, a.rounds))

    per = {base: [], head: []}
    for r in range(a.rounds):
        order = [base, head] if r % 2 == 0 else [head, base]
        for sha in order:
            w = measure_worker(sha, a.sample, a.runs)
            med = (w.get("total_ms") or {}).get("median")
            per[sha].append({"round": r + 1, "median": med, "p95": (w.get("total_ms") or {}).get("p95"),
                             "registry": (w.get("registry_ms") or {}).get("median"),
                             "resync": (w.get("resync_ms") or {}).get("median")})
            print("  r%d %s median=%s" % (r + 1, sha[:8], med))

    def stats(lst):
        vals = [x["median"] for x in lst if x["median"] is not None]
        return vals

    bv, hv = stats(per[base]), stats(per[head])
    b_med = statistics.median(bv) if bv else None
    h_med = statistics.median(hv) if hv else None
    delta = (h_med - b_med) / b_med * 100 if b_med else None
    if delta is None:
        verdict = "数据不足"
    elif abs(delta) <= 10:
        verdict = "持平"
    elif delta < 0:
        verdict = "改善"
    else:
        verdict = "回退需查"
    lines = ["# A/B 对比（交错多轮，抗机器漂移）",
             "",
             "- 时间：%s" % datetime.now(timezone.utc).isoformat(),
             "- base：`%s`（tag maint-base） vs head：`%s`" % (base, head),
             "- 方法：rounds=%d、sample=%d 文件、runs=%d；每轮 base/head 交替，轮间颠倒" % (a.rounds, a.sample, a.runs),
             "- 样本：语料 200 文件（digest 见 run json，生成确定性）",
             "",
             "| round | base median | head median |",
             "|---|---|---|"]
    for i in range(a.rounds):
        bl = next((x["median"] for x in per[base] if x["round"] == i + 1), None)
        hl = next((x["median"] for x in per[head] if x["round"] == i + 1), None)
        lines.append("| %d | %s | %s |" % (i + 1, bl, hl))
    lines += ["",
              "- base 各轮 median：%s → 中位 %s" % (bv, b_med),
              "- head 各轮 median：%s → 中位 %s" % (hv, h_med),
              "- Δ = %.1f%%" % (delta if delta is not None else float("nan")),
              "- **结论：%s**" % verdict,
              "",
              "> 说明：%s" % ("多轮一致时 Δ 才可信；单轮波动大时需增加 rounds。" if verdict != "数据不足" else "")]
    text = "\n".join(lines) + "\n"
    os.makedirs(RES, exist_ok=True)
    out_path = os.path.join(RES, "compare_%s_%s.md" % (base[:8], head[:8]))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
