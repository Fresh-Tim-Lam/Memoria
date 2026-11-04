"""S9 检索评估（S9-10）：edition-pinned golden + 可执行指标 + 2× 确定性。

指标定义（本仓库实现口径，写死在此以免"口径漂移"）：

- ``recall@5``：每个 query 的 ``expected`` 集合在 top-5 中的比例，再对 query 取均值；
- ``NDCG@10``：``expected`` 按顺序给 graded relevance（第 1 个最高），DCG/IDCG 取 top-10；
- ``MRR``：第一个 ``expected`` 的排名倒数（缺失记 0），再取均值；
- ``coverage``：返回候选中有 anchor 的比例（kp/anchor 需 file+line；file 需 file）；
- ``sem_purity``：graph 分量中由 semantic 边贡献的比例（结构/引用边贡献必须为 0）；
- ``latency_ms``：单 query 中位数（**不进 metrics_sha**，环境相关）。

``metrics_sha = sha256(canonical(metrics 中除 latency 外的字段))``；2× 确定性要求
两次独立构建/检索的 index_sha 与 metrics_sha 都一致。阈值 provisional（S9-10/R8）。
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from memoria.graph.multilevel.datasource import DataSourceReader
from memoria.graph.multilevel.errors import GRAPH_TOOL_INPUT_INVALID, GraphError
from memoria.graph.retrieval.index import IndexStore, canonical_bytes, sha256_canonical
from memoria.graph.retrieval.retriever import Retriever, RetrievalRequest

GOLDEN_SCHEMA_VERSION = 1
GOLDEN_REL = Path("docs/design/multilevel-graph/golden/S9-golden-set.json")
#: provisional 阈值（S9-10；发布前需基线校准，校准写回 S9 修订）
GATE_RET = {
    "recall_at_5": 0.80,
    "ndcg_at_10": 0.70,
    "mrr": 0.70,
    "coverage": 0.90,
    "sem_purity": 1.0,
}

#: fixture KB（tests/graph/fixtures/kb-mini）对应的 golden 查询（edition 由脚本写入）
DEFAULT_GOLDEN_QUERIES = [
    {"id": "q01-lowpass", "query": "低通抽样定理", "query_type": "keyword",
     "expected": ["kp:ch1-lowpass"], "subset": "no_semantic"},
    {"id": "q02-bandpass", "query": "带通抽样", "query_type": "keyword",
     "expected": ["kp:ch1-bandpass"], "subset": "no_semantic"},
    {"id": "q03-uniform", "query": "均匀量化", "query_type": "keyword",
     "expected": ["kp:ch2-uniform"], "subset": "no_semantic"},
    {"id": "q04-nonuniform", "query": "非均匀量化", "query_type": "keyword",
     "expected": ["kp:ch2-nonuniform"], "subset": "no_semantic"},
    {"id": "q05-aliasing", "query": "混叠", "query_type": "keyword",
     "expected": ["kp:note-aliasing"], "subset": "no_semantic"},
    {"id": "q06-snr", "query": "信噪比", "query_type": "keyword",
     "expected": ["kp:note-snr"], "subset": "no_semantic"},
    {"id": "q07-sampling-hybrid", "query": "抽样定理", "query_type": "hybrid",
     "expected": ["kp:ch1-sampling", "kp:ch1-lowpass", "kp:ch1-bandpass"]},
    {"id": "q08-quant-graph", "query": "量化全章", "query_type": "graph",
     "expected": ["kp:ch2-whole", "kp:ch2-uniform"]},
]


@dataclass(frozen=True)
class EvalReport:
    ok: bool
    metrics: dict
    gates: dict
    detail: dict

    def to_dict(self) -> dict:
        return {"ok": self.ok, "metrics": self.metrics, "gates": self.gates,
                "detail": self.detail}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def golden_path() -> Path:
    return repo_root() / GOLDEN_REL


def load_golden(path: str | Path | None = None) -> dict:
    p = Path(path) if path else golden_path()
    if not p.is_file():
        raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"golden 不存在：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version") != GOLDEN_SCHEMA_VERSION:
        raise GraphError(GRAPH_TOOL_INPUT_INVALID,
                         f"golden schema_version 必须是 {GOLDEN_SCHEMA_VERSION}")
    for key in ("kb_id", "edition_sha", "queries"):
        if key not in data:
            raise GraphError(GRAPH_TOOL_INPUT_INVALID, f"golden 缺字段：{key}")
    if not data["queries"]:
        raise GraphError(GRAPH_TOOL_INPUT_INVALID, "golden.queries 不能为空")
    return data


def write_golden(kb_path: str | Path, out: str | Path | None = None) -> dict:
    """用给定 KB 的当前 edition 生成/刷新 golden（唯一路径由 S9a 冻结）。"""
    ds = DataSourceReader(kb_path).read()
    data = {
        "schema_version": GOLDEN_SCHEMA_VERSION,
        "kb_id": "kb-mini",
        "edition_sha": ds.canonical_id,
        "note": "edition-pinned golden；fixture KB = tests/graph/fixtures/kb-mini",
        "queries": copy.deepcopy(DEFAULT_GOLDEN_QUERIES),
    }
    p = Path(out) if out else golden_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")
    return {"path": str(p), "edition_sha": ds.canonical_id,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def _dcg(grades: list[int], k: int) -> float:
    total = 0.0
    for i, grade in enumerate(grades[:k], 1):
        total += (2 ** grade - 1) / math.log2(i + 1)
    return total


def _ndcg(ranked: list[str], expected: list[str], k: int = 10) -> float:
    if not expected:
        return 1.0
    grade_by_ref = {ref: len(expected) - i for i, ref in enumerate(expected)}
    gains = [grade_by_ref.get(ref, 0) for ref in ranked[:k]]
    ideal = sorted(grade_by_ref.values(), reverse=True)[:k]
    idcg = _dcg(ideal, k)
    return 1.0 if idcg == 0 else min(1.0, _dcg(gains, k) / idcg)


def _recall(ranked: list[str], expected: list[str], k: int = 5) -> float:
    if not expected:
        return 1.0
    hits = sum(1 for ref in expected if ref in ranked[:k])
    return hits / len(expected)


def _mrr(ranked: list[str], expected: list[str]) -> float:
    for i, ref in enumerate(ranked, 1):
        if ref in expected:
            return 1.0 / i
    return 0.0


def _evaluate_once(kb_path: str | Path, golden: dict) -> dict:
    ds = DataSourceReader(kb_path).read()
    if golden["edition_sha"] != ds.canonical_id:
        raise GraphError(
            GRAPH_TOOL_INPUT_INVALID,
            "golden edition 与当前 KB edition 不一致（edition-pinned；请重建索引/刷新 golden）",
            detail={"golden_edition": golden["edition_sha"], "edition_sha": ds.canonical_id,
                    "legacy_code": "GRAPH_EDITION_STALE"},
        )
    store = IndexStore(kb_path)
    index, built = store.load_or_build(ds)
    retriever = Retriever(kb_path, datasource=ds, index=index)
    per_query: list[dict] = []
    latencies: list[float] = []
    coverage_hits = 0
    coverage_total = 0
    sem_purities: list[float] = []
    for q in golden["queries"]:
        request = RetrievalRequest(
            kb_id=golden["kb_id"], query=q["query"], query_type=q.get("query_type", "hybrid"),
            filters=dict(q.get("filters") or {}),
            budget=dict(q.get("budget") or {}),
            expected_edition=golden["edition_sha"],
        )
        start = time.perf_counter()
        response = retriever.search(request)
        latencies.append((time.perf_counter() - start) * 1000.0)
        ranked = [c["candidate_ref"] for c in response["candidates"]]
        expected = list(q.get("expected") or [])
        coverage_hits += int(round(response["metrics"]["coverage_ratio"] *
                                   response["metrics"]["candidate_count"]))
        coverage_total += response["metrics"]["candidate_count"]
        sem_purities.append(float(response["metrics"]["sem_purity"]))
        per_query.append({
            "id": q["id"],
            "query_type": q.get("query_type", "hybrid"),
            "recall_at_5": _recall(ranked, expected),
            "ndcg_at_10": _ndcg(ranked, expected),
            "mrr": _mrr(ranked, expected),
            "top_refs": ranked[:10],
            "expected": expected,
            "truncated": response["truncated"],
            "degraded_reasons": response["degraded_reasons"],
        })
    recall = statistics.fmean(p["recall_at_5"] for p in per_query)
    ndcg = statistics.fmean(p["ndcg_at_10"] for p in per_query)
    mrr = statistics.fmean(p["mrr"] for p in per_query)
    coverage = (coverage_hits / coverage_total) if coverage_total else 1.0
    sem_purity = min(sem_purities) if sem_purities else 1.0
    metrics = {
        "n_queries": len(per_query),
        "recall_at_5": round(recall, 6),
        "ndcg_at_10": round(ndcg, 6),
        "mrr": round(mrr, 6),
        "coverage": round(coverage, 6),
        "sem_purity": round(sem_purity, 6),
        "latency_ms_median": round(statistics.median(latencies), 3),
        "index_sha": index.canonical_sha(),
        "edition_sha": index.edition,
        "index_built": built,
    }
    metrics_core = {k: v for k, v in metrics.items()
                    if k not in {"latency_ms_median", "index_built"}}
    return {
        "metrics": metrics,
        "metrics_sha": sha256_canonical(metrics_core),
        "per_query": per_query,
    }


def evaluate(kb_path: str | Path, golden: dict | None = None) -> EvalReport:
    """跑 2×（独立两次构建/检索）并判 GATE-RET。"""
    golden = golden if golden is not None else load_golden()
    first = _evaluate_once(kb_path, golden)
    second = _evaluate_once(kb_path, golden)
    deterministic = (first["metrics_sha"] == second["metrics_sha"]
                     and first["metrics"]["index_sha"] == second["metrics"]["index_sha"])
    metrics = first["metrics"]
    gates = {
        "recall_at_5": metrics["recall_at_5"] >= GATE_RET["recall_at_5"],
        "ndcg_at_10": metrics["ndcg_at_10"] >= GATE_RET["ndcg_at_10"],
        "mrr": metrics["mrr"] >= GATE_RET["mrr"],
        "coverage": metrics["coverage"] >= GATE_RET["coverage"],
        "sem_purity": abs(metrics["sem_purity"] - GATE_RET["sem_purity"]) <= 1e-9,
        "determinism_2x": deterministic,
    }
    ok = all(gates.values())
    return EvalReport(
        ok=ok,
        metrics=metrics,
        gates=gates,
        detail={
            "golden_sha256": sha256_canonical(golden),
            "golden_edition": golden["edition_sha"],
            "thresholds": dict(GATE_RET),
            "provisional": True,
            "per_query": first["per_query"],
            "metrics_sha": first["metrics_sha"],
            "determinism": {
                "2x": deterministic,
                "first_metrics_sha": first["metrics_sha"],
                "second_metrics_sha": second["metrics_sha"],
            },
        },
    )


def evaluate_isolated(kb_path: str | Path, golden: dict | None = None) -> EvalReport:
    """复制 KB 到临时目录再评估：避免在产品/用户库留下 cache 派生文件。"""
    src = Path(kb_path)
    with tempfile.TemporaryDirectory(prefix="memoria-eval-") as td:
        dst = Path(td) / "kb"
        shutil.copytree(src, dst)
        return evaluate(dst, golden)
