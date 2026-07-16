"""Metric unit tests."""

import pytest

from benchmark.metrics import mrr, ndcg_at_k, noise_at_k, precision_at_k, recall_at_k


def test_recall_at_k():
    ranked = ["a", "b", "c", "d"]
    rel = {"b", "d", "x"}
    assert recall_at_k(ranked, rel, 1) == 0.0
    assert recall_at_k(ranked, rel, 2) == 1 / 3
    assert recall_at_k(ranked, rel, 4) == 2 / 3


def test_precision_and_noise():
    ranked = ["a", "b", "c"]
    rel = {"b"}
    assert precision_at_k(ranked, rel, 3) == pytest.approx(1 / 3)
    assert noise_at_k(ranked, rel, 3) == pytest.approx(2 / 3)


def test_mrr():
    assert mrr(["x", "y", "target"], {"target"}) == 1 / 3
    assert mrr(["target", "y"], {"target"}) == 1.0
    assert mrr(["x", "y"], {"target"}) == 0.0


def test_ndcg_at_k():
    ranked = ["irrelevant", "good", "also-good"]
    rel = {"good", "also-good"}
    assert ndcg_at_k(ranked, rel, 3) < 1.0
    assert ndcg_at_k(["good", "also-good"], rel, 2) == 1.0
