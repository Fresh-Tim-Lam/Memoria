"""SearchKernel v1.5c：RRF 融合与置信分档。"""

from memoria.services.retrieval_fusion import (
    assign_confidence_tier,
    fuse_search_results,
    reciprocal_rank_fusion,
    split_lexical_channels,
)


def test_split_lexical_channels():
    rows = [
        {"kp_id": "a", "score": 90, "sources": ["name-exact"]},
        {"kp_id": "b", "score": 70, "sources": ["auto-tag-fuzzy"]},
        {"kp_id": "c", "score": 80, "sources": ["tag-exact", "summary-fuzzy"]},
    ]
    explicit, implicit = split_lexical_channels(rows)
    assert [r["kp_id"] for r in explicit] == ["a", "c"]
    assert [r["kp_id"] for r in implicit] == ["b", "c"]


def test_rrf_boosts_multi_channel():
    channels = {
        "lexical_explicit": [{"kp_id": "a"}, {"kp_id": "b"}],
        "semantic": [{"kp_id": "b"}, {"kp_id": "c"}],
    }
    fused = reciprocal_rank_fusion(channels)
    assert fused[0][0] == "b"
    assert fused[0][1] > fused[1][1]


def test_assign_tier_high_on_id_exact():
    tier, conf = assign_confidence_tier({"sources": ["id-exact"], "score": 50})
    assert tier == "high"
    assert conf >= 90


def test_fuse_search_results_adds_tier():
    lexical = [
        {"kp_id": "x", "name": "X", "file": "a.md", "score": 88, "lexical_score": 88, "sources": ["name-exact"]},
    ]
    semantic = [
        {"kp_id": "y", "name": "Y", "file": "b.md", "score": 72, "semantic_score": 72, "sources": ["semantic"]},
    ]
    out = fuse_search_results(lexical_hits=lexical, semantic_hits=semantic, limit=5)
    assert len(out) == 2
    assert out[0]["tier"] in ("high", "medium", "low")
    assert "confidence" in out[0]
    assert "rrf_score" in out[0]
