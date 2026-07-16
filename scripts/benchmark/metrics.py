"""Standard IR metrics for KP-id ranked lists."""

from __future__ import annotations

import math


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = ranked[: max(0, k)]
    hits = sum(1 for doc_id in top if doc_id in relevant)
    return hits / len(relevant)


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = ranked[:k]
    if not top:
        return 0.0
    hits = sum(1 for doc_id in top if doc_id in relevant)
    return hits / len(top)


def noise_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Fraction of Top-k results that are not in qrels (irrelevant noise)."""
    return 1.0 - precision_at_k(ranked, relevant, k)


def mrr(ranked: list[str], relevant: set[str]) -> float:
    for i, doc_id in enumerate(ranked, start=1):
        if doc_id in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(
    ranked: list[str],
    relevant: set[str],
    k: int,
    *,
    graded: dict[str, float] | None = None,
) -> float:
    if k <= 0:
        return 0.0

    def gain(doc_id: str) -> float:
        if graded and doc_id in graded:
            return graded[doc_id]
        return 1.0 if doc_id in relevant else 0.0

    dcg = 0.0
    for i, doc_id in enumerate(ranked[:k], start=1):
        g = gain(doc_id)
        if g > 0:
            dcg += g / math.log2(i + 1)

    ideal_gains = sorted(
        [gain(d) for d in (graded or relevant)],
        reverse=True,
    )[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal_gains))
    if idcg <= 0:
        return 0.0
    return dcg / idcg


def aggregate_metric(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "count": 0.0}
    return {
        "mean": sum(values) / len(values),
        "count": float(len(values)),
    }
