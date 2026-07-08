"""2D force layout benchmark mirror (M2 stress tests; matches JS MemoriaGraphLayout2D)."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LayoutBenchOpts:
    link_distance: float = 108.0
    link_strength: float = 0.28
    repulsion: float = 5200.0
    center_strength: float = 0.006
    velocity_decay: float = 0.8
    alpha_min: float = 0.012
    warmup_ticks: int = 160
    spread_factor: float = 0.42
    group_spacing: float = 260.0
    sim_frames: int = 60
    ticks_per_frame: int = 6


@dataclass
class SimNode:
    id: str
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    group_id: str | None = None
    group_ox: float | None = None
    group_oy: float | None = None


@dataclass
class SimLink:
    source_index: int
    target_index: int
    strength_scale: float = 1.0


def _spread_radius(n: int, spread_factor: float) -> float:
    return max(72.0, math.sqrt(max(1, n)) * 140.0 * spread_factor)


def _initial_positions_2d(node_ids: list[str], radius: float, rng: random.Random) -> list[SimNode]:
    n = len(node_ids)
    out: list[SimNode] = []
    for i, nid in enumerate(node_ids):
        angle = (2 * math.pi * i) / max(1, n) + (rng.random() - 0.5) * 0.2
        r = radius * (0.55 + rng.random() * 0.45)
        out.append(SimNode(id=nid, x=math.cos(angle) * r, y=math.sin(angle) * r))
    return out


def _build_sim(graph: dict[str, Any], opts: LayoutBenchOpts, rng: random.Random) -> tuple[list[SimNode], list[SimLink]]:
    ids = [n["id"] for n in graph["nodes"]]
    radius = _spread_radius(len(ids), opts.spread_factor)
    nodes = _initial_positions_2d(ids, radius, rng)
    idx = {n.id: i for i, n in enumerate(nodes)}
    links: list[SimLink] = []
    for link in graph.get("links") or []:
        si = idx.get(link["source"])
        ti = idx.get(link["target"])
        if si is None or ti is None:
            continue
        rel = float(link.get("relevance", 0.5))
        strength = 0.55 + rel * 0.9 if math.isfinite(rel) else 1.0
        links.append(SimLink(source_index=si, target_index=ti, strength_scale=strength))
    return nodes, links


def tick(
    nodes: list[SimNode],
    links: list[SimLink],
    *,
    alpha: float,
    opts: LayoutBenchOpts,
    drag_id: str | None = None,
) -> float:
    n = len(nodes)
    rep_base = opts.repulsion * (1 + math.sqrt(n) * 0.15)
    rep = rep_base * alpha
    center = opts.center_strength * alpha

    for node in nodes:
        ax = node.group_ox if node.group_ox is not None else 0.0
        ay = node.group_oy if node.group_oy is not None else 0.0
        node.vx += (ax - node.x) * center
        node.vy += (ay - node.y) * center

    for i in range(n):
        for j in range(i + 1, n):
            a, b = nodes[i], nodes[j]
            if a.group_id and b.group_id and a.group_id != b.group_id:
                continue
            dx = b.x - a.x
            dy = b.y - a.y
            dist2 = dx * dx + dy * dy
            if dist2 < 1:
                dx = (random.random() - 0.5) * 0.01
                dy = (random.random() - 0.5) * 0.01
                dist2 = dx * dx + dy * dy
            dist = math.sqrt(dist2)
            f = rep / dist2
            fx = (dx / dist) * f
            fy = (dy / dist) * f
            a.vx -= fx
            a.vy -= fy
            b.vx += fx
            b.vy += fy

    for link in links:
        s = nodes[link.source_index]
        t = nodes[link.target_index]
        dx = t.x - s.x
        dy = t.y - s.y
        dist = math.sqrt(dx * dx + dy * dy) or 0.01
        strength = opts.link_strength * alpha * link.strength_scale
        force = ((dist - opts.link_distance) / dist) * strength
        fx = (dx / dist) * force
        fy = (dy / dist) * force
        s.vx += fx
        s.vy += fy
        t.vx -= fx
        t.vy -= fy

    for node in nodes:
        if drag_id and node.id == drag_id:
            continue
        node.vx *= opts.velocity_decay
        node.vy *= opts.velocity_decay
        node.x += node.vx
        node.y += node.vy

    return alpha + (opts.alpha_min - alpha) * 0.045


def bench_layout_2d(graph: dict[str, Any], opts: LayoutBenchOpts | None = None, *, seed: int = 42) -> dict[str, Any]:
    """Warmup + simulated frames; returns timing in milliseconds."""
    o = opts or LayoutBenchOpts()
    rng = random.Random(seed)
    nodes, links = _build_sim(graph, o, rng)

    t0 = time.perf_counter()
    alpha = 1.0
    for i in range(o.warmup_ticks):
        alpha = tick(nodes, links, alpha=1.0 - i / o.warmup_ticks, opts=o)
    warmup_ms = (time.perf_counter() - t0) * 1000.0

    alpha = 0.12
    t1 = time.perf_counter()
    for _ in range(o.sim_frames):
        for _ in range(o.ticks_per_frame):
            alpha = tick(nodes, links, alpha=alpha, opts=o)
    sim_ms = (time.perf_counter() - t1) * 1000.0

    return {
        "warmupMs": round(warmup_ms, 2),
        "simMs": round(sim_ms, 2),
        "nodeCount": len(nodes),
        "linkCount": len(links),
    }


def run_benchmark_suite(
    scales: tuple[int, ...] = (50, 100, 250, 500),
    patterns: tuple[str, ...] = ("small_world", "partitioned"),
    *,
    seed: int = 42,
) -> dict[str, Any]:
    from memoria.graph.synthetic import synthetic_graph

    rows = []
    for pattern in patterns:
        for n in scales:
            graph = synthetic_graph(n, pattern, seed=seed)
            rows.append(
                {
                    "pattern": pattern,
                    "scale": n,
                    "layout2d_py": bench_layout_2d(graph, seed=seed + n),
                }
            )
    return {
        "status": "ok",
        "engine": "memoria-layout-bench-py",
        "simFrames": LayoutBenchOpts().sim_frames,
        "ticksPerFrame": LayoutBenchOpts().ticks_per_frame,
        "results": rows,
    }
