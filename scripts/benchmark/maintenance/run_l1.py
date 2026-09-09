"""维护机制基准 · L1 headless A/B 采集与汇总（B3）。

用法（仓库根）：
  python scripts/benchmark/maintenance/run_l1.py                # 测当前 HEAD，写 run_<sha>.json
  python scripts/benchmark/maintenance/run_l1.py --sha <commit> # 检出指定 commit 测（worktree）
  python scripts/benchmark/maintenance/run_l1.py --summary      # 仅汇总 results/*.json → summary.md
同一语料（artifacts/_bench_maintenance/kb）、同机；输出 median/mean/p95 总时，
当前代码额外给出 registry/resync 分项（MEMORIA_BENCH_TIMING）。
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.abspath(".")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
GEN = os.path.join(ROOT, "scripts", "benchmark", "maintenance", "gen_maintenance_kb.py")
KB = os.path.abspath("artifacts/_bench_maintenance/kb")
WT = os.path.abspath("artifacts/_wt_l1")
RES = os.path.join(ROOT, "scripts", "benchmark", "maintenance", "results")


def head_sha():
    return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def corpus_digest():
    h = hashlib.sha256()
    for base, _, fs in os.walk(KB):
        for f in sorted(fs):
            p = os.path.join(base, f)
            if ".memoria/manifest.yaml" in p.replace("\\", "/"):
                continue
            h.update(os.path.relpath(p, KB).encode("utf-8"))
            h.update(open(p, "rb").read())
    return h.hexdigest()


def measure(sha, files, runs, sample_n):
    shutil.rmtree(KB, ignore_errors=True)
    subprocess.run([PY, GEN, "--out", KB, "--files", str(files)], check=True, capture_output=True)
    digest = corpus_digest()  # 生成后立即采集（与 anchor_baseline 同口径，排除运行时写入）
    os.environ["MEMORIA_BENCH_TIMING"] = "1"
    use_wt = sha != head_sha()
    if use_wt:
        shutil.rmtree(WT, ignore_errors=True)
        subprocess.run(["git", "-C", ROOT, "worktree", "add", "--detach", WT, sha], check=True, capture_output=True)
        sys.path.insert(0, WT)
    from memoria.services.document import DocumentService  # noqa: E402
    from memoria.storage.scanner import collect_md_files  # noqa: E402

    svc = DocumentService(kb_path=KB)
    rels = sorted(collect_md_files(KB))
    sample = rels[:: max(1, len(rels) // sample_n)]
    totals, regs, resyncs = [], [], []
    for rel in sample:
        body = open(os.path.join(KB, rel), encoding="utf-8").read()
        for _ in range(runs):
            t0 = time.perf_counter()
            res = svc.save_document(rel, body)
            totals.append((time.perf_counter() - t0) * 1000)
            bm = res.get("bench_ms") if isinstance(res, dict) else None
            if bm and bm.get("registry") is not None:
                regs.append(bm["registry"])
            if bm and bm.get("resync") is not None:
                resyncs.append(bm["resync"])
    if use_wt:
        subprocess.run(["git", "-C", ROOT, "worktree", "remove", "--force", WT], check=True, capture_output=True)
    shutil.rmtree(KB, ignore_errors=True)
    return totals, regs, resyncs, digest


def summarize(vals):
    if not vals:
        return None
    vals = sorted(vals)
    return {
        "count": len(vals),
        "mean": round(statistics.fmean(vals), 2),
        "median": round(statistics.median(vals), 2),
        "p95": round(vals[min(len(vals) - 1, int(0.95 * len(vals)))], 2),
    }


def write_record(sha, files, runs, sample_n, totals, regs, resyncs, digest):
    data = {
        "kind": "maintenance-l1",
        "commit": sha,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "corpus": {"files": files, "digest": digest},
        "method": {"sample_files": sample_n, "runs_per_file": runs},
        "total_ms": summarize(totals),
        "registry_ms": summarize(regs),
        "resync_ms": summarize(resyncs),
    }
    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, "run_%s.json" % sha[:8]), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("run_%s.json written" % sha[:8])


def build_summary():
    rows = []
    for p in sorted(glob.glob(os.path.join(RES, "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        t = d.get("total_ms") or d.get("result_ms") or {}
        r = d.get("registry_ms") or {}
        s = d.get("resync_ms") or {}
        rows.append((d.get("commit", os.path.basename(p)[:8]), d.get("kind", "?"), t.get("median"), t.get("p95"), r.get("median"), s.get("median")))
    lines = ["# 维护基准汇总（summary）", "", "| commit | kind | total median | total p95 | registry median | resync median |", "|---|---|---|---|---|---|"]
    for c, k, med, p95, r, s in rows:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (c, k, med, p95, r, s))
    with open(os.path.join(RES, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("summary.md updated")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", default=None)
    ap.add_argument("--files", type=int, default=200)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        build_summary()
        return
    sha = (a.sha or head_sha()).strip()
    totals, regs, resyncs, digest = measure(sha, a.files, a.runs, a.sample)
    write_record(sha, a.files, a.runs, a.sample, totals, regs, resyncs, digest)
    build_summary()


if __name__ == "__main__":
    main()
