"""S9 检索：candidate/ranking（S9-1..S9-9）。

只产**候选与排序**，不写图谱/不改事实/不做 presence；召回/排序语义：
- ``keyword``：派生索引上的词法分数（CJK 字符 + ASCII 词）；
- ``graph``：单 seed + **semantic 1 跳**（结构/引用边贡献 = 0，S9-4/S9-5）；
- ``hybrid``：keyword + graph 加权（embedding off ⇒ vector 分量=0，权重按可用分量归一；
  ``0.4/0.4/0.2`` 是 S9 冻结的**假设**权重，这里记录 components 便于校准）；
- ``vector``：v1 embedding 默认关闭 ⇒ 可见降级为 keyword-only（不伪造向量分）。

无 semantic 边 ⇒ KP-only + ``degraded_reason="no_semantic_edges"``（S9-4）；
索引缺失/edition 不符 ⇒ ``GRAPH_RETRIEVAL_UNAVAILABLE`` / 版本错误码（S9-9）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from memoria.graph.multilevel.datasource import DataSource, DataSourceReader
from memoria.graph.multilevel.errors import (
    GRAPH_ANCHOR_STALE,
    GRAPH_INTERNAL,
    GRAPH_RETRIEVAL_UNAVAILABLE,
    GRAPH_TOOL_INPUT_INVALID,
    GraphError,
)
from memoria.graph.retrieval.index import (
    RetrievalIndex,
    build_index,
    estimate_candidate_tokens,
    sha256_canonical,
)

QUERY_TYPES: tuple[str, ...] = ("keyword", "vector", "graph", "hybrid")
CANDIDATE_KINDS: tuple[str, ...] = ("kp", "cluster", "edge", "file", "anchor")
CANDIDATE_STATUSES: tuple[str, ...] = ("ok", "degraded", "unknown")
SUPPORTED_DIMENSIONS: tuple[str, ...] = ("H",)  # S9 v1：默认 H；A 维度需 S1 registry（B6 不做）
DEFAULT_BUDGET = {"max_candidates": 10, "max_tokens": 4000, "max_latency_ms": 500}
#: S9 冻结的 hybrid 假设权重（keyword/vector/graph）；embedding off 时按可用分量归一。
HYBRID_WEIGHTS = {"keyword": 0.4, "vector": 0.4, "graph": 0.2}
TIE_BREAK_ORDER = {kind: i for i, kind in enumerate(CANDIDATE_KINDS)}

_CHAR_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return _CHAR_RE.findall(str(text or "").lower())


@dataclass(frozen=True)
class RetrievalRequest:
    kb_id: str
    query: str
    query_type: str = "hybrid"
    dimension_id: str = "H"
    filters: Mapping[str, object] = field(default_factory=dict)
    budget: Mapping[str, int] = field(default_factory=dict)
    expected_edition: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kb_id, str) or not self.kb_id:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, "request.kb_id 必须非空")
        if not isinstance(self.query, str) or not self.query.strip():
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, "request.query 必须非空")
        if self.query_type not in QUERY_TYPES:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                             f"query_type 必须是 {QUERY_TYPES} 之一")
        if not isinstance(self.dimension_id, str) or not self.dimension_id:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, "dimension_id 必须非空")
        if not isinstance(self.filters, Mapping):
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, "filters 必须是对象")
        for key in self.budget:
            if key not in DEFAULT_BUDGET:
                raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"budget 不支持的键：{key}")
        for key, value in self.budget.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"budget.{key} 必须是 ≥1 整数")
        fkb = self.filters.get("kb_id")
        if fkb is not None and str(fkb) != self.kb_id:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                             "filters.kb_id 与 request.kb_id 不一致（S9-2）")
        kind = self.filters.get("kind")
        if kind is not None and kind not in CANDIDATE_KINDS:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                             f"filters.kind 必须是 {CANDIDATE_KINDS} 之一")

    def budget_dict(self) -> dict[str, int]:
        out = dict(DEFAULT_BUDGET)
        out.update({k: int(v) for k, v in self.budget.items()})
        return out


class Retriever:
    """S9 检索器（**纯只读**：不写 KB；索引由 IndexStore 负责）。"""

    def __init__(
        self,
        kb_path: str | Path,
        *,
        datasource: DataSource | None = None,
        index: RetrievalIndex | None = None,
        run=None,
    ) -> None:
        self.kb_path = Path(kb_path)
        self._datasource = datasource
        self._index = index
        self.run = run

    # -- 懒加载 ------------------------------------------------------
    @property
    def datasource(self) -> DataSource:
        if self._datasource is None:
            self._datasource = DataSourceReader(self.kb_path).read()
        return self._datasource

    @property
    def index(self) -> RetrievalIndex:
        if self._index is None:
            self._index = build_index(self.datasource)
        return self._index

    # -- 分数 --------------------------------------------------------
    @staticmethod
    def _field_hits(entry: Mapping, terms: Sequence[str]) -> int:
        text = str(entry.get("text") or "")
        return sum(1 for term in terms if term in text)

    def keyword_score(self, entry: Mapping, terms: Sequence[str], query: str = "") -> float:
        if not terms:
            return 0.0
        name = tokenize(entry.get("name") or "")
        desc = tokenize(entry.get("description") or "")
        text = tokenize(entry.get("text") or "")
        file = tokenize(entry.get("file") or "")
        weight = 3.0 * sum(1 for t in terms if t in name)
        weight += 2.0 * sum(1 for t in terms if t in desc)
        weight += 1.0 * sum(1 for t in terms if t in text)
        weight += 0.5 * sum(1 for t in terms if t in file)
        # 精确词面加成：中文单字匹配会把「非均匀量化」与「均匀量化」打平；
        # 用「查询串在名称中的占比」消除前缀差异（确定性、无模型）。
        q_raw = str(query or "").strip().lower()
        name_raw = str(entry.get("name") or "").lower()
        if q_raw and q_raw in name_raw:
            weight += 2.0 * (len(q_raw) / max(1, len(name_raw)))
        max_weight = 3.0 * len(terms) + 2.0 * len(terms) + 1.0 * len(terms) + 0.5 * len(terms)
        return min(1.0, weight / max_weight) if max_weight else 0.0

    def _graph_neighbors(self) -> dict[str, list[dict]]:
        adj: dict[str, list[dict]] = {}
        for edge in self.index.semantic_edges:
            adj.setdefault(edge["source"], []).append(edge)
            adj.setdefault(edge["target"], []).append(
                {"edge_id": edge["edge_id"], "type": edge["type"],
                 "source": edge["target"], "target": edge["source"],
                 "relation_class": "semantic", "reverse": True})
        for key in adj:
            adj[key].sort(key=lambda e: e["edge_id"])
        return adj

    def _candidate_entries(self) -> list[dict]:
        entries = [dict(e) for e in self.index.entries]
        entries.sort(key=lambda e: e["candidate_ref"])
        return entries

    # -- 主入口 ------------------------------------------------------
    def search(self, request: RetrievalRequest) -> dict:
        if request.dimension_id not in SUPPORTED_DIMENSIONS:
            raise GraphError(
                GRAPH_TOOL_INPUT_INVALID,
                f"v1 只支持 dimension_id={SUPPORTED_DIMENSIONS[0]}（A 维度需 S1 registry，B6 未做）",
                detail={"dimension_id": request.dimension_id},
            )
        current = self.datasource.canonical_id
        if request.expected_edition and request.expected_edition != current:
            raise GraphError(
                GRAPH_ANCHOR_STALE,
                "expected_edition 与当前 edition 不匹配（索引需重建）",
                detail={"expected_edition": request.expected_edition,
                        "edition_sha": current, "legacy_code": "GRAPH_EDITION_STALE"},
            )
        budget = request.budget_dict()
        filters = dict(request.filters)
        terms = tokenize(request.query)
        no_semantic = not self.index.semantic_edges
        degraded_reasons: list[str] = []
        if request.query_type == "vector":
            degraded_reasons.append("embedding_disabled:vector→keyword")
        if no_semantic and request.query_type in ("graph", "hybrid"):
            degraded_reasons.append("no_semantic_edges:graph→keyword")
        data_state = "empty_nosemantic" if no_semantic else "ok"

        entries = self._candidate_entries()
        by_ref = {e["candidate_ref"]: e for e in entries}
        keyword = {e["candidate_ref"]: self.keyword_score(e, terms, request.query)
                   for e in entries}

        graph_scores: dict[str, float] = {}
        graph_reason: dict[str, str] = {}
        if request.query_type in ("graph", "hybrid") and not no_semantic:
            seeds = [ref for ref, score in keyword.items() if score > 0.0]
            seeds.sort(key=lambda ref: (-keyword[ref], ref))
            seed_ref = seeds[0] if seeds else None
            if seed_ref:
                seed = by_ref[seed_ref]
                seed_id = str(seed.get("kp_id") or "")
                for edge in self._graph_neighbors().get(seed_id, ()):
                    target = edge["target"]
                    target_ref = f"kp:{target}"
                    if target_ref not in by_ref:
                        continue
                    graph_scores[target_ref] = max(graph_scores.get(target_ref, 0.0),
                                                   min(1.0, keyword[seed_ref] * 0.9))
                    graph_reason.setdefault(target_ref, f"semantic_1hop:{edge['edge_id']}")
                graph_scores[seed_ref] = max(graph_scores.get(seed_ref, 0.0), 1.0)
                graph_reason.setdefault(seed_ref, "graph_seed")

        candidates: list[dict] = []
        for entry in entries:
            ref = entry["candidate_ref"]
            kw = keyword.get(ref, 0.0)
            gs = graph_scores.get(ref, 0.0)
            if request.query_type == "keyword":
                score = kw
            elif request.query_type == "graph":
                score = gs
            elif request.query_type == "vector":
                score = kw
            else:  # hybrid
                score = (HYBRID_WEIGHTS["keyword"] * kw + HYBRID_WEIGHTS["graph"] * gs) / (
                    HYBRID_WEIGHTS["keyword"] + HYBRID_WEIGHTS["graph"])
            if score <= 0.0:
                continue
            kind = str(entry["kind"])
            if filters.get("kind") and kind != filters["kind"]:
                continue
            if filters.get("file") and str(filters["file"]) != entry.get("file"):
                continue
            components = {"keyword": round(kw, 6), "vector": 0.0, "graph": round(gs, 6)}
            reason = graph_reason.get(ref) or (
                "keyword_match" if kw > 0 else "graph_match")
            candidates.append({
                "candidate_ref": ref,
                "kind": kind,
                "status": "degraded" if (request.query_type == "vector" or
                                         (no_semantic and request.query_type in ("graph", "hybrid")))
                else "ok",
                "data_state": data_state,
                "score": round(float(score), 6),
                "components": components,
                "reason": reason,
                "edition": self.index.edition,
                "rank": 0,
            })
        candidates.sort(key=lambda c: (
            -c["score"], TIE_BREAK_ORDER.get(c["kind"], 9), c["candidate_ref"]))
        # 预算：max_candidates + max_tokens（显式 truncated，不静默）
        truncated = False
        truncation_reason = None
        kept: list[dict] = []
        used_tokens = 0
        for cand in candidates:
            if len(kept) >= budget["max_candidates"]:
                truncated = True
                truncation_reason = "candidate_budget" if not truncation_reason else truncation_reason
                break
            cost = estimate_candidate_tokens(cand)
            if used_tokens + cost > budget["max_tokens"]:
                truncated = True
                truncation_reason = "token_budget"
                break
            used_tokens += cost
            kept.append(cand)
        for rank, cand in enumerate(kept, 1):
            cand["rank"] = rank
        coverage_ratio = (
            sum(1 for c in kept if self._anchored(c, by_ref)) / len(kept) if kept else 1.0
        )
        sem_mass = sum(c["components"]["graph"] for c in kept)
        sem_purity = 1.0  # graph 分量只来自 semantic_edges（无结构/引用边参与）
        return {
            "kb_id": request.kb_id,
            "query": request.query,
            "query_type": request.query_type,
            "dimension_id": request.dimension_id,
            "edition_sha": self.index.edition,
            "data_state": data_state,
            "candidates": kept,
            "truncated": truncated,
            "truncation_reason": truncation_reason,
            "budget": budget,
            "weights": dict(HYBRID_WEIGHTS) if request.query_type == "hybrid" else {},
            "degraded_reasons": degraded_reasons,
            "metrics": {
                "candidate_count": len(kept),
                "tokens_est": used_tokens,
                "coverage_ratio": round(coverage_ratio, 6),
                "sem_purity": sem_purity,
                "graph_score_mass": round(sem_mass, 6),
            },
        }

    @staticmethod
    def _anchored(candidate: Mapping, by_ref: Mapping[str, Mapping]) -> bool:
        ref = str(candidate.get("candidate_ref"))
        if ref.startswith("file:"):
            return True
        entry = by_ref.get(ref) or {}
        return bool(entry.get("file"))
