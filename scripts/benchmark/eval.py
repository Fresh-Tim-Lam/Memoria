"""Run SearchKernel against qrels and aggregate IR metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ._bootstrap import ROOT  # noqa: F401 — ensures src on path
from .metrics import (
    aggregate_metric,
    mrr,
    ndcg_at_k,
    noise_at_k,
    precision_at_k,
    recall_at_k,
)
from memoria.services.lexical_index import rebuild_lexical_index
from memoria.services.search_kernel import search

SearchFn = Callable[..., dict]


def load_queries(path: str | Path) -> list[dict[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [{"query_id": qid, "text": text} for qid, text in data.items()]
    return list(data)


def load_qrels(path: str | Path) -> dict[str, set[str]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for qid, rel in raw.items():
        if isinstance(rel, dict):
            out[qid] = {d for d, s in rel.items() if float(s) > 0}
        else:
            out[qid] = {str(x) for x in rel}
    return out


def evaluate_retrieval(
    *,
    kb_path: str,
    queries: list[dict[str, str]],
    qrels: dict[str, set[str]],
    k_values: tuple[int, ...] = (1, 5, 10),
    modes: str = "lexical",
    limit: int = 20,
    rebuild_index: bool = True,
    search_fn: SearchFn | None = None,
) -> dict[str, Any]:
    if rebuild_index:
        rebuild_lexical_index(kb_path)
    _search = search_fn or search

    per_query: list[dict[str, Any]] = []
    recalls = {k: [] for k in k_values}
    precisions = {k: [] for k in k_values}
    noises = {k: [] for k in k_values}
    ndcgs = {k: [] for k in k_values}
    mrrs: list[float] = []

    for item in queries:
        qid = item["query_id"]
        text = item["text"]
        relevant = qrels.get(qid, set())
        if not relevant:
            continue

        payload = _search(text, kb_path=kb_path, modes=modes, limit=limit)
        ranked = [r["kp_id"] for r in payload.get("results") or []]

        row: dict[str, Any] = {
            "query_id": qid,
            "query": text,
            "relevant": sorted(relevant),
            "ranked": ranked,
            "metrics": {},
        }
        for k in k_values:
            row["metrics"][f"recall@{k}"] = recall_at_k(ranked, relevant, k)
            row["metrics"][f"precision@{k}"] = precision_at_k(ranked, relevant, k)
            row["metrics"][f"noise@{k}"] = noise_at_k(ranked, relevant, k)
            row["metrics"][f"ndcg@{k}"] = ndcg_at_k(ranked, relevant, k)
            recalls[k].append(row["metrics"][f"recall@{k}"])
            precisions[k].append(row["metrics"][f"precision@{k}"])
            noises[k].append(row["metrics"][f"noise@{k}"])
            ndcgs[k].append(row["metrics"][f"ndcg@{k}"])
        row["metrics"]["mrr"] = mrr(ranked, relevant)
        mrrs.append(row["metrics"]["mrr"])
        per_query.append(row)

    summary: dict[str, Any] = {
        "kb_path": kb_path,
        "modes": modes,
        "query_count": len(per_query),
        "mrr": aggregate_metric(mrrs),
    }
    for k in k_values:
        summary[f"recall@{k}"] = aggregate_metric(recalls[k])
        summary[f"precision@{k}"] = aggregate_metric(precisions[k])
        summary[f"noise@{k}"] = aggregate_metric(noises[k])
        summary[f"ndcg@{k}"] = aggregate_metric(ndcgs[k])

    return {"summary": summary, "queries": per_query}
