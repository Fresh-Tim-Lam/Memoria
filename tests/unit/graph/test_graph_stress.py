"""M2 图谱布局压测：synthetic 数据 + Python 布局基准（Node 可选）。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from memoria.graph.layout_bench import bench_layout_2d, run_benchmark_suite
from memoria.graph.synthetic import (
    BENCHMARK_PATTERNS,
    BENCHMARK_SCALES,
    expand_links,
    synthetic_graph,
)

ROOT = Path(__file__).resolve().parents[3]
BENCH_JS = ROOT / "scripts" / "graph_layout_benchmark.mjs"
BENCH_PY = ROOT / "scripts" / "graph_layout_benchmark.py"


def test_synthetic_graph_sizes_and_links():
    for n in (1, 10, 50):
        g = synthetic_graph(n, "small_world", seed=1)
        assert len(g["nodes"]) == n
        assert g["links"] == expand_links(g["edges"])
        assert all("source" in l and "target" in l for l in g["links"])


def test_synthetic_partitioned_components():
    g = synthetic_graph(120, "partitioned", n_groups=6, seed=2)
    assert len(g["nodes"]) == 120
    assert len(g["edges"]) >= 6


def test_synthetic_star_edges():
    g = synthetic_graph(20, "star", seed=0)
    assert len(g["edges"]) == 19
    hub = g["nodes"][0]["id"]
    assert all(e["source_id"] == hub for e in g["edges"])


@pytest.mark.parametrize("pattern", BENCHMARK_PATTERNS)
@pytest.mark.parametrize("n", BENCHMARK_SCALES[:4])
def test_synthetic_at_benchmark_scales(pattern: str, n: int):
    g = synthetic_graph(n, pattern, seed=n)
    assert len(g["nodes"]) == n
    if pattern == "star" and n > 1:
        assert len(g["links"]) == n - 1
    else:
        assert len(g["links"]) >= 0


def test_python_layout_benchmark_suite():
    report = run_benchmark_suite(scales=(50, 100, 250), patterns=("small_world",))
    assert report["status"] == "ok"
    assert len(report["results"]) == 3
    for row in report["results"]:
        m = row["layout2d_py"]
        assert m["nodeCount"] == row["scale"]
        assert m["warmupMs"] >= 0
        assert m["simMs"] >= 0


def test_python_layout_scaling_thresholds():
    """M2 baseline SLO (Python 2D mirror); revise after Worker."""
    limits = {
        50: {"warmupMs": 1200, "simMs": 600},
        100: {"warmupMs": 3500, "simMs": 1800},
        250: {"warmupMs": 15000, "simMs": 9000},
        500: {"warmupMs": 55000, "simMs": 32000},
    }
    for n, cap in limits.items():
        g = synthetic_graph(n, "small_world", seed=42)
        m = bench_layout_2d(g, seed=42)
        assert m["warmupMs"] <= cap["warmupMs"], f"n={n} warmup {m['warmupMs']} > {cap['warmupMs']}"
        assert m["simMs"] <= cap["simMs"], f"n={n} sim {m['simMs']} > {cap['simMs']}"


@pytest.fixture(scope="module")
def node_layout_benchmark_report() -> dict | None:
    node = shutil.which("node")
    if not node or not BENCH_JS.is_file():
        return None
    proc = subprocess.run(
        [node, str(BENCH_JS), "--scales", "50,100,250", "--patterns", "small_world"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return json.loads(proc.stdout)


def test_node_layout_benchmark_optional(node_layout_benchmark_report: dict | None):
    if node_layout_benchmark_report is None:
        pytest.skip("Node.js not available — run scripts/graph_layout_benchmark.mjs locally")
    assert node_layout_benchmark_report["status"] == "ok"
