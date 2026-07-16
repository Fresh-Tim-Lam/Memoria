"""Retrieval benchmark on tiny SciFact-style fixture (no network)."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

import pytest

from benchmark.eval import evaluate_retrieval, load_qrels, load_queries
from memoria.storage.manifest import rebuild_manifest

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "benchmark_retrieval_tiny"
EVAL = FIXTURE / "eval"


@pytest.fixture(scope="module")
def gold_kb(tmp_path_factory) -> Path:
    kb = tmp_path_factory.mktemp("kb_gold")
    shutil.copytree(FIXTURE, kb, dirs_exist_ok=True)
    rebuild_manifest(str(kb))
    return kb


@pytest.fixture(scope="module")
def skeleton_kb(gold_kb, tmp_path_factory) -> Path:
    kb = tmp_path_factory.mktemp("kb_skeleton")
    shutil.copytree(gold_kb, kb, dirs_exist_ok=True)
    sidecar_dir = kb / ".memoria" / "sidecars" / "corpus"
    for sc in sidecar_dir.glob("*.memoria.yaml"):
        data = yaml.safe_load(sc.read_text(encoding="utf-8"))
        for kp in data.get("knowledge_points") or []:
            kp["name"] = kp["id"]
            kp.pop("tags", None)
            kp.pop("description", None)
        sc.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    rebuild_manifest(str(kb))
    return kb


def test_tiny_benchmark_gold_recall(gold_kb: Path):
    queries = load_queries(EVAL / "queries.json")
    qrels = load_qrels(EVAL / "qrels.json")
    report = evaluate_retrieval(
        kb_path=str(gold_kb),
        queries=queries,
        qrels=qrels,
        k_values=(1, 5),
        modes="lexical",
        limit=10,
    )
    summary = report["summary"]
    assert summary["query_count"] == 3
    assert summary["recall@5"]["mean"] >= 0.66
    assert summary["mrr"]["mean"] >= 0.5


def test_skeleton_profile_hurts_or_equal(skeleton_kb: Path, gold_kb: Path):
    """Poor KP naming/metadata should not beat gold (quantifies characterization pain)."""
    queries = load_queries(EVAL / "queries.json")
    qrels = load_qrels(EVAL / "qrels.json")
    gold = evaluate_retrieval(
        kb_path=str(gold_kb),
        queries=queries,
        qrels=qrels,
        k_values=(5,),
        modes="lexical",
        rebuild_index=False,
    )
    skel = evaluate_retrieval(
        kb_path=str(skeleton_kb),
        queries=queries,
        qrels=qrels,
        k_values=(5,),
        modes="lexical",
    )
    assert skel["summary"]["recall@5"]["mean"] <= gold["summary"]["recall@5"]["mean"] + 0.01
    assert skel["summary"]["noise@5"]["mean"] >= gold["summary"]["noise@5"]["mean"] - 0.01
