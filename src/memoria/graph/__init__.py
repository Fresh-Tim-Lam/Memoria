"""图谱数据层（M2 前置）。"""

from memoria.graph.collector import collect_graph_data
from memoria.graph.layout_bench import bench_layout_2d, run_benchmark_suite
from memoria.graph.synthetic import synthetic_graph
from memoria.graph.edge_types import (
    EDGE_CONTAIN,
    EDGE_EXTEND,
    EDGE_REFERENCE,
    EDGE_TYPES,
    default_relevance,
    normalize_edge_type,
    normalize_wikilink_edge_hint,
)

__all__ = [
    "EDGE_CONTAIN",
    "EDGE_EXTEND",
    "EDGE_REFERENCE",
    "EDGE_TYPES",
    "collect_graph_data",
    "default_relevance",
    "normalize_edge_type",
    "normalize_wikilink_edge_hint",
]
