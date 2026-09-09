"""锚定指定快照（默认改造前 ae66a012 / tag maint-base）的维护基线测试数据。

用法（仓库根）：
  python scripts/benchmark/maintenance/anchor_baseline.py            # 默认 ae66a012
  python scripts/benchmark/maintenance/anchor_baseline.py --sha <sha>
流程：生成确定性语料 → 检出目标 commit 到 worktree → 用该版本代码实测保存链路线时
（registry+resync 合计总耗时；目标版本若无内部分项则外部计时）→ 记录 corpus digest/环境/统计 → 归档。
"""
import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ap = argparse.ArgumentParser()
ap.add_argument("--sha", default="ae66a012")
args = ap.parse_args()

ROOT = os.path.abspath(".")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
GEN = os.path.join(ROOT, "scripts", "benchmark", "maintenance", "gen_maintenance_kb.py")
KB = os.path.abspath("artifacts/_bench_anchor_kb")
WT = os.path.abspath("artifacts/_wt_anchor")
RES = os.path.join(ROOT, "scripts", "benchmark", "maintenance", "results")
BASE_SHA = args.sha

# 1) 语料
shutil.rmtree(KB, ignore_errors=True)
subprocess.run([PY, GEN, "--out", KB, "--files", "200"], check=True, capture_output=True)

# corpus digest（md+sidecar，排除 manifest 时间戳）
h = hashlib.sha256()
for base, _, fs in os.walk(KB):
    for f in sorted(fs):
        p = os.path.join(base, f)
        if ".memoria/manifest.yaml" in p.replace("\\", "/"):
            continue
        h.update(os.path.relpath(p, KB).encode("utf-8"))
        h.update(open(p, "rb").read())
corpus_digest = h.hexdigest()

# 2) worktree @ baseline
shutil.rmtree(WT, ignore_errors=True)
subprocess.run(["git", "-C", ROOT, "worktree", "add", "--detach", WT, BASE_SHA], check=True, capture_output=True)

# 3) 用旧代码测量
sys.path.insert(0, WT)
from memoria.services.document import DocumentService  # noqa: E402
from memoria.storage.scanner import collect_md_files  # noqa: E402

svc = DocumentService(kb_path=KB)
rels = sorted(collect_md_files(KB))
sample = rels[:: max(1, len(rels) // 20)]  # ~20 个文件
RUNS = 3
timings = []
for rel in sample:
    body = open(os.path.join(KB, rel), encoding="utf-8").read()
    for _ in range(RUNS):
        t0 = time.perf_counter()
        svc.save_document(rel, body)
        timings.append((time.perf_counter() - t0) * 1000)

timings.sort()
med = statistics.median(timings)
p95 = timings[min(len(timings) - 1, int(0.95 * len(timings)))]
mean = statistics.fmean(timings)
data = {
    "kind": "maintenance-baseline",
    "baseline_commit": BASE_SHA,
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "corpus": {"files": 200, "kps": 599, "links": 333, "digest": corpus_digest, "gen_cmd": "gen_maintenance_kb.py --files 200"},
    "env": {"python": sys.version.split()[0], "os": os.name},
    "method": {"sample_files": len(sample), "runs_per_file": RUNS, "total_saves": len(timings), "instrument": "external total save_document ms"},
    "result_ms": {"count": len(timings), "mean": round(mean, 2), "median": round(med, 2), "p95": round(p95, 2)},
}
os.makedirs(RES, exist_ok=True)
with open(os.path.join(RES, "baseline_%s.json" % BASE_SHA), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
md = """# 维护基线（改造前锚定）

- 基线 commit：`%(sha)s`（tag `maint-base`）
- 记录时间：%(when)s
- 语料：200 文件 / 599 KP / 333 links（digest `%(digest)s`），生成命令 `%(gen)s`
- 环境：python %(py)s / %(os)s
- 方法：外部计时 `save_document`（含 registry+resync 维护），样本 %(sf)s 文件 × %(runs)s 次 = %(n)s 次保存；旧代码无内部分项（registry/resync）计时，改造后对比时以新增 bench_ms 分项对齐口径
- 结果（ms）：mean=%(mean)s median=%(median)s p95=%(p95)s
""" % {
    "sha": BASE_SHA, "when": data["recorded_at"],
    "digest": corpus_digest[:16], "gen": data["corpus"]["gen_cmd"],
    "py": data["env"]["python"], "os": data["env"]["os"],
    "sf": data["method"]["sample_files"], "runs": RUNS, "n": data["result_ms"]["count"],
    "mean": data["result_ms"]["mean"], "median": data["result_ms"]["median"], "p95": data["result_ms"]["p95"],
}
with open(os.path.join(RES, "baseline_%s.md" % BASE_SHA), "w", encoding="utf-8") as f:
    f.write(md)
print(md)

# 4) 清理
subprocess.run(["git", "-C", ROOT, "worktree", "remove", "--force", WT], check=True, capture_output=True)
shutil.rmtree(KB, ignore_errors=True)
