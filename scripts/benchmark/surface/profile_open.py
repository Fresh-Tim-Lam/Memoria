# -*- coding: utf-8 -*-
"""单文档打开（openFile）稳态分段 — task-69 的"恢复文件 ≤5s"口径测量入口。

为什么单独一个入口：
    boot 期的"自动打开首个文件"常常是小文件（本仓库 baseline KB 的 files[0] 是
    `homework/README.md`，openFile 只要 ~9ms），**不能代表用户恢复大章节的体感**。
    本脚本在**同一台真机、同一个隔离实例**里，boot 完成后再显式 `openFile(<大章节>)`，
    用产品自带 `_lastSwitch`（stash/load/editor/render/settle/tail + async paint）
    量"稳态打开一篇大文档"的真实成本。

做法：完全复用 `run_boot_profile.py` 的启动/清理/采集管线，只额外带 `--extra-open`。

用法：
    .venv\\Scripts\\python.exe scripts/benchmark/surface/profile_open.py
    .venv\\Scripts\\python.exe scripts/benchmark/surface/profile_open.py --doc "教材/08_第8章_差错控制编码.md" --runs 3
    .venv\\Scripts\\python.exe scripts/benchmark/surface/profile_open.py --list    # 只列候选文档

产物（与 run_boot_profile 同一套）：`artifacts/agent/verify/boot-timeline-open-<label>.{json,md}`，
其中 `runs[*].probe.extraOpen` 与 `phases.O1_extra_open_ms / O3_extra_open_*` 是本文档的分段。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DEFAULT_DOC = "教材/08_第8章_差错控制编码.md"


def _utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def list_candidates(kb: Path, top: int = 10) -> list[tuple[str, int]]:
    rows = []
    for p in kb.rglob("*.md"):
        try:
            rows.append((str(p.relative_to(kb)).replace("\\", "/"), p.stat().st_size))
        except Exception:
            continue
    rows.sort(key=lambda kv: -kv[1])
    return rows[:top]


def main() -> int:
    _utf8_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC, help="要测量的文档（KB 内相对路径）")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", default="")
    ap.add_argument("--kb", default=str(REPO_ROOT / "artifacts" / "baseline-kb" / "数字通信原理"))
    ap.add_argument("--port", type=int, default=9662)
    ap.add_argument("--list", action="store_true", help="只列出 KB 内最大的 md（选 --doc 用）")
    args = ap.parse_args()

    kb = Path(args.kb).resolve()
    if args.list:
        for rel, size in list_candidates(kb):
            print(f"{size:>9,}  {rel}")
        return 0

    sys.path.insert(0, str(HERE))
    import run_boot_profile as rbp  # noqa: E402

    label = args.label or f"open-{time.strftime('%Y%m%d-%H%M%S')}"
    argv = [
        "run_boot_profile.py",
        "--runs", str(args.runs),
        "--label", label,
        "--port", str(args.port),
        "--kb", str(kb),
        "--extra-open", args.doc,
    ]
    print(f"[profile-open] doc={args.doc} runs={args.runs} label={label}")
    old = sys.argv[:]
    try:
        sys.argv = argv
        return rbp.main()
    finally:
        sys.argv = old


if __name__ == "__main__":
    raise SystemExit(main())
