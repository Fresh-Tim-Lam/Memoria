"""B6 / S9：检索索引 / candidate ranking / GATE-RET（task-353）。

覆盖：索引派生可重建/edition 绑定、candidate schema/score/budget、过滤错误、
无 semantic 降级、eval 可执行 + 2× 确定性 + metrics sha + provisional 阈值。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from memoria.graph.multilevel.datasource import DataSource, DataSourceReader  # noqa: E402
from memoria.graph.retrieval import (  # noqa: E402
    GATE_RET,
    IndexStore,
    RetrievalRequest,
    Retriever,
    build_index,
)
from memoria.graph.retrieval.eval import (  # noqa: E402
    evaluate,
    evaluate_isolated,
    golden_path,
    load_golden,
    write_golden,
)

KB_FIXTURE = REPO / "tests" / "graph" / "fixtures" / "kb-mini"
GOLDEN = REPO / "docs" / "design" / "multilevel-graph" / "golden" / "S9-golden-set.json"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    dst = tmp_path / "kb"
    shutil.copytree(KB_FIXTURE, dst)
    return dst


def _retriever(kb: Path) -> Retriever:
    ds = DataSourceReader(kb).read()
    index = build_index(ds)
    return Retriever(kb, datasource=ds, index=index)


# ── 索引 ────────────────────────────────────────────────────────────


def test_index_is_deterministic_and_derived(kb: Path):
    ds = DataSourceReader(kb).read()
    a = build_index(ds)
    b = build_index(ds)
    assert a.canonical_sha() == b.canonical_sha()
    kinds = {e["kind"] for e in a.entries}
    assert {"kp", "file", "anchor"} <= kinds
    assert a.metadata["rebuildable"] is True
    assert a.metadata["edition"] == ds.canonical_id
    assert a.metadata["model_id"] == "keyword-only"
    assert all(e["edge_id"].count("|") == 2 for e in a.semantic_edges)


def test_index_store_writes_under_cache_and_rebuilds(kb: Path):
    ds = DataSourceReader(kb).read()
    store = IndexStore(kb)
    index, built = store.load_or_build(ds)
    assert built is True
    path = kb / ".memoria" / "cache" / "graph" / "retrieval" / f"{ds.canonical_id}.json"
    assert path.is_file()
    loaded, built2 = store.load_or_build(ds)
    assert built2 is False
    assert loaded.canonical_sha() == index.canonical_sha()
    shutil.rmtree(store.root)
    rebuilt, built3 = store.load_or_build(ds)
    assert built3 is True
    assert rebuilt.edition == ds.canonical_id
    # 派生索引不是事实：删掉后 facts 仍在且 DataSource 可重读
    assert DataSourceReader(kb).read().canonical_id == ds.canonical_id


def test_index_missing_is_retrieval_unavailable(kb: Path):
    store = IndexStore(kb)
    from memoria.graph.multilevel.errors import GraphError
    with pytest.raises(GraphError) as exc:
        store.load("0" * 64)
    assert exc.value.code == "GRAPH_RETRIEVAL_UNAVAILABLE"


# ── candidate / ranking ─────────────────────────────────────────────


def test_candidate_schema_and_ranking(kb: Path):
    r = _retriever(kb)
    response = r.search(RetrievalRequest(kb_id="kb-mini", query="低通抽样定理",
                                        query_type="keyword"))
    assert response["edition_sha"] == r.index.edition
    assert response["candidates"]
    required = {"candidate_ref", "kind", "status", "data_state", "score",
                "components", "reason", "edition", "rank"}
    for cand in response["candidates"]:
        assert required <= set(cand)
        assert 0.0 <= cand["score"] <= 1.0
        assert cand["kind"] in {"kp", "cluster", "edge", "file", "anchor"}
        assert cand["status"] in {"ok", "degraded", "unknown"}
        assert cand["edition"] == r.index.edition
    ranks = [c["rank"] for c in response["candidates"]]
    assert ranks == list(range(1, len(ranks) + 1))
    assert response["candidates"][0]["candidate_ref"] == "kp:ch1-lowpass"
    assert response["metrics"]["sem_purity"] == 1.0


def test_budget_truncation_is_visible(kb: Path):
    r = _retriever(kb)
    by_candidates = r.search(RetrievalRequest(
        kb_id="kb-mini", query="量化", query_type="keyword",
        budget={"max_candidates": 1}))
    assert by_candidates["truncated"] is True
    assert by_candidates["truncation_reason"] == "candidate_budget"
    assert len(by_candidates["candidates"]) == 1
    by_tokens = r.search(RetrievalRequest(
        kb_id="kb-mini", query="量化", query_type="hybrid",
        budget={"max_tokens": 40}))
    assert by_tokens["truncated"] is True
    assert by_tokens["truncation_reason"] == "token_budget"


def test_filters_and_errors(kb: Path):
    r = _retriever(kb)
    with pytest.raises(Exception) as exc:
        r.search(RetrievalRequest(kb_id="kb-mini", query="x",
                                  filters={"kb_id": "other"}))
    assert "GRAPH_TOOL_INPUT_INVALID" in str(exc.value)
    with pytest.raises(Exception) as exc2:
        r.search(RetrievalRequest(kb_id="kb-mini", query="x",
                                  expected_edition="0" * 64))
    assert "GRAPH_ANCHOR_STALE" in str(exc2.value)
    with pytest.raises(Exception) as exc3:
        r.search(RetrievalRequest(kb_id="kb-mini", query="x", query_type="bogus"))
    assert "GRAPH_TOOL_INPUT_INVALID" in str(exc3.value)
    with pytest.raises(Exception) as exc4:
        r.search(RetrievalRequest(kb_id="kb-mini", query="x", dimension_id="A"))
    assert "GRAPH_TOOL_INPUT_INVALID" in str(exc4.value)


def test_no_semantic_degrades_to_kp_only(kb: Path):
    ds = DataSourceReader(kb).read()
    no_sem = replace(ds, edges=tuple(
        e for e in ds.edges if str(e.get("contain_kind")) != "semantic"))
    index = build_index(no_sem)
    r = Retriever(kb, datasource=no_sem, index=index)
    response = r.search(RetrievalRequest(kb_id="kb-mini", query="抽样定理",
                                        query_type="hybrid"))
    assert response["data_state"] == "empty_nosemantic"
    assert any("no_semantic_edges" in x for x in response["degraded_reasons"])
    assert all(c["kind"] == "kp" or c["kind"] == "anchor" or c["kind"] == "file"
               for c in response["candidates"])
    assert response["metrics"]["sem_purity"] == 1.0


# ── GATE-RET / golden ───────────────────────────────────────────────


def test_golden_is_edition_pinned_and_script_passes(kb: Path, tmp_path: Path):
    golden = load_golden(GOLDEN)
    ds = DataSourceReader(kb).read()
    assert golden["edition_sha"] == ds.canonical_id
    assert golden_path().resolve() == GOLDEN.resolve()
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    for out in (out1, out2):
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify" / "eval-retrieval.py"),
             "--kb", str(kb), "--golden", str(GOLDEN), "--out", str(out)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert r.returncode == 0, r.stdout + r.stderr
    a = json.loads(out1.read_text(encoding="utf-8"))
    b = json.loads(out2.read_text(encoding="utf-8"))
    assert a["ok"] is True and a["gate"] == "GATE-RET"
    assert a["metrics_sha"] == b["metrics_sha"]
    assert a["determinism"]["2x"] is True
    for key, floor in (("recall_at_5", GATE_RET["recall_at_5"]),
                       ("ndcg_at_10", GATE_RET["ndcg_at_10"]),
                       ("mrr", GATE_RET["mrr"]),
                       ("coverage", GATE_RET["coverage"])):
        assert a["metrics"][key] >= floor, key
    assert a["metrics"]["sem_purity"] == GATE_RET["sem_purity"]
    assert a["golden_sha256"]
    assert set(a["gates"]) == {"recall_at_5", "ndcg_at_10", "mrr", "coverage",
                               "sem_purity", "determinism_2x"}


def test_eval_in_process_and_write_golden(kb: Path):
    report = evaluate_isolated(kb)
    assert report.ok is True
    assert report.detail["determinism"]["2x"] is True
    tmp_golden = kb.parent / "golden-copy.json"
    res = write_golden(kb, out=tmp_golden)
    assert Path(res["path"]) == tmp_golden
    assert tmp_golden.is_file()
    assert res["edition_sha"] == DataSourceReader(kb).read().canonical_id
