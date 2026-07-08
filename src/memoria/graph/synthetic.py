"""Synthetic graph payloads for layout stress tests (M2)."""

from __future__ import annotations

import random
from typing import Any


def expand_links(edges: list[dict]) -> list[dict]:
    links: list[dict] = []
    for e in edges:
        source = (e.get("source_id") or "").strip()
        if not source:
            continue
        for target in e.get("targets") or []:
            tid = str(target or "").strip()
            if not tid or tid == source:
                continue
            links.append(
                {
                    "source": source,
                    "target": tid,
                    "type": e.get("type") or "reference",
                    "relevance": float(e.get("relevance", 0.5)),
                }
            )
    return links


def _node(i: int, *, file_idx: int = 0) -> dict:
    kid = f"kp-{i}"
    return {
        "id": kid,
        "name": f"知识点 {i}",
        "label": f"知识点 {i}",
        "description": f"synthetic node {i}",
        "file": f"synthetic/file-{file_idx % 8}.md",
        "kp_id": kid,
        "range_ok": True,
        "start_line": 1,
        "end_line": 3,
    }


def _edge(source_id: str, targets: list[str], *, etype: str = "reference") -> dict:
    return {
        "type": etype,
        "source_id": source_id,
        "targets": targets,
        "relevance": 0.65,
    }


def synthetic_graph(
    n_nodes: int,
    pattern: str = "small_world",
    *,
    avg_degree: int = 4,
    n_groups: int = 5,
    seed: int = 0,
) -> dict[str, Any]:
    """Build { nodes, edges, links } compatible with GraphEngine / layout JS."""
    n = max(1, int(n_nodes))
    rng = random.Random(seed)
    nodes = [_node(i, file_idx=i % max(1, n_groups)) for i in range(n)]
    node_ids = [nd["id"] for nd in nodes]
    edges: list[dict] = []

    if pattern == "chain":
        for i in range(n - 1):
            edges.append(_edge(node_ids[i], [node_ids[i + 1]]))
    elif pattern == "star":
        hub = node_ids[0]
        for i in range(1, n):
            edges.append(_edge(hub, [node_ids[i]]))
    elif pattern == "partitioned":
        groups = max(2, min(n_groups, n))
        size = max(1, n // groups)
        for g in range(groups):
            start = g * size
            end = min(n, start + size)
            if start >= end:
                continue
            local = node_ids[start:end]
            for i in range(len(local) - 1):
                edges.append(_edge(local[i], [local[i + 1]]))
            if len(local) > 2:
                edges.append(_edge(local[0], [local[-1]], etype="extend"))
    else:
        # small_world: random sparse directed edges
        target_count = max(n - 1, (n * avg_degree) // 2)
        seen: set[tuple[str, str]] = set()
        attempts = 0
        while len(seen) < target_count and attempts < target_count * 20:
            attempts += 1
            s = rng.randrange(n)
            t = rng.randrange(n)
            if s == t:
                continue
            key = (node_ids[s], node_ids[t])
            if key in seen:
                continue
            seen.add(key)
            edges.append(_edge(node_ids[s], [node_ids[t]]))

    links = expand_links(edges)
    return {"nodes": nodes, "edges": edges, "links": links}


BENCHMARK_SCALES = (50, 100, 250, 500, 1000)
BENCHMARK_PATTERNS = ("small_world", "partitioned", "star")
