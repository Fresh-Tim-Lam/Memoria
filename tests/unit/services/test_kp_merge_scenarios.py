"""相似知识点合并 — 多场景夹具回归。"""

from pathlib import Path

import pytest

from memoria.services.lexical_index import rebuild_lexical_index
from memoria.services.search_kernel import suggest_kp_merge

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "m4_merge_kb"


@pytest.fixture(scope="module")
def merge_kb():
    kb = str(FIXTURE)
    rebuild_lexical_index(kb)
    return kb


def _suggest_ids(kb: str, anchor_id: str) -> set[str]:
    res = suggest_kp_merge(anchor_id, kb_path=kb)
    assert res["available"] is True
    return {str(s["kp_id"]) for s in res.get("suggestions") or []}


def test_merge_same_name_cross_file(merge_kb):
    ids = _suggest_ids(merge_kb, "rl-intro-a")
    assert "rl-intro-b" in ids
    assert "unrelated-cook" not in ids


def test_merge_name_exact_duplicate_in_one_file(merge_kb):
    ids = _suggest_ids(merge_kb, "attn-mechanism")
    assert "attn-mech-typo" in ids


def test_merge_name_variant_suffix(merge_kb):
    ids = _suggest_ids(merge_kb, "policy-grad")
    assert "policy-grad-full" in ids


def test_merge_tag_bridge_only_no_name_match(merge_kb):
    """仅 tag 相同：当前 Lexical merge 不应命中。"""
    ids = _suggest_ids(merge_kb, "ddpg-algo")
    assert "dqn-discrete" not in ids


def test_merge_en_zh_not_lexical(merge_kb):
    """跨语言：当前 Lexical merge 不应命中（留待 embedding）。"""
    ids = _suggest_ids(merge_kb, "attention-en")
    assert "zh-attention-mechanism" not in ids
    assert "yizhu-jizhi" not in ids


def test_merge_id_prefix_only_not_name(merge_kb):
    ids = _suggest_ids(merge_kb, "mdp-core")
    assert "mdp-intro" not in ids


def test_merge_excludes_unrelated(merge_kb):
    ids = _suggest_ids(merge_kb, "rl-intro-a")
    assert "unrelated-cook" not in ids
