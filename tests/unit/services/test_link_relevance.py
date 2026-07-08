"""链接 relevance 建议接口测试。"""

from __future__ import annotations

from pathlib import Path

from memoria.services.lexical_index import rebuild_lexical_index
from memoria.services.link_relevance import suggest_link_relevance

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "m3_rename_kb"


def test_suggest_link_relevance_no_kb():
    res = suggest_link_relevance(
        anchor_text="attention",
        target_ids=["transformer"],
        edge_type="reference",
        source_id="nlp-intro",
        kb_path=None,
    )
    assert res["status"] == "ok"
    assert res["suggested"] is None
    assert res["reason"] == "search_kernel_not_available"
    assert res["default"] == 0.7
    assert res["edge_type"] == "reference"


def test_suggest_link_relevance_lexical_match():
    kb = str(FIXTURE)
    rebuild_lexical_index(kb)
    res = suggest_link_relevance(
        anchor_text="待重命名",
        target_ids=["rename-kp", "other-kp"],
        edge_type="reference",
        kb_path=kb,
    )
    assert res["status"] == "ok"
    assert res["available"] is True
    assert res["suggested"] is not None
    assert res["suggested"] > 0
    assert res["best_target_id"] == "rename-kp"
