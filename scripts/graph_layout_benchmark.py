#!/usr/bin/env python3
"""Run M2 graph layout stress benchmark (Python mirror + optional Node JS)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from memoria.graph.layout_bench import run_benchmark_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Memoria graph layout stress benchmark")
    parser.add_argument("--scales", default="50,100,250,500,1000")
    parser.add_argument("--patterns", default="small_world,partitioned,star")
    parser.add_argument("--node", action="store_true", help="also run Node.js benchmark if available")
    args = parser.parse_args()

    scales = tuple(int(x) for x in args.scales.split(",") if x.strip().isdigit())
    patterns = tuple(x.strip() for x in args.patterns.split(",") if x.strip())

    report = run_benchmark_suite(scales=scales, patterns=patterns)
    print(json.dumps(report, indent=2, ensure_ascii=False))

    node = shutil.which("node")
    script = ROOT / "scripts" / "graph_layout_benchmark.mjs"
    if args.node and node and script.is_file():
        proc = subprocess.run(
            [node, str(script), "--scales", args.scales, "--patterns", ",".join(patterns[:2])],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if proc.returncode == 0:
            js_report = json.loads(proc.stdout)
            print("\n--- Node JS benchmark ---")
            print(json.dumps(js_report, indent=2, ensure_ascii=False))
        else:
            print(proc.stderr or proc.stdout, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
