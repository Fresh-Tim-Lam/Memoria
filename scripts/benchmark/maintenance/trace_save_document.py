#!/usr/bin/env python3
"""save_document 子阶段剖析（L1 归因辅助）。

在当前代码上生成小语料并测量 save_document 的分项（原子写 / registry /
KP range resync / manifest touch）耗时中位数，用于定位保存路径回退来源。

用法：
    python scripts/benchmark/maintenance/trace_save_document.py [--files 60] [--sample 40] [--runs 2]
"""

from __future__ import annotations

import argparse
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

KB = ROOT / "artifacts" / "_bench_trace_save_kb"
GEN = ROOT / "scripts" / "benchmark" / "maintenance" / "gen_maintenance_kb.py"
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=60)
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--runs", type=int, default=2)
    a = ap.parse_args()

    shutil.rmtree(KB, ignore_errors=True)
    import subprocess
    subprocess.run([str(PY), str(GEN), "--out", str(KB), "--files", str(a.files)], check=True, capture_output=True)

    import memoria.services.document as D
    from memoria.services.document import DocumentService

    buckets: dict[str, list[float]] = {}
    def acc(name: str, ms: float) -> None:
        buckets.setdefault(name, []).append(ms)

    # 分项计时：方法 / 模块函数
    orig_upd = DocumentService._update_registry_for_doc
    orig_resync = DocumentService._resync_kp_ranges_after_edit
    def wrap(name: str, fn):
        def inner(self, *args, **kwargs):
            t = time.perf_counter()
            try:
                return fn(self, *args, **kwargs)
            finally:
                acc(name, (time.perf_counter() - t) * 1000)
        return inner
    DocumentService._update_registry_for_doc = wrap("registry", orig_upd)
    DocumentService._resync_kp_ranges_after_edit = wrap("resync", orig_resync)
    orig_touch = D.touch_manifest_entry
    def touch(self_or_kb, *args, **kwargs):
        t = time.perf_counter()
        try:
            return orig_touch(self_or_kb, *args, **kwargs)
        finally:
            acc("manifest_touch", (time.perf_counter() - t) * 1000)
    D.touch_manifest_entry = touch

    os.environ["MEMORIA_BENCH_TIMING"] = "1"
    svc = DocumentService()
    svc.kb_path = str(KB)
    svc._cache = {}
    from memoria.storage.manifest import ensure_manifest_baseline
    ensure_manifest_baseline(str(KB))

    from memoria.storage.scanner import collect_md_files
    rels = sorted(collect_md_files(str(KB)))
    sample = rels[:: max(1, len(rels) // a.sample)]
    write_ms: list[float] = []
    total: list[float] = []
    for rel in sample:
        body = (KB / rel).read_text(encoding="utf-8")
        for _ in range(a.runs):
            t = time.perf_counter()
            res = svc.save_document(rel, body)
            total.append((time.perf_counter() - t) * 1000)
            bm = res.get("bench_ms") if isinstance(res, dict) else {}
            if bm.get("registry") is not None:
                acc("registry(bench_ms)", bm["registry"])
            if bm.get("resync") is not None:
                acc("resync(bench_ms)", bm["resync"])
            # 单独量原子写（同路径 tmp+fsync+replace）
            full = KB / rel
            new_content = body
            tmp_full = str(full) + ".tmp"
            t = time.perf_counter()
            with open(tmp_full, "w", encoding="utf-8") as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_full, full)
            write_ms.append((time.perf_counter() - t) * 1000)

    def med(v):
        return round(statistics.median(v), 2) if v else None
    rows = [
        ("save_document total", total),
        ("atomic write(fsync)", write_ms),
        ("registry (patch)", buckets.get("registry", [])),
        ("resync (patch)", buckets.get("resync", [])),
        ("manifest_touch (patch)", buckets.get("manifest_touch", [])),
    ]
    print("\n分项中位数（ms，样本 %d）：" % len(sample))
    for name, v in rows:
        print("  %-24s median=%-8s n=%d" % (name, med(v), len(v)))
    # 还原补丁（进程即将退出，仅作形式）
    DocumentService._update_registry_for_doc = orig_upd
    DocumentService._resync_kp_ranges_after_edit = orig_resync
    D.touch_manifest_entry = orig_touch
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
