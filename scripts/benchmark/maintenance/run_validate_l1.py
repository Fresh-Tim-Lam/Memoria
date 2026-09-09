#!/usr/bin/env python3
"""G5.1 F01 validate 基准（L1）：维护基准语料上测量 validate_kb 全量耗时与 issue 数。
用法：python scripts/benchmark/maintenance/run_validate_l1.py
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ["MEMORIA_FSYNC_MODE"] = "barrier"

CORPUS = ROOT / "artifacts" / "_bench_maintenance" / "kb"
OUT = Path(__file__).resolve().parent / "results" / "validate-l1-2026-09-10.json"


def main() -> int:
    if not CORPUS.is_dir():
        print(f"语料不存在: {CORPUS}（先运行 scripts/benchmark/maintenance/gen_maintenance_kb.py）")
        return 2
    from memoria.services.document import DocumentService

    svc = DocumentService(); svc.kb_path = str(CORPUS); svc._cache = {}
    # 预热（含首次 import/jieba/模型等噪音）
    svc.validate_kb()
    times = []
    report = None
    for _ in range(3):
        t0 = time.perf_counter()
        report = svc.validate_kb()
        times.append((time.perf_counter() - t0) * 1000)
    assert report is not None
    out = {
        "kind": "validate-l1",
        "recorded_at": "2026-09-10",
        "corpus": {"path": str(CORPUS), "files": report["files_checked"]},
        "ms": {
            "count": len(times),
            "median": round(statistics.median(times), 2),
            "min": round(min(times), 2),
            "samples": [round(t, 2) for t in times],
        },
        "issues": {
            "errors": report["errors"],
            "warnings": report["warnings"],
            "issues_count": report["issues_count"],
        },
        "note": "errors=0 为门禁目标；warnings 属可登记改进项",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    print(f"写盘: {OUT}")
    svc.close_kb()
    return 0 if report["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
