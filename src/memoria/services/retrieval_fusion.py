"""SearchKernel v1.5c：多通道 RRF 融合与置信分档。"""

from __future__ import annotations

from typing import Any

RRF_K = 60

EXPLICIT_SOURCES = frozenset({
    "id-exact",
    "id-prefix",
    "id-fuzzy",
    "id-pinyin",
    "id-edit",
    "name-exact",
    "name-fuzzy",
    "name-pinyin",
    "name-edit",
    "tag-exact",
    "tag-fuzzy",
    "alias-explicit-exact",
    "alias-explicit-fuzzy",
    "kp-description",
    "file-description",
    "body-fuzzy",
})

IMPLICIT_SOURCES = frozenset({
    "auto-tag-exact",
    "auto-tag-fuzzy",
    "alias-exact",
    "alias-fuzzy",
    "summary-fuzzy",
    "key-phrase-fuzzy",
    "query-hit-fuzzy",
})

HIGH_SOURCES = frozenset({"id-exact", "name-exact"})
MEDIUM_SOURCES = frozenset({
    "id-prefix",
    "tag-exact",
    "alias-explicit-exact",
    "kp-description",
    "semantic-desc",
})

DEFAULT_CHANNEL_WEIGHTS: dict[str, float] = {
    "lexical_explicit": 1.0,
    "lexical_implicit": 0.9,
    "semantic": 1.0,
    "graph": 0.5,
}


def split_lexical_channels(results: list[dict]) -> tuple[list[dict], list[dict]]:
    """按 sources 将 Lexical 结果拆为显式 / 隐式通道（保持原排序）。"""
    explicit: list[dict] = []
    implicit: list[dict] = []
    for row in results:
        sources = set(row.get("sources") or [])
        if sources & EXPLICIT_SOURCES:
            explicit.append(row)
        if sources & IMPLICIT_SOURCES:
            implicit.append(row)
    return explicit, implicit


def reciprocal_rank_fusion(
    channels: dict[str, list[dict]],
    *,
    k: int = RRF_K,
    weights: dict[str, float] | None = None,
) -> list[tuple[str, float, dict[str, int], dict]]:
    """标准 RRF：返回 [(kp_id, rrf_score, channel_ranks), ...] 降序。"""
    w = {**DEFAULT_CHANNEL_WEIGHTS, **(weights or {})}
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    meta: dict[str, dict] = {}

    for channel, rows in channels.items():
        weight = float(w.get(channel, 1.0))
        if weight <= 0:
            continue
        for rank, row in enumerate(rows, start=1):
            kid = str(row.get("kp_id") or "")
            if not kid:
                continue
            scores[kid] = scores.get(kid, 0.0) + weight / (k + rank)
            ranks.setdefault(kid, {})[channel] = rank
            if kid not in meta:
                meta[kid] = dict(row)

    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return [(kid, score, ranks.get(kid, {}), meta[kid]) for kid, score in ordered]


def assign_confidence_tier(
    hit: dict,
    *,
    rrf_score: float | None = None,
    channel_ranks: dict[str, int] | None = None,
    max_rrf: float | None = None,
) -> tuple[str, float]:
    """返回 (tier, confidence 0–100)。"""
    sources = set(hit.get("sources") or [])
    channels = channel_ranks or {}
    channel_count = len(channels)

    if sources & HIGH_SOURCES:
        return "high", 95.0
    if channel_count >= 2:
        base = 88.0
        if rrf_score is not None and max_rrf and max_rrf > 0:
            base = max(base, 75.0 + (rrf_score / max_rrf) * 20.0)
        return "high", min(98.0, round(base, 1))

    lex = float(hit.get("lexical_score") or hit.get("score") or 0)
    sem = float(hit.get("semantic_score") or 0)

    if sources & MEDIUM_SOURCES or lex >= 70.0 or sem >= 62.0:
        conf = max(lex * 0.88, sem * 0.95, 55.0)
        return "medium", min(90.0, round(conf, 1))

    if sources & IMPLICIT_SOURCES and not (sources & EXPLICIT_SOURCES):
        conf = max(lex * 0.65, sem * 0.75, 35.0)
        return "low", min(55.0, round(conf, 1))

    conf = max(lex * 0.72, sem * 0.8, float(hit.get("score") or 0) * 0.65, 30.0)
    return "low", min(65.0, round(conf, 1))


def _merge_hit_fields(base: dict, other: dict) -> dict:
    row = dict(base)
    for key in ("lexical_score", "semantic_score", "name", "label", "file"):
        if row.get(key) is None and other.get(key) is not None:
            row[key] = other[key]
    src = list(row.get("sources") or [])
    for s in other.get("sources") or []:
        if s not in src:
            src.append(s)
    row["sources"] = src
    return row


def fuse_search_results(
    *,
    lexical_hits: list[dict],
    semantic_hits: list[dict] | None = None,
    graph_hits: list[dict] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Lexical 显式/隐式 + Semantic (+ Graph 占位) RRF 融合。"""
    explicit, implicit = split_lexical_channels(lexical_hits)
    channels: dict[str, list[dict]] = {
        "lexical_explicit": explicit,
        "lexical_implicit": implicit,
    }
    if semantic_hits:
        channels["semantic"] = semantic_hits
    if graph_hits:
        channels["graph"] = graph_hits

    fused = reciprocal_rank_fusion(channels)
    if not fused:
        return []

    max_rrf = max(s for _, s, _, _ in fused) if fused else 1.0
    by_id: dict[str, dict] = {}
    for row in lexical_hits:
        kid = str(row.get("kp_id") or "")
        if kid:
            by_id[kid] = dict(row)
    if semantic_hits:
        for row in semantic_hits:
            kid = str(row.get("kp_id") or "")
            if kid:
                by_id[kid] = _merge_hit_fields(by_id.get(kid, {}), row) if kid in by_id else dict(row)

    out: list[dict] = []
    for kid, rrf_score, channel_ranks, meta in fused[: max(1, int(limit))]:
        hit = _merge_hit_fields(by_id.get(kid, meta), meta)
        tier, confidence = assign_confidence_tier(
            hit,
            rrf_score=rrf_score,
            channel_ranks=channel_ranks,
            max_rrf=max_rrf,
        )
        display = round((rrf_score / max_rrf) * 100, 1) if max_rrf > 0 else round(rrf_score * 1000, 1)
        hit["rrf_score"] = round(rrf_score, 6)
        hit["channel_ranks"] = channel_ranks
        hit["tier"] = tier
        hit["confidence"] = confidence
        hit["score"] = display
        out.append(hit)
    return out


def annotate_lexical_results(results: list[dict]) -> list[dict]:
    """Lexical-only 模式：补 tier / confidence。"""
    out: list[dict] = []
    for row in results:
        hit = dict(row)
        if hit.get("lexical_score") is None and hit.get("score") is not None:
            hit["lexical_score"] = hit["score"]
        tier, confidence = assign_confidence_tier(hit)
        hit["tier"] = tier
        hit["confidence"] = confidence
        out.append(hit)
    return out
